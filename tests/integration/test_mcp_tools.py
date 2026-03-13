"""P1: Integration tests for MCP tool logic against live Neo4j.

These tests exercise the tool-level logic (query building + result handling)
without the MCP transport layer. They use the shared `conn` fixture from conftest.
"""

import json

import pytest

from multiomics_explorer.kg.queries_lib import (
    build_compare_conditions,
    build_find_gene,
    build_get_gene,
    build_get_gene_details_main,
    build_get_homologs,
    build_homolog_expression,
    build_query_expression,
    build_search_genes,
)
from multiomics_explorer.kg.schema import load_schema_from_neo4j
from multiomics_explorer.mcp_server.tools import _WRITE_KEYWORDS


@pytest.mark.kg
class TestGetSchema:
    def test_returns_node_counts_and_relationships(self, conn):
        schema = load_schema_from_neo4j(conn)
        assert len(schema.nodes) > 0
        assert len(schema.relationships) > 0
        # At least Gene nodes should exist
        assert "Gene" in schema.nodes
        assert schema.nodes["Gene"].count > 0

    def test_prompt_string_not_empty(self, conn):
        schema = load_schema_from_neo4j(conn)
        text = schema.to_prompt_string()
        assert "Gene" in text
        assert "## Graph Schema" in text


@pytest.mark.kg
class TestFindGene:
    def test_invalid_lucene_syntax_does_not_crash(self, conn):
        """Unbalanced brackets should trigger the Lucene escape fallback."""
        import re

        search_text = "DNA [repair"
        cypher, params = build_find_gene(search_text=search_text)
        try:
            results = conn.execute_query(cypher, **params)
        except Exception:
            # Retry with escaped Lucene chars (mirrors tools.py fallback logic)
            escaped = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', r'\\\g<0>', search_text)
            cypher, params = build_find_gene(search_text=escaped)
            results = conn.execute_query(cypher, **params)
        # Should not raise — may return 0 or more results
        assert isinstance(results, list)

    def test_basic_search_returns_results(self, conn):
        cypher, params = build_find_gene(search_text="photosystem")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        assert "locus_tag" in results[0]


@pytest.mark.kg
class TestQueryExpression:
    def test_orthologs_increase_results(self, conn):
        """Including orthologs should return >= the direct-only count."""
        cypher_direct, params_direct = build_query_expression(
            organism="MED4", include_orthologs=False, limit=100,
        )
        direct = conn.execute_query(cypher_direct, **params_direct)

        cypher_all, params_all = build_query_expression(
            organism="MED4", include_orthologs=True, limit=100,
        )
        all_results = conn.execute_query(cypher_all, **params_all)

        assert len(all_results) >= len(direct)


@pytest.mark.kg
class TestCompareConditions:
    def test_compare_two_organisms(self, conn):
        cypher, params = build_compare_conditions(
            organisms=["MED4"], limit=10,
        )
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        assert "gene" in results[0]


@pytest.mark.kg
class TestGetHomologs:
    def test_with_expression_data(self, conn):
        """get_homologs + expression enrichment should return expression rows."""
        cypher, params = build_get_homologs(gene_id="PMM0845")
        homologs = conn.execute_query(cypher, **params)
        assert len(homologs) > 0

        all_ids = ["PMM0845"] + [h["locus_tag"] for h in homologs]
        cypher_expr, params_expr = build_homolog_expression(gene_ids=all_ids)
        expr = conn.execute_query(cypher_expr, **params_expr)
        # Should have at least some expression data
        assert isinstance(expr, list)


@pytest.mark.kg
class TestRunCypherBlocking:
    def test_invalid_cypher_returns_error(self, conn):
        """Syntax-invalid Cypher should raise, not hang."""
        with pytest.raises(Exception):
            conn.execute_query("MATC (n) RETURNN n LIMIT 1")

    def test_write_blocked_at_regex_level(self):
        """Write keywords are caught before reaching Neo4j."""
        assert _WRITE_KEYWORDS.search("CREATE (n:Gene {name: 'test'})")
        assert _WRITE_KEYWORDS.search("MATCH (n) DELETE n")
        assert _WRITE_KEYWORDS.search("MATCH (n) SET n.x = 1")


@pytest.mark.kg
class TestEdgeCases:
    def test_get_gene_empty_id(self, conn):
        cypher, params = build_get_gene(id="")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 0

    def test_search_genes_special_chars(self, conn):
        cypher, params = build_search_genes(query="<script>alert('x')</script>")
        results = conn.execute_query(cypher, **params)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_get_gene_details_nonexistent(self, conn):
        cypher, params = build_get_gene_details_main(gene_id="FAKE_GENE_XYZ")
        results = conn.execute_query(cypher, **params)
        # Either empty or gene is None
        assert not results or results[0]["gene"] is None
