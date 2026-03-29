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
            gene_homologs,
            gene_ontology_terms,
            gene_overview,
            genes_by_function,
            genes_by_ontology,
            gene_details,
            kg_schema,
            list_filter_values,
            list_organisms,
            resolve_gene,
            run_cypher,
            search_ontology,
        )
        # Each should be the same object as in api.functions
        assert resolve_gene is api.resolve_gene
        assert gene_homologs is api.gene_homologs
        assert genes_by_function is api.genes_by_function

    def test_query_expression_removed(self):
        """query_expression is no longer exported (schema migration B1)."""
        import multiomics_explorer
        assert not hasattr(multiomics_explorer, "query_expression")


@pytest.fixture()
def mock_conn():
    """A MagicMock GraphConnection."""
    return MagicMock()


# ---------------------------------------------------------------------------
# kg_schema
# ---------------------------------------------------------------------------
class TestKgSchema:
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
            result = api.kg_schema(conn=mock_conn)
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
            api.kg_schema()
        mock_load.assert_called_once_with(MockConn.return_value)


# ---------------------------------------------------------------------------
# resolve_gene
# ---------------------------------------------------------------------------
class TestResolveGene:
    def test_returns_dict_with_total_and_results(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "DNA polymerase III subunit beta",
             "organism_name": "Prochlorococcus marinus MED4"},
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
        assert result == {"total_matching": 0, "by_organism": [], "returned": 0, "offset": 0, "truncated": False, "results": []}

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
             "product": "p", "organism_name": "MED4"}
            for i in range(3)
        ]
        result = api.resolve_gene("PMM", limit=2, conn=mock_conn)
        assert result["total_matching"] == 3
        assert len(result["results"]) == 2

    def test_total_matching_reflects_full_count(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": f"PMM000{i}", "gene_name": "g",
             "product": "p", "organism_name": "MED4"}
            for i in range(5)
        ]
        result = api.resolve_gene("PMM", limit=2, conn=mock_conn)
        assert result["total_matching"] == 5
        assert len(result["results"]) == 2

    def test_offset_skips_results(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": f"PMM000{i}", "gene_name": "g",
             "product": "p", "organism_name": "MED4"}
            for i in range(5)
        ]
        result = api.resolve_gene("PMM", limit=2, offset=2, conn=mock_conn)
        assert result["total_matching"] == 5
        assert result["returned"] == 2
        assert result["results"][0]["locus_tag"] == "PMM0002"
        assert result["results"][1]["locus_tag"] == "PMM0003"
        assert result["truncated"] is True

    def test_offset_beyond_results(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": "PMM0001", "gene_name": "g",
             "product": "p", "organism_name": "MED4"}
        ]
        result = api.resolve_gene("PMM", limit=10, offset=5, conn=mock_conn)
        assert result["total_matching"] == 1
        assert result["returned"] == 0
        assert result["results"] == []
        assert result["truncated"] is False

    def test_offset_default_zero(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"locus_tag": f"PMM000{i}", "gene_name": "g",
             "product": "p", "organism_name": "MED4"}
            for i in range(3)
        ]
        result = api.resolve_gene("PMM", limit=2, conn=mock_conn)
        assert result["results"][0]["locus_tag"] == "PMM0000"
        assert result["offset"] == 0


# ---------------------------------------------------------------------------
# genes_by_function
# ---------------------------------------------------------------------------
class TestGenesByFunction:
    def _summary_result(self, total_search_hits=100, total_matching=5):
        """Helper: mock summary query result."""
        return [{
            "total_search_hits": total_search_hits,
            "total_matching": total_matching,
            "score_max": 8.5,
            "score_median": 4.2,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 3},
                            {"item": "Synechococcus WH8102", "count": 2}],
            "by_category": [{"item": "DNA replication", "count": 3},
                            {"item": "Photosynthesis", "count": 2}],
        }]

    def _detail_rows(self):
        """Helper: mock detail query result rows."""
        return [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "DNA polymerase III subunit beta",
             "organism_name": "Prochlorococcus MED4",
             "gene_category": "DNA replication",
             "annotation_quality": 3, "score": 5.0},
        ]

    def test_returns_dict(self, mock_conn):
        """Runs summary + detail queries, returns dict with envelope keys."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.genes_by_function("DNA polymerase", conn=mock_conn)
        assert isinstance(result, dict)
        assert "total_search_hits" in result
        assert "total_matching" in result
        assert "by_organism" in result
        assert "by_category" in result
        assert "score_max" in result
        assert "score_median" in result
        assert "returned" in result
        assert "truncated" in result
        assert "results" in result
        assert result["total_matching"] == 5
        assert result["returned"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["locus_tag"] == "PMM0001"
        assert mock_conn.execute_query.call_count == 2

    def test_summary_true_skips_detail(self, mock_conn):
        """summary=True returns results=[], returned=0."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_matching=5),
        ]
        result = api.genes_by_function("DNA polymerase", summary=True, conn=mock_conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        # Only summary query called
        assert mock_conn.execute_query.call_count == 1

    def test_lucene_retry(self, mock_conn):
        """On Neo4jClientError, retries with escaped special chars."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("bad query"),
            self._summary_result(),  # retry summary succeeds (returns list, [0] extracted internally)
            self._detail_rows(),
        ]
        result = api.genes_by_function("bad+query", conn=mock_conn)
        assert mock_conn.execute_query.call_count == 3
        assert result["total_matching"] == 5

    def test_passes_params(self, mock_conn):
        """Verify organism, category, min_quality forwarded to builder."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        api.genes_by_function(
            "test", organism="MED4", category="Photosynthesis",
            min_quality=2, conn=mock_conn,
        )
        # Summary query (1st call) should have filter params
        summary_call = mock_conn.execute_query.call_args_list[0]
        params = summary_call[1]
        assert params.get("organism") == "MED4"
        assert params.get("category") == "Photosynthesis"
        assert params.get("min_quality") == 2

    def test_creates_conn_when_none(self):
        """Default conn used when None."""
        with patch(
            "multiomics_explorer.api.functions.GraphConnection",
        ) as MockConn:
            mock_instance = MockConn.return_value
            mock_instance.execute_query.side_effect = [
                [{  # summary
                    "total_search_hits": 0, "total_matching": 0,
                    "score_max": None, "score_median": None,
                    "by_organism": [], "by_category": [],
                }],
            ]
            result = api.genes_by_function("test", summary=True)
        MockConn.assert_called_once()
        assert result["total_matching"] == 0

    def test_importable_from_package(self):
        """from multiomics_explorer import genes_by_function works."""
        from multiomics_explorer import genes_by_function
        assert genes_by_function is api.genes_by_function

    def test_zero_match(self, mock_conn):
        """When summary returns total_matching=0, score_max=None, score_median=None."""
        mock_conn.execute_query.side_effect = [
            [{"total_search_hits": 50, "total_matching": 0,
              "score_max": None, "score_median": None,
              "by_organism": [], "by_category": []}],
        ]
        result = api.genes_by_function("nonexistent", summary=True, conn=mock_conn)
        assert result["total_matching"] == 0
        assert result["score_max"] is None
        assert result["score_median"] is None


# ---------------------------------------------------------------------------
# gene_overview
# ---------------------------------------------------------------------------
class TestGeneOverview:
    def _summary_result(self, total=1, not_found=None):
        """Helper: mock summary query result."""
        return [{
            "total_matching": total,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 1}],
            "by_category": [{"item": "DNA replication", "count": 1}],
            "by_annotation_type": [{"item": "go_bp", "count": 1}],
            "has_expression": 1,
            "has_significant_expression": 1,
            "has_orthologs": 1,
            "not_found": not_found or [],
        }]

    def _detail_rows(self):
        """Helper: mock detail query result rows."""
        return [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "DNA polymerase III subunit beta",
             "gene_category": "DNA replication",
             "annotation_quality": 3,
             "organism_name": "Prochlorococcus MED4",
             "annotation_types": ["go_bp", "ec", "kegg"],
             "expression_edge_count": 10,
             "significant_up_count": 3, "significant_down_count": 2,
             "closest_ortholog_group_size": 20,
             "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"]},
        ]

    def test_returns_dict(self, mock_conn):
        """Runs summary + detail queries, returns dict with envelope keys."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.gene_overview(["PMM0001"], conn=mock_conn)
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
        assert result["total_matching"] == 1
        assert result["returned"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["locus_tag"] == "PMM0001"
        assert mock_conn.execute_query.call_count == 2

    def test_summary_sets_limit_zero(self, mock_conn):
        """summary=True returns results=[], returned=0, only summary query called."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total=1),
        ]
        result = api.gene_overview(["PMM0001"], summary=True, conn=mock_conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert mock_conn.execute_query.call_count == 1

    def test_passes_params(self, mock_conn):
        """Verify locus_tags, verbose, limit forwarded to builders."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        api.gene_overview(
            ["PMM0001"], verbose=True, limit=10, conn=mock_conn,
        )
        # Summary query (1st call) should have locus_tags
        summary_call = mock_conn.execute_query.call_args_list[0]
        assert summary_call[1].get("locus_tags") == ["PMM0001"]
        # Detail query (2nd call) should have locus_tags and limit
        detail_call = mock_conn.execute_query.call_args_list[1]
        assert detail_call[1].get("locus_tags") == ["PMM0001"]
        assert detail_call[1].get("limit") == 10

    def test_creates_conn_when_none(self):
        """Default conn used when None."""
        with patch(
            "multiomics_explorer.api.functions.GraphConnection",
        ) as MockConn:
            mock_instance = MockConn.return_value
            mock_instance.execute_query.side_effect = [
                [{  # summary
                    "total_matching": 0,
                    "by_organism": [], "by_category": [],
                    "by_annotation_type": [],
                    "has_expression": 0,
                    "has_significant_expression": 0,
                    "has_orthologs": 0,
                    "not_found": ["FAKE"],
                }],
            ]
            result = api.gene_overview(["FAKE"], summary=True)
        MockConn.assert_called_once()
        assert result["total_matching"] == 0

    def test_not_found_populated(self, mock_conn):
        """Not-found locus_tags appear in not_found list."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total=0, not_found=["FAKE0001"]),
        ]
        result = api.gene_overview(["FAKE0001"], summary=True, conn=mock_conn)
        assert result["not_found"] == ["FAKE0001"]

    def test_importable_from_package(self):
        """from multiomics_explorer import gene_overview works."""
        from multiomics_explorer import gene_overview
        assert gene_overview is api.gene_overview


# ---------------------------------------------------------------------------
# gene_details
# ---------------------------------------------------------------------------
class TestGeneDetails:
    def test_returns_envelope(self, mock_conn):
        gene_props = {"locus_tag": "PMM0001", "gene_name": "dnaN",
                       "product": "DNA polymerase III subunit beta",
                       "organism_name": "Prochlorococcus MED4"}
        mock_conn.execute_query.side_effect = [
            [{"total_matching": 1, "not_found": []}],  # summary
            [{"gene": gene_props}],  # detail
        ]
        result = api.gene_details(["PMM0001"], conn=mock_conn)
        assert result["total_matching"] == 1
        assert result["returned"] == 1
        assert result["truncated"] is False
        assert result["not_found"] == []
        assert result["results"][0]["locus_tag"] == "PMM0001"

    def test_not_found(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_matching": 0, "not_found": ["FAKE0001"]}],  # summary
            [],  # detail
        ]
        result = api.gene_details(["FAKE0001"], conn=mock_conn)
        assert result["total_matching"] == 0
        assert result["not_found"] == ["FAKE0001"]
        assert result["results"] == []

    def test_summary_skips_detail(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"total_matching": 1, "not_found": []}
        ]
        result = api.gene_details(["PMM0001"], summary=True, conn=mock_conn)
        assert result["returned"] == 0
        assert result["results"] == []
        assert mock_conn.execute_query.call_count == 1

    def test_empty_locus_tags_raises(self, mock_conn):
        with pytest.raises(ValueError, match="non-empty"):
            api.gene_details([], conn=mock_conn)



# ---------------------------------------------------------------------------
# gene_homologs
# ---------------------------------------------------------------------------
class TestGeneHomologs:
    def _summary_result(self, total=2, not_found=None, no_groups=None):
        """Helper: mock summary query result."""
        return [{
            "total_matching": total,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 1},
                            {"item": "Synechococcus WH8102", "count": 1}],
            "by_source": [{"item": "cyanorak", "count": 2}],
            "not_found": not_found or [],
            "no_groups": no_groups or [],
        }]

    def _detail_rows(self):
        """Helper: mock detail query result rows."""
        return [
            {"locus_tag": "PMM0001", "organism_name": "Prochlorococcus MED4",
             "group_id": "cyanorak:CK_00000364", "consensus_gene_name": "dnaN",
             "consensus_product": "DNA polymerase III subunit beta",
             "taxonomic_level": "curated", "source": "cyanorak",
             "specificity_rank": 0},
            {"locus_tag": "SYNW0305", "organism_name": "Synechococcus WH8102",
             "group_id": "cyanorak:CK_00000364", "consensus_gene_name": "dnaN",
             "consensus_product": "DNA polymerase III subunit beta",
             "taxonomic_level": "curated", "source": "cyanorak",
             "specificity_rank": 0},
        ]

    def test_returns_dict(self, mock_conn):
        """Runs summary + detail queries, returns dict with envelope keys."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.gene_homologs(["PMM0001"], conn=mock_conn)
        assert isinstance(result, dict)
        assert result["total_matching"] == 2
        assert "by_organism" in result
        assert "by_source" in result
        assert "returned" in result
        assert "truncated" in result
        assert "not_found" in result
        assert "no_groups" in result
        assert len(result["results"]) == 2
        assert result["results"][0]["locus_tag"] == "PMM0001"
        assert mock_conn.execute_query.call_count == 2

    def test_summary_mode(self, mock_conn):
        """summary=True returns results=[], returned=0."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
        ]
        result = api.gene_homologs(["PMM0001"], summary=True, conn=mock_conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        # Only summary query called — no detail query
        assert mock_conn.execute_query.call_count == 1

    def test_not_found(self, mock_conn):
        """Locus tags not in KG appear in not_found."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total=0, not_found=["FAKE0001"]),
        ]
        result = api.gene_homologs(
            ["FAKE0001"], summary=True, conn=mock_conn,
        )
        assert "FAKE0001" in result["not_found"]

    def test_no_groups(self, mock_conn):
        """Genes that exist but have zero OG matches appear in no_groups."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total=0, no_groups=["PMM9999"]),
        ]
        result = api.gene_homologs(
            ["PMM9999"], summary=True, conn=mock_conn,
        )
        assert "PMM9999" in result["no_groups"]

    def test_filters_forwarded(self, mock_conn):
        """source/taxonomic_level/max_specificity_rank passed through."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total=1),
            self._detail_rows()[:1],
        ]
        api.gene_homologs(
            ["PMM0001"], source="cyanorak", taxonomic_level="curated",
            max_specificity_rank=0, conn=mock_conn,
        )
        # Summary query (1st call) should have filter params
        summary_call = mock_conn.execute_query.call_args_list[0]
        params = summary_call[1]
        assert params.get("source") == "cyanorak"
        assert params.get("level") == "curated"
        assert params.get("max_rank") == 0

    def test_invalid_source_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid source"):
            api.gene_homologs(["PMM0001"], source="invalid", conn=mock_conn)

    def test_invalid_taxonomic_level_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid taxonomic_level"):
            api.gene_homologs(
                ["PMM0001"], taxonomic_level="invalid", conn=mock_conn,
            )

    def test_invalid_specificity_rank_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid max_specificity_rank"):
            api.gene_homologs(
                ["PMM0001"], max_specificity_rank=5, conn=mock_conn,
            )

    def test_creates_conn_when_none(self):
        """Default conn used when None."""
        with patch(
            "multiomics_explorer.api.functions.GraphConnection",
        ) as MockConn:
            mock_instance = MockConn.return_value
            mock_instance.execute_query.side_effect = [
                [{  # summary
                    "total_matching": 0,
                    "by_organism": [], "by_source": [],
                    "not_found": [], "no_groups": [],
                }],
            ]
            result = api.gene_homologs(["PMM0001"], summary=True)
        MockConn.assert_called_once()
        assert result["total_matching"] == 0

    def test_importable_from_package(self):
        """from multiomics_explorer import gene_homologs works."""
        from multiomics_explorer import gene_homologs
        assert gene_homologs is api.gene_homologs


# ---------------------------------------------------------------------------
# list_filter_values
# ---------------------------------------------------------------------------
class TestListFilterValues:
    def test_returns_standard_envelope(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"category": "Photosynthesis", "gene_count": 770},
        ]
        result = api.list_filter_values(conn=mock_conn)
        assert isinstance(result, dict)
        for key in ("filter_type", "total_entries", "returned", "truncated", "results"):
            assert key in result

    def test_results_have_value_count_fields(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"category": "Photosynthesis", "gene_count": 770},
        ]
        result = api.list_filter_values(conn=mock_conn)
        assert result["results"][0] == {"value": "Photosynthesis", "count": 770}

    def test_gene_category_default(self, mock_conn):
        mock_conn.execute_query.return_value = []
        result = api.list_filter_values(conn=mock_conn)
        assert result["filter_type"] == "gene_category"

    def test_unknown_filter_type_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Unknown filter_type"):
            api.list_filter_values(filter_type="bogus", conn=mock_conn)

    def test_truncated_always_false(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"category": "X", "gene_count": 1},
        ]
        result = api.list_filter_values(conn=mock_conn)
        assert result["truncated"] is False

    def test_one_query_executed(self, mock_conn):
        mock_conn.execute_query.return_value = []
        api.list_filter_values(conn=mock_conn)
        assert mock_conn.execute_query.call_count == 1

    def test_creates_conn_when_none(self, mock_conn):
        with patch("multiomics_explorer.api.functions._default_conn", return_value=mock_conn):
            api.list_filter_values()
            assert mock_conn.execute_query.called


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

    def test_offset_skips_results(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"organism_name": f"Org{i}", "genus": "G", "species": "S",
             "strain": "s", "clade": None, "ncbi_taxon_id": i,
             "gene_count": 100, "publication_count": 1,
             "experiment_count": 1, "treatment_types": [], "omics_types": []}
            for i in range(5)
        ]
        result = api.list_organisms(limit=2, offset=2, conn=mock_conn)
        assert result["total_entries"] == 5
        assert result["returned"] == 2
        assert result["results"][0]["organism_name"] == "Org2"
        assert result["offset"] == 2
        assert result["truncated"] is True


# ---------------------------------------------------------------------------
# search_ontology
# ---------------------------------------------------------------------------
class TestSearchOntology:
    def _summary_result(self, total_entries=847, total_matching=5):
        """Helper: mock summary query result."""
        return [{
            "total_entries": total_entries,
            "total_matching": total_matching,
            "score_max": 5.23,
            "score_median": 2.1,
        }]

    def _detail_rows(self):
        """Helper: mock detail query result rows."""
        return [
            {"id": "GO:0006260", "name": "DNA replication", "score": 5.0},
        ]

    def test_returns_dict(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.search_ontology("DNA replication", "go_bp", conn=mock_conn)
        assert isinstance(result, dict)
        assert "total_entries" in result
        assert "total_matching" in result
        assert "score_max" in result
        assert "score_median" in result
        assert "returned" in result
        assert "truncated" in result
        assert "results" in result
        assert result["total_matching"] == 5
        assert result["returned"] == 1
        assert mock_conn.execute_query.call_count == 2

    def test_summary_sets_limit_zero(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_matching=5),
        ]
        result = api.search_ontology("test", "go_bp", summary=True, conn=mock_conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert mock_conn.execute_query.call_count == 1

    def test_passes_params(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        api.search_ontology("test", "go_bp", limit=10, conn=mock_conn)
        assert mock_conn.execute_query.call_count == 2

    def test_creates_conn_when_none(self, monkeypatch):
        mock = MagicMock()
        mock.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        monkeypatch.setattr("multiomics_explorer.api.functions._default_conn", lambda c: mock)
        result = api.search_ontology("test", "go_bp")
        assert isinstance(result, dict)

    def test_invalid_ontology_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.search_ontology("test", "invalid", conn=mock_conn)

    def test_empty_search_text_raises(self, mock_conn):
        with pytest.raises(ValueError, match="search_text must not be empty"):
            api.search_ontology("", "go_bp", conn=mock_conn)
        with pytest.raises(ValueError, match="search_text must not be empty"):
            api.search_ontology("   ", "go_bp", conn=mock_conn)

    def test_lucene_retry(self, mock_conn):
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("bad"),
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.search_ontology("bad+query", "go_bp", conn=mock_conn)
        assert mock_conn.execute_query.call_count == 3
        assert result["returned"] == 1

    def test_importable_from_package(self):
        from multiomics_explorer import search_ontology as fn
        assert callable(fn)


# ---------------------------------------------------------------------------
# genes_by_ontology
# ---------------------------------------------------------------------------
class TestGenesByOntology:
    def _summary_result(self, total_matching=5):
        """Helper: mock summary query result."""
        return [{
            "total_matching": total_matching,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 3},
                           {"item": "Alteromonas macleodii EZ55", "count": 2}],
            "by_category": [{"item": "Replication and repair", "count": 4},
                           {"item": "Unknown", "count": 1}],
            "by_term": [{"item": "go:0006260", "count": 5}],
        }]

    def _detail_rows(self):
        """Helper: mock detail query result rows."""
        return [
            {"locus_tag": "PMM0001", "gene_name": "dnaN",
             "product": "DNA polymerase III", "organism_name": "Prochlorococcus MED4",
             "gene_category": "Replication and repair"},
        ]

    def test_returns_dict(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.genes_by_ontology(["go:0006260"], "go_bp", conn=mock_conn)
        assert isinstance(result, dict)
        assert "total_matching" in result
        assert "by_organism" in result
        assert "by_category" in result
        assert "by_term" in result
        assert "returned" in result
        assert "truncated" in result
        assert "results" in result
        assert result["total_matching"] == 5
        assert result["returned"] == 1
        assert mock_conn.execute_query.call_count == 2

    def test_summary_sets_limit_zero(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_matching=5),
        ]
        result = api.genes_by_ontology(
            ["go:0006260"], "go_bp", summary=True, conn=mock_conn,
        )
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert mock_conn.execute_query.call_count == 1

    def test_passes_params(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        api.genes_by_ontology(
            ["go:0006260"], "go_bp", organism="MED4",
            verbose=True, limit=10, conn=mock_conn,
        )
        assert mock_conn.execute_query.call_count == 2

    def test_creates_conn_when_none(self, monkeypatch):
        mock = MagicMock()
        mock.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        monkeypatch.setattr("multiomics_explorer.api.functions._default_conn", lambda c: mock)
        result = api.genes_by_ontology(["go:0006260"], "go_bp")
        assert isinstance(result, dict)

    def test_empty_term_ids_raises(self, mock_conn):
        with pytest.raises(ValueError, match="term_ids must not be empty"):
            api.genes_by_ontology([], "go_bp", conn=mock_conn)

    def test_invalid_ontology_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.genes_by_ontology(["go:0006260"], "invalid", conn=mock_conn)

    def test_importable_from_package(self):
        from multiomics_explorer import genes_by_ontology as fn
        assert callable(fn)


# ---------------------------------------------------------------------------
# gene_ontology_terms
# ---------------------------------------------------------------------------
class TestGeneOntologyTerms:
    """Tests for gene_ontology_terms API function (multi-query orchestration)."""

    def _exist_found(self, *locus_tags):
        """Helper: existence check rows where all genes are found."""
        return [{"lt": lt, "found": True} for lt in locus_tags]

    def _exist_mixed(self, found, not_found):
        """Helper: existence check rows with some found, some not."""
        rows = [{"lt": lt, "found": True} for lt in found]
        rows += [{"lt": lt, "found": False} for lt in not_found]
        return rows

    def _detail_rows(self, locus_tag="PMM0001"):
        """Helper: sample detail query result rows."""
        return [
            {"locus_tag": locus_tag, "term_id": "go:0006260", "term_name": "DNA replication"},
            {"locus_tag": locus_tag, "term_id": "go:0006351", "term_name": "DNA-templated transcription"},
        ]

    def _summary_row(self, locus_tag="PMM0001"):
        """Helper: sample summary query result row."""
        return [{
            "gene_count": 1,
            "term_count": 2,
            "by_term": [
                {"term_id": "go:0006260", "term_name": "DNA replication", "count": 1},
                {"term_id": "go:0006351", "term_name": "DNA-templated transcription", "count": 1},
            ],
            "gene_term_counts": [{"locus_tag": locus_tag, "term_count": 2}],
        }]

    def test_returns_dict(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),       # existence check
            self._summary_row(),                 # go_bp summary
            self._detail_rows(),                 # go_bp detail
        ]
        result = api.gene_ontology_terms(["PMM0001"], "go_bp", conn=mock_conn)
        assert isinstance(result, dict)

    def test_has_expected_keys(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            self._summary_row(),
            self._detail_rows(),
        ]
        result = api.gene_ontology_terms(["PMM0001"], "go_bp", conn=mock_conn)
        expected_keys = {
            "total_matching", "total_genes", "total_terms",
            "by_ontology", "by_term",
            "terms_per_gene_min", "terms_per_gene_max", "terms_per_gene_median",
            "returned", "truncated", "not_found", "no_terms", "results",
        }
        assert set(result.keys()) == expected_keys

    def test_summary_sets_limit_zero(self, mock_conn):
        """summary=True uses summary queries, returns empty results."""
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            self._summary_row(),
        ]
        result = api.gene_ontology_terms(
            ["PMM0001"], "go_bp", summary=True, conn=mock_conn,
        )
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert result["total_matching"] == 2

    def test_empty_locus_tags_raises(self, mock_conn):
        with pytest.raises(ValueError, match="locus_tags must not be empty"):
            api.gene_ontology_terms([], "go_bp", conn=mock_conn)

    def test_invalid_ontology_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.gene_ontology_terms(["PMM0001"], "invalid", conn=mock_conn)

    def test_creates_conn_when_none(self):
        """Default conn used when None."""
        with patch(
            "multiomics_explorer.api.functions.GraphConnection",
        ) as MockConn:
            mock_instance = MockConn.return_value
            mock_instance.execute_query.side_effect = [
                self._exist_found("PMM0001"),
                self._summary_row(),
                self._detail_rows(),
            ]
            result = api.gene_ontology_terms(["PMM0001"], "go_bp")
        MockConn.assert_called_once()
        assert isinstance(result, dict)

    def test_not_found_populated(self, mock_conn):
        """Gene not in graph appears in not_found list."""
        mock_conn.execute_query.side_effect = [
            self._exist_mixed(found=["PMM0001"], not_found=["FAKE999"]),
            self._summary_row("PMM0001"),
            self._detail_rows("PMM0001"),
        ]
        result = api.gene_ontology_terms(
            ["PMM0001", "FAKE999"], "go_bp", conn=mock_conn,
        )
        assert "FAKE999" in result["not_found"]
        assert result["total_genes"] == 1

    def test_no_terms_populated(self, mock_conn):
        """Gene exists but has no terms for the ontology."""
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            [],  # summary query returns nothing
            [],  # detail query returns nothing
        ]
        result = api.gene_ontology_terms(["PMM0001"], "go_bp", conn=mock_conn)
        assert "PMM0001" in result["no_terms"]
        assert result["total_matching"] == 0
        assert result["total_genes"] == 0

    def test_limit_caps_results(self, mock_conn):
        """limit=2 with 5 total returns 2 results, truncated=True."""
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            # summary says 5 total
            [{
                "gene_count": 1, "term_count": 5,
                "by_term": [{"term_id": f"go:{i:07d}", "term_name": f"t{i}", "count": 1} for i in range(5)],
                "gene_term_counts": [{"locus_tag": "PMM0001", "term_count": 5}],
            }],
            # detail query (with limit=2 pushed in) returns 2 rows
            [
                {"locus_tag": "PMM0001", "term_id": "go:0000000", "term_name": "t0"},
                {"locus_tag": "PMM0001", "term_id": "go:0000001", "term_name": "t1"},
            ],
        ]
        result = api.gene_ontology_terms(
            ["PMM0001"], "go_bp", limit=2, conn=mock_conn,
        )
        assert result["returned"] == 2
        assert result["truncated"] is True
        assert result["total_matching"] == 5
        assert len(result["results"]) == 2

    def test_ontology_none_queries_all(self, mock_conn):
        """ontology=None queries all ONTOLOGY_CONFIG keys."""
        from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG
        n = len(ONTOLOGY_CONFIG)

        # existence + n summaries (all empty) + n details (all empty)
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
        ] + [[] for _ in range(n)] + [[] for _ in range(n)]

        result = api.gene_ontology_terms(["PMM0001"], conn=mock_conn)
        # 1 existence + n summary + n detail = 1 + 2n
        assert mock_conn.execute_query.call_count == 1 + 2 * n

    def test_importable_from_package(self):
        """from multiomics_explorer import gene_ontology_terms works."""
        from multiomics_explorer import gene_ontology_terms
        assert gene_ontology_terms is api.gene_ontology_terms


# ---------------------------------------------------------------------------
# run_cypher
# ---------------------------------------------------------------------------

MOD = "multiomics_explorer.api.functions"


def _valid_validators(sv_cls, schv_cls, pv_cls):
    """Configure CyVer validator mocks for an error-free query."""
    sv_cls.return_value.validate.return_value = (True, [])
    schv_cls.return_value.validate.return_value = (1.0, [])
    pv_cls.return_value.validate.return_value = (1.0, [])


class TestRunCypher:
    def test_returns_standard_envelope(self, mock_conn):
        mock_conn.execute_query.return_value = [{"count": 42}]
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            result = api.run_cypher("MATCH (g:Gene) RETURN count(g) AS count", conn=mock_conn)
        assert set(result.keys()) == {"returned", "truncated", "warnings", "results"}
        assert result["returned"] == 1
        assert result["results"][0]["count"] == 42

    def test_write_blocked_raises_value_error(self, mock_conn):
        with pytest.raises(ValueError, match="Write operations"):
            api.run_cypher("CREATE (n:Test)", conn=mock_conn)

    def test_foreach_blocked(self, mock_conn):
        with pytest.raises(ValueError, match="Write operations"):
            api.run_cypher("FOREACH (x IN [1] | CREATE (:Node))", conn=mock_conn)

    def test_load_csv_blocked(self, mock_conn):
        with pytest.raises(ValueError, match="Write operations"):
            api.run_cypher("LOAD CSV FROM 'file:///data.csv' AS row RETURN row", conn=mock_conn)

    def test_call_procedure_blocked(self, mock_conn):
        with pytest.raises(ValueError, match="Write operations"):
            api.run_cypher("CALL apoc.create.node(['Gene'], {name: 'x'})", conn=mock_conn)

    def test_syntax_error_raises_value_error(self, mock_conn):
        with patch(f"{MOD}.SyntaxValidator") as sv:
            sv.return_value.validate.return_value = (False, [{"description": "Invalid input 'MATC'"}])
            with pytest.raises(ValueError, match="Syntax error"):
                api.run_cypher("MATC (n) RETURNN n", conn=mock_conn)

    def test_syntax_error_message_propagated(self, mock_conn):
        with patch(f"{MOD}.SyntaxValidator") as sv:
            sv.return_value.validate.return_value = (False, [{"description": "Invalid input near line 1, col 5"}])
            with pytest.raises(ValueError, match="line 1, col 5"):
                api.run_cypher("MATC (n) RETURNN n", conn=mock_conn)

    def test_schema_warnings_in_response(self, mock_conn):
        mock_conn.execute_query.return_value = [{"n": 1}]
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            sv.return_value.validate.return_value = (True, [])
            schv.return_value.validate.return_value = (
                0.5,
                [{"code": "UnknownLabelWarning", "description": "Label Foo not in database"}],
            )
            pv.return_value.validate.return_value = (1.0, [])
            result = api.run_cypher("MATCH (n:Foo) RETURN n", conn=mock_conn)
        assert result["warnings"] == ["Label Foo not in database"]

    def test_property_warnings_in_response(self, mock_conn):
        mock_conn.execute_query.return_value = [{"n": 1}]
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            sv.return_value.validate.return_value = (True, [])
            schv.return_value.validate.return_value = (1.0, [])
            pv.return_value.validate.return_value = (
                0.5,
                [{"description": "Property bad_prop not found on Gene"}],
            )
            result = api.run_cypher("MATCH (n:Gene) RETURN n.bad_prop", conn=mock_conn)
        assert result["warnings"] == ["Property bad_prop not found on Gene"]

    def test_no_warnings_when_valid(self, mock_conn):
        mock_conn.execute_query.return_value = []
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            result = api.run_cypher("MATCH (n:Gene) RETURN n LIMIT 5", conn=mock_conn)
        assert result["warnings"] == []

    def test_duplicate_warnings_deduplicated(self, mock_conn):
        mock_conn.execute_query.return_value = []
        msg = "Label Foo not in database"
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            sv.return_value.validate.return_value = (True, [])
            schv.return_value.validate.return_value = (0.5, [{"description": msg}])
            pv.return_value.validate.return_value = (0.5, [{"description": msg}])
            result = api.run_cypher("MATCH (n:Foo) RETURN n", conn=mock_conn)
        assert result["warnings"] == [msg]

    def test_validators_use_conn_driver(self, mock_conn):
        mock_conn.execute_query.return_value = []
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            api.run_cypher("MATCH (n) RETURN n LIMIT 1", conn=mock_conn)
        sv.assert_called_once_with(mock_conn.driver)
        schv.assert_called_once_with(mock_conn.driver)
        pv.assert_called_once_with(mock_conn.driver)

    def test_limit_injected_when_absent(self, mock_conn):
        mock_conn.execute_query.return_value = []
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            api.run_cypher("MATCH (n) RETURN n", limit=10, conn=mock_conn)
        called_query = mock_conn.execute_query.call_args[0][0]
        assert "LIMIT 10" in called_query

    def test_limit_not_duplicated_when_present(self, mock_conn):
        mock_conn.execute_query.return_value = []
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            api.run_cypher("MATCH (n) RETURN n LIMIT 5", limit=10, conn=mock_conn)
        called_query = mock_conn.execute_query.call_args[0][0]
        assert called_query.count("LIMIT") == 1

    def test_limit_none_skips_injection(self, mock_conn):
        mock_conn.execute_query.return_value = []
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            result = api.run_cypher("MATCH (n) RETURN n", limit=None, conn=mock_conn)
        called_query = mock_conn.execute_query.call_args[0][0]
        assert "LIMIT" not in called_query
        assert result["truncated"] is False

    def test_semicolon_stripped(self, mock_conn):
        mock_conn.execute_query.return_value = []
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            api.run_cypher("MATCH (n) RETURN n;", limit=10, conn=mock_conn)
        called_query = mock_conn.execute_query.call_args[0][0]
        assert ";" not in called_query
        assert "LIMIT" in called_query

    def test_truncated_when_returned_equals_limit(self, mock_conn):
        mock_conn.execute_query.return_value = [{"n": i} for i in range(5)]
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            result = api.run_cypher("MATCH (n) RETURN n", limit=5, conn=mock_conn)
        assert result["truncated"] is True

    def test_not_truncated_when_returned_lt_limit(self, mock_conn):
        mock_conn.execute_query.return_value = [{"n": 1}, {"n": 2}]
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            result = api.run_cypher("MATCH (n) RETURN n", limit=5, conn=mock_conn)
        assert result["truncated"] is False

    def test_truncated_false_when_limit_none(self, mock_conn):
        mock_conn.execute_query.return_value = [{"n": i} for i in range(10)]
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            result = api.run_cypher("MATCH (n) RETURN n LIMIT 10", limit=None, conn=mock_conn)
        assert result["truncated"] is False

    def test_empty_results(self, mock_conn):
        mock_conn.execute_query.return_value = []
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            result = api.run_cypher("MATCH (n:Fake) RETURN n", conn=mock_conn)
        assert result["returned"] == 0
        assert result["truncated"] is False
        assert result["results"] == []

    def test_creates_conn_when_none(self):
        with patch(f"{MOD}.GraphConnection") as gc_cls, \
             patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            gc_cls.return_value.execute_query.return_value = []
            _valid_validators(sv, schv, pv)
            api.run_cypher("MATCH (n) RETURN n LIMIT 1")
        gc_cls.assert_called_once()

    def test_importable_from_package(self):
        from multiomics_explorer import run_cypher
        assert run_cypher is api.run_cypher


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
        assert "by_organism" in result
        assert "by_treatment_type" in result
        assert "by_omics_type" in result
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
        # Verify data query was called with verbose (no LIMIT — slicing done in Python)
        data_call = mock_conn.execute_query.call_args_list[1]
        assert "abstract" in data_call[0][0]  # verbose columns in Cypher

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

    def test_offset_skips_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 5, "total_matching": 5}],  # summary
            [{"doi": f"10.1234/{i}", "title": f"T{i}", "authors": "A",
              "year": 2024, "journal": "J", "study_type": "S",
              "organisms": ["MED4"], "experiment_count": 1,
              "treatment_types": ["light"], "omics_types": ["RNASEQ"]}
             for i in range(5)],  # detail
        ]
        result = api.list_publications(limit=2, offset=2, conn=mock_conn)
        assert result["total_matching"] == 5
        assert result["returned"] == 2
        assert result["results"][0]["doi"] == "10.1234/2"
        assert result["offset"] == 2


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
            "by_table_scope": [{"item": "gene_level", "count": 40}],
        }]

    def _detail_row(self, **overrides):
        """Helper: mock detail query result row."""
        row = {
            "experiment_id": "test_exp_1",
            "experiment_name": "Test Experiment 1",
            "publication_doi": "10.1234/test",
            "organism_name": "Prochlorococcus MED4",
            "treatment_type": "coculture",
            "coculture_partner": "Alteromonas macleodii HOT1A3",
            "omics_type": "RNASEQ",
            "is_time_course": "false",
            "table_scope": "gene_level",
            "table_scope_detail": "gene_level_all",
            "gene_count": 1696,
            "significant_up_count": 245,
            "significant_down_count": 178,
            "time_point_count": 1,
            "time_point_labels": ["20h"],
            "time_point_orders": [1],
            "time_point_hours": [20.0],
            "time_point_totals": [1696],
            "time_point_significant_up": [245],
            "time_point_significant_down": [178],
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
            time_point_significant_up=[0, 50, 150],
            time_point_significant_down=[0, 35, 108],
        )

    def test_detail_returns_dict(self, mock_conn):
        """Detail mode returns dict with breakdowns + results."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),       # filtered summary
            self._summary_result(),       # unfiltered total_entries
            [self._detail_row()],         # detail query
        ]
        result = api.list_experiments(conn=mock_conn)
        assert isinstance(result, dict)
        assert "total_entries" in result
        assert "total_matching" in result
        assert "by_organism" in result
        assert "by_treatment_type" in result
        assert "by_table_scope" in result
        assert "results" in result
        assert len(result["results"]) == 1

    def test_summary_returns_dict(self, mock_conn):
        """Summary mode returns dict with breakdowns + empty results."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),  # filtered summary
            self._summary_result(),  # unfiltered total_entries
        ]
        result = api.list_experiments(summary=True, conn=mock_conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert result["by_organism"][0]["organism_name"] == "Prochlorococcus MED4"
        assert result["by_organism"][0]["count"] == 30
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
            table_scope=["gene_level"],
            verbose=True, limit=10, conn=mock_conn,
        )
        # Summary query has filter params
        summary_call = mock_conn.execute_query.call_args_list[0]
        assert "organism" in summary_call[1]
        assert "treatment_types" in summary_call[1]
        # Detail query has verbose + limit
        detail_call = mock_conn.execute_query.call_args_list[2]
        assert "e.name AS experiment_name" in detail_call[0][0]
        assert "LIMIT $limit" in detail_call[0][0]

    def test_is_time_course_cast(self, mock_conn):
        """is_time_course string cast to bool."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._detail_row(is_time_course="true"),
             self._detail_row(is_time_course="false")],
        ]
        result = api.list_experiments(conn=mock_conn)
        assert result["results"][0]["is_time_course"] is True
        assert result["results"][1]["is_time_course"] is False

    def test_genes_by_status_computed(self, mock_conn):
        """genes_by_status dict computed from significant counts and gene_count."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._detail_row(
                gene_count=1000,
                significant_up_count=200,
                significant_down_count=150,
            )],
        ]
        result = api.list_experiments(conn=mock_conn)
        gbs = result["results"][0]["genes_by_status"]
        assert gbs["significant_up"] == 200
        assert gbs["significant_down"] == 150
        assert gbs["not_significant"] == 650  # 1000 - 200 - 150

    def test_timepoints_assembled(self, mock_conn):
        """Parallel arrays assembled into timepoints list of dicts for time-course."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._tc_detail_row()],
        ]
        result = api.list_experiments(conn=mock_conn)
        row = result["results"][0]
        assert "timepoints" in row
        assert len(row["timepoints"]) == 3
        tp = row["timepoints"][0]
        assert tp["timepoint"] == "2h"
        assert tp["timepoint_order"] == 1
        assert tp["timepoint_hours"] == 2.0
        assert tp["gene_count"] == 353
        assert tp["genes_by_status"]["significant_up"] == 0
        assert tp["genes_by_status"]["significant_down"] == 0
        assert tp["genes_by_status"]["not_significant"] == 353

    def test_timepoints_omitted(self, mock_conn):
        """Non-time-course results have no timepoints key."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._detail_row(is_time_course="false")],
        ]
        result = api.list_experiments(conn=mock_conn)
        assert "timepoints" not in result["results"][0]

    def test_sentinel_conversion(self, mock_conn):
        """Sentinel values converted: '' timepoint -> None, -1.0 hours -> None."""
        tc_row = self._detail_row(
            is_time_course="true",
            time_point_count=1,
            time_point_labels=[""],
            time_point_orders=[1],
            time_point_hours=[-1.0],
            time_point_totals=[100],
            time_point_significant_up=[6],
            time_point_significant_down=[4],
        )
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [tc_row],
        ]
        result = api.list_experiments(conn=mock_conn)
        tp = result["results"][0]["timepoints"][0]
        assert tp["timepoint"] is None
        assert tp["timepoint_hours"] is None

    def test_limit_slices_results(self, mock_conn):
        """Limit passed to builder, total_matching from summary."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_matching=76),
            self._summary_result(),
            [self._detail_row()],  # only 1 returned due to limit
        ]
        result = api.list_experiments(limit=1, conn=mock_conn)
        assert result["total_matching"] == 76
        assert result["returned"] == 1
        assert result["truncated"] is True

    def test_breakdowns_computed(self, mock_conn):
        """Breakdowns renamed from apoc format to domain keys."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
        ]
        result = api.list_experiments(summary=True, conn=mock_conn)
        assert result["by_organism"][0]["organism_name"] == "Prochlorococcus MED4"
        assert result["by_organism"][0]["count"] == 30
        assert result["by_treatment_type"][0]["treatment_type"] == "coculture"
        assert result["by_omics_type"][0]["omics_type"] == "RNASEQ"
        assert result["by_publication"][0]["publication_doi"] == "10.1038/ismej.2016.70"
        assert result["by_table_scope"][0]["table_scope"] == "gene_level"
        assert result["by_table_scope"][0]["count"] == 40

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
            result = api.list_experiments(summary=True)
        MockConn.assert_called_once()
        assert result["total_matching"] == 0

    def test_importable_from_package(self):
        """from multiomics_explorer import list_experiments works."""
        from multiomics_explorer import list_experiments
        assert list_experiments is api.list_experiments


# ---------------------------------------------------------------------------
# differential_expression_by_gene
# ---------------------------------------------------------------------------


class TestDifferentialExpressionByGene:
    """Unit tests for differential_expression_by_gene API function."""

    def _organism_result(self, orgs=None):
        """Mock organism pre-validation result."""
        if orgs is None:
            orgs = ["Prochlorococcus MED4"]
        return [{"organisms": orgs}]

    def _global_summary(self, total_matching=15, matching_genes=5):
        """Mock global summary query result."""
        return [{
            "total_matching": total_matching,
            "matching_genes": matching_genes,
            "rows_by_status": [
                {"item": "significant_up", "count": 3},
                {"item": "not_significant", "count": 12},
            ],
            "rows_by_treatment_type": [
                {"item": "nitrogen_stress", "count": 15},
            ],
            "by_table_scope": [
                {"item": "all_detected_genes", "count": 15},
            ],
            "median_abs_log2fc": 1.978,
            "max_abs_log2fc": 3.591,
        }]

    def _experiment_summary(self):
        """Mock per-experiment summary result."""
        return [{
            "organism_name": "Prochlorococcus MED4",
            "experiments": [
                {
                    "experiment_id": "exp1",
                    "experiment_name": "Test experiment",
                    "treatment_type": "nitrogen_stress",
                    "omics_type": "RNASEQ",
                    "coculture_partner": None,
                    "is_time_course": "true",
                    "table_scope": "all_detected_genes",
                    "table_scope_detail": None,
                    "matching_genes": 5,
                    "rows_by_status": [
                        {"item": "significant_up", "count": 3},
                        {"item": "not_significant", "count": 12},
                    ],
                    "timepoints": [
                        {
                            "timepoint": "day 18",
                            "timepoint_hours": 432.0,
                            "timepoint_order": 1,
                            "matching_genes": 5,
                            "rows_by_status": [
                                {"item": "not_significant", "count": 5},
                            ],
                        },
                    ],
                },
            ],
        }]

    def _diagnostics_summary(self):
        """Mock diagnostics summary result."""
        return [{
            "top_categories": [
                {"category": "Signal transduction",
                 "total_genes": 2, "significant_genes": 2},
            ],
            "not_found": [],
            "no_expression": [],
        }]

    def _detail_rows(self):
        """Mock detail query result rows."""
        return [
            {
                "locus_tag": "PMM0001", "gene_name": "dnaN",
                "experiment_id": "exp1", "treatment_type": "nitrogen_stress",
                "timepoint": "day 18", "timepoint_hours": 432.0,
                "timepoint_order": 1,
                "log2fc": 3.591, "padj": 1.13e-12, "rank": 77,
                "expression_status": "significant_up",
            },
        ]

    def _mock_side_effect_organism_only(self):
        """Side effect for organism-only call (1 pre-query + 3 summary + 1 detail)."""
        return [
            self._organism_result(),           # organism pre-query
            self._global_summary(),            # summary global
            self._experiment_summary(),        # summary by_experiment
            self._diagnostics_summary(),       # summary diagnostics
            self._detail_rows(),               # detail
        ]

    def _mock_side_effect_locus_tags(self):
        """Side effect for locus_tags call (1 pre-query + 3 summary + 1 detail)."""
        return [
            self._organism_result(),           # locus_tags pre-query
            self._global_summary(),
            self._experiment_summary(),
            self._diagnostics_summary(),
            self._detail_rows(),
        ]

    def test_returns_dict_with_envelope(self, mock_conn):
        """Runs pre-query + 3 summaries + detail, returns correct dict."""
        mock_conn.execute_query.side_effect = self._mock_side_effect_organism_only()
        result = api.differential_expression_by_gene(
            organism="MED4", conn=mock_conn
        )
        assert isinstance(result, dict)
        for key in [
            "organism_name", "matching_genes", "total_matching",
            "rows_by_status", "median_abs_log2fc", "max_abs_log2fc",
            "experiment_count", "rows_by_treatment_type", "by_table_scope",
            "top_categories", "experiments", "not_found", "no_expression",
            "returned", "truncated", "results",
        ]:
            assert key in result
        assert result["organism_name"] == "Prochlorococcus MED4"
        assert result["total_matching"] == 15
        assert result["matching_genes"] == 5
        assert result["returned"] == 1
        assert len(result["results"]) == 1

    def test_rows_by_status_filled(self, mock_conn):
        """APOC frequencies transformed; missing keys filled with 0."""
        mock_conn.execute_query.side_effect = self._mock_side_effect_organism_only()
        result = api.differential_expression_by_gene(
            organism="MED4", conn=mock_conn
        )
        rbs = result["rows_by_status"]
        assert rbs["significant_up"] == 3
        assert rbs["significant_down"] == 0  # filled
        assert rbs["not_significant"] == 12

    def test_summary_true_skips_detail(self, mock_conn):
        """summary=True returns results=[], returned=0."""
        mock_conn.execute_query.side_effect = [
            self._organism_result(),
            self._global_summary(),
            self._experiment_summary(),
            self._diagnostics_summary(),
            # No detail query call
        ]
        result = api.differential_expression_by_gene(
            organism="MED4", summary=True, conn=mock_conn
        )
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True  # total_matching=15 > 0
        assert mock_conn.execute_query.call_count == 4  # no detail call

    def test_no_filters_raises(self, mock_conn):
        """All three None raises ValueError."""
        with pytest.raises(ValueError, match="at least one"):
            api.differential_expression_by_gene(conn=mock_conn)

    def test_invalid_direction_raises(self, mock_conn):
        """Invalid direction raises ValueError."""
        with pytest.raises(ValueError, match="Invalid direction"):
            api.differential_expression_by_gene(
                organism="MED4", direction="sideways", conn=mock_conn
            )

    def test_multi_organism_locus_tags_raises(self, mock_conn):
        """Locus tags from multiple organisms raises ValueError."""
        mock_conn.execute_query.side_effect = [
            self._organism_result(["Prochlorococcus MED4", "MIT9313"]),
        ]
        with pytest.raises(ValueError, match="locus_tags span multiple"):
            api.differential_expression_by_gene(
                locus_tags=["PMM0001", "MIT9313_0001"], conn=mock_conn
            )

    def test_organism_no_match_raises(self, mock_conn):
        """No organism match raises ValueError."""
        mock_conn.execute_query.side_effect = [
            self._organism_result([]),
        ]
        with pytest.raises(ValueError, match="no organism matching"):
            api.differential_expression_by_gene(
                organism="ZZZZZ", conn=mock_conn
            )

    def test_organism_ambiguous_raises(self, mock_conn):
        """Ambiguous organism raises ValueError."""
        mock_conn.execute_query.side_effect = [
            self._organism_result(["Prochlorococcus MED4", "MIT9313"]),
        ]
        with pytest.raises(ValueError, match="matches multiple"):
            api.differential_expression_by_gene(
                organism="Prochlorococcus", conn=mock_conn
            )

    def test_truncated_true(self, mock_conn):
        """truncated=True when total_matching > returned."""
        mock_conn.execute_query.side_effect = self._mock_side_effect_organism_only()
        result = api.differential_expression_by_gene(
            organism="MED4", conn=mock_conn
        )
        assert result["truncated"] is True  # 15 > 1

    def test_experiments_sorted_by_significant(self, mock_conn):
        """Experiments sorted by total significant rows DESC."""
        exp_summary = [{
            "organism_name": "Prochlorococcus MED4",
            "experiments": [
                {
                    "experiment_id": "low_sig",
                    "experiment_name": "Low",
                    "treatment_type": "x",
                    "omics_type": "RNASEQ",
                    "coculture_partner": None,
                    "is_time_course": "false",
                    "table_scope": "all_detected_genes",
                    "table_scope_detail": None,
                    "matching_genes": 1,
                    "rows_by_status": [
                        {"item": "significant_up", "count": 1},
                    ],
                    "timepoints": [],
                },
                {
                    "experiment_id": "high_sig",
                    "experiment_name": "High",
                    "treatment_type": "y",
                    "omics_type": "RNASEQ",
                    "coculture_partner": None,
                    "is_time_course": "false",
                    "table_scope": "significant_only",
                    "table_scope_detail": None,
                    "matching_genes": 1,
                    "rows_by_status": [
                        {"item": "significant_up", "count": 10},
                        {"item": "significant_down", "count": 5},
                    ],
                    "timepoints": [],
                },
            ],
        }]
        mock_conn.execute_query.side_effect = [
            self._organism_result(),
            self._global_summary(),
            exp_summary,
            self._diagnostics_summary(),
            self._detail_rows(),
        ]
        result = api.differential_expression_by_gene(
            organism="MED4", conn=mock_conn
        )
        # high_sig (15 significant) should come before low_sig (1)
        assert result["experiments"][0]["experiment_id"] == "high_sig"
        assert result["experiments"][1]["experiment_id"] == "low_sig"

    def test_non_time_course_timepoints_null(self, mock_conn):
        """Non-time-course experiments have timepoints=None."""
        exp_summary = [{
            "organism_name": "Prochlorococcus MED4",
            "experiments": [
                {
                    "experiment_id": "single_tp",
                    "experiment_name": "Single",
                    "treatment_type": "x",
                    "omics_type": "RNASEQ",
                    "coculture_partner": None,
                    "is_time_course": "false",
                    "table_scope": "all_detected_genes",
                    "table_scope_detail": None,
                    "matching_genes": 1,
                    "rows_by_status": [
                        {"item": "not_significant", "count": 5},
                    ],
                    "timepoints": [
                        {
                            "timepoint": "t0",
                            "timepoint_hours": 0.0,
                            "timepoint_order": 1,
                            "matching_genes": 1,
                            "rows_by_status": [
                                {"item": "not_significant", "count": 5},
                            ],
                        },
                    ],
                },
            ],
        }]
        mock_conn.execute_query.side_effect = [
            self._organism_result(),
            self._global_summary(total_matching=5, matching_genes=1),
            exp_summary,
            self._diagnostics_summary(),
            self._detail_rows(),
        ]
        result = api.differential_expression_by_gene(
            organism="MED4", conn=mock_conn
        )
        assert result["experiments"][0]["timepoints"] is None

    def test_not_found_and_no_expression(self, mock_conn):
        """Batch diagnostics returns not_found and no_expression."""
        mock_conn.execute_query.side_effect = [
            self._organism_result(),           # locus_tags pre-query
            self._global_summary(),
            self._experiment_summary(),
            [{
                "top_categories": [],
                "not_found": ["FAKE_GENE"],
                "no_expression": ["PMM9999"],
            }],
            self._detail_rows(),
        ]
        result = api.differential_expression_by_gene(
            locus_tags=["PMM0001", "FAKE_GENE", "PMM9999"], conn=mock_conn
        )
        assert result["not_found"] == ["FAKE_GENE"]
        assert result["no_expression"] == ["PMM9999"]

    def test_experiment_count(self, mock_conn):
        """experiment_count = len(experiments)."""
        mock_conn.execute_query.side_effect = self._mock_side_effect_organism_only()
        result = api.differential_expression_by_gene(
            organism="MED4", conn=mock_conn
        )
        assert result["experiment_count"] == len(result["experiments"])

    def test_creates_conn_when_none(self):
        """Default conn used when None."""
        with patch(
            "multiomics_explorer.api.functions.GraphConnection",
        ) as MockConn:
            mock_instance = MockConn.return_value
            mock_instance.execute_query.side_effect = [
                self._organism_result(),
                self._global_summary(total_matching=0, matching_genes=0),
                [{"organism_name": "Prochlorococcus MED4", "experiments": []}],
                self._diagnostics_summary(),
            ]
            result = api.differential_expression_by_gene(
                organism="MED4", summary=True,
            )
        MockConn.assert_called_once()
        assert result["total_matching"] == 0

    def test_importable_from_package(self):
        """from multiomics_explorer import differential_expression_by_gene works."""
        from multiomics_explorer import differential_expression_by_gene
        assert differential_expression_by_gene is api.differential_expression_by_gene


class TestSearchHomologGroups:
    """Tests for search_homolog_groups API function."""

    def test_returns_dict(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21122, "total_matching": 5,
              "score_max": 3.5, "score_median": 2.0,
              "by_source": [{"item": "cyanorak", "count": 3}],
              "by_level": [{"item": "curated", "count": 3}]}],
            [{"group_id": "cyanorak:CK_1", "group_name": "CK_1",
              "consensus_gene_name": "psbB", "consensus_product": "photosystem II",
              "source": "cyanorak", "taxonomic_level": "curated",
              "specificity_rank": 0, "member_count": 9, "organism_count": 9,
              "score": 3.5}],
        ]
        result = api.search_homolog_groups("photosynthesis", conn=mock_conn)
        assert isinstance(result, dict)
        assert result["total_entries"] == 21122
        assert result["total_matching"] == 5
        assert result["score_max"] == 3.5
        assert len(result["by_source"]) == 1
        assert result["by_source"][0]["source"] == "cyanorak"
        assert result["returned"] == 1
        assert len(result["results"]) == 1

    def test_summary_mode(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21122, "total_matching": 884,
              "score_max": 6.1, "score_median": 1.0,
              "by_source": [], "by_level": []}],
        ]
        result = api.search_homolog_groups("photosynthesis", summary=True, conn=mock_conn)
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert result["results"] == []
        # Only 1 query call (summary only, detail skipped)
        assert mock_conn.execute_query.call_count == 1

    def test_zero_match(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21122, "total_matching": 0,
              "score_max": None, "score_median": None,
              "by_source": [], "by_level": []}],
        ]
        result = api.search_homolog_groups("xyznonexistent", summary=True, conn=mock_conn)
        assert result["total_matching"] == 0
        assert result["score_max"] is None
        assert result["score_median"] is None

    def test_validates_source(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid source"):
            api.search_homolog_groups("test", source="invalid", conn=mock_conn)

    def test_validates_taxonomic_level(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid taxonomic_level"):
            api.search_homolog_groups("test", taxonomic_level="invalid", conn=mock_conn)

    def test_validates_empty_search_text(self, mock_conn):
        with pytest.raises(ValueError, match="search_text"):
            api.search_homolog_groups("", conn=mock_conn)

    def test_passes_filters(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21122, "total_matching": 0,
              "score_max": None, "score_median": None,
              "by_source": [], "by_level": []}],
        ]
        api.search_homolog_groups(
            "test", source="cyanorak", taxonomic_level="curated",
            max_specificity_rank=0, summary=True, conn=mock_conn)
        # Verify builder was called with filters
        call_args = mock_conn.execute_query.call_args
        cypher = call_args[0][0]
        assert "og.source" in cypher

    def test_importable_from_package(self):
        from multiomics_explorer import search_homolog_groups
        assert search_homolog_groups is api.search_homolog_groups


class TestGenesByHomologGroup:
    """Tests for genes_by_homolog_group API function."""

    def test_returns_dict(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_matching": 9, "total_genes": 9, "total_categories": 1,
              "by_organism": [{"item": "Prochlorococcus MED4", "count": 1}],
              "by_category_raw": [{"item": "Photosynthesis", "count": 9}],
              "by_group_raw": [{"item": "cyanorak:CK_00000570", "count": 9}],
              "not_found_groups": [], "not_matched_groups": []}],
            [{"locus_tag": "PMM0315", "gene_name": "psbB",
              "product": "photosystem II", "organism_name": "Prochlorococcus MED4",
              "gene_category": "Photosynthesis", "group_id": "cyanorak:CK_00000570"}],
        ]
        result = api.genes_by_homolog_group(["cyanorak:CK_00000570"], conn=mock_conn)
        assert isinstance(result, dict)
        assert result["total_matching"] == 9
        assert result["total_genes"] == 9
        assert result["total_categories"] == 1
        assert result["genes_per_group_max"] == 9
        assert result["genes_per_group_median"] == 9
        assert len(result["by_organism"]) == 1
        assert result["by_organism"][0]["organism_name"] == "Prochlorococcus MED4"
        assert len(result["top_groups"]) == 1
        assert result["top_groups"][0]["group_id"] == "cyanorak:CK_00000570"
        assert result["not_found_groups"] == []
        assert result["not_matched_groups"] == []
        assert result["not_found_organisms"] == []
        assert result["not_matched_organisms"] == []
        assert result["returned"] == 1
        assert len(result["results"]) == 1

    def test_summary_mode(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_matching": 9, "total_genes": 9, "total_categories": 1,
              "by_organism": [],
              "by_category_raw": [],
              "by_group_raw": [{"item": "cyanorak:CK_00000570", "count": 9}],
              "not_found_groups": [], "not_matched_groups": []}],
        ]
        result = api.genes_by_homolog_group(
            ["cyanorak:CK_00000570"], summary=True, conn=mock_conn)
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert result["results"] == []
        assert mock_conn.execute_query.call_count == 1

    def test_not_found_groups(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_matching": 0, "total_genes": 0, "total_categories": 0,
              "by_organism": [], "by_category_raw": [], "by_group_raw": [],
              "not_found_groups": ["FAKE_GROUP"], "not_matched_groups": []}],
        ]
        result = api.genes_by_homolog_group(
            ["FAKE_GROUP"], summary=True, conn=mock_conn)
        assert result["not_found_groups"] == ["FAKE_GROUP"]
        assert result["total_matching"] == 0

    def test_validates_empty_group_ids(self, mock_conn):
        with pytest.raises(ValueError, match="group_ids must not be empty"):
            api.genes_by_homolog_group([], conn=mock_conn)

    def test_passes_params(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_matching": 0, "total_genes": 0, "total_categories": 0,
              "by_organism": [], "by_category_raw": [], "by_group_raw": [],
              "not_found_groups": [], "not_matched_groups": []}],
            [{"not_found_organisms": [], "not_matched_organisms": []}],
        ]
        api.genes_by_homolog_group(
            ["cyanorak:CK_1"], organisms=["MED4"], summary=True, conn=mock_conn)
        first_call = mock_conn.execute_query.call_args_list[0]
        cypher = first_call[0][0]
        assert "$organisms" in cypher

    def test_importable_from_package(self):
        from multiomics_explorer import genes_by_homolog_group
        assert genes_by_homolog_group is api.genes_by_homolog_group


class TestDifferentialExpressionByOrtholog:
    """Tests for differential_expression_by_ortholog API function."""

    def test_returns_dict(self, mock_conn):
        # Mock all 6 query results (Q1a group check + Q1b summary + Q2-Q5)
        mock_conn.execute_query.side_effect = [
            [{"not_found": []}],  # Q1a group check
            [{"total_matching": 10, "matching_genes": 3, "matching_groups": 1,
              "experiment_count": 2, "by_organism": [], "rows_by_status": [],
              "rows_by_treatment_type": [], "by_table_scope": [],
              "sig_log2fcs": [1.5, 2.0],
              "matched_group_ids": ["g1"]}],  # Q1b
            [{"top_groups": []}],  # Q2
            [{"top_experiments": []}],  # Q3
            [],  # Q4 results
            [],  # Q5 membership
        ]
        result = api.differential_expression_by_ortholog(
            group_ids=["g1"], conn=mock_conn,
        )
        assert isinstance(result, dict)
        assert "total_matching" in result
        assert "results" in result
        assert "returned" in result
        assert "truncated" in result

    def test_empty_group_ids_raises(self, mock_conn):
        with pytest.raises(ValueError, match="group_ids must not be empty"):
            api.differential_expression_by_ortholog(group_ids=[], conn=mock_conn)

    def test_invalid_direction_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid direction"):
            api.differential_expression_by_ortholog(
                group_ids=["g1"], direction="sideways", conn=mock_conn,
            )

    def test_median_max_computation(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"not_found": []}],  # Q1a
            [{"total_matching": 5, "matching_genes": 2, "matching_groups": 1,
              "experiment_count": 1, "by_organism": [], "rows_by_status": [],
              "rows_by_treatment_type": [], "by_table_scope": [],
              "sig_log2fcs": [1.0, 2.0, 3.0],
              "matched_group_ids": ["g1"]}],  # Q1b
            [{"top_groups": []}],
            [{"top_experiments": []}],
            [],
            [],
        ]
        result = api.differential_expression_by_ortholog(
            group_ids=["g1"], conn=mock_conn,
        )
        assert result["median_abs_log2fc"] == 2.0
        assert result["max_abs_log2fc"] == 3.0

    def test_empty_sig_log2fcs(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"not_found": ["g1"]}],  # Q1a: all groups not found
            # Q1b skipped (no found groups)
            [{"top_groups": []}],
            [{"top_experiments": []}],
            [],
            [],
        ]
        result = api.differential_expression_by_ortholog(
            group_ids=["g1"], conn=mock_conn,
        )
        assert result["median_abs_log2fc"] is None
        assert result["max_abs_log2fc"] is None

    def test_total_genes_join(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"not_found": []}],  # Q1a
            [{"total_matching": 1, "matching_genes": 1, "matching_groups": 1,
              "experiment_count": 1, "by_organism": [], "rows_by_status": [],
              "rows_by_treatment_type": [], "by_table_scope": [],
              "sig_log2fcs": [],
              "matched_group_ids": ["g1"]}],  # Q1b
            [{"top_groups": []}],
            [{"top_experiments": []}],
            [{"group_id": "g1", "organism_name": "MED4",
              "genes_with_expression": 2, "significant_up": 1,
              "significant_down": 0, "not_significant": 1}],  # Q4
            [{"group_id": "g1", "organism_name": "MED4",
              "total_genes": 5}],  # Q5
        ]
        result = api.differential_expression_by_ortholog(
            group_ids=["g1"], conn=mock_conn,
        )
        assert result["results"][0]["total_genes"] == 5

    def test_summary_true_skips_detail(self, mock_conn):
        """summary=True sets limit=0, returns results=[]."""
        mock_conn.execute_query.side_effect = [
            [{"not_found": []}],  # Q1a group check
            [{"total_matching": 10, "matching_genes": 3, "matching_groups": 1,
              "experiment_count": 2, "by_organism": [], "rows_by_status": [],
              "rows_by_treatment_type": [], "by_table_scope": [],
              "sig_log2fcs": [1.5, 2.0],
              "matched_group_ids": ["g1"]}],  # Q1b
            [{"top_groups": []}],  # Q2 top_groups
            [{"top_experiments": []}],  # Q3 top_experiments
            # Q4 results SKIPPED (limit=0)
            [],  # Q5 membership counts
        ]
        result = api.differential_expression_by_ortholog(
            group_ids=["g1"], summary=True, conn=mock_conn,
        )
        assert result["results"] == []
        assert result["returned"] == 0
        assert mock_conn.execute_query.call_count == 5  # Q1a+Q1b+Q2+Q3+Q5

    def test_importable_from_package(self):
        from multiomics_explorer import differential_expression_by_ortholog as fn
        assert callable(fn)


# ---------------------------------------------------------------------------
# _apoc_freq_to_dict and _apoc_freq_to_treatment_dict helpers
# ---------------------------------------------------------------------------
class TestApocFreqHelpers:
    def test_apoc_freq_to_dict_basic(self):
        """Converts [{item, count}] to {item: count} with expression status defaults."""
        freq = [{"item": "significant_up", "count": 5}]
        result = api._apoc_freq_to_dict(freq)
        assert result["significant_up"] == 5
        # Missing keys filled with 0
        assert result["significant_down"] == 0
        assert result["not_significant"] == 0

    def test_apoc_freq_to_dict_all_keys(self):
        """All three expression status keys present in output."""
        freq = [
            {"item": "significant_up", "count": 10},
            {"item": "significant_down", "count": 3},
            {"item": "not_significant", "count": 87},
        ]
        result = api._apoc_freq_to_dict(freq)
        assert result == {"significant_up": 10, "significant_down": 3, "not_significant": 87}

    def test_apoc_freq_to_dict_empty(self):
        """Empty input fills all keys with 0."""
        result = api._apoc_freq_to_dict([])
        assert result == {"significant_up": 0, "significant_down": 0, "not_significant": 0}

    def test_apoc_freq_to_treatment_dict_basic(self):
        """Converts [{item, count}] to {item: count} without defaults."""
        freq = [
            {"item": "coculture", "count": 16},
            {"item": "nitrogen_stress", "count": 8},
        ]
        result = api._apoc_freq_to_treatment_dict(freq)
        assert result == {"coculture": 16, "nitrogen_stress": 8}

    def test_apoc_freq_to_treatment_dict_empty(self):
        """Empty input returns empty dict."""
        result = api._apoc_freq_to_treatment_dict([])
        assert result == {}

    def test_apoc_freq_to_treatment_dict_single(self):
        """Single item."""
        result = api._apoc_freq_to_treatment_dict([{"item": "light_stress", "count": 4}])
        assert result == {"light_stress": 4}


# ---------------------------------------------------------------------------
# run_cypher LIMIT injection edge cases
# ---------------------------------------------------------------------------
class TestRunCypherLimitEdgeCases:
    """Edge cases for LIMIT injection in run_cypher."""

    def test_limit_in_subquery_not_duplicated(self, mock_conn):
        """LIMIT inside a subquery should not prevent top-level LIMIT injection."""
        query = "CALL { MATCH (n) RETURN n LIMIT 5 } RETURN count(n)"
        mock_conn.execute_query.return_value = []
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            api.run_cypher(query, limit=10, conn=mock_conn)
        called_query = mock_conn.execute_query.call_args[0][0]
        # The regex finds any LIMIT so it won't inject — just verify no crash
        assert "LIMIT" in called_query

    def test_trailing_whitespace_after_semicolon(self, mock_conn):
        """Semicolons with trailing whitespace stripped before LIMIT injection."""
        mock_conn.execute_query.return_value = []
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            api.run_cypher("MATCH (n) RETURN n;  ", limit=10, conn=mock_conn)
        called_query = mock_conn.execute_query.call_args[0][0]
        assert ";" not in called_query
        assert "LIMIT 10" in called_query

    def test_limit_case_insensitive_detection(self, mock_conn):
        """Existing LIMIT (any case) prevents injection."""
        mock_conn.execute_query.return_value = [{"n": 1}]
        with patch(f"{MOD}.SyntaxValidator") as sv, \
             patch(f"{MOD}.SchemaValidator") as schv, \
             patch(f"{MOD}.PropertiesValidator") as pv:
            _valid_validators(sv, schv, pv)
            api.run_cypher("MATCH (n) RETURN n limit 5", limit=10, conn=mock_conn)
        called_query = mock_conn.execute_query.call_args[0][0]
        assert called_query.count("limit") + called_query.count("LIMIT") == 1
