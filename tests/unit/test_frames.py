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
