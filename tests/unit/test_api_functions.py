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
    def test_returns_dict_with_total_and_results(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "DNA polymerase III subunit beta",
             "organism_strain": "Prochlorococcus marinus MED4"},
        ]
        result = api.resolve_gene("PMM0001", conn=mock_conn)
        assert isinstance(result, dict)
        assert "total_matching" in result
        assert "results" in result
        assert result["total_matching"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["locus_tag"] == "PMM0001"

    def test_empty_results(self, mock_conn):
        mock_conn.execute_query.return_value = []
        result = api.resolve_gene("FAKE0001", conn=mock_conn)
        assert result == {"total_matching": 0, "results": []}

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

    def test_limit_slices_results(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": f"PMM000{i}", "gene_name": "g",
             "product": "p", "organism_strain": "MED4"}
            for i in range(3)
        ]
        result = api.resolve_gene("PMM", limit=2, conn=mock_conn)
        assert result["total_matching"] == 3
        assert len(result["results"]) == 2

    def test_total_matching_reflects_full_count(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": f"PMM000{i}", "gene_name": "g",
             "product": "p", "organism_strain": "MED4"}
            for i in range(5)
        ]
        result = api.resolve_gene("PMM", limit=2, conn=mock_conn)
        assert result["total_matching"] == 5
        assert len(result["results"]) == 2


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
    _ROWS = [
        {"organism_name": "Prochlorococcus MED4", "genus": "Prochlorococcus",
         "species": "Prochlorococcus marinus", "strain": "MED4", "clade": "HLI",
         "ncbi_taxon_id": 59919, "gene_count": 1976, "publication_count": 11,
         "experiment_count": 46, "treatment_types": ["coculture", "light_stress"],
         "omics_types": ["RNASEQ", "PROTEOMICS"]},
        {"organism_name": "Alteromonas macleodii EZ55", "genus": "Alteromonas",
         "species": "Alteromonas macleodii", "strain": "EZ55", "clade": None,
         "ncbi_taxon_id": 28108, "gene_count": 4136, "publication_count": 2,
         "experiment_count": 13, "treatment_types": ["carbon_stress"],
         "omics_types": ["RNASEQ"]},
    ]

    def test_returns_dict(self, mock_conn):
        mock_conn.execute_query.return_value = self._ROWS
        result = api.list_organisms(conn=mock_conn)
        assert isinstance(result, dict)
        assert result["total_entries"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["organism_name"] == "Prochlorococcus MED4"

    def test_passes_verbose(self, mock_conn):
        mock_conn.execute_query.return_value = []
        api.list_organisms(verbose=True, conn=mock_conn)
        cypher = mock_conn.execute_query.call_args[0][0]
        assert "family" in cypher

    def test_limit_slices_results(self, mock_conn):
        mock_conn.execute_query.return_value = self._ROWS
        result = api.list_organisms(limit=1, conn=mock_conn)
        assert result["total_entries"] == 2
        assert len(result["results"]) == 1

    def test_limit_none_returns_all(self, mock_conn):
        mock_conn.execute_query.return_value = self._ROWS
        result = api.list_organisms(conn=mock_conn)
        assert len(result["results"]) == 2


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


# ---------------------------------------------------------------------------
# list_publications
# ---------------------------------------------------------------------------
class TestListPublications:
    def test_returns_dict(self, mock_conn):
        """Runs summary + data queries, returns dict with total_entries/total_matching/results."""
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21, "total_matching": 21}],  # summary query
            [{"doi": "10.1234/test", "title": "Test"}],      # data query
        ]
        result = api.list_publications(conn=mock_conn)
        assert isinstance(result, dict)
        assert result["total_entries"] == 21
        assert result["total_matching"] == 21
        assert len(result["results"]) == 1
        assert mock_conn.execute_query.call_count == 2

    def test_passes_params(self, mock_conn):
        """All filter params are forwarded to builders."""
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21, "total_matching": 5}],
            [{"doi": "10.1234/test"}],
        ]
        result = api.list_publications(
            organism="MED4", treatment_type="coculture",
            search_text="nitrogen", author="Sher",
            verbose=True, limit=10, conn=mock_conn,
        )
        # Verify summary query was called with filter params
        summary_call = mock_conn.execute_query.call_args_list[0]
        assert "$search_text" in summary_call[0][0]
        assert "organism" in summary_call[1]  # kwargs contain param keys
        # Verify data query was called with verbose + limit
        data_call = mock_conn.execute_query.call_args_list[1]
        assert "abstract" in data_call[0][0]  # verbose columns in Cypher
        assert "LIMIT $limit" in data_call[0][0]

    def test_creates_conn_when_none(self):
        """Default conn used when None."""
        with patch(
            "multiomics_explorer.api.functions.GraphConnection",
        ) as MockConn:
            mock_instance = MockConn.return_value
            mock_instance.execute_query.side_effect = [
                [{"total_entries": 0, "total_matching": 0}],
                [],
            ]
            result = api.list_publications()
        MockConn.assert_called_once()
        assert result["total_matching"] == 0

    def test_lucene_escape_retry(self, mock_conn):
        """Neo4jClientError with search_text triggers escaped retry."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("Lucene parse error"),
            # Retry calls:
            [{"total_entries": 21, "total_matching": 1}],
            [{"doi": "10.1234/test"}],
        ]
        result = api.list_publications(search_text="DNA [repair", conn=mock_conn)
        assert result["total_matching"] == 1
        assert mock_conn.execute_query.call_count == 3  # 1 failed + 2 retry

    def test_lucene_error_without_search_text_raises(self, mock_conn):
        """Neo4jClientError without search_text is not caught."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = Neo4jClientError("Some error")
        with pytest.raises(Neo4jClientError):
            api.list_publications(conn=mock_conn)

    def test_importable_from_package(self):
        """from multiomics_explorer import list_publications works."""
        from multiomics_explorer import list_publications
        assert list_publications is api.list_publications


class TestListExperiments:
    """Tests for list_experiments API function."""

    def _summary_result(self, total_matching=76, time_course_count=29):
        """Helper: mock summary query result."""
        return [{
            "total_matching": total_matching,
            "time_course_count": time_course_count,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 30}],
            "by_treatment_type": [{"item": "coculture", "count": 16}],
            "by_omics_type": [{"item": "RNASEQ", "count": 48}],
            "by_publication": [{"item": "10.1038/ismej.2016.70", "count": 5}],
        }]

    def _detail_row(self, **overrides):
        """Helper: mock detail query result row."""
        row = {
            "experiment_id": "test_exp_1",
            "publication_doi": "10.1234/test",
            "organism_strain": "Prochlorococcus MED4",
            "treatment_type": "coculture",
            "coculture_partner": "Alteromonas macleodii HOT1A3",
            "omics_type": "RNASEQ",
            "is_time_course": "false",
            "gene_count": 1696,
            "significant_count": 423,
            "time_point_count": 1,
            "time_point_labels": ["20h"],
            "time_point_orders": [1],
            "time_point_hours": [20.0],
            "time_point_totals": [1696],
            "time_point_significants": [423],
        }
        row.update(overrides)
        return row

    def _tc_detail_row(self):
        """Helper: mock time-course detail row."""
        return self._detail_row(
            experiment_id="test_tc_1",
            is_time_course="true",
            time_point_count=3,
            time_point_labels=["2h", "12h", "24h"],
            time_point_orders=[1, 2, 3],
            time_point_hours=[2.0, 12.0, 24.0],
            time_point_totals=[353, 353, 353],
            time_point_significants=[0, 85, 258],
        )

    def test_detail_returns_dict(self, mock_conn):
        """Detail mode returns dict with breakdowns + results."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),       # filtered summary
            self._summary_result(),       # unfiltered total_entries
            [self._detail_row()],         # detail query
        ]
        result = api.list_experiments(mode="detail", conn=mock_conn)
        assert isinstance(result, dict)
        assert "total_entries" in result
        assert "total_matching" in result
        assert "by_organism" in result
        assert "by_treatment_type" in result
        assert "results" in result
        assert len(result["results"]) == 1

    def test_summary_returns_dict(self, mock_conn):
        """Summary mode returns dict with breakdowns + empty results."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),  # filtered summary
            self._summary_result(),  # unfiltered total_entries
        ]
        result = api.list_experiments(mode="summary", conn=mock_conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert result["by_organism"][0]["organism_strain"] == "Prochlorococcus MED4"
        assert result["by_organism"][0]["experiment_count"] == 30
        # No detail query call — only 2 execute_query calls
        assert mock_conn.execute_query.call_count == 2

    def test_passes_params(self, mock_conn):
        """All filter params forwarded to builders."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_matching=5),
            self._summary_result(),
            [self._detail_row()],
        ]
        api.list_experiments(
            organism="MED4", treatment_type=["coculture"],
            omics_type=["RNASEQ"], publication_doi=["10.1234/test"],
            coculture_partner="Alteromonas", time_course_only=True,
            mode="detail", verbose=True, limit=10, conn=mock_conn,
        )
        # Summary query has filter params
        summary_call = mock_conn.execute_query.call_args_list[0]
        assert "org" in summary_call[1]
        assert "treatment_types" in summary_call[1]
        # Detail query has verbose + limit
        detail_call = mock_conn.execute_query.call_args_list[2]
        assert "e.name AS name" in detail_call[0][0]
        assert "LIMIT $limit" in detail_call[0][0]

    def test_is_time_course_cast(self, mock_conn):
        """is_time_course string cast to bool."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._detail_row(is_time_course="true"),
             self._detail_row(is_time_course="false")],
        ]
        result = api.list_experiments(mode="detail", conn=mock_conn)
        assert result["results"][0]["is_time_course"] is True
        assert result["results"][1]["is_time_course"] is False

    def test_time_points_assembled(self, mock_conn):
        """Parallel arrays assembled into time_points list of dicts for time-course."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._tc_detail_row()],
        ]
        result = api.list_experiments(mode="detail", conn=mock_conn)
        row = result["results"][0]
        assert "time_points" in row
        assert len(row["time_points"]) == 3
        tp = row["time_points"][0]
        assert tp["label"] == "2h"
        assert tp["order"] == 1
        assert tp["hours"] == 2.0
        assert tp["total"] == 353
        assert tp["significant"] == 0

    def test_time_points_omitted(self, mock_conn):
        """Non-time-course results have no time_points key."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._detail_row(is_time_course="false")],
        ]
        result = api.list_experiments(mode="detail", conn=mock_conn)
        assert "time_points" not in result["results"][0]

    def test_sentinel_conversion(self, mock_conn):
        """Sentinel values converted: '' label -> None, -1.0 hours -> None."""
        tc_row = self._detail_row(
            is_time_course="true",
            time_point_count=1,
            time_point_labels=[""],
            time_point_orders=[1],
            time_point_hours=[-1.0],
            time_point_totals=[100],
            time_point_significants=[10],
        )
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [tc_row],
        ]
        result = api.list_experiments(mode="detail", conn=mock_conn)
        tp = result["results"][0]["time_points"][0]
        assert tp["label"] is None
        assert tp["hours"] is None

    def test_limit_slices_results(self, mock_conn):
        """Limit passed to builder, total_matching from summary."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_matching=76),
            self._summary_result(),
            [self._detail_row()],  # only 1 returned due to limit
        ]
        result = api.list_experiments(mode="detail", limit=1, conn=mock_conn)
        assert result["total_matching"] == 76
        assert result["returned"] == 1
        assert result["truncated"] is True

    def test_breakdowns_computed(self, mock_conn):
        """Breakdowns renamed from apoc format to domain keys."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
        ]
        result = api.list_experiments(mode="summary", conn=mock_conn)
        assert result["by_organism"][0]["organism_strain"] == "Prochlorococcus MED4"
        assert result["by_organism"][0]["experiment_count"] == 30
        assert result["by_treatment_type"][0]["treatment_type"] == "coculture"
        assert result["by_omics_type"][0]["omics_type"] == "RNASEQ"
        assert result["by_publication"][0]["publication_doi"] == "10.1038/ismej.2016.70"

    def test_creates_conn_when_none(self):
        """Default conn used when None."""
        with patch(
            "multiomics_explorer.api.functions.GraphConnection",
        ) as MockConn:
            mock_instance = MockConn.return_value
            mock_instance.execute_query.side_effect = [
                self._summary_result(total_matching=0),
                self._summary_result(total_matching=0),
            ]
            result = api.list_experiments(mode="summary")
        MockConn.assert_called_once()
        assert result["total_matching"] == 0

    def test_importable_from_package(self):
        """from multiomics_explorer import list_experiments works."""
        from multiomics_explorer import list_experiments
        assert list_experiments is api.list_experiments
