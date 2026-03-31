"""Tests for multiomics_explorer.analysis.frames — to_dataframe() utility."""

import warnings

import pandas as pd
import pytest

from multiomics_explorer.analysis.frames import (
    experiments_to_dataframe,
    profile_summary_to_dataframe,
    to_dataframe,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PROFILE_RESULT = {
    "organism_name": "Test organism",
    "genes_queried": 2,
    "genes_with_response": 2,
    "not_found": [],
    "no_expression": [],
    "returned": 2,
    "offset": 0,
    "truncated": False,
    "results": [
        {
            "locus_tag": "GENE_A",
            "gene_name": "geneA",
            "product": "product A",
            "gene_category": "Category 1",
            "groups_responded": ["nitrogen_stress"],
            "groups_not_responded": ["light_stress"],
            "groups_tested_not_responded": [],
            "groups_not_known": [],
            "response_summary": {
                "nitrogen_stress": {
                    "experiments_total": 4, "experiments_tested": 4,
                    "experiments_up": 3, "experiments_down": 0,
                    "timepoints_total": 14, "timepoints_tested": 14,
                    "timepoints_up": 8, "timepoints_down": 0,
                    "up_best_rank": 3, "up_median_rank": 8.0,
                    "up_max_log2fc": 5.7,
                },
                "light_stress": {
                    "experiments_total": 2, "experiments_tested": 2,
                    "experiments_up": 0, "experiments_down": 0,
                    "timepoints_total": 6, "timepoints_tested": 6,
                    "timepoints_up": 0, "timepoints_down": 0,
                },
            },
        },
        {
            "locus_tag": "GENE_B",
            "gene_name": "geneB",
            "product": "product B",
            "gene_category": "Category 2",
            "groups_responded": ["nitrogen_stress"],
            "groups_not_responded": [],
            "groups_tested_not_responded": [],
            "groups_not_known": [],
            "response_summary": {
                "nitrogen_stress": {
                    "experiments_total": 4, "experiments_tested": 2,
                    "experiments_up": 0, "experiments_down": 2,
                    "timepoints_total": 14, "timepoints_tested": 6,
                    "timepoints_up": 0, "timepoints_down": 5,
                    "down_best_rank": 12, "down_median_rank": 15.0,
                    "down_max_log2fc": -3.0,
                },
            },
        },
    ],
}

_EXPERIMENTS_RESULT = {
    "total_entries": 3,
    "total_matching": 2,
    "returned": 2,
    "results": [
        {
            "experiment_id": "exp1",
            "experiment_name": "N-stress timecourse",
            "organism_name": "MED4",
            "treatment_type": "nitrogen_stress",
            "is_time_course": True,
            "gene_count": 200,
            "genes_by_status": {
                "significant_up": 50, "significant_down": 30, "not_significant": 120,
            },
            "timepoints": [
                {
                    "timepoint": "T0", "timepoint_order": 0, "timepoint_hours": 0.0,
                    "gene_count": 180,
                    "genes_by_status": {
                        "significant_up": 40, "significant_down": 20, "not_significant": 120,
                    },
                },
                {
                    "timepoint": "T1", "timepoint_order": 1, "timepoint_hours": 2.0,
                    "gene_count": 200,
                    "genes_by_status": {
                        "significant_up": 50, "significant_down": 30, "not_significant": 120,
                    },
                },
            ],
        },
        {
            "experiment_id": "exp2",
            "experiment_name": "Light snapshot",
            "organism_name": "MED4",
            "treatment_type": "light_stress",
            "is_time_course": False,
            "gene_count": 150,
            "genes_by_status": {
                "significant_up": 20, "significant_down": 10, "not_significant": 120,
            },
        },
    ],
}


class TestToDataFrameFlat:
    """Flat scalar result dicts produce clean DataFrames."""

    def test_flat_scalars(self):
        result = {
            "results": [
                {"gene": "MIT9313_0001", "log2fc": 1.5, "padj": 0.01},
                {"gene": "MIT9313_0002", "log2fc": -0.8, "padj": 0.05},
            ]
        }
        df = to_dataframe(result)
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["gene", "log2fc", "padj"]
        assert len(df) == 2
        assert df["gene"].tolist() == ["MIT9313_0001", "MIT9313_0002"]
        assert df["log2fc"].tolist() == [1.5, -0.8]

    def test_empty_results(self):
        result = {"results": []}
        df = to_dataframe(result)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_missing_results_key(self):
        with pytest.raises(ValueError, match="results"):
            to_dataframe({"data": []})


class TestToDataFrameListColumns:
    """List values in result dicts are joined with ' | '."""

    def test_list_columns_joined(self):
        result = {
            "results": [
                {"gene": "MIT9313_0001", "tags": ["iron", "stress"]},
                {"gene": "MIT9313_0002", "tags": ["photosynthesis"]},
            ]
        }
        df = to_dataframe(result)
        assert df["tags"].tolist() == ["iron | stress", "photosynthesis"]

    def test_list_column_with_none(self):
        result = {
            "results": [
                {"gene": "MIT9313_0001", "tags": ["iron", "stress"]},
                {"gene": "MIT9313_0002", "tags": None},
            ]
        }
        df = to_dataframe(result)
        assert df["tags"].iloc[0] == "iron | stress"
        assert pd.isna(df["tags"].iloc[1])

    def test_empty_list_becomes_empty_string(self):
        result = {
            "results": [
                {"gene": "MIT9313_0001", "tags": []},
                {"gene": "MIT9313_0002", "tags": ["photosynthesis"]},
            ]
        }
        df = to_dataframe(result)
        assert df["tags"].iloc[0] == ""
        assert df["tags"].iloc[1] == "photosynthesis"


class TestToDataFrameDictColumns:
    """Dict values in result dicts are expanded into prefixed columns."""

    def test_dict_columns_inlined(self):
        result = {
            "results": [
                {"gene": "MIT9313_0001", "stats": {"mean": 1.5, "std": 0.3}},
                {"gene": "MIT9313_0002", "stats": {"mean": -0.8, "std": 0.1}},
            ]
        }
        df = to_dataframe(result)
        assert "stats" not in df.columns
        assert "stats_mean" in df.columns
        assert "stats_std" in df.columns
        assert df["stats_mean"].tolist() == [1.5, -0.8]
        assert df["stats_std"].tolist() == [0.3, 0.1]

    def test_dict_column_with_none(self):
        result = {
            "results": [
                {"gene": "MIT9313_0001", "stats": {"mean": 1.5, "std": 0.3}},
                {"gene": "MIT9313_0002", "stats": None},
            ]
        }
        df = to_dataframe(result)
        assert "stats" not in df.columns
        assert "stats_mean" in df.columns
        assert df["stats_mean"].iloc[0] == 1.5
        assert pd.isna(df["stats_mean"].iloc[1])

    def test_dict_column_with_varying_keys(self):
        result = {
            "results": [
                {"gene": "MIT9313_0001", "stats": {"mean": 1.5, "std": 0.3}},
                {"gene": "MIT9313_0002", "stats": {"mean": -0.8}},
            ]
        }
        df = to_dataframe(result)
        assert "stats_mean" in df.columns
        assert "stats_std" in df.columns
        assert df["stats_std"].iloc[0] == 0.3
        assert pd.isna(df["stats_std"].iloc[1])

    def test_nested_dict_values_dropped_with_warning(self):
        result = {
            "results": [
                {
                    "gene": "MIT9313_0001",
                    "profile": {"nested": {"deep": 1}},
                },
            ]
        }
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            df = to_dataframe(result)
        assert "profile" not in df.columns
        assert any(issubclass(w.category, UserWarning) for w in caught)


class TestToDataFrameWarnings:
    """Dropped columns produce meaningful UserWarning messages."""

    def test_mixed_list_and_scalar_dropped(self):
        result = {
            "results": [
                {"gene": "MIT9313_0001", "data": ["iron", "stress"]},
                {"gene": "MIT9313_0002", "data": "photosynthesis"},
            ]
        }
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            df = to_dataframe(result)
        assert "data" not in df.columns
        assert any(issubclass(w.category, UserWarning) for w in caught)

    def test_response_summary_suggests_dedicated_function(self):
        result = {
            "results": [
                {
                    "gene": "MIT9313_0001",
                    "response_summary": {"responded": 3, "details": [1, 2, 3]},
                },
            ]
        }
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            df = to_dataframe(result)
        assert "response_summary" not in df.columns
        messages = [str(w.message) for w in caught if issubclass(w.category, UserWarning)]
        assert any("profile_summary_to_dataframe()" in m for m in messages)

    def test_timepoints_suggests_dedicated_function(self):
        result = {
            "results": [
                {
                    "gene": "MIT9313_0001",
                    "timepoints": [{"t": 0, "val": 1.0}, {"t": 30, "val": 2.0}],
                },
            ]
        }
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            df = to_dataframe(result)
        assert "timepoints" not in df.columns
        messages = [str(w.message) for w in caught if issubclass(w.category, UserWarning)]
        assert any("experiments_to_dataframe()" in m for m in messages)

    def test_unknown_nested_generic_warning(self):
        result = {
            "results": [
                {
                    "gene": "MIT9313_0001",
                    "unknown_complex": {"nested": {"deep": 1}},
                },
            ]
        }
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            df = to_dataframe(result)
        assert "unknown_complex" not in df.columns
        messages = [str(w.message) for w in caught if issubclass(w.category, UserWarning)]
        assert any("file an issue" in m for m in messages)


class TestProfileSummaryToDataFrame:
    """profile_summary_to_dataframe expands gene × group into one row per pair."""

    def test_shape_and_columns(self):
        df = profile_summary_to_dataframe(_PROFILE_RESULT)
        # GENE_A has 2 groups, GENE_B has 1 → 3 rows
        assert len(df) == 3
        for col in ("locus_tag", "gene_name", "group", "experiments_up"):
            assert col in df.columns

    def test_directional_fields_nan_when_absent(self):
        df = profile_summary_to_dataframe(_PROFILE_RESULT)
        row = df[(df["locus_tag"] == "GENE_A") & (df["group"] == "light_stress")].iloc[0]
        assert pd.isna(row["up_best_rank"])
        assert pd.isna(row["down_best_rank"])

    def test_directional_fields_present_when_available(self):
        df = profile_summary_to_dataframe(_PROFILE_RESULT)
        row = df[(df["locus_tag"] == "GENE_A") & (df["group"] == "nitrogen_stress")].iloc[0]
        assert row["up_best_rank"] == 3
        assert row["up_max_log2fc"] == 5.7

    def test_csv_safe(self):
        df = profile_summary_to_dataframe(_PROFILE_RESULT)
        for col in df.columns:
            for val in df[col]:
                assert not isinstance(val, (list, dict)), (
                    f"Column '{col}' contains a {type(val).__name__} value"
                )

    def test_wrong_result_raises(self):
        with pytest.raises(ValueError, match="response_summary"):
            profile_summary_to_dataframe({"results": [{"locus_tag": "A", "score": 1.0}]})

    def test_empty_results(self):
        df = profile_summary_to_dataframe({"results": []})
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0


class TestExperimentsToDataFrame:
    """experiments_to_dataframe expands experiment × timepoint into one row per pair."""

    def test_time_course_expanded(self):
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        exp1_rows = df[df["experiment_id"] == "exp1"]
        assert len(exp1_rows) == 2
        assert set(exp1_rows["timepoint"].tolist()) == {"T0", "T1"}

    def test_non_time_course_single_row(self):
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        exp2_rows = df[df["experiment_id"] == "exp2"]
        assert len(exp2_rows) == 1
        assert pd.isna(exp2_rows.iloc[0]["timepoint"])

    def test_timepoint_genes_by_status_inlined(self):
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        t0_row = df[(df["experiment_id"] == "exp1") & (df["timepoint"] == "T0")].iloc[0]
        assert t0_row["tp_significant_up"] == 40
        assert t0_row["tp_significant_down"] == 20
        assert t0_row["tp_not_significant"] == 120

    def test_experiment_genes_by_status_inlined(self):
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        exp2_row = df[df["experiment_id"] == "exp2"].iloc[0]
        assert exp2_row["genes_by_status_significant_up"] == 20

    def test_no_nested_columns(self):
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        for col in df.columns:
            for val in df[col]:
                assert not isinstance(val, (list, dict)), (
                    f"Column '{col}' contains a {type(val).__name__} value"
                )

    def test_empty_results(self):
        df = experiments_to_dataframe({"results": []})
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_missing_results_key(self):
        with pytest.raises(ValueError, match="results"):
            experiments_to_dataframe({"data": []})
