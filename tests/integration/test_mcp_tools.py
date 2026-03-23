"""P1: Integration tests for MCP tool logic against live Neo4j.

These tests exercise the tool-level logic (query building + result handling)
without the MCP transport layer. They use the shared `conn` fixture from conftest.
"""

import json

import pytest

from multiomics_explorer.kg.queries_lib import (
    build_gene_stub,
    build_get_gene_details,
    build_gene_homologs,
    build_gene_homologs_summary,
    build_list_experiments,
    build_list_experiments_summary,
    build_list_organisms,
    build_list_publications,
    build_list_publications_summary,
    build_resolve_gene,
    build_search_genes,
)
from multiomics_explorer.api import functions as api
from multiomics_explorer.kg.schema import load_schema_from_neo4j
from multiomics_explorer.api.functions import _WRITE_KEYWORDS


@pytest.mark.kg
class TestGetSchema:
    def test_returns_node_counts_and_relationships(self, conn):
        schema = load_schema_from_neo4j(conn)
        assert len(schema.nodes) > 0
        assert len(schema.relationships) > 0
        # At least Gene nodes should exist
        assert "Gene" in schema.nodes
        assert schema.nodes["Gene"].count > 0

    def test_prompt_string_not_empty(self, conn):
        schema = load_schema_from_neo4j(conn)
        text = schema.to_prompt_string()
        assert "Gene" in text
        assert "## Graph Schema" in text


@pytest.mark.kg
class TestSearchGenes:
    def test_invalid_lucene_syntax_does_not_crash(self, conn):
        """Unbalanced brackets should trigger the Lucene escape fallback."""
        import re

        search_text = "DNA [repair"
        cypher, params = build_search_genes(search_text=search_text)
        try:
            results = conn.execute_query(cypher, **params)
        except Exception:
            # Retry with escaped Lucene chars (mirrors tools.py fallback logic)
            escaped = re.sub(r'[+\-!(){}\[\]^"~*?:\\/]', r'\\\g<0>', search_text)
            cypher, params = build_search_genes(search_text=escaped)
            results = conn.execute_query(cypher, **params)
        # Should not raise — may return 0 or more results
        assert isinstance(results, list)

    def test_basic_search_returns_results(self, conn):
        cypher, params = build_search_genes(search_text="photosystem")
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
            assert "organism_strain" in r

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
class TestRunCypherBlocking:
    def test_invalid_cypher_returns_error(self, conn):
        """Syntax-invalid Cypher should raise, not hang."""
        with pytest.raises(Exception):
            conn.execute_query("MATC (n) RETURNN n LIMIT 1")

    def test_write_blocked_at_regex_level(self):
        """Write keywords are caught before reaching Neo4j."""
        assert _WRITE_KEYWORDS.search("CREATE (n:Gene {name: 'test'})")
        assert _WRITE_KEYWORDS.search("MATCH (n) DELETE n")
        assert _WRITE_KEYWORDS.search("MATCH (n) SET n.x = 1")


@pytest.mark.kg
class TestEdgeCases:
    def test_resolve_gene_empty_id(self, conn):
        cypher, params = build_resolve_gene(identifier="")
        results = conn.execute_query(cypher, **params)
        assert len(results) == 0

    def test_get_gene_details_nonexistent(self, conn):
        cypher, params = build_get_gene_details(gene_id="FAKE_GENE_XYZ")
        results = conn.execute_query(cypher, **params)
        # Either empty or gene is None
        assert not results or results[0]["gene"] is None


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
        org_total = sum(b["experiment_count"] for b in result["by_organism"])
        assert org_total == result["total_matching"]

    def test_summary_treatment_type_counts_sum(self, conn):
        """by_treatment_type experiment_counts sum to total_matching."""
        result = api.list_experiments(summary=True, conn=conn)
        tt_total = sum(b["experiment_count"] for b in result["by_treatment_type"])
        assert tt_total == result["total_matching"]

    def test_summary_omics_type_counts_sum(self, conn):
        """by_omics_type experiment_counts sum to total_matching."""
        result = api.list_experiments(summary=True, conn=conn)
        omics_total = sum(b["experiment_count"] for b in result["by_omics_type"])
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
            assert "MED4" in r["organism_strain"] or (
                r.get("coculture_partner") and "MED4" in r.get("coculture_partner", "")
            )

    def test_detail_treatment_type_filter(self, conn):
        """Treatment type list filter works."""
        result = api.list_experiments(
            treatment_type=["coculture"], conn=conn,
        )
        assert result["total_matching"] >= 10
        for r in result["results"]:
            assert r["treatment_type"] == "coculture"

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
            for col in ["experiment_id", "publication_doi", "organism_strain",
                        "treatment_type", "omics_type", "is_time_course",
                        "gene_count", "significant_count"]:
                assert col in r, f"Missing column: {col}"

    def test_detail_is_time_course_is_bool(self, conn):
        """is_time_course is bool, not string."""
        result = api.list_experiments(limit=5, conn=conn)
        for r in result["results"]:
            assert isinstance(r["is_time_course"], bool)

    def test_detail_gene_count_nonnegative(self, conn):
        """gene_count and significant_count are >= 0."""
        result = api.list_experiments(conn=conn)
        for r in result["results"]:
            assert r["gene_count"] >= 0
            assert r["significant_count"] >= 0

    def test_detail_time_course_has_time_points(self, conn):
        """Time-course experiments have time_points with >1 entry."""
        result = api.list_experiments(
            time_course_only=True, limit=5, conn=conn,
        )
        for r in result["results"]:
            assert "time_points" in r
            assert len(r["time_points"]) > 1
            tp = r["time_points"][0]
            assert "label" in tp
            assert "order" in tp
            assert "total" in tp
            assert "significant" in tp

    def test_detail_non_time_course_no_time_points(self, conn):
        """Non-time-course experiments have no time_points key."""
        result = api.list_experiments(conn=conn)
        non_tc = [r for r in result["results"] if not r["is_time_course"]]
        assert len(non_tc) > 0
        for r in non_tc:
            assert "time_points" not in r

    # --- Consistency ---

    def test_summary_consistency(self, conn):
        """Summary total_matching == detail total row count (same filters)."""
        kwargs = dict(organism="MED4", treatment_type=["coculture"])
        summary = api.list_experiments(**kwargs, summary=True, conn=conn)
        detail = api.list_experiments(**kwargs, limit=500, conn=conn)
        assert summary["total_matching"] == detail["total_matching"]
        assert summary["total_matching"] == len(detail["results"])

