"""MCP tool implementations for the Multiomics Knowledge Graph."""

import json
import re

from mcp.server.fastmcp import Context, FastMCP

from multiomics_explorer.kg.connection import GraphConnection


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
    def search_genes(
        ctx,
        query: str,
        organism: str | None = None,
        limit: int = 20,
    ) -> str:
        """Search for genes by locus_tag, gene name, or product keyword.

        Args:
            query: Search term — locus_tag (e.g. "PMM0001"), gene name (e.g. "psbA"),
                   or product keyword (e.g. "photosystem"). Case-insensitive.
            organism: Optional strain name filter (e.g. "MED4", "MIT9313").
            limit: Max results (default 20).
        """
        conn = _conn(ctx)

        where_clauses = [
            "(g.locus_tag CONTAINS $q OR "
            "toLower(g.product) CONTAINS toLower($q) OR "
            "any(name IN g.gene_names WHERE toLower(name) CONTAINS toLower($q)))"
        ]
        params: dict = {"q": query, "limit": limit}

        if organism:
            where_clauses.append("o.strain_name = $strain")
            params["strain"] = organism

        where = " AND ".join(where_clauses)
        cypher = (
            "MATCH (g:Gene)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)\n"
            f"WHERE {where}\n"
            "RETURN g.locus_tag AS locus_tag, g.gene_names AS gene_names,\n"
            "       g.product AS product, o.strain_name AS strain,\n"
            "       g.protein_id AS protein_id\n"
            "ORDER BY g.locus_tag\n"
            "LIMIT $limit"
        )
        results = conn.execute_query(cypher, **params)
        if not results:
            return f"No genes found matching '{query}'" + (
                f" in {organism}" if organism else ""
            )
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
        main = conn.execute_query(
            "MATCH (g:Gene {locus_tag: $lt})\n"
            "OPTIONAL MATCH (g)<-[:Gene_encodes_protein]-(p:Protein)\n"
            "OPTIONAL MATCH (g)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)\n"
            "OPTIONAL MATCH (g)-[:Gene_in_cyanorak_cluster]->(c:Cyanorak_cluster)\n"
            "RETURN g {.*, _protein: p {.protein_name, .function, .go_terms, .ec_numbers,\n"
            "           .subcellular_location, .refseq_ids},\n"
            "       _organism: o {.strain_name, .genus, .clade, .ncbi_taxon_id},\n"
            "       _cluster: c {.cluster_number}} AS gene",
            lt=gene_id,
        )
        if not main or main[0]["gene"] is None:
            return f"Gene '{gene_id}' not found."

        # Homolog count
        homologs = conn.execute_query(
            "MATCH (g:Gene {locus_tag: $lt})-[h:Gene_is_homolog_of_gene]-(other:Gene)\n"
            "OPTIONAL MATCH (other)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)\n"
            "RETURN other.locus_tag AS locus_tag, o.strain_name AS strain,\n"
            "       h.distance AS distance, h.cluster_id AS cluster_id\n"
            "ORDER BY h.distance\n"
            "LIMIT 20",
            lt=gene_id,
        )

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
        limit: int = 50,
    ) -> str:
        """Query differential expression data from the knowledge graph.

        At least one of gene_id, organism, or condition must be provided.

        Args:
            gene_id: Filter by gene locus_tag (e.g. "PMM0001").
            organism: Filter by target organism strain (e.g. "MED4") — the organism
                      whose genes are affected.
            condition: Filter by expression source — coculture partner genus
                       (e.g. "Alteromonas") or environmental condition name/type
                       (e.g. "nitrogen starvation", "iron limitation").
            direction: Filter by "up" or "down" regulation.
            min_log2fc: Minimum absolute log2 fold change.
            max_pvalue: Maximum adjusted p-value.
            limit: Max results (default 50).
        """
        if not any([gene_id, organism, condition]):
            return "Error: provide at least one of gene_id, organism, or condition."

        conn = _conn(ctx)

        # Build dynamic query
        match_parts = ["MATCH (factor)-[r:Affects_expression_of]->(g:Gene)"]
        where_clauses = []
        params: dict = {"limit": limit}

        if gene_id:
            where_clauses.append("g.locus_tag = $gene_id")
            params["gene_id"] = gene_id

        if organism:
            match_parts.append(
                "MATCH (g)-[:Gene_belongs_to_organism]->(target:OrganismTaxon)"
            )
            where_clauses.append("target.strain_name = $target_strain")
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

        match_block = "\n".join(match_parts)
        where_block = " AND ".join(where_clauses)

        cypher = (
            f"{match_block}\n"
            f"WHERE {where_block}\n"
            "RETURN g.locus_tag AS gene, g.product AS product,\n"
            "       labels(factor) AS source_type,\n"
            "       CASE WHEN factor:OrganismTaxon THEN factor.organism_name\n"
            "            ELSE factor.name END AS source,\n"
            "       r.expression_direction AS direction,\n"
            "       r.log2_fold_change AS log2fc,\n"
            "       r.adjusted_p_value AS padj,\n"
            "       r.control_condition AS control,\n"
            "       r.experimental_context AS context,\n"
            "       r.time_point AS time_point,\n"
            "       r.publications AS publications\n"
            "ORDER BY abs(r.log2_fold_change) DESC\n"
            "LIMIT $limit"
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
            conditions: List of source names (coculture genus or condition type).
            limit: Max results (default 100).
        """
        if not any([gene_ids, organisms, conditions]):
            return "Error: provide at least one of gene_ids, organisms, or conditions."

        conn = _conn(ctx)

        match_parts = [
            "MATCH (factor)-[r:Affects_expression_of]->(g:Gene)"
            "-[:Gene_belongs_to_organism]->(target:OrganismTaxon)"
        ]
        where_clauses = []
        params: dict = {"limit": limit}

        if gene_ids:
            where_clauses.append("g.locus_tag IN $gene_ids")
            params["gene_ids"] = gene_ids

        if organisms:
            where_clauses.append("target.strain_name IN $organisms")
            params["organisms"] = organisms

        if conditions:
            where_clauses.append(
                "CASE WHEN factor:OrganismTaxon "
                "THEN factor.genus IN $conditions "
                "ELSE factor.condition_type IN $conditions END"
            )
            params["conditions"] = conditions

        match_block = "\n".join(match_parts)
        where_block = " AND ".join(where_clauses)

        cypher = (
            f"{match_block}\n"
            f"WHERE {where_block}\n"
            "RETURN g.locus_tag AS gene, g.product AS product,\n"
            "       target.strain_name AS target_strain,\n"
            "       CASE WHEN factor:OrganismTaxon THEN factor.organism_name\n"
            "            ELSE factor.name END AS source,\n"
            "       r.expression_direction AS direction,\n"
            "       r.log2_fold_change AS log2fc,\n"
            "       r.adjusted_p_value AS padj,\n"
            "       r.experimental_context AS context\n"
            "ORDER BY g.locus_tag, source\n"
            "LIMIT $limit"
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
            include_expression: If True, also return expression data for each homolog.
        """
        conn = _conn(ctx)

        homologs = conn.execute_query(
            "MATCH (g:Gene {locus_tag: $lt})-[h:Gene_is_homolog_of_gene]-(other:Gene)\n"
            "OPTIONAL MATCH (other)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)\n"
            "RETURN other.locus_tag AS locus_tag, other.product AS product,\n"
            "       o.strain_name AS strain, o.clade AS clade,\n"
            "       h.distance AS distance, h.cluster_id AS cluster_id\n"
            "ORDER BY h.distance, other.locus_tag",
            lt=gene_id,
        )
        if not homologs:
            return f"No homologs found for '{gene_id}'."

        if include_expression:
            all_ids = [gene_id] + [h["locus_tag"] for h in homologs]
            expr = conn.execute_query(
                "MATCH (factor)-[r:Affects_expression_of]->(g:Gene)\n"
                "WHERE g.locus_tag IN $ids\n"
                "RETURN g.locus_tag AS gene,\n"
                "       CASE WHEN factor:OrganismTaxon THEN factor.organism_name\n"
                "            ELSE factor.name END AS source,\n"
                "       r.expression_direction AS direction,\n"
                "       r.log2_fold_change AS log2fc,\n"
                "       r.adjusted_p_value AS padj\n"
                "ORDER BY g.locus_tag, abs(r.log2_fold_change) DESC",
                ids=all_ids,
            )
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
