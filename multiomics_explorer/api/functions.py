"""Public Python API for the multi-omics knowledge graph.

Each function wraps query builders + connection.execute_query to provide
a clean interface for scripts, notebooks, and the MCP tool layer.

No limit parameters — callers slice results as needed.
No JSON formatting — returns Python dicts/lists.
Validation errors raise ValueError with specific messages.
"""

import logging
import os
import re
import statistics

from CyVer import PropertiesValidator, SchemaValidator, SyntaxValidator

from neo4j.exceptions import ClientError as Neo4jClientError

from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.constants import (
    ALL_ONTOLOGIES,
    GO_ONTOLOGIES,
    MAX_SPECIFICITY_RANK,
    VALID_OG_SOURCES,
    VALID_TAXONOMIC_LEVELS,
)
from multiomics_explorer.kg.queries_lib import (
    ONTOLOGY_CONFIG,
    build_gene_existence_check,
    build_gene_ontology_terms,
    build_gene_ontology_terms_summary,
    build_gene_overview,
    build_gene_overview_summary,
    build_genes_by_function,
    build_genes_by_function_summary,
    build_genes_by_ontology_detail,
    build_genes_by_ontology_per_gene,
    build_genes_by_ontology_per_term,
    build_genes_by_ontology_validate,
    build_gene_details,
    build_gene_details_summary,
    build_gene_homologs,
    build_gene_homologs_summary,
    build_list_brite_trees,
    build_list_gene_categories,
    build_list_organisms,
    build_list_publications,
    build_list_publications_summary,
    build_list_experiments,
    build_list_experiments_summary,
    build_resolve_gene,
    build_search_homolog_groups,
    build_search_homolog_groups_summary,
    build_genes_by_homolog_group,
    build_genes_by_homolog_group_diagnostics,
    build_genes_by_homolog_group_summary,
    build_search_ontology,
    build_search_ontology_summary,
    build_differential_expression_by_gene,
    build_differential_expression_by_gene_summary_global,
    build_differential_expression_by_gene_summary_by_experiment,
    build_differential_expression_by_gene_summary_diagnostics,
    build_resolve_organism_for_organism,
    build_resolve_organism_for_locus_tags,
    build_resolve_organism_for_experiments,
    build_differential_expression_by_ortholog_group_check,
    build_differential_expression_by_ortholog_summary_global,
    build_differential_expression_by_ortholog_top_groups,
    build_differential_expression_by_ortholog_top_experiments,
    build_differential_expression_by_ortholog_results,
    build_differential_expression_by_ortholog_membership_counts,
    build_differential_expression_by_ortholog_diagnostics,
    build_gene_response_profile_envelope,
    build_gene_response_profile,
    build_list_clustering_analyses,
    build_list_clustering_analyses_summary,
    build_gene_clusters_by_gene,
    build_gene_clusters_by_gene_summary,
    build_genes_in_cluster,
    build_genes_in_cluster_summary,
    build_ontology_experiment_check,
    build_ontology_expcov,
    build_ontology_landscape,
    build_ontology_organism_gene_count,
)
from multiomics_explorer.kg.schema import load_schema_from_neo4j

logger = logging.getLogger(__name__)

# Suppress EXPLAIN notification noise emitted by CyVer validators.
logging.getLogger("neo4j").setLevel(logging.ERROR)


def _default_conn(conn: GraphConnection | None) -> GraphConnection:
    if conn is None:
        return GraphConnection()
    return conn


def _chunk_locus_tags(locus_tags: list[str]) -> list[list[str]]:
    """Split locus_tags into chunks for memory-bounded transactions.

    Default 500; override via MULTIOMICS_KG_BATCH_SIZE env var.
    Chunking prevents Neo4j's 1.4 GiB transaction cap on large
    gene × term fan-out queries (e.g. 2000 × GO MF).
    """
    size = int(os.getenv("MULTIOMICS_KG_BATCH_SIZE", "500"))
    if size <= 0 or len(locus_tags) <= size:
        return [locus_tags]
    return [locus_tags[i: i + size] for i in range(0, len(locus_tags), size)]


# Regex for blocking write operations in raw Cypher.
_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|CALL\s*\{|CALL\s+\w+\.\w+|LOAD\s+CSV)\b",
    re.IGNORECASE,
)

# Regex for escaping Lucene special characters on retry.
_LUCENE_SPECIAL = re.compile(r'[+\-!(){}\[\]^"~*?:\\/]')


def kg_schema(
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
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Resolve a gene identifier to matching graph nodes.

    Returns dict with keys: total_matching, by_organism, returned, truncated,
    results.
    Per result: locus_tag, gene_name, product, organism_name.
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
        org = row.get("organism_name", "Unknown")
        org_counts[org] = org_counts.get(org, 0) + 1
    by_organism = sorted(
        [{"organism_name": k, "count": v} for k, v in org_counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    results = all_results[offset:offset + limit] if limit else all_results[offset:]
    return {
        "total_matching": total,
        "by_organism": by_organism,
        "returned": len(results),
        "offset": offset,
        "truncated": total > offset + len(results),
        "results": results,
    }


def genes_by_function(
    search_text: str,
    organism: str | None = None,
    category: str | None = None,
    min_quality: int = 0,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Search genes by functional annotation text.

    Returns dict with keys: total_search_hits, total_matching,
    by_organism, by_category, score_max, score_median,
    returned, truncated, results.
    Per result: locus_tag, gene_name, product, organism_name,
    gene_category, annotation_quality, score.
    Verbose adds: function_description, gene_summary.

    Raises ValueError if search_text is empty.
    """
    if not search_text or not search_text.strip():
        raise ValueError("search_text must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)
    filter_kwargs = dict(
        search_text=search_text, organism=organism,
        category=category, min_quality=min_quality,
    )

    def _run_summary(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        cypher, params = build_genes_by_function_summary(**kw)
        return conn.execute_query(cypher, **params)[0]

    def _run_detail(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        cypher, params = build_genes_by_function(
            **kw, verbose=verbose, limit=limit, offset=offset,
        )
        return conn.execute_query(cypher, **params)

    # Always run summary query
    try:
        raw_summary = _run_summary()
    except Neo4jClientError:
        logger.debug("genes_by_function: Lucene parse error, retrying with escaped query")
        escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
        raw_summary = _run_summary(st=escaped)
        filter_kwargs["search_text"] = escaped

    # Rename APOC {item, count} to domain keys, sort desc
    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_search_hits": raw_summary["total_search_hits"],
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_category": _rename_freq(raw_summary["by_category"], "category"),
        "score_max": raw_summary["score_max"],
        "score_median": raw_summary["score_median"],
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    try:
        results = _run_detail()
    except Neo4jClientError:
        if filter_kwargs["search_text"] == search_text:
            # Not yet escaped (summary succeeded without retry)
            logger.debug("genes_by_function detail: Lucene parse error, retrying")
            escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            results = _run_detail(st=escaped)
        else:
            raise

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def gene_overview(
    locus_tags: list[str],
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get overview of genes: identity + data availability signals.

    Returns dict with keys: total_matching, by_organism, by_category,
    by_annotation_type, has_expression, has_significant_expression,
    has_orthologs, has_clusters, returned, truncated, not_found, results.
    Per result: locus_tag, gene_name, product, gene_category,
    annotation_quality, organism_name, annotation_types,
    expression_edge_count, significant_up_count, significant_down_count,
    closest_ortholog_group_size, closest_ortholog_genera,
    cluster_membership_count, cluster_types.
    Verbose adds: gene_summary, function_description, all_identifiers.

    Raises ValueError if locus_tags is empty.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Summary query — always runs
    sum_cypher, sum_params = build_gene_overview_summary(locus_tags=locus_tags)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    # Rename APOC {item, count} to domain keys, sort desc
    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_category": _rename_freq(raw_summary["by_category"], "category"),
        "by_annotation_type": _rename_freq(
            raw_summary["by_annotation_type"], "annotation_type",
        ),
        "has_expression": raw_summary["has_expression"],
        "has_significant_expression": raw_summary["has_significant_expression"],
        "has_orthologs": raw_summary["has_orthologs"],
        "has_clusters": raw_summary["has_clusters"],
        "not_found": raw_summary["not_found"],
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_gene_overview(
        locus_tags=locus_tags, verbose=verbose, limit=limit, offset=offset,
    )
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def gene_details(
    locus_tags: list[str],
    summary: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get all properties for genes (deep-dive complement to gene_overview).

    Returns dict with keys: total_matching, returned, truncated,
    not_found, results.
    Each result is a flat dict of all Gene node properties (g {.*}).

    summary=True is sugar for limit=0: results=[], summary fields only.
    not_found: input locus_tags not in KG.
    """
    if not locus_tags:
        raise ValueError("locus_tags must be a non-empty list")

    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Summary query — always runs
    sum_cypher, sum_params = build_gene_details_summary(locus_tags=locus_tags)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    total_matching = raw_summary["total_matching"]
    envelope: dict = {
        "total_matching": total_matching,
        "not_found": raw_summary["not_found"],
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_gene_details(
        locus_tags=locus_tags, limit=limit, offset=offset,
    )
    results = [r["gene"] for r in conn.execute_query(det_cypher, **det_params)]

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope



def gene_homologs(
    locus_tags: list[str],
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get ortholog group memberships for genes.

    Returns dict with keys: total_matching, by_organism, by_source,
    top_cyanorak_roles, top_cog_categories,
    returned, truncated, not_found, no_groups, results.
    Per result (compact): locus_tag, organism_name, group_id,
    consensus_gene_name, consensus_product, taxonomic_level, source,
    specificity_rank.
    Per result (verbose): adds member_count, organism_count, genera,
    has_cross_genus_members, description, functional_description.

    Raises ValueError if locus_tags is empty.

    summary=True is sugar for limit=0: results=[], summary fields only.
    not_found: input locus_tags not in KG.
    no_groups: genes that exist but have zero matching OGs.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Validate enum params
    if source is not None and source not in VALID_OG_SOURCES:
        raise ValueError(
            f"Invalid source '{source}'. Valid: {sorted(VALID_OG_SOURCES)}"
        )
    if taxonomic_level is not None and taxonomic_level not in VALID_TAXONOMIC_LEVELS:
        raise ValueError(
            f"Invalid taxonomic_level '{taxonomic_level}'. "
            f"Valid: {sorted(VALID_TAXONOMIC_LEVELS)}"
        )
    if max_specificity_rank is not None and not (
        0 <= max_specificity_rank <= MAX_SPECIFICITY_RANK
    ):
        raise ValueError(
            f"Invalid max_specificity_rank {max_specificity_rank}. "
            f"Valid: 0-{MAX_SPECIFICITY_RANK}."
        )

    filter_kwargs = dict(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
    )

    # Summary query — always runs
    sum_cypher, sum_params = build_gene_homologs_summary(
        locus_tags=locus_tags, **filter_kwargs,
    )
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    def _sorted_breakdown(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    envelope = {
        "total_matching": raw_summary["total_matching"],
        "by_organism": _sorted_breakdown(raw_summary["by_organism"], "organism_name"),
        "by_source": _sorted_breakdown(raw_summary["by_source"], "source"),
        "not_found": raw_summary["not_found"],
        "no_groups": raw_summary["no_groups"],
        "top_cyanorak_roles": raw_summary["top_cyanorak_roles"],
        "top_cog_categories": raw_summary["top_cog_categories"],
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = envelope["total_matching"] > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_gene_homologs(
        locus_tags=locus_tags, **filter_kwargs,
        verbose=verbose, limit=limit, offset=offset,
    )
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = envelope["total_matching"] > offset + len(results)
    envelope["results"] = results
    return envelope


def list_filter_values(
    filter_type: str = "gene_category",
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List valid values for a categorical filter.

    Returns dict with keys: filter_type, total_entries, returned, truncated, results.
    Per result: value, count.
    """
    conn = _default_conn(conn)
    if filter_type == "gene_category":
        cypher, params = build_list_gene_categories()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["category"], "count": r["gene_count"]} for r in rows]
    elif filter_type == "brite_tree":
        cypher, params = build_list_brite_trees()
        rows = conn.execute_query(cypher, **params)
        results = [
            {"value": r["tree"], "tree_code": r["tree_code"], "count": r["term_count"]}
            for r in rows
        ]
    else:
        raise ValueError(f"Unknown filter_type: {filter_type!r}")
    total = len(results)
    return {
        "filter_type": filter_type,
        "total_entries": total,
        "returned": total,
        "truncated": False,
        "results": results,
    }


def list_organisms(
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List all organisms in the knowledge graph.

    Returns dict with keys: total_entries, returned, truncated,
    by_cluster_type, by_organism_type, results.
    Per result: organism_name, genus, species, strain, clade,
    ncbi_taxon_id, organism_type, gene_count, publication_count,
    experiment_count, treatment_types, omics_types,
    clustering_analysis_count, cluster_types.
    Sparse fields (omitted when null): reference_database,
    reference_proteome.
    When verbose=True, also includes: family, order, tax_class, phylum,
    kingdom, superkingdom, lineage, cluster_count.
    """
    conn = _default_conn(conn)
    cypher, params = build_list_organisms(verbose=verbose)
    all_results = conn.execute_query(cypher, **params)
    total = len(all_results)

    # Compute by_cluster_type breakdown from all results
    ct_counts: dict[str, int] = {}
    for org in all_results:
        for ct in org.get("cluster_types", []):
            ct_counts[ct] = ct_counts.get(ct, 0) + 1

    # Compute by_organism_type breakdown from all results
    ot_counts: dict[str, int] = {}
    for org in all_results:
        ot = org.get("organism_type")
        if ot:
            ot_counts[ot] = ot_counts.get(ot, 0) + 1

    results = all_results[offset:offset + limit] if limit else all_results[offset:]

    # Sparse-strip reference fields when null
    for r in results:
        if r.get("reference_database") is None:
            r.pop("reference_database", None)
            r.pop("reference_proteome", None)

    # Gate verbose-only fields
    if not verbose:
        results = [{k: v for k, v in r.items() if k != "cluster_count"} for r in results]

    return {
        "total_entries": total,
        "by_cluster_type": sorted(
            [{"cluster_type": k, "count": v} for k, v in ct_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        ),
        "by_organism_type": sorted(
            [{"organism_type": k, "count": v} for k, v in ot_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        ),
        "returned": len(results),
        "offset": offset,
        "truncated": total > offset + len(results),
        "results": results,
    }


def list_publications(
    organism: str | None = None,
    treatment_type: str | None = None,
    background_factors: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List publications with expression data.

    Returns dict with keys: total_entries, total_matching, returned, truncated,
    by_organism, by_treatment_type, by_background_factors, by_omics_type,
    by_cluster_type, results.
    Per result: doi, title, authors, year, journal, study_type, organisms,
    experiment_count, treatment_types, background_factors, omics_types,
    clustering_analysis_count, cluster_types.
    When verbose=True, also includes abstract, description, cluster_count.
    When search_text is provided, also includes score.
    """
    conn = _default_conn(conn)
    filter_kwargs = dict(
        organism=organism, treatment_type=treatment_type,
        background_factors=background_factors,
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
    bf_counts: dict[str, int] = {}
    omics_counts: dict[str, int] = {}
    ct_counts: dict[str, int] = {}
    for pub in all_results:
        for org in pub.get("organisms", []):
            org_counts[org] = org_counts.get(org, 0) + 1
        for tt in pub.get("treatment_types", []):
            tt_counts[tt] = tt_counts.get(tt, 0) + 1
        for bf in pub.get("background_factors", []):
            bf_counts[bf] = bf_counts.get(bf, 0) + 1
        for ot in pub.get("omics_types", []):
            omics_counts[ot] = omics_counts.get(ot, 0) + 1
        for ct in pub.get("cluster_types", []):
            ct_counts[ct] = ct_counts.get(ct, 0) + 1

    def _sorted_breakdown(counts, key_name):
        return sorted(
            [{key_name: k, "count": v} for k, v in counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )

    results = all_results[offset:offset + limit] if limit else all_results[offset:]

    # Gate verbose-only fields
    if not verbose:
        results = [{k: v for k, v in r.items() if k != "cluster_count"} for r in results]

    return {
        "total_entries": summary["total_entries"],
        "total_matching": summary["total_matching"],
        "by_organism": _sorted_breakdown(org_counts, "organism_name"),
        "by_treatment_type": _sorted_breakdown(tt_counts, "treatment_type"),
        "by_background_factors": _sorted_breakdown(bf_counts, "background_factor"),
        "by_omics_type": _sorted_breakdown(omics_counts, "omics_type"),
        "by_cluster_type": _sorted_breakdown(ct_counts, "cluster_type"),
        "returned": len(results),
        "offset": offset,
        "truncated": summary["total_matching"] > offset + len(results),
        "results": results,
    }


def list_experiments(
    organism: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    omics_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
    coculture_partner: str | None = None,
    search_text: str | None = None,
    time_course_only: bool = False,
    table_scope: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List experiments with gene count statistics.

    Always returns: total_entries, total_matching, by_organism,
    by_treatment_type, by_background_factors, by_omics_type,
    by_publication, by_table_scope, by_cluster_type,
    time_course_count, returned, truncated, results.

    summary=True is sugar for limit=0: results is empty list,
    returned=0, truncated=True.
    When summary=False (default): results populated with experiments.
    Per result: experiment_id, experiment_name, publication_doi,
    organism_name, treatment_type, background_factors, coculture_partner,
    omics_type, is_time_course (bool), table_scope, table_scope_detail,
    gene_count, genes_by_status (dict), clustering_analysis_count,
    cluster_types, timepoints (list, omitted if not time-course).
    When verbose=True, also includes: publication_title, treatment,
    control, light_condition, light_intensity, medium, temperature,
    statistical_test, experimental_context.
    When search_text is provided, detail results include score.
    """
    if summary:
        limit = 0

    conn = _default_conn(conn)
    filter_kwargs = dict(
        organism=organism, treatment_type=treatment_type,
        background_factors=background_factors,
        omics_type=omics_type, publication_doi=publication_doi,
        coculture_partner=coculture_partner, search_text=search_text,
        time_course_only=time_course_only, table_scope=table_scope,
    )

    def _run_summary(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        cypher, params = build_list_experiments_summary(**kw)
        return conn.execute_query(cypher, **params)[0]

    def _run_detail(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        cypher, params = build_list_experiments(
            **kw, verbose=verbose, limit=limit, offset=offset,
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
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    envelope = {
        "total_entries": total_entries,
        "total_matching": raw_summary["total_matching"],
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_treatment_type": _rename_freq(raw_summary["by_treatment_type"], "treatment_type"),
        "by_background_factors": _rename_freq(raw_summary["by_background_factors"], "background_factor"),
        "by_omics_type": _rename_freq(raw_summary["by_omics_type"], "omics_type"),
        "by_publication": _rename_freq(raw_summary["by_publication"], "publication_doi"),
        "by_table_scope": _rename_freq(raw_summary["by_table_scope"], "table_scope"),
        "by_cluster_type": _rename_freq(raw_summary["by_cluster_type"], "cluster_type"),
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
        envelope["offset"] = offset
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

        # Consolidate gene status counts into dict
        sig_up = r.pop("significant_up_count")
        sig_down = r.pop("significant_down_count")
        r["genes_by_status"] = {
            "significant_up": sig_up,
            "significant_down": sig_down,
            "not_significant": r["gene_count"] - sig_up - sig_down,
        }

        # Assemble timepoints from parallel arrays
        tp_count = r.pop("time_point_count", 0)
        tp_labels = r.pop("time_point_labels", [])
        tp_orders = r.pop("time_point_orders", [])
        tp_hours = r.pop("time_point_hours", [])
        tp_totals = r.pop("time_point_totals", [])
        tp_sig_up = r.pop("time_point_significant_up", [])
        tp_sig_down = r.pop("time_point_significant_down", [])

        if r["is_time_course"] and tp_count > 0:
            timepoints = []
            for i in range(tp_count):
                tp_total = tp_totals[i]
                tp_up = tp_sig_up[i]
                tp_down = tp_sig_down[i]
                tp = {
                    "timepoint": tp_labels[i] if tp_labels[i] != "" else None,
                    "timepoint_order": tp_orders[i],
                    "timepoint_hours": tp_hours[i] if tp_hours[i] != -1.0 else None,
                    "gene_count": tp_total,
                    "genes_by_status": {
                        "significant_up": tp_up,
                        "significant_down": tp_down,
                        "not_significant": tp_total - tp_up - tp_down,
                    },
                }
                timepoints.append(tp)
            r["timepoints"] = timepoints
        # Non-time-course: omit timepoints key entirely

        # Gate verbose-only cluster field
        if not verbose:
            r.pop("cluster_count", None)

        processed.append(r)

    envelope["returned"] = len(processed)
    envelope["offset"] = offset
    envelope["truncated"] = envelope["total_matching"] > offset + len(processed)
    envelope["results"] = processed
    return envelope


def search_ontology(
    search_text: str,
    ontology: str,
    summary: bool = False,
    limit: int | None = None,
    offset: int = 0,
    level: int | None = None,
    tree: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Browse ontology terms by text search.

    Returns dict with keys: total_entries, total_matching, score_max,
    score_median, returned, truncated, results.
    Per result: id, name, score, level, tree (sparse), tree_code (sparse).
    """
    if not search_text or not search_text.strip():
        raise ValueError("search_text must not be empty.")
    if ontology not in ONTOLOGY_CONFIG:
        valid = ", ".join(sorted(ONTOLOGY_CONFIG))
        raise ValueError(
            f"Invalid ontology '{ontology}'. Valid: {valid}"
        )
    if summary:
        limit = 0

    conn = _default_conn(conn)
    effective_text = search_text

    # Summary query — always runs
    try:
        sum_cypher, sum_params = build_search_ontology_summary(
            ontology=ontology, search_text=effective_text,
            level=level, tree=tree,
        )
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
    except Neo4jClientError:
        logger.debug("search_ontology: Lucene parse error, retrying with escaped query")
        effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
        sum_cypher, sum_params = build_search_ontology_summary(
            ontology=ontology, search_text=effective_text,
            level=level, tree=tree,
        )
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_entries": raw_summary["total_entries"],
        "total_matching": total_matching,
        "score_max": raw_summary["score_max"],
        "score_median": raw_summary["score_median"],
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    try:
        det_cypher, det_params = build_search_ontology(
            ontology=ontology, search_text=effective_text, limit=limit, offset=offset,
            level=level, tree=tree,
        )
        results = conn.execute_query(det_cypher, **det_params)
    except Neo4jClientError:
        if effective_text == search_text:
            logger.debug("search_ontology detail: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            det_cypher, det_params = build_search_ontology(
                ontology=ontology, search_text=effective_text, limit=limit, offset=offset,
                level=level, tree=tree,
            )
            results = conn.execute_query(det_cypher, **det_params)
        else:
            raise

    # Strip sparse BRITE-only fields when absent
    for r in results:
        if r.get("tree") is None:
            r.pop("tree", None)
            r.pop("tree_code", None)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def search_homolog_groups(
    search_text: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    cyanorak_roles: list[str] | None = None,
    cog_categories: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Search ortholog groups by text (Lucene fulltext).

    Returns dict with keys: total_entries, total_matching, by_source,
    by_level, top_cyanorak_roles, top_cog_categories,
    score_max, score_median, returned, truncated, results.

    cyanorak_roles: filter to groups linked to these Cyanorak role IDs.
    cog_categories: filter to groups linked to these COG category IDs.
    Per result (compact): group_id, group_name, consensus_gene_name,
    consensus_product, source, taxonomic_level, specificity_rank,
    member_count, organism_count, score.
    Per result (verbose): adds description, functional_description,
    genera, has_cross_genus_members.

    summary=True: results=[], summary fields only.
    """
    if not search_text or not search_text.strip():
        raise ValueError("search_text must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Validate enum params
    if source is not None and source not in VALID_OG_SOURCES:
        raise ValueError(
            f"Invalid source '{source}'. Valid: {sorted(VALID_OG_SOURCES)}"
        )
    if taxonomic_level is not None and taxonomic_level not in VALID_TAXONOMIC_LEVELS:
        raise ValueError(
            f"Invalid taxonomic_level '{taxonomic_level}'. "
            f"Valid: {sorted(VALID_TAXONOMIC_LEVELS)}"
        )
    if max_specificity_rank is not None and not (
        0 <= max_specificity_rank <= MAX_SPECIFICITY_RANK
    ):
        raise ValueError(
            f"Invalid max_specificity_rank {max_specificity_rank}. "
            f"Valid: 0-{MAX_SPECIFICITY_RANK}."
        )

    filter_kwargs = dict(
        source=source, taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
        cyanorak_roles=cyanorak_roles, cog_categories=cog_categories,
    )

    effective_text = search_text

    # Summary query — always runs
    try:
        sum_cypher, sum_params = build_search_homolog_groups_summary(
            search_text=effective_text, **filter_kwargs)
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
    except Neo4jClientError:
        logger.debug("search_homolog_groups: Lucene parse error, retrying with escaped query")
        effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
        sum_cypher, sum_params = build_search_homolog_groups_summary(
            search_text=effective_text, **filter_kwargs)
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_entries": raw_summary["total_entries"],
        "total_matching": total_matching,
        "by_source": _rename_freq(raw_summary["by_source"], "source"),
        "by_level": _rename_freq(raw_summary["by_level"], "taxonomic_level"),
        "top_cyanorak_roles": raw_summary["top_cyanorak_roles"],
        "top_cog_categories": raw_summary["top_cog_categories"],
        "score_max": raw_summary["score_max"],
        "score_median": raw_summary["score_median"],
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    try:
        det_cypher, det_params = build_search_homolog_groups(
            search_text=effective_text, **filter_kwargs,
            verbose=verbose, limit=limit, offset=offset)
        results = conn.execute_query(det_cypher, **det_params)
    except Neo4jClientError:
        if effective_text == search_text:
            logger.debug("search_homolog_groups detail: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            det_cypher, det_params = build_search_homolog_groups(
                search_text=effective_text, **filter_kwargs,
                verbose=verbose, limit=limit, offset=offset)
            results = conn.execute_query(det_cypher, **det_params)
        else:
            raise

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def genes_by_homolog_group(
    group_ids: list[str],
    organisms: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Find member genes of ortholog groups.

    Returns dict with keys: total_matching, total_genes,
    total_categories, genes_per_group_max, genes_per_group_median,
    by_organism, top_categories, top_groups,
    not_found_groups, not_matched_groups,
    not_found_organisms, not_matched_organisms,
    returned, truncated, results.
    Per result (compact): locus_tag, gene_name, product,
    organism_name, gene_category, group_id.
    Per result (verbose): adds gene_summary, function_description,
    consensus_product, source.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: if group_ids is empty.
    """
    if not group_ids:
        raise ValueError("group_ids must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Summary query — always runs
    sum_cypher, sum_params = build_genes_by_homolog_group_summary(
        group_ids=group_ids, organisms=organisms,
    )
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    by_group_all = _rename_freq(raw_summary["by_group_raw"], "group_id")
    group_counts = [g["count"] for g in by_group_all]

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_matching": total_matching,
        "total_genes": raw_summary["total_genes"],
        "total_categories": raw_summary["total_categories"],
        "genes_per_group_max": max(group_counts) if group_counts else 0,
        "genes_per_group_median": (
            statistics.median(group_counts) if group_counts else 0
        ),
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "top_categories": _rename_freq(raw_summary["by_category_raw"], "category")[:5],
        "top_groups": by_group_all[:5],
        "not_found_groups": raw_summary["not_found_groups"],
        "not_matched_groups": raw_summary["not_matched_groups"],
    }

    # Diagnostics query — only when organisms filter is active
    if organisms is not None:
        diag_cypher, diag_params = build_genes_by_homolog_group_diagnostics(
            group_ids=group_ids, organisms=organisms,
        )
        raw_diag = conn.execute_query(diag_cypher, **diag_params)[0]
        envelope["not_found_organisms"] = raw_diag["not_found_organisms"]
        envelope["not_matched_organisms"] = raw_diag["not_matched_organisms"]
    else:
        envelope["not_found_organisms"] = []
        envelope["not_matched_organisms"] = []

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_genes_by_homolog_group(
        group_ids=group_ids, organisms=organisms,
        verbose=verbose, limit=limit, offset=offset,
    )
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def genes_by_ontology(
    ontology: str,
    organism: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    tree: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Find genes x ontology-term pairs (TERM2GENE), three input modes.

    Mode 1 (term_ids only): expand DOWN, row term_id = input term.
    Mode 2 (level only): roll UP, row term_id = level-N ancestor.
    Mode 3 (level + term_ids): Mode 2 scoped to provided level-N terms.

    Returns dict with full envelope -- see spec for shape.
    """
    from collections import Counter

    # --- Input validation ---
    if ontology not in ALL_ONTOLOGIES:
        raise ValueError(
            f"Invalid ontology '{ontology}'. Valid: {ALL_ONTOLOGIES}"
        )
    if level is None and not term_ids:
        raise ValueError(
            "At least one of `level` or `term_ids` must be provided."
        )
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
    if min_gene_set_size < 0:
        raise ValueError("min_gene_set_size must be >= 0.")
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError("max_gene_set_size must be >= min_gene_set_size.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Resolve organism to canonical name (fuzzy → exact)
    organism = _validate_organism_inputs(
        organism=organism, locus_tags=None, experiment_ids=None, conn=conn,
    )

    # --- Query V: validate term_ids (only when provided) ---
    not_found: list[str] = []
    wrong_ontology: list[str] = []
    wrong_level: list[str] = []
    ok_term_ids: list[str] | None = None  # None = no validation needed
    if term_ids:
        v_cypher, v_params = build_genes_by_ontology_validate(
            term_ids=term_ids, ontology=ontology, level=level,
        )
        v_rows = conn.execute_query(v_cypher, **v_params)
        for r in v_rows:
            if r["status"] == "not_found":
                not_found.append(r["tid"])
            elif r["status"] == "wrong_ontology":
                wrong_ontology.append(r["tid"])
            elif r["status"] == "wrong_level":
                wrong_level.append(r["tid"])
        ok_term_ids = [r["tid"] for r in v_rows if r["status"] == "ok"]

    # Short-circuit when all term_ids invalid: skip queries A/B/D, fall through
    # to envelope assembly with empty aggregates. _stats and Counter both handle
    # empty inputs gracefully; `if limit == 0:` below skips Query D.
    effective_term_ids = ok_term_ids if term_ids else None
    if term_ids and not effective_term_ids:
        per_term: list[dict] = []
        per_gene: list[dict] = []
        limit = 0  # forces detail to be skipped without re-checking summary flag
    else:
        # --- Query A: per-term aggregate ---
        pt_cypher, pt_params = build_genes_by_ontology_per_term(
            ontology=ontology, organism=organism,
            level=level, term_ids=effective_term_ids,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
            tree=tree,
        )
        per_term = conn.execute_query(pt_cypher, **pt_params)

        # --- Query B: per-gene aggregate ---
        pg_cypher, pg_params = build_genes_by_ontology_per_gene(
            ontology=ontology, organism=organism,
            level=level, term_ids=effective_term_ids,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
            tree=tree,
        )
        per_gene = conn.execute_query(pg_cypher, **pg_params)

    # --- Compose envelope ---
    total_matching = sum(r["n_genes"] for r in per_term)
    total_genes = len(per_gene)
    total_terms = len(per_term)
    n_best_effort_terms = sum(1 for r in per_term if r["best_effort"])

    # by_category from per_gene
    cat_counter = Counter(r["gene_category"] for r in per_gene)
    by_category = [
        {"category": c, "count": n}
        for c, n in cat_counter.most_common()
    ]
    total_categories = len(cat_counter)

    # by_level from per_term (for n_terms, row_count) + per_gene (for n_genes)
    level_terms: dict[int, dict] = {}
    for r in per_term:
        lvl = r["level"]
        e = level_terms.setdefault(
            lvl,
            {"level": lvl, "n_terms": 0, "n_genes": 0, "row_count": 0},
        )
        e["n_terms"] += 1
        e["row_count"] += r["n_genes"]
    # n_genes per level from per_gene.levels_hit
    for r in per_gene:
        for lvl in r["levels_hit"]:
            # Only count levels that have surviving terms in per_term -- a gene
            # that hits a level whose terms were size-filtered out shouldn't
            # contribute to by_level for that level.
            if lvl in level_terms:
                level_terms[lvl]["n_genes"] += 1  # count once per gene per level
    by_level = sorted(level_terms.values(), key=lambda e: e["level"])

    # top_terms: top 5 by n_genes desc, tie-break term_id asc
    top_terms_sorted = sorted(
        per_term, key=lambda r: (-r["n_genes"], r["term_id"])
    )[:5]
    top_terms = [
        {"term_id": r["term_id"], "term_name": r["term_name"], "count": r["n_genes"]}
        for r in top_terms_sorted
    ]

    # Distributions
    genes_per_term_vals = [r["n_genes"] for r in per_term]
    terms_per_gene_vals = [r["n_terms"] for r in per_gene]

    def _stats(vals):
        if not vals:
            return 0, 0.0, 0
        return min(vals), float(statistics.median(vals)), max(vals)

    g_min, g_med, g_max = _stats(genes_per_term_vals)
    t_min, t_med, t_max = _stats(terms_per_gene_vals)

    # filtered_out: ok term_ids not present in per_term output (Modes 1 & 3)
    filtered_out: list[str] = []
    if effective_term_ids:
        emitted_term_ids = {r["term_id"] for r in per_term}
        filtered_out = [
            tid for tid in effective_term_ids if tid not in emitted_term_ids
        ]

    envelope = {
        "ontology": ontology,
        "organism_name": organism,
        "total_matching": total_matching,
        "total_genes": total_genes,
        "total_terms": total_terms,
        "total_categories": total_categories,
        "genes_per_term_min": g_min,
        "genes_per_term_median": g_med,
        "genes_per_term_max": g_max,
        "terms_per_gene_min": t_min,
        "terms_per_gene_median": t_med,
        "terms_per_gene_max": t_max,
        "by_category": by_category,
        "by_level": by_level,
        "top_terms": top_terms,
        "n_best_effort_terms": n_best_effort_terms,
        "not_found": not_found,
        "wrong_ontology": wrong_ontology,
        "wrong_level": wrong_level,
        "filtered_out": filtered_out,
        "offset": offset,
    }

    # --- Query D: detail rows (skipped when summary=True) ---
    if limit == 0:
        envelope["returned"] = 0
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_genes_by_ontology_detail(
        ontology=ontology, organism=organism,
        level=level, term_ids=effective_term_ids,
        min_gene_set_size=min_gene_set_size,
        max_gene_set_size=max_gene_set_size,
        verbose=verbose, limit=limit, offset=offset,
        tree=tree,
    )
    results = conn.execute_query(det_cypher, **det_params)

    # Strip sparse level_is_best_effort=False from rows (verbose only)
    if verbose:
        for r in results:
            if r.get("level_is_best_effort") is False:
                r.pop("level_is_best_effort", None)

    # Strip sparse tree/tree_code for non-BRITE results
    for r in results:
        if r.get("tree") is None:
            r.pop("tree", None)
            r.pop("tree_code", None)

    envelope["returned"] = len(results)
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def gene_ontology_terms(
    locus_tags: list[str],
    organism: str,
    ontology: str | None = None,
    mode: str = "leaf",
    level: int | None = None,
    tree: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get ontology annotations for genes. One row per gene × term.

    Returns dict with keys: total_matching, total_genes, total_terms,
    by_ontology, by_term, terms_per_gene_min, terms_per_gene_max,
    terms_per_gene_median, returned, truncated, not_found, no_terms,
    results.
    Per result: locus_tag, term_id, term_name, level.
    Verbose adds: organism_name.
    All-ontology queries add: ontology_type.
    BRITE results include sparse tree/tree_code fields.

    Raises ValueError if ontology is invalid or locus_tags is empty.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    if ontology is not None and ontology not in ONTOLOGY_CONFIG:
        raise ValueError(
            f"Invalid ontology '{ontology}'. "
            f"Valid: {sorted(ONTOLOGY_CONFIG)}"
        )
    if mode not in ("leaf", "rollup"):
        raise ValueError(f"mode must be 'leaf' or 'rollup', got '{mode}'")
    if mode == "rollup" and level is None:
        raise ValueError("level is required when mode='rollup'")
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Resolve organism
    organism_name = _validate_organism_inputs(
        organism=organism, locus_tags=None, experiment_ids=None, conn=conn,
    )

    # Step 1: gene existence check
    exist_cypher, exist_params = build_gene_existence_check(locus_tags=locus_tags)
    exist_rows = conn.execute_query(exist_cypher, **exist_params)
    not_found = [r["lt"] for r in exist_rows if not r["found"]]
    found_tags = [r["lt"] for r in exist_rows if r["found"]]

    # Determine which ontologies to query
    ontologies = [ontology] if ontology else sorted(ONTOLOGY_CONFIG)

    # Step 2: summary queries — chunked to avoid 1.4 GiB Neo4j transaction cap
    by_ontology: list[dict] = []
    all_by_term: list[dict] = []
    gene_term_counts: dict[str, int] = {lt: 0 for lt in found_tags}

    if found_tags:
        for ont in ontologies:
            merged_gene_count = 0
            merged_term_count = 0
            merged_by_term: dict[str, dict] = {}
            for chunk in _chunk_locus_tags(found_tags):
                sum_cypher, sum_params = build_gene_ontology_terms_summary(
                    locus_tags=chunk, ontology=ont,
                    organism_name=organism_name,
                    mode=mode, level=level, tree=tree,
                )
                rows = conn.execute_query(sum_cypher, **sum_params)
                if not rows or rows[0]["gene_count"] == 0:
                    continue
                row = rows[0]
                merged_gene_count += row["gene_count"]
                merged_term_count += row["term_count"]
                for bt in row["by_term"]:
                    key = bt["term_id"]
                    if key not in merged_by_term:
                        entry: dict = {
                            "term_id": key, "term_name": bt["term_name"],
                            "level": bt.get("level"),
                            "count": 0,
                        }
                        # Include sparse BRITE fields
                        if bt.get("tree") is not None:
                            entry["tree"] = bt["tree"]
                        if bt.get("tree_code") is not None:
                            entry["tree_code"] = bt["tree_code"]
                        merged_by_term[key] = entry
                    merged_by_term[key]["count"] += bt["count"]
                for gtc in row["gene_term_counts"]:
                    gene_term_counts[gtc["locus_tag"]] = (
                        gene_term_counts.get(gtc["locus_tag"], 0)
                        + gtc["term_count"]
                    )
            if merged_gene_count == 0:
                continue
            by_ontology.append({
                "ontology_type": ont,
                "term_count": merged_term_count,
                "gene_count": merged_gene_count,
            })
            for bt in merged_by_term.values():
                all_by_term.append({**bt, "ontology_type": ont})

    total_matching = sum(o["term_count"] for o in by_ontology)

    # Step 3: detail queries — skip when limit=0 (summary only)
    if limit == 0:
        results: list[dict] = []
    else:
        all_detail_rows: list[dict] = []
        if found_tags:
            for ont in ontologies:
                for chunk in _chunk_locus_tags(found_tags):
                    det_cypher, det_params = build_gene_ontology_terms(
                        locus_tags=chunk, ontology=ont,
                        organism_name=organism_name,
                        mode=mode, level=level, tree=tree,
                        verbose=verbose, limit=None,
                    )
                    rows = conn.execute_query(det_cypher, **det_params)
                    # Strip sparse tree/tree_code when None
                    for r in rows:
                        if r.get("tree") is None:
                            r.pop("tree", None)
                        if r.get("tree_code") is None:
                            r.pop("tree_code", None)
                    if ontology is None:
                        for r in rows:
                            r["ontology_type"] = ont
                    all_detail_rows.extend(rows)

        all_detail_rows.sort(key=lambda r: (r["locus_tag"], r["term_id"]))
        # Apply offset then limit on the merged result set
        sliced = all_detail_rows[offset:]
        if limit is not None:
            results = sliced[:limit]
        else:
            results = sliced

    # Sort breakdowns
    by_ontology.sort(key=lambda x: x["term_count"], reverse=True)
    all_by_term.sort(key=lambda x: x["count"], reverse=True)

    # Compute totals
    no_terms = [lt for lt in found_tags if gene_term_counts.get(lt, 0) == 0]
    genes_with_terms = [lt for lt in found_tags
                        if gene_term_counts.get(lt, 0) > 0]
    total_genes = len(genes_with_terms)
    total_terms = len({bt["term_id"] for bt in all_by_term})

    # Per-gene distribution (only genes with terms)
    counts = [gene_term_counts[lt] for lt in genes_with_terms]
    if counts:
        terms_per_gene_min = min(counts)
        terms_per_gene_max = max(counts)
        terms_per_gene_median = statistics.median(counts)
    else:
        terms_per_gene_min = 0
        terms_per_gene_max = 0
        terms_per_gene_median = 0.0

    return {
        "total_matching": total_matching,
        "total_genes": total_genes,
        "total_terms": total_terms,
        "by_ontology": by_ontology,
        "by_term": all_by_term,
        "terms_per_gene_min": terms_per_gene_min,
        "terms_per_gene_max": terms_per_gene_max,
        "terms_per_gene_median": terms_per_gene_median,
        "returned": len(results),
        "offset": offset,
        "truncated": total_matching > offset + len(results),
        "not_found": not_found,
        "no_terms": no_terms,
        "results": results,
    }


def run_cypher(
    query: str,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Execute a raw Cypher query (read-only).

    Write operations are blocked via keyword detection.
    Syntax is validated via CyVer before execution; schema and property
    warnings are included in the returned dict.

    Returns dict with keys: returned, truncated, warnings, results.

    Raises ValueError if the query contains write keywords or has a syntax error.

    Note: SyntaxValidator returns False for parameterized queries ($param) due to
    a ParameterNotProvided notification — not a real syntax error. run_cypher users
    should write literal values, so this is not an issue in practice.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty.")
    conn = _default_conn(conn)

    # 1. Write blocking
    if _WRITE_KEYWORDS.search(query):
        raise ValueError("Write operations are not allowed. This interface is read-only.")

    # 2. Syntax validation (hard block)
    valid, meta = SyntaxValidator(conn.driver).validate(query)
    if not valid:
        msg = meta[0]["description"] if meta else "Syntax error"
        raise ValueError(f"Syntax error: {msg}")

    # 3–4. Schema + property warnings (soft); deduplicate preserving order
    raw_warnings: list[str] = []
    _, schema_meta = SchemaValidator(conn.driver).validate(query)
    raw_warnings.extend(m["description"] for m in schema_meta)
    _, prop_meta = PropertiesValidator(conn.driver).validate(query)
    raw_warnings.extend(m["description"] for m in prop_meta)
    warnings = list(dict.fromkeys(raw_warnings))

    # 5. Limit injection + semicolon strip (only when limit provided)
    if limit is not None and not re.search(r"\bLIMIT\b", query, re.IGNORECASE):
        query = query.rstrip().rstrip(";")
        query += f"\nLIMIT {limit}"

    # 6. Execute
    results = conn.execute_query(query)
    return {
        "returned": len(results),
        "truncated": len(results) == limit if limit is not None else False,
        "warnings": warnings,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Expression: differential_expression_by_gene
# ---------------------------------------------------------------------------

_EXPRESSION_STATUS_KEYS = ("significant_up", "significant_down", "not_significant")
_VALID_DIRECTIONS = {"up", "down"}


def _apoc_freq_to_dict(freq_list: list[dict]) -> dict[str, int]:
    """Convert apoc.coll.frequencies [{item, count}] to {item: count} dict.

    Fills missing expression_status keys with 0.
    """
    d = {f["item"]: f["count"] for f in freq_list}
    for key in _EXPRESSION_STATUS_KEYS:
        d.setdefault(key, 0)
    return d


def _apoc_freq_to_treatment_dict(freq_list: list[dict]) -> dict[str, int]:
    """Convert apoc.coll.frequencies [{item, count}] to {item: count} dict.

    For treatment_type — no default keys needed.
    """
    return {f["item"]: f["count"] for f in freq_list}


def _validate_organism_inputs(
    organism: str | None,
    locus_tags: list[str] | None,
    experiment_ids: list[str] | None,
    conn: "GraphConnection",
) -> str:
    """Pre-validate that all inputs refer to a single organism.

    Returns the resolved organism_name string.
    Raises ValueError on validation failure.
    """
    resolved: dict[str, list[str]] = {}

    if organism:
        cypher, params = build_resolve_organism_for_organism(organism=organism)
        orgs = conn.execute_query(cypher, **params)[0]["organisms"]
        if len(orgs) == 0:
            raise ValueError(
                f"no organism matching '{organism}' found. "
                "Use list_organisms to see valid organism names."
            )
        if len(orgs) > 1:
            names = ", ".join(sorted(orgs))
            raise ValueError(
                f"organism '{organism}' matches multiple organisms: {names}"
                " — be more specific"
            )
        resolved["organism"] = orgs

    if locus_tags:
        cypher, params = build_resolve_organism_for_locus_tags(
            locus_tags=locus_tags
        )
        orgs = conn.execute_query(cypher, **params)[0]["organisms"]
        if len(orgs) > 1:
            names = ", ".join(sorted(orgs))
            raise ValueError(
                f"locus_tags span multiple organisms: {names}"
                " — call once per organism"
            )
        if orgs:
            resolved["locus_tags"] = orgs

    if experiment_ids:
        cypher, params = build_resolve_organism_for_experiments(
            experiment_ids=experiment_ids
        )
        orgs = conn.execute_query(cypher, **params)[0]["organisms"]
        if len(orgs) > 1:
            names = ", ".join(sorted(orgs))
            raise ValueError(
                f"experiment_ids span multiple organisms: {names}"
                " — call once per organism"
            )
        if orgs:
            resolved["experiment_ids"] = orgs

    # Cross-validate: all resolved sets must agree
    all_orgs = list(resolved.values())
    if not all_orgs:
        # No organism resolved from any input — shouldn't happen if at least
        # one input is provided, but handle gracefully
        raise ValueError(
            "at least one of organism, locus_tags, or experiment_ids is required. "
            "Use list_organisms for organisms, resolve_gene for locus_tags, "
            "or list_experiments for experiment_ids."
        )

    first = all_orgs[0][0]
    for source, orgs in resolved.items():
        if orgs[0] != first:
            # Find which sources disagree
            if "organism" in resolved and source != "organism":
                raise ValueError(
                    f"organism '{organism}' does not match"
                    f" {source} organism '{orgs[0]}'"
                )
            if source == "experiment_ids" and "locus_tags" in resolved:
                raise ValueError(
                    f"locus_tags are {resolved['locus_tags'][0]} genes"
                    f" but experiment_ids cover {orgs[0]}"
                    " — organisms must match"
                )

    return first


def differential_expression_by_gene(
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Query gene-centric differential expression data.

    Returns dict with summary fields + results list. Results are long form:
    one row per gene x experiment x timepoint, all context inlined.

    Raises:
        ValueError: if no filter provided, if inputs span multiple organisms,
            if organisms don't match each other, or if organism fuzzy match
            is ambiguous.

    Returns:
        dict with keys: organism_name, matching_genes, total_matching,
        rows_by_status, median_abs_log2fc, max_abs_log2fc, experiment_count,
        rows_by_treatment_type, rows_by_background_factors, by_table_scope,
        top_categories, experiments,
        returned, truncated, not_found, no_expression, results.
    """
    conn = _default_conn(conn)

    # Validate direction
    if direction is not None and direction not in _VALID_DIRECTIONS:
        raise ValueError(
            f"Invalid direction '{direction}'. Valid: {sorted(_VALID_DIRECTIONS)}"
        )

    # Require at least one filter
    if organism is None and locus_tags is None and experiment_ids is None:
        raise ValueError(
            "at least one of organism, locus_tags, or experiment_ids is required. "
            "Use list_organisms for organisms, resolve_gene for locus_tags, "
            "or list_experiments for experiment_ids."
        )

    if summary:
        limit = 0

    # Common filter kwargs for all builders
    filter_kwargs = dict(
        organism=organism,
        locus_tags=locus_tags,
        experiment_ids=experiment_ids,
        direction=direction,
        significant_only=significant_only,
    )

    # Pre-validate single organism
    organism_name = _validate_organism_inputs(
        organism, locus_tags, experiment_ids, conn
    )

    # --- Summary query 1: global stats ---
    global_cypher, global_params = (
        build_differential_expression_by_gene_summary_global(**filter_kwargs)
    )
    global_raw = conn.execute_query(global_cypher, **global_params)[0]

    total_matching = global_raw["total_matching"]
    matching_genes = global_raw["matching_genes"]
    rows_by_status = _apoc_freq_to_dict(global_raw["rows_by_status"])
    rows_by_treatment_type = _apoc_freq_to_treatment_dict(
        global_raw["rows_by_treatment_type"]
    )
    rows_by_background_factors = _apoc_freq_to_treatment_dict(
        global_raw["rows_by_background_factors"]
    )
    by_table_scope = _apoc_freq_to_treatment_dict(
        global_raw["by_table_scope"]
    )

    # --- Summary query 2: per-experiment with nested timepoints ---
    exp_cypher, exp_params = (
        build_differential_expression_by_gene_summary_by_experiment(
            **filter_kwargs
        )
    )
    exp_raw = conn.execute_query(exp_cypher, **exp_params)

    experiments: list[dict] = []
    if exp_raw:
        for exp in exp_raw[0]["experiments"]:
            e = dict(exp)
            e["rows_by_status"] = _apoc_freq_to_dict(e["rows_by_status"])

            # Handle timepoints
            if e.get("is_time_course") == "false":
                e["timepoints"] = None
            elif e.get("timepoints"):
                tps = []
                for tp in e["timepoints"]:
                    tp_dict = dict(tp)
                    tp_dict["rows_by_status"] = _apoc_freq_to_dict(
                        tp_dict["rows_by_status"]
                    )
                    tps.append(tp_dict)
                # Sort by timepoint_order
                tps.sort(key=lambda t: t["timepoint_order"])
                e["timepoints"] = tps

            experiments.append(e)

    # Sort experiments by total significant rows DESC
    experiments.sort(
        key=lambda e: (
            e["rows_by_status"]["significant_up"]
            + e["rows_by_status"]["significant_down"]
        ),
        reverse=True,
    )

    # --- Summary query 3: categories + batch diagnostics ---
    diag_cypher, diag_params = (
        build_differential_expression_by_gene_summary_diagnostics(
            **filter_kwargs
        )
    )
    diag_raw = conn.execute_query(diag_cypher, **diag_params)[0]

    top_categories = diag_raw["top_categories"]
    not_found = diag_raw["not_found"]
    no_expression = diag_raw["no_expression"]

    # --- Detail query (skip when limit=0) ---
    if limit == 0:
        results = []
    else:
        det_cypher, det_params = build_differential_expression_by_gene(
            **filter_kwargs, verbose=verbose, limit=limit, offset=offset,
        )
        results = conn.execute_query(det_cypher, **det_params)

    returned = len(results)
    envelope = {
        "organism_name": organism_name,
        "matching_genes": matching_genes,
        "total_matching": total_matching,
        "rows_by_status": rows_by_status,
        "median_abs_log2fc": global_raw["median_abs_log2fc"],
        "max_abs_log2fc": global_raw["max_abs_log2fc"],
        "experiment_count": len(experiments),
        "rows_by_treatment_type": rows_by_treatment_type,
        "rows_by_background_factors": rows_by_background_factors,
        "by_table_scope": by_table_scope,
        "top_categories": top_categories,
        "experiments": experiments,
        "not_found": not_found,
        "no_expression": no_expression,
        "returned": returned,
        "offset": offset,
        "truncated": total_matching > offset + returned,
        "results": results,
    }
    return envelope


def differential_expression_by_ortholog(
    group_ids: list[str],
    organisms: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Differential expression framed by ortholog groups.

    Cross-organism by design. Results at group x experiment x timepoint
    granularity showing how many group members respond (gene counts,
    not individual genes).

    Returns dict with keys: total_matching, matching_genes, matching_groups,
    experiment_count, median_abs_log2fc, max_abs_log2fc,
    by_organism, rows_by_status, rows_by_treatment_type,
    rows_by_background_factors, by_table_scope,
    top_groups, top_experiments,
    not_found_groups, not_matched_groups,
    not_found_organisms, not_matched_organisms,
    not_found_experiments, not_matched_experiments,
    returned, truncated, results.
    Per result (compact): group_id, consensus_gene_name, consensus_product,
    experiment_id, treatment_type, organism_name, coculture_partner,
    timepoint, timepoint_hours, timepoint_order,
    genes_with_expression, total_genes,
    significant_up, significant_down, not_significant.
    Per result (verbose): adds experiment_name, treatment, omics_type,
    table_scope, table_scope_detail.

    Raises:
        ValueError: if group_ids is empty or direction is invalid.
    """
    if not group_ids:
        raise ValueError("group_ids must not be empty.")

    if direction is not None and direction not in _VALID_DIRECTIONS:
        raise ValueError(
            f"Invalid direction '{direction}'. Valid: {sorted(_VALID_DIRECTIONS)}"
        )

    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Common filter kwargs for all builders
    filter_kwargs = dict(
        organisms=organisms,
        experiment_ids=experiment_ids,
        direction=direction,
        significant_only=significant_only,
    )

    # --- Q1a: group existence check ---
    check_cypher, check_params = (
        build_differential_expression_by_ortholog_group_check(
            group_ids=group_ids,
        )
    )
    not_found_groups = conn.execute_query(
        check_cypher, **check_params
    )[0]["not_found"]
    found_group_ids = [
        gid for gid in group_ids if gid not in not_found_groups
    ]

    # --- Q1b: summary_global (for found groups only) ---
    _empty_global = {
        "total_matching": 0, "matching_genes": 0,
        "matching_groups": 0, "experiment_count": 0,
        "by_organism": [], "rows_by_status": [],
        "rows_by_treatment_type": [], "rows_by_background_factors": [],
        "by_table_scope": [],
        "sig_log2fcs": [], "matched_group_ids": [],
    }
    if found_group_ids:
        global_cypher, global_params = (
            build_differential_expression_by_ortholog_summary_global(
                group_ids=found_group_ids, **filter_kwargs,
            )
        )
        global_rows = conn.execute_query(global_cypher, **global_params)
        global_raw = global_rows[0] if global_rows else _empty_global
        not_matched_groups = [
            gid for gid in found_group_ids
            if gid not in global_raw["matched_group_ids"]
        ]
    else:
        global_raw = _empty_global
        not_matched_groups = []

    rows_by_status = _apoc_freq_to_dict(global_raw["rows_by_status"])
    rows_by_treatment_type = _apoc_freq_to_treatment_dict(
        global_raw["rows_by_treatment_type"]
    )
    rows_by_background_factors = _apoc_freq_to_treatment_dict(
        global_raw["rows_by_background_factors"]
    )
    by_table_scope = _apoc_freq_to_treatment_dict(
        global_raw["by_table_scope"]
    )

    sig_log2fcs = global_raw.get("sig_log2fcs") or []
    median_abs_log2fc = statistics.median(sig_log2fcs) if sig_log2fcs else None
    max_abs_log2fc = max(sig_log2fcs) if sig_log2fcs else None

    # --- Q2: top_groups (always) ---
    tg_cypher, tg_params = build_differential_expression_by_ortholog_top_groups(
        group_ids=group_ids, **filter_kwargs,
    )
    top_groups_raw = conn.execute_query(tg_cypher, **tg_params)

    # --- Q3: top_experiments (always) ---
    te_cypher, te_params = (
        build_differential_expression_by_ortholog_top_experiments(
            group_ids=group_ids, **filter_kwargs,
        )
    )
    top_exp_raw = conn.execute_query(te_cypher, **te_params)

    # --- Q4: results (skip when limit=0 / summary mode) ---
    if limit == 0:
        results = []
    else:
        res_cypher, res_params = build_differential_expression_by_ortholog_results(
            group_ids=group_ids, **filter_kwargs, verbose=verbose, limit=limit, offset=offset,
        )
        results = conn.execute_query(res_cypher, **res_params)

    # --- Q5: membership_counts (always) ---
    mc_cypher, mc_params = (
        build_differential_expression_by_ortholog_membership_counts(
            group_ids=group_ids, organisms=organisms,
        )
    )
    mc_rows = conn.execute_query(mc_cypher, **mc_params)
    mc_lookup = {
        (r["group_id"], r["organism_name"]): r["total_genes"]
        for r in mc_rows
    }
    for r in results:
        key = (r["group_id"], r["organism_name"])
        r["total_genes"] = mc_lookup.get(key, 0)

    # --- Q6: diagnostics (conditional) ---
    if organisms is not None or experiment_ids is not None:
        diag_queries = build_differential_expression_by_ortholog_diagnostics(
            group_ids=group_ids, organisms=organisms,
            experiment_ids=experiment_ids,
            direction=direction, significant_only=significant_only,
        )
        not_found_organisms = []
        not_matched_organisms = []
        not_found_experiments = []
        not_matched_experiments = []
        if diag_queries:
            for diag_cypher, diag_params in diag_queries:
                diag_row = conn.execute_query(diag_cypher, **diag_params)[0]
                if "not_found_organisms" in diag_row:
                    not_found_organisms = diag_row["not_found_organisms"]
                    not_matched_organisms = diag_row["not_matched_organisms"]
                if "not_found_experiments" in diag_row:
                    not_found_experiments = diag_row["not_found_experiments"]
                    not_matched_experiments = diag_row["not_matched_experiments"]
    else:
        not_found_organisms = []
        not_matched_organisms = []
        not_found_experiments = []
        not_matched_experiments = []

    # Use same _rename_freq pattern as genes_by_homolog_group
    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    by_organism = _rename_freq(global_raw["by_organism"], "organism_name")

    envelope = {
        "total_matching": global_raw["total_matching"],
        "matching_genes": global_raw["matching_genes"],
        "matching_groups": global_raw["matching_groups"],
        "experiment_count": global_raw["experiment_count"],
        "median_abs_log2fc": median_abs_log2fc,
        "max_abs_log2fc": max_abs_log2fc,
        "by_organism": by_organism,
        "rows_by_status": rows_by_status,
        "rows_by_treatment_type": rows_by_treatment_type,
        "rows_by_background_factors": rows_by_background_factors,
        "by_table_scope": by_table_scope,
        "top_groups": (
            top_groups_raw[0]["top_groups"] if top_groups_raw else []
        ),
        "top_experiments": (
            top_exp_raw[0]["top_experiments"] if top_exp_raw else []
        ),
        "not_found_groups": not_found_groups,
        "not_matched_groups": not_matched_groups,
        "not_found_organisms": not_found_organisms,
        "not_matched_organisms": not_matched_organisms,
        "not_found_experiments": not_found_experiments,
        "not_matched_experiments": not_matched_experiments,
        "returned": len(results),
        "offset": offset,
        "truncated": global_raw["total_matching"] > offset + len(results),
        "results": results,
    }
    return envelope


_FULL_COVERAGE_SCOPES = {"significant_only", "significant_any_timepoint"}


def gene_response_profile(
    locus_tags: list[str],
    organism: str | None = None,
    treatment_types: list[str] | None = None,
    background_factors: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    group_by: str = "treatment_type",
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Cross-experiment gene-level response profile.

    Returns one result per gene summarizing its expression response
    across all experiments, grouped by treatment_type or experiment.

    Raises:
        ValueError: if locus_tags is empty, group_by is invalid,
            or organism validation fails.

    Returns:
        dict with keys: organism_name, genes_queried, genes_with_response,
        not_found, no_expression, returned, offset, truncated, results.
        Each result has: locus_tag, gene_name, product, gene_category,
        groups_responded, groups_not_responded, groups_tested_not_responded,
        groups_not_known, response_summary.
        groups_tested_not_responded: groups where the gene has no expression
        edges but all experiments in the group have full-coverage scopes
        (significant_only or significant_any_timepoint), implying the gene
        was measured but did not respond significantly.
    """
    if not locus_tags:
        raise ValueError(
            "locus_tags must not be empty. "
            "Use resolve_gene or gene_overview to find locus_tags."
        )
    if group_by not in ("treatment_type", "experiment"):
        raise ValueError(
            f"group_by must be 'treatment_type' or 'experiment', got '{group_by}'"
        )

    conn = _default_conn(conn)

    # Resolve organism upfront — validates single-organism constraint
    organism_name = _validate_organism_inputs(
        organism=organism,
        locus_tags=locus_tags,
        experiment_ids=experiment_ids,
        conn=conn,
    )

    # Q1: Envelope — gene existence, expression flags, group totals
    env_cypher, env_params = build_gene_response_profile_envelope(
        locus_tags=locus_tags,
        organism_name=organism_name,
        treatment_types=treatment_types,
        background_factors=background_factors,
        experiment_ids=experiment_ids,
        group_by=group_by,
    )
    env_row = conn.execute_query(env_cypher, **env_params)[0]

    found_genes = env_row["found_genes"]
    has_expression = set(env_row["has_expression"])
    has_significant = set(env_row["has_significant"])
    group_totals = {
        gt["group_key"]: {
            "experiments": gt["experiments"],
            "timepoints": gt["timepoints"],
            "table_scopes": gt.get("table_scopes", []),
        }
        for gt in env_row["group_totals"]
        if gt["group_key"] is not None
    }

    not_found = [lt for lt in locus_tags if lt not in found_genes]
    no_expression = [lt for lt in found_genes if lt not in has_expression]
    genes_with_response = len(has_significant)

    # Q2: Aggregation — per gene x group detail (paginated)
    genes_with_expr = [lt for lt in found_genes if lt in has_expression]
    if genes_with_expr:
        agg_cypher, agg_params = build_gene_response_profile(
            locus_tags=genes_with_expr,
            organism_name=organism_name,
            treatment_types=treatment_types,
            background_factors=background_factors,
            experiment_ids=experiment_ids,
            group_by=group_by,
            limit=limit,
            offset=offset,
        )
        agg_rows = conn.execute_query(agg_cypher, **agg_params)
    else:
        agg_rows = []

    # Pivot flat rows into per-gene nested structure
    genes_dict: dict[str, dict] = {}
    for row in agg_rows:
        lt = row["locus_tag"]
        if lt not in genes_dict:
            genes_dict[lt] = {
                "locus_tag": lt,
                "gene_name": row["gene_name"],
                "product": row["product"],
                "gene_category": row["gene_category"],
                "response_summary": {},
            }
        group_key = row["group_key"]
        totals = group_totals.get(group_key, {"experiments": 0, "timepoints": 0})

        entry: dict = {
            "experiments_total": totals["experiments"],
            "experiments_tested": row["experiments_tested"],
            "experiments_up": row["experiments_up"],
            "experiments_down": row["experiments_down"],
            "timepoints_total": totals["timepoints"],
            "timepoints_tested": row["timepoints_tested"],
            "timepoints_up": row["timepoints_up"],
            "timepoints_down": row["timepoints_down"],
        }

        # Directional rank/log2fc — only when experiments in that direction
        rank_ups = [r for r in row["rank_ups"] if r is not None]
        if rank_ups:
            entry["up_best_rank"] = min(rank_ups)
            entry["up_median_rank"] = statistics.median(rank_ups)
            entry["up_max_log2fc"] = max(row["log2fcs_up"])

        rank_downs = [r for r in row["rank_downs"] if r is not None]
        if rank_downs:
            entry["down_best_rank"] = min(rank_downs)
            entry["down_median_rank"] = statistics.median(rank_downs)
            entry["down_max_log2fc"] = min(row["log2fcs_down"])

        genes_dict[lt]["response_summary"][group_key] = entry

    # Build triage lists per gene
    results = []
    for gene in genes_dict.values():
        rs = gene["response_summary"]
        gene["groups_responded"] = [
            gk for gk, v in rs.items()
            if v["experiments_up"] > 0 or v["experiments_down"] > 0
        ]
        gene["groups_not_responded"] = [
            gk for gk, v in rs.items()
            if v["experiments_up"] == 0 and v["experiments_down"] == 0
        ]
        missing_groups = [gk for gk in group_totals if gk not in rs]
        gene["groups_tested_not_responded"] = [
            gk for gk in missing_groups
            if set(group_totals[gk]["table_scopes"]) <= _FULL_COVERAGE_SCOPES
        ]
        gene["groups_not_known"] = [
            gk for gk in missing_groups
            if gk not in gene["groups_tested_not_responded"]
        ]
        results.append(gene)

    # Determine truncation
    truncated = (
        len(results) + offset < len(genes_with_expr)
        if limit is not None
        else False
    )

    return {
        "organism_name": organism_name,
        "genes_queried": len(locus_tags),
        "genes_with_response": genes_with_response,
        "not_found": not_found,
        "no_expression": no_expression,
        "returned": len(results),
        "offset": offset,
        "truncated": truncated,
        "results": results,
    }


def list_clustering_analyses(
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    omics_type: str | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    analysis_ids: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Browse, search, and filter clustering analyses.

    Returns dict with keys: total_entries, total_matching,
    by_organism, by_cluster_type, by_treatment_type, by_background_factors,
    by_omics_type, returned, offset, truncated, results.
    When search_text provided: adds score_max, score_median.
    Per result (compact): analysis_id, name, organism_name, cluster_method,
    cluster_type, cluster_count, total_gene_count, treatment_type,
    background_factors, omics_type, experiment_ids, clusters, score (when searching).
    Per result (verbose): adds treatment, light_condition, experimental_context.

    summary=True: results=[], summary fields only.
    """
    if search_text is not None and not search_text.strip():
        raise ValueError("search_text must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    filter_kwargs = dict(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, background_factors=background_factors,
        omics_type=omics_type, publication_doi=publication_doi,
        experiment_ids=experiment_ids, analysis_ids=analysis_ids,
    )

    effective_text = search_text

    # Summary query — always runs
    try:
        sum_cypher, sum_params = build_list_clustering_analyses_summary(
            search_text=effective_text, **filter_kwargs)
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
    except Neo4jClientError:
        if search_text is not None:
            logger.debug("list_clustering_analyses: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            sum_cypher, sum_params = build_list_clustering_analyses_summary(
                search_text=effective_text, **filter_kwargs)
            raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
        else:
            raise

    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_entries": raw_summary["total_entries"],
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_cluster_type": _rename_freq(
            raw_summary["by_cluster_type"], "cluster_type"),
        "by_treatment_type": _rename_freq(
            raw_summary["by_treatment_type"], "treatment_type"),
        "by_background_factors": _rename_freq(
            raw_summary["by_background_factors"], "background_factor"),
        "by_omics_type": _rename_freq(raw_summary["by_omics_type"], "omics_type"),
    }

    if search_text is not None:
        envelope["score_max"] = raw_summary.get("score_max")
        envelope["score_median"] = raw_summary.get("score_median")
    else:
        envelope["score_max"] = None
        envelope["score_median"] = None

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    try:
        det_cypher, det_params = build_list_clustering_analyses(
            search_text=effective_text, **filter_kwargs,
            verbose=verbose, limit=limit, offset=offset)
        results = conn.execute_query(det_cypher, **det_params)
    except Neo4jClientError:
        if search_text is not None and effective_text == search_text:
            logger.debug("list_clustering_analyses detail: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            det_cypher, det_params = build_list_clustering_analyses(
                search_text=effective_text, **filter_kwargs,
                verbose=verbose, limit=limit, offset=offset)
            results = conn.execute_query(det_cypher, **det_params)
        else:
            raise

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def gene_clusters_by_gene(
    locus_tags: list[str],
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    analysis_ids: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Gene-centric cluster lookup. Single organism enforced.

    Returns dict with keys: total_matching, total_clusters,
    genes_with_clusters, genes_without_clusters,
    not_found, not_matched,
    by_cluster_type, by_treatment_type, by_background_factors, by_analysis,
    returned, offset, truncated, results.
    Per result (compact): locus_tag, gene_name, cluster_id, cluster_name,
    cluster_type, membership_score, analysis_id, analysis_name,
    treatment_type, background_factors.
    Per result (verbose): adds cluster_method, member_count,
    cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern, treatment, light_condition,
    experimental_context, p_value.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: if locus_tags is empty or spans multiple organisms.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Single-organism enforcement
    _validate_organism_inputs(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=None, conn=conn,
    )

    filter_kwargs = dict(
        cluster_type=cluster_type, treatment_type=treatment_type,
        background_factors=background_factors,
        publication_doi=publication_doi,
        analysis_ids=analysis_ids,
    )

    # Summary query — always runs
    sum_cypher, sum_params = build_gene_clusters_by_gene_summary(
        locus_tags=locus_tags, **filter_kwargs)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_matching": total_matching,
        "total_clusters": raw_summary["total_clusters"],
        "genes_with_clusters": raw_summary["genes_with_clusters"],
        "genes_without_clusters": raw_summary["genes_without_clusters"],
        "not_found": raw_summary["not_found"],
        "not_matched": raw_summary["not_matched"],
        "by_cluster_type": _rename_freq(
            raw_summary["by_cluster_type"], "cluster_type"),
        "by_treatment_type": _rename_freq(
            raw_summary["by_treatment_type"], "treatment_type"),
        "by_background_factors": _rename_freq(
            raw_summary["by_background_factors"], "background_factor"),
        "by_analysis": _rename_freq(
            raw_summary["by_analysis"], "analysis_id"),
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_gene_clusters_by_gene(
        locus_tags=locus_tags, **filter_kwargs,
        verbose=verbose, limit=limit, offset=offset)
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


def genes_in_cluster(
    cluster_ids: list[str] | None = None,
    analysis_id: str | None = None,
    organism: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Cluster IDs or analysis ID → member genes.

    Returns dict with keys: total_matching, by_organism, by_cluster,
    top_categories, genes_per_cluster_max, genes_per_cluster_median,
    not_found_clusters, not_matched_clusters, not_matched_organism,
    returned, offset, truncated, results.
    When analysis_id: also returns analysis_name.
    Per result (compact): locus_tag, gene_name, product, gene_category,
    organism_name, cluster_id, cluster_name, membership_score.
    Per result (verbose): adds gene_function_description, gene_summary,
    p_value, cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: if neither or both of cluster_ids and analysis_id provided.
    """
    if cluster_ids is not None and analysis_id is not None:
        raise ValueError("Provide cluster_ids or analysis_id, not both.")
    if cluster_ids is None and analysis_id is None:
        raise ValueError("Must provide cluster_ids or analysis_id.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Summary query — always runs
    sum_cypher, sum_params = build_genes_in_cluster_summary(
        cluster_ids=cluster_ids, analysis_id=analysis_id, organism=organism)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    by_cluster = raw_summary["by_cluster"]
    cluster_counts = [c["count"] for c in by_cluster]

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_cluster": by_cluster,
        "top_categories": _rename_freq(
            raw_summary["by_category_raw"], "category")[:5],
        "genes_per_cluster_max": max(cluster_counts) if cluster_counts else 0,
        "genes_per_cluster_median": (
            statistics.median(cluster_counts) if cluster_counts else 0
        ),
        "not_found_clusters": raw_summary["not_found_clusters"],
        "not_matched_clusters": raw_summary["not_matched_clusters"],
    }

    envelope["analysis_name"] = (
        raw_summary.get("analysis_name") if analysis_id is not None else None
    )

    # Check organism match
    if organism is not None and total_matching == 0 and not raw_summary["not_found_clusters"]:
        envelope["not_matched_organism"] = organism
    else:
        envelope["not_matched_organism"] = None

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_genes_in_cluster(
        cluster_ids=cluster_ids, analysis_id=analysis_id, organism=organism,
        verbose=verbose, limit=limit, offset=offset)
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope


# ---------------------------------------------------------------------------
# ontology_landscape helpers
# ---------------------------------------------------------------------------


def _ontology_size_factor(median: float) -> float:
    """[5, 50] sweet-spot penalty on median term size."""
    if median <= 0:
        return 0.0
    return min(1.0, median / 5.0) * min(1.0, 50.0 / median)


def _ontology_relevance_score(
    row: dict, experiment_weighted: bool,
) -> float:
    sf = _ontology_size_factor(row["median_genes_per_term"])
    if experiment_weighted and "median_exp_coverage" in row:
        return row["median_exp_coverage"] * sf
    return row["genome_coverage"] * sf


def _ontology_exp_coverage_stats(
    expcov_rows: list[dict],
    valid_eids: list[str],
    level_keys: list[int],
) -> dict:
    """Zero-fill + min/median/max across experiments per level.

    expcov_rows: rows from build_ontology_expcov for a single ontology.
    valid_eids: experiments known to be valid -- any missing from a given
                level contributes 0 to the aggregation.
    level_keys: set of levels observed in landscape stats; experiments
                contribute 0 at levels where they emit no row.

    Returns {level: {min_exp_coverage, median_exp_coverage,
    max_exp_coverage, n_experiments_with_coverage}}.
    """
    per_level: dict = {
        lvl: {eid: 0.0 for eid in valid_eids} for lvl in level_keys
    }
    for r in expcov_rows:
        lvl = r["level"]
        eid = r["eid"]
        if lvl in per_level and eid in per_level[lvl]:
            per_level[lvl][eid] = (
                r["n_at_level"] / r["n_total"] if r["n_total"] else 0.0
            )
    out: dict = {}
    for lvl, by_eid in per_level.items():
        covs = list(by_eid.values())
        out[lvl] = {
            "min_exp_coverage": min(covs) if covs else 0.0,
            "median_exp_coverage": statistics.median(covs) if covs else 0.0,
            "max_exp_coverage": max(covs) if covs else 0.0,
            "n_experiments_with_coverage": sum(1 for c in covs if c > 0),
        }
    return out


# ---------------------------------------------------------------------------
# ontology_landscape
# ---------------------------------------------------------------------------


def ontology_landscape(
    organism: str,
    ontology: str | None = None,
    experiment_ids: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    min_gene_set_size: int = 5,
    max_gene_set_size: int = 500,
    tree: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Characterise ontologies for enrichment in one organism.

    Per-(ontology x level) rows. Ranked by spec_score (genome_coverage
    x size_factor(median_genes_per_term)) when experiment_ids is None,
    or median_exp_coverage x size_factor when set. Only terms with
    min_gene_set_size <= gene_count <= max_gene_set_size contribute to
    per-level stats -- same filter as pathway_enrichment.

    Returns dict with keys: organism_name, organism_gene_count,
    n_ontologies, by_ontology, not_found, not_matched, results,
    returned, total_matching, truncated, offset.

    Raises ValueError on unknown/ambiguous organism or invalid ontology.
    """
    if ontology is not None and ontology not in ONTOLOGY_CONFIG:
        raise ValueError(
            f"Invalid ontology '{ontology}'. "
            f"Valid: {sorted(ONTOLOGY_CONFIG)}"
        )
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Step 1: Resolve organism to canonical string (raises on unknown/ambiguous)
    canonical_org = _validate_organism_inputs(
        organism=organism, locus_tags=None, experiment_ids=None, conn=conn,
    )

    # Step 2: Total gene count for genome_coverage denominator
    gc_cypher, gc_params = build_ontology_organism_gene_count(
        organism_name=canonical_org,
    )
    organism_gene_count = conn.execute_query(gc_cypher, **gc_params)[0]["total_genes"]

    # Step 3: Experiment validation
    valid_eids: list[str] = []
    not_found: list[str] = []
    not_matched: list[str] = []
    if experiment_ids:
        ec_cypher, ec_params = build_ontology_experiment_check(
            experiment_ids=experiment_ids,
        )
        ec_rows = conn.execute_query(ec_cypher, **ec_params)
        for r in ec_rows:
            if not r["exists"]:
                not_found.append(r["eid"])
            elif r["exp_organism"] != canonical_org:
                not_matched.append(r["eid"])
            else:
                valid_eids.append(r["eid"])

    # Step 4: Per-ontology landscape queries
    targets = [ontology] if ontology else ALL_ONTOLOGIES
    all_rows: list[dict] = []
    for ont in targets:
        ls_cypher, ls_params = build_ontology_landscape(
            ontology=ont, organism_name=canonical_org, verbose=verbose,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
            tree=tree if ont == "brite" else None,
        )
        stat_rows = conn.execute_query(ls_cypher, **ls_params)
        n_levels = len(stat_rows)

        # Experiment coverage aggregation (per-ontology)
        exp_stats: dict = {}
        if valid_eids:
            ec_cypher2, ec_params2 = build_ontology_expcov(
                ontology=ont, organism_name=canonical_org,
                experiment_ids=valid_eids,
                min_gene_set_size=min_gene_set_size,
                max_gene_set_size=max_gene_set_size,
            )
            expcov_rows = conn.execute_query(ec_cypher2, **ec_params2)
            exp_stats = _ontology_exp_coverage_stats(
                expcov_rows, valid_eids,
                level_keys=[r["level"] for r in stat_rows],
            )

        for r in stat_rows:
            tree_val = r.get("tree")
            row: dict = {
                "ontology_type": ont,
                "level": r["level"],
                "n_terms_with_genes": r["n_terms_with_genes"],
                "n_genes_at_level": r["n_genes_at_level"],
                "genome_coverage": (
                    r["n_genes_at_level"] / organism_gene_count
                    if organism_gene_count else 0.0
                ),
                "min_genes_per_term": r["min_genes_per_term"],
                "q1_genes_per_term": r["q1_genes_per_term"],
                "median_genes_per_term": r["median_genes_per_term"],
                "q3_genes_per_term": r["q3_genes_per_term"],
                "max_genes_per_term": r["max_genes_per_term"],
                "n_levels_in_ontology": n_levels,
            }
            # best_effort_share -- GO ontologies only
            if ont in GO_ONTOLOGIES:
                row["best_effort_share"] = (
                    r["n_best_effort"] / r["n_terms_with_genes"]
                    if r["n_terms_with_genes"] else 0.0
                )
            else:
                row["best_effort_share"] = None
            if tree_val is not None:
                row["tree"] = tree_val
                row["tree_code"] = r.get("tree_code")
            if verbose:
                row["example_terms"] = r["example_terms"]
            if valid_eids:
                e = exp_stats.get(r["level"], {
                    "min_exp_coverage": 0.0,
                    "median_exp_coverage": 0.0,
                    "max_exp_coverage": 0.0,
                    "n_experiments_with_coverage": 0,
                })
                row.update(e)
            all_rows.append(row)

    # Step 5: Rank in Python. Before limit/offset so relevance_rank is
    # stable when caller paginates.
    experiment_weighted = bool(valid_eids)
    for r in all_rows:
        r["_score"] = _ontology_relevance_score(r, experiment_weighted)
    all_rows.sort(
        key=lambda r: (-r["_score"], -r["genome_coverage"], r["level"]),
    )
    for i, r in enumerate(all_rows):
        r["relevance_rank"] = i + 1
        r.pop("_score", None)

    # by_ontology: summary keyed by ontology_type (or "brite:tree_name"
    # for BRITE with tree); first row per key (already sorted by rank)
    # provides best_* fields.
    by_ontology: dict[str, dict] = {}
    for r in all_rows:
        ont = r["ontology_type"]
        tree_val = r.get("tree")
        key = f"{ont}:{tree_val}" if tree_val else ont
        if key not in by_ontology:
            by_ontology[key] = {
                "best_level": r["level"],
                "best_genome_coverage": r["genome_coverage"],
                "best_relevance_rank": r["relevance_rank"],
                "n_levels": 0,
            }
            if tree_val:
                by_ontology[key]["tree"] = tree_val
                by_ontology[key]["tree_code"] = r.get("tree_code")
        by_ontology[key]["n_levels"] += 1

    # Step 6: Paginate + envelope
    total_matching = len(all_rows)
    sliced = all_rows[offset:]
    if limit is not None:
        results = [] if limit == 0 else sliced[:limit]
    else:
        results = sliced

    return {
        "organism_name": canonical_org,
        "organism_gene_count": organism_gene_count,
        "n_ontologies": len({r["ontology_type"] for r in all_rows}),
        "by_ontology": by_ontology,
        "not_found": not_found,
        "not_matched": not_matched,
        "results": results,
        "returned": len(results),
        "total_matching": total_matching,
        "truncated": total_matching > offset + len(results),
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# pathway_enrichment helpers
# ---------------------------------------------------------------------------


def _build_pathway_enrichment_envelope(
    *, df, inputs, gbo_result, ontology, level,
    pvalue_cutoff, summary, verbose, limit, offset,
) -> dict:
    import pandas as pd

    total_matching = int(len(df))
    n_significant = int((df["p_adjust"] < pvalue_cutoff).sum()) if total_matching else 0

    produced_clusters = set(df["cluster"]) if total_matching else set()
    skipped: list[dict] = []
    for cluster in inputs.cluster_metadata:
        if cluster in produced_clusters:
            continue
        if cluster not in inputs.background or not inputs.background.get(cluster):
            reason = "empty_background"
        elif not inputs.gene_sets.get(cluster):
            reason = "empty_gene_set"
        else:
            reason = "no_pathways_in_size_range"
        skipped.append({"cluster": cluster, "reason": reason})

    if summary:
        returned_rows = []
        returned = 0
        truncated = total_matching > 0
    else:
        sliced = df.iloc[offset:offset + limit] if total_matching else df
        if not verbose:
            drop_cols = [c for c in ("foreground_gene_ids", "background_gene_ids") if c in sliced.columns]
            sliced = sliced.drop(columns=drop_cols)
        returned_rows = sliced.to_dict(orient="records")
        # Strip sparse tree/tree_code for non-BRITE results
        for r in returned_rows:
            tree_v = r.get("tree")
            if tree_v is None or (isinstance(tree_v, float) and pd.isna(tree_v)):
                r.pop("tree", None)
                r.pop("tree_code", None)
        returned = len(returned_rows)
        truncated = (offset + returned) < total_matching

    return {
        "organism_name": inputs.organism_name,
        "ontology": ontology,
        "level": level,
        "total_matching": total_matching,
        "returned": returned,
        "truncated": truncated,
        "offset": offset,
        "n_significant": n_significant,
        "by_experiment": _envelope_by_experiment(df, inputs, pvalue_cutoff),
        "by_direction": _envelope_by_direction(df, pvalue_cutoff),
        "by_omics_type": _envelope_by_omics_type(df, pvalue_cutoff),
        "cluster_summary": _envelope_cluster_summary(df, inputs),
        "top_clusters_by_min_padj": _envelope_top_clusters(df, inputs),
        "top_pathways_by_padj": _envelope_top_pathways(df),
        "not_found": inputs.not_found,
        "not_matched": inputs.not_matched,
        "no_expression": inputs.no_expression,
        "term_validation": {
            "not_found": list(gbo_result.get("not_found", [])),
            "wrong_ontology": list(gbo_result.get("wrong_ontology", [])),
            "wrong_level": list(gbo_result.get("wrong_level", [])),
            "filtered_out": list(gbo_result.get("filtered_out", [])),
        },
        "clusters_skipped": skipped,
        "results": returned_rows,
    }


def _envelope_by_experiment(df, inputs, pvalue_cutoff):
    if df.empty:
        return []
    out = []
    for exp_id, sub in df.groupby("experiment_id", sort=True):
        md_cluster = next(
            (c for c, md in inputs.cluster_metadata.items() if md.get("experiment_id") == exp_id),
            None,
        )
        md = inputs.cluster_metadata.get(md_cluster, {}) if md_cluster else {}
        out.append({
            "experiment_id": exp_id,
            "name": md.get("name"),
            "omics_type": md.get("omics_type"),
            "table_scope": md.get("table_scope"),
            "treatment_type": md.get("treatment_type"),
            "background_factors": md.get("background_factors"),
            "is_time_course": md.get("is_time_course"),
            "n_tests": int(len(sub)),
            "n_significant": int((sub["p_adjust"] < pvalue_cutoff).sum()),
            "n_clusters": int(sub["cluster"].nunique()),
        })
    return out


def _envelope_by_direction(df, pvalue_cutoff):
    if df.empty:
        return []
    return [
        {
            "direction": direction,
            "n_tests": int(len(sub)),
            "n_significant": int((sub["p_adjust"] < pvalue_cutoff).sum()),
        }
        for direction, sub in df.groupby("direction", sort=True)
    ]


def _envelope_by_omics_type(df, pvalue_cutoff):
    if df.empty:
        return []
    return [
        {
            "omics_type": omics_type,
            "n_tests": int(len(sub)),
            "n_significant": int((sub["p_adjust"] < pvalue_cutoff).sum()),
        }
        for omics_type, sub in df.groupby("omics_type", sort=True)
    ]


def _envelope_cluster_summary(df, inputs):
    if df.empty:
        return {
            "n_clusters": 0,
            "n_tests_min": 0, "n_tests_median": 0.0, "n_tests_max": 0,
            "n_significant_min": 0, "n_significant_median": 0.0, "n_significant_max": 0,
            "universe_size_min": 0, "universe_size_median": 0.0, "universe_size_max": 0,
        }
    import statistics
    per_cluster = df.groupby("cluster").agg(n_tests=("term_id", "size"))
    n_tests_vals = per_cluster["n_tests"].tolist()
    universe_sizes = [
        len(inputs.background.get(c, [])) for c in per_cluster.index
    ]
    sig_per_cluster = (
        df[df["p_adjust"] < 0.05]
        .groupby("cluster")
        .size()
        .reindex(per_cluster.index, fill_value=0)
        .tolist()
    )
    return {
        "n_clusters": len(per_cluster),
        "n_tests_min": min(n_tests_vals),
        "n_tests_median": float(statistics.median(n_tests_vals)),
        "n_tests_max": max(n_tests_vals),
        "n_significant_min": min(sig_per_cluster),
        "n_significant_median": float(statistics.median(sig_per_cluster)),
        "n_significant_max": max(sig_per_cluster),
        "universe_size_min": min(universe_sizes) if universe_sizes else 0,
        "universe_size_median": float(statistics.median(universe_sizes)) if universe_sizes else 0.0,
        "universe_size_max": max(universe_sizes) if universe_sizes else 0,
    }


def _envelope_top_clusters(df, inputs, top_n=5):
    if df.empty:
        return []
    per_cluster_min_padj = df.groupby("cluster")["p_adjust"].min()
    top_clusters = (
        per_cluster_min_padj.sort_values(ascending=True).head(top_n).index.tolist()
    )
    out = []
    for cluster in top_clusters:
        sub = df[df["cluster"] == cluster]
        md = inputs.cluster_metadata.get(cluster, {})
        out.append({
            "cluster": cluster,
            "experiment_id": md.get("experiment_id"),
            "name": md.get("name"),
            "timepoint": md.get("timepoint"),
            "timepoint_hours": md.get("timepoint_hours"),
            "timepoint_order": md.get("timepoint_order"),
            "direction": md.get("direction"),
            "omics_type": md.get("omics_type"),
            "table_scope": md.get("table_scope"),
            "treatment_type": md.get("treatment_type"),
            "background_factors": md.get("background_factors"),
            "is_time_course": md.get("is_time_course"),
            "n_tests": int(len(sub)),
            "n_significant": int((sub["p_adjust"] < 0.05).sum()),
            "universe_size": len(inputs.background.get(cluster, [])),
            "min_padj": float(per_cluster_min_padj[cluster]),
        })
    return out


def _envelope_top_pathways(df, top_n=10):
    if df.empty:
        return []
    top = df.sort_values(
        ["p_adjust", "cluster", "term_id"], ascending=True
    ).head(top_n)
    return [
        {
            "cluster": r["cluster"],
            "term_id": r["term_id"],
            "term_name": r["term_name"],
            "p_adjust": float(r["p_adjust"]),
            "signed_score": float(r["signed_score"]) if "signed_score" in r else 0.0,
        }
        for _, r in top.iterrows()
    ]


# ---------------------------------------------------------------------------
# pathway_enrichment public function
# ---------------------------------------------------------------------------


def pathway_enrichment(
    organism: str,
    experiment_ids: list[str],
    ontology: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    direction: str = "both",
    significant_only: bool = True,
    background: str | list[str] = "table_scope",
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    pvalue_cutoff: float = 0.05,
    timepoint_filter: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    tree: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Pathway over-representation analysis from DE results.

    See docs://analysis/enrichment for methodology.
    See docs/superpowers/specs/2026-04-12-pathway-enrichment-design.md.
    """
    # --- Input validation (category 1) ---
    if ontology not in ALL_ONTOLOGIES:
        raise ValueError(
            f"Invalid ontology '{ontology}'. Valid: {ALL_ONTOLOGIES}"
        )
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
    if level is None and not term_ids:
        raise ValueError(
            "At least one of `level` or `term_ids` must be provided."
        )
    if direction not in {"up", "down", "both"}:
        raise ValueError(
            f"direction must be one of 'up', 'down', 'both'; got {direction!r}"
        )
    if isinstance(background, str):
        if background not in {"table_scope", "organism"}:
            raise ValueError(
                f"background must be 'table_scope', 'organism', or a list; "
                f"got {background!r}"
            )
    elif isinstance(background, list):
        if not background:
            raise ValueError("background list must be non-empty")
    else:
        raise ValueError(
            f"background must be 'table_scope', 'organism', or a list; "
            f"got {type(background).__name__}"
        )
    if min_gene_set_size < 0:
        raise ValueError("min_gene_set_size must be >= 0.")
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError(
            "max_gene_set_size must be >= min_gene_set_size."
        )
    if not (0 < pvalue_cutoff < 1):
        raise ValueError(
            f"pvalue_cutoff must be in (0, 1); got {pvalue_cutoff}"
        )
    if not experiment_ids:
        raise ValueError("at least one experiment_id required")

    from multiomics_explorer.analysis.enrichment import (
        de_enrichment_inputs, fisher_ora,
    )
    import pandas as pd

    conn = _default_conn(conn)

    # Step 2: build EnrichmentInputs
    inputs = de_enrichment_inputs(
        experiment_ids=experiment_ids,
        organism=organism,
        direction=direction,
        significant_only=significant_only,
        timepoint_filter=timepoint_filter,
        conn=conn,
    )

    # Step 3: resolve background
    if background == "table_scope":
        resolved_bg = inputs.background
    elif background == "organism":
        org_cypher = (
            "MATCH (g:Gene {organism_name: $org}) "
            "RETURN collect(g.locus_tag) AS locus_tags"
        )
        org_rows = conn.execute_query(org_cypher, org=inputs.organism_name)
        org_locus_tags = org_rows[0]["locus_tags"] if org_rows else []
        resolved_bg = {c: list(org_locus_tags) for c in inputs.gene_sets}
    else:
        resolved_bg = {c: list(background) for c in inputs.gene_sets}

    # Step 4: TERM2GENE
    gbo_result = genes_by_ontology(
        ontology=ontology,
        organism=inputs.organism_name,
        level=level,
        term_ids=term_ids,
        min_gene_set_size=0,
        max_gene_set_size=None,
        summary=False,
        verbose=False,
        limit=None,
        offset=0,
        tree=tree,
        conn=conn,
    )
    from multiomics_explorer.analysis.frames import to_dataframe
    term2gene = to_dataframe(gbo_result)

    # Step 5: fisher_ora
    if term2gene.empty or not inputs.gene_sets:
        df = pd.DataFrame()
    else:
        df = fisher_ora(
            gene_sets=inputs.gene_sets,
            background=resolved_bg,
            term2gene=term2gene,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
        )

    # Step 6: attach metadata + signed_score
    if not df.empty:
        md_df = pd.DataFrame.from_dict(
            inputs.cluster_metadata, orient="index"
        ).reset_index().rename(columns={"index": "cluster"})
        df = df.merge(md_df, on="cluster", how="left")
        import numpy as np
        sign = np.where(df["direction"] == "up", 1,
                        np.where(df["direction"] == "down", -1, 0))
        df["signed_score"] = sign * -np.log10(df["p_adjust"].clip(lower=1e-300))

    # Step 7: envelope
    envelope = _build_pathway_enrichment_envelope(
        df=df,
        inputs=inputs,
        gbo_result=gbo_result,
        ontology=ontology,
        level=level,
        pvalue_cutoff=pvalue_cutoff,
        summary=summary,
        verbose=verbose,
        limit=limit if limit is not None else len(df),
        offset=offset,
    )
    return envelope
