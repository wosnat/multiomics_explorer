"""Shared constants for the knowledge graph layer."""

# Canonical ontology keys — all 17 supported by ONTOLOGY_CONFIG.
# Order is load-bearing for ontology_landscape regression-fixture determinism:
# new ontologies are APPENDED, never inserted (interpro / ncbifam / merops
# joined in the 2026-08 annotation-trust surface).
ALL_ONTOLOGIES: list[str] = [
    "go_bp", "go_mf", "go_cc", "ec", "kegg",
    "cog_category", "cyanorak_role", "tigr_role", "pfam",
    "brite", "tcdb", "cazy",
    "subcellular_localization", "signal_peptide_type",
    "interpro", "ncbifam", "merops",
]

# Subset of ALL_ONTOLOGIES that have GO-DAG-based level assignments.
# Only these ontologies emit best_effort_share (non-GO rows get None).
GO_ONTOLOGIES: frozenset[str] = frozenset({"go_bp", "go_mf", "go_cc"})

VALID_OG_SOURCES: set[str] = {"cyanorak", "eggnog"}

VALID_TAXONOMIC_LEVELS: set[str] = {
    "curated", "Prochloraceae", "Synechococcus",
    "Alteromonadaceae", "Cyanobacteria",
    "Proteobacteria", "Bacteria",
}

MAX_SPECIFICITY_RANK: int = 3  # 0=curated, 1=family, 2=order, 3=domain

VALID_CLUSTER_TYPES: set[str] = {
    "condition_comparison",
    "diel",
    "time_course",
    "expression_bin",
    "decay_pattern",
    "genomic_island",
}

VALID_OMICS_TYPES: set[str] = {
    "EXOPROTEOMICS",
    "METABOLOMICS",
    "MICROARRAY",
    "PAIRED_RNASEQ_PROTEOME",
    "PROTEOMICS",
    "RNASEQ",
    "VESICLE_DNASEQ",
    "VESICLE_PROTEOMICS",
}


# Schema-shape contract for the KG ↔ explorer compatibility check
# (api/functions.kg_release_info). Six buckets, all small. Bucket 5
# (version compatibility) is computed in api/functions.py, not stored here;
# bucket 6 (vocabulary set) is the `controlled_vocabularies_hash` key in
# the dict below.
# See docs/superpowers/specs/2026-06-02-kg-compatibility-check-design.md §5.
#
# Bucket 6 (vocabulary set): the `Schema_info.controlled_vocabularies_hash`
# this explorer was built against (KG-SYNC-006 + two-state strings HO-001 +
# Meiothermus HO-002 + TigrRole hierarchy / NCBIfam→TigrRole bridge + docs-review
# asks DOC-001/004: Gene_has_pfam.evidence gains family_inferred, compartment
# loses spent_medium / lysate, built 2026-08-29T18:29Z, KG contract v2). The recipe lives KG-side (docs/kg-changes/
# vocabulary-contract.md). A mismatch means baked docs / parameter descriptions
# may list stale values — filters still validate live. Must equal the live
# KG's value at release cut.
EXPECTED_CONTROLLED_VOCABULARIES_HASH: str = (
    "sha256:1f671eaef9de7efc4489f749ec3c429581e1c3e6f5f30932c97bad547539a10c"
)

EXPECTED_KG_SHAPE: dict[str, tuple[str, ...] | str] = {
    # 6. Vocabulary set (see above).
    "controlled_vocabularies_hash": EXPECTED_CONTROLLED_VOCABULARIES_HASH,
    # 1. The contract surface — Schema_info must exist and carry these properties.
    "schema_info_required_props": (
        "version",
        "built_at",
        "mcp_min_version",
        "gene_count",
        "experiment_count",
    ),
    # 2. Foundational node labels every tool family touches.
    "required_node_labels": (
        "Schema_info",
        "Gene",
        "Experiment",
        "OrthologGroup",
        "Publication",
    ),
    # 3. Foundational relationship types.
    "required_relationship_types": (
        "Changes_expression_of",
        "Gene_in_ortholog_group",
        "Has_experiment",
    ),
    # 4. Counts that must be non-zero (catches "connected to empty DB").
    "required_nonzero_counts": (
        "gene_count",
        "experiment_count",
    ),
}


# Two-state string properties (KG hand-off 2026-08-28, HO-001). The KG stores
# these as named string pairs, never "true"/"false"; the explorer keeps a
# boolean surface and coerces at the Cypher boundary. Positive literal first.
TWO_STATE: dict[str, tuple[str, str]] = {
    "is_time_course": ("time_course", "single_time_point"),
    "reports_fold_change": ("fold_change", "no_fold_change"),
    "rankable": ("rankable", "not_rankable"),
    "has_p_value": ("p_value", "no_p_value"),
    "significant": ("significant", "not_significant"),
    "value": ("flagged", "not_flagged"),  # Derived_metric_flags_gene.value
    "flag_value": ("detected", "not_detected"),  # Assay_flags_metabolite.flag_value
}


def two_state(prop: str, flag: bool) -> str:
    """Map a boolean filter value to the KG's two-state literal for `prop`."""
    pos, neg = TWO_STATE[prop]
    return pos if flag else neg
