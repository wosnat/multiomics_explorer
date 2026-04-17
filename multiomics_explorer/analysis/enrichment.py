"""Pathway-enrichment primitives for multiomics_explorer.

Public API:
- EnrichmentInputs: Pydantic model holding gene_sets + backgrounds + metadata + validation buckets.
- de_enrichment_inputs: build EnrichmentInputs from DE results.
- fisher_ora: run Fisher-exact ORA over TERM2GENE for one or more gene sets.
- signed_enrichment_score: collapse up/down cluster pairs into a single signed row per pathway.

See docs://analysis/enrichment for methodology.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

import pandas as pd
import scipy.stats as _stats
import statsmodels.stats.multitest as _multitest


class EnrichmentInputs(BaseModel):
    """Inputs bundle for fisher_ora. Produced by de_enrichment_inputs.

    Gene-list-agnostic callers construct this directly; the DE helper is
    convenience. See docs://analysis/enrichment for end-to-end examples.
    """

    organism_name: str = Field(
        description="Single organism for all clusters (single-organism enforced).",
    )
    gene_sets: dict[str, list[str]] = Field(
        description=(
            "Cluster name -> foreground locus_tags (e.g. significant DE genes "
            "for that experiment/timepoint/direction)."
        ),
    )
    background: dict[str, list[str]] = Field(
        description=(
            "Cluster name -> universe locus_tags. Per-cluster because "
            "table_scope backgrounds vary between experiments."
        ),
    )
    cluster_metadata: dict[str, dict] = Field(
        description=(
            "Cluster name -> metadata dict (experiment_id, timepoint, "
            "direction, omics_type, table_scope, treatment_type, "
            "background_factors, is_time_course, etc.)."
        ),
    )
    not_found: list[str] = Field(
        default_factory=list,
        description="experiment_ids absent from the KG.",
    )
    not_matched: list[str] = Field(
        default_factory=list,
        description=(
            "experiment_ids that exist but belong to a different organism."
        ),
    )
    no_expression: list[str] = Field(
        default_factory=list,
        description=(
            "experiment_ids matching the organism but with no DE rows "
            "(reuses differential_expression_by_gene's bucket name)."
        ),
    )
    clusters_skipped: list[dict] = Field(
        default_factory=list,
        description=(
            "Clusters filtered out by size constraints. Each entry: "
            "{cluster_id, cluster_name, member_count, reason}."
        ),
    )
    analysis_metadata: dict = Field(
        default_factory=dict,
        description="Analysis-level metadata (analysis_id, name, cluster_type, etc.).",
    )


_REQUIRED_TERM2GENE_COLS = ("term_id", "term_name", "locus_tag")


def fisher_ora(
    gene_sets: dict[str, list[str]],
    background: dict[str, list[str]] | list[str],
    term2gene: pd.DataFrame,
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
) -> pd.DataFrame:
    """Run Fisher-exact over-representation analysis (ORA) per (cluster, term).

    The enrichment primitive. Direction-agnostic; gene-list-agnostic. Callers
    supply gene sets (one per cluster), per-cluster or shared backgrounds,
    and a TERM2GENE DataFrame (from genes_by_ontology via to_dataframe, from
    clusterProfiler, or hand-built). Returns one row per (cluster x term)
    pair that passes the per-cluster M size filter.

    Does NOT compute ``signed_score`` — that requires direction information
    this primitive doesn't know about. Attach a ``direction`` column and
    pass through ``signed_enrichment_score`` or compute ``sign * -log10(p)``
    directly.

    Parameters
    ----------
    gene_sets : dict[str, list[str]]
        Cluster name -> foreground locus_tags. Convention for the DE path is
        ``"{experiment_id}|{timepoint}|{direction}"`` keys.
    background : dict[str, list[str]] | list[str]
        Per-cluster background (dict keyed by cluster) or a single shared
        universe (list, broadcast to every cluster).
    term2gene : pandas.DataFrame
        Required columns: ``term_id``, ``term_name``, ``locus_tag``. Extra
        columns pass through to result rows. Idiomatic source is
        ``to_dataframe(genes_by_ontology(...))``.
    min_gene_set_size : int, default 5
        Per-cluster M filter: drop (cluster, term) pairs where the pathway
        has fewer than this many members in the cluster's background.
    max_gene_set_size : int or None, default 500
        Per-cluster M filter: drop pairs where M exceeds this. ``None``
        disables the upper bound.

    Returns
    -------
    pandas.DataFrame
        Long-format, compareCluster-compatible. Columns: ``cluster``,
        ``term_id``, ``term_name``, ``gene_ratio``, ``gene_ratio_numeric``,
        ``bg_ratio``, ``bg_ratio_numeric``, ``rich_factor``,
        ``fold_enrichment``, ``pvalue``, ``p_adjust``, ``count``,
        ``bg_count``, plus passthrough columns from ``term2gene``. See
        docs://analysis/enrichment for field meanings.

    Raises
    ------
    ValueError
        If ``term2gene`` is missing any of the required columns.
    ValueError
        If ``max_gene_set_size`` is set and less than ``min_gene_set_size``.

    Examples
    --------
    >>> from multiomics_explorer import fisher_ora
    >>> from multiomics_explorer.api import genes_by_ontology
    >>> from multiomics_explorer.analysis.frames import to_dataframe
    >>> term2gene = to_dataframe(genes_by_ontology(
    ...     ontology="cyanorak_role", organism="MED4", level=1,
    ... ))
    >>> gene_sets = {"treatment_up": ["PMM0123", "PMM0456"]}
    >>> background = ["PMM0001", "PMM0002"]  # truncated
    >>> df = fisher_ora(gene_sets, background, term2gene)  # doctest: +SKIP

    See Also
    --------
    de_enrichment_inputs : Build gene_sets + background from DE results.
    signed_enrichment_score : Collapse up/down cluster pairs into a signed score.
    multiomics_explorer.api.genes_by_ontology : Canonical TERM2GENE source.
    """
    missing = [c for c in _REQUIRED_TERM2GENE_COLS if c not in term2gene.columns]
    if missing:
        raise ValueError(
            f"term2gene is missing required column(s): {missing}. "
            f"Required: {list(_REQUIRED_TERM2GENE_COLS)}."
        )
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError(
            f"max_gene_set_size ({max_gene_set_size}) must be >= "
            f"min_gene_set_size ({min_gene_set_size})."
        )
    if isinstance(background, list):
        background = {c: list(background) for c in gene_sets}
    return _fisher_ora_impl(
        gene_sets=gene_sets,
        background=background,
        term2gene=term2gene,
        min_gene_set_size=min_gene_set_size,
        max_gene_set_size=max_gene_set_size,
    )


def _fisher_ora_impl(gene_sets, background, term2gene, min_gene_set_size, max_gene_set_size):
    # Build fast lookups: term_id -> frozenset(members), and name/passthrough maps.
    term_members: dict[str, frozenset] = (
        term2gene.groupby("term_id")["locus_tag"].apply(frozenset).to_dict()
    )
    term_name_map: dict[str, str] = dict(
        term2gene.drop_duplicates("term_id").set_index("term_id")["term_name"]
    )
    passthrough_cols = [
        c for c in term2gene.columns
        if c not in {"term_id", "term_name", "locus_tag"}
    ]
    passthrough_by_term: dict[str, dict] = {}
    if passthrough_cols:
        first_rows = term2gene.drop_duplicates("term_id").set_index("term_id")
        for tid in first_rows.index:
            passthrough_by_term[tid] = {
                c: first_rows.at[tid, c] for c in passthrough_cols
            }

    rows: list[dict] = []

    for cluster, gene_list in gene_sets.items():
        gene_set = set(gene_list)
        bg = set(background[cluster])
        N = len(bg)
        n = len(gene_set & bg)
        if n == 0 or N == 0:
            continue
        cluster_rows: list[dict] = []
        for term_id, members in term_members.items():
            pathway_in_bg = members & bg
            M = len(pathway_in_bg)
            if M < min_gene_set_size:
                continue
            if max_gene_set_size is not None and M > max_gene_set_size:
                continue
            k = len(pathway_in_bg & gene_set)
            a, b, c, d = k, n - k, M - k, N - n - (M - k)
            p = _stats.fisher_exact(
                [[a, b], [c, d]], alternative="greater"
            ).pvalue
            row = {
                "cluster": cluster,
                "term_id": term_id,
                "term_name": term_name_map.get(term_id, ""),
                "gene_ratio": f"{k}/{n}",
                "gene_ratio_numeric": k / n if n else 0.0,
                "bg_ratio": f"{M}/{N}",
                "bg_ratio_numeric": M / N if N else 0.0,
                "rich_factor": k / M if M else 0.0,
                "fold_enrichment": (
                    (k / n) / (M / N)
                    if n and M and N
                    else 0.0
                ),
                "pvalue": p,
                "count": k,
                "bg_count": M,
            }
            row.update(passthrough_by_term.get(term_id, {}))
            cluster_rows.append(row)
        if not cluster_rows:
            continue
        pvals = [r["pvalue"] for r in cluster_rows]
        padj = _multitest.multipletests(pvals, method="fdr_bh")[1]
        for r, pa in zip(cluster_rows, padj):
            r["p_adjust"] = float(pa)
        rows.extend(cluster_rows)

    if not rows:
        columns = [
            "cluster", "term_id", "term_name",
            "gene_ratio", "gene_ratio_numeric",
            "bg_ratio", "bg_ratio_numeric",
            "rich_factor", "fold_enrichment",
            "pvalue", "p_adjust", "count", "bg_count",
        ] + passthrough_cols
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(rows)
    return df.sort_values(
        by=["p_adjust", "cluster", "term_id"],
        ascending=[True, True, True],
    ).reset_index(drop=True)


import math as _math


def signed_enrichment_score(
    df: pd.DataFrame,
    direction_col: str = "direction",
    padj_col: str = "p_adjust",
) -> pd.DataFrame:
    """Collapse up/down cluster pairs into one signed row per (stem, term).

    Sign from the direction with the smaller ``p_adjust``; score =
    ``sign * -log10(min_padj)``. Standalone so callers re-derive under
    new cutoffs. Expects a ``direction`` column (or a caller-supplied
    equivalent) plus a cluster-name convention ``{stem}|{direction}``.

    Parameters
    ----------
    df : pandas.DataFrame
        Long-format rows from ``fisher_ora`` with at minimum ``cluster``,
        ``term_id``, the direction column, and the p_adjust column.
    direction_col : str, default 'direction'
        Column to read the direction from. ``"up"`` -> +, ``"down"`` -> -.
    padj_col : str, default 'p_adjust'
        Column to read the BH-adjusted p-value from.

    Returns
    -------
    pandas.DataFrame
        One row per ``(cluster_stem, term_id)``. Columns: ``cluster_stem``,
        ``term_id``, ``direction`` (the dominant one), ``p_adjust`` (the
        smaller of the pair), ``signed_score``. Other columns from the
        winning row are preserved.

    Examples
    --------
    >>> from multiomics_explorer import signed_enrichment_score
    >>> out = signed_enrichment_score(df_from_fisher_ora)  # doctest: +SKIP

    See Also
    --------
    fisher_ora : Produces the input DataFrame.
    """
    needed = {"cluster", "term_id", direction_col, padj_col}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(
            f"signed_enrichment_score: missing required columns: {sorted(missing)}"
        )
    work = df.copy()
    # Stem = cluster with trailing |direction stripped. Fall back to cluster
    # itself if the suffix isn't present.
    work["cluster_stem"] = work["cluster"].astype(str).where(
        ~work["cluster"].astype(str).str.endswith(("|up", "|down")),
        work["cluster"].astype(str).str.rsplit("|", n=1).str[0],
    )
    winners = (
        work.sort_values(padj_col, ascending=True)
        .drop_duplicates(subset=["cluster_stem", "term_id"], keep="first")
        .copy()
    )
    sign = winners[direction_col].map({"up": 1, "down": -1}).fillna(1)
    winners["signed_score"] = sign * winners[padj_col].apply(
        lambda p: -_math.log10(p) if p > 0 else float("inf")
    )
    return winners.reset_index(drop=True)


from typing import Any

_METADATA_FIELDS = (
    "experiment_id", "experiment_name",
    "timepoint", "timepoint_hours", "timepoint_order",
    "direction",
    "omics_type", "table_scope",
    "treatment_type", "background_factors", "growth_phase",
    "is_time_course",
)


def _normalize_timepoint(tp: Any) -> str:
    if tp is None:
        return "NA"
    if isinstance(tp, float) and _math.isnan(tp):
        return "NA"
    return str(tp)


def _call_de(**kwargs):
    """Thin indirection so tests can monkeypatch the DE call.

    Imported inside the function to avoid circular imports at module load.
    """
    from multiomics_explorer.api.functions import (
        differential_expression_by_gene as _de,
    )
    return _de(**kwargs)


def de_enrichment_inputs(
    experiment_ids: list[str],
    organism: str,
    direction: str = "both",
    significant_only: bool = True,
    timepoint_filter: list[str] | None = None,
    growth_phases: list[str] | None = None,
    *,
    conn=None,
) -> EnrichmentInputs:
    """Build EnrichmentInputs from differential-expression results.

    Calls ``differential_expression_by_gene`` once per call to get both the
    significant-gene foregrounds and the per-cluster universes (table_scope
    backgrounds), partitions rows by ``(experiment_id, timepoint, direction)``
    into clusters named ``"{experiment_id}|{timepoint}|{direction}"``, and
    surfaces partial-failure buckets on the returned ``EnrichmentInputs``.

    Parameters
    ----------
    experiment_ids : list[str]
        Experiment identifiers to pull DE rows for. Must be non-empty.
    organism : str
        Single organism name (fuzzy-matched). Required — single-organism
        enforced via ``_validate_organism_inputs``.
    direction : {'up', 'down', 'both'}, default 'both'
        Which DE directions contribute to ``gene_sets``. ``background`` is
        always the full quantified set regardless of direction.
    significant_only : bool, default True
        If True, ``gene_sets`` include only rows flagged significant.
        ``background`` is always the full set regardless of this flag.
    timepoint_filter : list[str] or None, default None
        If provided, restrict clusters to these timepoint labels. Useful
        for experiments with 10+ timepoints.
    growth_phases : list[str] or None, default None
        If provided, restrict DE rows to those whose edge-level ``growth_phase``
        property matches any of the specified values (case-insensitive). Rows
        with non-matching growth_phase are excluded from both foreground and
        background.
    conn : GraphConnection, optional
        Passed through to the DE call. Default: module default.

    Returns
    -------
    EnrichmentInputs
        Includes ``gene_sets``, ``background`` (per-cluster), and
        ``cluster_metadata`` dicts, plus three partial-failure buckets
        (``not_found``, ``not_matched``, ``no_expression``).

    Raises
    ------
    ValueError
        If ``experiment_ids`` is empty or ``direction`` invalid.
    ValueError
        If ``experiment_ids`` span multiple organisms (propagated from
        ``_validate_organism_inputs``).

    Examples
    --------
    >>> from multiomics_explorer import de_enrichment_inputs, fisher_ora
    >>> inputs = de_enrichment_inputs(
    ...     experiment_ids=["exp1"], organism="MED4",
    ... )  # doctest: +SKIP

    See Also
    --------
    fisher_ora : Primary consumer.
    multiomics_explorer.api.differential_expression_by_gene : Underlying data source.
    """
    if not experiment_ids:
        raise ValueError("at least one experiment_id required")
    if direction not in {"up", "down", "both"}:
        raise ValueError(
            f"direction must be one of 'up', 'down', 'both'; got {direction!r}"
        )

    de_full = _call_de(
        organism=organism,
        experiment_ids=experiment_ids,
        direction=None,
        significant_only=False,
        summary=False,
        limit=None,
        growth_phases=growth_phases,
        conn=conn,
    )

    gene_sets: dict[str, list[str]] = {}
    background: dict[str, list[str]] = {}
    cluster_metadata: dict[str, dict] = {}

    allowed_dirs = {"up", "down"} if direction == "both" else {direction}

    _STATUS_TO_DIR = {
        "significant_up": "up",
        "significant_down": "down",
        "up": "up",
        "down": "down",
    }

    _gp_filter = {g.lower() for g in growth_phases} if growth_phases else None

    for row in de_full.get("results", []):
        tp = _normalize_timepoint(row.get("timepoint"))
        if timepoint_filter is not None and tp not in set(timepoint_filter):
            continue
        if _gp_filter is not None:
            gp = (row.get("growth_phase") or "").lower()
            if gp not in _gp_filter:
                continue
        # Support both `direction` (unit-test mocks) and `expression_status`
        # (real DE query output).
        row_direction = row.get("direction") or _STATUS_TO_DIR.get(
            row.get("expression_status", ""), None
        )
        if row_direction not in ("up", "down"):
            continue
        exp_id = row.get("experiment_id")
        cluster = f"{exp_id}|{tp}|{row_direction}"

        background.setdefault(cluster, []).append(row["locus_tag"])
        if cluster not in cluster_metadata:
            md: dict = {}
            for field in _METADATA_FIELDS:
                md[field] = row.get(field)
            # Backfill direction from expression_status when not present directly.
            if md.get("direction") is None:
                md["direction"] = row_direction
            md["name"] = row.get("experiment_name") or row.get("name")
            md["timepoint"] = tp
            cluster_metadata[cluster] = md

        if row_direction in allowed_dirs:
            is_significant = (
                row.get("significant")
                or (row.get("expression_status", "") not in ("not_significant", ""))
            )
            if significant_only and not is_significant:
                continue
            gene_sets.setdefault(cluster, []).append(row["locus_tag"])

    for cluster in background:
        gene_sets.setdefault(cluster, [])

    return EnrichmentInputs(
        organism_name=de_full.get("organism_name", organism),
        gene_sets=gene_sets,
        background=background,
        cluster_metadata=cluster_metadata,
        not_found=list(de_full.get("not_found", []) or []),
        not_matched=list(de_full.get("not_matched", []) or []),
        no_expression=list(de_full.get("no_expression", []) or []),
    )


def cluster_enrichment_inputs(
    analysis_id: str,
    organism: str,
    min_cluster_size: int = 3,
    max_cluster_size: int | None = None,
    *,
    conn=None,
) -> EnrichmentInputs:
    """Build EnrichmentInputs from cluster memberships in a clustering analysis.

    Calls ``genes_in_cluster(analysis_id=...)`` to get all cluster members,
    groups them by cluster_name, applies size filters, and builds a
    ``cluster_union`` background from ALL clusters (including filtered ones).

    Parameters
    ----------
    analysis_id : str
        Clustering analysis identifier (e.g. ``"ca:..."``) to pull from.
    organism : str
        Single organism name (fuzzy-matched).
    min_cluster_size : int, default 1
        Clusters with fewer members are moved to ``clusters_skipped``.
    max_cluster_size : int or None, default None
        Clusters with more members are moved to ``clusters_skipped``.
    conn : GraphConnection, optional
        Passed through to API calls.

    Returns
    -------
    EnrichmentInputs
        Includes ``gene_sets``, ``background`` (cluster_union per cluster),
        ``cluster_metadata``, ``clusters_skipped``, and ``analysis_metadata``.
    """
    from multiomics_explorer.api.functions import (
        genes_in_cluster as _genes_in_cluster,
        list_clustering_analyses as _list_analyses,
    )

    cluster_result = _genes_in_cluster(
        analysis_id=analysis_id, organism=organism,
        verbose=True, limit=None, conn=conn,
    )

    analysis_meta_result = _list_analyses(
        analysis_ids=[analysis_id], limit=1, conn=conn,
    )
    analysis_meta = (
        analysis_meta_result["results"][0]
        if analysis_meta_result.get("results")
        else {}
    )

    # --- Partial-failure buckets ---
    not_found: list[str] = []
    not_matched: list[str] = []
    if not cluster_result.get("results") and cluster_result.get("total_matching", 0) == 0:
        if cluster_result.get("not_matched_organism"):
            not_matched = [analysis_id]
        elif not analysis_meta:
            not_found = [analysis_id]
        else:
            not_found = [analysis_id]

    # --- Group rows by cluster_name ---
    all_cluster_genes: dict[str, list[str]] = {}
    cluster_ids_map: dict[str, str] = {}
    cluster_verbose: dict[str, dict] = {}
    for row in cluster_result.get("results", []):
        cname = row["cluster_name"]
        all_cluster_genes.setdefault(cname, []).append(row["locus_tag"])
        if cname not in cluster_ids_map:
            cluster_ids_map[cname] = row["cluster_id"]
            cluster_verbose[cname] = {
                k: row.get(k)
                for k in (
                    "cluster_functional_description",
                    "cluster_expression_dynamics",
                    "cluster_temporal_pattern",
                )
            }

    # Union background: ALL genes from ALL clusters (including filtered ones).
    all_genes = sorted({
        lt for genes in all_cluster_genes.values() for lt in genes
    })

    # --- Apply size filters ---
    gene_sets: dict[str, list[str]] = {}
    clusters_skipped: list[dict] = []
    for cname, genes in all_cluster_genes.items():
        count = len(genes)
        if count < min_cluster_size:
            clusters_skipped.append({
                "cluster_id": cluster_ids_map[cname],
                "cluster_name": cname,
                "member_count": count,
                "reason": f"below min_cluster_size ({min_cluster_size})",
            })
            continue
        if max_cluster_size is not None and count > max_cluster_size:
            clusters_skipped.append({
                "cluster_id": cluster_ids_map[cname],
                "cluster_name": cname,
                "member_count": count,
                "reason": f"above max_cluster_size ({max_cluster_size})",
            })
            continue
        gene_sets[cname] = genes

    # Per-cluster background is the full union.
    background = {cname: list(all_genes) for cname in gene_sets}

    # --- Cluster metadata ---
    cluster_metadata: dict[str, dict] = {}
    for cname in gene_sets:
        cluster_metadata[cname] = {
            "cluster_id": cluster_ids_map[cname],
            "cluster_name": cname,
            "member_count": len(gene_sets[cname]),
            **cluster_verbose.get(cname, {}),
        }

    # --- Analysis-level metadata ---
    analysis_md = {
        "analysis_id": analysis_id,
        "analysis_name": analysis_meta.get("name")
            or cluster_result.get("analysis_name"),
        "cluster_method": analysis_meta.get("cluster_method"),
        "cluster_type": analysis_meta.get("cluster_type"),
        "omics_type": analysis_meta.get("omics_type"),
        "treatment_type": analysis_meta.get("treatment_type", []),
        "background_factors": analysis_meta.get("background_factors", []),
        "growth_phases": analysis_meta.get("growth_phases", []),
        "experiment_ids": analysis_meta.get("experiment_ids", []),
    }

    return EnrichmentInputs(
        organism_name=organism,
        gene_sets=gene_sets,
        background=background,
        cluster_metadata=cluster_metadata,
        not_found=not_found,
        not_matched=not_matched,
        no_expression=[],
        clusters_skipped=clusters_skipped,
        analysis_metadata=analysis_md,
    )
