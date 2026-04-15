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
from typing import Literal

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
    """Stub — real body lands in Task 3."""
    return pd.DataFrame(columns=["cluster", "term_id", "term_name"] + [
        c for c in term2gene.columns if c not in {"term_id", "term_name", "locus_tag"}
    ])
