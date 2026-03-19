"""Correctness tests for MCP tools using realistic gene fixture data.

Tests that tool functions produce correct results when mock Neo4j returns
real gene annotation data. Complements test_tool_wrappers.py which tests
wrapper logic (validation, error messages, LIMIT injection) with minimal mocks.
"""

import json
from unittest.mock import MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

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
# TestResolveGeneCorrectness
# ---------------------------------------------------------------------------
class TestResolveGeneCorrectness:
    """Verify resolve_gene returns correct data for realistic mock responses."""

    @pytest.mark.parametrize(
        "locus_tag",
        [g["locus_tag"] for g in GENES],
        ids=[g["locus_tag"] for g in GENES],
    )
    def test_single_gene_lookup_all_fixtures(self, tool_fns, mock_ctx, locus_tag):
        """Each fixture gene returns correct locus_tag, product, organism."""
        gene = GENES_BY_LOCUS[locus_tag]
        row = as_resolve_gene_result(gene)
        _conn_from(mock_ctx).execute_query.return_value = [row]

        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier=locus_tag))

        org = gene.get("organism_strain")
        assert org in result["results"]
        entries = result["results"][org]
        assert len(entries) == 1
        r = entries[0]
        assert r["locus_tag"] == locus_tag
        assert r["product"] == gene.get("product")

    def test_lookup_by_gene_name_dnaN(self, tool_fns, mock_ctx):
        """Looking up 'dnaN' with a single mock result returns the correct gene."""
        gene = GENES_BY_LOCUS["PMM0001"]
        row = as_resolve_gene_result(gene)
        _conn_from(mock_ctx).execute_query.return_value = [row]

        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier="dnaN"))

        org = "Prochlorococcus MED4"
        assert result["results"][org][0]["locus_tag"] == "PMM0001"
        assert result["results"][org][0]["gene_name"] == "dnaN"

    def test_dnaN_multiple_organisms_grouped(self, tool_fns, mock_ctx):
        """dnaN exists in MED4 and MIT9312; results are grouped by organism."""
        med4 = as_resolve_gene_result(GENES_BY_LOCUS["PMM0001"])
        mit9312 = as_resolve_gene_result(GENES_BY_LOCUS["PMT9312_0001"])
        _conn_from(mock_ctx).execute_query.return_value = [med4, mit9312]

        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier="dnaN"))

        assert result["total"] == 2
        assert "Prochlorococcus MED4" in result["results"]
        assert "Prochlorococcus MIT9312" in result["results"]
        loci = set()
        for entries in result["results"].values():
            for e in entries:
                loci.add(e["locus_tag"])
        assert loci == {"PMM0001", "PMT9312_0001"}

    def test_lookup_by_identifier_refseq(self, tool_fns, mock_ctx):
        """PMM0446 can be found via RefSeq protein ID WP_011132082.1."""
        gene = GENES_BY_LOCUS["PMM0446"]
        row = as_resolve_gene_result(gene)
        _conn_from(mock_ctx).execute_query.return_value = [row]

        result = json.loads(
            tool_fns["resolve_gene"](mock_ctx, identifier="WP_011132082.1")
        )

        org = gene["organism_strain"]
        assert result["results"][org][0]["locus_tag"] == "PMM0446"
        assert result["results"][org][0]["gene_name"] == "ctaCI"

    def test_gene_without_real_gene_name(self, tool_fns, mock_ctx):
        """S8102_04001 has no gene_name field — result shows None."""
        gene = GENES_BY_LOCUS["S8102_04001"]
        row = as_resolve_gene_result(gene)
        _conn_from(mock_ctx).execute_query.return_value = [row]

        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier="S8102_04001"))

        org = gene["organism_strain"]
        r = result["results"][org][0]
        assert r["locus_tag"] == "S8102_04001"
        assert r["gene_name"] is None

    def test_gene_without_gene_name(self, tool_fns, mock_ctx):
        """ALT831_RS00180 has no gene_name (None)."""
        gene = GENES_BY_LOCUS["ALT831_RS00180"]
        row = as_resolve_gene_result(gene)
        _conn_from(mock_ctx).execute_query.return_value = [row]

        result = json.loads(
            tool_fns["resolve_gene"](mock_ctx, identifier="ALT831_RS00180")
        )

        org = gene["organism_strain"]
        r = result["results"][org][0]
        assert r["gene_name"] is None

    def test_organism_filter_narrows_results(self, tool_fns, mock_ctx):
        """With organism='MED4', only the MED4 dnaN is returned."""
        med4 = as_resolve_gene_result(GENES_BY_LOCUS["PMM0001"])
        _conn_from(mock_ctx).execute_query.return_value = [med4]

        result = json.loads(
            tool_fns["resolve_gene"](mock_ctx, identifier="dnaN", organism="MED4")
        )

        assert result["total"] == 1
        assert "Prochlorococcus MED4" in result["results"]

    def test_alternate_identifier_lookup(self, tool_fns, mock_ctx):
        """PMM0001 all_identifiers includes TX50_RS00020 (alternate locus tag)."""
        gene = GENES_BY_LOCUS["PMM0001"]
        row = as_resolve_gene_result(gene)
        _conn_from(mock_ctx).execute_query.return_value = [row]

        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier="TX50_RS00020"))

        org = gene["organism_strain"]
        assert result["results"][org][0]["locus_tag"] == "PMM0001"
        assert result["results"][org][0]["gene_name"] == "dnaN"


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
# TestQueryExpressionCorrectness
# ---------------------------------------------------------------------------
class TestQueryExpressionCorrectness:
    """Verify query_expression passes filters and returns data correctly."""

    def test_direction_up_passed(self, tool_fns, mock_ctx):
        """direction='up' is forwarded as dir='up' to query builder."""
        rows = [{"gene": "PMM0001", "log2fc": 2.5, "direction": "up"}]
        _conn_from(mock_ctx).execute_query.return_value = rows

        tool_fns["query_expression"](mock_ctx, gene_id="PMM0001", direction="up")

        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["dir"] == "up"

    def test_direction_down_passed(self, tool_fns, mock_ctx):
        """direction='down' is forwarded correctly."""
        rows = [{"gene": "PMM0001", "log2fc": -3.5, "direction": "down"}]
        _conn_from(mock_ctx).execute_query.return_value = rows

        tool_fns["query_expression"](mock_ctx, gene_id="PMM0001", direction="down")

        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["dir"] == "down"

    def test_min_log2fc_with_negative_fc(self, tool_fns, mock_ctx):
        """A gene with log2fc=-3.5 passes abs() >= 1.5 filter."""
        rows = [{"gene": "PMM0446", "log2fc": -3.5, "padj": 0.001}]
        _conn_from(mock_ctx).execute_query.return_value = rows

        result = json.loads(
            tool_fns["query_expression"](mock_ctx, gene_id="PMM0446", min_log2fc=1.5)
        )

        assert len(result) == 1
        assert result[0]["log2fc"] == -3.5

    def test_max_pvalue_filter_passed(self, tool_fns, mock_ctx):
        """max_pvalue is forwarded as max_pv parameter."""
        rows = [{"gene": "PMM0001", "log2fc": 2.0, "padj": 0.01}]
        _conn_from(mock_ctx).execute_query.return_value = rows

        tool_fns["query_expression"](mock_ctx, gene_id="PMM0001", max_pvalue=0.05)

        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["max_pv"] == 0.05

    def test_combined_filters_gene_organism_direction(self, tool_fns, mock_ctx):
        """All three filters are passed through together."""
        rows = [{"gene": "PMM0001", "log2fc": 2.0, "direction": "up"}]
        _conn_from(mock_ctx).execute_query.return_value = rows

        tool_fns["query_expression"](
            mock_ctx, gene_id="PMM0001", organism="MED4", direction="up"
        )

        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["gene_id"] == "PMM0001"
        assert call_kwargs["target_strain"] == "MED4"
        assert call_kwargs["dir"] == "up"

    def test_expression_returns_valid_json(self, tool_fns, mock_ctx):
        """Multiple expression rows are returned as valid JSON array."""
        rows = [
            {"gene": "PMM0001", "log2fc": 2.5, "padj": 0.001, "condition": "coculture"},
            {"gene": "PMM0446", "log2fc": -1.8, "padj": 0.02, "condition": "coculture"},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows

        result = json.loads(
            tool_fns["query_expression"](mock_ctx, organism="MED4")
        )

        assert len(result) == 2
        genes = {r["gene"] for r in result}
        assert genes == {"PMM0001", "PMM0446"}


# ---------------------------------------------------------------------------
# TestCompareConditionsCorrectness
# ---------------------------------------------------------------------------
class TestCompareConditionsCorrectness:
    """Verify compare_conditions passes lists and returns data correctly."""

    def test_multiple_gene_ids_passed(self, tool_fns, mock_ctx):
        """A list of gene_ids is passed through to the query builder."""
        rows = [
            {"gene": "PMM0001", "condition": "coculture", "log2fc": 2.0},
            {"gene": "PMM0446", "condition": "coculture", "log2fc": -1.5},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows

        tool_fns["compare_conditions"](
            mock_ctx, gene_ids=["PMM0001", "PMM0446"]
        )

        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["gene_ids"] == ["PMM0001", "PMM0446"]

    def test_multiple_organisms_passed(self, tool_fns, mock_ctx):
        """A list of organisms is passed through."""
        rows = [{"gene": "PMM0001", "organism": "MED4"}]
        _conn_from(mock_ctx).execute_query.return_value = rows

        tool_fns["compare_conditions"](
            mock_ctx, organisms=["MED4", "MIT9312"]
        )

        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["organisms"] == ["MED4", "MIT9312"]

    def test_conditions_list_exact_match(self, tool_fns, mock_ctx):
        """Conditions are passed as exact list (IN not CONTAINS)."""
        rows = [{"gene": "PMM0001", "condition": "nitrogen_stress"}]
        _conn_from(mock_ctx).execute_query.return_value = rows

        tool_fns["compare_conditions"](
            mock_ctx, conditions=["nitrogen_stress", "light_stress"]
        )

        call_kwargs = _conn_from(mock_ctx).execute_query.call_args.kwargs
        assert call_kwargs["conditions"] == ["nitrogen_stress", "light_stress"]

    def test_compare_returns_valid_json(self, tool_fns, mock_ctx):
        """Results from multiple genes/conditions are returned as JSON array."""
        rows = [
            {"gene": "PMM0001", "condition": "coculture", "log2fc": 2.0},
            {"gene": "PMM0001", "condition": "nitrogen_stress", "log2fc": 1.5},
            {"gene": "PMM0446", "condition": "coculture", "log2fc": -3.0},
        ]
        _conn_from(mock_ctx).execute_query.return_value = rows

        result = json.loads(
            tool_fns["compare_conditions"](
                mock_ctx, gene_ids=["PMM0001", "PMM0446"]
            )
        )

        assert len(result) == 3


# ---------------------------------------------------------------------------
# TestGetHomologsCorrectness
# ---------------------------------------------------------------------------
class TestGetHomologsCorrectness:
    """Verify get_homologs returns correct homolog data with new group-based API."""

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

    def test_cross_organism_homologs_via_groups(self, tool_fns, mock_ctx):
        """Groups from different sources are returned with query_gene."""
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
        ]

        result = json.loads(
            tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")
        )

        assert result["query_gene"]["locus_tag"] == "PMM0001"
        assert len(result["ortholog_groups"]) == 2
        sources = {g["source"] for g in result["ortholog_groups"]}
        assert sources == {"cyanorak", "eggnog"}

    def test_include_members_shows_cross_organism_members(self, tool_fns, mock_ctx):
        """include_members=True returns member genes from multiple organisms."""
        members = [
            {"og_name": "CK_00000364", "locus_tag": "PMT9312_0001",
             "gene_name": "dnaN", "product": "DNA pol III beta",
             "organism_strain": "Prochlorococcus MIT9312"},
            {"og_name": "CK_00000364", "locus_tag": "SYNW0305",
             "gene_name": "ftsH1", "product": "metalloprotease",
             "organism_strain": "Synechococcus WH8102"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups()[:1],  # one group
            members,
        ]

        result = json.loads(
            tool_fns["get_homologs"](
                mock_ctx, gene_id="PMM0001", include_members=True,
            )
        )

        g = result["ortholog_groups"][0]
        assert "members" in g
        orgs = {m["organism_strain"] for m in g["members"]}
        assert "Prochlorococcus MIT9312" in orgs
        assert "Synechococcus WH8102" in orgs

    def test_default_mode_two_queries(self, tool_fns, mock_ctx):
        """Without include_members, two queries are executed (gene stub + groups)."""
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
        ]

        tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")

        assert conn.execute_query.call_count == 2

    def test_include_members_three_queries(self, tool_fns, mock_ctx):
        """With include_members, three queries are executed (stub + groups + members)."""
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
            mock_ctx, gene_id="PMM0001", include_members=True,
        )

        assert conn.execute_query.call_count == 3

    def test_group_enrichment_fields_in_response(self, tool_fns, mock_ctx):
        """Response includes OG enrichment fields like consensus_product."""
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
        ]

        result = json.loads(
            tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")
        )

        g = result["ortholog_groups"][0]
        assert g["consensus_product"] == "DNA polymerase III beta subunit"
        assert g["consensus_gene_name"] == "dnaN"
        assert g["member_count"] == 72

    def test_query_gene_has_all_expected_fields(self, tool_fns, mock_ctx):
        """query_gene block contains all gene stub fields."""
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
        ]
        result = json.loads(
            tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")
        )
        qg = result["query_gene"]
        assert qg["locus_tag"] == "PMM0001"
        assert qg["gene_name"] == "dnaN"
        assert qg["product"] == "DNA polymerase III, beta subunit"
        assert qg["organism_strain"] == "Prochlorococcus MED4"

    def test_null_consensus_gene_name_preserved(self, tool_fns, mock_ctx):
        """Groups with null consensus_gene_name serialize correctly."""
        groups = [
            {"og_name": "COG9999@2", "source": "eggnog",
             "taxonomic_level": "Bacteria", "specificity_rank": 3,
             "consensus_product": "hypothetical protein",
             "consensus_gene_name": None, "member_count": 10,
             "organism_count": 5, "genera": "Prochlorococcus",
             "has_cross_genus_members": False},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            groups,
        ]
        result = json.loads(
            tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")
        )
        g = result["ortholog_groups"][0]
        assert g["consensus_gene_name"] is None

    def test_field_types_in_response(self, tool_fns, mock_ctx):
        """Response fields have correct types (int, str, bool)."""
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
        ]
        result = json.loads(
            tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")
        )
        g = result["ortholog_groups"][0]
        assert isinstance(g["member_count"], int)
        assert isinstance(g["organism_count"], int)
        assert isinstance(g["specificity_rank"], int)
        assert isinstance(g["source"], str)
        assert isinstance(g["og_name"], str)
        assert isinstance(g["has_cross_genus_members"], bool)

    def test_member_fields_structure(self, tool_fns, mock_ctx):
        """Each member dict has exactly the expected keys."""
        members = [
            {"og_name": "CK_00000364", "locus_tag": "PMT9312_0001",
             "gene_name": "dnaN", "product": "DNA pol III beta",
             "organism_strain": "Prochlorococcus MIT9312"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups()[:1],
            members,
        ]
        result = json.loads(
            tool_fns["get_homologs"](
                mock_ctx, gene_id="PMM0001", include_members=True,
            )
        )
        m = result["ortholog_groups"][0]["members"][0]
        assert set(m.keys()) == {"locus_tag", "gene_name", "product", "organism_strain"}

    def test_per_group_member_limit_applied_independently(self, tool_fns, mock_ctx):
        """member_limit is applied per group, not globally."""
        members = [
            # 3 members in group CK_00000364
            {"og_name": "CK_00000364", "locus_tag": f"PMT{i:04d}",
             "gene_name": "x", "product": "p", "organism_strain": f"Strain{i}"}
            for i in range(3)
        ] + [
            # 1 member in group COG0592@2
            {"og_name": "COG0592@2", "locus_tag": "ALT001",
             "gene_name": "y", "product": "q", "organism_strain": "Alt1"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
            members,
        ]
        result = json.loads(
            tool_fns["get_homologs"](
                mock_ctx, gene_id="PMM0001", include_members=True, member_limit=2,
            )
        )
        g0 = result["ortholog_groups"][0]  # CK_00000364: 3 members, limit 2
        g1 = result["ortholog_groups"][1]  # COG0592@2: 1 member, under limit
        assert len(g0["members"]) == 2
        assert g0["truncated"] is True
        assert len(g1["members"]) == 1
        assert "truncated" not in g1

    def test_empty_members_for_group_without_matches(self, tool_fns, mock_ctx):
        """A group with no matching members gets an empty members list."""
        # Members only for the second group, none for the first
        members = [
            {"og_name": "COG0592@2", "locus_tag": "ALT001",
             "gene_name": "y", "product": "q", "organism_strain": "Alt1"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [self._gene_stub()],
            self._sample_groups(),
            members,
        ]
        result = json.loads(
            tool_fns["get_homologs"](
                mock_ctx, gene_id="PMM0001", include_members=True,
            )
        )
        g0 = result["ortholog_groups"][0]  # CK_00000364: no members returned
        g1 = result["ortholog_groups"][1]  # COG0592@2: 1 member
        assert g0["members"] == []
        assert len(g1["members"]) == 1
