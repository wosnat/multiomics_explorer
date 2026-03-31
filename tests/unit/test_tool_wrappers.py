"""Unit tests for MCP tool wrapper logic — no Neo4j needed.

Tests the tool-level behavior (input validation, response formatting,
error messages, LIMIT injection) by mocking the Neo4j connection.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from neo4j.exceptions import ClientError as Neo4jClientError

from multiomics_explorer.mcp_server.tools import register_tools


@pytest.fixture(scope="module")
def tool_fns():
    """Register tools on a fresh FastMCP and return a dict of {name: fn}."""
    import asyncio
    mcp = FastMCP("test")
    register_tools(mcp)
    tools = asyncio.run(mcp.list_tools())
    return {t.name: asyncio.run(mcp.get_tool(t.name)).fn for t in tools}


@pytest.fixture()
def mock_ctx():
    """MCP Context mock whose .conn returns a MagicMock GraphConnection.

    Also mocks async logging methods (info, warning, error, debug)
    for async tools.
    """
    ctx = MagicMock()
    ctx.request_context.lifespan_context.conn = MagicMock()
    # Mock async context logging methods
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()
    ctx.debug = AsyncMock()
    return ctx


def _conn_from(ctx):
    return ctx.request_context.lifespan_context.conn


EXPECTED_TOOLS = [
    "kg_schema", "list_filter_values", "list_organisms", "resolve_gene",
    "genes_by_function", "gene_overview", "gene_details",
    "gene_homologs", "run_cypher",
    "search_ontology", "search_homolog_groups", "genes_by_homolog_group",
    "genes_by_ontology", "gene_ontology_terms",
    "list_publications",
    "list_experiments",
    "differential_expression_by_gene",
    "differential_expression_by_ortholog",
    "gene_response_profile",
    "list_gene_clusters",
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
# kg_schema
# ---------------------------------------------------------------------------
class TestKgSchemaWrapper:
    _SAMPLE_API_RETURN = {
        "nodes": {"Gene": {"properties": {"locus_tag": "STRING"}}},
        "relationships": {
            "Has_function": {
                "source_labels": ["Gene"],
                "target_labels": ["GOTerm"],
                "properties": {},
            }
        },
    }

    @pytest.mark.asyncio
    async def test_returns_schema(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.kg_schema",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["kg_schema"](mock_ctx)
        assert "Gene" in result.nodes
        assert "Has_function" in result.relationships

    @pytest.mark.asyncio
    async def test_nodes_have_properties(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.kg_schema",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["kg_schema"](mock_ctx)
        assert "properties" in result.nodes["Gene"]
        assert result.nodes["Gene"]["properties"]["locus_tag"] == "STRING"


# ---------------------------------------------------------------------------
# list_filter_values
# ---------------------------------------------------------------------------
class TestListFilterValuesWrapper:
    _SAMPLE_API_RETURN = {
        "filter_type": "gene_category",
        "total_entries": 2,
        "returned": 2,
        "truncated": False,
        "results": [
            {"value": "Photosynthesis", "count": 770},
            {"value": "Transport", "count": 500},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, mock_ctx):
        """Response has filter_type, total_entries, returned, truncated, results."""
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_filter_values"](mock_ctx)
        assert result.filter_type == "gene_category"
        assert result.total_entries == 2
        assert result.returned == 2
        assert result.truncated is False
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_result_fields(self, tool_fns, mock_ctx):
        """Each result has value and count fields."""
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_filter_values"](mock_ctx)
        entry = result.results[0]
        assert hasattr(entry, "value")
        assert hasattr(entry, "count")
        assert entry.value == "Photosynthesis"
        assert entry.count == 770

    @pytest.mark.asyncio
    async def test_filter_type_forwarded(self, tool_fns, mock_ctx):
        """filter_type param is passed through to api.list_filter_values."""
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value={**self._SAMPLE_API_RETURN, "filter_type": "gene_category"},
        ) as mock_fn:
            await tool_fns["list_filter_values"](mock_ctx, filter_type="gene_category")
        mock_fn.assert_called_once()
        assert mock_fn.call_args.kwargs.get("filter_type") == "gene_category" or \
               mock_fn.call_args.args[0] == "gene_category"

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        """total_entries=0, results=[]."""
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value={
                "filter_type": "gene_category",
                "total_entries": 0,
                "returned": 0,
                "truncated": False,
                "results": [],
            },
        ):
            result = await tool_fns["list_filter_values"](mock_ctx)
        assert result.total_entries == 0
        assert result.results == []

    @pytest.mark.asyncio
    async def test_truncated_always_false(self, tool_fns, mock_ctx):
        """truncated is always False."""
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_filter_values"](mock_ctx)
        assert result.truncated is False

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from api raises ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            side_effect=ValueError("Unknown filter_type: 'bogus'"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["list_filter_values"](mock_ctx, filter_type="gene_category")

    @pytest.mark.asyncio
    async def test_generic_error(self, tool_fns, mock_ctx):
        """Unexpected exception raises ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            side_effect=RuntimeError("unexpected"),
        ):
            with pytest.raises(ToolError, match="Error in list_filter_values"):
                await tool_fns["list_filter_values"](mock_ctx)

    @pytest.mark.asyncio
    async def test_no_caching(self, tool_fns, mock_ctx):
        """api.list_filter_values is called on every invocation (no caching)."""
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_fn:
            await tool_fns["list_filter_values"](mock_ctx)
        assert mock_fn.call_count == 1


# ---------------------------------------------------------------------------
# list_organisms
# ---------------------------------------------------------------------------
class TestListOrganismsWrapper:
    _SAMPLE_ORG = {
        "organism_name": "Prochlorococcus MED4", "genus": "Prochlorococcus",
        "species": "Prochlorococcus marinus", "strain": "MED4", "clade": "HLI",
        "ncbi_taxon_id": 59919, "gene_count": 1976, "publication_count": 11,
        "experiment_count": 46,
        "treatment_types": ["coculture", "light_stress"],
        "omics_types": ["RNASEQ", "PROTEOMICS"],
    }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, mock_ctx):
        """Response has total_entries, returned, truncated, results."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={"total_entries": 15, "returned": 1, "truncated": True, "results": [self._SAMPLE_ORG]},
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        assert result.total_entries == 15
        assert result.returned == 1
        assert result.truncated is True  # 15 > 1
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_expected_columns_compact(self, tool_fns, mock_ctx):
        """Compact result has 11 fields, no taxonomy hierarchy."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={"total_entries": 1, "returned": 1, "truncated": False, "results": [self._SAMPLE_ORG]},
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        org = result.results[0]
        for col in ["organism_name", "genus", "species", "strain", "clade",
                     "ncbi_taxon_id", "gene_count", "publication_count",
                     "experiment_count", "treatment_types", "omics_types"]:
            assert hasattr(org, col)

    @pytest.mark.asyncio
    async def test_expected_columns_verbose(self, tool_fns, mock_ctx):
        """Verbose result includes taxonomy hierarchy fields."""
        verbose_org = {**self._SAMPLE_ORG,
                       "family": "Prochlorococcaceae", "order": "Synechococcales",
                       "tax_class": "Cyanophyceae", "phylum": "Cyanobacteriota",
                       "kingdom": "Bacillati", "superkingdom": "Bacteria",
                       "lineage": "cellular organisms; Bacteria; ..."}
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={"total_entries": 1, "returned": 1, "truncated": False, "results": [verbose_org]},
        ):
            result = await tool_fns["list_organisms"](mock_ctx, verbose=True)
        org = result.results[0]
        assert org.family == "Prochlorococcaceae"
        assert org.lineage == "cellular organisms; Bacteria; ..."

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        """Empty results return envelope with total_entries=0."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={"total_entries": 0, "returned": 0, "truncated": False, "results": []},
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        assert result.total_entries == 0
        assert result.returned == 0
        assert result.truncated is False
        assert result.results == []

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        """returned == len(results), truncated == (total > returned)."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={"total_entries": 2, "returned": 2, "truncated": False, "results": [self._SAMPLE_ORG, self._SAMPLE_ORG]},
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        assert result.returned == 2
        assert result.truncated is False  # 2 == 2

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 10, "returned": 2,
                "truncated": True, "offset": 5, "results": [],
            },
        ) as mock_api:
            result = await tool_fns["list_organisms"](mock_ctx, offset=5)
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# resolve_gene
# ---------------------------------------------------------------------------
class TestResolveGeneWrapper:
    @pytest.mark.asyncio
    async def test_single_match_returns_response(self, tool_fns, mock_ctx):
        """Mock API returns single result, verify response model fields."""
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={
                "total_matching": 1, "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}], "returned": 1, "truncated": False,
                "results": [
                    {"locus_tag": "PMM0001", "gene_name": "dnaN",
                     "product": "DNA pol III beta",
                     "organism_name": "Prochlorococcus MED4"},
                ],
            },
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="PMM0001")

        assert result.total_matching == 1
        assert result.returned == 1
        assert result.truncated is False
        assert len(result.results) == 1
        r = result.results[0]
        assert r.locus_tag == "PMM0001"
        assert r.gene_name == "dnaN"
        assert r.product == "DNA pol III beta"
        assert r.organism_name == "Prochlorococcus MED4"

    @pytest.mark.asyncio
    async def test_not_found_empty_results(self, tool_fns, mock_ctx):
        """Mock API returns no results, verify empty response."""
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 0, "by_organism": [], "returned": 0, "truncated": False, "results": []},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="FAKE_GENE")

        assert result.total_matching == 0
        assert result.returned == 0
        assert result.results == []

    @pytest.mark.asyncio
    async def test_multi_match_flat_list(self, tool_fns, mock_ctx):
        """Multiple results from different organisms are a flat list, not grouped."""
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={
                "total_matching": 3, "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}, {"organism_name": "Prochlorococcus MIT9312", "count": 1}, {"organism_name": "Synechococcus WH8102", "count": 1}], "returned": 3, "truncated": False,
                "results": [
                    {"locus_tag": "PMM0001", "gene_name": "dnaN",
                     "product": "p1", "organism_name": "Prochlorococcus MED4"},
                    {"locus_tag": "PMT9312_0001", "gene_name": "dnaN",
                     "product": "p2", "organism_name": "Prochlorococcus MIT9312"},
                    {"locus_tag": "SYNW0305", "gene_name": None,
                     "product": "p3", "organism_name": "Synechococcus WH8102"},
                ],
            },
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="dnaN")

        assert result.total_matching == 3
        assert result.returned == 3
        assert len(result.results) == 3
        # Flat list — each entry has organism_name as an attribute
        organisms = {r.organism_name for r in result.results}
        assert organisms == {"Prochlorococcus MED4", "Prochlorococcus MIT9312", "Synechococcus WH8102"}

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """Verify identifier, organism, limit are all passed through to API."""
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 0, "by_organism": [], "returned": 0, "truncated": False, "results": []},
        ) as mock_api:
            await tool_fns["resolve_gene"](
                mock_ctx, identifier="dnaN", organism="MED4", limit=10,
            )

        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        assert call_kwargs.args[0] == "dnaN" or call_kwargs.kwargs.get("identifier") == "dnaN"
        assert call_kwargs.kwargs["organism"] == "MED4"
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        """When total_matching > returned, truncated=True."""
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={
                "total_matching": 5, "by_organism": [{"organism_name": "Org1", "count": 3}, {"organism_name": "Org2", "count": 2}], "returned": 2, "truncated": True,
                "results": [
                    {"locus_tag": "PMM0001", "gene_name": "a",
                     "product": "p1", "organism_name": "Org1"},
                    {"locus_tag": "PMM0002", "gene_name": "b",
                     "product": "p2", "organism_name": "Org2"},
                ],
            },
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="dnaN")

        assert result.total_matching == 5
        assert result.returned == 2
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_empty_identifier_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            side_effect=ValueError("identifier must not be empty."),
        ):
            with pytest.raises(ToolError):
                await tool_fns["resolve_gene"](mock_ctx, identifier="")

    @pytest.mark.asyncio
    async def test_generic_error_raises_tool_error(self, tool_fns, mock_ctx):
        """RuntimeError from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            side_effect=RuntimeError("timeout"),
        ):
            with pytest.raises(ToolError, match="Error in resolve_gene"):
                await tool_fns["resolve_gene"](mock_ctx, identifier="PMM0001")

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={
                "total_matching": 10, "by_organism": [], "returned": 2,
                "truncated": True, "offset": 5, "results": [],
            },
        ) as mock_api:
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="x", offset=5)
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5 or (len(mock_api.call_args.args) > 3 and mock_api.call_args.args[3] == 5)


# ---------------------------------------------------------------------------
# genes_by_function
# ---------------------------------------------------------------------------
class TestGenesByFunctionWrapper:
    _SAMPLE_API_RETURN = {
        "total_search_hits": 100,
        "total_matching": 5,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 3},
                        {"organism_name": "Synechococcus WH8102", "count": 2}],
        "by_category": [{"category": "DNA replication", "count": 3},
                        {"category": "Photosynthesis", "count": 2}],
        "score_max": 8.5,
        "score_median": 4.2,
        "returned": 2,
        "truncated": True,
        "results": [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "DNA polymerase III subunit beta",
             "organism_name": "Prochlorococcus MED4",
             "gene_category": "DNA replication",
             "annotation_quality": 3, "score": 5.0},
            {"locus_tag": "SYNW0305", "gene_name": "ftsH1",
             "product": "ATP-dependent metalloprotease FtsH",
             "organism_name": "Synechococcus WH8102",
             "gene_category": None,
             "annotation_quality": 2, "score": 3.5},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_pydantic_envelope(self, tool_fns, mock_ctx):
        """Response has total_search_hits, total_matching, by_organism, by_category, score_max, score_median, returned, truncated, results."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_function"](
                mock_ctx, search_text="DNA polymerase",
            )
        assert result.total_search_hits == 100
        assert result.total_matching == 5
        assert result.returned == 2
        assert result.truncated is True
        assert result.score_max == 8.5
        assert result.score_median == 4.2
        assert len(result.by_organism) == 2
        assert result.by_organism[0].organism_name == "Prochlorococcus MED4"
        assert len(result.by_category) == 2
        assert len(result.results) == 2
        r = result.results[0]
        assert r.locus_tag == "PMM0001"
        assert r.gene_name == "dnaN"
        assert r.gene_category == "DNA replication"

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        """When api returns no matches."""
        empty_return = {
            **self._SAMPLE_API_RETURN,
            "total_search_hits": 50,
            "total_matching": 0,
            "by_organism": [],
            "by_category": [],
            "score_max": None,
            "score_median": None,
            "returned": 0,
            "truncated": False,
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            return_value=empty_return,
        ):
            result = await tool_fns["genes_by_function"](
                mock_ctx, search_text="nonexistent",
            )
        assert result.total_matching == 0
        assert result.returned == 0
        assert result.results == []

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All params passed through to api."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            return_value={**self._SAMPLE_API_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["genes_by_function"](
                mock_ctx,
                search_text="photosystem",
                organism="MED4",
                category="Photosynthesis",
                min_quality=2,
                summary=True,
                verbose=True,
                limit=10,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        assert call_kwargs.args[0] == "photosystem"
        assert call_kwargs.kwargs["organism"] == "MED4"
        assert call_kwargs.kwargs["category"] == "Photosynthesis"
        assert call_kwargs.kwargs["min_quality"] == 2
        assert call_kwargs.kwargs["summary"] is True
        assert call_kwargs.kwargs["verbose"] is True
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        """returned/truncated from api are preserved when total_matching > returned."""
        truncated_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 50,
            "returned": 5,
            "truncated": True,
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            return_value=truncated_return,
        ):
            result = await tool_fns["genes_by_function"](
                mock_ctx, search_text="photosystem",
            )
        assert result.total_matching == 50
        assert result.returned == 5
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_error_raises_tool_error(self, tool_fns, mock_ctx):
        """Exception from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            side_effect=Exception("something broke"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["genes_by_function"](
                    mock_ctx, search_text="test",
                )

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            return_value={**self._SAMPLE_API_RETURN, "offset": 5},
        ) as mock_api:
            result = await tool_fns["genes_by_function"](mock_ctx, search_text="dna", offset=5)
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# gene_overview
# ---------------------------------------------------------------------------
class TestGeneOverviewWrapper:
    _SAMPLE_API_RETURN = {
        "total_matching": 2,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1},
                        {"organism_name": "Alteromonas EZ55", "count": 1}],
        "by_category": [{"category": "DNA replication", "count": 1},
                        {"category": "Unknown", "count": 1}],
        "by_annotation_type": [{"annotation_type": "go_bp", "count": 1}],
        "has_expression": 1,
        "has_significant_expression": 1,
        "has_orthologs": 2,
        "returned": 2,
        "truncated": False,
        "not_found": [],
        "results": [
            {"locus_tag": "PMM1428", "gene_name": "test", "product": "test product",
             "gene_category": "DNA replication", "annotation_quality": 3,
             "organism_name": "Prochlorococcus MED4",
             "annotation_types": ["go_bp"], "expression_edge_count": 36,
             "significant_up_count": 3, "significant_down_count": 2, "closest_ortholog_group_size": 9,
             "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"]},
            {"locus_tag": "EZ55_00275", "gene_name": None, "product": "hypothetical",
             "gene_category": "Unknown", "annotation_quality": 0,
             "organism_name": "Alteromonas EZ55",
             "annotation_types": [], "expression_edge_count": 0,
             "significant_up_count": 0, "significant_down_count": 0, "closest_ortholog_group_size": 1,
             "closest_ortholog_genera": []},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_pydantic_response(self, tool_fns, mock_ctx):
        """Response is a Pydantic model with envelope fields."""
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMM1428", "EZ55_00275"],
            )
        assert result.total_matching == 2
        assert result.returned == 2
        assert result.truncated is False
        assert len(result.results) == 2
        r = result.results[0]
        assert r.locus_tag == "PMM1428"
        assert r.expression_edge_count == 36
        assert len(result.by_organism) == 2
        assert result.by_organism[0].organism_name == "Prochlorococcus MED4"
        assert len(result.by_category) == 2
        assert len(result.by_annotation_type) == 1
        assert result.has_expression == 1
        assert result.has_orthologs == 2

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        """When no genes found, not_found populated."""
        empty_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 0,
            "by_organism": [],
            "by_category": [],
            "by_annotation_type": [],
            "has_expression": 0,
            "has_significant_expression": 0,
            "has_orthologs": 0,
            "returned": 0,
            "truncated": False,
            "not_found": ["FAKE0001"],
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=empty_return,
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["FAKE0001"],
            )
        assert result.total_matching == 0
        assert result.returned == 0
        assert result.results == []
        assert result.not_found == ["FAKE0001"]

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All params passed through to api."""
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value={**self._SAMPLE_API_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["gene_overview"](
                mock_ctx,
                locus_tags=["PMM1428", "EZ55_00275"],
                summary=True,
                verbose=True,
                limit=10,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        assert call_kwargs.args[0] == ["PMM1428", "EZ55_00275"]
        assert call_kwargs.kwargs["summary"] is True
        assert call_kwargs.kwargs["verbose"] is True
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        """returned/truncated from api are preserved."""
        truncated_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 10,
            "returned": 2,
            "truncated": True,
        }
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=truncated_return,
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMM1428"],
            )
        assert result.total_matching == 10
        assert result.returned == 2
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value={**self._SAMPLE_API_RETURN, "offset": 5},
        ) as mock_api:
            result = await tool_fns["gene_overview"](mock_ctx, locus_tags=["PMM1428"], offset=5)
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


class TestGeneDetailsWrapper:
    @pytest.mark.asyncio
    async def test_returns_pydantic_model(self, tool_fns, mock_ctx):
        """V3: returns GeneDetailResponse Pydantic model."""
        gene_data = {"locus_tag": "PMM0001", "product": "test", "organism_name": "Prochlorococcus MED4"}
        with patch(
            "multiomics_explorer.api.functions.gene_details",
            return_value={
                "total_matching": 1, "returned": 1, "truncated": False,
                "not_found": [], "results": [gene_data],
            },
        ):
            result = await tool_fns["gene_details"](mock_ctx, locus_tags=["PMM0001"])
        assert hasattr(result, "total_matching")
        assert result.total_matching == 1
        assert result.results[0]["locus_tag"] == "PMM0001"

    @pytest.mark.asyncio
    async def test_not_found_in_envelope(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_details",
            return_value={
                "total_matching": 0, "returned": 0, "truncated": False,
                "not_found": ["FAKE"], "results": [],
            },
        ):
            result = await tool_fns["gene_details"](mock_ctx, locus_tags=["FAKE"])
        assert result.not_found == ["FAKE"]
        assert result.results == []

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_details",
            return_value={
                "total_matching": 1, "returned": 1, "truncated": False,
                "offset": 5, "not_found": [], "results": [],
            },
        ) as mock_api:
            result = await tool_fns["gene_details"](mock_ctx, locus_tags=["PMM0001"], offset=5)
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# gene_homologs
# ---------------------------------------------------------------------------
class TestGeneHomologsWrapper:
    _SAMPLE_API_RETURN = {
        "total_matching": 2,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1},
                        {"organism_name": "Synechococcus WH8102", "count": 1}],
        "by_source": [{"source": "cyanorak", "count": 2}],
        "returned": 2,
        "truncated": False,
        "not_found": [],
        "no_groups": [],
        "results": [
            {"locus_tag": "PMM0001", "organism_name": "Prochlorococcus MED4",
             "group_id": "cyanorak:CK_00000364", "consensus_gene_name": "dnaN",
             "consensus_product": "DNA polymerase III subunit beta",
             "taxonomic_level": "curated", "source": "cyanorak",
             "specificity_rank": 0},
            {"locus_tag": "SYNW0305", "organism_name": "Synechococcus WH8102",
             "group_id": "cyanorak:CK_00000364", "consensus_gene_name": "dnaN",
             "consensus_product": "DNA polymerase III subunit beta",
             "taxonomic_level": "curated", "source": "cyanorak",
             "specificity_rank": 0},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, mock_ctx):
        """Response has total_matching, by_organism, by_source, returned, truncated, results."""
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["gene_homologs"](
                mock_ctx, locus_tags=["PMM0001"],
            )
        assert result.total_matching == 2
        assert result.returned == 2
        assert result.truncated is False
        assert len(result.results) == 2
        r = result.results[0]
        assert r.locus_tag == "PMM0001"
        assert r.group_id == "cyanorak:CK_00000364"
        assert r.consensus_gene_name == "dnaN"
        assert r.source == "cyanorak"

    @pytest.mark.asyncio
    async def test_summary_mode(self, tool_fns, mock_ctx):
        """summary=True returns results=[]."""
        summary_return = {
            **self._SAMPLE_API_RETURN,
            "returned": 0,
            "truncated": True,
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            return_value=summary_return,
        ):
            result = await tool_fns["gene_homologs"](
                mock_ctx, locus_tags=["PMM0001"], summary=True,
            )
        assert result.returned == 0
        assert result.truncated is True
        assert result.results == []

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All params passed through to api."""
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            return_value={**self._SAMPLE_API_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["gene_homologs"](
                mock_ctx,
                locus_tags=["PMM0001", "PMM0845"],
                source="cyanorak",
                taxonomic_level="curated",
                max_specificity_rank=0,
                summary=False,
                verbose=True,
                limit=10,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        assert call_kwargs.args[0] == ["PMM0001", "PMM0845"]
        assert call_kwargs.kwargs["source"] == "cyanorak"
        assert call_kwargs.kwargs["taxonomic_level"] == "curated"
        assert call_kwargs.kwargs["max_specificity_rank"] == 0
        assert call_kwargs.kwargs["summary"] is False
        assert call_kwargs.kwargs["verbose"] is True
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        """returned/truncated from api are preserved."""
        truncated_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 10,
            "returned": 2,
            "truncated": True,
        }
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            return_value=truncated_return,
        ):
            result = await tool_fns["gene_homologs"](
                mock_ctx, locus_tags=["PMM0001"],
            )
        assert result.total_matching == 10
        assert result.returned == 2
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_not_found_and_no_groups(self, tool_fns, mock_ctx):
        """not_found and no_groups fields present in response."""
        data = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 0,
            "returned": 0,
            "truncated": False,
            "not_found": ["FAKE0001"],
            "no_groups": ["PMM9999"],
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            return_value=data,
        ):
            result = await tool_fns["gene_homologs"](
                mock_ctx, locus_tags=["FAKE0001", "PMM9999"],
            )
        assert "FAKE0001" in result.not_found
        assert "PMM9999" in result.no_groups

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            side_effect=ValueError("Invalid source 'bad'. Valid: ['cyanorak', 'eggnog']"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["gene_homologs"](
                    mock_ctx, locus_tags=["PMM0001"], source="bad",
                )

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            return_value={**self._SAMPLE_API_RETURN, "offset": 5},
        ) as mock_api:
            result = await tool_fns["gene_homologs"](mock_ctx, locus_tags=["PMM0001"], offset=5)
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# run_cypher
# ---------------------------------------------------------------------------

_CYPHER_MOD = "multiomics_explorer.api.functions"


def _patch_cyver_valid(sv_cls, schv_cls, pv_cls):
    sv_cls.return_value.validate.return_value = (True, [])
    schv_cls.return_value.validate.return_value = (1.0, [])
    pv_cls.return_value.validate.return_value = (1.0, [])


class TestRunCypherWrapper:
    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = [{"n": 1}]
        with patch(f"{_CYPHER_MOD}.SyntaxValidator") as sv, \
             patch(f"{_CYPHER_MOD}.SchemaValidator") as schv, \
             patch(f"{_CYPHER_MOD}.PropertiesValidator") as pv:
            _patch_cyver_valid(sv, schv, pv)
            response = await tool_fns["run_cypher"](mock_ctx, query="MATCH (n) RETURN n")
        assert hasattr(response, "returned")
        assert hasattr(response, "truncated")
        assert hasattr(response, "warnings")
        assert hasattr(response, "results")

    @pytest.mark.asyncio
    async def test_write_blocked_raises_tool_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with pytest.raises(ToolError, match="Write operations"):
            await tool_fns["run_cypher"](mock_ctx, query="CREATE (n:Gene {name: 'x'})")
        _conn_from(mock_ctx).execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_syntax_error_raises_tool_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(f"{_CYPHER_MOD}.SyntaxValidator") as sv:
            sv.return_value.validate.return_value = (False, [{"description": "Invalid input 'MATC'"}])
            with pytest.raises(ToolError, match="Syntax error"):
                await tool_fns["run_cypher"](mock_ctx, query="MATC (n) RETURNN n")

    @pytest.mark.asyncio
    async def test_cyver_exception_raises_tool_error(self, tool_fns, mock_ctx):
        """CyVer validator throwing an unexpected exception surfaces as ToolError."""
        from fastmcp.exceptions import ToolError
        with patch(f"{_CYPHER_MOD}.SyntaxValidator") as sv:
            sv.return_value.validate.side_effect = RuntimeError("CyVer internal error")
            with pytest.raises(ToolError):
                await tool_fns["run_cypher"](mock_ctx, query="MATCH (n) RETURN n")

    @pytest.mark.asyncio
    async def test_limit_forwarded(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        with patch(f"{_CYPHER_MOD}.SyntaxValidator") as sv, \
             patch(f"{_CYPHER_MOD}.SchemaValidator") as schv, \
             patch(f"{_CYPHER_MOD}.PropertiesValidator") as pv:
            _patch_cyver_valid(sv, schv, pv)
            await tool_fns["run_cypher"](mock_ctx, query="MATCH (n) RETURN n", limit=10)
        called_query = _conn_from(mock_ctx).execute_query.call_args[0][0]
        assert "LIMIT 10" in called_query

    @pytest.mark.asyncio
    async def test_warnings_in_response(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        with patch(f"{_CYPHER_MOD}.SyntaxValidator") as sv, \
             patch(f"{_CYPHER_MOD}.SchemaValidator") as schv, \
             patch(f"{_CYPHER_MOD}.PropertiesValidator") as pv:
            sv.return_value.validate.return_value = (True, [])
            schv.return_value.validate.return_value = (0.5, [{"description": "Label Foo not in database"}])
            pv.return_value.validate.return_value = (1.0, [])
            response = await tool_fns["run_cypher"](mock_ctx, query="MATCH (n:Foo) RETURN n")
        assert response.warnings == ["Label Foo not in database"]

    @pytest.mark.asyncio
    async def test_empty_warnings_when_valid(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = [{"n": 1}]
        with patch(f"{_CYPHER_MOD}.SyntaxValidator") as sv, \
             patch(f"{_CYPHER_MOD}.SchemaValidator") as schv, \
             patch(f"{_CYPHER_MOD}.PropertiesValidator") as pv:
            _patch_cyver_valid(sv, schv, pv)
            response = await tool_fns["run_cypher"](mock_ctx, query="MATCH (n) RETURN n")
        assert response.warnings == []

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        with patch(f"{_CYPHER_MOD}.SyntaxValidator") as sv, \
             patch(f"{_CYPHER_MOD}.SchemaValidator") as schv, \
             patch(f"{_CYPHER_MOD}.PropertiesValidator") as pv:
            _patch_cyver_valid(sv, schv, pv)
            response = await tool_fns["run_cypher"](mock_ctx, query="MATCH (n:Fake) RETURN n")
        assert response.returned == 0
        assert response.results == []

    @pytest.mark.asyncio
    async def test_generic_error_raises_tool_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(f"{_CYPHER_MOD}.SyntaxValidator") as sv, \
             patch(f"{_CYPHER_MOD}.SchemaValidator") as schv, \
             patch(f"{_CYPHER_MOD}.PropertiesValidator") as pv:
            _patch_cyver_valid(sv, schv, pv)
            _conn_from(mock_ctx).execute_query.side_effect = RuntimeError("timeout")
            with pytest.raises(ToolError, match="Error in run_cypher"):
                await tool_fns["run_cypher"](mock_ctx, query="MATCH (n) RETURN n")


# ---------------------------------------------------------------------------
# search_ontology
# ---------------------------------------------------------------------------
class TestSearchOntologyWrapper:
    _SAMPLE_API_RETURN = {
        "total_entries": 847,
        "total_matching": 2,
        "score_max": 5.0,
        "score_median": 3.2,
        "returned": 2,
        "truncated": False,
        "results": [
            {"id": "go:0006260", "name": "DNA replication", "score": 5.0},
            {"id": "go:0006261", "name": "DNA-templated DNA replication", "score": 3.2},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_dict_envelope(self, tool_fns, mock_ctx):
        """Response has total_entries, total_matching, score_max, score_median, returned, truncated, results."""
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="replication", ontology="go_bp",
            )
        assert result.total_entries == 847
        assert result.total_matching == 2
        assert result.returned == 2
        assert result.truncated is False
        assert result.score_max == 5.0
        assert result.score_median == 3.2
        assert len(result.results) == 2
        r = result.results[0]
        assert r.id == "go:0006260"
        assert r.name == "DNA replication"
        assert r.score == 5.0

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        """When api returns no matches."""
        empty_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 0,
            "score_max": None,
            "score_median": None,
            "returned": 0,
            "truncated": False,
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=empty_return,
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="nonexistent", ontology="go_bp",
            )
        assert result.total_matching == 0
        assert result.returned == 0
        assert result.results == []

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All params passed through to api."""
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={**self._SAMPLE_API_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["search_ontology"](
                mock_ctx,
                search_text="replication",
                ontology="go_bp",
                summary=True,
                limit=10,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        assert call_kwargs.args[0] == "replication"
        assert call_kwargs.args[1] == "go_bp"
        assert call_kwargs.kwargs["summary"] is True
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        """returned/truncated from api are preserved when total_matching > returned."""
        truncated_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 50,
            "returned": 2,
            "truncated": True,
        }
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=truncated_return,
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="replication", ontology="go_bp",
            )
        assert result.total_matching == 50
        assert result.returned == 2
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_invalid_ontology_raises_toolerror(self, tool_fns, mock_ctx):
        """ValueError from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            side_effect=ValueError("Invalid ontology 'bad'"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["search_ontology"](
                    mock_ctx, search_text="test", ontology="bad",
                )

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={**self._SAMPLE_API_RETURN, "offset": 5},
        ) as mock_api:
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="replication", ontology="go_bp", offset=5,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# genes_by_ontology
# ---------------------------------------------------------------------------
class TestGenesByOntologyWrapper:
    _SAMPLE_API_RETURN = {
        "total_matching": 2,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1},
                       {"organism_name": "Alteromonas macleodii MIT1002", "count": 1}],
        "by_category": [{"category": "Replication and repair", "count": 2}],
        "by_term": [{"term_id": "go:0006260", "count": 2}],
        "returned": 2,
        "truncated": False,
        "results": [
            {"locus_tag": "PMM0120", "gene_name": "dnaN", "product": "p1",
             "organism_name": "Prochlorococcus MED4",
             "gene_category": "Replication and repair"},
            {"locus_tag": "MIT1002_00001", "gene_name": "geneA", "product": "p2",
             "organism_name": "Alteromonas macleodii MIT1002",
             "gene_category": "Translation"},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_dict_envelope(self, tool_fns, mock_ctx):
        """Response has total_matching, by_organism, by_category, by_term, returned, truncated, results."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_ontology"](
                mock_ctx, term_ids=["go:0006260"], ontology="go_bp",
            )
        assert result.total_matching == 2
        assert result.returned == 2
        assert result.truncated is False
        assert len(result.by_organism) == 2
        assert result.by_organism[0].organism_name == "Prochlorococcus MED4"
        assert len(result.by_category) == 1
        assert len(result.by_term) == 1
        assert result.by_term[0].term_id == "go:0006260"
        assert len(result.results) == 2
        r = result.results[0]
        assert r.locus_tag == "PMM0120"
        assert r.gene_name == "dnaN"
        assert r.gene_category == "Replication and repair"

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        """When api returns no matches."""
        empty_return = {
            "total_matching": 0,
            "by_organism": [],
            "by_category": [],
            "by_term": [],
            "returned": 0,
            "truncated": False,
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value=empty_return,
        ):
            result = await tool_fns["genes_by_ontology"](
                mock_ctx, term_ids=["go:9999999"], ontology="go_bp",
            )
        assert result.total_matching == 0
        assert result.returned == 0
        assert result.results == []

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All params passed through to api."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value={**self._SAMPLE_API_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["genes_by_ontology"](
                mock_ctx,
                term_ids=["go:0006260"],
                ontology="go_bp",
                organism="MED4",
                summary=True,
                verbose=True,
                limit=10,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        assert call_kwargs.args[0] == ["go:0006260"]
        assert call_kwargs.args[1] == "go_bp"
        assert call_kwargs.kwargs["organism"] == "MED4"
        assert call_kwargs.kwargs["summary"] is True
        assert call_kwargs.kwargs["verbose"] is True
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        """returned/truncated from api are preserved."""
        truncated_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 50,
            "returned": 2,
            "truncated": True,
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value=truncated_return,
        ):
            result = await tool_fns["genes_by_ontology"](
                mock_ctx, term_ids=["go:0006260"], ontology="go_bp",
            )
        assert result.total_matching == 50
        assert result.returned == 2
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_invalid_ontology_raises_toolerror(self, tool_fns, mock_ctx):
        """ValueError from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            side_effect=ValueError("Invalid ontology 'bad'"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["genes_by_ontology"](
                    mock_ctx, term_ids=["x"], ontology="go_bp",
                )

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value={**self._SAMPLE_API_RETURN, "offset": 5},
        ) as mock_api:
            result = await tool_fns["genes_by_ontology"](
                mock_ctx, term_ids=["go:0006260"], ontology="go_bp", offset=5,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# gene_ontology_terms
# ---------------------------------------------------------------------------
class TestGeneOntologyTermsWrapper:
    _SAMPLE_API_RETURN = {
        "total_matching": 2,
        "total_genes": 1,
        "total_terms": 2,
        "by_ontology": [{"ontology_type": "go_bp", "term_count": 2, "gene_count": 1}],
        "by_term": [{"term_id": "go:0006260", "term_name": "DNA replication",
                     "ontology_type": "go_bp", "count": 1}],
        "terms_per_gene_min": 2,
        "terms_per_gene_max": 2,
        "terms_per_gene_median": 2.0,
        "returned": 2,
        "truncated": False,
        "not_found": [],
        "no_terms": [],
        "results": [
            {"locus_tag": "PMM0001", "term_id": "go:0006260",
             "term_name": "DNA replication"},
            {"locus_tag": "PMM0001", "term_id": "go:0006271",
             "term_name": "DNA strand elongation"},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_pydantic_response(self, tool_fns, mock_ctx):
        """Response is a GeneOntologyTermsResponse Pydantic model."""
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["gene_ontology_terms"](
                mock_ctx, locus_tags=["PMM0001"],
            )
        assert type(result).__name__ == "GeneOntologyTermsResponse"

    @pytest.mark.asyncio
    async def test_has_expected_fields(self, tool_fns, mock_ctx):
        """Response has total_matching, by_ontology, results, etc."""
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["gene_ontology_terms"](
                mock_ctx, locus_tags=["PMM0001"],
            )
        assert result.total_matching == 2
        assert result.total_genes == 1
        assert result.total_terms == 2
        assert result.returned == 2
        assert result.truncated is False
        assert len(result.by_ontology) == 1
        assert result.by_ontology[0].ontology_type == "go_bp"
        assert result.by_ontology[0].term_count == 2
        assert result.by_ontology[0].gene_count == 1
        assert len(result.by_term) == 1
        assert result.by_term[0].term_id == "go:0006260"
        assert result.by_term[0].term_name == "DNA replication"
        assert result.terms_per_gene_min == 2
        assert result.terms_per_gene_max == 2
        assert result.terms_per_gene_median == 2.0
        assert result.not_found == []
        assert result.no_terms == []
        assert len(result.results) == 2
        r = result.results[0]
        assert r.locus_tag == "PMM0001"
        assert r.term_id == "go:0006260"
        assert r.term_name == "DNA replication"

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All params passed through to api."""
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value={**self._SAMPLE_API_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["gene_ontology_terms"](
                mock_ctx,
                locus_tags=["PMM0001"],
                ontology="go_bp",
                summary=True,
                verbose=True,
                limit=10,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        assert call_kwargs.args[0] == ["PMM0001"]
        assert call_kwargs.kwargs["ontology"] == "go_bp"
        assert call_kwargs.kwargs["summary"] is True
        assert call_kwargs.kwargs["verbose"] is True
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        """When no genes found, not_found populated."""
        empty_return = {
            "total_matching": 0,
            "total_genes": 0,
            "total_terms": 0,
            "by_ontology": [],
            "by_term": [],
            "terms_per_gene_min": 0,
            "terms_per_gene_max": 0,
            "terms_per_gene_median": 0.0,
            "returned": 0,
            "truncated": False,
            "not_found": ["FAKE0001"],
            "no_terms": [],
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value=empty_return,
        ):
            result = await tool_fns["gene_ontology_terms"](
                mock_ctx, locus_tags=["FAKE0001"],
            )
        assert result.total_matching == 0
        assert result.returned == 0
        assert result.results == []
        assert result.not_found == ["FAKE0001"]

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        """returned < total_matching means truncated=True."""
        truncated_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 50,
            "returned": 2,
            "truncated": True,
        }
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value=truncated_return,
        ):
            result = await tool_fns["gene_ontology_terms"](
                mock_ctx, locus_tags=["PMM0001"],
            )
        assert result.total_matching == 50
        assert result.returned == 2
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            side_effect=ValueError("Invalid ontology 'bad'"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["gene_ontology_terms"](
                    mock_ctx, locus_tags=["PMM0001"], ontology="go_bp",
                )

    @pytest.mark.asyncio
    async def test_generic_error_raises_tool_error(self, tool_fns, mock_ctx):
        """Generic Exception from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            side_effect=RuntimeError("timeout"),
        ):
            with pytest.raises(ToolError, match="Error in gene_ontology_terms"):
                await tool_fns["gene_ontology_terms"](
                    mock_ctx, locus_tags=["PMM0001"],
                )

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value={**self._SAMPLE_API_RETURN, "offset": 5},
        ) as mock_api:
            result = await tool_fns["gene_ontology_terms"](mock_ctx, locus_tags=["PMM0001"], offset=5)
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# Error handling — all tools catch exceptions and return error strings
# ---------------------------------------------------------------------------
class TestErrorHandling:
    """Every MCP tool must catch ValueError and Exception, returning an error string."""

    @pytest.mark.asyncio
    async def test_list_filter_values_generic_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            side_effect=RuntimeError("connection lost"),
        ):
            with pytest.raises(ToolError, match="Error in list_filter_values"):
                await tool_fns["list_filter_values"](mock_ctx)

    @pytest.mark.asyncio
    async def test_list_organisms_generic_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            side_effect=RuntimeError("timeout"),
        ):
            with pytest.raises(ToolError, match="Error in list_organisms"):
                await tool_fns["list_organisms"](mock_ctx)

    @pytest.mark.asyncio
    async def test_resolve_gene_value_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            side_effect=ValueError("identifier must not be empty."),
        ):
            with pytest.raises(ToolError):
                await tool_fns["resolve_gene"](mock_ctx, identifier="")

    @pytest.mark.asyncio
    async def test_resolve_gene_generic_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            side_effect=RuntimeError("timeout"),
        ):
            with pytest.raises(ToolError, match="Error in resolve_gene"):
                await tool_fns["resolve_gene"](mock_ctx, identifier="PMM0001")

    @pytest.mark.asyncio
    async def test_genes_by_function_value_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            side_effect=ValueError("bad input"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["genes_by_function"](mock_ctx, search_text="test")

    @pytest.mark.asyncio
    async def test_genes_by_function_generic_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            side_effect=RuntimeError("timeout"),
        ):
            with pytest.raises(ToolError, match="Error in genes_by_function"):
                await tool_fns["genes_by_function"](mock_ctx, search_text="test")

    @pytest.mark.asyncio
    async def test_gene_overview_generic_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            side_effect=RuntimeError("timeout"),
        ):
            with pytest.raises(ToolError, match="Error in gene_overview"):
                await tool_fns["gene_overview"](mock_ctx, locus_tags=["PMM0001"])

    @pytest.mark.asyncio
    async def test_gene_details_generic_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.gene_details",
            side_effect=RuntimeError("timeout"),
        ):
            with pytest.raises(ToolError, match="Error in gene_details"):
                await tool_fns["gene_details"](mock_ctx, locus_tags=["PMM0001"])

    @pytest.mark.asyncio
    async def test_gene_homologs_generic_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            side_effect=RuntimeError("timeout"),
        ):
            with pytest.raises(ToolError, match="Error in gene_homologs"):
                await tool_fns["gene_homologs"](mock_ctx, locus_tags=["PMM0001"])

    @pytest.mark.asyncio
    async def test_gene_homologs_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        """gene_homologs ValueError is converted to ToolError."""
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            side_effect=ValueError("Invalid source 'bad'. Valid: ['cyanorak', 'eggnog']"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["gene_homologs"](mock_ctx, locus_tags=["PMM0001"])

    @pytest.mark.asyncio
    async def test_search_ontology_value_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            side_effect=ValueError("Invalid ontology 'bad'"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["search_ontology"](
                    mock_ctx, search_text="test", ontology="bad",
                )

    @pytest.mark.asyncio
    async def test_genes_by_ontology_generic_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            side_effect=RuntimeError("timeout"),
        ):
            with pytest.raises(ToolError, match="Error in genes_by_ontology"):
                await tool_fns["genes_by_ontology"](
                    mock_ctx, term_ids=["go:0006260"], ontology="go_bp",
                )

    @pytest.mark.asyncio
    async def test_gene_ontology_terms_generic_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            side_effect=RuntimeError("timeout"),
        ):
            with pytest.raises(ToolError, match="Error in gene_ontology_terms"):
                await tool_fns["gene_ontology_terms"](
                    mock_ctx, locus_tags=["PMM0001"],
                )


# ---------------------------------------------------------------------------
# list_publications
# ---------------------------------------------------------------------------
class TestListPublicationsWrapper:
    _SAMPLE_PUB = {
        "doi": "10.1234/a", "title": "Paper A",
        "authors": ["Author One"], "year": 2025,
        "journal": "J Test", "study_type": "RNA-seq",
        "organisms": ["Prochlorococcus MED4"],
        "experiment_count": 3, "treatment_types": ["coculture"],
        "omics_types": ["RNASEQ"],
    }

    @pytest.mark.asyncio
    async def test_returns_dict_envelope(self, tool_fns, mock_ctx):
        """Response has total_entries, total_matching, returned, truncated, results."""
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 21,
                "total_matching": 21,
                "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
                "by_treatment_type": [{"treatment_type": "coculture", "count": 1}],
                "by_omics_type": [{"omics_type": "RNASEQ", "count": 1}],
                "returned": 1,
                "truncated": True,
                "results": [self._SAMPLE_PUB],
            },
        ):
            result = await tool_fns["list_publications"](mock_ctx)
        assert result.total_entries == 21
        assert result.total_matching == 21
        assert result.returned == 1
        assert result.truncated is True  # 21 > 1
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        """Empty results return envelope with returned=0."""
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 21,
                "total_matching": 0,
                "by_organism": [], "by_treatment_type": [], "by_omics_type": [],
                "returned": 0,
                "truncated": False,
                "results": [],
            },
        ):
            result = await tool_fns["list_publications"](mock_ctx)
        assert result.returned == 0
        assert result.truncated is False
        assert result.results == []

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All params passed through to api."""
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={"total_entries": 0, "total_matching": 0, "by_organism": [], "by_treatment_type": [], "by_omics_type": [], "returned": 0, "truncated": False, "results": []},
        ) as mock_api:
            await tool_fns["list_publications"](
                mock_ctx,
                organism="MED4",
                treatment_type="coculture",
                search_text="nitrogen",
                author="Sher",
                verbose=True,
                limit=10,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        assert call_kwargs.kwargs["organism"] == "MED4"
        assert call_kwargs.kwargs["treatment_type"] == "coculture"
        assert call_kwargs.kwargs["search_text"] == "nitrogen"
        assert call_kwargs.kwargs["author"] == "Sher"
        assert call_kwargs.kwargs["verbose"] is True
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        """returned == len(results), truncated == (total_matching > returned)."""
        pubs = [{**self._SAMPLE_PUB, "doi": f"10.1234/{i}"} for i in range(8)]
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 50,
                "total_matching": 8,
                "by_organism": [], "by_treatment_type": [], "by_omics_type": [],
                "returned": 8,
                "truncated": False,
                "results": pubs,
            },
        ):
            result = await tool_fns["list_publications"](mock_ctx)
        assert result.returned == 8
        assert result.returned == len(result.results)
        assert result.truncated is False  # 8 == 8
        assert result.total_entries == 50

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from api raises ToolError."""
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            side_effect=ValueError("bad param"),
        ):
            with pytest.raises(ToolError, match="bad param"):
                await tool_fns["list_publications"](mock_ctx)

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 20, "total_matching": 10,
                "by_organism": [], "by_treatment_type": [], "by_omics_type": [],
                "returned": 2, "truncated": True, "offset": 5, "results": [],
            },
        ) as mock_api:
            result = await tool_fns["list_publications"](mock_ctx, offset=5)
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


class TestListExperimentsWrapper:
    _SAMPLE_SUMMARY = {
        "total_entries": 76,
        "total_matching": 76,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 30}],
        "by_treatment_type": [{"treatment_type": "coculture", "count": 16}],
        "by_omics_type": [{"omics_type": "RNASEQ", "count": 48}],
        "by_publication": [{"publication_doi": "10.1038/ismej.2016.70", "count": 5}],
        "by_table_scope": [{"table_scope": "all_detected_genes", "count": 22}],
        "time_course_count": 29,
        "score_max": None,
        "score_median": None,
        "returned": 0,
        "truncated": True,
        "results": [],
    }

    _SAMPLE_EXP = {
        "experiment_id": "test_exp_1",
        "experiment_name": "MED4 Coculture with Alteromonas HOT1A3 (RNASEQ)",
        "publication_doi": "10.1234/test",
        "organism_name": "Prochlorococcus MED4",
        "treatment_type": "coculture",
        "coculture_partner": "Alteromonas macleodii HOT1A3",
        "omics_type": "RNASEQ",
        "is_time_course": False,
        "table_scope": "all_detected_genes",
        "table_scope_detail": None,
        "gene_count": 1696,
        "genes_by_status": {"significant_up": 245, "significant_down": 178, "not_significant": 1273},
    }

    @classmethod
    def _make_detail(cls, results=None):
        """Return a fresh detail dict (wrapper mutates via .pop)."""
        import copy
        if results is None:
            results = [copy.deepcopy(cls._SAMPLE_EXP)]
        return {**cls._SAMPLE_SUMMARY, "returned": len(results),
                "truncated": True, "results": results}

    @pytest.mark.asyncio
    async def test_summary_mode_empty_results(self, tool_fns, mock_ctx):
        """Summary mode returns breakdowns + results=[]."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._SAMPLE_SUMMARY,
        ):
            result = await tool_fns["list_experiments"](mock_ctx, summary=True)
        assert result.returned == 0
        assert result.truncated is True
        assert result.results == []
        assert len(result.by_organism) == 1
        assert result.by_organism[0].organism_name == "Prochlorococcus MED4"
        assert result.by_organism[0].count == 30
        assert result.time_course_count == 29

    @pytest.mark.asyncio
    async def test_detail_mode_has_results(self, tool_fns, mock_ctx):
        """Detail mode returns breakdowns + results."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_detail(),
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        assert result.returned == 1
        assert len(result.results) == 1
        assert result.results[0].experiment_id == "test_exp_1"
        # Breakdowns also present
        assert len(result.by_organism) == 1

    @pytest.mark.asyncio
    async def test_default_is_detail(self, tool_fns, mock_ctx):
        """No summary param defaults to detail (summary=False)."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_detail(),
        ) as mock_api:
            await tool_fns["list_experiments"](mock_ctx)
        call_kwargs = mock_api.call_args[1]
        assert call_kwargs["summary"] is False

    @pytest.mark.asyncio
    async def test_both_modes_have_breakdowns(self, tool_fns, mock_ctx):
        """Breakdowns populated in both summary and detail."""
        for summary_val, api_result in [
            (True, self._SAMPLE_SUMMARY),
            (False, self._make_detail()),
        ]:
            with patch(
                "multiomics_explorer.api.functions.list_experiments",
                return_value=api_result,
            ):
                result = await tool_fns["list_experiments"](mock_ctx, summary=summary_val)
            assert len(result.by_organism) > 0
            assert len(result.by_treatment_type) > 0
            assert len(result.by_omics_type) > 0
            assert len(result.by_publication) > 0
            assert len(result.by_table_scope) > 0

    @pytest.mark.asyncio
    async def test_detail_empty_results(self, tool_fns, mock_ctx):
        """Detail mode with no matches returns empty results."""
        empty = {**self._SAMPLE_SUMMARY,
                 "total_matching": 0, "returned": 0, "truncated": False,
                 "by_organism": [], "by_treatment_type": [], "by_omics_type": [],
                 "by_publication": [], "by_table_scope": [],
                 "time_course_count": 0, "results": []}
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=empty,
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        assert result.returned == 0
        assert result.results == []

    @pytest.mark.asyncio
    async def test_detail_params_forwarded(self, tool_fns, mock_ctx):
        """All params passed through to api."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_detail(),
        ) as mock_api:
            await tool_fns["list_experiments"](
                mock_ctx,
                organism="MED4",
                treatment_type=["coculture"],
                omics_type=["RNASEQ"],
                publication_doi=["10.1234/test"],
                coculture_partner="Alteromonas",
                search_text="light",
                time_course_only=True,
                table_scope=["all_detected_genes"],
                verbose=True,
                limit=10,
            )
        kw = mock_api.call_args[1]
        assert kw["organism"] == "MED4"
        assert kw["treatment_type"] == ["coculture"]
        assert kw["omics_type"] == ["RNASEQ"]
        assert kw["publication_doi"] == ["10.1234/test"]
        assert kw["coculture_partner"] == "Alteromonas"
        assert kw["search_text"] == "light"
        assert kw["time_course_only"] is True
        assert kw["table_scope"] == ["all_detected_genes"]
        assert kw["summary"] is False
        assert kw["verbose"] is True
        assert kw["limit"] == 10

    @pytest.mark.asyncio
    async def test_detail_truncation_metadata(self, tool_fns, mock_ctx):
        """returned == len(results), truncated reflects total_matching."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_detail(),
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        assert result.returned == len(result.results)
        assert result.truncated is True  # 76 > 1

    @pytest.mark.asyncio
    async def test_detail_verbose_fields_present(self, tool_fns, mock_ctx):
        """verbose=True includes publication_title, treatment, etc. when present in api result."""
        import copy
        verbose_exp = {**copy.deepcopy(self._SAMPLE_EXP),
                       "publication_title": "Test paper",
                       "treatment": "Coculture", "control": "Axenic",
                       "light_condition": "continuous light"}
        detail = {**self._SAMPLE_SUMMARY, "returned": 1, "truncated": False,
                  "results": [verbose_exp]}
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=detail,
        ):
            result = await tool_fns["list_experiments"](mock_ctx, verbose=True)
        r = result.results[0]
        assert r.experiment_name == "MED4 Coculture with Alteromonas HOT1A3 (RNASEQ)"
        assert r.publication_title == "Test paper"
        assert r.light_condition == "continuous light"

    @pytest.mark.asyncio
    async def test_detail_verbose_fields_absent(self, tool_fns, mock_ctx):
        """verbose=False: verbose-only fields are None."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_detail(),
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        r = result.results[0]
        assert r.publication_title is None
        assert r.light_condition is None

    @pytest.mark.asyncio
    async def test_summary_with_filters(self, tool_fns, mock_ctx):
        """Filters applied to summary breakdowns."""
        filtered = {**self._SAMPLE_SUMMARY, "total_matching": 30}
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=filtered,
        ):
            result = await tool_fns["list_experiments"](mock_ctx, organism="MED4")
        assert result.total_matching == 30

    @pytest.mark.asyncio
    async def test_timepoints_model(self, tool_fns, mock_ctx):
        """timepoints assembled into TimePoint models."""
        import copy
        tc_exp = {
            **copy.deepcopy(self._SAMPLE_EXP),
            "is_time_course": True,
            "timepoints": [
                {"timepoint": "2h", "timepoint_order": 1, "timepoint_hours": 2.0,
                 "gene_count": 353, "genes_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 353}},
                {"timepoint": "24h", "timepoint_order": 2, "timepoint_hours": 24.0,
                 "gene_count": 353, "genes_by_status": {"significant_up": 150, "significant_down": 108, "not_significant": 95}},
            ],
        }
        detail = {**self._SAMPLE_SUMMARY, "returned": 1, "truncated": False,
                  "results": [tc_exp]}
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=detail,
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        r = result.results[0]
        assert r.is_time_course is True
        assert len(r.timepoints) == 2
        assert r.timepoints[0].timepoint == "2h"
        assert r.timepoints[0].timepoint_hours == 2.0
        assert r.timepoints[1].genes_by_status.significant_up == 150
        assert r.timepoints[1].genes_by_status.significant_down == 108

    @pytest.mark.asyncio
    async def test_table_scope_filter_forwarded(self, tool_fns, mock_ctx):
        """table_scope filter passed through to api."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_detail(),
        ) as mock_api:
            await tool_fns["list_experiments"](
                mock_ctx, table_scope=["all_detected_genes", "significant_only"],
            )
        kw = mock_api.call_args[1]
        assert kw["table_scope"] == ["all_detected_genes", "significant_only"]

    @pytest.mark.asyncio
    async def test_by_table_scope_in_response(self, tool_fns, mock_ctx):
        """by_table_scope breakdown populated in response."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._SAMPLE_SUMMARY,
        ):
            result = await tool_fns["list_experiments"](mock_ctx, summary=True)
        assert len(result.by_table_scope) == 1
        assert result.by_table_scope[0].table_scope == "all_detected_genes"
        assert result.by_table_scope[0].count == 22

    @pytest.mark.asyncio
    async def test_genes_by_status_in_experiment(self, tool_fns, mock_ctx):
        """genes_by_status breakdown populated in experiment results."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_detail(),
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        r = result.results[0]
        assert r.genes_by_status.significant_up == 245
        assert r.genes_by_status.significant_down == 178
        assert r.genes_by_status.not_significant == 1273

    @pytest.mark.asyncio
    async def test_experiment_name_always_present(self, tool_fns, mock_ctx):
        """experiment_name is always present (compact field)."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_detail(),
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        r = result.results[0]
        assert r.experiment_name == "MED4 Coculture with Alteromonas HOT1A3 (RNASEQ)"

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from api raises ToolError."""
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            side_effect=ValueError("bad param"),
        ):
            with pytest.raises(ToolError, match="bad param"):
                await tool_fns["list_experiments"](mock_ctx)

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value={**self._SAMPLE_SUMMARY, "offset": 5},
        ) as mock_api:
            result = await tool_fns["list_experiments"](mock_ctx, offset=5)
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# differential_expression_by_gene
# ---------------------------------------------------------------------------
class TestDifferentialExpressionByGeneWrapper:
    _SAMPLE_API_RETURN = {
        "organism_name": "Prochlorococcus MED4",
        "matching_genes": 5,
        "total_matching": 15,
        "rows_by_status": {
            "significant_up": 3,
            "significant_down": 0,
            "not_significant": 12,
        },
        "median_abs_log2fc": 1.978,
        "max_abs_log2fc": 3.591,
        "experiment_count": 1,
        "rows_by_treatment_type": {"nitrogen_stress": 15},
        "by_table_scope": {"all_detected_genes": 15},
        "top_categories": [
            {"category": "Signal transduction",
             "total_genes": 2, "significant_genes": 2},
        ],
        "experiments": [
            {
                "experiment_id": "exp1",
                "experiment_name": "Test experiment",
                "treatment_type": "nitrogen_stress",
                "omics_type": "RNASEQ",
                "coculture_partner": None,
                "is_time_course": "true",
                "table_scope": "all_detected_genes",
                "table_scope_detail": None,
                "matching_genes": 5,
                "rows_by_status": {
                    "significant_up": 3,
                    "significant_down": 0,
                    "not_significant": 12,
                },
                "timepoints": [
                    {
                        "timepoint": "day 18",
                        "timepoint_hours": 432.0,
                        "timepoint_order": 1,
                        "matching_genes": 5,
                        "rows_by_status": {
                            "significant_up": 0,
                            "significant_down": 0,
                            "not_significant": 5,
                        },
                    },
                ],
            },
        ],
        "not_found": [],
        "no_expression": [],
        "returned": 1,
        "truncated": True,
        "results": [
            {
                "locus_tag": "PMM0001",
                "gene_name": "dnaN",
                "experiment_id": "exp1",
                "treatment_type": "nitrogen_stress",
                "timepoint": "day 18",
                "timepoint_hours": 432.0,
                "timepoint_order": 1,
                "log2fc": 3.591,
                "padj": 1.13e-12,
                "rank": 77,
                "expression_status": "significant_up",
            },
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        """API dict is converted to Pydantic response model."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4",
            )
        assert result.organism_name == "Prochlorococcus MED4"
        assert result.total_matching == 15
        assert result.matching_genes == 5
        assert result.returned == 1
        assert result.truncated is True
        assert len(result.results) == 1
        assert result.results[0].locus_tag == "PMM0001"
        assert result.results[0].expression_status == "significant_up"

    @pytest.mark.asyncio
    async def test_rows_by_status_model(self, tool_fns, mock_ctx):
        """rows_by_status converted to ExpressionStatusBreakdown."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4",
            )
        rbs = result.rows_by_status
        assert rbs.significant_up == 3
        assert rbs.significant_down == 0
        assert rbs.not_significant == 12

    @pytest.mark.asyncio
    async def test_experiments_with_timepoints(self, tool_fns, mock_ctx):
        """Experiment with nested timepoints rendered correctly."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4",
            )
        exp = result.experiments[0]
        assert exp.experiment_id == "exp1"
        assert exp.is_time_course == "true"
        assert exp.timepoints is not None
        assert len(exp.timepoints) == 1
        assert exp.timepoints[0].timepoint == "day 18"
        assert exp.timepoints[0].matching_genes == 5

    @pytest.mark.asyncio
    async def test_non_time_course_null_timepoints(self, tool_fns, mock_ctx):
        """Non-time-course experiment has timepoints=None."""
        data = {
            **self._SAMPLE_API_RETURN,
            "experiments": [
                {
                    **self._SAMPLE_API_RETURN["experiments"][0],
                    "is_time_course": "false",
                    "timepoints": None,
                },
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value=data,
        ):
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4",
            )
        assert result.experiments[0].timepoints is None

    @pytest.mark.asyncio
    async def test_summary_true_empty_results(self, tool_fns, mock_ctx):
        """summary=True returns results=[], returned=0."""
        data = {**self._SAMPLE_API_RETURN, "results": [], "returned": 0}
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value=data,
        ):
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4", summary=True,
            )
        assert result.results == []
        assert result.returned == 0

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            side_effect=ValueError("at least one"),
        ):
            with pytest.raises(ToolError, match="at least one"):
                await tool_fns["differential_expression_by_gene"](
                    mock_ctx, organism="ZZZZZ",
                )

    @pytest.mark.asyncio
    async def test_no_filters_raises_tool_error(self, tool_fns, mock_ctx):
        """No organism/locus_tags/experiment_ids → ValueError → ToolError."""
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            side_effect=ValueError("at least one of organism, locus_tags, experiment_ids"),
        ):
            with pytest.raises(ToolError, match="at least one"):
                await tool_fns["differential_expression_by_gene"](mock_ctx)

    @pytest.mark.asyncio
    async def test_multi_organism_raises_tool_error(self, tool_fns, mock_ctx):
        """Multi-organism locus_tags → ValueError → ToolError."""
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            side_effect=ValueError("organism.*matches multiple"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["differential_expression_by_gene"](
                    mock_ctx, locus_tags=["PMM0001", "SYNW0305"],
                )

    @pytest.mark.asyncio
    async def test_invalid_direction_raises_tool_error(self, tool_fns, mock_ctx):
        """Invalid direction → ValueError → ToolError."""
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            side_effect=ValueError("Invalid direction"),
        ):
            with pytest.raises(ToolError, match="Invalid direction"):
                await tool_fns["differential_expression_by_gene"](
                    mock_ctx, organism="MED4", direction="up",
                )

    @pytest.mark.asyncio
    async def test_generic_error_raises_tool_error(self, tool_fns, mock_ctx):
        """RuntimeError caught and converted to ToolError."""
        from fastmcp.exceptions import ToolError
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            side_effect=RuntimeError("timeout"),
        ):
            with pytest.raises(ToolError, match="Error in differential_expression"):
                await tool_fns["differential_expression_by_gene"](
                    mock_ctx, organism="MED4",
                )

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value={**self._SAMPLE_API_RETURN, "offset": 5},
        ) as mock_api:
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4", offset=5,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# search_homolog_groups
# ---------------------------------------------------------------------------
class TestSearchHomologGroupsWrapper:
    """Tests for search_homolog_groups MCP wrapper."""

    _SAMPLE_API_RETURN = {
        "total_entries": 21122,
        "total_matching": 884,
        "by_source": [{"source": "eggnog", "count": 647}, {"source": "cyanorak", "count": 237}],
        "by_level": [{"taxonomic_level": "Bacteria", "count": 218}, {"taxonomic_level": "curated", "count": 237}],
        "score_max": 6.128,
        "score_median": 1.057,
        "returned": 2,
        "truncated": True,
        "results": [
            {"group_id": "eggnog:30SSF@2", "group_name": "30SSF@2",
             "consensus_gene_name": "psbJ", "consensus_product": "photosystem II reaction center protein PsbJ",
             "source": "eggnog", "taxonomic_level": "Bacteria",
             "specificity_rank": 3, "member_count": 13, "organism_count": 13,
             "score": 6.128},
            {"group_id": "cyanorak:CK_00000570", "group_name": "CK_00000570",
             "consensus_gene_name": "psbB", "consensus_product": "photosystem II chlorophyll-binding protein CP47",
             "source": "cyanorak", "taxonomic_level": "curated",
             "specificity_rank": 0, "member_count": 9, "organism_count": 9,
             "score": 5.5},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_homolog_groups",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["search_homolog_groups"](
                mock_ctx, search_text="photosynthesis",
            )
        assert result.total_entries == 21122
        assert result.total_matching == 884
        assert result.returned == 2
        assert result.truncated is True
        assert len(result.results) == 2
        assert len(result.by_source) == 2
        assert len(result.by_level) == 2

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        empty_return = {
            "total_entries": 21122,
            "total_matching": 0,
            "by_source": [],
            "by_level": [],
            "score_max": None,
            "score_median": None,
            "returned": 0,
            "truncated": False,
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.search_homolog_groups",
            return_value=empty_return,
        ):
            result = await tool_fns["search_homolog_groups"](
                mock_ctx, search_text="xyznonexistent",
            )
        assert result.total_matching == 0
        assert result.returned == 0
        assert result.results == []
        assert result.score_max is None

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_homolog_groups",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["search_homolog_groups"](
                mock_ctx, search_text="kinase", source="cyanorak",
                taxonomic_level="curated", max_specificity_rank=0,
                summary=True, verbose=True, limit=10,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        assert call_kwargs.args[0] == "kinase"
        assert call_kwargs.kwargs["source"] == "cyanorak"
        assert call_kwargs.kwargs["taxonomic_level"] == "curated"
        assert call_kwargs.kwargs["max_specificity_rank"] == 0
        assert call_kwargs.kwargs["summary"] is True
        assert call_kwargs.kwargs["verbose"] is True
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        truncated_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 884, "returned": 5, "truncated": True,
        }
        with patch(
            "multiomics_explorer.api.functions.search_homolog_groups",
            return_value=truncated_return,
        ):
            result = await tool_fns["search_homolog_groups"](
                mock_ctx, search_text="photosynthesis",
            )
        assert result.truncated is True
        assert result.total_matching == 884

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.search_homolog_groups",
            side_effect=ValueError("Invalid source 'bad'"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["search_homolog_groups"](
                    mock_ctx, search_text="test", source="bad",
                )

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_homolog_groups",
            return_value={**self._SAMPLE_API_RETURN, "offset": 5},
        ) as mock_api:
            result = await tool_fns["search_homolog_groups"](
                mock_ctx, search_text="photosynthesis", offset=5,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# genes_by_homolog_group
# ---------------------------------------------------------------------------
class TestGenesByHomologGroupWrapper:
    """Tests for genes_by_homolog_group MCP wrapper."""

    _SAMPLE_API_RETURN = {
        "total_matching": 9,
        "total_genes": 9,
        "total_categories": 1,
        "genes_per_group_max": 9,
        "genes_per_group_median": 9.0,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1},
                        {"organism_name": "Prochlorococcus AS9601", "count": 1}],
        "top_categories": [{"category": "Photosynthesis", "count": 9}],
        "top_groups": [{"group_id": "cyanorak:CK_00000570", "count": 9}],
        "not_found_groups": [],
        "not_matched_groups": [],
        "not_found_organisms": [],
        "not_matched_organisms": [],
        "returned": 2,
        "truncated": True,
        "results": [
            {"locus_tag": "A9601_03391", "gene_name": "psbB",
             "product": "photosystem II chlorophyll-binding protein CP47",
             "organism_name": "Prochlorococcus AS9601",
             "gene_category": "Photosynthesis",
             "group_id": "cyanorak:CK_00000570"},
            {"locus_tag": "PMM0315", "gene_name": "psbB",
             "product": "photosystem II chlorophyll-binding protein CP47",
             "organism_name": "Prochlorococcus MED4",
             "gene_category": "Photosynthesis",
             "group_id": "cyanorak:CK_00000570"},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_homolog_group",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_homolog_group"](
                mock_ctx, group_ids=["cyanorak:CK_00000570"],
            )
        assert result.total_matching == 9
        assert result.total_genes == 9
        assert result.total_categories == 1
        assert result.genes_per_group_max == 9
        assert result.genes_per_group_median == 9.0
        assert result.returned == 2
        assert result.truncated is True
        assert len(result.results) == 2
        assert len(result.by_organism) == 2
        assert len(result.top_groups) == 1
        assert result.not_found_groups == []
        assert result.not_matched_groups == []
        assert result.not_found_organisms == []
        assert result.not_matched_organisms == []

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        empty_return = {
            "total_matching": 0,
            "total_genes": 0,
            "total_categories": 0,
            "genes_per_group_max": 0,
            "genes_per_group_median": 0,
            "by_organism": [],
            "top_categories": [],
            "top_groups": [],
            "not_found_groups": ["FAKE_GROUP"],
            "not_matched_groups": [],
            "not_found_organisms": [],
            "not_matched_organisms": [],
            "returned": 0,
            "truncated": False,
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_homolog_group",
            return_value=empty_return,
        ):
            result = await tool_fns["genes_by_homolog_group"](
                mock_ctx, group_ids=["FAKE_GROUP"],
            )
        assert result.total_matching == 0
        assert result.returned == 0
        assert result.results == []
        assert result.not_found_groups == ["FAKE_GROUP"]

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_homolog_group",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["genes_by_homolog_group"](
                mock_ctx, group_ids=["cyanorak:CK_1"],
                organisms=["MED4"], summary=True, verbose=True, limit=10,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        assert call_kwargs.args[0] == ["cyanorak:CK_1"]
        assert call_kwargs.kwargs["organisms"] == ["MED4"]
        assert call_kwargs.kwargs["summary"] is True
        assert call_kwargs.kwargs["verbose"] is True
        assert call_kwargs.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        truncated_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 33, "returned": 5, "truncated": True,
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_homolog_group",
            return_value=truncated_return,
        ):
            result = await tool_fns["genes_by_homolog_group"](
                mock_ctx, group_ids=["cyanorak:CK_00000570"],
            )
        assert result.truncated is True
        assert result.total_matching == 33

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.genes_by_homolog_group",
            side_effect=ValueError("group_ids must not be empty."),
        ):
            with pytest.raises(ToolError):
                await tool_fns["genes_by_homolog_group"](
                    mock_ctx, group_ids=[],
                )

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_homolog_group",
            return_value={**self._SAMPLE_API_RETURN, "offset": 5},
        ) as mock_api:
            result = await tool_fns["genes_by_homolog_group"](
                mock_ctx, group_ids=["cyanorak:CK_00000570"], offset=5,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# differential_expression_by_ortholog
# ---------------------------------------------------------------------------
class TestDifferentialExpressionByOrthologWrapper:
    """Tests for differential_expression_by_ortholog MCP wrapper."""

    _SAMPLE_API_RETURN = {
        "total_matching": 10,
        "matching_genes": 3,
        "matching_groups": 1,
        "experiment_count": 2,
        "median_abs_log2fc": 1.5,
        "max_abs_log2fc": 3.0,
        "by_organism": [{"organism_name": "MED4", "count": 10}],
        "rows_by_status": {"significant_up": 5, "significant_down": 3,
                           "not_significant": 2},
        "rows_by_treatment_type": {"nitrogen_limitation": 10},
        "by_table_scope": {"all_detected_genes": 10},
        "top_groups": [{"group_id": "g1", "consensus_gene_name": "psbB",
                        "consensus_product": "CP47",
                        "significant_genes": 3, "total_genes": 5}],
        "top_experiments": [{"experiment_id": "EXP001",
                             "treatment_type": "nitrogen_limitation",
                             "organism_name": "MED4",
                             "significant_genes": 3}],
        "not_found_groups": [],
        "not_matched_groups": [],
        "not_found_organisms": [],
        "not_matched_organisms": [],
        "not_found_experiments": [],
        "not_matched_experiments": [],
        "returned": 1,
        "truncated": False,
        "results": [
            {"group_id": "g1", "consensus_gene_name": "psbB",
             "consensus_product": "CP47", "experiment_id": "EXP001",
             "treatment_type": "nitrogen_limitation",
             "organism_name": "MED4", "coculture_partner": None,
             "timepoint": "24h", "timepoint_hours": 24.0,
             "timepoint_order": 3, "genes_with_expression": 3,
             "total_genes": 5, "significant_up": 2,
             "significant_down": 1, "not_significant": 0},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        """API dict is converted to Pydantic response model."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_ortholog",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["differential_expression_by_ortholog"](
                mock_ctx, group_ids=["g1"],
            )
        assert result.total_matching == 10
        assert result.returned == 1
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_ortholog",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["differential_expression_by_ortholog"](
                mock_ctx, group_ids=["g1"],
                organisms=["MED4"], direction="up",
                significant_only=True, verbose=True, limit=10,
                summary=True,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs
        assert call_kwargs["group_ids"] == ["g1"]
        assert call_kwargs["organisms"] == ["MED4"]
        assert call_kwargs["direction"] == "up"
        assert call_kwargs["significant_only"] is True
        assert call_kwargs["verbose"] is True
        assert call_kwargs["limit"] == 10
        assert call_kwargs["summary"] is True

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        empty_return = {
            "total_matching": 0, "matching_genes": 0, "matching_groups": 0,
            "experiment_count": 0, "median_abs_log2fc": None,
            "max_abs_log2fc": None, "results": [], "returned": 0,
            "truncated": False,
            "by_organism": [], "rows_by_status": {},
            "rows_by_treatment_type": {}, "by_table_scope": {},
            "top_groups": [], "top_experiments": [],
            "not_found_groups": ["g1"], "not_matched_groups": [],
            "not_found_organisms": [], "not_matched_organisms": [],
            "not_found_experiments": [], "not_matched_experiments": [],
        }
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_ortholog",
            return_value=empty_return,
        ):
            result = await tool_fns["differential_expression_by_ortholog"](
                mock_ctx, group_ids=["g1"],
            )
        assert result.returned == 0
        assert result.not_found_groups == ["g1"]

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from API is converted to ToolError."""
        from fastmcp.exceptions import ToolError

        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_ortholog",
            side_effect=ValueError("group_ids must not be empty."),
        ):
            with pytest.raises(ToolError):
                await tool_fns["differential_expression_by_ortholog"](
                    mock_ctx, group_ids=[],
                )

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_ortholog",
            return_value={**self._SAMPLE_API_RETURN, "offset": 5},
        ) as mock_api:
            result = await tool_fns["differential_expression_by_ortholog"](
                mock_ctx, group_ids=["g1"], offset=5,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5


# ---------------------------------------------------------------------------
# gene_response_profile
# ---------------------------------------------------------------------------
class TestGeneResponseProfileWrapper:
    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],
            [{
                "found_genes": ["PMM0370"],
                "has_expression": ["PMM0370"],
                "has_significant": ["PMM0370"],
                "group_totals": [
                    {"group_key": "nitrogen_stress", "experiments": 4, "timepoints": 14},
                ],
            }],
            [{
                "locus_tag": "PMM0370", "gene_name": "cynA",
                "product": "cyanate transporter", "gene_category": "Inorganic ion transport",
                "group_key": "nitrogen_stress", "experiments_tested": 3,
                "timepoints_tested": 8, "timepoints_up": 8, "timepoints_down": 0,
                "rank_ups": [3, 5, 8], "rank_downs": [],
                "log2fcs_up": [5.7, 4.2, 3.1], "log2fcs_down": [],
                "experiments_up": 3, "experiments_down": 0,
            }],
        ]
        result = await tool_fns["gene_response_profile"](mock_ctx, locus_tags=["PMM0370"])
        assert hasattr(result, "results")
        assert hasattr(result, "genes_queried")
        assert hasattr(result, "returned")
        assert hasattr(result, "truncated")
        assert hasattr(result, "organism_name")

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],
            [{"found_genes": [], "has_expression": [], "has_significant": [], "group_totals": []}],
            [],
        ]
        result = await tool_fns["gene_response_profile"](mock_ctx, locus_tags=["FAKE999"])
        assert result.results == []
        assert result.returned == 0

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        _conn_from(mock_ctx).execute_query.side_effect = ValueError("bad")
        with pytest.raises(ToolError):
            await tool_fns["gene_response_profile"](mock_ctx, locus_tags=["PMM0370"])


# ---------------------------------------------------------------------------
# list_gene_clusters
# ---------------------------------------------------------------------------
class TestListGeneClustersWrapper:
    """Tests for list_gene_clusters MCP wrapper."""

    _SAMPLE_API_RETURN = {
        "total_entries": 16,
        "total_matching": 9,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 9}],
        "by_cluster_type": [{"cluster_type": "stress_response", "count": 9}],
        "by_treatment_type": [{"treatment_type": "nitrogen_stress", "count": 9}],
        "by_omics_type": [{"omics_type": "MICROARRAY", "count": 9}],
        "by_publication": [{"publication_doi": "10.1038/msb4100087", "count": 9}],
        "returned": 1,
        "offset": 0,
        "truncated": True,
        "results": [
            {"cluster_id": "cluster:msb4100087:med4:up_n_transport",
             "name": "MED4 cluster 1 (up, N transport)",
             "organism_name": "Prochlorococcus MED4",
             "cluster_type": "stress_response",
             "treatment_type": ["nitrogen_stress"],
             "member_count": 5,
             "source_paper": "Tolonen 2006"},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_gene_clusters",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_gene_clusters"](mock_ctx)
        assert result.total_entries == 16
        assert result.total_matching == 9
        assert result.returned == 1
        assert len(result.results) == 1
        assert result.results[0].cluster_id == "cluster:msb4100087:med4:up_n_transport"

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_gene_clusters",
            side_effect=ValueError("search_text must not be empty"),
        ):
            with pytest.raises(ToolError, match="search_text must not be empty"):
                await tool_fns["list_gene_clusters"](
                    mock_ctx, search_text="")

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_gene_clusters",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["list_gene_clusters"](
                mock_ctx, search_text="nitrogen",
                organism="MED4", cluster_type="stress_response",
                summary=True, verbose=True, limit=10,
            )
        mock_api.assert_called_once()
        kwargs = mock_api.call_args.kwargs
        assert kwargs["search_text"] == "nitrogen"
        assert kwargs["organism"] == "MED4"
        assert kwargs["cluster_type"] == "stress_response"
        assert kwargs["summary"] is True
