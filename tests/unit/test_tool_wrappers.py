"""Unit tests for MCP tool wrapper logic — no Neo4j needed.

Tests the tool-level behavior (input validation, response formatting,
error messages, LIMIT injection) by mocking the Neo4j connection.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

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
    "kg_schema", "kg_release_info", "list_filter_values", "list_organisms", "resolve_gene",
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
    "list_metabolite_assays",
    "metabolites_by_quantifies_assay",
    "metabolites_by_flags_assay",
    "assays_by_metabolite",
    "gene_aa_sequence",
    "gene_neighbors",
    "discussed_by_publication",
    "ontology_term_details",
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
        """Each result row includes reaction_count and
        catalyzed_metabolite_count (catalysis-arm rename, KG-SYNC-001)."""
        sample_org_with_chem = {
            **self._SAMPLE_ORG,
            "reaction_count": 943,
            "catalyzed_metabolite_count": 1039,
        }
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 1, "total_matching": 1, "returned": 1,
                "truncated": False, "not_found": [], "results": [sample_org_with_chem],
                "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
                "top_metabolic_capability": [],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        org = result.results[0]
        assert org.reaction_count == 943
        assert org.catalyzed_metabolite_count == 1039

    @pytest.mark.asyncio
    async def test_top_metabolic_capability_envelope(self, tool_fns, mock_ctx):
        """Response includes top_metabolic_capability rollup with typed entries."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 2, "total_matching": 2, "returned": 0,
                "truncated": True, "not_found": [], "results": [],
                "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
                "top_metabolic_capability": [
                    {"organism_name": "Alteromonas macleodii EZ55",
                     "reaction_count": 1348,
                     "catalyzed_metabolite_count": 1428,
                     "transported_metabolite_count": 95},
                    {"organism_name": "Prochlorococcus MED4",
                     "reaction_count": 943,
                     "catalyzed_metabolite_count": 1039,
                     "transported_metabolite_count": 120},
                ],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx, summary=True)
        assert len(result.top_metabolic_capability) == 2
        top = result.top_metabolic_capability[0]
        assert top.organism_name == "Alteromonas macleodii EZ55"
        assert top.reaction_count == 1348
        assert top.catalyzed_metabolite_count == 1428
        # substrate_depth migration: entries carry transported_metabolite_count
        # (ranking unchanged — EZ55 leads on catalyzed_metabolite_count)
        assert top.transported_metabolite_count == 95
        assert result.top_metabolic_capability[1].transported_metabolite_count == 120

    @pytest.mark.asyncio
    async def test_row_transported_metabolite_count(self, tool_fns, mock_ctx):
        """substrate_depth migration: OrganismResult gains
        transported_metabolite_count (deepest-attachment transport breadth)."""
        sample = {
            **self._SAMPLE_ORG,
            "reaction_count": 943,
            "catalyzed_metabolite_count": 1039,
            "transported_metabolite_count": 120,
        }
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 1, "total_matching": 1, "returned": 1,
                "truncated": False, "not_found": [], "results": [sample],
                "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
                "top_metabolic_capability": [],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)
        assert result.results[0].transported_metabolite_count == 120


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
            await tool_fns["resolve_gene"](mock_ctx, identifier="x", offset=5)
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
            await tool_fns["genes_by_function"](mock_ctx, search_text="dna", offset=5)
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
            await tool_fns["gene_overview"](mock_ctx, locus_tags=["PMM1428"], offset=5)
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
            await tool_fns["gene_details"](mock_ctx, locus_tags=["PMM0001"], offset=5)
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
            await tool_fns["gene_homologs"](mock_ctx, locus_tags=["PMM0001"], offset=5)
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
            await tool_fns["search_ontology"](
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
            await tool_fns["gene_ontology_terms"](mock_ctx, locus_tags=["PMM0001"], organism="MED4", offset=5)
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
            await tool_fns["list_publications"](mock_ctx, offset=5)
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
            await tool_fns["list_experiments"](mock_ctx, offset=5)
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
        "n_experiments": 1,
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
                "is_time_course": "time_course",
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
        "filtered_out": [],
        "warnings": [],
        "not_found_experiments": [],
        "not_matched_experiments": [],
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
        assert result.filtered_out == []
        assert result.warnings == []

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
        assert exp.is_time_course == "time_course"
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
                    "is_time_course": "single_time_point",
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
            await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4", offset=5,
            )
        mock_api.assert_called_once()
        call_kwargs = mock_api.call_args.kwargs if mock_api.call_args.kwargs else {}
        assert call_kwargs.get("offset") == 5

    @pytest.mark.asyncio
    async def test_n_experiments_passed_through(self, tool_fns, mock_ctx):
        """(llm-review 2b.2) n_experiments surfaces on the response model."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4",
            )
        assert result.n_experiments == 1

    @pytest.mark.asyncio
    async def test_compact_experiment_validates_without_dropped_fields(
        self, tool_fns, mock_ctx,
    ):
        """(llm-review 2b.2) A compact api-layer experiment dict (as
        produced with verbose=False — no experiment_name / background_factors
        / omics_type / coculture_partner / table_scope_detail / timepoints
        keys) still validates against ExpressionByExperiment, and those
        fields render as None."""
        data = {
            **self._SAMPLE_API_RETURN,
            "experiments": [
                {
                    "experiment_id": "exp1",
                    "treatment_type": ["nitrogen_stress"],
                    "table_scope": "all_detected_genes",
                    "is_time_course": "time_course",
                    "matching_genes": 5,
                    "rows_by_status": {
                        "significant_up": 3,
                        "significant_down": 0,
                        "not_significant": 12,
                    },
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
        exp = result.experiments[0]
        assert exp.experiment_id == "exp1"
        assert exp.timepoints is None
        assert exp.experiment_name is None
        assert exp.background_factors is None
        assert exp.omics_type is None
        assert exp.coculture_partner is None
        assert exp.table_scope_detail is None


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
            await tool_fns["search_homolog_groups"](
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
            await tool_fns["genes_by_homolog_group"](
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
            await tool_fns["differential_expression_by_ortholog"](
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
                "has_any_edge": ["PMM0370"],
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
            [{"found_genes": [], "has_expression": [], "has_significant": [], "has_any_edge": [], "group_totals": []}],
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
    "catalyst_gene_count": 320,
    "organism_count": 31,
    "transporter_count": 17,
    "transporter_gene_count": 3051,
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
    # Phase 2 Item 2: rename top_pathways → top_metabolite_pathways and
    # element keys pathway_id/pathway_name → metabolite_pathway_id/
    # metabolite_pathway_name.
    "top_metabolite_pathways": [
        {
            "metabolite_pathway_id": "kegg.pathway:ko01100",
            "metabolite_pathway_name": "Metabolic pathways",
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
        assert r.catalyst_gene_count == 320
        assert r.organism_count == 31
        assert r.transporter_count == 17
        # substrate_depth migration: deepest-attachment transporter genes
        # (closes the transport-only trap loop: catalyst 0 / transporter > 0)
        assert r.transporter_gene_count == 3051
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
        """top_organisms, top_metabolite_pathways, by_evidence_source,
        xref_coverage, mass_stats are surfaced on the Pydantic envelope.

        Phase 2 Item 2: envelope key renamed from `top_pathways` to
        `top_metabolite_pathways`; per-element keys renamed from
        `pathway_id`/`pathway_name` to `metabolite_pathway_id`/
        `metabolite_pathway_name`.
        """
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_metabolites"](mock_ctx)
        assert len(result.top_organisms) == 1
        assert result.top_organisms[0].organism_name == "Prochlorococcus MED4"
        assert result.top_organisms[0].count == 1
        assert len(result.top_metabolite_pathways) == 1
        assert (
            result.top_metabolite_pathways[0].metabolite_pathway_id
            == "kegg.pathway:ko01100"
        )
        assert (
            result.top_metabolite_pathways[0].metabolite_pathway_name
            == "Metabolic pathways"
        )
        assert len(result.by_evidence_source) == 1
        assert result.by_evidence_source[0].evidence_source == "metabolism"
        assert result.xref_coverage.with_chebi == 1
        assert result.xref_coverage.with_hmdb == 0
        assert result.xref_coverage.with_mnxm == 1
        assert result.mass_stats.mass_min == 180.156
        assert result.mass_stats.mass_max == 180.156

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        """All filter params flow from MCP wrapper into api.list_metabolites.

        Phase 2 Item 1: `search` kwarg renamed to `search_text`.
        """
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["list_metabolites"](
                mock_ctx,
                search_text="glucose",
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
        assert kwargs["search_text"] == "glucose"
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
        """ValueError from api.list_metabolites becomes a ToolError.

        Phase 2 Item 1: `search` kwarg renamed to `search_text`.
        """
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            side_effect=ValueError("search must not be empty."),
        ):
            with pytest.raises(ToolError, match="search must not be empty"):
                await tool_fns["list_metabolites"](mock_ctx, search_text="")


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
    "substrate_depth": "most_specific",
    "tcdb_evidence_score": 0.8,
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
            "transport_most_specific_rows": 10,
            "transport_inherited_rows": 9,
        },
    ],
    "by_evidence_source": [
        {"evidence_source": "metabolism", "count": 4},
        {"evidence_source": "transport", "count": 19},
    ],
    "by_substrate_depth": [
        {"substrate_depth": "most_specific", "count": 10},
        {"substrate_depth": "inherited", "count": 9},
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
            "substrate_depth": "most_specific",
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
            "transport_most_specific_rows": 2,
            "transport_inherited_rows": 0,
            "transport_substrate_resolution": "resolved",
            "tcdb_evidence_score_max": 0.8,
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
        assert metab.substrate_depth is None
        assert metab.tcdb_evidence_score is None
        assert not hasattr(metab, "transport_confidence")

    @pytest.mark.asyncio
    async def test_compact_transport_row_fields(self, tool_fns, mock_ctx):
        """Transport row populates tcdb_*, substrate_depth; metabolism
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
        assert trans.substrate_depth == "most_specific"
        assert trans.tcdb_evidence_score == 0.8
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
        assert result.by_metabolite[0].transport_most_specific_rows == 10
        assert result.by_metabolite[0].transport_inherited_rows == 9
        assert not hasattr(result.by_metabolite[0], "transport_substrate_confirmed_rows")

        assert len(result.by_evidence_source) == 2
        es_set = {e.evidence_source for e in result.by_evidence_source}
        assert es_set == {"metabolism", "transport"}

        assert len(result.by_substrate_depth) == 2
        tc_set = {
            e.substrate_depth for e in result.by_substrate_depth
        }
        assert tc_set == {"most_specific", "inherited"}

        assert len(result.top_reactions) == 1
        assert result.top_reactions[0].reaction_id == "kegg.reaction:R00131"

        assert len(result.top_tcdb_families) == 1
        assert (
            result.top_tcdb_families[0].tcdb_family_id == "tcdb:3.A.1.4.5"
        )
        assert (
            result.top_tcdb_families[0].substrate_depth
            == "most_specific"
        )

        assert len(result.top_gene_categories) == 1
        assert result.top_gene_categories[0].category == "Transport"

        assert len(result.top_genes) == 1
        assert result.top_genes[0].locus_tag == "PMM0974"
        assert result.top_genes[0].transport_substrate_resolution == "resolved"
        assert result.top_genes[0].tcdb_evidence_score_max == 0.8

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
    async def test_warnings_field_carries_inherited_string(
        self, tool_fns, mock_ctx,
    ):
        api_return = {
            **self._SAMPLE_API_RETURN,
            "warnings": [
                "Most transport rows are `inherited` (23 of 29) — rolled up "
                "from family-level transport potential. Use "
                "substrate_depth=['most_specific'] to narrow."
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
        assert any("inherited" in w for w in result.warnings)

    # ---- substrate_depth migration (spec 2026-08-20) ----

    @pytest.mark.asyncio
    async def test_substrate_depth_forwarded_as_list(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
                substrate_depth=["most_specific", "inherited"],
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs["substrate_depth"] == ["most_specific", "inherited"]
        assert "transport_confidence" not in kwargs

    @pytest.mark.asyncio
    @pytest.mark.parametrize("old_value", ["substrate_confirmed", "family_inferred"])
    async def test_substrate_depth_old_value_strings_raise_tool_error(
        self, tool_fns, mock_ctx, old_value,
    ):
        """Retired `transport_confidence` value strings surface as ToolError
        with a rename pointer (api ValueError → ToolError)."""
        pointer = {"substrate_confirmed": "most_specific",
                   "family_inferred": "inherited"}[old_value]
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            side_effect=ValueError(
                f"substrate_depth value {old_value!r} was renamed to "
                f"{pointer!r}; valid values: ['most_specific', 'inherited']"
            ),
        ):
            with pytest.raises(ToolError, match=pointer):
                await tool_fns["genes_by_metabolite"](
                    mock_ctx,
                    metabolite_ids=["kegg.compound:C00086"],
                    organism="Prochlorococcus MED4",
                    substrate_depth=[old_value],
                )

    @pytest.mark.asyncio
    async def test_transport_confidence_kwarg_rejected(self, tool_fns, mock_ctx):
        """The old parameter name is gone from the wrapper signature."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ):
            with pytest.raises(TypeError):
                await tool_fns["genes_by_metabolite"](
                    mock_ctx,
                    metabolite_ids=["kegg.compound:C00086"],
                    organism="Prochlorococcus MED4",
                    transport_confidence="substrate_confirmed",
                )

    def test_substrate_depth_param_literal(self, tool_fns):
        """Wrapper param is `list[Literal['most_specific','inherited']] | None`."""
        import inspect
        import typing
        sig = inspect.signature(tool_fns["genes_by_metabolite"])
        assert "transport_confidence" not in sig.parameters
        ann = sig.parameters["substrate_depth"].annotation
        # Annotated[list[Literal[...]] | None, Field(...)] → unwrap
        inner = typing.get_args(ann)[0] if typing.get_origin(ann) is typing.Annotated else ann
        assert "most_specific" in repr(inner) and "inherited" in repr(inner)
        assert "substrate_confirmed" not in repr(inner)
        assert sig.parameters["substrate_depth"].default is None

    def test_row_model_fields(self):
        """GeneReactionMetaboliteTriplet: `transport_confidence` gone;
        `substrate_depth` (Literal | None) + `tcdb_evidence_score`
        (float | None) present, both defaulting to None (metabolism rows)."""
        from multiomics_explorer.mcp_server.tools import (
            GeneReactionMetaboliteTriplet,
        )
        fields = GeneReactionMetaboliteTriplet.model_fields
        assert "transport_confidence" not in fields
        assert "substrate_depth" in fields
        assert "tcdb_evidence_score" in fields
        row = GeneReactionMetaboliteTriplet(
            locus_tag="PMM0001", evidence_source="metabolism",
            metabolite_id="kegg.compound:C00086", metabolite_name="Urea",
        )
        assert row.substrate_depth is None
        assert row.tcdb_evidence_score is None
        assert "substrate_depth" in row.model_dump()
        assert "tcdb_evidence_score" in row.model_dump()
        with pytest.raises(Exception):
            GeneReactionMetaboliteTriplet(
                locus_tag="PMM0001", evidence_source="transport",
                metabolite_id="kegg.compound:C00086", metabolite_name="Urea",
                substrate_depth="substrate_confirmed",
            )

    def test_gbm_envelope_models(self):
        """GbmBySubstrateDepth (key `substrate_depth`) replaces
        GbmByTransportConfidence; GbmByMetabolite / GbmTopGene carry the
        renamed counters; GbmTopGene gains the gene-level TCDB facts;
        GbmTopTcdbFamily derives `substrate_depth`, not transport_confidence."""
        import multiomics_explorer.mcp_server.tools as tools_mod
        assert not hasattr(tools_mod, "GbmByTransportConfidence")
        depth_fields = tools_mod.GbmBySubstrateDepth.model_fields
        assert set(depth_fields) == {"substrate_depth", "count"}
        assert "by_substrate_depth" in tools_mod.GenesByMetaboliteResponse.model_fields
        assert "by_transport_confidence" not in tools_mod.GenesByMetaboliteResponse.model_fields
        for model in (tools_mod.GbmByMetabolite, tools_mod.GbmTopGene):
            f = model.model_fields
            assert "transport_most_specific_rows" in f
            assert "transport_inherited_rows" in f
            assert "transport_substrate_confirmed_rows" not in f
            assert "transport_family_inferred_rows" not in f
        tg = tools_mod.GbmTopGene.model_fields
        assert "transport_substrate_resolution" in tg
        assert "tcdb_evidence_score_max" in tg
        entry = tools_mod.GbmTopGene(
            locus_tag="PMM0001", reaction_count=1, transporter_count=0,
            metabolite_count=1, metabolism_rows=1,
            transport_most_specific_rows=0, transport_inherited_rows=0,
        )
        assert entry.transport_substrate_resolution is None
        assert entry.tcdb_evidence_score_max is None
        tf = tools_mod.GbmTopTcdbFamily.model_fields
        assert "substrate_depth" in tf
        assert "transport_confidence" not in tf

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
                substrate_depth=["most_specific"],
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
        assert kwargs["substrate_depth"] == ["most_specific"]
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

    # ---- Phase 3 Item 6.1 — None-padding lock-in on the wrapper path ----

    @pytest.mark.asyncio
    async def test_envelope_serializes_none_cross_arm_fields(
        self, tool_fns, mock_ctx,
    ):
        """After Item 6.1: model_dump() of the response must NOT strip
        None values from cross-arm fields. Default Pydantic v2 behavior
        preserves None on Optional fields — verify no `exclude_none=True`
        is added on the wrapper response path.

        This test exists to LOCK the behavior — it should pass green
        today (Pydantic v2 default) and catch a future regression where
        someone might accidentally add exclude_none=True on the response
        path.
        """
        # Construct a synthetic raw API response with one metabolism +
        # one transport row, with cross-arm fields explicitly None
        # (mirroring the post-Item-6.1 api/-layer output).
        raw = {
            "total_matching": 2,
            "returned": 2,
            "offset": 0,
            "truncated": False,
            "warnings": [],
            "not_found": {
                "metabolite_ids": [],
                "organism": None,
                "metabolite_pathway_ids": [],
            },
            "not_matched": [],
            "by_metabolite": [],
            "by_evidence_source": [],
            "by_substrate_depth": [],
            "top_reactions": [],
            "top_tcdb_families": [],
            "top_gene_categories": [],
            "top_genes": [],
            "gene_count_total": 1,
            "reaction_count_total": 1,
            "transporter_count_total": 1,
            "metabolite_count_total": 1,
            "results": [
                {
                    "locus_tag": "PMM0001",
                    "evidence_source": "metabolism",
                    "substrate_depth": None,    # None preserved
                    "tcdb_evidence_score": None,  # None preserved
                    "reaction_id": "kegg.reaction:R00131",
                    "reaction_name": "test reaction",
                    "ec_numbers": ["3.5.1.5"],
                    "mass_balance": "balanced",
                    "tcdb_family_id": None,           # None preserved
                    "tcdb_family_name": None,          # None preserved
                    "metabolite_id": "kegg.compound:C00086",
                    "metabolite_name": "Urea",
                },
                {
                    "locus_tag": "PMM0392",
                    "evidence_source": "transport",
                    "substrate_depth": "inherited",
                    "tcdb_evidence_score": 0.2,
                    "reaction_id": None,                # None preserved
                    "reaction_name": None,               # None preserved
                    "ec_numbers": None,                   # None preserved
                    "mass_balance": None,                  # None preserved
                    "tcdb_family_id": "tcdb:3.A.1",
                    "tcdb_family_name": "ABC superfamily",
                    "metabolite_id": "kegg.compound:C00086",
                    "metabolite_name": "Urea",
                },
            ],
        }

        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=raw,
        ):
            response = await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
            )

        dumped = response.model_dump()

        metab_row = next(
            r for r in dumped["results"] if r["evidence_source"] == "metabolism"
        )
        transp_row = next(
            r for r in dumped["results"] if r["evidence_source"] == "transport"
        )

        # Cross-arm None values must be present, not stripped
        assert "substrate_depth" in metab_row
        assert metab_row["substrate_depth"] is None
        assert "tcdb_evidence_score" in metab_row
        assert metab_row["tcdb_evidence_score"] is None
        assert "transport_confidence" not in metab_row
        assert "tcdb_family_id" in metab_row
        assert metab_row["tcdb_family_id"] is None
        assert "tcdb_family_name" in metab_row
        assert metab_row["tcdb_family_name"] is None

        assert "reaction_id" in transp_row
        assert transp_row["reaction_id"] is None
        assert "reaction_name" in transp_row
        assert transp_row["reaction_name"] is None
        assert "ec_numbers" in transp_row
        assert transp_row["ec_numbers"] is None
        assert "mass_balance" in transp_row
        assert transp_row["mass_balance"] is None


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
    "substrate_depth": "most_specific",
    "tcdb_evidence_score": 0.8,
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
            "transport_most_specific_rows": 1,
            "transport_inherited_rows": 0,
            "transport_substrate_resolution": "resolved",
            "tcdb_evidence_score_max": 0.8,
        },
    ],
    "by_evidence_source": [
        {"evidence_source": "metabolism", "count": 12},
        {"evidence_source": "transport", "count": 3},
    ],
    "by_substrate_depth": [
        {"substrate_depth": "most_specific", "count": 2},
        {"substrate_depth": "inherited", "count": 1},
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
            "transport_most_specific_rows": 2,
            "transport_inherited_rows": 1,
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
            "substrate_depth": "most_specific",
            "gene_count": 1,
            "metabolite_count": 1,
        },
    ],
    "top_gene_categories": [
        {"category": "Amino acid metabolism", "gene_count": 3},
    ],
    # Phase 2 Item 2: rename top_pathways → top_metabolite_pathways and
    # element keys pathway_id/pathway_name → metabolite_pathway_id/
    # metabolite_pathway_name. Other element keys unchanged.
    "top_metabolite_pathways": [
        {
            "metabolite_pathway_id": "kegg.pathway:ko00910",
            "metabolite_pathway_name": "Nitrogen metabolism",
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
        assert metab.substrate_depth is None
        assert metab.tcdb_evidence_score is None
        assert not hasattr(metab, "transport_confidence")

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
        assert trans.substrate_depth == "most_specific"
        assert trans.tcdb_evidence_score == 0.8
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
        assert result.by_gene[0].transport_most_specific_rows == 1
        assert result.by_gene[0].transport_substrate_resolution == "resolved"
        assert result.by_gene[0].tcdb_evidence_score_max == 0.8

        assert len(result.by_evidence_source) == 2
        es_set = {e.evidence_source for e in result.by_evidence_source}
        assert es_set == {"metabolism", "transport"}

        assert len(result.by_substrate_depth) == 2
        tc_set = {
            e.substrate_depth for e in result.by_substrate_depth
        }
        assert tc_set == {"most_specific", "inherited"}

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
            result.top_tcdb_families[0].substrate_depth
            == "most_specific"
        )

        assert len(result.top_gene_categories) == 1
        assert result.top_gene_categories[0].category == "Amino acid metabolism"

        # NEW MBG: top_metabolite_pathways rollup (Phase 2 Item 2: renamed
        # from top_pathways; per-element keys also renamed).
        assert len(result.top_metabolite_pathways) == 1
        p = result.top_metabolite_pathways[0]
        assert p.metabolite_pathway_id == "kegg.pathway:ko00910"
        assert p.metabolite_pathway_name == "Nitrogen metabolism"
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
    async def test_warnings_field_carries_inherited_string(
        self, tool_fns, mock_ctx,
    ):
        api_return = {
            **self._SAMPLE_API_RETURN,
            "warnings": [
                "1 gene (PMM0913) carries transport_substrate_resolution="
                "'family_inferred' — substrate breadth is reachability, not "
                "capability for these genes (resolved means at least one "
                "non-lumping attachment)."
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

    # ---- substrate_depth migration (spec 2026-08-20; mirrors GBM) ----

    @pytest.mark.asyncio
    async def test_substrate_depth_forwarded_as_list(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963"],
                organism="Prochlorococcus MED4",
                substrate_depth=["inherited"],
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs["substrate_depth"] == ["inherited"]
        assert "transport_confidence" not in kwargs

    @pytest.mark.asyncio
    @pytest.mark.parametrize("old_value", ["substrate_confirmed", "family_inferred"])
    async def test_substrate_depth_old_value_strings_raise_tool_error(
        self, tool_fns, mock_ctx, old_value,
    ):
        pointer = {"substrate_confirmed": "most_specific",
                   "family_inferred": "inherited"}[old_value]
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            side_effect=ValueError(
                f"substrate_depth value {old_value!r} was renamed to "
                f"{pointer!r}; valid values: ['most_specific', 'inherited']"
            ),
        ):
            with pytest.raises(ToolError, match=pointer):
                await tool_fns["metabolites_by_gene"](
                    mock_ctx,
                    locus_tags=["PMM0963"],
                    organism="Prochlorococcus MED4",
                    substrate_depth=[old_value],
                )

    @pytest.mark.asyncio
    async def test_transport_confidence_kwarg_rejected(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            with pytest.raises(TypeError):
                await tool_fns["metabolites_by_gene"](
                    mock_ctx,
                    locus_tags=["PMM0963"],
                    organism="Prochlorococcus MED4",
                    transport_confidence="substrate_confirmed",
                )

    def test_substrate_depth_param_literal(self, tool_fns):
        import inspect
        import typing
        sig = inspect.signature(tool_fns["metabolites_by_gene"])
        assert "transport_confidence" not in sig.parameters
        ann = sig.parameters["substrate_depth"].annotation
        inner = typing.get_args(ann)[0] if typing.get_origin(ann) is typing.Annotated else ann
        assert "most_specific" in repr(inner) and "inherited" in repr(inner)
        assert "substrate_confirmed" not in repr(inner)
        assert sig.parameters["substrate_depth"].default is None

    def test_mbg_envelope_models(self):
        """MbgBySubstrateDepth (key `substrate_depth`) replaces
        MbgByTransportConfidence; MbgByGene / MbgTopMetabolite carry the
        renamed counters; MbgByGene gains the gene-level TCDB facts;
        MbgTopTcdbFamily derives `substrate_depth`."""
        import multiomics_explorer.mcp_server.tools as tools_mod
        assert not hasattr(tools_mod, "MbgByTransportConfidence")
        assert set(tools_mod.MbgBySubstrateDepth.model_fields) == {
            "substrate_depth", "count",
        }
        resp = tools_mod.MetabolitesByGeneResponse.model_fields
        assert "by_substrate_depth" in resp
        assert "by_transport_confidence" not in resp
        for model in (tools_mod.MbgByGene, tools_mod.MbgTopMetabolite):
            f = model.model_fields
            assert "transport_most_specific_rows" in f
            assert "transport_inherited_rows" in f
            assert "transport_substrate_confirmed_rows" not in f
            assert "transport_family_inferred_rows" not in f
        entry = tools_mod.MbgByGene(
            locus_tag="PMM0001", rows=1, metabolite_count=1, reaction_count=1,
            transporter_count=0, metabolism_rows=1,
            transport_most_specific_rows=0, transport_inherited_rows=0,
        )
        assert entry.transport_substrate_resolution is None
        assert entry.tcdb_evidence_score_max is None
        tf = tools_mod.MbgTopTcdbFamily.model_fields
        assert "substrate_depth" in tf
        assert "transport_confidence" not in tf

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
                substrate_depth=["most_specific"],
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
        assert kwargs["substrate_depth"] == ["most_specific"]
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
            "by_gene", "by_evidence_source", "by_substrate_depth",
            "by_element",          # NEW vs GBM
            "top_metabolites", "top_reactions", "top_tcdb_families",
            "top_gene_categories",
            # Phase 2 Item 2: renamed from top_pathways.
            "top_metabolite_pathways",
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
            "MbgBySubstrateDepth",
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
        """MbgTopPathway has the spec'd fields. Phase 2 Item 2:
        pathway_id/pathway_name renamed to metabolite_pathway_id /
        metabolite_pathway_name. Other fields unchanged."""
        from multiomics_explorer.mcp_server.tools import MbgTopPathway
        fields = set(MbgTopPathway.model_fields.keys())
        for required in [
            "metabolite_pathway_id",
            "metabolite_pathway_name",
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
            "transport_most_specific_rows",
            "transport_inherited_rows",
            "transport_substrate_resolution",
            "tcdb_evidence_score_max",
        ]:
            assert required in fields, f"missing MbgByGene field: {required}"
        for retired in [
            "transport_substrate_confirmed_rows",
            "transport_family_inferred_rows",
        ]:
            assert retired not in fields, f"retired MbgByGene field: {retired}"

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

    # ---- Phase 3 Item 6.1 — None-padding lock-in on the wrapper path ----

    @pytest.mark.asyncio
    async def test_envelope_serializes_none_cross_arm_fields(
        self, tool_fns, mock_ctx,
    ):
        """After Item 6.1: model_dump() of the response must NOT strip
        None values from cross-arm fields. The MBG row class is shared
        with GBM (GeneReactionMetaboliteTriplet) — this test mirrors
        the GBM equivalent.

        This test exists to LOCK the behavior — it should pass green
        today (Pydantic v2 default) and catch a future regression where
        someone might accidentally add exclude_none=True on the response
        path.
        """
        raw = {
            "total_matching": 2,
            "returned": 2,
            "offset": 0,
            "truncated": False,
            "warnings": [],
            "not_found": {
                "locus_tags": [],
                "organism": None,
                "metabolite_ids": [],
                "metabolite_pathway_ids": [],
                "metabolite_elements": [],
            },
            "not_matched": [],
            "by_gene": [],
            "by_evidence_source": [],
            "by_substrate_depth": [],
            "by_element": [],
            "top_metabolites": [],
            "top_reactions": [],
            "top_tcdb_families": [],
            "top_gene_categories": [],
            "top_metabolite_pathways": [],
            "gene_count_total": 1,
            "reaction_count_total": 1,
            "transporter_count_total": 1,
            "metabolite_count_total": 1,
            "results": [
                {
                    "locus_tag": "PMM0963",
                    "evidence_source": "metabolism",
                    "substrate_depth": None,    # None preserved
                    "tcdb_evidence_score": None,  # None preserved
                    "reaction_id": "kegg.reaction:R00131",
                    "reaction_name": "test reaction",
                    "ec_numbers": ["3.5.1.5"],
                    "mass_balance": "balanced",
                    "tcdb_family_id": None,           # None preserved
                    "tcdb_family_name": None,          # None preserved
                    "metabolite_id": "kegg.compound:C00086",
                    "metabolite_name": "Urea",
                },
                {
                    "locus_tag": "PMM0913",
                    "evidence_source": "transport",
                    "substrate_depth": "inherited",
                    "tcdb_evidence_score": 0.2,
                    "reaction_id": None,                # None preserved
                    "reaction_name": None,               # None preserved
                    "ec_numbers": None,                   # None preserved
                    "mass_balance": None,                  # None preserved
                    "tcdb_family_id": "tcdb:3.A.1",
                    "tcdb_family_name": "ABC superfamily",
                    "metabolite_id": "kegg.compound:C00086",
                    "metabolite_name": "Urea",
                },
            ],
        }

        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=raw,
        ):
            response = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963", "PMM0913"],
                organism="Prochlorococcus MED4",
            )

        dumped = response.model_dump()

        metab_row = next(
            r for r in dumped["results"] if r["evidence_source"] == "metabolism"
        )
        transp_row = next(
            r for r in dumped["results"] if r["evidence_source"] == "transport"
        )

        # Cross-arm None values must be present, not stripped
        assert "substrate_depth" in metab_row
        assert metab_row["substrate_depth"] is None
        assert "tcdb_evidence_score" in metab_row
        assert metab_row["tcdb_evidence_score"] is None
        assert "transport_confidence" not in metab_row
        assert "tcdb_family_id" in metab_row
        assert metab_row["tcdb_family_id"] is None
        assert "tcdb_family_name" in metab_row
        assert metab_row["tcdb_family_name"] is None

        assert "reaction_id" in transp_row
        assert transp_row["reaction_id"] is None
        assert "reaction_name" in transp_row
        assert transp_row["reaction_name"] is None
        assert "ec_numbers" in transp_row
        assert transp_row["ec_numbers"] is None
        assert "mass_balance" in transp_row
        assert transp_row["mass_balance"] is None


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
        # Bumped 33 → 34 by Phase 5 list_metabolite_assays — likewise a
        # legitimate new MCP tool (metabolomics-assay discovery surface),
        # separate spec, parallel addition.
        # Bumped 34 → 37 by Phase 5 metabolites-by-assay 3-tool slice
        # (metabolites_by_quantifies_assay + metabolites_by_flags_assay +
        # assays_by_metabolite — all legitimate new MCP tools, separate
        # spec, parallel addition).
        # Bumped 37 → 39 by the gene-sequence-neighbors slice
        # (gene_aa_sequence + gene_neighbors — both legitimate new MCP tools,
        # separate spec, parallel addition).
        # Bumped 39 → 40 by kg_release_info (KG compatibility check tool).
        # Bumped 40 → 41 by discussed_by_publication (literature-index forward
        # tool; the 3 sibling extensions add fields only, no new tool).
        # Bumped 41 → 42 by ontology_term_details (annotation-trust surface
        # PR 3b — term-side drill-down, legitimate new MCP tool).
        assert len(EXPECTED_TOOLS) == 42, (
            f"EXPECTED_TOOLS unexpectedly has {len(EXPECTED_TOOLS)} entries; "
            "tcdb/cazy adds NO new tools (it's a Mode-B ontology surface "
            "refresh); MBG legitimately adds one; "
            "list_metabolite_assays legitimately adds one; "
            "metabolites-by-assay 3-tool slice legitimately adds three; "
            "gene_aa_sequence + gene_neighbors legitimately add two; "
            "discussed_by_publication legitimately adds one."
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
        # Bumped 33 → 34 by Phase 5 list_metabolite_assays (legitimate new
        # MCP tool — metabolomics-assay discovery surface, separate spec).
        # Bumped 34 → 37 by Phase 5 metabolites-by-assay 3-tool slice
        # (metabolites_by_quantifies_assay + metabolites_by_flags_assay +
        # assays_by_metabolite — all legitimate new MCP tools, separate spec).
        # Bumped 37 → 39 by the gene-sequence-neighbors slice
        # (gene_aa_sequence + gene_neighbors — both legitimate new MCP tools,
        # separate spec).
        # Bumped 39 → 40 by kg_release_info (KG compatibility check tool).
        # Bumped 40 → 41 by discussed_by_publication (literature-index forward
        # tool; its 3 sibling extensions add fields only, no new tool).
        # Bumped 41 → 42 by ontology_term_details (annotation-trust surface
        # PR 3b — term-side drill-down, legitimate new MCP tool).
        assert len(EXPECTED_TOOLS) == 42, (
            f"EXPECTED_TOOLS unexpectedly has {len(EXPECTED_TOOLS)} entries; "
            "Phase 1 plumbing adds no new tools — only field additions; "
            "Phase 5 list_metabolite_assays legitimately adds one; "
            "metabolites-by-assay 3-tool slice legitimately adds three; "
            "gene_aa_sequence + gene_neighbors legitimately add two."
        )


class TestGeneOverviewPhase1PlumbingWrapper:
    """Pydantic GeneOverviewResult adds reaction_count,
    catalyzed_metabolite_count, evidence_sources, and (substrate_depth
    migration 2026-08) tcdb_evidence_score_max / transported_metabolite_count /
    transport_substrate_resolution in place of transporter_count.
    GeneOverviewResponse adds has_chemistry envelope key (spec §6.1).
    Catalysis-arm rename (KG-SYNC-001): metabolite_count →
    catalyzed_metabolite_count — catalysis-only count; transport-only
    genes carry 0 (discriminate via tcdb_evidence_score_max / evidence_sources)."""

    def _api_return_with_chem(self, locus_tag, **chem):
        defaults = {
            "reaction_count": 0, "catalyzed_metabolite_count": 0,
            "tcdb_evidence_score_max": None,
            "transported_metabolite_count": 0,
            "transport_substrate_resolution": None,
            "evidence_sources": [],
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
        """PMM0392 → 0 / 0 catalyzed / tcdb_evidence_score_max 0.8 /
        transported_metabolite_count 13 / 'resolved' /
        [transport, metabolomics] (live-verified 2026-08-26)."""
        api_return = self._api_return_with_chem(
            "PMM0392",
            reaction_count=0, catalyzed_metabolite_count=0,
            tcdb_evidence_score_max=0.8,
            transported_metabolite_count=13,
            transport_substrate_resolution="resolved",
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
        assert r.catalyzed_metabolite_count == 0
        assert not hasattr(r, "transporter_count")
        assert r.tcdb_evidence_score_max == 0.8
        assert r.transported_metabolite_count == 13
        assert r.transport_substrate_resolution == "resolved"
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
        assert r.catalyzed_metabolite_count == 0
        assert not hasattr(r, "transporter_count")
        assert r.tcdb_evidence_score_max is None
        assert r.transported_metabolite_count == 0
        assert r.transport_substrate_resolution is None
        assert r.evidence_sources == []

    @pytest.mark.asyncio
    async def test_pmm0001_metabolism_only_validates(self, tool_fns, mock_ctx):
        """Spec §6.1 verification: PMM0001 → 4 / 6 catalyzed / no TCDB call
        (null / 0 / null, live-verified 2026-08-20) / ['metabolism']."""
        api_return = self._api_return_with_chem(
            "PMM0001",
            reaction_count=4, catalyzed_metabolite_count=6,
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
        assert r.catalyzed_metabolite_count == 6
        # no TCDB call: null score / 0 transported / null resolution
        assert not hasattr(r, "transporter_count")
        assert r.tcdb_evidence_score_max is None
        assert r.transported_metabolite_count == 0
        assert r.transport_substrate_resolution is None
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

    @pytest.mark.asyncio
    async def test_gene_overview_result_model_fields(self, tool_fns, mock_ctx):
        """GeneOverviewResult (nested in register_tools): transporter_count
        removed; the three gene-level TCDB fields present with
        null-means-no-call defaults (score/resolution nullable, count int)."""
        api_return = self._api_return_with_chem("PMM0001")
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=api_return,
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMM0001"],
            )
        row = result.results[0]
        fields = type(row).model_fields
        assert "transporter_count" not in fields
        for name in ("tcdb_evidence_score_max", "transported_metabolite_count",
                     "transport_substrate_resolution"):
            assert name in fields, f"missing GeneOverviewResult field: {name}"
        dumped = row.model_dump()
        assert "transporter_count" not in dumped
        assert dumped["tcdb_evidence_score_max"] is None
        assert dumped["transported_metabolite_count"] == 0
        assert dumped["transport_substrate_resolution"] is None


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


class TestListFilterValuesMultiLabelVocabsWrapper:
    """llm-review 2b.1: list_filter_values gains 5 new filter_type values —
    treatment_type, background_factors, table_scope, detection_status,
    expression_status — closed vocabularies read via _read_vocab_values."""

    @pytest.mark.asyncio
    async def test_treatment_type_branch_passes_through_applies_to(self, tool_fns, mock_ctx):
        api_return = {
            "filter_type": "treatment_type",
            "description": None, "total_entries": 3, "returned": 3, "truncated": False,
            "warnings": [],
            "results": [
                {"value": "diel", "applies_to": ["ClusteringAnalysis", "DerivedMetric"], "source": "vocabulary"},
                {"value": "iron", "applies_to": ["Experiment"], "source": "vocabulary"},
                {"value": "nitrogen", "applies_to": ["Experiment", "MetaboliteAssay"], "source": "vocabulary"},
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value=api_return,
        ):
            result = await tool_fns["list_filter_values"](
                mock_ctx, filter_type="treatment_type",
            )
        assert result.filter_type == "treatment_type"
        by_value = {r.value: r for r in result.results}
        assert by_value["nitrogen"].applies_to == ["Experiment", "MetaboliteAssay"]

    @pytest.mark.asyncio
    async def test_detection_status_branch_is_edge_scoped(self, tool_fns, mock_ctx):
        api_return = {
            "filter_type": "detection_status",
            "description": None, "total_entries": 3, "returned": 3, "truncated": False,
            "warnings": [],
            "results": [
                {"value": "detected", "applies_to": ["Assay_quantifies_metabolite"], "source": "vocabulary"},
                {"value": "not_detected", "applies_to": ["Assay_quantifies_metabolite"], "source": "vocabulary"},
                {"value": "sporadic", "applies_to": ["Assay_quantifies_metabolite"], "source": "vocabulary"},
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value=api_return,
        ):
            result = await tool_fns["list_filter_values"](
                mock_ctx, filter_type="detection_status",
            )
        assert result.filter_type == "detection_status"
        assert all(r.applies_to == ["Assay_quantifies_metabolite"] for r in result.results)

    def test_filter_type_literal_includes_the_five_new_values(self, tool_fns):
        """The Literal annotation on filter_type must enumerate the 5 new
        values so the JSON schema gates them at the MCP boundary."""
        import typing
        fn = tool_fns["list_filter_values"]
        hints = typing.get_type_hints(fn, include_extras=True)
        ft_hint = hints.get("filter_type")
        assert ft_hint is not None
        hint_str = str(ft_hint)
        for name in ("treatment_type", "background_factors", "table_scope",
                     "detection_status", "expression_status"):
            assert name in hint_str, (
                f"llm-review 2b.1 must add {name!r} to filter_type Literal; "
                f"got: {hint_str}"
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
        "catalyst_gene_count": 320,
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
        "top_organisms": [], "top_metabolite_pathways": [],
        "by_evidence_source": [],
        "xref_coverage": {
            "with_chebi": 0, "with_hmdb": 0, "with_mnxm": 0,
        },
        "mass_stats": {
            "mass_min": None, "mass_median": None, "mass_max": None,
        },
        "score_max": None, "score_median": None,
        # Post-api-transform shape (the api layer renames apoc.coll.frequencies
        # `{item, count}` to `{paper_count, count}` / `{compartment, count}`
        # before this dict reaches the MCP wrapper).
        "by_measurement_coverage": {
            "by_paper_count": [
                {"paper_count": 0, "count": 3111},
                {"paper_count": 1, "count": 99},
                {"paper_count": 2, "count": 8},
            ],
            "by_compartment": [
                {"compartment": "whole_cell", "count": 107},
                {"compartment": "extracellular", "count": 92},
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


# ===========================================================================
# Phase 2 — Cross-cutting renames + filter additions (frozen spec
# 2026-05-05-phase2-cross-cutting-renames.md). Stage 1 RED — failing tests.
# ===========================================================================
# Wrapper-layer tests:
#   - Item 2: Pydantic envelope reflects renamed fields (top_metabolite_pathways
#     + per-element renames).
#   - Item 3: exclude_metabolite_ids parameter accepted on 3 wrappers (forwarded
#     to api).
#   - Item 4: direction Literal accepts 'both' on the DE wrapper.
# ===========================================================================


class TestListMetabolitesWrapperPhase2:
    """Phase 2 items 2 + 3 on list_metabolites wrapper."""

    _SAMPLE_API_RETURN = _LM_SAMPLE_API_RETURN

    @pytest.mark.asyncio
    async def test_top_metabolite_pathways_field(self, tool_fns, mock_ctx):
        """Phase 2 Item 2: ListMetabolitesResponse parses envelope with
        the renamed `top_metabolite_pathways` key + per-element renames."""
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_metabolites"](mock_ctx)
        # Renamed envelope field surfaces on the Pydantic model.
        assert hasattr(result, "top_metabolite_pathways")
        # Old envelope name no longer exists.
        assert not hasattr(result, "top_pathways")
        # Per-element key renames.
        entry = result.top_metabolite_pathways[0]
        assert entry.metabolite_pathway_id == "kegg.pathway:ko01100"
        assert entry.metabolite_pathway_name == "Metabolic pathways"
        # Other element keys unchanged.
        assert entry.count == 1

    @pytest.mark.asyncio
    async def test_exclude_metabolite_ids_param_forwarded(
        self, tool_fns, mock_ctx,
    ):
        """Phase 2 Item 3: wrapper forwards exclude_metabolite_ids to api."""
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["list_metabolites"](
                mock_ctx,
                exclude_metabolite_ids=[
                    "kegg.compound:C00002", "kegg.compound:C00008",
                ],
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs["exclude_metabolite_ids"] == [
            "kegg.compound:C00002", "kegg.compound:C00008",
        ]

    @pytest.mark.asyncio
    async def test_exclude_metabolite_ids_accepts_none(
        self, tool_fns, mock_ctx,
    ):
        """exclude_metabolite_ids defaults to None (no error, not forwarded
        as a positional)."""
        with patch(
            "multiomics_explorer.api.functions.list_metabolites",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["list_metabolites"](mock_ctx)
        kwargs = mock_api.call_args.kwargs
        # Default forwarded as None or absent — both acceptable.
        assert kwargs.get("exclude_metabolite_ids") in (None, [])

    def test_exclude_metabolite_ids_typed_as_optional_list(self, tool_fns):
        """The wrapper signature's `exclude_metabolite_ids` annotation is
        `list[str] | None`.

        Direct call-time Pydantic validation isn't reliably enforced
        through `tool_fns` dispatch (FastMCP's `mcp.get_tool(name).fn`
        returns the raw Python function and bypasses Pydantic at
        raw-Python-dispatch time). So we pin the signature itself —
        `list[str] | None` — which is what FastMCP exposes to remote
        callers as the contract and what Pydantic enforces at the MCP
        boundary.
        """
        import types
        import typing
        fn = tool_fns["list_metabolites"]
        hints = typing.get_type_hints(fn, include_extras=True)
        annotation = hints["exclude_metabolite_ids"]
        # Annotated[list[str] | None, Field(...)] — strip Annotated.
        inner = (
            typing.get_args(annotation)[0]
            if hasattr(annotation, "__metadata__")
            else annotation
        )
        # Inner is `list[str] | None`; origin is types.UnionType (PEP 604)
        # or typing.Union for older typing.Optional forms.
        assert typing.get_origin(inner) in {types.UnionType, typing.Union}
        args = set(typing.get_args(inner))
        assert list[str] in args
        assert type(None) in args


class TestGenesByMetaboliteWrapperPhase2:
    """Phase 2 item 3 on genes_by_metabolite wrapper."""

    _SAMPLE_API_RETURN = _GBM_SAMPLE_API_RETURN

    @pytest.mark.asyncio
    async def test_exclude_metabolite_ids_param_forwarded(
        self, tool_fns, mock_ctx,
    ):
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
                exclude_metabolite_ids=["kegg.compound:C00002"],
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    @pytest.mark.asyncio
    async def test_exclude_metabolite_ids_accepts_none(
        self, tool_fns, mock_ctx,
    ):
        with patch(
            "multiomics_explorer.api.functions.genes_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["genes_by_metabolite"](
                mock_ctx,
                metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4",
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("exclude_metabolite_ids") in (None, [])

    def test_exclude_metabolite_ids_typed_as_optional_list(self, tool_fns):
        """The wrapper signature's `exclude_metabolite_ids` annotation is
        `list[str] | None`. (Same FastMCP raw-dispatch caveat as
        list_metabolites.)
        """
        import types
        import typing
        fn = tool_fns["genes_by_metabolite"]
        hints = typing.get_type_hints(fn, include_extras=True)
        annotation = hints["exclude_metabolite_ids"]
        inner = (
            typing.get_args(annotation)[0]
            if hasattr(annotation, "__metadata__")
            else annotation
        )
        assert typing.get_origin(inner) in {types.UnionType, typing.Union}
        args = set(typing.get_args(inner))
        assert list[str] in args
        assert type(None) in args


class TestMetabolitesByGeneWrapperPhase2:
    """Phase 2 items 2 + 3 on metabolites_by_gene wrapper."""

    _SAMPLE_API_RETURN = _MBG_SAMPLE_API_RETURN

    @pytest.mark.asyncio
    async def test_top_metabolite_pathways_field(self, tool_fns, mock_ctx):
        """Phase 2 Item 2: MetabolitesByGeneResponse parses envelope with
        the renamed `top_metabolite_pathways` key + per-element renames."""
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963", "PMM0964", "PMM0965"],
                organism="Prochlorococcus MED4",
            )
        assert hasattr(result, "top_metabolite_pathways")
        assert not hasattr(result, "top_pathways")
        entry = result.top_metabolite_pathways[0]
        assert entry.metabolite_pathway_id == "kegg.pathway:ko00910"
        assert entry.metabolite_pathway_name == "Nitrogen metabolism"
        # Other element keys unchanged.
        assert entry.gene_count == 3
        assert entry.pathway_reaction_count == 23
        assert entry.pathway_metabolite_count == 35

    @pytest.mark.asyncio
    async def test_exclude_metabolite_ids_param_forwarded(
        self, tool_fns, mock_ctx,
    ):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963"],
                organism="Prochlorococcus MED4",
                exclude_metabolite_ids=["kegg.compound:C00002"],
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    @pytest.mark.asyncio
    async def test_exclude_metabolite_ids_accepts_none(
        self, tool_fns, mock_ctx,
    ):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["metabolites_by_gene"](
                mock_ctx,
                locus_tags=["PMM0963"],
                organism="Prochlorococcus MED4",
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("exclude_metabolite_ids") in (None, [])

    def test_exclude_metabolite_ids_typed_as_optional_list(self, tool_fns):
        """The wrapper signature's `exclude_metabolite_ids` annotation is
        `list[str] | None`. (Same FastMCP raw-dispatch caveat as
        list_metabolites.)
        """
        import types
        import typing
        fn = tool_fns["metabolites_by_gene"]
        hints = typing.get_type_hints(fn, include_extras=True)
        annotation = hints["exclude_metabolite_ids"]
        inner = (
            typing.get_args(annotation)[0]
            if hasattr(annotation, "__metadata__")
            else annotation
        )
        assert typing.get_origin(inner) in {types.UnionType, typing.Union}
        args = set(typing.get_args(inner))
        assert list[str] in args
        assert type(None) in args


class TestDifferentialExpressionByGeneWrapperPhase2:
    """Phase 2 item 4 on differential_expression_by_gene wrapper.

    Expand the `direction` Literal from `Literal["up", "down"] | None`
    to `Literal["up", "down", "both"] | None`.
    """

    _SAMPLE_API_RETURN = {
        "organism_name": "Prochlorococcus MED4",
        "matching_genes": 4,
        "total_matching": 6,
        "rows_by_status": {
            "significant_up": 3,
            "significant_down": 3,
            "not_significant": 0,
        },
        "median_abs_log2fc": 1.5,
        "max_abs_log2fc": 3.5,
        "experiment_count": 1,
        "n_experiments": 1,
        "rows_by_treatment_type": {"nitrogen_stress": 6},
        "rows_by_background_factors": {},
        "by_table_scope": {"all_detected_genes": 6},
        "top_categories": [],
        "experiments": [],
        "not_found": [],
        "no_expression": [],
        "filtered_out": [],
        "warnings": [],
        "not_found_experiments": [],
        "not_matched_experiments": [],
        "returned": 0,
        "truncated": True,
        "results": [],
    }

    @pytest.mark.asyncio
    async def test_direction_both_accepted(self, tool_fns, mock_ctx):
        """direction='both' is accepted by Pydantic Literal validation."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4", direction="both",
            )
        # direction='both' must reach the api layer
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("direction") == "both"
        # Response model still builds
        assert result.organism_name == "Prochlorococcus MED4"

    def test_direction_literal_includes_both(self, tool_fns):
        """The wrapper signature's `direction` Literal includes 'both'.

        Inspects the FastMCP-registered function annotation: the Literal
        for the `direction` param must contain {'up', 'down', 'both'}
        after Phase 2 Item 4 lands. (Direct call-time Pydantic
        validation isn't reliably enforced through tool_fns dispatch,
        so we pin the signature itself.)
        """
        import typing
        fn = tool_fns["differential_expression_by_gene"]
        hints = typing.get_type_hints(fn, include_extras=True)
        direction_hint = hints.get("direction")
        assert direction_hint is not None
        # Walk the Annotated wrapper to extract the Literal args.
        # `direction_hint` looks like Annotated[Literal[...] | None, Field(...)].
        # Strip Annotated/Union; collect Literal arg sets.
        def _literal_values(tp):
            o = typing.get_origin(tp)
            if o is typing.Literal:
                return set(typing.get_args(tp))
            vals: set = set()
            for arg in typing.get_args(tp):
                vals.update(_literal_values(arg))
            return vals
        literal_vals = _literal_values(direction_hint)
        # Phase 2 Item 4: 'both' must be one of the accepted values.
        assert "both" in literal_vals
        # Existing values still present (no regression).
        assert "up" in literal_vals
        assert "down" in literal_vals
        # 'invalid' is NOT a Literal value.
        assert "invalid" not in literal_vals

    @pytest.mark.asyncio
    async def test_direction_up_still_accepted(self, tool_fns, mock_ctx):
        """Existing 'up' value still accepted (no regression)."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4", direction="up",
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("direction") == "up"

    @pytest.mark.asyncio
    async def test_direction_down_still_accepted(self, tool_fns, mock_ctx):
        """Existing 'down' value still accepted (no regression)."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4", direction="down",
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("direction") == "down"


# ---------------------------------------------------------------------------
# list_metabolite_assays — Phase 5 (RED stage; wrapper + Pydantic models
# land in GREEN stage Task 11). Mirrors TestListDerivedMetricsWrapper.
# Plan: docs/superpowers/plans/2026-05-06-list-metabolite-assays.md Task 10
# ---------------------------------------------------------------------------


class TestListMetaboliteAssaysWrapper:
    """MCP wrapper tests — calls api.list_metabolite_assays."""

    _SAMPLE_API_RETURN = {
        "total_entries": 10,
        "total_matching": 10,
        "metabolite_count_total": 768,
        "by_organism": [{"organism_name": "Prochlorococcus MIT9301", "count": 4}],
        "by_value_kind": [{"value_kind": "numeric", "count": 8}],
        "by_compartment": [{"compartment": "whole_cell", "count": 7}],
        "top_metric_types": [{"metric_type": "cellular_concentration", "count": 5}],
        "by_treatment_type": [{"treatment_type": "carbon", "count": 2}],
        "by_background_factors": [{"background_factor": "axenic", "count": 10}],
        "by_growth_phase": [],
        "by_detection_status": [
            {"detection_status": "not_detected", "count": 902},
            {"detection_status": "detected", "count": 247},
            {"detection_status": "sporadic", "count": 51},
        ],
        "score_max": None, "score_median": None,
        "returned": 0, "offset": 0, "truncated": True,
        "not_found": {
            "assay_ids": [], "metabolite_ids": [],
            "experiment_ids": [], "publication_doi": [],
        },
        "results": [],
    }

    @pytest.mark.asyncio
    async def test_summary_returns_response_envelope(self, tool_fns, mock_ctx):
        """Wrapper returns Pydantic ListMetaboliteAssaysResponse envelope."""
        with patch(
            "multiomics_explorer.api.functions.list_metabolite_assays",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_metabolite_assays"](mock_ctx, summary=True)
        assert result.total_entries == 10
        assert result.total_matching == 10
        assert result.metabolite_count_total == 768
        assert len(result.by_organism) == 1
        assert result.by_organism[0].organism_name == "Prochlorococcus MIT9301"
        assert result.by_organism[0].count == 4
        assert len(result.by_value_kind) == 1
        assert result.by_value_kind[0].value_kind == "numeric"
        assert len(result.by_detection_status) == 3
        # detected / sporadic / not_detected all surface on envelope
        statuses = {b.detection_status for b in result.by_detection_status}
        assert statuses == {"detected", "sporadic", "not_detected"}
        assert result.results == []

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        """When total_matching > returned → truncated=True."""
        api_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 10,
            "returned": 2,
            "truncated": True,
            "results": [
                {
                    "assay_id": "metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration",
                    "name": "MIT9301 intracellular metabolite concentration",
                    "metric_type": "cellular_concentration",
                    "value_kind": "numeric",
                    "rankable": True,
                    "unit": "mol/cell",
                    "field_description": "Intracellular metabolite concentration.",
                    "organism_name": "Prochlorococcus MIT9301",
                    "experiment_id": "exp:foo",
                    "publication_doi": "10.1128/msystems.01261-22",
                    "compartment": "whole_cell",
                    "omics_type": "METABOLOMICS",
                    "treatment_type": ["carbon"],
                    "background_factors": ["axenic"],
                    "growth_phases": [],
                    "total_metabolite_count": 92,
                    "aggregation_method": "mean_across_replicates",
                    "preferred_id": "metabolite_assay_id",
                    "value_min": 0.0, "value_q1": 0.001, "value_median": 0.005,
                    "value_q3": 0.012, "value_max": 0.16,
                    "timepoints": [],
                    "detection_status_counts": [
                        {"detection_status": "detected", "count": 47},
                        {"detection_status": "not_detected", "count": 45},
                    ],
                },
                {
                    "assay_id": "metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration",
                    "name": "MIT9313 chitosan intracellular concentration",
                    "metric_type": "cellular_concentration",
                    "value_kind": "numeric",
                    "rankable": True,
                    "unit": "fg/cell",
                    "field_description": "Capovilla 2023 chitosan paper.",
                    "organism_name": "Prochlorococcus MIT9313",
                    "experiment_id": "exp:bar",
                    "publication_doi": "10.1073/pnas.2213271120",
                    "compartment": "whole_cell",
                    "omics_type": "METABOLOMICS",
                    "treatment_type": ["carbon"],
                    "background_factors": ["axenic"],
                    "growth_phases": [],
                    "total_metabolite_count": 64,
                    "aggregation_method": "mean_across_replicates",
                    "preferred_id": "metabolite_assay_id",
                    "value_min": 0.0, "value_q1": 0.0, "value_median": 0.001,
                    "value_q3": 0.01, "value_max": 0.5,
                    "timepoints": ["4 days", "6 days"],
                    "detection_status_counts": [
                        {"detection_status": "detected", "count": 27},
                        {"detection_status": "sporadic", "count": 30},
                        {"detection_status": "not_detected", "count": 7},
                    ],
                },
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.list_metabolite_assays",
            return_value=api_return,
        ):
            result = await tool_fns["list_metabolite_assays"](mock_ctx, limit=2)
        assert result.returned == 2
        assert result.total_matching == 10
        assert result.truncated is True
        assert len(result.results) == 2
        # First row: detection_status_counts surfaces as typed sub-models
        first = result.results[0]
        assert first.value_kind == "numeric"
        assert first.rankable is True
        assert first.compartment == "whole_cell"
        assert len(first.detection_status_counts) == 2
        assert first.timepoints == []

    @pytest.mark.asyncio
    async def test_value_error_becomes_tool_error(self, tool_fns, mock_ctx):
        """api raises ValueError → wrapper raises ToolError."""
        with patch(
            "multiomics_explorer.api.functions.list_metabolite_assays",
            side_effect=ValueError("search_text must not be empty if provided."),
        ):
            with pytest.raises(ToolError, match="search_text must not be empty"):
                await tool_fns["list_metabolite_assays"](mock_ctx, search_text="")
        mock_ctx.warning.assert_awaited()

    @pytest.mark.asyncio
    async def test_rankable_bool_param(self, tool_fns, mock_ctx):
        """Tool accepts Python True/False for rankable; api receives same."""
        with patch(
            "multiomics_explorer.api.functions.list_metabolite_assays",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["list_metabolite_assays"](
                mock_ctx, rankable=True,
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("rankable") is True

        # rankable=False also forwarded
        with patch(
            "multiomics_explorer.api.functions.list_metabolite_assays",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["list_metabolite_assays"](
                mock_ctx, rankable=False,
            )
        kwargs = mock_api.call_args.kwargs
        assert kwargs.get("rankable") is False

    @pytest.mark.asyncio
    async def test_structured_not_found(self, tool_fns, mock_ctx):
        """not_found in response is the structured Pydantic model
        with all 4 batch-input buckets (assay_ids, metabolite_ids,
        experiment_ids, publication_doi) — parent §11 Conv B / §13.6."""
        api_return = {
            **self._SAMPLE_API_RETURN,
            "not_found": {
                "assay_ids": ["nonexistent_assay_id"],
                "metabolite_ids": ["kegg.compound:C99999"],
                "experiment_ids": ["bogus_exp"],
                "publication_doi": ["10.x/bogus"],
            },
        }
        with patch(
            "multiomics_explorer.api.functions.list_metabolite_assays",
            return_value=api_return,
        ):
            result = await tool_fns["list_metabolite_assays"](mock_ctx)
        assert result.not_found.assay_ids == ["nonexistent_assay_id"]
        assert result.not_found.metabolite_ids == ["kegg.compound:C99999"]
        assert result.not_found.experiment_ids == ["bogus_exp"]
        assert result.not_found.publication_doi == ["10.x/bogus"]


# ---------------------------------------------------------------------------
# Phase 5 metabolites-by-assay slice — 3 tools
# Tool 1: metabolites_by_quantifies_assay (numeric drill-down)
# Tool 2: metabolites_by_flags_assay (boolean drill-down)
# Tool 3: assays_by_metabolite (polymorphic reverse-lookup)
# ---------------------------------------------------------------------------
class TestMetabolitesByQuantifiesAssayWrapper:
    """MCP wrapper tests — calls api.metabolites_by_quantifies_assay (slice spec §4)."""

    _SAMPLE_API_RETURN = {
        "results": [],
        "total_matching": 64,
        "by_detection_status": [
            {"detection_status": "not_detected", "count": 48},
            {"detection_status": "detected", "count": 16},
        ],
        "by_metric_bucket": [{"bucket": "low", "count": 32}],
        "by_assay": [{"assay_id": "a1", "count": 64}],
        "by_compartment": [{"compartment": "whole_cell", "count": 64}],
        "by_organism": [{"organism_name": "Prochlorococcus MIT9313", "count": 64}],
        "by_metric": [],
        "excluded_assays": [],
        "warnings": [],
        "not_found": {
            "assay_ids": [],
            "metabolite_ids": [],
            "experiment_ids": [],
            "publication_doi": [],
        },
        "returned": 0,
        "truncated": True,
        "offset": 0,
    }

    def test_registered(self, tool_fns):
        assert "metabolites_by_quantifies_assay" in tool_fns

    @pytest.mark.asyncio
    async def test_empty_assay_ids_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_quantifies_assay",
            side_effect=ValueError("assay_ids must not be empty"),
        ):
            with pytest.raises(ToolError, match="assay_ids"):
                await tool_fns["metabolites_by_quantifies_assay"](
                    mock_ctx, assay_ids=[])

    @pytest.mark.asyncio
    async def test_response_model_validates_typical_envelope(
            self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_quantifies_assay",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["metabolites_by_quantifies_assay"](
                mock_ctx, assay_ids=["a1"], summary=True)
        assert result.total_matching == 64
        assert len(result.by_detection_status) == 2
        assert result.by_detection_status[0].detection_status == "not_detected"
        assert result.results == []


class TestMetabolitesByFlagsAssayWrapper:
    """MCP wrapper tests — calls api.metabolites_by_flags_assay (slice spec §5)."""

    _SAMPLE_API_RETURN = {
        "results": [],
        "total_matching": 93,
        "by_value": [
            {"flag_value": False, "count": 58},
            {"flag_value": True, "count": 35},
        ],
        "by_assay": [{"assay_id": "a1", "count": 93}],
        "by_compartment": [{"compartment": "whole_cell", "count": 93}],
        "by_organism": [{"organism_name": "Prochlorococcus MIT9301", "count": 93}],
        "by_metric": [],
        "excluded_assays": [],
        "warnings": [],
        "not_found": {
            "assay_ids": [],
            "metabolite_ids": [],
            "experiment_ids": [],
            "publication_doi": [],
        },
        "returned": 0,
        "truncated": True,
        "offset": 0,
    }

    def test_registered(self, tool_fns):
        assert "metabolites_by_flags_assay" in tool_fns

    @pytest.mark.asyncio
    async def test_empty_assay_ids_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_flags_assay",
            side_effect=ValueError("assay_ids must not be empty"),
        ):
            with pytest.raises(ToolError, match="assay_ids"):
                await tool_fns["metabolites_by_flags_assay"](
                    mock_ctx, assay_ids=[])

    @pytest.mark.asyncio
    async def test_response_model_validates_typical_envelope(
            self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.metabolites_by_flags_assay",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["metabolites_by_flags_assay"](
                mock_ctx, assay_ids=["a1"], summary=True)
        assert result.total_matching == 93
        assert len(result.by_value) == 2
        assert result.results == []


class TestAssaysByMetaboliteWrapper:
    """MCP wrapper tests — calls api.assays_by_metabolite (slice spec §6)."""

    _SAMPLE_API_RETURN = {
        "results": [],
        "total_matching": 20,
        "by_evidence_kind": [
            {"evidence_kind": "quantifies", "count": 18},
            {"evidence_kind": "flags", "count": 2},
        ],
        "by_organism": [{"organism_name": "Prochlorococcus MIT9313", "count": 18}],
        "by_compartment": [{"compartment": "whole_cell", "count": 20}],
        "by_assay": [{"assay_id": "a1", "count": 18}],
        "by_detection_status": [{"detection_status": "detected", "count": 12}],
        "by_flag_value": [{"flag_value": True, "count": 2}],
        "metabolites_with_evidence": ["kegg.compound:C00074"],
        "metabolites_without_evidence": [],
        "metabolites_matched": 1,
        "not_found": [],
        "not_matched": [],
        "returned": 0,
        "truncated": True,
        "offset": 0,
    }

    def test_registered(self, tool_fns):
        assert "assays_by_metabolite" in tool_fns

    @pytest.mark.asyncio
    async def test_empty_metabolite_ids_raises_tool_error(
            self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.assays_by_metabolite",
            side_effect=ValueError("metabolite_ids must not be empty"),
        ):
            with pytest.raises(ToolError, match="metabolite_ids"):
                await tool_fns["assays_by_metabolite"](
                    mock_ctx, metabolite_ids=[])

    @pytest.mark.asyncio
    async def test_response_model_validates_typical_envelope(
            self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.assays_by_metabolite",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["assays_by_metabolite"](
                mock_ctx, metabolite_ids=["kegg.compound:C00074"], summary=True)
        assert result.total_matching == 20
        # Flat not_found per parent §13.6 (single-batch reverse-lookup)
        assert isinstance(result.not_found, list)
        assert result.metabolites_matched == 1


# ---------------------------------------------------------------------------
# gene_aa_sequence
# ---------------------------------------------------------------------------
class TestGeneAaSequenceWrapper:
    _SAMPLE_API_RETURN = {
        "total_matching": 2,
        "returned": 2,
        "truncated": False,
        "by_organism": [{"organism_name": "Alteromonas macleodii HOT1A3", "count": 2}],
        "sequence_length_stats": {
            "count": 2, "min": 178, "q1": 178.0, "median": 178.0,
            "q3": 487.0, "max": 487, "mean": 332.5,
        },
        "not_found": [],
        "not_matched": [],
        "fasta": "",
        "results": [
            {"locus_tag": "ACZ81_08855", "organism_name": "Alteromonas macleodii HOT1A3",
             "gene_name": None, "product": "hypothetical protein",
             "protein_id": "WP_001", "sequence_length": 178, "sequence": "M" * 178},
            {"locus_tag": "ACZ81_08860", "organism_name": "Alteromonas macleodii HOT1A3",
             "gene_name": "dnaN", "product": "DNA polymerase III subunit beta",
             "protein_id": "WP_002", "sequence_length": 487, "sequence": "M" * 487},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_aa_sequence",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["gene_aa_sequence"](
                mock_ctx, locus_tags=["ACZ81_08855", "ACZ81_08860"],
            )
        assert result.total_matching == 2
        assert result.returned == 2
        assert result.truncated is False
        assert len(result.results) == 2
        r = result.results[0]
        assert r.locus_tag == "ACZ81_08855"
        assert r.sequence_length == 178

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        data = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 0,
            "returned": 0,
            "by_organism": [],
            "not_found": ["NOTAREAL"],
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_aa_sequence",
            return_value=data,
        ):
            result = await tool_fns["gene_aa_sequence"](
                mock_ctx, locus_tags=["NOTAREAL"],
            )
        assert result.results == []
        assert result.returned == 0
        assert "NOTAREAL" in result.not_found

    @pytest.mark.asyncio
    async def test_zero_match_none_stats_no_crash(self, tool_fns, mock_ctx):
        """Zero-match all-None sequence_length_stats must validate (nullable fields),
        not raise ToolError. Regression guard for the empty-batch BLOCKER."""
        data = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 0, "returned": 0, "by_organism": [],
            "sequence_length_stats": {
                "count": 0, "min": None, "q1": None, "median": None,
                "q3": None, "max": None, "mean": None,
            },
            "not_found": ["NOTAREAL"], "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_aa_sequence",
            return_value=data,
        ):
            result = await tool_fns["gene_aa_sequence"](
                mock_ctx, locus_tags=["NOTAREAL"],
            )
        assert result.sequence_length_stats.count == 0
        assert result.sequence_length_stats.min is None
        assert result.sequence_length_stats.median is None
        assert result.results == []

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_aa_sequence",
            return_value={**self._SAMPLE_API_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["gene_aa_sequence"](
                mock_ctx,
                locus_tags=["ACZ81_08860"],
                fasta=True,
                summary=False,
                limit=10,
                offset=5,
            )
        mock_api.assert_called_once()
        call = mock_api.call_args
        assert call.args[0] == ["ACZ81_08860"]
        assert call.kwargs["fasta"] is True
        assert call.kwargs["summary"] is False
        assert call.kwargs["limit"] == 10
        assert call.kwargs["offset"] == 5

    @pytest.mark.asyncio
    async def test_fasta_blob_surfaced(self, tool_fns, mock_ctx):
        data = {
            **self._SAMPLE_API_RETURN,
            "fasta": ">ACZ81_08860 Alteromonas macleodii HOT1A3|WP_002|DNA polymerase III subunit beta\nMMM",
            "results": [
                {**self._SAMPLE_API_RETURN["results"][0], "sequence": None},
                {**self._SAMPLE_API_RETURN["results"][1], "sequence": None},
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_aa_sequence",
            return_value=data,
        ):
            result = await tool_fns["gene_aa_sequence"](
                mock_ctx, locus_tags=["ACZ81_08855", "ACZ81_08860"], fasta=True,
            )
        assert result.fasta.startswith(">ACZ81_08860")
        for r in result.results:
            assert r.sequence is None

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        data = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 10,
            "returned": 2,
            "truncated": True,
        }
        with patch(
            "multiomics_explorer.api.functions.gene_aa_sequence",
            return_value=data,
        ):
            result = await tool_fns["gene_aa_sequence"](
                mock_ctx, locus_tags=["ACZ81_08860"],
            )
        assert result.total_matching == 10
        assert result.returned == 2
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_aa_sequence",
            side_effect=ValueError("locus_tags must not be empty"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["gene_aa_sequence"](mock_ctx, locus_tags=[])


# ---------------------------------------------------------------------------
# gene_neighbors
# ---------------------------------------------------------------------------
class TestGeneNeighborsWrapper:
    _SAMPLE_API_RETURN = {
        "total_matching": 2,
        "returned": 2,
        "truncated": False,
        "anchors": [
            {"locus_tag": "ACZ81_08860", "organism_name": "Alteromonas macleodii HOT1A3",
             "contig": "contig1", "start": 1000, "end": 1500, "strand": "+",
             "product": "DNA polymerase III subunit beta",
             "neighbors_returned": 2, "dropped_null_strand": 0},
        ],
        "by_organism": [{"organism_name": "Alteromonas macleodii HOT1A3", "count": 2}],
        "not_found": [],
        "not_matched": [],
        "warnings": [],
        "results": [
            {"anchor_locus_tag": "ACZ81_08860", "neighbor_locus_tag": "ACZ81_08850",
             "rank_offset": -1, "bp_gap": 10, "strand": "+", "same_strand": True,
             "product": "hypothetical protein", "gene_name": None, "gene_category": "unknown"},
            {"anchor_locus_tag": "ACZ81_08860", "neighbor_locus_tag": "ACZ81_08870",
             "rank_offset": 1, "bp_gap": 335, "strand": "-", "same_strand": False,
             "product": "hypothetical protein", "gene_name": None, "gene_category": "unknown"},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_neighbors",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["gene_neighbors"](
                mock_ctx, locus_tags=["ACZ81_08860"],
            )
        assert result.total_matching == 2
        assert result.returned == 2
        assert result.truncated is False
        assert len(result.results) == 2
        r = result.results[0]
        assert r.anchor_locus_tag == "ACZ81_08860"
        assert r.neighbor_locus_tag == "ACZ81_08850"
        assert r.rank_offset == -1
        assert r.bp_gap == 10
        assert r.same_strand is True
        assert len(result.anchors) == 1
        assert result.anchors[0].locus_tag == "ACZ81_08860"

    @pytest.mark.asyncio
    async def test_empty_results(self, tool_fns, mock_ctx):
        data = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 0,
            "returned": 0,
            "anchors": [],
            "by_organism": [],
            "not_found": ["NOTAREAL"],
            "results": [],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_neighbors",
            return_value=data,
        ):
            result = await tool_fns["gene_neighbors"](
                mock_ctx, locus_tags=["NOTAREAL"],
            )
        assert result.results == []
        assert result.returned == 0
        assert "NOTAREAL" in result.not_found

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_neighbors",
            return_value={**self._SAMPLE_API_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["gene_neighbors"](
                mock_ctx,
                locus_tags=["ACZ81_08860"],
                window=3,
                max_bp_distance=400,
                same_strand=True,
                summary=False,
                limit=10,
            )
        mock_api.assert_called_once()
        call = mock_api.call_args
        assert call.args[0] == ["ACZ81_08860"]
        assert call.kwargs["window"] == 3
        assert call.kwargs["max_bp_distance"] == 400
        assert call.kwargs["same_strand"] is True
        assert call.kwargs["summary"] is False
        assert call.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_not_matched_and_warnings_surfaced(self, tool_fns, mock_ctx):
        data = {
            **self._SAMPLE_API_RETURN,
            "not_matched": ["SYNW1755"],
            "warnings": ["same_strand requested but anchor ACZ81_08865 has null strand; returned unfiltered"],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_neighbors",
            return_value=data,
        ):
            result = await tool_fns["gene_neighbors"](
                mock_ctx, locus_tags=["ACZ81_08860", "SYNW1755"], same_strand=True,
            )
        assert "SYNW1755" in result.not_matched
        assert len(result.warnings) == 1

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, tool_fns, mock_ctx):
        data = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 10,
            "returned": 2,
            "truncated": True,
        }
        with patch(
            "multiomics_explorer.api.functions.gene_neighbors",
            return_value=data,
        ):
            result = await tool_fns["gene_neighbors"](
                mock_ctx, locus_tags=["ACZ81_08860"],
            )
        assert result.total_matching == 10
        assert result.returned == 2
        assert result.truncated is True

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_neighbors",
            side_effect=ValueError("locus_tags must not be empty"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["gene_neighbors"](mock_ctx, locus_tags=[])


class TestOntologyLiteralAcceptsPsortbSignalp:
    """The closed Literal[...] enums on the 5 ontology wrappers must accept
    'subcellular_localization' and 'signal_peptide_type'. Mirrors
    TestOntologyLiteralAcceptsTcdbCazy."""

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

    def test_genes_by_ontology_literal_includes_new_keys(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "genes_by_ontology")
        assert "'subcellular_localization'" in hint_str
        assert "'signal_peptide_type'" in hint_str

    def test_gene_ontology_terms_literal_includes_new_keys(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "gene_ontology_terms")
        assert "'subcellular_localization'" in hint_str
        assert "'signal_peptide_type'" in hint_str

    def test_ontology_landscape_literal_includes_new_keys(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "ontology_landscape")
        assert "'subcellular_localization'" in hint_str
        assert "'signal_peptide_type'" in hint_str

    def test_pathway_enrichment_literal_includes_new_keys(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "pathway_enrichment")
        assert "'subcellular_localization'" in hint_str
        assert "'signal_peptide_type'" in hint_str

    def test_cluster_enrichment_literal_includes_new_keys(self, tool_fns):
        hint_str = self._ontology_hint_str(tool_fns, "cluster_enrichment")
        assert "'subcellular_localization'" in hint_str
        assert "'signal_peptide_type'" in hint_str

    def test_search_ontology_description_mentions_new_keys(self, tool_fns):
        import typing
        fn = tool_fns["search_ontology"]
        hints = typing.get_type_hints(fn, include_extras=True)
        ontology_hint = hints.get("ontology")
        assert ontology_hint is not None
        descriptions = [
            getattr(meta, "description", None) for meta in
            getattr(ontology_hint, "__metadata__", ())
        ]
        joined = " ".join(d for d in descriptions if d)
        assert "subcellular_localization" in joined
        assert "signal_peptide_type" in joined


class TestEdgePropFieldsOnRowModels:
    """The GenesByOntologyResult and OntologyTermRow Pydantic classes
    must carry the 4 optional edge-prop fields (default=None, sparse)."""

    def test_genes_by_ontology_result_has_edge_prop_fields(self):
        from multiomics_explorer.mcp_server.tools import register_tools
        import inspect
        src = inspect.getsource(register_tools)
        idx = src.index("class GenesByOntologyResult(SparseRow):")
        end_idx = src.index("class OntologyCategoryBreakdown(BaseModel):", idx)
        section = src[idx:end_idx]
        assert "localization_score:" in section, (
            "localization_score must be a field on GenesByOntologyResult"
        )
        assert "signal_peptide_probability:" in section
        assert "signal_peptide_cleavage_site:" in section
        assert "signal_peptide_cleavage_probability:" in section

    def test_ontology_term_row_has_edge_prop_fields(self):
        from multiomics_explorer.mcp_server.tools import register_tools
        import inspect
        src = inspect.getsource(register_tools)
        idx = src.index("class OntologyTermRow(SparseRow):")
        end_idx = src.index("class OntologyTypeBreakdown(BaseModel):", idx)
        section = src[idx:end_idx]
        assert "localization_score:" in section
        assert "signal_peptide_probability:" in section
        assert "signal_peptide_cleavage_site:" in section
        assert "signal_peptide_cleavage_probability:" in section


class TestExpectedToolsUnchangedForPsortbSignalp:
    """Adding subcellular_localization/signal_peptide_type as ontology
    dimensions does NOT add new tool entries."""

    def test_no_new_tools_added(self, tool_fns):
        assert "subcellular_localization" not in tool_fns
        assert "signal_peptide_type" not in tool_fns
        assert "psortb" not in tool_fns
        assert "signalp" not in tool_fns

    def test_expected_tools_size_unchanged_at_40(self):
        # No new tool — only ontology surface refresh.
        # Bumped 39 → 40 by kg_release_info (KG compatibility check tool).
        # Bumped 40 → 41 by discussed_by_publication (literature-index forward
        # tool; its 3 sibling extensions add fields only, no new tool).
        # Bumped 41 → 42 by ontology_term_details (annotation-trust surface
        # PR 3b — term-side drill-down, legitimate new MCP tool).
        assert len(EXPECTED_TOOLS) == 42, (
            f"EXPECTED_TOOLS unexpectedly has {len(EXPECTED_TOOLS)} entries; "
            "psortb/signalp adds NO new tools (Mode-B ontology surface refresh); "
            "kg_release_info legitimately adds one."
        )


class TestKGReleaseInfoTool:
    """Layer-3 wrapper for kg_release_info — Pydantic shape validation."""

    def _ok_report(self):
        return {
            "verdict": "ok",
            "explorer_version": "0.1.0a1",
            "kg": {
                "version": "0.1.0",
                "built_at": "2026-06-02T00:00:00Z",
                "mcp_min_version": "0.0.1",
                "git_sha_short": "deadbee",
                "git_branch": "main",
                "gene_count": 100,
                "experiment_count": 5,
                "paper_count": 3,
                "organism_count": 2,
                "expression_edge_count": 500,
                "release_notes_url": None,
            },
            "asserts": [
                {"name": "version_compat", "kind": "version_compat", "passed": True, "detail": None},
            ],
            "summary": "OK: explorer 0.1.0a1 satisfies KG mcp_min_version 0.0.1; 1/1 asserts pass.",
        }

    def test_response_validates_ok_shape(self):
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        response = KGReleaseInfoResponse(**self._ok_report())
        assert response.verdict == "ok"
        assert response.kg.version == "0.1.0"
        assert len(response.asserts) == 1

    def test_response_validates_warn_shape(self):
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        report = self._ok_report()
        report["verdict"] = "warn"
        report["asserts"] = [
            {"name": "version_compat", "kind": "version_compat", "passed": False,
             "detail": "Explorer 0.1.0a1 < KG mcp_min_version 99.99.99 (PEP 440)."},
        ]
        response = KGReleaseInfoResponse(**report)
        assert response.verdict == "warn"
        assert response.asserts[0].passed is False

    def test_response_validates_unknown_shape(self):
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        unknown = {
            "verdict": "unknown",
            "explorer_version": "0.1.0a1",
            "kg": {},  # all defaults to None
            "asserts": [],
            "summary": "UNKNOWN: Schema_info node not found.",
        }
        response = KGReleaseInfoResponse(**unknown)
        assert response.verdict == "unknown"
        assert response.kg.version is None
        assert response.asserts == []

    def test_response_rejects_unknown_verdict(self):
        from pydantic import ValidationError
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        bad = self._ok_report()
        bad["verdict"] = "bogus"
        with pytest.raises(ValidationError):
            KGReleaseInfoResponse(**bad)

    def test_kg_identity_carries_change_list_fields(self):
        """KGIdentity accepts the optional preflight change-list strings."""
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        report = self._ok_report()
        report["kg"]["release_highlights"] = "- Publication discusses-edges"
        report["kg"]["breaking_changes"] = "- annotation_quality redefined"
        response = KGReleaseInfoResponse(**report)
        assert response.kg.release_highlights == "- Publication discusses-edges"
        assert response.kg.breaking_changes == "- annotation_quality redefined"

    def test_kg_identity_change_list_fields_default_none(self):
        """Absent on dev builds -> default None, no validation error."""
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        response = KGReleaseInfoResponse(**self._ok_report())
        assert response.kg.release_highlights is None
        assert response.kg.breaking_changes is None

    def test_kg_identity_carries_deployment_role(self):
        """KGIdentity echoes the KG's self-declared deployment_role."""
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        report = self._ok_report()
        report["kg"]["deployment_role"] = "local-dev"
        response = KGReleaseInfoResponse(**report)
        assert response.kg.deployment_role == "local-dev"

    def test_kg_identity_deployment_role_defaults_none(self):
        """Absent (legacy KG) -> default None, rendered as unknown, no error."""
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        response = KGReleaseInfoResponse(**self._ok_report())
        assert response.kg.deployment_role is None


# ===========================================================================
# Publication "discusses" literature-index surface
# (docs/tool-specs/publication-discusses-surface.md)
# ===========================================================================


class TestDiscussedByPublicationWrapper:
    """New tool wrapper: discussed_by_publication. Polymorphic rows (gene +
    kegg_pathway via union padding). Pydantic response model
    DiscussedByPublicationResponse."""

    _SAMPLE_API_RETURN = {
        "total_entries": 4,
        "total_matching": 4,
        "returned": 2,
        "offset": 0,
        "truncated": True,
        "by_entity_kind": [{"entity_kind": "gene", "count": 3},
                           {"entity_kind": "kegg_pathway", "count": 1}],
        "by_prominence": [{"prominence": "central", "count": 2},
                          {"prominence": "peripheral", "count": 2}],
        "top_kegg_pathways": [
            {"id": "kegg.pathway:ko00710", "name": "Carbon fixation", "n": 1}],
        "top_publications": [
            {"doi": "10.1038/ismej.2016.70", "title": "Paper A", "n": 4}],
        "not_found": [],
        "not_matched": [],
        "results": [
            {"doi": "10.1038/ismej.2016.70", "entity_kind": "gene",
             "entity_id": "PMT1030", "entity_name": "psbA",
             "organism": "Prochlorococcus MED4", "prominence": "central"},
            {"doi": "10.1038/ismej.2016.70", "entity_kind": "kegg_pathway",
             "entity_id": "kegg.pathway:ko00710", "entity_name": "Carbon fixation",
             "organism": None, "prominence": "peripheral"},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.discussed_by_publication",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["discussed_by_publication"](
                mock_ctx, publication_dois=["10.1038/ismej.2016.70"],
            )
        assert result.total_entries == 4
        assert result.total_matching == 4
        assert result.returned == 2
        assert result.truncated is True
        assert len(result.results) == 2
        r = result.results[0]
        assert r.doi == "10.1038/ismej.2016.70"
        assert r.entity_kind == "gene"
        assert r.entity_id == "PMT1030"
        assert r.prominence == "central"

    @pytest.mark.asyncio
    async def test_pathway_row_organism_none(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.discussed_by_publication",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["discussed_by_publication"](
                mock_ctx, publication_dois=["10.1038/ismej.2016.70"],
            )
        pathway = [r for r in result.results if r.entity_kind == "kegg_pathway"][0]
        assert pathway.organism is None

    @pytest.mark.asyncio
    async def test_envelope_rollups(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.discussed_by_publication",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["discussed_by_publication"](
                mock_ctx, publication_dois=["10.1038/ismej.2016.70"],
            )
        assert result.by_entity_kind is not None
        assert result.by_prominence is not None
        assert result.top_kegg_pathways is not None
        assert result.top_publications is not None

    @pytest.mark.asyncio
    async def test_not_found_and_not_matched(self, tool_fns, mock_ctx):
        data = {**self._SAMPLE_API_RETURN,
                "not_found": ["10.0/missing"], "not_matched": ["10.1/empty"]}
        with patch(
            "multiomics_explorer.api.functions.discussed_by_publication",
            return_value=data,
        ):
            result = await tool_fns["discussed_by_publication"](
                mock_ctx, publication_dois=["10.1038/ismej.2016.70"],
            )
        assert "10.0/missing" in result.not_found
        assert "10.1/empty" in result.not_matched

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.discussed_by_publication",
            return_value={**self._SAMPLE_API_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["discussed_by_publication"](
                mock_ctx,
                publication_dois=["10.1038/ismej.2016.70"],
                entity_kind="gene",
                prominence="central",
                summary=False,
                verbose=True,
                limit=10,
                offset=5,
            )
        mock_api.assert_called_once()
        call = mock_api.call_args
        assert call.kwargs["entity_kind"] == "gene"
        assert call.kwargs["prominence"] == "central"
        assert call.kwargs["verbose"] is True
        assert call.kwargs["limit"] == 10
        assert call.kwargs["offset"] == 5

    @pytest.mark.asyncio
    async def test_verbose_row_carries_evidence(self, tool_fns, mock_ctx):
        data = {
            **self._SAMPLE_API_RETURN,
            "results": [
                {"doi": "10.1038/ismej.2016.70", "entity_kind": "gene",
                 "entity_id": "PMT1030", "entity_name": "psbA",
                 "organism": "Prochlorococcus MED4", "prominence": "central",
                 "evidence": "psbA is the model gene"},
            ],
            "returned": 1,
        }
        with patch(
            "multiomics_explorer.api.functions.discussed_by_publication",
            return_value=data,
        ):
            result = await tool_fns["discussed_by_publication"](
                mock_ctx, publication_dois=["10.1038/ismej.2016.70"], verbose=True,
            )
        assert result.results[0].evidence == "psbA is the model gene"

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.discussed_by_publication",
            side_effect=ValueError("publication_dois must not be empty"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["discussed_by_publication"](
                    mock_ctx, publication_dois=[],
                )

    @pytest.mark.asyncio
    async def test_unexpected_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.discussed_by_publication",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["discussed_by_publication"](
                    mock_ctx, publication_dois=["10.1/x"],
                )


class TestDiscussedPublicationRefModel:
    """Shared submodel DiscussedPublicationRef (doi, prominence, evidence),
    reused by gene_overview + search_ontology verbose discussed lists."""

    def test_model_importable_and_shape(self):
        from multiomics_explorer.mcp_server.tools import DiscussedPublicationRef
        ref = DiscussedPublicationRef(
            doi="10.1038/ismej.2016.70", prominence="central",
            evidence="psbA is the model gene",
        )
        assert ref.doi == "10.1038/ismej.2016.70"
        assert ref.prominence == "central"
        assert ref.evidence == "psbA is the model gene"


class TestGeneOverviewWrapperDiscusses:
    """Extension 1: gene_overview response gains per-row
    discussed_in_publication_count + discussed_in_publications, envelope
    has_discussed + top_discussing_publications."""

    def _api_return(self, verbose=False):
        row = {
            "locus_tag": "PMT1030", "gene_name": "psbA", "product": "PSII",
            "gene_category": "Photosynthesis", "annotation_quality": 3,
            "organism_name": "Prochlorococcus MED4",
            "annotation_types": [], "annotation_state": "informative_multi",
            "informative_annotation_types": [],
            "expression_edge_count": 0,
            "significant_up_count": 0, "significant_down_count": 0,
            "closest_ortholog_group_size": 1, "closest_ortholog_genera": [],
            "cluster_membership_count": 0, "cluster_types": [],
            "derived_metric_count": 0, "derived_metric_value_kinds": [],
            "discussed_in_publication_count": 2,
        }
        if verbose:
            row["discussed_in_publications"] = [
                {"doi": "10.1038/ismej.2016.70", "prominence": "central",
                 "evidence": "psbA is the model gene"},
            ]
        return {
            "total_matching": 1,
            "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
            "by_category": [], "by_annotation_type": [], "by_annotation_state": [],
            "has_expression": 0, "has_significant_expression": 0,
            "has_orthologs": 0, "has_clusters": 0, "has_derived_metrics": 0,
            "has_chemistry": 0,
            "has_discussed": 1,
            "top_discussing_publications": [
                {"doi": "10.1038/ismej.2016.70", "title": "Paper A", "n_genes": 1}],
            "returned": 1, "offset": 0, "truncated": False,
            "not_found": [],
            "results": [row],
        }

    @pytest.mark.asyncio
    async def test_compact_row_has_discussed_count(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=self._api_return(),
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMT1030"],
            )
        assert result.results[0].discussed_in_publication_count == 2

    @pytest.mark.asyncio
    async def test_envelope_has_discussed(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=self._api_return(),
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMT1030"],
            )
        assert result.has_discussed == 1

    @pytest.mark.asyncio
    async def test_envelope_top_discussing_publications(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=self._api_return(),
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMT1030"],
            )
        assert result.top_discussing_publications[0].doi == "10.1038/ismej.2016.70"
        assert result.top_discussing_publications[0].n_genes == 1

    @pytest.mark.asyncio
    async def test_verbose_row_discussed_publications(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=self._api_return(verbose=True),
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMT1030"], verbose=True,
            )
        refs = result.results[0].discussed_in_publications
        assert refs[0].doi == "10.1038/ismej.2016.70"
        assert refs[0].prominence == "central"
        assert refs[0].evidence == "psbA is the model gene"


class TestSearchOntologyWrapperDiscusses:
    """Extension 2: search_ontology wrapper gains a verbose param + per-KEGG-row
    discussed_by_n_publications + discussed_in_publications."""

    def _api_return(self, verbose=False):
        row = {
            "id": "kegg.pathway:ko00710", "name": "Carbon fixation",
            "score": 5.0, "level": 2, "is_informative": True,
            "discussed_by_n_publications": 19,
        }
        if verbose:
            row["discussed_in_publications"] = [
                {"doi": "10.1038/ismej.2016.70", "prominence": "central",
                 "evidence": "carbon fixation is discussed"},
            ]
        return {
            "total_entries": 1, "total_matching": 1,
            "score_max": 5.0, "score_median": 5.0,
            "returned": 1, "truncated": False, "results": [row],
        }

    @pytest.mark.asyncio
    async def test_wrapper_accepts_verbose_param(self, tool_fns, mock_ctx):
        """search_ontology wrapper must accept the new verbose kwarg and forward
        it to the api function."""
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=self._api_return(),
        ) as mock_api:
            await tool_fns["search_ontology"](
                mock_ctx, search_text="carbon", ontology="kegg", verbose=True,
            )
        assert mock_api.call_args.kwargs.get("verbose") is True

    @pytest.mark.asyncio
    async def test_kegg_row_has_discussed_count(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=self._api_return(),
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="carbon", ontology="kegg",
            )
        assert result.results[0].discussed_by_n_publications == 19

    @pytest.mark.asyncio
    async def test_kegg_verbose_row_has_discussed_list(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=self._api_return(verbose=True),
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="carbon", ontology="kegg", verbose=True,
            )
        refs = result.results[0].discussed_in_publications
        assert refs[0].doi == "10.1038/ismej.2016.70"
        assert refs[0].evidence == "carbon fixation is discussed"


class TestListPublicationsWrapperDiscusses:
    """Extension 3: list_publications response gains per-row discussed_gene_count
    + discussed_pathway_count and envelope by_discusses_coverage."""

    def _api_return(self):
        return {
            "total_entries": 1, "total_matching": 1,
            "by_organism": [], "by_treatment_type": [], "by_background_factors": [],
            "by_omics_type": [], "by_cluster_type": [], "by_value_kind": [],
            "by_metric_type": [], "by_compartment": [],
            "by_discusses_coverage": {"has_discusses": 1, "no_discusses": 0},
            "returned": 1, "offset": 0, "truncated": False, "not_found": [],
            "results": [
                {"doi": "10.1038/ismej.2016.70", "title": "Paper A", "authors": ["A"],
                 "year": 2016, "journal": "ISMEJ", "study_type": "S",
                 "organisms": ["MED4"], "experiment_count": 1,
                 "treatment_types": ["coculture"], "background_factors": [],
                 "omics_types": ["RNASEQ"],
                 "clustering_analysis_count": 0, "cluster_types": [],
                 "growth_phases": [],
                 "derived_metric_count": 0, "derived_metric_value_kinds": [],
                 "compartments": [],
                 "metabolite_count": 0, "metabolite_assay_count": 0,
                 "metabolite_compartments": [],
                 "discussed_gene_count": 25, "discussed_pathway_count": 4},
            ],
        }

    @pytest.mark.asyncio
    async def test_row_has_discussed_counts(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value=self._api_return(),
        ):
            result = await tool_fns["list_publications"](mock_ctx)
        r = result.results[0]
        assert r.discussed_gene_count == 25
        assert r.discussed_pathway_count == 4

    @pytest.mark.asyncio
    async def test_envelope_by_discusses_coverage(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value=self._api_return(),
        ):
            result = await tool_fns["list_publications"](mock_ctx)
        assert result.by_discusses_coverage.has_discusses == 1
        assert result.by_discusses_coverage.no_discusses == 0


# ---------------------------------------------------------------------------
# Annotation-trust surface (PR 3a) — MCP wrapper layer
# ---------------------------------------------------------------------------


def _hint_str(tool_fns, tool_name, param):
    import typing
    hints = typing.get_type_hints(tool_fns[tool_name], include_extras=True)
    hint = hints.get(param)
    assert hint is not None, f"{tool_name} has no {param} parameter"
    return str(hint)


def _field_descriptions(tool_fns, tool_name, param):
    import typing
    hints = typing.get_type_hints(tool_fns[tool_name], include_extras=True)
    hint = hints.get(param)
    assert hint is not None, f"{tool_name} has no {param} parameter"
    return [
        getattr(meta, "description", None)
        for meta in getattr(hint, "__metadata__", ())
    ]


_TRUST_TOOLS = [
    "genes_by_ontology", "gene_ontology_terms",
    "pathway_enrichment", "cluster_enrichment",
]

_ONTOLOGY_LITERAL_TOOLS = [
    "genes_by_ontology", "gene_ontology_terms", "ontology_landscape",
    "pathway_enrichment", "cluster_enrichment",
]


class TestOntologyLiteralAcceptsNewThree:
    """The closed Literal enums on the 5 ontology wrappers must accept
    'interpro', 'ncbifam' and 'merops'."""

    @pytest.mark.parametrize("tool_name", _ONTOLOGY_LITERAL_TOOLS)
    @pytest.mark.parametrize("key", ["interpro", "ncbifam", "merops"])
    def test_literal_includes_new_key(self, tool_fns, tool_name, key):
        assert f"'{key}'" in _hint_str(tool_fns, tool_name, "ontology")

    @pytest.mark.parametrize("tool_name", _ONTOLOGY_LITERAL_TOOLS)
    def test_literal_still_carries_the_existing_14(self, tool_fns, tool_name):
        hint_str = _hint_str(tool_fns, tool_name, "ontology")
        for key in ("go_bp", "kegg", "tcdb", "cazy",
                    "subcellular_localization", "signal_peptide_type"):
            assert f"'{key}'" in hint_str, key

    def test_search_ontology_description_mentions_new_keys(self, tool_fns):
        joined = " ".join(
            d for d in _field_descriptions(tool_fns, "search_ontology", "ontology")
            if d
        )
        assert "interpro" in joined
        assert "ncbifam" in joined
        assert "merops" in joined


class TestMultiOntologyParamShape:
    """`gene_ontology_terms` and `ontology_landscape` accept a list."""

    @pytest.mark.parametrize(
        "tool_name", ["gene_ontology_terms", "ontology_landscape"])
    def test_ontology_param_accepts_a_list(self, tool_fns, tool_name):
        hint_str = _hint_str(tool_fns, tool_name, "ontology")
        assert "list" in hint_str.lower()

    @pytest.mark.parametrize(
        "tool_name", ["genes_by_ontology", "pathway_enrichment",
                      "cluster_enrichment"])
    def test_single_ontology_tools_stay_single(self, tool_fns, tool_name):
        hint_str = _hint_str(tool_fns, tool_name, "ontology")
        assert "list[" not in hint_str


class TestTrustFilterParamsOnWrappers:
    """Every trust filter is exposed on the four gene-set tools; the two
    categorical facets also on ontology_landscape."""

    @pytest.mark.parametrize("tool_name", _TRUST_TOOLS)
    @pytest.mark.parametrize("param", [
        "sources", "evidence", "max_tier", "min_evidence_score",
        "call_class", "interpro_type",
    ])
    def test_param_present(self, tool_fns, tool_name, param):
        import inspect
        sig = inspect.signature(tool_fns[tool_name])
        assert param in sig.parameters, f"{tool_name}.{param}"

    @pytest.mark.parametrize("tool_name", _TRUST_TOOLS)
    @pytest.mark.parametrize("param", [
        "sources", "evidence", "max_tier", "min_evidence_score",
        "call_class", "interpro_type",
    ])
    def test_param_defaults_to_none(self, tool_fns, tool_name, param):
        import inspect
        sig = inspect.signature(tool_fns[tool_name])
        assert sig.parameters[param].default is None, f"{tool_name}.{param}"

    @pytest.mark.parametrize("param", ["call_class", "interpro_type"])
    def test_landscape_carries_the_categorical_facets(self, tool_fns, param):
        import inspect
        sig = inspect.signature(tool_fns["ontology_landscape"])
        assert param in sig.parameters

    def test_gene_ontology_terms_has_include_superseded(self, tool_fns):
        import inspect
        sig = inspect.signature(tool_fns["gene_ontology_terms"])
        assert sig.parameters["include_superseded"].default is False

    def test_search_ontology_has_interpro_type(self, tool_fns):
        import inspect
        sig = inspect.signature(tool_fns["search_ontology"])
        assert sig.parameters["interpro_type"].default is None

    @pytest.mark.parametrize("tool_name", _TRUST_TOOLS + ["ontology_landscape"])
    @pytest.mark.parametrize("param", ["sources", "evidence", "call_class",
                                       "interpro_type", "max_tier",
                                       "min_evidence_score"])
    def test_field_description_within_250_chars(self, tool_fns, tool_name, param):
        import inspect
        sig = inspect.signature(tool_fns[tool_name])
        if param not in sig.parameters:
            pytest.skip(f"{tool_name} does not expose {param}")
        for desc in _field_descriptions(tool_fns, tool_name, param):
            if desc is None:
                continue
            assert len(desc) <= 250, (
                f"{tool_name}.{param} Field description is {len(desc)} chars")

    @pytest.mark.parametrize("tool_name", _TRUST_TOOLS + ["ontology_landscape"])
    @pytest.mark.parametrize("param", ["sources", "evidence", "call_class",
                                       "interpro_type", "max_tier",
                                       "min_evidence_score"])
    def test_field_description_is_present(self, tool_fns, tool_name, param):
        import inspect
        sig = inspect.signature(tool_fns[tool_name])
        if param not in sig.parameters:
            pytest.skip(f"{tool_name} does not expose {param}")
        descs = [d for d in _field_descriptions(tool_fns, tool_name, param) if d]
        assert descs, f"{tool_name}.{param} has no Field description"


class TestInterproTypeLiteral:
    """`interpro_type` is a closed 8-value Literal — the InterPro entry
    types. Values come from ControlledVocabulary; the enum pins the shape."""

    def test_literal_has_eight_options(self, tool_fns):
        import re
        hint_str = _hint_str(tool_fns, "genes_by_ontology", "interpro_type")
        assert "Literal[" in hint_str
        literal_part = hint_str[hint_str.index("Literal["):]
        options = set(re.findall(r"'([A-Z_]+)'", literal_part))
        assert len(options) == 8, sorted(options)

    @pytest.mark.parametrize("value", [
        "FAMILY", "DOMAIN", "HOMOLOGOUS_SUPERFAMILY"])
    def test_literal_includes_the_verified_strata(self, tool_fns, value):
        assert f"'{value}'" in _hint_str(
            tool_fns, "genes_by_ontology", "interpro_type")


class TestInterproEnrichmentRequiresStratum:
    """Section 10 acceptance 5: interpro enrichment without a stratum raises."""

    @pytest.mark.asyncio
    async def test_pathway_enrichment_raises_without_interpro_type(
        self, tool_fns, mock_ctx
    ):
        with pytest.raises(ToolError):
            await tool_fns["pathway_enrichment"](
                mock_ctx, organism="MED4", experiment_ids=["EXP1"],
                ontology="interpro", level=0,
            )

    @pytest.mark.asyncio
    async def test_cluster_enrichment_raises_without_interpro_type(
        self, tool_fns, mock_ctx
    ):
        with pytest.raises(ToolError):
            await tool_fns["cluster_enrichment"](
                mock_ctx, analysis_id="A1", organism="MED4",
                ontology="interpro", level=0,
            )

    @pytest.mark.asyncio
    async def test_unsupported_axis_becomes_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            side_effect=ValueError("max_tier is not a trust axis of 'kegg'"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["genes_by_ontology"](
                    mock_ctx, ontology="kegg", organism="MED4", level=1,
                    max_tier=2,
                )


class TestTrustFieldsOnRowModels:
    """Row models carry the compact trust column and the verbose axes /
    native detail as optional sparse fields."""

    @staticmethod
    def _model_section(class_name, next_class_name):
        from multiomics_explorer.mcp_server.tools import register_tools
        import inspect
        src = inspect.getsource(register_tools)
        import re
        m = re.search(rf"class {class_name}\((BaseModel|SparseRow)\):", src)
        idx = m.start()
        end_idx = src.index(f"class {next_class_name}(BaseModel):", idx)
        return src[idx:end_idx]

    @pytest.mark.parametrize("field", [
        "evidence", "sources", "evidence_score", "tier",
        "call_class", "interpro_type",
    ])
    def test_genes_by_ontology_result_has_trust_fields(self, field):
        section = self._model_section(
            "GenesByOntologyResult", "OntologyCategoryBreakdown")
        assert f"{field}:" in section

    @pytest.mark.parametrize("field", [
        "evidence", "sources", "evidence_score", "tier",
        "call_class", "interpro_type",
    ])
    def test_ontology_term_row_has_trust_fields(self, field):
        section = self._model_section("OntologyTermRow", "OntologyTypeBreakdown")
        assert f"{field}:" in section

    @pytest.mark.parametrize("field", [
        "attachment_depth", "confidence_score", "pfam_support",
        "best_hit_kind", "libraries", "bit_score",
    ])
    def test_native_detail_fields_on_the_gene_term_row(self, field):
        section = self._model_section(
            "GenesByOntologyResult", "OntologyCategoryBreakdown")
        assert f"{field}:" in section


class TestTrustEnvelopeFieldsOnResponses:
    """Envelope keys are declared on the response models, not just passed
    through as dict keys."""

    @staticmethod
    def _response_src(class_name):
        from multiomics_explorer.mcp_server.tools import register_tools
        import inspect
        src = inspect.getsource(register_tools)
        idx = src.index(f"class {class_name}(BaseModel):")
        return src[idx:idx + 6000]

    @pytest.mark.parametrize("field", [
        "trust_axes", "by_evidence", "by_tier", "by_sources", "by_call_class",
        "evidence_score_stats", "filters_applied", "skipped_ontologies",
        "warnings",
    ])
    def test_genes_by_ontology_response_declares_envelope_field(self, field):
        assert f"{field}:" in self._response_src("GenesByOntologyResponse")

    @pytest.mark.parametrize("field", [
        "merops_classes", "ncbifam_family_count", "merops_evidence_score_max",
    ])
    def test_gene_overview_row_declares_the_new_columns(self, field):
        from multiomics_explorer.mcp_server.tools import register_tools
        import inspect
        src = inspect.getsource(register_tools)
        idx = src.index("class GeneOverviewResult(SparseRow):")
        assert f"{field}:" in src[idx:idx + 8000]


class TestGeneOverviewWrapperFamilyCounts:
    """Backlog 3.4: GeneOverviewResult declares tcdb_family_count /
    cazy_family_count (int, default 0); GeneOverviewResponse declares
    has_tcdb / has_cazy; the wrapper forwards the api values verbatim."""

    @staticmethod
    def _src(class_name):
        from multiomics_explorer.mcp_server.tools import register_tools
        import inspect
        src = inspect.getsource(register_tools)
        idx = src.index(f"class {class_name}(")
        return src[idx:idx + 8000]

    @pytest.mark.parametrize("field", ["tcdb_family_count", "cazy_family_count"])
    def test_row_declares_family_count_with_zero_default(self, field):
        import re as _re
        src = self._src("GeneOverviewResult")
        assert (
            _re.search(rf"{field}:\s*int\s*=\s*Field\(\s*0\b", src)
            or _re.search(rf"{field}:\s*int\s*=\s*0\b", src)
        ), field

    @pytest.mark.parametrize("field", ["has_tcdb", "has_cazy"])
    def test_response_declares_envelope_field(self, field):
        assert f"{field}:" in self._src("GeneOverviewResponse")

    def _api_return(self):
        row = {
            "locus_tag": "PMM0392", "gene_name": None, "product": "ABC transporter",
            "gene_category": "Transport", "annotation_quality": 3,
            "organism_name": "Prochlorococcus MED4",
            "annotation_types": [], "annotation_state": "informative_multi",
            "informative_annotation_types": [],
            "expression_edge_count": 0,
            "significant_up_count": 0, "significant_down_count": 0,
            "closest_ortholog_group_size": 1, "closest_ortholog_genera": [],
            "cluster_membership_count": 0, "cluster_types": [],
            "derived_metric_count": 0, "derived_metric_value_kinds": [],
            "discussed_in_publication_count": 0,
            "ncbifam_family_count": 0, "merops_classes": [],
            "tcdb_family_count": 7, "cazy_family_count": 4,
        }
        return {
            "total_matching": 1,
            "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
            "by_category": [], "by_annotation_type": [], "by_annotation_state": [],
            "has_expression": 0, "has_significant_expression": 0,
            "has_orthologs": 0, "has_clusters": 0, "has_derived_metrics": 0,
            "has_chemistry": 0, "has_discussed": 0,
            "top_discussing_publications": [],
            "has_ncbifam": 0, "by_merops_class": [],
            "has_tcdb": 1, "has_cazy": 1,
            "returned": 1, "offset": 0, "truncated": False,
            "not_found": [], "results": [row],
        }

    @pytest.mark.asyncio
    async def test_wrapper_forwards_family_counts(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=self._api_return(),
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMM0392"],
            )
        assert result.results[0].tcdb_family_count == 7
        assert result.results[0].cazy_family_count == 4
        assert result.has_tcdb == 1
        assert result.has_cazy == 1

    @pytest.mark.asyncio
    async def test_wrapper_defaults_family_counts_to_zero(self, tool_fns, mock_ctx):
        ret = self._api_return()
        for k in ("tcdb_family_count", "cazy_family_count"):
            del ret["results"][0][k]
        for k in ("has_tcdb", "has_cazy"):
            del ret[k]
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=ret,
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMM0392"],
            )
        assert result.results[0].tcdb_family_count == 0
        assert result.results[0].cazy_family_count == 0
        assert result.has_tcdb == 0
        assert result.has_cazy == 0


class TestListFilterValuesTrustTypes:
    """`filter_type` grows the trust / facet / config-derived enumerations."""

    NEW_FILTER_TYPES = [
        "evidence", "sources", "call_class", "interpro_type",
        "ncbifam_family_type", "merops_catalytic_type", "merops_family_class",
        "best_hit_kind", "pfam_support", "attachment_depth",
        "trust_axes", "link_kinds",
    ]

    @pytest.mark.parametrize("value", NEW_FILTER_TYPES)
    def test_literal_includes_new_filter_type(self, tool_fns, value):
        assert f"'{value}'" in _hint_str(
            tool_fns, "list_filter_values", "filter_type")

    def test_ontology_scope_param_present(self, tool_fns):
        import inspect
        sig = inspect.signature(tool_fns["list_filter_values"])
        assert sig.parameters["ontology"].default is None

    def test_existing_filter_types_survive(self, tool_fns):
        hint_str = _hint_str(tool_fns, "list_filter_values", "filter_type")
        for value in ("gene_category", "brite_tree", "omics_type",
                      "evidence_source"):
            assert f"'{value}'" in hint_str, value


class TestExpectedToolsUnchangedForAnnotationTrust:
    """PR 3a registers three ontologies and a trust surface — no new tool.
    PR 3b adds exactly one: `ontology_term_details` (41 → 42)."""

    def test_expected_tools_size_is_42(self):
        assert len(EXPECTED_TOOLS) == 42, (
            f"EXPECTED_TOOLS unexpectedly has {len(EXPECTED_TOOLS)} entries; "
            "the annotation-trust surface adds exactly one tool "
            "(ontology_term_details, PR 3b)"
        )

    def test_no_ontology_keys_leaked_in_as_tools(self, tool_fns):
        for key in ("interpro", "ncbifam", "merops"):
            assert key not in tool_fns


class TestSparseRowWireShape:
    """Trust row models serialize only the fields the api layer set:
    a non-applicable column (never provided) is omitted from the wire,
    an owned-but-absent column (provided as None) is kept as null.
    Mirrors the api strip rule (design §3) at the MCP boundary."""

    def test_unset_fields_are_omitted_and_explicit_none_is_kept(self):
        from pydantic import Field
        from pydantic_core import to_json
        from multiomics_explorer.mcp_server.tools import SparseRow

        class Row(SparseRow):
            locus_tag: str
            evidence: str | None = Field(default=None)
            tier: int | None = Field(default=None)
            bit_score: float | None = Field(default=None)

        row = Row(locus_tag="PMM0392", evidence="family_inferred", tier=None)
        dumped = row.model_dump()
        assert dumped == {"locus_tag": "PMM0392", "evidence": "family_inferred", "tier": None}
        assert json.loads(to_json(row)) == dumped

    @pytest.mark.parametrize("class_name", ["GenesByOntologyResult", "OntologyTermRow"])
    def test_gene_term_row_models_are_sparse(self, class_name):
        import inspect
        from multiomics_explorer.mcp_server.tools import register_tools
        src = inspect.getsource(register_tools)
        assert f"class {class_name}(SparseRow):" in src


# ===========================================================================
# PR 3b — annotation-trust surface, term side (RED)
#
# New `ontology_term_details` tool (Mode A) + `search_ontology` browse /
# multi-ontology signature and envelope changes (design §3.4, §3.5, §6;
# spec §13).
# ===========================================================================

import inspect as _inspect3b
import typing as _typing3b

from multiomics_explorer.mcp_server.tools import SparseRow as _SparseRow3b


def _response_model(tool_fns, tool_name):
    hints = _typing3b.get_type_hints(tool_fns[tool_name])
    return hints["return"]


def _row_model(tool_fns, tool_name):
    resp = _response_model(tool_fns, tool_name)
    ann = resp.model_fields["results"].annotation
    return _typing3b.get_args(ann)[0]


_OTD_API_RETURN = {
    "total_matching": 2,
    "returned": 2,
    "offset": 0,
    "truncated": False,
    "not_found": ["bogus:xyz"],
    "by_ontology": [{"ontology": "tcdb", "count": 1},
                    {"ontology": "go_bp", "count": 1}],
    "links_out_total": 2,
    "by_link_kind": [{"link_kind": "composition", "count": 2}],
    "warnings": [],
    "results": [
        {
            "term_id": "tcdb:3.A.1", "ontology": "tcdb", "label": "TcdbFamily",
            "name": "ABC superfamily", "description": None, "level": 2,
            "level_kind": "tc_family", "is_informative": True,
            "gene_count": 900, "organism_count": 45, "direct_gene_count": 120,
            "tcdb_id": "3.A.1", "tc_class_id": "3.A", "member_count": 55,
            "superfamily": "ABC", "metabolite_count": 40,
            "parents": [{"id": "tcdb:3.A", "name": "P-P-bond", "level": 1}],
            "children": [{"id": "tcdb:3.A.1.1", "name": "fam", "level": 3}],
            "children_total": 55, "children_truncated": True,
            "links_out": [
                {"rel": "Tcdb_family_has_pfam_domain", "link_kind": "composition",
                 "target_id": "pfam:PF00005", "target_ontology": "pfam",
                 "target_name": "ABC_tran"},
                {"rel": "Tcdb_family_involved_in_biological_process",
                 "link_kind": "composition", "target_id": "go:0055085",
                 "target_ontology": "go_bp", "target_name": "transmembrane transport"},
            ],
        },
        {
            "term_id": "go:0006979", "ontology": "go_bp",
            "label": "BiologicalProcess", "name": "response to oxidative stress",
            "description": None, "level": 3, "level_kind": "depth",
            "is_informative": True, "gene_count": 1050, "organism_count": 42,
            "direct_gene_count": 860,
            "parents": [{"id": "go:0006950", "name": "response to stress", "level": 2}],
            "children": [], "children_total": 0, "children_truncated": False,
            "links_out": [],
        },
    ],
}


class TestOntologyTermDetailsWrapper:
    def test_registered(self, tool_fns):
        assert "ontology_term_details" in tool_fns

    def test_in_expected_tools(self):
        assert "ontology_term_details" in EXPECTED_TOOLS

    @pytest.mark.parametrize("param,default", [
        ("organism", None), ("link_kinds", None), ("verbose", False),
        ("limit", 50), ("offset", 0),
    ])
    def test_signature_defaults(self, tool_fns, param, default):
        sig = _inspect3b.signature(tool_fns["ontology_term_details"])
        assert sig.parameters[param].default == default

    def test_term_ids_is_required(self, tool_fns):
        sig = _inspect3b.signature(tool_fns["ontology_term_details"])
        assert sig.parameters["term_ids"].default is _inspect3b.Parameter.empty

    def test_no_summary_param(self, tool_fns):
        sig = _inspect3b.signature(tool_fns["ontology_term_details"])
        assert "summary" not in sig.parameters

    def test_link_kinds_is_a_closed_literal(self, tool_fns):
        hint = _hint_str(tool_fns, "ontology_term_details", "link_kinds")
        for kind in ("composition", "membership", "router"):
            assert f"'{kind}'" in hint

    @pytest.mark.parametrize("param", [
        "term_ids", "organism", "link_kinds", "verbose", "limit", "offset",
    ])
    def test_field_description_present_and_within_250(self, tool_fns, param):
        descs = [d for d in _field_descriptions(
            tool_fns, "ontology_term_details", param) if d]
        assert descs, f"{param} has no Field description"
        for d in descs:
            assert len(d) <= 250, f"{param}: {len(d)} chars"

    def test_docstring_opens_with_a_verb_and_ends_with_routing(self, tool_fns):
        doc = _inspect3b.getdoc(tool_fns["ontology_term_details"]) or ""
        first = doc.strip().split()[0]
        assert first[0].isupper()
        assert first not in ("This", "The", "A", "An", "Tool")
        assert "Routing:" in doc
        assert doc.strip().rfind("Routing:") > doc.strip().rfind("\n\n")

    @pytest.mark.parametrize("needle", [
        "genes_by_ontology", "search_ontology", "docs://ontologies",
    ])
    def test_docstring_routes(self, tool_fns, needle):
        doc = _inspect3b.getdoc(tool_fns["ontology_term_details"]) or ""
        assert needle in doc

    @pytest.mark.parametrize("needle", ["composition", "router", "recall"])
    def test_docstring_carries_the_bridge_direction_contract(self, tool_fns, needle):
        doc = _inspect3b.getdoc(tool_fns["ontology_term_details"]) or ""
        assert needle in doc.lower()

    def test_row_model_is_sparse(self, tool_fns):
        row_model = _row_model(tool_fns, "ontology_term_details")
        assert issubclass(row_model, _SparseRow3b)

    @pytest.mark.parametrize("field", [
        "term_id", "ontology", "label", "name", "description", "level",
        "level_kind", "is_informative", "gene_count", "organism_count",
        "direct_gene_count", "parents", "children", "children_total",
        "children_truncated", "links_out", "properties", "genes_by_organism",
        "organism_gene_count",
    ])
    def test_row_model_field(self, tool_fns, field):
        assert field in _row_model(tool_fns, "ontology_term_details").model_fields

    def test_ontology_field_routes_to_the_reference(self, tool_fns):
        row_model = _row_model(tool_fns, "ontology_term_details")
        assert "docs://ontologies" in (
            row_model.model_fields["ontology"].description or "")

    @pytest.mark.parametrize("field", [
        "total_matching", "returned", "offset", "truncated", "not_found",
        "by_ontology", "links_out_total", "by_link_kind", "warnings", "results",
    ])
    def test_response_model_field(self, tool_fns, field):
        assert field in _response_model(
            tool_fns, "ontology_term_details").model_fields

    def test_row_field_descriptions_within_250(self, tool_fns):
        row_model = _row_model(tool_fns, "ontology_term_details")
        for name, field in row_model.model_fields.items():
            assert field.description, name
            assert len(field.description) <= 250, name

    @pytest.mark.asyncio
    async def test_returns_envelope(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.ontology_term_details",
            return_value=_OTD_API_RETURN,
        ):
            result = await tool_fns["ontology_term_details"](
                mock_ctx, term_ids=["tcdb:3.A.1", "go:0006979", "bogus:xyz"])
        assert result.total_matching == 2
        assert result.returned == 2
        assert result.not_found == ["bogus:xyz"]
        assert result.links_out_total == 2
        assert [b.ontology for b in result.by_ontology] == ["tcdb", "go_bp"]
        assert result.by_link_kind[0].link_kind == "composition"
        assert result.results[0].term_id == "tcdb:3.A.1"
        assert result.results[0].children_truncated is True
        assert result.results[0].links_out[0].target_ontology == "pfam"

    @pytest.mark.asyncio
    async def test_rows_serialize_sparse(self, tool_fns, mock_ctx):
        """A GO row never carries tcdb_id; a TCDB row does."""
        with patch(
            "multiomics_explorer.api.functions.ontology_term_details",
            return_value=_OTD_API_RETURN,
        ):
            result = await tool_fns["ontology_term_details"](
                mock_ctx, term_ids=["tcdb:3.A.1", "go:0006979"])
        go = result.results[1].model_dump()
        tcdb = result.results[0].model_dump()
        assert "tcdb_id" not in go
        assert "properties" not in go
        assert "genes_by_organism" not in go
        assert tcdb["tcdb_id"] == "3.A.1"

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.ontology_term_details",
            return_value={**_OTD_API_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["ontology_term_details"](
                mock_ctx, term_ids=["tcdb:3.A.1"],
                organism="Prochlorococcus MED4", link_kinds=["router"],
                verbose=True, limit=10, offset=5)
        kwargs = mock_api.call_args.kwargs
        args = mock_api.call_args.args
        assert kwargs.get("term_ids", args[0] if args else None) == ["tcdb:3.A.1"]
        assert kwargs["organism"] == "Prochlorococcus MED4"
        assert kwargs["link_kinds"] == ["router"]
        assert kwargs["verbose"] is True
        assert kwargs["limit"] == 10
        assert kwargs["offset"] == 5

    @pytest.mark.asyncio
    async def test_empty_term_ids_raises_toolerror(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.ontology_term_details",
            side_effect=ValueError("term_ids must not be empty"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["ontology_term_details"](mock_ctx, term_ids=[])

    @pytest.mark.asyncio
    async def test_value_error_becomes_toolerror(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.ontology_term_details",
            side_effect=ValueError("Unknown link_kind"),
        ):
            with pytest.raises(ToolError, match="link_kind"):
                await tool_fns["ontology_term_details"](
                    mock_ctx, term_ids=["tcdb:3.A.1"], link_kinds=["router"])

    @pytest.mark.asyncio
    async def test_verbose_rows_carry_properties_and_genes_by_organism(
            self, tool_fns, mock_ctx):
        rows = [dict(_OTD_API_RETURN["results"][0])]
        rows[0]["properties"] = {"id": "tcdb:3.A.1", "name": "ABC superfamily"}
        rows[0]["genes_by_organism"] = [
            {"organism": "Prochlorococcus MED4", "gene_count": 3}]
        rows[0]["links_out"] = [dict(rows[0]["links_out"][0],
                                     props={"curated_tcids": ["3.A.1.1.1"]})]
        with patch(
            "multiomics_explorer.api.functions.ontology_term_details",
            return_value={**_OTD_API_RETURN, "results": rows, "returned": 1},
        ):
            result = await tool_fns["ontology_term_details"](
                mock_ctx, term_ids=["tcdb:3.A.1"], verbose=True)
        row = result.results[0]
        assert row.properties["id"] == "tcdb:3.A.1"
        assert row.genes_by_organism[0].organism == "Prochlorococcus MED4"
        assert row.links_out[0].props["curated_tcids"] == ["3.A.1.1.1"]

    def test_compact_link_rows_omit_props_key_on_the_wire(self, tool_fns):
        """Compact `links_out[]` rows carry no `props` key at all (sparse) —
        the wrapper must not re-add `props: null`."""
        row_model = _response_model(tool_fns, "ontology_term_details").model_fields[
            "results"].annotation.__args__[0]
        link_model = row_model.model_fields["links_out"].annotation.__args__[0]
        compact = link_model(rel="Tcdb_family_has_pfam_domain", link_kind="composition",
                             target_id="pfam:PF00005", target_ontology="pfam")
        assert "props" not in compact.model_dump()
        verbose = link_model(rel="Tcdb_family_has_pfam_domain", link_kind="composition",
                             target_id="pfam:PF00005", target_ontology="pfam",
                             props={"curated_tcids": ["3.A.1.1.1"]})
        assert verbose.model_dump()["props"] == {"curated_tcids": ["3.A.1.1.1"]}

    @pytest.mark.asyncio
    async def test_all_not_found_is_an_empty_envelope(self, tool_fns, mock_ctx):
        empty = {**_OTD_API_RETURN, "total_matching": 0, "returned": 0,
                 "truncated": False, "not_found": ["a:1"], "by_ontology": [],
                 "links_out_total": 0, "by_link_kind": [], "results": []}
        with patch(
            "multiomics_explorer.api.functions.ontology_term_details",
            return_value=empty,
        ):
            result = await tool_fns["ontology_term_details"](
                mock_ctx, term_ids=["a:1"])
        assert result.results == []
        assert result.not_found == ["a:1"]


class TestSearchOntologyWrapper3b:
    """`search_text` optional (browse), `ontology: list | str | None`,
    `min_gene_count`, `organism`; rows gain `ontology_type`; envelope gains
    `mode` / `by_ontology` / `by_level` / `skipped_ontologies` / `warnings`."""

    _BROWSE_RETURN = {
        "total_entries": 300, "total_matching": 60,
        "score_max": None, "score_median": None,
        "returned": 2, "offset": 0, "truncated": True,
        "mode": "browse",
        "by_ontology": [{"ontology": "merops", "total_entries": 300,
                         "total_matching": 60, "score_max": None,
                         "returned": 2, "truncated": True}],
        "by_level": [{"level": 1, "count": 60}],
        "skipped_ontologies": [],
        "warnings": ["browse mode truncated; narrow with level / min_gene_count"],
        "results": [
            {"id": "merops.family:S33", "name": "S33", "ontology_type": "merops",
             "score": None, "level": 1, "is_informative": True,
             "gene_count": 412, "organism_count": 41},
            {"id": "merops.family:S09", "name": "S09", "ontology_type": "merops",
             "score": None, "level": 1, "is_informative": True,
             "gene_count": 298, "organism_count": 40},
        ],
    }

    @pytest.mark.parametrize("param,default", [
        ("search_text", None), ("ontology", None),
        ("min_gene_count", None), ("organism", None),
    ])
    def test_signature_defaults(self, tool_fns, param, default):
        sig = _inspect3b.signature(tool_fns["search_ontology"])
        assert sig.parameters[param].default == default

    def test_ontology_accepts_a_list(self, tool_fns):
        assert "list" in _hint_str(tool_fns, "search_ontology", "ontology").lower()

    @pytest.mark.parametrize("param", [
        "search_text", "ontology", "min_gene_count", "organism",
    ])
    def test_field_description_present_and_within_250(self, tool_fns, param):
        descs = [d for d in _field_descriptions(
            tool_fns, "search_ontology", param) if d]
        assert descs, f"{param} has no Field description"
        for d in descs:
            assert len(d) <= 250, f"{param}: {len(d)} chars"

    def test_search_text_description_mentions_browse(self, tool_fns):
        joined = " ".join(
            d for d in _field_descriptions(tool_fns, "search_ontology", "search_text") if d)
        assert "browse" in joined.lower()

    def test_docstring_routes_to_the_reference(self, tool_fns):
        doc = _inspect3b.getdoc(tool_fns["search_ontology"]) or ""
        assert "docs://ontologies" in doc
        assert "ontology_term_details" in doc

    @pytest.mark.parametrize("field", [
        "ontology_type", "description", "level_kind", "direct_gene_count",
        "superfamily", "metabolite_count", "family_type", "gene_symbol",
        "family_class", "catalytic_type", "peptidase_gene_count",
        "interpro_type", "organism_gene_count",
    ])
    def test_row_model_field(self, tool_fns, field):
        assert field in _row_model(tool_fns, "search_ontology").model_fields

    def test_row_score_is_optional(self, tool_fns):
        row_model = _row_model(tool_fns, "search_ontology")
        assert row_model.model_fields["score"].is_required() is False

    @pytest.mark.parametrize("field", [
        "mode", "by_ontology", "by_level", "by_interpro_type",
        "by_family_type", "skipped_ontologies", "warnings",
    ])
    def test_response_model_field(self, tool_fns, field):
        assert field in _response_model(tool_fns, "search_ontology").model_fields

    @pytest.mark.asyncio
    async def test_browse_call_without_search_text(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=self._BROWSE_RETURN,
        ) as mock_api:
            result = await tool_fns["search_ontology"](
                mock_ctx, ontology="merops", level=1)
        assert result.mode == "browse"
        assert result.results[0].id == "merops.family:S33"
        assert result.results[0].gene_count == 412
        assert result.results[0].score is None
        assert result.results[0].ontology_type == "merops"
        assert result.by_level[0].level == 1
        assert result.by_ontology[0].ontology == "merops"
        assert result.by_ontology[0].truncated is True
        assert result.warnings
        call = mock_api.call_args
        text = call.kwargs.get("search_text", call.args[0] if call.args else "MISSING")
        assert text is None

    @pytest.mark.asyncio
    async def test_list_ontology_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={**self._BROWSE_RETURN, "results": [], "returned": 0,
                          "mode": "search"},
        ) as mock_api:
            await tool_fns["search_ontology"](
                mock_ctx, search_text="transport", ontology=["go_bp", "tcdb"],
                limit=5)
        call = mock_api.call_args
        ont = call.kwargs.get(
            "ontology", call.args[1] if len(call.args) > 1 else None)
        assert ont == ["go_bp", "tcdb"]

    @pytest.mark.asyncio
    async def test_new_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={**self._BROWSE_RETURN, "results": [], "returned": 0},
        ) as mock_api:
            await tool_fns["search_ontology"](
                mock_ctx, ontology="interpro",
                interpro_type="HOMOLOGOUS_SUPERFAMILY",
                organism="Prochlorococcus MED4", min_gene_count=5)
        kwargs = mock_api.call_args.kwargs
        assert kwargs["organism"] == "Prochlorococcus MED4"
        assert kwargs["min_gene_count"] == 5
        assert kwargs["interpro_type"] == "HOMOLOGOUS_SUPERFAMILY"

    @pytest.mark.asyncio
    async def test_rows_with_organism_gene_count(self, tool_fns, mock_ctx):
        rows = [dict(self._BROWSE_RETURN["results"][0], organism_gene_count=9)]
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={**self._BROWSE_RETURN, "results": rows, "returned": 1},
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, ontology="merops", organism="Prochlorococcus MED4")
        assert result.results[0].organism_gene_count == 9

    @pytest.mark.asyncio
    async def test_compact_rows_serialize_sparse(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=self._BROWSE_RETURN,
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, ontology="merops", level=1)
        dumped = result.results[0].model_dump()
        assert "description" not in dumped
        assert "family_class" not in dumped
        assert "organism_gene_count" not in dumped
        assert dumped["score"] is None

    @pytest.mark.asyncio
    async def test_multi_response_carries_skipped_and_by_ontology(
            self, tool_fns, mock_ctx):
        multi = {
            **self._BROWSE_RETURN, "mode": "search", "score_max": 9.0,
            "score_median": 4.0, "warnings": [],
            "by_ontology": [
                {"ontology": "go_bp", "total_entries": 1000, "total_matching": 40,
                 "score_max": 9.0, "returned": 5, "truncated": True},
                {"ontology": "tcdb", "total_entries": 500, "total_matching": 3,
                 "score_max": 6.0, "returned": 3, "truncated": False},
            ],
            "by_level": [],
            "results": [
                {"id": "go:0055085", "name": "transmembrane transport",
                 "ontology_type": "go_bp", "score": 9.0, "level": 3,
                 "is_informative": True, "gene_count": 10, "organism_count": 4},
                {"id": "tcdb:3.A.1", "name": "ABC", "ontology_type": "tcdb",
                 "score": 6.0, "level": 2, "is_informative": True,
                 "gene_count": 10, "organism_count": 4},
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=multi,
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="transport", ontology=["go_bp", "tcdb"],
                limit=5)
        assert [b.ontology for b in result.by_ontology] == ["go_bp", "tcdb"]
        assert result.by_ontology[0].truncated is True
        assert result.by_ontology[1].truncated is False
        assert result.skipped_ontologies == []
        assert [r.ontology_type for r in result.results] == ["go_bp", "tcdb"]

    @pytest.mark.asyncio
    async def test_facet_owner_absent_becomes_toolerror(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            side_effect=ValueError("interpro_type is only carried by 'interpro'"),
        ):
            with pytest.raises(ToolError, match="interpro_type"):
                await tool_fns["search_ontology"](
                    mock_ctx, search_text="kinase", ontology=["kegg", "tcdb"],
                    interpro_type="DOMAIN")

    @pytest.mark.asyncio
    async def test_verbose_rows_carry_term_verbose_columns(self, tool_fns, mock_ctx):
        rows = [dict(self._BROWSE_RETURN["results"][0],
                     description="serine peptidase", level_kind="family",
                     direct_gene_count=400, family_class="S",
                     catalytic_type="Serine", peptidase_gene_count=380)]
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={**self._BROWSE_RETURN, "results": rows, "returned": 1},
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, ontology="merops", verbose=True)
        row = result.results[0]
        assert row.description == "serine peptidase"
        assert row.family_class == "S"
        assert row.peptidase_gene_count == 380
        assert row.direct_gene_count == 400


class TestSearchOntologyReviewFixes3b:
    """PR 3b code-review fix wave: `skipped_ontologies` is `[{ontology,
    reason}]` (matches `_resolve_multi_ontology` and the other multi-ontology
    wrappers); every Field description on search_ontology and
    ontology_term_details is within 250 chars (incl. `verbose`)."""

    @pytest.mark.asyncio
    async def test_skipped_ontologies_accepts_dict_entries(self, tool_fns, mock_ctx):
        data = dict(TestSearchOntologyWrapper3b._BROWSE_RETURN)
        data["skipped_ontologies"] = [
            {"ontology": "tcdb", "reason": "interpro_type applies to interpro only"}]
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value=data,
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, ontology=["merops", "tcdb"], level=1,
                interpro_type="FAMILY")
        assert result.skipped_ontologies == [
            {"ontology": "tcdb", "reason": "interpro_type applies to interpro only"}]

    def test_skipped_ontologies_is_a_list_of_dicts(self, tool_fns):
        ann = _response_model(tool_fns, "search_ontology").model_fields[
            "skipped_ontologies"].annotation
        assert ann == list[dict]

    @pytest.mark.parametrize("tool_name", [
        "search_ontology", "ontology_term_details",
        "list_filter_values", "kg_release_info",
    ])
    def test_every_param_field_description_within_250(self, tool_fns, tool_name):
        sig = _inspect3b.signature(tool_fns[tool_name])
        for param in sig.parameters:
            if param == "ctx":
                continue
            for d in _field_descriptions(tool_fns, tool_name, param):
                if d is not None:
                    assert len(d) <= 250, f"{tool_name}.{param}: {len(d)} chars"

    def test_search_ontology_verbose_within_250(self, tool_fns):
        descs = [d for d in _field_descriptions(
            tool_fns, "search_ontology", "verbose") if d]
        assert descs
        assert all(len(d) <= 250 for d in descs)

    @pytest.mark.parametrize("tool_name", ["search_ontology", "ontology_term_details"])
    def test_every_response_field_description_within_250(self, tool_fns, tool_name):
        seen = set()

        def walk(model):
            if model in seen:
                return
            seen.add(model)
            for name, info in model.model_fields.items():
                if info.description is not None:
                    assert len(info.description) <= 250, (
                        f"{model.__name__}.{name}: {len(info.description)} chars")
                for sub in (info.annotation, *_typing3b.get_args(info.annotation)):
                    if hasattr(sub, "model_fields"):
                        walk(sub)

        walk(_response_model(tool_fns, tool_name))
        assert len(seen) >= 2

    def test_organism_gene_count_semantics_are_stated(self, tool_fns):
        so = _row_model(tool_fns, "search_ontology").model_fields[
            "organism_gene_count"].description
        otd = _row_model(tool_fns, "ontology_term_details").model_fields[
            "organism_gene_count"].description
        # Both are subtree-scoped since backlog 2.2 and say so, cross-referencing
        # each other.
        assert "SUBTREE" in so and "DIRECT" not in so
        assert "ontology_term_details" in so
        assert "SUBTREE" in otd
        assert "search_ontology" in otd

    def test_score_median_states_page_vs_full_match(self, tool_fns):
        desc = _response_model(tool_fns, "search_ontology").model_fields[
            "score_median"].description
        assert "page" in desc.lower()
        assert "full match" in desc.lower()

    def test_term_details_warnings_is_reserved(self, tool_fns):
        desc = _response_model(tool_fns, "ontology_term_details").model_fields[
            "warnings"].description
        assert "router_ambiguous" not in desc
        assert "reserved" in desc.lower()


# ===========================================================================
# Slice 4 — light surface + paper-batch absorption (spec
# docs/tool-specs/2026-08-27-slice4-light-surface.md). Stage 1 RED.
# ===========================================================================


def _param_description(tool_fns, tool_name, param):
    """Joined Field(description=...) text of one wrapper parameter."""
    import typing
    fn = tool_fns[tool_name]
    hints = typing.get_type_hints(fn, include_extras=True)
    hint = hints[param]
    descriptions = [
        getattr(meta, "description", None)
        for meta in getattr(hint, "__metadata__", ())
    ]
    return " ".join(d for d in descriptions if d)


def _param_literal_values(tool_fns, tool_name, param):
    import typing
    fn = tool_fns[tool_name]
    hints = typing.get_type_hints(fn, include_extras=True)
    hint = hints[param]
    inner = typing.get_args(hint)[0] if hasattr(hint, "__metadata__") else hint
    assert typing.get_origin(inner) is typing.Literal, inner
    return set(typing.get_args(inner))


class TestGeneReactionMetaboliteTripletSubstrateResolution:
    """Spec §3.2 / §6: `GeneReactionMetaboliteTriplet` gains
    `transport_substrate_resolution: Literal['resolved','family_inferred']
    | None`, compact, right after `tcdb_evidence_score`, explicit None on
    metabolism rows (union padding — the model is NOT a SparseRow)."""

    _BASE = {
        "locus_tag": "PMM0974", "gene_name": "urtE",
        "product": "ABC-type urea transporter, ATPase component",
        "evidence_source": "transport", "substrate_depth": "most_specific",
        "tcdb_evidence_score": 0.8,
        "tcdb_family_id": "tcdb:3.A.1.4.5", "tcdb_family_name": "tcdb:3.A.1.4.5",
        "metabolite_id": "kegg.compound:C00086", "metabolite_name": "Urea",
    }

    def test_field_exists_and_is_optional_literal(self):
        import types
        import typing
        from multiomics_explorer.mcp_server.tools import GeneReactionMetaboliteTriplet
        fields = GeneReactionMetaboliteTriplet.model_fields
        assert "transport_substrate_resolution" in fields
        ann = fields["transport_substrate_resolution"].annotation
        assert typing.get_origin(ann) in {types.UnionType, typing.Union}
        args = typing.get_args(ann)
        assert type(None) in args
        literal = next(a for a in args if typing.get_origin(a) is typing.Literal)
        assert set(typing.get_args(literal)) == {"resolved", "family_inferred"}

    def test_field_description_present_and_bounded(self):
        from multiomics_explorer.mcp_server.tools import GeneReactionMetaboliteTriplet
        field = GeneReactionMetaboliteTriplet.model_fields["transport_substrate_resolution"]
        assert field.description
        assert len(field.description) <= 250
        # It is the GENE's resolution, repeated on the row — say so.
        assert "gene" in field.description.lower()

    def test_position_right_after_tcdb_evidence_score(self):
        from multiomics_explorer.mcp_server.tools import GeneReactionMetaboliteTriplet
        names = list(GeneReactionMetaboliteTriplet.model_fields)
        assert names.index("transport_substrate_resolution") == (
            names.index("tcdb_evidence_score") + 1)

    def test_transport_row_accepts_both_values(self):
        from multiomics_explorer.mcp_server.tools import GeneReactionMetaboliteTriplet
        for v in ("resolved", "family_inferred"):
            row = GeneReactionMetaboliteTriplet(
                **self._BASE, transport_substrate_resolution=v)
            assert row.transport_substrate_resolution == v

    def test_rejects_retired_or_unknown_value(self):
        from pydantic import ValidationError
        from multiomics_explorer.mcp_server.tools import GeneReactionMetaboliteTriplet
        for bad in ("substrate_confirmed", "most_specific", "bogus"):
            with pytest.raises(ValidationError):
                GeneReactionMetaboliteTriplet(
                    **self._BASE, transport_substrate_resolution=bad)

    def test_metabolism_row_explicit_none_is_kept_on_the_wire(self):
        """Union padding: an explicit None must survive serialization
        (the model is not a SparseRow — every row carries identical keys)."""
        from multiomics_explorer.mcp_server.tools import GeneReactionMetaboliteTriplet
        row = GeneReactionMetaboliteTriplet(
            locus_tag="PMM0944", gene_name="ureC", product="urease",
            evidence_source="metabolism", substrate_depth=None,
            tcdb_evidence_score=None, transport_substrate_resolution=None,
            reaction_id="kegg.reaction:R00131",
            metabolite_id="kegg.compound:C00086", metabolite_name="Urea",
        )
        dumped = row.model_dump()
        assert "transport_substrate_resolution" in dumped
        assert dumped["transport_substrate_resolution"] is None

    @pytest.mark.asyncio
    async def test_gbm_wrapper_surfaces_the_column(self, tool_fns, mock_ctx):
        payload = {
            **_GBM_SAMPLE_API_RETURN,
            "results": [
                {**self._BASE, "transport_substrate_resolution": "resolved"},
                {
                    "locus_tag": "PMM0944", "gene_name": "ureC",
                    "product": "urease", "evidence_source": "metabolism",
                    "substrate_depth": None, "tcdb_evidence_score": None,
                    "transport_substrate_resolution": None,
                    "reaction_id": "kegg.reaction:R00131",
                    "metabolite_id": "kegg.compound:C00086",
                    "metabolite_name": "Urea",
                },
            ],
        }
        with patch("multiomics_explorer.api.functions.genes_by_metabolite",
                   return_value=payload):
            result = await tool_fns["genes_by_metabolite"](
                mock_ctx, metabolite_ids=["kegg.compound:C00086"],
                organism="Prochlorococcus MED4")
        by_src = {r.evidence_source: r for r in result.results}
        assert by_src["transport"].transport_substrate_resolution == "resolved"
        assert by_src["metabolism"].transport_substrate_resolution is None

    @pytest.mark.asyncio
    async def test_mbg_wrapper_surfaces_the_column(self, tool_fns, mock_ctx):
        payload = {
            **_MBG_SAMPLE_API_RETURN,
            "results": [
                {**self._BASE, "locus_tag": "PMM0234",
                 "substrate_depth": "inherited", "tcdb_evidence_score": 0.4,
                 "transport_substrate_resolution": "family_inferred"},
            ],
        }
        with patch("multiomics_explorer.api.functions.metabolites_by_gene",
                   return_value=payload):
            result = await tool_fns["metabolites_by_gene"](
                mock_ctx, locus_tags=["PMM0234"],
                organism="Prochlorococcus MED4")
        assert result.results[0].transport_substrate_resolution == "family_inferred"


class TestListOrganismsAnnotationCapabilityWrapper:
    """Spec §3.3 / §6: `ListOrganismsResult` carries the four ints (default 0)
    and `ListOrganismsResponse.top_annotation_capability` is a typed list of
    `{preferred_name, organism_name, <four counts>}` entries."""

    _COLS = (
        "peptidase_gene_count", "nonpeptidase_homolog_gene_count",
        "interpro_gene_count", "ncbifam_gene_count",
    )

    _ORG = {
        "organism_name": "Alteromonas (MarRef v6)",
        "organism_type": "reference_proteome_match",
        "genus": "Alteromonas", "species": None, "strain": None, "clade": None,
        "ncbi_taxon_id": None, "gene_count": 4200, "publication_count": 1,
        "experiment_count": 2, "treatment_types": [], "omics_types": [],
        "peptidase_gene_count": 148,
        "nonpeptidase_homolog_gene_count": 31,
        "interpro_gene_count": 3746,
        "ncbifam_gene_count": 1379,
    }

    _CAP = [
        {"preferred_name": "Alteromonas (MarRef v6)",
         "organism_name": "Alteromonas (MarRef v6)",
         "peptidase_gene_count": 148, "nonpeptidase_homolog_gene_count": 31,
         "interpro_gene_count": 3746, "ncbifam_gene_count": 1379},
        {"preferred_name": "Prochlorococcus MED4",
         "organism_name": "Prochlorococcus MED4",
         "peptidase_gene_count": 50, "nonpeptidase_homolog_gene_count": 8,
         "interpro_gene_count": 1545, "ncbifam_gene_count": 744},
    ]

    def _envelope(self, **extra):
        return {
            "total_entries": 48, "total_matching": 48,
            "returned": 1, "truncated": True, "not_found": [],
            "results": [self._ORG],
            "top_annotation_capability": self._CAP,
            **extra,
        }

    @pytest.mark.asyncio
    async def test_rows_carry_the_four_counts(self, tool_fns, mock_ctx):
        with patch("multiomics_explorer.api.functions.list_organisms",
                   return_value=self._envelope()):
            result = await tool_fns["list_organisms"](mock_ctx)
        org = result.results[0]
        assert org.peptidase_gene_count == 148
        assert org.nonpeptidase_homolog_gene_count == 31
        assert org.interpro_gene_count == 3746
        assert org.ncbifam_gene_count == 1379

    @pytest.mark.asyncio
    async def test_row_counts_default_to_zero(self, tool_fns, mock_ctx):
        bare = {k: v for k, v in self._ORG.items() if k not in self._COLS}
        with patch("multiomics_explorer.api.functions.list_organisms",
                   return_value=self._envelope(results=[bare])):
            result = await tool_fns["list_organisms"](mock_ctx)
        org = result.results[0]
        for col in self._COLS:
            assert getattr(org, col) == 0, col

    @pytest.mark.asyncio
    async def test_row_field_descriptions_present(self, tool_fns, mock_ctx):
        with patch("multiomics_explorer.api.functions.list_organisms",
                   return_value=self._envelope()):
            result = await tool_fns["list_organisms"](mock_ctx)
        row_model = type(result.results[0])
        names = list(row_model.model_fields)
        for col in self._COLS:
            field = row_model.model_fields[col]
            assert field.description, col
            assert field.annotation is int, col
            # compact, after measured_metabolite_count (spec §3.3)
            assert names.index(col) > names.index("measured_metabolite_count"), col

    @pytest.mark.asyncio
    async def test_envelope_top_annotation_capability_is_typed(self, tool_fns, mock_ctx):
        with patch("multiomics_explorer.api.functions.list_organisms",
                   return_value=self._envelope()):
            result = await tool_fns["list_organisms"](mock_ctx)
        cap = result.top_annotation_capability
        assert len(cap) == 2
        first = cap[0]
        assert not isinstance(first, dict), "entries must be a Pydantic sub-model"
        assert first.preferred_name == "Alteromonas (MarRef v6)"
        assert first.organism_name == "Alteromonas (MarRef v6)"
        assert first.peptidase_gene_count == 148
        assert first.nonpeptidase_homolog_gene_count == 31
        assert first.interpro_gene_count == 3746
        assert first.ncbifam_gene_count == 1379
        entry_model = type(first)
        assert set(entry_model.model_fields) == {
            "preferred_name", "organism_name", *self._COLS}
        for name, field in entry_model.model_fields.items():
            assert field.description, name

    @pytest.mark.asyncio
    async def test_envelope_field_description_names_the_ranking(self, tool_fns, mock_ctx):
        with patch("multiomics_explorer.api.functions.list_organisms",
                   return_value=self._envelope()):
            result = await tool_fns["list_organisms"](mock_ctx)
        field = type(result).model_fields["top_annotation_capability"]
        assert field.description
        assert "peptidase_gene_count" in field.description
        assert "10" in field.description

    @pytest.mark.asyncio
    async def test_envelope_defaults_to_empty_list(self, tool_fns, mock_ctx):
        env = self._envelope()
        env.pop("top_annotation_capability")
        with patch("multiomics_explorer.api.functions.list_organisms",
                   return_value=env):
            result = await tool_fns["list_organisms"](mock_ctx)
        assert result.top_annotation_capability == []

    def test_no_new_filter_param(self, tool_fns):
        import inspect
        params = inspect.signature(tool_fns["list_organisms"]).parameters
        assert "min_peptidase_gene_count" not in params


class TestKGAssertVocabularyBucket:
    """Spec §3.1 / §6: bucket 6 entry shape on the KGAssert model —
    `{name/kind: 'controlled_vocabularies_hash', passed, expected, actual,
    detail}`; older kinds validate without expected/actual."""

    def _bucket(self, passed=True):
        pin = "sha256:" + "6" * 64
        return {
            "name": "controlled_vocabularies_hash",
            "kind": "controlled_vocabularies_hash",
            "passed": passed,
            "expected": pin,
            "actual": pin if passed else "sha256:" + "0" * 64,
            "detail": None if passed else "Vocabulary set differs.",
        }

    def test_kind_literal_accepts_the_new_bucket(self):
        from multiomics_explorer.mcp_server.tools import KGAssert
        a = KGAssert(**self._bucket())
        assert a.kind == "controlled_vocabularies_hash"
        assert a.passed is True
        assert a.expected.startswith("sha256:")
        assert a.actual == a.expected

    def test_failed_bucket_carries_both_hashes(self):
        from multiomics_explorer.mcp_server.tools import KGAssert
        a = KGAssert(**self._bucket(passed=False))
        assert a.passed is False
        assert a.expected != a.actual
        assert a.detail

    def test_absent_hash_is_null_actual(self):
        from multiomics_explorer.mcp_server.tools import KGAssert
        b = self._bucket(passed=False)
        b["actual"] = None
        b["detail"] = "KG predates the vocabulary contract."
        a = KGAssert(**b)
        assert a.actual is None

    def test_expected_actual_optional_on_older_kinds(self):
        from multiomics_explorer.mcp_server.tools import KGAssert
        a = KGAssert(name="node_label:Gene", kind="node_label",
                     passed=True, detail=None)
        assert a.expected is None and a.actual is None

    def test_expected_actual_fields_documented(self):
        from multiomics_explorer.mcp_server.tools import KGAssert
        for name in ("expected", "actual"):
            assert KGAssert.model_fields[name].description, name
        assert "controlled_vocabularies_hash" in KGAssert.model_fields["kind"].description

    def test_kg_identity_surfaces_controlled_vocabularies_hash(self):
        from multiomics_explorer.mcp_server.tools import KGIdentity
        pin = "sha256:" + "6" * 64
        assert "controlled_vocabularies_hash" in KGIdentity.model_fields
        assert KGIdentity.model_fields["controlled_vocabularies_hash"].description
        assert KGIdentity(controlled_vocabularies_hash=pin).controlled_vocabularies_hash == pin
        assert KGIdentity().controlled_vocabularies_hash is None

    def test_full_response_with_bucket_six(self):
        from multiomics_explorer.mcp_server.tools import KGReleaseInfoResponse
        report = TestKGReleaseInfoTool()._ok_report()
        report["kg"]["controlled_vocabularies_hash"] = "sha256:" + "6" * 64
        report["asserts"].append(self._bucket())
        resp = KGReleaseInfoResponse(**report)
        assert resp.asserts[-1].kind == "controlled_vocabularies_hash"
        assert resp.kg.controlled_vocabularies_hash == "sha256:" + "6" * 64


class TestClusterTypeDescriptionsAndFilterType:
    """Spec §3.4: `VALID_CLUSTER_TYPES` is description-only — the two
    `cluster_type` Field descriptions point at `list_filter_values`, and
    `list_filter_values` accepts `filter_type='cluster_type'`."""

    @pytest.mark.parametrize("tool", ["list_clustering_analyses", "gene_clusters_by_gene"])
    def test_cluster_type_description_points_at_list_filter_values(self, tool_fns, tool):
        desc = _param_description(tool_fns, tool, "cluster_type")
        assert "list_filter_values" in desc, desc
        assert "cluster_type" in desc, desc

    @pytest.mark.parametrize("tool", ["list_clustering_analyses", "gene_clusters_by_gene"])
    def test_cluster_type_description_lists_the_six_offline_values(self, tool_fns, tool):
        desc = _param_description(tool_fns, tool, "cluster_type")
        for v in ("condition_comparison", "diel", "time_course",
                  "expression_bin", "decay_pattern", "genomic_island"):
            assert v in desc, (tool, v)

    def test_filter_type_literal_accepts_cluster_type(self, tool_fns):
        values = _param_literal_values(tool_fns, "list_filter_values", "filter_type")
        assert "cluster_type" in values

    def test_filter_type_description_mentions_cluster_type(self, tool_fns):
        desc = _param_description(tool_fns, "list_filter_values", "filter_type")
        assert "cluster_type" in desc

    @pytest.mark.asyncio
    async def test_wrapper_forwards_cluster_type_rows(self, tool_fns, mock_ctx):
        payload = {
            "filter_type": "cluster_type", "total_entries": 6, "returned": 6,
            "truncated": False, "warnings": [],
            "results": [
                {"value": v, "applies_to": ["ClusteringAnalysis"],
                 "description": "How the analysis grouped genes",
                 "source": "vocabulary"}
                for v in ("time_course", "diel", "condition_comparison",
                          "expression_bin", "decay_pattern", "genomic_island")
            ],
        }
        with patch("multiomics_explorer.api.functions.list_filter_values",
                   return_value=payload) as mock_api:
            result = await tool_fns["list_filter_values"](
                mock_ctx, filter_type="cluster_type")
        assert mock_api.call_args.kwargs["filter_type"] == "cluster_type"
        assert result.filter_type == "cluster_type"
        assert result.returned == 6
        assert {r.value for r in result.results} == {
            "time_course", "diel", "condition_comparison",
            "expression_bin", "decay_pattern", "genomic_island"}
        assert all(r.source == "vocabulary" for r in result.results)
        assert all(r.applies_to == ["ClusteringAnalysis"] for r in result.results)


class TestSlice4NoNewTool:
    """Slice 4 is Mode B — no new tool; EXPECTED_TOOLS stays at 42."""

    def test_expected_tools_unchanged(self, tool_fns):
        assert len(EXPECTED_TOOLS) == 42
        assert sorted(tool_fns) == sorted(EXPECTED_TOOLS)


# ---------------------------------------------------------------------------
# Bare metabolite-ID coercion (backlog 3.2, Mode B) — envelope keys + docs
# ---------------------------------------------------------------------------

_METABOLITE_ID_TOOLS = [
    "list_metabolites", "genes_by_metabolite", "metabolites_by_gene",
    "list_metabolite_assays", "metabolites_by_quantifies_assay",
    "metabolites_by_flags_assay", "assays_by_metabolite",
]


def _response_model(tool_fns, name):
    import inspect
    return inspect.signature(tool_fns[name]).return_annotation


def _param_description(tool_fns, name, param):
    import typing
    hints = typing.get_type_hints(tool_fns[name], include_extras=True)
    ann = hints[param]
    for meta in getattr(ann, "__metadata__", ()):
        if getattr(meta, "description", None):
            return meta.description
    raise AssertionError(f"{name}.{param} has no Field(description=...)")


class TestMetaboliteIdCoercionWrappers:
    """Mode B — no new tool; every metabolite-ID tool's response model gains
    `resolved_aliases` + `warnings` and its two ID params document bare IDs."""

    def test_expected_tools_unchanged(self, tool_fns):
        assert len(EXPECTED_TOOLS) == 42
        assert sorted(tool_fns) == sorted(EXPECTED_TOOLS)

    @pytest.mark.parametrize("name", _METABOLITE_ID_TOOLS)
    def test_resolved_aliases_field(self, tool_fns, name):
        model = _response_model(tool_fns, name)
        field = model.model_fields["resolved_aliases"]
        assert field.annotation == dict[str, list[str]]
        assert field.get_default(call_default_factory=True) == {}
        assert field.description, f"{name}: resolved_aliases needs a description"

    @pytest.mark.parametrize("name", _METABOLITE_ID_TOOLS)
    def test_warnings_field(self, tool_fns, name):
        model = _response_model(tool_fns, name)
        field = model.model_fields["warnings"]
        assert field.annotation == list[str]
        assert field.get_default(call_default_factory=True) == []
        assert field.description, f"{name}: warnings needs a description"

    @pytest.mark.parametrize("name", _METABOLITE_ID_TOOLS)
    @pytest.mark.parametrize("param", ["metabolite_ids", "exclude_metabolite_ids"])
    def test_param_description_mentions_bare_ids(self, tool_fns, name, param):
        desc = _param_description(tool_fns, name, param)
        assert "bare" in desc.lower(), f"{name}.{param}: {desc!r}"
        assert "resolved_aliases" in desc, f"{name}.{param}: {desc!r}"
        assert len(desc) <= 250, f"{name}.{param} is {len(desc)} chars"
