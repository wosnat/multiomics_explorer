"""Tests for multiomics_explorer.analysis.frames — to_dataframe() utility."""

import warnings

import pandas as pd
import pytest

from multiomics_explorer.analysis.frames import to_dataframe


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
