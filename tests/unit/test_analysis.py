"""Unit tests for the analysis/ layer — no Neo4j needed.

Tests response_matrix pivot logic, direction classification,
group_map re-aggregation, and metadata columns.
"""

from unittest.mock import patch

import pytest

from multiomics_explorer.analysis import response_matrix


# ---------------------------------------------------------------------------
# Mock data helpers
# ---------------------------------------------------------------------------

def _make_api_result(results, organism_name="Test organism", not_found=None, no_expression=None):
    """Build a gene_response_profile-shaped dict for mocking."""
    return {
        "organism_name": organism_name,
        "genes_queried": len(results) + len(not_found or []) + len(no_expression or []),
        "genes_with_response": sum(1 for r in results if r.get("groups_responded")),
        "not_found": not_found or [],
        "no_expression": no_expression or [],
        "returned": len(results),
        "offset": 0,
        "truncated": False,
        "results": results,
    }


GENE_UP_ONLY = {
    "locus_tag": "GENE_A",
    "gene_name": "geneA",
    "product": "product A",
    "gene_category": "Category 1",
    "groups_responded": ["nitrogen_stress"],
    "groups_not_responded": ["light_stress"],
    "groups_not_known": ["iron_stress"],
    "response_summary": {
        "nitrogen_stress": {
            "experiments_total": 4, "experiments_tested": 4,
            "experiments_up": 3, "experiments_down": 0,
            "timepoints_total": 14, "timepoints_tested": 14,
            "timepoints_up": 8, "timepoints_down": 0,
            "up_best_rank": 3, "up_median_rank": 8.0, "up_max_log2fc": 5.7,
        },
        "light_stress": {
            "experiments_total": 2, "experiments_tested": 2,
            "experiments_up": 0, "experiments_down": 0,
            "timepoints_total": 6, "timepoints_tested": 6,
            "timepoints_up": 0, "timepoints_down": 0,
        },
    },
}

GENE_DOWN_ONLY = {
    "locus_tag": "GENE_B",
    "gene_name": "geneB",
    "product": "product B",
    "gene_category": "Category 2",
    "groups_responded": ["nitrogen_stress"],
    "groups_not_responded": [],
    "groups_not_known": ["light_stress", "iron_stress"],
    "response_summary": {
        "nitrogen_stress": {
            "experiments_total": 4, "experiments_tested": 2,
            "experiments_up": 0, "experiments_down": 2,
            "timepoints_total": 14, "timepoints_tested": 6,
            "timepoints_up": 0, "timepoints_down": 5,
            "down_best_rank": 12, "down_median_rank": 15.0, "down_max_log2fc": -3.0,
        },
    },
}

GENE_MIXED = {
    "locus_tag": "GENE_C",
    "gene_name": None,
    "product": None,
    "gene_category": "Category 1",
    "groups_responded": ["nitrogen_stress"],
    "groups_not_responded": ["light_stress"],
    "groups_not_known": ["iron_stress"],
    "response_summary": {
        "nitrogen_stress": {
            "experiments_total": 4, "experiments_tested": 4,
            "experiments_up": 2, "experiments_down": 1,
            "timepoints_total": 14, "timepoints_tested": 10,
            "timepoints_up": 4, "timepoints_down": 2,
            "up_best_rank": 5, "up_median_rank": 10.0, "up_max_log2fc": 3.1,
            "down_best_rank": 20, "down_median_rank": 20.0, "down_max_log2fc": -1.5,
        },
        "light_stress": {
            "experiments_total": 2, "experiments_tested": 2,
            "experiments_up": 0, "experiments_down": 0,
            "timepoints_total": 6, "timepoints_tested": 6,
            "timepoints_up": 0, "timepoints_down": 0,
        },
    },
}


# ---------------------------------------------------------------------------
# TestResponseMatrix
# ---------------------------------------------------------------------------

class TestResponseMatrix:
    def test_direction_classification(self):
        """Verify all 5 direction values are correctly classified."""
        api_result = _make_api_result([GENE_UP_ONLY, GENE_DOWN_ONLY, GENE_MIXED])

        with patch(
            "multiomics_explorer.analysis.expression.api.gene_response_profile",
            return_value=api_result,
        ):
            df = response_matrix(
                genes=["GENE_A", "GENE_B", "GENE_C"],
            )

        # Index should be keyed by locus_tag
        assert df.index.name == "locus_tag"

        # GENE_A: nitrogen_stress=up, light_stress=not_responded, iron_stress=not_known
        assert df.loc["GENE_A", "nitrogen_stress"] == "up"
        assert df.loc["GENE_A", "light_stress"] == "not_responded"
        assert df.loc["GENE_A", "iron_stress"] == "not_known"

        # GENE_B: nitrogen_stress=down, light_stress=not_known, iron_stress=not_known
        assert df.loc["GENE_B", "nitrogen_stress"] == "down"
        assert df.loc["GENE_B", "light_stress"] == "not_known"
        assert df.loc["GENE_B", "iron_stress"] == "not_known"

        # GENE_C: nitrogen_stress=mixed, light_stress=not_responded, iron_stress=not_known
        assert df.loc["GENE_C", "nitrogen_stress"] == "mixed"
        assert df.loc["GENE_C", "light_stress"] == "not_responded"
        assert df.loc["GENE_C", "iron_stress"] == "not_known"

    def test_metadata_columns(self):
        """Verify gene_name, product, gene_category metadata are in the DataFrame."""
        api_result = _make_api_result([GENE_UP_ONLY])

        with patch(
            "multiomics_explorer.analysis.expression.api.gene_response_profile",
            return_value=api_result,
        ):
            df = response_matrix(genes=["GENE_A"])

        assert df.loc["GENE_A", "gene_name"] == "geneA"
        assert df.loc["GENE_A", "product"] == "product A"
        assert df.loc["GENE_A", "gene_category"] == "Category 1"

    def test_passes_organism_and_experiment_ids(self):
        """Verify organism and experiment_ids are forwarded; group_by='treatment_type'."""
        api_result = _make_api_result([GENE_UP_ONLY])

        with patch(
            "multiomics_explorer.analysis.expression.api.gene_response_profile",
            return_value=api_result,
        ) as mock_fn:
            response_matrix(
                genes=["GENE_A"],
                organism="MED4",
                experiment_ids=["exp_1"],
            )

        mock_fn.assert_called_once()
        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs["organism"] == "MED4"
        assert call_kwargs["experiment_ids"] == ["exp_1"]
        assert call_kwargs["group_by"] == "treatment_type"

    def test_group_map_reaggregation(self):
        """Verify group_map causes re-aggregation by summing experiments_up/down."""
        # Gene with per-experiment response_summary
        gene_exp = {
            "locus_tag": "GENE_D",
            "gene_name": "geneD",
            "product": "product D",
            "gene_category": "Category 1",
            "groups_responded": ["exp_1", "exp_2", "exp_3"],
            "groups_not_responded": [],
            "groups_not_known": [],
            "response_summary": {
                "exp_1": {
                    "experiments_total": 1, "experiments_tested": 1,
                    "experiments_up": 1, "experiments_down": 0,
                    "timepoints_total": 3, "timepoints_tested": 3,
                    "timepoints_up": 2, "timepoints_down": 0,
                },
                "exp_2": {
                    "experiments_total": 1, "experiments_tested": 1,
                    "experiments_up": 0, "experiments_down": 1,
                    "timepoints_total": 3, "timepoints_tested": 3,
                    "timepoints_up": 0, "timepoints_down": 2,
                },
                "exp_3": {
                    "experiments_total": 1, "experiments_tested": 1,
                    "experiments_up": 1, "experiments_down": 0,
                    "timepoints_total": 3, "timepoints_tested": 3,
                    "timepoints_up": 1, "timepoints_down": 0,
                },
            },
        }
        api_result = _make_api_result([gene_exp])
        group_map = {"exp_1": "early", "exp_2": "early", "exp_3": "late"}

        with patch(
            "multiomics_explorer.analysis.expression.api.gene_response_profile",
            return_value=api_result,
        ) as mock_fn:
            df = response_matrix(
                genes=["GENE_D"],
                group_map=group_map,
            )

        # API must be called with group_by="experiment"
        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs["group_by"] == "experiment"
        assert set(call_kwargs["experiment_ids"]) == {"exp_1", "exp_2", "exp_3"}

        # early: exp_1 (up=1, down=0) + exp_2 (up=0, down=1) → up=1, down=1 → mixed
        assert df.loc["GENE_D", "early"] == "mixed"
        # late: exp_3 (up=1, down=0) → up=1, down=0 → up
        assert df.loc["GENE_D", "late"] == "up"

    def test_empty_result(self):
        """Verify empty DataFrame returned when no genes found."""
        api_result = _make_api_result([], not_found=["FAKE_GENE"])

        with patch(
            "multiomics_explorer.analysis.expression.api.gene_response_profile",
            return_value=api_result,
        ):
            df = response_matrix(genes=["FAKE_GENE"])

        assert df.empty
        assert df.index.name == "locus_tag"
