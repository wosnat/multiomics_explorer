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
        "    toLower(g.locus_tag) = toLower($identifier)\n"
        "    OR toLower(g.gene_name) = toLower($identifier)\n"
        "    OR ANY(id IN g.all_identifiers WHERE toLower(id) = toLower($identifier))\n"
        "  )\n"
        "  AND ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_strain) CONTAINS word))\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_strain AS organism_strain\n"
        "ORDER BY g.organism_strain, g.locus_tag"
    )
    return cypher, {"identifier": identifier, "organism": organism}


def _genes_by_function_filter_clause() -> str:
    """Return the shared WHERE filter expression for genes_by_function builders."""
    return (
        "($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_strain) CONTAINS word))\n"
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

    Uses conditional counting to compute total_entries (before filters)
    and total_matching (after filters) in a single fulltext pass.

    RETURN keys: total_entries, total_matching, by_organism, by_category,
    score_max, score_median.
    """
    filt = _genes_by_function_filter_clause()
    cypher = (
        "CALL db.index.fulltext.queryNodes('geneFullText', $search_text)\n"
        "YIELD node AS g, score\n"
        f"WITH g, score,\n"
        f"     CASE WHEN {filt}\n"
        "     THEN 1 ELSE 0 END AS matches\n"
        "WITH count(g) AS total_entries,\n"
        "     sum(matches) AS total_matching,\n"
        "     max(CASE WHEN matches = 1 THEN score END) AS score_max,\n"
        "     percentileDisc(\n"
        "       CASE WHEN matches = 1 THEN score END, 0.5\n"
        "     ) AS score_median,\n"
        "     [x IN collect(\n"
        "       CASE WHEN matches = 1 THEN g.organism_strain END\n"
        "     ) WHERE x IS NOT NULL] AS organisms,\n"
        "     [x IN collect(\n"
        "       CASE WHEN matches = 1 THEN g.gene_category END\n"
        "     ) WHERE x IS NOT NULL] AS categories\n"
        "RETURN total_entries, total_matching, score_max, score_median,\n"
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
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_function.

    RETURN keys (compact): locus_tag, gene_name, product,
    organism_strain, gene_category, annotation_quality, score.
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
        "       g.product AS product, g.organism_strain AS organism_strain,\n"
        "       g.gene_category AS gene_category,\n"
        f"       g.annotation_quality AS annotation_quality, score{verbose_cols}\n"
        f"ORDER BY score DESC, g.locus_tag{limit_clause}"
    )
    return cypher, params


def build_gene_overview_summary(
    *,
    locus_tags: list[str],
) -> tuple[str, dict]:
    """Build summary + not_found for gene_overview.

    RETURN keys: total_matching, by_organism, by_category,
    by_annotation_type, has_expression, has_significant_expression,
    has_orthologs, not_found.
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
        "     [g IN found | g.organism_strain] AS orgs,\n"
        "     [g IN found | g.gene_category] AS cats,\n"
        "     apoc.coll.flatten([g IN found | g.annotation_types]) AS all_atypes\n"
        "RETURN total_matching,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(cats) AS by_category,\n"
        "       apoc.coll.frequencies(all_atypes) AS by_annotation_type,\n"
        "       size([g IN found WHERE g.expression_edge_count > 0]) AS has_expression,\n"
        "       size([g IN found WHERE (g.significant_up_count + g.significant_down_count) > 0]) AS has_significant_expression,\n"
        "       size([g IN found WHERE g.closest_ortholog_group_size > 0]) AS has_orthologs,\n"
        "       not_found"
    )
    return cypher, {"locus_tags": locus_tags}


def build_gene_overview(
    *,
    locus_tags: list[str],
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_overview.

    RETURN keys (compact): locus_tag, gene_name, product, gene_category,
    annotation_quality, organism_strain, annotation_types,
    expression_edge_count, significant_up_count, significant_down_count,
    closest_ortholog_group_size, closest_ortholog_genera.
    RETURN keys (verbose): adds gene_summary, function_description,
    all_identifiers.
    """
    params: dict = {"locus_tags": locus_tags}

    verbose_cols = (
        ",\n       g.gene_summary AS gene_summary"
        ",\n       g.function_description AS function_description"
        ",\n       g.all_identifiers AS all_identifiers"
        if verbose else ""
    )

    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.gene_category AS gene_category,\n"
        "       g.annotation_quality AS annotation_quality,\n"
        "       g.organism_strain AS organism_strain,\n"
        "       g.annotation_types AS annotation_types,\n"
        "       g.expression_edge_count AS expression_edge_count,\n"
        "       g.significant_up_count AS significant_up_count,\n"
        "       g.significant_down_count AS significant_down_count,\n"
        "       g.closest_ortholog_group_size AS closest_ortholog_group_size,\n"
        f"       g.closest_ortholog_genera AS closest_ortholog_genera{verbose_cols}\n"
        f"ORDER BY g.locus_tag{limit_clause}"
    )
    return cypher, params


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


def _gene_homologs_og_where(
    *,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
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
    return conditions, params


def build_gene_homologs_summary(
    *,
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
) -> tuple[str, dict]:
    """Build summary + not_found/no_groups for gene_homologs.

    RETURN keys: total_matching, by_organism, by_source, not_found, no_groups.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
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
        "  [row IN collect({org: CASE WHEN size(groups) > 0 THEN g.organism_strain END,\n"
        "                    srcs: [x IN groups | x.source]})\n"
        "   WHERE row.org IS NOT NULL] AS matched\n"
        "UNWIND CASE WHEN size(matched) = 0 THEN [null] ELSE matched END AS m\n"
        "WITH nf_raw, ng_raw,\n"
        "     [x IN collect(m.org) WHERE x IS NOT NULL] AS orgs,\n"
        "     apoc.coll.flatten([x IN collect(m.srcs) WHERE x IS NOT NULL]) AS sources\n"
        "RETURN size(sources) AS total_matching,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(sources) AS by_source,\n"
        "       [x IN nf_raw WHERE x IS NOT NULL] AS not_found,\n"
        "       [x IN ng_raw WHERE x IS NOT NULL] AS no_groups"
    )
    return cypher, params


def build_gene_homologs(
    *,
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_homologs.

    RETURN keys (compact): locus_tag, organism_strain, group_id,
    consensus_gene_name, consensus_product, taxonomic_level, source,
    specificity_rank.
    RETURN keys (verbose): adds member_count, organism_count, genera,
    has_cross_genus_members, description, functional_description.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
    )
    params["locus_tags"] = locus_tags

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = (
        ",\n       og.member_count AS member_count"
        ",\n       og.organism_count AS organism_count"
        ",\n       og.genera AS genera"
        ",\n       og.has_cross_genus_members AS has_cross_genus_members"
        ",\n       og.description AS description"
        ",\n       og.functional_description AS functional_description"
        if verbose else ""
    )

    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag, g.organism_strain AS organism_strain,\n"
        "       og.id AS group_id,\n"
        "       og.consensus_gene_name AS consensus_gene_name,\n"
        "       og.consensus_product AS consensus_product,\n"
        "       og.taxonomic_level AS taxonomic_level, og.source AS source,\n"
        f"       og.specificity_rank AS specificity_rank{verbose_cols}\n"
        f"ORDER BY g.locus_tag, og.specificity_rank, og.source{limit_clause}"
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
            "(ALL(word IN split(toLower($org), ' ')"
            " WHERE toLower(e.organism_strain) CONTAINS word)"
            " OR ALL(word IN split(toLower($org), ' ')"
            " WHERE toLower(e.coculture_partner) CONTAINS word))"
        )
        params["org"] = organism

    if treatment_type:
        conditions.append("toLower(e.treatment_type) IN $treatment_types")
        params["treatment_types"] = [t.lower() for t in treatment_type]

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
        conditions.append("e.is_time_course = 'true'")

    if table_scope:
        conditions.append("e.table_scope IN $table_scopes")
        params["table_scopes"] = table_scope

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
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build Cypher for listing experiments with precomputed gene count stats.

    RETURN keys (compact): experiment_id, experiment_name, publication_doi,
    organism_strain, treatment_type, coculture_partner, omics_type,
    is_time_course, table_scope, table_scope_detail,
    gene_count, significant_up_count, significant_down_count,
    time_point_count, time_point_labels, time_point_orders, time_point_hours,
    time_point_totals, time_point_significant_up, time_point_significant_down.
    RETURN keys (verbose): adds publication_title, treatment,
    control, light_condition, light_intensity, medium, temperature,
    statistical_test, experimental_context.
    RETURN keys (search_text): adds score.
    """
    where_block, params = _list_experiments_where(
        organism=organism, treatment_type=treatment_type,
        omics_type=omics_type, publication_doi=publication_doi,
        coculture_partner=coculture_partner, search_text=search_text,
        time_course_only=time_course_only, table_scope=table_scope,
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
        "\n       e.experimental_context AS experimental_context"
        if verbose else ""
    )

    if limit is not None:
        limit_clause = "LIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    return_cols = (
        "e.id AS experiment_id,\n"
        "       e.name AS experiment_name,\n"
        "       p.doi AS publication_doi,\n"
        "       e.organism_strain AS organism_strain,\n"
        "       e.treatment_type AS treatment_type,\n"
        "       e.coculture_partner AS coculture_partner,\n"
        "       e.omics_type AS omics_type,\n"
        "       e.is_time_course AS is_time_course,\n"
        "       e.table_scope AS table_scope,\n"
        "       e.table_scope_detail AS table_scope_detail,\n"
        "       e.gene_count AS gene_count,\n"
        "       e.significant_up_count AS significant_up_count,\n"
        "       e.significant_down_count AS significant_down_count,\n"
        "       e.time_point_count AS time_point_count,\n"
        "       e.time_point_labels AS time_point_labels,\n"
        "       e.time_point_orders AS time_point_orders,\n"
        "       e.time_point_hours AS time_point_hours,\n"
        "       e.time_point_totals AS time_point_totals,\n"
        "       e.time_point_significant_up AS time_point_significant_up,\n"
        "       e.time_point_significant_down AS time_point_significant_down"
    )

    if search_text:
        cypher = (
            "CALL db.index.fulltext.queryNodes('experimentFullText', $search_text)\n"
            "YIELD node AS e, score\n"
            "MATCH (p:Publication)-[:Has_experiment]->(e)\n"
            f"{where_block}"
            f"RETURN {return_cols},\n"
            f"       score{verbose_cols}\n"
            f"ORDER BY score DESC, e.organism_strain, e.name\n"
            f"{limit_clause}"
        )
    else:
        cypher = (
            "MATCH (p:Publication)-[:Has_experiment]->(e:Experiment)\n"
            f"{where_block}"
            f"RETURN {return_cols}{verbose_cols}\n"
            f"ORDER BY p.publication_year DESC, e.organism_strain, e.name\n"
            f"{limit_clause}"
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
) -> tuple[str, dict]:
    """Build summary aggregation Cypher for list_experiments.

    Returns breakdowns by organism, treatment type, omics type,
    publication, and table_scope using apoc.coll.frequencies.

    RETURN keys: total_matching, time_course_count, by_organism,
    by_treatment_type, by_omics_type, by_publication, by_table_scope.
    RETURN keys (search_text): adds score_max, score_median.
    """
    where_block, params = _list_experiments_where(
        organism=organism, treatment_type=treatment_type,
        omics_type=omics_type, publication_doi=publication_doi,
        coculture_partner=coculture_partner, search_text=search_text,
        time_course_only=time_course_only, table_scope=table_scope,
    )

    collect_cols = (
        "collect(e.organism_strain) AS orgs,\n"
        "     collect(e.treatment_type) AS tts,\n"
        "     collect(e.omics_type) AS omics,\n"
        "     collect(p.doi) AS dois,\n"
        "     collect(e.is_time_course) AS tc,\n"
        "     collect(e.table_scope) AS scopes"
    )

    return_cols = (
        "size(orgs) AS total_matching,\n"
        "       size([x IN tc WHERE x = 'true']) AS time_course_count,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(tts) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(omics) AS by_omics_type,\n"
        "       apoc.coll.frequencies(dois) AS by_publication,\n"
        "       apoc.coll.frequencies(scopes) AS by_table_scope"
    )

    if search_text:
        cypher = (
            "CALL db.index.fulltext.queryNodes('experimentFullText', $search_text)\n"
            "YIELD node AS e, score\n"
            "MATCH (p:Publication)-[:Has_experiment]->(e)\n"
            f"{where_block}"
            f"WITH {collect_cols},\n"
            "     collect(score) AS scores\n"
            f"RETURN {return_cols},\n"
            "       apoc.coll.max(scores) AS score_max,\n"
            "       apoc.coll.sort(scores)[size(scores)/2] AS score_median"
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


def build_search_ontology_summary(
    *, ontology: str, search_text: str,
) -> tuple[str, dict]:
    """Build summary Cypher for search_ontology.

    RETURN keys: total_entries, total_matching, score_max, score_median.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    cfg = ONTOLOGY_CONFIG[ontology]
    index_name = cfg["fulltext_index"]
    parent_index = cfg.get("parent_fulltext_index")

    if parent_index:
        cypher = (
            "CALL {\n"
            f"  CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "  YIELD node AS t, score\n"
            "  RETURN score\n"
            "  UNION ALL\n"
            f"  CALL db.index.fulltext.queryNodes('{parent_index}', $search_text)\n"
            "  YIELD node AS t, score\n"
            "  RETURN score\n"
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
        label = cfg["label"]
        cypher = (
            f"CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "YIELD node AS t, score\n"
            "WITH count(t) AS total_matching,\n"
            "     max(score) AS score_max,\n"
            "     percentileDisc(score, 0.5) AS score_median\n"
            f"CALL {{ MATCH (all_t:{label}) RETURN count(all_t) AS total_entries }}\n"
            "RETURN total_entries, total_matching, score_max, score_median"
        )
    return cypher, {"search_text": search_text}


def build_search_ontology(
    *, ontology: str, search_text: str,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build Cypher for search_ontology.

    RETURN keys: id, name, score.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    cfg = ONTOLOGY_CONFIG[ontology]
    index_name = cfg["fulltext_index"]
    parent_index = cfg.get("parent_fulltext_index")

    limit_clause = "\nLIMIT $limit" if limit is not None else ""

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
            "ORDER BY score DESC" + limit_clause
        )
    else:
        cypher = (
            f"CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "YIELD node AS t, score\n"
            "RETURN t.id AS id, t.name AS name, score\n"
            "ORDER BY score DESC" + limit_clause
        )
    params: dict = {"search_text": search_text}
    if limit is not None:
        params["limit"] = limit
    return cypher, params


def _genes_by_ontology_cfg(ontology: str) -> dict:
    """Validate ontology and return ONTOLOGY_CONFIG entry + derived clauses."""
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    cfg = ONTOLOGY_CONFIG[ontology]
    label = cfg["label"]
    gene_rel = cfg["gene_rel"]
    hierarchy_rels = cfg["hierarchy_rels"]
    level_filter = cfg.get("gene_connects_to_level")
    parent_label = cfg.get("parent_label")

    level_clause = (
        f"\nWITH DISTINCT descendant\nWHERE descendant.level = '{level_filter}'"
        if level_filter else "\nWITH DISTINCT descendant"
    )
    # Variant that preserves tid for UNWIND-based queries (summary + verbose)
    level_clause_tid = (
        f"\nWITH DISTINCT descendant, tid\nWHERE descendant.level = '{level_filter}'"
        if level_filter else "\nWITH DISTINCT descendant, tid"
    )

    if hierarchy_rels:
        hierarchy = "|".join(hierarchy_rels)
        expansion = f"MATCH (root)<-[:{hierarchy}*0..15]-(descendant)"
    else:
        expansion = "WITH root AS descendant"

    # Per-tid root match (for UNWIND-based queries: verbose + summary)
    if parent_label:
        per_tid_root = (
            f"MATCH (root) WHERE (root:{label} OR root:{parent_label})\n"
            "  AND root.id = tid"
        )
    else:
        per_tid_root = f"MATCH (root:{label}) WHERE root.id = tid"

    # Batch root match (for compact detail query)
    if parent_label:
        batch_root = (
            f"MATCH (root) WHERE (root:{label} OR root:{parent_label})\n"
            f"  AND root.id IN $term_ids"
        )
    else:
        batch_root = f"MATCH (root:{label}) WHERE root.id IN $term_ids"

    return {
        "gene_rel": gene_rel,
        "expansion": expansion,
        "level_clause": level_clause,
        "level_clause_tid": level_clause_tid,
        "per_tid_root": per_tid_root,
        "batch_root": batch_root,
    }


def build_genes_by_ontology_summary(
    *,
    ontology: str,
    term_ids: list[str],
    organism: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_ontology.

    RETURN keys: total_matching, by_organism, by_category, by_term.
    """
    c = _genes_by_ontology_cfg(ontology)

    cypher = (
        "UNWIND $term_ids AS tid\n"
        f"{c['per_tid_root']}\n"
        f"{c['expansion']}"
        f"{c['level_clause_tid']}\n"
        f"MATCH (g:Gene)-[:{c['gene_rel']}]->(descendant)\n"
        "WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')\n"
        "       WHERE toLower(g.organism_strain) CONTAINS word))\n"
        "WITH DISTINCT tid AS root_tid, g.locus_tag AS lt, g.organism_strain AS org,\n"
        "     coalesce(g.gene_category, 'Unknown') AS cat\n"
        "WITH collect({lt: lt, org: org, cat: cat, tid: root_tid}) AS rows\n"
        "WITH rows,\n"
        "     size(apoc.coll.toSet([r IN rows | r.lt])) AS total_matching,\n"
        "     apoc.coll.frequencies([r IN rows | r.tid]) AS by_term\n"
        "WITH total_matching, by_term, rows,\n"
        "     apoc.coll.toSet([r IN rows | r.lt]) AS unique_lts\n"
        "UNWIND unique_lts AS lt\n"
        "WITH total_matching, by_term,\n"
        "     [r IN rows WHERE r.lt = lt][0] AS rep\n"
        "WITH total_matching, by_term,\n"
        "     collect(rep.org) AS orgs, collect(rep.cat) AS cats\n"
        "RETURN total_matching, by_term,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(cats) AS by_category"
    )
    return cypher, {"term_ids": term_ids, "organism": organism}


def build_genes_by_ontology(
    *,
    ontology: str,
    term_ids: list[str],
    organism: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_ontology.

    RETURN keys (compact): locus_tag, gene_name, product,
    organism_strain, gene_category.
    RETURN keys (verbose): adds matched_terms, gene_summary,
    function_description.
    """
    c = _genes_by_ontology_cfg(ontology)

    params: dict = {"term_ids": term_ids, "organism": organism}
    limit_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit

    if verbose:
        cypher = (
            "UNWIND $term_ids AS tid\n"
            f"{c['per_tid_root']}\n"
            f"{c['expansion']}"
            f"{c['level_clause_tid']}\n"
            f"MATCH (g:Gene)-[:{c['gene_rel']}]->(descendant)\n"
            "WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')\n"
            "       WHERE toLower(g.organism_strain) CONTAINS word))\n"
            "WITH DISTINCT tid, g\n"
            "WITH g, collect(DISTINCT tid) AS matched_terms\n"
            "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
            "       g.product AS product, g.organism_strain AS organism_strain,\n"
            "       g.gene_category AS gene_category,\n"
            "       matched_terms,\n"
            "       g.gene_summary AS gene_summary,\n"
            "       g.function_description AS function_description\n"
            "ORDER BY g.organism_strain, g.locus_tag" + limit_clause
        )
    else:
        cypher = (
            f"{c['batch_root']}\n"
            f"{c['expansion']}"
            f"{c['level_clause']}\n"
            f"MATCH (g:Gene)-[:{c['gene_rel']}]->(descendant)\n"
            "WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')\n"
            "       WHERE toLower(g.organism_strain) CONTAINS word))\n"
            "RETURN DISTINCT g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
            "       g.product AS product, g.organism_strain AS organism_strain,\n"
            "       g.gene_category AS gene_category\n"
            "ORDER BY g.organism_strain, g.locus_tag" + limit_clause
        )

    return cypher, params


def _gene_ontology_terms_leaf_filter(cfg: dict) -> str:
    """Return a WHERE NOT EXISTS clause for leaf filtering, or empty string.

    Leaf filtering is meaningful only when genes can be annotated to both
    a child and its ancestor within the same label. Skipped for:
    - Flat ontologies (no hierarchy_rels): cog_category, tigr_role
    - Cross-label hierarchies (parent_label present): pfam (Pfam→PfamClan)
    - Level-restricted ontologies (gene_connects_to_level): kegg (ko only)
    """
    hierarchy_rels = cfg["hierarchy_rels"]
    if not hierarchy_rels:
        return ""
    if cfg.get("parent_label"):
        return ""
    if cfg.get("gene_connects_to_level"):
        return ""
    gene_rel = cfg["gene_rel"]
    label = cfg["label"]
    hierarchy = "|".join(hierarchy_rels)
    return (
        "WHERE NOT EXISTS {\n"
        f"  MATCH (g)-[:{gene_rel}]->(child:{label})\n"
        f"        -[:{hierarchy}]->(t)\n"
        "}\n"
    )


def build_gene_ontology_terms_summary(
    *,
    locus_tags: list[str],
    ontology: str,
) -> tuple[str, dict]:
    """Build summary for gene_ontology_terms for ONE ontology.

    Called once per ontology by api/ layer (which merges results
    and adds not_found, no_terms, totals).

    RETURN keys: gene_count, term_count, by_term, gene_term_counts.
    gene_term_counts is [{locus_tag, term_count}] — has per-gene identity
    so api/ can merge across ontologies for cross-ontology stats.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    cfg = ONTOLOGY_CONFIG[ontology]
    gene_rel = cfg["gene_rel"]
    label = cfg["label"]
    leaf_filter = _gene_ontology_terms_leaf_filter(cfg)

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        f"MATCH (g:Gene {{locus_tag: lt}})-[:{gene_rel}]->(t:{label})\n"
        f"{leaf_filter}"
        "WITH g.locus_tag AS lt, collect({id: t.id, name: t.name}) AS terms\n"
        "WITH collect({lt: lt, cnt: size(terms), terms: terms}) AS genes\n"
        "WITH genes,\n"
        "     apoc.coll.flatten([g IN genes | g.terms]) AS all_terms,\n"
        "     [g IN genes | {locus_tag: g.lt, term_count: g.cnt}] AS gene_term_counts\n"
        "UNWIND all_terms AS t\n"
        "WITH genes, gene_term_counts, t.id AS tid, t.name AS tname, count(*) AS cnt\n"
        "WITH genes, gene_term_counts,\n"
        "     collect({term_id: tid, term_name: tname, count: cnt}) AS by_term\n"
        "RETURN size(genes) AS gene_count,\n"
        "       size(apoc.coll.flatten([g IN genes | g.terms])) AS term_count,\n"
        "       by_term,\n"
        "       gene_term_counts"
    )
    return cypher, {"locus_tags": locus_tags}


def build_gene_ontology_terms(
    *,
    locus_tags: list[str],
    ontology: str,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_ontology_terms for ONE ontology.

    RETURN keys (compact): locus_tag, term_id, term_name.
    RETURN keys (verbose): adds organism_strain.

    Called by api/ — which adds ontology_type column and merges
    across ontologies when ontology=None.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    cfg = ONTOLOGY_CONFIG[ontology]
    gene_rel = cfg["gene_rel"]
    label = cfg["label"]
    leaf_filter = _gene_ontology_terms_leaf_filter(cfg)

    params: dict = {"locus_tags": locus_tags}

    verbose_cols = (
        ",\n       g.organism_strain AS organism_strain"
        if verbose else ""
    )

    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        f"MATCH (g:Gene {{locus_tag: lt}})-[:{gene_rel}]->(t:{label})\n"
        f"{leaf_filter}"
        "RETURN g.locus_tag AS locus_tag, t.id AS term_id,\n"
        f"       t.name AS term_name{verbose_cols}\n"
        f"ORDER BY g.locus_tag, t.id{limit_clause}"
    )
    return cypher, params


def build_gene_existence_check() -> tuple[str, dict]:
    """Build query to check which locus_tags exist in the KG.

    RETURN keys: lt, found.
    Pass locus_tags as parameter when executing.
    """
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "RETURN lt, g IS NOT NULL AS found"
    )
    return cypher, {}


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
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params shared by all de_by_gene builders.

    direction takes precedence over significant_only (direction implies
    significance). organism uses fuzzy word-based matching (same as
    list_experiments).
    """
    conditions: list[str] = []
    params: dict = {}
    if organism:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(e.organism_strain) CONTAINS word)"
        )
        params["organism"] = organism
    if locus_tags:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if experiment_ids:
        conditions.append("e.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    if direction == "up":
        conditions.append('r.expression_status = "significant_up"')
    elif direction == "down":
        conditions.append('r.expression_status = "significant_down"')
    elif significant_only:
        conditions.append('r.expression_status <> "not_significant"')
    return conditions, params


# ---------------------------------------------------------------------------
# Organism pre-validation builders (differential expression)
# ---------------------------------------------------------------------------


def build_resolve_organism_for_organism(
    *, organism: str,
) -> tuple[str, dict]:
    """Resolve distinct organism_strain values for a fuzzy organism name.

    RETURN keys: organisms (list[str]).
    Uses the same word-based CONTAINS matching as list_experiments.
    """
    cypher = (
        "MATCH (e:Experiment)-[:Changes_expression_of]->()\n"
        "WHERE ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(e.organism_strain) CONTAINS word)\n"
        "RETURN collect(DISTINCT e.organism_strain) AS organisms"
    )
    return cypher, {"organism": organism}


def build_resolve_organism_for_locus_tags(
    *, locus_tags: list[str],
) -> tuple[str, dict]:
    """Resolve distinct organism_strain values for a list of locus_tags.

    RETURN keys: organisms (list[str]).
    """
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})\n"
        "RETURN collect(DISTINCT g.organism_strain) AS organisms"
    )
    return cypher, {"locus_tags": locus_tags}


def build_resolve_organism_for_experiments(
    *, experiment_ids: list[str],
) -> tuple[str, dict]:
    """Resolve distinct organism_strain values for a list of experiment IDs.

    RETURN keys: organisms (list[str]).
    """
    cypher = (
        "UNWIND $experiment_ids AS eid\n"
        "MATCH (e:Experiment {id: eid})\n"
        "RETURN collect(DISTINCT e.organism_strain) AS organisms"
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
) -> tuple[str, dict]:
    """Global aggregate stats for differential_expression_by_gene.

    RETURN keys: total_rows, matching_genes, rows_by_status,
    rows_by_treatment_type, by_table_scope, median_abs_log2fc, max_abs_log2fc.
    rows_by_status = apoc list [{item, count}] — api/ converts to dict.
    rows_by_treatment_type = apoc list [{item, count}] — api/ converts to dict.
    by_table_scope = apoc list [{item, count}] — api/ converts to dict.
    """
    conditions, params = _differential_expression_where(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=experiment_ids, direction=direction,
        significant_only=significant_only,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
        f"{where_block}"
        "RETURN count(*) AS total_rows,\n"
        "       count(DISTINCT g.locus_tag) AS matching_genes,\n"
        "       apoc.coll.frequencies(collect(r.expression_status)) AS rows_by_status,\n"
        "       apoc.coll.frequencies(collect(e.treatment_type)) AS rows_by_treatment_type,\n"
        "       apoc.coll.frequencies(collect(e.table_scope)) AS by_table_scope,\n"
        "       percentileCont(\n"
        '           CASE WHEN r.expression_status <> "not_significant"\n'
        "                THEN abs(r.log2_fold_change) ELSE null END, 0.5\n"
        "       ) AS median_abs_log2fc,\n"
        '       max(CASE WHEN r.expression_status <> "not_significant"\n'
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
) -> tuple[str, dict]:
    """Per-experiment breakdown with nested timepoints (single organism enforced).

    RETURN keys: organism_strain, experiments.
    experiments: list of dicts, each with nested timepoints.
    rows_by_status at both experiment and timepoint level (APOC list format).
    is_time_course included per experiment so api/ can null-out timepoints.
    """
    conditions, params = _differential_expression_where(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=experiment_ids, direction=direction,
        significant_only=significant_only,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
        f"{where_block}"
        "WITH e, r.time_point AS tp, r.time_point_order AS tpo,"
        " r.time_point_hours AS tph,\n"
        "     collect(DISTINCT g.locus_tag) AS tp_genes,\n"
        "     collect(r.expression_status) AS tp_calls\n"
        "WITH e,\n"
        "     size(apoc.coll.toSet(apoc.coll.flatten(collect(tp_genes))))"
        " AS matching_genes,\n"
        "     apoc.coll.frequencies(apoc.coll.flatten(collect(tp_calls)))"
        " AS rows_by_status,\n"
        "     collect({timepoint: tp, timepoint_hours: tph,"
        " timepoint_order: tpo,\n"
        "              matching_genes: size(tp_genes),\n"
        "              rows_by_status: apoc.coll.frequencies(tp_calls)})"
        " AS timepoints\n"
        "WITH collect({experiment_id: e.id, experiment_name: e.name,\n"
        "              treatment_type: e.treatment_type,"
        " omics_type: e.omics_type,\n"
        "              coculture_partner: e.coculture_partner,\n"
        "              is_time_course: e.is_time_course,\n"
        "              table_scope: e.table_scope,\n"
        "              table_scope_detail: e.table_scope_detail,\n"
        "              matching_genes: matching_genes,\n"
        "              rows_by_status: rows_by_status,\n"
        "              timepoints: timepoints}) AS experiments,\n"
        "     e.organism_strain AS organism_strain\n"
        "RETURN organism_strain, experiments"
    )
    return cypher, params


def build_differential_expression_by_gene_summary_diagnostics(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
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
            significant_only=significant_only,
        )
        where_block = (
            "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
        )
        cypher = (
            "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
            f"{where_block}"
            "WITH g.gene_category AS category,\n"
            "     count(DISTINCT g.locus_tag) AS total_genes,\n"
            '     count(DISTINCT CASE WHEN r.expression_status <> "not_significant"\n'
            "                         THEN g.locus_tag END) AS significant_genes\n"
            "ORDER BY significant_genes DESC\n"
            "RETURN [] AS not_found, [] AS no_expression,\n"
            "       collect({category: category, total_genes: total_genes,\n"
            "                significant_genes: significant_genes})[0..5]"
            " AS top_categories"
        )
        return cypher, params

    # Batch diagnostics: UNWIND locus_tags for not_found/no_expression
    # Use where_block WITHOUT locus_tags condition (already applied via UNWIND)
    conditions_no_lt, params = _differential_expression_where(
        organism=organism, locus_tags=None,
        experiment_ids=experiment_ids, direction=direction,
        significant_only=significant_only,
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
        '     count(DISTINCT CASE WHEN r.expression_status <> "not_significant"\n'
        "                         THEN g.locus_tag END) AS significant_genes\n"
        "ORDER BY significant_genes DESC\n"
        "RETURN not_found, no_expression,\n"
        "       collect({category: category, total_genes: total_genes,\n"
        "                significant_genes: significant_genes})[0..5]"
        " AS top_categories"
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
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for differential_expression_by_gene.

    RETURN keys (compact — 11): locus_tag, gene_name,
    experiment_id, treatment_type, timepoint, timepoint_hours, timepoint_order,
    log2fc, padj, rank, expression_status.
    RETURN keys (verbose): adds product, experiment_name, treatment,
    gene_category, omics_type, coculture_partner, table_scope,
    table_scope_detail.
    """
    conditions, params = _differential_expression_where(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=experiment_ids, direction=direction,
        significant_only=significant_only,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = (
        ",\n       g.function_description AS product"
        ",\n       e.name AS experiment_name"
        ",\n       e.treatment AS treatment"
        ",\n       g.gene_category AS gene_category"
        ",\n       e.omics_type AS omics_type"
        ",\n       e.coculture_partner AS coculture_partner"
        ",\n       e.table_scope AS table_scope"
        ",\n       e.table_scope_detail AS table_scope_detail"
        if verbose else ""
    )

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
        "       r.expression_status AS expression_status"
        f"{verbose_cols}\n"
        "ORDER BY ABS(r.log2_fold_change) DESC, g.locus_tag ASC,"
        " e.id ASC, r.time_point_order ASC"
        f"{limit_clause}"
    )
    return cypher, params


def build_search_homolog_groups_summary(
    *,
    search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for search_homolog_groups.

    RETURN keys: total_entries, total_matching, score_max, score_median,
    by_source, by_level.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
    )
    params["search_text"] = search_text

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "CALL db.index.fulltext.queryNodes('orthologGroupFullText', $search_text)\n"
        "YIELD node AS og, score\n"
        f"{where_block}"
        "WITH collect(og.source) AS sources,\n"
        "     collect(og.taxonomic_level) AS levels,\n"
        "     count(og) AS total_matching,\n"
        "     max(score) AS score_max,\n"
        "     percentileDisc(score, 0.5) AS score_median\n"
        "CALL { MATCH (all_og:OrthologGroup) RETURN count(all_og) AS total_entries }\n"
        "RETURN total_entries, total_matching, score_max, score_median,\n"
        "       apoc.coll.frequencies(sources) AS by_source,\n"
        "       apoc.coll.frequencies(levels) AS by_level"
    )
    return cypher, params


def build_search_homolog_groups(
    *,
    search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build Cypher for search_homolog_groups.

    RETURN keys (compact): group_id, group_name, consensus_gene_name,
    consensus_product, source, taxonomic_level, specificity_rank,
    member_count, organism_count, score.
    RETURN keys (verbose): adds description, functional_description,
    genera, has_cross_genus_members.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
    )
    params["search_text"] = search_text

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = (
        ",\n       og.description AS description"
        ",\n       og.functional_description AS functional_description"
        ",\n       og.genera AS genera"
        ",\n       og.has_cross_genus_members AS has_cross_genus_members"
        if verbose else ""
    )

    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

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
        f"       score{verbose_cols}\n"
        f"ORDER BY score DESC, og.specificity_rank, og.source{limit_clause}"
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
        "             WHERE toLower(g.organism_strain) CONTAINS word)))\n"
        "WITH gid, og, g\n"
        "WITH collect(DISTINCT CASE WHEN og IS NULL THEN gid END) AS nf_groups_raw,\n"
        "     collect(DISTINCT CASE WHEN og IS NOT NULL AND g IS NULL\n"
        "             THEN gid END) AS nm_groups_raw,\n"
        "     collect(CASE WHEN g IS NOT NULL THEN\n"
        "       {lt: g.locus_tag, org: g.organism_strain,\n"
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
        "          WHERE toLower(g_any.organism_strain) CONTAINS word)\n"
        "WITH org_input, count(g_any) AS kg_count\n"
        "OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        "WHERE org_input IS NOT NULL AND kg_count > 0\n"
        "  AND og.id IN $group_ids\n"
        "  AND ALL(word IN split(toLower(org_input), ' ')\n"
        "          WHERE toLower(g.organism_strain) CONTAINS word)\n"
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
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_homolog_group.

    RETURN keys (compact): locus_tag, gene_name, product,
    organism_strain, gene_category, group_id.
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
        "             WHERE toLower(g.organism_strain) CONTAINS word)))\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_strain AS organism_strain,\n"
        f"       g.gene_category AS gene_category, og.id AS group_id{verbose_cols}\n"
        f"ORDER BY og.id, g.organism_strain, g.locus_tag{limit_clause}"
    )
    return cypher, params