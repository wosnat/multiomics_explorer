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
# get_schema
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGetSchemaContract:
    def test_returns_dict_with_nodes_and_relationships(self, conn):
        result = api.get_schema(conn=conn)
        assert isinstance(result, dict)
        assert "nodes" in result
        assert "relationships" in result

    def test_gene_node_present(self, conn):
        result = api.get_schema(conn=conn)
        assert "Gene" in result["nodes"]
        assert "properties" in result["nodes"]["Gene"]


# ---------------------------------------------------------------------------
# resolve_gene
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestResolveGeneContract:
    def test_returns_list_of_dicts(self, conn):
        result = api.resolve_gene(KNOWN_GENE, conn=conn)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_result_keys(self, conn):
        result = api.resolve_gene(KNOWN_GENE, conn=conn)
        expected_keys = {"locus_tag", "gene_name", "product", "organism_strain"}
        assert set(result[0].keys()) == expected_keys

    def test_not_found_returns_empty(self, conn):
        result = api.resolve_gene("NONEXISTENT_GENE_XYZ", conn=conn)
        assert result == []


# ---------------------------------------------------------------------------
# search_genes
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestSearchGenesContract:
    def test_returns_list_of_dicts(self, conn):
        result = api.search_genes("DNA polymerase", conn=conn)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_result_keys(self, conn):
        result = api.search_genes("DNA polymerase", conn=conn)
        expected_keys = {
            "locus_tag", "gene_name", "product", "function_description",
            "gene_summary", "organism_strain", "annotation_quality", "score",
        }
        assert set(result[0].keys()) == expected_keys

    def test_dedup_adds_keys(self, conn):
        result = api.search_genes(
            "DNA polymerase", deduplicate=True, conn=conn,
        )
        # At least one result should have collapsed_count
        has_collapsed = any("collapsed_count" in r for r in result)
        assert has_collapsed


# ---------------------------------------------------------------------------
# gene_overview
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneOverviewContract:
    def test_returns_list_of_dicts(self, conn):
        result = api.gene_overview([KNOWN_GENE], conn=conn)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_result_keys(self, conn):
        result = api.gene_overview([KNOWN_GENE], conn=conn)
        expected_keys = {
            "locus_tag", "gene_name", "product", "gene_summary",
            "gene_category", "annotation_quality", "organism_strain",
            "annotation_types", "expression_edge_count",
            "significant_expression_count", "closest_ortholog_group_size",
            "closest_ortholog_genera",
        }
        assert set(result[0].keys()) == expected_keys


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
# query_expression
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestQueryExpressionContract:
    def test_returns_list_of_dicts(self, conn):
        result = api.query_expression(gene_id=KNOWN_GENE, conn=conn)
        assert isinstance(result, list)

    def test_result_keys_when_data_exists(self, conn):
        result = api.query_expression(gene_id=KNOWN_GENE, conn=conn)
        if result:
            expected_keys = {
                "gene", "product", "edge_type", "source", "direction",
                "log2fc", "padj", "organism_strain", "control", "context",
                "time_point", "publications",
            }
            assert set(result[0].keys()) == expected_keys

    def test_no_filter_raises(self, conn):
        with pytest.raises(ValueError, match="At least one"):
            api.query_expression(conn=conn)


# ---------------------------------------------------------------------------
# get_homologs
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGetHomologsContract:
    def test_returns_dict_with_keys(self, conn):
        result = api.get_homologs(KNOWN_GENE, conn=conn)
        assert isinstance(result, dict)
        assert "query_gene" in result
        assert "ortholog_groups" in result

    def test_query_gene_keys(self, conn):
        result = api.get_homologs(KNOWN_GENE, conn=conn)
        expected_keys = {"locus_tag", "gene_name", "product", "organism_strain"}
        assert set(result["query_gene"].keys()) == expected_keys

    def test_group_keys(self, conn):
        result = api.get_homologs(KNOWN_GENE, conn=conn)
        assert len(result["ortholog_groups"]) >= 1
        group = result["ortholog_groups"][0]
        expected_keys = {
            "og_name", "source", "taxonomic_level", "specificity_rank",
            "consensus_product", "consensus_gene_name",
            "member_count", "organism_count", "genera",
            "has_cross_genus_members",
        }
        assert set(group.keys()) == expected_keys

    def test_gene_not_found_raises(self, conn):
        with pytest.raises(ValueError, match="not found"):
            api.get_homologs("NONEXISTENT_GENE_XYZ", conn=conn)

    def test_include_members_adds_members_key(self, conn):
        result = api.get_homologs(
            KNOWN_GENE, include_members=True, conn=conn,
        )
        for group in result["ortholog_groups"]:
            assert "members" in group


# ---------------------------------------------------------------------------
# list_filter_values
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestListFilterValuesContract:
    def test_returns_dict_with_keys(self, conn):
        result = api.list_filter_values(conn=conn)
        assert isinstance(result, dict)
        assert "gene_categories" in result
        assert "condition_types" in result

    def test_gene_categories_keys(self, conn):
        result = api.list_filter_values(conn=conn)
        if result["gene_categories"]:
            assert "category" in result["gene_categories"][0]
            assert "gene_count" in result["gene_categories"][0]

    def test_condition_types_keys(self, conn):
        result = api.list_filter_values(conn=conn)
        if result["condition_types"]:
            assert "condition_type" in result["condition_types"][0]
            assert "count" in result["condition_types"][0]


# ---------------------------------------------------------------------------
# list_organisms
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestListOrganismsContract:
    def test_returns_list_of_dicts(self, conn):
        result = api.list_organisms(conn=conn)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_result_keys(self, conn):
        result = api.list_organisms(conn=conn)
        expected_keys = {"organism_name", "genus", "strain", "clade", "gene_count"}
        assert set(result[0].keys()) == expected_keys


# ---------------------------------------------------------------------------
# search_ontology
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestSearchOntologyContract:
    def test_returns_list_of_dicts(self, conn):
        result = api.search_ontology("DNA replication", "go_bp", conn=conn)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_result_keys(self, conn):
        result = api.search_ontology("DNA replication", "go_bp", conn=conn)
        expected_keys = {"id", "name", "score"}
        assert set(result[0].keys()) == expected_keys


# ---------------------------------------------------------------------------
# genes_by_ontology
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGenesByOntologyContract:
    def test_returns_list_of_dicts(self, conn):
        result = api.genes_by_ontology(["go:0006260"], "go_bp", conn=conn)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_result_keys(self, conn):
        result = api.genes_by_ontology(["go:0006260"], "go_bp", conn=conn)
        expected_keys = {"locus_tag", "gene_name", "product", "organism_strain"}
        assert set(result[0].keys()) == expected_keys


# ---------------------------------------------------------------------------
# gene_ontology_terms
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestGeneOntologyTermsContract:
    def test_returns_list_of_dicts(self, conn):
        result = api.gene_ontology_terms(KNOWN_GENE, "go_bp", conn=conn)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_result_keys(self, conn):
        result = api.gene_ontology_terms(KNOWN_GENE, "go_bp", conn=conn)
        expected_keys = {"id", "name"}
        assert set(result[0].keys()) == expected_keys


# ---------------------------------------------------------------------------
# run_cypher
# ---------------------------------------------------------------------------
@pytest.mark.kg
class TestRunCypherContract:
    def test_returns_list_of_dicts(self, conn):
        result = api.run_cypher(
            "MATCH (g:Gene) RETURN count(g) AS count", conn=conn,
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert "count" in result[0]

    def test_write_blocked(self, conn):
        with pytest.raises(ValueError, match="Write operations"):
            api.run_cypher("CREATE (n:Test)", conn=conn)
