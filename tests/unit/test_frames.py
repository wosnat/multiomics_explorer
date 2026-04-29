"""Tests for multiomics_explorer.analysis.frames — to_dataframe() utility."""

import warnings

import pandas as pd
import pytest

from multiomics_explorer.analysis.frames import (
    analyses_to_dataframe,
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
                    "growth_phase": "exponential",
                    "gene_count": 180,
                    "genes_by_status": {
                        "significant_up": 40, "significant_down": 20, "not_significant": 120,
                    },
                },
                {
                    "timepoint": "T1", "timepoint_order": 1, "timepoint_hours": 2.0,
                    "growth_phase": "nutrient_limited",
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

    def test_tp_growth_phase_per_row(self):
        """tp_growth_phase column is populated from timepoints[].growth_phase per TP."""
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        exp1_rows = df[df["experiment_id"] == "exp1"].sort_values("timepoint_order")
        assert exp1_rows.iloc[0]["tp_growth_phase"] == "exponential"
        assert exp1_rows.iloc[1]["tp_growth_phase"] == "nutrient_limited"

    def test_tp_growth_phase_nan_for_non_time_course(self):
        """Non-time-course experiments have NaN tp_growth_phase (single-row branch)."""
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        exp2_row = df[df["experiment_id"] == "exp2"].iloc[0]
        assert pd.isna(exp2_row["tp_growth_phase"])


# ---------------------------------------------------------------------------
# Fixtures for analyses_to_dataframe
# ---------------------------------------------------------------------------

_ANALYSES_RESULT_COMPACT = {
    "total_entries": 2,
    "total_matching": 2,
    "returned": 2,
    "results": [
        {
            "analysis_id": "ana1",
            "name": "MED4 N-stress clusters",
            "organism_name": "MED4",
            "cluster_method": "kmeans",
            "cluster_type": "transcriptomic",
            "cluster_count": 2,
            "total_gene_count": 100,
            "treatment_type": ["nitrogen_stress"],
            "background_factors": [],
            "omics_type": "transcriptomics",
            "experiment_ids": ["exp1"],
            "clusters": [
                {"cluster_id": "cl1", "name": "Cluster 1", "member_count": 60},
                {"cluster_id": "cl2", "name": "Cluster 2", "member_count": 40},
            ],
        },
        {
            "analysis_id": "ana2",
            "name": "MED4 light clusters",
            "organism_name": "MED4",
            "cluster_method": "kmeans",
            "cluster_type": "transcriptomic",
            "cluster_count": 1,
            "total_gene_count": 80,
            "treatment_type": ["light_stress"],
            "background_factors": ["low_light"],
            "omics_type": "transcriptomics",
            "experiment_ids": ["exp2"],
            "clusters": [
                {"cluster_id": "cl3", "name": "Cluster 3", "member_count": 80},
            ],
        },
    ],
}

_ANALYSES_RESULT_VERBOSE = {
    "total_entries": 1,
    "total_matching": 1,
    "returned": 1,
    "results": [
        {
            "analysis_id": "ana1",
            "name": "MED4 N-stress clusters",
            "organism_name": "MED4",
            "cluster_method": "kmeans",
            "cluster_type": "transcriptomic",
            "cluster_count": 1,
            "total_gene_count": 60,
            "treatment_type": ["nitrogen_stress"],
            "background_factors": [],
            "omics_type": "transcriptomics",
            "experiment_ids": ["exp1"],
            "treatment": "N-deplete",
            "light_condition": "HL",
            "experimental_context": "lab",
            "clusters": [
                {
                    "cluster_id": "cl1",
                    "name": "Cluster 1",
                    "member_count": 60,
                    "functional_description": "ribosomal genes",
                    "expression_dynamics": "early induction",
                    "temporal_pattern": "Genes induced early under stress",
                },
            ],
        },
    ],
}


class TestAnalysesToDataFrame:
    """analyses_to_dataframe flattens analysis × cluster into one row per pair."""

    def test_flattens_analysis_x_cluster(self):
        """1 analysis with 2 clusters + 1 analysis with 1 cluster → 3 rows total."""
        df = analyses_to_dataframe(_ANALYSES_RESULT_COMPACT)
        assert len(df) == 3
        assert "analysis_id" in df.columns
        assert "cluster_id" in df.columns

    def test_analysis_fields_repeat_per_cluster(self):
        """Analysis-level scalar fields are repeated for each cluster row."""
        df = analyses_to_dataframe(_ANALYSES_RESULT_COMPACT)
        ana1_rows = df[df["analysis_id"] == "ana1"]
        assert len(ana1_rows) == 2
        assert set(ana1_rows["organism_name"].tolist()) == {"MED4"}
        assert set(ana1_rows["cluster_count"].tolist()) == {2}

    def test_compact_cluster_columns(self):
        """Compact mode produces cluster_id, cluster_name, cluster_member_count."""
        df = analyses_to_dataframe(_ANALYSES_RESULT_COMPACT)
        assert "cluster_id" in df.columns
        assert "cluster_name" in df.columns
        assert "cluster_member_count" in df.columns

    def test_cluster_values_correct(self):
        """cluster_id / cluster_member_count values match the source data."""
        df = analyses_to_dataframe(_ANALYSES_RESULT_COMPACT)
        cl1_row = df[df["cluster_id"] == "cl1"].iloc[0]
        assert cl1_row["cluster_member_count"] == 60
        cl3_row = df[df["cluster_id"] == "cl3"].iloc[0]
        assert cl3_row["cluster_member_count"] == 80

    def test_empty_results(self):
        """Empty results list → empty DataFrame."""
        df = analyses_to_dataframe({"results": []})
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_no_results_key_raises(self):
        """Missing 'results' key → ValueError."""
        with pytest.raises(ValueError, match="results"):
            analyses_to_dataframe({"data": []})

    def test_verbose_cluster_fields(self):
        """Verbose fields present → columns for functional/expression_dynamics/temporal_pattern."""
        df = analyses_to_dataframe(_ANALYSES_RESULT_VERBOSE)
        assert "cluster_functional_description" in df.columns
        assert "cluster_expression_dynamics" in df.columns
        assert "cluster_temporal_pattern" in df.columns
        row = df.iloc[0]
        assert row["cluster_functional_description"] == "ribosomal genes"
        assert row["cluster_expression_dynamics"] == "early induction"

    def test_no_nested_columns(self):
        """Output is CSV-safe — no list or dict values remain."""
        df = analyses_to_dataframe(_ANALYSES_RESULT_COMPACT)
        for col in df.columns:
            for val in df[col]:
                assert not isinstance(val, (list, dict)), (
                    f"Column '{col}' contains a {type(val).__name__} value"
                )

    def test_clusters_column_absent_from_output(self):
        """The raw 'clusters' column should not appear in the output."""
        df = analyses_to_dataframe(_ANALYSES_RESULT_COMPACT)
        assert "clusters" not in df.columns


# ---------------------------------------------------------------------------
# Tests for enrichment output
# ---------------------------------------------------------------------------


class TestToDataFrameEnrichmentOutput:
    """Default to_dataframe must handle pathway_enrichment envelopes cleanly."""

    @staticmethod
    def _envelope(verbose=False):
        row = {
            "cluster": "exp1|T0|up",
            "experiment_id": "exp1",
            "name": "exp1_name",
            "timepoint": "T0",
            "timepoint_hours": 0.0,
            "timepoint_order": 0,
            "direction": "up",
            "omics_type": "transcriptomics",
            "table_scope": "rna_all",
            "treatment_type": ["N_stress"],
            "background_factors": None,
            "is_time_course": True,
            "term_id": "P",
            "term_name": "Pathway P",
            "level": 1,
            "gene_ratio": "2/10",
            "gene_ratio_numeric": 0.2,
            "bg_ratio": "3/100",
            "bg_ratio_numeric": 0.03,
            "rich_factor": 0.67,
            "fold_enrichment": 6.67,
            "pvalue": 1e-5,
            "p_adjust": 1e-4,
            "count": 2,
            "bg_count": 3,
            "signed_score": 4.0,
        }
        if verbose:
            row["foreground_gene_ids"] = ["PMM0001", "PMM0002"]
            row["background_gene_ids"] = ["PMM0003"]
        return {"results": [row]}

    def test_compact_rows_produce_clean_dataframe(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            df = to_dataframe(self._envelope(verbose=False))
            assert not any(issubclass(w.category, UserWarning) for w in caught), (
                f"Unexpected warnings: {[str(w.message) for w in caught]}"
            )
        assert len(df) == 1
        assert df.loc[0, "treatment_type"] == "N_stress"

    def test_verbose_rows_with_gene_id_lists(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            df = to_dataframe(self._envelope(verbose=True))
            assert not any(issubclass(w.category, UserWarning) for w in caught)
        row = df.iloc[0]
        assert "PMM0001" in str(row["foreground_gene_ids"])
        assert "PMM0003" in str(row["background_gene_ids"])
