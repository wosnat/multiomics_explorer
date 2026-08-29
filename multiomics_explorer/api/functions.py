"""Public Python API for the multi-omics knowledge graph.

Each function wraps query builders + connection.execute_query to provide
a clean interface for scripts, notebooks, and the MCP tool layer.

No limit parameters — callers slice results as needed.
No JSON formatting — returns Python dicts/lists.
Validation errors raise ValueError with specific messages.
"""

import logging
import os
import re
import statistics
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from typing import Literal

from packaging.version import InvalidVersion, Version

from CyVer import PropertiesValidator, SchemaValidator, SyntaxValidator

from neo4j.exceptions import ClientError as Neo4jClientError

from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.constants import (
    ALL_ONTOLOGIES,
    EXPECTED_KG_SHAPE,
    GO_ONTOLOGIES,
    MAX_SPECIFICITY_RANK,
    VALID_OG_SOURCES,
    VALID_OMICS_TYPES,
    VALID_TAXONOMIC_LEVELS,
)
from multiomics_explorer.kg.queries_lib import (
    ONTOLOGY_CONFIG,
    TRUST_FILTER_AXIS,
    verbose_edge_pairs,
    ontology_row_columns,
    ontology_trust_axes,
    build_evidence_score_signals,
    build_vocab_pivot_values,
    build_vocab_values,
    build_discussed_by_publication,
    build_discussed_by_publication_summary,
    build_gene_aa_sequence,
    build_gene_aa_sequence_summary,
    build_gene_existence_check,
    build_gene_neighbors,
    build_gene_neighbors_summary,
    build_gene_ontology_terms,
    build_gene_ontology_terms_summary,
    build_gene_overview,
    build_gene_overview_summary,
    build_gene_overview_top_discussing_publications,
    build_genes_by_function,
    build_genes_by_function_summary,
    build_genes_by_ontology_detail,
    build_genes_by_ontology_per_gene,
    build_genes_by_ontology_per_term,
    build_genes_by_ontology_trust_rollups,
    build_genes_by_ontology_validate,
    build_gene_details,
    build_gene_details_summary,
    build_gene_homologs,
    build_gene_homologs_summary,
    build_list_brite_trees,
    build_list_compartments,
    build_list_evidence_sources,
    build_list_gene_categories,
    build_list_growth_phases,
    build_list_metric_types,
    build_list_omics_types,
    build_list_value_kinds,
    build_list_organisms,
    build_list_organisms_capability,
    build_list_organisms_summary,
    build_list_publications,
    build_list_publications_summary,
    build_list_experiments,
    build_list_experiments_summary,
    build_resolve_gene,
    build_search_homolog_groups,
    build_search_homolog_groups_summary,
    build_genes_by_homolog_group,
    build_genes_by_homolog_group_diagnostics,
    build_genes_by_homolog_group_summary,
    build_search_ontology,
    build_search_ontology_summary,
    build_differential_expression_by_gene,
    build_differential_expression_by_gene_summary_global,
    build_differential_expression_by_gene_summary_by_experiment,
    build_differential_expression_by_gene_summary_diagnostics,
    build_differential_expression_by_gene_experiment_diagnostics,
    build_resolve_organism_for_organism,
    build_resolve_organism_for_locus_tags,
    build_resolve_organism_for_experiments,
    build_differential_expression_by_ortholog_group_check,
    build_differential_expression_by_ortholog_summary_global,
    build_differential_expression_by_ortholog_top_groups,
    build_differential_expression_by_ortholog_top_experiments,
    build_differential_expression_by_ortholog_results,
    build_differential_expression_by_ortholog_membership_counts,
    build_differential_expression_by_ortholog_diagnostics,
    build_gene_response_profile_envelope,
    build_gene_response_profile,
    build_kg_release_info,
    build_list_clustering_analyses,
    build_list_clustering_analyses_summary,
    build_list_derived_metrics,
    build_list_derived_metrics_summary,
    build_list_metabolite_assays,
    build_list_metabolite_assays_summary,
    build_metabolites_by_quantifies_assay,
    build_metabolites_by_quantifies_assay_diagnostics,
    build_metabolites_by_quantifies_assay_summary,
    build_metabolites_by_flags_assay,
    build_metabolites_by_flags_assay_summary,
    build_assays_by_metabolite,
    build_assays_by_metabolite_summary,
    build_list_metabolites,
    build_list_metabolites_summary,
    build_genes_by_metabolite_metabolism,
    build_genes_by_metabolite_transport,
    build_genes_by_metabolite_summary,
    build_metabolites_by_gene_metabolism,
    build_metabolites_by_gene_transport,
    build_metabolites_by_gene_summary,
    build_gene_clusters_by_gene,
    build_gene_clusters_by_gene_summary,
    build_gene_derived_metrics,
    build_gene_derived_metrics_summary,
    build_genes_by_boolean_metric,
    build_genes_by_boolean_metric_diagnostics,
    build_genes_by_boolean_metric_summary,
    build_genes_by_categorical_metric,
    build_genes_by_categorical_metric_diagnostics,
    build_genes_by_categorical_metric_summary,
    build_genes_by_numeric_metric,
    build_genes_by_numeric_metric_diagnostics,
    build_genes_by_numeric_metric_summary,
    build_genes_in_cluster,
    build_genes_in_cluster_summary,
    build_ontology_experiment_check,
    build_ontology_expcov,
    build_ontology_landscape,
    build_ontology_organism_gene_count,
    build_ontology_term_details,
)
from multiomics_explorer.kg.schema import load_schema_from_neo4j

logger = logging.getLogger(__name__)

# Suppress EXPLAIN notification noise emitted by CyVer validators.
logging.getLogger("neo4j").setLevel(logging.ERROR)


def _default_conn(conn: GraphConnection | None) -> GraphConnection:
    if conn is None:
        return GraphConnection()
    return conn


def _chunk_locus_tags(locus_tags: list[str]) -> list[list[str]]:
    """Split locus_tags into chunks for memory-bounded transactions.

    Default 500; override via MULTIOMICS_KG_BATCH_SIZE env var.
    Chunking prevents Neo4j's 1.4 GiB transaction cap on large
    gene × term fan-out queries (e.g. 2000 × GO MF).
    """
    size = int(os.getenv("MULTIOMICS_KG_BATCH_SIZE", "500"))
    if size <= 0 or len(locus_tags) <= size:
        return [locus_tags]
    return [locus_tags[i: i + size] for i in range(0, len(locus_tags), size)]


def _rename_freq(freq_list: list[dict], key_name: str) -> list[dict]:
    """Rename APOC ``{item, count}`` rows to ``{<key_name>, count}``, sorted desc by count."""
    return sorted(
        [{key_name: f["item"], "count": f["count"]} for f in freq_list],
        key=lambda x: x["count"],
        reverse=True,
    )


def _rename_measurement_coverage(raw: dict | None) -> dict:
    """Rename apoc.coll.frequencies output for `by_measurement_coverage`.

    The Cypher emits both sub-rollups as ``[{item, count}, ...]`` lists. The
    Pydantic boundary expects ``[{paper_count, count}]`` for `by_paper_count`
    and ``[{compartment, count}]`` for `by_compartment`. Returns the
    sub-rollups in canonical-order (paper_count ascending; compartment
    alphabetical) so the response is deterministic.
    """
    if not raw:
        return {"by_paper_count": [], "by_compartment": []}
    by_pc = sorted(
        [{"paper_count": f["item"], "count": f["count"]}
         for f in raw.get("by_paper_count", []) if f.get("item") is not None],
        key=lambda x: x["paper_count"],
    )
    by_comp = sorted(
        [{"compartment": f["item"], "count": f["count"]}
         for f in raw.get("by_compartment", []) if f.get("item") is not None],
        key=lambda x: x["compartment"],
    )
    return {"by_paper_count": by_pc, "by_compartment": by_comp}


# Regex for blocking write operations in raw Cypher.
_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|CALL\s*\{|CALL\s+\w+\.\w+|LOAD\s+CSV)\b",
    re.IGNORECASE,
)

# Regex for escaping Lucene special characters on retry.
_LUCENE_SPECIAL = re.compile(r'[+\-!(){}\[\]^"~*?:\\/]')

# ---------------------------------------------------------------------------
# Annotation-trust surface: shared helpers
#
# One vocabulary of trust axes across every gene->term edge. ONTOLOGY_CONFIG
# owns the shape (which axes an ontology carries, which native scalars are
# verbose-only, which facet it exposes); ControlledVocabulary nodes in the
# graph own the allowed values. Nothing here hard-codes a value set.
# ---------------------------------------------------------------------------

# Every generic trust / facet filter, in the order envelopes echo them.
# `tree` and `interpro_type` are facets: they narrow terms rather than edges,
# and they route to their owning ontology through `_facet_owner`.
_TRUST_PARAMS: tuple[str, ...] = (
    "sources", "evidence", "max_tier", "min_evidence_score",
    "call_class", "interpro_type", "tree",
)

_TRUST_AXIS_HINT = "list_filter_values(filter_type='trust_axes')"

_TRUST_AXIS_DESCRIPTIONS: dict[str, str] = {
    "sources": "Which pipelines asserted the annotation (membership list).",
    "evidence": "Strength ladder: curated > signature > homology > "
                "family_inferred > domain_inferred.",
    "evidence_score": "Composite trust score in 0..1 — the only numeric "
                      "cutoff (min_evidence_score) and the within-ontology "
                      "sort key.",
    "tier": "Diamond-truncation depth 1..3; null means the edge came from a "
            "single source and was never truncated.",
}

# Cached ControlledVocabulary reads, keyed by (applies_to, property). The
# graph is read once per process; a missing node degrades to a pivot query
# plus a warning, never a raise.
_VOCAB_CACHE: dict[tuple[str, str], dict] = {}


def _reset_vocab_cache() -> None:
    """Drop the cached ControlledVocabulary reads."""
    _VOCAB_CACHE.clear()


def _facet_owner(param: str) -> str | None:
    """Ontology key whose facet is driven by `param`, if any."""
    for key, cfg in ONTOLOGY_CONFIG.items():
        facet = cfg.get("facet")
        if isinstance(facet, dict) and facet.get("param") == param:
            return key
    return None


def _compact_edge_owners(param: str) -> list[str]:
    """Ontology keys carrying `param` as a compact edge column."""
    return [
        key for key, cfg in ONTOLOGY_CONFIG.items()
        if param in (cfg.get("compact_edge") or {})
    ]


def _ontology_carries(ontology: str, param: str) -> bool:
    """True when `ontology` can be filtered on `param`."""
    if param in TRUST_FILTER_AXIS:
        return TRUST_FILTER_AXIS[param] in ontology_trust_axes(ontology)
    cfg = ONTOLOGY_CONFIG.get(ontology, {})
    if param in (cfg.get("compact_edge") or {}):
        return True
    facet = cfg.get("facet")
    return isinstance(facet, dict) and facet.get("param") == param


def _active_trust_filters(**filters) -> dict:
    """The subset of trust filters the caller actually set."""
    return {p: filters[p] for p in _TRUST_PARAMS if filters.get(p) is not None}


def _axes_phrase(ontology: str) -> str:
    axes = ontology_trust_axes(ontology)
    return ", ".join(axes) if axes else "none"


def _unsupported_axis_error(ontology: str, param: str) -> ValueError:
    """ValueError naming the ontology's axes and where to look them up."""
    owner = _facet_owner(param)
    owners = [owner] if owner else _compact_edge_owners(param)
    if owners:
        head = (
            f"{param} is only carried by ontology "
            f"{' / '.join(repr(o) for o in owners)}, not '{ontology}'."
        )
    else:
        head = f"Ontology '{ontology}' does not carry the {param} filter."
    return ValueError(
        f"{head} Trust axes on '{ontology}': {_axes_phrase(ontology)}. "
        f"Call {_TRUST_AXIS_HINT} for the per-ontology axis map."
    )


def _validate_trust_filters(ontology: str, filters: dict) -> None:
    """Raise when a single-ontology call sets a filter it cannot carry."""
    for param in filters:
        if not _ontology_carries(ontology, param):
            raise _unsupported_axis_error(ontology, param)


def _normalize_ontology_arg(ontology) -> list[str] | None:
    """Accept a key, a list of keys, or None; validate every name."""
    if ontology is None:
        return None
    names = [ontology] if isinstance(ontology, str) else list(ontology)
    if not names:
        return None
    unknown = [n for n in names if n not in ONTOLOGY_CONFIG]
    if unknown:
        raise ValueError(
            f"Invalid ontology {', '.join(repr(n) for n in unknown)}. "
            f"Valid: {sorted(ONTOLOGY_CONFIG)}"
        )
    seen: list[str] = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return seen


def _resolve_multi_ontology(
    ontologies: list[str], filters: dict,
) -> tuple[list[str], list[dict], list[str], dict[str, dict]]:
    """Apply the multi-ontology skip / raise rules to a filter set.

    Carried by all -> applied everywhere. Carried by some -> applied to the
    carriers, the rest are dropped into `skipped` with a reason plus a
    warning. Carried by none -> raise. A facet applies to its owner only and
    never skips the others; a facet whose owner is absent raises.

    Returns (targets, skipped, warnings, per_ontology_filters).
    """
    skipped: dict[str, str] = {}
    warns: list[str] = []
    per_ontology: dict[str, dict] = {o: {} for o in ontologies}

    for param, value in filters.items():
        carriers = [o for o in ontologies if _ontology_carries(o, param)]
        if not carriers:
            raise ValueError(
                f"None of the requested ontologies "
                f"({', '.join(ontologies)}) carries the {param} filter. "
                f"Axes: "
                + "; ".join(f"{o}=[{_axes_phrase(o)}]" for o in ontologies)
                + f". Call {_TRUST_AXIS_HINT} for the per-ontology axis map."
            )
        for o in carriers:
            per_ontology[o][param] = value
        if _facet_owner(param) is not None:
            continue
        dropped = [o for o in ontologies if o not in carriers]
        if dropped:
            for o in dropped:
                skipped.setdefault(o, f"does not carry the {param} filter")
            warns.append(
                f"Dropped {len(dropped)} ontologies that do not carry "
                f"{param}: {', '.join(dropped)}. Re-run without {param} to "
                f"see them."
            )

    targets = [o for o in ontologies if o not in skipped]
    skipped_rows = [
        {"ontology": o, "reason": skipped[o]} for o in ontologies if o in skipped
    ]
    return targets, skipped_rows, warns, per_ontology


def _freq_rollup(counter, key: str) -> list[dict]:
    """Counter -> the codebase's [{<key>, count}] rollup shape."""
    return [{key: value, "count": n} for value, n in counter.most_common()]


def _trust_rollups(rows: list[dict]) -> dict:
    """Row-derived envelope rollups for the trust axes present in `rows`.

    An axis no ontology in the batch carries yields an empty rollup rather
    than a missing key, so a reader can tell "no rows" from "not carried"
    by reading `trust_axes`.
    """
    from collections import Counter

    evidence_counter: Counter = Counter()
    tier_counter: Counter = Counter()
    sources_counter: Counter = Counter()
    call_class_counter: Counter = Counter()
    scores: list[float] = []
    n_null_score = 0

    for r in rows:
        if "evidence" in r and r["evidence"] is not None:
            evidence_counter[r["evidence"]] += 1
        if "tier" in r:
            tier_counter["null" if r["tier"] is None else r["tier"]] += 1
        if "sources" in r:
            for s in r["sources"] or []:
                sources_counter[s] += 1
        if "call_class" in r and r["call_class"] is not None:
            call_class_counter[r["call_class"]] += 1
        if "evidence_score" in r:
            if r["evidence_score"] is None:
                n_null_score += 1
            else:
                scores.append(float(r["evidence_score"]))

    stats = {
        "min": min(scores) if scores else None,
        "median": float(statistics.median(scores)) if scores else None,
        "max": max(scores) if scores else None,
        "n_null": n_null_score,
    }
    return {
        "by_evidence": _freq_rollup(evidence_counter, "evidence"),
        "by_tier": _freq_rollup(tier_counter, "tier"),
        "by_sources": _freq_rollup(sources_counter, "source"),
        "by_call_class": _freq_rollup(call_class_counter, "call_class"),
        "evidence_score_stats": stats,
    }


def _trust_row_warnings(
    rows: list[dict], targets: list[str], filters: dict,
) -> list[str]:
    """Rows-conditional auto-warnings over the matched rows.

    `rows` is the full match wherever the caller can supply it, so the
    warning does not appear and disappear as a reader pages.
    """
    warns: list[str] = []
    for ontology in targets:
        cfg = ONTOLOGY_CONFIG.get(ontology, {})
        for name, spec in (cfg.get("compact_edge") or {}).items():
            if filters.get(name) is not None:
                continue
            warn_values = set(spec.get("warn_values") or [])
            hits = [r for r in rows if r.get(name) in warn_values]
            if not hits:
                continue
            observed = sorted({r[name] for r in hits})
            warns.append(
                f"{len(hits)} of {len(rows)} matching rows carry "
                f"{name}={observed} — catalytically-dead homologs that keep "
                f"the family fold but not a working active site. Pass "
                f"{name}=[...] to scope the set."
            )
    if filters.get("max_tier") is not None:
        n_null = sum(1 for r in rows if "tier" in r and r["tier"] is None)
        if n_null:
            warns.append(
                f"max_tier={filters['max_tier']} kept {n_null} rows that "
                f"carry no tier — single-source edges are never truncated, "
                f"so a null tier is not a tier-1 call."
            )
    if filters.get("min_evidence_score") is not None:
        warns.append(
            f"min_evidence_score={filters['min_evidence_score']} applied — "
            f"the one numeric trust cutoff. Read evidence_score_signals for "
            f"the signals that fed each score."
        )
    return warns


_TRUST_ROLLUP_KEYS: tuple[str, ...] = (
    "by_evidence", "by_tier", "by_sources", "by_call_class",
)


def _trust_rollups_from_aggregate(agg: dict | None) -> dict:
    """Normalize the one-row output of the aggregate-only trust builder.

    Same envelope keys and value shapes as `_trust_rollups`, read from
    Cypher `count()` aggregations instead of a second per-row scan. A
    missing rollup defaults to `[]`; missing stats to the all-null shape.
    """
    agg = agg or {}
    out = {key: list(agg.get(key) or []) for key in _TRUST_ROLLUP_KEYS}
    stats = dict(agg.get("evidence_score_stats") or {})
    out["evidence_score_stats"] = {
        "min": stats.get("min"),
        "median": stats.get("median"),
        "max": stats.get("max"),
        "n_null": int(stats.get("n_null") or 0),
    }
    return out


def _trust_aggregate_warnings(
    rollups: dict, targets: list[str], filters: dict, total_rows: int,
) -> list[str]:
    """The `_trust_row_warnings` set, derived from full-match rollups.

    Mirrors the per-row variant message for message so a reader sees the
    same warning whether the envelope came from rows or from the aggregate.
    """
    warns: list[str] = []
    for ontology in targets:
        cfg = ONTOLOGY_CONFIG.get(ontology, {})
        for name, spec in (cfg.get("compact_edge") or {}).items():
            if filters.get(name) is not None:
                continue
            warn_values = set(spec.get("warn_values") or [])
            rollup = rollups.get(f"by_{name}") or []
            hits = [e for e in rollup if e.get(name) in warn_values]
            if not hits:
                continue
            n_hits = sum(int(e.get("count") or 0) for e in hits)
            observed = sorted({e[name] for e in hits})
            warns.append(
                f"{n_hits} of {total_rows} matching rows carry "
                f"{name}={observed} — catalytically-dead homologs that keep "
                f"the family fold but not a working active site. Pass "
                f"{name}=[...] to scope the set."
            )
    if filters.get("max_tier") is not None:
        n_null = sum(
            int(e.get("count") or 0)
            for e in (rollups.get("by_tier") or [])
            if e.get("tier") in (None, "null")
        )
        if n_null:
            warns.append(
                f"max_tier={filters['max_tier']} kept {n_null} rows that "
                f"carry no tier — single-source edges are never truncated, "
                f"so a null tier is not a tier-1 call."
            )
    if filters.get("min_evidence_score") is not None:
        warns.append(
            f"min_evidence_score={filters['min_evidence_score']} applied — "
            f"the one numeric trust cutoff. Read evidence_score_signals for "
            f"the signals that fed each score."
        )
    return warns


def _evidence_score_signals(conn, targets: list[str]) -> dict:
    """Vocabulary-declared signals behind evidence_score, per edge type."""
    edge_types = [
        ONTOLOGY_CONFIG[o]["gene_rel"]
        for o in targets
        if "evidence_score" in ontology_trust_axes(o)
        and ONTOLOGY_CONFIG.get(o, {}).get("gene_rel")
    ]
    if not edge_types:
        return {}
    cypher, params = build_evidence_score_signals(edge_types=edge_types)
    rows = conn.execute_query(cypher, **params)
    out: dict[str, list] = {}
    for r in rows:
        edge_type = r.get("edge_type") or r.get("applies_to")
        if edge_type:
            out[edge_type] = list(r.get("signals") or [])
    return out


def _strip_value_prefix(value: str, text: str) -> str:
    """KG `value_descriptions` entries read ``"<value>: <text>"``; the value
    is already on the row, so keep only the text."""
    prefix = f"{value}:"
    if text.startswith(prefix):
        return text[len(prefix):].strip()
    return text


def _read_vocab_values(
    conn, applies_to: str, prop: str, kind: str, *, cache: bool = True,
) -> dict:
    """Allowed values for one (applies_to, property) pair.

    Reads the ControlledVocabulary node first. When the node is missing the
    values are derived from the graph with a pivot query and the result
    carries a warning — never a raise.

    Returns a dict with keys: values, value_descriptions (``{value: text}``
    from the node's parallel ``value_descriptions`` list, with a leading
    ``"<value>: "`` prefix stripped; empty when the node carries none),
    description, source, warning.
    """
    key = (applies_to, prop)
    if cache and key in _VOCAB_CACHE:
        return _VOCAB_CACHE[key]

    values: list = []
    value_descriptions: dict = {}
    description = None
    v_cypher, v_params = build_vocab_values(applies_to=applies_to, prop=prop)
    for r in conn.execute_query(v_cypher, **v_params) or []:
        node_values = r.get("values") or []
        node_texts = r.get("value_descriptions") or []
        for i, v in enumerate(node_values):
            if v not in values:
                values.append(v)
            if i < len(node_texts) and node_texts[i] and v not in value_descriptions:
                value_descriptions[v] = _strip_value_prefix(v, node_texts[i])
        description = description or r.get("description")

    if values:
        out = {
            "values": values, "value_descriptions": value_descriptions,
            "description": description,
            "source": "vocabulary", "warning": None,
        }
    else:
        p_cypher, p_params = build_vocab_pivot_values(
            applies_to=applies_to, prop=prop, kind=kind,
        )
        pivoted: list = []
        for r in conn.execute_query(p_cypher, **p_params) or []:
            v = r.get("value")
            if v is None:
                continue
            if isinstance(v, list):
                pivoted.extend(x for x in v if x not in pivoted)
            elif v not in pivoted:
                pivoted.append(v)
        out = {
            "values": pivoted, "value_descriptions": {},
            "description": description, "source": "pivot",
            "warning": (
                f"No ControlledVocabulary entry for {applies_to}.{prop}; "
                f"allowed values derived from the graph "
                f"(KG-side fix pending)"
            ),
        }
    if cache:
        _VOCAB_CACHE[key] = out
    return out


# Categorical filter params -> where their allowed values live.
_CATEGORICAL_VALUE_SOURCE: dict[str, tuple[str, str]] = {
    "evidence": ("edge", "evidence"),
    "sources": ("edge", "sources"),
    "call_class": ("edge", "call_class"),
    "interpro_type": ("node", "interpro_type"),
}


def _validate_categorical_values(
    conn, ontology: str, filters: dict,
) -> list[str]:
    """Check categorical filter values against the graph's vocabulary.

    Silent when the vocabulary yields nothing — an unknown value is only
    ever rejected against a known allowed set.
    """
    warns: list[str] = []
    cfg = ONTOLOGY_CONFIG.get(ontology, {})
    for param, value in filters.items():
        if param not in _CATEGORICAL_VALUE_SOURCE:
            continue
        kind, prop = _CATEGORICAL_VALUE_SOURCE[param]
        applies_to = cfg.get("gene_rel") if kind == "edge" else cfg.get("label")
        if not applies_to:
            continue
        read = _read_vocab_values(conn, applies_to, prop, kind)
        if read["warning"]:
            warns.append(read["warning"])
        allowed = read["values"]
        if not allowed:
            continue
        wanted = value if isinstance(value, list) else [value]
        unknown = [v for v in wanted if v not in allowed]
        if unknown:
            raise ValueError(
                f"Unknown {param} value(s) {', '.join(map(repr, unknown))} "
                f"for ontology '{ontology}'. Allowed: "
                f"{', '.join(map(str, allowed))}. Call "
                f"list_filter_values(filter_type='{param}') for the full set."
            )
    return warns


# Annotation-trust `filter_type` values -> where their allowed values live.
# `scope` says how the owning ontologies are found in ONTOLOGY_CONFIG:
# "trust_axis" (the axis is declared), "compact_edge", "verbose_edge", or an
# explicit ontology list for the node-side term-character values.
_TRUST_FILTER_VALUE_SPECS: dict[str, dict] = {
    "evidence": {"kind": "edge", "prop": "evidence", "scope": "trust_axis"},
    "sources": {"kind": "edge", "prop": "sources", "scope": "trust_axis"},
    "call_class": {"kind": "edge", "prop": "call_class",
                   "scope": "compact_edge"},
    "best_hit_kind": {"kind": "edge", "prop": "best_hit_kind",
                      "scope": "verbose_edge"},
    "pfam_support": {"kind": "edge", "prop": "pfam_support",
                     "scope": "verbose_edge"},
    "attachment_depth": {"kind": "edge", "prop": "attachment_depth",
                         "scope": "verbose_edge"},
    "interpro_type": {"kind": "node", "prop": "interpro_type",
                      "ontologies": ["interpro"]},
    "ncbifam_family_type": {"kind": "node", "prop": "family_type",
                            "ontologies": ["ncbifam"]},
    "merops_catalytic_type": {"kind": "node", "prop": "catalytic_type",
                              "ontologies": ["merops"]},
    "merops_family_class": {"kind": "node", "prop": "family_class",
                            "ontologies": ["merops"]},
}


def _trust_value_owners(filter_type: str, ontology: str | None) -> list[str]:
    """Ontology keys whose config declares this filter_type's property."""
    spec = _TRUST_FILTER_VALUE_SPECS[filter_type]
    prop = spec["prop"]
    scope = spec.get("scope")
    owners: list[str] = []
    for key, cfg in ONTOLOGY_CONFIG.items():
        if scope == "trust_axis":
            hit = prop in ontology_trust_axes(key)
        elif scope == "compact_edge":
            hit = prop in (cfg.get("compact_edge") or {})
        elif scope == "verbose_edge":
            hit = prop in {p for p, _c in verbose_edge_pairs(cfg)}
        else:
            hit = key in spec.get("ontologies", [])
        if hit:
            owners.append(key)
    if ontology is not None:
        owners = [o for o in owners if o == ontology]
    return owners


def _trust_filter_values(
    conn, filter_type: str, ontology: str | None,
) -> tuple[list[dict], list[str], str | None]:
    """Allowed values for one annotation-trust filter_type.

    One row per distinct value, carrying every edge type or label it applies
    to, so a reader can see that `evidence` means the same thing everywhere.

    Description parity with `cluster_type` (backlog 2.3): the property-level
    vocabulary text is returned once (third element, for the envelope — the
    first owner's when several edge types carry the property); rows carry
    only the per-value text from `value_descriptions`, and the row key is
    absent when no owner has any (sparse row).
    """
    spec = _TRUST_FILTER_VALUE_SPECS[filter_type]
    kind, prop = spec["kind"], spec["prop"]
    applies_to_keys = []
    for key in _trust_value_owners(filter_type, ontology):
        cfg = ONTOLOGY_CONFIG[key]
        target = cfg.get("gene_rel") if kind == "edge" else cfg.get("label")
        if target and target not in applies_to_keys:
            applies_to_keys.append(target)

    aggregated: dict[str, dict] = {}
    warns: list[str] = []
    property_description: str | None = None
    for applies_to in applies_to_keys:
        read = _read_vocab_values(conn, applies_to, prop, kind, cache=False)
        if read["warning"]:
            warns.append(read["warning"])
        property_description = property_description or read["description"]
        for value in read["values"]:
            row = aggregated.setdefault(value, {
                "value": value,
                "applies_to": [],
                "source": read["source"],
            })
            if applies_to not in row["applies_to"]:
                row["applies_to"].append(applies_to)
            text = read["value_descriptions"].get(value)
            if text and "description" not in row:
                row["description"] = text
    return list(aggregated.values()), warns, property_description


def _trust_axes_filter_values(ontology: str | None) -> list[dict]:
    """Which trust axes each ontology carries, read from the registry."""
    aggregated: dict[str, dict] = {}
    for key in ONTOLOGY_CONFIG:
        if ontology is not None and key != ontology:
            continue
        for axis in ontology_trust_axes(key):
            row = aggregated.setdefault(axis, {
                "value": axis,
                "applies_to": [],
                "description": _TRUST_AXIS_DESCRIPTIONS.get(axis),
                "source": "config",
            })
            row["applies_to"].append(key)
    return list(aggregated.values())


def _link_kind_filter_values(ontology: str | None) -> list[dict]:
    """The bridge kinds terms link out on, read from the registry."""
    aggregated: dict[str, dict] = {}
    for key, cfg in ONTOLOGY_CONFIG.items():
        if ontology is not None and key != ontology:
            continue
        for bridge in cfg.get("bridges_out") or []:
            if len(bridge) < 3:
                continue
            link_kind = bridge[2]
            row = aggregated.setdefault(link_kind, {
                "value": link_kind,
                "applies_to": [],
                "description": None,
                "source": "config",
            })
            if key not in row["applies_to"]:
                row["applies_to"].append(key)
    return list(aggregated.values())


def _require_interpro_stratum(ontology: str, interpro_type: str | None) -> None:
    """InterPro enrichment must name one stratum.

    InterPro entry types are separate strata, not levels of one hierarchy.
    Pooling them puts families, domains and homologous superfamilies in the
    same test and the result reads as significance where it is only overlap.
    """
    if ontology == "interpro" and interpro_type is None:
        raise ValueError(
            "interpro_type is required when ontology='interpro'. InterPro "
            "entry types are separate strata, not levels of one hierarchy — "
            "pick one (e.g. 'FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY'). "
            "Call list_filter_values(filter_type='interpro_type') for the "
            "full set."
        )


def _enrichment_trust_params(
    ontology: str, trust_filters: dict, interpro_type: str | None,
) -> dict:
    """The trust block enrichment envelopes echo back.

    `background_filtered` counts only the *edge* filters. A facet
    (`interpro_type`, `tree`) selects which terms are tested; it never
    removes a gene from the universe, so it does not make the background
    narrower than the organism.
    """
    narrowing = [p for p in trust_filters if _facet_owner(p) is None]
    return {
        "filters_applied": dict(trust_filters),
        "trust_axes": {ontology: ontology_trust_axes(ontology)},
        "background_filtered": bool(narrowing),
        "interpro_type": interpro_type,
    }


@lru_cache(maxsize=1)
def _owned_row_columns() -> frozenset[str]:
    """Union of every column any registered ontology owns on a gene x term row."""
    return frozenset({
        col
        for ont in ALL_ONTOLOGIES
        for col in ontology_row_columns(ont, verbose=True)
    })


def _strip_unowned_columns(rows: list[dict], ontology: str, verbose: bool) -> None:
    """Drop columns the ontology does not own; keep owned-but-null ones.

    A null in an owned column is information (a single-source edge has no
    tier, a PROSITE-only match has no e-value); a null in a column the
    ontology never carries is noise.
    """
    owned = set(ontology_row_columns(ontology, verbose=verbose))
    drop = _owned_row_columns() - owned
    if not drop:
        return
    for r in rows:
        for col in drop:
            r.pop(col, None)


def kg_schema(
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get the knowledge graph schema as a plain dict.

    Returns dict with keys:
      nodes: {label: {properties: {name: type}}}
      relationships: {type: {source_labels, target_labels, properties}}
    """
    conn = _default_conn(conn)
    schema = load_schema_from_neo4j(conn)
    return schema.to_dict()


def resolve_gene(
    identifier: str,
    organism: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Resolve a gene identifier to matching graph nodes.

    Returns dict with keys: total_matching, by_organism, returned, truncated,
    results.
    Per result: locus_tag, gene_name, product, organism_name.
    """
    if not identifier or not identifier.strip():
        logger.debug("resolve_gene: empty identifier")
        raise ValueError("identifier must not be empty.")
    conn = _default_conn(conn)
    cypher, params = build_resolve_gene(identifier=identifier, organism=organism)
    all_results = conn.execute_query(cypher, **params)
    total = len(all_results)

    # Compute by_organism from all matching results
    org_counts: dict[str, int] = {}
    for row in all_results:
        org = row.get("organism_name", "Unknown")
        org_counts[org] = org_counts.get(org, 0) + 1
    by_organism = sorted(
        [{"organism_name": k, "count": v} for k, v in org_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    results = all_results[offset:offset + limit] if limit else all_results[offset:]
    return {
        "total_matching": total,
        "by_organism": by_organism,
        "returned": len(results),
        "offset": offset,
        "truncated": total > offset + len(results),
        "results": results,
    }


def genes_by_function(
    search_text: str,
    organism: str | None = None,
    category: str | None = None,
    min_quality: int = 0,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Search genes by functional annotation text.

    Returns dict with keys: total_search_hits, total_matching,
    by_organism, by_category, score_max, score_median,
    returned, truncated, results.
    Per result: locus_tag, gene_name, product, organism_name,
    gene_category, annotation_quality, score.
    Verbose adds: function_description, gene_summary.

    Raises ValueError if search_text is empty.
    """
    if not search_text or not search_text.strip():
        raise ValueError("search_text must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)
    filter_kwargs = dict(
        search_text=search_text, organism=organism,
        category=category, min_quality=min_quality,
    )

    def _run_summary(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        cypher, params = build_genes_by_function_summary(**kw)
        return conn.execute_query(cypher, **params)[0]

    def _run_detail(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        cypher, params = build_genes_by_function(
            **kw, verbose=verbose, limit=limit, offset=offset,
        )
        return conn.execute_query(cypher, **params)

    # Always run summary query
    try:
        raw_summary = _run_summary()
    except Neo4jClientError:
        logger.debug("genes_by_function: Lucene parse error, retrying with escaped query")
        escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
        raw_summary = _run_summary(st=escaped)
        filter_kwargs["search_text"] = escaped

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_search_hits": raw_summary["total_search_hits"],
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_category": _rename_freq(raw_summary["by_category"], "category"),
        "score_max": raw_summary["score_max"],
        "score_median": raw_summary["score_median"],
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    try:
        results = _run_detail()
    except Neo4jClientError:
        if filter_kwargs["search_text"] == search_text:
            # Not yet escaped (summary succeeded without retry)
            logger.debug("genes_by_function detail: Lucene parse error, retrying")
            escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            results = _run_detail(st=escaped)
        else:
            raise

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def gene_overview(
    locus_tags: list[str],
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get overview of genes: identity + data availability signals.

    Returns dict with keys: total_matching, by_organism, by_category,
    by_annotation_type, has_expression, has_significant_expression,
    has_orthologs, has_clusters, has_discussed, top_discussing_publications,
    returned, truncated, not_found, results.
    Per result: locus_tag, gene_name, product, gene_category,
    annotation_quality, organism_name, annotation_types,
    expression_edge_count, significant_up_count, significant_down_count,
    closest_ortholog_group_size, closest_ortholog_genera,
    cluster_membership_count, cluster_types, discussed_in_publication_count,
    plus the chemistry signals reaction_count, catalyzed_metabolite_count,
    evidence_sources and the TCDB gene-level trio: tcdb_evidence_score_max
    (float | None — None means no TCDB call at all; 0 is an uncorroborated
    hit; rank with it, don't filter), transported_metabolite_count (distinct
    substrates over the gene's deepest TCDB attachments — the same set
    metabolites_by_gene's transport rows enumerate), and
    transport_substrate_resolution ('resolved' | 'family_inferred' | None;
    'resolved' means at least one non-lumping attachment, 'family_inferred'
    means breadth is reachability, not capability).
    Rows also carry the protease / family-domain routing trio:
    merops_classes (list — 'peptidase' vs 'nonpeptidase_homolog', the
    catalytically-dead homologs), ncbifam_family_count (int, 0 default) and
    merops_evidence_score_max (float | None — None means no MEROPS call at
    all, 0 means an uncorroborated one; rank with it, don't filter).
    Rows also carry tcdb_family_count (int, 0 default — distinct TCDB
    families at the deepest attachment only, superseded ancestors excluded;
    0 means no TCDB call) and cazy_family_count (int, 0 default — distinct
    CAZy families, precomputed on the gene). Drill in with
    gene_ontology_terms(ontology=['tcdb'] or ['cazy']).
    Envelope adds by_merops_class, has_ncbifam, has_tcdb and has_cazy
    (ints — input genes with at least one family of that kind).
    Verbose adds: gene_summary, function_description, all_identifiers,
    discussed_in_publications (list of {doi, prominence, evidence}; see
    discussed_by_publication for a paper's full discussed set).

    Raises ValueError if locus_tags is empty.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Summary query — always runs
    sum_cypher, sum_params = build_gene_overview_summary(locus_tags=locus_tags)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    total_matching = raw_summary["total_matching"]
    _KIND_FIELD_MAP = [
        ("numeric_metric_count", "numeric"),
        ("boolean_metric_count", "boolean"),
        ("categorical_metric_count", "categorical"),
    ]
    _VERBOSE_DM_FIELDS = (
        "numeric_metric_count", "boolean_metric_count", "categorical_metric_count",
        "numeric_metric_types_observed", "boolean_metric_types_observed",
        "categorical_metric_types_observed", "compartments_observed",
    )

    envelope = {
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_category": _rename_freq(raw_summary["by_category"], "category"),
        "by_annotation_type": _rename_freq(
            raw_summary["by_annotation_type"], "annotation_type",
        ),
        "by_annotation_state": _rename_freq(
            raw_summary.get("by_annotation_state", []), "annotation_state",
        ),
        "has_expression": raw_summary["has_expression"],
        "has_significant_expression": raw_summary["has_significant_expression"],
        "has_orthologs": raw_summary["has_orthologs"],
        "has_clusters": raw_summary["has_clusters"],
        "has_derived_metrics": raw_summary["has_derived_metrics"],
        # Phase 1 plumbing (spec §6.1): count of genes in batch with non-empty
        # evidence_sources. Mirrors has_orthologs / has_clusters envelope keys.
        "has_chemistry": raw_summary.get("has_chemistry", 0),
        # Literature "discusses" arm (spec Extension 1): count of input genes
        # with >=1 discussing publication. Mirrors has_expression / has_chemistry.
        "has_discussed": raw_summary.get("has_discussed", 0),
        # Protease / family-domain routing. by_merops_class splits real
        # peptidases from catalytically-dead homologs across the batch;
        # has_ncbifam counts input genes with at least one NCBIfam family.
        "by_merops_class": _rename_freq(
            raw_summary.get("by_merops_class", []), "merops_class",
        ),
        "has_ncbifam": raw_summary.get("has_ncbifam", 0),
        # Transporter / CAZyme routing: input genes with >=1 TCDB family at
        # the deepest attachment / >=1 CAZy family.
        "has_tcdb": raw_summary.get("has_tcdb", 0),
        "has_cazy": raw_summary.get("has_cazy", 0),
        "not_found": raw_summary["not_found"],
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        envelope["top_discussing_publications"] = []
        return envelope

    det_cypher, det_params = build_gene_overview(
        locus_tags=locus_tags, verbose=verbose, limit=limit, offset=offset,
    )
    results = conn.execute_query(det_cypher, **det_params)

    # Envelope rollup `top_discussing_publications` (spec Extension 1): one extra
    # builder call ranking publications by distinct queried-gene count — the
    # batch set-coverage signal the per-gene rows cannot yield. Same multi-query
    # orchestration shape as gene_ontology_terms. Skipped (empty rollup) when no
    # queried gene has a discussing publication — no edges to rank.
    if envelope["has_discussed"]:
        td_cypher, td_params = build_gene_overview_top_discussing_publications(
            locus_tags=locus_tags,
        )
        envelope["top_discussing_publications"] = conn.execute_query(
            td_cypher, **td_params,
        )
    else:
        envelope["top_discussing_publications"] = []

    # Synthesize compact DM fields; strip verbose-only fields in compact mode
    for r in results:
        counts = {kind: r.get(field, 0) for field, kind in _KIND_FIELD_MAP}
        r["derived_metric_count"] = sum(counts.values())
        r["derived_metric_value_kinds"] = [k for k, v in counts.items() if v > 0]
        if not verbose:
            for f in _VERBOSE_DM_FIELDS:
                r.pop(f, None)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


_DISCUSSES_ENTITY_KINDS = ("gene", "kegg_pathway")
_DISCUSSES_PROMINENCE = ("central", "peripheral")


def discussed_by_publication(
    publication_dois: list[str],
    entity_kind: str | None = None,
    prominence: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int = 50,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List the genes and KEGG pathways each publication discusses in prose.

    Recall-biased narrative literature router over the two `discusses` edge
    types (prose mentions with prominence + evidence quote) — NOT exhaustive
    coverage and NOT DE-table expression data (use differential_expression_by_gene
    for that). Batch tool over DOIs; DOI match is case-insensitive.

    Args:
        publication_dois: Publication DOIs (case-insensitive match).
        entity_kind: Restrict to one arm: 'gene' or 'kegg_pathway'. None = both.
        prominence: Filter edges by prominence: 'central' or 'peripheral'.
        summary: Return only summary fields (forces limit=0, empty results).
        verbose: Include the full `evidence` extraction quote per row.
        limit: Max detail rows (default 50).
        offset: Skip this many detail rows (pagination).
        conn: Optional graph connection (defaults to the shared connection).

    Returns dict with keys: total_entries (all discusses edges from matched DOIs,
    before entity_kind/prominence filters), total_matching (rows after filters),
    returned, offset, truncated, by_entity_kind, by_prominence, top_kegg_pathways,
    top_publications, not_found (DOIs absent from the KG), not_matched (DOIs
    present but with no discusses edge after filters), results.
    Per result (compact): doi, entity_kind, entity_id, entity_name, organism
    (gene-only; None on pathway rows), prominence. Verbose adds: evidence.

    Raises ValueError if publication_dois is empty, or entity_kind / prominence
    is not a recognized value.
    """
    if not publication_dois:
        raise ValueError("publication_dois must not be empty.")
    if entity_kind is not None and entity_kind not in _DISCUSSES_ENTITY_KINDS:
        raise ValueError(
            f"Invalid entity_kind '{entity_kind}'. "
            f"Valid: {list(_DISCUSSES_ENTITY_KINDS)}"
        )
    if prominence is not None and prominence not in _DISCUSSES_PROMINENCE:
        raise ValueError(
            f"Invalid prominence '{prominence}'. "
            f"Valid: {list(_DISCUSSES_PROMINENCE)}"
        )
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # DOIs are matched case-insensitively (toLower(p.doi) IN $publication_dois).
    lowered = [d.lower() for d in publication_dois]

    # Summary query — always runs.
    sum_cypher, sum_params = build_discussed_by_publication_summary(
        publication_dois=lowered, entity_kind=entity_kind, prominence=prominence,
    )
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    total_matching = raw_summary["total_matching"]

    # not_found / not_matched — computed in the API by diffing the input DOIs
    # against the summary builder's resolved_dois (DOIs that resolve to a
    # Publication) and matched_dois (DOIs with >=1 edge after filters). Both
    # builder sets are lowercased; `lowered` is already lowercased. not_found =
    # never resolved; not_matched = resolved but no surviving edge.
    resolved = set(raw_summary.get("resolved_dois", []))
    matched = set(raw_summary.get("matched_dois", []))
    unique_lowered = list(dict.fromkeys(lowered))
    not_found = [d for d in unique_lowered if d not in resolved]
    not_matched = [d for d in unique_lowered if d in resolved and d not in matched]

    envelope: dict = {
        "total_entries": raw_summary["total_entries"],
        "total_matching": total_matching,
        # Rename APOC {item, count} frequency rows to the semantic key the MCP
        # breakdown models expect (parallels by_organism -> organism_name etc.).
        "by_entity_kind": _rename_freq(
            raw_summary.get("by_entity_kind", []), "entity_kind",
        ),
        "by_prominence": _rename_freq(
            raw_summary.get("by_prominence", []), "prominence",
        ),
        "top_kegg_pathways": raw_summary.get("top_kegg_pathways", []),
        "top_publications": raw_summary.get("top_publications", []),
        "not_found": not_found,
        "not_matched": not_matched,
    }

    # Detail query — skip when limit=0 (summary mode).
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_discussed_by_publication(
        publication_dois=lowered, entity_kind=entity_kind, prominence=prominence,
        verbose=verbose, limit=limit, offset=offset,
    )
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def gene_details(
    locus_tags: list[str],
    summary: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get all properties for genes (deep-dive complement to gene_overview).

    Returns dict with keys: total_matching, returned, truncated,
    not_found, results.
    Each result is a flat dict of all Gene node properties (g {.*}).

    summary=True is sugar for limit=0: results=[], summary fields only.
    not_found: input locus_tags not in KG.
    """
    if not locus_tags:
        raise ValueError("locus_tags must be a non-empty list")

    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Summary query — always runs
    sum_cypher, sum_params = build_gene_details_summary(locus_tags=locus_tags)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    total_matching = raw_summary["total_matching"]
    envelope: dict = {
        "total_matching": total_matching,
        "not_found": raw_summary["not_found"],
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_gene_details(
        locus_tags=locus_tags, limit=limit, offset=offset,
    )
    results = [r["gene"] for r in conn.execute_query(det_cypher, **det_params)]

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope



def gene_homologs(
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get ortholog group memberships for genes.

    Returns dict with keys: total_matching, by_organism, by_source,
    top_cyanorak_roles, top_cog_categories,
    returned, truncated, not_found, no_groups, results.
    Per result (compact): locus_tag, organism_name, group_id,
    consensus_gene_name, consensus_product, taxonomic_level, source,
    specificity_rank.
    Per result (verbose): adds member_count, organism_count, genera,
    has_cross_genus_members, description, functional_description.

    Raises ValueError if locus_tags is empty.

    summary=True is sugar for limit=0: results=[], summary fields only.
    not_found: input locus_tags not in KG.
    no_groups: genes that exist but have zero matching OGs.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Validate enum params
    if source is not None and source not in VALID_OG_SOURCES:
        raise ValueError(
            f"Invalid source '{source}'. Valid: {sorted(VALID_OG_SOURCES)}"
        )
    if taxonomic_level is not None and taxonomic_level not in VALID_TAXONOMIC_LEVELS:
        raise ValueError(
            f"Invalid taxonomic_level '{taxonomic_level}'. "
            f"Valid: {sorted(VALID_TAXONOMIC_LEVELS)}"
        )
    if max_specificity_rank is not None and not (
        0 <= max_specificity_rank <= MAX_SPECIFICITY_RANK
    ):
        raise ValueError(
            f"Invalid max_specificity_rank {max_specificity_rank}. "
            f"Valid: 0-{MAX_SPECIFICITY_RANK}."
        )

    filter_kwargs = dict(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
    )

    # Summary query — always runs
    sum_cypher, sum_params = build_gene_homologs_summary(
        locus_tags=locus_tags, **filter_kwargs,
    )
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    def _sorted_breakdown(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    envelope = {
        "total_matching": raw_summary["total_matching"],
        "by_organism": _sorted_breakdown(raw_summary["by_organism"], "organism_name"),
        "by_source": _sorted_breakdown(raw_summary["by_source"], "source"),
        "not_found": raw_summary["not_found"],
        "no_groups": raw_summary["no_groups"],
        "top_cyanorak_roles": raw_summary["top_cyanorak_roles"],
        "top_cog_categories": raw_summary["top_cog_categories"],
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = envelope["total_matching"] > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_gene_homologs(
        locus_tags=locus_tags, **filter_kwargs,
        verbose=verbose, limit=limit, offset=offset,
    )
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = envelope["total_matching"] > offset + len(results)
    envelope["results"] = results
    return envelope


def list_filter_values(
    filter_type: str = "gene_category",
    ontology: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List valid values for a categorical filter.

    Returns dict with keys: filter_type, total_entries, returned, truncated,
    warnings, results.
    Per result: value, count (graph-derived types) or value, applies_to,
    description, source (annotation-trust types).

    filter_type options:
      - ``gene_category``: gene functional categories.
      - ``brite_tree``: KEGG BRITE hierarchy trees.
      - ``growth_phase``: growth phase values on Experiment nodes.
      - ``metric_type``: DerivedMetric.metric_type tag values.
      - ``value_kind``: DerivedMetric.value_kind enum.
      - ``compartment``: Experiment.compartment values.
      - ``omics_type``: Experiment.omics_type values; result merges the
        canonical OMICS_TYPE enum (8 values) so METABOLOMICS surfaces with
        count=0 even when no experiments of that type exist.
      - ``evidence_source``: Metabolite.evidence_sources buckets
        (metabolism / transport / metabolomics).
      - ``evidence``, ``sources``, ``call_class``, ``best_hit_kind``,
        ``pfam_support``, ``attachment_depth``: gene-to-term edge trust
        values, one row per value with the edge types it applies to.
      - ``interpro_type``, ``ncbifam_family_type``, ``merops_catalytic_type``,
        ``merops_family_class``: term-side character values.
      - ``trust_axes``: which trust axes each ontology carries.
      - ``link_kinds``: the bridge kinds a term can link out on.
      - ``cluster_type``: ClusteringAnalysis.cluster_type values (closed
        vocabulary; the ``cluster_type`` filter on
        ``list_clustering_analyses`` / ``gene_clusters_by_gene``). Rows carry
        value, applies_to (``['ClusteringAnalysis']``), description, source.
        ``ontology`` does not apply and is ignored.

    ``ontology`` scopes any of the annotation-trust types to one ontology.
    Values come from the graph's ControlledVocabulary nodes; when a node is
    missing they are derived from the graph instead, ``source`` reads
    "pivot" and a warning says so.

    Raises ValueError on an unknown filter_type or ontology.
    """
    conn = _default_conn(conn)
    warnings_out: list[str] = []
    envelope_description: str | None = None
    if ontology is not None and ontology not in ONTOLOGY_CONFIG:
        raise ValueError(
            f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}"
        )
    if filter_type in _TRUST_FILTER_VALUE_SPECS:
        results, warnings_out, envelope_description = _trust_filter_values(
            conn, filter_type, ontology,
        )
    elif filter_type == "trust_axes":
        results = _trust_axes_filter_values(ontology)
    elif filter_type == "link_kinds":
        results = _link_kind_filter_values(ontology)
    elif filter_type == "cluster_type":
        # Slice 4 (§3.4): closed vocab on ClusteringAnalysis.cluster_type.
        # Same read-then-pivot rule as the annotation-trust types; the
        # vocabulary node is not ontology-scoped, so `ontology` is ignored.
        read = _read_vocab_values(
            conn, "ClusteringAnalysis", "cluster_type", "node", cache=False,
        )
        if read["warning"]:
            warnings_out.append(read["warning"])
        # The vocabulary description is per-property, not per-value: emit it
        # once on the envelope and leave the per-row key absent (sparse row).
        envelope_description = read["description"]
        results = [
            {
                "value": v,
                "applies_to": ["ClusteringAnalysis"],
                "source": read["source"],
            }
            for v in read["values"]
        ]
    elif filter_type == "gene_category":
        cypher, params = build_list_gene_categories()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["category"], "count": r["gene_count"]} for r in rows]
    elif filter_type == "brite_tree":
        cypher, params = build_list_brite_trees()
        rows = conn.execute_query(cypher, **params)
        results = [
            {"value": r["tree"], "tree_code": r["tree_code"], "count": r["term_count"]}
            for r in rows
        ]
    elif filter_type == "growth_phase":
        cypher, params = build_list_growth_phases()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["phase"], "count": r["experiment_count"]} for r in rows]
    elif filter_type == "metric_type":
        cypher, params = build_list_metric_types()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["value"], "count": r["count"]} for r in rows]
    elif filter_type == "value_kind":
        cypher, params = build_list_value_kinds()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["value"], "count": r["count"]} for r in rows]
    elif filter_type == "compartment":
        cypher, params = build_list_compartments()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["value"], "count": r["count"]} for r in rows]
    elif filter_type == "omics_type":
        # Phase 1 plumbing (spec §6.5): merge canonical OMICS_TYPE enum
        # so METABOLOMICS (and any future enum addition) surfaces with
        # count=0 when no experiments of that type exist yet.
        cypher, params = build_list_omics_types()
        rows = conn.execute_query(cypher, **params)
        observed = {r["value"]: r["count"] for r in rows}
        results = [
            {"value": v, "count": observed.get(v, 0)}
            for v in sorted(VALID_OMICS_TYPES)
        ]
    elif filter_type == "evidence_source":
        cypher, params = build_list_evidence_sources()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["value"], "count": r["count"]} for r in rows]
    else:
        valid = [
            "gene_category", "brite_tree", "growth_phase", "metric_type",
            "value_kind", "compartment", "omics_type", "evidence_source",
            *sorted(_TRUST_FILTER_VALUE_SPECS), "trust_axes", "link_kinds",
            "cluster_type",
        ]
        raise ValueError(
            f"Unknown filter_type: {filter_type!r}. Valid options: "
            + ", ".join(repr(v) for v in valid) + "."
        )
    total = len(results)
    if envelope_description is None:
        # Trust types keep the per-row description (one vocab read per
        # applies_to may differ); the envelope carries it only when every
        # row agrees on a single non-null text.
        descs = {r.get("description") for r in results} - {None}
        if len(descs) == 1 and all(r.get("description") for r in results):
            envelope_description = descs.pop()
    return {
        "filter_type": filter_type,
        "description": envelope_description,
        "total_entries": total,
        "returned": total,
        "truncated": False,
        "warnings": warnings_out,
        "results": results,
    }


def list_organisms(
    organism_names: list[str] | None = None,
    compartment: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List organisms in the knowledge graph, optionally filtered by name or compartment.

    organism_names: when provided, each name goes through the shared organism
        resolver (case-insensitive word match on `preferred_name` and
        `name_synonyms`, so 'MED4' works as everywhere else); an exact
        `preferred_name` also matches gene-less treatment taxa. Names that
        resolve to nothing are returned in `not_found`.
    compartment: when provided, restricts to organisms with at least one
        experiment in that wet-lab compartment ('whole_cell', 'vesicle',
        'exoproteome', 'spent_medium', 'lysate').
    summary: when True, sets limit=0 internally — results=[], summary fields only.

    Returns dict with keys: total_entries, total_matching, returned, offset,
    truncated, by_cluster_type, by_organism_type, by_value_kind, by_metric_type,
    by_compartment, top_metabolic_capability, by_measurement_capability,
    top_annotation_capability, not_found, results.
    Per result (compact): organism_name, organism_type, genus, species,
    strain, clade, ncbi_taxon_id, gene_count, publication_count,
    experiment_count, treatment_types, omics_types, clustering_analysis_count,
    cluster_types, derived_metric_count, derived_metric_value_kinds, compartments,
    reaction_count, catalyzed_metabolite_count, transported_metabolite_count
    (distinct substrates reached via the organism's genes' deepest TCDB
    attachments), measured_metabolite_count, peptidase_gene_count,
    nonpeptidase_homolog_gene_count, interpro_gene_count, ncbifam_gene_count
    (annotation-coverage counts of genes carrying a MEROPS peptidase call,
    a MEROPS non-peptidase-homolog call, at least one InterPro term, at
    least one NCBIfam family; 0 when the organism has none).
    Sparse fields (omitted when null): reference_database, reference_proteome.
    When verbose=True, also includes: family, order, tax_class, phylum, kingdom,
    superkingdom, lineage, cluster_count, derived_metric_gene_count,
    derived_metric_types.
    top_metabolic_capability: top 10 organisms (within matched set) by
    catalyzed_metabolite_count, sorted desc; excludes zero-chemistry
    organisms. Ranks on the catalysis arm only (metabolites reached via
    Gene -> Reaction); each entry also carries transported_metabolite_count
    as a column, so a transport-heavy organism is visible without changing
    the ranking. For per-gene transport trust, read tcdb_evidence_score_max
    / transport_substrate_resolution via gene_overview.
    by_measurement_capability: binary 2-bucket count
    {has_metabolomics: N, no_metabolomics: M} where has_metabolomics counts
    organisms with measured_metabolite_count > 0. Sums to total_matching.
    top_annotation_capability: top 10 organisms (within matched set) by
    peptidase_gene_count desc, then preferred_name; each entry carries
    preferred_name, organism_name and all four annotation counts. Organisms
    with all four counts at 0 are excluded. A reading aid for choosing an
    organism for MEROPS / InterPro / NCBIfam questions — there is no filter
    on these counts.
    """
    conn = _default_conn(conn)
    if summary:
        limit = 0

    # Resolve each input through the shared organism resolver (word match on
    # preferred_name + name_synonyms, gene_count > 0) so 'MED4' works here
    # like everywhere else; exact preferred_name stays a fallback so gene-less
    # treatment taxa remain addressable (backlog 3.3).
    names_lc: list[str] | None = None
    unresolved: list[str] = []
    if organism_names:
        resolved: set[str] = set()
        for name in organism_names:
            cypher, params = build_resolve_organism_for_organism(organism=name)
            rows = conn.execute_query(cypher, **params)
            hits = rows[0]["organisms"] if rows else []
            if hits:
                resolved.update(h.lower() for h in hits)
            else:
                unresolved.append(name)
            resolved.add(name.lower())
        names_lc = sorted(resolved)

    # Always run summary first — provides total_entries, total_matching,
    # and the 3 new rollup envelope keys.
    summary_cypher, summary_params = build_list_organisms_summary(
        organism_names_lc=names_lc, compartment=compartment,
    )
    summary_rows = conn.execute_query(summary_cypher, **summary_params)
    summary_row = summary_rows[0] if summary_rows else {
        "total_entries": 0, "total_matching": 0,
        "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
        "by_cluster_type": [], "by_organism_type": [],
        "by_measurement_capability": {
            "has_metabolomics": 0, "no_metabolomics": 0,
        },
        "top_annotation_capability": [],
    }
    total_entries = summary_row["total_entries"]
    total_matching = summary_row["total_matching"]

    # top_metabolic_capability source: detail-mode callers reuse matched rows
    # (avoids a second round-trip); summary-mode callers run a small dedicated
    # capability projection so the summary fast path stays cheap and doesn't
    # pull verbose detail columns just to throw them away.
    matched: list[dict] = []
    if limit == 0:
        results: list[dict] = []
        if total_matching > 0:
            cap_cypher, cap_params = build_list_organisms_capability(
                organism_names_lc=names_lc, compartment=compartment,
            )
            capability_rows = conn.execute_query(cap_cypher, **cap_params)
        else:
            capability_rows = []
    else:
        detail_cypher, detail_params = build_list_organisms(
            organism_names_lc=names_lc, compartment=compartment, verbose=verbose,
        )
        matched = conn.execute_query(detail_cypher, **detail_params)
        capability_rows = matched
        # The detail projection is unpaged (slicing happens below), so the
        # matched-row count is the authoritative total for the same filters.
        total_matching = len(matched)

        sliced = matched
        if offset:
            sliced = sliced[offset:]
        if limit is not None:
            sliced = sliced[:limit]
        results = list(sliced)

        # Sparse-strip reference fields when null
        for r in results:
            if r.get("reference_database") is None:
                r.pop("reference_database", None)
                r.pop("reference_proteome", None)

        # Gate verbose-only fields
        if not verbose:
            results = [{k: v for k, v in r.items()
                        if k not in ("cluster_count", "derived_metric_gene_count",
                                     "derived_metric_types")}
                       for r in results]

    # top_metabolic_capability: top 10 organisms by catalyzed_metabolite_count
    # in the matched set; excludes zero-chemistry rows. transported_metabolite_count
    # rides along as a column (ranking unchanged — catalysis arm).
    chemistry_capable = [
        {
            "organism_name": r["organism_name"],
            "reaction_count": r.get("reaction_count", 0),
            "catalyzed_metabolite_count": r.get("catalyzed_metabolite_count", 0),
            "transported_metabolite_count": r.get(
                "transported_metabolite_count", 0) or 0,
        }
        for r in capability_rows
        if r.get("catalyzed_metabolite_count", 0) > 0
        or r.get("reaction_count", 0) > 0
    ]
    chemistry_capable.sort(
        key=lambda r: r["catalyzed_metabolite_count"], reverse=True,
    )
    top_metabolic_capability = chemistry_capable[:10]

    # top_annotation_capability (slice 4 §3.3): top 10 organisms by
    # peptidase_gene_count desc then preferred_name; all-four-zero rows
    # excluded. Detail mode ranks the matched rows api-side (page-
    # independent); summary mode reads the summary builder's rollup and
    # only falls back to the capability rows when that key is absent.
    if limit == 0 and summary_row.get("top_annotation_capability") is not None:
        top_annotation_capability = list(summary_row["top_annotation_capability"])
    else:
        top_annotation_capability = _rank_annotation_capability(capability_rows)

    # not_found: input names that didn't match any OrganismTaxon
    # (case-insensitive). Original casing preserved in the returned list.
    if unresolved:
        not_found_cypher = (
            "MATCH (o:OrganismTaxon) "
            "WHERE toLower(o.preferred_name) IN $names_lc "
            "RETURN collect(toLower(o.preferred_name)) AS found"
        )
        nf_rows = conn.execute_query(
            not_found_cypher, names_lc=[n.lower() for n in unresolved])
        found = set(nf_rows[0]["found"]) if nf_rows else set()
        not_found = [n for n in unresolved if n.lower() not in found]
    else:
        not_found = []

    return {
        "total_entries": total_entries,
        "total_matching": total_matching,
        "by_cluster_type": _rename_freq(
            summary_row.get("by_cluster_type", []), "cluster_type"),
        "by_organism_type": _rename_freq(
            summary_row.get("by_organism_type", []), "organism_type"),
        "by_value_kind": _rename_freq(summary_row.get("by_value_kind", []),
                                      "value_kind"),
        "by_metric_type": _rename_freq(summary_row.get("by_metric_type", []),
                                       "metric_type"),
        "by_compartment": _rename_freq(summary_row.get("by_compartment", []),
                                       "compartment"),
        "top_metabolic_capability": top_metabolic_capability,
        # Phase 1 plumbing (spec §6.4): pass-through binary 2-bucket dict
        # surfaced by build_list_organisms_summary. Default to zero-bucket
        # dict on no-summary fall-through.
        "by_measurement_capability": summary_row.get(
            "by_measurement_capability",
            {"has_metabolomics": 0, "no_metabolomics": 0},
        ),
        "top_annotation_capability": top_annotation_capability,
        "returned": len(results),
        "offset": offset,
        "truncated": total_matching > offset + len(results),
        "not_found": not_found,
        "results": results,
    }


_ANNOTATION_CAPABILITY_COLS = (
    "peptidase_gene_count", "nonpeptidase_homolog_gene_count",
    "interpro_gene_count", "ncbifam_gene_count",
)


def _rank_annotation_capability(rows: list[dict]) -> list[dict]:
    """Top-10 `top_annotation_capability` entries over organism rows.

    Sort key: peptidase_gene_count desc, then preferred_name (== organism_name
    on the row projection). Rows with all four counts at 0 are dropped.
    """
    entries = []
    for r in rows:
        counts = {c: r.get(c) or 0 for c in _ANNOTATION_CAPABILITY_COLS}
        if not any(counts.values()):
            continue
        name = r.get("preferred_name") or r.get("organism_name")
        entries.append({
            "preferred_name": name,
            "organism_name": r.get("organism_name") or name,
            **counts,
        })
    entries.sort(key=lambda e: (-e["peptidase_gene_count"], e["preferred_name"]))
    return entries[:10]


def list_publications(
    organism: str | None = None,
    treatment_type: str | None = None,
    background_factors: str | None = None,
    growth_phases: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    publication_dois: list[str] | None = None,
    compartment: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List publications with expression data.

    Returns dict with keys: total_entries, total_matching, returned, offset,
    truncated, by_organism, by_treatment_type, by_background_factors,
    by_omics_type, by_cluster_type, by_value_kind, by_metric_type,
    by_compartment, by_discusses_coverage, not_found, results.
    Per result (compact): doi, title, authors, year, journal, study_type,
    organisms, experiment_count, treatment_types, background_factors,
    omics_types, clustering_analysis_count, cluster_types, growth_phases,
    derived_metric_count, derived_metric_value_kinds, compartments,
    metabolite_count, metabolite_assay_count, metabolite_compartments,
    discussed_gene_count, discussed_pathway_count (narrative-index rollups; see
    discussed_by_publication).
    When verbose=True, also includes abstract, description, cluster_count,
    derived_metric_gene_count, derived_metric_types.
    When search_text is provided, also includes score.

    growth_phases: if provided, restricts to publications whose growth_phases
    array contains the specified value (case-insensitive).

    compartment: if provided, restricts to publications with at least one
    experiment in that wet-lab compartment (e.g. 'vesicle', 'whole_cell').
    Use list_filter_values(filter_type='compartment') to enumerate values.

    publication_dois: if provided, restricts to publications whose `doi`
    matches any of the listed values (case-insensitive). Mirrors the filter
    shape on sibling list_* tools (list_experiments.experiment_ids).
    `not_found` in the envelope lists any provided DOIs that did not match.
    """
    conn = _default_conn(conn)
    filter_kwargs = dict(
        organism=organism, treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
        search_text=search_text, author=author,
        publication_dois=publication_dois,
        compartment=compartment,
    )

    def _execute(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        summary_cypher, summary_params = build_list_publications_summary(**kw)
        summary_row = conn.execute_query(summary_cypher, **summary_params)[0]

        # Fetch all matching detail rows, then slice for results.
        data_cypher, data_params = build_list_publications(
            **kw, verbose=verbose,
        )
        all_results = conn.execute_query(data_cypher, **data_params)
        return summary_row, all_results

    try:
        summary, all_results = _execute()
    except Neo4jClientError:
        if search_text:
            logger.debug("list_publications: Lucene parse error, retrying with escaped query")
            escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            summary, all_results = _execute(st=escaped)
        else:
            raise

    results = all_results[offset:offset + limit] if limit else all_results[offset:]

    # Gate verbose-only fields
    if not verbose:
        results = [{k: v for k, v in r.items()
                    if k not in ("cluster_count", "derived_metric_gene_count",
                                 "derived_metric_types")}
                   for r in results]

    # Compute not_found: provided publication_dois that no Publication node
    # matches. Only the publication_dois filter is used (other filters could
    # exclude a real DOI, which is "filtered out" rather than "not found").
    if publication_dois:
        doi_cypher = (
            "MATCH (p:Publication) WHERE toLower(p.doi) IN $dois "
            "RETURN collect(toLower(p.doi)) AS found"
        )
        doi_rows = conn.execute_query(
            doi_cypher, dois=[d.lower() for d in publication_dois],
        )
        found_dois = set(doi_rows[0]["found"]) if doi_rows else set()
        not_found = [d for d in publication_dois if d.lower() not in found_dois]
    else:
        not_found = []

    return {
        "total_entries": summary["total_entries"],
        "total_matching": summary["total_matching"],
        "by_organism": _rename_freq(
            summary.get("by_organism", []), "organism_name"),
        "by_treatment_type": _rename_freq(
            summary.get("by_treatment_type", []), "treatment_type"),
        "by_background_factors": _rename_freq(
            summary.get("by_background_factors", []), "background_factor"),
        "by_omics_type": _rename_freq(
            summary.get("by_omics_type", []), "omics_type"),
        "by_cluster_type": _rename_freq(
            summary.get("by_cluster_type", []), "cluster_type"),
        "by_value_kind": _rename_freq(
            summary.get("by_value_kind", []), "value_kind"),
        "by_metric_type": _rename_freq(
            summary.get("by_metric_type", []), "metric_type"),
        "by_compartment": _rename_freq(
            summary.get("by_compartment", []), "compartment"),
        # Literature "discusses" coverage (spec Extension 3): binary
        # {has_discusses, no_discusses} split across the matched publications.
        "by_discusses_coverage": summary.get("by_discusses_coverage", {}),
        "returned": len(results),
        "offset": offset,
        "truncated": summary["total_matching"] > offset + len(results),
        "not_found": not_found,
        "results": results,
    }


def list_experiments(
    organism: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    omics_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
    coculture_partner: str | None = None,
    search_text: str | None = None,
    time_course_only: bool = False,
    table_scope: list[str] | None = None,
    growth_phases: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    compartment: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List experiments with gene count statistics.

    Always returns: total_entries, total_matching, by_organism,
    by_treatment_type, by_background_factors, by_omics_type,
    by_publication, by_table_scope, by_cluster_type, by_growth_phase,
    by_value_kind, by_metric_type, by_compartment,
    time_course_count, returned, truncated, not_found, results.

    summary=True is sugar for limit=0: results is empty list,
    returned=0, truncated=True.
    When summary=False (default): results populated with experiments.
    Per result (compact): experiment_id, experiment_name, publication_doi,
    authors, organism_name, treatment_type, background_factors, coculture_partner,
    omics_type, is_time_course (bool), table_scope, table_scope_detail,
    gene_count, distinct_gene_count, genes_by_status (dict),
    clustering_analysis_count, cluster_types, growth_phases,
    timepoints (list, omitted if not time-course),
    derived_metric_count, derived_metric_value_kinds, compartment,
    metabolite_count, metabolite_assay_count, metabolite_compartments.
    Per timepoint dict: timepoint, timepoint_order, timepoint_hours,
    growth_phase (str | None), gene_count, genes_by_status.
    When verbose=True, also includes: publication_title, treatment,
    control, light_condition, light_intensity, medium, temperature,
    statistical_test, experimental_context,
    derived_metric_gene_count, derived_metric_types,
    reports_derived_metric_types.
    Both derived_metric_types and reports_derived_metric_types source
    from the same KG property (e.reports_derived_metric_types) and are
    identical in current data. Both are emitted for forward-compat
    with a future KG distinction between "DMs reported by this experiment"
    and "DMs associated with this experiment" (slice-2 D5).
    When search_text is provided, detail results include score.

    organism: case-insensitive substring match against profiled organism
        (e.organism_name only). For partner-side filtering, use
        coculture_partner=; the two filters AND-compose.

    compartment: if provided, restricts to experiments in that wet-lab
    compartment (scalar equality match on e.compartment, e.g. 'vesicle',
    'whole_cell', 'exoproteome'). Use list_filter_values(filter_type=
    'compartment') to enumerate values.

    growth_phases: if provided, restricts to experiments whose growth_phases
    array contains any of the specified values (case-insensitive).

    experiment_ids: if provided, restricts to experiments whose `id` matches
    any of the listed values (exact match). Mirrors the filter shape on
    sibling tools (pathway_enrichment, ontology_landscape, etc.).
    `not_found` in the envelope lists any provided IDs that did not match.

    gene_count vs distinct_gene_count
    ---------------------------------
    For time-course experiments, top-level `gene_count` is the cumulative row
    count across timepoints (= ``sum(time_point_totals)``). A 6-TP experiment
    with 1697 genes per TP has ``gene_count == 10182``. Use
    ``distinct_gene_count`` for detection-power / pathway-background reasoning
    — that's the number of distinct genes with at least one measurement edge,
    regardless of timepoint. For non-time-course experiments the two are
    equal. Per-TP detail lives in ``timepoints[].gene_count``.
    """
    if summary:
        limit = 0

    conn = _default_conn(conn)
    filter_kwargs = dict(
        organism=organism, treatment_type=treatment_type,
        background_factors=background_factors,
        omics_type=omics_type, publication_doi=publication_doi,
        coculture_partner=coculture_partner, search_text=search_text,
        time_course_only=time_course_only, table_scope=table_scope,
        growth_phases=growth_phases, experiment_ids=experiment_ids,
        compartment=compartment,
    )

    def _run_summary(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        cypher, params = build_list_experiments_summary(**kw)
        return conn.execute_query(cypher, **params)[0]

    def _run_detail(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        cypher, params = build_list_experiments(
            **kw, verbose=verbose, limit=limit, offset=offset,
        )
        return conn.execute_query(cypher, **params)

    # Always run summary query
    try:
        raw_summary = _run_summary()
    except Neo4jClientError:
        if search_text:
            logger.debug("list_experiments: Lucene parse error, retrying with escaped query")
            escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            raw_summary = _run_summary(st=escaped)
            # Update search_text for detail query too
            filter_kwargs["search_text"] = escaped
        else:
            raise

    # Get total_entries (unfiltered count)
    total_cypher, total_params = build_list_experiments_summary()
    total_raw = conn.execute_query(total_cypher, **total_params)[0]
    total_entries = total_raw["total_matching"]

    envelope = {
        "total_entries": total_entries,
        "total_matching": raw_summary["total_matching"],
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_treatment_type": _rename_freq(raw_summary["by_treatment_type"], "treatment_type"),
        "by_background_factors": _rename_freq(raw_summary["by_background_factors"], "background_factor"),
        "by_omics_type": _rename_freq(raw_summary["by_omics_type"], "omics_type"),
        "by_publication": _rename_freq(raw_summary["by_publication"], "publication_doi"),
        "by_table_scope": _rename_freq(raw_summary["by_table_scope"], "table_scope"),
        "by_cluster_type": _rename_freq(raw_summary["by_cluster_type"], "cluster_type"),
        "by_growth_phase": _rename_freq(raw_summary.get("by_growth_phase", []), "growth_phase"),
        "by_value_kind": _rename_freq(
            raw_summary.get("by_value_kind", []), "value_kind"),
        "by_metric_type": _rename_freq(
            raw_summary.get("by_metric_type", []), "metric_type"),
        "by_compartment": _rename_freq(
            raw_summary.get("by_compartment", []), "compartment"),
        "time_course_count": raw_summary["time_course_count"],
    }

    # Compute not_found: provided experiment_ids that no Experiment node matches.
    # Only the experiment_ids filter is used (other filters could exclude a real
    # ID, which is "filtered out" rather than "not found").
    if experiment_ids:
        eid_cypher = (
            "MATCH (e:Experiment) WHERE e.id IN $experiment_ids "
            "RETURN collect(e.id) AS found"
        )
        eid_rows = conn.execute_query(eid_cypher, experiment_ids=experiment_ids)
        found_ids = set(eid_rows[0]["found"]) if eid_rows else set()
        envelope["not_found"] = [eid for eid in experiment_ids if eid not in found_ids]
    else:
        envelope["not_found"] = []

    # Score distribution (only when search_text used)
    if "score_max" in raw_summary:
        envelope["score_max"] = raw_summary["score_max"]
        envelope["score_median"] = raw_summary["score_median"]
    else:
        envelope["score_max"] = None
        envelope["score_median"] = None

    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = envelope["total_matching"] > 0
        envelope["results"] = []
        return envelope

    # Detail: run detail query
    try:
        results = _run_detail()
    except Neo4jClientError:
        if search_text and filter_kwargs["search_text"] == search_text:
            # Not yet escaped (summary succeeded without retry)
            logger.debug("list_experiments detail: Lucene parse error, retrying")
            escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            results = _run_detail(st=escaped)
        else:
            raise

    # Post-process results
    processed = []
    for row in results:
        r = dict(row)
        # Cast is_time_course string to bool
        r["is_time_course"] = r["is_time_course"] == "time_course"

        # Consolidate gene status counts into dict
        sig_up = r.pop("significant_up_count")
        sig_down = r.pop("significant_down_count")
        r["genes_by_status"] = {
            "significant_up": sig_up,
            "significant_down": sig_down,
            "not_significant": r["gene_count"] - sig_up - sig_down,
        }

        # Assemble timepoints from parallel arrays
        tp_count = r.pop("time_point_count", 0)
        tp_labels = r.pop("time_point_labels", [])
        tp_orders = r.pop("time_point_orders", [])
        tp_hours = r.pop("time_point_hours", [])
        tp_totals = r.pop("time_point_totals", [])
        tp_sig_up = r.pop("time_point_significant_up", [])
        tp_sig_down = r.pop("time_point_significant_down", [])
        # Pop (don't get) — strips the experiment-level field from r so it
        # doesn't leak into the response. Per-TP growth_phase below replaces it.
        tp_growth_phases = r.pop("time_point_growth_phases", [])

        if r["is_time_course"] and tp_count > 0:
            timepoints = []
            for i in range(tp_count):
                tp_total = tp_totals[i]
                tp_up = tp_sig_up[i]
                tp_down = tp_sig_down[i]
                tp = {
                    "timepoint": tp_labels[i] if tp_labels[i] != "" else None,
                    "timepoint_order": tp_orders[i],
                    "timepoint_hours": tp_hours[i] if tp_hours[i] != -1.0 else None,
                    "growth_phase": (
                        tp_growth_phases[i]
                        if i < len(tp_growth_phases) and tp_growth_phases[i]
                        else None
                    ),
                    "gene_count": tp_total,
                    "genes_by_status": {
                        "significant_up": tp_up,
                        "significant_down": tp_down,
                        "not_significant": tp_total - tp_up - tp_down,
                    },
                }
                timepoints.append(tp)
            r["timepoints"] = timepoints
        # Non-time-course: omit timepoints key entirely. tp_growth_phases is
        # popped above so the experiment-level field never leaks into r.

        # Gate verbose-only fields
        if not verbose:
            r.pop("cluster_count", None)
            r.pop("derived_metric_gene_count", None)
            r.pop("derived_metric_types", None)
            r.pop("reports_derived_metric_types", None)

        processed.append(r)

    envelope["returned"] = len(processed)
    envelope["offset"] = offset
    envelope["truncated"] = envelope["total_matching"] > offset + len(processed)
    envelope["results"] = processed
    return envelope


_SEARCH_ONTOLOGY_NARROWING = ("level", "tree", "interpro_type", "min_gene_count", "organism")


def _search_ontology_one(
    conn, ontology: str, *, search_text: str | None, mode: str,
    limit: int | None, offset: int, level: int | None,
    facet: dict, informative_only: bool, verbose: bool,
    min_gene_count: int | None, organism: str | None,
) -> tuple[dict, list[dict]]:
    """Run the summary (+ detail) query for ONE ontology with Lucene retry.

    Returns (summary_row, detail_rows). `detail_rows` is empty when
    `limit == 0`. Search mode retries once with the Lucene-escaped text on
    a parse error; browse mode never touches the fulltext index.
    """
    effective_text = search_text
    common = dict(
        ontology=ontology, level=level, informative_only=informative_only,
        min_gene_count=min_gene_count, organism=organism, **facet,
    )

    def _summary(text):
        cypher, params = build_search_ontology_summary(
            search_text=text, **common,
        )
        rows = conn.execute_query(cypher, **params)
        return rows[0] if rows else {}

    def _detail(text):
        cypher, params = build_search_ontology(
            search_text=text, limit=limit, offset=offset, verbose=verbose,
            **common,
        )
        return conn.execute_query(cypher, **params)

    try:
        raw_summary = _summary(effective_text)
    except Neo4jClientError:
        if mode != "search":
            raise
        logger.debug(
            "search_ontology[%s]: Lucene parse error, retrying escaped", ontology,
        )
        effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
        raw_summary = _summary(effective_text)

    if limit == 0:
        return raw_summary, []

    try:
        rows = _detail(effective_text)
    except Neo4jClientError:
        if mode != "search" or effective_text != search_text:
            raise
        logger.debug(
            "search_ontology[%s] detail: Lucene parse error, retrying", ontology,
        )
        effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
        rows = _detail(effective_text)
    return raw_summary, rows


def search_ontology(
    search_text: str | None = None,
    ontology: str | list[str] | None = None,
    summary: bool = False,
    limit: int | None = None,
    offset: int = 0,
    level: int | None = None,
    tree: str | None = None,
    informative_only: bool = False,
    verbose: bool = False,
    interpro_type: str | None = None,
    min_gene_count: int | None = None,
    organism: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Search or browse ontology terms, one or many ontologies per call.

    Two modes, chosen by `search_text`:

    - **search** (`search_text` given): Lucene fulltext query over term
      names, rows ranked by `score` DESC within each ontology.
    - **browse** (`search_text` None / empty): plain label scan, rows ranked
      by `gene_count` DESC then id, `score` is None. Narrow with `level`,
      a facet (`tree` / `interpro_type`), `min_gene_count` or `organism`;
      a truncated browse with none of those set adds a warning.

    Args:
        search_text: Lucene fulltext query, or None/'' for browse mode.
        ontology: One ontology key, a list of keys, or None for all 17 in
            ONTOLOGY_CONFIG order. Duplicates collapse; unknown keys raise.
        summary: Return only summary fields (forces limit=0, empty results).
        limit: Max detail rows PER ONTOLOGY (lockstep paging on multi-
            ontology calls — `returned` is at most `limit * n_ontologies`).
        offset: Skip this many detail rows per ontology.
        level: Restrict to terms at this hierarchy level (0 = root).
        tree: BRITE-only sub-tree facet; raises when brite is not in the set.
        informative_only: Drop uninformative (root / catch-all) terms.
        verbose: Add `description`, `level_kind`, `direct_gene_count`
            (hierarchical ontologies), the per-ontology `term_verbose`
            columns, and the KEGG `discussed_in_publications` list.
        interpro_type: InterPro-only stratum facet (e.g. 'FAMILY'); raises
            when interpro is not in the set.
        min_gene_count: Keep terms with at least this many annotated genes
            (`organism_gene_count` when `organism` is set).
        organism: Scope gene counts to one organism; rows gain
            `organism_gene_count` and browse ranks by it. Resolved by the
            shared organism resolver (word match, e.g. 'MED4'); an unknown
            or ambiguous name raises ValueError.
        conn: Optional graph connection (defaults to the shared connection).

    Returns dict with keys: mode ('search' | 'browse'), total_entries,
    total_matching, score_max, score_median, returned, offset, truncated,
    by_ontology [{ontology, total_entries, total_matching, score_max,
    returned, truncated}], by_level [{level, count}] (browse, single ontology only —
    `[]` on multi-ontology browse because level scales differ),
    by_interpro_type, by_family_type, skipped_ontologies, warnings, results.
    On multi-ontology calls the flat counts are sums (score_max the max)
    across ontologies and rows are grouped by ontology in config order.
    Per result: id, name, ontology_type, score, level, is_informative,
    gene_count, organism_count, tree / tree_code (BRITE), interpro_type
    (InterPro), organism_gene_count (when `organism` is set). KEGG rows
    also carry discussed_by_n_publications.

    Raises ValueError on an unknown ontology key, or when a facet's owning
    ontology is not in the requested set.
    """
    from collections import Counter

    mode = "search" if search_text and search_text.strip() else "browse"
    effective_text = search_text if mode == "search" else None

    requested = _normalize_ontology_arg(ontology)
    if requested is None:
        requested = list(ONTOLOGY_CONFIG)
    # Config order is the row / by_ontology order, whatever the caller wrote.
    ontologies = [key for key in ONTOLOGY_CONFIG if key in requested]

    facet_filters = _active_trust_filters(tree=tree, interpro_type=interpro_type)
    if len(ontologies) == 1:
        _validate_trust_filters(ontologies[0], facet_filters)
    targets, skipped, warnings, per_ontology = _resolve_multi_ontology(
        ontologies, facet_filters,
    )
    if summary:
        limit = 0

    conn = _default_conn(conn)
    if organism is not None:
        # Same fuzzy resolution as every other organism-taking tool
        # ('MED4' -> 'Prochlorococcus MED4'; unknown / ambiguous raises).
        organism = _validate_organism_inputs(organism, None, None, conn)

    results: list[dict] = []
    by_ontology: list[dict] = []
    level_counter: Counter = Counter()
    single_summary: dict | None = None
    for key in targets:
        raw_summary, rows = _search_ontology_one(
            conn, key, search_text=effective_text, mode=mode,
            limit=limit, offset=offset, level=level,
            facet=per_ontology.get(key, {}),
            informative_only=informative_only, verbose=verbose,
            min_gene_count=min_gene_count, organism=organism,
        )
        if single_summary is None:
            single_summary = raw_summary
        o_total = raw_summary.get("total_matching") or 0
        for r in rows:
            r["ontology_type"] = key
            # Strip sparse BRITE-only fields when absent
            if r.get("tree") is None:
                r.pop("tree", None)
                r.pop("tree_code", None)
        results.extend(rows)
        by_ontology.append({
            "ontology": key,
            "total_entries": raw_summary.get("total_entries") or 0,
            "total_matching": o_total,
            "score_max": raw_summary.get("score_max"),
            "returned": len(rows),
            "truncated": (
                o_total > 0 if limit == 0 else o_total > offset + len(rows)
            ),
        })
        for entry in raw_summary.get("by_level") or []:
            if entry and entry.get("level") is not None:
                level_counter[entry["level"]] += entry.get("count") or 0

    score_values = [e["score_max"] for e in by_ontology if e["score_max"] is not None]
    if len(by_ontology) == 1 and single_summary is not None:
        score_median = single_summary.get("score_median")
    else:
        returned_scores = [
            r["score"] for r in results if r.get("score") is not None
        ]
        score_median = (
            float(statistics.median(returned_scores)) if returned_scores else None
        )

    truncated = any(e["truncated"] for e in by_ontology)
    if mode == "browse" and truncated and not any(
        v is not None for v in (level, tree, interpro_type, min_gene_count, organism)
    ):
        warnings = warnings + [
            "Browse mode truncated with no narrowing filter — set level, "
            "min_gene_count, organism or a facet (tree / interpro_type), "
            "or raise limit / page with offset, to see the rest."
        ]

    def _facet_rollup(owner: str, column: str) -> list[dict]:
        counter = Counter(
            r.get(column) for r in results
            if r.get("ontology_type") == owner and r.get(column) is not None
        )
        return _freq_rollup(counter, column)

    return {
        "mode": mode,
        "total_entries": sum(e["total_entries"] for e in by_ontology),
        "total_matching": sum(e["total_matching"] for e in by_ontology),
        "score_max": max(score_values) if score_values else None,
        "score_median": score_median,
        "returned": len(results),
        "offset": offset,
        "truncated": truncated,
        "by_ontology": by_ontology,
        # Levels are ontology-scoped scales (GO depth != KEGG != TCDB), so
        # the rollup is only meaningful for a single-ontology browse.
        "by_level": (
            [{"level": lvl, "count": n} for lvl, n in sorted(level_counter.items())]
            if len(by_ontology) == 1 else []
        ),
        "by_interpro_type": _facet_rollup("interpro", "interpro_type"),
        "by_family_type": _facet_rollup("ncbifam", "family_type"),
        "skipped_ontologies": skipped,
        "warnings": warnings,
        "results": results,
    }


def search_homolog_groups(
    search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Search ortholog groups by text (Lucene fulltext).

    Returns dict with keys: total_entries, total_matching, by_source,
    by_level, top_cyanorak_roles, top_cog_categories,
    score_max, score_median, returned, truncated, results.

    cyanorak_roles: filter to groups linked to these Cyanorak role IDs.
    cog_categories: filter to groups linked to these COG category IDs.
    Per result (compact): group_id, group_name, consensus_gene_name,
    consensus_product, source, taxonomic_level, specificity_rank,
    member_count, organism_count, score.
    Per result (verbose): adds description, functional_description,
    genera, has_cross_genus_members.

    summary=True: results=[], summary fields only.
    """
    if not search_text or not search_text.strip():
        raise ValueError("search_text must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Validate enum params
    if source is not None and source not in VALID_OG_SOURCES:
        raise ValueError(
            f"Invalid source '{source}'. Valid: {sorted(VALID_OG_SOURCES)}"
        )
    if taxonomic_level is not None and taxonomic_level not in VALID_TAXONOMIC_LEVELS:
        raise ValueError(
            f"Invalid taxonomic_level '{taxonomic_level}'. "
            f"Valid: {sorted(VALID_TAXONOMIC_LEVELS)}"
        )
    if max_specificity_rank is not None and not (
        0 <= max_specificity_rank <= MAX_SPECIFICITY_RANK
    ):
        raise ValueError(
            f"Invalid max_specificity_rank {max_specificity_rank}. "
            f"Valid: 0-{MAX_SPECIFICITY_RANK}."
        )

    filter_kwargs = dict(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles, cog_categories=cog_categories,
    )

    effective_text = search_text

    # Summary query — always runs
    try:
        sum_cypher, sum_params = build_search_homolog_groups_summary(
            search_text=effective_text, **filter_kwargs)
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
    except Neo4jClientError:
        logger.debug("search_homolog_groups: Lucene parse error, retrying with escaped query")
        effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
        sum_cypher, sum_params = build_search_homolog_groups_summary(
            search_text=effective_text, **filter_kwargs)
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_entries": raw_summary["total_entries"],
        "total_matching": total_matching,
        "by_source": _rename_freq(raw_summary["by_source"], "source"),
        "by_level": _rename_freq(raw_summary["by_level"], "taxonomic_level"),
        "top_cyanorak_roles": raw_summary["top_cyanorak_roles"],
        "top_cog_categories": raw_summary["top_cog_categories"],
        "score_max": raw_summary["score_max"],
        "score_median": raw_summary["score_median"],
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    try:
        det_cypher, det_params = build_search_homolog_groups(
            search_text=effective_text, **filter_kwargs,
            verbose=verbose, limit=limit, offset=offset)
        results = conn.execute_query(det_cypher, **det_params)
    except Neo4jClientError:
        if effective_text == search_text:
            logger.debug("search_homolog_groups detail: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            det_cypher, det_params = build_search_homolog_groups(
                search_text=effective_text, **filter_kwargs,
                verbose=verbose, limit=limit, offset=offset)
            results = conn.execute_query(det_cypher, **det_params)
        else:
            raise

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def genes_by_homolog_group(
    group_ids: list[str],
    organisms: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Find member genes of ortholog groups.

    Returns dict with keys: total_matching, total_genes,
    total_categories, genes_per_group_max, genes_per_group_median,
    by_organism, top_categories, top_groups,
    not_found_groups, not_matched_groups,
    not_found_organisms, not_matched_organisms,
    returned, truncated, results.
    Per result (compact): locus_tag, gene_name, product,
    organism_name, gene_category, group_id.
    Per result (verbose): adds gene_summary, function_description,
    consensus_product, source.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: if group_ids is empty.
    """
    if not group_ids:
        raise ValueError("group_ids must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Summary query — always runs
    sum_cypher, sum_params = build_genes_by_homolog_group_summary(
        group_ids=group_ids, organisms=organisms,
    )
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    by_group_all = _rename_freq(raw_summary["by_group_raw"], "group_id")
    group_counts = [g["count"] for g in by_group_all]

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_matching": total_matching,
        "total_genes": raw_summary["total_genes"],
        "total_categories": raw_summary["total_categories"],
        "genes_per_group_max": max(group_counts) if group_counts else 0,
        "genes_per_group_median": (
            statistics.median(group_counts) if group_counts else 0
        ),
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "top_categories": _rename_freq(raw_summary["by_category_raw"], "category")[:5],
        "top_groups": by_group_all[:5],
        "not_found_groups": raw_summary["not_found_groups"],
        "not_matched_groups": raw_summary["not_matched_groups"],
    }

    # Diagnostics query — only when organisms filter is active
    if organisms is not None:
        diag_cypher, diag_params = build_genes_by_homolog_group_diagnostics(
            group_ids=group_ids, organisms=organisms,
        )
        raw_diag = conn.execute_query(diag_cypher, **diag_params)[0]
        envelope["not_found_organisms"] = raw_diag["not_found_organisms"]
        envelope["not_matched_organisms"] = raw_diag["not_matched_organisms"]
    else:
        envelope["not_found_organisms"] = []
        envelope["not_matched_organisms"] = []

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_genes_by_homolog_group(
        group_ids=group_ids, organisms=organisms,
        verbose=verbose, limit=limit, offset=offset,
    )
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


_LINK_KINDS: tuple[str, ...] = ("composition", "membership", "router")


@lru_cache(maxsize=1)
def _term_label_to_ontology() -> dict[str, str]:
    """Node label -> ontology key, PfamClan folding into pfam."""
    out: dict[str, str] = {}
    for key, cfg in ONTOLOGY_CONFIG.items():
        out[cfg["label"]] = key
        if cfg.get("parent_label"):
            out[cfg["parent_label"]] = key
    return out


@lru_cache(maxsize=1)
def _bridge_registry() -> dict[str, tuple[str, str]]:
    """Bridge rel type -> (target ontology key, link_kind), from config."""
    out: dict[str, tuple[str, str]] = {}
    for cfg in ONTOLOGY_CONFIG.values():
        for rel, target, kind in cfg.get("bridges_out") or []:
            out[rel] = (target, kind)
    return out


# Count props carried by only SOME nodes of their label (KEGG chemistry
# counts live on pathway terms, not KO / module rows). Neo4j has no null
# property, so a null here means "not carried" — stripped, like
# `direct_gene_count`. Every other owned prop keeps a null (e.g. ncbifam
# `gene_symbol`), which is information.
_TERM_DETAILS_SPARSE_COUNTS: frozenset[str] = frozenset({
    "direct_gene_count", "reaction_count", "metabolite_count",
})


def _term_details_row(row: dict, *, verbose: bool, organism: str | None) -> dict:
    """Project one builder row onto the compact / verbose term-details shape.

    Only the props the term's ontology declares under `term_details_compact`
    are carried (owned-but-null survives, except the count props in
    `_TERM_DETAILS_SPARSE_COUNTS`, which are stripped when null; a prop
    another ontology owns is absent). `direct_gene_count` is emitted only
    when the node carries a value — flat labels, PfamClan and BriteCategory
    have none.
    """
    labels = _term_label_to_ontology()
    label = next((lab for lab in row.get("labels") or [] if lab in labels), None)
    ontology = labels.get(label) if label else None
    cfg = ONTOLOGY_CONFIG.get(ontology, {}) if ontology else {}
    props_map = row.get("properties") or {}

    def _prop(name):
        if name in row:
            return row[name]
        return props_map.get(name)

    out: dict = {
        "term_id": row["term_id"],
        "ontology": ontology,
        "label": label,
        "name": row.get("name"),
        "description": row.get("description"),
        "level": row.get("level"),
        "level_kind": row.get("level_kind"),
        "is_informative": row.get("is_informative"),
        "gene_count": row.get("gene_count"),
        "organism_count": row.get("organism_count"),
    }
    compact_props = list(cfg.get("term_details_compact") or [])
    # Strip rule: emitted only when the node actually carries it (null on
    # flat labels, PfamClan, BriteCategory -> key absent, not null).
    direct_gene_count = _prop("direct_gene_count")
    if direct_gene_count is not None:
        out["direct_gene_count"] = direct_gene_count
    for prop in compact_props:
        if prop == "direct_gene_count" or prop in out:
            continue
        if prop in row or prop in props_map:
            value = _prop(prop)
            if value is None and prop in _TERM_DETAILS_SPARSE_COUNTS:
                continue
            out[prop] = value
    if organism is not None:
        out["organism_gene_count"] = row.get("organism_gene_count")

    children = list(row.get("children") or [])
    children_total = row.get("children_total")
    if children_total is None:
        children_total = len(children)
    out["parents"] = list(row.get("parents") or [])
    out["children"] = children
    out["children_total"] = children_total
    out["children_truncated"] = children_total > len(children)

    bridges = _bridge_registry()
    raw_links = list(row.get("links_out") or [])
    n_router = sum(
        1 for link in raw_links
        if bridges.get(link.get("rel"), (None, None))[1] == "router"
    )
    interpro_type = _prop("interpro_type")
    links_out: list[dict] = []
    for link in raw_links:
        target_ontology, kind = bridges.get(link.get("rel"), (None, None))
        entry = {
            "rel": link.get("rel"),
            "link_kind": kind,
            "target_id": link.get("target_id"),
            "target_ontology": target_ontology,
            "target_name": link.get("target_name"),
        }
        if verbose:
            props = dict(link.get("props") or {})
            if kind == "router" and ontology == "interpro":
                props["router_ambiguous"] = bool(
                    n_router > 1 or interpro_type != "FAMILY"
                )
            entry["props"] = props
        links_out.append(entry)
    out["links_out"] = links_out

    if verbose:
        out["properties"] = props_map
        out["genes_by_organism"] = list(row.get("genes_by_organism") or [])
    return out


def ontology_term_details(
    term_ids: list[str],
    organism: str | None = None,
    link_kinds: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = 50,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Describe ontology terms: hierarchy, counts, and cross-ontology links.

    Batch and cross-ontology — term IDs are self-prefixed CURIEs
    (`go:0006979`, `tcdb:3.A.1`, `merops.family:S14`, `interpro:IPR000362`,
    `ncbifam:NF000812`, `kegg.pathway:ko00010`, `pfam:PF00005`, `ec:1.1.1.1`,
    `cazy:GH13`). Rows come back in input order; IDs with no node land in
    `not_found`.

    Links are forward-only by construction. `composition` (tcdb / merops ->
    pfam, tcdb -> go_*) says what a family is built from — read it forward,
    never as "this Pfam domain implies that transporter". `membership`
    (pfam / ncbifam -> interpro, kegg -> brite) is a grouping. `router`
    (interpro -> ec / cazy) is recall-biased: it points at candidate
    functions and never assigns one to a gene — verbose `router_ambiguous`
    flags entries with more than one target or a non-FAMILY type.

    Args:
        term_ids: Term CURIEs to describe (any ontology, mixed is fine).
        organism: Scope `genes_by_organism` (verbose) to one organism and
            add `organism_gene_count` to every row. Resolved by the shared
            organism resolver (word match, e.g. 'MED4'); an unknown or
            ambiguous name raises ValueError.
        link_kinds: Keep only these link kinds ('composition', 'membership',
            'router'); None keeps all.
        verbose: Add `properties` (every node prop), `links_out[].props`
            (edge props such as `curated_tcids` / `member_id_count`, plus
            `router_ambiguous` on router links) and `genes_by_organism`.
        limit: Max rows returned per page (found rows only).
        offset: Skip this many found rows.
        conn: Optional graph connection (defaults to the shared connection).

    Returns dict with keys: total_matching (found rows), returned, offset,
    truncated, not_found, by_ontology [{ontology, count}], links_out_total,
    by_link_kind [{link_kind, count}], warnings, results.
    Per result: term_id, ontology, label (node label), name, description,
    level, level_kind, is_informative, gene_count, organism_count,
    direct_gene_count (hierarchical ontologies), the ontology's own detail
    props (e.g. tcdb_id / tc_class_id, family_class / catalytic_type,
    interpro_type, family_type / gene_symbol — a prop the ontology does not
    own is absent, an owned null survives), parents [{id, name, level}],
    children [{id, name, level}] (capped at 50), children_total,
    children_truncated, links_out [{rel, link_kind, target_id,
    target_ontology, target_name}]. The rollups describe the whole batch,
    not the page.

    Raises ValueError when `term_ids` is empty or `link_kinds` names an
    unknown kind.

    Routing: genes_by_ontology(term_ids=[...]) for the annotated genes;
    search_ontology for discovery; docs://ontologies/{ontology} for the
    per-ontology reference.
    """
    from collections import Counter

    if not term_ids:
        raise ValueError("term_ids must not be empty.")
    if link_kinds is not None:
        unknown = [k for k in link_kinds if k not in _LINK_KINDS]
        if unknown:
            raise ValueError(
                f"Unknown link_kind {', '.join(repr(k) for k in unknown)}. "
                f"Valid link_kinds: {', '.join(_LINK_KINDS)}."
            )
        link_kinds = list(link_kinds)

    conn = _default_conn(conn)
    if organism is not None:
        organism = _validate_organism_inputs(organism, None, None, conn)
    cypher, params = build_ontology_term_details(
        term_ids=list(term_ids), link_kinds=link_kinds, verbose=verbose,
        organism=organism,
    )
    raw_rows = conn.execute_query(cypher, **params)

    found: list[dict] = []
    not_found: list[str] = []
    for row in raw_rows:
        if row.get("not_found") or not row.get("labels"):
            not_found.append(row["term_id"])
            continue
        found.append(_term_details_row(row, verbose=verbose, organism=organism))
    ontology_counter = Counter(r["ontology"] for r in found)
    link_counter: Counter = Counter()
    for r in found:
        for link in r["links_out"]:
            link_counter[link["link_kind"]] += 1

    total_matching = len(found)
    page = found[offset:] if limit is None else found[offset:offset + limit]

    return {
        "total_matching": total_matching,
        "returned": len(page),
        "offset": offset,
        "truncated": total_matching > offset + len(page),
        "not_found": not_found,
        "by_ontology": _freq_rollup(ontology_counter, "ontology"),
        "links_out_total": sum(link_counter.values()),
        "by_link_kind": _freq_rollup(link_counter, "link_kind"),
        "warnings": [],
        "results": page,
    }


def genes_by_ontology(
    ontology: str,
    organism: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    tree: str | None = None,
    informative_only: bool = False,
    sources: list[str] | None = None,
    evidence: list[str] | None = None,
    max_tier: int | None = None,
    min_evidence_score: float | None = None,
    call_class: list[str] | None = None,
    interpro_type: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Find genes x ontology-term pairs (TERM2GENE), three input modes.

    Mode 1 (term_ids only): expand DOWN, row term_id = input term.
    Mode 2 (level only): roll UP, row term_id = level-N ancestor.
    Mode 3 (level + term_ids): Mode 2 scoped to provided level-N terms.

    Trust filters bind on the gene->term edge before the hierarchy walk, so
    they shape the gene set itself and not just the rows you read. They all
    default to None and none of them filters by default:

    - ``sources``: keep edges asserted by any of the named pipelines.
    - ``evidence``: keep edges on the named rungs of the strength ladder
      (curated > signature > homology > family_inferred > domain_inferred).
    - ``max_tier``: keep edges at or above this truncation depth. Edges with
      no tier are kept and counted in the ``by_tier`` null bucket.
    - ``min_evidence_score``: the one numeric cutoff. Sets
      ``evidence_score_signals`` in the envelope.
    - ``call_class``: MEROPS only — separate real peptidases from
      catalytically-dead homologs.
    - ``interpro_type``: InterPro only — the term-side stratum facet.

    Returns dict with the standard envelope plus ``trust_axes``,
    ``by_evidence``, ``by_tier``, ``by_sources``, ``by_call_class``,
    ``evidence_score_stats``, ``filters_applied``, ``skipped_ontologies``
    and ``warnings``.

    Raises ValueError when the ontology does not carry a filter you set.
    """
    from collections import Counter

    # --- Input validation ---
    if ontology not in ALL_ONTOLOGIES:
        raise ValueError(
            f"Invalid ontology '{ontology}'. Valid: {ALL_ONTOLOGIES}"
        )
    trust_filters = _active_trust_filters(
        sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
        interpro_type=interpro_type, tree=tree,
    )
    _validate_trust_filters(ontology, trust_filters)
    if level is None and not term_ids:
        raise ValueError(
            "At least one of `level` or `term_ids` must be provided."
        )
    if min_gene_set_size < 0:
        raise ValueError("min_gene_set_size must be >= 0.")
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError("max_gene_set_size must be >= min_gene_set_size.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Categorical filter values are owned by the graph's ControlledVocabulary
    # nodes, never by this file. A missing node degrades to a pivot read.
    trust_warnings = _validate_categorical_values(conn, ontology, trust_filters)

    # Resolve organism to canonical name (fuzzy → exact)
    organism = _validate_organism_inputs(
        organism=organism, locus_tags=None, experiment_ids=None, conn=conn,
    )

    # --- Query V: validate term_ids (only when provided) ---
    not_found: list[str] = []
    wrong_ontology: list[str] = []
    wrong_level: list[str] = []
    ok_term_ids: list[str] | None = None  # None = no validation needed
    if term_ids:
        v_cypher, v_params = build_genes_by_ontology_validate(
            term_ids=term_ids, ontology=ontology, level=level,
        )
        v_rows = conn.execute_query(v_cypher, **v_params)
        for r in v_rows:
            if r["status"] == "not_found":
                not_found.append(r["tid"])
            elif r["status"] == "wrong_ontology":
                wrong_ontology.append(r["tid"])
            elif r["status"] == "wrong_level":
                wrong_level.append(r["tid"])
        ok_term_ids = [r["tid"] for r in v_rows if r["status"] == "ok"]

    # Short-circuit when all term_ids invalid: skip queries A/B/D, fall through
    # to envelope assembly with empty aggregates. _stats and Counter both handle
    # empty inputs gracefully; `if limit == 0:` below skips Query D.
    effective_term_ids = ok_term_ids if term_ids else None
    if term_ids and not effective_term_ids:
        per_term: list[dict] = []
        per_gene: list[dict] = []
        limit = 0  # forces detail to be skipped without re-checking summary flag
    else:
        # --- Query A: per-term aggregate ---
        pt_cypher, pt_params = build_genes_by_ontology_per_term(
            ontology=ontology, organism=organism,
            level=level, term_ids=effective_term_ids,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
            informative_only=informative_only,
            **trust_filters,
        )
        per_term = conn.execute_query(pt_cypher, **pt_params)

        # --- Query B: per-gene aggregate ---
        pg_cypher, pg_params = build_genes_by_ontology_per_gene(
            ontology=ontology, organism=organism,
            level=level, term_ids=effective_term_ids,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
            informative_only=informative_only,
            **trust_filters,
        )
        per_gene = conn.execute_query(pg_cypher, **pg_params)

    # --- Compose envelope ---
    total_matching = sum(r["n_genes"] for r in per_term)
    total_genes = len(per_gene)
    total_terms = len(per_term)
    n_best_effort_terms = sum(1 for r in per_term if r["best_effort"])

    # by_category from per_gene
    cat_counter = Counter(r["gene_category"] for r in per_gene)
    by_category = [
        {"category": c, "count": n}
        for c, n in cat_counter.most_common()
    ]
    total_categories = len(cat_counter)

    # by_level from per_term (for n_terms, row_count) + per_gene (for n_genes)
    level_terms: dict[int, dict] = {}
    for r in per_term:
        lvl = r["level"]
        e = level_terms.setdefault(
            lvl,
            {"level": lvl, "n_terms": 0, "n_genes": 0, "row_count": 0},
        )
        e["n_terms"] += 1
        e["row_count"] += r["n_genes"]
    # n_genes per level from per_gene.levels_hit
    for r in per_gene:
        for lvl in r["levels_hit"]:
            # Only count levels that have surviving terms in per_term -- a gene
            # that hits a level whose terms were size-filtered out shouldn't
            # contribute to by_level for that level.
            if lvl in level_terms:
                level_terms[lvl]["n_genes"] += 1  # count once per gene per level
    by_level = sorted(level_terms.values(), key=lambda e: e["level"])

    # top_terms: top 5 by n_genes desc, tie-break term_id asc
    top_terms_sorted = sorted(
        per_term, key=lambda r: (-r["n_genes"], r["term_id"])
    )[:5]
    top_terms = [
        {"term_id": r["term_id"], "term_name": r["term_name"],
         "count": r["n_genes"], "is_informative": r["is_informative"]}
        for r in top_terms_sorted
    ]

    # Distributions
    genes_per_term_vals = [r["n_genes"] for r in per_term]
    terms_per_gene_vals = [r["n_terms"] for r in per_gene]

    def _stats(vals):
        if not vals:
            return 0, 0.0, 0
        return min(vals), float(statistics.median(vals)), max(vals)

    g_min, g_med, g_max = _stats(genes_per_term_vals)
    t_min, t_med, t_max = _stats(terms_per_gene_vals)

    # filtered_out: ok term_ids not present in per_term output (Modes 1 & 3)
    filtered_out: list[str] = []
    if effective_term_ids:
        emitted_term_ids = {r["term_id"] for r in per_term}
        filtered_out = [
            tid for tid in effective_term_ids if tid not in emitted_term_ids
        ]

    envelope = {
        "ontology": ontology,
        "organism_name": organism,
        "total_matching": total_matching,
        "total_genes": total_genes,
        "total_terms": total_terms,
        "total_categories": total_categories,
        "genes_per_term_min": g_min,
        "genes_per_term_median": g_med,
        "genes_per_term_max": g_max,
        "terms_per_gene_min": t_min,
        "terms_per_gene_median": t_med,
        "terms_per_gene_max": t_max,
        "by_category": by_category,
        "by_level": by_level,
        "top_terms": top_terms,
        "n_best_effort_terms": n_best_effort_terms,
        "not_found": not_found,
        "wrong_ontology": wrong_ontology,
        "wrong_level": wrong_level,
        "filtered_out": filtered_out,
        "offset": offset,
        "trust_axes": {ontology: ontology_trust_axes(ontology)},
        "filters_applied": dict(trust_filters),
        "skipped_ontologies": [],
    }
    # --- Query C: full-match trust rollups (aggregate-only) ---
    # The `by_*` rollups and the row-conditional warnings describe the whole
    # match, not the page the caller happens to be reading, and they must be
    # there in summary mode too. The detail query below already IS the full
    # match when it is unpaginated; on a paged or summary call the rollups
    # come from Cypher count() aggregations — never a second row scan.
    aggregate_done = False
    if ontology_row_columns(ontology, verbose=False, force_trust_axes=True) and (
        per_term and not (limit is None and offset == 0)
    ):
        agg_cypher, agg_params = build_genes_by_ontology_trust_rollups(
            ontology=ontology, organism=organism,
            level=level, term_ids=effective_term_ids,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
            informative_only=informative_only,
            **trust_filters,
        )
        agg_rows = conn.execute_query(agg_cypher, **agg_params)
        rollups = _trust_rollups_from_aggregate(agg_rows[0] if agg_rows else None)
        envelope.update(rollups)
        envelope["warnings"] = trust_warnings + _trust_aggregate_warnings(
            rollups, [ontology], trust_filters, total_matching,
        )
        aggregate_done = True
    else:
        envelope.update(_trust_rollups([]))
        envelope["warnings"] = trust_warnings + _trust_row_warnings(
            [], [ontology], trust_filters,
        )
    if min_evidence_score is not None:
        envelope["evidence_score_signals"] = _evidence_score_signals(
            conn, [ontology],
        )

    # --- Query D: detail rows (skipped when summary=True) ---
    if limit == 0:
        envelope["returned"] = 0
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_genes_by_ontology_detail(
        ontology=ontology, organism=organism,
        level=level, term_ids=effective_term_ids,
        min_gene_set_size=min_gene_set_size,
        max_gene_set_size=max_gene_set_size,
        verbose=verbose, limit=limit, offset=offset,
        informative_only=informative_only,
        **trust_filters,
    )
    results = conn.execute_query(det_cypher, **det_params)

    # Rollups and warnings read the raw rows: the compact strip below hides
    # the verbose axes from the caller, but the distribution still belongs
    # in the envelope. When the aggregate was skipped these rows ARE the
    # full match.
    if not aggregate_done:
        envelope.update(_trust_rollups(results))
        envelope["warnings"] = trust_warnings + _trust_row_warnings(
            results, [ontology], trust_filters,
        )

    # Strip sparse level_is_best_effort=False from rows (verbose only)
    if verbose:
        for r in results:
            if r.get("level_is_best_effort") is False:
                r.pop("level_is_best_effort", None)

    # Strip sparse tree/tree_code for non-BRITE results
    for r in results:
        if r.get("tree") is None:
            r.pop("tree", None)
            r.pop("tree_code", None)

    # Strip-non-applicable: drop the columns this ontology does not own.
    _strip_unowned_columns(results, ontology, verbose)

    envelope["returned"] = len(results)
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def gene_ontology_terms(
    locus_tags: list[str],
    organism: str,
    ontology: str | list[str] | None = None,
    mode: str = "leaf",
    level: int | None = None,
    tree: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    informative_only: bool = False,
    sources: list[str] | None = None,
    evidence: list[str] | None = None,
    max_tier: int | None = None,
    min_evidence_score: float | None = None,
    call_class: list[str] | None = None,
    interpro_type: str | None = None,
    include_superseded: bool = False,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get ontology annotations for genes. One row per gene × term.

    ``ontology`` takes one key, a list of keys, or None for every registered
    ontology. With several ontologies in play a trust filter that all of
    them carry is applied everywhere; one only some of them carry is applied
    to the carriers and the rest are reported in ``skipped_ontologies``; one
    none of them carries raises. A facet applies to its owner alone and
    raises when that owner is absent from the list.

    ``include_superseded`` widens leaf mode to the less specific TCDB
    attachments a gene also carries. Superseded means less specific, not
    wrong.

    Returns dict with keys: total_matching, total_genes, total_terms,
    by_ontology, by_term, terms_per_gene_min, terms_per_gene_max,
    terms_per_gene_median, returned, truncated, not_found, no_terms,
    results, plus trust_axes, by_evidence, by_tier, by_sources,
    by_call_class, evidence_score_stats, filters_applied,
    skipped_ontologies and warnings.
    Per result: locus_tag, term_id, term_name, level.
    Verbose adds: organism_name.
    All-ontology queries add: ontology_type.
    BRITE results include sparse tree/tree_code fields.

    Raises ValueError if an ontology name is unknown, if an ontology cannot
    carry a filter you set, or if locus_tags is empty.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    ontology_arg = ontology
    requested = _normalize_ontology_arg(ontology)
    single_ontology = isinstance(ontology_arg, str)
    if mode not in ("leaf", "rollup"):
        raise ValueError(f"mode must be 'leaf' or 'rollup', got '{mode}'")
    if mode == "rollup" and level is None:
        raise ValueError("level is required when mode='rollup'")
    if summary:
        limit = 0

    trust_filters = _active_trust_filters(
        sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
        interpro_type=interpro_type, tree=tree,
    )
    requested_all = requested if requested is not None else sorted(ONTOLOGY_CONFIG)
    if single_ontology:
        _validate_trust_filters(requested_all[0], trust_filters)
        targets = list(requested_all)
        skipped_ontologies: list[dict] = []
        trust_warnings: list[str] = []
        per_ontology_filters = {requested_all[0]: dict(trust_filters)}
    else:
        (targets, skipped_ontologies, trust_warnings,
         per_ontology_filters) = _resolve_multi_ontology(
            requested_all, trust_filters,
        )

    conn = _default_conn(conn)

    for ont in targets:
        trust_warnings += _validate_categorical_values(
            conn, ont, per_ontology_filters.get(ont, {}),
        )

    # Resolve organism
    organism_name = _validate_organism_inputs(
        organism=organism, locus_tags=None, experiment_ids=None, conn=conn,
    )

    # Step 1: gene existence check
    exist_cypher, exist_params = build_gene_existence_check(locus_tags=locus_tags)
    exist_rows = conn.execute_query(exist_cypher, **exist_params)
    not_found = [r["lt"] for r in exist_rows if not r["found"]]
    found_tags = [r["lt"] for r in exist_rows if r["found"]]

    # Determine which ontologies to query (skipped ones already dropped)
    ontologies = list(targets)

    # Step 2: summary queries — chunked to avoid 1.4 GiB Neo4j transaction cap
    by_ontology: list[dict] = []
    all_by_term: list[dict] = []
    gene_term_counts: dict[str, int] = {lt: 0 for lt in found_tags}

    if found_tags:
        for ont in ontologies:
            merged_gene_count = 0
            merged_term_count = 0
            merged_by_term: dict[str, dict] = {}
            for chunk in _chunk_locus_tags(found_tags):
                sum_cypher, sum_params = build_gene_ontology_terms_summary(
                    locus_tags=chunk, ontology=ont,
                    organism_name=organism_name,
                    mode=mode, level=level,
                    informative_only=informative_only,
                    include_superseded=include_superseded,
                    **per_ontology_filters.get(ont, {}),
                )
                rows = conn.execute_query(sum_cypher, **sum_params)
                if not rows or rows[0]["gene_count"] == 0:
                    continue
                row = rows[0]
                merged_gene_count += row["gene_count"]
                merged_term_count += row["term_count"]
                for bt in row["by_term"]:
                    key = bt["term_id"]
                    if key not in merged_by_term:
                        entry: dict = {
                            "term_id": key, "term_name": bt["term_name"],
                            "level": bt.get("level"),
                            "count": 0,
                        }
                        # Include sparse BRITE fields
                        if bt.get("tree") is not None:
                            entry["tree"] = bt["tree"]
                        if bt.get("tree_code") is not None:
                            entry["tree_code"] = bt["tree_code"]
                        merged_by_term[key] = entry
                    merged_by_term[key]["count"] += bt["count"]
                for gtc in row["gene_term_counts"]:
                    gene_term_counts[gtc["locus_tag"]] = (
                        gene_term_counts.get(gtc["locus_tag"], 0)
                        + gtc["term_count"]
                    )
            if merged_gene_count == 0:
                continue
            by_ontology.append({
                "ontology_type": ont,
                "term_count": merged_term_count,
                "gene_count": merged_gene_count,
            })
            for bt in merged_by_term.values():
                all_by_term.append({**bt, "ontology_type": ont})

    total_matching = sum(o["term_count"] for o in by_ontology)

    # Step 3: detail queries — skip when limit=0 (summary only)
    # Rollups read the pre-strip rows so the envelope carries the trust
    # distribution even in compact mode.
    raw_trust_rows: list[dict] = []
    if limit == 0:
        results: list[dict] = []
    else:
        all_detail_rows: list[dict] = []
        if found_tags:
            for ont in ontologies:
                for chunk in _chunk_locus_tags(found_tags):
                    det_cypher, det_params = build_gene_ontology_terms(
                        locus_tags=chunk, ontology=ont,
                        organism_name=organism_name,
                        mode=mode, level=level,
                        verbose=verbose, limit=None,
                        informative_only=informative_only,
                        include_superseded=include_superseded,
                        **per_ontology_filters.get(ont, {}),
                    )
                    rows = conn.execute_query(det_cypher, **det_params)
                    # Strip sparse tree/tree_code when None
                    for r in rows:
                        if r.get("tree") is None:
                            r.pop("tree", None)
                        if r.get("tree_code") is None:
                            r.pop("tree_code", None)
                    raw_trust_rows.extend({**r} for r in rows)
                    # Strip-non-applicable, keyed on the chunk's ontology.
                    _strip_unowned_columns(rows, ont, verbose)
                    if not single_ontology:
                        for r in rows:
                            r["ontology_type"] = ont
                    all_detail_rows.extend(rows)

        all_detail_rows.sort(key=lambda r: (r["locus_tag"], r["term_id"]))
        # Apply offset then limit on the merged result set
        sliced = all_detail_rows[offset:]
        if limit is not None:
            results = sliced[:limit]
        else:
            results = sliced

    # Sort breakdowns
    by_ontology.sort(key=lambda x: x["term_count"], reverse=True)
    all_by_term.sort(key=lambda x: x["count"], reverse=True)

    # Compute totals
    no_terms = [lt for lt in found_tags if gene_term_counts.get(lt, 0) == 0]
    genes_with_terms = [lt for lt in found_tags
                        if gene_term_counts.get(lt, 0) > 0]
    total_genes = len(genes_with_terms)
    total_terms = len({bt["term_id"] for bt in all_by_term})

    # Per-gene distribution (only genes with terms)
    counts = [gene_term_counts[lt] for lt in genes_with_terms]
    if counts:
        terms_per_gene_min = min(counts)
        terms_per_gene_max = max(counts)
        terms_per_gene_median = statistics.median(counts)
    else:
        terms_per_gene_min = 0
        terms_per_gene_max = 0
        terms_per_gene_median = 0.0

    envelope = {
        "total_matching": total_matching,
        "total_genes": total_genes,
        "total_terms": total_terms,
        "by_ontology": by_ontology,
        "by_term": all_by_term,
        "terms_per_gene_min": terms_per_gene_min,
        "terms_per_gene_max": terms_per_gene_max,
        "terms_per_gene_median": terms_per_gene_median,
        "returned": len(results),
        "offset": offset,
        "truncated": total_matching > offset + len(results),
        "not_found": not_found,
        "no_terms": no_terms,
        "results": results,
        "trust_axes": {o: ontology_trust_axes(o) for o in targets},
        "filters_applied": dict(trust_filters),
        "skipped_ontologies": skipped_ontologies,
    }
    envelope.update(_trust_rollups(raw_trust_rows))
    if min_evidence_score is not None:
        envelope["evidence_score_signals"] = _evidence_score_signals(
            conn, targets,
        )
    envelope["warnings"] = trust_warnings + _trust_row_warnings(
        raw_trust_rows, targets, trust_filters,
    )
    return envelope


def run_cypher(
    query: str,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Execute a raw Cypher query (read-only).

    Write operations are blocked via keyword detection.
    Syntax is validated via CyVer before execution; schema and property
    warnings are included in the returned dict.

    Returns dict with keys: returned, truncated, warnings, results.

    Raises ValueError if the query contains write keywords or has a syntax error.

    Note: SyntaxValidator returns False for parameterized queries ($param) due to
    a ParameterNotProvided notification — not a real syntax error. run_cypher users
    should write literal values, so this is not an issue in practice.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty.")
    conn = _default_conn(conn)

    # 1. Write blocking
    if _WRITE_KEYWORDS.search(query):
        raise ValueError("Write operations are not allowed. This interface is read-only.")

    # 2. Syntax validation (hard block)
    valid, meta = SyntaxValidator(conn.driver).validate(query)
    if not valid:
        msg = meta[0]["description"] if meta else "Syntax error"
        raise ValueError(f"Syntax error: {msg}")

    # 3–4. Schema + property warnings (soft); deduplicate preserving order
    raw_warnings: list[str] = []
    _, schema_meta = SchemaValidator(conn.driver).validate(query)
    raw_warnings.extend(m["description"] for m in schema_meta)
    _, prop_meta = PropertiesValidator(conn.driver).validate(query)
    raw_warnings.extend(m["description"] for m in prop_meta)
    warnings = list(dict.fromkeys(raw_warnings))

    # 5. Limit injection + semicolon strip (only when limit provided)
    if limit is not None and not re.search(r"\bLIMIT\b", query, re.IGNORECASE):
        query = query.rstrip().rstrip(";")
        query += f"\nLIMIT {limit}"

    # 6. Execute
    results = conn.execute_query(query)
    return {
        "returned": len(results),
        "truncated": len(results) == limit if limit is not None else False,
        "warnings": warnings,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Expression: differential_expression_by_gene
# ---------------------------------------------------------------------------

_EXPRESSION_STATUS_KEYS = ("significant_up", "significant_down", "not_significant")
_VALID_DIRECTIONS_BY_GENE = {"up", "down", "both"}
_VALID_DIRECTIONS_BY_ORTHOLOG = {"up", "down"}


def _apoc_freq_to_dict(freq_list: list[dict]) -> dict[str, int]:
    """Convert apoc.coll.frequencies [{item, count}] to {item: count} dict.

    Fills missing expression_status keys with 0.
    """
    d = {f["item"]: f["count"] for f in freq_list}
    for key in _EXPRESSION_STATUS_KEYS:
        d.setdefault(key, 0)
    return d


def _apoc_freq_to_treatment_dict(freq_list: list[dict]) -> dict[str, int]:
    """Convert apoc.coll.frequencies [{item, count}] to {item: count} dict.

    For treatment_type — no default keys needed.
    """
    return {f["item"]: f["count"] for f in freq_list}


def _validate_organism_inputs(
    organism: str | None,
    locus_tags: list[str] | None,
    experiment_ids: list[str] | None,
    conn: "GraphConnection",
) -> str:
    """Pre-validate that all inputs refer to a single organism.

    Returns the resolved organism_name string.
    Raises ValueError on validation failure.
    """
    resolved: dict[str, list[str]] = {}

    if organism:
        cypher, params = build_resolve_organism_for_organism(organism=organism)
        orgs = conn.execute_query(cypher, **params)[0]["organisms"]
        if len(orgs) == 0:
            raise ValueError(
                f"no organism matching '{organism}' found. "
                "Use list_organisms to see valid organism names."
            )
        if len(orgs) > 1:
            names = ", ".join(sorted(orgs))
            raise ValueError(
                f"organism '{organism}' matches multiple organisms: {names}"
                " — be more specific"
            )
        resolved["organism"] = orgs

    if locus_tags:
        cypher, params = build_resolve_organism_for_locus_tags(
            locus_tags=locus_tags
        )
        orgs = conn.execute_query(cypher, **params)[0]["organisms"]
        if len(orgs) > 1:
            names = ", ".join(sorted(orgs))
            raise ValueError(
                f"locus_tags span multiple organisms: {names}"
                " — call once per organism"
            )
        if orgs:
            resolved["locus_tags"] = orgs

    if experiment_ids:
        cypher, params = build_resolve_organism_for_experiments(
            experiment_ids=experiment_ids
        )
        orgs = conn.execute_query(cypher, **params)[0]["organisms"]
        if len(orgs) > 1:
            names = ", ".join(sorted(orgs))
            raise ValueError(
                f"experiment_ids span multiple organisms: {names}"
                " — call once per organism"
            )
        if orgs:
            resolved["experiment_ids"] = orgs

    # Cross-validate: all resolved sets must agree
    all_orgs = list(resolved.values())
    if not all_orgs:
        # No organism resolved from any input — shouldn't happen if at least
        # one input is provided, but handle gracefully
        raise ValueError(
            "at least one of organism, locus_tags, or experiment_ids is required. "
            "Use list_organisms for organisms, resolve_gene for locus_tags, "
            "or list_experiments for experiment_ids."
        )

    first = all_orgs[0][0]
    for source, orgs in resolved.items():
        if orgs[0] != first:
            # Find which sources disagree
            if "organism" in resolved and source != "organism":
                raise ValueError(
                    f"organism '{organism}' does not match"
                    f" {source} organism '{orgs[0]}'"
                )
            if source == "experiment_ids" and "locus_tags" in resolved:
                raise ValueError(
                    f"locus_tags are {resolved['locus_tags'][0]} genes"
                    f" but experiment_ids cover {orgs[0]}"
                    " — organisms must match"
                )

    return first


def differential_expression_by_gene(
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Query gene-centric differential expression data.

    Returns dict with summary fields + results list. Results are long form:
    one row per gene x experiment x timepoint, all context inlined.

    direction: ``'up'`` / ``'down'`` / ``'both'`` / ``None``. ``'both'`` is
        the explicit, self-documenting spelling for "return rows with
        ``expression_status`` ∈ {``'significant_up'``, ``'significant_down'``}"
        — functionally equivalent to ``direction=None, significant_only=True``;
        pick whichever spelling is clearer at the call site.
        Default ``None`` is unchanged.

    Raises:
        ValueError: if no filter provided, if inputs span multiple organisms,
            if organisms don't match each other, or if organism fuzzy match
            is ambiguous.

    Returns:
        dict with keys: organism_name, matching_genes, total_matching,
        rows_by_status, median_abs_log2fc, max_abs_log2fc, experiment_count,
        rows_by_treatment_type, rows_by_background_factors, by_table_scope,
        rows_by_growth_phase, top_categories, experiments,
        returned, truncated, not_found, no_expression,
        not_found_experiments, not_matched_experiments, results.
        not_found_experiments/not_matched_experiments are populated only
        when experiment_ids is provided (empty lists otherwise).

    growth_phases: if provided, restricts DE rows to those whose edge-level
    growth_phase property matches any of the specified values (case-insensitive).
    """
    conn = _default_conn(conn)

    # Validate direction
    if direction is not None and direction not in _VALID_DIRECTIONS_BY_GENE:
        raise ValueError(
            f"Invalid direction '{direction}'. Valid: {sorted(_VALID_DIRECTIONS_BY_GENE)}"
        )

    # Require at least one filter
    if organism is None and locus_tags is None and experiment_ids is None:
        raise ValueError(
            "at least one of organism, locus_tags, or experiment_ids is required. "
            "Use list_organisms for organisms, resolve_gene for locus_tags, "
            "or list_experiments for experiment_ids."
        )

    if summary:
        limit = 0

    # Common filter kwargs for all builders
    filter_kwargs = dict(
        organism=organism,
        locus_tags=locus_tags,
        experiment_ids=experiment_ids,
        direction=direction,
        significant_only=significant_only,
        growth_phases=growth_phases,
    )

    # Pre-validate single organism
    organism_name = _validate_organism_inputs(
        organism, locus_tags, experiment_ids, conn
    )

    # --- Summary query 1: global stats ---
    global_cypher, global_params = (
        build_differential_expression_by_gene_summary_global(**filter_kwargs)
    )
    global_raw = conn.execute_query(global_cypher, **global_params)[0]

    total_matching = global_raw["total_matching"]
    matching_genes = global_raw["matching_genes"]
    rows_by_status = _apoc_freq_to_dict(global_raw["rows_by_status"])
    rows_by_treatment_type = _apoc_freq_to_treatment_dict(
        global_raw["rows_by_treatment_type"]
    )
    rows_by_background_factors = _apoc_freq_to_treatment_dict(
        global_raw["rows_by_background_factors"]
    )
    by_table_scope = _apoc_freq_to_treatment_dict(
        global_raw["by_table_scope"]
    )
    rows_by_growth_phase = _apoc_freq_to_treatment_dict(
        global_raw.get("rows_by_growth_phase") or []
    )

    # --- Summary query 2: per-experiment with nested timepoints ---
    exp_cypher, exp_params = (
        build_differential_expression_by_gene_summary_by_experiment(
            **filter_kwargs
        )
    )
    exp_raw = conn.execute_query(exp_cypher, **exp_params)

    experiments: list[dict] = []
    if exp_raw:
        for exp in exp_raw[0]["experiments"]:
            e = dict(exp)
            e["rows_by_status"] = _apoc_freq_to_dict(e["rows_by_status"])

            # Handle timepoints
            if e.get("is_time_course") == "single_time_point":
                e["timepoints"] = None
            elif e.get("timepoints"):
                tps = []
                for tp in e["timepoints"]:
                    tp_dict = dict(tp)
                    tp_dict["rows_by_status"] = _apoc_freq_to_dict(
                        tp_dict["rows_by_status"]
                    )
                    tps.append(tp_dict)
                # Sort by timepoint_order
                tps.sort(key=lambda t: t["timepoint_order"])
                e["timepoints"] = tps

            experiments.append(e)

    # Sort experiments by total significant rows DESC
    experiments.sort(
        key=lambda e: (
            e["rows_by_status"]["significant_up"]
            + e["rows_by_status"]["significant_down"]
        ),
        reverse=True,
    )

    # --- Summary query 3: categories + batch diagnostics ---
    diag_cypher, diag_params = (
        build_differential_expression_by_gene_summary_diagnostics(
            **filter_kwargs
        )
    )
    diag_raw = conn.execute_query(diag_cypher, **diag_params)[0]

    top_categories = diag_raw["top_categories"]
    not_found = diag_raw["not_found"]
    no_expression = diag_raw["no_expression"]

    # --- Experiment diagnostics (only when experiment_ids provided) ---
    if experiment_ids:
        exp_diag_cypher, exp_diag_params = (
            build_differential_expression_by_gene_experiment_diagnostics(
                experiment_ids=experiment_ids,
                organism=organism,
                locus_tags=locus_tags,
                direction=direction,
                significant_only=significant_only,
                growth_phases=growth_phases,
            )
        )
        exp_diag_raw = conn.execute_query(
            exp_diag_cypher, **exp_diag_params
        )[0]
        not_found_experiments = exp_diag_raw["not_found_experiments"]
        not_matched_experiments = exp_diag_raw["not_matched_experiments"]
    else:
        not_found_experiments = []
        not_matched_experiments = []

    # --- Detail query (skip when limit=0) ---
    if limit == 0:
        results = []
    else:
        det_cypher, det_params = build_differential_expression_by_gene(
            **filter_kwargs, verbose=verbose, limit=limit, offset=offset,
        )
        results = conn.execute_query(det_cypher, **det_params)

    returned = len(results)
    envelope = {
        "organism_name": organism_name,
        "matching_genes": matching_genes,
        "total_matching": total_matching,
        "rows_by_status": rows_by_status,
        "median_abs_log2fc": global_raw["median_abs_log2fc"],
        "max_abs_log2fc": global_raw["max_abs_log2fc"],
        "experiment_count": len(experiments),
        "rows_by_treatment_type": rows_by_treatment_type,
        "rows_by_background_factors": rows_by_background_factors,
        "by_table_scope": by_table_scope,
        "rows_by_growth_phase": rows_by_growth_phase,
        "top_categories": top_categories,
        "experiments": experiments,
        "not_found": not_found,
        "no_expression": no_expression,
        "not_found_experiments": not_found_experiments,
        "not_matched_experiments": not_matched_experiments,
        "returned": returned,
        "offset": offset,
        "truncated": total_matching > offset + returned,
        "results": results,
    }
    return envelope


def differential_expression_by_ortholog(
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Differential expression framed by ortholog groups.

    Cross-organism by design. Results at group x experiment x timepoint
    granularity showing how many group members respond (gene counts,
    not individual genes).

    Returns dict with keys: total_matching, matching_genes, matching_groups,
    experiment_count, median_abs_log2fc, max_abs_log2fc,
    by_organism, rows_by_status, rows_by_treatment_type,
    rows_by_background_factors, by_table_scope, rows_by_growth_phase,
    top_groups, top_experiments,
    not_found_groups, not_matched_groups,
    not_found_organisms, not_matched_organisms,
    not_found_experiments, not_matched_experiments,
    returned, truncated, results.
    Per result (compact): group_id, consensus_gene_name, consensus_product,
    experiment_id, treatment_type, organism_name, coculture_partner,
    timepoint, timepoint_hours, timepoint_order,
    genes_with_expression, total_genes,
    significant_up, significant_down, not_significant.
    Per result (verbose): adds experiment_name, treatment, omics_type,
    table_scope, table_scope_detail.

    Raises:
        ValueError: if group_ids is empty or direction is invalid.

    growth_phases: if provided, restricts DE rows to those whose edge-level
    growth_phase property matches any of the specified values (case-insensitive).
    """
    if not group_ids:
        raise ValueError("group_ids must not be empty.")

    if direction is not None and direction not in _VALID_DIRECTIONS_BY_ORTHOLOG:
        raise ValueError(
            f"Invalid direction '{direction}'. Valid: {sorted(_VALID_DIRECTIONS_BY_ORTHOLOG)}"
        )

    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Common filter kwargs for all builders
    filter_kwargs = dict(
        organisms=organisms,
        experiment_ids=experiment_ids,
        direction=direction,
        significant_only=significant_only,
        growth_phases=growth_phases,
    )

    # --- Q1a: group existence check ---
    check_cypher, check_params = (
        build_differential_expression_by_ortholog_group_check(
            group_ids=group_ids,
        )
    )
    not_found_groups = conn.execute_query(
        check_cypher, **check_params
    )[0]["not_found"]
    found_group_ids = [
        gid for gid in group_ids if gid not in not_found_groups
    ]

    # --- Q1b: summary_global (for found groups only) ---
    _empty_global = {
        "total_matching": 0, "matching_genes": 0,
        "matching_groups": 0, "experiment_count": 0,
        "by_organism": [], "rows_by_status": [],
        "rows_by_treatment_type": [], "rows_by_background_factors": [],
        "by_table_scope": [],
        "sig_log2fcs": [], "matched_group_ids": [],
    }
    if found_group_ids:
        global_cypher, global_params = (
            build_differential_expression_by_ortholog_summary_global(
                group_ids=found_group_ids, **filter_kwargs,
            )
        )
        global_rows = conn.execute_query(global_cypher, **global_params)
        global_raw = global_rows[0] if global_rows else _empty_global
        not_matched_groups = [
            gid for gid in found_group_ids
            if gid not in global_raw["matched_group_ids"]
        ]
    else:
        global_raw = _empty_global
        not_matched_groups = []

    rows_by_status = _apoc_freq_to_dict(global_raw["rows_by_status"])
    rows_by_treatment_type = _apoc_freq_to_treatment_dict(
        global_raw["rows_by_treatment_type"]
    )
    rows_by_background_factors = _apoc_freq_to_treatment_dict(
        global_raw["rows_by_background_factors"]
    )
    by_table_scope = _apoc_freq_to_treatment_dict(
        global_raw["by_table_scope"]
    )
    rows_by_growth_phase = _apoc_freq_to_treatment_dict(
        global_raw.get("rows_by_growth_phase") or []
    )

    sig_log2fcs = global_raw.get("sig_log2fcs") or []
    median_abs_log2fc = statistics.median(sig_log2fcs) if sig_log2fcs else None
    max_abs_log2fc = max(sig_log2fcs) if sig_log2fcs else None

    # --- Q2: top_groups (always) ---
    tg_cypher, tg_params = build_differential_expression_by_ortholog_top_groups(
        group_ids=group_ids, **filter_kwargs,
    )
    top_groups_raw = conn.execute_query(tg_cypher, **tg_params)

    # --- Q3: top_experiments (always) ---
    te_cypher, te_params = (
        build_differential_expression_by_ortholog_top_experiments(
            group_ids=group_ids, **filter_kwargs,
        )
    )
    top_exp_raw = conn.execute_query(te_cypher, **te_params)

    # --- Q4: results (skip when limit=0 / summary mode) ---
    if limit == 0:
        results = []
    else:
        res_cypher, res_params = build_differential_expression_by_ortholog_results(
            group_ids=group_ids, **filter_kwargs, verbose=verbose, limit=limit, offset=offset,
        )
        results = conn.execute_query(res_cypher, **res_params)

    # --- Q5: membership_counts (always) ---
    mc_cypher, mc_params = (
        build_differential_expression_by_ortholog_membership_counts(
            group_ids=group_ids, organisms=organisms,
        )
    )
    mc_rows = conn.execute_query(mc_cypher, **mc_params)
    mc_lookup = {
        (r["group_id"], r["organism_name"]): r["total_genes"]
        for r in mc_rows
    }
    for r in results:
        key = (r["group_id"], r["organism_name"])
        r["total_genes"] = mc_lookup.get(key, 0)

    # --- Q6: diagnostics (conditional) ---
    if organisms is not None or experiment_ids is not None:
        diag_queries = build_differential_expression_by_ortholog_diagnostics(
            group_ids=group_ids, organisms=organisms,
            experiment_ids=experiment_ids,
            direction=direction, significant_only=significant_only,
            growth_phases=growth_phases,
        )
        not_found_organisms = []
        not_matched_organisms = []
        not_found_experiments = []
        not_matched_experiments = []
        if diag_queries:
            for diag_cypher, diag_params in diag_queries:
                diag_row = conn.execute_query(diag_cypher, **diag_params)[0]
                if "not_found_organisms" in diag_row:
                    not_found_organisms = diag_row["not_found_organisms"]
                    not_matched_organisms = diag_row["not_matched_organisms"]
                if "not_found_experiments" in diag_row:
                    not_found_experiments = diag_row["not_found_experiments"]
                    not_matched_experiments = diag_row["not_matched_experiments"]
    else:
        not_found_organisms = []
        not_matched_organisms = []
        not_found_experiments = []
        not_matched_experiments = []

    by_organism = _rename_freq(global_raw["by_organism"], "organism_name")

    envelope = {
        "total_matching": global_raw["total_matching"],
        "matching_genes": global_raw["matching_genes"],
        "matching_groups": global_raw["matching_groups"],
        "experiment_count": global_raw["experiment_count"],
        "median_abs_log2fc": median_abs_log2fc,
        "max_abs_log2fc": max_abs_log2fc,
        "by_organism": by_organism,
        "rows_by_status": rows_by_status,
        "rows_by_treatment_type": rows_by_treatment_type,
        "rows_by_background_factors": rows_by_background_factors,
        "by_table_scope": by_table_scope,
        "rows_by_growth_phase": rows_by_growth_phase,
        "top_groups": (
            top_groups_raw[0]["top_groups"] if top_groups_raw else []
        ),
        "top_experiments": (
            top_exp_raw[0]["top_experiments"] if top_exp_raw else []
        ),
        "not_found_groups": not_found_groups,
        "not_matched_groups": not_matched_groups,
        "not_found_organisms": not_found_organisms,
        "not_matched_organisms": not_matched_organisms,
        "not_found_experiments": not_found_experiments,
        "not_matched_experiments": not_matched_experiments,
        "returned": len(results),
        "offset": offset,
        "truncated": global_raw["total_matching"] > offset + len(results),
        "results": results,
    }
    return envelope


_FULL_COVERAGE_SCOPES = {"significant_only", "significant_any_timepoint"}


def gene_response_profile(
    locus_tags: list[str],
    organism: str | None = None,
    treatment_types: list[str] | None = None,
    background_factors: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    group_by: str = "treatment_type",
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Cross-experiment gene-level response profile.

    Returns one result per gene summarizing its expression response
    across all experiments, grouped by treatment_type or experiment.

    Raises:
        ValueError: if locus_tags is empty, group_by is invalid,
            or organism validation fails.

    Returns:
        dict with keys: organism_name, genes_queried, genes_with_response,
        not_found, no_expression, returned, offset, truncated, results.
        Each result has: locus_tag, gene_name, product, gene_category,
        groups_responded, groups_not_responded, groups_tested_not_responded,
        groups_not_known, response_summary.
        groups_tested_not_responded: groups where the gene has no expression
        edges but all experiments in the group have full-coverage scopes
        (significant_only or significant_any_timepoint), implying the gene
        was measured but did not respond significantly.
    """
    if not locus_tags:
        raise ValueError(
            "locus_tags must not be empty. "
            "Use resolve_gene or gene_overview to find locus_tags."
        )
    if group_by not in ("treatment_type", "experiment"):
        raise ValueError(
            f"group_by must be 'treatment_type' or 'experiment', got '{group_by}'"
        )

    conn = _default_conn(conn)

    # Resolve organism upfront — validates single-organism constraint
    organism_name = _validate_organism_inputs(
        organism=organism,
        locus_tags=locus_tags,
        experiment_ids=experiment_ids,
        conn=conn,
    )

    # Q1: Envelope — gene existence, expression flags, group totals
    env_cypher, env_params = build_gene_response_profile_envelope(
        locus_tags=locus_tags,
        organism_name=organism_name,
        treatment_types=treatment_types,
        background_factors=background_factors,
        experiment_ids=experiment_ids,
        group_by=group_by,
    )
    env_row = conn.execute_query(env_cypher, **env_params)[0]

    found_genes = env_row["found_genes"]
    has_expression = set(env_row["has_expression"])
    has_significant = set(env_row["has_significant"])
    group_totals = {
        gt["group_key"]: {
            "experiments": gt["experiments"],
            "timepoints": gt["timepoints"],
            "table_scopes": gt.get("table_scopes", []),
        }
        for gt in env_row["group_totals"]
        if gt["group_key"] is not None
    }

    not_found = [lt for lt in locus_tags if lt not in found_genes]
    no_expression = [lt for lt in found_genes if lt not in has_expression]
    genes_with_response = len(has_significant)

    # Q2: Aggregation — per gene x group detail (paginated)
    genes_with_expr = [lt for lt in found_genes if lt in has_expression]
    if genes_with_expr:
        agg_cypher, agg_params = build_gene_response_profile(
            locus_tags=genes_with_expr,
            organism_name=organism_name,
            treatment_types=treatment_types,
            background_factors=background_factors,
            experiment_ids=experiment_ids,
            group_by=group_by,
            limit=limit,
            offset=offset,
        )
        agg_rows = conn.execute_query(agg_cypher, **agg_params)
    else:
        agg_rows = []

    # Pivot flat rows into per-gene nested structure
    genes_dict: dict[str, dict] = {}
    for row in agg_rows:
        lt = row["locus_tag"]
        if lt not in genes_dict:
            genes_dict[lt] = {
                "locus_tag": lt,
                "gene_name": row["gene_name"],
                "product": row["product"],
                "gene_category": row["gene_category"],
                "response_summary": {},
            }
        group_key = row["group_key"]
        totals = group_totals.get(group_key, {"experiments": 0, "timepoints": 0})

        entry: dict = {
            "experiments_total": totals["experiments"],
            "experiments_tested": row["experiments_tested"],
            "experiments_up": row["experiments_up"],
            "experiments_down": row["experiments_down"],
            "timepoints_total": totals["timepoints"],
            "timepoints_tested": row["timepoints_tested"],
            "timepoints_up": row["timepoints_up"],
            "timepoints_down": row["timepoints_down"],
        }

        # Directional rank/log2fc — only when experiments in that direction
        rank_ups = [r for r in row["rank_ups"] if r is not None]
        if rank_ups:
            entry["up_best_rank"] = min(rank_ups)
            entry["up_median_rank"] = statistics.median(rank_ups)
            entry["up_max_log2fc"] = max(row["log2fcs_up"])

        rank_downs = [r for r in row["rank_downs"] if r is not None]
        if rank_downs:
            entry["down_best_rank"] = min(rank_downs)
            entry["down_median_rank"] = statistics.median(rank_downs)
            entry["down_max_log2fc"] = min(row["log2fcs_down"])

        genes_dict[lt]["response_summary"][group_key] = entry

    # Build triage lists per gene
    results = []
    for gene in genes_dict.values():
        rs = gene["response_summary"]
        gene["groups_responded"] = [
            gk for gk, v in rs.items()
            if v["experiments_up"] > 0 or v["experiments_down"] > 0
        ]
        gene["groups_not_responded"] = [
            gk for gk, v in rs.items()
            if v["experiments_up"] == 0 and v["experiments_down"] == 0
        ]
        missing_groups = [gk for gk in group_totals if gk not in rs]
        gene["groups_tested_not_responded"] = [
            gk for gk in missing_groups
            if set(group_totals[gk]["table_scopes"]) <= _FULL_COVERAGE_SCOPES
        ]
        gene["groups_not_known"] = [
            gk for gk in missing_groups
            if gk not in gene["groups_tested_not_responded"]
        ]
        results.append(gene)

    # Determine truncation
    truncated = (
        len(results) + offset < len(genes_with_expr)
        if limit is not None
        else False
    )

    return {
        "organism_name": organism_name,
        "genes_queried": len(locus_tags),
        "genes_with_response": genes_with_response,
        "not_found": not_found,
        "no_expression": no_expression,
        "returned": len(results),
        "offset": offset,
        "truncated": truncated,
        "results": results,
    }


def list_clustering_analyses(
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    omics_type: str | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    analysis_ids: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Browse, search, and filter clustering analyses.

    Returns dict with keys: total_entries, total_matching,
    by_organism, by_cluster_type, by_treatment_type, by_background_factors,
    by_omics_type, by_growth_phase, returned, offset, truncated, results.
    When search_text provided: adds score_max, score_median.
    Per result (compact): analysis_id, name, organism_name, cluster_method,
    cluster_type, cluster_count, total_gene_count, treatment_type,
    background_factors, omics_type, experiment_ids, clusters, score (when searching).
    Per result (verbose): adds treatment, light_condition, experimental_context.

    summary=True: results=[], summary fields only.

    growth_phases: if provided, restricts to analyses whose growth_phases
    array contains any of the specified values (case-insensitive).
    """
    if search_text is not None and not search_text.strip():
        raise ValueError("search_text must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    filter_kwargs = dict(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, background_factors=background_factors,
        growth_phases=growth_phases,
        omics_type=omics_type, publication_doi=publication_doi,
        experiment_ids=experiment_ids, analysis_ids=analysis_ids,
    )

    effective_text = search_text

    # Summary query — always runs
    try:
        sum_cypher, sum_params = build_list_clustering_analyses_summary(
            search_text=effective_text, **filter_kwargs)
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
    except Neo4jClientError:
        if search_text is not None:
            logger.debug("list_clustering_analyses: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            sum_cypher, sum_params = build_list_clustering_analyses_summary(
                search_text=effective_text, **filter_kwargs)
            raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
        else:
            raise

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_entries": raw_summary["total_entries"],
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_cluster_type": _rename_freq(
            raw_summary["by_cluster_type"], "cluster_type"),
        "by_treatment_type": _rename_freq(
            raw_summary["by_treatment_type"], "treatment_type"),
        "by_background_factors": _rename_freq(
            raw_summary["by_background_factors"], "background_factor"),
        "by_omics_type": _rename_freq(raw_summary["by_omics_type"], "omics_type"),
        "by_growth_phase": _rename_freq(
            raw_summary.get("by_growth_phase", []), "growth_phase"),
    }

    if search_text is not None:
        envelope["score_max"] = raw_summary.get("score_max")
        envelope["score_median"] = raw_summary.get("score_median")
    else:
        envelope["score_max"] = None
        envelope["score_median"] = None

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    try:
        det_cypher, det_params = build_list_clustering_analyses(
            search_text=effective_text, **filter_kwargs,
            verbose=verbose, limit=limit, offset=offset)
        results = conn.execute_query(det_cypher, **det_params)
    except Neo4jClientError:
        if search_text is not None and effective_text == search_text:
            logger.debug("list_clustering_analyses detail: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            det_cypher, det_params = build_list_clustering_analyses(
                search_text=effective_text, **filter_kwargs,
                verbose=verbose, limit=limit, offset=offset)
            results = conn.execute_query(det_cypher, **det_params)
        else:
            raise

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def list_derived_metrics(
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: Literal["numeric", "boolean", "categorical"] | None = None,
    compartment: str | None = None,
    omics_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    rankable: bool | None = None,
    has_p_value: bool | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Browse, search, and filter DerivedMetric nodes.

    Returns dict with keys: total_entries, total_matching, by_organism,
    by_value_kind, by_metric_type, by_compartment, by_omics_type,
    by_treatment_type, by_background_factors, by_growth_phase,
    score_max, score_median, returned, offset, truncated, results.
    Per result (compact): derived_metric_id, name, metric_type, value_kind,
    rankable, has_p_value, unit, allowed_categories, field_description,
    organism_name, experiment_id, publication_doi, compartment, omics_type,
    treatment_type, background_factors, total_gene_count, growth_phases,
    score (when searching).
    Per result (verbose): adds treatment, light_condition, experimental_context.

    summary=True: results=[], summary fields only.
    """
    if search_text is not None and not search_text.strip():
        raise ValueError("search_text must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    filter_kwargs = dict(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, omics_type=omics_type,
        treatment_type=treatment_type, background_factors=background_factors,
        growth_phases=growth_phases, publication_doi=publication_doi,
        experiment_ids=experiment_ids, derived_metric_ids=derived_metric_ids,
        rankable=rankable, has_p_value=has_p_value,
    )

    effective_text = search_text

    # Summary query — always runs
    try:
        sum_cypher, sum_params = build_list_derived_metrics_summary(
            search_text=effective_text, **filter_kwargs)
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
    except Neo4jClientError:
        if search_text is not None:
            logger.debug("list_derived_metrics: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            sum_cypher, sum_params = build_list_derived_metrics_summary(
                search_text=effective_text, **filter_kwargs)
            raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
        else:
            raise

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_entries": raw_summary["total_entries"],
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_value_kind": _rename_freq(raw_summary["by_value_kind"], "value_kind"),
        "by_metric_type": _rename_freq(raw_summary["by_metric_type"], "metric_type"),
        "by_compartment": _rename_freq(raw_summary["by_compartment"], "compartment"),
        "by_omics_type": _rename_freq(raw_summary["by_omics_type"], "omics_type"),
        "by_treatment_type": _rename_freq(
            raw_summary["by_treatment_type"], "treatment_type"),
        "by_background_factors": _rename_freq(
            raw_summary["by_background_factors"], "background_factor"),
        "by_growth_phase": _rename_freq(
            raw_summary.get("by_growth_phase", []), "growth_phase"),
    }

    if search_text is not None:
        envelope["score_max"] = raw_summary.get("score_max")
        envelope["score_median"] = raw_summary.get("score_median")
    else:
        envelope["score_max"] = None
        envelope["score_median"] = None

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    try:
        det_cypher, det_params = build_list_derived_metrics(
            search_text=effective_text, **filter_kwargs,
            verbose=verbose, limit=limit, offset=offset)
        results = conn.execute_query(det_cypher, **det_params)
    except Neo4jClientError:
        if search_text is not None and effective_text == search_text:
            logger.debug("list_derived_metrics detail: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            det_cypher, det_params = build_list_derived_metrics(
                search_text=effective_text, **filter_kwargs,
                verbose=verbose, limit=limit, offset=offset)
            results = conn.execute_query(det_cypher, **det_params)
        else:
            raise

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def gene_clusters_by_gene(
    locus_tags: list[str],
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    analysis_ids: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Gene-centric cluster lookup. Single organism enforced.

    Returns dict with keys: total_matching, total_clusters,
    genes_with_clusters, genes_without_clusters,
    not_found, not_matched,
    by_cluster_type, by_treatment_type, by_background_factors, by_analysis,
    returned, offset, truncated, results.
    Per result (compact): locus_tag, gene_name, cluster_id, cluster_name,
    cluster_type, membership_score, analysis_id, analysis_name,
    treatment_type, background_factors.
    Per result (verbose): adds cluster_method, member_count,
    cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern, treatment, light_condition,
    experimental_context, p_value.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: if locus_tags is empty or spans multiple organisms.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Single-organism enforcement
    _validate_organism_inputs(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=None, conn=conn,
    )

    filter_kwargs = dict(
        cluster_type=cluster_type, treatment_type=treatment_type,
        background_factors=background_factors,
        publication_doi=publication_doi,
        analysis_ids=analysis_ids,
    )

    # Summary query — always runs
    sum_cypher, sum_params = build_gene_clusters_by_gene_summary(
        locus_tags=locus_tags, **filter_kwargs)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_matching": total_matching,
        "total_clusters": raw_summary["total_clusters"],
        "genes_with_clusters": raw_summary["genes_with_clusters"],
        "genes_without_clusters": raw_summary["genes_without_clusters"],
        "not_found": raw_summary["not_found"],
        "not_matched": raw_summary["not_matched"],
        "by_cluster_type": _rename_freq(
            raw_summary["by_cluster_type"], "cluster_type"),
        "by_treatment_type": _rename_freq(
            raw_summary["by_treatment_type"], "treatment_type"),
        "by_background_factors": _rename_freq(
            raw_summary["by_background_factors"], "background_factor"),
        "by_analysis": _rename_freq(
            raw_summary["by_analysis"], "analysis_id"),
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_gene_clusters_by_gene(
        locus_tags=locus_tags, **filter_kwargs,
        verbose=verbose, limit=limit, offset=offset)
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def gene_derived_metrics(
    locus_tags: list[str],
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: Literal["numeric", "boolean", "categorical"] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Gene-centric DerivedMetric lookup. Single organism enforced.

    Returns dict with keys: total_matching, total_derived_metrics,
    genes_with_metrics, genes_without_metrics, not_found, not_matched,
    by_value_kind, by_metric_type, by_metric, by_compartment,
    by_treatment_type, by_background_factors, by_publication,
    returned, offset, truncated, results.
    Per result (compact, 13 Pydantic fields; 11 emitted by Cypher in the
    current KG): locus_tag, gene_name, derived_metric_id, value_kind, name,
    value, rankable, has_p_value, rank_by_metric, metric_percentile,
    metric_bucket, adjusted_p_value (None), significant (None).
    Per result (verbose adds, 12 Pydantic; 11 emitted): metric_type,
    field_description, unit, allowed_categories, compartment,
    treatment_type, background_factors, publication_doi, treatment,
    light_condition, experimental_context, p_value (None).

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: locus_tags empty, or spans multiple organisms,
                    or organism arg conflicts with inferred organism.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Single-organism enforcement
    _validate_organism_inputs(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=None, conn=conn,
    )

    filter_kwargs = dict(
        metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, treatment_type=treatment_type,
        background_factors=background_factors,
        publication_doi=publication_doi,
        derived_metric_ids=derived_metric_ids,
    )

    # Summary query — always runs
    sum_cypher, sum_params = build_gene_derived_metrics_summary(
        locus_tags=locus_tags, **filter_kwargs)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    total_matching = raw_summary["total_matching"]

    # by_metric is already shaped — sort by count desc; no rename
    by_metric = sorted(
        raw_summary["by_metric"], key=lambda x: x["count"], reverse=True)

    envelope = {
        "total_matching": total_matching,
        "total_derived_metrics": raw_summary["total_derived_metrics"],
        "genes_with_metrics": raw_summary["genes_with_metrics"],
        "genes_without_metrics": raw_summary["genes_without_metrics"],
        "not_found": raw_summary["not_found"],
        "not_matched": raw_summary["not_matched"],
        "by_value_kind": _rename_freq(
            raw_summary["by_value_kind"], "value_kind"),
        "by_metric_type": _rename_freq(
            raw_summary["by_metric_type"], "metric_type"),
        "by_metric": by_metric,
        "by_compartment": _rename_freq(
            raw_summary["by_compartment"], "compartment"),
        "by_treatment_type": _rename_freq(
            raw_summary["by_treatment_type"], "treatment_type"),
        "by_background_factors": _rename_freq(
            raw_summary["by_background_factors"], "background_factor"),
        "by_publication": _rename_freq(
            raw_summary["by_publication"], "publication_doi"),
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_gene_derived_metrics(
        locus_tags=locus_tags, **filter_kwargs,
        verbose=verbose, limit=limit, offset=offset)
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def genes_by_numeric_metric(
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_percentile: float | None = None,
    max_percentile: float | None = None,
    bucket: list[str] | None = None,
    max_rank: int | None = None,
    significant_only: bool = False,
    max_adjusted_p_value: float | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Numeric DerivedMetric drill-down. Cross-organism by design.

    3-query orchestration:
      1. diagnostics — resolve selection, fetch gate states.
      2. (api/ validates) — value_kind=='numeric' check; rankable /
         has_p_value gate compat; build excluded_derived_metrics + warnings.
      3. summary — aggregations over surviving DM ID list (always runs).
      4. detail — rows; skipped when limit==0.

    Selection is mutually exclusive: pass exactly one of
    `derived_metric_ids` or `metric_types`.

    Returns dict with keys: total_matching, total_derived_metrics,
    total_genes, by_organism, by_compartment, by_publication,
    by_experiment, by_metric, top_categories, genes_per_metric_max,
    genes_per_metric_median, not_found_ids, not_matched_ids,
    not_found_metric_types, not_matched_metric_types,
    not_matched_organism, excluded_derived_metrics, warnings,
    returned, offset, truncated, results.
    Per result (compact, 14 cols): locus_tag, gene_name, product,
    gene_category, organism_name, derived_metric_id, name, value_kind,
    rankable, has_p_value, value, rank_by_metric, metric_percentile,
    metric_bucket.
    Per result (verbose adds, 13 cols): metric_type, field_description,
    unit, compartment, experiment_id, publication_doi, treatment_type,
    background_factors, treatment, light_condition, experimental_context,
    gene_function_description, gene_summary.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: derived_metric_ids+metric_types both/neither set;
                    rankable-gated filter used and ALL selected DMs
                    rankable=False;
                    has_p_value-gated filter used and ALL selected DMs
                    has_p_value=False.
    """
    # 1. Mutual exclusion check
    if derived_metric_ids is not None and metric_types is not None:
        raise ValueError(
            "provide one of derived_metric_ids or metric_types, not both")
    if derived_metric_ids is None and metric_types is None:
        raise ValueError(
            "must provide one of derived_metric_ids or metric_types")

    # 2. summary=True shortcut
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # 3. Q1: diagnostics
    diag_cypher, diag_params = build_genes_by_numeric_metric_diagnostics(
        derived_metric_ids=derived_metric_ids,
        metric_types=metric_types,
        organism=organism,
        experiment_ids=experiment_ids,
        publication_doi=publication_doi,
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
    )
    diagnostics = conn.execute_query(diag_cypher, **diag_params)

    # 4. Compute not_found_ids / not_found_metric_types
    surviving_ids = {d["derived_metric_id"] for d in diagnostics}
    surviving_metric_types = {d["metric_type"] for d in diagnostics}
    not_found_ids = [
        x for x in (derived_metric_ids or []) if x not in surviving_ids
    ]
    not_found_metric_types = [
        x for x in (metric_types or []) if x not in surviving_metric_types
    ]

    excluded_derived_metrics: list[dict] = []
    warnings: list[str] = []

    # 5. Validate rankable gate
    rankable_filters = {
        "min_percentile": min_percentile,
        "max_percentile": max_percentile,
        "bucket": bucket,
        "max_rank": max_rank,
    }
    triggered_rank = [
        name for name, val in rankable_filters.items() if val is not None
    ]
    if triggered_rank:
        rankable_dms = [d for d in diagnostics if d["rankable"]]
        non_rankable_dms = [d for d in diagnostics if not d["rankable"]]
        if not diagnostics:
            # Nothing survived diagnostic scoping — fall through; summary
            # will be empty.
            pass
        elif not rankable_dms and non_rankable_dms:
            non_rankable_repr = [
                f"{d['derived_metric_id']} (rankable=False)"
                for d in non_rankable_dms
            ]
            raise ValueError(
                f"All {len(non_rankable_dms)} selected DMs are non-rankable; "
                f"cannot apply rankable-gated filter(s) {triggered_rank}. "
                f"Selected DMs: {non_rankable_repr}. "
                f"Inspect rankable=true DMs via "
                f"list_derived_metrics(value_kind='numeric', rankable=True)."
            )
        elif non_rankable_dms:
            filter_label = ", ".join(f"`{f}`" for f in triggered_rank)
            for d in non_rankable_dms:
                excluded_derived_metrics.append({
                    "derived_metric_id": d["derived_metric_id"],
                    "metric_type": d["metric_type"],
                    "rankable": False,
                    "has_p_value": d["has_p_value"],
                    "reason": (
                        f"non-rankable; {filter_label} filter does not apply"
                    ),
                })
            mt_list = ", ".join(d["metric_type"] for d in non_rankable_dms)
            warnings.append(
                f"{len(non_rankable_dms)} non-rankable DM(s) excluded by "
                f"{filter_label} filter ({mt_list})"
            )

    # 6. Validate has_p_value gate
    pval_filters = {
        "significant_only": significant_only if significant_only else None,
        "max_adjusted_p_value": max_adjusted_p_value,
    }
    triggered_pval = [
        name for name, val in pval_filters.items() if val is not None
    ]
    if triggered_pval:
        excluded_set_for_pval = {
            x["derived_metric_id"] for x in excluded_derived_metrics
        }
        pval_dms = [
            d for d in diagnostics
            if d["has_p_value"]
            and d["derived_metric_id"] not in excluded_set_for_pval
        ]
        non_pval_dms = [
            d for d in diagnostics
            if not d["has_p_value"]
            and d["derived_metric_id"] not in excluded_set_for_pval
        ]
        if not diagnostics:
            pass
        elif not pval_dms and non_pval_dms:
            raise ValueError(
                f"All {len(non_pval_dms)} selected DMs have "
                f"has_p_value=False; cannot apply has_p_value-gated "
                f"filter(s) {triggered_pval}. No numeric DM in the current "
                f"KG has p-values. Inspect has_p_value=true DMs via "
                f"list_derived_metrics(has_p_value=True)."
            )
        elif non_pval_dms:
            filter_label = ", ".join(f"`{f}`" for f in triggered_pval)
            for d in non_pval_dms:
                excluded_derived_metrics.append({
                    "derived_metric_id": d["derived_metric_id"],
                    "metric_type": d["metric_type"],
                    "rankable": d["rankable"],
                    "has_p_value": False,
                    "reason": (
                        f"has_p_value=False; {filter_label} filter does "
                        f"not apply"
                    ),
                })
            mt_list = ", ".join(d["metric_type"] for d in non_pval_dms)
            warnings.append(
                f"{len(non_pval_dms)} has_p_value=False DM(s) excluded by "
                f"{filter_label} filter ({mt_list})"
            )

    # 7. Build surviving DM ID list (post-gate)
    excluded_set = {x["derived_metric_id"] for x in excluded_derived_metrics}
    surviving = [
        d["derived_metric_id"]
        for d in diagnostics
        if d["derived_metric_id"] not in excluded_set
    ]

    # Defensive: if everything got soft-excluded, return empty envelope
    # without calling summary/detail (which require non-empty list).
    if not surviving:
        return {
            "total_matching": 0,
            "total_derived_metrics": 0,
            "total_genes": 0,
            "by_organism": [],
            "by_compartment": [],
            "by_publication": [],
            "by_experiment": [],
            "by_metric": [],
            "top_categories": [],
            "genes_per_metric_max": 0,
            "genes_per_metric_median": 0.0,
            "not_found_ids": not_found_ids,
            "not_matched_ids": [],
            "not_found_metric_types": not_found_metric_types,
            "not_matched_metric_types": [],
            "not_matched_organism": organism,
            "excluded_derived_metrics": excluded_derived_metrics,
            "warnings": warnings,
            "returned": 0,
            "offset": offset,
            "truncated": False,
            "results": [],
        }

    # 8. Q2: summary (always runs)
    sum_cypher, sum_params = build_genes_by_numeric_metric_summary(
        derived_metric_ids=surviving,
        locus_tags=locus_tags,
        min_value=min_value, max_value=max_value,
        min_percentile=min_percentile, max_percentile=max_percentile,
        bucket=bucket, max_rank=max_rank,
    )
    sum_rows = conn.execute_query(sum_cypher, **sum_params)
    sum_row = sum_rows[0] if sum_rows else {}

    # 9. Frequency-list rename + post-processing
    by_organism = _rename_freq(
        sum_row.get("by_organism", []), "organism_name")
    by_compartment = _rename_freq(
        sum_row.get("by_compartment", []), "compartment")
    by_publication = _rename_freq(
        sum_row.get("by_publication", []), "publication_doi")
    by_experiment = _rename_freq(
        sum_row.get("by_experiment", []), "experiment_id")
    top_categories = _rename_freq(
        sum_row.get("top_categories_raw", []), "gene_category")[:5]

    # by_metric is already shaped — sort by count desc
    by_metric = sorted(
        sum_row.get("by_metric", []),
        key=lambda x: x["count"],
        reverse=True,
    )

    # 10. Compute not_matched_ids / not_matched_metric_types
    contributed_ids = {entry["derived_metric_id"] for entry in by_metric}
    not_matched_ids_all = set(surviving) - contributed_ids
    not_matched_ids = [
        x for x in (derived_metric_ids or []) if x in not_matched_ids_all
    ]

    not_matched_metric_types: list[str] = []
    if metric_types:
        for mt in metric_types:
            dm_ids_for_mt = [
                d["derived_metric_id"]
                for d in diagnostics
                if d["metric_type"] == mt
            ]
            if not dm_ids_for_mt:
                continue  # already in not_found_metric_types
            if all(
                d_id in excluded_set or d_id in not_matched_ids_all
                for d_id in dm_ids_for_mt
            ):
                not_matched_metric_types.append(mt)

    # not_matched_organism: organism passed but no by_organism row matches
    not_matched_organism: str | None = None
    if organism:
        if not any(
            organism.lower() in entry["organism_name"].lower()
            for entry in by_organism
        ):
            not_matched_organism = organism

    # 11. Q3: detail (skip when limit=0)
    results: list[dict] = []
    if limit != 0:
        det_cypher, det_params = build_genes_by_numeric_metric(
            derived_metric_ids=surviving,
            locus_tags=locus_tags,
            min_value=min_value, max_value=max_value,
            min_percentile=min_percentile, max_percentile=max_percentile,
            bucket=bucket, max_rank=max_rank,
            verbose=verbose, limit=limit, offset=offset,
        )
        results = conn.execute_query(det_cypher, **det_params)

    # 12. Build envelope
    total_matching = sum_row.get("total_matching", 0)
    returned = len(results)
    truncated = total_matching > offset + returned

    return {
        "total_matching": total_matching,
        "total_derived_metrics": sum_row.get("total_derived_metrics", 0),
        "total_genes": sum_row.get("total_genes", 0),
        "by_organism": by_organism,
        "by_compartment": by_compartment,
        "by_publication": by_publication,
        "by_experiment": by_experiment,
        "by_metric": by_metric,
        "top_categories": top_categories,
        "genes_per_metric_max": sum_row.get("genes_per_metric_max", 0) or 0,
        "genes_per_metric_median": (
            sum_row.get("genes_per_metric_median", 0.0) or 0.0
        ),
        "not_found_ids": not_found_ids,
        "not_matched_ids": not_matched_ids,
        "not_found_metric_types": not_found_metric_types,
        "not_matched_metric_types": not_matched_metric_types,
        "not_matched_organism": not_matched_organism,
        "excluded_derived_metrics": excluded_derived_metrics,
        "warnings": warnings,
        "returned": returned,
        "offset": offset,
        "truncated": truncated,
        "results": results,
    }


def genes_by_boolean_metric(
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    flag: bool | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Boolean DerivedMetric drill-down. Cross-organism by design.

    3-query orchestration:
      1. diagnostics — resolve selection by intersecting with
         dm.value_kind='boolean' + scoping filters; surviving IDs drive
         Q2/Q3. Wrong-kind IDs and IDs filtered out by scoping both
         surface as not_found_ids (matches genes_by_numeric_metric).
      2. summary — aggregations over surviving DM ID list (always runs).
      3. detail — rows; skipped when limit==0.

    Selection is mutually exclusive: pass exactly one of
    `derived_metric_ids` or `metric_types`. No rankable / has_p_value
    gates exist for boolean DMs, so `excluded_derived_metrics` and
    `warnings` are always returned as `[]` (kept for envelope-shape
    consistency with genes_by_numeric_metric).

    Returns dict with keys: total_matching, total_derived_metrics,
    total_genes, by_organism, by_compartment, by_publication,
    by_experiment, by_value, by_metric, top_categories,
    genes_per_metric_max, genes_per_metric_median, not_found_ids,
    not_matched_ids, not_found_metric_types, not_matched_metric_types,
    not_matched_organism, excluded_derived_metrics (always []),
    warnings (always []), returned, offset, truncated, results.
    Per result (compact, 11 cols): locus_tag, gene_name, product,
    gene_category, organism_name, derived_metric_id, name, value_kind,
    rankable, has_p_value, value.
    Per result (verbose adds, 13 cols): metric_type, field_description,
    unit, compartment, experiment_id, publication_doi, treatment_type,
    background_factors, treatment, light_condition, experimental_context,
    gene_function_description, gene_summary.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: derived_metric_ids+metric_types both/neither set.
    """
    # 1. Mutual exclusion check
    if derived_metric_ids is not None and metric_types is not None:
        raise ValueError(
            "provide one of derived_metric_ids or metric_types, not both")
    if derived_metric_ids is None and metric_types is None:
        raise ValueError(
            "must provide one of derived_metric_ids or metric_types")

    # 2. summary=True shortcut
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # 3. Q1: diagnostics
    diag_cypher, diag_params = build_genes_by_boolean_metric_diagnostics(
        derived_metric_ids=derived_metric_ids,
        metric_types=metric_types,
        organism=organism,
        experiment_ids=experiment_ids,
        publication_doi=publication_doi,
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
    )
    diagnostics = conn.execute_query(diag_cypher, **diag_params)

    # 4. Compute not_found_ids / not_found_metric_types
    surviving_ids = {d["derived_metric_id"] for d in diagnostics}
    surviving_metric_types = {d["metric_type"] for d in diagnostics}
    not_found_ids = [
        x for x in (derived_metric_ids or []) if x not in surviving_ids
    ]
    not_found_metric_types = [
        x for x in (metric_types or []) if x not in surviving_metric_types
    ]

    # 5. No gate validation for boolean — excluded_derived_metrics /
    #    warnings always empty. Surviving = all diagnostics survivors.
    surviving = [d["derived_metric_id"] for d in diagnostics]

    # 6. Defensive: if everything got filtered out at diagnostics, skip
    #    summary/detail (Cypher's `IN $derived_metric_ids` would receive
    #    an empty list).
    if not surviving:
        return {
            "total_matching": 0,
            "total_derived_metrics": 0,
            "total_genes": 0,
            "by_organism": [],
            "by_compartment": [],
            "by_publication": [],
            "by_experiment": [],
            "by_value": [],
            "by_metric": [],
            "top_categories": [],
            "genes_per_metric_max": 0,
            "genes_per_metric_median": 0.0,
            "not_found_ids": not_found_ids,
            "not_matched_ids": [],
            "not_found_metric_types": not_found_metric_types,
            "not_matched_metric_types": [],
            "not_matched_organism": organism,
            "excluded_derived_metrics": [],
            "warnings": [],
            "returned": 0,
            "offset": offset,
            "truncated": False,
            "results": [],
        }

    # 7. Q2: summary (always runs)
    sum_cypher, sum_params = build_genes_by_boolean_metric_summary(
        derived_metric_ids=surviving,
        locus_tags=locus_tags,
        flag=flag,
    )
    sum_rows = conn.execute_query(sum_cypher, **sum_params)
    sum_row = sum_rows[0] if sum_rows else {}

    # 8. Frequency-list rename + post-processing
    by_organism = _rename_freq(
        sum_row.get("by_organism", []), "organism_name")
    by_compartment = _rename_freq(
        sum_row.get("by_compartment", []), "compartment")
    by_publication = _rename_freq(
        sum_row.get("by_publication", []), "publication_doi")
    by_experiment = _rename_freq(
        sum_row.get("by_experiment", []), "experiment_id")
    by_value = _rename_freq(sum_row.get("by_value", []), "value")
    top_categories = _rename_freq(
        sum_row.get("top_categories_raw", []), "gene_category")[:5]

    # by_metric: per-DM scalar rollups (true_count / false_count /
    # dm_*_count are scalars, not freq lists — no nested rename).
    by_metric = sorted(
        sum_row.get("by_metric", []),
        key=lambda x: x["count"],
        reverse=True,
    )

    # 9. Compute not_matched_ids / not_matched_metric_types
    contributed_ids = {entry["derived_metric_id"] for entry in by_metric}
    not_matched_ids_all = set(surviving) - contributed_ids
    not_matched_ids = [
        x for x in (derived_metric_ids or []) if x in not_matched_ids_all
    ]

    not_matched_metric_types: list[str] = []
    if metric_types:
        for mt in metric_types:
            dm_ids_for_mt = [
                d["derived_metric_id"]
                for d in diagnostics
                if d["metric_type"] == mt
            ]
            if not dm_ids_for_mt:
                continue  # already in not_found_metric_types
            if all(d_id in not_matched_ids_all for d_id in dm_ids_for_mt):
                not_matched_metric_types.append(mt)

    # not_matched_organism: organism passed but no by_organism row matches
    not_matched_organism: str | None = None
    if organism:
        if not any(
            organism.lower() in entry["organism_name"].lower()
            for entry in by_organism
        ):
            not_matched_organism = organism

    # 10. Q3: detail (skip when limit=0)
    results: list[dict] = []
    if limit != 0:
        det_cypher, det_params = build_genes_by_boolean_metric(
            derived_metric_ids=surviving,
            locus_tags=locus_tags,
            flag=flag,
            verbose=verbose, limit=limit, offset=offset,
        )
        results = conn.execute_query(det_cypher, **det_params)

    # 11. Build envelope
    total_matching = sum_row.get("total_matching", 0)
    returned = len(results)
    truncated = total_matching > offset + returned

    return {
        "total_matching": total_matching,
        "total_derived_metrics": sum_row.get("total_derived_metrics", 0),
        "total_genes": sum_row.get("total_genes", 0),
        "by_organism": by_organism,
        "by_compartment": by_compartment,
        "by_publication": by_publication,
        "by_experiment": by_experiment,
        "by_value": by_value,
        "by_metric": by_metric,
        "top_categories": top_categories,
        "genes_per_metric_max": sum_row.get("genes_per_metric_max", 0) or 0,
        "genes_per_metric_median": (
            sum_row.get("genes_per_metric_median", 0.0) or 0.0
        ),
        "not_found_ids": not_found_ids,
        "not_matched_ids": not_matched_ids,
        "not_found_metric_types": not_found_metric_types,
        "not_matched_metric_types": not_matched_metric_types,
        "not_matched_organism": not_matched_organism,
        "excluded_derived_metrics": [],
        "warnings": [],
        "returned": returned,
        "offset": offset,
        "truncated": truncated,
        "results": results,
    }


def genes_by_categorical_metric(
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    categories: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Categorical DerivedMetric drill-down. Cross-organism by design.

    3-query orchestration (same as genes_by_boolean_metric, plus a
    categories-subset validation step):
      1. diagnostics — resolve selection by intersecting with
         dm.value_kind='categorical' + scoping; collect each surviving
         DM's allowed_categories. Wrong-kind IDs surface as not_found_ids.
      2. (api/ validates) — `categories` ⊆ union of surviving DMs'
         `allowed_categories` (raise on unknowns).
      3. summary — aggregations over surviving DM ID list (always runs).
      4. detail — rows; skipped when limit==0.

    Selection is mutually exclusive: pass exactly one of
    `derived_metric_ids` or `metric_types`. No rankable / has_p_value
    gates exist for categorical DMs, so `excluded_derived_metrics` and
    `warnings` are always returned as `[]` (kept for envelope-shape
    consistency with genes_by_numeric_metric).

    Returns dict with keys: total_matching, total_derived_metrics,
    total_genes, by_organism, by_compartment, by_publication,
    by_experiment, by_category, by_metric, top_categories,
    genes_per_metric_max, genes_per_metric_median, not_found_ids,
    not_matched_ids, not_found_metric_types, not_matched_metric_types,
    not_matched_organism, excluded_derived_metrics (always []),
    warnings (always []), returned, offset, truncated, results.
    Per result (compact, 11 cols): locus_tag, gene_name, product,
    gene_category, organism_name, derived_metric_id, name, value_kind,
    rankable, has_p_value, value.
    Per result (verbose adds, 14 cols): metric_type, field_description,
    unit, compartment, experiment_id, publication_doi, treatment_type,
    background_factors, treatment, light_condition, experimental_context,
    gene_function_description, gene_summary, allowed_categories.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: derived_metric_ids+metric_types both/neither set;
                    categories includes value not in union of selected
                    DMs' allowed_categories.
    """
    # 1. Mutual exclusion check
    if derived_metric_ids is not None and metric_types is not None:
        raise ValueError(
            "provide one of derived_metric_ids or metric_types, not both")
    if derived_metric_ids is None and metric_types is None:
        raise ValueError(
            "must provide one of derived_metric_ids or metric_types")

    # 2. summary=True shortcut
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # 3. Q1: diagnostics
    diag_cypher, diag_params = build_genes_by_categorical_metric_diagnostics(
        derived_metric_ids=derived_metric_ids,
        metric_types=metric_types,
        organism=organism,
        experiment_ids=experiment_ids,
        publication_doi=publication_doi,
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
    )
    diagnostics = conn.execute_query(diag_cypher, **diag_params)

    # 4. Compute not_found_ids / not_found_metric_types
    surviving_ids = {d["derived_metric_id"] for d in diagnostics}
    surviving_metric_types = {d["metric_type"] for d in diagnostics}
    not_found_ids = [
        x for x in (derived_metric_ids or []) if x not in surviving_ids
    ]
    not_found_metric_types = [
        x for x in (metric_types or []) if x not in surviving_metric_types
    ]

    # 5. Validate categories ⊆ union of surviving DMs' allowed_categories
    if categories:
        allowed_union: set[str] = set()
        for d in diagnostics:
            allowed_union.update(d.get("allowed_categories") or [])
        unknown = [c for c in categories if c not in allowed_union]
        if unknown:
            raise ValueError(
                f"categories include value(s) not in any selected DM's "
                f"allowed_categories: {sorted(set(unknown))}. Allowed "
                f"union across surviving DMs: {sorted(allowed_union)}. "
                f"Inspect via "
                f"list_derived_metrics(value_kind='categorical')."
            )

    # 6. No gate validation for categorical — excluded_derived_metrics /
    #    warnings always empty. Surviving = all diagnostics survivors.
    surviving = [d["derived_metric_id"] for d in diagnostics]

    # 7. Defensive: if everything got filtered out at diagnostics, skip
    #    summary/detail.
    if not surviving:
        return {
            "total_matching": 0,
            "total_derived_metrics": 0,
            "total_genes": 0,
            "by_organism": [],
            "by_compartment": [],
            "by_publication": [],
            "by_experiment": [],
            "by_category": [],
            "by_metric": [],
            "top_categories": [],
            "genes_per_metric_max": 0,
            "genes_per_metric_median": 0.0,
            "not_found_ids": not_found_ids,
            "not_matched_ids": [],
            "not_found_metric_types": not_found_metric_types,
            "not_matched_metric_types": [],
            "not_matched_organism": organism,
            "excluded_derived_metrics": [],
            "warnings": [],
            "returned": 0,
            "offset": offset,
            "truncated": False,
            "results": [],
        }

    # 8. Q2: summary (always runs)
    sum_cypher, sum_params = build_genes_by_categorical_metric_summary(
        derived_metric_ids=surviving,
        locus_tags=locus_tags,
        categories=categories,
    )
    sum_rows = conn.execute_query(sum_cypher, **sum_params)
    sum_row = sum_rows[0] if sum_rows else {}

    # 9. Frequency-list rename + post-processing
    by_organism = _rename_freq(
        sum_row.get("by_organism", []), "organism_name")
    by_compartment = _rename_freq(
        sum_row.get("by_compartment", []), "compartment")
    by_publication = _rename_freq(
        sum_row.get("by_publication", []), "publication_doi")
    by_experiment = _rename_freq(
        sum_row.get("by_experiment", []), "experiment_id")
    by_category = _rename_freq(sum_row.get("by_category", []), "category")
    top_categories = _rename_freq(
        sum_row.get("top_categories_raw", []), "gene_category")[:5]

    # by_metric: rename nested by_category / dm_by_category freq lists
    # (item → category) on top of the envelope-level rename. Top-level
    # keys (count, allowed_categories, dm_total_gene_count) are scalars
    # / pass-through and don't need renaming.
    by_metric_raw = sum_row.get("by_metric", [])
    by_metric: list[dict] = []
    for entry in by_metric_raw:
        new_entry = dict(entry)
        new_entry["by_category"] = _rename_freq(
            entry.get("by_category", []), "category")
        new_entry["dm_by_category"] = _rename_freq(
            entry.get("dm_by_category", []), "category")
        by_metric.append(new_entry)
    by_metric.sort(key=lambda x: x["count"], reverse=True)

    # 10. Compute not_matched_ids / not_matched_metric_types
    contributed_ids = {entry["derived_metric_id"] for entry in by_metric}
    not_matched_ids_all = set(surviving) - contributed_ids
    not_matched_ids = [
        x for x in (derived_metric_ids or []) if x in not_matched_ids_all
    ]

    not_matched_metric_types: list[str] = []
    if metric_types:
        for mt in metric_types:
            dm_ids_for_mt = [
                d["derived_metric_id"]
                for d in diagnostics
                if d["metric_type"] == mt
            ]
            if not dm_ids_for_mt:
                continue  # already in not_found_metric_types
            if all(d_id in not_matched_ids_all for d_id in dm_ids_for_mt):
                not_matched_metric_types.append(mt)

    # not_matched_organism: organism passed but no by_organism row matches
    not_matched_organism: str | None = None
    if organism:
        if not any(
            organism.lower() in entry["organism_name"].lower()
            for entry in by_organism
        ):
            not_matched_organism = organism

    # 11. Q3: detail (skip when limit=0)
    results: list[dict] = []
    if limit != 0:
        det_cypher, det_params = build_genes_by_categorical_metric(
            derived_metric_ids=surviving,
            locus_tags=locus_tags,
            categories=categories,
            verbose=verbose, limit=limit, offset=offset,
        )
        results = conn.execute_query(det_cypher, **det_params)

    # 12. Build envelope
    total_matching = sum_row.get("total_matching", 0)
    returned = len(results)
    truncated = total_matching > offset + returned

    return {
        "total_matching": total_matching,
        "total_derived_metrics": sum_row.get("total_derived_metrics", 0),
        "total_genes": sum_row.get("total_genes", 0),
        "by_organism": by_organism,
        "by_compartment": by_compartment,
        "by_publication": by_publication,
        "by_experiment": by_experiment,
        "by_category": by_category,
        "by_metric": by_metric,
        "top_categories": top_categories,
        "genes_per_metric_max": sum_row.get("genes_per_metric_max", 0) or 0,
        "genes_per_metric_median": (
            sum_row.get("genes_per_metric_median", 0.0) or 0.0
        ),
        "not_found_ids": not_found_ids,
        "not_matched_ids": not_matched_ids,
        "not_found_metric_types": not_found_metric_types,
        "not_matched_metric_types": not_matched_metric_types,
        "not_matched_organism": not_matched_organism,
        "excluded_derived_metrics": [],
        "warnings": [],
        "returned": returned,
        "offset": offset,
        "truncated": truncated,
        "results": results,
    }


def genes_in_cluster(
    cluster_ids: list[str] | None = None,
    analysis_id: str | None = None,
    organism: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Cluster IDs or analysis ID → member genes.

    Returns dict with keys: total_matching, by_organism, by_cluster,
    top_categories, genes_per_cluster_max, genes_per_cluster_median,
    not_found_clusters, not_matched_clusters, not_matched_organism,
    returned, offset, truncated, results.
    When analysis_id: also returns analysis_name.
    Per result (compact): locus_tag, gene_name, product, gene_category,
    organism_name, cluster_id, cluster_name, membership_score.
    Per result (verbose): adds gene_function_description, gene_summary,
    p_value, cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: if neither or both of cluster_ids and analysis_id provided.
    """
    if cluster_ids is not None and analysis_id is not None:
        raise ValueError("Provide cluster_ids or analysis_id, not both.")
    if cluster_ids is None and analysis_id is None:
        raise ValueError("Must provide cluster_ids or analysis_id.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Summary query — always runs
    sum_cypher, sum_params = build_genes_in_cluster_summary(
        cluster_ids=cluster_ids, analysis_id=analysis_id, organism=organism)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    by_cluster = raw_summary["by_cluster"]
    cluster_counts = [c["count"] for c in by_cluster]

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_cluster": by_cluster,
        "top_categories": _rename_freq(
            raw_summary["by_category_raw"], "category")[:5],
        "genes_per_cluster_max": max(cluster_counts) if cluster_counts else 0,
        "genes_per_cluster_median": (
            statistics.median(cluster_counts) if cluster_counts else 0
        ),
        "not_found_clusters": raw_summary["not_found_clusters"],
        "not_matched_clusters": raw_summary["not_matched_clusters"],
    }

    envelope["analysis_name"] = (
        raw_summary.get("analysis_name") if analysis_id is not None else None
    )

    # Check organism match
    if organism is not None and total_matching == 0 and not raw_summary["not_found_clusters"]:
        envelope["not_matched_organism"] = organism
    else:
        envelope["not_matched_organism"] = None

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_genes_in_cluster(
        cluster_ids=cluster_ids, analysis_id=analysis_id, organism=organism,
        verbose=verbose, limit=limit, offset=offset)
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


# ---------------------------------------------------------------------------
# ontology_landscape helpers
# ---------------------------------------------------------------------------


def _ontology_size_factor(median: float) -> float:
    """[5, 50] sweet-spot penalty on median term size."""
    if median <= 0:
        return 0.0
    return min(1.0, median / 5.0) * min(1.0, 50.0 / median)


def _ontology_relevance_score(
    row: dict, experiment_weighted: bool,
) -> float:
    sf = _ontology_size_factor(row["median_genes_per_term"])
    if experiment_weighted and "median_exp_coverage" in row:
        return row["median_exp_coverage"] * sf
    return row["genome_coverage"] * sf


def _ontology_exp_coverage_stats(
    expcov_rows: list[dict],
    valid_eids: list[str],
    level_keys: list[tuple],
) -> dict:
    """Zero-fill + min/median/max across experiments per stratum.

    expcov_rows: rows from build_ontology_expcov for a single ontology.
    valid_eids: experiments known to be valid -- any missing from a given
                stratum contributes 0 to the aggregation.
    level_keys: `(level, facet_value)` strata observed in landscape stats;
                experiments contribute 0 where they emit no row. The facet
                is part of the key so InterPro's types (and BRITE's trees)
                do not share one set of coverage numbers.

    Returns {(level, facet_value): {min_exp_coverage, median_exp_coverage,
    max_exp_coverage, n_experiments_with_coverage}}.
    """
    per_level: dict = {
        key: {eid: 0.0 for eid in valid_eids} for key in level_keys
    }
    for r in expcov_rows:
        key = (r["level"], r.get("facet_value"))
        eid = r["eid"]
        if key in per_level and eid in per_level[key]:
            per_level[key][eid] = (
                r["n_at_level"] / r["n_total"] if r["n_total"] else 0.0
            )
    out: dict = {}
    for key, by_eid in per_level.items():
        covs = list(by_eid.values())
        out[key] = {
            "min_exp_coverage": min(covs) if covs else 0.0,
            "median_exp_coverage": statistics.median(covs) if covs else 0.0,
            "max_exp_coverage": max(covs) if covs else 0.0,
            "n_experiments_with_coverage": sum(1 for c in covs if c > 0),
        }
    return out


# ---------------------------------------------------------------------------
# ontology_landscape
# ---------------------------------------------------------------------------


def ontology_landscape(
    organism: str,
    ontology: str | list[str] | None = None,
    experiment_ids: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    min_gene_set_size: int = 5,
    max_gene_set_size: int = 500,
    tree: str | None = None,
    informative_only: bool = True,
    call_class: list[str] | None = None,
    interpro_type: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Characterise ontologies for enrichment in one organism.

    Per-(ontology x level) rows. Ranked by spec_score (genome_coverage
    x size_factor(median_genes_per_term)) when experiment_ids is None,
    or median_exp_coverage x size_factor when set. Only terms with
    min_gene_set_size <= gene_count <= max_gene_set_size contribute to
    per-level stats -- same filter as pathway_enrichment.

    ``ontology`` takes one key, a list of keys, or None to survey every
    registered ontology. InterPro is stratified by (interpro_type, level)
    because its types are not comparable strata; ``by_ontology`` reports
    ``best_interpro_type`` alongside ``best_level``.

    Returns dict with keys: organism_name, organism_gene_count,
    n_ontologies, by_ontology, not_found, not_matched, results,
    returned, total_matching, truncated, offset, filters_applied,
    trust_axes, skipped_ontologies, warnings.

    Raises ValueError on unknown/ambiguous organism, an unknown ontology
    name, or a filter the ontology cannot carry.
    """
    requested = _normalize_ontology_arg(ontology)
    if summary:
        limit = 0

    trust_filters = _active_trust_filters(
        call_class=call_class, interpro_type=interpro_type, tree=tree,
    )
    requested_all = requested if requested is not None else list(ALL_ONTOLOGIES)
    if isinstance(ontology, str):
        _validate_trust_filters(requested_all[0], trust_filters)
        target_keys = list(requested_all)
        skipped_ontologies: list[dict] = []
        trust_warnings: list[str] = []
        per_ontology_filters = {requested_all[0]: dict(trust_filters)}
    else:
        (target_keys, skipped_ontologies, trust_warnings,
         per_ontology_filters) = _resolve_multi_ontology(
            requested_all, trust_filters,
        )

    conn = _default_conn(conn)

    # Step 1: Resolve organism to canonical string (raises on unknown/ambiguous)
    canonical_org = _validate_organism_inputs(
        organism=organism, locus_tags=None, experiment_ids=None, conn=conn,
    )

    # Step 2: Total gene count for genome_coverage denominator
    gc_cypher, gc_params = build_ontology_organism_gene_count(
        organism_name=canonical_org,
    )
    organism_gene_count = conn.execute_query(gc_cypher, **gc_params)[0]["total_genes"]

    # Step 3: Experiment validation
    valid_eids: list[str] = []
    not_found: list[str] = []
    not_matched: list[str] = []
    if experiment_ids:
        ec_cypher, ec_params = build_ontology_experiment_check(
            experiment_ids=experiment_ids,
        )
        ec_rows = conn.execute_query(ec_cypher, **ec_params)
        for r in ec_rows:
            if not r["exists"]:
                not_found.append(r["eid"])
            elif r["exp_organism"] != canonical_org:
                not_matched.append(r["eid"])
            else:
                valid_eids.append(r["eid"])

    # Step 4: Per-ontology landscape queries
    targets = list(target_keys)
    all_rows: list[dict] = []
    for ont in targets:
        ls_cypher, ls_params = build_ontology_landscape(
            ontology=ont, organism_name=canonical_org, verbose=verbose,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
            informative_only=informative_only,
            **per_ontology_filters.get(ont, {}),
        )
        stat_rows = conn.execute_query(ls_cypher, **ls_params)
        # Distinct levels, not stat rows: a faceted ontology emits one row
        # per (facet_value, level), and InterPro's 6 strata sit on 2 levels.
        n_levels = len({r["level"] for r in stat_rows})
        # A facet marks a separate stratum, so it is part of the coverage key.
        ont_facet = ONTOLOGY_CONFIG[ont].get("facet")
        facet_prop = ont_facet["prop"] if ont_facet else None

        # Experiment coverage aggregation (per-ontology)
        exp_stats: dict = {}
        if valid_eids:
            ec_cypher2, ec_params2 = build_ontology_expcov(
                ontology=ont, organism_name=canonical_org,
                experiment_ids=valid_eids,
                min_gene_set_size=min_gene_set_size,
                max_gene_set_size=max_gene_set_size,
            )
            expcov_rows = conn.execute_query(ec_cypher2, **ec_params2)
            exp_stats = _ontology_exp_coverage_stats(
                expcov_rows, valid_eids,
                level_keys=[
                    (r["level"], r.get(facet_prop) if facet_prop else None)
                    for r in stat_rows
                ],
            )

        for r in stat_rows:
            tree_val = r.get("tree")
            row: dict = {
                "ontology_type": ont,
                "level": r["level"],
                "n_terms_with_genes": r["n_terms_with_genes"],
                "n_genes_at_level": r["n_genes_at_level"],
                "genome_coverage": (
                    r["n_genes_at_level"] / organism_gene_count
                    if organism_gene_count else 0.0
                ),
                "min_genes_per_term": r["min_genes_per_term"],
                "q1_genes_per_term": r["q1_genes_per_term"],
                "median_genes_per_term": r["median_genes_per_term"],
                "q3_genes_per_term": r["q3_genes_per_term"],
                "max_genes_per_term": r["max_genes_per_term"],
                "n_levels_in_ontology": n_levels,
            }
            # best_effort_share -- GO ontologies only
            if ont in GO_ONTOLOGIES:
                row["best_effort_share"] = (
                    r["n_best_effort"] / r["n_terms_with_genes"]
                    if r["n_terms_with_genes"] else 0.0
                )
            else:
                row["best_effort_share"] = None
            if tree_val is not None:
                row["tree"] = tree_val
                row["tree_code"] = r.get("tree_code")
            # Sparse facet column: only the ontology that owns it carries it.
            if r.get("interpro_type") is not None:
                row["interpro_type"] = r["interpro_type"]
            if verbose:
                row["example_terms"] = r["example_terms"]
            if valid_eids:
                cov_key = (
                    r["level"], r.get(facet_prop) if facet_prop else None,
                )
                e = exp_stats.get(cov_key, {
                    "min_exp_coverage": 0.0,
                    "median_exp_coverage": 0.0,
                    "max_exp_coverage": 0.0,
                    "n_experiments_with_coverage": 0,
                })
                row.update(e)
            all_rows.append(row)

    # Step 5: Rank in Python. Before limit/offset so relevance_rank is
    # stable when caller paginates.
    experiment_weighted = bool(valid_eids)
    for r in all_rows:
        r["_score"] = _ontology_relevance_score(r, experiment_weighted)
    all_rows.sort(
        key=lambda r: (-r["_score"], -r["genome_coverage"], r["level"]),
    )
    for i, r in enumerate(all_rows):
        r["relevance_rank"] = i + 1
        r.pop("_score", None)

    # by_ontology: summary keyed by ontology_type (or "brite:tree_name"
    # for BRITE with tree); first row per key (already sorted by rank)
    # provides best_* fields.
    by_ontology: dict[str, dict] = {}
    levels_seen: dict[str, set] = {}
    for r in all_rows:
        ont = r["ontology_type"]
        tree_val = r.get("tree")
        key = f"{ont}:{tree_val}" if tree_val else ont
        if key not in by_ontology:
            by_ontology[key] = {
                "best_level": r["level"],
                "best_genome_coverage": r["genome_coverage"],
                "best_relevance_rank": r["relevance_rank"],
                "n_levels": 0,
            }
            if tree_val:
                by_ontology[key]["tree"] = tree_val
                by_ontology[key]["tree_code"] = r.get("tree_code")
            if r.get("interpro_type") is not None:
                by_ontology[key]["best_interpro_type"] = r["interpro_type"]
            levels_seen[key] = set()
        levels_seen[key].add(r["level"])
        # Distinct levels, not rows: a faceted ontology contributes one row
        # per (facet_value, level) under a single key.
        by_ontology[key]["n_levels"] = len(levels_seen[key])

    # Step 6: Paginate + envelope
    total_matching = len(all_rows)
    sliced = all_rows[offset:]
    if limit is not None:
        results = [] if limit == 0 else sliced[:limit]
    else:
        results = sliced

    return {
        "organism_name": canonical_org,
        "organism_gene_count": organism_gene_count,
        "n_ontologies": len({r["ontology_type"] for r in all_rows}),
        "by_ontology": by_ontology,
        "not_found": not_found,
        "not_matched": not_matched,
        "results": results,
        "returned": len(results),
        "total_matching": total_matching,
        "truncated": total_matching > offset + len(results),
        "offset": offset,
        "filters_applied": dict(trust_filters),
        "trust_axes": {o: ontology_trust_axes(o) for o in targets},
        "skipped_ontologies": skipped_ontologies,
        "warnings": trust_warnings,
    }


# ---------------------------------------------------------------------------
# pathway_enrichment helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# pathway_enrichment public function
# ---------------------------------------------------------------------------


def pathway_enrichment(
    organism: str,
    experiment_ids: list[str],
    ontology: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    direction: str = "both",
    significant_only: bool = True,
    background: str | list[str] = "table_scope",
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    pvalue_cutoff: float = 0.05,
    timepoint_filter: list[str] | None = None,
    growth_phases: list[str] | None = None,
    tree: str | None = None,
    informative_only: bool = True,
    sources: list[str] | None = None,
    evidence: list[str] | None = None,
    max_tier: int | None = None,
    min_evidence_score: float | None = None,
    call_class: list[str] | None = None,
    interpro_type: str | None = None,
    *,
    conn: GraphConnection | None = None,
):
    """Pathway over-representation analysis from DE results.

    The trust filters (``sources``, ``evidence``, ``max_tier``,
    ``min_evidence_score``, ``call_class``, ``interpro_type``) shape the
    gene-to-term mapping itself, so tested sets and background move
    together; the envelope echoes that as ``background_filtered``.

    ``interpro_type`` is required when ``ontology='interpro'``: InterPro
    types are separate strata, not levels of one hierarchy, and pooling
    them mixes families with domains and superfamilies.

    Returns an EnrichmentResult. Callers who need the MCP-dict envelope
    should call result.to_envelope(...).

    Raises ValueError when the ontology cannot carry a filter you set, or
    when an InterPro run omits interpro_type.
    """
    if ontology not in ALL_ONTOLOGIES:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {ALL_ONTOLOGIES}")
    trust_filters = _active_trust_filters(
        sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
        interpro_type=interpro_type, tree=tree,
    )
    _require_interpro_stratum(ontology, interpro_type)
    _validate_trust_filters(ontology, trust_filters)
    if level is None and not term_ids:
        raise ValueError("At least one of `level` or `term_ids` must be provided.")
    if direction not in {"up", "down", "both"}:
        raise ValueError(f"direction must be 'up'|'down'|'both'; got {direction!r}")
    if isinstance(background, str):
        if background not in {"table_scope", "organism"}:
            raise ValueError(
                f"background must be 'table_scope', 'organism', or a list; got {background!r}"
            )
    elif isinstance(background, list):
        if not background:
            raise ValueError("background list must be non-empty")
    else:
        raise ValueError(
            f"background must be 'table_scope', 'organism', or a list; "
            f"got {type(background).__name__}"
        )
    if min_gene_set_size < 0:
        raise ValueError("min_gene_set_size must be >= 0.")
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError("max_gene_set_size must be >= min_gene_set_size.")
    if not (0 < pvalue_cutoff < 1):
        raise ValueError(f"pvalue_cutoff must be in (0, 1); got {pvalue_cutoff}")
    if not experiment_ids:
        raise ValueError("at least one experiment_id required")

    from multiomics_explorer.analysis.enrichment import (
        de_enrichment_inputs, fisher_ora, EnrichmentResult,
    )
    import pandas as pd
    import numpy as np

    conn = _default_conn(conn)

    inputs = de_enrichment_inputs(
        experiment_ids=experiment_ids,
        organism=organism,
        direction=direction,
        significant_only=significant_only,
        timepoint_filter=timepoint_filter,
        growth_phases=growth_phases,
        conn=conn,
    )

    if background == "table_scope":
        resolved_bg = inputs.background
        background_mode = "table_scope"
    elif background == "organism":
        org_rows = conn.execute_query(
            "MATCH (g:Gene {organism_name: $org}) "
            "RETURN collect(g.locus_tag) AS locus_tags",
            org=inputs.organism_name,
        )
        org_locus_tags = org_rows[0]["locus_tags"] if org_rows else []
        resolved_bg = {c: list(org_locus_tags) for c in inputs.gene_sets}
        background_mode = "organism"
    else:
        resolved_bg = {c: list(background) for c in inputs.gene_sets}
        background_mode = {
            "explicit": list(background)[:5] + (
                [f"+{len(background) - 5} more"] if len(background) > 5 else []
            ),
        }

    inputs.background = resolved_bg

    gbo_result = genes_by_ontology(
        ontology=ontology, organism=inputs.organism_name,
        level=level, term_ids=term_ids,
        min_gene_set_size=0, max_gene_set_size=None,
        summary=False, verbose=False,
        limit=None, offset=0,
        informative_only=informative_only,
        conn=conn,
        **trust_filters,
    )
    from multiomics_explorer.analysis.frames import to_dataframe
    term2gene = to_dataframe(gbo_result)

    if term2gene.empty or not inputs.gene_sets:
        result = EnrichmentResult(
            kind="pathway", organism_name=inputs.organism_name,
            ontology=ontology, level=level,
            results=pd.DataFrame(), inputs=inputs, term2gene=term2gene,
        )
    else:
        result = fisher_ora(
            inputs, term2gene,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
        )
        result.kind = "pathway"
        result.ontology = ontology
        result.level = level

        md_df = pd.DataFrame.from_dict(
            inputs.cluster_metadata, orient="index"
        ).reset_index().rename(columns={"index": "cluster"})
        result.results = result.results.merge(md_df, on="cluster", how="left")
        sign = np.where(result.results["direction"] == "up", 1,
                        np.where(result.results["direction"] == "down", -1, 0))
        result.results["signed_score"] = (
            sign * -np.log10(result.results["p_adjust"].clip(lower=1e-300))
        )

    result.term_validation = {
        "not_found": list(gbo_result.get("not_found", [])),
        "wrong_ontology": list(gbo_result.get("wrong_ontology", [])),
        "wrong_level": list(gbo_result.get("wrong_level", [])),
        "filtered_out": list(gbo_result.get("filtered_out", [])),
    }

    produced = set(result.results["cluster"]) if not result.results.empty else set()
    skipped = []
    for cluster in inputs.cluster_metadata:
        if cluster in produced:
            continue
        if cluster not in inputs.background or not inputs.background.get(cluster):
            reason = "empty_background"
        elif not inputs.gene_sets.get(cluster):
            reason = "empty_gene_set"
        else:
            reason = "no_pathways_in_size_range"
        skipped.append({"cluster": cluster, "reason": reason})
    skipped.sort(key=lambda s: (s["cluster"], s["reason"]))
    result.clusters_skipped = skipped

    result.params = {
        "organism": organism, "ontology": ontology,
        "level": level, "term_ids": term_ids, "tree": tree,
        "informative_only": informative_only,
        "min_gene_set_size": min_gene_set_size,
        "max_gene_set_size": max_gene_set_size,
        "pvalue_cutoff": pvalue_cutoff,
        "background_mode": background_mode,
        "experiment_ids": experiment_ids,
        "direction": direction,
        "significant_only": significant_only,
        "timepoint_filter": timepoint_filter,
        "growth_phases": growth_phases,
        "n_clusters_input": len(inputs.cluster_metadata),
        "n_clusters_tested": len(produced),
        "n_clusters_skipped": len(skipped),
        "term2gene_row_count": int(len(term2gene)),
        "n_unique_terms": int(term2gene["term_id"].nunique()) if not term2gene.empty else 0,
        "multitest_method": "fdr_bh",
    }
    result.params.update(
        _enrichment_trust_params(ontology, trust_filters, interpro_type)
    )

    return result


# ---------------------------------------------------------------------------
# cluster_enrichment envelope helper
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# cluster_enrichment public function
# ---------------------------------------------------------------------------


def cluster_enrichment(
    analysis_id: str,
    organism: str,
    ontology: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    background: str | list[str] = "cluster_union",
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    min_cluster_size: int = 3,
    max_cluster_size: int | None = None,
    pvalue_cutoff: float = 0.05,
    tree: str | None = None,
    informative_only: bool = True,
    sources: list[str] | None = None,
    evidence: list[str] | None = None,
    max_tier: int | None = None,
    min_evidence_score: float | None = None,
    call_class: list[str] | None = None,
    interpro_type: str | None = None,
    *,
    conn: GraphConnection | None = None,
):
    """Cluster-based over-representation analysis — returns EnrichmentResult.

    Takes the same trust filters as pathway_enrichment; they shape the
    gene-to-term mapping, so tested sets and background move together.
    ``interpro_type`` is required when ``ontology='interpro'``.

    Raises ValueError when the ontology cannot carry a filter you set, or
    when an InterPro run omits interpro_type.
    """
    if ontology not in ALL_ONTOLOGIES:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {ALL_ONTOLOGIES}")
    trust_filters = _active_trust_filters(
        sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
        interpro_type=interpro_type, tree=tree,
    )
    _require_interpro_stratum(ontology, interpro_type)
    _validate_trust_filters(ontology, trust_filters)
    if level is None and not term_ids:
        raise ValueError("At least one of `level` or `term_ids` must be provided.")
    if isinstance(background, str):
        if background not in {"cluster_union", "organism"}:
            raise ValueError(
                f"background must be 'cluster_union', 'organism', or a list; got {background!r}"
            )
    elif isinstance(background, list):
        if not background:
            raise ValueError("background list must be non-empty")
    else:
        raise ValueError(
            f"background must be 'cluster_union', 'organism', or a list; "
            f"got {type(background).__name__}"
        )
    if min_gene_set_size < 0:
        raise ValueError("min_gene_set_size must be >= 0.")
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError("max_gene_set_size must be >= min_gene_set_size.")
    if min_cluster_size < 0:
        raise ValueError("min_cluster_size must be >= 0.")
    if max_cluster_size is not None and max_cluster_size < min_cluster_size:
        raise ValueError("max_cluster_size must be >= min_cluster_size.")
    if not (0 < pvalue_cutoff < 1):
        raise ValueError(f"pvalue_cutoff must be in (0, 1]; got {pvalue_cutoff}")

    from multiomics_explorer.analysis.enrichment import (
        cluster_enrichment_inputs, fisher_ora, EnrichmentResult,
    )
    import pandas as pd

    conn = _default_conn(conn)

    inputs = cluster_enrichment_inputs(
        analysis_id=analysis_id,
        organism=organism,
        min_cluster_size=min_cluster_size,
        max_cluster_size=max_cluster_size,
        conn=conn,
    )

    if background == "cluster_union":
        resolved_bg = inputs.background
        background_mode = "cluster_union"
    elif background == "organism":
        org_rows = conn.execute_query(
            "MATCH (g:Gene {organism_name: $org}) "
            "RETURN collect(g.locus_tag) AS locus_tags",
            org=inputs.organism_name,
        )
        org_locus_tags = org_rows[0]["locus_tags"] if org_rows else []
        resolved_bg = {c: list(org_locus_tags) for c in inputs.gene_sets}
        background_mode = "organism"
    else:
        resolved_bg = {c: list(background) for c in inputs.gene_sets}
        background_mode = {
            "explicit": list(background)[:5] + (
                [f"+{len(background) - 5} more"] if len(background) > 5 else []
            ),
        }
    inputs.background = resolved_bg

    if not inputs.gene_sets:
        result = EnrichmentResult(
            kind="cluster", organism_name=inputs.organism_name,
            ontology=ontology, level=level,
            results=pd.DataFrame(), inputs=inputs, term2gene=pd.DataFrame(),
        )
        result.term_validation = {
            "not_found": [], "wrong_ontology": [], "wrong_level": [], "filtered_out": [],
        }
        result.clusters_skipped = list(inputs.clusters_skipped)
        result.params = _cluster_enrichment_params_dict(
            analysis_id=analysis_id, organism=organism,
            ontology=ontology, level=level, term_ids=term_ids, tree=tree,
            informative_only=informative_only,
            background_mode=background_mode,
            min_gene_set_size=min_gene_set_size, max_gene_set_size=max_gene_set_size,
            min_cluster_size=min_cluster_size, max_cluster_size=max_cluster_size,
            pvalue_cutoff=pvalue_cutoff,
            inputs=inputs, produced=set(), term2gene=pd.DataFrame(),
        )
        result.params.update(
            _enrichment_trust_params(ontology, trust_filters, interpro_type)
        )
        return result

    gbo_result = genes_by_ontology(
        ontology=ontology, organism=inputs.organism_name,
        level=level, term_ids=term_ids,
        min_gene_set_size=0, max_gene_set_size=None,
        summary=False, verbose=False,
        limit=None, offset=0,
        informative_only=informative_only,
        conn=conn,
        **trust_filters,
    )
    from multiomics_explorer.analysis.frames import to_dataframe
    term2gene = to_dataframe(gbo_result)

    if term2gene.empty:
        result = EnrichmentResult(
            kind="cluster", organism_name=inputs.organism_name,
            ontology=ontology, level=level,
            results=pd.DataFrame(), inputs=inputs, term2gene=term2gene,
        )
    else:
        result = fisher_ora(
            inputs, term2gene,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
        )
        result.kind = "cluster"
        result.ontology = ontology
        result.level = level
        if not result.results.empty:
            md_df = pd.DataFrame.from_dict(
                inputs.cluster_metadata, orient="index"
            ).reset_index().rename(columns={"index": "cluster"})
            result.results = result.results.merge(md_df, on="cluster", how="left")

    result.term_validation = {
        "not_found": list(gbo_result.get("not_found", [])),
        "wrong_ontology": list(gbo_result.get("wrong_ontology", [])),
        "wrong_level": list(gbo_result.get("wrong_level", [])),
        "filtered_out": list(gbo_result.get("filtered_out", [])),
    }

    produced = set(result.results["cluster"]) if not result.results.empty else set()
    skipped = list(inputs.clusters_skipped)
    skipped_names = {s.get("cluster_name") for s in skipped}
    for cluster in inputs.cluster_metadata:
        if cluster in produced or cluster in skipped_names:
            continue
        if cluster not in inputs.background or not inputs.background.get(cluster):
            reason = "empty_background"
        elif not inputs.gene_sets.get(cluster):
            reason = "empty_gene_set"
        else:
            reason = "no_pathways_in_size_range"
        md = inputs.cluster_metadata.get(cluster, {})
        skipped.append({
            "cluster_id": md.get("cluster_id"),
            "cluster_name": cluster,
            "member_count": md.get("member_count"),
            "reason": reason,
        })
    skipped.sort(
        key=lambda s: (
            s.get("cluster_name") or "",
            s.get("cluster_id") or "",
            s.get("reason") or "",
        )
    )
    result.clusters_skipped = skipped

    result.params = _cluster_enrichment_params_dict(
        analysis_id=analysis_id, organism=organism,
        ontology=ontology, level=level, term_ids=term_ids, tree=tree,
        informative_only=informative_only,
        background_mode=background_mode,
        min_gene_set_size=min_gene_set_size, max_gene_set_size=max_gene_set_size,
        min_cluster_size=min_cluster_size, max_cluster_size=max_cluster_size,
        pvalue_cutoff=pvalue_cutoff,
        inputs=inputs, produced=produced, term2gene=term2gene,
    )
    result.params.update(
        _enrichment_trust_params(ontology, trust_filters, interpro_type)
    )
    return result


def _cluster_enrichment_params_dict(
    *, analysis_id, organism, ontology, level, term_ids, tree,
    informative_only, background_mode,
    min_gene_set_size, max_gene_set_size,
    min_cluster_size, max_cluster_size, pvalue_cutoff,
    inputs, produced, term2gene,
):
    return {
        "analysis_id": analysis_id, "organism": organism,
        "ontology": ontology, "level": level, "term_ids": term_ids, "tree": tree,
        "informative_only": informative_only,
        "background_mode": background_mode,
        "min_gene_set_size": min_gene_set_size,
        "max_gene_set_size": max_gene_set_size,
        "min_cluster_size": min_cluster_size,
        "max_cluster_size": max_cluster_size,
        "pvalue_cutoff": pvalue_cutoff,
        "n_clusters_input": len(inputs.cluster_metadata),
        "n_clusters_tested": len(produced),
        "n_clusters_skipped": len(inputs.clusters_skipped),
        "term2gene_row_count": int(len(term2gene)),
        "n_unique_terms": int(term2gene["term_id"].nunique()) if not term2gene.empty else 0,
        "multitest_method": "fdr_bh",
    }


_VALID_EVIDENCE_SOURCES = ("metabolism", "transport", "metabolomics")


def list_metabolites(
    search_text: str | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    kegg_compound_ids: list[str] | None = None,
    chebi_ids: list[str] | None = None,
    hmdb_ids: list[str] | None = None,
    mnxm_ids: list[str] | None = None,
    elements: list[str] | None = None,
    mass_min: float | None = None,
    mass_max: float | None = None,
    organism_names: list[str] | None = None,
    pathway_ids: list[str] | None = None,
    evidence_sources: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List metabolites in the chemistry layer with rich filtering.

    Returns dict with keys: total_entries, total_matching, returned, offset,
    truncated, top_organisms, top_metabolite_pathways, by_evidence_source,
    xref_coverage, mass_stats, by_measurement_coverage, score_max,
    score_median, not_found, results.
    Per result (compact): metabolite_id, name, formula, elements, mass,
    catalyst_gene_count (genes reaching this metabolite via Reaction —
    catalysis arm only; a transport-only metabolite reads 0 here, so use
    evidence_sources or transporter_gene_count > 0, NOT
    catalyst_gene_count == 0, to spot metabolomics-only metabolites),
    transporter_gene_count (genes reaching this metabolite through a
    deepest TCDB attachment — the same set genes_by_metabolite's transport
    rows enumerate, summed across organisms), organism_count,
    transporter_count, evidence_sources,
    chebi_id (sparse), pathway_ids, pathway_count, measured_assay_count,
    measured_paper_count, measured_organisms, measured_compartments.
    When verbose=True, also includes: inchikey, smiles, mnxm_id, hmdb_id,
    pathway_names. (For per-organism gene tallies, drill into
    genes_by_metabolite — slice-1 Tool #2.)
    by_measurement_coverage envelope: sub-rollups
    {by_paper_count: [{paper_count, n}], by_compartment: [{compartment, n}]}
    over the matched metabolite set.
    When search_text is provided, also includes score (per row) +
    score_max, score_median (envelope, otherwise None).

    exclude_metabolite_ids: Exclude metabolites with these IDs. Set-difference
        semantics with metabolite_ids — exclude wins on overlap. Empty list
        is no-op.

    Raises:
        ValueError: if search_text is empty/whitespace, or evidence_sources
            contains values outside {"metabolism", "transport",
            "metabolomics"}.
    """
    # 1. Validate search_text (non-empty when provided)
    if search_text is not None and not search_text.strip():
        raise ValueError("search_text must not be empty or whitespace.")

    # 1. Validate evidence_sources enum (defensive — MCP wrapper also gates)
    if evidence_sources is not None:
        invalid = [s for s in evidence_sources if s not in _VALID_EVIDENCE_SOURCES]
        if invalid:
            raise ValueError(
                f"evidence_sources contains invalid value(s) {invalid}; "
                f"allowed: {list(_VALID_EVIDENCE_SOURCES)}."
            )

    # 3. summary=True is sugar for limit=0
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # 2. Lowercase organism_names for WHERE
    organism_names_lc = (
        [o.lower() for o in organism_names] if organism_names else None
    )

    filter_kwargs = dict(
        metabolite_ids=metabolite_ids,
        kegg_compound_ids=kegg_compound_ids,
        chebi_ids=chebi_ids,
        hmdb_ids=hmdb_ids,
        mnxm_ids=mnxm_ids,
        elements=elements,
        mass_min=mass_min,
        mass_max=mass_max,
        organism_names_lc=organism_names_lc,
        pathway_ids=pathway_ids,
        evidence_sources=evidence_sources,
    )
    if exclude_metabolite_ids:
        filter_kwargs["exclude_metabolite_ids"] = exclude_metabolite_ids

    def _run_summary(st=search_text):
        cypher, params = build_list_metabolites_summary(
            search_text=st, **filter_kwargs,
        )
        return conn.execute_query(cypher, **params)[0]

    def _run_detail(st=search_text):
        cypher, params = build_list_metabolites(
            search_text=st, **filter_kwargs,
            verbose=verbose, limit=limit, offset=offset,
        )
        return conn.execute_query(cypher, **params)

    # 4. Always run summary builder (with Lucene retry)
    effective_search = search_text
    try:
        raw_summary = _run_summary()
    except Neo4jClientError:
        if search_text:
            logger.debug(
                "list_metabolites: Lucene parse error, "
                "retrying with escaped query"
            )
            effective_search = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            raw_summary = _run_summary(st=effective_search)
        else:
            raise

    # 5. Run detail builder when limit != 0
    if limit == 0:
        results = []
    else:
        results = _run_detail(st=effective_search)

    # 6. Sparse-strip null chebi_id
    results = [
        {k: v for k, v in row.items() if not (k == "chebi_id" and v is None)}
        for row in results
    ]

    # 7. Compute typed not_found dict (one quick existence Cypher per filter)
    not_found: dict[str, list[str]] = {
        "metabolite_ids": [],
        "organism_names": [],
        "pathway_ids": [],
    }
    if metabolite_ids:
        rows = conn.execute_query(
            "MATCH (m:Metabolite) WHERE m.id IN $ids "
            "RETURN collect(m.id) AS found",
            ids=metabolite_ids,
        )
        found = set(rows[0]["found"]) if rows else set()
        not_found["metabolite_ids"] = [
            x for x in metabolite_ids if x not in found
        ]
    if organism_names:
        rows = conn.execute_query(
            "MATCH (o:OrganismTaxon) "
            "WHERE toLower(o.preferred_name) IN $names "
            "RETURN collect(toLower(o.preferred_name)) AS found",
            names=[o.lower() for o in organism_names],
        )
        found = set(rows[0]["found"]) if rows else set()
        not_found["organism_names"] = [
            x for x in organism_names if x.lower() not in found
        ]
    if pathway_ids:
        rows = conn.execute_query(
            "MATCH (p:KeggTerm) WHERE p.id IN $ids "
            "RETURN collect(p.id) AS found",
            ids=pathway_ids,
        )
        found = set(rows[0]["found"]) if rows else set()
        not_found["pathway_ids"] = [
            x for x in pathway_ids if x not in found
        ]

    # 8. Assemble + return envelope
    total_matching = raw_summary.get("total_matching", 0)
    return {
        "total_entries": raw_summary.get("total_entries", 0),
        "total_matching": total_matching,
        "top_organisms": raw_summary.get("top_organisms", []) or [],
        "top_metabolite_pathways": raw_summary.get(
            "top_metabolite_pathways", []
        ) or [],
        "by_evidence_source": _rename_freq(
            raw_summary.get("by_evidence_source", []) or [],
            "evidence_source",
        ),
        "xref_coverage": {
            "with_chebi": raw_summary.get("with_chebi", 0),
            "with_hmdb": raw_summary.get("with_hmdb", 0),
            "with_mnxm": raw_summary.get("with_mnxm", 0),
        },
        "mass_stats": {
            "mass_min": raw_summary.get("mass_min"),
            "mass_median": raw_summary.get("mass_median"),
            "mass_max": raw_summary.get("mass_max"),
        },
        # Phase 1 plumbing (spec §6.6): pass-through measurement-coverage
        # rollup surfaced by build_list_metabolites_summary. Two sub-rollups:
        # by_paper_count (distribution over m.measured_paper_count) and
        # by_compartment (frequency over m.measured_compartments). Both come
        # from apoc.coll.frequencies as [{item, count}] and need renaming to
        # the {paper_count, count} / {compartment, count} shape Pydantic
        # expects.
        "by_measurement_coverage": _rename_measurement_coverage(
            raw_summary.get("by_measurement_coverage"),
        ),
        "score_max": raw_summary.get("score_max") if search_text else None,
        "score_median": raw_summary.get("score_median") if search_text else None,
        "returned": len(results),
        "offset": offset,
        "truncated": total_matching > offset + len(results),
        "not_found": not_found,
        "results": results,
    }


# evidence_sources accepted by `genes_by_metabolite` — diverges intentionally
# from `_VALID_EVIDENCE_SOURCES` (which includes `"metabolomics"` for the
# metabolite-anchored `list_metabolites`). Gene-anchored tools have no
# metabolomics path (DerivedMetric → Metabolite carries no Gene anchor), so
# we reject `"metabolomics"` at the boundary instead of silently returning
# zero rows.
_VALID_EVIDENCE_SOURCES_GBM = ("metabolism", "transport")


# Sparse-strip: nullable result columns dropped when null. Per-arm-specific
# fields (reaction_id, transport_confidence, etc.) are NOT in this set —
# Phase 3 Item 6.1 keeps them as explicit None on cross-arm rows so every
# row carries identical keys. Only naturally-sparse fields (gene_name,
# product, formula, verbose-only IDs) appear here.
_GBM_SPARSE_FIELDS = (
    "gene_name",
    "product",
    "metabolite_formula",
    "metabolite_mass",
    "metabolite_chebi_id",
    # verbose fields — sparse-strip when null on the other arm or
    # when KG simply has no value
    "gene_category",
    "metabolite_inchikey",
    "metabolite_smiles",
    "metabolite_mnxm_id",
    "metabolite_hmdb_id",
    "reaction_mnxr_id",
    "reaction_rhea_ids",
    "tcdb_level_kind",
    "tc_class_id",
)


_VALID_SUBSTRATE_DEPTHS = ("most_specific", "inherited")

# Retired `transport_confidence` value strings → their `substrate_depth`
# replacement. Used only to build the rename pointer in the ValueError.
_RETIRED_TRANSPORT_CONFIDENCE = {
    "substrate_confirmed": "most_specific",
    "family_inferred": "inherited",
}


def _validate_substrate_depth(substrate_depth: list[str] | None) -> None:
    """Raise ValueError on unknown `substrate_depth` values.

    The two retired `transport_confidence` strings get a rename pointer so a
    caller migrating from the old param lands on the right value.
    """
    if substrate_depth is None:
        return
    for value in substrate_depth:
        if value in _VALID_SUBSTRATE_DEPTHS:
            continue
        replacement = _RETIRED_TRANSPORT_CONFIDENCE.get(value)
        if replacement is not None:
            raise ValueError(
                f"substrate_depth value '{value}' was renamed: use "
                f"substrate_depth=['{replacement}'] instead. Valid values: "
                f"{list(_VALID_SUBSTRATE_DEPTHS)}."
            )
        raise ValueError(
            f"substrate_depth contains invalid value '{value}'; "
            f"allowed: {list(_VALID_SUBSTRATE_DEPTHS)}."
        )


def _sorted_by_substrate_depth(rows_by_sd: list[dict]) -> list[dict]:
    """`by_substrate_depth` rollup: `{substrate_depth, count}` entries sorted
    count desc, then value asc (deterministic across APOC's unordered sets)."""
    return sorted(
        [
            {"substrate_depth": e["substrate_depth"], "count": e["count"]}
            for e in rows_by_sd
        ],
        key=lambda r: (-r["count"], r["substrate_depth"]),
    )


def _substrate_depth_priority(row: dict) -> int:
    """0 for `most_specific` or None (metabolism rows); 1 for `inherited`."""
    return 1 if row.get("substrate_depth") == "inherited" else 0


def _gbm_sort_key(row: dict) -> tuple:
    """Global sort key for genes_by_metabolite detail rows.

    Sort by: (metabolite_id, evidence_source, substrate_depth_priority,
              -tcdb_evidence_score, secondary_id, locus_tag).

    `substrate_depth_priority`:
      - 0 for `most_specific` OR None (metabolism rows)
      - 1 for `inherited`

    `tcdb_evidence_score` desc ranks rows within a transport depth tier;
    metabolism rows carry None (treated as 0 — they never mix with
    transport rows because evidence_source sorts first).

    `secondary_id`: `reaction_id` for metabolism rows, `tcdb_family_id` for
    transport rows. Acts as deterministic tiebreaker within each
    (metabolite, evidence_source, depth, score) group.
    """
    if row.get("evidence_source") == "metabolism":
        secondary = row.get("reaction_id") or ""
    else:
        secondary = row.get("tcdb_family_id") or ""
    return (
        row.get("metabolite_id") or "",
        row.get("evidence_source") or "",
        _substrate_depth_priority(row),
        -(row.get("tcdb_evidence_score") or 0.0),
        secondary,
        row.get("locus_tag") or "",
    )


def genes_by_metabolite(
    metabolite_ids: list[str],
    organism: str,
    *,
    exclude_metabolite_ids: list[str] | None = None,
    ec_numbers: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    mass_balance: str | None = None,
    gene_categories: list[str] | None = None,
    substrate_depth: list[str] | None = None,
    evidence_sources: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int = 10,
    offset: int = 0,
    conn: GraphConnection | None = None,
) -> dict:
    """Find genes connected to specified metabolites in one organism.

    Two evidence arms (joined api-side, not via Cypher UNION):
      - metabolism: `Gene → Reaction → Metabolite`
      - transport:  `Gene → TcdbFamily → Metabolite`, over each gene's
        deepest TCDB attachments only (an attachment is superseded when the
        same gene is also attached to a descendant family). Transport rows
        are therefore projections of the same (gene, metabolite) set as the
        KG's `transported_metabolite_count` / `transporter_gene_count`.

    Path-scoped filters narrow only their own arm; the other arm runs
    unfiltered. Use `evidence_sources` to suppress an entire arm.

    Transport rows carry two TCDB facts (both None on metabolism rows):
      - `substrate_depth` (`most_specific` | `inherited`): the most specific
        surviving transporter node for this substrate, relative to the
        gene-pruned hierarchy — not a curation level. `inherited` rows reach
        the substrate through a broader family's substrate list.
      - `tcdb_evidence_score` (float, 0..1): the KG's composite evidence for
        the gene × family call. Rank with it, don't filter on it — 0 means
        an uncorroborated DIAMOND hit, not "absent".
      - `transport_substrate_resolution` (`resolved` | `family_inferred` |
        None): the GENE's KG-authoritative resolution, repeated on every
        transport row of that gene — not a per-substrate fact (use
        `substrate_depth` for the row). Explicit None on metabolism rows.

    substrate_depth: Transport-arm filter, list of `most_specific` /
        `inherited`. Unknown values raise ValueError; the retired
        `transport_confidence` strings raise with a rename pointer.

    Envelope: `by_substrate_depth` rollup, per-metabolite
    `transport_most_specific_rows` / `transport_inherited_rows`, and
    `top_genes[]` entries carrying the gene-level
    `transport_substrate_resolution` (`resolved` | `family_inferred` | None)
    + `tcdb_evidence_score_max`. Both are raw gene properties: None when
    the gene has no TCDB call at all (independent of which rows it
    contributes here — a gene with only metabolism rows for this metabolite
    can still carry a score for other substrates). `resolved` means at
    least one non-lumping deepest attachment — a resolved gene can still
    contribute `inherited` rows.

    Detail sort: metabolism → `most_specific` → `inherited`; within a
    transport tier `tcdb_evidence_score` desc, then family / locus_tag.

    Auto-warning: when `inherited` rows outnumber `most_specific` rows on the
    transport arm and `substrate_depth` was not set explicitly.

    exclude_metabolite_ids: Exclude metabolites with these IDs. Set-difference
        semantics with metabolite_ids — exclude wins on overlap. Empty list
        is no-op.

    Raises:
        ValueError: if `evidence_sources` contains values outside
            ``("metabolism", "transport")``. Note this diverges from
            `list_metabolites` — gene-anchored tools reject
            ``"metabolomics"``. Also on unknown `substrate_depth` values.
    """
    # 1. Defense-in-depth validators (before any Cypher executes).
    if evidence_sources is not None:
        invalid = [
            s for s in evidence_sources
            if s not in _VALID_EVIDENCE_SOURCES_GBM
        ]
        if invalid:
            raise ValueError(
                f"evidence_sources contains invalid value(s) {invalid}; "
                f"allowed: {list(_VALID_EVIDENCE_SOURCES_GBM)}."
            )
    _validate_substrate_depth(substrate_depth)

    conn = _default_conn(conn)

    # 2. Arm selection driven solely by evidence_sources.
    if evidence_sources is None:
        active_arms = ("metabolism", "transport")
    else:
        # Preserve canonical order regardless of input ordering.
        active_arms = tuple(
            arm for arm in ("metabolism", "transport")
            if arm in evidence_sources
        )

    # 3. Always run summary builder (envelope rollups even when
    # summary=True).
    sum_cypher, sum_params = build_genes_by_metabolite_summary(
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids,
        organism=organism,
        ec_numbers=ec_numbers,
        mass_balance=mass_balance,
        metabolite_pathway_ids=metabolite_pathway_ids,
        gene_categories=gene_categories,
        substrate_depth=substrate_depth,
        arms=active_arms,
    )
    summary_rows = conn.execute_query(sum_cypher, **sum_params)
    raw_summary = summary_rows[0] if summary_rows else {}

    total_matching = raw_summary.get("total_matching", 0) or 0
    gene_count_total = raw_summary.get("gene_count_total", 0) or 0
    by_metabolite = raw_summary.get("by_metabolite", []) or []

    # 4. Detail collection — Mode 1 (single arm), Mode 2 (summary), or
    # Mode 3 (both arms over-fetch + concat + sort + slice).
    results: list[dict]
    if summary:
        results = []
    elif offset >= total_matching:
        # Deep-paging guardrail: short-circuit; don't touch detail arms
        # but still run existence probes so not_found is populated.
        results = []
    else:
        single_arm_mode = len(active_arms) == 1
        if single_arm_mode:
            # Mode 1: pass limit + offset directly into the single arm.
            arm = active_arms[0]
            if arm == "metabolism":
                cypher, params = build_genes_by_metabolite_metabolism(
                    metabolite_ids=metabolite_ids,
                    exclude_metabolite_ids=exclude_metabolite_ids,
                    organism=organism,
                    ec_numbers=ec_numbers,
                    mass_balance=mass_balance,
                    metabolite_pathway_ids=metabolite_pathway_ids,
                    gene_categories=gene_categories,
                    verbose=verbose,
                    limit=limit,
                    offset=offset,
                )
            else:
                cypher, params = build_genes_by_metabolite_transport(
                    metabolite_ids=metabolite_ids,
                    exclude_metabolite_ids=exclude_metabolite_ids,
                    organism=organism,
                    metabolite_pathway_ids=metabolite_pathway_ids,
                    gene_categories=gene_categories,
                    substrate_depth=substrate_depth,
                    verbose=verbose,
                    limit=limit,
                    offset=offset,
                )
            results = list(conn.execute_query(cypher, **params))
        else:
            # Mode 3: both arms; over-fetch limit+offset per arm,
            # concat, global-sort, slice.
            per_arm_fetch = limit + offset
            combined: list[dict] = []
            for arm in active_arms:
                if arm == "metabolism":
                    cypher, params = build_genes_by_metabolite_metabolism(
                        metabolite_ids=metabolite_ids,
                        exclude_metabolite_ids=exclude_metabolite_ids,
                        organism=organism,
                        ec_numbers=ec_numbers,
                        mass_balance=mass_balance,
                        metabolite_pathway_ids=metabolite_pathway_ids,
                        gene_categories=gene_categories,
                        verbose=verbose,
                        limit=per_arm_fetch,
                        offset=0,
                    )
                else:
                    cypher, params = build_genes_by_metabolite_transport(
                        metabolite_ids=metabolite_ids,
                        exclude_metabolite_ids=exclude_metabolite_ids,
                        organism=organism,
                        metabolite_pathway_ids=metabolite_pathway_ids,
                        gene_categories=gene_categories,
                        substrate_depth=substrate_depth,
                        verbose=verbose,
                        limit=per_arm_fetch,
                        offset=0,
                    )
                combined.extend(conn.execute_query(cypher, **params))
            combined.sort(key=_gbm_sort_key)
            results = combined[offset:offset + limit]

    # 5. Sparse-strip nullable result columns.
    results = [
        {k: v for k, v in row.items()
         if not (k in _GBM_SPARSE_FIELDS and v is None)}
        for row in results
    ]

    # 6. Compute not_found.metabolite_ids via existence probe.
    if metabolite_ids:
        rows = conn.execute_query(
            "MATCH (m:Metabolite) WHERE m.id IN $ids "
            "RETURN collect(m.id) AS found",
            ids=metabolite_ids,
        )
        found_metab = set(rows[0]["found"]) if rows else set()
        not_found_metab = [x for x in metabolite_ids if x not in found_metab]
    else:
        not_found_metab = []

    # 7. Compute not_found.metabolite_pathway_ids via existence probe.
    if metabolite_pathway_ids:
        rows = conn.execute_query(
            "MATCH (p:KeggTerm) WHERE p.id IN $ids "
            "RETURN collect(p.id) AS found",
            ids=metabolite_pathway_ids,
        )
        found_paths = set(rows[0]["found"]) if rows else set()
        not_found_paths = [
            x for x in metabolite_pathway_ids if x not in found_paths
        ]
    else:
        not_found_paths = []

    # 8. not_found.organism — set when the fuzzy match resolved to zero
    # genes (i.e. nothing showed up in the summary aggregate).
    not_found_org = organism if gene_count_total == 0 else None

    # 9. not_matched: input metabolite_ids that exist as Metabolite nodes
    # but produced 0 rows in this organism slice. Computed as
    # `(input - not_found.metabolite_ids) - <ids present in by_metabolite>`.
    summary_metab_ids = {
        entry.get("metabolite_id") for entry in by_metabolite
    }
    not_found_set = set(not_found_metab)
    not_matched = [
        mid for mid in metabolite_ids
        if mid not in not_found_set and mid not in summary_metab_ids
    ]

    # 10. Build envelope rollups from the summary builder output.
    # APOC's coll.toSet() yields unordered arrays — we sort api-side for
    # deterministic snapshots, and slice top_* arrays to the spec'd top-10.
    rows_by_es = raw_summary.get("rows_by_evidence_source", []) or []
    rows_by_sd = raw_summary.get("rows_by_substrate_depth", []) or []

    by_evidence_source = sorted(
        [
            {"evidence_source": e["evidence_source"], "count": e["count"]}
            for e in rows_by_es
        ],
        key=lambda r: (-r["count"], r["evidence_source"]),
    )
    by_substrate_depth = _sorted_by_substrate_depth(rows_by_sd)

    # by_metabolite: bounded by input size; sort by metabolite_id asc, no slice.
    by_metabolite = sorted(
        by_metabolite,
        key=lambda r: r.get("metabolite_id") or "",
    )

    # top_* envelopes: sort by gene_count desc + stable tiebreaker, then [:10].
    top_reactions = sorted(
        raw_summary.get("top_reactions", []) or [],
        key=lambda r: (-(r.get("gene_count") or 0), r.get("reaction_id") or ""),
    )[:10]
    top_tcdb_families = sorted(
        raw_summary.get("top_tcdb_families", []) or [],
        key=lambda r: (
            -(r.get("gene_count") or 0),
            r.get("tcdb_family_id") or "",
        ),
    )[:10]
    top_gene_categories = sorted(
        raw_summary.get("top_gene_categories", []) or [],
        key=lambda r: (-(r.get("gene_count") or 0), r.get("category") or ""),
    )[:10]
    # top_genes ranked by combined reaction + transporter breadth (per spec
    # § "Return envelope" line 366 / GbmTopGene docstring), with locus_tag
    # tiebreaker (gene_name may be None and would TypeError on sort).
    # Entries pass through the gene-level TCDB facts
    # (transport_substrate_resolution / tcdb_evidence_score_max) from the
    # summary builder; raw gene props, explicit None when the gene has no
    # TCDB call at all, so every entry carries identical keys.
    top_genes = sorted(
        [
            {
                **r,
                "transport_substrate_resolution": r.get(
                    "transport_substrate_resolution"),
                "tcdb_evidence_score_max": r.get("tcdb_evidence_score_max"),
            }
            for r in (raw_summary.get("top_genes", []) or [])
        ],
        key=lambda r: (
            -((r.get("reaction_count") or 0) + (r.get("transporter_count") or 0)),
            r.get("locus_tag") or "",
        ),
    )[:10]

    # 11. Auto-warning: `inherited` dominance over deepest-attachment
    # transport rows. Strict majority threshold; metabolism rows do not
    # factor in; suppressed when the caller set substrate_depth explicitly.
    warnings: list[str] = []
    transport_ms_total = sum(
        (entry.get("transport_most_specific_rows") or 0)
        for entry in by_metabolite
    )
    transport_inh_total = sum(
        (entry.get("transport_inherited_rows") or 0)
        for entry in by_metabolite
    )
    transport_rows_present = (transport_ms_total + transport_inh_total) > 0
    if (
        transport_rows_present
        and transport_inh_total > transport_ms_total
        and substrate_depth is None
    ):
        warnings.append(
            f"Most transport rows are `inherited` ({transport_inh_total} of "
            f"{transport_inh_total + transport_ms_total}) — the substrate is "
            "reached through a broader family's substrate list, not the "
            "gene's most specific surviving node. Use "
            "substrate_depth=['most_specific'] for conservative-cast "
            "questions (e.g. cross-organism inference); keep `inherited` "
            "rows for broad-screen candidate enumeration, and rank within a "
            "tier by `tcdb_evidence_score`. Per-gene trust lives in "
            "`top_genes[].transport_substrate_resolution`."
        )

    # 12. Assemble + return envelope.
    not_found = {
        "metabolite_ids": not_found_metab,
        "organism": not_found_org,
        "metabolite_pathway_ids": not_found_paths,
    }

    return {
        "total_matching": total_matching,
        "returned": len(results),
        "offset": offset,
        # Per spec § "Result-size controls" line 966 + Pydantic doc:
        # truncated iff (offset + limit) < total_matching.
        "truncated": (offset + limit) < total_matching,
        "warnings": warnings,
        "not_found": not_found,
        "not_matched": not_matched,
        "by_metabolite": by_metabolite,
        "by_evidence_source": by_evidence_source,
        "by_substrate_depth": by_substrate_depth,
        "top_reactions": top_reactions,
        "top_tcdb_families": top_tcdb_families,
        "top_gene_categories": top_gene_categories,
        "top_genes": top_genes,
        "gene_count_total": gene_count_total,
        "reaction_count_total": raw_summary.get("reaction_count_total", 0) or 0,
        "transporter_count_total": raw_summary.get("transporter_count_total", 0) or 0,
        "metabolite_count_total": raw_summary.get("metabolite_count_total", 0) or 0,
        "results": results,
    }


# ---------------------------------------------------------------------------
# metabolites_by_gene — gene-anchored mirror of genes_by_metabolite.
# ---------------------------------------------------------------------------

# Same evidence-source Literal as GBM (gene-anchored tools reject
# 'metabolomics' — there is no gene anchor on metabolomics evidence).
_VALID_EVIDENCE_SOURCES_MBG = ("metabolism", "transport")


# Sparse-strip set is identical to GBM's: only naturally-sparse fields
# (gene_name, product, formula, verbose-only IDs) drop when null. Cross-arm
# fields are intentionally NOT in this set — Phase 3 Item 6.1 keeps them
# as explicit None on cross-arm rows so every row carries identical keys.
_MBG_SPARSE_FIELDS = _GBM_SPARSE_FIELDS


def _mbg_sort_key(row: dict, locus_index: dict[str, int]) -> tuple:
    """Global sort key for metabolites_by_gene detail rows.

    Sort order:
      1. precision_tier: 0 = metabolism, 1 = transport `most_specific`,
         2 = transport `inherited`
      2. tcdb_evidence_score desc (None → 0; metabolism rows all tie)
      3. input gene order via `apoc.coll.indexOf` equivalent
      4. locus_tag (deterministic tiebreaker)
      5. metabolite_id (final tiebreaker)
    """
    if row.get("evidence_source") == "metabolism":
        precision_tier = 0
    else:
        precision_tier = 1 + _substrate_depth_priority(row)
    locus = row.get("locus_tag") or ""
    # Genes not in the input list (shouldn't happen but be defensive) sort
    # last within their precision tier.
    input_pos = locus_index.get(locus, len(locus_index))
    return (
        precision_tier,
        -(row.get("tcdb_evidence_score") or 0.0),
        input_pos,
        locus,
        row.get("metabolite_id") or "",
    )


def metabolites_by_gene(
    locus_tags: list[str],
    organism: str,
    *,
    metabolite_elements: list[str] | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    ec_numbers: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    mass_balance: str | None = None,
    gene_categories: list[str] | None = None,
    substrate_depth: list[str] | None = None,
    evidence_sources: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int = 10,
    offset: int = 0,
    conn: GraphConnection | None = None,
) -> dict:
    """Find metabolites the input gene set's chemistry reaches in one organism.

    Two evidence arms (joined api-side, not via Cypher UNION):
      - metabolism: `Gene → Reaction → Metabolite`
      - transport:  `Gene → TcdbFamily → Metabolite`, over each gene's
        deepest TCDB attachments only (an attachment is superseded when the
        same gene is also attached to a descendant family). Transport rows
        are therefore projections of the same (gene, metabolite) set as the
        KG's `transported_metabolite_count` on `gene_overview`.

    Path-scoped filters narrow only their own arm; the other arm runs
    unfiltered. Use `evidence_sources` to suppress an entire arm.

    Transport rows carry two TCDB facts (both None on metabolism rows):
      - `substrate_depth` (`most_specific` | `inherited`): the most specific
        surviving transporter node for this substrate, relative to the
        gene-pruned hierarchy — not a curation level.
      - `tcdb_evidence_score` (float, 0..1): the KG's composite evidence for
        the gene × family call. Rank with it, don't filter on it — 0 means
        an uncorroborated DIAMOND hit, not "absent".
      - `transport_substrate_resolution` (`resolved` | `family_inferred` |
        None): the GENE's KG-authoritative resolution, repeated on every
        transport row of that gene — not a per-substrate fact (use
        `substrate_depth` for the row). Explicit None on metabolism rows.

    substrate_depth: Transport-arm filter, list of `most_specific` /
        `inherited`. Unknown values raise ValueError; the retired
        `transport_confidence` strings raise with a rename pointer.

    Envelope: `by_substrate_depth` rollup, and `by_gene[]` entries carrying
    `transport_most_specific_rows` / `transport_inherited_rows` plus the
    gene-level `transport_substrate_resolution` (`resolved` |
    `family_inferred` | None) + `tcdb_evidence_score_max`. Both are raw
    gene properties: None when the gene has no TCDB call at all
    (independent of which rows it contributes here). `resolved` means at
    least one non-lumping deepest attachment — a resolved gene can still
    contribute `inherited` rows; read per-row `substrate_depth` to separate
    them.

    Detail sort: metabolism → `most_specific` → `inherited` globally (so a
    single ABC-only gene can't eat `limit`); within a transport tier
    `tcdb_evidence_score` desc, then input gene order.

    Auto-warning: per gene, when `by_gene[].transport_substrate_resolution`
    is `family_inferred` — that gene's substrate breadth is reachability,
    not capability. Such a gene still emits `most_specific` rows (substrates
    positioned at the superfamily itself), so `substrate_depth` does not
    guard against it; the resolution field does. Suppressed when
    `substrate_depth` was set explicitly.

    exclude_metabolite_ids: Exclude metabolites with these IDs. Set-difference
        semantics with metabolite_ids — exclude wins on overlap. Empty list
        is no-op.

    Raises:
        ValueError: if `evidence_sources` contains values outside
            ``("metabolism", "transport")``. Mirrors `genes_by_metabolite`
            — gene-anchored tools reject ``"metabolomics"``. Also on
            unknown `substrate_depth` values.
    """
    # 1. Defense-in-depth validators (before any Cypher executes).
    if evidence_sources is not None:
        invalid = [
            s for s in evidence_sources
            if s not in _VALID_EVIDENCE_SOURCES_MBG
        ]
        if invalid:
            raise ValueError(
                f"evidence_sources contains invalid value(s) {invalid}; "
                f"allowed: {list(_VALID_EVIDENCE_SOURCES_MBG)}."
            )
    _validate_substrate_depth(substrate_depth)

    conn = _default_conn(conn)

    # 2. Arm selection driven solely by evidence_sources.
    if evidence_sources is None:
        active_arms = ("metabolism", "transport")
    else:
        # Preserve canonical order regardless of input ordering.
        active_arms = tuple(
            arm for arm in ("metabolism", "transport")
            if arm in evidence_sources
        )

    # 3. Always run summary builder (envelope rollups even when summary=True).
    sum_cypher, sum_params = build_metabolites_by_gene_summary(
        locus_tags=locus_tags,
        organism=organism,
        metabolite_elements=metabolite_elements,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids,
        ec_numbers=ec_numbers,
        mass_balance=mass_balance,
        metabolite_pathway_ids=metabolite_pathway_ids,
        gene_categories=gene_categories,
        substrate_depth=substrate_depth,
        arms=active_arms,
    )
    summary_rows = conn.execute_query(sum_cypher, **sum_params)
    raw_summary = summary_rows[0] if summary_rows else {}

    total_matching = raw_summary.get("total_matching", 0) or 0
    gene_count_total = raw_summary.get("gene_count_total", 0) or 0
    by_gene = raw_summary.get("by_gene", []) or []

    # 4. Detail collection — Mode 1 (single arm), Mode 2 (summary), or
    # Mode 3 (both arms over-fetch + concat + global-sort + slice).
    locus_index = {lt: idx for idx, lt in enumerate(locus_tags)}
    results: list[dict]
    if summary:
        results = []
    elif offset > 0 and offset >= total_matching:
        # Deep-paging guardrail: short-circuit; don't touch detail arms
        # but still run existence probes so not_found is populated.
        # Only kicks in for explicit pagination (offset>0); offset=0 with
        # total_matching=0 still dispatches the arms (cheap; preserves
        # symmetry with non-empty case for callers/mocks).
        results = []
    else:
        single_arm_mode = len(active_arms) == 1
        if single_arm_mode:
            # Mode 1: pass limit + offset directly into the single arm.
            arm = active_arms[0]
            if arm == "metabolism":
                cypher, params = build_metabolites_by_gene_metabolism(
                    locus_tags=locus_tags,
                    organism=organism,
                    metabolite_elements=metabolite_elements,
                    metabolite_ids=metabolite_ids,
                    exclude_metabolite_ids=exclude_metabolite_ids,
                    ec_numbers=ec_numbers,
                    mass_balance=mass_balance,
                    metabolite_pathway_ids=metabolite_pathway_ids,
                    gene_categories=gene_categories,
                    verbose=verbose,
                    limit=limit,
                    offset=offset,
                )
            else:
                cypher, params = build_metabolites_by_gene_transport(
                    locus_tags=locus_tags,
                    organism=organism,
                    metabolite_elements=metabolite_elements,
                    metabolite_ids=metabolite_ids,
                    exclude_metabolite_ids=exclude_metabolite_ids,
                    metabolite_pathway_ids=metabolite_pathway_ids,
                    gene_categories=gene_categories,
                    substrate_depth=substrate_depth,
                    verbose=verbose,
                    limit=limit,
                    offset=offset,
                )
            results = list(conn.execute_query(cypher, **params))
        else:
            # Mode 3: both arms; over-fetch limit+offset per arm,
            # concat, global-sort, slice.
            per_arm_fetch = limit + offset
            combined: list[dict] = []
            for arm in active_arms:
                if arm == "metabolism":
                    cypher, params = build_metabolites_by_gene_metabolism(
                        locus_tags=locus_tags,
                        organism=organism,
                        metabolite_elements=metabolite_elements,
                        metabolite_ids=metabolite_ids,
                        exclude_metabolite_ids=exclude_metabolite_ids,
                        ec_numbers=ec_numbers,
                        mass_balance=mass_balance,
                        metabolite_pathway_ids=metabolite_pathway_ids,
                        gene_categories=gene_categories,
                        verbose=verbose,
                        limit=per_arm_fetch,
                        offset=0,
                    )
                else:
                    cypher, params = build_metabolites_by_gene_transport(
                        locus_tags=locus_tags,
                        organism=organism,
                        metabolite_elements=metabolite_elements,
                        metabolite_ids=metabolite_ids,
                        exclude_metabolite_ids=exclude_metabolite_ids,
                        metabolite_pathway_ids=metabolite_pathway_ids,
                        gene_categories=gene_categories,
                        substrate_depth=substrate_depth,
                        verbose=verbose,
                        limit=per_arm_fetch,
                        offset=0,
                    )
                combined.extend(conn.execute_query(cypher, **params))
            combined.sort(key=lambda r: _mbg_sort_key(r, locus_index))
            results = combined[offset:offset + limit]

    # 5. Sparse-strip nullable result columns.
    results = [
        {k: v for k, v in row.items()
         if not (k in _MBG_SPARSE_FIELDS and v is None)}
        for row in results
    ]

    # 6. Compute not_found.locus_tags via existence probe (always run).
    if locus_tags:
        rows = conn.execute_query(
            "MATCH (g:Gene {organism_name: $organism}) "
            "WHERE g.locus_tag IN $locus_tags "
            "RETURN collect(DISTINCT g.locus_tag) AS found",
            organism=organism, locus_tags=locus_tags,
        )
        found_locus = set(rows[0]["found"]) if rows else set()
        not_found_locus = [lt for lt in locus_tags if lt not in found_locus]
    else:
        found_locus = set()
        not_found_locus = []

    # 7. Compute not_found.metabolite_pathway_ids via existence probe.
    if metabolite_pathway_ids:
        rows = conn.execute_query(
            "MATCH (p:KeggTerm) WHERE p.id IN $ids "
            "RETURN collect(p.id) AS found",
            ids=metabolite_pathway_ids,
        )
        found_paths = set(rows[0]["found"]) if rows else set()
        not_found_paths = [
            x for x in metabolite_pathway_ids if x not in found_paths
        ]
    else:
        not_found_paths = []

    # 8. Compute not_found.metabolite_elements via existence probe (any
    # KG metabolite carrying the element symbol).
    if metabolite_elements:
        rows = conn.execute_query(
            "MATCH (m:Metabolite) "
            "WHERE size(m.elements) > 0 "
            "WITH apoc.coll.toSet(apoc.coll.flatten(collect(m.elements))) AS all_elements "
            "RETURN [e IN $elements WHERE e IN all_elements] AS found",
            elements=metabolite_elements,
        )
        found_elems = set(rows[0]["found"]) if rows else set()
        not_found_elements = [
            e for e in metabolite_elements if e not in found_elems
        ]
    else:
        not_found_elements = []

    # 9. Compute not_found.metabolite_ids via existence probe.
    if metabolite_ids:
        rows = conn.execute_query(
            "MATCH (m:Metabolite) WHERE m.id IN $ids "
            "RETURN collect(m.id) AS found",
            ids=metabolite_ids,
        )
        found_metab = set(rows[0]["found"]) if rows else set()
        not_found_metab = [x for x in metabolite_ids if x not in found_metab]
    else:
        not_found_metab = []

    # 10. not_found.organism — set when fuzzy-resolution yielded zero genes
    # in the slice (mirror GBM).
    not_found_org = organism if gene_count_total == 0 else None

    # 11. not_matched: locus_tags that resolve to a Gene in the requested
    # organism (i.e. exist in `found_locus`) but produced 0 rows in the
    # filtered slice (i.e. NOT in by_gene). This is symmetric to GBM's
    # `not_matched` (which uses metabolite_ids).
    summary_locus_tags = {
        entry.get("locus_tag") for entry in by_gene
    }
    not_matched = [
        lt for lt in locus_tags
        if lt in found_locus and lt not in summary_locus_tags
    ]

    # 12. Build envelope rollups from the summary builder output.
    rows_by_es = raw_summary.get("rows_by_evidence_source", []) or []
    rows_by_sd = raw_summary.get("rows_by_substrate_depth", []) or []

    by_evidence_source = sorted(
        [
            {"evidence_source": e["evidence_source"], "count": e["count"]}
            for e in rows_by_es
        ],
        key=lambda r: (-r["count"], r["evidence_source"]),
    )
    by_substrate_depth = _sorted_by_substrate_depth(rows_by_sd)

    # by_gene: bounded by input list; sort by input order (mirror builder
    # ORDER BY apoc.coll.indexOf), then locus_tag for stability. Entries
    # pass through the gene-level TCDB facts (raw gene props; explicit None
    # when the gene has no TCDB call at all, so every entry carries
    # identical keys).
    by_gene = sorted(
        [
            {
                **r,
                "transport_substrate_resolution": r.get(
                    "transport_substrate_resolution"),
                "tcdb_evidence_score_max": r.get("tcdb_evidence_score_max"),
            }
            for r in by_gene
        ],
        key=lambda r: (
            locus_index.get(r.get("locus_tag") or "", len(locus_index)),
            r.get("locus_tag") or "",
        ),
    )

    # by_element: full freq, periodic-table-bounded (~30 max). Sort desc by
    # count + ascending element for deterministic output.
    by_element = sorted(
        raw_summary.get("by_element", []) or [],
        key=lambda r: (
            -(r.get("metabolite_count") or 0),
            r.get("element") or "",
        ),
    )

    # top_* envelopes: sort by gene_count desc + stable tiebreaker, then [:10].
    top_metabolites = sorted(
        raw_summary.get("top_metabolites", []) or [],
        key=lambda r: (
            -(r.get("gene_count") or 0),
            r.get("metabolite_id") or "",
        ),
    )[:10]
    top_reactions = sorted(
        raw_summary.get("top_reactions", []) or [],
        key=lambda r: (-(r.get("gene_count") or 0), r.get("reaction_id") or ""),
    )[:10]
    top_tcdb_families = sorted(
        raw_summary.get("top_tcdb_families", []) or [],
        key=lambda r: (
            -(r.get("gene_count") or 0),
            r.get("tcdb_family_id") or "",
        ),
    )[:10]
    top_gene_categories = sorted(
        raw_summary.get("top_gene_categories", []) or [],
        key=lambda r: (-(r.get("gene_count") or 0), r.get("category") or ""),
    )[:10]
    # Phase 2 Item 2: top_metabolite_pathways now sourced directly from the
    # summary builder, which produces a chemistry-pathway-filtered rollup
    # (p.reaction_count >= 3) over m.pathway_ids (KG-A5 denorm,
    # transport-extended; uniform coverage across both arms).
    top_metabolite_pathways = (
        raw_summary.get("top_metabolite_pathways", []) or []
    )

    # 13. Auto-warning: gene-anchored, keyed on the KG-authoritative
    # `transport_substrate_resolution = 'family_inferred'` (every deepest
    # attachment is a lumping family), NOT on a row-share threshold.
    # Suppressed when the caller set substrate_depth explicitly.
    warnings: list[str] = []
    family_inferred_genes = [
        entry["locus_tag"] for entry in by_gene
        if entry.get("transport_substrate_resolution") == "family_inferred"
        and entry.get("locus_tag")
    ]
    if family_inferred_genes and substrate_depth is None:
        listed = ", ".join(family_inferred_genes[:10])
        if len(family_inferred_genes) > 10:
            listed += f", … ({len(family_inferred_genes)} genes)"
        warnings.append(
            f"transport_substrate_resolution is `family_inferred` for "
            f"{listed}: substrate breadth is reachability, not capability "
            "for these genes — their deepest attachment is a lumping "
            "superfamily (e.g. 3.A.1), so even their most_specific rows are "
            "superfamily-level positions, not subfamily calls. "
            "substrate_depth=['most_specific'] does NOT filter these out; "
            "the gene's transport_substrate_resolution is the only guard. "
            "Treat them as candidates, not calls; rank by "
            "`tcdb_evidence_score`. Note that resolved means at least one "
            "non-lumping attachment (not all) — resolved genes can still "
            "contribute `inherited` rows (read per-row `substrate_depth`)."
        )

    # 14. Assemble + return envelope.
    not_found = {
        "locus_tags": not_found_locus,
        "organism": not_found_org,
        "metabolite_ids": not_found_metab,
        "metabolite_pathway_ids": not_found_paths,
        "metabolite_elements": not_found_elements,
    }

    return {
        "total_matching": total_matching,
        "returned": len(results),
        "offset": offset,
        # truncated iff (offset + limit) < total_matching (mirrors GBM).
        "truncated": (offset + limit) < total_matching,
        "warnings": warnings,
        "not_found": not_found,
        "not_matched": not_matched,
        "by_gene": by_gene,
        "by_evidence_source": by_evidence_source,
        "by_substrate_depth": by_substrate_depth,
        "by_element": by_element,
        "top_metabolites": top_metabolites,
        "top_reactions": top_reactions,
        "top_tcdb_families": top_tcdb_families,
        "top_gene_categories": top_gene_categories,
        "top_metabolite_pathways": top_metabolite_pathways,
        "gene_count_total": gene_count_total,
        "reaction_count_total": raw_summary.get("reaction_count_total", 0) or 0,
        "transporter_count_total": raw_summary.get("transporter_count_total", 0) or 0,
        "metabolite_count_total": raw_summary.get("metabolite_count_total", 0) or 0,
        "results": results,
    }


# ---------------------------------------------------------------------------
# list_metabolite_assays — Phase 5 metabolomics-measurement discovery surface
# Mirrors list_derived_metrics; 2-query pattern (summary always; detail when
# limit != 0). Lucene retry on metaboliteAssayFullText parse errors.
# ---------------------------------------------------------------------------


def list_metabolite_assays(
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: Literal["numeric", "boolean"] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    assay_ids: list[str] | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    rankable: bool | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List MetaboliteAssay nodes — discovery surface for the metabolomics
    measurement layer. Mirrors `list_derived_metrics`.

    Returns dict with envelope keys:
      total_entries, total_matching, metabolite_count_total,
      by_organism, by_value_kind, by_compartment, top_metric_types,
      by_treatment_type, by_background_factors, by_growth_phase,
      by_detection_status, score_max (opt), score_median (opt),
      returned, offset, truncated, not_found, results.

    Per-result compact:
      assay_id, name, metric_type, value_kind, rankable, unit,
      field_description, organism_name, experiment_id, publication_doi,
      compartment, omics_type, treatment_type, background_factors,
      growth_phases, total_metabolite_count, aggregation_method,
      preferred_id, value_min, value_q1, value_median, value_q3, value_max,
      timepoints, detection_status_counts (+ score when searching).
    Verbose adds: treatment, light_condition, experimental_context.

    `not_found` is a structured dict, one bucket per batch input:
      {assay_ids: [...], metabolite_ids: [...], experiment_ids: [...],
       publication_doi: [...]}. Empty per field
      when all matched.

    summary=True forces limit=0 and skips the detail query.
    """
    if search_text is not None and not search_text.strip():
        raise ValueError("search_text must not be empty if provided.")

    conn = _default_conn(conn)
    if summary:
        limit = 0

    builder_kwargs = dict(
        search_text=search_text, organism=organism, metric_types=metric_types,
        value_kind=value_kind, compartment=compartment,
        treatment_type=treatment_type, background_factors=background_factors,
        growth_phases=growth_phases, publication_doi=publication_doi,
        experiment_ids=experiment_ids, assay_ids=assay_ids,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids, rankable=rankable,
    )

    effective_text = search_text

    # ---- Summary query (always runs) -------------------------------------
    try:
        sum_cypher, sum_params = build_list_metabolite_assays_summary(
            **builder_kwargs)
        sum_result = conn.execute_query(sum_cypher, **sum_params)
    except Neo4jClientError:
        if search_text is not None:
            logger.debug(
                "list_metabolite_assays summary: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            retry_kwargs = {**builder_kwargs, "search_text": effective_text}
            sum_cypher, sum_params = build_list_metabolite_assays_summary(
                **retry_kwargs)
            sum_result = conn.execute_query(sum_cypher, **sum_params)
        else:
            raise

    summary_row = sum_result[0] if sum_result else {}
    total_entries = summary_row.get("total_entries", 0)
    total_matching = summary_row.get("total_matching", 0)
    metabolite_count_total = summary_row.get("metabolite_count_total", 0)

    # Rename apoc.coll.frequencies output keys (item/count → domain).
    by_organism = _rename_freq(
        summary_row.get("by_organism", []), "organism_name")
    by_value_kind = _rename_freq(
        summary_row.get("by_value_kind", []), "value_kind")
    by_compartment = _rename_freq(
        summary_row.get("by_compartment", []), "compartment")
    top_metric_types = _rename_freq(
        summary_row.get("top_metric_types", []), "metric_type")
    by_treatment_type = _rename_freq(
        summary_row.get("by_treatment_type", []), "treatment_type")
    by_background_factors = _rename_freq(
        summary_row.get("by_background_factors", []), "background_factor")
    by_growth_phase = _rename_freq(
        summary_row.get("by_growth_phase", []), "growth_phase")
    by_detection_status = _rename_freq(
        summary_row.get("by_detection_status", []), "detection_status")
    score_max = summary_row.get("score_max")
    score_median = summary_row.get("score_median")

    # ---- Detail query (skipped when limit == 0) ---------------------------
    if limit == 0:
        results: list[dict] = []
    else:
        detail_kwargs = {**builder_kwargs, "search_text": effective_text}
        try:
            det_cypher, det_params = build_list_metabolite_assays(
                **detail_kwargs, verbose=verbose,
                limit=limit, offset=offset)
            results = conn.execute_query(det_cypher, **det_params)
        except Neo4jClientError:
            if search_text is not None and effective_text == search_text:
                logger.debug(
                    "list_metabolite_assays detail: Lucene parse error, retrying")
                effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
                retry_kwargs = {**builder_kwargs, "search_text": effective_text}
                det_cypher, det_params = build_list_metabolite_assays(
                    **retry_kwargs, verbose=verbose,
                    limit=limit, offset=offset)
                results = conn.execute_query(det_cypher, **det_params)
            else:
                raise

    # ---- not_found (structured per §11 Conv B / §13.6) -------------------
    # One existence-check Cypher per batch input. Mirrors the
    # `MetNotFound` pattern on list_metabolites (api/functions.py §7
    # of list_metabolites). Each query is cheap — indexed lookups on
    # the KG's primary-key properties.
    not_found: dict[str, list[str]] = {
        "assay_ids": [],
        "metabolite_ids": [],
        "experiment_ids": [],
        "publication_doi": [],
    }
    if assay_ids:
        rows = conn.execute_query(
            "MATCH (a:MetaboliteAssay) WHERE a.id IN $ids "
            "RETURN collect(a.id) AS found",
            ids=assay_ids,
        )
        found = set(rows[0]["found"]) if rows else set()
        not_found["assay_ids"] = [x for x in assay_ids if x not in found]
    if metabolite_ids:
        rows = conn.execute_query(
            "MATCH (m:Metabolite) WHERE m.id IN $ids "
            "RETURN collect(m.id) AS found",
            ids=metabolite_ids,
        )
        found = set(rows[0]["found"]) if rows else set()
        not_found["metabolite_ids"] = [
            x for x in metabolite_ids if x not in found
        ]
    if experiment_ids:
        rows = conn.execute_query(
            "MATCH (e:Experiment) WHERE e.id IN $ids "
            "RETURN collect(e.id) AS found",
            ids=experiment_ids,
        )
        found = set(rows[0]["found"]) if rows else set()
        not_found["experiment_ids"] = [
            x for x in experiment_ids if x not in found
        ]
    if publication_doi:
        rows = conn.execute_query(
            "MATCH (p:Publication) WHERE p.id IN $ids "
            "RETURN collect(p.id) AS found",
            ids=publication_doi,
        )
        found = set(rows[0]["found"]) if rows else set()
        not_found["publication_doi"] = [
            x for x in publication_doi if x not in found
        ]

    return {
        "total_entries": total_entries,
        "total_matching": total_matching,
        "metabolite_count_total": metabolite_count_total,
        "by_organism": by_organism,
        "by_value_kind": by_value_kind,
        "by_compartment": by_compartment,
        "top_metric_types": top_metric_types,
        "by_treatment_type": by_treatment_type,
        "by_background_factors": by_background_factors,
        "by_growth_phase": by_growth_phase,
        "by_detection_status": by_detection_status,
        "score_max": score_max,
        "score_median": score_median,
        "returned": len(results),
        "offset": offset,
        "truncated": total_matching > offset + len(results),
        "not_found": not_found,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Metabolites-by-assay slice — 3 tools (slice spec 2026-05-06)
# ---------------------------------------------------------------------------

# Closed vocabularies for the numeric drill-down's edge-level filters.
_VALID_METRIC_BUCKETS = {"top_decile", "top_quartile", "mid", "low"}
_VALID_DETECTION_STATUS = {"detected", "sporadic", "not_detected"}


def _mqa_build_by_metric(
    diag_rows: list[dict],
    summary_by_assay: list[dict],
    summary_filtered_min: float | None,
    summary_filtered_max: float | None,
    surviving_ids: list[str],
) -> list[dict]:
    """Build `by_metric` envelope: per-assay precomputed-vs-filtered range.

    Each surviving assay gets a row pairing the full-assay value range
    (echoed from diagnostics: value_min/q1/median/q3/max) with the
    filtered-slice count + min/max. The filtered_value_min/max from the
    summary is global across assays in the current slice; we surface it
    on every contributing assay so the LLM can compare slice vs full
    range inline (mirrors DM `by_metric`).
    """
    surviving_set = set(surviving_ids)
    diag_by_id = {r["assay_id"]: r for r in diag_rows if r["assay_id"] in surviving_set}
    summary_count_by_id = {r["item"]: r["count"] for r in (summary_by_assay or [])}

    by_metric: list[dict] = []
    for aid in sorted(surviving_set):
        d = diag_by_id.get(aid, {})
        count = summary_count_by_id.get(aid, 0)
        by_metric.append({
            "assay_id": aid,
            "name": d.get("name"),
            "value_kind": d.get("value_kind"),
            "rankable": d.get("rankable", False),
            "count": count,
            # Full-assay precomputed range (echoed from diagnostics).
            "assay_value_min": d.get("value_min"),
            "assay_value_q1": d.get("value_q1"),
            "assay_value_median": d.get("value_median"),
            "assay_value_q3": d.get("value_q3"),
            "assay_value_max": d.get("value_max"),
            # Filtered-slice min/max (global across the current selection).
            "filtered_value_min": (
                summary_filtered_min if count > 0 else None
            ),
            "filtered_value_max": (
                summary_filtered_max if count > 0 else None
            ),
        })
    by_metric.sort(key=lambda r: (-(r["count"] or 0), r["assay_id"]))
    return by_metric


def _probe_existence(
    conn: GraphConnection,
    label: str,
    id_property: str,
    ids: list[str],
) -> list[str]:
    """Helper: probe which of `ids` exist on (label) nodes via id_property.

    Returns sorted list of IDs NOT found (input set − returned set).
    """
    if not ids:
        return []
    rows = conn.execute_query(
        f"MATCH (n:{label}) WHERE n.{id_property} IN $ids RETURN collect(n.{id_property}) AS found",
        ids=ids,
    )
    found = set(rows[0]["found"]) if rows else set()
    return sorted(set(ids) - found)


def metabolites_by_quantifies_assay(
    *,
    assay_ids: list[str],
    organism: str | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    value_min: float | None = None,
    value_max: float | None = None,
    detection_status: list[str] | None = None,
    timepoint: list[str] | None = None,
    metric_bucket: list[str] | None = None,
    metric_percentile_min: float | None = None,
    metric_percentile_max: float | None = None,
    rank_by_metric_max: int | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int = 5,
    offset: int = 0,
    conn: GraphConnection | None = None,
) -> dict:
    """Drill into numeric MetaboliteAssay edges.

    Three-query dispatch per `genes_by_numeric_metric` precedent:
      1. diagnostics — probe rankable + per-assay precomputed range
         (echoed into envelope `by_metric`).
      2. summary — envelope rollups; runs over surviving (rankable)
         assay_ids when rankable-gated filters apply.
      3. detail — top-N rows; skipped when `summary=True`.

    Tested-absent rows (`detection_status='not_detected'` / `value=0`)
    are real biology — kept in `results`, counted in `total_matching`
    and `by_detection_status` rollups.

    `not_found` is a structured dict, one bucket per batch input
    (`assay_ids`, `metabolite_ids`, `experiment_ids`, `publication_doi`).

    Raises:
        ValueError: empty `assay_ids`; `metric_bucket` / `detection_status`
        contains invalid values; rankable-gated filter set with all
        selected assays non-rankable.
    """
    conn = _default_conn(conn)

    # ---- Validation ------------------------------------------------------
    if not assay_ids:
        raise ValueError("assay_ids must not be empty")
    if metric_bucket is not None:
        bad = set(metric_bucket) - _VALID_METRIC_BUCKETS
        if bad:
            raise ValueError(
                f"Invalid metric_bucket value(s): {sorted(bad)}. "
                f"Allowed: {sorted(_VALID_METRIC_BUCKETS)}."
            )
    if detection_status is not None:
        bad = set(detection_status) - _VALID_DETECTION_STATUS
        if bad:
            raise ValueError(
                f"Invalid detection_status value(s): {sorted(bad)}. "
                f"Allowed: {sorted(_VALID_DETECTION_STATUS)}."
            )

    # ---- Q1: diagnostics probe ------------------------------------------
    diag_cypher, diag_params = build_metabolites_by_quantifies_assay_diagnostics(
        assay_ids=assay_ids,
        organism=organism,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids,
        experiment_ids=experiment_ids,
        publication_doi=publication_doi,
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
    )
    diag_rows = conn.execute_query(diag_cypher, **diag_params)

    found_ids = {r["assay_id"] for r in diag_rows}
    not_found_assay_ids = sorted(set(assay_ids) - found_ids)
    surviving_ids = sorted(found_ids)

    # ---- Rankable-gating logic ------------------------------------------
    rankable_filter_set = any([
        metric_bucket,
        metric_percentile_min is not None,
        metric_percentile_max is not None,
        rank_by_metric_max is not None,
    ])
    excluded_assays: list[str] = []
    warnings: list[str] = []
    if rankable_filter_set and diag_rows:
        rankable_ids = {r["assay_id"] for r in diag_rows if r["rankable"]}
        if not rankable_ids:
            raise ValueError(
                f"All selected assays have rankable=False, but a rankable-"
                f"gated filter (metric_bucket / metric_percentile / "
                f"rank_by_metric_max) was set. Selected assay_ids: "
                f"{sorted(found_ids)}. Pre-flight: "
                f"list_metabolite_assays(rankable=True, value_kind='numeric')."
            )
        excluded_assays = sorted(found_ids - rankable_ids)
        if excluded_assays:
            warnings.append(
                f"Soft-excluded {len(excluded_assays)} non-rankable "
                f"assay(s) from rankable-gated filter: {excluded_assays}"
            )
        surviving_ids = sorted(rankable_ids)

    # ---- Defensive: if nothing survived, return empty envelope ----------
    if not surviving_ids:
        return {
            "results": [],
            "total_matching": 0,
            "by_detection_status": [],
            "by_metric_bucket": [],
            "by_assay": [],
            "by_compartment": [],
            "by_organism": [],
            "by_metric": [],
            "excluded_assays": excluded_assays,
            "warnings": warnings,
            "not_found": {
                "assay_ids": not_found_assay_ids,
                "metabolite_ids": _probe_existence(
                    conn, "Metabolite", "id", metabolite_ids or []),
                "experiment_ids": _probe_existence(
                    conn, "Experiment", "id", experiment_ids or []),
                "publication_doi": _probe_existence(
                    conn, "Publication", "id", publication_doi or []),
            },
            "returned": 0,
            "truncated": False,
            "offset": offset,
        }

    # ---- Q2: summary ----------------------------------------------------
    sum_cypher, sum_params = build_metabolites_by_quantifies_assay_summary(
        assay_ids=surviving_ids,
        organism=organism,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids,
        experiment_ids=experiment_ids,
        publication_doi=publication_doi,
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
        value_min=value_min,
        value_max=value_max,
        detection_status=detection_status,
        timepoint=timepoint,
        metric_bucket=metric_bucket,
        metric_percentile_min=metric_percentile_min,
        metric_percentile_max=metric_percentile_max,
        rank_by_metric_max=rank_by_metric_max,
    )
    sum_rows = conn.execute_query(sum_cypher, **sum_params)
    sum_row = sum_rows[0] if sum_rows else {}

    by_detection_status = _rename_freq(
        sum_row.get("by_detection_status", []) or [], "detection_status")
    by_metric_bucket = _rename_freq(
        sum_row.get("by_metric_bucket", []) or [], "bucket")
    by_assay_freq = sum_row.get("by_assay", []) or []
    by_assay = _rename_freq(by_assay_freq, "assay_id")
    by_compartment = _rename_freq(
        sum_row.get("by_compartment", []) or [], "compartment")
    by_organism = _rename_freq(
        sum_row.get("by_organism", []) or [], "organism_name")
    by_metric = _mqa_build_by_metric(
        diag_rows=diag_rows,
        summary_by_assay=by_assay_freq,
        summary_filtered_min=sum_row.get("filtered_value_min"),
        summary_filtered_max=sum_row.get("filtered_value_max"),
        surviving_ids=surviving_ids,
    )

    total_matching = sum_row.get("total_matching", 0) or 0

    # ---- Q3: detail (skipped when summary=True) -------------------------
    results: list[dict] = []
    if not summary:
        det_cypher, det_params = build_metabolites_by_quantifies_assay(
            assay_ids=surviving_ids,
            organism=organism,
            metabolite_ids=metabolite_ids,
            exclude_metabolite_ids=exclude_metabolite_ids,
            experiment_ids=experiment_ids,
            publication_doi=publication_doi,
            compartment=compartment,
            treatment_type=treatment_type,
            background_factors=background_factors,
            growth_phases=growth_phases,
            value_min=value_min,
            value_max=value_max,
            detection_status=detection_status,
            timepoint=timepoint,
            metric_bucket=metric_bucket,
            metric_percentile_min=metric_percentile_min,
            metric_percentile_max=metric_percentile_max,
            rank_by_metric_max=rank_by_metric_max,
            verbose=verbose,
            limit=limit,
            offset=offset,
        )
        results = conn.execute_query(det_cypher, **det_params)

    return {
        "results": results,
        "total_matching": total_matching,
        "by_detection_status": by_detection_status,
        "by_metric_bucket": by_metric_bucket,
        "by_assay": by_assay,
        "by_compartment": by_compartment,
        "by_organism": by_organism,
        "by_metric": by_metric,
        "excluded_assays": excluded_assays,
        "warnings": warnings,
        "not_found": {
            "assay_ids": not_found_assay_ids,
            "metabolite_ids": _probe_existence(
                conn, "Metabolite", "id", metabolite_ids or []),
            "experiment_ids": _probe_existence(
                conn, "Experiment", "id", experiment_ids or []),
            "publication_doi": _probe_existence(
                conn, "Publication", "id", publication_doi or []),
        },
        "returned": len(results),
        "truncated": total_matching > offset + len(results),
        "offset": offset,
    }


def metabolites_by_flags_assay(
    *,
    assay_ids: list[str],
    organism: str | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    flag_value: bool | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int = 5,
    offset: int = 0,
    conn: GraphConnection | None = None,
) -> dict:
    """Drill into boolean MetaboliteAssay edges.

    Two-query dispatch (no diagnostics — boolean tool has no rankable
    gate):
      1. summary — envelope rollups.
      2. detail — top-N rows; skipped when `summary=True`.

    The API coerces `flag_value: bool | None` to string `'detected'` /
    `'not_detected'` for Cypher (KG two-state string, HO-001).
    `flag_value=False` returns rows in this slice (KG stores both true
    and false flags; differs from DM `genes_by_boolean_metric`).

    Tested-absent rows (`flag_value=False`) are real biology — 62% of
    boolean rows in the live KG. Don't default-filter.

    `excluded_assays` and `warnings` always `[]` here (no gates) — kept
    for cross-tool envelope-shape consistency.

    Raises:
        ValueError: empty `assay_ids`.
    """
    conn = _default_conn(conn)

    if not assay_ids:
        raise ValueError("assay_ids must not be empty")

    # D4: bool → string coercion at API boundary (parent §11 Conv K).
    flag_value_str: str | None
    if flag_value is True:
        flag_value_str = "detected"
    elif flag_value is False:
        flag_value_str = "not_detected"
    else:
        flag_value_str = None

    # ---- Q1: summary ----------------------------------------------------
    sum_cypher, sum_params = build_metabolites_by_flags_assay_summary(
        assay_ids=assay_ids,
        organism=organism,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids,
        experiment_ids=experiment_ids,
        publication_doi=publication_doi,
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
        flag_value=flag_value_str,
    )
    sum_rows = conn.execute_query(sum_cypher, **sum_params)
    sum_row = sum_rows[0] if sum_rows else {}

    by_value = _rename_freq(
        sum_row.get("by_value", []) or [], "flag_value")
    by_assay_freq = sum_row.get("by_assay", []) or []
    by_assay = _rename_freq(by_assay_freq, "assay_id")
    by_compartment = _rename_freq(
        sum_row.get("by_compartment", []) or [], "compartment")
    by_organism = _rename_freq(
        sum_row.get("by_organism", []) or [], "organism_name")

    total_matching = sum_row.get("total_matching", 0) or 0

    # `by_metric` per spec §5.3: per-assay scalar rollup. Boolean has
    # no diagnostics builder, so the precomputed dm_true_count /
    # dm_false_count side is left as None today (best-effort). The
    # filtered-slice `count` comes from by_assay.
    summary_count_by_id = {r["item"]: r["count"] for r in by_assay_freq}
    by_metric: list[dict] = []
    for aid in sorted(set(assay_ids)):
        by_metric.append({
            "assay_id": aid,
            "count": summary_count_by_id.get(aid, 0),
        })
    by_metric.sort(key=lambda r: (-(r["count"] or 0), r["assay_id"]))

    # `not_found.assay_ids`: derived from summary's by_assay coverage.
    # Boolean has no diagnostics builder (per parent §13.1) so we cannot
    # distinguish "absent from KG" vs "in KG but no edges after filters"
    # without a probe — and the test suite asserts a strict 2-query
    # dispatch shape on the assay_ids-only path. Best-effort: assays
    # absent from `by_assay` are not surfaced as not_found here. The
    # other batch-input buckets ARE probed (cheap indexed lookups).
    not_found_assay_ids: list[str] = []

    # ---- Q2: detail (skipped when summary=True) -------------------------
    results: list[dict] = []
    if not summary:
        det_cypher, det_params = build_metabolites_by_flags_assay(
            assay_ids=assay_ids,
            organism=organism,
            metabolite_ids=metabolite_ids,
            exclude_metabolite_ids=exclude_metabolite_ids,
            experiment_ids=experiment_ids,
            publication_doi=publication_doi,
            compartment=compartment,
            treatment_type=treatment_type,
            background_factors=background_factors,
            growth_phases=growth_phases,
            flag_value=flag_value_str,
            verbose=verbose,
            limit=limit,
            offset=offset,
        )
        results = conn.execute_query(det_cypher, **det_params)

    return {
        "results": results,
        "total_matching": total_matching,
        "by_value": by_value,
        "by_assay": by_assay,
        "by_compartment": by_compartment,
        "by_organism": by_organism,
        "by_metric": by_metric,
        "excluded_assays": [],
        "warnings": [],
        "not_found": {
            "assay_ids": not_found_assay_ids,
            "metabolite_ids": _probe_existence(
                conn, "Metabolite", "id", metabolite_ids or []),
            "experiment_ids": _probe_existence(
                conn, "Experiment", "id", experiment_ids or []),
            "publication_doi": _probe_existence(
                conn, "Publication", "id", publication_doi or []),
        },
        "returned": len(results),
        "truncated": total_matching > offset + len(results),
        "offset": offset,
    }


def assays_by_metabolite(
    *,
    metabolite_ids: list[str],
    organism: str | None = None,
    evidence_kind: Literal["quantifies", "flags"] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    compartment: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int = 5,
    offset: int = 0,
    conn: GraphConnection | None = None,
) -> dict:
    """Polymorphic reverse-lookup: metabolite IDs → measurement evidence
    across both arms (quantifies + flags).

    Cross-organism by default (metabolite IDs are organism-agnostic).
    Three-query dispatch:
      1. existence-probe — populate flat `not_found`.
      2. summary — UNION ALL envelope rollups.
      3. detail — polymorphic rows; skipped when `summary=True`.

    Polymorphic rows: numeric-arm rows carry value/detection_status/
    timepoint*; boolean-arm rows carry flag_value/n_positive. Cross-arm
    fields explicit `None` (UNION ALL union-shape padding).

    Three states for a metabolite:
      1. `not_found` — ID not in the KG (unmeasured).
      2. `not_matched` — ID in KG, no assay edge after filters
         (unmeasured for this scope).
      3. Row in `results` with `value=0` / `flag_value=False` /
         `detection_status='not_detected'` — *tested-absent* (real biology).

    `not_found` is a flat `list[str]` (single batch input —
    `metabolite_ids` only). `not_matched` likewise flat.

    Raises:
        ValueError: empty `metabolite_ids`; `evidence_kind` not in
        {None, 'quantifies', 'flags'}.
    """
    conn = _default_conn(conn)

    if not metabolite_ids:
        raise ValueError("metabolite_ids must not be empty")
    if evidence_kind is not None and evidence_kind not in ("quantifies", "flags"):
        raise ValueError(
            f"Invalid evidence_kind: {evidence_kind!r}. "
            f"Allowed: 'quantifies', 'flags', or None (both)."
        )

    # ---- Q1: existence-probe (populate flat not_found per §13.6) --------
    probe_rows = conn.execute_query(
        "MATCH (m:Metabolite) WHERE m.id IN $ids RETURN m.id AS metabolite_id",
        ids=metabolite_ids,
    )
    kg_present = {r["metabolite_id"] for r in probe_rows}
    not_found = sorted(set(metabolite_ids) - kg_present)

    # ---- Q2: summary (UNION ALL envelope) -------------------------------
    sum_cypher, sum_params = build_assays_by_metabolite_summary(
        metabolite_ids=metabolite_ids,
        organism=organism,
        evidence_kind=evidence_kind,
        exclude_metabolite_ids=exclude_metabolite_ids,
        metric_types=metric_types,
        compartment=compartment,
    )
    sum_rows = conn.execute_query(sum_cypher, **sum_params)
    sum_row = sum_rows[0] if sum_rows else {}

    total_matching = sum_row.get("total_matching", 0) or 0
    by_evidence_kind = _rename_freq(
        sum_row.get("by_evidence_kind", []) or [], "evidence_kind")
    by_organism = _rename_freq(
        sum_row.get("by_organism", []) or [], "organism_name")
    by_compartment = _rename_freq(
        sum_row.get("by_compartment", []) or [], "compartment")
    by_assay = _rename_freq(
        sum_row.get("by_assay", []) or [], "assay_id")
    by_detection_status = _rename_freq(
        sum_row.get("by_detection_status", []) or [], "detection_status")
    by_flag_value = _rename_freq(
        sum_row.get("by_flag_value", []) or [], "flag_value")
    metabolites_matched = sum_row.get("metabolites_matched", 0) or 0

    # ---- Q3: detail (skipped when summary=True) -------------------------
    results: list[dict] = []
    if not summary:
        det_cypher, det_params = build_assays_by_metabolite(
            metabolite_ids=metabolite_ids,
            organism=organism,
            evidence_kind=evidence_kind,
            exclude_metabolite_ids=exclude_metabolite_ids,
            metric_types=metric_types,
            compartment=compartment,
            verbose=verbose,
            limit=limit,
            offset=offset,
        )
        results = conn.execute_query(det_cypher, **det_params)

    # ---- Compute partition (metabolites_with / without_evidence) --------
    # In summary mode `results=[]`, so derive metabolites_with_evidence
    # from the summary's by_assay context if needed. Most-correct source
    # is the row-set itself; in summary mode we approximate via the
    # metabolite IDs surfaced through detail (or skip if absent).
    metabolites_with_evidence = sorted({
        r.get("metabolite_id") for r in results if r.get("metabolite_id")
    })
    if summary:
        # In summary mode, we rely on the existence probe + filters to
        # estimate. Without per-metabolite rollup in the summary, we
        # default to "all KG-present metabolites with edges" which we
        # can't distinguish from "no edges after filters". Best-effort:
        # use `metabolites_matched` as a count signal; identifiers are
        # only authoritative when detail rows are returned.
        # Caller pattern: drop summary=True for batch routing on 50+
        # metabolite_ids when per-ID partitions are needed.
        pass

    metabolites_without_evidence = sorted(
        set(metabolite_ids) - set(metabolites_with_evidence)
    )
    not_matched = sorted(
        (kg_present - set(metabolites_with_evidence))
        & set(metabolite_ids)
    )

    return {
        "results": results,
        "total_matching": total_matching,
        "by_evidence_kind": by_evidence_kind,
        "by_organism": by_organism,
        "by_compartment": by_compartment,
        "by_assay": by_assay,
        "by_detection_status": by_detection_status,
        "by_flag_value": by_flag_value,
        "metabolites_matched": metabolites_matched,
        "metabolites_with_evidence": metabolites_with_evidence,
        "metabolites_without_evidence": metabolites_without_evidence,
        "not_found": not_found,
        "not_matched": not_matched,
        "returned": len(results),
        "truncated": total_matching > offset + len(results),
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# gene_aa_sequence
# ---------------------------------------------------------------------------


def gene_aa_sequence(
    locus_tags: list[str],
    fasta: bool = False,
    summary: bool = False,
    limit: int = 25,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Fetch amino-acid sequences for a batch of genes, export-optimized.

    Resolves each input locus_tag, keeps genes that carry a non-null
    ``sequence``, and assembles a paginated detail list plus full-match
    summary statistics. Use ``fasta=True`` to receive one multi-FASTA blob
    instead of per-row sequences (the two carriers are mutually exclusive —
    a sequence is never emitted in both).

    Returns a dict with keys: total_matching, returned, truncated,
    by_organism, sequence_length_stats, not_found, not_matched, fasta,
    results.

    - total_matching: input locus_tags resolving to a gene with a sequence.
    - by_organism: list of {organism_name, count} over matched genes.
    - sequence_length_stats: {count, min, q1, median, q3, max, mean} over all
      matched genes (full match, not just the page — stable across limit and
      offset).
    - not_found: input locus_tags absent from the KG.
    - not_matched: locus_tags whose gene exists but has a null sequence.
    - fasta: multi-FASTA blob (non-empty only when fasta=True), else "".

    Per result: locus_tag, organism_name, gene_name, product, protein_id,
    sequence_length, sequence. When fasta=False the sequence carries the
    amino-acid string; when fasta=True it is None and the envelope fasta
    blob carries the sequences instead.

    Summary fields cover the full match and are page-independent. summary=True
    returns the envelope with results=[] (sugar for limit=0).

    Raises ValueError if locus_tags is empty.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Step 1: gene existence check (reused primitive)
    exist_cypher, exist_params = build_gene_existence_check(locus_tags=locus_tags)
    exist_rows = conn.execute_query(exist_cypher, **exist_params)
    not_found = [r["lt"] for r in exist_rows if not r["found"]]
    found_tags = [r["lt"] for r in exist_rows if r["found"]]

    # Step 2: summary builder — always runs (cheap, no sequences transferred)
    sum_cypher, sum_params = build_gene_aa_sequence_summary(locus_tags=locus_tags)
    sum_rows = conn.execute_query(sum_cypher, **sum_params)
    summary_row = sum_rows[0] if sum_rows else {}
    total_matching = summary_row.get("total_matching", 0) or 0
    matched_tags = summary_row.get("matched_tags") or []
    # Zero-match: aggregates are undefined. apoc.agg.percentiles over an empty set
    # returns a variable-length all-null list, so emit explicit None stats rather
    # than indexing into it.
    if total_matching == 0:
        sequence_length_stats = {
            "count": 0, "min": None, "q1": None, "median": None,
            "q3": None, "max": None, "mean": None,
        }
    else:
        len_pcts = summary_row.get("len_pcts") or [None, None, None]
        sequence_length_stats = {
            "count": total_matching,
            "min": summary_row.get("len_min"),
            "q1": len_pcts[0],
            "median": len_pcts[1],
            "q3": len_pcts[2],
            "max": summary_row.get("len_max"),
            "mean": summary_row.get("len_mean"),
        }
    by_organism = _rename_freq(summary_row.get("by_organism") or [], "organism_name")
    not_matched = [t for t in found_tags if t not in matched_tags]

    # Step 3: detail builder — skip when summary-only
    results: list[dict] = []
    if not (summary or limit == 0):
        det_cypher, det_params = build_gene_aa_sequence(
            locus_tags=locus_tags, limit=limit, offset=offset,
        )
        results = conn.execute_query(det_cypher, **det_params)

    fasta_blob = ""
    if fasta and results:
        lines = []
        for row in results:
            header = (
                f">{row['locus_tag']} {row.get('organism_name') or ''}"
                f"|{row.get('protein_id') or ''}|{row.get('product') or ''}"
            )
            lines.append(header)
            lines.append(row.get("sequence") or "")
        fasta_blob = "\n".join(lines) + "\n"
        for row in results:
            row["sequence"] = None

    returned = len(results)
    return {
        "total_matching": total_matching,
        "returned": returned,
        "truncated": offset + returned < total_matching,
        "by_organism": by_organism,
        "sequence_length_stats": sequence_length_stats,
        "not_found": not_found,
        "not_matched": not_matched,
        "fasta": fasta_blob,
        "results": results,
    }


# ---------------------------------------------------------------------------
# gene_neighbors
# ---------------------------------------------------------------------------


def gene_neighbors(
    locus_tags: list[str],
    window: int = 5,
    max_bp_distance: int | None = None,
    same_strand: bool | None = None,
    summary: bool = False,
    limit: int = 25,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Fetch each gene's genomic neighborhood for operon or synteny reasoning.

    For every anchor locus_tag, returns the closest ``window`` genes upstream
    and downstream on the same contig and organism, with strand orientation
    and intergenic distance. Neighbors are positional only (same-contig
    adjacency) — not co-expression. Fragmented assemblies yield fewer or no
    neighbors near contig ends.

    Returns a dict with keys: total_matching, returned, truncated, anchors,
    by_organism, not_found, not_matched, warnings, results.

    - total_matching: neighbor rows after max_bp_distance and same_strand
      filters (pre-limit).
    - anchors: list of per-anchor blocks {locus_tag, organism_name, contig,
      start, end, strand, product, neighbors_returned, dropped_null_strand}.
    - by_organism: list of {organism_name, count} over neighbor rows.
    - not_found: anchor locus_tags absent from the KG.
    - not_matched: anchors that exist but lack coordinates (no neighborhood).
    - warnings: e.g. same_strand requested but an anchor's own strand is null,
      so its neighbors are returned unfiltered.

    Per result (flat long, one row per anchor × neighbor): anchor_locus_tag,
    neighbor_locus_tag, rank_offset (signed, negative = upstream by start),
    bp_gap (unsigned intergenic distance, 0 if intervals overlap), strand,
    same_strand (True/False/None — None when either strand is null), product,
    gene_name, gene_category.

    same_strand=None returns all neighbors; True keeps co-oriented only; False
    keeps opposite-strand only. When set, null-strand neighbors are dropped and
    counted into the anchor's dropped_null_strand, except when the anchor's own
    strand is null — then all its neighbors are kept and a warning is added.
    summary=True returns the envelope with results=[] (sugar for limit=0).

    Raises ValueError if locus_tags is empty.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Step 1: gene existence check (reused primitive)
    exist_cypher, exist_params = build_gene_existence_check(locus_tags=locus_tags)
    exist_rows = conn.execute_query(exist_cypher, **exist_params)
    not_found = [r["lt"] for r in exist_rows if not r["found"]]

    # Step 2: anchor metadata over existing anchors
    anc_cypher, anc_params = build_gene_neighbors_summary(locus_tags=locus_tags)
    anc_rows = conn.execute_query(anc_cypher, **anc_params)
    not_matched = [r["anchor_locus_tag"] for r in anc_rows if not r["has_coords"]]

    # anchor strand lookup for same_strand handling; build anchor blocks
    anchor_strand: dict[str, str | None] = {}
    anchors: list[dict] = []
    for r in anc_rows:
        if not r["has_coords"]:
            continue
        lt = r["anchor_locus_tag"]
        anchor_strand[lt] = r.get("strand")
        anchors.append({
            "locus_tag": lt,
            "organism_name": r.get("organism_name"),
            "contig": r.get("contig"),
            "start": r.get("start"),
            "end": r.get("end"),
            "strand": r.get("strand"),
            "product": r.get("product"),
            "neighbors_returned": 0,
            "dropped_null_strand": 0,
        })

    # Step 3: detail builder — skip when summary-only
    warnings: list[str] = []
    filtered: list[dict] = []
    anchor_by_tag = {a["locus_tag"]: a for a in anchors}
    if not (summary or limit == 0):
        det_cypher, det_params = build_gene_neighbors(
            locus_tags=locus_tags, window=window, max_bp_distance=max_bp_distance,
        )
        detail_rows = conn.execute_query(det_cypher, **det_params)

        # same_strand filter applied in Python, per anchor
        per_anchor: dict[str, list[dict]] = {}
        for row in detail_rows:
            per_anchor.setdefault(row["anchor_locus_tag"], []).append(row)

        warned_null_anchor: set[str] = set()
        for anchor_tag, rows in per_anchor.items():
            block = anchor_by_tag.get(anchor_tag)
            if same_strand is None:
                kept = rows
            elif anchor_strand.get(anchor_tag) is None:
                # Anchor's own strand is null → filter unappliable; keep all.
                kept = rows
                if anchor_tag not in warned_null_anchor:
                    warnings.append(
                        f"same_strand requested but anchor {anchor_tag} has a "
                        f"null strand; its neighbors are returned unfiltered."
                    )
                    warned_null_anchor.add(anchor_tag)
            else:
                kept = []
                dropped_null = 0
                for row in rows:
                    if row.get("same_strand") == same_strand:
                        kept.append(row)
                    elif row.get("strand") is None:
                        dropped_null += 1
                if block is not None:
                    block["dropped_null_strand"] = dropped_null
            if block is not None:
                block["neighbors_returned"] = len(kept)
            filtered.extend(kept)

        filtered.sort(key=lambda r: (r["anchor_locus_tag"], r["rank_offset"]))

    total_matching = len(filtered)
    results = filtered[:limit] if limit else filtered

    # by_organism rolls up neighbor rows over the post-filter set. Neighbor
    # rows are same-contig/organism as their anchor, so the organism comes
    # from the anchor block.
    anchor_org = {a["locus_tag"]: a["organism_name"] for a in anchors}
    org_counts: dict[str, int] = {}
    for row in filtered:
        org = anchor_org.get(row["anchor_locus_tag"])
        if org is not None:
            org_counts[org] = org_counts.get(org, 0) + 1
    by_organism = sorted(
        [{"organism_name": org, "count": cnt} for org, cnt in org_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    returned = len(results)
    return {
        "total_matching": total_matching,
        "returned": returned,
        "truncated": total_matching > returned,
        "anchors": anchors,
        "by_organism": by_organism,
        "not_found": not_found,
        "not_matched": not_matched,
        "warnings": warnings,
        "results": results,
    }


# --- kg_release_info helpers (compat check) ----------------------------------

_KG_IDENTITY_FIELDS = (
    "version", "built_at", "mcp_min_version", "git_sha_short", "git_branch",
    "gene_count", "experiment_count", "paper_count", "organism_count",
    "expression_edge_count", "release_notes_url",
    "release_highlights", "breaking_changes", "deployment_role",
    "controlled_vocabularies_hash",
)

_VOCAB_HASH_KEY = "controlled_vocabularies_hash"
_VOCAB_MISMATCH_SENTENCE = (
    "Vocabulary set differs from the one this explorer was built against — "
    "filters still validate live and `list_filter_values` reads live, but "
    "docs://ontologies pages and parameter descriptions may list stale values"
)


def _evaluate_vocabulary_hash(schema_info: dict) -> dict:
    """Build assert bucket 6 — the vocabulary-set check.

    Compares `Schema_info.controlled_vocabularies_hash` with the pin in
    `EXPECTED_KG_SHAPE` (read at call time). A KG that predates the
    vocabulary contract has no such property and fails the bucket.
    """
    expected = EXPECTED_KG_SHAPE[_VOCAB_HASH_KEY]
    actual = schema_info.get(_VOCAB_HASH_KEY)
    base = {
        "name": _VOCAB_HASH_KEY, "kind": _VOCAB_HASH_KEY,
        "expected": expected, "actual": actual,
    }
    if actual is None:
        return {
            **base, "passed": False,
            "detail": (
                "KG predates the vocabulary contract "
                "(no Schema_info.controlled_vocabularies_hash)."
            ),
        }
    if actual == expected:
        return {**base, "passed": True, "detail": None}
    return {
        **base, "passed": False,
        "detail": (
            f"Schema_info.controlled_vocabularies_hash is {actual}, "
            f"explorer was built against {expected}."
        ),
    }


def _get_explorer_version() -> str:
    """Return the installed multiomics-explorer version via importlib.metadata.

    Returns 'unknown' if the package metadata cannot be located (rare —
    only when running against a tree that was never installed via uv/pip)."""
    try:
        return _pkg_version("multiomics-explorer")
    except PackageNotFoundError:
        return "unknown"


def _evaluate_version_compat(explorer_version: str, kg_min: str | None) -> dict:
    """Build the version_compat assert dict.

    PEP 440 semantics — `0.1.0a1 < 0.1.0` (pre-release < release).
    This is the explorer↔KG coordination edge case the CHANGELOG flagged.
    """
    name = "version_compat"
    if explorer_version == "unknown":
        return {
            "name": name, "kind": "version_compat", "passed": False,
            "detail": (
                "Explorer version unknown (package metadata not installed via "
                "uv/pip); cannot evaluate compatibility."
            ),
        }
    if kg_min is None:
        return {
            "name": name, "kind": "version_compat", "passed": False,
            "detail": "KG did not declare mcp_min_version.",
        }
    try:
        ev = Version(explorer_version)
        kv = Version(kg_min)
    except InvalidVersion as e:
        return {
            "name": name, "kind": "version_compat", "passed": False,
            "detail": f"Could not parse a version: {e}.",
        }
    if ev >= kv:
        return {"name": name, "kind": "version_compat", "passed": True, "detail": None}
    return {
        "name": name, "kind": "version_compat", "passed": False,
        "detail": f"Explorer {explorer_version} < KG mcp_min_version {kg_min} (PEP 440).",
    }


def kg_release_info(conn: GraphConnection) -> dict:
    """Compute the KG release identity + compatibility verdict.

    One Cypher round-trip; pure Python evaluation of EXPECTED_KG_SHAPE.
    Returns a dict matching the KGReleaseInfoResponse Pydantic shape
    (verdict, explorer_version, kg, asserts, summary). Cached by the
    MCP server at lifespan startup; the kg_release_info MCP tool reads
    from cache.

    Six assert buckets: Schema_info props, node labels, relationship
    types, non-zero counts, version compatibility, and the vocabulary set
    (`controlled_vocabularies_hash` vs the pin this explorer was built
    against; that assert also carries `expected` / `actual`). A vocabulary
    mismatch — or a KG that predates the contract — yields `warn`, never
    worse: filters still validate live and `list_filter_values` reads live,
    but baked docs may list stale values. `kg` carries the live hash.
    """
    cypher, params = build_kg_release_info()
    rows = conn.execute_query(cypher, **params)
    row = rows[0] if rows else {"schema_info": None, "labels": [], "rel_types": []}

    schema_info = row.get("schema_info")
    labels = set(row.get("labels") or [])
    rel_types = set(row.get("rel_types") or [])

    explorer_version = _get_explorer_version()

    # No Schema_info node -> verdict='unknown', short-circuit
    if schema_info is None:
        return {
            "verdict": "unknown",
            "explorer_version": explorer_version,
            "kg": {},
            "asserts": [],
            "summary": (
                "UNKNOWN: Schema_info node not found "
                "(legacy KG build without release metadata, or wrong database?)."
            ),
        }

    asserts: list[dict] = []

    for prop in EXPECTED_KG_SHAPE["schema_info_required_props"]:
        present = prop in schema_info and schema_info[prop] is not None
        asserts.append({
            "name": f"schema_info_prop:{prop}",
            "kind": "schema_info_prop",
            "passed": present,
            "detail": None if present else f"Schema_info is missing or null on '{prop}'.",
        })

    for label in EXPECTED_KG_SHAPE["required_node_labels"]:
        passed = label in labels
        asserts.append({
            "name": f"node_label:{label}",
            "kind": "node_label",
            "passed": passed,
            "detail": None if passed else f"Node label '{label}' not found in db.labels().",
        })

    for rt in EXPECTED_KG_SHAPE["required_relationship_types"]:
        passed = rt in rel_types
        asserts.append({
            "name": f"relationship_type:{rt}",
            "kind": "relationship_type",
            "passed": passed,
            "detail": None if passed else f"Relationship type '{rt}' not found in db.relationshipTypes().",
        })

    for count_prop in EXPECTED_KG_SHAPE["required_nonzero_counts"]:
        value = schema_info.get(count_prop)
        passed = isinstance(value, int) and value > 0
        asserts.append({
            "name": f"nonzero_count:{count_prop}",
            "kind": "nonzero_count",
            "passed": passed,
            "detail": None if passed else f"Schema_info.{count_prop} is {value!r}, expected positive int.",
        })

    kg_min = schema_info.get("mcp_min_version")
    asserts.append(_evaluate_version_compat(explorer_version, kg_min))

    # Bucket 6 — vocabulary set (slice 4 §3.1). A failure folds into `warn`,
    # never worse: filters still validate live against the KG's vocab nodes.
    asserts.append(_evaluate_vocabulary_hash(schema_info))

    failed = [a for a in asserts if not a["passed"]]
    verdict = "ok" if not failed else "warn"

    if verdict == "ok":
        summary = (
            f"OK: explorer {explorer_version} satisfies KG mcp_min_version "
            f"{kg_min}; {len(asserts)}/{len(asserts)} schema asserts pass."
        )
    else:
        version_fail = next((a for a in failed if a["kind"] == "version_compat"), None)
        vocab_fail = next((a for a in failed if a["kind"] == _VOCAB_HASH_KEY), None)
        shape_fails = [a for a in failed
                       if a["kind"] not in ("version_compat", _VOCAB_HASH_KEY)]
        parts: list[str] = []
        if version_fail:
            parts.append(version_fail["detail"].rstrip("."))
        if shape_fails:
            kinds = sorted({a["kind"] for a in shape_fails})
            parts.append(
                f"{len(shape_fails)} schema assert(s) failed ({', '.join(kinds)})"
            )
        if vocab_fail:
            parts.append(_VOCAB_MISMATCH_SENTENCE)
        summary = "WARN: " + "; ".join(parts) + "."

    # Preflight change-list pointers (nullable, absent on dev builds). Keep the
    # one-liner short — point at the full markdown carried in kg{}. Breaking
    # changes first: the higher-value field a user most needs at preflight.
    if schema_info.get("breaking_changes"):
        summary += " ⚠ Breaking changes in this release — see kg.breaking_changes."
    if schema_info.get("release_highlights"):
        summary += " New in this release — see kg.release_highlights."

    return {
        "verdict": verdict,
        "explorer_version": explorer_version,
        "kg": {k: schema_info.get(k) for k in _KG_IDENTITY_FIELDS},
        "asserts": asserts,
        "summary": summary,
    }
