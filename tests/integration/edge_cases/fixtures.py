"""Pinned, KG-discovered degenerate inputs for the corner-case harness.

Each fixture is degenerate in exactly one way. The companion guard test
(test_fixture_guards.py) asserts each still has its degenerate property after a
KG rebuild; if a rebuild populates a previously-empty layer, the guard fails
and the fixture must be re-pinned using the discovery cypher in its comment.
"""

# --- Organisms by data-layer population -----------------------------------

# experiment_count == 0, genes present. 11 such strains as of 2026-06-15.
# MATCH (o:OrganismTaxon) WHERE coalesce(o.experiment_count,0)=0
#   AND coalesce(o.gene_count,0)>0 RETURN o.preferred_name LIMIT 1
GENOME_ONLY_ORGANISM = "Prochlorococcus MIT9515"

# Has Experiment nodes but METABOLOMICS-only — no transcriptomic / DE layer
# (0 Changes_expression_of edges).
# MATCH (o:OrganismTaxon) WHERE o.experiment_count>0
#   AND o.omics_types=['METABOLOMICS'] RETURN o.preferred_name LIMIT 1
EXPRESSION_LAYER_EMPTY_ORGANISM = "Prochlorococcus MIT0801"

# Fully populated control for sanity baselines.
CONTROL_ORGANISM = "Prochlorococcus MED4"

# --- Genes by layer -------------------------------------------------------

# Valid MED4 gene with zero Changes_expression_of edges.
# MATCH (g:Gene {organism_name:'Prochlorococcus MED4'})
#   WHERE NOT EXISTS { (:Experiment)-[:Changes_expression_of]->(g) }
#   RETURN g.locus_tag LIMIT 1
GENE_NO_DE = "PMM1720"

# Unknown locus tag (never present).
UNKNOWN_LOCUS = "PMM_DOES_NOT_EXIST"

# Real + fake mix for not_found correctness (single organism).
MIXED_LOCUS_BATCH = ["PMM0001", "PMM_DOES_NOT_EXIST"]

# --- Other unknown IDs (for not_found buckets) ----------------------------

UNKNOWN_EXPERIMENT_ID = "exp_does_not_exist"
UNKNOWN_PUBLICATION_DOI = "10.0000/does.not.exist"
UNKNOWN_METABOLITE_ID = "kegg.compound:C99999"
UNKNOWN_HOMOLOG_GROUP = "cyanorak:CK_99999999"
UNKNOWN_CLUSTER_ID = "cluster_does_not_exist"
UNKNOWN_DERIVED_METRIC_ID = "dm_does_not_exist"
UNKNOWN_ONTOLOGY_TERM = "go:9999999"

# --- Pagination -----------------------------------------------------------

OFFSET_PAST_END = 10_000_000
