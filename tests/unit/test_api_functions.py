"""Unit tests for the api/ layer — no Neo4j needed.

Tests business logic, validation, parameter passing, and return types
by mocking GraphConnection.execute_query.
"""

from unittest.mock import MagicMock, patch

import pytest

from multiomics_explorer.api import functions as api


# ---------------------------------------------------------------------------
# Top-level package re-exports
# ---------------------------------------------------------------------------
class TestTopLevelImports:
    def test_all_api_functions_importable_from_package(self):
        """from multiomics_explorer import <fn> works for every api function."""
        from multiomics_explorer import (
            gene_ontology_terms,
            gene_overview,
            genes_by_ontology,
            get_gene_details,
            get_homologs,
            get_schema,
            list_filter_values,
            list_organisms,
            resolve_gene,
            run_cypher,
            search_genes,
            search_ontology,
        )
        # Each should be the same object as in api.functions
        assert resolve_gene is api.resolve_gene
        assert get_homologs is api.get_homologs

    def test_query_expression_removed(self):
        """query_expression is no longer exported (schema migration B1)."""
        import multiomics_explorer
        assert not hasattr(multiomics_explorer, "query_expression")


@pytest.fixture()
def mock_conn():
    """A MagicMock GraphConnection."""
    return MagicMock()


# ---------------------------------------------------------------------------
# get_schema
# ---------------------------------------------------------------------------
class TestGetSchema:
    def test_returns_dict(self, mock_conn):
        mock_schema = MagicMock()
        mock_schema.to_dict.return_value = {
            "nodes": {"Gene": {"properties": {"locus_tag": "string"}}},
            "relationships": {},
        }
        with patch(
            "multiomics_explorer.api.functions.load_schema_from_neo4j",
            return_value=mock_schema,
        ):
            result = api.get_schema(conn=mock_conn)
        assert isinstance(result, dict)
        assert "nodes" in result
        assert "relationships" in result
        mock_schema.to_dict.assert_called_once()

    def test_creates_conn_when_none(self):
        mock_schema = MagicMock()
        mock_schema.to_dict.return_value = {"nodes": {}, "relationships": {}}
        with patch(
            "multiomics_explorer.api.functions.load_schema_from_neo4j",
            return_value=mock_schema,
        ) as mock_load, patch(
            "multiomics_explorer.api.functions.GraphConnection",
        ) as MockConn:
            api.get_schema()
        mock_load.assert_called_once_with(MockConn.return_value)


# ---------------------------------------------------------------------------
# resolve_gene
# ---------------------------------------------------------------------------
class TestResolveGene:
    def test_returns_list(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "DNA polymerase III subunit beta",
             "organism_strain": "Prochlorococcus marinus MED4"},
        ]
        result = api.resolve_gene("PMM0001", conn=mock_conn)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["locus_tag"] == "PMM0001"

    def test_empty_results(self, mock_conn):
        mock_conn.execute_query.return_value = []
        result = api.resolve_gene("FAKE0001", conn=mock_conn)
        assert result == []

    def test_empty_identifier_raises(self, mock_conn):
        with pytest.raises(ValueError, match="identifier must not be empty"):
            api.resolve_gene("", conn=mock_conn)

    def test_whitespace_identifier_raises(self, mock_conn):
        with pytest.raises(ValueError, match="identifier must not be empty"):
            api.resolve_gene("  ", conn=mock_conn)

    def test_organism_filter_passed(self, mock_conn):
        mock_conn.execute_query.return_value = []
        api.resolve_gene("dnaN", organism="MED4", conn=mock_conn)
        _, kwargs = mock_conn.execute_query.call_args
        assert kwargs["organism"] == "MED4"


# ---------------------------------------------------------------------------
# search_genes
# ---------------------------------------------------------------------------
class TestSearchGenes:
    def test_returns_list(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "DNA polymerase III subunit beta",
             "function_description": None, "gene_summary": None,
             "organism_strain": "Prochlorococcus marinus MED4",
             "annotation_quality": 3, "score": 5.0},
        ]
        result = api.search_genes("DNA polymerase", conn=mock_conn)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_lucene_retry_on_error(self, mock_conn):
        """On Neo4jClientError, retries with escaped special chars."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        normal_results = [{"locus_tag": "PMM0001", "gene_name": "dnaN",
                           "product": "p", "function_description": None,
                           "gene_summary": None,
                           "organism_strain": "MED4",
                           "annotation_quality": 3, "score": 1.0}]
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("bad query"),
            normal_results,
        ]
        result = api.search_genes("bad+query", conn=mock_conn)
        assert mock_conn.execute_query.call_count == 2
        assert result == normal_results

    def test_dedup_collapses_orthologs(self, mock_conn):
        """deduplicate=True collapses genes sharing an ortholog group."""
        search_results = [
            {"locus_tag": "PMM0001", "organism_strain": "MED4",
             "gene_name": "dnaN", "product": "p",
             "function_description": None, "gene_summary": None,
             "annotation_quality": 3, "score": 5.0},
            {"locus_tag": "sync_0001", "organism_strain": "WH8102",
             "gene_name": "dnaN", "product": "p",
             "function_description": None, "gene_summary": None,
             "annotation_quality": 3, "score": 4.0},
        ]
        dedup_rows = [
            {"locus_tag": "PMM0001", "dedup_group": "CK_00000364"},
            {"locus_tag": "sync_0001", "dedup_group": "CK_00000364"},
        ]
        mock_conn.execute_query.side_effect = [search_results, dedup_rows]
        result = api.search_genes("DNA polymerase", deduplicate=True, conn=mock_conn)
        assert len(result) == 1
        assert result[0]["locus_tag"] == "PMM0001"
        assert result[0]["collapsed_count"] == 2
        assert "group_organisms" in result[0]

    def test_dedup_preserves_ungrouped(self, mock_conn):
        """Genes without ortholog groups are not collapsed."""
        search_results = [
            {"locus_tag": "PMM0001", "organism_strain": "MED4",
             "gene_name": "dnaN", "product": "p",
             "function_description": None, "gene_summary": None,
             "annotation_quality": 3, "score": 5.0},
            {"locus_tag": "PMM9999", "organism_strain": "MED4",
             "gene_name": None, "product": "hypothetical",
             "function_description": None, "gene_summary": None,
             "annotation_quality": 0, "score": 1.0},
        ]
        dedup_rows = [
            {"locus_tag": "PMM0001", "dedup_group": "CK_00000364"},
            # PMM9999 has no group
        ]
        mock_conn.execute_query.side_effect = [search_results, dedup_rows]
        result = api.search_genes("test", deduplicate=True, conn=mock_conn)
        assert len(result) == 2
        assert result[0]["collapsed_count"] == 1
        assert "collapsed_count" not in result[1]


# ---------------------------------------------------------------------------
# gene_overview
# ---------------------------------------------------------------------------
class TestGeneOverview:
    def test_returns_list(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "DNA polymerase III subunit beta",
             "gene_summary": None, "gene_category": "DNA replication",
             "annotation_quality": 3,
             "organism_strain": "Prochlorococcus marinus MED4",
             "annotation_types": ["go_bp", "ec", "kegg"],
             "expression_edge_count": 10,
             "significant_expression_count": 5,
             "closest_ortholog_group_size": 20,
             "closest_ortholog_genera": "Prochlorococcus,Synechococcus"},
        ]
        result = api.gene_overview(["PMM0001"], conn=mock_conn)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_empty_gene_ids(self, mock_conn):
        mock_conn.execute_query.return_value = []
        result = api.gene_overview([], conn=mock_conn)
        assert result == []


# ---------------------------------------------------------------------------
# get_gene_details
# ---------------------------------------------------------------------------
class TestGetGeneDetails:
    def test_returns_dict(self, mock_conn):
        gene_props = {"locus_tag": "PMM0001", "gene_name": "dnaN",
                       "product": "DNA polymerase III subunit beta"}
        mock_conn.execute_query.return_value = [{"gene": gene_props}]
        result = api.get_gene_details("PMM0001", conn=mock_conn)
        assert isinstance(result, dict)
        assert result["locus_tag"] == "PMM0001"

    def test_not_found_returns_none(self, mock_conn):
        mock_conn.execute_query.return_value = [{"gene": None}]
        result = api.get_gene_details("FAKE0001", conn=mock_conn)
        assert result is None

    def test_empty_results_returns_none(self, mock_conn):
        mock_conn.execute_query.return_value = []
        result = api.get_gene_details("FAKE0001", conn=mock_conn)
        assert result is None



# ---------------------------------------------------------------------------
# get_homologs
# ---------------------------------------------------------------------------
class TestGetHomologs:
    def _gene_stub(self):
        return [{"locus_tag": "PMM0001", "gene_name": "dnaN",
                 "product": "DNA polymerase III subunit beta",
                 "organism_strain": "Prochlorococcus marinus MED4"}]

    def _groups(self):
        return [
            {"og_name": "CK_00000364", "source": "cyanorak",
             "taxonomic_level": "curated", "specificity_rank": 0,
             "consensus_product": "DNA polymerase III subunit beta",
             "consensus_gene_name": "dnaN",
             "member_count": 25, "organism_count": 20,
             "genera": "Prochlorococcus,Synechococcus",
             "has_cross_genus_members": True},
        ]

    def test_returns_dict_with_keys(self, mock_conn):
        mock_conn.execute_query.side_effect = [self._gene_stub(), self._groups()]
        result = api.get_homologs("PMM0001", conn=mock_conn)
        assert isinstance(result, dict)
        assert "query_gene" in result
        assert "ortholog_groups" in result
        assert result["query_gene"]["locus_tag"] == "PMM0001"

    def test_gene_not_found_raises(self, mock_conn):
        mock_conn.execute_query.return_value = []
        with pytest.raises(ValueError, match="not found"):
            api.get_homologs("FAKE0001", conn=mock_conn)

    def test_no_groups_returns_empty_list(self, mock_conn):
        mock_conn.execute_query.side_effect = [self._gene_stub(), []]
        result = api.get_homologs("PMM0001", conn=mock_conn)
        assert result["ortholog_groups"] == []

    def test_invalid_source_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid source"):
            api.get_homologs("PMM0001", source="invalid", conn=mock_conn)

    def test_invalid_taxonomic_level_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid taxonomic_level"):
            api.get_homologs("PMM0001", taxonomic_level="invalid", conn=mock_conn)

    def test_invalid_specificity_rank_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid max_specificity_rank"):
            api.get_homologs("PMM0001", max_specificity_rank=5, conn=mock_conn)

    def test_invalid_member_limit_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid member_limit"):
            api.get_homologs("PMM0001", member_limit=0, conn=mock_conn)

    def test_include_members(self, mock_conn):
        members = [
            {"og_name": "CK_00000364", "locus_tag": "sync_0001",
             "gene_name": "dnaN", "product": "p",
             "organism_strain": "Synechococcus WH8102"},
            {"og_name": "CK_00000364", "locus_tag": "sync_0002",
             "gene_name": "dnaN", "product": "p",
             "organism_strain": "Synechococcus WH7803"},
        ]
        mock_conn.execute_query.side_effect = [
            self._gene_stub(), self._groups(), members,
        ]
        result = api.get_homologs("PMM0001", include_members=True, conn=mock_conn)
        group = result["ortholog_groups"][0]
        assert "members" in group
        assert len(group["members"]) == 2

    def test_member_limit_truncates(self, mock_conn):
        members = [
            {"og_name": "CK_00000364", "locus_tag": f"g{i}",
             "gene_name": None, "product": "p",
             "organism_strain": f"org{i}"}
            for i in range(5)
        ]
        mock_conn.execute_query.side_effect = [
            self._gene_stub(), self._groups(), members,
        ]
        result = api.get_homologs(
            "PMM0001", include_members=True, member_limit=3, conn=mock_conn,
        )
        group = result["ortholog_groups"][0]
        assert len(group["members"]) == 3
        assert group["truncated"] is True

    def test_valid_sources_accepted(self, mock_conn):
        mock_conn.execute_query.side_effect = [self._gene_stub(), self._groups()]
        result = api.get_homologs("PMM0001", source="cyanorak", conn=mock_conn)
        assert "ortholog_groups" in result

    def test_valid_taxonomic_level_accepted(self, mock_conn):
        mock_conn.execute_query.side_effect = [self._gene_stub(), self._groups()]
        result = api.get_homologs(
            "PMM0001", taxonomic_level="curated", conn=mock_conn,
        )
        assert "ortholog_groups" in result


# ---------------------------------------------------------------------------
# list_filter_values
# ---------------------------------------------------------------------------
class TestListFilterValues:
    def test_returns_dict_with_gene_categories(self, mock_conn):
        categories = [{"category": "Photosynthesis", "gene_count": 100}]
        mock_conn.execute_query.return_value = categories
        result = api.list_filter_values(conn=mock_conn)
        assert isinstance(result, dict)
        assert "gene_categories" in result
        assert result["gene_categories"] == categories

    def test_no_condition_types_key(self, mock_conn):
        """condition_types removed in schema migration B1."""
        mock_conn.execute_query.return_value = []
        result = api.list_filter_values(conn=mock_conn)
        assert "condition_types" not in result

    def test_one_query_executed(self, mock_conn):
        mock_conn.execute_query.return_value = []
        api.list_filter_values(conn=mock_conn)
        assert mock_conn.execute_query.call_count == 1


# ---------------------------------------------------------------------------
# list_organisms
# ---------------------------------------------------------------------------
class TestListOrganisms:
    def test_returns_list(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"organism_name": "Prochlorococcus marinus MED4",
             "genus": "Prochlorococcus", "strain": "MED4",
             "clade": "HLI", "gene_count": 1716},
        ]
        result = api.list_organisms(conn=mock_conn)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["organism_name"] == "Prochlorococcus marinus MED4"


# ---------------------------------------------------------------------------
# search_ontology
# ---------------------------------------------------------------------------
class TestSearchOntology:
    def test_returns_list(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"id": "GO:0006260", "name": "DNA replication", "score": 5.0},
        ]
        result = api.search_ontology("DNA replication", "go_bp", conn=mock_conn)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_invalid_ontology_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.search_ontology("test", "invalid", conn=mock_conn)

    def test_lucene_retry(self, mock_conn):
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("bad"),
            [{"id": "GO:0006260", "name": "DNA replication", "score": 1.0}],
        ]
        result = api.search_ontology("bad+query", "go_bp", conn=mock_conn)
        assert mock_conn.execute_query.call_count == 2
        assert len(result) == 1


# ---------------------------------------------------------------------------
# genes_by_ontology
# ---------------------------------------------------------------------------
class TestGenesByOntology:
    def test_returns_list(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "p", "organism_strain": "MED4"},
        ]
        result = api.genes_by_ontology(["GO:0006260"], "go_bp", conn=mock_conn)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_invalid_ontology_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.genes_by_ontology(["GO:0006260"], "invalid", conn=mock_conn)

    def test_organism_filter_passed(self, mock_conn):
        mock_conn.execute_query.return_value = []
        api.genes_by_ontology(
            ["GO:0006260"], "go_bp", organism="MED4", conn=mock_conn,
        )
        _, kwargs = mock_conn.execute_query.call_args
        assert kwargs["organism"] == "MED4"


# ---------------------------------------------------------------------------
# gene_ontology_terms
# ---------------------------------------------------------------------------
class TestGeneOntologyTerms:
    def test_returns_list(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"id": "GO:0006260", "name": "DNA replication"},
        ]
        result = api.gene_ontology_terms("PMM0001", "go_bp", conn=mock_conn)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_invalid_ontology_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.gene_ontology_terms("PMM0001", "invalid", conn=mock_conn)

    def test_leaf_only_default_true(self, mock_conn):
        """Default leaf_only=True is passed through to query builder."""
        mock_conn.execute_query.return_value = []
        api.gene_ontology_terms("PMM0001", "go_bp", conn=mock_conn)
        cypher_arg = mock_conn.execute_query.call_args[0][0]
        # leaf_only=True produces a WHERE NOT EXISTS clause
        assert "NOT EXISTS" in cypher_arg


# ---------------------------------------------------------------------------
# run_cypher
# ---------------------------------------------------------------------------
class TestRunCypher:
    def test_returns_list(self, mock_conn):
        mock_conn.execute_query.return_value = [{"count": 42}]
        result = api.run_cypher("MATCH (g:Gene) RETURN count(g) AS count", conn=mock_conn)
        assert isinstance(result, list)
        assert result[0]["count"] == 42

    def test_write_keyword_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Write operations"):
            api.run_cypher("CREATE (n:Test)", conn=mock_conn)

    def test_merge_blocked(self, mock_conn):
        with pytest.raises(ValueError, match="Write operations"):
            api.run_cypher("MERGE (n:Test {id: 1})", conn=mock_conn)

    def test_delete_blocked(self, mock_conn):
        with pytest.raises(ValueError, match="Write operations"):
            api.run_cypher("MATCH (n) DELETE n", conn=mock_conn)

    def test_read_query_passes(self, mock_conn):
        mock_conn.execute_query.return_value = []
        result = api.run_cypher("MATCH (n) RETURN n LIMIT 10", conn=mock_conn)
        assert result == []
