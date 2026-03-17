"""P1: Integration tests for MCP tool logic against live Neo4j.

These tests exercise the tool-level logic (query building + result handling)
without the MCP transport layer. They use the shared `conn` fixture from conftest.
"""

import json

import pytest

from multiomics_explorer.kg.queries_lib import (
    build_compare_conditions,
    build_gene_stub,
    build_get_gene_details,
    build_get_homologs_groups,
    build_get_homologs_members,
    build_query_expression,
    build_resolve_gene,
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
class TestSearchGenes:
    def test_invalid_lucene_syntax_does_not_crash(self, conn):
        """Unbalanced brackets should trigger the Lucene escape fallback."""
        import re

        search_text = "DNA [repair"
        cypher, params = build_search_genes(search_text=search_text)
        try:
            results = conn.execute_query(cypher, **params)
        except Exception:
            # Retry with escaped Lucene chars (mirrors tools.py fallback logic)
            escaped = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', r'\\\g<0>', search_text)
            cypher, params = build_search_genes(search_text=escaped)
            results = conn.execute_query(cypher, **params)
        # Should not raise — may return 0 or more results
        assert isinstance(results, list)

    def test_basic_search_returns_results(self, conn):
        cypher, params = build_search_genes(search_text="photosystem")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        assert "locus_tag" in results[0]


@pytest.mark.kg
class TestQueryExpression:
    def test_direct_expression_returns_results(self, conn):
        """Direct expression query for MED4 should return results."""
        cypher, params = build_query_expression(organism="MED4", limit=10)
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0


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
    def test_gene_stub_returns_metadata(self, conn):
        """build_gene_stub returns query gene metadata."""
        cypher, params = build_gene_stub(gene_id="PMM0845")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 1
        assert results[0]["locus_tag"] == "PMM0845"
        assert "gene_name" in results[0]
        assert "product" in results[0]
        assert "organism_strain" in results[0]

    def test_groups_query_returns_ortholog_groups(self, conn):
        """build_get_homologs_groups returns group metadata for PMM0845."""
        cypher, params = build_get_homologs_groups(gene_id="PMM0845")
        groups = conn.execute_query(cypher, **params)
        assert len(groups) > 0
        for g in groups:
            assert "og_name" in g
            assert "source" in g
            assert "consensus_product" in g

    def test_members_query_returns_homolog_genes(self, conn):
        """build_get_homologs_members returns member genes."""
        cypher, params = build_get_homologs_members(gene_id="PMM0845")
        members = conn.execute_query(cypher, **params)
        assert len(members) > 0
        for m in members:
            assert "locus_tag" in m
            assert "og_name" in m
            assert "organism_strain" in m


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
    def test_resolve_gene_empty_id(self, conn):
        cypher, params = build_resolve_gene(identifier="")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 0

    def test_get_gene_details_nonexistent(self, conn):
        cypher, params = build_get_gene_details(gene_id="FAKE_GENE_XYZ")
        results = conn.execute_query(cypher, **params)
        # Either empty or gene is None
        assert not results or results[0]["gene"] is None

    def test_query_expression_conflicting_filters(self, conn):
        """Conflicting filters should return empty results, not crash."""
        cypher, params = build_query_expression(
            gene_id="PMM0001",
            organism="NONEXISTENT_STRAIN_XYZ",
            direction="up",
            min_log2fc=999.0,
            max_pvalue=0.0000001,
        )
        results = conn.execute_query(cypher, **params)
        assert isinstance(results, list)
        assert len(results) == 0
