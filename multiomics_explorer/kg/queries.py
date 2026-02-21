"""Curated Cypher query library.

Contains validation queries, common patterns, and few-shot examples
for LLM prompt engineering. Ported from multiomics_biocypher_kg KG validity tests
and cypher-queries skill.
"""

# ──────────────────────────────────────────────
# Validation queries (Stage 1)
# ──────────────────────────────────────────────

GENE_COUNT = "MATCH (g:Gene) RETURN count(g) AS cnt"

ORGANISM_LIST = """
MATCH (o:OrganismTaxon)
RETURN o.strain_name AS strain, o.genus AS genus,
       o.clade AS clade, o.ncbi_taxon_id AS taxid
ORDER BY o.genus, o.strain_name
"""

ORPHAN_GENES = """
MATCH (g:Gene)
WHERE NOT (g)-[:Gene_belongs_to_organism]->()
RETURN g.locus_tag AS locus_tag LIMIT 20
"""

ORPHAN_PROTEINS = """
MATCH (p:Protein)
WHERE NOT (p)-[:Protein_belongs_to_organism]->()
RETURN p.locus_tag AS locus_tag LIMIT 20
"""

EXPRESSION_EDGE_COUNT = """
MATCH ()-[r:Affects_expression_of]->()
RETURN count(r) AS cnt
"""

HOMOLOG_EDGE_COUNT = """
MATCH ()-[r:Gene_is_homolog_of_gene]->()
RETURN count(r) AS cnt
"""

# ──────────────────────────────────────────────
# Common biological queries
# ──────────────────────────────────────────────

GENES_BY_ORGANISM = """
MATCH (g:Gene)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)
WHERE o.strain_name = $strain
RETURN g.locus_tag AS locus_tag, g.product AS product,
       g.function_description AS function_description
ORDER BY g.locus_tag
"""

GENE_DETAILS = """
MATCH (g:Gene {locus_tag: $locus_tag})
OPTIONAL MATCH (g)<-[:Gene_encodes_protein]-(p:Protein)
OPTIONAL MATCH (g)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)
RETURN g.locus_tag AS locus_tag, g.product AS product,
       g.function_description AS function_description,
       g.go_biological_processes AS go_processes,
       p.protein_name AS protein_name,
       o.strain_name AS strain
"""

HOMOLOGS_OF_GENE = """
MATCH (g:Gene {locus_tag: $locus_tag})-[h:Gene_is_homolog_of_gene]-(other:Gene)
OPTIONAL MATCH (other)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)
RETURN other.locus_tag AS locus_tag, other.product AS product,
       o.strain_name AS strain, h.distance AS distance,
       h.cluster_id AS cluster_id
ORDER BY h.distance, other.locus_tag
"""

EXPRESSION_FOR_GENE = """
MATCH (factor)-[r:Affects_expression_of]->(g:Gene {locus_tag: $locus_tag})
RETURN labels(factor) AS factor_type,
       CASE WHEN factor:OrganismTaxon THEN factor.organism_name
            ELSE factor.name END AS factor_name,
       r.expression_direction AS direction,
       r.log2_fold_change AS log2fc,
       r.adjusted_p_value AS padj,
       r.control_condition AS control,
       r.experimental_context AS context,
       r.time_point AS time_point,
       r.publications AS publications
ORDER BY abs(r.log2_fold_change) DESC
"""

GENES_UPREGULATED_BY_COCULTURE = """
MATCH (org:OrganismTaxon)-[r:Affects_expression_of]->(g:Gene)-[:Gene_belongs_to_organism]->(target:OrganismTaxon)
WHERE org.genus = $coculture_genus
  AND target.strain_name = $target_strain
  AND r.expression_direction = 'up'
RETURN g.locus_tag AS locus_tag, g.product AS product,
       r.log2_fold_change AS log2fc, r.adjusted_p_value AS padj,
       org.organism_name AS coculture_organism
ORDER BY r.log2_fold_change DESC
LIMIT 50
"""

GENES_AFFECTED_BY_STRESS = """
MATCH (env:EnvironmentalCondition)-[r:Affects_expression_of]->(g:Gene)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)
WHERE env.condition_type = $condition_type
  AND o.strain_name = $strain
RETURN g.locus_tag AS locus_tag, g.product AS product,
       r.expression_direction AS direction,
       r.log2_fold_change AS log2fc,
       env.name AS condition_name
ORDER BY abs(r.log2_fold_change) DESC
LIMIT 50
"""

FUNCTIONAL_ENRICHMENT = """
MATCH (factor)-[r:Affects_expression_of]->(g:Gene)
WHERE r.expression_direction = $direction
MATCH (g)<-[:Gene_encodes_protein]-(p:Protein)-[:protein_involved_in_biological_process]->(bp:BiologicalProcess)
RETURN bp.name AS process,
       collect(DISTINCT g.locus_tag) AS genes,
       avg(r.log2_fold_change) AS avg_log2fc,
       count(DISTINCT g) AS gene_count
ORDER BY gene_count DESC
LIMIT 20
"""

# ──────────────────────────────────────────────
# Few-shot examples for LLM prompt engineering
# ──────────────────────────────────────────────

FEW_SHOT_EXAMPLES = [
    {
        "question": "How many genes are in the MED4 strain?",
        "cypher": (
            "MATCH (g:Gene)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)\n"
            "WHERE o.strain_name = 'MED4'\n"
            "RETURN count(g) AS gene_count"
        ),
        "explanation": "Filter genes by organism using strain_name property.",
    },
    {
        "question": "What are the homologs of PMM1375 (psbA)?",
        "cypher": (
            "MATCH (g:Gene {locus_tag: 'PMM1375'})-[:Gene_is_homolog_of_gene]-(h:Gene)\n"
            "OPTIONAL MATCH (h)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)\n"
            "RETURN h.locus_tag AS locus_tag, h.product AS product, o.strain_name AS strain"
        ),
        "explanation": (
            "Gene_is_homolog_of_gene is bidirectional, so use undirected pattern (no arrow)."
        ),
    },
    {
        "question": "Which genes are upregulated in MED4 during coculture with Alteromonas?",
        "cypher": (
            "MATCH (org:OrganismTaxon)-[r:Affects_expression_of]->(g:Gene)"
            "-[:Gene_belongs_to_organism]->(target:OrganismTaxon)\n"
            "WHERE org.genus = 'Alteromonas'\n"
            "  AND target.strain_name = 'MED4'\n"
            "  AND r.expression_direction = 'up'\n"
            "RETURN g.locus_tag, g.product, r.log2_fold_change\n"
            "ORDER BY r.log2_fold_change DESC\n"
            "LIMIT 50"
        ),
        "explanation": (
            "Alteromonas (source OrganismTaxon) affects expression of MED4 genes (target). "
            "Use genus for coculture organisms, strain_name for target."
        ),
    },
    {
        "question": "Which genes are affected by nitrogen starvation in MED4?",
        "cypher": (
            "MATCH (env:EnvironmentalCondition)-[r:Affects_expression_of]->(g:Gene)"
            "-[:Gene_belongs_to_organism]->(o:OrganismTaxon)\n"
            "WHERE env.nitrogen_level = 'starved'\n"
            "  AND o.strain_name = 'MED4'\n"
            "RETURN g.locus_tag, g.product, r.expression_direction, r.log2_fold_change\n"
            "ORDER BY abs(r.log2_fold_change) DESC\n"
            "LIMIT 50"
        ),
        "explanation": (
            "EnvironmentalCondition nodes have condition-specific properties like "
            "nitrogen_level, phosphate_level, light_condition."
        ),
    },
    {
        "question": "What biological processes are enriched among genes upregulated by Alteromonas?",
        "cypher": (
            "MATCH (org:OrganismTaxon)-[r:Affects_expression_of {expression_direction: 'up'}]->"
            "(g:Gene)\n"
            "WHERE org.genus = 'Alteromonas'\n"
            "MATCH (g)<-[:Gene_encodes_protein]-(p:Protein)"
            "-[:protein_involved_in_biological_process]->(bp:BiologicalProcess)\n"
            "RETURN bp.name AS process, collect(DISTINCT g.locus_tag) AS genes, "
            "count(DISTINCT g) AS gene_count\n"
            "ORDER BY gene_count DESC\n"
            "LIMIT 10"
        ),
        "explanation": (
            "Multi-hop query: expression edge -> gene -> protein -> GO term. "
            "Note Gene_encodes_protein direction is Protein->Gene (reversed with <-)."
        ),
    },
    {
        "question": "Show gene expression over time for PMM0001 in coculture",
        "cypher": (
            "MATCH (org:OrganismTaxon)-[r:Affects_expression_of]->"
            "(g:Gene {locus_tag: 'PMM0001'})\n"
            "WHERE org.genus = 'Alteromonas'\n"
            "RETURN r.time_point, r.log2_fold_change, r.expression_direction,\n"
            "       org.organism_name\n"
            "ORDER BY r.time_point"
        ),
        "explanation": "Time series: filter by gene and order by time_point.",
    },
]
