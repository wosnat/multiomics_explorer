"""Shared query builders for MCP tools, CLI, and tests.

Each builder returns a (cypher, params) tuple. The caller is responsible
for executing the query via GraphConnection.execute_query(cypher, **params).
"""

# Ontology type configuration — drives all three ontology query builders.
ONTOLOGY_CONFIG = {
    "go_bp": {
        "label": "BiologicalProcess",
        "gene_rel": "Gene_involved_in_biological_process",
        "hierarchy_rels": [
            "Biological_process_is_a_biological_process",
            "Biological_process_part_of_biological_process",
        ],
        "fulltext_index": "biologicalProcessFullText",
    },
    "go_mf": {
        "label": "MolecularFunction",
        "gene_rel": "Gene_enables_molecular_function",
        "hierarchy_rels": [
            "Molecular_function_is_a_molecular_function",
            "Molecular_function_part_of_molecular_function",
        ],
        "fulltext_index": "molecularFunctionFullText",
    },
    "go_cc": {
        "label": "CellularComponent",
        "gene_rel": "Gene_located_in_cellular_component",
        "hierarchy_rels": [
            "Cellular_component_is_a_cellular_component",
            "Cellular_component_part_of_cellular_component",
        ],
        "fulltext_index": "cellularComponentFullText",
    },
    "ec": {
        "label": "EcNumber",
        "gene_rel": "Gene_catalyzes_ec_number",
        "hierarchy_rels": ["Ec_number_is_a_ec_number"],
        "fulltext_index": "ecNumberFullText",
    },
    "kegg": {
        "label": "KeggTerm",
        "gene_rel": "Gene_has_kegg_ko",
        "hierarchy_rels": ["Kegg_term_is_a_kegg_term"],
        "fulltext_index": "keggFullText",
        "gene_connects_to_level": "ko",  # genes only link to ko-level nodes
    },
    "cog_category": {
        "label": "CogFunctionalCategory",
        "gene_rel": "Gene_in_cog_category",
        "hierarchy_rels": [],
        "fulltext_index": "cogCategoryFullText",
    },
    "cyanorak_role": {
        "label": "CyanorakRole",
        "gene_rel": "Gene_has_cyanorak_role",
        "hierarchy_rels": ["Cyanorak_role_is_a_cyanorak_role"],
        "fulltext_index": "cyanorakRoleFullText",
    },
    "tigr_role": {
        "label": "TigrRole",
        "gene_rel": "Gene_has_tigr_role",
        "hierarchy_rels": [],
        "fulltext_index": "tigrRoleFullText",
    },
    "pfam": {
        "label": "Pfam",
        "gene_rel": "Gene_has_pfam",
        "hierarchy_rels": ["Pfam_in_pfam_clan"],
        "fulltext_index": "pfamFullText",
        "parent_label": "PfamClan",
        "parent_fulltext_index": "pfamClanFullText",
    },
}

# Expression relationship types in the current KG schema.
DIRECT_EXPR_RELS = "Condition_changes_expression_of|Coculture_changes_expression_of"


def build_resolve_gene(
    *, identifier: str, organism: str | None = None
) -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene)\n"
        "WHERE (\n"
        "    g.locus_tag = $identifier\n"
        "    OR g.gene_name = $identifier\n"
        "    OR $identifier IN g.all_identifiers\n"
        "  )\n"
        "  AND ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_strain) CONTAINS word))\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_strain AS organism_strain\n"
        "ORDER BY g.locus_tag"
    )
    return cypher, {"identifier": identifier, "organism": organism}


def build_search_genes(
    *, search_text: str, organism: str | None = None,
    category: str | None = None,
    min_quality: int = 0, limit: int = 10,
) -> tuple[str, dict]:
    cypher = (
        "CALL db.index.fulltext.queryNodes('geneFullText', $search_text)\n"
        "YIELD node AS g, score\n"
        "WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_strain) CONTAINS word))\n"
        "  AND ($min_quality = 0 OR g.annotation_quality >= $min_quality)\n"
        "  AND ($category IS NULL OR g.gene_category = $category)\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.function_description AS function_description,\n"
        "       g.gene_summary AS gene_summary,\n"
        "       g.organism_strain AS organism_strain,\n"
        "       g.annotation_quality AS annotation_quality,\n"
        "       score\n"
        "ORDER BY score DESC, g.locus_tag\n"
        "LIMIT $limit"
    )
    return cypher, {
        "search_text": search_text, "organism": organism,
        "category": category,
        "min_quality": min_quality, "limit": limit,
    }


def build_search_genes_dedup_groups(*, locus_tags: list[str]) -> tuple[str, dict]:
    """Return the most specific OrthologGroup name for each gene (for dedup)."""
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        "WHERE og.specificity_rank < 3\n"
        "WITH g.locus_tag AS locus_tag, og ORDER BY og.specificity_rank\n"
        "WITH locus_tag, collect(og.name)[0] AS dedup_group\n"
        "RETURN locus_tag, dedup_group"
    )
    return cypher, {"locus_tags": locus_tags}


def build_get_gene_details_main(*, gene_id: str) -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene {locus_tag: $lt})\n"
        "OPTIONAL MATCH (g)-[:Gene_encodes_protein]->(p:Protein)\n"
        "OPTIONAL MATCH (g)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)\n"
        "OPTIONAL MATCH (g)-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        "WITH g, p, o, collect(DISTINCT og {.name, .source, .taxonomic_level}) AS ogs\n"
        "RETURN g {.*, _protein: p {.gene_names, .is_reviewed, .annotation_score,\n"
        "           .sequence_length, .refseq_ids},\n"
        "       _organism: o {.preferred_name, .strain_name, .genus, .clade, .ncbi_taxon_id},\n"
        "       _ortholog_groups: ogs} AS gene"
    )
    return cypher, {"lt": gene_id}


def build_get_gene_details_homologs(*, gene_id: str) -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene {locus_tag: $lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        "      <-[:Gene_in_ortholog_group]-(other:Gene)\n"
        "WHERE other <> g\n"
        "RETURN DISTINCT other.locus_tag AS locus_tag,\n"
        "       other.organism_strain AS organism_strain,\n"
        "       og.source AS source, og.taxonomic_level AS taxonomic_level\n"
        "ORDER BY og.taxonomic_level, other.locus_tag\n"
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
    limit: int = 50,
) -> tuple[str, dict]:
    expr_rels = DIRECT_EXPR_RELS

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
    where_line = f"WHERE {where_block}\n" if where_block else "\n"

    cypher = (
        f"MATCH (factor)-[r:{expr_rels}]->(g:Gene)\n"
        f"{where_line}"
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
    where_line = f"WHERE {where_block}\n" if where_block else "\n"

    cypher = (
        f"MATCH (factor)-[r:{DIRECT_EXPR_RELS}]->(g:Gene)\n"
        f"{where_line}"
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


def build_gene_stub(*, gene_id: str) -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene {locus_tag: $lt})\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_strain AS organism_strain"
    )
    return cypher, {"lt": gene_id}


def build_get_homologs_groups(
    *,
    gene_id: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
) -> tuple[str, dict]:
    conditions: list[str] = []
    params: dict = {"lt": gene_id}

    if source is not None:
        conditions.append("og.source = $source")
        params["source"] = source
    if taxonomic_level is not None:
        conditions.append("og.taxonomic_level = $level")
        params["level"] = taxonomic_level
    if max_specificity_rank is not None:
        conditions.append("og.specificity_rank <= $max_rank")
        params["max_rank"] = max_specificity_rank

    where_block = " AND ".join(conditions)
    where_line = f"WHERE {where_block}\n" if where_block else ""

    cypher = (
        "MATCH (g:Gene {locus_tag: $lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        f"{where_line}"
        "RETURN og.name AS og_name, og.source AS source,\n"
        "       og.taxonomic_level AS taxonomic_level,\n"
        "       og.specificity_rank AS specificity_rank,\n"
        "       og.consensus_product AS consensus_product,\n"
        "       og.consensus_gene_name AS consensus_gene_name,\n"
        "       og.member_count AS member_count,\n"
        "       og.organism_count AS organism_count,\n"
        "       og.genera AS genera,\n"
        "       og.has_cross_genus_members AS has_cross_genus_members\n"
        "ORDER BY og.specificity_rank, og.source"
    )
    return cypher, params


def build_get_homologs_members(
    *,
    gene_id: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    exclude_paralogs: bool = True,
) -> tuple[str, dict]:
    conditions: list[str] = ["other <> g"]
    params: dict = {"lt": gene_id}

    if exclude_paralogs:
        conditions.append("other.organism_strain <> g.organism_strain")
    if source is not None:
        conditions.append("og.source = $source")
        params["source"] = source
    if taxonomic_level is not None:
        conditions.append("og.taxonomic_level = $level")
        params["level"] = taxonomic_level
    if max_specificity_rank is not None:
        conditions.append("og.specificity_rank <= $max_rank")
        params["max_rank"] = max_specificity_rank

    where_block = " AND ".join(conditions)

    cypher = (
        "MATCH (g:Gene {locus_tag: $lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        "      <-[:Gene_in_ortholog_group]-(other:Gene)\n"
        f"WHERE {where_block}\n"
        "RETURN og.name AS og_name,\n"
        "       other.locus_tag AS locus_tag, other.gene_name AS gene_name,\n"
        "       other.product AS product, other.organism_strain AS organism_strain\n"
        "ORDER BY og.specificity_rank, og.source, other.organism_strain, other.locus_tag"
    )
    return cypher, params


def build_list_gene_categories() -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene) WHERE g.gene_category IS NOT NULL\n"
        "RETURN g.gene_category AS category, count(*) AS gene_count\n"
        "ORDER BY gene_count DESC"
    )
    return cypher, {}


def build_list_condition_types() -> tuple[str, dict]:
    cypher = (
        "MATCH (e:EnvironmentalCondition)\n"
        "RETURN e.condition_type AS condition_type, count(*) AS cnt\n"
        "ORDER BY cnt DESC"
    )
    return cypher, {}


def build_list_organisms() -> tuple[str, dict]:
    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        "OPTIONAL MATCH (g:Gene)-[:Gene_belongs_to_organism]->(o)\n"
        "RETURN o.preferred_name AS name, o.genus AS genus,\n"
        "       o.strain_name AS strain, o.clade AS clade,\n"
        "       count(g) AS gene_count\n"
        "ORDER BY o.genus, o.preferred_name"
    )
    return cypher, {}


def build_search_ontology(
    *, ontology: str, search_text: str, limit: int = 25,
) -> tuple[str, dict]:
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    cfg = ONTOLOGY_CONFIG[ontology]
    index_name = cfg["fulltext_index"]
    parent_index = cfg.get("parent_fulltext_index")

    if parent_index:
        # UNION search across both indexes (e.g. Pfam domain + clan)
        cypher = (
            "CALL {\n"
            f"  CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "  YIELD node AS t, score\n"
            "  RETURN t.id AS id, t.name AS name, score\n"
            "  UNION ALL\n"
            f"  CALL db.index.fulltext.queryNodes('{parent_index}', $search_text)\n"
            "  YIELD node AS t, score\n"
            "  RETURN t.id AS id, t.name AS name, score\n"
            "}\n"
            "RETURN id, name, score\n"
            "ORDER BY score DESC\n"
            "LIMIT $limit"
        )
    else:
        cypher = (
            f"CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "YIELD node AS t, score\n"
            "RETURN t.id AS id, t.name AS name, score\n"
            "ORDER BY score DESC\n"
            "LIMIT $limit"
        )
    return cypher, {"search_text": search_text, "limit": limit}


def build_genes_by_ontology(
    *, ontology: str, term_ids: list[str],
    organism: str | None = None, limit: int = 25,
) -> tuple[str, dict]:
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    cfg = ONTOLOGY_CONFIG[ontology]
    label = cfg["label"]
    gene_rel = cfg["gene_rel"]
    hierarchy_rels = cfg["hierarchy_rels"]
    level_filter = cfg.get("gene_connects_to_level")

    level_clause = (
        f"\nWITH DISTINCT descendant\nWHERE descendant.level = '{level_filter}'"
        if level_filter else "\nWITH DISTINCT descendant"
    )

    if hierarchy_rels:
        hierarchy = "|".join(hierarchy_rels)
        expansion = f"MATCH (root)<-[:{hierarchy}*0..15]-(descendant)"
    else:
        expansion = "WITH root AS descendant"

    parent_label = cfg.get("parent_label")
    if parent_label:
        root_match = (
            f"MATCH (root) WHERE (root:{label} OR root:{parent_label})\n"
            f"  AND root.id IN $term_ids"
        )
    else:
        root_match = f"MATCH (root:{label}) WHERE root.id IN $term_ids"

    cypher = (
        f"{root_match}\n"
        f"{expansion}"
        f"{level_clause}\n"
        f"MATCH (g:Gene)-[:{gene_rel}]->(descendant)\n"
        "WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')\n"
        "       WHERE toLower(g.organism_strain) CONTAINS word))\n"
        "RETURN DISTINCT g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_strain AS organism_strain\n"
        "ORDER BY g.locus_tag\n"
        "LIMIT $limit"
    )
    return cypher, {
        "term_ids": term_ids, "organism": organism, "limit": limit,
    }


def build_gene_ontology_terms(
    *, ontology: str, gene_id: str, leaf_only: bool = True, limit: int = 50,
) -> tuple[str, dict]:
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    cfg = ONTOLOGY_CONFIG[ontology]
    label = cfg["label"]
    gene_rel = cfg["gene_rel"]
    hierarchy_rels = cfg["hierarchy_rels"]

    if leaf_only and hierarchy_rels:
        hierarchy = "|".join(hierarchy_rels)
        cypher = (
            f"MATCH (g:Gene {{locus_tag: $gene_id}})-[:{gene_rel}]->(t:{label})\n"
            "WHERE NOT EXISTS {\n"
            f"  MATCH (g)-[:{gene_rel}]->(child:{label})\n"
            f"        -[:{hierarchy}]->(t)\n"
            "}\n"
            "RETURN t.id AS id, t.name AS name\n"
            "ORDER BY t.name\n"
            "LIMIT $limit"
        )
    else:
        cypher = (
            f"MATCH (g:Gene {{locus_tag: $gene_id}})-[:{gene_rel}]->(t:{label})\n"
            "RETURN t.id AS id, t.name AS name\n"
            "ORDER BY t.name\n"
            "LIMIT $limit"
        )
    return cypher, {"gene_id": gene_id, "limit": limit}
