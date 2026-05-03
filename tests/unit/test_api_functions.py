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
            gene_response_profile,
            genes_by_function,
            genes_by_ontology,
            gene_details,
            kg_schema,
            list_filter_values,
            list_clustering_analyses,
            list_organisms,
            resolve_gene,
            run_cypher,
            search_ontology,
            gene_clusters_by_gene,
            genes_in_cluster,
        )
        # Each should be the same object as in api.functions
        assert resolve_gene is api.resolve_gene
        assert gene_homologs is api.gene_homologs
        assert genes_by_function is api.genes_by_function
        assert list_clustering_analyses is api.list_clustering_analyses
        assert gene_clusters_by_gene is api.gene_clusters_by_gene
        assert genes_in_cluster is api.genes_in_cluster

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

    def test_offset_passed_to_builder(self, mock_conn):
        """offset is forwarded to the detail builder call."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        api.genes_by_function("DNA polymerase", offset=5, conn=mock_conn)
        detail_call = mock_conn.execute_query.call_args_list[1]
        assert detail_call[1].get("offset") == 5

    def test_offset_in_response(self, mock_conn):
        """Result dict includes offset key."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.genes_by_function("DNA polymerase", offset=5, conn=mock_conn)
        assert result["offset"] == 5


# ---------------------------------------------------------------------------
# gene_overview
# ---------------------------------------------------------------------------
class TestGeneOverview:
    def _summary_result(self, total=1, not_found=None, has_derived_metrics=0):
        """Helper: mock summary query result."""
        return [{
            "total_matching": total,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 1}],
            "by_category": [{"item": "DNA replication", "count": 1}],
            "by_annotation_type": [{"item": "go_bp", "count": 1}],
            "has_expression": 1,
            "has_significant_expression": 1,
            "has_orthologs": 1,
            "has_clusters": 0,
            "has_derived_metrics": has_derived_metrics,
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
             "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
             "cluster_membership_count": 0, "cluster_types": [],
             "numeric_metric_count": 0,
             "boolean_metric_count": 0,
             "categorical_metric_count": 0},
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
        assert "has_clusters" in result
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
                    "has_clusters": 0,
                    "has_derived_metrics": 0,
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

    def test_offset_passed_to_builder(self, mock_conn):
        """offset is forwarded to the detail builder call."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        api.gene_overview(["PMM0001"], offset=5, conn=mock_conn)
        detail_call = mock_conn.execute_query.call_args_list[1]
        assert detail_call[1].get("offset") == 5

    def test_offset_in_response(self, mock_conn):
        """Result dict includes offset key."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.gene_overview(["PMM0001"], offset=5, conn=mock_conn)
        assert result["offset"] == 5

    def test_synthesizes_dm_count_and_value_kinds(self, mock_conn):
        """Compact derived_metric_count = sum of per-kind; value_kinds = which kinds > 0."""
        detail_rows = [{
            "locus_tag": "PMM0001", "gene_name": "rbcL",
            "product": "RuBisCO large subunit",
            "gene_category": "Carbon fixation",
            "annotation_quality": 3,
            "organism_name": "Prochlorococcus MED4",
            "annotation_types": ["go_bp"],
            "expression_edge_count": 5,
            "significant_up_count": 2, "significant_down_count": 1,
            "closest_ortholog_group_size": 10,
            "closest_ortholog_genera": ["Prochlorococcus"],
            "cluster_membership_count": 0, "cluster_types": [],
            "numeric_metric_count": 5,
            "boolean_metric_count": 3,
            "categorical_metric_count": 0,
        }]
        summary_row = self._summary_result(total=1, has_derived_metrics=1)
        mock_conn.execute_query.side_effect = [summary_row, detail_rows]
        result = api.gene_overview(locus_tags=["PMM0001"], conn=mock_conn)
        assert result["has_derived_metrics"] == 1
        row = result["results"][0]
        assert row["derived_metric_count"] == 8
        assert set(row["derived_metric_value_kinds"]) == {"numeric", "boolean"}

    def test_zero_dm_gene_has_empty_value_kinds(self, mock_conn):
        """Gene with no DM annotations gets count=0 and empty value_kinds list."""
        detail_rows = [{
            "locus_tag": "PMM9999", "gene_name": "x",
            "product": "hypothetical protein",
            "gene_category": "Unknown",
            "annotation_quality": 1,
            "organism_name": "Prochlorococcus MED4",
            "annotation_types": [],
            "expression_edge_count": 0,
            "significant_up_count": 0, "significant_down_count": 0,
            "closest_ortholog_group_size": 0,
            "closest_ortholog_genera": [],
            "cluster_membership_count": 0, "cluster_types": [],
            "numeric_metric_count": 0,
            "boolean_metric_count": 0,
            "categorical_metric_count": 0,
        }]
        summary_row = self._summary_result(total=1, has_derived_metrics=0)
        mock_conn.execute_query.side_effect = [summary_row, detail_rows]
        result = api.gene_overview(locus_tags=["PMM9999"], conn=mock_conn)
        assert result["results"][0]["derived_metric_count"] == 0
        assert result["results"][0]["derived_metric_value_kinds"] == []

    def test_compact_strips_per_kind_and_types_observed(self, mock_conn):
        """Per-kind raw fields + types lists + compartments_observed are verbose-only."""
        detail_rows = [{
            "locus_tag": "PMM0001", "gene_name": "dnaN",
            "product": "DNA polymerase III subunit beta",
            "gene_category": "DNA replication",
            "annotation_quality": 3,
            "organism_name": "Prochlorococcus MED4",
            "annotation_types": ["go_bp"],
            "expression_edge_count": 5,
            "significant_up_count": 1, "significant_down_count": 0,
            "closest_ortholog_group_size": 10,
            "closest_ortholog_genera": ["Prochlorococcus"],
            "cluster_membership_count": 0, "cluster_types": [],
            "numeric_metric_count": 2,
            "boolean_metric_count": 1,
            "categorical_metric_count": 0,
            "numeric_metric_types_observed": ["diel_amplitude"],
            "boolean_metric_types_observed": ["rhythmic"],
            "categorical_metric_types_observed": [],
            "compartments_observed": ["intracellular"],
        }]
        mock_conn.execute_query.side_effect = [
            self._summary_result(has_derived_metrics=1), detail_rows,
        ]
        result = api.gene_overview(locus_tags=["PMM0001"], verbose=False, conn=mock_conn)
        row = result["results"][0]
        assert "numeric_metric_count" not in row
        assert "boolean_metric_count" not in row
        assert "categorical_metric_count" not in row
        assert "numeric_metric_types_observed" not in row
        assert "boolean_metric_types_observed" not in row
        assert "categorical_metric_types_observed" not in row
        assert "compartments_observed" not in row
        # But synthesized compact fields should be present
        assert "derived_metric_count" in row
        assert "derived_metric_value_kinds" in row

    def test_verbose_keeps_per_kind_and_types_observed(self, mock_conn):
        """Verbose mode preserves per-kind counts + types lists + compartments_observed."""
        detail_rows = [{
            "locus_tag": "PMM0001", "gene_name": "dnaN",
            "product": "DNA polymerase III subunit beta",
            "gene_category": "DNA replication",
            "annotation_quality": 3,
            "organism_name": "Prochlorococcus MED4",
            "annotation_types": ["go_bp"],
            "expression_edge_count": 5,
            "significant_up_count": 1, "significant_down_count": 0,
            "closest_ortholog_group_size": 10,
            "closest_ortholog_genera": ["Prochlorococcus"],
            "cluster_membership_count": 0, "cluster_types": [],
            "numeric_metric_count": 2,
            "boolean_metric_count": 1,
            "categorical_metric_count": 0,
            "numeric_metric_types_observed": ["diel_amplitude"],
            "boolean_metric_types_observed": ["rhythmic"],
            "categorical_metric_types_observed": [],
            "compartments_observed": ["intracellular"],
        }]
        mock_conn.execute_query.side_effect = [
            self._summary_result(has_derived_metrics=1), detail_rows,
        ]
        result = api.gene_overview(locus_tags=["PMM0001"], verbose=True, conn=mock_conn)
        row = result["results"][0]
        assert row["numeric_metric_count"] == 2
        assert row["boolean_metric_count"] == 1
        assert row["categorical_metric_count"] == 0
        assert row["numeric_metric_types_observed"] == ["diel_amplitude"]
        assert row["boolean_metric_types_observed"] == ["rhythmic"]
        assert row["categorical_metric_types_observed"] == []
        assert row["compartments_observed"] == ["intracellular"]
        assert row["derived_metric_count"] == 3
        assert set(row["derived_metric_value_kinds"]) == {"numeric", "boolean"}


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

    def test_offset_passed_to_builder(self, mock_conn):
        """offset is forwarded to the detail builder call."""
        gene_props = {"locus_tag": "PMM0001", "gene_name": "dnaN",
                       "product": "p", "organism_name": "MED4"}
        mock_conn.execute_query.side_effect = [
            [{"total_matching": 1, "not_found": []}],
            [{"gene": gene_props}],
        ]
        api.gene_details(["PMM0001"], offset=5, conn=mock_conn)
        detail_call = mock_conn.execute_query.call_args_list[1]
        assert detail_call[1].get("offset") == 5

    def test_offset_in_response(self, mock_conn):
        """Result dict includes offset key."""
        gene_props = {"locus_tag": "PMM0001", "gene_name": "dnaN",
                       "product": "p", "organism_name": "MED4"}
        mock_conn.execute_query.side_effect = [
            [{"total_matching": 1, "not_found": []}],
            [{"gene": gene_props}],
        ]
        result = api.gene_details(["PMM0001"], offset=5, conn=mock_conn)
        assert result["offset"] == 5


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
            "top_cyanorak_roles": [],
            "top_cog_categories": [],
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
                    "top_cyanorak_roles": [], "top_cog_categories": [],
                }],
            ]
            result = api.gene_homologs(["PMM0001"], summary=True)
        MockConn.assert_called_once()
        assert result["total_matching"] == 0

    def test_importable_from_package(self):
        """from multiomics_explorer import gene_homologs works."""
        from multiomics_explorer import gene_homologs
        assert gene_homologs is api.gene_homologs

    def test_offset_passed_to_builder(self, mock_conn):
        """offset is forwarded to the detail builder call."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        api.gene_homologs(["PMM0001"], offset=5, conn=mock_conn)
        detail_call = mock_conn.execute_query.call_args_list[1]
        assert detail_call[1].get("offset") == 5

    def test_offset_in_response(self, mock_conn):
        """Result dict includes offset key."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.gene_homologs(["PMM0001"], offset=5, conn=mock_conn)
        assert result["offset"] == 5

    def test_summary_includes_top_ontology(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_matching": 3,
              "by_organism": [{"item": "Prochlorococcus MED4", "count": 3}],
              "by_source": [{"item": "cyanorak", "count": 2}],
              "not_found": [], "no_groups": [],
              "top_cyanorak_roles": [{"id": "cyanorak.role:G.3", "name": "Energy", "count": 2}],
              "top_cog_categories": []}],
        ]
        result = api.gene_homologs(["PMM0845"], summary=True, conn=mock_conn)
        assert "top_cyanorak_roles" in result
        assert len(result["top_cyanorak_roles"]) == 1
        assert "top_cog_categories" in result


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

    def test_dispatches_metric_type(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"value": "damping_ratio", "count": 4},
            {"value": "diel_amplitude_protein_log2", "count": 2},
        ]
        result = api.list_filter_values(filter_type="metric_type", conn=mock_conn)
        assert result["filter_type"] == "metric_type"
        assert result["total_entries"] == 2
        assert result["results"][0] == {"value": "damping_ratio", "count": 4}

    def test_dispatches_value_kind(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"value": "boolean", "count": 14},
            {"value": "numeric", "count": 15},
        ]
        result = api.list_filter_values(filter_type="value_kind", conn=mock_conn)
        assert {r["value"] for r in result["results"]} == {"boolean", "numeric"}

    def test_dispatches_compartment(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"value": "whole_cell", "count": 160},
            {"value": "vesicle", "count": 5},
        ]
        result = api.list_filter_values(filter_type="compartment", conn=mock_conn)
        assert result["total_entries"] == 2
        assert result["results"][0]["value"] == "whole_cell"


# ---------------------------------------------------------------------------
# list_organisms
# ---------------------------------------------------------------------------
class TestListOrganisms:
    _ROWS = [
        {"organism_name": "Prochlorococcus MED4", "genus": "Prochlorococcus",
         "species": "Prochlorococcus marinus", "strain": "MED4", "clade": "HLI",
         "ncbi_taxon_id": 59919, "gene_count": 1976, "publication_count": 11,
         "experiment_count": 46, "treatment_types": ["coculture", "light_stress"],
         "omics_types": ["RNASEQ", "PROTEOMICS"],
         "clustering_analysis_count": 4, "cluster_types": ["condition_comparison", "diel"],
         "derived_metric_count": 7, "derived_metric_value_kinds": ["numeric", "boolean"],
         "compartments": ["whole_cell"],
         "background_factors": []},
        {"organism_name": "Alteromonas macleodii EZ55", "genus": "Alteromonas",
         "species": "Alteromonas macleodii", "strain": "EZ55", "clade": None,
         "ncbi_taxon_id": 28108, "gene_count": 4136, "publication_count": 2,
         "experiment_count": 13, "treatment_types": ["carbon_stress"],
         "omics_types": ["RNASEQ"],
         "clustering_analysis_count": 0, "cluster_types": [],
         "derived_metric_count": 0, "derived_metric_value_kinds": [],
         "compartments": [],
         "background_factors": []},
    ]
    # Summary row returned by build_list_organisms_summary (APOC frequencies format)
    _SUMMARY_ROW = {
        "total_entries": 2, "total_matching": 2,
        "by_value_kind": [{"item": "numeric", "count": 1}, {"item": "boolean", "count": 1}],
        "by_metric_type": [{"item": "damping_ratio", "count": 1}],
        "by_compartment": [{"item": "whole_cell", "count": 1}],
        "by_cluster_type": [{"item": "condition_comparison", "count": 1},
                             {"item": "diel", "count": 1}],
        "by_organism_type": [{"item": "genome_strain", "count": 2}],
    }

    def test_returns_dict(self, mock_conn):
        mock_conn.execute_query.side_effect = [[self._SUMMARY_ROW], self._ROWS]
        result = api.list_organisms(conn=mock_conn)
        assert isinstance(result, dict)
        assert result["total_entries"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["organism_name"] == "Prochlorococcus MED4"

    def test_passes_verbose(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], [],
        ]
        api.list_organisms(verbose=True, conn=mock_conn)
        # Second call is the detail query — check its cypher for "family"
        detail_cypher = mock_conn.execute_query.call_args_list[1][0][0]
        assert "family" in detail_cypher

    def test_limit_slices_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [[self._SUMMARY_ROW], self._ROWS]
        result = api.list_organisms(limit=1, conn=mock_conn)
        assert result["total_entries"] == 2
        assert len(result["results"]) == 1

    def test_limit_none_returns_all(self, mock_conn):
        mock_conn.execute_query.side_effect = [[self._SUMMARY_ROW], self._ROWS]
        result = api.list_organisms(conn=mock_conn)
        assert len(result["results"]) == 2

    def test_by_cluster_type_in_envelope(self, mock_conn):
        mock_conn.execute_query.side_effect = [[self._SUMMARY_ROW], self._ROWS]
        result = api.list_organisms(conn=mock_conn)
        assert "by_cluster_type" in result
        # MED4 has condition_comparison and diel; EZ55 has none
        ct_map = {b["cluster_type"]: b["count"] for b in result["by_cluster_type"]}
        assert ct_map["condition_comparison"] == 1
        assert ct_map["diel"] == 1

    def test_verbose_includes_cluster_count(self, mock_conn):
        rows = [{**r, "cluster_count": 10} for r in self._ROWS]
        mock_conn.execute_query.side_effect = [[self._SUMMARY_ROW], rows]
        result = api.list_organisms(verbose=True, conn=mock_conn)
        assert "cluster_count" in result["results"][0]

    def test_compact_excludes_cluster_count(self, mock_conn):
        rows = [{**r, "cluster_count": 10} for r in self._ROWS]
        mock_conn.execute_query.side_effect = [[self._SUMMARY_ROW], rows]
        result = api.list_organisms(verbose=False, conn=mock_conn)
        assert "cluster_count" not in result["results"][0]

    def test_offset_skips_results(self, mock_conn):
        org_rows = [
            {"organism_name": f"Org{i}", "genus": "G", "species": "S",
             "strain": "s", "clade": None, "ncbi_taxon_id": i,
             "gene_count": 100, "publication_count": 1,
             "experiment_count": 1, "treatment_types": [], "omics_types": [],
             "clustering_analysis_count": 0, "cluster_types": [],
             "derived_metric_count": 0, "derived_metric_value_kinds": [],
             "compartments": [],
             "background_factors": []}
            for i in range(5)
        ]
        summary = {**self._SUMMARY_ROW, "total_entries": 5, "total_matching": 5}
        mock_conn.execute_query.side_effect = [[summary], org_rows]
        result = api.list_organisms(limit=2, offset=2, conn=mock_conn)
        assert result["total_entries"] == 5
        assert result["returned"] == 2
        assert result["results"][0]["organism_name"] == "Org2"
        assert result["offset"] == 2
        assert result["truncated"] is True

    def test_total_matching_no_filter(self, mock_conn):
        """Without filter, total_matching and total_entries come from summary query."""
        mock_conn.execute_query.side_effect = [[self._SUMMARY_ROW], self._ROWS]
        result = api.list_organisms(conn=mock_conn)
        assert result["total_matching"] == 2
        assert result["total_entries"] == 2
        assert result["not_found"] == []
        # summary + detail = 2 calls (no not_found query when no filter)
        assert mock_conn.execute_query.call_count == 2

    def test_filter_lowercases_input(self, mock_conn):
        """api lowercases input list before forwarding to both builders."""
        filtered_summary = {**self._SUMMARY_ROW, "total_entries": 32, "total_matching": 1}
        mock_conn.execute_query.side_effect = [
            [filtered_summary],                          # summary
            self._ROWS[:1],                              # detail
            [{"found": ["prochlorococcus med4"]}],       # not_found lookup
        ]
        api.list_organisms(
            organism_names=["Prochlorococcus MED4"], conn=mock_conn,
        )
        # Second call is the detail query — params include lowercased list.
        detail_call_kwargs = mock_conn.execute_query.call_args_list[1][1]
        assert detail_call_kwargs["organism_names_lc"] == ["prochlorococcus med4"]

    def test_filter_with_unknown_populates_not_found(self, mock_conn):
        """Unknown names appear in not_found, original casing preserved."""
        filtered_summary = {**self._SUMMARY_ROW, "total_entries": 32, "total_matching": 1}
        mock_conn.execute_query.side_effect = [
            [filtered_summary],                          # summary
            self._ROWS[:1],                              # detail
            [{"found": ["prochlorococcus med4"]}],       # not_found lookup
        ]
        result = api.list_organisms(
            organism_names=["Prochlorococcus MED4", "Bogus Org"],
            conn=mock_conn,
        )
        assert result["total_entries"] == 32
        assert result["total_matching"] == 1
        assert result["not_found"] == ["Bogus Org"]

    def test_filter_all_match_empty_not_found(self, mock_conn):
        filtered_summary = {**self._SUMMARY_ROW, "total_entries": 32, "total_matching": 2}
        mock_conn.execute_query.side_effect = [
            [filtered_summary],                          # summary
            self._ROWS,                                  # detail
            [{"found": [
                "prochlorococcus med4",
                "alteromonas macleodii ez55",
            ]}],                                          # not_found lookup
        ]
        result = api.list_organisms(
            organism_names=["Prochlorococcus MED4", "Alteromonas macleodii EZ55"],
            conn=mock_conn,
        )
        assert result["not_found"] == []
        assert result["total_matching"] == 2

    # Chemistry rollup propagation + by_metabolic_capability envelope (slice 1)

    _CHEMISTRY_ROWS = [
        {**dict(_ROWS[0]), "reaction_count": 943, "metabolite_count": 1039},
        {**dict(_ROWS[1]), "reaction_count": 1348, "metabolite_count": 1428},
    ]

    def test_reaction_count_propagates_to_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], self._CHEMISTRY_ROWS,
        ]
        result = api.list_organisms(conn=mock_conn)
        assert result["results"][0]["reaction_count"] == 943
        assert result["results"][1]["reaction_count"] == 1348

    def test_metabolite_count_propagates_to_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], self._CHEMISTRY_ROWS,
        ]
        result = api.list_organisms(conn=mock_conn)
        assert result["results"][0]["metabolite_count"] == 1039
        assert result["results"][1]["metabolite_count"] == 1428

    def test_by_metabolic_capability_sorted_desc_by_metabolite_count(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], self._CHEMISTRY_ROWS,
        ]
        result = api.list_organisms(conn=mock_conn)
        cap = result["by_metabolic_capability"]
        assert len(cap) == 2
        # EZ55 has higher metabolite_count (1428 > 1039) — should be first
        assert cap[0]["organism_name"] == "Alteromonas macleodii EZ55"
        assert cap[0]["metabolite_count"] == 1428
        assert cap[0]["reaction_count"] == 1348
        assert cap[1]["organism_name"] == "Prochlorococcus MED4"

    def test_by_metabolic_capability_excludes_zero_chemistry(self, mock_conn):
        rows = [
            {**dict(self._ROWS[0]), "reaction_count": 943, "metabolite_count": 1039},
            {**dict(self._ROWS[1]), "reaction_count": 0, "metabolite_count": 0},
        ]
        mock_conn.execute_query.side_effect = [[self._SUMMARY_ROW], rows]
        result = api.list_organisms(conn=mock_conn)
        cap = result["by_metabolic_capability"]
        assert len(cap) == 1
        assert cap[0]["organism_name"] == "Prochlorococcus MED4"

    def test_by_metabolic_capability_empty_when_no_matches(self, mock_conn):
        empty_summary = {**self._SUMMARY_ROW, "total_entries": 0, "total_matching": 0}
        mock_conn.execute_query.side_effect = [[empty_summary], []]
        result = api.list_organisms(conn=mock_conn)
        assert result["by_metabolic_capability"] == []

    def test_by_metabolic_capability_summary_mode(self, mock_conn):
        """summary=True populates by_metabolic_capability via the dedicated
        capability builder, NOT the detail builder. Asserts call count = 2
        (summary + capability) so the summary fast path stays cheap."""
        capability_rows = [
            {"organism_name": r["organism_name"],
             "reaction_count": r["reaction_count"],
             "metabolite_count": r["metabolite_count"]}
            for r in self._CHEMISTRY_ROWS
        ]
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], capability_rows,
        ]
        result = api.list_organisms(summary=True, conn=mock_conn)
        assert result["results"] == []
        assert len(result["by_metabolic_capability"]) == 2
        assert result["by_metabolic_capability"][0]["metabolite_count"] == 1428
        # Exactly 2 Cypher calls: summary + capability. No detail builder.
        assert mock_conn.execute_query.call_count == 2
        # Verify the second call used the capability builder (3-column projection)
        second_cypher = mock_conn.execute_query.call_args_list[1][0][0]
        assert "metabolite_count" in second_cypher
        # Capability builder doesn't pull verbose detail columns
        assert "lineage" not in second_cypher
        assert "derived_metric_count" not in second_cypher

    def test_by_metabolic_capability_top_10_cap(self, mock_conn):
        """When matched set has > 10 chemistry-capable organisms, only top 10 returned."""
        rows = [
            {
                "organism_name": f"Org{i:02d}", "genus": "G", "species": "S",
                "strain": f"s{i}", "clade": None, "ncbi_taxon_id": i,
                "gene_count": 100, "publication_count": 1, "experiment_count": 1,
                "treatment_types": [], "omics_types": [],
                "clustering_analysis_count": 0, "cluster_types": [],
                "derived_metric_count": 0, "derived_metric_value_kinds": [],
                "compartments": [], "background_factors": [],
                "reaction_count": i, "metabolite_count": i * 10,
            }
            for i in range(15)  # 15 organisms; org00 has metabolite_count=0 so excluded
        ]
        summary = {**self._SUMMARY_ROW, "total_entries": 15, "total_matching": 15}
        mock_conn.execute_query.side_effect = [[summary], rows]
        result = api.list_organisms(conn=mock_conn)
        cap = result["by_metabolic_capability"]
        assert len(cap) == 10  # capped
        # Top entry should be Org14 (highest metabolite_count = 140)
        assert cap[0]["organism_name"] == "Org14"
        assert cap[0]["metabolite_count"] == 140

    def test_summary_flag_zeros_results(self, mock_conn):
        """summary=True → results=[], summary fields populated from summary builder."""
        mock_conn.execute_query.return_value = [self._SUMMARY_ROW]
        result = api.list_organisms(summary=True, conn=mock_conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["total_matching"] == 2
        # Rollups are sourced from the summary builder, so populated even when results=[].
        ct_map = {b["cluster_type"]: b["count"] for b in result["by_cluster_type"]}
        assert ct_map["condition_comparison"] == 1
        assert ct_map["diel"] == 1
        ot_map = {b["organism_type"]: b["count"] for b in result["by_organism_type"]}
        assert ot_map["genome_strain"] == 2
        assert result["truncated"] is True

    def test_breakdowns_over_filtered_set(self, mock_conn):
        """When filter applied, breakdowns reflect only matched rows."""
        filtered_summary = {**self._SUMMARY_ROW, "total_entries": 32, "total_matching": 1}
        mock_conn.execute_query.side_effect = [
            [filtered_summary],                          # summary
            self._ROWS[:1],                              # detail (MED4 only)
            [{"found": ["prochlorococcus med4"]}],
        ]
        result = api.list_organisms(
            organism_names=["Prochlorococcus MED4"], conn=mock_conn,
        )
        ct_map = {b["cluster_type"]: b["count"] for b in result["by_cluster_type"]}
        # Only MED4 contributes — EZ55 was filtered out.
        assert ct_map["condition_comparison"] == 1
        assert "diel" in ct_map

    def test_envelope_carries_dm_rollups(self, mock_conn):
        detail_rows = [{
            "organism_name": "Prochlorococcus marinus MED4",
            "organism_type": "marine_cyanobacterium",
            "genus": "Prochlorococcus", "species": "marinus", "strain": "MED4",
            "clade": "HLII", "ncbi_taxon_id": "59919",
            "gene_count": 1900, "publication_count": 4, "experiment_count": 12,
            "treatment_types": ["light_dark_cycle"], "background_factors": [],
            "omics_types": ["RNASEQ", "PROTEOMICS"],
            "clustering_analysis_count": 2, "cluster_types": ["coexpression"],
            "derived_metric_count": 7,
            "derived_metric_value_kinds": ["numeric", "boolean"],
            "compartments": ["whole_cell"],
            "reference_database": None, "reference_proteome": None,
            "growth_phases": [],
        }]
        summary_row = {
            "total_entries": 30, "total_matching": 1,
            "by_value_kind": [{"item": "numeric", "count": 6}, {"item": "boolean", "count": 1}],
            "by_metric_type": [{"item": "damping_ratio", "count": 1}],
            "by_compartment": [{"item": "whole_cell", "count": 1}],
        }
        mock_conn.execute_query.side_effect = [[summary_row], detail_rows]
        result = api.list_organisms(conn=mock_conn)
        # Envelope keys present
        assert "by_value_kind" in result
        assert "by_metric_type" in result
        assert "by_compartment" in result
        # _rename_freq shapes: [{value_kind: ..., count: ...}]
        vk_values = {r["value_kind"] for r in result["by_value_kind"]}
        assert vk_values & {"numeric", "boolean"}
        # Per-row fields
        assert result["results"][0]["derived_metric_count"] == 7
        assert result["results"][0]["compartments"] == ["whole_cell"]

    def test_compartment_filter_param_passes_through(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 30, "total_matching": 0,
              "by_value_kind": [], "by_metric_type": [], "by_compartment": []}],
            [],
        ]
        api.list_organisms(compartment="vesicle", conn=mock_conn)
        # Both summary + detail builders called with compartment param
        calls = mock_conn.execute_query.call_args_list
        assert any(c.kwargs.get("compartment") == "vesicle" for c in calls)


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

    def test_offset_passed_to_builder(self, mock_conn):
        """offset is forwarded to the detail builder call."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        api.search_ontology("DNA replication", "go_bp", offset=5, conn=mock_conn)
        detail_call = mock_conn.execute_query.call_args_list[1]
        assert detail_call[1].get("offset") == 5

    def test_offset_in_response(self, mock_conn):
        """Result dict includes offset key."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.search_ontology("DNA replication", "go_bp", offset=5, conn=mock_conn)
        assert result["offset"] == 5


# ---------------------------------------------------------------------------
# genes_by_ontology
# ---------------------------------------------------------------------------
class TestGenesByOntology:
    """Tests the 4-query composer: Query V -> Per-term -> Per-gene -> Detail."""

    @staticmethod
    def _org_resolve(name="Prochlorococcus MED4"):
        """Mock organism resolution response (first query after conn)."""
        return [{"organisms": [name]}]

    def _validate_rows(self, classifications):
        """Build mock Query V output: [(tid, status, matched_label), ...]."""
        return [
            {"tid": tid, "status": status, "matched_label": lbl}
            for tid, status, lbl in classifications
        ]

    def _per_term_rows(self, *terms):
        """Mock Query A output. Each term = (id, name, level, be, n_genes, cat_freqs)."""
        return [
            {"term_id": tid, "term_name": name, "level": lvl,
             "best_effort": be, "n_genes": n, "cat_freqs": freqs}
            for tid, name, lvl, be, n, freqs in terms
        ]

    def _per_gene_rows(self, *genes):
        """Mock Query B output. Each = (locus, cat, n_terms, levels_hit)."""
        return [
            {"locus_tag": lt, "gene_category": cat,
             "n_terms": nt, "levels_hit": lh}
            for lt, cat, nt, lh in genes
        ]

    def _detail_rows(self, n=3):
        return [
            {"locus_tag": f"PMM{i:04d}", "gene_name": None,
             "product": None, "gene_category": "Unknown",
             "term_id": "go:0022414", "term_name": "reproductive process",
             "level": 1}
            for i in range(n)
        ]

    def test_mode2_level_only_happy_path(self, mock_conn):
        # No term_ids -> skip Query V. Runs Org-resolve, A, B, D.
        mock_conn.execute_query.side_effect = [
            self._org_resolve(),
            # Query A (per-term)
            self._per_term_rows(
                ("go:0022414", "reproductive process", 1, False, 7,
                 [{"item": "Cell cycle", "count": 7}]),
                ("go:0050896", "response to stimulus", 1, False, 152,
                 [{"item": "Stress", "count": 100},
                  {"item": "Transport", "count": 52}]),
            ),
            # Query B (per-gene)
            self._per_gene_rows(
                ("PMM0001", "Cell cycle", 1, [1]),
                ("PMM0002", "Stress", 1, [1]),
            ),
            # Query D (detail)
            self._detail_rows(n=2),
        ]
        result = api.genes_by_ontology(
            ontology="go_bp",
            organism="Prochlorococcus MED4",
            level=1,
            conn=mock_conn,
        )
        assert result["ontology"] == "go_bp"
        assert result["organism_name"] == "Prochlorococcus MED4"
        assert result["total_matching"] == 159  # 7 + 152
        assert result["total_genes"] == 2
        assert result["total_terms"] == 2
        assert result["total_categories"] == 2
        # by_level computed from per_gene (one level here, count = 2 genes)
        assert result["by_level"] == [
            {"level": 1, "n_terms": 2, "n_genes": 2, "row_count": 159}
        ]
        # by_category from per_gene
        cats = {c["category"] for c in result["by_category"]}
        assert cats == {"Cell cycle", "Stress"}
        # top_terms sorted desc
        assert result["top_terms"][0]["term_id"] == "go:0050896"
        assert result["top_terms"][0]["count"] == 152
        # validation buckets empty (no term_ids)
        assert result["not_found"] == []
        assert result["wrong_ontology"] == []
        assert result["wrong_level"] == []
        assert result["filtered_out"] == []
        assert result["n_best_effort_terms"] == 0
        # detail
        assert len(result["results"]) == 2
        assert result["returned"] == 2
        assert mock_conn.execute_query.call_count == 4

    def test_mode1_term_ids_only_runs_validate(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._org_resolve(),
            # Query V
            self._validate_rows([("go:0006260", "ok", "BiologicalProcess")]),
            # Query A
            self._per_term_rows(
                ("go:0006260", "DNA replication", 6, False, 30,
                 [{"item": "Replication", "count": 30}]),
            ),
            # Query B
            self._per_gene_rows(
                ("PMM0001", "Replication", 1, [6]),
            ),
            # Query D
            self._detail_rows(n=1),
        ]
        result = api.genes_by_ontology(
            ontology="go_bp",
            organism="MED4",
            term_ids=["go:0006260"],
            conn=mock_conn,
        )
        assert result["not_found"] == []
        assert result["wrong_ontology"] == []
        assert result["filtered_out"] == []
        assert mock_conn.execute_query.call_count == 5

    def test_validation_buckets(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._org_resolve(),
            # Query V -- mixed statuses
            self._validate_rows([
                ("go:0006260", "ok", "BiologicalProcess"),
                ("fake:X", "not_found", None),
                ("kegg:K00001", "wrong_ontology", None),
                ("go:0008150", "wrong_level", "BiologicalProcess"),  # root, level=0
            ]),
            # Query A (only "ok" terms survived to per-term query)
            self._per_term_rows(
                ("go:0006260", "DNA replication", 3, False, 30,
                 [{"item": "Repl", "count": 30}]),
            ),
            # Query B
            self._per_gene_rows(("PMM0001", "Repl", 1, [3])),
            # Query D
            self._detail_rows(n=1),
        ]
        result = api.genes_by_ontology(
            ontology="go_bp",
            organism="MED4",
            level=3,
            term_ids=["go:0006260", "fake:X", "kegg:K00001", "go:0008150"],
            conn=mock_conn,
        )
        assert result["not_found"] == ["fake:X"]
        assert result["wrong_ontology"] == ["kegg:K00001"]
        assert result["wrong_level"] == ["go:0008150"]

    def test_filtered_out_bucket(self, mock_conn):
        # ok term_ids that don't appear in Query A output -> filtered_out.
        mock_conn.execute_query.side_effect = [
            self._org_resolve(),
            self._validate_rows([
                ("go:0006260", "ok", "BiologicalProcess"),
                ("go:0006412", "ok", "BiologicalProcess"),  # filtered out
            ]),
            # Only one term passed size filter
            self._per_term_rows(
                ("go:0006260", "DNA replication", 6, False, 30,
                 [{"item": "Repl", "count": 30}]),
            ),
            self._per_gene_rows(("PMM0001", "Repl", 1, [6])),
            self._detail_rows(n=1),
        ]
        result = api.genes_by_ontology(
            ontology="go_bp",
            organism="MED4",
            term_ids=["go:0006260", "go:0006412"],
            conn=mock_conn,
        )
        assert result["filtered_out"] == ["go:0006412"]

    def test_summary_mode_skips_detail(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._org_resolve(),
            self._per_term_rows(
                ("go:0022414", "reproductive process", 1, False, 7,
                 [{"item": "Cell cycle", "count": 7}]),
            ),
            self._per_gene_rows(("PMM0001", "Cell cycle", 1, [1])),
            # no detail
        ]
        result = api.genes_by_ontology(
            ontology="go_bp",
            organism="MED4",
            level=1,
            summary=True,
            conn=mock_conn,
        )
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True  # total_matching > 0 but returned=0
        assert mock_conn.execute_query.call_count == 3  # org-resolve + A + B, no detail

    def test_missing_level_and_term_ids_raises(self, mock_conn):
        with pytest.raises(ValueError, match="level.*term_ids"):
            api.genes_by_ontology(
                ontology="go_bp", organism="MED4", conn=mock_conn,
            )

    def test_bad_ontology_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.genes_by_ontology(
                ontology="nope", organism="MED4", level=1, conn=mock_conn,
            )

    def test_bad_size_bounds_raises(self, mock_conn):
        with pytest.raises(ValueError, match="max_gene_set_size"):
            api.genes_by_ontology(
                ontology="go_bp", organism="MED4", level=1,
                min_gene_set_size=10, max_gene_set_size=5,
                conn=mock_conn,
            )

    def test_best_effort_terms_counted(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._org_resolve(),
            self._per_term_rows(
                ("go:A", "A", 1, True, 5, []),
                ("go:B", "B", 1, False, 10, []),
                ("go:C", "C", 1, True, 7, []),
            ),
            self._per_gene_rows(
                ("PMM0001", "Unknown", 1, [1]),
            ),
            self._detail_rows(n=0),
        ]
        result = api.genes_by_ontology(
            ontology="go_bp", organism="MED4", level=1, conn=mock_conn,
        )
        assert result["n_best_effort_terms"] == 2


# ---------------------------------------------------------------------------
# gene_ontology_terms
# ---------------------------------------------------------------------------
@patch("multiomics_explorer.api.functions._validate_organism_inputs", return_value="Prochlorococcus MED4")
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
            {"locus_tag": locus_tag, "term_id": "go:0006260", "term_name": "DNA replication", "level": 5},
            {"locus_tag": locus_tag, "term_id": "go:0006351", "term_name": "DNA-templated transcription", "level": 4},
        ]

    def _summary_row(self, locus_tag="PMM0001"):
        """Helper: sample summary query result row."""
        return [{
            "gene_count": 1,
            "term_count": 2,
            "by_term": [
                {"term_id": "go:0006260", "term_name": "DNA replication", "level": 5, "count": 1},
                {"term_id": "go:0006351", "term_name": "DNA-templated transcription", "level": 4, "count": 1},
            ],
            "gene_term_counts": [{"locus_tag": locus_tag, "term_count": 2}],
        }]

    def test_returns_dict(self, _mock_validate, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),       # existence check
            self._summary_row(),                 # go_bp summary
            self._detail_rows(),                 # go_bp detail
        ]
        result = api.gene_ontology_terms(["PMM0001"], organism="MED4", ontology="go_bp", conn=mock_conn)
        assert isinstance(result, dict)

    def test_has_expected_keys(self, _mock_validate, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            self._summary_row(),
            self._detail_rows(),
        ]
        result = api.gene_ontology_terms(["PMM0001"], organism="MED4", ontology="go_bp", conn=mock_conn)
        expected_keys = {
            "total_matching", "total_genes", "total_terms",
            "by_ontology", "by_term",
            "terms_per_gene_min", "terms_per_gene_max", "terms_per_gene_median",
            "returned", "offset", "truncated", "not_found", "no_terms", "results",
        }
        assert set(result.keys()) == expected_keys

    def test_summary_sets_limit_zero(self, _mock_validate, mock_conn):
        """summary=True uses summary queries, returns empty results."""
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            self._summary_row(),
        ]
        result = api.gene_ontology_terms(
            ["PMM0001"], organism="MED4", ontology="go_bp", summary=True, conn=mock_conn,
        )
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert result["total_matching"] == 2

    def test_empty_locus_tags_raises(self, _mock_validate, mock_conn):
        with pytest.raises(ValueError, match="locus_tags must not be empty"):
            api.gene_ontology_terms([], organism="MED4", ontology="go_bp", conn=mock_conn)

    def test_invalid_ontology_raises(self, _mock_validate, mock_conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.gene_ontology_terms(["PMM0001"], organism="MED4", ontology="invalid", conn=mock_conn)

    def test_creates_conn_when_none(self, _mock_validate):
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
            result = api.gene_ontology_terms(["PMM0001"], organism="MED4", ontology="go_bp")
        MockConn.assert_called_once()
        assert isinstance(result, dict)

    def test_not_found_populated(self, _mock_validate, mock_conn):
        """Gene not in graph appears in not_found list."""
        mock_conn.execute_query.side_effect = [
            self._exist_mixed(found=["PMM0001"], not_found=["FAKE999"]),
            self._summary_row("PMM0001"),
            self._detail_rows("PMM0001"),
        ]
        result = api.gene_ontology_terms(
            ["PMM0001", "FAKE999"], organism="MED4", ontology="go_bp", conn=mock_conn,
        )
        assert "FAKE999" in result["not_found"]
        assert result["total_genes"] == 1

    def test_no_terms_populated(self, _mock_validate, mock_conn):
        """Gene exists but has no terms for the ontology."""
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            [],  # summary query returns nothing
            [],  # detail query returns nothing
        ]
        result = api.gene_ontology_terms(["PMM0001"], organism="MED4", ontology="go_bp", conn=mock_conn)
        assert "PMM0001" in result["no_terms"]
        assert result["total_matching"] == 0
        assert result["total_genes"] == 0

    def test_limit_caps_results(self, _mock_validate, mock_conn):
        """limit=2 with 5 total returns 2 results, truncated=True."""
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            # summary says 5 total
            [{
                "gene_count": 1, "term_count": 5,
                "by_term": [{"term_id": f"go:{i:07d}", "term_name": f"t{i}", "level": 3, "count": 1} for i in range(5)],
                "gene_term_counts": [{"locus_tag": "PMM0001", "term_count": 5}],
            }],
            # detail query (with limit=2 pushed in) returns 2 rows
            [
                {"locus_tag": "PMM0001", "term_id": "go:0000000", "term_name": "t0", "level": 3},
                {"locus_tag": "PMM0001", "term_id": "go:0000001", "term_name": "t1", "level": 3},
            ],
        ]
        result = api.gene_ontology_terms(
            ["PMM0001"], organism="MED4", ontology="go_bp", limit=2, conn=mock_conn,
        )
        assert result["returned"] == 2
        assert result["truncated"] is True
        assert result["total_matching"] == 5
        assert len(result["results"]) == 2

    def test_ontology_none_queries_all(self, _mock_validate, mock_conn):
        """ontology=None queries all ONTOLOGY_CONFIG keys."""
        from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG
        n = len(ONTOLOGY_CONFIG)

        # existence + n summaries (all empty) + n details (all empty)
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
        ] + [[] for _ in range(n)] + [[] for _ in range(n)]

        result = api.gene_ontology_terms(["PMM0001"], organism="MED4", conn=mock_conn)
        # 1 existence + n summary + n detail = 1 + 2n
        assert mock_conn.execute_query.call_count == 1 + 2 * n

    def test_importable_from_package(self, _mock_validate):
        """from multiomics_explorer import gene_ontology_terms works."""
        from multiomics_explorer import gene_ontology_terms
        assert gene_ontology_terms is api.gene_ontology_terms

    def test_offset_skips_results(self, _mock_validate, mock_conn):
        """offset skips rows from the merged detail result set."""
        rows = [
            {"locus_tag": "PMM0001", "term_id": f"go:{i:07d}", "term_name": f"t{i}", "level": 3}
            for i in range(5)
        ]
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            [{
                "gene_count": 1, "term_count": 5,
                "by_term": [{"term_id": f"go:{i:07d}", "term_name": f"t{i}", "level": 3, "count": 1}
                             for i in range(5)],
                "gene_term_counts": [{"locus_tag": "PMM0001", "term_count": 5}],
            }],
            rows,
        ]
        result = api.gene_ontology_terms(["PMM0001"], organism="MED4", ontology="go_bp", limit=2, offset=2, conn=mock_conn)
        assert result["offset"] == 2
        # Rows sorted by (locus_tag, term_id), then offset=2 applied, then limit=2
        assert len(result["results"]) == 2
        assert result["results"][0]["term_id"] == "go:0000002"
        assert result["results"][1]["term_id"] == "go:0000003"

    def test_offset_in_response(self, _mock_validate, mock_conn):
        """Result dict includes offset key."""
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            self._summary_row(),
            self._detail_rows(),
        ]
        result = api.gene_ontology_terms(["PMM0001"], organism="MED4", ontology="go_bp", offset=5, conn=mock_conn)
        assert result["offset"] == 5


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
    _PUB_ROW = {
        "doi": "10.1234/test", "title": "Test", "authors": ["A"],
        "year": 2024, "journal": "J", "study_type": "S",
        "organisms": ["MED4"], "experiment_count": 1,
        "treatment_types": ["coculture"], "background_factors": [],
        "omics_types": ["RNASEQ"],
        "clustering_analysis_count": 2, "cluster_types": ["condition_comparison"],
    }

    def test_returns_dict(self, mock_conn):
        """Runs summary + data queries, returns dict with total_entries/total_matching/results."""
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21, "total_matching": 21}],  # summary query
            [self._PUB_ROW],                                 # data query
        ]
        result = api.list_publications(conn=mock_conn)
        assert isinstance(result, dict)
        assert result["total_entries"] == 21
        assert result["total_matching"] == 21
        assert "by_organism" in result
        assert "by_treatment_type" in result
        assert "by_omics_type" in result
        assert "by_cluster_type" in result
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

    def test_verbose_includes_cluster_count(self, mock_conn):
        row = {**self._PUB_ROW, "abstract": "...", "description": "...", "cluster_count": 20}
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 1, "total_matching": 1}],
            [row],
        ]
        result = api.list_publications(verbose=True, conn=mock_conn)
        assert "cluster_count" in result["results"][0]

    def test_compact_excludes_cluster_count(self, mock_conn):
        row = {**self._PUB_ROW, "cluster_count": 20}
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 1, "total_matching": 1}],
            [row],
        ]
        result = api.list_publications(verbose=False, conn=mock_conn)
        assert "cluster_count" not in result["results"][0]

    def test_offset_skips_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 5, "total_matching": 5}],  # summary
            [{"doi": f"10.1234/{i}", "title": f"T{i}", "authors": "A",
              "year": 2024, "journal": "J", "study_type": "S",
              "organisms": ["MED4"], "experiment_count": 1,
              "treatment_types": ["light"], "omics_types": ["RNASEQ"],
              "clustering_analysis_count": 0, "cluster_types": [],
              "background_factors": []}
             for i in range(5)],  # detail
        ]
        result = api.list_publications(limit=2, offset=2, conn=mock_conn)
        assert result["total_matching"] == 5
        assert result["returned"] == 2
        assert result["results"][0]["doi"] == "10.1234/2"
        assert result["offset"] == 2

    def test_publication_dois_filter_threaded_to_builders(self, mock_conn):
        """publication_dois flows into the summary + detail builder params."""
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21, "total_matching": 1}],   # summary
            [{**self._PUB_ROW, "doi": "10.1234/a"}],         # detail
            [{"found": ["10.1234/a"]}],                      # not_found probe
        ]
        result = api.list_publications(
            publication_dois=["10.1234/a"], conn=mock_conn,
        )
        # Summary query has the filter
        summary_call = mock_conn.execute_query.call_args_list[0]
        assert summary_call.kwargs.get("publication_dois") == ["10.1234/a"]
        # Detail query has the filter
        detail_call = mock_conn.execute_query.call_args_list[1]
        assert detail_call.kwargs.get("publication_dois") == ["10.1234/a"]
        assert result["not_found"] == []
        assert result["results"][0]["doi"] == "10.1234/a"

    def test_publication_dois_not_found_populated(self, mock_conn):
        """Provided DOIs that no Publication matches surface in not_found.
        Comparison is case-insensitive (input preserved in not_found list)."""
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21, "total_matching": 1}],
            [{**self._PUB_ROW, "doi": "10.1234/a"}],
            [{"found": ["10.1234/a"]}],  # only one of two requested DOIs exists
        ]
        result = api.list_publications(
            publication_dois=["10.1234/A", "10.1234/zzz"],
            conn=mock_conn,
        )
        # 10.1234/A normalises to lowercase and matches
        assert result["not_found"] == ["10.1234/zzz"]
        assert result["total_matching"] == 1

    def test_publication_dois_not_found_probe_lowercases(self, mock_conn):
        """The not_found probe sends lowercased DOIs to Cypher."""
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21, "total_matching": 0}],
            [],
            [{"found": []}],
        ]
        api.list_publications(
            publication_dois=["10.1234/MIXEDCase"], conn=mock_conn,
        )
        probe_call = mock_conn.execute_query.call_args_list[2]
        assert probe_call.kwargs.get("dois") == ["10.1234/mixedcase"]

    def test_default_not_found_empty_list(self, mock_conn):
        """When publication_dois not provided, not_found is an empty list."""
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21, "total_matching": 21}],
            [self._PUB_ROW],
        ]
        result = api.list_publications(conn=mock_conn)
        assert result["not_found"] == []

    # --- DM rollup + compartment filter tests (slice 2 Task 3) ---

    def test_dm_envelope_keys_sourced_from_summary(self, mock_conn):
        """by_value_kind, by_metric_type, by_compartment sourced from summary row."""
        mock_conn.execute_query.side_effect = [
            [{
                "total_entries": 5, "total_matching": 5,
                "by_value_kind": [{"item": "numeric", "count": 3}],
                "by_metric_type": [{"item": "rhythmicity", "count": 2}],
                "by_compartment": [{"item": "whole_cell", "count": 4}],
                "by_cluster_type": [{"item": "condition_comparison", "count": 2}],
            }],
            [self._PUB_ROW],
        ]
        result = api.list_publications(conn=mock_conn)
        assert result["by_value_kind"] == [{"value_kind": "numeric", "count": 3}]
        assert result["by_metric_type"] == [{"metric_type": "rhythmicity", "count": 2}]
        assert result["by_compartment"] == [{"compartment": "whole_cell", "count": 4}]

    def test_by_cluster_type_sourced_from_summary(self, mock_conn):
        """by_cluster_type now sourced from summary row (migrated from in-memory)."""
        mock_conn.execute_query.side_effect = [
            [{
                "total_entries": 1, "total_matching": 1,
                "by_value_kind": [],
                "by_metric_type": [],
                "by_compartment": [],
                "by_cluster_type": [{"item": "condition_comparison", "count": 1}],
            }],
            [self._PUB_ROW],
        ]
        result = api.list_publications(conn=mock_conn)
        ct_map = {b["cluster_type"]: b["count"] for b in result["by_cluster_type"]}
        assert ct_map["condition_comparison"] == 1

    def test_compartment_filter_passed_to_builders(self, mock_conn):
        """compartment param is forwarded to summary and detail builders."""
        mock_conn.execute_query.side_effect = [
            [{
                "total_entries": 5, "total_matching": 2,
                "by_value_kind": [], "by_metric_type": [],
                "by_compartment": [{"item": "vesicle", "count": 2}],
                "by_cluster_type": [],
            }],
            [self._PUB_ROW],
        ]
        result = api.list_publications(compartment="vesicle", conn=mock_conn)
        # Both summary and detail query should receive $compartment
        summary_call = mock_conn.execute_query.call_args_list[0]
        detail_call = mock_conn.execute_query.call_args_list[1]
        assert summary_call.kwargs.get("compartment") == "vesicle"
        assert detail_call.kwargs.get("compartment") == "vesicle"
        assert result["total_matching"] == 2

    def test_per_row_dm_fields_present(self, mock_conn):
        """Per-row derived_metric_count, derived_metric_value_kinds, compartments present."""
        row = {
            **self._PUB_ROW,
            "derived_metric_count": 3,
            "derived_metric_value_kinds": ["numeric"],
            "compartments": ["whole_cell"],
        }
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 1, "total_matching": 1,
              "by_value_kind": [], "by_metric_type": [],
              "by_compartment": [], "by_cluster_type": []}],
            [row],
        ]
        result = api.list_publications(conn=mock_conn)
        r = result["results"][0]
        assert r["derived_metric_count"] == 3
        assert r["derived_metric_value_kinds"] == ["numeric"]
        assert r["compartments"] == ["whole_cell"]

    def test_verbose_per_row_dm_extras(self, mock_conn):
        """Verbose mode includes derived_metric_gene_count and derived_metric_types."""
        row = {
            **self._PUB_ROW,
            "abstract": "...", "description": "...", "cluster_count": 10,
            "derived_metric_count": 2,
            "derived_metric_value_kinds": ["boolean"],
            "compartments": [],
            "derived_metric_gene_count": 150,
            "derived_metric_types": ["diel_rhythmicity"],
        }
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 1, "total_matching": 1,
              "by_value_kind": [], "by_metric_type": [],
              "by_compartment": [], "by_cluster_type": []}],
            [row],
        ]
        result = api.list_publications(verbose=True, conn=mock_conn)
        r = result["results"][0]
        assert r["derived_metric_gene_count"] == 150
        assert r["derived_metric_types"] == ["diel_rhythmicity"]

    def test_missing_dm_envelope_keys_default_empty(self, mock_conn):
        """Missing DM envelope keys in summary row default to empty lists."""
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 1, "total_matching": 1}],  # no DM keys
            [self._PUB_ROW],
        ]
        result = api.list_publications(conn=mock_conn)
        assert result["by_value_kind"] == []
        assert result["by_metric_type"] == []
        assert result["by_compartment"] == []


class TestListExperiments:
    """Tests for list_experiments API function."""

    def _summary_result(self, total_matching=76, time_course_count=29):
        """Helper: mock summary query result."""
        return [{
            "total_matching": total_matching,
            "time_course_count": time_course_count,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 30}],
            "by_treatment_type": [{"item": "coculture", "count": 16}],
            "by_background_factors": [{"item": "pro99_medium", "count": 30}],
            "by_omics_type": [{"item": "RNASEQ", "count": 48}],
            "by_publication": [{"item": "10.1038/ismej.2016.70", "count": 5}],
            "by_table_scope": [{"item": "gene_level", "count": 40}],
            "by_cluster_type": [{"item": "condition_comparison", "count": 3}],
            "by_growth_phase": [{"item": "exponential", "count": 20}],
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
            "distinct_gene_count": 1696,
            "significant_up_count": 245,
            "significant_down_count": 178,
            "time_point_count": 1,
            "time_point_labels": ["20h"],
            "time_point_orders": [1],
            "time_point_hours": [20.0],
            "time_point_totals": [1696],
            "time_point_significant_up": [245],
            "time_point_significant_down": [178],
            "clustering_analysis_count": 1,
            "cluster_types": ["condition_comparison"],
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
        assert result["by_cluster_type"][0]["cluster_type"] == "condition_comparison"
        assert result["by_cluster_type"][0]["count"] == 3

    def test_verbose_includes_cluster_count(self, mock_conn):
        row = self._detail_row(cluster_count=20)
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [row],
        ]
        result = api.list_experiments(verbose=True, conn=mock_conn)
        assert "cluster_count" in result["results"][0]

    def test_compact_excludes_cluster_count(self, mock_conn):
        row = self._detail_row(cluster_count=20)
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [row],
        ]
        result = api.list_experiments(verbose=False, conn=mock_conn)
        assert "cluster_count" not in result["results"][0]

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

    def test_offset_passed_to_builder(self, mock_conn):
        """offset is forwarded to the detail builder call."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._detail_row()],
        ]
        api.list_experiments(offset=5, conn=mock_conn)
        detail_call = mock_conn.execute_query.call_args_list[2]
        assert detail_call[1].get("offset") == 5

    def test_offset_in_response(self, mock_conn):
        """Result dict includes offset key."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._detail_row()],
        ]
        result = api.list_experiments(offset=5, conn=mock_conn)
        assert result["offset"] == 5

    def test_experiment_ids_filter_threaded_to_builders(self, mock_conn):
        """experiment_ids flows into the summary + detail builder params (B2 #1)."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_matching=1),  # filtered summary
            self._summary_result(),                  # unfiltered total_entries
            [{"found": ["exp_a"]}],                  # not_found probe
            [self._detail_row(experiment_id="exp_a")],
        ]
        result = api.list_experiments(
            experiment_ids=["exp_a"], conn=mock_conn,
        )
        # Summary query has the filter
        summary_call = mock_conn.execute_query.call_args_list[0]
        assert summary_call.kwargs.get("experiment_ids") == ["exp_a"]
        # Detail query has the filter
        detail_call = mock_conn.execute_query.call_args_list[3]
        assert detail_call.kwargs.get("experiment_ids") == ["exp_a"]
        assert result["not_found"] == []
        assert result["results"][0]["experiment_id"] == "exp_a"

    def test_experiment_ids_not_found_populated(self, mock_conn):
        """Provided IDs that no Experiment matches surface in not_found."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_matching=1),
            self._summary_result(),
            [{"found": ["exp_a"]}],  # only one of the two requested ids exists
            [self._detail_row(experiment_id="exp_a")],
        ]
        result = api.list_experiments(
            experiment_ids=["exp_a", "exp_zzz"], conn=mock_conn,
        )
        assert result["not_found"] == ["exp_zzz"]
        assert result["total_matching"] == 1

    def test_experiment_ids_summary_mode_still_returns_not_found(self, mock_conn):
        """In summary mode, not_found is still populated (probe runs before
        the early return)."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_matching=1),
            self._summary_result(),
            [{"found": []}],  # neither id exists
        ]
        result = api.list_experiments(
            experiment_ids=["fake_a", "fake_b"], summary=True, conn=mock_conn,
        )
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["not_found"] == ["fake_a", "fake_b"]

    def test_default_not_found_empty_list(self, mock_conn):
        """When experiment_ids not provided, not_found is an empty list."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._detail_row()],
        ]
        result = api.list_experiments(conn=mock_conn)
        assert result["not_found"] == []

    def test_distinct_gene_count_passthrough(self, mock_conn):
        """distinct_gene_count flows through api/ post-process unchanged
        and the cumulative-vs-distinct invariant holds (B2 #2)."""
        # Time-course mock: cumulative gene_count = 6 * 1697 = 10182,
        # distinct_gene_count = 1697.
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._detail_row(
                experiment_id="time_course_med4",
                is_time_course="true",
                gene_count=10182,
                distinct_gene_count=1697,
                time_point_count=6,
                time_point_labels=["1h", "3h", "6h", "12h", "24h", "48h"],
                time_point_orders=[1, 2, 3, 4, 5, 6],
                time_point_hours=[1.0, 3.0, 6.0, 12.0, 24.0, 48.0],
                time_point_totals=[1697, 1697, 1697, 1697, 1697, 1697],
                time_point_significant_up=[10, 20, 30, 40, 50, 60],
                time_point_significant_down=[5, 10, 15, 20, 25, 30],
            )],
        ]
        result = api.list_experiments(conn=mock_conn)
        row = result["results"][0]
        assert row["distinct_gene_count"] == 1697
        assert row["gene_count"] == 10182
        # Invariant: distinct count never exceeds cumulative.
        assert row["distinct_gene_count"] <= row["gene_count"]

    # --- Task 4: DM rollups + compartment filter ---

    def _summary_result_with_dm(self, total_matching=76, time_course_count=29):
        """Summary result with DM rollup keys."""
        base = self._summary_result(total_matching, time_course_count)[0]
        base.update({
            "by_value_kind": [
                {"item": "numeric", "count": 15},
                {"item": "boolean", "count": 14},
            ],
            "by_metric_type": [
                {"item": "damping_ratio", "count": 4},
            ],
            "by_compartment": [
                {"item": "whole_cell", "count": 60},
                {"item": "vesicle", "count": 5},
            ],
        })
        return [base]

    def test_dm_envelope_keys_present(self, mock_conn):
        """by_value_kind, by_metric_type, by_compartment in envelope."""
        mock_conn.execute_query.side_effect = [
            self._summary_result_with_dm(),
            self._summary_result_with_dm(),
        ]
        result = api.list_experiments(summary=True, conn=mock_conn)
        assert "by_value_kind" in result
        assert "by_metric_type" in result
        assert "by_compartment" in result

    def test_dm_by_value_kind_renamed(self, mock_conn):
        """by_value_kind uses 'value_kind' key (renamed from apoc 'item')."""
        mock_conn.execute_query.side_effect = [
            self._summary_result_with_dm(),
            self._summary_result_with_dm(),
        ]
        result = api.list_experiments(summary=True, conn=mock_conn)
        assert result["by_value_kind"][0]["value_kind"] == "numeric"
        assert result["by_value_kind"][0]["count"] == 15

    def test_dm_by_metric_type_renamed(self, mock_conn):
        """by_metric_type uses 'metric_type' key."""
        mock_conn.execute_query.side_effect = [
            self._summary_result_with_dm(),
            self._summary_result_with_dm(),
        ]
        result = api.list_experiments(summary=True, conn=mock_conn)
        assert result["by_metric_type"][0]["metric_type"] == "damping_ratio"

    def test_dm_by_compartment_renamed(self, mock_conn):
        """by_compartment uses 'compartment' key."""
        mock_conn.execute_query.side_effect = [
            self._summary_result_with_dm(),
            self._summary_result_with_dm(),
        ]
        result = api.list_experiments(summary=True, conn=mock_conn)
        assert result["by_compartment"][0]["compartment"] == "whole_cell"
        assert result["by_compartment"][0]["count"] == 60

    def test_compartment_filter_passed_to_builders(self, mock_conn):
        """compartment param is forwarded to summary and detail builder calls."""
        mock_conn.execute_query.side_effect = [
            self._summary_result_with_dm(total_matching=5),
            self._summary_result_with_dm(),
            [self._detail_row()],
        ]
        api.list_experiments(compartment="vesicle", conn=mock_conn)
        summary_call = mock_conn.execute_query.call_args_list[0]
        assert summary_call.kwargs.get("compartment") == "vesicle"
        detail_call = mock_conn.execute_query.call_args_list[2]
        assert detail_call.kwargs.get("compartment") == "vesicle"

    def test_per_row_compartment_field(self, mock_conn):
        """Per-row 'compartment' scalar field flows through to results."""
        mock_conn.execute_query.side_effect = [
            self._summary_result_with_dm(),
            self._summary_result_with_dm(),
            [self._detail_row(
                compartment="whole_cell",
                derived_metric_count=3,
                derived_metric_value_kinds=["numeric", "boolean"],
            )],
        ]
        result = api.list_experiments(conn=mock_conn)
        row = result["results"][0]
        assert row["compartment"] == "whole_cell"
        assert row["derived_metric_count"] == 3
        assert row["derived_metric_value_kinds"] == ["numeric", "boolean"]

    def test_verbose_dm_extra_fields(self, mock_conn):
        """Verbose mode includes derived_metric_gene_count, derived_metric_types,
        reports_derived_metric_types."""
        mock_conn.execute_query.side_effect = [
            self._summary_result_with_dm(),
            self._summary_result_with_dm(),
            [self._detail_row(
                compartment="whole_cell",
                derived_metric_count=3,
                derived_metric_value_kinds=["numeric"],
                derived_metric_gene_count=450,
                derived_metric_types=["damping_ratio"],
                reports_derived_metric_types=["rhythmicity"],
            )],
        ]
        result = api.list_experiments(verbose=True, conn=mock_conn)
        row = result["results"][0]
        assert "derived_metric_gene_count" in row
        assert row["derived_metric_gene_count"] == 450
        assert "derived_metric_types" in row
        assert row["derived_metric_types"] == ["damping_ratio"]
        assert "reports_derived_metric_types" in row
        assert row["reports_derived_metric_types"] == ["rhythmicity"]

    def test_compact_no_verbose_dm_fields(self, mock_conn):
        """Compact mode excludes derived_metric_gene_count, derived_metric_types,
        reports_derived_metric_types."""
        mock_conn.execute_query.side_effect = [
            self._summary_result_with_dm(),
            self._summary_result_with_dm(),
            [self._detail_row(
                compartment="whole_cell",
                derived_metric_count=3,
                derived_metric_value_kinds=["numeric"],
                derived_metric_gene_count=450,
                derived_metric_types=["damping_ratio"],
                reports_derived_metric_types=["rhythmicity"],
            )],
        ]
        result = api.list_experiments(verbose=False, conn=mock_conn)
        row = result["results"][0]
        assert "derived_metric_gene_count" not in row
        assert "derived_metric_types" not in row
        assert "reports_derived_metric_types" not in row

    def test_per_tp_growth_phase_populated(self, mock_conn):
        """Per-TP growth_phase is zipped from time_point_growth_phases parallel array."""
        tc_row = self._tc_detail_row()
        tc_row["time_point_growth_phases"] = [
            "exponential", "nutrient_limited", "death",
        ]
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [tc_row],
        ]
        result = api.list_experiments(conn=mock_conn)
        timepoints = result["results"][0]["timepoints"]
        assert [tp["growth_phase"] for tp in timepoints] == [
            "exponential", "nutrient_limited", "death",
        ]

    def test_experiment_level_time_point_growth_phases_absent(self, mock_conn):
        """Experiment-level time_point_growth_phases is removed from the response."""
        tc_row = self._tc_detail_row()
        tc_row["time_point_growth_phases"] = [
            "exponential", "nutrient_limited", "death",
        ]
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [tc_row],
        ]
        result = api.list_experiments(conn=mock_conn)
        assert "time_point_growth_phases" not in result["results"][0]

    def test_per_tp_growth_phase_none_when_array_short(self, mock_conn):
        """If time_point_growth_phases has fewer entries than time_point_count, missing TPs get None."""
        tc_row = self._tc_detail_row()
        # 3 TPs declared, only 1 phase
        tc_row["time_point_growth_phases"] = ["exponential"]
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [tc_row],
        ]
        result = api.list_experiments(conn=mock_conn)
        timepoints = result["results"][0]["timepoints"]
        assert timepoints[0]["growth_phase"] == "exponential"
        assert timepoints[1]["growth_phase"] is None
        assert timepoints[2]["growth_phase"] is None

    def test_per_tp_growth_phase_none_when_array_missing(self, mock_conn):
        """If Cypher returns no time_point_growth_phases key at all, every TP gets None."""
        tc_row = self._tc_detail_row()
        # Do not add time_point_growth_phases — simulates pre-Cypher-coalesce or empty data
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [tc_row],
        ]
        result = api.list_experiments(conn=mock_conn)
        timepoints = result["results"][0]["timepoints"]
        assert all(tp["growth_phase"] is None for tp in timepoints)

    def test_authors_passes_through_from_builder(self, mock_conn):
        """Authors column from builder appears in api result rows verbatim."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),   # filtered summary
            self._summary_result(),   # unfiltered total_entries
            [self._detail_row(authors=["Smith J", "Jones K"])],  # detail query
        ]
        result = api.list_experiments(conn=mock_conn)
        assert result["results"][0]["authors"] == ["Smith J", "Jones K"]


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
            "rows_by_background_factors": [],
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
            "experiment_count", "rows_by_treatment_type",
            "rows_by_background_factors", "by_table_scope",
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

    def test_offset_passed_to_builder(self, mock_conn):
        """offset is forwarded to the detail builder call."""
        mock_conn.execute_query.side_effect = self._mock_side_effect_organism_only()
        api.differential_expression_by_gene(organism="MED4", offset=5, conn=mock_conn)
        # detail call is the 5th call (index 4): organism pre-query + 3 summary + detail
        detail_call = mock_conn.execute_query.call_args_list[4]
        assert detail_call[1].get("offset") == 5

    def test_offset_in_response(self, mock_conn):
        """Result dict includes offset key."""
        mock_conn.execute_query.side_effect = self._mock_side_effect_organism_only()
        result = api.differential_expression_by_gene(organism="MED4", offset=5, conn=mock_conn)
        assert result["offset"] == 5


class TestSearchHomologGroups:
    """Tests for search_homolog_groups API function."""

    def test_returns_dict(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21122, "total_matching": 5,
              "score_max": 3.5, "score_median": 2.0,
              "by_source": [{"item": "cyanorak", "count": 3}],
              "by_level": [{"item": "curated", "count": 3}],
              "top_cyanorak_roles": [], "top_cog_categories": []}],
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
              "by_source": [], "by_level": [],
              "top_cyanorak_roles": [], "top_cog_categories": []}],
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
              "by_source": [], "by_level": [],
              "top_cyanorak_roles": [], "top_cog_categories": []}],
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
              "by_source": [], "by_level": [],
              "top_cyanorak_roles": [], "top_cog_categories": []}],
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

    def test_offset_passed_to_builder(self, mock_conn):
        """offset is forwarded to the detail builder call."""
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21122, "total_matching": 5,
              "score_max": 3.5, "score_median": 2.0,
              "by_source": [], "by_level": [],
              "top_cyanorak_roles": [], "top_cog_categories": []}],
            [{"group_id": "cyanorak:CK_1", "group_name": "CK_1",
              "consensus_gene_name": "psbB", "consensus_product": "photosystem II",
              "source": "cyanorak", "taxonomic_level": "curated",
              "specificity_rank": 0, "member_count": 9, "organism_count": 9,
              "score": 3.5}],
        ]
        api.search_homolog_groups("photosynthesis", offset=5, conn=mock_conn)
        detail_call = mock_conn.execute_query.call_args_list[1]
        assert detail_call[1].get("offset") == 5

    def test_offset_in_response(self, mock_conn):
        """Result dict includes offset key."""
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21122, "total_matching": 5,
              "score_max": 3.5, "score_median": 2.0,
              "by_source": [], "by_level": [],
              "top_cyanorak_roles": [], "top_cog_categories": []}],
            [{"group_id": "cyanorak:CK_1", "group_name": "CK_1",
              "consensus_gene_name": "psbB", "consensus_product": "photosystem II",
              "source": "cyanorak", "taxonomic_level": "curated",
              "specificity_rank": 0, "member_count": 9, "organism_count": 9,
              "score": 3.5}],
        ]
        result = api.search_homolog_groups("photosynthesis", offset=5, conn=mock_conn)
        assert result["offset"] == 5

    def test_passes_ontology_filters(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21122, "total_matching": 0,
              "score_max": None, "score_median": None,
              "by_source": [], "by_level": [],
              "top_cyanorak_roles": [], "top_cog_categories": []}],
        ]
        api.search_homolog_groups(
            "test", cyanorak_roles=["cyanorak.role:G.3"],
            cog_categories=["cog.category:J"], summary=True, conn=mock_conn)
        call_args = mock_conn.execute_query.call_args
        cypher = call_args[0][0]
        assert "Og_has_cyanorak_role" in cypher
        assert "Og_in_cog_category" in cypher

    def test_summary_includes_top_ontology(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21122, "total_matching": 5,
              "score_max": 3.5, "score_median": 2.0,
              "by_source": [], "by_level": [],
              "top_cyanorak_roles": [{"id": "cyanorak.role:G.3", "name": "Energy", "count": 3}],
              "top_cog_categories": [{"id": "cog.category:C", "name": "Energy prod", "count": 2}]}],
        ]
        result = api.search_homolog_groups("test", summary=True, conn=mock_conn)
        assert len(result["top_cyanorak_roles"]) == 1
        assert result["top_cyanorak_roles"][0]["id"] == "cyanorak.role:G.3"
        assert len(result["top_cog_categories"]) == 1


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

    def test_offset_passed_to_builder(self, mock_conn):
        """offset is forwarded to the detail builder call."""
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
        api.genes_by_homolog_group(["cyanorak:CK_00000570"], offset=5, conn=mock_conn)
        detail_call = mock_conn.execute_query.call_args_list[1]
        assert detail_call[1].get("offset") == 5

    def test_offset_in_response(self, mock_conn):
        """Result dict includes offset key."""
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
        result = api.genes_by_homolog_group(["cyanorak:CK_00000570"], offset=5, conn=mock_conn)
        assert result["offset"] == 5


class TestDifferentialExpressionByOrtholog:
    """Tests for differential_expression_by_ortholog API function."""

    def test_returns_dict(self, mock_conn):
        # Mock all 6 query results (Q1a group check + Q1b summary + Q2-Q5)
        mock_conn.execute_query.side_effect = [
            [{"not_found": []}],  # Q1a group check
            [{"total_matching": 10, "matching_genes": 3, "matching_groups": 1,
              "experiment_count": 2, "by_organism": [], "rows_by_status": [],
              "rows_by_treatment_type": [], "rows_by_background_factors": [],
              "by_table_scope": [],
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
              "rows_by_treatment_type": [], "rows_by_background_factors": [],
              "by_table_scope": [],
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
              "rows_by_treatment_type": [], "rows_by_background_factors": [],
              "by_table_scope": [],
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
              "rows_by_treatment_type": [], "rows_by_background_factors": [],
              "by_table_scope": [],
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

    def test_offset_passed_to_builder(self, mock_conn):
        """offset is forwarded to the detail (Q4) builder call."""
        mock_conn.execute_query.side_effect = [
            [{"not_found": []}],  # Q1a group check
            [{"total_matching": 10, "matching_genes": 3, "matching_groups": 1,
              "experiment_count": 2, "by_organism": [], "rows_by_status": [],
              "rows_by_treatment_type": [], "rows_by_background_factors": [],
              "by_table_scope": [],
              "sig_log2fcs": [1.5, 2.0],
              "matched_group_ids": ["g1"]}],  # Q1b
            [{"top_groups": []}],  # Q2
            [{"top_experiments": []}],  # Q3
            [],  # Q4 results
            [],  # Q5 membership
        ]
        api.differential_expression_by_ortholog(group_ids=["g1"], offset=5, conn=mock_conn)
        # Q4 is call index 4
        detail_call = mock_conn.execute_query.call_args_list[4]
        assert detail_call[1].get("offset") == 5

    def test_offset_in_response(self, mock_conn):
        """Result dict includes offset key."""
        mock_conn.execute_query.side_effect = [
            [{"not_found": []}],
            [{"total_matching": 10, "matching_genes": 3, "matching_groups": 1,
              "experiment_count": 2, "by_organism": [], "rows_by_status": [],
              "rows_by_treatment_type": [], "rows_by_background_factors": [],
              "by_table_scope": [],
              "sig_log2fcs": [1.5, 2.0],
              "matched_group_ids": ["g1"]}],
            [{"top_groups": []}],
            [{"top_experiments": []}],
            [],
            [],
        ]
        result = api.differential_expression_by_ortholog(
            group_ids=["g1"], offset=5, conn=mock_conn,
        )
        assert result["offset"] == 5


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


# ---------------------------------------------------------------------------
# gene_response_profile
# ---------------------------------------------------------------------------
class TestGeneResponseProfile:
    _ORGANISM = "Prochlorococcus marinus subsp. pastoris str. CCMP1986"

    def _make_envelope_result(self, found=None, has_expression=None, has_significant=None, group_totals=None):
        return [{
            "found_genes": found or ["PMM0370"],
            "has_expression": has_expression or ["PMM0370"],
            "has_significant": has_significant or ["PMM0370"],
            "group_totals": group_totals or [
                {"group_key": "nitrogen_stress", "experiments": 4, "timepoints": 14, "table_scopes": ["all_detected_genes"]},
                {"group_key": "coculture", "experiments": 2, "timepoints": 6, "table_scopes": ["significant_only"]},
            ],
        }]

    def _make_agg_rows(self):
        return [
            {
                "locus_tag": "PMM0370", "gene_name": "cynA",
                "product": "cyanate transporter", "gene_category": "Inorganic ion transport",
                "group_key": "nitrogen_stress", "experiments_tested": 3,
                "timepoints_tested": 8, "timepoints_up": 8, "timepoints_down": 0,
                "rank_ups": [3, 5, 8, 10, 12, 7, 6, 9], "rank_downs": [],
                "log2fcs_up": [5.7, 4.2, 3.1, 2.8, 2.5, 3.5, 3.8, 2.9], "log2fcs_down": [],
                "experiments_up": 3, "experiments_down": 0,
            },
            {
                "locus_tag": "PMM0370", "gene_name": "cynA",
                "product": "cyanate transporter", "gene_category": "Inorganic ion transport",
                "group_key": "coculture", "experiments_tested": 2,
                "timepoints_tested": 5, "timepoints_up": 0, "timepoints_down": 5,
                "rank_ups": [], "rank_downs": [12, 15, 14, 16, 18],
                "log2fcs_up": [], "log2fcs_down": [-13.0, -10.2, -8.5, -7.1, -6.0],
                "experiments_up": 0, "experiments_down": 2,
            },
        ]

    def test_returns_dict_with_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370"], conn=mock_conn)
        assert isinstance(result, dict)
        for key in ["results", "genes_queried", "genes_with_response", "returned",
                     "truncated", "not_found", "no_expression", "organism_name", "offset"]:
            assert key in result

    def test_not_found(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(found=["PMM0370"]),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370", "FAKE999"], conn=mock_conn)
        assert "FAKE999" in result["not_found"]

    def test_no_expression(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(found=["PMM0370", "PMM1234"], has_expression=["PMM0370"]),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370", "PMM1234"], conn=mock_conn)
        assert "PMM1234" in result["no_expression"]

    def test_response_summary_structure(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370"], conn=mock_conn)
        gene = result["results"][0]
        ns = gene["response_summary"]["nitrogen_stress"]
        assert ns["experiments_total"] == 4
        assert ns["experiments_tested"] == 3
        assert ns["experiments_up"] == 3
        assert ns["experiments_down"] == 0
        assert ns["timepoints_total"] == 14
        assert ns["timepoints_tested"] == 8
        assert ns["timepoints_up"] == 8
        assert ns["timepoints_down"] == 0

    def test_directional_fields_present_when_up(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370"], conn=mock_conn)
        ns = result["results"][0]["response_summary"]["nitrogen_stress"]
        assert "up_best_rank" in ns
        assert "up_median_rank" in ns
        assert "up_max_log2fc" in ns
        assert ns["up_best_rank"] == 3
        assert ns["up_max_log2fc"] == 5.7

    def test_directional_fields_absent_when_no_up(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370"], conn=mock_conn)
        cc = result["results"][0]["response_summary"]["coculture"]
        assert "up_best_rank" not in cc
        assert "up_median_rank" not in cc
        assert "up_max_log2fc" not in cc
        assert "down_best_rank" in cc
        assert cc["down_best_rank"] == 12

    def test_triage_lists(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370"], conn=mock_conn)
        gene = result["results"][0]
        assert "nitrogen_stress" in gene["groups_responded"]
        assert "coculture" in gene["groups_responded"]
        assert gene["groups_not_responded"] == []
        assert gene["groups_not_known"] == []

    def test_groups_not_known(self, mock_conn):
        agg_rows = [self._make_agg_rows()[0]]  # only nitrogen_stress
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(),
            agg_rows,
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370"], conn=mock_conn)
        gene = result["results"][0]
        # coculture has significant_only scope → tested_not_responded, not not_known
        assert "coculture" in gene["groups_tested_not_responded"]
        assert "coculture" not in gene["groups_not_known"]

    def test_groups_tested_not_responded(self, mock_conn):
        """Gene with no edges in a significant_only group → groups_tested_not_responded."""
        agg_rows = [self._make_agg_rows()[0]]  # only nitrogen_stress
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(),
            agg_rows,
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370"], conn=mock_conn)
        gene = result["results"][0]
        # coculture has table_scopes=["significant_only"] and gene has no edges → tested_not_responded
        assert "coculture" in gene["groups_tested_not_responded"]
        assert "coculture" not in gene["groups_not_known"]

    def test_groups_not_known_with_mixed_scopes(self, mock_conn):
        """Gene with no edges in a mixed-scope group stays in groups_not_known."""
        agg_rows = [self._make_agg_rows()[0]]  # only nitrogen_stress
        env = self._make_envelope_result(group_totals=[
            {"group_key": "nitrogen_stress", "experiments": 4, "timepoints": 14, "table_scopes": ["all_detected_genes"]},
            {"group_key": "iron_stress", "experiments": 3, "timepoints": 9, "table_scopes": ["significant_only", "filtered_subset"]},
        ])
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            env,
            agg_rows,
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370"], conn=mock_conn)
        gene = result["results"][0]
        # iron_stress has mixed scopes (includes filtered_subset) → stays not_known
        assert "iron_stress" in gene["groups_not_known"]
        assert "iron_stress" not in gene.get("groups_tested_not_responded", [])

    def test_groups_tested_not_responded_all_scopes_full_coverage(self, mock_conn):
        """Group with both significant_only and significant_any_timepoint → tested_not_responded."""
        agg_rows = [self._make_agg_rows()[0]]  # only nitrogen_stress
        env = self._make_envelope_result(group_totals=[
            {"group_key": "nitrogen_stress", "experiments": 4, "timepoints": 14, "table_scopes": ["all_detected_genes"]},
            {"group_key": "light_stress", "experiments": 3, "timepoints": 9, "table_scopes": ["significant_only", "significant_any_timepoint"]},
        ])
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            env,
            agg_rows,
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370"], conn=mock_conn)
        gene = result["results"][0]
        assert "light_stress" in gene["groups_tested_not_responded"]
        assert "light_stress" not in gene["groups_not_known"]

    def test_pagination(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(
                found=["PMM0001", "PMM0002", "PMM0003"],
                has_significant=["PMM0001", "PMM0002", "PMM0003"],
                has_expression=["PMM0001", "PMM0002", "PMM0003"],
            ),
            [
                {**self._make_agg_rows()[0], "locus_tag": "PMM0001"},
                {**self._make_agg_rows()[0], "locus_tag": "PMM0002"},
            ],
        ]
        result = api.gene_response_profile(
            locus_tags=["PMM0001", "PMM0002", "PMM0003"], limit=2, conn=mock_conn,
        )
        assert result["returned"] == 2
        assert result["truncated"] is True
        assert result["genes_queried"] == 3

    def test_empty_locus_tags_raises(self, mock_conn):
        with pytest.raises(ValueError, match="locus_tags"):
            api.gene_response_profile(locus_tags=[], conn=mock_conn)

    def test_invalid_group_by_raises(self, mock_conn):
        with pytest.raises(ValueError, match="group_by"):
            api.gene_response_profile(locus_tags=["PMM0370"], group_by="bad", conn=mock_conn)


# ---------------------------------------------------------------------------
# list_gene_clusters
# ---------------------------------------------------------------------------
class TestListClusteringAnalyses:
    """Tests for list_clustering_analyses API function."""

    _SUMMARY_RESULT = {
        "total_entries": 4, "total_matching": 3,
        "by_organism": [{"item": "Prochlorococcus MED4", "count": 3}],
        "by_cluster_type": [{"item": "stress_response", "count": 3}],
        "by_treatment_type": [{"item": "nitrogen_stress", "count": 3}],
        "by_background_factors": [{"item": "pro99_medium", "count": 3}],
        "by_omics_type": [{"item": "MICROARRAY", "count": 3}],
    }

    _SUMMARY_RESULT_WITH_SCORE = {
        **_SUMMARY_RESULT,
        "score_max": 5.2, "score_median": 2.1,
    }

    _DETAIL_ROW = {
        "analysis_id": "ca:tolonen2006:med4:nitrogen",
        "name": "MED4 nitrogen stress clustering",
        "organism_name": "Prochlorococcus MED4",
        "cluster_method": "k-means",
        "cluster_type": "stress_response",
        "cluster_count": 9,
        "total_gene_count": 150,
        "treatment_type": ["nitrogen_stress"],
        "background_factors": ["pro99_medium"],
        "omics_type": "MICROARRAY",
        "experiment_ids": ["exp:tolonen2006:1"],
        "clusters": [{"cluster_id": "gc:1", "name": "cluster 1", "member_count": 5}],
    }

    def test_summary_mode(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT],
        ]
        result = api.list_clustering_analyses(summary=True, conn=mock_conn)
        assert result["returned"] == 0
        assert result["results"] == []
        assert result["total_entries"] == 4
        assert result["total_matching"] == 3
        assert mock_conn.execute_query.call_count == 1
        # Verify envelope keys present
        for key in ("by_organism", "by_cluster_type", "by_treatment_type",
                     "by_background_factors", "by_omics_type"):
            assert key in result

    def test_detail_mode(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT],
            [self._DETAIL_ROW],
        ]
        result = api.list_clustering_analyses(conn=mock_conn)
        assert isinstance(result, dict)
        assert result["total_entries"] == 4
        assert result["total_matching"] == 3
        assert result["returned"] == 1
        assert len(result["results"]) == 1
        assert result["results"][0]["analysis_id"] == "ca:tolonen2006:med4:nitrogen"

    def test_empty_search_text_raises(self, mock_conn):
        with pytest.raises(ValueError, match="search_text must not be empty"):
            api.list_clustering_analyses(search_text="", conn=mock_conn)

    def test_by_organism_rename(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT],
        ]
        result = api.list_clustering_analyses(summary=True, conn=mock_conn)
        assert result["by_organism"][0]["organism_name"] == "Prochlorococcus MED4"

    def test_search_text_adds_score_fields(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT_WITH_SCORE],
            [{**self._DETAIL_ROW, "score": 5.2}],
        ]
        result = api.list_clustering_analyses(
            search_text="nitrogen", conn=mock_conn)
        assert result["score_max"] == 5.2
        assert result["score_median"] == 2.1


# ---------------------------------------------------------------------------
# gene_clusters_by_gene
# ---------------------------------------------------------------------------
class TestGeneClustersByGene:
    """Tests for gene_clusters_by_gene API function."""

    _SUMMARY_RESULT = {
        "total_matching": 2, "total_clusters": 2,
        "genes_with_clusters": 2, "genes_without_clusters": 0,
        "not_found": [], "not_matched": [],
        "by_cluster_type": [{"item": "stress_response", "count": 2}],
        "by_treatment_type": [{"item": "nitrogen_stress", "count": 2}],
        "by_background_factors": [],
        "by_analysis": [{"item": "ca:tolonen2006:med4:nitrogen", "count": 2}],
    }

    _DETAIL_ROW = {
        "locus_tag": "PMM0370",
        "gene_name": "cynA",
        "cluster_id": "cluster:msb4100087:med4:up_n_transport",
        "cluster_name": "MED4 cluster 1 (up, N transport)",
        "cluster_type": "stress_response",
        "membership_score": None,
        "analysis_id": "ca:tolonen2006:med4:nitrogen",
        "analysis_name": "MED4 nitrogen stress clustering",
        "treatment_type": ["nitrogen_stress"],
        "background_factors": [],
    }

    def test_returns_envelope(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            # organism validation
            [{"organisms": ["Prochlorococcus MED4"]}],
            # summary
            [self._SUMMARY_RESULT],
            # detail
            [self._DETAIL_ROW],
        ]
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], conn=mock_conn)
        assert result["total_matching"] == 2
        assert result["total_clusters"] == 2
        assert result["genes_with_clusters"] == 2
        assert len(result["results"]) == 1

    def test_by_analysis_in_envelope(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],
            [self._SUMMARY_RESULT],
        ]
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], summary=True, conn=mock_conn)
        assert "by_analysis" in result
        assert result["by_analysis"][0]["analysis_id"] == "ca:tolonen2006:med4:nitrogen"

    def test_analysis_ids_parameter(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],
            [self._SUMMARY_RESULT],
        ]
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"],
            analysis_ids=["ca:tolonen2006:med4:nitrogen"],
            summary=True, conn=mock_conn)
        assert result["returned"] == 0

    def test_empty_locus_tags_raises(self, mock_conn):
        with pytest.raises(ValueError, match="locus_tags must not be empty"):
            api.gene_clusters_by_gene(locus_tags=[], conn=mock_conn)

    def test_summary_mode(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],
            [self._SUMMARY_RESULT],
        ]
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], summary=True, conn=mock_conn)
        assert result["returned"] == 0
        assert result["results"] == []

    def test_not_found_always_in_envelope(self, mock_conn):
        summary_with_nf = {
            **self._SUMMARY_RESULT,
            "not_found": ["FAKE001"],
            "genes_without_clusters": 0,
        }
        mock_conn.execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],
            [summary_with_nf],
        ]
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370", "FAKE001"], summary=True, conn=mock_conn)
        assert "FAKE001" in result["not_found"]


class TestGenesInCluster:
    """Tests for genes_in_cluster API function."""

    _SUMMARY_RESULT = {
        "total_matching": 5,
        "by_organism": [{"item": "Prochlorococcus MED4", "count": 5}],
        "by_cluster": [{"cluster_id": "cluster:msb4100087:med4:up_n_transport",
                         "cluster_name": "MED4 cluster 1", "count": 5}],
        "by_category_raw": [{"item": "N-metabolism", "count": 3}],
        "not_found_clusters": [],
        "not_matched_clusters": [],
    }

    _DETAIL_ROW = {
        "locus_tag": "PMM0370",
        "gene_name": "cynA",
        "product": "cyanate ABC transporter",
        "gene_category": "N-metabolism",
        "organism_name": "Prochlorococcus MED4",
        "cluster_id": "cluster:msb4100087:med4:up_n_transport",
        "cluster_name": "MED4 cluster 1 (up, N transport)",
        "membership_score": None,
    }

    def test_returns_envelope_with_cluster_ids(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT],
            [self._DETAIL_ROW],
        ]
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            conn=mock_conn)
        assert result["total_matching"] == 5
        assert len(result["results"]) == 1

    def test_mutual_exclusion_both_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Provide cluster_ids or analysis_id, not both"):
            api.genes_in_cluster(
                cluster_ids=["gc:1"], analysis_id="ca:1", conn=mock_conn)

    def test_mutual_exclusion_neither_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Must provide cluster_ids or analysis_id"):
            api.genes_in_cluster(conn=mock_conn)

    def test_analysis_id_mode(self, mock_conn):
        summary_with_analysis = {
            **self._SUMMARY_RESULT,
            "analysis_name": "MED4 nitrogen stress clustering",
        }
        mock_conn.execute_query.side_effect = [
            [summary_with_analysis],
            [self._DETAIL_ROW],
        ]
        result = api.genes_in_cluster(
            analysis_id="ca:tolonen2006:med4:nitrogen", conn=mock_conn)
        assert result["analysis_name"] == "MED4 nitrogen stress clustering"
        assert result["total_matching"] == 5

    def test_analysis_id_summary_mode(self, mock_conn):
        summary_with_analysis = {
            **self._SUMMARY_RESULT,
            "analysis_name": "MED4 nitrogen stress clustering",
        }
        mock_conn.execute_query.side_effect = [
            [summary_with_analysis],
        ]
        result = api.genes_in_cluster(
            analysis_id="ca:tolonen2006:med4:nitrogen",
            summary=True, conn=mock_conn)
        assert result["returned"] == 0
        assert result["results"] == []
        assert result["analysis_name"] == "MED4 nitrogen stress clustering"

    def test_summary_mode_with_cluster_ids(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT],
        ]
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            summary=True, conn=mock_conn)
        assert result["returned"] == 0
        assert result["results"] == []
        assert result["analysis_name"] is None

    def test_not_found_clusters_in_envelope(self, mock_conn):
        summary_nf = {
            **self._SUMMARY_RESULT,
            "not_found_clusters": ["cluster:fake:id"],
        }
        mock_conn.execute_query.side_effect = [
            [summary_nf],
        ]
        result = api.genes_in_cluster(
            cluster_ids=["cluster:fake:id"], summary=True, conn=mock_conn)
        assert "cluster:fake:id" in result["not_found_clusters"]


class TestGeneDerivedMetrics:
    """Unit tests for api.gene_derived_metrics with mocked GraphConnection."""

    @pytest.fixture
    def mock_summary_result(self):
        return [{
            "total_matching": 9,
            "total_derived_metrics": 9,
            "genes_with_metrics": 1,
            "genes_without_metrics": 0,
            "not_found": [],
            "not_matched": [],
            "by_value_kind": [{"item": "numeric", "count": 7},
                              {"item": "boolean", "count": 1},
                              {"item": "categorical", "count": 1}],
            "by_metric_type": [{"item": "damping_ratio", "count": 1}],
            "by_metric": [{"derived_metric_id": "dm:foo",
                           "name": "Foo metric",
                           "metric_type": "damping_ratio",
                           "value_kind": "numeric",
                           "count": 1}],
            "by_compartment": [{"item": "whole_cell", "count": 7},
                               {"item": "vesicle", "count": 2}],
            "by_treatment_type": [{"item": "diel", "count": 6}],
            "by_background_factors": [{"item": "axenic", "count": 9}],
            "by_publication": [{"item": "10.1371/...", "count": 9}],
        }]

    def test_envelope_keys_present(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [mock_summary_result, []]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], conn=mock_conn, summary=True)
        for key in [
            "total_matching", "total_derived_metrics",
            "genes_with_metrics", "genes_without_metrics",
            "not_found", "not_matched",
            "by_value_kind", "by_metric_type", "by_metric",
            "by_compartment", "by_treatment_type",
            "by_background_factors", "by_publication",
            "returned", "offset", "truncated", "results",
        ]:
            assert key in data, f"missing envelope key: {key}"

    def test_summary_skips_detail_query(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        mock_conn.execute_query.return_value = mock_summary_result
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], conn=mock_conn, summary=True)
        assert mock_conn.execute_query.call_count == 1  # summary only
        assert data["results"] == []
        assert data["returned"] == 0
        assert data["truncated"] is True  # total_matching=9 > returned=0

    def test_empty_locus_tags_raises(self):
        from unittest.mock import MagicMock
        with pytest.raises(ValueError, match="locus_tags must not be empty"):
            api.gene_derived_metrics([], conn=MagicMock())

    def test_truncated_full_set(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        details = [{"locus_tag": "PMM1714"}] * 9
        mock_conn.execute_query.side_effect = [mock_summary_result, details]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(["PMM1714"], conn=mock_conn)
        assert data["returned"] == 9
        assert data["truncated"] is False  # 9 not > 0+9

    def test_truncated_partial(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        details = [{"locus_tag": "PMM1714"}] * 5
        mock_conn.execute_query.side_effect = [mock_summary_result, details]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], conn=mock_conn, limit=5)
        assert data["returned"] == 5
        assert data["truncated"] is True  # 9 > 0+5

    def test_rename_freq_applied(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [mock_summary_result, []]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], conn=mock_conn, summary=True)
        # Frequency-style breakdowns get renamed item -> domain key
        assert data["by_value_kind"][0] == {"value_kind": "numeric", "count": 7}
        assert data["by_compartment"][0] == {"compartment": "whole_cell", "count": 7}

    def test_by_metric_passthrough_no_rename(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [mock_summary_result, []]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], conn=mock_conn, summary=True)
        # by_metric is already shaped; should NOT be renamed
        assert data["by_metric"][0]["derived_metric_id"] == "dm:foo"
        assert data["by_metric"][0]["name"] == "Foo metric"

    def test_by_metric_sorted_count_desc(self):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        # Cypher returns set-iteration order, api/ must sort
        mock_summary = [{
            "total_matching": 5, "total_derived_metrics": 2,
            "genes_with_metrics": 1, "genes_without_metrics": 0,
            "not_found": [], "not_matched": [],
            "by_value_kind": [], "by_metric_type": [],
            "by_metric": [
                {"derived_metric_id": "a", "name": "A", "metric_type": "x",
                 "value_kind": "numeric", "count": 1},
                {"derived_metric_id": "b", "name": "B", "metric_type": "y",
                 "value_kind": "numeric", "count": 4},
            ],
            "by_compartment": [], "by_treatment_type": [],
            "by_background_factors": [], "by_publication": [],
        }]
        mock_conn.execute_query.side_effect = [mock_summary, []]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["X"], conn=mock_conn, summary=True)
        assert data["by_metric"][0]["count"] == 4
        assert data["by_metric"][1]["count"] == 1

    def test_not_found_plumbed_through(self):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        mock_summary = [{
            "total_matching": 0, "total_derived_metrics": 0,
            "genes_with_metrics": 0, "genes_without_metrics": 0,
            "not_found": ["PMM_FAKE"], "not_matched": [],
            "by_value_kind": [], "by_metric_type": [],
            "by_metric": [], "by_compartment": [],
            "by_treatment_type": [], "by_background_factors": [],
            "by_publication": [],
        }]
        mock_conn.execute_query.side_effect = [mock_summary, []]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM_FAKE"], conn=mock_conn, summary=True)
        assert data["not_found"] == ["PMM_FAKE"]
        assert data["not_matched"] == []


# ---------------------------------------------------------------------------
# genes_by_numeric_metric
# ---------------------------------------------------------------------------


class TestGenesByNumericMetric:
    """Unit tests for api.genes_by_numeric_metric with mocked GraphConnection."""

    @pytest.fixture
    def diag_rankable(self):
        """Diagnostics row(s) — single rankable, no p-value DM."""
        return [{
            "derived_metric_id": "dm:dr",
            "metric_type": "damping_ratio",
            "value_kind": "numeric",
            "name": "Damping ratio",
            "rankable": True,
            "has_p_value": False,
            "total_gene_count": 320,
            "organism_name": "Prochlorococcus MED4",
        }]

    @pytest.fixture
    def diag_mixed(self):
        """Diagnostics with one rankable + one non-rankable DM."""
        return [
            {"derived_metric_id": "dm:dr", "metric_type": "damping_ratio",
             "value_kind": "numeric", "name": "Damping ratio",
             "rankable": True, "has_p_value": False,
             "total_gene_count": 320,
             "organism_name": "Prochlorococcus MED4"},
            {"derived_metric_id": "dm:da", "metric_type": "diel_amplitude",
             "value_kind": "numeric", "name": "Diel amplitude",
             "rankable": False, "has_p_value": False,
             "total_gene_count": 200,
             "organism_name": "Prochlorococcus MED4"},
        ]

    @pytest.fixture
    def diag_non_rankable(self):
        return [
            {"derived_metric_id": "dm:da", "metric_type": "diel_amplitude",
             "value_kind": "numeric", "name": "Diel amplitude",
             "rankable": False, "has_p_value": False,
             "total_gene_count": 200,
             "organism_name": "Prochlorococcus MED4"},
        ]

    @pytest.fixture
    def summary_row(self):
        """Standard summary row, single DM survived."""
        return [{
            "total_matching": 32,
            "total_derived_metrics": 1,
            "total_genes": 32,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 32}],
            "by_compartment": [{"item": "whole_cell", "count": 32}],
            "by_publication": [{"item": "10.1234/foo", "count": 32}],
            "by_experiment": [{"item": "exp:1", "count": 32}],
            "by_metric": [{
                "derived_metric_id": "dm:dr",
                "name": "Damping ratio",
                "metric_type": "damping_ratio",
                "value_kind": "numeric",
                "count": 32,
            }],
            "top_categories_raw": [
                {"item": "Translation", "count": 5},
                {"item": "Carbohydrate metabolism", "count": 4},
            ],
            "genes_per_metric_max": 32,
            "genes_per_metric_median": 32.0,
        }]

    def test_envelope_keys_present(self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"],
            bucket=["top_decile"],
            conn=mock_conn,
            summary=True,
        )
        for key in [
            "total_matching", "total_derived_metrics", "total_genes",
            "by_organism", "by_compartment", "by_publication",
            "by_experiment", "by_metric", "top_categories",
            "genes_per_metric_max", "genes_per_metric_median",
            "not_found_ids", "not_matched_ids",
            "not_found_metric_types", "not_matched_metric_types",
            "not_matched_organism", "excluded_derived_metrics", "warnings",
            "returned", "offset", "truncated", "results",
        ]:
            assert key in data, f"missing envelope key: {key}"

    def test_mutual_exclusion_both_raises(self):
        with pytest.raises(ValueError, match="not both"):
            api.genes_by_numeric_metric(
                derived_metric_ids=["dm:dr"],
                metric_types=["damping_ratio"],
                conn=MagicMock(),
            )

    def test_mutual_exclusion_neither_raises(self):
        with pytest.raises(ValueError, match="must provide one of"):
            api.genes_by_numeric_metric(conn=MagicMock())

    def test_summary_skips_detail_query(self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"],
            bucket=["top_decile"],
            conn=mock_conn,
            summary=True,
        )
        assert mock_conn.execute_query.call_count == 2  # diag + summary
        assert data["results"] == []
        assert data["returned"] == 0
        assert data["truncated"] is True  # total=32 > 0

    def test_three_query_orchestration(self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        details = [{"locus_tag": f"PMM{i:04d}"} for i in range(32)]
        mock_conn.execute_query.side_effect = [
            diag_rankable, summary_row, details,
        ]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"],
            bucket=["top_decile"],
            conn=mock_conn,
        )
        # diag → summary → detail
        assert mock_conn.execute_query.call_count == 3
        assert data["returned"] == 32

    def test_all_rankable_no_exclusions(self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row, []]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"],
            bucket=["top_decile"],
            conn=mock_conn,
        )
        assert data["excluded_derived_metrics"] == []
        assert data["warnings"] == []

    def test_mixed_rankable_excludes_non_rankable(
            self, diag_mixed, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_mixed, summary_row, []]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio", "diel_amplitude"],
            bucket=["top_decile"],
            conn=mock_conn,
        )
        assert len(data["excluded_derived_metrics"]) == 1
        excl = data["excluded_derived_metrics"][0]
        assert excl["derived_metric_id"] == "dm:da"
        assert excl["rankable"] is False
        assert "bucket" in excl["reason"]
        assert len(data["warnings"]) == 1
        assert "bucket" in data["warnings"][0]

    def test_all_non_rankable_raises(self, diag_non_rankable):
        mock_conn = MagicMock()
        mock_conn.execute_query.return_value = diag_non_rankable
        with pytest.raises(ValueError, match="non-rankable"):
            api.genes_by_numeric_metric(
                metric_types=["diel_amplitude"],
                bucket=["top_decile"],
                conn=mock_conn,
            )

    def test_significant_only_all_no_pvalue_raises(self, diag_rankable):
        # diag_rankable has has_p_value=False
        mock_conn = MagicMock()
        mock_conn.execute_query.return_value = diag_rankable
        with pytest.raises(ValueError, match="has_p_value=False"):
            api.genes_by_numeric_metric(
                metric_types=["damping_ratio"],
                significant_only=True,
                conn=mock_conn,
            )

    def test_max_adjusted_p_value_all_no_pvalue_raises(self, diag_rankable):
        mock_conn = MagicMock()
        mock_conn.execute_query.return_value = diag_rankable
        with pytest.raises(ValueError, match="has_p_value=False"):
            api.genes_by_numeric_metric(
                metric_types=["damping_ratio"],
                max_adjusted_p_value=0.05,
                conn=mock_conn,
            )

    def test_not_found_ids_plumbed(self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row, []]
        data = api.genes_by_numeric_metric(
            derived_metric_ids=["dm:dr", "dm:fake"],
            conn=mock_conn,
        )
        assert data["not_found_ids"] == ["dm:fake"]

    def test_not_found_metric_types_plumbed(self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row, []]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio", "no_such_type"],
            conn=mock_conn,
        )
        assert data["not_found_metric_types"] == ["no_such_type"]

    def test_not_matched_organism_set_when_no_match(
            self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row, []]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"],
            organism="Alteromonas",  # no match in by_organism
            conn=mock_conn,
        )
        assert data["not_matched_organism"] == "Alteromonas"

    def test_not_matched_organism_none_when_match(
            self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row, []]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"],
            organism="Prochlorococcus MED4",
            conn=mock_conn,
        )
        assert data["not_matched_organism"] is None

    def test_top_categories_capped_at_5(self, diag_rankable):
        # 7 categories in raw — only top 5 should survive
        big_summary = [{
            "total_matching": 50, "total_derived_metrics": 1, "total_genes": 50,
            "by_organism": [], "by_compartment": [], "by_publication": [],
            "by_experiment": [],
            "by_metric": [{
                "derived_metric_id": "dm:dr", "name": "Damping ratio",
                "metric_type": "damping_ratio", "value_kind": "numeric",
                "count": 50,
            }],
            "top_categories_raw": [
                {"item": f"cat{i}", "count": 10 - i} for i in range(7)
            ],
            "genes_per_metric_max": 50, "genes_per_metric_median": 50.0,
        }]
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, big_summary, []]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"], conn=mock_conn,
        )
        assert len(data["top_categories"]) == 5
        # rename + sorted desc by count
        assert data["top_categories"][0] == {"gene_category": "cat0", "count": 10}

    def test_by_metric_sorted_count_desc(self, diag_rankable):
        # by_metric out of order → api/ must sort
        unsorted_summary = [{
            "total_matching": 9, "total_derived_metrics": 2, "total_genes": 9,
            "by_organism": [], "by_compartment": [], "by_publication": [],
            "by_experiment": [],
            "by_metric": [
                {"derived_metric_id": "a", "name": "A", "metric_type": "x",
                 "value_kind": "numeric", "count": 2},
                {"derived_metric_id": "b", "name": "B", "metric_type": "y",
                 "value_kind": "numeric", "count": 7},
            ],
            "top_categories_raw": [],
            "genes_per_metric_max": 7, "genes_per_metric_median": 4.5,
        }]
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_rankable, unsorted_summary, [],
        ]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"], conn=mock_conn,
        )
        assert data["by_metric"][0]["count"] == 7
        assert data["by_metric"][1]["count"] == 2

    def test_freq_lists_renamed(self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row, []]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"], conn=mock_conn,
        )
        assert data["by_organism"][0] == {
            "organism_name": "Prochlorococcus MED4", "count": 32,
        }
        assert data["by_compartment"][0] == {
            "compartment": "whole_cell", "count": 32,
        }
        assert data["by_publication"][0] == {
            "publication_doi": "10.1234/foo", "count": 32,
        }
        assert data["by_experiment"][0] == {
            "experiment_id": "exp:1", "count": 32,
        }

    def test_truncated_full_set(self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        details = [{"locus_tag": f"PMM{i}"} for i in range(32)]
        mock_conn.execute_query.side_effect = [
            diag_rankable, summary_row, details,
        ]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"], conn=mock_conn,
        )
        assert data["returned"] == 32
        assert data["truncated"] is False  # 32 not > 0+32

    def test_truncated_partial(self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        details = [{"locus_tag": f"PMM{i}"} for i in range(10)]
        mock_conn.execute_query.side_effect = [
            diag_rankable, summary_row, details,
        ]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"],
            limit=10, conn=mock_conn,
        )
        assert data["returned"] == 10
        assert data["truncated"] is True  # 32 > 0+10

    def test_truncated_summary_mode(self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"],
            summary=True, conn=mock_conn,
        )
        assert data["returned"] == 0
        assert data["truncated"] is True  # 32 > 0+0


# ---------------------------------------------------------------------------
# genes_by_boolean_metric
# ---------------------------------------------------------------------------
class TestGenesByBooleanMetric:
    """Unit tests for api.genes_by_boolean_metric with mocked GraphConnection."""

    @pytest.fixture
    def diag_boolean(self):
        """Single boolean DM survives diagnostics."""
        return [{
            "derived_metric_id": "dm:vp_med4",
            "metric_type": "vesicle_proteome_member",
            "value_kind": "boolean",
            "name": "Vesicle proteome member (MED4)",
            "total_gene_count": 32,
            "organism_name": "Prochlorococcus MED4",
        }]

    @pytest.fixture
    def diag_two_dms(self):
        """Two boolean DMs (cross-organism vesicle proteome)."""
        return [
            {"derived_metric_id": "dm:vp_med4",
             "metric_type": "vesicle_proteome_member",
             "value_kind": "boolean",
             "name": "Vesicle proteome member (MED4)",
             "total_gene_count": 32,
             "organism_name": "Prochlorococcus MED4"},
            {"derived_metric_id": "dm:vp_mit9313",
             "metric_type": "vesicle_proteome_member",
             "value_kind": "boolean",
             "name": "Vesicle proteome member (MIT9313)",
             "total_gene_count": 26,
             "organism_name": "Prochlorococcus MIT9313"},
        ]

    @pytest.fixture
    def summary_row(self):
        """Standard summary row, single DM survived."""
        return [{
            "total_matching": 32,
            "total_derived_metrics": 1,
            "total_genes": 32,
            "by_organism": [
                {"item": "Prochlorococcus MED4", "count": 32},
            ],
            "by_compartment": [{"item": "vesicle", "count": 32}],
            "by_publication": [{"item": "10.1038/foo", "count": 32}],
            "by_experiment": [{"item": "exp:vesicle_med4", "count": 32}],
            "by_value": [{"item": "true", "count": 32}],
            "by_metric": [{
                "derived_metric_id": "dm:vp_med4",
                "name": "Vesicle proteome member (MED4)",
                "metric_type": "vesicle_proteome_member",
                "value_kind": "boolean",
                "count": 32,
                "true_count": 32,
                "false_count": 0,
                "dm_total_gene_count": 32,
                "dm_true_count": 32,
                "dm_false_count": 0,
            }],
            "top_categories_raw": [
                {"item": "Cellular processes", "count": 5},
            ],
            "genes_per_metric_max": 32,
            "genes_per_metric_median": 32.0,
        }]

    def test_returns_dict(self, diag_boolean, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_boolean, summary_row, []]
        data = api.genes_by_boolean_metric(
            metric_types=["vesicle_proteome_member"], conn=mock_conn,
        )
        assert isinstance(data, dict)
        for key in [
            "total_matching", "total_derived_metrics", "total_genes",
            "by_organism", "by_compartment", "by_publication",
            "by_experiment", "by_value", "by_metric", "top_categories",
            "genes_per_metric_max", "genes_per_metric_median",
            "not_found_ids", "not_matched_ids",
            "not_found_metric_types", "not_matched_metric_types",
            "not_matched_organism", "excluded_derived_metrics", "warnings",
            "returned", "offset", "truncated", "results",
        ]:
            assert key in data, f"missing envelope key: {key}"

    def test_mutex_selection_raises(self):
        with pytest.raises(ValueError, match="not both"):
            api.genes_by_boolean_metric(
                derived_metric_ids=["dm:vp_med4"],
                metric_types=["vesicle_proteome_member"],
                conn=MagicMock(),
            )

    def test_neither_selection_raises(self):
        with pytest.raises(ValueError, match="must provide one of"):
            api.genes_by_boolean_metric(conn=MagicMock())

    def test_kind_mismatch_in_not_found_ids(self, summary_row):
        # Pass a numeric DM id; diagnostics' value_kind='boolean' filter
        # gives zero rows → id surfaces in not_found_ids and we
        # short-circuit before summary/detail.
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [[]]  # diagnostics empty
        data = api.genes_by_boolean_metric(
            derived_metric_ids=["dm:numeric_dr"], conn=mock_conn,
        )
        assert mock_conn.execute_query.call_count == 1  # short-circuit
        assert data["not_found_ids"] == ["dm:numeric_dr"]
        assert data["total_matching"] == 0
        assert data["results"] == []

    def test_summary_true_skips_detail_query(self, diag_boolean, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_boolean, summary_row]
        data = api.genes_by_boolean_metric(
            metric_types=["vesicle_proteome_member"],
            summary=True, conn=mock_conn,
        )
        # diag + summary only — no detail
        assert mock_conn.execute_query.call_count == 2
        assert data["results"] == []
        assert data["returned"] == 0
        assert data["truncated"] is True  # total=32 > 0+0

    def test_excluded_derived_metrics_always_empty_list(
            self, diag_two_dms, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_two_dms, summary_row, []]
        data = api.genes_by_boolean_metric(
            metric_types=["vesicle_proteome_member"], conn=mock_conn,
        )
        assert data["excluded_derived_metrics"] == []

    def test_warnings_always_empty_list(
            self, diag_two_dms, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_two_dms, summary_row, []]
        data = api.genes_by_boolean_metric(
            metric_types=["vesicle_proteome_member"], conn=mock_conn,
        )
        assert data["warnings"] == []

    def test_not_found_plumbing(self, diag_boolean, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_boolean, summary_row, []]
        data = api.genes_by_boolean_metric(
            derived_metric_ids=["dm:vp_med4", "dm:fake"], conn=mock_conn,
        )
        assert data["not_found_ids"] == ["dm:fake"]

    def test_not_matched_plumbing(self, diag_two_dms):
        # Two DMs survive diagnostics, but only one contributes rows
        # post edge filter → the other is in not_matched_ids.
        summary_one_dm = [{
            "total_matching": 32, "total_derived_metrics": 1,
            "total_genes": 32,
            "by_organism": [], "by_compartment": [], "by_publication": [],
            "by_experiment": [], "by_value": [],
            "by_metric": [{
                "derived_metric_id": "dm:vp_med4",
                "name": "Vesicle proteome member (MED4)",
                "metric_type": "vesicle_proteome_member",
                "value_kind": "boolean",
                "count": 32, "true_count": 32, "false_count": 0,
                "dm_total_gene_count": 32, "dm_true_count": 32,
                "dm_false_count": 0,
            }],
            "top_categories_raw": [],
            "genes_per_metric_max": 32, "genes_per_metric_median": 32.0,
        }]
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_two_dms, summary_one_dm, []]
        data = api.genes_by_boolean_metric(
            derived_metric_ids=["dm:vp_med4", "dm:vp_mit9313"],
            conn=mock_conn,
        )
        assert data["not_matched_ids"] == ["dm:vp_mit9313"]

    def test_passes_flag_to_summary_and_detail(
            self, diag_boolean, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_boolean, summary_row, []]
        api.genes_by_boolean_metric(
            metric_types=["vesicle_proteome_member"],
            flag=True, conn=mock_conn,
        )
        # 3 calls: diag, summary, detail. flag → flag_str='true' on
        # summary + detail.
        assert mock_conn.execute_query.call_count == 3
        sum_kwargs = mock_conn.execute_query.call_args_list[1].kwargs
        det_kwargs = mock_conn.execute_query.call_args_list[2].kwargs
        assert sum_kwargs.get("flag_str") == "true"
        assert det_kwargs.get("flag_str") == "true"

    def test_creates_conn_when_none(self, monkeypatch):
        # Patch GraphConnection so no real Neo4j call happens.
        instances = []

        class FakeConn:
            def __init__(self, *args, **kwargs):
                instances.append(self)
                self.execute_query = MagicMock(return_value=[])

        monkeypatch.setattr(
            "multiomics_explorer.api.functions.GraphConnection", FakeConn)
        # diagnostics empty → short-circuit before summary/detail.
        data = api.genes_by_boolean_metric(
            metric_types=["vesicle_proteome_member"],
        )
        assert instances, "GraphConnection should have been instantiated"
        assert data["total_matching"] == 0

    def test_importable_from_package(self):
        from multiomics_explorer import (
            genes_by_boolean_metric as pkg_fn,
        )
        from multiomics_explorer.api import (
            genes_by_boolean_metric as api_fn,
        )
        assert pkg_fn is api_fn is api.genes_by_boolean_metric


# ---------------------------------------------------------------------------
# genes_by_categorical_metric
# ---------------------------------------------------------------------------
class TestGenesByCategoricalMetric:
    """Unit tests for api.genes_by_categorical_metric with mocked GraphConnection."""

    @pytest.fixture
    def diag_categorical(self):
        """Single categorical DM survives diagnostics, with allowed_categories."""
        return [{
            "derived_metric_id": "dm:psortb_med4",
            "metric_type": "predicted_subcellular_localization",
            "value_kind": "categorical",
            "name": "PSORTb subcellular localization (MED4)",
            "total_gene_count": 32,
            "organism_name": "Prochlorococcus MED4",
            "allowed_categories": [
                "Cytoplasmic", "Cytoplasmic Membrane",
                "Periplasmic", "Outer Membrane", "Extracellular", "Unknown",
            ],
        }]

    @pytest.fixture
    def diag_two_dms(self):
        """Two categorical DMs (PSORTb cross-organism)."""
        return [
            {"derived_metric_id": "dm:psortb_med4",
             "metric_type": "predicted_subcellular_localization",
             "value_kind": "categorical",
             "name": "PSORTb subcellular localization (MED4)",
             "total_gene_count": 32,
             "organism_name": "Prochlorococcus MED4",
             "allowed_categories": [
                 "Cytoplasmic", "Cytoplasmic Membrane",
                 "Periplasmic", "Outer Membrane",
                 "Extracellular", "Unknown",
             ]},
            {"derived_metric_id": "dm:psortb_mit9313",
             "metric_type": "predicted_subcellular_localization",
             "value_kind": "categorical",
             "name": "PSORTb subcellular localization (MIT9313)",
             "total_gene_count": 26,
             "organism_name": "Prochlorococcus MIT9313",
             "allowed_categories": [
                 "Cytoplasmic", "Cytoplasmic Membrane",
                 "Periplasmic", "Outer Membrane",
                 "Extracellular", "Unknown",
             ]},
        ]

    @pytest.fixture
    def summary_row(self):
        """Standard summary row, single DM survived. by_metric carries
        nested by_category / dm_by_category in raw {item, count} shape
        (mirrors apoc.coll.frequencies output)."""
        return [{
            "total_matching": 8,
            "total_derived_metrics": 1,
            "total_genes": 8,
            "by_organism": [
                {"item": "Prochlorococcus MED4", "count": 8},
            ],
            "by_compartment": [{"item": "vesicle", "count": 8}],
            "by_publication": [{"item": "10.1038/foo", "count": 8}],
            "by_experiment": [{"item": "exp:psortb_med4", "count": 8}],
            "by_category": [
                {"item": "Outer Membrane", "count": 5},
                {"item": "Periplasmic", "count": 3},
            ],
            "by_metric": [{
                "derived_metric_id": "dm:psortb_med4",
                "name": "PSORTb subcellular localization (MED4)",
                "metric_type": "predicted_subcellular_localization",
                "value_kind": "categorical",
                "count": 8,
                "by_category": [
                    {"item": "Outer Membrane", "count": 5},
                    {"item": "Periplasmic", "count": 3},
                ],
                "allowed_categories": [
                    "Cytoplasmic", "Cytoplasmic Membrane",
                    "Periplasmic", "Outer Membrane",
                    "Extracellular", "Unknown",
                ],
                "dm_total_gene_count": 32,
                "dm_by_category": [
                    {"item": "Cytoplasmic", "count": 11},
                    {"item": "Cytoplasmic Membrane", "count": 6},
                    {"item": "Outer Membrane", "count": 5},
                    {"item": "Periplasmic", "count": 3},
                    {"item": "Unknown", "count": 7},
                ],
            }],
            "top_categories_raw": [
                {"item": "Cellular processes", "count": 5},
            ],
            "genes_per_metric_max": 8,
            "genes_per_metric_median": 8.0,
        }]

    def test_returns_dict(self, diag_categorical, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_categorical, summary_row, [],
        ]
        data = api.genes_by_categorical_metric(
            metric_types=["predicted_subcellular_localization"],
            categories=["Outer Membrane", "Periplasmic"],
            conn=mock_conn,
        )
        assert isinstance(data, dict)
        for key in [
            "total_matching", "total_derived_metrics", "total_genes",
            "by_organism", "by_compartment", "by_publication",
            "by_experiment", "by_category", "by_metric", "top_categories",
            "genes_per_metric_max", "genes_per_metric_median",
            "not_found_ids", "not_matched_ids",
            "not_found_metric_types", "not_matched_metric_types",
            "not_matched_organism", "excluded_derived_metrics", "warnings",
            "returned", "offset", "truncated", "results",
        ]:
            assert key in data, f"missing envelope key: {key}"

    def test_mutex_selection_raises(self):
        with pytest.raises(ValueError, match="not both"):
            api.genes_by_categorical_metric(
                derived_metric_ids=["dm:psortb_med4"],
                metric_types=["predicted_subcellular_localization"],
                conn=MagicMock(),
            )

    def test_neither_selection_raises(self):
        with pytest.raises(ValueError, match="must provide one of"):
            api.genes_by_categorical_metric(conn=MagicMock())

    def test_kind_mismatch_in_not_found_ids(self):
        # Pass a numeric / boolean DM id; diagnostics' value_kind='categorical'
        # filter gives zero rows → id surfaces in not_found_ids and we
        # short-circuit before summary/detail.
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [[]]  # diagnostics empty
        data = api.genes_by_categorical_metric(
            derived_metric_ids=["dm:vp_med4"], conn=mock_conn,
        )
        assert mock_conn.execute_query.call_count == 1  # short-circuit
        assert data["not_found_ids"] == ["dm:vp_med4"]
        assert data["total_matching"] == 0
        assert data["results"] == []

    def test_summary_true_skips_detail_query(
            self, diag_categorical, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_categorical, summary_row,
        ]
        data = api.genes_by_categorical_metric(
            metric_types=["predicted_subcellular_localization"],
            summary=True, conn=mock_conn,
        )
        # diag + summary only — no detail
        assert mock_conn.execute_query.call_count == 2
        assert data["results"] == []
        assert data["returned"] == 0
        assert data["truncated"] is True  # total=8 > 0+0

    def test_excluded_derived_metrics_always_empty_list(
            self, diag_two_dms, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_two_dms, summary_row, []]
        data = api.genes_by_categorical_metric(
            metric_types=["predicted_subcellular_localization"],
            conn=mock_conn,
        )
        assert data["excluded_derived_metrics"] == []

    def test_warnings_always_empty_list(self, diag_two_dms, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_two_dms, summary_row, []]
        data = api.genes_by_categorical_metric(
            metric_types=["predicted_subcellular_localization"],
            conn=mock_conn,
        )
        assert data["warnings"] == []

    def test_not_found_plumbing(self, diag_categorical, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_categorical, summary_row, [],
        ]
        data = api.genes_by_categorical_metric(
            derived_metric_ids=["dm:psortb_med4", "dm:fake"],
            conn=mock_conn,
        )
        assert data["not_found_ids"] == ["dm:fake"]

    def test_not_matched_plumbing(self, diag_two_dms, summary_row):
        # Two DMs survive diagnostics; summary_row contributes only one
        # → the other is not_matched.
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_two_dms, summary_row, []]
        data = api.genes_by_categorical_metric(
            derived_metric_ids=["dm:psortb_med4", "dm:psortb_mit9313"],
            conn=mock_conn,
        )
        assert data["not_matched_ids"] == ["dm:psortb_mit9313"]

    def test_categories_subset_validation_raises(self, diag_categorical):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_categorical]
        with pytest.raises(ValueError, match="allowed_categories"):
            api.genes_by_categorical_metric(
                metric_types=["predicted_subcellular_localization"],
                categories=["nonsense"],
                conn=mock_conn,
            )

    def test_categories_subset_validation_message_lists_allowed_union(
            self, diag_categorical):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_categorical]
        with pytest.raises(ValueError) as excinfo:
            api.genes_by_categorical_metric(
                metric_types=["predicted_subcellular_localization"],
                categories=["Outer Membrane", "Foo"],
                conn=mock_conn,
            )
        msg = str(excinfo.value)
        # Mentions the unknown plus the allowed union
        assert "Foo" in msg
        for allowed in [
            "Cytoplasmic", "Cytoplasmic Membrane",
            "Periplasmic", "Outer Membrane",
            "Extracellular", "Unknown",
        ]:
            assert allowed in msg

    def test_passes_categories_to_summary_and_detail(
            self, diag_categorical, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_categorical, summary_row, [],
        ]
        api.genes_by_categorical_metric(
            metric_types=["predicted_subcellular_localization"],
            categories=["Outer Membrane", "Periplasmic"],
            conn=mock_conn,
        )
        # 3 calls: diag, summary, detail
        assert mock_conn.execute_query.call_count == 3
        sum_kwargs = mock_conn.execute_query.call_args_list[1].kwargs
        det_kwargs = mock_conn.execute_query.call_args_list[2].kwargs
        assert sum_kwargs.get("categories") == ["Outer Membrane", "Periplasmic"]
        assert det_kwargs.get("categories") == ["Outer Membrane", "Periplasmic"]

    def test_by_category_renamed_item_to_category(
            self, diag_categorical, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_categorical, summary_row, [],
        ]
        data = api.genes_by_categorical_metric(
            metric_types=["predicted_subcellular_localization"],
            conn=mock_conn,
        )
        # Envelope-level by_category renamed
        assert data["by_category"][0].keys() == {"category", "count"}
        # Nested by_metric[*].by_category renamed
        nested = data["by_metric"][0]["by_category"]
        assert nested[0].keys() == {"category", "count"}
        # Nested by_metric[*].dm_by_category renamed
        nested_full = data["by_metric"][0]["dm_by_category"]
        assert nested_full[0].keys() == {"category", "count"}

    def test_creates_conn_when_none(self, monkeypatch):
        instances = []

        class FakeConn:
            def __init__(self, *args, **kwargs):
                instances.append(self)
                self.execute_query = MagicMock(return_value=[])

        monkeypatch.setattr(
            "multiomics_explorer.api.functions.GraphConnection", FakeConn)
        # diagnostics empty → short-circuit before summary/detail.
        data = api.genes_by_categorical_metric(
            metric_types=["predicted_subcellular_localization"],
        )
        assert instances, "GraphConnection should have been instantiated"
        assert data["total_matching"] == 0

    def test_importable_from_package(self):
        from multiomics_explorer import (
            genes_by_categorical_metric as pkg_fn,
        )
        from multiomics_explorer.api import (
            genes_by_categorical_metric as api_fn,
        )
        assert pkg_fn is api_fn is api.genes_by_categorical_metric


# ---------------------------------------------------------------------------
# gene_ontology_terms batching fix
# ---------------------------------------------------------------------------

from multiomics_explorer.api.functions import _chunk_locus_tags


@patch("multiomics_explorer.api.functions._validate_organism_inputs", return_value="Prochlorococcus MED4")
class TestGeneOntologyTermsChunking:
    def test_single_chunk_when_under_threshold(self, _mock_validate, monkeypatch):
        monkeypatch.setenv("MULTIOMICS_KG_BATCH_SIZE", "500")
        assert _chunk_locus_tags(["a", "b", "c"]) == [["a", "b", "c"]]
        assert _chunk_locus_tags([f"x{i}" for i in range(500)]) == [
            [f"x{i}" for i in range(500)]
        ]

    def test_two_chunks_at_501(self, _mock_validate, monkeypatch):
        monkeypatch.setenv("MULTIOMICS_KG_BATCH_SIZE", "500")
        tags = [f"x{i}" for i in range(501)]
        chunks = _chunk_locus_tags(tags)
        assert len(chunks) == 2
        assert len(chunks[0]) == 500
        assert len(chunks[1]) == 1

    def test_chunks_on_threshold(self, _mock_validate, monkeypatch):
        """N=1001 genes, batch=500 → 3 chunks × 10 ontologies = 30 summary calls."""
        monkeypatch.setenv("MULTIOMICS_KG_BATCH_SIZE", "500")
        N = 1001
        locus_tags = [f"PMM{i:04d}" for i in range(N)]
        exist_rows = [{"lt": lt, "found": True} for lt in locus_tags]
        summary_row = [{"gene_count": 0, "term_count": 0,
                        "by_term": [], "gene_term_counts": []}]

        conn = MagicMock()

        def side(cypher, **params):
            if "g IS NOT NULL AS found" in cypher:
                # existence check — return found=True for each tag in chunk
                return exist_rows[:len(params["locus_tags"])]
            if "gene_count" in cypher:
                return summary_row
            return []

        conn.execute_query.side_effect = side

        api.gene_ontology_terms(locus_tags=locus_tags, organism="MED4", summary=True, conn=conn)

        summary_calls = [
            c for c in conn.execute_query.call_args_list
            if "gene_count" in (c.args[0] if c.args else "")
        ]
        # Without chunking: 10 calls (one per ontology).
        # With chunking into 3 chunks: 30 calls.
        assert len(summary_calls) >= 27, (
            f"expected chunked summary calls, got {len(summary_calls)}"
        )


# ---------------------------------------------------------------------------
# ontology_landscape
# ---------------------------------------------------------------------------

from multiomics_explorer.kg.constants import ALL_ONTOLOGIES, GO_ONTOLOGIES
from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG


class TestOntologyLandscape:
    def _mock_conn(self, gene_count: int, per_ont_rows: dict):
        """Build a mock conn whose execute_query returns results keyed by
        the 'org' / 'experiment_ids' param dispatch implied by the Cypher.
        """
        conn = MagicMock()

        def run(cypher, **params):
            if "RETURN collect(DISTINCT e.organism_name)" in cypher:
                return [{"organisms": ["Prochlorococcus MED4"]}]
            if "count(g) AS total_genes" in cypher:
                return [{"total_genes": gene_count}]
            # Match one of the 9 ontology landscape queries
            for ont, rows in per_ont_rows.items():
                cfg = ONTOLOGY_CONFIG[ont]
                if cfg["gene_rel"] in cypher and f":{cfg['label']}" in cypher:
                    return rows
            raise AssertionError(f"no mock for cypher:\n{cypher}")

        conn.execute_query.side_effect = run
        return conn

    def _mock_conn_with_experiments(
        self, gene_count, per_ont_stats, per_ont_expcov, exp_check_rows,
    ):
        conn = MagicMock()

        def run(cypher, **params):
            if "RETURN collect(DISTINCT e.organism_name)" in cypher:
                return [{"organisms": ["Prochlorococcus MED4"]}]
            if "count(g) AS total_genes" in cypher:
                return [{"total_genes": gene_count}]
            if "OPTIONAL MATCH (e:Experiment {id: eid})" in cypher:
                return exp_check_rows
            for ont, rows in per_ont_expcov.items():
                cfg = ONTOLOGY_CONFIG[ont]
                if ("Changes_expression_of" in cypher and
                        cfg["gene_rel"] in cypher):
                    return rows
            for ont, rows in per_ont_stats.items():
                cfg = ONTOLOGY_CONFIG[ont]
                if cfg["gene_rel"] in cypher and f":{cfg['label']}" in cypher:
                    return rows
            raise AssertionError(f"no mock for cypher:\n{cypher[:200]}")

        conn.execute_query.side_effect = run
        return conn

    def test_genome_branch_all_ontologies(self):
        per_ont_rows = {
            ont: [
                {
                    "level": 0, "n_terms_with_genes": 1,
                    "n_genes_at_level": 1000,
                    "min_genes_per_term": 1000, "q1_genes_per_term": 1000.0,
                    "median_genes_per_term": 1000.0, "q3_genes_per_term": 1000.0,
                    "max_genes_per_term": 1000, "n_best_effort": 0,
                },
            ]
            for ont in ALL_ONTOLOGIES
        }
        conn = self._mock_conn(gene_count=1976, per_ont_rows=per_ont_rows)
        result = api.ontology_landscape(
            organism="MED4", conn=conn,
        )
        # Envelope
        assert result["organism_name"] == "Prochlorococcus MED4"
        assert result["organism_gene_count"] == 1976
        assert result["n_ontologies"] == len(ALL_ONTOLOGIES)
        assert result["not_found"] == []
        assert result["not_matched"] == []
        assert "total_matching" in result
        assert "total_rows" not in result
        # Results
        assert len(result["results"]) == len(ALL_ONTOLOGIES)
        for row in result["results"]:
            assert row["ontology_type"] in ALL_ONTOLOGIES
            assert row["level"] == 0
            assert row["genome_coverage"] == pytest.approx(1000 / 1976)

    def test_ranking_and_by_ontology(self):
        # tigr_role L0: cov=1765/1976, median=9 → sf=1.0 → rank 1
        # cyanorak_role L1: cov=1491/1976, median=9 → sf=1.0 → rank 2
        # go_bp L0: cov=1122/1976, median=1122 → sf≈0.045 → low rank
        per_ont_rows = {ont: [] for ont in ALL_ONTOLOGIES}
        per_ont_rows["tigr_role"] = [{
            "level": 0, "n_terms_with_genes": 106,
            "n_genes_at_level": 1765,
            "min_genes_per_term": 1, "q1_genes_per_term": 3.0,
            "median_genes_per_term": 9.0, "q3_genes_per_term": 17.0,
            "max_genes_per_term": 451, "n_best_effort": 0,
        }]
        per_ont_rows["cyanorak_role"] = [{
            "level": 1, "n_terms_with_genes": 110,
            "n_genes_at_level": 1491,
            "min_genes_per_term": 1, "q1_genes_per_term": 3.0,
            "median_genes_per_term": 9.0, "q3_genes_per_term": 16.0,
            "max_genes_per_term": 340, "n_best_effort": 0,
        }]
        per_ont_rows["go_bp"] = [{
            "level": 0, "n_terms_with_genes": 1,
            "n_genes_at_level": 1122,
            "min_genes_per_term": 1122, "q1_genes_per_term": 1122.0,
            "median_genes_per_term": 1122.0, "q3_genes_per_term": 1122.0,
            "max_genes_per_term": 1122, "n_best_effort": 0,
        }]
        conn = self._mock_conn(gene_count=1976, per_ont_rows=per_ont_rows)
        result = api.ontology_landscape(organism="MED4", conn=conn)
        # Rank 1 = tigr_role
        top = result["results"][0]
        assert top["ontology_type"] == "tigr_role"
        assert top["relevance_rank"] == 1
        # Rank 2 = cyanorak_role
        assert result["results"][1]["ontology_type"] == "cyanorak_role"
        assert result["results"][1]["relevance_rank"] == 2
        # by_ontology summary
        assert "tigr_role" in result["by_ontology"]
        tigr_summary = result["by_ontology"]["tigr_role"]
        assert tigr_summary["best_level"] == 0
        assert tigr_summary["best_relevance_rank"] == 1
        assert tigr_summary["n_levels"] == 1
        assert tigr_summary["best_genome_coverage"] == pytest.approx(1765 / 1976)

    def test_experiment_branch_not_found_and_not_matched(self):
        per_ont_stats = {
            "cyanorak_role": [{
                "level": 1, "n_terms_with_genes": 110,
                "n_genes_at_level": 1491,
                "min_genes_per_term": 1, "q1_genes_per_term": 3.0,
                "median_genes_per_term": 9.0, "q3_genes_per_term": 16.0,
                "max_genes_per_term": 340, "n_best_effort": 0,
            }],
        }
        per_ont_expcov = {
            "cyanorak_role": [
                {"eid": "EXP_A", "n_total": 100, "level": 1, "n_at_level": 80},
                # No row for EXP_B at level 1 — zero-fill expected
            ],
        }
        exp_check_rows = [
            {"eid": "EXP_A", "exists": True,
             "exp_organism": "Prochlorococcus MED4"},
            {"eid": "EXP_B", "exists": True,
             "exp_organism": "Prochlorococcus MED4"},
            {"eid": "EXP_MISSING", "exists": False, "exp_organism": ""},
            {"eid": "EXP_WRONG_ORG", "exists": True,
             "exp_organism": "Alteromonas macleodii HOT1A3"},
        ]
        conn = self._mock_conn_with_experiments(
            gene_count=1976,
            per_ont_stats=per_ont_stats,
            per_ont_expcov=per_ont_expcov,
            exp_check_rows=exp_check_rows,
        )
        result = api.ontology_landscape(
            organism="MED4", ontology="cyanorak_role",
            experiment_ids=["EXP_A", "EXP_B", "EXP_MISSING", "EXP_WRONG_ORG"],
            conn=conn,
        )
        assert result["not_found"] == ["EXP_MISSING"]
        assert result["not_matched"] == ["EXP_WRONG_ORG"]
        # Only one landscape row (cyanorak L1)
        assert len(result["results"]) == 1
        row = result["results"][0]
        # Zero-fill: EXP_A has 80/100 = 0.8, EXP_B had no row → 0.0
        # min=0.0, max=0.8, median=0.4
        assert row["min_exp_coverage"] == pytest.approx(0.0)
        assert row["max_exp_coverage"] == pytest.approx(0.8)
        assert row["median_exp_coverage"] == pytest.approx(0.4)
        assert row["n_experiments_with_coverage"] == 1

    def test_summary_mode_returns_empty_results(self):
        per_ont_rows = {
            ont: [
                {
                    "level": 0, "n_terms_with_genes": 50,
                    "n_genes_at_level": 900,
                    "min_genes_per_term": 5, "q1_genes_per_term": 10.0,
                    "median_genes_per_term": 15.0, "q3_genes_per_term": 30.0,
                    "max_genes_per_term": 100, "n_best_effort": 0,
                },
            ]
            for ont in ALL_ONTOLOGIES
        }
        conn = self._mock_conn(gene_count=1976, per_ont_rows=per_ont_rows)
        result = api.ontology_landscape(organism="MED4", summary=True, conn=conn)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["total_matching"] == len(ALL_ONTOLOGIES)
        assert result["truncated"] is True

    def test_verbose_threads_example_terms(self):
        per_ont_rows = {
            ont: [
                {
                    "level": 0, "n_terms_with_genes": 1,
                    "n_genes_at_level": 500,
                    "min_genes_per_term": 500, "q1_genes_per_term": 500.0,
                    "median_genes_per_term": 500.0, "q3_genes_per_term": 500.0,
                    "max_genes_per_term": 500, "n_best_effort": 0,
                    "example_terms": [
                        {"term_id": "T001", "name": "Alpha process", "n_genes": 500}
                    ],
                },
            ]
            for ont in ALL_ONTOLOGIES
        }
        conn = self._mock_conn(gene_count=1976, per_ont_rows=per_ont_rows)
        result = api.ontology_landscape(organism="MED4", verbose=True, conn=conn)
        for row in result["results"]:
            assert "example_terms" in row
            assert isinstance(row["example_terms"], list)

    def test_truncated_respects_offset(self):
        """truncated must be total_matching > offset + len(results), not > len(results)."""
        per_ont_rows = {
            ont: [
                {
                    "level": 0, "n_terms_with_genes": 50,
                    "n_genes_at_level": 900,
                    "min_genes_per_term": 5, "q1_genes_per_term": 10.0,
                    "median_genes_per_term": 15.0, "q3_genes_per_term": 30.0,
                    "max_genes_per_term": 100, "n_best_effort": 0,
                },
            ]
            for ont in ALL_ONTOLOGIES
        }
        conn = self._mock_conn(gene_count=1976, per_ont_rows=per_ont_rows)
        total = len(ALL_ONTOLOGIES)  # e.g. 9
        # Fetch the last page: offset = total - 2, limit = 5 → 2 rows returned
        offset = total - 2
        result = api.ontology_landscape(
            organism="MED4", offset=offset, limit=5, conn=conn,
        )
        assert result["returned"] == 2
        assert result["offset"] == offset
        assert result["total_matching"] == total
        # No more rows after this page → truncated must be False
        assert result["truncated"] is False


class TestPathwayEnrichment:
    """Input validation + orchestration for api.pathway_enrichment."""

    def test_importable_from_api(self):
        from multiomics_explorer.api import pathway_enrichment
        assert pathway_enrichment is not None

    def test_invalid_ontology_raises(self):
        from multiomics_explorer.api import pathway_enrichment
        with pytest.raises(ValueError, match="ontology"):
            pathway_enrichment(
                organism="MED4", experiment_ids=["exp1"],
                ontology="not_a_real_ontology", level=1,
            )

    def test_missing_level_and_term_ids_raises(self):
        from multiomics_explorer.api import pathway_enrichment
        with pytest.raises(ValueError, match="level|term_ids"):
            pathway_enrichment(
                organism="MED4", experiment_ids=["exp1"],
                ontology="cyanorak_role",
            )

    def test_bad_direction_raises(self):
        from multiomics_explorer.api import pathway_enrichment
        with pytest.raises(ValueError, match="direction"):
            pathway_enrichment(
                organism="MED4", experiment_ids=["exp1"],
                ontology="cyanorak_role", level=1,
                direction="sideways",
            )

    def test_bad_background_string_raises(self):
        from multiomics_explorer.api import pathway_enrichment
        with pytest.raises(ValueError, match="background"):
            pathway_enrichment(
                organism="MED4", experiment_ids=["exp1"],
                ontology="cyanorak_role", level=1,
                background="genome",
            )

    def test_max_less_than_min_raises(self):
        from multiomics_explorer.api import pathway_enrichment
        with pytest.raises(ValueError, match="max_gene_set_size"):
            pathway_enrichment(
                organism="MED4", experiment_ids=["exp1"],
                ontology="cyanorak_role", level=1,
                min_gene_set_size=50, max_gene_set_size=5,
            )

    def test_bad_pvalue_cutoff_raises(self):
        from multiomics_explorer.api import pathway_enrichment
        with pytest.raises(ValueError, match="pvalue_cutoff"):
            pathway_enrichment(
                organism="MED4", experiment_ids=["exp1"],
                ontology="cyanorak_role", level=1,
                pvalue_cutoff=1.5,
            )

    def test_empty_experiment_ids_raises(self):
        from multiomics_explorer.api import pathway_enrichment
        with pytest.raises(ValueError, match="experiment_id"):
            pathway_enrichment(
                organism="MED4", experiment_ids=[],
                ontology="cyanorak_role", level=1,
            )

    @staticmethod
    def _stub_de_result(rows=(), not_found=(), not_matched=(), no_expression=()):
        return {
            "organism_name": "MED4",
            "results": list(rows),
            "not_found": list(not_found),
            "not_matched": list(not_matched),
            "no_expression": list(no_expression),
        }

    @staticmethod
    def _stub_gbo_result(rows=(), not_found=(), wrong_ontology=(),
                        wrong_level=(), filtered_out=()):
        return {
            "ontology": "cyanorak_role",
            "organism_name": "MED4",
            "results": list(rows),
            "not_found": list(not_found),
            "wrong_ontology": list(wrong_ontology),
            "wrong_level": list(wrong_level),
            "filtered_out": list(filtered_out),
        }

    def test_vacuous_success_when_all_experiments_missing(self, monkeypatch):
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(not_found=["exp1"]),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            lambda **_: self._stub_gbo_result(),
        )
        result = pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
        )
        out = result.to_envelope()
        assert out["total_matching"] == 0
        assert out["results"] == []
        assert out["not_found"] == ["exp1"]
        assert out["n_significant"] == 0

    def test_term_validation_passthrough(self, monkeypatch):
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            lambda **_: self._stub_gbo_result(
                not_found=["missing_term"],
                wrong_level=["wrong_level_term"],
            ),
        )
        result = pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
            term_ids=["missing_term", "wrong_level_term"],
        )
        out = result.to_envelope()
        assert out["term_validation"]["not_found"] == ["missing_term"]
        assert out["term_validation"]["wrong_level"] == ["wrong_level_term"]

    def test_envelope_shape_echoes_inputs(self, monkeypatch):
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            lambda **_: self._stub_gbo_result(),
        )
        result = pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
        )
        out = result.to_envelope()
        assert out["organism_name"] == "MED4"
        assert out["ontology"] == "cyanorak_role"
        assert out["level"] == 1
        for key in ("total_matching", "returned", "truncated", "offset",
                    "n_significant", "by_experiment", "by_direction",
                    "by_omics_type", "cluster_summary",
                    "top_clusters_by_min_padj", "top_pathways_by_padj",
                    "not_found", "not_matched", "no_expression",
                    "term_validation", "clusters_skipped", "results"):
            assert key in out, f"envelope missing key: {key}"


# ---------------------------------------------------------------------------
# cluster_enrichment_inputs
# ---------------------------------------------------------------------------
class TestClusterEnrichmentInputs:
    """Tests for cluster_enrichment_inputs helper."""

    _CLUSTER_RESULT = {
        "total_matching": 7,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 7}],
        "by_cluster": [
            {"cluster_id": "gc:1", "cluster_name": "Cluster A", "count": 4},
            {"cluster_id": "gc:2", "cluster_name": "Cluster B", "count": 2},
            {"cluster_id": "gc:3", "cluster_name": "Cluster C", "count": 1},
        ],
        "top_categories": [],
        "genes_per_cluster_max": 4,
        "genes_per_cluster_median": 2,
        "not_found_clusters": [],
        "not_matched_clusters": [],
        "not_matched_organism": None,
        "analysis_name": "Test Analysis",
        "returned": 7,
        "truncated": False,
        "offset": 0,
        "results": [
            {"locus_tag": "PMM0001", "cluster_id": "gc:1", "cluster_name": "Cluster A",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0002", "cluster_id": "gc:1", "cluster_name": "Cluster A",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0003", "cluster_id": "gc:1", "cluster_name": "Cluster A",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0004", "cluster_id": "gc:1", "cluster_name": "Cluster A",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0005", "cluster_id": "gc:2", "cluster_name": "Cluster B",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0006", "cluster_id": "gc:2", "cluster_name": "Cluster B",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0007", "cluster_id": "gc:3", "cluster_name": "Cluster C",
             "organism_name": "Prochlorococcus MED4"},
        ],
    }

    _ANALYSIS_META = {
        "results": [{
            "analysis_id": "ca:test",
            "name": "Test Analysis",
            "organism_name": "Prochlorococcus MED4",
            "cluster_method": "kmeans",
            "cluster_type": "diel_cycle",
            "cluster_count": 3,
            "total_gene_count": 7,
            "treatment_type": ["light_dark"],
            "background_factors": [],
            "growth_phases": [],
            "omics_type": "transcriptomics",
            "experiment_ids": ["exp:1"],
            "clusters": [],
        }],
        "total_matching": 1,
        "returned": 1,
        "truncated": False,
    }

    def test_builds_gene_sets_grouped_by_cluster(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4", min_cluster_size=1)
        assert "Cluster A" in inputs.gene_sets
        assert "Cluster B" in inputs.gene_sets
        assert sorted(inputs.gene_sets["Cluster A"]) == ["PMM0001", "PMM0002", "PMM0003", "PMM0004"]
        assert sorted(inputs.gene_sets["Cluster B"]) == ["PMM0005", "PMM0006"]

    def test_cluster_union_background_includes_all_genes(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4", min_cluster_size=3)
        # Cluster C (1 gene) filtered out but its gene still in background
        all_bg_genes = set(inputs.background["Cluster A"])
        assert "PMM0007" in all_bg_genes
        assert len(all_bg_genes) == 7

    def test_min_cluster_size_filters_small_clusters(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4", min_cluster_size=3)
        assert "Cluster A" in inputs.gene_sets
        assert "Cluster B" not in inputs.gene_sets
        assert "Cluster C" not in inputs.gene_sets

    def test_max_cluster_size_filters_large_clusters(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4",
            min_cluster_size=1, max_cluster_size=3)
        assert "Cluster A" not in inputs.gene_sets
        assert "Cluster B" in inputs.gene_sets
        assert "Cluster C" in inputs.gene_sets

    def test_clusters_skipped_populated(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4", min_cluster_size=3)
        assert len(inputs.clusters_skipped) == 2
        skipped_names = {s["cluster_name"] for s in inputs.clusters_skipped}
        assert skipped_names == {"Cluster B", "Cluster C"}

    def test_not_found_when_analysis_missing(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        empty_result = {
            **self._CLUSTER_RESULT,
            "total_matching": 0, "results": [], "returned": 0,
            "analysis_name": None,
        }
        empty_meta = {**self._ANALYSIS_META, "total_matching": 0, "results": [], "returned": 0}
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: empty_result)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: empty_meta)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:missing", organism="MED4")
        assert "ca:missing" in inputs.not_found

    def test_not_matched_when_organism_wrong(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        wrong_org_result = {
            **self._CLUSTER_RESULT,
            "not_matched_organism": "SomeOtherOrg",
            "total_matching": 0, "results": [], "returned": 0,
        }
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: wrong_org_result)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="SomeOtherOrg")
        assert "ca:test" in inputs.not_matched

    def test_cluster_metadata_populated(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4")
        md = inputs.cluster_metadata["Cluster A"]
        assert md["cluster_id"] == "gc:1"
        assert md["member_count"] == 4


# ---------------------------------------------------------------------------
# cluster_enrichment  (L2 API)
# ---------------------------------------------------------------------------


class TestClusterEnrichment:
    """Input validation + orchestration for api.cluster_enrichment."""

    def test_importable_from_api(self):
        from multiomics_explorer.api import cluster_enrichment
        assert cluster_enrichment is not None

    def test_invalid_ontology_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="ontology"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="not_real", level=1,
            )

    def test_missing_level_and_term_ids_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="level|term_ids"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="cyanorak_role",
            )

    def test_bad_background_string_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="background"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="cyanorak_role", level=1,
                background="genome",
            )

    def test_bad_pvalue_cutoff_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="pvalue_cutoff"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="cyanorak_role", level=1,
                pvalue_cutoff=1.5,
            )

    def test_max_less_than_min_gene_set_size_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="max_gene_set_size"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="cyanorak_role", level=1,
                min_gene_set_size=50, max_gene_set_size=5,
            )

    def test_max_less_than_min_cluster_size_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="max_cluster_size"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="cyanorak_role", level=1,
                min_cluster_size=20, max_cluster_size=5,
            )

    @staticmethod
    def _stub_inputs(gene_sets=None, not_found=(), not_matched=()):
        from multiomics_explorer.analysis.enrichment import EnrichmentInputs
        if gene_sets is None:
            gene_sets = {"Cluster A": ["PMM0001", "PMM0002"]}
        return EnrichmentInputs(
            organism_name="MED4",
            gene_sets=gene_sets,
            background={"Cluster A": ["PMM0001", "PMM0002", "PMM0003"]},
            cluster_metadata={"Cluster A": {
                "cluster_id": "gc:1", "cluster_name": "Cluster A",
                "member_count": 2,
            }},
            not_found=list(not_found),
            not_matched=list(not_matched),
            no_expression=[],
            clusters_skipped=[],
            analysis_metadata={
                "analysis_id": "ca:test", "analysis_name": "Test",
                "cluster_method": "kmeans", "cluster_type": "diel_cycle",
                "omics_type": "transcriptomics",
                "treatment_type": ["light_dark"],
                "background_factors": [], "growth_phases": [],
                "experiment_ids": ["exp:1"],
            },
        )

    @staticmethod
    def _stub_gbo_result(rows=()):
        return {
            "ontology": "cyanorak_role", "organism_name": "MED4",
            "results": list(rows),
            "not_found": [], "wrong_ontology": [],
            "wrong_level": [], "filtered_out": [],
        }

    def test_early_return_when_not_found(self, monkeypatch):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(gene_sets={}, not_found=["ca:missing"]),
        )
        result = cluster_enrichment(
            analysis_id="ca:missing", organism="MED4",
            ontology="cyanorak_role", level=1,
        )
        envelope = result.to_envelope()
        assert envelope["not_found"] == ["ca:missing"]
        assert envelope["results"] == []

    def test_orchestration_produces_envelope(self, monkeypatch):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            lambda **_: self._stub_gbo_result([
                {"term_id": "CR:A", "term_name": "Cat A", "locus_tag": "PMM0001", "level": 1},
                {"term_id": "CR:A", "term_name": "Cat A", "locus_tag": "PMM0002", "level": 1},
                {"term_id": "CR:B", "term_name": "Cat B", "locus_tag": "PMM0003", "level": 1},
            ]),
        )
        result = cluster_enrichment(
            analysis_id="ca:test", organism="MED4",
            ontology="cyanorak_role", level=1,
            pvalue_cutoff=0.99,
        )
        envelope = result.to_envelope()
        assert "total_matching" in envelope
        assert "returned" in envelope
        assert "analysis_id" in envelope
        assert "organism_name" in envelope
        assert isinstance(envelope["results"], list)

    def test_cluster_skip_dict_shape_matches_pydantic_model(self):
        """Regression: post-Fisher skip dicts must include cluster_id (required
        by ClusterEnrichmentClusterSkipped) so ClusterEnrichmentResponse(**envelope)
        doesn't raise ValidationError."""
        from multiomics_explorer.mcp_server.tools import ClusterEnrichmentClusterSkipped

        skip = {
            "cluster_id": "gc:1",
            "cluster_name": "Cluster A",
            "member_count": 5,
            "reason": "no_pathways_in_size_range",
        }
        model = ClusterEnrichmentClusterSkipped(**skip)
        assert model.cluster_id == "gc:1"
        assert model.cluster_name == "Cluster A"
        assert model.reason == "no_pathways_in_size_range"

    def test_post_fisher_skip_populates_cluster_id(self, monkeypatch):
        """Regression: when a cluster passes size filter but yields no Fisher rows,
        the post-Fisher skip must include cluster_id so the Pydantic envelope
        roundtrip succeeds."""
        from multiomics_explorer.api import cluster_enrichment
        from multiomics_explorer.mcp_server.tools import ClusterEnrichmentResponse
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f

        # Cluster B has members in gene_sets and background but no matching
        # ontology terms → yields no Fisher rows → falls into post-Fisher skip.
        def _stub_inputs(**_):
            from multiomics_explorer.analysis.enrichment import EnrichmentInputs
            return EnrichmentInputs(
                organism_name="MED4",
                gene_sets={"Cluster B": ["PMM0010", "PMM0011"]},
                background={"Cluster B": ["PMM0010", "PMM0011", "PMM0012"]},
                cluster_metadata={"Cluster B": {
                    "cluster_id": "gc:99", "cluster_name": "Cluster B",
                    "member_count": 2,
                }},
                not_found=[], not_matched=[], no_expression=[],
                clusters_skipped=[],
                analysis_metadata={
                    "analysis_id": "ca:test2", "analysis_name": "Test2",
                    "cluster_method": "kmeans", "cluster_type": "diel_cycle",
                    "omics_type": "transcriptomics",
                    "treatment_type": ["light_dark"],
                    "background_factors": [], "growth_phases": [],
                    "experiment_ids": ["exp:1"],
                },
            )

        monkeypatch.setattr(enr, "cluster_enrichment_inputs", _stub_inputs)
        # Return empty term2gene rows — no Fisher rows produced for Cluster B.
        monkeypatch.setattr(
            f, "genes_by_ontology",
            lambda **_: self._stub_gbo_result([]),
        )

        result = cluster_enrichment(
            analysis_id="ca:test2", organism="MED4",
            ontology="cyanorak_role", level=1,
            pvalue_cutoff=0.99,
        )
        envelope = result.to_envelope()
        # Before the fix this would raise pydantic ValidationError (missing cluster_id).
        response = ClusterEnrichmentResponse(**envelope)
        skips = response.clusters_skipped
        assert len(skips) == 1
        assert skips[0].cluster_id == "gc:99"
        assert skips[0].cluster_name == "Cluster B"


class TestListDerivedMetrics:
    """Tests for api.list_derived_metrics."""

    _SUMMARY_ROW = {
        "total_entries": 13,
        "total_matching": 4,
        "by_organism": [{"item": "Prochlorococcus MED4", "count": 4}],
        "by_value_kind": [{"item": "numeric", "count": 4}],
        "by_metric_type": [
            {"item": "damping_ratio", "count": 1},
            {"item": "diel_amplitude_protein_log2", "count": 1},
        ],
        "by_compartment": [{"item": "whole_cell", "count": 4}],
        "by_omics_type": [{"item": "PAIRED_RNASEQ_PROTEOME", "count": 4}],
        "by_treatment_type": [{"item": "diel", "count": 4}],
        "by_background_factors": [{"item": "axenic", "count": 4}],
        "by_growth_phase": [],
    }

    _DETAIL_ROW = {
        "derived_metric_id": "derived_metric:.../damping_ratio",
        "name": "Transcript:protein amplitude ratio",
        "metric_type": "damping_ratio",
        "value_kind": "numeric",
        "rankable": "true",
        "has_p_value": "false",
        "unit": "",
        "allowed_categories": None,
        "field_description": "...",
        "organism_name": "Prochlorococcus MED4",
        "experiment_id": "exp_1",
        "publication_doi": "10.1371/journal.pone.0043432",
        "compartment": "whole_cell",
        "omics_type": "PAIRED_RNASEQ_PROTEOME",
        "treatment_type": ["diel"],
        "background_factors": ["axenic"],
        "total_gene_count": 312,
        "growth_phases": [],
    }

    def _mock_conn(self, summary_row, detail_rows):
        from unittest.mock import MagicMock
        conn = MagicMock()
        # Two calls: summary first, detail second
        conn.execute_query.side_effect = [[summary_row], detail_rows]
        return conn

    def test_summary_and_detail_envelope(self):
        from multiomics_explorer.api.functions import list_derived_metrics
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_derived_metrics(organism="MED4", conn=conn)
        assert out["total_entries"] == 13
        assert out["total_matching"] == 4
        assert out["returned"] == 1
        assert out["offset"] == 0
        assert out["truncated"] is True  # 4 > 0 + 1
        assert len(out["results"]) == 1
        assert out["results"][0]["derived_metric_id"].endswith("damping_ratio")
        # Breakdowns renamed from {item, count} to {<key>, count}
        assert out["by_organism"] == [
            {"organism_name": "Prochlorococcus MED4", "count": 4}
        ]
        assert out["by_value_kind"] == [{"value_kind": "numeric", "count": 4}]
        assert out["by_background_factors"] == [
            {"background_factor": "axenic", "count": 4}
        ]
        assert out["by_growth_phase"] == []
        # No search_text → score fields None
        assert out["score_max"] is None
        assert out["score_median"] is None

    def test_summary_true_skips_detail_query(self):
        from multiomics_explorer.api.functions import list_derived_metrics
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.execute_query.side_effect = [[self._SUMMARY_ROW]]  # only summary called
        out = list_derived_metrics(summary=True, conn=conn)
        assert out["results"] == []
        assert out["returned"] == 0
        assert out["truncated"] is True  # total_matching > 0
        assert conn.execute_query.call_count == 1

    def test_search_text_empty_raises(self):
        from multiomics_explorer.api.functions import list_derived_metrics
        import pytest
        with pytest.raises(ValueError, match="search_text"):
            list_derived_metrics(search_text="")

    def test_search_text_whitespace_raises(self):
        from multiomics_explorer.api.functions import list_derived_metrics
        import pytest
        with pytest.raises(ValueError, match="search_text"):
            list_derived_metrics(search_text="   ")

    def test_score_stats_present_when_search(self):
        from multiomics_explorer.api.functions import list_derived_metrics
        summary_with_score = {**self._SUMMARY_ROW, "score_max": 1.9, "score_median": 0.8}
        conn = self._mock_conn(summary_with_score, [self._DETAIL_ROW])
        out = list_derived_metrics(search_text="diel", conn=conn)
        assert out["score_max"] == 1.9
        assert out["score_median"] == 0.8

    def test_lucene_retry_on_parse_error(self):
        from multiomics_explorer.api.functions import list_derived_metrics
        from neo4j.exceptions import ClientError
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.execute_query.side_effect = [
            ClientError("parse error"),  # summary first call fails
            [self._SUMMARY_ROW],           # summary retry succeeds
            [self._DETAIL_ROW],             # detail succeeds
        ]
        out = list_derived_metrics(search_text="diel*", conn=conn)
        # Escape check — the retry call used escaped "diel\\*"
        second_call_params = conn.execute_query.call_args_list[1].kwargs
        assert second_call_params["search_text"] == r"diel\*"
        assert out["total_matching"] == 4

    def test_importable_from_package(self):
        from multiomics_explorer import list_derived_metrics as api_ldm
        from multiomics_explorer.api import list_derived_metrics as api_direct
        assert api_ldm is api_direct

    def test_returns_score_max_none_when_no_search(self):
        from multiomics_explorer.api.functions import list_derived_metrics
        conn = self._mock_conn(self._SUMMARY_ROW, [])
        out = list_derived_metrics(conn=conn)
        assert out["score_max"] is None


# ---------------------------------------------------------------------------
# list_metabolites — Phase 1 (Stage 1 RED)
# ---------------------------------------------------------------------------


class TestListMetabolites:
    """Tests for api.list_metabolites.

    Imports happen inside each test so pre-impl collection still passes.
    """

    _SUMMARY_ROW = {
        "total_entries": 3025,
        "total_matching": 1,
        "top_organisms": [
            {"organism_name": "Prochlorococcus MED4", "count": 1},
        ],
        "top_pathways": [
            {
                "pathway_id": "kegg.pathway:ko01100",
                "pathway_name": "Metabolic pathways",
                "count": 1,
            },
        ],
        "by_evidence_source": [{"item": "metabolism", "count": 1}],
        "with_chebi": 1,
        "with_hmdb": 0,
        "with_mnxm": 1,
        "mass_min": 180.156,
        "mass_median": 180.156,
        "mass_max": 180.156,
    }

    _DETAIL_ROW = {
        "metabolite_id": "kegg.compound:C00031",
        "name": "D-Glucose",
        "formula": "C6H12O6",
        "elements": ["C", "H", "O"],
        "mass": 180.156,
        "gene_count": 320,
        "organism_count": 31,
        "transporter_count": 17,
        "evidence_sources": ["metabolism", "transport"],
        "chebi_id": "4167",
        "pathway_ids": ["kegg.pathway:ko00010"],
        "pathway_count": 1,
    }

    def _mock_conn(self, summary_row, detail_rows, *extra):
        conn = MagicMock()
        side_effect = [[summary_row], detail_rows]
        side_effect.extend(extra)
        conn.execute_query.side_effect = side_effect
        return conn

    def test_returns_dict_envelope(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(conn=conn)
        assert isinstance(out, dict)
        assert out["total_entries"] == 3025
        assert out["total_matching"] == 1
        assert "top_organisms" in out
        assert "top_pathways" in out
        assert "by_evidence_source" in out
        assert "xref_coverage" in out
        assert "mass_stats" in out
        assert "not_found" in out
        assert out["returned"] == 1
        assert out["truncated"] is False
        assert len(out["results"]) == 1

    def test_summary_only_when_summary_true(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = MagicMock()
        # summary=True must skip the detail query entirely
        conn.execute_query.side_effect = [[self._SUMMARY_ROW]]
        out = list_metabolites(summary=True, conn=conn)
        assert out["results"] == []
        assert out["returned"] == 0
        assert conn.execute_query.call_count == 1

    def test_lucene_retry_on_parse_error(self):
        from multiomics_explorer.api.functions import list_metabolites
        from neo4j.exceptions import ClientError as Neo4jClientError
        conn = MagicMock()
        conn.execute_query.side_effect = [
            Neo4jClientError("Lucene parse error"),
            [self._SUMMARY_ROW],
            [self._DETAIL_ROW],
        ]
        out = list_metabolites(search="glucose*", conn=conn)
        assert out["total_matching"] == 1
        assert conn.execute_query.call_count == 3

    def test_evidence_sources_enum_validation(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = MagicMock()
        with pytest.raises(ValueError):
            list_metabolites(evidence_sources=["bogus"], conn=conn)

    def test_search_empty_validation(self):
        from multiomics_explorer.api.functions import list_metabolites
        with pytest.raises(ValueError):
            list_metabolites(search="")
        with pytest.raises(ValueError):
            list_metabolites(search="   ")

    def test_organism_names_lowercased(self):
        """organism_names is lowercased before being passed as
        $organism_names_lc to the WHERE clause."""
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(
            self._SUMMARY_ROW,
            [self._DETAIL_ROW],
            [{"found": ["prochlorococcus med4"]}],  # not_found probe
        )
        list_metabolites(
            organism_names=["Prochlorococcus MED4"], conn=conn,
        )
        summary_call = conn.execute_query.call_args_list[0]
        # Either passed as kwarg organism_names_lc or in params dict
        kw = summary_call.kwargs
        assert kw.get("organism_names_lc") == ["prochlorococcus med4"]

    def test_not_found_metabolite_ids(self):
        """Provided metabolite_ids that don't exist surface in
        not_found.metabolite_ids."""
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(
            self._SUMMARY_ROW,
            [self._DETAIL_ROW],
            [{"found": ["kegg.compound:C00031"]}],  # only one of two exists
        )
        out = list_metabolites(
            metabolite_ids=[
                "kegg.compound:C00031", "kegg.compound:C99999",
            ],
            conn=conn,
        )
        assert out["not_found"]["metabolite_ids"] == ["kegg.compound:C99999"]

    def test_not_found_organism_names(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(
            self._SUMMARY_ROW,
            [self._DETAIL_ROW],
            [{"found": ["prochlorococcus med4"]}],
        )
        out = list_metabolites(
            organism_names=["Prochlorococcus MED4", "Bogus organism"],
            conn=conn,
        )
        assert "Bogus organism" in out["not_found"]["organism_names"]

    def test_not_found_pathway_ids(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(
            self._SUMMARY_ROW,
            [self._DETAIL_ROW],
            [{"found": ["kegg.pathway:ko00910"]}],
        )
        out = list_metabolites(
            pathway_ids=[
                "kegg.pathway:ko00910", "kegg.pathway:bogus",
            ],
            conn=conn,
        )
        assert out["not_found"]["pathway_ids"] == ["kegg.pathway:bogus"]

    def test_sparse_strip_null_chebi(self):
        """When chebi_id is null on a row, api/ strips the key
        (Pydantic field is optional)."""
        from multiomics_explorer.api.functions import list_metabolites
        row = {**self._DETAIL_ROW, "chebi_id": None}
        conn = self._mock_conn(self._SUMMARY_ROW, [row])
        out = list_metabolites(conn=conn)
        assert "chebi_id" not in out["results"][0]

    def test_verbose_returns_only_property_reads(self):
        """Guard: verbose detail Cypher contains no CALL { ... } subqueries —
        purely property reads on m. Inspects the Cypher string handed to the
        Neo4j driver."""
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        list_metabolites(verbose=True, conn=conn)
        detail_call = conn.execute_query.call_args_list[1]
        cypher = detail_call.args[0] if detail_call.args else ""
        assert "CALL {" not in cypher
        assert "CALL{" not in cypher

    def test_creates_conn_when_none(self):
        from multiomics_explorer.api.functions import list_metabolites
        with patch(
            "multiomics_explorer.api.functions.GraphConnection",
        ) as MockConn:
            mock_instance = MockConn.return_value
            mock_instance.execute_query.side_effect = [
                [self._SUMMARY_ROW],
                [self._DETAIL_ROW],
            ]
            out = list_metabolites()
        MockConn.assert_called_once()
        assert out["total_matching"] == 1

    def test_importable_from_package(self):
        from multiomics_explorer import list_metabolites as pkg_lm
        from multiomics_explorer.api import list_metabolites as api_direct
        assert pkg_lm is api_direct


# ---------------------------------------------------------------------------
# genes_by_metabolite — Phase 1 (Stage 1 RED)
# ---------------------------------------------------------------------------


class TestGenesByMetabolite:
    """Tests for api.genes_by_metabolite.

    Mirrors `TestListMetabolites`'s mocked-conn pattern. Each test
    constructs a `_mock_conn` with a defined sequence of execute_query
    return values matching the expected per-call order in the api layer:

    1. summary builder (always)
    2. metabolism-arm detail (when summary=False AND metabolism arm fires)
    3. transport-arm detail   (when summary=False AND transport arm fires)
    4. existence probes (one per filter that has unknown-input diagnostics)

    The exact order in steps 2/3/4 matches the api implementation; tests
    that care about ordering use .call_args_list inspection. Tests that
    only care about the envelope use simpler probes via .return_value or
    side_effect.
    """

    _METS = ["kegg.compound:C00086"]  # urea
    _ORG = "Prochlorococcus MED4"

    # ---- Canned summary row (envelope payload from build_*_summary) ----
    _SUMMARY_ROW_BOTH_ARMS = {
        "total_matching": 23,
        "gene_count_total": 18,
        "reaction_count_total": 4,
        "transporter_count_total": 14,
        "metabolite_count_total": 1,
        # 4 metabolism + 19 transport rows
        "rows_by_evidence_source": [
            {"evidence_source": "metabolism", "count": 4},
            {"evidence_source": "transport", "count": 19},
        ],
        # 10 substrate_confirmed + 9 family_inferred (transport-only — 23 total
        # transport-confidence rows)
        "rows_by_transport_confidence": [
            {"transport_confidence": "substrate_confirmed", "count": 10},
            {"transport_confidence": "family_inferred", "count": 9},
        ],
        "by_metabolite": [
            {
                "metabolite_id": "kegg.compound:C00086",
                "name": "Urea",
                "formula": "CH4N2O",
                "rows": 23,
                "gene_count": 18,
                "reaction_count": 4,
                "transporter_count": 14,
                "metabolism_rows": 4,
                "transport_substrate_confirmed_rows": 10,
                "transport_family_inferred_rows": 9,
            },
        ],
        "top_reactions": [],
        "top_tcdb_families": [],
        "top_gene_categories": [],
        "top_genes": [],
    }

    # Family-inferred dominates — for the auto-warning trigger test
    _SUMMARY_ROW_FI_DOMINATES = {
        **_SUMMARY_ROW_BOTH_ARMS,
        "total_matching": 14,
        "gene_count_total": 14,
        "reaction_count_total": 0,
        "transporter_count_total": 14,
        "metabolite_count_total": 1,
        "rows_by_evidence_source": [
            {"evidence_source": "transport", "count": 14},
        ],
        "rows_by_transport_confidence": [
            {"transport_confidence": "substrate_confirmed", "count": 5},
            {"transport_confidence": "family_inferred", "count": 9},
        ],
        "by_metabolite": [
            {
                "metabolite_id": "kegg.compound:C00088",
                "name": "Nitrite",
                "formula": "HNO2",
                "rows": 14,
                "gene_count": 14,
                "reaction_count": 0,
                "transporter_count": 14,
                "metabolism_rows": 0,
                "transport_substrate_confirmed_rows": 5,
                "transport_family_inferred_rows": 9,
            },
        ],
    }

    # Sample metabolism-arm detail row (substrate_confirmed-by-definition)
    _METAB_ROW = {
        "locus_tag": "PMM0944",
        "gene_name": "ureC",
        "product": "urease",
        "evidence_source": "metabolism",
        "transport_confidence": None,
        "reaction_id": "kegg.reaction:R00131",
        "reaction_name": "Urea + 2H2O => CO2 + 2NH3",
        "ec_numbers": ["3.5.1.5"],
        "mass_balance": "balanced",
        "tcdb_family_id": None,
        "tcdb_family_name": None,
        "metabolite_id": "kegg.compound:C00086",
        "metabolite_name": "Urea",
        "metabolite_formula": "CH4N2O",
        "metabolite_mass": 60.032,
        "metabolite_chebi_id": "16199",
    }

    # Sample transport-arm detail row (substrate_confirmed)
    _TRANS_ROW_SC = {
        "locus_tag": "PMM0974",
        "gene_name": "urtE",
        "product": "ABC-type urea transporter, ATPase component",
        "evidence_source": "transport",
        "transport_confidence": "substrate_confirmed",
        "reaction_id": None,
        "reaction_name": None,
        "ec_numbers": None,
        "mass_balance": None,
        "tcdb_family_id": "tcdb:3.A.1.4.5",
        "tcdb_family_name": "tcdb:3.A.1.4.5",
        "metabolite_id": "kegg.compound:C00086",
        "metabolite_name": "Urea",
        "metabolite_formula": "CH4N2O",
        "metabolite_mass": 60.032,
        "metabolite_chebi_id": "16199",
    }

    # Sample transport-arm detail row (family_inferred)
    _TRANS_ROW_FI = {
        "locus_tag": "PMM0234",
        "gene_name": None,
        "product": "ABC superfamily ATP-binding cassette transporter",
        "evidence_source": "transport",
        "transport_confidence": "family_inferred",
        "reaction_id": None,
        "reaction_name": None,
        "ec_numbers": None,
        "mass_balance": None,
        "tcdb_family_id": "tcdb:3.A.1",
        "tcdb_family_name": "The ATP-binding Cassette (ABC) Superfamily",
        "metabolite_id": "kegg.compound:C00086",
        "metabolite_name": "Urea",
        "metabolite_formula": "CH4N2O",
        "metabolite_mass": 60.032,
        "metabolite_chebi_id": "16199",
    }

    # ---- Helpers ----

    def _mock_conn(self, *side_effect):
        """Conn whose .execute_query yields the provided sequence."""
        conn = MagicMock()
        conn.execute_query.side_effect = list(side_effect)
        return conn

    def _api(self):
        from multiomics_explorer.api.functions import genes_by_metabolite
        return genes_by_metabolite

    # ---- Tests ----

    def test_returns_dict_envelope(self):
        gbm = self._api()
        # summary, metab arm, transport arm, met-id existence probe
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        assert isinstance(out, dict)
        assert out["total_matching"] == 23
        assert "by_metabolite" in out
        assert "by_evidence_source" in out
        assert "by_transport_confidence" in out
        assert "top_reactions" in out
        assert "top_tcdb_families" in out
        assert "top_gene_categories" in out
        assert "top_genes" in out
        assert "not_found" in out
        assert "not_matched" in out
        assert "warnings" in out
        assert "results" in out

    def test_default_fires_both_arms(self):
        """No `evidence_sources` filter → both arm builders dispatched."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        # 1 summary + 2 detail (one per arm) + 1 existence probe = 4
        assert conn.execute_query.call_count >= 3
        # Both rows surface in the result
        evidence = {r["evidence_source"] for r in out["results"]}
        assert evidence == {"metabolism", "transport"}

    def test_evidence_sources_metabolism_only_skips_transport_arm(self):
        """evidence_sources=['metabolism'] suppresses the transport arm.
        No warning is emitted."""
        gbm = self._api()
        # summary (single arm), metabolism detail, met-id probe
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(
            self._METS, self._ORG,
            evidence_sources=["metabolism"], conn=conn,
        )
        # Only metabolism rows
        for r in out["results"]:
            assert r["evidence_source"] == "metabolism"
        assert out["warnings"] == []

    def test_evidence_sources_transport_only_skips_metabolism_arm(self):
        """evidence_sources=['transport'] suppresses the metabolism arm."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(
            self._METS, self._ORG,
            evidence_sources=["transport"], conn=conn,
        )
        for r in out["results"]:
            assert r["evidence_source"] == "transport"
        assert out["warnings"] == []

    def test_ec_numbers_does_not_suppress_transport_arm(self):
        """Per-arm filter scope: ec_numbers narrows only the metabolism
        arm WHERE; transport-arm rows still appear in the result."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],   # metabolism arm narrowed but row returned
            [self._TRANS_ROW_SC],  # transport arm UNCHANGED
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(
            self._METS, self._ORG,
            ec_numbers=["3.5.1.5"], conn=conn,
        )
        evidence = {r["evidence_source"] for r in out["results"]}
        assert "transport" in evidence  # transport arm STILL fired
        # No "soft-exclude" warning (per spec, this pattern was abandoned)
        assert all("soft-exclude" not in w for w in out["warnings"])

    def test_mass_balance_does_not_suppress_transport_arm(self):
        """Same per-arm filter scope as ec_numbers."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(
            self._METS, self._ORG,
            mass_balance="balanced", conn=conn,
        )
        evidence = {r["evidence_source"] for r in out["results"]}
        assert "transport" in evidence

    def test_transport_confidence_substrate_confirmed_no_warning(self):
        """transport_confidence='substrate_confirmed' narrows transport arm
        only AND suppresses the family-inferred-dominance warning (since user
        chose explicitly)."""
        gbm = self._api()
        # SC-only summary so transport rows are exclusively SC
        sc_summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "rows_by_transport_confidence": [
                {"transport_confidence": "substrate_confirmed", "count": 10},
            ],
            "by_metabolite": [
                {
                    **self._SUMMARY_ROW_BOTH_ARMS["by_metabolite"][0],
                    "transport_substrate_confirmed_rows": 10,
                    "transport_family_inferred_rows": 0,
                },
            ],
        }
        conn = self._mock_conn(
            [sc_summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(
            self._METS, self._ORG,
            transport_confidence="substrate_confirmed", conn=conn,
        )
        # Metabolism rows still present (transport_confidence does NOT touch
        # metabolism arm)
        evidence = {r["evidence_source"] for r in out["results"]}
        assert evidence == {"metabolism", "transport"}
        # No auto-warning (user explicitly set transport_confidence)
        assert out["warnings"] == []

    def test_transport_confidence_family_inferred_no_warning(self):
        """transport_confidence='family_inferred' likewise suppresses the
        auto-warning (user chose explicitly)."""
        gbm = self._api()
        fi_summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "rows_by_transport_confidence": [
                {"transport_confidence": "family_inferred", "count": 9},
            ],
            "by_metabolite": [
                {
                    **self._SUMMARY_ROW_BOTH_ARMS["by_metabolite"][0],
                    "transport_substrate_confirmed_rows": 0,
                    "transport_family_inferred_rows": 9,
                },
            ],
        }
        conn = self._mock_conn(
            [fi_summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_FI],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(
            self._METS, self._ORG,
            transport_confidence="family_inferred", conn=conn,
        )
        assert out["warnings"] == []

    def test_family_inferred_dominance_warning_fires(self):
        """Warning fires when:
        - transport rows present in result AND
        - transport_family_inferred_rows > transport_substrate_confirmed_rows AND
        - user did NOT set transport_confidence."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_FI_DOMINATES],
            # Note: transport-only — no metabolism rows from spec § probe:
            # "MED4 has no nitrite-anchored metabolism reactions today"
            [],  # metabolism arm fires but returns nothing
            [self._TRANS_ROW_FI],
            [{"found": ["kegg.compound:C00088"]}],
        )
        out = gbm(["kegg.compound:C00088"], self._ORG, conn=conn)
        assert any(
            "family_inferred" in w for w in out["warnings"]
        ), f"expected family-inferred warning, got {out['warnings']!r}"

    def test_no_warning_when_substrate_confirmed_majority(self):
        """sc >= fi → no auto-warning even with default both-arm mode."""
        gbm = self._api()
        # urea slice: 10 SC > 9 FI on transport
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        # 10 SC > 9 FI — no warning
        assert all(
            "family_inferred" not in w for w in out["warnings"]
        )

    def test_no_warning_when_no_transport_rows(self):
        """Metabolism-only result → no transport check → no warning."""
        gbm = self._api()
        # Suppress transport arm via evidence_sources
        no_transport_summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "rows_by_evidence_source": [
                {"evidence_source": "metabolism", "count": 4},
            ],
            "rows_by_transport_confidence": [],
            "by_metabolite": [
                {
                    **self._SUMMARY_ROW_BOTH_ARMS["by_metabolite"][0],
                    "transport_substrate_confirmed_rows": 0,
                    "transport_family_inferred_rows": 0,
                },
            ],
        }
        conn = self._mock_conn(
            [no_transport_summary],
            [self._METAB_ROW],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(
            self._METS, self._ORG,
            evidence_sources=["metabolism"], conn=conn,
        )
        assert out["warnings"] == []

    def test_not_found_metabolite_ids(self):
        """Input metabolite_ids that don't resolve to a Metabolite node
        surface in not_found.metabolite_ids."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            # Existence probe returns only one of the two as found
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(
            ["kegg.compound:C00086", "kegg.compound:C99999"],
            self._ORG, conn=conn,
        )
        assert out["not_found"]["metabolite_ids"] == ["kegg.compound:C99999"]

    def test_not_matched_for_resolved_but_no_rows(self):
        """Input metabolite_id that exists as Metabolite but produces zero
        rows in this organism slice → not_matched (NOT not_found)."""
        gbm = self._api()
        # Summary's by_metabolite carries only urea — water resolves but
        # produces no rows.
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            # Both IDs exist in KG
            [{"found": ["kegg.compound:C00086", "kegg.compound:C00001"]}],
        )
        out = gbm(
            ["kegg.compound:C00086", "kegg.compound:C00001"],
            self._ORG, conn=conn,
        )
        # water exists as Metabolite (so not in not_found) but produced no
        # rows for this organism (so it's in not_matched).
        assert "kegg.compound:C00001" in out["not_matched"]
        assert "kegg.compound:C00001" not in out["not_found"]["metabolite_ids"]

    def test_not_found_organism_when_zero_genes(self):
        """When the fuzzy organism match produces 0 genes (i.e. summary's
        gene_count_total == 0), not_found.organism is set to the input."""
        gbm = self._api()
        empty_summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "total_matching": 0,
            "gene_count_total": 0,
            "rows_by_evidence_source": [],
            "rows_by_transport_confidence": [],
            "by_metabolite": [],
        }
        conn = self._mock_conn(
            [empty_summary],
            [],  # metab detail (empty)
            [],  # transport detail (empty)
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, "Bogus organism", conn=conn)
        assert out["not_found"]["organism"] == "Bogus organism"

    def test_not_found_organism_none_on_success(self):
        """gene_count_total > 0 → not_found.organism is None."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        assert out["not_found"]["organism"] is None

    def test_not_found_metabolite_pathway_ids(self):
        """Input metabolite_pathway_ids that don't resolve to KeggTerm
        surface in not_found.metabolite_pathway_ids."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            # metabolite_id existence probe
            [{"found": ["kegg.compound:C00086"]}],
            # pathway-id existence probe
            [{"found": ["kegg.pathway:ko00910"]}],
        )
        out = gbm(
            self._METS, self._ORG,
            metabolite_pathway_ids=[
                "kegg.pathway:ko00910", "kegg.pathway:bogus",
            ],
            conn=conn,
        )
        assert (
            out["not_found"]["metabolite_pathway_ids"]
            == ["kegg.pathway:bogus"]
        )

    def test_summary_true_skips_detail_dispatch(self):
        """summary=True returns envelope only; detail builders not called."""
        gbm = self._api()
        conn = MagicMock()
        # Only summary should run — detail should not be invoked. We seed
        # only one return value; if detail dispatched, the next call would
        # raise StopIteration.
        conn.execute_query.side_effect = [
            [self._SUMMARY_ROW_BOTH_ARMS],
            [{"found": ["kegg.compound:C00086"]}],
        ]
        out = gbm(self._METS, self._ORG, summary=True, conn=conn)
        assert out["results"] == []
        assert out["returned"] == 0

    def test_evidence_sources_validator_rejects_bogus(self):
        """Defense-in-depth ValueError from the api validator."""
        gbm = self._api()
        conn = MagicMock()
        with pytest.raises(ValueError):
            gbm(
                self._METS, self._ORG,
                evidence_sources=["bogus"], conn=conn,
            )

    def test_evidence_sources_validator_rejects_metabolomics(self):
        """`metabolomics` is accepted by list_metabolites but NOT here —
        gene-anchored tools have no metabolomics path. Per spec § Resolved
        ('evidence_sources Literal divergence with list_metabolites')."""
        gbm = self._api()
        conn = MagicMock()
        with pytest.raises(ValueError):
            gbm(
                self._METS, self._ORG,
                evidence_sources=["metabolomics"], conn=conn,
            )

    def test_limit_offset_paging_across_arms(self):
        """Arms over-fetch limit+offset, api concatenates and slices.
        Verify the global slice returns the correct prefix."""
        gbm = self._api()
        # Mock returns metabolism + 2 transport rows; with limit=2/offset=0
        # the returned slice should be the first 2 rows in global sort
        # order ('metabolism' < 'transport' alphabetically → metab row,
        # then SC transport row).
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC, self._TRANS_ROW_FI],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, limit=2, offset=0, conn=conn)
        assert len(out["results"]) == 2
        # Sort key: metabolite_id, evidence_source ('metabolism' < 'transport'),
        # transport_confidence_priority — first row metab, second transport.
        assert out["results"][0]["evidence_source"] == "metabolism"
        assert out["results"][1]["evidence_source"] == "transport"

    def test_truncated_flag(self):
        """When total_matching > offset + len(results), truncated=True."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],  # total_matching=23
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, limit=2, conn=conn)
        assert out["truncated"] is True

    def test_offset_echoed_in_envelope(self):
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, offset=3, conn=conn)
        assert out["offset"] == 3

    def test_creates_conn_when_none(self):
        """When conn=None, default GraphConnection is created."""
        gbm = self._api()
        with patch(
            "multiomics_explorer.api.functions.GraphConnection",
        ) as MockConn:
            mock_instance = MockConn.return_value
            mock_instance.execute_query.side_effect = [
                [self._SUMMARY_ROW_BOTH_ARMS],
                [self._METAB_ROW],
                [self._TRANS_ROW_SC],
                [{"found": ["kegg.compound:C00086"]}],
            ]
            out = gbm(self._METS, self._ORG)
        MockConn.assert_called_once()
        assert out["total_matching"] == 23

    def test_importable_from_package(self):
        from multiomics_explorer import (
            genes_by_metabolite as pkg_gbm,
        )
        from multiomics_explorer.api import (
            genes_by_metabolite as api_direct,
        )
        assert pkg_gbm is api_direct

    # ---- Top-N sort + truncate contract (B2/C11 fixes) ----

    def _summary_with_top_arrays(self):
        """Synthesize a summary row with >10 entries in each top_* array,
        in shuffled order, using the post-fix Cypher field names.

        The api layer must (a) sort each top_* by gene_count/breadth desc
        with stable tiebreaker, and (b) slice to top 10. APOC's
        coll.toSet() does not preserve order, so the api-side sort is
        the only thing standing between the user and snapshot flakes.
        """
        # 12 reactions (intentionally shuffled; counts include a tie on 5)
        top_reactions = [
            {
                "reaction_id": f"kegg.reaction:R{i:05d}",
                "name": f"Reaction R{i:05d}",
                "ec_numbers": ["1.1.1.1"],
                "gene_count": gc,
                "metabolite_count": 1,
            }
            for i, gc in zip(
                # shuffled IDs, mixed counts incl. a 5/5 tie at the boundary
                [3, 11, 7, 1, 9, 4, 12, 5, 2, 8, 6, 10],
                [9, 1, 7, 12, 3, 8, 0, 11, 10, 5, 5, 4],
            )
        ]
        # 12 TCDB families
        top_tcdb_families = [
            {
                "tcdb_family_id": f"tcdb:3.A.1.{i}.1",
                "tcdb_family_name": f"Family {i}",
                "level_kind": "tc_specificity" if i % 2 == 0 else "tc_family",
                "transport_confidence": (
                    "substrate_confirmed" if i % 2 == 0 else "family_inferred"
                ),
                "gene_count": gc,
                "metabolite_count": 1,
            }
            for i, gc in zip(
                [5, 1, 11, 3, 9, 7, 12, 2, 8, 4, 10, 6],
                [4, 12, 2, 9, 6, 7, 1, 11, 5, 8, 3, 10],
            )
        ]
        # 12 categories
        top_gene_categories = [
            {"category": f"cat-{chr(ord('a') + i)}", "gene_count": gc}
            for i, gc in enumerate(
                [3, 1, 11, 5, 9, 7, 12, 2, 8, 4, 10, 6]
            )
        ]
        # 12 genes — RANK BY (reaction_count + transporter_count) DESC.
        # Build with combined-breadth values so we can verify the spec'd
        # ranking (NOT by gene_count; that field is not even on top_genes).
        top_genes = [
            {
                "locus_tag": f"PMM{i:04d}",
                "gene_name": None if i % 3 == 0 else f"gene-{i}",
                "reaction_count": rc,
                "transporter_count": tc,
                "metabolite_count": 1,
                "metabolism_rows": rc,
                "transport_substrate_confirmed_rows": tc,
                "transport_family_inferred_rows": 0,
            }
            for i, rc, tc in [
                (101, 2, 1),    # 3
                (102, 5, 4),    # 9
                (103, 1, 0),    # 1
                (104, 7, 6),    # 13 ← top
                (105, 0, 8),    # 8
                (106, 3, 3),    # 6
                (107, 4, 4),    # 8
                (108, 2, 2),    # 4
                (109, 6, 6),    # 12
                (110, 5, 5),    # 10
                (111, 1, 1),    # 2
                (112, 7, 4),    # 11
            ]
        ]
        return {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "top_reactions": top_reactions,
            "top_tcdb_families": top_tcdb_families,
            "top_gene_categories": top_gene_categories,
            "top_genes": top_genes,
        }

    def test_top_reactions_sorted_and_truncated_to_10(self):
        gbm = self._api()
        conn = self._mock_conn(
            [self._summary_with_top_arrays()],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        # Truncated to 10
        assert len(out["top_reactions"]) == 10
        # Sorted by gene_count desc, reaction_id asc tiebreaker
        gcs = [r["gene_count"] for r in out["top_reactions"]]
        assert gcs == sorted(gcs, reverse=True)
        # Highest gene_count is first
        assert out["top_reactions"][0]["gene_count"] == 12
        # Field name is `name` (not the old `reaction_name`)
        assert "name" in out["top_reactions"][0]
        assert "reaction_name" not in out["top_reactions"][0]

    def test_top_tcdb_families_sorted_and_truncated_to_10(self):
        gbm = self._api()
        conn = self._mock_conn(
            [self._summary_with_top_arrays()],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        assert len(out["top_tcdb_families"]) == 10
        gcs = [r["gene_count"] for r in out["top_tcdb_families"]]
        assert gcs == sorted(gcs, reverse=True)
        # New contract fields present
        first = out["top_tcdb_families"][0]
        assert "level_kind" in first
        assert "transport_confidence" in first
        assert "metabolite_count" in first

    def test_top_gene_categories_sorted_and_truncated_to_10(self):
        gbm = self._api()
        conn = self._mock_conn(
            [self._summary_with_top_arrays()],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        assert len(out["top_gene_categories"]) == 10
        gcs = [r["gene_count"] for r in out["top_gene_categories"]]
        assert gcs == sorted(gcs, reverse=True)
        # Field name is `category` (not the old `gene_category`)
        assert "category" in out["top_gene_categories"][0]
        assert "gene_category" not in out["top_gene_categories"][0]

    def test_top_genes_ranked_by_combined_breadth_not_gene_count(self):
        """Per spec § GbmTopGene: ranked by (reaction_count + transporter_count)
        desc, with locus_tag tiebreaker. gene_count is not even a field."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._summary_with_top_arrays()],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        assert len(out["top_genes"]) == 10
        # Combined breadth sequence is monotonically non-increasing
        breadths = [
            (g["reaction_count"] + g["transporter_count"])
            for g in out["top_genes"]
        ]
        assert breadths == sorted(breadths, reverse=True)
        # PMM0104 (rc=7, tc=6) → 13, the unique top.
        assert out["top_genes"][0]["locus_tag"] == "PMM0104"
        # gene_name may be None (fixture sets every 3rd to None) — confirm
        # the sort didn't TypeError on None.
        assert any(g["gene_name"] is None for g in out["top_genes"])

    def test_top_genes_locus_tag_tiebreaker(self):
        """When combined breadth ties, sort by locus_tag asc (NOT gene_name —
        gene_name may be None and would TypeError)."""
        gbm = self._api()
        # Two genes tied at combined breadth = 5; locus_tag asc breaks tie.
        tied_summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "top_genes": [
                {
                    "locus_tag": "PMM0999",
                    "gene_name": None,
                    "reaction_count": 2,
                    "transporter_count": 3,
                    "metabolite_count": 1,
                    "metabolism_rows": 2,
                    "transport_substrate_confirmed_rows": 3,
                    "transport_family_inferred_rows": 0,
                },
                {
                    "locus_tag": "PMM0001",
                    "gene_name": None,
                    "reaction_count": 5,
                    "transporter_count": 0,
                    "metabolite_count": 1,
                    "metabolism_rows": 5,
                    "transport_substrate_confirmed_rows": 0,
                    "transport_family_inferred_rows": 0,
                },
            ],
        }
        conn = self._mock_conn(
            [tied_summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        assert [g["locus_tag"] for g in out["top_genes"]] == [
            "PMM0001", "PMM0999",
        ]

    def test_by_metabolite_sorted_by_metabolite_id(self):
        """by_metabolite is bounded by input size (NOT sliced) but must be
        sorted by metabolite_id asc for deterministic snapshots, since the
        Cypher emits via apoc.coll.toSet() (unordered)."""
        gbm = self._api()
        # Two-entry by_metabolite supplied in shuffled order
        multi_metab_summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "by_metabolite": [
                {
                    "metabolite_id": "kegg.compound:C99999",
                    "name": "Z-compound",
                    "formula": "Z",
                    "rows": 1, "gene_count": 1, "reaction_count": 1,
                    "transporter_count": 0, "metabolism_rows": 1,
                    "transport_substrate_confirmed_rows": 0,
                    "transport_family_inferred_rows": 0,
                },
                {
                    "metabolite_id": "kegg.compound:C00086",
                    "name": "Urea",
                    "formula": "CH4N2O",
                    "rows": 23, "gene_count": 18, "reaction_count": 4,
                    "transporter_count": 14, "metabolism_rows": 4,
                    "transport_substrate_confirmed_rows": 10,
                    "transport_family_inferred_rows": 9,
                },
            ],
        }
        conn = self._mock_conn(
            [multi_metab_summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": [
                "kegg.compound:C00086", "kegg.compound:C99999",
            ]}],
        )
        out = gbm(
            ["kegg.compound:C00086", "kegg.compound:C99999"],
            self._ORG, conn=conn,
        )
        assert [b["metabolite_id"] for b in out["by_metabolite"]] == [
            "kegg.compound:C00086", "kegg.compound:C99999",
        ]

    def test_by_evidence_source_and_by_transport_confidence_sorted(self):
        """Both rollups sorted by count desc, then key asc."""
        gbm = self._api()
        # Provide rollups in non-canonical order to exercise the sort.
        scrambled = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "rows_by_evidence_source": [
                {"evidence_source": "transport", "count": 4},
                {"evidence_source": "metabolism", "count": 19},
            ],
            "rows_by_transport_confidence": [
                {"transport_confidence": "substrate_confirmed", "count": 3},
                {"transport_confidence": "family_inferred", "count": 9},
            ],
        }
        conn = self._mock_conn(
            [scrambled],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        # by_evidence_source: highest count first
        assert out["by_evidence_source"][0]["evidence_source"] == "metabolism"
        assert out["by_evidence_source"][0]["count"] == 19
        # by_transport_confidence: highest count first
        assert (
            out["by_transport_confidence"][0]["transport_confidence"]
            == "family_inferred"
        )

    def test_truncated_uses_offset_plus_limit_formula(self):
        """Per spec § Result-size controls (line 966): truncated iff
        (offset + limit) < total_matching. Independent of len(results)."""
        gbm = self._api()
        # offset=10, limit=10 → 20; total_matching=23 → truncated=True
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],  # total_matching=23
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, limit=10, offset=10, conn=conn)
        assert out["truncated"] is True

        # offset=20, limit=10 → 30 ≥ 23 → truncated=False
        conn2 = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_SC],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out2 = gbm(self._METS, self._ORG, limit=10, offset=20, conn=conn2)
        assert out2["truncated"] is False
