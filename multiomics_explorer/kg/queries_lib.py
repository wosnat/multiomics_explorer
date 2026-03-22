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
    min_quality: int = 0,
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
        "ORDER BY score DESC, g.locus_tag"
    )
    return cypher, {
        "search_text": search_text, "organism": organism,
        "category": category,
        "min_quality": min_quality,
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


def build_gene_overview(
    *, gene_ids: list[str],
) -> tuple[str, dict]:
    """Build query for gene overview: identity + data availability signals."""
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.gene_summary AS gene_summary,\n"
        "       g.gene_category AS gene_category, g.annotation_quality AS annotation_quality,\n"
        "       g.organism_strain AS organism_strain,\n"
        "       g.annotation_types AS annotation_types,\n"
        "       g.expression_edge_count AS expression_edge_count,\n"
        "       g.significant_expression_count AS significant_expression_count,\n"
        "       g.closest_ortholog_group_size AS closest_ortholog_group_size,\n"
        "       g.closest_ortholog_genera AS closest_ortholog_genera\n"
        "ORDER BY g.locus_tag"
    )
    return cypher, {"locus_tags": gene_ids}


def build_get_gene_details(*, gene_id: str) -> tuple[str, dict]:
    """Build query for full gene node properties."""
    cypher = (
        "MATCH (g:Gene {locus_tag: $gene_id})\n"
        "RETURN g {.*} AS gene"
    )
    return cypher, {"gene_id": gene_id}



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


def _list_publications_where(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
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

    if author:
        conditions.append(
            "ANY(a IN p.authors WHERE toLower(a) CONTAINS toLower($author))"
        )
        params["author"] = author

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
    return where_block, params


def build_list_publications(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build Cypher for listing publications with experiment summaries.

    RETURN keys (compact): doi, title, authors, year, journal, study_type,
    organisms, experiment_count, treatment_types, omics_types.
    When search_text is provided, also: score.
    RETURN keys (verbose): adds abstract, description.
    """
    where_block, params = _list_publications_where(
        organism=organism, treatment_type=treatment_type,
        search_text=search_text, author=author,
    )

    verbose_cols = (
        ",\n       p.abstract AS abstract, p.description AS description"
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
            "       p.omics_types AS omics_types,\n"
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
            f"       p.omics_types AS omics_types{verbose_cols}\n"
            f"ORDER BY p.publication_year DESC, p.title\n"
            f"{limit_clause}"
        )

    return cypher, params


def build_list_publications_summary(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for matching publications.

    RETURN keys: total_entries, total_matching.
    total_entries is the unfiltered count of all publications.
    total_matching is the count after applying filters.
    """
    where_block, params = _list_publications_where(
        organism=organism, treatment_type=treatment_type,
        search_text=search_text, author=author,
    )

    if search_text:
        cypher = (
            "CALL db.index.fulltext.queryNodes('publicationFullText', $search_text)\n"
            "YIELD node AS p, score\n"
            f"{where_block}"
            "WITH count(p) AS total_matching\n"
            "MATCH (p2:Publication)\n"
            "RETURN count(p2) AS total_entries, total_matching"
        )
    else:
        cypher = (
            "MATCH (p:Publication)\n"
            "WITH count(p) AS total_entries\n"
            "MATCH (p:Publication)\n"
            f"{where_block}"
            "RETURN total_entries, count(p) AS total_matching"
        )

    return cypher, params


def build_list_gene_categories() -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene) WHERE g.gene_category IS NOT NULL\n"
        "RETURN g.gene_category AS category, count(*) AS gene_count\n"
        "ORDER BY gene_count DESC"
    )
    return cypher, {}



def build_list_organisms(
    *,
    verbose: bool = False,
) -> tuple[str, dict]:
    """Build Cypher for listing all organisms with data-availability signals.

    RETURN keys (compact): organism_name, genus, species, strain, clade,
    ncbi_taxon_id, gene_count, publication_count, experiment_count,
    treatment_types, omics_types.
    RETURN keys (verbose): adds family, order, tax_class, phylum, kingdom,
    superkingdom, lineage.
    """
    verbose_cols = (
        ",\n       o.family AS family,"
        "\n       o.order AS order,"
        "\n       o.tax_class AS tax_class,"
        "\n       o.phylum AS phylum,"
        "\n       o.kingdom AS kingdom,"
        "\n       o.superkingdom AS superkingdom,"
        "\n       o.lineage AS lineage"
        if verbose else ""
    )

    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        "RETURN o.preferred_name AS organism_name,\n"
        "       o.genus AS genus,\n"
        "       o.species AS species,\n"
        "       o.strain_name AS strain,\n"
        "       o.clade AS clade,\n"
        "       o.ncbi_taxon_id AS ncbi_taxon_id,\n"
        "       o.gene_count AS gene_count,\n"
        "       o.publication_count AS publication_count,\n"
        "       o.experiment_count AS experiment_count,\n"
        "       o.treatment_types AS treatment_types,\n"
        "       o.omics_types AS omics_types"
        f"{verbose_cols}\n"
        "ORDER BY o.genus, o.preferred_name"
    )
    return cypher, {}


def build_search_ontology(
    *, ontology: str, search_text: str,
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
            "ORDER BY score DESC"
        )
    else:
        cypher = (
            f"CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "YIELD node AS t, score\n"
            "RETURN t.id AS id, t.name AS name, score\n"
            "ORDER BY score DESC"
        )
    return cypher, {"search_text": search_text}


def build_genes_by_ontology(
    *, ontology: str, term_ids: list[str],
    organism: str | None = None,
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
        "ORDER BY g.locus_tag"
    )
    return cypher, {
        "term_ids": term_ids, "organism": organism,
    }


def build_gene_ontology_terms(
    *, ontology: str, gene_id: str, leaf_only: bool = True,
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
            "ORDER BY t.name"
        )
    else:
        cypher = (
            f"MATCH (g:Gene {{locus_tag: $gene_id}})-[:{gene_rel}]->(t:{label})\n"
            "RETURN t.id AS id, t.name AS name\n"
            "ORDER BY t.name"
        )
    return cypher, {"gene_id": gene_id}
