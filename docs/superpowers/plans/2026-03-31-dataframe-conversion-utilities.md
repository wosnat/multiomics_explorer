# DataFrame Conversion Utilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `to_dataframe()`, `profile_summary_to_dataframe()`, and `experiments_to_dataframe()` so any API result can be converted to a CSV-safe DataFrame with one call.

**Architecture:** A new `analysis/frames.py` module with three public functions. `to_dataframe()` is fully generic (no hardcoded column names) — it inspects cell types at runtime to join lists, inline dicts, and warn on nested structures. Two dedicated unpackers handle secondary tables from `gene_response_profile` and `list_experiments`.

**Tech Stack:** Python, pandas, warnings module. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-31-utils-docs-and-response-profile-design.md` Part 3.

---

### Task 1: `to_dataframe` — scaffold + flat pass-through

**Files:**
- Create: `multiomics_explorer/analysis/frames.py`
- Modify: `multiomics_explorer/analysis/__init__.py`
- Create: `tests/unit/test_frames.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for analysis/frames.py — no Neo4j needed."""

import warnings

import pandas as pd
import pytest

from multiomics_explorer.analysis import to_dataframe


class TestToDataFrameFlat:
    def test_flat_scalars(self):
        """Flat result dicts produce a clean DataFrame."""
        result = {
            "total_matching": 2,
            "results": [
                {"locus_tag": "A", "gene_name": "gA", "score": 1.5},
                {"locus_tag": "B", "gene_name": "gB", "score": 2.0},
            ],
        }
        df = to_dataframe(result)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ["locus_tag", "gene_name", "score"]
        assert df["score"].dtype == float

    def test_empty_results(self):
        """Empty results list returns empty DataFrame."""
        result = {"results": []}
        df = to_dataframe(result)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_missing_results_key(self):
        """Missing 'results' key raises ValueError."""
        with pytest.raises(ValueError, match="results"):
            to_dataframe({"total_matching": 5})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_frames.py -v`
Expected: ImportError — `cannot import name 'to_dataframe'`

- [ ] **Step 3: Write minimal implementation + wire exports**

`multiomics_explorer/analysis/frames.py`:
```python
"""DataFrame conversion utilities for API results.

Converts API result dicts into CSV-safe DataFrames. Handles list columns
(joins with ' | '), dict columns (inlines as prefixed columns), and
nested structures (drops with warning).
"""

from __future__ import annotations

import warnings

import pandas as pd


def to_dataframe(result: dict) -> pd.DataFrame:
    """Convert any API result dict to a flat, CSV-safe DataFrame.

    Args:
        result: Dict returned by any API function. Must contain a
                'results' key with a list of row dicts.

    Returns:
        DataFrame with one row per result. List columns joined with
        ' | ', dict columns inlined as prefixed columns, deeper
        nesting dropped with warnings.

    Raises:
        ValueError: If result has no 'results' key.
    """
    if "results" not in result:
        raise ValueError(
            "Expected a dict with a 'results' key. "
            "Got keys: " + ", ".join(sorted(result.keys()))
        )

    rows = result["results"]
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return _flatten_columns(df)


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Detect and flatten list/dict columns in-place."""
    for col in list(df.columns):
        if df[col].dtype != object:
            continue
        non_null = df[col].dropna()
        if non_null.empty:
            continue
        _process_object_column(df, col, non_null)
    return df
```

Add to `multiomics_explorer/analysis/__init__.py`:
```python
from multiomics_explorer.analysis.frames import (
    to_dataframe,
)
```

And update `__all__`:
```python
__all__ = ["response_matrix", "gene_set_compare", "to_dataframe"]
```

For the initial pass, `_process_object_column` is a no-op stub:

```python
def _process_object_column(
    df: pd.DataFrame, col: str, non_null: pd.Series,
) -> None:
    """Process a single object-typed column. Stub for flat pass-through."""
    pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_frames.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/frames.py multiomics_explorer/analysis/__init__.py tests/unit/test_frames.py
git commit -m "feat(analysis): scaffold to_dataframe with flat pass-through"
```

---

### Task 2: `to_dataframe` — list column joining

**Files:**
- Modify: `multiomics_explorer/analysis/frames.py`
- Modify: `tests/unit/test_frames.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_frames.py`:

```python
class TestToDataFrameListColumns:
    def test_list_columns_joined(self):
        """List-valued columns are joined with ' | '."""
        result = {
            "results": [
                {"id": "A", "tags": ["x", "y", "z"]},
                {"id": "B", "tags": ["w"]},
            ],
        }
        df = to_dataframe(result)
        assert df.loc[0, "tags"] == "x | y | z"
        assert df.loc[1, "tags"] == "w"

    def test_list_column_with_none(self):
        """None values in list columns are preserved as NaN."""
        result = {
            "results": [
                {"id": "A", "tags": ["x", "y"]},
                {"id": "B", "tags": None},
            ],
        }
        df = to_dataframe(result)
        assert df.loc[0, "tags"] == "x | y"
        assert pd.isna(df.loc[1, "tags"])

    def test_empty_list_becomes_empty_string(self):
        """Empty list becomes empty string."""
        result = {
            "results": [
                {"id": "A", "tags": []},
            ],
        }
        df = to_dataframe(result)
        assert df.loc[0, "tags"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_frames.py::TestToDataFrameListColumns -v`
Expected: FAIL — list values are not joined yet

- [ ] **Step 3: Implement list joining in `_process_object_column`**

Replace the stub `_process_object_column` in `frames.py`:

```python
_LIST_DELIMITER = " | "


def _process_object_column(
    df: pd.DataFrame, col: str, non_null: pd.Series,
) -> None:
    """Process a single object-typed column.

    - All non-null values are lists → join with _LIST_DELIMITER
    - All non-null values are dicts → inline as prefixed columns (TODO)
    - Mixed or deeper nesting → drop with warning (TODO)
    """
    if all(isinstance(v, list) for v in non_null):
        df[col] = df[col].apply(
            lambda x: _LIST_DELIMITER.join(str(i) for i in x)
            if isinstance(x, list) else x
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_frames.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/frames.py tests/unit/test_frames.py
git commit -m "feat(analysis): to_dataframe joins list columns with ' | '"
```

---

### Task 3: `to_dataframe` — dict column inlining

**Files:**
- Modify: `multiomics_explorer/analysis/frames.py`
- Modify: `tests/unit/test_frames.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_frames.py`:

```python
class TestToDataFrameDictColumns:
    def test_dict_columns_inlined(self):
        """Dict-valued columns are expanded into prefixed columns."""
        result = {
            "results": [
                {"id": "exp1", "genes_by_status": {"up": 5, "down": 3, "ns": 100}},
                {"id": "exp2", "genes_by_status": {"up": 10, "down": 1, "ns": 50}},
            ],
        }
        df = to_dataframe(result)
        assert "genes_by_status" not in df.columns
        assert df.loc[0, "genes_by_status_up"] == 5
        assert df.loc[0, "genes_by_status_down"] == 3
        assert df.loc[0, "genes_by_status_ns"] == 100
        assert df.loc[1, "genes_by_status_up"] == 10

    def test_dict_column_with_none(self):
        """None values in dict columns become NaN in expanded columns."""
        result = {
            "results": [
                {"id": "exp1", "stats": {"a": 1, "b": 2}},
                {"id": "exp2", "stats": None},
            ],
        }
        df = to_dataframe(result)
        assert "stats" not in df.columns
        assert df.loc[0, "stats_a"] == 1
        assert pd.isna(df.loc[1, "stats_a"])

    def test_dict_column_with_varying_keys(self):
        """Dicts with different key sets produce union of columns, NaN for missing."""
        result = {
            "results": [
                {"id": "A", "info": {"x": 1}},
                {"id": "B", "info": {"x": 2, "y": 3}},
            ],
        }
        df = to_dataframe(result)
        assert df.loc[0, "info_x"] == 1
        assert pd.isna(df.loc[0, "info_y"])
        assert df.loc[1, "info_y"] == 3

    def test_nested_dict_values_dropped_with_warning(self):
        """Dicts whose values are themselves dicts/lists are dropped with warning."""
        result = {
            "results": [
                {"id": "A", "deep": {"inner": {"x": 1}}},
            ],
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            df = to_dataframe(result)
        assert "deep" not in df.columns
        assert len(w) == 1
        assert "deep" in str(w[0].message)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_frames.py::TestToDataFrameDictColumns -v`
Expected: FAIL — dict values remain as objects

- [ ] **Step 3: Implement dict inlining**

Update `_process_object_column` in `frames.py`:

```python
# Lookup: dropped column name → suggested dedicated function
_DEDICATED_FUNCTIONS: dict[str, str] = {
    "response_summary": "profile_summary_to_dataframe()",
    "timepoints": "experiments_to_dataframe()",
}


def _process_object_column(
    df: pd.DataFrame, col: str, non_null: pd.Series,
) -> None:
    """Process a single object-typed column.

    - All non-null values are lists → join with _LIST_DELIMITER
    - All non-null values are flat dicts → inline as prefixed columns
    - Mixed or deeper nesting → drop with warning
    """
    if all(isinstance(v, list) for v in non_null):
        df[col] = df[col].apply(
            lambda x: _LIST_DELIMITER.join(str(i) for i in x)
            if isinstance(x, list) else x
        )
        return

    if all(isinstance(v, dict) for v in non_null):
        # Check if any dict value is itself a dict or list (deeper nesting)
        has_nesting = any(
            isinstance(inner_v, (dict, list))
            for v in non_null
            for inner_v in v.values()
        )
        if has_nesting:
            _drop_with_warning(df, col)
            return

        # Inline: expand each dict into prefixed columns
        expanded = df[col].apply(
            lambda x: x if isinstance(x, dict) else {}
        )
        expanded_df = pd.DataFrame(expanded.tolist(), index=df.index)
        expanded_df.columns = [f"{col}_{k}" for k in expanded_df.columns]
        # Insert expanded columns at the position of the original
        col_idx = df.columns.get_loc(col)
        df.drop(columns=[col], inplace=True)
        for i, new_col in enumerate(expanded_df.columns):
            df.insert(col_idx + i, new_col, expanded_df[new_col])
        return

    # Mixed types — drop with warning
    _drop_with_warning(df, col)


def _drop_with_warning(df: pd.DataFrame, col: str) -> None:
    """Drop a column and emit a UserWarning with suggestion if available."""
    suggestion = _DEDICATED_FUNCTIONS.get(col)
    if suggestion:
        msg = (
            f"Dropped nested column '{col}'. "
            f"Use {suggestion} to extract it as a separate DataFrame."
        )
    else:
        msg = f"Dropped nested column '{col}' — flatten manually or file an issue."
    warnings.warn(msg, UserWarning, stacklevel=4)
    df.drop(columns=[col], inplace=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_frames.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/frames.py tests/unit/test_frames.py
git commit -m "feat(analysis): to_dataframe inlines dict columns, drops nested with warning"
```

---

### Task 4: `to_dataframe` — mixed types and known-column warnings

**Files:**
- Modify: `multiomics_explorer/analysis/frames.py`
- Modify: `tests/unit/test_frames.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_frames.py`:

```python
class TestToDataFrameWarnings:
    def test_mixed_list_and_scalar_dropped(self):
        """Column with mix of lists and scalars is dropped with warning."""
        result = {
            "results": [
                {"id": "A", "mixed": ["a", "b"]},
                {"id": "B", "mixed": "just a string"},
            ],
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            df = to_dataframe(result)
        assert "mixed" not in df.columns
        assert len(w) == 1
        assert "mixed" in str(w[0].message)

    def test_response_summary_suggests_dedicated_function(self):
        """Dropping 'response_summary' warns with profile_summary_to_dataframe."""
        result = {
            "results": [
                {
                    "locus_tag": "A",
                    "response_summary": {
                        "nitrogen": {"experiments_up": 3, "experiments_down": 0},
                    },
                },
            ],
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            df = to_dataframe(result)
        assert "response_summary" not in df.columns
        assert "profile_summary_to_dataframe()" in str(w[0].message)

    def test_timepoints_suggests_dedicated_function(self):
        """Dropping 'timepoints' warns with experiments_to_dataframe."""
        result = {
            "results": [
                {
                    "id": "exp1",
                    "timepoints": [
                        {"timepoint": "T0", "gene_count": 100},
                    ],
                },
            ],
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            df = to_dataframe(result)
        assert "timepoints" not in df.columns
        assert "experiments_to_dataframe()" in str(w[0].message)

    def test_unknown_nested_generic_warning(self):
        """Unknown nested columns get a generic warning."""
        result = {
            "results": [
                {"id": "A", "weird": [{"nested": True}]},
            ],
        }
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            df = to_dataframe(result)
        assert "weird" not in df.columns
        assert "file an issue" in str(w[0].message)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_frames.py::TestToDataFrameWarnings -v`
Expected: Mixed result — some may pass from Task 3 implementation, `test_mixed_list_and_scalar_dropped` and the list-of-dicts warning tests likely fail

- [ ] **Step 3: Handle list-of-dicts (distinct from list-of-scalars)**

The current list check (`all(isinstance(v, list) for v in non_null)`) will match both `["a", "b"]` and `[{"nested": True}]`. Update the list branch in `_process_object_column`:

```python
    if all(isinstance(v, list) for v in non_null):
        # Check if list contents are dicts/lists (nested — not joinable)
        has_nested_items = any(
            isinstance(item, (dict, list))
            for v in non_null
            for item in v
            if item is not None
        )
        if has_nested_items:
            _drop_with_warning(df, col)
            return

        df[col] = df[col].apply(
            lambda x: _LIST_DELIMITER.join(str(i) for i in x)
            if isinstance(x, list) else x
        )
        return
```

No changes needed for the mixed-types case — that already falls through to `_drop_with_warning`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_frames.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/frames.py tests/unit/test_frames.py
git commit -m "feat(analysis): to_dataframe handles list-of-dicts and suggests dedicated functions"
```

---

### Task 5: `profile_summary_to_dataframe`

**Files:**
- Modify: `multiomics_explorer/analysis/frames.py`
- Modify: `multiomics_explorer/analysis/__init__.py`
- Modify: `tests/unit/test_frames.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_frames.py`. Reuse the mock data constants from `test_analysis.py`:

```python
from multiomics_explorer.analysis import profile_summary_to_dataframe


# Minimal gene_response_profile result for testing
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


class TestProfileSummaryToDataFrame:
    def test_shape_and_columns(self):
        """One row per gene x group, with expected columns."""
        df = profile_summary_to_dataframe(_PROFILE_RESULT)
        # GENE_A has 2 groups, GENE_B has 1 → 3 rows
        assert len(df) == 3
        assert "locus_tag" in df.columns
        assert "gene_name" in df.columns
        assert "group" in df.columns
        assert "experiments_up" in df.columns

    def test_directional_fields_nan_when_absent(self):
        """Directional rank/log2fc fields are NaN when not in source dict."""
        df = profile_summary_to_dataframe(_PROFILE_RESULT)
        # GENE_A light_stress has no up or down experiments → no rank fields
        light_row = df[(df["locus_tag"] == "GENE_A") & (df["group"] == "light_stress")]
        assert pd.isna(light_row.iloc[0]["up_best_rank"])
        assert pd.isna(light_row.iloc[0]["down_best_rank"])

    def test_directional_fields_present_when_available(self):
        """Directional fields are populated when present in source."""
        df = profile_summary_to_dataframe(_PROFILE_RESULT)
        n_row = df[(df["locus_tag"] == "GENE_A") & (df["group"] == "nitrogen_stress")]
        assert n_row.iloc[0]["up_best_rank"] == 3
        assert n_row.iloc[0]["up_max_log2fc"] == 5.7

    def test_csv_safe(self):
        """All columns are scalar — no lists or dicts in cells."""
        df = profile_summary_to_dataframe(_PROFILE_RESULT)
        for col in df.columns:
            for val in df[col].dropna():
                assert not isinstance(val, (list, dict)), (
                    f"Column '{col}' has non-scalar value: {val}"
                )

    def test_wrong_result_raises(self):
        """Passing a result without response_summary raises ValueError."""
        wrong = {"results": [{"locus_tag": "A", "score": 1.0}]}
        with pytest.raises(ValueError, match="response_summary"):
            profile_summary_to_dataframe(wrong)

    def test_empty_results(self):
        """Empty results list returns empty DataFrame."""
        result = {"results": []}
        df = profile_summary_to_dataframe(result)
        assert len(df) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_frames.py::TestProfileSummaryToDataFrame -v`
Expected: ImportError — `cannot import name 'profile_summary_to_dataframe'`

- [ ] **Step 3: Implement `profile_summary_to_dataframe`**

Add to `multiomics_explorer/analysis/frames.py`:

```python
def profile_summary_to_dataframe(result: dict) -> pd.DataFrame:
    """Extract gene x group detail table from gene_response_profile result.

    Flattens the response_summary dict from each gene into one row per
    gene x group combination.

    Args:
        result: Dict returned by gene_response_profile(). Must contain
                'results' with each entry having a 'response_summary' key.

    Returns:
        DataFrame with columns: locus_tag, gene_name, group, plus all
        stats fields from response_summary entries. Directional fields
        (up_best_rank, etc.) are NaN when absent.

    Raises:
        ValueError: If result has no 'results' key or results lack
                    'response_summary'.
    """
    if "results" not in result:
        raise ValueError(
            "Expected a dict with a 'results' key. "
            "Got keys: " + ", ".join(sorted(result.keys()))
        )

    rows_list = result["results"]
    if not rows_list:
        return pd.DataFrame()

    if "response_summary" not in rows_list[0]:
        raise ValueError(
            "Results do not contain 'response_summary'. "
            "This function is for gene_response_profile results. "
            "Got keys: " + ", ".join(sorted(rows_list[0].keys()))
        )

    records = []
    for gene in rows_list:
        lt = gene["locus_tag"]
        gn = gene.get("gene_name")
        for group_key, stats in gene["response_summary"].items():
            record = {
                "locus_tag": lt,
                "gene_name": gn,
                "group": group_key,
                **stats,
            }
            records.append(record)

    return pd.DataFrame(records)
```

Update `multiomics_explorer/analysis/__init__.py`:

```python
from multiomics_explorer.analysis.frames import (
    profile_summary_to_dataframe,
    to_dataframe,
)

__all__ = [
    "response_matrix",
    "gene_set_compare",
    "to_dataframe",
    "profile_summary_to_dataframe",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_frames.py -v`
Expected: 20 passed

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/frames.py multiomics_explorer/analysis/__init__.py tests/unit/test_frames.py
git commit -m "feat(analysis): add profile_summary_to_dataframe for gene x group detail"
```

---

### Task 6: `experiments_to_dataframe`

**Files:**
- Modify: `multiomics_explorer/analysis/frames.py`
- Modify: `multiomics_explorer/analysis/__init__.py`
- Modify: `tests/unit/test_frames.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_frames.py`:

```python
from multiomics_explorer.analysis import experiments_to_dataframe


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
                "significant_up": 50,
                "significant_down": 30,
                "not_significant": 120,
            },
            "timepoints": [
                {
                    "timepoint": "T0",
                    "timepoint_order": 0,
                    "timepoint_hours": 0.0,
                    "gene_count": 180,
                    "genes_by_status": {
                        "significant_up": 40,
                        "significant_down": 20,
                        "not_significant": 120,
                    },
                },
                {
                    "timepoint": "T1",
                    "timepoint_order": 1,
                    "timepoint_hours": 2.0,
                    "gene_count": 200,
                    "genes_by_status": {
                        "significant_up": 50,
                        "significant_down": 30,
                        "not_significant": 120,
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
                "significant_up": 20,
                "significant_down": 10,
                "not_significant": 120,
            },
        },
    ],
}


class TestExperimentsToDataFrame:
    def test_time_course_expanded(self):
        """Time-course experiment produces one row per timepoint."""
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        exp1_rows = df[df["experiment_id"] == "exp1"]
        assert len(exp1_rows) == 2
        assert list(exp1_rows["timepoint"]) == ["T0", "T1"]

    def test_non_time_course_single_row(self):
        """Non-time-course experiment produces one row with NaN timepoint fields."""
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        exp2_rows = df[df["experiment_id"] == "exp2"]
        assert len(exp2_rows) == 1
        assert pd.isna(exp2_rows.iloc[0]["timepoint"])

    def test_timepoint_genes_by_status_inlined(self):
        """genes_by_status within timepoints is inlined as prefixed columns."""
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        t0_row = df[(df["experiment_id"] == "exp1") & (df["timepoint"] == "T0")]
        assert t0_row.iloc[0]["tp_significant_up"] == 40
        assert t0_row.iloc[0]["tp_significant_down"] == 20
        assert t0_row.iloc[0]["tp_not_significant"] == 120

    def test_experiment_genes_by_status_inlined(self):
        """genes_by_status at experiment level is inlined."""
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        row = df[df["experiment_id"] == "exp2"].iloc[0]
        assert row["genes_by_status_significant_up"] == 20

    def test_no_nested_columns(self):
        """No list or dict values remain in cells."""
        df = experiments_to_dataframe(_EXPERIMENTS_RESULT)
        for col in df.columns:
            for val in df[col].dropna():
                assert not isinstance(val, (list, dict)), (
                    f"Column '{col}' has non-scalar value: {val}"
                )

    def test_empty_results(self):
        """Empty results list returns empty DataFrame."""
        df = experiments_to_dataframe({"results": []})
        assert len(df) == 0

    def test_missing_results_key(self):
        """Missing 'results' key raises ValueError."""
        with pytest.raises(ValueError, match="results"):
            experiments_to_dataframe({"total": 5})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_frames.py::TestExperimentsToDataFrame -v`
Expected: ImportError — `cannot import name 'experiments_to_dataframe'`

- [ ] **Step 3: Implement `experiments_to_dataframe`**

Add to `multiomics_explorer/analysis/frames.py`:

```python
def experiments_to_dataframe(result: dict) -> pd.DataFrame:
    """Extract experiment x timepoint table from list_experiments result.

    Time-course experiments are expanded to one row per timepoint.
    Non-time-course experiments get a single row with timepoint fields
    as NaN. genes_by_status dicts are inlined as prefixed columns at
    both experiment and timepoint level.

    Args:
        result: Dict returned by list_experiments(). Must contain a
                'results' key.

    Returns:
        DataFrame with all scalar experiment fields plus timepoint
        columns (timepoint, timepoint_order, timepoint_hours,
        tp_gene_count, tp_significant_up, tp_significant_down,
        tp_not_significant).

    Raises:
        ValueError: If result has no 'results' key.
    """
    if "results" not in result:
        raise ValueError(
            "Expected a dict with a 'results' key. "
            "Got keys: " + ", ".join(sorted(result.keys()))
        )

    rows_list = result["results"]
    if not rows_list:
        return pd.DataFrame()

    records = []
    for exp in rows_list:
        # Base experiment fields (exclude timepoints and genes_by_status)
        base = {
            k: v for k, v in exp.items()
            if k not in ("timepoints", "genes_by_status")
        }

        # Inline experiment-level genes_by_status
        gbs = exp.get("genes_by_status")
        if isinstance(gbs, dict):
            for status_key, count in gbs.items():
                base[f"genes_by_status_{status_key}"] = count

        timepoints = exp.get("timepoints")
        if timepoints:
            for tp in timepoints:
                record = {**base}
                record["timepoint"] = tp.get("timepoint")
                record["timepoint_order"] = tp.get("timepoint_order")
                record["timepoint_hours"] = tp.get("timepoint_hours")
                record["tp_gene_count"] = tp.get("gene_count")
                tp_gbs = tp.get("genes_by_status", {})
                record["tp_significant_up"] = tp_gbs.get("significant_up")
                record["tp_significant_down"] = tp_gbs.get("significant_down")
                record["tp_not_significant"] = tp_gbs.get("not_significant")
                records.append(record)
        else:
            # Non-time-course: single row with NaN timepoint fields
            record = {**base}
            record["timepoint"] = None
            record["timepoint_order"] = None
            record["timepoint_hours"] = None
            record["tp_gene_count"] = None
            record["tp_significant_up"] = None
            record["tp_significant_down"] = None
            record["tp_not_significant"] = None
            records.append(record)

    return pd.DataFrame(records)
```

Update `multiomics_explorer/analysis/__init__.py`:

```python
from multiomics_explorer.analysis.frames import (
    experiments_to_dataframe,
    profile_summary_to_dataframe,
    to_dataframe,
)

__all__ = [
    "response_matrix",
    "gene_set_compare",
    "to_dataframe",
    "profile_summary_to_dataframe",
    "experiments_to_dataframe",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_frames.py -v`
Expected: 27 passed

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/frames.py multiomics_explorer/analysis/__init__.py tests/unit/test_frames.py
git commit -m "feat(analysis): add experiments_to_dataframe for experiment x timepoint detail"
```

---

### Task 7: Integration tests — round-trip with live KG

**Files:**
- Modify: `tests/integration/test_analysis.py`

- [ ] **Step 1: Write the integration tests**

Add to `tests/integration/test_analysis.py`:

```python
from multiomics_explorer.analysis import (
    to_dataframe,
    profile_summary_to_dataframe,
    experiments_to_dataframe,
)


@pytest.mark.kg
class TestToDataFrameIntegration:
    """Round-trip: API call → to_dataframe → verify CSV-safe."""

    def _assert_csv_safe(self, df):
        """Verify no column contains list or dict values."""
        for col in df.columns:
            for val in df[col].dropna():
                assert not isinstance(val, (list, dict)), (
                    f"Column '{col}' has non-scalar value: {type(val).__name__}"
                )

    def test_resolve_gene(self, conn):
        result = api.resolve_gene("PMM0370", conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_genes_by_function(self, conn):
        result = api.genes_by_function("nitrogen", conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_gene_overview(self, conn):
        result = api.gene_overview(locus_tags=["PMM0370", "PMM0920"], conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_list_organisms(self, conn):
        result = api.list_organisms(conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_list_publications(self, conn):
        result = api.list_publications(conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_list_experiments(self, conn):
        result = api.list_experiments(conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_gene_response_profile(self, conn):
        result = api.gene_response_profile(
            locus_tags=["PMM0370", "PMM0920"], conn=conn,
        )
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)
        assert "response_summary" not in df.columns

    def test_differential_expression_by_gene(self, conn):
        result = api.differential_expression_by_gene(
            organism="MED4", conn=conn,
        )
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)

    def test_search_ontology(self, conn):
        result = api.search_ontology("nitrogen", conn=conn)
        df = to_dataframe(result)
        assert len(df) >= 1
        self._assert_csv_safe(df)


@pytest.mark.kg
class TestProfileSummaryIntegration:
    def test_round_trip(self, conn):
        result = api.gene_response_profile(
            locus_tags=["PMM0370", "PMM0920"], conn=conn,
        )
        df = profile_summary_to_dataframe(result)
        assert len(df) >= 1
        assert "group" in df.columns
        assert "experiments_up" in df.columns
        # CSV-safe
        for col in df.columns:
            for val in df[col].dropna():
                assert not isinstance(val, (list, dict))


@pytest.mark.kg
class TestExperimentsToDataFrameIntegration:
    def test_round_trip(self, conn):
        result = api.list_experiments(conn=conn)
        df = experiments_to_dataframe(result)
        assert len(df) >= 1
        assert "experiment_id" in df.columns
        # CSV-safe
        for col in df.columns:
            for val in df[col].dropna():
                assert not isinstance(val, (list, dict))
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/integration/test_analysis.py -v -m kg`
Expected: All passed

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_analysis.py
git commit -m "test(integration): add round-trip tests for DataFrame conversion utilities"
```

---

### Task 8: Reference doc + MCP resource

**Files:**
- Create: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/to_dataframe.md`
- Modify: `multiomics_explorer/mcp_server/server.py` (only if `docs://analysis/{name}` resource handler doesn't exist yet — it may already be added by Part 1)

- [ ] **Step 1: Check if the MCP resource handler exists**

Run: `grep -n "docs://analysis" multiomics_explorer/mcp_server/server.py`

If the handler already exists (from Part 1), skip to Step 2. If not, add it per the Part 1 spec.

- [ ] **Step 2: Write the reference doc**

Create `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/to_dataframe.md`:

```markdown
# DataFrame Conversion Utilities

Three functions for converting API results to CSV-safe DataFrames.
Imported from `multiomics_explorer.analysis`.

## `to_dataframe(result)` — universal converter

### What it does

Converts any API result dict into a flat, CSV-safe DataFrame.
Automatically handles list columns (joins with ` | `), dict columns
(inlines as prefixed columns), and nested structures (drops with
warning suggesting the dedicated function).

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| result | dict | required | Return value from any API function |

### Response format

Single `pd.DataFrame`. One row per entry in `result["results"]`.
All columns are scalar-valued (safe for `.to_csv()`).

### Few-shot examples

**Simple — flat results:**
```python
from multiomics_explorer import genes_by_function
from multiomics_explorer.analysis import to_dataframe

result = genes_by_function("nitrogen")
df = to_dataframe(result)
df.to_csv("nitrogen_genes.csv", index=False)
```

**With nested fields — warning emitted:**
```python
from multiomics_explorer import gene_response_profile
from multiomics_explorer.analysis import to_dataframe

result = gene_response_profile(locus_tags=["PMM0370", "PMM0920"])
df = to_dataframe(result)
# WARNING: Dropped nested column 'response_summary'.
# Use profile_summary_to_dataframe() to extract it as a separate DataFrame.
```

**list_experiments — genes_by_status auto-inlined:**
```python
from multiomics_explorer import list_experiments
from multiomics_explorer.analysis import to_dataframe

result = list_experiments()
df = to_dataframe(result)
# genes_by_status dict becomes:
#   genes_by_status_significant_up, genes_by_status_significant_down,
#   genes_by_status_not_significant
# timepoints list is dropped with warning
```

### Common mistakes

| Mistake | Fix |
|---------|-----|
| Ignoring the warning about dropped columns | Read the warning — it names the dedicated function |
| Using `pd.DataFrame(result["results"])` directly | Use `to_dataframe(result)` instead — it handles nested fields |
| Expecting `to_dataframe` to return the gene x group detail | Use `profile_summary_to_dataframe()` for that |

---

## `profile_summary_to_dataframe(result)` — gene x group detail

### What it does

Extracts the `response_summary` dict from each gene in a
`gene_response_profile` result. Returns one row per gene x group.

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| result | dict | required | Return value from `gene_response_profile()` |

### Response format

`pd.DataFrame` with columns: `locus_tag`, `gene_name`, `group`,
`experiments_total`, `experiments_tested`, `experiments_up`,
`experiments_down`, `timepoints_total`, `timepoints_tested`,
`timepoints_up`, `timepoints_down`, `up_best_rank`,
`up_median_rank`, `up_max_log2fc`, `down_best_rank`,
`down_median_rank`, `down_max_log2fc`.

Directional fields are NaN when no experiments in that direction.

### Few-shot examples

```python
from multiomics_explorer import gene_response_profile
from multiomics_explorer.analysis import to_dataframe, profile_summary_to_dataframe

result = gene_response_profile(locus_tags=["PMM0370", "PMM0920"])

# Gene-level flat table
genes_df = to_dataframe(result)

# Gene x group detail table
summary_df = profile_summary_to_dataframe(result)
summary_df.to_csv("response_detail.csv", index=False)
```

### Common mistakes

| Mistake | Fix |
|---------|-----|
| Passing a `list_experiments` result | This function is for `gene_response_profile` only |
| Expecting the gene-level flat table | Use `to_dataframe()` for that |

---

## `experiments_to_dataframe(result)` — experiment x timepoint

### What it does

Expands time-course experiments into one row per timepoint.
Non-time-course experiments get a single row with NaN timepoint
fields. `genes_by_status` dicts are inlined at both levels.

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| result | dict | required | Return value from `list_experiments()` |

### Response format

`pd.DataFrame` with all scalar experiment fields plus:
`timepoint`, `timepoint_order`, `timepoint_hours`,
`tp_gene_count`, `tp_significant_up`, `tp_significant_down`,
`tp_not_significant`.

Experiment-level `genes_by_status` is inlined as
`genes_by_status_significant_up`, etc.

### Few-shot examples

```python
from multiomics_explorer import list_experiments
from multiomics_explorer.analysis import experiments_to_dataframe

result = list_experiments(organism="MED4")
tp_df = experiments_to_dataframe(result)
tp_df.to_csv("med4_timepoints.csv", index=False)
```

### Common mistakes

| Mistake | Fix |
|---------|-----|
| Passing a `gene_response_profile` result | This function is for `list_experiments` only |
| Using `to_dataframe()` when you want timepoint detail | `to_dataframe()` drops timepoints — use this function |
```

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/skills/multiomics-kg-guide/references/analysis/to_dataframe.md
git commit -m "docs: add reference doc for DataFrame conversion utilities"
```

---

### Task 9: Run all tests

**Files:** None (verification only)

- [ ] **Step 1: Run unit tests**

Run: `pytest tests/unit/ -v`
Expected: All passed (including existing tests — no regressions)

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/integration/test_analysis.py -v -m kg`
Expected: All passed

- [ ] **Step 3: Fix any failures and commit**

If failures, fix and commit with descriptive message.
