"""Unit tests for the api/ layer — no Neo4j needed.

Tests business logic, validation, parameter passing, and return types
by mocking GraphConnection.execute_query.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from multiomics_explorer.api import functions as api
from multiomics_explorer.kg import constants as _kg_constants


# ---------------------------------------------------------------------------
# Top-level package re-exports
# ---------------------------------------------------------------------------
class TestTopLevelImports:
    def test_all_api_functions_importable_from_package(self):
        """from multiomics_explorer import <fn> works for every api function."""
        from multiomics_explorer import (
            gene_homologs,
            genes_by_function,
            list_clustering_analyses,
            resolve_gene,
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


@pytest.fixture(autouse=True)
def _reset_vocab_cache():
    """`_read_vocab_values` caches per (applies_to, prop) at module scope
    (real-KG perf optimisation) — without a reset, whichever test in this
    file happens to run first for a given pair silently seeds the cache
    for every later test, making mocked `execute_query.side_effect` call
    counts order-dependent. Reset before and after every test so each test
    sees a cold cache regardless of run order (llm-review 2b.3)."""
    api._reset_vocab_cache()
    yield
    api._reset_vocab_cache()


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
        mock_load.assert_called_once_with(
            MockConn.return_value,
            labels=None,
            relationship_types=None,
            section="both",
        )

    def test_not_found_keys_default_empty(self, mock_conn):
        mock_schema = MagicMock()
        mock_schema.to_dict.return_value = {"nodes": {}, "relationships": {}}
        with patch(
            "multiomics_explorer.api.functions.load_schema_from_neo4j",
            return_value=mock_schema,
        ):
            result = api.kg_schema(conn=mock_conn)
        assert result["not_found_labels"] == []
        assert result["not_found_relationship_types"] == []
        mock_conn.get_labels.assert_not_called()
        mock_conn.get_relationship_types.assert_not_called()

    def test_labels_filter_reports_not_found_and_passes_valid_only(self, mock_conn):
        mock_conn.get_labels.return_value = ["Gene", "Experiment"]
        mock_schema = MagicMock()
        mock_schema.to_dict.return_value = {"nodes": {"Gene": {}}, "relationships": {}}
        with patch(
            "multiomics_explorer.api.functions.load_schema_from_neo4j",
            return_value=mock_schema,
        ) as mock_load:
            result = api.kg_schema(labels=["Gene", "Bogus"], conn=mock_conn)
        assert result["not_found_labels"] == ["Bogus"]
        mock_load.assert_called_once_with(
            mock_conn,
            labels=["Gene"],
            relationship_types=None,
            section="both",
        )

    def test_relationship_types_filter_reports_not_found_and_passes_valid_only(self, mock_conn):
        mock_conn.get_relationship_types.return_value = ["Encodes"]
        mock_schema = MagicMock()
        mock_schema.to_dict.return_value = {"nodes": {}, "relationships": {"Encodes": {}}}
        with patch(
            "multiomics_explorer.api.functions.load_schema_from_neo4j",
            return_value=mock_schema,
        ) as mock_load:
            result = api.kg_schema(relationship_types=["Encodes", "Bogus"], conn=mock_conn)
        assert result["not_found_relationship_types"] == ["Bogus"]
        mock_load.assert_called_once_with(
            mock_conn,
            labels=None,
            relationship_types=["Encodes"],
            section="both",
        )

    def test_section_passed_through(self, mock_conn):
        mock_schema = MagicMock()
        mock_schema.to_dict.return_value = {"nodes": {}, "relationships": {}}
        with patch(
            "multiomics_explorer.api.functions.load_schema_from_neo4j",
            return_value=mock_schema,
        ) as mock_load:
            api.kg_schema(section="nodes", conn=mock_conn)
        mock_load.assert_called_once_with(
            mock_conn,
            labels=None,
            relationship_types=None,
            section="nodes",
        )


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
# _run_fulltext — shared Lucene-error-to-ValueError translation helper
# ---------------------------------------------------------------------------
class TestRunFulltext:
    """Every fulltext (db.index.fulltext.queryNodes) tool routes its final
    (post-escape-retry) query execution through this one helper so a Neo4j
    ClientError carrying a Lucene parse failure becomes a readable
    ValueError instead of leaking the raw driver exception (llm-review
    2b.3)."""

    def test_passes_through_success(self, mock_conn):
        mock_conn.execute_query.return_value = [{"a": 1}]
        rows = api._run_fulltext(mock_conn, "CALL ...", {}, "search text")
        assert rows == [{"a": 1}]

    def test_parse_exception_becomes_readable_valueerror(self, mock_conn):
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = Neo4jClientError(
            "Invalid input 'AND': expected ... (line 1, column 6) ParseException"
        )
        with pytest.raises(ValueError) as exc_info:
            api._run_fulltext(mock_conn, "CALL ...", {}, "psbA AND")
        msg = str(exc_info.value)
        assert "psbA AND" in msg
        assert "is not valid Lucene syntax" in msg
        assert "ParseException" in msg
        assert "Quote phrases, escape special characters, or drop trailing operators" in msg

    def test_querynodes_error_becomes_readable_valueerror(self, mock_conn):
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = Neo4jClientError(
            "Failed to invoke procedure `db.index.fulltext.queryNodes`: "
            "Caused by: bad syntax"
        )
        with pytest.raises(ValueError, match=r"is not valid Lucene syntax"):
            api._run_fulltext(mock_conn, "CALL ...", {}, "nitrogen AND (")

    def test_unrelated_clienterror_not_translated(self, mock_conn):
        """A ClientError with no Lucene fingerprint propagates unchanged —
        this helper only translates parse failures, not arbitrary errors."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = Neo4jClientError(
            "Neo.ClientError.Security.Unauthorized"
        )
        with pytest.raises(Neo4jClientError):
            api._run_fulltext(mock_conn, "CALL ...", {}, "fine query")


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

    def test_empty_intersection_warns(self, mock_conn, monkeypatch):
        """search_text hits but the organism/category filters leave 0 rows
        -> envelope warning (upstream ticket 2026-08 #1: a silent zero read
        as 'no transporters in this organism')."""
        monkeypatch.setattr(api, "_closed_vocab_warnings", lambda *a, **k: [])
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_search_hits=9374, total_matching=0),
            [],
        ]
        result = api.genes_by_function(
            "ABC transporter permease", organism="HOT1A3",
            category="Transport", conn=mock_conn)
        assert result["total_matching"] == 0
        assert len(result["warnings"]) == 1
        w = result["warnings"][0]
        assert "9374" in w and "category='Transport'" in w
        assert "organism='HOT1A3'" in w
        assert "min_quality" not in w  # default 0 is not an active filter
        assert "by_category" in w

    def test_intersection_warning_yields_to_vocab_warning(self, mock_conn, monkeypatch):
        """A category typo already explains the zero — no second warning."""
        monkeypatch.setattr(api, "_closed_vocab_warnings",
                            lambda *a, **k: ["category value 'Bogus' matched nothing"])
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_search_hits=100, total_matching=0), [],
        ]
        result = api.genes_by_function("x", category="Bogus", conn=mock_conn)
        assert len(result["warnings"]) == 1
        assert "empty intersection" not in result["warnings"][0]

    def test_no_intersection_warning_without_filters(self, mock_conn):
        """A plain zero-hit search is not an empty intersection."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total_search_hits=0, total_matching=0),
            [],
        ]
        result = api.genes_by_function("zzz", conn=mock_conn)
        assert result["warnings"] == []

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

    def test_lucene_parse_error_survives_retry_raises_readable_valueerror(self, mock_conn):
        """When even the escaped retry fails with a Lucene parse error, the
        raw neo4j ClientError must not leak — it becomes a readable
        ValueError naming the bad search_text (llm-review 2b.3)."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError(
                "Invalid input 'AND': expected ... ParseException"),
            Neo4jClientError(
                "Invalid input 'AND': expected ... ParseException"),
        ]
        with pytest.raises(ValueError, match=r"is not valid Lucene syntax"):
            api.genes_by_function("psbA AND", conn=mock_conn)

    def test_passes_params(self, mock_conn, monkeypatch):
        """Verify organism, category, min_quality forwarded to builder."""
        monkeypatch.setattr(api, "_closed_vocab_warnings", lambda *a, **k: [])
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
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
                [],  # case-mismatch lookup over not_found
            ]
            result = api.gene_overview(["FAKE"], summary=True)
        MockConn.assert_called_once()
        assert result["total_matching"] == 0

    def test_not_found_populated(self, mock_conn):
        """Not-found locus_tags appear in not_found list."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(total=0, not_found=["FAKE0001"]),
            [],  # case-mismatch lookup over not_found
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
            [],  # case-mismatch lookup over not_found
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
            [],  # case-mismatch lookup over not_found
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
            [{"organisms": ["Prochlorococcus MED4"]}],    # resolver
            [filtered_summary],                          # summary
            self._ROWS[:1],                              # detail
        ]
        api.list_organisms(
            organism_names=["Prochlorococcus MED4"], conn=mock_conn,
        )
        # Third call is the detail query — params include lowercased list.
        detail_call_kwargs = mock_conn.execute_query.call_args_list[2][1]
        assert detail_call_kwargs["organism_names_lc"] == ["prochlorococcus med4"]

    def test_filter_with_unknown_populates_not_found(self, mock_conn):
        """Unknown names appear in not_found, original casing preserved."""
        filtered_summary = {**self._SUMMARY_ROW, "total_entries": 32, "total_matching": 1}
        mock_conn.execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],    # resolver
            [{"organisms": []}],                         # resolver miss
            [filtered_summary],                          # summary
            self._ROWS[:1],                              # detail
            [{"found": []}],                             # exact-name fallback
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
            [{"organisms": ["Prochlorococcus MED4"]}],    # resolver
            [{"organisms": ["Alteromonas macleodii EZ55"]}],
            [filtered_summary],                          # summary
            self._ROWS,                                  # detail
        ]
        result = api.list_organisms(
            organism_names=["Prochlorococcus MED4", "Alteromonas macleodii EZ55"],
            conn=mock_conn,
        )
        assert result["not_found"] == []
        assert result["total_matching"] == 2

    # Chemistry rollup propagation + top_metabolic_capability envelope (slice 1)
    # Catalysis-arm rename (KG-SYNC-001): metabolite_count →
    # catalyzed_metabolite_count on rows AND top_metabolic_capability entries.

    _CHEMISTRY_ROWS = [
        {**dict(_ROWS[0]),
         "reaction_count": 943, "catalyzed_metabolite_count": 1039,
         "transported_metabolite_count": 120},
        {**dict(_ROWS[1]),
         "reaction_count": 1348, "catalyzed_metabolite_count": 1428,
         "transported_metabolite_count": 95},
    ]

    def test_transported_metabolite_count_propagates_to_results(self, mock_conn):
        """substrate_depth migration: per-row transported_metabolite_count
        (deepest-attachment transport breadth) passes through."""
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], self._CHEMISTRY_ROWS,
        ]
        result = api.list_organisms(conn=mock_conn)
        assert result["results"][0]["transported_metabolite_count"] == 120
        assert result["results"][1]["transported_metabolite_count"] == 95

    def test_reaction_count_propagates_to_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], self._CHEMISTRY_ROWS,
        ]
        result = api.list_organisms(conn=mock_conn)
        assert result["results"][0]["reaction_count"] == 943
        assert result["results"][1]["reaction_count"] == 1348

    def test_catalyzed_metabolite_count_propagates_to_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], self._CHEMISTRY_ROWS,
        ]
        result = api.list_organisms(conn=mock_conn)
        assert result["results"][0]["catalyzed_metabolite_count"] == 1039
        assert result["results"][1]["catalyzed_metabolite_count"] == 1428

    def test_top_metabolic_capability_sorted_desc_by_catalyzed_metabolite_count(
        self, mock_conn,
    ):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], self._CHEMISTRY_ROWS,
        ]
        result = api.list_organisms(conn=mock_conn)
        cap = result["top_metabolic_capability"]
        assert len(cap) == 2
        # EZ55 has higher catalyzed_metabolite_count (1428 > 1039) — first
        assert cap[0]["organism_name"] == "Alteromonas macleodii EZ55"
        assert cap[0]["catalyzed_metabolite_count"] == 1428
        assert cap[0]["reaction_count"] == 1348
        assert cap[1]["organism_name"] == "Prochlorococcus MED4"

    def test_top_metabolic_capability_entries_carry_transported_metabolite_count(
        self, mock_conn,
    ):
        """substrate_depth migration: top_metabolic_capability[] entries gain
        transported_metabolite_count as a column; ranking stays
        catalyzed_metabolite_count desc (EZ55 first despite lower transport
        breadth)."""
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], self._CHEMISTRY_ROWS,
        ]
        result = api.list_organisms(conn=mock_conn)
        cap = result["top_metabolic_capability"]
        assert cap[0]["organism_name"] == "Alteromonas macleodii EZ55"
        assert cap[0]["transported_metabolite_count"] == 95
        assert cap[1]["transported_metabolite_count"] == 120
        assert set(cap[0]) == {
            "organism_name", "reaction_count", "catalyzed_metabolite_count",
            "transported_metabolite_count",
        }

    def test_top_metabolic_capability_excludes_zero_chemistry(self, mock_conn):
        rows = [
            {**dict(self._ROWS[0]),
             "reaction_count": 943, "catalyzed_metabolite_count": 1039},
            {**dict(self._ROWS[1]),
             "reaction_count": 0, "catalyzed_metabolite_count": 0},
        ]
        mock_conn.execute_query.side_effect = [[self._SUMMARY_ROW], rows]
        result = api.list_organisms(conn=mock_conn)
        cap = result["top_metabolic_capability"]
        assert len(cap) == 1
        assert cap[0]["organism_name"] == "Prochlorococcus MED4"

    def test_top_metabolic_capability_empty_when_no_matches(self, mock_conn):
        empty_summary = {**self._SUMMARY_ROW, "total_entries": 0, "total_matching": 0}
        mock_conn.execute_query.side_effect = [[empty_summary], []]
        result = api.list_organisms(conn=mock_conn)
        assert result["top_metabolic_capability"] == []

    def test_top_metabolic_capability_summary_mode(self, mock_conn):
        """summary=True populates top_metabolic_capability via the dedicated
        capability builder, NOT the detail builder. Asserts call count = 2
        (summary + capability) so the summary fast path stays cheap."""
        capability_rows = [
            {"organism_name": r["organism_name"],
             "reaction_count": r["reaction_count"],
             "catalyzed_metabolite_count": r["catalyzed_metabolite_count"],
             "transported_metabolite_count": r["transported_metabolite_count"]}
            for r in self._CHEMISTRY_ROWS
        ]
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], capability_rows,
        ]
        result = api.list_organisms(summary=True, conn=mock_conn)
        assert result["results"] == []
        assert len(result["top_metabolic_capability"]) == 2
        assert (result["top_metabolic_capability"][0]
                ["catalyzed_metabolite_count"]) == 1428
        assert (result["top_metabolic_capability"][0]
                ["transported_metabolite_count"]) == 95
        # Exactly 2 Cypher calls: summary + capability. No detail builder.
        assert mock_conn.execute_query.call_count == 2
        # Verify the second call used the capability builder (3-column projection)
        second_cypher = mock_conn.execute_query.call_args_list[1][0][0]
        assert "catalyzed_metabolite_count" in second_cypher
        # Capability builder doesn't pull verbose detail columns
        assert "lineage" not in second_cypher
        assert "derived_metric_count" not in second_cypher

    def test_top_metabolic_capability_top_10_cap(self, mock_conn):
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
                "reaction_count": i, "catalyzed_metabolite_count": i * 10,
            }
            for i in range(15)  # 15 organisms; org00 has count=0 so excluded
        ]
        summary = {**self._SUMMARY_ROW, "total_entries": 15, "total_matching": 15}
        mock_conn.execute_query.side_effect = [[summary], rows]
        result = api.list_organisms(conn=mock_conn)
        cap = result["top_metabolic_capability"]
        assert len(cap) == 10  # capped
        # Top entry should be Org14 (highest catalyzed_metabolite_count = 140)
        assert cap[0]["organism_name"] == "Org14"
        assert cap[0]["catalyzed_metabolite_count"] == 140

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
            [{"organisms": ["Prochlorococcus MED4"]}],    # resolver
            [filtered_summary],                          # summary
            self._ROWS[:1],                              # detail (MED4 only)
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

    def test_compartment_filter_param_passes_through(self, mock_conn, monkeypatch):
        monkeypatch.setattr(api, "_closed_vocab_warnings", lambda *a, **k: [])
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

    def test_empty_search_text_is_browse_mode(self, mock_conn):
        # Retired "search_text must not be empty" (spec §11/§13): empty or
        # whitespace-only search_text now selects browse mode.
        mock_conn.execute_query.return_value = []
        for text in ("", "   "):
            mock_conn.execute_query.reset_mock()
            result = api.search_ontology(text, "go_bp", conn=mock_conn)
            assert result["mode"] == "browse"
            cyphers = [c.args[0] for c in mock_conn.execute_query.call_args_list]
            assert cyphers and all("db.index.fulltext" not in c for c in cyphers)

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

    def test_lucene_retry_adds_sanitised_warning(self, mock_conn):
        """When the escaped retry succeeds, the envelope names the
        sanitised text actually used (llm-review 2b.3)."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("bad"),
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.search_ontology("nitrogen AND (", "go_bp", conn=mock_conn)
        assert any(
            "search_text was sanitised to" in w for w in result["warnings"]
        )

    def test_lucene_retry_success_does_not_warn(self, mock_conn):
        """No warning when the query never needed escaping."""
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.search_ontology("DNA replication", "go_bp", conn=mock_conn)
        assert not any(
            "sanitised" in w for w in result["warnings"]
        )

    def test_lucene_parse_error_survives_retry_raises_readable_valueerror(self, mock_conn):
        """When the escaped retry also fails, the raw ClientError must not
        leak (llm-review 2b.3)."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("Invalid input ParseException"),
            Neo4jClientError("Invalid input ParseException"),
        ]
        with pytest.raises(ValueError, match=r"is not valid Lucene syntax"):
            api.search_ontology("nitrogen AND (", "go_bp", conn=mock_conn)

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
             "best_effort": be, "n_genes": n, "cat_freqs": freqs,
             "is_informative": True}
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

    def test_summary_mode_returns_no_rows(self, mock_conn):
        """Summary mode returns no rows, but still rolls up the trust axes —
        the full-match trust projection runs in place of the paged detail."""
        mock_conn.execute_query.side_effect = [
            self._org_resolve(),
            self._per_term_rows(
                ("go:0022414", "reproductive process", 1, False, 7,
                 [{"item": "Cell cycle", "count": 7}]),
            ),
            self._per_gene_rows(("PMM0001", "Cell cycle", 1, [1])),
            self._detail_rows(n=1),  # Query C — rollups only, never returned
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
        # org-resolve + A + B + C; the paged detail query never runs.
        assert mock_conn.execute_query.call_count == 4

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
            # Annotation-trust surface (design section 5.1). `evidence_score_signals`
            # is deliberately absent: it appears only when `min_evidence_score`
            # is set, and this call applies no cutoff.
            "trust_axes", "by_evidence", "by_tier", "by_sources", "by_call_class",
            "evidence_score_stats", "filters_applied", "skipped_ontologies",
            "warnings",
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
            [],  # case-mismatch lookup over not_found
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

        api.gene_ontology_terms(["PMM0001"], organism="MED4", conn=mock_conn)
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

    def test_passes_params(self, mock_conn, monkeypatch):
        """All filter params are forwarded to builders."""
        monkeypatch.setattr(api, "_closed_vocab_warnings", lambda *a, **k: [])
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 21, "total_matching": 5}],
            [{"doi": "10.1234/test"}],
        ]
        api.list_publications(
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

    def test_lucene_parse_error_survives_retry_raises_readable_valueerror(self, mock_conn):
        """When the escaped retry also fails with a Lucene parse error, the
        raw ClientError must not leak (llm-review 2b.3)."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("Invalid input ParseException"),
            Neo4jClientError("Invalid input ParseException"),
        ]
        with pytest.raises(ValueError, match=r"is not valid Lucene syntax"):
            api.list_publications(search_text="DNA [repair", conn=mock_conn)

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

    def test_compartment_filter_passed_to_builders(self, mock_conn, monkeypatch):
        """compartment param is forwarded to summary and detail builders."""
        monkeypatch.setattr(api, "_closed_vocab_warnings", lambda *a, **k: [])
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
            "is_time_course": "single_time_point",
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
            is_time_course="time_course",
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

    def test_passes_params(self, mock_conn, monkeypatch):
        """All filter params forwarded to builders."""
        monkeypatch.setattr(api, "_closed_vocab_warnings", lambda *a, **k: [])
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
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
            [self._detail_row(is_time_course="time_course"),
             self._detail_row(is_time_course="single_time_point")],
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
            [self._detail_row(is_time_course="single_time_point")],
        ]
        result = api.list_experiments(conn=mock_conn)
        assert "timepoints" not in result["results"][0]

    def test_sentinel_conversion(self, mock_conn):
        """Sentinel values converted: '' timepoint -> None, -1.0 hours -> None."""
        tc_row = self._detail_row(
            is_time_course="time_course",
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
                is_time_course="time_course",
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

    def test_compartment_filter_passed_to_builders(self, mock_conn, monkeypatch):
        """compartment param is forwarded to summary and detail builder calls."""
        monkeypatch.setattr(api, "_closed_vocab_warnings", lambda *a, **k: [])
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

    def test_lucene_parse_error_survives_retry_raises_readable_valueerror(self, mock_conn):
        """When the escaped retry also fails with a Lucene parse error, the
        raw ClientError must not leak (llm-review 2b.3)."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("Invalid input ParseException"),
            Neo4jClientError("Invalid input ParseException"),
        ]
        with pytest.raises(ValueError, match=r"is not valid Lucene syntax"):
            api.list_experiments(search_text="nitrogen AND (", conn=mock_conn)


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
                    "is_time_course": "time_course",
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
            "filtered_out": [],
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
                    "is_time_course": "single_time_point",
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
                    "is_time_course": "single_time_point",
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
        """Non-time-course experiments have timepoints=None with
        verbose=True; compact (default) drops the key entirely
        (llm-review 2b.2)."""
        exp_summary = [{
            "organism_name": "Prochlorococcus MED4",
            "experiments": [
                {
                    "experiment_id": "single_tp",
                    "experiment_name": "Single",
                    "treatment_type": "x",
                    "omics_type": "RNASEQ",
                    "coculture_partner": None,
                    "is_time_course": "single_time_point",
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
        assert "timepoints" not in result["experiments"][0]

        mock_conn.execute_query.side_effect = [
            self._organism_result(),
            self._global_summary(total_matching=5, matching_genes=1),
            exp_summary,
            self._diagnostics_summary(),
            self._detail_rows(),
        ]
        verbose_result = api.differential_expression_by_gene(
            organism="MED4", verbose=True, conn=mock_conn
        )
        assert verbose_result["experiments"][0]["timepoints"] is None

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
                "filtered_out": [],
            }],
            [],  # case-mismatch lookup over not_found
            self._detail_rows(),
        ]
        result = api.differential_expression_by_gene(
            locus_tags=["PMM0001", "FAKE_GENE", "PMM9999"], conn=mock_conn
        )
        assert result["not_found"] == ["FAKE_GENE"]
        assert result["no_expression"] == ["PMM9999"]

    def test_vocabulary_typo_lands_in_filtered_out_not_no_expression(self, mock_conn):
        """A gene with expression edges that don't survive growth_phases
        must land in filtered_out, never no_expression (llm-review 2b.1)."""
        mock_conn.execute_query.side_effect = [
            self._organism_result(),           # locus_tags pre-query
            self._global_summary(),
            self._experiment_summary(),
            [{
                "top_categories": [],
                "not_found": [],
                "no_expression": [],
                "filtered_out": ["PMM1171"],
            }],
            [],
        ]
        with patch(
            "multiomics_explorer.api.functions._read_vocab_values",
            return_value={
                "values": ["exponential", "stationary"],
                "value_descriptions": {}, "description": None,
                "source": "vocabulary", "warning": None,
            },
        ):
            result = api.differential_expression_by_gene(
                locus_tags=["PMM1171"], growth_phases=["log"], conn=mock_conn,
            )
        assert result["filtered_out"] == ["PMM1171"]
        assert result["no_expression"] == []
        assert len(result["warnings"]) == 1
        assert result["warnings"][0].startswith(
            "growth_phases value 'log' matched nothing"
        )

    def test_no_growth_phases_no_warnings(self, mock_conn):
        """warnings is always present and empty when growth_phases is unset."""
        mock_conn.execute_query.side_effect = self._mock_side_effect_organism_only()
        result = api.differential_expression_by_gene(
            organism="MED4", conn=mock_conn
        )
        assert result["warnings"] == []
        assert result["filtered_out"] == []

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

    def _two_experiment_two_timepoint_summary(self):
        """Mock per-experiment summary: two experiments, two timepoints each
        (llm-review 2b.2 — experiments[] compaction fixture)."""
        def _exp(exp_id):
            return {
                "experiment_id": exp_id,
                "experiment_name": f"Test experiment {exp_id}",
                "treatment_type": "nitrogen_stress",
                "background_factors": ["axenic"],
                "omics_type": "RNASEQ",
                "coculture_partner": None,
                "is_time_course": "time_course",
                "table_scope": "all_detected_genes",
                "table_scope_detail": None,
                "matching_genes": 5,
                "rows_by_status": [
                    {"item": "significant_up", "count": 3},
                    {"item": "not_significant", "count": 12},
                ],
                "timepoints": [
                    {
                        "timepoint": "day 18", "timepoint_hours": 432.0,
                        "timepoint_order": 1, "matching_genes": 5,
                        "rows_by_status": [
                            {"item": "not_significant", "count": 5},
                        ],
                    },
                    {
                        "timepoint": "day 31", "timepoint_hours": 744.0,
                        "timepoint_order": 2, "matching_genes": 5,
                        "rows_by_status": [
                            {"item": "significant_up", "count": 3},
                        ],
                    },
                ],
            }
        return [{
            "organism_name": "Prochlorococcus MED4",
            "experiments": [_exp("exp1"), _exp("exp2")],
        }]

    def test_compact_experiments_drop_verbose_fields_by_default(self, mock_conn):
        """(llm-review 2b.2, controller ruling) Compact experiments[]
        entries carry the seven always-present keys (including omics_type
        — cheap and needed to distinguish RNASEQ vs PROTEOMICS entries);
        experiment_count counts before any trimming."""
        mock_conn.execute_query.side_effect = [
            self._organism_result(),
            self._global_summary(),
            self._two_experiment_two_timepoint_summary(),
            self._diagnostics_summary(),
            self._detail_rows(),
        ]
        result = api.differential_expression_by_gene(
            organism="MED4", conn=mock_conn
        )
        assert result["experiment_count"] == 2
        for exp in result["experiments"]:
            assert set(exp.keys()) == {
                "experiment_id", "treatment_type", "table_scope",
                "is_time_course", "matching_genes", "rows_by_status",
                "omics_type",
            }
            assert exp["omics_type"] == "RNASEQ"
            assert "timepoints" not in exp
            assert "experiment_name" not in exp
            assert "coculture_partner" not in exp

    def test_verbose_experiments_restore_dropped_fields(self, mock_conn):
        """verbose=True restores experiment_name, background_factors,
        coculture_partner, table_scope_detail, timepoints (omics_type is
        always present, compact or verbose — controller ruling)."""
        mock_conn.execute_query.side_effect = [
            self._organism_result(),
            self._global_summary(),
            self._two_experiment_two_timepoint_summary(),
            self._diagnostics_summary(),
            self._detail_rows(),
        ]
        result = api.differential_expression_by_gene(
            organism="MED4", verbose=True, conn=mock_conn
        )
        assert result["experiment_count"] == 2
        for exp in result["experiments"]:
            assert exp["experiment_name"].startswith("Test experiment")
            assert exp["timepoints"] is not None
            assert len(exp["timepoints"]) == 2
            assert exp["background_factors"] == ["axenic"]
            assert exp["omics_type"] == "RNASEQ"
            assert exp["coculture_partner"] is None
            assert exp["table_scope_detail"] is None


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

    def test_lucene_retry(self, mock_conn):
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("bad"),
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
        result = api.search_homolog_groups("bad+query", conn=mock_conn)
        assert mock_conn.execute_query.call_count == 3
        assert result["returned"] == 1

    def test_lucene_parse_error_survives_retry_raises_readable_valueerror(self, mock_conn):
        """When the escaped retry also fails with a Lucene parse error, the
        raw ClientError must not leak (llm-review 2b.3)."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("Invalid input ParseException"),
            Neo4jClientError("Invalid input ParseException"),
        ]
        with pytest.raises(ValueError, match=r"is not valid Lucene syntax"):
            api.search_homolog_groups("photosystem AND", conn=mock_conn)

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

    def test_by_organism_tie_break_is_deterministic(self, mock_conn):
        """Equal-count organisms sort by count DESC then organism_name ASC.

        apoc.coll.frequencies (the Cypher source of by_organism) has no
        defined tie order, so ties can reorder between KG builds unless
        the api layer applies a deterministic secondary sort key.
        """
        mock_conn.execute_query.side_effect = [
            [{"total_matching": 6, "total_genes": 6, "total_categories": 1,
              "by_organism": [
                  {"item": "Zeta organism", "count": 2},
                  {"item": "Alpha organism", "count": 2},
                  {"item": "Middle organism", "count": 3},
              ],
              "by_category_raw": [],
              "by_group_raw": [{"item": "cyanorak:CK_00000570", "count": 6}],
              "not_found_groups": [], "not_matched_groups": []}],
        ]
        result = api.genes_by_homolog_group(
            ["cyanorak:CK_00000570"], summary=True, conn=mock_conn)
        assert result["by_organism"] == [
            {"organism_name": "Middle organism", "count": 3},
            {"organism_name": "Alpha organism", "count": 2},
            {"organism_name": "Zeta organism", "count": 2},
        ]

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

    def _make_envelope_result(self, found=None, has_expression=None, has_significant=None, group_totals=None, has_any_edge=None):
        he = has_expression or ["PMM0370"]
        return [{
            "found_genes": found or ["PMM0370"],
            "has_expression": he,
            "has_significant": has_significant or ["PMM0370"],
            # Defaults to has_expression — matches pre-fix behavior for every
            # test that doesn't explicitly exercise the filtered_out split.
            "has_any_edge": he if has_any_edge is None else has_any_edge,
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
            [],  # case-mismatch lookup over not_found
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

    def test_vocabulary_typo_lands_in_filtered_out_not_no_expression(self, mock_conn):
        """A gene with edges that don't survive treatment_types must land in
        filtered_out, never no_expression (llm-review 2b.1)."""
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(
                found=["PMM0370", "PMM1234"], has_expression=["PMM0370"],
                has_any_edge=["PMM0370", "PMM1234"],
            ),
            self._make_agg_rows(),
        ]
        with patch(
            "multiomics_explorer.api.functions._read_vocab_values",
            return_value={
                "values": ["nitrogen", "coculture"],
                "value_descriptions": {}, "description": None,
                "source": "vocabulary", "warning": None,
            },
        ):
            result = api.gene_response_profile(
                locus_tags=["PMM0370", "PMM1234"], treatment_types=["Fe"],
                conn=mock_conn,
            )
        assert result["filtered_out"] == ["PMM1234"]
        assert result["no_expression"] == []
        assert len(result["warnings"]) == 1
        assert result["warnings"][0].startswith(
            "treatment_types value 'Fe' matched nothing"
        )

    def test_no_treatment_types_no_warnings(self, mock_conn):
        """warnings is always present and empty when treatment_types is unset."""
        mock_conn.execute_query.side_effect = [
            [{"organisms": [self._ORGANISM]}],
            self._make_envelope_result(),
            self._make_agg_rows(),
        ]
        result = api.gene_response_profile(locus_tags=["PMM0370"], conn=mock_conn)
        assert result["warnings"] == []
        assert result["filtered_out"] == []

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

    def test_lucene_retry(self, mock_conn):
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("bad"),
            [self._SUMMARY_RESULT_WITH_SCORE],
            [{**self._DETAIL_ROW, "score": 5.2}],
        ]
        result = api.list_clustering_analyses(
            search_text="nitrogen AND (", conn=mock_conn)
        assert result["returned"] == 1
        assert mock_conn.execute_query.call_count == 3

    def test_lucene_parse_error_survives_retry_raises_readable_valueerror(self, mock_conn):
        """When the escaped retry also fails with a Lucene parse error, the
        raw ClientError must not leak (llm-review 2b.3)."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        mock_conn.execute_query.side_effect = [
            Neo4jClientError("Invalid input ParseException"),
            Neo4jClientError("Invalid input ParseException"),
        ]
        with pytest.raises(ValueError, match=r"is not valid Lucene syntax"):
            api.list_clustering_analyses(
                search_text="nitrogen AND (", conn=mock_conn)


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
            [],  # case-mismatch lookup over not_found
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
            "analysis_exists": True,
        }
        mock_conn.execute_query.side_effect = [
            [summary_with_analysis],
            [self._DETAIL_ROW],
        ]
        result = api.genes_in_cluster(
            analysis_id="ca:tolonen2006:med4:nitrogen", conn=mock_conn)
        assert result["analysis_name"] == "MED4 nitrogen stress clustering"
        assert result["total_matching"] == 5
        assert result["not_found_analysis"] is None

    def test_analysis_id_summary_mode(self, mock_conn):
        summary_with_analysis = {
            **self._SUMMARY_RESULT,
            "analysis_name": "MED4 nitrogen stress clustering",
            "analysis_exists": True,
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
        assert result["not_found_analysis"] is None

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

    def test_unknown_analysis_id_sets_not_found_analysis(self, mock_conn):
        # llm-review 2b.3 Task 5: analysis_exists=False (builder's OPTIONAL
        # MATCH split) -> not_found_analysis set to the id + a warning,
        # instead of silently reporting an indistinguishable empty result.
        summary_unknown = {
            "total_matching": 0,
            "by_organism": [],
            "by_cluster": [],
            "by_category_raw": [],
            "not_found_clusters": [],
            "not_matched_clusters": [],
            "analysis_name": None,
            "analysis_exists": False,
        }
        mock_conn.execute_query.side_effect = [
            [summary_unknown],
        ]
        result = api.genes_in_cluster(
            analysis_id="nope", summary=True, conn=mock_conn)
        assert result["not_found_analysis"] == "nope"
        assert any(
            "nope" in w and "list_clustering_analyses" in w
            for w in result["warnings"]
        )

    def test_known_analysis_id_no_not_found_analysis(self, mock_conn):
        summary_with_analysis = {
            **self._SUMMARY_RESULT,
            "analysis_name": "MED4 nitrogen stress clustering",
            "analysis_exists": True,
        }
        mock_conn.execute_query.side_effect = [
            [summary_with_analysis],
        ]
        result = api.genes_in_cluster(
            analysis_id="ca:tolonen2006:med4:nitrogen",
            summary=True, conn=mock_conn)
        assert result["not_found_analysis"] is None
        assert result["warnings"] == []

    def test_cluster_ids_mode_no_not_found_analysis(self, mock_conn):
        # analysis_exists is not a concept in cluster_ids mode.
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT],
        ]
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            summary=True, conn=mock_conn)
        assert result["not_found_analysis"] is None
        assert result["warnings"] == []

    def test_analysis_id_zero_rows_same_organism_no_mismatch(self, mock_conn):
        """llm-review 2b.3 Task 5 controller fix: analysis_id mode used to
        flag not_matched_organism on ANY zero-row result. Now it compares
        the analysis's own ca_organism_name against the requested organism
        -- when they genuinely match, zero cluster->gene rows is a normal
        empty result (not_matched_organism stays None), letting
        cluster_enrichment_inputs reach its "exists but empty" warning
        branch instead of misreporting a wrong-organism mismatch."""
        summary_zero_same_org = {
            "total_matching": 0,
            "by_organism": [],
            "by_cluster": [],
            "by_category_raw": [],
            "not_found_clusters": [],
            "not_matched_clusters": [],
            "analysis_name": "Test Analysis",
            "analysis_exists": True,
            "ca_organism_name": "Prochlorococcus MED4",
        }
        mock_conn.execute_query.side_effect = [
            [summary_zero_same_org],
            [],  # detail query: no gene rows
        ]
        result = api.genes_in_cluster(
            analysis_id="ca:test", organism="MED4", conn=mock_conn)
        assert result["not_found_analysis"] is None
        assert result["not_matched_organism"] is None
        assert result["total_matching"] == 0

    def test_analysis_id_zero_rows_different_organism_sets_mismatch(self, mock_conn):
        """The genuine-mismatch case: the analysis's own organism differs
        from the requested one -> not_matched_organism is set to the
        requested organism (unchanged contract for a real mismatch)."""
        summary_zero_diff_org = {
            "total_matching": 0,
            "by_organism": [],
            "by_cluster": [],
            "by_category_raw": [],
            "not_found_clusters": [],
            "not_matched_clusters": [],
            "analysis_name": "Test Analysis",
            "analysis_exists": True,
            "ca_organism_name": "Prochlorococcus MED4",
        }
        mock_conn.execute_query.side_effect = [
            [summary_zero_diff_org],
            [],  # detail query: no gene rows
        ]
        result = api.genes_in_cluster(
            analysis_id="ca:test", organism="MIT9515", conn=mock_conn)
        assert result["not_found_analysis"] is None
        assert result["not_matched_organism"] == "MIT9515"
        assert result["total_matching"] == 0

    def test_analysis_id_zero_rows_unknown_ca_organism_no_mismatch(self, mock_conn):
        """A missing ca_organism_name (e.g. a real analysis that somehow
        carries no organism_name) must never be manufactured into a
        mismatch -- not_found_analysis / a genuine word-match are the only
        signals allowed to set not_matched_organism."""
        summary_zero_no_org = {
            "total_matching": 0,
            "by_organism": [],
            "by_cluster": [],
            "by_category_raw": [],
            "not_found_clusters": [],
            "not_matched_clusters": [],
            "analysis_name": "Test Analysis",
            "analysis_exists": True,
            "ca_organism_name": None,
        }
        mock_conn.execute_query.side_effect = [
            [summary_zero_no_org],
            [],
        ]
        result = api.genes_in_cluster(
            analysis_id="ca:test", organism="MED4", conn=mock_conn)
        assert result["not_matched_organism"] is None


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

    def test_sibling_warning_on_value_kind_mismatch_with_ids(
            self, mock_summary_result):
        # (llm-review 2b.3) value_kind + derived_metric_ids where the id
        # actually resolves to a different kind → sibling-tool warning
        # (the row itself already lands in not_matched via the
        # value_kind-gated OPTIONAL MATCH; this only adds the warning).
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        kind_rows = [{
            "derived_metric_id": "dm:foo", "metric_type": "damping_ratio",
            "value_kind": "numeric",
        }]
        mock_conn.execute_query.side_effect = [
            kind_rows, mock_summary_result, [],
        ]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], derived_metric_ids=["dm:foo"],
                value_kind="boolean", conn=mock_conn,
            )
        assert any(
            "dm:foo exists as value_kind=numeric" in w
            and "genes_by_numeric_metric" in w
            for w in data["warnings"]
        )

    def test_sibling_warning_on_value_kind_mismatch_with_metric_types(
            self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        kind_rows = [{
            "derived_metric_id": "dm:foo", "metric_type": "damping_ratio",
            "value_kind": "numeric",
        }]
        mock_conn.execute_query.side_effect = [
            kind_rows, mock_summary_result, [],
        ]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], metric_types=["damping_ratio"],
                value_kind="boolean", conn=mock_conn,
            )
        assert any(
            "damping_ratio exists as value_kind=numeric" in w
            and "genes_by_numeric_metric" in w
            for w in data["warnings"]
        )

    def test_no_sibling_warning_when_kind_matches(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        kind_rows = [{
            "derived_metric_id": "dm:foo", "metric_type": "damping_ratio",
            "value_kind": "numeric",
        }]
        mock_conn.execute_query.side_effect = [
            kind_rows, mock_summary_result, [],
        ]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], derived_metric_ids=["dm:foo"],
                value_kind="numeric", conn=mock_conn,
            )
        assert not any("exists as value_kind=" in w for w in data["warnings"])

    def test_no_kind_lookup_query_without_value_kind(self, mock_summary_result):
        # No value_kind filter → no sibling-lookup query (only summary +
        # detail).
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [mock_summary_result, []]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            api.gene_derived_metrics(
                ["PMM1714"], derived_metric_ids=["dm:foo"], conn=mock_conn,
            )
        assert mock_conn.execute_query.call_count == 2


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
            self, diag_rankable, summary_row, monkeypatch):
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row, []]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"],
            organism="Alteromonas",  # no match in by_organism
            conn=mock_conn,
        )
        assert data["not_matched_organism"] == "Alteromonas"

    def test_not_matched_organism_none_when_match(
            self, diag_rankable, summary_row, monkeypatch):
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row, []]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"],
            organism="Prochlorococcus MED4",
            conn=mock_conn,
        )
        assert data["not_matched_organism"] is None

    def test_not_matched_organism_warning_lists_dm_organisms(
            self, diag_rankable, summary_row, monkeypatch):
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_rankable, summary_row, []]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"],
            organism="Alteromonas",
            conn=mock_conn,
        )
        assert any("Prochlorococcus MED4" in w for w in data["warnings"])

    def test_organism_mismatch_not_confused_with_absent_metric_type(
            self, monkeypatch):
        # (llm-review 2b.3 bug fix) organism passed + metric_type doesn't
        # exist at all (any organism) → not_matched_organism stays None.
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [[]]  # diagnostics empty
        data = api.genes_by_numeric_metric(
            metric_types=["totally_fake_metric_xyz"],
            organism="MED4",
            conn=mock_conn,
        )
        assert data["not_matched_organism"] is None
        assert data["not_found_metric_types"] == ["totally_fake_metric_xyz"]

    def test_kind_mismatch_moves_to_not_matched_with_sibling_warning(self):
        # A boolean DM id passed here is found by diagnostics (no more
        # value_kind predicate) but its actual kind differs — moves to
        # not_matched_ids with a sibling-tool warning.
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [[{
            "derived_metric_id": "dm:vp_med4",
            "metric_type": "vesicle_proteome_member",
            "value_kind": "boolean",
            "name": "Vesicle proteome member (MED4)",
            "rankable": False,
            "has_p_value": False,
            "total_gene_count": 32,
            "organism_name": "Prochlorococcus MED4",
        }]]
        data = api.genes_by_numeric_metric(
            derived_metric_ids=["dm:vp_med4"], conn=mock_conn,
        )
        assert mock_conn.execute_query.call_count == 1  # short-circuit
        assert data["not_found_ids"] == []
        assert data["not_matched_ids"] == ["dm:vp_med4"]
        assert any(
            "dm:vp_med4 exists as value_kind=boolean" in w
            and "genes_by_boolean_metric" in w
            for w in data["warnings"]
        )

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

    def _full_detail_row(self):
        return {
            "locus_tag": "PMM0001", "gene_name": "rpsH", "product": "ribosomal",
            "gene_category": "Translation", "organism_name": "Prochlorococcus MED4",
            "derived_metric_id": "dm:dr", "name": "Damping ratio",
            "value_kind": "numeric", "rankable": True, "has_p_value": False,
            "value": 1.5, "rank_by_metric": 1, "metric_percentile": 99.0,
            "metric_bucket": "top_decile",
        }

    def test_compact_drops_parent_constant_fields(
            self, diag_rankable, summary_row):
        """verbose=False (default) strips name/value_kind/rankable/
        has_p_value/organism_name — all duplicated on the by_metric /
        by_organism envelope rollups (llm-review 2b.2 Task 5)."""
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_rankable, summary_row, [self._full_detail_row()],
        ]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"], conn=mock_conn,
        )
        row = data["results"][0]
        for dropped in ("name", "value_kind", "rankable", "has_p_value",
                        "organism_name"):
            assert dropped not in row, f"{dropped} should be dropped compact"
        for kept in ("locus_tag", "gene_name", "product", "gene_category",
                     "derived_metric_id", "value", "rank_by_metric",
                     "metric_percentile", "metric_bucket"):
            assert kept in row, f"{kept} should remain in compact row"

    def test_verbose_keeps_parent_constant_fields(
            self, diag_rankable, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_rankable, summary_row, [self._full_detail_row()],
        ]
        data = api.genes_by_numeric_metric(
            metric_types=["damping_ratio"], verbose=True, conn=mock_conn,
        )
        row = data["results"][0]
        for kept in ("name", "value_kind", "rankable", "has_p_value",
                     "organism_name"):
            assert kept in row, f"{kept} should survive verbose=True"


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

    def test_kind_mismatch_moves_to_not_matched_with_sibling_warning(self):
        # (llm-review 2b.3) diagnostics no longer filters by value_kind —
        # the numeric DM is found, but its actual kind differs from what
        # genes_by_boolean_metric expects, so it moves to not_matched_ids
        # (not not_found_ids) with a sibling-tool warning.
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [[{
            "derived_metric_id": "dm:numeric_dr",
            "metric_type": "damping_ratio",
            "value_kind": "numeric",
            "name": "Damping ratio",
            "total_gene_count": 320,
            "organism_name": "Prochlorococcus MED4",
        }]]
        data = api.genes_by_boolean_metric(
            derived_metric_ids=["dm:numeric_dr"], conn=mock_conn,
        )
        assert mock_conn.execute_query.call_count == 1  # short-circuit
        assert data["not_found_ids"] == []
        assert data["not_matched_ids"] == ["dm:numeric_dr"]
        assert data["total_matching"] == 0
        assert data["results"] == []
        assert any(
            "dm:numeric_dr exists as value_kind=numeric" in w
            and "genes_by_numeric_metric" in w
            for w in data["warnings"]
        )

    def test_wrong_kind_metric_type_moves_to_not_matched_with_warning(self):
        # metric_types entry that only maps to a numeric DM.
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [[{
            "derived_metric_id": "dm:dr",
            "metric_type": "damping_ratio",
            "value_kind": "numeric",
            "name": "Damping ratio",
            "total_gene_count": 320,
            "organism_name": "Prochlorococcus MED4",
        }]]
        data = api.genes_by_boolean_metric(
            metric_types=["damping_ratio"], conn=mock_conn,
        )
        assert data["not_found_metric_types"] == []
        assert data["not_matched_metric_types"] == ["damping_ratio"]
        assert any(
            "damping_ratio exists as value_kind=numeric" in w
            and "genes_by_numeric_metric" in w
            for w in data["warnings"]
        )

    def test_truly_absent_id_still_not_found(self):
        # An id absent from the KG entirely (any kind) still lands in
        # not_found_ids — the kind-mismatch reclassification only applies
        # to ids diagnostics actually returns.
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [[]]
        data = api.genes_by_boolean_metric(
            derived_metric_ids=["dm:totally_fake"], conn=mock_conn,
        )
        assert data["not_found_ids"] == ["dm:totally_fake"]
        assert data["not_matched_ids"] == []
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
        # 3 calls: diag, summary, detail. flag → flag_str='flagged' on
        # summary + detail.
        assert mock_conn.execute_query.call_count == 3
        sum_kwargs = mock_conn.execute_query.call_args_list[1].kwargs
        det_kwargs = mock_conn.execute_query.call_args_list[2].kwargs
        assert sum_kwargs.get("flag_str") == "flagged"
        assert det_kwargs.get("flag_str") == "flagged"

    def test_flag_false_on_positive_only_dm_keeps_row_and_warns(
            self, diag_boolean):
        # (llm-review 2b.3) flag=False against a positive-only DM
        # (dm_false_count=0) keeps its by_metric row (count/false_count
        # both 0) and appends a warning pointing at false_count.
        summary_positive_only = [{
            "total_matching": 0, "total_derived_metrics": 0,
            "total_genes": 0,
            "by_organism": [], "by_compartment": [], "by_publication": [],
            "by_experiment": [], "by_value": [],
            "by_metric": [{
                "derived_metric_id": "dm:vp_med4",
                "name": "Vesicle proteome member (MED4)",
                "metric_type": "vesicle_proteome_member",
                "value_kind": "boolean",
                "count": 0, "true_count": 32, "false_count": 0,
                "dm_total_gene_count": 32, "dm_true_count": 32,
                "dm_false_count": 0,
            }],
            "top_categories_raw": [],
            "genes_per_metric_max": 0, "genes_per_metric_median": 0.0,
        }]
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_boolean, summary_positive_only, [],
        ]
        data = api.genes_by_boolean_metric(
            metric_types=["vesicle_proteome_member"],
            flag=False, conn=mock_conn,
        )
        assert len(data["by_metric"]) == 1
        assert data["by_metric"][0]["derived_metric_id"] == "dm:vp_med4"
        assert data["by_metric"][0]["count"] == 0
        assert data["by_metric"][0]["false_count"] == 0
        assert any(
            "dm:vp_med4 stores positive flags only" in w
            and "false_count" in w
            for w in data["warnings"]
        )

    def test_organism_mismatch_not_confused_with_absent_metric_type(
            self, monkeypatch):
        # (llm-review 2b.3 bug fix) organism passed + metric_type doesn't
        # exist at all (any organism) → not_matched_organism stays None
        # (it's a not_found, not an organism mismatch).
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [[]]  # diagnostics empty
        data = api.genes_by_boolean_metric(
            metric_types=["totally_fake_metric_xyz"],
            organism="MED4",
            conn=mock_conn,
        )
        assert data["not_matched_organism"] is None
        assert data["not_found_metric_types"] == ["totally_fake_metric_xyz"]

    def test_not_matched_organism_set_when_dm_exists_elsewhere(
            self, diag_boolean, monkeypatch):
        # DM genuinely exists (MED4) but the requested organism doesn't
        # match — not_matched_organism set, warning lists the DM's
        # organism(s), short-circuits before summary/detail.
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [diag_boolean]
        data = api.genes_by_boolean_metric(
            metric_types=["vesicle_proteome_member"],
            organism="Alteromonas",
            conn=mock_conn,
        )
        assert mock_conn.execute_query.call_count == 1  # short-circuit
        assert data["not_matched_organism"] == "Alteromonas"
        assert any(
            "Prochlorococcus MED4" in w for w in data["warnings"]
        )

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

    def _full_detail_row(self):
        return {
            "locus_tag": "PMM0090", "gene_name": "vp1", "product": "vesicle",
            "gene_category": "Cellular processes",
            "organism_name": "Prochlorococcus MED4",
            "derived_metric_id": "dm:vp_med4",
            "name": "Vesicle proteome member (MED4)",
            "value_kind": "boolean", "rankable": False, "has_p_value": False,
            "value": "flagged",
        }

    def test_compact_drops_parent_constant_fields(
            self, diag_boolean, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_boolean, summary_row, [self._full_detail_row()],
        ]
        data = api.genes_by_boolean_metric(
            metric_types=["vesicle_proteome_member"], conn=mock_conn,
        )
        row = data["results"][0]
        for dropped in ("name", "value_kind", "rankable", "has_p_value",
                        "organism_name"):
            assert dropped not in row, f"{dropped} should be dropped compact"
        for kept in ("locus_tag", "gene_name", "product", "gene_category",
                     "derived_metric_id", "value"):
            assert kept in row, f"{kept} should remain in compact row"

    def test_verbose_keeps_parent_constant_fields(
            self, diag_boolean, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_boolean, summary_row, [self._full_detail_row()],
        ]
        data = api.genes_by_boolean_metric(
            metric_types=["vesicle_proteome_member"],
            verbose=True, conn=mock_conn,
        )
        row = data["results"][0]
        for kept in ("name", "value_kind", "rankable", "has_p_value",
                     "organism_name"):
            assert kept in row, f"{kept} should survive verbose=True"


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

    def test_kind_mismatch_moves_to_not_matched_with_sibling_warning(self):
        # (llm-review 2b.3) a boolean DM id passed here is found by
        # diagnostics (no more value_kind predicate) but its actual kind
        # differs — moves to not_matched_ids with a sibling-tool warning.
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [[{
            "derived_metric_id": "dm:vp_med4",
            "metric_type": "vesicle_proteome_member",
            "value_kind": "boolean",
            "name": "Vesicle proteome member (MED4)",
            "total_gene_count": 32,
            "organism_name": "Prochlorococcus MED4",
            "allowed_categories": None,
        }]]
        data = api.genes_by_categorical_metric(
            derived_metric_ids=["dm:vp_med4"], conn=mock_conn,
        )
        assert mock_conn.execute_query.call_count == 1  # short-circuit
        assert data["not_found_ids"] == []
        assert data["not_matched_ids"] == ["dm:vp_med4"]
        assert data["total_matching"] == 0
        assert data["results"] == []
        assert any(
            "dm:vp_med4 exists as value_kind=boolean" in w
            and "genes_by_boolean_metric" in w
            for w in data["warnings"]
        )

    def test_truly_absent_id_still_not_found(self):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [[]]  # diagnostics empty
        data = api.genes_by_categorical_metric(
            derived_metric_ids=["dm:totally_fake"], conn=mock_conn,
        )
        assert data["not_found_ids"] == ["dm:totally_fake"]
        assert data["not_matched_ids"] == []
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

    def _full_detail_row(self):
        return {
            "locus_tag": "PMM0097", "gene_name": None, "product": "psortb",
            "gene_category": "Cellular processes",
            "organism_name": "Prochlorococcus MED4",
            "derived_metric_id": "dm:psortb_med4",
            "name": "PSORTb subcellular localization (MED4)",
            "value_kind": "categorical", "rankable": False,
            "has_p_value": False, "value": "Outer Membrane",
        }

    def test_compact_drops_parent_constant_fields(
            self, diag_categorical, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_categorical, summary_row, [self._full_detail_row()],
        ]
        data = api.genes_by_categorical_metric(
            metric_types=["predicted_subcellular_localization"],
            conn=mock_conn,
        )
        row = data["results"][0]
        for dropped in ("name", "value_kind", "rankable", "has_p_value",
                        "organism_name"):
            assert dropped not in row, f"{dropped} should be dropped compact"
        for kept in ("locus_tag", "product", "gene_category",
                     "derived_metric_id", "value"):
            assert kept in row, f"{kept} should remain in compact row"

    def test_verbose_keeps_parent_constant_fields(
            self, diag_categorical, summary_row):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            diag_categorical, summary_row, [self._full_detail_row()],
        ]
        data = api.genes_by_categorical_metric(
            metric_types=["predicted_subcellular_localization"],
            verbose=True, conn=mock_conn,
        )
        row = data["results"][0]
        for kept in ("name", "value_kind", "rankable", "has_p_value",
                     "organism_name"):
            assert kept in row, f"{kept} should survive verbose=True"


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

from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG


class TestOntologyLandscape:
    def _mock_conn(self, gene_count: int, per_ont_rows: dict):
        """Build a mock conn whose execute_query returns results keyed by
        the 'org' / 'experiment_ids' param dispatch implied by the Cypher.
        """
        conn = MagicMock()

        def run(cypher, **params):
            if "RETURN collect(DISTINCT o.preferred_name)" in cypher:
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
            if "RETURN collect(DISTINCT o.preferred_name)" in cypher:
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


class TestApiAcceptsTcdbCazy:
    """API entry points must accept ontology='tcdb' / 'cazy' once Phase 2
    lands. Use mocked conns — no Neo4j needed.
    """

    def _search_ontology_mock_conn(self):
        """Build a conn whose summary returns a well-formed 1-row dict and
        whose detail returns []. Matches the contract of real Cypher: the
        summary aggregator always returns exactly one row.
        """
        conn = MagicMock()
        summary_row = [{
            "total_entries": 0, "total_matching": 0,
            "score_max": None, "score_median": None,
        }]

        def run(cypher, **params):
            # Summary cypher uses `count(t) AS total_matching`; detail
            # uses `RETURN t.id AS id`. Discriminate on that.
            if "total_matching" in cypher:
                return summary_row
            return []

        conn.execute_query.side_effect = run
        return conn

    def test_search_ontology_accepts_tcdb(self):
        conn = self._search_ontology_mock_conn()
        # Should NOT raise — proves api.search_ontology accepts ontology='tcdb'.
        result = api.search_ontology("sucrose", "tcdb", conn=conn)
        assert "results" in result

    def test_search_ontology_accepts_cazy(self):
        conn = self._search_ontology_mock_conn()
        result = api.search_ontology("GH13", "cazy", conn=conn)
        assert "results" in result

    def test_ontology_landscape_sweeps_tcdb_cazy(self):
        """Default branch (no `ontology=` argument) sweeps ALL_ONTOLOGIES
        — once tcdb/cazy are in the list, the loop must produce rows for
        them too (12 results, not 10)."""
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG
        # Ensure spec preconditions hold under test (will be RED until
        # constants/config are extended)
        assert "tcdb" in ALL_ONTOLOGIES
        assert "cazy" in ALL_ONTOLOGIES
        assert "tcdb" in ONTOLOGY_CONFIG
        assert "cazy" in ONTOLOGY_CONFIG
        per_ont_rows = {
            ont: [
                {
                    "level": 0, "n_terms_with_genes": 1,
                    "n_genes_at_level": 50,
                    "min_genes_per_term": 50, "q1_genes_per_term": 50.0,
                    "median_genes_per_term": 50.0, "q3_genes_per_term": 50.0,
                    "max_genes_per_term": 50, "n_best_effort": 0,
                },
            ]
            for ont in ALL_ONTOLOGIES
        }
        conn = MagicMock()

        def run(cypher, **params):
            if "RETURN collect(DISTINCT o.preferred_name)" in cypher:
                return [{"organisms": ["Prochlorococcus MED4"]}]
            if "count(g) AS total_genes" in cypher:
                return [{"total_genes": 1976}]
            for ont, rows in per_ont_rows.items():
                cfg = ONTOLOGY_CONFIG[ont]
                if cfg["gene_rel"] in cypher and f":{cfg['label']}" in cypher:
                    return rows
            raise AssertionError(f"no mock for cypher:\n{cypher[:200]}")

        conn.execute_query.side_effect = run
        result = api.ontology_landscape(organism="MED4", conn=conn)
        ontology_types = {row["ontology_type"] for row in result["results"]}
        assert "tcdb" in ontology_types
        assert "cazy" in ontology_types
        # And the count surfaces both new dimensions
        assert result["n_ontologies"] == len(ALL_ONTOLOGIES)
        assert result["n_ontologies"] >= 12


def _patch_enrichment_preflight(monkeypatch):
    """Stub the live-KG preflight calls that pathway_enrichment /
    cluster_enrichment now make before their (already-mocked) DE / cluster
    inputs builders run — organism resolution, ontology level-range lookup,
    and (inside de_enrichment_inputs) experiment-metadata lookup — so these
    unit tests never touch Neo4j (llm-review 2b.1 finding I1).

    _validate_organism_inputs / _ontology_max_level are called as bare names
    within api/functions.py, so they patch directly on `api`.
    _call_list_experiments is a thin indirection inside
    multiomics_explorer.analysis.enrichment (re-imported fresh per call), so
    it patches on that module. Returning `{}` is safe: de_enrichment_inputs
    falls back to per-row DE metadata when exp_meta is empty.
    """
    import multiomics_explorer.analysis.enrichment as enr
    monkeypatch.setattr(
        api, "_validate_organism_inputs",
        lambda *a, **k: "Prochlorococcus MED4",
    )
    monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 3)
    monkeypatch.setattr(enr, "_call_list_experiments", lambda **k: {})


class TestPathwayEnrichment:
    """Input validation + orchestration for api.pathway_enrichment."""

    @pytest.fixture(autouse=True)
    def _enrichment_preflight(self, monkeypatch):
        _patch_enrichment_preflight(monkeypatch)

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
    def _stub_de_result(rows=(), not_found=(), not_matched=(), no_expression=(),
                        not_found_experiments=()):
        return {
            "organism_name": "MED4",
            "results": list(rows),
            "not_found": list(not_found),
            "not_matched": list(not_matched),
            "no_expression": list(no_expression),
            "not_found_experiments": list(not_found_experiments),
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

    def test_partial_unknown_experiments_no_raise(self, monkeypatch):
        """Renamed from test_vacuous_success_when_all_experiments_missing
        (llm-review 2b.1 finding M1): that name/body asserted the vacuous
        empty-envelope Task 4 eliminated for the ALL-unknown case, and only
        passed because its stub omitted `not_found_experiments` (the DE
        call's own not-found-experiment-ids key, distinct from the
        gene-level `not_found`). The all-unknown-raises case is covered by
        TestEnrichmentRaisesOnUnknownIdsAndBadLevel
        .test_pathway_enrichment_all_unknown_experiments_raises; this test
        now covers the complementary PARTIAL-batch contract through the
        real (unmocked) de_enrichment_inputs, exercising the DE-mock layer
        rather than the inputs-builder-mock layer Task 4 uses: one unknown
        id out of two does NOT raise, and the unknown one surfaces in
        `not_found_experiments`.
        """
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(not_found_experiments=["nope"]),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            lambda **_: self._stub_gbo_result(),
        )
        result = pathway_enrichment(
            organism="MED4", experiment_ids=["exp1", "nope"],
            ontology="cyanorak_role", level=1,
        )
        out = result.to_envelope()
        assert out["total_matching"] == 0
        assert out["results"] == []
        assert out["not_found_experiments"] == ["nope"]
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
                    "not_found_experiments",
                    "term_validation", "clusters_skipped", "results"):
            assert key in out, f"envelope missing key: {key}"


# ---------------------------------------------------------------------------
# llm-review 2b.2 Task 2 — include_nonsignificant wiring
#
# The exact-value filtering logic (does to_envelope actually drop rows,
# leave total_matching/n_significant/by_cluster alone) is covered directly
# in tests/unit/test_enrichment_result.py::TestToEnvelopeIncludeNonsignificant
# (hand-built EnrichmentResult, no fisher_ora involved). These tests cover
# the orchestration layer only: does pathway_enrichment / cluster_enrichment
# thread the parameter onto result.params so to_envelope sees it. fisher_ora
# is monkeypatched to return controlled p_adjust values (0.01, 0.04, 0.5 vs
# cutoff 0.05) since the real Fisher-exact computation can't be pinned to
# specific p-values from a tiny mocked gene set.
# ---------------------------------------------------------------------------


def _fake_fisher_ora_three_rows(cluster_name):
    """fisher_ora stand-in: one cluster, 3 term rows, p_adjust 0.01/0.04/0.5
    (2 significant of 3 at the default 0.05 cutoff)."""
    def _fisher_ora(inputs, term2gene, **_kwargs):
        import pandas as pd
        from multiomics_explorer.analysis.enrichment import EnrichmentResult
        df = pd.DataFrame([
            {"cluster": cluster_name, "term_id": "T1", "term_name": "Term1", "p_adjust": 0.01},
            {"cluster": cluster_name, "term_id": "T2", "term_name": "Term2", "p_adjust": 0.04},
            {"cluster": cluster_name, "term_id": "T3", "term_name": "Term3", "p_adjust": 0.5},
        ])
        return EnrichmentResult(
            kind="pathway", organism_name=inputs.organism_name, ontology=None, level=None,
            results=df, inputs=inputs, term2gene=term2gene,
        )
    return _fisher_ora


class TestPathwayEnrichmentIncludeNonsignificant:
    """pathway_enrichment(include_nonsignificant=...) orchestration."""

    @pytest.fixture(autouse=True)
    def _enrichment_preflight(self, monkeypatch):
        _patch_enrichment_preflight(monkeypatch)

    def _run(self, monkeypatch, **kwargs):
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: TestPathwayEnrichmentInformativeOnly._stub_de_result(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            lambda **_: TestPathwayEnrichment._stub_gbo_result(rows=[
                {"term_id": "T1", "term_name": "Term1", "locus_tag": "PMM0001"},
            ]),
        )
        monkeypatch.setattr(
            enr, "fisher_ora", _fake_fisher_ora_three_rows("exp1|T0|up"),
        )
        return pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
            min_gene_set_size=0,
            **kwargs,
        )

    def test_default_true_returns_all_rows(self, monkeypatch):
        result = self._run(monkeypatch)
        assert result.params["include_nonsignificant"] is True
        out = result.to_envelope()
        assert out["total_matching"] == 3
        assert out["n_significant"] == 2
        assert out["returned"] == 3

    def test_false_total_matching_is_pageable_subset(self, monkeypatch):
        """total_matching == n_significant when filtered (controller ruling,
        llm-review 2b.2 follow-up) — not the raw 3-row test count."""
        result = self._run(monkeypatch, include_nonsignificant=False)
        assert result.params["include_nonsignificant"] is False
        out = result.to_envelope()
        assert out["n_significant"] == 2
        assert out["total_matching"] == out["n_significant"]
        assert out["returned"] == 2
        assert len(out["results"]) == 2


class TestClusterEnrichmentIncludeNonsignificant:
    """cluster_enrichment(include_nonsignificant=...) orchestration."""

    @pytest.fixture(autouse=True)
    def _enrichment_preflight(self, monkeypatch):
        _patch_enrichment_preflight(monkeypatch)

    def _run(self, monkeypatch, **kwargs):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: TestClusterEnrichment._stub_inputs(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            lambda **_: TestClusterEnrichment._stub_gbo_result([
                {"term_id": "T1", "term_name": "Term1", "locus_tag": "PMM0001", "level": 1},
            ]),
        )
        monkeypatch.setattr(
            enr, "fisher_ora", _fake_fisher_ora_three_rows("Cluster A"),
        )
        return cluster_enrichment(
            analysis_id="ca:test", organism="MED4",
            ontology="cyanorak_role", level=1,
            min_gene_set_size=0,
            **kwargs,
        )

    def test_default_true_returns_all_rows(self, monkeypatch):
        result = self._run(monkeypatch)
        assert result.params["include_nonsignificant"] is True
        out = result.to_envelope()
        assert out["total_matching"] == 3
        assert out["n_significant"] == 2
        assert out["returned"] == 3

    def test_false_total_matching_is_pageable_subset(self, monkeypatch):
        """total_matching == n_significant when filtered (controller ruling,
        llm-review 2b.2 follow-up) — not the raw 3-row test count."""
        result = self._run(monkeypatch, include_nonsignificant=False)
        assert result.params["include_nonsignificant"] is False
        out = result.to_envelope()
        assert out["n_significant"] == 2
        assert out["total_matching"] == out["n_significant"]
        assert out["returned"] == 2
        assert len(out["results"]) == 2


# ---------------------------------------------------------------------------
# Task 4 (llm-review 2b.1) — raise on all-unknown ids / out-of-range level
# ---------------------------------------------------------------------------


class TestEnrichmentRaisesOnUnknownIdsAndBadLevel:
    """pathway_enrichment / cluster_enrichment fail loudly instead of
    returning a vacuous empty envelope; level is range-checked before any
    gene-set query.

    de_enrichment_inputs / cluster_enrichment_inputs are imported locally
    inside pathway_enrichment / cluster_enrichment (each call re-imports from
    multiomics_explorer.analysis.enrichment — see that module's `_call_de`
    docstring on why), so the patchable attribute lives on the `enrichment`
    module, not on `api`. _validate_organism_inputs / _ontology_max_level /
    genes_by_ontology are called as bare names within api/functions.py
    itself, so they patch directly on `api`.
    """

    def teardown_method(self, _method):
        api._MAX_LEVEL_CACHE.clear()

    def test_pathway_enrichment_all_unknown_experiments_raises(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(api, "_validate_organism_inputs", lambda *a, **k: "Prochlorococcus MED4")
        monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 3)
        fake_inputs = SimpleNamespace(
            gene_sets={}, background={}, cluster_metadata={},
            not_found=[], not_matched=[], no_expression=[],
            not_found_experiments=["nope"], clusters_skipped=[],
        )
        monkeypatch.setattr(enr, "de_enrichment_inputs", lambda *a, **k: fake_inputs)
        with pytest.raises(ValueError, match=r"experiment_ids not found: \['nope'\]"):
            api.pathway_enrichment(
                organism="MED4", experiment_ids=["nope"],
                ontology="kegg", level=1, conn=MagicMock(),
            )

    def test_pathway_enrichment_duplicate_unknown_experiments_raises(self, monkeypatch):
        """M3 (llm-review 2b.1): the all-unknown check must use set
        comparison, not a length comparison — ``experiment_ids=['nope',
        'nope']`` has len 2 but only one distinct id, so
        ``len(not_found_experiments) == len(experiment_ids)`` would never
        be True and the all-unknown case would silently fall through
        instead of raising."""
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(api, "_validate_organism_inputs", lambda *a, **k: "Prochlorococcus MED4")
        monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 3)
        fake_inputs = SimpleNamespace(
            gene_sets={}, background={}, cluster_metadata={},
            not_found=[], not_matched=[], no_expression=[],
            not_found_experiments=["nope"], clusters_skipped=[],
        )
        monkeypatch.setattr(enr, "de_enrichment_inputs", lambda *a, **k: fake_inputs)
        with pytest.raises(ValueError, match=r"experiment_ids not found: \['nope'\]"):
            api.pathway_enrichment(
                organism="MED4", experiment_ids=["nope", "nope"],
                ontology="kegg", level=1, conn=MagicMock(),
            )

    def test_pathway_enrichment_partial_unknown_experiments_keeps_running(self, monkeypatch):
        """Partial batch (some ids unknown) does NOT raise — the unknown ones
        surface in not_found_experiments instead."""
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(api, "_validate_organism_inputs", lambda *a, **k: "Prochlorococcus MED4")
        monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 3)
        fake_inputs = SimpleNamespace(
            organism_name="Prochlorococcus MED4",
            gene_sets={"exp1|t0|up": ["PMM0001"]},
            background={"exp1|t0|up": ["PMM0001", "PMM0002"]},
            cluster_metadata={"exp1|t0|up": {"experiment_id": "exp1"}},
            not_found=[], not_matched=[], no_expression=[],
            not_found_experiments=["nope"], clusters_skipped=[],
        )
        monkeypatch.setattr(enr, "de_enrichment_inputs", lambda *a, **k: fake_inputs)
        monkeypatch.setattr(
            api, "genes_by_ontology",
            lambda **_: {
                "ontology": "kegg", "organism_name": "MED4", "results": [],
                "not_found": [], "wrong_ontology": [], "wrong_level": [], "filtered_out": [],
            },
        )
        result = api.pathway_enrichment(
            organism="MED4", experiment_ids=["exp1", "nope"],
            ontology="kegg", level=1, conn=MagicMock(),
        )
        envelope = result.to_envelope()
        assert envelope["not_found_experiments"] == ["nope"]

    def test_pathway_enrichment_level_out_of_range_raises(self, monkeypatch):
        monkeypatch.setattr(api, "_validate_organism_inputs", lambda *a, **k: "Prochlorococcus MED4")
        monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 3)
        with pytest.raises(ValueError, match=r"level 9 is out of range for ontology 'kegg' \(levels 0–3"):
            api.pathway_enrichment(
                organism="MED4", experiment_ids=["x"],
                ontology="kegg", level=9, conn=MagicMock(),
            )

    def test_pathway_enrichment_flat_ontology_level_zero_message(self, monkeypatch):
        monkeypatch.setattr(api, "_validate_organism_inputs", lambda *a, **k: "Prochlorococcus MED4")
        monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 0)
        with pytest.raises(ValueError, match=r"levels 0 only — this ontology is flat"):
            api.pathway_enrichment(
                organism="MED4", experiment_ids=["x"],
                ontology="cog_category", level=1, conn=MagicMock(),
            )

    def test_pathway_enrichment_flat_ontology_level_zero_ok(self, monkeypatch):
        """level=0 on a flat ontology (max_level=0) does not raise."""
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(api, "_validate_organism_inputs", lambda *a, **k: "Prochlorococcus MED4")
        monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 0)
        fake_inputs = SimpleNamespace(
            organism_name="Prochlorococcus MED4",
            gene_sets={}, background={}, cluster_metadata={},
            not_found=[], not_matched=[], no_expression=[],
            not_found_experiments=[], clusters_skipped=[],
        )
        monkeypatch.setattr(enr, "de_enrichment_inputs", lambda *a, **k: fake_inputs)
        monkeypatch.setattr(
            api, "genes_by_ontology",
            lambda **_: {
                "ontology": "cog_category", "organism_name": "Prochlorococcus MED4", "results": [],
                "not_found": [], "wrong_ontology": [], "wrong_level": [], "filtered_out": [],
            },
        )
        result = api.pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cog_category", level=0, conn=MagicMock(),
        )
        assert result.level == 0

    def test_cluster_enrichment_analysis_id_not_found_raises(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(api, "_validate_organism_inputs", lambda *a, **k: "Prochlorococcus MED4")
        monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 3)
        fake_inputs = SimpleNamespace(
            gene_sets={}, background={}, cluster_metadata={},
            not_found=["nope"], not_matched=[], no_expression=[],
            not_found_experiments=[], clusters_skipped=[],
        )
        monkeypatch.setattr(enr, "cluster_enrichment_inputs", lambda *a, **k: fake_inputs)
        with pytest.raises(ValueError, match=r"analysis_id not found: 'nope'"):
            api.cluster_enrichment(
                analysis_id="nope", organism="MED4",
                ontology="kegg", level=1, conn=MagicMock(),
            )

    def test_cluster_enrichment_level_out_of_range_raises(self, monkeypatch):
        monkeypatch.setattr(api, "_validate_organism_inputs", lambda *a, **k: "Prochlorococcus MED4")
        monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 3)
        with pytest.raises(ValueError, match=r"level 9 is out of range for ontology 'kegg' \(levels 0–3"):
            api.cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="kegg", level=9, conn=MagicMock(),
            )

    def test_pathway_enrichment_brite_without_tree_raises(self, monkeypatch):
        """BRITE pools 12 unrelated hierarchies — a tree-less run must raise
        before any query, same as the level-range check (llm-review 2b.3)."""
        with pytest.raises(ValueError, match=r"ontology='brite' needs tree="):
            api.pathway_enrichment(
                organism="MED4", experiment_ids=["exp1"],
                ontology="brite", level=1, conn=MagicMock(),
            )

    def test_pathway_enrichment_brite_without_tree_raises_before_organism_query(self, monkeypatch):
        """The BRITE/tree check must fire before _validate_organism_inputs —
        an unpatched MagicMock conn would blow up first if the order were
        wrong, so this test deliberately does NOT patch the preflight."""
        conn = MagicMock()
        conn.execute_query.side_effect = AssertionError(
            "no query should run before the BRITE/tree check")
        with pytest.raises(ValueError, match=r"ontology='brite' needs tree="):
            api.pathway_enrichment(
                organism="MED4", experiment_ids=["exp1"],
                ontology="brite", level=1, conn=conn,
            )

    def test_pathway_enrichment_brite_with_tree_does_not_raise_on_tree_check(self, monkeypatch):
        """tree='transporters' clears the BRITE check (a later stage may
        still raise on missing DE inputs, which is unrelated)."""
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(api, "_validate_organism_inputs", lambda *a, **k: "Prochlorococcus MED4")
        monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 3)
        fake_inputs = SimpleNamespace(
            organism_name="Prochlorococcus MED4",
            gene_sets={}, background={}, cluster_metadata={},
            not_found=[], not_matched=[], no_expression=[],
            not_found_experiments=[], clusters_skipped=[],
        )
        monkeypatch.setattr(enr, "de_enrichment_inputs", lambda *a, **k: fake_inputs)
        monkeypatch.setattr(
            api, "genes_by_ontology",
            lambda **_: {
                "ontology": "brite", "organism_name": "Prochlorococcus MED4", "results": [],
                "not_found": [], "wrong_ontology": [], "wrong_level": [], "filtered_out": [],
            },
        )
        result = api.pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="brite", tree="transporters", level=1, conn=MagicMock(),
        )
        assert result.level == 1

    def test_cluster_enrichment_brite_without_tree_raises(self, monkeypatch):
        with pytest.raises(ValueError, match=r"ontology='brite' needs tree="):
            api.cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="brite", level=1, conn=MagicMock(),
            )

    def test_cluster_enrichment_brite_without_tree_raises_before_analysis_query(self, monkeypatch):
        """The BRITE/tree check must fire before cluster_enrichment_inputs
        runs (before any query) — deliberately no preflight patching."""
        conn = MagicMock()
        conn.execute_query.side_effect = AssertionError(
            "no query should run before the BRITE/tree check")
        with pytest.raises(ValueError, match=r"ontology='brite' needs tree="):
            api.cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="brite", level=1, conn=conn,
            )


# ---------------------------------------------------------------------------
# A3 — pathway_enrichment.informative_only (frozen spec 2026-05-04)
# ---------------------------------------------------------------------------


class TestPathwayEnrichmentInformativeOnly:
    """A3 spec § Decisions locked: default `informative_only=True`,
    per-row `is_informative` carried through to result.results.

    Each test uses mocked genes_by_ontology rows with a mix of informative
    and uninformative terms, then checks (a) which rows survive (informative
    side controls inclusion), (b) `result.params['informative_only']` records
    the requested value, (c) the `is_informative` column is present on
    result.results.
    """

    @pytest.fixture(autouse=True)
    def _enrichment_preflight(self, monkeypatch):
        _patch_enrichment_preflight(monkeypatch)

    @staticmethod
    def _stub_de_result():
        # Field names align with `de_enrichment_inputs` consumption:
        # log2fc / padj (or log2_fc / p_adjust), `significant` flag, `direction`
        # ('up'|'down'). Two significant-up rows over the same exp/timepoint
        # so cluster `exp1|T0|up` gets 2 foreground genes.
        return {
            "organism_name": "MED4",
            "results": [
                {"locus_tag": "PMM0001", "experiment_id": "exp1",
                 "timepoint": "T0", "direction": "up",
                 "log2fc": 2.0, "padj": 0.001, "significant": True,
                 "name": "exp1", "omics_type": "transcriptomics",
                 "table_scope": "rnaseq",
                 "treatment_type": ["light_dark"],
                 "background_factors": [], "is_time_course": False,
                 "growth_phase": None, "timepoint_hours": 0.0,
                 "timepoint_order": 0},
                {"locus_tag": "PMM0002", "experiment_id": "exp1",
                 "timepoint": "T0", "direction": "up",
                 "log2fc": 1.5, "padj": 0.001, "significant": True,
                 "name": "exp1", "omics_type": "transcriptomics",
                 "table_scope": "rnaseq",
                 "treatment_type": ["light_dark"],
                 "background_factors": [], "is_time_course": False,
                 "growth_phase": None, "timepoint_hours": 0.0,
                 "timepoint_order": 0},
            ],
            "not_found": [], "not_matched": [], "no_expression": [],
        }

    @staticmethod
    def _gbo_rows_mixed_informativeness():
        """Two terms — one informative (TERM_OK), one uninformative
        (TERM_ROOT). Each has 2 gene members in the foreground."""
        return [
            # Informative term (e.g. a real pathway) — kept under default True.
            {"term_id": "CR:OK", "term_name": "Real Pathway",
             "locus_tag": "PMM0001", "level": 1,
             "is_informative": True},
            {"term_id": "CR:OK", "term_name": "Real Pathway",
             "locus_tag": "PMM0002", "level": 1,
             "is_informative": True},
            # Uninformative term (e.g. KEGG map00001) — excluded under default.
            {"term_id": "CR:ROOT", "term_name": "Metabolic pathways",
             "locus_tag": "PMM0001", "level": 0,
             "is_informative": False},
            {"term_id": "CR:ROOT", "term_name": "Metabolic pathways",
             "locus_tag": "PMM0002", "level": 0,
             "is_informative": False},
        ]

    def _gbo_factory(self, captured, *, filter_uninformative_when_true):
        """Return a genes_by_ontology stub that mimics KG-side filtering.

        When `informative_only=True` is in the call kwargs, the stub emits
        only the informative subset of `_gbo_rows_mixed_informativeness()`,
        matching the real KG-side semantics (filter happens server-side).
        When False, all rows pass through.
        """
        rows = self._gbo_rows_mixed_informativeness()

        def _gbo(**kwargs):
            captured.update(kwargs)
            io = kwargs.get("informative_only", False)
            if filter_uninformative_when_true and io:
                kept = [r for r in rows if r["is_informative"]]
            else:
                kept = list(rows)
            return {
                "ontology": "cyanorak_role", "organism_name": "MED4",
                "results": kept,
                "not_found": [], "wrong_ontology": [],
                "wrong_level": [], "filtered_out": [],
            }

        return _gbo

    # --- (a) default informative_only=True excludes uninformative term rows ---
    def test_default_excludes_uninformative_term_rows(self, monkeypatch):
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f

        captured: dict = {}
        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            self._gbo_factory(captured, filter_uninformative_when_true=True),
        )

        result = pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
            min_gene_set_size=1, pvalue_cutoff=0.99,
        )
        # Default carried into the genes_by_ontology call.
        assert captured.get("informative_only") is True
        # No uninformative term row in the Fisher result.
        if not result.results.empty:
            term_ids = set(result.results["term_id"])
            assert "CR:ROOT" not in term_ids, (
                "Default informative_only=True must exclude uninformative term"
            )
            assert "CR:OK" in term_ids

    # --- (b) informative_only=False includes them -----------------------
    def test_explicit_false_includes_uninformative_term_rows(self, monkeypatch):
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f

        captured: dict = {}
        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            self._gbo_factory(captured, filter_uninformative_when_true=True),
        )

        result = pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
            informative_only=False,
            min_gene_set_size=1, pvalue_cutoff=0.99,
        )
        assert captured.get("informative_only") is False
        if not result.results.empty:
            term_ids = set(result.results["term_id"])
            assert "CR:ROOT" in term_ids, (
                "informative_only=False must include uninformative term rows"
            )
            assert "CR:OK" in term_ids

    # --- (c) result.params['informative_only'] recorded -----------------
    def test_params_records_informative_only_default(self, monkeypatch):
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f

        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            self._gbo_factory({}, filter_uninformative_when_true=True),
        )
        result = pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
            min_gene_set_size=1, pvalue_cutoff=0.99,
        )
        assert "informative_only" in result.params
        assert result.params["informative_only"] is True

    def test_params_records_informative_only_false(self, monkeypatch):
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f

        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            self._gbo_factory({}, filter_uninformative_when_true=True),
        )
        result = pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
            informative_only=False,
            min_gene_set_size=1, pvalue_cutoff=0.99,
        )
        assert result.params["informative_only"] is False

    # --- (d) is_informative column present in result.results DataFrame ---
    def test_is_informative_column_present_in_results(self, monkeypatch):
        """fisher_ora auto-passes through any term2gene column other than
        term_id/term_name/locus_tag (analysis/enrichment.py:367-374). The
        `is_informative` column must therefore appear on result.results."""
        from multiomics_explorer.api import pathway_enrichment
        import multiomics_explorer.api.functions as f

        monkeypatch.setattr(
            f, "differential_expression_by_gene",
            lambda **_: self._stub_de_result(),
        )
        # Use False so both informative and uninformative rows survive
        # to the result.results DataFrame.
        monkeypatch.setattr(
            f, "genes_by_ontology",
            self._gbo_factory({}, filter_uninformative_when_true=False),
        )
        result = pathway_enrichment(
            organism="MED4", experiment_ids=["exp1"],
            ontology="cyanorak_role", level=1,
            informative_only=False,
            min_gene_set_size=1, pvalue_cutoff=0.99,
        )
        assert not result.results.empty, (
            "Fixture should yield Fisher rows (gene_set ⊆ background, M >= 1)"
        )
        assert "is_informative" in result.results.columns


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
        # llm-review 2b.3 Task 5: genes_in_cluster's own not_found_analysis
        # is now the authoritative "doesn't exist at all" signal.
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        empty_result = {
            **self._CLUSTER_RESULT,
            "total_matching": 0, "results": [], "returned": 0,
            "analysis_name": None,
            "not_found_analysis": "ca:missing",
        }
        empty_meta = {**self._ANALYSIS_META, "total_matching": 0, "results": [], "returned": 0}
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: empty_result)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: empty_meta)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:missing", organism="MED4")
        assert "ca:missing" in inputs.not_found
        assert inputs.warnings == []

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
        assert inputs.warnings == []

    def test_warning_when_analysis_exists_but_empty(self, monkeypatch):
        """llm-review 2b.3 Task 5 carried-over item: analysis EXISTS,
        organism matches, but zero cluster->gene rows -> a warning, not
        not_found / not_matched (a normal empty result).

        Controller fix: drives through the REAL `genes_in_cluster` (mocked
        only at the conn level, matching build_genes_in_cluster_summary's
        actual analysis_id-mode return shape) rather than hand-building its
        result dict, so this test proves not_matched_organism=None is a
        genuine reachable outcome of genes_in_cluster's own organism-match
        logic (ca_organism_name == requested organism), not an assumption.
        """
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f

        class _StubConn:
            """Mimics the real 2-query dispatch genes_in_cluster runs in
            analysis_id mode (limit=None -> summary, then detail)."""

            def __init__(self):
                self.calls = 0

            def execute_query(self, cypher, **params):
                self.calls += 1
                if self.calls == 1:
                    # Real build_genes_in_cluster_summary shape
                    # (analysis_id mode): analysis exists, its own
                    # organism_name matches the requested organism
                    # word-for-word, but zero cluster->gene rows.
                    return [{
                        "total_matching": 0,
                        "by_organism": [],
                        "by_cluster": [],
                        "by_category_raw": [],
                        "not_found_clusters": [],
                        "not_matched_clusters": [],
                        "analysis_name": "Test Analysis",
                        "analysis_exists": True,
                        "ca_organism_name": "Prochlorococcus MED4",
                    }]
                return []  # detail query: no gene rows

        monkeypatch.setattr(
            f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4", conn=_StubConn())
        assert inputs.not_found == []
        assert inputs.not_matched == []
        assert any(
            "ca:test" in w and "no cluster" in w and "MED4" in w
            for w in inputs.warnings
        ), inputs.warnings

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

    @pytest.fixture(autouse=True)
    def _enrichment_preflight(self, monkeypatch):
        _patch_enrichment_preflight(monkeypatch)

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

    def test_not_found_analysis_id_raises(self, monkeypatch):
        """Task 4 (llm-review 2b.1): an unknown analysis_id raises loudly
        instead of returning a vacuous empty envelope."""
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(gene_sets={}, not_found=["ca:missing"]),
        )
        with pytest.raises(ValueError, match=r"analysis_id not found: 'ca:missing'"):
            cluster_enrichment(
                analysis_id="ca:missing", organism="MED4",
                ontology="cyanorak_role", level=1,
            )

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


# ---------------------------------------------------------------------------
# A3 — cluster_enrichment.informative_only (frozen spec 2026-05-04)
# ---------------------------------------------------------------------------


class TestClusterEnrichmentInformativeOnly:
    """Parallel of TestPathwayEnrichmentInformativeOnly for cluster_enrichment.

    Mode-B template-and-extend: same param, same threading pattern, same
    `is_informative` field placement.
    """

    @pytest.fixture(autouse=True)
    def _enrichment_preflight(self, monkeypatch):
        _patch_enrichment_preflight(monkeypatch)

    @staticmethod
    def _stub_inputs():
        from multiomics_explorer.analysis.enrichment import EnrichmentInputs
        # Cluster A has 2 foreground genes ⊆ background of 3.
        return EnrichmentInputs(
            organism_name="MED4",
            gene_sets={"Cluster A": ["PMM0001", "PMM0002"]},
            background={"Cluster A": ["PMM0001", "PMM0002", "PMM0003"]},
            cluster_metadata={"Cluster A": {
                "cluster_id": "gc:1", "cluster_name": "Cluster A",
                "member_count": 2,
            }},
            not_found=[], not_matched=[], no_expression=[],
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
    def _gbo_rows_mixed_informativeness():
        return [
            {"term_id": "CR:OK", "term_name": "Real Pathway",
             "locus_tag": "PMM0001", "level": 1,
             "is_informative": True},
            {"term_id": "CR:OK", "term_name": "Real Pathway",
             "locus_tag": "PMM0002", "level": 1,
             "is_informative": True},
            {"term_id": "CR:ROOT", "term_name": "Metabolic pathways",
             "locus_tag": "PMM0001", "level": 0,
             "is_informative": False},
            {"term_id": "CR:ROOT", "term_name": "Metabolic pathways",
             "locus_tag": "PMM0002", "level": 0,
             "is_informative": False},
        ]

    def _gbo_factory(self, captured, *, filter_uninformative_when_true):
        rows = self._gbo_rows_mixed_informativeness()

        def _gbo(**kwargs):
            captured.update(kwargs)
            io = kwargs.get("informative_only", False)
            if filter_uninformative_when_true and io:
                kept = [r for r in rows if r["is_informative"]]
            else:
                kept = list(rows)
            return {
                "ontology": "cyanorak_role", "organism_name": "MED4",
                "results": kept,
                "not_found": [], "wrong_ontology": [],
                "wrong_level": [], "filtered_out": [],
            }

        return _gbo

    # --- (a) default informative_only=True excludes uninformative rows ---
    def test_default_excludes_uninformative_term_rows(self, monkeypatch):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        captured: dict = {}
        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            self._gbo_factory(captured, filter_uninformative_when_true=True),
        )

        result = cluster_enrichment(
            analysis_id="ca:test", organism="MED4",
            ontology="cyanorak_role", level=1,
            min_gene_set_size=1, pvalue_cutoff=0.99,
        )
        assert captured.get("informative_only") is True
        if not result.results.empty:
            term_ids = set(result.results["term_id"])
            assert "CR:ROOT" not in term_ids
            assert "CR:OK" in term_ids

    # --- (b) informative_only=False includes them -----------------------
    def test_explicit_false_includes_uninformative_term_rows(self, monkeypatch):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        captured: dict = {}
        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            self._gbo_factory(captured, filter_uninformative_when_true=True),
        )

        result = cluster_enrichment(
            analysis_id="ca:test", organism="MED4",
            ontology="cyanorak_role", level=1,
            informative_only=False,
            min_gene_set_size=1, pvalue_cutoff=0.99,
        )
        assert captured.get("informative_only") is False
        if not result.results.empty:
            term_ids = set(result.results["term_id"])
            assert "CR:ROOT" in term_ids
            assert "CR:OK" in term_ids

    # --- (c) result.params['informative_only'] recorded -----------------
    def test_params_records_informative_only_default(self, monkeypatch):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            self._gbo_factory({}, filter_uninformative_when_true=True),
        )
        result = cluster_enrichment(
            analysis_id="ca:test", organism="MED4",
            ontology="cyanorak_role", level=1,
            min_gene_set_size=1, pvalue_cutoff=0.99,
        )
        assert "informative_only" in result.params
        assert result.params["informative_only"] is True

    def test_params_records_informative_only_false(self, monkeypatch):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            self._gbo_factory({}, filter_uninformative_when_true=True),
        )
        result = cluster_enrichment(
            analysis_id="ca:test", organism="MED4",
            ontology="cyanorak_role", level=1,
            informative_only=False,
            min_gene_set_size=1, pvalue_cutoff=0.99,
        )
        assert result.params["informative_only"] is False

    # --- (d) is_informative column present in result.results DataFrame ---
    def test_is_informative_column_present_in_results(self, monkeypatch):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            self._gbo_factory({}, filter_uninformative_when_true=False),
        )
        result = cluster_enrichment(
            analysis_id="ca:test", organism="MED4",
            ontology="cyanorak_role", level=1,
            informative_only=False,
            min_gene_set_size=1, pvalue_cutoff=0.99,
        )
        assert not result.results.empty, (
            "Fixture should yield Fisher rows (gene_set ⊆ background, M >= 1)"
        )
        assert "is_informative" in result.results.columns


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
        "rankable": "rankable",
        "has_p_value": "no_p_value",
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

    def test_summary_and_detail_envelope(self, monkeypatch):
        from multiomics_explorer.api.functions import list_derived_metrics
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
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

    def test_lucene_parse_error_survives_retry_raises_readable_valueerror(self):
        """When the escaped retry also fails with a Lucene parse error, the
        raw ClientError must not leak (llm-review 2b.3)."""
        from multiomics_explorer.api.functions import list_derived_metrics
        from neo4j.exceptions import ClientError
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.execute_query.side_effect = [
            ClientError("Invalid input ParseException"),
            ClientError("Invalid input ParseException"),
        ]
        with pytest.raises(ValueError, match=r"is not valid Lucene syntax"):
            list_derived_metrics(search_text="diel AND", conn=conn)

    def test_importable_from_package(self):
        from multiomics_explorer import list_derived_metrics as api_ldm
        from multiomics_explorer.api import list_derived_metrics as api_direct
        assert api_ldm is api_direct

    def test_returns_score_max_none_when_no_search(self):
        from multiomics_explorer.api.functions import list_derived_metrics
        conn = self._mock_conn(self._SUMMARY_ROW, [])
        out = list_derived_metrics(conn=conn)
        assert out["score_max"] is None

    def test_compact_drops_verbose_only_fields(self, monkeypatch):
        """verbose=False (default) strips the 9 fields moved behind
        verbose; the compact identity/routing set (derived_metric_id,
        name, metric_type, value_kind, rankable, organism_name, unit,
        total_gene_count, allowed_categories) survives — `unit` stays
        compact because a numeric `value` is unreadable without it."""
        from multiomics_explorer.api.functions import list_derived_metrics
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_derived_metrics(organism="MED4", conn=conn)
        row = out["results"][0]
        for dropped in (
            "has_p_value", "field_description", "experiment_id",
            "publication_doi", "compartment", "omics_type",
            "treatment_type", "background_factors", "growth_phases",
        ):
            assert dropped not in row, f"{dropped} should be dropped compact"
        for kept in (
            "derived_metric_id", "name", "metric_type", "value_kind",
            "rankable", "organism_name", "unit", "total_gene_count",
            "allowed_categories",
        ):
            assert kept in row, f"{kept} should remain in compact row"

    def test_verbose_keeps_all_fields(self, monkeypatch):
        from multiomics_explorer.api.functions import list_derived_metrics
        monkeypatch.setattr(api, "_organism_zero_match_warning", lambda *a, **k: [])
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_derived_metrics(organism="MED4", verbose=True, conn=conn)
        row = out["results"][0]
        for kept in (
            "has_p_value", "field_description", "experiment_id",
            "publication_doi", "compartment", "omics_type",
            "treatment_type", "background_factors", "growth_phases",
        ):
            assert kept in row, f"{kept} should survive verbose=True"


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
        "top_metabolite_pathways": [
            {
                "metabolite_pathway_id": "kegg.pathway:ko01100",
                "metabolite_pathway_name": "Metabolic pathways",
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
        "catalyst_gene_count": 320,
        "organism_count": 31,
        "transporter_count": 17,
        "transporter_gene_count": 3051,
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
        # Phase 2 Item 2 rename: top_pathways → top_metabolite_pathways
        assert "top_metabolite_pathways" in out
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
        out = list_metabolites(search_text="glucose*", conn=conn)
        assert out["total_matching"] == 1
        assert conn.execute_query.call_count == 3

    def test_lucene_parse_error_survives_summary_retry_raises_readable_valueerror(self):
        """When the escaped summary retry also fails with a Lucene parse
        error, the raw ClientError must not leak (llm-review 2b.3)."""
        from multiomics_explorer.api.functions import list_metabolites
        from neo4j.exceptions import ClientError as Neo4jClientError
        conn = MagicMock()
        conn.execute_query.side_effect = [
            Neo4jClientError("Invalid input ParseException"),
            Neo4jClientError("Invalid input ParseException"),
        ]
        with pytest.raises(ValueError, match=r"is not valid Lucene syntax"):
            list_metabolites(search_text="glucose AND", conn=conn)

    def test_lucene_parse_error_on_detail_raises_readable_valueerror(self):
        """The detail query has no escape-retry of its own (unlike summary)
        — a Lucene parse error there must still become a readable
        ValueError, not a raw ClientError (llm-review 2b.3)."""
        from multiomics_explorer.api.functions import list_metabolites
        from neo4j.exceptions import ClientError as Neo4jClientError
        conn = MagicMock()
        conn.execute_query.side_effect = [
            [self._SUMMARY_ROW],
            Neo4jClientError("Invalid input ParseException"),
        ]
        with pytest.raises(ValueError, match=r"is not valid Lucene syntax"):
            list_metabolites(search_text="glucose", conn=conn)

    def test_evidence_sources_enum_validation(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = MagicMock()
        with pytest.raises(ValueError):
            list_metabolites(evidence_sources=["bogus"], conn=conn)

    def test_search_empty_validation(self):
        from multiomics_explorer.api.functions import list_metabolites
        with pytest.raises(ValueError):
            list_metabolites(search_text="")
        with pytest.raises(ValueError):
            list_metabolites(search_text="   ")

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

    def test_elements_full_name_normalized_silently(self):
        """llm-review 2b.3 Task 5 resolution 2: a full element name
        ('Nitrogen') normalises to its symbol with NO warning."""
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(elements=["Nitrogen"], conn=conn)
        assert out["not_found"]["elements"] == []
        assert not any("element" in w.lower() for w in out["warnings"])
        # The normalized symbol reached the builder.
        called_kwargs = conn.execute_query.call_args_list[0].kwargs
        assert called_kwargs.get("elements") == ["N"]

    def test_elements_lowercase_symbol_normalized_silently(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(elements=["n", "fe"], conn=conn)
        assert out["not_found"]["elements"] == []
        called_kwargs = conn.execute_query.call_args_list[0].kwargs
        assert called_kwargs.get("elements") == ["N", "Fe"]

    def test_elements_unrecognized_warns_and_not_found(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(elements=["Xx"], conn=conn)
        assert out["not_found"]["elements"] == ["Xx"]
        assert any(
            "'Xx' is not a recognized element" in w for w in out["warnings"]
        ), out["warnings"]
        # Dropped from the filter entirely (no impossible-AND on a bogus symbol).
        called_kwargs = conn.execute_query.call_args_list[0].kwargs
        assert called_kwargs.get("elements") is None

    def test_elements_mixed_valid_and_invalid(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(elements=["N", "Xx"], conn=conn)
        assert out["not_found"]["elements"] == ["Xx"]
        called_kwargs = conn.execute_query.call_args_list[0].kwargs
        assert called_kwargs.get("elements") == ["N"]

    def test_name_shaped_metabolite_id_warns(self):
        """llm-review 2b.3 Task 5: a metabolite_ids entry matching no id
        pattern at all (a NAME) warns and points at search_text."""
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(
            self._SUMMARY_ROW, [self._DETAIL_ROW],
            [{"found": []}],
        )
        out = list_metabolites(metabolite_ids=["glutamate"], conn=conn)
        assert any(
            "'glutamate' is not a metabolite id" in w
            and "list_metabolites(search_text=...)" in w
            for w in out["warnings"]
        ), out["warnings"]

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

    Organism resolution (`_validate_organism_inputs`) is monkeypatched to
    an identity function by an autouse fixture below, so it consumes no
    `conn.execute_query` call and the mocked sequences above stay
    unshifted. Tests that specifically exercise organism resolution
    (ambiguous / zero-match) override the patch locally.
    """

    _METS = ["kegg.compound:C00086"]  # urea
    _ORG = "Prochlorococcus MED4"

    @pytest.fixture(autouse=True)
    def _mock_validate_organism_inputs(self, monkeypatch):
        monkeypatch.setattr(
            api, "_validate_organism_inputs",
            lambda organism, locus_tags, experiment_ids, conn: organism,
        )

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
        # 10 most_specific + 9 inherited (transport-only — 23 total
        # transport-confidence rows)
        "rows_by_substrate_depth": [
            {"substrate_depth": "most_specific", "count": 10},
            {"substrate_depth": "inherited", "count": 9},
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
                "transport_most_specific_rows": 10,
                "transport_inherited_rows": 9,
            },
        ],
        "top_reactions": [],
        "top_tcdb_families": [],
        "top_gene_categories": [],
        "top_genes": [],
    }

    # Family-inferred dominates — for the auto-warning trigger test
    _SUMMARY_ROW_INHERITED_DOMINATES = {
        **_SUMMARY_ROW_BOTH_ARMS,
        "total_matching": 14,
        "gene_count_total": 14,
        "reaction_count_total": 0,
        "transporter_count_total": 14,
        "metabolite_count_total": 1,
        "rows_by_evidence_source": [
            {"evidence_source": "transport", "count": 14},
        ],
        "rows_by_substrate_depth": [
            {"substrate_depth": "most_specific", "count": 5},
            {"substrate_depth": "inherited", "count": 9},
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
                "transport_most_specific_rows": 5,
                "transport_inherited_rows": 9,
            },
        ],
    }

    # Sample metabolism-arm detail row (most_specific-by-definition)
    _METAB_ROW = {
        "locus_tag": "PMM0944",
        "gene_name": "ureC",
        "product": "urease",
        "evidence_source": "metabolism",
        "substrate_depth": None,
        "tcdb_evidence_score": None,
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

    # Sample transport-arm detail row (most_specific)
    _TRANS_ROW_MS = {
        "locus_tag": "PMM0974",
        "gene_name": "urtE",
        "product": "ABC-type urea transporter, ATPase component",
        "evidence_source": "transport",
        "substrate_depth": "most_specific",
        "tcdb_evidence_score": 0.8,
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

    # Sample transport-arm detail row (inherited)
    _TRANS_ROW_INH = {
        "locus_tag": "PMM0234",
        "gene_name": None,
        "product": "ABC superfamily ATP-binding cassette transporter",
        "evidence_source": "transport",
        "substrate_depth": "inherited",
        "tcdb_evidence_score": 0.4,
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
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        assert isinstance(out, dict)
        assert out["total_matching"] == 23
        assert "by_metabolite" in out
        assert "by_evidence_source" in out
        assert "by_substrate_depth" in out
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
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        # 1 summary + 2 detail (one per arm) + 1 existence probe = 4
        assert conn.execute_query.call_count >= 3
        # Both rows surface in the result
        evidence = {r["evidence_source"] for r in out["results"]}
        assert evidence == {"metabolism", "transport"}

    def test_name_shaped_metabolite_id_warns(self):
        """llm-review 2b.3 Task 5: an input matching no metabolite-id
        pattern at all (a NAME, not an ID) gets its own warning pointing
        at list_metabolites(search_text=...). Zero extra queries — the
        name never enters `_canonicalize_metabolite_ids`'s to_resolve set,
        so it's forwarded verbatim, same query count as a canonical id."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": []}],  # the raw name resolves to nothing in the KG
        )
        out = gbm(["glutamate"], self._ORG, conn=conn)
        assert any(
            "'glutamate' is not a metabolite id" in w
            and "list_metabolites(search_text=...)" in w
            for w in out["warnings"]
        ), out["warnings"]

    def test_canonical_metabolite_id_no_shape_warning(self):
        """A correctly-shaped canonical id (already `prefix:id`) never
        triggers the shape warning."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        assert not any("is not a metabolite id" in w for w in out["warnings"])

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
            [self._TRANS_ROW_MS],
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
            [self._TRANS_ROW_MS],  # transport arm UNCHANGED
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
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(
            self._METS, self._ORG,
            mass_balance="balanced", conn=conn,
        )
        evidence = {r["evidence_source"] for r in out["results"]}
        assert "transport" in evidence

    def test_substrate_depth_most_specific_no_warning(self):
        """substrate_depth='most_specific' narrows transport arm
        only AND suppresses the family-inferred-dominance warning (since user
        chose explicitly)."""
        gbm = self._api()
        # SC-only summary so transport rows are exclusively SC
        sc_summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "rows_by_substrate_depth": [
                {"substrate_depth": "most_specific", "count": 10},
            ],
            "by_metabolite": [
                {
                    **self._SUMMARY_ROW_BOTH_ARMS["by_metabolite"][0],
                    "transport_most_specific_rows": 10,
                    "transport_inherited_rows": 0,
                },
            ],
        }
        conn = self._mock_conn(
            [sc_summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(
            self._METS, self._ORG,
            substrate_depth=["most_specific"], conn=conn,
        )
        # Metabolism rows still present (substrate_depth does NOT touch
        # metabolism arm)
        evidence = {r["evidence_source"] for r in out["results"]}
        assert evidence == {"metabolism", "transport"}
        # No auto-warning (user explicitly set substrate_depth)
        assert out["warnings"] == []

    def test_substrate_depth_inherited_no_warning(self):
        """substrate_depth='inherited' likewise suppresses the
        auto-warning (user chose explicitly)."""
        gbm = self._api()
        fi_summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "rows_by_substrate_depth": [
                {"substrate_depth": "inherited", "count": 9},
            ],
            "by_metabolite": [
                {
                    **self._SUMMARY_ROW_BOTH_ARMS["by_metabolite"][0],
                    "transport_most_specific_rows": 0,
                    "transport_inherited_rows": 9,
                },
            ],
        }
        conn = self._mock_conn(
            [fi_summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_INH],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(
            self._METS, self._ORG,
            substrate_depth=["inherited"], conn=conn,
        )
        assert out["warnings"] == []

    def test_inherited_dominance_warning_fires(self):
        """Warning fires when:
        - transport rows present in result AND
        - transport_inherited_rows > transport_most_specific_rows AND
        - user did NOT set substrate_depth.

        substrate_depth migration: keyed on `inherited` dominance over
        deepest-attachment rows only; the message names
        `substrate_depth=['most_specific']` as the narrowing filter and
        no longer uses the retired substrate_confirmed / family_inferred
        vocabulary.
        """
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_INHERITED_DOMINATES],
            # transport-only — MED4 has no nitrite-anchored metabolism
            [],
            [self._TRANS_ROW_INH],
            [{"found": ["kegg.compound:C00088"]}],
        )
        out = gbm(["kegg.compound:C00088"], self._ORG, conn=conn)
        warnings = [w for w in out["warnings"] if "inherited" in w]
        assert warnings, (
            f"expected inherited-dominance warning, got {out['warnings']!r}"
        )
        warning = warnings[0]
        assert "substrate_depth=['most_specific']" in warning
        # Inline counts `(X of Y)` — X = inherited rows, Y = transport rows
        import re
        m = re.search(r"\((\d+) of (\d+)\)", warning)
        assert m, (
            f"warning must include `(X of Y)` count format; got: {warning}"
        )
        inh_count, total = int(m.group(1)), int(m.group(2))
        assert (inh_count, total) == (9, 14)
        # Retired vocabulary must not leak into the message
        assert "family_inferred" not in warning
        assert "substrate_confirmed" not in warning
        assert "transport_confidence" not in warning

    def test_no_warning_when_most_specific_majority(self):
        """sc >= fi → no auto-warning even with default both-arm mode."""
        gbm = self._api()
        # urea slice: 10 SC > 9 FI on transport
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        # 10 SC > 9 FI — no warning
        assert all(
            "inherited" not in w for w in out["warnings"]
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
            "rows_by_substrate_depth": [],
            "by_metabolite": [
                {
                    **self._SUMMARY_ROW_BOTH_ARMS["by_metabolite"][0],
                    "transport_most_specific_rows": 0,
                    "transport_inherited_rows": 0,
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
            [self._TRANS_ROW_MS],
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
            [self._TRANS_ROW_MS],
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

    def test_not_found_organism_when_zero_genes(self, monkeypatch):
        """A word matching zero organisms short-circuits to an empty
        envelope with `not_found.organism` set — no arm queries run, but
        the metabolite-side existence probe still does."""
        gbm = self._api()

        def boom(organism, locus_tags, experiment_ids, conn):
            raise ValueError(
                f"no organism matching '{organism}' found. "
                "Use list_organisms to see valid organism names."
            )
        monkeypatch.setattr(api, "_validate_organism_inputs", boom)
        conn = self._mock_conn(
            [{"found": ["kegg.compound:C00086"]}],  # metabolite_id probe
        )
        out = gbm(self._METS, "Bogus organism", conn=conn)
        assert out["not_found"]["organism"] == "Bogus organism"
        assert out["total_matching"] == 0
        assert out["gene_count_total"] == 0
        assert out["results"] == []

    def test_genes_by_metabolite_ambiguous_organism_raises(self, monkeypatch):
        """An organism word matching multiple organisms propagates the
        ValueError rather than silently returning cross-organism rows."""
        gbm = self._api()

        def boom(organism, locus_tags, experiment_ids, conn):
            raise ValueError(
                f"organism '{organism}' matches multiple organisms: "
                "Prochlorococcus MED4, Prochlorococcus MIT9313 — be more "
                "specific"
            )
        monkeypatch.setattr(api, "_validate_organism_inputs", boom)
        with pytest.raises(ValueError, match="multiple organisms"):
            gbm(self._METS, "Prochlorococcus", conn=MagicMock())

    def test_not_found_organism_none_on_success(self):
        """gene_count_total > 0 → not_found.organism is None."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
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
            [self._TRANS_ROW_MS],
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
            [self._TRANS_ROW_MS, self._TRANS_ROW_INH],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, limit=2, offset=0, conn=conn)
        assert len(out["results"]) == 2
        # Sort key: metabolite_id, evidence_source ('metabolism' < 'transport'),
        # substrate_depth_priority — first row metab, second transport.
        assert out["results"][0]["evidence_source"] == "metabolism"
        assert out["results"][1]["evidence_source"] == "transport"

    def test_truncated_flag(self):
        """When total_matching > offset + len(results), truncated=True."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],  # total_matching=23
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, limit=2, conn=conn)
        assert out["truncated"] is True

    def test_offset_echoed_in_envelope(self):
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
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
                [self._TRANS_ROW_MS],
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
                "substrate_depth": (
                    "most_specific" if i % 2 == 0 else "inherited"
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
                "transport_most_specific_rows": tc,
                "transport_inherited_rows": 0,
                # gene-level TCDB facts (null on metabolism-only genes)
                "transport_substrate_resolution": "resolved" if tc else None,
                "tcdb_evidence_score_max": 0.8 if tc else None,
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
            [self._TRANS_ROW_MS],
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
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        assert len(out["top_tcdb_families"]) == 10
        gcs = [r["gene_count"] for r in out["top_tcdb_families"]]
        assert gcs == sorted(gcs, reverse=True)
        # New contract fields present
        first = out["top_tcdb_families"][0]
        assert "level_kind" in first
        assert "substrate_depth" in first
        assert "metabolite_count" in first

    def test_top_gene_categories_sorted_and_truncated_to_10(self):
        gbm = self._api()
        conn = self._mock_conn(
            [self._summary_with_top_arrays()],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        assert len(out["top_gene_categories"]) == 10
        gcs = [r["gene_count"] for r in out["top_gene_categories"]]
        assert gcs == sorted(gcs, reverse=True)
        # Field name is `category` (not the old `gene_category`)
        assert "category" in out["top_gene_categories"][0]
        assert "gene_category" not in out["top_gene_categories"][0]

    # ---- substrate_depth migration (spec 2026-08-20) ----

    def test_substrate_depth_unknown_value_raises_listing_valid(self):
        """Unknown values raise ValueError listing the valid ones, before
        any Cypher executes."""
        gbm = self._api()
        conn = MagicMock()
        with pytest.raises(ValueError) as exc:
            gbm(self._METS, self._ORG, substrate_depth=["bogus"], conn=conn)
        msg = str(exc.value)
        assert "bogus" in msg
        assert "most_specific" in msg and "inherited" in msg
        conn.execute_query.assert_not_called()

    @pytest.mark.parametrize("old_value,new_value", [
        ("substrate_confirmed", "most_specific"),
        ("family_inferred", "inherited"),
    ])
    def test_substrate_depth_old_value_strings_raise_with_rename_pointer(
        self, old_value, new_value,
    ):
        """The two retired `transport_confidence` value strings raise with a
        rename pointer naming the replacement value."""
        gbm = self._api()
        conn = MagicMock()
        with pytest.raises(ValueError) as exc:
            gbm(self._METS, self._ORG, substrate_depth=[old_value], conn=conn)
        msg = str(exc.value)
        assert old_value in msg
        assert new_value in msg
        assert "substrate_depth" in msg
        conn.execute_query.assert_not_called()

    def test_substrate_depth_forwarded_to_transport_builders(self):
        """The list flows into the transport-arm detail + summary builders
        as `$substrate_depth`; the metabolism arm never sees it."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        gbm(self._METS, self._ORG, substrate_depth=["most_specific"], conn=conn)
        calls = conn.execute_query.call_args_list
        summary_kwargs = calls[0].kwargs
        assert summary_kwargs.get("substrate_depth") == ["most_specific"]
        metab_cypher, metab_kwargs = calls[1].args[0], calls[1].kwargs
        assert "$substrate_depth" not in metab_cypher
        assert "substrate_depth" not in metab_kwargs
        trans_kwargs = calls[2].kwargs
        assert trans_kwargs.get("substrate_depth") == ["most_specific"]

    def test_no_transport_confidence_kwarg(self):
        """The old parameter name is gone (TypeError, not silently ignored)."""
        gbm = self._api()
        with pytest.raises(TypeError):
            gbm(self._METS, self._ORG, transport_confidence="substrate_confirmed",
                conn=MagicMock())

    def test_sort_score_desc_within_depth_tier(self):
        """Within a transport depth tier rows rank by tcdb_evidence_score
        desc; most_specific always precedes inherited regardless of score;
        metabolism rows precede all transport rows."""
        gbm = self._api()
        low_ms = {**self._TRANS_ROW_MS, "locus_tag": "PMM0970",
                  "tcdb_evidence_score": 0.6}
        high_ms = {**self._TRANS_ROW_MS, "locus_tag": "PMM0971",
                   "tcdb_evidence_score": 0.8}
        high_inh = {**self._TRANS_ROW_INH, "locus_tag": "PMM0001",
                    "tcdb_evidence_score": 1.0}
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [high_inh, low_ms, high_ms],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, limit=10, conn=conn)
        order = [(r["evidence_source"], r.get("substrate_depth"), r["locus_tag"])
                 for r in out["results"]]
        assert order == [
            ("metabolism", None, "PMM0944"),
            ("transport", "most_specific", "PMM0971"),   # 0.8
            ("transport", "most_specific", "PMM0970"),   # 0.6
            ("transport", "inherited", "PMM0001"),        # 1.0 but inherited
        ]

    def test_sort_key_tiebreakers_after_score(self):
        """Equal score inside a tier → existing tiebreakers (tcdb_family_id,
        locus_tag) — the api sort key is
        (metabolite_id, evidence_source, substrate_depth_priority, -score,
        secondary_id, locus_tag)."""
        from multiomics_explorer.api.functions import _gbm_sort_key
        a = {**self._TRANS_ROW_MS, "locus_tag": "PMM0972"}
        b = {**self._TRANS_ROW_MS, "locus_tag": "PMM0971"}
        assert _gbm_sort_key(b) < _gbm_sort_key(a)
        inh = {**self._TRANS_ROW_INH, "tcdb_evidence_score": 1.0}
        assert _gbm_sort_key(a) < _gbm_sort_key(inh)
        assert _gbm_sort_key(self._METAB_ROW) < _gbm_sort_key(b)

    def test_top_genes_carry_resolution_and_score_max(self):
        """top_genes[] entries gain transport_substrate_resolution +
        tcdb_evidence_score_max (null on metabolism-only genes)."""
        gbm = self._api()
        summary = self._summary_with_top_arrays()
        # PMM0103 (rc=1, tc=0) is the fixture's only metabolism-only gene but
        # ranks 12/12 and falls outside the [:10] slice — lift its reaction
        # breadth locally so the null-contract probe sits inside top_genes.
        summary["top_genes"] = [
            {**g, "reaction_count": 9, "metabolism_rows": 9}
            if g["locus_tag"] == "PMM0103" else g
            for g in summary["top_genes"]
        ]
        conn = self._mock_conn(
            [summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        by_lt = {g["locus_tag"]: g for g in out["top_genes"]}
        assert by_lt["PMM0104"]["transport_substrate_resolution"] == "resolved"
        assert by_lt["PMM0104"]["tcdb_evidence_score_max"] == 0.8
        metab_only = by_lt["PMM0103"]   # rc=9, tc=0 → breadth 9, in slice
        assert "transport_substrate_resolution" in metab_only
        assert metab_only["transport_substrate_resolution"] is None
        assert "tcdb_evidence_score_max" in metab_only
        assert metab_only["tcdb_evidence_score_max"] is None

    def test_envelope_uses_substrate_depth_names_only(self):
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        assert "by_transport_confidence" not in out
        assert {e["substrate_depth"] for e in out["by_substrate_depth"]} == {
            "most_specific", "inherited",
        }
        bm = out["by_metabolite"][0]
        assert bm["transport_most_specific_rows"] == 10
        assert bm["transport_inherited_rows"] == 9
        assert "transport_substrate_confirmed_rows" not in bm
        assert "transport_family_inferred_rows" not in bm
        for row in out["results"]:
            assert "transport_confidence" not in row
            assert "substrate_depth" in row
            assert "tcdb_evidence_score" in row
        metab = next(r for r in out["results"] if r["evidence_source"] == "metabolism")
        assert metab["substrate_depth"] is None
        assert metab["tcdb_evidence_score"] is None
        trans = next(r for r in out["results"] if r["evidence_source"] == "transport")
        assert trans["substrate_depth"] == "most_specific"
        assert trans["tcdb_evidence_score"] == 0.8

    def test_top_genes_ranked_by_combined_breadth_not_gene_count(self):
        """Per spec § GbmTopGene: ranked by (reaction_count + transporter_count)
        desc, with locus_tag tiebreaker. gene_count is not even a field."""
        gbm = self._api()
        conn = self._mock_conn(
            [self._summary_with_top_arrays()],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
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
                    "transport_most_specific_rows": 3,
                    "transport_inherited_rows": 0,
                },
                {
                    "locus_tag": "PMM0001",
                    "gene_name": None,
                    "reaction_count": 5,
                    "transporter_count": 0,
                    "metabolite_count": 1,
                    "metabolism_rows": 5,
                    "transport_most_specific_rows": 0,
                    "transport_inherited_rows": 0,
                },
            ],
        }
        conn = self._mock_conn(
            [tied_summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
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
                    "transport_most_specific_rows": 0,
                    "transport_inherited_rows": 0,
                },
                {
                    "metabolite_id": "kegg.compound:C00086",
                    "name": "Urea",
                    "formula": "CH4N2O",
                    "rows": 23, "gene_count": 18, "reaction_count": 4,
                    "transporter_count": 14, "metabolism_rows": 4,
                    "transport_most_specific_rows": 10,
                    "transport_inherited_rows": 9,
                },
            ],
        }
        conn = self._mock_conn(
            [multi_metab_summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
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

    def test_by_evidence_source_and_by_substrate_depth_sorted(self):
        """Both rollups sorted by count desc, then key asc."""
        gbm = self._api()
        # Provide rollups in non-canonical order to exercise the sort.
        scrambled = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "rows_by_evidence_source": [
                {"evidence_source": "transport", "count": 4},
                {"evidence_source": "metabolism", "count": 19},
            ],
            "rows_by_substrate_depth": [
                {"substrate_depth": "most_specific", "count": 3},
                {"substrate_depth": "inherited", "count": 9},
            ],
        }
        conn = self._mock_conn(
            [scrambled],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)
        # by_evidence_source: highest count first
        assert out["by_evidence_source"][0]["evidence_source"] == "metabolism"
        assert out["by_evidence_source"][0]["count"] == 19
        # by_substrate_depth: highest count first
        assert (
            out["by_substrate_depth"][0]["substrate_depth"]
            == "inherited"
        )

    def test_truncated_uses_offset_plus_limit_formula(self):
        """Per spec § Result-size controls (line 966): truncated iff
        (offset + limit) < total_matching. Independent of len(results)."""
        gbm = self._api()
        # offset=10, limit=10 → 20; total_matching=23 → truncated=True
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],  # total_matching=23
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, limit=10, offset=10, conn=conn)
        assert out["truncated"] is True

        # offset=20, limit=10 → 30 ≥ 23 → truncated=False
        conn2 = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out2 = gbm(self._METS, self._ORG, limit=10, offset=20, conn=conn2)
        assert out2["truncated"] is False

    # ---- Phase 3 Item 6.1 — None-padding for cross-arm fields ----

    def test_cross_arm_fields_none_padded(self):
        """After Item 6.1 None-padding: every result row carries all 7
        cross-arm keys; arm-specific fields are explicitly None on rows
        from the other arm.

        Cross-arm fields:
        - transport-only (None on metabolism rows): substrate_depth,
          tcdb_family_id, tcdb_family_name
        - metabolism-only (None on transport rows): reaction_id,
          reaction_name, ec_numbers, mass_balance
        """
        gbm = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm(self._METS, self._ORG, conn=conn)

        metabolism_rows = [
            r for r in out["results"] if r["evidence_source"] == "metabolism"
        ]
        transport_rows = [
            r for r in out["results"] if r["evidence_source"] == "transport"
        ]
        assert metabolism_rows, (
            "fixture must include at least one metabolism row"
        )
        assert transport_rows, (
            "fixture must include at least one transport row"
        )

        # Metabolism rows: transport-arm cross-arm keys present, value None
        for row in metabolism_rows:
            assert "substrate_depth" in row
            assert row["substrate_depth"] is None
            assert "tcdb_family_id" in row
            assert row["tcdb_family_id"] is None
            assert "tcdb_family_name" in row
            assert row["tcdb_family_name"] is None

        # Transport rows: metabolism-arm cross-arm keys present, value None
        for row in transport_rows:
            assert "reaction_id" in row
            assert row["reaction_id"] is None
            assert "reaction_name" in row
            assert row["reaction_name"] is None
            assert "ec_numbers" in row
            assert row["ec_numbers"] is None
            assert "mass_balance" in row
            assert row["mass_balance"] is None


# ---------------------------------------------------------------------------
# metabolites_by_gene (MBG) — Tool 3 of chemistry slice 1
#
# Mirrors TestGenesByMetabolite (above). Anchor flips from metabolite_ids
# → locus_tags + organism (single-organism enforced). Adds:
#   - metabolite_elements filter (uniform across both arms)
#   - by_element / top_pathways envelope rollups
#   - not_matched semantics flip: locus_tags that resolve in organism but
#     have zero chemistry edges (mirror of GBM's metabolite-side not_matched)
#   - not_found.metabolite_elements bucket (typo / unknown element symbols)
# Spec: docs/tool-specs/metabolites_by_gene.md
# ---------------------------------------------------------------------------


class TestMetabolitesByGene:
    """Tests for api.metabolites_by_gene.

    Mirrors TestGenesByMetabolite mocked-conn pattern. Each test wires a
    `_mock_conn` whose `execute_query` yields a defined sequence matching
    the expected per-call order in the api layer. Detail order:
      1. summary builder (always)
      2. metabolism-arm detail (when summary=False AND metabolism arm fires)
      3. transport-arm detail   (when summary=False AND transport arm fires)
      4. existence probes (one per filter that has unknown-input diagnostics)

    Organism resolution (`_validate_organism_inputs`) is monkeypatched to
    an identity function by an autouse fixture below, so it consumes no
    `conn.execute_query` call and the mocked sequences above stay
    unshifted. Tests that specifically exercise organism resolution
    (ambiguous / zero-match) override the patch locally.
    """

    _LOCUS = ["PMM0963", "PMM0964", "PMM0965"]   # urease α/β/γ subunits
    _ORG = "Prochlorococcus MED4"

    @pytest.fixture(autouse=True)
    def _mock_validate_organism_inputs(self, monkeypatch):
        monkeypatch.setattr(
            api, "_validate_organism_inputs",
            lambda organism, locus_tags, experiment_ids, conn: organism,
        )

    # ---- Canned summary row (envelope payload from build_*_summary) ----
    _SUMMARY_ROW_BOTH_ARMS = {
        "total_matching": 15,
        "gene_count_total": 3,
        "reaction_count_total": 1,
        "transporter_count_total": 3,
        "metabolite_count_total": 4,
        "rows_by_evidence_source": [
            {"evidence_source": "metabolism", "count": 12},
            {"evidence_source": "transport", "count": 3},
        ],
        "rows_by_substrate_depth": [
            {"substrate_depth": "most_specific", "count": 2},
            {"substrate_depth": "inherited", "count": 1},
        ],
        "by_gene": [
            {
                "locus_tag": "PMM0963",
                "gene_name": "ureA",
                "product": "urease gamma subunit",
                "rows": 5,
                "metabolite_count": 4,
                "reaction_count": 1,
                "transporter_count": 1,
                "metabolism_rows": 4,
                "transport_most_specific_rows": 1,
                "transport_inherited_rows": 0,
                "transport_substrate_resolution": "resolved",
                "tcdb_evidence_score_max": 0.8,
            },
            {
                "locus_tag": "PMM0964",
                "gene_name": "ureB",
                "product": "urease beta subunit",
                "rows": 5,
                "metabolite_count": 4,
                "reaction_count": 1,
                "transporter_count": 1,
                "metabolism_rows": 4,
                "transport_most_specific_rows": 1,
                "transport_inherited_rows": 0,
                "transport_substrate_resolution": "resolved",
                "tcdb_evidence_score_max": 0.8,
            },
            {
                "locus_tag": "PMM0965",
                "gene_name": "ureC",
                "product": "urease alpha subunit",
                "rows": 5,
                "metabolite_count": 4,
                "reaction_count": 1,
                "transporter_count": 1,
                "metabolism_rows": 4,
                "transport_most_specific_rows": 0,
                "transport_inherited_rows": 1,
                # decision 5: resolved = at least one non-lumping deepest
                # attachment (this gene still carries an inherited row)
                "transport_substrate_resolution": "resolved",
                "tcdb_evidence_score_max": 0.6,
            },
        ],
        "top_metabolites": [],
        "top_reactions": [],
        "top_tcdb_families": [],
        "top_gene_categories": [],
        # Phase 2 Item 2 rename: top_pathways → top_metabolite_pathways
        "top_metabolite_pathways": [],
        "by_element": [],
    }

    # Family-inferred dominates — for the auto-warning trigger
    _SUMMARY_ROW_INHERITED_DOMINATES = {
        **_SUMMARY_ROW_BOTH_ARMS,
        "total_matching": 551,
        "gene_count_total": 1,
        "reaction_count_total": 0,
        "transporter_count_total": 1,
        "metabolite_count_total": 551,
        "rows_by_evidence_source": [
            {"evidence_source": "transport", "count": 551},
        ],
        "rows_by_substrate_depth": [
            {"substrate_depth": "most_specific", "count": 0},
            {"substrate_depth": "inherited", "count": 551},
        ],
        "by_gene": [
            {
                "locus_tag": "PMM0913",
                "gene_name": "salY",
                "product": "ABC superfamily ATP-binding cassette transporter",
                "rows": 551,
                "metabolite_count": 551,
                "reaction_count": 0,
                "transporter_count": 1,
                "metabolism_rows": 0,
                "transport_most_specific_rows": 0,
                "transport_inherited_rows": 551,
                # KG-authoritative: ABC-superfamily-only attachment
                "transport_substrate_resolution": "family_inferred",
                "tcdb_evidence_score_max": 0.2,
            },
        ],
    }

    # Sample metabolism-arm detail row (most_specific-by-definition)
    _METAB_ROW = {
        "locus_tag": "PMM0963",
        "gene_name": "ureA",
        "product": "urease gamma subunit",
        "evidence_source": "metabolism",
        "substrate_depth": None,
        "tcdb_evidence_score": None,
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

    # Sample transport-arm detail row (most_specific)
    _TRANS_ROW_MS = {
        "locus_tag": "PMM0963",
        "gene_name": "ureA",
        "product": "urease gamma subunit",
        "evidence_source": "transport",
        "substrate_depth": "most_specific",
        "tcdb_evidence_score": 0.8,
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

    # Sample transport-arm detail row (inherited)
    _TRANS_ROW_INH = {
        "locus_tag": "PMM0913",
        "gene_name": "salY",
        "product": "ABC superfamily ATP-binding cassette transporter",
        "evidence_source": "transport",
        "substrate_depth": "inherited",
        "tcdb_evidence_score": 0.4,
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
        conn = MagicMock()
        # Auto-pad with empty results to cover the post-existence-probe
        # top_pathways query (added in S1 fix to honor spec § 5 verified
        # 3-branch UNION). Tests that need to assert on top_pathways
        # content provide an explicit positional response in the slot.
        conn.execute_query.side_effect = list(side_effect) + [[]] * 4
        return conn

    def _api(self):
        from multiomics_explorer.api.functions import metabolites_by_gene
        return metabolites_by_gene

    # ---- Tests ----

    def test_returns_dict_envelope(self):
        mbg = self._api()
        # summary, metab arm, transport arm, locus_tag existence probe
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, conn=conn)
        assert isinstance(out, dict)
        assert out["total_matching"] == 15
        # MBG envelope keys
        assert "by_gene" in out
        assert "by_evidence_source" in out
        assert "by_substrate_depth" in out
        assert "by_element" in out      # NEW vs GBM
        assert "top_metabolites" in out
        assert "top_reactions" in out
        assert "top_tcdb_families" in out
        assert "top_gene_categories" in out
        # Phase 2 Item 2 rename: top_pathways → top_metabolite_pathways
        assert "top_metabolite_pathways" in out
        assert "not_found" in out
        assert "not_matched" in out
        assert "warnings" in out
        assert "results" in out

    def test_default_fires_both_arms(self):
        """No `evidence_sources` filter → both arms dispatched."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, conn=conn)
        evidence = {r["evidence_source"] for r in out["results"]}
        assert evidence == {"metabolism", "transport"}

    def test_evidence_sources_metabolism_only_skips_transport_arm(self):
        """evidence_sources=['metabolism'] suppresses the transport arm."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(
            self._LOCUS, self._ORG,
            evidence_sources=["metabolism"], conn=conn,
        )
        for r in out["results"]:
            assert r["evidence_source"] == "metabolism"
        assert out["warnings"] == []

    def test_evidence_sources_transport_only_skips_metabolism_arm(self):
        """evidence_sources=['transport'] suppresses the metabolism arm."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(
            self._LOCUS, self._ORG,
            evidence_sources=["transport"], conn=conn,
        )
        for r in out["results"]:
            assert r["evidence_source"] == "transport"
        assert out["warnings"] == []

    def test_ec_numbers_does_not_suppress_transport_arm(self):
        """Per per-arm filter scope: ec_numbers narrows only the metabolism
        arm WHERE; transport-arm rows still appear."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(
            self._LOCUS, self._ORG,
            ec_numbers=["3.5.1.5"], conn=conn,
        )
        evidence = {r["evidence_source"] for r in out["results"]}
        assert "transport" in evidence

    def test_mass_balance_does_not_suppress_transport_arm(self):
        """Same per-arm filter scope as ec_numbers."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(
            self._LOCUS, self._ORG,
            mass_balance="balanced", conn=conn,
        )
        evidence = {r["evidence_source"] for r in out["results"]}
        assert "transport" in evidence

    def test_substrate_depth_most_specific_no_warning(self):
        """substrate_depth=['most_specific'] narrows the transport arm only;
        fixture genes are all `resolved` → no gene-anchored warning."""
        mbg = self._api()
        sc_summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "rows_by_substrate_depth": [
                {"substrate_depth": "most_specific", "count": 2},
            ],
        }
        conn = self._mock_conn(
            [sc_summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(
            self._LOCUS, self._ORG,
            substrate_depth=["most_specific"], conn=conn,
        )
        # Metabolism rows still present (per-arm scope)
        evidence = {r["evidence_source"] for r in out["results"]}
        assert evidence == {"metabolism", "transport"}
        # No auto-warning (user explicitly set substrate_depth)
        assert out["warnings"] == []

    def test_substrate_depth_inherited_no_warning(self):
        """substrate_depth=['inherited'] narrows the transport arm only;
        fixture genes are all `resolved` → no gene-anchored warning."""
        mbg = self._api()
        fi_summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "rows_by_substrate_depth": [
                {"substrate_depth": "inherited", "count": 1},
            ],
        }
        conn = self._mock_conn(
            [fi_summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_INH],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(
            self._LOCUS, self._ORG,
            substrate_depth=["inherited"], conn=conn,
        )
        assert out["warnings"] == []

    def test_family_inferred_resolution_warning_fires(self):
        """substrate_depth migration (gene-anchored warning): fires per gene
        from the KG-authoritative `by_gene[].transport_substrate_resolution
        == 'family_inferred'` (the 9 ABC-only MED4 genes carry it), NOT from
        a row-share threshold. Message states that substrate breadth is
        reachability, not capability, names the flagged gene(s), and carries
        the decision-5 caveat (resolved = at least one non-lumping
        attachment).
        """
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_INHERITED_DOMINATES],
            [],   # metabolism arm fires but returns nothing (PMM0913 transport-only)
            [self._TRANS_ROW_INH],
            [{"found": ["PMM0913"]}],
        )
        out = mbg(["PMM0913"], self._ORG, conn=conn)
        warnings = [w for w in out["warnings"] if "family_inferred" in w]
        assert warnings, (
            f"expected family_inferred-resolution warning, got {out['warnings']!r}"
        )
        warning = warnings[0]
        assert "PMM0913" in warning
        assert "reachability, not capability" in warning
        assert "resolved means at least one non-lumping attachment" in warning
        # Retired vocabulary / param must not leak into the message
        assert "substrate_confirmed" not in warning
        assert "transport_confidence" not in warning

    def test_no_warning_when_every_gene_resolved(self):
        """All by_gene entries `resolved` → no gene-anchored warning even
        when inherited rows outnumber most_specific rows (row share is no
        longer the trigger)."""
        mbg = self._api()
        resolved_but_inherited_heavy = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "rows_by_substrate_depth": [
                {"substrate_depth": "most_specific", "count": 1},
                {"substrate_depth": "inherited", "count": 5},
            ],
            "by_gene": [
                {
                    **self._SUMMARY_ROW_BOTH_ARMS["by_gene"][0],
                    "transport_most_specific_rows": 1,
                    "transport_inherited_rows": 5,
                    "transport_substrate_resolution": "resolved",
                },
            ],
        }
        conn = self._mock_conn(
            [resolved_but_inherited_heavy],
            [self._METAB_ROW],
            [self._TRANS_ROW_INH],
            [{"found": ["PMM0963"]}],
        )
        out = mbg(["PMM0963"], self._ORG, conn=conn)
        assert not [w for w in out["warnings"] if "family_inferred" in w]

    def test_no_warning_when_most_specific_majority(self):
        """All fixture genes resolved, ms >= inherited → no auto-warning."""
        mbg = self._api()
        # 2 SC > 1 FI on transport in default summary
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, conn=conn)
        assert all("inherited" not in w for w in out["warnings"])

    def test_not_found_locus_tags(self):
        """Input locus_tags that don't resolve to any Gene in the requested
        organism surface in not_found.locus_tags."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            # Existence probe returns only 3 of the 4 (PMM9999 missing)
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(
            ["PMM0963", "PMM0964", "PMM0965", "PMM9999"],
            self._ORG, conn=conn,
        )
        assert out["not_found"]["locus_tags"] == ["PMM9999"]

    def test_not_matched_for_resolved_but_no_chemistry(self):
        """locus_tag that resolves in organism but has zero chemistry edges
        (e.g. PMM0005 DNA gyrase) → not_matched (NOT not_found)."""
        mbg = self._api()
        # by_gene only has the 3 urease subunits — PMM0005 resolves but
        # produces no rows.
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            # All four locus_tags exist in organism
            [{"found": ["PMM0963", "PMM0964", "PMM0965", "PMM0005"]}],
        )
        out = mbg(
            ["PMM0963", "PMM0964", "PMM0965", "PMM0005"],
            self._ORG, conn=conn,
        )
        assert "PMM0005" in out["not_matched"]
        assert "PMM0005" not in out["not_found"]["locus_tags"]

    def test_mixed_batch_found_not_found_not_matched(self):
        """Spec § Edge case 10: mixed batch.

        Input: ['PMM0963' chemistry, 'PMM0005' no chemistry, 'PMM9999' nonexistent]
          → results = PMM0963 rows
          → not_matched = ['PMM0005']
          → not_found.locus_tags = ['PMM9999']
        """
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            # Existence probe finds 0963 + 0005, not 9999
            [{"found": ["PMM0963", "PMM0005"]}],
        )
        out = mbg(
            ["PMM0963", "PMM0005", "PMM9999"],
            self._ORG, conn=conn,
        )
        assert out["not_found"]["locus_tags"] == ["PMM9999"]
        assert "PMM0005" in out["not_matched"]
        assert "PMM9999" not in out["not_matched"]

    def test_not_found_organism_when_zero_genes(self, monkeypatch):
        """A word matching zero organisms short-circuits to an empty
        envelope with `not_found.organism` set — no arm queries or
        existence probes run when no metabolite-side filters are given
        (locus_tags can't exist under a nonexistent organism, so
        `not_found.locus_tags` is the full input, no query needed)."""
        mbg = self._api()

        def boom(organism, locus_tags, experiment_ids, conn):
            raise ValueError(
                f"no organism matching '{organism}' found. "
                "Use list_organisms to see valid organism names."
            )
        monkeypatch.setattr(api, "_validate_organism_inputs", boom)
        conn = self._mock_conn()
        out = mbg(self._LOCUS, "Bogus organism", conn=conn)
        assert out["not_found"]["organism"] == "Bogus organism"
        assert out["not_found"]["locus_tags"] == self._LOCUS
        assert out["total_matching"] == 0
        assert out["results"] == []
        conn.execute_query.assert_not_called()

    def test_metabolites_by_gene_probe_uses_resolved_organism(self, monkeypatch):
        """The existence probe (exact match on `g.organism_name`) must use
        the canonical name — passing the raw fuzzy word ('MED4') would
        never match, listing every found gene as not_found (the bug this
        task fixes)."""
        monkeypatch.setattr(
            api, "_validate_organism_inputs",
            lambda o, lt, ex, conn: "Prochlorococcus MED4",
        )
        conn = MagicMock()
        seen = []

        def exec_q(cypher, **params):
            seen.append(params)
            if "collect(DISTINCT g.locus_tag) AS found" in cypher:
                return [{"found": ["PMM0920"]}]
            return []  # every other builder: no rows (mock)
        conn.execute_query.side_effect = exec_q
        out = api.metabolites_by_gene(
            locus_tags=["PMM0920"], organism="MED4", conn=conn,
        )
        probe = [p for p in seen if "locus_tags" in p and "organism" in p][-1]
        assert probe["organism"] == "Prochlorococcus MED4"
        assert out["not_found"]["locus_tags"] == []

    def test_not_found_organism_none_on_success(self):
        """gene_count_total > 0 → not_found.organism is None."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, conn=conn)
        assert out["not_found"]["organism"] is None

    def test_not_found_metabolite_pathway_ids(self):
        """Input metabolite_pathway_ids that don't resolve → bucket."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            # locus_tag existence probe
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
            # pathway-id existence probe
            [{"found": ["kegg.pathway:ko00910"]}],
        )
        out = mbg(
            self._LOCUS, self._ORG,
            metabolite_pathway_ids=[
                "kegg.pathway:ko00910", "kegg.pathway:bogus",
            ],
            conn=conn,
        )
        assert (
            out["not_found"]["metabolite_pathway_ids"]
            == ["kegg.pathway:bogus"]
        )

    def test_not_found_metabolite_elements(self):
        """Input metabolite_elements that don't appear on any KG metabolite
        surface in not_found.metabolite_elements (typo / lowercase)."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            # locus_tag existence probe
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
            # element existence probe — only 'N' is real
            [{"found": ["N"]}],
        )
        out = mbg(
            self._LOCUS, self._ORG,
            metabolite_elements=["N", "Nx"],   # 'Nx' is a typo
            conn=conn,
        )
        assert out["not_found"]["metabolite_elements"] == ["Nx"]

    def test_not_found_metabolite_ids(self):
        """Input metabolite_ids that don't exist as Metabolite node → bucket."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            # locus_tag existence probe
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
            # metabolite-id existence probe
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = mbg(
            self._LOCUS, self._ORG,
            metabolite_ids=[
                "kegg.compound:C00086", "kegg.compound:C99999",
            ],
            conn=conn,
        )
        assert (
            out["not_found"]["metabolite_ids"]
            == ["kegg.compound:C99999"]
        )

    def test_summary_true_skips_detail_dispatch(self):
        """summary=True returns envelope only; detail builders not called.
        Trailing `[]` covers the post-existence-probe top_pathways query
        (S1 fix to honor spec § 5 verified 3-branch UNION)."""
        mbg = self._api()
        conn = MagicMock()
        conn.execute_query.side_effect = [
            [self._SUMMARY_ROW_BOTH_ARMS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
            [],
        ]
        out = mbg(self._LOCUS, self._ORG, summary=True, conn=conn)
        assert out["results"] == []
        assert out["returned"] == 0

    def test_evidence_sources_validator_rejects_bogus(self):
        """ValueError on unknown evidence_source value."""
        mbg = self._api()
        conn = MagicMock()
        with pytest.raises(ValueError):
            mbg(
                self._LOCUS, self._ORG,
                evidence_sources=["bogus"], conn=conn,
            )

    def test_evidence_sources_validator_rejects_metabolomics(self):
        """`metabolomics` is NOT a valid value here — gene-anchored tools
        have no metabolomics path. Per spec § Resolved decisions."""
        mbg = self._api()
        conn = MagicMock()
        with pytest.raises(ValueError):
            mbg(
                self._LOCUS, self._ORG,
                evidence_sources=["metabolomics"], conn=conn,
            )

    def test_truncated_flag(self):
        """When (offset + limit) < total_matching → truncated=True."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],   # total_matching=15
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, limit=2, conn=conn)
        assert out["truncated"] is True

    def test_offset_echoed_in_envelope(self):
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, offset=3, conn=conn)
        assert out["offset"] == 3

    def test_total_count_fields_in_envelope(self):
        """gene_count_total / reaction_count_total / transporter_count_total /
        metabolite_count_total surface on the envelope."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, conn=conn)
        assert out["gene_count_total"] == 3
        assert out["reaction_count_total"] == 1
        assert out["transporter_count_total"] == 3
        assert out["metabolite_count_total"] == 4

    def test_creates_conn_when_none(self):
        """When conn=None, default GraphConnection is created. Trailing
        `[]` covers the post-existence-probe top_pathways query (S1 fix
        to honor spec § 5 verified 3-branch UNION)."""
        mbg = self._api()
        with patch(
            "multiomics_explorer.api.functions.GraphConnection",
        ) as MockConn:
            mock_instance = MockConn.return_value
            mock_instance.execute_query.side_effect = [
                [self._SUMMARY_ROW_BOTH_ARMS],
                [self._METAB_ROW],
                [self._TRANS_ROW_MS],
                [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
                [],
            ]
            out = mbg(self._LOCUS, self._ORG)
        MockConn.assert_called_once()
        assert out["total_matching"] == 15

    def test_importable_from_package(self):
        from multiomics_explorer import (
            metabolites_by_gene as pkg_mbg,
        )
        from multiomics_explorer.api import (
            metabolites_by_gene as api_direct,
        )
        assert pkg_mbg is api_direct

    def test_envelope_carries_by_element_rollup(self):
        """by_element envelope rollup mirrors the verified Cypher example
        in spec § 6 (e.g. urease subunits → [{H,3},{O,3},{C,2},{N,2}])."""
        mbg = self._api()
        with_by_element = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "by_element": [
                {"element": "H", "metabolite_count": 3},
                {"element": "O", "metabolite_count": 3},
                {"element": "C", "metabolite_count": 2},
                {"element": "N", "metabolite_count": 2},
            ],
        }
        conn = self._mock_conn(
            [with_by_element],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, conn=conn)
        elements = {b["element"] for b in out["by_element"]}
        assert elements == {"H", "O", "C", "N"}

    def test_envelope_carries_top_pathways_rollup(self):
        """top_metabolite_pathways envelope rollup with Mbg-shaped fields
        (metabolite_pathway_id, metabolite_pathway_name, gene_count,
        pathway_reaction_count, pathway_metabolite_count). Phase 2 Item 2:
        top_metabolite_pathways is now sourced directly from the summary
        builder (no dedicated post-existence-probe UNION query)."""
        mbg = self._api()
        summary_with_pathways = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "top_metabolite_pathways": [
                {
                    "metabolite_pathway_id": "kegg.pathway:ko00910",
                    "metabolite_pathway_name": "Nitrogen metabolism",
                    "gene_count": 3,
                    "pathway_reaction_count": 23,
                    "pathway_metabolite_count": 35,
                },
            ],
        }
        conn = self._mock_conn(
            [summary_with_pathways],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, conn=conn)
        assert len(out["top_metabolite_pathways"]) == 1
        p = out["top_metabolite_pathways"][0]
        assert p["metabolite_pathway_id"] == "kegg.pathway:ko00910"
        assert p["metabolite_pathway_name"] == "Nitrogen metabolism"
        assert p["gene_count"] == 3
        assert p["pathway_reaction_count"] == 23
        assert p["pathway_metabolite_count"] == 35

    def test_envelope_carries_by_gene_rollup(self):
        """by_gene rollup is INPUT-BOUNDED (gene-anchored mirror of
        GBM's by_metabolite). Fields per Mbg shape."""
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, conn=conn)
        assert len(out["by_gene"]) == 3
        first = out["by_gene"][0]
        assert "locus_tag" in first
        assert "gene_name" in first
        assert "rows" in first
        assert "metabolite_count" in first
        assert "reaction_count" in first
        assert "transporter_count" in first
        assert "metabolism_rows" in first
        assert "transport_most_specific_rows" in first
        assert "transport_inherited_rows" in first

    # ---- substrate_depth migration (spec 2026-08-20; mirrors GBM) ----

    def test_substrate_depth_unknown_value_raises_listing_valid(self):
        mbg = self._api()
        conn = MagicMock()
        with pytest.raises(ValueError) as exc:
            mbg(self._LOCUS, self._ORG, substrate_depth=["bogus"], conn=conn)
        msg = str(exc.value)
        assert "bogus" in msg
        assert "most_specific" in msg and "inherited" in msg
        conn.execute_query.assert_not_called()

    @pytest.mark.parametrize("old_value,new_value", [
        ("substrate_confirmed", "most_specific"),
        ("family_inferred", "inherited"),
    ])
    def test_substrate_depth_old_value_strings_raise_with_rename_pointer(
        self, old_value, new_value,
    ):
        mbg = self._api()
        conn = MagicMock()
        with pytest.raises(ValueError) as exc:
            mbg(self._LOCUS, self._ORG, substrate_depth=[old_value], conn=conn)
        msg = str(exc.value)
        assert old_value in msg
        assert new_value in msg
        assert "substrate_depth" in msg
        conn.execute_query.assert_not_called()

    def test_substrate_depth_forwarded_to_transport_builders(self):
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        mbg(self._LOCUS, self._ORG, substrate_depth=["most_specific"], conn=conn)
        calls = conn.execute_query.call_args_list
        assert calls[0].kwargs.get("substrate_depth") == ["most_specific"]
        metab_cypher, metab_kwargs = calls[1].args[0], calls[1].kwargs
        assert "$substrate_depth" not in metab_cypher
        assert "substrate_depth" not in metab_kwargs
        assert calls[2].kwargs.get("substrate_depth") == ["most_specific"]

    def test_no_transport_confidence_kwarg(self):
        mbg = self._api()
        with pytest.raises(TypeError):
            mbg(self._LOCUS, self._ORG, transport_confidence="substrate_confirmed",
                conn=MagicMock())

    def test_sort_precision_tier_then_score_desc(self):
        """Global precision tier (metabolism → most_specific → inherited),
        then tcdb_evidence_score desc within a transport tier, then
        input-gene order."""
        mbg = self._api()
        low_ms = {**self._TRANS_ROW_MS, "locus_tag": "PMM0963",
                  "metabolite_id": "kegg.compound:C00001",
                  "tcdb_evidence_score": 0.6}
        high_ms = {**self._TRANS_ROW_MS, "locus_tag": "PMM0965",
                   "metabolite_id": "kegg.compound:C00002",
                   "tcdb_evidence_score": 0.8}
        high_inh = {**self._TRANS_ROW_INH, "locus_tag": "PMM0963",
                    "tcdb_evidence_score": 1.0}
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [high_inh, low_ms, high_ms],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, limit=10, conn=conn)
        order = [(r["evidence_source"], r.get("substrate_depth"), r["locus_tag"])
                 for r in out["results"]]
        assert order == [
            ("metabolism", None, "PMM0963"),
            # 0.8 beats 0.6 even though PMM0965 is later in input order
            ("transport", "most_specific", "PMM0965"),
            ("transport", "most_specific", "PMM0963"),
            ("transport", "inherited", "PMM0963"),
        ]

    def test_sort_key_tiebreakers_after_score(self):
        from multiomics_explorer.api.functions import _mbg_sort_key
        idx = {lt: i for i, lt in enumerate(self._LOCUS)}
        a = {**self._TRANS_ROW_MS, "locus_tag": "PMM0965"}
        b = {**self._TRANS_ROW_MS, "locus_tag": "PMM0963"}
        # equal score → input order decides
        assert _mbg_sort_key(b, idx) < _mbg_sort_key(a, idx)
        inh = {**self._TRANS_ROW_INH, "locus_tag": "PMM0963",
               "tcdb_evidence_score": 1.0}
        assert _mbg_sort_key(a, idx) < _mbg_sort_key(inh, idx)
        assert _mbg_sort_key(self._METAB_ROW, idx) < _mbg_sort_key(b, idx)

    def test_by_gene_carries_resolution_and_score_max(self):
        """by_gene[] entries gain transport_substrate_resolution +
        tcdb_evidence_score_max (pass-through from the summary builder;
        null on metabolism-only genes)."""
        mbg = self._api()
        summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "by_gene": [
                *self._SUMMARY_ROW_BOTH_ARMS["by_gene"],
                {
                    "locus_tag": "PMM0001", "gene_name": None, "product": None,
                    "rows": 1, "metabolite_count": 1, "reaction_count": 1,
                    "transporter_count": 0, "metabolism_rows": 1,
                    "transport_most_specific_rows": 0,
                    "transport_inherited_rows": 0,
                    "transport_substrate_resolution": None,
                    "tcdb_evidence_score_max": None,
                },
            ],
        }
        conn = self._mock_conn(
            [summary],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965", "PMM0001"]}],
        )
        out = mbg([*self._LOCUS, "PMM0001"], self._ORG, conn=conn)
        by_lt = {g["locus_tag"]: g for g in out["by_gene"]}
        assert by_lt["PMM0963"]["transport_substrate_resolution"] == "resolved"
        assert by_lt["PMM0963"]["tcdb_evidence_score_max"] == 0.8
        assert by_lt["PMM0001"]["transport_substrate_resolution"] is None
        assert by_lt["PMM0001"]["tcdb_evidence_score_max"] is None
        assert "transport_substrate_confirmed_rows" not in by_lt["PMM0963"]
        assert "transport_family_inferred_rows" not in by_lt["PMM0963"]

    def test_envelope_uses_substrate_depth_names_only(self):
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, conn=conn)
        assert "by_transport_confidence" not in out
        assert {e["substrate_depth"] for e in out["by_substrate_depth"]} == {
            "most_specific", "inherited",
        }
        for row in out["results"]:
            assert "transport_confidence" not in row
            assert "substrate_depth" in row
            assert "tcdb_evidence_score" in row
        trans = next(r for r in out["results"] if r["evidence_source"] == "transport")
        assert trans["substrate_depth"] == "most_specific"
        assert trans["tcdb_evidence_score"] == 0.8

    def test_empty_inputs_zero_rollups(self):
        """All locus_tags in not_matched (resolved but zero chemistry)
        → empty rollups, total_matching=0, no warning, no spurious not_found."""
        mbg = self._api()
        empty_summary = {
            **self._SUMMARY_ROW_BOTH_ARMS,
            "total_matching": 0,
            "gene_count_total": 0,
            "reaction_count_total": 0,
            "transporter_count_total": 0,
            "metabolite_count_total": 0,
            "rows_by_evidence_source": [],
            "rows_by_substrate_depth": [],
            "by_gene": [],
            "by_element": [],
            "top_metabolite_pathways": [],
            "top_metabolites": [],
            "top_reactions": [],
            "top_tcdb_families": [],
            "top_gene_categories": [],
        }
        conn = self._mock_conn(
            [empty_summary],
            [],
            [],
            # All inputs exist in organism but have zero chemistry
            [{"found": ["PMM0005", "PMM0006", "PMM0007"]}],
        )
        out = mbg(["PMM0005", "PMM0006", "PMM0007"], self._ORG, conn=conn)
        assert out["total_matching"] == 0
        assert out["results"] == []
        assert out["warnings"] == []
        assert set(out["not_matched"]) == {"PMM0005", "PMM0006", "PMM0007"}
        assert out["not_found"]["locus_tags"] == []

    # ---- Phase 3 Item 6.1 — None-padding for cross-arm fields ----

    def test_cross_arm_fields_none_padded(self):
        """After Item 6.1 None-padding: every result row carries all 7
        cross-arm keys; arm-specific fields are explicitly None on rows
        from the other arm. Mirrors the GBM test — the row class
        `GeneReactionMetaboliteTriplet` is shared between the two tools.
        """
        mbg = self._api()
        conn = self._mock_conn(
            [self._SUMMARY_ROW_BOTH_ARMS],
            [self._METAB_ROW],
            [self._TRANS_ROW_MS],
            [{"found": ["PMM0963", "PMM0964", "PMM0965"]}],
        )
        out = mbg(self._LOCUS, self._ORG, conn=conn)

        metabolism_rows = [
            r for r in out["results"] if r["evidence_source"] == "metabolism"
        ]
        transport_rows = [
            r for r in out["results"] if r["evidence_source"] == "transport"
        ]
        assert metabolism_rows, (
            "fixture must include at least one metabolism row"
        )
        assert transport_rows, (
            "fixture must include at least one transport row"
        )

        # Metabolism rows: transport-arm cross-arm keys present, value None
        for row in metabolism_rows:
            assert "substrate_depth" in row
            assert row["substrate_depth"] is None
            assert "tcdb_family_id" in row
            assert row["tcdb_family_id"] is None
            assert "tcdb_family_name" in row
            assert row["tcdb_family_name"] is None

        # Transport rows: metabolism-arm cross-arm keys present, value None
        for row in transport_rows:
            assert "reaction_id" in row
            assert row["reaction_id"] is None
            assert "reaction_name" in row
            assert row["reaction_name"] is None
            assert "ec_numbers" in row
            assert row["ec_numbers"] is None
            assert "mass_balance" in row
            assert row["mass_balance"] is None


class TestChemistryInputProbesParity:
    """llm-review 2b.3 Task 6 (carried-over 2b.1 final-review M4).

    `genes_by_metabolite` and `metabolites_by_gene` each ran the same
    metabolite / pathway / element existence-probe Cypher twice: once in
    the organism-unresolved short-circuit, once in the main path. Both now
    call the shared `_chemistry_input_probes` helper. This asserts the
    helper's own shape, that it skips a query entirely for an empty/None
    input, and that the short-circuit and main-path branches of
    `genes_by_metabolite` produce an identical `not_found` key set for the
    same metabolite_ids / metabolite_pathway_ids inputs and the same KG
    existence state — the parity a shared helper is supposed to guarantee.
    """

    def test_probe_dict_shape(self):
        conn = MagicMock()
        conn.execute_query.side_effect = [
            [{"found": ["kegg.compound:C00086"]}],
            [{"found": ["kegg.pathway:ko00910"]}],
            [{"found": ["N"]}],
        ]
        out = api._chemistry_input_probes(
            conn,
            ["kegg.compound:C00086", "kegg.compound:C99999"],
            ["kegg.pathway:ko00910", "kegg.pathway:ko99999"],
            ["N", "Xx"],
        )
        assert out == {
            "not_found_metabolite_ids": ["kegg.compound:C99999"],
            "not_found_pathway_ids": ["kegg.pathway:ko99999"],
            "not_found_elements": ["Xx"],
        }

    def test_empty_or_none_inputs_skip_every_query(self):
        conn = MagicMock()
        out = api._chemistry_input_probes(conn, None, None)
        assert out == {
            "not_found_metabolite_ids": [],
            "not_found_pathway_ids": [],
            "not_found_elements": [],
        }
        conn.execute_query.assert_not_called()

    def test_genes_by_metabolite_short_circuit_and_main_path_agree(
        self, monkeypatch,
    ):
        from multiomics_explorer.api.functions import genes_by_metabolite as gbm

        metabolite_ids = ["kegg.compound:C00086", "kegg.compound:C99999"]
        pathway_ids = ["kegg.pathway:ko00910", "kegg.pathway:ko99999"]
        found_metab = {"found": ["kegg.compound:C00086"]}
        found_paths = {"found": ["kegg.pathway:ko00910"]}

        # --- Short-circuit path: organism doesn't resolve. ---
        def boom(organism, locus_tags, experiment_ids, conn):
            raise ValueError(f"no organism matching '{organism}' found.")
        monkeypatch.setattr(api, "_validate_organism_inputs", boom)
        conn_sc = MagicMock()
        conn_sc.execute_query.side_effect = [[found_metab], [found_paths]]
        out_sc = gbm(
            metabolite_ids, "Bogus organism",
            metabolite_pathway_ids=pathway_ids, conn=conn_sc,
        )

        # --- Main path: organism resolves; zero rows for this slice, so
        # the deep-paging guardrail skips arm queries but existence
        # probes still run. ---
        monkeypatch.setattr(
            api, "_validate_organism_inputs",
            lambda organism, locus_tags, experiment_ids, conn: organism,
        )
        empty_summary = {
            "total_matching": 0, "gene_count_total": 0,
            "reaction_count_total": 0, "transporter_count_total": 0,
            "metabolite_count_total": 0,
            "rows_by_evidence_source": [], "rows_by_substrate_depth": [],
            "by_metabolite": [], "top_reactions": [], "top_tcdb_families": [],
            "top_gene_categories": [], "top_genes": [],
        }
        conn_main = MagicMock()
        conn_main.execute_query.side_effect = [
            [empty_summary],  # summary builder
            [found_metab],    # not_found.metabolite_ids probe
            [found_paths],    # not_found.metabolite_pathway_ids probe
        ]
        out_main = gbm(
            metabolite_ids, "Prochlorococcus MED4",
            metabolite_pathway_ids=pathway_ids, conn=conn_main,
        )

        assert set(out_sc["not_found"].keys()) == set(out_main["not_found"].keys())
        assert (
            out_sc["not_found"]["metabolite_ids"]
            == out_main["not_found"]["metabolite_ids"]
            == ["kegg.compound:C99999"]
        )
        assert (
            out_sc["not_found"]["metabolite_pathway_ids"]
            == out_main["not_found"]["metabolite_pathway_ids"]
            == ["kegg.pathway:ko99999"]
        )


# ===========================================================================
# Cluster A — F1 informativeness surface (frozen spec 2026-05-04)
# ===========================================================================
# API-layer pass-through: the new fields appear in results, the new
# `informative_only` param reaches the underlying builder.


class TestGeneOverviewF1Surface:
    """gene_overview adds annotation_state + informative_annotation_types
    to results and `by_annotation_state` to the envelope."""

    def _summary_with_annotation_state(self):
        return [{
            "total_matching": 1,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 1}],
            "by_category": [{"item": "DNA replication", "count": 1}],
            "by_annotation_type": [{"item": "go_mf", "count": 1}],
            "by_annotation_state": [
                {"item": "informative_multi", "count": 1},
            ],
            "has_expression": 1,
            "has_significant_expression": 1,
            "has_orthologs": 1,
            "has_clusters": 0,
            "has_derived_metrics": 0,
            "not_found": [],
        }]

    def _detail_with_state(self):
        return [{
            "locus_tag": "PMM1428", "gene_name": "test",
            "product": "DNA polymerase III subunit beta",
            "gene_category": "DNA replication",
            "annotation_quality": 3,
            "organism_name": "Prochlorococcus MED4",
            "annotation_types": ["go_mf", "pfam"],
            "expression_edge_count": 0,
            "significant_up_count": 0, "significant_down_count": 0,
            "closest_ortholog_group_size": 9,
            "closest_ortholog_genera": ["Prochlorococcus"],
            "cluster_membership_count": 0, "cluster_types": [],
            "numeric_metric_count": 0,
            "boolean_metric_count": 0,
            "categorical_metric_count": 0,
            # New fields:
            "annotation_state": "informative_multi",
            "informative_annotation_types": ["go_mf", "pfam"],
        }]

    def test_envelope_contains_by_annotation_state(self, mock_conn):
        """Spec § envelope: by_annotation_state added (rollup over results)."""
        mock_conn.execute_query.side_effect = [
            self._summary_with_annotation_state(),
            self._detail_with_state(),
        ]
        result = api.gene_overview(["PMM1428"], conn=mock_conn)
        assert "by_annotation_state" in result
        # _rename_freq path: APOC {item,count} → {annotation_state,count}.
        assert isinstance(result["by_annotation_state"], list)
        assert len(result["by_annotation_state"]) == 1
        first = result["by_annotation_state"][0]
        assert first["count"] == 1
        # The renamed key holds the state value.
        assert first.get("annotation_state") == "informative_multi"

    def test_results_pass_through_annotation_state(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_with_annotation_state(),
            self._detail_with_state(),
        ]
        result = api.gene_overview(["PMM1428"], conn=mock_conn)
        row = result["results"][0]
        assert row["annotation_state"] == "informative_multi"
        assert row["informative_annotation_types"] == ["go_mf", "pfam"]


class TestGeneOntologyTermsF1Surface:
    """gene_ontology_terms threads `informative_only` to builders + returns
    is_informative on rows."""

    def _exist_found(self, *locus_tags):
        return [{"lt": lt, "found": True} for lt in locus_tags]

    def _summary_row(self):
        return [{
            "gene_count": 1, "term_count": 1,
            "by_term": [{"term_id": "go:0006260", "term_name": "DNA replication",
                         "level": 5, "count": 1}],
            "gene_term_counts": [{"locus_tag": "PMM0001", "term_count": 1}],
        }]

    def _detail_rows(self):
        return [{"locus_tag": "PMM0001", "term_id": "go:0006260",
                 "term_name": "DNA replication", "level": 5,
                 "is_informative": True}]

    @patch("multiomics_explorer.api.functions._validate_organism_inputs",
           return_value="Prochlorococcus MED4")
    def test_informative_only_reaches_summary_builder(self, _val, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            self._summary_row(),
            self._detail_rows(),
        ]
        api.gene_ontology_terms(
            ["PMM0001"], organism="MED4", ontology="go_bp",
            informative_only=True, conn=mock_conn,
        )
        # Summary call (the 2nd execute_query call) should carry the
        # builder's informative_only=True propagation. We assert by
        # cypher contents — the builder emits the WHERE filter when True.
        summary_cypher = mock_conn.execute_query.call_args_list[1].args[0]
        assert "AND coalesce(t.is_uninformative, '') <> 'true'" in summary_cypher

    @patch("multiomics_explorer.api.functions._validate_organism_inputs",
           return_value="Prochlorococcus MED4")
    def test_informative_only_reaches_detail_builder(self, _val, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            self._summary_row(),
            self._detail_rows(),
        ]
        api.gene_ontology_terms(
            ["PMM0001"], organism="MED4", ontology="go_bp",
            informative_only=True, conn=mock_conn,
        )
        # Detail call (3rd) — informative_only=True forces WHERE filter.
        detail_cypher = mock_conn.execute_query.call_args_list[2].args[0]
        assert "AND coalesce(t.is_uninformative, '') <> 'true'" in detail_cypher

    @patch("multiomics_explorer.api.functions._validate_organism_inputs",
           return_value="Prochlorococcus MED4")
    def test_default_informative_only_is_false(self, _val, mock_conn):
        """No filter when default param is left untouched."""
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            self._summary_row(),
            self._detail_rows(),
        ]
        api.gene_ontology_terms(
            ["PMM0001"], organism="MED4", ontology="go_bp", conn=mock_conn,
        )
        for call in mock_conn.execute_query.call_args_list[1:]:
            cypher = call.args[0]
            assert "AND coalesce(t.is_uninformative, '') <> 'true'" not in cypher

    @patch("multiomics_explorer.api.functions._validate_organism_inputs",
           return_value="Prochlorococcus MED4")
    def test_is_informative_flows_through_to_results(self, _val, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist_found("PMM0001"),
            self._summary_row(),
            self._detail_rows(),
        ]
        result = api.gene_ontology_terms(
            ["PMM0001"], organism="MED4", ontology="go_bp", conn=mock_conn,
        )
        assert result["results"][0]["is_informative"] is True


class TestGenesByOntologyF1Surface:
    """genes_by_ontology threads informative_only to detail/per_term/per_gene."""

    def _org_resolve(self):
        return [{"organisms": ["Prochlorococcus MED4"]}]

    def _per_term_rows(self):
        return [{
            "term_id": "go:0050896", "term_name": "response to stimulus",
            "level": 1, "best_effort": False, "n_genes": 7,
            "cat_freqs": [{"item": "Stress", "count": 7}],
            "is_informative": True,
        }]

    def _per_gene_rows(self):
        return [{"locus_tag": "PMM0001", "gene_category": "Stress",
                 "n_terms": 1, "levels_hit": [1]}]

    def _detail_rows(self):
        return [{"locus_tag": "PMM0001", "gene_name": None,
                 "product": None, "gene_category": "Stress",
                 "term_id": "go:0050896",
                 "term_name": "response to stimulus", "level": 1,
                 "is_informative": True}]

    def test_informative_only_threads_to_per_term_per_gene_detail(self, mock_conn):
        """Default param routes through helper into all three builders'
        match-stage. Per spec: detail/per_term/per_gene inherit via helper."""
        mock_conn.execute_query.side_effect = [
            self._org_resolve(),
            self._per_term_rows(),
            self._per_gene_rows(),
            self._detail_rows(),
        ]
        api.genes_by_ontology(
            ontology="go_bp", organism="Prochlorococcus MED4",
            level=1, informative_only=True, conn=mock_conn,
        )
        # Calls 2,3,4 are per_term, per_gene, detail. Each must have the filter.
        for call in mock_conn.execute_query.call_args_list[1:]:
            cypher = call.args[0]
            assert "coalesce(t.is_uninformative, '') <> 'true'" in cypher, (
                f"informative_only=True did not reach builder:\n{cypher}"
            )

    def test_default_informative_only_no_filter(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._org_resolve(),
            self._per_term_rows(),
            self._per_gene_rows(),
            self._detail_rows(),
        ]
        api.genes_by_ontology(
            ontology="go_bp", organism="Prochlorococcus MED4",
            level=1, conn=mock_conn,
        )
        # Detail (last call) should still have RETURN-side coalesce only,
        # not the WHERE-side filter, because default informative_only=False.
        # Distinguish WHERE-side `AND coalesce(...)` from RETURN-side
        # `coalesce(...) AS is_informative` since per_term/detail builders
        # always emit the RETURN-side form unconditionally.
        for call in mock_conn.execute_query.call_args_list[1:]:
            cypher = call.args[0]
            assert "AND coalesce(t.is_uninformative, '') <> 'true'" not in cypher

    def test_results_carry_is_informative(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._org_resolve(),
            self._per_term_rows(),
            self._per_gene_rows(),
            self._detail_rows(),
        ]
        result = api.genes_by_ontology(
            ontology="go_bp", organism="Prochlorococcus MED4",
            level=1, conn=mock_conn,
        )
        assert result["results"][0]["is_informative"] is True


class TestSearchOntologyF1Surface:
    """search_ontology threads informative_only + returns is_informative."""

    def _summary_result(self):
        return [{
            "total_entries": 847, "total_matching": 1,
            "score_max": 5.0, "score_median": 5.0,
        }]

    def _detail_rows(self):
        return [{"id": "go:0006260", "name": "DNA replication", "score": 5.0,
                 "level": 5, "is_informative": True}]

    def test_informative_only_reaches_builder(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        api.search_ontology(
            "DNA replication", "go_bp",
            informative_only=True, conn=mock_conn,
        )
        # Summary + detail Cypher both should carry the where-side filter.
        for call in mock_conn.execute_query.call_args_list:
            cypher = call.args[0]
            assert "coalesce(t.is_uninformative, '') <> 'true'" in cypher

    def test_default_informative_only_no_where_filter(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        api.search_ontology(
            "DNA replication", "go_bp", conn=mock_conn,
        )
        # Summary builder doesn't have a RETURN-side coalesce either, so
        # any appearance in the summary cypher would be the where-side filter.
        sum_cypher = mock_conn.execute_query.call_args_list[0].args[0]
        assert "coalesce(t.is_uninformative, '') <> 'true'" not in sum_cypher

    def test_is_informative_flows_through(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._detail_rows(),
        ]
        result = api.search_ontology(
            "DNA replication", "go_bp", conn=mock_conn,
        )
        assert result["results"][0]["is_informative"] is True


class TestOntologyLandscapeF1Surface:
    """ontology_landscape threads informative_only (default-on)."""

    def _conn(self, gene_count, per_ont_rows):
        conn = MagicMock()

        def run(cypher, **params):
            if "RETURN collect(DISTINCT o.preferred_name)" in cypher:
                return [{"organisms": ["Prochlorococcus MED4"]}]
            if "count(g) AS total_genes" in cypher:
                return [{"total_genes": gene_count}]
            from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG
            for ont, rows in per_ont_rows.items():
                cfg = ONTOLOGY_CONFIG[ont]
                if cfg["gene_rel"] in cypher and f":{cfg['label']}" in cypher:
                    return rows
            raise AssertionError(f"no mock for cypher:\n{cypher[:200]}")

        conn.execute_query.side_effect = run
        return conn

    def test_default_filters_uninformative(self):
        """Default param: filter present in landscape Cypher (not opt-out)."""
        per_ont_rows = {"cyanorak_role": []}
        conn = self._conn(gene_count=1976, per_ont_rows=per_ont_rows)
        api.ontology_landscape(
            organism="Prochlorococcus MED4", ontology="cyanorak_role", conn=conn,
        )
        # Find the landscape-builder call.
        cyphers = [c.args[0] for c in conn.execute_query.call_args_list]
        landscape_cyphers = [c for c in cyphers if "n_terms_with_genes" in c]
        assert landscape_cyphers, "expected at least one landscape cypher"
        for c in landscape_cyphers:
            assert "coalesce(t.is_uninformative, '') <> 'true'" in c, (
                "default informative_only=True should emit WHERE filter"
            )

    def test_opt_out_omits_filter(self):
        per_ont_rows = {"cyanorak_role": []}
        conn = self._conn(gene_count=1976, per_ont_rows=per_ont_rows)
        api.ontology_landscape(
            organism="Prochlorococcus MED4", ontology="cyanorak_role",
            informative_only=False, conn=conn,
        )
        cyphers = [c.args[0] for c in conn.execute_query.call_args_list]
        landscape_cyphers = [c for c in cyphers if "n_terms_with_genes" in c]
        for c in landscape_cyphers:
            assert "coalesce(t.is_uninformative, '') <> 'true'" not in c


# ===========================================================================
# Phase 1 — P0 pass-through plumbing (metabolites surface refresh)
# Spec: docs/tool-specs/2026-05-05-phase1-pass-through-plumbing.md
# 6 tools, all additive. Verification cases per spec §6.1 (gene_overview).
# ===========================================================================


class TestGeneOverviewPhase1Plumbing:
    """gene_overview adds reaction_count + catalyzed_metabolite_count +
    evidence_sources per row, plus has_chemistry envelope; the TCDB
    substrate_depth migration (2026-08) replaces transporter_count with
    tcdb_evidence_score_max / transported_metabolite_count /
    transport_substrate_resolution (pass-through; null = no TCDB call).
    Verification cases per spec §6.1 (PMM1428 / PMM0001 / PMM0392 / PMM0628 /
    PMM0263). Catalysis-arm rename (KG-SYNC-001): metabolite_count →
    catalyzed_metabolite_count — catalysis-only, so transport-only genes
    carry 0 (discriminate via tcdb_evidence_score_max / evidence_sources)."""

    def _summary_with_chemistry(self, total=1, has_chemistry=0, not_found=None):
        return [{
            "total_matching": total,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": total}],
            "by_category": [],
            "by_annotation_type": [],
            "has_expression": 0,
            "has_significant_expression": 0,
            "has_orthologs": 0,
            "has_clusters": 0,
            "has_derived_metrics": 0,
            "has_chemistry": has_chemistry,
            "not_found": not_found or [],
        }]

    def _detail_row(self, locus_tag, **chem_overrides):
        """Default row carries no chemistry; overrides for verification cases."""
        row = {
            "locus_tag": locus_tag, "gene_name": None,
            "product": "test", "gene_category": "Unknown",
            "annotation_quality": 0,
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
            "reaction_count": 0,
            "catalyzed_metabolite_count": 0,
            "tcdb_evidence_score_max": None,
            "transported_metabolite_count": 0,
            "transport_substrate_resolution": None,
            "evidence_sources": [],
        }
        row.update(chem_overrides)
        return row

    def test_pmm1428_no_chemistry_zeros_and_empty(self, mock_conn):
        """PMM1428 (EVE domain) — all zeros / empty list per spec §6.1."""
        mock_conn.execute_query.side_effect = [
            self._summary_with_chemistry(total=1, has_chemistry=0),
            [self._detail_row("PMM1428")],
        ]
        result = api.gene_overview(["PMM1428"], conn=mock_conn)
        row = result["results"][0]
        assert row["reaction_count"] == 0
        assert row["catalyzed_metabolite_count"] == 0
        assert "transporter_count" not in row
        assert row["tcdb_evidence_score_max"] is None
        assert row["transported_metabolite_count"] == 0
        assert row["transport_substrate_resolution"] is None
        assert row["evidence_sources"] == []

    def test_pmm0001_metabolism_only(self, mock_conn):
        """PMM0001: 4 reactions, 6 catalyzed metabolites, no TCDB call
        (score null / transported 0 / resolution null — live-verified
        2026-08-20), ['metabolism']."""
        mock_conn.execute_query.side_effect = [
            self._summary_with_chemistry(total=1, has_chemistry=1),
            [self._detail_row(
                "PMM0001",
                reaction_count=4, catalyzed_metabolite_count=6,
                evidence_sources=["metabolism"],
            )],
        ]
        result = api.gene_overview(["PMM0001"], conn=mock_conn)
        row = result["results"][0]
        assert row["reaction_count"] == 4
        assert row["catalyzed_metabolite_count"] == 6
        assert "transporter_count" not in row
        assert row["tcdb_evidence_score_max"] is None
        assert row["transported_metabolite_count"] == 0
        assert row["transport_substrate_resolution"] is None
        assert row["evidence_sources"] == ["metabolism"]

    def test_pmm0392_transport_and_metabolomics(self, mock_conn):
        """PMM0392: 0 reactions, 0 catalyzed metabolites (transport-only —
        catalysis-arm count is 0 post-rename, live-KG verified),
        tcdb_evidence_score_max 0.8 / transported_metabolite_count 13 /
        'resolved' (live-verified 2026-08-26), ['transport', 'metabolomics'].
        Critical reproducer: reaction_count=0 must NOT promote 'metabolism'."""
        mock_conn.execute_query.side_effect = [
            self._summary_with_chemistry(total=1, has_chemistry=1),
            [self._detail_row(
                "PMM0392",
                reaction_count=0, catalyzed_metabolite_count=0,
                tcdb_evidence_score_max=0.8,
                transported_metabolite_count=13,
                transport_substrate_resolution="resolved",
                evidence_sources=["transport", "metabolomics"],
            )],
        ]
        result = api.gene_overview(["PMM0392"], conn=mock_conn)
        row = result["results"][0]
        assert row["reaction_count"] == 0
        assert row["catalyzed_metabolite_count"] == 0
        assert "transporter_count" not in row
        assert row["tcdb_evidence_score_max"] == 0.8
        assert row["transported_metabolite_count"] == 13
        assert row["transport_substrate_resolution"] == "resolved"
        assert row["evidence_sources"] == ["transport", "metabolomics"]
        assert "metabolism" not in row["evidence_sources"]

    def test_pmm0628_transport_with_measurement(self, mock_conn):
        """PMM0628: 0 / 0 catalyzed / TCDB call present /
        ['transport', 'metabolomics'] (transport-only → catalyzed count 0)."""
        mock_conn.execute_query.side_effect = [
            self._summary_with_chemistry(total=1, has_chemistry=1),
            [self._detail_row(
                "PMM0628",
                reaction_count=0, catalyzed_metabolite_count=0,
                tcdb_evidence_score_max=0.6,
                transported_metabolite_count=1,
                transport_substrate_resolution="resolved",
                evidence_sources=["transport", "metabolomics"],
            )],
        ]
        result = api.gene_overview(["PMM0628"], conn=mock_conn)
        row = result["results"][0]
        assert row["tcdb_evidence_score_max"] == 0.6
        assert row["transported_metabolite_count"] == 1
        assert row["transport_substrate_resolution"] == "resolved"
        assert row["evidence_sources"] == ["transport", "metabolomics"]

    def test_pmm0263_transport_only_no_measured(self, mock_conn):
        """PMM0263: 0 / 0 catalyzed / TCDB call present / ['transport'] —
        transport-only reachable metabolites not in 107 measured, so
        'metabolomics' correctly drops out (catalysis-arm count 0)."""
        mock_conn.execute_query.side_effect = [
            self._summary_with_chemistry(total=1, has_chemistry=1),
            [self._detail_row(
                "PMM0263",
                reaction_count=0, catalyzed_metabolite_count=0,
                tcdb_evidence_score_max=0.4,
                transported_metabolite_count=1,
                transport_substrate_resolution="family_inferred",
                evidence_sources=["transport"],
            )],
        ]
        result = api.gene_overview(["PMM0263"], conn=mock_conn)
        row = result["results"][0]
        assert row["evidence_sources"] == ["transport"]
        assert "metabolomics" not in row["evidence_sources"]

    def test_envelope_has_chemistry_present(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_with_chemistry(total=1, has_chemistry=1),
            [self._detail_row(
                "PMM0001", reaction_count=4, evidence_sources=["metabolism"],
            )],
        ]
        result = api.gene_overview(["PMM0001"], conn=mock_conn)
        assert "has_chemistry" in result
        assert result["has_chemistry"] == 1

    def test_envelope_has_chemistry_zero(self, mock_conn):
        """Empty evidence_sources => has_chemistry stays at 0."""
        mock_conn.execute_query.side_effect = [
            self._summary_with_chemistry(total=1, has_chemistry=0),
            [self._detail_row("PMM1428")],
        ]
        result = api.gene_overview(["PMM1428"], conn=mock_conn)
        assert result["has_chemistry"] == 0

    def test_evidence_sources_defaults_empty_when_absent(self, mock_conn):
        """Per spec — when chemistry edges are absent, evidence_sources is
        a list (possibly empty), never null on the response row."""
        mock_conn.execute_query.side_effect = [
            self._summary_with_chemistry(total=1, has_chemistry=0),
            [self._detail_row("PMM1428")],  # default factory sets [] above
        ]
        result = api.gene_overview(["PMM1428"], conn=mock_conn)
        row = result["results"][0]
        assert row["evidence_sources"] == []


class TestListPublicationsPhase1Plumbing:
    """list_publications adds 3 metabolite measurement pass-through fields
    per row (spec §6.2). Pure pass-through — no envelope change."""

    _PUB_BASE = {
        "doi": "10.1234/test", "title": "Test", "authors": ["A"],
        "year": 2024, "journal": "J", "study_type": "S",
        "organisms": ["MED4"], "experiment_count": 1,
        "treatment_types": ["coculture"], "background_factors": [],
        "omics_types": ["RNASEQ"],
        "clustering_analysis_count": 0, "cluster_types": [],
    }

    def test_metabolite_count_passes_through(self, mock_conn):
        row = {**self._PUB_BASE, "metabolite_count": 42,
               "metabolite_assay_count": 18, "metabolite_compartments": ["whole_cell"]}
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 1, "total_matching": 1}], [row],
        ]
        result = api.list_publications(conn=mock_conn)
        r = result["results"][0]
        assert r["metabolite_count"] == 42
        assert r["metabolite_assay_count"] == 18
        assert r["metabolite_compartments"] == ["whole_cell"]

    def test_zero_when_no_measurement(self, mock_conn):
        """Publication without metabolomics data — fields default to 0/[]."""
        row = {**self._PUB_BASE, "metabolite_count": 0,
               "metabolite_assay_count": 0, "metabolite_compartments": []}
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 1, "total_matching": 1}], [row],
        ]
        result = api.list_publications(conn=mock_conn)
        r = result["results"][0]
        assert r["metabolite_count"] == 0
        assert r["metabolite_assay_count"] == 0
        assert r["metabolite_compartments"] == []

    def test_dual_compartment_publication(self, mock_conn):
        """Capovilla 2023 / Kujawinski 2023 example: papers measuring multiple
        compartments — list comes through as-is."""
        row = {**self._PUB_BASE, "metabolite_count": 92,
               "metabolite_assay_count": 92,
               "metabolite_compartments": ["extracellular", "whole_cell"]}
        mock_conn.execute_query.side_effect = [
            [{"total_entries": 1, "total_matching": 1}], [row],
        ]
        result = api.list_publications(conn=mock_conn)
        r = result["results"][0]
        assert r["metabolite_compartments"] == ["extracellular", "whole_cell"]


class TestListExperimentsPhase1Plumbing:
    """list_experiments adds 3 metabolite measurement pass-through fields
    per row (spec §6.3). Symmetric with list_publications."""

    def _summary_result(self):
        return [{
            "total_matching": 1, "time_course_count": 0,
            "by_organism": [{"item": "MED4", "count": 1}],
            "by_treatment_type": [],
            "by_background_factors": [],
            "by_omics_type": [{"item": "METABOLOMICS", "count": 1}],
            "by_publication": [],
            "by_table_scope": [],
            "by_cluster_type": [],
            "by_growth_phase": [],
        }]

    def _exp_row(self, **overrides):
        row = {
            "experiment_id": "exp_a", "experiment_name": "A",
            "publication_doi": "10.1234/a",
            "organism_name": "MED4", "treatment_type": ["control"],
            "coculture_partner": None, "omics_type": "METABOLOMICS",
            "is_time_course": "single_time_point",
            "table_scope": "all_detected_genes",
            "table_scope_detail": None,
            "gene_count": 0, "distinct_gene_count": 0,
            "significant_up_count": 0, "significant_down_count": 0,
            "time_point_count": 1, "time_point_labels": ["20h"],
            "time_point_orders": [1], "time_point_hours": [20.0],
            "time_point_totals": [0], "time_point_significant_up": [0],
            "time_point_significant_down": [0],
            "clustering_analysis_count": 0, "cluster_types": [],
            "metabolite_count": 0,
            "metabolite_assay_count": 0,
            "metabolite_compartments": [],
        }
        row.update(overrides)
        return row

    def test_metabolite_count_passes_through(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_result(),  # filtered summary
            self._summary_result(),  # unfiltered total_entries
            [self._exp_row(metabolite_count=42, metabolite_assay_count=18,
                           metabolite_compartments=["whole_cell"])],
        ]
        result = api.list_experiments(conn=mock_conn)
        r = result["results"][0]
        assert r["metabolite_count"] == 42
        assert r["metabolite_assay_count"] == 18
        assert r["metabolite_compartments"] == ["whole_cell"]

    def test_zero_when_no_measurement(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary_result(),
            self._summary_result(),
            [self._exp_row()],
        ]
        result = api.list_experiments(conn=mock_conn)
        r = result["results"][0]
        assert r["metabolite_count"] == 0
        assert r["metabolite_assay_count"] == 0
        assert r["metabolite_compartments"] == []


class TestListOrganismsPhase1Plumbing:
    """list_organisms adds measured_metabolite_count per row + binary
    by_measurement_capability envelope (spec §6.4)."""

    _ROW_HIGH = {
        "organism_name": "Prochlorococcus MIT9301", "organism_type": "genome_strain",
        "genus": "Prochlorococcus", "species": "Prochlorococcus marinus",
        "strain": "MIT9301", "clade": "HLII", "ncbi_taxon_id": 167546,
        "gene_count": 1900, "publication_count": 5, "experiment_count": 12,
        "treatment_types": [], "background_factors": [],
        "omics_types": ["METABOLOMICS"], "clustering_analysis_count": 0,
        "cluster_types": [], "derived_metric_count": 0,
        "derived_metric_value_kinds": [], "compartments": [],
        "reaction_count": 0, "catalyzed_metabolite_count": 0,
        "measured_metabolite_count": 4,
    }
    _ROW_NONE = {
        "organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain",
        "genus": "Prochlorococcus", "species": "Prochlorococcus marinus",
        "strain": "MED4", "clade": "HLI", "ncbi_taxon_id": 59919,
        "gene_count": 1976, "publication_count": 11, "experiment_count": 46,
        "treatment_types": [], "background_factors": [],
        "omics_types": ["RNASEQ"], "clustering_analysis_count": 0,
        "cluster_types": [], "derived_metric_count": 0,
        "derived_metric_value_kinds": [], "compartments": [],
        "reaction_count": 0, "catalyzed_metabolite_count": 0,
        "measured_metabolite_count": 0,
    }
    _SUMMARY_ROW = {
        "total_entries": 2, "total_matching": 2,
        "by_value_kind": [], "by_metric_type": [],
        "by_compartment": [],
        "by_cluster_type": [], "by_organism_type": [],
        "by_measurement_capability": {
            "has_metabolomics": 1, "no_metabolomics": 1,
        },
    }

    def test_measured_metabolite_count_per_row(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], [self._ROW_HIGH, self._ROW_NONE],
        ]
        result = api.list_organisms(conn=mock_conn)
        # Row order isn't strict here — assert by name lookup.
        by_name = {r["organism_name"]: r for r in result["results"]}
        assert by_name["Prochlorococcus MIT9301"]["measured_metabolite_count"] == 4
        assert by_name["Prochlorococcus MED4"]["measured_metabolite_count"] == 0

    def test_envelope_has_by_measurement_capability(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], [self._ROW_HIGH, self._ROW_NONE],
        ]
        result = api.list_organisms(conn=mock_conn)
        assert "by_measurement_capability" in result

    def test_envelope_binary_buckets_sum_to_total(self, mock_conn):
        """Spec §6.4: has_metabolomics + no_metabolomics == total organisms."""
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_ROW], [self._ROW_HIGH, self._ROW_NONE],
        ]
        result = api.list_organisms(conn=mock_conn)
        cap = result["by_measurement_capability"]
        # The shape is a dict per spec ({has_metabolomics, no_metabolomics}).
        assert isinstance(cap, dict)
        assert cap["has_metabolomics"] == 1
        assert cap["no_metabolomics"] == 1
        assert cap["has_metabolomics"] + cap["no_metabolomics"] == 2

    def test_envelope_summary_mode(self, mock_conn):
        """summary=True still surfaces by_measurement_capability."""
        mock_conn.execute_query.return_value = [self._SUMMARY_ROW]
        result = api.list_organisms(summary=True, conn=mock_conn)
        assert "by_measurement_capability" in result


class TestListFilterValuesPhase1Plumbing:
    """list_filter_values gains two new filter_type values: omics_type and
    evidence_source (spec §6.5)."""

    def test_dispatches_omics_type(self, mock_conn):
        """omics_type returns canonical OMICS_TYPE enum (8 values)."""
        # Mock returns 7 of 8 values present in KG; the function must merge
        # canonical METABOLOMICS even at count=0.
        mock_conn.execute_query.return_value = [
            {"value": "RNASEQ", "count": 80},
            {"value": "PROTEOMICS", "count": 30},
            {"value": "MICROARRAY", "count": 12},
            {"value": "EXOPROTEOMICS", "count": 5},
            {"value": "VESICLE_DNASEQ", "count": 4},
            {"value": "VESICLE_PROTEOMICS", "count": 4},
            {"value": "PAIRED_RNASEQ_PROTEOME", "count": 2},
            {"value": "METABOLOMICS", "count": 1},
        ]
        result = api.list_filter_values(filter_type="omics_type", conn=mock_conn)
        assert result["filter_type"] == "omics_type"
        # 8 distinct OMICS_TYPE enum values per spec §6.5.
        values = {r["value"] for r in result["results"]}
        assert "METABOLOMICS" in values
        assert "RNASEQ" in values
        assert "PROTEOMICS" in values
        assert len(values) == 8

    def test_omics_type_includes_metabolomics_even_when_zero(self, mock_conn):
        """Spec §6.5 — METABOLOMICS must appear even when no Experiment carries it.
        Canonical enum is merged in Python after the Cypher count."""
        # Cypher returns count rows for some omics types but NOT METABOLOMICS.
        mock_conn.execute_query.return_value = [
            {"value": "RNASEQ", "count": 80},
            {"value": "PROTEOMICS", "count": 30},
        ]
        result = api.list_filter_values(filter_type="omics_type", conn=mock_conn)
        values = {r["value"] for r in result["results"]}
        assert "METABOLOMICS" in values
        # The METABOLOMICS row must surface count=0 for backward-consistency.
        metab_row = next(r for r in result["results"] if r["value"] == "METABOLOMICS")
        assert metab_row["count"] == 0

    def test_dispatches_evidence_source(self, mock_conn):
        """evidence_source returns 3 values: metabolism / transport / metabolomics."""
        mock_conn.execute_query.return_value = [
            {"value": "metabolism", "count": 2188},
            {"value": "transport", "count": 1355},
            {"value": "metabolomics", "count": 107},
        ]
        result = api.list_filter_values(
            filter_type="evidence_source", conn=mock_conn,
        )
        assert result["filter_type"] == "evidence_source"
        assert result["total_entries"] == 3
        values = {r["value"] for r in result["results"]}
        assert values == {"metabolism", "transport", "metabolomics"}
        by_value = {r["value"]: r["count"] for r in result["results"]}
        assert by_value["metabolism"] == 2188
        assert by_value["transport"] == 1355
        assert by_value["metabolomics"] == 107


class TestListMetabolitesPhase1Plumbing:
    """list_metabolites adds 4 measurement pass-through fields per row +
    by_measurement_coverage envelope (spec §6.6). All KG fields populated
    by post-import — KG-MET-016 closed."""

    _SUMMARY_ROW = {
        "total_entries": 3218, "total_matching": 1,
        "top_organisms": [],
        "top_metabolite_pathways": [],
        "by_evidence_source": [{"item": "metabolism", "count": 1}],
        "with_chebi": 0, "with_hmdb": 0, "with_mnxm": 0,
        "mass_min": None, "mass_median": None, "mass_max": None,
        # Raw apoc.coll.frequencies output shape — `{item, count}`. The api
        # layer's `_rename_measurement_coverage` transforms this into the
        # Pydantic-expected `{paper_count, count}` / `{compartment, count}`
        # shape. Tests below assert the post-transform output.
        "by_measurement_coverage": {
            "by_paper_count": [
                {"item": 0, "count": 3111},
                {"item": 1, "count": 99},
                {"item": 2, "count": 8},
            ],
            "by_compartment": [
                {"item": "whole_cell", "count": 107},
                {"item": "extracellular", "count": 92},
            ],
        },
    }

    _DETAIL_ROW = {
        "metabolite_id": "kegg.compound:C00031",
        "name": "D-Glucose",
        "formula": "C6H12O6",
        "elements": ["C", "H", "O"],
        "mass": 180.156,
        "catalyst_gene_count": 320,
        "organism_count": 31,
        "transporter_count": 17,
        "evidence_sources": ["metabolism", "metabolomics"],
        "chebi_id": "4167",
        "pathway_ids": ["kegg.pathway:ko00010"],
        "pathway_count": 1,
        # New measurement fields:
        "measured_assay_count": 4,
        "measured_paper_count": 1,
        "measured_organisms": ["Prochlorococcus MIT9301"],
        "measured_compartments": ["whole_cell"],
    }

    def _mock_conn(self, summary_row, detail_rows, *extra):
        conn = MagicMock()
        side_effect = [[summary_row], detail_rows]
        side_effect.extend(extra)
        conn.execute_query.side_effect = side_effect
        return conn

    def test_per_row_measured_assay_count(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(conn=conn)
        r = out["results"][0]
        assert r["measured_assay_count"] == 4

    def test_per_row_measured_paper_count(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(conn=conn)
        r = out["results"][0]
        assert r["measured_paper_count"] == 1

    def test_per_row_measured_organisms(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(conn=conn)
        r = out["results"][0]
        assert r["measured_organisms"] == ["Prochlorococcus MIT9301"]

    def test_per_row_measured_compartments(self):
        """KG-MET-016 closed: populated on all 107 measured metabolites."""
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(conn=conn)
        r = out["results"][0]
        assert r["measured_compartments"] == ["whole_cell"]

    def test_unmeasured_metabolite_zero_and_empty(self):
        """3111 unmeasured metabolites: assay_count=0, paper_count=0,
        organisms=[], compartments=[] — never None per KG default-empty
        convention (spec §6.6)."""
        from multiomics_explorer.api.functions import list_metabolites
        unmeasured_row = {
            **self._DETAIL_ROW,
            "evidence_sources": ["metabolism"],
            "measured_assay_count": 0,
            "measured_paper_count": 0,
            "measured_organisms": [],
            "measured_compartments": [],
        }
        conn = self._mock_conn(self._SUMMARY_ROW, [unmeasured_row])
        out = list_metabolites(conn=conn)
        r = out["results"][0]
        assert r["measured_assay_count"] == 0
        assert r["measured_paper_count"] == 0
        assert r["measured_organisms"] == []
        assert r["measured_compartments"] == []

    def test_envelope_has_by_measurement_coverage(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(conn=conn)
        assert "by_measurement_coverage" in out

    def test_envelope_coverage_has_paper_count_subkey(self):
        """Spec §6.6: by_measurement_coverage.by_paper_count exposes the
        live distribution (3111 / 99 / 8). The api layer renames apoc's
        `{item, count}` to `{paper_count, count}` per Pydantic contract."""
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(conn=conn)
        cov = out["by_measurement_coverage"]
        assert "by_paper_count" in cov
        # 3 buckets matching the live KG counts.
        buckets = {b["paper_count"]: b["count"] for b in cov["by_paper_count"]}
        assert buckets[0] == 3111
        assert buckets[1] == 99
        assert buckets[2] == 8

    def test_envelope_coverage_has_compartment_subkey(self):
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(conn=conn)
        cov = out["by_measurement_coverage"]
        assert "by_compartment" in cov


# ===========================================================================
# Phase 2 — Cross-cutting renames + filter additions (frozen spec
# 2026-05-05-phase2-cross-cutting-renames.md). Stage 1 RED — failing tests.
# ===========================================================================


class TestListMetabolitesPhase2:
    """API-layer tests for Phase 2 items 2 and 3 on list_metabolites.

    Item 1 (search → search_text) is exercised structurally by the
    existing `test_lucene_retry_on_parse_error` and
    `test_search_empty_validation` tests, which were renamed in place.
    """

    _SUMMARY_ROW = {
        "total_entries": 3025,
        "total_matching": 1,
        "top_organisms": [],
        # Phase 2 Item 2: renamed envelope key + per-element keys.
        "top_metabolite_pathways": [
            {
                "metabolite_pathway_id": "kegg.pathway:ko01100",
                "metabolite_pathway_name": "Metabolic pathways",
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
        "catalyst_gene_count": 320,
        "organism_count": 31,
        "transporter_count": 17,
        "evidence_sources": ["metabolism"],
        "chebi_id": "4167",
        "pathway_ids": ["kegg.pathway:ko00010"],
        "pathway_count": 1,
    }

    def _mock_conn(self, summary_row, detail_rows):
        conn = MagicMock()
        conn.execute_query.side_effect = [[summary_row], detail_rows]
        return conn

    def test_envelope_top_metabolite_pathways_propagated(self):
        """Phase 2 Item 2: api passes through renamed envelope rollup."""
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        out = list_metabolites(conn=conn)
        assert "top_metabolite_pathways" in out
        assert len(out["top_metabolite_pathways"]) == 1
        entry = out["top_metabolite_pathways"][0]
        assert entry["metabolite_pathway_id"] == "kegg.pathway:ko01100"
        assert entry["metabolite_pathway_name"] == "Metabolic pathways"
        assert entry["count"] == 1

    def test_exclude_metabolite_ids_passed(self):
        """Phase 2 Item 3: api forwards exclude_metabolite_ids to builder."""
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        list_metabolites(
            exclude_metabolite_ids=[
                "kegg.compound:C00002", "kegg.compound:C00008",
            ],
            conn=conn,
        )
        # Inspect the summary call (first call) — kwargs should carry
        # the exclude list through to the builder.
        summary_call = conn.execute_query.call_args_list[0]
        kw = summary_call.kwargs
        # The builder param `exclude_metabolite_ids` is passed as a
        # Cypher param of the same name — so it appears in execute_query
        # kwargs.
        assert kw.get("exclude_metabolite_ids") == [
            "kegg.compound:C00002", "kegg.compound:C00008",
        ]

    def test_exclude_metabolite_ids_default_none(self):
        """Default (no exclude param) → no exclude_metabolite_ids in
        builder kwargs."""
        from multiomics_explorer.api.functions import list_metabolites
        conn = self._mock_conn(self._SUMMARY_ROW, [self._DETAIL_ROW])
        list_metabolites(conn=conn)
        summary_call = conn.execute_query.call_args_list[0]
        kw = summary_call.kwargs
        assert "exclude_metabolite_ids" not in kw


class TestGenesByMetabolitePhase2:
    """API-layer tests for Phase 2 item 3 on genes_by_metabolite."""

    _METS = ["kegg.compound:C00086"]
    _ORG = "Prochlorococcus MED4"

    @pytest.fixture(autouse=True)
    def _mock_validate_organism_inputs(self, monkeypatch):
        monkeypatch.setattr(
            api, "_validate_organism_inputs",
            lambda organism, locus_tags, experiment_ids, conn: organism,
        )

    _SUMMARY_ROW = {
        "total_matching": 0,
        "gene_count_total": 0,
        "reaction_count_total": 0,
        "transporter_count_total": 0,
        "metabolite_count_total": 0,
        "rows_by_evidence_source": [],
        "rows_by_substrate_depth": [],
        "by_metabolite": [],
        "top_reactions": [],
        "top_tcdb_families": [],
        "top_gene_categories": [],
        "top_genes": [],
    }

    def _mock_conn(self):
        """Provide a wide buffer of empty results to satisfy probes."""
        conn = MagicMock()
        conn.execute_query.side_effect = [
            [self._SUMMARY_ROW],
        ] + [[]] * 10
        return conn

    def test_exclude_metabolite_ids_passed(self):
        from multiomics_explorer.api.functions import genes_by_metabolite
        conn = self._mock_conn()
        genes_by_metabolite(
            metabolite_ids=self._METS, organism=self._ORG,
            exclude_metabolite_ids=["kegg.compound:C00002"],
            summary=True, conn=conn,
        )
        summary_call = conn.execute_query.call_args_list[0]
        kw = summary_call.kwargs
        assert kw.get("exclude_metabolite_ids") == ["kegg.compound:C00002"]

    def test_exclude_metabolite_ids_default_none(self):
        from multiomics_explorer.api.functions import genes_by_metabolite
        conn = self._mock_conn()
        genes_by_metabolite(
            metabolite_ids=self._METS, organism=self._ORG,
            summary=True, conn=conn,
        )
        summary_call = conn.execute_query.call_args_list[0]
        kw = summary_call.kwargs
        assert "exclude_metabolite_ids" not in kw


class TestMetabolitesByGenePhase2:
    """API-layer tests for Phase 2 items 2 + 3 on metabolites_by_gene."""

    _LOCUS = ["PMM0963", "PMM0964", "PMM0965"]
    _ORG = "Prochlorococcus MED4"

    @pytest.fixture(autouse=True)
    def _mock_validate_organism_inputs(self, monkeypatch):
        monkeypatch.setattr(
            api, "_validate_organism_inputs",
            lambda organism, locus_tags, experiment_ids, conn: organism,
        )

    _SUMMARY_ROW = {
        "total_matching": 0,
        "gene_count_total": 0,
        "reaction_count_total": 0,
        "transporter_count_total": 0,
        "metabolite_count_total": 0,
        "rows_by_evidence_source": [],
        "rows_by_substrate_depth": [],
        "by_gene": [],
        "top_metabolites": [],
        "top_reactions": [],
        "top_tcdb_families": [],
        "top_gene_categories": [],
        # Phase 2 Item 2: renamed envelope key.
        "top_metabolite_pathways": [
            {
                "metabolite_pathway_id": "kegg.pathway:ko00910",
                "metabolite_pathway_name": "Nitrogen metabolism",
                "gene_count": 3,
                "pathway_reaction_count": 23,
                "pathway_metabolite_count": 35,
            },
        ],
        "by_element": [],
    }

    def _mock_conn(self):
        conn = MagicMock()
        conn.execute_query.side_effect = [
            [self._SUMMARY_ROW],
        ] + [[]] * 10
        return conn

    def test_envelope_top_metabolite_pathways_propagated(self):
        """Phase 2 Item 2: api passes through renamed envelope rollup."""
        from multiomics_explorer.api.functions import metabolites_by_gene
        conn = self._mock_conn()
        out = metabolites_by_gene(
            self._LOCUS, self._ORG, summary=True, conn=conn,
        )
        assert "top_metabolite_pathways" in out
        assert len(out["top_metabolite_pathways"]) == 1
        entry = out["top_metabolite_pathways"][0]
        assert entry["metabolite_pathway_id"] == "kegg.pathway:ko00910"
        assert entry["metabolite_pathway_name"] == "Nitrogen metabolism"
        # Other element keys unchanged
        assert entry["gene_count"] == 3
        assert entry["pathway_reaction_count"] == 23
        assert entry["pathway_metabolite_count"] == 35

    def test_exclude_metabolite_ids_passed(self):
        from multiomics_explorer.api.functions import metabolites_by_gene
        conn = self._mock_conn()
        metabolites_by_gene(
            self._LOCUS, self._ORG,
            exclude_metabolite_ids=["kegg.compound:C00002"],
            summary=True, conn=conn,
        )
        summary_call = conn.execute_query.call_args_list[0]
        kw = summary_call.kwargs
        assert kw.get("exclude_metabolite_ids") == ["kegg.compound:C00002"]

    def test_exclude_metabolite_ids_default_none(self):
        from multiomics_explorer.api.functions import metabolites_by_gene
        conn = self._mock_conn()
        metabolites_by_gene(
            self._LOCUS, self._ORG, summary=True, conn=conn,
        )
        summary_call = conn.execute_query.call_args_list[0]
        kw = summary_call.kwargs
        assert "exclude_metabolite_ids" not in kw


class TestDifferentialExpressionByGenePhase2:
    """API-layer tests for Phase 2 item 4 — direction='both'."""

    def _organism_result(self, orgs=None):
        if orgs is None:
            orgs = ["Prochlorococcus MED4"]
        return [{"organisms": orgs}]

    def _global_summary(self):
        return [{
            "total_matching": 6,
            "matching_genes": 4,
            "rows_by_status": [
                {"item": "significant_up", "count": 3},
                {"item": "significant_down", "count": 3},
            ],
            "rows_by_treatment_type": [
                {"item": "nitrogen_stress", "count": 6},
            ],
            "rows_by_background_factors": [],
            "by_table_scope": [
                {"item": "all_detected_genes", "count": 6},
            ],
            "median_abs_log2fc": 1.5,
            "max_abs_log2fc": 3.5,
        }]

    def _experiment_summary(self):
        return [{
            "organism_name": "Prochlorococcus MED4",
            "experiments": [],
        }]

    def _diagnostics_summary(self):
        return [{
            "top_categories": [],
            "not_found": [],
            "no_expression": [],
            "filtered_out": [],
        }]

    def _detail_rows(self):
        return [
            {
                "locus_tag": "PMM0001", "gene_name": "dnaN",
                "experiment_id": "exp1", "treatment_type": "nitrogen_stress",
                "timepoint": "day 18", "timepoint_hours": 432.0,
                "timepoint_order": 1,
                "log2fc": 3.5, "padj": 1e-12, "rank": 1,
                "expression_status": "significant_up",
            },
            {
                "locus_tag": "PMM0002", "gene_name": "rpoA",
                "experiment_id": "exp1", "treatment_type": "nitrogen_stress",
                "timepoint": "day 18", "timepoint_hours": 432.0,
                "timepoint_order": 1,
                "log2fc": -2.5, "padj": 1e-9, "rank": 2,
                "expression_status": "significant_down",
            },
        ]

    def test_direction_both_accepted(self):
        """direction='both' must NOT raise; passes validation."""
        import multiomics_explorer.api.functions as api
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            self._organism_result(),
            self._global_summary(),
            self._experiment_summary(),
            self._diagnostics_summary(),
            self._detail_rows(),
        ]
        # Should not raise on 'both'
        result = api.differential_expression_by_gene(
            organism="MED4", direction="both", conn=mock_conn,
        )
        assert result["total_matching"] == 6

    def test_direction_both_returns_both_statuses(self):
        """direction='both' returns both up + down rows."""
        import multiomics_explorer.api.functions as api
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            self._organism_result(),
            self._global_summary(),
            self._experiment_summary(),
            self._diagnostics_summary(),
            self._detail_rows(),
        ]
        result = api.differential_expression_by_gene(
            organism="MED4", direction="both", conn=mock_conn,
        )
        statuses = {r["expression_status"] for r in result["results"]}
        assert "significant_up" in statuses
        assert "significant_down" in statuses

    def test_invalid_direction_still_raises(self):
        """Invalid direction values still raise even with 'both' support."""
        import multiomics_explorer.api.functions as api
        mock_conn = MagicMock()
        with pytest.raises(ValueError, match="Invalid direction"):
            api.differential_expression_by_gene(
                organism="MED4", direction="sideways", conn=mock_conn,
            )


# ---------------------------------------------------------------------------
# list_metabolite_assays — Phase 5 (RED stage; impl lands in GREEN)
# Plan: docs/superpowers/plans/2026-05-06-list-metabolite-assays.md
# Task 7
# ---------------------------------------------------------------------------


class TestListMetaboliteAssays:
    """API-layer tests — mocked GraphConnection."""

    def _mock_conn(self, summary_rows, detail_rows):
        from unittest.mock import MagicMock
        conn = MagicMock()
        # 2-query pattern: summary first, detail second
        conn.execute_query.side_effect = [summary_rows, detail_rows]
        return conn

    def test_returns_envelope_keys(self):
        from multiomics_explorer.api.functions import list_metabolite_assays
        summary_row = [{
            "total_entries": 10, "total_matching": 10,
            "metabolite_count_total": 768,
            "by_organism": [], "by_value_kind": [], "by_compartment": [],
            "top_metric_types": [], "by_treatment_type": [],
            "by_background_factors": [], "by_growth_phase": [],
            "by_detection_status": [],
        }]
        result = list_metabolite_assays(conn=self._mock_conn(summary_row, []))
        for k in [
            "total_entries", "total_matching", "metabolite_count_total",
            "by_organism", "by_value_kind", "by_compartment", "top_metric_types",
            "by_treatment_type", "by_background_factors", "by_growth_phase",
            "by_detection_status", "returned", "truncated", "offset",
            "not_found", "results",
        ]:
            assert k in result, f"missing envelope key: {k}"

    def test_summary_true_skips_detail_query(self):
        """summary=True forces limit=0; detail builder isn't executed."""
        from multiomics_explorer.api.functions import list_metabolite_assays
        from unittest.mock import MagicMock
        summary_row = [{
            "total_entries": 10, "total_matching": 10,
            "metabolite_count_total": 0,
            "by_organism": [], "by_value_kind": [], "by_compartment": [],
            "top_metric_types": [], "by_treatment_type": [],
            "by_background_factors": [], "by_growth_phase": [],
            "by_detection_status": [],
        }]
        conn = MagicMock()
        conn.execute_query.return_value = summary_row
        result = list_metabolite_assays(summary=True, conn=conn)
        assert conn.execute_query.call_count == 1
        assert result["results"] == []
        assert result["truncated"] is True

    def test_truncated_when_total_matching_exceeds_limit(self):
        from multiomics_explorer.api.functions import list_metabolite_assays
        summary_row = [{
            "total_entries": 10, "total_matching": 10,
            "metabolite_count_total": 768,
            "by_organism": [], "by_value_kind": [], "by_compartment": [],
            "top_metric_types": [], "by_treatment_type": [],
            "by_background_factors": [], "by_growth_phase": [],
            "by_detection_status": [],
        }]
        detail_rows = [{"assay_id": f"a{i}"} for i in range(2)]
        result = list_metabolite_assays(
            limit=2, conn=self._mock_conn(summary_row, detail_rows))
        assert result["returned"] == 2
        assert result["truncated"] is True

    def test_search_text_empty_raises(self):
        from multiomics_explorer.api.functions import list_metabolite_assays
        from unittest.mock import MagicMock
        conn = MagicMock()
        try:
            list_metabolite_assays(search_text="", conn=conn)
        except ValueError:
            return
        raise AssertionError("expected ValueError on empty search_text")

    def test_lucene_retry_on_parse_error(self):
        """Lucene parse error → escape + retry once."""
        from multiomics_explorer.api.functions import list_metabolite_assays
        from unittest.mock import MagicMock
        from neo4j.exceptions import ClientError as Neo4jClientError
        summary_row = [{
            "total_entries": 10, "total_matching": 0,
            "metabolite_count_total": 0,
            "by_organism": [], "by_value_kind": [], "by_compartment": [],
            "top_metric_types": [], "by_treatment_type": [],
            "by_background_factors": [], "by_growth_phase": [],
            "by_detection_status": [],
            "score_max": None, "score_median": None,
        }]
        conn = MagicMock()
        # First call (summary) raises Lucene parse error; retry succeeds
        conn.execute_query.side_effect = [
            Neo4jClientError("Failed to parse query: chitosan AND"),
            summary_row,
            [],
        ]
        result = list_metabolite_assays(search_text="chitosan AND", conn=conn)
        assert result["total_matching"] == 0

    def test_lucene_parse_error_survives_retry_raises_readable_valueerror(self):
        """When the escaped retry also fails with a Lucene parse error, the
        raw ClientError must not leak (llm-review 2b.3)."""
        from multiomics_explorer.api.functions import list_metabolite_assays
        from unittest.mock import MagicMock
        from neo4j.exceptions import ClientError as Neo4jClientError
        conn = MagicMock()
        conn.execute_query.side_effect = [
            Neo4jClientError("Invalid input ParseException"),
            Neo4jClientError("Invalid input ParseException"),
        ]
        with pytest.raises(ValueError, match=r"is not valid Lucene syntax"):
            list_metabolite_assays(search_text="chitosan AND", conn=conn)

    def test_not_found_structured_for_batch_inputs(self):
        """`not_found` carries per-batch buckets (parent §11 Conv B).

        After the post-review fix to use existence-check Cyphers per batch
        input (mirroring list_metabolites' MetNotFound precedent), the api
        function emits one additional `conn.execute_query` call per non-empty
        batch. This test passes only `assay_ids`, so the mock provides:
          [0] summary, [1] detail, [2] existence-check on assay_ids.
        """
        from unittest.mock import MagicMock
        from multiomics_explorer.api.functions import list_metabolite_assays
        summary_row = [{
            "total_entries": 10, "total_matching": 1,
            "metabolite_count_total": 92,
            "by_organism": [], "by_value_kind": [], "by_compartment": [],
            "top_metric_types": [], "by_treatment_type": [],
            "by_background_factors": [], "by_growth_phase": [],
            "by_detection_status": [],
        }]
        valid_assay_id = "metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration"
        detail_rows = [{"assay_id": valid_assay_id}]
        existence_check_response = [{"found": [valid_assay_id]}]
        conn = MagicMock()
        conn.execute_query.side_effect = [
            summary_row, detail_rows, existence_check_response,
        ]
        result = list_metabolite_assays(
            assay_ids=[valid_assay_id, "non_existent_assay_id"],
            conn=conn,
        )
        assert "not_found" in result
        assert "assay_ids" in result["not_found"]
        assert "non_existent_assay_id" in result["not_found"]["assay_ids"]
        # Valid IDs are NOT in not_found (true existence check, not the
        # broken "if total_matching == 0 then mark all unknown" heuristic).
        assert valid_assay_id not in result["not_found"]["assay_ids"]
        assert "metabolite_ids" in result["not_found"]
        assert "experiment_ids" in result["not_found"]
        assert "publication_doi" in result["not_found"]

    def test_offset_echoed(self):
        from multiomics_explorer.api.functions import list_metabolite_assays
        summary_row = [{
            "total_entries": 10, "total_matching": 10,
            "metabolite_count_total": 768,
            "by_organism": [], "by_value_kind": [], "by_compartment": [],
            "top_metric_types": [], "by_treatment_type": [],
            "by_background_factors": [], "by_growth_phase": [],
            "by_detection_status": [],
        }]
        result = list_metabolite_assays(
            offset=5, conn=self._mock_conn(summary_row, []))
        assert result["offset"] == 5

    def test_importable_from_package(self):
        """Re-exported from api/__init__.py and multiomics_explorer/__init__.py."""
        from multiomics_explorer.api import list_metabolite_assays as _api_export
        from multiomics_explorer import list_metabolite_assays as _root_export
        assert _api_export is _root_export

    def test_organism_no_assays_warns(self):
        """llm-review 2b.3 Task 5: organism resolves genomically but has
        zero MetaboliteAssay nodes -> distinct warning naming which
        organisms DO have assays."""
        from unittest.mock import MagicMock
        from multiomics_explorer.api.functions import list_metabolite_assays
        summary_row = [{
            "total_entries": 10, "total_matching": 0,
            "metabolite_count_total": 0,
            "by_organism": [], "by_value_kind": [], "by_compartment": [],
            "top_metric_types": [], "by_treatment_type": [],
            "by_background_factors": [], "by_growth_phase": [],
            "by_detection_status": [],
        }]
        conn = MagicMock()
        conn.execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],  # organism resolve
            [{"has_assays": False}],                     # targeted existence
            [{"orgs": ["Prochlorococcus MED4", "Alteromonas macleodii"]}],
            summary_row,
            [],  # detail
        ]
        result = list_metabolite_assays(organism="MED4", conn=conn)
        assert any(
            "MED4" in w and "no metabolomics assays" in w
            and "Alteromonas macleodii" in w
            for w in result["warnings"]
        ), result["warnings"]

    def test_organism_with_assays_no_warning(self):
        from unittest.mock import MagicMock
        from multiomics_explorer.api.functions import list_metabolite_assays
        summary_row = [{
            "total_entries": 10, "total_matching": 3,
            "metabolite_count_total": 3,
            "by_organism": [], "by_value_kind": [], "by_compartment": [],
            "top_metric_types": [], "by_treatment_type": [],
            "by_background_factors": [], "by_growth_phase": [],
            "by_detection_status": [],
        }]
        conn = MagicMock()
        conn.execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],
            [{"has_assays": True}],
            summary_row,
            [],
        ]
        result = list_metabolite_assays(organism="MED4", conn=conn)
        assert not any("no metabolomics assays" in w for w in result["warnings"])

    def test_organism_no_match_at_all_warns_unmatched(self):
        from unittest.mock import MagicMock
        from multiomics_explorer.api.functions import list_metabolite_assays
        summary_row = [{
            "total_entries": 10, "total_matching": 0,
            "metabolite_count_total": 0,
            "by_organism": [], "by_value_kind": [], "by_compartment": [],
            "top_metric_types": [], "by_treatment_type": [],
            "by_background_factors": [], "by_growth_phase": [],
            "by_detection_status": [],
        }]
        conn = MagicMock()
        conn.execute_query.side_effect = [
            [{"organisms": []}],  # organism resolve: no match at all
            summary_row,
            [],
        ]
        result = list_metabolite_assays(organism="Bogus organism", conn=conn)
        assert any(
            "matched no organism" in w for w in result["warnings"]
        ), result["warnings"]
        # No metabolomics-layer query fired since organism never resolved.
        assert conn.execute_query.call_count == 3


# ---------------------------------------------------------------------------
# Phase 5 metabolites-by-assay slice — 3 tools
# Tool 1: metabolites_by_quantifies_assay (numeric drill-down)
# Tool 2: metabolites_by_flags_assay (boolean drill-down)
# Tool 3: assays_by_metabolite (polymorphic reverse-lookup)
# ---------------------------------------------------------------------------
class TestMetabolitesByQuantifiesAssay:
    """Unit tests for api.metabolites_by_quantifies_assay (slice spec §4)."""

    @staticmethod
    def _diag_rankable(assay_ids=("a1",)):
        """Diagnostics rows where every assay is rankable."""
        return [
            {
                "assay_id": aid,
                "name": f"Assay {aid}",
                "value_kind": "numeric",
                "rankable": True,
                "organism_name": "Prochlorococcus MIT9313",
                "compartment": "whole_cell",
                "value_min": 0.0,
                "value_q1": 0.001,
                "value_median": 0.005,
                "value_q3": 0.05,
                "value_max": 0.5,
            }
            for aid in assay_ids
        ]

    @staticmethod
    def _diag_non_rankable(assay_ids=("a1",)):
        """Diagnostics rows where every assay is non-rankable."""
        return [
            {
                "assay_id": aid,
                "name": f"Assay {aid}",
                "value_kind": "numeric",
                "rankable": False,
                "organism_name": "Prochlorococcus MIT9313",
                "compartment": "whole_cell",
                "value_min": 0.0,
                "value_q1": 0.0,
                "value_median": 0.0,
                "value_q3": 0.0,
                "value_max": 1.0,
            }
            for aid in assay_ids
        ]

    @staticmethod
    def _diag_mixed():
        return [
            {
                "assay_id": "a_rank",
                "name": "Rankable assay",
                "value_kind": "numeric",
                "rankable": True,
                "organism_name": "Prochlorococcus MIT9313",
                "compartment": "whole_cell",
                "value_min": 0.0, "value_q1": 0.001, "value_median": 0.005,
                "value_q3": 0.05, "value_max": 0.5,
            },
            {
                "assay_id": "a_norank",
                "name": "Non-rankable assay",
                "value_kind": "numeric",
                "rankable": False,
                "organism_name": "Prochlorococcus MIT9313",
                "compartment": "whole_cell",
                "value_min": 0.0, "value_q1": 0.0, "value_median": 0.0,
                "value_q3": 0.0, "value_max": 1.0,
            },
        ]

    @staticmethod
    def _summary_row():
        return [{
            "total_matching": 64,
            "by_detection_status": [{"item": "not_detected", "count": 48},
                                    {"item": "detected", "count": 16}],
            "by_metric_bucket": [{"item": "low", "count": 32}],
            "by_assay": [{"item": "a1", "count": 64}],
            "by_compartment": [{"item": "whole_cell", "count": 64}],
            "by_organism": [{"item": "Prochlorococcus MIT9313", "count": 64}],
            "filtered_value_min": 0.0,
            "filtered_value_max": 0.5,
        }]

    def test_empty_assay_ids_raises(self):
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        with pytest.raises(ValueError, match="assay_ids"):
            metabolites_by_quantifies_assay(assay_ids=[], conn=MagicMock())

    def test_invalid_metric_bucket_raises(self):
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        with pytest.raises(ValueError, match="metric_bucket"):
            metabolites_by_quantifies_assay(
                assay_ids=["a1"], metric_bucket=["INVALID"], conn=MagicMock())

    def test_invalid_detection_status_raises(self):
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        with pytest.raises(ValueError, match="detection_status"):
            metabolites_by_quantifies_assay(
                assay_ids=["a1"], detection_status=["INVALID"], conn=MagicMock())

    def test_all_non_rankable_raises_when_rankable_filter_set(self):
        # All-non-rankable input + rankable-gated filter → ValueError.
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        mock_conn = MagicMock()
        mock_conn.execute_query.return_value = self._diag_non_rankable(("a1",))
        with pytest.raises(ValueError, match="rankable"):
            metabolites_by_quantifies_assay(
                assay_ids=["a1"], metric_bucket=["top_decile"], conn=mock_conn)

    def test_mixed_rankable_soft_excludes(self):
        # Mixed input: some rankable, some not. Expect excluded surfaced.
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            self._diag_mixed(),
            self._summary_row(),
            [],
        ]
        data = metabolites_by_quantifies_assay(
            assay_ids=["a_rank", "a_norank"],
            metric_bucket=["top_decile"],
            conn=mock_conn,
        )
        assert "a_norank" in data["excluded_assays"]
        assert "a_rank" not in data["excluded_assays"]
        assert data["warnings"]

    def test_summary_skips_detail_query(self):
        # summary=True means only diagnostics + summary builders run.
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            self._diag_rankable(("a1",)),
            self._summary_row(),
        ]
        data = metabolites_by_quantifies_assay(
            assay_ids=["a1"], summary=True, conn=mock_conn,
        )
        # diag + summary only; detail builder NOT invoked
        assert mock_conn.execute_query.call_count == 2
        assert data["results"] == []

    def test_not_detected_rows_have_null_rank_fields(self):
        # Regression: a tested-absent row can still carry a stored
        # metric_bucket / metric_percentile / rank_by_metric (raw-zero
        # coincidence — many edges are zero) — nulled for display so a
        # rank-gated caller can't mistake it for a real ranking signal.
        # Mirrors the live repro (MIT0801 extracellular glutamate:
        # value=0, detection_status='not_detected', metric_bucket=
        # 'top_quartile', metric_percentile≈78.02).
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        mock_conn = MagicMock()
        detail_rows = [{
            "metabolite_id": "kegg.compound:C00025",
            "name": "L-Glutamate",
            "kegg_compound_id": "C00025",
            "value": 0,
            "value_sd": 0,
            "n_replicates": 1,
            "n_non_zero": 0,
            "metric_type": "extracellular_concentration",
            "metric_bucket": "top_quartile",
            "metric_percentile": 78.02197802197803,
            "rank_by_metric": 21,
            "detection_status": "not_detected",
            "timepoint": None,
            "timepoint_hours": None,
            "timepoint_order": None,
            "growth_phase": None,
            "condition_label": "replete_light_10",
            "assay_id": "a1",
            "organism_name": "Prochlorococcus MIT0801",
            "compartment": "extracellular",
        }]
        mock_conn.execute_query.side_effect = [
            self._diag_rankable(("a1",)),
            self._summary_row(),
            detail_rows,
        ]
        data = metabolites_by_quantifies_assay(assay_ids=["a1"], conn=mock_conn)
        row = data["results"][0]
        assert row["metric_bucket"] is None
        assert row["metric_percentile"] is None
        assert row["rank_by_metric"] is None
        # KG-stored value fields untouched.
        assert row["value"] == 0
        assert row["detection_status"] == "not_detected"

    def test_detected_rows_keep_rank_fields(self):
        # Sanity: the nulling only targets not_detected rows.
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        mock_conn = MagicMock()
        detail_rows = [{
            "metabolite_id": "kegg.compound:C00085",
            "value": 0.4465,
            "metric_bucket": "top_decile",
            "metric_percentile": 100.0,
            "rank_by_metric": 1,
            "detection_status": "detected",
        }]
        mock_conn.execute_query.side_effect = [
            self._diag_rankable(("a1",)),
            self._summary_row(),
            detail_rows,
        ]
        data = metabolites_by_quantifies_assay(assay_ids=["a1"], conn=mock_conn)
        row = data["results"][0]
        assert row["metric_bucket"] == "top_decile"
        assert row["metric_percentile"] == 100.0
        assert row["rank_by_metric"] == 1

    def test_boolean_assay_id_reported_as_wrong_kind_not_not_found(self):
        """llm-review 2b.3 Task 5: a boolean assay_id passed to this
        numeric-only tool is genuinely found (excluded from
        not_found.assay_ids) but reported via a sibling-tool warning."""
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        mock_conn = MagicMock()
        diag_rows = [
            {
                "assay_id": "bool_a1",
                "name": "Boolean assay",
                "value_kind": "boolean",
                "rankable": False,
                "organism_name": "Prochlorococcus MIT9313",
                "compartment": "whole_cell",
                "value_min": None, "value_q1": None, "value_median": None,
                "value_q3": None, "value_max": None,
            },
        ]
        mock_conn.execute_query.side_effect = [diag_rows]
        data = metabolites_by_quantifies_assay(assay_ids=["bool_a1"], conn=mock_conn)
        assert "bool_a1" not in data["not_found"]["assay_ids"]
        assert any(
            "bool_a1 exists as value_kind=boolean" in w
            and "metabolites_by_flags_assay" in w
            for w in data["warnings"]
        ), data["warnings"]
        # Nothing survived the kind partition -> empty result, not a crash.
        assert data["results"] == []
        assert data["total_matching"] == 0

    def test_mixed_kind_assay_ids_partition_correctly(self):
        """One numeric + one boolean id: the numeric one proceeds through
        summary/detail; the boolean one is warned, not not_found."""
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        mock_conn = MagicMock()
        diag_rows = self._diag_rankable(("num_a1",)) + [
            {
                "assay_id": "bool_a1",
                "name": "Boolean assay",
                "value_kind": "boolean",
                "rankable": False,
                "organism_name": "Prochlorococcus MIT9313",
                "compartment": "whole_cell",
                "value_min": None, "value_q1": None, "value_median": None,
                "value_q3": None, "value_max": None,
            },
        ]
        summary = [{
            "total_matching": 3,
            "by_detection_status": [{"item": "detected", "count": 3}],
            "by_metric_bucket": [],
            "by_assay": [{"item": "num_a1", "count": 3}],
            "by_compartment": [{"item": "whole_cell", "count": 3}],
            "by_organism": [{"item": "Prochlorococcus MIT9313", "count": 3}],
            "filtered_value_min": 0.0,
            "filtered_value_max": 0.5,
        }]
        mock_conn.execute_query.side_effect = [diag_rows, summary]
        data = metabolites_by_quantifies_assay(
            assay_ids=["num_a1", "bool_a1"], summary=True, conn=mock_conn)
        assert "bool_a1" not in data["not_found"]["assay_ids"]
        assert "num_a1" not in data["not_found"]["assay_ids"]
        assert any("bool_a1 exists as value_kind=boolean" in w
                   for w in data["warnings"])
        assert data["total_matching"] == 3


class TestMetabolitesByFlagsAssay:
    """Unit tests for api.metabolites_by_flags_assay (slice spec §5)."""

    def test_empty_assay_ids_raises(self):
        from multiomics_explorer.api.functions import metabolites_by_flags_assay
        with pytest.raises(ValueError, match="assay_ids"):
            metabolites_by_flags_assay(assay_ids=[], conn=MagicMock())

    def test_flag_value_bool_to_string_coercion(self):
        # D4: bool flag_value → string 'detected'/'not_detected' for Cypher param.
        captured: list[dict] = []

        class StubConn:
            def execute_query(self, cypher, **params):
                captured.append(dict(params))
                if "a.id AS assay_id" in cypher:
                    # Q1: kind-agnostic existence + value_kind probe.
                    return [{"assay_id": "a1", "value_kind": "boolean"}]
                # Q2: summary envelope so api/ continues.
                return [{
                    "total_matching": 0,
                    "by_value": [],
                    "by_assay": [],
                    "by_compartment": [],
                    "by_organism": [],
                }]

        from multiomics_explorer.api.functions import metabolites_by_flags_assay
        metabolites_by_flags_assay(
            assay_ids=["a1"], flag_value=True, summary=True, conn=StubConn(),
        )
        # At least one query carried flag_value="detected"
        coerced_seen = [p for p in captured if p.get("flag_value") == "detected"]
        assert coerced_seen, (
            f"Expected flag_value='detected' string param, got: {captured}"
        )

    def test_no_rankable_diagnostics(self):
        # Boolean tool has no rankable-gate diagnostics; the dispatch is
        # three queries (kind-agnostic existence probe, summary, detail),
        # not four (llm-review 2b.3 Task 5 added the existence probe).
        from multiomics_explorer.api.functions import metabolites_by_flags_assay
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            [{"assay_id": "a1", "value_kind": "boolean"}],
            [{
                "total_matching": 0,
                "by_value": [],
                "by_assay": [],
                "by_compartment": [],
                "by_organism": [],
            }],
            [],
        ]
        metabolites_by_flags_assay(
            assay_ids=["a1"], conn=mock_conn,
        )
        # Three queries: kind probe + summary + detail.
        assert mock_conn.execute_query.call_count == 3

    def test_unknown_assay_id_in_not_found(self):
        """llm-review 2b.3 Task 5: not_found.assay_ids is now a real
        existence check, not always []."""
        from multiomics_explorer.api.functions import metabolites_by_flags_assay
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            [],  # kind probe: nothing found
            [{
                "total_matching": 0,
                "by_value": [],
                "by_assay": [],
                "by_compartment": [],
                "by_organism": [],
            }],
            [],
        ]
        data = metabolites_by_flags_assay(assay_ids=["nope"], conn=mock_conn)
        assert data["not_found"]["assay_ids"] == ["nope"]
        assert data["warnings"] == []

    def test_numeric_assay_id_reported_as_wrong_kind_not_not_found(self):
        """A numeric assay_id passed to this boolean-only tool is
        genuinely found (excluded from not_found.assay_ids) but reported
        via a sibling-tool warning."""
        from multiomics_explorer.api.functions import metabolites_by_flags_assay
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            [{"assay_id": "num_a1", "value_kind": "numeric"}],
            [{
                "total_matching": 0,
                "by_value": [],
                "by_assay": [],
                "by_compartment": [],
                "by_organism": [],
            }],
            [],
        ]
        data = metabolites_by_flags_assay(assay_ids=["num_a1"], conn=mock_conn)
        assert "num_a1" not in data["not_found"]["assay_ids"]
        assert any(
            "num_a1 exists as value_kind=numeric" in w
            and "metabolites_by_quantifies_assay" in w
            for w in data["warnings"]
        ), data["warnings"]


class TestAssaysByMetabolite:
    """Unit tests for api.assays_by_metabolite (slice spec §6, polymorphic reverse-lookup)."""

    def test_empty_metabolite_ids_raises(self):
        from multiomics_explorer.api.functions import assays_by_metabolite
        with pytest.raises(ValueError, match="metabolite_ids"):
            assays_by_metabolite(metabolite_ids=[], conn=MagicMock())

    def test_invalid_evidence_kind_raises(self):
        from multiomics_explorer.api.functions import assays_by_metabolite
        with pytest.raises(ValueError, match="evidence_kind"):
            assays_by_metabolite(
                metabolite_ids=["m1"], evidence_kind="INVALID", conn=MagicMock())

    def test_not_found_flat_list(self):
        # Single-batch input → flat list[str] (parent §13.6).
        # Stubbed: probe returns empty (metabolite ID absent from KG).
        from multiomics_explorer.api.functions import assays_by_metabolite
        mock_conn = MagicMock()
        # 3 queries: existence-probe, summary, detail
        # existence-probe returns no rows → all input IDs are not_found
        empty_summary = [{
            "total_matching": 0,
            "by_evidence_kind": [],
            "by_organism": [],
            "by_compartment": [],
            "by_assay": [],
            "by_detection_status": [],
            "by_flag_value": [],
            "metabolites_matched": 0,
            "matched_metabolite_ids": [],
        }]
        mock_conn.execute_query.side_effect = [
            [],            # existence probe — input ID absent
            empty_summary, # summary
            [],            # detail
        ]
        data = assays_by_metabolite(
            metabolite_ids=["kegg.compound:C99999"], conn=mock_conn,
        )
        # Flat list[str] per parent §13.6 (single batch input).
        assert isinstance(data["not_found"], list)
        assert "kegg.compound:C99999" in data["not_found"]

    def test_metabolites_with_evidence_partition(self):
        # 2 metabolites in input, 1 has rows, 1 has none.
        from multiomics_explorer.api.functions import assays_by_metabolite
        mock_conn = MagicMock()
        present_id = "kegg.compound:C00074"
        absent_id = "kegg.compound:C00031"
        existence_rows = [
            {"metabolite_id": present_id},
            {"metabolite_id": absent_id},
        ]
        summary_rows = [{
            "total_matching": 18,
            "by_evidence_kind": [{"item": "quantifies", "count": 18}],
            "by_organism": [],
            "by_compartment": [],
            "by_assay": [],
            "by_detection_status": [],
            "by_flag_value": [],
            "metabolites_matched": 1,
            "matched_metabolite_ids": [present_id],
        }]
        detail_rows = [
            {
                "metabolite_id": present_id,
                "metabolite_name": "PEP",
                "assay_id": "a1",
                "evidence_kind": "quantifies",
                "value": 0.05,
            },
        ]
        mock_conn.execute_query.side_effect = [
            existence_rows,
            summary_rows,
            detail_rows,
        ]
        data = assays_by_metabolite(
            metabolite_ids=[present_id, absent_id], conn=mock_conn,
        )
        assert present_id in data["metabolites_with_evidence"]
        assert absent_id in data["metabolites_without_evidence"]
        assert present_id not in data["metabolites_without_evidence"]

    def test_summary_true_not_matched_uses_full_match_set(self):
        # Regression for the bug: summary=True skips the detail query
        # (results=[]), so metabolites_with_evidence / not_matched must be
        # derived from the summary's matched_metabolite_ids, never from the
        # (empty) `results` page. Mirrors the live repro:
        # assays_by_metabolite(['C00025'], summary=True) previously reported
        # a matched metabolite as not_matched.
        from multiomics_explorer.api.functions import assays_by_metabolite
        mock_conn = MagicMock()
        present_id = "kegg.compound:C00025"
        existence_rows = [{"metabolite_id": present_id}]
        summary_rows = [{
            "total_matching": 14,
            "by_evidence_kind": [{"item": "quantifies", "count": 12},
                                 {"item": "flags", "count": 2}],
            "by_organism": [],
            "by_compartment": [],
            "by_assay": [],
            "by_detection_status": [],
            "by_flag_value": [],
            "metabolites_matched": 1,
            "matched_metabolite_ids": [present_id],
        }]
        mock_conn.execute_query.side_effect = [
            existence_rows,
            summary_rows,
            # detail query must NOT run when summary=True; no third item
            # needed, but pytest-regressions-style side_effect lists tolerate
            # unused extras — omit it to also assert call_count below.
        ]
        data = assays_by_metabolite(
            metabolite_ids=[present_id], summary=True, conn=mock_conn,
        )
        assert data["results"] == []
        assert data["not_matched"] == []
        assert data["metabolites_without_evidence"] == []
        assert data["metabolites_with_evidence"] == [present_id]
        assert mock_conn.execute_query.call_count == 2

    def test_not_detected_rows_have_null_rank_fields(self):
        # Regression for the bug: a tested-absent row can still carry a
        # stored metric_bucket/metric_percentile from raw-zero coincidence
        # (many edges are zero) — those must be nulled for display so a
        # caller can't mistake "the KG ranked this row" for a real signal.
        from multiomics_explorer.api.functions import assays_by_metabolite
        mock_conn = MagicMock()
        mid = "kegg.compound:C00025"
        existence_rows = [{"metabolite_id": mid}]
        summary_rows = [{
            "total_matching": 1,
            "by_evidence_kind": [{"item": "quantifies", "count": 1}],
            "by_organism": [],
            "by_compartment": [],
            "by_assay": [],
            "by_detection_status": [],
            "by_flag_value": [],
            "metabolites_matched": 1,
            "matched_metabolite_ids": [mid],
        }]
        detail_rows = [
            {
                "metabolite_id": mid,
                "metabolite_name": "L-Glutamate",
                "assay_id": "a1",
                "evidence_kind": "quantifies",
                "value": 0,
                "metric_bucket": "top_quartile",
                "metric_percentile": 78.02,
                "rank_by_metric": None,
                "detection_status": "not_detected",
            },
        ]
        mock_conn.execute_query.side_effect = [
            existence_rows, summary_rows, detail_rows,
        ]
        data = assays_by_metabolite(metabolite_ids=[mid], conn=mock_conn)
        row = data["results"][0]
        assert row["metric_bucket"] is None
        assert row["metric_percentile"] is None
        assert row["value"] == 0
        assert row["detection_status"] == "not_detected"

    def test_organism_no_assays_warns(self):
        """llm-review 2b.3 Task 5: same organism-layer warning as
        list_metabolite_assays (assays_by_metabolite had no organism
        warning at all before this)."""
        from multiomics_explorer.api.functions import assays_by_metabolite
        mock_conn = MagicMock()
        mid = "kegg.compound:C00025"
        empty_summary = [{
            "total_matching": 0,
            "by_evidence_kind": [],
            "by_organism": [],
            "by_compartment": [],
            "by_assay": [],
            "by_detection_status": [],
            "by_flag_value": [],
            "metabolites_matched": 0,
            "matched_metabolite_ids": [],
        }]
        mock_conn.execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],   # organism resolve
            [{"has_assays": False}],                      # targeted existence
            [{"orgs": ["Prochlorococcus MED4"]}],          # full org list
            [{"metabolite_id": mid}],                      # existence probe
            empty_summary,
            [],
        ]
        data = assays_by_metabolite(
            metabolite_ids=[mid], organism="MIT9313", conn=mock_conn)
        assert any(
            "MIT9313" in w and "no metabolomics assays" in w
            for w in data["warnings"]
        ), data["warnings"]


# ---------------------------------------------------------------------------
# gene_aa_sequence
# ---------------------------------------------------------------------------
class TestGeneAaSequence:
    """gene_aa_sequence orchestration (existence + summary + detail)."""

    _ENVELOPE_KEYS = {
        "total_matching", "returned", "truncated", "by_organism",
        "sequence_length_stats", "not_found", "not_matched", "warnings",
        "fasta", "results",
    }

    def _exist(self, found, not_found=()):
        rows = [{"lt": lt, "found": True} for lt in found]
        rows += [{"lt": lt, "found": False} for lt in not_found]
        return rows

    def _summary_row(self, *, matched_tags, by_organism, total_matching,
                     len_min=178, len_max=487, len_mean=332.5,
                     len_pcts=(178.0, 178.0, 487.0)):
        return [{
            "total_matching": total_matching,
            "matched_tags": list(matched_tags),
            "by_organism": by_organism,
            "len_min": len_min,
            "len_max": len_max,
            "len_mean": len_mean,
            "len_pcts": list(len_pcts),
        }]

    def _detail_rows(self):
        return [
            {"locus_tag": "ACZ81_08855", "organism_name": "Alteromonas macleodii HOT1A3",
             "gene_name": None, "product": "hypothetical protein",
             "protein_id": "WP_001", "sequence_length": 178, "sequence": "M" * 178},
            {"locus_tag": "ACZ81_08860", "organism_name": "Alteromonas macleodii HOT1A3",
             "gene_name": "dnaN", "product": "DNA polymerase III subunit beta",
             "protein_id": "WP_002", "sequence_length": 487, "sequence": "M" * 487},
        ]

    def test_returns_dict_with_envelope_keys(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08855", "ACZ81_08860"]),
            self._summary_row(
                matched_tags=["ACZ81_08855", "ACZ81_08860"],
                by_organism=[{"item": "Alteromonas macleodii HOT1A3", "count": 2}],
                total_matching=2,
            ),
            self._detail_rows(),
        ]
        result = api.gene_aa_sequence(
            locus_tags=["ACZ81_08855", "ACZ81_08860"], conn=mock_conn,
        )
        assert isinstance(result, dict)
        assert set(result.keys()) == self._ENVELOPE_KEYS

    def test_total_matching_from_summary(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08855", "ACZ81_08860"]),
            self._summary_row(
                matched_tags=["ACZ81_08855", "ACZ81_08860"],
                by_organism=[{"item": "Alteromonas macleodii HOT1A3", "count": 2}],
                total_matching=2,
            ),
            self._detail_rows(),
        ]
        result = api.gene_aa_sequence(
            locus_tags=["ACZ81_08855", "ACZ81_08860"], conn=mock_conn,
        )
        assert result["total_matching"] == 2
        assert result["returned"] == 2
        assert result["truncated"] is False

    def test_sequence_length_stats_assembled(self, mock_conn):
        """sequence_length_stats built from summary aggregates (no Python recompute)."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08855", "ACZ81_08860"]),
            self._summary_row(
                matched_tags=["ACZ81_08855", "ACZ81_08860"],
                by_organism=[{"item": "Alteromonas macleodii HOT1A3", "count": 2}],
                total_matching=2,
                len_min=178, len_max=487, len_mean=332.5,
                len_pcts=(178.0, 178.0, 487.0),
            ),
            self._detail_rows(),
        ]
        result = api.gene_aa_sequence(
            locus_tags=["ACZ81_08855", "ACZ81_08860"], conn=mock_conn,
        )
        stats = result["sequence_length_stats"]
        assert stats["count"] == 2
        assert stats["min"] == 178
        assert stats["max"] == 487
        assert stats["mean"] == 332.5
        assert stats["q1"] == 178.0
        assert stats["median"] == 178.0
        assert stats["q3"] == 487.0

    def test_zero_match_returns_none_stats(self, mock_conn):
        """All inputs not_found/no-sequence: stats are None, not a crash.

        Guards the zero-match summary row — apoc.agg.percentiles over an empty set
        returns an all-null list, and min/max/avg are null. The envelope must carry
        count=0 + None stats (the MCP SequenceLengthStats fields are nullable).
        """
        mock_conn.execute_query.side_effect = [
            self._exist([], not_found=["NOTAREAL"]),
            self._summary_row(
                matched_tags=[], by_organism=[], total_matching=0,
                len_min=None, len_max=None, len_mean=None,
                len_pcts=(None, None, None, None, None, None),
            ),
            [],  # detail builder runs (limit>0) but matches nothing
            [],  # case-mismatch lookup over not_found
        ]
        result = api.gene_aa_sequence(locus_tags=["NOTAREAL"], conn=mock_conn)
        assert result["total_matching"] == 0
        assert result["not_found"] == ["NOTAREAL"]
        assert result["results"] == []
        assert result["sequence_length_stats"] == {
            "count": 0, "min": None, "q1": None, "median": None,
            "q3": None, "max": None, "mean": None,
        }

    def test_by_organism_renamed(self, mock_conn):
        """by_organism item/count renamed to organism_name/count."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08855", "ACZ81_08860"]),
            self._summary_row(
                matched_tags=["ACZ81_08855", "ACZ81_08860"],
                by_organism=[{"item": "Alteromonas macleodii HOT1A3", "count": 2}],
                total_matching=2,
            ),
            self._detail_rows(),
        ]
        result = api.gene_aa_sequence(
            locus_tags=["ACZ81_08855", "ACZ81_08860"], conn=mock_conn,
        )
        assert result["by_organism"] == [
            {"organism_name": "Alteromonas macleodii HOT1A3", "count": 2},
        ]

    def test_not_found_populated(self, mock_conn):
        """Locus tag absent from KG → not_found."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08860"], not_found=["NOTAREAL"]),
            self._summary_row(
                matched_tags=["ACZ81_08860"],
                by_organism=[{"item": "Alteromonas macleodii HOT1A3", "count": 1}],
                total_matching=1,
            ),
            [self._detail_rows()[1]],
            [],  # case-mismatch lookup over not_found
        ]
        result = api.gene_aa_sequence(
            locus_tags=["ACZ81_08860", "NOTAREAL"], conn=mock_conn,
        )
        assert result["not_found"] == ["NOTAREAL"]

    def test_not_matched_derived_from_found_minus_matched(self, mock_conn):
        """Gene exists but sequence null → not_matched (found_tags − matched_tags)."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08860", "SYNW1755"], not_found=["NOTAREAL"]),
            self._summary_row(
                matched_tags=["ACZ81_08860"],
                by_organism=[{"item": "Alteromonas macleodii HOT1A3", "count": 1}],
                total_matching=1,
            ),
            [self._detail_rows()[1]],
            [],  # case-mismatch lookup over not_found
        ]
        result = api.gene_aa_sequence(
            locus_tags=["ACZ81_08860", "SYNW1755", "NOTAREAL"], conn=mock_conn,
        )
        assert result["not_found"] == ["NOTAREAL"]
        assert result["not_matched"] == ["SYNW1755"]
        assert "SYNW1755" not in result["not_found"]
        assert "NOTAREAL" not in result["not_matched"]

    def test_fasta_false_rows_carry_sequence(self, mock_conn):
        """fasta=False → rows carry sequence; envelope fasta is empty string."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08855", "ACZ81_08860"]),
            self._summary_row(
                matched_tags=["ACZ81_08855", "ACZ81_08860"],
                by_organism=[{"item": "Alteromonas macleodii HOT1A3", "count": 2}],
                total_matching=2,
            ),
            self._detail_rows(),
        ]
        result = api.gene_aa_sequence(
            locus_tags=["ACZ81_08855", "ACZ81_08860"], fasta=False, conn=mock_conn,
        )
        assert result["fasta"] == ""
        for row in result["results"]:
            assert row["sequence"] is not None
            assert isinstance(row["sequence"], str)

    def test_fasta_true_blob_and_rows_nulled(self, mock_conn):
        """fasta=True → rows have sequence=None and envelope fasta non-empty (no dup)."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08855", "ACZ81_08860"]),
            self._summary_row(
                matched_tags=["ACZ81_08855", "ACZ81_08860"],
                by_organism=[{"item": "Alteromonas macleodii HOT1A3", "count": 2}],
                total_matching=2,
            ),
            self._detail_rows(),
        ]
        result = api.gene_aa_sequence(
            locus_tags=["ACZ81_08855", "ACZ81_08860"], fasta=True, conn=mock_conn,
        )
        assert result["fasta"] != ""
        assert ">ACZ81_08860" in result["fasta"]
        for row in result["results"]:
            assert row["sequence"] is None

    def test_summary_returns_empty_results(self, mock_conn):
        """summary=True → results=[], stats still present."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08855", "ACZ81_08860"]),
            self._summary_row(
                matched_tags=["ACZ81_08855", "ACZ81_08860"],
                by_organism=[{"item": "Alteromonas macleodii HOT1A3", "count": 2}],
                total_matching=2,
            ),
        ]
        result = api.gene_aa_sequence(
            locus_tags=["ACZ81_08855", "ACZ81_08860"], summary=True, conn=mock_conn,
        )
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["total_matching"] == 2
        assert result["sequence_length_stats"]["count"] == 2

    def test_limit_caps_and_truncates(self, mock_conn):
        """limit smaller than total_matching → truncated True."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08855", "ACZ81_08860"]),
            self._summary_row(
                matched_tags=["ACZ81_08855", "ACZ81_08860"],
                by_organism=[{"item": "Alteromonas macleodii HOT1A3", "count": 2}],
                total_matching=2,
            ),
            [self._detail_rows()[0]],
        ]
        result = api.gene_aa_sequence(
            locus_tags=["ACZ81_08855", "ACZ81_08860"], limit=1, conn=mock_conn,
        )
        assert result["total_matching"] == 2
        assert result["returned"] == 1
        assert result["truncated"] is True

    def test_empty_locus_tags_raises(self, mock_conn):
        with pytest.raises(ValueError):
            api.gene_aa_sequence(locus_tags=[], conn=mock_conn)

    def test_importable_from_package(self):
        from multiomics_explorer import gene_aa_sequence
        assert gene_aa_sequence is api.gene_aa_sequence


# ---------------------------------------------------------------------------
# gene_neighbors
# ---------------------------------------------------------------------------
class TestGeneNeighbors:
    """gene_neighbors orchestration (existence + anchor metadata + detail)."""

    _ENVELOPE_KEYS = {
        "total_matching", "returned", "truncated", "anchors", "by_organism",
        "not_found", "not_matched", "warnings", "results",
    }

    def _exist(self, found, not_found=()):
        rows = [{"lt": lt, "found": True} for lt in found]
        rows += [{"lt": lt, "found": False} for lt in not_found]
        return rows

    def _anchor_rows(self, *rows):
        """Each row: (locus_tag, has_coords, strand)."""
        out = []
        for lt, has_coords, strand in rows:
            out.append({
                "anchor_locus_tag": lt,
                "organism_name": "Alteromonas macleodii HOT1A3",
                "contig": "contig1" if has_coords else None,
                "start": 1000 if has_coords else None,
                "end": 1500 if has_coords else None,
                "strand": strand,
                "product": "DNA polymerase III subunit beta",
                "has_coords": has_coords,
            })
        return out

    def _neighbor_row(self, anchor, neighbor, rank_offset, bp_gap, strand, same_strand):
        return {
            "anchor_locus_tag": anchor,
            "neighbor_locus_tag": neighbor,
            "rank_offset": rank_offset,
            "bp_gap": bp_gap,
            "strand": strand,
            "same_strand": same_strand,
            "product": "hypothetical protein",
            "gene_name": None,
            "gene_category": "unknown",
        }

    def test_returns_dict_with_envelope_keys(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08860"]),
            self._anchor_rows(("ACZ81_08860", True, "+")),
            [
                self._neighbor_row("ACZ81_08860", "ACZ81_08850", -1, 10, "+", True),
                self._neighbor_row("ACZ81_08860", "ACZ81_08870", 1, 335, "-", False),
            ],
        ]
        result = api.gene_neighbors(locus_tags=["ACZ81_08860"], conn=mock_conn)
        assert isinstance(result, dict)
        assert set(result.keys()) == self._ENVELOPE_KEYS

    def test_total_matching_from_detail_set(self, mock_conn):
        """total_matching derived from the (bounded) detail set, not the summary query."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08860"]),
            self._anchor_rows(("ACZ81_08860", True, "+")),
            [
                self._neighbor_row("ACZ81_08860", "ACZ81_08850", -1, 10, "+", True),
                self._neighbor_row("ACZ81_08860", "ACZ81_08870", 1, 335, "-", False),
            ],
        ]
        result = api.gene_neighbors(locus_tags=["ACZ81_08860"], conn=mock_conn)
        assert result["total_matching"] == 2
        assert result["returned"] == 2
        assert result["truncated"] is False

    def test_not_found_populated(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08860"], not_found=["NOTAREAL"]),
            self._anchor_rows(("ACZ81_08860", True, "+")),
            [self._neighbor_row("ACZ81_08860", "ACZ81_08850", -1, 10, "+", True)],
            [],  # case-mismatch lookup over not_found
        ]
        result = api.gene_neighbors(
            locus_tags=["ACZ81_08860", "NOTAREAL"], conn=mock_conn,
        )
        assert result["not_found"] == ["NOTAREAL"]

    def test_not_matched_from_missing_coords(self, mock_conn):
        """Anchor exists but lacks coordinates (has_coords=false) → not_matched."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08860", "SYNW1755"], not_found=["NOTAREAL"]),
            self._anchor_rows(
                ("ACZ81_08860", True, "+"),
                ("SYNW1755", False, None),
            ),
            [self._neighbor_row("ACZ81_08860", "ACZ81_08850", -1, 10, "+", True)],
            [],  # case-mismatch lookup over not_found
        ]
        result = api.gene_neighbors(
            locus_tags=["ACZ81_08860", "SYNW1755", "NOTAREAL"], conn=mock_conn,
        )
        assert result["not_found"] == ["NOTAREAL"]
        assert result["not_matched"] == ["SYNW1755"]

    def test_contig_boundary_anchor_present_in_anchors(self, mock_conn):
        """Anchor alone-ish on contig → fewer neighbor rows but still in anchors."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_00010"]),
            self._anchor_rows(("ACZ81_00010", True, "+")),
            [
                self._neighbor_row("ACZ81_00010", "ACZ81_00020", 1, 50, "+", True),
                self._neighbor_row("ACZ81_00010", "ACZ81_00030", 2, 120, "+", True),
            ],
        ]
        result = api.gene_neighbors(locus_tags=["ACZ81_00010"], conn=mock_conn)
        anchor_tags = [a["locus_tag"] for a in result["anchors"]]
        assert "ACZ81_00010" in anchor_tags
        # only downstream offsets present (boundary handled)
        offsets = sorted(r["rank_offset"] for r in result["results"])
        assert offsets == [1, 2]

    def test_same_strand_true_keeps_co_oriented_drops_null(self, mock_conn):
        """same_strand=True keeps co-oriented, drops null-strand neighbors, counts dropped."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08860"]),
            self._anchor_rows(("ACZ81_08860", True, "+")),
            [
                self._neighbor_row("ACZ81_08860", "ACZ81_08850", -1, 10, "+", True),
                self._neighbor_row("ACZ81_08860", "ACZ81_08855", -2, 556, None, None),
                self._neighbor_row("ACZ81_08860", "ACZ81_08870", 1, 335, "-", False),
            ],
        ]
        result = api.gene_neighbors(
            locus_tags=["ACZ81_08860"], same_strand=True, conn=mock_conn,
        )
        kept = {r["neighbor_locus_tag"] for r in result["results"]}
        assert kept == {"ACZ81_08850"}
        assert result["total_matching"] == 1
        anchor = next(a for a in result["anchors"] if a["locus_tag"] == "ACZ81_08860")
        assert anchor["dropped_null_strand"] == 1

    def test_null_strand_anchor_with_same_strand_warns_unfiltered(self, mock_conn):
        """Anchor's own strand null + same_strand set → unfiltered + warning, dropped=0."""
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08865"]),
            self._anchor_rows(("ACZ81_08865", True, None)),
            [
                self._neighbor_row("ACZ81_08865", "ACZ81_08860", -1, 10, "+", None),
                self._neighbor_row("ACZ81_08865", "ACZ81_08870", 1, 335, "-", None),
            ],
        ]
        result = api.gene_neighbors(
            locus_tags=["ACZ81_08865"], same_strand=True, conn=mock_conn,
        )
        # unfiltered: both neighbors kept
        assert result["total_matching"] == 2
        assert len(result["warnings"]) >= 1
        anchor = next(a for a in result["anchors"] if a["locus_tag"] == "ACZ81_08865")
        assert anchor["dropped_null_strand"] == 0

    def test_max_bp_distance_passed_to_builder(self, mock_conn):
        """max_bp_distance forwarded into the detail builder call."""
        with patch(
            "multiomics_explorer.api.functions.build_gene_neighbors",
            wraps=None,
        ) as mock_builder:
            mock_builder.return_value = ("MATCH (a:Gene) RETURN a", {})
            mock_conn.execute_query.side_effect = [
                self._exist(["ACZ81_08860"]),
                self._anchor_rows(("ACZ81_08860", True, "+")),
                [],
            ]
            api.gene_neighbors(
                locus_tags=["ACZ81_08860"], max_bp_distance=400, conn=mock_conn,
            )
        mock_builder.assert_called_once()
        assert mock_builder.call_args.kwargs.get("max_bp_distance") == 400

    def test_summary_returns_empty_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08860"]),
            self._anchor_rows(("ACZ81_08860", True, "+")),
        ]
        result = api.gene_neighbors(
            locus_tags=["ACZ81_08860"], summary=True, conn=mock_conn,
        )
        assert result["results"] == []
        assert result["returned"] == 0

    def test_limit_caps_and_truncates(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._exist(["ACZ81_08860"]),
            self._anchor_rows(("ACZ81_08860", True, "+")),
            [
                self._neighbor_row("ACZ81_08860", "ACZ81_08850", -1, 10, "+", True),
                self._neighbor_row("ACZ81_08860", "ACZ81_08870", 1, 335, "+", True),
            ],
        ]
        result = api.gene_neighbors(
            locus_tags=["ACZ81_08860"], limit=1, conn=mock_conn,
        )
        assert result["total_matching"] == 2
        assert result["returned"] == 1
        assert result["truncated"] is True

    def test_empty_locus_tags_raises(self, mock_conn):
        with pytest.raises(ValueError):
            api.gene_neighbors(locus_tags=[], conn=mock_conn)

    def test_importable_from_package(self):
        from multiomics_explorer import gene_neighbors
        assert gene_neighbors is api.gene_neighbors


# ---------------------------------------------------------------------------
# Edge-prop null stripping — genes_by_ontology and gene_ontology_terms
# ---------------------------------------------------------------------------


class TestGenesByOntologyEdgePropStripping:
    """Strip-non-applicable: a row keeps only the columns its ontology OWNS
    (`ontology_row_columns`), and owned-but-null columns stay — there `null`
    is information. Supersedes the fixed `_EDGE_PROP_COLS` union strip.

    Uses lightweight row-dicts since threading the trust columns through the
    heavy mock-conn machinery would require invasive fixture changes."""

    @staticmethod
    def _owned_universe():
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        from multiomics_explorer.kg.queries_lib import ontology_row_columns
        return {
            col
            for ont in ALL_ONTOLOGIES
            for col in ontology_row_columns(ont, verbose=True)
        }

    def _run_strip(self, rows, ontology, verbose=True):
        """Apply the same strip rule that genes_by_ontology uses."""
        from multiomics_explorer.kg.queries_lib import ontology_row_columns
        owned = set(ontology_row_columns(ontology, verbose=verbose))
        for r in rows:
            for col in self._owned_universe() - owned:
                r.pop(col, None)
        return rows

    def test_non_owner_ontology_strips_all_four_columns(self):
        """A Pfam row owns none of the PSORTb / SignalP native scalars."""
        rows = [{
            "locus_tag": "PMM0001",
            "term_id": "pfam:PF00001",
            "term_name": "7tm_1",
            "level": 3,
            "localization_score": None,
            "signal_peptide_probability": None,
            "signal_peptide_cleavage_site": None,
            "signal_peptide_cleavage_probability": None,
        }]
        result = self._run_strip(rows, ontology="pfam")
        row = result[0]
        assert "localization_score" not in row
        assert "signal_peptide_probability" not in row
        assert "signal_peptide_cleavage_site" not in row
        assert "signal_peptide_cleavage_probability" not in row
        # Non-owned-universe fields are preserved
        assert row["locus_tag"] == "PMM0001"
        assert row["term_id"] == "pfam:PF00001"

    def test_owner_ontology_psortb_keeps_localization_score(self):
        """A subcellular_localization verbose row keeps localization_score
        while the SignalP columns are stripped."""
        rows = [{
            "locus_tag": "PMM0001",
            "term_id": "psortb:cytoplasmic",
            "term_name": "Cytoplasmic",
            "level": 1,
            "localization_score": 9.97,
            "signal_peptide_probability": None,
            "signal_peptide_cleavage_site": None,
            "signal_peptide_cleavage_probability": None,
        }]
        result = self._run_strip(
            rows, ontology="subcellular_localization", verbose=True)
        row = result[0]
        assert row["localization_score"] == 9.97
        assert "signal_peptide_probability" not in row
        assert "signal_peptide_cleavage_site" not in row
        assert "signal_peptide_cleavage_probability" not in row

    def test_psortb_compact_row_sheds_localization_score(self):
        """PSORTb native detail moved compact -> verbose."""
        rows = [{
            "locus_tag": "PMM0001",
            "term_id": "psortb:cytoplasmic",
            "localization_score": 9.97,
        }]
        result = self._run_strip(
            rows, ontology="subcellular_localization", verbose=False)
        assert "localization_score" not in result[0]

    def test_owner_ontology_signalp_keeps_three_columns(self):
        """signal_peptide verbose rows keep all 3 SP cols; localization_score
        is not owned and gets stripped."""
        rows = [{
            "locus_tag": "PMM0002",
            "term_id": "signalp:signal_peptide",
            "term_name": "Signal peptide",
            "level": 1,
            "localization_score": None,
            "signal_peptide_probability": 0.992,
            "signal_peptide_cleavage_site": 22,
            "signal_peptide_cleavage_probability": 0.841,
        }]
        result = self._run_strip(
            rows, ontology="signal_peptide_type", verbose=True)
        row = result[0]
        assert "localization_score" not in row
        assert row["signal_peptide_probability"] == 0.992
        assert row["signal_peptide_cleavage_site"] == 22
        assert row["signal_peptide_cleavage_probability"] == 0.841

    def test_owned_but_null_columns_are_kept(self):
        """A TCDB eggNOG-only edge carries no tier — `null` is information,
        not absence, and the envelope `trust_axes` says what to expect."""
        rows = [{
            "locus_tag": "PMM0392",
            "term_id": "tcdb:3.A.1",
            "evidence": "homology",
            "sources": ["eggnog"],
            "evidence_score": 0.6,
            "tier": None,
            "attachment_depth": "most_specific",
        }]
        result = self._run_strip(rows, ontology="tcdb", verbose=True)
        row = result[0]
        assert "tier" in row
        assert row["tier"] is None
        assert row["evidence"] == "homology"

    def test_edge_prop_cols_constant_is_deleted(self):
        """The fixed union constant is superseded by the registry."""
        assert not hasattr(api, "_EDGE_PROP_COLS")

    def test_rows_without_owned_universe_keys_unaffected(self):
        rows = [{"locus_tag": "PMM0003", "term_id": "go:0006260", "level": 4}]
        result = self._run_strip(rows, ontology="go_bp")
        assert result[0] == {
            "locus_tag": "PMM0003", "term_id": "go:0006260", "level": 4}

    def test_mixed_batch_strips_per_ontology(self):
        """Rows from different ontologies keep their own owned columns."""
        psortb_rows = self._run_strip(
            [{
                "locus_tag": "PMM0001",
                "term_id": "psortb:cytoplasmic",
                "localization_score": 9.97,
                "signal_peptide_probability": None,
            }],
            ontology="subcellular_localization", verbose=True)
        pfam_rows = self._run_strip(
            [{
                "locus_tag": "PMM0002",
                "term_id": "pfam:PF00001",
                "localization_score": None,
                "signal_peptide_probability": None,
            }],
            ontology="pfam", verbose=True)
        assert psortb_rows[0]["localization_score"] == 9.97
        assert "signal_peptide_probability" not in psortb_rows[0]
        assert "localization_score" not in pfam_rows[0]
        assert "signal_peptide_probability" not in pfam_rows[0]


class TestGeneOntologyTermsEdgePropStripping:
    """gene_ontology_terms applies the same strip-non-applicable rule
    per-chunk inside the detail-row loop, keyed on the chunk's ontology."""

    _run_strip = TestGenesByOntologyEdgePropStripping._run_strip
    _owned_universe = staticmethod(
        TestGenesByOntologyEdgePropStripping._owned_universe)

    def test_non_owner_chunk_strips_all_four(self):
        rows = [
            {
                "locus_tag": "PMM0001",
                "term_id": "go:0006260",
                "term_name": "DNA replication",
                "level": 5,
                "localization_score": None,
                "signal_peptide_probability": None,
                "signal_peptide_cleavage_site": None,
                "signal_peptide_cleavage_probability": None,
            },
        ]
        result = self._run_strip(rows, ontology="go_bp", verbose=True)
        row = result[0]
        for col in ("localization_score", "signal_peptide_probability",
                    "signal_peptide_cleavage_site",
                    "signal_peptide_cleavage_probability"):
            assert col not in row
        assert row["locus_tag"] == "PMM0001"
        assert row["term_id"] == "go:0006260"

    def test_owner_psortb_chunk_keeps_score(self):
        rows = [
            {
                "locus_tag": "PMM0001",
                "term_id": "psortb:cytoplasmic",
                "level": 1,
                "localization_score": 9.97,
                "signal_peptide_probability": None,
                "signal_peptide_cleavage_site": None,
                "signal_peptide_cleavage_probability": None,
            },
        ]
        result = self._run_strip(
            rows, ontology="subcellular_localization", verbose=True)
        row = result[0]
        assert row["localization_score"] == 9.97
        assert "signal_peptide_probability" not in row
        assert "signal_peptide_cleavage_site" not in row
        assert "signal_peptide_cleavage_probability" not in row

    def test_owner_signalp_chunk_keeps_three_sp_cols(self):
        rows = [
            {
                "locus_tag": "PMM0002",
                "term_id": "signalp:signal_peptide",
                "level": 1,
                "localization_score": None,
                "signal_peptide_probability": 0.992,
                "signal_peptide_cleavage_site": 22,
                "signal_peptide_cleavage_probability": 0.841,
            },
        ]
        result = self._run_strip(
            rows, ontology="signal_peptide_type", verbose=True)
        row = result[0]
        assert "localization_score" not in row
        assert row["signal_peptide_probability"] == 0.992
        assert row["signal_peptide_cleavage_site"] == 22
        assert row["signal_peptide_cleavage_probability"] == 0.841

    def test_merops_chunk_keeps_call_class_in_compact(self):
        rows = [
            {
                "locus_tag": "MIT1002_03660",
                "term_id": "merops.family:S14",
                "evidence": "signature",
                "call_class": "peptidase",
                "confidence_score": 1.0,
            },
        ]
        result = self._run_strip(rows, ontology="merops", verbose=False)
        row = result[0]
        assert row["call_class"] == "peptidase"
        assert row["evidence"] == "signature"
        # native detail is verbose-only
        assert "confidence_score" not in row

    def test_chunk_without_owned_universe_keys_unaffected(self):
        rows = [{"locus_tag": "PMM0003", "term_id": "go:0006260", "level": 5}]
        result = self._run_strip(rows, ontology="go_bp", verbose=True)
        assert result[0] == {
            "locus_tag": "PMM0003", "term_id": "go:0006260", "level": 5}


# ---------------------------------------------------------------------------
# Outfacing-doc lint gate for api/functions.py docstrings
# ---------------------------------------------------------------------------
# See docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md
# for the 9 style rules. Gate is per-function so cleanup progress is visible
# in the test report.

import ast
import inspect
from pathlib import Path

from multiomics_explorer._outfacing_lint import lint_python_docstrings

_API_FILE = Path(inspect.getsourcefile(api)).resolve()


def _api_public_function_names() -> list[str]:
    """Top-level public functions in api/functions.py via AST walk."""
    tree = ast.parse(_API_FILE.read_text())
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                names.append(node.name)
    return names


def _api_function_line_range(name: str) -> tuple[int, int]:
    """Line range of `name` in api/functions.py (1-indexed, inclusive)."""
    tree = ast.parse(_API_FILE.read_text())
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return node.lineno, node.end_lineno
    raise LookupError(f"function {name!r} not found in {_API_FILE}")


@pytest.mark.parametrize("fn_name", _api_public_function_names())
def test_api_function_docstring_lint_clean(fn_name: str):
    """Each public function in api/functions.py has a clean docstring."""
    start, end = _api_function_line_range(fn_name)
    violations = lint_python_docstrings([_API_FILE])
    fn_violations = [v for v in violations if start <= v[1] <= end]
    if fn_violations:
        msg_lines = [
            f"{fn_name} ({_API_FILE.name}:{start}-{end}) has outfacing-doc violations:",
        ]
        for path, line_no, line, token in fn_violations:
            msg_lines.append(f"  {path.name}:{line_no}: {token!r} in: {line.strip()}")
        pytest.fail("\n".join(msg_lines))


# ---------------------------------------------------------------------------
# _evaluate_version_compat
# ---------------------------------------------------------------------------
class TestEvaluateVersionCompat:
    """The version_compat assert dict, including PEP 440 pre-release semantics."""

    def test_kg_min_none_fails(self):
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("0.1.0", None)
        assert result["name"] == "version_compat"
        assert result["kind"] == "version_compat"
        assert result["passed"] is False
        assert "did not declare mcp_min_version" in result["detail"]

    def test_pre_release_explorer_against_stable_min_fails(self):
        """The load-bearing case: explorer 0.1.0a1 against KG mcp_min_version 0.1.0.
        PEP 440 says 0.1.0a1 < 0.1.0 (pre-release ordering)."""
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("0.1.0a1", "0.1.0")
        assert result["passed"] is False
        assert "0.1.0a1" in result["detail"]
        assert "0.1.0" in result["detail"]
        assert "PEP 440" in result["detail"]

    def test_equal_versions_pass(self):
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("0.1.0", "0.1.0")
        assert result["passed"] is True
        assert result["detail"] is None

    def test_explorer_newer_than_min_passes(self):
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("0.2.0", "0.1.0")
        assert result["passed"] is True

    def test_matching_pre_releases_pass(self):
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("0.1.0a1", "0.1.0a1")
        assert result["passed"] is True

    def test_invalid_version_string_fails_gracefully(self):
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("not-a-version", "0.1.0")
        assert result["passed"] is False
        assert "Could not parse" in result["detail"]

    def test_explorer_version_unknown_fails_with_actionable_message(self):
        """Distinguish 'package not installed' from 'malformed version string'."""
        from multiomics_explorer.api.functions import _evaluate_version_compat
        result = _evaluate_version_compat("unknown", "0.1.0")
        assert result["passed"] is False
        assert "Explorer version unknown" in result["detail"]
        assert "uv/pip" in result["detail"]


class TestKGReleaseInfo:
    """The api-layer kg_release_info function — 4 scenarios via mocked conn."""

    def _make_conn(self, schema_info, labels, rel_types):
        """Build a fake conn whose execute_query returns one row of the
        build_kg_release_info() shape."""
        from unittest.mock import MagicMock
        conn = MagicMock()
        conn.execute_query.return_value = [{
            "schema_info": schema_info,
            "labels": labels,
            "rel_types": rel_types,
        }]
        return conn

    def _ok_schema_info(self, **overrides):
        si = {
            "version": "0.1.0",
            "built_at": "2026-06-02T00:00:00Z",
            "mcp_min_version": "0.0.1",
            "git_sha_short": "deadbee",
            "git_branch": "main",
            "gene_count": 100,
            "experiment_count": 5,
            "paper_count": 3,
            "organism_count": 2,
            "expression_edge_count": 500,
            "release_notes_url": None,
            # Spec 2026-08-27-slice4 §3.1: an absent hash is a `warn`, so the
            # "everything passes" fixture must carry the pinned value.
            "controlled_vocabularies_hash": (
                _kg_constants.EXPECTED_KG_SHAPE["controlled_vocabularies_hash"]),
        }
        si.update(overrides)
        return si

    def _ok_labels(self):
        return ["Schema_info", "Gene", "Experiment", "OrthologGroup", "Publication", "Other"]

    def _ok_rel_types(self):
        return ["Changes_expression_of", "Gene_in_ortholog_group", "Has_experiment", "Other"]

    def test_ok_verdict_when_everything_passes(self):
        from multiomics_explorer.api.functions import kg_release_info
        conn = self._make_conn(self._ok_schema_info(), self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert report["verdict"] == "ok"
        # 5 + 5 + 3 + 2 + 1 + 1 = 17 asserts (bucket 6, spec slice-4 §3.1)
        assert len(report["asserts"]) == 17
        assert all(a["passed"] for a in report["asserts"])
        assert "OK:" in report["summary"]
        assert report["kg"]["version"] == "0.1.0"
        assert report["explorer_version"]  # populated, real value

    def test_warn_verdict_on_version_mismatch(self):
        from multiomics_explorer.api.functions import kg_release_info
        # KG demands a version higher than anything the explorer could be
        si = self._ok_schema_info(mcp_min_version="99.99.99")
        conn = self._make_conn(si, self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert report["verdict"] == "warn"
        version_assert = next(a for a in report["asserts"] if a["kind"] == "version_compat")
        assert version_assert["passed"] is False
        assert "99.99.99" in version_assert["detail"]
        assert "WARN:" in report["summary"]

    def test_warn_verdict_on_missing_label(self):
        from multiomics_explorer.api.functions import kg_release_info
        labels = ["Schema_info", "Gene", "Experiment", "OrthologGroup"]  # Publication missing
        conn = self._make_conn(self._ok_schema_info(), labels, self._ok_rel_types())

        report = kg_release_info(conn)

        assert report["verdict"] == "warn"
        pub_assert = next(a for a in report["asserts"] if a["name"] == "node_label:Publication")
        assert pub_assert["passed"] is False

    def test_unknown_verdict_when_schema_info_missing(self):
        from multiomics_explorer.api.functions import kg_release_info
        conn = self._make_conn(None, [], [])

        report = kg_release_info(conn)

        assert report["verdict"] == "unknown"
        assert report["kg"] == {}
        assert report["asserts"] == []
        assert "UNKNOWN:" in report["summary"]
        assert "Schema_info node not found" in report["summary"]
        assert report["explorer_version"]  # still populated

    def test_kg_identity_only_carries_known_fields(self):
        """KGIdentity is the curated subset, not all Schema_info props."""
        from multiomics_explorer.api.functions import kg_release_info
        si = self._ok_schema_info()
        si["some_extra_prop"] = "should-not-appear"
        conn = self._make_conn(si, self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert "some_extra_prop" not in report["kg"]
        assert "version" in report["kg"]
        assert "gene_count" in report["kg"]

    def test_kg_identity_carries_release_highlights_and_breaking_changes(self):
        """The preflight change-list fields pass through into kg{} when stamped."""
        from multiomics_explorer.api.functions import kg_release_info
        si = self._ok_schema_info(
            release_highlights="- Publication discusses-edges\n- +8 organisms",
            breaking_changes="- annotation_quality redefined to 0..3",
        )
        conn = self._make_conn(si, self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert report["kg"]["release_highlights"] == "- Publication discusses-edges\n- +8 organisms"
        assert report["kg"]["breaking_changes"] == "- annotation_quality redefined to 0..3"

    def test_dev_build_leaves_change_list_fields_null_and_summary_clean(self):
        """A KG built without the fields (dev build) -> None, summary unchanged."""
        from multiomics_explorer.api.functions import kg_release_info
        # _ok_schema_info omits both keys, mirroring a dev build.
        conn = self._make_conn(self._ok_schema_info(), self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert report["kg"]["release_highlights"] is None
        assert report["kg"]["breaking_changes"] is None
        assert "Breaking" not in report["summary"]
        assert "release_highlights" not in report["summary"]

    def test_summary_points_to_breaking_changes_when_present(self):
        from multiomics_explorer.api.functions import kg_release_info
        si = self._ok_schema_info(breaking_changes="- annotation_quality redefined")
        conn = self._make_conn(si, self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert "Breaking" in report["summary"]
        assert "kg.breaking_changes" in report["summary"]

    def test_summary_points_to_release_highlights_when_present(self):
        from multiomics_explorer.api.functions import kg_release_info
        si = self._ok_schema_info(release_highlights="- Publication discusses-edges")
        conn = self._make_conn(si, self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert "kg.release_highlights" in report["summary"]

    def test_kg_identity_carries_deployment_role(self):
        """The KG self-declared deployment_role passes through into kg{}."""
        from multiomics_explorer.api.functions import kg_release_info
        si = self._ok_schema_info(deployment_role="production")
        conn = self._make_conn(si, self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert report["kg"]["deployment_role"] == "production"

    def test_deployment_role_null_when_absent(self):
        """Legacy KG built before deployment_role -> None (unknown), no crash."""
        from multiomics_explorer.api.functions import kg_release_info
        # _ok_schema_info omits deployment_role, mirroring a pre-2026-06 KG.
        conn = self._make_conn(self._ok_schema_info(), self._ok_labels(), self._ok_rel_types())

        report = kg_release_info(conn)

        assert report["kg"]["deployment_role"] is None
        assert report["verdict"] == "ok"  # absence is not a compat failure


# ===========================================================================
# Publication "discusses" literature-index surface
# (docs/tool-specs/publication-discusses-surface.md)
# ===========================================================================


class TestDiscussedByPublication:
    """New forward tool api fn: discussed_by_publication. Batch tool over DOIs.
    Two-query orchestration (summary + detail); not_found vs not_matched;
    offset slicing; summary=True ⇒ limit=0."""

    def _summary(self, **over):
        row = {
            "total_entries": 4,
            "total_matching": 4,
            "by_entity_kind": [{"item": "gene", "count": 3},
                               {"item": "kegg_pathway", "count": 1}],
            "by_prominence": [{"item": "central", "count": 2},
                              {"item": "peripheral", "count": 2}],
            "top_kegg_pathways": [
                {"id": "kegg.pathway:ko00710", "name": "Carbon fixation", "n": 1}],
            "top_publications": [
                {"doi": "10.1038/ismej.2016.70", "title": "Paper A", "n": 4}],
            # The summary builder returns resolved_dois (input DOIs that resolve
            # to a Publication) + matched_dois (DOIs with >=1 edge after
            # filters), both lowercased; the api diffs them into not_found /
            # not_matched. Defaults reflect the single fully-matched DOI.
            "resolved_dois": ["10.1038/ismej.2016.70"],
            "matched_dois": ["10.1038/ismej.2016.70"],
        }
        row.update(over)
        return [row]

    def _detail(self):
        return [
            {"doi": "10.1038/ismej.2016.70", "entity_kind": "gene",
             "entity_id": "PMT1030", "entity_name": "psbA",
             "organism": "Prochlorococcus MED4", "prominence": "central"},
            {"doi": "10.1038/ismej.2016.70", "entity_kind": "kegg_pathway",
             "entity_id": "kegg.pathway:ko00710", "entity_name": "Carbon fixation",
             "organism": None, "prominence": "peripheral"},
        ]

    def test_returns_envelope_and_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [self._summary(), self._detail()]
        result = api.discussed_by_publication(
            publication_dois=["10.1038/ismej.2016.70"], conn=mock_conn,
        )
        assert isinstance(result, dict)
        assert result["total_entries"] == 4
        assert result["total_matching"] == 4
        # APOC {item, count} frequency rows must be renamed to the semantic key
        # the MCP breakdown models expect (entity_kind / prominence), not passed
        # through raw — a raw `item` key fails Pydantic validation at the wrapper.
        assert result["by_entity_kind"][0]["entity_kind"] in ("gene", "kegg_pathway")
        assert "item" not in result["by_entity_kind"][0]
        assert result["by_prominence"][0]["prominence"] in ("central", "peripheral")
        assert "item" not in result["by_prominence"][0]
        assert "top_kegg_pathways" in result
        assert "top_publications" in result
        assert result["results"][0]["entity_id"] == "PMT1030"

    def test_pathway_row_organism_none(self, mock_conn):
        mock_conn.execute_query.side_effect = [self._summary(), self._detail()]
        result = api.discussed_by_publication(
            publication_dois=["10.1038/ismej.2016.70"], conn=mock_conn,
        )
        pathway_row = [r for r in result["results"]
                       if r["entity_kind"] == "kegg_pathway"][0]
        assert pathway_row["organism"] is None

    def test_not_found_and_not_matched(self, mock_conn):
        # 10.1038/ismej.2016.70 resolves + has edges; 10.1/empty resolves but
        # has no edges (not_matched); 10.0000/missing never resolves (not_found).
        mock_conn.execute_query.side_effect = [
            self._summary(
                resolved_dois=["10.1038/ismej.2016.70", "10.1/empty"],
                matched_dois=["10.1038/ismej.2016.70"],
            ),
            self._detail(),
        ]
        result = api.discussed_by_publication(
            publication_dois=["10.1038/ismej.2016.70", "10.0000/missing", "10.1/empty"],
            conn=mock_conn,
        )
        assert result["not_found"] == ["10.0000/missing"]
        assert result["not_matched"] == ["10.1/empty"]

    def test_summary_true_empty_results(self, mock_conn):
        mock_conn.execute_query.side_effect = [self._summary()]
        result = api.discussed_by_publication(
            publication_dois=["10.1038/ismej.2016.70"], summary=True, conn=mock_conn,
        )
        assert result["results"] == []
        assert result["returned"] == 0

    def test_limit_caps_returned(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary(total_entries=20, total_matching=20), self._detail()[:1],
        ]
        result = api.discussed_by_publication(
            publication_dois=["10.1038/ismej.2016.70"], limit=1, conn=mock_conn,
        )
        assert result["returned"] == 1
        assert result["truncated"] is True

    def test_offset_passes_to_envelope(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary(total_entries=20, total_matching=20), self._detail(),
        ]
        result = api.discussed_by_publication(
            publication_dois=["10.1038/ismej.2016.70"], limit=10, offset=5,
            conn=mock_conn,
        )
        assert result["offset"] == 5

    def test_empty_dois_raises(self, mock_conn):
        with pytest.raises(ValueError):
            api.discussed_by_publication(publication_dois=[], conn=mock_conn)

    def test_invalid_entity_kind_raises(self, mock_conn):
        with pytest.raises(ValueError):
            api.discussed_by_publication(
                publication_dois=["10.1/x"], entity_kind="bogus", conn=mock_conn,
            )

    def test_invalid_prominence_raises(self, mock_conn):
        with pytest.raises(ValueError):
            api.discussed_by_publication(
                publication_dois=["10.1/x"], prominence="loud", conn=mock_conn,
            )

    def test_top_level_export(self):
        from multiomics_explorer import discussed_by_publication as exported
        assert exported is api.discussed_by_publication


class TestGeneOverviewDiscusses:
    """Extension 1: gene_overview per-row discussed_in_publication_count
    (compact) + discussed_in_publications (verbose); envelope has_discussed +
    top_discussing_publications."""

    def _summary(self, has_discussed=1):
        return [{
            "total_matching": 1,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 1}],
            "by_category": [],
            "by_annotation_type": [],
            "by_annotation_state": [],
            "has_expression": 0,
            "has_significant_expression": 0,
            "has_orthologs": 0,
            "has_clusters": 0,
            "has_derived_metrics": 0,
            "has_chemistry": 0,
            "has_discussed": has_discussed,
            "not_found": [],
        }]

    def _detail(self, verbose=False):
        row = {
            "locus_tag": "PMT1030", "gene_name": "psbA", "product": "PSII",
            "gene_category": "Photosynthesis", "annotation_quality": 3,
            "organism_name": "Prochlorococcus MED4",
            "annotation_types": [], "annotation_state": "informative_multi",
            "informative_annotation_types": [],
            "expression_edge_count": 0,
            "significant_up_count": 0, "significant_down_count": 0,
            "closest_ortholog_group_size": 1, "closest_ortholog_genera": [],
            "cluster_membership_count": 0, "cluster_types": [],
            "numeric_metric_count": 0, "boolean_metric_count": 0,
            "categorical_metric_count": 0,
            "reaction_count": 0, "metabolite_count": 0, "transporter_count": 0,
            "evidence_sources": [],
            "discussed_in_publication_count": 2,
        }
        if verbose:
            row["discussed_in_publications"] = [
                {"doi": "10.1038/ismej.2016.70", "prominence": "central",
                 "evidence": "psbA is the model gene"},
            ]
        return [row]

    def _top_discussing(self):
        return [{"doi": "10.1038/ismej.2016.70", "title": "Paper A", "n_genes": 1}]

    def test_compact_row_has_discussed_count(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary(), self._detail(), self._top_discussing(),
        ]
        result = api.gene_overview(["PMT1030"], conn=mock_conn)
        assert result["results"][0]["discussed_in_publication_count"] == 2

    def test_envelope_has_discussed(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary(has_discussed=1), self._detail(), self._top_discussing(),
        ]
        result = api.gene_overview(["PMT1030"], conn=mock_conn)
        assert result["has_discussed"] == 1

    def test_envelope_top_discussing_publications(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary(), self._detail(), self._top_discussing(),
        ]
        result = api.gene_overview(["PMT1030"], conn=mock_conn)
        assert "top_discussing_publications" in result
        assert result["top_discussing_publications"][0]["doi"] == (
            "10.1038/ismej.2016.70")
        assert result["top_discussing_publications"][0]["n_genes"] == 1

    def test_verbose_row_has_discussed_publications_list(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary(), self._detail(verbose=True), self._top_discussing(),
        ]
        result = api.gene_overview(["PMT1030"], verbose=True, conn=mock_conn)
        row = result["results"][0]
        assert row["discussed_in_publications"][0]["doi"] == (
            "10.1038/ismej.2016.70")
        assert row["discussed_in_publications"][0]["prominence"] == "central"
        assert "evidence" in row["discussed_in_publications"][0]


class TestSearchOntologyDiscusses:
    """Extension 2: search_ontology gains verbose param + KEGG-only per-row
    discussed_by_n_publications (compact) + discussed_in_publications (verbose)."""

    def _summary(self):
        return [{
            "total_entries": 1, "total_matching": 1,
            "score_max": 5.0, "score_median": 5.0,
        }]

    def _kegg_detail(self, verbose=False):
        row = {
            "id": "kegg.pathway:ko00710", "name": "Carbon fixation",
            "score": 5.0, "level": 2, "tree": None, "tree_code": None,
            "is_informative": True,
            "discussed_by_n_publications": 19,
        }
        if verbose:
            row["discussed_in_publications"] = [
                {"doi": "10.1038/ismej.2016.70", "prominence": "central",
                 "evidence": "carbon fixation is discussed"},
            ]
        return [row]

    def test_kegg_row_has_discussed_count(self, mock_conn):
        mock_conn.execute_query.side_effect = [self._summary(), self._kegg_detail()]
        result = api.search_ontology(
            search_text="carbon", ontology="kegg", limit=10, conn=mock_conn,
        )
        assert result["results"][0]["discussed_by_n_publications"] == 19

    def test_kegg_verbose_row_has_discussed_list(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            self._summary(), self._kegg_detail(verbose=True),
        ]
        result = api.search_ontology(
            search_text="carbon", ontology="kegg", limit=10, verbose=True,
            conn=mock_conn,
        )
        row = result["results"][0]
        assert row["discussed_in_publications"][0]["doi"] == (
            "10.1038/ismej.2016.70")
        assert "evidence" in row["discussed_in_publications"][0]

    def test_verbose_param_accepted(self, mock_conn):
        """search_ontology must now accept a verbose kwarg (new interface add)."""
        mock_conn.execute_query.side_effect = [self._summary(), self._kegg_detail()]
        # Should not raise TypeError for unexpected kwarg.
        api.search_ontology(
            search_text="x", ontology="kegg", limit=5, verbose=False, conn=mock_conn,
        )


class TestListPublicationsDiscusses:
    """Extension 3: list_publications per-row discussed_gene_count +
    discussed_pathway_count; envelope by_discusses_coverage."""

    _PUB_BASE = {
        "doi": "10.1038/ismej.2016.70", "title": "Paper A", "authors": ["A"],
        "year": 2016, "journal": "ISMEJ", "study_type": "S",
        "organisms": ["MED4"], "experiment_count": 1,
        "treatment_types": ["coculture"], "background_factors": [],
        "omics_types": ["RNASEQ"],
        "clustering_analysis_count": 0, "cluster_types": [],
        "metabolite_count": 0, "metabolite_assay_count": 0,
        "metabolite_compartments": [],
    }

    def _summary(self, **over):
        # by_discusses_coverage is a single {has_discusses, no_discusses} map
        # (binary split), not a frequency list — matches the builder RETURN.
        row = {"total_entries": 1, "total_matching": 1,
               "by_discusses_coverage": {"has_discusses": 1, "no_discusses": 0}}
        row.update(over)
        return [row]

    def test_row_has_discussed_counts(self, mock_conn):
        row = {**self._PUB_BASE, "discussed_gene_count": 25,
               "discussed_pathway_count": 4}
        mock_conn.execute_query.side_effect = [self._summary(), [row]]
        result = api.list_publications(conn=mock_conn)
        r = result["results"][0]
        assert r["discussed_gene_count"] == 25
        assert r["discussed_pathway_count"] == 4

    def test_envelope_by_discusses_coverage(self, mock_conn):
        row = {**self._PUB_BASE, "discussed_gene_count": 25,
               "discussed_pathway_count": 4}
        mock_conn.execute_query.side_effect = [self._summary(), [row]]
        result = api.list_publications(conn=mock_conn)
        assert result["by_discusses_coverage"] == {"has_discusses": 1, "no_discusses": 0}

    def test_zero_discusses_pub(self, mock_conn):
        row = {**self._PUB_BASE, "discussed_gene_count": 0,
               "discussed_pathway_count": 0}
        mock_conn.execute_query.side_effect = [self._summary(), [row]]
        result = api.list_publications(conn=mock_conn)
        r = result["results"][0]
        assert r["discussed_gene_count"] == 0
        assert r["discussed_pathway_count"] == 0


# ---------------------------------------------------------------------------
# Annotation-trust surface (PR 3a) — api layer
#
# One normalized trust vocabulary across 17 ontologies: generic
# config-validated filters, envelope rollups + auto-warnings, the
# strip-non-applicable row rule, three newly registered ontologies, and the
# ControlledVocabulary -> pivot -> warning ladder behind list_filter_values.
# ---------------------------------------------------------------------------

import inspect as _inspect

_ORG = "Prochlorococcus MED4"
_MIT1002 = "Alteromonas macleodii MIT1002"


def _trust_dispatch(mock_conn, rules, default=None):
    """Route mocked execute_query calls by a substring of their Cypher.

    `rules` is an ordered list of (needle, rows). The first needle contained
    in the Cypher wins; `default` (or []) is the fallthrough.
    """
    def _exec(cypher, **params):
        for needle, rows in rules:
            if needle in cypher:
                return rows
        return [] if default is None else default
    mock_conn.execute_query.side_effect = _exec
    return mock_conn


def _org_rows(name=_ORG):
    return [{"organisms": [name]}]


def _freq_values(rollup):
    """Values of a `by_X` rollup, whatever its value-key is named."""
    out = []
    for entry in rollup:
        vals = [v for k, v in entry.items() if k != "count"]
        out.append(vals[0] if len(vals) == 1 else tuple(vals))
    return out


def _freq_map(rollup):
    return dict(zip(_freq_values(rollup), [e["count"] for e in rollup]))


def _gbo_rules(detail_rows, per_term=None, per_gene=None, org=_ORG):
    """Mock the genes_by_ontology query chain (org -> A -> B -> D)."""
    per_term = per_term if per_term is not None else [{
        "term_id": "tcdb:3.A.1", "term_name": "ABC superfamily", "level": 2,
        "tree": None, "tree_code": None, "best_effort": False,
        "n_genes": len(detail_rows),
        "cat_freqs": [{"item": "Transport", "count": len(detail_rows)}],
        "is_informative": True,
    }]
    per_gene = per_gene if per_gene is not None else [
        {"locus_tag": r["locus_tag"], "gene_category": "Transport",
         "n_terms": 1, "levels_hit": [2]}
        for r in detail_rows
    ]
    return [
        ("MATCH (o:OrganismTaxon)", _org_rows(org)),
        ("matched_label", []),
        ("cat_freqs", per_term),
        ("levels_hit", per_gene),
    ]


class TestGenesByOntologyTrustFilterSignature:
    """Generic trust filters, all defaulting to None — defaults never filter."""

    @pytest.mark.parametrize("param", [
        "sources", "evidence", "max_tier", "min_evidence_score",
        "call_class", "interpro_type",
    ])
    def test_param_exists_and_defaults_to_none(self, param):
        sig = _inspect.signature(api.genes_by_ontology)
        assert param in sig.parameters, param
        assert sig.parameters[param].default is None, param

    @pytest.mark.parametrize("fn_name,param", [
        ("gene_ontology_terms", "sources"),
        ("gene_ontology_terms", "evidence"),
        ("gene_ontology_terms", "max_tier"),
        ("gene_ontology_terms", "min_evidence_score"),
        ("gene_ontology_terms", "call_class"),
        ("gene_ontology_terms", "interpro_type"),
        ("pathway_enrichment", "sources"),
        ("pathway_enrichment", "evidence"),
        ("pathway_enrichment", "max_tier"),
        ("pathway_enrichment", "min_evidence_score"),
        ("pathway_enrichment", "call_class"),
        ("pathway_enrichment", "interpro_type"),
        ("cluster_enrichment", "sources"),
        ("cluster_enrichment", "evidence"),
        ("cluster_enrichment", "max_tier"),
        ("cluster_enrichment", "min_evidence_score"),
        ("cluster_enrichment", "call_class"),
        ("cluster_enrichment", "interpro_type"),
        ("ontology_landscape", "call_class"),
        ("ontology_landscape", "interpro_type"),
    ])
    def test_filters_present_on_the_other_ontology_tools(self, fn_name, param):
        sig = _inspect.signature(getattr(api, fn_name))
        assert param in sig.parameters, f"{fn_name}.{param}"
        assert sig.parameters[param].default is None

    def test_gene_ontology_terms_gains_include_superseded(self):
        sig = _inspect.signature(api.gene_ontology_terms)
        assert sig.parameters["include_superseded"].default is False

    def test_search_ontology_gains_interpro_type(self):
        sig = _inspect.signature(api.search_ontology)
        assert sig.parameters["interpro_type"].default is None

    def test_list_filter_values_gains_ontology_scope(self):
        sig = _inspect.signature(api.list_filter_values)
        assert sig.parameters["ontology"].default is None


class TestGenesByOntologyTrustEnvelope:
    """Design section 5 envelope keys on the gene-set tools."""

    def _run(self, mock_conn, rows, **kwargs):
        _trust_dispatch(mock_conn, _gbo_rules(rows), default=rows)
        return api.genes_by_ontology(
            ontology=kwargs.pop("ontology", "tcdb"), organism=_ORG,
            level=kwargs.pop("level", 2), conn=mock_conn, **kwargs,
        )

    def _tcdb_rows(self):
        return [
            {"locus_tag": "PMM0392", "gene_name": None, "product": None,
             "gene_category": "Transport", "term_id": "tcdb:3.A.1",
             "term_name": "ABC superfamily", "level": 2, "is_informative": True,
             "evidence": "homology", "sources": ["eggnog"],
             "evidence_score": 0.6, "tier": None},
            {"locus_tag": "PMM0393", "gene_name": None, "product": None,
             "gene_category": "Transport", "term_id": "tcdb:3.A.1",
             "term_name": "ABC superfamily", "level": 2, "is_informative": True,
             "evidence": "curated", "sources": ["tcdb", "eggnog"],
             "evidence_score": 1.0, "tier": 1},
        ]

    @pytest.mark.parametrize("key", [
        "trust_axes", "by_evidence", "by_tier", "by_sources", "by_call_class",
        "evidence_score_stats", "filters_applied", "skipped_ontologies",
        "warnings",
    ])
    def test_envelope_key_present(self, mock_conn, key):
        result = self._run(mock_conn, self._tcdb_rows())
        assert key in result

    def test_trust_axes_reports_the_ontology_axes(self, mock_conn):
        result = self._run(mock_conn, self._tcdb_rows())
        assert result["trust_axes"] == {
            "tcdb": ["sources", "evidence", "evidence_score", "tier"]}

    def test_by_evidence_rolls_up_the_compact_column(self, mock_conn):
        result = self._run(mock_conn, self._tcdb_rows())
        assert _freq_map(result["by_evidence"]) == {"homology": 1, "curated": 1}

    def test_by_tier_carries_an_explicit_null_bucket(self, mock_conn):
        """eggNOG-only TCDB edges carry no tier; the bucket is explicit so a
        reader never mistakes tier-null for tier-1."""
        result = self._run(mock_conn, self._tcdb_rows())
        values = _freq_values(result["by_tier"])
        assert "null" in values
        assert _freq_map(result["by_tier"])["null"] == 1

    def test_by_sources_counts_membership_not_tuples(self, mock_conn):
        result = self._run(mock_conn, self._tcdb_rows())
        assert _freq_map(result["by_sources"]) == {"eggnog": 2, "tcdb": 1}

    def test_evidence_score_stats_shape(self, mock_conn):
        result = self._run(mock_conn, self._tcdb_rows())
        stats = result["evidence_score_stats"]
        assert set(stats) == {"min", "median", "max", "n_null"}
        assert stats["min"] == 0.6
        assert stats["max"] == 1.0
        assert stats["n_null"] == 0

    def test_evidence_score_signals_absent_without_a_cutoff(self, mock_conn):
        """Ground rule 1: the envelope shows fired signals only when the one
        numeric cutoff is actually applied."""
        result = self._run(mock_conn, self._tcdb_rows())
        assert "evidence_score_signals" not in result

    def test_evidence_score_signals_present_with_a_cutoff(self, mock_conn):
        rows = self._tcdb_rows()
        rules = _gbo_rules(rows) + [
            ("ControlledVocabulary", [{
                "edge_type": "Gene_has_tcdb_family",
                "signals": ["tier_le_2", "pfam_support", "go_support",
                            "source_agreement", "identity"],
                "signal_count": 5,
            }]),
        ]
        _trust_dispatch(mock_conn, rules, default=rows)
        result = api.genes_by_ontology(
            ontology="tcdb", organism=_ORG, level=2,
            min_evidence_score=0.6, conn=mock_conn,
        )
        assert "evidence_score_signals" in result
        assert "Gene_has_tcdb_family" in result["evidence_score_signals"]

    def test_filters_applied_echoes_the_active_filters(self, mock_conn):
        result = self._run(
            mock_conn, self._tcdb_rows(), max_tier=2, sources=["eggnog"])
        applied = result["filters_applied"]
        assert applied["max_tier"] == 2
        assert applied["sources"] == ["eggnog"]

    def test_filters_applied_omits_unset_filters(self, mock_conn):
        result = self._run(mock_conn, self._tcdb_rows())
        assert result["filters_applied"] == {}

    def test_skipped_ontologies_empty_on_single_ontology_tool(self, mock_conn):
        result = self._run(mock_conn, self._tcdb_rows())
        assert result["skipped_ontologies"] == []


class TestGenesByOntologyTrustWarnings:
    """Design section 5.4 auto-warnings — rows-conditional, message-pinned."""

    def _merops_rows(self, call_class="nonpeptidase_homolog"):
        return [{
            "locus_tag": "MIT1002_03660", "gene_name": None, "product": None,
            "gene_category": "Unknown", "term_id": "merops.family:S14",
            "term_name": "ClpP", "level": 1, "is_informative": True,
            "evidence": "signature", "call_class": call_class,
        }]

    def _run_merops(self, mock_conn, rows, **kwargs):
        rules = _gbo_rules(rows, org=_MIT1002)
        _trust_dispatch(mock_conn, rules, default=rows)
        return api.genes_by_ontology(
            ontology="merops", organism=_MIT1002, level=0,
            conn=mock_conn, **kwargs,
        )

    def test_nonpeptidase_rows_without_call_class_filter_warn(self, mock_conn):
        result = self._run_merops(mock_conn, self._merops_rows())
        joined = " ".join(result["warnings"])
        assert "catalytically-dead homologs" in joined

    def test_no_warning_when_call_class_filter_is_set(self, mock_conn):
        result = self._run_merops(
            mock_conn, self._merops_rows(call_class="peptidase"),
            call_class=["peptidase"],
        )
        joined = " ".join(result["warnings"])
        assert "catalytically-dead homologs" not in joined

    def test_no_warning_when_no_nonpeptidase_rows(self, mock_conn):
        result = self._run_merops(
            mock_conn, self._merops_rows(call_class="peptidase"))
        joined = " ".join(result["warnings"])
        assert "catalytically-dead homologs" not in joined

    def test_by_call_class_rollup(self, mock_conn):
        result = self._run_merops(mock_conn, self._merops_rows())
        assert _freq_map(result["by_call_class"]) == {"nonpeptidase_homolog": 1}

    def test_max_tier_keeping_tier_null_rows_warns(self, mock_conn):
        rows = [{
            "locus_tag": "PMM0392", "gene_name": None, "product": None,
            "gene_category": "Transport", "term_id": "tcdb:3.A.1",
            "term_name": "ABC superfamily", "level": 2, "is_informative": True,
            "evidence": "homology", "tier": None,
        }]
        _trust_dispatch(mock_conn, _gbo_rules(rows), default=rows)
        result = api.genes_by_ontology(
            ontology="tcdb", organism=_ORG, level=2, max_tier=2, conn=mock_conn,
        )
        joined = " ".join(result["warnings"])
        assert "carry no tier" in joined

    def test_min_evidence_score_applied_warns(self, mock_conn):
        rows = [{
            "locus_tag": "PMM0392", "term_id": "tcdb:3.A.1",
            "term_name": "ABC superfamily", "level": 2, "gene_name": None,
            "product": None, "gene_category": "Transport",
            "is_informative": True, "evidence": "homology",
        }]
        rules = _gbo_rules(rows) + [("ControlledVocabulary", [])]
        _trust_dispatch(mock_conn, rules, default=rows)
        result = api.genes_by_ontology(
            ontology="tcdb", organism=_ORG, level=2,
            min_evidence_score=0.6, conn=mock_conn,
        )
        assert result["warnings"], "min_evidence_score must announce itself"


class TestGenesByOntologyTrustValidation:
    """Unsupported axis / unknown facet raise before any query runs."""

    def test_max_tier_on_kegg_raises(self, mock_conn):
        with pytest.raises(ValueError, match="max_tier"):
            api.genes_by_ontology(
                ontology="kegg", organism=_ORG, level=1, max_tier=2,
                conn=mock_conn,
            )

    def test_call_class_on_tcdb_raises(self, mock_conn):
        with pytest.raises(ValueError, match="call_class"):
            api.genes_by_ontology(
                ontology="tcdb", organism=_ORG, level=2,
                call_class=["peptidase"], conn=mock_conn,
            )

    def test_error_message_names_the_ontology_axes(self, mock_conn):
        with pytest.raises(ValueError) as excinfo:
            api.genes_by_ontology(
                ontology="kegg", organism=_ORG, level=1,
                min_evidence_score=0.5, conn=mock_conn,
            )
        msg = str(excinfo.value)
        assert "evidence" in msg
        assert "trust_axes" in msg

    def test_interpro_type_on_non_interpro_raises(self, mock_conn):
        with pytest.raises(ValueError, match="interpro_type"):
            api.genes_by_ontology(
                ontology="tcdb", organism=_ORG, level=2,
                interpro_type="FAMILY", conn=mock_conn,
            )

    def test_the_three_new_ontologies_are_accepted(self, mock_conn):
        for ontology in ("interpro", "ncbifam", "merops"):
            _trust_dispatch(mock_conn, _gbo_rules([]), default=[])
            result = api.genes_by_ontology(
                ontology=ontology, organism=_ORG, level=0, conn=mock_conn,
            )
            assert result["ontology"] == ontology


class TestGenesByOntologyStripRule:
    """Rows omit columns their ontology does not own; owned-but-null stay."""

    def _run(self, ontology, rows, **kwargs):
        from unittest.mock import MagicMock
        conn = MagicMock()
        _trust_dispatch(conn, _gbo_rules(rows), default=rows)
        return api.genes_by_ontology(
            ontology=ontology, organism=_ORG, level=kwargs.pop("level", 2),
            conn=conn, **kwargs,
        )

    def test_compact_tcdb_row_keeps_evidence_and_sheds_axes(self):
        rows = [{
            "locus_tag": "PMM0392", "gene_name": None, "product": None,
            "gene_category": "Transport", "term_id": "tcdb:3.A.1",
            "term_name": "ABC superfamily", "level": 2, "is_informative": True,
            "evidence": "homology", "sources": ["eggnog"],
            "evidence_score": 0.6, "tier": None,
        }]
        result = self._run("tcdb", rows)
        row = result["results"][0]
        assert row["evidence"] == "homology"
        assert "sources" not in row
        assert "evidence_score" not in row
        assert "tier" not in row

    def test_verbose_tcdb_row_keeps_owned_null_tier(self):
        rows = [{
            "locus_tag": "PMM0392", "gene_name": None, "product": None,
            "gene_category": "Transport", "term_id": "tcdb:3.A.1",
            "term_name": "ABC superfamily", "level": 2, "is_informative": True,
            "evidence": "homology", "sources": ["eggnog"],
            "evidence_score": 0.6, "tier": None,
            "attachment_depth": "most_specific",
        }]
        result = self._run("tcdb", rows, verbose=True)
        row = result["results"][0]
        assert "tier" in row and row["tier"] is None
        assert row["attachment_depth"] == "most_specific"

    def test_kegg_row_never_carries_evidence_score(self):
        rows = [{
            "locus_tag": "PMM0001", "gene_name": None, "product": None,
            "gene_category": "Unknown", "term_id": "kegg:ko00010",
            "term_name": "Glycolysis", "level": 3, "is_informative": True,
            "evidence": "signature", "sources": ["eggnog"],
            "evidence_score": None,
        }]
        result = self._run("kegg", rows, level=3, verbose=True)
        row = result["results"][0]
        assert "evidence_score" not in row
        assert row["evidence"] == "signature"

    def test_interpro_row_keeps_interpro_type_in_compact(self):
        rows = [{
            "locus_tag": "PMM0001", "gene_name": None, "product": None,
            "gene_category": "Unknown", "term_id": "interpro:IPR027417",
            "term_name": "P-loop NTPase", "level": 0, "is_informative": True,
            "evidence": "signature", "interpro_type": "HOMOLOGOUS_SUPERFAMILY",
        }]
        result = self._run("interpro", rows, level=0)
        row = result["results"][0]
        assert row["interpro_type"] == "HOMOLOGOUS_SUPERFAMILY"


class TestGeneOntologyTermsMultiOntology:
    """Design section 4.5 skip / raise matrix for `ontology: list | None`."""

    def _rules(self, detail_rows=None, org=_ORG):
        detail_rows = detail_rows or []
        return [
            ("MATCH (o:OrganismTaxon)", _org_rows(org)),
            ("AS found", [{"lt": "PMM0392", "found": True}]),
            ("gene_term_counts", []),
        ]

    def test_accepts_a_list_of_ontologies(self, mock_conn):
        _trust_dispatch(mock_conn, self._rules(), default=[])
        result = api.gene_ontology_terms(
            locus_tags=["PMM0392"], organism=_ORG,
            ontology=["tcdb", "merops"], conn=mock_conn,
        )
        assert result["skipped_ontologies"] == []

    def test_filter_carried_by_all_applies_to_all(self, mock_conn):
        _trust_dispatch(mock_conn, self._rules(), default=[])
        result = api.gene_ontology_terms(
            locus_tags=["PMM0392"], organism=_ORG,
            ontology=["tcdb", "merops"], max_tier=2, conn=mock_conn,
        )
        assert result["skipped_ontologies"] == []
        assert result["filters_applied"]["max_tier"] == 2

    def test_filter_carried_by_some_skips_the_rest_with_a_warning(self, mock_conn):
        _trust_dispatch(mock_conn, self._rules(), default=[])
        result = api.gene_ontology_terms(
            locus_tags=["PMM0392"], organism=_ORG,
            ontology=["tcdb", "kegg"], max_tier=2, conn=mock_conn,
        )
        skipped = {e["ontology"] for e in result["skipped_ontologies"]}
        assert skipped == {"kegg"}
        assert all("reason" in e for e in result["skipped_ontologies"])
        assert result["warnings"]

    def test_filter_carried_by_none_raises(self, mock_conn):
        with pytest.raises(ValueError, match="max_tier"):
            api.gene_ontology_terms(
                locus_tags=["PMM0392"], organism=_ORG,
                ontology=["kegg", "go_bp"], max_tier=2, conn=mock_conn,
            )

    def test_facet_owner_in_the_set_applies_to_owner_only(self, mock_conn):
        _trust_dispatch(mock_conn, self._rules(), default=[])
        result = api.gene_ontology_terms(
            locus_tags=["PMM0392"], organism=_ORG,
            ontology=["interpro", "kegg"], interpro_type="FAMILY",
            conn=mock_conn,
        )
        assert result["skipped_ontologies"] == []

    def test_facet_owner_absent_raises(self, mock_conn):
        with pytest.raises(ValueError, match="interpro_type"):
            api.gene_ontology_terms(
                locus_tags=["PMM0392"], organism=_ORG,
                ontology=["kegg", "tcdb"], interpro_type="FAMILY",
                conn=mock_conn,
            )

    def test_tree_applies_to_brite_only_and_skips_nothing(self, mock_conn):
        """`tree` is a facet like any other: it narrows its owner and leaves
        the rest of the list alone, rather than refusing the whole call."""
        _trust_dispatch(mock_conn, self._rules(), default=[])
        result = api.gene_ontology_terms(
            locus_tags=["PMM0392"], organism=_ORG,
            ontology=["brite", "kegg"], tree="transporters", conn=mock_conn,
        )
        assert result["skipped_ontologies"] == []
        assert result["filters_applied"]["tree"] == "transporters"

    def test_tree_owner_absent_raises(self, mock_conn):
        with pytest.raises(ValueError, match="tree"):
            api.gene_ontology_terms(
                locus_tags=["PMM0392"], organism=_ORG,
                ontology=["kegg", "tcdb"], tree="transporters",
                conn=mock_conn,
            )

    def test_unknown_ontology_name_raises(self, mock_conn):
        with pytest.raises(ValueError, match="bogus"):
            api.gene_ontology_terms(
                locus_tags=["PMM0392"], organism=_ORG,
                ontology=["bogus"], conn=mock_conn,
            )

    def test_single_string_ontology_still_accepted(self, mock_conn):
        _trust_dispatch(mock_conn, self._rules(), default=[])
        result = api.gene_ontology_terms(
            locus_tags=["PMM0392"], organism=_ORG, ontology="tcdb",
            conn=mock_conn,
        )
        assert "results" in result

    def test_trust_axes_envelope_is_per_ontology(self, mock_conn):
        _trust_dispatch(mock_conn, self._rules(), default=[])
        result = api.gene_ontology_terms(
            locus_tags=["PMM0392"], organism=_ORG,
            ontology=["tcdb", "kegg"], conn=mock_conn,
        )
        assert result["trust_axes"]["kegg"] == ["sources", "evidence"]
        assert "tier" in result["trust_axes"]["tcdb"]


class TestOntologyLandscapeTrustSurface:
    """Landscape gains `ontology: list | None`, the merops call_class filter,
    and the InterPro (interpro_type, level) stratum."""

    def _rules(self, stat_rows=None):
        return [
            ("MATCH (o:OrganismTaxon)", _org_rows()),
            ("total_genes", [{"total_genes": 1000}]),
            ("n_terms_with_genes", stat_rows or []),
        ]

    def test_accepts_a_list_of_ontologies(self, mock_conn):
        _trust_dispatch(mock_conn, self._rules(), default=[])
        result = api.ontology_landscape(
            organism=_ORG, ontology=["tcdb", "merops"], conn=mock_conn)
        assert "results" in result

    def test_unknown_ontology_in_list_raises(self, mock_conn):
        with pytest.raises(ValueError, match="bogus"):
            api.ontology_landscape(
                organism=_ORG, ontology=["bogus"], conn=mock_conn)

    def test_call_class_on_non_merops_raises(self, mock_conn):
        with pytest.raises(ValueError, match="call_class"):
            api.ontology_landscape(
                organism=_ORG, ontology="tcdb", call_class=["peptidase"],
                conn=mock_conn)

    def test_interpro_stratum_rows_carry_interpro_type(self, mock_conn):
        stat_rows = [{
            "level": 0, "tree": None, "tree_code": None,
            "interpro_type": "HOMOLOGOUS_SUPERFAMILY",
            "n_terms_with_genes": 74, "n_genes_at_level": 400,
            "min_genes_per_term": 5, "q1_genes_per_term": 6.0,
            "median_genes_per_term": 9.0, "q3_genes_per_term": 20.0,
            "max_genes_per_term": 119, "n_best_effort": 0,
        }]
        _trust_dispatch(mock_conn, self._rules(stat_rows), default=[])
        result = api.ontology_landscape(
            organism=_ORG, ontology="interpro", conn=mock_conn)
        assert result["results"][0]["interpro_type"] == "HOMOLOGOUS_SUPERFAMILY"

    def test_by_ontology_reports_best_interpro_type(self, mock_conn):
        stat_rows = [{
            "level": 0, "tree": None, "tree_code": None,
            "interpro_type": "HOMOLOGOUS_SUPERFAMILY",
            "n_terms_with_genes": 74, "n_genes_at_level": 400,
            "min_genes_per_term": 5, "q1_genes_per_term": 6.0,
            "median_genes_per_term": 9.0, "q3_genes_per_term": 20.0,
            "max_genes_per_term": 119, "n_best_effort": 0,
        }]
        _trust_dispatch(mock_conn, self._rules(stat_rows), default=[])
        result = api.ontology_landscape(
            organism=_ORG, ontology="interpro", conn=mock_conn)
        entry = result["by_ontology"]["interpro"]
        assert entry["best_interpro_type"] == "HOMOLOGOUS_SUPERFAMILY"
        assert entry["best_level"] == 0

    def test_non_interpro_rows_carry_no_interpro_type(self, mock_conn):
        stat_rows = [{
            "level": 1, "tree": None, "tree_code": None,
            "n_terms_with_genes": 10, "n_genes_at_level": 100,
            "min_genes_per_term": 5, "q1_genes_per_term": 6.0,
            "median_genes_per_term": 9.0, "q3_genes_per_term": 20.0,
            "max_genes_per_term": 40, "n_best_effort": 0,
        }]
        _trust_dispatch(mock_conn, self._rules(stat_rows), default=[])
        result = api.ontology_landscape(
            organism=_ORG, ontology="kegg", conn=mock_conn)
        assert "interpro_type" not in result["results"][0]

    def test_default_fan_out_covers_all_17_ontologies(self, mock_conn):
        seen = []

        def _exec(cypher, **params):
            if "MATCH (o:OrganismTaxon)" in cypher:
                return _org_rows()
            if "total_genes" in cypher:
                return [{"total_genes": 1000}]
            seen.append(cypher)
            return []

        mock_conn.execute_query.side_effect = _exec
        api.ontology_landscape(organism=_ORG, conn=mock_conn)
        joined = "\n".join(seen)
        for rel in ("Gene_has_interpro_entry", "Gene_has_ncbifam_family",
                    "Gene_has_merops_family"):
            assert rel in joined, rel


class TestEnrichmentTrustFilters:
    """Enrichment shapes TERM2GENE with the same filters, so tested sets and
    background move together."""

    def test_interpro_without_interpro_type_raises(self, mock_conn):
        with pytest.raises(ValueError, match="interpro_type"):
            api.pathway_enrichment(
                organism=_ORG, experiment_ids=["EXP1"], ontology="interpro",
                level=0, conn=mock_conn,
            )

    def test_cluster_enrichment_interpro_without_type_raises(self, mock_conn):
        with pytest.raises(ValueError, match="interpro_type"):
            api.cluster_enrichment(
                analysis_id="A1", organism=_ORG, ontology="interpro",
                level=0, conn=mock_conn,
            )

    def test_unsupported_axis_raises_on_enrichment(self, mock_conn):
        with pytest.raises(ValueError, match="max_tier"):
            api.pathway_enrichment(
                organism=_ORG, experiment_ids=["EXP1"], ontology="kegg",
                level=1, max_tier=2, conn=mock_conn,
            )

    def test_the_three_new_ontologies_are_valid_enrichment_targets(self):
        from multiomics_explorer.kg.constants import ALL_ONTOLOGIES
        for ontology in ("interpro", "ncbifam", "merops"):
            assert ontology in ALL_ONTOLOGIES


class TestEnrichmentEnvelopeTrustKeys:
    """Design section 5: enrichment envelope adds filters_applied,
    trust_axes, background_filtered, interpro_type."""

    @pytest.mark.parametrize("key", [
        "filters_applied", "trust_axes", "background_filtered", "interpro_type",
    ])
    def test_envelope_key_declared_on_the_result(self, key):
        from multiomics_explorer.analysis.enrichment import EnrichmentResult
        src = _inspect.getsource(EnrichmentResult.to_envelope)
        assert key in src, f"{key} missing from the enrichment envelope"

    def test_background_filtered_is_true_only_for_edge_filters(self):
        from multiomics_explorer.api.functions import _enrichment_trust_params
        block = _enrichment_trust_params("merops", {"max_tier": 2}, None)
        assert block["background_filtered"] is True

    def test_a_facet_alone_does_not_narrow_the_background(self):
        """`interpro_type` and `tree` pick which terms are tested; neither
        removes a gene from the universe."""
        from multiomics_explorer.api.functions import _enrichment_trust_params
        block = _enrichment_trust_params(
            "interpro", {"interpro_type": "FAMILY"}, "FAMILY",
        )
        assert block["background_filtered"] is False
        assert block["filters_applied"]["interpro_type"] == "FAMILY"

    def test_no_filters_at_all_is_false(self):
        from multiomics_explorer.api.functions import _enrichment_trust_params
        assert _enrichment_trust_params("kegg", {}, None)[
            "background_filtered"] is False


class TestSearchOntologyTrustSurfaceApi:
    """PR 3a: `interpro_type` facet + compact gene_count / organism_count.
    Browse mode and multi-ontology are PR 3b."""

    def _rules(self, rows):
        return [
            ("total_entries", [{
                "total_entries": 100, "total_matching": len(rows),
                "score_max": 5.0, "score_median": 3.0}]),
        ]

    def test_rows_carry_gene_count_and_organism_count(self, mock_conn):
        rows = [{
            "id": "merops.family:S33", "name": "S33", "score": 5.0,
            "level": 1, "tree": None, "tree_code": None,
            "is_informative": True, "gene_count": 412, "organism_count": 41,
        }]
        _trust_dispatch(mock_conn, self._rules(rows), default=rows)
        result = api.search_ontology(
            "protease", "merops", conn=mock_conn)
        assert result["results"][0]["gene_count"] == 412
        assert result["results"][0]["organism_count"] == 41

    def test_interpro_type_facet_is_forwarded(self, mock_conn):
        seen = {}

        def _exec(cypher, **params):
            seen.update(params)
            if "total_entries" in cypher:
                return [{"total_entries": 10, "total_matching": 0,
                         "score_max": None, "score_median": None}]
            return []

        mock_conn.execute_query.side_effect = _exec
        api.search_ontology(
            "kinase", "interpro", interpro_type="DOMAIN", conn=mock_conn)
        assert seen.get("interpro_type") == "DOMAIN"

    def test_interpro_type_on_non_interpro_raises(self, mock_conn):
        with pytest.raises(ValueError, match="interpro_type"):
            api.search_ontology(
                "transport", "kegg", interpro_type="DOMAIN", conn=mock_conn)

    @pytest.mark.parametrize("ontology", ["interpro", "ncbifam", "merops"])
    def test_new_ontologies_accepted(self, mock_conn, ontology):
        _trust_dispatch(mock_conn, self._rules([]), default=[])
        result = api.search_ontology("x", ontology, conn=mock_conn)
        assert result["returned"] == 0


class TestListFilterValuesTrustTypes:
    """ControlledVocabulary owns the values; the pivot query is the fallback
    and always announces itself."""

    TRUST_FILTER_TYPES = [
        "evidence", "sources", "call_class", "interpro_type",
        "ncbifam_family_type", "merops_catalytic_type", "merops_family_class",
        "best_hit_kind", "pfam_support", "attachment_depth",
    ]

    def _vocab_rows(self, values, applies_to="Gene_has_merops_family"):
        return [{
            "applies_to": applies_to,
            "values": values,
            "description": "MEROPS call class",
            "sparse": "false",
        }]

    @pytest.mark.parametrize("filter_type", TRUST_FILTER_TYPES)
    def test_filter_type_is_accepted(self, mock_conn, filter_type):
        _trust_dispatch(
            mock_conn,
            [("ControlledVocabulary", self._vocab_rows(["a", "b"]))],
            default=[],
        )
        result = api.list_filter_values(filter_type=filter_type, conn=mock_conn)
        assert result["filter_type"] == filter_type

    def test_vocabulary_rows_are_tagged_as_vocabulary(self, mock_conn):
        _trust_dispatch(
            mock_conn,
            [("ControlledVocabulary", self._vocab_rows(
                ["peptidase", "nonpeptidase_homolog", "unassigned"]))],
            default=[],
        )
        result = api.list_filter_values(
            filter_type="call_class", conn=mock_conn)
        values = {r["value"] for r in result["results"]}
        assert "peptidase" in values
        assert all(r["source"] == "vocabulary" for r in result["results"])

    def test_rows_carry_applies_to(self, mock_conn):
        _trust_dispatch(
            mock_conn,
            [("ControlledVocabulary", self._vocab_rows(["peptidase"]))],
            default=[],
        )
        result = api.list_filter_values(
            filter_type="call_class", conn=mock_conn)
        row = result["results"][0]
        assert row["applies_to"] == ["Gene_has_merops_family"]

    # --- backlog 2.3: description parity with cluster_type -----------------
    # Property-level vocab text goes once on the envelope; rows carry the
    # per-value text from `value_descriptions` (KG B1) or nothing at all.

    def _vocab_rows_with_value_text(self):
        return [{
            "applies_to": "Gene_has_merops_family",
            "values": ["peptidase", "inhibitor"],
            "value_descriptions": [
                "peptidase: best hit is a catalytically live entry",
                "inhibitor: the family is an I-family",
            ],
            "description": "MEROPS call class",
            "sparse": "false",
        }]

    def test_property_description_is_on_the_envelope_once(self, mock_conn):
        _trust_dispatch(
            mock_conn,
            [("ControlledVocabulary", self._vocab_rows_with_value_text())],
            default=[],
        )
        result = api.list_filter_values(
            filter_type="call_class", conn=mock_conn)
        assert result["description"] == "MEROPS call class"
        assert all(r.get("description") != "MEROPS call class"
                   for r in result["results"])

    def test_rows_carry_the_per_value_text_without_the_value_prefix(
            self, mock_conn):
        _trust_dispatch(
            mock_conn,
            [("ControlledVocabulary", self._vocab_rows_with_value_text())],
            default=[],
        )
        result = api.list_filter_values(
            filter_type="call_class", conn=mock_conn)
        by_value = {r["value"]: r for r in result["results"]}
        assert by_value["peptidase"]["description"] == (
            "best hit is a catalytically live entry")
        assert by_value["inhibitor"]["description"] == (
            "the family is an I-family")

    def test_rows_without_per_value_text_have_no_description_key(
            self, mock_conn):
        """Vocab nodes that predate B1 (no `value_descriptions`) — the row
        key is absent, the same sparse rule cluster_type already follows."""
        _trust_dispatch(
            mock_conn,
            [("ControlledVocabulary", self._vocab_rows(["peptidase"]))],
            default=[],
        )
        result = api.list_filter_values(
            filter_type="call_class", conn=mock_conn)
        assert result["description"] == "MEROPS call class"
        assert "description" not in result["results"][0]

    def test_per_value_text_survives_multi_owner_aggregation(self, mock_conn):
        """`evidence` spans many edges; the first owner that carries text
        for a value wins, and a later owner without text never blanks it."""
        rows = [
            {"applies_to": "Gene_has_pfam", "values": ["curated"],
             "value_descriptions": None,
             "description": "pfam ladder", "sparse": "false"},
        ]
        calls = {"n": 0}

        def _exec(cypher, **params):
            if "ControlledVocabulary" not in cypher:
                return []
            calls["n"] += 1
            if params.get("applies_to") == "Gene_has_pfam":
                return rows
            return [{"applies_to": params["applies_to"], "values": ["curated"],
                     "value_descriptions": ["curated: a human said so"],
                     "description": "some ladder", "sparse": "false"}]

        mock_conn.execute_query.side_effect = _exec
        result = api.list_filter_values(filter_type="evidence", conn=mock_conn)
        row = next(r for r in result["results"] if r["value"] == "curated")
        assert row["description"] == "a human said so"
        assert calls["n"] > 1

    def test_missing_vocab_node_falls_back_to_the_pivot(self, mock_conn):
        def _exec(cypher, **params):
            if "ControlledVocabulary" in cypher:
                return []
            if "DISTINCT" in cypher:
                return [{"value": "peptidase"},
                        {"value": "nonpeptidase_homolog"}]
            return []

        mock_conn.execute_query.side_effect = _exec
        result = api.list_filter_values(
            filter_type="call_class", conn=mock_conn)
        values = {r["value"] for r in result["results"]}
        assert values == {"peptidase", "nonpeptidase_homolog"}
        assert all(r["source"] == "pivot" for r in result["results"])

    def test_pivot_fallback_emits_the_kg_side_warning(self, mock_conn):
        def _exec(cypher, **params):
            if "ControlledVocabulary" in cypher:
                return []
            if "DISTINCT" in cypher:
                return [{"value": "peptidase"}]
            return []

        mock_conn.execute_query.side_effect = _exec
        result = api.list_filter_values(
            filter_type="call_class", conn=mock_conn)
        joined = " ".join(result["warnings"])
        assert "No ControlledVocabulary entry for" in joined
        assert "KG-side fix pending" in joined

    def test_missing_vocab_is_never_a_hard_raise(self, mock_conn):
        mock_conn.execute_query.side_effect = lambda cypher, **p: []
        result = api.list_filter_values(
            filter_type="call_class", conn=mock_conn)
        assert result["results"] == []

    def test_trust_axes_filter_type_is_config_derived(self, mock_conn):
        result = api.list_filter_values(
            filter_type="trust_axes", conn=mock_conn)
        values = {r["value"] for r in result["results"]}
        assert {"sources", "evidence", "evidence_score", "tier"} <= values

    def test_link_kinds_filter_type_is_config_derived(self, mock_conn):
        result = api.list_filter_values(
            filter_type="link_kinds", conn=mock_conn)
        values = {r["value"] for r in result["results"]}
        assert values == {"composition", "membership", "router"}

    def test_ontology_scope_narrows_trust_axes(self, mock_conn):
        result = api.list_filter_values(
            filter_type="trust_axes", ontology="kegg", conn=mock_conn)
        values = {r["value"] for r in result["results"]}
        assert values == {"sources", "evidence"}

    def test_unknown_filter_type_still_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Unknown filter_type"):
            api.list_filter_values(filter_type="bogus", conn=mock_conn)


class TestGeneOverviewMeropsNcbifam:
    """gene_overview gains the protease / family-domain routing columns."""

    def _summary_row(self, **overrides):
        row = {
            "total_matching": 1,
            "by_organism": [{"item": _MIT1002, "count": 1}],
            "by_category": [{"item": "Unknown", "count": 1}],
            "by_annotation_type": [],
            "by_annotation_state": [],
            "has_expression": 0,
            "has_significant_expression": 0,
            "has_orthologs": 0,
            "has_clusters": 0,
            "has_derived_metrics": 0,
            "has_chemistry": 0,
            "has_discussed": 0,
            "has_ncbifam": 1,
            "by_merops_class": [{"item": "peptidase", "count": 1}],
            "not_found": [],
        }
        row.update(overrides)
        return [row]

    def _detail_rows(self):
        return [{
            "locus_tag": "MIT1002_03660",
            "gene_name": None, "product": None, "gene_category": "Unknown",
            "annotation_quality": 3, "organism_name": _MIT1002,
            "annotation_types": [], "expression_edge_count": 0,
            "significant_up_count": 0, "significant_down_count": 0,
            "closest_ortholog_group_size": 0, "closest_ortholog_genera": [],
            "cluster_membership_count": 0, "cluster_types": [],
            "numeric_metric_count": 0, "boolean_metric_count": 0,
            "categorical_metric_count": 0, "reaction_count": 0,
            "catalyzed_metabolite_count": 0, "tcdb_evidence_score_max": None,
            "transported_metabolite_count": 0,
            "transport_substrate_resolution": None,
            "discussed_in_publication_count": 0, "evidence_sources": [],
            "merops_classes": ["peptidase"],
            "ncbifam_family_count": 2,
            "merops_evidence_score_max": 1.0,
        }]

    def _run(self, mock_conn, summary_rows=None, detail_rows=None):
        summary_rows = summary_rows or self._summary_row()
        detail_rows = self._detail_rows() if detail_rows is None else detail_rows
        _trust_dispatch(
            mock_conn,
            [("not_found", summary_rows)],
            default=detail_rows,
        )
        return api.gene_overview(
            locus_tags=["MIT1002_03660"], conn=mock_conn)

    def test_rows_carry_merops_classes(self, mock_conn):
        result = self._run(mock_conn)
        assert result["results"][0]["merops_classes"] == ["peptidase"]

    def test_rows_carry_ncbifam_family_count(self, mock_conn):
        result = self._run(mock_conn)
        assert result["results"][0]["ncbifam_family_count"] == 2

    def test_merops_evidence_score_max_is_uncoalesced(self, mock_conn):
        """Twin of tcdb_evidence_score_max: null means no MEROPS call at all,
        0 means an uncorroborated one."""
        rows = self._detail_rows()
        rows[0]["merops_evidence_score_max"] = None
        result = self._run(mock_conn, detail_rows=rows)
        assert result["results"][0]["merops_evidence_score_max"] is None

    def test_envelope_by_merops_class(self, mock_conn):
        result = self._run(mock_conn)
        assert _freq_map(result["by_merops_class"]) == {"peptidase": 1}

    def test_envelope_has_ncbifam(self, mock_conn):
        result = self._run(mock_conn)
        assert result["has_ncbifam"] == 1


class TestGeneOverviewFamilyCounts(TestGeneOverviewMeropsNcbifam):
    """Backlog 3.4 — gene_overview rows carry tcdb_family_count /
    cazy_family_count; envelope carries has_tcdb / has_cazy (0 default)."""

    def _summary_row(self, **overrides):
        return super()._summary_row(has_tcdb=1, has_cazy=1, **overrides)

    def _detail_rows(self):
        rows = super()._detail_rows()
        rows[0]["tcdb_family_count"] = 7
        rows[0]["cazy_family_count"] = 4
        return rows

    def test_rows_carry_tcdb_family_count(self, mock_conn):
        result = self._run(mock_conn)
        assert result["results"][0]["tcdb_family_count"] == 7

    def test_rows_carry_cazy_family_count(self, mock_conn):
        result = self._run(mock_conn)
        assert result["results"][0]["cazy_family_count"] == 4

    def test_envelope_has_tcdb(self, mock_conn):
        result = self._run(mock_conn)
        assert result["has_tcdb"] == 1

    def test_envelope_has_cazy(self, mock_conn):
        result = self._run(mock_conn)
        assert result["has_cazy"] == 1

    def test_envelope_defaults_to_zero_when_summary_lacks_keys(self, mock_conn):
        rows = self._summary_row()
        del rows[0]["has_tcdb"]
        del rows[0]["has_cazy"]
        result = self._run(mock_conn, summary_rows=rows)
        assert result["has_tcdb"] == 0
        assert result["has_cazy"] == 0


# ===========================================================================
# PR 3b — annotation-trust surface, term side (RED)
#
# `ontology_term_details` (design §6, spec §7.5), `search_ontology` browse
# mode + multi-ontology lockstep paging (design §4 / §7, spec §7.4 / §13),
# and the aggregate-only trust rollups on `genes_by_ontology` (spec §13 (i)).
# ===========================================================================

from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG as _CFG3B

_BATCH6 = [
    "tcdb:3.A.1", "merops.family:S14", "interpro:IPR000362",
    "ncbifam:NF000812", "go:0006979", "bogus:xyz",
]


def _otd_link(rel, target_id, target_name="x", **props):
    return {"rel": rel, "target_id": target_id, "target_name": target_name,
            "props": props}


def _otd_row(term_id, label=None, *, not_found=False, name=None, level=None,
             level_kind=None, gene_count=10, organism_count=3,
             direct_gene_count=None, parents=(), children=(),
             children_total=None, links=(), extra=None, is_informative=True,
             genes_by_organism=None, organism_gene_count=None):
    """A builder row in the spec §7.5 shape (+ `labels`, flat compact props,
    and the verbose `properties` map so either projection strategy works)."""
    extra = dict(extra or {})
    row = {
        "term_id": term_id,
        "not_found": not_found,
        "labels": [label] if label else [],
        "name": name, "description": None,
        "level": level, "level_kind": level_kind,
        "is_informative": is_informative,
        "gene_count": gene_count, "organism_count": organism_count,
        "direct_gene_count": direct_gene_count,
        "parents": list(parents), "children": list(children),
        "children_total": (
            children_total if children_total is not None else len(children)),
        "links_total": len(links), "links_out": list(links),
    }
    if not_found:
        for k in ("name", "level", "gene_count", "organism_count"):
            row[k] = None
    row.update(extra)
    props = {k: v for k, v in extra.items() if v is not None}
    props.update({"id": term_id, "name": name, "level": level,
                  "gene_count": gene_count, "organism_count": organism_count})
    if direct_gene_count is not None:
        props["direct_gene_count"] = direct_gene_count
    row["properties"] = None if not_found else props
    if genes_by_organism is not None:
        row["genes_by_organism"] = genes_by_organism
    if organism_gene_count is not None:
        row["organism_gene_count"] = organism_gene_count
    return row


def _batch6_rows():
    """The verified §7.5 batch, shrunk to a handful of links per term."""
    tcdb_children = [{"id": f"tcdb:3.A.1.{i}", "name": f"fam {i}", "level": 3}
                     for i in range(50)]
    return [
        _otd_row("tcdb:3.A.1", "TcdbFamily", name="ABC superfamily", level=2,
                 level_kind="tc_family", gene_count=900, organism_count=45,
                 direct_gene_count=120,
                 parents=[{"id": "tcdb:3.A", "name": "P-P-bond", "level": 1}],
                 children=tcdb_children, children_total=55,
                 links=[
                     _otd_link("Tcdb_family_has_pfam_domain", "pfam:PF00005",
                               "ABC_tran", curated_tcids=["3.A.1.1.1"]),
                     _otd_link("Tcdb_family_has_pfam_domain", "pfam:PF00664",
                               "ABC_membrane", curated_tcids=["3.A.1.2.1"]),
                     _otd_link("Tcdb_family_involved_in_biological_process",
                               "go:0055085", "transmembrane transport",
                               curated_tcids=["3.A.1.1.1"]),
                 ],
                 extra={"tcdb_id": "3.A.1", "tc_class_id": "3.A",
                        "member_count": 55, "superfamily": "ABC",
                        "metabolite_count": 40}),
        _otd_row("merops.family:S14", "MeropsFamily", name="S14", level=1,
                 gene_count=100, organism_count=44, direct_gene_count=100,
                 parents=[{"id": "merops.clan:SK", "name": "SK", "level": 0}],
                 links=[_otd_link("Merops_family_has_pfam_domain",
                                  "pfam:PF00574", "CLP_protease",
                                  member_id_count=5)],
                 extra={"merops_id": "S14", "family_class": "S",
                        "catalytic_type": "Serine",
                        "peptidase_gene_count": 90}),
        _otd_row("interpro:IPR000362", "InterproEntry",
                 name="Fumarate lyase family", level=0, gene_count=60,
                 organism_count=40, direct_gene_count=10,
                 children=[{"id": f"interpro:IPR00{i}", "name": f"c{i}",
                            "level": 1} for i in range(4)],
                 links=[_otd_link("Interpro_entry_related_to_ec_number",
                                  f"ec:4.3.2.{i}", f"EC {i}")
                        for i in range(5)],
                 extra={"interpro_id": "IPR000362",
                        "interpro_type": "FAMILY", "member_count": 4}),
        _otd_row("ncbifam:NF000812", "NcbifamFamily", name="NF000812",
                 level=0, gene_count=5, organism_count=5,
                 extra={"ncbifam_id": "NF000812", "family_type": "equivalog",
                        "gene_symbol": None}),
        _otd_row("go:0006979", "BiologicalProcess",
                 name="response to oxidative stress", level=3,
                 level_kind="depth", gene_count=1050, organism_count=42,
                 direct_gene_count=860,
                 parents=[{"id": "go:0006950", "name": "response to stress",
                           "level": 2}],
                 children=[{"id": f"go:000{i}", "name": f"c{i}", "level": 4}
                           for i in range(3)],
                 extra={"member_count": None, "go_id": None}),
        _otd_row("bogus:xyz", None, not_found=True),
    ]


def _is_resolve(cypher):
    """The organism-resolution query every organism-taking api runs first."""
    return "OrganismTaxon" in cypher and "organisms" in cypher


def _otd_run(mock_conn, rows=None, term_ids=None, **kwargs):
    rows = _batch6_rows() if rows is None else rows

    def _exec(cypher, **params):
        if _is_resolve(cypher):
            # Echo the resolver: 'MED4' and the full name both resolve.
            org = params["organism"]
            return [{"organisms": [
                org if org.startswith("Prochlorococcus") else f"Prochlorococcus {org}"]}]
        return rows

    mock_conn.execute_query.side_effect = _exec
    return api.ontology_term_details(
        term_ids=list(_BATCH6) if term_ids is None else term_ids,
        conn=mock_conn, **kwargs)


def _by(rollup, key):
    return {e[key]: e["count"] for e in rollup}


class TestOntologyTermDetailsApi:
    """Batch, cross-ontology, rows in input order, `not_found[]`."""

    def test_importable_from_package(self):
        from multiomics_explorer import ontology_term_details as fn
        assert fn is api.ontology_term_details

    def test_returns_dict(self, mock_conn):
        assert isinstance(_otd_run(mock_conn), dict)

    def test_empty_term_ids_raises_before_any_query(self, mock_conn):
        with pytest.raises(ValueError, match="term_ids"):
            api.ontology_term_details(term_ids=[], conn=mock_conn)
        assert mock_conn.execute_query.call_count == 0

    def test_unknown_link_kind_raises_before_any_query(self, mock_conn):
        with pytest.raises(ValueError, match="link_kind"):
            api.ontology_term_details(
                term_ids=["tcdb:3.A.1"], link_kinds=["sideways"],
                conn=mock_conn)
        assert mock_conn.execute_query.call_count == 0

    def test_term_ids_forwarded_as_param(self, mock_conn):
        _otd_run(mock_conn)
        assert mock_conn.execute_query.call_args.kwargs["term_ids"] == _BATCH6

    def test_rows_in_input_order(self, mock_conn):
        result = _otd_run(mock_conn)
        assert [r["term_id"] for r in result["results"]] == _BATCH6[:5]

    def test_not_found_lists_missing_ids(self, mock_conn):
        result = _otd_run(mock_conn)
        assert result["not_found"] == ["bogus:xyz"]
        assert "bogus:xyz" not in {r["term_id"] for r in result["results"]}

    def test_counts(self, mock_conn):
        result = _otd_run(mock_conn)
        assert result["total_matching"] == 5
        assert result["returned"] == 5
        assert result["offset"] == 0
        assert result["truncated"] is False

    @pytest.mark.parametrize("key", [
        "total_matching", "returned", "offset", "truncated", "not_found",
        "by_ontology", "links_out_total", "by_link_kind", "warnings",
        "results",
    ])
    def test_envelope_key_present(self, mock_conn, key):
        assert key in _otd_run(mock_conn)

    def test_warnings_is_a_list(self, mock_conn):
        assert isinstance(_otd_run(mock_conn)["warnings"], list)

    # --- ontology / label derivation ---

    def test_ontology_derived_from_node_label(self, mock_conn):
        result = _otd_run(mock_conn)
        got = {r["term_id"]: r["ontology"] for r in result["results"]}
        assert got == {
            "tcdb:3.A.1": "tcdb", "merops.family:S14": "merops",
            "interpro:IPR000362": "interpro", "ncbifam:NF000812": "ncbifam",
            "go:0006979": "go_bp",
        }

    def test_label_column_is_the_node_label(self, mock_conn):
        result = _otd_run(mock_conn)
        assert result["results"][0]["label"] == "TcdbFamily"

    def test_pfam_clan_maps_to_pfam(self, mock_conn):
        rows = [_otd_row("pfam.clan:CL0023", "PfamClan", name="P-loop_NTPase",
                         level=0, extra={"short_name": "P-loop_NTPase"})]
        result = _otd_run(mock_conn, rows=rows, term_ids=["pfam.clan:CL0023"])
        assert result["results"][0]["ontology"] == "pfam"
        assert result["results"][0]["label"] == "PfamClan"

    def test_by_ontology_rollup(self, mock_conn):
        result = _otd_run(mock_conn)
        assert _by(result["by_ontology"], "ontology") == {
            "tcdb": 1, "merops": 1, "interpro": 1, "ncbifam": 1, "go_bp": 1}

    # --- compact columns ---

    @pytest.mark.parametrize("col", [
        "term_id", "ontology", "label", "name", "description", "level",
        "level_kind", "is_informative", "gene_count", "organism_count",
        "parents", "children", "children_total", "children_truncated",
        "links_out",
    ])
    def test_compact_column_present(self, mock_conn, col):
        row = _otd_run(mock_conn)["results"][0]
        assert col in row

    def test_go_row_matches_the_verified_batch(self, mock_conn):
        row = [r for r in _otd_run(mock_conn)["results"]
               if r["term_id"] == "go:0006979"][0]
        assert row["level"] == 3
        assert row["gene_count"] == 1050
        assert row["organism_count"] == 42
        assert len(row["parents"]) == 1
        assert len(row["children"]) == 3
        assert row["links_out"] == []

    def test_term_details_compact_props_projected(self, mock_conn):
        rows = {r["term_id"]: r for r in _otd_run(mock_conn)["results"]}
        assert rows["tcdb:3.A.1"]["tcdb_id"] == "3.A.1"
        assert rows["tcdb:3.A.1"]["tc_class_id"] == "3.A"
        assert rows["merops.family:S14"]["family_class"] == "S"
        assert rows["merops.family:S14"]["catalytic_type"] == "Serine"
        assert rows["interpro:IPR000362"]["interpro_type"] == "FAMILY"
        assert rows["ncbifam:NF000812"]["family_type"] == "equivalog"

    def test_strip_rule_missing_prop_is_absent_not_null(self, mock_conn):
        """Spec §13: GO nodes carry direct_gene_count only — no member_count,
        no go_id. A missing term_details_compact prop is absent."""
        rows = {r["term_id"]: r for r in _otd_run(mock_conn)["results"]}
        go = rows["go:0006979"]
        assert go["direct_gene_count"] == 860
        assert "member_count" not in go
        assert "go_id" not in go

    def test_strip_rule_direct_gene_count_absent_on_flat_label(self, mock_conn):
        rows = {r["term_id"]: r for r in _otd_run(mock_conn)["results"]}
        assert "direct_gene_count" not in rows["ncbifam:NF000812"]

    def test_strip_rule_does_not_leak_other_ontologies_props(self, mock_conn):
        rows = {r["term_id"]: r for r in _otd_run(mock_conn)["results"]}
        assert "tcdb_id" not in rows["merops.family:S14"]
        assert "family_class" not in rows["tcdb:3.A.1"]

    def test_owned_but_null_prop_survives(self, mock_conn):
        """ncbifam owns gene_symbol; null there is information."""
        rows = {r["term_id"]: r for r in _otd_run(mock_conn)["results"]}
        assert "gene_symbol" in rows["ncbifam:NF000812"]
        assert rows["ncbifam:NF000812"]["gene_symbol"] is None

    # --- children cap ---

    def test_children_truncated_flag(self, mock_conn):
        rows = {r["term_id"]: r for r in _otd_run(mock_conn)["results"]}
        assert rows["tcdb:3.A.1"]["children_total"] == 55
        assert len(rows["tcdb:3.A.1"]["children"]) == 50
        assert rows["tcdb:3.A.1"]["children_truncated"] is True
        assert rows["interpro:IPR000362"]["children_truncated"] is False

    def test_parent_child_entries_carry_id_name_level(self, mock_conn):
        rows = {r["term_id"]: r for r in _otd_run(mock_conn)["results"]}
        assert set(rows["tcdb:3.A.1"]["parents"][0]) == {"id", "name", "level"}
        assert set(rows["tcdb:3.A.1"]["children"][0]) == {"id", "name", "level"}

    # --- links_out ---

    def test_compact_link_keys(self, mock_conn):
        rows = {r["term_id"]: r for r in _otd_run(mock_conn)["results"]}
        link = rows["tcdb:3.A.1"]["links_out"][0]
        assert set(link) == {
            "rel", "link_kind", "target_id", "target_ontology", "target_name"}

    def test_link_kind_and_target_ontology_derived_from_registry(self, mock_conn):
        rows = {r["term_id"]: r for r in _otd_run(mock_conn)["results"]}
        tcdb_links = {(lk["rel"], lk["link_kind"], lk["target_ontology"])
                      for lk in rows["tcdb:3.A.1"]["links_out"]}
        assert ("Tcdb_family_has_pfam_domain", "composition", "pfam") in tcdb_links
        assert ("Tcdb_family_involved_in_biological_process", "composition",
                "go_bp") in tcdb_links
        s14 = rows["merops.family:S14"]["links_out"][0]
        assert (s14["link_kind"], s14["target_ontology"]) == ("composition", "pfam")
        ipr = rows["interpro:IPR000362"]["links_out"][0]
        assert (ipr["link_kind"], ipr["target_ontology"]) == ("router", "ec")

    def test_links_out_total_and_by_link_kind(self, mock_conn):
        result = _otd_run(mock_conn)
        assert result["links_out_total"] == 9
        assert _by(result["by_link_kind"], "link_kind") == {
            "composition": 4, "router": 5}

    def test_link_kinds_filter_is_applied_in_the_query(self, mock_conn):
        _otd_run(mock_conn, link_kinds=["router"])
        cypher = mock_conn.execute_query.call_args.args[0]
        assert "Interpro_entry_related_to_ec_number" in cypher
        assert "Tcdb_family_has_pfam_domain" not in cypher

    def test_link_kinds_none_keeps_every_bridge_in_the_query(self, mock_conn):
        _otd_run(mock_conn)
        cypher = mock_conn.execute_query.call_args.args[0]
        assert "Tcdb_family_has_pfam_domain" in cypher
        assert "Kegg_term_in_brite_category" in cypher

    # --- verbose ---

    def test_compact_has_no_properties_or_genes_by_organism(self, mock_conn):
        row = _otd_run(mock_conn)["results"][0]
        assert "properties" not in row
        assert "genes_by_organism" not in row

    def test_verbose_adds_properties_map(self, mock_conn):
        row = _otd_run(mock_conn, verbose=True)["results"][0]
        assert row["properties"]["id"] == "tcdb:3.A.1"

    def test_verbose_adds_genes_by_organism(self, mock_conn):
        rows = _batch6_rows()
        for r in rows:
            r["genes_by_organism"] = [
                {"organism": "Prochlorococcus MED4", "gene_count": 3}]
        row = _otd_run(mock_conn, rows=rows, verbose=True)["results"][0]
        assert row["genes_by_organism"] == [
            {"organism": "Prochlorococcus MED4", "gene_count": 3}]

    def test_verbose_link_props(self, mock_conn):
        rows = {r["term_id"]: r
                for r in _otd_run(mock_conn, verbose=True)["results"]}
        assert rows["tcdb:3.A.1"]["links_out"][0]["props"]["curated_tcids"] == [
            "3.A.1.1.1"]
        assert rows["merops.family:S14"]["links_out"][0]["props"][
            "member_id_count"] == 5

    def test_router_ambiguous_true_when_out_degree_above_one(self, mock_conn):
        rows = {r["term_id"]: r
                for r in _otd_run(mock_conn, verbose=True)["results"]}
        for link in rows["interpro:IPR000362"]["links_out"]:
            assert link["props"]["router_ambiguous"] is True

    def test_router_ambiguous_false_for_single_family_router(self, mock_conn):
        rows = [_otd_row(
            "interpro:IPR999999", "InterproEntry", name="x", level=0,
            links=[_otd_link("Interpro_entry_related_to_ec_number",
                             "ec:1.1.1.1")],
            extra={"interpro_id": "IPR999999", "interpro_type": "FAMILY"})]
        result = _otd_run(mock_conn, rows=rows,
                          term_ids=["interpro:IPR999999"], verbose=True)
        assert result["results"][0]["links_out"][0]["props"][
            "router_ambiguous"] is False

    def test_router_ambiguous_true_when_type_is_not_family(self, mock_conn):
        rows = [_otd_row(
            "interpro:IPR999998", "InterproEntry", name="x", level=0,
            links=[_otd_link("Interpro_entry_related_to_ec_number",
                             "ec:1.1.1.1")],
            extra={"interpro_id": "IPR999998", "interpro_type": "DOMAIN"})]
        result = _otd_run(mock_conn, rows=rows,
                          term_ids=["interpro:IPR999998"], verbose=True)
        assert result["results"][0]["links_out"][0]["props"][
            "router_ambiguous"] is True

    def test_router_ambiguous_computed_api_side_ignores_builder_column(
            self, mock_conn):
        """The api derives `router_ambiguous` from router out-degree +
        `interpro_type`; a stray builder column must never leak through."""
        rows = [_otd_row(
            "interpro:IPR999997", "InterproEntry", name="x", level=0,
            links=[_otd_link("Interpro_entry_related_to_ec_number",
                             "ec:1.1.1.1")],
            extra={"interpro_id": "IPR999997", "interpro_type": "FAMILY"})]
        rows[0]["router_ambiguous"] = True  # contradicts the api computation
        result = _otd_run(mock_conn, rows=rows,
                          term_ids=["interpro:IPR999997"], verbose=True)
        row = result["results"][0]
        assert row["links_out"][0]["props"]["router_ambiguous"] is False
        assert "router_ambiguous" not in row

    def test_router_ambiguous_not_on_composition_links(self, mock_conn):
        rows = {r["term_id"]: r
                for r in _otd_run(mock_conn, verbose=True)["results"]}
        for link in rows["tcdb:3.A.1"]["links_out"]:
            assert "router_ambiguous" not in link["props"]

    def test_verbose_flag_forwarded_to_builder(self, mock_conn):
        _otd_run(mock_conn, verbose=True)
        cypher = mock_conn.execute_query.call_args.args[0]
        assert "genes_by_organism" in cypher

    # --- organism scope ---

    def test_organism_forwarded_to_query(self, mock_conn):
        _otd_run(mock_conn, organism="Prochlorococcus MED4")
        params = mock_conn.execute_query.call_args.kwargs
        assert "Prochlorococcus MED4" in params.values()

    def test_organism_scope_adds_organism_gene_count(self, mock_conn):
        rows = _batch6_rows()
        for r in rows:
            if not r["not_found"]:
                r["organism_gene_count"] = 7
        result = _otd_run(mock_conn, rows=rows,
                          organism="Prochlorococcus MED4")
        assert result["results"][0]["organism_gene_count"] == 7

    def test_no_organism_no_organism_gene_count(self, mock_conn):
        row = _otd_run(mock_conn)["results"][0]
        assert "organism_gene_count" not in row

    # --- pagination over the row list ---

    def test_limit_and_offset_paginate_found_rows(self, mock_conn):
        result = _otd_run(mock_conn, limit=2, offset=1)
        assert [r["term_id"] for r in result["results"]] == [
            "merops.family:S14", "interpro:IPR000362"]
        assert result["returned"] == 2
        assert result["offset"] == 1
        assert result["truncated"] is True
        assert result["total_matching"] == 5
        assert result["not_found"] == ["bogus:xyz"]

    def test_offset_beyond_found_rows(self, mock_conn):
        result = _otd_run(mock_conn, offset=50)
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is False
        assert result["total_matching"] == 5

    def test_rollups_describe_the_full_batch_not_the_page(self, mock_conn):
        result = _otd_run(mock_conn, limit=1)
        assert result["links_out_total"] == 9
        assert sum(_by(result["by_ontology"], "ontology").values()) == 5

    def test_all_missing(self, mock_conn):
        rows = [_otd_row("a:1", None, not_found=True),
                _otd_row("b:2", None, not_found=True)]
        result = _otd_run(mock_conn, rows=rows, term_ids=["a:1", "b:2"])
        assert result["not_found"] == ["a:1", "b:2"]
        assert result["results"] == []
        assert result["total_matching"] == 0
        assert result["by_ontology"] == []
        assert result["links_out_total"] == 0


# ---------------------------------------------------------------------------
# search_ontology — browse mode + multi-ontology (PR 3b)
# ---------------------------------------------------------------------------

def _so_summary(total_entries=100, total_matching=1, score_max=5.0,
                score_median=3.0, by_level=None):
    return {
        "total_entries": total_entries, "total_matching": total_matching,
        "score_max": score_max, "score_median": score_median,
        "by_level": by_level if by_level is not None else [],
    }


def _so_row(id_, name="x", score=5.0, level=1, **extra):
    row = {"id": id_, "name": name, "score": score, "level": level,
           "tree": None, "tree_code": None, "is_informative": True,
           "gene_count": 10, "organism_count": 4}
    row.update(extra)
    return row


def _so_dispatch(mock_conn, per_ontology):
    """Route by ontology: the fulltext index name (search) or the label
    (browse) identifies the ontology; `total_entries` marks the summary.
    Returns the list of (cypher, params) calls for assertions."""
    calls = []

    def _exec(cypher, **params):
        calls.append((cypher, params))
        if _is_resolve(cypher):
            org = params["organism"]
            return [{"organisms": [
                org if org.startswith("Prochlorococcus") else f"Prochlorococcus {org}"]}]
        for key, (summary, rows) in per_ontology.items():
            cfg = _CFG3B[key]
            labels = [cfg["label"]] + (
                [cfg["parent_label"]] if "parent_label" in cfg else [])
            hit = cfg["fulltext_index"] in cypher or any(
                f"t:{lab}" in cypher for lab in labels)
            if hit:
                return [summary] if "total_entries" in cypher else rows
        if "total_entries" in cypher:
            return [_so_summary(total_entries=0, total_matching=0,
                                score_max=None, score_median=None)]
        return []

    mock_conn.execute_query.side_effect = _exec
    return calls


def _is_detail(cypher):
    return "total_entries" not in cypher and not _is_resolve(cypher)


class TestSearchOntologyBrowseApi:
    """Spec §7.4 / §13: `search_text` None / '' -> browse."""

    def _merops(self, mock_conn, total=60, rows=None, by_level=None):
        rows = rows if rows is not None else [
            _so_row("merops.family:S33", "S33", score=None, gene_count=412),
            _so_row("merops.family:S09", "S09", score=None, gene_count=298),
        ]
        return _so_dispatch(mock_conn, {"merops": (
            _so_summary(total_entries=300, total_matching=total,
                        score_max=None, score_median=None,
                        by_level=by_level if by_level is not None else [
                            {"level": 1, "count": total}]),
            rows)})

    def test_no_search_text_is_browse(self, mock_conn):
        calls = self._merops(mock_conn)
        result = api.search_ontology(ontology="merops", level=1, conn=mock_conn)
        assert result["mode"] == "browse"
        assert all("db.index.fulltext" not in c for c, _ in calls)

    def test_empty_search_text_is_browse_not_a_raise(self, mock_conn):
        self._merops(mock_conn)
        result = api.search_ontology("", "merops", level=1, conn=mock_conn)
        assert result["mode"] == "browse"

    def test_whitespace_search_text_is_browse(self, mock_conn):
        self._merops(mock_conn)
        result = api.search_ontology("   ", "merops", level=1, conn=mock_conn)
        assert result["mode"] == "browse"

    def test_search_mode_when_text_given(self, mock_conn):
        calls = _so_dispatch(mock_conn, {"merops": (
            _so_summary(), [_so_row("merops.family:S33")])})
        result = api.search_ontology("protease", "merops", conn=mock_conn)
        assert result["mode"] == "search"
        assert any("db.index.fulltext" in c for c, _ in calls)

    def test_browse_rows_carry_null_score(self, mock_conn):
        self._merops(mock_conn)
        result = api.search_ontology(ontology="merops", level=1, conn=mock_conn)
        assert result["results"][0]["score"] is None
        assert result["score_max"] is None
        assert result["score_median"] is None

    def test_browse_rows_keep_builder_order(self, mock_conn):
        self._merops(mock_conn)
        result = api.search_ontology(ontology="merops", level=1, conn=mock_conn)
        assert result["results"][0]["id"] == "merops.family:S33"
        assert result["results"][0]["gene_count"] == 412

    def test_browse_rows_carry_ontology_type(self, mock_conn):
        self._merops(mock_conn)
        result = api.search_ontology(ontology="merops", level=1, conn=mock_conn)
        assert all(r["ontology_type"] == "merops" for r in result["results"])

    def test_browse_by_level_over_full_match(self, mock_conn):
        self._merops(mock_conn, by_level=[{"level": 1, "count": 60}])
        result = api.search_ontology(ontology="merops", level=1, conn=mock_conn)
        assert result["by_level"] == [{"level": 1, "count": 60}]

    def test_search_mode_by_level_is_empty(self, mock_conn):
        _so_dispatch(mock_conn, {"merops": (
            _so_summary(), [_so_row("merops.family:S33")])})
        result = api.search_ontology("protease", "merops", conn=mock_conn)
        assert result["by_level"] == []

    def test_level_forwarded(self, mock_conn):
        calls = self._merops(mock_conn)
        api.search_ontology(ontology="merops", level=1, conn=mock_conn)
        assert all(p.get("level") == 1 for _, p in calls)

    def test_min_gene_count_forwarded(self, mock_conn):
        calls = self._merops(mock_conn)
        api.search_ontology(ontology="merops", min_gene_count=5, conn=mock_conn)
        assert all(p.get("min_gene_count") == 5 for _, p in calls)

    def test_organism_forwarded(self, mock_conn):
        calls = self._merops(mock_conn)
        api.search_ontology(
            ontology="merops", organism="Prochlorococcus MED4", conn=mock_conn)
        assert all("Prochlorococcus MED4" in p.values() for _, p in calls)
        assert all("org_gene_count" in c for c, _ in calls if _is_detail(c))

    def test_organism_scope_rows_carry_organism_gene_count(self, mock_conn):
        self._merops(mock_conn, rows=[
            _so_row("merops.family:S33", score=None, organism_gene_count=9)])
        result = api.search_ontology(
            ontology="merops", organism="Prochlorococcus MED4", conn=mock_conn)
        assert result["results"][0]["organism_gene_count"] == 9

    def test_no_organism_no_organism_gene_count(self, mock_conn):
        self._merops(mock_conn)
        result = api.search_ontology(ontology="merops", conn=mock_conn)
        assert "organism_gene_count" not in result["results"][0]

    def test_flat_envelope_keys_survive(self, mock_conn):
        self._merops(mock_conn)
        result = api.search_ontology(ontology="merops", level=1, conn=mock_conn)
        for key in ("total_entries", "total_matching", "score_max",
                    "score_median", "returned", "offset", "truncated"):
            assert key in result, key
        assert result["total_entries"] == 300
        assert result["total_matching"] == 60
        assert result["returned"] == 2
        assert result["truncated"] is True

    @pytest.mark.parametrize("key", [
        "mode", "by_ontology", "by_level", "skipped_ontologies", "warnings",
    ])
    def test_new_envelope_key_on_single_ontology_call(self, mock_conn, key):
        self._merops(mock_conn)
        assert key in api.search_ontology(ontology="merops", conn=mock_conn)

    # --- auto-warning: browse truncated without narrowing ---

    def test_browse_truncated_without_narrowing_warns(self, mock_conn):
        self._merops(mock_conn, total=60)
        result = api.search_ontology(ontology="merops", limit=2, conn=mock_conn)
        assert result["truncated"] is True
        assert result["warnings"], "expected a browse-truncation warning"
        assert "browse" in " ".join(result["warnings"]).lower()

    @pytest.mark.parametrize("narrowing", [
        {"level": 1}, {"min_gene_count": 5},
        {"organism": "Prochlorococcus MED4"},
    ])
    def test_browse_truncated_with_narrowing_does_not_warn(
            self, mock_conn, narrowing):
        self._merops(mock_conn, total=60)
        result = api.search_ontology(
            ontology="merops", limit=2, conn=mock_conn, **narrowing)
        assert result["truncated"] is True
        assert not [w for w in result["warnings"] if "browse" in w.lower()]

    def test_interpro_facet_is_narrowing(self, mock_conn):
        _so_dispatch(mock_conn, {"interpro": (
            _so_summary(total_matching=60, score_max=None, score_median=None),
            [_so_row("interpro:IPR027417", score=None,
                     interpro_type="HOMOLOGOUS_SUPERFAMILY")])})
        result = api.search_ontology(
            ontology="interpro", interpro_type="HOMOLOGOUS_SUPERFAMILY",
            limit=1, conn=mock_conn)
        assert result["truncated"] is True
        assert not [w for w in result["warnings"] if "browse" in w.lower()]

    def test_browse_not_truncated_does_not_warn(self, mock_conn):
        self._merops(mock_conn, total=2)
        result = api.search_ontology(ontology="merops", limit=10, conn=mock_conn)
        assert result["truncated"] is False
        assert result["warnings"] == []

    def test_search_mode_never_emits_browse_warning(self, mock_conn):
        _so_dispatch(mock_conn, {"merops": (
            _so_summary(total_matching=60), [_so_row("merops.family:S33")])})
        result = api.search_ontology(
            "protease", "merops", limit=1, conn=mock_conn)
        assert result["truncated"] is True
        assert not [w for w in result["warnings"] if "browse" in w.lower()]

    def test_summary_browse_runs_no_detail_query(self, mock_conn):
        calls = self._merops(mock_conn)
        result = api.search_ontology(
            ontology="merops", level=1, summary=True, conn=mock_conn)
        assert result["results"] == []
        assert result["mode"] == "browse"
        assert all(not _is_detail(c) for c, _ in calls)

    def test_pfam_browse_hits_both_labels(self, mock_conn):
        calls = _so_dispatch(mock_conn, {"pfam": (
            _so_summary(score_max=None, score_median=None),
            [_so_row("pfam.clan:CL0023", score=None, level=0)])})
        result = api.search_ontology(ontology="pfam", conn=mock_conn)
        assert result["mode"] == "browse"
        assert any("t:PfamClan" in c for c, _ in calls)


class TestSearchOntologyMultiApi:
    """Design §4 / §7: `ontology: str | list[str] | None`, api-layer fan-out,
    config-order rows, lockstep per-ontology paging."""

    def _go_tcdb(self, mock_conn, go_total=40, tcdb_total=3):
        return _so_dispatch(mock_conn, {
            "go_bp": (
                _so_summary(total_entries=1000, total_matching=go_total,
                            score_max=9.0, score_median=4.0),
                [_so_row(f"go:00{i}", score=9.0 - i, level=3)
                 for i in range(5)]),
            "tcdb": (
                _so_summary(total_entries=500, total_matching=tcdb_total,
                            score_max=6.0, score_median=5.0),
                [_so_row(f"tcdb:3.A.{i}", score=6.0 - i, level=2)
                 for i in range(3)]),
        })

    def test_list_is_accepted(self, mock_conn):
        self._go_tcdb(mock_conn)
        result = api.search_ontology(
            "transport", ["go_bp", "tcdb"], limit=5, conn=mock_conn)
        assert isinstance(result, dict)

    def test_rows_ordered_by_ontology_config_order_then_score(self, mock_conn):
        self._go_tcdb(mock_conn)
        result = api.search_ontology(
            "transport", ["tcdb", "go_bp"], limit=5, conn=mock_conn)
        types = [r["ontology_type"] for r in result["results"]]
        assert types == ["go_bp"] * 5 + ["tcdb"] * 3
        go_scores = [r["score"] for r in result["results"] if r["ontology_type"] == "go_bp"]
        assert go_scores == sorted(go_scores, reverse=True)

    def test_returned_is_bounded_by_limit_times_n(self, mock_conn):
        self._go_tcdb(mock_conn)
        result = api.search_ontology(
            "transport", ["go_bp", "tcdb"], limit=5, conn=mock_conn)
        assert result["returned"] == 8
        assert result["returned"] <= 5 * 2

    def test_limit_and_offset_apply_per_ontology(self, mock_conn):
        """Lockstep paging: every ontology's detail query gets the same
        LIMIT / SKIP — never a global slice."""
        calls = self._go_tcdb(mock_conn)
        api.search_ontology(
            "transport", ["go_bp", "tcdb"], limit=5, offset=5, conn=mock_conn)
        detail = [p for c, p in calls if _is_detail(c)]
        assert len(detail) == 2
        assert all(p["limit"] == 5 for p in detail)
        assert all(p["offset"] == 5 for p in detail)

    def test_one_summary_and_one_detail_per_ontology(self, mock_conn):
        calls = self._go_tcdb(mock_conn)
        api.search_ontology("transport", ["go_bp", "tcdb"], limit=5, conn=mock_conn)
        assert len(calls) == 4

    def test_by_ontology_shape_and_order(self, mock_conn):
        self._go_tcdb(mock_conn)
        result = api.search_ontology(
            "transport", ["tcdb", "go_bp"], limit=5, conn=mock_conn)
        assert [e["ontology"] for e in result["by_ontology"]] == ["go_bp", "tcdb"]
        for entry in result["by_ontology"]:
            assert set(entry) == {
                "ontology", "total_entries", "total_matching", "score_max",
                "returned", "truncated"}

    def test_by_ontology_truncation_flags(self, mock_conn):
        self._go_tcdb(mock_conn, go_total=40, tcdb_total=3)
        result = api.search_ontology(
            "transport", ["go_bp", "tcdb"], limit=5, conn=mock_conn)
        by = {e["ontology"]: e for e in result["by_ontology"]}
        assert by["go_bp"]["truncated"] is True
        assert by["go_bp"]["returned"] == 5
        assert by["go_bp"]["total_matching"] == 40
        assert by["tcdb"]["truncated"] is False
        assert by["tcdb"]["returned"] == 3

    def test_flat_keys_are_sums_and_max_across_ontologies(self, mock_conn):
        self._go_tcdb(mock_conn)
        result = api.search_ontology(
            "transport", ["go_bp", "tcdb"], limit=5, conn=mock_conn)
        assert result["total_entries"] == 1500
        assert result["total_matching"] == 43
        assert result["score_max"] == 9.0
        assert result["returned"] == 8
        assert result["truncated"] is True
        assert result["offset"] == 0

    def test_mode_is_search_with_text(self, mock_conn):
        self._go_tcdb(mock_conn)
        result = api.search_ontology(
            "transport", ["go_bp", "tcdb"], limit=5, conn=mock_conn)
        assert result["mode"] == "search"
        assert result["skipped_ontologies"] == []
        assert result["warnings"] == []

    def test_multi_browse(self, mock_conn):
        calls = _so_dispatch(mock_conn, {
            "merops": (_so_summary(score_max=None, score_median=None,
                                   by_level=[{"level": 1, "count": 1}]),
                       [_so_row("merops.family:S33", score=None)]),
            "tcdb": (_so_summary(score_max=None, score_median=None,
                                 by_level=[{"level": 2, "count": 1}]),
                     [_so_row("tcdb:3.A.1", score=None, level=2)]),
        })
        result = api.search_ontology(
            ontology=["tcdb", "merops"], conn=mock_conn)
        assert result["mode"] == "browse"
        assert all("db.index.fulltext" not in c for c, _ in calls)
        assert [r["ontology_type"] for r in result["results"]] == ["tcdb", "merops"]
        assert result["score_max"] is None
        # by_level is single-ontology only (level scales differ across
        # ontologies): multi-ontology browse emits [] (backlog 2.5).
        assert result["by_level"] == []

    def test_none_means_all_17_in_config_order(self, mock_conn):
        calls = _so_dispatch(mock_conn, {})
        result = api.search_ontology("transport", None, limit=5, conn=mock_conn)
        summaries = [c for c, _ in calls if not _is_detail(c)]
        assert len(summaries) == 17
        assert [e["ontology"] for e in result["by_ontology"]] == list(_CFG3B)

    def test_ontology_kwarg_defaults_to_all(self, mock_conn):
        calls = _so_dispatch(mock_conn, {})
        api.search_ontology("transport", limit=5, conn=mock_conn)
        assert len([c for c, _ in calls if not _is_detail(c)]) == 17

    def test_single_str_still_works_and_carries_ontology_type(self, mock_conn):
        self._go_tcdb(mock_conn)
        result = api.search_ontology("transport", "tcdb", limit=5, conn=mock_conn)
        assert result["returned"] == 3
        assert all(r["ontology_type"] == "tcdb" for r in result["results"])
        assert [e["ontology"] for e in result["by_ontology"]] == ["tcdb"]
        assert result["total_entries"] == 500

    def test_single_ontology_summary_still_one_query(self, mock_conn):
        calls = self._go_tcdb(mock_conn)
        result = api.search_ontology(
            "transport", "tcdb", summary=True, conn=mock_conn)
        assert result["results"] == []
        assert len(calls) == 1

    def test_duplicates_in_list_are_collapsed(self, mock_conn):
        calls = self._go_tcdb(mock_conn)
        result = api.search_ontology(
            "transport", ["tcdb", "tcdb"], limit=5, conn=mock_conn)
        assert [e["ontology"] for e in result["by_ontology"]] == ["tcdb"]
        assert len(calls) == 2

    def test_unknown_name_in_list_raises(self, mock_conn):
        with pytest.raises(ValueError, match="Invalid ontology"):
            api.search_ontology(
                "transport", ["go_bp", "nope"], conn=mock_conn)
        assert mock_conn.execute_query.call_count == 0

    def test_empty_list_means_all(self, mock_conn):
        calls = _so_dispatch(mock_conn, {})
        api.search_ontology("transport", [], limit=5, conn=mock_conn)
        assert len([c for c, _ in calls if not _is_detail(c)]) == 17

    # --- facet skip/raise matrix ---

    def test_facet_owner_absent_raises(self, mock_conn):
        with pytest.raises(ValueError, match="interpro_type"):
            api.search_ontology(
                "kinase", ["kegg", "tcdb"], interpro_type="DOMAIN",
                conn=mock_conn)
        assert mock_conn.execute_query.call_count == 0

    def test_tree_owner_absent_raises(self, mock_conn):
        with pytest.raises(ValueError, match="tree"):
            api.search_ontology(
                "transport", ["kegg", "tcdb"], tree="transporters",
                conn=mock_conn)

    def test_facet_applies_to_owner_only(self, mock_conn):
        calls = _so_dispatch(mock_conn, {
            "interpro": (_so_summary(), [_so_row("interpro:IPR1", interpro_type="DOMAIN")]),
            "kegg": (_so_summary(), [_so_row("kegg.pathway:ko00010")]),
        })
        result = api.search_ontology(
            "kinase", ["interpro", "kegg"], interpro_type="DOMAIN",
            limit=5, conn=mock_conn)
        for cypher, params in calls:
            if "interproEntryFullText" in cypher:
                assert params.get("interpro_type") == "DOMAIN"
            else:
                assert "interpro_type" not in params
        assert result["skipped_ontologies"] == []

    def test_tree_applies_to_brite_only(self, mock_conn):
        calls = _so_dispatch(mock_conn, {
            "brite": (_so_summary(), [_so_row("brite:br01601", tree="transporters",
                                                tree_code="br01601")]),
            "kegg": (_so_summary(), [_so_row("kegg.pathway:ko00010")]),
        })
        api.search_ontology(
            "transport", ["brite", "kegg"], tree="transporters",
            limit=5, conn=mock_conn)
        for cypher, params in calls:
            if "briteCategoryFullText" in cypher:
                assert params.get("tree") == "transporters"
            else:
                assert "tree" not in params

    def test_by_interpro_type_present_when_interpro_in_set(self, mock_conn):
        _so_dispatch(mock_conn, {
            "interpro": (_so_summary(), [_so_row("interpro:IPR1", interpro_type="DOMAIN")]),
        })
        result = api.search_ontology(
            "kinase", ["interpro", "kegg"], limit=5, conn=mock_conn)
        assert isinstance(result["by_interpro_type"], list)

    def test_by_family_type_present_when_ncbifam_in_set(self, mock_conn):
        _so_dispatch(mock_conn, {
            "ncbifam": (_so_summary(), [_so_row("ncbifam:NF000812", family_type="equivalog")]),
        })
        result = api.search_ontology(
            "protein", ["ncbifam", "kegg"], limit=5, conn=mock_conn)
        assert isinstance(result["by_family_type"], list)

    def test_lucene_retry_is_per_ontology(self, mock_conn):
        """A Lucene parse error on one ontology retries that ontology with
        the escaped query and leaves the others untouched."""
        from neo4j.exceptions import ClientError as Neo4jClientError
        state = {"failed": False}

        def _exec(cypher, **params):
            if "tcdbFamilyFullText" in cypher and not state["failed"]:
                state["failed"] = True
                raise Neo4jClientError("bad")
            if "total_entries" in cypher:
                return [_so_summary(total_matching=1)]
            return [_so_row("x:1")]

        mock_conn.execute_query.side_effect = _exec
        result = api.search_ontology(
            "bad+query", ["go_bp", "tcdb"], limit=5, conn=mock_conn)
        assert result["returned"] == 2


class TestGenesByOntologyAggregateRollups:
    """Spec §13 (i): the full-match trust rollups on a paged call come from
    the aggregate-only builder — the detail scan runs exactly once."""

    _AGG = {
        "by_evidence": [{"evidence": "curated", "count": 5},
                        {"evidence": "homology", "count": 2}],
        "by_tier": [{"tier": 1, "count": 5}, {"tier": "null", "count": 2}],
        "by_sources": [{"source": "eggnog", "count": 7},
                       {"source": "tcdb", "count": 5}],
        "by_call_class": [],
        "evidence_score_stats": {"min": 0.2, "median": 0.7, "max": 1.0,
                                 "n_null": 2},
    }

    def _rows(self):
        return [
            {"locus_tag": "PMM0392", "gene_name": None, "product": None,
             "gene_category": "Transport", "term_id": "tcdb:3.A.1",
             "term_name": "ABC superfamily", "level": 2, "is_informative": True,
             "evidence": "homology", "sources": ["eggnog"],
             "evidence_score": 0.6, "tier": None},
        ]

    def _run(self, mock_conn, calls=None, **kwargs):
        rows = self._rows()
        rules = [("by_evidence", [dict(self._AGG)])] + _gbo_rules(rows)
        seen = calls if calls is not None else []

        def _exec(cypher, **params):
            seen.append((cypher, params))
            for needle, out in rules:
                if needle in cypher:
                    return out
            return rows

        mock_conn.execute_query.side_effect = _exec
        return api.genes_by_ontology(
            ontology="tcdb", organism=_ORG, level=2, conn=mock_conn, **kwargs)

    @staticmethod
    def _is_detail_scan(cypher):
        """The paged detail query is the only one projecting term_name; the
        per-gene rollup (Query B) also emits `AS locus_tag`, so that alone
        cannot identify it."""
        return "AS term_name" in cypher and "AS locus_tag" in cypher

    def test_paged_call_runs_the_detail_scan_exactly_once(self, mock_conn):
        calls = []
        self._run(mock_conn, calls, limit=5)
        detail = [c for c, _ in calls if self._is_detail_scan(c)]
        assert len(detail) == 1
        assert "LIMIT $limit" in detail[0]

    def test_paged_call_runs_the_aggregate_projection(self, mock_conn):
        calls = []
        self._run(mock_conn, calls, limit=5)
        agg = [c for c, _ in calls if "by_evidence" in c]
        assert len(agg) == 1
        assert "AS locus_tag" not in agg[0]
        assert "AS term_name" not in agg[0]
        assert "LIMIT" not in agg[0]

    def test_envelope_reads_the_aggregate_row(self, mock_conn):
        result = self._run(mock_conn, limit=5)
        assert _freq_map(result["by_evidence"]) == {"curated": 5, "homology": 2}
        assert _freq_map(result["by_tier"]) == {1: 5, "null": 2}
        assert _freq_map(result["by_sources"]) == {"eggnog": 7, "tcdb": 5}
        assert result["evidence_score_stats"] == {
            "min": 0.2, "median": 0.7, "max": 1.0, "n_null": 2}

    def test_summary_mode_uses_the_aggregate_and_no_detail_scan(self, mock_conn):
        calls = []
        result = self._run(mock_conn, calls, summary=True)
        assert result["results"] == []
        assert not [c for c, _ in calls if self._is_detail_scan(c)]
        assert _freq_map(result["by_evidence"]) == {"curated": 5, "homology": 2}

    def test_aggregate_carries_the_trust_filters(self, mock_conn):
        calls = []
        self._run(mock_conn, calls, limit=5, sources=["eggnog"])
        agg = [(c, p) for c, p in calls if "by_evidence" in c]
        assert agg[0][1]["sources"] == ["eggnog"]

    def test_tier_null_warning_from_the_aggregate(self, mock_conn):
        result = self._run(mock_conn, limit=5, max_tier=2)
        assert any("tier" in w for w in result["warnings"])

    def test_envelope_keys_unchanged(self, mock_conn):
        result = self._run(mock_conn, limit=5)
        for key in ("trust_axes", "by_evidence", "by_tier", "by_sources",
                    "by_call_class", "evidence_score_stats", "filters_applied",
                    "skipped_ontologies", "warnings", "results", "returned",
                    "truncated", "offset", "total_matching"):
            assert key in result, key


# ---------------------------------------------------------------------------
# PR 3b code-review fix wave
# ---------------------------------------------------------------------------


class TestOntologyOrganismResolution3b:
    """Review #1: `organism` on search_ontology / ontology_term_details is
    resolved through the shared organism resolver BEFORE the builder runs —
    'MED4' reaches Cypher as 'Prochlorococcus MED4'; unknown / ambiguous
    names raise the standard ValueError without a term query."""

    def _merops(self, mock_conn):
        return _so_dispatch(mock_conn, {"merops": (
            _so_summary(total_matching=1, score_max=None, score_median=None,
                        by_level=[{"level": 1, "count": 1}]),
            [_so_row("merops.family:S33", score=None, organism_gene_count=9)])})

    # --- search_ontology ---

    def test_search_ontology_resolves_short_name_before_builder(self, mock_conn):
        calls = self._merops(mock_conn)
        api.search_ontology(ontology="merops", organism="MED4", conn=mock_conn)
        assert _is_resolve(calls[0][0]), "resolver must run first"
        assert calls[0][1]["organism"] == "MED4"
        term_calls = [(c, p) for c, p in calls if not _is_resolve(c)]
        assert term_calls
        for _, params in term_calls:
            assert params["organism"] == "Prochlorococcus MED4"
            assert "MED4" not in [v for v in params.values() if v == "MED4"]

    def test_search_ontology_full_name_passes_through(self, mock_conn):
        calls = self._merops(mock_conn)
        api.search_ontology(
            ontology="merops", organism="Prochlorococcus MED4", conn=mock_conn)
        for c, params in calls:
            if not _is_resolve(c):
                assert params["organism"] == "Prochlorococcus MED4"

    def test_search_ontology_unknown_organism_raises(self, mock_conn):
        mock_conn.execute_query.return_value = [{"organisms": []}]
        with pytest.raises(ValueError, match="no organism matching"):
            api.search_ontology(ontology="merops", organism="Nope", conn=mock_conn)
        assert mock_conn.execute_query.call_count == 1

    def test_search_ontology_ambiguous_organism_raises(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"organisms": ["Prochlorococcus MED4", "Prochlorococcus MIT9312"]}]
        with pytest.raises(ValueError, match="multiple organisms"):
            api.search_ontology(
                ontology="merops", organism="Prochlorococcus", conn=mock_conn)
        assert mock_conn.execute_query.call_count == 1

    def test_search_ontology_no_organism_no_resolver_call(self, mock_conn):
        calls = self._merops(mock_conn)
        api.search_ontology(ontology="merops", conn=mock_conn)
        assert not any(_is_resolve(c) for c, _ in calls)

    # --- ontology_term_details ---

    def test_term_details_resolves_short_name_before_builder(self, mock_conn):
        _otd_run(mock_conn, organism="MED4")
        calls = mock_conn.execute_query.call_args_list
        assert _is_resolve(calls[0].args[0])
        assert calls[0].kwargs["organism"] == "MED4"
        assert calls[-1].kwargs["organism"] == "Prochlorococcus MED4"
        assert not _is_resolve(calls[-1].args[0])

    def test_term_details_unknown_organism_raises(self, mock_conn):
        mock_conn.execute_query.return_value = [{"organisms": []}]
        with pytest.raises(ValueError, match="no organism matching"):
            api.ontology_term_details(
                term_ids=["tcdb:3.A.1"], organism="Nope", conn=mock_conn)
        assert mock_conn.execute_query.call_count == 1

    def test_term_details_ambiguous_organism_raises(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"organisms": ["Prochlorococcus MED4", "Prochlorococcus MIT9312"]}]
        with pytest.raises(ValueError, match="multiple organisms"):
            api.ontology_term_details(
                term_ids=["tcdb:3.A.1"], organism="Prochlorococcus",
                conn=mock_conn)
        assert mock_conn.execute_query.call_count == 1

    def test_term_details_no_organism_no_resolver_call(self, mock_conn):
        _otd_run(mock_conn)
        assert mock_conn.execute_query.call_count == 1
        assert not _is_resolve(mock_conn.execute_query.call_args.args[0])


class TestTermDetailsStripRule3b:
    """Review #4 / #5: `direct_gene_count` is keyed on the node VALUE (absent
    when null, present when 0); KEGG chemistry counts are compact on pathway
    terms and absent on KO terms."""

    def test_pfam_row_without_direct_gene_count_has_no_key(self, mock_conn):
        rows = [_otd_row("pfam:PF00005", "Pfam", name="ABC_tran", level=1,
                         gene_count=1702, organism_count=42,
                         extra={"short_name": "ABC_tran"})]
        row = _otd_run(mock_conn, rows=rows, term_ids=["pfam:PF00005"])["results"][0]
        assert row["ontology"] == "pfam"
        assert "direct_gene_count" not in row
        assert row["short_name"] == "ABC_tran"

    def test_hierarchical_row_with_a_value_keeps_it(self, mock_conn):
        rows = {r["term_id"]: r for r in _otd_run(mock_conn)["results"]}
        assert rows["go:0006979"]["direct_gene_count"] == 860

    def test_zero_is_a_value_not_a_strip(self, mock_conn):
        rows = [_otd_row("kegg.pathway:ko00010", "KeggTerm", name="Glycolysis",
                         level=2, direct_gene_count=0,
                         extra={"reaction_count": 40, "metabolite_count": 31})]
        row = _otd_run(mock_conn, rows=rows,
                       term_ids=["kegg.pathway:ko00010"])["results"][0]
        assert row["direct_gene_count"] == 0

    def test_kegg_pathway_carries_chemistry_counts(self, mock_conn):
        rows = [_otd_row("kegg.pathway:ko00010", "KeggTerm", name="Glycolysis",
                         level=2, direct_gene_count=0,
                         extra={"reaction_count": 40, "metabolite_count": 31})]
        row = _otd_run(mock_conn, rows=rows,
                       term_ids=["kegg.pathway:ko00010"])["results"][0]
        assert row["reaction_count"] == 40
        assert row["metabolite_count"] == 31

    def test_kegg_ko_has_neither_chemistry_key(self, mock_conn):
        rows = [_otd_row("kegg.orthology:K00001", "KeggTerm", name="adh",
                         level=3, direct_gene_count=52,
                         extra={"reaction_count": None, "metabolite_count": None})]
        row = _otd_run(mock_conn, rows=rows,
                       term_ids=["kegg.orthology:K00001"])["results"][0]
        assert row["direct_gene_count"] == 52
        assert "reaction_count" not in row
        assert "metabolite_count" not in row


# ===========================================================================
# Slice 4 — light surface + paper-batch absorption (spec
# docs/tool-specs/2026-08-27-slice4-light-surface.md). Stage 1 RED.
# ===========================================================================


class TestKGReleaseInfoVocabularyHash:
    """Spec §3.1: assert bucket 6 — the KG's `controlled_vocabularies_hash`
    must equal the pin the explorer was built against. Match → ok; mismatch
    or absent → warn (never worse), with a summary sentence naming the
    vocabulary set. The pin is read from
    `EXPECTED_KG_SHAPE["controlled_vocabularies_hash"]` — never hard-coded."""

    _BUCKET = "controlled_vocabularies_hash"

    @staticmethod
    def _pin():
        from multiomics_explorer.kg.constants import EXPECTED_KG_SHAPE
        return EXPECTED_KG_SHAPE["controlled_vocabularies_hash"]

    def _conn(self, **overrides):
        """Fake conn over the ok-schema fixture. The fixture now carries the
        pinned hash (spec §3.1); pass `absent=True` to drop the property
        entirely (pre-SYNC-005 KG) rather than null it."""
        absent = overrides.pop("absent", False)
        base = TestKGReleaseInfo()
        si = base._ok_schema_info(**overrides)
        if absent:
            si.pop("controlled_vocabularies_hash", None)
        return base._make_conn(si, base._ok_labels(), base._ok_rel_types())

    @staticmethod
    def _bucket6(report):
        hits = [a for a in report["asserts"]
                if a.get("kind") == "controlled_vocabularies_hash"]
        assert len(hits) == 1, report["asserts"]
        return hits[0]

    def test_pin_is_declared_in_expected_kg_shape(self):
        pin = self._pin()
        assert isinstance(pin, str)
        assert pin.startswith("sha256:")
        assert len(pin) == len("sha256:") + 64

    def test_hash_match_yields_ok_and_a_passed_bucket(self):
        from multiomics_explorer.api.functions import kg_release_info
        report = kg_release_info(self._conn(
            controlled_vocabularies_hash=self._pin()))
        assert report["verdict"] == "ok"
        b6 = self._bucket6(report)
        assert b6["passed"] is True
        assert b6["name"] == self._BUCKET
        assert b6["expected"] == self._pin()
        assert b6["actual"] == self._pin()
        assert b6["detail"] is None
        # 5 + 5 + 3 + 2 + 1 + 1 = 17 asserts
        assert len(report["asserts"]) == 17
        assert "17/17" in report["summary"]

    def test_hash_mismatch_yields_warn_with_the_vocabulary_sentence(self):
        from multiomics_explorer.api.functions import kg_release_info
        report = kg_release_info(self._conn(
            controlled_vocabularies_hash="sha256:" + "0" * 64))
        assert report["verdict"] == "warn"
        b6 = self._bucket6(report)
        assert b6["passed"] is False
        assert b6["expected"] == self._pin()
        assert b6["actual"] == "sha256:" + "0" * 64
        assert b6["detail"]
        assert "vocabulary" in report["summary"].lower()
        assert "list_filter_values" in report["summary"]

    def test_hash_absent_yields_warn_and_predates_detail(self):
        from multiomics_explorer.api.functions import kg_release_info
        # Pre-SYNC-005 KG: no such property on Schema_info at all.
        report = kg_release_info(self._conn(absent=True))
        assert report["verdict"] == "warn"
        b6 = self._bucket6(report)
        assert b6["passed"] is False
        assert b6["actual"] is None
        assert b6["expected"] == self._pin()
        assert "predates" in b6["detail"]
        assert "vocabulary" in report["summary"].lower()

    def test_failed_bucket_never_worse_than_warn(self):
        from multiomics_explorer.api.functions import kg_release_info
        report = kg_release_info(self._conn(
            controlled_vocabularies_hash="sha256:" + "f" * 64))
        assert report["verdict"] in ("ok", "warn")
        assert report["verdict"] != "unknown"

    def test_expected_is_read_from_expected_kg_shape(self, monkeypatch):
        """Patch the pin — the bucket must follow it, proving the api reads
        EXPECTED_KG_SHAPE rather than a private copy."""
        from multiomics_explorer.api.functions import kg_release_info
        from multiomics_explorer.kg import constants
        sentinel = "sha256:" + "a" * 64
        monkeypatch.setitem(
            constants.EXPECTED_KG_SHAPE, "controlled_vocabularies_hash", sentinel)
        report = kg_release_info(self._conn(
            controlled_vocabularies_hash=sentinel))
        b6 = self._bucket6(report)
        assert b6["expected"] == sentinel
        assert b6["passed"] is True
        assert report["verdict"] == "ok"

    def test_kg_identity_surfaces_the_hash(self):
        from multiomics_explorer.api.functions import kg_release_info
        report = kg_release_info(self._conn(
            controlled_vocabularies_hash=self._pin()))
        assert report["kg"]["controlled_vocabularies_hash"] == self._pin()

    def test_kg_identity_hash_is_none_when_absent(self):
        from multiomics_explorer.api.functions import kg_release_info
        report = kg_release_info(self._conn(absent=True))
        assert "controlled_vocabularies_hash" in report["kg"]
        assert report["kg"]["controlled_vocabularies_hash"] is None

    def test_other_shape_failures_still_reported_alongside(self):
        from multiomics_explorer.api.functions import kg_release_info
        base = TestKGReleaseInfo()
        si = base._ok_schema_info(mcp_min_version="99.99.99",
                                  controlled_vocabularies_hash="sha256:" + "1" * 64)
        report = kg_release_info(base._make_conn(
            si, base._ok_labels(), base._ok_rel_types()))
        assert report["verdict"] == "warn"
        failed_kinds = {a["kind"] for a in report["asserts"] if not a["passed"]}
        assert failed_kinds == {"version_compat", "controlled_vocabularies_hash"}
        assert "99.99.99" in report["summary"]
        assert "vocabulary" in report["summary"].lower()


class TestListOrganismsAnnotationCapability:
    """Spec §3.3: four compact annotation counts per row and the
    `top_annotation_capability` envelope — top-10 by peptidase_gene_count
    desc then preferred_name, all four columns, all-zero rows excluded.
    Detail mode computes it api-side over the matched rows; summary mode
    reads the summary builder (mirror of top_metabolic_capability)."""

    _COLS = (
        "peptidase_gene_count", "nonpeptidase_homolog_gene_count",
        "interpro_gene_count", "ncbifam_gene_count",
    )

    @staticmethod
    def _row(name, pep, nonpep, ipr, ncbi, genus="Alteromonas"):
        return {
            "organism_name": name, "organism_type": "genome_strain",
            "genus": genus, "species": None, "strain": None, "clade": None,
            "ncbi_taxon_id": None, "gene_count": 4000,
            "publication_count": 0, "experiment_count": 0,
            "treatment_types": [], "background_factors": [],
            "omics_types": [], "clustering_analysis_count": 0,
            "cluster_types": [], "derived_metric_count": 0,
            "derived_metric_value_kinds": [], "compartments": [],
            "reaction_count": 0, "catalyzed_metabolite_count": 0,
            "transported_metabolite_count": 0,
            "measured_metabolite_count": 0,
            "peptidase_gene_count": pep,
            "nonpeptidase_homolog_gene_count": nonpep,
            "interpro_gene_count": ipr,
            "ncbifam_gene_count": ncbi,
            "growth_phases": [],
        }

    # Live-shaped fixtures (spec §10): MarRef tops, two ties on 125 broken by
    # name, one all-zero treatment taxon, one zero-peptidase-but-annotated.
    _ROWS = [
        _row.__func__("Alteromonas (MarRef v6)", 148, 31, 3746, 1379),
        _row.__func__("Pseudomonas putida KT2440", 125, 43, 4961, 2264,
                      genus="Pseudomonas"),
        _row.__func__("Alteromonas macleodii ATCC27126", 125, 37, 3456, 1598),
        _row.__func__("Alteromonas macleodii AD45", 129, 32, 3495, 1611),
        _row.__func__("Prochlorococcus MED4", 50, 8, 1545, 744,
                      genus="Prochlorococcus"),
        _row.__func__("Phage", 0, 0, 0, 0, genus=None),
        _row.__func__("Prochlorococcus MIT1314", 0, 0, 12, 3,
                      genus="Prochlorococcus"),
    ]

    @staticmethod
    def _expected_entries(rows):
        keep = [r for r in rows if any(r[c] for c in (
            "peptidase_gene_count", "nonpeptidase_homolog_gene_count",
            "interpro_gene_count", "ncbifam_gene_count"))]
        keep.sort(key=lambda r: (-r["peptidase_gene_count"], r["organism_name"]))
        return [
            {
                "preferred_name": r["organism_name"],
                "organism_name": r["organism_name"],
                "peptidase_gene_count": r["peptidase_gene_count"],
                "nonpeptidase_homolog_gene_count": r["nonpeptidase_homolog_gene_count"],
                "interpro_gene_count": r["interpro_gene_count"],
                "ncbifam_gene_count": r["ncbifam_gene_count"],
            }
            for r in keep[:10]
        ]

    def _summary_row(self, rows):
        return {
            "total_entries": 48, "total_matching": len(rows),
            "by_value_kind": [], "by_metric_type": [], "by_compartment": [],
            "by_cluster_type": [], "by_organism_type": [],
            "by_measurement_capability": {
                "has_metabolomics": 0, "no_metabolomics": len(rows)},
            "top_annotation_capability": self._expected_entries(rows),
        }

    def _wire(self, mock_conn, rows):
        """Route by Cypher shape: the summary builder returns one rollup row;
        every other (detail / capability / not_found probe) query returns
        the organism rows, which carry the four counts."""
        summary_row = self._summary_row(rows)

        def _exec(cypher, **params):
            if "total_entries" in cypher:
                return [summary_row]
            if "collect(toLower(o.preferred_name)) AS found" in cypher:
                return [{"found": [r["organism_name"].lower() for r in rows]}]
            if "collect(DISTINCT o.preferred_name) AS organisms" in cypher:
                # shared resolver: word match on the wired rows
                words = params["organism"].lower().split()
                return [{"organisms": [
                    r["organism_name"] for r in rows
                    if all(w in r["organism_name"].lower() for w in words)
                ]}]
            names_lc = params.get("organism_names_lc")
            if names_lc:
                return [r for r in rows if r["organism_name"].lower() in names_lc]
            return list(rows)

        mock_conn.execute_query.side_effect = _exec
        return mock_conn

    def test_rows_carry_the_four_counts(self, mock_conn):
        self._wire(mock_conn, self._ROWS)
        result = api.list_organisms(limit=50, conn=mock_conn)
        by_name = {r["organism_name"]: r for r in result["results"]}
        marref = by_name["Alteromonas (MarRef v6)"]
        assert marref["peptidase_gene_count"] == 148
        assert marref["nonpeptidase_homolog_gene_count"] == 31
        assert marref["interpro_gene_count"] == 3746
        assert marref["ncbifam_gene_count"] == 1379
        phage = by_name["Phage"]
        assert all(phage[c] == 0 for c in self._COLS)

    def test_envelope_has_top_annotation_capability(self, mock_conn):
        self._wire(mock_conn, self._ROWS)
        result = api.list_organisms(limit=50, conn=mock_conn)
        assert "top_annotation_capability" in result
        assert isinstance(result["top_annotation_capability"], list)

    def test_entry_shape(self, mock_conn):
        self._wire(mock_conn, self._ROWS)
        result = api.list_organisms(limit=50, conn=mock_conn)
        entry = result["top_annotation_capability"][0]
        assert set(entry) == {
            "preferred_name", "organism_name", *self._COLS,
        }
        assert entry["preferred_name"] == entry["organism_name"]

    def test_sorted_by_peptidase_desc_then_preferred_name(self, mock_conn):
        self._wire(mock_conn, self._ROWS)
        result = api.list_organisms(limit=50, conn=mock_conn)
        names = [e["organism_name"] for e in result["top_annotation_capability"]]
        assert names[:4] == [
            "Alteromonas (MarRef v6)",            # 148
            "Alteromonas macleodii AD45",          # 129
            "Alteromonas macleodii ATCC27126",     # 125, name-tie-break
            "Pseudomonas putida KT2440",           # 125
        ]
        assert result["top_annotation_capability"][0]["peptidase_gene_count"] == 148

    def test_all_zero_rows_excluded_but_zero_peptidase_kept(self, mock_conn):
        self._wire(mock_conn, self._ROWS)
        result = api.list_organisms(limit=50, conn=mock_conn)
        names = {e["organism_name"] for e in result["top_annotation_capability"]}
        assert "Phage" not in names
        # zero peptidases but non-zero interpro/ncbifam → still listed
        assert "Prochlorococcus MIT1314" in names

    def test_top_ten_cap(self, mock_conn):
        rows = [self._row(f"Org {i:02d}", 200 - i, 1, 1, 1) for i in range(15)]
        self._wire(mock_conn, rows)
        result = api.list_organisms(limit=50, conn=mock_conn)
        cap = result["top_annotation_capability"]
        assert len(cap) == 10
        assert [e["peptidase_gene_count"] for e in cap] == list(range(200, 190, -1))

    def test_computed_over_matched_set_not_page(self, mock_conn):
        """Detail mode with limit=1: the rollup still ranks every matched
        organism (page-independent, like top_metabolic_capability)."""
        self._wire(mock_conn, self._ROWS)
        result = api.list_organisms(limit=1, conn=mock_conn)
        assert result["returned"] == 1
        assert len(result["top_annotation_capability"]) == 6

    def test_subset_via_organism_names(self, mock_conn):
        self._wire(mock_conn, self._ROWS)
        result = api.list_organisms(
            organism_names=["Prochlorococcus MED4"], limit=50, conn=mock_conn)
        cap = result["top_annotation_capability"]
        assert [e["organism_name"] for e in cap] == ["Prochlorococcus MED4"]
        assert cap[0]["peptidase_gene_count"] == 50

    def test_subset_of_all_zero_organism_is_empty(self, mock_conn):
        self._wire(mock_conn, self._ROWS)
        result = api.list_organisms(
            organism_names=["Phage"], limit=50, conn=mock_conn)
        assert result["total_matching"] == 1
        assert result["top_annotation_capability"] == []

    def test_summary_mode_surfaces_rollup(self, mock_conn):
        self._wire(mock_conn, self._ROWS)
        result = api.list_organisms(summary=True, conn=mock_conn)
        assert result["results"] == []
        cap = result["top_annotation_capability"]
        assert cap == self._expected_entries(self._ROWS)

    def test_empty_match_yields_empty_rollup(self, mock_conn):
        self._wire(mock_conn, [])
        result = api.list_organisms(
            organism_names=["Nonexistus fakeii"], conn=mock_conn)
        assert result["top_annotation_capability"] == []

    def test_no_new_filter_param(self):
        import inspect
        assert "min_peptidase_gene_count" not in inspect.signature(
            api.list_organisms).parameters


class TestListFilterValuesClusterType:
    """Spec §3.4 / §7.4: `filter_type='cluster_type'` reads the
    ControlledVocabulary node for ClusteringAnalysis.cluster_type (closed,
    6 values), falling back to a node pivot + warning (slice-3 rule)."""

    _SIX = ["time_course", "diel", "condition_comparison",
            "expression_bin", "decay_pattern", "genomic_island"]

    def _vocab_rows(self):
        return [{
            "values": list(self._SIX),
            "description": "How the analysis grouped genes",
            "value_type": "string", "sparse": "false",
            "min_value": None, "max_value": None,
        }]

    def test_filter_type_is_accepted(self, mock_conn):
        _trust_dispatch(mock_conn,
                        [("ControlledVocabulary", self._vocab_rows())])
        result = api.list_filter_values(filter_type="cluster_type", conn=mock_conn)
        assert result["filter_type"] == "cluster_type"
        assert result["total_entries"] == 6
        assert result["returned"] == 6
        assert result["truncated"] is False

    def test_vocabulary_path_rows(self, mock_conn):
        _trust_dispatch(mock_conn,
                        [("ControlledVocabulary", self._vocab_rows())])
        result = api.list_filter_values(filter_type="cluster_type", conn=mock_conn)
        values = [r["value"] for r in result["results"]]
        assert set(values) == set(self._SIX)
        for row in result["results"]:
            assert row["source"] == "vocabulary"
            assert row["applies_to"] == ["ClusteringAnalysis"]
            # Vocab description is per-property: once on the envelope, and
            # the per-row key is absent (no per-value text in the vocab).
            assert "description" not in row
        assert result["description"] == "How the analysis grouped genes"
        assert result["warnings"] == []

    def test_pivot_fallback_has_no_envelope_description(self, mock_conn):
        def _exec(cypher, **params):
            if "ControlledVocabulary" in cypher:
                return []
            if "DISTINCT" in cypher:
                return [{"value": "diel"}]
            return []

        mock_conn.execute_query.side_effect = _exec
        result = api.list_filter_values(filter_type="cluster_type", conn=mock_conn)
        assert result["description"] is None
        assert "description" not in result["results"][0]

    def test_non_vocab_filter_types_have_null_envelope_description(self, mock_conn):
        mock_conn.execute_query.return_value = [
            {"category": "Photosynthesis", "gene_count": 3}]
        result = api.list_filter_values(filter_type="gene_category", conn=mock_conn)
        assert result["description"] is None

    def test_vocab_read_targets_clustering_analysis_cluster_type(self, mock_conn):
        _trust_dispatch(mock_conn,
                        [("ControlledVocabulary", self._vocab_rows())])
        api.list_filter_values(filter_type="cluster_type", conn=mock_conn)
        vocab_calls = [
            c for c in mock_conn.execute_query.call_args_list
            if "ControlledVocabulary" in c.args[0]
        ]
        assert vocab_calls, "no ControlledVocabulary read issued"
        kwargs = vocab_calls[0].kwargs
        assert kwargs["applies_to"] == "ClusteringAnalysis"
        assert kwargs["prop"] == "cluster_type"

    def test_missing_vocab_node_falls_back_to_the_node_pivot(self, mock_conn):
        def _exec(cypher, **params):
            if "ControlledVocabulary" in cypher:
                return []
            if "MATCH (n:ClusteringAnalysis)" in cypher and "DISTINCT" in cypher:
                return [{"value": "diel"}, {"value": "decay_pattern"}]
            return []

        mock_conn.execute_query.side_effect = _exec
        result = api.list_filter_values(filter_type="cluster_type", conn=mock_conn)
        assert {r["value"] for r in result["results"]} == {"diel", "decay_pattern"}
        assert all(r["source"] == "pivot" for r in result["results"])
        assert all(r["applies_to"] == ["ClusteringAnalysis"]
                   for r in result["results"])

    def test_pivot_fallback_emits_the_kg_side_warning(self, mock_conn):
        def _exec(cypher, **params):
            if "ControlledVocabulary" in cypher:
                return []
            if "DISTINCT" in cypher:
                return [{"value": "diel"}]
            return []

        mock_conn.execute_query.side_effect = _exec
        result = api.list_filter_values(filter_type="cluster_type", conn=mock_conn)
        joined = " ".join(result["warnings"])
        assert "No ControlledVocabulary entry for ClusteringAnalysis.cluster_type" in joined
        assert "KG-side fix pending" in joined

    def test_missing_vocab_is_never_a_hard_raise(self, mock_conn):
        mock_conn.execute_query.side_effect = lambda cypher, **p: []
        result = api.list_filter_values(filter_type="cluster_type", conn=mock_conn)
        assert result["results"] == []

    def test_unknown_filter_type_error_lists_cluster_type(self, mock_conn):
        with pytest.raises(ValueError, match="cluster_type"):
            api.list_filter_values(filter_type="bogus", conn=mock_conn)


class TestListFilterValuesMultiLabelVocabs:
    """llm-review 2b.1: `list_filter_values` serves the remaining closed
    vocabularies — treatment_type / background_factors (union across four
    node labels), table_scope (single node label), detection_status and
    expression_status (edge-scoped)."""

    def test_list_filter_values_treatment_type_unions_four_labels(self, monkeypatch):
        calls = []
        def fake_read(conn, applies_to, prop, kind, *, cache=True):
            calls.append((applies_to, prop, kind))
            vals = {"Experiment": ["nitrogen", "iron"], "DerivedMetric": ["diel"],
                    "MetaboliteAssay": ["nitrogen"], "ClusteringAnalysis": ["diel"]}[applies_to]
            return {"values": vals, "value_descriptions": {}, "description": "d", "source": "vocabulary", "warning": None}
        monkeypatch.setattr(api, "_read_vocab_values", fake_read)
        out = api.list_filter_values(filter_type="treatment_type", conn=MagicMock())
        by_value = {r["value"]: r for r in out["results"]}
        assert set(by_value) == {"nitrogen", "iron", "diel"}
        assert by_value["nitrogen"]["applies_to"] == ["Experiment", "MetaboliteAssay"]
        assert {c[0] for c in calls} == {"Experiment", "DerivedMetric", "MetaboliteAssay", "ClusteringAnalysis"}

    def test_list_filter_values_background_factors_unions_four_labels(self, monkeypatch):
        calls = []
        def fake_read(conn, applies_to, prop, kind, *, cache=True):
            calls.append((applies_to, prop, kind))
            vals = {"Experiment": ["axenic", "diel"], "DerivedMetric": ["diel"],
                    "MetaboliteAssay": ["axenic"], "ClusteringAnalysis": ["viral"]}[applies_to]
            return {"values": vals, "value_descriptions": {}, "description": "d", "source": "vocabulary", "warning": None}
        monkeypatch.setattr(api, "_read_vocab_values", fake_read)
        out = api.list_filter_values(filter_type="background_factors", conn=MagicMock())
        by_value = {r["value"]: r for r in out["results"]}
        assert set(by_value) == {"axenic", "diel", "viral"}
        assert by_value["axenic"]["applies_to"] == ["Experiment", "MetaboliteAssay"]
        assert by_value["viral"]["applies_to"] == ["ClusteringAnalysis"]
        assert {c[0] for c in calls} == {"Experiment", "DerivedMetric", "MetaboliteAssay", "ClusteringAnalysis"}

    def test_list_filter_values_table_scope_single_label(self, monkeypatch):
        calls = []
        def fake_read(conn, applies_to, prop, kind, *, cache=True):
            calls.append((applies_to, prop, kind))
            return {"values": ["all_detected_genes", "top_n"], "value_descriptions": {},
                    "description": "d", "source": "vocabulary", "warning": None}
        monkeypatch.setattr(api, "_read_vocab_values", fake_read)
        out = api.list_filter_values(filter_type="table_scope", conn=MagicMock())
        by_value = {r["value"]: r for r in out["results"]}
        assert set(by_value) == {"all_detected_genes", "top_n"}
        for row in out["results"]:
            assert row["applies_to"] == ["Experiment"]
        assert calls == [("Experiment", "table_scope", "node")]

    def test_list_filter_values_detection_status_is_edge_scoped(self, monkeypatch):
        calls = []
        def fake_read(conn, applies_to, prop, kind, *, cache=True):
            calls.append((applies_to, prop, kind))
            return {"values": ["detected", "not_detected", "sporadic"], "value_descriptions": {},
                    "description": "d", "source": "vocabulary", "warning": None}
        monkeypatch.setattr(api, "_read_vocab_values", fake_read)
        out = api.list_filter_values(filter_type="detection_status", conn=MagicMock())
        by_value = {r["value"]: r for r in out["results"]}
        assert set(by_value) == {"detected", "not_detected", "sporadic"}
        for row in out["results"]:
            assert row["applies_to"] == ["Assay_quantifies_metabolite"]
        assert calls == [("Assay_quantifies_metabolite", "detection_status", "edge")]

    def test_list_filter_values_expression_status_is_edge_scoped(self, monkeypatch):
        calls = []
        def fake_read(conn, applies_to, prop, kind, *, cache=True):
            calls.append((applies_to, prop, kind))
            return {"values": ["up", "down"], "value_descriptions": {},
                    "description": "d", "source": "vocabulary", "warning": None}
        monkeypatch.setattr(api, "_read_vocab_values", fake_read)
        out = api.list_filter_values(filter_type="expression_status", conn=MagicMock())
        by_value = {r["value"]: r for r in out["results"]}
        assert set(by_value) == {"up", "down"}
        for row in out["results"]:
            assert row["applies_to"] == ["Changes_expression_of"]
        assert calls == [("Changes_expression_of", "expression_status", "edge")]

    def test_unknown_filter_type_error_lists_new_types(self, mock_conn):
        with pytest.raises(ValueError) as exc_info:
            api.list_filter_values(filter_type="bogus", conn=mock_conn)
        msg = str(exc_info.value)
        for name in ("treatment_type", "background_factors", "table_scope",
                     "detection_status", "expression_status"):
            assert name in msg

    def test_source_is_tracked_per_value_not_a_single_flag(self, monkeypatch):
        """Review fix: a mixed read (one label vocabulary, one label pivot)
        must not stamp the same `source` on every row. A value carried by
        at least one vocabulary-sourced label reads "vocabulary" even if
        another label carrying it (or a later label carrying nothing in
        common) fell back to pivot; a value carried ONLY by pivot-sourced
        label(s) reads "pivot"."""
        reads = {
            "Experiment": {"values": ["nitrogen"], "value_descriptions": {},
                           "description": "d", "source": "vocabulary", "warning": None},
            "DerivedMetric": {"values": ["nitrogen", "diel"], "value_descriptions": {},
                              "description": "d", "source": "pivot",
                              "warning": "No ControlledVocabulary entry for DerivedMetric.treatment_type"},
            "MetaboliteAssay": {"values": [], "value_descriptions": {},
                                "description": "d", "source": "vocabulary", "warning": None},
            "ClusteringAnalysis": {"values": ["iron"], "value_descriptions": {},
                                   "description": "d", "source": "vocabulary", "warning": None},
        }
        def fake_read(conn, applies_to, prop, kind, *, cache=True):
            return reads[applies_to]
        monkeypatch.setattr(api, "_read_vocab_values", fake_read)
        out = api.list_filter_values(filter_type="treatment_type", conn=MagicMock())
        by_value = {r["value"]: r for r in out["results"]}
        # Carried by Experiment (vocabulary) AND DerivedMetric (pivot) -> vocabulary wins.
        assert by_value["nitrogen"]["source"] == "vocabulary"
        # Carried ONLY by DerivedMetric (pivot).
        assert by_value["diel"]["source"] == "pivot"
        # Carried ONLY by ClusteringAnalysis (vocabulary).
        assert by_value["iron"]["source"] == "vocabulary"
        assert "No ControlledVocabulary entry" in " ".join(out["warnings"])


class TestTripletRowsCarryTransportSubstrateResolution:
    """Spec §3.2: the api passes the new detail column through unchanged —
    a real value on transport rows, an explicit `None` (union padding, NOT
    sparse-stripped) on metabolism rows — for both triplet tools."""

    _MET_ROW = {**TestGenesByMetabolite._METAB_ROW,
                "transport_substrate_resolution": None}
    _TR_ROW = {**TestGenesByMetabolite._TRANS_ROW_MS,
               "transport_substrate_resolution": "resolved"}
    _TR_ROW_FI = {**TestGenesByMetabolite._TRANS_ROW_INH,
                  "transport_substrate_resolution": "family_inferred"}

    def test_gbm_rows_keep_the_column_on_both_arms(self, monkeypatch):
        # Manually-instantiated helper object (not run through pytest's own
        # collection) — TestGenesByMetabolite's autouse fixture doesn't
        # apply here, so patch _validate_organism_inputs directly.
        monkeypatch.setattr(
            api, "_validate_organism_inputs",
            lambda organism, locus_tags, experiment_ids, conn: organism,
        )
        gbm = TestGenesByMetabolite()
        conn = gbm._mock_conn(
            [gbm._SUMMARY_ROW_BOTH_ARMS],
            [self._MET_ROW],
            [self._TR_ROW, self._TR_ROW_FI],
            [{"found": ["kegg.compound:C00086"]}],
        )
        out = gbm._api()(gbm._METS, gbm._ORG, conn=conn)
        by_src = {}
        for r in out["results"]:
            by_src.setdefault(r["evidence_source"], []).append(r)
        met = by_src["metabolism"][0]
        assert "transport_substrate_resolution" in met
        assert met["transport_substrate_resolution"] is None
        trans = {r["locus_tag"]: r["transport_substrate_resolution"]
                 for r in by_src["transport"]}
        assert trans == {"PMM0974": "resolved", "PMM0234": "family_inferred"}

    def test_gbm_column_is_not_sparse_stripped(self):
        from multiomics_explorer.api.functions import _GBM_SPARSE_FIELDS
        assert "transport_substrate_resolution" not in _GBM_SPARSE_FIELDS

    def test_mbg_rows_keep_the_column_on_both_arms(self, monkeypatch):
        # See test_gbm_rows_keep_the_column_on_both_arms — same reason.
        monkeypatch.setattr(
            api, "_validate_organism_inputs",
            lambda organism, locus_tags, experiment_ids, conn: organism,
        )
        mbg = TestMetabolitesByGene()
        conn = mbg._mock_conn(
            [mbg._SUMMARY_ROW_BOTH_ARMS],
            [self._MET_ROW],
            [self._TR_ROW],
            [{"found": ["PMM0944", "PMM0974"]}],
        )
        out = mbg._api()(["PMM0944", "PMM0974"], mbg._ORG, conn=conn)
        rows = {r["evidence_source"]: r for r in out["results"]}
        assert rows["metabolism"]["transport_substrate_resolution"] is None
        assert "transport_substrate_resolution" in rows["metabolism"]
        assert rows["transport"]["transport_substrate_resolution"] == "resolved"

    def test_mbg_column_is_not_sparse_stripped(self):
        from multiomics_explorer.api.functions import _MBG_SPARSE_FIELDS
        assert "transport_substrate_resolution" not in _MBG_SPARSE_FIELDS


# ---------------------------------------------------------------------------
# Bare metabolite-ID coercion (backlog 3.2, Mode B) — api helper + 7 tools
# ---------------------------------------------------------------------------

_ALIAS_MARK = "UNWIND $raw"


class _AliasConn:
    """Stub GraphConnection that answers the alias-resolver query from a
    `{raw: [canonical, ...]}` map and every other query from a FIFO of canned
    responses (last-exhausted → `[]`).

    Records every call so tests can inspect the params each builder received.
    """

    def __init__(self, alias_map: dict | None = None, responses=None):
        self.alias_map = alias_map or {}
        self.responses = list(responses or [])
        self.calls: list[tuple[str, dict]] = []

    def execute_query(self, cypher, **params):
        self.calls.append((cypher, dict(params)))
        if _ALIAS_MARK in cypher:
            return [
                {"raw": r, "canonical": list(self.alias_map.get(r, []))}
                for r in params["raw"]
            ]
        if "AS organisms" in cypher:
            # genes_by_metabolite / metabolites_by_gene call
            # _validate_organism_inputs before any builder; every per-tool
            # call here already passes the canonical `_ORG`, so echo it
            # back as the sole resolved organism (doesn't consume the
            # `responses` FIFO reserved for the builder calls).
            return [{"organisms": [params["organism"]]}]
        if self.responses:
            return self.responses.pop(0)
        return []

    # -- helpers -----------------------------------------------------------
    @property
    def alias_calls(self):
        return [(c, p) for c, p in self.calls if _ALIAS_MARK in c]

    def first_params_with(self, key):
        for c, p in self.calls:
            if _ALIAS_MARK in c:
                continue
            if key in p:
                return p
        raise AssertionError(f"no non-alias query carried param {key!r}: "
                             f"{[sorted(p) for _, p in self.calls]}")


class TestCanonicalizeMetaboliteIds:
    """`_canonicalize_metabolite_ids(conn, ids)` →
    `(canonical_ids, resolved_aliases, warnings)`."""

    def _fn(self):
        from multiomics_explorer.api.functions import (
            _canonicalize_metabolite_ids,
        )
        return _canonicalize_metabolite_ids

    # -- short-circuits ----------------------------------------------------
    def test_none_passthrough_no_query(self):
        conn = _AliasConn()
        ids, aliases, warnings = self._fn()(conn, None)
        assert ids is None
        assert aliases == {}
        assert warnings == []
        assert conn.calls == []

    def test_empty_list_passthrough_no_query(self):
        conn = _AliasConn()
        ids, aliases, warnings = self._fn()(conn, [])
        assert ids == []
        assert aliases == {}
        assert warnings == []
        assert conn.calls == []

    @pytest.mark.parametrize("canon", [
        "kegg.compound:C00064", "chebi:17234", "mnx:MNXM1095050",
    ])
    def test_canonical_prefix_passthrough_no_query(self, canon):
        conn = _AliasConn()
        ids, aliases, warnings = self._fn()(conn, [canon])
        assert ids == [canon]
        assert aliases == {}
        assert warnings == []
        assert conn.calls == []

    def test_all_canonical_batch_zero_queries(self):
        conn = _AliasConn()
        batch = ["kegg.compound:C00064", "chebi:17234", "mnx:MNXM1095050"]
        ids, _, _ = self._fn()(conn, batch)
        assert ids == batch
        assert conn.calls == []

    def test_unknown_prefix_passthrough_verbatim_no_query(self):
        """Any other `prefix:` form (except CHEBI:) is not an alias —
        forwarded untouched so it lands in `not_found` as today."""
        conn = _AliasConn()
        ids, aliases, _ = self._fn()(conn, ["pubchem:5793", "kegg.pathway:ko00010"])
        assert ids == ["pubchem:5793", "kegg.pathway:ko00010"]
        assert aliases == {}
        assert conn.calls == []

    def test_prefixed_ids_not_sent_to_resolver(self):
        """Canonical inputs are filtered out in Python before the UNWIND."""
        conn = _AliasConn({"C00064": ["kegg.compound:C00064"]})
        self._fn()(conn, ["kegg.compound:C00001", "C00064", "pubchem:1"])
        assert len(conn.alias_calls) == 1
        _, params = conn.alias_calls[0]
        assert params["raw"] == ["C00064"]

    # -- classification rules ---------------------------------------------
    def test_bare_kegg(self):
        conn = _AliasConn({"C00064": ["kegg.compound:C00064"]})
        ids, aliases, warnings = self._fn()(conn, ["C00064"])
        assert ids == ["kegg.compound:C00064"]
        assert aliases == {"C00064": ["kegg.compound:C00064"]}
        assert warnings == []

    def test_uppercase_chebi_prefix_is_alias(self):
        conn = _AliasConn({"CHEBI:17234": ["kegg.compound:C00064"]})
        ids, aliases, _ = self._fn()(conn, ["CHEBI:17234"])
        assert ids == ["kegg.compound:C00064"]
        assert aliases == {"CHEBI:17234": ["kegg.compound:C00064"]}
        _, params = conn.alias_calls[0]
        assert params["raw"] == ["CHEBI:17234"]

    def test_lowercase_chebi_prefix_is_canonical(self):
        """`chebi:NNN` is a KG-canonical `Metabolite.id` — never resolved."""
        conn = _AliasConn({"chebi:10004": ["SHOULD_NOT_BE_USED"]})
        ids, aliases, _ = self._fn()(conn, ["chebi:10004"])
        assert ids == ["chebi:10004"]
        assert aliases == {}
        assert conn.calls == []

    def test_bare_numeric_is_chebi(self):
        conn = _AliasConn({"17234": ["kegg.compound:C00064"]})
        ids, aliases, _ = self._fn()(conn, ["17234"])
        assert ids == ["kegg.compound:C00064"]
        assert aliases == {"17234": ["kegg.compound:C00064"]}

    def test_bare_hmdb(self):
        conn = _AliasConn({"HMDB0000122": ["kegg.compound:C00221"]})
        ids, aliases, _ = self._fn()(conn, ["HMDB0000122"])
        assert ids == ["kegg.compound:C00221"]
        assert aliases == {"HMDB0000122": ["kegg.compound:C00221"]}

    def test_bare_mnxm(self):
        conn = _AliasConn({"MNXM1095050": ["chebi:10004"]})
        ids, aliases, _ = self._fn()(conn, ["MNXM1095050"])
        assert ids == ["chebi:10004"]
        assert aliases == {"MNXM1095050": ["chebi:10004"]}

    def test_exactly_one_round_trip(self):
        conn = _AliasConn({
            "C00064": ["kegg.compound:C00064"],
            "HMDB0000122": ["kegg.compound:C00221"],
            "MNXM1095050": ["chebi:10004"],
        })
        self._fn()(conn, ["C00064", "HMDB0000122", "MNXM1095050", "chebi:1"])
        assert len(conn.calls) == 1
        assert len(conn.alias_calls) == 1

    # -- collisions / unresolved / ordering -------------------------------
    def test_collision_expands_to_all_and_warns(self):
        both = ["kegg.compound:C00354", "kegg.compound:C05378"]
        conn = _AliasConn({"CHEBI:16905": both})
        ids, aliases, warnings = self._fn()(conn, ["CHEBI:16905"])
        assert ids == both
        assert aliases == {"CHEBI:16905": both}
        assert len(warnings) == 1
        w = warnings[0]
        assert "CHEBI:16905" in w
        assert "kegg.compound:C00354" in w
        assert "kegg.compound:C05378" in w
        assert "2 metabolites" in w

    def test_unique_match_no_warning(self):
        conn = _AliasConn({"C00064": ["kegg.compound:C00064"]})
        _, _, warnings = self._fn()(conn, ["C00064"])
        assert warnings == []

    def test_unresolved_stays_verbatim(self):
        """No node matched → keep the user's input form so the existing
        `not_found` probes report it unchanged; no alias, no warning."""
        conn = _AliasConn({})  # C99999 → []
        ids, aliases, warnings = self._fn()(conn, ["C99999"])
        assert ids == ["C99999"]
        assert aliases == {}
        assert warnings == []

    def test_input_order_preserved(self):
        conn = _AliasConn({
            "C00064": ["kegg.compound:C00064"],
            "HMDB0000122": ["kegg.compound:C00221"],
        })
        ids, _, _ = self._fn()(conn, [
            "HMDB0000122", "chebi:10004", "C00064", "bogus99",
        ])
        assert ids == [
            "kegg.compound:C00221", "chebi:10004", "kegg.compound:C00064",
            "bogus99",
        ]

    def test_dedup_after_expansion_first_seen_order(self):
        conn = _AliasConn({
            "C00064": ["kegg.compound:C00064"],
            "CHEBI:17234": ["kegg.compound:C00064"],
        })
        ids, aliases, _ = self._fn()(conn, [
            "C00064", "kegg.compound:C00064", "CHEBI:17234", "kegg.compound:C00001",
        ])
        assert ids == ["kegg.compound:C00064", "kegg.compound:C00001"]
        assert aliases == {
            "C00064": ["kegg.compound:C00064"],
            "CHEBI:17234": ["kegg.compound:C00064"],
        }

    def test_resolved_aliases_only_holds_coerced_entries(self):
        conn = _AliasConn({"C00064": ["kegg.compound:C00064"]})
        _, aliases, _ = self._fn()(conn, [
            "kegg.compound:C00001", "C00064", "C99999", "pubchem:1",
        ])
        assert set(aliases) == {"C00064"}


# ---- per-tool plumbing ------------------------------------------------------

_BARE = "C00064"
_CANON = "kegg.compound:C00064"
_BARE_X = "C00002"
_CANON_X = "kegg.compound:C00002"
_ALIAS_MAP = {_BARE: [_CANON], _BARE_X: [_CANON_X]}
_ORG = "Prochlorococcus MED4"

_LM_SUMMARY = {
    "total_entries": 3025, "total_matching": 0, "top_organisms": [],
    "top_metabolite_pathways": [], "by_evidence_source": [],
    "with_chebi": 0, "with_hmdb": 0, "with_mnxm": 0,
    "mass_min": None, "mass_median": None, "mass_max": None,
}
_GBM_SUMMARY = {
    "total_matching": 0, "gene_count_total": 0, "reaction_count_total": 0,
    "transporter_count_total": 0, "metabolite_count_total": 0,
    "rows_by_evidence_source": [], "rows_by_substrate_depth": [],
    "by_metabolite": [], "top_reactions": [], "top_tcdb_families": [],
    "top_gene_categories": [], "top_genes": [],
}
_MBG_SUMMARY = {
    **_GBM_SUMMARY, "by_gene": [], "top_metabolites": [],
    "top_metabolite_pathways": [], "by_element": [],
}
_LMA_SUMMARY = {
    "total_entries": 10, "total_matching": 0, "metabolite_count_total": 0,
    "by_organism": [], "by_value_kind": [], "by_compartment": [],
    "top_metric_types": [], "by_treatment_type": [],
    "by_background_factors": [], "by_growth_phase": [],
    "by_detection_status": [],
}
_MQA_DIAG = [{
    "assay_id": "a1", "name": "Assay a1", "value_kind": "numeric",
    "rankable": True, "organism_name": "Prochlorococcus MIT9313",
    "compartment": "whole_cell", "value_min": 0.0, "value_q1": 0.001,
    "value_median": 0.005, "value_q3": 0.05, "value_max": 0.5,
}]
_MQA_SUMMARY = {
    "total_matching": 0, "by_detection_status": [], "by_metric_bucket": [],
    "by_assay": [], "by_compartment": [], "by_organism": [],
    "filtered_value_min": None, "filtered_value_max": None,
}
_MFA_KIND = [{"assay_id": "a1", "value_kind": "boolean"}]
_MFA_SUMMARY = {
    "total_matching": 0, "by_value": [], "by_assay": [],
    "by_compartment": [], "by_organism": [],
}
_ABM_SUMMARY = {
    "total_matching": 0, "by_evidence_kind": [], "by_organism": [],
    "by_compartment": [], "by_assay": [], "by_detection_status": [],
    "by_flag_value": [], "metabolites_matched": 0,
}


def _tool_calls():
    """(name, call(conn, metabolite_ids, exclude_metabolite_ids), responses)."""
    from multiomics_explorer.api import functions as f
    return [
        ("list_metabolites",
         lambda c, m, x: f.list_metabolites(
             metabolite_ids=m, exclude_metabolite_ids=x, summary=True, conn=c),
         lambda: [[_LM_SUMMARY]]),
        ("genes_by_metabolite",
         lambda c, m, x: f.genes_by_metabolite(
             metabolite_ids=m or [_CANON], organism=_ORG,
             exclude_metabolite_ids=x, summary=True, conn=c),
         lambda: [[_GBM_SUMMARY]]),
        ("metabolites_by_gene",
         lambda c, m, x: f.metabolites_by_gene(
             ["PMM0963"], _ORG, metabolite_ids=m, exclude_metabolite_ids=x,
             summary=True, conn=c),
         lambda: [[_MBG_SUMMARY]]),
        ("list_metabolite_assays",
         lambda c, m, x: f.list_metabolite_assays(
             metabolite_ids=m, exclude_metabolite_ids=x, summary=True, conn=c),
         lambda: [[_LMA_SUMMARY]]),
        ("metabolites_by_quantifies_assay",
         lambda c, m, x: f.metabolites_by_quantifies_assay(
             assay_ids=["a1"], metabolite_ids=m, exclude_metabolite_ids=x,
             summary=True, conn=c),
         lambda: [list(_MQA_DIAG), [_MQA_SUMMARY]]),
        ("metabolites_by_flags_assay",
         lambda c, m, x: f.metabolites_by_flags_assay(
             assay_ids=["a1"], metabolite_ids=m, exclude_metabolite_ids=x,
             summary=True, conn=c),
         lambda: [list(_MFA_KIND), [_MFA_SUMMARY]]),
        ("assays_by_metabolite",
         lambda c, m, x: f.assays_by_metabolite(
             metabolite_ids=m or [_CANON], exclude_metabolite_ids=x,
             summary=True, conn=c),
         # existence probe (canonical id present) then summary
         lambda: [[{"metabolite_id": _CANON}], [_ABM_SUMMARY]]),
    ]


_TOOL_NAMES = [
    "list_metabolites", "genes_by_metabolite", "metabolites_by_gene",
    "list_metabolite_assays", "metabolites_by_quantifies_assay",
    "metabolites_by_flags_assay", "assays_by_metabolite",
]


def _tool(name):
    for n, call, responses in _tool_calls():
        if n == name:
            return call, responses
    raise KeyError(name)


class TestMetaboliteIdCoercionPerTool:
    """Every one of the 7 tools canonicalizes both `metabolite_ids` and
    `exclude_metabolite_ids` before the builders run, and carries
    `resolved_aliases` + `warnings` on its envelope."""

    @pytest.mark.parametrize("name", _TOOL_NAMES)
    def test_bare_metabolite_id_reaches_builder_canonical(self, name):
        call, responses = _tool(name)
        conn = _AliasConn(_ALIAS_MAP, responses())
        out = call(conn, [_BARE], None)
        params = conn.first_params_with("metabolite_ids")
        assert params["metabolite_ids"] == [_CANON]
        assert _BARE not in params["metabolite_ids"]
        assert out["resolved_aliases"] == {_BARE: [_CANON]}

    @pytest.mark.parametrize("name", _TOOL_NAMES)
    def test_bare_exclude_metabolite_id_reaches_builder_canonical(self, name):
        call, responses = _tool(name)
        conn = _AliasConn(_ALIAS_MAP, responses())
        out = call(conn, None, [_BARE_X])
        params = conn.first_params_with("exclude_metabolite_ids")
        assert params["exclude_metabolite_ids"] == [_CANON_X]
        assert out["resolved_aliases"] == {_BARE_X: [_CANON_X]}

    @pytest.mark.parametrize("name", _TOOL_NAMES)
    def test_envelope_carries_resolved_aliases_and_warnings(self, name):
        """Keys present (typed) even when nothing was coerced."""
        call, responses = _tool(name)
        conn = _AliasConn(_ALIAS_MAP, responses())
        out = call(conn, None, None)
        assert isinstance(out["resolved_aliases"], dict)
        assert out["resolved_aliases"] == {}
        assert isinstance(out["warnings"], list)
        # No bare input → no resolver round-trip.
        assert conn.alias_calls == []

    @pytest.mark.parametrize("name", _TOOL_NAMES)
    def test_both_params_share_one_resolved_aliases_map(self, name):
        call, responses = _tool(name)
        conn = _AliasConn(_ALIAS_MAP, responses())
        out = call(conn, [_BARE], [_BARE_X])
        assert out["resolved_aliases"] == {
            _BARE: [_CANON], _BARE_X: [_CANON_X],
        }

    @pytest.mark.parametrize("name", _TOOL_NAMES)
    def test_collision_warning_appended_to_envelope(self, name):
        both = ["kegg.compound:C00354", "kegg.compound:C05378"]
        call, responses = _tool(name)
        conn = _AliasConn({"CHEBI:16905": both}, responses())
        out = call(conn, ["CHEBI:16905"], None)
        params = conn.first_params_with("metabolite_ids")
        assert params["metabolite_ids"] == both
        assert any("CHEBI:16905" in w for w in out["warnings"])

    @pytest.mark.parametrize("name", _TOOL_NAMES)
    def test_unresolved_bare_id_forwarded_verbatim(self, name):
        """Unresolved input keeps the user's form so `not_found` reports it."""
        call, responses = _tool(name)
        conn = _AliasConn({}, responses())
        out = call(conn, ["C99999"], None)
        params = conn.first_params_with("metabolite_ids")
        assert "C99999" in params["metabolite_ids"]
        assert out["resolved_aliases"] == {}


class TestCoercionWarningsAppendNotReplace:
    """Alias-collision warnings seed the envelope `warnings` list and a
    tool's own auto-warning is appended after them — never overwritten."""

    def test_genes_by_metabolite_keeps_both_warnings(self):
        import copy
        from multiomics_explorer.api import functions as f
        both = ["kegg.compound:C00354", "kegg.compound:C05378"]
        summary = copy.deepcopy(_GBM_SUMMARY)
        # Inherited strictly dominates most_specific → native auto-warning.
        summary["by_metabolite"] = [{
            "metabolite_id": both[0], "name": "x",
            "transport_most_specific_rows": 1, "transport_inherited_rows": 3,
        }]
        conn = _AliasConn({"CHEBI:16905": both}, [[summary]])
        out = f.genes_by_metabolite(
            metabolite_ids=["CHEBI:16905"], organism=_ORG,
            summary=True, conn=conn,
        )
        assert len(out["warnings"]) == 2
        assert "CHEBI:16905" in out["warnings"][0]
        assert "inherited" in out["warnings"][1]


class TestListMetabolitesCoercionOverlap:
    def test_exclude_wins_when_overlap_only_visible_post_coercion(self):
        """`metabolite_ids=['C00064'], exclude_metabolite_ids=['kegg.compound:C00064']`
        — both reach the builder canonical so the Cypher set-difference sees
        the overlap (exclude wins)."""
        from multiomics_explorer.api.functions import list_metabolites
        conn = _AliasConn(_ALIAS_MAP, [[_LM_SUMMARY]])
        out = list_metabolites(
            metabolite_ids=[_BARE], exclude_metabolite_ids=[_CANON],
            summary=True, conn=conn,
        )
        params = conn.first_params_with("exclude_metabolite_ids")
        assert params["metabolite_ids"] == [_CANON]
        assert params["exclude_metabolite_ids"] == [_CANON]
        assert out["resolved_aliases"] == {_BARE: [_CANON]}
        # The coerced id exists → never reported as not_found.
        assert _BARE not in out["not_found"]["metabolite_ids"]

    def test_unresolved_bare_id_lands_in_not_found_verbatim(self):
        from multiomics_explorer.api.functions import list_metabolites
        # summary, then the existence probe returns nothing found
        conn = _AliasConn({}, [[_LM_SUMMARY], [{"found": []}]])
        out = list_metabolites(metabolite_ids=["C99999"], summary=True, conn=conn)
        assert out["not_found"]["metabolite_ids"] == ["C99999"]


# ---------------------------------------------------------------------------
# _cap_breakdowns — llm-review 2b.2 Task 4 (top-10 caps on detail breakdowns)
# ---------------------------------------------------------------------------
class TestCapBreakdownsHelper:
    """Pure-function tests for `api._cap_breakdowns`."""

    @staticmethod
    def _entries(n):
        return [{"count": i} for i in range(n)]

    def test_short_list_untouched_and_no_truncated_key(self):
        envelope = {"by_x": self._entries(5)}
        out = api._cap_breakdowns(envelope, ("by_x",), summary=False)
        assert len(out["by_x"]) == 5
        assert "by_x_truncated" not in out

    def test_exactly_ten_untouched_and_no_truncated_key(self):
        envelope = {"by_x": self._entries(10)}
        out = api._cap_breakdowns(envelope, ("by_x",), summary=False)
        assert len(out["by_x"]) == 10
        assert "by_x_truncated" not in out

    def test_over_ten_capped_to_first_ten_with_truncated_flag(self):
        full = self._entries(12)
        envelope = {"by_x": list(full)}
        out = api._cap_breakdowns(envelope, ("by_x",), summary=False)
        assert out["by_x"] == full[:10]
        assert out["by_x_truncated"] is True

    def test_summary_true_keeps_full_list_no_truncated_key(self):
        full = self._entries(12)
        envelope = {"by_x": list(full)}
        out = api._cap_breakdowns(envelope, ("by_x",), summary=True)
        assert out["by_x"] == full
        assert "by_x_truncated" not in out

    def test_missing_key_is_a_noop(self):
        envelope = {"other": 1}
        out = api._cap_breakdowns(envelope, ("by_x",), summary=False)
        assert "by_x" not in out
        assert "by_x_truncated" not in out

    def test_non_list_value_is_a_noop(self):
        envelope = {"by_x": {"a": 1}}
        out = api._cap_breakdowns(envelope, ("by_x",), summary=False)
        assert out["by_x"] == {"a": 1}
        assert "by_x_truncated" not in out

    def test_multiple_keys_capped_independently(self):
        envelope = {"a": self._entries(12), "b": self._entries(3)}
        out = api._cap_breakdowns(envelope, ("a", "b"), summary=False)
        assert len(out["a"]) == 10 and out["a_truncated"] is True
        assert len(out["b"]) == 3 and "b_truncated" not in out

    def test_returns_the_same_envelope_object(self):
        envelope = {"a": self._entries(12)}
        out = api._cap_breakdowns(envelope, ("a",), summary=False)
        assert out is envelope


# ---------------------------------------------------------------------------
class TestCapBreakdownsSharedModule:
    """backlog 2b.11: the helper lives in api/envelope.py; functions.py and
    analysis/enrichment.py both import it from there (no private cross-import)."""

    def test_public_module_exports(self):
        from multiomics_explorer.api import envelope
        assert envelope.BREAKDOWN_CAP == 10
        out = envelope.cap_breakdowns({"by_x": list(range(12))}, ("by_x",), summary=False)
        assert len(out["by_x"]) == 10 and out["by_x_truncated"] is True

    def test_functions_reexports_same_object(self):
        from multiomics_explorer.api import envelope
        assert api._cap_breakdowns is envelope.cap_breakdowns
        assert api._BREAKDOWN_CAP is envelope.BREAKDOWN_CAP

    def test_enrichment_imports_from_envelope_not_functions(self):
        import inspect
        from multiomics_explorer.analysis import enrichment
        src = inspect.getsource(enrichment)
        assert "from multiomics_explorer.api.envelope import cap_breakdowns" in src
        assert "from multiomics_explorer.api.functions import _cap_breakdowns" not in src


# Tool-level _cap_breakdowns wiring — one 12-entry test per affected tool.
# ---------------------------------------------------------------------------
class TestResolveGeneBreakdownCap:
    def _genes(self, n):
        return [
            {"locus_tag": f"PMM{i:04d}", "gene_name": "g", "product": "p",
             "organism_name": f"Organism {i:02d}"}
            for i in range(n)
        ]

    def test_by_organism_capped_at_ten(self, mock_conn):
        """Detail call (summary=False) caps by_organism at 10."""
        mock_conn.execute_query.return_value = self._genes(12)
        result = api.resolve_gene("PMM", limit=50, conn=mock_conn)
        assert len(result["by_organism"]) == 10
        assert result["by_organism_truncated"] is True

    def test_by_organism_untouched_under_the_cap(self, mock_conn):
        mock_conn.execute_query.return_value = self._genes(5)
        result = api.resolve_gene("PMM", limit=50, conn=mock_conn)
        assert len(result["by_organism"]) == 5
        assert "by_organism_truncated" not in result

    def test_summary_true_returns_full_by_organism_and_no_rows(self, mock_conn):
        """backlog 2b.7: summary=True uncaps by_organism; results empty."""
        mock_conn.execute_query.return_value = self._genes(12)
        result = api.resolve_gene("PMM", summary=True, conn=mock_conn)
        assert len(result["by_organism"]) == 12
        assert "by_organism_truncated" not in result
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["total_matching"] == 12
        assert result["truncated"] is True

    def test_summary_true_with_no_matches_is_not_truncated(self, mock_conn):
        mock_conn.execute_query.return_value = []
        result = api.resolve_gene("nope", summary=True, conn=mock_conn)
        assert result["results"] == [] and result["truncated"] is False


class TestGenesByFunctionBreakdownCap:
    def _summary_result(self, n=12):
        return [{
            "total_search_hits": 100, "total_matching": n,
            "score_max": 8.5, "score_median": 4.2,
            "by_organism": [
                {"item": f"Organism {i:02d}", "count": n - i} for i in range(n)
            ],
            "by_category": [{"item": "DNA replication", "count": n}],
        }]

    def test_by_organism_capped_on_detail_call(self, mock_conn):
        mock_conn.execute_query.side_effect = [self._summary_result(12), []]
        result = api.genes_by_function("DNA polymerase", conn=mock_conn)
        assert len(result["by_organism"]) == 10
        assert result["by_organism_truncated"] is True
        # Sorted desc by count before slicing — highest-count orgs survive.
        assert result["by_organism"][0]["organism_name"] == "Organism 00"

    def test_by_organism_full_list_on_summary_true(self, mock_conn):
        mock_conn.execute_query.side_effect = [self._summary_result(12)]
        result = api.genes_by_function("DNA polymerase", summary=True, conn=mock_conn)
        assert len(result["by_organism"]) == 12
        assert "by_organism_truncated" not in result


class TestListPublicationsBreakdownCap:
    _PUB_BASE = {
        "doi": "10.1234/test", "title": "Test", "authors": ["A"],
        "year": 2024, "journal": "J", "study_type": "S",
        "organisms": ["MED4"], "experiment_count": 1,
        "treatment_types": ["coculture"], "background_factors": [],
        "omics_types": ["RNASEQ"],
        "clustering_analysis_count": 0, "cluster_types": [],
    }

    @staticmethod
    def _summary_row(n=12):
        return {
            "total_entries": n, "total_matching": n,
            "by_organism": [
                {"item": f"Organism {i:02d}", "count": n - i} for i in range(n)
            ],
            "by_treatment_type": [], "by_background_factors": [],
            "by_omics_type": [],
        }

    def test_by_organism_capped_on_detail_call(self, mock_conn):
        """Detail call (summary=False) caps by_organism at 10."""
        mock_conn.execute_query.side_effect = [[self._summary_row(12)], [dict(self._PUB_BASE)]]
        result = api.list_publications(conn=mock_conn)
        assert len(result["by_organism"]) == 10
        assert result["by_organism_truncated"] is True
        assert result["by_organism"][0]["organism_name"] == "Organism 00"

    def test_summary_true_skips_detail_query_and_uncaps(self, mock_conn):
        """backlog 2b.7: summary=True runs only the summary Cypher, returns
        by_organism uncapped and no rows."""
        mock_conn.execute_query.side_effect = [[self._summary_row(12)]]
        result = api.list_publications(summary=True, conn=mock_conn)
        assert len(result["by_organism"]) == 12
        assert "by_organism_truncated" not in result
        assert result["results"] == [] and result["returned"] == 0
        assert result["truncated"] is True
        assert mock_conn.execute_query.call_count == 1

    def test_summary_true_no_matches_not_truncated(self, mock_conn):
        mock_conn.execute_query.side_effect = [[self._summary_row(0)]]
        result = api.list_publications(summary=True, conn=mock_conn)
        assert result["truncated"] is False and result["results"] == []


class TestListExperimentsBreakdownCap:
    def _summary_result(self, publication_freq):
        return [{
            "total_matching": 1, "time_course_count": 0,
            "by_organism": [], "by_treatment_type": [],
            "by_background_factors": [], "by_omics_type": [],
            "by_publication": publication_freq,
            "by_table_scope": [], "by_cluster_type": [], "by_growth_phase": [],
        }]

    def test_by_publication_capped_on_detail_call(self, mock_conn):
        pub_freq = [{"item": f"10.1234/p{i:02d}", "count": 12 - i} for i in range(12)]
        mock_conn.execute_query.side_effect = [
            self._summary_result(pub_freq),  # filtered summary
            self._summary_result(pub_freq),  # unfiltered total_entries
            [],  # detail rows
        ]
        result = api.list_experiments(conn=mock_conn)
        assert len(result["by_publication"]) == 10
        assert result["by_publication_truncated"] is True
        assert result["by_publication"][0]["publication_doi"] == "10.1234/p00"

    def test_by_publication_full_list_on_summary_true(self, mock_conn):
        pub_freq = [{"item": f"10.1234/p{i:02d}", "count": 12 - i} for i in range(12)]
        mock_conn.execute_query.side_effect = [
            self._summary_result(pub_freq),
            self._summary_result(pub_freq),
        ]
        result = api.list_experiments(summary=True, conn=mock_conn)
        assert len(result["by_publication"]) == 12
        assert "by_publication_truncated" not in result


class TestListOrganismsBreakdownCap:
    def _summary_row(self, metric_type_freq):
        return {
            "total_entries": 0, "total_matching": 0,
            "by_value_kind": [], "by_metric_type": metric_type_freq,
            "by_compartment": [], "by_cluster_type": [], "by_organism_type": [],
            "by_measurement_capability": {"has_metabolomics": 0, "no_metabolomics": 0},
            "top_annotation_capability": [],
        }

    def _wire(self, mock_conn, metric_type_freq):
        summary_row = self._summary_row(metric_type_freq)

        def _exec(cypher, **params):
            if "total_entries" in cypher:
                return [summary_row]
            return []  # detail / capability rows — unused by this test

        mock_conn.execute_query.side_effect = _exec

    def test_by_metric_type_capped_on_detail_call(self, mock_conn):
        freq = [{"item": f"metric_{i:02d}", "count": 12 - i} for i in range(12)]
        self._wire(mock_conn, freq)
        result = api.list_organisms(conn=mock_conn)
        assert len(result["by_metric_type"]) == 10
        assert result["by_metric_type_truncated"] is True
        assert result["by_metric_type"][0]["metric_type"] == "metric_00"

    def test_by_metric_type_full_list_on_summary_true(self, mock_conn):
        freq = [{"item": f"metric_{i:02d}", "count": 12 - i} for i in range(12)]
        self._wire(mock_conn, freq)
        result = api.list_organisms(summary=True, conn=mock_conn)
        assert len(result["by_metric_type"]) == 12
        assert "by_metric_type_truncated" not in result

    def test_top_annotation_capability_capped_and_ranked(self, mock_conn):
        """top_annotation_capability is ranked api-side over the matched
        capability rows, independent of the summary builder's own rollup."""
        rows = [
            {
                "organism_name": f"Organism {i:02d}", "organism_type": "genome_strain",
                "genus": "Genus", "species": None, "strain": None, "clade": None,
                "ncbi_taxon_id": None, "gene_count": 1000,
                "publication_count": 0, "experiment_count": 0,
                "treatment_types": [], "background_factors": [], "omics_types": [],
                "clustering_analysis_count": 0, "cluster_types": [],
                "derived_metric_count": 0, "derived_metric_value_kinds": [],
                "compartments": [], "reaction_count": 0,
                "catalyzed_metabolite_count": 0, "transported_metabolite_count": 0,
                "measured_metabolite_count": 0,
                "peptidase_gene_count": 12 - i,
                "nonpeptidase_homolog_gene_count": 0,
                "interpro_gene_count": 0, "ncbifam_gene_count": 0,
                "growth_phases": [],
            }
            for i in range(12)
        ]
        summary_row = self._summary_row([])
        summary_row["total_entries"] = summary_row["total_matching"] = len(rows)

        def _exec(cypher, **params):
            if "total_entries" in cypher:
                return [summary_row]
            return list(rows)

        mock_conn.execute_query.side_effect = _exec
        result = api.list_organisms(limit=50, conn=mock_conn)
        assert len(result["top_annotation_capability"]) == 10
        assert result["top_annotation_capability_truncated"] is True
        assert result["top_annotation_capability"][0]["organism_name"] == "Organism 00"

        mock_conn.execute_query.side_effect = _exec
        summary_result = api.list_organisms(summary=True, conn=mock_conn)
        assert len(summary_result["top_annotation_capability"]) == 12
        assert "top_annotation_capability_truncated" not in summary_result


class TestDifferentialExpressionByGeneBreakdownCap:
    def _organism_result(self):
        return [{"organisms": ["Prochlorococcus MED4"]}]

    def _global_summary(self):
        return [{
            "total_matching": 12, "matching_genes": 12,
            "rows_by_status": [{"item": "significant_up", "count": 12}],
            "rows_by_treatment_type": [], "rows_by_background_factors": [],
            "by_table_scope": [], "median_abs_log2fc": 1.0, "max_abs_log2fc": 2.0,
        }]

    def _experiment_summary(self, n=12):
        experiments = [
            {
                "experiment_id": f"exp{i:02d}", "treatment_type": ["nitrogen"],
                "table_scope": "all_detected_genes", "is_time_course": "single_time_point",
                "matching_genes": 1, "omics_type": "RNASEQ",
                "rows_by_status": [
                    {"item": "significant_up", "count": n - i},
                ],
            }
            for i in range(n)
        ]
        return [{"organism_name": "Prochlorococcus MED4", "experiments": experiments}]

    def _diagnostics_summary(self):
        return [{"top_categories": [], "not_found": [], "no_expression": [], "filtered_out": []}]

    def test_experiments_capped_and_sorted_desc_on_detail_call(self):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            self._organism_result(), self._global_summary(),
            self._experiment_summary(12), self._diagnostics_summary(), [],
        ]
        result = api.differential_expression_by_gene(organism="MED4", conn=mock_conn)
        assert len(result["experiments"]) == 10
        assert result["experiments_truncated"] is True
        # Sorted desc by significant row count — exp00 (count 12) leads.
        assert result["experiments"][0]["experiment_id"] == "exp00"
        # experiment_count reflects the FULL count, uncapped (backlog 2b.8:
        # the duplicate n_experiments key is gone).
        assert "n_experiments" not in result
        assert result["experiment_count"] == 12

    def test_experiments_full_list_on_summary_true(self):
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [
            self._organism_result(), self._global_summary(),
            self._experiment_summary(12), self._diagnostics_summary(),
        ]
        result = api.differential_expression_by_gene(
            organism="MED4", summary=True, conn=mock_conn,
        )
        assert len(result["experiments"]) == 12
        assert "experiments_truncated" not in result


class TestGenesByMetaboliteBreakdownCap:
    _METS = ["kegg.compound:C00086"]
    _ORG = "Prochlorococcus MED4"

    @pytest.fixture(autouse=True)
    def _mock_validate_organism_inputs(self, monkeypatch):
        monkeypatch.setattr(
            api, "_validate_organism_inputs",
            lambda organism, locus_tags, experiment_ids, conn: organism,
        )

    @staticmethod
    def _top_genes(n=12):
        return [
            {
                "locus_tag": f"PMM{i:04d}", "gene_name": None, "product": None,
                "gene_category": None, "reaction_count": n - i,
                "transporter_count": 0,
                "transport_substrate_resolution": None,
                "tcdb_evidence_score_max": None,
            }
            for i in range(n)
        ]

    def _summary_row(self, top_genes):
        return {
            "total_matching": 0, "gene_count_total": 0, "reaction_count_total": 0,
            "transporter_count_total": 0, "metabolite_count_total": 0,
            "rows_by_evidence_source": [], "rows_by_substrate_depth": [],
            "by_metabolite": [], "top_reactions": [], "top_tcdb_families": [],
            "top_gene_categories": [], "top_genes": top_genes,
        }

    def _mock_conn(self, top_genes):
        conn = MagicMock()
        conn.execute_query.side_effect = [[self._summary_row(top_genes)]] + [[]] * 10
        return conn

    def test_top_genes_capped_and_sorted_desc_on_detail_call(self):
        conn = self._mock_conn(self._top_genes(12))
        out = api.genes_by_metabolite(
            metabolite_ids=self._METS, organism=self._ORG, conn=conn,
        )
        assert len(out["top_genes"]) == 10
        assert out["top_genes_truncated"] is True
        assert out["top_genes"][0]["locus_tag"] == "PMM0000"

    def test_top_genes_full_list_on_summary_true(self):
        conn = self._mock_conn(self._top_genes(12))
        out = api.genes_by_metabolite(
            metabolite_ids=self._METS, organism=self._ORG, summary=True, conn=conn,
        )
        assert len(out["top_genes"]) == 12
        assert "top_genes_truncated" not in out


class TestMetabolitesByGeneBreakdownCap:
    _LOCUS = ["PMM0963", "PMM0964", "PMM0965"]
    _ORG = "Prochlorococcus MED4"

    @pytest.fixture(autouse=True)
    def _mock_validate_organism_inputs(self, monkeypatch):
        monkeypatch.setattr(
            api, "_validate_organism_inputs",
            lambda organism, locus_tags, experiment_ids, conn: organism,
        )

    @staticmethod
    def _top_pathways(n=12):
        """Deliberately shuffled input — the api layer must sort desc by
        gene_count, then asc by pathway_metabolite_count, before capping."""
        rows = [
            {
                "metabolite_pathway_id": f"kegg.pathway:ko{i:05d}",
                "metabolite_pathway_name": f"Pathway {i}",
                "gene_count": n - i,
                "pathway_reaction_count": 10,
                "pathway_metabolite_count": 5,
            }
            for i in range(n)
        ]
        # Shuffle so input order isn't already the expected output order.
        return [rows[i] for i in (1, 0, 3, 2, 5, 4, 7, 6, 9, 8, 11, 10)]

    @staticmethod
    def _by_element():
        # Mix of singleton (count < 2, dropped) and repeated elements
        # (count >= 2, kept), 12 kept entries to exercise the cap.
        singletons = [
            {"element": s, "metabolite_count": 1} for s in ("Se", "Br")
        ]
        kept = [
            {"element": f"E{i}", "metabolite_count": 13 - i} for i in range(12)
        ]
        return singletons + kept

    def _summary_row(self, top_pathways, by_element):
        return {
            "total_matching": 0, "gene_count_total": 0, "reaction_count_total": 0,
            "transporter_count_total": 0, "metabolite_count_total": 0,
            "rows_by_evidence_source": [], "rows_by_substrate_depth": [],
            "by_gene": [], "top_metabolites": [], "top_reactions": [],
            "top_tcdb_families": [], "top_gene_categories": [],
            "top_metabolite_pathways": top_pathways, "by_element": by_element,
        }

    def _mock_conn(self, top_pathways, by_element):
        conn = MagicMock()
        conn.execute_query.side_effect = [
            [self._summary_row(top_pathways, by_element)]
        ] + [[]] * 10
        return conn

    def test_top_metabolite_pathways_sorted_then_capped_on_detail_call(self):
        conn = self._mock_conn(self._top_pathways(12), [])
        out = api.metabolites_by_gene(self._LOCUS, self._ORG, conn=conn)
        assert len(out["top_metabolite_pathways"]) == 10
        assert out["top_metabolite_pathways_truncated"] is True
        # gene_count desc: ko00000 (gene_count=12) sorts first regardless
        # of the shuffled input order.
        assert out["top_metabolite_pathways"][0]["metabolite_pathway_id"] == "kegg.pathway:ko00000"

    def test_top_metabolite_pathways_full_list_on_summary_true(self):
        conn = self._mock_conn(self._top_pathways(12), [])
        out = api.metabolites_by_gene(
            self._LOCUS, self._ORG, summary=True, conn=conn,
        )
        assert len(out["top_metabolite_pathways"]) == 12
        assert "top_metabolite_pathways_truncated" not in out

    def test_by_element_drops_singletons_then_caps_on_detail_call(self):
        conn = self._mock_conn([], self._by_element())
        out = api.metabolites_by_gene(self._LOCUS, self._ORG, conn=conn)
        elements = {e["element"] for e in out["by_element"]}
        assert "Se" not in elements and "Br" not in elements
        assert len(out["by_element"]) == 10
        assert out["by_element_truncated"] is True
        assert out["by_element"][0]["element"] == "E0"

    def test_by_element_full_list_on_summary_true(self):
        conn = self._mock_conn([], self._by_element())
        out = api.metabolites_by_gene(
            self._LOCUS, self._ORG, summary=True, conn=conn,
        )
        elements = {e["element"] for e in out["by_element"]}
        assert "Se" not in elements and "Br" not in elements
        assert len(out["by_element"]) == 12
        assert "by_element_truncated" not in out


# ---------------------------------------------------------------------------
# llm-review 2b.3 Task 2: bare term / group ID coercion + locus-tag
# case-mismatch warning
# ---------------------------------------------------------------------------

class TestCoerceIds:
    """`_coerce_ids(ids, rules)` -> `(canonical_ids, resolved_aliases)`.

    Table-driven over every rule in `_TERM_ID_COERCIONS` /
    `_GROUP_ID_COERCIONS`, plus the shared no-op / passthrough behavior.
    """

    def _fn(self):
        from multiomics_explorer.api.functions import _coerce_ids
        return _coerce_ids

    def _term_rules(self):
        from multiomics_explorer.api.functions import _TERM_ID_COERCIONS
        return _TERM_ID_COERCIONS

    def _group_rules(self):
        from multiomics_explorer.api.functions import _GROUP_ID_COERCIONS
        return _GROUP_ID_COERCIONS

    # -- short-circuits ------------------------------------------------
    def test_none_passthrough(self):
        ids, aliases = self._fn()(None, self._term_rules())
        assert ids is None
        assert aliases == {}

    def test_empty_list_passthrough(self):
        ids, aliases = self._fn()([], self._term_rules())
        assert ids == []
        assert aliases == {}

    # -- table-driven: bare -> canonical, per ontology rule -------------
    @pytest.mark.parametrize("bare,canonical", [
        ("ko00910", "kegg.pathway:ko00910"),
        ("map00910", "kegg.pathway:ko00910"),
        ("00910", "kegg.pathway:ko00910"),
        ("K00001", "kegg.orthology:K00001"),
        ("k00001", "kegg.orthology:K00001"),
        ("0006979", "go:0006979"),
        ("GO:0006979", "go:0006979"),
        ("go:0006979", "go:0006979"),
        ("PF00004", "pfam:PF00004"),
        ("pf00004", "pfam:PF00004"),
        ("IPR000014", "interpro:IPR000014"),
        ("ipr000014", "interpro:IPR000014"),
        ("3.A.1", "tcdb:3.A.1"),
        ("3.A.1.1", "tcdb:3.A.1.1"),
        ("3.A.1.1.1", "tcdb:3.A.1.1.1"),
        ("1.1.1.1", "ec:1.1.1.1"),
        ("1.-.-.-", "ec:1.-.-.-"),
        ("GH13", "cazy:GH13"),
        ("AA10_1", "cazy:AA10_1"),
        ("S33", "merops.family:S33"),
        ("A01A", "merops.family:A01A"),
        ("TIGR00254", "ncbifam:TIGR00254"),
        ("NF000282", "ncbifam:NF000282"),
    ])
    def test_term_id_coercion_table(self, bare, canonical):
        ids, aliases = self._fn()([bare], self._term_rules())
        assert ids == [canonical]
        if bare == canonical:
            assert aliases == {}
        else:
            assert aliases == {bare: [canonical]}

    @pytest.mark.parametrize("canonical", [
        "kegg.pathway:ko00910", "kegg.orthology:K00001", "go:0006979",
        "pfam:PF00004", "interpro:IPR000014", "tcdb:3.A.1.1",
        "ec:1.1.1.1", "cazy:GH13", "merops.family:S33",
        "ncbifam:TIGR00254", "ncbifam:NF000282",
    ])
    def test_already_canonical_term_id_passes_through_unaliased(self, canonical):
        ids, aliases = self._fn()([canonical], self._term_rules())
        assert ids == [canonical]
        assert aliases == {}

    @pytest.mark.parametrize("bare,canonical", [
        ("CK_00000570", "cyanorak:CK_00000570"),
        ("COG0592@2", "eggnog:COG0592@2"),
        ("1MKTR@1212", "eggnog:1MKTR@1212"),
        ("1H29V@1129", "eggnog:1H29V@1129"),
    ])
    def test_group_id_coercion_table(self, bare, canonical):
        ids, aliases = self._fn()([bare], self._group_rules())
        assert ids == [canonical]
        assert aliases == {bare: [canonical]}

    @pytest.mark.parametrize("canonical", [
        "cyanorak:CK_00000570", "eggnog:COG0592@2", "eggnog:1MKTR@1212",
    ])
    def test_already_canonical_group_id_passes_through_unaliased(self, canonical):
        ids, aliases = self._fn()([canonical], self._group_rules())
        assert ids == [canonical]
        assert aliases == {}

    # -- non-matching input passes through unchanged --------------------
    def test_non_matching_input_passes_through(self):
        ids, aliases = self._fn()(["not-a-term-id"], self._term_rules())
        assert ids == ["not-a-term-id"]
        assert aliases == {}

    def test_non_matching_group_input_passes_through(self):
        ids, aliases = self._fn()(["not-a-group-id"], self._group_rules())
        assert ids == ["not-a-group-id"]
        assert aliases == {}

    # -- batch: order preserved, only coerced entries in the alias map --
    def test_batch_preserves_order_and_records_only_coerced(self):
        ids, aliases = self._fn()(
            ["ko00910", "kegg.pathway:ko00195", "bogus"], self._term_rules(),
        )
        assert ids == ["kegg.pathway:ko00910", "kegg.pathway:ko00195", "bogus"]
        assert aliases == {"ko00910": ["kegg.pathway:ko00910"]}


class TestCaseMismatchWarnings:
    """`_case_mismatch_warnings(conn, not_found)` — one extra lookup, no
    normalisation of the input locus_tags."""

    def _fn(self):
        from multiomics_explorer.api.functions import _case_mismatch_warnings
        return _case_mismatch_warnings

    def test_empty_not_found_no_query(self):
        conn = MagicMock()
        warnings = self._fn()(conn, [])
        assert warnings == []
        conn.execute_query.assert_not_called()

    def test_case_mismatch_produces_warning(self):
        conn = MagicMock()
        conn.execute_query.return_value = [{"locus_tag": "PMM0001"}]
        warnings = self._fn()(conn, ["pmm0001"])
        assert warnings == ["pmm0001 not found; 'PMM0001' differs only by case"]

    def test_no_case_match_no_warning(self):
        conn = MagicMock()
        conn.execute_query.return_value = []
        warnings = self._fn()(conn, ["totally_bogus_tag"])
        assert warnings == []

    def test_query_params_uppercased(self):
        conn = MagicMock()
        conn.execute_query.return_value = []
        self._fn()(conn, ["pmm0001", "sync_0002"])
        _, kwargs = conn.execute_query.call_args
        assert kwargs["upper"] == ["PMM0001", "SYNC_0002"]

    def test_self_match_suppressed(self):
        """A not_found tag that exactly matches a real locus_tag (organism-
        scoped not_found, e.g. metabolites_by_gene) must not warn — nothing
        actually differs by case."""
        conn = MagicMock()
        conn.execute_query.return_value = [{"locus_tag": "PMM0001"}]
        warnings = self._fn()(conn, ["PMM0001"])
        assert warnings == []
