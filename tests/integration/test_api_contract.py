"""Integration tests for api/ layer return contracts against live Neo4j.

Validates that each api function returns the documented type and keys.
Marked with @pytest.mark.kg — auto-skips if Neo4j is unavailable.
"""

import pytest

from multiomics_explorer.api import functions as api
from tests.fixtures.gene_data import GENES


# Use a well-annotated gene for most tests.
KNOWN_GENE = "PMM0001"
KNOWN_ORGANISM = "MED4"


# ---------------------------------------------------------------------------
# kg_schema
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestKgSchemaContract:
    def test_returns_dict_with_nodes_and_relationships(self, conn):
        result = api.kg_schema(conn=conn)
        assert isinstance(result, dict)
        assert "nodes" in result
        assert "relationships" in result

    def test_gene_node_present(self, conn):
        result = api.kg_schema(conn=conn)
        assert "Gene" in result["nodes"]
        assert "properties" in result["nodes"]["Gene"]


# ---------------------------------------------------------------------------
# resolve_gene
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestResolveGeneContract:
    def test_returns_dict_envelope(self, conn):
        result = api.resolve_gene(KNOWN_GENE, conn=conn)
        assert isinstance(result, dict)
        assert "total_matching" in result
        assert "results" in result
        assert result["total_matching"] >= 1

    def test_result_keys(self, conn):
        result = api.resolve_gene(KNOWN_GENE, conn=conn)
        expected_keys = {"locus_tag", "gene_name", "product", "organism_strain"}
        assert set(result["results"][0].keys()) == expected_keys

    def test_not_found_returns_empty(self, conn):
        result = api.resolve_gene("NONEXISTENT_GENE_XYZ", conn=conn)
        assert result == {"total_matching": 0, "by_organism": [], "returned": 0, "truncated": False, "results": []}


# ---------------------------------------------------------------------------
# genes_by_function
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGenesByFunctionContract:
    def test_returns_dict(self, conn):
        result = api.genes_by_function("DNA polymerase", conn=conn)
        assert isinstance(result, dict)
        assert result["total_matching"] >= 1
        assert len(result["results"]) >= 1

    def test_envelope_keys(self, conn):
        result = api.genes_by_function("DNA polymerase", conn=conn)
        expected_envelope = {
            "total_entries", "total_matching", "by_organism", "by_category",
            "score_max", "score_median", "returned", "truncated", "results",
        }
        assert set(result.keys()) == expected_envelope

    def test_result_keys(self, conn):
        result = api.genes_by_function("DNA polymerase", conn=conn)
        expected_keys = {
            "locus_tag", "gene_name", "product", "organism_strain",
            "gene_category", "annotation_quality", "score",
        }
        assert set(result["results"][0].keys()) == expected_keys


# ---------------------------------------------------------------------------
# gene_overview
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneOverviewContract:
    def test_returns_dict_envelope(self, conn):
        result = api.gene_overview([KNOWN_GENE], conn=conn)
        assert isinstance(result, dict)
        assert "total_matching" in result
        assert "by_organism" in result
        assert "by_category" in result
        assert "by_annotation_type" in result
        assert "has_expression" in result
        assert "has_significant_expression" in result
        assert "has_orthologs" in result
        assert "returned" in result
        assert "truncated" in result
        assert "not_found" in result
        assert "results" in result
        assert result["total_matching"] >= 1
        assert len(result["results"]) >= 1

    def test_result_keys(self, conn):
        result = api.gene_overview([KNOWN_GENE], conn=conn)
        expected_keys = {
            "locus_tag", "gene_name", "product",
            "gene_category", "annotation_quality", "organism_strain",
            "annotation_types", "expression_edge_count",
            "significant_up_count", "significant_down_count", "closest_ortholog_group_size",
            "closest_ortholog_genera",
        }
        assert set(result["results"][0].keys()) == expected_keys


# ---------------------------------------------------------------------------
# get_gene_details
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGetGeneDetailsContract:
    def test_returns_dict(self, conn):
        result = api.get_gene_details(KNOWN_GENE, conn=conn)
        assert isinstance(result, dict)
        assert "locus_tag" in result

    def test_not_found_returns_none(self, conn):
        result = api.get_gene_details("NONEXISTENT_GENE_XYZ", conn=conn)
        assert result is None


# ---------------------------------------------------------------------------
# gene_homologs
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneHomologsContract:
    def test_returns_dict_with_envelope(self, conn):
        result = api.gene_homologs([KNOWN_GENE], conn=conn)
        assert isinstance(result, dict)
        for key in ("total_matching", "by_organism", "by_source",
                     "returned", "truncated", "not_found", "no_groups", "results"):
            assert key in result

    def test_result_keys_compact(self, conn):
        result = api.gene_homologs([KNOWN_GENE], conn=conn)
        assert len(result["results"]) >= 1
        expected_keys = {
            "locus_tag", "organism_strain", "group_id",
            "consensus_gene_name", "consensus_product",
            "taxonomic_level", "source",
        }
        assert set(result["results"][0].keys()) == expected_keys

    def test_not_found(self, conn):
        result = api.gene_homologs(["NONEXISTENT_GENE_XYZ"], conn=conn)
        assert "NONEXISTENT_GENE_XYZ" in result["not_found"]
        assert result["total_matching"] == 0


# ---------------------------------------------------------------------------
# list_filter_values
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestListFilterValuesContract:
    def test_returns_dict_with_keys(self, conn):
        result = api.list_filter_values(conn=conn)
        assert isinstance(result, dict)
        for key in ("filter_type", "total_entries", "returned", "truncated", "results"):
            assert key in result

    def test_filter_type_in_result(self, conn):
        result = api.list_filter_values(conn=conn)
        assert result["filter_type"] == "gene_category"

    def test_results_have_value_count_keys(self, conn):
        result = api.list_filter_values(conn=conn)
        if result["results"]:
            assert "value" in result["results"][0]
            assert "count" in result["results"][0]


# ---------------------------------------------------------------------------
# list_organisms
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestListOrganismsContract:
    def test_returns_dict_with_results(self, conn):
        result = api.list_organisms(conn=conn)
        assert isinstance(result, dict)
        assert "total_entries" in result
        assert "results" in result
        assert len(result["results"]) >= 1

    def test_result_keys(self, conn):
        result = api.list_organisms(conn=conn)
        expected_keys = {
            "organism_name", "genus", "species", "strain", "clade",
            "ncbi_taxon_id", "gene_count", "publication_count",
            "experiment_count", "treatment_types", "omics_types",
        }
        assert set(result["results"][0].keys()) == expected_keys


# ---------------------------------------------------------------------------
# search_ontology
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestSearchOntologyContract:
    def test_returns_dict_envelope(self, conn):
        result = api.search_ontology("DNA replication", "go_bp", conn=conn)
        assert isinstance(result, dict)
        assert "total_entries" in result
        assert "total_matching" in result
        assert "score_max" in result
        assert "score_median" in result
        assert "returned" in result
        assert "truncated" in result
        assert "results" in result
        assert result["total_matching"] >= 1

    def test_result_keys(self, conn):
        result = api.search_ontology("DNA replication", "go_bp", conn=conn)
        expected_keys = {"id", "name", "score"}
        assert len(result["results"]) >= 1
        assert set(result["results"][0].keys()) == expected_keys


# ---------------------------------------------------------------------------
# genes_by_ontology
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGenesByOntologyContract:
    def test_returns_dict_envelope(self, conn):
        result = api.genes_by_ontology(["go:0006260"], "go_bp", conn=conn)
        assert isinstance(result, dict)
        for key in ("total_matching", "by_organism", "by_category",
                     "by_term", "returned", "truncated", "results"):
            assert key in result
        assert result["total_matching"] >= 1
        assert result["returned"] >= 1

    def test_result_keys(self, conn):
        result = api.genes_by_ontology(["go:0006260"], "go_bp", conn=conn)
        expected_keys = {"locus_tag", "gene_name", "product",
                         "organism_strain", "gene_category"}
        assert set(result["results"][0].keys()) == expected_keys

    def test_summary_mode(self, conn):
        result = api.genes_by_ontology(
            ["go:0006260"], "go_bp", summary=True, conn=conn,
        )
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["total_matching"] >= 1

    def test_verbose_adds_columns(self, conn):
        result = api.genes_by_ontology(
            ["go:0006260"], "go_bp", verbose=True, limit=1, conn=conn,
        )
        row = result["results"][0]
        assert "matched_terms" in row
        assert "gene_summary" in row
        assert "function_description" in row


# ---------------------------------------------------------------------------
# gene_ontology_terms
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneOntologyTermsContract:
    def test_returns_dict_envelope(self, conn):
        result = api.gene_ontology_terms(
            locus_tags=[KNOWN_GENE], ontology="go_bp", conn=conn,
        )
        assert isinstance(result, dict)
        expected_keys = {
            "total_matching", "total_genes", "total_terms",
            "by_ontology", "by_term",
            "terms_per_gene_min", "terms_per_gene_max",
            "terms_per_gene_median",
            "returned", "truncated", "not_found", "no_terms",
            "results",
        }
        assert expected_keys <= set(result.keys())
        assert result["total_matching"] >= 1

    def test_results_have_expected_columns(self, conn):
        result = api.gene_ontology_terms(
            locus_tags=[KNOWN_GENE], ontology="go_bp", conn=conn,
        )
        assert len(result["results"]) >= 1
        row = result["results"][0]
        for col in ("locus_tag", "term_id", "term_name"):
            assert col in row

    def test_not_found(self, conn):
        result = api.gene_ontology_terms(
            locus_tags=[KNOWN_GENE, "FAKE_GENE_999"], ontology="go_bp",
            conn=conn,
        )
        assert "FAKE_GENE_999" in result["not_found"]

    def test_all_ontology(self, conn):
        result = api.gene_ontology_terms(
            locus_tags=[KNOWN_GENE], ontology=None, conn=conn,
        )
        assert isinstance(result, dict)
        assert result["total_matching"] >= 1
        row = result["results"][0]
        assert "ontology_type" in row

    def test_single_ontology_filter(self, conn):
        result = api.gene_ontology_terms(
            locus_tags=[KNOWN_GENE], ontology="go_bp", conn=conn,
        )
        assert isinstance(result, dict)
        assert result["total_matching"] >= 1


# ---------------------------------------------------------------------------
# run_cypher
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestRunCypherContract:
    def test_returns_envelope(self, conn):
        result = api.run_cypher(
            "MATCH (g:Gene) RETURN count(g) AS count", conn=conn,
        )
        assert isinstance(result, dict)
        assert set(result.keys()) >= {"returned", "truncated", "warnings", "results"}
        assert result["returned"] == 1
        assert "count" in result["results"][0]

    def test_write_blocked(self, conn):
        with pytest.raises(ValueError, match="Write operations"):
            api.run_cypher("CREATE (n:Test)", conn=conn)


# ---------------------------------------------------------------------------
# differential_expression_by_gene
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestDifferentialExpressionByGeneContract:
    def test_returns_dict_envelope(self, conn):
        result = api.differential_expression_by_gene(
            organism=KNOWN_ORGANISM, summary=True, conn=conn,
        )
        assert isinstance(result, dict)
        expected_keys = {
            "organism_strain", "matching_genes", "total_rows",
            "rows_by_status", "median_abs_log2fc", "max_abs_log2fc",
            "experiment_count", "rows_by_treatment_type", "top_categories",
            "experiments", "not_found", "no_expression",
            "returned", "truncated", "results",
        }
        assert set(result.keys()) == expected_keys

    def test_rows_by_status_keys(self, conn):
        result = api.differential_expression_by_gene(
            organism=KNOWN_ORGANISM, summary=True, conn=conn,
        )
        rbs = result["rows_by_status"]
        assert set(rbs.keys()) == {"significant_up", "significant_down", "not_significant"}
        assert sum(rbs.values()) == result["total_rows"]

    def test_result_row_keys(self, conn):
        result = api.differential_expression_by_gene(
            locus_tags=[KNOWN_GENE], limit=1, conn=conn,
        )
        assert result["returned"] >= 1
        row = result["results"][0]
        expected_compact = {
            "locus_tag", "gene_name", "experiment_id", "treatment_type",
            "timepoint", "timepoint_hours", "timepoint_order",
            "log2fc", "padj", "rank", "expression_status",
        }
        assert expected_compact <= set(row.keys())

    def test_verbose_adds_columns(self, conn):
        result = api.differential_expression_by_gene(
            locus_tags=[KNOWN_GENE], verbose=True, limit=1, conn=conn,
        )
        row = result["results"][0]
        for col in ("product", "experiment_name", "treatment",
                     "gene_category", "omics_type"):
            assert col in row

    def test_experiment_summary_shape(self, conn):
        result = api.differential_expression_by_gene(
            organism=KNOWN_ORGANISM, summary=True, conn=conn,
        )
        assert result["experiment_count"] == len(result["experiments"])
        if result["experiments"]:
            exp = result["experiments"][0]
            assert "experiment_id" in exp
            assert "rows_by_status" in exp
            assert "matching_genes" in exp
