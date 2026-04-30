"""Shared query builders for MCP tools, CLI, and tests.

Each builder returns a (cypher, params) tuple. The caller is responsible
for executing the query via GraphConnection.execute_query(cypher, **params).
"""

from typing import Literal

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
    "brite": {
        "label": "BriteCategory",
        "gene_rel": "Gene_has_kegg_ko",
        "hierarchy_rels": ["Brite_category_is_a_brite_category"],
        "fulltext_index": "briteCategoryFullText",
        "bridge": {
            "node_label": "KeggTerm",
            "edge": "Kegg_term_in_brite_category",
        },
    },
}

def _hierarchy_walk(
    ontology: str,
    direction: Literal["up", "down"],
    root_label: str | None = None,
) -> dict:
    """Return Cypher fragments for ontology hierarchy walks.

    Consumed by genes_by_ontology builders and (post-refactor)
    ontology_landscape. Dispatches on ONTOLOGY_CONFIG + known special
    cases (Pfam cross-label, flat ontologies).

    Args:
        ontology: one of ALL_ONTOLOGIES.
        direction: 'up' = gene → leaf → ancestor at target level.
                   'down' = root-at-input → descendants → genes.
        root_label: used only when ontology='pfam' + direction='down';
                    distinguishes Pfam root (no walk) vs PfamClan root
                    (walk down via Pfam_in_pfam_clan).

    Returns:
        dict with keys:
          - leaf_label: str — label for the gene-bound node.
          - gene_rel: str — relationship from Gene to leaf.
          - rel_union: str — '|'.join(hierarchy_rels) (empty for flat).
          - bind_up: str — Cypher for gene→leaf binding (direction=up).
          - walk_up: str — Cypher for leaf→ancestor walk (direction=up).
          - walk_down: str — Cypher for root→leaf walk (direction=down).
    """
    if direction not in ("up", "down"):
        raise ValueError(
            f"direction must be 'up' or 'down', got '{direction}'"
        )
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(
            f"Invalid ontology '{ontology}'. "
            f"Valid: {sorted(ONTOLOGY_CONFIG)}"
        )

    cfg = ONTOLOGY_CONFIG[ontology]
    leaf_label = cfg["label"]
    gene_rel = cfg["gene_rel"]
    hierarchy_rels = cfg["hierarchy_rels"]
    rel_union = "|".join(hierarchy_rels)

    # --- Pfam: cross-label two-level ontology ---
    if ontology == "pfam":
        bind_up = (
            f"MATCH (g:Gene {{organism_name: $org}})"
            f"-[:{gene_rel}]->(leaf:Pfam)"
        )
        # *0..1 because Pfam.level=1 (t=leaf) OR PfamClan.level=0 (t=clan)
        walk_up = (
            "MATCH (leaf)-[:Pfam_in_pfam_clan*0..1]->(t)\n"
            "WHERE t:Pfam OR t:PfamClan"
        )
        if direction == "up":
            # Parenthesize the label guard so downstream callers can safely
            # append `AND ...` without altering operator precedence.
            walk_up_safe = (
                "MATCH (leaf)-[:Pfam_in_pfam_clan*0..1]->(t)\n"
                "WHERE (t:Pfam OR t:PfamClan)"
            )
            return {
                "leaf_label": leaf_label,
                "gene_rel": gene_rel,
                "rel_union": "Pfam_in_pfam_clan",
                "bind_up": bind_up,
                "walk_up": walk_up_safe,
                "walk_down": "",
            }
        # direction == "down"
        if root_label == "PfamClan":
            walk_down = (
                "MATCH (t:PfamClan)<-[:Pfam_in_pfam_clan]-(leaf:Pfam)"
            )
        elif root_label == "Pfam":
            # Pfam root has no descendants in this 2-level ontology
            walk_down = ""
        else:
            raise ValueError(
                f"For ontology='pfam' direction='down', root_label must "
                f"be 'Pfam' or 'PfamClan', got {root_label!r}"
            )
        return {
            "leaf_label": leaf_label,
            "gene_rel": gene_rel,
            "rel_union": "Pfam_in_pfam_clan",
            "bind_up": bind_up,
            "walk_up": walk_up,
            "walk_down": walk_down,
        }

    # --- Bridge ontologies (2-hop gene → intermediate → leaf) ---
    bridge = cfg.get("bridge")
    if bridge:
        bridge_edge = bridge["edge"]
        bridge_node = bridge["node_label"]
        bind_up = (
            f"MATCH (g:Gene {{organism_name: $org}})"
            f"-[:{gene_rel}]->(ko:{bridge_node})"
            f"-[:{bridge_edge}]->(leaf:{leaf_label})"
        )
        walk_up = f"MATCH (leaf)-[:{rel_union}*0..]->(t:{leaf_label})"
        walk_down = (
            f"MATCH (t:{leaf_label})<-[:{rel_union}*0..]-(leaf:{leaf_label})"
        )
        return {
            "leaf_label": leaf_label,
            "gene_rel": gene_rel,
            "rel_union": rel_union,
            "bind_up": bind_up,
            "walk_up": walk_up,
            "walk_down": walk_down,
        }

    # --- Flat ontologies (no hierarchy_rels): t = leaf ---
    if not hierarchy_rels:
        bind_up = (
            f"MATCH (g:Gene {{organism_name: $org}})"
            f"-[:{gene_rel}]->(t:{leaf_label})"
        )
        return {
            "leaf_label": leaf_label,
            "gene_rel": gene_rel,
            "rel_union": "",
            "bind_up": bind_up,
            "walk_up": "",
            "walk_down": "",
        }

    # --- Single-label tree ontologies (GO BP/MF/CC, EC, KEGG, CyanoRak) ---
    bind_up = (
        f"MATCH (g:Gene {{organism_name: $org}})"
        f"-[:{gene_rel}]->(leaf:{leaf_label})"
    )
    walk_up = f"MATCH (leaf)-[:{rel_union}*0..]->(t:{leaf_label})"
    walk_down = (
        f"MATCH (t:{leaf_label})<-[:{rel_union}*0..]-(leaf:{leaf_label})"
    )
    return {
        "leaf_label": leaf_label,
        "gene_rel": gene_rel,
        "rel_union": rel_union,
        "bind_up": bind_up,
        "walk_up": walk_up,
        "walk_down": walk_down,
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
        "  AND ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_name) CONTAINS word))\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_name AS organism_name\n"
        "ORDER BY g.organism_name, g.locus_tag"
    )
    return cypher, {"identifier": identifier, "organism": organism}


def _genes_by_function_filter_clause() -> str:
    """Return the shared WHERE filter expression for genes_by_function builders."""
    return (
        "($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_name) CONTAINS word))\n"
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

    Uses conditional counting to compute total_search_hits (fulltext hits
    before post-filters) and total_matching (after filters) in a single pass.

    RETURN keys: total_search_hits, total_matching, by_organism, by_category,
    score_max, score_median.
    """
    filt = _genes_by_function_filter_clause()
    cypher = (
        "CALL db.index.fulltext.queryNodes('geneFullText', $search_text)\n"
        "YIELD node AS g, score\n"
        f"WITH g, score,\n"
        f"     CASE WHEN {filt}\n"
        "     THEN 1 ELSE 0 END AS matches\n"
        "WITH count(g) AS total_search_hits,\n"
        "     sum(matches) AS total_matching,\n"
        "     max(CASE WHEN matches = 1 THEN score END) AS score_max,\n"
        "     percentileDisc(\n"
        "       CASE WHEN matches = 1 THEN score END, 0.5\n"
        "     ) AS score_median,\n"
        "     [x IN collect(\n"
        "       CASE WHEN matches = 1 THEN g.organism_name END\n"
        "     ) WHERE x IS NOT NULL] AS organisms,\n"
        "     [x IN collect(\n"
        "       CASE WHEN matches = 1 THEN g.gene_category END\n"
        "     ) WHERE x IS NOT NULL] AS categories\n"
        "RETURN total_search_hits, total_matching, score_max, score_median,\n"
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
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_function.

    RETURN keys (compact): locus_tag, gene_name, product,
    organism_name, gene_category, annotation_quality, score.
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

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
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
        "       g.product AS product, g.organism_name AS organism_name,\n"
        "       g.gene_category AS gene_category,\n"
        f"       g.annotation_quality AS annotation_quality, score{verbose_cols}\n"
        f"ORDER BY score DESC, g.locus_tag{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_gene_overview_summary(
    *,
    locus_tags: list[str],
) -> tuple[str, dict]:
    """Build summary + not_found for gene_overview.

    RETURN keys: total_matching, by_organism, by_category,
    by_annotation_type, has_expression, has_significant_expression,
    has_orthologs, has_clusters, not_found.
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
        "     [g IN found | g.organism_name] AS orgs,\n"
        "     [g IN found | g.gene_category] AS cats,\n"
        "     apoc.coll.flatten([g IN found | g.annotation_types]) AS all_atypes\n"
        "RETURN total_matching,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(cats) AS by_category,\n"
        "       apoc.coll.frequencies(all_atypes) AS by_annotation_type,\n"
        "       size([g IN found WHERE g.expression_edge_count > 0]) AS has_expression,\n"
        "       size([g IN found WHERE (g.significant_up_count + g.significant_down_count) > 0]) AS has_significant_expression,\n"
        "       size([g IN found WHERE g.closest_ortholog_group_size > 0]) AS has_orthologs,\n"
        "       size([g IN found WHERE g.cluster_membership_count > 0]) AS has_clusters,\n"
        "       size([g IN found WHERE\n"
        "           coalesce(g.numeric_metric_count, 0)\n"
        "         + coalesce(g.boolean_metric_count, 0)\n"
        "         + coalesce(g.categorical_metric_count, 0) > 0]) AS has_derived_metrics,\n"
        "       not_found"
    )
    return cypher, {"locus_tags": locus_tags}


def build_gene_overview(
    *,
    locus_tags: list[str],
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_overview.

    RETURN keys (compact): locus_tag, gene_name, product, gene_category,
    annotation_quality, organism_name, annotation_types,
    expression_edge_count, significant_up_count, significant_down_count,
    closest_ortholog_group_size, closest_ortholog_genera,
    cluster_membership_count, cluster_types,
    numeric_metric_count, boolean_metric_count, categorical_metric_count.
    RETURN keys (verbose): adds gene_summary, function_description,
    all_identifiers, numeric_metric_types_observed,
    boolean_metric_types_observed, categorical_metric_types_observed,
    compartments_observed.
    """
    params: dict = {"locus_tags": locus_tags}

    verbose_cols = (
        ",\n       g.gene_summary AS gene_summary"
        ",\n       g.function_description AS function_description"
        ",\n       g.all_identifiers AS all_identifiers"
        ",\n       coalesce(g.numeric_metric_types_observed, []) AS numeric_metric_types_observed"
        ",\n       coalesce(g.boolean_metric_types_observed, []) AS boolean_metric_types_observed"
        ",\n       coalesce(g.categorical_metric_types_observed, []) AS categorical_metric_types_observed"
        ",\n       coalesce(g.compartments_observed, []) AS compartments_observed"
        if verbose else ""
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
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
        "       g.organism_name AS organism_name,\n"
        "       g.annotation_types AS annotation_types,\n"
        "       g.expression_edge_count AS expression_edge_count,\n"
        "       g.significant_up_count AS significant_up_count,\n"
        "       g.significant_down_count AS significant_down_count,\n"
        "       g.closest_ortholog_group_size AS closest_ortholog_group_size,\n"
        "       g.closest_ortholog_genera AS closest_ortholog_genera,\n"
        "       coalesce(g.cluster_membership_count, 0) AS cluster_membership_count,\n"
        "       coalesce(g.cluster_types, []) AS cluster_types,\n"
        "       coalesce(g.numeric_metric_count, 0) AS numeric_metric_count,\n"
        "       coalesce(g.boolean_metric_count, 0) AS boolean_metric_count,\n"
        f"       coalesce(g.categorical_metric_count, 0) AS categorical_metric_count{verbose_cols}\n"
        f"ORDER BY g.locus_tag{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_gene_details(
    *, locus_tags: list[str], limit: int | None = None, offset: int = 0,
) -> tuple[str, dict]:
    """Build query for full gene node properties (batch)."""
    params: dict = {"locus_tags": locus_tags}
    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    limit_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})\n"
        f"RETURN g {{.*}} AS gene\nORDER BY g.locus_tag{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_gene_details_summary(
    *, locus_tags: list[str],
) -> tuple[str, dict]:
    """Build summary query for gene details: total + not_found."""
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "WITH collect(CASE WHEN g IS NOT NULL THEN lt END) AS found,\n"
        "     collect(CASE WHEN g IS NULL THEN lt END) AS not_found\n"
        "RETURN size(found) AS total_matching, not_found"
    )
    return cypher, {"locus_tags": locus_tags}



def build_gene_stub(*, gene_id: str) -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene {locus_tag: $lt})\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_name AS organism_name"
    )
    return cypher, {"lt": gene_id}


def _gene_homologs_og_where(
    *,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
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
    if cyanorak_roles is not None:
        conditions.append(
            "EXISTS { (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)"
            " WHERE cr.id IN $cyanorak_roles }"
        )
        params["cyanorak_roles"] = cyanorak_roles
    if cog_categories is not None:
        conditions.append(
            "EXISTS { (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)"
            " WHERE cc.id IN $cog_categories }"
        )
        params["cog_categories"] = cog_categories
    return conditions, params


def build_gene_homologs_summary(
    *,
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary + not_found/no_groups for gene_homologs.

    RETURN keys: total_matching, by_organism, by_source, not_found, no_groups,
    top_cyanorak_roles, top_cog_categories.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles,
        cog_categories=cog_categories,
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
        "  [row IN collect({org: CASE WHEN size(groups) > 0 THEN g.organism_name END,\n"
        "                    srcs: [x IN groups | x.source],\n"
        "                    og_ids: [x IN groups | x.id]})\n"
        "   WHERE row.org IS NOT NULL] AS matched\n"
        "UNWIND CASE WHEN size(matched) = 0 THEN [null] ELSE matched END AS m\n"
        "WITH nf_raw, ng_raw,\n"
        "     [x IN collect(m.org) WHERE x IS NOT NULL] AS orgs,\n"
        "     apoc.coll.flatten([x IN collect(m.srcs) WHERE x IS NOT NULL]) AS sources,\n"
        "     apoc.coll.toSet(apoc.coll.flatten(\n"
        "       [x IN collect(m.og_ids) WHERE x IS NOT NULL])) AS all_og_ids\n"
        "UNWIND CASE WHEN size(all_og_ids) = 0 THEN [null] ELSE all_og_ids END AS og_id\n"
        "OPTIONAL MATCH (og_node:OrthologGroup {id: og_id})-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
        "OPTIONAL MATCH (og_node)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
        "WITH nf_raw, ng_raw, orgs, sources,\n"
        "     collect(DISTINCT {id: cr.id, name: cr.name}) AS cr_pairs,\n"
        "     collect(DISTINCT {id: cc.id, name: cc.name}) AS cc_pairs\n"
        "WITH nf_raw, ng_raw, orgs, sources,\n"
        "     [p IN cr_pairs WHERE p.id IS NOT NULL | p.id + ' | ' + p.name] AS cr_items,\n"
        "     [p IN cc_pairs WHERE p.id IS NOT NULL | p.id + ' | ' + p.name] AS cc_items\n"
        "WITH *,\n"
        "     apoc.coll.frequencies(cr_items) AS cr_freq,\n"
        "     apoc.coll.frequencies(cc_items) AS cc_freq\n"
        "RETURN size(sources) AS total_matching,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(sources) AS by_source,\n"
        "       [x IN nf_raw WHERE x IS NOT NULL] AS not_found,\n"
        "       [x IN ng_raw WHERE x IS NOT NULL] AS no_groups,\n"
        "       apoc.coll.sortMaps(\n"
        "         [x IN cr_freq | {id: split(x.item, ' | ')[0],\n"
        "                          name: split(x.item, ' | ')[1],\n"
        "                          count: x.count}],\n"
        "         'count')[0..5] AS top_cyanorak_roles,\n"
        "       apoc.coll.sortMaps(\n"
        "         [x IN cc_freq | {id: split(x.item, ' | ')[0],\n"
        "                          name: split(x.item, ' | ')[1],\n"
        "                          count: x.count}],\n"
        "         'count')[0..5] AS top_cog_categories"
    )
    return cypher, params


def build_gene_homologs(
    *,
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_homologs.

    RETURN keys (compact): locus_tag, organism_name, group_id,
    consensus_gene_name, consensus_product, taxonomic_level, source,
    specificity_rank.
    RETURN keys (verbose): adds member_count, organism_count, genera,
    has_cross_genus_members, description, functional_description,
    cyanorak_roles, cog_categories.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles,
        cog_categories=cog_categories,
    )
    params["locus_tags"] = locus_tags

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    if verbose:
        cypher = (
            "UNWIND $locus_tags AS lt\n"
            "MATCH (g:Gene {locus_tag: lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
            f"{where_block}"
            "OPTIONAL MATCH (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
            "OPTIONAL MATCH (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
            "WITH g, og,\n"
            "     [x IN collect(DISTINCT {id: cr.id, name: cr.name}) WHERE x.id IS NOT NULL] AS cyanorak_roles,\n"
            "     [x IN collect(DISTINCT {id: cc.id, name: cc.name}) WHERE x.id IS NOT NULL] AS cog_categories\n"
            "RETURN g.locus_tag AS locus_tag, g.organism_name AS organism_name,\n"
            "       og.id AS group_id,\n"
            "       og.consensus_gene_name AS consensus_gene_name,\n"
            "       og.consensus_product AS consensus_product,\n"
            "       og.taxonomic_level AS taxonomic_level, og.source AS source,\n"
            "       og.specificity_rank AS specificity_rank,\n"
            "       og.member_count AS member_count,\n"
            "       og.organism_count AS organism_count,\n"
            "       og.genera AS genera,\n"
            "       og.has_cross_genus_members AS has_cross_genus_members,\n"
            "       og.description AS description,\n"
            "       og.functional_description AS functional_description,\n"
            "       cyanorak_roles, cog_categories\n"
            f"ORDER BY g.locus_tag, og.specificity_rank, og.source{skip_clause}{limit_clause}"
        )
    else:
        cypher = (
            "UNWIND $locus_tags AS lt\n"
            "MATCH (g:Gene {locus_tag: lt})-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
            f"{where_block}"
            "RETURN g.locus_tag AS locus_tag, g.organism_name AS organism_name,\n"
            "       og.id AS group_id,\n"
            "       og.consensus_gene_name AS consensus_gene_name,\n"
            "       og.consensus_product AS consensus_product,\n"
            "       og.taxonomic_level AS taxonomic_level, og.source AS source,\n"
            f"       og.specificity_rank AS specificity_rank\n"
            f"ORDER BY g.locus_tag, og.specificity_rank, og.source{skip_clause}{limit_clause}"
        )
    return cypher, params


def _list_publications_where(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    background_factors: str | None = None,
    growth_phases: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    publication_dois: list[str] | None = None,
    compartment: str | None = None,
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

    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(p.background_factors, [])"
            " WHERE toLower(bf) = toLower($background_factors))"
        )
        params["background_factors"] = background_factors

    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(p.growth_phases, [])"
            " WHERE toLower(gp) = toLower($growth_phases))"
        )
        params["growth_phases"] = growth_phases

    if author:
        conditions.append(
            "ANY(a IN p.authors WHERE toLower(a) CONTAINS toLower($author))"
        )
        params["author"] = author

    if publication_dois:
        conditions.append("toLower(p.doi) IN $publication_dois")
        params["publication_dois"] = [d.lower() for d in publication_dois]

    if compartment is not None:
        conditions.append("$compartment IN coalesce(p.compartments, [])")
        params["compartment"] = compartment

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
    return where_block, params


def build_list_publications(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    background_factors: str | None = None,
    growth_phases: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    publication_dois: list[str] | None = None,
    compartment: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build Cypher for listing publications with experiment summaries.

    RETURN keys (compact): doi, title, authors, year, journal, study_type,
    organisms, experiment_count, treatment_types, background_factors, omics_types,
    clustering_analysis_count, cluster_types, growth_phases,
    derived_metric_count, derived_metric_value_kinds, compartments.
    When search_text is provided, also: score.
    RETURN keys (verbose): adds abstract, description, cluster_count,
    derived_metric_gene_count, derived_metric_types.
    compartment: when provided, restricts to publications with at least one
    experiment in that wet-lab compartment.
    """
    where_block, params = _list_publications_where(
        organism=organism, treatment_type=treatment_type,
        background_factors=background_factors, growth_phases=growth_phases,
        search_text=search_text, author=author,
        publication_dois=publication_dois, compartment=compartment,
    )

    verbose_cols = (
        ",\n       p.abstract AS abstract, p.description AS description,"
        "\n       p.cluster_count AS cluster_count,"
        "\n       coalesce(p.derived_metric_gene_count, 0) AS derived_metric_gene_count,"
        "\n       coalesce(p.derived_metric_types, []) AS derived_metric_types"
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
            "       coalesce(p.background_factors, []) AS background_factors,\n"
            "       p.omics_types AS omics_types,\n"
            "       coalesce(p.clustering_analysis_count, 0) AS clustering_analysis_count,\n"
            "       coalesce(p.cluster_types, []) AS cluster_types,\n"
            "       coalesce(p.growth_phases, []) AS growth_phases,\n"
            "       coalesce(p.derived_metric_count, 0) AS derived_metric_count,\n"
            "       coalesce(p.derived_metric_value_kinds, []) AS derived_metric_value_kinds,\n"
            "       coalesce(p.compartments, []) AS compartments,\n"
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
            "       coalesce(p.background_factors, []) AS background_factors,\n"
            "       p.omics_types AS omics_types,\n"
            "       coalesce(p.clustering_analysis_count, 0) AS clustering_analysis_count,\n"
            "       coalesce(p.cluster_types, []) AS cluster_types,\n"
            "       coalesce(p.growth_phases, []) AS growth_phases,\n"
            "       coalesce(p.derived_metric_count, 0) AS derived_metric_count,\n"
            "       coalesce(p.derived_metric_value_kinds, []) AS derived_metric_value_kinds,\n"
            f"       coalesce(p.compartments, []) AS compartments{verbose_cols}\n"
            f"ORDER BY p.publication_year DESC, p.title\n"
            f"{limit_clause}"
        )

    return cypher, params


def build_list_publications_summary(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    background_factors: str | None = None,
    growth_phases: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    publication_dois: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for matching publications.

    RETURN keys: total_entries, total_matching, by_organism,
    by_treatment_type, by_background_factors, by_omics_type,
    by_cluster_type, by_value_kind, by_metric_type, by_compartment.
    total_entries is the unfiltered count of all publications.
    total_matching is the count after applying filters.
    The rollup envelope keys use apoc.coll.flatten + apoc.coll.frequencies over
    the precomputed list properties on each Publication node.
    """
    where_block, params = _list_publications_where(
        organism=organism, treatment_type=treatment_type,
        background_factors=background_factors, growth_phases=growth_phases,
        search_text=search_text, author=author,
        publication_dois=publication_dois, compartment=compartment,
    )

    collect_cols = (
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.organisms, []))) AS orgs,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.treatment_types, []))) AS tts,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.background_factors, []))) AS bfs,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.omics_types, []))) AS omics,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.derived_metric_value_kinds, []))) AS vks,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.derived_metric_types, []))) AS mtypes,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.compartments, []))) AS comps,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(p.cluster_types, []))) AS ctypes"
    )
    return_cols = (
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(tts) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(bfs) AS by_background_factors,\n"
        "       apoc.coll.frequencies(omics) AS by_omics_type,\n"
        "       apoc.coll.frequencies(vks) AS by_value_kind,\n"
        "       apoc.coll.frequencies(mtypes) AS by_metric_type,\n"
        "       apoc.coll.frequencies(comps) AS by_compartment,\n"
        "       apoc.coll.frequencies(ctypes) AS by_cluster_type"
    )

    if search_text:
        cypher = (
            "CALL db.index.fulltext.queryNodes('publicationFullText', $search_text)\n"
            "YIELD node AS p, score\n"
            f"{where_block}"
            "WITH count(p) AS total_matching,\n"
            f"{collect_cols}\n"
            "MATCH (p2:Publication)\n"
            "RETURN count(p2) AS total_entries, total_matching,\n"
            f"{return_cols}"
        )
    else:
        # OPTIONAL MATCH preserves the total_entries row when the filtered
        # MATCH returns zero rows — without it, an empty filter intersection
        # collapses to 0 result rows and callers IndexError on summary[0].
        cypher = (
            "MATCH (p:Publication)\n"
            "WITH count(p) AS total_entries\n"
            "OPTIONAL MATCH (p:Publication)\n"
            f"{where_block}"
            "WITH total_entries,\n"
            "     count(p) AS total_matching,\n"
            f"{collect_cols}\n"
            "RETURN total_entries, total_matching,\n"
            f"{return_cols}"
        )

    return cypher, params


def build_list_gene_categories() -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene) WHERE g.gene_category IS NOT NULL\n"
        "RETURN g.gene_category AS category, count(*) AS gene_count\n"
        "ORDER BY gene_count DESC"
    )
    return cypher, {}


def build_list_brite_trees() -> tuple[str, dict]:
    """List BRITE trees with term counts.

    RETURN keys: tree, tree_code, term_count.
    """
    cypher = (
        "MATCH (b:BriteCategory)\n"
        "RETURN b.tree AS tree, b.tree_code AS tree_code, "
        "count(*) AS term_count\n"
        "ORDER BY b.tree"
    )
    return cypher, {}


def build_list_growth_phases() -> tuple[str, dict]:
    """List distinct growth_phase values with experiment counts.

    RETURN keys: phase, experiment_count.
    """
    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(:Gene)\n"
        "WITH r.growth_phase AS phase, e.id AS eid\n"
        "WITH phase, count(DISTINCT eid) AS experiment_count\n"
        "WHERE phase IS NOT NULL\n"
        "RETURN phase, experiment_count\n"
        "ORDER BY experiment_count DESC, phase"
    )
    return cypher, {}


def build_list_metric_types() -> tuple[str, dict]:
    """List distinct DerivedMetric.metric_type values with DM counts.

    RETURN keys: value, count.
    """
    cypher = (
        "MATCH (dm:DerivedMetric) WHERE dm.metric_type IS NOT NULL\n"
        "RETURN dm.metric_type AS value, count(*) AS count\n"
        "ORDER BY count DESC, value"
    )
    return cypher, {}


def build_list_value_kinds() -> tuple[str, dict]:
    """List DerivedMetric.value_kind enum values with DM counts per kind.

    RETURN keys: value, count. Today's KG: {numeric, boolean, categorical}.
    """
    cypher = (
        "MATCH (dm:DerivedMetric) WHERE dm.value_kind IS NOT NULL\n"
        "RETURN dm.value_kind AS value, count(*) AS count\n"
        "ORDER BY count DESC, value"
    )
    return cypher, {}


def build_list_compartments() -> tuple[str, dict]:
    """List distinct Experiment.compartment values with experiment counts.

    Sourced from Experiment.compartment (wet-lab fraction), per slice-2 D7.

    RETURN keys: value, count.
    """
    cypher = (
        "MATCH (e:Experiment) WHERE e.compartment IS NOT NULL\n"
        "RETURN e.compartment AS value, count(*) AS count\n"
        "ORDER BY count DESC, value"
    )
    return cypher, {}


def build_list_organisms(
    *,
    organism_names_lc: list[str] | None = None,
    compartment: str | None = None,
    verbose: bool = False,
) -> tuple[str, dict]:
    """Build Cypher for listing organisms with data-availability signals.

    organism_names_lc: optional list of lowercased preferred_names. When
        None, returns all organisms. When non-None, restricts to organisms
        whose preferred_name (lowercased) is in the list.
    compartment: optional Experiment.compartment value (e.g. 'vesicle')
        to restrict to organisms whose compartments list includes it.

    RETURN keys (compact): organism_name, organism_type, genus, species,
    strain, clade, ncbi_taxon_id, gene_count, publication_count,
    experiment_count, treatment_types, background_factors, omics_types,
    clustering_analysis_count, cluster_types, derived_metric_count,
    derived_metric_value_kinds, compartments, reference_database,
    reference_proteome, growth_phases.
    RETURN keys (verbose): adds family, order, tax_class, phylum, kingdom,
    superkingdom, lineage, cluster_count, derived_metric_gene_count,
    derived_metric_types.
    """
    verbose_cols = (
        ",\n       o.family AS family,"
        "\n       o.order AS order,"
        "\n       o.tax_class AS tax_class,"
        "\n       o.phylum AS phylum,"
        "\n       o.kingdom AS kingdom,"
        "\n       o.superkingdom AS superkingdom,"
        "\n       o.lineage AS lineage,"
        "\n       coalesce(o.cluster_count, 0) AS cluster_count,"
        "\n       coalesce(o.derived_metric_gene_count, 0) AS derived_metric_gene_count,"
        "\n       coalesce(o.derived_metric_types, []) AS derived_metric_types"
        if verbose else ""
    )

    conditions = [
        "($organism_names_lc IS NULL"
        " OR toLower(o.preferred_name) IN $organism_names_lc)"
    ]
    params: dict = {"organism_names_lc": organism_names_lc}
    if compartment is not None:
        conditions.append("$compartment IN coalesce(o.compartments, [])")
        params["compartment"] = compartment

    where_block = "WHERE " + "\n  AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        f"{where_block}"
        "RETURN o.preferred_name AS organism_name,\n"
        "       o.organism_type AS organism_type,\n"
        "       o.genus AS genus,\n"
        "       o.species AS species,\n"
        "       o.strain_name AS strain,\n"
        "       o.clade AS clade,\n"
        "       o.ncbi_taxon_id AS ncbi_taxon_id,\n"
        "       o.gene_count AS gene_count,\n"
        "       o.publication_count AS publication_count,\n"
        "       o.experiment_count AS experiment_count,\n"
        "       o.treatment_types AS treatment_types,\n"
        "       coalesce(o.background_factors, []) AS background_factors,\n"
        "       o.omics_types AS omics_types,\n"
        "       coalesce(o.clustering_analysis_count, 0) AS clustering_analysis_count,\n"
        "       coalesce(o.cluster_types, []) AS cluster_types,\n"
        "       coalesce(o.derived_metric_count, 0) AS derived_metric_count,\n"
        "       coalesce(o.derived_metric_value_kinds, []) AS derived_metric_value_kinds,\n"
        "       coalesce(o.compartments, []) AS compartments,\n"
        "       o.reference_database AS reference_database,\n"
        "       o.reference_proteome AS reference_proteome,\n"
        "       coalesce(o.growth_phases, []) AS growth_phases"
        f"{verbose_cols}\n"
        "ORDER BY o.genus, o.preferred_name"
    )
    return cypher, params


def build_list_organisms_summary(
    *,
    organism_names_lc: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[str, dict]:
    """Summary count + DM/compartment/cluster/organism-type rollups across matched organisms.

    RETURN keys: total_entries, total_matching, by_value_kind,
    by_metric_type, by_compartment, by_cluster_type, by_organism_type.
    """
    conditions = [
        "($organism_names_lc IS NULL"
        " OR toLower(o.preferred_name) IN $organism_names_lc)"
    ]
    params: dict = {"organism_names_lc": organism_names_lc}
    if compartment is not None:
        conditions.append("$compartment IN coalesce(o.compartments, [])")
        params["compartment"] = compartment
    where_block = "WHERE " + "\n  AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        "WITH count(o) AS total_entries\n"
        "OPTIONAL MATCH (o:OrganismTaxon)\n"
        f"{where_block}"
        "WITH total_entries,\n"
        "     count(o) AS total_matching,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(o.derived_metric_value_kinds, []))) AS vks,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(o.derived_metric_types, []))) AS mtypes,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(o.compartments, []))) AS comps,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(o.cluster_types, []))) AS ctypes,\n"
        "     collect(o.organism_type) AS otypes\n"
        "RETURN total_entries, total_matching,\n"
        "       apoc.coll.frequencies(vks) AS by_value_kind,\n"
        "       apoc.coll.frequencies(mtypes) AS by_metric_type,\n"
        "       apoc.coll.frequencies(comps) AS by_compartment,\n"
        "       apoc.coll.frequencies(ctypes) AS by_cluster_type,\n"
        "       apoc.coll.frequencies(otypes) AS by_organism_type"
    )
    return cypher, params


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
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    compartment: str | None = None,
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
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(e.organism_name) CONTAINS word)"
        )
        params["organism"] = organism

    if treatment_type:
        conditions.append(
            "ANY(t IN e.treatment_type WHERE toLower(t) IN $treatment_types)"
        )
        params["treatment_types"] = [t.lower() for t in treatment_type]

    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(e.background_factors, [])"
            " WHERE toLower(bf) IN $background_factors)"
        )
        params["background_factors"] = [bf.lower() for bf in background_factors]

    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(e.growth_phases, [])"
            " WHERE toLower(gp) IN $growth_phases)"
        )
        params["growth_phases"] = [gp.lower() for gp in growth_phases]

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

    if experiment_ids:
        conditions.append("e.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids

    if compartment is not None:
        conditions.append("e.compartment = $compartment")
        params["compartment"] = compartment

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
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    compartment: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for listing experiments with precomputed gene count stats.

    RETURN keys (compact): experiment_id, experiment_name, publication_doi,
    authors, organism_name, treatment_type, coculture_partner, omics_type,
    is_time_course, table_scope, table_scope_detail,
    gene_count, distinct_gene_count, significant_up_count,
    significant_down_count, time_point_count, time_point_labels,
    time_point_orders, time_point_hours, time_point_totals,
    time_point_significant_up, time_point_significant_down,
    clustering_analysis_count, cluster_types, growth_phases,
    time_point_growth_phases, derived_metric_count,
    derived_metric_value_kinds, compartment.
    RETURN keys (verbose): adds publication_title, treatment,
    control, light_condition, light_intensity, medium, temperature,
    statistical_test, experimental_context, cluster_count,
    derived_metric_gene_count, derived_metric_types,
    reports_derived_metric_types.
    RETURN keys (search_text): adds score.
    compartment: when provided, restricts to experiments in that wet-lab
    compartment (scalar equality: e.compartment = $compartment).

    Note on derived_metric_types vs reports_derived_metric_types:
    Both fields are sourced from ``e.reports_derived_metric_types`` today —
    the KG only stores a single report-side rollup on the Experiment node.
    They are identical in current data and are both surfaced for
    forward-compat with a future KG distinction between "DMs reported by
    this experiment" and "DMs associated with this experiment" (per
    slice-2 design D5).
    """
    where_block, params = _list_experiments_where(
        organism=organism, treatment_type=treatment_type,
        omics_type=omics_type, publication_doi=publication_doi,
        coculture_partner=coculture_partner, search_text=search_text,
        time_course_only=time_course_only, table_scope=table_scope,
        background_factors=background_factors, growth_phases=growth_phases,
        experiment_ids=experiment_ids, compartment=compartment,
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
        "\n       e.experimental_context AS experimental_context,"
        "\n       coalesce(e.cluster_count, 0) AS cluster_count,"
        "\n       coalesce(e.derived_metric_gene_count, 0) AS derived_metric_gene_count,"
        "\n       coalesce(e.reports_derived_metric_types, []) AS derived_metric_types,"
        "\n       coalesce(e.reports_derived_metric_types, []) AS reports_derived_metric_types"
        if verbose else ""
    )

    if offset:
        skip_clause = "SKIP $offset\n"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "LIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    return_cols = (
        "e.id AS experiment_id,\n"
        "       e.name AS experiment_name,\n"
        "       p.doi AS publication_doi,\n"
        "       coalesce(p.authors, []) AS authors,\n"
        "       e.organism_name AS organism_name,\n"
        "       e.treatment_type AS treatment_type,\n"
        "       coalesce(e.background_factors, []) AS background_factors,\n"
        "       e.coculture_partner AS coculture_partner,\n"
        "       e.omics_type AS omics_type,\n"
        "       e.is_time_course AS is_time_course,\n"
        "       e.table_scope AS table_scope,\n"
        "       e.table_scope_detail AS table_scope_detail,\n"
        "       e.gene_count AS gene_count,\n"
        "       e.distinct_gene_count AS distinct_gene_count,\n"
        "       e.significant_up_count AS significant_up_count,\n"
        "       e.significant_down_count AS significant_down_count,\n"
        "       e.time_point_count AS time_point_count,\n"
        "       e.time_point_labels AS time_point_labels,\n"
        "       e.time_point_orders AS time_point_orders,\n"
        "       e.time_point_hours AS time_point_hours,\n"
        "       e.time_point_totals AS time_point_totals,\n"
        "       e.time_point_significant_up AS time_point_significant_up,\n"
        "       e.time_point_significant_down AS time_point_significant_down,\n"
        "       coalesce(e.clustering_analysis_count, 0) AS clustering_analysis_count,\n"
        "       coalesce(e.cluster_types, []) AS cluster_types"
        ",\n       coalesce(e.growth_phases, []) AS growth_phases"
        ",\n       coalesce(e.time_point_growth_phases, []) AS time_point_growth_phases"
        ",\n       coalesce(e.derived_metric_count, 0) AS derived_metric_count"
        ",\n       coalesce(e.derived_metric_value_kinds, []) AS derived_metric_value_kinds"
        ",\n       e.compartment AS compartment"
    )

    if search_text:
        cypher = (
            "CALL db.index.fulltext.queryNodes('experimentFullText', $search_text)\n"
            "YIELD node AS e, score\n"
            "MATCH (p:Publication)-[:Has_experiment]->(e)\n"
            f"{where_block}"
            f"RETURN {return_cols},\n"
            f"       score{verbose_cols}\n"
            f"ORDER BY score DESC, e.organism_name, e.name\n"
            f"{skip_clause}{limit_clause}"
        )
    else:
        cypher = (
            "MATCH (p:Publication)-[:Has_experiment]->(e:Experiment)\n"
            f"{where_block}"
            f"RETURN {return_cols}{verbose_cols}\n"
            f"ORDER BY p.publication_year DESC, e.organism_name, e.name\n"
            f"{skip_clause}{limit_clause}"
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
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[str, dict]:
    """Build summary aggregation Cypher for list_experiments.

    Returns breakdowns by organism, treatment type, omics type,
    publication, table_scope, background_factors, cluster_type,
    growth_phase, and DM rollups using apoc.coll.frequencies.

    RETURN keys: total_matching, time_course_count, by_organism,
    by_treatment_type, by_background_factors, by_omics_type, by_publication,
    by_table_scope, by_cluster_type, by_growth_phase,
    by_value_kind, by_metric_type, by_compartment.
    RETURN keys (search_text): adds score_max, score_median.

    Note: e.compartment is a scalar string, so we use collect(e.compartment)
    directly (no apoc.coll.flatten) for the by_compartment rollup.
    """
    where_block, params = _list_experiments_where(
        organism=organism, treatment_type=treatment_type,
        omics_type=omics_type, publication_doi=publication_doi,
        coculture_partner=coculture_partner, search_text=search_text,
        time_course_only=time_course_only, table_scope=table_scope,
        background_factors=background_factors, growth_phases=growth_phases,
        experiment_ids=experiment_ids, compartment=compartment,
    )

    collect_cols = (
        "collect(e.organism_name) AS orgs,\n"
        "     apoc.coll.flatten(collect(coalesce(e.treatment_type, []))) AS tts,\n"
        "     apoc.coll.flatten(collect(coalesce(e.background_factors, []))) AS bfs,\n"
        "     collect(e.omics_type) AS omics,\n"
        "     collect(p.doi) AS dois,\n"
        "     collect(e.is_time_course) AS tc,\n"
        "     collect(e.table_scope) AS scopes,\n"
        "     apoc.coll.flatten(collect(coalesce(e.cluster_types, []))) AS ctypes"
        ",\n     apoc.coll.flatten(collect(coalesce(e.growth_phases, []))) AS gps"
        ",\n     apoc.coll.flatten(\n"
        "       collect(coalesce(e.derived_metric_value_kinds, []))) AS vks"
        ",\n     apoc.coll.flatten(\n"
        "       collect(coalesce(e.reports_derived_metric_types, []))) AS mtypes"
        ",\n     collect(e.compartment) AS comps"
    )

    return_cols = (
        "size(orgs) AS total_matching,\n"
        "       size([x IN tc WHERE x = 'true']) AS time_course_count,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(tts) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(bfs) AS by_background_factors,\n"
        "       apoc.coll.frequencies(omics) AS by_omics_type,\n"
        "       apoc.coll.frequencies(dois) AS by_publication,\n"
        "       apoc.coll.frequencies(scopes) AS by_table_scope,\n"
        "       apoc.coll.frequencies(ctypes) AS by_cluster_type"
        ",\n       apoc.coll.frequencies(gps) AS by_growth_phase"
        ",\n       apoc.coll.frequencies(vks) AS by_value_kind"
        ",\n       apoc.coll.frequencies(mtypes) AS by_metric_type"
        ",\n       apoc.coll.frequencies(comps) AS by_compartment"
    )

    if search_text:
        cypher = (
            "CALL db.index.fulltext.queryNodes('experimentFullText', $search_text)\n"
            "YIELD node AS e, score\n"
            "MATCH (p:Publication)-[:Has_experiment]->(e)\n"
            f"{where_block}"
            f"WITH {collect_cols},\n"
            "     max(score) AS score_max,\n"
            "     percentileDisc(score, 0.5) AS score_median\n"
            f"RETURN {return_cols},\n"
            "       score_max, score_median"
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
    level: int | None = None,
    tree: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for search_ontology.

    RETURN keys: total_entries, total_matching, score_max, score_median.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
    cfg = ONTOLOGY_CONFIG[ontology]
    index_name = cfg["fulltext_index"]
    parent_index = cfg.get("parent_fulltext_index")

    params: dict = {"search_text": search_text}

    # Build optional WHERE predicates
    where_parts: list[str] = []
    if level is not None:
        where_parts.append("t.level = $level")
        params["level"] = level
    if tree is not None:
        where_parts.append("t.tree = $tree")
        params["tree"] = tree
    where_clause = "  WHERE " + " AND ".join(where_parts) + "\n" if where_parts else ""

    if parent_index:
        cypher = (
            "CALL {\n"
            f"  CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "  YIELD node AS t, score\n"
            + where_clause
            + "  RETURN score\n"
            "  UNION ALL\n"
            f"  CALL db.index.fulltext.queryNodes('{parent_index}', $search_text)\n"
            "  YIELD node AS t, score\n"
            + where_clause
            + "  RETURN score\n"
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
            + where_clause
            + "WITH count(t) AS total_matching,\n"
            "     max(score) AS score_max,\n"
            "     percentileDisc(score, 0.5) AS score_median\n"
            f"CALL {{ MATCH (all_t:{label}) RETURN count(all_t) AS total_entries }}\n"
            "RETURN total_entries, total_matching, score_max, score_median"
        )
    return cypher, params


def build_search_ontology(
    *, ontology: str, search_text: str,
    limit: int | None = None,
    offset: int = 0,
    level: int | None = None,
    tree: str | None = None,
) -> tuple[str, dict]:
    """Build Cypher for search_ontology.

    RETURN keys: id, name, score, level, tree, tree_code.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
    cfg = ONTOLOGY_CONFIG[ontology]
    index_name = cfg["fulltext_index"]
    parent_index = cfg.get("parent_fulltext_index")

    params: dict = {"search_text": search_text}
    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    limit_clause = "\nLIMIT $limit" if limit is not None else ""
    if limit is not None:
        params["limit"] = limit

    # Build optional WHERE predicates
    where_parts: list[str] = []
    if level is not None:
        where_parts.append("t.level = $level")
        params["level"] = level
    if tree is not None:
        where_parts.append("t.tree = $tree")
        params["tree"] = tree
    where_clause = "  WHERE " + " AND ".join(where_parts) + "\n" if where_parts else ""

    if parent_index:
        # UNION search across both indexes (e.g. Pfam domain + clan)
        cypher = (
            "CALL {\n"
            f"  CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "  YIELD node AS t, score\n"
            + where_clause
            + "  RETURN t.id AS id, t.name AS name, score,\n"
            "         t.level AS level, t.tree AS tree, t.tree_code AS tree_code\n"
            "  UNION ALL\n"
            f"  CALL db.index.fulltext.queryNodes('{parent_index}', $search_text)\n"
            "  YIELD node AS t, score\n"
            + where_clause
            + "  RETURN t.id AS id, t.name AS name, score,\n"
            "         t.level AS level, t.tree AS tree, t.tree_code AS tree_code\n"
            "}\n"
            "RETURN id, name, score, level, tree, tree_code\n"
            "ORDER BY score DESC, id" + skip_clause + limit_clause
        )
    else:
        cypher = (
            f"CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "YIELD node AS t, score\n"
            + where_clause
            + "RETURN t.id AS id, t.name AS name, score,\n"
            "       t.level AS level, t.tree AS tree, t.tree_code AS tree_code\n"
            "ORDER BY score DESC, id" + skip_clause + limit_clause
        )
    return cypher, params


# Ontology key → expected node label(s). Single-label ontologies get a
# one-element list; pfam accepts both Pfam (level 1) and PfamClan (level 0).
# Derived from ONTOLOGY_CONFIG so adding a new ontology is one-place.
_ONTOLOGY_LABELS: dict[str, list[str]] = {
    key: (
        [cfg["label"], cfg["parent_label"]]
        if "parent_label" in cfg else [cfg["label"]]
    )
    for key, cfg in ONTOLOGY_CONFIG.items()
}

_ALL_ONTOLOGY_LABELS: list[str] = sorted({
    label for labels in _ONTOLOGY_LABELS.values() for label in labels
})
_ONTOLOGY_LABEL_GUARD: str = " OR ".join(f"t:{L}" for L in _ALL_ONTOLOGY_LABELS)


def build_genes_by_ontology_validate(
    *,
    term_ids: list[str],
    ontology: str,
    level: int | None,
) -> tuple[str, dict]:
    """Classify input term_ids into ok / not_found / wrong_ontology / wrong_level.

    RETURN keys per row: tid, status, matched_label.
    status ∈ {'ok','not_found','wrong_ontology','wrong_level'}.
    matched_label is the expected-label the term carries when the term exists
    and belongs to the requested ontology (status='ok' or 'wrong_level').
    NULL when status='not_found' or 'wrong_ontology'.
    """
    if ontology not in _ONTOLOGY_LABELS:
        raise ValueError(
            f"Invalid ontology '{ontology}'. "
            f"Valid: {sorted(_ONTOLOGY_LABELS)}"
        )
    expected_labels = _ONTOLOGY_LABELS[ontology]
    cypher = (
        "UNWIND $term_ids AS tid\n"
        "OPTIONAL MATCH (t {id: tid})\n"
        f"  WHERE {_ONTOLOGY_LABEL_GUARD}\n"
        "WITH tid, head(collect(t)) AS t\n"
        "RETURN tid,\n"
        "  CASE\n"
        "    WHEN t IS NULL THEN 'not_found'\n"
        "    WHEN NOT ANY(L IN $expected_labels WHERE L IN labels(t)) "
        "THEN 'wrong_ontology'\n"
        "    WHEN $level IS NOT NULL AND t.level <> $level "
        "THEN 'wrong_level'\n"
        "    ELSE 'ok'\n"
        "  END AS status,\n"
        "  CASE WHEN t IS NOT NULL "
        "THEN [L IN labels(t) WHERE L IN $expected_labels][0] "
        "ELSE NULL END AS matched_label"
    )
    return cypher, {
        "term_ids": term_ids,
        "expected_labels": expected_labels,
        "level": level,
    }


def _genes_by_ontology_match_stage(
    *,
    ontology: str,
    level: int | None,
    term_ids: list[str] | None,
    organism: str,
    tree: str | None = None,
) -> tuple[str, dict]:
    """Shared MATCH + size-filter-WITH for detail/per_term/per_gene builders.

    Returns the Cypher fragment through `WITH t, collect(DISTINCT g) AS term_genes`
    with the $min_gene_set_size / $max_gene_set_size filter applied,
    plus the common params dict (org, term_ids/level as applicable).
    Consumers are responsible for adding $min_gene_set_size / $max_gene_set_size
    into params, and for appending their own UNWIND/RETURN tail.
    """
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")

    params: dict = {"org": organism}

    if level is None:
        # Mode 1 — walk DOWN from each input term.
        params["term_ids"] = term_ids
        # Pfam needs special handling because input may be Pfam OR PfamClan;
        # caller-side validation (Query V) tells the apex label, but the
        # builder must work without that. Use coalesce over both label MATCHes.
        if ontology == "pfam":
            cypher_head = (
                "UNWIND $term_ids AS input_tid\n"
                "OPTIONAL MATCH (tp:Pfam {id: input_tid})\n"
                "OPTIONAL MATCH (tc:PfamClan {id: input_tid})\n"
                "WITH input_tid, coalesce(tp, tc) AS t\n"
                "OPTIONAL MATCH (t)<-[:Pfam_in_pfam_clan*0..1]-(leaf:Pfam)\n"
                "WITH t, coalesce(leaf, t) AS leaf\n"
                "MATCH (g:Gene {organism_name: $org})-[:Gene_has_pfam]->(leaf)\n"
                "WHERE t:Pfam OR t:PfamClan\n"
            )
        else:
            frag = _hierarchy_walk(ontology, direction="down")
            leaf = frag["leaf_label"]
            walk = frag["walk_down"]
            # Single-label: walk DOWN from root to leaf to gene.
            # Flat ontologies: no walk, leaf = t.
            if walk:
                cypher_head = (
                    "UNWIND $term_ids AS input_tid\n"
                    f"MATCH (t:{leaf} {{id: input_tid}})\n"
                    f"{walk}\n"
                    f"MATCH (g:Gene {{organism_name: $org}})"
                    f"-[:{frag['gene_rel']}]->(leaf)\n"
                )
            else:
                # Flat: t = leaf; still the "input term's genes"
                cypher_head = (
                    "UNWIND $term_ids AS input_tid\n"
                    f"MATCH (t:{leaf} {{id: input_tid}})\n"
                    f"MATCH (g:Gene {{organism_name: $org}})"
                    f"-[:{frag['gene_rel']}]->(t)\n"
                )
    else:
        # Mode 2/3 — walk UP, filter on level (and optionally term_ids).
        params["level"] = level
        frag = _hierarchy_walk(ontology, direction="up")
        bind = frag["bind_up"]
        walk = frag["walk_up"]
        # Pfam's walk_up already carries a `WHERE t:Pfam OR t:PfamClan` guard
        # — merge the level filter in via AND instead of opening a new WHERE.
        walk_has_where = bool(walk) and "WHERE" in walk
        level_keyword = "AND" if walk_has_where else "WHERE"
        level_clause = f"{level_keyword} t.level = $level"
        if term_ids is not None:
            level_clause += " AND t.id IN $term_ids"
            params["term_ids"] = term_ids
        if tree is not None:
            level_clause += " AND t.tree = $tree"
            params["tree"] = tree
        if walk:
            cypher_head = f"{bind}\n{walk}\n{level_clause}\n"
        else:
            # Flat ontology: t = leaf; no walk; level filter on t directly.
            cypher_head = f"{bind}\n{level_clause}\n"

    # Size filter (common to all modes). Caller must add
    # $min_gene_set_size and $max_gene_set_size to params.
    size_filter = (
        "WITH t, collect(DISTINCT g) AS term_genes\n"
        "WHERE size(term_genes) >= $min_gene_set_size\n"
        "  AND ($max_gene_set_size IS NULL OR "
        "size(term_genes) <= $max_gene_set_size)"
    )
    return f"{cypher_head}\n{size_filter}", params


def build_genes_by_ontology_detail(
    *,
    ontology: str,
    organism: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    tree: str | None = None,
) -> tuple[str, dict]:
    """Build (gene × term) detail query. Dispatches on (level, term_ids).

    `organism` is required (single-organism contract).

    Mode 1: term_ids only — walk DOWN.
    Mode 2: level only — walk UP, filter on level.
    Mode 3: level + term_ids — walk UP, filter on level AND input_tids.

    RETURN keys (compact): locus_tag, gene_name, product, gene_category,
    term_id, term_name, level.
    RETURN keys (verbose): adds function_description, level_is_best_effort.
    """
    # Validation stays in the builder (helper would also need it, but the
    # detail-builder tests expect `match="level.*term_ids"`).
    if level is None and not term_ids:
        raise ValueError(
            "At least one of `level` or `term_ids` must be provided."
        )
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError(
            "max_gene_set_size must be >= min_gene_set_size."
        )

    head, params = _genes_by_ontology_match_stage(
        ontology=ontology, level=level, term_ids=term_ids, organism=organism,
        tree=tree,
    )
    params["min_gene_set_size"] = min_gene_set_size
    params["max_gene_set_size"] = max_gene_set_size

    # Row return
    verbose_cols = (
        ",\n       g.function_description AS function_description,\n"
        "       t.level_is_best_effort IS NOT NULL AS level_is_best_effort"
        if verbose else ""
    )
    return_block = (
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.gene_category AS gene_category,\n"
        "       t.id AS term_id, t.name AS term_name, t.level AS level,\n"
        "       t.tree AS tree, t.tree_code AS tree_code"
        f"{verbose_cols}\n"
        "ORDER BY t.id, g.locus_tag"
    )

    # Pagination
    skip_clause = ""
    limit_clause = ""
    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit

    cypher = (
        f"{head}\n"
        f"UNWIND term_genes AS g\n"
        f"{return_block}{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_genes_by_ontology_per_term(
    *,
    ontology: str,
    organism: str,
    level: int | None,
    term_ids: list[str] | None,
    min_gene_set_size: int,
    max_gene_set_size: int | None,
    tree: str | None = None,
) -> tuple[str, dict]:
    """Per-term aggregate. One row per surviving term.

    `organism` is required (single-organism contract). Feeds summary fields
    such as `top_terms`, `by_level.n_terms`, `by_level.row_count`,
    `n_best_effort_terms`, and `filtered_out` detection.

    Mode 1: term_ids only — walk DOWN.
    Mode 2: level only — walk UP, filter on level.
    Mode 3: level + term_ids — walk UP, filter on level AND input_tids.

    RETURN keys: term_id, term_name, level, best_effort, n_genes, cat_freqs.
    """
    head, params = _genes_by_ontology_match_stage(
        ontology=ontology, level=level, term_ids=term_ids, organism=organism,
        tree=tree,
    )
    params["min_gene_set_size"] = min_gene_set_size
    params["max_gene_set_size"] = max_gene_set_size

    tail = (
        "UNWIND term_genes AS g\n"
        "WITH t, collect({lt: g.locus_tag, "
        "cat: coalesce(g.gene_category, 'Unknown')}) AS gene_rows\n"
        "RETURN t.id AS term_id, t.name AS term_name, t.level AS level,\n"
        "       t.tree AS tree, t.tree_code AS tree_code,\n"
        "       t.level_is_best_effort IS NOT NULL AS best_effort,\n"
        "       size(gene_rows) AS n_genes,\n"
        "       apoc.coll.frequencies("
        "[r IN gene_rows | r.cat]) AS cat_freqs\n"
        "ORDER BY t.id"
    )
    return f"{head}\n{tail}", params


def build_genes_by_ontology_per_gene(
    *,
    ontology: str,
    organism: str,
    level: int | None,
    term_ids: list[str] | None,
    min_gene_set_size: int,
    max_gene_set_size: int | None,
    tree: str | None = None,
) -> tuple[str, dict]:
    """Per-gene aggregate. One row per surviving gene.

    RETURN keys: locus_tag, gene_category, n_terms, levels_hit.
    `levels_hit` is the distinct set of term levels each gene was reached
    via — used by L2 to compute by_level.n_genes via set-union.
    """
    head, params = _genes_by_ontology_match_stage(
        ontology=ontology, level=level, term_ids=term_ids, organism=organism,
        tree=tree,
    )
    params["min_gene_set_size"] = min_gene_set_size
    params["max_gene_set_size"] = max_gene_set_size
    tail = (
        "UNWIND term_genes AS g\n"
        "WITH g, collect(DISTINCT t.id) AS gene_terms, "
        "collect(DISTINCT t.level) AS gene_levels\n"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       coalesce(g.gene_category, 'Unknown') AS gene_category,\n"
        "       size(gene_terms) AS n_terms,\n"
        "       gene_levels AS levels_hit\n"
        "ORDER BY g.locus_tag"
    )
    return f"{head}\n{tail}", params


def _gene_ontology_terms_leaf_filter(cfg: dict) -> str:
    """Return a WHERE NOT EXISTS clause for leaf filtering, or empty string.

    Leaf filtering is meaningful only when genes can be annotated to both
    a child and its ancestor within the same label. Skipped for:
    - Flat ontologies (no hierarchy_rels): cog_category, tigr_role
    - Cross-label hierarchies (parent_label present): pfam (Pfam→PfamClan)

    For KEGG, gene→KeggTerm edges only terminate at ko leaves (enforced by
    graph structure), so the NOT EXISTS clause is a no-op but still emitted
    — the query optimizer handles it cheaply.
    """
    hierarchy_rels = cfg["hierarchy_rels"]
    if not hierarchy_rels:
        return ""
    if cfg.get("parent_label"):
        return ""
    if cfg.get("bridge"):
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
    organism_name: str,
    mode: str = "leaf",
    level: int | None = None,
    tree: str | None = None,
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
    if mode == "rollup" and level is None:
        raise ValueError("level is required when mode='rollup'")
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
    cfg = ONTOLOGY_CONFIG[ontology]
    gene_rel = cfg["gene_rel"]
    label = cfg["label"]

    params: dict = {"locus_tags": locus_tags, "org": organism_name}

    bridge = cfg.get("bridge")

    if mode == "rollup":
        # --- rollup: walk leaf → ancestor at target level ---
        if bridge:
            bridge_edge = bridge["edge"]
            bridge_node = bridge["node_label"]
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(ko:{bridge_node})"
                f"-[:{bridge_edge}]->(leaf:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
            rel_union = "|".join(cfg["hierarchy_rels"])
            walk = (
                f"MATCH (leaf)-[:{rel_union}*0..]->(t:{label})\n"
                "WHERE t.level = $level\n"
            )
        elif not cfg["hierarchy_rels"]:
            # flat: leaf = term, walk is identity
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(t:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
            walk = "WITH g, t\nWHERE t.level = $level\n"
        elif ontology == "pfam":
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(leaf:Pfam)\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
            walk = (
                "MATCH (leaf)-[:Pfam_in_pfam_clan*0..1]->(t)\n"
                "WHERE (t:Pfam OR t:PfamClan) AND t.level = $level\n"
            )
        else:
            rel_union = "|".join(cfg["hierarchy_rels"])
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(leaf:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
            walk = (
                f"MATCH (leaf)-[:{rel_union}*0..]->(t:{label})\n"
                "WHERE t.level = $level\n"
            )
        params["level"] = level
        tree_filter = ""
        if tree is not None:
            tree_filter = "AND t.tree = $tree\n"
            params["tree"] = tree
        cypher = (
            f"{bind}"
            f"{walk}"
            f"{tree_filter}"
            "WITH g.locus_tag AS lt, collect(DISTINCT {id: t.id, name: t.name, level: t.level, tree: t.tree, tree_code: t.tree_code}) AS terms\n"
            "WITH collect({lt: lt, cnt: size(terms), terms: terms}) AS genes\n"
            "WITH genes,\n"
            "     apoc.coll.flatten([g IN genes | g.terms]) AS all_terms,\n"
            "     [g IN genes | {locus_tag: g.lt, term_count: g.cnt}] AS gene_term_counts\n"
            "UNWIND all_terms AS t\n"
            "WITH genes, gene_term_counts, t.id AS tid, t.name AS tname, t.level AS tlevel, t.tree AS ttree, t.tree_code AS ttree_code, count(*) AS cnt\n"
            "WITH genes, gene_term_counts,\n"
            "     collect({term_id: tid, term_name: tname, level: tlevel, tree: ttree, tree_code: ttree_code, count: cnt}) AS by_term\n"
            "RETURN size(genes) AS gene_count,\n"
            "       size(apoc.coll.flatten([g IN genes | g.terms])) AS term_count,\n"
            "       by_term,\n"
            "       gene_term_counts"
        )
    else:
        # --- leaf mode ---
        leaf_filter = _gene_ontology_terms_leaf_filter(cfg)

        if bridge:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(:{bridge['node_label']})"
                f"-[:{bridge['edge']}]->(t:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
        else:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})-[:{gene_rel}]->(t:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )

        # Convert leaf_filter "WHERE NOT EXISTS ..." to "AND NOT EXISTS ..."
        if leaf_filter:
            leaf_filter = "AND " + leaf_filter.replace("WHERE ", "", 1)

        level_filter = ""
        if level is not None:
            level_filter = "AND t.level = $level\n"
            params["level"] = level
        tree_filter = ""
        if tree is not None:
            tree_filter = "AND t.tree = $tree\n"
            params["tree"] = tree

        cypher = (
            f"{match_line}"
            f"{leaf_filter}"
            f"{level_filter}"
            f"{tree_filter}"
            "WITH g.locus_tag AS lt, collect({id: t.id, name: t.name, level: t.level, tree: t.tree, tree_code: t.tree_code}) AS terms\n"
            "WITH collect({lt: lt, cnt: size(terms), terms: terms}) AS genes\n"
            "WITH genes,\n"
            "     apoc.coll.flatten([g IN genes | g.terms]) AS all_terms,\n"
            "     [g IN genes | {locus_tag: g.lt, term_count: g.cnt}] AS gene_term_counts\n"
            "UNWIND all_terms AS t\n"
            "WITH genes, gene_term_counts, t.id AS tid, t.name AS tname, t.level AS tlevel, t.tree AS ttree, t.tree_code AS ttree_code, count(*) AS cnt\n"
            "WITH genes, gene_term_counts,\n"
            "     collect({term_id: tid, term_name: tname, level: tlevel, tree: ttree, tree_code: ttree_code, count: cnt}) AS by_term\n"
            "RETURN size(genes) AS gene_count,\n"
            "       size(apoc.coll.flatten([g IN genes | g.terms])) AS term_count,\n"
            "       by_term,\n"
            "       gene_term_counts"
        )
    return cypher, params


def build_gene_ontology_terms(
    *,
    locus_tags: list[str],
    ontology: str,
    organism_name: str,
    mode: str = "leaf",
    level: int | None = None,
    tree: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_ontology_terms for ONE ontology.

    RETURN keys (compact): locus_tag, term_id, term_name, level, tree, tree_code.
    RETURN keys (verbose): adds organism_name.

    Called by api/ — which adds ontology_type column and merges
    across ontologies when ontology=None.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    if mode == "rollup" and level is None:
        raise ValueError("level is required when mode='rollup'")
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
    cfg = ONTOLOGY_CONFIG[ontology]
    gene_rel = cfg["gene_rel"]
    label = cfg["label"]

    params: dict = {"locus_tags": locus_tags, "org": organism_name}

    verbose_cols = (
        ",\n       g.organism_name AS organism_name"
        if verbose else ""
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    bridge = cfg.get("bridge")

    if mode == "rollup":
        # --- rollup: walk leaf → ancestor at target level ---
        params["level"] = level
        if bridge:
            bridge_edge = bridge["edge"]
            bridge_node = bridge["node_label"]
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(ko:{bridge_node})"
                f"-[:{bridge_edge}]->(leaf:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
            rel_union = "|".join(cfg["hierarchy_rels"])
            walk = (
                f"MATCH (leaf)-[:{rel_union}*0..]->(t:{label})\n"
                "WHERE t.level = $level\n"
            )
        elif not cfg["hierarchy_rels"]:
            # flat: leaf = term
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(t:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
            walk = "WITH g, t\nWHERE t.level = $level\n"
        elif ontology == "pfam":
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(leaf:Pfam)\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
            walk = (
                "MATCH (leaf)-[:Pfam_in_pfam_clan*0..1]->(t)\n"
                "WHERE (t:Pfam OR t:PfamClan) AND t.level = $level\n"
            )
        else:
            rel_union = "|".join(cfg["hierarchy_rels"])
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(leaf:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
            walk = (
                f"MATCH (leaf)-[:{rel_union}*0..]->(t:{label})\n"
                "WHERE t.level = $level\n"
            )
        tree_filter = ""
        if tree is not None:
            tree_filter = "AND t.tree = $tree\n"
            params["tree"] = tree
        cypher = (
            f"{bind}"
            f"{walk}"
            f"{tree_filter}"
            "RETURN DISTINCT g.locus_tag AS locus_tag, t.id AS term_id,\n"
            f"       t.name AS term_name, t.level AS level, t.tree AS tree, t.tree_code AS tree_code{verbose_cols}\n"
            f"ORDER BY g.locus_tag, t.id{skip_clause}{limit_clause}"
        )
    else:
        # --- leaf mode ---
        leaf_filter = _gene_ontology_terms_leaf_filter(cfg)

        if bridge:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(:{bridge['node_label']})"
                f"-[:{bridge['edge']}]->(t:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )
        else:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})-[:{gene_rel}]->(t:{label})\n"
                "WHERE g.locus_tag IN $locus_tags\n"
            )

        # Convert leaf_filter "WHERE NOT EXISTS ..." to "AND NOT EXISTS ..."
        if leaf_filter:
            leaf_filter = "AND " + leaf_filter.replace("WHERE ", "", 1)

        level_filter = ""
        if level is not None:
            level_filter = "AND t.level = $level\n"
            params["level"] = level
        tree_filter = ""
        if tree is not None:
            tree_filter = "AND t.tree = $tree\n"
            params["tree"] = tree

        cypher = (
            f"{match_line}"
            f"{leaf_filter}"
            f"{level_filter}"
            f"{tree_filter}"
            "RETURN g.locus_tag AS locus_tag, t.id AS term_id,\n"
            f"       t.name AS term_name, t.level AS level, t.tree AS tree, t.tree_code AS tree_code{verbose_cols}\n"
            f"ORDER BY g.locus_tag, t.id{skip_clause}{limit_clause}"
        )
    return cypher, params


def build_gene_existence_check(
    *, locus_tags: list[str],
) -> tuple[str, dict]:
    """Build query to check which locus_tags exist in the KG.

    RETURN keys: lt, found.
    """
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "RETURN lt, g IS NOT NULL AS found"
    )
    return cypher, {"locus_tags": locus_tags}


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
    growth_phases: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params shared by all de_by_gene builders.

    direction takes precedence over significant_only (direction implies
    significance). organism uses fuzzy word-based matching (same as
    list_experiments). growth_phases filters on the edge-level r.growth_phase
    property (case-insensitive).
    """
    conditions: list[str] = []
    params: dict = {}
    if organism:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(e.organism_name) CONTAINS word)"
        )
        params["organism"] = organism
    if locus_tags:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if experiment_ids:
        conditions.append("e.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    if direction == "up":
        conditions.append("r.expression_status = 'significant_up'")
    elif direction == "down":
        conditions.append("r.expression_status = 'significant_down'")
    elif significant_only:
        conditions.append("r.expression_status <> 'not_significant'")
    if growth_phases:
        conditions.append("toLower(r.growth_phase) IN $growth_phases")
        params["growth_phases"] = [gp.lower() for gp in growth_phases]
    return conditions, params


# ---------------------------------------------------------------------------
# Organism pre-validation builders (differential expression)
# ---------------------------------------------------------------------------


def build_resolve_organism_for_organism(
    *, organism: str,
) -> tuple[str, dict]:
    """Resolve distinct organism_name values for a fuzzy organism name.

    RETURN keys: organisms (list[str]).
    Uses the same word-based CONTAINS matching as list_experiments.
    """
    cypher = (
        "MATCH (e:Experiment)\n"
        "WHERE e.gene_count > 0\n"
        "  AND ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(e.organism_name) CONTAINS word)\n"
        "RETURN collect(DISTINCT e.organism_name) AS organisms"
    )
    return cypher, {"organism": organism}


def build_resolve_organism_for_locus_tags(
    *, locus_tags: list[str],
) -> tuple[str, dict]:
    """Resolve distinct organism_name values for a list of locus_tags.

    RETURN keys: organisms (list[str]).
    """
    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})\n"
        "RETURN collect(DISTINCT g.organism_name) AS organisms"
    )
    return cypher, {"locus_tags": locus_tags}


def build_resolve_organism_for_experiments(
    *, experiment_ids: list[str],
) -> tuple[str, dict]:
    """Resolve distinct organism_name values for a list of experiment IDs.

    RETURN keys: organisms (list[str]).
    """
    cypher = (
        "UNWIND $experiment_ids AS eid\n"
        "MATCH (e:Experiment {id: eid})\n"
        "RETURN collect(DISTINCT e.organism_name) AS organisms"
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
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Global aggregate stats for differential_expression_by_gene.

    RETURN keys: total_matching, matching_genes, rows_by_status,
    rows_by_treatment_type, rows_by_background_factors,
    by_table_scope, rows_by_growth_phase, median_abs_log2fc, max_abs_log2fc.
    rows_by_status = apoc list [{item, count}] — api/ converts to dict.
    rows_by_treatment_type = apoc list [{item, count}] — api/ converts to dict.
    rows_by_background_factors = apoc list [{item, count}] — api/ converts to dict.
    by_table_scope = apoc list [{item, count}] — api/ converts to dict.
    rows_by_growth_phase = apoc list [{item, count}] — api/ converts to dict.
    """
    conditions, params = _differential_expression_where(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=experiment_ids, direction=direction,
        significant_only=significant_only, growth_phases=growth_phases,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
        f"{where_block}"
        "RETURN count(*) AS total_matching,\n"
        "       count(DISTINCT g.locus_tag) AS matching_genes,\n"
        "       apoc.coll.frequencies(collect(r.expression_status)) AS rows_by_status,\n"
        "       apoc.coll.frequencies(apoc.coll.flatten(collect(coalesce(e.treatment_type, [])))) AS rows_by_treatment_type,\n"
        "       apoc.coll.frequencies(apoc.coll.flatten(collect(coalesce(e.background_factors, [])))) AS rows_by_background_factors,\n"
        "       apoc.coll.frequencies(collect(e.table_scope)) AS by_table_scope,\n"
        "       apoc.coll.frequencies(collect(r.growth_phase)) AS rows_by_growth_phase,\n"
        "       percentileCont(\n"
        "           CASE WHEN r.expression_status <> 'not_significant'\n"
        "                THEN abs(r.log2_fold_change) ELSE null END, 0.5\n"
        "       ) AS median_abs_log2fc,\n"
        "       max(CASE WHEN r.expression_status <> 'not_significant'\n"
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
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Per-experiment breakdown with nested timepoints (single organism enforced).

    RETURN keys: organism_name, experiments.
    experiments: list of dicts, each with nested timepoints.
    rows_by_status at both experiment and timepoint level (APOC list format).
    is_time_course included per experiment so api/ can null-out timepoints.
    timepoints include growth_phase from the edge.
    """
    conditions, params = _differential_expression_where(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=experiment_ids, direction=direction,
        significant_only=significant_only, growth_phases=growth_phases,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
        f"{where_block}"
        "WITH e, r.time_point AS tp, r.time_point_order AS tpo,"
        " r.time_point_hours AS tph, r.growth_phase AS gp,\n"
        "     collect(DISTINCT g.locus_tag) AS tp_genes,\n"
        "     collect(r.expression_status) AS tp_calls\n"
        "WITH e,\n"
        "     size(apoc.coll.toSet(apoc.coll.flatten(collect(tp_genes))))"
        " AS matching_genes,\n"
        "     apoc.coll.frequencies(apoc.coll.flatten(collect(tp_calls)))"
        " AS rows_by_status,\n"
        "     collect({timepoint: tp, timepoint_hours: tph,"
        " timepoint_order: tpo, growth_phase: gp,\n"
        "              matching_genes: size(tp_genes),\n"
        "              rows_by_status: apoc.coll.frequencies(tp_calls)})"
        " AS timepoints\n"
        "WITH collect({experiment_id: e.id, experiment_name: e.name,\n"
        "              treatment_type: e.treatment_type,"
        " omics_type: e.omics_type,\n"
        "              background_factors: coalesce(e.background_factors, []),\n"
        "              coculture_partner: e.coculture_partner,\n"
        "              is_time_course: e.is_time_course,\n"
        "              table_scope: e.table_scope,\n"
        "              table_scope_detail: e.table_scope_detail,\n"
        "              matching_genes: matching_genes,\n"
        "              rows_by_status: rows_by_status,\n"
        "              timepoints: timepoints}) AS experiments,\n"
        "     e.organism_name AS organism_name\n"
        "RETURN organism_name, experiments"
    )
    return cypher, params


def build_differential_expression_by_gene_summary_diagnostics(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
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
            significant_only=significant_only, growth_phases=growth_phases,
        )
        where_block = (
            "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
        )
        cypher = (
            "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
            f"{where_block}"
            "WITH g.gene_category AS category,\n"
            "     count(DISTINCT g.locus_tag) AS total_genes,\n"
            "     count(DISTINCT CASE WHEN r.expression_status <> 'not_significant'\n"
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
        significant_only=significant_only, growth_phases=growth_phases,
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
        "     count(DISTINCT CASE WHEN r.expression_status <> 'not_significant'\n"
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
    growth_phases: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for differential_expression_by_gene.

    RETURN keys (compact — 14): locus_tag, gene_name,
    experiment_id, treatment_type, timepoint, timepoint_hours, timepoint_order,
    log2fc, padj, rank, rank_up, rank_down, expression_status, growth_phase.
    RETURN keys (verbose): adds product, experiment_name, treatment,
    gene_category, omics_type, coculture_partner, table_scope,
    table_scope_detail.
    """
    conditions, params = _differential_expression_where(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=experiment_ids, direction=direction,
        significant_only=significant_only, growth_phases=growth_phases,
    )
    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = (
        ",\n       g.product AS product"
        ",\n       e.name AS experiment_name"
        ",\n       e.treatment AS treatment"
        ",\n       g.gene_category AS gene_category"
        ",\n       e.omics_type AS omics_type"
        ",\n       e.coculture_partner AS coculture_partner"
        ",\n       e.table_scope AS table_scope"
        ",\n       e.table_scope_detail AS table_scope_detail"
        ",\n       coalesce(e.background_factors, []) AS background_factors"
        if verbose else ""
    )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
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
        "       r.rank_up AS rank_up,\n"
        "       r.rank_down AS rank_down,\n"
        "       r.expression_status AS expression_status"
        ",\n       r.growth_phase AS growth_phase"
        f"{verbose_cols}\n"
        "ORDER BY ABS(r.log2_fold_change) DESC, g.locus_tag ASC,"
        " e.id ASC, r.time_point_order ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_search_homolog_groups_summary(
    *,
    search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for search_homolog_groups.

    RETURN keys: total_entries, total_matching, score_max, score_median,
    by_source, by_level, top_cyanorak_roles, top_cog_categories.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles,
        cog_categories=cog_categories,
    )
    params["search_text"] = search_text

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "CALL db.index.fulltext.queryNodes('orthologGroupFullText', $search_text)\n"
        "YIELD node AS og, score\n"
        f"{where_block}"
        "OPTIONAL MATCH (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
        "OPTIONAL MATCH (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
        "WITH collect({src: og.source, lvl: og.taxonomic_level,\n"
        "              cr_id: cr.id, cr_name: cr.name,\n"
        "              cc_id: cc.id, cc_name: cc.name}) AS rows,\n"
        "     count(DISTINCT og) AS total_matching,\n"
        "     max(score) AS score_max,\n"
        "     percentileDisc(score, 0.5) AS score_median\n"
        "CALL { MATCH (all_og:OrthologGroup) RETURN count(all_og) AS total_entries }\n"
        "WITH *, [r IN rows | r.src] AS sources,\n"
        "        [r IN rows | r.lvl] AS levels,\n"
        "        [r IN rows WHERE r.cr_id IS NOT NULL | r.cr_id + ' | ' + r.cr_name] AS cr_items,\n"
        "        [r IN rows WHERE r.cc_id IS NOT NULL | r.cc_id + ' | ' + r.cc_name] AS cc_items\n"
        "WITH total_entries, total_matching, score_max, score_median,\n"
        "     apoc.coll.frequencies(sources) AS by_source,\n"
        "     apoc.coll.frequencies(levels) AS by_level,\n"
        "     apoc.coll.frequencies(cr_items) AS cr_freq,\n"
        "     apoc.coll.frequencies(cc_items) AS cc_freq\n"
        "RETURN total_entries, total_matching, score_max, score_median,\n"
        "       by_source, by_level,\n"
        "       apoc.coll.sortMaps(\n"
        "         [x IN cr_freq | {id: split(x.item, ' | ')[0],\n"
        "                          name: split(x.item, ' | ')[1],\n"
        "                          count: x.count}],\n"
        "         'count')[0..5] AS top_cyanorak_roles,\n"
        "       apoc.coll.sortMaps(\n"
        "         [x IN cc_freq | {id: split(x.item, ' | ')[0],\n"
        "                          name: split(x.item, ' | ')[1],\n"
        "                          count: x.count}],\n"
        "         'count')[0..5] AS top_cog_categories"
    )
    return cypher, params


def build_search_homolog_groups(
    *,
    search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build Cypher for search_homolog_groups.

    RETURN keys (compact): group_id, group_name, consensus_gene_name,
    consensus_product, source, taxonomic_level, specificity_rank,
    member_count, organism_count, score.
    RETURN keys (verbose): adds description, functional_description,
    genera, has_cross_genus_members, cyanorak_roles, cog_categories.
    """
    conditions, params = _gene_homologs_og_where(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles,
        cog_categories=cog_categories,
    )
    params["search_text"] = search_text

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    if verbose:
        cypher = (
            "CALL db.index.fulltext.queryNodes('orthologGroupFullText', $search_text)\n"
            "YIELD node AS og, score\n"
            f"{where_block}"
            "OPTIONAL MATCH (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)\n"
            "OPTIONAL MATCH (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)\n"
            "WITH og, score,\n"
            "     [x IN collect(DISTINCT {id: cr.id, name: cr.name}) WHERE x.id IS NOT NULL] AS cyanorak_roles,\n"
            "     [x IN collect(DISTINCT {id: cc.id, name: cc.name}) WHERE x.id IS NOT NULL] AS cog_categories\n"
            "RETURN og.id AS group_id, og.name AS group_name,\n"
            "       og.consensus_gene_name AS consensus_gene_name,\n"
            "       og.consensus_product AS consensus_product,\n"
            "       og.source AS source, og.taxonomic_level AS taxonomic_level,\n"
            "       og.specificity_rank AS specificity_rank,\n"
            "       og.member_count AS member_count, og.organism_count AS organism_count,\n"
            "       score,\n"
            "       og.description AS description,\n"
            "       og.functional_description AS functional_description,\n"
            "       og.genera AS genera,\n"
            "       og.has_cross_genus_members AS has_cross_genus_members,\n"
            "       cyanorak_roles, cog_categories\n"
            f"ORDER BY score DESC, og.specificity_rank, og.source, og.id{skip_clause}{limit_clause}"
        )
    else:
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
            f"       score\n"
            f"ORDER BY score DESC, og.specificity_rank, og.source, og.id{skip_clause}{limit_clause}"
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
        "             WHERE toLower(g.organism_name) CONTAINS word)))\n"
        "WITH gid, og, g\n"
        "WITH collect(DISTINCT CASE WHEN og IS NULL THEN gid END) AS nf_groups_raw,\n"
        "     collect(DISTINCT CASE WHEN og IS NOT NULL AND g IS NULL\n"
        "             THEN gid END) AS nm_groups_raw,\n"
        "     collect(CASE WHEN g IS NOT NULL THEN\n"
        "       {lt: g.locus_tag, org: g.organism_name,\n"
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
        "          WHERE toLower(g_any.organism_name) CONTAINS word)\n"
        "WITH org_input, count(g_any) AS kg_count\n"
        "OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        "WHERE org_input IS NOT NULL AND kg_count > 0\n"
        "  AND og.id IN $group_ids\n"
        "  AND ALL(word IN split(toLower(org_input), ' ')\n"
        "          WHERE toLower(g.organism_name) CONTAINS word)\n"
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
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_homolog_group.

    RETURN keys (compact): locus_tag, gene_name, product,
    organism_name, gene_category, group_id.
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

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
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
        "             WHERE toLower(g.organism_name) CONTAINS word)))\n"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_name AS organism_name,\n"
        f"       g.gene_category AS gene_category, og.id AS group_id{verbose_cols}\n"
        f"ORDER BY og.id, g.organism_name, g.locus_tag{skip_clause}{limit_clause}"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Differential expression by ortholog — shared WHERE helper
# ---------------------------------------------------------------------------


def _differential_expression_by_ortholog_where(
    *,
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params shared by de_by_ortholog builders.

    organisms is a list with OR semantics (any matching organism).
    direction takes precedence over significant_only. growth_phases filters
    on the edge-level r.growth_phase property (case-insensitive).
    """
    conditions: list[str] = []
    params: dict = {}
    if organisms:
        conditions.append(
            "ANY(org_input IN $organisms"
            " WHERE ALL(word IN split(toLower(org_input), ' ')"
            " WHERE toLower(e.organism_name) CONTAINS word))"
        )
        params["organisms"] = organisms
    if experiment_ids:
        conditions.append("e.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    if direction == "up":
        conditions.append("r.expression_status = 'significant_up'")
    elif direction == "down":
        conditions.append("r.expression_status = 'significant_down'")
    elif significant_only:
        conditions.append("r.expression_status <> 'not_significant'")
    if growth_phases:
        conditions.append("toLower(r.growth_phase) IN $growth_phases")
        params["growth_phases"] = [gp.lower() for gp in growth_phases]
    return conditions, params


# ---------------------------------------------------------------------------
# Differential expression by ortholog — summary builders
# ---------------------------------------------------------------------------


def build_differential_expression_by_ortholog_group_check(
    *,
    group_ids: list[str],
) -> tuple[str, dict]:
    """Check which group_ids exist as OrthologGroup nodes.

    RETURN keys: not_found (list[str]).
    """
    cypher = (
        "UNWIND $group_ids AS gid\n"
        "OPTIONAL MATCH (og:OrthologGroup {id: gid})\n"
        "WITH collect(CASE WHEN og IS NULL THEN gid END) AS nf_raw\n"
        "RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found"
    )
    return cypher, {"group_ids": group_ids}


def build_differential_expression_by_ortholog_summary_global(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Global aggregate stats for differential_expression_by_ortholog.

    Uses MATCH (not OPTIONAL) — caller should pass only found group_ids.

    RETURN keys: total_matching, matching_genes, matching_groups,
    experiment_count, by_organism, rows_by_status, rows_by_treatment_type,
    rows_by_background_factors, by_table_scope, rows_by_growth_phase,
    sig_log2fcs, matched_group_ids.
    """
    conditions, params = _differential_expression_by_ortholog_where(
        organisms=organisms, experiment_ids=experiment_ids,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "MATCH (og:OrthologGroup {id: gid})\n"
        "MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og)\n"
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n"
        f"{where_block}"
        "WITH gid, g.locus_tag AS lt, e.organism_name AS org,\n"
        "     r.expression_status AS status, e.treatment_type AS tt,\n"
        "     e.background_factors AS bfs, e.table_scope AS ts, e.id AS eid,\n"
        "     r.log2_fold_change AS log2fc, r.growth_phase AS gp\n"
        "WITH collect({gid: gid, lt: lt, org: org,\n"
        "              status: status, tt: tt, bfs: bfs, ts: ts,\n"
        "              eid: eid, log2fc: log2fc, gp: gp}) AS rows\n"
        "RETURN size(rows) AS total_matching,\n"
        "       size(apoc.coll.toSet([r IN rows | r.lt])) AS matching_genes,\n"
        "       size(apoc.coll.toSet([r IN rows | r.gid])) AS matching_groups,\n"
        "       size(apoc.coll.toSet([r IN rows | r.eid])) AS experiment_count,\n"
        "       apoc.coll.frequencies([r IN rows | r.org]) AS by_organism,\n"
        "       apoc.coll.frequencies([r IN rows | r.status]) AS rows_by_status,\n"
        "       apoc.coll.frequencies(apoc.coll.flatten([r IN rows | coalesce(r.tt, [])])) AS rows_by_treatment_type,\n"
        "       apoc.coll.frequencies(apoc.coll.flatten([r IN rows | coalesce(r.bfs, [])])) AS rows_by_background_factors,\n"
        "       apoc.coll.frequencies([r IN rows | r.ts]) AS by_table_scope,\n"
        "       apoc.coll.frequencies([r IN rows | r.gp]) AS rows_by_growth_phase,\n"
        "       apoc.coll.toSet([r IN rows | r.gid]) AS matched_group_ids,\n"
        "       [r IN rows WHERE r.status <> 'not_significant' | abs(r.log2fc)]"
        " AS sig_log2fcs"
    )
    return cypher, params


def build_differential_expression_by_ortholog_top_groups(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Top ortholog groups by significant gene count.

    RETURN keys: top_groups (list of dicts with group_id,
    consensus_gene_name, consensus_product, significant_genes, total_genes).
    """
    conditions, params = _differential_expression_by_ortholog_where(
        organisms=organisms, experiment_ids=experiment_ids,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})\n"
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n"
        f"{where_block}"
        "WITH og,\n"
        "     count(DISTINCT g.locus_tag) AS total_genes,\n"
        "     count(DISTINCT CASE WHEN r.expression_status <> 'not_significant'\n"
        "                         THEN g.locus_tag END) AS significant_genes\n"
        "ORDER BY significant_genes DESC, og.id ASC\n"
        "LIMIT 5\n"
        "RETURN collect({\n"
        "  group_id: og.id,\n"
        "  consensus_gene_name: og.consensus_gene_name,\n"
        "  consensus_product: og.consensus_product,\n"
        "  significant_genes: significant_genes,\n"
        "  total_genes: total_genes\n"
        "}) AS top_groups"
    )
    return cypher, params


def build_differential_expression_by_ortholog_top_experiments(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Top experiments by significant gene count across ortholog groups.

    RETURN keys: top_experiments (list of dicts with experiment_id,
    treatment_type, organism_name, significant_genes).
    """
    conditions, params = _differential_expression_by_ortholog_where(
        organisms=organisms, experiment_ids=experiment_ids,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})\n"
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n"
        f"{where_block}"
        "WITH e,\n"
        "     count(DISTINCT CASE WHEN r.expression_status <> 'not_significant'\n"
        "                         THEN g.locus_tag END) AS significant_genes\n"
        "ORDER BY significant_genes DESC, e.id ASC\n"
        "LIMIT 5\n"
        "RETURN collect({\n"
        "  experiment_id: e.id,\n"
        "  treatment_type: e.treatment_type,\n"
        "  background_factors: coalesce(e.background_factors, []),\n"
        "  organism_name: e.organism_name,\n"
        "  significant_genes: significant_genes\n"
        "}) AS top_experiments"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Differential expression by ortholog — detail builder
# ---------------------------------------------------------------------------


def build_differential_expression_by_ortholog_results(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for differential_expression_by_ortholog.

    RETURN keys (compact — 14): group_id, consensus_gene_name,
    consensus_product, experiment_id, treatment_type, organism_name,
    coculture_partner, timepoint, timepoint_hours, timepoint_order,
    growth_phase, genes_with_expression, significant_up, significant_down,
    not_significant.
    RETURN keys (verbose): adds experiment_name, treatment, omics_type,
    table_scope, table_scope_detail.
    """
    conditions, params = _differential_expression_by_ortholog_where(
        organisms=organisms, experiment_ids=experiment_ids,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = (
        ",\n       e.name AS experiment_name"
        ",\n       e.treatment AS treatment"
        ",\n       e.omics_type AS omics_type"
        ",\n       e.table_scope AS table_scope"
        ",\n       e.table_scope_detail AS table_scope_detail"
        if verbose else ""
    )

    if offset:
        params["offset"] = offset
    if limit is not None:
        params["limit"] = limit

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})\n"
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n"
        f"{where_block}"
        "WITH og, e,\n"
        "     r.time_point AS tp,\n"
        "     r.time_point_hours AS tph,\n"
        "     r.time_point_order AS tpo,\n"
        "     r.growth_phase AS gp,\n"
        "     collect(DISTINCT g.locus_tag) AS genes,\n"
        "     collect(r.expression_status) AS statuses\n"
        "RETURN og.id AS group_id,\n"
        "       og.consensus_gene_name AS consensus_gene_name,\n"
        "       og.consensus_product AS consensus_product,\n"
        "       e.id AS experiment_id,\n"
        "       e.treatment_type AS treatment_type,\n"
        "       coalesce(e.background_factors, []) AS background_factors,\n"
        "       e.organism_name AS organism_name,\n"
        "       e.coculture_partner AS coculture_partner,\n"
        "       tp AS timepoint,\n"
        "       tph AS timepoint_hours,\n"
        "       tpo AS timepoint_order,\n"
        "       gp AS growth_phase,\n"
        "       size(genes) AS genes_with_expression,\n"
        "       size([s IN statuses WHERE s = 'significant_up']) AS significant_up,\n"
        "       size([s IN statuses WHERE s = 'significant_down']) AS significant_down,\n"
        "       size([s IN statuses WHERE s = 'not_significant']) AS not_significant"
        f"{verbose_cols}\n"
        "ORDER BY og.id ASC, e.id ASC, tpo ASC\n"
    )
    if offset:
        cypher += "SKIP $offset\n"
    if limit is not None:
        cypher += "LIMIT $limit"
    return cypher, params


# ---------------------------------------------------------------------------
# Differential expression by ortholog — membership counts
# ---------------------------------------------------------------------------


def build_differential_expression_by_ortholog_membership_counts(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
) -> tuple[str, dict]:
    """Gene counts per ortholog group per organism (no expression filter).

    RETURN keys: group_id, organism_name, total_genes.
    """
    params: dict = {"group_ids": group_ids, "organisms": organisms}

    cypher = (
        "UNWIND $group_ids AS gid\n"
        "MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup {id: gid})\n"
        "WHERE ($organisms IS NULL OR ANY(org_input IN $organisms\n"
        "       WHERE ALL(word IN split(toLower(org_input), ' ')\n"
        "             WHERE toLower(g.organism_name) CONTAINS word)))\n"
        "RETURN og.id AS group_id,\n"
        "       g.organism_name AS organism_name,\n"
        "       count(g) AS total_genes\n"
        "ORDER BY og.id ASC, g.organism_name ASC"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Differential expression by ortholog — diagnostics
# ---------------------------------------------------------------------------


def _build_de_by_ortholog_organism_diagnostics(
    *,
    group_ids: list[str],
    organisms: list[str],
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Validate organisms against KG + expression in ortholog groups.

    RETURN keys: not_found_organisms, not_matched_organisms.
    """
    # Build expression WHERE conditions WITHOUT organism filter
    conditions_no_org, params = _differential_expression_by_ortholog_where(
        organisms=None, experiment_ids=experiment_ids,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids
    params["organisms"] = organisms

    expression_where = (
        "\nWHERE " + " AND ".join(conditions_no_org)
        if conditions_no_org else ""
    )

    cypher = (
        "WITH $organisms AS org_inputs\n"
        "UNWIND CASE WHEN org_inputs IS NULL THEN [null]\n"
        "       ELSE org_inputs END AS org_input\n"
        "OPTIONAL MATCH (g_any:Gene)\n"
        "WHERE org_input IS NOT NULL\n"
        "  AND ALL(word IN split(toLower(org_input), ' ')\n"
        "          WHERE toLower(g_any.organism_name) CONTAINS word)\n"
        "WITH org_input, count(g_any) AS kg_count\n"
        "OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        "WHERE org_input IS NOT NULL AND kg_count > 0\n"
        "  AND og.id IN $group_ids\n"
        "  AND ALL(word IN split(toLower(org_input), ' ')\n"
        "          WHERE toLower(g.organism_name) CONTAINS word)\n"
        "OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g)"
        f"{expression_where}\n"
        "WITH org_input, kg_count, count(r) AS matched_count\n"
        "WITH collect(CASE WHEN org_input IS NOT NULL AND kg_count = 0\n"
        "             THEN org_input END) AS nf_raw,\n"
        "     collect(CASE WHEN org_input IS NOT NULL AND kg_count > 0\n"
        "                   AND matched_count = 0 THEN org_input END) AS nm_raw\n"
        "RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found_organisms,\n"
        "       [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_organisms"
    )
    return cypher, params


def _build_de_by_ortholog_experiment_diagnostics(
    *,
    group_ids: list[str],
    experiment_ids: list[str],
    organisms: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Validate experiment IDs against KG + expression in ortholog groups.

    RETURN keys: not_found_experiments, not_matched_experiments.
    """
    # Build WHERE conditions WITHOUT experiment_ids filter (already via UNWIND)
    conditions_no_eid, params = _differential_expression_by_ortholog_where(
        organisms=organisms, experiment_ids=None,
        direction=direction, significant_only=significant_only,
        growth_phases=growth_phases,
    )
    params["group_ids"] = group_ids
    params["experiment_ids"] = experiment_ids

    # Additional AND conditions for organism + expression filters
    extra_and = (
        " AND " + " AND ".join(conditions_no_eid)
        if conditions_no_eid else ""
    )

    cypher = (
        "WITH $experiment_ids AS eid_inputs\n"
        "UNWIND CASE WHEN eid_inputs IS NULL THEN [null]\n"
        "       ELSE eid_inputs END AS eid\n"
        "OPTIONAL MATCH (e:Experiment {id: eid})\n"
        "WITH eid, e, CASE WHEN e IS NULL THEN true ELSE false END AS missing\n"
        "OPTIONAL MATCH (e)-[r:Changes_expression_of]->(g:Gene)"
        "-[:Gene_in_ortholog_group]->(og:OrthologGroup)\n"
        "WHERE NOT missing AND og.id IN $group_ids"
        f"{extra_and}\n"
        "WITH eid, missing, count(r) AS matched_count\n"
        "WITH collect(CASE WHEN missing THEN eid END) AS nf_raw,\n"
        "     collect(CASE WHEN NOT missing AND matched_count = 0\n"
        "             THEN eid END) AS nm_raw\n"
        "RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found_experiments,\n"
        "       [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_experiments"
    )
    return cypher, params


def build_differential_expression_by_ortholog_diagnostics(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    growth_phases: list[str] | None = None,
) -> list[tuple[str, dict]] | None:
    """Build diagnostic queries for differential_expression_by_ortholog.

    Returns None when both organisms and experiment_ids are None.
    Otherwise returns a list of (cypher, params) tuples — one per
    diagnostic sub-query that needs to run.
    """
    if organisms is None and experiment_ids is None:
        return None

    queries: list[tuple[str, dict]] = []
    if organisms is not None:
        queries.append(_build_de_by_ortholog_organism_diagnostics(
            group_ids=group_ids, organisms=organisms,
            experiment_ids=experiment_ids, direction=direction,
            significant_only=significant_only, growth_phases=growth_phases,
        ))
    if experiment_ids is not None:
        queries.append(_build_de_by_ortholog_experiment_diagnostics(
            group_ids=group_ids, experiment_ids=experiment_ids,
            organisms=organisms, direction=direction,
            significant_only=significant_only, growth_phases=growth_phases,
        ))
    return queries


# ---------------------------------------------------------------------------
# gene_response_profile helpers
# ---------------------------------------------------------------------------

def _gene_response_profile_where(
    *,
    organism_name: str | None = None,
    treatment_types: list[str] | None = None,
    background_factors: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    experiment_alias: str = "e",
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params shared by gene_response_profile builders."""
    conditions: list[str] = []
    params: dict = {}
    if organism_name:
        conditions.append(f"{experiment_alias}.organism_name = $organism_name")
        params["organism_name"] = organism_name
    if treatment_types:
        conditions.append(
            f"ANY(t IN {experiment_alias}.treatment_type"
            f" WHERE toLower(t) IN $treatment_types)"
        )
        params["treatment_types"] = [t.lower() for t in treatment_types]
    if background_factors:
        conditions.append(
            f"ANY(bf IN coalesce({experiment_alias}.background_factors, [])"
            f" WHERE toLower(bf) IN $background_factors)"
        )
        params["background_factors"] = [bf.lower() for bf in background_factors]
    if experiment_ids:
        conditions.append(f"{experiment_alias}.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    return conditions, params


def _group_key_expr(group_by: str, alias: str = "e") -> tuple[str, str]:
    """Return (unwind_clause, group_key_expr) for the group key.

    When group_by='treatment_type', returns an UNWIND clause because
    treatment_type is an array property. The UNWIND must be inserted
    after the MATCH that introduces the experiment alias.
    """
    if group_by == "treatment_type":
        return (
            f"UNWIND coalesce({alias}.treatment_type, ['unknown']) AS _tt\n",
            "_tt",
        )
    elif group_by == "experiment":
        return ("", f"{alias}.id")
    else:
        raise ValueError(
            f"group_by must be 'treatment_type' or 'experiment', got '{group_by}'"
        )


def build_gene_response_profile_envelope(
    *,
    locus_tags: list[str],
    organism_name: str,
    treatment_types: list[str] | None = None,
    background_factors: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    group_by: str = "treatment_type",
) -> tuple[str, dict]:
    """Build envelope query for gene_response_profile.

    organism_name is required (resolved by API before calling).

    RETURN keys: found_genes (list), has_expression (list), has_significant (list),
    group_totals (list of {group_key, experiments, timepoints, table_scopes}).
    """
    _, gk = _group_key_expr(group_by)
    unwind2, gk2 = _group_key_expr(group_by, alias="e2")

    conditions_e, params = _gene_response_profile_where(
        organism_name=organism_name, treatment_types=treatment_types,
        background_factors=background_factors,
        experiment_ids=experiment_ids, experiment_alias="e",
    )
    params["locus_tags"] = locus_tags
    where_e = " AND " + " AND ".join(conditions_e) if conditions_e else ""

    conditions_e2, _ = _gene_response_profile_where(
        organism_name=organism_name, treatment_types=treatment_types,
        background_factors=background_factors,
        experiment_ids=experiment_ids, experiment_alias="e2",
    )
    where_e2 = "WHERE " + " AND ".join(conditions_e2)

    cypher = (
        "MATCH (g:Gene)\n"
        "WHERE g.locus_tag IN $locus_tags\n"
        "WITH collect(g.locus_tag) AS found_genes\n"
        "\n"
        "OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g2:Gene)\n"
        f"WHERE g2.locus_tag IN found_genes{where_e}\n"
        "WITH found_genes,\n"
        "     collect(DISTINCT g2.locus_tag) AS has_expression,\n"
        "     collect(DISTINCT CASE WHEN r.expression_status IN"
        " ['significant_up', 'significant_down']"
        " THEN g2.locus_tag END) AS has_significant\n"
        "\n"
        "OPTIONAL MATCH (e2:Experiment)-[:Changes_expression_of]->(:Gene)\n"
        f"{where_e2}\n"
        f"{unwind2}"
        f"WITH found_genes, has_expression, has_significant,\n"
        f"     {gk2} AS group_key,\n"
        "     collect(DISTINCT e2) AS group_experiments\n"
        "WITH found_genes, has_expression, has_significant,\n"
        "     collect({group_key: group_key,"
        " experiments: size(group_experiments),"
        " timepoints: reduce(s = 0, exp IN group_experiments |"
        " s + COALESCE(exp.time_point_count, 1)),"
        " table_scopes: apoc.coll.toSet([exp IN group_experiments |"
        " exp.table_scope])}) AS group_totals\n"
        "RETURN found_genes,"
        " has_expression, has_significant, group_totals"
    )
    return cypher, params


def build_gene_response_profile(
    *,
    locus_tags: list[str],
    organism_name: str,
    treatment_types: list[str] | None = None,
    background_factors: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    group_by: str = "treatment_type",
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build two-pass aggregation query for gene_response_profile.

    Pass 1: compute per-gene sort keys (breadth/depth/timepoints), sort and paginate.
    Pass 2: group by experiment first (experiments_up/down), then flatten for rank/log2fc.

    RETURN keys: locus_tag, gene_name, product, gene_category, group_key,
    experiments_tested, experiments_up, experiments_down, timepoints_tested,
    timepoints_up, timepoints_down, rank_ups (list), rank_downs (list),
    log2fcs_up (list), log2fcs_down (list).
    """
    unwind, gk = _group_key_expr(group_by)

    conditions, params = _gene_response_profile_where(
        organism_name=organism_name, treatment_types=treatment_types,
        background_factors=background_factors,
        experiment_ids=experiment_ids,
    )
    params["locus_tags"] = locus_tags
    conditions.append("g.locus_tag IN $locus_tags")
    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    pass2_conditions, _ = _gene_response_profile_where(
        organism_name=organism_name, treatment_types=treatment_types,
        background_factors=background_factors,
        experiment_ids=experiment_ids,
    )
    pass2_where = (
        "WHERE " + " AND ".join(pass2_conditions) + "\n"
        if pass2_conditions else ""
    )

    pagination = ""
    if offset:
        pagination += "\nSKIP $offset"
        params["offset"] = offset
    if limit is not None:
        pagination += "\nLIMIT $limit"
        params["limit"] = limit

    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
        f"{where_block}"
        f"{unwind}"
        "WITH g,\n"
        "     count(DISTINCT CASE"
        " WHEN r.expression_status IN ['significant_up', 'significant_down']"
        f" THEN {gk} END) AS groups_responded,\n"
        "     count(DISTINCT CASE"
        " WHEN r.expression_status IN ['significant_up', 'significant_down']"
        " THEN e.id END) AS experiments_responded,\n"
        "     sum(CASE"
        " WHEN r.expression_status IN ['significant_up', 'significant_down']"
        " THEN 1 ELSE 0 END) AS timepoints_responded\n"
        "ORDER BY groups_responded DESC,"
        " experiments_responded DESC,"
        " timepoints_responded DESC,"
        " g.locus_tag ASC"
        f"{pagination}\n"
        "\n"
        "WITH g\n"
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n"
        f"{pass2_where}"
        f"{unwind}"
        f"WITH g, {gk} AS group_key, e.id AS eid,"
        " collect(r) AS exp_edges\n"
        "WITH g, group_key,\n"
        "     count(eid) AS experiments_tested,\n"
        "     count(CASE WHEN ANY(x IN exp_edges"
        " WHERE x.expression_status = 'significant_up')"
        " THEN 1 END) AS experiments_up,\n"
        "     count(CASE WHEN ANY(x IN exp_edges"
        " WHERE x.expression_status = 'significant_down')"
        " THEN 1 END) AS experiments_down,\n"
        "     reduce(acc = [], edges IN collect(exp_edges)"
        " | acc + edges) AS all_edges\n"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       g.gene_category AS gene_category,\n"
        "       group_key,\n"
        "       experiments_tested,\n"
        "       experiments_up,\n"
        "       experiments_down,\n"
        "       size(all_edges) AS timepoints_tested,\n"
        "       size([x IN all_edges"
        " WHERE x.expression_status = 'significant_up'])"
        " AS timepoints_up,\n"
        "       size([x IN all_edges"
        " WHERE x.expression_status = 'significant_down'])"
        " AS timepoints_down,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_up'"
        " | x.rank_up] AS rank_ups,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_down'"
        " | x.rank_down] AS rank_downs,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_up'"
        " | x.log2_fold_change] AS log2fcs_up,\n"
        "       [x IN all_edges"
        " WHERE x.expression_status = 'significant_down'"
        " | x.log2_fold_change] AS log2fcs_down\n"
        "ORDER BY locus_tag ASC, group_key ASC"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Gene cluster builders
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# ClusteringAnalysis builders
# ---------------------------------------------------------------------------


def _clustering_analysis_where(
    *,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build ClusteringAnalysis filter conditions + params."""
    conditions: list[str] = []
    params: dict = {}
    if organism is not None:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(ca.organism_name) CONTAINS word)"
        )
        params["organism"] = organism
    if cluster_type is not None:
        conditions.append("ca.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        conditions.append(
            "ANY(tt IN ca.treatment_type WHERE tt IN $treatment_type)"
        )
        params["treatment_type"] = treatment_type
    if omics_type is not None:
        conditions.append("ca.omics_type = $omics_type")
        params["omics_type"] = omics_type
    if background_factors is not None:
        conditions.append(
            "ANY(bf IN coalesce(ca.background_factors, [])"
            " WHERE bf IN $background_factors)"
        )
        params["background_factors"] = background_factors
    if growth_phases is not None:
        conditions.append(
            "ANY(gp IN coalesce(ca.growth_phases, [])"
            " WHERE toLower(gp) IN $growth_phases)"
        )
        params["growth_phases"] = [gp.lower() for gp in growth_phases]
    return conditions, params


def build_list_clustering_analyses_summary(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    analysis_ids: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for list_clustering_analyses.

    RETURN keys: total_entries, total_matching, by_organism,
    by_cluster_type, by_treatment_type, by_background_factors,
    by_omics_type, by_growth_phase.
    When search_text: adds score_max, score_median.
    """
    conditions, params = _clustering_analysis_where(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, omics_type=omics_type,
        background_factors=background_factors, growth_phases=growth_phases,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('clusteringAnalysisFullText', $search_text)\n"
            "YIELD node AS ca, score\n"
        )
        score_cols = (
            ",\n     max(score) AS score_max"
            ",\n     percentileDisc(score, 0.5) AS score_median"
        )
        score_return = ", score_max, score_median"
    else:
        match_block = "MATCH (ca:ClusteringAnalysis)\n"
        score_cols = ""
        score_return = ""

    if publication_doi is not None:
        match_block += "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    if experiment_ids is not None:
        match_block += "MATCH (exp:Experiment)-[:ExperimentHasClusteringAnalysis]->(ca)\n"
        conditions.append("exp.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids

    if analysis_ids is not None:
        conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "WITH collect(ca.organism_name) AS organisms,\n"
        "     collect(ca.cluster_type) AS cluster_types,\n"
        "     apoc.coll.flatten(collect(coalesce(ca.treatment_type, []))) AS treatment_types,\n"
        "     apoc.coll.flatten(collect(coalesce(ca.background_factors, []))) AS background_factors_flat,\n"
        "     collect(ca.omics_type) AS omics_types,\n"
        "     apoc.coll.flatten(collect(coalesce(ca.growth_phases, []))) AS growth_phases_flat,\n"
        f"     count(ca) AS total_matching{score_cols}\n"
        "CALL { MATCH (all_ca:ClusteringAnalysis) RETURN count(all_ca) AS total_entries }\n"
        "RETURN total_entries, total_matching,\n"
        "       apoc.coll.frequencies(organisms) AS by_organism,\n"
        "       apoc.coll.frequencies(cluster_types) AS by_cluster_type,\n"
        "       apoc.coll.frequencies(treatment_types) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(background_factors_flat) AS by_background_factors,\n"
        "       apoc.coll.frequencies(omics_types) AS by_omics_type,\n"
        f"       apoc.coll.frequencies(growth_phases_flat) AS by_growth_phase{score_return}"
    )
    return cypher, params


def build_list_clustering_analyses(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    analysis_ids: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for list_clustering_analyses.

    RETURN keys (compact): analysis_id, name, organism_name, cluster_method,
    cluster_type, cluster_count, total_gene_count, treatment_type,
    background_factors, growth_phases, omics_type, experiment_ids, clusters.
    When search_text: adds score.
    RETURN keys (verbose): adds treatment, light_condition, experimental_context.
    Inline clusters (compact): cluster_id, name, member_count.
    Inline clusters (verbose): adds functional_description, expression_dynamics,
    temporal_pattern.
    """
    conditions, params = _clustering_analysis_where(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, omics_type=omics_type,
        background_factors=background_factors, growth_phases=growth_phases,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('clusteringAnalysisFullText', $search_text)\n"
            "YIELD node AS ca, score\n"
        )
        score_col = ",\n       score"
        order_prefix = "score DESC, "
    else:
        match_block = "MATCH (ca:ClusteringAnalysis)\n"
        score_col = ""
        order_prefix = ""

    if publication_doi is not None:
        match_block += "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    if experiment_ids is not None:
        match_block += "MATCH (exp:Experiment)-[:ExperimentHasClusteringAnalysis]->(ca)\n"
        conditions.append("exp.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids

    if analysis_ids is not None:
        conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       ca.treatment AS treatment"
            ",\n       ca.light_condition AS light_condition"
            ",\n       ca.experimental_context AS experimental_context"
        )

    # Inline cluster subquery — compact or verbose
    if verbose:
        cluster_collect = (
            "collect({cluster_id: gc.id, name: gc.name,"
            " member_count: gc.member_count,"
            " functional_description: gc.functional_description,"
            " expression_dynamics: gc.expression_dynamics,"
            " temporal_pattern: gc.temporal_pattern}) AS clusters"
        )
    else:
        cluster_collect = (
            "collect({cluster_id: gc.id, name: gc.name,"
            " member_count: gc.member_count}) AS clusters"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    score_with = ", score" if search_text is not None else ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        # Collect experiment IDs (OPTIONAL — edge may not exist)
        "OPTIONAL MATCH (exp_link:Experiment)-[:ExperimentHasClusteringAnalysis]->(ca)\n"
        f"WITH ca{score_with},\n"
        "     collect(DISTINCT exp_link.id) AS experiment_ids\n"
        # Collect inline clusters
        "OPTIONAL MATCH (ca)-[:ClusteringAnalysisHasGeneCluster]->(gc:GeneCluster)\n"
        f"WITH ca{score_with}, experiment_ids,\n"
        f"     {cluster_collect}\n"
        "RETURN ca.id AS analysis_id, ca.name AS name,\n"
        "       ca.organism_name AS organism_name,\n"
        "       ca.cluster_method AS cluster_method,\n"
        "       ca.cluster_type AS cluster_type,\n"
        "       ca.cluster_count AS cluster_count,\n"
        "       ca.total_gene_count AS total_gene_count,\n"
        "       ca.treatment_type AS treatment_type,\n"
        "       coalesce(ca.background_factors, []) AS background_factors,\n"
        "       coalesce(ca.growth_phases, []) AS growth_phases,\n"
        "       ca.omics_type AS omics_type,\n"
        f"       experiment_ids, clusters{score_col}{verbose_cols}\n"
        f"ORDER BY {order_prefix}ca.organism_name, ca.name{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_gene_clusters_by_gene_summary(
    *,
    locus_tags: list[str],
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    analysis_ids: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for gene_clusters_by_gene.

    Joins through ClusteringAnalysis for analysis fields and filters.

    RETURN keys: total_matching, total_clusters,
    genes_with_clusters, genes_without_clusters,
    not_found, not_matched,
    by_cluster_type, by_treatment_type, by_background_factors,
    by_analysis.
    """
    params: dict = {"locus_tags": locus_tags}

    ca_conditions: list[str] = []
    if cluster_type is not None:
        ca_conditions.append("ca.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        ca_conditions.append(
            "ANY(tt IN ca.treatment_type WHERE tt IN $treatment_type)")
        params["treatment_type"] = treatment_type
    if background_factors is not None:
        ca_conditions.append(
            "ANY(bf IN coalesce(ca.background_factors, [])"
            " WHERE bf IN $background_factors)")
        params["background_factors"] = background_factors
    if analysis_ids is not None:
        ca_conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    pub_match = ""
    if publication_doi is not None:
        pub_match = "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        ca_conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    ca_where = "WHERE " + " AND ".join(ca_conditions) + "\n" if ca_conditions else ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "OPTIONAL MATCH (ca:ClusteringAnalysis)-[:ClusteringAnalysisHasGeneCluster]->"
        "(gc:GeneCluster)-[:Gene_in_gene_cluster]->(g)\n"
        f"{pub_match}"
        f"{ca_where}"
        "WITH lt, g, gc, ca\n"
        "WITH collect(DISTINCT CASE WHEN g IS NULL THEN lt END) AS nf_raw,\n"
        "     collect(DISTINCT CASE WHEN g IS NOT NULL AND gc IS NULL\n"
        "             THEN lt END) AS nm_raw,\n"
        "     collect(CASE WHEN gc IS NOT NULL THEN\n"
        "       {lt: lt, cid: gc.id, ct: ca.cluster_type,\n"
        "        tt: ca.treatment_type, bfs: ca.background_factors,\n"
        "        aid: ca.id, aname: ca.name} END) AS rows\n"
        "WITH [x IN nf_raw WHERE x IS NOT NULL] AS not_found,\n"
        "     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched,\n"
        "     rows\n"
        "WITH not_found, not_matched,\n"
        "     size(rows) AS total_matching,\n"
        "     size(apoc.coll.toSet([r IN rows | r.cid])) AS total_clusters,\n"
        "     size(apoc.coll.toSet([r IN rows | r.lt])) AS genes_with_clusters,\n"
        "     size($locus_tags) - size(apoc.coll.toSet([r IN rows | r.lt]))\n"
        "       - size([x IN not_found WHERE x IS NOT NULL]) AS genes_without_clusters,\n"
        "     apoc.coll.frequencies([r IN rows | r.ct]) AS by_cluster_type,\n"
        "     apoc.coll.frequencies(\n"
        "       apoc.coll.flatten([r IN rows | coalesce(r.tt, [])])) AS by_treatment_type,\n"
        "     apoc.coll.frequencies(\n"
        "       apoc.coll.flatten([r IN rows | coalesce(r.bfs, [])])) AS by_background_factors,\n"
        "     apoc.coll.frequencies([r IN rows | r.aid]) AS by_analysis\n"
        "RETURN total_matching, total_clusters,\n"
        "       genes_with_clusters, genes_without_clusters,\n"
        "       not_found, not_matched,\n"
        "       by_cluster_type, by_treatment_type, by_background_factors,\n"
        "       by_analysis"
    )
    return cypher, params


def build_gene_clusters_by_gene(
    *,
    locus_tags: list[str],
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    analysis_ids: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_clusters_by_gene.

    Joins through ClusteringAnalysis for analysis fields and filters.

    RETURN keys (compact): locus_tag, gene_name, cluster_id, cluster_name,
    cluster_type, membership_score, analysis_id, analysis_name,
    treatment_type, background_factors.
    RETURN keys (verbose): adds cluster_method, member_count,
    cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern, treatment, light_condition,
    experimental_context, p_value.
    """
    params: dict = {"locus_tags": locus_tags}

    ca_conditions: list[str] = []
    if cluster_type is not None:
        ca_conditions.append("ca.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        ca_conditions.append(
            "ANY(tt IN ca.treatment_type WHERE tt IN $treatment_type)")
        params["treatment_type"] = treatment_type
    if background_factors is not None:
        ca_conditions.append(
            "ANY(bf IN coalesce(ca.background_factors, [])"
            " WHERE bf IN $background_factors)")
        params["background_factors"] = background_factors
    if analysis_ids is not None:
        ca_conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    pub_match = ""
    if publication_doi is not None:
        pub_match = "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        ca_conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    ca_where = ""
    if ca_conditions:
        ca_where = "WHERE " + " AND ".join(ca_conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       ca.cluster_method AS cluster_method"
            ",\n       gc.member_count AS member_count"
            ",\n       gc.functional_description AS cluster_functional_description"
            ",\n       gc.expression_dynamics AS cluster_expression_dynamics"
            ",\n       gc.temporal_pattern AS cluster_temporal_pattern"
            ",\n       ca.treatment AS treatment"
            ",\n       ca.light_condition AS light_condition"
            ",\n       ca.experimental_context AS experimental_context"
            ",\n       r.p_value AS p_value"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (ca:ClusteringAnalysis)-[:ClusteringAnalysisHasGeneCluster]->"
        "(gc:GeneCluster)-[r:Gene_in_gene_cluster]->(g:Gene {locus_tag: lt})\n"
        f"{pub_match}"
        f"{ca_where}"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       gc.id AS cluster_id, gc.name AS cluster_name,\n"
        "       ca.cluster_type AS cluster_type,\n"
        "       r.membership_score AS membership_score,\n"
        "       ca.id AS analysis_id, ca.name AS analysis_name,\n"
        "       ca.treatment_type AS treatment_type,\n"
        f"       coalesce(ca.background_factors, []) AS background_factors{verbose_cols}\n"
        f"ORDER BY g.locus_tag, gc.id{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_genes_in_cluster_summary(
    *,
    cluster_ids: list[str] | None = None,
    analysis_id: str | None = None,
    organism: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_in_cluster.

    Two entry modes:
    - cluster_ids: UNWIND specific cluster IDs (original mode)
    - analysis_id: match all clusters belonging to a ClusteringAnalysis

    RETURN keys: total_matching, by_organism, by_cluster,
    by_category_raw, not_found_clusters, not_matched_clusters.
    When analysis_id: also returns analysis_name.
    """
    params: dict = {"organism": organism}

    organism_filter = (
        "AND ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_name) CONTAINS word)\n"
        if organism is not None else ""
    )

    if analysis_id is not None:
        params["analysis_id"] = analysis_id
        match_block = (
            "MATCH (ca:ClusteringAnalysis {id: $analysis_id})"
            "-[:ClusteringAnalysisHasGeneCluster]->(gc:GeneCluster)\n"
            "WITH gc, gc.id AS cid, ca.name AS analysis_name\n"
            "OPTIONAL MATCH (gc)-[r:Gene_in_gene_cluster]->(g:Gene)\n"
            f"WHERE g IS NOT NULL {organism_filter}"
            "WITH cid, gc, g, analysis_name\n"
        )
        nf_nm_block = (
            "WITH collect(CASE WHEN g IS NOT NULL THEN\n"
            "       {lt: g.locus_tag, org: g.organism_name,\n"
            "        cat: coalesce(g.gene_category, 'Unknown'),\n"
            "        cid: cid, cname: gc.name} END) AS rows,\n"
            "     head(collect(DISTINCT analysis_name)) AS analysis_name\n"
        )
        return_suffix = ",\n       analysis_name"
        not_found_block = (
            "WITH rows, analysis_name,\n"
            "     [] AS not_found_clusters, [] AS not_matched_clusters\n"
        )
    else:
        params["cluster_ids"] = cluster_ids
        match_block = (
            "UNWIND $cluster_ids AS cid\n"
            "OPTIONAL MATCH (gc:GeneCluster {id: cid})\n"
            "OPTIONAL MATCH (gc)-[r:Gene_in_gene_cluster]->(g:Gene)\n"
            f"WHERE g IS NOT NULL {organism_filter}"
            "WITH cid, gc, g\n"
        )
        nf_nm_block = (
            "WITH collect(DISTINCT CASE WHEN gc IS NULL THEN cid END) AS nf_raw,\n"
            "     collect(DISTINCT CASE WHEN gc IS NOT NULL AND g IS NULL\n"
            "             THEN cid END) AS nm_raw,\n"
            "     collect(CASE WHEN g IS NOT NULL THEN\n"
            "       {lt: g.locus_tag, org: g.organism_name,\n"
            "        cat: coalesce(g.gene_category, 'Unknown'),\n"
            "        cid: cid, cname: gc.name} END) AS rows\n"
        )
        return_suffix = ""
        not_found_block = (
            "WITH [x IN nf_raw WHERE x IS NOT NULL] AS not_found_clusters,\n"
            "     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_clusters,\n"
            "     rows\n"
        )

    cypher = (
        f"{match_block}"
        f"{nf_nm_block}"
        f"{not_found_block}"
        "WITH not_found_clusters, not_matched_clusters,\n"
        "     size(rows) AS total_matching,\n"
        "     apoc.coll.frequencies([r IN rows | r.org]) AS by_organism,\n"
        "     apoc.coll.frequencies([r IN rows | r.cat]) AS by_category_raw,\n"
        "     [cid IN apoc.coll.toSet([r IN rows | r.cid]) |\n"
        "       {cluster_id: cid,\n"
        "        cluster_name: head([r IN rows WHERE r.cid = cid | r.cname]),\n"
        "        count: size([r IN rows WHERE r.cid = cid])}] AS by_cluster"
        + (f",\n     analysis_name\n" if analysis_id is not None else "\n")
        + "RETURN total_matching, by_organism, by_cluster, by_category_raw,\n"
        f"       not_found_clusters, not_matched_clusters{return_suffix}"
    )
    return cypher, params


def build_genes_in_cluster(
    *,
    cluster_ids: list[str] | None = None,
    analysis_id: str | None = None,
    organism: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_in_cluster.

    Two entry modes:
    - cluster_ids: UNWIND specific cluster IDs (original mode)
    - analysis_id: match through CA → GC → Gene

    RETURN keys (compact): locus_tag, gene_name, product, gene_category,
    organism_name, cluster_id, cluster_name, membership_score.
    RETURN keys (verbose): adds gene_function_description, gene_summary,
    p_value, cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern.
    """
    params: dict = {}

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       g.function_description AS gene_function_description"
            ",\n       g.gene_summary AS gene_summary"
            ",\n       r.p_value AS p_value"
            ",\n       gc.functional_description AS cluster_functional_description"
            ",\n       gc.expression_dynamics AS cluster_expression_dynamics"
            ",\n       gc.temporal_pattern AS cluster_temporal_pattern"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    # Build match block based on entry mode
    if analysis_id is not None:
        params["analysis_id"] = analysis_id
        match_base = (
            "MATCH (ca:ClusteringAnalysis {id: $analysis_id})"
            "-[:ClusteringAnalysisHasGeneCluster]->"
            "(gc:GeneCluster)-[r:Gene_in_gene_cluster]->(g:Gene)\n"
        )
    else:
        params["cluster_ids"] = cluster_ids
        match_base = (
            "UNWIND $cluster_ids AS cid\n"
            "MATCH (gc:GeneCluster {id: cid})-[r:Gene_in_gene_cluster]->(g:Gene)\n"
        )

    # Conditional WHERE for organism filter
    if organism is not None:
        params["organism"] = organism
        cypher = (
            f"{match_base}"
            "WHERE ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(g.organism_name) CONTAINS word)\n"
        )
    else:
        cypher = match_base

    cypher += (
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.gene_category AS gene_category,\n"
        "       g.organism_name AS organism_name,\n"
        "       gc.id AS cluster_id, gc.name AS cluster_name,\n"
        f"       r.membership_score AS membership_score{verbose_cols}\n"
        f"ORDER BY gc.id, g.organism_name, g.locus_tag{skip_clause}{limit_clause}"
    )
    return cypher, params


# ---------------------------------------------------------------------------
# Ontology landscape builders (Child 1 of KG enrichment surface)
# ---------------------------------------------------------------------------


def build_ontology_landscape(
    *,
    ontology: str,
    organism_name: str,
    verbose: bool = False,
    min_gene_set_size: int = 5,
    max_gene_set_size: int = 500,
    tree: str | None = None,
) -> tuple[str, dict]:
    """Per-(ontology, level) aggregated landscape stats for one ontology.

    Returns one row per level reached by the organism's genes. Aggregates
    happen server-side — percentiles via percentileCont, distinct-gene
    coverage via apoc.coll.toSet(apoc.coll.flatten(...)), best_effort
    counts via CASE-sum. The min_gene_set_size/max_gene_set_size filter is
    applied after per-term aggregation so the per-level stats describe only
    terms that would be valid for pathway enrichment. Verbose adds top-3
    example terms in the same scan via pre-aggregation ORDER BY + collect[0..3].

    RETURN keys: level, n_terms_with_genes, n_genes_at_level,
    min_genes_per_term, q1_genes_per_term, median_genes_per_term,
    q3_genes_per_term, max_genes_per_term, n_best_effort.
    Verbose adds: example_terms (list of {term_id, name, n_genes}).
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(
            f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}"
        )
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")

    # Unified hierarchy walk via _hierarchy_walk helper.
    # This corrects the previous flat-Pfam treatment: Pfam is actually 2-level
    # (Pfam leaf + PfamClan parent), and the helper walks Pfam_in_pfam_clan.
    frag = _hierarchy_walk(ontology, direction="up")
    walk = frag["walk_up"] + "\n" if frag["walk_up"] else ""

    # Tree filter (BRITE only): applied after the hierarchy walk, before
    # per-term aggregation.
    tree_filter = ""
    if tree is not None:
        tree_filter = "WHERE t.tree = $tree\n"

    # Verbose clauses — Python string composition so compute is
    # short-circuited when verbose=False (see scoping D4).
    # pre_sort is an intermediate WITH..ORDER BY to pre-sort rows by gene count
    # before the final aggregation; collect()[0..3] then captures top-3.
    pre_sort = (
        "WITH t, n_g_per_term, term_genes ORDER BY n_g_per_term DESC\n"
        if verbose else ""
    )
    verbose_agg = (
        ",\n"
        "     collect({term_id:t.id, name:t.name, "
        "n_genes:n_g_per_term})[0..3] AS example_terms"
        if verbose else ""
    )
    verbose_ret = ",\n       example_terms" if verbose else ""

    cypher = (
        f"{frag['bind_up']}\n"
        f"{walk}"
        f"{tree_filter}"
        "WITH t, count(DISTINCT g) AS n_g_per_term, "
        "collect(DISTINCT g) AS term_genes\n"
        "WHERE n_g_per_term >= $min_gene_set_size "
        "AND n_g_per_term <= $max_gene_set_size\n"
        f"{pre_sort}"
        "WITH t.level AS level, t.tree AS tree, t.tree_code AS tree_code,\n"
        "     count(t) AS n_terms_with_genes,\n"
        "     min(n_g_per_term) AS min_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.25) AS q1_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.5)  AS median_genes_per_term,\n"
        "     percentileCont(toFloat(n_g_per_term), 0.75) AS q3_genes_per_term,\n"
        "     max(n_g_per_term) AS max_genes_per_term,\n"
        "     apoc.coll.toSet(apoc.coll.flatten(collect(term_genes))) AS all_genes,\n"
        "     sum(CASE WHEN t.level_is_best_effort IS NOT NULL "
        "THEN 1 ELSE 0 END) AS n_best_effort"
        f"{verbose_agg}\n"
        "RETURN level, tree, tree_code, n_terms_with_genes,\n"
        "       size(all_genes) AS n_genes_at_level,\n"
        "       min_genes_per_term, q1_genes_per_term, median_genes_per_term,\n"
        "       q3_genes_per_term, max_genes_per_term,\n"
        f"       n_best_effort{verbose_ret}\n"
        "ORDER BY level"
    )
    params = {
        "org": organism_name,
        "min_gene_set_size": min_gene_set_size,
        "max_gene_set_size": max_gene_set_size,
    }
    if tree is not None:
        params["tree"] = tree
    return cypher, params


def build_ontology_expcov(
    *,
    ontology: str,
    organism_name: str,
    experiment_ids: list[str],
    min_gene_set_size: int = 5,
    max_gene_set_size: int = 500,
) -> tuple[str, dict]:
    """Per-(experiment, level) coverage rows for ontology_landscape.

    For each experiment, count distinct genes that (a) are quantified
    in that experiment AND (b) reach any term at each level. The same
    min_gene_set_size/max_gene_set_size filter as Q_landscape is applied
    so coverage is computed over the same term population. Returns one row
    per (eid, level). L2 applies zero-fill + min/median/max aggregation.

    RETURN keys: eid, n_total, level, n_at_level.
    """
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(
            f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}"
        )

    # Unified hierarchy walk via _hierarchy_walk helper (shared with
    # build_ontology_landscape). For expcov we strip the Gene-Match prefix
    # from bind_up because `g` is already bound by the outer Experiment match.
    frag = _hierarchy_walk(ontology, direction="up")
    prefix = "MATCH (g:Gene {organism_name: $org})"
    assert frag["bind_up"].startswith(prefix), (
        f"_hierarchy_walk bind_up format changed; "
        f"expcov prefix-stripping needs update. Got: {frag['bind_up']!r}"
    )
    bind_tail = frag["bind_up"][len(prefix):]
    walk = frag["walk_up"] + "\n" if frag["walk_up"] else ""

    cypher = (
        "UNWIND $experiment_ids AS eid\n"
        "MATCH (e:Experiment {id:eid})-[:Changes_expression_of]->"
        "(g:Gene {organism_name:$org})\n"
        "WITH eid, collect(DISTINCT g) AS quantified\n"
        "WITH eid, quantified, size(quantified) AS n_total\n"
        "UNWIND quantified AS g\n"
        f"MATCH (g){bind_tail}\n"
        f"{walk}"
        "WITH eid, n_total, t, count(DISTINCT g) AS n_g_per_term_exp, "
        "collect(DISTINCT g) AS term_genes_exp\n"
        "WHERE n_g_per_term_exp >= $min_gene_set_size "
        "AND n_g_per_term_exp <= $max_gene_set_size\n"
        "WITH eid, n_total, t.level AS level,\n"
        "     apoc.coll.toSet(apoc.coll.flatten("
        "collect(term_genes_exp))) AS level_genes\n"
        "RETURN eid, n_total, level, size(level_genes) AS n_at_level\n"
        "ORDER BY eid, level"
    )
    return cypher, {
        "org": organism_name,
        "experiment_ids": experiment_ids,
        "min_gene_set_size": min_gene_set_size,
        "max_gene_set_size": max_gene_set_size,
    }


def build_ontology_experiment_check(
    *,
    experiment_ids: list[str],
) -> tuple[str, dict]:
    """Classify experiment_ids — does each exist, which organism?

    Consumers (ontology_landscape) compare exp_organism to the
    canonical organism to decide found / not_found / not_matched.
    Returns one row per input eid, preserving order.

    RETURN keys: eid, exists (bool), exp_organism (str; '' if absent).
    """
    cypher = (
        "UNWIND $experiment_ids AS eid\n"
        "OPTIONAL MATCH (e:Experiment {id: eid})\n"
        "RETURN eid,\n"
        "       e IS NOT NULL AS exists,\n"
        "       coalesce(e.organism_name, '') AS exp_organism"
    )
    return cypher, {"experiment_ids": experiment_ids}


def build_ontology_organism_gene_count(
    *, organism_name: str,
) -> tuple[str, dict]:
    """Total gene count for one organism — denominator for genome_coverage.

    RETURN keys: total_genes (int).
    """
    cypher = "MATCH (g:Gene {organism_name:$org}) RETURN count(g) AS total_genes"
    return cypher, {"org": organism_name}


def _list_derived_metrics_where(
    *,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    omics_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    rankable: bool | None = None,
    has_p_value: bool | None = None,
) -> tuple[list[str], dict]:
    """Shared WHERE builder for build_list_derived_metrics{,_summary}.

    Returns (conditions, params). All filters are AND-joined at the caller.
    Organism uses space-split CONTAINS (mirrors _list_experiments_where).
    rankable / has_p_value bool params are coerced to string "true"/"false"
    for comparison against KG-stored strings.
    omics_type is scalar on DerivedMetric (unlike list-valued on Experiment);
    filter is exact-match after toUpper normalization.
    treatment_type / background_factors / growth_phases are wrapped in
    coalesce(..., []) defensively — the KG convention guarantees non-null
    lists, but the coalesce keeps the ANY() filter null-safe against
    schema drift.
    """
    conditions: list[str] = []
    params: dict = {}

    if organism:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(dm.organism_name) CONTAINS word)"
        )
        params["organism"] = organism

    if metric_types:
        conditions.append("dm.metric_type IN $metric_types")
        params["metric_types"] = metric_types

    if value_kind:
        conditions.append("dm.value_kind = $value_kind")
        params["value_kind"] = value_kind

    if compartment:
        conditions.append("dm.compartment = $compartment")
        params["compartment"] = compartment

    if omics_type:
        conditions.append("toUpper(dm.omics_type) = $omics_type_upper")
        params["omics_type_upper"] = omics_type.upper()

    if treatment_type:
        conditions.append(
            "ANY(t IN coalesce(dm.treatment_type, [])"
            " WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]

    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(dm.background_factors, [])"
            " WHERE toLower(bf) IN $background_factors_lower)"
        )
        params["background_factors_lower"] = [bf.lower() for bf in background_factors]

    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(dm.growth_phases, [])"
            " WHERE toLower(gp) IN $growth_phases_lower)"
        )
        params["growth_phases_lower"] = [gp.lower() for gp in growth_phases]

    if publication_doi:
        conditions.append("dm.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    if experiment_ids:
        conditions.append("dm.experiment_id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids

    if derived_metric_ids:
        conditions.append("dm.id IN $derived_metric_ids")
        params["derived_metric_ids"] = derived_metric_ids

    if rankable is not None:
        conditions.append("dm.rankable = $rankable_str")
        params["rankable_str"] = "true" if rankable else "false"

    if has_p_value is not None:
        conditions.append("dm.has_p_value = $has_p_value_str")
        params["has_p_value_str"] = "true" if has_p_value else "false"

    return conditions, params


def build_list_derived_metrics_summary(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    omics_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    rankable: bool | None = None,
    has_p_value: bool | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for list_derived_metrics.

    RETURN keys: total_entries, total_matching, by_organism, by_value_kind,
    by_metric_type, by_compartment, by_omics_type, by_treatment_type,
    by_background_factors, by_growth_phase.
    When search_text: adds score_max, score_median.
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, omics_type=omics_type,
        treatment_type=treatment_type, background_factors=background_factors,
        growth_phases=growth_phases, publication_doi=publication_doi,
        experiment_ids=experiment_ids, derived_metric_ids=derived_metric_ids,
        rankable=rankable, has_p_value=has_p_value,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)\n"
            "YIELD node AS dm, score\n"
        )
        score_cols = (
            ",\n     max(score) AS score_max"
            ",\n     percentileDisc(score, 0.5) AS score_median"
        )
        score_return = ", score_max, score_median"
    else:
        match_block = "MATCH (dm:DerivedMetric)\n"
        score_cols = ""
        score_return = ""

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "WITH collect(dm.organism_name) AS organisms,\n"
        "     collect(dm.value_kind) AS value_kinds,\n"
        "     collect(dm.metric_type) AS metric_types,\n"
        "     collect(dm.compartment) AS compartments,\n"
        "     collect(dm.omics_type) AS omics_types,\n"
        "     apoc.coll.flatten(collect(coalesce(dm.treatment_type, []))) AS treatment_types_flat,\n"
        "     apoc.coll.flatten(collect(coalesce(dm.background_factors, []))) AS background_factors_flat,\n"
        "     apoc.coll.flatten(collect(coalesce(dm.growth_phases, []))) AS growth_phases_flat,\n"
        f"     count(dm) AS total_matching{score_cols}\n"
        "CALL { MATCH (all_dm:DerivedMetric) RETURN count(all_dm) AS total_entries }\n"
        "RETURN total_entries, total_matching,\n"
        "       apoc.coll.frequencies(organisms) AS by_organism,\n"
        "       apoc.coll.frequencies(value_kinds) AS by_value_kind,\n"
        "       apoc.coll.frequencies(metric_types) AS by_metric_type,\n"
        "       apoc.coll.frequencies(compartments) AS by_compartment,\n"
        "       apoc.coll.frequencies(omics_types) AS by_omics_type,\n"
        "       apoc.coll.frequencies(treatment_types_flat) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(background_factors_flat) AS by_background_factors,\n"
        f"       apoc.coll.frequencies(growth_phases_flat) AS by_growth_phase{score_return}"
    )
    return cypher, params


def build_list_derived_metrics(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    omics_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    rankable: bool | None = None,
    has_p_value: bool | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for list_derived_metrics.

    RETURN keys (compact): derived_metric_id, name, metric_type, value_kind,
    rankable, has_p_value, unit, allowed_categories (CASE-gated on
    value_kind='categorical'), field_description, organism_name,
    experiment_id, publication_doi, compartment, omics_type,
    treatment_type, background_factors, total_gene_count, growth_phases.
    When search_text: adds score.
    When verbose: adds treatment, light_condition, experimental_context.

    NOTE: p_value_threshold is intentionally absent from the RETURN — the
    property does not exist on any DerivedMetric in the current KG. See
    docs/tool-specs/list_derived_metrics.md §Verbose adds for the
    reinstatement rule (CASE-gated on dm.has_p_value='true').
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, omics_type=omics_type,
        treatment_type=treatment_type, background_factors=background_factors,
        growth_phases=growth_phases, publication_doi=publication_doi,
        experiment_ids=experiment_ids, derived_metric_ids=derived_metric_ids,
        rankable=rankable, has_p_value=has_p_value,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)\n"
            "YIELD node AS dm, score\n"
        )
        score_col = ",\n       score"
        order_prefix = "score DESC, "
    else:
        match_block = "MATCH (dm:DerivedMetric)\n"
        score_col = ""
        order_prefix = ""

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "RETURN dm.id AS derived_metric_id,\n"
        "       dm.name AS name,\n"
        "       dm.metric_type AS metric_type,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.rankable = 'true' AS rankable,\n"
        "       dm.has_p_value = 'true' AS has_p_value,\n"
        "       dm.unit AS unit,\n"
        "       CASE WHEN dm.value_kind = 'categorical'\n"
        "            THEN dm.allowed_categories ELSE null END AS allowed_categories,\n"
        "       dm.field_description AS field_description,\n"
        "       dm.organism_name AS organism_name,\n"
        "       dm.experiment_id AS experiment_id,\n"
        "       dm.publication_doi AS publication_doi,\n"
        "       dm.compartment AS compartment,\n"
        "       dm.omics_type AS omics_type,\n"
        "       coalesce(dm.treatment_type, []) AS treatment_type,\n"
        "       coalesce(dm.background_factors, []) AS background_factors,\n"
        "       dm.total_gene_count AS total_gene_count,\n"
        f"       coalesce(dm.growth_phases, []) AS growth_phases{score_col}{verbose_cols}\n"
        f"ORDER BY {order_prefix}dm.organism_name ASC, dm.value_kind ASC, dm.id ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_gene_derived_metrics_summary(
    *,
    locus_tags: list[str],
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for gene_derived_metrics.

    OPTIONAL MATCH cascade tracks not_found (no Gene) / not_matched
    (Gene present but no DM rows after filters, including kind-mismatch).
    DM-level filters wrapped inside `dm IS NULL OR (...)` so the OPTIONAL
    MATCH still emits a "no edge" row for not_matched bookkeeping.

    RETURN keys: total_matching, total_derived_metrics, genes_with_metrics,
    genes_without_metrics, not_found, not_matched, by_value_kind,
    by_metric_type, by_metric, by_compartment, by_treatment_type,
    by_background_factors, by_publication.
    """
    params: dict = {"locus_tags": locus_tags}

    dm_conditions: list[str] = []
    if metric_types is not None:
        dm_conditions.append("dm.metric_type IN $metric_types")
        params["metric_types"] = metric_types
    if value_kind is not None:
        dm_conditions.append("dm.value_kind = $value_kind")
        params["value_kind"] = value_kind
    if compartment is not None:
        dm_conditions.append("dm.compartment = $compartment")
        params["compartment"] = compartment
    if treatment_type is not None:
        dm_conditions.append(
            "ANY(t IN coalesce(dm.treatment_type, [])"
            " WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]
    if background_factors is not None:
        dm_conditions.append(
            "ANY(bf IN coalesce(dm.background_factors, [])"
            " WHERE toLower(bf) IN $bfs_lower)"
        )
        params["bfs_lower"] = [bf.lower() for bf in background_factors]
    if publication_doi is not None:
        dm_conditions.append("dm.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi
    if derived_metric_ids is not None:
        dm_conditions.append("dm.id IN $derived_metric_ids")
        params["derived_metric_ids"] = derived_metric_ids

    where_block = ""
    if dm_conditions:
        where_block = (
            "WHERE dm IS NULL OR ( "
            + " AND ".join(dm_conditions)
            + " )\n"
        )

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "OPTIONAL MATCH (g)<-[r:Derived_metric_quantifies_gene\n"
        "                    |Derived_metric_flags_gene\n"
        "                    |Derived_metric_classifies_gene]-(dm:DerivedMetric)\n"
        f"{where_block}"
        "WITH lt, g, dm, $locus_tags AS input_tags\n"
        "WITH input_tags,\n"
        "     collect(DISTINCT CASE WHEN g IS NULL THEN lt END) AS nf_raw,\n"
        "     collect(DISTINCT CASE WHEN g IS NOT NULL AND dm IS NULL THEN lt END) AS nm_raw,\n"
        "     collect(CASE WHEN dm IS NOT NULL THEN\n"
        "       {lt: lt, dm_id: dm.id, name: dm.name,\n"
        "        mt: dm.metric_type, vk: dm.value_kind,\n"
        "        comp: dm.compartment, doi: dm.publication_doi,\n"
        "        tt: dm.treatment_type, bfs: dm.background_factors} END) AS rows\n"
        "WITH input_tags,\n"
        "     [x IN nf_raw WHERE x IS NOT NULL] AS not_found,\n"
        "     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched,\n"
        "     rows\n"
        "RETURN size(rows) AS total_matching,\n"
        "       size(apoc.coll.toSet([r IN rows | r.dm_id])) AS total_derived_metrics,\n"
        "       size(apoc.coll.toSet([r IN rows | r.lt])) AS genes_with_metrics,\n"
        "       size(input_tags) - size(apoc.coll.toSet([r IN rows | r.lt]))\n"
        "         - size(not_found) AS genes_without_metrics,\n"
        "       not_found, not_matched,\n"
        "       apoc.coll.frequencies([r IN rows | r.vk]) AS by_value_kind,\n"
        "       apoc.coll.frequencies([r IN rows | r.mt]) AS by_metric_type,\n"
        "       [dm_id IN apoc.coll.toSet([r IN rows | r.dm_id]) |\n"
        "         {derived_metric_id: dm_id,\n"
        "          name: head([r IN rows WHERE r.dm_id = dm_id | r.name]),\n"
        "          metric_type: head([r IN rows WHERE r.dm_id = dm_id | r.mt]),\n"
        "          value_kind: head([r IN rows WHERE r.dm_id = dm_id | r.vk]),\n"
        "          count: size([r IN rows WHERE r.dm_id = dm_id])}] AS by_metric,\n"
        "       apoc.coll.frequencies([r IN rows | r.comp]) AS by_compartment,\n"
        "       apoc.coll.frequencies(\n"
        "         apoc.coll.flatten([r IN rows | coalesce(r.tt, [])])) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(\n"
        "         apoc.coll.flatten([r IN rows | coalesce(r.bfs, [])])) AS by_background_factors,\n"
        "       apoc.coll.frequencies([r IN rows | r.doi]) AS by_publication"
    )
    return cypher, params


def build_gene_derived_metrics(
    *,
    locus_tags: list[str],
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_derived_metrics.

    One row per gene × DM. `r.value` is polymorphic across edge types
    (float / 'true'/'false' string / category string) — branch on
    value_kind in the consumer.

    RETURN keys (compact, 11 columns today): locus_tag, gene_name,
    derived_metric_id, value_kind, name, value, rankable, has_p_value,
    rank_by_metric, metric_percentile, metric_bucket.

    NOTE: adjusted_p_value, significant are declared in the Pydantic
    Result model with default=None but NOT in the current Cypher RETURN
    — no edge in today's KG carries those props (no DM has
    has_p_value='true') and including them produces CyVer schema
    warnings. Mirrors p_value_threshold deferral in
    build_list_derived_metrics. Re-add CASE-gated RETURN columns
    (`CASE WHEN dm.has_p_value = 'true' THEN r.<col> ELSE null END`)
    when a has_p_value='true' DM lands.

    RETURN keys (verbose, 11 added today): metric_type,
    field_description, unit, allowed_categories, compartment,
    treatment_type, background_factors, publication_doi, treatment,
    light_condition, experimental_context. p_value (raw, edge-side)
    is also deferred until has_p_value DM lands.
    """
    params: dict = {"locus_tags": locus_tags}

    conditions: list[str] = []
    if metric_types is not None:
        conditions.append("dm.metric_type IN $metric_types")
        params["metric_types"] = metric_types
    if value_kind is not None:
        conditions.append("dm.value_kind = $value_kind")
        params["value_kind"] = value_kind
    if compartment is not None:
        conditions.append("dm.compartment = $compartment")
        params["compartment"] = compartment
    if treatment_type is not None:
        conditions.append(
            "ANY(t IN coalesce(dm.treatment_type, [])"
            " WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]
    if background_factors is not None:
        conditions.append(
            "ANY(bf IN coalesce(dm.background_factors, [])"
            " WHERE toLower(bf) IN $bfs_lower)"
        )
        params["bfs_lower"] = [bf.lower() for bf in background_factors]
    if publication_doi is not None:
        conditions.append("dm.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi
    if derived_metric_ids is not None:
        conditions.append("dm.id IN $derived_metric_ids")
        params["derived_metric_ids"] = derived_metric_ids

    where_block = ""
    if conditions:
        where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.metric_type AS metric_type"
            ",\n       dm.field_description AS field_description"
            ",\n       dm.unit AS unit"
            ",\n       CASE WHEN dm.value_kind = 'categorical'\n"
            "            THEN dm.allowed_categories ELSE null END "
            "AS allowed_categories"
            ",\n       dm.compartment AS compartment"
            ",\n       coalesce(dm.treatment_type, []) AS treatment_type"
            ",\n       coalesce(dm.background_factors, []) AS background_factors"
            ",\n       dm.publication_doi AS publication_doi"
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})\n"
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene\n"
        "                          |Derived_metric_flags_gene\n"
        "                          |Derived_metric_classifies_gene]->(g)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       dm.id AS derived_metric_id,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.name AS name,\n"
        "       r.value AS value,\n"
        "       dm.rankable = 'true' AS rankable,\n"
        "       dm.has_p_value = 'true' AS has_p_value,\n"
        "       CASE WHEN dm.rankable = 'true' THEN r.rank_by_metric ELSE null END AS rank_by_metric,\n"
        "       CASE WHEN dm.rankable = 'true' THEN r.metric_percentile ELSE null END AS metric_percentile,\n"
        "       CASE WHEN dm.rankable = 'true' THEN r.metric_bucket ELSE null END AS metric_bucket"
        f"{verbose_cols}\n"
        "ORDER BY g.locus_tag ASC, dm.value_kind ASC, dm.id ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_genes_by_numeric_metric_diagnostics(
    *,
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Pre-flight DM selection + gate-state probe for genes_by_numeric_metric.

    api/ runs this BEFORE summary/detail so it can:
      1. Validate every selected DM has `value_kind='numeric'` (raise on
         mismatch).
      2. Compute `excluded_derived_metrics` for rankable-/p-value-gated
         filters that don't apply to some/all selected DMs.
      3. Pass the surviving DM ID list to summary/detail.

    Reuses `_list_derived_metrics_where` for DM-scoping conditions with a
    hardcoded `value_kind='numeric'` predicate (this tool only drills into
    numeric DMs; mismatches surface here as zero-row results that api/
    converts to a ValueError listing offending IDs).

    RETURN keys (one row per surviving DM, 8 columns):
      derived_metric_id, metric_type, value_kind, name,
      rankable, has_p_value, total_gene_count, organism_name.
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism,
        metric_types=metric_types,
        value_kind="numeric",
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
        publication_doi=publication_doi,
        experiment_ids=experiment_ids,
        derived_metric_ids=derived_metric_ids,
    )

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)\n"
        f"{where_block}"
        "RETURN dm.id AS derived_metric_id,\n"
        "       dm.metric_type AS metric_type,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.name AS name,\n"
        "       dm.rankable = 'true' AS rankable,\n"
        "       dm.has_p_value = 'true' AS has_p_value,\n"
        "       dm.total_gene_count AS total_gene_count,\n"
        "       dm.organism_name AS organism_name\n"
        "ORDER BY dm.id ASC"
    )
    return cypher, params


def build_genes_by_numeric_metric_summary(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_percentile: float | None = None,
    max_percentile: float | None = None,
    bucket: list[str] | None = None,
    max_rank: int | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_numeric_metric.

    Takes the gate-validated `derived_metric_ids` list (api/ has already
    resolved metric_types and excluded incompatible DMs), plus all
    edge-level filters that survived gate validation. Produces the
    envelope rollups in one query.

    `significant_only` / `max_adjusted_p_value` are NOT parameters —
    they would never reach this builder against today's KG (api/ raises
    on the all-fail branch). When a has_p_value DM lands, add the
    corresponding edge-level WHERE conditions here.

    RETURN keys: total_matching, total_derived_metrics, total_genes,
    by_organism, by_compartment, by_publication, by_experiment,
    by_metric, top_categories_raw, genes_per_metric_max,
    genes_per_metric_median.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if min_value is not None:
        conditions.append("r.value >= $min_value")
        params["min_value"] = min_value
    if max_value is not None:
        conditions.append("r.value <= $max_value")
        params["max_value"] = max_value
    if min_percentile is not None:
        conditions.append("r.metric_percentile >= $min_percentile")
        params["min_percentile"] = min_percentile
    if max_percentile is not None:
        conditions.append("r.metric_percentile <= $max_percentile")
        params["max_percentile"] = max_percentile
    if bucket is not None:
        conditions.append("r.metric_bucket IN $bucket")
        params["bucket"] = bucket
    if max_rank is not None:
        conditions.append("r.rank_by_metric <= $max_rank")
        params["max_rank"] = max_rank

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene]->(g:Gene)\n"
        f"{where_block}"
        "WITH collect({\n"
        "  dm_id: dm.id, dm_name: dm.name, mt: dm.metric_type, vk: dm.value_kind,\n"
        "  org: g.organism_name, cat: coalesce(g.gene_category, 'Unknown'),\n"
        "  comp: dm.compartment, doi: dm.publication_doi, exp: dm.experiment_id,\n"
        "  lt: g.locus_tag,\n"
        "  value: r.value, rank: r.rank_by_metric,\n"
        "  dm_vmin: dm.value_min, dm_vq1: dm.value_q1, dm_vmed: dm.value_median,\n"
        "  dm_vq3: dm.value_q3, dm_vmax: dm.value_max\n"
        "}) AS rows\n"
        "RETURN\n"
        "  size(rows) AS total_matching,\n"
        "  size(apoc.coll.toSet([x IN rows | x.dm_id])) AS total_derived_metrics,\n"
        "  size(apoc.coll.toSet([x IN rows | x.lt])) AS total_genes,\n"
        "  apoc.coll.frequencies([x IN rows | x.org]) AS by_organism,\n"
        "  apoc.coll.frequencies([x IN rows | x.comp]) AS by_compartment,\n"
        "  apoc.coll.frequencies([x IN rows | x.doi]) AS by_publication,\n"
        "  apoc.coll.frequencies([x IN rows | x.exp]) AS by_experiment,\n"
        "  apoc.coll.frequencies([x IN rows | x.cat]) AS top_categories_raw,\n"
        "  [dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "    {derived_metric_id: dm_id,\n"
        "     name:        head([x IN rows WHERE x.dm_id = dm_id | x.dm_name]),\n"
        "     metric_type: head([x IN rows WHERE x.dm_id = dm_id | x.mt]),\n"
        "     value_kind:  head([x IN rows WHERE x.dm_id = dm_id | x.vk]),\n"
        "     count:       size([x IN rows WHERE x.dm_id = dm_id]),\n"
        "     value_min:    apoc.coll.min([x IN rows WHERE x.dm_id = dm_id | x.value]),\n"
        "     value_max:    apoc.coll.max([x IN rows WHERE x.dm_id = dm_id | x.value]),\n"
        "     value_median: apoc.coll.sort([x IN rows WHERE x.dm_id = dm_id | x.value])\n"
        "                     [toInteger(size([x IN rows WHERE x.dm_id = dm_id]) / 2)],\n"
        "     value_q1: apoc.coll.sort([x IN rows WHERE x.dm_id = dm_id | x.value])\n"
        "                 [toInteger(size([x IN rows WHERE x.dm_id = dm_id]) * 0.25)],\n"
        "     value_q3: apoc.coll.sort([x IN rows WHERE x.dm_id = dm_id | x.value])\n"
        "                 [toInteger(size([x IN rows WHERE x.dm_id = dm_id]) * 0.75)],\n"
        "     dm_value_min:    head([x IN rows WHERE x.dm_id = dm_id | x.dm_vmin]),\n"
        "     dm_value_q1:     head([x IN rows WHERE x.dm_id = dm_id | x.dm_vq1]),\n"
        "     dm_value_median: head([x IN rows WHERE x.dm_id = dm_id | x.dm_vmed]),\n"
        "     dm_value_q3:     head([x IN rows WHERE x.dm_id = dm_id | x.dm_vq3]),\n"
        "     dm_value_max:    head([x IN rows WHERE x.dm_id = dm_id | x.dm_vmax]),\n"
        "     rank_min: apoc.coll.min(\n"
        "       [x IN rows WHERE x.dm_id = dm_id AND x.rank IS NOT NULL | x.rank]),\n"
        "     rank_max: apoc.coll.max(\n"
        "       [x IN rows WHERE x.dm_id = dm_id AND x.rank IS NOT NULL | x.rank])\n"
        "    }] AS by_metric,\n"
        "  apoc.coll.max([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                 size([x IN rows WHERE x.dm_id = dm_id])]) AS genes_per_metric_max,\n"
        "  toFloat(apoc.coll.sort([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                          size([x IN rows WHERE x.dm_id = dm_id])])\n"
        "          [toInteger(size(apoc.coll.toSet([x IN rows | x.dm_id])) / 2)])\n"
        "    AS genes_per_metric_median"
    )
    return cypher, params


def build_genes_by_numeric_metric(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_percentile: float | None = None,
    max_percentile: float | None = None,
    bucket: list[str] | None = None,
    max_rank: int | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_numeric_metric.

    Takes the gate-validated `derived_metric_ids` list. Same edge-level
    filter set as the summary builder. Returns 14 compact columns
    (per-row gene + DM identity + gate echoes + value extras), plus 13
    verbose columns when verbose=True.

    NOTE: adjusted_p_value, significant declared in Pydantic Result with
    default=None, NOT in current Cypher RETURN — no edge in today's KG
    carries those props (no DM has has_p_value='true') and including them
    produces CyVer schema warnings. p_value (raw, edge-side) is also
    deferred for the same reason. Re-add CASE-gated RETURN columns
    (`CASE WHEN dm.has_p_value = 'true' THEN r.<col> ELSE null END`)
    when a has_p_value='true' DM lands.

    RETURN keys (compact, 14 columns): locus_tag, gene_name, product,
    gene_category, organism_name, derived_metric_id, name, value_kind,
    rankable, has_p_value, value, rank_by_metric, metric_percentile,
    metric_bucket.

    RETURN keys (verbose adds, 13 columns): metric_type,
    field_description, unit, compartment, experiment_id, publication_doi,
    treatment_type, background_factors, treatment, light_condition,
    experimental_context, gene_function_description, gene_summary.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if min_value is not None:
        conditions.append("r.value >= $min_value")
        params["min_value"] = min_value
    if max_value is not None:
        conditions.append("r.value <= $max_value")
        params["max_value"] = max_value
    if min_percentile is not None:
        conditions.append("r.metric_percentile >= $min_percentile")
        params["min_percentile"] = min_percentile
    if max_percentile is not None:
        conditions.append("r.metric_percentile <= $max_percentile")
        params["max_percentile"] = max_percentile
    if bucket is not None:
        conditions.append("r.metric_bucket IN $bucket")
        params["bucket"] = bucket
    if max_rank is not None:
        conditions.append("r.rank_by_metric <= $max_rank")
        params["max_rank"] = max_rank

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.metric_type AS metric_type"
            ",\n       dm.field_description AS field_description"
            ",\n       dm.unit AS unit"
            ",\n       dm.compartment AS compartment"
            ",\n       dm.experiment_id AS experiment_id"
            ",\n       dm.publication_doi AS publication_doi"
            ",\n       coalesce(dm.treatment_type, []) AS treatment_type"
            ",\n       coalesce(dm.background_factors, []) AS background_factors"
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
            ",\n       g.function_description AS gene_function_description"
            ",\n       g.gene_summary AS gene_summary"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene]->(g:Gene)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       g.gene_category AS gene_category,\n"
        "       g.organism_name AS organism_name,\n"
        "       dm.id AS derived_metric_id,\n"
        "       dm.name AS name,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.rankable = 'true' AS rankable,\n"
        "       dm.has_p_value = 'true' AS has_p_value,\n"
        "       r.value AS value,\n"
        "       CASE WHEN dm.rankable = 'true' THEN r.rank_by_metric ELSE null END AS rank_by_metric,\n"
        "       CASE WHEN dm.rankable = 'true' THEN r.metric_percentile ELSE null END AS metric_percentile,\n"
        "       CASE WHEN dm.rankable = 'true' THEN r.metric_bucket ELSE null END AS metric_bucket"
        f"{verbose_cols}\n"
        "ORDER BY r.rank_by_metric ASC, r.value DESC, dm.id ASC, g.locus_tag ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_genes_by_boolean_metric_diagnostics(
    *,
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Pre-flight DM selection + value_kind validation probe for boolean drill-down.

    Reuses `_list_derived_metrics_where` for DM-scoping conditions with a
    hardcoded `value_kind='boolean'` predicate. Mismatched IDs (numeric or
    categorical DMs passed in `derived_metric_ids`) surface as zero-row
    results that api/ converts into `not_found_ids`.

    RETURN keys (one row per surviving DM, 6 columns):
      derived_metric_id, metric_type, value_kind, name,
      total_gene_count, organism_name.
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism,
        metric_types=metric_types,
        value_kind="boolean",
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
        publication_doi=publication_doi,
        experiment_ids=experiment_ids,
        derived_metric_ids=derived_metric_ids,
    )

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)\n"
        f"{where_block}"
        "RETURN dm.id AS derived_metric_id,\n"
        "       dm.metric_type AS metric_type,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.name AS name,\n"
        "       dm.total_gene_count AS total_gene_count,\n"
        "       dm.organism_name AS organism_name\n"
        "ORDER BY dm.id ASC"
    )
    return cypher, params


def build_genes_by_boolean_metric_summary(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    flag: bool | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_boolean_metric.

    Takes the diagnostics-validated `derived_metric_ids` list plus the
    edge-level `flag` filter. Boolean DMs have no rankable / has_p_value
    gates so no gate-resolution step is needed.

    RETURN keys: total_matching, total_derived_metrics, total_genes,
    by_organism, by_compartment, by_publication, by_experiment,
    by_value, top_categories_raw, by_metric (per-DM filtered + full-DM
    precomputed counts), genes_per_metric_max, genes_per_metric_median.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if flag is not None:
        # Edge property `value` is BioCypher string-typed bool ("true"/"false").
        conditions.append("r.value = $flag_str")
        params["flag_str"] = "true" if flag else "false"

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_flags_gene]->(g:Gene)\n"
        f"{where_block}"
        "WITH collect({\n"
        "  dm_id: dm.id, dm_name: dm.name, mt: dm.metric_type, vk: dm.value_kind,\n"
        "  org: g.organism_name, cat: coalesce(g.gene_category, 'Unknown'),\n"
        "  comp: dm.compartment, doi: dm.publication_doi, exp: dm.experiment_id,\n"
        "  lt: g.locus_tag,\n"
        "  value: r.value,\n"
        "  dm_total: dm.total_gene_count,\n"
        "  dm_true: dm.flag_true_count,\n"
        "  dm_false: dm.flag_false_count\n"
        "}) AS rows\n"
        "RETURN\n"
        "  size(rows) AS total_matching,\n"
        "  size(apoc.coll.toSet([x IN rows | x.dm_id])) AS total_derived_metrics,\n"
        "  size(apoc.coll.toSet([x IN rows | x.lt])) AS total_genes,\n"
        "  apoc.coll.frequencies([x IN rows | x.org]) AS by_organism,\n"
        "  apoc.coll.frequencies([x IN rows | x.comp]) AS by_compartment,\n"
        "  apoc.coll.frequencies([x IN rows | x.doi]) AS by_publication,\n"
        "  apoc.coll.frequencies([x IN rows | x.exp]) AS by_experiment,\n"
        "  apoc.coll.frequencies([x IN rows | x.value]) AS by_value,\n"
        "  apoc.coll.frequencies([x IN rows | x.cat]) AS top_categories_raw,\n"
        "  [dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "    {derived_metric_id: dm_id,\n"
        "     name:        head([x IN rows WHERE x.dm_id = dm_id | x.dm_name]),\n"
        "     metric_type: head([x IN rows WHERE x.dm_id = dm_id | x.mt]),\n"
        "     value_kind:  head([x IN rows WHERE x.dm_id = dm_id | x.vk]),\n"
        "     count:       size([x IN rows WHERE x.dm_id = dm_id]),\n"
        "     true_count:  size([x IN rows WHERE x.dm_id = dm_id AND x.value = 'true']),\n"
        "     false_count: size([x IN rows WHERE x.dm_id = dm_id AND x.value = 'false']),\n"
        "     dm_total_gene_count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_total]),\n"
        "     dm_true_count:  head([x IN rows WHERE x.dm_id = dm_id | x.dm_true]),\n"
        "     dm_false_count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_false])\n"
        "    }] AS by_metric,\n"
        "  apoc.coll.max([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                 size([x IN rows WHERE x.dm_id = dm_id])]) AS genes_per_metric_max,\n"
        "  toFloat(apoc.coll.sort([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                          size([x IN rows WHERE x.dm_id = dm_id])])\n"
        "          [toInteger(size(apoc.coll.toSet([x IN rows | x.dm_id])) / 2)])\n"
        "    AS genes_per_metric_median"
    )
    return cypher, params


def build_genes_by_boolean_metric(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    flag: bool | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_boolean_metric.

    11 compact RETURN columns (per-row gene + DM identity + value),
    plus 13 verbose columns. No CASE-gate wrappers: boolean edges have
    no rankable / has_p_value extras.

    RETURN keys (compact, 11): locus_tag, gene_name, product, gene_category,
    organism_name, derived_metric_id, name, value_kind, rankable,
    has_p_value, value.

    RETURN keys (verbose adds, 13): metric_type, field_description, unit,
    compartment, experiment_id, publication_doi, treatment_type,
    background_factors, treatment, light_condition, experimental_context,
    gene_function_description, gene_summary.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if flag is not None:
        # Edge property `value` is BioCypher string-typed bool ("true"/"false").
        conditions.append("r.value = $flag_str")
        params["flag_str"] = "true" if flag else "false"

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.metric_type AS metric_type"
            ",\n       dm.field_description AS field_description"
            ",\n       dm.unit AS unit"
            ",\n       dm.compartment AS compartment"
            ",\n       dm.experiment_id AS experiment_id"
            ",\n       dm.publication_doi AS publication_doi"
            ",\n       coalesce(dm.treatment_type, []) AS treatment_type"
            ",\n       coalesce(dm.background_factors, []) AS background_factors"
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
            ",\n       g.function_description AS gene_function_description"
            ",\n       g.gene_summary AS gene_summary"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_flags_gene]->(g:Gene)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       g.gene_category AS gene_category,\n"
        "       g.organism_name AS organism_name,\n"
        "       dm.id AS derived_metric_id,\n"
        "       dm.name AS name,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.rankable = 'true' AS rankable,\n"
        "       dm.has_p_value = 'true' AS has_p_value,\n"
        "       r.value AS value"
        f"{verbose_cols}\n"
        "ORDER BY dm.id ASC, g.locus_tag ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params


def build_genes_by_categorical_metric_diagnostics(
    *,
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Pre-flight DM selection + value_kind validation probe for categorical drill-down.

    Reuses `_list_derived_metrics_where` for DM-scoping conditions with a
    hardcoded `value_kind='categorical'` predicate. Mismatched IDs surface
    as zero-row results that api/ converts into `not_found_ids`.

    RETURN keys (one row per surviving DM, 7 columns):
      derived_metric_id, metric_type, value_kind, name,
      total_gene_count, organism_name, allowed_categories.
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism,
        metric_types=metric_types,
        value_kind="categorical",
        compartment=compartment,
        treatment_type=treatment_type,
        background_factors=background_factors,
        growth_phases=growth_phases,
        publication_doi=publication_doi,
        experiment_ids=experiment_ids,
        derived_metric_ids=derived_metric_ids,
    )

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)\n"
        f"{where_block}"
        "RETURN dm.id AS derived_metric_id,\n"
        "       dm.metric_type AS metric_type,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.name AS name,\n"
        "       dm.total_gene_count AS total_gene_count,\n"
        "       dm.organism_name AS organism_name,\n"
        "       dm.allowed_categories AS allowed_categories\n"
        "ORDER BY dm.id ASC"
    )
    return cypher, params


def build_genes_by_categorical_metric_summary(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    categories: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_categorical_metric.

    Takes the diagnostics-validated `derived_metric_ids` list plus the
    edge-level `categories` filter (api/ has already validated each
    category against the union of allowed_categories per DM).

    RETURN keys: total_matching, total_derived_metrics, total_genes,
    by_organism, by_compartment, by_publication, by_experiment,
    by_category, top_categories_raw, by_metric (per-DM filtered slice +
    full-DM precomputed histogram via dm.category_labels /
    dm.category_counts), genes_per_metric_max, genes_per_metric_median.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if categories is not None:
        conditions.append("r.value IN $categories")
        params["categories"] = categories

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_classifies_gene]->(g:Gene)\n"
        f"{where_block}"
        "WITH collect({\n"
        "  dm_id: dm.id, dm_name: dm.name, mt: dm.metric_type, vk: dm.value_kind,\n"
        "  org: g.organism_name, cat: coalesce(g.gene_category, 'Unknown'),\n"
        "  comp: dm.compartment, doi: dm.publication_doi, exp: dm.experiment_id,\n"
        "  lt: g.locus_tag,\n"
        "  value: r.value,\n"
        "  dm_total: dm.total_gene_count,\n"
        "  dm_labels: dm.category_labels,\n"
        "  dm_counts: dm.category_counts,\n"
        "  dm_allowed: dm.allowed_categories\n"
        "}) AS rows\n"
        "RETURN\n"
        "  size(rows) AS total_matching,\n"
        "  size(apoc.coll.toSet([x IN rows | x.dm_id])) AS total_derived_metrics,\n"
        "  size(apoc.coll.toSet([x IN rows | x.lt])) AS total_genes,\n"
        "  apoc.coll.frequencies([x IN rows | x.org]) AS by_organism,\n"
        "  apoc.coll.frequencies([x IN rows | x.comp]) AS by_compartment,\n"
        "  apoc.coll.frequencies([x IN rows | x.doi]) AS by_publication,\n"
        "  apoc.coll.frequencies([x IN rows | x.exp]) AS by_experiment,\n"
        "  apoc.coll.frequencies([x IN rows | x.value]) AS by_category,\n"
        "  apoc.coll.frequencies([x IN rows | x.cat]) AS top_categories_raw,\n"
        "  [dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "    {derived_metric_id: dm_id,\n"
        "     name:        head([x IN rows WHERE x.dm_id = dm_id | x.dm_name]),\n"
        "     metric_type: head([x IN rows WHERE x.dm_id = dm_id | x.mt]),\n"
        "     value_kind:  head([x IN rows WHERE x.dm_id = dm_id | x.vk]),\n"
        "     count:       size([x IN rows WHERE x.dm_id = dm_id]),\n"
        "     by_category: apoc.coll.frequencies([x IN rows WHERE x.dm_id = dm_id | x.value]),\n"
        "     allowed_categories:  head([x IN rows WHERE x.dm_id = dm_id | x.dm_allowed]),\n"
        "     dm_total_gene_count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_total]),\n"
        "     dm_by_category:\n"
        "       [i IN range(0,\n"
        "            size(head([x IN rows WHERE x.dm_id = dm_id | x.dm_labels])) - 1)\n"
        "        | {item:  head([x IN rows WHERE x.dm_id = dm_id | x.dm_labels])[i],\n"
        "           count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_counts])[i]}]\n"
        "    }] AS by_metric,\n"
        "  apoc.coll.max([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                 size([x IN rows WHERE x.dm_id = dm_id])]) AS genes_per_metric_max,\n"
        "  toFloat(apoc.coll.sort([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |\n"
        "                          size([x IN rows WHERE x.dm_id = dm_id])])\n"
        "          [toInteger(size(apoc.coll.toSet([x IN rows | x.dm_id])) / 2)])\n"
        "    AS genes_per_metric_median"
    )
    return cypher, params


def build_genes_by_categorical_metric(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    categories: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_categorical_metric.

    11 compact RETURN columns (per-row gene + DM identity + value),
    plus 14 verbose columns (= boolean's 13 verbose + allowed_categories).
    No CASE-gate wrappers: categorical edges have no rankable / has_p_value
    extras.

    RETURN keys (compact, 11): locus_tag, gene_name, product, gene_category,
    organism_name, derived_metric_id, name, value_kind, rankable,
    has_p_value, value.

    RETURN keys (verbose adds, 14): metric_type, field_description, unit,
    compartment, experiment_id, publication_doi, treatment_type,
    background_factors, treatment, light_condition, experimental_context,
    gene_function_description, gene_summary, allowed_categories.
    """
    params: dict = {"derived_metric_ids": derived_metric_ids}

    conditions: list[str] = ["dm.id IN $derived_metric_ids"]
    if locus_tags is not None:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if categories is not None:
        conditions.append("r.value IN $categories")
        params["categories"] = categories

    where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.metric_type AS metric_type"
            ",\n       dm.field_description AS field_description"
            ",\n       dm.unit AS unit"
            ",\n       dm.compartment AS compartment"
            ",\n       dm.experiment_id AS experiment_id"
            ",\n       dm.publication_doi AS publication_doi"
            ",\n       coalesce(dm.treatment_type, []) AS treatment_type"
            ",\n       coalesce(dm.background_factors, []) AS background_factors"
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
            ",\n       g.function_description AS gene_function_description"
            ",\n       g.gene_summary AS gene_summary"
            ",\n       dm.allowed_categories AS allowed_categories"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_classifies_gene]->(g:Gene)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       g.product AS product,\n"
        "       g.gene_category AS gene_category,\n"
        "       g.organism_name AS organism_name,\n"
        "       dm.id AS derived_metric_id,\n"
        "       dm.name AS name,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.rankable = 'true' AS rankable,\n"
        "       dm.has_p_value = 'true' AS has_p_value,\n"
        "       r.value AS value"
        f"{verbose_cols}\n"
        "ORDER BY r.value ASC, dm.id ASC, g.locus_tag ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params
