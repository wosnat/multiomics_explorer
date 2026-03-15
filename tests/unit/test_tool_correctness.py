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
    ctx.request_context.lifespan_context.debug_queries = False
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

    def test_gene_name_equals_locus_tag(self, tool_fns, mock_ctx):
        """ALT831_RS00180 has gene_name == locus_tag (fallback)."""
        gene = GENES_BY_LOCUS["ALT831_RS00180"]
        row = as_resolve_gene_result(gene)
        _conn_from(mock_ctx).execute_query.return_value = [row]

        result = json.loads(
            tool_fns["resolve_gene"](mock_ctx, identifier="ALT831_RS00180")
        )

        org = gene["organism_strain"]
        r = result["results"][org][0]
        assert r["gene_name"] == r["locus_tag"]

    def test_organism_filter_narrows_results(self, tool_fns, mock_ctx):
        """With organism='MED4', only the MED4 dnaN is returned."""
        med4 = as_resolve_gene_result(GENES_BY_LOCUS["PMM0001"])
        _conn_from(mock_ctx).execute_query.return_value = [med4]

        result = json.loads(
            tool_fns["resolve_gene"](mock_ctx, identifier="dnaN", organism="MED4")
        )

        assert result["total"] == 1
        assert "Prochlorococcus MED4" in result["results"]

    def test_old_locus_tag_lookup(self, tool_fns, mock_ctx):
        """PMT0106 has old_locus_tags including PMT_0106."""
        gene = GENES_BY_LOCUS["PMT0106"]
        row = as_resolve_gene_result(gene)
        _conn_from(mock_ctx).execute_query.return_value = [row]

        result = json.loads(tool_fns["resolve_gene"](mock_ctx, identifier="PMT_0106"))

        org = gene["organism_strain"]
        assert result["results"][org][0]["locus_tag"] == "PMT0106"
        assert result["results"][org][0]["gene_name"] == "legI"


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
    """Verify get_gene_details assembles realistic data correctly."""

    def test_well_annotated_prochlorococcus(self, tool_fns, mock_ctx):
        """PMM0001 returns full gene data with protein, organism, cluster info."""
        gene_data = {
            "locus_tag": "PMM0001",
            "gene_name": "dnaN",
            "product": "DNA polymerase III, beta subunit",
            "organism_strain": "Prochlorococcus MED4",
            "ec_numbers": ["2.7.7.7"],
            "go_terms": GENES_BY_LOCUS["PMM0001"]["go_terms"],
            "_protein": {"protein_id": "WP_011131639.1", "protein_family": "Beta sliding clamp family"},
            "_organism": {"strain": "MED4", "species": "Prochlorococcus marinus"},
            "_cluster": {"cluster_number": "CK_00000364"},
        }
        homologs = [
            {"locus_tag": "PMT9312_0001", "organism_strain": "Prochlorococcus MIT9312",
             "gene_name": "dnaN"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [{"gene": gene_data}],
            homologs,
        ]

        result = json.loads(tool_fns["get_gene_details"](mock_ctx, gene_id="PMM0001"))

        assert len(result) == 1
        r = result[0]
        assert r["locus_tag"] == "PMM0001"
        assert r["gene_name"] == "dnaN"
        assert r["_protein"]["protein_id"] == "WP_011131639.1"
        assert r["_organism"]["strain"] == "MED4"
        assert r["_cluster"]["cluster_number"] == "CK_00000364"
        assert r["_homologs"] == homologs

    def test_alteromonas_gene_no_cluster(self, tool_fns, mock_ctx):
        """ALT831_RS00180 is Alteromonas — no CyanORAK cluster."""
        gene_data = {
            "locus_tag": "ALT831_RS00180",
            "gene_name": "ALT831_RS00180",
            "product": "IS630 family transposase",
            "organism_strain": "Alteromonas macleodii MIT1002",
            "_protein": {"protein_id": "WP_197047964.1"},
            "_organism": {"strain": "MIT1002", "species": "Alteromonas macleodii"},
            "_cluster": None,
        }
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [{"gene": gene_data}],
            [],  # no homologs
        ]

        result = json.loads(
            tool_fns["get_gene_details"](mock_ctx, gene_id="ALT831_RS00180")
        )

        r = result[0]
        assert r["locus_tag"] == "ALT831_RS00180"
        assert r["_cluster"] is None
        assert r["_homologs"] == []

    def test_homologs_merged_from_different_organisms(self, tool_fns, mock_ctx):
        """Homologs from MED4, MIT9312, WH8102 are all merged into result."""
        gene_data = {
            "locus_tag": "PMM0001",
            "gene_name": "dnaN",
            "product": "DNA polymerase III, beta subunit",
        }
        homologs = [
            {"locus_tag": "PMT9312_0001", "organism_strain": "Prochlorococcus MIT9312"},
            {"locus_tag": "SYNW0305", "organism_strain": "Synechococcus WH8102"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [
            [{"gene": gene_data}],
            homologs,
        ]

        result = json.loads(tool_fns["get_gene_details"](mock_ctx, gene_id="PMM0001"))

        assert len(result[0]["_homologs"]) == 2
        orgs = {h["organism_strain"] for h in result[0]["_homologs"]}
        assert "Prochlorococcus MIT9312" in orgs
        assert "Synechococcus WH8102" in orgs


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

    def test_include_orthologs_query_contains_ortholog(self, tool_fns, mock_ctx):
        """include_orthologs=True changes query to include ortholog relationships."""
        rows = [{"gene": "PMM0001", "log2fc": 1.5}]
        _conn_from(mock_ctx).execute_query.return_value = rows

        tool_fns["query_expression"](
            mock_ctx, gene_id="PMM0001", include_orthologs=True
        )

        called_cypher = _conn_from(mock_ctx).execute_query.call_args[0][0]
        assert "ortholog" in called_cypher.lower()

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
    """Verify get_homologs returns correct homolog data and merges expression."""

    def test_cross_organism_homologs(self, tool_fns, mock_ctx):
        """Homologs from MED4, MIT9312, WH8102 are all returned."""
        homologs = [
            {"locus_tag": "PMM0001", "organism_strain": "Prochlorococcus MED4",
             "gene_name": "dnaN"},
            {"locus_tag": "PMT9312_0001", "organism_strain": "Prochlorococcus MIT9312",
             "gene_name": "dnaN"},
            {"locus_tag": "SYNW0305", "organism_strain": "Synechococcus WH8102",
             "gene_name": "ftsH1"},
        ]
        _conn_from(mock_ctx).execute_query.return_value = homologs

        result = json.loads(
            tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")
        )

        assert len(result) == 3
        orgs = {h["organism_strain"] for h in result}
        assert orgs == {
            "Prochlorococcus MED4",
            "Prochlorococcus MIT9312",
            "Synechococcus WH8102",
        }

    def test_include_expression_merges_data(self, tool_fns, mock_ctx):
        """include_expression=True returns homologs + expression in merged dict."""
        homologs = [
            {"locus_tag": "PMT9312_0001", "organism_strain": "Prochlorococcus MIT9312"},
            {"locus_tag": "SYNW0305", "organism_strain": "Synechococcus WH8102"},
        ]
        expr = [
            {"gene": "PMM0001", "log2fc": 2.5, "condition": "coculture"},
            {"gene": "PMT9312_0001", "log2fc": 1.8, "condition": "coculture"},
        ]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [homologs, expr]

        result = json.loads(
            tool_fns["get_homologs"](
                mock_ctx, gene_id="PMM0001", include_expression=True
            )
        )

        assert "homologs" in result
        assert "expression" in result
        assert result["homologs"] == homologs
        assert result["expression"] == expr

    def test_all_ids_passed_to_expression_query(self, tool_fns, mock_ctx):
        """Expression query includes source gene + all homolog locus_tags."""
        homologs = [
            {"locus_tag": "PMT9312_0001", "organism_strain": "Prochlorococcus MIT9312"},
            {"locus_tag": "SYNW0305", "organism_strain": "Synechococcus WH8102"},
        ]
        expr = []
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [homologs, expr]

        tool_fns["get_homologs"](
            mock_ctx, gene_id="PMM0001", include_expression=True
        )

        # Second call is expression query — check gene_ids param
        expr_call = conn.execute_query.call_args_list[1]
        expr_kwargs = expr_call.kwargs
        expected_ids = ["PMM0001", "PMT9312_0001", "SYNW0305"]
        assert expr_kwargs["ids"] == expected_ids

    def test_homologs_without_expression_single_query(self, tool_fns, mock_ctx):
        """Without include_expression, only one query is executed."""
        homologs = [
            {"locus_tag": "PMT9312_0001", "organism_strain": "Prochlorococcus MIT9312"},
        ]
        _conn_from(mock_ctx).execute_query.return_value = homologs

        tool_fns["get_homologs"](mock_ctx, gene_id="PMM0001")

        assert _conn_from(mock_ctx).execute_query.call_count == 1

    def test_include_expression_two_queries(self, tool_fns, mock_ctx):
        """With include_expression, two queries are executed (homologs + expr)."""
        homologs = [
            {"locus_tag": "PMT9312_0001", "organism_strain": "Prochlorococcus MIT9312"},
        ]
        expr = [{"gene": "PMM0001", "log2fc": 1.0}]
        conn = _conn_from(mock_ctx)
        conn.execute_query.side_effect = [homologs, expr]

        tool_fns["get_homologs"](
            mock_ctx, gene_id="PMM0001", include_expression=True
        )

        assert conn.execute_query.call_count == 2
