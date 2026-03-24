"""Unit tests for MCP tool wrapper logic — no Neo4j needed.

Tests the tool-level behavior (input validation, response formatting,
error messages, LIMIT injection) by mocking the Neo4j connection.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP
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
    "genes_by_function", "gene_overview", "get_gene_details",
    "gene_homologs", "run_cypher",
    "search_ontology", "genes_by_ontology", "gene_ontology_terms",
    "list_publications",
    "list_experiments",
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
                "total_matching": 1, "by_organism": [{"organism_name": "Prochlorococcus MED4", "gene_count": 1}], "returned": 1, "truncated": False,
                "results": [
                    {"locus_tag": "PMM0001", "gene_name": "dnaN",
                     "product": "DNA pol III beta",
                     "organism_strain": "Prochlorococcus MED4"},
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
        assert r.organism_strain == "Prochlorococcus MED4"

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
                "total_matching": 3, "by_organism": [{"organism_name": "Prochlorococcus MED4", "gene_count": 1}, {"organism_name": "Prochlorococcus MIT9312", "gene_count": 1}, {"organism_name": "Synechococcus WH8102", "gene_count": 1}], "returned": 3, "truncated": False,
                "results": [
                    {"locus_tag": "PMM0001", "gene_name": "dnaN",
                     "product": "p1", "organism_strain": "Prochlorococcus MED4"},
                    {"locus_tag": "PMT9312_0001", "gene_name": "dnaN",
                     "product": "p2", "organism_strain": "Prochlorococcus MIT9312"},
                    {"locus_tag": "SYNW0305", "gene_name": None,
                     "product": "p3", "organism_strain": "Synechococcus WH8102"},
                ],
            },
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="dnaN")

        assert result.total_matching == 3
        assert result.returned == 3
        assert len(result.results) == 3
        # Flat list — each entry has organism_strain as an attribute
        organisms = {r.organism_strain for r in result.results}
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
                "total_matching": 5, "by_organism": [{"organism_name": "Org1", "gene_count": 3}, {"organism_name": "Org2", "gene_count": 2}], "returned": 2, "truncated": True,
                "results": [
                    {"locus_tag": "PMM0001", "gene_name": "a",
                     "product": "p1", "organism_strain": "Org1"},
                    {"locus_tag": "PMM0002", "gene_name": "b",
                     "product": "p2", "organism_strain": "Org2"},
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



# ---------------------------------------------------------------------------
# genes_by_function
# ---------------------------------------------------------------------------
class TestGenesByFunctionWrapper:
    _SAMPLE_API_RETURN = {
        "total_entries": 100,
        "total_matching": 5,
        "by_organism": [{"organism": "Prochlorococcus MED4", "count": 3},
                        {"organism": "Synechococcus WH8102", "count": 2}],
        "by_category": [{"category": "DNA replication", "count": 3},
                        {"category": "Photosynthesis", "count": 2}],
        "score_max": 8.5,
        "score_median": 4.2,
        "returned": 2,
        "truncated": True,
        "results": [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "DNA polymerase III subunit beta",
             "organism_strain": "Prochlorococcus MED4",
             "gene_category": "DNA replication",
             "annotation_quality": 3, "score": 5.0},
            {"locus_tag": "SYNW0305", "gene_name": "ftsH1",
             "product": "ATP-dependent metalloprotease FtsH",
             "organism_strain": "Synechococcus WH8102",
             "gene_category": None,
             "annotation_quality": 2, "score": 3.5},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_pydantic_envelope(self, tool_fns, mock_ctx):
        """Response has total_entries, total_matching, by_organism, by_category, score_max, score_median, returned, truncated, results."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_function"](
                mock_ctx, search_text="DNA polymerase",
            )
        assert result.total_entries == 100
        assert result.total_matching == 5
        assert result.returned == 2
        assert result.truncated is True
        assert result.score_max == 8.5
        assert result.score_median == 4.2
        assert len(result.by_organism) == 2
        assert result.by_organism[0].organism == "Prochlorococcus MED4"
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
            "total_entries": 50,
            "total_matching": 0,
            "by_organism": [],
            "by_category": [],
            "score_max": 0.0,
            "score_median": 0.0,
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
             "organism_strain": "Prochlorococcus MED4",
             "annotation_types": ["go_bp"], "expression_edge_count": 36,
             "significant_up_count": 3, "significant_down_count": 2, "closest_ortholog_group_size": 9,
             "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"]},
            {"locus_tag": "EZ55_00275", "gene_name": None, "product": "hypothetical",
             "gene_category": "Unknown", "annotation_quality": 0,
             "organism_strain": "Alteromonas EZ55",
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


class TestGetGeneDetailsWrapper:
    def test_not_found_message(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = [{"gene": None}]
        result = tool_fns["get_gene_details"](mock_ctx, gene_id="FAKE")
        assert "not found" in result

    def test_not_found_empty_results(self, tool_fns, mock_ctx):
        _conn_from(mock_ctx).execute_query.return_value = []
        result = tool_fns["get_gene_details"](mock_ctx, gene_id="FAKE")
        assert "not found" in result

    def test_single_query_no_homologs(self, tool_fns, mock_ctx):
        """Single execute_query call, no _homologs key in result."""
        gene_data = {"locus_tag": "PMM0001", "product": "test", "organism_strain": "Prochlorococcus MED4"}
        conn = _conn_from(mock_ctx)
        conn.execute_query.return_value = [{"gene": gene_data}]
        result = json.loads(tool_fns["get_gene_details"](mock_ctx, gene_id="PMM0001"))
        assert len(result) == 1
        assert result[0]["locus_tag"] == "PMM0001"
        assert "_homologs" not in result[0]
        assert conn.execute_query.call_count == 1



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
            {"locus_tag": "PMM0001", "organism_strain": "Prochlorococcus MED4",
             "group_id": "CK_00000364", "consensus_gene_name": "dnaN",
             "consensus_product": "DNA polymerase III subunit beta",
             "taxonomic_level": "curated", "source": "cyanorak"},
            {"locus_tag": "SYNW0305", "organism_strain": "Synechococcus WH8102",
             "group_id": "CK_00000364", "consensus_gene_name": "dnaN",
             "consensus_product": "DNA polymerase III subunit beta",
             "taxonomic_level": "curated", "source": "cyanorak"},
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
        assert r.group_id == "CK_00000364"
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
            "score_max": 0.0,
            "score_median": 0.0,
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


# ---------------------------------------------------------------------------
# genes_by_ontology
# ---------------------------------------------------------------------------
class TestGenesByOntologyWrapper:
    _SAMPLE_API_RETURN = {
        "total_matching": 2,
        "by_organism": [{"organism": "Prochlorococcus MED4", "count": 1},
                       {"organism": "Alteromonas macleodii MIT1002", "count": 1}],
        "by_category": [{"category": "Replication and repair", "count": 2}],
        "by_term": [{"term_id": "go:0006260", "count": 2}],
        "returned": 2,
        "truncated": False,
        "results": [
            {"locus_tag": "PMM0120", "gene_name": "dnaN", "product": "p1",
             "organism_strain": "Prochlorococcus MED4",
             "gene_category": "Replication and repair"},
            {"locus_tag": "MIT1002_00001", "gene_name": "geneA", "product": "p2",
             "organism_strain": "Alteromonas macleodii MIT1002",
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
        assert result.by_organism[0].organism == "Prochlorococcus MED4"
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

    def test_get_gene_details_generic_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.get_gene_details",
            side_effect=RuntimeError("timeout"),
        ):
            result = tool_fns["get_gene_details"](mock_ctx, gene_id="PMM0001")
        assert "Error in get_gene_details" in result

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
                "by_organism": [{"organism_name": "Prochlorococcus MED4", "publication_count": 1}],
                "by_treatment_type": [{"treatment_type": "coculture", "publication_count": 1}],
                "by_omics_type": [{"omics_type": "RNASEQ", "publication_count": 1}],
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


class TestListExperimentsWrapper:
    _SAMPLE_SUMMARY = {
        "total_entries": 76,
        "total_matching": 76,
        "by_organism": [{"organism_strain": "Prochlorococcus MED4", "experiment_count": 30}],
        "by_treatment_type": [{"treatment_type": "coculture", "experiment_count": 16}],
        "by_omics_type": [{"omics_type": "RNASEQ", "experiment_count": 48}],
        "by_publication": [{"publication_doi": "10.1038/ismej.2016.70", "experiment_count": 5}],
        "time_course_count": 29,
        "score_max": None,
        "score_median": None,
        "returned": 0,
        "truncated": True,
        "results": [],
    }

    _SAMPLE_EXP = {
        "experiment_id": "test_exp_1",
        "publication_doi": "10.1234/test",
        "organism_strain": "Prochlorococcus MED4",
        "treatment_type": "coculture",
        "coculture_partner": "Alteromonas macleodii HOT1A3",
        "omics_type": "RNASEQ",
        "is_time_course": False,
        "gene_count": 1696,
        "significant_up_count": 245,
        "significant_down_count": 178,
    }

    _SAMPLE_DETAIL = {
        **_SAMPLE_SUMMARY,
        "returned": 1,
        "truncated": True,
        "results": [_SAMPLE_EXP],
    }

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
        assert result.by_organism[0].organism_strain == "Prochlorococcus MED4"
        assert result.by_organism[0].experiment_count == 30
        assert result.time_course_count == 29

    @pytest.mark.asyncio
    async def test_detail_mode_has_results(self, tool_fns, mock_ctx):
        """Detail mode returns breakdowns + results."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._SAMPLE_DETAIL,
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
            return_value=self._SAMPLE_DETAIL,
        ) as mock_api:
            await tool_fns["list_experiments"](mock_ctx)
        call_kwargs = mock_api.call_args[1]
        assert call_kwargs["summary"] is False

    @pytest.mark.asyncio
    async def test_both_modes_have_breakdowns(self, tool_fns, mock_ctx):
        """Breakdowns populated in both summary and detail."""
        for summary_val, api_result in [
            (True, self._SAMPLE_SUMMARY),
            (False, self._SAMPLE_DETAIL),
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

    @pytest.mark.asyncio
    async def test_detail_empty_results(self, tool_fns, mock_ctx):
        """Detail mode with no matches returns empty results."""
        empty = {**self._SAMPLE_SUMMARY,
                 "total_matching": 0, "returned": 0, "truncated": False,
                 "by_organism": [], "by_treatment_type": [], "by_omics_type": [],
                 "by_publication": [], "time_course_count": 0, "results": []}
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
            return_value=self._SAMPLE_DETAIL,
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
        assert kw["summary"] is False
        assert kw["verbose"] is True
        assert kw["limit"] == 10

    @pytest.mark.asyncio
    async def test_detail_truncation_metadata(self, tool_fns, mock_ctx):
        """returned == len(results), truncated reflects total_matching."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._SAMPLE_DETAIL,
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        assert result.returned == len(result.results)
        assert result.truncated is True  # 76 > 1

    @pytest.mark.asyncio
    async def test_detail_verbose_fields_present(self, tool_fns, mock_ctx):
        """verbose=True includes name, treatment, etc. when present in api result."""
        verbose_exp = {**self._SAMPLE_EXP,
                       "name": "Test experiment", "publication_title": "Test paper",
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
        assert r.name == "Test experiment"
        assert r.publication_title == "Test paper"
        assert r.light_condition == "continuous light"

    @pytest.mark.asyncio
    async def test_detail_verbose_fields_absent(self, tool_fns, mock_ctx):
        """verbose=False: verbose-only fields are None."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._SAMPLE_DETAIL,
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        r = result.results[0]
        assert r.name is None
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
    async def test_time_points_model(self, tool_fns, mock_ctx):
        """time_points assembled into TimePoint models."""
        tc_exp = {
            **self._SAMPLE_EXP,
            "is_time_course": True,
            "time_points": [
                {"label": "2h", "order": 1, "hours": 2.0, "total": 353, "significant_up": 0, "significant_down": 0},
                {"label": "24h", "order": 2, "hours": 24.0, "total": 353, "significant_up": 150, "significant_down": 108},
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
        assert len(r.time_points) == 2
        assert r.time_points[0].label == "2h"
        assert r.time_points[0].hours == 2.0
        assert r.time_points[1].significant_up + r.time_points[1].significant_down == 258

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
