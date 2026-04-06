"""Shared constants for the knowledge graph layer."""

VALID_OG_SOURCES: set[str] = {"cyanorak", "eggnog"}

VALID_TAXONOMIC_LEVELS: set[str] = {
    "curated", "Prochloraceae", "Synechococcus",
    "Alteromonadaceae", "Cyanobacteria",
    "Proteobacteria", "Bacteria",
}

MAX_SPECIFICITY_RANK: int = 3  # 0=curated, 1=family, 2=order, 3=domain

VALID_CLUSTER_TYPES: set[str] = {
    "diel_cycling",
    "diel_expression_pattern",
    "expression_classification",
    "expression_level",
    "expression_pattern",
    "periodicity_classification",
    "response_pattern",
}

VALID_OMICS_TYPES: set[str] = {
    "EXOPROTEOMICS",
    "MICROARRAY",
    "PROTEOMICS",
    "RNASEQ",
}
