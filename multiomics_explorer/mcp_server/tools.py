"""MCP tool implementations for the Multiomics Knowledge Graph."""

import json
import re

from mcp.server.fastmcp import Context, FastMCP

from multiomics_explorer.kg.connection import GraphConnection

# Expression relationship types in the current KG schema.
# Direct edges: from the original study organism/condition to the measured gene.
# Ortholog edges: propagated to homologous genes via cluster membership.
_DIRECT_EXPR_RELS = "Condition_changes_expression_of|Coculture_changes_expression_of"
_ORTHOLOG_EXPR_RELS = (
    "Condition_changes_expression_of_ortholog|Coculture_changes_expression_of_ortholog"
)
_ALL_EXPR_RELS = f"{_DIRECT_EXPR_RELS}|{_ORTHOLOG_EXPR_RELS}"


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
        cypher = (
            "MATCH (g:Gene)\n"
            "WHERE (\n"
            "    g.locus_tag = $id\n"
            "    OR g.gene_name = $id\n"
            "    OR $id IN g.all_identifiers\n"
            "  )\n"
            "  AND ($organism IS NULL OR g.organism_strain = $organism)\n"
            "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
            "       g.gene_summary AS gene_summary, g.product AS product,\n"
            "       g.function_description AS function_description,\n"
            "       g.organism_strain AS organism_strain,\n"
            "       g.go_terms AS go_terms, g.kegg_ko AS kegg_ko,\n"
            "       g.annotation_quality AS annotation_quality\n"
            "LIMIT 5"
        )
        results = conn.execute_query(cypher, id=id, organism=organism)
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
        cypher = (
            "CALL db.index.fulltext.queryNodes('geneFullText', $search_text)\n"
            "YIELD node AS g, score\n"
            "WHERE ($organism IS NULL OR g.organism_strain = $organism)\n"
            "  AND ($min_quality = 0 OR g.annotation_quality >= $min_quality)\n"
            "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
            "       g.gene_summary AS gene_summary, g.product AS product,\n"
            "       g.organism_strain AS organism_strain,\n"
            "       g.annotation_quality AS annotation_quality,\n"
            "       score\n"
            "ORDER BY score DESC\n"
            "LIMIT $limit"
        )
        try:
            results = conn.execute_query(
                cypher, search_text=search_text, organism=organism,
                min_quality=min_quality, limit=limit,
            )
        except Exception:
            # Retry with escaped Lucene special characters
            escaped = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', r'\\\g<0>', search_text)
            results = conn.execute_query(
                cypher, search_text=escaped, organism=organism,
                min_quality=min_quality, limit=limit,
            )
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

        where_clauses = [
            "(g.locus_tag CONTAINS $q OR "
            "toLower(g.product) CONTAINS toLower($q) OR "
            "toLower(g.gene_name) CONTAINS toLower($q))"
        ]
        params: dict = {"q": query, "limit": limit}

        if organism:
            where_clauses.append("g.organism_strain CONTAINS $strain")
            params["strain"] = organism

        where = " AND ".join(where_clauses)
        cypher = (
            "MATCH (g:Gene)\n"
            f"WHERE {where}\n"
            "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
            "       g.product AS product, g.organism_strain AS organism_strain\n"
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
            "OPTIONAL MATCH (g)-[:Gene_encodes_protein]->(p:Protein)\n"
            "OPTIONAL MATCH (g)-[:Gene_belongs_to_organism]->(o:OrganismTaxon)\n"
            "OPTIONAL MATCH (g)-[:Gene_in_cyanorak_cluster]->(c:Cyanorak_cluster)\n"
            "RETURN g {.*, _protein: p {.gene_names, .is_reviewed, .annotation_score,\n"
            "           .sequence_length, .refseq_ids},\n"
            "       _organism: o {.preferred_name, .strain_name, .genus, .clade, .ncbi_taxon_id},\n"
            "       _cluster: c {.cluster_number}} AS gene",
            lt=gene_id,
        )
        if not main or main[0]["gene"] is None:
            return f"Gene '{gene_id}' not found."

        # Homolog summary
        homologs = conn.execute_query(
            "MATCH (g:Gene {locus_tag: $lt})-[h:Gene_is_homolog_of_gene]-(other:Gene)\n"
            "RETURN other.locus_tag AS locus_tag, other.organism_strain AS organism_strain,\n"
            "       h.distance AS distance, h.cluster_id AS cluster_id,\n"
            "       h.source AS source\n"
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

        expr_rels = _ALL_EXPR_RELS if include_orthologs else _DIRECT_EXPR_RELS
        match_parts = [f"MATCH (factor)-[r:{expr_rels}]->(g:Gene)"]
        where_clauses = []
        params: dict = {"limit": limit}

        if gene_id:
            where_clauses.append("g.locus_tag = $gene_id")
            params["gene_id"] = gene_id

        if organism:
            where_clauses.append("r.organism_strain CONTAINS $target_strain")
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
            "       type(r) AS edge_type,\n"
            "       CASE WHEN factor:OrganismTaxon THEN factor.organism_name\n"
            "            ELSE factor.name END AS source,\n"
            "       r.expression_direction AS direction,\n"
            "       r.log2_fold_change AS log2fc,\n"
            "       r.adjusted_p_value AS padj,\n"
            "       r.organism_strain AS organism_strain,\n"
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
            conditions: List of source names (coculture organism_name or condition_type).
            limit: Max results (default 100).
        """
        if not any([gene_ids, organisms, conditions]):
            return "Error: provide at least one of gene_ids, organisms, or conditions."

        conn = _conn(ctx)

        match_parts = [
            f"MATCH (factor)-[r:{_DIRECT_EXPR_RELS}]->(g:Gene)"
        ]
        where_clauses = []
        params: dict = {"limit": limit}

        if gene_ids:
            where_clauses.append("g.locus_tag IN $gene_ids")
            params["gene_ids"] = gene_ids

        if organisms:
            where_clauses.append(
                "any(org IN $organisms WHERE r.organism_strain CONTAINS org)"
            )
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
            "       r.organism_strain AS target_strain,\n"
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
            include_expression: If True, also return direct expression data for each homolog.
        """
        conn = _conn(ctx)

        homologs = conn.execute_query(
            "MATCH (g:Gene {locus_tag: $lt})-[h:Gene_is_homolog_of_gene]-(other:Gene)\n"
            "RETURN other.locus_tag AS locus_tag, other.product AS product,\n"
            "       other.organism_strain AS organism_strain,\n"
            "       h.distance AS distance, h.cluster_id AS cluster_id,\n"
            "       h.source AS source\n"
            "ORDER BY h.distance, other.locus_tag",
            lt=gene_id,
        )
        if not homologs:
            return f"No homologs found for '{gene_id}'."

        if include_expression:
            all_ids = [gene_id] + [h["locus_tag"] for h in homologs]
            expr = conn.execute_query(
                f"MATCH (factor)-[r:{_DIRECT_EXPR_RELS}]->(g:Gene)\n"
                "WHERE g.locus_tag IN $ids\n"
                "RETURN g.locus_tag AS gene,\n"
                "       type(r) AS edge_type,\n"
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
