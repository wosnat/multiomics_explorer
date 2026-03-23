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

from multiomics_explorer.mcp_server.tools import register_tools
from tests.fixtures.gene_data import (
    GENES,
    GENES_BY_LOCUS,
    GENES_HYPOTHETICAL,
    GENES_WITH_EC,
    GENES_WITH_GENE_NAME,
    GENES_WITHOUT_GENE_NAME,
    as_resolve_gene_result,
    as_search_genes_result,
    genes_by_organism,
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
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_strain", "Unknown"), "gene_count": 1}], "returned": 1, "truncated": False, "results": [row]},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier=locus_tag)

        assert result.total_matching == 1
        assert len(result.results) == 1
        r = result.results[0]
        assert r.locus_tag == locus_tag
        assert r.product == gene.get("product")
        assert r.organism_strain == gene.get("organism_strain")

    @pytest.mark.asyncio
    async def test_lookup_by_gene_name_dnaN(self, tool_fns, mock_ctx):
        """Looking up 'dnaN' with a single mock result returns the correct gene."""
        gene = GENES_BY_LOCUS["PMM0001"]
        row = as_resolve_gene_result(gene)
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_strain", "Unknown"), "gene_count": 1}], "returned": 1, "truncated": False, "results": [row]},
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
            return_value={"total_matching": 2, "by_organism": [{"organism_name": "Prochlorococcus MED4", "gene_count": 1}, {"organism_name": "Prochlorococcus MIT9312", "gene_count": 1}], "returned": 2, "truncated": False, "results": [med4, mit9312]},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="dnaN")

        assert result.total_matching == 2
        assert result.returned == 2
        loci = {r.locus_tag for r in result.results}
        assert loci == {"PMM0001", "PMT9312_0001"}
        organisms = {r.organism_strain for r in result.results}
        assert "Prochlorococcus MED4" in organisms
        assert "Prochlorococcus MIT9312" in organisms

    @pytest.mark.asyncio
    async def test_lookup_by_identifier_refseq(self, tool_fns, mock_ctx):
        """PMM0446 can be found via RefSeq protein ID WP_011132082.1."""
        gene = GENES_BY_LOCUS["PMM0446"]
        row = as_resolve_gene_result(gene)
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_strain", "Unknown"), "gene_count": 1}], "returned": 1, "truncated": False, "results": [row]},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="WP_011132082.1")

        r = result.results[0]
        assert r.locus_tag == "PMM0446"
        assert r.gene_name == "ctaCI"
        assert r.organism_strain == gene["organism_strain"]

    @pytest.mark.asyncio
    async def test_gene_without_real_gene_name(self, tool_fns, mock_ctx):
        """S8102_04001 has no gene_name field — result shows None."""
        gene = GENES_BY_LOCUS["S8102_04001"]
        row = as_resolve_gene_result(gene)
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_strain", "Unknown"), "gene_count": 1}], "returned": 1, "truncated": False, "results": [row]},
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
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_strain", "Unknown"), "gene_count": 1}], "returned": 1, "truncated": False, "results": [row]},
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
            return_value={"total_matching": 1, "by_organism": [{"organism_name": "Prochlorococcus MED4", "gene_count": 1}], "returned": 1, "truncated": False, "results": [med4]},
        ):
            result = await tool_fns["resolve_gene"](
                mock_ctx, identifier="dnaN", organism="MED4",
            )

        assert result.total_matching == 1
        assert result.results[0].organism_strain == "Prochlorococcus MED4"

    @pytest.mark.asyncio
    async def test_alternate_identifier_lookup(self, tool_fns, mock_ctx):
        """PMM0001 all_identifiers includes TX50_RS00020 (alternate locus tag)."""
        gene = GENES_BY_LOCUS["PMM0001"]
        row = as_resolve_gene_result(gene)
        with patch(
            "multiomics_explorer.api.functions.resolve_gene",
            return_value={"total_matching": 1, "by_organism": [{"organism_name": row.get("organism_strain", "Unknown"), "gene_count": 1}], "returned": 1, "truncated": False, "results": [row]},
        ):
            result = await tool_fns["resolve_gene"](mock_ctx, identifier="TX50_RS00020")

        r = result.results[0]
        assert r.locus_tag == "PMM0001"
        assert r.gene_name == "dnaN"


# ---------------------------------------------------------------------------
# TestSearchGenesCorrectness
# ---------------------------------------------------------------------------
class TestSearchGenesCorrectness:
    """Verify search_genes returns correct data for realistic mock responses."""

    def test_fulltext_results_with_scores(self, tool_fns, mock_ctx):
        """Results from multiple organisms are returned with total count."""
        rows = [
            as_search_genes_result(GENES_BY_LOCUS["PMM0001"], score=5.2),
            as_search_genes_result(GENES_BY_LOCUS["PMT9312_0001"], score=4.8),
            as_search_genes_result(GENES_BY_LOCUS["SYNW0305"], score=2.1),
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows

        result = json.loads(
            tool_fns["search_genes"](mock_ctx, search_text="DNA polymerase")
        )

        assert result["total"] == 3
        assert result["query"] == "DNA polymerase"
        # Results preserve order (sorted by score from Neo4j)
        loci = [r["locus_tag"] for r in result["results"]]
        assert loci == ["PMM0001", "PMT9312_0001", "SYNW0305"]

    def test_organism_filter_wh8102(self, tool_fns, mock_ctx):
        """Organism filter passes through and only WH8102 genes returned."""
        wh8102_row = as_search_genes_result(GENES_BY_LOCUS["SYNW0305"], score=3.0)
        _conn_from(mock_ctx).execute_query.return_value = [wh8102_row]

        tool_fns["search_genes"](mock_ctx, search_text="metallopeptidase", organism="WH8102")

        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["organism"] == "WH8102"

    def test_quality_filter_passed(self, tool_fns, mock_ctx):
        """min_quality=2 is passed through to query builder."""
        rows = [
            as_search_genes_result(GENES_BY_LOCUS["PMM0001"], score=5.0),
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows

        tool_fns["search_genes"](mock_ctx, search_text="polymerase", min_quality=2)

        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["min_quality"] == 2

    def test_search_genes_result_envelope(self, tool_fns, mock_ctx):
        """Result envelope contains query, total, and results keys."""
        rows = [as_search_genes_result(GENES_BY_LOCUS["PMN2A_0044"], score=4.0)]
        _conn_from(mock_ctx).execute_query.return_value = rows

        result = json.loads(
            tool_fns["search_genes"](mock_ctx, search_text="naphthoate synthase")
        )

        assert "results" in result
        assert "total" in result
        assert "query" in result
        assert result["total"] == 1
        assert result["results"][0]["locus_tag"] == "PMN2A_0044"


# ---------------------------------------------------------------------------
# TestGetGeneDetailsCorrectness
# ---------------------------------------------------------------------------
class TestGetGeneDetailsCorrectness:
    """Verify get_gene_details returns flat g{.*} properties correctly."""

    def test_well_annotated_prochlorococcus(self, tool_fns, mock_ctx):
        """PMM0001 returns flat gene properties via g{.*}. Single execute_query call."""
        gene_data = {
            "locus_tag": "PMM0001",
            "gene_name": "dnaN",
            "product": "DNA polymerase III, beta subunit",
            "organism_strain": "Prochlorococcus MED4",
            "gene_category": "DNA replication",
            "annotation_quality": 3,
            "ec_numbers": ["2.7.7.7"],
        }
        conn = _conn_from(mock_ctx)
        conn.execute_query.return_value = [{"gene": gene_data}]

        result = json.loads(tool_fns["get_gene_details"](mock_ctx, gene_id="PMM0001"))

        assert len(result) == 1
        r = result[0]
        assert r["locus_tag"] == "PMM0001"
        assert r["gene_name"] == "dnaN"
        assert r["organism_strain"] == "Prochlorococcus MED4"
        assert "_protein" not in r
        assert "_organism" not in r
        assert "_ortholog_groups" not in r
        assert "_homologs" not in r
        assert conn.execute_query.call_count == 1

    def test_alteromonas_gene_eggnog_only(self, tool_fns, mock_ctx):
        """ALT831_RS00180 returns flat properties. Single query call."""
        gene_data = {
            "locus_tag": "ALT831_RS00180",
            "gene_name": None,
            "product": "IS630 family transposase",
            "organism_strain": "Alteromonas macleodii MIT1002",
            "annotation_quality": 2,
        }
        conn = _conn_from(mock_ctx)
        conn.execute_query.return_value = [{"gene": gene_data}]

        result = json.loads(
            tool_fns["get_gene_details"](mock_ctx, gene_id="ALT831_RS00180")
        )

        r = result[0]
        assert r["locus_tag"] == "ALT831_RS00180"
        assert r["organism_strain"] == "Alteromonas macleodii MIT1002"
        assert "_protein" not in r
        assert "_organism" not in r
        assert "_ortholog_groups" not in r
        assert "_homologs" not in r
        assert conn.execute_query.call_count == 1


# ---------------------------------------------------------------------------
# TestGeneOverviewCorrectness
# ---------------------------------------------------------------------------
class TestGeneOverviewCorrectness:
    """Verify gene_overview returns correct data for realistic mock responses."""

    def test_single_gene_overview(self, tool_fns, mock_ctx):
        """Mock single gene row with all 12 columns, verify JSON output structure."""
        row = {
            "locus_tag": "PMM1428",
            "gene_name": "test",
            "product": "test product",
            "gene_summary": "A test summary",
            "gene_category": "Photosynthesis",
            "annotation_quality": 3,
            "organism_strain": "Prochlorococcus MED4",
            "annotation_types": ["go_mf", "pfam", "cog_category", "tigr_role"],
            "expression_edge_count": 36,
            "significant_expression_count": 5,
            "closest_ortholog_group_size": 9,
            "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
        }
        _conn_from(mock_ctx).execute_query.return_value = [row]

        result = json.loads(tool_fns["gene_overview"](mock_ctx, gene_ids=["PMM1428"]))

        assert len(result) == 1
        r = result[0]
        assert r["locus_tag"] == "PMM1428"
        assert r["expression_edge_count"] == 36
        assert r["annotation_types"] == ["go_mf", "pfam", "cog_category", "tigr_role"]

    def test_batch_overview(self, tool_fns, mock_ctx):
        """Mock multiple gene rows, verify all returned."""
        rows = [
            {"locus_tag": "PMM1428", "gene_name": "a", "product": "p1",
             "gene_summary": None, "gene_category": None,
             "annotation_quality": 3, "organism_strain": "Prochlorococcus MED4",
             "annotation_types": ["go_mf"], "expression_edge_count": 36,
             "significant_expression_count": 5, "closest_ortholog_group_size": 9,
             "closest_ortholog_genera": ["Prochlorococcus"]},
            {"locus_tag": "EZ55_00275", "gene_name": None, "product": "p2",
             "gene_summary": None, "gene_category": None,
             "annotation_quality": 0, "organism_strain": "Alteromonas EZ55",
             "annotation_types": [], "expression_edge_count": 0,
             "significant_expression_count": 0, "closest_ortholog_group_size": 1,
             "closest_ortholog_genera": []},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows

        result = json.loads(
            tool_fns["gene_overview"](mock_ctx, gene_ids=["PMM1428", "EZ55_00275"])
        )

        assert len(result) == 2
        loci = {r["locus_tag"] for r in result}
        assert loci == {"PMM1428", "EZ55_00275"}

    def test_annotation_types_preserved(self, tool_fns, mock_ctx):
        """List field preserved in JSON output."""
        row = {
            "locus_tag": "PMM1428",
            "gene_name": "a", "product": "p",
            "gene_summary": None, "gene_category": None,
            "annotation_quality": 3, "organism_strain": "Prochlorococcus MED4",
            "annotation_types": ["go_mf", "pfam", "cog_category"],
            "expression_edge_count": 36, "significant_expression_count": 5,
            "closest_ortholog_group_size": 9,
            "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
        }
        _conn_from(mock_ctx).execute_query.return_value = [row]

        result = json.loads(tool_fns["gene_overview"](mock_ctx, gene_ids=["PMM1428"]))

        assert isinstance(result[0]["annotation_types"], list)
        assert "go_mf" in result[0]["annotation_types"]



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
        {"locus_tag": "PMM0001", "organism_strain": "Prochlorococcus MED4",
         "group_id": "CK_00000364", "consensus_gene_name": "dnaN",
         "consensus_product": "DNA polymerase III, beta subunit",
         "taxonomic_level": "curated", "source": "cyanorak"},
        {"locus_tag": "PMM0001", "organism_strain": "Prochlorococcus MED4",
         "group_id": "COG0592@2", "consensus_gene_name": "dnaN",
         "consensus_product": "DNA polymerase III, beta subunit",
         "taxonomic_level": "Bacteria", "source": "eggnog"},
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
        assert r.group_id == "CK_00000364"
        assert r.source == "cyanorak"
        assert r.consensus_product == "DNA polymerase III, beta subunit"

    @pytest.mark.asyncio
    async def test_batch_input_multiple_genes(self, tool_fns, mock_ctx):
        """Batch query returns rows for multiple genes."""
        batch_results = self._SAMPLE_RESULTS + [
            {"locus_tag": "PMM0845", "organism_strain": "Prochlorococcus MED4",
             "group_id": "CK_00000853", "consensus_gene_name": "ndhV",
             "consensus_product": "NADH dehydrogenase subunit NdhV",
             "taxonomic_level": "curated", "source": "cyanorak"},
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
