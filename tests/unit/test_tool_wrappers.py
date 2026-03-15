"""Unit tests for MCP tool wrapper logic — no Neo4j needed.

Tests the tool-level behavior (input validation, response formatting,
error messages, LIMIT injection) by mocking the Neo4j connection.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP
from neo4j.exceptions import ClientError as Neo4jClientError

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
    ctx.request_context.lifespan_context.debug_queries = False
    return ctx


def _conn_from(ctx):
    return ctx.request_context.lifespan_context.conn


EXPECTED_TOOLS = [
    "get_schema", "resolve_gene", "search_genes",
    "get_gene_details", "query_expression", "compare_conditions",
    "get_homologs", "run_cypher",
]


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------
class TestToolRegistration:
    def test_all_nine_tools_registered(self, tool_fns):
        assert sorted(tool_fns.keys()) == sorted(EXPECTED_TOOLS)

    def test_no_extra_tools(self, tool_fns):
        assert len(tool_fns) == len(EXPECTED_TOOLS)


# ---------------------------------------------------------------------------
# get_schema
# ---------------------------------------------------------------------------
class TestGetSchemaWrapper:
    def test_returns_prompt_string(self, tool_fns, mock_ctx):
        """get_schema calls load_schema_from_neo4j and returns its prompt string."""
        mock_schema = MagicMock()
        mock_schema.to_prompt_string.return_value = "## Graph Schema\n- Gene (42)"
        with patch(
            "multiomics_explorer.kg.schema.load_schema_from_neo4j",
            return_value=mock_schema,
        ):
            result = tool_fns["get_schema"](mock_ctx)
        assert "Graph Schema" in result
        assert "Gene" in result
        mock_schema.to_prompt_string.assert_called_once()


# ---------------------------------------------------------------------------
# resolve_gene
# ---------------------------------------------------------------------------
class TestResolveGeneWrapper:
    def test_not_found_message(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier="FAKE_GENE"))
        assert result["results"] == {}
        assert "No gene found" in result["message"]

    def test_not_found_with_organism(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier="FAKE", organism="MED4"))
        assert "MED4" in result["message"]

    def test_single_match(self, tool_fns, mock_ctx):
        row = {"locus_tag": "PMM0001", "gene_name": "dnaN", "organism_strain": "Prochlorococcus MED4"}
        _conn_from(mock_ctx).execute_query.return_value = [row]
        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier="PMM0001"))
        assert result["total"] == 1
        assert "Prochlorococcus MED4" in result["results"]

    def test_multi_match_grouped(self, tool_fns, mock_ctx):
        rows = [
            {"locus_tag": "PMM0001", "organism_strain": "Prochlorococcus MED4"},
            {"locus_tag": "PMT9312_0001", "organism_strain": "Prochlorococcus MIT9312"},
            {"locus_tag": "SYNW0305", "organism_strain": "Synechococcus WH8102"},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier="dnaN"))
        assert result["total"] == 3
        assert len(result["results"]) == 3  # 3 organism groups

    def test_same_organism_grouped_together(self, tool_fns, mock_ctx):
        """Multiple genes from the same organism land under one key."""
        rows = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN", "product": "p1", "organism_strain": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0002", "gene_name": "dnaN2", "product": "p2", "organism_strain": "Prochlorococcus MED4"},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier="dnaN"))
        assert result["total"] == 2
        assert len(result["results"]) == 1  # single organism group
        assert len(result["results"]["Prochlorococcus MED4"]) == 2
        # organism_strain should be stripped from individual entries
        for entry in result["results"]["Prochlorococcus MED4"]:
            assert "organism_strain" not in entry

    def test_missing_organism_strain_grouped_as_unknown(self, tool_fns, mock_ctx):
        """Row without organism_strain is grouped under 'Unknown'."""
        rows = [{"locus_tag": "PMM0001", "gene_name": "x", "product": "y"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier="PMM0001"))
        assert "Unknown" in result["results"]

    def test_debug_mode_includes_query(self, tool_fns, mock_ctx):
        """When debug_queries is on, response includes cypher and params."""
        mock_ctx.request_context.lifespan_context.debug_queries = True
        rows = [{"locus_tag": "PMM0001", "gene_name": "dnaN", "organism_strain": "MED4"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        raw = tool_fns["resolve_gene"](mock_ctx, identifier="PMM0001")
        assert "_debug" in raw
        debug_part = raw.split("---")[0]
        debug = json.loads(debug_part)
        assert "cypher" in debug["_debug"]
        assert "params" in debug["_debug"]


# ---------------------------------------------------------------------------
# search_genes
# ---------------------------------------------------------------------------
class TestSearchGenesWrapper:
    def test_empty_result_envelope(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = json.loads(tool_fns["search_genes"](mock_ctx, search_text="nonexistent"))
        assert result["results"] == []
        assert result["total"] == 0
        assert result["query"] == "nonexistent"

    def test_result_envelope_with_hits(self, tool_fns, mock_ctx):
        rows = [{"locus_tag": "PMM0001", "score": 1.5}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["search_genes"](mock_ctx, search_text="photosystem"))
        assert result["total"] == 1
        assert result["query"] == "photosystem"

    def test_limit_capped_at_50(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["search_genes"](mock_ctx, search_text="x", limit=999)
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args
        assert call_kwargs.kwargs["limit"] == 50

    def test_raises_on_double_failure(self, tool_fns, mock_ctx):
        """When both original and escaped queries fail, exception propagates."""
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            Neo4jClientError("parse error"),
            Neo4jClientError("still broken"),
        ]
        with pytest.raises(Neo4jClientError):
            tool_fns["search_genes"](mock_ctx, search_text="bad [query")

    def test_organism_filter_passed_through(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["search_genes"](mock_ctx, search_text="photosystem", organism="MED4")
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["organism"] == "MED4"

    def test_min_quality_passed_through(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["search_genes"](mock_ctx, search_text="photosystem", min_quality=2)
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["min_quality"] == 2

    def test_lucene_fallback_on_error(self, tool_fns, mock_ctx):
        """When first query raises, should retry with escaped Lucene chars."""
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            Neo4jClientError("Lucene parse error"),  # first call fails
            [{"locus_tag": "PMM0001"}],  # retry succeeds
        ]
        result = json.loads(tool_fns["search_genes"](mock_ctx, search_text="DNA [repair"))
        assert result["total"] == 1
        assert conn.execute_query.call_count == 2

    def test_category_passed_through(self, tool_fns, mock_ctx):
        """category param is forwarded to the query builder."""
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["search_genes"](mock_ctx, search_text="x", category="Photosynthesis")
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["category"] == "Photosynthesis"

    def test_dedup_collapses_same_cluster(self, tool_fns, mock_ctx):
        """Dedup groups rows with the same cluster_id, keeping the first as representative."""
        rows = [
            {"locus_tag": "PMM0044", "cluster_id": "CK_00001234", "organism_strain": "Prochlorococcus MED4", "score": 5.0},
            {"locus_tag": "PMT9312_0044", "cluster_id": "CK_00001234", "organism_strain": "Prochlorococcus MIT9312", "score": 4.5},
            {"locus_tag": "SYNW0044", "cluster_id": "CK_00001234", "organism_strain": "Synechococcus WH8102", "score": 4.0},
            {"locus_tag": "PMM0099", "cluster_id": "CK_00005678", "organism_strain": "Prochlorococcus MED4", "score": 3.0},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(
            tool_fns["search_genes"](mock_ctx, search_text="naphthoate", deduplicate=True)
        )
        assert result["total"] == 2
        rep = result["results"][0]
        assert rep["locus_tag"] == "PMM0044"
        assert rep["collapsed_count"] == 3
        assert rep["cluster_organisms"] == {
            "Prochlorococcus MED4": 1,
            "Prochlorococcus MIT9312": 1,
            "Synechococcus WH8102": 1,
        }
        # Second cluster has only 1 member
        assert result["results"][1]["collapsed_count"] == 1

    def test_dedup_genes_without_cluster_appear_individually(self, tool_fns, mock_ctx):
        """Genes without cluster_id always appear individually even with dedup."""
        rows = [
            {"locus_tag": "PMM0044", "cluster_id": "CK_00001234", "organism_strain": "Prochlorococcus MED4", "score": 5.0},
            {"locus_tag": "PMT9312_0044", "cluster_id": "CK_00001234", "organism_strain": "Prochlorococcus MIT9312", "score": 4.5},
            {"locus_tag": "ALT_NOCL", "cluster_id": None, "organism_strain": "Alteromonas macleodii MIT1002", "score": 3.0},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(
            tool_fns["search_genes"](mock_ctx, search_text="test", deduplicate=True)
        )
        assert result["total"] == 2
        loci = [r["locus_tag"] for r in result["results"]]
        assert "ALT_NOCL" in loci
        # Gene without cluster should not have collapsed_count
        nocl = [r for r in result["results"] if r["locus_tag"] == "ALT_NOCL"][0]
        assert "collapsed_count" not in nocl


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

    def test_direction_filter_passed_through(self, tool_fns, mock_ctx):
        rows = [{"gene": "PMM0001", "direction": "up"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        tool_fns["query_expression"](mock_ctx, gene_id="PMM0001", direction="up")
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["dir"] == "up"

    def test_include_orthologs_changes_query(self, tool_fns, mock_ctx):
        rows = [{"gene": "PMM0001"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        tool_fns["query_expression"](mock_ctx, gene_id="PMM0001", include_orthologs=True)
        called_cypher = _conn_from(mock_ctx).execute_query.call_args[0][0]
        assert "ortholog" in called_cypher.lower()

    def test_min_log2fc_passed_through(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["query_expression"](mock_ctx, gene_id="PMM0001", min_log2fc=1.5)
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["min_fc"] == 1.5

    def test_max_pvalue_passed_through(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["query_expression"](mock_ctx, gene_id="PMM0001", max_pvalue=0.05)
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["max_pv"] == 0.05


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

    def test_conditions_filter_passed_through(self, tool_fns, mock_ctx):
        rows = [{"gene": "PMM0001"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        tool_fns["compare_conditions"](mock_ctx, conditions=["nitrogen_stress"])
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["conditions"] == ["nitrogen_stress"]


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

    def test_neo4j_error_propagates(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.side_effect = Neo4jClientError("syntax error")
        with pytest.raises(Neo4jClientError):
            tool_fns["run_cypher"](mock_ctx, query="MATCH (n) RETURN n")

    def test_foreach_blocked(self, tool_fns, mock_ctx):
        result = tool_fns["run_cypher"](
            mock_ctx, query="FOREACH (x IN [1] | CREATE (:Node))"
        )
        assert "Error" in result
        _conn_from(mock_ctx).execute_query.assert_not_called()

    def test_load_csv_blocked(self, tool_fns, mock_ctx):
        result = tool_fns["run_cypher"](
            mock_ctx, query="LOAD CSV FROM 'file:///data.csv' AS row RETURN row"
        )
        assert "Error" in result
        _conn_from(mock_ctx).execute_query.assert_not_called()

    def test_call_procedure_blocked(self, tool_fns, mock_ctx):
        result = tool_fns["run_cypher"](
            mock_ctx, query="CALL apoc.create.node(['Gene'], {name: 'x'})"
        )
        assert "Error" in result
        _conn_from(mock_ctx).execute_query.assert_not_called()
