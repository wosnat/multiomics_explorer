"""MCP tool implementations for the Multiomics Knowledge Graph."""

import json
import re

from mcp.server.fastmcp import Context, FastMCP

from neo4j.exceptions import ClientError as Neo4jClientError

from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.queries_lib import (
    build_compare_conditions,
    build_find_gene,
    build_resolve_gene,
    build_get_gene_details_homologs,
    build_get_gene_details_main,
    build_get_homologs,
    build_homolog_expression,
    build_query_expression,
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
            grouped: dict[str, list[dict]] = {}
            for row in results:
                org = row.get("organism_strain", "Unknown")
                entry = {k: v for k, v in row.items() if k != "organism_strain"}
                grouped.setdefault(org, []).append(entry)
            response = json.dumps(
                {"results": grouped, "total": len(results)},
                indent=2, default=str,
            )
        return _with_query(response, cypher, params, ctx)

    @mcp.tool()
    def find_gene(
        ctx: Context,
        search_text: str,
        organism: str | None = None,
        min_quality: int = 0,
        limit: int = 10,
    ) -> str:
        """Free-text search across gene functional annotations using full-text index.
        Supports Lucene syntax: "DNA repair", nitrogen AND transport, iron*, dnaN~.

        Args:
            search_text: Free-text query (Lucene syntax supported).
            organism: Optional organism filter (e.g. "MED4", "Prochlorococcus MED4").
            min_quality: Minimum annotation_quality (0-3).
                0 = hypothetical, no function info;
                1 = hypothetical but has function description;
                2 = real product name;
                3 = well-annotated (product + GO/KEGG/EC/Pfam).
                Use 2 to skip hypothetical proteins.
            limit: Max results (default 10, max 50).
        """
        conn = _conn(ctx)
        limit = min(limit, 50)
        cypher, params = build_find_gene(
            search_text=search_text, organism=organism,
            min_quality=min_quality, limit=limit,
        )
        try:
            results = conn.execute_query(cypher, **params)
        except Neo4jClientError:
            # Retry with escaped Lucene special characters
            escaped = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', r'\\\g<0>', search_text)
            cypher, params = build_find_gene(
                search_text=escaped, organism=organism,
                min_quality=min_quality, limit=limit,
            )
            results = conn.execute_query(cypher, **params)
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
    def get_gene_details(ctx: Context, gene_id: str) -> str:
        """Get full details for a gene: properties, protein, organism, Cyanorak cluster,
        and homolog summary.

        Args:
            gene_id: Gene locus_tag (e.g. "PMM0001", "sync_0001").
        """
        conn = _conn(ctx)

        # Main gene + protein + organism
        cypher_main, params_main = build_get_gene_details_main(gene_id=gene_id)
        main = conn.execute_query(cypher_main, **params_main)
        if not main or main[0]["gene"] is None:
            return f"Gene '{gene_id}' not found."

        # Homolog summary
        cypher_hom, params_hom = build_get_gene_details_homologs(gene_id=gene_id)
        homologs = conn.execute_query(cypher_hom, **params_hom)

        result = main[0]["gene"]
        result["_homologs"] = homologs
        response = _fmt([result])
        if _debug(ctx):
            queries = [
                {"cypher": cypher_main, "params": params_main},
                {"cypher": cypher_hom, "params": params_hom},
            ]
            debug_block = json.dumps({"_debug": {"queries": queries}}, indent=2, default=str)
            return f"{debug_block}\n---\n{response}"
        return response

    @mcp.tool()
    def query_expression(
        ctx: Context,
        gene_id: str | None = None,
        organism: str | None = None,
        condition: str | None = None,
        direction: str | None = None,
        min_log2fc: float | None = None,
        max_pvalue: float | None = None,
        include_orthologs: bool = False,
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
            include_orthologs: If True, also include ortholog-inferred expression edges.
            limit: Max results (default 50).
        """
        if not any([gene_id, organism, condition]):
            return "Error: provide at least one of gene_id, organism, or condition."

        conn = _conn(ctx)
        cypher, params = build_query_expression(
            gene_id=gene_id, organism=organism, condition=condition,
            direction=direction, min_log2fc=min_log2fc, max_pvalue=max_pvalue,
            include_orthologs=include_orthologs, limit=limit,
        )
        results = conn.execute_query(cypher, **params)
        if not results:
            return _with_query("No expression data found for the given filters.", cypher, params, ctx)
        return _with_query(_fmt(results), cypher, params, ctx)

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
            conditions=conditions, limit=limit,
        )
        results = conn.execute_query(cypher, **params)
        if not results:
            return _with_query("No expression data found for the given filters.", cypher, params, ctx)
        return _with_query(_fmt(results), cypher, params, ctx)

    @mcp.tool()
    def get_homologs(
        ctx: Context,
        gene_id: str,
        include_expression: bool = False,
    ) -> str:
        """Find homologs of a gene across strains, with optional expression data.

        Args:
            gene_id: Gene locus_tag (e.g. "PMM0001").
            include_expression: If True, also return direct expression data for each homolog.
        """
        conn = _conn(ctx)

        cypher, params = build_get_homologs(gene_id=gene_id)
        homologs = conn.execute_query(cypher, **params)
        if not homologs:
            return _with_query(f"No homologs found for '{gene_id}'.", cypher, params, ctx)

        if include_expression:
            all_ids = [gene_id] + [h["locus_tag"] for h in homologs]
            cypher_expr, params_expr = build_homolog_expression(gene_ids=all_ids)
            expr = conn.execute_query(cypher_expr, **params_expr)
            response = json.dumps(
                {"homologs": homologs, "expression": expr},
                indent=2,
                default=str,
            )
            if _debug(ctx):
                queries = [
                    {"cypher": cypher, "params": params},
                    {"cypher": cypher_expr, "params": params_expr},
                ]
                debug_block = json.dumps({"_debug": {"queries": queries}}, indent=2, default=str)
                return f"{debug_block}\n---\n{response}"
            return response

        return _with_query(_fmt(homologs), cypher, params, ctx)

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
