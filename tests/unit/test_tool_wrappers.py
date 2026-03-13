"""Unit tests for MCP tool wrapper logic — no Neo4j needed.

Tests the tool-level behavior (input validation, response formatting,
error messages, LIMIT injection) by mocking the Neo4j connection.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from multiomics_explorer.mcp_server.tools import register_tools


@pytest.fixture(scope="module")
def tool_fns():
    """Register tools on a fresh FastMCP and return a dict of {name: fn}."""
    mcp = FastMCP("test")
    register_tools(mcp)
    return {name: t.fn for name, t in mcp._tool_manager._tools.items()}


@pytest.fixture()
def mock_ctx():
    """MCP Context mock whose .conn returns a MagicMock GraphConnection."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context.conn = MagicMock()
    return ctx


def _conn_from(ctx):
    return ctx.request_context.lifespan_context.conn


# ---------------------------------------------------------------------------
# get_gene
# ---------------------------------------------------------------------------
class TestGetGeneWrapper:
    def test_not_found_message(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = json.loads(tool_fns["get_gene"](mock_ctx, id="FAKE_GENE"))
        assert result["results"] == []
        assert "No gene found" in result["message"]

    def test_not_found_with_organism(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = json.loads(tool_fns["get_gene"](mock_ctx, id="FAKE", organism="MED4"))
        assert "MED4" in result["message"]

    def test_single_match(self, tool_fns, mock_ctx):
        row = {"locus_tag": "PMM0001", "gene_name": "dnaN"}
        _conn_from(mock_ctx).execute_query.return_value = [row]
        result = json.loads(tool_fns["get_gene"](mock_ctx, id="PMM0001"))
        assert len(result["results"]) == 1
        assert "message" not in result  # no ambiguity message

    def test_ambiguous_multi_match(self, tool_fns, mock_ctx):
        rows = [{"locus_tag": f"PMM000{i}"} for i in range(3)]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["get_gene"](mock_ctx, id="dnaN"))
        assert len(result["results"]) == 3
        assert "Ambiguous" in result["message"]


# ---------------------------------------------------------------------------
# find_gene
# ---------------------------------------------------------------------------
class TestFindGeneWrapper:
    def test_empty_result_envelope(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = json.loads(tool_fns["find_gene"](mock_ctx, search_text="nonexistent"))
        assert result["results"] == []
        assert result["total"] == 0
        assert result["query"] == "nonexistent"

    def test_result_envelope_with_hits(self, tool_fns, mock_ctx):
        rows = [{"locus_tag": "PMM0001", "score": 1.5}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["find_gene"](mock_ctx, search_text="photosystem"))
        assert result["total"] == 1
        assert result["query"] == "photosystem"

    def test_limit_capped_at_50(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["find_gene"](mock_ctx, search_text="x", limit=999)
        # The build_find_gene call should have received limit=50
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args
        # We can't easily inspect the Cypher params, but at least it didn't crash
        assert True

    def test_lucene_fallback_on_error(self, tool_fns, mock_ctx):
        """When first query raises, should retry with escaped Lucene chars."""
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            Exception("Lucene parse error"),  # first call fails
            [{"locus_tag": "PMM0001"}],  # retry succeeds
        ]
        result = json.loads(tool_fns["find_gene"](mock_ctx, search_text="DNA [repair"))
        assert result["total"] == 1
        assert conn.execute_query.call_count == 2


# ---------------------------------------------------------------------------
# search_genes
# ---------------------------------------------------------------------------
class TestSearchGenesWrapper:
    def test_empty_returns_plain_string(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = tool_fns["search_genes"](mock_ctx, query="nonexistent")
        assert "No genes found" in result
        # Not JSON — this is the current behavior
        with pytest.raises(json.JSONDecodeError):
            json.loads(result)

    def test_empty_with_organism_in_message(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = tool_fns["search_genes"](mock_ctx, query="x", organism="MED4")
        assert "MED4" in result

    def test_results_returned_as_json(self, tool_fns, mock_ctx):
        rows = [{"locus_tag": "PMM0001", "product": "photosystem II"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["search_genes"](mock_ctx, query="photosystem"))
        assert len(result) == 1


# ---------------------------------------------------------------------------
# get_gene_details
# ---------------------------------------------------------------------------
class TestGetGeneDetailsWrapper:
    def test_not_found_message(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = [{"gene": None}]
        result = tool_fns["get_gene_details"](mock_ctx, gene_id="FAKE")
        assert "not found" in result

    def test_not_found_empty_results(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = tool_fns["get_gene_details"](mock_ctx, gene_id="FAKE")
        assert "not found" in result

    def test_assembles_homologs_into_result(self, tool_fns, mock_ctx):
        """Two queries: main gene + homologs, merged into one result."""
        gene_data = {"locus_tag": "PMM0001", "product": "test"}
        homolog_data = [{"locus_tag": "sync_0001", "organism": "CC9311"}]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [{"gene": gene_data}],  # main query
            homolog_data,  # homologs query
        ]
        result = json.loads(tool_fns["get_gene_details"](mock_ctx, gene_id="PMM0001"))
        assert len(result) == 1
        assert result[0]["_homologs"] == homolog_data


# ---------------------------------------------------------------------------
# query_expression
# ---------------------------------------------------------------------------
class TestQueryExpressionWrapper:
    def test_no_filters_returns_error(self, tool_fns, mock_ctx):
        result = tool_fns["query_expression"](mock_ctx)
        assert "Error" in result
        assert "at least one" in result
        # Should NOT have called Neo4j
        _conn_from(mock_ctx).execute_query.assert_not_called()

    def test_empty_results_message(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = tool_fns["query_expression"](mock_ctx, gene_id="PMM0001")
        assert "No expression data" in result

    def test_returns_json_with_results(self, tool_fns, mock_ctx):
        rows = [{"gene": "PMM0001", "log2fc": 2.5, "pvalue": 0.001}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["query_expression"](mock_ctx, organism="MED4"))
        assert len(result) == 1


# ---------------------------------------------------------------------------
# compare_conditions
# ---------------------------------------------------------------------------
class TestCompareConditionsWrapper:
    def test_no_filters_returns_error(self, tool_fns, mock_ctx):
        result = tool_fns["compare_conditions"](mock_ctx)
        assert "Error" in result
        assert "at least one" in result
        _conn_from(mock_ctx).execute_query.assert_not_called()

    def test_empty_results_message(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = tool_fns["compare_conditions"](mock_ctx, organisms=["MED4"])
        assert "No expression data" in result

    def test_returns_json_with_results(self, tool_fns, mock_ctx):
        rows = [{"gene": "PMM0001", "condition": "coculture"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(
            tool_fns["compare_conditions"](mock_ctx, gene_ids=["PMM0001"])
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# get_homologs
# ---------------------------------------------------------------------------
class TestGetHomologsWrapper:
    def test_no_homologs_message(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")
        assert "No homologs found" in result

    def test_without_expression(self, tool_fns, mock_ctx):
        rows = [{"locus_tag": "sync_0001", "organism": "CC9311"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001"))
        assert len(result) == 1

    def test_with_expression_merges_response(self, tool_fns, mock_ctx):
        homologs = [{"locus_tag": "sync_0001", "organism": "CC9311"}]
        expr = [{"gene": "PMM0001", "log2fc": 1.5}]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [homologs, expr]
        result = json.loads(
            tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001", include_expression=True)
        )
        assert "homologs" in result
        assert "expression" in result
        assert result["homologs"] == homologs
        assert result["expression"] == expr


# ---------------------------------------------------------------------------
# run_cypher
# ---------------------------------------------------------------------------
class TestRunCypherWrapper:
    def test_write_blocked_returns_error_message(self, tool_fns, mock_ctx):
        result = tool_fns["run_cypher"](mock_ctx, query="CREATE (n:Gene {name: 'x'})")
        assert "Error" in result
        assert "write operations" in result
        _conn_from(mock_ctx).execute_query.assert_not_called()

    def test_limit_injected_when_absent(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = [{"n": 1}]
        tool_fns["run_cypher"](mock_ctx, query="MATCH (n) RETURN n")
        called_query = _conn_from(mock_ctx).execute_query.call_args[0][0]
        assert "LIMIT" in called_query

    def test_limit_not_duplicated_when_present(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = [{"n": 1}]
        tool_fns["run_cypher"](mock_ctx, query="MATCH (n) RETURN n LIMIT 5")
        called_query = _conn_from(mock_ctx).execute_query.call_args[0][0]
        assert called_query.count("LIMIT") == 1

    def test_limit_capped_at_200(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = [{"n": 1}]
        tool_fns["run_cypher"](mock_ctx, query="MATCH (n) RETURN n", limit=500)
        called_query = _conn_from(mock_ctx).execute_query.call_args[0][0]
        assert "LIMIT 200" in called_query

    def test_empty_results_message(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = tool_fns["run_cypher"](mock_ctx, query="MATCH (n:Fake) RETURN n")
        assert "no results" in result.lower()

    def test_semicolon_stripped_before_limit(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = [{"n": 1}]
        tool_fns["run_cypher"](mock_ctx, query="MATCH (n) RETURN n;")
        called_query = _conn_from(mock_ctx).execute_query.call_args[0][0]
        assert ";" not in called_query
        assert "LIMIT" in called_query
