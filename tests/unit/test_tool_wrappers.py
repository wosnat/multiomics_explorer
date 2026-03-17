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
    "get_schema", "list_filter_values", "list_organisms", "resolve_gene",
    "search_genes", "get_gene_details", "query_expression",
    "compare_conditions", "get_homologs", "run_cypher",
    "search_ontology", "genes_by_ontology", "gene_ontology_terms",
]


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------
class TestToolRegistration:
    def test_all_tools_registered(self, tool_fns):
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
# list_filter_values
# ---------------------------------------------------------------------------
class TestListFilterValuesWrapper:
    def test_returns_combined_json(self, tool_fns, mock_ctx):
        """list_filter_values returns gene_categories and condition_types in one JSON response."""
        categories = [
            {"category": "Photosynthesis", "gene_count": 100},
            {"category": "Transport", "gene_count": 50},
        ]
        condition_types = [
            {"condition_type": "nitrogen_stress", "cnt": 10},
            {"condition_type": "light_stress", "cnt": 8},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [categories, condition_types]
        # Ensure no cached value
        mock_ctx.request_context.lifespan_context._filter_values_cache = None
        result = json.loads(tool_fns["list_filter_values"](mock_ctx))
        assert "gene_categories" in result
        assert "condition_types" in result
        assert len(result["gene_categories"]) == 2
        assert len(result["condition_types"]) == 2

    def test_gene_categories_keys(self, tool_fns, mock_ctx):
        """Each gene_categories entry has 'category' and 'gene_count' keys."""
        categories = [{"category": "Photosynthesis", "gene_count": 100}]
        condition_types = [{"condition_type": "nitrogen_stress", "cnt": 10}]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [categories, condition_types]
        mock_ctx.request_context.lifespan_context._filter_values_cache = None
        result = json.loads(tool_fns["list_filter_values"](mock_ctx))
        entry = result["gene_categories"][0]
        assert "category" in entry
        assert "gene_count" in entry

    def test_condition_types_keys(self, tool_fns, mock_ctx):
        """Each condition_types entry has 'condition_type' and 'cnt' keys."""
        categories = [{"category": "Photosynthesis", "gene_count": 100}]
        condition_types = [{"condition_type": "nitrogen_stress", "cnt": 10}]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [categories, condition_types]
        mock_ctx.request_context.lifespan_context._filter_values_cache = None
        result = json.loads(tool_fns["list_filter_values"](mock_ctx))
        entry = result["condition_types"][0]
        assert "condition_type" in entry
        assert "cnt" in entry

    def test_caching(self, tool_fns, mock_ctx):
        """Second call returns cached value without hitting Neo4j again."""
        cached_response = json.dumps({
            "gene_categories": [{"category": "Cached", "gene_count": 1}],
            "condition_types": [{"condition_type": "cached_type", "cnt": 1}],
        })
        mock_ctx.request_context.lifespan_context._filter_values_cache = cached_response
        result = tool_fns["list_filter_values"](mock_ctx)
        assert result == cached_response
        _conn_from(mock_ctx).execute_query.assert_not_called()


# ---------------------------------------------------------------------------
# list_organisms
# ---------------------------------------------------------------------------
class TestListOrganismsWrapper:
    def test_returns_json_array(self, tool_fns, mock_ctx):
        """list_organisms returns a JSON array with expected columns."""
        rows = [
            {"name": "Prochlorococcus MED4", "genus": "Prochlorococcus",
             "strain": "MED4", "clade": "HLI", "gene_count": 1929},
            {"name": "Alteromonas EZ55", "genus": "Alteromonas",
             "strain": "EZ55", "clade": None, "gene_count": 3800},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows
        mock_ctx.request_context.lifespan_context._organisms_cache = None
        result = json.loads(tool_fns["list_organisms"](mock_ctx))
        assert isinstance(result, list)
        assert len(result) == 2
        for col in ["name", "genus", "strain", "clade", "gene_count"]:
            assert col in result[0]

    def test_empty_result_message(self, tool_fns, mock_ctx):
        """Empty result returns descriptive message."""
        _conn_from(mock_ctx).execute_query.return_value = []
        mock_ctx.request_context.lifespan_context._organisms_cache = None
        result = tool_fns["list_organisms"](mock_ctx)
        assert result == "No organisms found in the knowledge graph."

    def test_caching(self, tool_fns, mock_ctx):
        """Second call returns cached value without hitting Neo4j again."""
        cached_response = json.dumps([
            {"name": "Cached", "genus": "G", "strain": "S",
             "clade": None, "gene_count": 1},
        ])
        mock_ctx.request_context.lifespan_context._organisms_cache = cached_response
        result = tool_fns["list_organisms"](mock_ctx)
        assert result == cached_response
        _conn_from(mock_ctx).execute_query.assert_not_called()


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

    def test_dedup_collapses_same_group(self, tool_fns, mock_ctx):
        """Dedup groups rows with the same ortholog group, keeping the first as representative."""
        search_rows = [
            {"locus_tag": "PMM0044", "organism_strain": "Prochlorococcus MED4", "score": 5.0},
            {"locus_tag": "PMT9312_0044", "organism_strain": "Prochlorococcus MIT9312", "score": 4.5},
            {"locus_tag": "SYNW0044", "organism_strain": "Synechococcus WH8102", "score": 4.0},
            {"locus_tag": "PMM0099", "organism_strain": "Prochlorococcus MED4", "score": 3.0},
        ]
        dedup_rows = [
            {"locus_tag": "PMM0044", "dedup_group": "CK_00001234"},
            {"locus_tag": "PMT9312_0044", "dedup_group": "CK_00001234"},
            {"locus_tag": "SYNW0044", "dedup_group": "CK_00001234"},
            {"locus_tag": "PMM0099", "dedup_group": "CK_00005678"},
        ]
        _conn_from(mock_ctx).execute_query.side_effect = [search_rows, dedup_rows]
        result = json.loads(
            tool_fns["search_genes"](mock_ctx, search_text="naphthoate", deduplicate=True)
        )
        assert result["total"] == 2
        rep = result["results"][0]
        assert rep["locus_tag"] == "PMM0044"
        assert rep["collapsed_count"] == 3
        assert rep["group_organisms"] == {
            "Prochlorococcus MED4": 1,
            "Prochlorococcus MIT9312": 1,
            "Synechococcus WH8102": 1,
        }
        # Second group has only 1 member
        assert result["results"][1]["collapsed_count"] == 1

    def test_dedup_genes_without_group_appear_individually(self, tool_fns, mock_ctx):
        """Genes without an ortholog group always appear individually even with dedup."""
        search_rows = [
            {"locus_tag": "PMM0044", "organism_strain": "Prochlorococcus MED4", "score": 5.0},
            {"locus_tag": "PMT9312_0044", "organism_strain": "Prochlorococcus MIT9312", "score": 4.5},
            {"locus_tag": "ALT_NOCL", "organism_strain": "Alteromonas macleodii MIT1002", "score": 3.0},
        ]
        dedup_rows = [
            {"locus_tag": "PMM0044", "dedup_group": "CK_00001234"},
            {"locus_tag": "PMT9312_0044", "dedup_group": "CK_00001234"},
            # ALT_NOCL has no ortholog group — not in dedup_rows
        ]
        _conn_from(mock_ctx).execute_query.side_effect = [search_rows, dedup_rows]
        result = json.loads(
            tool_fns["search_genes"](mock_ctx, search_text="test", deduplicate=True)
        )
        assert result["total"] == 2
        loci = [r["locus_tag"] for r in result["results"]]
        assert "ALT_NOCL" in loci
        # Gene without group should not have collapsed_count
        nocl = [r for r in result["results"] if r["locus_tag"] == "ALT_NOCL"][0]
        assert "collapsed_count" not in nocl

    def test_limit_boundary_one(self, tool_fns, mock_ctx):
        """limit=1 returns at most 1 result."""
        rows = [{"locus_tag": "PMM0001", "score": 5.0}, {"locus_tag": "PMM0002", "score": 3.0}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["search_genes"](mock_ctx, search_text="x", limit=1))
        # limit is applied at the query level, not post-filter
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["limit"] == 1


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
    def _gene_stub(self):
        return {"locus_tag": "PMM0001", "gene_name": "dnaN",
                "product": "DNA polymerase III, beta subunit",
                "organism_strain": "Prochlorococcus MED4"}

    def _sample_groups(self):
        return [
            {"og_name": "CK_00000364", "source": "cyanorak",
             "taxonomic_level": "curated", "specificity_rank": 0,
             "consensus_product": "DNA polymerase III beta subunit",
             "consensus_gene_name": "dnaN", "member_count": 72,
             "organism_count": 72, "genera": "Prochlorococcus;Synechococcus",
             "has_cross_genus_members": True},
            {"og_name": "COG0592@2", "source": "eggnog",
             "taxonomic_level": "Bacteria", "specificity_rank": 3,
             "consensus_product": "DNA polymerase III beta subunit",
             "consensus_gene_name": "dnaN", "member_count": 150,
             "organism_count": 140, "genera": "Prochlorococcus;Synechococcus;Alteromonas",
             "has_cross_genus_members": True},
        ]

    def test_gene_not_found_message(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = tool_fns["get_homologs"](mock_ctx, gene_id="FAKE")
        assert "not found" in result

    def test_no_ortholog_groups_message(self, tool_fns, mock_ctx):
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],  # gene stub
            [],                   # no groups
        ]
        result = tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")
        assert "No ortholog groups" in result

    def test_default_mode_has_query_gene_and_groups_without_members(self, tool_fns, mock_ctx):
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
        ]
        result = json.loads(tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001"))
        assert "query_gene" in result
        assert "ortholog_groups" in result
        assert result["query_gene"]["locus_tag"] == "PMM0001"
        for g in result["ortholog_groups"]:
            assert "members" not in g

    def test_include_members_has_members_lists(self, tool_fns, mock_ctx):
        members = [
            {"og_name": "CK_00000364", "locus_tag": "PMT9312_0001",
             "gene_name": "dnaN", "product": "DNA pol III beta",
             "organism_strain": "Prochlorococcus MIT9312"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
            members,
        ]
        result = json.loads(
            tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001", include_members=True)
        )
        # At least one group should have members
        has_members = any("members" in g for g in result["ortholog_groups"])
        assert has_members

    def test_source_filter_passed_through(self, tool_fns, mock_ctx):
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups()[:1],  # only cyanorak group
        ]
        tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001", source="cyanorak")
        # The groups query (2nd call) should have source param
        groups_call = conn.execute_query.call_args_list[1]
        groups_kwargs = groups_call.kwargs
        assert groups_kwargs.get("source") == "cyanorak"

    def test_exclude_paralogs_passed_to_members_builder(self, tool_fns, mock_ctx):
        """exclude_paralogs=True adds organism_strain filter in members query."""
        members = [
            {"og_name": "CK_00000364", "locus_tag": "PMT9312_0001",
             "gene_name": "dnaN", "product": "p",
             "organism_strain": "Prochlorococcus MIT9312"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
            members,
        ]
        tool_fns["get_homologs"](
            mock_ctx, gene_id="PMM0001", include_members=True, exclude_paralogs=True,
        )
        # Members query is the 3rd call
        members_cypher = conn.execute_query.call_args_list[2][0][0]
        assert "other.organism_strain <> g.organism_strain" in members_cypher

    def test_include_expression_parameter_no_longer_exists(self, tool_fns, mock_ctx):
        """include_expression is no longer accepted by get_homologs."""
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
        ]
        with pytest.raises(TypeError):
            tool_fns["get_homologs"](
                mock_ctx, gene_id="PMM0001", include_expression=True,
            )

    def test_response_is_json(self, tool_fns, mock_ctx):
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
        ]
        raw = tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")
        result = json.loads(raw)
        assert isinstance(result, dict)

    def test_invalid_source_returns_error(self, tool_fns, mock_ctx):
        result = tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001", source="bad")
        assert "Invalid source" in result
        assert "cyanorak" in result
        assert "eggnog" in result

    def test_invalid_taxonomic_level_returns_error(self, tool_fns, mock_ctx):
        result = tool_fns["get_homologs"](
            mock_ctx, gene_id="PMM0001", taxonomic_level="bad",
        )
        assert "Invalid taxonomic_level" in result

    def test_invalid_max_specificity_rank_returns_error(self, tool_fns, mock_ctx):
        result = tool_fns["get_homologs"](
            mock_ctx, gene_id="PMM0001", max_specificity_rank=5,
        )
        assert "Invalid max_specificity_rank" in result

    def test_invalid_member_limit_zero_returns_error(self, tool_fns, mock_ctx):
        result = tool_fns["get_homologs"](
            mock_ctx, gene_id="PMM0001", member_limit=0,
        )
        assert "Invalid member_limit" in result

    def test_invalid_member_limit_300_returns_error(self, tool_fns, mock_ctx):
        result = tool_fns["get_homologs"](
            mock_ctx, gene_id="PMM0001", member_limit=300,
        )
        assert "Invalid member_limit" in result

    def test_member_limit_truncates_and_sets_flag(self, tool_fns, mock_ctx):
        members = [
            {"og_name": "CK_00000364", "locus_tag": f"PMT{i:04d}",
             "gene_name": "x", "product": "p", "organism_strain": f"Strain{i}"}
            for i in range(5)
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups()[:1],  # one group
            members,
        ]
        result = json.loads(
            tool_fns["get_homologs"](
                mock_ctx, gene_id="PMM0001", include_members=True, member_limit=2,
            )
        )
        g = result["ortholog_groups"][0]
        assert len(g["members"]) == 2
        assert g["truncated"] is True

    def test_groups_below_limit_no_truncated_key(self, tool_fns, mock_ctx):
        members = [
            {"og_name": "CK_00000364", "locus_tag": "PMT0001",
             "gene_name": "x", "product": "p", "organism_strain": "Strain1"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups()[:1],
            members,
        ]
        result = json.loads(
            tool_fns["get_homologs"](
                mock_ctx, gene_id="PMM0001", include_members=True, member_limit=50,
            )
        )
        g = result["ortholog_groups"][0]
        assert "truncated" not in g

    # -- member_limit edge cases ------------------------------------------

    def test_member_limit_1_accepts(self, tool_fns, mock_ctx):
        """member_limit=1 is the minimum valid value."""
        members = [
            {"og_name": "CK_00000364", "locus_tag": "PMT0001",
             "gene_name": "x", "product": "p", "organism_strain": "Strain1"},
            {"og_name": "CK_00000364", "locus_tag": "PMT0002",
             "gene_name": "x", "product": "p", "organism_strain": "Strain2"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups()[:1],
            members,
        ]
        result = json.loads(
            tool_fns["get_homologs"](
                mock_ctx, gene_id="PMM0001", include_members=True, member_limit=1,
            )
        )
        g = result["ortholog_groups"][0]
        assert len(g["members"]) == 1
        assert g["truncated"] is True

    def test_member_limit_200_accepts(self, tool_fns, mock_ctx):
        """member_limit=200 is the maximum valid value (accepted, not error)."""
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
        ]
        result = tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001", member_limit=200)
        # Should not error — returns valid JSON
        assert "Invalid member_limit" not in result

    def test_member_limit_exact_no_truncation(self, tool_fns, mock_ctx):
        """When members == member_limit, no truncation occurs."""
        members = [
            {"og_name": "CK_00000364", "locus_tag": f"PMT{i:04d}",
             "gene_name": "x", "product": "p", "organism_strain": f"Strain{i}"}
            for i in range(3)
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups()[:1],
            members,
        ]
        result = json.loads(
            tool_fns["get_homologs"](
                mock_ctx, gene_id="PMM0001", include_members=True, member_limit=3,
            )
        )
        g = result["ortholog_groups"][0]
        assert len(g["members"]) == 3
        assert "truncated" not in g

    # -- debug mode -------------------------------------------------------

    def test_debug_true_includes_queries(self, tool_fns, mock_ctx):
        """debug=True attaches Cypher queries to the response."""
        mock_ctx.request_context.lifespan_context.debug_queries = True
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
        ]
        raw = tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")
        assert "_debug" in raw
        assert "queries" in raw
        # Response has both debug block and data block separated by ---
        assert "---" in raw
        # Reset for other tests
        mock_ctx.request_context.lifespan_context.debug_queries = False

    def test_debug_true_with_members_has_two_queries(self, tool_fns, mock_ctx):
        """debug=True with include_members attaches both groups and members queries."""
        mock_ctx.request_context.lifespan_context.debug_queries = True
        members = [
            {"og_name": "CK_00000364", "locus_tag": "PMT0001",
             "gene_name": "x", "product": "p", "organism_strain": "Strain1"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups()[:1],
            members,
        ]
        raw = tool_fns["get_homologs"](
            mock_ctx, gene_id="PMM0001", include_members=True,
        )
        # Parse the debug block (before ---)
        debug_part = raw.split("---")[0]
        debug_data = json.loads(debug_part)
        assert len(debug_data["_debug"]["queries"]) == 2
        # Reset
        mock_ctx.request_context.lifespan_context.debug_queries = False


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


# ---------------------------------------------------------------------------
# search_ontology
# ---------------------------------------------------------------------------
class TestSearchOntologyWrapper:
    def test_returns_json_with_id_name_score(self, tool_fns, mock_ctx):
        rows = [
            {"id": "go:0006260", "name": "DNA replication", "score": 5.0},
            {"id": "go:0006261", "name": "DNA-templated DNA replication", "score": 3.2},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["search_ontology"](mock_ctx, search_text="replication", ontology="go_bp"))
        assert result["total"] == 2
        assert result["query"] == "replication"
        for r in result["results"]:
            assert "id" in r
            assert "name" in r
            assert "score" in r

    def test_kegg_same_columns(self, tool_fns, mock_ctx):
        rows = [{"id": "kegg.pathway:ko00010", "name": "Glycolysis", "score": 4.0}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["search_ontology"](mock_ctx, search_text="glycolysis", ontology="kegg"))
        assert set(result["results"][0].keys()) == {"id", "name", "score"}

    def test_empty_results(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = json.loads(tool_fns["search_ontology"](mock_ctx, search_text="nonexistent", ontology="go_bp"))
        assert result["results"] == []
        assert result["total"] == 0

    def test_lucene_fallback_on_error(self, tool_fns, mock_ctx):
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            Neo4jClientError("Lucene parse error"),
            [{"id": "go:0006260", "name": "DNA replication", "score": 1.0}],
        ]
        result = json.loads(tool_fns["search_ontology"](mock_ctx, search_text="bad [query", ontology="go_bp"))
        assert result["total"] == 1
        assert conn.execute_query.call_count == 2

    def test_raises_on_double_failure(self, tool_fns, mock_ctx):
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            Neo4jClientError("parse error"),
            Neo4jClientError("still broken"),
        ]
        with pytest.raises(Neo4jClientError):
            tool_fns["search_ontology"](mock_ctx, search_text="bad [query", ontology="go_bp")

    def test_limit_passed_through(self, tool_fns, mock_ctx):
        """Limit parameter is forwarded to the query builder."""
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["search_ontology"](mock_ctx, search_text="test", ontology="go_bp", limit=5)
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["limit"] == 5

    def test_go_mf_ontology_accepted(self, tool_fns, mock_ctx):
        """go_mf ontology is accepted without error."""
        rows = [{"id": "go:0003677", "name": "DNA binding", "score": 4.0}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["search_ontology"](mock_ctx, search_text="binding", ontology="go_mf"))
        assert result["total"] == 1

    def test_go_cc_ontology_accepted(self, tool_fns, mock_ctx):
        """go_cc ontology is accepted without error."""
        rows = [{"id": "go:0016020", "name": "membrane", "score": 3.5}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["search_ontology"](mock_ctx, search_text="membrane", ontology="go_cc"))
        assert result["total"] == 1

    def test_cog_category_ontology_accepted(self, tool_fns, mock_ctx):
        """cog_category ontology is accepted without error."""
        rows = [{"id": "cog:C", "name": "Energy production and conversion", "score": 4.0}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["search_ontology"](mock_ctx, search_text="energy", ontology="cog_category"))
        assert result["total"] == 1

    def test_cyanorak_role_ontology_accepted(self, tool_fns, mock_ctx):
        """cyanorak_role ontology is accepted without error."""
        rows = [{"id": "cyanorak_role:F", "name": "DNA metabolism", "score": 3.5}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["search_ontology"](mock_ctx, search_text="DNA", ontology="cyanorak_role"))
        assert result["total"] == 1

    def test_tigr_role_ontology_accepted(self, tool_fns, mock_ctx):
        """tigr_role ontology is accepted without error."""
        rows = [{"id": "tigr_role:120", "name": "Energy metabolism", "score": 3.0}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["search_ontology"](mock_ctx, search_text="metabolism", ontology="tigr_role"))
        assert result["total"] == 1

    def test_pfam_ontology_accepted(self, tool_fns, mock_ctx):
        """pfam ontology is accepted without error."""
        rows = [{"id": "pfam:PF00712", "name": "DNA polymerase", "score": 5.0}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["search_ontology"](mock_ctx, search_text="polymerase", ontology="pfam"))
        assert result["total"] == 1


# ---------------------------------------------------------------------------
# genes_by_ontology
# ---------------------------------------------------------------------------
class TestGenesByOntologyWrapper:
    def test_grouped_by_organism_response(self, tool_fns, mock_ctx):
        rows = [
            {"locus_tag": "PMM0120", "gene_name": "dnaN", "product": "p1", "organism_strain": "Prochlorococcus MED4"},
            {"locus_tag": "MIT1002_00001", "gene_name": "geneA", "product": "p2", "organism_strain": "Alteromonas macleodii MIT1002"},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["genes_by_ontology"](
            mock_ctx, term_ids=["go:0006260"], ontology="go_bp",
        ))
        assert result["total"] == 2
        assert "Prochlorococcus MED4" in result["results"]
        assert "Alteromonas macleodii MIT1002" in result["results"]
        # organism_strain should be stripped from individual entries
        for org_genes in result["results"].values():
            for gene in org_genes:
                assert "organism_strain" not in gene

    def test_empty_results(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = json.loads(tool_fns["genes_by_ontology"](
            mock_ctx, term_ids=["go:9999999"], ontology="go_bp",
        ))
        assert result["results"] == {}
        assert result["total"] == 0

    def test_invalid_ontology_raises_error(self, tool_fns, mock_ctx):
        """Invalid ontology value raises ValueError from the builder."""
        with pytest.raises(ValueError, match="Invalid ontology"):
            tool_fns["genes_by_ontology"](
                mock_ctx, term_ids=["x"], ontology="bad_value",
            )

    def test_go_mf_ontology_accepted(self, tool_fns, mock_ctx):
        """go_mf ontology is accepted without error."""
        rows = [{"locus_tag": "PMM0120", "gene_name": "x", "product": "p", "organism_strain": "Prochlorococcus MED4"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["genes_by_ontology"](
            mock_ctx, term_ids=["go:0003677"], ontology="go_mf",
        ))
        assert result["total"] == 1

    def test_go_cc_ontology_accepted(self, tool_fns, mock_ctx):
        """go_cc ontology is accepted without error."""
        rows = [{"locus_tag": "PMM0120", "gene_name": "x", "product": "p", "organism_strain": "Prochlorococcus MED4"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["genes_by_ontology"](
            mock_ctx, term_ids=["go:0016020"], ontology="go_cc",
        ))
        assert result["total"] == 1

    def test_cog_category_ontology_accepted(self, tool_fns, mock_ctx):
        """cog_category ontology is accepted without error."""
        rows = [{"locus_tag": "PMM0120", "gene_name": "x", "product": "p", "organism_strain": "Prochlorococcus MED4"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["genes_by_ontology"](
            mock_ctx, term_ids=["cog:C"], ontology="cog_category",
        ))
        assert result["total"] == 1

    def test_cyanorak_role_ontology_accepted(self, tool_fns, mock_ctx):
        """cyanorak_role ontology is accepted without error."""
        rows = [{"locus_tag": "PMM0120", "gene_name": "x", "product": "p", "organism_strain": "Prochlorococcus MED4"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["genes_by_ontology"](
            mock_ctx, term_ids=["cyanorak_role:F"], ontology="cyanorak_role",
        ))
        assert result["total"] == 1

    def test_tigr_role_ontology_accepted(self, tool_fns, mock_ctx):
        """tigr_role ontology is accepted without error."""
        rows = [{"locus_tag": "PMM0120", "gene_name": "x", "product": "p", "organism_strain": "Prochlorococcus MED4"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["genes_by_ontology"](
            mock_ctx, term_ids=["tigr_role:120"], ontology="tigr_role",
        ))
        assert result["total"] == 1

    def test_pfam_ontology_accepted(self, tool_fns, mock_ctx):
        """pfam ontology is accepted without error."""
        rows = [{"locus_tag": "PMM0120", "gene_name": "x", "product": "p", "organism_strain": "Prochlorococcus MED4"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["genes_by_ontology"](
            mock_ctx, term_ids=["pfam:PF00712"], ontology="pfam",
        ))
        assert result["total"] == 1

    def test_organism_filter_passed_through(self, tool_fns, mock_ctx):
        """Organism parameter is forwarded to the query builder."""
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["genes_by_ontology"](
            mock_ctx, term_ids=["go:0006260"], ontology="go_bp", organism="MED4",
        )
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["organism"] == "MED4"

    def test_limit_passed_through(self, tool_fns, mock_ctx):
        """Limit parameter is forwarded to the query builder."""
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["genes_by_ontology"](
            mock_ctx, term_ids=["go:0006260"], ontology="go_bp", limit=5,
        )
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["limit"] == 5


# ---------------------------------------------------------------------------
# gene_ontology_terms
# ---------------------------------------------------------------------------
class TestGeneOntologyTermsWrapper:
    def test_returns_json_with_id_name(self, tool_fns, mock_ctx):
        rows = [
            {"id": "go:0006260", "name": "DNA replication"},
            {"id": "go:0006261", "name": "DNA-templated DNA replication"},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["gene_ontology_terms"](
            mock_ctx, gene_id="PMM0001", ontology="go_bp",
        ))
        assert result["total"] == 2
        for r in result["results"]:
            assert "id" in r
            assert "name" in r

    def test_empty_results(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = json.loads(tool_fns["gene_ontology_terms"](
            mock_ctx, gene_id="FAKE", ontology="go_bp",
        ))
        assert result["results"] == []
        assert result["total"] == 0

    def test_invalid_ontology_raises_error(self, tool_fns, mock_ctx):
        with pytest.raises(ValueError, match="Invalid ontology"):
            tool_fns["gene_ontology_terms"](
                mock_ctx, gene_id="PMM0001", ontology="invalid",
            )

    def test_limit_passed_through(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["gene_ontology_terms"](
            mock_ctx, gene_id="PMM0001", ontology="go_bp", limit=10,
        )
        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["limit"] == 10

    def test_go_mf_ontology_accepted(self, tool_fns, mock_ctx):
        """go_mf ontology is accepted without error."""
        rows = [{"id": "go:0003677", "name": "DNA binding"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["gene_ontology_terms"](
            mock_ctx, gene_id="PMM0001", ontology="go_mf",
        ))
        assert result["total"] == 1

    def test_go_cc_ontology_accepted(self, tool_fns, mock_ctx):
        """go_cc ontology is accepted without error."""
        rows = [{"id": "go:0016020", "name": "membrane"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["gene_ontology_terms"](
            mock_ctx, gene_id="PMM0001", ontology="go_cc",
        ))
        assert result["total"] == 1

    def test_cog_category_ontology_accepted(self, tool_fns, mock_ctx):
        """cog_category ontology is accepted without error."""
        rows = [{"id": "cog:C", "name": "Energy production and conversion"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["gene_ontology_terms"](
            mock_ctx, gene_id="PMM0001", ontology="cog_category",
        ))
        assert result["total"] == 1

    def test_cyanorak_role_ontology_accepted(self, tool_fns, mock_ctx):
        """cyanorak_role ontology is accepted without error."""
        rows = [{"id": "cyanorak_role:F", "name": "DNA metabolism"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["gene_ontology_terms"](
            mock_ctx, gene_id="PMM0001", ontology="cyanorak_role",
        ))
        assert result["total"] == 1

    def test_tigr_role_ontology_accepted(self, tool_fns, mock_ctx):
        """tigr_role ontology is accepted without error."""
        rows = [{"id": "tigr_role:120", "name": "Energy metabolism"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["gene_ontology_terms"](
            mock_ctx, gene_id="PMM0001", ontology="tigr_role",
        ))
        assert result["total"] == 1

    def test_pfam_ontology_accepted(self, tool_fns, mock_ctx):
        """pfam ontology is accepted without error."""
        rows = [{"id": "pfam:PF00712", "name": "DNA polymerase"}]
        _conn_from(mock_ctx).execute_query.return_value = rows
        result = json.loads(tool_fns["gene_ontology_terms"](
            mock_ctx, gene_id="PMM0001", ontology="pfam",
        ))
        assert result["total"] == 1

    def test_leaf_only_default_true(self, tool_fns, mock_ctx):
        """leaf_only defaults to True (leaf_only filter in query)."""
        _conn_from(mock_ctx).execute_query.return_value = []
        tool_fns["gene_ontology_terms"](
            mock_ctx, gene_id="PMM0001", ontology="go_bp",
        )
        called_cypher = _conn_from(mock_ctx).execute_query.call_args[0][0]
        assert "NOT EXISTS" in called_cypher
