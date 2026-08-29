"""Shared query builders for MCP tools, CLI, and tests.

Each builder returns a (cypher, params) tuple. The caller is responsible
for executing the query via GraphConnection.execute_query(cypher, **params).
"""

import re
from typing import Literal

from multiomics_explorer.kg.constants import two_state

# Ontology type configuration — the single registry driving every ontology
# builder: labels, edges, indexes, hierarchy walks, trust axes, row columns,
# term-side projections, facets and forward bridges.
#
# Per-entry keys (annotation-trust surface, 2026-08):
#   label / gene_rel / hierarchy_rels / fulltext_index  — graph names.
#   trust        — comparable trust axes: normalized axis name -> edge prop.
#                  Absent key = axis not carried. `rank_prop` is NOT an axis:
#                  it is the sort key for the one-edge-per-(gene, term) rebind.
#   compact_edge — materially-important edge categoricals: compact column,
#                  filterable, rolled up, auto-warned on `warn_values`.
#   verbose_edge — native trust detail, verbose only, never a filter. Entries
#                  are either a bare prop name (column == prop) or a
#                  (edge_prop, output_column) pair.
#   facet        — term-side facet ({prop, param}) bound on `t` after the walk.
#   term_compact / term_verbose         — search_ontology term columns.
#   term_details_compact / _verbose     — ontology_term_details (PR 3b).
#   leaf_attachment — leaf-mode most-specific-attachment predicate (TCDB).
#   bridges_out  — forward-only (rel, target_ontology, link_kind) triples.
#
# The registry declares SHAPE only. Values / descriptions / ranges / signals
# come from `ControlledVocabulary` at runtime (see build_vocab_values).
_TRUST_AXES_ORDER: tuple[str, ...] = ("sources", "evidence", "evidence_score", "tier")

# Trust-axis sets shared by several ontologies (Layer-B `sources` + `evidence`
# landed on all 14 functional gene-edge types in KG-SYNC-005).
_TRUST_SOURCES_EVIDENCE = {"sources": "sources", "evidence": "evidence"}
_TRUST_SOURCES_EVIDENCE_SCORE = {
    "sources": "sources", "evidence": "evidence",
    "evidence_score": "evidence_score",
}

ONTOLOGY_CONFIG = {
    "go_bp": {
        "label": "BiologicalProcess",
        "gene_rel": "Gene_involved_in_biological_process",
        "hierarchy_rels": [
            "Biological_process_is_a_biological_process",
            "Biological_process_part_of_biological_process",
        ],
        "fulltext_index": "biologicalProcessFullText",
        "trust": dict(_TRUST_SOURCES_EVIDENCE_SCORE),
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": ["direct_gene_count"],
        "term_details_verbose": "*",
    },
    "go_mf": {
        "label": "MolecularFunction",
        "gene_rel": "Gene_enables_molecular_function",
        "hierarchy_rels": [
            "Molecular_function_is_a_molecular_function",
            "Molecular_function_part_of_molecular_function",
        ],
        "fulltext_index": "molecularFunctionFullText",
        "trust": dict(_TRUST_SOURCES_EVIDENCE_SCORE),
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": ["direct_gene_count"],
        "term_details_verbose": "*",
    },
    "go_cc": {
        "label": "CellularComponent",
        "gene_rel": "Gene_located_in_cellular_component",
        "hierarchy_rels": [
            "Cellular_component_is_a_cellular_component",
            "Cellular_component_part_of_cellular_component",
        ],
        "fulltext_index": "cellularComponentFullText",
        "trust": dict(_TRUST_SOURCES_EVIDENCE_SCORE),
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": ["direct_gene_count"],
        "term_details_verbose": "*",
    },
    "ec": {
        "label": "EcNumber",
        "gene_rel": "Gene_catalyzes_ec_number",
        "hierarchy_rels": ["Ec_number_is_a_ec_number"],
        "fulltext_index": "ecNumberFullText",
        "trust": dict(_TRUST_SOURCES_EVIDENCE_SCORE),
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": ["direct_gene_count"],
        "term_details_verbose": "*",
    },
    "kegg": {
        "label": "KeggTerm",
        "gene_rel": "Gene_has_kegg_ko",
        "hierarchy_rels": ["Kegg_term_is_a_kegg_term"],
        "fulltext_index": "keggFullText",
        "discusses_rel": "Publication_discusses_kegg_pathway",
        "trust": dict(_TRUST_SOURCES_EVIDENCE),
        "term_compact": ["gene_count", "organism_count"],
        # reaction_count / metabolite_count live on pathway terms only
        # (strip rule: absent on KO / module rows).
        "term_details_compact": [
            "direct_gene_count", "reaction_count", "metabolite_count",
        ],
        "term_details_verbose": "*",
        "bridges_out": [
            ("Kegg_term_in_brite_category", "brite", "membership"),
        ],
    },
    "cog_category": {
        "label": "CogFunctionalCategory",
        "gene_rel": "Gene_in_cog_category",
        "hierarchy_rels": [],
        "fulltext_index": "cogCategoryFullText",
        "trust": dict(_TRUST_SOURCES_EVIDENCE),
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": ["code"],
        "term_details_verbose": "*",
    },
    "cyanorak_role": {
        "label": "CyanorakRole",
        "gene_rel": "Gene_has_cyanorak_role",
        "hierarchy_rels": ["Cyanorak_role_is_a_cyanorak_role"],
        "fulltext_index": "cyanorakRoleFullText",
        "trust": dict(_TRUST_SOURCES_EVIDENCE),
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": ["code", "direct_gene_count"],
        "term_details_verbose": "*",
    },
    "tigr_role": {
        # Two-level since the 2026-08-29 KG (subrole -> mainrole); mainroles
        # are slug ids (`tigr.role:energy_metabolism`), subroles numeric.
        "label": "TigrRole",
        "gene_rel": "Gene_has_tigr_role",
        "hierarchy_rels": ["Tigr_role_is_a_tigr_role"],
        "fulltext_index": "tigrRoleFullText",
        "trust": dict(_TRUST_SOURCES_EVIDENCE),
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": ["code", "direct_gene_count", "ncbifam_family_count"],
        "term_details_verbose": "*",
    },
    "pfam": {
        "label": "Pfam",
        "gene_rel": "Gene_has_pfam",
        "hierarchy_rels": ["Pfam_in_pfam_clan"],
        "fulltext_index": "pfamFullText",
        "parent_label": "PfamClan",
        "parent_fulltext_index": "pfamClanFullText",
        "trust": dict(_TRUST_SOURCES_EVIDENCE_SCORE),
        "term_compact": ["gene_count", "organism_count"],
        # `pfam_id` (spec §4) is not a Pfam node property in the KG-SYNC-005
        # baseline; `short_name` is the accession-side prop that exists.
        "term_details_compact": ["short_name"],
        "term_details_verbose": "*",
        "bridges_out": [
            ("Pfam_in_interpro_entry", "interpro", "membership"),
        ],
    },
    "brite": {
        "label": "BriteCategory",
        "gene_rel": "Gene_has_kegg_ko",
        "hierarchy_rels": ["Brite_category_is_a_brite_category"],
        "fulltext_index": "briteCategoryFullText",
        "bridge": {
            "node_label": "KeggTerm",
            "edge": "Kegg_term_in_brite_category",
        },
        # BRITE binds `r` on the Gene_has_kegg_ko edge, so it carries KEGG's
        # axes (spec §4: "(kegg's)").
        "trust": dict(_TRUST_SOURCES_EVIDENCE),
        "facet": {"prop": "tree", "param": "tree"},
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": ["tree", "tree_code"],
        "term_details_verbose": "*",
    },
    "tcdb": {
        "label": "TcdbFamily",
        "gene_rel": "Gene_has_tcdb_family",
        "hierarchy_rels": ["Tcdb_family_is_a_tcdb_family"],
        "fulltext_index": "tcdbFamilyFullText",
        "trust": {
            "sources": "sources", "evidence": "evidence",
            "evidence_score": "evidence_score", "tier": "tier",
            "rank_prop": "evidence_score",
        },
        "verbose_edge": [
            "confidence_score", "source_agreement", "pfam_support", "go_support",
            "identity", "qcov", "evalue", "consensus_n", "attachment_depth",
        ],
        # Leaf mode: the deepest surviving attachment. `include_superseded`
        # drops the predicate (spec §7.3).
        "leaf_attachment": {
            "prop": "attachment_depth",
            "value": "most_specific",
            "override_param": "include_superseded",
        },
        "term_compact": ["gene_count", "organism_count"],
        "term_verbose": ["superfamily", "metabolite_count"],
        "term_details_compact": [
            "tcdb_id", "tc_class_id", "direct_gene_count", "member_count",
            "superfamily", "metabolite_count",
        ],
        "term_details_verbose": "*",
        "bridges_out": [
            ("Tcdb_family_has_pfam_domain", "pfam", "composition"),
            ("Tcdb_family_involved_in_biological_process", "go_bp", "composition"),
            ("Tcdb_family_enables_molecular_function", "go_mf", "composition"),
            ("Tcdb_family_located_in_cellular_component", "go_cc", "composition"),
        ],
    },
    "cazy": {
        "label": "CazyFamily",
        "gene_rel": "Gene_has_cazy_family",
        "hierarchy_rels": ["Cazy_family_is_a_cazy_family"],
        "fulltext_index": "cazyFamilyFullText",
        "trust": dict(_TRUST_SOURCES_EVIDENCE_SCORE),
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": ["cazy_id", "direct_gene_count"],
        "term_details_verbose": "*",
    },
    "subcellular_localization": {
        "label": "SubcellularLocalization",
        "gene_rel": "Gene_has_subcellular_localization",
        "hierarchy_rels": [],
        "fulltext_index": "subcellularLocalizationFullText",
        # No trust axes — PSORTb carries a native scalar only.
        "verbose_edge": [("score", "localization_score")],
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": ["psortb_id"],
        "term_details_verbose": "*",
    },
    "signal_peptide_type": {
        "label": "SignalPeptideType",
        "gene_rel": "Gene_has_signal_peptide_type",
        "hierarchy_rels": [],
        "fulltext_index": "signalPeptideTypeFullText",
        "verbose_edge": [
            ("probability", "signal_peptide_probability"),
            ("cleavage_site", "signal_peptide_cleavage_site"),
            ("cleavage_probability", "signal_peptide_cleavage_probability"),
        ],
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": ["signalp_id"],
        "term_details_verbose": "*",
    },
    "interpro": {
        "label": "InterproEntry",
        "gene_rel": "Gene_has_interpro_entry",
        "hierarchy_rels": ["Interpro_entry_is_a_interpro_entry"],
        "fulltext_index": "interproEntryFullText",
        "trust": dict(_TRUST_SOURCES_EVIDENCE),
        "verbose_edge": [
            "libraries", "evalue_library", "evalue", "match_count",
            "start", "end",
        ],
        "facet": {"prop": "interpro_type", "param": "interpro_type"},
        "term_compact": ["gene_count", "organism_count"],
        "term_details_compact": [
            "interpro_id", "interpro_type", "direct_gene_count", "member_count",
        ],
        "term_details_verbose": "*",
        "bridges_out": [
            ("Interpro_entry_related_to_ec_number", "ec", "router"),
            ("Interpro_entry_related_to_cazy_family", "cazy", "router"),
        ],
    },
    "ncbifam": {
        "label": "NcbifamFamily",
        "gene_rel": "Gene_has_ncbifam_family",
        "hierarchy_rels": [],
        "fulltext_index": "ncbifamFamilyFullText",
        "trust": dict(_TRUST_SOURCES_EVIDENCE),
        "verbose_edge": ["evalue", "bit_score", "start", "end"],
        "term_compact": ["gene_count", "organism_count"],
        "term_verbose": ["family_type", "gene_symbol"],
        "term_details_compact": ["ncbifam_id", "family_type", "gene_symbol"],
        "term_details_verbose": "*",
        "bridges_out": [
            ("Ncbifam_family_in_interpro_entry", "interpro", "membership"),
            # JCVI TIGRFAMs 15.0 role archive, family -> role; read outward
            # only -- the KG asserts a gene role from it solely for
            # equivalog families.
            ("Ncbifam_family_has_tigr_role", "tigr_role", "router"),
        ],
    },
    "merops": {
        "label": "MeropsFamily",
        "gene_rel": "Gene_has_merops_family",
        "hierarchy_rels": ["Merops_family_is_a_merops_family"],
        "fulltext_index": "meropsFamilyFullText",
        "trust": {
            "sources": "sources", "evidence": "evidence",
            "evidence_score": "evidence_score", "tier": "tier",
            "rank_prop": "confidence_score",
        },
        "compact_edge": {
            "call_class": {
                "prop": "call_class",
                "warn_values": ["nonpeptidase_homolog"],
            },
        },
        "verbose_edge": [
            "confidence_score", "pfam_support", "best_hit_kind", "identity",
            "qcov", "evalue", "consensus_n", "best_hit_id",
        ],
        "term_compact": ["gene_count", "organism_count"],
        "term_verbose": ["family_class", "catalytic_type", "peptidase_gene_count"],
        "term_details_compact": [
            "merops_id", "family_class", "catalytic_type", "peptidase_gene_count",
            "peptidase_organism_count", "direct_gene_count", "member_count",
            "cleavage_summary", "cleavage_p1_residues", "known_cleavage_count",
        ],
        "term_details_verbose": "*",
        "bridges_out": [
            ("Merops_family_has_pfam_domain", "pfam", "composition"),
        ],
    },
}

# Term-side columns every ontology row already projects from `t`. A facet whose
# prop is one of these does not become an extra owned row column (BRITE's
# `tree` is already a first-class row column; InterPro's `interpro_type` is not).
_STANDARD_TERM_ROW_COLUMNS: frozenset[str] = frozenset({"tree", "tree_code"})

# param name -> (owning ontology key, node prop). Generated from the registry so
# a new facet is one config entry (spec §7, design §7).
_FACET_PARAMS: dict[str, tuple[str, str]] = {
    cfg["facet"]["param"]: (key, cfg["facet"]["prop"])
    for key, cfg in ONTOLOGY_CONFIG.items()
    if cfg.get("facet")
}

# Trust filter params -> the config axis they need. `call_class` is not an
# axis: it is declared per-ontology under `compact_edge`.
TRUST_FILTER_AXIS: dict[str, str] = {
    "sources": "sources",
    "evidence": "evidence",
    "max_tier": "tier",
    "min_evidence_score": "evidence_score",
}
# Pre-3b private name — kept as an alias for one release (spec §13 ii).
_TRUST_FILTER_AXIS = TRUST_FILTER_AXIS

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(value: str, what: str) -> str:
    """Guard a graph identifier that cannot be passed as a `$param`.

    Labels, relationship types and property names are structural in Cypher.
    Every caller sources them from ONTOLOGY_CONFIG or ControlledVocabulary,
    but the guard keeps an unexpected value from reaching the query text.
    """
    if not _IDENTIFIER_RE.match(value or ""):
        raise ValueError(f"Invalid {what} '{value}'.")
    return value


def verbose_edge_pairs(cfg: dict) -> list[tuple[str, str]]:
    """Normalize `verbose_edge` entries to (edge_prop, output_column) pairs.

    A bare string means column == prop; a 2-tuple means (prop, column) —
    needed for PSORTb `score -> localization_score` and the three SignalP
    columns, which keep their existing prefixed names (design §1).
    """
    pairs: list[tuple[str, str]] = []
    for entry in cfg.get("verbose_edge") or []:
        if isinstance(entry, str):
            pairs.append((entry, entry))
        else:
            prop, column = entry
            pairs.append((prop, column))
    return pairs


# Pre-3b private name — kept as an alias for one release (spec §13 ii).
_verbose_edge_pairs = verbose_edge_pairs


def _ontology_cfg(ontology: str) -> dict:
    """Look up an ONTOLOGY_CONFIG entry, raising the standard ValueError."""
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(
            f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}"
        )
    return ONTOLOGY_CONFIG[ontology]


def ontology_trust_axes(ontology: str) -> list[str]:
    """Comparable trust axes the ontology's gene edge carries.

    Returns a subset of ('sources', 'evidence', 'evidence_score', 'tier') in
    that canonical order — never `rank_prop`, which is a sort key, not an axis.
    Drives the envelope `trust_axes` key and the unsupported-axis message.
    """
    cfg = _ontology_cfg(ontology)
    trust = cfg.get("trust") or {}
    return [axis for axis in _TRUST_AXES_ORDER if axis in trust]


def ontology_row_columns(
    ontology: str, verbose: bool, *, force_trust_axes: bool = False,
) -> list[str]:
    """Row columns a gene × term row of `ontology` OWNS.

    Compact = comparable + materially-important: `evidence` (the single
    compact trust column, spec §0), the ontology's facet column when it is not
    already a standard term column (InterPro `interpro_type`), and every
    `compact_edge` categorical (MEROPS `call_class`).

    Verbose appends the remaining trust axes (`sources`, `evidence_score`,
    `tier` — whichever the edge carries) and then the native detail from
    `verbose_edge`, under its output-column names.

    `force_trust_axes` adds the remaining trust axes to a *compact* column
    set without the native detail. The gene×term detail builders project
    that set unconditionally so the envelope rollups (`by_tier`,
    `by_sources`, `evidence_score_stats`) and the tier-null auto-warning
    have something to read; the api layer then strips the extra axes off
    compact rows, which stay byte-identical.

    The api layer strips every column an ontology does not own; owned-but-null
    columns stay (there `null` is information — design §3).
    """
    cfg = _ontology_cfg(ontology)
    trust = cfg.get("trust") or {}

    columns: list[str] = []
    if "evidence" in trust:
        columns.append("evidence")
    facet = cfg.get("facet")
    if facet and facet["prop"] not in _STANDARD_TERM_ROW_COLUMNS:
        columns.append(facet["prop"])
    columns.extend(cfg.get("compact_edge") or {})
    if not verbose and not force_trust_axes:
        return columns

    for axis in ("sources", "evidence_score", "tier"):
        if axis in trust:
            columns.append(axis)
    if not verbose:
        return columns
    columns.extend(column for _prop, column in _verbose_edge_pairs(cfg))
    return columns


def ontology_edge_row_columns() -> frozenset[str]:
    """Every gene×term row column sourced from the gene→term *edge*.

    Trust axes, `compact_edge` categoricals and `verbose_edge` native
    detail — but never a facet, which is a term-node property. Consumers
    that treat a row as a *term* fact (enrichment's TERM2GENE passthrough)
    must drop these: the first gene's edge is not a property of the term.
    """
    columns: set[str] = set()
    for cfg in ONTOLOGY_CONFIG.values():
        columns.update(cfg.get("trust") or {})
        columns.update(cfg.get("compact_edge") or {})
        columns.update(column for _prop, column in _verbose_edge_pairs(cfg))
    columns.discard("rank_prop")
    return frozenset(columns)


def build_trust_filter_clause(
    ontology: str,
    *,
    sources: list[str] | None = None,
    evidence: list[str] | None = None,
    max_tier: int | None = None,
    min_evidence_score: float | None = None,
    call_class: list[str] | None = None,
    rel_var: str = "r",
) -> tuple[str, dict]:
    """Build the trust WHERE fragment bound on the gene→leaf rel var.

    Returns a bare conjunction (no leading `WHERE` / `AND`) plus its params, so
    callers splice it into whichever WHERE the gene→leaf MATCH already has.
    Empty string + empty params when nothing is filtered — defaults never
    filter on trust (design §1 ground rule 1).

    Clause forms (spec §7.1):
      sources            any(s IN $sources WHERE s IN r.sources)
      evidence           r.evidence IN $evidence
      max_tier           (r.tier <= $max_tier OR r.tier IS NULL)   — keeps the
                         tier-null bucket (TCDB eggNOG-only edges)
      min_evidence_score r.evidence_score >= $min_evidence_score
      call_class         r.call_class IN $call_class

    Raises ValueError naming the ontology's axes when an axis the ontology does
    not carry is filtered on.
    """
    cfg = _ontology_cfg(ontology)
    trust = cfg.get("trust") or {}
    compact_edge = cfg.get("compact_edge") or {}
    axes = ontology_trust_axes(ontology)

    def _unsupported(param: str) -> ValueError:
        carried = ", ".join(axes + sorted(compact_edge)) or "none"
        return ValueError(
            f"Filter '{param}' is not supported for ontology '{ontology}'. "
            f"{ontology} carries: {carried}. "
            f"Discover the per-ontology axes with "
            f"list_filter_values(filter_type='trust_axes')."
        )

    parts: list[str] = []
    params: dict = {}

    requested = {
        "sources": sources, "evidence": evidence, "max_tier": max_tier,
        "min_evidence_score": min_evidence_score,
    }
    for param, value in requested.items():
        if value is None:
            continue
        axis = _TRUST_FILTER_AXIS[param]
        if axis not in trust:
            raise _unsupported(param)
        prop = _safe_identifier(trust[axis], "trust property")
        if param == "sources":
            parts.append(f"any(s IN $sources WHERE s IN {rel_var}.{prop})")
        elif param == "evidence":
            parts.append(f"{rel_var}.{prop} IN $evidence")
        elif param == "max_tier":
            parts.append(
                f"({rel_var}.{prop} <= $max_tier OR {rel_var}.{prop} IS NULL)"
            )
        else:
            parts.append(f"{rel_var}.{prop} >= $min_evidence_score")
        params[param] = value

    if call_class is not None:
        if "call_class" not in compact_edge:
            raise _unsupported("call_class")
        prop = _safe_identifier(
            compact_edge["call_class"]["prop"], "compact_edge property"
        )
        parts.append(f"{rel_var}.{prop} IN $call_class")
        params["call_class"] = call_class

    return " AND ".join(parts), params


def _resolve_facet(
    ontology: str,
    *,
    tree: str | None = None,
    interpro_type: str | None = None,
) -> tuple[str, str, str] | None:
    """Validate the facet params and return (prop, param, value) or None.

    Facets are term-side node properties declared per ontology under `facet`
    and bound on `t` AFTER the hierarchy walk. Passing a facet param to an
    ontology that does not own it raises ValueError.
    """
    requested = {"tree": tree, "interpro_type": interpro_type}
    resolved: tuple[str, str, str] | None = None
    for param, value in requested.items():
        if value is None:
            continue
        owner, prop = _FACET_PARAMS[param]
        if ontology != owner:
            raise ValueError(
                f"{param} filter is only valid for ontology='{owner}'"
            )
        resolved = (prop, param, value)
    return resolved


def _ontology_row_return_cypher(
    ontology: str, verbose: bool, *, rel_var: str = "r",
    force_trust_axes: bool = False,
) -> str:
    """Comma-prefixed RETURN fragment projecting `ontology_row_columns`.

    Trust axes / compact_edge / verbose_edge columns come from the gene→leaf
    relationship (or, on the one-edge rebind, from the best-edge map — the
    `r.<prop>` access syntax is identical for both). The facet column comes
    from the term (`t.interpro_type`). Empty string when the ontology owns no
    row columns in this mode.
    """
    cfg = _ontology_cfg(ontology)
    trust = cfg.get("trust") or {}
    columns = ontology_row_columns(
        ontology, verbose, force_trust_axes=force_trust_axes,
    )
    if not columns:
        return ""

    facet = cfg.get("facet")
    facet_prop = facet["prop"] if facet else None
    compact_edge = cfg.get("compact_edge") or {}
    verbose_props = {column: prop for prop, column in _verbose_edge_pairs(cfg)}

    parts: list[str] = []
    for column in columns:
        if column == facet_prop:
            parts.append(f"t.{column} AS {column}")
        elif column in trust:
            parts.append(f"{rel_var}.{trust[column]} AS {column}")
        elif column in compact_edge:
            parts.append(f"{rel_var}.{compact_edge[column]['prop']} AS {column}")
        else:
            parts.append(f"{rel_var}.{verbose_props[column]} AS {column}")
    return ",\n       " + ",\n       ".join(parts)


def _ontology_row_edge_props(
    ontology: str, verbose: bool, *, force_trust_axes: bool = False,
) -> list[str]:
    """Edge props the row columns need, for the best-edge rebind map."""
    cfg = _ontology_cfg(ontology)
    trust = cfg.get("trust") or {}
    compact_edge = cfg.get("compact_edge") or {}
    verbose_props = {column: prop for prop, column in _verbose_edge_pairs(cfg)}
    facet = cfg.get("facet")
    facet_prop = facet["prop"] if facet else None

    props: list[str] = []
    for column in ontology_row_columns(
        ontology, verbose, force_trust_axes=force_trust_axes,
    ):
        if column == facet_prop:
            continue
        if column in trust:
            props.append(trust[column])
        elif column in compact_edge:
            props.append(compact_edge[column]["prop"])
        else:
            props.append(verbose_props[column])
    return props


def _best_edge_rank_key(cfg: dict) -> str:
    """Sort key for the one-edge-per-(gene, term) rebind.

    `rank_prop` when the ontology declares one (TCDB `evidence_score`, MEROPS
    `confidence_score`); else `evidence_score` when the edge carries it; else
    the attachment's own level, i.e. spec §3.1's "most specific attachment"
    tiebreak. Never an e-value or bit score — those are native scalars whose
    direction differs (design §1).
    """
    trust = cfg.get("trust") or {}
    if trust.get("rank_prop"):
        return trust["rank_prop"]
    if "evidence_score" in trust:
        return trust["evidence_score"]
    return "attachment_level"


def _uses_best_edge_rebind(
    ontology: str, verbose: bool, *, force_trust_axes: bool = False,
) -> bool:
    """True when a rollup row needs the one-edge-per-(gene, term) rebind.

    Hierarchical ontologies only: a rollup row's `t` is an ancestor reachable
    through several gene edges, so `RETURN DISTINCT ... r.*` would emit one row
    per edge (the latent PSORTb-era duplication). Flat ontologies have exactly
    one (gene, term) edge and keep the direct OPTIONAL MATCH.
    """
    cfg = _ontology_cfg(ontology)
    return bool(cfg["hierarchy_rels"]) and bool(
        ontology_row_columns(ontology, verbose, force_trust_axes=force_trust_axes)
    )


def _best_edge_rebind_cypher(
    ontology: str,
    verbose: bool,
    *,
    trust_frag: str = "",
    distinct_head: str = "WITH DISTINCT t, g",
    force_trust_axes: bool = False,
) -> str:
    """Cypher for the one-edge-per-(gene, term) rebind (spec §7.2).

    Collects every gene edge that reaches `t` (leaf or ancestor), keeps the
    best one by the ontology's rank key (ties → deepest attachment), and
    rebinds it as `r` — a map whose
    `r.<prop>` accesses read exactly like the relationship's.

    `trust_frag` is the same trust conjunction the gene→leaf MATCH carries,
    rebuilt on `r2`: an edge the filter removed must not come back as the
    row's "best" one (a `max_tier=2` row may never report `tier=3`).
    """
    cfg = _ontology_cfg(ontology)
    label = cfg["label"]
    gene_rel = cfg["gene_rel"]
    rank_key = _best_edge_rank_key(cfg)

    bridge = cfg.get("bridge")
    if bridge:
        edge_pattern = (
            f"(g)-[r2:{gene_rel}]->(:{bridge['node_label']})"
            f"-[:{bridge['edge']}]->(l2:{label})"
        )
    else:
        edge_pattern = f"(g)-[r2:{gene_rel}]->(l2:{label})"

    rel_union = "|".join(cfg["hierarchy_rels"])
    depth = "*0..1" if cfg.get("parent_label") else "*0.."
    walk_pattern = f"-[:{rel_union}{depth}]->(t)"

    row_props = _ontology_row_edge_props(
        ontology, verbose, force_trust_axes=force_trust_axes,
    )
    entries = [f"{prop}: r2.{prop}" for prop in row_props]
    if rank_key != "attachment_level" and rank_key not in row_props:
        entries.append(f"{rank_key}: r2.{rank_key}")
    # Secondary key (backlog 2.1): equal primary scores pick the deepest
    # attachment (higher `level` = more specific), so a rollup row never
    # reports a `superseded` ancestor edge over a most-specific descendant
    # with the same score. Levels are always in the map.
    entries.append("attachment_level: l2.level")
    edge_map = "{" + ", ".join(entries) + "}"
    trust_where = f"            WHERE {trust_frag}\n" if trust_frag else ""
    sort_keys = (
        "['attachment_level']" if rank_key == "attachment_level"
        else f"['{rank_key}', 'attachment_level']"
    )

    return (
        f"{distinct_head}\n"
        f"WITH t, g, [{edge_pattern}{walk_pattern}\n"
        f"{trust_where}"
        f"            | {edge_map}] AS edges\n"
        f"WITH t, g, head(apoc.coll.sortMulti(edges, {sort_keys})) AS r\n"
    )


def build_vocab_values(*, applies_to: str, prop: str) -> tuple[str, dict]:
    """Read one `ControlledVocabulary` node (spec §7.6).

    `ControlledVocabulary` owns values / descriptions / ranges; the registry
    owns shape. Callers cache per process and fall back to
    `build_vocab_pivot_values` (plus a warning) when the node is missing.

    `value_descriptions` (KG B1, 2026-08-29) is a list parallel to `values`
    carrying per-value text; absent on nodes that predate it.

    RETURN keys: values, value_descriptions, description, value_type, sparse,
    min_value, max_value.
    """
    cypher = (
        "MATCH (v:ControlledVocabulary "
        "{applies_to: $applies_to, property: $prop})\n"
        "RETURN v.values AS values,\n"
        "       v.value_descriptions AS value_descriptions,\n"
        "       v.description AS description,\n"
        "       v.value_type AS value_type, v.sparse AS sparse,\n"
        "       v.min_value AS min_value, v.max_value AS max_value"
    )
    return cypher, {"applies_to": applies_to, "prop": prop}


def build_vocab_pivot_values(
    *, applies_to: str, prop: str, kind: Literal["edge", "node"],
) -> tuple[str, dict]:
    """Derive a value set from the graph when the vocabulary node is missing.

    `applies_to` is a relationship type (`kind='edge'`) or a node label
    (`kind='node'`); both are structural in Cypher and cannot be `$param`s, so
    they are identifier-guarded instead.

    RETURN keys: value.
    """
    prop = _safe_identifier(prop, "property name")
    if kind == "edge":
        rel_type = _safe_identifier(applies_to, "relationship type")
        cypher = (
            f"MATCH ()-[r:{rel_type}]->()\n"
            f"RETURN DISTINCT r.{prop} AS value\n"
            "ORDER BY value"
        )
    elif kind == "node":
        label = _safe_identifier(applies_to, "node label")
        cypher = (
            f"MATCH (n:{label})\n"
            f"RETURN DISTINCT n.{prop} AS value\n"
            "ORDER BY value"
        )
    else:
        raise ValueError(f"kind must be 'edge' or 'node', got {kind!r}")
    return cypher, {}


def build_evidence_score_signals(
    *, edge_types: list[str],
) -> tuple[str, dict]:
    """Read the `evidence_score` signal list per edge type (spec §7.6).

    Surfaced as the envelope `evidence_score_signals` whenever
    `min_evidence_score` is applied, so a cutoff says which signals it fired on.

    RETURN keys: edge_type, signals, signal_count.
    """
    cypher = (
        "MATCH (v:ControlledVocabulary)\n"
        "WHERE v.applies_to IN $edge_types AND v.property = 'evidence_score'\n"
        "RETURN v.applies_to AS edge_type, v.signals AS signals,\n"
        "       v.signal_count AS signal_count\n"
        "ORDER BY edge_type"
    )
    return cypher, {"edge_types": edge_types}


def _hierarchy_walk(
    ontology: str,
    direction: Literal["up", "down"],
    root_label: str | None = None,
) -> dict:
    """Return Cypher fragments for ontology hierarchy walks.

    Consumed by genes_by_ontology builders and (post-refactor)
    ontology_landscape. Dispatches on ONTOLOGY_CONFIG + known special
    cases (Pfam cross-label, flat ontologies).

    Args:
        ontology: one of ALL_ONTOLOGIES.
        direction: 'up' = gene → leaf → ancestor at target level.
                   'down' = root-at-input → descendants → genes.
        root_label: used only when ontology='pfam' + direction='down';
                    distinguishes Pfam root (no walk) vs PfamClan root
                    (walk down via Pfam_in_pfam_clan).

    Returns:
        dict with keys:
          - leaf_label: str — label for the gene-bound node.
          - gene_rel: str — relationship from Gene to leaf.
          - rel_union: str — '|'.join(hierarchy_rels) (empty for flat).
          - bind_up: str — Cypher for gene→leaf binding (direction=up).
          - walk_up: str — Cypher for leaf→ancestor walk (direction=up).
          - walk_down: str — Cypher for root→leaf walk (direction=down).
    """
    if direction not in ("up", "down"):
        raise ValueError(
            f"direction must be 'up' or 'down', got '{direction}'"
        )
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(
            f"Invalid ontology '{ontology}'. "
            f"Valid: {sorted(ONTOLOGY_CONFIG)}"
        )

    cfg = ONTOLOGY_CONFIG[ontology]
    leaf_label = cfg["label"]
    gene_rel = cfg["gene_rel"]
    hierarchy_rels = cfg["hierarchy_rels"]
    rel_union = "|".join(hierarchy_rels)

    # --- Pfam: cross-label two-level ontology ---
    if ontology == "pfam":
        bind_up = (
            f"MATCH (g:Gene {{organism_name: $org}})"
            f"-[r:{gene_rel}]->(leaf:Pfam)"
        )
        # *0..1 because Pfam.level=1 (t=leaf) OR PfamClan.level=0 (t=clan)
        walk_up = (
            "MATCH (leaf)-[:Pfam_in_pfam_clan*0..1]->(t)\n"
            "WHERE t:Pfam OR t:PfamClan"
        )
        if direction == "up":
            # Parenthesize the label guard so downstream callers can safely
            # append `AND ...` without altering operator precedence.
            walk_up_safe = (
                "MATCH (leaf)-[:Pfam_in_pfam_clan*0..1]->(t)\n"
                "WHERE (t:Pfam OR t:PfamClan)"
            )
            return {
                "leaf_label": leaf_label,
                "gene_rel": gene_rel,
                "rel_union": "Pfam_in_pfam_clan",
                "bind_up": bind_up,
                "walk_up": walk_up_safe,
                "walk_down": "",
            }
        # direction == "down"
        if root_label == "PfamClan":
            walk_down = (
                "MATCH (t:PfamClan)<-[:Pfam_in_pfam_clan]-(leaf:Pfam)"
            )
        elif root_label == "Pfam":
            # Pfam root has no descendants in this 2-level ontology
            walk_down = ""
        else:
            raise ValueError(
                f"For ontology='pfam' direction='down', root_label must "
                f"be 'Pfam' or 'PfamClan', got {root_label!r}"
            )
        return {
            "leaf_label": leaf_label,
            "gene_rel": gene_rel,
            "rel_union": "Pfam_in_pfam_clan",
            "bind_up": bind_up,
            "walk_up": walk_up,
            "walk_down": walk_down,
        }

    # --- Bridge ontologies (2-hop gene → intermediate → leaf) ---
    bridge = cfg.get("bridge")
    if bridge:
        bridge_edge = bridge["edge"]
        bridge_node = bridge["node_label"]
        bind_up = (
            f"MATCH (g:Gene {{organism_name: $org}})"
            f"-[r:{gene_rel}]->(ko:{bridge_node})"
            f"-[:{bridge_edge}]->(leaf:{leaf_label})"
        )
        walk_up = f"MATCH (leaf)-[:{rel_union}*0..]->(t:{leaf_label})"
        walk_down = (
            f"MATCH (t:{leaf_label})<-[:{rel_union}*0..]-(leaf:{leaf_label})"
        )
        return {
            "leaf_label": leaf_label,
            "gene_rel": gene_rel,
            "rel_union": rel_union,
            "bind_up": bind_up,
            "walk_up": walk_up,
            "walk_down": walk_down,
        }

    # --- Flat ontologies (no hierarchy_rels): t = leaf ---
    if not hierarchy_rels:
        bind_up = (
            f"MATCH (g:Gene {{organism_name: $org}})"
            f"-[r:{gene_rel}]->(t:{leaf_label})"
        )
        return {
            "leaf_label": leaf_label,
            "gene_rel": gene_rel,
            "rel_union": "",
            "bind_up": bind_up,
            "walk_up": "",
            "walk_down": "",
        }

    # --- Single-label tree ontologies (GO BP/MF/CC, EC, KEGG, CyanoRak) ---
    bind_up = (
        f"MATCH (g:Gene {{organism_name: $org}})"
        f"-[r:{gene_rel}]->(leaf:{leaf_label})"
    )
    walk_up = f"MATCH (leaf)-[:{rel_union}*0..]->(t:{leaf_label})"
    walk_down = (
        f"MATCH (t:{leaf_label})<-[:{rel_union}*0..]-(leaf:{leaf_label})"
    )
    return {
        "leaf_label": leaf_label,
        "gene_rel": gene_rel,
        "rel_union": rel_union,
        "bind_up": bind_up,
        "walk_up": walk_up,
        "walk_down": walk_down,
    }


def build_resolve_gene(
    *, identifier: str, organism: str | None = None
) -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene)\n"
        "WHERE (\n"
        "    toLower(g.locus_tag) = toLower($identifier)\n"
        "    OR toLower(g.gene_name) = toLower($identifier)\n"
        "    OR ANY(id IN g.all_identifiers WHERE toLower(id) = toLower($identifier))\n"
        "  )\n"
        "  AND ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_name) CONTAINS word))\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_name AS organism_name\n"
        "ORDER BY g.organism_name, g.locus_tag"
    )
    return cypher, {"identifier": identifier, "organism": organism}


def _genes_by_function_filter_clause() -> str:
    """Return the shared WHERE filter expression for genes_by_function builders."""
    return (
        "($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_name) CONTAINS word))\n"
        "  AND ($min_quality = 0 OR g.annotation_quality >= $min_quality)\n"
        "  AND ($category IS NULL OR g.gene_category = $category)"
    )


def _genes_by_function_params(
    *,
    search_text: str,
    organism: str | None = None,
    category: str | None = None,
    min_quality: int = 0,
) -> dict:
    return {
        "search_text": search_text, "organism": organism,
        "category": category, "min_quality": min_quality,
    }


def build_genes_by_function_summary(
    *,
    search_text: str,
    organism: str | None = None,
    category: str | None = None,
    min_quality: int = 0,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_function.

    Uses conditional counting to compute total_search_hits (fulltext hits
    before post-filters) and total_matching (after filters) in a single pass.

    RETURN keys: total_search_hits, total_matching, by_organism, by_category,
    score_max, score_median.
    """
    filt = _genes_by_function_filter_clause()
    cypher = (
        "CALL db.index.fulltext.queryNodes('geneFullText', $search_text)\n"
        "YIELD node AS g, score\n"
        f"WITH g, score,\n"
        f"     CASE WHEN {filt}\n"
        "     THEN 1 ELSE 0 END AS matches\n"
        "WITH count(g) AS total_search_hits,\n"
        "     sum(matches) AS total_matching,\n"
        "     max(CASE WHEN matches = 1 THEN score END) AS score_max,\n"
        "     percentileDisc(\n"
        "       CASE WHEN matches = 1 THEN score END, 0.5\n"
        "     ) AS score_median,\n"
        "     [x IN collect(\n"
        "       CASE WHEN matches = 1 THEN g.organism_name END\n"
        "     ) WHERE x IS NOT NULL] AS organisms,\n"
        "     [x IN collect(\n"
        "       CASE WHEN matches = 1 THEN g.gene_category END\n"
        "     ) WHERE x IS NOT NULL] AS categories\n"
        "RETURN total_search_hits, total_matching, score_max, score_median,\n"
        "       apoc.coll.frequencies(organisms) AS by_organism,\n"
        "       apoc.coll.frequencies(categories) AS by_category"
    )
    return cypher, _genes_by_function_params(
        search_text=search_text, organism=organism,
        category=category, min_quality=min_quality,
    )


def build_genes_by_function(
    *,
    search_text: str,
    organism: str | None = None,
    category: str | None = None,
    min_quality: int = 0,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_function.

    RETURN keys (compact): locus_tag, gene_name, product,
    organism_name, gene_category, annotation_quality, score.
    RETURN keys (verbose): adds function_description, gene_summary.
    """
    params = _genes_by_function_params(
        search_text=search_text, organism=organism,
        category=category, min_quality=min_quality,
    )

    verbose_cols = (
        ",\n       g.function_description AS function_description"
        ",\n       g.gene_summary AS gene_summary"
        if verbose else ""
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    filt = _genes_by_function_filter_clause()
    cypher = (
        "CALL db.index.fulltext.queryNodes('geneFullText', $search_text)\n"
        "YIELD node AS g, score\n"
        f"WHERE {filt}\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_name AS organism_name,\n"
        "       g.gene_category AS gene_category,\n"
        f"       g.annotation_quality AS annotation_quality, score{verbose_cols}\n"
        f"ORDER BY score DESC, g.locus_tag{skip_clause}{limit_clause}"
    )
    return cypher, params


# Deepest-attachment predicate (TCDB substrate-depth migration, decision 4).
# An attachment of gene `g` to TcdbFamily `tf` is superseded when `g` is also
# attached to a descendant of `tf`; every transport-arm traversal (rows,
# envelope counts, evidence_sources / has_chemistry) walks deepest
# attachments only so all TCDB surfaces project one (gene, metabolite) set —
# the same set the KG's precomputed transport counts are built over.
# Requires `g` and `tf` to be bound in the enclosing MATCH.
TCDB_DEEPEST_ATTACHMENT_PREDICATE = (
    "NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family]->(d:TcdbFamily)"
    " WHERE (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(tf) }"
)


def build_gene_overview_summary(
    *,
    locus_tags: list[str],
) -> tuple[str, dict]:
    """Build summary + not_found for gene_overview.

    RETURN keys: total_matching, by_organism, by_category,
    by_annotation_type, has_expression, has_significant_expression,
    has_orthologs, has_clusters, has_derived_metrics, has_chemistry,
    has_discussed, by_merops_class, has_ncbifam, has_tcdb, has_cazy,
    not_found.
    """
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "WITH collect(lt) AS all_tags,\n"
        "     collect(g) AS genes,\n"
        "     collect(CASE WHEN g IS NULL THEN lt END) AS not_found_raw\n"
        "WITH [x IN not_found_raw WHERE x IS NOT NULL] AS not_found,\n"
        "     [g IN genes WHERE g IS NOT NULL] AS found\n"
        "WITH not_found, found,\n"
        "     size(found) AS total_matching,\n"
        "     [g IN found | g.organism_name] AS orgs,\n"
        "     [g IN found | g.gene_category] AS cats,\n"
        "     [g IN found | g.annotation_state] AS states,\n"
        "     apoc.coll.flatten([g IN found | g.annotation_types]) AS all_atypes\n"
        "RETURN total_matching,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(cats) AS by_category,\n"
        "       apoc.coll.frequencies(all_atypes) AS by_annotation_type,\n"
        "       apoc.coll.frequencies(states) AS by_annotation_state,\n"
        "       size([g IN found WHERE g.expression_edge_count > 0]) AS has_expression,\n"
        "       size([g IN found WHERE (g.significant_up_count + g.significant_down_count) > 0]) AS has_significant_expression,\n"
        "       size([g IN found WHERE g.closest_ortholog_group_size > 0]) AS has_orthologs,\n"
        "       size([g IN found WHERE g.cluster_membership_count > 0]) AS has_clusters,\n"
        "       size([g IN found WHERE\n"
        "           coalesce(g.numeric_metric_count, 0)\n"
        "         + coalesce(g.boolean_metric_count, 0)\n"
        "         + coalesce(g.categorical_metric_count, 0) > 0]) AS has_derived_metrics,\n"
        # has_chemistry: metabolism arm OR deepest-attachment transport arm
        # (decision 4 — same predicate as the detail evidence_sources traversal).
        "       size([g IN found WHERE EXISTS {\n"
        "         MATCH (g)-[:Gene_catalyzes_reaction]->(:Reaction)"
        "-[:Reaction_has_metabolite]->(:Metabolite)\n"
        "       } OR EXISTS {\n"
        "         MATCH (g)-[:Gene_has_tcdb_family]->(tf:TcdbFamily)"
        "-[:Tcdb_family_transports_metabolite]->(:Metabolite)\n"
        f"         WHERE {TCDB_DEEPEST_ATTACHMENT_PREDICATE}\n"
        "       }]) AS has_chemistry,\n"
        # Literature "discusses" arm (Extension 1): count of input genes with
        # >=1 discussing publication. Drives the top_discussing_publications
        # envelope rollup gate in the api layer.
        "       size([g IN found WHERE\n"
        "           coalesce(g.discussed_in_publication_count, 0) > 0]) AS has_discussed,\n"
        # Annotation-trust rollups (design §8): protease-call classes across the
        # batch, and how many input genes carry any NCBIfam family call.
        "       apoc.coll.frequencies(apoc.coll.flatten(\n"
        "         [g IN found | coalesce(g.merops_classes, [])])) AS by_merops_class,\n"
        "       size([g IN found WHERE\n"
        "           coalesce(g.ncbifam_family_count, 0) > 0]) AS has_ncbifam,\n"
        # Family-count rollups (backlog 3.4): both read the KG precomputes
        # (tcdb_family_count = deepest-attachment edges only; cazy is flat).
        "       size([g IN found WHERE coalesce(g.tcdb_family_count, 0) > 0]) AS has_tcdb,\n"
        "       size([g IN found WHERE coalesce(g.cazy_family_count, 0) > 0]) AS has_cazy,\n"
        "       not_found"
    )
    return cypher, {"locus_tags": locus_tags}


def build_gene_overview(
    *,
    locus_tags: list[str],
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_overview.

    RETURN keys (compact): locus_tag, gene_name, product, gene_category,
    annotation_quality, annotation_state, informative_annotation_types,
    organism_name, annotation_types,
    expression_edge_count, significant_up_count, significant_down_count,
    closest_ortholog_group_size, closest_ortholog_genera,
    cluster_membership_count, cluster_types,
    numeric_metric_count, boolean_metric_count, categorical_metric_count,
    reaction_count, catalyzed_metabolite_count,
    tcdb_evidence_score_max (float | null — sparse KG prop, NOT coalesced:
    null = no TCDB call), transported_metabolite_count (deepest-attachment
    substrate breadth), transport_substrate_resolution ('resolved' |
    'family_inferred' | null), discussed_in_publication_count,
    merops_classes (list, [] default — the protease call classes this gene
    carries), ncbifam_family_count (int, 0 default),
    tcdb_family_count (int, live count of attachment_depth='most_specific'
    Gene_has_tcdb_family edges — NOT the KG precompute, which counts
    superseded ancestors), cazy_family_count (int, 0 default),
    merops_evidence_score_max (float | null — sparse KG prop, NOT coalesced:
    null = no MEROPS call, the twin of tcdb_evidence_score_max),
    evidence_sources.
    RETURN keys (verbose): adds gene_summary, function_description,
    all_identifiers, numeric_metric_types_observed,
    boolean_metric_types_observed, categorical_metric_types_observed,
    compartments_observed.
    """
    params: dict = {"locus_tags": locus_tags}

    verbose_cols = (
        ",\n       g.gene_summary AS gene_summary"
        ",\n       g.function_description AS function_description"
        ",\n       g.all_identifiers AS all_identifiers"
        ",\n       coalesce(g.numeric_metric_types_observed, []) AS numeric_metric_types_observed"
        ",\n       coalesce(g.boolean_metric_types_observed, []) AS boolean_metric_types_observed"
        ",\n       coalesce(g.categorical_metric_types_observed, []) AS categorical_metric_types_observed"
        ",\n       coalesce(g.compartments_observed, []) AS compartments_observed"
        # Publication "discusses" verbose list — pattern comprehension yields []
        # for a gene with no discussing publication (no CASE-NULL row needed).
        ",\n       [(g)<-[rdp:Publication_discusses_gene]-(pdp:Publication)"
        " | {doi: pdp.doi, prominence: rdp.prominence, evidence: rdp.evidence}]"
        " AS discussed_in_publications"
        if verbose else ""
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    # Phase 1 plumbing (spec §6.1): per-row chemistry counts +
    # path-existence-derived evidence_sources. The CASE/EXISTS form
    # avoids the false-positive 'metabolism' tag that a metabolite-level
    # rollup would produce on transport-only genes (e.g. PMM0392).
    chemistry_with = (
        "WITH g,\n"
        "  CASE WHEN EXISTS {\n"
        "    MATCH (g)-[:Gene_catalyzes_reaction]->(:Reaction)"
        "-[:Reaction_has_metabolite]->(:Metabolite)\n"
        "  } THEN ['metabolism'] ELSE [] END +\n"
        "  CASE WHEN EXISTS {\n"
        "    MATCH (g)-[:Gene_has_tcdb_family]->(tf:TcdbFamily)"
        "-[:Tcdb_family_transports_metabolite]->(:Metabolite)\n"
        f"    WHERE {TCDB_DEEPEST_ATTACHMENT_PREDICATE}\n"
        "  } THEN ['transport'] ELSE [] END +\n"
        "  CASE WHEN EXISTS {\n"
        "    MATCH (g)-[:Gene_catalyzes_reaction]->(:Reaction)"
        "-[:Reaction_has_metabolite]->(m:Metabolite)\n"
        "    WHERE coalesce(m.measured_assay_count, 0) > 0\n"
        "  } OR EXISTS {\n"
        "    MATCH (g)-[:Gene_has_tcdb_family]->(tf:TcdbFamily)"
        "-[:Tcdb_family_transports_metabolite]->(m:Metabolite)\n"
        "    WHERE coalesce(m.measured_assay_count, 0) > 0\n"
        f"      AND {TCDB_DEEPEST_ATTACHMENT_PREDICATE}\n"
        "  } THEN ['metabolomics'] ELSE [] END AS evidence_sources\n"
    )

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})\n"
        f"{chemistry_with}"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.gene_category AS gene_category,\n"
        "       g.annotation_quality AS annotation_quality,\n"
        "       g.annotation_state AS annotation_state,\n"
        "       coalesce(g.informative_annotation_types, []) AS informative_annotation_types,\n"
        "       g.organism_name AS organism_name,\n"
        "       g.annotation_types AS annotation_types,\n"
        "       g.expression_edge_count AS expression_edge_count,\n"
        "       g.significant_up_count AS significant_up_count,\n"
        "       g.significant_down_count AS significant_down_count,\n"
        "       g.closest_ortholog_group_size AS closest_ortholog_group_size,\n"
        "       g.closest_ortholog_genera AS closest_ortholog_genera,\n"
        "       coalesce(g.cluster_membership_count, 0) AS cluster_membership_count,\n"
        "       coalesce(g.cluster_types, []) AS cluster_types,\n"
        "       coalesce(g.numeric_metric_count, 0) AS numeric_metric_count,\n"
        "       coalesce(g.boolean_metric_count, 0) AS boolean_metric_count,\n"
        "       coalesce(g.categorical_metric_count, 0) AS categorical_metric_count,\n"
        "       coalesce(g.reaction_count, 0) AS reaction_count,\n"
        "       coalesce(g.catalyzed_metabolite_count, 0) AS catalyzed_metabolite_count,\n"
        # TCDB gene-level surface (substrate-depth migration). Score is a
        # sparse KG prop surfaced uncoalesced — null means "no TCDB call".
        "       g.tcdb_evidence_score_max AS tcdb_evidence_score_max,\n"
        "       coalesce(g.transported_metabolite_count, 0) AS transported_metabolite_count,\n"
        "       g.transport_substrate_resolution AS transport_substrate_resolution,\n"
        "       coalesce(g.discussed_in_publication_count, 0) AS discussed_in_publication_count,\n"
        # Annotation-trust routing signals (spec §7.8). merops_classes and
        # ncbifam_family_count are safe to default; merops_evidence_score_max
        # is surfaced uncoalesced (twin of tcdb_evidence_score_max) — null
        # means "no MEROPS call", which is not the same as a weak one.
        "       coalesce(g.merops_classes, []) AS merops_classes,\n"
        "       coalesce(g.ncbifam_family_count, 0) AS ncbifam_family_count,\n"
        # TCDB family count at the deepest attachment only (backlog 3.4).
        # Gene.tcdb_family_count is a KG precompute over the
        # attachment_depth='most_specific' edges (aligned in the 2026-08-29
        # rebuild; test_trust_invariants guards it against the live edge
        # count). CAZy is flat, so its precompute is exact by construction.
        "       coalesce(g.tcdb_family_count, 0) AS tcdb_family_count,\n"
        "       coalesce(g.cazy_family_count, 0) AS cazy_family_count,\n"
        "       g.merops_evidence_score_max AS merops_evidence_score_max,\n"
        f"       evidence_sources{verbose_cols}\n"
        f"ORDER BY g.locus_tag{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_gene_details(
    *, locus_tags: list[str], limit: int | None = None, offset: int = 0,
) -> tuple[str, dict]:
    """Build query for full gene node properties (batch)."""
    params: dict = {"locus_tags": locus_tags}
    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    limit_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})\n"
        f"RETURN g {{.*}} AS gene\nORDER BY g.locus_tag{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_gene_details_summary(
    *, locus_tags: list[str],
) -> tuple[str, dict]:
    """Build summary query for gene details: total + not_found."""
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "WITH collect(CASE WHEN g IS NOT NULL THEN lt END) AS found,\n"
        "     collect(CASE WHEN g IS NULL THEN lt END) AS not_found\n"
        "RETURN size(found) AS total_matching, not_found"
    )
    return cypher, {"locus_tags": locus_tags}



def build_gene_stub(*, gene_id: str) -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene {locus_tag: $lt})\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_name AS organism_name"
    )
    return cypher, {"lt": gene_id}


def _gene_homologs_og_where(
    *,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build OG filter conditions + params shared by gene_homologs builders."""
    conditions: list[str] = []
    params: dict = {}
    if source is not None:
        conditions.append("og.source = $source")
        params["source"] = source
    if taxonomic_level is not None:
        conditions.append("og.taxonomic_level = $level")
        params["level"] = taxonomic_level
    if max_specificity_rank is not None:
        conditions.append("og.specificity_rank <= $max_rank")
        params["max_rank"] = max_specificity_rank
    if cyanorak_roles is not None:
        conditions.append(
            "EXISTS { (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)"
            " WHERE cr.id IN $cyanorak_roles }"
        )
        params["cyanorak_roles"] = cyanorak_roles
    if cog_categories is not None:
        conditions.append(
            "EXISTS { (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)"
            " WHERE cc.id IN $cog_categories }"
        )
        params["cog_categories"] = cog_categories
    return conditions, params


def build_gene_homologs_summary(
    *,
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary + not_found/no_groups for gene_homologs.

    RETURN keys: total_matching, by_organism, by_source, not_found, no_groups,
    top_cyanorak_roles, top_cog_categories.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles,
        cog_categories=cog_categories,
    )
    params["locus_tags"] = locus_tags

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "OPTIONAL MATCH (g)-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        f"{where_block}"
        "WITH lt, g, collect(og) AS groups\n"
        "WITH\n"
        "  collect(CASE WHEN g IS NULL THEN lt END) AS nf_raw,\n"
        "  collect(CASE WHEN g IS NOT NULL AND size(groups) = 0 THEN lt END) AS ng_raw,\n"
        "  [row IN collect({org: CASE WHEN size(groups) > 0 THEN g.organism_name END,\n"
        "                    srcs: [x IN groups | x.source],\n"
        "                    og_ids: [x IN groups | x.id]})\n"
        "   WHERE row.org IS NOT NULL] AS matched\n"
        "UNWIND CASE WHEN size(matched) = 0 THEN [null] ELSE matched END AS m\n"
        "WITH nf_raw, ng_raw,\n"
        "     [x IN collect(m.org) WHERE x IS NOT NULL] AS orgs,\n"
        "     apoc.coll.flatten([x IN collect(m.srcs) WHERE x IS NOT NULL]) AS sources,\n"
        "     apoc.coll.toSet(apoc.coll.flatten(\n"
        "       [x IN collect(m.og_ids) WHERE x IS NOT NULL])) AS all_og_ids\n"
        "UNWIND CASE WHEN size(all_og_ids) = 0 THEN [null] ELSE all_og_ids END AS og_id\n"
        "OPTIONAL MATCH (og_node:OrthologGroup {id: og_id})-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
        "OPTIONAL MATCH (og_node)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
        "WITH nf_raw, ng_raw, orgs, sources,\n"
        "     collect(DISTINCT {id: cr.id, name: cr.name}) AS cr_pairs,\n"
        "     collect(DISTINCT {id: cc.id, name: cc.name}) AS cc_pairs\n"
        "WITH nf_raw, ng_raw, orgs, sources,\n"
        "     [p IN cr_pairs WHERE p.id IS NOT NULL | p.id + ' | ' + p.name] AS cr_items,\n"
        "     [p IN cc_pairs WHERE p.id IS NOT NULL | p.id + ' | ' + p.name] AS cc_items\n"
        "WITH *,\n"
        "     apoc.coll.frequencies(cr_items) AS cr_freq,\n"
        "     apoc.coll.frequencies(cc_items) AS cc_freq\n"
        "RETURN size(sources) AS total_matching,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(sources) AS by_source,\n"
        "       [x IN nf_raw WHERE x IS NOT NULL] AS not_found,\n"
        "       [x IN ng_raw WHERE x IS NOT NULL] AS no_groups,\n"
        "       apoc.coll.sortMaps(\n"
        "         [x IN cr_freq | {id: split(x.item, ' | ')[0],\n"
        "                          name: split(x.item, ' | ')[1],\n"
        "                          count: x.count}],\n"
        "         'count')[0..5] AS top_cyanorak_roles,\n"
        "       apoc.coll.sortMaps(\n"
        "         [x IN cc_freq | {id: split(x.item, ' | ')[0],\n"
        "                          name: split(x.item, ' | ')[1],\n"
        "                          count: x.count}],\n"
        "         'count')[0..5] AS top_cog_categories"
    )
    return cypher, params


def build_gene_homologs(
    *,
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_homologs.

    RETURN keys (compact): locus_tag, organism_name, group_id,
    consensus_gene_name, consensus_product, taxonomic_level, source,
    specificity_rank.
    RETURN keys (verbose): adds member_count, organism_count, genera,
    has_cross_genus_members, description, functional_description,
    cyanorak_roles, cog_categories.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles,
        cog_categories=cog_categories,
    )
    params["locus_tags"] = locus_tags

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    if verbose:
        cypher = (
            "UNWIND $locus_tags AS lt\n"
            "MATCH (g:Gene {locus_tag: lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
            f"{where_block}"
            "OPTIONAL MATCH (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
            "OPTIONAL MATCH (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
            "WITH g, og,\n"
            "     [x IN collect(DISTINCT {id: cr.id, name: cr.name}) WHERE x.id IS NOT NULL] AS cyanorak_roles,\n"
            "     [x IN collect(DISTINCT {id: cc.id, name: cc.name}) WHERE x.id IS NOT NULL] AS cog_categories\n"
            "RETURN g.locus_tag AS locus_tag, g.organism_name AS organism_name,\n"
            "       og.id AS group_id,\n"
            "       og.consensus_gene_name AS consensus_gene_name,\n"
            "       og.consensus_product AS consensus_product,\n"
            "       og.taxonomic_level AS taxonomic_level, og.source AS source,\n"
            "       og.specificity_rank AS specificity_rank,\n"
            "       og.member_count AS member_count,\n"
            "       og.organism_count AS organism_count,\n"
            "       og.genera AS genera,\n"
            "       og.has_cross_genus_members AS has_cross_genus_members,\n"
            "       og.description AS description,\n"
            "       og.functional_description AS functional_description,\n"
            "       cyanorak_roles, cog_categories\n"
            f"ORDER BY g.locus_tag, og.specificity_rank, og.source{skip_clause}{limit_clause}"
        )
    else:
        cypher = (
            "UNWIND $locus_tags AS lt\n"
            "MATCH (g:Gene {locus_tag: lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
            f"{where_block}"
            "RETURN g.locus_tag AS locus_tag, g.organism_name AS organism_name,\n"
            "       og.id AS group_id,\n"
            "       og.consensus_gene_name AS consensus_gene_name,\n"
            "       og.consensus_product AS consensus_product,\n"
            "       og.taxonomic_level AS taxonomic_level, og.source AS source,\n"
            f"       og.specificity_rank AS specificity_rank\n"
            f"ORDER BY g.locus_tag, og.specificity_rank, og.source{skip_clause}{limit_clause}"
        )
    return cypher, params


def _list_publications_where(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    background_factors: str | None = None,
    growth_phases: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    publication_dois: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[str, dict]:
    """Build WHERE clause and params for publication queries.

    Shared between build_list_publications and build_list_publications_summary.
    """
    conditions: list[str] = []
    params: dict = {}

    if search_text:
        params["search_text"] = search_text

    if organism:
        conditions.append(
            "ANY(o IN p.organisms WHERE toLower(o) CONTAINS toLower($organism))"
        )
        params["organism"] = organism

    if treatment_type:
        conditions.append(
            "ANY(t IN p.treatment_types WHERE toLower(t) = toLower($treatment_type))"
        )
        params["treatment_type"] = treatment_type

    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(p.background_factors, [])"
            " WHERE toLower(bf) = toLower($background_factors))"
        )
        params["background_factors"] = background_factors

    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(p.growth_phases, [])"
            " WHERE toLower(gp) = toLower($growth_phases))"
        )
        params["growth_phases"] = growth_phases

    if author:
        conditions.append(
            "ANY(a IN p.authors WHERE toLower(a) CONTAINS toLower($author))"
        )
        params["author"] = author

    if publication_dois:
        conditions.append("toLower(p.doi) IN $publication_dois")
        params["publication_dois"] = [d.lower() for d in publication_dois]

    if compartment is not None:
        conditions.append("$compartment IN coalesce(p.compartments, [])")
        params["compartment"] = compartment

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
    return where_block, params


def build_list_publications(
    *,
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
) -> tuple[str, dict]:
    """Build Cypher for listing publications with experiment summaries.

    RETURN keys (compact): doi, title, authors, year, journal, study_type,
    organisms, experiment_count, treatment_types, background_factors, omics_types,
    clustering_analysis_count, cluster_types, growth_phases,
    derived_metric_count, derived_metric_value_kinds, compartments.
    When search_text is provided, also: score.
    RETURN keys (verbose): adds abstract, description, cluster_count,
    derived_metric_gene_count, derived_metric_types.
    compartment: when provided, restricts to publications with at least one
    experiment in that wet-lab compartment.
    """
    where_block, params = _list_publications_where(
        organism=organism, treatment_type=treatment_type,
        background_factors=background_factors, growth_phases=growth_phases,
        search_text=search_text, author=author,
        publication_dois=publication_dois, compartment=compartment,
    )

    verbose_cols = (
        ",\n       p.abstract AS abstract, p.description AS description,"
        "\n       p.cluster_count AS cluster_count,"
        "\n       coalesce(p.derived_metric_gene_count, 0) AS derived_metric_gene_count,"
        "\n       coalesce(p.derived_metric_types, []) AS derived_metric_types"
        if verbose else ""
    )
    if limit is not None:
        limit_clause = "LIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    if search_text:
        cypher = (
            "CALL db.index.fulltext.queryNodes('publicationFullText', $search_text)\n"
            "YIELD node AS p, score\n"
            f"{where_block}"
            "RETURN p.doi AS doi,\n"
            "       p.title AS title,\n"
            "       p.authors AS authors,\n"
            "       p.publication_year AS year,\n"
            "       p.journal AS journal,\n"
            "       p.study_type AS study_type,\n"
            "       p.organisms AS organisms,\n"
            "       p.experiment_count AS experiment_count,\n"
            "       p.treatment_types AS treatment_types,\n"
            "       coalesce(p.background_factors, []) AS background_factors,\n"
            "       p.omics_types AS omics_types,\n"
            "       coalesce(p.clustering_analysis_count, 0) AS clustering_analysis_count,\n"
            "       coalesce(p.cluster_types, []) AS cluster_types,\n"
            "       coalesce(p.growth_phases, []) AS growth_phases,\n"
            "       coalesce(p.derived_metric_count, 0) AS derived_metric_count,\n"
            "       coalesce(p.derived_metric_value_kinds, []) AS derived_metric_value_kinds,\n"
            "       coalesce(p.compartments, []) AS compartments,\n"
            "       coalesce(p.metabolite_count, 0) AS metabolite_count,\n"
            "       coalesce(p.metabolite_assay_count, 0) AS metabolite_assay_count,\n"
            "       coalesce(p.metabolite_compartments, []) AS metabolite_compartments,\n"
            "       coalesce(p.discussed_gene_count, 0) AS discussed_gene_count,\n"
            "       coalesce(p.discussed_pathway_count, 0) AS discussed_pathway_count,\n"
            f"       score{verbose_cols}\n"
            f"ORDER BY score DESC, p.publication_year DESC, p.title\n"
            f"{limit_clause}"
        )
    else:
        cypher = (
            "MATCH (p:Publication)\n"
            f"{where_block}"
            "RETURN p.doi AS doi,\n"
            "       p.title AS title,\n"
            "       p.authors AS authors,\n"
            "       p.publication_year AS year,\n"
            "       p.journal AS journal,\n"
            "       p.study_type AS study_type,\n"
            "       p.organisms AS organisms,\n"
            "       p.experiment_count AS experiment_count,\n"
            "       p.treatment_types AS treatment_types,\n"
            "       coalesce(p.background_factors, []) AS background_factors,\n"
            "       p.omics_types AS omics_types,\n"
            "       coalesce(p.clustering_analysis_count, 0) AS clustering_analysis_count,\n"
            "       coalesce(p.cluster_types, []) AS cluster_types,\n"
            "       coalesce(p.growth_phases, []) AS growth_phases,\n"
            "       coalesce(p.derived_metric_count, 0) AS derived_metric_count,\n"
            "       coalesce(p.derived_metric_value_kinds, []) AS derived_metric_value_kinds,\n"
            "       coalesce(p.compartments, []) AS compartments,\n"
            "       coalesce(p.metabolite_count, 0) AS metabolite_count,\n"
            "       coalesce(p.metabolite_assay_count, 0) AS metabolite_assay_count,\n"
            "       coalesce(p.metabolite_compartments, []) AS metabolite_compartments,\n"
            "       coalesce(p.discussed_gene_count, 0) AS discussed_gene_count,\n"
            f"       coalesce(p.discussed_pathway_count, 0) AS discussed_pathway_count{verbose_cols}\n"
            f"ORDER BY p.publication_year DESC, p.title\n"
            f"{limit_clause}"
        )

    return cypher, params


def build_list_publications_summary(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    background_factors: str | None = None,
    growth_phases: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    publication_dois: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for matching publications.

    RETURN keys: total_entries, total_matching, by_organism,
    by_treatment_type, by_background_factors, by_omics_type,
    by_cluster_type, by_value_kind, by_metric_type, by_compartment.
    total_entries is the unfiltered count of all publications.
    total_matching is the count after applying filters.
    The rollup envelope keys use apoc.coll.flatten + apoc.coll.frequencies over
    the precomputed list properties on each Publication node.
    """
    where_block, params = _list_publications_where(
        organism=organism, treatment_type=treatment_type,
        background_factors=background_factors, growth_phases=growth_phases,
        search_text=search_text, author=author,
        publication_dois=publication_dois, compartment=compartment,
    )

    collect_cols = (
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.organisms, []))) AS orgs,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.treatment_types, []))) AS tts,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.background_factors, []))) AS bfs,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.omics_types, []))) AS omics,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.derived_metric_value_kinds, []))) AS vks,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.derived_metric_types, []))) AS mtypes,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.compartments, []))) AS comps,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.cluster_types, []))) AS ctypes,\n"
        # Binary discusses-coverage split: a publication has a narrative
        # literature index when either precomputed discussed count is > 0.
        "     collect(CASE WHEN coalesce(p.discussed_gene_count, 0)\n"
        "                       + coalesce(p.discussed_pathway_count, 0) > 0\n"
        "                  THEN 'has_discusses' ELSE 'no_discusses' END) AS disc_cov"
    )
    return_cols = (
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(tts) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(bfs) AS by_background_factors,\n"
        "       apoc.coll.frequencies(omics) AS by_omics_type,\n"
        "       apoc.coll.frequencies(vks) AS by_value_kind,\n"
        "       apoc.coll.frequencies(mtypes) AS by_metric_type,\n"
        "       apoc.coll.frequencies(comps) AS by_compartment,\n"
        "       apoc.coll.frequencies(ctypes) AS by_cluster_type,\n"
        "       {has_discusses: size([x IN disc_cov WHERE x = 'has_discusses']),\n"
        "        no_discusses: size([x IN disc_cov WHERE x = 'no_discusses'])}\n"
        "         AS by_discusses_coverage"
    )

    if search_text:
        cypher = (
            "CALL db.index.fulltext.queryNodes('publicationFullText', $search_text)\n"
            "YIELD node AS p, score\n"
            f"{where_block}"
            "WITH count(p) AS total_matching,\n"
            f"{collect_cols}\n"
            "MATCH (p2:Publication)\n"
            "RETURN count(p2) AS total_entries, total_matching,\n"
            f"{return_cols}"
        )
    else:
        # OPTIONAL MATCH preserves the total_entries row when the filtered
        # MATCH returns zero rows — without it, an empty filter intersection
        # collapses to 0 result rows and callers IndexError on summary[0].
        cypher = (
            "MATCH (p:Publication)\n"
            "WITH count(p) AS total_entries\n"
            "OPTIONAL MATCH (p:Publication)\n"
            f"{where_block}"
            "WITH total_entries,\n"
            "     count(p) AS total_matching,\n"
            f"{collect_cols}\n"
            "RETURN total_entries, total_matching,\n"
            f"{return_cols}"
        )

    return cypher, params


# --- Publication "discusses" literature-index surface -----------------------

_DISCUSSES_ENTITY_KINDS = ("gene", "kegg_pathway")
_DISCUSSES_PROMINENCE = ("central", "peripheral")


def _validate_discusses_filters(
    entity_kind: str | None, prominence: str | None,
) -> None:
    """Validate the closed-Literal filters shared by the discusses builders."""
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


def build_discussed_by_publication(
    *,
    publication_dois: list[str],
    entity_kind: str | None = None,
    prominence: str | None = None,
    verbose: bool = False,
    limit: int | None = 50,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for discussed_by_publication (forward lookup).

    UNION ALL over Publication_discusses_gene + Publication_discusses_kegg_pathway
    with distinct edge variables (rg / rk) — reusing one variable across both
    rel types raises a CyVer conflicting-labels error.

    RETURN keys (compact): doi, entity_kind, entity_id, entity_name, organism,
    prominence. Verbose adds: evidence.

    `entity_kind` drops the unwanted UNION branch (conditional assembly).
    `prominence` filters edges inline in each arm. DOI match is case-insensitive
    (`toLower(p.doi) IN $publication_dois` — caller lowercases the param).
    Global ORDER BY doi, entity_kind, prominence (central first), entity_id;
    SKIP $offset; LIMIT $limit.
    """
    _validate_discusses_filters(entity_kind, prominence)

    # `prominence` is bound unconditionally (even when None): the Cypher always
    # references `$prominence` via `($prominence IS NULL OR ...)`, and Neo4j
    # raises ParameterMissing if a referenced param is absent from the dict.
    params: dict = {"publication_dois": publication_dois, "prominence": prominence}

    gene_evidence = ",\n       rg.evidence AS evidence" if verbose else ""
    pathway_evidence = ",\n       rk.evidence AS evidence" if verbose else ""

    gene_arm = (
        "MATCH (p:Publication)-[rg:Publication_discusses_gene]->(g:Gene)\n"
        "WHERE toLower(p.doi) IN $publication_dois\n"
        "  AND ($prominence IS NULL OR rg.prominence = $prominence)\n"
        "RETURN p.doi AS doi, 'gene' AS entity_kind, g.locus_tag AS entity_id,\n"
        "       coalesce(g.gene_name, g.product) AS entity_name,\n"
        "       g.organism_name AS organism,\n"
        f"       rg.prominence AS prominence{gene_evidence}"
    )
    pathway_arm = (
        "MATCH (p:Publication)-[rk:Publication_discusses_kegg_pathway]->(k:KeggTerm)\n"
        "WHERE toLower(p.doi) IN $publication_dois\n"
        "  AND ($prominence IS NULL OR rk.prominence = $prominence)\n"
        "RETURN p.doi AS doi, 'kegg_pathway' AS entity_kind, k.id AS entity_id,\n"
        "       k.name AS entity_name, NULL AS organism,\n"
        f"       rk.prominence AS prominence{pathway_evidence}"
    )

    if entity_kind == "gene":
        body = gene_arm
    elif entity_kind == "kegg_pathway":
        body = pathway_arm
    else:
        body = gene_arm + "\nUNION ALL\n" + pathway_arm

    # Wrap so the ORDER BY / SKIP / LIMIT apply globally across the union.
    # central-first via a CASE ordinal on prominence.
    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "CALL {\n"
        f"{body}\n"
        "}\n"
        "RETURN *\n"
        "ORDER BY doi, entity_kind,\n"
        "         CASE prominence WHEN 'central' THEN 0 ELSE 1 END,\n"
        f"         entity_id{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_discussed_by_publication_summary(
    *,
    publication_dois: list[str],
    entity_kind: str | None = None,
    prominence: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for discussed_by_publication.

    RETURN keys: total_entries, total_matching, by_entity_kind, by_prominence,
    top_kegg_pathways, top_publications, resolved_dois, matched_dois.

    total_entries is UNFILTERED — sums the precomputed
    Publication.discussed_gene_count + discussed_pathway_count over the matched
    DOIs (NOT a re-count of the filtered detail query). Every other rollup
    reflects the FILTERED (entity_kind / prominence) set.

    `resolved_dois` (input DOIs that resolve to a Publication) and `matched_dois`
    (input DOIs with >=1 edge after filters), both lowercased, let the api layer
    diff them into not_found / not_matched. Filtered rows are built via pattern
    comprehensions (which always yield a list, possibly empty) rather than a
    correlated `CALL {}` subquery, so the summary returns exactly one row even
    when zero input DOIs have any edge (all-edgeless / all-garbage input).
    """
    _validate_discusses_filters(entity_kind, prominence)

    # `prominence` bound unconditionally — the pattern-comprehension predicates
    # always reference `$prominence` (see C1 note on the detail builder).
    params: dict = {"publication_dois": publication_dois, "prominence": prominence}

    gene_rows = (
        "[ (p:Publication)-[rg:Publication_discusses_gene]->(g:Gene)\n"
        "  WHERE toLower(p.doi) IN $publication_dois\n"
        "    AND ($prominence IS NULL OR rg.prominence = $prominence)\n"
        "  | {doi: p.doi, entity_kind: 'gene', entity_id: g.locus_tag,\n"
        "     entity_name: coalesce(g.gene_name, g.product),\n"
        "     prominence: rg.prominence} ]"
    )
    pathway_rows = (
        "[ (p:Publication)-[rk:Publication_discusses_kegg_pathway]->(k:KeggTerm)\n"
        "  WHERE toLower(p.doi) IN $publication_dois\n"
        "    AND ($prominence IS NULL OR rk.prominence = $prominence)\n"
        "  | {doi: p.doi, entity_kind: 'kegg_pathway', entity_id: k.id,\n"
        "     entity_name: k.name, prominence: rk.prominence} ]"
    )
    if entity_kind == "gene":
        rows_expr = gene_rows
    elif entity_kind == "kegg_pathway":
        rows_expr = pathway_rows
    else:
        rows_expr = f"{gene_rows}\n     + {pathway_rows}"

    cypher = (
        # resolved DOIs + total_entries (unfiltered, precomputed counts) + a
        # doi->title map for top_publications. Aggregations yield one row even
        # when no Publication matches (resolved_dois -> [], total_entries -> 0).
        "MATCH (p0:Publication)\n"
        "WHERE toLower(p0.doi) IN $publication_dois\n"
        "WITH collect(DISTINCT toLower(p0.doi)) AS resolved_dois,\n"
        "     apoc.map.fromPairs(collect([p0.doi, p0.title])) AS title_by_doi,\n"
        "     sum(coalesce(p0.discussed_gene_count, 0)\n"
        "         + coalesce(p0.discussed_pathway_count, 0)) AS total_entries\n"
        f"WITH resolved_dois, title_by_doi, total_entries,\n     {rows_expr} AS rows\n"
        "RETURN total_entries,\n"
        "       resolved_dois,\n"
        "       apoc.coll.toSet([r IN rows | toLower(r.doi)]) AS matched_dois,\n"
        "       size(rows) AS total_matching,\n"
        "       apoc.coll.frequencies([r IN rows | r.entity_kind]) AS by_entity_kind,\n"
        "       apoc.coll.frequencies([r IN rows | r.prominence]) AS by_prominence,\n"
        "       apoc.coll.sortMaps(\n"
        "         [f IN apoc.coll.frequencies(\n"
        "            [r IN rows WHERE r.entity_kind = 'kegg_pathway'\n"
        "             | r.entity_id + ' | ' + coalesce(r.entity_name, '')])\n"
        "          | {id: split(f.item, ' | ')[0],\n"
        "             name: split(f.item, ' | ')[1], n: f.count}],\n"
        "         'n')[0..10] AS top_kegg_pathways,\n"
        "       apoc.coll.sortMaps(\n"
        "         [f IN apoc.coll.frequencies([r IN rows | r.doi])\n"
        "          | {doi: f.item, title: title_by_doi[f.item], n: f.count}],\n"
        "         'n')[0..10] AS top_publications"
    )
    return cypher, params


def build_gene_overview_top_discussing_publications(
    *, locus_tags: list[str],
) -> tuple[str, dict]:
    """Build the gene_overview envelope rollup `top_discussing_publications`.

    Ranks publications by how many of the QUERIED genes they discuss (distinct
    gene count) — the batch set-coverage signal the per-gene rows cannot yield.

    RETURN keys: doi, title, n_genes.
    """
    cypher = (
        "MATCH (g:Gene)<-[:Publication_discusses_gene]-(p:Publication)\n"
        "WHERE g.locus_tag IN $locus_tags\n"
        "WITH p, count(DISTINCT g) AS n_genes\n"
        "RETURN p.doi AS doi, p.title AS title, n_genes\n"
        "ORDER BY n_genes DESC, p.doi\n"
        "LIMIT 10"
    )
    return cypher, {"locus_tags": locus_tags}


def _list_metabolites_where(
    *,
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
    organism_names_lc: list[str] | None = None,
    pathway_ids: list[str] | None = None,
    evidence_sources: list[str] | None = None,
) -> tuple[str, dict]:
    """Build WHERE clause and params for metabolite queries.

    Shared between build_list_metabolites and build_list_metabolites_summary.
    `search_text` is not added to WHERE — it controls which Cypher variant
    is used (fulltext entry point vs MATCH). The Cypher param name `$search`
    stays unchanged (it's the second arg to
    `db.index.fulltext.queryNodes('metaboliteFullText', $search)`); only
    the Python kwarg renamed.
    """
    conditions: list[str] = []
    params: dict = {}

    if search_text:
        params["search"] = search_text

    if metabolite_ids:
        conditions.append("m.id IN $metabolite_ids")
        params["metabolite_ids"] = metabolite_ids

    if exclude_metabolite_ids:
        conditions.append("(NOT (m.id IN $exclude_metabolite_ids))")
        params["exclude_metabolite_ids"] = exclude_metabolite_ids

    if kegg_compound_ids:
        conditions.append("m.kegg_compound_id IN $kegg_compound_ids")
        params["kegg_compound_ids"] = kegg_compound_ids

    if chebi_ids:
        conditions.append("m.chebi_id IN $chebi_ids")
        params["chebi_ids"] = chebi_ids

    if hmdb_ids:
        conditions.append("m.hmdb_id IN $hmdb_ids")
        params["hmdb_ids"] = hmdb_ids

    if mnxm_ids:
        conditions.append("m.mnxm_id IN $mnxm_ids")
        params["mnxm_ids"] = mnxm_ids

    if elements:
        conditions.append(
            "ALL(e IN $elements WHERE e IN coalesce(m.elements, []))"
        )
        params["elements"] = elements

    if mass_min is not None:
        conditions.append("m.mass >= $mass_min")
        params["mass_min"] = mass_min

    if mass_max is not None:
        conditions.append("m.mass <= $mass_max")
        params["mass_max"] = mass_max

    if organism_names_lc:
        conditions.append(
            "ANY(o IN coalesce(m.organism_names, []) "
            "WHERE toLower(o) IN $organism_names_lc)"
        )
        params["organism_names_lc"] = organism_names_lc

    if pathway_ids:
        conditions.append(
            "ANY(p IN coalesce(m.pathway_ids, []) WHERE p IN $pathway_ids)"
        )
        params["pathway_ids"] = pathway_ids

    if evidence_sources:
        conditions.append(
            "ANY(s IN $evidence_sources "
            "WHERE s IN coalesce(m.evidence_sources, []))"
        )
        params["evidence_sources"] = evidence_sources

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
    return where_block, params


def build_resolve_metabolite_aliases(raw_ids: list[str]) -> tuple[str, dict]:
    """Map bare / xref metabolite identifiers to canonical ``Metabolite.id``.

    One ``UNWIND $raw`` round-trip (spec
    ``docs/tool-specs/bare-metabolite-id-coercion.md``). Each input string is
    matched against exactly one xref property by shape: ``C\\d{5}`` →
    ``kegg_compound_id``; ``CHEBI:\\d+`` (prefix stripped case-insensitively)
    or ``\\d+`` → ``chebi_id``; ``HMDB\\d+`` → ``hmdb_id``; ``MNXM\\d+`` →
    ``mnxm_id``. Already-canonical / prefixed inputs are filtered out by the
    api layer before the call — this builder does not pass them through.

    Returns one row per input (``OPTIONAL MATCH``) with ``raw`` and
    ``canonical`` (``collect(m.id)`` — empty when unresolved, >1 on CHEBI /
    HMDB / MNXM collisions; the api layer expands all and warns, never picks
    one). Row order follows ``$raw``.

    Args:
        raw_ids: Bare / xref identifiers to resolve (``["C00064", "CHEBI:17234"]``).

    Returns:
        ``(cypher, {"raw": raw_ids})``.
    """
    cypher = (
        "UNWIND $raw AS raw\n"
        "WITH raw,\n"
        "     CASE WHEN toUpper(raw) STARTS WITH 'CHEBI:' "
        "THEN substring(raw, 6) ELSE raw END AS key\n"
        "OPTIONAL MATCH (m:Metabolite)\n"
        "WHERE (raw =~ 'C[0-9]{5}'  AND m.kegg_compound_id = raw)\n"
        "   OR (key =~ '[0-9]+'     AND m.chebi_id = key)\n"
        "   OR (raw =~ 'HMDB[0-9]+' AND m.hmdb_id = raw)\n"
        "   OR (raw =~ 'MNXM[0-9]+' AND m.mnxm_id = raw)\n"
        "RETURN raw, collect(m.id) AS canonical"
    )
    return cypher, {"raw": raw_ids}


def build_list_metabolites(
    *,
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
    organism_names_lc: list[str] | None = None,
    pathway_ids: list[str] | None = None,
    evidence_sources: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for listing metabolites.

    RETURN keys (compact): metabolite_id, name, formula, elements, mass,
    catalyst_gene_count, organism_count, transporter_count,
    transporter_gene_count (deepest-attachment transporter genes;
    catalyst_gene_count=0 + transporter_gene_count>0 = transport-only),
    evidence_sources, chebi_id, pathway_ids, pathway_count,
    measured_assay_count, measured_paper_count, measured_organisms,
    measured_compartments.
    When search_text is provided, also: score.
    RETURN keys (verbose): adds inchikey, smiles, mnxm_id, hmdb_id,
    pathway_names. All verbose columns are direct property reads on m;
    no edge traversal in either compact or verbose mode.
    """
    where_block, params = _list_metabolites_where(
        search_text=search_text,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids,
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

    verbose_cols = (
        ",\n       m.inchikey AS inchikey,"
        "\n       m.smiles AS smiles,"
        "\n       m.mnxm_id AS mnxm_id,"
        "\n       m.hmdb_id AS hmdb_id,"
        "\n       coalesce(m.pathway_names, []) AS pathway_names"
        if verbose else ""
    )

    pagination_parts: list[str] = []
    if offset:
        pagination_parts.append("SKIP $offset")
        params["offset"] = offset
    if limit is not None:
        pagination_parts.append("LIMIT $limit")
        params["limit"] = limit
    limit_clause = " ".join(pagination_parts)

    if search_text:
        cypher = (
            "CALL db.index.fulltext.queryNodes('metaboliteFullText', $search)\n"
            "YIELD node AS m, score\n"
            f"{where_block}"
            "RETURN m.id AS metabolite_id,\n"
            "       m.name AS name,\n"
            "       m.formula AS formula,\n"
            "       coalesce(m.elements, []) AS elements,\n"
            "       m.mass AS mass,\n"
            "       coalesce(m.catalyst_gene_count, 0) AS catalyst_gene_count,\n"
            "       coalesce(m.organism_count, 0) AS organism_count,\n"
            "       coalesce(m.transporter_count, 0) AS transporter_count,\n"
            "       coalesce(m.transporter_gene_count, 0) AS transporter_gene_count,\n"
            "       coalesce(m.evidence_sources, []) AS evidence_sources,\n"
            "       m.chebi_id AS chebi_id,\n"
            "       coalesce(m.pathway_ids, []) AS pathway_ids,\n"
            "       coalesce(m.pathway_count, 0) AS pathway_count,\n"
            "       coalesce(m.measured_assay_count, 0) AS measured_assay_count,\n"
            "       coalesce(m.measured_paper_count, 0) AS measured_paper_count,\n"
            "       coalesce(m.measured_organisms, []) AS measured_organisms,\n"
            "       coalesce(m.measured_compartments, []) AS measured_compartments,\n"
            f"       score{verbose_cols}\n"
            "ORDER BY score DESC, m.organism_count DESC, m.id\n"
            f"{limit_clause}"
        )
    else:
        cypher = (
            "MATCH (m:Metabolite)\n"
            f"{where_block}"
            "RETURN m.id AS metabolite_id,\n"
            "       m.name AS name,\n"
            "       m.formula AS formula,\n"
            "       coalesce(m.elements, []) AS elements,\n"
            "       m.mass AS mass,\n"
            "       coalesce(m.catalyst_gene_count, 0) AS catalyst_gene_count,\n"
            "       coalesce(m.organism_count, 0) AS organism_count,\n"
            "       coalesce(m.transporter_count, 0) AS transporter_count,\n"
            "       coalesce(m.transporter_gene_count, 0) AS transporter_gene_count,\n"
            "       coalesce(m.evidence_sources, []) AS evidence_sources,\n"
            "       m.chebi_id AS chebi_id,\n"
            "       coalesce(m.pathway_ids, []) AS pathway_ids,\n"
            "       coalesce(m.pathway_count, 0) AS pathway_count,\n"
            "       coalesce(m.measured_assay_count, 0) AS measured_assay_count,\n"
            "       coalesce(m.measured_paper_count, 0) AS measured_paper_count,\n"
            "       coalesce(m.measured_organisms, []) AS measured_organisms,\n"
            f"       coalesce(m.measured_compartments, []) AS measured_compartments{verbose_cols}\n"
            "ORDER BY m.organism_count DESC, m.catalyst_gene_count DESC, m.id\n"
            f"{limit_clause}"
        )

    return cypher, params


def build_list_metabolites_summary(
    *,
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
    organism_names_lc: list[str] | None = None,
    pathway_ids: list[str] | None = None,
    evidence_sources: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary aggregation Cypher for list_metabolites.

    RETURN keys: total_entries, total_matching, top_organisms,
    top_metabolite_pathways, by_evidence_source, with_chebi, with_hmdb,
    with_mnxm, mass_min, mass_median, mass_max.
    When search_text is provided, also: score_max, score_median.

    Critical: never `collect(m) AS matched`. Instead flatten denormalized
    list properties (KG-A5..A8) via apoc.coll.flatten over cheap collects.
    """
    where_block, params = _list_metabolites_where(
        search_text=search_text,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids,
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

    top_organisms_block = (
        "CALL {\n"
        "  WITH all_orgs\n"
        "  UNWIND apoc.coll.frequencies(all_orgs) AS f\n"
        "  WITH f.item AS organism_name, f.count AS count\n"
        "  ORDER BY count DESC LIMIT 10\n"
        "  RETURN collect({organism_name: organism_name, count: count}) "
        "AS top_organisms\n"
        "}\n"
    )
    top_pathways_block = (
        "CALL {\n"
        "  WITH all_pwys\n"
        "  UNWIND apoc.coll.frequencies(all_pwys) AS f\n"
        "  WITH f.item AS metabolite_pathway_id, f.count AS count\n"
        "  ORDER BY count DESC LIMIT 10\n"
        "  OPTIONAL MATCH (p:KeggTerm {id: metabolite_pathway_id})\n"
        "  RETURN collect({\n"
        "    metabolite_pathway_id: metabolite_pathway_id,\n"
        "    metabolite_pathway_name: p.name,\n"
        "    count: count\n"
        "  }) AS top_metabolite_pathways\n"
        "}\n"
    )

    if search_text:
        # Search variant: fulltext entry point + score collection. Pull
        # total_entries from a small unfiltered Metabolite count after
        # the filtered aggregation.
        cypher = (
            "CALL db.index.fulltext.queryNodes('metaboliteFullText', $search)\n"
            "YIELD node AS m, score\n"
            f"{where_block}"
            "WITH count(m) AS total_matching,\n"
            "     apoc.coll.flatten(\n"
            "       collect(coalesce(m.evidence_sources, []))) AS es,\n"
            "     apoc.coll.flatten(\n"
            "       collect(coalesce(m.organism_names, []))) AS all_orgs,\n"
            "     apoc.coll.flatten(\n"
            "       collect(coalesce(m.pathway_ids, []))) AS all_pwys,\n"
            "     count(m.chebi_id) AS with_chebi,\n"
            "     count(m.hmdb_id) AS with_hmdb,\n"
            "     count(m.mnxm_id) AS with_mnxm,\n"
            "     collect(m.mass) AS masses,\n"
            "     collect(score) AS scores,\n"
            "     collect(coalesce(m.measured_paper_count, 0)) AS paper_counts,\n"
            "     apoc.coll.flatten(\n"
            "       collect(coalesce(m.measured_compartments, []))) AS m_comps\n"
            "MATCH (m2:Metabolite)\n"
            "WITH count(m2) AS total_entries, total_matching, es, all_orgs, "
            "all_pwys, with_chebi, with_hmdb, with_mnxm, masses, scores, "
            "paper_counts, m_comps\n"
            f"{top_organisms_block}"
            f"{top_pathways_block}"
            "RETURN total_entries, total_matching,\n"
            "       apoc.coll.frequencies(es) AS by_evidence_source,\n"
            "       with_chebi, with_hmdb, with_mnxm,\n"
            "       apoc.coll.min(masses) AS mass_min,\n"
            "       apoc.coll.sort(masses)[size(masses)/2] AS mass_median,\n"
            "       apoc.coll.max(masses) AS mass_max,\n"
            "       apoc.coll.max(scores) AS score_max,\n"
            "       apoc.coll.sort(scores)[size(scores)/2] AS score_median,\n"
            "       top_organisms, top_metabolite_pathways,\n"
            "       {\n"
            "         by_paper_count: apoc.coll.frequencies(paper_counts),\n"
            "         by_compartment: apoc.coll.frequencies(m_comps)\n"
            "       } AS by_measurement_coverage"
        )
    else:
        # OPTIONAL MATCH preserves the total_entries row when the filtered
        # MATCH returns zero rows — without it, an empty filter intersection
        # collapses to 0 result rows and callers IndexError on summary[0].
        cypher = (
            "MATCH (m:Metabolite)\n"
            "WITH count(m) AS total_entries\n"
            "OPTIONAL MATCH (m:Metabolite)\n"
            f"{where_block}"
            "WITH total_entries,\n"
            "     count(m) AS total_matching,\n"
            "     apoc.coll.flatten(\n"
            "       collect(coalesce(m.evidence_sources, []))) AS es,\n"
            "     apoc.coll.flatten(\n"
            "       collect(coalesce(m.organism_names, []))) AS all_orgs,\n"
            "     apoc.coll.flatten(\n"
            "       collect(coalesce(m.pathway_ids, []))) AS all_pwys,\n"
            "     count(m.chebi_id) AS with_chebi,\n"
            "     count(m.hmdb_id) AS with_hmdb,\n"
            "     count(m.mnxm_id) AS with_mnxm,\n"
            "     collect(m.mass) AS masses,\n"
            "     collect(coalesce(m.measured_paper_count, 0)) AS paper_counts,\n"
            "     apoc.coll.flatten(\n"
            "       collect(coalesce(m.measured_compartments, []))) AS m_comps\n"
            f"{top_organisms_block}"
            f"{top_pathways_block}"
            "RETURN total_entries, total_matching,\n"
            "       apoc.coll.frequencies(es) AS by_evidence_source,\n"
            "       with_chebi, with_hmdb, with_mnxm,\n"
            "       apoc.coll.min(masses) AS mass_min,\n"
            "       apoc.coll.sort(masses)[size(masses)/2] AS mass_median,\n"
            "       apoc.coll.max(masses) AS mass_max,\n"
            "       top_organisms, top_metabolite_pathways,\n"
            "       {\n"
            "         by_paper_count: apoc.coll.frequencies(paper_counts),\n"
            "         by_compartment: apoc.coll.frequencies(m_comps)\n"
            "       } AS by_measurement_coverage"
        )

    return cypher, params


def build_list_gene_categories() -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene) WHERE g.gene_category IS NOT NULL\n"
        "RETURN g.gene_category AS category, count(*) AS gene_count\n"
        "ORDER BY gene_count DESC"
    )
    return cypher, {}


def build_list_brite_trees() -> tuple[str, dict]:
    """List BRITE trees with term counts.

    RETURN keys: tree, tree_code, term_count.
    """
    cypher = (
        "MATCH (b:BriteCategory)\n"
        "RETURN b.tree AS tree, b.tree_code AS tree_code, "
        "count(*) AS term_count\n"
        "ORDER BY b.tree"
    )
    return cypher, {}


def build_list_growth_phases() -> tuple[str, dict]:
    """List distinct growth_phase values with experiment counts.

    RETURN keys: phase, experiment_count.
    """
    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(:Gene)\n"
        "WITH r.growth_phase AS phase, e.id AS eid\n"
        "WITH phase, count(DISTINCT eid) AS experiment_count\n"
        "WHERE phase IS NOT NULL\n"
        "RETURN phase, experiment_count\n"
        "ORDER BY experiment_count DESC, phase"
    )
    return cypher, {}


def build_list_metric_types() -> tuple[str, dict]:
    """List distinct DerivedMetric.metric_type values with DM counts.

    RETURN keys: value, count.
    """
    cypher = (
        "MATCH (dm:DerivedMetric) WHERE dm.metric_type IS NOT NULL\n"
        "RETURN dm.metric_type AS value, count(*) AS count\n"
        "ORDER BY count DESC, value"
    )
    return cypher, {}


def build_list_value_kinds() -> tuple[str, dict]:
    """List DerivedMetric.value_kind enum values with DM counts per kind.

    RETURN keys: value, count. Today's KG: {numeric, boolean, categorical}.
    """
    cypher = (
        "MATCH (dm:DerivedMetric) WHERE dm.value_kind IS NOT NULL\n"
        "RETURN dm.value_kind AS value, count(*) AS count\n"
        "ORDER BY count DESC, value"
    )
    return cypher, {}


def build_list_compartments() -> tuple[str, dict]:
    """List distinct Experiment.compartment values with experiment counts.

    Sourced from Experiment.compartment (wet-lab fraction), per slice-2 D7.

    RETURN keys: value, count.
    """
    cypher = (
        "MATCH (e:Experiment) WHERE e.compartment IS NOT NULL\n"
        "RETURN e.compartment AS value, count(*) AS count\n"
        "ORDER BY count DESC, value"
    )
    return cypher, {}


def build_list_omics_types() -> tuple[str, dict]:
    """List distinct Experiment.omics_type values with experiment counts.

    Sourced from Experiment.omics_type (per spec §6.5). Live distinct
    values: 8 categories. The Python wrapper layer is expected to merge
    this with the canonical OMICS_TYPE enum so values like METABOLOMICS
    appear with count=0 when no experiments of that type exist yet.

    RETURN keys: value, count.
    """
    cypher = (
        "MATCH (e:Experiment) WHERE e.omics_type IS NOT NULL\n"
        "RETURN e.omics_type AS value, count(*) AS count\n"
        "ORDER BY count DESC, value"
    )
    return cypher, {}


def build_list_evidence_sources() -> tuple[str, dict]:
    """List Metabolite.evidence_sources buckets with metabolite counts.

    Sourced from Metabolite.evidence_sources array (per spec §6.5).
    Live distribution: metabolism=2188, transport=1355, metabolomics=107.

    RETURN keys: value, count.
    """
    cypher = (
        "MATCH (m:Metabolite)\n"
        "UNWIND coalesce(m.evidence_sources, []) AS src\n"
        "RETURN src AS value, count(*) AS count\n"
        "ORDER BY count DESC, value"
    )
    return cypher, {}


def build_list_organisms(
    *,
    organism_names_lc: list[str] | None = None,
    compartment: str | None = None,
    verbose: bool = False,
) -> tuple[str, dict]:
    """Build Cypher for listing organisms with data-availability signals.

    organism_names_lc: optional list of lowercased preferred_names. When
        None, returns all organisms. When non-None, restricts to organisms
        whose preferred_name (lowercased) is in the list.
    compartment: optional Experiment.compartment value (e.g. 'vesicle')
        to restrict to organisms whose compartments list includes it.

    RETURN keys (compact): organism_name, organism_type, genus, species,
    strain, clade, ncbi_taxon_id, gene_count, publication_count,
    experiment_count, treatment_types, background_factors, omics_types,
    clustering_analysis_count, cluster_types, derived_metric_count,
    derived_metric_value_kinds, compartments, reaction_count,
    catalyzed_metabolite_count, transported_metabolite_count,
    measured_metabolite_count, peptidase_gene_count,
    nonpeptidase_homolog_gene_count, interpro_gene_count, ncbifam_gene_count,
    reference_database, reference_proteome, growth_phases.
    RETURN keys (verbose): adds family, order, tax_class, phylum, kingdom,
    superkingdom, lineage, cluster_count, derived_metric_gene_count,
    derived_metric_types.
    """
    verbose_cols = (
        ",\n       o.family AS family,"
        "\n       o.order AS order,"
        "\n       o.tax_class AS tax_class,"
        "\n       o.phylum AS phylum,"
        "\n       o.kingdom AS kingdom,"
        "\n       o.superkingdom AS superkingdom,"
        "\n       o.lineage AS lineage,"
        "\n       coalesce(o.cluster_count, 0) AS cluster_count,"
        "\n       coalesce(o.derived_metric_gene_count, 0) AS derived_metric_gene_count,"
        "\n       coalesce(o.derived_metric_types, []) AS derived_metric_types"
        if verbose else ""
    )

    conditions = [
        "($organism_names_lc IS NULL"
        " OR toLower(o.preferred_name) IN $organism_names_lc)"
    ]
    params: dict = {"organism_names_lc": organism_names_lc}
    if compartment is not None:
        conditions.append("$compartment IN coalesce(o.compartments, [])")
        params["compartment"] = compartment

    where_block = "WHERE " + "\n  AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        f"{where_block}"
        "RETURN o.preferred_name AS organism_name,\n"
        "       o.organism_type AS organism_type,\n"
        "       o.genus AS genus,\n"
        "       o.species AS species,\n"
        "       o.strain_name AS strain,\n"
        "       o.clade AS clade,\n"
        "       o.ncbi_taxon_id AS ncbi_taxon_id,\n"
        "       o.gene_count AS gene_count,\n"
        "       o.publication_count AS publication_count,\n"
        "       o.experiment_count AS experiment_count,\n"
        "       o.treatment_types AS treatment_types,\n"
        "       coalesce(o.background_factors, []) AS background_factors,\n"
        "       o.omics_types AS omics_types,\n"
        "       coalesce(o.clustering_analysis_count, 0) AS clustering_analysis_count,\n"
        "       coalesce(o.cluster_types, []) AS cluster_types,\n"
        "       coalesce(o.derived_metric_count, 0) AS derived_metric_count,\n"
        "       coalesce(o.derived_metric_value_kinds, []) AS derived_metric_value_kinds,\n"
        "       coalesce(o.compartments, []) AS compartments,\n"
        "       coalesce(o.reaction_count, 0) AS reaction_count,\n"
        "       coalesce(o.catalyzed_metabolite_count, 0) AS catalyzed_metabolite_count,\n"
        "       coalesce(o.transported_metabolite_count, 0) AS transported_metabolite_count,\n"
        "       coalesce(o.measured_metabolite_count, 0) AS measured_metabolite_count,\n"
        "       coalesce(o.peptidase_gene_count, 0) AS peptidase_gene_count,\n"
        "       coalesce(o.nonpeptidase_homolog_gene_count, 0) AS nonpeptidase_homolog_gene_count,\n"
        "       coalesce(o.interpro_gene_count, 0) AS interpro_gene_count,\n"
        "       coalesce(o.ncbifam_gene_count, 0) AS ncbifam_gene_count,\n"
        "       o.reference_database AS reference_database,\n"
        "       o.reference_proteome AS reference_proteome,\n"
        "       coalesce(o.growth_phases, []) AS growth_phases"
        f"{verbose_cols}\n"
        "ORDER BY o.genus, o.preferred_name"
    )
    return cypher, params


def build_list_organisms_summary(
    *,
    organism_names_lc: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[str, dict]:
    """Summary count + DM/compartment/cluster/organism-type rollups across matched organisms.

    RETURN keys: total_entries, total_matching, by_value_kind,
    by_metric_type, by_compartment, by_cluster_type, by_organism_type,
    by_measurement_capability, top_annotation_capability (top-10 by
    peptidase_gene_count desc then preferred_name; entries carry
    preferred_name, organism_name + the four ORG-001 counts; all-four-zero
    organisms excluded).
    """
    conditions = [
        "($organism_names_lc IS NULL"
        " OR toLower(o.preferred_name) IN $organism_names_lc)"
    ]
    params: dict = {"organism_names_lc": organism_names_lc}
    if compartment is not None:
        conditions.append("$compartment IN coalesce(o.compartments, [])")
        params["compartment"] = compartment
    where_block = "WHERE " + "\n  AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        "WITH count(o) AS total_entries\n"
        "OPTIONAL MATCH (o:OrganismTaxon)\n"
        f"{where_block}"
        "WITH total_entries,\n"
        "     count(o) AS total_matching,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(o.derived_metric_value_kinds, []))) AS vks,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(o.derived_metric_types, []))) AS mtypes,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(o.compartments, []))) AS comps,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(o.cluster_types, []))) AS ctypes,\n"
        "     collect(o.organism_type) AS otypes,\n"
        "     collect(coalesce(o.measured_metabolite_count, 0)) AS mmc,\n"
        "     collect({\n"
        "       preferred_name: o.preferred_name,\n"
        "       organism_name: o.preferred_name,\n"
        "       peptidase_gene_count: coalesce(o.peptidase_gene_count, 0),\n"
        "       nonpeptidase_homolog_gene_count:\n"
        "         coalesce(o.nonpeptidase_homolog_gene_count, 0),\n"
        "       interpro_gene_count: coalesce(o.interpro_gene_count, 0),\n"
        "       ncbifam_gene_count: coalesce(o.ncbifam_gene_count, 0)\n"
        "     }) AS ann\n"
        "RETURN total_entries, total_matching,\n"
        "       apoc.coll.frequencies(vks) AS by_value_kind,\n"
        "       apoc.coll.frequencies(mtypes) AS by_metric_type,\n"
        "       apoc.coll.frequencies(comps) AS by_compartment,\n"
        "       apoc.coll.frequencies(ctypes) AS by_cluster_type,\n"
        "       apoc.coll.frequencies(otypes) AS by_organism_type,\n"
        "       {\n"
        "         has_metabolomics: size([c IN mmc WHERE c > 0]),\n"
        "         no_metabolomics: size([c IN mmc WHERE c = 0])\n"
        "       } AS by_measurement_capability,\n"
        "       apoc.coll.sortMulti(\n"
        "         [a IN ann WHERE a.peptidase_gene_count > 0\n"
        "            OR a.nonpeptidase_homolog_gene_count > 0\n"
        "            OR a.interpro_gene_count > 0\n"
        "            OR a.ncbifam_gene_count > 0],\n"
        "         ['peptidase_gene_count', '^preferred_name'])[0..10]\n"
        "       AS top_annotation_capability"
    )
    return cypher, params


def build_list_organisms_capability(
    *,
    organism_names_lc: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[str, dict]:
    """Build Cypher for the small chemistry-capability projection used by
    list_organisms's top_metabolic_capability envelope rollup in summary mode.

    Returns only (organism_name, reaction_count, catalyzed_metabolite_count,
    transported_metabolite_count, measured_metabolite_count) per matched
    organism — the minimum needed to compute the rollup without pulling the
    full detail row set. Used when limit=0 so the summary fast path stays
    cheap; detail-mode callers (limit>0) source the same data from the
    regular detail builder rows already in flight.

    Same WHERE clause as build_list_organisms / build_list_organisms_summary
    so the matched set is identical.

    RETURN keys: organism_name, reaction_count, catalyzed_metabolite_count,
    transported_metabolite_count, measured_metabolite_count,
    peptidase_gene_count, nonpeptidase_homolog_gene_count, interpro_gene_count,
    ncbifam_gene_count (feeds top_annotation_capability api-side).
    """
    conditions = [
        "($organism_names_lc IS NULL"
        " OR toLower(o.preferred_name) IN $organism_names_lc)"
    ]
    params: dict = {"organism_names_lc": organism_names_lc}
    if compartment is not None:
        conditions.append("$compartment IN coalesce(o.compartments, [])")
        params["compartment"] = compartment

    where_block = "WHERE " + "\n  AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        f"{where_block}"
        "RETURN o.preferred_name AS organism_name,\n"
        "       coalesce(o.reaction_count, 0) AS reaction_count,\n"
        "       coalesce(o.catalyzed_metabolite_count, 0) AS catalyzed_metabolite_count,\n"
        "       coalesce(o.transported_metabolite_count, 0) AS transported_metabolite_count,\n"
        "       coalesce(o.measured_metabolite_count, 0) AS measured_metabolite_count,\n"
        "       coalesce(o.peptidase_gene_count, 0) AS peptidase_gene_count,\n"
        "       coalesce(o.nonpeptidase_homolog_gene_count, 0) AS nonpeptidase_homolog_gene_count,\n"
        "       coalesce(o.interpro_gene_count, 0) AS interpro_gene_count,\n"
        "       coalesce(o.ncbifam_gene_count, 0) AS ncbifam_gene_count\n"
        "ORDER BY o.genus, o.preferred_name"
    )
    return cypher, params


def _list_experiments_where(
    *,
    organism: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
    coculture_partner: str | None = None,
    search_text: str | None = None,
    time_course_only: bool = False,
    table_scope: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[str, dict]:
    """Build WHERE clause and params for experiment queries.

    Shared between build_list_experiments and build_list_experiments_summary.
    search_text is not added to WHERE — it controls which Cypher variant
    is used (fulltext entry point vs MATCH). The $search_text param is
    added to params when search_text is provided.
    """
    conditions: list[str] = []
    params: dict = {}

    if search_text:
        params["search_text"] = search_text

    if organism:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(e.organism_name) CONTAINS word)"
        )
        params["organism"] = organism

    if treatment_type:
        conditions.append(
            "ANY(t IN e.treatment_type WHERE toLower(t) IN $treatment_types)"
        )
        params["treatment_types"] = [t.lower() for t in treatment_type]

    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(e.background_factors, [])"
            " WHERE toLower(bf) IN $background_factors)"
        )
        params["background_factors"] = [bf.lower() for bf in background_factors]

    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(e.growth_phases, [])"
            " WHERE toLower(gp) IN $growth_phases)"
        )
        params["growth_phases"] = [gp.lower() for gp in growth_phases]

    if omics_type:
        conditions.append("toUpper(e.omics_type) IN $omics_types")
        params["omics_types"] = [t.upper() for t in omics_type]

    if publication_doi:
        conditions.append("toLower(p.doi) IN $dois")
        params["dois"] = [d.lower() for d in publication_doi]

    if coculture_partner:
        conditions.append(
            "toLower(e.coculture_partner) CONTAINS toLower($partner)"
        )
        params["partner"] = coculture_partner

    if time_course_only:
        conditions.append("e.is_time_course = 'time_course'")

    if table_scope:
        conditions.append("e.table_scope IN $table_scopes")
        params["table_scopes"] = table_scope

    if experiment_ids:
        conditions.append("e.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids

    if compartment is not None:
        conditions.append("e.compartment = $compartment")
        params["compartment"] = compartment

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
    return where_block, params


def build_list_experiments(
    *,
    organism: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
    coculture_partner: str | None = None,
    search_text: str | None = None,
    time_course_only: bool = False,
    table_scope: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    compartment: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for listing experiments with precomputed gene count stats.

    RETURN keys (compact): experiment_id, experiment_name, publication_doi,
    authors, organism_name, treatment_type, coculture_partner, omics_type,
    is_time_course, table_scope, table_scope_detail,
    gene_count, distinct_gene_count, significant_up_count,
    significant_down_count, time_point_count, time_point_labels,
    time_point_orders, time_point_hours, time_point_totals,
    time_point_significant_up, time_point_significant_down,
    clustering_analysis_count, cluster_types, growth_phases,
    time_point_growth_phases, derived_metric_count,
    derived_metric_value_kinds, compartment.
    RETURN keys (verbose): adds publication_title, treatment,
    control, light_condition, light_intensity, medium, temperature,
    statistical_test, experimental_context, cluster_count,
    derived_metric_gene_count, derived_metric_types,
    reports_derived_metric_types.
    RETURN keys (search_text): adds score.
    compartment: when provided, restricts to experiments in that wet-lab
    compartment (scalar equality: e.compartment = $compartment).

    Note on derived_metric_types vs reports_derived_metric_types:
    Both fields are sourced from ``e.reports_derived_metric_types`` today —
    the KG only stores a single report-side rollup on the Experiment node.
    They are identical in current data and are both surfaced for
    forward-compat with a future KG distinction between "DMs reported by
    this experiment" and "DMs associated with this experiment" (per
    slice-2 design D5).
    """
    where_block, params = _list_experiments_where(
        organism=organism, treatment_type=treatment_type,
        omics_type=omics_type, publication_doi=publication_doi,
        coculture_partner=coculture_partner, search_text=search_text,
        time_course_only=time_course_only, table_scope=table_scope,
        background_factors=background_factors, growth_phases=growth_phases,
        experiment_ids=experiment_ids, compartment=compartment,
    )

    verbose_cols = (
        ",\n       p.title AS publication_title,"
        "\n       e.treatment AS treatment,"
        "\n       e.control AS control,"
        "\n       e.light_condition AS light_condition,"
        "\n       e.light_intensity AS light_intensity,"
        "\n       e.medium AS medium,"
        "\n       e.temperature AS temperature,"
        "\n       e.statistical_test AS statistical_test,"
        "\n       e.experimental_context AS experimental_context,"
        "\n       coalesce(e.cluster_count, 0) AS cluster_count,"
        "\n       coalesce(e.derived_metric_gene_count, 0) AS derived_metric_gene_count,"
        "\n       coalesce(e.reports_derived_metric_types, []) AS derived_metric_types,"
        "\n       coalesce(e.reports_derived_metric_types, []) AS reports_derived_metric_types"
        if verbose else ""
    )

    if offset:
        skip_clause = "SKIP $offset\n"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "LIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    return_cols = (
        "e.id AS experiment_id,\n"
        "       e.name AS experiment_name,\n"
        "       p.doi AS publication_doi,\n"
        "       coalesce(p.authors, []) AS authors,\n"
        "       e.organism_name AS organism_name,\n"
        "       e.treatment_type AS treatment_type,\n"
        "       coalesce(e.background_factors, []) AS background_factors,\n"
        "       e.coculture_partner AS coculture_partner,\n"
        "       e.omics_type AS omics_type,\n"
        "       e.is_time_course AS is_time_course,\n"
        "       e.table_scope AS table_scope,\n"
        "       e.table_scope_detail AS table_scope_detail,\n"
        "       e.gene_count AS gene_count,\n"
        "       e.distinct_gene_count AS distinct_gene_count,\n"
        "       e.significant_up_count AS significant_up_count,\n"
        "       e.significant_down_count AS significant_down_count,\n"
        "       e.time_point_count AS time_point_count,\n"
        "       e.time_point_labels AS time_point_labels,\n"
        "       e.time_point_orders AS time_point_orders,\n"
        "       e.time_point_hours AS time_point_hours,\n"
        "       e.time_point_totals AS time_point_totals,\n"
        "       e.time_point_significant_up AS time_point_significant_up,\n"
        "       e.time_point_significant_down AS time_point_significant_down,\n"
        "       coalesce(e.clustering_analysis_count, 0) AS clustering_analysis_count,\n"
        "       coalesce(e.cluster_types, []) AS cluster_types"
        ",\n       coalesce(e.growth_phases, []) AS growth_phases"
        ",\n       coalesce(e.time_point_growth_phases, []) AS time_point_growth_phases"
        ",\n       coalesce(e.derived_metric_count, 0) AS derived_metric_count"
        ",\n       coalesce(e.derived_metric_value_kinds, []) AS derived_metric_value_kinds"
        ",\n       e.compartment AS compartment"
        ",\n       coalesce(e.metabolite_count, 0) AS metabolite_count"
        ",\n       coalesce(e.metabolite_assay_count, 0) AS metabolite_assay_count"
        ",\n       coalesce(e.metabolite_compartments, []) AS metabolite_compartments"
    )

    if search_text:
        cypher = (
            "CALL db.index.fulltext.queryNodes('experimentFullText', $search_text)\n"
            "YIELD node AS e, score\n"
            "MATCH (p:Publication)-[:Has_experiment]->(e)\n"
            f"{where_block}"
            f"RETURN {return_cols},\n"
            f"       score{verbose_cols}\n"
            f"ORDER BY score DESC, e.organism_name, e.name\n"
            f"{skip_clause}{limit_clause}"
        )
    else:
        cypher = (
            "MATCH (p:Publication)-[:Has_experiment]->(e:Experiment)\n"
            f"{where_block}"
            f"RETURN {return_cols}{verbose_cols}\n"
            f"ORDER BY p.publication_year DESC, e.organism_name, e.name\n"
            f"{skip_clause}{limit_clause}"
        )

    return cypher, params


def build_list_experiments_summary(
    *,
    organism: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
    coculture_partner: str | None = None,
    search_text: str | None = None,
    time_course_only: bool = False,
    table_scope: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[str, dict]:
    """Build summary aggregation Cypher for list_experiments.

    Returns breakdowns by organism, treatment type, omics type,
    publication, table_scope, background_factors, cluster_type,
    growth_phase, and DM rollups using apoc.coll.frequencies.

    RETURN keys: total_matching, time_course_count, by_organism,
    by_treatment_type, by_background_factors, by_omics_type, by_publication,
    by_table_scope, by_cluster_type, by_growth_phase,
    by_value_kind, by_metric_type, by_compartment.
    RETURN keys (search_text): adds score_max, score_median.

    Note: e.compartment is a scalar string, so we use collect(e.compartment)
    directly (no apoc.coll.flatten) for the by_compartment rollup.
    """
    where_block, params = _list_experiments_where(
        organism=organism, treatment_type=treatment_type,
        omics_type=omics_type, publication_doi=publication_doi,
        coculture_partner=coculture_partner, search_text=search_text,
        time_course_only=time_course_only, table_scope=table_scope,
        background_factors=background_factors, growth_phases=growth_phases,
        experiment_ids=experiment_ids, compartment=compartment,
    )

    collect_cols = (
        "collect(e.organism_name) AS orgs,\n"
        "     apoc.coll.flatten(collect(coalesce(e.treatment_type, []))) AS tts,\n"
        "     apoc.coll.flatten(collect(coalesce(e.background_factors, []))) AS bfs,\n"
        "     collect(e.omics_type) AS omics,\n"
        "     collect(p.doi) AS dois,\n"
        "     collect(e.is_time_course) AS tc,\n"
        "     collect(e.table_scope) AS scopes,\n"
        "     apoc.coll.flatten(collect(coalesce(e.cluster_types, []))) AS ctypes"
        ",\n     apoc.coll.flatten(collect(coalesce(e.growth_phases, []))) AS gps"
        ",\n     apoc.coll.flatten(\n"
        "       collect(coalesce(e.derived_metric_value_kinds, []))) AS vks"
        ",\n     apoc.coll.flatten(\n"
        "       collect(coalesce(e.reports_derived_metric_types, []))) AS mtypes"
        ",\n     collect(e.compartment) AS comps"
    )

    return_cols = (
        "size(orgs) AS total_matching,\n"
        "       size([x IN tc WHERE x = 'time_course']) AS time_course_count,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(tts) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(bfs) AS by_background_factors,\n"
        "       apoc.coll.frequencies(omics) AS by_omics_type,\n"
        "       apoc.coll.frequencies(dois) AS by_publication,\n"
        "       apoc.coll.frequencies(scopes) AS by_table_scope,\n"
        "       apoc.coll.frequencies(ctypes) AS by_cluster_type"
        ",\n       apoc.coll.frequencies(gps) AS by_growth_phase"
        ",\n       apoc.coll.frequencies(vks) AS by_value_kind"
        ",\n       apoc.coll.frequencies(mtypes) AS by_metric_type"
        ",\n       apoc.coll.frequencies(comps) AS by_compartment"
    )

    if search_text:
        cypher = (
            "CALL db.index.fulltext.queryNodes('experimentFullText', $search_text)\n"
            "YIELD node AS e, score\n"
            "MATCH (p:Publication)-[:Has_experiment]->(e)\n"
            f"{where_block}"
            f"WITH {collect_cols},\n"
            "     max(score) AS score_max,\n"
            "     percentileDisc(score, 0.5) AS score_median\n"
            f"RETURN {return_cols},\n"
            "       score_max, score_median"
        )
    else:
        cypher = (
            "MATCH (p:Publication)-[:Has_experiment]->(e:Experiment)\n"
            f"{where_block}"
            f"WITH {collect_cols}\n"
            f"RETURN {return_cols}"
        )

    # total_entries: unfiltered count appended as a subquery
    # API layer runs this separately or uses UNION — implementation detail
    return cypher, params


def _is_browse(search_text: str | None) -> bool:
    """`search_text` None / '' / whitespace selects browse mode (spec §7.4)."""
    return search_text is None or not search_text.strip()


def _search_ontology_term_verbose_props(cfg: dict) -> list[str]:
    """Term-side verbose columns for search_ontology (design §3.4).

    `description`, `level_kind`, `direct_gene_count` (hierarchical labels
    only — flat ontologies have no rollup so the prop does not exist), then
    the registry `term_verbose` union.
    """
    props = ["description", "level_kind"]
    if cfg["hierarchy_rels"]:
        props.append("direct_gene_count")
    for prop in cfg.get("term_verbose") or []:
        if prop not in props:
            props.append(prop)
    return props


def _search_ontology_org_scope(cfg: dict, *, indent: str) -> str:
    """OPTIONAL MATCH counting one organism's genes in `t`'s SUBTREE.

    Same scope as the term's `gene_count` and as
    `ontology_term_details.organism_gene_count` (backlog 2.2 — was the
    direct edge only): hierarchical ontologies walk `hierarchy_rels*0..`
    down to descendants before the registry `gene_rel`; BRITE additionally
    crosses its `bridge` (KEGG term); Pfam walks `*0..1` so a clan row
    counts its member domains' genes; flat ontologies read the direct edge.
    """
    gene_rel = cfg["gene_rel"]
    bridge = cfg.get("bridge")
    org_gene = "(g:Gene {organism_name: $organism})"
    hier = cfg.get("hierarchy_rels") or []
    if bridge:
        walk = f"<-[:{'|'.join(hier)}*0..]-(:{cfg['label']})" if hier else ""
        pattern = (
            f"(t){walk}<-[:{bridge['edge']}]-(:{bridge['node_label']})"
            f"<-[:{gene_rel}]-{org_gene}"
        )
    elif cfg.get("parent_label"):
        rel_union = "|".join(hier)
        pattern = (
            f"(t)<-[:{rel_union}*0..1]-(:{cfg['label']})"
            f"<-[:{gene_rel}]-{org_gene}"
        )
    elif hier:
        pattern = (
            f"(t)<-[:{'|'.join(hier)}*0..]-(:{cfg['label']})"
            f"<-[:{gene_rel}]-{org_gene}"
        )
    else:
        pattern = f"(t)<-[:{gene_rel}]-{org_gene}"
    return f"{indent}OPTIONAL MATCH {pattern}\n"


def _search_ontology_predicates(
    *, level, facet, informative_only, min_gene_count, organism, params,
) -> tuple[list[str], str]:
    """Shared term-side WHERE parts + the organism-scope post-filter."""
    where_parts: list[str] = []
    if level is not None:
        where_parts.append("t.level = $level")
        params["level"] = level
    if facet is not None:
        facet_prop, facet_param, facet_value = facet
        where_parts.append(f"t.{facet_prop} = ${facet_param}")
        params[facet_param] = facet_value
    if informative_only:
        where_parts.append("coalesce(t.is_uninformative, '') <> 'true'")
    org_where = ""
    if min_gene_count is not None:
        params["min_gene_count"] = min_gene_count
        if organism is None:
            where_parts.append("t.gene_count >= $min_gene_count")
        else:
            org_where = "WHERE org_gene_count >= $min_gene_count\n"
    if organism is not None:
        params["organism"] = organism
    return where_parts, org_where


def build_search_ontology_summary(
    *, ontology: str, search_text: str | None = None,
    level: int | None = None,
    tree: str | None = None,
    informative_only: bool = False,
    interpro_type: str | None = None,
    min_gene_count: int | None = None,
    organism: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for search_ontology.

    `search_text` None / empty selects browse mode (spec §7.4): a plain
    label MATCH with no fulltext CALL; `score_max` / `score_median` are null
    and `by_level` ([{level, count}]) rolls up the FULL match. Search mode
    keeps its existing Cypher.

    `interpro_type` is the InterPro term facet (spec §7.4) — the same
    `facet` config entry BRITE's `tree` uses. `min_gene_count` filters on the
    node `gene_count` (or, with `organism`, on the per-organism count).

    RETURN keys: total_entries, total_matching, score_max, score_median;
    browse adds by_level.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    facet = _resolve_facet(ontology, tree=tree, interpro_type=interpro_type)
    cfg = ONTOLOGY_CONFIG[ontology]
    index_name = cfg["fulltext_index"]
    parent_index = cfg.get("parent_fulltext_index")
    browse = _is_browse(search_text)

    params: dict = {} if browse else {"search_text": search_text}
    where_parts, org_where = _search_ontology_predicates(
        level=level, facet=facet, informative_only=informative_only,
        min_gene_count=min_gene_count, organism=organism, params=params,
    )
    label = cfg["label"]

    if browse:
        if parent_index:
            where_parts.insert(0, f"(t:{label} OR t:{cfg['parent_label']})")
            match = "MATCH (t)\n"
            total_entries = (
                f"CALL {{ MATCH (all_t:{label}) RETURN count(all_t) AS pfam_count }}\n"
                f"CALL {{ MATCH (all_c:{cfg['parent_label']}) "
                "RETURN count(all_c) AS clan_count }\n"
                "RETURN pfam_count + clan_count AS total_entries,\n"
            )
        else:
            match = f"MATCH (t:{label})\n"
            total_entries = (
                f"CALL {{ MATCH (all_t:{label}) RETURN count(all_t) AS total_entries }}\n"
                "RETURN total_entries,\n"
            )
        where_clause = (
            "WHERE " + " AND ".join(where_parts) + "\n" if where_parts else ""
        )
        org_block = ""
        if organism is not None:
            org_block = (
                _search_ontology_org_scope(cfg, indent="")
                + "WITH t, count(DISTINCT g) AS org_gene_count\n"
                + org_where
            )
        cypher = (
            match
            + where_clause
            + org_block
            + "WITH count(t) AS total_matching,\n"
            "     [x IN apoc.coll.frequencies(collect(t.level))"
            " | {level: x.item, count: x.count}] AS by_level\n"
            + total_entries
            + "       total_matching, null AS score_max, null AS score_median,\n"
            "       by_level"
        )
        return cypher, params

    where_clause = "  WHERE " + " AND ".join(where_parts) + "\n" if where_parts else ""
    # Organism scope in search mode: count the organism's genes per term and
    # apply the per-organism floor after the fulltext YIELD.
    org_inner = ""
    org_flat = ""
    if organism is not None:
        org_inner = (
            _search_ontology_org_scope(cfg, indent="  ")
            + "  WITH t, score, count(DISTINCT g) AS org_gene_count\n"
            + ("  " + org_where if org_where else "")
        )
        org_flat = (
            _search_ontology_org_scope(cfg, indent="")
            + "WITH t, score, count(DISTINCT g) AS org_gene_count\n"
            + org_where
        )

    if parent_index:
        cypher = (
            "CALL {\n"
            f"  CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "  YIELD node AS t, score\n"
            + where_clause
            + org_inner
            + "  RETURN score\n"
            "  UNION ALL\n"
            f"  CALL db.index.fulltext.queryNodes('{parent_index}', $search_text)\n"
            "  YIELD node AS t, score\n"
            + where_clause
            + org_inner
            + "  RETURN score\n"
            "}\n"
            "WITH count(score) AS total_matching,\n"
            "     max(score) AS score_max,\n"
            "     percentileDisc(score, 0.5) AS score_median\n"
            "CALL { MATCH (all_t:Pfam) RETURN count(all_t) AS pfam_count }\n"
            "CALL { MATCH (all_c:PfamClan) RETURN count(all_c) AS clan_count }\n"
            "RETURN pfam_count + clan_count AS total_entries,\n"
            "       total_matching, score_max, score_median"
        )
    else:
        cypher = (
            f"CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "YIELD node AS t, score\n"
            + where_clause
            + org_flat
            + "WITH count(t) AS total_matching,\n"
            "     max(score) AS score_max,\n"
            "     percentileDisc(score, 0.5) AS score_median\n"
            f"CALL {{ MATCH (all_t:{label}) RETURN count(all_t) AS total_entries }}\n"
            "RETURN total_entries, total_matching, score_max, score_median"
        )
    return cypher, params


def build_search_ontology(
    *, ontology: str, search_text: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    level: int | None = None,
    tree: str | None = None,
    informative_only: bool = False,
    verbose: bool = False,
    interpro_type: str | None = None,
    min_gene_count: int | None = None,
    organism: str | None = None,
) -> tuple[str, dict]:
    """Build Cypher for search_ontology.

    Two modes (spec §7.4):

    * search — `search_text` given: fulltext CALL, `ORDER BY score DESC, id`
      (existing Cypher, unchanged).
    * browse — `search_text` None / empty / whitespace: plain label MATCH
      (`MATCH (t:<label>)`; Pfam `MATCH (t) WHERE t:Pfam OR t:PfamClan`),
      no fulltext CALL, `null AS score`, `ORDER BY gene_count DESC, id`.

    `min_gene_count` filters on the node `gene_count`. With `organism`, the
    per-organism gene count is computed (`org_gene_count`, projected as
    `organism_gene_count`), the floor applies to it, and browse rows sort by
    `org_gene_count DESC, id` (search mode keeps `score DESC`).

    RETURN keys (compact): id, name, score, level, tree, tree_code,
    is_informative, gene_count, organism_count (`term_compact`), the facet
    column where owned (InterPro `interpro_type`), `organism_gene_count`
    when `organism` is set.
    Verbose adds description, level_kind, direct_gene_count (hierarchical
    labels only) and the registry `term_verbose` union.

    When the selected ontology's ONTOLOGY_CONFIG entry declares `discusses_rel`
    (KEGG only today), an extra per-row `discussed_by_n_publications`
    pattern-count column is emitted, and verbose adds the
    `discussed_in_publications` list of {doi, prominence, evidence}. Other
    ontologies pay no per-row subquery — the columns are simply absent.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    facet = _resolve_facet(ontology, tree=tree, interpro_type=interpro_type)
    cfg = ONTOLOGY_CONFIG[ontology]
    index_name = cfg["fulltext_index"]
    parent_index = cfg.get("parent_fulltext_index")
    browse = _is_browse(search_text)

    # Term-side compact counts (registry `term_compact`) plus the facet column
    # where the ontology owns one that is not already a first-class column.
    term_props = list(cfg["term_compact"])
    cfg_facet = cfg.get("facet")
    if cfg_facet and cfg_facet["prop"] not in _STANDARD_TERM_ROW_COLUMNS:
        term_props.append(cfg_facet["prop"])
    if verbose:
        term_props.extend(
            p for p in _search_ontology_term_verbose_props(cfg)
            if p not in term_props
        )
    # Inner projection is indented one level deeper inside the UNION subquery.
    term_cols = "".join(f",\n         t.{prop} AS {prop}" for prop in term_props)
    term_cols_flat = "".join(f",\n       t.{prop} AS {prop}" for prop in term_props)
    term_outer = "".join(f",\n       {prop}" for prop in term_props)
    if organism is not None:
        term_cols += ",\n         org_gene_count AS organism_gene_count"
        term_cols_flat += ",\n       org_gene_count AS organism_gene_count"
        term_outer += ",\n       organism_gene_count"

    # Publication "discusses" columns — config-gated (only ontologies whose
    # config declares `discusses_rel`, i.e. KEGG). Rel-type read from config,
    # never inlined as a literal, mirroring gene_rel / fulltext_index plumbing.
    discusses_rel = cfg.get("discusses_rel")
    if discusses_rel:
        discusses_count_col = (
            ",\n         size([(t)<-[:" + discusses_rel + "]-() | 1])"
            " AS discussed_by_n_publications"
        )
        discusses_verbose_col = (
            ",\n         [(t)<-[rdp:" + discusses_rel + "]-(pdp:Publication)"
            " | {doi: pdp.doi, prominence: rdp.prominence, evidence: rdp.evidence}]"
            " AS discussed_in_publications"
            if verbose else ""
        )
        discusses_outer = ",\n       discussed_by_n_publications" + (
            ", discussed_in_publications" if verbose else ""
        )
    else:
        discusses_count_col = ""
        discusses_verbose_col = ""
        discusses_outer = ""

    params: dict = {} if browse else {"search_text": search_text}
    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    limit_clause = "\nLIMIT $limit" if limit is not None else ""
    if limit is not None:
        params["limit"] = limit

    where_parts, org_where = _search_ontology_predicates(
        level=level, facet=facet, informative_only=informative_only,
        min_gene_count=min_gene_count, organism=organism, params=params,
    )
    inner_discusses = discusses_count_col + discusses_verbose_col

    if browse:
        label = cfg["label"]
        if parent_index:
            where_parts.insert(0, f"(t:{label} OR t:{cfg['parent_label']})")
            match = "MATCH (t)\n"
        else:
            match = f"MATCH (t:{label})\n"
        where_clause = (
            "WHERE " + " AND ".join(where_parts) + "\n" if where_parts else ""
        )
        if organism is not None:
            org_block = (
                _search_ontology_org_scope(cfg, indent="")
                + "WITH t, count(DISTINCT g) AS org_gene_count\n"
                + org_where
                + "WITH t, org_gene_count\n"
                "ORDER BY org_gene_count DESC, t.id"
            )
        else:
            org_block = "WITH t\nORDER BY t.gene_count DESC, t.id"
        cypher = (
            match
            + where_clause
            + org_block
            + skip_clause + limit_clause + "\n"
            "RETURN t.id AS id, t.name AS name, null AS score,\n"
            "       t.level AS level, t.tree AS tree, t.tree_code AS tree_code,\n"
            "       coalesce(t.is_uninformative, '') <> 'true' AS is_informative"
            + term_cols_flat
            + inner_discusses
        )
        return cypher, params

    where_clause = "  WHERE " + " AND ".join(where_parts) + "\n" if where_parts else ""
    org_inner = ""
    org_flat = ""
    if organism is not None:
        org_inner = (
            _search_ontology_org_scope(cfg, indent="  ")
            + "  WITH t, score, count(DISTINCT g) AS org_gene_count\n"
            + ("  " + org_where if org_where else "")
        )
        org_flat = (
            _search_ontology_org_scope(cfg, indent="")
            + "WITH t, score, count(DISTINCT g) AS org_gene_count\n"
            + org_where
        )

    if parent_index:
        # UNION search across both indexes (e.g. Pfam domain + clan)
        cypher = (
            "CALL {\n"
            f"  CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "  YIELD node AS t, score\n"
            + where_clause
            + org_inner
            + "  RETURN t.id AS id, t.name AS name, score,\n"
            "         t.level AS level, t.tree AS tree, t.tree_code AS tree_code,\n"
            "         coalesce(t.is_uninformative, '') <> 'true' AS is_informative"
            + term_cols + inner_discusses + "\n"
            "  UNION ALL\n"
            f"  CALL db.index.fulltext.queryNodes('{parent_index}', $search_text)\n"
            "  YIELD node AS t, score\n"
            + where_clause
            + org_inner
            + "  RETURN t.id AS id, t.name AS name, score,\n"
            "         t.level AS level, t.tree AS tree, t.tree_code AS tree_code,\n"
            "         coalesce(t.is_uninformative, '') <> 'true' AS is_informative"
            + term_cols + inner_discusses + "\n"
            "}\n"
            "RETURN id, name, score, level, tree, tree_code, is_informative"
            + term_outer + discusses_outer + "\n"
            "ORDER BY score DESC, id" + skip_clause + limit_clause
        )
    else:
        cypher = (
            f"CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "YIELD node AS t, score\n"
            + where_clause
            + org_flat
            + "RETURN t.id AS id, t.name AS name, score,\n"
            "       t.level AS level, t.tree AS tree, t.tree_code AS tree_code,\n"
            "       coalesce(t.is_uninformative, '') <> 'true' AS is_informative"
            + term_cols_flat
            + inner_discusses + "\n"
            "ORDER BY score DESC, id" + skip_clause + limit_clause
        )
    return cypher, params


# Ontology key → expected node label(s). Single-label ontologies get a
# one-element list; pfam accepts both Pfam (level 1) and PfamClan (level 0).
# Derived from ONTOLOGY_CONFIG so adding a new ontology is one-place.
_ONTOLOGY_LABELS: dict[str, list[str]] = {
    key: (
        [cfg["label"], cfg["parent_label"]]
        if "parent_label" in cfg else [cfg["label"]]
    )
    for key, cfg in ONTOLOGY_CONFIG.items()
}

_ALL_ONTOLOGY_LABELS: list[str] = sorted({
    label for labels in _ONTOLOGY_LABELS.values() for label in labels
})
_ONTOLOGY_LABEL_GUARD: str = " OR ".join(f"t:{L}" for L in _ALL_ONTOLOGY_LABELS)


def build_genes_by_ontology_validate(
    *,
    term_ids: list[str],
    ontology: str,
    level: int | None,
) -> tuple[str, dict]:
    """Classify input term_ids into ok / not_found / wrong_ontology / wrong_level.

    RETURN keys per row: tid, status, matched_label.
    status ∈ {'ok','not_found','wrong_ontology','wrong_level'}.
    matched_label is the expected-label the term carries when the term exists
    and belongs to the requested ontology (status='ok' or 'wrong_level').
    NULL when status='not_found' or 'wrong_ontology'.
    """
    if ontology not in _ONTOLOGY_LABELS:
        raise ValueError(
            f"Invalid ontology '{ontology}'. "
            f"Valid: {sorted(_ONTOLOGY_LABELS)}"
        )
    expected_labels = _ONTOLOGY_LABELS[ontology]
    cypher = (
        "UNWIND $term_ids AS tid\n"
        "OPTIONAL MATCH (t {id: tid})\n"
        f"  WHERE {_ONTOLOGY_LABEL_GUARD}\n"
        "WITH tid, head(collect(t)) AS t\n"
        "RETURN tid,\n"
        "  CASE\n"
        "    WHEN t IS NULL THEN 'not_found'\n"
        "    WHEN NOT ANY(L IN $expected_labels WHERE L IN labels(t)) "
        "THEN 'wrong_ontology'\n"
        "    WHEN $level IS NOT NULL AND t.level <> $level "
        "THEN 'wrong_level'\n"
        "    ELSE 'ok'\n"
        "  END AS status,\n"
        "  CASE WHEN t IS NOT NULL "
        "THEN [L IN labels(t) WHERE L IN $expected_labels][0] "
        "ELSE NULL END AS matched_label"
    )
    return cypher, {
        "term_ids": term_ids,
        "expected_labels": expected_labels,
        "level": level,
    }


def _genes_by_ontology_match_stage(
    *,
    ontology: str,
    level: int | None,
    term_ids: list[str] | None,
    organism: str,
    tree: str | None = None,
    informative_only: bool = False,
    sources: list[str] | None = None,
    evidence: list[str] | None = None,
    max_tier: int | None = None,
    min_evidence_score: float | None = None,
    call_class: list[str] | None = None,
    interpro_type: str | None = None,
) -> tuple[str, dict]:
    """Shared MATCH + size-filter-WITH for detail/per_term/per_gene builders.

    Returns the Cypher fragment through `WITH t, collect(DISTINCT g) AS term_genes`
    with the $min_gene_set_size / $max_gene_set_size filter applied,
    plus the common params dict (org, term_ids/level as applicable).

    When `informative_only=True`, an extra term-level filter
    `AND coalesce(t.is_uninformative, '') <> 'true'` is applied BEFORE the
    size collapse so per-term gene counts reflect informative terms only.

    Trust filters (`sources` / `evidence` / `max_tier` / `min_evidence_score` /
    `call_class`) bind on the gene→leaf relationship `r`, BEFORE the hierarchy
    walk and BEFORE `collect(DISTINCT g)`, so per-term gene-set sizes reflect
    the filtered edges (spec §7.1). Facets (`tree`, `interpro_type`) bind on
    `t`: after the walk UP in level mode, and on the input term itself in
    term_ids mode (where the facet narrows the caller's own list rather than
    the walk). Enrichment reaches the same filters through this stage.

    Consumers are responsible for adding $min_gene_set_size / $max_gene_set_size
    into params, and for appending their own UNWIND/RETURN tail.
    """
    facet = _resolve_facet(ontology, tree=tree, interpro_type=interpro_type)
    trust_frag, trust_params = build_trust_filter_clause(
        ontology, sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
    )

    params: dict = {"org": organism}
    params.update(trust_params)

    if level is None:
        # Mode 1 — walk DOWN from each input term.
        params["term_ids"] = term_ids
        # The facet narrows the caller's own term list here: it binds on `t`
        # right after the input MATCH and before the walk down, so a mixed
        # `term_ids` batch cannot pool two InterPro strata (or two BRITE
        # trees) into one gene set (spec §7.7).
        facet_where = ""
        facet_and = ""
        if facet is not None:
            facet_prop, facet_param, facet_value = facet
            facet_where = f"WHERE t.{facet_prop} = ${facet_param}\n"
            facet_and = f" AND t.{facet_prop} = ${facet_param}"
            params[facet_param] = facet_value
        # Pfam needs special handling because input may be Pfam OR PfamClan;
        # caller-side validation (Query V) tells the apex label, but the
        # builder must work without that. Use coalesce over both label MATCHes.
        if ontology == "pfam":
            cypher_head = (
                "UNWIND $term_ids AS input_tid\n"
                "OPTIONAL MATCH (tp:Pfam {id: input_tid})\n"
                "OPTIONAL MATCH (tc:PfamClan {id: input_tid})\n"
                "WITH input_tid, coalesce(tp, tc) AS t\n"
                "OPTIONAL MATCH (t)<-[:Pfam_in_pfam_clan*0..1]-(leaf:Pfam)\n"
                "WITH t, coalesce(leaf, t) AS leaf\n"
                "MATCH (g:Gene {organism_name: $org})-[r:Gene_has_pfam]->(leaf)\n"
                "WHERE t:Pfam OR t:PfamClan"
                + facet_and
                + (f" AND {trust_frag}" if trust_frag else "")
                + "\n"
            )
        else:
            frag = _hierarchy_walk(ontology, direction="down")
            leaf = frag["leaf_label"]
            walk = frag["walk_down"]
            # Single-label: walk DOWN from root to leaf to gene.
            # Flat ontologies: no walk, leaf = t.
            trust_where = f"WHERE {trust_frag}\n" if trust_frag else ""
            if walk:
                cypher_head = (
                    "UNWIND $term_ids AS input_tid\n"
                    f"MATCH (t:{leaf} {{id: input_tid}})\n"
                    f"{facet_where}"
                    f"{walk}\n"
                    f"MATCH (g:Gene {{organism_name: $org}})"
                    f"-[r:{frag['gene_rel']}]->(leaf)\n"
                    f"{trust_where}"
                )
            else:
                # Flat: t = leaf; still the "input term's genes"
                cypher_head = (
                    "UNWIND $term_ids AS input_tid\n"
                    f"MATCH (t:{leaf} {{id: input_tid}})\n"
                    f"{facet_where}"
                    f"MATCH (g:Gene {{organism_name: $org}})"
                    f"-[r:{frag['gene_rel']}]->(t)\n"
                    f"{trust_where}"
                )
    else:
        # Mode 2/3 — walk UP, filter on level (and optionally term_ids).
        params["level"] = level
        frag = _hierarchy_walk(ontology, direction="up")
        bind = frag["bind_up"]
        walk = frag["walk_up"]
        # Pfam's walk_up already carries a `WHERE t:Pfam OR t:PfamClan` guard
        # — merge the level filter in via AND instead of opening a new WHERE.
        walk_has_where = bool(walk) and "WHERE" in walk
        level_keyword = "AND" if walk_has_where else "WHERE"
        level_clause = f"{level_keyword} t.level = $level"
        if term_ids is not None:
            level_clause += " AND t.id IN $term_ids"
            params["term_ids"] = term_ids
        if facet is not None:
            facet_prop, facet_param, facet_value = facet
            level_clause += f" AND t.{facet_prop} = ${facet_param}"
            params[facet_param] = facet_value
        if walk:
            # Trust predicate rides the gene→leaf MATCH, ahead of the walk.
            bind_block = bind + (f"\nWHERE {trust_frag}" if trust_frag else "")
            cypher_head = f"{bind_block}\n{walk}\n{level_clause}\n"
        else:
            # Flat ontology: t = leaf; no walk; one WHERE carries both the
            # trust predicate and the level filter.
            if trust_frag:
                level_clause = (
                    f"WHERE {trust_frag} AND " + level_clause[len("WHERE "):]
                )
            cypher_head = f"{bind}\n{level_clause}\n"

    # Term-level informative filter: must apply BEFORE size collapse so
    # per-term gene counts reflect informative-only terms.
    informative_filter = (
        "WITH t, g WHERE coalesce(t.is_uninformative, '') <> 'true'\n"
        if informative_only else ""
    )

    # Size filter (common to all modes). Caller must add
    # $min_gene_set_size and $max_gene_set_size to params.
    # Collect DISTINCT g (not records) so multi-edge ontologies don't
    # inflate term-size counts — r is re-bound via OPTIONAL MATCH in
    # the detail builder when needed.
    size_filter = (
        "WITH t, collect(DISTINCT g) AS term_genes\n"
        "WHERE size(term_genes) >= $min_gene_set_size\n"
        "  AND ($max_gene_set_size IS NULL OR "
        "size(term_genes) <= $max_gene_set_size)"
    )
    return f"{cypher_head}\n{informative_filter}{size_filter}", params


def build_genes_by_ontology_detail(
    *,
    ontology: str,
    organism: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
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
) -> tuple[str, dict]:
    """Build (gene × term) detail query. Dispatches on (level, term_ids).

    `organism` is required (single-organism contract).

    Mode 1: term_ids only — walk DOWN.
    Mode 2: level only — walk UP, filter on level.
    Mode 3: level + term_ids — walk UP, filter on level AND input_tids.

    Trust filters (`sources` / `evidence` / `max_tier` / `min_evidence_score` /
    `call_class`) bind on the gene→leaf relationship `r` BEFORE the walk and
    the size collapse, so per-term gene-set sizes reflect the filtered edges
    (spec §7.1). Facets (`tree`, `interpro_type`) bind on `t` after the walk.
    On a hierarchical ontology the trust columns come from the gene's best
    edge under `t` via the one-edge-per-(gene, term) rebind (spec §7.2).

    RETURN keys (compact): locus_tag, gene_name, product, gene_category,
    term_id, term_name, level, tree, tree_code, is_informative, plus the
    ontology's compact trust columns — `evidence`, and `interpro_type` /
    `call_class` where owned.
    RETURN keys (verbose): adds function_description, level_is_best_effort
    and the ontology's native detail. See
    `ontology_row_columns(ontology, verbose)` for the exact owned set; the
    api layer strips everything else.

    The remaining trust axes (`sources`, `evidence_score`, `tier`) are
    projected in BOTH modes (`force_trust_axes`) so the envelope rollups and
    the tier-null warning have rows to read; the api layer strips them back
    off compact rows.
    """
    # Validation stays in the builder (helper would also need it, but the
    # detail-builder tests expect `match="level.*term_ids"`).
    if level is None and not term_ids:
        raise ValueError(
            "At least one of `level` or `term_ids` must be provided."
        )
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError(
            "max_gene_set_size must be >= min_gene_set_size."
        )

    head, params = _genes_by_ontology_match_stage(
        ontology=ontology, level=level, term_ids=term_ids, organism=organism,
        tree=tree, informative_only=informative_only,
        sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
        interpro_type=interpro_type,
    )
    params["min_gene_set_size"] = min_gene_set_size
    params["max_gene_set_size"] = max_gene_set_size

    # Row return
    verbose_cols = (
        ",\n       g.function_description AS function_description,\n"
        "       t.level_is_best_effort IS NOT NULL AS level_is_best_effort"
        if verbose else ""
    )
    edge_prop_cols = _ontology_row_return_cypher(
        ontology, verbose, force_trust_axes=True,
    )
    return_block = (
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.gene_category AS gene_category,\n"
        "       t.id AS term_id, t.name AS term_name, t.level AS level,\n"
        "       t.tree AS tree, t.tree_code AS tree_code,\n"
        "       coalesce(t.is_uninformative, '') <> 'true' AS is_informative"
        f"{verbose_cols}{edge_prop_cols}\n"
        "ORDER BY t.id, g.locus_tag"
    )

    # Pagination
    skip_clause = ""
    limit_clause = ""
    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit

    # Re-bind `r` for the (gene, term) pair. Emitted only when the ontology
    # owns row columns in this mode — skipping it avoids multi-edge fan-out.
    #
    # Hierarchical ontologies take the one-edge-per-(gene, term) rebind
    # (spec §7.2): `t` is an ancestor reachable through several gene edges, so
    # the best one by the ontology's rank key wins and exactly one row per
    # (gene, term) survives. Flat ontologies keep the direct OPTIONAL MATCH.
    cfg = ONTOLOGY_CONFIG[ontology]
    if _uses_best_edge_rebind(ontology, verbose, force_trust_axes=True):
        rebind_trust, _ = build_trust_filter_clause(
            ontology, sources=sources, evidence=evidence, max_tier=max_tier,
            min_evidence_score=min_evidence_score, call_class=call_class,
            rel_var="r2",
        )
        edge_rebind = _best_edge_rebind_cypher(
            ontology, verbose, trust_frag=rebind_trust, force_trust_axes=True,
        )
    elif ontology_row_columns(ontology, verbose, force_trust_axes=True):
        edge_rebind = f"OPTIONAL MATCH (g)-[r:{cfg['gene_rel']}]->(t)\n"
    else:
        edge_rebind = ""

    cypher = (
        f"{head}\n"
        f"UNWIND term_genes AS g\n"
        f"{edge_rebind}"
        f"{return_block}{skip_clause}{limit_clause}"
    )
    return cypher, params




# --- ontology_term_details (spec §7.5, design §6) -----------------------------

LINK_KINDS: tuple[str, ...] = ("composition", "membership", "router")

# Every (rel, target_ontology, link_kind) bridge the registry declares, in
# config order. `ontology_term_details` derives `link_kind` / `target_ontology`
# per row from `rel` through this table.
BRIDGES_OUT: list[tuple[str, str, str, str]] = [
    (rel, key, target, kind)
    for key, cfg in ONTOLOGY_CONFIG.items()
    for (rel, target, kind) in (cfg.get("bridges_out") or [])
]

_ALL_HIERARCHY_RELS: list[str] = sorted({
    rel for cfg in ONTOLOGY_CONFIG.values() for rel in cfg["hierarchy_rels"]
})
_ALL_GENE_RELS: list[str] = sorted({
    cfg["gene_rel"] for cfg in ONTOLOGY_CONFIG.values()
})
# Membership edges a term reaches genes through indirectly (BRITE → KEGG
# term → gene). Joined into the subtree walk so a bridged ontology's
# per-organism gene count is not 0 by construction.
_ALL_BRIDGE_WALK_RELS: list[str] = sorted({
    cfg["bridge"]["edge"] for cfg in ONTOLOGY_CONFIG.values() if cfg.get("bridge")
})

# Columns every term-details row already projects from `t`; a
# `term_details_compact` prop with one of these names is not re-projected.
_TERM_DETAILS_STANDARD_COLUMNS: frozenset[str] = frozenset({
    "id", "name", "description", "level", "level_kind", "gene_count",
    "organism_count", "direct_gene_count",
})


def _term_details_compact_props() -> list[str]:
    """Union of the registry `term_details_compact` props, config order."""
    props: list[str] = []
    for cfg in ONTOLOGY_CONFIG.values():
        for prop in cfg.get("term_details_compact") or []:
            if prop not in props and prop not in _TERM_DETAILS_STANDARD_COLUMNS:
                props.append(prop)
    return props


def build_ontology_term_details(
    *,
    term_ids: list[str],
    link_kinds: list[str] | None = None,
    verbose: bool = False,
    organism: str | None = None,
) -> tuple[str, dict]:
    """Build the batch term-details query (spec §7.5).

    One `UNWIND $term_ids` over a cross-ontology batch; the lookup is an
    OPTIONAL MATCH guarded by an OR over every registry label (17 `label`s +
    `PfamClan`) so an unknown id survives as `not_found = true`. Rows come
    back in input order.

    Hierarchy: parents = `(t)-[:<is-a union>]->(p)`, children =
    `(t)<-[:<is-a union>]-(c)` over the union of ALL `hierarchy_rels`;
    children are capped at 50 (`children_total` carries the full count).
    Bridges: `(t)-[b:<bridges_out union>]->(tgt)` generated from the registry
    `bridges_out` triples; `link_kinds` narrows the union IN CYPHER (a
    de-selected rel type is absent from the query text). Every collect is
    null-safe (`CASE WHEN x IS NULL THEN null ... WHERE x IS NOT NULL`).

    Term-side props: the flat `t.<prop> AS <prop>` union of every
    `term_details_compact` entry — a prop the node lacks comes back null and
    the api layer strips it (docs://guide/conventions). `labels(t)` is
    projected so the api derives `ontology` from the registry (`PfamClan` →
    `pfam`), and `links_out[].rel` so it derives `link_kind` /
    `target_ontology` via `BRIDGES_OUT`.

    `router_ambiguous` is NOT projected — the api layer derives it per
    router link from the row's router out-degree and `interpro_type`.

    `organism` scopes the gene walk to `$organism` and adds
    `organism_gene_count`. Verbose adds `t{.*} AS properties` and
    `genes_by_organism` ([{organism, gene_count}], gene_count DESC) via
    `(t)<-[:<is-a union>*0..]-(d)<-[:<gene_rel union>]-(g:Gene)`.

    RETURN keys: term_id, not_found, labels, name, description, level,
    level_kind, is_informative, gene_count, organism_count,
    direct_gene_count, <term_details_compact union>, parents,
    children_total, children, links_total, links_out;
    + organism_gene_count (organism); + properties, genes_by_organism
    (verbose).
    """
    if not term_ids:
        raise ValueError("term_ids must be a non-empty list.")
    if link_kinds is not None:
        unknown = sorted(set(link_kinds) - set(LINK_KINDS))
        if unknown:
            raise ValueError(
                f"Unknown link_kind value(s) {unknown}. "
                f"Valid link_kinds: {list(LINK_KINDS)}."
            )
    selected_kinds = set(link_kinds) if link_kinds is not None else set(LINK_KINDS)
    bridges = [b for b in BRIDGES_OUT if b[3] in selected_kinds]
    bridge_rels = "|".join(rel for rel, _o, _t, _k in bridges)

    params: dict = {"term_ids": list(term_ids)}
    label_guard = _ONTOLOGY_LABEL_GUARD
    hier_union = "|".join(_ALL_HIERARCHY_RELS)

    # --- bridges (union generated from config; empty when link_kinds
    # de-selects every kind that exists) ---
    if bridges:
        bridge_block = (
            f"OPTIONAL MATCH (t)-[b:{bridge_rels}]->(tgt)\n"
            "WITH tid, t, parents, children_total, children, b, tgt\n"
            "ORDER BY tgt.id\n"
            "WITH tid, t, parents, children_total, children,\n"
            "     count(b) AS links_total,\n"
            "     [x IN collect(CASE WHEN b IS NULL THEN null ELSE {\n"
            "         rel: type(b), target_id: tgt.id, target_name: tgt.name,\n"
            "         target_labels: labels(tgt), props: properties(b)}\n"
            "     END) WHERE x IS NOT NULL] AS links_out\n"
        )
    else:
        bridge_block = (
            "WITH tid, t, parents, children_total, children,\n"
            "     0 AS links_total, [] AS links_out\n"
        )

    # --- gene walk: organism scope and/or verbose genes_by_organism ---
    gene_block = ""
    gene_cols = ""
    if organism is not None or verbose:
        walk_union = "|".join(_ALL_HIERARCHY_RELS + _ALL_BRIDGE_WALK_RELS)
        gene_union = "|".join(_ALL_GENE_RELS)
        if organism is not None:
            params["organism"] = organism
            gene_node = "(g:Gene {organism_name: $organism})"
        else:
            gene_node = "(g:Gene)"
        gene_block = (
            f"OPTIONAL MATCH (t)<-[:{walk_union}*0..]-(d)"
            f"<-[:{gene_union}]-{gene_node}\n"
            "WITH tid, t, parents, children_total, children, links_total, links_out,\n"
            "     g.organism_name AS organism_name, count(DISTINCT g) AS n_genes\n"
            "ORDER BY n_genes DESC, organism_name\n"
            "WITH tid, t, parents, children_total, children, links_total, links_out,\n"
            "     [x IN collect(CASE WHEN organism_name IS NULL THEN null\n"
            "         ELSE {organism: organism_name, gene_count: n_genes} END)\n"
            "      WHERE x IS NOT NULL] AS genes_by_organism\n"
        )
        if organism is not None:
            gene_cols += (
                ",\n       reduce(acc = 0, x IN genes_by_organism | acc + x.gene_count)"
                " AS organism_gene_count"
            )
        if verbose:
            gene_cols += ",\n       genes_by_organism"

    compact_cols = "".join(
        f",\n       t.{prop} AS {prop}" for prop in _term_details_compact_props()
    )
    verbose_cols = ",\n       t{.*} AS properties" if verbose else ""

    cypher = (
        "UNWIND $term_ids AS tid\n"
        f"OPTIONAL MATCH (t {{id: tid}}) WHERE {label_guard}\n"
        "WITH tid, t\n"
        f"OPTIONAL MATCH (t)-[:{hier_union}]->(p)\n"
        "WITH tid, t, p ORDER BY p.id\n"
        "WITH tid, t,\n"
        "     [x IN collect(DISTINCT CASE WHEN p IS NULL THEN null\n"
        "         ELSE {id: p.id, name: p.name, level: p.level} END)\n"
        "      WHERE x IS NOT NULL] AS parents\n"
        f"OPTIONAL MATCH (t)<-[:{hier_union}]-(c)\n"
        "WITH tid, t, parents, c ORDER BY c.id\n"
        "WITH tid, t, parents, count(DISTINCT c) AS children_total,\n"
        "     [x IN collect(DISTINCT CASE WHEN c IS NULL THEN null\n"
        "         ELSE {id: c.id, name: c.name, level: c.level} END)\n"
        "      WHERE x IS NOT NULL][0..50] AS children\n"
        + bridge_block
        + gene_block
        + "RETURN tid AS term_id, t IS NULL AS not_found, labels(t) AS labels,\n"
        "       t.name AS name, t.description AS description,\n"
        "       t.level AS level, t.level_kind AS level_kind,\n"
        "       CASE WHEN t IS NULL THEN null\n"
        "            ELSE coalesce(t.is_uninformative, '') <> 'true' END AS is_informative,\n"
        "       t.gene_count AS gene_count, t.organism_count AS organism_count,\n"
        "       t.direct_gene_count AS direct_gene_count"
        + compact_cols
        + ",\n       parents, children_total, children, links_total, links_out"
        + gene_cols
        + verbose_cols
        + "\nORDER BY apoc.coll.indexOf($term_ids, tid)"
    )
    return cypher, params


# --- genes_by_ontology aggregate trust rollups (spec §13 i) ------------------

def build_genes_by_ontology_trust_rollups(
    *,
    ontology: str,
    organism: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    tree: str | None = None,
    informative_only: bool = False,
    sources: list[str] | None = None,
    evidence: list[str] | None = None,
    max_tier: int | None = None,
    min_evidence_score: float | None = None,
    call_class: list[str] | None = None,
    interpro_type: str | None = None,
) -> tuple[str, dict]:
    """Aggregate-only full-match trust projection for genes_by_ontology.

    Same MATCH stage, filters and one-edge-per-(gene, term) rebind as
    `build_genes_by_ontology_detail`, but the tail is a single aggregation
    over the (gene, term) edges — no per-row id / locus_tag, no pagination —
    so the envelope rollups describe the whole match without a second row
    scan (spec §13 i).

    Rollups follow the api's row-derived shapes: `by_evidence`
    [{evidence, count}], `by_tier` [{tier, count}] with a string `'null'`
    bucket for tier-less edges, `by_sources` [{source, count}] (one count per
    source membership), `by_call_class` [{call_class, count}] (MEROPS),
    `evidence_score_stats` {min, median, max, n_null}. An axis the ontology
    does not carry yields `[]` / null stats with `n_null = 0`. Rollup lists
    are sorted count DESC in Cypher (`apoc.coll.sortMulti`); `total_rows` is
    the full (gene, term) row count the per-row warnings are phrased against.

    RETURN keys: total_rows, by_evidence, by_tier, by_sources,
    by_call_class, evidence_score_stats.
    """
    if level is None and not term_ids:
        raise ValueError(
            "At least one of `level` or `term_ids` must be provided."
        )
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError(
            "max_gene_set_size must be >= min_gene_set_size."
        )

    head, params = _genes_by_ontology_match_stage(
        ontology=ontology, level=level, term_ids=term_ids, organism=organism,
        tree=tree, informative_only=informative_only,
        sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
        interpro_type=interpro_type,
    )
    params["min_gene_set_size"] = min_gene_set_size
    params["max_gene_set_size"] = max_gene_set_size

    cfg = ONTOLOGY_CONFIG[ontology]
    trust = cfg.get("trust") or {}
    compact_edge = cfg.get("compact_edge") or {}
    has_edge_cols = bool(
        ontology_row_columns(ontology, False, force_trust_axes=True)
    )

    if _uses_best_edge_rebind(ontology, False, force_trust_axes=True):
        rebind_trust, _ = build_trust_filter_clause(
            ontology, sources=sources, evidence=evidence, max_tier=max_tier,
            min_evidence_score=min_evidence_score, call_class=call_class,
            rel_var="r2",
        )
        edge_rebind = _best_edge_rebind_cypher(
            ontology, False, trust_frag=rebind_trust, force_trust_axes=True,
        )
    elif has_edge_cols:
        edge_rebind = f"OPTIONAL MATCH (g)-[r:{cfg['gene_rel']}]->(t)\n"
    else:
        edge_rebind = ""

    def _freq(values: str, key: str) -> str:
        return (
            f"[x IN apoc.coll.sortMulti(apoc.coll.frequencies({values}), "
            f"['count']) | {{{key}: x.item, count: x.count}}]"
        )

    agg_parts = ["count(*) AS total_rows"]
    ret_parts = ["total_rows"]

    if "evidence" in trust:
        prop = _safe_identifier(trust["evidence"], "trust property")
        agg_parts.append(f"collect(r.{prop}) AS evidence_values")
        ret_parts.append(_freq("evidence_values", "evidence") + " AS by_evidence")
    else:
        ret_parts.append("[] AS by_evidence")

    if "tier" in trust:
        prop = _safe_identifier(trust["tier"], "trust property")
        agg_parts.append(
            f"collect(CASE WHEN r.{prop} IS NULL THEN 'null' ELSE r.{prop} END)"
            " AS tier_values"
        )
        ret_parts.append(_freq("tier_values", "tier") + " AS by_tier")
    else:
        ret_parts.append("[] AS by_tier")

    if "sources" in trust:
        prop = _safe_identifier(trust["sources"], "trust property")
        agg_parts.append(
            f"apoc.coll.flatten(collect(coalesce(r.{prop}, []))) AS source_values"
        )
        ret_parts.append(_freq("source_values", "source") + " AS by_sources")
    else:
        ret_parts.append("[] AS by_sources")

    if "call_class" in compact_edge:
        prop = _safe_identifier(
            compact_edge["call_class"]["prop"], "compact_edge property"
        )
        agg_parts.append(f"collect(r.{prop}) AS call_class_values")
        ret_parts.append(
            _freq("call_class_values", "call_class") + " AS by_call_class"
        )
    else:
        ret_parts.append("[] AS by_call_class")

    if "evidence_score" in trust:
        prop = _safe_identifier(trust["evidence_score"], "trust property")
        agg_parts.extend([
            f"min(r.{prop}) AS score_min",
            f"percentileCont(r.{prop}, 0.5) AS score_median",
            f"max(r.{prop}) AS score_max",
            f"sum(CASE WHEN r.{prop} IS NULL THEN 1 ELSE 0 END) AS score_n_null",
        ])
        ret_parts.append(
            "{min: score_min, median: score_median, max: score_max,"
            " n_null: score_n_null} AS evidence_score_stats"
        )
    else:
        ret_parts.append(
            "{min: null, median: null, max: null, n_null: 0}"
            " AS evidence_score_stats"
        )

    cypher = (
        f"{head}\n"
        "UNWIND term_genes AS g\n"
        f"{edge_rebind}"
        "WITH " + ",\n     ".join(agg_parts) + "\n"
        "RETURN " + ",\n       ".join(ret_parts)
    )
    return cypher, params


def build_genes_by_ontology_per_term(
    *,
    ontology: str,
    organism: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    tree: str | None = None,
    informative_only: bool = False,
    sources: list[str] | None = None,
    evidence: list[str] | None = None,
    max_tier: int | None = None,
    min_evidence_score: float | None = None,
    call_class: list[str] | None = None,
    interpro_type: str | None = None,
) -> tuple[str, dict]:
    """Per-term aggregate. One row per surviving term.

    `organism` is required (single-organism contract). Feeds summary fields
    such as `top_terms`, `by_level.n_terms`, `by_level.row_count`,
    `n_best_effort_terms`, and `filtered_out` detection.

    Mode 1: term_ids only — walk DOWN.
    Mode 2: level only — walk UP, filter on level.
    Mode 3: level + term_ids — walk UP, filter on level AND input_tids.

    Trust filters and facets thread through `_genes_by_ontology_match_stage`,
    so the per-term sizes here match the detail rows for the same filters.

    RETURN keys: term_id, term_name, level, tree, tree_code, best_effort,
    n_genes, cat_freqs, is_informative.
    """
    head, params = _genes_by_ontology_match_stage(
        ontology=ontology, level=level, term_ids=term_ids, organism=organism,
        tree=tree, informative_only=informative_only,
        sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
        interpro_type=interpro_type,
    )
    params["min_gene_set_size"] = min_gene_set_size
    params["max_gene_set_size"] = max_gene_set_size

    tail = (
        "UNWIND term_genes AS g\n"
        "WITH t, collect({lt: g.locus_tag, "
        "cat: coalesce(g.gene_category, 'Unknown')}) AS gene_rows\n"
        "RETURN t.id AS term_id, t.name AS term_name, t.level AS level,\n"
        "       t.tree AS tree, t.tree_code AS tree_code,\n"
        "       t.level_is_best_effort IS NOT NULL AS best_effort,\n"
        "       size(gene_rows) AS n_genes,\n"
        "       apoc.coll.frequencies("
        "[r IN gene_rows | r.cat]) AS cat_freqs,\n"
        "       coalesce(t.is_uninformative, '') <> 'true' AS is_informative\n"
        "ORDER BY t.id"
    )
    return f"{head}\n{tail}", params


def build_genes_by_ontology_per_gene(
    *,
    ontology: str,
    organism: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    tree: str | None = None,
    informative_only: bool = False,
    sources: list[str] | None = None,
    evidence: list[str] | None = None,
    max_tier: int | None = None,
    min_evidence_score: float | None = None,
    call_class: list[str] | None = None,
    interpro_type: str | None = None,
) -> tuple[str, dict]:
    """Per-gene aggregate. One row per surviving gene.

    RETURN keys: locus_tag, gene_category, n_terms, levels_hit.
    `levels_hit` is the distinct set of term levels each gene was reached
    via — used by L2 to compute by_level.n_genes via set-union.

    Per-gene rows do not carry per-term flags; `informative_only` threads
    through the helper so only informative terms count toward each gene's
    aggregate, but `is_informative` is NOT a row column here. Trust filters
    and facets thread through the same helper — a gene only counts through
    edges that survive them.
    """
    head, params = _genes_by_ontology_match_stage(
        ontology=ontology, level=level, term_ids=term_ids, organism=organism,
        tree=tree, informative_only=informative_only,
        sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
        interpro_type=interpro_type,
    )
    params["min_gene_set_size"] = min_gene_set_size
    params["max_gene_set_size"] = max_gene_set_size
    tail = (
        "UNWIND term_genes AS g\n"
        "WITH g, collect(DISTINCT t.id) AS gene_terms, "
        "collect(DISTINCT t.level) AS gene_levels\n"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       coalesce(g.gene_category, 'Unknown') AS gene_category,\n"
        "       size(gene_terms) AS n_terms,\n"
        "       gene_levels AS levels_hit\n"
        "ORDER BY g.locus_tag"
    )
    return f"{head}\n{tail}", params


def _gene_ontology_terms_leaf_filter(
    cfg: dict, *, include_superseded: bool = False,
) -> str:
    """Return a WHERE clause pinning leaf mode to most-specific rows, or "".

    Two predicates, both spec §7.3:

    1. The *transitive* leaf filter — `NOT EXISTS { (g)-[:gene_rel]->(child)
       -[:is_a*1..]->(t) }`. `*1..` (was a single hop) so an annotation two or
       more levels below `t` also supersedes it. Meaningful only when genes can
       be annotated to both a child and its ancestor within the same label, so
       skipped for flat ontologies (cog_category, ncbifam, psortb),
       cross-label hierarchies (pfam: Pfam→PfamClan) and bridges (brite).

    2. `leaf_attachment` — TCDB stamps the deepest surviving attachment on the
       edge itself (`attachment_depth='most_specific'`), which selects exactly
       the same rows as (1) and is cheaper (spec §7.3: verified identical on
       MED4, 670 → 597 either way).

    Because the two are equivalent, `include_superseded=True` must drop BOTH on
    an ontology that declares `leaf_attachment` — dropping only the
    `attachment_depth` predicate would leave the flag a no-op. The superseded
    rows then come back labelled by the `attachment_depth` verbose column.

    For KEGG, gene→KeggTerm edges only terminate at ko leaves (enforced by
    graph structure), so the NOT EXISTS clause is a no-op but still emitted
    — the query optimizer handles it cheaply.
    """
    parts: list[str] = []

    attachment = cfg.get("leaf_attachment")
    superseded_opt_out = bool(attachment) and include_superseded

    hierarchy_rels = cfg["hierarchy_rels"]
    if (
        hierarchy_rels
        and not cfg.get("parent_label")
        and not cfg.get("bridge")
        and not superseded_opt_out
    ):
        gene_rel = cfg["gene_rel"]
        label = cfg["label"]
        hierarchy = "|".join(hierarchy_rels)
        parts.append(
            "NOT EXISTS {\n"
            f"  MATCH (g)-[:{gene_rel}]->(child:{label})\n"
            f"        -[:{hierarchy}*1..]->(t)\n"
            "}"
        )

    if attachment and not include_superseded:
        parts.append(f"r.{attachment['prop']} = '{attachment['value']}'")

    if not parts:
        return ""
    return "WHERE " + "\n  AND ".join(parts) + "\n"


def build_gene_ontology_terms_summary(
    *,
    locus_tags: list[str],
    ontology: str,
    organism_name: str,
    mode: str = "leaf",
    level: int | None = None,
    tree: str | None = None,
    informative_only: bool = False,
    sources: list[str] | None = None,
    evidence: list[str] | None = None,
    max_tier: int | None = None,
    min_evidence_score: float | None = None,
    call_class: list[str] | None = None,
    interpro_type: str | None = None,
    include_superseded: bool = False,
) -> tuple[str, dict]:
    """Build summary for gene_ontology_terms for ONE ontology.

    Called once per ontology by api/ layer (which merges results
    and adds not_found, no_terms, totals).

    Trust filters bind on the gene→leaf relationship `r` before the hierarchy
    walk, so the summary counts and the detail rows describe the same filtered
    edge set (spec §7.1). Leaf mode honours the most-specific-attachment
    predicate unless `include_superseded` (spec §7.3).

    RETURN keys: gene_count, term_count, by_term, gene_term_counts.
    gene_term_counts is [{locus_tag, term_count}] — has per-gene identity
    so api/ can merge across ontologies for cross-ontology stats.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    if mode == "rollup" and level is None:
        raise ValueError("level is required when mode='rollup'")
    facet = _resolve_facet(ontology, tree=tree, interpro_type=interpro_type)
    trust_frag, trust_params = build_trust_filter_clause(
        ontology, sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
    )
    cfg = ONTOLOGY_CONFIG[ontology]
    gene_rel = cfg["gene_rel"]
    label = cfg["label"]

    params: dict = {"locus_tags": locus_tags, "org": organism_name}
    params.update(trust_params)
    trust_and = f" AND {trust_frag}" if trust_frag else ""

    bridge = cfg.get("bridge")

    if mode == "rollup":
        # --- rollup: walk leaf → ancestor at target level ---
        if bridge:
            bridge_edge = bridge["edge"]
            bridge_node = bridge["node_label"]
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(ko:{bridge_node})"
                f"-[:{bridge_edge}]->(leaf:{label})\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )
            rel_union = "|".join(cfg["hierarchy_rels"])
            walk = (
                f"MATCH (leaf)-[:{rel_union}*0..]->(t:{label})\n"
                "WHERE t.level = $level\n"
            )
        elif not cfg["hierarchy_rels"]:
            # flat: leaf = term, walk is identity
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(t:{label})\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )
            walk = "WITH g, t\nWHERE t.level = $level\n"
        elif ontology == "pfam":
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(leaf:Pfam)\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )
            walk = (
                "MATCH (leaf)-[:Pfam_in_pfam_clan*0..1]->(t)\n"
                "WHERE (t:Pfam OR t:PfamClan) AND t.level = $level\n"
            )
        else:
            rel_union = "|".join(cfg["hierarchy_rels"])
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(leaf:{label})\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )
            walk = (
                f"MATCH (leaf)-[:{rel_union}*0..]->(t:{label})\n"
                "WHERE t.level = $level\n"
            )
        params["level"] = level
        facet_filter = ""
        if facet is not None:
            facet_prop, facet_param, facet_value = facet
            facet_filter = f"AND t.{facet_prop} = ${facet_param}\n"
            params[facet_param] = facet_value
        informative_filter = (
            "AND coalesce(t.is_uninformative, '') <> 'true'\n"
            if informative_only else ""
        )
        cypher = (
            f"{bind}"
            f"{walk}"
            f"{facet_filter}"
            f"{informative_filter}"
            "WITH g.locus_tag AS lt, collect(DISTINCT {id: t.id, name: t.name, level: t.level, tree: t.tree, tree_code: t.tree_code}) AS terms\n"
            "WITH collect({lt: lt, cnt: size(terms), terms: terms}) AS genes\n"
            "WITH genes,\n"
            "     apoc.coll.flatten([g IN genes | g.terms]) AS all_terms,\n"
            "     [g IN genes | {locus_tag: g.lt, term_count: g.cnt}] AS gene_term_counts\n"
            "UNWIND all_terms AS t\n"
            "WITH genes, gene_term_counts, t.id AS tid, t.name AS tname, t.level AS tlevel, t.tree AS ttree, t.tree_code AS ttree_code, count(*) AS cnt\n"
            "WITH genes, gene_term_counts,\n"
            "     collect({term_id: tid, term_name: tname, level: tlevel, tree: ttree, tree_code: ttree_code, count: cnt}) AS by_term\n"
            "RETURN size(genes) AS gene_count,\n"
            "       size(apoc.coll.flatten([g IN genes | g.terms])) AS term_count,\n"
            "       by_term,\n"
            "       gene_term_counts"
        )
    else:
        # --- leaf mode ---
        leaf_filter = _gene_ontology_terms_leaf_filter(
            cfg, include_superseded=include_superseded,
        )

        if bridge:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(:{bridge['node_label']})"
                f"-[:{bridge['edge']}]->(t:{label})\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )
        else:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})-[r:{gene_rel}]->(t:{label})\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )

        # Convert leaf_filter "WHERE NOT EXISTS ..." to "AND NOT EXISTS ..."
        if leaf_filter:
            leaf_filter = "AND " + leaf_filter.replace("WHERE ", "", 1)

        level_filter = ""
        if level is not None:
            level_filter = "AND t.level = $level\n"
            params["level"] = level
        facet_filter = ""
        if facet is not None:
            facet_prop, facet_param, facet_value = facet
            facet_filter = f"AND t.{facet_prop} = ${facet_param}\n"
            params[facet_param] = facet_value
        informative_filter = (
            "AND coalesce(t.is_uninformative, '') <> 'true'\n"
            if informative_only else ""
        )

        cypher = (
            f"{match_line}"
            f"{leaf_filter}"
            f"{level_filter}"
            f"{facet_filter}"
            f"{informative_filter}"
            "WITH g.locus_tag AS lt, collect({id: t.id, name: t.name, level: t.level, tree: t.tree, tree_code: t.tree_code}) AS terms\n"
            "WITH collect({lt: lt, cnt: size(terms), terms: terms}) AS genes\n"
            "WITH genes,\n"
            "     apoc.coll.flatten([g IN genes | g.terms]) AS all_terms,\n"
            "     [g IN genes | {locus_tag: g.lt, term_count: g.cnt}] AS gene_term_counts\n"
            "UNWIND all_terms AS t\n"
            "WITH genes, gene_term_counts, t.id AS tid, t.name AS tname, t.level AS tlevel, t.tree AS ttree, t.tree_code AS ttree_code, count(*) AS cnt\n"
            "WITH genes, gene_term_counts,\n"
            "     collect({term_id: tid, term_name: tname, level: tlevel, tree: ttree, tree_code: ttree_code, count: cnt}) AS by_term\n"
            "RETURN size(genes) AS gene_count,\n"
            "       size(apoc.coll.flatten([g IN genes | g.terms])) AS term_count,\n"
            "       by_term,\n"
            "       gene_term_counts"
        )
    return cypher, params


def build_gene_ontology_terms(
    *,
    locus_tags: list[str],
    ontology: str,
    organism_name: str,
    mode: str = "leaf",
    level: int | None = None,
    tree: str | None = None,
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
) -> tuple[str, dict]:
    """Build detail Cypher for gene_ontology_terms for ONE ontology.

    Trust filters (`sources` / `evidence` / `max_tier` / `min_evidence_score` /
    `call_class`) bind on the gene→leaf relationship `r`; facets (`tree`,
    `interpro_type`) bind on `t`. In rollup mode a hierarchical ontology takes
    the one-edge-per-(gene, term) rebind (spec §7.2) so the trust columns come
    from the gene's best edge under `t` and no (gene, term) pair repeats. Leaf
    mode pins rows to the most specific attachment unless `include_superseded`
    (spec §7.3) — the superseded rows then carry `attachment_depth` in verbose.

    RETURN keys (compact): locus_tag, term_id, term_name, level, tree,
    tree_code, is_informative, plus the ontology's compact trust columns —
    `evidence`, and `interpro_type` / `call_class` where owned.
    RETURN keys (verbose): adds organism_name and the ontology's native
    detail. See `ontology_row_columns(ontology, verbose)` for the exact
    owned set. The remaining trust axes (`sources`, `evidence_score`,
    `tier`) are projected in BOTH modes (`force_trust_axes`) so the
    envelope rollups and the tier-null warning have rows to read; the api
    layer strips them back off compact rows.

    Called by api/ — which adds ontology_type column, strips the columns this
    ontology does not own, and merges across ontologies when ontology=None.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    if mode == "rollup" and level is None:
        raise ValueError("level is required when mode='rollup'")
    facet = _resolve_facet(ontology, tree=tree, interpro_type=interpro_type)
    trust_frag, trust_params = build_trust_filter_clause(
        ontology, sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
    )
    cfg = ONTOLOGY_CONFIG[ontology]
    gene_rel = cfg["gene_rel"]
    label = cfg["label"]

    params: dict = {"locus_tags": locus_tags, "org": organism_name}
    params.update(trust_params)
    trust_and = f" AND {trust_frag}" if trust_frag else ""

    verbose_cols = (
        ",\n       g.organism_name AS organism_name"
        if verbose else ""
    )
    edge_prop_cols = _ontology_row_return_cypher(
        ontology, verbose, force_trust_axes=True,
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    bridge = cfg.get("bridge")

    if mode == "rollup":
        # --- rollup: walk leaf → ancestor at target level ---
        params["level"] = level
        if bridge:
            bridge_edge = bridge["edge"]
            bridge_node = bridge["node_label"]
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(ko:{bridge_node})"
                f"-[:{bridge_edge}]->(leaf:{label})\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )
            rel_union = "|".join(cfg["hierarchy_rels"])
            walk = (
                f"MATCH (leaf)-[:{rel_union}*0..]->(t:{label})\n"
                "WHERE t.level = $level\n"
            )
        elif not cfg["hierarchy_rels"]:
            # flat: leaf = term
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(t:{label})\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )
            walk = "WITH g, t, r\nWHERE t.level = $level\n"
        elif ontology == "pfam":
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(leaf:Pfam)\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )
            walk = (
                "MATCH (leaf)-[:Pfam_in_pfam_clan*0..1]->(t)\n"
                "WHERE (t:Pfam OR t:PfamClan) AND t.level = $level\n"
            )
        else:
            rel_union = "|".join(cfg["hierarchy_rels"])
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(leaf:{label})\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )
            walk = (
                f"MATCH (leaf)-[:{rel_union}*0..]->(t:{label})\n"
                "WHERE t.level = $level\n"
            )
        facet_filter = ""
        if facet is not None:
            facet_prop, facet_param, facet_value = facet
            facet_filter = f"AND t.{facet_prop} = ${facet_param}\n"
            params[facet_param] = facet_value
        informative_filter = (
            "AND coalesce(t.is_uninformative, '') <> 'true'\n"
            if informative_only else ""
        )
        # One edge per (gene, term): on a hierarchical rollup `t` is an
        # ancestor several gene edges can reach, so keep the best one
        # (spec section 7.2) instead of emitting one row per edge.
        if _uses_best_edge_rebind(ontology, verbose, force_trust_axes=True):
            rebind_trust, _ = build_trust_filter_clause(
                ontology, sources=sources, evidence=evidence,
                max_tier=max_tier, min_evidence_score=min_evidence_score,
                call_class=call_class, rel_var="r2",
            )
            rebind = _best_edge_rebind_cypher(
                ontology, verbose, trust_frag=rebind_trust,
                force_trust_axes=True,
            )
            row_head = "RETURN g.locus_tag AS locus_tag, t.id AS term_id,\n"
        else:
            rebind = ""
            row_head = (
                "RETURN DISTINCT g.locus_tag AS locus_tag, t.id AS term_id,\n"
            )
        cypher = (
            f"{bind}"
            f"{walk}"
            f"{facet_filter}"
            f"{informative_filter}"
            f"{rebind}"
            f"{row_head}"
            f"       t.name AS term_name, t.level AS level, t.tree AS tree, t.tree_code AS tree_code,\n"
            f"       coalesce(t.is_uninformative, '') <> 'true' AS is_informative{verbose_cols}{edge_prop_cols}\n"
            f"ORDER BY g.locus_tag, t.id{skip_clause}{limit_clause}"
        )
    else:
        # --- leaf mode ---
        leaf_filter = _gene_ontology_terms_leaf_filter(
            cfg, include_superseded=include_superseded,
        )

        if bridge:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[r:{gene_rel}]->(:{bridge['node_label']})"
                f"-[:{bridge['edge']}]->(t:{label})\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )
        else:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})-[r:{gene_rel}]->(t:{label})\n"
                f"WHERE g.locus_tag IN $locus_tags{trust_and}\n"
            )

        # Convert leaf_filter "WHERE NOT EXISTS ..." to "AND NOT EXISTS ..."
        if leaf_filter:
            leaf_filter = "AND " + leaf_filter.replace("WHERE ", "", 1)

        level_filter = ""
        if level is not None:
            level_filter = "AND t.level = $level\n"
            params["level"] = level
        facet_filter = ""
        if facet is not None:
            facet_prop, facet_param, facet_value = facet
            facet_filter = f"AND t.{facet_prop} = ${facet_param}\n"
            params[facet_param] = facet_value
        informative_filter = (
            "AND coalesce(t.is_uninformative, '') <> 'true'\n"
            if informative_only else ""
        )

        cypher = (
            f"{match_line}"
            f"{leaf_filter}"
            f"{level_filter}"
            f"{facet_filter}"
            f"{informative_filter}"
            "RETURN g.locus_tag AS locus_tag, t.id AS term_id,\n"
            f"       t.name AS term_name, t.level AS level, t.tree AS tree, t.tree_code AS tree_code,\n"
            f"       coalesce(t.is_uninformative, '') <> 'true' AS is_informative{verbose_cols}{edge_prop_cols}\n"
            f"ORDER BY g.locus_tag, t.id{skip_clause}{limit_clause}"
        )
    return cypher, params


def build_gene_existence_check(
    *, locus_tags: list[str],
) -> tuple[str, dict]:
    """Build query to check which locus_tags exist in the KG.

    RETURN keys: lt, found.
    """
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "RETURN lt, g IS NOT NULL AS found"
    )
    return cypher, {"locus_tags": locus_tags}


# ---------------------------------------------------------------------------
# gene_aa_sequence
# ---------------------------------------------------------------------------


def build_gene_aa_sequence(
    *,
    locus_tags: list[str],
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail query for gene_aa_sequence (amino-acid export).

    Only genes with a non-null `sequence` are returned. Pagination is
    pushed into Cypher (`SKIP $offset LIMIT $limit`) so sequences for
    off-page rows are never transferred.

    RETURN keys: locus_tag, organism_name, gene_name, product, protein_id,
    sequence_length, sequence.
    """
    cypher = (
        "MATCH (g:Gene)\n"
        "WHERE g.locus_tag IN $locus_tags AND g.sequence IS NOT NULL\n"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.organism_name AS organism_name,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       g.protein_id AS protein_id,\n"
        "       size(g.sequence) AS sequence_length,\n"
        "       g.sequence AS sequence\n"
        "ORDER BY g.organism_name, g.locus_tag"
    )
    params: dict = {"locus_tags": locus_tags}
    if limit is not None:
        if offset:
            cypher += "\nSKIP $offset LIMIT $limit"
            params["offset"] = offset
        else:
            cypher += "\nLIMIT $limit"
        params["limit"] = limit
    return cypher, params


def build_gene_aa_sequence_summary(
    *,
    locus_tags: list[str],
) -> tuple[str, dict]:
    """Build single-row aggregate summary for gene_aa_sequence.

    Stats are computed in Cypher (no sequences transferred). `ORDER BY`
    precedes `collect()` so `matched_tags` is deterministic for snapshots.

    RETURN keys: total_matching, matched_tags, by_organism, len_min,
    len_max, len_mean, len_pcts.
    """
    cypher = (
        "MATCH (g:Gene)\n"
        "WHERE g.locus_tag IN $locus_tags AND g.sequence IS NOT NULL\n"
        "WITH g ORDER BY g.organism_name, g.locus_tag\n"
        "WITH g.organism_name AS org, size(g.sequence) AS len, g.locus_tag AS lt\n"
        "WITH collect(lt) AS matched_tags, collect(org) AS orgs, count(*) AS total_matching,\n"
        "     min(len) AS len_min, max(len) AS len_max, avg(len) AS len_mean,\n"
        "     apoc.agg.percentiles(len, [0.25, 0.5, 0.75]) AS len_pcts\n"
        "RETURN total_matching,\n"
        "       matched_tags,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       len_min, len_max, len_mean, len_pcts"
    )
    return cypher, {"locus_tags": locus_tags}


# ---------------------------------------------------------------------------
# gene_neighbors
# ---------------------------------------------------------------------------


def build_gene_neighbors(
    *,
    locus_tags: list[str],
    window: int = 5,
    max_bp_distance: int | None = None,
) -> tuple[str, dict]:
    """Build detail (bounded-window) query for gene_neighbors.

    Two correlated `CALL {}` subqueries each fetch the closest <= `$window`
    genes on the same contig/organism (upstream by descending start,
    downstream by ascending start). `collect()` is INSIDE each subquery so a
    contig-edge anchor (no upstream/downstream) yields an empty list rather
    than being dropped (5.15 has no OPTIONAL CALL). The `max_bp_distance`
    filter is appended as a Cypher WHERE on the computed `bp_gap` only when set.

    RETURN keys: anchor_locus_tag, neighbor_locus_tag, rank_offset, bp_gap,
    strand, same_strand, product, gene_name, gene_category.
    """
    bp_where = (
        "WHERE bp_gap <= $max_bp_distance\n"
        if max_bp_distance is not None
        else ""
    )
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (a:Gene {locus_tag: lt})\n"
        "WHERE a.contig IS NOT NULL AND a.start IS NOT NULL\n"
        "CALL {\n"
        "  WITH a\n"
        "  MATCH (u:Gene)\n"
        "  WHERE u.organism_name = a.organism_name AND u.contig = a.contig"
        " AND u.start < a.start\n"
        "  WITH u ORDER BY u.start DESC LIMIT $window\n"
        "  RETURN collect(u) AS ups\n"
        "}\n"
        "CALL {\n"
        "  WITH a\n"
        "  MATCH (d:Gene)\n"
        "  WHERE d.organism_name = a.organism_name AND d.contig = a.contig"
        " AND d.start > a.start\n"
        "  WITH d ORDER BY d.start ASC LIMIT $window\n"
        "  RETURN collect(d) AS downs\n"
        "}\n"
        "WITH a, [i IN range(0, size(ups)-1)   | {nb: ups[i],   ro: -(i+1)}]\n"
        "      + [i IN range(0, size(downs)-1) | {nb: downs[i], ro:  (i+1)}] AS pairs\n"
        "UNWIND pairs AS p\n"
        "WITH a, p.nb AS nb, p.ro AS rank_offset,\n"
        "     CASE WHEN p.nb.end  < a.start THEN a.start  - p.nb.end  - 1\n"
        "          WHEN p.nb.start > a.end  THEN p.nb.start - a.end   - 1\n"
        "          ELSE 0 END AS bp_gap\n"
        f"{bp_where}"
        "RETURN a.locus_tag AS anchor_locus_tag,\n"
        "       nb.locus_tag AS neighbor_locus_tag,\n"
        "       rank_offset, bp_gap,\n"
        "       nb.strand AS strand,\n"
        "       (nb.strand = a.strand) AS same_strand,\n"
        "       nb.product AS product,\n"
        "       nb.gene_name AS gene_name,\n"
        "       nb.gene_category AS gene_category\n"
        "ORDER BY anchor_locus_tag, rank_offset"
    )
    params: dict = {"locus_tags": locus_tags, "window": window}
    if max_bp_distance is not None:
        params["max_bp_distance"] = max_bp_distance
    return cypher, params


def build_gene_neighbors_summary(
    *,
    locus_tags: list[str],
) -> tuple[str, dict]:
    """Build anchor-metadata query for gene_neighbors.

    `MATCH` (not `OPTIONAL MATCH`) → only existing anchors return rows;
    existence/`not_found` is handled by the reused `build_gene_existence_check`.
    API derives `not_matched` from `has_coords=false` rows and builds the
    `anchors` envelope blocks.

    RETURN keys: anchor_locus_tag, organism_name, contig, start, end, strand,
    product, has_coords.
    """
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (a:Gene {locus_tag: lt})\n"
        "RETURN lt AS anchor_locus_tag,\n"
        "       a.organism_name AS organism_name,\n"
        "       a.contig AS contig, a.start AS start, a.end AS end,\n"
        "       a.strand AS strand, a.product AS product,\n"
        "       (a.contig IS NOT NULL AND a.start IS NOT NULL) AS has_coords\n"
        "ORDER BY anchor_locus_tag"
    )
    return cypher, {"locus_tags": locus_tags}


# ---------------------------------------------------------------------------
# Differential expression helpers
# ---------------------------------------------------------------------------


def _differential_expression_where(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params shared by all de_by_gene builders.

    direction takes precedence over significant_only (direction implies
    significance). organism uses fuzzy word-based matching (same as
    list_experiments). growth_phases filters on the edge-level r.growth_phase
    property (case-insensitive).
    """
    conditions: list[str] = []
    params: dict = {}
    if organism:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(e.organism_name) CONTAINS word)"
        )
        params["organism"] = organism
    if locus_tags:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if experiment_ids:
        conditions.append("e.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    if direction == "up":
        conditions.append("r.expression_status = 'significant_up'")
    elif direction == "down":
        conditions.append("r.expression_status = 'significant_down'")
    elif direction == "both":
        conditions.append(
            "r.expression_status IN ['significant_up', 'significant_down']"
        )
    elif significant_only:
        conditions.append("r.expression_status <> 'not_significant'")
    if growth_phases:
        conditions.append("toLower(r.growth_phase) IN $growth_phases")
        params["growth_phases"] = [gp.lower() for gp in growth_phases]
    return conditions, params


# ---------------------------------------------------------------------------
# Organism pre-validation builders (differential expression)
# ---------------------------------------------------------------------------


def build_resolve_organism_for_organism(
    *, organism: str,
) -> tuple[str, dict]:
    """Resolve distinct organism_name values for a fuzzy organism name.

    RETURN keys: organisms (list[str]).
    Matches against ``OrganismTaxon`` (the canonical organism registry, whose
    ``preferred_name`` equals ``Gene.organism_name``) using the same word-based
    CONTAINS matching as list_experiments. Resolving an organism is a genomic-
    identity question, so it gates on the presence of GENES
    (``gene_count > 0``), never on expression EXPERIMENTS — genome-only and
    metabolomics-only strains have genes but no Changes_expression_of edges and
    must still resolve, whereas gene-less higher-rank taxonomy nodes
    (genus / phage / non-target species) should not resolve (they would only
    yield empty downstream results with a confusing success).

    Each word must match ``preferred_name`` or one of the sparse
    ``name_synonyms`` (HO-002: 'Meiothermus taiwanensis' resolves the
    'Meiothermus ruber' genome strain).
    """
    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        "WHERE coalesce(o.gene_count, 0) > 0\n"
        "  AND ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(o.preferred_name) CONTAINS word"
        "    OR ANY(syn IN coalesce(o.name_synonyms, [])"
        " WHERE toLower(syn) CONTAINS word))\n"
        "RETURN collect(DISTINCT o.preferred_name) AS organisms"
    )
    return cypher, {"organism": organism}


def build_resolve_organism_for_locus_tags(
    *, locus_tags: list[str],
) -> tuple[str, dict]:
    """Resolve distinct organism_name values for a list of locus_tags.

    RETURN keys: organisms (list[str]).
    """
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})\n"
        "RETURN collect(DISTINCT g.organism_name) AS organisms"
    )
    return cypher, {"locus_tags": locus_tags}


def build_resolve_organism_for_experiments(
    *, experiment_ids: list[str],
) -> tuple[str, dict]:
    """Resolve distinct organism_name values for a list of experiment IDs.

    RETURN keys: organisms (list[str]).
    """
    cypher = (
        "UNWIND $experiment_ids AS eid\n"
        "MATCH (e:Experiment {id: eid})\n"
        "RETURN collect(DISTINCT e.organism_name) AS organisms"
    )
    return cypher, {"experiment_ids": experiment_ids}


# ---------------------------------------------------------------------------
# Differential expression summary builders
# ---------------------------------------------------------------------------


def build_differential_expression_by_gene_summary_global(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Global aggregate stats for differential_expression_by_gene.

    RETURN keys: total_matching, matching_genes, rows_by_status,
    rows_by_treatment_type, rows_by_background_factors,
    by_table_scope, rows_by_growth_phase, median_abs_log2fc, max_abs_log2fc.
    rows_by_status = apoc list [{item, count}] — api/ converts to dict.
    rows_by_treatment_type = apoc list [{item, count}] — api/ converts to dict.
    rows_by_background_factors = apoc list [{item, count}] — api/ converts to dict.
    by_table_scope = apoc list [{item, count}] — api/ converts to dict.
    rows_by_growth_phase = apoc list [{item, count}] — api/ converts to dict.
    """
    conditions, params = _differential_expression_where(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=experiment_ids, direction=direction,
        significant_only=significant_only, growth_phases=growth_phases,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
        f"{where_block}"
        "RETURN count(*) AS total_matching,\n"
        "       count(DISTINCT g.locus_tag) AS matching_genes,\n"
        "       apoc.coll.frequencies(collect(r.expression_status)) AS rows_by_status,\n"
        "       apoc.coll.frequencies(apoc.coll.flatten(collect(coalesce(e.treatment_type, [])))) AS rows_by_treatment_type,\n"
        "       apoc.coll.frequencies(apoc.coll.flatten(collect(coalesce(e.background_factors, [])))) AS rows_by_background_factors,\n"
        "       apoc.coll.frequencies(collect(e.table_scope)) AS by_table_scope,\n"
        "       apoc.coll.frequencies(collect(r.growth_phase)) AS rows_by_growth_phase,\n"
        "       percentileCont(\n"
        "           CASE WHEN r.expression_status <> 'not_significant'\n"
        "                THEN abs(r.log2_fold_change) ELSE null END, 0.5\n"
        "       ) AS median_abs_log2fc,\n"
        "       max(CASE WHEN r.expression_status <> 'not_significant'\n"
        "               THEN abs(r.log2_fold_change) END) AS max_abs_log2fc"
    )
    return cypher, params


def build_differential_expression_by_gene_summary_by_experiment(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Per-experiment breakdown with nested timepoints (single organism enforced).

    RETURN keys: organism_name, experiments.
    experiments: list of dicts, each with nested timepoints.
    rows_by_status at both experiment and timepoint level (APOC list format).
    is_time_course included per experiment so api/ can null-out timepoints.
    timepoints include growth_phase from the edge.
    """
    conditions, params = _differential_expression_where(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=experiment_ids, direction=direction,
        significant_only=significant_only, growth_phases=growth_phases,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
        f"{where_block}"
        "WITH e, r.time_point AS tp, r.time_point_order AS tpo,"
        " r.time_point_hours AS tph, r.growth_phase AS gp,\n"
        "     collect(DISTINCT g.locus_tag) AS tp_genes,\n"
        "     collect(r.expression_status) AS tp_calls\n"
        "WITH e,\n"
        "     size(apoc.coll.toSet(apoc.coll.flatten(collect(tp_genes))))"
        " AS matching_genes,\n"
        "     apoc.coll.frequencies(apoc.coll.flatten(collect(tp_calls)))"
        " AS rows_by_status,\n"
        "     collect({timepoint: tp, timepoint_hours: tph,"
        " timepoint_order: tpo, growth_phase: gp,\n"
        "              matching_genes: size(tp_genes),\n"
        "              rows_by_status: apoc.coll.frequencies(tp_calls)})"
        " AS timepoints\n"
        "WITH collect({experiment_id: e.id, experiment_name: e.name,\n"
        "              treatment_type: e.treatment_type,"
        " omics_type: e.omics_type,\n"
        "              background_factors: coalesce(e.background_factors, []),\n"
        "              coculture_partner: e.coculture_partner,\n"
        "              is_time_course: e.is_time_course,\n"
        "              table_scope: e.table_scope,\n"
        "              table_scope_detail: e.table_scope_detail,\n"
        "              matching_genes: matching_genes,\n"
        "              rows_by_status: rows_by_status,\n"
        "              timepoints: timepoints}) AS experiments,\n"
        "     e.organism_name AS organism_name\n"
        "RETURN organism_name, experiments"
    )
    return cypher, params


def build_differential_expression_by_gene_summary_diagnostics(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Top categories + batch diagnostics for differential_expression_by_gene.

    RETURN keys: top_categories, not_found, no_expression.
    not_found and no_expression are empty lists when locus_tags is None.
    Constructs different Cypher depending on whether locus_tags is provided.
    """
    if locus_tags is None:
        # Simple: no batch diagnostics needed
        conditions, params = _differential_expression_where(
            organism=organism, locus_tags=None,
            experiment_ids=experiment_ids, direction=direction,
            significant_only=significant_only, growth_phases=growth_phases,
        )
        where_block = (
            "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
        )
        # Intermediate `WITH collect(...) AS top_categories` (pure aggregation,
        # no grouping key) guarantees one row even when the MATCH is empty —
        # without it, RETURN with literal grouping keys (`[] AS not_found`)
        # collapses to zero rows when the experiment has no DE edges and
        # callers IndexError on diag_raw[0].
        cypher = (
            "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
            f"{where_block}"
            "WITH g.gene_category AS category,\n"
            "     count(DISTINCT g.locus_tag) AS total_genes,\n"
            "     count(DISTINCT CASE WHEN r.expression_status <> 'not_significant'\n"
            "                         THEN g.locus_tag END) AS significant_genes\n"
            "ORDER BY significant_genes DESC\n"
            "WITH [c IN collect({category: category, total_genes: total_genes,\n"
            "                    significant_genes: significant_genes})\n"
            "      WHERE c.category IS NOT NULL][0..5]"
            " AS top_categories\n"
            "RETURN [] AS not_found, [] AS no_expression, top_categories"
        )
        return cypher, params

    # Batch diagnostics: UNWIND locus_tags for not_found/no_expression
    # Use where_block WITHOUT locus_tags condition (already applied via UNWIND)
    conditions_no_lt, params = _differential_expression_where(
        organism=organism, locus_tags=None,
        experiment_ids=experiment_ids, direction=direction,
        significant_only=significant_only, growth_phases=growth_phases,
    )
    params["locus_tags"] = locus_tags
    where_block_no_lt = (
        "\nWHERE " + " AND ".join(conditions_no_lt)
        if conditions_no_lt else ""
    )

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g)"
        f"{where_block_no_lt}\n"
        "WITH lt, g, count(r) AS edge_count\n"
        "WITH collect(CASE WHEN g IS NULL           THEN lt END)"
        " AS not_found_raw,\n"
        "     collect(CASE WHEN g IS NOT NULL AND edge_count = 0"
        " THEN lt END) AS no_expr_raw,\n"
        "     collect(CASE WHEN g IS NOT NULL AND edge_count > 0"
        " THEN g  END) AS matched_genes\n"
        "UNWIND CASE WHEN size(matched_genes) > 0"
        " THEN matched_genes ELSE [null] END AS g\n"
        "OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g)"
        f"{where_block_no_lt}\n"
        "WITH [x IN not_found_raw WHERE x IS NOT NULL] AS not_found,\n"
        "     [x IN no_expr_raw  WHERE x IS NOT NULL] AS no_expression,\n"
        "     g.gene_category AS category,\n"
        "     count(DISTINCT g.locus_tag) AS total_genes,\n"
        "     count(DISTINCT CASE WHEN r.expression_status <> 'not_significant'\n"
        "                         THEN g.locus_tag END) AS significant_genes\n"
        "ORDER BY significant_genes DESC\n"
        "RETURN not_found, no_expression,\n"
        "       [c IN collect({category: category, total_genes: total_genes,\n"
        "                      significant_genes: significant_genes})\n"
        "        WHERE c.category IS NOT NULL][0..5]"
        " AS top_categories"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Differential expression by gene — experiment diagnostics
# ---------------------------------------------------------------------------


def build_differential_expression_by_gene_experiment_diagnostics(
    *,
    experiment_ids: list[str],
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Validate experiment IDs against KG + expression edges for DE-by-gene.

    Mirrors `_build_de_by_ortholog_experiment_diagnostics` without the
    ortholog-group join. RETURN keys: not_found_experiments,
    not_matched_experiments. `not_matched` applies the other active
    filters (organism, locus_tags, direction, significant_only,
    growth_phases) so it reflects "no DE edges satisfy the user's query
    on this experiment" rather than just "no edges at all".
    """
    # WHERE conditions WITHOUT experiment_ids filter (already via UNWIND)
    conditions_no_eid, params = _differential_expression_where(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=None, direction=direction,
        significant_only=significant_only, growth_phases=growth_phases,
    )
    params["experiment_ids"] = experiment_ids

    extra_and = (
        " AND " + " AND ".join(conditions_no_eid)
        if conditions_no_eid else ""
    )

    cypher = (
        "UNWIND $experiment_ids AS eid\n"
        "OPTIONAL MATCH (e:Experiment {id: eid})\n"
        "WITH eid, e, CASE WHEN e IS NULL THEN true ELSE false END AS missing\n"
        "OPTIONAL MATCH (e)-[r:Changes_expression_of]->(g:Gene)\n"
        f"WHERE NOT missing{extra_and}\n"
        "WITH eid, missing, count(r) AS matched_count\n"
        "WITH collect(CASE WHEN missing THEN eid END) AS nf_raw,\n"
        "     collect(CASE WHEN NOT missing AND matched_count = 0\n"
        "             THEN eid END) AS nm_raw\n"
        "RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found_experiments,\n"
        "       [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_experiments"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Differential expression detail builder
# ---------------------------------------------------------------------------


def build_differential_expression_by_gene(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for differential_expression_by_gene.

    RETURN keys (compact — 14): locus_tag, gene_name,
    experiment_id, treatment_type, timepoint, timepoint_hours, timepoint_order,
    log2fc, padj, rank, rank_up, rank_down, expression_status, growth_phase.
    RETURN keys (verbose): adds product, experiment_name, treatment,
    gene_category, omics_type, coculture_partner, table_scope,
    table_scope_detail.
    """
    conditions, params = _differential_expression_where(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=experiment_ids, direction=direction,
        significant_only=significant_only, growth_phases=growth_phases,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = (
        ",\n       g.product AS product"
        ",\n       e.name AS experiment_name"
        ",\n       e.treatment AS treatment"
        ",\n       g.gene_category AS gene_category"
        ",\n       e.omics_type AS omics_type"
        ",\n       e.coculture_partner AS coculture_partner"
        ",\n       e.table_scope AS table_scope"
        ",\n       e.table_scope_detail AS table_scope_detail"
        ",\n       coalesce(e.background_factors, []) AS background_factors"
        if verbose else ""
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       e.id AS experiment_id,\n"
        "       e.treatment_type AS treatment_type,\n"
        "       r.time_point AS timepoint,\n"
        "       r.time_point_hours AS timepoint_hours,\n"
        "       r.time_point_order AS timepoint_order,\n"
        "       r.log2_fold_change AS log2fc,\n"
        "       r.adjusted_p_value AS padj,\n"
        "       r.rank_by_effect AS rank,\n"
        "       r.rank_up AS rank_up,\n"
        "       r.rank_down AS rank_down,\n"
        "       r.expression_status AS expression_status"
        ",\n       r.growth_phase AS growth_phase"
        f"{verbose_cols}\n"
        "ORDER BY ABS(r.log2_fold_change) DESC, g.locus_tag ASC,"
        " e.id ASC, r.time_point_order ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_search_homolog_groups_summary(
    *,
    search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for search_homolog_groups.

    RETURN keys: total_entries, total_matching, score_max, score_median,
    by_source, by_level, top_cyanorak_roles, top_cog_categories.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles,
        cog_categories=cog_categories,
    )
    params["search_text"] = search_text

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "CALL db.index.fulltext.queryNodes('orthologGroupFullText', $search_text)\n"
        "YIELD node AS og, score\n"
        f"{where_block}"
        "OPTIONAL MATCH (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
        "OPTIONAL MATCH (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
        "WITH collect({src: og.source, lvl: og.taxonomic_level,\n"
        "              cr_id: cr.id, cr_name: cr.name,\n"
        "              cc_id: cc.id, cc_name: cc.name}) AS rows,\n"
        "     count(DISTINCT og) AS total_matching,\n"
        "     max(score) AS score_max,\n"
        "     percentileDisc(score, 0.5) AS score_median\n"
        "CALL { MATCH (all_og:OrthologGroup) RETURN count(all_og) AS total_entries }\n"
        "WITH *, [r IN rows | r.src] AS sources,\n"
        "        [r IN rows | r.lvl] AS levels,\n"
        "        [r IN rows WHERE r.cr_id IS NOT NULL | r.cr_id + ' | ' + r.cr_name] AS cr_items,\n"
        "        [r IN rows WHERE r.cc_id IS NOT NULL | r.cc_id + ' | ' + r.cc_name] AS cc_items\n"
        "WITH total_entries, total_matching, score_max, score_median,\n"
        "     apoc.coll.frequencies(sources) AS by_source,\n"
        "     apoc.coll.frequencies(levels) AS by_level,\n"
        "     apoc.coll.frequencies(cr_items) AS cr_freq,\n"
        "     apoc.coll.frequencies(cc_items) AS cc_freq\n"
        "RETURN total_entries, total_matching, score_max, score_median,\n"
        "       by_source, by_level,\n"
        "       apoc.coll.sortMaps(\n"
        "         [x IN cr_freq | {id: split(x.item, ' | ')[0],\n"
        "                          name: split(x.item, ' | ')[1],\n"
        "                          count: x.count}],\n"
        "         'count')[0..5] AS top_cyanorak_roles,\n"
        "       apoc.coll.sortMaps(\n"
        "         [x IN cc_freq | {id: split(x.item, ' | ')[0],\n"
        "                          name: split(x.item, ' | ')[1],\n"
        "                          count: x.count}],\n"
        "         'count')[0..5] AS top_cog_categories"
    )
    return cypher, params


def build_search_homolog_groups(
    *,
    search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for search_homolog_groups.

    RETURN keys (compact): group_id, group_name, consensus_gene_name,
    consensus_product, source, taxonomic_level, specificity_rank,
    member_count, organism_count, score.
    RETURN keys (verbose): adds description, functional_description,
    genera, has_cross_genus_members, cyanorak_roles, cog_categories.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles,
        cog_categories=cog_categories,
    )
    params["search_text"] = search_text

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    if verbose:
        cypher = (
            "CALL db.index.fulltext.queryNodes('orthologGroupFullText', $search_text)\n"
            "YIELD node AS og, score\n"
            f"{where_block}"
            "OPTIONAL MATCH (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
            "OPTIONAL MATCH (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
            "WITH og, score,\n"
            "     [x IN collect(DISTINCT {id: cr.id, name: cr.name}) WHERE x.id IS NOT NULL] AS cyanorak_roles,\n"
            "     [x IN collect(DISTINCT {id: cc.id, name: cc.name}) WHERE x.id IS NOT NULL] AS cog_categories\n"
            "RETURN og.id AS group_id, og.name AS group_name,\n"
            "       og.consensus_gene_name AS consensus_gene_name,\n"
            "       og.consensus_product AS consensus_product,\n"
            "       og.source AS source, og.taxonomic_level AS taxonomic_level,\n"
            "       og.specificity_rank AS specificity_rank,\n"
            "       og.member_count AS member_count, og.organism_count AS organism_count,\n"
            "       score,\n"
            "       og.description AS description,\n"
            "       og.functional_description AS functional_description,\n"
            "       og.genera AS genera,\n"
            "       og.has_cross_genus_members AS has_cross_genus_members,\n"
            "       cyanorak_roles, cog_categories\n"
            f"ORDER BY score DESC, og.specificity_rank, og.source, og.id{skip_clause}{limit_clause}"
        )
    else:
        cypher = (
            "CALL db.index.fulltext.queryNodes('orthologGroupFullText', $search_text)\n"
            "YIELD node AS og, score\n"
            f"{where_block}"
            "RETURN og.id AS group_id, og.name AS group_name,\n"
            "       og.consensus_gene_name AS consensus_gene_name,\n"
            "       og.consensus_product AS consensus_product,\n"
            "       og.source AS source, og.taxonomic_level AS taxonomic_level,\n"
            "       og.specificity_rank AS specificity_rank,\n"
            "       og.member_count AS member_count, og.organism_count AS organism_count,\n"
            f"       score\n"
            f"ORDER BY score DESC, og.specificity_rank, og.source, og.id{skip_clause}{limit_clause}"
        )
    return cypher, params


def build_genes_by_homolog_group_summary(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_homolog_group.

    RETURN keys: total_matching, total_genes, total_categories,
    by_organism, by_category_raw, by_group_raw,
    not_found_groups, not_matched_groups.
    """
    params: dict = {"group_ids": group_ids, "organisms": organisms}

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "OPTIONAL MATCH (og:OrthologGroup {id: gid})\n"
        "OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og)\n"
        "WHERE ($organisms IS NULL OR ANY(org_input IN $organisms\n"
        "       WHERE ALL(word IN split(toLower(org_input), ' ')\n"
        "             WHERE toLower(g.organism_name) CONTAINS word)))\n"
        "WITH gid, og, g\n"
        "WITH collect(DISTINCT CASE WHEN og IS NULL THEN gid END) AS nf_groups_raw,\n"
        "     collect(DISTINCT CASE WHEN og IS NOT NULL AND g IS NULL\n"
        "             THEN gid END) AS nm_groups_raw,\n"
        "     collect(CASE WHEN g IS NOT NULL THEN\n"
        "       {lt: g.locus_tag, org: g.organism_name,\n"
        "        cat: coalesce(g.gene_category, 'Unknown'), gid: gid} END) AS rows\n"
        "WITH [x IN nf_groups_raw WHERE x IS NOT NULL] AS not_found_groups,\n"
        "     [x IN nm_groups_raw WHERE x IS NOT NULL] AS not_matched_groups,\n"
        "     rows\n"
        "WITH not_found_groups, not_matched_groups,\n"
        "     size(rows) AS total_matching,\n"
        "     size(apoc.coll.toSet([r IN rows | r.lt])) AS total_genes,\n"
        "     size(apoc.coll.toSet([r IN rows | r.cat])) AS total_categories,\n"
        "     apoc.coll.frequencies([r IN rows | r.org]) AS by_organism,\n"
        "     apoc.coll.frequencies([r IN rows | r.cat]) AS by_category_raw,\n"
        "     apoc.coll.frequencies([r IN rows | r.gid]) AS by_group_raw\n"
        "RETURN total_matching, total_genes, total_categories,\n"
        "       not_found_groups, not_matched_groups,\n"
        "       by_organism, by_category_raw, by_group_raw"
    )
    return cypher, params


def build_genes_by_homolog_group_diagnostics(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
) -> tuple[str, dict]:
    """Validate organisms against KG + result set.

    RETURN keys: not_found_organisms, not_matched_organisms.
    Returns empty lists when organisms is None.
    """
    params: dict = {"group_ids": group_ids, "organisms": organisms}

    cypher = (
        "WITH $organisms AS org_inputs\n"
        "UNWIND CASE WHEN org_inputs IS NULL THEN [null]\n"
        "       ELSE org_inputs END AS org_input\n"
        "OPTIONAL MATCH (g_any:Gene)\n"
        "WHERE org_input IS NOT NULL\n"
        "  AND ALL(word IN split(toLower(org_input), ' ')\n"
        "          WHERE toLower(g_any.organism_name) CONTAINS word)\n"
        "WITH org_input, count(g_any) AS kg_count\n"
        "OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        "WHERE org_input IS NOT NULL AND kg_count > 0\n"
        "  AND og.id IN $group_ids\n"
        "  AND ALL(word IN split(toLower(org_input), ' ')\n"
        "          WHERE toLower(g.organism_name) CONTAINS word)\n"
        "WITH org_input, kg_count, count(g) AS matched_count\n"
        "WITH collect(CASE WHEN org_input IS NOT NULL AND kg_count = 0\n"
        "             THEN org_input END) AS nf_raw,\n"
        "     collect(CASE WHEN org_input IS NOT NULL AND kg_count > 0\n"
        "                   AND matched_count = 0 THEN org_input END) AS nm_raw\n"
        "RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found_organisms,\n"
        "       [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_organisms"
    )
    return cypher, params


def build_genes_by_homolog_group(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_homolog_group.

    RETURN keys (compact): locus_tag, gene_name, product,
    organism_name, gene_category, group_id.
    RETURN keys (verbose): adds gene_summary, function_description,
    consensus_product, source.
    """
    params: dict = {"group_ids": group_ids, "organisms": organisms}

    verbose_cols = (
        ",\n       g.gene_summary AS gene_summary"
        ",\n       g.function_description AS function_description"
        ",\n       og.consensus_product AS consensus_product"
        ",\n       og.source AS source"
        if verbose else ""
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})\n"
        "WHERE ($organisms IS NULL OR ANY(org_input IN $organisms\n"
        "       WHERE ALL(word IN split(toLower(org_input), ' ')\n"
        "             WHERE toLower(g.organism_name) CONTAINS word)))\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_name AS organism_name,\n"
        f"       g.gene_category AS gene_category, og.id AS group_id{verbose_cols}\n"
        f"ORDER BY og.id, g.organism_name, g.locus_tag{skip_clause}{limit_clause}"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Differential expression by ortholog — shared WHERE helper
# ---------------------------------------------------------------------------


def _differential_expression_by_ortholog_where(
    *,
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params shared by de_by_ortholog builders.

    organisms is a list with OR semantics (any matching organism).
    direction takes precedence over significant_only. growth_phases filters
    on the edge-level r.growth_phase property (case-insensitive).
    """
    conditions: list[str] = []
    params: dict = {}
    if organisms:
        conditions.append(
            "ANY(org_input IN $organisms"
            " WHERE ALL(word IN split(toLower(org_input), ' ')"
            " WHERE toLower(e.organism_name) CONTAINS word))"
        )
        params["organisms"] = organisms
    if experiment_ids:
        conditions.append("e.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    if direction == "up":
        conditions.append("r.expression_status = 'significant_up'")
    elif direction == "down":
        conditions.append("r.expression_status = 'significant_down'")
    elif significant_only:
        conditions.append("r.expression_status <> 'not_significant'")
    if growth_phases:
        conditions.append("toLower(r.growth_phase) IN $growth_phases")
        params["growth_phases"] = [gp.lower() for gp in growth_phases]
    return conditions, params


# ---------------------------------------------------------------------------
# Differential expression by ortholog — summary builders
# ---------------------------------------------------------------------------


def build_differential_expression_by_ortholog_group_check(
    *,
    group_ids: list[str],
) -> tuple[str, dict]:
    """Check which group_ids exist as OrthologGroup nodes.

    RETURN keys: not_found (list[str]).
    """
    cypher = (
        "UNWIND $group_ids AS gid\n"
        "OPTIONAL MATCH (og:OrthologGroup {id: gid})\n"
        "WITH collect(CASE WHEN og IS NULL THEN gid END) AS nf_raw\n"
        "RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found"
    )
    return cypher, {"group_ids": group_ids}


def build_differential_expression_by_ortholog_summary_global(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Global aggregate stats for differential_expression_by_ortholog.

    Uses MATCH (not OPTIONAL) — caller should pass only found group_ids.

    RETURN keys: total_matching, matching_genes, matching_groups,
    experiment_count, by_organism, rows_by_status, rows_by_treatment_type,
    rows_by_background_factors, by_table_scope, rows_by_growth_phase,
    sig_log2fcs, matched_group_ids.
    """
    conditions, params = _differential_expression_by_ortholog_where(
        organisms=organisms, experiment_ids=experiment_ids,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "MATCH (og:OrthologGroup {id: gid})\n"
        "MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og)\n"
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n"
        f"{where_block}"
        "WITH gid, g.locus_tag AS lt, e.organism_name AS org,\n"
        "     r.expression_status AS status, e.treatment_type AS tt,\n"
        "     e.background_factors AS bfs, e.table_scope AS ts, e.id AS eid,\n"
        "     r.log2_fold_change AS log2fc, r.growth_phase AS gp\n"
        "WITH collect({gid: gid, lt: lt, org: org,\n"
        "              status: status, tt: tt, bfs: bfs, ts: ts,\n"
        "              eid: eid, log2fc: log2fc, gp: gp}) AS rows\n"
        "RETURN size(rows) AS total_matching,\n"
        "       size(apoc.coll.toSet([r IN rows | r.lt])) AS matching_genes,\n"
        "       size(apoc.coll.toSet([r IN rows | r.gid])) AS matching_groups,\n"
        "       size(apoc.coll.toSet([r IN rows | r.eid])) AS experiment_count,\n"
        "       apoc.coll.frequencies([r IN rows | r.org]) AS by_organism,\n"
        "       apoc.coll.frequencies([r IN rows | r.status]) AS rows_by_status,\n"
        "       apoc.coll.frequencies(apoc.coll.flatten([r IN rows | coalesce(r.tt, [])])) AS rows_by_treatment_type,\n"
        "       apoc.coll.frequencies(apoc.coll.flatten([r IN rows | coalesce(r.bfs, [])])) AS rows_by_background_factors,\n"
        "       apoc.coll.frequencies([r IN rows | r.ts]) AS by_table_scope,\n"
        "       apoc.coll.frequencies([r IN rows | r.gp]) AS rows_by_growth_phase,\n"
        "       apoc.coll.toSet([r IN rows | r.gid]) AS matched_group_ids,\n"
        "       [r IN rows WHERE r.status <> 'not_significant' | abs(r.log2fc)]"
        " AS sig_log2fcs"
    )
    return cypher, params


def build_differential_expression_by_ortholog_top_groups(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Top ortholog groups by significant gene count.

    RETURN keys: top_groups (list of dicts with group_id,
    consensus_gene_name, consensus_product, significant_genes, total_genes).
    """
    conditions, params = _differential_expression_by_ortholog_where(
        organisms=organisms, experiment_ids=experiment_ids,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})\n"
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n"
        f"{where_block}"
        "WITH og,\n"
        "     count(DISTINCT g.locus_tag) AS total_genes,\n"
        "     count(DISTINCT CASE WHEN r.expression_status <> 'not_significant'\n"
        "                         THEN g.locus_tag END) AS significant_genes\n"
        "ORDER BY significant_genes DESC, og.id ASC\n"
        "LIMIT 5\n"
        "RETURN collect({\n"
        "  group_id: og.id,\n"
        "  consensus_gene_name: og.consensus_gene_name,\n"
        "  consensus_product: og.consensus_product,\n"
        "  significant_genes: significant_genes,\n"
        "  total_genes: total_genes\n"
        "}) AS top_groups"
    )
    return cypher, params


def build_differential_expression_by_ortholog_top_experiments(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Top experiments by significant gene count across ortholog groups.

    RETURN keys: top_experiments (list of dicts with experiment_id,
    treatment_type, organism_name, significant_genes).
    """
    conditions, params = _differential_expression_by_ortholog_where(
        organisms=organisms, experiment_ids=experiment_ids,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})\n"
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n"
        f"{where_block}"
        "WITH e,\n"
        "     count(DISTINCT CASE WHEN r.expression_status <> 'not_significant'\n"
        "                         THEN g.locus_tag END) AS significant_genes\n"
        "ORDER BY significant_genes DESC, e.id ASC\n"
        "LIMIT 5\n"
        "RETURN collect({\n"
        "  experiment_id: e.id,\n"
        "  treatment_type: e.treatment_type,\n"
        "  background_factors: coalesce(e.background_factors, []),\n"
        "  organism_name: e.organism_name,\n"
        "  significant_genes: significant_genes\n"
        "}) AS top_experiments"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Differential expression by ortholog — detail builder
# ---------------------------------------------------------------------------


def build_differential_expression_by_ortholog_results(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for differential_expression_by_ortholog.

    RETURN keys (compact — 14): group_id, consensus_gene_name,
    consensus_product, experiment_id, treatment_type, organism_name,
    coculture_partner, timepoint, timepoint_hours, timepoint_order,
    growth_phase, genes_with_expression, significant_up, significant_down,
    not_significant.
    RETURN keys (verbose): adds experiment_name, treatment, omics_type,
    table_scope, table_scope_detail.
    """
    conditions, params = _differential_expression_by_ortholog_where(
        organisms=organisms, experiment_ids=experiment_ids,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = (
        ",\n       e.name AS experiment_name"
        ",\n       e.treatment AS treatment"
        ",\n       e.omics_type AS omics_type"
        ",\n       e.table_scope AS table_scope"
        ",\n       e.table_scope_detail AS table_scope_detail"
        if verbose else ""
    )

    if offset:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})\n"
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n"
        f"{where_block}"
        "WITH og, e,\n"
        "     r.time_point AS tp,\n"
        "     r.time_point_hours AS tph,\n"
        "     r.time_point_order AS tpo,\n"
        "     r.growth_phase AS gp,\n"
        "     collect(DISTINCT g.locus_tag) AS genes,\n"
        "     collect(r.expression_status) AS statuses\n"
        "RETURN og.id AS group_id,\n"
        "       og.consensus_gene_name AS consensus_gene_name,\n"
        "       og.consensus_product AS consensus_product,\n"
        "       e.id AS experiment_id,\n"
        "       e.treatment_type AS treatment_type,\n"
        "       coalesce(e.background_factors, []) AS background_factors,\n"
        "       e.organism_name AS organism_name,\n"
        "       e.coculture_partner AS coculture_partner,\n"
        "       tp AS timepoint,\n"
        "       tph AS timepoint_hours,\n"
        "       tpo AS timepoint_order,\n"
        "       gp AS growth_phase,\n"
        "       size(genes) AS genes_with_expression,\n"
        "       size([s IN statuses WHERE s = 'significant_up']) AS significant_up,\n"
        "       size([s IN statuses WHERE s = 'significant_down']) AS significant_down,\n"
        "       size([s IN statuses WHERE s = 'not_significant']) AS not_significant"
        f"{verbose_cols}\n"
        "ORDER BY og.id ASC, e.id ASC, tpo ASC\n"
    )
    if offset:
        cypher += "SKIP $offset\n"
    if limit is not None:
        cypher += "LIMIT $limit"
    return cypher, params


# ---------------------------------------------------------------------------
# Differential expression by ortholog — membership counts
# ---------------------------------------------------------------------------


def build_differential_expression_by_ortholog_membership_counts(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
) -> tuple[str, dict]:
    """Gene counts per ortholog group per organism (no expression filter).

    RETURN keys: group_id, organism_name, total_genes.
    """
    params: dict = {"group_ids": group_ids, "organisms": organisms}

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})\n"
        "WHERE ($organisms IS NULL OR ANY(org_input IN $organisms\n"
        "       WHERE ALL(word IN split(toLower(org_input), ' ')\n"
        "             WHERE toLower(g.organism_name) CONTAINS word)))\n"
        "RETURN og.id AS group_id,\n"
        "       g.organism_name AS organism_name,\n"
        "       count(g) AS total_genes\n"
        "ORDER BY og.id ASC, g.organism_name ASC"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Differential expression by ortholog — diagnostics
# ---------------------------------------------------------------------------


def _build_de_by_ortholog_organism_diagnostics(
    *,
    group_ids: list[str],
    organisms: list[str],
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Validate organisms against KG + expression in ortholog groups.

    RETURN keys: not_found_organisms, not_matched_organisms.
    """
    # Build expression WHERE conditions WITHOUT organism filter
    conditions_no_org, params = _differential_expression_by_ortholog_where(
        organisms=None, experiment_ids=experiment_ids,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids
    params["organisms"] = organisms

    expression_where = (
        "\nWHERE " + " AND ".join(conditions_no_org)
        if conditions_no_org else ""
    )

    cypher = (
        "WITH $organisms AS org_inputs\n"
        "UNWIND CASE WHEN org_inputs IS NULL THEN [null]\n"
        "       ELSE org_inputs END AS org_input\n"
        "OPTIONAL MATCH (g_any:Gene)\n"
        "WHERE org_input IS NOT NULL\n"
        "  AND ALL(word IN split(toLower(org_input), ' ')\n"
        "          WHERE toLower(g_any.organism_name) CONTAINS word)\n"
        "WITH org_input, count(g_any) AS kg_count\n"
        "OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        "WHERE org_input IS NOT NULL AND kg_count > 0\n"
        "  AND og.id IN $group_ids\n"
        "  AND ALL(word IN split(toLower(org_input), ' ')\n"
        "          WHERE toLower(g.organism_name) CONTAINS word)\n"
        "OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g)"
        f"{expression_where}\n"
        "WITH org_input, kg_count, count(r) AS matched_count\n"
        "WITH collect(CASE WHEN org_input IS NOT NULL AND kg_count = 0\n"
        "             THEN org_input END) AS nf_raw,\n"
        "     collect(CASE WHEN org_input IS NOT NULL AND kg_count > 0\n"
        "                   AND matched_count = 0 THEN org_input END) AS nm_raw\n"
        "RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found_organisms,\n"
        "       [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_organisms"
    )
    return cypher, params


def _build_de_by_ortholog_experiment_diagnostics(
    *,
    group_ids: list[str],
    experiment_ids: list[str],
    organisms: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Validate experiment IDs against KG + expression in ortholog groups.

    RETURN keys: not_found_experiments, not_matched_experiments.
    """
    # Build WHERE conditions WITHOUT experiment_ids filter (already via UNWIND)
    conditions_no_eid, params = _differential_expression_by_ortholog_where(
        organisms=organisms, experiment_ids=None,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids
    params["experiment_ids"] = experiment_ids

    # Additional AND conditions for organism + expression filters
    extra_and = (
        " AND " + " AND ".join(conditions_no_eid)
        if conditions_no_eid else ""
    )

    cypher = (
        "WITH $experiment_ids AS eid_inputs\n"
        "UNWIND CASE WHEN eid_inputs IS NULL THEN [null]\n"
        "       ELSE eid_inputs END AS eid\n"
        "OPTIONAL MATCH (e:Experiment {id: eid})\n"
        "WITH eid, e, CASE WHEN e IS NULL THEN true ELSE false END AS missing\n"
        "OPTIONAL MATCH (e)-[r:Changes_expression_of]->(g:Gene)"
        "-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        "WHERE NOT missing AND og.id IN $group_ids"
        f"{extra_and}\n"
        "WITH eid, missing, count(r) AS matched_count\n"
        "WITH collect(CASE WHEN missing THEN eid END) AS nf_raw,\n"
        "     collect(CASE WHEN NOT missing AND matched_count = 0\n"
        "             THEN eid END) AS nm_raw\n"
        "RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found_experiments,\n"
        "       [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_experiments"
    )
    return cypher, params


def build_differential_expression_by_ortholog_diagnostics(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> list[tuple[str, dict]] | None:
    """Build diagnostic queries for differential_expression_by_ortholog.

    Returns None when both organisms and experiment_ids are None.
    Otherwise returns a list of (cypher, params) tuples — one per
    diagnostic sub-query that needs to run.
    """
    if organisms is None and experiment_ids is None:
        return None

    queries: list[tuple[str, dict]] = []
    if organisms is not None:
        queries.append(_build_de_by_ortholog_organism_diagnostics(
            group_ids=group_ids, organisms=organisms,
            experiment_ids=experiment_ids, direction=direction,
            significant_only=significant_only, growth_phases=growth_phases,
        ))
    if experiment_ids is not None:
        queries.append(_build_de_by_ortholog_experiment_diagnostics(
            group_ids=group_ids, experiment_ids=experiment_ids,
            organisms=organisms, direction=direction,
            significant_only=significant_only, growth_phases=growth_phases,
        ))
    return queries


# ---------------------------------------------------------------------------
# gene_response_profile helpers
# ---------------------------------------------------------------------------

def _gene_response_profile_where(
    *,
    organism_name: str | None = None,
    treatment_types: list[str] | None = None,
    background_factors: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    experiment_alias: str = "e",
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params shared by gene_response_profile builders."""
    conditions: list[str] = []
    params: dict = {}
    if organism_name:
        conditions.append(f"{experiment_alias}.organism_name = $organism_name")
        params["organism_name"] = organism_name
    if treatment_types:
        conditions.append(
            f"ANY(t IN {experiment_alias}.treatment_type"
            f" WHERE toLower(t) IN $treatment_types)"
        )
        params["treatment_types"] = [t.lower() for t in treatment_types]
    if background_factors:
        conditions.append(
            f"ANY(bf IN coalesce({experiment_alias}.background_factors, [])"
            f" WHERE toLower(bf) IN $background_factors)"
        )
        params["background_factors"] = [bf.lower() for bf in background_factors]
    if experiment_ids:
        conditions.append(f"{experiment_alias}.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    return conditions, params


def _group_key_expr(group_by: str, alias: str = "e") -> tuple[str, str]:
    """Return (unwind_clause, group_key_expr) for the group key.

    When group_by='treatment_type', returns an UNWIND clause because
    treatment_type is an array property. The UNWIND must be inserted
    after the MATCH that introduces the experiment alias.
    """
    if group_by == "treatment_type":
        return (
            f"UNWIND coalesce({alias}.treatment_type, ['unknown']) AS _tt\n",
            "_tt",
        )
    elif group_by == "experiment":
        return ("", f"{alias}.id")
    else:
        raise ValueError(
            f"group_by must be 'treatment_type' or 'experiment', got '{group_by}'"
        )


def build_gene_response_profile_envelope(
    *,
    locus_tags: list[str],
    organism_name: str,
    treatment_types: list[str] | None = None,
    background_factors: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    group_by: str = "treatment_type",
) -> tuple[str, dict]:
    """Build envelope query for gene_response_profile.

    organism_name is required (resolved by API before calling).

    RETURN keys: found_genes (list), has_expression (list), has_significant (list),
    group_totals (list of {group_key, experiments, timepoints, table_scopes}).
    """
    _, gk = _group_key_expr(group_by)
    unwind2, gk2 = _group_key_expr(group_by, alias="e2")

    conditions_e, params = _gene_response_profile_where(
        organism_name=organism_name, treatment_types=treatment_types,
        background_factors=background_factors,
        experiment_ids=experiment_ids, experiment_alias="e",
    )
    params["locus_tags"] = locus_tags
    where_e = " AND " + " AND ".join(conditions_e) if conditions_e else ""

    conditions_e2, _ = _gene_response_profile_where(
        organism_name=organism_name, treatment_types=treatment_types,
        background_factors=background_factors,
        experiment_ids=experiment_ids, experiment_alias="e2",
    )
    where_e2 = "WHERE " + " AND ".join(conditions_e2)

    cypher = (
        "MATCH (g:Gene)\n"
        "WHERE g.locus_tag IN $locus_tags\n"
        "WITH collect(g.locus_tag) AS found_genes\n"
        "\n"
        "OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g2:Gene)\n"
        f"WHERE g2.locus_tag IN found_genes{where_e}\n"
        "WITH found_genes,\n"
        "     collect(DISTINCT g2.locus_tag) AS has_expression,\n"
        "     collect(DISTINCT CASE WHEN r.expression_status IN"
        " ['significant_up', 'significant_down']"
        " THEN g2.locus_tag END) AS has_significant\n"
        "\n"
        "OPTIONAL MATCH (e2:Experiment)-[:Changes_expression_of]->(:Gene)\n"
        f"{where_e2}\n"
        f"{unwind2}"
        f"WITH found_genes, has_expression, has_significant,\n"
        f"     {gk2} AS group_key,\n"
        "     collect(DISTINCT e2) AS group_experiments\n"
        "WITH found_genes, has_expression, has_significant,\n"
        "     collect({group_key: group_key,"
        " experiments: size(group_experiments),"
        " timepoints: reduce(s = 0, exp IN group_experiments |"
        " s + COALESCE(exp.time_point_count, 1)),"
        " table_scopes: apoc.coll.toSet([exp IN group_experiments |"
        " exp.table_scope])}) AS group_totals\n"
        "RETURN found_genes,"
        " has_expression, has_significant, group_totals"
    )
    return cypher, params


def build_gene_response_profile(
    *,
    locus_tags: list[str],
    organism_name: str,
    treatment_types: list[str] | None = None,
    background_factors: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    group_by: str = "treatment_type",
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build two-pass aggregation query for gene_response_profile.

    Pass 1: compute per-gene sort keys (breadth/depth/timepoints), sort and paginate.
    Pass 2: group by experiment first (experiments_up/down), then flatten for rank/log2fc.

    RETURN keys: locus_tag, gene_name, product, gene_category, group_key,
    experiments_tested, experiments_up, experiments_down, timepoints_tested,
    timepoints_up, timepoints_down, rank_ups (list), rank_downs (list),
    log2fcs_up (list), log2fcs_down (list).
    """
    unwind, gk = _group_key_expr(group_by)

    conditions, params = _gene_response_profile_where(
        organism_name=organism_name, treatment_types=treatment_types,
        background_factors=background_factors,
        experiment_ids=experiment_ids,
    )
    params["locus_tags"] = locus_tags
    conditions.append("g.locus_tag IN $locus_tags")
    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    pass2_conditions, _ = _gene_response_profile_where(
        organism_name=organism_name, treatment_types=treatment_types,
        background_factors=background_factors,
        experiment_ids=experiment_ids,
    )
    pass2_where = (
        "WHERE " + " AND ".join(pass2_conditions) + "\n"
        if pass2_conditions else ""
    )

    pagination = ""
    if offset:
        pagination += "\nSKIP $offset"
        params["offset"] = offset
    if limit is not None:
        pagination += "\nLIMIT $limit"
        params["limit"] = limit

    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
        f"{where_block}"
        f"{unwind}"
        "WITH g,\n"
        "     count(DISTINCT CASE"
        " WHEN r.expression_status IN ['significant_up', 'significant_down']"
        f" THEN {gk} END) AS groups_responded,\n"
        "     count(DISTINCT CASE"
        " WHEN r.expression_status IN ['significant_up', 'significant_down']"
        " THEN e.id END) AS experiments_responded,\n"
        "     sum(CASE"
        " WHEN r.expression_status IN ['significant_up', 'significant_down']"
        " THEN 1 ELSE 0 END) AS timepoints_responded\n"
        "ORDER BY groups_responded DESC,"
        " experiments_responded DESC,"
        " timepoints_responded DESC,"
        " g.locus_tag ASC"
        f"{pagination}\n"
        "\n"
        "WITH g\n"
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n"
        f"{pass2_where}"
        f"{unwind}"
        f"WITH g, {gk} AS group_key, e.id AS eid,"
        " collect(r) AS exp_edges\n"
        "WITH g, group_key,\n"
        "     count(eid) AS experiments_tested,\n"
        "     count(CASE WHEN ANY(x IN exp_edges"
        " WHERE x.expression_status = 'significant_up')"
        " THEN 1 END) AS experiments_up,\n"
        "     count(CASE WHEN ANY(x IN exp_edges"
        " WHERE x.expression_status = 'significant_down')"
        " THEN 1 END) AS experiments_down,\n"
        "     reduce(acc = [], edges IN collect(exp_edges)"
        " | acc + edges) AS all_edges\n"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       g.gene_category AS gene_category,\n"
        "       group_key,\n"
        "       experiments_tested,\n"
        "       experiments_up,\n"
        "       experiments_down,\n"
        "       size(all_edges) AS timepoints_tested,\n"
        "       size([x IN all_edges"
        " WHERE x.expression_status = 'significant_up'])"
        " AS timepoints_up,\n"
        "       size([x IN all_edges"
        " WHERE x.expression_status = 'significant_down'])"
        " AS timepoints_down,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_up'"
        " | x.rank_up] AS rank_ups,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_down'"
        " | x.rank_down] AS rank_downs,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_up'"
        " | x.log2_fold_change] AS log2fcs_up,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_down'"
        " | x.log2_fold_change] AS log2fcs_down\n"
        "ORDER BY locus_tag ASC, group_key ASC"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Gene cluster builders
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# ClusteringAnalysis builders
# ---------------------------------------------------------------------------


def _clustering_analysis_where(
    *,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build ClusteringAnalysis filter conditions + params."""
    conditions: list[str] = []
    params: dict = {}
    if organism is not None:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(ca.organism_name) CONTAINS word)"
        )
        params["organism"] = organism
    if cluster_type is not None:
        conditions.append("ca.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        conditions.append(
            "ANY(tt IN ca.treatment_type WHERE tt IN $treatment_type)"
        )
        params["treatment_type"] = treatment_type
    if omics_type is not None:
        conditions.append("ca.omics_type = $omics_type")
        params["omics_type"] = omics_type
    if background_factors is not None:
        conditions.append(
            "ANY(bf IN coalesce(ca.background_factors, [])"
            " WHERE bf IN $background_factors)"
        )
        params["background_factors"] = background_factors
    if growth_phases is not None:
        conditions.append(
            "ANY(gp IN coalesce(ca.growth_phases, [])"
            " WHERE toLower(gp) IN $growth_phases)"
        )
        params["growth_phases"] = [gp.lower() for gp in growth_phases]
    return conditions, params


def build_list_clustering_analyses_summary(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    analysis_ids: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for list_clustering_analyses.

    RETURN keys: total_entries, total_matching, by_organism,
    by_cluster_type, by_treatment_type, by_background_factors,
    by_omics_type, by_growth_phase.
    When search_text: adds score_max, score_median.
    """
    conditions, params = _clustering_analysis_where(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, omics_type=omics_type,
        background_factors=background_factors, growth_phases=growth_phases,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('clusteringAnalysisFullText', $search_text)\n"
            "YIELD node AS ca, score\n"
        )
        score_cols = (
            ",\n     max(score) AS score_max"
            ",\n     percentileDisc(score, 0.5) AS score_median"
        )
        score_return = ", score_max, score_median"
    else:
        match_block = "MATCH (ca:ClusteringAnalysis)\n"
        score_cols = ""
        score_return = ""

    if publication_doi is not None:
        match_block += "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    if experiment_ids is not None:
        match_block += "MATCH (exp:Experiment)-[:ExperimentHasClusteringAnalysis]->(ca)\n"
        conditions.append("exp.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids

    if analysis_ids is not None:
        conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "WITH collect(ca.organism_name) AS organisms,\n"
        "     collect(ca.cluster_type) AS cluster_types,\n"
        "     apoc.coll.flatten(collect(coalesce(ca.treatment_type, []))) AS treatment_types,\n"
        "     apoc.coll.flatten(collect(coalesce(ca.background_factors, []))) AS background_factors_flat,\n"
        "     collect(ca.omics_type) AS omics_types,\n"
        "     apoc.coll.flatten(collect(coalesce(ca.growth_phases, []))) AS growth_phases_flat,\n"
        f"     count(ca) AS total_matching{score_cols}\n"
        "CALL { MATCH (all_ca:ClusteringAnalysis) RETURN count(all_ca) AS total_entries }\n"
        "RETURN total_entries, total_matching,\n"
        "       apoc.coll.frequencies(organisms) AS by_organism,\n"
        "       apoc.coll.frequencies(cluster_types) AS by_cluster_type,\n"
        "       apoc.coll.frequencies(treatment_types) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(background_factors_flat) AS by_background_factors,\n"
        "       apoc.coll.frequencies(omics_types) AS by_omics_type,\n"
        f"       apoc.coll.frequencies(growth_phases_flat) AS by_growth_phase{score_return}"
    )
    return cypher, params


def build_list_clustering_analyses(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    analysis_ids: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for list_clustering_analyses.

    RETURN keys (compact): analysis_id, name, organism_name, cluster_method,
    cluster_type, cluster_count, total_gene_count, treatment_type,
    background_factors, growth_phases, omics_type, experiment_ids, clusters.
    When search_text: adds score.
    RETURN keys (verbose): adds treatment, light_condition, experimental_context.
    Inline clusters (compact): cluster_id, name, member_count.
    Inline clusters (verbose): adds functional_description, expression_dynamics,
    temporal_pattern.
    """
    conditions, params = _clustering_analysis_where(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, omics_type=omics_type,
        background_factors=background_factors, growth_phases=growth_phases,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('clusteringAnalysisFullText', $search_text)\n"
            "YIELD node AS ca, score\n"
        )
        score_col = ",\n       score"
        order_prefix = "score DESC, "
    else:
        match_block = "MATCH (ca:ClusteringAnalysis)\n"
        score_col = ""
        order_prefix = ""

    if publication_doi is not None:
        match_block += "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    if experiment_ids is not None:
        match_block += "MATCH (exp:Experiment)-[:ExperimentHasClusteringAnalysis]->(ca)\n"
        conditions.append("exp.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids

    if analysis_ids is not None:
        conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       ca.treatment AS treatment"
            ",\n       ca.light_condition AS light_condition"
            ",\n       ca.experimental_context AS experimental_context"
        )

    # Inline cluster subquery — compact or verbose
    if verbose:
        cluster_collect = (
            "collect({cluster_id: gc.id, name: gc.name,"
            " member_count: gc.member_count,"
            " functional_description: gc.functional_description,"
            " expression_dynamics: gc.expression_dynamics,"
            " temporal_pattern: gc.temporal_pattern}) AS clusters"
        )
    else:
        cluster_collect = (
            "collect({cluster_id: gc.id, name: gc.name,"
            " member_count: gc.member_count}) AS clusters"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    score_with = ", score" if search_text is not None else ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        # Collect experiment IDs (OPTIONAL — edge may not exist)
        "OPTIONAL MATCH (exp_link:Experiment)-[:ExperimentHasClusteringAnalysis]->(ca)\n"
        f"WITH ca{score_with},\n"
        "     collect(DISTINCT exp_link.id) AS experiment_ids\n"
        # Collect inline clusters
        "OPTIONAL MATCH (ca)-[:ClusteringAnalysisHasGeneCluster]->(gc:GeneCluster)\n"
        f"WITH ca{score_with}, experiment_ids,\n"
        f"     {cluster_collect}\n"
        "RETURN ca.id AS analysis_id, ca.name AS name,\n"
        "       ca.organism_name AS organism_name,\n"
        "       ca.cluster_method AS cluster_method,\n"
        "       ca.cluster_type AS cluster_type,\n"
        "       ca.cluster_count AS cluster_count,\n"
        "       ca.total_gene_count AS total_gene_count,\n"
        "       ca.treatment_type AS treatment_type,\n"
        "       coalesce(ca.background_factors, []) AS background_factors,\n"
        "       coalesce(ca.growth_phases, []) AS growth_phases,\n"
        "       ca.omics_type AS omics_type,\n"
        f"       experiment_ids, clusters{score_col}{verbose_cols}\n"
        f"ORDER BY {order_prefix}ca.organism_name, ca.name{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_gene_clusters_by_gene_summary(
    *,
    locus_tags: list[str],
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    analysis_ids: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for gene_clusters_by_gene.

    Joins through ClusteringAnalysis for analysis fields and filters.

    RETURN keys: total_matching, total_clusters,
    genes_with_clusters, genes_without_clusters,
    not_found, not_matched,
    by_cluster_type, by_treatment_type, by_background_factors,
    by_analysis.
    """
    params: dict = {"locus_tags": locus_tags}

    ca_conditions: list[str] = []
    if cluster_type is not None:
        ca_conditions.append("ca.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        ca_conditions.append(
            "ANY(tt IN ca.treatment_type WHERE tt IN $treatment_type)")
        params["treatment_type"] = treatment_type
    if background_factors is not None:
        ca_conditions.append(
            "ANY(bf IN coalesce(ca.background_factors, [])"
            " WHERE bf IN $background_factors)")
        params["background_factors"] = background_factors
    if analysis_ids is not None:
        ca_conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    pub_match = ""
    if publication_doi is not None:
        pub_match = "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        ca_conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    ca_where = "WHERE " + " AND ".join(ca_conditions) + "\n" if ca_conditions else ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "OPTIONAL MATCH (ca:ClusteringAnalysis)-[:ClusteringAnalysisHasGeneCluster]->"
        "(gc:GeneCluster)-[:Gene_in_gene_cluster]->(g)\n"
        f"{pub_match}"
        f"{ca_where}"
        "WITH lt, g, gc, ca\n"
        "WITH collect(DISTINCT CASE WHEN g IS NULL THEN lt END) AS nf_raw,\n"
        "     collect(DISTINCT CASE WHEN g IS NOT NULL AND gc IS NULL\n"
        "             THEN lt END) AS nm_raw,\n"
        "     collect(CASE WHEN gc IS NOT NULL THEN\n"
        "       {lt: lt, cid: gc.id, ct: ca.cluster_type,\n"
        "        tt: ca.treatment_type, bfs: ca.background_factors,\n"
        "        aid: ca.id, aname: ca.name} END) AS rows\n"
        "WITH [x IN nf_raw WHERE x IS NOT NULL] AS not_found,\n"
        "     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched,\n"
        "     rows\n"
        "WITH not_found, not_matched,\n"
        "     size(rows) AS total_matching,\n"
        "     size(apoc.coll.toSet([r IN rows | r.cid])) AS total_clusters,\n"
        "     size(apoc.coll.toSet([r IN rows | r.lt])) AS genes_with_clusters,\n"
        "     size($locus_tags) - size(apoc.coll.toSet([r IN rows | r.lt]))\n"
        "       - size([x IN not_found WHERE x IS NOT NULL]) AS genes_without_clusters,\n"
        "     apoc.coll.frequencies([r IN rows | r.ct]) AS by_cluster_type,\n"
        "     apoc.coll.frequencies(\n"
        "       apoc.coll.flatten([r IN rows | coalesce(r.tt, [])])) AS by_treatment_type,\n"
        "     apoc.coll.frequencies(\n"
        "       apoc.coll.flatten([r IN rows | coalesce(r.bfs, [])])) AS by_background_factors,\n"
        "     apoc.coll.frequencies([r IN rows | r.aid]) AS by_analysis\n"
        "RETURN total_matching, total_clusters,\n"
        "       genes_with_clusters, genes_without_clusters,\n"
        "       not_found, not_matched,\n"
        "       by_cluster_type, by_treatment_type, by_background_factors,\n"
        "       by_analysis"
    )
    return cypher, params


def build_gene_clusters_by_gene(
    *,
    locus_tags: list[str],
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    analysis_ids: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_clusters_by_gene.

    Joins through ClusteringAnalysis for analysis fields and filters.

    RETURN keys (compact): locus_tag, gene_name, cluster_id, cluster_name,
    cluster_type, membership_score, analysis_id, analysis_name,
    treatment_type, background_factors.
    RETURN keys (verbose): adds cluster_method, member_count,
    cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern, treatment, light_condition,
    experimental_context, p_value.
    """
    params: dict = {"locus_tags": locus_tags}

    ca_conditions: list[str] = []
    if cluster_type is not None:
        ca_conditions.append("ca.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        ca_conditions.append(
            "ANY(tt IN ca.treatment_type WHERE tt IN $treatment_type)")
        params["treatment_type"] = treatment_type
    if background_factors is not None:
        ca_conditions.append(
            "ANY(bf IN coalesce(ca.background_factors, [])"
            " WHERE bf IN $background_factors)")
        params["background_factors"] = background_factors
    if analysis_ids is not None:
        ca_conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    pub_match = ""
    if publication_doi is not None:
        pub_match = "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        ca_conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    ca_where = ""
    if ca_conditions:
        ca_where = "WHERE " + " AND ".join(ca_conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       ca.cluster_method AS cluster_method"
            ",\n       gc.member_count AS member_count"
            ",\n       gc.functional_description AS cluster_functional_description"
            ",\n       gc.expression_dynamics AS cluster_expression_dynamics"
            ",\n       gc.temporal_pattern AS cluster_temporal_pattern"
            ",\n       ca.treatment AS treatment"
            ",\n       ca.light_condition AS light_condition"
            ",\n       ca.experimental_context AS experimental_context"
            ",\n       r.p_value AS p_value"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (ca:ClusteringAnalysis)-[:ClusteringAnalysisHasGeneCluster]->"
        "(gc:GeneCluster)-[r:Gene_in_gene_cluster]->(g:Gene {locus_tag: lt})\n"
        f"{pub_match}"
        f"{ca_where}"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       gc.id AS cluster_id, gc.name AS cluster_name,\n"
        "       ca.cluster_type AS cluster_type,\n"
        "       r.membership_score AS membership_score,\n"
        "       ca.id AS analysis_id, ca.name AS analysis_name,\n"
        "       ca.treatment_type AS treatment_type,\n"
        f"       coalesce(ca.background_factors, []) AS background_factors{verbose_cols}\n"
        f"ORDER BY g.locus_tag, gc.id{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_genes_in_cluster_summary(
    *,
    cluster_ids: list[str] | None = None,
    analysis_id: str | None = None,
    organism: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_in_cluster.

    Two entry modes:
    - cluster_ids: UNWIND specific cluster IDs (original mode)
    - analysis_id: match all clusters belonging to a ClusteringAnalysis

    RETURN keys: total_matching, by_organism, by_cluster,
    by_category_raw, not_found_clusters, not_matched_clusters.
    When analysis_id: also returns analysis_name.
    """
    params: dict = {"organism": organism}

    organism_filter = (
        "AND ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_name) CONTAINS word)\n"
        if organism is not None else ""
    )

    if analysis_id is not None:
        params["analysis_id"] = analysis_id
        match_block = (
            "MATCH (ca:ClusteringAnalysis {id: $analysis_id})"
            "-[:ClusteringAnalysisHasGeneCluster]->(gc:GeneCluster)\n"
            "WITH gc, gc.id AS cid, ca.name AS analysis_name\n"
            "OPTIONAL MATCH (gc)-[r:Gene_in_gene_cluster]->(g:Gene)\n"
            f"WHERE g IS NOT NULL {organism_filter}"
            "WITH cid, gc, g, analysis_name\n"
        )
        nf_nm_block = (
            "WITH collect(CASE WHEN g IS NOT NULL THEN\n"
            "       {lt: g.locus_tag, org: g.organism_name,\n"
            "        cat: coalesce(g.gene_category, 'Unknown'),\n"
            "        cid: cid, cname: gc.name} END) AS rows,\n"
            "     head(collect(DISTINCT analysis_name)) AS analysis_name\n"
        )
        return_suffix = ",\n       analysis_name"
        not_found_block = (
            "WITH rows, analysis_name,\n"
            "     [] AS not_found_clusters, [] AS not_matched_clusters\n"
        )
    else:
        params["cluster_ids"] = cluster_ids
        match_block = (
            "UNWIND $cluster_ids AS cid\n"
            "OPTIONAL MATCH (gc:GeneCluster {id: cid})\n"
            "OPTIONAL MATCH (gc)-[r:Gene_in_gene_cluster]->(g:Gene)\n"
            f"WHERE g IS NOT NULL {organism_filter}"
            "WITH cid, gc, g\n"
        )
        nf_nm_block = (
            "WITH collect(DISTINCT CASE WHEN gc IS NULL THEN cid END) AS nf_raw,\n"
            "     collect(DISTINCT CASE WHEN gc IS NOT NULL AND g IS NULL\n"
            "             THEN cid END) AS nm_raw,\n"
            "     collect(CASE WHEN g IS NOT NULL THEN\n"
            "       {lt: g.locus_tag, org: g.organism_name,\n"
            "        cat: coalesce(g.gene_category, 'Unknown'),\n"
            "        cid: cid, cname: gc.name} END) AS rows\n"
        )
        return_suffix = ""
        not_found_block = (
            "WITH [x IN nf_raw WHERE x IS NOT NULL] AS not_found_clusters,\n"
            "     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_clusters,\n"
            "     rows\n"
        )

    cypher = (
        f"{match_block}"
        f"{nf_nm_block}"
        f"{not_found_block}"
        "WITH not_found_clusters, not_matched_clusters,\n"
        "     size(rows) AS total_matching,\n"
        "     apoc.coll.frequencies([r IN rows | r.org]) AS by_organism,\n"
        "     apoc.coll.frequencies([r IN rows | r.cat]) AS by_category_raw,\n"
        "     [cid IN apoc.coll.toSet([r IN rows | r.cid]) |\n"
        "       {cluster_id: cid,\n"
        "        cluster_name: head([r IN rows WHERE r.cid = cid | r.cname]),\n"
        "        count: size([r IN rows WHERE r.cid = cid])}] AS by_cluster"
        + (",\n     analysis_name\n" if analysis_id is not None else "\n")
        + "RETURN total_matching, by_organism, by_cluster, by_category_raw,\n"
        f"       not_found_clusters, not_matched_clusters{return_suffix}"
    )
    return cypher, params


def build_genes_in_cluster(
    *,
    cluster_ids: list[str] | None = None,
    analysis_id: str | None = None,
    organism: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_in_cluster.

    Two entry modes:
    - cluster_ids: UNWIND specific cluster IDs (original mode)
    - analysis_id: match through CA → GC → Gene

    RETURN keys (compact): locus_tag, gene_name, product, gene_category,
    organism_name, cluster_id, cluster_name, membership_score.
    RETURN keys (verbose): adds gene_function_description, gene_summary,
    p_value, cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern.
    """
    params: dict = {}

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       g.function_description AS gene_function_description"
            ",\n       g.gene_summary AS gene_summary"
            ",\n       r.p_value AS p_value"
            ",\n       gc.functional_description AS cluster_functional_description"
            ",\n       gc.expression_dynamics AS cluster_expression_dynamics"
            ",\n       gc.temporal_pattern AS cluster_temporal_pattern"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    # Build match block based on entry mode
    if analysis_id is not None:
        params["analysis_id"] = analysis_id
        match_base = (
            "MATCH (ca:ClusteringAnalysis {id: $analysis_id})"
            "-[:ClusteringAnalysisHasGeneCluster]->"
            "(gc:GeneCluster)-[r:Gene_in_gene_cluster]->(g:Gene)\n"
        )
    else:
        params["cluster_ids"] = cluster_ids
        match_base = (
            "UNWIND $cluster_ids AS cid\n"
            "MATCH (gc:GeneCluster {id: cid})-[r:Gene_in_gene_cluster]->(g:Gene)\n"
        )

    # Conditional WHERE for organism filter
    if organism is not None:
        params["organism"] = organism
        cypher = (
            f"{match_base}"
            "WHERE ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(g.organism_name) CONTAINS word)\n"
        )
    else:
        cypher = match_base

    cypher += (
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.gene_category AS gene_category,\n"
        "       g.organism_name AS organism_name,\n"
        "       gc.id AS cluster_id, gc.name AS cluster_name,\n"
        f"       r.membership_score AS membership_score{verbose_cols}\n"
        f"ORDER BY gc.id, g.organism_name, g.locus_tag{skip_clause}{limit_clause}"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Ontology landscape builders (Child 1 of KG enrichment surface)
# ---------------------------------------------------------------------------


def build_ontology_landscape(
    *,
    ontology: str,
    organism_name: str,
    verbose: bool = False,
    min_gene_set_size: int = 5,
    max_gene_set_size: int = 500,
    tree: str | None = None,
    informative_only: bool = True,
    sources: list[str] | None = None,
    evidence: list[str] | None = None,
    max_tier: int | None = None,
    min_evidence_score: float | None = None,
    call_class: list[str] | None = None,
    interpro_type: str | None = None,
) -> tuple[str, dict]:
    """Per-(ontology, level[, facet]) aggregated landscape stats for one ontology.

    Returns one row per level reached by the organism's genes. Aggregates
    happen server-side — percentiles via percentileCont, distinct-gene
    coverage via apoc.coll.toSet(apoc.coll.flatten(...)), best_effort
    counts via CASE-sum. The min_gene_set_size/max_gene_set_size filter is
    applied after per-term aggregation so the per-level stats describe only
    terms that would be valid for pathway enrichment. Verbose adds top-3
    example terms in the same scan via pre-aggregation ORDER BY + collect[0..3].

    Trust filters bind on the gene→leaf relationship `r` ahead of the per-term
    aggregation, so landscape sizes match the enrichment tested sets for the
    same filters (spec §7.1). InterPro rows carry `interpro_type` in the
    grouping key — an ORA stratum is `(interpro_type, level)`, not `level`
    alone (spec §7.7).

    RETURN keys: level, tree, tree_code, n_terms_with_genes, n_genes_at_level,
    min_genes_per_term, q1_genes_per_term, median_genes_per_term,
    q3_genes_per_term, max_genes_per_term, n_best_effort.
    InterPro adds: interpro_type.
    Verbose adds: example_terms (list of {term_id, name, n_genes}).
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(
            f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}"
        )
    facet = _resolve_facet(ontology, tree=tree, interpro_type=interpro_type)
    trust_frag, trust_params = build_trust_filter_clause(
        ontology, sources=sources, evidence=evidence, max_tier=max_tier,
        min_evidence_score=min_evidence_score, call_class=call_class,
    )

    # Unified hierarchy walk via _hierarchy_walk helper.
    # This corrects the previous flat-Pfam treatment: Pfam is actually 2-level
    # (Pfam leaf + PfamClan parent), and the helper walks Pfam_in_pfam_clan.
    frag = _hierarchy_walk(ontology, direction="up")
    walk = frag["walk_up"] + "\n" if frag["walk_up"] else ""

    # Trust predicate: rides the gene→leaf MATCH, ahead of the walk and of the
    # per-term aggregation.
    bind_up = frag["bind_up"] + (f"\nWHERE {trust_frag}" if trust_frag else "")

    # Facet filter (BRITE `tree`, InterPro `interpro_type`): applied after the
    # hierarchy walk, before per-term aggregation. Flat ontologies own no
    # facet, so this never collides with the trust WHERE on the same MATCH.
    facet_filter = ""
    if facet is not None:
        facet_prop, facet_param, _facet_value = facet
        facet_filter = f"WHERE t.{facet_prop} = ${facet_param}\n"

    # Facet column in the level-rollup grouping key. Only for facets that are
    # not already first-class row columns (BRITE's `tree` / `tree_code` are).
    cfg_facet = ONTOLOGY_CONFIG[ontology].get("facet")
    if cfg_facet and cfg_facet["prop"] not in _STANDARD_TERM_ROW_COLUMNS:
        facet_col = cfg_facet["prop"]
        facet_group = f"t.{facet_col} AS {facet_col}, "
        facet_ret = f"{facet_col}, "
        facet_order = f"{facet_col}, "
    else:
        facet_group = facet_ret = facet_order = ""

    # Informative-only filter (default-on per spec § decision 3 for
    # ontology_landscape). Filters terms by per-term flag in the level-rollup.
    informative_filter = (
        "WITH t, g WHERE coalesce(t.is_uninformative, '') <> 'true'\n"
        if informative_only else ""
    )

    # Verbose clauses — Python string composition so compute is
    # short-circuited when verbose=False (see scoping D4).
    # pre_sort is an intermediate WITH..ORDER BY to pre-sort rows by gene count
    # before the final aggregation; collect()[0..3] then captures top-3.
    pre_sort = (
        "WITH t, n_g_per_term, term_genes ORDER BY n_g_per_term DESC\n"
        if verbose else ""
    )
    verbose_agg = (
        ",\n"
        "     collect({term_id:t.id, name:t.name, "
        "n_genes:n_g_per_term})[0..3] AS example_terms"
        if verbose else ""
    )
    verbose_ret = ",\n       example_terms" if verbose else ""

    cypher = (
        f"{bind_up}\n"
        f"{walk}"
        f"{facet_filter}"
        f"{informative_filter}"
        "WITH t, count(DISTINCT g) AS n_g_per_term, "
        "collect(DISTINCT g) AS term_genes\n"
        "WHERE n_g_per_term >= $min_gene_set_size "
        "AND n_g_per_term <= $max_gene_set_size\n"
        f"{pre_sort}"
        f"WITH {facet_group}t.level AS level, t.tree AS tree, "
        "t.tree_code AS tree_code,\n"
        "     count(t) AS n_terms_with_genes,\n"
        "     min(n_g_per_term) AS min_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.25) AS q1_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.5)  AS median_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.75) AS q3_genes_per_term,\n"
        "     max(n_g_per_term) AS max_genes_per_term,\n"
        "     apoc.coll.toSet(apoc.coll.flatten(collect(term_genes))) AS all_genes,\n"
        "     sum(CASE WHEN t.level_is_best_effort IS NOT NULL "
        "THEN 1 ELSE 0 END) AS n_best_effort"
        f"{verbose_agg}\n"
        f"RETURN {facet_ret}level, tree, tree_code, n_terms_with_genes,\n"
        "       size(all_genes) AS n_genes_at_level,\n"
        "       min_genes_per_term, q1_genes_per_term, median_genes_per_term,\n"
        "       q3_genes_per_term, max_genes_per_term,\n"
        f"       n_best_effort{verbose_ret}\n"
        f"ORDER BY {facet_order}level"
    )
    params = {
        "org": organism_name,
        "min_gene_set_size": min_gene_set_size,
        "max_gene_set_size": max_gene_set_size,
    }
    params.update(trust_params)
    if facet is not None:
        params[facet[1]] = facet[2]
    return cypher, params


def build_ontology_max_level(ontology: str) -> tuple[str, dict]:
    """Loosest-bound max hierarchy level for one ontology label.

    Used to validate a caller-supplied `level` before running enrichment.
    Flat ontologies (no hierarchy_rels) return `max_level=null` when no term
    carries a `level` property — callers treat that as 0. BRITE levels are
    per `tree`; `max(t.level)` over the whole label is a looser bound (fine
    for range-checking, not for per-tree precision).
    """
    label = ONTOLOGY_CONFIG[ontology]["label"]
    cypher = f"MATCH (t:`{label}`) RETURN max(t.level) AS max_level"
    return cypher, {}


def build_ontology_expcov(
    *,
    ontology: str,
    organism_name: str,
    experiment_ids: list[str],
    min_gene_set_size: int = 5,
    max_gene_set_size: int = 500,
) -> tuple[str, dict]:
    """Per-(experiment, level) coverage rows for ontology_landscape.

    For each experiment, count distinct genes that (a) are quantified
    in that experiment AND (b) reach any term at each level. The same
    min_gene_set_size/max_gene_set_size filter as Q_landscape is applied
    so coverage is computed over the same term population. Returns one row
    per (eid, level, facet_value). L2 applies zero-fill + min/median/max
    aggregation.

    `facet_value` carries the ontology's facet property (BRITE `tree`,
    InterPro `interpro_type`) and is null on the ontologies that own no
    facet. It is part of the key because a facet marks a separate stratum:
    without it every InterPro type at one level would report the same
    experiment coverage.

    RETURN keys: eid, n_total, level, facet_value, n_at_level.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(
            f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}"
        )

    # Unified hierarchy walk via _hierarchy_walk helper (shared with
    # build_ontology_landscape). For expcov we strip the Gene-Match prefix
    # from bind_up because `g` is already bound by the outer Experiment match.
    frag = _hierarchy_walk(ontology, direction="up")
    prefix = "MATCH (g:Gene {organism_name: $org})"
    assert frag["bind_up"].startswith(prefix), (
        f"_hierarchy_walk bind_up format changed; "
        f"expcov prefix-stripping needs update. Got: {frag['bind_up']!r}"
    )
    bind_tail = frag["bind_up"][len(prefix):]
    walk = frag["walk_up"] + "\n" if frag["walk_up"] else ""

    # Facet column in the stratum key — see docstring. `null` keeps the
    # RETURN shape uniform for the ontologies that own no facet.
    cfg_facet = ONTOLOGY_CONFIG[ontology].get("facet")
    if cfg_facet:
        facet_expr = f"t.{cfg_facet['prop']} AS facet_value"
    else:
        facet_expr = "null AS facet_value"

    cypher = (
        "UNWIND $experiment_ids AS eid\n"
        "MATCH (e:Experiment {id:eid})-[:Changes_expression_of]->"
        "(g:Gene {organism_name:$org})\n"
        "WITH eid, collect(DISTINCT g) AS quantified\n"
        "WITH eid, quantified, size(quantified) AS n_total\n"
        "UNWIND quantified AS g\n"
        f"MATCH (g){bind_tail}\n"
        f"{walk}"
        "WITH eid, n_total, t, count(DISTINCT g) AS n_g_per_term_exp, "
        "collect(DISTINCT g) AS term_genes_exp\n"
        "WHERE n_g_per_term_exp >= $min_gene_set_size "
        "AND n_g_per_term_exp <= $max_gene_set_size\n"
        f"WITH eid, n_total, t.level AS level, {facet_expr},\n"
        "     apoc.coll.toSet(apoc.coll.flatten("
        "collect(term_genes_exp))) AS level_genes\n"
        "RETURN eid, n_total, level, facet_value, "
        "size(level_genes) AS n_at_level\n"
        "ORDER BY eid, level, facet_value"
    )
    return cypher, {
        "org": organism_name,
        "experiment_ids": experiment_ids,
        "min_gene_set_size": min_gene_set_size,
        "max_gene_set_size": max_gene_set_size,
    }


def build_ontology_experiment_check(
    *,
    experiment_ids: list[str],
) -> tuple[str, dict]:
    """Classify experiment_ids — does each exist, which organism?

    Consumers (ontology_landscape) compare exp_organism to the
    canonical organism to decide found / not_found / not_matched.
    Returns one row per input eid, preserving order.

    RETURN keys: eid, exists (bool), exp_organism (str; '' if absent).
    """
    cypher = (
        "UNWIND $experiment_ids AS eid\n"
        "OPTIONAL MATCH (e:Experiment {id: eid})\n"
        "RETURN eid,\n"
        "       e IS NOT NULL AS exists,\n"
        "       coalesce(e.organism_name, '') AS exp_organism"
    )
    return cypher, {"experiment_ids": experiment_ids}


def build_ontology_organism_gene_count(
    *, organism_name: str,
) -> tuple[str, dict]:
    """Total gene count for one organism — denominator for genome_coverage.

    RETURN keys: total_genes (int).
    """
    cypher = "MATCH (g:Gene {organism_name:$org}) RETURN count(g) AS total_genes"
    return cypher, {"org": organism_name}


def _list_derived_metrics_where(
    *,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
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
) -> tuple[list[str], dict]:
    """Shared WHERE builder for build_list_derived_metrics{,_summary}.

    Returns (conditions, params). All filters are AND-joined at the caller.
    Organism uses space-split CONTAINS (mirrors _list_experiments_where).
    rankable / has_p_value bool params are coerced to the KG two-state literals
    for comparison against KG-stored strings.
    omics_type is scalar on DerivedMetric (unlike list-valued on Experiment);
    filter is exact-match after toUpper normalization.
    treatment_type / background_factors / growth_phases are wrapped in
    coalesce(..., []) defensively — the KG convention guarantees non-null
    lists, but the coalesce keeps the ANY() filter null-safe against
    schema drift.
    """
    conditions: list[str] = []
    params: dict = {}

    if organism:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(dm.organism_name) CONTAINS word)"
        )
        params["organism"] = organism

    if metric_types:
        conditions.append("dm.metric_type IN $metric_types")
        params["metric_types"] = metric_types

    if value_kind:
        conditions.append("dm.value_kind = $value_kind")
        params["value_kind"] = value_kind

    if compartment:
        conditions.append("dm.compartment = $compartment")
        params["compartment"] = compartment

    if omics_type:
        conditions.append("toUpper(dm.omics_type) = $omics_type_upper")
        params["omics_type_upper"] = omics_type.upper()

    if treatment_type:
        conditions.append(
            "ANY(t IN coalesce(dm.treatment_type, [])"
            " WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]

    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(dm.background_factors, [])"
            " WHERE toLower(bf) IN $background_factors_lower)"
        )
        params["background_factors_lower"] = [bf.lower() for bf in background_factors]

    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(dm.growth_phases, [])"
            " WHERE toLower(gp) IN $growth_phases_lower)"
        )
        params["growth_phases_lower"] = [gp.lower() for gp in growth_phases]

    if publication_doi:
        conditions.append("dm.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    if experiment_ids:
        conditions.append("dm.experiment_id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids

    if derived_metric_ids:
        conditions.append("dm.id IN $derived_metric_ids")
        params["derived_metric_ids"] = derived_metric_ids

    if rankable is not None:
        conditions.append("dm.rankable = $rankable_str")
        params["rankable_str"] = two_state("rankable", rankable)

    if has_p_value is not None:
        conditions.append("dm.has_p_value = $has_p_value_str")
        params["has_p_value_str"] = two_state("has_p_value", has_p_value)

    return conditions, params


def build_list_derived_metrics_summary(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
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
) -> tuple[str, dict]:
    """Build summary Cypher for list_derived_metrics.

    RETURN keys: total_entries, total_matching, by_organism, by_value_kind,
    by_metric_type, by_compartment, by_omics_type, by_treatment_type,
    by_background_factors, by_growth_phase.
    When search_text: adds score_max, score_median.
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, omics_type=omics_type,
        treatment_type=treatment_type, background_factors=background_factors,
        growth_phases=growth_phases, publication_doi=publication_doi,
        experiment_ids=experiment_ids, derived_metric_ids=derived_metric_ids,
        rankable=rankable, has_p_value=has_p_value,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)\n"
            "YIELD node AS dm, score\n"
        )
        score_cols = (
            ",\n     max(score) AS score_max"
            ",\n     percentileDisc(score, 0.5) AS score_median"
        )
        score_return = ", score_max, score_median"
    else:
        match_block = "MATCH (dm:DerivedMetric)\n"
        score_cols = ""
        score_return = ""

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "WITH collect(dm.organism_name) AS organisms,\n"
        "     collect(dm.value_kind) AS value_kinds,\n"
        "     collect(dm.metric_type) AS metric_types,\n"
        "     collect(dm.compartment) AS compartments,\n"
        "     collect(dm.omics_type) AS omics_types,\n"
        "     apoc.coll.flatten(collect(coalesce(dm.treatment_type, []))) AS treatment_types_flat,\n"
        "     apoc.coll.flatten(collect(coalesce(dm.background_factors, []))) AS background_factors_flat,\n"
        "     apoc.coll.flatten(collect(coalesce(dm.growth_phases, []))) AS growth_phases_flat,\n"
        f"     count(dm) AS total_matching{score_cols}\n"
        "CALL { MATCH (all_dm:DerivedMetric) RETURN count(all_dm) AS total_entries }\n"
        "RETURN total_entries, total_matching,\n"
        "       apoc.coll.frequencies(organisms) AS by_organism,\n"
        "       apoc.coll.frequencies(value_kinds) AS by_value_kind,\n"
        "       apoc.coll.frequencies(metric_types) AS by_metric_type,\n"
        "       apoc.coll.frequencies(compartments) AS by_compartment,\n"
        "       apoc.coll.frequencies(omics_types) AS by_omics_type,\n"
        "       apoc.coll.frequencies(treatment_types_flat) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(background_factors_flat) AS by_background_factors,\n"
        f"       apoc.coll.frequencies(growth_phases_flat) AS by_growth_phase{score_return}"
    )
    return cypher, params


def build_list_derived_metrics(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
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
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for list_derived_metrics.

    RETURN keys (compact): derived_metric_id, name, metric_type, value_kind,
    rankable, has_p_value, unit, allowed_categories (CASE-gated on
    value_kind='categorical'), field_description, organism_name,
    experiment_id, publication_doi, compartment, omics_type,
    treatment_type, background_factors, total_gene_count, growth_phases.
    When search_text: adds score.
    When verbose: adds treatment, light_condition, experimental_context.

    NOTE: p_value_threshold is intentionally absent from the RETURN — the
    property does not exist on any DerivedMetric in the current KG. See
    docs/tool-specs/list_derived_metrics.md §Verbose adds for the
    reinstatement rule (CASE-gated on dm.has_p_value='p_value').
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, omics_type=omics_type,
        treatment_type=treatment_type, background_factors=background_factors,
        growth_phases=growth_phases, publication_doi=publication_doi,
        experiment_ids=experiment_ids, derived_metric_ids=derived_metric_ids,
        rankable=rankable, has_p_value=has_p_value,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)\n"
            "YIELD node AS dm, score\n"
        )
        score_col = ",\n       score"
        order_prefix = "score DESC, "
    else:
        match_block = "MATCH (dm:DerivedMetric)\n"
        score_col = ""
        order_prefix = ""

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "RETURN dm.id AS derived_metric_id,\n"
        "       dm.name AS name,\n"
        "       dm.metric_type AS metric_type,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.rankable = 'rankable' AS rankable,\n"
        "       dm.has_p_value = 'p_value' AS has_p_value,\n"
        "       dm.unit AS unit,\n"
        "       CASE WHEN dm.value_kind = 'categorical'\n"
        "            THEN dm.allowed_categories ELSE null END AS allowed_categories,\n"
        "       dm.field_description AS field_description,\n"
        "       dm.organism_name AS organism_name,\n"
        "       dm.experiment_id AS experiment_id,\n"
        "       dm.publication_doi AS publication_doi,\n"
        "       dm.compartment AS compartment,\n"
        "       dm.omics_type AS omics_type,\n"
        "       coalesce(dm.treatment_type, []) AS treatment_type,\n"
        "       coalesce(dm.background_factors, []) AS background_factors,\n"
        "       dm.total_gene_count AS total_gene_count,\n"
        f"       coalesce(dm.growth_phases, []) AS growth_phases{score_col}{verbose_cols}\n"
        f"ORDER BY {order_prefix}dm.organism_name ASC, dm.value_kind ASC, dm.id ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_gene_derived_metrics_summary(
    *,
    locus_tags: list[str],
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for gene_derived_metrics.

    OPTIONAL MATCH cascade tracks not_found (no Gene) / not_matched
    (Gene present but no DM rows after filters, including kind-mismatch).
    DM-level filters wrapped inside `dm IS NULL OR (...)` so the OPTIONAL
    MATCH still emits a "no edge" row for not_matched bookkeeping.

    RETURN keys: total_matching, total_derived_metrics, genes_with_metrics,
    genes_without_metrics, not_found, not_matched, by_value_kind,
    by_metric_type, by_metric, by_compartment, by_treatment_type,
    by_background_factors, by_publication.
    """
    params: dict = {"locus_tags": locus_tags}

    dm_conditions: list[str] = []
    if metric_types is not None:
        dm_conditions.append("dm.metric_type IN $metric_types")
        params["metric_types"] = metric_types
    if value_kind is not None:
        dm_conditions.append("dm.value_kind = $value_kind")
        params["value_kind"] = value_kind
    if compartment is not None:
        dm_conditions.append("dm.compartment = $compartment")
        params["compartment"] = compartment
    if treatment_type is not None:
        dm_conditions.append(
            "ANY(t IN coalesce(dm.treatment_type, [])"
            " WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]
    if background_factors is not None:
        dm_conditions.append(
            "ANY(bf IN coalesce(dm.background_factors, [])"
            " WHERE toLower(bf) IN $bfs_lower)"
        )
        params["bfs_lower"] = [bf.lower() for bf in background_factors]
    if publication_doi is not None:
        dm_conditions.append("dm.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi
    if derived_metric_ids is not None:
        dm_conditions.append("dm.id IN $derived_metric_ids")
        params["derived_metric_ids"] = derived_metric_ids

    where_block = ""
    if dm_conditions:
        where_block = (
            "WHERE dm IS NULL OR ( "
            + " AND ".join(dm_conditions)
            + " )\n"
        )

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "OPTIONAL MATCH (g)<-[r:Derived_metric_quantifies_gene\n"
        "                    |Derived_metric_flags_gene\n"
        "                    |Derived_metric_classifies_gene]-(dm:DerivedMetric)\n"
        f"{where_block}"
        "WITH lt, g, dm, $locus_tags AS input_tags\n"
        "WITH input_tags,\n"
        "     collect(DISTINCT CASE WHEN g IS NULL THEN lt END) AS nf_raw,\n"
        "     collect(DISTINCT CASE WHEN g IS NOT NULL AND dm IS NULL THEN lt END) AS nm_raw,\n"
        "     collect(CASE WHEN dm IS NOT NULL THEN\n"
        "       {lt: lt, dm_id: dm.id, name: dm.name,\n"
        "        mt: dm.metric_type, vk: dm.value_kind,\n"
        "        comp: dm.compartment, doi: dm.publication_doi,\n"
        "        tt: dm.treatment_type, bfs: dm.background_factors} END) AS rows\n"
        "WITH input_tags,\n"
        "     [x IN nf_raw WHERE x IS NOT NULL] AS not_found,\n"
        "     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched,\n"
        "     rows\n"
        "RETURN size(rows) AS total_matching,\n"
        "       size(apoc.coll.toSet([r IN rows | r.dm_id])) AS total_derived_metrics,\n"
        "       size(apoc.coll.toSet([r IN rows | r.lt])) AS genes_with_metrics,\n"
        "       size(input_tags) - size(apoc.coll.toSet([r IN rows | r.lt]))\n"
        "         - size(not_found) AS genes_without_metrics,\n"
        "       not_found, not_matched,\n"
        "       apoc.coll.frequencies([r IN rows | r.vk]) AS by_value_kind,\n"
        "       apoc.coll.frequencies([r IN rows | r.mt]) AS by_metric_type,\n"
        "       [dm_id IN apoc.coll.toSet([r IN rows | r.dm_id]) |\n"
        "         {derived_metric_id: dm_id,\n"
        "          name: head([r IN rows WHERE r.dm_id = dm_id | r.name]),\n"
        "          metric_type: head([r IN rows WHERE r.dm_id = dm_id | r.mt]),\n"
        "          value_kind: head([r IN rows WHERE r.dm_id = dm_id | r.vk]),\n"
        "          count: size([r IN rows WHERE r.dm_id = dm_id])}] AS by_metric,\n"
        "       apoc.coll.frequencies([r IN rows | r.comp]) AS by_compartment,\n"
        "       apoc.coll.frequencies(\n"
        "         apoc.coll.flatten([r IN rows | coalesce(r.tt, [])])) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(\n"
        "         apoc.coll.flatten([r IN rows | coalesce(r.bfs, [])])) AS by_background_factors,\n"
        "       apoc.coll.frequencies([r IN rows | r.doi]) AS by_publication"
    )
    return cypher, params


def build_gene_derived_metrics(
    *,
    locus_tags: list[str],
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_derived_metrics.

    One row per gene × DM. `r.value` is polymorphic across edge types
    (float / 'flagged'/'not_flagged' string / category string) — branch on
    value_kind in the consumer.

    RETURN keys (compact, 11 columns today): locus_tag, gene_name,
    derived_metric_id, value_kind, name, value, rankable, has_p_value,
    rank_by_metric, metric_percentile, metric_bucket.

    NOTE: adjusted_p_value, significant are declared in the Pydantic
    Result model with default=None but NOT in the current Cypher RETURN
    — no edge in today's KG carries those props (no DM has
    has_p_value='p_value') and including them produces CyVer schema
    warnings. Mirrors p_value_threshold deferral in
    build_list_derived_metrics. Re-add CASE-gated RETURN columns
    (`CASE WHEN dm.has_p_value = 'p_value' THEN r.<col> ELSE null END`)
    when a has_p_value='p_value' DM lands.

    RETURN keys (verbose, 11 added today): metric_type,
    field_description, unit, allowed_categories, compartment,
    treatment_type, background_factors, publication_doi, treatment,
    light_condition, experimental_context. p_value (raw, edge-side)
    is also deferred until has_p_value DM lands.
    """
    params: dict = {"locus_tags": locus_tags}

    conditions: list[str] = []
    if metric_types is not None:
        conditions.append("dm.metric_type IN $metric_types")
        params["metric_types"] = metric_types
    if value_kind is not None:
        conditions.append("dm.value_kind = $value_kind")
        params["value_kind"] = value_kind
    if compartment is not None:
        conditions.append("dm.compartment = $compartment")
        params["compartment"] = compartment
    if treatment_type is not None:
        conditions.append(
            "ANY(t IN coalesce(dm.treatment_type, [])"
            " WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]
    if background_factors is not None:
        conditions.append(
            "ANY(bf IN coalesce(dm.background_factors, [])"
            " WHERE toLower(bf) IN $bfs_lower)"
        )
        params["bfs_lower"] = [bf.lower() for bf in background_factors]
    if publication_doi is not None:
        conditions.append("dm.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi
    if derived_metric_ids is not None:
        conditions.append("dm.id IN $derived_metric_ids")
        params["derived_metric_ids"] = derived_metric_ids

    where_block = ""
    if conditions:
        where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.metric_type AS metric_type"
            ",\n       dm.field_description AS field_description"
            ",\n       dm.unit AS unit"
            ",\n       CASE WHEN dm.value_kind = 'categorical'\n"
            "            THEN dm.allowed_categories ELSE null END "
            "AS allowed_categories"
            ",\n       dm.compartment AS compartment"
            ",\n       coalesce(dm.treatment_type, []) AS treatment_type"
            ",\n       coalesce(dm.background_factors, []) AS background_factors"
            ",\n       dm.publication_doi AS publication_doi"
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})\n"
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene\n"
        "                          |Derived_metric_flags_gene\n"
        "                          |Derived_metric_classifies_gene]->(g)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       dm.id AS derived_metric_id,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.name AS name,\n"
        "       r.value AS value,\n"
        "       dm.rankable = 'rankable' AS rankable,\n"
        "       dm.has_p_value = 'p_value' AS has_p_value,\n"
        "       CASE WHEN dm.rankable = 'rankable' THEN r.rank_by_metric ELSE null END AS rank_by_metric,\n"
        "       CASE WHEN dm.rankable = 'rankable' THEN r.metric_percentile ELSE null END AS metric_percentile,\n"
        "       CASE WHEN dm.rankable = 'rankable' THEN r.metric_bucket ELSE null END AS metric_bucket"
        f"{verbose_cols}\n"
        "ORDER BY g.locus_tag ASC, dm.value_kind ASC, dm.id ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_genes_by_numeric_metric_diagnostics(
    *,
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Pre-flight DM selection + gate-state probe for genes_by_numeric_metric.

    api/ runs this BEFORE summary/detail so it can:
      1. Validate every selected DM has `value_kind='numeric'` (raise on
         mismatch).
      2. Compute `excluded_derived_metrics` for rankable-/p-value-gated
         filters that don't apply to some/all selected DMs.
      3. Pass the surviving DM ID list to summary/detail.

    Reuses `_list_derived_metrics_where` for DM-scoping conditions with a
    hardcoded `value_kind='numeric'` predicate (this tool only drills into
    numeric DMs; mismatches surface here as zero-row results that api/
    converts to a ValueError listing offending IDs).

    RETURN keys (one row per surviving DM, 8 columns):
      derived_metric_id, metric_type, value_kind, name,
      rankable, has_p_value, total_gene_count, organism_name.
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism,
        metric_types=metric_types,
        value_kind="numeric",
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
        publication_doi=publication_doi,
        experiment_ids=experiment_ids,
        derived_metric_ids=derived_metric_ids,
    )

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)\n"
        f"{where_block}"
        "RETURN dm.id AS derived_metric_id,\n"
        "       dm.metric_type AS metric_type,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.name AS name,\n"
        "       dm.rankable = 'rankable' AS rankable,\n"
        "       dm.has_p_value = 'p_value' AS has_p_value,\n"
        "       dm.total_gene_count AS total_gene_count,\n"
        "       dm.organism_name AS organism_name\n"
        "ORDER BY dm.id ASC"
    )
    return cypher, params


def build_genes_by_numeric_metric_summary(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_percentile: float | None = None,
    max_percentile: float | None = None,
    bucket: list[str] | None = None,
    max_rank: int | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_numeric_metric.

    Takes the gate-validated `derived_metric_ids` list (api/ has already
    resolved metric_types and excluded incompatible DMs), plus all
    edge-level filters that survived gate validation. Produces the
    envelope rollups in one query.

    `significant_only` / `max_adjusted_p_value` are NOT parameters —
    they would never reach this builder against today's KG (api/ raises
    on the all-fail branch). When a has_p_value DM lands, add the
    corresponding edge-level WHERE conditions here.

    RETURN keys: total_matching, total_derived_metrics, total_genes,
    by_organism, by_compartment, by_publication, by_experiment,
    by_metric, top_categories_raw, genes_per_metric_max,
    genes_per_metric_median.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if min_value is not None:
        conditions.append("r.value >= $min_value")
        params["min_value"] = min_value
    if max_value is not None:
        conditions.append("r.value <= $max_value")
        params["max_value"] = max_value
    if min_percentile is not None:
        conditions.append("r.metric_percentile >= $min_percentile")
        params["min_percentile"] = min_percentile
    if max_percentile is not None:
        conditions.append("r.metric_percentile <= $max_percentile")
        params["max_percentile"] = max_percentile
    if bucket is not None:
        conditions.append("r.metric_bucket IN $bucket")
        params["bucket"] = bucket
    if max_rank is not None:
        conditions.append("r.rank_by_metric <= $max_rank")
        params["max_rank"] = max_rank

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene]->(g:Gene)\n"
        f"{where_block}"
        "WITH collect({\n"
        "  dm_id: dm.id, dm_name: dm.name, mt: dm.metric_type, vk: dm.value_kind,\n"
        "  org: g.organism_name, cat: coalesce(g.gene_category, 'Unknown'),\n"
        "  comp: dm.compartment, doi: dm.publication_doi, exp: dm.experiment_id,\n"
        "  lt: g.locus_tag,\n"
        "  value: r.value, rank: r.rank_by_metric,\n"
        "  dm_vmin: dm.value_min, dm_vq1: dm.value_q1, dm_vmed: dm.value_median,\n"
        "  dm_vq3: dm.value_q3, dm_vmax: dm.value_max\n"
        "}) AS rows\n"
        "RETURN\n"
        "  size(rows) AS total_matching,\n"
        "  size(apoc.coll.toSet([x IN rows | x.dm_id])) AS total_derived_metrics,\n"
        "  size(apoc.coll.toSet([x IN rows | x.lt])) AS total_genes,\n"
        "  apoc.coll.frequencies([x IN rows | x.org]) AS by_organism,\n"
        "  apoc.coll.frequencies([x IN rows | x.comp]) AS by_compartment,\n"
        "  apoc.coll.frequencies([x IN rows | x.doi]) AS by_publication,\n"
        "  apoc.coll.frequencies([x IN rows | x.exp]) AS by_experiment,\n"
        "  apoc.coll.frequencies([x IN rows | x.cat]) AS top_categories_raw,\n"
        "  [dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "    {derived_metric_id: dm_id,\n"
        "     name:        head([x IN rows WHERE x.dm_id = dm_id | x.dm_name]),\n"
        "     metric_type: head([x IN rows WHERE x.dm_id = dm_id | x.mt]),\n"
        "     value_kind:  head([x IN rows WHERE x.dm_id = dm_id | x.vk]),\n"
        "     count:       size([x IN rows WHERE x.dm_id = dm_id]),\n"
        "     value_min:    apoc.coll.min([x IN rows WHERE x.dm_id = dm_id | x.value]),\n"
        "     value_max:    apoc.coll.max([x IN rows WHERE x.dm_id = dm_id | x.value]),\n"
        "     value_median: apoc.coll.sort([x IN rows WHERE x.dm_id = dm_id | x.value])\n"
        "                     [toInteger(size([x IN rows WHERE x.dm_id = dm_id]) / 2)],\n"
        "     value_q1: apoc.coll.sort([x IN rows WHERE x.dm_id = dm_id | x.value])\n"
        "                 [toInteger(size([x IN rows WHERE x.dm_id = dm_id]) * 0.25)],\n"
        "     value_q3: apoc.coll.sort([x IN rows WHERE x.dm_id = dm_id | x.value])\n"
        "                 [toInteger(size([x IN rows WHERE x.dm_id = dm_id]) * 0.75)],\n"
        "     dm_value_min:    head([x IN rows WHERE x.dm_id = dm_id | x.dm_vmin]),\n"
        "     dm_value_q1:     head([x IN rows WHERE x.dm_id = dm_id | x.dm_vq1]),\n"
        "     dm_value_median: head([x IN rows WHERE x.dm_id = dm_id | x.dm_vmed]),\n"
        "     dm_value_q3:     head([x IN rows WHERE x.dm_id = dm_id | x.dm_vq3]),\n"
        "     dm_value_max:    head([x IN rows WHERE x.dm_id = dm_id | x.dm_vmax]),\n"
        "     rank_min: apoc.coll.min(\n"
        "       [x IN rows WHERE x.dm_id = dm_id AND x.rank IS NOT NULL | x.rank]),\n"
        "     rank_max: apoc.coll.max(\n"
        "       [x IN rows WHERE x.dm_id = dm_id AND x.rank IS NOT NULL | x.rank])\n"
        "    }] AS by_metric,\n"
        "  apoc.coll.max([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                 size([x IN rows WHERE x.dm_id = dm_id])]) AS genes_per_metric_max,\n"
        "  toFloat(apoc.coll.sort([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                          size([x IN rows WHERE x.dm_id = dm_id])])\n"
        "          [toInteger(size(apoc.coll.toSet([x IN rows | x.dm_id])) / 2)])\n"
        "    AS genes_per_metric_median"
    )
    return cypher, params


def build_genes_by_numeric_metric(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_percentile: float | None = None,
    max_percentile: float | None = None,
    bucket: list[str] | None = None,
    max_rank: int | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_numeric_metric.

    Takes the gate-validated `derived_metric_ids` list. Same edge-level
    filter set as the summary builder. Returns 14 compact columns
    (per-row gene + DM identity + gate echoes + value extras), plus 13
    verbose columns when verbose=True.

    NOTE: adjusted_p_value, significant declared in Pydantic Result with
    default=None, NOT in current Cypher RETURN — no edge in today's KG
    carries those props (no DM has has_p_value='p_value') and including them
    produces CyVer schema warnings. p_value (raw, edge-side) is also
    deferred for the same reason. Re-add CASE-gated RETURN columns
    (`CASE WHEN dm.has_p_value = 'p_value' THEN r.<col> ELSE null END`)
    when a has_p_value='p_value' DM lands.

    RETURN keys (compact, 14 columns): locus_tag, gene_name, product,
    gene_category, organism_name, derived_metric_id, name, value_kind,
    rankable, has_p_value, value, rank_by_metric, metric_percentile,
    metric_bucket.

    RETURN keys (verbose adds, 13 columns): metric_type,
    field_description, unit, compartment, experiment_id, publication_doi,
    treatment_type, background_factors, treatment, light_condition,
    experimental_context, gene_function_description, gene_summary.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if min_value is not None:
        conditions.append("r.value >= $min_value")
        params["min_value"] = min_value
    if max_value is not None:
        conditions.append("r.value <= $max_value")
        params["max_value"] = max_value
    if min_percentile is not None:
        conditions.append("r.metric_percentile >= $min_percentile")
        params["min_percentile"] = min_percentile
    if max_percentile is not None:
        conditions.append("r.metric_percentile <= $max_percentile")
        params["max_percentile"] = max_percentile
    if bucket is not None:
        conditions.append("r.metric_bucket IN $bucket")
        params["bucket"] = bucket
    if max_rank is not None:
        conditions.append("r.rank_by_metric <= $max_rank")
        params["max_rank"] = max_rank

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.metric_type AS metric_type"
            ",\n       dm.field_description AS field_description"
            ",\n       dm.unit AS unit"
            ",\n       dm.compartment AS compartment"
            ",\n       dm.experiment_id AS experiment_id"
            ",\n       dm.publication_doi AS publication_doi"
            ",\n       coalesce(dm.treatment_type, []) AS treatment_type"
            ",\n       coalesce(dm.background_factors, []) AS background_factors"
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
            ",\n       g.function_description AS gene_function_description"
            ",\n       g.gene_summary AS gene_summary"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene]->(g:Gene)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       g.gene_category AS gene_category,\n"
        "       g.organism_name AS organism_name,\n"
        "       dm.id AS derived_metric_id,\n"
        "       dm.name AS name,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.rankable = 'rankable' AS rankable,\n"
        "       dm.has_p_value = 'p_value' AS has_p_value,\n"
        "       r.value AS value,\n"
        "       CASE WHEN dm.rankable = 'rankable' THEN r.rank_by_metric ELSE null END AS rank_by_metric,\n"
        "       CASE WHEN dm.rankable = 'rankable' THEN r.metric_percentile ELSE null END AS metric_percentile,\n"
        "       CASE WHEN dm.rankable = 'rankable' THEN r.metric_bucket ELSE null END AS metric_bucket"
        f"{verbose_cols}\n"
        "ORDER BY r.rank_by_metric ASC, r.value DESC, dm.id ASC, g.locus_tag ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_genes_by_boolean_metric_diagnostics(
    *,
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Pre-flight DM selection + value_kind validation probe for boolean drill-down.

    Reuses `_list_derived_metrics_where` for DM-scoping conditions with a
    hardcoded `value_kind='boolean'` predicate. Mismatched IDs (numeric or
    categorical DMs passed in `derived_metric_ids`) surface as zero-row
    results that api/ converts into `not_found_ids`.

    RETURN keys (one row per surviving DM, 6 columns):
      derived_metric_id, metric_type, value_kind, name,
      total_gene_count, organism_name.
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism,
        metric_types=metric_types,
        value_kind="boolean",
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
        publication_doi=publication_doi,
        experiment_ids=experiment_ids,
        derived_metric_ids=derived_metric_ids,
    )

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)\n"
        f"{where_block}"
        "RETURN dm.id AS derived_metric_id,\n"
        "       dm.metric_type AS metric_type,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.name AS name,\n"
        "       dm.total_gene_count AS total_gene_count,\n"
        "       dm.organism_name AS organism_name\n"
        "ORDER BY dm.id ASC"
    )
    return cypher, params


def build_genes_by_boolean_metric_summary(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    flag: bool | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_boolean_metric.

    Takes the diagnostics-validated `derived_metric_ids` list plus the
    edge-level `flag` filter. Boolean DMs have no rankable / has_p_value
    gates so no gate-resolution step is needed.

    RETURN keys: total_matching, total_derived_metrics, total_genes,
    by_organism, by_compartment, by_publication, by_experiment,
    by_value, top_categories_raw, by_metric (per-DM filtered + full-DM
    precomputed counts), genes_per_metric_max, genes_per_metric_median.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if flag is not None:
        # Edge property `value` is a two-state string ('flagged' / 'not_flagged').
        conditions.append("r.value = $flag_str")
        params["flag_str"] = two_state("value", flag)

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_flags_gene]->(g:Gene)\n"
        f"{where_block}"
        "WITH collect({\n"
        "  dm_id: dm.id, dm_name: dm.name, mt: dm.metric_type, vk: dm.value_kind,\n"
        "  org: g.organism_name, cat: coalesce(g.gene_category, 'Unknown'),\n"
        "  comp: dm.compartment, doi: dm.publication_doi, exp: dm.experiment_id,\n"
        "  lt: g.locus_tag,\n"
        "  value: r.value,\n"
        "  dm_total: dm.total_gene_count,\n"
        "  dm_true: dm.flag_true_count,\n"
        "  dm_false: dm.flag_false_count\n"
        "}) AS rows\n"
        "RETURN\n"
        "  size(rows) AS total_matching,\n"
        "  size(apoc.coll.toSet([x IN rows | x.dm_id])) AS total_derived_metrics,\n"
        "  size(apoc.coll.toSet([x IN rows | x.lt])) AS total_genes,\n"
        "  apoc.coll.frequencies([x IN rows | x.org]) AS by_organism,\n"
        "  apoc.coll.frequencies([x IN rows | x.comp]) AS by_compartment,\n"
        "  apoc.coll.frequencies([x IN rows | x.doi]) AS by_publication,\n"
        "  apoc.coll.frequencies([x IN rows | x.exp]) AS by_experiment,\n"
        "  apoc.coll.frequencies([x IN rows | x.value]) AS by_value,\n"
        "  apoc.coll.frequencies([x IN rows | x.cat]) AS top_categories_raw,\n"
        "  [dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "    {derived_metric_id: dm_id,\n"
        "     name:        head([x IN rows WHERE x.dm_id = dm_id | x.dm_name]),\n"
        "     metric_type: head([x IN rows WHERE x.dm_id = dm_id | x.mt]),\n"
        "     value_kind:  head([x IN rows WHERE x.dm_id = dm_id | x.vk]),\n"
        "     count:       size([x IN rows WHERE x.dm_id = dm_id]),\n"
        "     true_count:  size([x IN rows WHERE x.dm_id = dm_id AND x.value = 'flagged']),\n"
        "     false_count: size([x IN rows WHERE x.dm_id = dm_id AND x.value = 'not_flagged']),\n"
        "     dm_total_gene_count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_total]),\n"
        "     dm_true_count:  head([x IN rows WHERE x.dm_id = dm_id | x.dm_true]),\n"
        "     dm_false_count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_false])\n"
        "    }] AS by_metric,\n"
        "  apoc.coll.max([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                 size([x IN rows WHERE x.dm_id = dm_id])]) AS genes_per_metric_max,\n"
        "  toFloat(apoc.coll.sort([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                          size([x IN rows WHERE x.dm_id = dm_id])])\n"
        "          [toInteger(size(apoc.coll.toSet([x IN rows | x.dm_id])) / 2)])\n"
        "    AS genes_per_metric_median"
    )
    return cypher, params


def build_genes_by_boolean_metric(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    flag: bool | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_boolean_metric.

    11 compact RETURN columns (per-row gene + DM identity + value),
    plus 13 verbose columns. No CASE-gate wrappers: boolean edges have
    no rankable / has_p_value extras.

    RETURN keys (compact, 11): locus_tag, gene_name, product, gene_category,
    organism_name, derived_metric_id, name, value_kind, rankable,
    has_p_value, value.

    RETURN keys (verbose adds, 13): metric_type, field_description, unit,
    compartment, experiment_id, publication_doi, treatment_type,
    background_factors, treatment, light_condition, experimental_context,
    gene_function_description, gene_summary.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if flag is not None:
        # Edge property `value` is a two-state string ('flagged' / 'not_flagged').
        conditions.append("r.value = $flag_str")
        params["flag_str"] = two_state("value", flag)

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.metric_type AS metric_type"
            ",\n       dm.field_description AS field_description"
            ",\n       dm.unit AS unit"
            ",\n       dm.compartment AS compartment"
            ",\n       dm.experiment_id AS experiment_id"
            ",\n       dm.publication_doi AS publication_doi"
            ",\n       coalesce(dm.treatment_type, []) AS treatment_type"
            ",\n       coalesce(dm.background_factors, []) AS background_factors"
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
            ",\n       g.function_description AS gene_function_description"
            ",\n       g.gene_summary AS gene_summary"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_flags_gene]->(g:Gene)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       g.gene_category AS gene_category,\n"
        "       g.organism_name AS organism_name,\n"
        "       dm.id AS derived_metric_id,\n"
        "       dm.name AS name,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.rankable = 'rankable' AS rankable,\n"
        "       dm.has_p_value = 'p_value' AS has_p_value,\n"
        "       r.value AS value"
        f"{verbose_cols}\n"
        "ORDER BY dm.id ASC, g.locus_tag ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_genes_by_categorical_metric_diagnostics(
    *,
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Pre-flight DM selection + value_kind validation probe for categorical drill-down.

    Reuses `_list_derived_metrics_where` for DM-scoping conditions with a
    hardcoded `value_kind='categorical'` predicate. Mismatched IDs surface
    as zero-row results that api/ converts into `not_found_ids`.

    RETURN keys (one row per surviving DM, 7 columns):
      derived_metric_id, metric_type, value_kind, name,
      total_gene_count, organism_name, allowed_categories.
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism,
        metric_types=metric_types,
        value_kind="categorical",
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
        publication_doi=publication_doi,
        experiment_ids=experiment_ids,
        derived_metric_ids=derived_metric_ids,
    )

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)\n"
        f"{where_block}"
        "RETURN dm.id AS derived_metric_id,\n"
        "       dm.metric_type AS metric_type,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.name AS name,\n"
        "       dm.total_gene_count AS total_gene_count,\n"
        "       dm.organism_name AS organism_name,\n"
        "       dm.allowed_categories AS allowed_categories\n"
        "ORDER BY dm.id ASC"
    )
    return cypher, params


def build_genes_by_categorical_metric_summary(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    categories: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_categorical_metric.

    Takes the diagnostics-validated `derived_metric_ids` list plus the
    edge-level `categories` filter (api/ has already validated each
    category against the union of allowed_categories per DM).

    RETURN keys: total_matching, total_derived_metrics, total_genes,
    by_organism, by_compartment, by_publication, by_experiment,
    by_category, top_categories_raw, by_metric (per-DM filtered slice +
    full-DM precomputed histogram via dm.category_labels /
    dm.category_counts), genes_per_metric_max, genes_per_metric_median.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if categories is not None:
        conditions.append("r.value IN $categories")
        params["categories"] = categories

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_classifies_gene]->(g:Gene)\n"
        f"{where_block}"
        "WITH collect({\n"
        "  dm_id: dm.id, dm_name: dm.name, mt: dm.metric_type, vk: dm.value_kind,\n"
        "  org: g.organism_name, cat: coalesce(g.gene_category, 'Unknown'),\n"
        "  comp: dm.compartment, doi: dm.publication_doi, exp: dm.experiment_id,\n"
        "  lt: g.locus_tag,\n"
        "  value: r.value,\n"
        "  dm_total: dm.total_gene_count,\n"
        "  dm_labels: dm.category_labels,\n"
        "  dm_counts: dm.category_counts,\n"
        "  dm_allowed: dm.allowed_categories\n"
        "}) AS rows\n"
        "RETURN\n"
        "  size(rows) AS total_matching,\n"
        "  size(apoc.coll.toSet([x IN rows | x.dm_id])) AS total_derived_metrics,\n"
        "  size(apoc.coll.toSet([x IN rows | x.lt])) AS total_genes,\n"
        "  apoc.coll.frequencies([x IN rows | x.org]) AS by_organism,\n"
        "  apoc.coll.frequencies([x IN rows | x.comp]) AS by_compartment,\n"
        "  apoc.coll.frequencies([x IN rows | x.doi]) AS by_publication,\n"
        "  apoc.coll.frequencies([x IN rows | x.exp]) AS by_experiment,\n"
        "  apoc.coll.frequencies([x IN rows | x.value]) AS by_category,\n"
        "  apoc.coll.frequencies([x IN rows | x.cat]) AS top_categories_raw,\n"
        "  [dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "    {derived_metric_id: dm_id,\n"
        "     name:        head([x IN rows WHERE x.dm_id = dm_id | x.dm_name]),\n"
        "     metric_type: head([x IN rows WHERE x.dm_id = dm_id | x.mt]),\n"
        "     value_kind:  head([x IN rows WHERE x.dm_id = dm_id | x.vk]),\n"
        "     count:       size([x IN rows WHERE x.dm_id = dm_id]),\n"
        "     by_category: apoc.coll.frequencies([x IN rows WHERE x.dm_id = dm_id | x.value]),\n"
        "     allowed_categories:  head([x IN rows WHERE x.dm_id = dm_id | x.dm_allowed]),\n"
        "     dm_total_gene_count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_total]),\n"
        "     dm_by_category:\n"
        "       [i IN range(0,\n"
        "            size(head([x IN rows WHERE x.dm_id = dm_id | x.dm_labels])) - 1)\n"
        "        | {item:  head([x IN rows WHERE x.dm_id = dm_id | x.dm_labels])[i],\n"
        "           count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_counts])[i]}]\n"
        "    }] AS by_metric,\n"
        "  apoc.coll.max([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                 size([x IN rows WHERE x.dm_id = dm_id])]) AS genes_per_metric_max,\n"
        "  toFloat(apoc.coll.sort([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                          size([x IN rows WHERE x.dm_id = dm_id])])\n"
        "          [toInteger(size(apoc.coll.toSet([x IN rows | x.dm_id])) / 2)])\n"
        "    AS genes_per_metric_median"
    )
    return cypher, params


def build_genes_by_categorical_metric(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    categories: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_categorical_metric.

    11 compact RETURN columns (per-row gene + DM identity + value),
    plus 14 verbose columns (= boolean's 13 verbose + allowed_categories).
    No CASE-gate wrappers: categorical edges have no rankable / has_p_value
    extras.

    RETURN keys (compact, 11): locus_tag, gene_name, product, gene_category,
    organism_name, derived_metric_id, name, value_kind, rankable,
    has_p_value, value.

    RETURN keys (verbose adds, 14): metric_type, field_description, unit,
    compartment, experiment_id, publication_doi, treatment_type,
    background_factors, treatment, light_condition, experimental_context,
    gene_function_description, gene_summary, allowed_categories.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if categories is not None:
        conditions.append("r.value IN $categories")
        params["categories"] = categories

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.metric_type AS metric_type"
            ",\n       dm.field_description AS field_description"
            ",\n       dm.unit AS unit"
            ",\n       dm.compartment AS compartment"
            ",\n       dm.experiment_id AS experiment_id"
            ",\n       dm.publication_doi AS publication_doi"
            ",\n       coalesce(dm.treatment_type, []) AS treatment_type"
            ",\n       coalesce(dm.background_factors, []) AS background_factors"
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
            ",\n       g.function_description AS gene_function_description"
            ",\n       g.gene_summary AS gene_summary"
            ",\n       dm.allowed_categories AS allowed_categories"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_classifies_gene]->(g:Gene)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       g.gene_category AS gene_category,\n"
        "       g.organism_name AS organism_name,\n"
        "       dm.id AS derived_metric_id,\n"
        "       dm.name AS name,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.rankable = 'rankable' AS rankable,\n"
        "       dm.has_p_value = 'p_value' AS has_p_value,\n"
        "       r.value AS value"
        f"{verbose_cols}\n"
        "ORDER BY r.value ASC, dm.id ASC, g.locus_tag ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# genes_by_metabolite — two-arm metabolism + transport detail builders + summary
# ---------------------------------------------------------------------------


def _genes_by_metabolite_metabolism_where(
    *,
    metabolite_ids: list[str],
    organism: str,
    exclude_metabolite_ids: list[str] | None = None,
    ec_numbers: list[str] | None = None,
    mass_balance: str | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params for the metabolism arm.

    `substrate_depth` is not accepted here — it is a transport-arm
    filter and the metabolism arm is unaffected by it (per the per-arm
    filter scope rule in 'Special handling').
    """
    conditions: list[str] = [
        "m.id IN $metabolite_ids",
        "ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_name) CONTAINS word)",
    ]
    params: dict = {
        "metabolite_ids": metabolite_ids,
        "organism": organism,
    }
    if exclude_metabolite_ids:
        conditions.append("(NOT (m.id IN $exclude_metabolite_ids))")
        params["exclude_metabolite_ids"] = exclude_metabolite_ids
    if ec_numbers:
        conditions.append(
            "ANY(ec IN $ec_numbers WHERE ec IN coalesce(r.ec_numbers, []))"
        )
        params["ec_numbers"] = ec_numbers
    if mass_balance is not None:
        conditions.append("r.mass_balance = $mass_balance")
        params["mass_balance"] = mass_balance
    if metabolite_pathway_ids:
        conditions.append(
            "ANY(p IN $metabolite_pathway_ids "
            "WHERE p IN coalesce(m.pathway_ids, []))"
        )
        params["metabolite_pathway_ids"] = metabolite_pathway_ids
    if gene_categories:
        conditions.append("g.gene_category IN $gene_categories")
        params["gene_categories"] = gene_categories
    return conditions, params


def _genes_by_metabolite_transport_where(
    *,
    metabolite_ids: list[str],
    organism: str,
    exclude_metabolite_ids: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
    substrate_depth: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params for the transport arm.

    Always carries the deepest-attachment predicate (decision 4) so the
    arm walks only the gene's deepest TCDB attachments.

    `ec_numbers` / `mass_balance` are not accepted here — they are
    metabolism-arm filters and the transport arm is unaffected by them.
    `substrate_depth` (list of 'most_specific' / 'inherited') adds
    `r.substrate_depth IN $substrate_depth` on the transport edge.
    """
    conditions: list[str] = [
        "m.id IN $metabolite_ids",
        "ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_name) CONTAINS word)",
        TCDB_DEEPEST_ATTACHMENT_PREDICATE,
    ]
    params: dict = {
        "metabolite_ids": metabolite_ids,
        "organism": organism,
    }
    if exclude_metabolite_ids:
        conditions.append("(NOT (m.id IN $exclude_metabolite_ids))")
        params["exclude_metabolite_ids"] = exclude_metabolite_ids
    if metabolite_pathway_ids:
        conditions.append(
            "ANY(p IN $metabolite_pathway_ids "
            "WHERE p IN coalesce(m.pathway_ids, []))"
        )
        params["metabolite_pathway_ids"] = metabolite_pathway_ids
    if gene_categories:
        conditions.append("g.gene_category IN $gene_categories")
        params["gene_categories"] = gene_categories
    if substrate_depth:
        conditions.append("r.substrate_depth IN $substrate_depth")
        params["substrate_depth"] = substrate_depth
    return conditions, params


def build_genes_by_metabolite_metabolism(
    *,
    metabolite_ids: list[str],
    organism: str,
    exclude_metabolite_ids: list[str] | None = None,
    ec_numbers: list[str] | None = None,
    mass_balance: str | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for the metabolism arm of genes_by_metabolite.

    RETURN keys (compact, 13 + 2 null-padding columns to align with the
    transport arm): locus_tag, gene_name, product, evidence_source
    ('metabolism'), substrate_depth (always null), tcdb_evidence_score
    (always null), reaction_id,
    reaction_name, ec_numbers, mass_balance, tcdb_family_id (null),
    tcdb_family_name (null), metabolite_id, metabolite_name,
    metabolite_formula, metabolite_mass, metabolite_chebi_id.

    Verbose adds: gene_category, metabolite_inchikey, metabolite_smiles,
    metabolite_mnxm_id, metabolite_hmdb_id, reaction_mnxr_id,
    reaction_rhea_ids, tcdb_level_kind (null), tc_class_id (null).
    """
    conditions, params = _genes_by_metabolite_metabolism_where(
        metabolite_ids=metabolite_ids,
        organism=organism,
        exclude_metabolite_ids=exclude_metabolite_ids,
        ec_numbers=ec_numbers,
        mass_balance=mass_balance,
        metabolite_pathway_ids=metabolite_pathway_ids,
        gene_categories=gene_categories,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = (
        ",\n       g.gene_category AS gene_category"
        ",\n       m.inchikey AS metabolite_inchikey"
        ",\n       m.smiles AS metabolite_smiles"
        ",\n       m.mnxm_id AS metabolite_mnxm_id"
        ",\n       m.hmdb_id AS metabolite_hmdb_id"
        ",\n       r.mnxr_id AS reaction_mnxr_id"
        ",\n       r.rhea_ids AS reaction_rhea_ids"
        ",\n       null AS tcdb_level_kind"
        ",\n       null AS tc_class_id"
        if verbose else ""
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "MATCH (g:Gene)-[:Gene_catalyzes_reaction]->"
        "(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       'metabolism' AS evidence_source,\n"
        "       null AS substrate_depth,\n"
        "       null AS tcdb_evidence_score,\n"
        "       null AS transport_substrate_resolution,\n"
        "       r.id AS reaction_id,\n"
        "       r.name AS reaction_name,\n"
        "       coalesce(r.ec_numbers, []) AS ec_numbers,\n"
        "       r.mass_balance AS mass_balance,\n"
        "       null AS tcdb_family_id,\n"
        "       null AS tcdb_family_name,\n"
        "       m.id AS metabolite_id,\n"
        "       m.name AS metabolite_name,\n"
        "       m.formula AS metabolite_formula,\n"
        "       m.mass AS metabolite_mass,\n"
        "       m.chebi_id AS metabolite_chebi_id"
        f"{verbose_cols}\n"
        "ORDER BY metabolite_id, reaction_id, locus_tag"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_genes_by_metabolite_transport(
    *,
    metabolite_ids: list[str],
    organism: str,
    exclude_metabolite_ids: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
    substrate_depth: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for the transport arm of genes_by_metabolite.

    Walks deepest TCDB attachments only (decision 4 predicate).

    RETURN keys (compact): locus_tag, gene_name, product,
    evidence_source ('transport'), substrate_depth (edge
    `r.substrate_depth`: 'most_specific' | 'inherited'),
    tcdb_evidence_score (edge `gt.evidence_score`, float [0,1]),
    reaction_id (null), reaction_name (null), ec_numbers (null),
    mass_balance (null), tcdb_family_id, tcdb_family_name,
    metabolite_id, metabolite_name, metabolite_formula,
    metabolite_mass, metabolite_chebi_id.

    Sort: metabolite_id, depth tier (most_specific before inherited),
    tcdb_evidence_score DESC within the tier, tcdb_family_id, locus_tag.

    Verbose adds: gene_category, metabolite_inchikey, metabolite_smiles,
    metabolite_mnxm_id, metabolite_hmdb_id, reaction_mnxr_id (null),
    reaction_rhea_ids (null), tcdb_level_kind, tc_class_id.

    `ec_numbers` / `mass_balance` are not accepted (per per-arm filter
    scope rule); passing them raises `TypeError`.
    """
    conditions, params = _genes_by_metabolite_transport_where(
        metabolite_ids=metabolite_ids,
        organism=organism,
        exclude_metabolite_ids=exclude_metabolite_ids,
        metabolite_pathway_ids=metabolite_pathway_ids,
        gene_categories=gene_categories,
        substrate_depth=substrate_depth,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = (
        ",\n       g.gene_category AS gene_category"
        ",\n       m.inchikey AS metabolite_inchikey"
        ",\n       m.smiles AS metabolite_smiles"
        ",\n       m.mnxm_id AS metabolite_mnxm_id"
        ",\n       m.hmdb_id AS metabolite_hmdb_id"
        ",\n       null AS reaction_mnxr_id"
        ",\n       null AS reaction_rhea_ids"
        ",\n       tf.level_kind AS tcdb_level_kind"
        ",\n       tf.tc_class_id AS tc_class_id"
        if verbose else ""
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "MATCH (g:Gene)-[gt:Gene_has_tcdb_family]->"
        "(tf:TcdbFamily)-[r:Tcdb_family_transports_metabolite]->(m:Metabolite)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       'transport' AS evidence_source,\n"
        "       r.substrate_depth AS substrate_depth,\n"
        "       gt.evidence_score AS tcdb_evidence_score,\n"
        "       g.transport_substrate_resolution AS transport_substrate_resolution,\n"
        "       null AS reaction_id,\n"
        "       null AS reaction_name,\n"
        "       null AS ec_numbers,\n"
        "       null AS mass_balance,\n"
        "       tf.id AS tcdb_family_id,\n"
        "       tf.name AS tcdb_family_name,\n"
        "       m.id AS metabolite_id,\n"
        "       m.name AS metabolite_name,\n"
        "       m.formula AS metabolite_formula,\n"
        "       m.mass AS metabolite_mass,\n"
        "       m.chebi_id AS metabolite_chebi_id"
        f"{verbose_cols}\n"
        "ORDER BY metabolite_id,"
        " CASE WHEN r.substrate_depth = 'most_specific' THEN 0 ELSE 1 END,"
        " tcdb_evidence_score DESC,"
        " tcdb_family_id, locus_tag"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_genes_by_metabolite_summary(
    *,
    metabolite_ids: list[str],
    organism: str,
    exclude_metabolite_ids: list[str] | None = None,
    ec_numbers: list[str] | None = None,
    mass_balance: str | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
    substrate_depth: list[str] | None = None,
    arms: tuple[str, ...] = ("metabolism", "transport"),
) -> tuple[str, dict]:
    """Build single-pass aggregation Cypher for genes_by_metabolite.

    Per-arm filter scope (matches detail builders): `ec_numbers` and
    `mass_balance` apply only to the metabolism arm of the UNION;
    `substrate_depth` applies only to the transport arm (which always
    walks deepest TCDB attachments only — decision 4);
    `metabolite_pathway_ids` and `gene_categories` apply to both arms.

    `arms` selects which arm bodies are emitted in the inner CALL{...}
    subquery. When only one arm is selected, the other's MATCH path is
    omitted entirely.

    RETURN keys: total_matching, gene_count_total, reaction_count_total,
    transporter_count_total, metabolite_count_total,
    rows_by_evidence_source (long-format list of {evidence_source, count}),
    rows_by_substrate_depth (long-format list of {substrate_depth, count},
       transport rows only),
    by_metabolite (per-metabolite rollup with metabolism_rows /
       transport_most_specific_rows / transport_inherited_rows),
    top_reactions, top_tcdb_families (entries carry level_kind +
       substrate_depth, the latter 'most_specific' when any collected row
       for the family is most_specific, else 'inherited'),
    top_gene_categories, top_genes (entries carry the gene-level
       transport_substrate_resolution + tcdb_evidence_score_max, null on
       metabolism-only genes).

    The api/ layer post-processes some apoc.coll outputs into the
    documented top-N shape; the contract here is the RETURN keys and
    their semantics.
    """
    params: dict = {
        "metabolite_ids": metabolite_ids,
        "organism": organism,
    }

    arm_blocks: list[str] = []

    if "metabolism" in arms:
        m_conditions, m_params = _genes_by_metabolite_metabolism_where(
            metabolite_ids=metabolite_ids,
            organism=organism,
            exclude_metabolite_ids=exclude_metabolite_ids,
            ec_numbers=ec_numbers,
            mass_balance=mass_balance,
            metabolite_pathway_ids=metabolite_pathway_ids,
            gene_categories=gene_categories,
        )
        params.update(m_params)
        m_where = "  WHERE " + " AND ".join(m_conditions) + "\n"
        arm_blocks.append(
            "  MATCH (g:Gene)-[:Gene_catalyzes_reaction]->"
            "(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)\n"
            f"{m_where}"
            "  RETURN g, r, null AS tf, m, 'metabolism' AS es,"
            " null AS sdepth, null AS tscore"
        )

    if "transport" in arms:
        t_conditions, t_params = _genes_by_metabolite_transport_where(
            metabolite_ids=metabolite_ids,
            organism=organism,
            exclude_metabolite_ids=exclude_metabolite_ids,
            metabolite_pathway_ids=metabolite_pathway_ids,
            gene_categories=gene_categories,
            substrate_depth=substrate_depth,
        )
        params.update(t_params)
        t_where = "  WHERE " + " AND ".join(t_conditions) + "\n"
        arm_blocks.append(
            "  MATCH (g:Gene)-[gt:Gene_has_tcdb_family]->"
            "(tf:TcdbFamily)-[r:Tcdb_family_transports_metabolite]->(m:Metabolite)\n"
            f"{t_where}"
            "  RETURN g, null AS r, tf, m, 'transport' AS es,\n"
            "         r.substrate_depth AS sdepth,"
            " gt.evidence_score AS tscore"
        )

    union_body = "\n  UNION\n".join(arm_blocks)

    cypher = (
        "CALL {\n"
        f"{union_body}\n"
        "}\n"
        "WITH g, r, tf, m, es, sdepth, tscore\n"
        "WITH count(*) AS total_matching,\n"
        "     count(DISTINCT g) AS gene_count_total,\n"
        "     count(DISTINCT r) AS reaction_count_total,\n"
        "     count(DISTINCT tf) AS transporter_count_total,\n"
        "     count(DISTINCT m) AS metabolite_count_total,\n"
        "     collect({\n"
        "       locus_tag: g.locus_tag,\n"
        "       gene_name: g.gene_name,\n"
        "       gene_category: g.gene_category,\n"
        "       transport_substrate_resolution: g.transport_substrate_resolution,\n"
        "       tcdb_evidence_score_max: g.tcdb_evidence_score_max,\n"
        "       reaction_id: r.id,\n"
        "       reaction_name: r.name,\n"
        "       reaction_ec_numbers: coalesce(r.ec_numbers, []),\n"
        "       tcdb_family_id: tf.id,\n"
        "       tcdb_family_name: tf.name,\n"
        "       tcdb_family_level_kind: tf.level_kind,\n"
        "       metabolite_id: m.id,\n"
        "       metabolite_name: m.name,\n"
        "       metabolite_formula: m.formula,\n"
        "       es: es,\n"
        "       substrate_depth: sdepth,\n"
        "       tcdb_evidence_score: tscore\n"
        "     }) AS rows\n"
        "WITH total_matching, gene_count_total, reaction_count_total,\n"
        "     transporter_count_total, metabolite_count_total, rows,\n"
        "     [es IN apoc.coll.toSet([row IN rows | row.es]) |\n"
        "        {evidence_source: es,\n"
        "         count: size([row IN rows WHERE row.es = es])}]"
        " AS rows_by_evidence_source,\n"
        "     [sd IN apoc.coll.toSet("
        "[row IN rows WHERE row.substrate_depth IS NOT NULL"
        " | row.substrate_depth]) |\n"
        "        {substrate_depth: sd,\n"
        "         count: size([row IN rows WHERE row.substrate_depth = sd])}]"
        " AS rows_by_substrate_depth\n"
        "// Per-metabolite rollup with per-evidence row breakdowns\n"
        "WITH total_matching, gene_count_total, reaction_count_total,\n"
        "     transporter_count_total, metabolite_count_total, rows,\n"
        "     rows_by_evidence_source, rows_by_substrate_depth,\n"
        "     [mid IN apoc.coll.toSet([row IN rows | row.metabolite_id]) |\n"
        "        {metabolite_id: mid,\n"
        "         name: head([row IN rows WHERE row.metabolite_id = mid"
        " | row.metabolite_name]),\n"
        "         formula: head([row IN rows WHERE row.metabolite_id = mid"
        " | row.metabolite_formula]),\n"
        "         rows: size([row IN rows WHERE row.metabolite_id = mid]),\n"
        "         gene_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.metabolite_id = mid | row.locus_tag])),\n"
        "         reaction_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.metabolite_id = mid AND row.reaction_id"
        " IS NOT NULL | row.reaction_id])),\n"
        "         transporter_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.metabolite_id = mid AND row.tcdb_family_id"
        " IS NOT NULL | row.tcdb_family_id])),\n"
        "         metabolism_rows: size("
        "[row IN rows WHERE row.metabolite_id = mid"
        " AND row.es = 'metabolism']),\n"
        "         transport_most_specific_rows: size("
        "[row IN rows WHERE row.metabolite_id = mid"
        " AND row.substrate_depth = 'most_specific']),\n"
        "         transport_inherited_rows: size("
        "[row IN rows WHERE row.metabolite_id = mid"
        " AND row.substrate_depth = 'inherited'])}]"
        " AS by_metabolite\n"
        "// Top-N rollups: api/ layer trims to top 10 by gene_count\n"
        "WITH total_matching, gene_count_total, reaction_count_total,\n"
        "     transporter_count_total, metabolite_count_total,\n"
        "     rows_by_evidence_source, rows_by_substrate_depth,\n"
        "     by_metabolite, rows,\n"
        "     [rid IN apoc.coll.toSet("
        "[row IN rows WHERE row.reaction_id IS NOT NULL | row.reaction_id]) |\n"
        "        {reaction_id: rid,\n"
        "         name: head("
        "[row IN rows WHERE row.reaction_id = rid | row.reaction_name]),\n"
        "         ec_numbers: head("
        "[row IN rows WHERE row.reaction_id = rid"
        " | row.reaction_ec_numbers]),\n"
        "         gene_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.reaction_id = rid | row.locus_tag])),\n"
        "         metabolite_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.reaction_id = rid"
        " | row.metabolite_id]))}] AS top_reactions,\n"
        "     [tfid IN apoc.coll.toSet("
        "[row IN rows WHERE row.tcdb_family_id IS NOT NULL"
        " | row.tcdb_family_id]) |\n"
        "        {tcdb_family_id: tfid,\n"
        "         tcdb_family_name: head("
        "[row IN rows WHERE row.tcdb_family_id = tfid"
        " | row.tcdb_family_name]),\n"
        "         level_kind: head("
        "[row IN rows WHERE row.tcdb_family_id = tfid"
        " | row.tcdb_family_level_kind]),\n"
        "         substrate_depth: CASE WHEN 'most_specific' IN "
        "[row IN rows WHERE row.tcdb_family_id = tfid"
        " | row.substrate_depth]"
        " THEN 'most_specific' ELSE 'inherited' END,\n"
        "         gene_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.tcdb_family_id = tfid | row.locus_tag])),\n"
        "         metabolite_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.tcdb_family_id = tfid"
        " | row.metabolite_id]))}]"
        " AS top_tcdb_families,\n"
        "     [cat IN apoc.coll.toSet("
        "[row IN rows WHERE row.gene_category IS NOT NULL"
        " | row.gene_category]) |\n"
        "        {category: cat,\n"
        "         gene_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.gene_category = cat | row.locus_tag]))}]"
        " AS top_gene_categories,\n"
        "     [lt IN apoc.coll.toSet([row IN rows | row.locus_tag]) |\n"
        "        {locus_tag: lt,\n"
        "         gene_name: head("
        "[row IN rows WHERE row.locus_tag = lt | row.gene_name]),\n"
        "         transport_substrate_resolution: head("
        "[row IN rows WHERE row.locus_tag = lt"
        " | row.transport_substrate_resolution]),\n"
        "         tcdb_evidence_score_max: head("
        "[row IN rows WHERE row.locus_tag = lt"
        " | row.tcdb_evidence_score_max]),\n"
        "         reaction_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.locus_tag = lt AND row.reaction_id"
        " IS NOT NULL | row.reaction_id])),\n"
        "         transporter_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.locus_tag = lt AND row.tcdb_family_id"
        " IS NOT NULL | row.tcdb_family_id])),\n"
        "         metabolite_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.locus_tag = lt | row.metabolite_id])),\n"
        "         metabolism_rows: size("
        "[row IN rows WHERE row.locus_tag = lt"
        " AND row.es = 'metabolism']),\n"
        "         transport_most_specific_rows: size("
        "[row IN rows WHERE row.locus_tag = lt"
        " AND row.substrate_depth = 'most_specific']),\n"
        "         transport_inherited_rows: size("
        "[row IN rows WHERE row.locus_tag = lt"
        " AND row.substrate_depth = 'inherited'])}] AS top_genes\n"
        "RETURN total_matching, gene_count_total, reaction_count_total,\n"
        "       transporter_count_total, metabolite_count_total,\n"
        "       rows_by_evidence_source, rows_by_substrate_depth,\n"
        "       by_metabolite, top_reactions, top_tcdb_families,\n"
        "       top_gene_categories, top_genes"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# metabolites_by_gene (MBG) — Tool 3 of the chemistry slice-1 symmetric set.
#
# Mirrors genes_by_metabolite (GBM) with these MBG-specific differences:
#   - anchor flips to locus_tags + organism (single-organism enforced)
#   - new metabolite_elements filter (uniform across both arms)
#   - per-arm filter scope identical to GBM (ec_numbers / mass_balance →
#     metabolism only; substrate_depth → transport only;
#     metabolite_pathway_ids / gene_categories / metabolite_ids /
#     metabolite_elements → uniform)
#   - sort uses **global precision-tier** (metabolism → most_specific →
#     inherited; tcdb_evidence_score desc within a transport tier) then
#     input-gene order via
#     apoc.coll.indexOf($locus_tags, locus_tag), then locus_tag, then
#     metabolite_id
#   - summary builder gains two new envelope keys: by_element +
#     top_metabolite_pathways
#
# Spec: docs/tool-specs/metabolites_by_gene.md
# ---------------------------------------------------------------------------


def _metabolites_by_gene_metabolism_where(
    *,
    locus_tags: list[str],
    organism: str,
    metabolite_elements: list[str] | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    ec_numbers: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    mass_balance: str | None = None,
    gene_categories: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params for the MBG metabolism arm.

    `substrate_depth` is not accepted here — it is a transport-arm
    filter and the metabolism arm is unaffected by it (per-arm filter
    scope rule).
    """
    conditions: list[str] = [
        "g.locus_tag IN $locus_tags",
        "ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_name) CONTAINS word)",
    ]
    params: dict = {
        "locus_tags": locus_tags,
        "organism": organism,
    }
    if metabolite_ids:
        conditions.append("m.id IN $metabolite_ids")
        params["metabolite_ids"] = metabolite_ids
    if exclude_metabolite_ids:
        conditions.append("(NOT (m.id IN $exclude_metabolite_ids))")
        params["exclude_metabolite_ids"] = exclude_metabolite_ids
    if metabolite_elements:
        conditions.append(
            "ALL(elem IN $metabolite_elements "
            "WHERE elem IN coalesce(m.elements, []))"
        )
        params["metabolite_elements"] = metabolite_elements
    if ec_numbers:
        conditions.append(
            "ANY(ec IN $ec_numbers WHERE ec IN coalesce(r.ec_numbers, []))"
        )
        params["ec_numbers"] = ec_numbers
    if mass_balance is not None:
        conditions.append("r.mass_balance = $mass_balance")
        params["mass_balance"] = mass_balance
    if metabolite_pathway_ids:
        conditions.append(
            "ANY(p IN $metabolite_pathway_ids "
            "WHERE p IN coalesce(m.pathway_ids, []))"
        )
        params["metabolite_pathway_ids"] = metabolite_pathway_ids
    if gene_categories:
        conditions.append("g.gene_category IN $gene_categories")
        params["gene_categories"] = gene_categories
    return conditions, params


def _metabolites_by_gene_transport_where(
    *,
    locus_tags: list[str],
    organism: str,
    metabolite_elements: list[str] | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
    substrate_depth: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params for the MBG transport arm.

    Always carries the deepest-attachment predicate (decision 4) so the
    arm walks only the gene's deepest TCDB attachments.

    `ec_numbers` / `mass_balance` are not accepted here — they are
    metabolism-arm filters and the transport arm is unaffected by them.
    `substrate_depth` (list of 'most_specific' / 'inherited') adds
    `r.substrate_depth IN $substrate_depth` on the transport edge.
    """
    conditions: list[str] = [
        "g.locus_tag IN $locus_tags",
        "ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_name) CONTAINS word)",
        TCDB_DEEPEST_ATTACHMENT_PREDICATE,
    ]
    params: dict = {
        "locus_tags": locus_tags,
        "organism": organism,
    }
    if metabolite_ids:
        conditions.append("m.id IN $metabolite_ids")
        params["metabolite_ids"] = metabolite_ids
    if exclude_metabolite_ids:
        conditions.append("(NOT (m.id IN $exclude_metabolite_ids))")
        params["exclude_metabolite_ids"] = exclude_metabolite_ids
    if metabolite_elements:
        conditions.append(
            "ALL(elem IN $metabolite_elements "
            "WHERE elem IN coalesce(m.elements, []))"
        )
        params["metabolite_elements"] = metabolite_elements
    if metabolite_pathway_ids:
        conditions.append(
            "ANY(p IN $metabolite_pathway_ids "
            "WHERE p IN coalesce(m.pathway_ids, []))"
        )
        params["metabolite_pathway_ids"] = metabolite_pathway_ids
    if gene_categories:
        conditions.append("g.gene_category IN $gene_categories")
        params["gene_categories"] = gene_categories
    if substrate_depth:
        conditions.append("r.substrate_depth IN $substrate_depth")
        params["substrate_depth"] = substrate_depth
    return conditions, params


def build_metabolites_by_gene_metabolism(
    *,
    locus_tags: list[str],
    organism: str,
    metabolite_elements: list[str] | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    ec_numbers: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    mass_balance: str | None = None,
    gene_categories: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for the metabolism arm of metabolites_by_gene.

    RETURN keys (compact, 16 columns aligned with the transport arm):
    locus_tag, gene_name, product, evidence_source ('metabolism'),
    substrate_depth (always null), tcdb_evidence_score (always null),
    reaction_id, reaction_name,
    ec_numbers, mass_balance, tcdb_family_id (null), tcdb_family_name
    (null), metabolite_id, metabolite_name, metabolite_formula,
    metabolite_mass, metabolite_chebi_id.

    Verbose adds: gene_category, metabolite_inchikey, metabolite_smiles,
    metabolite_mnxm_id, metabolite_hmdb_id, reaction_mnxr_id,
    reaction_rhea_ids, tcdb_level_kind (null), tc_class_id (null).

    `substrate_depth` is not accepted (per-arm filter scope rule);
    passing it raises `TypeError`.

    Sort: precision_tier (constant 0 for metabolism), then input-gene
    order via apoc.coll.indexOf($locus_tags, locus_tag), then locus_tag,
    then metabolite_id. Surfaces metabolism rows first when api/
    layer concatenates per-arm results into a globally sorted slice.
    """
    conditions, params = _metabolites_by_gene_metabolism_where(
        locus_tags=locus_tags,
        organism=organism,
        metabolite_elements=metabolite_elements,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids,
        ec_numbers=ec_numbers,
        metabolite_pathway_ids=metabolite_pathway_ids,
        mass_balance=mass_balance,
        gene_categories=gene_categories,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = (
        ",\n       g.gene_category AS gene_category"
        ",\n       m.inchikey AS metabolite_inchikey"
        ",\n       m.smiles AS metabolite_smiles"
        ",\n       m.mnxm_id AS metabolite_mnxm_id"
        ",\n       m.hmdb_id AS metabolite_hmdb_id"
        ",\n       r.mnxr_id AS reaction_mnxr_id"
        ",\n       r.rhea_ids AS reaction_rhea_ids"
        ",\n       null AS tcdb_level_kind"
        ",\n       null AS tc_class_id"
        if verbose else ""
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "MATCH (g:Gene)-[:Gene_catalyzes_reaction]->"
        "(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       'metabolism' AS evidence_source,\n"
        "       null AS substrate_depth,\n"
        "       null AS tcdb_evidence_score,\n"
        "       null AS transport_substrate_resolution,\n"
        "       r.id AS reaction_id,\n"
        "       r.name AS reaction_name,\n"
        "       coalesce(r.ec_numbers, []) AS ec_numbers,\n"
        "       r.mass_balance AS mass_balance,\n"
        "       null AS tcdb_family_id,\n"
        "       null AS tcdb_family_name,\n"
        "       m.id AS metabolite_id,\n"
        "       m.name AS metabolite_name,\n"
        "       m.formula AS metabolite_formula,\n"
        "       m.mass AS metabolite_mass,\n"
        "       m.chebi_id AS metabolite_chebi_id"
        f"{verbose_cols}\n"
        "ORDER BY 0,"
        " apoc.coll.indexOf($locus_tags, locus_tag),"
        " locus_tag, metabolite_id"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_metabolites_by_gene_transport(
    *,
    locus_tags: list[str],
    organism: str,
    metabolite_elements: list[str] | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    gene_categories: list[str] | None = None,
    substrate_depth: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for the transport arm of metabolites_by_gene.

    Walks deepest TCDB attachments only (decision 4 predicate), so the
    distinct metabolites across rows equal the gene's precomputed
    `transported_metabolite_count`.

    RETURN keys (compact): locus_tag, gene_name, product,
    evidence_source ('transport'), substrate_depth (edge
    `r.substrate_depth`: 'most_specific' | 'inherited'),
    tcdb_evidence_score (edge `gt.evidence_score`, float [0,1]),
    reaction_id (null), reaction_name (null),
    ec_numbers (null), mass_balance (null), tcdb_family_id,
    tcdb_family_name, metabolite_id, metabolite_name,
    metabolite_formula, metabolite_mass, metabolite_chebi_id.

    Verbose adds: gene_category, metabolite_inchikey, metabolite_smiles,
    metabolite_mnxm_id, metabolite_hmdb_id, reaction_mnxr_id (null),
    reaction_rhea_ids (null), tcdb_level_kind, tc_class_id.

    `ec_numbers` / `mass_balance` are not accepted (per-arm filter
    scope rule); passing them raises `TypeError`.

    Sort: depth tier (most_specific = 0, inherited = 1) via CASE on
    r.substrate_depth, then tcdb_evidence_score DESC within the tier,
    then input-gene order via apoc.coll.indexOf($locus_tags, locus_tag),
    then locus_tag, then metabolite_id.
    """
    conditions, params = _metabolites_by_gene_transport_where(
        locus_tags=locus_tags,
        organism=organism,
        metabolite_elements=metabolite_elements,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids,
        metabolite_pathway_ids=metabolite_pathway_ids,
        gene_categories=gene_categories,
        substrate_depth=substrate_depth,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = (
        ",\n       g.gene_category AS gene_category"
        ",\n       m.inchikey AS metabolite_inchikey"
        ",\n       m.smiles AS metabolite_smiles"
        ",\n       m.mnxm_id AS metabolite_mnxm_id"
        ",\n       m.hmdb_id AS metabolite_hmdb_id"
        ",\n       null AS reaction_mnxr_id"
        ",\n       null AS reaction_rhea_ids"
        ",\n       tf.level_kind AS tcdb_level_kind"
        ",\n       tf.tc_class_id AS tc_class_id"
        if verbose else ""
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "MATCH (g:Gene)-[gt:Gene_has_tcdb_family]->"
        "(tf:TcdbFamily)-[r:Tcdb_family_transports_metabolite]->(m:Metabolite)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       'transport' AS evidence_source,\n"
        "       r.substrate_depth AS substrate_depth,\n"
        "       gt.evidence_score AS tcdb_evidence_score,\n"
        "       g.transport_substrate_resolution AS transport_substrate_resolution,\n"
        "       null AS reaction_id,\n"
        "       null AS reaction_name,\n"
        "       null AS ec_numbers,\n"
        "       null AS mass_balance,\n"
        "       tf.id AS tcdb_family_id,\n"
        "       tf.name AS tcdb_family_name,\n"
        "       m.id AS metabolite_id,\n"
        "       m.name AS metabolite_name,\n"
        "       m.formula AS metabolite_formula,\n"
        "       m.mass AS metabolite_mass,\n"
        "       m.chebi_id AS metabolite_chebi_id"
        f"{verbose_cols}\n"
        "ORDER BY"
        " CASE WHEN r.substrate_depth = 'most_specific' THEN 0 ELSE 1 END,"
        " tcdb_evidence_score DESC,"
        " apoc.coll.indexOf($locus_tags, locus_tag),"
        " locus_tag, metabolite_id"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_metabolites_by_gene_summary(
    *,
    locus_tags: list[str],
    organism: str,
    metabolite_elements: list[str] | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    ec_numbers: list[str] | None = None,
    metabolite_pathway_ids: list[str] | None = None,
    mass_balance: str | None = None,
    gene_categories: list[str] | None = None,
    substrate_depth: list[str] | None = None,
    arms: tuple[str, ...] = ("metabolism", "transport"),
) -> tuple[str, dict]:
    """Build single-pass aggregation Cypher for metabolites_by_gene.

    Per-arm filter scope (matches detail builders): `ec_numbers` and
    `mass_balance` apply only to the metabolism arm of the UNION;
    `substrate_depth` applies only to the transport arm (which always
    walks deepest TCDB attachments only — decision 4);
    `metabolite_pathway_ids`, `gene_categories`, `metabolite_ids`, and
    `metabolite_elements` apply to both arms uniformly.

    `arms` selects which arm bodies are emitted in the inner CALL{...}
    subquery. When only one arm is selected, the other's MATCH path is
    omitted entirely (cheap api/-side `evidence_sources` skip).

    RETURN keys: total_matching, gene_count_total, reaction_count_total,
    transporter_count_total, metabolite_count_total,
    rows_by_evidence_source (long-format list of {evidence_source, count}),
    rows_by_substrate_depth (long-format list of {substrate_depth, count},
       transport rows only),
    by_gene (per-input-gene rollup with metabolism_rows /
       transport_most_specific_rows / transport_inherited_rows, plus the
       gene-level transport_substrate_resolution + tcdb_evidence_score_max
       — null on metabolism-only genes — which drive the gene-anchored
       auto-warning),
    top_metabolites, top_reactions, top_tcdb_families,
    top_gene_categories, top_metabolite_pathways (NEW — chemistry-filtered
    to p.reaction_count >= 3), by_element (NEW — periodic-table-bounded
    rollup over m.elements).

    The api/ layer post-processes some apoc.coll outputs into the
    documented top-N shape; the contract here is the RETURN keys and
    their semantics.
    """
    params: dict = {
        "locus_tags": locus_tags,
        "organism": organism,
    }

    arm_blocks: list[str] = []

    if "metabolism" in arms:
        m_conditions, m_params = _metabolites_by_gene_metabolism_where(
            locus_tags=locus_tags,
            organism=organism,
            metabolite_elements=metabolite_elements,
            metabolite_ids=metabolite_ids,
            exclude_metabolite_ids=exclude_metabolite_ids,
            ec_numbers=ec_numbers,
            metabolite_pathway_ids=metabolite_pathway_ids,
            mass_balance=mass_balance,
            gene_categories=gene_categories,
        )
        params.update(m_params)
        m_where = "  WHERE " + " AND ".join(m_conditions) + "\n"
        arm_blocks.append(
            "  MATCH (g:Gene)-[:Gene_catalyzes_reaction]->"
            "(r:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)\n"
            f"{m_where}"
            "  RETURN g, r, null AS tf, m, 'metabolism' AS es,"
            " null AS sdepth, null AS tscore"
        )

    if "transport" in arms:
        t_conditions, t_params = _metabolites_by_gene_transport_where(
            locus_tags=locus_tags,
            organism=organism,
            metabolite_elements=metabolite_elements,
            metabolite_ids=metabolite_ids,
            exclude_metabolite_ids=exclude_metabolite_ids,
            metabolite_pathway_ids=metabolite_pathway_ids,
            gene_categories=gene_categories,
            substrate_depth=substrate_depth,
        )
        params.update(t_params)
        t_where = "  WHERE " + " AND ".join(t_conditions) + "\n"
        arm_blocks.append(
            "  MATCH (g:Gene)-[gt:Gene_has_tcdb_family]->"
            "(tf:TcdbFamily)-[r:Tcdb_family_transports_metabolite]->(m:Metabolite)\n"
            f"{t_where}"
            "  RETURN g, null AS r, tf, m, 'transport' AS es,\n"
            "         r.substrate_depth AS sdepth,"
            " gt.evidence_score AS tscore"
        )

    union_body = "\n  UNION\n".join(arm_blocks)

    cypher = (
        "CALL {\n"
        f"{union_body}\n"
        "}\n"
        "WITH g, r, tf, m, es, sdepth, tscore\n"
        "WITH count(*) AS total_matching,\n"
        "     count(DISTINCT g) AS gene_count_total,\n"
        "     count(DISTINCT r) AS reaction_count_total,\n"
        "     count(DISTINCT tf) AS transporter_count_total,\n"
        "     count(DISTINCT m) AS metabolite_count_total,\n"
        "     collect({\n"
        "       locus_tag: g.locus_tag,\n"
        "       gene_name: g.gene_name,\n"
        "       product: g.product,\n"
        "       gene_category: g.gene_category,\n"
        "       transport_substrate_resolution: g.transport_substrate_resolution,\n"
        "       tcdb_evidence_score_max: g.tcdb_evidence_score_max,\n"
        "       reaction_id: r.id,\n"
        "       reaction_name: r.name,\n"
        "       reaction_ec_numbers: coalesce(r.ec_numbers, []),\n"
        "       tcdb_family_id: tf.id,\n"
        "       tcdb_family_name: tf.name,\n"
        "       tcdb_family_level_kind: tf.level_kind,\n"
        "       metabolite_id: m.id,\n"
        "       metabolite_name: m.name,\n"
        "       metabolite_formula: m.formula,\n"
        "       metabolite_elements: coalesce(m.elements, []),\n"
        "       metabolite_pathway_ids: coalesce(m.pathway_ids, []),\n"
        "       es: es,\n"
        "       substrate_depth: sdepth,\n"
        "       tcdb_evidence_score: tscore\n"
        "     }) AS rows\n"
        "WITH total_matching, gene_count_total, reaction_count_total,\n"
        "     transporter_count_total, metabolite_count_total, rows,\n"
        "     [es IN apoc.coll.toSet([row IN rows | row.es]) |\n"
        "        {evidence_source: es,\n"
        "         count: size([row IN rows WHERE row.es = es])}]"
        " AS rows_by_evidence_source,\n"
        "     [sd IN apoc.coll.toSet("
        "[row IN rows WHERE row.substrate_depth IS NOT NULL"
        " | row.substrate_depth]) |\n"
        "        {substrate_depth: sd,\n"
        "         count: size([row IN rows WHERE row.substrate_depth = sd])}]"
        " AS rows_by_substrate_depth\n"
        "// Per-input-gene rollup (the gene-anchored mirror of GBM by_metabolite)\n"
        "WITH total_matching, gene_count_total, reaction_count_total,\n"
        "     transporter_count_total, metabolite_count_total, rows,\n"
        "     rows_by_evidence_source, rows_by_substrate_depth,\n"
        "     [lt IN apoc.coll.toSet([row IN rows | row.locus_tag]) |\n"
        "        {locus_tag: lt,\n"
        "         gene_name: head([row IN rows WHERE row.locus_tag = lt"
        " | row.gene_name]),\n"
        "         product: head([row IN rows WHERE row.locus_tag = lt"
        " | row.product]),\n"
        "         transport_substrate_resolution: head("
        "[row IN rows WHERE row.locus_tag = lt"
        " | row.transport_substrate_resolution]),\n"
        "         tcdb_evidence_score_max: head("
        "[row IN rows WHERE row.locus_tag = lt"
        " | row.tcdb_evidence_score_max]),\n"
        "         rows: size([row IN rows WHERE row.locus_tag = lt]),\n"
        "         metabolite_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.locus_tag = lt | row.metabolite_id])),\n"
        "         reaction_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.locus_tag = lt AND row.reaction_id"
        " IS NOT NULL | row.reaction_id])),\n"
        "         transporter_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.locus_tag = lt AND row.tcdb_family_id"
        " IS NOT NULL | row.tcdb_family_id])),\n"
        "         metabolism_rows: size("
        "[row IN rows WHERE row.locus_tag = lt"
        " AND row.es = 'metabolism']),\n"
        "         transport_most_specific_rows: size("
        "[row IN rows WHERE row.locus_tag = lt"
        " AND row.substrate_depth = 'most_specific']),\n"
        "         transport_inherited_rows: size("
        "[row IN rows WHERE row.locus_tag = lt"
        " AND row.substrate_depth = 'inherited'])}] AS by_gene\n"
        "// Top-N rollups: api/ layer trims to top 10 by gene_count\n"
        "WITH total_matching, gene_count_total, reaction_count_total,\n"
        "     transporter_count_total, metabolite_count_total,\n"
        "     rows_by_evidence_source, rows_by_substrate_depth,\n"
        "     by_gene, rows,\n"
        "     [rid IN apoc.coll.toSet("
        "[row IN rows WHERE row.reaction_id IS NOT NULL | row.reaction_id]) |\n"
        "        {reaction_id: rid,\n"
        "         name: head("
        "[row IN rows WHERE row.reaction_id = rid | row.reaction_name]),\n"
        "         ec_numbers: head("
        "[row IN rows WHERE row.reaction_id = rid"
        " | row.reaction_ec_numbers]),\n"
        "         gene_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.reaction_id = rid | row.locus_tag])),\n"
        "         metabolite_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.reaction_id = rid"
        " | row.metabolite_id]))}] AS top_reactions,\n"
        "     [tfid IN apoc.coll.toSet("
        "[row IN rows WHERE row.tcdb_family_id IS NOT NULL"
        " | row.tcdb_family_id]) |\n"
        "        {tcdb_family_id: tfid,\n"
        "         tcdb_family_name: head("
        "[row IN rows WHERE row.tcdb_family_id = tfid"
        " | row.tcdb_family_name]),\n"
        "         level_kind: head("
        "[row IN rows WHERE row.tcdb_family_id = tfid"
        " | row.tcdb_family_level_kind]),\n"
        "         substrate_depth: CASE WHEN 'most_specific' IN "
        "[row IN rows WHERE row.tcdb_family_id = tfid"
        " | row.substrate_depth]"
        " THEN 'most_specific' ELSE 'inherited' END,\n"
        "         gene_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.tcdb_family_id = tfid | row.locus_tag])),\n"
        "         metabolite_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.tcdb_family_id = tfid"
        " | row.metabolite_id]))}]"
        " AS top_tcdb_families,\n"
        "     [cat IN apoc.coll.toSet("
        "[row IN rows WHERE row.gene_category IS NOT NULL"
        " | row.gene_category]) |\n"
        "        {category: cat,\n"
        "         gene_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.gene_category = cat | row.locus_tag]))}]"
        " AS top_gene_categories,\n"
        "     [mid IN apoc.coll.toSet([row IN rows | row.metabolite_id]) |\n"
        "        {metabolite_id: mid,\n"
        "         name: head([row IN rows WHERE row.metabolite_id = mid"
        " | row.metabolite_name]),\n"
        "         formula: head([row IN rows WHERE row.metabolite_id = mid"
        " | row.metabolite_formula]),\n"
        "         gene_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.metabolite_id = mid | row.locus_tag])),\n"
        "         reaction_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.metabolite_id = mid AND row.reaction_id"
        " IS NOT NULL | row.reaction_id])),\n"
        "         transporter_count: size(apoc.coll.toSet("
        "[row IN rows WHERE row.metabolite_id = mid AND row.tcdb_family_id"
        " IS NOT NULL | row.tcdb_family_id])),\n"
        "         metabolism_rows: size("
        "[row IN rows WHERE row.metabolite_id = mid"
        " AND row.es = 'metabolism']),\n"
        "         transport_most_specific_rows: size("
        "[row IN rows WHERE row.metabolite_id = mid"
        " AND row.substrate_depth = 'most_specific']),\n"
        "         transport_inherited_rows: size("
        "[row IN rows WHERE row.metabolite_id = mid"
        " AND row.substrate_depth = 'inherited'])}]"
        " AS top_metabolites\n"
        "// by_element rollup: distinct metabolites that carry each element.\n"
        "// Uses m.elements (KG-A3 Hill-parsed presence list); empty\n"
        "// formulas (~31 metabolites) gracefully drop out.\n"
        "WITH total_matching, gene_count_total, reaction_count_total,\n"
        "     transporter_count_total, metabolite_count_total,\n"
        "     rows_by_evidence_source, rows_by_substrate_depth,\n"
        "     by_gene, top_reactions, top_tcdb_families,\n"
        "     top_gene_categories, top_metabolites, rows,\n"
        "     apoc.coll.toSet([row IN rows | row.metabolite_id])"
        " AS distinct_mids,\n"
        "     [elem IN apoc.coll.toSet("
        "apoc.coll.flatten("
        "[row IN rows | row.metabolite_elements])) |\n"
        "        {element: elem,\n"
        "         metabolite_count: size(apoc.coll.toSet("
        "[row IN rows WHERE elem IN row.metabolite_elements"
        " | row.metabolite_id]))}] AS by_element\n"
        "// top_metabolite_pathways rollup: metabolite-side KEGG pathways\n"
        "// the gene set reaches, filtered to chemistry pathways\n"
        "// (p.reaction_count >= 3) to drop signaling/disease pathways with\n"
        "// no chemistry breadth. Pathway IDs sourced from m.pathway_ids\n"
        "// (KG-A5 denorm, transport-extended), so coverage is uniform\n"
        "// across both arms.\n"
        "WITH total_matching, gene_count_total, reaction_count_total,\n"
        "     transporter_count_total, metabolite_count_total,\n"
        "     rows_by_evidence_source, rows_by_substrate_depth,\n"
        "     by_gene, top_reactions, top_tcdb_families,\n"
        "     top_gene_categories, top_metabolites, by_element, rows,\n"
        "     apoc.coll.toSet("
        "apoc.coll.flatten("
        "[row IN rows | row.metabolite_pathway_ids])) AS distinct_pids\n"
        "CALL {\n"
        "  WITH rows, distinct_pids\n"
        "  UNWIND distinct_pids AS pid\n"
        "  MATCH (p:KeggTerm {id: pid})\n"
        "  WHERE p.reaction_count >= 3\n"
        "  RETURN collect({\n"
        "    metabolite_pathway_id: p.id,\n"
        "    metabolite_pathway_name: p.name,\n"
        "    gene_count: size(apoc.coll.toSet("
        "[row IN rows WHERE p.id IN row.metabolite_pathway_ids"
        " | row.locus_tag])),\n"
        "    pathway_reaction_count: p.reaction_count,\n"
        "    pathway_metabolite_count: p.metabolite_count\n"
        "  }) AS top_metabolite_pathways\n"
        "}\n"
        "RETURN total_matching, gene_count_total, reaction_count_total,\n"
        "       transporter_count_total, metabolite_count_total,\n"
        "       rows_by_evidence_source, rows_by_substrate_depth,\n"
        "       by_gene, top_reactions, top_tcdb_families,\n"
        "       top_gene_categories, top_metabolites, by_element,\n"
        "       top_metabolite_pathways"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# list_metabolite_assays — Phase 5 greenfield assay-discovery surface
# ---------------------------------------------------------------------------

def _list_metabolite_assays_where(
    *,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
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
) -> tuple[list[str], dict]:
    """Shared WHERE-clause builder for build_list_metabolite_assays{,_summary}.

    Mirrors `_list_derived_metrics_where` but on `a:MetaboliteAssay` instead of
    `dm:DerivedMetric`. Adds two Phase-5-specific filters that DM lacks:
    - `metabolite_ids` / `exclude_metabolite_ids` — EXISTS / NOT EXISTS clauses
      traversing `Assay_quantifies_metabolite | Assay_flags_metabolite` to find
      assays that measure (or skip) specific compounds.

    Returns:
        (conditions, params): list of WHERE-clause snippets joined by AND in
        the caller, plus the parameters dict.
    """
    conditions: list[str] = []
    params: dict = {}

    if organism is not None:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ') "
            "WHERE toLower(a.organism_name) CONTAINS word)"
        )
        params["organism"] = organism
    if metric_types:
        conditions.append("a.metric_type IN $metric_types")
        params["metric_types"] = metric_types
    if value_kind is not None:
        conditions.append("a.value_kind = $value_kind")
        params["value_kind"] = value_kind
    if compartment is not None:
        conditions.append("a.compartment = $compartment")
        params["compartment"] = compartment
    if treatment_type:
        conditions.append(
            "ANY(t IN coalesce(a.treatment_type, []) "
            "WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]
    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(a.background_factors, []) "
            "WHERE toLower(bf) IN $background_factors_lower)"
        )
        params["background_factors_lower"] = [bf.lower() for bf in background_factors]
    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(a.growth_phases, []) "
            "WHERE toLower(gp) IN $growth_phases_lower)"
        )
        params["growth_phases_lower"] = [gp.lower() for gp in growth_phases]
    if publication_doi:
        conditions.append("a.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi
    if experiment_ids:
        conditions.append("a.experiment_id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    if assay_ids:
        conditions.append("a.id IN $assay_ids")
        params["assay_ids"] = assay_ids
    if metabolite_ids:
        conditions.append(
            "EXISTS { MATCH (a)-[:Assay_quantifies_metabolite|Assay_flags_metabolite]"
            "->(m:Metabolite) WHERE m.id IN $metabolite_ids }"
        )
        params["metabolite_ids"] = metabolite_ids
    if exclude_metabolite_ids:
        conditions.append(
            "NOT EXISTS { MATCH (a)-[:Assay_quantifies_metabolite|Assay_flags_metabolite]"
            "->(m:Metabolite) WHERE m.id IN $exclude_metabolite_ids }"
        )
        params["exclude_metabolite_ids"] = exclude_metabolite_ids
    if rankable is not None:
        conditions.append("a.rankable = $rankable_str")
        params["rankable_str"] = two_state("rankable", rankable)

    return conditions, params


def build_list_metabolite_assays_summary(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
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
) -> tuple[str, dict]:
    """Build summary Cypher for list_metabolite_assays.

    RETURN keys:
      total_entries, total_matching, metabolite_count_total,
      by_organism, by_value_kind, by_compartment, top_metric_types,
      by_treatment_type, by_background_factors, by_growth_phase,
      by_detection_status.
    When `search_text` is set, also returns: score_max, score_median.
    """
    conditions, params = _list_metabolite_assays_where(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, treatment_type=treatment_type,
        background_factors=background_factors, growth_phases=growth_phases,
        publication_doi=publication_doi, experiment_ids=experiment_ids,
        assay_ids=assay_ids, metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids, rankable=rankable,
    )

    if search_text is not None:
        match_block = (
            "CALL db.index.fulltext.queryNodes('metaboliteAssayFullText', $search_text) "
            "YIELD node AS a, score\n"
        )
        params["search_text"] = search_text
        score_carry = ", score"
        score_extras = (
            ",\n     max(score) AS score_max,\n"
            "     percentileDisc(score, 0.5) AS score_median"
        )
        score_return = ",\n       score_max,\n       score_median"
    else:
        match_block = "MATCH (a:MetaboliteAssay)\n"
        score_carry = ""
        score_extras = ""
        score_return = ""

    where_block = (
        "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
    )

    cypher = (
        "CALL { MATCH (all_a:MetaboliteAssay) RETURN count(all_a) AS total_entries }\n"
        f"{match_block}"
        f"{where_block}"
        "OPTIONAL MATCH (a)-[r:Assay_quantifies_metabolite]->(:Metabolite)\n"
        "WITH total_entries, a, [s IN collect(r.detection_status) WHERE s IS NOT NULL] AS det"
        f"{score_carry}\n"
        "WITH total_entries,\n"
        "     collect(a.organism_name) AS orgs,\n"
        "     collect(a.value_kind) AS vks,\n"
        "     collect(a.compartment) AS comps,\n"
        "     collect(a.metric_type) AS mts,\n"
        "     apoc.coll.flatten(collect(coalesce(a.treatment_type, []))) AS tts,\n"
        "     apoc.coll.flatten(collect(coalesce(a.background_factors, []))) AS bfs,\n"
        "     apoc.coll.flatten(collect(coalesce(a.growth_phases, []))) AS gps,\n"
        "     apoc.coll.flatten(collect(det)) AS all_det,\n"
        "     count(a) AS total_matching,\n"
        "     sum(a.total_metabolite_count) AS metabolite_count_total"
        f"{score_extras}\n"
        "RETURN total_entries, total_matching, metabolite_count_total,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(vks) AS by_value_kind,\n"
        "       apoc.coll.frequencies(comps) AS by_compartment,\n"
        "       apoc.coll.frequencies(mts) AS top_metric_types,\n"
        "       apoc.coll.frequencies(tts) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(bfs) AS by_background_factors,\n"
        "       apoc.coll.frequencies(gps) AS by_growth_phase,\n"
        "       apoc.coll.frequencies(all_det) AS by_detection_status"
        f"{score_return}"
    )
    return cypher, params


def build_list_metabolite_assays(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
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
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for list_metabolite_assays.

    RETURN keys (compact):
      assay_id, name, metric_type, value_kind, rankable, unit,
      field_description, organism_name, experiment_id, publication_doi,
      compartment, omics_type, treatment_type, background_factors,
      growth_phases, total_metabolite_count, aggregation_method,
      preferred_id, value_min, value_q1, value_median, value_q3, value_max,
      timepoints, detection_status_counts.
    When `search_text` set: + `score`.
    Verbose adds: treatment, light_condition, experimental_context.
    """
    conditions, params = _list_metabolite_assays_where(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, treatment_type=treatment_type,
        background_factors=background_factors, growth_phases=growth_phases,
        publication_doi=publication_doi, experiment_ids=experiment_ids,
        assay_ids=assay_ids, metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids, rankable=rankable,
    )

    if search_text is not None:
        match_block = (
            "CALL db.index.fulltext.queryNodes('metaboliteAssayFullText', $search_text) "
            "YIELD node AS a, score\n"
        )
        params["search_text"] = search_text
        score_col = ",\n       score AS score"
        order_by = (
            "ORDER BY score DESC, a.organism_name ASC, a.value_kind ASC, a.id ASC"
        )
    else:
        match_block = "MATCH (a:MetaboliteAssay)\n"
        score_col = ""
        order_by = "ORDER BY a.organism_name ASC, a.value_kind ASC, a.id ASC"

    where_block = (
        "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
    )

    if verbose:
        verbose_cols = (
            ",\n       a.treatment AS treatment,\n"
            "       a.light_condition AS light_condition,\n"
            "       a.experimental_context AS experimental_context"
        )
    else:
        verbose_cols = ""

    pagination = ""
    if limit is not None:
        params["limit"] = limit
        params["offset"] = offset
        pagination = "\nSKIP $offset\nLIMIT $limit"

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "OPTIONAL MATCH (a)-[r:Assay_quantifies_metabolite]->(:Metabolite)\n"
        "WITH a, "
        "[label IN collect(DISTINCT r.time_point) "
        "WHERE label IS NOT NULL AND label <> \"\" | label] AS timepoints,\n"
        "     [s IN collect(r.detection_status) WHERE s IS NOT NULL] AS detection_statuses"
        + (",\n     score" if search_text is not None else "")
        + "\n"
        "WITH a, timepoints,\n"
        "     CASE WHEN size(detection_statuses) = 0 THEN [] "
        "ELSE [x IN apoc.coll.frequencies(detection_statuses) "
        "| {detection_status: x.item, count: x.count}] END AS detection_status_counts"
        + (",\n     score" if search_text is not None else "")
        + "\n"
        "RETURN\n"
        "       a.id AS assay_id,\n"
        "       a.name AS name,\n"
        "       a.metric_type AS metric_type,\n"
        "       a.value_kind AS value_kind,\n"
        "       (a.rankable = \"rankable\") AS rankable,\n"
        "       a.unit AS unit,\n"
        "       a.field_description AS field_description,\n"
        "       a.organism_name AS organism_name,\n"
        "       a.experiment_id AS experiment_id,\n"
        "       a.publication_doi AS publication_doi,\n"
        "       a.compartment AS compartment,\n"
        "       a.omics_type AS omics_type,\n"
        "       coalesce(a.treatment_type, []) AS treatment_type,\n"
        "       coalesce(a.background_factors, []) AS background_factors,\n"
        "       coalesce(a.growth_phases, []) AS growth_phases,\n"
        "       a.total_metabolite_count AS total_metabolite_count,\n"
        "       a.aggregation_method AS aggregation_method,\n"
        "       a.preferred_id AS preferred_id,\n"
        "       a.value_min AS value_min,\n"
        "       a.value_q1 AS value_q1,\n"
        "       a.value_median AS value_median,\n"
        "       a.value_q3 AS value_q3,\n"
        "       a.value_max AS value_max,\n"
        "       timepoints,\n"
        "       detection_status_counts"
        f"{score_col}{verbose_cols}\n"
        f"{order_by}"
        f"{pagination}"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Phase 5 metabolites-by-assay slice — 3 tools
# Tool 1: metabolites_by_quantifies_assay (numeric drill-down)
# Tool 2: metabolites_by_flags_assay (boolean drill-down)
# Tool 3: assays_by_metabolite (polymorphic reverse-lookup, UNION ALL)
# Source: parent §12.2 / §12.3 / §12.4 verbatim Cypher (verified live 2026-05-06).
# ---------------------------------------------------------------------------

def _metabolites_by_quantifies_assay_where(
    *,
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
) -> tuple[list[str], dict]:
    """Shared WHERE-conditions builder for metabolites_by_quantifies_assay.

    Mirrors `_list_derived_metrics_where` / `_list_metabolite_assays_where`
    style. Scoping params target `a:MetaboliteAssay` and `m:Metabolite`;
    edge filters target `r:Assay_quantifies_metabolite`.

    Per parent §11 Conv A, `exclude_metabolite_ids` uses set-difference
    semantics — exclude wins on overlap with `metabolite_ids`.

    Returns:
        (conditions, params): list of WHERE-clause snippets joined by AND in
        the caller, plus the parameters dict.
    """
    conditions: list[str] = []
    params: dict = {}

    if organism is not None:
        conditions.append("toLower(a.organism_name) CONTAINS $organism")
        params["organism"] = organism.lower()
    if metabolite_ids is not None:
        conditions.append("m.id IN $metabolite_ids")
        params["metabolite_ids"] = metabolite_ids
    if exclude_metabolite_ids is not None:
        conditions.append("NOT m.id IN $exclude_metabolite_ids")
        params["exclude_metabolite_ids"] = exclude_metabolite_ids
    if experiment_ids:
        conditions.append("a.experiment_id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    if publication_doi:
        conditions.append("a.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi
    if compartment is not None:
        conditions.append("a.compartment = $compartment")
        params["compartment"] = compartment
    if treatment_type:
        conditions.append(
            "ANY(t IN coalesce(a.treatment_type, []) "
            "WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]
    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(a.background_factors, []) "
            "WHERE toLower(bf) IN $background_factors_lower)"
        )
        params["background_factors_lower"] = [bf.lower() for bf in background_factors]
    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(a.growth_phases, []) "
            "WHERE toLower(gp) IN $growth_phases_lower)"
        )
        params["growth_phases_lower"] = [gp.lower() for gp in growth_phases]
    if value_min is not None:
        conditions.append("r.value >= $value_min")
        params["value_min"] = value_min
    if value_max is not None:
        conditions.append("r.value <= $value_max")
        params["value_max"] = value_max
    if detection_status:
        conditions.append("r.detection_status IN $detection_status")
        params["detection_status"] = detection_status
    if timepoint:
        conditions.append("r.time_point IN $timepoint")
        params["timepoint"] = timepoint
    if metric_bucket:
        conditions.append("r.metric_bucket IN $metric_bucket")
        params["metric_bucket"] = metric_bucket
    if metric_percentile_min is not None:
        conditions.append("r.metric_percentile >= $metric_percentile_min")
        params["metric_percentile_min"] = metric_percentile_min
    if metric_percentile_max is not None:
        conditions.append("r.metric_percentile <= $metric_percentile_max")
        params["metric_percentile_max"] = metric_percentile_max
    if rank_by_metric_max is not None:
        conditions.append("r.rank_by_metric <= $rank_by_metric_max")
        params["rank_by_metric_max"] = rank_by_metric_max

    return conditions, params


def build_metabolites_by_quantifies_assay_diagnostics(
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
) -> tuple[str, dict]:
    """Pre-flight rankable-gating probe for metabolites_by_quantifies_assay.

    Mirrors `build_genes_by_numeric_metric_diagnostics` (parent §13.1).
    api/ runs this BEFORE summary/detail to:
      1. Validate every selected assay has `value_kind='numeric'` (raise on
         mismatch).
      2. Compute `excluded_assays` for rankable-gated filters that don't
         apply to some/all selected assays.
      3. Echo full-assay value range into envelope `by_metric`.

    RETURN keys (one row per assay): assay_id, name, value_kind,
    rankable (bool, D4-coerced), organism_name, compartment,
    value_min, value_q1, value_median, value_q3, value_max.
    """
    # Reuse WHERE-helper for organism/metabolite/scoping conditions
    # (no edge filters — diagnostics is node-level only).
    conditions, params = _metabolites_by_quantifies_assay_where(
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
    params["assay_ids"] = assay_ids

    # Hardcoded predicate: this tool only drills numeric assays.
    extra = ["a.id IN $assay_ids", "a.value_kind = 'numeric'"]
    all_conditions = extra + conditions

    # If metabolite_ids / exclude_metabolite_ids in scope, we need an EXISTS
    # traversal on the quantifies relationship. Otherwise the assay-only
    # MATCH suffices.
    if metabolite_ids is not None or exclude_metabolite_ids is not None:
        # Replace m.id-based conditions with EXISTS-style traversals.
        # Easier: re-derive node-only conditions, then add EXISTS for metabolite scope.
        node_conditions = [c for c in all_conditions if "m.id" not in c]
        if metabolite_ids is not None:
            node_conditions.append(
                "EXISTS { MATCH (a)-[:Assay_quantifies_metabolite]->"
                "(m:Metabolite) WHERE m.id IN $metabolite_ids }"
            )
        if exclude_metabolite_ids is not None:
            node_conditions.append(
                "NOT EXISTS { MATCH (a)-[:Assay_quantifies_metabolite]->"
                "(m:Metabolite) WHERE m.id IN $exclude_metabolite_ids }"
            )
        all_conditions = node_conditions

    where_block = "WHERE " + " AND ".join(all_conditions) + "\n"

    cypher = (
        "MATCH (a:MetaboliteAssay)\n"
        f"{where_block}"
        "RETURN a.id AS assay_id,\n"
        "       a.name AS name,\n"
        "       a.value_kind AS value_kind,\n"
        "       (a.rankable = 'rankable') AS rankable,\n"
        "       a.organism_name AS organism_name,\n"
        "       a.compartment AS compartment,\n"
        "       a.value_min AS value_min,\n"
        "       a.value_q1 AS value_q1,\n"
        "       a.value_median AS value_median,\n"
        "       a.value_q3 AS value_q3,\n"
        "       a.value_max AS value_max\n"
        "ORDER BY a.id ASC"
    )
    return cypher, params


def build_metabolites_by_quantifies_assay_summary(
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
) -> tuple[str, dict]:
    """Build summary Cypher for metabolites_by_quantifies_assay (parent §12.2).

    RETURN keys: total_matching, by_detection_status (audit §4.3.3 primary
    headline), by_metric_bucket, by_assay, by_compartment, by_organism,
    filtered_value_min, filtered_value_max.

    `by_metric` envelope (per-assay precomputed-vs-filtered) is computed in
    api/ layer by enriching with diagnostics result.
    """
    conditions, params = _metabolites_by_quantifies_assay_where(
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
    params["assay_ids"] = assay_ids
    all_conditions = ["a.id IN $assay_ids"] + conditions
    where_block = "WHERE " + " AND ".join(all_conditions) + "\n"

    cypher = (
        "MATCH (a:MetaboliteAssay)-[r:Assay_quantifies_metabolite]->(m:Metabolite)\n"
        f"{where_block}"
        "WITH [s IN collect(r.detection_status) WHERE s IS NOT NULL] AS dets,\n"
        "     [b IN collect(r.metric_bucket) WHERE b IS NOT NULL] AS buckets,\n"
        "     collect(a.id) AS assay_ids_collected,\n"
        "     collect(a.compartment) AS comps,\n"
        "     collect(a.organism_name) AS orgs,\n"
        "     [v IN collect(r.value) WHERE v IS NOT NULL] AS vals,\n"
        "     count(*) AS total_matching\n"
        "RETURN total_matching,\n"
        "       apoc.coll.frequencies(dets) AS by_detection_status,\n"
        "       apoc.coll.frequencies(buckets) AS by_metric_bucket,\n"
        "       apoc.coll.frequencies(assay_ids_collected) AS by_assay,\n"
        "       apoc.coll.frequencies(comps) AS by_compartment,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.min(vals) AS filtered_value_min,\n"
        "       apoc.coll.max(vals) AS filtered_value_max"
    )
    return cypher, params


def build_metabolites_by_quantifies_assay(
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
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for metabolites_by_quantifies_assay (parent §12.2).

    Per-row schema (compact):
      metabolite_id, name, kegg_compound_id, value, value_sd, n_replicates,
      n_non_zero, metric_type, metric_bucket, metric_percentile,
      rank_by_metric, detection_status, timepoint, timepoint_hours,
      timepoint_order, growth_phase (KG-MET-017 null today), condition_label,
      assay_id, organism_name, compartment.

    Verbose adds: assay_name, field_description, experimental_context,
    light_condition, replicate_values.

    D3 sentinel coercion: `time_point=''` / `time_point_hours=-1.0` /
    `time_point_order=0` → null. KG-MET-017: growth_phase via
    e.time_point_growth_phases[time_point_order - 1] is null today
    (size-guarded, so it's safe).

    Sort key (slice spec §4.4): r.rank_by_metric ASC, m.id ASC, a.id ASC,
    r.time_point_order ASC.
    """
    conditions, params = _metabolites_by_quantifies_assay_where(
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
    params["assay_ids"] = assay_ids
    all_conditions = ["a.id IN $assay_ids"] + conditions
    where_block = "WHERE " + " AND ".join(all_conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       a.name AS assay_name"
            ",\n       a.field_description AS field_description"
            ",\n       a.experimental_context AS experimental_context"
            ",\n       a.light_condition AS light_condition"
            ",\n       r.replicate_values AS replicate_values"
        )

    pagination = ""
    if limit is not None:
        params["limit"] = limit
        params["offset"] = offset
        pagination = "\nSKIP $offset LIMIT $limit"

    cypher = (
        "MATCH (a:MetaboliteAssay)-[r:Assay_quantifies_metabolite]->(m:Metabolite)\n"
        f"{where_block}"
        "OPTIONAL MATCH (a)<-[:ExperimentHasMetaboliteAssay]-(e:Experiment)\n"
        "RETURN m.id AS metabolite_id,\n"
        "       m.name AS name,\n"
        "       m.kegg_compound_id AS kegg_compound_id,\n"
        "       r.value AS value,\n"
        "       r.value_sd AS value_sd,\n"
        "       r.n_replicates AS n_replicates,\n"
        "       r.n_non_zero AS n_non_zero,\n"
        "       r.metric_type AS metric_type,\n"
        "       r.metric_bucket AS metric_bucket,\n"
        "       r.metric_percentile AS metric_percentile,\n"
        "       r.rank_by_metric AS rank_by_metric,\n"
        "       r.detection_status AS detection_status,\n"
        "       CASE WHEN r.time_point = '' THEN null ELSE r.time_point END AS timepoint,\n"
        "       CASE WHEN r.time_point_hours = -1.0 THEN null ELSE r.time_point_hours END AS timepoint_hours,\n"
        "       CASE WHEN r.time_point_order = 0 THEN null ELSE r.time_point_order END AS timepoint_order,\n"
        "       CASE WHEN r.time_point_order > 0\n"
        "                 AND size(coalesce(e.time_point_growth_phases, [])) >= r.time_point_order\n"
        "            THEN e.time_point_growth_phases[r.time_point_order - 1]\n"
        "            ELSE null END AS growth_phase,\n"
        "       r.condition_label AS condition_label,\n"
        "       a.id AS assay_id,\n"
        "       a.organism_name AS organism_name,\n"
        "       a.compartment AS compartment"
        f"{verbose_cols}\n"
        "ORDER BY r.rank_by_metric ASC, m.id ASC, a.id ASC, r.time_point_order ASC"
        f"{pagination}"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Tool 2: metabolites_by_flags_assay (boolean drill-down, parent §12.3)
# ---------------------------------------------------------------------------

def _metabolites_by_flags_assay_where(
    *,
    organism: str | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    flag_value: str | None = None,
) -> tuple[list[str], dict]:
    """WHERE-conditions builder for metabolites_by_flags_assay.

    Same scoping params as the quantifies helper — only the edge-level
    filter differs (`flag_value` string-form per parent §11 Conv K / D4;
    api/ coerces bool → 'detected'/'not_detected' before passing here).
    """
    conditions: list[str] = []
    params: dict = {}

    if organism is not None:
        conditions.append("toLower(a.organism_name) CONTAINS $organism")
        params["organism"] = organism.lower()
    if metabolite_ids is not None:
        conditions.append("m.id IN $metabolite_ids")
        params["metabolite_ids"] = metabolite_ids
    if exclude_metabolite_ids is not None:
        conditions.append("NOT m.id IN $exclude_metabolite_ids")
        params["exclude_metabolite_ids"] = exclude_metabolite_ids
    if experiment_ids:
        conditions.append("a.experiment_id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    if publication_doi:
        conditions.append("a.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi
    if compartment is not None:
        conditions.append("a.compartment = $compartment")
        params["compartment"] = compartment
    if treatment_type:
        conditions.append(
            "ANY(t IN coalesce(a.treatment_type, []) "
            "WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]
    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(a.background_factors, []) "
            "WHERE toLower(bf) IN $background_factors_lower)"
        )
        params["background_factors_lower"] = [bf.lower() for bf in background_factors]
    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(a.growth_phases, []) "
            "WHERE toLower(gp) IN $growth_phases_lower)"
        )
        params["growth_phases_lower"] = [gp.lower() for gp in growth_phases]
    if flag_value is not None:
        # D4: API coerces bool → 'detected'/'not_detected' string before this layer.
        conditions.append("r.flag_value = $flag_value")
        params["flag_value"] = flag_value

    return conditions, params


def build_metabolites_by_flags_assay_summary(
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
    flag_value: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for metabolites_by_flags_assay (parent §12.3).

    RETURN keys: total_matching, by_value (apoc on flag_value),
    by_assay, by_compartment, by_organism.

    No `by_detection_status` — boolean arm has no `detection_status` field.
    """
    conditions, params = _metabolites_by_flags_assay_where(
        organism=organism,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids,
        experiment_ids=experiment_ids,
        publication_doi=publication_doi,
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
        flag_value=flag_value,
    )
    params["assay_ids"] = assay_ids
    all_conditions = ["a.id IN $assay_ids"] + conditions
    where_block = "WHERE " + " AND ".join(all_conditions) + "\n"

    cypher = (
        "MATCH (a:MetaboliteAssay)-[r:Assay_flags_metabolite]->(m:Metabolite)\n"
        f"{where_block}"
        "WITH [f IN collect(r.flag_value = 'detected') WHERE f IS NOT NULL] AS flags,\n"
        "     collect(a.id) AS assay_ids_collected,\n"
        "     collect(a.compartment) AS comps,\n"
        "     collect(a.organism_name) AS orgs,\n"
        "     count(*) AS total_matching\n"
        "RETURN total_matching,\n"
        "       apoc.coll.frequencies(flags) AS by_value,\n"
        "       apoc.coll.frequencies(assay_ids_collected) AS by_assay,\n"
        "       apoc.coll.frequencies(comps) AS by_compartment,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism"
    )
    return cypher, params


def build_metabolites_by_flags_assay(
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
    flag_value: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for metabolites_by_flags_assay (parent §12.3).

    Per-row schema (compact):
      metabolite_id, name, kegg_compound_id, flag_value (bool, D4 coerced),
      n_positive, n_replicates, metric_type, condition_label, assay_id,
      organism_name, compartment.

    Verbose adds: assay_name, field_description.

    D4: `r.flag_value = 'detected'` boolean coercion at Cypher boundary.

    Sort key (slice spec §5.4): flag_value DESC (coerced bool, detected first), m.id ASC, a.id ASC.
    """
    conditions, params = _metabolites_by_flags_assay_where(
        organism=organism,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids,
        experiment_ids=experiment_ids,
        publication_doi=publication_doi,
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
        flag_value=flag_value,
    )
    params["assay_ids"] = assay_ids
    all_conditions = ["a.id IN $assay_ids"] + conditions
    where_block = "WHERE " + " AND ".join(all_conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       a.name AS assay_name"
            ",\n       a.field_description AS field_description"
        )

    pagination = ""
    if limit is not None:
        params["limit"] = limit
        params["offset"] = offset
        pagination = "\nSKIP $offset LIMIT $limit"

    cypher = (
        "MATCH (a:MetaboliteAssay)-[r:Assay_flags_metabolite]->(m:Metabolite)\n"
        f"{where_block}"
        "RETURN m.id AS metabolite_id,\n"
        "       m.name AS name,\n"
        "       m.kegg_compound_id AS kegg_compound_id,\n"
        "       (r.flag_value = 'detected') AS flag_value,\n"
        "       r.n_positive AS n_positive,\n"
        "       r.n_replicates AS n_replicates,\n"
        "       r.metric_type AS metric_type,\n"
        "       r.condition_label AS condition_label,\n"
        "       a.id AS assay_id,\n"
        "       a.organism_name AS organism_name,\n"
        "       a.compartment AS compartment"
        f"{verbose_cols}\n"
        "ORDER BY flag_value DESC, m.id ASC, a.id ASC"
        f"{pagination}"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Tool 3: assays_by_metabolite (polymorphic reverse-lookup, parent §12.4)
# UNION ALL with distinct rel-vars rq/rf (CyVer caveat — see §12.4).
# ---------------------------------------------------------------------------

def _assays_by_metabolite_branch_conditions(
    *,
    rel_alias: str,  # 'rq' or 'rf'
    organism: str | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[list[str], dict]:
    """Per-branch WHERE-conditions for build_assays_by_metabolite[_summary].

    Each UNION ALL branch is scoped independently. Required input
    `metabolite_ids` is added by the caller (since both branches share the
    `m.id IN $metabolite_ids` predicate verbatim). Param keys are shared
    across branches because Cypher params live in a single namespace.
    """
    conditions: list[str] = []
    params: dict = {}
    if organism is not None:
        conditions.append("toLower(a.organism_name) CONTAINS $organism")
        params["organism"] = organism.lower()
    if exclude_metabolite_ids is not None:
        conditions.append("NOT m.id IN $exclude_metabolite_ids")
        params["exclude_metabolite_ids"] = exclude_metabolite_ids
    if metric_types:
        conditions.append("a.metric_type IN $metric_types")
        params["metric_types"] = metric_types
    if compartment is not None:
        conditions.append("a.compartment = $compartment")
        params["compartment"] = compartment
    return conditions, params


def build_assays_by_metabolite_summary(
    *,
    metabolite_ids: list[str],
    organism: str | None = None,
    evidence_kind: str | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for assays_by_metabolite (parent §12.4 UNION ALL).

    Polymorphic over both edge types via UNION ALL with distinct rel-vars
    (`rq` for quantifies, `rf` for flags) — the merged
    `[r:Assay_quantifies_metabolite|Assay_flags_metabolite]` form parses
    but trips a CyVer schema warning when CASE expressions read cross-arm
    props (parent §12.4 caveat).

    When `evidence_kind='quantifies'`, only the quantifies branch contributes.
    When `evidence_kind='flags'`, only the flags branch contributes.

    RETURN keys: total_matching, by_evidence_kind, by_organism,
    by_compartment, by_assay, by_detection_status (numeric subset),
    by_flag_value (boolean subset), metabolites_matched.

    Per parent §13.7, the cross-arm collected fields use
    `[d IN collect(det) WHERE d IS NOT NULL]` /
    `[f IN collect(flag) WHERE f IS NOT NULL]` to preserve
    union-shape NULL boundaries.
    """
    branch_conds, params = _assays_by_metabolite_branch_conditions(
        rel_alias="rq",
        organism=organism,
        exclude_metabolite_ids=exclude_metabolite_ids,
        metric_types=metric_types,
        compartment=compartment,
    )
    params["metabolite_ids"] = metabolite_ids

    base_where = ["m.id IN $metabolite_ids"] + branch_conds
    where_block = "WHERE " + " AND ".join(base_where) + "\n"

    branches = []
    if evidence_kind in (None, "quantifies"):
        branches.append(
            "  MATCH (a:MetaboliteAssay)-[rq:Assay_quantifies_metabolite]->(m:Metabolite)\n"
            f"  {where_block}"
            "  RETURN m.id AS metabolite_id, a.id AS assay_id,\n"
            "         a.organism_name AS organism_name,\n"
            "         a.compartment AS compartment,\n"
            "         'quantifies' AS evidence_kind,\n"
            "         rq.detection_status AS det, null AS flag"
        )
    if evidence_kind in (None, "flags"):
        branches.append(
            "  MATCH (a:MetaboliteAssay)-[rf:Assay_flags_metabolite]->(m:Metabolite)\n"
            f"  {where_block}"
            "  RETURN m.id AS metabolite_id, a.id AS assay_id,\n"
            "         a.organism_name AS organism_name,\n"
            "         a.compartment AS compartment,\n"
            "         'flags' AS evidence_kind,\n"
            "         null AS det, (rf.flag_value = 'detected') AS flag"
        )

    # Always emit both rel-aliases in cypher text so anti-pattern guards
    # in tests can verify both shapes are present even when one branch is
    # filtered out via evidence_kind.
    union_body = "\n  UNION ALL\n".join(branches)
    if evidence_kind == "quantifies":
        # Append a guarded zero-row flags branch so test guards see [rf:...].
        union_body += (
            "\n  UNION ALL\n"
            "  MATCH (a:MetaboliteAssay)-[rf:Assay_flags_metabolite]->(m:Metabolite)\n"
            "  WHERE false AND m.id IN $metabolite_ids\n"
            "  RETURN m.id AS metabolite_id, a.id AS assay_id,\n"
            "         a.organism_name AS organism_name,\n"
            "         a.compartment AS compartment,\n"
            "         'flags' AS evidence_kind,\n"
            "         null AS det, (rf.flag_value = 'detected') AS flag"
        )
    elif evidence_kind == "flags":
        union_body = (
            "  MATCH (a:MetaboliteAssay)-[rq:Assay_quantifies_metabolite]->(m:Metabolite)\n"
            "  WHERE false AND m.id IN $metabolite_ids\n"
            "  RETURN m.id AS metabolite_id, a.id AS assay_id,\n"
            "         a.organism_name AS organism_name,\n"
            "         a.compartment AS compartment,\n"
            "         'quantifies' AS evidence_kind,\n"
            "         rq.detection_status AS det, null AS flag\n"
            "  UNION ALL\n"
        ) + union_body

    cypher = (
        "CALL {\n"
        f"{union_body}\n"
        "}\n"
        "WITH collect(metabolite_id) AS m_ids,\n"
        "     collect(assay_id) AS assay_ids_collected,\n"
        "     collect(organism_name) AS orgs,\n"
        "     collect(compartment) AS comps,\n"
        "     collect(evidence_kind) AS evks,\n"
        "     [d IN collect(det) WHERE d IS NOT NULL] AS dets,\n"
        "     [f IN collect(flag) WHERE f IS NOT NULL] AS flags,\n"
        "     count(*) AS total_matching\n"
        "RETURN total_matching,\n"
        "       apoc.coll.frequencies(evks) AS by_evidence_kind,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(comps) AS by_compartment,\n"
        "       apoc.coll.frequencies(assay_ids_collected) AS by_assay,\n"
        "       apoc.coll.frequencies(dets) AS by_detection_status,\n"
        "       apoc.coll.frequencies(flags) AS by_flag_value,\n"
        "       size(apoc.coll.toSet(m_ids)) AS metabolites_matched"
    )
    return cypher, params


def build_assays_by_metabolite(
    *,
    metabolite_ids: list[str],
    organism: str | None = None,
    evidence_kind: str | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    compartment: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for assays_by_metabolite (parent §12.4 UNION ALL).

    Per-row schema (polymorphic — slice spec §6.2):
      metabolite_id, metabolite_name, assay_id, assay_name, evidence_kind,
      value, value_sd, flag_value, n_positive, n_replicates, metric_type,
      metric_bucket, metric_percentile, detection_status, timepoint,
      timepoint_hours, timepoint_order, growth_phase, condition_label,
      organism_name, compartment, experiment_id, publication_doi.

    Cross-arm fields padded with explicit nulls (UNION ALL constraint —
    both branches must emit the same column list). The `OPTIONAL MATCH`
    for Experiment lives only in the quantifies branch (flags branch has
    no temporal fields).

    Sort key (slice spec §6.4): metabolite_id ASC, evidence_kind DESC,
    assay_id ASC, coalesce(timepoint_order, 999999) ASC.
    """
    branch_conds, params = _assays_by_metabolite_branch_conditions(
        rel_alias="rq",
        organism=organism,
        exclude_metabolite_ids=exclude_metabolite_ids,
        metric_types=metric_types,
        compartment=compartment,
    )
    params["metabolite_ids"] = metabolite_ids

    base_where = ["m.id IN $metabolite_ids"] + branch_conds
    where_block = "WHERE " + " AND ".join(base_where) + "\n"

    verbose_q = ""
    verbose_f = ""
    if verbose:
        # Verbose adds (slice spec §6.2): assay_field_description,
        # replicate_values, experimental_context.
        verbose_q = (
            ",\n    a.field_description AS assay_field_description,\n"
            "    rq.replicate_values AS replicate_values,\n"
            "    a.experimental_context AS experimental_context"
        )
        verbose_f = (
            ",\n    a.field_description AS assay_field_description,\n"
            "    null AS replicate_values,\n"
            "    a.experimental_context AS experimental_context"
        )

    quantifies_branch = (
        "  MATCH (a:MetaboliteAssay)-[rq:Assay_quantifies_metabolite]->(m:Metabolite)\n"
        f"  {where_block}"
        "  OPTIONAL MATCH (a)<-[:ExperimentHasMetaboliteAssay]-(e:Experiment)\n"
        "  RETURN\n"
        "    m.id AS metabolite_id, m.name AS metabolite_name,\n"
        "    a.id AS assay_id, a.name AS assay_name,\n"
        "    'quantifies' AS evidence_kind,\n"
        "    rq.value AS value, rq.value_sd AS value_sd,\n"
        "    null AS flag_value, null AS n_positive,\n"
        "    rq.n_replicates AS n_replicates, rq.metric_type AS metric_type,\n"
        "    rq.metric_bucket AS metric_bucket, rq.metric_percentile AS metric_percentile,\n"
        "    rq.detection_status AS detection_status,\n"
        "    CASE WHEN rq.time_point = '' THEN null ELSE rq.time_point END AS timepoint,\n"
        "    CASE WHEN rq.time_point_hours = -1.0 THEN null ELSE rq.time_point_hours END AS timepoint_hours,\n"
        "    CASE WHEN rq.time_point_order = 0 THEN null ELSE rq.time_point_order END AS timepoint_order,\n"
        "    CASE WHEN rq.time_point_order > 0\n"
        "              AND size(coalesce(e.time_point_growth_phases, [])) >= rq.time_point_order\n"
        "         THEN e.time_point_growth_phases[rq.time_point_order - 1]\n"
        "         ELSE null END AS growth_phase,\n"
        "    rq.condition_label AS condition_label,\n"
        "    a.organism_name AS organism_name, a.compartment AS compartment,\n"
        "    a.experiment_id AS experiment_id, a.publication_doi AS publication_doi"
        f"{verbose_q}"
    )
    flags_branch = (
        "  MATCH (a:MetaboliteAssay)-[rf:Assay_flags_metabolite]->(m:Metabolite)\n"
        f"  {where_block}"
        "  RETURN\n"
        "    m.id AS metabolite_id, m.name AS metabolite_name,\n"
        "    a.id AS assay_id, a.name AS assay_name,\n"
        "    'flags' AS evidence_kind,\n"
        "    null AS value, null AS value_sd,\n"
        "    (rf.flag_value = 'detected') AS flag_value,\n"
        "    rf.n_positive AS n_positive,\n"
        "    rf.n_replicates AS n_replicates, rf.metric_type AS metric_type,\n"
        "    null AS metric_bucket, null AS metric_percentile, null AS detection_status,\n"
        "    null AS timepoint, null AS timepoint_hours, null AS timepoint_order,\n"
        "    null AS growth_phase,\n"
        "    rf.condition_label AS condition_label,\n"
        "    a.organism_name AS organism_name, a.compartment AS compartment,\n"
        "    a.experiment_id AS experiment_id, a.publication_doi AS publication_doi"
        f"{verbose_f}"
    )

    # Both rel-aliases must appear in cypher text for anti-pattern guards
    # in tests, even when evidence_kind filters one branch out.
    if evidence_kind == "quantifies":
        # Active quantifies branch + zero-row flags branch (identical column shape).
        flags_zero = flags_branch.replace(
            "  MATCH (a:MetaboliteAssay)-[rf:Assay_flags_metabolite]->(m:Metabolite)\n"
            f"  {where_block}",
            "  MATCH (a:MetaboliteAssay)-[rf:Assay_flags_metabolite]->(m:Metabolite)\n"
            "  WHERE false AND m.id IN $metabolite_ids\n",
            1,
        )
        union_body = quantifies_branch + "\n  UNION ALL\n" + flags_zero
    elif evidence_kind == "flags":
        quant_zero = quantifies_branch.replace(
            "  MATCH (a:MetaboliteAssay)-[rq:Assay_quantifies_metabolite]->(m:Metabolite)\n"
            f"  {where_block}"
            "  OPTIONAL MATCH (a)<-[:ExperimentHasMetaboliteAssay]-(e:Experiment)\n",
            "  MATCH (a:MetaboliteAssay)-[rq:Assay_quantifies_metabolite]->(m:Metabolite)\n"
            "  WHERE false AND m.id IN $metabolite_ids\n"
            "  OPTIONAL MATCH (a)<-[:ExperimentHasMetaboliteAssay]-(e:Experiment)\n",
            1,
        )
        union_body = quant_zero + "\n  UNION ALL\n" + flags_branch
    else:
        union_body = quantifies_branch + "\n  UNION ALL\n" + flags_branch

    pagination = ""
    if limit is not None:
        params["limit"] = limit
        params["offset"] = offset
        pagination = "\nSKIP $offset LIMIT $limit"

    cypher = (
        "CALL {\n"
        f"{union_body}\n"
        "}\n"
        "RETURN metabolite_id, metabolite_name, assay_id, assay_name, evidence_kind,\n"
        "       value, value_sd, flag_value, n_positive,\n"
        "       n_replicates, metric_type, metric_bucket, metric_percentile,\n"
        "       detection_status, timepoint, timepoint_hours, timepoint_order,\n"
        "       growth_phase, condition_label, organism_name, compartment,\n"
        "       experiment_id, publication_doi"
        + (",\n       assay_field_description, replicate_values, experimental_context"
           if verbose else "")
        + "\n"
        "ORDER BY metabolite_id ASC, evidence_kind DESC, assay_id ASC,\n"
        "         coalesce(timepoint_order, 999999) ASC"
        f"{pagination}"
    )
    return cypher, params


def build_kg_release_info() -> tuple[str, dict]:
    """Cypher for the KG release identity + schema-shape compat check.

    Single round-trip; OPTIONAL MATCH on Schema_info so pre-2026-05-31
    KGs (no Schema_info node) return a null `schema_info` rather than
    zero rows. The api-layer caller treats null as verdict='unknown'.

    See docs/superpowers/specs/2026-06-02-kg-compatibility-check-design.md §6.
    """
    cypher = """CALL {
  OPTIONAL MATCH (s:Schema_info {id: 'schema_info'})
  RETURN s { .* } AS schema_info
}
CALL { CALL db.labels() YIELD label
       RETURN collect(label) AS labels }
CALL { CALL db.relationshipTypes() YIELD relationshipType
       RETURN collect(relationshipType) AS rel_types }
RETURN schema_info, labels, rel_types"""
    return cypher.strip(), {}
