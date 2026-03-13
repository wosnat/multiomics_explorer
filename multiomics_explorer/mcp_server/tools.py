"""MCP tool implementations for the Multiomics Knowledge Graph."""

import json
import re

from mcp.server.fastmcp import Context, FastMCP

from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.queries_lib import (
    build_compare_conditions,
    build_find_gene,
    build_get_gene,
    build_get_gene_details_homologs,
    build_get_gene_details_main,
    build_get_homologs,
    build_homolog_expression,
    build_query_expression,
    build_search_genes,
)


def _conn(ctx: Context) -> GraphConnection:
    """Get the Neo4j connection from lifespan context."""
    return ctx.request_context.lifespan_context.conn


def _fmt(results: list[dict], limit: int | None = None) -> str:
    """Format query results as JSON string."""
    if limit:
        results = results[:limit]
    return json.dumps(results, indent=2, default=str)


# Read-only keywords check for raw Cypher
_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|CALL\s*\{)\b",
    re.IGNORECASE,
)


def register_tools(mcp: FastMCP):
    """Register all KG tools with the MCP server."""

    @mcp.tool()
    def get_schema(ctx) -> str:
        """Get the knowledge graph schema: node types with counts, relationship types with
        source/target labels, and property names. Use this first to understand what's queryable."""
        from multiomics_explorer.kg.schema import load_schema_from_neo4j

        conn = _conn(ctx)
        schema = load_schema_from_neo4j(conn)
        return schema.to_prompt_string()

    @mcp.tool()
    def get_gene(
        ctx,
        id: str,
        organism: str | None = None,
    ) -> str:
        """Look up a gene by any known identifier: locus_tag, gene_name, old locus tag,
        RefSeq protein ID, etc. Returns up to 5 matches (specify organism to narrow).

        Args:
            id: Gene identifier — locus_tag (e.g. "PMM0001"), gene name (e.g. "dnaN"),
                old locus tag, or RefSeq protein ID.
            organism: Optional organism filter (e.g. "MED4", "Prochlorococcus MED4").
        """
        conn = _conn(ctx)
        cypher, params = build_get_gene(id=id, organism=organism)
        results = conn.execute_query(cypher, **params)
        if not results:
            msg = f"No gene found for id '{id}'"
            if organism:
                msg += f" in {organism}"
            return json.dumps({"results": [], "message": msg})
        if len(results) > 1:
            return json.dumps({
                "results": results,
                "message": f"Ambiguous — {len(results)} matches found. Specify organism to narrow.",
            }, indent=2, default=str)
        return json.dumps({"results": results}, indent=2, default=str)

    @mcp.tool()
    def find_gene(
        ctx,
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
            min_quality: Minimum annotation_quality (0-3). Use 2 to skip hypothetical proteins.
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
        except Exception:
            # Retry with escaped Lucene special characters
            escaped = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', r'\\\g<0>', search_text)
            cypher, params = build_find_gene(
                search_text=escaped, organism=organism,
                min_quality=min_quality, limit=limit,
            )
            results = conn.execute_query(cypher, **params)
        if not results:
            return json.dumps({
                "results": [], "total": 0, "query": search_text,
            })
        return json.dumps({
            "results": results, "total": len(results), "query": search_text,
        }, indent=2, default=str)

    @mcp.tool()
    def search_genes(
        ctx,
        query: str,
        organism: str | None = None,
        limit: int = 20,
    ) -> str:
        """Search for genes by locus_tag, gene name, or product keyword (CONTAINS match).
        For richer free-text search, use find_gene instead.

        Args:
            query: Search term — locus_tag (e.g. "PMM0001"), gene name (e.g. "psbA"),
                   or product keyword (e.g. "photosystem"). Case-insensitive.
            organism: Optional strain name filter (e.g. "MED4", "MIT9313").
            limit: Max results (default 20).
        """
        conn = _conn(ctx)
        cypher, params = build_search_genes(query=query, organism=organism, limit=limit)
        results = conn.execute_query(cypher, **params)
        if not results:
            msg = f"No genes found matching '{query}'"
            if organism:
                msg += f" in {organism}"
            return json.dumps({"results": [], "message": msg})
        return _fmt(results)

    @mcp.tool()
    def get_gene_details(ctx, gene_id: str) -> str:
        """Get full details for a gene: properties, protein, organism, Cyanorak cluster,
        and homolog summary.

        Args:
            gene_id: Gene locus_tag (e.g. "PMM0001", "sync_0001").
        """
        conn = _conn(ctx)

        # Main gene + protein + organism
        cypher, params = build_get_gene_details_main(gene_id=gene_id)
        main = conn.execute_query(cypher, **params)
        if not main or main[0]["gene"] is None:
            return f"Gene '{gene_id}' not found."

        # Homolog summary
        cypher, params = build_get_gene_details_homologs(gene_id=gene_id)
        homologs = conn.execute_query(cypher, **params)

        result = main[0]["gene"]
        result["_homologs"] = homologs
        return _fmt([result])

    @mcp.tool()
    def query_expression(
        ctx,
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
            return "No expression data found for the given filters."
        return _fmt(results)

    @mcp.tool()
    def compare_conditions(
        ctx,
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
            conditions: List of source names (coculture organism_name or condition_type).
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
            return "No expression data found for the given filters."
        return _fmt(results)

    @mcp.tool()
    def get_homologs(
        ctx,
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
            return f"No homologs found for '{gene_id}'."

        if include_expression:
            all_ids = [gene_id] + [h["locus_tag"] for h in homologs]
            cypher, params = build_homolog_expression(gene_ids=all_ids)
            expr = conn.execute_query(cypher, **params)
            return json.dumps(
                {"homologs": homologs, "expression": expr},
                indent=2,
                default=str,
            )

        return _fmt(homologs)

    @mcp.tool()
    def run_cypher(ctx, query: str, limit: int = 25) -> str:
        """Execute a raw Cypher query against the knowledge graph (read-only).

        Use this as an escape hatch when the other tools don't cover your query.
        Write operations are blocked.

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
