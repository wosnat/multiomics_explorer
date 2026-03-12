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
MATCH ()-[r:Condition_changes_expression_of|Coculture_changes_expression_of]->()
RETURN count(r) AS cnt
"""

ORTHOLOG_EXPRESSION_EDGE_COUNT = """
MATCH ()-[r:Condition_changes_expression_of_ortholog|Coculture_changes_expression_of_ortholog]->()
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
OPTIONAL MATCH (g)-[:Gene_encodes_protein]->(p:Protein)
OPTIONAL MATCH (g)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.function_description AS function_description,
       g.go_terms AS go_terms, g.kegg_ko AS kegg_ko,
       g.annotation_quality AS annotation_quality,
       p.gene_names AS protein_names, p.is_reviewed AS protein_reviewed,
       o.strain_name AS strain
"""

HOMOLOGS_OF_GENE = """
MATCH (g:Gene {locus_tag: $locus_tag})-[h:Gene_is_homolog_of_gene]-(other:Gene)
OPTIONAL MATCH (other)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)
RETURN other.locus_tag AS locus_tag, other.product AS product,
       o.strain_name AS strain, h.distance AS distance,
       h.cluster_id AS cluster_id, h.source AS source
ORDER BY h.distance, other.locus_tag
"""

EXPRESSION_FOR_GENE = """
MATCH (factor)-[r:Condition_changes_expression_of|Coculture_changes_expression_of]->(g:Gene {locus_tag: $locus_tag})
RETURN type(r) AS edge_type,
       CASE WHEN factor:OrganismTaxon THEN factor.organism_name
            ELSE factor.name END AS source,
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
MATCH (org:OrganismTaxon)-[r:Coculture_changes_expression_of {expression_direction: 'up'}]->(g:Gene)
WHERE org.genus = $coculture_genus
  AND r.organism_strain CONTAINS $target_strain
RETURN g.locus_tag AS locus_tag, g.product AS product,
       r.log2_fold_change AS log2fc, r.adjusted_p_value AS padj,
       org.organism_name AS coculture_organism
ORDER BY r.log2_fold_change DESC
LIMIT 50
"""

GENES_AFFECTED_BY_STRESS = """
MATCH (env:EnvironmentalCondition)-[r:Condition_changes_expression_of]->(g:Gene)
WHERE env.condition_type = $condition_type
  AND r.organism_strain CONTAINS $strain
RETURN g.locus_tag AS locus_tag, g.product AS product,
       r.expression_direction AS direction,
       r.log2_fold_change AS log2fc,
       env.name AS condition_name
ORDER BY abs(r.log2_fold_change) DESC
LIMIT 50
"""

FUNCTIONAL_ENRICHMENT = """
MATCH (factor)-[r:Condition_changes_expression_of|Coculture_changes_expression_of]->(g:Gene)
WHERE r.expression_direction = $direction
MATCH (g)-[:Gene_involved_in_biological_process]->(bp:BiologicalProcess)
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
            "MATCH (g:Gene {locus_tag: 'PMM1375'})-[h:Gene_is_homolog_of_gene]-(hg:Gene)\n"
            "OPTIONAL MATCH (hg)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)\n"
            "RETURN hg.locus_tag AS locus_tag, hg.product AS product,\n"
            "       o.strain_name AS strain, h.source, h.distance"
        ),
        "explanation": (
            "Gene_is_homolog_of_gene is bidirectional, so use undirected pattern (no arrow). "
            "h.source indicates origin: cyanorak_cluster, eggnog_alteromonadaceae_og, or eggnog_bacteria_cog_og."
        ),
    },
    {
        "question": "Which genes are upregulated in MED4 during coculture with Alteromonas?",
        "cypher": (
            "MATCH (org:OrganismTaxon)-[r:Coculture_changes_expression_of {expression_direction: 'up'}]->(g:Gene)\n"
            "WHERE org.genus = 'Alteromonas'\n"
            "  AND r.organism_strain CONTAINS 'MED4'\n"
            "RETURN g.locus_tag, g.product, r.log2_fold_change\n"
            "ORDER BY r.log2_fold_change DESC\n"
            "LIMIT 50"
        ),
        "explanation": (
            "Coculture expression uses Coculture_changes_expression_of (OrganismTaxon → Gene). "
            "Source is the genome strain of the coculture partner — filter by org.genus = 'Alteromonas' "
            "(not organism_name, which is the specific strain like 'HOT1A3'). "
            "r.organism_strain is the target organism whose genes are affected."
        ),
    },
    {
        "question": "Which genes are affected by nitrogen stress in MED4?",
        "cypher": (
            "MATCH (env:EnvironmentalCondition {condition_type: 'nutrient_stress'})"
            "-[r:Condition_changes_expression_of]->(g:Gene)\n"
            "WHERE r.organism_strain = 'MED4'\n"
            "  AND env.description CONTAINS 'nitrogen'\n"
            "RETURN g.locus_tag, g.product, r.expression_direction, r.log2_fold_change\n"
            "ORDER BY abs(r.log2_fold_change) DESC\n"
            "LIMIT 50"
        ),
        "explanation": (
            "Environmental stress uses Condition_changes_expression_of (EnvironmentalCondition → Gene). "
            "Filter by condition_type (e.g. 'nutrient_stress', 'light_stress', 'salt_stress') "
            "and use description CONTAINS for specific stressors. "
            "EnvironmentalCondition has NO nitrogen_level/phosphate_level properties."
        ),
    },
    {
        "question": "What biological processes are enriched among genes upregulated by Alteromonas coculture?",
        "cypher": (
            "MATCH (org:OrganismTaxon)-[r:Coculture_changes_expression_of {expression_direction: 'up'}]->"
            "(g:Gene)\n"
            "WHERE org.organism_name = 'Alteromonas'\n"
            "MATCH (g)-[:Gene_involved_in_biological_process]->(bp:BiologicalProcess)\n"
            "RETURN bp.name AS process, collect(DISTINCT g.locus_tag) AS genes, "
            "count(DISTINCT g) AS gene_count\n"
            "ORDER BY gene_count DESC\n"
            "LIMIT 10"
        ),
        "explanation": (
            "Multi-hop: expression edge → gene → GO biological process. "
            "Use Gene_involved_in_biological_process (Gene → BiologicalProcess), "
            "not the old protein_involved_in_biological_process."
        ),
    },
    {
        "question": "Show gene expression over time for PMM0001 in coculture",
        "cypher": (
            "MATCH (org:OrganismTaxon)-[r:Coculture_changes_expression_of]->"
            "(g:Gene {locus_tag: 'PMM0001'})\n"
            "WHERE r.time_point IS NOT NULL\n"
            "RETURN org.organism_name, r.time_point, r.log2_fold_change,\n"
            "       r.expression_direction\n"
            "ORDER BY r.time_point"
        ),
        "explanation": "Time series: filter by gene and order by time_point.",
    },
    {
        "question": "Which KEGG pathways are enriched among genes downregulated by nitrogen stress?",
        "cypher": (
            "MATCH (env:EnvironmentalCondition {condition_type: 'nutrient_stress'})"
            "-[r:Condition_changes_expression_of {expression_direction: 'down'}]->(g:Gene)\n"
            "WHERE env.description CONTAINS 'nitrogen'\n"
            "MATCH (g)-[:Gene_has_kegg_ko]->(ko:KeggOrthologousGroup)"
            "-[:Ko_in_kegg_pathway]->(pw:KeggPathway)\n"
            "RETURN pw.name AS pathway, count(DISTINCT g) AS gene_count\n"
            "ORDER BY gene_count DESC\n"
            "LIMIT 10"
        ),
        "explanation": (
            "Multi-hop: expression edge → gene → KEGG KO → pathway. "
            "Use the Gene_has_kegg_ko → Ko_in_kegg_pathway chain for pathway enrichment."
        ),
    },
]
