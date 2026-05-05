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
    "list_clustering_analyses",
    "list_derived_metrics",
    "gene_clusters_by_gene",
    "gene_derived_metrics",
    "genes_by_numeric_metric",
    "genes_by_boolean_metric",
    "genes_by_categorical_metric",
    "genes_in_cluster",
    "ontology_landscape",
    "pathway_enrichment",
    "cluster_enrichment",
    "list_metabolites",
    "genes_by_metabolite",
    "metabolites_by_gene",
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

    def test_filter_type_literal_includes_dm_types(self, tool_fns):
        """Verify the filter_type Literal includes the 3 DM-awareness values added in Task 1.

        Calling tool_fns[...] invokes the raw function and bypasses FastMCP's
        Pydantic validation layer, so we cannot trigger a ToolError here.
        Instead we introspect the type hint — FastMCP uses it to build the JSON
        schema that enforces the constraint at the MCP protocol boundary.
        """
        import inspect
        import typing
        fn = tool_fns["list_filter_values"]
        hints = typing.get_type_hints(fn, include_extras=True)
        ft_hint = hints.get("filter_type")
        assert ft_hint is not None, "filter_type parameter not found in type hints"
        hint_str = str(ft_hint)
        assert "Literal" in hint_str, f"Expected Literal in filter_type hint, got: {hint_str}"
        for valid in ("gene_category", "brite_tree", "growth_phase", "metric_type", "value_kind", "compartment"):
            assert valid in hint_str, (
                f"Expected '{valid}' in filter_type Literal, got: {hint_str}"
            )


# ---------------------------------------------------------------------------
# list_organisms
# ---------------------------------------------------------------------------
class TestListOrganismsWrapper:
    _SAMPLE_ORG = {
        "organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain",
        "genus": "Prochlorococcus",
        "species": "Prochlorococcus marinus", "strain": "MED4", "clade": "HLI",
        "ncbi_taxon_id": 59919, "gene_count": 1976, "publication_count": 11,
        "experiment_count": 46,
        "treatment_types": ["coculture", "light_stress"],
        "omics_types": ["RNASEQ", "PROTEOMICS"],
    }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, mock_ctx):
        """Response has total_entries, total_matching, returned, truncated, not_found, results."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 15, "total_matching": 15,
                "returned": 1, "truncated": True,
                "not_found": [], "results": [self._SAMPLE_ORG],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        assert result.total_entries == 15
        assert result.total_matching == 15
        assert result.returned == 1
        assert result.truncated is True
        assert result.not_found == []
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_expected_columns_compact(self, tool_fns, mock_ctx):
        """Compact result has 11 fields, no taxonomy hierarchy."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 1, "total_matching": 1,
                "returned": 1, "truncated": False,
                "not_found": [], "results": [self._SAMPLE_ORG],
            },
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
            return_value={
                "total_entries": 1, "total_matching": 1,
                "returned": 1, "truncated": False,
                "not_found": [], "results": [verbose_org],
            },
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
            return_value={
                "total_entries": 0, "total_matching": 0,
                "returned": 0, "truncated": False,
                "not_found": [], "results": [],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        assert result.total_entries == 0
        assert result.total_matching == 0
        assert result.returned == 0
        assert result.truncated is False
        assert result.results == []

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        """returned == len(results), truncated == (total > returned)."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 2, "total_matching": 2,
                "returned": 2, "truncated": False,
                "not_found": [],
                "results": [self._SAMPLE_ORG, self._SAMPLE_ORG],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        assert result.returned == 2
        assert result.truncated is False  # 2 == 2

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 10, "total_matching": 10, "returned": 2,
                "truncated": True, "offset": 5, "not_found": [], "results": [],
            },
        ) as mock_api:
            await tool_fns["list_organisms"](mock_ctx, offset=5)
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5

    @pytest.mark.asyncio
    async def test_organism_names_forwarded(self, tool_fns, mock_ctx):
        """organism_names is forwarded to the api call verbatim."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 32, "total_matching": 1, "returned": 1,
                "truncated": False, "not_found": [],
                "results": [self._SAMPLE_ORG],
            },
        ) as mock_api:
            await tool_fns["list_organisms"](
                mock_ctx, organism_names=["Prochlorococcus MED4"],
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("organism_names") == ["Prochlorococcus MED4"]

    @pytest.mark.asyncio
    async def test_summary_forwarded(self, tool_fns, mock_ctx):
        """summary flag is forwarded to the api call."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 32, "total_matching": 32, "returned": 0,
                "truncated": True, "not_found": [], "results": [],
            },
        ) as mock_api:
            await tool_fns["list_organisms"](mock_ctx, summary=True)
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("summary") is True

    @pytest.mark.asyncio
    async def test_unknown_input_populates_not_found(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 32, "total_matching": 1, "returned": 1,
                "truncated": False, "not_found": ["Bogus Org"],
                "results": [self._SAMPLE_ORG],
            },
        ):
            result = await tool_fns["list_organisms"](
                mock_ctx,
                organism_names=["Prochlorococcus MED4", "Bogus Org"],
            )
        assert result.not_found == ["Bogus Org"]
        assert result.total_matching == 1
        assert result.total_entries == 32

    @pytest.mark.asyncio
    async def test_compartment_forwarded(self, tool_fns, mock_ctx):
        """compartment param is forwarded to the api call."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 5, "total_matching": 3, "returned": 3,
                "truncated": False, "not_found": [], "results": [],
                "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
            },
        ) as mock_api:
            await tool_fns["list_organisms"](mock_ctx, compartment="vesicle")
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("compartment") == "vesicle"

    @pytest.mark.asyncio
    async def test_dm_rollup_envelope_keys_present(self, tool_fns, mock_ctx):
        """Response model includes by_value_kind, by_metric_type, by_compartment."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 2, "total_matching": 2, "returned": 0,
                "truncated": True, "not_found": [], "results": [],
                "by_value_kind": [{"value_kind": "numeric", "count": 5}],
                "by_metric_type": [{"metric_type": "damping_ratio", "count": 3}],
                "by_compartment": [{"compartment": "whole_cell", "count": 2}],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx, summary=True)
        assert len(result.by_value_kind) == 1
        assert result.by_value_kind[0].value_kind == "numeric"
        assert result.by_value_kind[0].count == 5
        assert len(result.by_metric_type) == 1
        assert result.by_metric_type[0].metric_type == "damping_ratio"
        assert result.by_metric_type[0].count == 3
        assert len(result.by_compartment) == 1
        assert result.by_compartment[0].compartment == "whole_cell"
        assert result.by_compartment[0].count == 2

    @pytest.mark.asyncio
    async def test_per_row_dm_fields_present(self, tool_fns, mock_ctx):
        """Each result row includes derived_metric_count, derived_metric_value_kinds, compartments."""
        sample_org_with_dm = {
            **self._SAMPLE_ORG,
            "derived_metric_count": 7,
            "derived_metric_value_kinds": ["numeric", "boolean"],
            "compartments": ["whole_cell"],
        }
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 1, "total_matching": 1, "returned": 1,
                "truncated": False, "not_found": [], "results": [sample_org_with_dm],
                "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        org = result.results[0]
        assert org.derived_metric_count == 7
        assert org.derived_metric_value_kinds == ["numeric", "boolean"]
        assert org.compartments == ["whole_cell"]

    @pytest.mark.asyncio
    async def test_per_row_chemistry_fields_present(self, tool_fns, mock_ctx):
        """Each result row includes reaction_count and metabolite_count."""
        sample_org_with_chem = {
            **self._SAMPLE_ORG,
            "reaction_count": 943,
            "metabolite_count": 1039,
        }
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 1, "total_matching": 1, "returned": 1,
                "truncated": False, "not_found": [], "results": [sample_org_with_chem],
                "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
                "by_metabolic_capability": [],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        org = result.results[0]
        assert org.reaction_count == 943
        assert org.metabolite_count == 1039

    @pytest.mark.asyncio
    async def test_by_metabolic_capability_envelope(self, tool_fns, mock_ctx):
        """Response includes by_metabolic_capability rollup with typed entries."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 2, "total_matching": 2, "returned": 0,
                "truncated": True, "not_found": [], "results": [],
                "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
                "by_metabolic_capability": [
                    {"organism_name": "Alteromonas macleodii EZ55",
                     "reaction_count": 1348, "metabolite_count": 1428},
                    {"organism_name": "Prochlorococcus MED4",
                     "reaction_count": 943, "metabolite_count": 1039},
                ],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx, summary=True)
        assert len(result.by_metabolic_capability) == 2
        top = result.by_metabolic_capability[0]
        assert top.organism_name == "Alteromonas macleodii EZ55"
        assert top.reaction_count == 1348
        assert top.metabolite_count == 1428


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
        "by_annotation_state": [
            {"annotation_state": "informative_multi", "count": 1},
            {"annotation_state": "no_evidence", "count": 1},
        ],
        "has_expression": 1,
        "has_significant_expression": 1,
        "has_orthologs": 2,
        "has_clusters": 1,
        "has_derived_metrics": 1,
        "returned": 2,
        "truncated": False,
        "not_found": [],
        "results": [
            {"locus_tag": "PMM1428", "gene_name": "test", "product": "test product",
             "gene_category": "DNA replication", "annotation_quality": 3,
             "organism_name": "Prochlorococcus MED4",
             "annotation_types": ["go_bp"],
             "annotation_state": "informative_multi",
             "informative_annotation_types": ["go_mf", "pfam"],
             "expression_edge_count": 36,
             "significant_up_count": 3, "significant_down_count": 2, "closest_ortholog_group_size": 9,
             "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
             "cluster_membership_count": 2, "cluster_types": ["condition_comparison"],
             "derived_metric_count": 4, "derived_metric_value_kinds": ["boolean"]},
            {"locus_tag": "EZ55_00275", "gene_name": None, "product": "hypothetical",
             "gene_category": "Unknown", "annotation_quality": 0,
             "organism_name": "Alteromonas EZ55",
             "annotation_types": [],
             "annotation_state": "no_evidence",
             "informative_annotation_types": [],
             "expression_edge_count": 0,
             "significant_up_count": 0, "significant_down_count": 0, "closest_ortholog_group_size": 1,
             "closest_ortholog_genera": [],
             "cluster_membership_count": 0, "cluster_types": [],
             "derived_metric_count": 0, "derived_metric_value_kinds": []},
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
        "top_cyanorak_roles": [],
        "top_cog_categories": [],
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

    @pytest.mark.asyncio
    async def test_ontology_summary_in_response(self, tool_fns, mock_ctx):
        api_return = {
            "total_matching": 3,
            "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 3}],
            "by_source": [{"source": "cyanorak", "count": 2}],
            "returned": 0,
            "truncated": True,
            "not_found": [],
            "no_groups": [],
            "top_cyanorak_roles": [{"id": "cyanorak.role:G.3", "name": "Energy", "count": 2}],
            "top_cog_categories": [],
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            return_value=api_return,
        ):
            result = await tool_fns["gene_homologs"](
                mock_ctx, locus_tags=["PMM0845"], summary=True,
            )
        assert len(result.top_cyanorak_roles) == 1
        assert result.top_cyanorak_roles[0].id == "cyanorak.role:G.3"


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
            {"id": "go:0006260", "name": "DNA replication", "score": 5.0, "level": 5,
             "is_informative": True},
            {"id": "go:0006261", "name": "DNA-templated DNA replication", "score": 3.2, "level": 6,
             "is_informative": True},
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
        "ontology": "go_bp",
        "organism_name": "Prochlorococcus MED4",
        "total_matching": 410,
        "total_genes": 332,
        "total_terms": 8,
        "total_categories": 22,
        "genes_per_term_min": 5,
        "genes_per_term_median": 15.0,
        "genes_per_term_max": 152,
        "terms_per_gene_min": 1,
        "terms_per_gene_median": 1.0,
        "terms_per_gene_max": 4,
        "by_category": [{"category": "Stress", "count": 101}],
        "by_level": [
            {"level": 1, "n_terms": 8, "n_genes": 332, "row_count": 410}
        ],
        "top_terms": [
            {"term_id": "go:0050896",
             "term_name": "response to stimulus", "count": 152,
             "is_informative": True}
        ],
        "n_best_effort_terms": 1,
        "not_found": [],
        "wrong_ontology": [],
        "wrong_level": [],
        "filtered_out": [],
        "returned": 2,
        "offset": 0,
        "truncated": True,
        "results": [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "DNA pol", "gene_category": "Replication",
             "term_id": "go:0050896",
             "term_name": "response to stimulus", "level": 1,
             "is_informative": True},
            {"locus_tag": "PMM0002", "gene_name": None,
             "product": None, "gene_category": None,
             "term_id": "go:0050896",
             "term_name": "response to stimulus", "level": 1,
             "is_informative": True},
        ],
    }

    @pytest.mark.asyncio
    async def test_wraps_api_result(self, tool_fns, mock_ctx):
        """Full envelope conversion to Pydantic, including by_level entries."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_ontology"](
                mock_ctx,
                ontology="go_bp",
                organism="Prochlorococcus MED4",
                level=1,
            )
        assert result.ontology == "go_bp"
        assert result.organism_name == "Prochlorococcus MED4"
        assert result.total_matching == 410
        assert result.total_genes == 332
        assert result.total_terms == 8
        assert result.total_categories == 22
        assert result.genes_per_term_median == 15.0
        assert result.terms_per_gene_max == 4
        assert len(result.by_category) == 1
        assert result.by_category[0].category == "Stress"
        assert len(result.by_level) == 1
        assert result.by_level[0].level == 1
        assert result.by_level[0].n_terms == 8
        assert result.by_level[0].n_genes == 332
        assert result.by_level[0].row_count == 410
        assert len(result.top_terms) == 1
        assert result.top_terms[0].term_id == "go:0050896"
        assert result.top_terms[0].term_name == "response to stimulus"
        assert result.n_best_effort_terms == 1
        assert result.returned == 2
        assert result.truncated is True
        assert len(result.results) == 2
        r0 = result.results[0]
        assert r0.locus_tag == "PMM0001"
        assert r0.gene_name == "dnaN"
        assert r0.term_id == "go:0050896"
        assert r0.level == 1

    @pytest.mark.asyncio
    async def test_default_limit_is_500(self, tool_fns, mock_ctx):
        """Default MCP limit is 500 (not 5) because this tool feeds enrichment."""
        empty_return = {
            "ontology": "go_bp", "organism_name": "MED4",
            "total_matching": 0, "total_genes": 0, "total_terms": 0,
            "total_categories": 0,
            "genes_per_term_min": 0, "genes_per_term_median": 0.0,
            "genes_per_term_max": 0,
            "terms_per_gene_min": 0, "terms_per_gene_median": 0.0,
            "terms_per_gene_max": 0,
            "by_category": [], "by_level": [], "top_terms": [],
            "n_best_effort_terms": 0,
            "not_found": [], "wrong_ontology": [],
            "wrong_level": [], "filtered_out": [],
            "returned": 0, "offset": 0, "truncated": False, "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value=empty_return,
        ) as mock_api:
            await tool_fns["genes_by_ontology"](
                mock_ctx, ontology="go_bp", organism="MED4", level=1,
            )
        mock_api.assert_called_once()
        assert mock_api.call_args.kwargs["limit"] == 500

    @pytest.mark.asyncio
    async def test_sparse_level_is_best_effort(self, tool_fns, mock_ctx):
        """Verbose mode: True passes through; absent (None) acceptable."""
        resp = {
            "ontology": "go_bp", "organism_name": "MED4",
            "total_matching": 2, "total_genes": 2, "total_terms": 1,
            "total_categories": 1,
            "genes_per_term_min": 2, "genes_per_term_median": 2.0,
            "genes_per_term_max": 2,
            "terms_per_gene_min": 1, "terms_per_gene_median": 1.0,
            "terms_per_gene_max": 1,
            "by_category": [], "by_level": [], "top_terms": [],
            "n_best_effort_terms": 1,
            "not_found": [], "wrong_ontology": [], "wrong_level": [],
            "filtered_out": [],
            "returned": 2, "offset": 0, "truncated": False,
            "results": [
                {
                    "locus_tag": "PMM0001", "gene_name": None, "product": None,
                    "gene_category": None, "term_id": "go:0098754",
                    "term_name": "detoxification", "level": 1,
                    "is_informative": True,
                    "level_is_best_effort": True,  # sparse — only set when True
                },
                {
                    # Absent level_is_best_effort (None) is acceptable.
                    "locus_tag": "PMM0002", "gene_name": None, "product": None,
                    "gene_category": None, "term_id": "go:0098754",
                    "term_name": "detoxification", "level": 1,
                    "is_informative": True,
                },
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value=resp,
        ):
            result = await tool_fns["genes_by_ontology"](
                mock_ctx, ontology="go_bp", organism="MED4", level=1,
                verbose=True,
            )
        assert result.results[0].level_is_best_effort is True
        assert result.results[1].level_is_best_effort is None

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All params passed through to api as kwargs."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value={**self._SAMPLE_API_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["genes_by_ontology"](
                mock_ctx,
                ontology="go_bp",
                organism="MED4",
                level=2,
                term_ids=["go:0006260"],
                min_gene_set_size=3,
                max_gene_set_size=200,
                summary=True,
                verbose=True,
                limit=10,
                offset=5,
            )
        mock_api.assert_called_once()
        kwargs = mock_api.call_args.kwargs
        assert kwargs["ontology"] == "go_bp"
        assert kwargs["organism"] == "MED4"
        assert kwargs["level"] == 2
        assert kwargs["term_ids"] == ["go:0006260"]
        assert kwargs["min_gene_set_size"] == 3
        assert kwargs["max_gene_set_size"] == 200
        assert kwargs["summary"] is True
        assert kwargs["verbose"] is True
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 5

    @pytest.mark.asyncio
    async def test_invalid_ontology_raises_toolerror(self, tool_fns, mock_ctx):
        """ValueError from API is converted to ToolError."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            side_effect=ValueError("Invalid ontology 'bad'"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["genes_by_ontology"](
                    mock_ctx, ontology="go_bp", organism="MED4", level=1,
                )

    @pytest.mark.asyncio
    async def test_warning_emitted_on_validation_buckets(self, tool_fns, mock_ctx):
        """ctx.warning is emitted when wrong_ontology or wrong_level are non-empty."""
        resp = {
            **self._SAMPLE_API_RETURN,
            "wrong_ontology": ["ec:1.1.1.1"],
            "wrong_level": ["go:0050896"],
            "results": [],
            "returned": 0,
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value=resp,
        ):
            await tool_fns["genes_by_ontology"](
                mock_ctx,
                ontology="go_bp",
                organism="MED4",
                level=1,
                term_ids=["ec:1.1.1.1", "go:0050896"],
            )
        # Both warnings should have been emitted.
        warning_calls = [str(c) for c in mock_ctx.warning.call_args_list]
        assert any("wrong ontology" in c for c in warning_calls)
        assert any("wrong level" in c for c in warning_calls)

    def test_expected_tools_registration(self):
        assert "genes_by_ontology" in EXPECTED_TOOLS


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
                     "level": 5, "ontology_type": "go_bp", "count": 1}],
        "terms_per_gene_min": 2,
        "terms_per_gene_max": 2,
        "terms_per_gene_median": 2.0,
        "returned": 2,
        "truncated": False,
        "not_found": [],
        "no_terms": [],
        "results": [
            {"locus_tag": "PMM0001", "term_id": "go:0006260",
             "term_name": "DNA replication", "level": 5,
             "is_informative": True},
            {"locus_tag": "PMM0001", "term_id": "go:0006271",
             "term_name": "DNA strand elongation", "level": 6,
             "is_informative": True},
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
                mock_ctx, locus_tags=["PMM0001"], organism="MED4",
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
                mock_ctx, locus_tags=["PMM0001"], organism="MED4",
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
        assert result.by_term[0].level == 5
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
        assert r.level == 5

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
                organism="MED4",
                ontology="go_bp",
                mode="leaf",
                level=3,
                tree=None,
                summary=True,
                verbose=True,
                limit=10,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args
        assert call_kwargs.args[0] == ["PMM0001"]
        assert call_kwargs.kwargs["organism"] == "MED4"
        assert call_kwargs.kwargs["ontology"] == "go_bp"
        assert call_kwargs.kwargs["mode"] == "leaf"
        assert call_kwargs.kwargs["level"] == 3
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
                mock_ctx, locus_tags=["FAKE0001"], organism="MED4",
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
                mock_ctx, locus_tags=["PMM0001"], organism="MED4",
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
                    mock_ctx, locus_tags=["PMM0001"], organism="MED4", ontology="go_bp",
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
                    mock_ctx, locus_tags=["PMM0001"], organism="MED4",
                )

    @pytest.mark.asyncio
    async def test_offset_passed_to_api(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value={**self._SAMPLE_API_RETURN, "offset": 5},
        ) as mock_api:
            result = await tool_fns["gene_ontology_terms"](mock_ctx, locus_tags=["PMM0001"], organism="MED4", offset=5)
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
                    mock_ctx, ontology="go_bp", organism="MED4",
                    term_ids=["go:0006260"],
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
                    mock_ctx, locus_tags=["PMM0001"], organism="MED4",
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
                "by_background_factors": [],
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
                "by_organism": [], "by_treatment_type": [], "by_background_factors": [], "by_omics_type": [],
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
            return_value={"total_entries": 0, "total_matching": 0, "by_organism": [], "by_treatment_type": [], "by_background_factors": [], "by_omics_type": [], "returned": 0, "truncated": False, "results": []},
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
                "by_organism": [], "by_treatment_type": [], "by_background_factors": [], "by_omics_type": [],
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
                "by_organism": [], "by_treatment_type": [], "by_background_factors": [], "by_omics_type": [],
                "returned": 2, "truncated": True, "offset": 5, "results": [],
            },
        ) as mock_api:
            result = await tool_fns["list_publications"](mock_ctx, offset=5)
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5

    @pytest.mark.asyncio
    async def test_publication_dois_passed_to_api(self, tool_fns, mock_ctx):
        """publication_dois flows from MCP wrapper into api.list_publications."""
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 21, "total_matching": 0,
                "by_organism": [], "by_treatment_type": [],
                "by_background_factors": [], "by_omics_type": [],
                "returned": 0, "truncated": False, "results": [],
                "not_found": [],
            },
        ) as mock_api:
            await tool_fns["list_publications"](
                mock_ctx, publication_dois=["10.1234/a", "10.1234/b"],
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("publication_dois") == ["10.1234/a", "10.1234/b"]

    @pytest.mark.asyncio
    async def test_not_found_surfaced_in_response(self, tool_fns, mock_ctx):
        """not_found from api dict appears on the Pydantic response."""
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 21, "total_matching": 0,
                "by_organism": [], "by_treatment_type": [],
                "by_background_factors": [], "by_omics_type": [],
                "returned": 0, "truncated": False, "results": [],
                "not_found": ["10.1234/zzz"],
            },
        ):
            result = await tool_fns["list_publications"](
                mock_ctx, publication_dois=["10.1234/zzz"],
            )
        assert result.not_found == ["10.1234/zzz"]

    @pytest.mark.asyncio
    async def test_not_found_default_empty(self, tool_fns, mock_ctx):
        """When api dict omits not_found, response defaults to empty list."""
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 21, "total_matching": 21,
                "by_organism": [], "by_treatment_type": [],
                "by_background_factors": [], "by_omics_type": [],
                "returned": 0, "truncated": True, "results": [],
            },
        ):
            result = await tool_fns["list_publications"](mock_ctx)
        assert result.not_found == []

    @pytest.mark.asyncio
    async def test_dm_envelope_keys_in_response(self, tool_fns, mock_ctx):
        """by_value_kind, by_metric_type, by_compartment are in the response."""
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 5, "total_matching": 5,
                "by_organism": [], "by_treatment_type": [],
                "by_background_factors": [], "by_omics_type": [],
                "by_value_kind": [{"value_kind": "numeric", "count": 3}],
                "by_metric_type": [{"metric_type": "diel_rhythmicity", "count": 2}],
                "by_compartment": [{"compartment": "whole_cell", "count": 4}],
                "returned": 0, "truncated": False, "results": [],
            },
        ):
            result = await tool_fns["list_publications"](mock_ctx)
        assert len(result.by_value_kind) == 1
        assert result.by_value_kind[0].value_kind == "numeric"
        assert result.by_value_kind[0].count == 3
        assert len(result.by_metric_type) == 1
        assert result.by_metric_type[0].metric_type == "diel_rhythmicity"
        assert len(result.by_compartment) == 1
        assert result.by_compartment[0].compartment == "whole_cell"

    @pytest.mark.asyncio
    async def test_compartment_param_forwarded(self, tool_fns, mock_ctx):
        """compartment param is forwarded to api.list_publications."""
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 5, "total_matching": 2,
                "by_organism": [], "by_treatment_type": [],
                "by_background_factors": [], "by_omics_type": [],
                "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
                "returned": 0, "truncated": False, "results": [],
            },
        ) as mock_api:
            await tool_fns["list_publications"](mock_ctx, compartment="vesicle")
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("compartment") == "vesicle"

    @pytest.mark.asyncio
    async def test_per_row_dm_fields_in_result(self, tool_fns, mock_ctx):
        """Per-row derived_metric_count, derived_metric_value_kinds, compartments present."""
        pub_with_dm = {
            **self._SAMPLE_PUB,
            "derived_metric_count": 2,
            "derived_metric_value_kinds": ["boolean"],
            "compartments": ["whole_cell"],
        }
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 1, "total_matching": 1,
                "by_organism": [], "by_treatment_type": [],
                "by_background_factors": [], "by_omics_type": [],
                "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
                "returned": 1, "truncated": False, "results": [pub_with_dm],
            },
        ):
            result = await tool_fns["list_publications"](mock_ctx)
        r = result.results[0]
        assert r.derived_metric_count == 2
        assert r.derived_metric_value_kinds == ["boolean"]
        assert r.compartments == ["whole_cell"]


class TestListExperimentsWrapper:
    _SAMPLE_SUMMARY = {
        "total_entries": 76,
        "total_matching": 76,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 30}],
        "by_treatment_type": [{"treatment_type": "coculture", "count": 16}],
        "by_background_factors": [],
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
        "authors": ["Smith J", "Jones K"],
        "organism_name": "Prochlorococcus MED4",
        "treatment_type": ["coculture"],
        "background_factors": [],
        "coculture_partner": "Alteromonas macleodii HOT1A3",
        "omics_type": "RNASEQ",
        "is_time_course": False,
        "table_scope": "all_detected_genes",
        "table_scope_detail": None,
        "gene_count": 1696,
        "distinct_gene_count": 1696,
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
    async def test_authors_propagates_to_response(self, tool_fns, mock_ctx):
        """authors field from api dict reaches the Pydantic ExperimentResult."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_detail(),
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        assert result.results[0].authors == ["Smith J", "Jones K"]

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
                 "by_organism": [], "by_treatment_type": [], "by_background_factors": [], "by_omics_type": [],
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

    @pytest.mark.asyncio
    async def test_experiment_ids_passed_to_api(self, tool_fns, mock_ctx):
        """experiment_ids flows from MCP wrapper into api.list_experiments. B2 #1."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value={**self._SAMPLE_SUMMARY, "not_found": []},
        ) as mock_api:
            await tool_fns["list_experiments"](
                mock_ctx, experiment_ids=["exp_a", "exp_b"],
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("experiment_ids") == ["exp_a", "exp_b"]

    @pytest.mark.asyncio
    async def test_not_found_surfaced_in_response(self, tool_fns, mock_ctx):
        """not_found from api dict appears on the Pydantic response."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value={**self._SAMPLE_SUMMARY, "not_found": ["exp_zzz"]},
        ):
            result = await tool_fns["list_experiments"](
                mock_ctx, experiment_ids=["exp_zzz"],
            )
        assert result.not_found == ["exp_zzz"]

    @pytest.mark.asyncio
    async def test_not_found_default_empty(self, tool_fns, mock_ctx):
        """When api dict omits not_found, response defaults to empty list."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._SAMPLE_SUMMARY,
        ):
            result = await tool_fns["list_experiments"](mock_ctx, summary=True)
        assert result.not_found == []

    @pytest.mark.asyncio
    async def test_distinct_gene_count_in_pydantic_result(self, tool_fns, mock_ctx):
        """Per-experiment distinct_gene_count is a real Pydantic field
        and flows through. B2 #2."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_detail(),
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        row = result.results[0]
        assert row.distinct_gene_count == 1696
        assert row.gene_count == 1696
        assert row.distinct_gene_count <= row.gene_count

    # --- Task 4: DM rollups + compartment filter ---

    _SAMPLE_SUMMARY_DM = {
        **{k: v for k, v in _SAMPLE_SUMMARY.items()},
        "by_value_kind": [
            {"value_kind": "numeric", "count": 15},
            {"value_kind": "boolean", "count": 14},
        ],
        "by_metric_type": [
            {"metric_type": "damping_ratio", "count": 4},
        ],
        "by_compartment": [
            {"compartment": "whole_cell", "count": 160},
            {"compartment": "vesicle", "count": 5},
        ],
        "by_cluster_type": [{"cluster_type": "condition_comparison", "count": 7}],
        "by_growth_phase": [{"growth_phase": "exponential", "count": 20}],
        "not_found": [],
        "offset": 0,
    }

    @pytest.mark.asyncio
    async def test_dm_envelope_keys_in_response(self, tool_fns, mock_ctx):
        """by_value_kind, by_metric_type, by_compartment present in response."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._SAMPLE_SUMMARY_DM,
        ):
            result = await tool_fns["list_experiments"](mock_ctx, summary=True)
        assert len(result.by_value_kind) == 2
        assert result.by_value_kind[0].value_kind == "numeric"
        assert result.by_value_kind[0].count == 15
        assert len(result.by_metric_type) == 1
        assert result.by_metric_type[0].metric_type == "damping_ratio"
        assert len(result.by_compartment) == 2
        assert result.by_compartment[0].compartment == "whole_cell"
        assert result.by_compartment[0].count == 160

    @pytest.mark.asyncio
    async def test_compartment_param_forwarded(self, tool_fns, mock_ctx):
        """compartment filter parameter is forwarded to api.list_experiments."""
        import copy
        summary_with_dm = copy.deepcopy(self._SAMPLE_SUMMARY_DM)
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=summary_with_dm,
        ) as mock_api:
            await tool_fns["list_experiments"](mock_ctx, compartment="vesicle", summary=True)
        call_kwargs = mock_api.call_args.kwargs
        assert call_kwargs.get("compartment") == "vesicle"

    @pytest.mark.asyncio
    async def test_per_row_compartment_and_dm_fields(self, tool_fns, mock_ctx):
        """Per-row compartment, derived_metric_count, derived_metric_value_kinds present."""
        import copy
        exp = copy.deepcopy(self._SAMPLE_EXP)
        exp.update({
            "compartment": "whole_cell",
            "derived_metric_count": 3,
            "derived_metric_value_kinds": ["numeric", "boolean"],
        })
        detail = {**self._SAMPLE_SUMMARY_DM, "returned": 1, "results": [exp]}
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=detail,
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        row = result.results[0]
        assert row.compartment == "whole_cell"
        assert row.derived_metric_count == 3
        assert row.derived_metric_value_kinds == ["numeric", "boolean"]

    @pytest.mark.asyncio
    async def test_verbose_dm_fields_in_pydantic(self, tool_fns, mock_ctx):
        """Verbose DM fields map to Pydantic ExperimentResult."""
        import copy
        exp = copy.deepcopy(self._SAMPLE_EXP)
        exp.update({
            "compartment": "vesicle",
            "derived_metric_count": 2,
            "derived_metric_value_kinds": ["numeric"],
            "derived_metric_gene_count": 300,
            "derived_metric_types": ["damping_ratio"],
            "reports_derived_metric_types": ["rhythmicity"],
        })
        detail = {**self._SAMPLE_SUMMARY_DM, "returned": 1, "results": [exp]}
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=detail,
        ):
            result = await tool_fns["list_experiments"](mock_ctx, verbose=True)
        row = result.results[0]
        assert row.derived_metric_gene_count == 300
        assert row.derived_metric_types == ["damping_ratio"]
        assert row.reports_derived_metric_types == ["rhythmicity"]

    @pytest.mark.asyncio
    async def test_per_tp_growth_phase_in_response_model(self, tool_fns, mock_ctx):
        """Per-timepoint growth_phase round-trips through TimePoint; experiment-level
        time_point_growth_phases field is gone from ExperimentResult."""
        import copy
        tc_exp = {
            **copy.deepcopy(self._SAMPLE_EXP),
            "is_time_course": True,
            "timepoints": [
                {"timepoint": "2h", "timepoint_order": 1, "timepoint_hours": 2.0,
                 "growth_phase": "exponential",
                 "gene_count": 353,
                 "genes_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 353}},
                {"timepoint": "24h", "timepoint_order": 2, "timepoint_hours": 24.0,
                 "growth_phase": "nutrient_limited",
                 "gene_count": 353,
                 "genes_by_status": {"significant_up": 150, "significant_down": 108, "not_significant": 95}},
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
        assert r.timepoints[0].growth_phase == "exponential"
        assert r.timepoints[1].growth_phase == "nutrient_limited"
        assert not hasattr(r, "time_point_growth_phases")


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
        "rows_by_background_factors": {},
        "by_table_scope": {"all_detected_genes": 15},
        "top_categories": [
            {"category": "Signal transduction",
             "total_genes": 2, "significant_genes": 2},
        ],
        "experiments": [
            {
                "experiment_id": "exp1",
                "experiment_name": "Test experiment",
                "treatment_type": ["nitrogen_stress"],
                "background_factors": [],
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
                "treatment_type": ["nitrogen_stress"],
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
        "top_cyanorak_roles": [],
        "top_cog_categories": [],
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

    @pytest.mark.asyncio
    async def test_ontology_filters_forwarded(self, tool_fns, mock_ctx):
        api_return = {
            **self._SAMPLE_API_RETURN,
            "top_cyanorak_roles": [{"id": "cyanorak.role:G.3", "name": "Energy", "count": 3}],
            "top_cog_categories": [],
        }
        with patch(
            "multiomics_explorer.api.functions.search_homolog_groups",
            return_value=api_return,
        ) as mock_api:
            await tool_fns["search_homolog_groups"](
                mock_ctx, search_text="photosynthesis",
                cyanorak_roles=["cyanorak.role:G.3"],
                cog_categories=["cog.category:J"],
            )
        call_kwargs = mock_api.call_args.kwargs
        assert call_kwargs["cyanorak_roles"] == ["cyanorak.role:G.3"]
        assert call_kwargs["cog_categories"] == ["cog.category:J"]

    @pytest.mark.asyncio
    async def test_ontology_summary_in_response(self, tool_fns, mock_ctx):
        api_return = {
            **self._SAMPLE_API_RETURN,
            "top_cyanorak_roles": [{"id": "cyanorak.role:G.3", "name": "Energy", "count": 3}],
            "top_cog_categories": [{"id": "cog.category:C", "name": "Energy prod", "count": 2}],
        }
        with patch(
            "multiomics_explorer.api.functions.search_homolog_groups",
            return_value=api_return,
        ):
            result = await tool_fns["search_homolog_groups"](
                mock_ctx, search_text="photosynthesis",
            )
        assert len(result.top_cyanorak_roles) == 1
        assert result.top_cyanorak_roles[0].id == "cyanorak.role:G.3"
        assert len(result.top_cog_categories) == 1


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
        "rows_by_background_factors": {},
        "by_table_scope": {"all_detected_genes": 10},
        "top_groups": [{"group_id": "g1", "consensus_gene_name": "psbB",
                        "consensus_product": "CP47",
                        "significant_genes": 3, "total_genes": 5}],
        "top_experiments": [{"experiment_id": "EXP001",
                             "treatment_type": ["nitrogen_limitation"],
                             "background_factors": [],
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
             "treatment_type": ["nitrogen_limitation"],
             "background_factors": [],
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
            "rows_by_treatment_type": {}, "rows_by_background_factors": {},
            "by_table_scope": {},
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
# list_clustering_analyses
# ---------------------------------------------------------------------------
class TestListClusteringAnalysesWrapper:
    """Tests for list_clustering_analyses MCP wrapper."""

    _SAMPLE_API_RETURN = {
        "total_entries": 4,
        "total_matching": 2,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 2}],
        "by_cluster_type": [{"cluster_type": "stress_response", "count": 2}],
        "by_treatment_type": [{"treatment_type": "nitrogen_stress", "count": 2}],
        "by_background_factors": [],
        "by_omics_type": [{"omics_type": "MICROARRAY", "count": 2}],
        "score_max": None,
        "score_median": None,
        "returned": 1,
        "offset": 0,
        "truncated": True,
        "results": [
            {"analysis_id": "ca:msb4100087:med4:nitrogen",
             "name": "MED4 nitrogen stress response clustering",
             "organism_name": "Prochlorococcus MED4",
             "cluster_method": "K-means",
             "cluster_type": "stress_response",
             "cluster_count": 9,
             "total_gene_count": 45,
             "treatment_type": ["nitrogen_stress"],
             "background_factors": [],
             "omics_type": "MICROARRAY",
             "experiment_ids": ["exp:msb4100087:1"],
             "clusters": [
                 {"cluster_id": "cluster:msb4100087:med4:up_n_transport",
                  "name": "MED4 cluster 1 (up, N transport)",
                  "member_count": 5},
             ]},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_clustering_analyses",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_clustering_analyses"](mock_ctx)
        assert result.total_entries == 4
        assert result.total_matching == 2
        assert result.returned == 1
        assert len(result.results) == 1
        r = result.results[0]
        assert r.analysis_id == "ca:msb4100087:med4:nitrogen"
        assert r.cluster_count == 9
        assert len(r.clusters) == 1
        assert r.clusters[0].cluster_id == "cluster:msb4100087:med4:up_n_transport"
        assert r.clusters[0].member_count == 5

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_clustering_analyses",
            side_effect=ValueError("search_text must not be empty"),
        ):
            with pytest.raises(ToolError, match="search_text must not be empty"):
                await tool_fns["list_clustering_analyses"](
                    mock_ctx, search_text="")

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_clustering_analyses",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["list_clustering_analyses"](
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


# ---------------------------------------------------------------------------
# gene_clusters_by_gene
# ---------------------------------------------------------------------------
class TestGeneClustersByGeneWrapper:
    """Tests for gene_clusters_by_gene MCP wrapper."""

    _SAMPLE_API_RETURN = {
        "total_matching": 2, "total_clusters": 2,
        "genes_with_clusters": 2, "genes_without_clusters": 0,
        "not_found": [], "not_matched": [],
        "by_cluster_type": [{"cluster_type": "stress_response", "count": 2}],
        "by_treatment_type": [{"treatment_type": "nitrogen_stress", "count": 2}],
        "by_background_factors": [],
        "by_analysis": [{"analysis_id": "ca:msb4100087:med4:nitrogen", "count": 2}],
        "returned": 1, "offset": 0, "truncated": True,
        "results": [
            {"locus_tag": "PMM0370", "gene_name": "cynA",
             "cluster_id": "cluster:msb4100087:med4:up_n_transport",
             "cluster_name": "MED4 cluster 1 (up, N transport)",
             "cluster_type": "stress_response",
             "membership_score": None,
             "analysis_id": "ca:msb4100087:med4:nitrogen",
             "analysis_name": "MED4 nitrogen stress response clustering",
             "treatment_type": ["nitrogen_stress"],
             "background_factors": []},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_clusters_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["gene_clusters_by_gene"](
                mock_ctx, locus_tags=["PMM0370"])
        assert result.total_matching == 2
        assert result.genes_with_clusters == 2
        assert len(result.results) == 1
        r = result.results[0]
        assert r.analysis_id == "ca:msb4100087:med4:nitrogen"
        assert r.treatment_type == ["nitrogen_stress"]
        assert r.background_factors == []

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_clusters_by_gene",
            side_effect=ValueError("locus_tags must not be empty"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["gene_clusters_by_gene"](
                    mock_ctx, locus_tags=[])


class TestGenesInClusterWrapper:
    """Tests for genes_in_cluster MCP wrapper."""

    _SAMPLE_API_RETURN = {
        "total_matching": 5,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 5}],
        "by_cluster": [{"cluster_id": "cluster:msb4100087:med4:up_n_transport",
                         "cluster_name": "MED4 cluster 1", "count": 5}],
        "top_categories": [{"category": "N-metabolism", "count": 3}],
        "genes_per_cluster_max": 5,
        "genes_per_cluster_median": 5.0,
        "not_found_clusters": [],
        "not_matched_clusters": [],
        "not_matched_organism": None,
        "returned": 1, "offset": 0, "truncated": True,
        "results": [
            {"locus_tag": "PMM0370", "gene_name": "cynA",
             "product": "cyanate ABC transporter",
             "gene_category": "N-metabolism",
             "organism_name": "Prochlorococcus MED4",
             "cluster_id": "cluster:msb4100087:med4:up_n_transport",
             "cluster_name": "MED4 cluster 1 (up, N transport)",
             "membership_score": None},
        ],
    }

    _SAMPLE_ANALYSIS_API_RETURN = {
        "total_matching": 5,
        "analysis_name": "MED4 nitrogen stress response clustering",
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 5}],
        "by_cluster": [{"cluster_id": "cluster:msb4100087:med4:up_n_transport",
                         "cluster_name": "MED4 cluster 1", "count": 5}],
        "top_categories": [{"category": "N-metabolism", "count": 3}],
        "genes_per_cluster_max": 5,
        "genes_per_cluster_median": 5.0,
        "not_found_clusters": [],
        "not_matched_clusters": [],
        "not_matched_organism": None,
        "returned": 1, "offset": 0, "truncated": True,
        "results": [
            {"locus_tag": "PMM0370", "gene_name": "cynA",
             "product": "cyanate ABC transporter",
             "gene_category": "N-metabolism",
             "organism_name": "Prochlorococcus MED4",
             "cluster_id": "cluster:msb4100087:med4:up_n_transport",
             "cluster_name": "MED4 cluster 1 (up, N transport)",
             "membership_score": None},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_in_cluster",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_in_cluster"](
                mock_ctx,
                cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
        assert result.total_matching == 5
        assert result.genes_per_cluster_max == 5
        assert len(result.results) == 1
        assert result.analysis_name is None

    @pytest.mark.asyncio
    async def test_analysis_id_returns_analysis_name(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_in_cluster",
            return_value=self._SAMPLE_ANALYSIS_API_RETURN,
        ):
            result = await tool_fns["genes_in_cluster"](
                mock_ctx,
                analysis_id="ca:msb4100087:med4:nitrogen")
        assert result.analysis_name == "MED4 nitrogen stress response clustering"
        assert result.total_matching == 5

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_in_cluster",
            side_effect=ValueError("Must provide cluster_ids or analysis_id."),
        ):
            with pytest.raises(ToolError):
                await tool_fns["genes_in_cluster"](mock_ctx)


# ---------------------------------------------------------------------------
# ontology_landscape
# ---------------------------------------------------------------------------

class TestOntologyLandscapeWrapper:
    _SAMPLE_API_RETURN = {
        "organism_name": "Prochlorococcus MED4",
        "organism_gene_count": 1976,
        "n_ontologies": 1,
        "by_ontology": {
            "cyanorak_role": {
                "best_level": 1, "best_genome_coverage": 0.75,
                "best_relevance_rank": 1, "n_levels": 3,
            },
        },
        "not_found": [],
        "not_matched": [],
        "results": [{
            "ontology_type": "cyanorak_role", "level": 1,
            "relevance_rank": 1,
            "n_terms_with_genes": 110, "n_genes_at_level": 1491,
            "genome_coverage": 0.755,
            "min_genes_per_term": 5, "q1_genes_per_term": 9.0,
            "median_genes_per_term": 14.0, "q3_genes_per_term": 23.0,
            "max_genes_per_term": 340,
            "n_levels_in_ontology": 3,
            "best_effort_share": None,
        }],
        "returned": 1, "total_matching": 3, "truncated": True, "offset": 0,
    }

    @pytest.mark.asyncio
    async def test_returns_pydantic_response(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.ontology_landscape",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["ontology_landscape"](
                mock_ctx, organism="MED4",
            )
        assert type(result).__name__ == "OntologyLandscapeResponse"

    @pytest.mark.asyncio
    async def test_has_expected_fields(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.ontology_landscape",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["ontology_landscape"](
                mock_ctx, organism="MED4",
            )
        assert result.total_matching == 3
        assert result.returned == 1
        assert result.truncated is True
        assert result.organism_gene_count == 1976
        assert len(result.results) == 1
        assert result.results[0].ontology_type == "cyanorak_role"
        assert result.results[0].relevance_rank == 1
        assert "cyanorak_role" in result.by_ontology
        assert result.by_ontology["cyanorak_role"].best_relevance_rank == 1

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.ontology_landscape",
            side_effect=ValueError("no organism matching 'BOGUS'"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["ontology_landscape"](mock_ctx, organism="BOGUS")

    @pytest.mark.asyncio
    async def test_default_limit_is_none(self, mock_ctx, tool_fns):
        """MCP default limit should be None (Python API parity); B2 #3."""
        with patch(
            "multiomics_explorer.api.functions.ontology_landscape",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["ontology_landscape"](mock_ctx, organism="MED4")
            # Default limit should be None — assert it was passed through as None.
            kwargs = mock_api.call_args.kwargs
            assert kwargs["limit"] is None, (
                f"Expected default limit=None, got {kwargs['limit']}"
            )


class TestPathwayEnrichmentWrapper:
    def test_response_model_imports(self):
        from multiomics_explorer.mcp_server.tools import (
            PathwayEnrichmentResult,
            PathwayEnrichmentResponse,
        )
        assert PathwayEnrichmentResult is not None
        assert PathwayEnrichmentResponse is not None

    def test_every_result_field_has_description(self):
        from multiomics_explorer.mcp_server.tools import PathwayEnrichmentResult
        for name, field in PathwayEnrichmentResult.model_fields.items():
            assert field.description, (
                f"PathwayEnrichmentResult.{name} missing Field(description=...)"
            )

    def test_every_envelope_field_has_description(self):
        from multiomics_explorer.mcp_server.tools import PathwayEnrichmentResponse
        for name, field in PathwayEnrichmentResponse.model_fields.items():
            assert field.description, (
                f"PathwayEnrichmentResponse.{name} missing Field(description=...)"
            )

    def test_clusterprofiler_names_mention_equivalent(self):
        """clusterProfiler-named fields must document the mapping."""
        from multiomics_explorer.mcp_server.tools import PathwayEnrichmentResult
        expected_mentions = {
            "gene_ratio": "GeneRatio",
            "bg_ratio": "BgRatio",
            "rich_factor": "RichFactor",
            "fold_enrichment": "FoldEnrichment",
            "count": "Count",
        }
        for field_name, cp_name in expected_mentions.items():
            field = PathwayEnrichmentResult.model_fields[field_name]
            assert cp_name in field.description, (
                f"{field_name} description should mention clusterProfiler name {cp_name}"
            )

    # Default limit=100 is asserted in the Task 16 integration test, not here —
    # introspecting FastMCP's tool registry for signature defaults is brittle, and
    # the default is verified by end-to-end calling behavior in integration.


class TestClusterEnrichmentWrapper:
    def test_response_model_imports(self):
        from multiomics_explorer.mcp_server.tools import (
            ClusterEnrichmentResult,
            ClusterEnrichmentResponse,
        )
        assert ClusterEnrichmentResult is not None
        assert ClusterEnrichmentResponse is not None

    def test_every_result_field_has_description(self):
        from multiomics_explorer.mcp_server.tools import ClusterEnrichmentResult
        for name, field in ClusterEnrichmentResult.model_fields.items():
            assert field.description, (
                f"ClusterEnrichmentResult.{name} missing Field(description=...)"
            )

    def test_every_envelope_field_has_description(self):
        from multiomics_explorer.mcp_server.tools import ClusterEnrichmentResponse
        for name, field in ClusterEnrichmentResponse.model_fields.items():
            assert field.description, (
                f"ClusterEnrichmentResponse.{name} missing Field(description=...)"
            )

    def test_clusterprofiler_names_mention_equivalent(self):
        from multiomics_explorer.mcp_server.tools import ClusterEnrichmentResult
        expected_mentions = {
            "gene_ratio": "GeneRatio",
            "bg_ratio": "BgRatio",
            "rich_factor": "RichFactor",
            "fold_enrichment": "FoldEnrichment",
            "count": "Count",
        }
        for field_name, cp_name in expected_mentions.items():
            field = ClusterEnrichmentResult.model_fields[field_name]
            assert cp_name in field.description, (
                f"{field_name} description should mention clusterProfiler name {cp_name}"
            )


class TestListDerivedMetricsWrapper:
    """Tests for list_derived_metrics MCP wrapper."""

    _SAMPLE_API_RETURN = {
        "total_entries": 13,
        "total_matching": 2,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 2}],
        "by_value_kind": [{"value_kind": "numeric", "count": 2}],
        "by_metric_type": [{"metric_type": "diel_amplitude_protein_log2", "count": 2}],
        "by_compartment": [{"compartment": "whole_cell", "count": 2}],
        "by_omics_type": [{"omics_type": "PAIRED_RNASEQ_PROTEOME", "count": 2}],
        "by_treatment_type": [{"treatment_type": "diel", "count": 2}],
        "by_background_factors": [],
        "by_growth_phase": [],
        "score_max": None,
        "score_median": None,
        "returned": 1,
        "offset": 0,
        "truncated": True,
        "results": [
            {
                "derived_metric_id": "dm:10.1038/s41396-020-0597-6:med4:diel_amplitude_protein_log2",
                "name": "Protein diel amplitude (log2)",
                "metric_type": "diel_amplitude_protein_log2",
                "value_kind": "numeric",
                "rankable": True,
                "has_p_value": False,
                "unit": "log2",
                "allowed_categories": None,
                "field_description": "Log2 amplitude of the diel protein oscillation.",
                "organism_name": "Prochlorococcus MED4",
                "experiment_id": "exp:10.1038/s41396-020-0597-6:diel_med4",
                "publication_doi": "10.1038/s41396-020-0597-6",
                "compartment": "whole_cell",
                "omics_type": "PAIRED_RNASEQ_PROTEOME",
                "treatment_type": ["diel"],
                "background_factors": [],
                "total_gene_count": 1200,
                "growth_phases": [],
            },
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_derived_metrics",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_derived_metrics"](mock_ctx)
        assert result.total_entries == 13
        assert result.total_matching == 2
        assert result.returned == 1
        assert len(result.results) == 1
        r = result.results[0]
        assert r.derived_metric_id == (
            "dm:10.1038/s41396-020-0597-6:med4:diel_amplitude_protein_log2"
        )
        assert r.value_kind == "numeric"
        assert r.rankable is True
        assert r.has_p_value is False

    @pytest.mark.asyncio
    async def test_summary_mode(self, tool_fns, mock_ctx):
        summary_return = {**self._SAMPLE_API_RETURN, "results": [], "truncated": True}
        with patch(
            "multiomics_explorer.api.functions.list_derived_metrics",
            return_value=summary_return,
        ):
            result = await tool_fns["list_derived_metrics"](mock_ctx, summary=True)
        assert result.results == []
        assert result.truncated is True
        assert result.total_matching > 0

    @pytest.mark.asyncio
    async def test_bool_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_derived_metrics",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["list_derived_metrics"](
                mock_ctx, rankable=True, has_p_value=False,
            )
        mock_api.assert_called_once()
        kwargs = mock_api.call_args.kwargs
        assert kwargs["rankable"] is True
        assert kwargs["has_p_value"] is False

    def test_value_kind_literal_enforced(self, tool_fns):
        """Verify the Literal['numeric','boolean','categorical'] annotation is present.

        Calling tool_fns[...] invokes the raw function and bypasses FastMCP's
        Pydantic validation layer, so we cannot trigger a ToolError here.
        Instead we introspect the type hint — FastMCP uses it to build the JSON
        schema that enforces the constraint at the MCP protocol boundary.
        """
        import inspect
        import typing
        fn = tool_fns["list_derived_metrics"]
        hints = typing.get_type_hints(fn, include_extras=True)
        vk_hint = hints.get("value_kind")
        assert vk_hint is not None, "value_kind parameter not found in type hints"
        hint_str = str(vk_hint)
        assert "Literal" in hint_str, f"Expected Literal in value_kind hint, got: {hint_str}"
        for valid in ("numeric", "boolean", "categorical"):
            assert valid in hint_str, (
                f"Expected '{valid}' in value_kind Literal, got: {hint_str}"
            )

    @pytest.mark.asyncio
    async def test_value_error_becomes_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_derived_metrics",
            side_effect=ValueError("search_text must not be empty."),
        ):
            with pytest.raises(ToolError, match="search_text must not be empty"):
                await tool_fns["list_derived_metrics"](mock_ctx, search_text="")
        mock_ctx.warning.assert_awaited()

    @pytest.mark.asyncio
    async def test_generic_exception_becomes_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_derived_metrics",
            side_effect=RuntimeError("unexpected db failure"),
        ):
            with pytest.raises(ToolError, match="Error in list_derived_metrics"):
                await tool_fns["list_derived_metrics"](mock_ctx)
        mock_ctx.error.assert_awaited()


class TestGeneDerivedMetricsWrapper:
    """Unit tests for gene_derived_metrics MCP wrapper."""

    @pytest.fixture
    def envelope_data(self):
        return {
            "total_matching": 9, "total_derived_metrics": 9,
            "genes_with_metrics": 1, "genes_without_metrics": 0,
            "not_found": [], "not_matched": [],
            "by_value_kind": [{"value_kind": "numeric", "count": 7}],
            "by_metric_type": [{"metric_type": "damping_ratio", "count": 1}],
            "by_metric": [{"derived_metric_id": "dm:foo", "name": "Foo",
                           "metric_type": "damping_ratio",
                           "value_kind": "numeric", "count": 1}],
            "by_compartment": [{"compartment": "whole_cell", "count": 7}],
            "by_treatment_type": [{"treatment_type": "diel", "count": 6}],
            "by_background_factors": [{"background_factor": "axenic", "count": 9}],
            "by_publication": [{"publication_doi": "10.X/Y", "count": 9}],
            "returned": 1, "offset": 0, "truncated": True,
            "results": [{
                "locus_tag": "PMM1714",
                "gene_name": "dnaN",
                "derived_metric_id": "dm:foo",
                "value_kind": "numeric",
                "name": "Foo",
                "value": 1.3,
                "rankable": True,
                "has_p_value": False,
                "rank_by_metric": 286,
                "metric_percentile": 8.36,
                "metric_bucket": "low",
                # adjusted_p_value, significant: missing in dict; Pydantic fills None
            }],
        }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, envelope_data):
        from unittest.mock import patch, AsyncMock
        with patch("multiomics_explorer.mcp_server.tools.api.gene_derived_metrics",
                   return_value=envelope_data):
            ctx = AsyncMock()
            response = await tool_fns["gene_derived_metrics"](
                ctx, locus_tags=["PMM1714"])
        assert response.total_matching == 9
        assert response.returned == 1
        assert len(response.by_metric) == 1

    @pytest.mark.asyncio
    async def test_polymorphic_value_field(self, tool_fns):
        """Pydantic value: float | str accepts both."""
        from unittest.mock import patch, AsyncMock
        for val in [1.3, "true", "Cytoplasmic Membrane"]:
            envelope = {
                "total_matching": 1, "total_derived_metrics": 1,
                "genes_with_metrics": 1, "genes_without_metrics": 0,
                "not_found": [], "not_matched": [],
                "by_value_kind": [], "by_metric_type": [], "by_metric": [],
                "by_compartment": [], "by_treatment_type": [],
                "by_background_factors": [], "by_publication": [],
                "returned": 1, "offset": 0, "truncated": False,
                "results": [{
                    "locus_tag": "X", "gene_name": None,
                    "derived_metric_id": "dm:1",
                    "value_kind": "numeric" if isinstance(val, float) else "boolean",
                    "name": "n", "value": val,
                    "rankable": False, "has_p_value": False,
                }],
            }
            with patch("multiomics_explorer.mcp_server.tools.api.gene_derived_metrics",
                       return_value=envelope):
                ctx = AsyncMock()
                response = await tool_fns["gene_derived_metrics"](
                    ctx, locus_tags=["X"])
            assert response.results[0].value == val

    @pytest.mark.asyncio
    async def test_sparse_extras_default_none(self, tool_fns, envelope_data):
        """Result accepts row dicts with adjusted_p_value/significant absent."""
        from unittest.mock import patch, AsyncMock
        with patch("multiomics_explorer.mcp_server.tools.api.gene_derived_metrics",
                   return_value=envelope_data):
            ctx = AsyncMock()
            response = await tool_fns["gene_derived_metrics"](
                ctx, locus_tags=["X"])
        row = response.results[0]
        assert row.adjusted_p_value is None
        assert row.significant is None
        assert row.p_value is None  # verbose-only, also default None

    @pytest.mark.asyncio
    async def test_summary_empty_results(self, tool_fns, envelope_data):
        from unittest.mock import patch, AsyncMock
        envelope_data["results"] = []
        envelope_data["returned"] = 0
        envelope_data["truncated"] = True
        with patch("multiomics_explorer.mcp_server.tools.api.gene_derived_metrics",
                   return_value=envelope_data):
            ctx = AsyncMock()
            response = await tool_fns["gene_derived_metrics"](
                ctx, locus_tags=["X"], summary=True)
        assert response.results == []
        assert response.truncated is True

    @pytest.mark.asyncio
    async def test_value_error_to_tool_error(self, tool_fns):
        from unittest.mock import patch, AsyncMock
        from fastmcp.exceptions import ToolError
        with patch("multiomics_explorer.mcp_server.tools.api.gene_derived_metrics",
                   side_effect=ValueError("locus_tags must not be empty.")):
            ctx = AsyncMock()
            with pytest.raises(ToolError, match="locus_tags must not be empty"):
                await tool_fns["gene_derived_metrics"](ctx, locus_tags=[])


class TestGenesByNumericMetricWrapper:
    """Unit tests for genes_by_numeric_metric MCP wrapper."""

    @pytest.fixture
    def envelope_data(self):
        return {
            "total_matching": 32,
            "total_derived_metrics": 1,
            "total_genes": 32,
            "by_organism": [
                {"organism_name": "Prochlorococcus MED4", "count": 32},
            ],
            "by_compartment": [{"compartment": "whole_cell", "count": 32}],
            "by_publication": [{"publication_doi": "10.X/Y", "count": 32}],
            "by_experiment": [{"experiment_id": "exp:foo", "count": 32}],
            "by_metric": [{
                "derived_metric_id": "dm:damping_ratio",
                "name": "Damping ratio",
                "metric_type": "damping_ratio",
                "value_kind": "numeric",
                "count": 32,
                "value_min": 12.2, "value_q1": 13.5,
                "value_median": 15.9, "value_q3": 18.0, "value_max": 25.3,
                "dm_value_min": 0.0, "dm_value_q1": 3.0,
                "dm_value_median": 6.0, "dm_value_q3": 10.0,
                "dm_value_max": 28.0,
                "rank_min": 1, "rank_max": 32,
            }],
            "top_categories": [
                {"gene_category": "Translation", "count": 6},
                {"gene_category": "Photosynthesis", "count": 5},
            ],
            "genes_per_metric_max": 32,
            "genes_per_metric_median": 32.0,
            "not_found_ids": [],
            "not_matched_ids": [],
            "not_found_metric_types": [],
            "not_matched_metric_types": [],
            "not_matched_organism": None,
            "excluded_derived_metrics": [],
            "warnings": [],
            "returned": 1,
            "offset": 0,
            "truncated": True,
            "results": [{
                "locus_tag": "PMM1545",
                "gene_name": "rpsH",
                "product": "30S ribosomal protein S8",
                "gene_category": "Translation",
                "organism_name": "Prochlorococcus MED4",
                "derived_metric_id": "dm:damping_ratio",
                "name": "Damping ratio",
                "value_kind": "numeric",
                "rankable": True,
                "has_p_value": False,
                "value": 25.3,
                "rank_by_metric": 1,
                "metric_percentile": 100.0,
                "metric_bucket": "top_decile",
            }],
        }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, envelope_data):
        with patch(
            "multiomics_explorer.mcp_server.tools.api.genes_by_numeric_metric",
            return_value=envelope_data,
        ):
            ctx = AsyncMock()
            response = await tool_fns["genes_by_numeric_metric"](
                ctx, metric_types=["damping_ratio"], bucket=["top_decile"])
        assert response.total_matching == 32
        assert response.total_derived_metrics == 1
        assert response.total_genes == 32
        assert response.returned == 1
        assert response.truncated is True
        assert len(response.by_metric) == 1
        assert response.by_metric[0].value_kind == "numeric"
        assert response.by_metric[0].dm_value_max == 28.0
        assert response.by_metric[0].rank_min == 1
        assert response.results[0].locus_tag == "PMM1545"
        assert response.results[0].value == 25.3
        assert response.results[0].metric_bucket == "top_decile"

    @pytest.mark.asyncio
    async def test_excluded_dm_envelope_field(self, tool_fns, envelope_data):
        """Pydantic accepts list[ExcludedDerivedMetric] including empty list."""
        # Empty list (default)
        with patch(
            "multiomics_explorer.mcp_server.tools.api.genes_by_numeric_metric",
            return_value=envelope_data,
        ):
            ctx = AsyncMock()
            response = await tool_fns["genes_by_numeric_metric"](
                ctx, metric_types=["damping_ratio"])
        assert response.excluded_derived_metrics == []

        # Single-entry list
        envelope_data["excluded_derived_metrics"] = [{
            "derived_metric_id": "dm:peak_time_protein_h",
            "metric_type": "peak_time_protein_h",
            "rankable": False,
            "has_p_value": False,
            "reason": "non-rankable; bucket filter does not apply",
        }]
        envelope_data["warnings"] = [
            "1 non-rankable DM excluded by `bucket` filter "
            "(peak_time_protein_h)",
        ]
        with patch(
            "multiomics_explorer.mcp_server.tools.api.genes_by_numeric_metric",
            return_value=envelope_data,
        ):
            ctx = AsyncMock()
            response = await tool_fns["genes_by_numeric_metric"](
                ctx, metric_types=["damping_ratio", "peak_time_protein_h"],
                bucket=["top_decile"])
        assert len(response.excluded_derived_metrics) == 1
        excl = response.excluded_derived_metrics[0]
        assert excl.derived_metric_id == "dm:peak_time_protein_h"
        assert excl.rankable is False
        assert excl.has_p_value is False
        assert "non-rankable" in excl.reason
        assert len(response.warnings) == 1

    @pytest.mark.asyncio
    async def test_warnings_default_empty(self, tool_fns, envelope_data):
        """Empty warnings list parses cleanly."""
        envelope_data["warnings"] = []
        with patch(
            "multiomics_explorer.mcp_server.tools.api.genes_by_numeric_metric",
            return_value=envelope_data,
        ):
            ctx = AsyncMock()
            response = await tool_fns["genes_by_numeric_metric"](
                ctx, metric_types=["damping_ratio"])
        assert response.warnings == []

    @pytest.mark.asyncio
    async def test_summary_empty_results(self, tool_fns, envelope_data):
        """summary=True → results=[] + populated envelope."""
        envelope_data["results"] = []
        envelope_data["returned"] = 0
        envelope_data["truncated"] = True
        with patch(
            "multiomics_explorer.mcp_server.tools.api.genes_by_numeric_metric",
            return_value=envelope_data,
        ):
            ctx = AsyncMock()
            response = await tool_fns["genes_by_numeric_metric"](
                ctx, metric_types=["damping_ratio"], summary=True)
        assert response.results == []
        assert response.returned == 0
        assert response.truncated is True
        assert response.total_matching == 32
        assert len(response.by_metric) == 1

    @pytest.mark.asyncio
    async def test_value_error_to_tool_error(self, tool_fns):
        """When api/ raises ValueError, wrapper raises ToolError."""
        with patch(
            "multiomics_explorer.mcp_server.tools.api.genes_by_numeric_metric",
            side_effect=ValueError(
                "must provide one of derived_metric_ids or metric_types"),
        ):
            ctx = AsyncMock()
            with pytest.raises(
                ToolError,
                match="must provide one of derived_metric_ids or metric_types",
            ):
                await tool_fns["genes_by_numeric_metric"](ctx)


# ---------------------------------------------------------------------------
# genes_by_boolean_metric
# ---------------------------------------------------------------------------
class TestGenesByBooleanMetricWrapper:
    """Unit tests for genes_by_boolean_metric MCP wrapper."""

    @pytest.fixture
    def envelope_data(self):
        return {
            "total_matching": 58,
            "total_derived_metrics": 2,
            "total_genes": 58,
            "by_organism": [
                {"organism_name": "Prochlorococcus MED4", "count": 32},
                {"organism_name": "Prochlorococcus MIT9313", "count": 26},
            ],
            "by_compartment": [{"compartment": "vesicle", "count": 58}],
            "by_publication": [
                {"publication_doi": "10.1111/1462-2920.12187", "count": 58},
            ],
            "by_experiment": [
                {"experiment_id": "exp:biller2014:med4_vesicle", "count": 32},
                {"experiment_id": "exp:biller2014:mit9313_vesicle", "count": 26},
            ],
            "by_value": [{"value": "true", "count": 58}],
            "by_metric": [
                {
                    "derived_metric_id": "dm:vesicle_proteome_member:med4",
                    "name": "MED4 vesicle proteome",
                    "metric_type": "vesicle_proteome_member",
                    "value_kind": "boolean",
                    "count": 32,
                    "true_count": 32,
                    "false_count": 0,
                    "dm_total_gene_count": 32,
                    "dm_true_count": 32,
                    "dm_false_count": 0,
                },
                {
                    "derived_metric_id": "dm:vesicle_proteome_member:mit9313",
                    "name": "MIT9313 vesicle proteome",
                    "metric_type": "vesicle_proteome_member",
                    "value_kind": "boolean",
                    "count": 26,
                    "true_count": 26,
                    "false_count": 0,
                    "dm_total_gene_count": 26,
                    "dm_true_count": 26,
                    "dm_false_count": 0,
                },
            ],
            "top_categories": [
                {"gene_category": "Membrane/wall", "count": 12},
                {"gene_category": "Unknown", "count": 6},
            ],
            "genes_per_metric_max": 32,
            "genes_per_metric_median": 29.0,
            "not_found_ids": [],
            "not_matched_ids": [],
            "not_found_metric_types": [],
            "not_matched_metric_types": [],
            "not_matched_organism": None,
            "excluded_derived_metrics": [],
            "warnings": [],
            "returned": 1,
            "offset": 0,
            "truncated": True,
            "results": [{
                "locus_tag": "PMM0090",
                "gene_name": None,
                "product": "Hypothetical protein",
                "gene_category": "Unknown",
                "organism_name": "Prochlorococcus MED4",
                "derived_metric_id": "dm:vesicle_proteome_member:med4",
                "name": "MED4 vesicle proteome",
                "value_kind": "boolean",
                "rankable": False,
                "has_p_value": False,
                "value": "true",
            }],
        }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, envelope_data):
        with patch(
            "multiomics_explorer.mcp_server.tools.api.genes_by_boolean_metric",
            return_value=envelope_data,
        ) as mock_api:
            ctx = AsyncMock()
            response = await tool_fns["genes_by_boolean_metric"](
                ctx, metric_types=["vesicle_proteome_member"])
        assert mock_api.called
        assert response.total_matching == 58
        assert response.total_derived_metrics == 2
        assert response.total_genes == 58
        assert response.returned == 1
        assert response.truncated is True
        assert len(response.by_organism) == 2
        assert len(response.by_value) == 1
        assert response.by_value[0].value == "true"
        assert response.by_value[0].count == 58
        assert len(response.by_metric) == 2
        assert response.by_metric[0].value_kind == "boolean"
        assert response.by_metric[0].true_count == 32
        assert response.by_metric[0].false_count == 0
        assert response.by_metric[0].dm_true_count == 32
        assert response.by_metric[0].dm_false_count == 0
        assert response.results[0].locus_tag == "PMM0090"
        assert response.results[0].value == "true"
        assert response.results[0].value_kind == "boolean"
        assert response.results[0].rankable is False
        assert response.results[0].has_p_value is False
        # Always-empty cross-tool envelope keys
        assert response.excluded_derived_metrics == []
        assert response.warnings == []

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, envelope_data):
        """summary=True → results=[] + populated summary envelope."""
        envelope_data["results"] = []
        envelope_data["returned"] = 0
        envelope_data["truncated"] = True
        with patch(
            "multiomics_explorer.mcp_server.tools.api.genes_by_boolean_metric",
            return_value=envelope_data,
        ):
            ctx = AsyncMock()
            response = await tool_fns["genes_by_boolean_metric"](
                ctx, metric_types=["vesicle_proteome_member"], summary=True)
        assert response.results == []
        assert response.returned == 0
        assert response.truncated is True
        assert response.total_matching == 58
        assert len(response.by_metric) == 2

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, envelope_data):
        """All params are forwarded through to api.genes_by_boolean_metric."""
        with patch(
            "multiomics_explorer.mcp_server.tools.api.genes_by_boolean_metric",
            return_value=envelope_data,
        ) as mock_api:
            ctx = AsyncMock()
            await tool_fns["genes_by_boolean_metric"](
                ctx,
                metric_types=["vesicle_proteome_member"],
                organism="MED4",
                locus_tags=["PMM0090", "PMM0097"],
                experiment_ids=["exp:biller2014:med4_vesicle"],
                publication_doi=["10.1111/1462-2920.12187"],
                compartment="vesicle",
                treatment_type=["compartment"],
                background_factors=["axenic"],
                growth_phases=["exponential"],
                flag=True,
                summary=False,
                verbose=True,
                limit=10,
                offset=5,
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs["metric_types"] == ["vesicle_proteome_member"]
        assert kwargs["derived_metric_ids"] is None
        assert kwargs["organism"] == "MED4"
        assert kwargs["locus_tags"] == ["PMM0090", "PMM0097"]
        assert kwargs["experiment_ids"] == ["exp:biller2014:med4_vesicle"]
        assert kwargs["publication_doi"] == ["10.1111/1462-2920.12187"]
        assert kwargs["compartment"] == "vesicle"
        assert kwargs["treatment_type"] == ["compartment"]
        assert kwargs["background_factors"] == ["axenic"]
        assert kwargs["growth_phases"] == ["exponential"]
        assert kwargs["flag"] is True
        assert kwargs["summary"] is False
        assert kwargs["verbose"] is True
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 5

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, envelope_data):
        """Wrapper preserves api/'s truncated + offset bookkeeping."""
        envelope_data["returned"] = 5
        envelope_data["offset"] = 5
        envelope_data["truncated"] = True
        with patch(
            "multiomics_explorer.mcp_server.tools.api.genes_by_boolean_metric",
            return_value=envelope_data,
        ):
            ctx = AsyncMock()
            response = await tool_fns["genes_by_boolean_metric"](
                ctx, metric_types=["vesicle_proteome_member"],
                offset=5, limit=5)
        assert response.offset == 5
        assert response.truncated is True
        assert response.total_matching == 58

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns):
        """When api/ raises ValueError, wrapper raises ToolError."""
        with patch(
            "multiomics_explorer.mcp_server.tools.api.genes_by_boolean_metric",
            side_effect=ValueError(
                "must provide one of derived_metric_ids or metric_types"),
        ):
            ctx = AsyncMock()
            with pytest.raises(
                ToolError,
                match="must provide one of derived_metric_ids or metric_types",
            ):
                await tool_fns["genes_by_boolean_metric"](ctx)


# ---------------------------------------------------------------------------
# genes_by_categorical_metric
# ---------------------------------------------------------------------------
class TestGenesByCategoricalMetricWrapper:
    """Unit tests for genes_by_categorical_metric MCP wrapper."""

    @pytest.fixture
    def envelope_data(self):
        return {
            "total_matching": 14,
            "total_derived_metrics": 2,
            "total_genes": 14,
            "by_organism": [
                {"organism_name": "Prochlorococcus MED4", "count": 8},
                {"organism_name": "Prochlorococcus MIT9313", "count": 6},
            ],
            "by_compartment": [{"compartment": "vesicle", "count": 14}],
            "by_publication": [
                {"publication_doi": "10.1111/1462-2920.12187", "count": 14},
            ],
            "by_experiment": [
                {"experiment_id": "exp:biller2014:med4_vesicle", "count": 8},
                {"experiment_id": "exp:biller2014:mit9313_vesicle", "count": 6},
            ],
            "by_category": [
                {"category": "Outer Membrane", "count": 8},
                {"category": "Periplasmic", "count": 6},
            ],
            "by_metric": [
                {
                    "derived_metric_id": (
                        "dm:predicted_subcellular_localization:med4"),
                    "name": "MED4 PSORTb localization",
                    "metric_type": "predicted_subcellular_localization",
                    "value_kind": "categorical",
                    "count": 8,
                    "by_category": [
                        {"category": "Outer Membrane", "count": 5},
                        {"category": "Periplasmic", "count": 3},
                    ],
                    "allowed_categories": [
                        "Cytoplasmic", "Cytoplasmic Membrane", "Periplasmic",
                        "Outer Membrane", "Extracellular", "Unknown",
                    ],
                    "dm_total_gene_count": 32,
                    "dm_by_category": [
                        {"category": "Cytoplasmic", "count": 11},
                        {"category": "Cytoplasmic Membrane", "count": 6},
                        {"category": "Outer Membrane", "count": 5},
                        {"category": "Periplasmic", "count": 3},
                        {"category": "Unknown", "count": 7},
                    ],
                },
            ],
            "top_categories": [
                {"gene_category": "Membrane/wall", "count": 8},
                {"gene_category": "Unknown", "count": 4},
            ],
            "genes_per_metric_max": 8,
            "genes_per_metric_median": 7.0,
            "not_found_ids": [],
            "not_matched_ids": [],
            "not_found_metric_types": [],
            "not_matched_metric_types": [],
            "not_matched_organism": None,
            "excluded_derived_metrics": [],
            "warnings": [],
            "returned": 1,
            "offset": 0,
            "truncated": True,
            "results": [{
                "locus_tag": "PMM0097",
                "gene_name": None,
                "product": "Hypothetical protein",
                "gene_category": "Membrane/wall",
                "organism_name": "Prochlorococcus MED4",
                "derived_metric_id": (
                    "dm:predicted_subcellular_localization:med4"),
                "name": "MED4 PSORTb localization",
                "value_kind": "categorical",
                "rankable": False,
                "has_p_value": False,
                "value": "Outer Membrane",
            }],
        }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, envelope_data):
        with patch(
            "multiomics_explorer.mcp_server.tools.api"
            ".genes_by_categorical_metric",
            return_value=envelope_data,
        ) as mock_api:
            ctx = AsyncMock()
            response = await tool_fns["genes_by_categorical_metric"](
                ctx,
                metric_types=["predicted_subcellular_localization"],
                categories=["Outer Membrane", "Periplasmic"])
        assert mock_api.called
        assert response.total_matching == 14
        assert response.total_derived_metrics == 2
        assert response.total_genes == 14
        assert response.returned == 1
        assert response.truncated is True
        assert len(response.by_organism) == 2
        # Envelope-level by_category uses the kind-specific freq class
        assert len(response.by_category) == 2
        assert response.by_category[0].category == "Outer Membrane"
        assert response.by_category[0].count == 8
        # by_metric carries nested by_category + dm_by_category + allowed
        assert len(response.by_metric) == 1
        bm = response.by_metric[0]
        assert bm.value_kind == "categorical"
        assert bm.count == 8
        assert len(bm.by_category) == 2
        assert bm.by_category[0].category == "Outer Membrane"
        assert "Extracellular" in bm.allowed_categories
        assert bm.dm_total_gene_count == 32
        assert len(bm.dm_by_category) == 5
        assert bm.dm_by_category[0].category == "Cytoplasmic"
        # Result row
        assert response.results[0].locus_tag == "PMM0097"
        assert response.results[0].value == "Outer Membrane"
        assert response.results[0].value_kind == "categorical"
        assert response.results[0].rankable is False
        assert response.results[0].has_p_value is False
        # Always-empty cross-tool envelope keys
        assert response.excluded_derived_metrics == []
        assert response.warnings == []

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, envelope_data):
        """summary=True → results=[] + populated summary envelope."""
        envelope_data["results"] = []
        envelope_data["returned"] = 0
        envelope_data["truncated"] = True
        with patch(
            "multiomics_explorer.mcp_server.tools.api"
            ".genes_by_categorical_metric",
            return_value=envelope_data,
        ):
            ctx = AsyncMock()
            response = await tool_fns["genes_by_categorical_metric"](
                ctx,
                metric_types=["predicted_subcellular_localization"],
                summary=True)
        assert response.results == []
        assert response.returned == 0
        assert response.truncated is True
        assert response.total_matching == 14
        assert len(response.by_metric) == 1

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, envelope_data):
        """All params are forwarded through to api.genes_by_categorical_metric."""
        with patch(
            "multiomics_explorer.mcp_server.tools.api"
            ".genes_by_categorical_metric",
            return_value=envelope_data,
        ) as mock_api:
            ctx = AsyncMock()
            await tool_fns["genes_by_categorical_metric"](
                ctx,
                metric_types=["predicted_subcellular_localization"],
                organism="MED4",
                locus_tags=["PMM0097"],
                experiment_ids=["exp:biller2014:med4_vesicle"],
                publication_doi=["10.1111/1462-2920.12187"],
                compartment="vesicle",
                treatment_type=["compartment"],
                background_factors=["axenic"],
                growth_phases=["exponential"],
                categories=["Outer Membrane", "Periplasmic"],
                summary=False,
                verbose=True,
                limit=10,
                offset=5,
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs["metric_types"] == [
            "predicted_subcellular_localization"]
        assert kwargs["derived_metric_ids"] is None
        assert kwargs["organism"] == "MED4"
        assert kwargs["locus_tags"] == ["PMM0097"]
        assert kwargs["experiment_ids"] == ["exp:biller2014:med4_vesicle"]
        assert kwargs["publication_doi"] == ["10.1111/1462-2920.12187"]
        assert kwargs["compartment"] == "vesicle"
        assert kwargs["treatment_type"] == ["compartment"]
        assert kwargs["background_factors"] == ["axenic"]
        assert kwargs["growth_phases"] == ["exponential"]
        assert kwargs["categories"] == ["Outer Membrane", "Periplasmic"]
        assert kwargs["summary"] is False
        assert kwargs["verbose"] is True
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 5

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, envelope_data):
        """Wrapper preserves api/'s truncated + offset bookkeeping."""
        envelope_data["returned"] = 5
        envelope_data["offset"] = 5
        envelope_data["truncated"] = True
        with patch(
            "multiomics_explorer.mcp_server.tools.api"
            ".genes_by_categorical_metric",
            return_value=envelope_data,
        ):
            ctx = AsyncMock()
            response = await tool_fns["genes_by_categorical_metric"](
                ctx,
                metric_types=["predicted_subcellular_localization"],
                offset=5, limit=5)
        assert response.offset == 5
        assert response.truncated is True
        assert response.total_matching == 14

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns):
        """When api/ raises ValueError (e.g. unknown category), wrapper
        raises ToolError."""
        with patch(
            "multiomics_explorer.mcp_server.tools.api"
            ".genes_by_categorical_metric",
            side_effect=ValueError(
                "categories includes unknown values: ['Foo']; allowed "
                "values across selected DMs: ['Cytoplasmic', "
                "'Outer Membrane', 'Periplasmic']"),
        ):
            ctx = AsyncMock()
            with pytest.raises(
                ToolError,
                match="categories includes unknown values",
            ):
                await tool_fns["genes_by_categorical_metric"](
                    ctx,
                    metric_types=["predicted_subcellular_localization"],
                    categories=["Foo"])


# ---------------------------------------------------------------------------
# list_metabolites — Phase 1 (Stage 1 RED)
# ---------------------------------------------------------------------------


_LM_SAMPLE_RESULT = {
    "metabolite_id": "kegg.compound:C00031",
    "name": "D-Glucose",
    "formula": "C6H12O6",
    "elements": ["C", "H", "O"],
    "mass": 180.156,
    "gene_count": 320,
    "organism_count": 31,
    "transporter_count": 17,
    "evidence_sources": ["metabolism", "transport"],
    "chebi_id": "4167",
    "pathway_ids": ["kegg.pathway:ko00010"],
    "pathway_count": 1,
}

_LM_SAMPLE_API_RETURN = {
    "total_entries": 3025,
    "total_matching": 1,
    "top_organisms": [
        {"organism_name": "Prochlorococcus MED4", "count": 1},
    ],
    "top_pathways": [
        {
            "pathway_id": "kegg.pathway:ko01100",
            "pathway_name": "Metabolic pathways",
            "count": 1,
        },
    ],
    "by_evidence_source": [
        {"evidence_source": "metabolism", "count": 1},
    ],
    "xref_coverage": {"with_chebi": 1, "with_hmdb": 0, "with_mnxm": 1},
    "mass_stats": {
        "mass_min": 180.156, "mass_median": 180.156, "mass_max": 180.156,
    },
    "score_max": None,
    "score_median": None,
    "returned": 1,
    "offset": 0,
    "truncated": False,
    "not_found": {
        "metabolite_ids": [], "organism_names": [], "pathway_ids": [],
    },
    "results": [_LM_SAMPLE_RESULT],
}


class TestListMetabolitesWrapper:
    """MCP-wrapper tests for list_metabolites."""

    _SAMPLE_RESULT = _LM_SAMPLE_RESULT
    _SAMPLE_API_RETURN = _LM_SAMPLE_API_RETURN

    @pytest.mark.asyncio
    async def test_returns_response_type(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_metabolites"](mock_ctx)
        assert result.total_entries == 3025
        assert result.total_matching == 1
        assert result.returned == 1
        assert result.truncated is False
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_compact_fields_present(self, tool_fns, mock_ctx):
        """Compact per-row fields surface on the Pydantic model."""
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_metabolites"](mock_ctx)
        r = result.results[0]
        assert r.metabolite_id == "kegg.compound:C00031"
        assert r.name == "D-Glucose"
        assert r.formula == "C6H12O6"
        assert r.elements == ["C", "H", "O"]
        assert r.gene_count == 320
        assert r.organism_count == 31
        assert r.transporter_count == 17
        assert r.evidence_sources == ["metabolism", "transport"]
        assert r.pathway_ids == ["kegg.pathway:ko00010"]
        assert r.pathway_count == 1

    @pytest.mark.asyncio
    async def test_verbose_fields_optional(self, tool_fns, mock_ctx):
        """Verbose-only fields default to None / are present when populated."""
        verbose_row = {
            **self._SAMPLE_RESULT,
            "inchikey": "WQZGKKKJIJFFOK-GASJEMHNSA-N",
            "smiles": "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
            "mnxm_id": "MNXM1364061",
            "hmdb_id": "HMDB0000122",
            "pathway_names": ["Glycolysis / Gluconeogenesis"],
        }
        api_return = {**self._SAMPLE_API_RETURN, "results": [verbose_row]}
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=api_return,
        ):
            result = await tool_fns["list_metabolites"](mock_ctx, verbose=True)
        r = result.results[0]
        assert r.inchikey == "WQZGKKKJIJFFOK-GASJEMHNSA-N"
        assert r.smiles == "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O"
        assert r.mnxm_id == "MNXM1364061"
        assert r.hmdb_id == "HMDB0000122"
        assert r.pathway_names == ["Glycolysis / Gluconeogenesis"]

    @pytest.mark.asyncio
    async def test_not_found_structure(self, tool_fns, mock_ctx):
        """not_found is a typed dict with all 3 buckets."""
        api_return = {
            **self._SAMPLE_API_RETURN,
            "not_found": {
                "metabolite_ids": ["kegg.compound:C99999"],
                "organism_names": ["Bogus organism"],
                "pathway_ids": ["kegg.pathway:bogus"],
            },
        }
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=api_return,
        ):
            result = await tool_fns["list_metabolites"](mock_ctx)
        assert result.not_found.metabolite_ids == ["kegg.compound:C99999"]
        assert result.not_found.organism_names == ["Bogus organism"]
        assert result.not_found.pathway_ids == ["kegg.pathway:bogus"]

    @pytest.mark.asyncio
    async def test_envelope_breakdowns_present(self, tool_fns, mock_ctx):
        """top_organisms, top_pathways, by_evidence_source, xref_coverage,
        mass_stats are surfaced on the Pydantic envelope."""
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_metabolites"](mock_ctx)
        assert len(result.top_organisms) == 1
        assert result.top_organisms[0].organism_name == "Prochlorococcus MED4"
        assert result.top_organisms[0].count == 1
        assert len(result.top_pathways) == 1
        assert result.top_pathways[0].pathway_id == "kegg.pathway:ko01100"
        assert result.top_pathways[0].pathway_name == "Metabolic pathways"
        assert len(result.by_evidence_source) == 1
        assert result.by_evidence_source[0].evidence_source == "metabolism"
        assert result.xref_coverage.with_chebi == 1
        assert result.xref_coverage.with_hmdb == 0
        assert result.xref_coverage.with_mnxm == 1
        assert result.mass_stats.mass_min == 180.156
        assert result.mass_stats.mass_max == 180.156

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All filter params flow from MCP wrapper into api.list_metabolites."""
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["list_metabolites"](
                mock_ctx,
                search="glucose",
                metabolite_ids=["kegg.compound:C00031"],
                kegg_compound_ids=["C00031"],
                chebi_ids=["4167"],
                hmdb_ids=["HMDB0000122"],
                mnxm_ids=["MNXM1364061"],
                elements=["N"],
                mass_min=60.0,
                mass_max=1000.0,
                organism_names=["Prochlorococcus MED4"],
                pathway_ids=["kegg.pathway:ko00910"],
                evidence_sources=["transport"],
                summary=False,
                verbose=True,
                limit=10,
                offset=5,
            )
        mock_api.assert_called_once()
        kwargs = mock_api.call_args.kwargs
        assert kwargs["search"] == "glucose"
        assert kwargs["metabolite_ids"] == ["kegg.compound:C00031"]
        assert kwargs["kegg_compound_ids"] == ["C00031"]
        assert kwargs["chebi_ids"] == ["4167"]
        assert kwargs["hmdb_ids"] == ["HMDB0000122"]
        assert kwargs["mnxm_ids"] == ["MNXM1364061"]
        assert kwargs["elements"] == ["N"]
        assert kwargs["mass_min"] == 60.0
        assert kwargs["mass_max"] == 1000.0
        assert kwargs["organism_names"] == ["Prochlorococcus MED4"]
        assert kwargs["pathway_ids"] == ["kegg.pathway:ko00910"]
        assert kwargs["evidence_sources"] == ["transport"]
        assert kwargs["verbose"] is True
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 5

    @pytest.mark.asyncio
    async def test_validation_error_raises_tool_error(self, tool_fns, mock_ctx):
        """ValueError from api.list_metabolites becomes a ToolError."""
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            side_effect=ValueError("search must not be empty."),
        ):
            with pytest.raises(ToolError, match="search must not be empty"):
                await tool_fns["list_metabolites"](mock_ctx, search="")


# ---------------------------------------------------------------------------
# genes_by_metabolite — Phase 1 (Stage 1 RED)
# ---------------------------------------------------------------------------


_GBM_METAB_ROW = {
    "locus_tag": "PMM0944",
    "gene_name": "ureC",
    "product": "urease",
    "evidence_source": "metabolism",
    # Sparse-stripped at api/ — surface as None by Pydantic default
    "reaction_id": "kegg.reaction:R00131",
    "reaction_name": "Urea + 2H2O => CO2 + 2NH3",
    "ec_numbers": ["3.5.1.5"],
    "mass_balance": "balanced",
    "metabolite_id": "kegg.compound:C00086",
    "metabolite_name": "Urea",
    "metabolite_formula": "CH4N2O",
    "metabolite_mass": 60.032,
    "metabolite_chebi_id": "16199",
}

_GBM_TRANS_ROW = {
    "locus_tag": "PMM0974",
    "gene_name": "urtE",
    "product": "ABC-type urea transporter",
    "evidence_source": "transport",
    "transport_confidence": "substrate_confirmed",
    "tcdb_family_id": "tcdb:3.A.1.4.5",
    "tcdb_family_name": "tcdb:3.A.1.4.5",
    "metabolite_id": "kegg.compound:C00086",
    "metabolite_name": "Urea",
    "metabolite_formula": "CH4N2O",
    "metabolite_mass": 60.032,
    "metabolite_chebi_id": "16199",
}

_GBM_SAMPLE_API_RETURN = {
    "total_matching": 23,
    "returned": 2,
    "offset": 0,
    "truncated": True,
    "warnings": [],
    "not_found": {
        "metabolite_ids": [],
        "organism": None,
        "metabolite_pathway_ids": [],
    },
    "not_matched": [],
    "by_metabolite": [
        {
            "metabolite_id": "kegg.compound:C00086",
            "name": "Urea",
            "formula": "CH4N2O",
            "rows": 23,
            "gene_count": 18,
            "reaction_count": 4,
            "transporter_count": 14,
            "metabolism_rows": 4,
            "transport_substrate_confirmed_rows": 10,
            "transport_family_inferred_rows": 9,
        },
    ],
    "by_evidence_source": [
        {"evidence_source": "metabolism", "count": 4},
        {"evidence_source": "transport", "count": 19},
    ],
    "by_transport_confidence": [
        {"transport_confidence": "substrate_confirmed", "count": 10},
        {"transport_confidence": "family_inferred", "count": 9},
    ],
    "top_reactions": [
        {
            "reaction_id": "kegg.reaction:R00131",
            "name": "Urea + 2H2O => CO2 + 2NH3",
            "ec_numbers": ["3.5.1.5"],
            "gene_count": 4,
            "metabolite_count": 1,
        },
    ],
    "top_tcdb_families": [
        {
            "tcdb_family_id": "tcdb:3.A.1.4.5",
            "tcdb_family_name": "tcdb:3.A.1.4.5",
            "level_kind": "tc_specificity",
            "transport_confidence": "substrate_confirmed",
            "gene_count": 5,
            "metabolite_count": 1,
        },
    ],
    "top_gene_categories": [
        {"category": "Transport", "gene_count": 14},
    ],
    "top_genes": [
        {
            "locus_tag": "PMM0974",
            "gene_name": "urtE",
            "reaction_count": 0,
            "transporter_count": 1,
            "metabolite_count": 1,
            "metabolism_rows": 0,
            "transport_substrate_confirmed_rows": 2,
            "transport_family_inferred_rows": 0,
        },
    ],
    "gene_count_total": 18,
    "reaction_count_total": 4,
    "transporter_count_total": 14,
    "metabolite_count_total": 1,
    "results": [_GBM_METAB_ROW, _GBM_TRANS_ROW],
}


class TestGenesByMetaboliteWrapper:
    """MCP-wrapper tests for genes_by_metabolite."""

    _SAMPLE_API_RETURN = _GBM_SAMPLE_API_RETURN

    @pytest.mark.asyncio
    async def test_returns_response_type(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
            )
        assert result.total_matching == 23
        assert result.returned == 2
        assert result.truncated is True
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_compact_metabolism_row_fields(self, tool_fns, mock_ctx):
        """Metabolism row populates reaction_*, ec_numbers, mass_balance;
        per-arm-specific transport fields are None (sparse-strip behavior)."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
            )
        metab = next(
            r for r in result.results if r.evidence_source == "metabolism"
        )
        assert metab.locus_tag == "PMM0944"
        assert metab.gene_name == "ureC"
        assert metab.reaction_id == "kegg.reaction:R00131"
        assert metab.ec_numbers == ["3.5.1.5"]
        assert metab.mass_balance == "balanced"
        assert metab.metabolite_id == "kegg.compound:C00086"
        # Sparse: per-arm-specific fields on the OTHER arm are None
        assert metab.tcdb_family_id is None
        assert metab.tcdb_family_name is None
        assert metab.transport_confidence is None

    @pytest.mark.asyncio
    async def test_compact_transport_row_fields(self, tool_fns, mock_ctx):
        """Transport row populates tcdb_*, transport_confidence; metabolism
        per-arm-specific fields are None."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
            )
        trans = next(
            r for r in result.results if r.evidence_source == "transport"
        )
        assert trans.locus_tag == "PMM0974"
        assert trans.tcdb_family_id == "tcdb:3.A.1.4.5"
        assert trans.transport_confidence == "substrate_confirmed"
        # Sparse: metabolism-specific fields are None on transport rows
        assert trans.reaction_id is None
        assert trans.reaction_name is None
        assert trans.ec_numbers is None
        assert trans.mass_balance is None

    @pytest.mark.asyncio
    async def test_verbose_fields_optional(self, tool_fns, mock_ctx):
        """Verbose-only fields default to None / surface when populated."""
        verbose_metab = {
            **_GBM_METAB_ROW,
            "gene_category": "Amino acid metabolism",
            "metabolite_inchikey": "XSQUKJJJFZCRTK-UHFFFAOYSA-N",
            "metabolite_smiles": "NC(N)=O",
            "metabolite_mnxm_id": "MNXM731",
            "metabolite_hmdb_id": "HMDB0000294",
            "reaction_mnxr_id": "MNXR104471",
            "reaction_rhea_ids": ["20557"],
        }
        verbose_trans = {
            **_GBM_TRANS_ROW,
            "gene_category": "Transport",
            "metabolite_inchikey": "XSQUKJJJFZCRTK-UHFFFAOYSA-N",
            "metabolite_smiles": "NC(N)=O",
            "metabolite_mnxm_id": "MNXM731",
            "metabolite_hmdb_id": "HMDB0000294",
            "tcdb_level_kind": "tc_specificity",
            "tc_class_id": "tcdb:3",
        }
        api_return = {
            **self._SAMPLE_API_RETURN,
            "results": [verbose_metab, verbose_trans],
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=api_return,
        ):
            result = await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
                verbose=True,
            )
        m = next(
            r for r in result.results if r.evidence_source == "metabolism"
        )
        t = next(
            r for r in result.results if r.evidence_source == "transport"
        )
        assert m.gene_category == "Amino acid metabolism"
        assert m.metabolite_inchikey == "XSQUKJJJFZCRTK-UHFFFAOYSA-N"
        assert m.metabolite_mnxm_id == "MNXM731"
        assert m.reaction_mnxr_id == "MNXR104471"
        assert m.reaction_rhea_ids == ["20557"]
        # Sparse: TCDB verbose fields stay None on metabolism row
        assert m.tcdb_level_kind is None
        assert m.tc_class_id is None

        assert t.gene_category == "Transport"
        assert t.tcdb_level_kind == "tc_specificity"
        assert t.tc_class_id == "tcdb:3"
        # Sparse: reaction verbose fields stay None on transport row
        assert t.reaction_mnxr_id is None
        assert t.reaction_rhea_ids is None

    @pytest.mark.asyncio
    async def test_not_found_structure(self, tool_fns, mock_ctx):
        """not_found is a typed dict with metabolite_ids / organism /
        metabolite_pathway_ids buckets."""
        api_return = {
            **self._SAMPLE_API_RETURN,
            "not_found": {
                "metabolite_ids": ["kegg.compound:C99999"],
                "organism": "Bogus organism",
                "metabolite_pathway_ids": ["kegg.pathway:bogus"],
            },
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=api_return,
        ):
            result = await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
            )
        assert result.not_found.metabolite_ids == ["kegg.compound:C99999"]
        assert result.not_found.organism == "Bogus organism"
        assert (
            result.not_found.metabolite_pathway_ids == ["kegg.pathway:bogus"]
        )

    @pytest.mark.asyncio
    async def test_not_matched_top_level(self, tool_fns, mock_ctx):
        """not_matched is a top-level list[str] (distinct from not_found)."""
        api_return = {
            **self._SAMPLE_API_RETURN,
            "not_matched": ["kegg.compound:C00001"],
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=api_return,
        ):
            result = await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
            )
        assert result.not_matched == ["kegg.compound:C00001"]

    @pytest.mark.asyncio
    async def test_envelope_breakdowns_present(self, tool_fns, mock_ctx):
        """All envelope rollups surface on the Pydantic envelope."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
            )
        assert len(result.by_metabolite) == 1
        assert result.by_metabolite[0].metabolite_id == "kegg.compound:C00086"
        assert result.by_metabolite[0].metabolism_rows == 4
        assert result.by_metabolite[0].transport_substrate_confirmed_rows == 10
        assert result.by_metabolite[0].transport_family_inferred_rows == 9

        assert len(result.by_evidence_source) == 2
        es_set = {e.evidence_source for e in result.by_evidence_source}
        assert es_set == {"metabolism", "transport"}

        assert len(result.by_transport_confidence) == 2
        tc_set = {
            e.transport_confidence for e in result.by_transport_confidence
        }
        assert tc_set == {"substrate_confirmed", "family_inferred"}

        assert len(result.top_reactions) == 1
        assert result.top_reactions[0].reaction_id == "kegg.reaction:R00131"

        assert len(result.top_tcdb_families) == 1
        assert (
            result.top_tcdb_families[0].tcdb_family_id == "tcdb:3.A.1.4.5"
        )
        assert (
            result.top_tcdb_families[0].transport_confidence
            == "substrate_confirmed"
        )

        assert len(result.top_gene_categories) == 1
        assert result.top_gene_categories[0].category == "Transport"

        assert len(result.top_genes) == 1
        assert result.top_genes[0].locus_tag == "PMM0974"

    @pytest.mark.asyncio
    async def test_total_count_fields(self, tool_fns, mock_ctx):
        """gene_count_total / reaction_count_total / transporter_count_total /
        metabolite_count_total surface on the envelope."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
            )
        assert result.gene_count_total == 18
        assert result.reaction_count_total == 4
        assert result.transporter_count_total == 14
        assert result.metabolite_count_total == 1

    @pytest.mark.asyncio
    async def test_warnings_field_default_empty(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
            )
        assert result.warnings == []

    @pytest.mark.asyncio
    async def test_warnings_field_carries_family_inferred_string(
        self, tool_fns, mock_ctx,
    ):
        api_return = {
            **self._SAMPLE_API_RETURN,
            "warnings": [
                "Majority of transport rows are family_inferred (rolled-up "
                "from broad TCDB families). Re-run with "
                "transport_confidence='substrate_confirmed' for substrate-"
                "curated transporter genes only."
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=api_return,
        ):
            result = await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00088"],
                organism="Prochlorococcus MED4",
            )
        assert any("family_inferred" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All filter params flow from MCP wrapper into api.genes_by_metabolite."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
                ec_numbers=["6.3.1.2"],
                metabolite_pathway_ids=["kegg.pathway:ko00910"],
                mass_balance="balanced",
                gene_categories=["Transport"],
                transport_confidence="substrate_confirmed",
                evidence_sources=["transport"],
                summary=False,
                verbose=True,
                limit=10,
                offset=5,
            )
        mock_api.assert_called_once()
        kwargs = mock_api.call_args.kwargs
        assert kwargs["metabolite_ids"] == ["kegg.compound:C00086"]
        assert kwargs["organism"] == "Prochlorococcus MED4"
        assert kwargs["ec_numbers"] == ["6.3.1.2"]
        assert (
            kwargs["metabolite_pathway_ids"] == ["kegg.pathway:ko00910"]
        )
        assert kwargs["mass_balance"] == "balanced"
        assert kwargs["gene_categories"] == ["Transport"]
        assert kwargs["transport_confidence"] == "substrate_confirmed"
        assert kwargs["evidence_sources"] == ["transport"]
        assert kwargs["verbose"] is True
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 5

    @pytest.mark.asyncio
    async def test_validation_error_raises_tool_error(
        self, tool_fns, mock_ctx,
    ):
        """ValueError from api.genes_by_metabolite becomes a ToolError."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            side_effect=ValueError(
                "evidence_sources contains invalid value(s)"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["genes_by_metabolite"](
                    mock_ctx,
                    metabolite_ids=["kegg.compound:C00086"],
                    organism="Prochlorococcus MED4",
                    evidence_sources=["bogus"],
                )

    def test_in_expected_tools(self):
        assert "genes_by_metabolite" in EXPECTED_TOOLS


# ---------------------------------------------------------------------------
# metabolites_by_gene (MBG) — Tool 3 of chemistry slice 1
#
# Mirrors TestGenesByMetaboliteWrapper. Anchor flips from metabolite_ids
# → locus_tags + organism. Reuses GeneReactionMetaboliteTriplet verbatim.
# Adds two new envelope rollups (top_pathways, by_element) plus by_gene
# (gene-anchored mirror of GBM's by_metabolite).
#
# Spec: docs/tool-specs/metabolites_by_gene.md
# ---------------------------------------------------------------------------


_MBG_METAB_ROW = {
    "locus_tag": "PMM0963",
    "gene_name": "ureA",
    "product": "urease gamma subunit",
    "evidence_source": "metabolism",
    "reaction_id": "kegg.reaction:R00131",
    "reaction_name": "Urea + 2H2O => CO2 + 2NH3",
    "ec_numbers": ["3.5.1.5"],
    "mass_balance": "balanced",
    "metabolite_id": "kegg.compound:C00086",
    "metabolite_name": "Urea",
    "metabolite_formula": "CH4N2O",
    "metabolite_mass": 60.032,
    "metabolite_chebi_id": "16199",
}

_MBG_TRANS_ROW = {
    "locus_tag": "PMM0974",
    "gene_name": "urtE",
    "product": "ABC-type urea transporter",
    "evidence_source": "transport",
    "transport_confidence": "substrate_confirmed",
    "tcdb_family_id": "tcdb:3.A.1.4.5",
    "tcdb_family_name": "tcdb:3.A.1.4.5",
    "metabolite_id": "kegg.compound:C00086",
    "metabolite_name": "Urea",
    "metabolite_formula": "CH4N2O",
    "metabolite_mass": 60.032,
    "metabolite_chebi_id": "16199",
}

_MBG_SAMPLE_API_RETURN = {
    "total_matching": 15,
    "returned": 2,
    "offset": 0,
    "truncated": True,
    "warnings": [],
    "not_found": {
        "locus_tags": [],
        "organism": None,
        "metabolite_ids": [],
        "metabolite_pathway_ids": [],
        "metabolite_elements": [],
    },
    "not_matched": [],
    "by_gene": [
        {
            "locus_tag": "PMM0963",
            "gene_name": "ureA",
            "product": "urease gamma subunit",
            "rows": 5,
            "metabolite_count": 4,
            "reaction_count": 1,
            "transporter_count": 1,
            "metabolism_rows": 4,
            "transport_substrate_confirmed_rows": 1,
            "transport_family_inferred_rows": 0,
        },
    ],
    "by_evidence_source": [
        {"evidence_source": "metabolism", "count": 12},
        {"evidence_source": "transport", "count": 3},
    ],
    "by_transport_confidence": [
        {"transport_confidence": "substrate_confirmed", "count": 2},
        {"transport_confidence": "family_inferred", "count": 1},
    ],
    "by_element": [
        {"element": "H", "metabolite_count": 3},
        {"element": "O", "metabolite_count": 3},
        {"element": "C", "metabolite_count": 2},
        {"element": "N", "metabolite_count": 2},
    ],
    "top_metabolites": [
        {
            "metabolite_id": "kegg.compound:C00086",
            "name": "Urea",
            "formula": "CH4N2O",
            "gene_count": 3,
            "reaction_count": 1,
            "transporter_count": 1,
            "metabolism_rows": 12,
            "transport_substrate_confirmed_rows": 2,
            "transport_family_inferred_rows": 1,
        },
    ],
    "top_reactions": [
        {
            "reaction_id": "kegg.reaction:R00131",
            "name": "Urea + 2H2O => CO2 + 2NH3",
            "ec_numbers": ["3.5.1.5"],
            "gene_count": 3,
            "metabolite_count": 4,
        },
    ],
    "top_tcdb_families": [
        {
            "tcdb_family_id": "tcdb:3.A.1.4.5",
            "tcdb_family_name": "tcdb:3.A.1.4.5",
            "level_kind": "tc_specificity",
            "transport_confidence": "substrate_confirmed",
            "gene_count": 1,
            "metabolite_count": 1,
        },
    ],
    "top_gene_categories": [
        {"category": "Amino acid metabolism", "gene_count": 3},
    ],
    "top_pathways": [
        {
            "pathway_id": "kegg.pathway:ko00910",
            "pathway_name": "Nitrogen metabolism",
            "gene_count": 3,
            "pathway_reaction_count": 23,
            "pathway_metabolite_count": 35,
        },
    ],
    "gene_count_total": 3,
    "reaction_count_total": 1,
    "transporter_count_total": 3,
    "metabolite_count_total": 4,
    "results": [_MBG_METAB_ROW, _MBG_TRANS_ROW],
}


class TestMetabolitesByGeneWrapper:
    """MCP-wrapper tests for metabolites_by_gene."""

    _SAMPLE_API_RETURN = _MBG_SAMPLE_API_RETURN

    @pytest.mark.asyncio
    async def test_returns_response_type(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963", "PMM0964", "PMM0965"],
                organism="Prochlorococcus MED4",
            )
        assert result.total_matching == 15
        assert result.returned == 2
        assert result.truncated is True
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_compact_metabolism_row_fields(self, tool_fns, mock_ctx):
        """Metabolism row populates reaction_*, ec_numbers, mass_balance;
        per-arm-specific transport fields are None (sparse-strip)."""
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963", "PMM0964", "PMM0965"],
                organism="Prochlorococcus MED4",
            )
        metab = next(
            r for r in result.results if r.evidence_source == "metabolism"
        )
        assert metab.locus_tag == "PMM0963"
        assert metab.gene_name == "ureA"
        assert metab.reaction_id == "kegg.reaction:R00131"
        assert metab.ec_numbers == ["3.5.1.5"]
        assert metab.mass_balance == "balanced"
        assert metab.metabolite_id == "kegg.compound:C00086"
        # Sparse: per-arm-specific transport fields are None
        assert metab.tcdb_family_id is None
        assert metab.tcdb_family_name is None
        assert metab.transport_confidence is None

    @pytest.mark.asyncio
    async def test_compact_transport_row_fields(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963", "PMM0964", "PMM0965"],
                organism="Prochlorococcus MED4",
            )
        trans = next(
            r for r in result.results if r.evidence_source == "transport"
        )
        assert trans.locus_tag == "PMM0974"
        assert trans.tcdb_family_id == "tcdb:3.A.1.4.5"
        assert trans.transport_confidence == "substrate_confirmed"
        # Sparse: metabolism-specific fields are None on transport rows
        assert trans.reaction_id is None
        assert trans.reaction_name is None
        assert trans.ec_numbers is None
        assert trans.mass_balance is None

    @pytest.mark.asyncio
    async def test_verbose_fields_optional(self, tool_fns, mock_ctx):
        verbose_metab = {
            **_MBG_METAB_ROW,
            "gene_category": "Amino acid metabolism",
            "metabolite_inchikey": "XSQUKJJJFZCRTK-UHFFFAOYSA-N",
            "metabolite_smiles": "NC(N)=O",
            "metabolite_mnxm_id": "MNXM731",
            "metabolite_hmdb_id": "HMDB0000294",
            "reaction_mnxr_id": "MNXR104471",
            "reaction_rhea_ids": ["20557"],
        }
        verbose_trans = {
            **_MBG_TRANS_ROW,
            "gene_category": "Transport",
            "metabolite_inchikey": "XSQUKJJJFZCRTK-UHFFFAOYSA-N",
            "metabolite_smiles": "NC(N)=O",
            "metabolite_mnxm_id": "MNXM731",
            "metabolite_hmdb_id": "HMDB0000294",
            "tcdb_level_kind": "tc_specificity",
            "tc_class_id": "tcdb:3",
        }
        api_return = {
            **self._SAMPLE_API_RETURN,
            "results": [verbose_metab, verbose_trans],
        }
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=api_return,
        ):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963", "PMM0964", "PMM0965"],
                organism="Prochlorococcus MED4",
                verbose=True,
            )
        m = next(
            r for r in result.results if r.evidence_source == "metabolism"
        )
        t = next(
            r for r in result.results if r.evidence_source == "transport"
        )
        assert m.gene_category == "Amino acid metabolism"
        assert m.metabolite_inchikey == "XSQUKJJJFZCRTK-UHFFFAOYSA-N"
        assert m.reaction_mnxr_id == "MNXR104471"
        # Sparse: TCDB verbose fields stay None on metabolism row
        assert m.tcdb_level_kind is None
        assert m.tc_class_id is None

        assert t.gene_category == "Transport"
        assert t.tcdb_level_kind == "tc_specificity"
        assert t.tc_class_id == "tcdb:3"
        # Sparse: reaction verbose fields stay None on transport row
        assert t.reaction_mnxr_id is None
        assert t.reaction_rhea_ids is None

    @pytest.mark.asyncio
    async def test_not_found_structure(self, tool_fns, mock_ctx):
        """not_found is a typed dict with locus_tags / organism /
        metabolite_ids / metabolite_pathway_ids / metabolite_elements buckets."""
        api_return = {
            **self._SAMPLE_API_RETURN,
            "not_found": {
                "locus_tags": ["PMM9999"],
                "organism": "Bogus organism",
                "metabolite_ids": ["kegg.compound:C99999"],
                "metabolite_pathway_ids": ["kegg.pathway:bogus"],
                "metabolite_elements": ["Nx"],
            },
        }
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=api_return,
        ):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963"],
                organism="Prochlorococcus MED4",
            )
        assert result.not_found.locus_tags == ["PMM9999"]
        assert result.not_found.organism == "Bogus organism"
        assert result.not_found.metabolite_ids == ["kegg.compound:C99999"]
        assert (
            result.not_found.metabolite_pathway_ids
            == ["kegg.pathway:bogus"]
        )
        assert result.not_found.metabolite_elements == ["Nx"]

    @pytest.mark.asyncio
    async def test_not_matched_top_level(self, tool_fns, mock_ctx):
        """not_matched is a top-level list[str] (locus_tags that resolve in
        organism but have zero chemistry edges)."""
        api_return = {
            **self._SAMPLE_API_RETURN,
            "not_matched": ["PMM0005"],
        }
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=api_return,
        ):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963", "PMM0005"],
                organism="Prochlorococcus MED4",
            )
        assert result.not_matched == ["PMM0005"]

    @pytest.mark.asyncio
    async def test_envelope_breakdowns_present(self, tool_fns, mock_ctx):
        """All envelope rollups surface on the Pydantic envelope, including
        the new MBG-specific by_element + top_pathways."""
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963", "PMM0964", "PMM0965"],
                organism="Prochlorococcus MED4",
            )
        # by_gene — input-bounded gene rollup
        assert len(result.by_gene) == 1
        assert result.by_gene[0].locus_tag == "PMM0963"
        assert result.by_gene[0].metabolism_rows == 4
        assert result.by_gene[0].transport_substrate_confirmed_rows == 1

        assert len(result.by_evidence_source) == 2
        es_set = {e.evidence_source for e in result.by_evidence_source}
        assert es_set == {"metabolism", "transport"}

        assert len(result.by_transport_confidence) == 2
        tc_set = {
            e.transport_confidence for e in result.by_transport_confidence
        }
        assert tc_set == {"substrate_confirmed", "family_inferred"}

        # NEW MBG: by_element rollup
        assert len(result.by_element) == 4
        elements = {b.element for b in result.by_element}
        assert elements == {"H", "O", "C", "N"}

        # top_metabolites — data-driven top-10
        assert len(result.top_metabolites) == 1
        assert (
            result.top_metabolites[0].metabolite_id
            == "kegg.compound:C00086"
        )
        assert result.top_metabolites[0].gene_count == 3

        assert len(result.top_reactions) == 1
        assert result.top_reactions[0].reaction_id == "kegg.reaction:R00131"

        assert len(result.top_tcdb_families) == 1
        assert (
            result.top_tcdb_families[0].tcdb_family_id == "tcdb:3.A.1.4.5"
        )
        assert (
            result.top_tcdb_families[0].transport_confidence
            == "substrate_confirmed"
        )

        assert len(result.top_gene_categories) == 1
        assert result.top_gene_categories[0].category == "Amino acid metabolism"

        # NEW MBG: top_pathways rollup
        assert len(result.top_pathways) == 1
        p = result.top_pathways[0]
        assert p.pathway_id == "kegg.pathway:ko00910"
        assert p.pathway_name == "Nitrogen metabolism"
        assert p.gene_count == 3
        assert p.pathway_reaction_count == 23
        assert p.pathway_metabolite_count == 35

    @pytest.mark.asyncio
    async def test_total_count_fields(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963", "PMM0964", "PMM0965"],
                organism="Prochlorococcus MED4",
            )
        assert result.gene_count_total == 3
        assert result.reaction_count_total == 1
        assert result.transporter_count_total == 3
        assert result.metabolite_count_total == 4

    @pytest.mark.asyncio
    async def test_warnings_field_default_empty(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963", "PMM0964", "PMM0965"],
                organism="Prochlorococcus MED4",
            )
        assert result.warnings == []

    @pytest.mark.asyncio
    async def test_warnings_field_carries_family_inferred_string(
        self, tool_fns, mock_ctx,
    ):
        api_return = {
            **self._SAMPLE_API_RETURN,
            "warnings": [
                "Transport rows in this slice are dominated by `family_inferred` "
                "rollup (551 of 551 transport rows). For high-precision "
                "substrate-curated annotations only, set "
                "transport_confidence='substrate_confirmed' and/or "
                "evidence_sources=['transport']."
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=api_return,
        ):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0913"],
                organism="Prochlorococcus MED4",
            )
        assert any("family_inferred" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All filter params flow from MCP wrapper into api.metabolites_by_gene."""
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963", "PMM0964", "PMM0965"],
                organism="Prochlorococcus MED4",
                metabolite_elements=["N"],
                metabolite_ids=["kegg.compound:C00086"],
                ec_numbers=["3.5.1.5"],
                metabolite_pathway_ids=["kegg.pathway:ko00910"],
                mass_balance="balanced",
                gene_categories=["Amino acid metabolism"],
                transport_confidence="substrate_confirmed",
                evidence_sources=["transport"],
                summary=False,
                verbose=True,
                limit=10,
                offset=5,
            )
        mock_api.assert_called_once()
        kwargs = mock_api.call_args.kwargs
        assert kwargs["locus_tags"] == ["PMM0963", "PMM0964", "PMM0965"]
        assert kwargs["organism"] == "Prochlorococcus MED4"
        assert kwargs["metabolite_elements"] == ["N"]
        assert kwargs["metabolite_ids"] == ["kegg.compound:C00086"]
        assert kwargs["ec_numbers"] == ["3.5.1.5"]
        assert (
            kwargs["metabolite_pathway_ids"] == ["kegg.pathway:ko00910"]
        )
        assert kwargs["mass_balance"] == "balanced"
        assert kwargs["gene_categories"] == ["Amino acid metabolism"]
        assert kwargs["transport_confidence"] == "substrate_confirmed"
        assert kwargs["evidence_sources"] == ["transport"]
        assert kwargs["verbose"] is True
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 5

    @pytest.mark.asyncio
    async def test_validation_error_raises_tool_error(
        self, tool_fns, mock_ctx,
    ):
        """ValueError from api.metabolites_by_gene becomes a ToolError."""
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            side_effect=ValueError(
                "evidence_sources contains invalid value(s)"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["metabolites_by_gene"](
                    mock_ctx,
                    locus_tags=["PMM0963"],
                    organism="Prochlorococcus MED4",
                    evidence_sources=["bogus"],
                )

    def test_in_expected_tools(self):
        assert "metabolites_by_gene" in EXPECTED_TOOLS

    def test_response_envelope_field_presence(self):
        """MetabolitesByGeneResponse class exists with all spec'd envelope
        fields. This pins the Pydantic envelope shape independent of any
        api invocation."""
        from multiomics_explorer.mcp_server.tools import (
            MetabolitesByGeneResponse,
        )
        fields = set(MetabolitesByGeneResponse.model_fields.keys())
        for required in [
            "total_matching", "returned", "offset", "truncated",
            "warnings", "not_found", "not_matched",
            "by_gene", "by_evidence_source", "by_transport_confidence",
            "by_element",          # NEW vs GBM
            "top_metabolites", "top_reactions", "top_tcdb_families",
            "top_gene_categories",
            "top_pathways",        # NEW vs GBM
            "gene_count_total", "reaction_count_total",
            "transporter_count_total", "metabolite_count_total",
            "results",
        ]:
            assert required in fields, f"missing envelope field: {required}"

    def test_mbg_pydantic_classes_exist(self):
        """All Mbg* row classes exist with the spec'd names."""
        import multiomics_explorer.mcp_server.tools as tools_mod
        for name in [
            "MbgByGene",
            "MbgByEvidenceSource",
            "MbgByTransportConfidence",
            "MbgByElement",            # NEW vs GBM
            "MbgTopMetabolite",
            "MbgTopReaction",
            "MbgTopTcdbFamily",
            "MbgTopGeneCategory",
            "MbgTopPathway",           # NEW vs GBM
            "MbgNotFound",
            "MetabolitesByGeneResponse",
        ]:
            assert hasattr(tools_mod, name), f"missing class: {name}"

    def test_mbg_top_pathway_fields(self):
        """MbgTopPathway has the spec'd fields."""
        from multiomics_explorer.mcp_server.tools import MbgTopPathway
        fields = set(MbgTopPathway.model_fields.keys())
        for required in [
            "pathway_id",
            "pathway_name",
            "gene_count",
            "pathway_reaction_count",
            "pathway_metabolite_count",
        ]:
            assert required in fields, f"missing MbgTopPathway field: {required}"

    def test_mbg_by_element_fields(self):
        """MbgByElement has element + metabolite_count."""
        from multiomics_explorer.mcp_server.tools import MbgByElement
        fields = set(MbgByElement.model_fields.keys())
        assert fields == {"element", "metabolite_count"}

    def test_mbg_by_gene_fields(self):
        """MbgByGene mirrors GBM's GbmByMetabolite shape, gene-anchored."""
        from multiomics_explorer.mcp_server.tools import MbgByGene
        fields = set(MbgByGene.model_fields.keys())
        for required in [
            "locus_tag", "gene_name", "product",
            "rows", "metabolite_count", "reaction_count",
            "transporter_count", "metabolism_rows",
            "transport_substrate_confirmed_rows",
            "transport_family_inferred_rows",
        ]:
            assert required in fields, f"missing MbgByGene field: {required}"

    def test_mbg_not_found_fields(self):
        """MbgNotFound has all five buckets per spec."""
        from multiomics_explorer.mcp_server.tools import MbgNotFound
        fields = set(MbgNotFound.model_fields.keys())
        for required in [
            "locus_tags",
            "organism",
            "metabolite_ids",
            "metabolite_pathway_ids",
            "metabolite_elements",     # NEW vs GBM
        ]:
            assert required in fields, f"missing MbgNotFound field: {required}"

    def test_gene_reaction_metabolite_triplet_shared_with_gbm(self):
        """MBG REUSES GeneReactionMetaboliteTriplet verbatim — same class
        object as the one referenced by GenesByMetaboliteResponse.results."""
        from multiomics_explorer.mcp_server.tools import (
            GeneReactionMetaboliteTriplet,
            GenesByMetaboliteResponse,
            MetabolitesByGeneResponse,
        )
        # Pull the inner type from the `results: list[...]` annotation
        gbm_results_type = (
            GenesByMetaboliteResponse.model_fields["results"].annotation
        )
        mbg_results_type = (
            MetabolitesByGeneResponse.model_fields["results"].annotation
        )
        assert gbm_results_type == mbg_results_type
        # And both reference the canonical class
        # `list[GeneReactionMetaboliteTriplet]`
        assert "GeneReactionMetaboliteTriplet" in str(mbg_results_type)
        assert GeneReactionMetaboliteTriplet is not None


# ---------------------------------------------------------------------------
# tcdb / cazy: Literal enum acceptance on the 5 ontology wrappers
# ---------------------------------------------------------------------------
class TestOntologyLiteralAcceptsTcdbCazy:
    """The closed Literal[...] enums on the 5 ontology wrappers must accept
    'tcdb' and 'cazy'. We introspect the type hints (FastMCP uses these to
    build the JSON schema enforced at the MCP protocol boundary) — calling
    tool_fns[...] bypasses Pydantic validation, so the introspection test
    is the right enforcement point. (search_ontology uses an open `str`,
    so it has no Literal — only its description string changes.)
    """

    @staticmethod
    def _ontology_hint_str(tool_fns, tool_name: str) -> str:
        import typing
        fn = tool_fns[tool_name]
        hints = typing.get_type_hints(fn, include_extras=True)
        ontology_hint = hints.get("ontology")
        assert ontology_hint is not None, (
            f"ontology parameter not found in type hints for {tool_name}"
        )
        return str(ontology_hint)

    def test_genes_by_ontology_literal_includes_tcdb_cazy(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "genes_by_ontology")
        assert "Literal" in hint_str, (
            f"Expected Literal in genes_by_ontology ontology hint, got: {hint_str}"
        )
        assert "'tcdb'" in hint_str, (
            f"Expected 'tcdb' in genes_by_ontology ontology Literal, got: {hint_str}"
        )
        assert "'cazy'" in hint_str, (
            f"Expected 'cazy' in genes_by_ontology ontology Literal, got: {hint_str}"
        )

    def test_gene_ontology_terms_literal_includes_tcdb_cazy(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "gene_ontology_terms")
        assert "Literal" in hint_str, (
            f"Expected Literal in gene_ontology_terms ontology hint, got: {hint_str}"
        )
        assert "'tcdb'" in hint_str
        assert "'cazy'" in hint_str

    def test_ontology_landscape_literal_includes_tcdb_cazy(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "ontology_landscape")
        assert "Literal" in hint_str, (
            f"Expected Literal in ontology_landscape ontology hint, got: {hint_str}"
        )
        assert "'tcdb'" in hint_str
        assert "'cazy'" in hint_str

    def test_pathway_enrichment_literal_includes_tcdb_cazy(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "pathway_enrichment")
        assert "Literal" in hint_str, (
            f"Expected Literal in pathway_enrichment ontology hint, got: {hint_str}"
        )
        assert "'tcdb'" in hint_str
        assert "'cazy'" in hint_str

    def test_cluster_enrichment_literal_includes_tcdb_cazy(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "cluster_enrichment")
        assert "Literal" in hint_str, (
            f"Expected Literal in cluster_enrichment ontology hint, got: {hint_str}"
        )
        assert "'tcdb'" in hint_str
        assert "'cazy'" in hint_str

    def test_search_ontology_description_mentions_tcdb_cazy(self, tool_fns):
        """search_ontology uses open `str` (no Literal); the description
        string is the contract surface that lists supported ontology keys."""
        import typing
        fn = tool_fns["search_ontology"]
        hints = typing.get_type_hints(fn, include_extras=True)
        ontology_hint = hints.get("ontology")
        assert ontology_hint is not None
        # Annotated[str, Field(description="...")] — pull the description
        # via metadata. Iterate __metadata__ in case there's more than one
        # annotation entry.
        descriptions = [
            getattr(meta, "description", None) for meta in
            getattr(ontology_hint, "__metadata__", ())
        ]
        joined = " ".join(d for d in descriptions if d)
        assert "tcdb" in joined, (
            f"search_ontology description should mention 'tcdb'; got: {joined!r}"
        )
        assert "cazy" in joined, (
            f"search_ontology description should mention 'cazy'; got: {joined!r}"
        )


class TestExpectedToolsUnchangedForTcdbCazy:
    """Adding tcdb/cazy as ontology dimensions does NOT add new tool entries.
    EXPECTED_TOOLS must NOT grow."""

    def test_no_new_tools_added(self, tool_fns):
        # Sanity guardrail — implementer must not register any new tool.
        assert "tcdb" not in tool_fns, (
            "No tool should be named 'tcdb' — tcdb is a new ontology key, "
            "not a new tool"
        )
        assert "cazy" not in tool_fns

    def test_expected_tools_size_unchanged(self):
        # Brittle but cheap check: tcdb/cazy add NO rows to EXPECTED_TOOLS.
        # If this fails, someone added a new tool when the spec said no
        # new tools should be added.
        # Bumped 32 → 33 by chemistry slice-1 Tool 3 (metabolites_by_gene),
        # which is a legitimate new MCP tool — separate spec, lands
        # alongside this in the merge into main.
        assert len(EXPECTED_TOOLS) == 33, (
            f"EXPECTED_TOOLS unexpectedly has {len(EXPECTED_TOOLS)} entries; "
            "tcdb/cazy adds NO new tools (it's a Mode-B ontology surface "
            "refresh); MBG legitimately adds one."
        )


# ===========================================================================
# Cluster A — F1 informativeness surface (frozen spec 2026-05-04)
# ===========================================================================
# MCP wrapper layer: Pydantic models gain new fields, wrappers accept new
# `informative_only` param and forward it to the api/ layer.


class TestGeneOverviewF1SurfaceWrapper:
    """gene_overview Pydantic models add annotation_state +
    informative_annotation_types + by_annotation_state."""

    @pytest.mark.asyncio
    async def test_response_includes_by_annotation_state(self, tool_fns, mock_ctx):
        api_return = {
            "total_matching": 1,
            "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
            "by_category": [{"category": "DNA replication", "count": 1}],
            "by_annotation_type": [{"annotation_type": "go_mf", "count": 1}],
            "by_annotation_state": [
                {"annotation_state": "informative_multi", "count": 1},
            ],
            "has_expression": 0,
            "has_significant_expression": 0,
            "has_orthologs": 1,
            "has_clusters": 0,
            "has_derived_metrics": 0,
            "returned": 1,
            "truncated": False,
            "not_found": [],
            "results": [{
                "locus_tag": "PMM1428", "gene_name": "test",
                "product": "DNA polymerase III subunit beta",
                "gene_category": "DNA replication", "annotation_quality": 3,
                "organism_name": "Prochlorococcus MED4",
                "annotation_types": ["go_mf", "pfam"],
                "expression_edge_count": 0,
                "significant_up_count": 0, "significant_down_count": 0,
                "closest_ortholog_group_size": 9,
                "closest_ortholog_genera": ["Prochlorococcus"],
                "cluster_membership_count": 0, "cluster_types": [],
                "derived_metric_count": 0, "derived_metric_value_kinds": [],
                "annotation_state": "informative_multi",
                "informative_annotation_types": ["go_mf", "pfam"],
            }],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=api_return,
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMM1428"],
            )
        # New envelope rollup
        assert hasattr(result, "by_annotation_state")
        assert len(result.by_annotation_state) == 1
        # New per-row fields
        r = result.results[0]
        assert r.annotation_state == "informative_multi"
        assert r.informative_annotation_types == ["go_mf", "pfam"]


class TestGeneOntologyTermsF1SurfaceWrapper:
    """gene_ontology_terms wrapper accepts informative_only;
    response model has is_informative."""

    _SAMPLE_API_RETURN = {
        "total_matching": 1,
        "total_genes": 1,
        "total_terms": 1,
        "by_ontology": [{"ontology_type": "go_bp", "term_count": 1, "gene_count": 1}],
        "by_term": [{"term_id": "go:0006260", "term_name": "DNA replication",
                     "level": 5, "ontology_type": "go_bp", "count": 1}],
        "terms_per_gene_min": 1,
        "terms_per_gene_max": 1,
        "terms_per_gene_median": 1.0,
        "returned": 1,
        "truncated": False,
        "not_found": [],
        "no_terms": [],
        "results": [
            {"locus_tag": "PMM0001", "term_id": "go:0006260",
             "term_name": "DNA replication", "level": 5,
             "is_informative": True},
        ],
    }

    @pytest.mark.asyncio
    async def test_informative_only_param_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["gene_ontology_terms"](
                mock_ctx, locus_tags=["PMM0001"], organism="MED4",
                informative_only=True,
            )
        assert mock_api.call_args.kwargs["informative_only"] is True

    @pytest.mark.asyncio
    async def test_informative_only_default_false(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["gene_ontology_terms"](
                mock_ctx, locus_tags=["PMM0001"], organism="MED4",
            )
        # Default must be False for opt-in.
        assert mock_api.call_args.kwargs.get("informative_only") is False

    @pytest.mark.asyncio
    async def test_is_informative_in_result_row(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["gene_ontology_terms"](
                mock_ctx, locus_tags=["PMM0001"], organism="MED4",
            )
        assert result.results[0].is_informative is True


class TestSearchOntologyF1SurfaceWrapper:
    """search_ontology wrapper accepts informative_only; result has is_informative."""

    _SAMPLE_API_RETURN = {
        "total_entries": 847,
        "total_matching": 1,
        "score_max": 5.0,
        "score_median": 5.0,
        "returned": 1,
        "truncated": False,
        "results": [
            {"id": "go:0006260", "name": "DNA replication", "score": 5.0,
             "level": 5, "is_informative": True},
        ],
    }

    @pytest.mark.asyncio
    async def test_informative_only_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["search_ontology"](
                mock_ctx, search_text="replication", ontology="go_bp",
                informative_only=True,
            )
        assert mock_api.call_args.kwargs["informative_only"] is True

    @pytest.mark.asyncio
    async def test_informative_only_default_false(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["search_ontology"](
                mock_ctx, search_text="replication", ontology="go_bp",
            )
        assert mock_api.call_args.kwargs.get("informative_only") is False

    @pytest.mark.asyncio
    async def test_is_informative_in_result_row(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="replication", ontology="go_bp",
            )
        assert result.results[0].is_informative is True


class TestGenesByOntologyF1SurfaceWrapper:
    """genes_by_ontology wrapper accepts informative_only; detail row has is_informative."""

    _SAMPLE_API_RETURN = {
        "ontology": "go_bp",
        "organism_name": "Prochlorococcus MED4",
        "total_matching": 7,
        "total_genes": 7,
        "total_terms": 1,
        "total_categories": 1,
        "genes_per_term_min": 7, "genes_per_term_median": 7.0,
        "genes_per_term_max": 7,
        "terms_per_gene_min": 1, "terms_per_gene_median": 1.0,
        "terms_per_gene_max": 1,
        "by_category": [{"category": "Stress", "count": 7}],
        "by_level": [{"level": 1, "n_terms": 1, "n_genes": 7, "row_count": 7}],
        "top_terms": [{"term_id": "go:0050896",
                       "term_name": "response to stimulus", "count": 7,
                       "is_informative": True}],
        "n_best_effort_terms": 0,
        "not_found": [], "wrong_ontology": [],
        "wrong_level": [], "filtered_out": [],
        "returned": 1, "offset": 0, "truncated": False,
        "results": [
            {"locus_tag": "PMM0001", "gene_name": "x", "product": "y",
             "gene_category": "Stress", "term_id": "go:0050896",
             "term_name": "response to stimulus", "level": 1,
             "is_informative": True},
        ],
    }

    @pytest.mark.asyncio
    async def test_informative_only_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["genes_by_ontology"](
                mock_ctx, ontology="go_bp", organism="MED4", level=1,
                informative_only=True,
            )
        assert mock_api.call_args.kwargs["informative_only"] is True

    @pytest.mark.asyncio
    async def test_informative_only_default_false(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["genes_by_ontology"](
                mock_ctx, ontology="go_bp", organism="MED4", level=1,
            )
        assert mock_api.call_args.kwargs.get("informative_only") is False

    @pytest.mark.asyncio
    async def test_is_informative_in_result_row(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_by_ontology"](
                mock_ctx, ontology="go_bp", organism="MED4", level=1,
            )
        assert result.results[0].is_informative is True


class TestOntologyLandscapeF1SurfaceWrapper:
    """ontology_landscape wrapper accepts informative_only with default True."""

    _SAMPLE_API_RETURN = {
        "organism_name": "Prochlorococcus MED4",
        "organism_gene_count": 1976,
        "n_ontologies": 1,
        "by_ontology": {
            "cyanorak_role": {
                "best_level": 1, "best_genome_coverage": 0.75,
                "best_relevance_rank": 1, "n_levels": 3,
            },
        },
        "not_found": [],
        "not_matched": [],
        "results": [{
            "ontology_type": "cyanorak_role", "level": 1,
            "relevance_rank": 1,
            "n_terms_with_genes": 110, "n_genes_at_level": 1491,
            "genome_coverage": 0.755,
            "min_genes_per_term": 5, "q1_genes_per_term": 9.0,
            "median_genes_per_term": 14.0, "q3_genes_per_term": 23.0,
            "max_genes_per_term": 340,
            "n_levels_in_ontology": 3,
            "best_effort_share": None,
        }],
        "returned": 1, "total_matching": 3, "truncated": True, "offset": 0,
    }

    @pytest.mark.asyncio
    async def test_informative_only_default_true(self, tool_fns, mock_ctx):
        """Spec decision 3: default True for ontology_landscape."""
        with patch(
            "multiomics_explorer.api.functions.ontology_landscape",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["ontology_landscape"](
                mock_ctx, organism="MED4",
            )
        assert mock_api.call_args.kwargs.get("informative_only") is True

    @pytest.mark.asyncio
    async def test_informative_only_opt_out_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.ontology_landscape",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["ontology_landscape"](
                mock_ctx, organism="MED4", informative_only=False,
            )
        assert mock_api.call_args.kwargs["informative_only"] is False


# ===========================================================================
# A3 — Enrichment defaults wrapper layer (frozen spec 2026-05-04)
# ===========================================================================
# pathway_enrichment + cluster_enrichment MCP wrappers add `informative_only`
# (default True per spec § Decisions locked) and the per-row `is_informative`
# field on PathwayEnrichmentResult / ClusterEnrichmentResult.
#
# The two existing top-level introspection tests
# (TestPathwayEnrichmentWrapper.test_every_result_field_has_description and
# TestClusterEnrichmentWrapper.test_every_result_field_has_description) already
# loop over .model_fields, so once `is_informative: bool = Field(description=...)`
# is added by the api-updater, those tests automatically cover the new field's
# Field(description=...) contract — no new test required for that.


class TestPathwayEnrichmentInformativeOnlyWrapper:
    """pathway_enrichment MCP wrapper threads `informative_only` (default True)
    and surfaces `is_informative` on per-row Pydantic models."""

    _SAMPLE_API_ENVELOPE = {
        "organism_name": "MED4",
        "ontology": "cyanorak_role",
        "level": 1,
        "total_matching": 1,
        "returned": 1, "truncated": False, "offset": 0,
        "n_significant": 1,
        "by_experiment": [],
        "by_direction": [],
        "by_omics_type": [],
        "cluster_summary": {
            "n_clusters": 1,
            "n_tests_min": 1, "n_tests_median": 1.0, "n_tests_max": 1,
            "n_significant_min": 1, "n_significant_median": 1.0, "n_significant_max": 1,
            "universe_size_min": 3, "universe_size_median": 3.0, "universe_size_max": 3,
        },
        "top_clusters_by_min_padj": [],
        "top_pathways_by_padj": [],
        "not_found": [], "not_matched": [], "no_expression": [],
        "term_validation": {
            "not_found": [], "wrong_ontology": [],
            "wrong_level": [], "filtered_out": [],
        },
        "clusters_skipped": [],
        "results": [
            {
                "cluster": "exp1|T0|up",
                "experiment_id": "exp1",
                "name": "exp1",
                "timepoint": "T0",
                "timepoint_hours": 0.0,
                "timepoint_order": 0,
                "direction": "up",
                "omics_type": "transcriptomics",
                "table_scope": "rnaseq",
                "treatment_type": ["light_dark"],
                "background_factors": [],
                "is_time_course": False,
                "growth_phase": None,
                "term_id": "CR:OK",
                "term_name": "Real Pathway",
                "level": 1,
                "is_informative": True,
                "gene_ratio": "2/2",
                "gene_ratio_numeric": 1.0,
                "bg_ratio": "2/3",
                "bg_ratio_numeric": 0.6667,
                "rich_factor": 1.0,
                "fold_enrichment": 1.5,
                "pvalue": 0.001,
                "p_adjust": 0.001,
                "count": 2,
                "bg_count": 2,
                "signed_score": 3.0,
            },
        ],
    }

    @staticmethod
    def _api_result_double():
        """Mock api.pathway_enrichment return — the wrapper calls
        `result.to_envelope(...)`, so we need an object with that method."""
        envelope = TestPathwayEnrichmentInformativeOnlyWrapper._SAMPLE_API_ENVELOPE

        class _Result:
            @staticmethod
            def to_envelope(*, summary=False, limit=None, offset=0):
                return dict(envelope)
        return _Result()

    @pytest.mark.asyncio
    async def test_informative_only_default_true(self, tool_fns, mock_ctx):
        """Spec § Default value: pathway_enrichment defaults informative_only=True."""
        with patch(
            "multiomics_explorer.mcp_server.tools.api.pathway_enrichment",
            return_value=self._api_result_double(),
        ) as mock_api:
            await tool_fns["pathway_enrichment"](
                mock_ctx, organism="MED4", experiment_ids=["exp1"],
                ontology="cyanorak_role", level=1,
            )
        assert mock_api.call_args.kwargs.get("informative_only") is True, (
            "Wrapper default must be informative_only=True (spec § Decisions locked)"
        )

    @pytest.mark.asyncio
    async def test_informative_only_explicit_false_threaded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.mcp_server.tools.api.pathway_enrichment",
            return_value=self._api_result_double(),
        ) as mock_api:
            await tool_fns["pathway_enrichment"](
                mock_ctx, organism="MED4", experiment_ids=["exp1"],
                ontology="cyanorak_role", level=1,
                informative_only=False,
            )
        assert mock_api.call_args.kwargs["informative_only"] is False

    @pytest.mark.asyncio
    async def test_informative_only_explicit_true_threaded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.mcp_server.tools.api.pathway_enrichment",
            return_value=self._api_result_double(),
        ) as mock_api:
            await tool_fns["pathway_enrichment"](
                mock_ctx, organism="MED4", experiment_ids=["exp1"],
                ontology="cyanorak_role", level=1,
                informative_only=True,
            )
        assert mock_api.call_args.kwargs["informative_only"] is True

    @pytest.mark.asyncio
    async def test_is_informative_present_on_per_row_model(self, tool_fns, mock_ctx):
        """Spec § Pydantic field shape: is_informative on PathwayEnrichmentResult."""
        with patch(
            "multiomics_explorer.mcp_server.tools.api.pathway_enrichment",
            return_value=self._api_result_double(),
        ):
            response = await tool_fns["pathway_enrichment"](
                mock_ctx, organism="MED4", experiment_ids=["exp1"],
                ontology="cyanorak_role", level=1,
            )
        assert hasattr(response.results[0], "is_informative"), (
            "PathwayEnrichmentResult must expose `is_informative` per-row"
        )
        assert response.results[0].is_informative is True

    def test_is_informative_field_required(self):
        """Spec § Pydantic field shape: required field, not Optional.
        Pydantic must reject a row dict missing `is_informative`."""
        from pydantic import ValidationError
        from multiomics_explorer.mcp_server.tools import PathwayEnrichmentResult

        # Build a minimum-viable row WITHOUT is_informative; expect ValidationError.
        row_without = dict(self._SAMPLE_API_ENVELOPE["results"][0])
        row_without.pop("is_informative", None)
        with pytest.raises(ValidationError) as excinfo:
            PathwayEnrichmentResult(**row_without)
        assert "is_informative" in str(excinfo.value)

    def test_is_informative_field_in_model_fields(self):
        """The new field must appear on model_fields with a description."""
        from multiomics_explorer.mcp_server.tools import PathwayEnrichmentResult

        assert "is_informative" in PathwayEnrichmentResult.model_fields
        field = PathwayEnrichmentResult.model_fields["is_informative"]
        # Required field — Pydantic v2: PydanticUndefined as default sentinel.
        assert field.is_required(), (
            "is_informative must be required (spec § Pydantic field shape)"
        )
        assert field.description, "is_informative must have a Field(description=...)"


class TestClusterEnrichmentInformativeOnlyWrapper:
    """cluster_enrichment MCP wrapper — parallel of
    TestPathwayEnrichmentInformativeOnlyWrapper (Mode-B template-and-extend)."""

    _SAMPLE_API_ENVELOPE = {
        "analysis_id": "ca:test",
        "analysis_name": "Test Analysis",
        "organism_name": "MED4",
        "cluster_method": "kmeans",
        "cluster_type": "diel_cycle",
        "omics_type": "transcriptomics",
        "treatment_type": ["light_dark"],
        "background_factors": [],
        "growth_phases": [],
        "experiment_ids": ["exp:1"],
        "ontology": "cyanorak_role",
        "level": 1,
        "tree": None,
        "total_matching": 1,
        "returned": 1, "truncated": False, "offset": 0,
        "n_significant": 1,
        "by_cluster": [],
        "by_term": [],
        "clusters_tested": 1,
        "not_found": [], "not_matched": [],
        "clusters_skipped": [],
        "term_validation": {
            "not_found": [], "wrong_ontology": [],
            "wrong_level": [], "filtered_out": [],
        },
        "results": [
            {
                "cluster": "Cluster A",
                "cluster_id": "gc:1",
                "term_id": "CR:OK",
                "term_name": "Real Pathway",
                "level": 1,
                "is_informative": True,
                "gene_ratio": "2/2",
                "gene_ratio_numeric": 1.0,
                "bg_ratio": "2/3",
                "bg_ratio_numeric": 0.6667,
                "rich_factor": 1.0,
                "fold_enrichment": 1.5,
                "pvalue": 0.001,
                "p_adjust": 0.001,
                "count": 2,
                "bg_count": 2,
            },
        ],
    }

    @staticmethod
    def _api_result_double():
        envelope = TestClusterEnrichmentInformativeOnlyWrapper._SAMPLE_API_ENVELOPE

        class _Result:
            @staticmethod
            def to_envelope(*, summary=False, limit=None, offset=0):
                return dict(envelope)
        return _Result()

    @pytest.mark.asyncio
    async def test_informative_only_default_true(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.mcp_server.tools.api.cluster_enrichment",
            return_value=self._api_result_double(),
        ) as mock_api:
            await tool_fns["cluster_enrichment"](
                mock_ctx, analysis_id="ca:test", organism="MED4",
                ontology="cyanorak_role", level=1,
            )
        assert mock_api.call_args.kwargs.get("informative_only") is True

    @pytest.mark.asyncio
    async def test_informative_only_explicit_false_threaded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.mcp_server.tools.api.cluster_enrichment",
            return_value=self._api_result_double(),
        ) as mock_api:
            await tool_fns["cluster_enrichment"](
                mock_ctx, analysis_id="ca:test", organism="MED4",
                ontology="cyanorak_role", level=1,
                informative_only=False,
            )
        assert mock_api.call_args.kwargs["informative_only"] is False

    @pytest.mark.asyncio
    async def test_informative_only_explicit_true_threaded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.mcp_server.tools.api.cluster_enrichment",
            return_value=self._api_result_double(),
        ) as mock_api:
            await tool_fns["cluster_enrichment"](
                mock_ctx, analysis_id="ca:test", organism="MED4",
                ontology="cyanorak_role", level=1,
                informative_only=True,
            )
        assert mock_api.call_args.kwargs["informative_only"] is True

    @pytest.mark.asyncio
    async def test_is_informative_present_on_per_row_model(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.mcp_server.tools.api.cluster_enrichment",
            return_value=self._api_result_double(),
        ):
            response = await tool_fns["cluster_enrichment"](
                mock_ctx, analysis_id="ca:test", organism="MED4",
                ontology="cyanorak_role", level=1,
            )
        assert hasattr(response.results[0], "is_informative")
        assert response.results[0].is_informative is True

    def test_is_informative_field_required(self):
        from pydantic import ValidationError
        from multiomics_explorer.mcp_server.tools import ClusterEnrichmentResult

        row_without = dict(self._SAMPLE_API_ENVELOPE["results"][0])
        row_without.pop("is_informative", None)
        with pytest.raises(ValidationError) as excinfo:
            ClusterEnrichmentResult(**row_without)
        assert "is_informative" in str(excinfo.value)

    def test_is_informative_field_in_model_fields(self):
        from multiomics_explorer.mcp_server.tools import ClusterEnrichmentResult

        assert "is_informative" in ClusterEnrichmentResult.model_fields
        field = ClusterEnrichmentResult.model_fields["is_informative"]
        assert field.is_required(), (
            "is_informative must be required (spec § Pydantic field shape)"
        )
        assert field.description, "is_informative must have a Field(description=...)"


# ===========================================================================
# Phase 1 — P0 pass-through plumbing (metabolites surface refresh)
# Spec: docs/tool-specs/2026-05-05-phase1-pass-through-plumbing.md
# 6 tools, all additive — no new MCP tools registered (EXPECTED_TOOLS
# unchanged), only Pydantic models extended.
# ===========================================================================


class TestExpectedToolsUnchangedForPhase1Plumbing:
    """Phase 1 plumbing: 6 existing tools gain pass-through fields.
    No new tool gets registered."""

    def test_expected_tools_size_unchanged(self):
        # Phase 1 plumbing must NOT register a new MCP tool — all 6 tools
        # touched are existing surfaces (gene_overview, list_publications,
        # list_experiments, list_organisms, list_filter_values, list_metabolites).
        assert len(EXPECTED_TOOLS) == 33, (
            f"EXPECTED_TOOLS unexpectedly has {len(EXPECTED_TOOLS)} entries; "
            "Phase 1 plumbing adds no new tools — only field additions."
        )


class TestGeneOverviewPhase1PlumbingWrapper:
    """Pydantic GeneOverviewResult adds reaction_count, metabolite_count,
    transporter_count, evidence_sources. GeneOverviewResponse adds
    has_chemistry envelope key (spec §6.1)."""

    def _api_return_with_chem(self, locus_tag, **chem):
        defaults = {
            "reaction_count": 0, "metabolite_count": 0,
            "transporter_count": 0, "evidence_sources": [],
        }
        defaults.update(chem)
        return {
            "total_matching": 1,
            "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
            "by_category": [],
            "by_annotation_type": [],
            "by_annotation_state": [],
            "has_expression": 0,
            "has_significant_expression": 0,
            "has_orthologs": 0,
            "has_clusters": 0,
            "has_derived_metrics": 0,
            "has_chemistry": 1 if defaults["evidence_sources"] else 0,
            "returned": 1,
            "truncated": False,
            "not_found": [],
            "results": [{
                "locus_tag": locus_tag, "gene_name": None,
                "product": "test", "gene_category": "Unknown",
                "annotation_quality": 0,
                "organism_name": "Prochlorococcus MED4",
                "annotation_types": [],
                "annotation_state": "no_evidence",
                "informative_annotation_types": [],
                "expression_edge_count": 0,
                "significant_up_count": 0, "significant_down_count": 0,
                "closest_ortholog_group_size": 0,
                "closest_ortholog_genera": [],
                "cluster_membership_count": 0, "cluster_types": [],
                "derived_metric_count": 0, "derived_metric_value_kinds": [],
                **defaults,
            }],
        }

    @pytest.mark.asyncio
    async def test_pmm0392_transport_metabolomics_validates(self, tool_fns, mock_ctx):
        """Spec §6.1 verification: PMM0392 → 0 / 554 / 8 / [transport, metabolomics]."""
        api_return = self._api_return_with_chem(
            "PMM0392",
            reaction_count=0, metabolite_count=554, transporter_count=8,
            evidence_sources=["transport", "metabolomics"],
        )
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=api_return,
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMM0392"],
            )
        r = result.results[0]
        assert r.reaction_count == 0
        assert r.metabolite_count == 554
        assert r.transporter_count == 8
        assert r.evidence_sources == ["transport", "metabolomics"]

    @pytest.mark.asyncio
    async def test_pmm1428_no_chemistry_validates(self, tool_fns, mock_ctx):
        """Spec §6.1 verification: PMM1428 → all-zero / empty list."""
        api_return = self._api_return_with_chem("PMM1428")
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=api_return,
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMM1428"],
            )
        r = result.results[0]
        assert r.reaction_count == 0
        assert r.metabolite_count == 0
        assert r.transporter_count == 0
        assert r.evidence_sources == []

    @pytest.mark.asyncio
    async def test_pmm0001_metabolism_only_validates(self, tool_fns, mock_ctx):
        """Spec §6.1 verification: PMM0001 → 4 / 6 / 0 / ['metabolism']."""
        api_return = self._api_return_with_chem(
            "PMM0001",
            reaction_count=4, metabolite_count=6, transporter_count=0,
            evidence_sources=["metabolism"],
        )
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=api_return,
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMM0001"],
            )
        r = result.results[0]
        assert r.reaction_count == 4
        assert r.metabolite_count == 6
        assert r.evidence_sources == ["metabolism"]

    @pytest.mark.asyncio
    async def test_envelope_has_chemistry_field(self, tool_fns, mock_ctx):
        api_return = self._api_return_with_chem(
            "PMM0001", reaction_count=4, evidence_sources=["metabolism"],
        )
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=api_return,
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMM0001"],
            )
        assert hasattr(result, "has_chemistry")
        assert result.has_chemistry == 1


class TestListPublicationsPhase1PlumbingWrapper:
    """PublicationResult adds metabolite_count + metabolite_assay_count +
    metabolite_compartments per row (spec §6.2)."""

    @pytest.mark.asyncio
    async def test_metabolite_fields_per_row(self, tool_fns, mock_ctx):
        pub_with_metab = {
            "doi": "10.1234/cap2023", "title": "Capovilla 2023",
            "authors": ["Capovilla G"], "year": 2023, "journal": "ISME",
            "study_type": "metabolomics", "organisms": ["MIT9301"],
            "experiment_count": 4, "treatment_types": [],
            "background_factors": [], "omics_types": ["METABOLOMICS"],
            "metabolite_count": 92, "metabolite_assay_count": 92,
            "metabolite_compartments": ["extracellular", "whole_cell"],
        }
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 1, "total_matching": 1,
                "by_organism": [], "by_treatment_type": [],
                "by_background_factors": [], "by_omics_type": [],
                "by_value_kind": [], "by_metric_type": [],
                "by_compartment": [], "by_cluster_type": [],
                "returned": 1, "truncated": False, "not_found": [],
                "results": [pub_with_metab],
            },
        ):
            result = await tool_fns["list_publications"](mock_ctx)
        r = result.results[0]
        assert r.metabolite_count == 92
        assert r.metabolite_assay_count == 92
        assert r.metabolite_compartments == ["extracellular", "whole_cell"]

    @pytest.mark.asyncio
    async def test_zero_when_no_metabolomics_data(self, tool_fns, mock_ctx):
        """Most publications have metabolite_count=0 — fields are not optional."""
        pub_no_metab = {
            "doi": "10.1234/test", "title": "T", "authors": [],
            "year": 2024, "journal": "J", "study_type": "S",
            "organisms": [], "experiment_count": 0,
            "treatment_types": [], "background_factors": [],
            "omics_types": [], "metabolite_count": 0,
            "metabolite_assay_count": 0, "metabolite_compartments": [],
        }
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 1, "total_matching": 1,
                "by_organism": [], "by_treatment_type": [],
                "by_background_factors": [], "by_omics_type": [],
                "by_value_kind": [], "by_metric_type": [],
                "by_compartment": [], "by_cluster_type": [],
                "returned": 1, "truncated": False, "not_found": [],
                "results": [pub_no_metab],
            },
        ):
            result = await tool_fns["list_publications"](mock_ctx)
        r = result.results[0]
        assert r.metabolite_count == 0
        assert r.metabolite_assay_count == 0
        assert r.metabolite_compartments == []


class TestListExperimentsPhase1PlumbingWrapper:
    """ExperimentResult adds the same 3 metabolite fields per row (spec §6.3)."""

    _SUMMARY = {
        "total_entries": 1, "total_matching": 1,
        "by_organism": [], "by_treatment_type": [],
        "by_background_factors": [], "by_omics_type": [],
        "by_publication": [], "by_table_scope": [],
        "time_course_count": 0, "score_max": None, "score_median": None,
        "returned": 0, "truncated": True, "results": [],
    }

    _EXP_BASE = {
        "experiment_id": "exp_metab", "experiment_name": "Metab",
        "publication_doi": "10.1234/m", "authors": [],
        "organism_name": "MIT9301",
        "treatment_type": ["control"], "background_factors": [],
        "coculture_partner": None, "omics_type": "METABOLOMICS",
        "is_time_course": False, "table_scope": "all_detected_genes",
        "table_scope_detail": None, "gene_count": 0,
        "distinct_gene_count": 0,
        "genes_by_status": {
            "significant_up": 0, "significant_down": 0, "not_significant": 0,
        },
    }

    @pytest.mark.asyncio
    async def test_metabolite_fields_per_row(self, tool_fns, mock_ctx):
        exp = {
            **self._EXP_BASE,
            "metabolite_count": 30,
            "metabolite_assay_count": 30,
            "metabolite_compartments": ["extracellular"],
        }
        detail = {**self._SUMMARY, "returned": 1, "truncated": False,
                  "results": [exp]}
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=detail,
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        r = result.results[0]
        assert r.metabolite_count == 30
        assert r.metabolite_assay_count == 30
        assert r.metabolite_compartments == ["extracellular"]

    @pytest.mark.asyncio
    async def test_zero_when_no_metabolomics_data(self, tool_fns, mock_ctx):
        exp = {**self._EXP_BASE, "metabolite_count": 0,
               "metabolite_assay_count": 0, "metabolite_compartments": []}
        detail = {**self._SUMMARY, "returned": 1, "truncated": False,
                  "results": [exp]}
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=detail,
        ):
            result = await tool_fns["list_experiments"](mock_ctx)
        r = result.results[0]
        assert r.metabolite_count == 0
        assert r.metabolite_assay_count == 0
        assert r.metabolite_compartments == []


class TestListOrganismsPhase1PlumbingWrapper:
    """OrganismResult adds measured_metabolite_count per row;
    response adds by_measurement_capability binary envelope (spec §6.4)."""

    _ORG = {
        "organism_name": "Prochlorococcus MIT9301",
        "organism_type": "genome_strain",
        "genus": "Prochlorococcus", "species": "P. marinus",
        "strain": "MIT9301", "clade": "HLII", "ncbi_taxon_id": 167546,
        "gene_count": 1900, "publication_count": 5, "experiment_count": 12,
        "treatment_types": [], "omics_types": [],
        "measured_metabolite_count": 4,
    }

    @pytest.mark.asyncio
    async def test_measured_metabolite_count_per_row(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 1, "total_matching": 1,
                "returned": 1, "truncated": False, "not_found": [],
                "results": [self._ORG],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        org = result.results[0]
        assert org.measured_metabolite_count == 4

    @pytest.mark.asyncio
    async def test_envelope_has_by_measurement_capability(self, tool_fns, mock_ctx):
        """Spec §6.4: dict shape {has_metabolomics, no_metabolomics}."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 37, "total_matching": 37,
                "returned": 0, "truncated": True, "not_found": [],
                "by_measurement_capability": {
                    "has_metabolomics": 4, "no_metabolomics": 33,
                },
                "results": [],
            },
        ):
            result = await tool_fns["list_organisms"](
                mock_ctx, summary=True,
            )
        # The Pydantic model must surface the new envelope key.
        assert hasattr(result, "by_measurement_capability")
        cap = result.by_measurement_capability
        # Acceptable shapes: dict-like or Pydantic submodel — both expose
        # has/no_metabolomics.
        if isinstance(cap, dict):
            assert cap["has_metabolomics"] == 4
            assert cap["no_metabolomics"] == 33
        else:
            assert cap.has_metabolomics == 4
            assert cap.no_metabolomics == 33


class TestListFilterValuesPhase1PlumbingWrapper:
    """list_filter_values gains 2 new filter_type values: omics_type +
    evidence_source (spec §6.5)."""

    @pytest.mark.asyncio
    async def test_omics_type_branch_returns_8_values(self, tool_fns, mock_ctx):
        """Canonical OMICS_TYPE enum has 8 values incl. METABOLOMICS."""
        api_return = {
            "filter_type": "omics_type",
            "total_entries": 8, "returned": 8, "truncated": False,
            "results": [
                {"value": "RNASEQ", "count": 80},
                {"value": "PROTEOMICS", "count": 30},
                {"value": "METABOLOMICS", "count": 1},
                {"value": "MICROARRAY", "count": 12},
                {"value": "EXOPROTEOMICS", "count": 5},
                {"value": "VESICLE_DNASEQ", "count": 4},
                {"value": "VESICLE_PROTEOMICS", "count": 4},
                {"value": "PAIRED_RNASEQ_PROTEOME", "count": 2},
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value=api_return,
        ):
            result = await tool_fns["list_filter_values"](
                mock_ctx, filter_type="omics_type",
            )
        assert result.filter_type == "omics_type"
        values = {r.value for r in result.results}
        assert "METABOLOMICS" in values
        assert len(values) == 8

    @pytest.mark.asyncio
    async def test_evidence_source_branch_returns_3_values(self, tool_fns, mock_ctx):
        api_return = {
            "filter_type": "evidence_source",
            "total_entries": 3, "returned": 3, "truncated": False,
            "results": [
                {"value": "metabolism", "count": 2188},
                {"value": "transport", "count": 1355},
                {"value": "metabolomics", "count": 107},
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value=api_return,
        ):
            result = await tool_fns["list_filter_values"](
                mock_ctx, filter_type="evidence_source",
            )
        assert result.filter_type == "evidence_source"
        assert len(result.results) == 3
        values = {r.value for r in result.results}
        assert values == {"metabolism", "transport", "metabolomics"}

    def test_filter_type_literal_includes_phase1_values(self, tool_fns):
        """The Literal annotation on filter_type must enumerate the 2 new
        values (omics_type + evidence_source) so the JSON schema gates
        them at the MCP boundary (spec §6.5)."""
        import typing
        fn = tool_fns["list_filter_values"]
        hints = typing.get_type_hints(fn, include_extras=True)
        ft_hint = hints.get("filter_type")
        assert ft_hint is not None
        hint_str = str(ft_hint)
        assert "omics_type" in hint_str, (
            f"Phase 1 must add 'omics_type' to filter_type Literal; got: {hint_str}"
        )
        assert "evidence_source" in hint_str, (
            f"Phase 1 must add 'evidence_source' to filter_type Literal; got: {hint_str}"
        )


class TestListMetabolitesPhase1PlumbingWrapper:
    """MetaboliteResult adds 4 measurement pass-through fields per row;
    list_metabolites response gains by_measurement_coverage envelope (spec §6.6)."""

    _DETAIL_ROW = {
        "metabolite_id": "kegg.compound:C00031",
        "name": "D-Glucose",
        "formula": "C6H12O6",
        "elements": ["C", "H", "O"],
        "mass": 180.156,
        "gene_count": 320,
        "organism_count": 31,
        "transporter_count": 17,
        "evidence_sources": ["metabolism", "metabolomics"],
        "chebi_id": "4167",
        "pathway_ids": ["kegg.pathway:ko00010"],
        "pathway_count": 1,
        "measured_assay_count": 4,
        "measured_paper_count": 1,
        "measured_organisms": ["Prochlorococcus MIT9301"],
        "measured_compartments": ["whole_cell"],
    }

    _API_RETURN = {
        "total_entries": 3218, "total_matching": 1,
        "top_organisms": [], "top_pathways": [],
        "by_evidence_source": [],
        "xref_coverage": {
            "with_chebi": 0, "with_hmdb": 0, "with_mnxm": 0,
        },
        "mass_stats": {
            "mass_min": None, "mass_median": None, "mass_max": None,
        },
        "score_max": None, "score_median": None,
        "by_measurement_coverage": {
            "by_paper_count": [
                {"paper_count": 0, "n": 3111},
                {"paper_count": 1, "n": 99},
                {"paper_count": 2, "n": 8},
            ],
            "by_compartment": [
                {"compartment": "whole_cell", "n": 107},
                {"compartment": "extracellular", "n": 92},
            ],
        },
        "returned": 1, "offset": 0, "truncated": True,
        "not_found": {
            "metabolite_ids": [], "organism_names": [], "pathway_ids": [],
        },
        "results": [_DETAIL_ROW],
    }

    @pytest.mark.asyncio
    async def test_measurement_fields_per_row(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._API_RETURN,
        ):
            result = await tool_fns["list_metabolites"](mock_ctx)
        r = result.results[0]
        assert r.measured_assay_count == 4
        assert r.measured_paper_count == 1
        assert r.measured_organisms == ["Prochlorococcus MIT9301"]
        assert r.measured_compartments == ["whole_cell"]

    @pytest.mark.asyncio
    async def test_envelope_has_by_measurement_coverage(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._API_RETURN,
        ):
            result = await tool_fns["list_metabolites"](mock_ctx)
        # Pydantic-side surface: must expose the new envelope key.
        assert hasattr(result, "by_measurement_coverage")

    @pytest.mark.asyncio
    async def test_envelope_coverage_subkeys_present(self, tool_fns, mock_ctx):
        """Sub-keys: by_paper_count + by_compartment (spec §6.6)."""
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._API_RETURN,
        ):
            result = await tool_fns["list_metabolites"](mock_ctx)
        cov = result.by_measurement_coverage
        # Accept either dict shape or Pydantic submodel.
        if isinstance(cov, dict):
            assert "by_paper_count" in cov
            assert "by_compartment" in cov
        else:
            assert hasattr(cov, "by_paper_count")
            assert hasattr(cov, "by_compartment")
