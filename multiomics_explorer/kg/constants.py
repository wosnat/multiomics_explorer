"""Shared constants for the knowledge graph layer."""

# Canonical ontology keys — all nine supported by ONTOLOGY_CONFIG.
# Order is load-bearing for ontology_landscape regression-fixture determinism.
ALL_ONTOLOGIES: list[str] = [
    "go_bp", "go_mf", "go_cc", "ec", "kegg",
    "cog_category", "cyanorak_role", "tigr_role", "pfam",
    "brite", "tcdb", "cazy",
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
}

VALID_OMICS_TYPES: set[str] = {
    "EXOPROTEOMICS",
    "MICROARRAY",
    "PAIRED_RNASEQ_PROTEOME",
    "PROTEOMICS",
    "RNASEQ",
    "VESICLE_DNASEQ",
    "VESICLE_PROTEOMICS",
}
