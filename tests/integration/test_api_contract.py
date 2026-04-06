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
        expected_keys = {"locus_tag", "gene_name", "product", "organism_name"}
        assert set(result["results"][0].keys()) == expected_keys

    def test_not_found_returns_empty(self, conn):
        result = api.resolve_gene("NONEXISTENT_GENE_XYZ", conn=conn)
        assert result == {"total_matching": 0, "by_organism": [], "returned": 0, "truncated": False, "offset": 0, "results": []}


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
            "total_search_hits", "total_matching", "by_organism", "by_category",
            "score_max", "score_median", "returned", "truncated", "offset", "results",
        }
        assert set(result.keys()) == expected_envelope

    def test_result_keys(self, conn):
        result = api.genes_by_function("DNA polymerase", conn=conn)
        expected_keys = {
            "locus_tag", "gene_name", "product", "organism_name",
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
        assert "offset" in result
        assert "not_found" in result
        assert "results" in result
        assert result["total_matching"] >= 1
        assert len(result["results"]) >= 1

    def test_result_keys(self, conn):
        result = api.gene_overview([KNOWN_GENE], conn=conn)
        expected_keys = {
            "locus_tag", "gene_name", "product",
            "gene_category", "annotation_quality", "organism_name",
            "annotation_types", "expression_edge_count",
            "significant_up_count", "significant_down_count", "closest_ortholog_group_size",
            "closest_ortholog_genera",
        }
        assert set(result["results"][0].keys()) == expected_keys


# ---------------------------------------------------------------------------
# gene_details
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneDetailsContract:
    def test_returns_envelope(self, conn):
        result = api.gene_details([KNOWN_GENE], conn=conn)
        assert isinstance(result, dict)
        assert "total_matching" in result
        assert "results" in result
        assert result["results"][0]["locus_tag"] == KNOWN_GENE

    def test_not_found_in_envelope(self, conn):
        result = api.gene_details(["NONEXISTENT_GENE_XYZ"], conn=conn)
        assert result["total_matching"] == 0
        assert "NONEXISTENT_GENE_XYZ" in result["not_found"]


# ---------------------------------------------------------------------------
# gene_homologs
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneHomologsContract:
    def test_returns_dict_with_envelope(self, conn):
        result = api.gene_homologs([KNOWN_GENE], conn=conn)
        assert isinstance(result, dict)
        for key in ("total_matching", "by_organism", "by_source",
                     "returned", "truncated", "offset", "not_found", "no_groups",
                     "top_cyanorak_roles", "top_cog_categories", "results"):
            assert key in result

    def test_result_keys_compact(self, conn):
        result = api.gene_homologs([KNOWN_GENE], conn=conn)
        assert len(result["results"]) >= 1
        expected_keys = {
            "locus_tag", "organism_name", "group_id",
            "consensus_gene_name", "consensus_product",
            "taxonomic_level", "source", "specificity_rank",
        }
        assert set(result["results"][0].keys()) == expected_keys

    def test_not_found(self, conn):
        result = api.gene_homologs(["NONEXISTENT_GENE_XYZ"], conn=conn)
        assert "NONEXISTENT_GENE_XYZ" in result["not_found"]
        assert result["total_matching"] == 0

    def test_summary_has_ontology_keys(self, conn):
        result = api.gene_homologs([KNOWN_GENE], summary=True, conn=conn)
        assert "top_cyanorak_roles" in result
        assert "top_cog_categories" in result
        for item in result["top_cyanorak_roles"]:
            assert "id" in item
            assert "name" in item
            assert "count" in item

    def test_verbose_has_ontology_columns(self, conn):
        result = api.gene_homologs([KNOWN_GENE], verbose=True, limit=1, conn=conn)
        row = result["results"][0]
        assert "cyanorak_roles" in row
        assert "cog_categories" in row
        assert isinstance(row["cyanorak_roles"], list)
        assert isinstance(row["cog_categories"], list)


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
            "background_factors", "clustering_analysis_count", "cluster_types",
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
        assert "offset" in result
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
                     "by_term", "returned", "truncated", "offset", "results"):
            assert key in result
        assert result["total_matching"] >= 1
        assert result["returned"] >= 1

    def test_result_keys(self, conn):
        result = api.genes_by_ontology(["go:0006260"], "go_bp", conn=conn)
        expected_keys = {"locus_tag", "gene_name", "product",
                         "organism_name", "gene_category"}
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
            "returned", "truncated", "offset", "not_found", "no_terms",
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
            "organism_name", "matching_genes", "total_matching",
            "rows_by_status", "median_abs_log2fc", "max_abs_log2fc",
            "experiment_count", "rows_by_treatment_type",
            "rows_by_background_factors", "by_table_scope",
            "top_categories", "experiments", "not_found", "no_expression",
            "returned", "truncated", "offset", "results",
        }
        assert set(result.keys()) == expected_keys

    def test_rows_by_status_keys(self, conn):
        result = api.differential_expression_by_gene(
            organism=KNOWN_ORGANISM, summary=True, conn=conn,
        )
        rbs = result["rows_by_status"]
        assert set(rbs.keys()) == {"significant_up", "significant_down", "not_significant"}
        assert sum(rbs.values()) == result["total_matching"]

    def test_result_row_keys(self, conn):
        result = api.differential_expression_by_gene(
            locus_tags=[KNOWN_GENE], limit=1, conn=conn,
        )
        assert result["returned"] >= 1
        row = result["results"][0]
        expected_compact = {
            "locus_tag", "gene_name", "experiment_id", "treatment_type",
            "timepoint", "timepoint_hours", "timepoint_order",
            "log2fc", "padj", "rank", "rank_up", "rank_down",
            "expression_status",
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


# ---------------------------------------------------------------------------
# differential_expression_by_ortholog
# ---------------------------------------------------------------------------
KNOWN_GROUP = "cyanorak:CK_00000570"


@pytest.mark.kg
class TestDifferentialExpressionByOrthologContract:
    def test_returns_dict_envelope(self, conn):
        result = api.differential_expression_by_ortholog(
            group_ids=[KNOWN_GROUP], limit=5, conn=conn,
        )
        assert isinstance(result, dict)
        expected_keys = {
            "total_matching", "matching_genes", "matching_groups",
            "experiment_count", "median_abs_log2fc", "max_abs_log2fc",
            "results", "returned", "truncated", "offset",
            "by_organism", "rows_by_status", "rows_by_treatment_type",
            "rows_by_background_factors",
            "by_table_scope", "top_groups", "top_experiments",
            "not_found_groups", "not_matched_groups",
            "not_found_organisms", "not_matched_organisms",
            "not_found_experiments", "not_matched_experiments",
        }
        assert set(result.keys()) == expected_keys

    def test_rows_by_status_keys(self, conn):
        result = api.differential_expression_by_ortholog(
            group_ids=[KNOWN_GROUP], limit=5, conn=conn,
        )
        rbs = result["rows_by_status"]
        assert set(rbs.keys()) == {"significant_up", "significant_down", "not_significant"}
        assert sum(rbs.values()) == result["total_matching"]

    def test_result_row_keys_compact(self, conn):
        result = api.differential_expression_by_ortholog(
            group_ids=[KNOWN_GROUP], limit=1, conn=conn,
        )
        assert result["returned"] >= 1
        row = result["results"][0]
        expected_compact = {
            "group_id", "consensus_gene_name", "consensus_product",
            "experiment_id", "treatment_type", "organism_name",
            "coculture_partner", "timepoint", "timepoint_hours",
            "timepoint_order", "genes_with_expression", "total_genes",
            "significant_up", "significant_down", "not_significant",
        }
        assert expected_compact <= set(row.keys())

    def test_verbose_adds_columns(self, conn):
        result = api.differential_expression_by_ortholog(
            group_ids=[KNOWN_GROUP], verbose=True, limit=1, conn=conn,
        )
        row = result["results"][0]
        for col in ("experiment_name", "treatment", "omics_type",
                     "table_scope", "table_scope_detail"):
            assert col in row

    def test_top_groups_shape(self, conn):
        result = api.differential_expression_by_ortholog(
            group_ids=[KNOWN_GROUP], limit=1, conn=conn,
        )
        assert isinstance(result["top_groups"], list)
        if result["top_groups"]:
            tg = result["top_groups"][0]
            assert set(tg.keys()) == {
                "group_id", "consensus_gene_name", "consensus_product",
                "significant_genes", "total_genes",
            }

    def test_top_experiments_shape(self, conn):
        result = api.differential_expression_by_ortholog(
            group_ids=[KNOWN_GROUP], limit=1, conn=conn,
        )
        assert isinstance(result["top_experiments"], list)
        if result["top_experiments"]:
            te = result["top_experiments"][0]
            assert set(te.keys()) == {
                "experiment_id", "treatment_type", "organism_name",
                "significant_genes", "background_factors",
            }

    def test_by_organism_shape(self, conn):
        result = api.differential_expression_by_ortholog(
            group_ids=[KNOWN_GROUP], limit=1, conn=conn,
        )
        assert isinstance(result["by_organism"], list)
        if result["by_organism"]:
            bo = result["by_organism"][0]
            assert "organism_name" in bo
            assert "count" in bo

    def test_diagnostic_fields_present(self, conn):
        result = api.differential_expression_by_ortholog(
            group_ids=[KNOWN_GROUP], conn=conn,
        )
        for field in ("not_found_groups", "not_matched_groups",
                       "not_found_organisms", "not_matched_organisms",
                       "not_found_experiments", "not_matched_experiments"):
            assert isinstance(result[field], list)


# ---------------------------------------------------------------------------
# list_publications
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestListPublicationsContract:
    def test_returns_dict_envelope(self, conn):
        result = api.list_publications(conn=conn)
        assert isinstance(result, dict)
        expected_keys = {
            "total_entries", "total_matching", "by_organism",
            "by_treatment_type", "by_omics_type", "by_cluster_type",
            "returned", "truncated", "offset", "results",
        }
        assert expected_keys <= set(result.keys())
        assert result["total_matching"] >= 15

    def test_result_keys(self, conn):
        result = api.list_publications(conn=conn)
        row = result["results"][0]
        for key in ("doi", "title", "authors", "year",
                     "experiment_count", "organisms",
                     "treatment_types", "omics_types",
                     "clustering_analysis_count", "cluster_types"):
            assert key in row

    def test_verbose_adds_abstract(self, conn):
        result = api.list_publications(verbose=True, limit=1, conn=conn)
        row = result["results"][0]
        assert "abstract" in row
        assert "description" in row
        assert "cluster_count" in row

    def test_organism_filter_narrows(self, conn):
        all_pubs = api.list_publications(conn=conn)
        filtered = api.list_publications(organism="MED4", conn=conn)
        assert filtered["total_matching"] <= all_pubs["total_matching"]
        assert filtered["total_matching"] >= 5


# ---------------------------------------------------------------------------
# list_experiments
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestListExperimentsContract:
    def test_returns_dict_envelope(self, conn):
        result = api.list_experiments(conn=conn)
        assert isinstance(result, dict)
        expected_keys = {
            "total_entries", "total_matching",
            "by_organism", "by_treatment_type", "by_omics_type",
            "by_publication", "by_table_scope", "by_cluster_type",
            "time_course_count",
            "returned", "truncated", "offset", "results",
        }
        assert expected_keys <= set(result.keys())
        assert result["total_matching"] >= 70

    def test_result_keys(self, conn):
        result = api.list_experiments(limit=1, conn=conn)
        row = result["results"][0]
        for key in ("experiment_id", "experiment_name",
                     "publication_doi", "organism_name",
                     "treatment_type", "omics_type",
                     "is_time_course", "table_scope",
                     "gene_count", "genes_by_status",
                     "clustering_analysis_count", "cluster_types"):
            assert key in row

    def test_verbose_adds_fields(self, conn):
        result = api.list_experiments(verbose=True, limit=1, conn=conn)
        row = result["results"][0]
        for key in ("publication_title", "treatment", "control", "cluster_count"):
            assert key in row

    def test_summary_mode(self, conn):
        result = api.list_experiments(summary=True, conn=conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["total_matching"] >= 70
        assert len(result["by_organism"]) >= 8

    def test_table_scope_filter(self, conn):
        result = api.list_experiments(
            table_scope=["significant_only"], conn=conn,
        )
        for row in result["results"]:
            assert row["table_scope"] == "significant_only"


# ---------------------------------------------------------------------------
# search_homolog_groups
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestSearchHomologGroupsContract:
    def test_returns_dict_envelope(self, conn):
        result = api.search_homolog_groups("photosynthesis", conn=conn)
        assert isinstance(result, dict)
        expected_keys = {
            "total_entries", "total_matching", "by_source", "by_level",
            "score_max", "score_median",
            "top_cyanorak_roles", "top_cog_categories",
            "returned", "truncated", "offset", "results",
        }
        assert set(result.keys()) == expected_keys
        assert result["total_matching"] >= 5

    def test_result_keys_compact(self, conn):
        result = api.search_homolog_groups("photosynthesis", conn=conn)
        expected_keys = {
            "group_id", "group_name", "consensus_gene_name",
            "consensus_product", "source", "taxonomic_level",
            "specificity_rank", "member_count", "organism_count", "score",
        }
        assert set(result["results"][0].keys()) == expected_keys

    def test_result_keys_verbose(self, conn):
        result = api.search_homolog_groups(
            "nitrogen", verbose=True, limit=1, conn=conn,
        )
        row = result["results"][0]
        for key in ("description", "functional_description",
                     "genera", "has_cross_genus_members"):
            assert key in row

    def test_by_source_shape(self, conn):
        result = api.search_homolog_groups("kinase", conn=conn)
        for b in result["by_source"]:
            assert "source" in b
            assert "count" in b

    def test_by_level_shape(self, conn):
        result = api.search_homolog_groups("kinase", conn=conn)
        for b in result["by_level"]:
            assert "taxonomic_level" in b
            assert "count" in b

    def test_summary_has_ontology_keys(self, conn):
        result = api.search_homolog_groups("photosynthesis", summary=True, conn=conn)
        assert "top_cyanorak_roles" in result
        assert "top_cog_categories" in result

    def test_verbose_has_ontology_columns(self, conn):
        result = api.search_homolog_groups(
            "photosynthesis", verbose=True, limit=1, conn=conn)
        row = result["results"][0]
        assert "cyanorak_roles" in row
        assert "cog_categories" in row
        assert isinstance(row["cyanorak_roles"], list)

    def test_ontology_filter(self, conn):
        result = api.search_homolog_groups(
            "photosystem", cyanorak_roles=["cyanorak.role:J.8"],
            summary=True, conn=conn)
        assert result["total_matching"] >= 1


# ---------------------------------------------------------------------------
# genes_by_homolog_group
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGenesByHomologGroupContract:
    KNOWN_GROUP = "cyanorak:CK_00000570"

    def test_returns_dict_envelope(self, conn):
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], conn=conn,
        )
        assert isinstance(result, dict)
        expected_keys = {
            "total_matching", "total_genes", "total_categories",
            "genes_per_group_max", "genes_per_group_median",
            "by_organism", "top_categories", "top_groups",
            "not_found_groups", "not_matched_groups",
            "not_found_organisms", "not_matched_organisms",
            "returned", "truncated", "offset", "results",
        }
        assert set(result.keys()) == expected_keys

    def test_result_keys_compact(self, conn):
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], conn=conn,
        )
        expected_keys = {
            "locus_tag", "gene_name", "product",
            "organism_name", "gene_category", "group_id",
        }
        assert set(result["results"][0].keys()) == expected_keys

    def test_result_keys_verbose(self, conn):
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], verbose=True, limit=1, conn=conn,
        )
        row = result["results"][0]
        for key in ("gene_summary", "function_description",
                     "consensus_product", "source"):
            assert key in row

    def test_not_found(self, conn):
        result = api.genes_by_homolog_group(
            group_ids=["FAKE_GROUP_XYZ"], conn=conn,
        )
        assert "FAKE_GROUP_XYZ" in result["not_found_groups"]
        assert result["total_matching"] == 0

    def test_by_organism_shape(self, conn):
        result = api.genes_by_homolog_group(
            group_ids=[self.KNOWN_GROUP], conn=conn,
        )
        assert len(result["by_organism"]) >= 1
        for b in result["by_organism"]:
            assert "organism_name" in b
            assert "count" in b


# ---------------------------------------------------------------------------
# gene_response_profile
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneResponseProfileContract:
    def test_returns_dict_envelope(self, conn):
        result = api.gene_response_profile(
            locus_tags=[KNOWN_GENE], conn=conn,
        )
        assert isinstance(result, dict)
        expected_keys = {
            "organism_name", "genes_queried", "genes_with_response",
            "not_found", "no_expression",
            "returned", "offset", "truncated", "results",
        }
        assert set(result.keys()) == expected_keys

    def test_result_structure(self, conn):
        result = api.gene_response_profile(
            locus_tags=[KNOWN_GENE], conn=conn,
        )
        assert result["returned"] >= 1
        gene = result["results"][0]
        for key in ("locus_tag", "gene_name", "product", "gene_category",
                     "groups_responded", "groups_not_responded",
                     "groups_not_known", "response_summary"):
            assert key in gene

    def test_response_summary_fields(self, conn):
        result = api.gene_response_profile(
            locus_tags=[KNOWN_GENE], conn=conn,
        )
        gene = result["results"][0]
        if gene["response_summary"]:
            entry = next(iter(gene["response_summary"].values()))
            for key in ("experiments_total", "experiments_tested",
                         "experiments_up", "experiments_down",
                         "timepoints_total", "timepoints_tested",
                         "timepoints_up", "timepoints_down"):
                assert key in entry


# ---------------------------------------------------------------------------
# list_clustering_analyses
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestListClusteringAnalysesContract:
    def test_returns_dict_envelope(self, conn):
        result = api.list_clustering_analyses(conn=conn)
        expected_keys = {
            "total_entries", "total_matching",
            "by_organism", "by_cluster_type", "by_treatment_type",
            "by_background_factors", "by_omics_type",
            "score_max", "score_median",
            "returned", "offset", "truncated", "results",
        }
        assert expected_keys <= set(result.keys())
        assert result["total_entries"] >= 2

    def test_search_text(self, conn):
        result = api.list_clustering_analyses(
            search_text="starvation", conn=conn)
        assert result["total_matching"] >= 1
        assert result["score_max"] is not None

    def test_organism_filter(self, conn):
        result = api.list_clustering_analyses(
            organism="MED4", conn=conn)
        assert result["total_matching"] >= 1

    def test_result_keys_compact(self, conn):
        result = api.list_clustering_analyses(limit=1, conn=conn)
        if result["results"]:
            expected = {
                "analysis_id", "name", "organism_name",
                "cluster_method", "cluster_type", "cluster_count",
                "total_gene_count", "treatment_type",
                "background_factors", "omics_type",
                "experiment_ids", "clusters",
            }
            assert expected <= set(result["results"][0].keys())

    def test_result_keys_verbose(self, conn):
        result = api.list_clustering_analyses(
            verbose=True, limit=1, conn=conn)
        if result["results"]:
            for key in ("treatment", "light_condition",
                        "experimental_context"):
                assert key in result["results"][0]

    def test_inline_clusters_present(self, conn):
        result = api.list_clustering_analyses(limit=1, conn=conn)
        if result["results"]:
            clusters = result["results"][0]["clusters"]
            assert isinstance(clusters, list)
            if clusters:
                expected_cluster_keys = {"cluster_id", "name", "member_count"}
                assert expected_cluster_keys <= set(clusters[0].keys())

    def test_summary_mode(self, conn):
        result = api.list_clustering_analyses(summary=True, conn=conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["total_matching"] >= 2


# ---------------------------------------------------------------------------
# gene_clusters_by_gene
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneClustersByGeneContract:
    def test_returns_dict_envelope(self, conn):
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], conn=conn)
        expected_keys = {
            "total_matching", "total_clusters",
            "genes_with_clusters", "genes_without_clusters",
            "not_found", "not_matched",
            "by_cluster_type", "by_treatment_type",
            "by_background_factors", "by_analysis",
            "returned", "offset", "truncated", "results",
        }
        assert expected_keys <= set(result.keys())

    def test_known_gene_has_cluster(self, conn):
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], conn=conn)
        assert result["genes_with_clusters"] >= 1
        assert result["total_clusters"] >= 1

    def test_result_keys_compact(self, conn):
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], conn=conn)
        if result["results"]:
            expected = {
                "locus_tag", "gene_name", "cluster_id", "cluster_name",
                "cluster_type", "membership_score",
                "analysis_id", "analysis_name",
                "treatment_type", "background_factors",
            }
            assert expected <= set(result["results"][0].keys())

    def test_result_keys_verbose(self, conn):
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=True, conn=conn)
        if result["results"]:
            for key in ("cluster_functional_description",
                        "cluster_expression_dynamics",
                        "cluster_temporal_pattern",
                        "cluster_method", "member_count"):
                assert key in result["results"][0]

    def test_by_analysis_in_envelope(self, conn):
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], conn=conn)
        assert "by_analysis" in result
        assert isinstance(result["by_analysis"], list)

    def test_unknown_gene_in_not_found(self, conn):
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370", "FAKE_GENE_XYZ"],
            conn=conn)
        assert "FAKE_GENE_XYZ" in result["not_found"]


# ---------------------------------------------------------------------------
# genes_in_cluster
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGenesInClusterContract:
    def test_returns_dict_envelope(self, conn):
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:8"],
            conn=conn)
        expected_keys = {
            "total_matching", "by_organism", "by_cluster",
            "top_categories", "genes_per_cluster_max",
            "genes_per_cluster_median",
            "not_found_clusters", "not_matched_clusters",
            "returned", "offset", "truncated", "results",
        }
        assert expected_keys <= set(result.keys())

    def test_known_cluster_has_members(self, conn):
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:8"],
            conn=conn)
        assert result["total_matching"] == 37

    def test_result_keys_compact(self, conn):
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:8"],
            limit=1, conn=conn)
        expected = {"locus_tag", "gene_name", "product", "gene_category",
                    "organism_name", "cluster_id", "cluster_name",
                    "membership_score"}
        assert expected <= set(result["results"][0].keys())

    def test_analysis_id_mode(self, conn):
        result = api.genes_in_cluster(
            analysis_id="clustering_analysis:msb4100087:med4_kmeans_nstarvation",
            conn=conn)
        assert result["total_matching"] >= 1
        assert "analysis_name" in result

    def test_verbose_keys(self, conn):
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:8"],
            verbose=True, limit=1, conn=conn)
        if result["results"]:
            for key in ("gene_function_description",
                        "cluster_functional_description",
                        "cluster_expression_dynamics",
                        "cluster_temporal_pattern"):
                assert key in result["results"][0]

    def test_unknown_cluster_in_not_found(self, conn):
        result = api.genes_in_cluster(
            cluster_ids=["cluster:fake:id"], conn=conn)
        assert "cluster:fake:id" in result["not_found_clusters"]
