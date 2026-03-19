"""MCP tool implementations for the Multiomics Knowledge Graph."""

import json
import re

from mcp.server.fastmcp import Context, FastMCP

from neo4j.exceptions import ClientError as Neo4jClientError

from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.constants import (
    MAX_SPECIFICITY_RANK,
    VALID_OG_SOURCES,
    VALID_TAXONOMIC_LEVELS,
)
from multiomics_explorer.kg.queries_lib import (
    build_compare_conditions,
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


def _conn(ctx: Context) -> GraphConnection:
    """Get the Neo4j connection from lifespan context."""
    return ctx.request_context.lifespan_context.conn


def _debug(ctx: Context) -> bool:
    """Check if debug_queries is enabled."""
    return ctx.request_context.lifespan_context.debug_queries


def _fmt(results: list[dict], limit: int | None = None) -> str:
    """Format query results as JSON string."""
    if limit is not None:
        results = results[:limit]
    return json.dumps(results, indent=2, default=str)


def _with_query(response: str, cypher: str, params: dict, ctx: Context) -> str:
    """Wrap response with query info if debug mode is on."""
    if not _debug(ctx):
        return response
    debug_block = json.dumps({"_debug": {"cypher": cypher, "params": params}}, indent=2, default=str)
    return f"{debug_block}\n---\n{response}"


# Read-only keywords check for raw Cypher
_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|CALL\s*\{|CALL\s+\w+\.\w+|LOAD\s+CSV)\b",
    re.IGNORECASE,
)


def _group_by_organism(results: list[dict]) -> dict:
    """Group gene results by organism_strain. Returns {organism: [genes], ...}."""
    grouped: dict[str, list[dict]] = {}
    for row in results:
        org = row.get("organism_strain", "Unknown")
        entry = {k: v for k, v in row.items() if k != "organism_strain"}
        grouped.setdefault(org, []).append(entry)
    return grouped


def register_tools(mcp: FastMCP):
    """Register all KG tools with the MCP server."""

    @mcp.tool()
    def get_schema(ctx: Context) -> str:
        """Get the knowledge graph schema: node types with counts, relationship types with
        source/target labels, and property names. Use this first to understand what's queryable."""
        from multiomics_explorer.kg.schema import load_schema_from_neo4j

        conn = _conn(ctx)
        schema = load_schema_from_neo4j(conn)
        return schema.to_prompt_string()

    @mcp.tool()
    def list_filter_values(ctx: Context) -> str:
        """List valid values for categorical filters used across tools.

        Returns:
        - gene_categories: values for the category filter on search_genes
          (e.g. "Photosynthesis", "Transport", "Stress response and adaptation")
        - condition_types: values for the condition filter on query_expression
          and compare_conditions (e.g. "nitrogen_stress", "light_stress", "coculture")
        """
        lc = ctx.request_context.lifespan_context
        cached = getattr(lc, "_filter_values_cache", None)
        if cached is not None:
            return cached

        conn = _conn(ctx)

        cat_cypher, cat_params = build_list_gene_categories()
        categories = conn.execute_query(cat_cypher, **cat_params)

        cond_cypher, cond_params = build_list_condition_types()
        condition_types = conn.execute_query(cond_cypher, **cond_params)

        result = {
            "gene_categories": categories,
            "condition_types": condition_types,
        }
        response = json.dumps(result, indent=2, default=str)
        lc._filter_values_cache = response
        return response

    @mcp.tool()
    def list_organisms(ctx: Context) -> str:
        """List all organisms in the knowledge graph with strain, genus, clade,
        and gene count.

        Use this to discover valid organism names for filtering in other tools.
        The organism filter uses partial matching (CONTAINS), so "MED4",
        "Prochlorococcus MED4", and "Prochlorococcus" all work.
        """
        lc = ctx.request_context.lifespan_context
        cached = getattr(lc, "_organisms_cache", None)
        if cached is not None:
            return cached

        conn = _conn(ctx)
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        if not results:
            return "No organisms found in the knowledge graph."
        response = _fmt(results)
        lc._organisms_cache = response
        return response

    @mcp.tool()
    def resolve_gene(
        ctx: Context,
        identifier: str,
        organism: str | None = None,
    ) -> str:
        """Resolve a gene identifier to matching graph nodes. Returns locus_tags grouped by
        organism. Use the returned locus_tag with get_gene_details, query_expression, or
        other tools.

        Args:
            identifier: Gene identifier — locus_tag (e.g. "PMM0001"), gene name (e.g. "dnaN"),
                old locus tag, or RefSeq protein ID.
            organism: Optional organism filter (e.g. "MED4", "Prochlorococcus MED4").
        """
        conn = _conn(ctx)
        cypher, params = build_resolve_gene(identifier=identifier, organism=organism)
        results = conn.execute_query(cypher, **params)
        if not results:
            msg = f"No gene found for identifier '{identifier}'"
            if organism:
                msg += f" in {organism}"
            response = json.dumps({"results": {}, "message": msg})
        else:
            grouped = _group_by_organism(results)
            response = json.dumps(
                {"results": grouped, "total": len(results)},
                indent=2, default=str,
            )
        return _with_query(response, cypher, params, ctx)

    @mcp.tool()
    def search_genes(
        ctx: Context,
        search_text: str,
        organism: str | None = None,
        category: str | None = None,
        min_quality: int = 0,
        deduplicate: bool = False,
        limit: int = 10,
    ) -> str:
        """Free-text search across gene functional annotations using full-text index.
        Supports Lucene syntax: "DNA repair", nitrogen AND transport, iron*, dnaN~.

        Args:
            search_text: Free-text query (Lucene syntax supported).
            organism: Optional organism filter (e.g. "MED4", "Prochlorococcus MED4").
                Use list_organisms to see all valid organisms.
            category: Optional gene_category filter (e.g. "Photosynthesis", "Transport").
                Use list_filter_values to see all valid categories. Invalid values
                return empty results (no validation).
            min_quality: Minimum annotation_quality (0-3).
                0 = hypothetical, no function info;
                1 = hypothetical but has function description;
                2 = real product name;
                3 = well-annotated (product + GO/KEGG/EC/Pfam).
                Use 2 to skip hypothetical proteins.
            deduplicate: If True, collapse orthologs by ortholog group and return
                one representative per group with collapsed_count and
                group_organisms summary. Counts reflect hits within the result
                set, not total group membership — use get_homologs for full
                ortholog inventory.
            limit: Max results (default 10, max 50). When deduplicate=True, the
                limit applies to the pre-dedup query, so fewer rows may be
                returned after collapsing.
        """
        conn = _conn(ctx)
        limit = min(limit, 50)
        cypher, params = build_search_genes(
            search_text=search_text, organism=organism,
            category=category,
            min_quality=min_quality,
        )
        try:
            results = conn.execute_query(cypher, **params)
        except Neo4jClientError:
            # Retry with escaped Lucene special characters
            escaped = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', r'\\\g<0>', search_text)
            cypher, params = build_search_genes(
                search_text=escaped, organism=organism,
                category=category,
                min_quality=min_quality,
            )
            results = conn.execute_query(cypher, **params)
        results = results[:limit]
        if deduplicate:
            # Fetch most-specific ortholog group for each result gene
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
            # Add group summary to each representative
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
            results = deduped
        if not results:
            response = json.dumps({
                "results": [], "total": 0, "query": search_text,
            })
        else:
            response = json.dumps({
                "results": results, "total": len(results), "query": search_text,
            }, indent=2, default=str)
        return _with_query(response, cypher, params, ctx)

    @mcp.tool()
    def gene_overview(ctx: Context, gene_ids: list[str], limit: int = 50) -> str:
        """Get an overview of one or more genes: identity and data availability.

        Use this after resolve_gene, search_genes, genes_by_ontology, or
        get_homologs to understand what each gene is and what follow-up data
        exists.

        Returns one row per gene with routing signals:
        - annotation_types: which ontology types have annotations
          → use gene_ontology_terms with the relevant type
        - expression_edge_count + significant_expression_count: whether
          expression data exists and how much is significant
          → use query_expression
        - closest_ortholog_group_size + closest_ortholog_genera: whether
          orthologs exist and in which genera
          → use get_homologs for full membership

        Args:
            gene_ids: List of gene locus_tags.
                      Use resolve_gene to find locus_tags from other identifiers.
            limit: Max genes to return (default 50).
        """
        conn = _conn(ctx)
        cypher, params = build_gene_overview(gene_ids=gene_ids)
        rows = conn.execute_query(cypher, **params)
        if not rows:
            return "No genes found for the given locus_tags."
        response = _fmt(rows, limit=limit)
        return _with_query(response, cypher, params, ctx)

    @mcp.tool()
    def get_gene_details(ctx: Context, gene_id: str) -> str:
        """Get all properties for a gene.

        This is a deep-dive tool — use gene_overview for the common case.
        Returns all Gene node properties including sparse fields
        (catalytic_activities, transporter_classification, cazy_ids, etc.).

        For organism taxonomy, use list_organisms. For homologs, use
        get_homologs. For ontology annotations, use gene_ontology_terms.
        For expression data, use query_expression.

        Args:
            gene_id: Gene locus_tag (e.g. "PMM0001", "sync_0001").
        """
        conn = _conn(ctx)
        cypher, params = build_get_gene_details(gene_id=gene_id)
        results = conn.execute_query(cypher, **params)
        if not results or results[0]["gene"] is None:
            return f"Gene '{gene_id}' not found."
        response = _fmt([results[0]["gene"]])
        return _with_query(response, cypher, params, ctx)

    @mcp.tool()
    def query_expression(
        ctx: Context,
        gene_id: str | None = None,
        organism: str | None = None,
        condition: str | None = None,
        direction: str | None = None,
        min_log2fc: float | None = None,
        max_pvalue: float | None = None,
        limit: int = 50,
    ) -> str:
        """Query differential expression data from the knowledge graph.

        Expression edges come in two types:
        - Coculture_changes_expression_of: OrganismTaxon → Gene (coculture experiments)
        - Condition_changes_expression_of: EnvironmentalCondition → Gene (stress experiments)

        At least one of gene_id, organism, or condition must be provided.

        Args:
            gene_id: Filter by gene locus_tag (e.g. "PMM0001").
            organism: Filter by target organism strain (e.g. "MED4") — the organism
                      whose genes are affected.
            condition: Filter by expression source — coculture partner name
                       (e.g. "Alteromonas") or environmental condition name/type
                       (e.g. "nitrogen_stress", "light_stress").
            direction: Filter by "up" or "down" regulation.
            min_log2fc: Minimum absolute log2 fold change.
            max_pvalue: Maximum adjusted p-value.
            limit: Max results (default 50).
        """
        if not any([gene_id, organism, condition]):
            return "Error: provide at least one of gene_id, organism, or condition."

        conn = _conn(ctx)
        cypher, params = build_query_expression(
            gene_id=gene_id, organism=organism, condition=condition,
            direction=direction, min_log2fc=min_log2fc, max_pvalue=max_pvalue,
        )
        results = conn.execute_query(cypher, **params)
        if not results:
            return _with_query("No expression data found for the given filters.", cypher, params, ctx)
        return _with_query(_fmt(results, limit=limit), cypher, params, ctx)

    @mcp.tool()
    def compare_conditions(
        ctx: Context,
        gene_ids: list[str] | None = None,
        organisms: list[str] | None = None,
        conditions: list[str] | None = None,
        limit: int = 100,
    ) -> str:
        """Compare expression across conditions or strains. Returns one row per
        gene-source combination for easy comparison.

        At least one filter must be provided.

        Args:
            gene_ids: List of gene locus_tags to compare.
            organisms: List of target strain names (whose genes are affected).
            conditions: List of source names — coculture organism genus or condition_type
                        (exact match, unlike query_expression which uses CONTAINS).
            limit: Max results (default 100).
        """
        if not any([gene_ids, organisms, conditions]):
            return "Error: provide at least one of gene_ids, organisms, or conditions."

        conn = _conn(ctx)
        cypher, params = build_compare_conditions(
            gene_ids=gene_ids, organisms=organisms,
            conditions=conditions,
        )
        results = conn.execute_query(cypher, **params)
        if not results:
            return _with_query("No expression data found for the given filters.", cypher, params, ctx)
        return _with_query(_fmt(results, limit=limit), cypher, params, ctx)

    def _no_groups_msg(gene_id, source, taxonomic_level, max_specificity_rank):
        msg = f"No ortholog groups found for '{gene_id}'"
        filters = []
        if source:
            filters.append(f"source={source}")
        if taxonomic_level:
            filters.append(f"taxonomic_level={taxonomic_level}")
        if max_specificity_rank is not None:
            filters.append(f"max_specificity_rank={max_specificity_rank}")
        if filters:
            msg += f" with constraints: {', '.join(filters)}"
        return msg + "."

    @mcp.tool()
    def get_homologs(
        ctx: Context,
        gene_id: str,
        source: str | None = None,
        taxonomic_level: str | None = None,
        max_specificity_rank: int | None = None,
        exclude_paralogs: bool = True,
        include_members: bool = False,
        member_limit: int = 50,
    ) -> str:
        """Find orthologs of a gene, grouped by ortholog group.

        Returns ortholog groups the gene belongs to, ordered from most specific
        (curated) to broadest (Bacteria-level COG). Each group includes its
        consensus function, member/organism counts, and genera.

        By default returns group summaries only. Set include_members=True to
        get the full list of member genes per group.

        Args:
            gene_id: Gene locus_tag (e.g. "PMM0001").
            source: Filter by OG source: "cyanorak" or "eggnog".
            taxonomic_level: Filter by level: "curated", "Prochloraceae",
                "Synechococcus", "Alteromonadaceae", "Cyanobacteria",
                "Gammaproteobacteria", "Bacteria".
            max_specificity_rank: Cap breadth — 0=curated only, 1=+family,
                2=+order, 3=+domain (all). Overrides source/taxonomic_level.
            exclude_paralogs: If True (default), exclude members from the same
                organism strain as the query gene. Set False to include paralogs.
                Only applies when include_members=True.
            include_members: If True, include full member gene lists per group.
                Default False returns group summaries (counts, consensus function,
                genera) without individual member genes.
            member_limit: Max members returned per group (default 50, max 200).
                Only applies when include_members=True. Groups exceeding the
                limit include a "truncated" flag.

        Raises:
            ValueError if source is not in {"cyanorak", "eggnog"} or
            taxonomic_level is not in {"curated", "Prochloraceae",
            "Synechococcus", "Alteromonadaceae", "Cyanobacteria",
            "Gammaproteobacteria", "Bacteria"} or max_specificity_rank
            is not in 0-3 or member_limit is not in 1-200.

        Notes:
            - member_count and organism_count are total group counts from the
              KG (include paralogs). When exclude_paralogs is True, the
              returned members list may be smaller than member_count.
            - For expression data of orthologs, use query_expression with
              include_orthologs (separate tool, not part of this response).
            - A gene typically belongs to 1-3 groups: one Cyanorak curated
              cluster (Pro/Syn only), one eggNOG family-level OG, and one
              eggNOG Bacteria-level COG.
        """
        conn = _conn(ctx)

        # Validate enum params
        if source is not None and source not in VALID_OG_SOURCES:
            return f"Invalid source '{source}'. Valid: {sorted(VALID_OG_SOURCES)}"
        if taxonomic_level is not None and taxonomic_level not in VALID_TAXONOMIC_LEVELS:
            return f"Invalid taxonomic_level '{taxonomic_level}'. Valid: {sorted(VALID_TAXONOMIC_LEVELS)}"
        if max_specificity_rank is not None and not (0 <= max_specificity_rank <= MAX_SPECIFICITY_RANK):
            return f"Invalid max_specificity_rank {max_specificity_rank}. Valid: 0-{MAX_SPECIFICITY_RANK}."
        if not (1 <= member_limit <= 200):
            return f"Invalid member_limit {member_limit}. Valid: 1-200."

        # 1. Query gene metadata
        cypher_gene, params_gene = build_gene_stub(gene_id=gene_id)
        gene_rows = conn.execute_query(cypher_gene, **params_gene)
        if not gene_rows:
            return f"Gene '{gene_id}' not found."
        query_gene = gene_rows[0]

        # 2. Query ortholog groups
        cypher_groups, params_groups = build_get_homologs_groups(
            gene_id=gene_id, source=source,
            taxonomic_level=taxonomic_level,
            max_specificity_rank=max_specificity_rank,
        )
        groups = conn.execute_query(cypher_groups, **params_groups)
        if not groups:
            return _with_query(
                _no_groups_msg(gene_id, source, taxonomic_level, max_specificity_rank),
                cypher_groups, params_groups, ctx,
            )

        # 3. Optionally fetch members
        if include_members:
            cypher_members, params_members = build_get_homologs_members(
                gene_id=gene_id, source=source,
                taxonomic_level=taxonomic_level,
                max_specificity_rank=max_specificity_rank,
                exclude_paralogs=exclude_paralogs,
            )
            members = conn.execute_query(cypher_members, **params_members)

            # Group members by og_name, apply per-group limit
            from collections import defaultdict
            members_by_og = defaultdict(list)
            for m in members:
                members_by_og[m.pop("og_name")].append(m)

            for g in groups:
                og_members = members_by_og.get(g["og_name"], [])
                if len(og_members) > member_limit:
                    g["members"] = og_members[:member_limit]
                    g["truncated"] = True
                else:
                    g["members"] = og_members

        response = json.dumps(
            {"query_gene": query_gene, "ortholog_groups": groups},
            indent=2, default=str,
        )

        # Debug: attach all queries
        if _debug(ctx):
            queries = [{"cypher": cypher_groups, "params": params_groups}]
            if include_members:
                queries.append({"cypher": cypher_members, "params": params_members})
            debug_block = json.dumps({"_debug": {"queries": queries}}, indent=2, default=str)
            return f"{debug_block}\n---\n{response}"

        return response

    @mcp.tool()
    def run_cypher(ctx: Context, query: str, limit: int = 25) -> str:
        """Execute a raw Cypher query against the knowledge graph (read-only).

        Use this as an escape hatch when the other tools don't cover your query.
        Write operations are blocked (regex keyword filter + read-only transaction).

        Args:
            query: Cypher query string. A LIMIT clause will be added if not present.
            limit: Max results (default 25, max 200).
        """
        # Block write operations
        if _WRITE_KEYWORDS.search(query):
            return "Error: write operations are not allowed. This tool is read-only."

        limit = min(limit, 200)

        # Add LIMIT if not present
        if not re.search(r"\bLIMIT\b", query, re.IGNORECASE):
            query = query.rstrip().rstrip(";")
            query += f"\nLIMIT {limit}"

        conn = _conn(ctx)
        results = conn.execute_query(query)
        if not results:
            return "Query returned no results."
        return _fmt(results, limit=limit)

    @mcp.tool()
    def search_ontology(
        ctx: Context,
        search_text: str,
        ontology: str,
        limit: int = 25,
    ) -> str:
        """Browse ontology terms by text search (fuzzy, Lucene syntax).

        Use this to discover ontology term IDs, then pass them to
        genes_by_ontology to find genes.

        Supports Lucene query syntax: fuzzy matching (~), wildcards (*),
        exact phrases ("..."), boolean operators (AND, OR).

        Args:
            search_text: Search query against term names. Examples:
                "DNA replication" — phrase match
                "replicat~" — fuzzy match
                "oxido*" — wildcard
                "transport AND membrane" — boolean
            ontology: Which ontology to search. One of:
                "go_bp" (biological process), "go_mf" (molecular function),
                "go_cc" (cellular component), "kegg", "ec",
                "cog_category" (COG functional categories),
                "cyanorak_role" (Cyanorak functional roles),
                "tigr_role" (TIGR functional roles),
                "pfam" (Pfam protein domains and clans).
                For KEGG, searches across all levels — level is encoded in
                the returned ID prefix:
                  kegg.category:    (e.g. "Metabolism")
                  kegg.subcategory: (e.g. "Carbohydrate metabolism")
                  kegg.pathway:     (e.g. "Glycolysis")
                  kegg.orthology:   (e.g. "K00001 alcohol dehydrogenase")
            limit: Max results (default 25).
        """
        conn = _conn(ctx)
        cypher, params = build_search_ontology(
            ontology=ontology, search_text=search_text,
        )
        try:
            results = conn.execute_query(cypher, **params)
        except Neo4jClientError:
            # Retry with escaped Lucene special characters
            escaped = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', r'\\\g<0>', search_text)
            cypher, params = build_search_ontology(
                ontology=ontology, search_text=escaped,
            )
            results = conn.execute_query(cypher, **params)
        results = results[:limit]
        if not results:
            response = json.dumps({
                "results": [], "total": 0, "query": search_text,
            })
        else:
            response = json.dumps({
                "results": results, "total": len(results), "query": search_text,
            }, indent=2, default=str)
        return _with_query(response, cypher, params, ctx)

    @mcp.tool()
    def genes_by_ontology(
        ctx: Context,
        term_ids: list[str],
        ontology: str,
        organism: str | None = None,
        limit: int = 25,
    ) -> str:
        """Find genes annotated to ontology terms, with hierarchy expansion.

        Takes ontology term IDs (from search_ontology) and finds all genes
        annotated to those terms or any of their descendant terms in the
        ontology hierarchy.

        Args:
            term_ids: One or more ontology term IDs (from search_ontology).
            ontology: Which ontology the IDs belong to. One of:
                "go_bp" (biological process), "go_mf" (molecular function),
                "go_cc" (cellular component), "kegg", "ec",
                "cog_category", "cyanorak_role", "tigr_role", "pfam".
            organism: Optional organism filter (fuzzy match on strain name).
            limit: Max gene results (default 25).
        """
        conn = _conn(ctx)
        cypher, params = build_genes_by_ontology(
            ontology=ontology, term_ids=term_ids,
            organism=organism,
        )
        results = conn.execute_query(cypher, **params)
        results = results[:limit]
        if not results:
            response = json.dumps({"results": {}, "total": 0})
        else:
            grouped = _group_by_organism(results)
            response = json.dumps(
                {"results": grouped, "total": len(results)},
                indent=2, default=str,
            )
        return _with_query(response, cypher, params, ctx)

    @mcp.tool()
    def gene_ontology_terms(
        ctx: Context,
        gene_id: str,
        ontology: str,
        leaf_only: bool = True,
        limit: int = 50,
    ) -> str:
        """Get ontology annotations for a gene.

        Returns the ontology terms a gene is annotated to. By default returns
        only the most specific (leaf) terms — those that are not ancestors of
        other terms the gene is annotated to.

        Args:
            gene_id: Gene locus_tag (e.g. "PMM0001").
            ontology: Which ontology to return. One of:
                "go_bp" (biological process), "go_mf" (molecular function),
                "go_cc" (cellular component), "kegg", "ec",
                "cog_category", "cyanorak_role", "tigr_role", "pfam".
            leaf_only: If True (default), return only the most specific terms.
                If False, return all annotations.
            limit: Max results (default 50). Relevant mainly with
                leaf_only=False, which can return many ancestor terms.
        """
        conn = _conn(ctx)
        cypher, params = build_gene_ontology_terms(
            ontology=ontology, gene_id=gene_id,
            leaf_only=leaf_only,
        )
        results = conn.execute_query(cypher, **params)
        results = results[:limit]
        if not results:
            response = json.dumps({"results": [], "total": 0})
        else:
            response = json.dumps({
                "results": results, "total": len(results),
            }, indent=2, default=str)
        return _with_query(response, cypher, params, ctx)
