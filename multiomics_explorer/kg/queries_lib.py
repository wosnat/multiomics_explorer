"""Shared query builders for MCP tools, CLI, and tests.

Each builder returns a (cypher, params) tuple. The caller is responsible
for executing the query via GraphConnection.execute_query(cypher, **params).
"""

# Expression relationship types in the current KG schema.
DIRECT_EXPR_RELS = "Condition_changes_expression_of|Coculture_changes_expression_of"
ORTHOLOG_EXPR_RELS = (
    "Condition_changes_expression_of_ortholog|Coculture_changes_expression_of_ortholog"
)
ALL_EXPR_RELS = f"{DIRECT_EXPR_RELS}|{ORTHOLOG_EXPR_RELS}"


def build_get_gene(
    *, id: str, organism: str | None = None
) -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene)\n"
        "WHERE (\n"
        "    g.locus_tag = $id\n"
        "    OR g.gene_name = $id\n"
        "    OR $id IN g.all_identifiers\n"
        "  )\n"
        "  AND ($organism IS NULL OR g.organism_strain CONTAINS $organism)\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.gene_summary AS gene_summary, g.product AS product,\n"
        "       g.function_description AS function_description,\n"
        "       g.organism_strain AS organism_strain,\n"
        "       g.go_terms AS go_terms, g.kegg_ko AS kegg_ko,\n"
        "       g.annotation_quality AS annotation_quality\n"
        "ORDER BY g.locus_tag\n"
        "LIMIT 5"
    )
    return cypher, {"id": id, "organism": organism}


def build_find_gene(
    *, search_text: str, organism: str | None = None,
    min_quality: int = 0, limit: int = 10,
) -> tuple[str, dict]:
    cypher = (
        "CALL db.index.fulltext.queryNodes('geneFullText', $search_text)\n"
        "YIELD node AS g, score\n"
        "WHERE ($organism IS NULL OR g.organism_strain CONTAINS $organism)\n"
        "  AND ($min_quality = 0 OR g.annotation_quality >= $min_quality)\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.gene_summary AS gene_summary, g.product AS product,\n"
        "       g.organism_strain AS organism_strain,\n"
        "       g.annotation_quality AS annotation_quality,\n"
        "       score\n"
        "ORDER BY score DESC, g.locus_tag\n"
        "LIMIT $limit"
    )
    return cypher, {
        "search_text": search_text, "organism": organism,
        "min_quality": min_quality, "limit": limit,
    }


def build_search_genes(
    *, query: str, organism: str | None = None, limit: int = 20,
) -> tuple[str, dict]:
    where_clauses = [
        "(g.locus_tag CONTAINS $q OR "
        "toLower(g.product) CONTAINS toLower($q) OR "
        "toLower(g.gene_name) CONTAINS toLower($q))"
    ]
    params: dict = {"q": query, "limit": limit}

    if organism:
        where_clauses.append("g.organism_strain CONTAINS $strain")
        params["strain"] = organism

    where = " AND ".join(where_clauses)
    cypher = (
        "MATCH (g:Gene)\n"
        f"WHERE {where}\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_strain AS organism_strain\n"
        "ORDER BY g.locus_tag\n"
        "LIMIT $limit"
    )
    return cypher, params


def build_get_gene_details_main(*, gene_id: str) -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene {locus_tag: $lt})\n"
        "OPTIONAL MATCH (g)-[:Gene_encodes_protein]->(p:Protein)\n"
        "OPTIONAL MATCH (g)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)\n"
        "OPTIONAL MATCH (g)-[:Gene_in_cyanorak_cluster]->(c:Cyanorak_cluster)\n"
        "RETURN g {.*, _protein: p {.gene_names, .is_reviewed, .annotation_score,\n"
        "           .sequence_length, .refseq_ids},\n"
        "       _organism: o {.preferred_name, .strain_name, .genus, .clade, .ncbi_taxon_id},\n"
        "       _cluster: c {.cluster_number}} AS gene"
    )
    return cypher, {"lt": gene_id}


def build_get_gene_details_homologs(*, gene_id: str) -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene {locus_tag: $lt})-[h:Gene_is_homolog_of_gene]-(other:Gene)\n"
        "RETURN other.locus_tag AS locus_tag, other.organism_strain AS organism_strain,\n"
        "       h.distance AS distance, h.cluster_id AS cluster_id,\n"
        "       h.source AS source\n"
        "ORDER BY h.distance, other.locus_tag\n"
        "LIMIT 20"
    )
    return cypher, {"lt": gene_id}


def build_query_expression(
    *,
    gene_id: str | None = None,
    organism: str | None = None,
    condition: str | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
    include_orthologs: bool = False,
    limit: int = 50,
) -> tuple[str, dict]:
    expr_rels = ALL_EXPR_RELS if include_orthologs else DIRECT_EXPR_RELS

    where_clauses: list[str] = []
    params: dict = {"limit": limit}

    if gene_id:
        where_clauses.append("g.locus_tag = $gene_id")
        params["gene_id"] = gene_id

    if organism:
        where_clauses.append("r.organism_strain CONTAINS $target_strain")
        params["target_strain"] = organism

    if condition:
        where_clauses.append(
            "(CASE WHEN factor:OrganismTaxon "
            "THEN (factor.genus CONTAINS $cond OR factor.organism_name CONTAINS $cond) "
            "ELSE (factor.name CONTAINS $cond OR factor.condition_type CONTAINS $cond) "
            "END)"
        )
        params["cond"] = condition

    if direction:
        where_clauses.append("r.expression_direction = $dir")
        params["dir"] = direction.lower()

    if min_log2fc is not None:
        where_clauses.append("abs(r.log2_fold_change) >= $min_fc")
        params["min_fc"] = min_log2fc

    if max_pvalue is not None:
        where_clauses.append(
            "r.adjusted_p_value IS NOT NULL AND r.adjusted_p_value <= $max_pv"
        )
        params["max_pv"] = max_pvalue

    where_block = " AND ".join(where_clauses)

    cypher = (
        f"MATCH (factor)-[r:{expr_rels}]->(g:Gene)\n"
        f"WHERE {where_block}\n"
        "RETURN g.locus_tag AS gene, g.product AS product,\n"
        "       type(r) AS edge_type,\n"
        "       CASE WHEN factor:OrganismTaxon THEN factor.organism_name\n"
        "            ELSE factor.name END AS source,\n"
        "       r.expression_direction AS direction,\n"
        "       r.log2_fold_change AS log2fc,\n"
        "       r.adjusted_p_value AS padj,\n"
        "       r.organism_strain AS organism_strain,\n"
        "       r.control_condition AS control,\n"
        "       r.experimental_context AS context,\n"
        "       r.time_point AS time_point,\n"
        "       r.publications AS publications\n"
        "ORDER BY abs(r.log2_fold_change) DESC, g.locus_tag, source\n"
        "LIMIT $limit"
    )
    return cypher, params


def build_compare_conditions(
    *,
    gene_ids: list[str] | None = None,
    organisms: list[str] | None = None,
    conditions: list[str] | None = None,
    limit: int = 100,
) -> tuple[str, dict]:
    where_clauses: list[str] = []
    params: dict = {"limit": limit}

    if gene_ids:
        where_clauses.append("g.locus_tag IN $gene_ids")
        params["gene_ids"] = gene_ids

    if organisms:
        where_clauses.append(
            "any(org IN $organisms WHERE r.organism_strain CONTAINS org)"
        )
        params["organisms"] = organisms

    if conditions:
        where_clauses.append(
            "CASE WHEN factor:OrganismTaxon "
            "THEN factor.genus IN $conditions "
            "ELSE factor.condition_type IN $conditions END"
        )
        params["conditions"] = conditions

    where_block = " AND ".join(where_clauses)

    cypher = (
        f"MATCH (factor)-[r:{DIRECT_EXPR_RELS}]->(g:Gene)\n"
        f"WHERE {where_block}\n"
        "RETURN g.locus_tag AS gene, g.product AS product,\n"
        "       r.organism_strain AS target_strain,\n"
        "       CASE WHEN factor:OrganismTaxon THEN factor.organism_name\n"
        "            ELSE factor.name END AS source,\n"
        "       r.expression_direction AS direction,\n"
        "       r.log2_fold_change AS log2fc,\n"
        "       r.adjusted_p_value AS padj,\n"
        "       r.experimental_context AS context\n"
        "ORDER BY g.locus_tag, source, r.log2_fold_change\n"
        "LIMIT $limit"
    )
    return cypher, params


def build_get_homologs(*, gene_id: str) -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene {locus_tag: $lt})-[h:Gene_is_homolog_of_gene]-(other:Gene)\n"
        "RETURN other.locus_tag AS locus_tag, other.product AS product,\n"
        "       other.organism_strain AS organism_strain,\n"
        "       h.distance AS distance, h.cluster_id AS cluster_id,\n"
        "       h.source AS source\n"
        "ORDER BY h.distance, other.locus_tag"
    )
    return cypher, {"lt": gene_id}


def build_homolog_expression(*, gene_ids: list[str]) -> tuple[str, dict]:
    cypher = (
        f"MATCH (factor)-[r:{DIRECT_EXPR_RELS}]->(g:Gene)\n"
        "WHERE g.locus_tag IN $ids\n"
        "RETURN g.locus_tag AS gene,\n"
        "       type(r) AS edge_type,\n"
        "       CASE WHEN factor:OrganismTaxon THEN factor.organism_name\n"
        "            ELSE factor.name END AS source,\n"
        "       r.expression_direction AS direction,\n"
        "       r.log2_fold_change AS log2fc,\n"
        "       r.adjusted_p_value AS padj\n"
        "ORDER BY g.locus_tag, abs(r.log2_fold_change) DESC, source"
    )
    return cypher, {"ids": gene_ids}
