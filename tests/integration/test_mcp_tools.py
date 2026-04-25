"""P1: Integration tests for MCP tool logic against live Neo4j.

These tests exercise the tool-level logic (query building + result handling)
without the MCP transport layer. They use the shared `conn` fixture from conftest.
"""

import json

import pytest

from multiomics_explorer.kg.queries_lib import (
    build_gene_stub,
    build_gene_details,
    build_gene_homologs,
    build_gene_homologs_summary,
    build_genes_by_homolog_group,
    build_genes_by_homolog_group_summary,
    build_list_experiments,
    build_list_experiments_summary,
    build_list_organisms,
    build_list_publications,
    build_list_publications_summary,
    build_resolve_gene,
    build_genes_by_function,
    build_search_homolog_groups,
    build_search_homolog_groups_summary,
)
from multiomics_explorer.api import functions as api
from multiomics_explorer.api.functions import _WRITE_KEYWORDS


@pytest.mark.kg
class TestKgSchema:
    def test_returns_nodes_and_relationships(self, conn):
        result = api.kg_schema(conn=conn)
        assert "Gene" in result["nodes"]
        assert len(result["relationships"]) > 0

    def test_gene_node_has_properties(self, conn):
        result = api.kg_schema(conn=conn)
        assert "properties" in result["nodes"]["Gene"]


@pytest.mark.kg
class TestGenesByFunction:
    def test_invalid_lucene_syntax_does_not_crash(self, conn):
        """Unbalanced brackets should trigger the Lucene escape fallback."""
        import re

        search_text = "DNA [repair"
        cypher, params = build_genes_by_function(search_text=search_text)
        try:
            results = conn.execute_query(cypher, **params)
        except Exception:
            # Retry with escaped Lucene chars (mirrors tools.py fallback logic)
            escaped = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', r'\\\g<0>', search_text)
            cypher, params = build_genes_by_function(search_text=escaped)
            results = conn.execute_query(cypher, **params)
        # Should not raise — may return 0 or more results
        assert isinstance(results, list)

    def test_basic_search_returns_results(self, conn):
        cypher, params = build_genes_by_function(search_text="photosystem")
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        assert "locus_tag" in results[0]


@pytest.mark.kg
class TestGeneHomologs:
    def test_detail_returns_flat_rows(self, conn):
        """build_gene_homologs returns flat gene×group rows."""
        cypher, params = build_gene_homologs(locus_tags=["PMM0845"])
        results = conn.execute_query(cypher, **params)
        assert len(results) > 0
        for r in results:
            assert r["locus_tag"] == "PMM0845"
            assert "group_id" in r
            assert "source" in r
            assert "consensus_product" in r
            assert "organism_name" in r

    def test_summary_returns_counts(self, conn):
        """build_gene_homologs_summary returns counts + breakdowns."""
        cypher, params = build_gene_homologs_summary(locus_tags=["PMM0845"])
        result = conn.execute_query(cypher, **params)[0]
        assert result["total_matching"] > 0
        assert len(result["by_organism"]) > 0
        assert len(result["by_source"]) > 0
        assert result["not_found"] == []
        assert result["no_groups"] == []

    def test_summary_not_found(self, conn):
        """Fake gene appears in not_found."""
        cypher, params = build_gene_homologs_summary(locus_tags=["FAKE_GENE_XYZ"])
        result = conn.execute_query(cypher, **params)[0]
        assert "FAKE_GENE_XYZ" in result["not_found"]


@pytest.mark.kg
class TestRunCypher:
    def test_valid_query_returns_results(self, conn):
        """Valid query returns envelope with rows and empty warnings."""
        result = api.run_cypher("MATCH (g:Gene) RETURN count(g) AS cnt", conn=conn)
        assert result["returned"] > 0
        assert result["warnings"] == []
        assert set(result.keys()) >= {"returned", "truncated", "warnings", "results"}

    def test_bad_label_produces_warnings(self, conn):
        """Query referencing a non-existent label returns non-empty warnings."""
        result = api.run_cypher(
            "MATCH (n:NonExistentLabel_XYZ) RETURN n LIMIT 1", conn=conn
        )
        assert len(result["warnings"]) > 0

    def test_write_query_raises_value_error(self, conn):
        """Write keywords raise ValueError before execution."""
        with pytest.raises(ValueError, match="Write operations"):
            api.run_cypher("CREATE (n:Gene {name: 'test'})", conn=conn)

    def test_syntax_error_raises_value_error(self, conn):
        """Syntax-invalid Cypher raises ValueError with a message."""
        with pytest.raises(ValueError, match="Syntax error"):
            api.run_cypher("MATC (n) RETURNN n LIMIT 1", conn=conn)


@pytest.mark.kg
class TestEdgeCases:
    def test_resolve_gene_empty_id(self, conn):
        cypher, params = build_resolve_gene(identifier="")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 0

    def test_gene_details_nonexistent(self, conn):
        cypher, params = build_gene_details(locus_tags=["FAKE_GENE_XYZ"])
        results = conn.execute_query(cypher, **params)
        assert results == []


@pytest.mark.kg
class TestListPublications:
    def test_no_filters_returns_all(self, conn):
        """Unfiltered query returns all publications."""
        cypher, params = build_list_publications()
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 15
        for r in results:
            assert "doi" in r
            assert "title" in r
            assert "experiment_count" in r

    def test_organism_filter(self, conn):
        """Organism filter returns subset with MED4 experiments."""
        cypher, params = build_list_publications(organism="MED4")
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 5

    def test_treatment_type_filter(self, conn):
        """Treatment type filter returns papers with coculture experiments."""
        cypher, params = build_list_publications(treatment_type="coculture")
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 3

    def test_author_filter(self, conn):
        """Author filter returns Chisholm lab papers."""
        cypher, params = build_list_publications(author="Chisholm")
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 2

    def test_experiment_count_positive(self, conn):
        """All publications with experiments have experiment_count > 0."""
        cypher, params = build_list_publications()
        results = conn.execute_query(cypher, **params)
        with_experiments = [r for r in results if r["experiment_count"] > 0]
        assert len(with_experiments) >= 15

    def test_summary_matches_data(self, conn):
        """Summary total_matching equals actual data row count (no limit)."""
        summary_cypher, summary_params = build_list_publications_summary(organism="MED4")
        summary = conn.execute_query(summary_cypher, **summary_params)[0]

        data_cypher, data_params = build_list_publications(organism="MED4")
        data = conn.execute_query(data_cypher, **data_params)

        assert summary["total_matching"] == len(data)
        assert summary["total_entries"] >= summary["total_matching"]


@pytest.mark.kg
class TestListOrganisms:
    def test_returns_all_organisms(self, conn):
        """Returns all OrganismTaxon nodes with precomputed stats."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        assert len(results) >= 13  # at least 13 strain-level organisms

    def test_expected_columns(self, conn):
        """Each result has all 11 compact columns."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        for col in ["organism_name", "genus", "species", "strain", "clade",
                     "ncbi_taxon_id", "gene_count", "publication_count",
                     "experiment_count", "treatment_types", "omics_types"]:
            assert col in results[0], f"Missing column: {col}"

    def test_verbose_adds_taxonomy(self, conn):
        """Verbose mode adds taxonomy hierarchy columns."""
        cypher, params = build_list_organisms(verbose=True)
        results = conn.execute_query(cypher, **params)
        for col in ["family", "order", "tax_class", "phylum",
                     "kingdom", "superkingdom", "lineage"]:
            assert col in results[0], f"Missing verbose column: {col}"

    def test_precomputed_gene_count_matches(self, conn):
        """Precomputed gene_count matches live count for MED4."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        med4 = [r for r in results if r["organism_name"] == "Prochlorococcus MED4"][0]
        assert med4["gene_count"] > 1900

    def test_precomputed_publication_count(self, conn):
        """MED4 has the most publications."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        med4 = [r for r in results if r["organism_name"] == "Prochlorococcus MED4"][0]
        assert med4["publication_count"] >= 10

    def test_treatment_types_not_empty(self, conn):
        """Organisms with publications have non-empty treatment_types."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        med4 = [r for r in results if r["organism_name"] == "Prochlorococcus MED4"][0]
        assert len(med4["treatment_types"]) >= 5

    def test_ordered_by_genus(self, conn):
        """Results are ordered by genus, then organism_name."""
        cypher, params = build_list_organisms()
        results = conn.execute_query(cypher, **params)
        genera = [r["genus"] for r in results if r["genus"] is not None]
        assert genera == sorted(genera)


@pytest.mark.kg
class TestListExperiments:
    """Integration tests for list_experiments against live KG."""

    # --- Summary mode ---

    def test_summary_no_filters(self, conn):
        """Summary returns all experiments with breakdowns."""
        result = api.list_experiments(summary=True, conn=conn)
        assert result["total_matching"] == result["total_entries"]
        assert result["total_matching"] >= 70
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert result["results"] == []
        assert len(result["by_organism"]) >= 8
        assert len(result["by_treatment_type"]) >= 8
        assert len(result["by_omics_type"]) >= 2

    def test_summary_organism_filter(self, conn):
        """Organism filter narrows summary."""
        result = api.list_experiments(organism="MED4", summary=True, conn=conn)
        assert result["total_matching"] < result["total_entries"]
        assert result["total_matching"] >= 20

    def test_summary_breakdown_counts_sum(self, conn):
        """by_organism experiment_counts sum to total_matching."""
        result = api.list_experiments(summary=True, conn=conn)
        org_total = sum(b["count"] for b in result["by_organism"])
        assert org_total == result["total_matching"]

    def test_summary_treatment_type_counts_sum(self, conn):
        """by_treatment_type counts >= total_matching (experiments can have multiple treatment_types)."""
        result = api.list_experiments(summary=True, conn=conn)
        tt_total = sum(b["count"] for b in result["by_treatment_type"])
        assert tt_total >= result["total_matching"]

    def test_summary_omics_type_counts_sum(self, conn):
        """by_omics_type counts sum to total_matching."""
        result = api.list_experiments(summary=True, conn=conn)
        omics_total = sum(b["count"] for b in result["by_omics_type"])
        assert omics_total == result["total_matching"]

    # --- Detail mode ---

    def test_detail_no_filters(self, conn):
        """Detail returns experiments up to limit."""
        result = api.list_experiments(limit=50, conn=conn)
        assert result["returned"] == min(50, result["total_matching"])
        assert len(result["results"]) == result["returned"]
        # Breakdowns also present
        assert len(result["by_organism"]) >= 8

    def test_detail_organism_filter(self, conn):
        """Organism filter returns MED4 experiments."""
        result = api.list_experiments(organism="MED4", conn=conn)
        assert result["total_matching"] >= 20
        for r in result["results"]:
            assert "MED4" in r["organism_name"] or (
                r.get("coculture_partner") and "MED4" in r.get("coculture_partner", "")
            )

    def test_detail_treatment_type_filter(self, conn):
        """Treatment type list filter works."""
        result = api.list_experiments(
            treatment_type=["coculture"], conn=conn,
        )
        assert result["total_matching"] >= 10
        for r in result["results"]:
            assert "coculture" in r["treatment_type"]

    def test_detail_omics_type_filter(self, conn):
        """Omics type list filter works."""
        result = api.list_experiments(
            omics_type=["PROTEOMICS"], conn=conn,
        )
        assert result["total_matching"] >= 1
        for r in result["results"]:
            assert r["omics_type"] == "PROTEOMICS"

    def test_detail_time_course_only(self, conn):
        """time_course_only returns only time-course experiments."""
        result = api.list_experiments(
            time_course_only=True, conn=conn,
        )
        assert result["total_matching"] >= 20
        for r in result["results"]:
            assert r["is_time_course"] is True

    def test_detail_expected_columns(self, conn):
        """Each result has compact columns."""
        result = api.list_experiments(limit=5, conn=conn)
        for r in result["results"]:
            for col in ["experiment_id", "experiment_name",
                        "publication_doi", "organism_name",
                        "treatment_type", "omics_type", "is_time_course",
                        "table_scope", "gene_count", "genes_by_status"]:
                assert col in r, f"Missing column: {col}"

    def test_detail_is_time_course_is_bool(self, conn):
        """is_time_course is bool, not string."""
        result = api.list_experiments(limit=5, conn=conn)
        for r in result["results"]:
            assert isinstance(r["is_time_course"], bool)

    def test_detail_gene_count_nonnegative(self, conn):
        """gene_count and genes_by_status counts are >= 0."""
        result = api.list_experiments(conn=conn)
        for r in result["results"]:
            assert r["gene_count"] >= 0
            gbs = r["genes_by_status"]
            assert gbs["significant_up"] >= 0
            assert gbs["significant_down"] >= 0
            assert gbs["not_significant"] >= 0

    def test_detail_time_course_has_timepoints(self, conn):
        """Time-course experiments have timepoints with >1 entry."""
        result = api.list_experiments(
            time_course_only=True, limit=5, conn=conn,
        )
        for r in result["results"]:
            assert "timepoints" in r
            assert len(r["timepoints"]) > 1
            tp = r["timepoints"][0]
            assert "timepoint" in tp
            assert "timepoint_order" in tp
            assert "gene_count" in tp
            assert "genes_by_status" in tp

    def test_detail_non_time_course_no_timepoints(self, conn):
        """Non-time-course experiments have no timepoints key."""
        result = api.list_experiments(conn=conn)
        non_tc = [r for r in result["results"] if not r["is_time_course"]]
        assert len(non_tc) > 0
        for r in non_tc:
            assert "timepoints" not in r

    # --- Consistency ---

    def test_summary_consistency(self, conn):
        """Summary total_matching == detail total row count (same filters)."""
        kwargs = dict(organism="MED4", treatment_type=["coculture"])
        summary = api.list_experiments(**kwargs, summary=True, conn=conn)
        detail = api.list_experiments(**kwargs, limit=500, conn=conn)
        assert summary["total_matching"] == detail["total_matching"]
        assert summary["total_matching"] == len(detail["results"])


@pytest.mark.kg
class TestListFilterValues:
    def test_returns_envelope_keys(self, conn):
        result = api.list_filter_values(conn=conn)
        for key in ("filter_type", "total_entries", "returned", "truncated", "results"):
            assert key in result

    def test_filter_type_is_gene_category(self, conn):
        result = api.list_filter_values(conn=conn)
        assert result["filter_type"] == "gene_category"

    def test_results_have_value_and_count(self, conn):
        result = api.list_filter_values(conn=conn)
        assert len(result["results"]) >= 1
        assert "value" in result["results"][0]
        assert "count" in result["results"][0]


@pytest.mark.kg
class TestDifferentialExpressionByGene:
    def test_organism_summary(self, conn):
        """Organism-only summary returns counts without rows."""
        result = api.differential_expression_by_gene(
            organism="MED4", summary=True, conn=conn,
        )
        assert "MED4" in result["organism_name"]
        assert result["total_matching"] > 0
        assert result["results"] == []
        assert result["truncated"] is True

    def test_locus_tags_with_limit(self, conn):
        """Locus tags return detail rows sorted by |log2fc|."""
        result = api.differential_expression_by_gene(
            locus_tags=["PMM0001"], limit=5, conn=conn,
        )
        assert result["returned"] <= 5
        assert result["matching_genes"] >= 1
        for row in result["results"]:
            assert row["locus_tag"] == "PMM0001"
            assert "log2fc" in row
            assert "expression_status" in row

    def test_significant_only(self, conn):
        """significant_only filters to significant rows."""
        result = api.differential_expression_by_gene(
            organism="MED4", significant_only=True, limit=5, conn=conn,
        )
        for row in result["results"]:
            assert row["expression_status"] in ("significant_up", "significant_down")

    def test_no_filters_raises(self, conn):
        """All three None raises ValueError."""
        with pytest.raises(ValueError, match="at least one"):
            api.differential_expression_by_gene(conn=conn)

    def test_summary_consistency(self, conn):
        """Summary total_matching matches detail row count (small dataset)."""
        kwargs = dict(locus_tags=["PMM0001"], conn=conn)
        summary = api.differential_expression_by_gene(**kwargs, summary=True)
        detail = api.differential_expression_by_gene(**kwargs, limit=500)
        assert summary["total_matching"] == detail["total_matching"]
        assert summary["total_matching"] == len(detail["results"])


@pytest.mark.kg
class TestDifferentialExpressionByOrtholog:
    KNOWN_GROUP = "cyanorak:CK_00000570"

    def test_single_group(self, conn):
        """Single group returns results with expected fields."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], limit=10, conn=conn,
        )
        assert result["total_matching"] > 0
        assert result["matching_genes"] >= 1
        assert result["matching_groups"] == 1
        assert result["returned"] >= 1
        row = result["results"][0]
        assert row["group_id"] == self.KNOWN_GROUP
        for key in ("experiment_id", "treatment_type", "organism_name",
                     "timepoint_order", "genes_with_expression", "total_genes",
                     "significant_up", "significant_down", "not_significant"):
            assert key in row

    def test_multiple_groups(self, conn):
        """Multiple groups return results from all groups."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP, "cyanorak:CK_00000364"],
            limit=200, conn=conn,
        )
        group_ids = {r["group_id"] for r in result["results"]}
        assert len(group_ids) >= 2
        assert result["matching_groups"] >= 2

    def test_organisms_filter(self, conn):
        """Organisms filter restricts by_organism and results."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], organisms=["MED4"],
            limit=50, conn=conn,
        )
        for row in result["results"]:
            assert "MED4" in row["organism_name"]
        organisms = [b["organism_name"] for b in result["by_organism"]]
        assert all("MED4" in o for o in organisms)

    def test_significant_only(self, conn):
        """significant_only filters to significant rows only."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], significant_only=True,
            limit=50, conn=conn,
        )
        for row in result["results"]:
            # Each row should have at least one significant gene
            assert row["significant_up"] + row["significant_down"] > 0
        rbs = result["rows_by_status"]
        assert rbs.get("not_significant", 0) == 0

    def test_direction_up(self, conn):
        """direction='up' only counts significant_up in rows_by_status."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], direction="up",
            limit=50, conn=conn,
        )
        rbs = result["rows_by_status"]
        assert rbs.get("significant_down", 0) == 0
        assert rbs.get("not_significant", 0) == 0

    def test_verbose_adds_fields(self, conn):
        """verbose=True adds experiment_name, treatment, omics_type."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], verbose=True, limit=1, conn=conn,
        )
        if result["results"]:
            row = result["results"][0]
            for key in ("experiment_name", "treatment", "omics_type",
                        "table_scope"):
                assert key in row

    def test_not_found_groups(self, conn):
        """Fake group ID appears in not_found_groups."""
        result = api.differential_expression_by_ortholog(
            group_ids=["FAKE_GROUP_ID"], conn=conn,
        )
        assert "FAKE_GROUP_ID" in result["not_found_groups"]
        assert result["total_matching"] == 0
        assert result["results"] == []

    def test_genes_with_expression_le_total_genes(self, conn):
        """genes_with_expression <= total_genes in every result row."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP], limit=50, conn=conn,
        )
        for row in result["results"]:
            assert row["genes_with_expression"] <= row["total_genes"]

    def test_empty_group_ids_raises(self, conn):
        """Empty group_ids raises ValueError."""
        with pytest.raises(ValueError, match="group_ids must not be empty"):
            api.differential_expression_by_ortholog(group_ids=[], conn=conn)

    def test_top_groups_and_experiments(self, conn):
        """top_groups and top_experiments are populated."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP, "cyanorak:CK_00000364"],
            limit=10, conn=conn,
        )
        assert len(result["top_groups"]) >= 1
        assert len(result["top_experiments"]) >= 1
        tg = result["top_groups"][0]
        assert "group_id" in tg
        assert "significant_genes" in tg
        te = result["top_experiments"][0]
        assert "experiment_id" in te
        assert "significant_genes" in te

    def test_diagnostics_with_combined_filters(self, conn):
        """Diagnostics work with organisms + experiment_ids + direction."""
        result = api.differential_expression_by_ortholog(
            group_ids=[self.KNOWN_GROUP],
            organisms=["FAKE_ORG", "MED4"],
            experiment_ids=["FAKE_EXP"],
            direction="up",
            conn=conn,
        )
        assert "FAKE_ORG" in result["not_found_organisms"]
        assert "FAKE_EXP" in result["not_found_experiments"]


# ---------------------------------------------------------------------------
# search_homolog_groups
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestSearchHomologGroups:
    def test_basic_search(self, conn):
        """Text search returns matching groups with expected columns."""
        result = api.search_homolog_groups("photosynthesis", conn=conn)
        assert result["total_matching"] >= 5
        assert result["returned"] >= 1
        row = result["results"][0]
        for key in ("group_id", "group_name", "consensus_gene_name",
                     "consensus_product", "source", "taxonomic_level",
                     "specificity_rank", "member_count", "organism_count", "score"):
            assert key in row

    def test_source_filter_cyanorak(self, conn):
        """Source filter restricts to cyanorak groups only."""
        result = api.search_homolog_groups(
            "photosynthesis", source="cyanorak", conn=conn,
        )
        assert result["total_matching"] >= 1
        for row in result["results"]:
            assert row["source"] == "cyanorak"
        sources = [b["source"] for b in result["by_source"]]
        assert sources == ["cyanorak"]

    def test_source_filter_eggnog(self, conn):
        """Source filter restricts to eggnog groups only."""
        result = api.search_homolog_groups(
            "polymerase", source="eggnog", conn=conn,
        )
        assert result["total_matching"] >= 1
        for row in result["results"]:
            assert row["source"] == "eggnog"

    def test_max_specificity_rank(self, conn):
        """max_specificity_rank caps group breadth."""
        result = api.search_homolog_groups(
            "photosynthesis", max_specificity_rank=0, conn=conn,
        )
        for row in result["results"]:
            assert row["specificity_rank"] <= 0

    def test_verbose_adds_fields(self, conn):
        """Verbose mode includes description and genera."""
        result = api.search_homolog_groups(
            "nitrogen", verbose=True, limit=1, conn=conn,
        )
        if result["results"]:
            row = result["results"][0]
            for key in ("description", "functional_description",
                        "genera", "has_cross_genus_members"):
                assert key in row

    def test_summary_mode(self, conn):
        """Summary mode returns counts without detail rows."""
        result = api.search_homolog_groups(
            "photosynthesis", summary=True, conn=conn,
        )
        assert result["total_matching"] >= 5
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert len(result["by_source"]) >= 1
        assert len(result["by_level"]) >= 1

    def test_summary_consistency(self, conn):
        """Summary total_matching matches detail row count."""
        summary = api.search_homolog_groups(
            "kinase", summary=True, conn=conn,
        )
        detail = api.search_homolog_groups(
            "kinase", limit=1000, conn=conn,
        )
        assert summary["total_matching"] == detail["total_matching"]
        assert detail["total_matching"] == len(detail["results"])

    def test_empty_search_raises(self, conn):
        """Empty search_text raises ValueError."""
        with pytest.raises(ValueError, match="search_text"):
            api.search_homolog_groups("", conn=conn)

    def test_invalid_source_raises(self, conn):
        """Invalid source enum raises ValueError."""
        with pytest.raises(ValueError, match="Invalid source"):
            api.search_homolog_groups("kinase", source="invalid", conn=conn)

    def test_score_fields_populated(self, conn):
        """score_max and score_median are populated when results exist."""
        result = api.search_homolog_groups("photosynthesis", conn=conn)
        assert result["score_max"] is not None
        assert result["score_median"] is not None
        assert result["score_max"] >= result["score_median"]


# ---------------------------------------------------------------------------
# genes_by_homolog_group
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGenesByHomologGroup:
    KNOWN_GROUP = "cyanorak:CK_00000570"

    def test_basic_lookup(self, conn):
        """Single group returns member genes."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], conn=conn,
        )
        assert result["total_matching"] >= 1
        assert result["returned"] >= 1
        row = result["results"][0]
        for key in ("locus_tag", "gene_name", "product",
                     "organism_name", "gene_category", "group_id"):
            assert key in row
        assert row["group_id"] == self.KNOWN_GROUP

    def test_organisms_filter(self, conn):
        """Organisms filter restricts results."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], organisms=["MED4"], conn=conn,
        )
        for row in result["results"]:
            assert "MED4" in row["organism_name"]

    def test_verbose_adds_fields(self, conn):
        """Verbose mode adds gene_summary and group context."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], verbose=True, limit=1, conn=conn,
        )
        if result["results"]:
            row = result["results"][0]
            for key in ("gene_summary", "function_description",
                        "consensus_product", "source"):
                assert key in row

    def test_summary_mode(self, conn):
        """Summary mode returns counts without detail rows."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], summary=True, conn=conn,
        )
        assert result["total_matching"] >= 1
        assert result["results"] == []
        assert result["returned"] == 0

    def test_not_found_groups(self, conn):
        """Fake group ID appears in not_found_groups."""
        result = api.genes_by_homolog_group(
            group_ids=["FAKE_GROUP_XYZ"], conn=conn,
        )
        assert "FAKE_GROUP_XYZ" in result["not_found_groups"]
        assert result["total_matching"] == 0

    def test_not_matched_organisms(self, conn):
        """Organism that exists but has no members appears in not_matched."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP],
            organisms=["FAKE_ORG", "MED4"], conn=conn,
        )
        assert "FAKE_ORG" in result["not_found_organisms"]

    def test_empty_group_ids_raises(self, conn):
        """Empty group_ids raises ValueError."""
        with pytest.raises(ValueError, match="group_ids must not be empty"):
            api.genes_by_homolog_group(group_ids=[], conn=conn)

    def test_multiple_groups(self, conn):
        """Multiple groups return genes from all groups."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP, "cyanorak:CK_00000364"],
            limit=200, conn=conn,
        )
        group_ids = {r["group_id"] for r in result["results"]}
        assert len(group_ids) >= 2

    def test_summary_consistency(self, conn):
        """Summary total_matching matches detail row count."""
        summary = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], summary=True, conn=conn,
        )
        detail = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], limit=500, conn=conn,
        )
        assert summary["total_matching"] == detail["total_matching"]
        assert detail["total_matching"] == len(detail["results"])

    def test_top_groups_and_categories(self, conn):
        """top_groups and top_categories are populated."""
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP, "cyanorak:CK_00000364"],
            conn=conn,
        )
        assert len(result["top_groups"]) >= 1
        assert result["top_groups"][0]["group_id"] in (
            self.KNOWN_GROUP, "cyanorak:CK_00000364"
        )
        assert result["total_categories"] >= 1


# ---------------------------------------------------------------------------
# gene_overview
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneOverview:
    def test_single_gene(self, conn):
        """Single gene returns overview with routing signals."""
        result = api.gene_overview(["PMM0001"], conn=conn)
        assert result["total_matching"] == 1
        assert result["returned"] == 1
        row = result["results"][0]
        assert row["locus_tag"] == "PMM0001"
        for key in ("gene_name", "product", "gene_category",
                     "annotation_quality", "organism_name",
                     "annotation_types", "expression_edge_count",
                     "significant_up_count", "significant_down_count",
                     "closest_ortholog_group_size", "closest_ortholog_genera"):
            assert key in row

    def test_batch_pro_and_alt(self, conn):
        """Batch with Pro + Alt genes returns both."""
        result = api.gene_overview(
            ["PMM1428", "EZ55_00275"], conn=conn,
        )
        assert result["total_matching"] == 2
        tags = {r["locus_tag"] for r in result["results"]}
        assert tags == {"PMM1428", "EZ55_00275"}

    def test_not_found(self, conn):
        """Non-existent gene appears in not_found."""
        result = api.gene_overview(
            ["PMM0001", "FAKE_GENE_XYZ"], conn=conn,
        )
        assert "FAKE_GENE_XYZ" in result["not_found"]
        assert result["total_matching"] == 1

    def test_summary_mode(self, conn):
        """Summary mode returns counts without detail rows."""
        result = api.gene_overview(
            ["PMM0001"], summary=True, conn=conn,
        )
        assert result["total_matching"] == 1
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["has_expression"] >= 0
        assert result["has_orthologs"] >= 0

    def test_verbose_adds_fields(self, conn):
        """Verbose mode adds gene_summary and function_description."""
        result = api.gene_overview(
            ["PMM0001"], verbose=True, conn=conn,
        )
        row = result["results"][0]
        for key in ("gene_summary", "function_description", "all_identifiers"):
            assert key in row

    def test_by_organism_breakdown(self, conn):
        """by_organism is populated for cross-organism batch."""
        result = api.gene_overview(
            ["PMM1428", "EZ55_00275"], conn=conn,
        )
        assert len(result["by_organism"]) == 2
        org_total = sum(b["count"] for b in result["by_organism"])
        assert org_total == result["total_matching"]

    def test_expression_signals(self, conn):
        """MED4 gene has expression data available."""
        result = api.gene_overview(["PMM0001"], conn=conn)
        row = result["results"][0]
        assert row["expression_edge_count"] > 0

    def test_summary_consistency(self, conn):
        """Summary total_matching matches detail row count."""
        tags = ["PMM0001", "PMM0845", "EZ55_00275"]
        summary = api.gene_overview(tags, summary=True, conn=conn)
        detail = api.gene_overview(tags, limit=500, conn=conn)
        assert summary["total_matching"] == detail["total_matching"]
        assert detail["total_matching"] == len(detail["results"])



@pytest.mark.kg
class TestOntologyLandscapeIntegration:
    def test_med4_all_ontologies_cyanorak_l1_rank1_among_hierarchical(self, conn):
        from multiomics_explorer.api.functions import ontology_landscape
        result = ontology_landscape(
            organism="MED4", limit=None, conn=conn,
        )
        hierarchical = [
            r for r in result["results"]
            if r["n_levels_in_ontology"] > 1
        ]
        assert hierarchical, "expected at least one hierarchical row"
        top_hier = min(hierarchical, key=lambda r: r["relevance_rank"])
        assert top_hier["ontology_type"] == "cyanorak_role"
        assert top_hier["level"] == 1, (
            f"expected cyanorak_role L1, got L{top_hier['level']}"
        )

    def test_med4_experiment_branch_coverage_fields(self, conn):
        from multiomics_explorer.api.functions import ontology_landscape
        result = ontology_landscape(
            organism="MED4",
            ontology="cyanorak_role",
            experiment_ids=[
                "10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq",
                "THIS_DOES_NOT_EXIST",
            ],
            limit=None,
            conn=conn,
        )
        assert "THIS_DOES_NOT_EXIST" in result["not_found"]
        # Coverage fields present on every row
        for r in result["results"]:
            assert "min_exp_coverage" in r
            assert "median_exp_coverage" in r
            assert "max_exp_coverage" in r


@pytest.mark.kg
class TestPathwayEnrichmentIntegration:
    """Live-KG integration for pathway_enrichment."""

    def test_b1_reproduction_cyanorak_level1(self, conn):
        """MED4 × CyanoRak level 1 produces recognizable enriched pathways.

        Baseline: B1 analysis found enrichments in N-metabolism (E.4),
        photosynthesis (J.1–J.8), and ribosomal (K.2) categories.

        Uses background='organism' to give a meaningful universe size;
        table_scope background would be too small per-cluster to yield significance.
        """
        from multiomics_explorer.api.functions import pathway_enrichment, list_experiments
        all_experiments = list_experiments(organism="MED4", limit=100, conn=conn)
        # Filter to MED4-only experiments (exclude co-culture rows where Alteromonas is primary)
        exp_ids = [
            e["experiment_id"]
            for e in all_experiments["results"]
            if "MED4" in e.get("organism_name", "")
        ]
        result = pathway_enrichment(
            organism="MED4",
            experiment_ids=exp_ids,
            ontology="cyanorak_role",
            level=1,
            direction="both",
            significant_only=True,
            background="organism",
            conn=conn,
        )
        envelope = result.to_envelope()
        assert envelope["total_matching"] > 0
        assert envelope["n_significant"] > 0
        top_terms = {p["term_id"] for p in envelope["top_pathways_by_padj"]}
        expected_family_prefixes = ("cyanorak.role:E.", "cyanorak.role:J.", "cyanorak.role:K.")
        assert any(any(t.startswith(p) for p in expected_family_prefixes) for t in top_terms), (
            f"Expected at least one E./J./K. pathway; got {top_terms}"
        )

    def test_organism_background(self, conn):
        """`background='organism'` fetches the full MED4 gene set."""
        from multiomics_explorer.api.functions import pathway_enrichment, list_experiments
        all_experiments = list_experiments(organism="MED4", limit=20, conn=conn)
        exp_ids = [
            e["experiment_id"]
            for e in all_experiments["results"]
            if "MED4" in e.get("organism_name", "")
        ][:1]
        result = pathway_enrichment(
            organism="MED4",
            experiment_ids=exp_ids,
            ontology="cyanorak_role",
            level=1,
            background="organism",
            conn=conn,
        )
        assert result.to_envelope()["total_matching"] >= 0

    def test_explicit_background_list(self, conn):
        """`background=<list>` uses caller's universe."""
        from multiomics_explorer.api.functions import pathway_enrichment, list_experiments
        all_experiments = list_experiments(organism="MED4", limit=20, conn=conn)
        med4_exps = [
            e["experiment_id"]
            for e in all_experiments["results"]
            if "MED4" in e.get("organism_name", "")
        ]
        exp_ids = med4_exps[:1]
        custom_bg = [f"PMM{i:04d}" for i in range(1, 501)]
        result = pathway_enrichment(
            organism="MED4",
            experiment_ids=exp_ids,
            ontology="cyanorak_role",
            level=1,
            background=custom_bg,
            conn=conn,
        )
        assert result.to_envelope()["cluster_summary"]["universe_size_max"] <= len(custom_bg)

    def test_clusters_skipped_for_undersized(self, conn):
        """Very high min_gene_set_size forces all clusters to be skipped."""
        from multiomics_explorer.api.functions import pathway_enrichment, list_experiments
        all_experiments = list_experiments(organism="MED4", limit=20, conn=conn)
        med4_exps = [
            e["experiment_id"]
            for e in all_experiments["results"]
            if "MED4" in e.get("organism_name", "")
        ]
        exp_ids = med4_exps[:1]
        result = pathway_enrichment(
            organism="MED4",
            experiment_ids=exp_ids,
            ontology="cyanorak_role",
            level=1,
            min_gene_set_size=100000,
            max_gene_set_size=None,
            conn=conn,
        )
        assert result.to_envelope()["clusters_skipped"], "expected clusters skipped under impossible min filter"


@pytest.mark.kg
class TestClusterEnrichmentIntegration:
    """Live-KG integration for cluster_enrichment."""

    def test_basic_call(self, conn):
        from multiomics_explorer.api import list_clustering_analyses, cluster_enrichment
        analyses = list_clustering_analyses(limit=1, conn=conn)
        if not analyses["results"]:
            pytest.skip("No clustering analyses in KG")
        analysis = analyses["results"][0]
        result = cluster_enrichment(
            analysis_id=analysis["analysis_id"],
            organism=analysis["organism_name"],
            ontology="cyanorak_role",
            level=1,
            pvalue_cutoff=0.99,
            conn=conn,
        )
        envelope = result.to_envelope()
        assert isinstance(envelope["results"], list)
        assert result.params["background_mode"] == "cluster_union"

    def test_organism_background_differs(self, conn):
        from multiomics_explorer.api import list_clustering_analyses, cluster_enrichment
        analyses = list_clustering_analyses(limit=1, conn=conn)
        if not analyses["results"]:
            pytest.skip("No clustering analyses in KG")
        analysis = analyses["results"][0]
        r_union = cluster_enrichment(
            analysis_id=analysis["analysis_id"],
            organism=analysis["organism_name"],
            ontology="cyanorak_role", level=1,
            background="cluster_union", conn=conn,
        )
        r_org = cluster_enrichment(
            analysis_id=analysis["analysis_id"],
            organism=analysis["organism_name"],
            ontology="cyanorak_role", level=1,
            background="organism", conn=conn,
        )
        # organism background must be >= cluster_union background per cluster
        union_max = max((len(v) for v in r_union.inputs.background.values()), default=0)
        org_max = max((len(v) for v in r_org.inputs.background.values()), default=0)
        assert org_max >= union_max


@pytest.mark.kg
class TestListDerivedMetrics:
    """Live-KG integration tests for list_derived_metrics."""

    def test_no_filters_13_dms(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(conn=conn, limit=None)
        assert out["total_entries"] == 13
        assert out["total_matching"] == 13
        assert len(out["results"]) == 13

    def test_value_kind_numeric_6(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(value_kind="numeric", conn=conn, limit=None)
        assert out["total_matching"] == 6
        assert all(r["value_kind"] == "numeric" for r in out["results"])
        assert all(r["compartment"] == "whole_cell" for r in out["results"])

    def test_value_kind_boolean_6(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(value_kind="boolean", conn=conn, limit=None)
        assert out["total_matching"] == 6
        # 4 NATL2A + 2 MIT1002
        organisms = {r["organism_name"] for r in out["results"]}
        assert organisms == {
            "Prochlorococcus NATL2A", "Alteromonas macleodii MIT1002",
        }

    def test_value_kind_categorical_1(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(value_kind="categorical", conn=conn, limit=None)
        assert out["total_matching"] == 1
        row = out["results"][0]
        assert row["metric_type"] == "darkness_survival_class"
        assert row["allowed_categories"] is not None
        assert len(row["allowed_categories"]) == 3

    def test_rankable_true_4(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(rankable=True, conn=conn, limit=None)
        assert out["total_matching"] == 4
        assert all(r["rankable"] is True for r in out["results"])

    def test_rankable_false_9(self, conn):
        """Sanity-checks bool→'false' string coercion path.
        Baseline updated from plan's 2 to 9: boolean DMs (periodic_*, darkness_survival_class)
        also carry rankable='false', giving 2 numeric + 6 boolean + 1 categorical = 9.
        """
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(rankable=False, conn=conn, limit=None)
        assert out["total_matching"] == 9
        metric_types = {r["metric_type"] for r in out["results"]}
        # The two non-rankable numeric DMs are always in this set
        assert "peak_time_protein_h" in metric_types
        assert "peak_time_transcript_h" in metric_types
        assert all(r["rankable"] is False for r in out["results"])

    def test_has_p_value_true_empty(self, conn):
        """Intentional: no DM in current KG has p-values."""
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(has_p_value=True, conn=conn, limit=None)
        assert out["total_matching"] == 0
        assert out["results"] == []

    def test_organism_short_code(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(organism="MED4", conn=conn, limit=None)
        assert out["total_matching"] == 6
        assert all(r["organism_name"] == "Prochlorococcus MED4" for r in out["results"])

    def test_organism_full_name(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(
            organism="Prochlorococcus NATL2A", conn=conn, limit=None)
        assert out["total_matching"] == 5

    def test_organism_alteromonas(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(organism="MIT1002", conn=conn, limit=None)
        assert out["total_matching"] == 2

    def test_search_text_diel_amplitude(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(search_text="diel amplitude", conn=conn, limit=5)
        # Top hits must include both diel_amplitude_* DMs
        top_metric_types = [r["metric_type"] for r in out["results"][:2]]
        assert "diel_amplitude_protein_log2" in top_metric_types
        assert "diel_amplitude_transcript_log2" in top_metric_types
        assert out["score_max"] is not None
        assert out["score_median"] is not None

    def test_publication_biller_7(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(
            publication_doi=["10.1128/mSystems.00040-18"], conn=conn, limit=None)
        assert out["total_matching"] == 7

    def test_derived_metric_ids_direct(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        target = (
            "derived_metric:journal.pone.0043432:"
            "table_s2_waldbauer_diel_metrics:damping_ratio"
        )
        out = list_derived_metrics(derived_metric_ids=[target], conn=conn)
        assert out["total_matching"] == 1
        assert out["results"][0]["derived_metric_id"] == target

    def test_summary_results_empty(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(summary=True, conn=conn)
        assert out["results"] == []
        assert out["returned"] == 0
        assert len(out["by_value_kind"]) == 3  # numeric, boolean, categorical
        assert len(out["by_organism"]) == 3

    def test_verbose_adds_fields(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(verbose=True, limit=1, conn=conn)
        row = out["results"][0]
        assert "treatment" in row
        assert "light_condition" in row
        assert "experimental_context" in row
        # p_value_threshold NOT in Cypher — still keyed in Pydantic default, absent here
        assert row.get("p_value_threshold") is None

    def test_envelope_keys_always_present(self, conn):
        """Zero-row filter case: breakdowns are [], not missing."""
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(
            derived_metric_ids=["nonexistent:id"], conn=conn, limit=None)
        assert out["total_matching"] == 0
        for key in (
            "by_organism", "by_value_kind", "by_metric_type", "by_compartment",
            "by_omics_type", "by_treatment_type", "by_background_factors",
            "by_growth_phase",
        ):
            assert key in out
            assert out[key] == []
        assert out["results"] == []
        assert out["score_max"] is None

    def test_pagination_offset(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        page1 = list_derived_metrics(conn=conn, limit=5, offset=0)
        page2 = list_derived_metrics(conn=conn, limit=5, offset=5)
        page1_ids = {r["derived_metric_id"] for r in page1["results"]}
        page2_ids = {r["derived_metric_id"] for r in page2["results"]}
        assert page1_ids.isdisjoint(page2_ids)
        assert page1["truncated"] is True
        assert page2["truncated"] is True  # 5 + 5 = 10 < 13
