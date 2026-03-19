"""Public Python API for the multi-omics knowledge graph.

Each function wraps query builders + connection.execute_query to provide
a clean interface for scripts, notebooks, and the MCP tool layer.

No limit parameters — callers slice results as needed.
No JSON formatting — returns Python dicts/lists.
Validation errors raise ValueError with specific messages.
"""

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
    build_list_condition_types,
    build_list_gene_categories,
    build_list_organisms,
    build_query_expression,
    build_resolve_gene,
    build_search_genes,
    build_search_genes_dedup_groups,
    build_search_ontology,
)
from multiomics_explorer.kg.schema import load_schema_from_neo4j


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
    *,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """Resolve a gene identifier to matching graph nodes.

    Returns list of dicts with keys: locus_tag, gene_name, product,
    organism_strain.
    """
    if not identifier or not identifier.strip():
        raise ValueError("identifier must not be empty.")
    conn = _default_conn(conn)
    cypher, params = build_resolve_gene(identifier=identifier, organism=organism)
    return conn.execute_query(cypher, **params)


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
        escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
        cypher, params = build_search_genes(
            search_text=escaped, organism=organism,
            category=category, min_quality=min_quality,
        )
        results = conn.execute_query(cypher, **params)

    if deduplicate:
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


def query_expression(
    gene_id: str | None = None,
    organism: str | None = None,
    condition: str | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
    *,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """Query differential expression data.

    At least one of gene_id, organism, or condition must be provided.

    Returns list of dicts with keys: gene, product, edge_type, source,
    direction, log2fc, padj, organism_strain, control, context,
    time_point, publications.

    Raises ValueError if no filter is provided.
    """
    if not any([gene_id, organism, condition]):
        raise ValueError(
            "At least one of gene_id, organism, or condition must be provided."
        )
    conn = _default_conn(conn)
    cypher, params = build_query_expression(
        gene_id=gene_id, organism=organism, condition=condition,
        direction=direction, min_log2fc=min_log2fc, max_pvalue=max_pvalue,
    )
    return conn.execute_query(cypher, **params)


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
    if not (1 <= member_limit <= 200):
        raise ValueError(
            f"Invalid member_limit {member_limit}. Valid: 1-200."
        )

    # 1. Query gene metadata
    cypher_gene, params_gene = build_gene_stub(gene_id=gene_id)
    gene_rows = conn.execute_query(cypher_gene, **params_gene)
    if not gene_rows:
        raise ValueError(f"Gene '{gene_id}' not found.")
    query_gene = gene_rows[0]

    # 2. Query ortholog groups
    cypher_groups, params_groups = build_get_homologs_groups(
        gene_id=gene_id, source=source,
        taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank,
    )
    groups = conn.execute_query(cypher_groups, **params_groups)

    # 3. Optionally fetch members
    if include_members and groups:
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
      condition_types: list[dict] with condition_type, count
    """
    conn = _default_conn(conn)

    cat_cypher, cat_params = build_list_gene_categories()
    categories = conn.execute_query(cat_cypher, **cat_params)

    cond_cypher, cond_params = build_list_condition_types()
    condition_types = conn.execute_query(cond_cypher, **cond_params)

    return {
        "gene_categories": categories,
        "condition_types": condition_types,
    }


def list_organisms(
    *,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """List all organisms in the knowledge graph.

    Returns list of dicts with keys: organism_name, genus, strain,
    clade, gene_count.
    """
    conn = _default_conn(conn)
    cypher, params = build_list_organisms()
    return conn.execute_query(cypher, **params)


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
