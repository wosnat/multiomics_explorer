"""Correctness tests for MCP tools using realistic gene fixture data.

Tests that tool functions produce correct results when mock Neo4j returns
real gene annotation data. Complements test_tool_wrappers.py which tests
wrapper logic (validation, error messages, LIMIT injection) with minimal mocks.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from multiomics_explorer.mcp_server.tools import register_tools
from tests.fixtures.gene_data import (
    GENES,
    GENES_BY_LOCUS,
    GENES_HYPOTHETICAL,
    GENES_WITH_EC,
    GENES_WITH_GENE_NAME,
    GENES_WITHOUT_GENE_NAME,
    as_search_genes_result,
    as_resolve_gene_result,
    genes_by_organism,
    genes_with_property,
)


@pytest.fixture(scope="module")
def tool_fns():
    """Register tools on a fresh FastMCP and return a dict of {name: fn}."""
    mcp = FastMCP("test")
    register_tools(mcp)
    tools = asyncio.run(mcp.list_tools())
    return {t.name: asyncio.run(mcp.get_tool(t.name)).fn for t in tools}


@pytest.fixture()
def mock_ctx():
    """MCP Context mock whose .conn returns a MagicMock GraphConnection."""
    ctx = MagicMock()
    ctx.request_context.lifespan_context.conn = MagicMock()
    ctx.info = AsyncMock()
    ctx.warning = AsyncMock()
    ctx.error = AsyncMock()
    ctx.debug = AsyncMock()
    return ctx


def _conn_from(ctx):
    return ctx.request_context.lifespan_context.conn


# ---------------------------------------------------------------------------
# TestResolveGeneCorrectness
# ---------------------------------------------------------------------------
class TestResolveGeneCorrectness:
    """Verify resolve_gene returns correct data for realistic mock responses."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "locus_tag",
        [g["locus_tag"] for g in GENES],
        ids=[g["locus_tag"] for g in GENES],
    )
    async def test_single_gene_lookup_all_fixtures(self, tool_fns, mock_ctx, locus_tag):
        """Each fixture gene returns correct locus_tag, product, organism."""
        gene = GENES_BY_LOCUS[locus_tag]
        row = as_resolve_gene_result(gene)
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_name", "Unknown"), "count": 1}], "returned": 1, "truncated": False, "results": [row]},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier=locus_tag)

        assert result.total_matching == 1
        assert len(result.results) == 1
        r = result.results[0]
        assert r.locus_tag == locus_tag
        assert r.product == gene.get("product")
        assert r.organism_name == gene.get("organism_name")

    @pytest.mark.asyncio
    async def test_lookup_by_gene_name_dnaN(self, tool_fns, mock_ctx):
        """Looking up 'dnaN' with a single mock result returns the correct gene."""
        gene = GENES_BY_LOCUS["PMM0001"]
        row = as_resolve_gene_result(gene)
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_name", "Unknown"), "count": 1}], "returned": 1, "truncated": False, "results": [row]},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="dnaN")

        assert result.results[0].locus_tag == "PMM0001"
        assert result.results[0].gene_name == "dnaN"

    @pytest.mark.asyncio
    async def test_dnaN_multiple_organisms_flat_list(self, tool_fns, mock_ctx):
        """dnaN exists in MED4 and MIT9312; results are a flat list."""
        med4 = as_resolve_gene_result(GENES_BY_LOCUS["PMM0001"])
        mit9312 = as_resolve_gene_result(GENES_BY_LOCUS["PMT9312_0001"])
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 2, "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}, {"organism_name": "Prochlorococcus MIT9312", "count": 1}], "returned": 2, "truncated": False, "results": [med4, mit9312]},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="dnaN")

        assert result.total_matching == 2
        assert result.returned == 2
        loci = {r.locus_tag for r in result.results}
        assert loci == {"PMM0001", "PMT9312_0001"}
        organisms = {r.organism_name for r in result.results}
        assert "Prochlorococcus MED4" in organisms
        assert "Prochlorococcus MIT9312" in organisms

    @pytest.mark.asyncio
    async def test_lookup_by_identifier_refseq(self, tool_fns, mock_ctx):
        """PMM0446 can be found via RefSeq protein ID WP_011132082.1."""
        gene = GENES_BY_LOCUS["PMM0446"]
        row = as_resolve_gene_result(gene)
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_name", "Unknown"), "count": 1}], "returned": 1, "truncated": False, "results": [row]},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="WP_011132082.1")

        r = result.results[0]
        assert r.locus_tag == "PMM0446"
        assert r.gene_name == "ctaCI"
        assert r.organism_name == gene["organism_name"]

    @pytest.mark.asyncio
    async def test_gene_without_real_gene_name(self, tool_fns, mock_ctx):
        """S8102_04001 has no gene_name field — result shows None."""
        gene = GENES_BY_LOCUS["S8102_04001"]
        row = as_resolve_gene_result(gene)
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_name", "Unknown"), "count": 1}], "returned": 1, "truncated": False, "results": [row]},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="S8102_04001")

        r = result.results[0]
        assert r.locus_tag == "S8102_04001"
        assert r.gene_name is None

    @pytest.mark.asyncio
    async def test_gene_without_gene_name(self, tool_fns, mock_ctx):
        """ALT831_RS00180 has no gene_name (None)."""
        gene = GENES_BY_LOCUS["ALT831_RS00180"]
        row = as_resolve_gene_result(gene)
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_name", "Unknown"), "count": 1}], "returned": 1, "truncated": False, "results": [row]},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="ALT831_RS00180")

        r = result.results[0]
        assert r.gene_name is None

    @pytest.mark.asyncio
    async def test_organism_filter_narrows_results(self, tool_fns, mock_ctx):
        """With organism='MED4', only the MED4 dnaN is returned."""
        med4 = as_resolve_gene_result(GENES_BY_LOCUS["PMM0001"])
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 1, "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}], "returned": 1, "truncated": False, "results": [med4]},
        ):
            result = await tool_fns["resolve_gene"](
                mock_ctx, identifier="dnaN", organism="MED4",
            )

        assert result.total_matching == 1
        assert result.results[0].organism_name == "Prochlorococcus MED4"

    @pytest.mark.asyncio
    async def test_alternate_identifier_lookup(self, tool_fns, mock_ctx):
        """PMM0001 all_identifiers includes TX50_RS00020 (alternate locus tag)."""
        gene = GENES_BY_LOCUS["PMM0001"]
        row = as_resolve_gene_result(gene)
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_name", "Unknown"), "count": 1}], "returned": 1, "truncated": False, "results": [row]},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="TX50_RS00020")

        r = result.results[0]
        assert r.locus_tag == "PMM0001"
        assert r.gene_name == "dnaN"


# ---------------------------------------------------------------------------
# TestGenesByFunctionCorrectness
# ---------------------------------------------------------------------------
class TestGenesByFunctionCorrectness:
    """Verify genes_by_function returns correct data for realistic mock responses."""

    def _make_api_return(self, results, total_matching=None):
        """Helper: build api return dict from result rows."""
        if total_matching is None:
            total_matching = len(results)
        return {
            "total_search_hits": 100,
            "total_matching": total_matching,
            "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": len(results)}],
            "by_category": [{"category": "DNA replication", "count": len(results)}],
            "score_max": results[0]["score"] if results else None,
            "score_median": results[0]["score"] if results else None,
            "returned": len(results),
            "truncated": total_matching > len(results),
            "results": results,
        }

    @pytest.mark.asyncio
    async def test_fulltext_results_with_scores(self, tool_fns, mock_ctx):
        """Results from multiple organisms are returned with Pydantic envelope."""
        rows = [
            as_search_genes_result(GENES_BY_LOCUS["PMM0001"], score=5.2),
            as_search_genes_result(GENES_BY_LOCUS["PMT9312_0001"], score=4.8),
            as_search_genes_result(GENES_BY_LOCUS["SYNW0305"], score=2.1),
        ]
        api_return = self._make_api_return(rows)
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            return_value=api_return,
        ):
            result = await tool_fns["genes_by_function"](
                mock_ctx, search_text="DNA polymerase",
            )

        assert result.total_matching == 3
        assert result.returned == 3
        loci = [r.locus_tag for r in result.results]
        assert loci == ["PMM0001", "PMT9312_0001", "SYNW0305"]

    @pytest.mark.asyncio
    async def test_organism_filter_forwarded(self, tool_fns, mock_ctx):
        """Organism filter passes through to the api function."""
        rows = [as_search_genes_result(GENES_BY_LOCUS["SYNW0305"], score=3.0)]
        api_return = self._make_api_return(rows)
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            return_value=api_return,
        ) as mock_api:
            await tool_fns["genes_by_function"](
                mock_ctx, search_text="metallopeptidase", organism="WH8102",
            )

        assert mock_api.call_args.kwargs["organism"] == "WH8102"

    @pytest.mark.asyncio
    async def test_quality_filter_forwarded(self, tool_fns, mock_ctx):
        """min_quality=2 is passed through to the api function."""
        rows = [as_search_genes_result(GENES_BY_LOCUS["PMM0001"], score=5.0)]
        api_return = self._make_api_return(rows)
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            return_value=api_return,
        ) as mock_api:
            await tool_fns["genes_by_function"](
                mock_ctx, search_text="polymerase", min_quality=2,
            )

        assert mock_api.call_args.kwargs["min_quality"] == 2

    @pytest.mark.asyncio
    async def test_result_envelope_shape(self, tool_fns, mock_ctx):
        """Result envelope contains all expected fields."""
        rows = [as_search_genes_result(GENES_BY_LOCUS["PMN2A_0044"], score=4.0)]
        api_return = self._make_api_return(rows)
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            return_value=api_return,
        ):
            result = await tool_fns["genes_by_function"](
                mock_ctx, search_text="naphthoate synthase",
            )

        assert hasattr(result, "total_search_hits")
        assert hasattr(result, "total_matching")
        assert hasattr(result, "by_organism")
        assert hasattr(result, "by_category")
        assert hasattr(result, "score_max")
        assert hasattr(result, "score_median")
        assert hasattr(result, "returned")
        assert hasattr(result, "truncated")
        assert hasattr(result, "results")
        assert result.total_matching == 1
        assert result.results[0].locus_tag == "PMN2A_0044"


# ---------------------------------------------------------------------------
# TestGetGeneDetailsCorrectness
# ---------------------------------------------------------------------------
class TestGeneDetailsCorrectness:
    """Verify gene_details returns flat g{.*} properties correctly."""

    @pytest.mark.asyncio
    async def test_well_annotated_prochlorococcus(self, tool_fns, mock_ctx):
        """PMM0001 returns flat gene properties via g{.*}."""
        gene_data = {
            "locus_tag": "PMM0001",
            "gene_name": "dnaN",
            "product": "DNA polymerase III, beta subunit",
            "organism_name": "Prochlorococcus MED4",
            "gene_category": "DNA replication",
            "annotation_quality": 3,
            "ec_numbers": ["2.7.7.7"],
        }
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [{"total_matching": 1, "not_found": []}],  # summary
            [{"gene": gene_data}],  # detail
        ]

        result = await tool_fns["gene_details"](mock_ctx, locus_tags=["PMM0001"])

        assert result.total_matching == 1
        assert result.returned == 1
        r = result.results[0]
        assert r["locus_tag"] == "PMM0001"
        assert r["gene_name"] == "dnaN"
        assert r["organism_name"] == "Prochlorococcus MED4"

    @pytest.mark.asyncio
    async def test_alteromonas_gene_eggnog_only(self, tool_fns, mock_ctx):
        """ALT831_RS00180 returns flat properties."""
        gene_data = {
            "locus_tag": "ALT831_RS00180",
            "gene_name": None,
            "product": "IS630 family transposase",
            "organism_name": "Alteromonas macleodii MIT1002",
            "annotation_quality": 2,
        }
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [{"total_matching": 1, "not_found": []}],  # summary
            [{"gene": gene_data}],  # detail
        ]

        result = await tool_fns["gene_details"](mock_ctx, locus_tags=["ALT831_RS00180"])

        assert result.total_matching == 1
        r = result.results[0]
        assert r["locus_tag"] == "ALT831_RS00180"
        assert r["organism_name"] == "Alteromonas macleodii MIT1002"


# ---------------------------------------------------------------------------
# TestGeneOverviewCorrectness
# ---------------------------------------------------------------------------
class TestGeneOverviewCorrectness:
    """Verify gene_overview returns correct data for realistic mock responses."""

    _SAMPLE_API_RETURN = {
        "total_matching": 1,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
        "by_category": [{"category": "Photosynthesis", "count": 1}],
        "by_annotation_type": [{"annotation_type": "go_mf", "count": 1},
                               {"annotation_type": "pfam", "count": 1}],
        "has_expression": 1,
        "has_significant_expression": 1,
        "has_orthologs": 1,
        "has_clusters": 1,
        "returned": 1,
        "truncated": False,
        "not_found": [],
        "results": [
            {"locus_tag": "PMM1428", "gene_name": "test", "product": "test product",
             "gene_category": "Photosynthesis", "annotation_quality": 3,
             "organism_name": "Prochlorococcus MED4",
             "annotation_types": ["go_mf", "pfam", "cog_category", "tigr_role"],
             "expression_edge_count": 36, "significant_up_count": 3, "significant_down_count": 2,
             "closest_ortholog_group_size": 9,
             "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
             "cluster_membership_count": 2, "cluster_types": ["condition_comparison"]},
        ],
    }

    @pytest.mark.asyncio
    async def test_single_gene_overview(self, tool_fns, mock_ctx):
        """Mock single gene row with all 11 compact columns, verify Pydantic response."""
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["gene_overview"](mock_ctx, locus_tags=["PMM1428"])

        assert result.total_matching == 1
        assert len(result.results) == 1
        r = result.results[0]
        assert r.locus_tag == "PMM1428"
        assert r.expression_edge_count == 36
        assert r.annotation_types == ["go_mf", "pfam", "cog_category", "tigr_role"]

    @pytest.mark.asyncio
    async def test_batch_overview(self, tool_fns, mock_ctx):
        """Mock multiple gene rows, verify all returned."""
        batch_return = {
            **self._SAMPLE_API_RETURN,
            "total_matching": 2,
            "returned": 2,
            "results": [
                {"locus_tag": "PMM1428", "gene_name": "a", "product": "p1",
                 "gene_category": None, "annotation_quality": 3,
                 "organism_name": "Prochlorococcus MED4",
                 "annotation_types": ["go_mf"], "expression_edge_count": 36,
                 "significant_up_count": 3, "significant_down_count": 2, "closest_ortholog_group_size": 9,
                 "closest_ortholog_genera": ["Prochlorococcus"],
                 "cluster_membership_count": 1, "cluster_types": ["diel"]},
                {"locus_tag": "EZ55_00275", "gene_name": None, "product": "p2",
                 "gene_category": None, "annotation_quality": 0,
                 "organism_name": "Alteromonas EZ55",
                 "annotation_types": [], "expression_edge_count": 0,
                 "significant_up_count": 0, "significant_down_count": 0, "closest_ortholog_group_size": 1,
                 "closest_ortholog_genera": [],
                 "cluster_membership_count": 0, "cluster_types": []},
            ],
        }
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=batch_return,
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=["PMM1428", "EZ55_00275"],
            )

        assert result.total_matching == 2
        assert len(result.results) == 2
        loci = {r.locus_tag for r in result.results}
        assert loci == {"PMM1428", "EZ55_00275"}

    @pytest.mark.asyncio
    async def test_annotation_types_preserved(self, tool_fns, mock_ctx):
        """List field preserved in Pydantic response."""
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["gene_overview"](mock_ctx, locus_tags=["PMM1428"])

        assert isinstance(result.results[0].annotation_types, list)
        assert "go_mf" in result.results[0].annotation_types



# ---------------------------------------------------------------------------
# TestGeneHomologsCorrectness
# ---------------------------------------------------------------------------
class TestGeneHomologsCorrectness:
    """Verify gene_homologs returns correct flat long-format data."""

    _SAMPLE_SUMMARY = {
        "total_matching": 3,
        "by_organism": [{"item": "Prochlorococcus MED4", "count": 3}],
        "by_source": [{"item": "cyanorak", "count": 1}, {"item": "eggnog", "count": 2}],
        "not_found": [],
        "no_groups": [],
    }

    _SAMPLE_RESULTS = [
        {"locus_tag": "PMM0001", "organism_name": "Prochlorococcus MED4",
         "group_id": "cyanorak:CK_00000364", "consensus_gene_name": "dnaN",
         "consensus_product": "DNA polymerase III, beta subunit",
         "taxonomic_level": "curated", "source": "cyanorak",
         "specificity_rank": 0},
        {"locus_tag": "PMM0001", "organism_name": "Prochlorococcus MED4",
         "group_id": "eggnog:COG0592@2", "consensus_gene_name": "dnaN",
         "consensus_product": "DNA polymerase III, beta subunit",
         "taxonomic_level": "Bacteria", "source": "eggnog",
         "specificity_rank": 3},
    ]

    @pytest.mark.asyncio
    async def test_flat_format_has_compact_columns(self, tool_fns, mock_ctx):
        """Each result row has compact columns."""
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            return_value={
                **self._SAMPLE_SUMMARY,
                "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 3}],
                "by_source": [{"source": "cyanorak", "count": 1}, {"source": "eggnog", "count": 2}],
                "returned": 2, "truncated": True, "results": self._SAMPLE_RESULTS,
            },
        ):
            result = await tool_fns["gene_homologs"](mock_ctx, locus_tags=["PMM0001"])
        assert len(result.results) == 2
        r = result.results[0]
        assert r.locus_tag == "PMM0001"
        assert r.group_id == "cyanorak:CK_00000364"
        assert r.source == "cyanorak"
        assert r.consensus_product == "DNA polymerase III, beta subunit"

    @pytest.mark.asyncio
    async def test_batch_input_multiple_genes(self, tool_fns, mock_ctx):
        """Batch query returns rows for multiple genes."""
        batch_results = self._SAMPLE_RESULTS + [
            {"locus_tag": "PMM0845", "organism_name": "Prochlorococcus MED4",
             "group_id": "cyanorak:CK_00000853", "consensus_gene_name": "ndhV",
             "consensus_product": "NADH dehydrogenase subunit NdhV",
             "taxonomic_level": "curated", "source": "cyanorak",
             "specificity_rank": 0},
        ]
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            return_value={
                "total_matching": 3,
                "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 3}],
                "by_source": [{"source": "cyanorak", "count": 2}, {"source": "eggnog", "count": 1}],
                "not_found": [], "no_groups": [],
                "returned": 3, "truncated": False, "results": batch_results,
            },
        ):
            result = await tool_fns["gene_homologs"](
                mock_ctx, locus_tags=["PMM0001", "PMM0845"],
            )
        loci = {r.locus_tag for r in result.results}
        assert loci == {"PMM0001", "PMM0845"}

    @pytest.mark.asyncio
    async def test_not_found_and_no_groups(self, tool_fns, mock_ctx):
        """not_found and no_groups are populated correctly."""
        with patch(
            "multiomics_explorer.api.functions.gene_homologs",
            return_value={
                "total_matching": 0,
                "by_organism": [], "by_source": [],
                "not_found": ["FAKE_GENE"], "no_groups": ["A9601_RS13285"],
                "returned": 0, "truncated": False, "results": [],
            },
        ):
            result = await tool_fns["gene_homologs"](
                mock_ctx, locus_tags=["FAKE_GENE", "A9601_RS13285"],
            )
        assert result.not_found == ["FAKE_GENE"]
        assert result.no_groups == ["A9601_RS13285"]
        assert result.results == []


# ---------------------------------------------------------------------------
# TestSearchOntologyCorrectness
# ---------------------------------------------------------------------------
class TestSearchOntologyCorrectness:
    """Verify search_ontology returns correct data for realistic mock responses."""

    @pytest.mark.asyncio
    async def test_go_bp_search_returns_terms(self, tool_fns, mock_ctx):
        """GO BP search returns term IDs and names."""
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={
                "total_entries": 2448,
                "total_matching": 31,
                "score_max": 5.23,
                "score_median": 2.1,
                "returned": 3,
                "truncated": True,
                "results": [
                    {"id": "go:0006260", "name": "DNA replication", "score": 5.23, "level": 5},
                    {"id": "go:0006261", "name": "DNA-templated DNA replication", "score": 4.1, "level": 6},
                    {"id": "go:0006270", "name": "DNA replication initiation", "score": 2.1, "level": 6},
                ],
            },
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="replication", ontology="go_bp",
            )

        assert result.total_entries == 2448
        assert result.total_matching == 31
        assert result.returned == 3
        assert result.truncated is True
        assert result.score_max == 5.23
        assert result.score_median == 2.1
        assert len(result.results) == 3
        assert result.results[0].id == "go:0006260"
        assert result.results[0].name == "DNA replication"

    @pytest.mark.asyncio
    async def test_summary_mode_empty_results(self, tool_fns, mock_ctx):
        """Summary mode returns counts with results=[]."""
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={
                "total_entries": 847,
                "total_matching": 12,
                "score_max": 3.5,
                "score_median": 1.8,
                "returned": 0,
                "truncated": True,
                "results": [],
            },
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="transport", ontology="go_bp", summary=True,
            )

        assert result.returned == 0
        assert result.truncated is True
        assert result.results == []
        assert result.total_matching == 12

    @pytest.mark.asyncio
    async def test_zero_matches(self, tool_fns, mock_ctx):
        """No matches returns score_max=None, score_median=None."""
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={
                "total_entries": 500,
                "total_matching": 0,
                "score_max": None,
                "score_median": None,
                "returned": 0,
                "truncated": False,
                "results": [],
            },
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="xyznonexistent", ontology="ec",
            )

        assert result.total_matching == 0
        assert result.score_max is None
        assert result.score_median is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ontology", [
        "go_bp", "go_mf", "go_cc", "kegg", "ec",
        "cog_category", "cyanorak_role", "tigr_role", "pfam",
    ])
    async def test_all_ontologies_accepted(self, tool_fns, mock_ctx, ontology):
        """Each valid ontology value is accepted without error."""
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={
                "total_entries": 100, "total_matching": 1,
                "score_max": 1.0, "score_median": 1.0,
                "returned": 1, "truncated": False,
                "results": [{"id": "test:001", "name": "test term", "score": 1.0, "level": 2}],
            },
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="test", ontology=ontology,
            )
        assert result.total_matching == 1

    @pytest.mark.asyncio
    async def test_level_in_result_rows(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={
                "total_entries": 100, "total_matching": 1,
                "score_max": 3.0, "score_median": 3.0,
                "returned": 1, "truncated": False,
                "results": [
                    {"id": "go:0006260", "name": "DNA replication", "score": 3.0, "level": 5},
                ],
            },
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="replication", ontology="go_bp",
            )
        assert result.results[0].level == 5

    @pytest.mark.asyncio
    async def test_brite_result_has_tree(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={
                "total_entries": 100, "total_matching": 1,
                "score_max": 3.0, "score_median": 3.0,
                "returned": 1, "truncated": False,
                "results": [
                    {"id": "kegg.brite:ko02000.A5", "name": "PTS", "score": 3.0,
                     "level": 0, "tree": "transporters", "tree_code": "ko02000"},
                ],
            },
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="PTS", ontology="brite",
            )
        assert result.results[0].tree == "transporters"
        assert result.results[0].tree_code == "ko02000"

    @pytest.mark.asyncio
    async def test_non_brite_result_no_tree(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.search_ontology",
            return_value={
                "total_entries": 100, "total_matching": 1,
                "score_max": 3.0, "score_median": 3.0,
                "returned": 1, "truncated": False,
                "results": [
                    {"id": "go:0006260", "name": "DNA replication", "score": 3.0, "level": 5},
                ],
            },
        ):
            result = await tool_fns["search_ontology"](
                mock_ctx, search_text="replication", ontology="go_bp",
            )
        assert result.results[0].tree is None
        assert result.results[0].tree_code is None


# ---------------------------------------------------------------------------
# TestGenesByOntologyCorrectness
# ---------------------------------------------------------------------------
class TestGenesByOntologyCorrectness:
    """Verify genes_by_ontology returns correct data for realistic mock responses."""

    _EMPTY_ENVELOPE = {
        "ontology": "go_bp",
        "organism_name": "Prochlorococcus MED4",
        "total_matching": 0,
        "total_genes": 0,
        "total_terms": 0,
        "total_categories": 0,
        "genes_per_term_min": 0,
        "genes_per_term_median": 0.0,
        "genes_per_term_max": 0,
        "terms_per_gene_min": 0,
        "terms_per_gene_median": 0.0,
        "terms_per_gene_max": 0,
        "by_category": [],
        "by_level": [],
        "top_terms": [],
        "n_best_effort_terms": 0,
        "not_found": [],
        "wrong_ontology": [],
        "wrong_level": [],
        "filtered_out": [],
        "returned": 0,
        "offset": 0,
        "truncated": False,
        "results": [],
    }

    @pytest.mark.asyncio
    async def test_single_term_returns_genes(self, tool_fns, mock_ctx):
        """Single GO term returns annotated (gene × term) rows."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value={
                **self._EMPTY_ENVELOPE,
                "total_matching": 2,
                "total_genes": 2,
                "total_terms": 1,
                "total_categories": 1,
                "genes_per_term_min": 2,
                "genes_per_term_median": 2.0,
                "genes_per_term_max": 2,
                "terms_per_gene_min": 1,
                "terms_per_gene_median": 1.0,
                "terms_per_gene_max": 1,
                "by_category": [{"category": "DNA replication", "count": 2}],
                "by_level": [
                    {"level": 3, "n_terms": 1, "n_genes": 2, "row_count": 2},
                ],
                "top_terms": [{"term_id": "go:0006260",
                               "term_name": "DNA replication", "count": 2}],
                "returned": 2,
                "truncated": False,
                "results": [
                    {"locus_tag": "PMM0001", "gene_name": "dnaN",
                     "product": "DNA polymerase III, beta subunit",
                     "gene_category": "DNA replication",
                     "term_id": "go:0006260",
                     "term_name": "DNA replication", "level": 3},
                    {"locus_tag": "PMM0845", "gene_name": None,
                     "product": "hypothetical protein",
                     "gene_category": None,
                     "term_id": "go:0006260",
                     "term_name": "DNA replication", "level": 3},
                ],
            },
        ):
            result = await tool_fns["genes_by_ontology"](
                mock_ctx, ontology="go_bp", organism="Prochlorococcus MED4",
                term_ids=["go:0006260"],
            )

        assert result.total_matching == 2
        assert result.returned == 2
        loci = {r.locus_tag for r in result.results}
        assert loci == {"PMM0001", "PMM0845"}

    @pytest.mark.asyncio
    async def test_zero_match_empty_response(self, tool_fns, mock_ctx):
        """Zero matches return empty results."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value=self._EMPTY_ENVELOPE,
        ):
            result = await tool_fns["genes_by_ontology"](
                mock_ctx, ontology="go_bp", organism="Prochlorococcus MED4",
                term_ids=["go:9999999"],
            )

        assert result.total_matching == 0
        assert result.results == []

    @pytest.mark.asyncio
    async def test_summary_mode(self, tool_fns, mock_ctx):
        """Summary mode returns breakdowns with results=[]."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_ontology",
            return_value={
                **self._EMPTY_ENVELOPE,
                "total_matching": 15,
                "total_genes": 15,
                "total_terms": 1,
                "total_categories": 1,
                "genes_per_term_min": 15,
                "genes_per_term_median": 15.0,
                "genes_per_term_max": 15,
                "terms_per_gene_min": 1,
                "terms_per_gene_median": 1.0,
                "terms_per_gene_max": 1,
                "by_category": [{"category": "Transport", "count": 10}],
                "top_terms": [{"term_id": "go:0006810",
                               "term_name": "transport", "count": 15}],
                "returned": 0,
                "truncated": True,
            },
        ):
            result = await tool_fns["genes_by_ontology"](
                mock_ctx, ontology="go_bp", organism="Prochlorococcus MED4",
                term_ids=["go:0006810"], summary=True,
            )

        assert result.returned == 0
        assert result.truncated is True
        assert result.total_matching == 15


# ---------------------------------------------------------------------------
# TestGeneOntologyTermsCorrectness
# ---------------------------------------------------------------------------
class TestGeneOntologyTermsCorrectness:
    """Verify gene_ontology_terms returns correct ontology annotations for genes."""

    @pytest.mark.asyncio
    async def test_single_gene_returns_terms(self, tool_fns, mock_ctx):
        """Single gene returns its ontology term annotations."""
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value={
                "total_matching": 3,
                "total_genes": 1,
                "total_terms": 3,
                "by_ontology": [
                    {"ontology_type": "go_bp", "term_count": 2, "gene_count": 1},
                    {"ontology_type": "go_mf", "term_count": 1, "gene_count": 1},
                ],
                "by_term": [
                    {"term_id": "go:0006260", "term_name": "DNA replication",
                     "level": 5, "ontology_type": "go_bp", "count": 1},
                ],
                "terms_per_gene_min": 3,
                "terms_per_gene_max": 3,
                "terms_per_gene_median": 3.0,
                "returned": 3,
                "truncated": False,
                "not_found": [],
                "results": [
                    {"locus_tag": "PMM0001", "term_id": "go:0006260",
                     "term_name": "DNA replication", "level": 5, "ontology_type": "go_bp"},
                    {"locus_tag": "PMM0001", "term_id": "go:0006261",
                     "term_name": "DNA-templated DNA replication", "level": 6, "ontology_type": "go_bp"},
                    {"locus_tag": "PMM0001", "term_id": "go:0003887",
                     "term_name": "DNA-directed DNA polymerase activity", "level": 4, "ontology_type": "go_mf"},
                ],
            },
        ):
            result = await tool_fns["gene_ontology_terms"](
                mock_ctx, locus_tags=["PMM0001"], organism="MED4",
            )

        assert result.total_matching == 3
        assert result.returned == 3
        assert len(result.results) == 3
        assert result.results[0].locus_tag == "PMM0001"
        assert result.results[0].term_id == "go:0006260"
        assert len(result.by_ontology) == 2

    @pytest.mark.asyncio
    async def test_batch_genes(self, tool_fns, mock_ctx):
        """Batch query returns terms for multiple genes."""
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value={
                "total_matching": 4,
                "total_genes": 2,
                "total_terms": 4,
                "by_ontology": [{"ontology_type": "go_bp", "term_count": 4, "gene_count": 2}],
                "by_term": [],
                "terms_per_gene_min": 2,
                "terms_per_gene_max": 2,
                "terms_per_gene_median": 2.0,
                "returned": 4,
                "truncated": False,
                "not_found": [],
                "results": [
                    {"locus_tag": "PMM0001", "term_id": "go:0006260",
                     "term_name": "DNA replication", "level": 5, "ontology_type": "go_bp"},
                    {"locus_tag": "PMM0001", "term_id": "go:0006261",
                     "term_name": "DNA-templated DNA replication", "level": 6, "ontology_type": "go_bp"},
                    {"locus_tag": "PMM0845", "term_id": "go:0015979",
                     "term_name": "photosynthesis", "level": 3, "ontology_type": "go_bp"},
                    {"locus_tag": "PMM0845", "term_id": "go:0009765",
                     "term_name": "photosynthesis, light harvesting", "level": 4, "ontology_type": "go_bp"},
                ],
            },
        ):
            result = await tool_fns["gene_ontology_terms"](
                mock_ctx, locus_tags=["PMM0001", "PMM0845"], organism="MED4",
            )

        loci = {r.locus_tag for r in result.results}
        assert loci == {"PMM0001", "PMM0845"}

    @pytest.mark.asyncio
    async def test_not_found_genes(self, tool_fns, mock_ctx):
        """Fake genes appear in not_found."""
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value={
                "total_matching": 0,
                "total_genes": 0,
                "total_terms": 0,
                "by_ontology": [], "by_term": [],
                "terms_per_gene_min": 0,
                "terms_per_gene_max": 0,
                "terms_per_gene_median": 0.0,
                "returned": 0,
                "truncated": False,
                "not_found": ["FAKE_GENE"],
                "results": [],
            },
        ):
            result = await tool_fns["gene_ontology_terms"](
                mock_ctx, locus_tags=["FAKE_GENE"], organism="MED4",
            )

        assert result.not_found == ["FAKE_GENE"]
        assert result.results == []

    @pytest.mark.asyncio
    async def test_level_in_result_rows(self, tool_fns, mock_ctx):
        """Result rows include level field."""
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            return_value={
                "total_matching": 1,
                "total_genes": 1,
                "total_terms": 1,
                "by_ontology": [{"ontology_type": "go_bp", "term_count": 1, "gene_count": 1}],
                "by_term": [
                    {"term_id": "go:0006260", "term_name": "DNA replication",
                     "level": 5, "ontology_type": "go_bp", "count": 1},
                ],
                "terms_per_gene_min": 1,
                "terms_per_gene_max": 1,
                "terms_per_gene_median": 1.0,
                "returned": 1,
                "truncated": False,
                "not_found": [],
                "results": [
                    {"locus_tag": "PMM0001", "term_id": "go:0006260",
                     "term_name": "DNA replication", "level": 5, "ontology_type": "go_bp"},
                ],
            },
        ):
            result = await tool_fns["gene_ontology_terms"](
                mock_ctx, locus_tags=["PMM0001"], organism="MED4",
            )

        assert result.results[0].level == 5
        assert result.by_term[0].level == 5

    @pytest.mark.asyncio
    async def test_mode_rollup_without_level_raises(self, tool_fns, mock_ctx):
        """Rollup mode without level raises ToolError."""
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            side_effect=ValueError("level is required when mode='rollup'"),
        ):
            with pytest.raises(ToolError, match="level is required"):
                await tool_fns["gene_ontology_terms"](
                    mock_ctx, locus_tags=["PMM0001"], organism="MED4",
                    mode="rollup",
                )

    @pytest.mark.asyncio
    async def test_tree_with_non_brite_raises(self, tool_fns, mock_ctx):
        """Tree filter with non-brite ontology raises ToolError."""
        with patch(
            "multiomics_explorer.api.functions.gene_ontology_terms",
            side_effect=ValueError("tree filter is only valid for ontology='brite'"),
        ):
            with pytest.raises(ToolError, match="tree filter is only valid"):
                await tool_fns["gene_ontology_terms"](
                    mock_ctx, locus_tags=["PMM0001"], organism="MED4",
                    ontology="go_bp", tree="Enzymes",
                )


# ---------------------------------------------------------------------------
# TestListPublicationsCorrectness
# ---------------------------------------------------------------------------
class TestListPublicationsCorrectness:
    """Verify list_publications returns correct data."""

    @pytest.mark.asyncio
    async def test_returns_publications(self, tool_fns, mock_ctx):
        """Publications returned with experiment summaries."""
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 12,
                "total_matching": 2,
                "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
                "by_treatment_type": [{"treatment_type": "coculture", "count": 1}],
                "by_background_factors": [],
                "by_omics_type": [{"omics_type": "RNASEQ", "count": 2}],
                "returned": 2,
                "truncated": False,
                "results": [
                    {"doi": "10.1038/ismej.2016.70", "title": "Test paper 1",
                     "authors": ["Smith A", "Jones B"], "year": 2016,
                     "journal": "ISME Journal",
                     "organisms": ["Prochlorococcus MED4"],
                     "experiment_count": 5,
                     "treatment_types": ["coculture"],
                     "background_factors": [],
                     "omics_types": ["RNASEQ"]},
                    {"doi": "10.1111/test.2020", "title": "Test paper 2",
                     "authors": ["Jones C"], "year": 2020,
                     "journal": "Nature",
                     "organisms": ["Prochlorococcus MIT9312"],
                     "experiment_count": 3,
                     "treatment_types": ["nitrogen_stress"],
                     "background_factors": [],
                     "omics_types": ["PROTEOMICS"]},
                ],
            },
        ):
            result = await tool_fns["list_publications"](mock_ctx)

        assert result.total_entries == 12
        assert result.total_matching == 2
        assert result.returned == 2
        assert len(result.results) == 2
        assert result.results[0].doi == "10.1038/ismej.2016.70"
        assert result.results[0].experiment_count == 5
        assert result.results[0].authors == ["Smith A", "Jones B"]

    @pytest.mark.asyncio
    async def test_organism_filter(self, tool_fns, mock_ctx):
        """Organism filter forwarded to API."""
        with patch(
            "multiomics_explorer.api.functions.list_publications",
            return_value={
                "total_entries": 12, "total_matching": 1,
                "by_organism": [], "by_treatment_type": [], "by_background_factors": [], "by_omics_type": [],
                "returned": 1, "truncated": False,
                "results": [
                    {"doi": "10.1038/ismej.2016.70", "title": "Test",
                     "authors": ["Smith A"], "year": 2016,
                     "journal": "ISME Journal",
                     "organisms": ["Prochlorococcus MED4"],
                     "experiment_count": 5,
                     "treatment_types": ["coculture"],
                     "background_factors": [],
                     "omics_types": ["RNASEQ"]},
                ],
            },
        ) as mock_api:
            await tool_fns["list_publications"](mock_ctx, organism="MED4")

        assert mock_api.call_args.kwargs["organism"] == "MED4"


# ---------------------------------------------------------------------------
# TestListExperimentsCorrectness
# ---------------------------------------------------------------------------
class TestListExperimentsCorrectness:
    """Verify list_experiments returns correct data with realistic mock responses."""

    @classmethod
    def _make_api_return(cls):
        """Return a fresh deep copy of the sample API return to avoid .pop() mutation."""
        import copy
        return copy.deepcopy(cls._SAMPLE_API_RETURN_TEMPLATE)

    _SAMPLE_API_RETURN_TEMPLATE = {
        "total_entries": 76,
        "total_matching": 2,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 2}],
        "by_treatment_type": [{"treatment_type": "coculture", "count": 1},
                               {"treatment_type": "light_stress", "count": 1}],
        "by_background_factors": [],
        "by_omics_type": [{"omics_type": "RNASEQ", "count": 2}],
        "by_publication": [{"publication_doi": "10.1038/test", "count": 2}],
        "by_table_scope": [{"table_scope": "all_detected_genes", "count": 2}],
        "by_cluster_type": [],
        "by_growth_phase": [{"growth_phase": "exponential", "count": 2}],
        "time_course_count": 1,
        "score_max": None,
        "score_median": None,
        "returned": 2,
        "truncated": False,
        "results": [
            {"experiment_id": "exp_001",
             "experiment_name": "MED4 Coculture",
             "publication_doi": "10.1038/test",
             "organism_name": "Prochlorococcus MED4",
             "treatment_type": ["coculture"],
             "background_factors": [],
             "coculture_partner": "Alteromonas HOT1A3",
             "omics_type": "RNASEQ",
             "is_time_course": False,
             "table_scope": "all_detected_genes",
             "table_scope_detail": None,
             "gene_count": 1696,
             "distinct_gene_count": 1696,
             "growth_phases": ["exponential"],
             "time_point_growth_phases": [],
             "genes_by_status": {"significant_up": 245, "significant_down": 178, "not_significant": 1273}},
            {"experiment_id": "exp_002",
             "experiment_name": "MED4 Light Stress Time Course",
             "publication_doi": "10.1038/test",
             "organism_name": "Prochlorococcus MED4",
             "treatment_type": ["light_stress"],
             "background_factors": [],
             "coculture_partner": None,
             "omics_type": "RNASEQ",
             "is_time_course": True,
             "table_scope": "all_detected_genes",
             "table_scope_detail": None,
             "gene_count": 3392,
             "distinct_gene_count": 1696,
             "growth_phases": ["exponential"],
             "time_point_growth_phases": ["exponential", "exponential"],
             "genes_by_status": {"significant_up": 450, "significant_down": 320, "not_significant": 926},
             "timepoints": [
                 {"timepoint": "2h", "timepoint_order": 1, "timepoint_hours": 2.0,
                  "gene_count": 1696,
                  "genes_by_status": {"significant_up": 50, "significant_down": 30, "not_significant": 1616}},
                 {"timepoint": "24h", "timepoint_order": 2, "timepoint_hours": 24.0,
                  "gene_count": 1696,
                  "genes_by_status": {"significant_up": 400, "significant_down": 290, "not_significant": 1006}},
             ]},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_experiments_with_breakdowns(self, tool_fns, mock_ctx):
        """Full response with experiments and breakdowns."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_api_return(),
        ):
            result = await tool_fns["list_experiments"](mock_ctx)

        assert result.total_entries == 76
        assert result.total_matching == 2
        assert result.returned == 2
        assert len(result.results) == 2
        assert result.results[0].experiment_id == "exp_001"
        assert result.results[0].treatment_type == ["coculture"]
        assert result.results[0].table_scope == "all_detected_genes"
        assert len(result.by_table_scope) == 1

    @pytest.mark.asyncio
    async def test_time_course_experiment_has_timepoints(self, tool_fns, mock_ctx):
        """Time-course experiment has timepoints list."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_api_return(),
        ):
            result = await tool_fns["list_experiments"](mock_ctx)

        tc = result.results[1]
        assert tc.is_time_course is True
        assert len(tc.timepoints) == 2
        assert tc.timepoints[0].timepoint == "2h"
        assert tc.timepoints[1].genes_by_status.significant_up == 400

    @pytest.mark.asyncio
    async def test_growth_phases_in_experiment_result(self, tool_fns, mock_ctx):
        """ExperimentResult includes growth_phases and by_growth_phase breakdown."""
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value=self._make_api_return(),
        ):
            result = await tool_fns["list_experiments"](mock_ctx)

        # growth_phases on the experiment result
        assert result.results[0].growth_phases == ["exponential"]
        assert result.results[1].growth_phases == ["exponential"]
        assert result.results[1].time_point_growth_phases == ["exponential", "exponential"]
        # by_growth_phase breakdown on the response envelope
        assert len(result.by_growth_phase) == 1
        assert result.by_growth_phase[0].growth_phase == "exponential"
        assert result.by_growth_phase[0].count == 2


# ---------------------------------------------------------------------------
# TestDiffExprByGeneCorrectness
# ---------------------------------------------------------------------------
class TestDiffExprByGeneCorrectness:
    """Verify differential_expression_by_gene returns correct data."""

    @pytest.mark.asyncio
    async def test_single_gene_expression(self, tool_fns, mock_ctx):
        """Gene-centric DE returns rows per gene × experiment × timepoint."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value={
                "organism_name": "Prochlorococcus MED4",
                "matching_genes": 1,
                "total_matching": 3,
                "rows_by_status": {"significant_up": 1, "significant_down": 1, "not_significant": 1},
                "median_abs_log2fc": 1.2,
                "max_abs_log2fc": 3.5,
                "experiment_count": 2,
                "rows_by_treatment_type": {"coculture": 2, "light_stress": 1},
                "rows_by_background_factors": {},
                "rows_by_growth_phase": {"exponential": 3},
                "by_table_scope": {"all_detected_genes": 3},
                "top_categories": [{"category": "DNA replication", "total_genes": 1, "significant_genes": 1}],
                "experiments": [
                    {"experiment_id": "exp1", "experiment_name": "Coculture",
                     "treatment_type": ["coculture"], "background_factors": [], "omics_type": "RNASEQ",
                     "coculture_partner": None, "is_time_course": "true",
                     "table_scope": "all_detected_genes",
                     "matching_genes": 1,
                     "rows_by_status": {"significant_up": 1, "significant_down": 1, "not_significant": 0},
                     "total_rows": 2, "significant_rows": 1,
                     "timepoints": [
                         {"timepoint": "2h", "timepoint_hours": 2.0,
                          "timepoint_order": 1, "matching_genes": 1,
                          "rows_by_status": {"significant_up": 1, "significant_down": 0, "not_significant": 0},
                          "total_rows": 1, "significant_rows": 1},
                     ]},
                ],
                "not_found": [],
                "no_expression": [],
                "returned": 3,
                "truncated": False,
                "results": [
                    {"locus_tag": "PMM0001", "experiment_id": "exp1",
                     "timepoint": "2h", "timepoint_hours": 2.0, "timepoint_order": 1,
                     "log2fc": 2.5, "padj": 0.001, "rank": 1,
                     "expression_status": "significant_up",
                     "growth_phase": "exponential",
                     "gene_name": "dnaN", "treatment_type": ["coculture"],
                     "gene_category": "DNA replication"},
                    {"locus_tag": "PMM0001", "experiment_id": "exp1",
                     "timepoint": "24h", "timepoint_hours": 24.0, "timepoint_order": 2,
                     "log2fc": -1.8, "padj": 0.01, "rank": 2,
                     "expression_status": "significant_down",
                     "growth_phase": "exponential",
                     "gene_name": "dnaN", "treatment_type": ["coculture"],
                     "gene_category": "DNA replication"},
                    {"locus_tag": "PMM0001", "experiment_id": "exp2",
                     "timepoint": None, "timepoint_hours": None, "timepoint_order": 1,
                     "log2fc": 0.3, "padj": 0.45, "rank": 1,
                     "expression_status": "not_significant",
                     "growth_phase": "exponential",
                     "gene_name": "dnaN", "treatment_type": ["light_stress"],
                     "gene_category": "DNA replication"},
                ],
            },
        ):
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, locus_tags=["PMM0001"],
            )

        assert result.organism_name == "Prochlorococcus MED4"
        assert result.matching_genes == 1
        assert result.total_matching == 3
        assert result.returned == 3
        assert len(result.results) == 3
        r = result.results[0]
        assert r.locus_tag == "PMM0001"
        assert r.log2fc == 2.5
        assert r.expression_status == "significant_up"

    @pytest.mark.asyncio
    async def test_growth_phase_in_expression_row(self, tool_fns, mock_ctx):
        """ExpressionRow includes growth_phase and response has rows_by_growth_phase."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value={
                "organism_name": "Prochlorococcus MED4",
                "matching_genes": 1,
                "total_matching": 1,
                "rows_by_status": {"significant_up": 1, "significant_down": 0, "not_significant": 0},
                "median_abs_log2fc": 2.5,
                "max_abs_log2fc": 2.5,
                "experiment_count": 1,
                "rows_by_treatment_type": {"coculture": 1},
                "rows_by_background_factors": {},
                "rows_by_growth_phase": {"exponential": 1},
                "by_table_scope": {"all_detected_genes": 1},
                "top_categories": [],
                "experiments": [
                    {"experiment_id": "exp1", "experiment_name": "Test",
                     "treatment_type": ["coculture"], "background_factors": [], "omics_type": "RNASEQ",
                     "coculture_partner": None, "is_time_course": "false",
                     "table_scope": "all_detected_genes",
                     "matching_genes": 1,
                     "rows_by_status": {"significant_up": 1, "significant_down": 0, "not_significant": 0},
                     "total_rows": 1, "significant_rows": 1,
                     "timepoints": None},
                ],
                "not_found": [],
                "no_expression": [],
                "returned": 1,
                "truncated": False,
                "results": [
                    {"locus_tag": "PMM0001", "experiment_id": "exp1",
                     "timepoint": None, "timepoint_hours": None, "timepoint_order": 1,
                     "log2fc": 2.5, "padj": 0.001, "rank": 1,
                     "expression_status": "significant_up",
                     "growth_phase": "exponential",
                     "gene_name": "dnaN", "treatment_type": ["coculture"],
                     "gene_category": "DNA replication"},
                ],
            },
        ):
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, locus_tags=["PMM0001"],
            )

        assert result.results[0].growth_phase == "exponential"
        assert result.rows_by_growth_phase == {"exponential": 1}

    @pytest.mark.asyncio
    async def test_not_found_and_no_expression(self, tool_fns, mock_ctx):
        """not_found and no_expression populated for missing genes."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value={
                "organism_name": "Prochlorococcus MED4",
                "matching_genes": 0,
                "total_matching": 0,
                "rows_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 0},
                "median_abs_log2fc": None,
                "max_abs_log2fc": None,
                "experiment_count": 0,
                "rows_by_treatment_type": {},
                "rows_by_background_factors": {},
                "rows_by_growth_phase": {},
                "by_table_scope": {},
                "top_categories": [],
                "experiments": [],
                "not_found": ["FAKE_GENE"],
                "no_expression": ["PMM9999"],
                "returned": 0,
                "truncated": False,
                "results": [],
            },
        ):
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, locus_tags=["FAKE_GENE", "PMM9999"],
            )

        assert result.not_found == ["FAKE_GENE"]
        assert result.no_expression == ["PMM9999"]
        assert result.results == []


# ---------------------------------------------------------------------------
# TestHypotheticalAndECFixtureUsage
# ---------------------------------------------------------------------------
class TestFixtureSubsetUsage:
    """Verify fixture subsets (GENES_HYPOTHETICAL, GENES_WITH_EC) are meaningful."""

    def test_hypothetical_genes_have_no_gene_name(self):
        """Hypothetical genes have annotation_quality == 0 or product containing 'hypothetical'."""
        for gene in GENES_HYPOTHETICAL:
            assert (
                gene.get("annotation_quality", 0) == 0
                or "hypothetical" in gene.get("product", "").lower()
            ), f"{gene['locus_tag']} is not hypothetical"

    def test_ec_genes_have_ec_numbers(self):
        """Genes in GENES_WITH_EC have ec_numbers field."""
        for gene in GENES_WITH_EC:
            assert gene.get("ec_numbers"), (
                f"{gene['locus_tag']} in GENES_WITH_EC but has no ec_numbers"
            )

    @pytest.mark.asyncio
    async def test_hypothetical_gene_overview_low_quality(self, tool_fns, mock_ctx):
        """Hypothetical genes returned with low annotation_quality via gene_overview."""
        gene = GENES_HYPOTHETICAL[0]
        with patch(
            "multiomics_explorer.api.functions.gene_overview",
            return_value={
                "total_matching": 1,
                "by_organism": [{"organism_name": gene["organism_name"], "count": 1}],
                "by_category": [],
                "by_annotation_type": [],
                "has_expression": 0,
                "has_significant_expression": 0,
                "has_orthologs": 0,
                "has_clusters": 0,
                "returned": 1,
                "truncated": False,
                "not_found": [],
                "results": [
                    {"locus_tag": gene["locus_tag"],
                     "gene_name": gene.get("gene_name"),
                     "product": gene.get("product"),
                     "gene_category": gene.get("gene_category"),
                     "annotation_quality": gene.get("annotation_quality", 0),
                     "organism_name": gene["organism_name"],
                     "annotation_types": [],
                     "expression_edge_count": 0,
                     "significant_up_count": 0,
                     "significant_down_count": 0,
                     "closest_ortholog_group_size": 0,
                     "closest_ortholog_genera": [],
                     "cluster_membership_count": 0, "cluster_types": []},
                ],
            },
        ):
            result = await tool_fns["gene_overview"](
                mock_ctx, locus_tags=[gene["locus_tag"]],
            )

        r = result.results[0]
        assert r.annotation_quality == gene.get("annotation_quality", 0)

    @pytest.mark.asyncio
    async def test_ec_gene_in_function_search(self, tool_fns, mock_ctx):
        """Gene with EC number appears in function search results."""
        gene = GENES_WITH_EC[0]
        row = as_search_genes_result(gene, score=4.0)
        with patch(
            "multiomics_explorer.api.functions.genes_by_function",
            return_value={
                "total_search_hits": 50,
                "total_matching": 1,
                "by_organism": [{"organism_name": gene["organism_name"], "count": 1}],
                "by_category": [{"category": gene.get("gene_category", "Unknown"), "count": 1}],
                "score_max": 4.0,
                "score_median": 4.0,
                "returned": 1,
                "truncated": False,
                "results": [row],
            },
        ):
            result = await tool_fns["genes_by_function"](
                mock_ctx, search_text="polymerase",
            )

        assert result.results[0].locus_tag == gene["locus_tag"]


# ---------------------------------------------------------------------------
# TestRunCypherCorrectness
# ---------------------------------------------------------------------------
class TestRunCypherCorrectness:
    """Verify run_cypher returns correct data for realistic mock responses."""

    @pytest.mark.asyncio
    async def test_basic_query_returns_results(self, tool_fns, mock_ctx):
        """Simple MATCH query returns results with envelope."""
        with patch(
            "multiomics_explorer.api.functions.run_cypher",
            return_value={
                "returned": 2,
                "truncated": False,
                "warnings": [],
                "results": [
                    {"locus_tag": "PMM0001", "gene_name": "dnaN"},
                    {"locus_tag": "PMM0845", "gene_name": None},
                ],
            },
        ):
            result = await tool_fns["run_cypher"](
                mock_ctx, query="MATCH (g:Gene) RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name LIMIT 2",
            )

        assert result.returned == 2
        assert result.truncated is False
        assert result.warnings == []
        assert len(result.results) == 2
        assert result.results[0]["locus_tag"] == "PMM0001"

    @pytest.mark.asyncio
    async def test_warnings_propagated(self, tool_fns, mock_ctx):
        """Schema warnings from CyVer appear in response."""
        with patch(
            "multiomics_explorer.api.functions.run_cypher",
            return_value={
                "returned": 0,
                "truncated": False,
                "warnings": ["Label 'FakeNode' not in database"],
                "results": [],
            },
        ):
            result = await tool_fns["run_cypher"](
                mock_ctx, query="MATCH (n:FakeNode) RETURN n",
            )

        assert result.returned == 0
        assert result.warnings == ["Label 'FakeNode' not in database"]

    @pytest.mark.asyncio
    async def test_truncated_when_limit_reached(self, tool_fns, mock_ctx):
        """truncated=True when returned == limit."""
        with patch(
            "multiomics_explorer.api.functions.run_cypher",
            return_value={
                "returned": 10,
                "truncated": True,
                "warnings": [],
                "results": [{"n": i} for i in range(10)],
            },
        ):
            result = await tool_fns["run_cypher"](
                mock_ctx, query="MATCH (n) RETURN n", limit=10,
            )

        assert result.truncated is True
        assert result.returned == 10


# ---------------------------------------------------------------------------
# TestSearchHomologGroupsCorrectness
# ---------------------------------------------------------------------------
class TestSearchHomologGroupsCorrectness:
    """Verify search_homolog_groups returns correct data."""

    @pytest.mark.asyncio
    async def test_search_returns_groups(self, tool_fns, mock_ctx):
        """Text search returns ortholog groups with scores."""
        with patch(
            "multiomics_explorer.api.functions.search_homolog_groups",
            return_value={
                "total_entries": 21122,
                "total_matching": 50,
                "by_source": [{"source": "cyanorak", "count": 30},
                              {"source": "eggnog", "count": 20}],
                "by_level": [{"taxonomic_level": "curated", "count": 30}],
                "score_max": 6.1,
                "score_median": 2.0,
                "returned": 3,
                "truncated": True,
                "results": [
                    {"group_id": "cyanorak:CK_00000570", "group_name": "CK_00000570",
                     "source": "cyanorak",
                     "taxonomic_level": "curated", "specificity_rank": 0,
                     "consensus_gene_name": "psaA",
                     "consensus_product": "Photosystem I P700 chlorophyll a apoprotein A1",
                     "member_count": 15, "organism_count": 15, "score": 6.1},
                    {"group_id": "cyanorak:CK_00000571", "group_name": "CK_00000571",
                     "source": "cyanorak",
                     "taxonomic_level": "curated", "specificity_rank": 0,
                     "consensus_gene_name": "psaB",
                     "consensus_product": "Photosystem I P700 chlorophyll a apoprotein A2",
                     "member_count": 15, "organism_count": 15, "score": 5.8},
                    {"group_id": "eggnog:COG0592@2", "group_name": "COG0592@2",
                     "source": "eggnog",
                     "taxonomic_level": "Bacteria", "specificity_rank": 3,
                     "consensus_gene_name": "dnaN",
                     "consensus_product": "DNA polymerase III, beta subunit",
                     "member_count": 200, "organism_count": 150, "score": 2.0},
                ],
            },
        ):
            result = await tool_fns["search_homolog_groups"](
                mock_ctx, search_text="photosystem",
            )

        assert result.total_matching == 50
        assert result.returned == 3
        assert result.truncated is True
        assert result.score_max == 6.1
        assert len(result.results) == 3
        assert result.results[0].group_id == "cyanorak:CK_00000570"
        assert len(result.by_source) == 2

    @pytest.mark.asyncio
    async def test_summary_mode(self, tool_fns, mock_ctx):
        """Summary mode returns counts only."""
        with patch(
            "multiomics_explorer.api.functions.search_homolog_groups",
            return_value={
                "total_entries": 21122, "total_matching": 50,
                "by_source": [{"source": "cyanorak", "count": 30}],
                "by_level": [{"taxonomic_level": "curated", "count": 30}],
                "score_max": 6.1, "score_median": 2.0,
                "returned": 0, "truncated": True, "results": [],
            },
        ):
            result = await tool_fns["search_homolog_groups"](
                mock_ctx, search_text="photosystem", summary=True,
            )

        assert result.returned == 0
        assert result.results == []
        assert result.total_matching == 50


# ---------------------------------------------------------------------------
# TestGenesByHomologGroupCorrectness
# ---------------------------------------------------------------------------
class TestGenesByHomologGroupCorrectness:
    """Verify genes_by_homolog_group returns correct data."""

    @pytest.mark.asyncio
    async def test_returns_member_genes(self, tool_fns, mock_ctx):
        """Group IDs → member genes."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_homolog_group",
            return_value={
                "total_matching": 2,
                "total_genes": 2,
                "total_categories": 1,
                "genes_per_group_max": 2,
                "genes_per_group_median": 2.0,
                "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 2}],
                "top_categories": [{"category": "DNA replication", "count": 2}],
                "top_groups": [{"group_id": "cyanorak:CK_00000364", "count": 2}],
                "not_found_groups": [],
                "not_matched_groups": [],
                "not_found_organisms": [],
                "not_matched_organisms": [],
                "returned": 2,
                "truncated": False,
                "results": [
                    {"locus_tag": "PMM0001", "gene_name": "dnaN",
                     "product": "DNA polymerase III, beta subunit",
                     "organism_name": "Prochlorococcus MED4",
                     "gene_category": "DNA replication",
                     "annotation_quality": 3,
                     "group_id": "cyanorak:CK_00000364"},
                    {"locus_tag": "PMM0845", "gene_name": None,
                     "product": "hypothetical protein",
                     "organism_name": "Prochlorococcus MED4",
                     "gene_category": None,
                     "annotation_quality": 0,
                     "group_id": "cyanorak:CK_00000364"},
                ],
            },
        ):
            result = await tool_fns["genes_by_homolog_group"](
                mock_ctx, group_ids=["cyanorak:CK_00000364"],
            )

        assert result.total_matching == 2
        assert result.returned == 2
        assert len(result.results) == 2
        assert result.results[0].locus_tag == "PMM0001"
        assert result.not_found_groups == []

    @pytest.mark.asyncio
    async def test_not_found_groups(self, tool_fns, mock_ctx):
        """Non-existent group IDs appear in not_found_groups."""
        with patch(
            "multiomics_explorer.api.functions.genes_by_homolog_group",
            return_value={
                "total_matching": 0, "total_genes": 0, "total_categories": 0,
                "genes_per_group_max": 0, "genes_per_group_median": 0.0,
                "by_organism": [], "top_categories": [], "top_groups": [],
                "not_found_groups": ["fake:group"],
                "not_matched_groups": [],
                "not_found_organisms": [],
                "not_matched_organisms": [],
                "returned": 0, "truncated": False, "results": [],
            },
        ):
            result = await tool_fns["genes_by_homolog_group"](
                mock_ctx, group_ids=["fake:group"],
            )

        assert result.not_found_groups == ["fake:group"]
        assert result.results == []


# ---------------------------------------------------------------------------
# TestDiffExprByOrthologCorrectness
# ---------------------------------------------------------------------------
class TestDiffExprByOrthologCorrectness:
    """Verify differential_expression_by_ortholog returns correct data."""

    @pytest.mark.asyncio
    async def test_returns_group_level_expression(self, tool_fns, mock_ctx):
        """Cross-organism expression data at group × experiment × timepoint."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_ortholog",
            return_value={
                "total_matching": 2,
                "matching_genes": 3,
                "matching_groups": 1,
                "experiment_count": 2,
                "median_abs_log2fc": 1.5,
                "max_abs_log2fc": 3.2,
                "returned": 2,
                "truncated": False,
                "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 2}],
                "rows_by_status": {"significant_up": 1, "significant_down": 0, "not_significant": 1},
                "rows_by_treatment_type": {"coculture": 2},
                "rows_by_background_factors": {},
                "rows_by_growth_phase": {},
                "by_table_scope": {"all_detected_genes": 2},
                "top_groups": [{"group_id": "cyanorak:CK_00000570",
                                "consensus_gene_name": "psaA",
                                "consensus_product": "photosystem I",
                                "significant_genes": 2, "total_genes": 3}],
                "top_experiments": [{"experiment_id": "exp1",
                                     "treatment_type": ["coculture"],
                                     "background_factors": [],
                                     "organism_name": "Prochlorococcus MED4",
                                     "significant_genes": 2}],
                "not_found_groups": [],
                "not_matched_groups": [],
                "not_found_organisms": [],
                "not_matched_organisms": [],
                "not_found_experiments": [],
                "not_matched_experiments": [],
                "results": [
                    {"group_id": "cyanorak:CK_00000570",
                     "consensus_gene_name": "psaA",
                     "consensus_product": "photosystem I",
                     "experiment_id": "exp1", "treatment_type": ["coculture"],
                     "background_factors": [],
                     "organism_name": "Prochlorococcus MED4",
                     "timepoint": "2h", "timepoint_hours": 2.0, "timepoint_order": 1,
                     "genes_with_expression": 3, "total_genes": 3,
                     "significant_up": 2, "significant_down": 0, "not_significant": 1},
                    {"group_id": "cyanorak:CK_00000570",
                     "consensus_gene_name": "psaA",
                     "consensus_product": "photosystem I",
                     "experiment_id": "exp2", "treatment_type": ["light_stress"],
                     "background_factors": [],
                     "organism_name": "Prochlorococcus MED4",
                     "timepoint": None, "timepoint_hours": None, "timepoint_order": 1,
                     "genes_with_expression": 3, "total_genes": 3,
                     "significant_up": 0, "significant_down": 0, "not_significant": 3},
                ],
            },
        ):
            result = await tool_fns["differential_expression_by_ortholog"](
                mock_ctx, group_ids=["cyanorak:CK_00000570"],
            )

        assert result.total_matching == 2
        assert result.matching_groups == 1
        assert result.experiment_count == 2
        assert len(result.results) == 2
        assert result.results[0].group_id == "cyanorak:CK_00000570"
        assert result.rows_by_status["significant_up"] == 1

    @pytest.mark.asyncio
    async def test_not_found_groups(self, tool_fns, mock_ctx):
        """Non-existent groups appear in not_found_groups."""
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_ortholog",
            return_value={
                "total_matching": 0, "matching_genes": 0, "matching_groups": 0,
                "experiment_count": 0, "median_abs_log2fc": None, "max_abs_log2fc": None,
                "returned": 0, "truncated": False,
                "by_organism": [],
                "rows_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 0},
                "rows_by_treatment_type": {}, "rows_by_background_factors": {},
                "rows_by_growth_phase": {},
                "by_table_scope": {},
                "top_groups": [], "top_experiments": [],
                "not_found_groups": ["fake:group"],
                "not_matched_groups": [],
                "not_found_organisms": [],
                "not_matched_organisms": [],
                "not_found_experiments": [],
                "not_matched_experiments": [],
                "results": [],
            },
        ):
            result = await tool_fns["differential_expression_by_ortholog"](
                mock_ctx, group_ids=["fake:group"],
            )

        assert result.not_found_groups == ["fake:group"]
        assert result.results == []


# ---------------------------------------------------------------------------
# TestListOrganismsCorrectness
# ---------------------------------------------------------------------------
class TestListOrganismsCorrectness:
    """Verify list_organisms returns correct data."""

    @pytest.mark.asyncio
    async def test_returns_organisms(self, tool_fns, mock_ctx):
        """Returns organisms with taxonomy and counts."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 15,
                "total_matching": 15,
                "returned": 2,
                "truncated": True,
                "by_cluster_type": [],
                "by_organism_type": [],
                "not_found": [],
                "results": [
                    {"organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain",
                     "genus": "Prochlorococcus",
                     "species": "Prochlorococcus marinus", "strain": "MED4", "clade": "HLI",
                     "ncbi_taxon_id": 59919, "gene_count": 1976, "publication_count": 11,
                     "experiment_count": 46,
                     "treatment_types": ["coculture", "light_stress"],
                     "background_factors": [],
                     "omics_types": ["RNASEQ", "PROTEOMICS"]},
                    {"organism_name": "Alteromonas macleodii EZ55", "organism_type": "genome_strain",
                     "genus": "Alteromonas",
                     "species": "Alteromonas macleodii", "strain": "EZ55", "clade": None,
                     "ncbi_taxon_id": 28108, "gene_count": 4136, "publication_count": 2,
                     "experiment_count": 13,
                     "treatment_types": ["carbon_stress"],
                     "background_factors": [],
                     "omics_types": ["RNASEQ"]},
                ],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)

        assert result.total_entries == 15
        assert result.returned == 2
        assert result.truncated is True
        assert len(result.results) == 2
        assert result.results[0].organism_name == "Prochlorococcus MED4"
        assert result.results[0].gene_count == 1976
        assert result.results[1].genus == "Alteromonas"

    @pytest.mark.asyncio
    async def test_organism_type_in_results(self, tool_fns, mock_ctx):
        """Results include organism_type field."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 2,
                "total_matching": 2,
                "returned": 2,
                "truncated": False,
                "by_cluster_type": [],
                "by_organism_type": [
                    {"organism_type": "genome_strain", "count": 1},
                    {"organism_type": "reference_proteome_match", "count": 1},
                ],
                "not_found": [],
                "results": [
                    {"organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain",
                     "genus": "Prochlorococcus", "species": "Prochlorococcus marinus",
                     "strain": "MED4", "clade": "HLI", "ncbi_taxon_id": 59919,
                     "gene_count": 1976, "publication_count": 11, "experiment_count": 46,
                     "treatment_types": ["coculture"], "background_factors": [],
                     "omics_types": ["RNASEQ"]},
                    {"organism_name": "Alteromonas (MarRef v6)",
                     "organism_type": "reference_proteome_match",
                     "genus": "Alteromonas", "species": None, "strain": "Alt_MarRef",
                     "clade": None, "ncbi_taxon_id": 232, "gene_count": 500,
                     "publication_count": 1, "experiment_count": 3,
                     "treatment_types": ["coculture"], "background_factors": [],
                     "omics_types": ["PROTEOMICS"],
                     "reference_database": "MarRef v6",
                     "reference_proteome": "UP000262181"},
                ],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)

        assert result.results[0].organism_type == "genome_strain"
        assert result.results[0].reference_database is None
        assert result.results[0].reference_proteome is None
        assert result.results[1].organism_type == "reference_proteome_match"
        assert result.results[1].reference_database == "MarRef v6"
        assert result.results[1].reference_proteome == "UP000262181"

    @pytest.mark.asyncio
    async def test_by_organism_type_in_envelope(self, tool_fns, mock_ctx):
        """Envelope includes by_organism_type breakdown."""
        with patch(
            "multiomics_explorer.api.functions.list_organisms",
            return_value={
                "total_entries": 2,
                "total_matching": 2,
                "returned": 2,
                "truncated": False,
                "by_cluster_type": [],
                "by_organism_type": [
                    {"organism_type": "genome_strain", "count": 25},
                    {"organism_type": "treatment", "count": 5},
                    {"organism_type": "reference_proteome_match", "count": 2},
                ],
                "not_found": [],
                "results": [
                    {"organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain",
                     "genus": "Prochlorococcus", "species": "Prochlorococcus marinus",
                     "strain": "MED4", "clade": "HLI", "ncbi_taxon_id": 59919,
                     "gene_count": 1976, "publication_count": 11, "experiment_count": 46,
                     "treatment_types": [], "background_factors": [], "omics_types": []},
                    {"organism_name": "Test Org", "organism_type": "treatment",
                     "genus": "Test", "species": None, "strain": None, "clade": None,
                     "ncbi_taxon_id": None, "gene_count": 0, "publication_count": 0,
                     "experiment_count": 0,
                     "treatment_types": [], "background_factors": [], "omics_types": []},
                ],
            },
        ):
            result = await tool_fns["list_organisms"](mock_ctx)

        assert len(result.by_organism_type) == 3
        assert result.by_organism_type[0].organism_type == "genome_strain"
        assert result.by_organism_type[0].count == 25


# ---------------------------------------------------------------------------
# TestListFilterValuesCorrectness
# ---------------------------------------------------------------------------
class TestListFilterValuesCorrectness:
    """Verify list_filter_values returns correct data."""

    @pytest.mark.asyncio
    async def test_returns_categories(self, tool_fns, mock_ctx):
        """Returns gene categories with counts."""
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value={
                "filter_type": "gene_category",
                "total_entries": 26,
                "returned": 26,
                "truncated": False,
                "results": [
                    {"value": "Photosynthesis", "count": 770},
                    {"value": "Transport", "count": 500},
                    {"value": "DNA replication", "count": 120},
                ],
            },
        ):
            result = await tool_fns["list_filter_values"](mock_ctx)

        assert result.filter_type == "gene_category"
        assert result.total_entries == 26
        assert result.returned == 26
        assert result.truncated is False
        assert len(result.results) == 3
        assert result.results[0].value == "Photosynthesis"
        assert result.results[0].count == 770

    @pytest.mark.asyncio
    async def test_brite_tree_filter_type(self, tool_fns, mock_ctx):
        """brite_tree returns trees with tree_code."""
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value={
                "filter_type": "brite_tree",
                "total_entries": 12,
                "returned": 12,
                "truncated": False,
                "results": [
                    {"value": "enzymes", "tree_code": "ko01000", "count": 2057},
                    {"value": "transporters", "tree_code": "ko02000", "count": 184},
                ],
            },
        ):
            result = await tool_fns["list_filter_values"](
                mock_ctx, filter_type="brite_tree",
            )
        assert result.filter_type == "brite_tree"
        assert result.total_entries == 12
        assert len(result.results) == 2
        assert result.results[0].value == "enzymes"
        assert result.results[0].tree_code == "ko01000"
        assert result.results[0].count == 2057

    @pytest.mark.asyncio
    async def test_growth_phase_filter_type(self, tool_fns, mock_ctx):
        """growth_phase filter_type returns physiological state values."""
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value={
                "filter_type": "growth_phase",
                "total_entries": 3,
                "returned": 3,
                "truncated": False,
                "results": [
                    {"value": "exponential", "count": 45},
                    {"value": "nutrient_limited", "count": 12},
                    {"value": "stationary", "count": 5},
                ],
            },
        ):
            result = await tool_fns["list_filter_values"](
                mock_ctx, filter_type="growth_phase",
            )
        assert result.filter_type == "growth_phase"
        assert result.total_entries == 3
        assert len(result.results) == 3
        assert result.results[0].value == "exponential"
        assert result.results[0].count == 45
