"""Public Python API for the multi-omics knowledge graph.

Each function wraps query builders + connection.execute_query to provide
a clean interface for scripts, notebooks, and the MCP tool layer.

No limit parameters — callers slice results as needed.
No JSON formatting — returns Python dicts/lists.
Validation errors raise ValueError with specific messages.
"""

import logging
import re
from collections import defaultdict

from neo4j.exceptions import ClientError as Neo4jClientError

from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.constants import (
    MAX_SPECIFICITY_RANK,
    VALID_OG_SOURCES,
    VALID_TAXONOMIC_LEVELS,
)
from multiomics_explorer.kg.queries_lib import (
    build_gene_ontology_terms,
    build_gene_overview,
    build_gene_stub,
    build_genes_by_ontology,
    build_get_gene_details,
    build_get_homologs_groups,
    build_get_homologs_members,
    build_list_gene_categories,
    build_list_organisms,
    build_list_publications,
    build_list_publications_summary,
    build_list_experiments,
    build_list_experiments_summary,
    build_resolve_gene,
    build_search_genes,
    build_search_genes_dedup_groups,
    build_search_ontology,
)
from multiomics_explorer.kg.schema import load_schema_from_neo4j

logger = logging.getLogger(__name__)


def _default_conn(conn: GraphConnection | None) -> GraphConnection:
    if conn is None:
        return GraphConnection()
    return conn


# Regex for blocking write operations in raw Cypher.
_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|CALL\s*\{|CALL\s+\w+\.\w+|LOAD\s+CSV)\b",
    re.IGNORECASE,
)

# Regex for escaping Lucene special characters on retry.
_LUCENE_SPECIAL = re.compile(r'[+\-!(){}\[\]^"~*?:\\/]')


def get_schema(
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get the knowledge graph schema as a plain dict.

    Returns dict with keys:
      nodes: {label: {properties: {name: type}}}
      relationships: {type: {source_labels, target_labels, properties}}
    """
    conn = _default_conn(conn)
    schema = load_schema_from_neo4j(conn)
    return schema.to_dict()


def resolve_gene(
    identifier: str,
    organism: str | None = None,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Resolve a gene identifier to matching graph nodes.

    Returns dict with keys: total_matching, by_organism, returned, truncated,
    results.
    Per result: locus_tag, gene_name, product, organism_strain.
    """
    if not identifier or not identifier.strip():
        logger.debug("resolve_gene: empty identifier")
        raise ValueError("identifier must not be empty.")
    conn = _default_conn(conn)
    cypher, params = build_resolve_gene(identifier=identifier, organism=organism)
    all_results = conn.execute_query(cypher, **params)
    total = len(all_results)

    # Compute by_organism from all matching results
    org_counts: dict[str, int] = {}
    for row in all_results:
        org = row.get("organism_strain", "Unknown")
        org_counts[org] = org_counts.get(org, 0) + 1
    by_organism = sorted(
        [{"organism_name": k, "gene_count": v} for k, v in org_counts.items()],
        key=lambda x: x["gene_count"],
        reverse=True,
    )

    results = all_results[:limit] if limit else all_results
    return {
        "total_matching": total,
        "by_organism": by_organism,
        "returned": len(results),
        "truncated": total > len(results),
        "results": results,
    }


def search_genes(
    search_text: str,
    organism: str | None = None,
    category: str | None = None,
    min_quality: int = 0,
    deduplicate: bool = False,
    *,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """Free-text search across gene functional annotations.

    Returns list of dicts with keys: locus_tag, gene_name, product,
    function_description, gene_summary, organism_strain,
    annotation_quality, score.

    When deduplicate=True, representatives also have collapsed_count
    and group_organisms keys.
    """
    conn = _default_conn(conn)
    cypher, params = build_search_genes(
        search_text=search_text, organism=organism,
        category=category, min_quality=min_quality,
    )
    try:
        results = conn.execute_query(cypher, **params)
    except Neo4jClientError:
        logger.debug("search_genes: Lucene parse error, retrying with escaped query")
        escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
        cypher, params = build_search_genes(
            search_text=escaped, organism=organism,
            category=category, min_quality=min_quality,
        )
        results = conn.execute_query(cypher, **params)

    if deduplicate:
        logger.debug("search_genes: deduplicating %d results by orthogroup", len(results))
        results = _deduplicate_by_orthogroup(results, conn)

    return results


def _deduplicate_by_orthogroup(
    results: list[dict], conn: GraphConnection,
) -> list[dict]:
    """Collapse search results by ortholog group."""
    locus_tags = [r["locus_tag"] for r in results]
    dedup_cypher, dedup_params = build_search_genes_dedup_groups(
        locus_tags=locus_tags,
    )
    dedup_rows = conn.execute_query(dedup_cypher, **dedup_params)
    tag_to_group = {r["locus_tag"]: r["dedup_group"] for r in dedup_rows}

    seen_groups: dict[str, list] = {}
    deduped = []
    for row in results:
        group = tag_to_group.get(row["locus_tag"])
        if group:
            if group in seen_groups:
                seen_groups[group].append(row)
                continue
            seen_groups[group] = [row]
        deduped.append(row)

    for row in deduped:
        group = tag_to_group.get(row["locus_tag"])
        if group:
            members = seen_groups[group]
            row["collapsed_count"] = len(members)
            org_counts: dict[str, int] = {}
            for r in members:
                org = r.get("organism_strain", "Unknown")
                org_counts[org] = org_counts.get(org, 0) + 1
            row["group_organisms"] = org_counts

    return deduped


def gene_overview(
    gene_ids: list[str],
    *,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """Get overview of one or more genes: identity + data availability.

    Returns list of dicts with keys: locus_tag, gene_name, product,
    gene_summary, gene_category, annotation_quality, organism_strain,
    annotation_types, expression_edge_count,
    significant_expression_count, closest_ortholog_group_size,
    closest_ortholog_genera.
    """
    conn = _default_conn(conn)
    cypher, params = build_gene_overview(gene_ids=gene_ids)
    return conn.execute_query(cypher, **params)


def get_gene_details(
    gene_id: str,
    *,
    conn: GraphConnection | None = None,
) -> dict | None:
    """Get all properties for a gene node.

    Returns a flat dict of all Gene node properties, or None if the
    gene is not found.
    """
    conn = _default_conn(conn)
    cypher, params = build_get_gene_details(gene_id=gene_id)
    results = conn.execute_query(cypher, **params)
    if not results or results[0]["gene"] is None:
        return None
    return results[0]["gene"]



def get_homologs(
    gene_id: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    exclude_paralogs: bool = True,
    include_members: bool = False,
    member_limit: int = 50,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Find orthologs grouped by ortholog group.

    Returns dict with keys:
      query_gene: dict with locus_tag, gene_name, product, organism_strain
      ortholog_groups: list[dict] with og_name, source, taxonomic_level,
        specificity_rank, consensus_product, consensus_gene_name,
        member_count, organism_count, genera, has_cross_genus_members.
        When include_members=True, each group also has a members list
        and optionally a truncated flag.

    Raises ValueError if gene not found or params invalid.
    """
    conn = _default_conn(conn)

    # Validate enum params
    if source is not None and source not in VALID_OG_SOURCES:
        logger.debug("get_homologs: invalid source '%s'", source)
        raise ValueError(
            f"Invalid source '{source}'. Valid: {sorted(VALID_OG_SOURCES)}"
        )
    if taxonomic_level is not None and taxonomic_level not in VALID_TAXONOMIC_LEVELS:
        logger.debug("get_homologs: invalid taxonomic_level '%s'", taxonomic_level)
        raise ValueError(
            f"Invalid taxonomic_level '{taxonomic_level}'. "
            f"Valid: {sorted(VALID_TAXONOMIC_LEVELS)}"
        )
    if max_specificity_rank is not None and not (
        0 <= max_specificity_rank <= MAX_SPECIFICITY_RANK
    ):
        logger.debug("get_homologs: invalid max_specificity_rank %s", max_specificity_rank)
        raise ValueError(
            f"Invalid max_specificity_rank {max_specificity_rank}. "
            f"Valid: 0-{MAX_SPECIFICITY_RANK}."
        )
    if not (1 <= member_limit <= 200):
        logger.debug("get_homologs: invalid member_limit %s", member_limit)
        raise ValueError(
            f"Invalid member_limit {member_limit}. Valid: 1-200."
        )

    # 1. Query gene metadata
    logger.debug("get_homologs: fetching gene stub for '%s'", gene_id)
    cypher_gene, params_gene = build_gene_stub(gene_id=gene_id)
    gene_rows = conn.execute_query(cypher_gene, **params_gene)
    if not gene_rows:
        raise ValueError(f"Gene '{gene_id}' not found.")
    query_gene = gene_rows[0]

    # 2. Query ortholog groups
    logger.debug("get_homologs: fetching ortholog groups for '%s'", gene_id)
    cypher_groups, params_groups = build_get_homologs_groups(
        gene_id=gene_id, source=source,
        taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
    )
    groups = conn.execute_query(cypher_groups, **params_groups)

    # 3. Optionally fetch members
    if include_members and groups:
        logger.debug("get_homologs: fetching members for %d groups", len(groups))
        cypher_members, params_members = build_get_homologs_members(
            gene_id=gene_id, source=source,
            taxonomic_level=taxonomic_level,
            max_specificity_rank=max_specificity_rank,
            exclude_paralogs=exclude_paralogs,
        )
        members = conn.execute_query(cypher_members, **params_members)

        members_by_og: dict[str, list] = defaultdict(list)
        for m in members:
            members_by_og[m.pop("og_name")].append(m)

        for g in groups:
            og_members = members_by_og.get(g["og_name"], [])
            if len(og_members) > member_limit:
                g["members"] = og_members[:member_limit]
                g["truncated"] = True
            else:
                g["members"] = og_members

    return {"query_gene": query_gene, "ortholog_groups": groups}


def list_filter_values(
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List valid values for categorical filters.

    Returns dict with keys:
      gene_categories: list[dict] with category, gene_count
    """
    conn = _default_conn(conn)

    logger.debug("list_filter_values: fetching gene categories")
    cat_cypher, cat_params = build_list_gene_categories()
    categories = conn.execute_query(cat_cypher, **cat_params)

    return {
        "gene_categories": categories,
    }


def list_organisms(
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List all organisms in the knowledge graph.

    Returns dict with keys: total_entries, returned, truncated, results.
    Per result: organism_name, genus, species, strain, clade,
    ncbi_taxon_id, gene_count, publication_count, experiment_count,
    treatment_types, omics_types.
    When verbose=True, also includes: family, order, tax_class, phylum,
    kingdom, superkingdom, lineage.
    """
    conn = _default_conn(conn)
    cypher, params = build_list_organisms(verbose=verbose)
    all_results = conn.execute_query(cypher, **params)
    total = len(all_results)
    results = all_results[:limit] if limit else all_results
    return {
        "total_entries": total,
        "returned": len(results),
        "truncated": total > len(results),
        "results": results,
    }


def list_publications(
    organism: str | None = None,
    treatment_type: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List publications with expression data.

    Returns dict with keys: total_entries, total_matching, returned, truncated,
    by_organism, by_treatment_type, by_omics_type, results.
    Per result: doi, title, authors, year, journal, study_type, organisms,
    experiment_count, treatment_types, omics_types.
    When verbose=True, also includes abstract, description.
    When search_text is provided, also includes score.
    """
    conn = _default_conn(conn)
    filter_kwargs = dict(
        organism=organism, treatment_type=treatment_type,
        search_text=search_text, author=author,
    )

    def _execute(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        summary_cypher, summary_params = build_list_publications_summary(**kw)
        summary = conn.execute_query(summary_cypher, **summary_params)[0]

        # Fetch all matching for breakdowns, then slice for results
        data_cypher, data_params = build_list_publications(
            **kw, verbose=verbose,
        )
        all_results = conn.execute_query(data_cypher, **data_params)
        return summary, all_results

    try:
        summary, all_results = _execute()
    except Neo4jClientError:
        if search_text:
            logger.debug("list_publications: Lucene parse error, retrying with escaped query")
            escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            summary, all_results = _execute(st=escaped)
        else:
            raise

    # Compute breakdowns from all matching publications
    org_counts: dict[str, int] = {}
    tt_counts: dict[str, int] = {}
    omics_counts: dict[str, int] = {}
    for pub in all_results:
        for org in pub.get("organisms", []):
            org_counts[org] = org_counts.get(org, 0) + 1
        for tt in pub.get("treatment_types", []):
            tt_counts[tt] = tt_counts.get(tt, 0) + 1
        for ot in pub.get("omics_types", []):
            omics_counts[ot] = omics_counts.get(ot, 0) + 1

    def _sorted_breakdown(counts, key_name):
        return sorted(
            [{key_name: k, "publication_count": v} for k, v in counts.items()],
            key=lambda x: x["publication_count"],
            reverse=True,
        )

    results = all_results[:limit] if limit else all_results

    return {
        "total_entries": summary["total_entries"],
        "total_matching": summary["total_matching"],
        "by_organism": _sorted_breakdown(org_counts, "organism_name"),
        "by_treatment_type": _sorted_breakdown(tt_counts, "treatment_type"),
        "by_omics_type": _sorted_breakdown(omics_counts, "omics_type"),
        "returned": len(results),
        "truncated": summary["total_matching"] > len(results),
        "results": results,
    }


def list_experiments(
    organism: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
    coculture_partner: str | None = None,
    search_text: str | None = None,
    time_course_only: bool = False,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List experiments with gene count statistics.

    Always returns: total_entries, total_matching, by_organism,
    by_treatment_type, by_omics_type, by_publication, time_course_count,
    returned, truncated, results.

    summary=True is sugar for limit=0: results is empty list,
    returned=0, truncated=True.
    When summary=False (default): results populated with experiments.
    Per result: experiment_id, publication_doi, organism_strain,
    treatment_type, coculture_partner, omics_type, is_time_course (bool),
    time_points (list, omitted if not time-course), gene_count,
    significant_count.
    When verbose=True, also includes: name, publication_title, treatment,
    control, light_condition, light_intensity, medium, temperature,
    statistical_test, experimental_context.
    When search_text is provided, detail results include score.
    """
    if summary:
        limit = 0

    conn = _default_conn(conn)
    filter_kwargs = dict(
        organism=organism, treatment_type=treatment_type,
        omics_type=omics_type, publication_doi=publication_doi,
        coculture_partner=coculture_partner, search_text=search_text,
        time_course_only=time_course_only,
    )

    def _run_summary(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        cypher, params = build_list_experiments_summary(**kw)
        return conn.execute_query(cypher, **params)[0]

    def _run_detail(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        cypher, params = build_list_experiments(
            **kw, verbose=verbose, limit=limit,
        )
        return conn.execute_query(cypher, **params)

    # Always run summary query
    try:
        raw_summary = _run_summary()
    except Neo4jClientError:
        if search_text:
            logger.debug("list_experiments: Lucene parse error, retrying with escaped query")
            escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            raw_summary = _run_summary(st=escaped)
            # Update search_text for detail query too
            filter_kwargs["search_text"] = escaped
        else:
            raise

    # Get total_entries (unfiltered count)
    total_cypher, total_params = build_list_experiments_summary()
    total_raw = conn.execute_query(total_cypher, **total_params)[0]
    total_entries = total_raw["total_matching"]

    # Rename apoc.coll.frequencies {item, count} to domain keys, sort desc
    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "experiment_count": f["count"]} for f in freq_list],
            key=lambda x: x["experiment_count"],
            reverse=True,
        )

    envelope = {
        "total_entries": total_entries,
        "total_matching": raw_summary["total_matching"],
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_strain"),
        "by_treatment_type": _rename_freq(raw_summary["by_treatment_type"], "treatment_type"),
        "by_omics_type": _rename_freq(raw_summary["by_omics_type"], "omics_type"),
        "by_publication": _rename_freq(raw_summary["by_publication"], "publication_doi"),
        "time_course_count": raw_summary["time_course_count"],
    }

    # Score distribution (only when search_text used)
    if "score_max" in raw_summary:
        envelope["score_max"] = raw_summary["score_max"]
        envelope["score_median"] = raw_summary["score_median"]
    else:
        envelope["score_max"] = None
        envelope["score_median"] = None

    if limit == 0:
        envelope["returned"] = 0
        envelope["truncated"] = envelope["total_matching"] > 0
        envelope["results"] = []
        return envelope

    # Detail: run detail query
    try:
        results = _run_detail()
    except Neo4jClientError:
        if search_text and filter_kwargs["search_text"] == search_text:
            # Not yet escaped (summary succeeded without retry)
            logger.debug("list_experiments detail: Lucene parse error, retrying")
            escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            results = _run_detail(st=escaped)
        else:
            raise

    # Post-process results
    processed = []
    for row in results:
        r = dict(row)
        # Cast is_time_course string to bool
        r["is_time_course"] = r["is_time_course"] == "true"

        # Assemble time_points from parallel arrays
        tp_count = r.pop("time_point_count", 0)
        tp_labels = r.pop("time_point_labels", [])
        tp_orders = r.pop("time_point_orders", [])
        tp_hours = r.pop("time_point_hours", [])
        tp_totals = r.pop("time_point_totals", [])
        tp_sigs = r.pop("time_point_significants", [])

        if r["is_time_course"] and tp_count > 0:
            time_points = []
            for i in range(tp_count):
                tp = {
                    "label": tp_labels[i] if tp_labels[i] != "" else None,
                    "order": tp_orders[i],
                    "hours": tp_hours[i] if tp_hours[i] != -1.0 else None,
                    "total": tp_totals[i],
                    "significant": tp_sigs[i],
                }
                time_points.append(tp)
            r["time_points"] = time_points
        # Non-time-course: omit time_points key entirely

        processed.append(r)

    envelope["returned"] = len(processed)
    envelope["truncated"] = envelope["total_matching"] > len(processed)
    envelope["results"] = processed
    return envelope


def search_ontology(
    search_text: str,
    ontology: str,
    *,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """Browse ontology terms by text search.

    Returns list of dicts with keys: id, name, score.

    Raises ValueError if ontology is invalid (raised by query builder).
    """
    conn = _default_conn(conn)
    cypher, params = build_search_ontology(
        ontology=ontology, search_text=search_text,
    )
    try:
        results = conn.execute_query(cypher, **params)
    except Neo4jClientError:
        logger.debug("search_ontology: Lucene parse error, retrying with escaped query")
        escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
        cypher, params = build_search_ontology(
            ontology=ontology, search_text=escaped,
        )
        results = conn.execute_query(cypher, **params)
    return results


def genes_by_ontology(
    term_ids: list[str],
    ontology: str,
    organism: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """Find genes annotated to ontology terms, with hierarchy expansion.

    Returns list of dicts with keys: locus_tag, gene_name, product,
    organism_strain.

    Raises ValueError if ontology is invalid (raised by query builder).
    """
    conn = _default_conn(conn)
    cypher, params = build_genes_by_ontology(
        ontology=ontology, term_ids=term_ids, organism=organism,
    )
    return conn.execute_query(cypher, **params)


def gene_ontology_terms(
    gene_id: str,
    ontology: str,
    leaf_only: bool = True,
    *,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """Get ontology annotations for a gene.

    Returns list of dicts with keys: id, name.

    Raises ValueError if ontology is invalid (raised by query builder).
    """
    conn = _default_conn(conn)
    cypher, params = build_gene_ontology_terms(
        ontology=ontology, gene_id=gene_id, leaf_only=leaf_only,
    )
    return conn.execute_query(cypher, **params)


def run_cypher(
    query: str,
    *,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """Execute a raw Cypher query (read-only).

    Write operations are blocked via keyword detection.

    Returns list of dicts (raw query results).

    Raises ValueError if the query contains write keywords.
    """
    if _WRITE_KEYWORDS.search(query):
        raise ValueError(
            "Write operations are not allowed. This interface is read-only."
        )
    conn = _default_conn(conn)
    return conn.execute_query(query)
