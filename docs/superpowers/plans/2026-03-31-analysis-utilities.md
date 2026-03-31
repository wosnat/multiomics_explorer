# Analysis Utilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `response_matrix` and `gene_set_compare` utility functions that compose the existing `gene_response_profile` API into DataFrame outputs for scripts and notebooks.

**Architecture:** New `multiomics_explorer/analysis/` package with a single `expression.py` module. Functions call `api.gene_response_profile()` as a Python function (never MCP). `gene_set_compare` calls `response_matrix` which calls the API — a clean three-layer dependency chain.

**Tech Stack:** pandas (new dependency), existing `multiomics_explorer.api` functions, pytest with mocked API returns for unit tests, real KG for integration tests.

---

### Task 1: Add pandas dependency

**Files:**
- Modify: `pyproject.toml:13-29`

- [ ] **Step 1: Add pandas to dependencies**

In `pyproject.toml`, add `"pandas>=2.0"` to the `dependencies` list:

```toml
dependencies = [
    # Neo4j
    "neo4j>=5.0",
    # Configuration & utilities
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "python-dotenv>=1.0",
    "pyyaml>=6.0",
    # CLI
    "typer>=0.12.0",
    "rich>=13.0",
    # Testing
    "pytest>=9.0.2",
    # MCP server
    "fastmcp>=3.0",
    "cyver>=2.0.2",
    # Analysis utilities
    "pandas>=2.0",
]
```

- [ ] **Step 2: Sync dependencies**

Run: `uv sync`
Expected: pandas installed, lock file updated.

- [ ] **Step 3: Verify import**

Run: `python -c "import pandas; print(pandas.__version__)"`
Expected: prints a version >= 2.0

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add pandas for analysis utilities"
```

---

### Task 2: Create analysis package with `response_matrix` — direction classification (unit tested)

**Files:**
- Create: `multiomics_explorer/analysis/__init__.py`
- Create: `multiomics_explorer/analysis/expression.py`
- Create: `tests/unit/test_analysis.py`

- [ ] **Step 1: Write the failing test for basic `response_matrix`**

Create `tests/unit/test_analysis.py`:

```python
"""Unit tests for the analysis/ layer — no Neo4j needed.

Tests direction classification, DataFrame shape, metadata columns,
and group_map re-aggregation by mocking api.gene_response_profile.
"""

from unittest.mock import patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Fixtures: mock gene_response_profile returns
# ---------------------------------------------------------------------------

def _make_api_result(results, organism_name="Test organism", not_found=None,
                     no_expression=None):
    """Build a gene_response_profile-shaped dict for mocking."""
    return {
        "organism_name": organism_name,
        "genes_queried": len(results) + len(not_found or []) + len(no_expression or []),
        "genes_with_response": sum(
            1 for r in results if r.get("groups_responded")
        ),
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
# response_matrix
# ---------------------------------------------------------------------------
class TestResponseMatrix:
    @patch("multiomics_explorer.analysis.expression.api.gene_response_profile")
    def test_direction_classification(self, mock_grp):
        """All five cell values: up, down, mixed, not_responded, not_known."""
        mock_grp.return_value = _make_api_result(
            [GENE_UP_ONLY, GENE_DOWN_ONLY, GENE_MIXED],
        )
        from multiomics_explorer.analysis import response_matrix

        df = response_matrix(genes=["GENE_A", "GENE_B", "GENE_C"])

        assert isinstance(df, pd.DataFrame)
        assert list(df.index) == ["GENE_A", "GENE_B", "GENE_C"]
        assert df.index.name == "locus_tag"

        # GENE_A: nitrogen=up, light=not_responded, iron=not_known
        assert df.loc["GENE_A", "nitrogen_stress"] == "up"
        assert df.loc["GENE_A", "light_stress"] == "not_responded"
        assert df.loc["GENE_A", "iron_stress"] == "not_known"

        # GENE_B: nitrogen=down, light=not_known, iron=not_known
        assert df.loc["GENE_B", "nitrogen_stress"] == "down"
        assert df.loc["GENE_B", "light_stress"] == "not_known"
        assert df.loc["GENE_B", "iron_stress"] == "not_known"

        # GENE_C: nitrogen=mixed, light=not_responded, iron=not_known
        assert df.loc["GENE_C", "nitrogen_stress"] == "mixed"
        assert df.loc["GENE_C", "light_stress"] == "not_responded"
        assert df.loc["GENE_C", "iron_stress"] == "not_known"

    @patch("multiomics_explorer.analysis.expression.api.gene_response_profile")
    def test_metadata_columns(self, mock_grp):
        """gene_name, product, gene_category are present."""
        mock_grp.return_value = _make_api_result([GENE_UP_ONLY])
        from multiomics_explorer.analysis import response_matrix

        df = response_matrix(genes=["GENE_A"])

        assert df.loc["GENE_A", "gene_name"] == "geneA"
        assert df.loc["GENE_A", "product"] == "product A"
        assert df.loc["GENE_A", "gene_category"] == "Category 1"

    @patch("multiomics_explorer.analysis.expression.api.gene_response_profile")
    def test_passes_organism_and_experiment_ids(self, mock_grp):
        """organism and experiment_ids are forwarded to the API."""
        mock_grp.return_value = _make_api_result([GENE_UP_ONLY])
        from multiomics_explorer.analysis import response_matrix

        response_matrix(
            genes=["GENE_A"], organism="MED4",
            experiment_ids=["exp_1"],
        )

        mock_grp.assert_called_once()
        call_kwargs = mock_grp.call_args[1]
        assert call_kwargs["organism"] == "MED4"
        assert call_kwargs["experiment_ids"] == ["exp_1"]
        assert call_kwargs["group_by"] == "treatment_type"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_analysis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'multiomics_explorer.analysis'`

- [ ] **Step 3: Create analysis package with minimal `response_matrix`**

Create `multiomics_explorer/analysis/__init__.py`:

```python
"""Analysis utilities that compose API results into DataFrames."""

from multiomics_explorer.analysis.expression import (
    gene_set_compare,
    response_matrix,
)

__all__ = ["response_matrix", "gene_set_compare"]
```

Create `multiomics_explorer/analysis/expression.py`:

```python
"""Expression response analysis utilities.

These functions call gene_response_profile() as a Python function
and pivot/aggregate the results into pandas DataFrames.
"""

from __future__ import annotations

import pandas as pd

from multiomics_explorer.api import functions as api
from multiomics_explorer.kg.connection import GraphConnection


def _classify_direction(entry: dict) -> str:
    """Classify a response_summary entry into a direction string."""
    up = entry.get("experiments_up", 0)
    down = entry.get("experiments_down", 0)
    if up > 0 and down > 0:
        return "mixed"
    if up > 0:
        return "up"
    if down > 0:
        return "down"
    return "not_responded"


def response_matrix(
    genes: list[str],
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    group_map: dict[str, str] | None = None,
    conn: GraphConnection | None = None,
) -> pd.DataFrame:
    """Build a gene x group matrix of expression response direction.

    Returns a DataFrame indexed by locus_tag. Group columns contain one of:
    "up", "down", "mixed", "not_responded", "not_known".
    Metadata columns: gene_name, product, gene_category.
    """
    if group_map is not None:
        result = api.gene_response_profile(
            locus_tags=genes,
            organism=organism,
            experiment_ids=list(group_map.keys()),
            group_by="experiment",
            conn=conn,
        )
    else:
        result = api.gene_response_profile(
            locus_tags=genes,
            organism=organism,
            experiment_ids=experiment_ids,
            group_by="treatment_type",
            conn=conn,
        )

    # Collect all group keys across all genes
    all_groups: set[str] = set()
    for gene in result["results"]:
        all_groups.update(gene["response_summary"].keys())
        all_groups.update(gene.get("groups_not_responded", []))
        all_groups.update(gene.get("groups_not_known", []))

    # Re-map group keys when group_map is provided
    if group_map is not None:
        target_groups = sorted(set(group_map.values()))
    else:
        target_groups = sorted(all_groups)

    rows = []
    for gene in result["results"]:
        row: dict[str, str | None] = {"locus_tag": gene["locus_tag"]}
        rs = gene["response_summary"]
        not_responded = set(gene.get("groups_not_responded", []))
        not_known = set(gene.get("groups_not_known", []))

        if group_map is not None:
            # Re-aggregate experiment-level entries by custom group label
            merged: dict[str, dict] = {}
            for exp_id, entry in rs.items():
                label = group_map.get(exp_id)
                if label is None:
                    continue
                if label not in merged:
                    merged[label] = {
                        "experiments_up": 0, "experiments_down": 0,
                    }
                merged[label]["experiments_up"] += entry.get("experiments_up", 0)
                merged[label]["experiments_down"] += entry.get("experiments_down", 0)

            for group in target_groups:
                if group in merged:
                    row[group] = _classify_direction(merged[group])
                else:
                    row[group] = "not_known"
        else:
            for group in target_groups:
                if group in rs:
                    row[group] = _classify_direction(rs[group])
                elif group in not_responded:
                    row[group] = "not_responded"
                elif group in not_known:
                    row[group] = "not_known"
                else:
                    row[group] = "not_known"

        row["gene_name"] = gene.get("gene_name")
        row["product"] = gene.get("product")
        row["gene_category"] = gene.get("gene_category")
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.set_index("locus_tag")
    else:
        df = pd.DataFrame(
            columns=target_groups + ["gene_name", "product", "gene_category"],
        )
        df.index.name = "locus_tag"
    return df


def gene_set_compare(
    set_a: list[str],
    set_b: list[str],
    organism: str | None = None,
    set_a_name: str = "set_a",
    set_b_name: str = "set_b",
    experiment_ids: list[str] | None = None,
    group_map: dict[str, str] | None = None,
    conn: GraphConnection | None = None,
) -> dict[str, pd.DataFrame | list[str]]:
    """Compare two gene sets by their expression response profiles.

    Returns dict with keys: overlap, only_a, only_b,
    shared_groups, divergent_groups, summary_per_group.
    """
    raise NotImplementedError("gene_set_compare will be implemented in Task 4")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_analysis.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/__init__.py multiomics_explorer/analysis/expression.py tests/unit/test_analysis.py
git commit -m "feat: add response_matrix with direction classification"
```

---

### Task 3: `response_matrix` — `group_map` re-aggregation (unit tested)

**Files:**
- Modify: `tests/unit/test_analysis.py`

- [ ] **Step 1: Write the failing test for `group_map`**

Add to `TestResponseMatrix` in `tests/unit/test_analysis.py`:

```python
    @patch("multiomics_explorer.analysis.expression.api.gene_response_profile")
    def test_group_map_reaggregation(self, mock_grp):
        """group_map merges experiment-level results into custom groups."""
        gene_exp_level = {
            "locus_tag": "GENE_A",
            "gene_name": "geneA",
            "product": "product A",
            "gene_category": "Category 1",
            "groups_responded": ["exp_1", "exp_2"],
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
                    "timepoints_up": 2, "timepoints_down": 0,
                },
            },
        }
        mock_grp.return_value = _make_api_result([gene_exp_level])
        from multiomics_explorer.analysis import response_matrix

        df = response_matrix(
            genes=["GENE_A"],
            group_map={
                "exp_1": "early",  # up
                "exp_2": "early",  # down → merged with exp_1 → mixed
                "exp_3": "late",   # up
            },
        )

        # exp_1 (up) + exp_2 (down) merged into "early" → mixed
        assert df.loc["GENE_A", "early"] == "mixed"
        # exp_3 (up) alone → "late" = up
        assert df.loc["GENE_A", "late"] == "up"

        # Verify API was called with group_by="experiment"
        call_kwargs = mock_grp.call_args[1]
        assert call_kwargs["group_by"] == "experiment"
        assert set(call_kwargs["experiment_ids"]) == {"exp_1", "exp_2", "exp_3"}

    @patch("multiomics_explorer.analysis.expression.api.gene_response_profile")
    def test_empty_result(self, mock_grp):
        """No genes found returns empty DataFrame with correct structure."""
        mock_grp.return_value = _make_api_result(
            [], not_found=["FAKE_GENE"],
        )
        from multiomics_explorer.analysis import response_matrix

        df = response_matrix(genes=["FAKE_GENE"])

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert df.index.name == "locus_tag"
```

- [ ] **Step 2: Run tests to verify the new tests pass**

Run: `pytest tests/unit/test_analysis.py -v`
Expected: all 5 tests PASS (the `group_map` logic is already implemented in Task 2)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_analysis.py
git commit -m "test: add group_map and empty result tests for response_matrix"
```

---

### Task 4: `gene_set_compare` (unit tested)

**Files:**
- Modify: `multiomics_explorer/analysis/expression.py`
- Modify: `tests/unit/test_analysis.py`

- [ ] **Step 1: Write the failing tests for `gene_set_compare`**

Add to `tests/unit/test_analysis.py`:

```python
# ---------------------------------------------------------------------------
# gene_set_compare
# ---------------------------------------------------------------------------
class TestGeneSetCompare:
    @patch("multiomics_explorer.analysis.expression.api.gene_response_profile")
    def test_partitioning(self, mock_grp):
        """Genes are correctly split into overlap, only_a, only_b."""
        mock_grp.return_value = _make_api_result(
            [GENE_UP_ONLY, GENE_DOWN_ONLY, GENE_MIXED],
        )
        from multiomics_explorer.analysis import gene_set_compare

        result = gene_set_compare(
            set_a=["GENE_A", "GENE_C"],
            set_b=["GENE_B", "GENE_C"],
        )

        assert list(result["overlap"].index) == ["GENE_C"]
        assert list(result["only_a"].index) == ["GENE_A"]
        assert list(result["only_b"].index) == ["GENE_B"]

    @patch("multiomics_explorer.analysis.expression.api.gene_response_profile")
    def test_summary_per_group(self, mock_grp):
        """summary_per_group has correct counts and shared flag."""
        mock_grp.return_value = _make_api_result(
            [GENE_UP_ONLY, GENE_DOWN_ONLY, GENE_MIXED],
        )
        from multiomics_explorer.analysis import gene_set_compare

        result = gene_set_compare(
            set_a=["GENE_A", "GENE_C"],
            set_b=["GENE_B", "GENE_C"],
            set_a_name="early",
            set_b_name="late",
        )

        spg = result["summary_per_group"]
        assert isinstance(spg, pd.DataFrame)
        assert "early" in spg.columns
        assert "late" in spg.columns
        assert "overlap" in spg.columns
        assert "shared" in spg.columns

        # nitrogen_stress: A=up, B=down, C=mixed → early=2(A,C), late=2(B,C), overlap=1(C), shared=True
        row = spg.loc["nitrogen_stress"]
        assert row["early"] == 2
        assert row["late"] == 2
        assert row["overlap"] == 1
        assert row["shared"] is True

    @patch("multiomics_explorer.analysis.expression.api.gene_response_profile")
    def test_shared_groups(self, mock_grp):
        """shared_groups lists groups where both sets have responding genes."""
        mock_grp.return_value = _make_api_result(
            [GENE_UP_ONLY, GENE_DOWN_ONLY],
        )
        from multiomics_explorer.analysis import gene_set_compare

        result = gene_set_compare(
            set_a=["GENE_A"],
            set_b=["GENE_B"],
        )

        # nitrogen_stress: A=up (responds), B=down (responds) → shared
        assert "nitrogen_stress" in result["shared_groups"]
        # light_stress: A=not_responded → not responding → not shared
        assert "light_stress" not in result["shared_groups"]

    @patch("multiomics_explorer.analysis.expression.api.gene_response_profile")
    def test_passes_params_through(self, mock_grp):
        """organism and experiment_ids forwarded to the API."""
        mock_grp.return_value = _make_api_result([GENE_UP_ONLY])
        from multiomics_explorer.analysis import gene_set_compare

        gene_set_compare(
            set_a=["GENE_A"], set_b=["GENE_A"],
            organism="MED4", experiment_ids=["exp_1"],
        )

        call_kwargs = mock_grp.call_args[1]
        assert call_kwargs["organism"] == "MED4"
        assert call_kwargs["experiment_ids"] == ["exp_1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_analysis.py::TestGeneSetCompare -v`
Expected: FAIL — `NotImplementedError: gene_set_compare will be implemented in Task 4`

- [ ] **Step 3: Implement `gene_set_compare`**

Replace the `gene_set_compare` stub in `multiomics_explorer/analysis/expression.py`:

```python
_RESPONDING_VALUES = {"up", "down", "mixed"}


def gene_set_compare(
    set_a: list[str],
    set_b: list[str],
    organism: str | None = None,
    set_a_name: str = "set_a",
    set_b_name: str = "set_b",
    experiment_ids: list[str] | None = None,
    group_map: dict[str, str] | None = None,
    conn: GraphConnection | None = None,
) -> dict[str, pd.DataFrame | list[str]]:
    """Compare two gene sets by their expression response profiles.

    Returns dict with keys: overlap, only_a, only_b,
    shared_groups, divergent_groups, summary_per_group.
    """
    set_a_tags = set(set_a)
    set_b_tags = set(set_b)
    union = list(set_a_tags | set_b_tags)

    matrix = response_matrix(
        genes=union,
        organism=organism,
        experiment_ids=experiment_ids,
        group_map=group_map,
        conn=conn,
    )

    # Partition rows
    in_both = set_a_tags & set_b_tags
    overlap = matrix.loc[matrix.index.isin(in_both)]
    only_a = matrix.loc[matrix.index.isin(set_a_tags - set_b_tags)]
    only_b = matrix.loc[matrix.index.isin(set_b_tags - set_a_tags)]

    # Identify group columns (everything except metadata)
    metadata_cols = {"gene_name", "product", "gene_category"}
    group_cols = [c for c in matrix.columns if c not in metadata_cols]

    # Build summary_per_group
    summary_rows = []
    shared_groups = []
    divergent_groups = []

    for group in group_cols:
        a_genes = matrix.loc[matrix.index.isin(set_a_tags)]
        b_genes = matrix.loc[matrix.index.isin(set_b_tags)]

        a_responding = int((a_genes[group].isin(_RESPONDING_VALUES)).sum()) if not a_genes.empty else 0
        b_responding = int((b_genes[group].isin(_RESPONDING_VALUES)).sum()) if not b_genes.empty else 0

        # Overlap: genes in both sets that respond
        overlap_genes = matrix.loc[matrix.index.isin(in_both)]
        o_responding = int((overlap_genes[group].isin(_RESPONDING_VALUES)).sum()) if not overlap_genes.empty else 0

        is_shared = a_responding > 0 and b_responding > 0

        summary_rows.append({
            "group": group,
            set_a_name: a_responding,
            set_b_name: b_responding,
            "overlap": o_responding,
            "shared": is_shared,
        })

        if is_shared:
            shared_groups.append(group)
        elif a_responding > 0 or b_responding > 0:
            divergent_groups.append(group)

    summary_per_group = pd.DataFrame(summary_rows)
    if not summary_per_group.empty:
        summary_per_group = summary_per_group.set_index("group")

    return {
        "overlap": overlap,
        "only_a": only_a,
        "only_b": only_b,
        "shared_groups": shared_groups,
        "divergent_groups": divergent_groups,
        "summary_per_group": summary_per_group,
    }
```

- [ ] **Step 4: Run all unit tests**

Run: `pytest tests/unit/test_analysis.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/expression.py tests/unit/test_analysis.py
git commit -m "feat: add gene_set_compare with set partitioning and group summary"
```

---

### Task 5: Integration tests (real KG)

**Files:**
- Create: `tests/integration/test_analysis.py`

- [ ] **Step 1: Write integration tests**

Create `tests/integration/test_analysis.py`:

```python
"""Integration tests for analysis utilities — requires Neo4j."""

import pytest

from multiomics_explorer.analysis import gene_set_compare, response_matrix

KNOWN_GENE = "PMM0001"
# Two genes known to have expression data in the KG
KNOWN_EXPRESSED_GENES = ["PMM0370", "PMM0920"]


@pytest.mark.kg
class TestResponseMatrixIntegration:
    def test_returns_dataframe_with_correct_shape(self, conn):
        df = response_matrix(genes=KNOWN_EXPRESSED_GENES, conn=conn)

        assert len(df) == len(KNOWN_EXPRESSED_GENES)
        assert df.index.name == "locus_tag"
        # Metadata columns present
        for col in ("gene_name", "product", "gene_category"):
            assert col in df.columns

    def test_group_columns_are_treatment_types(self, conn):
        df = response_matrix(genes=KNOWN_EXPRESSED_GENES, conn=conn)

        metadata_cols = {"gene_name", "product", "gene_category"}
        group_cols = [c for c in df.columns if c not in metadata_cols]
        # Should have at least one treatment type column
        assert len(group_cols) > 0

    def test_cell_values_are_valid(self, conn):
        df = response_matrix(genes=KNOWN_EXPRESSED_GENES, conn=conn)

        valid_values = {"up", "down", "mixed", "not_responded", "not_known"}
        metadata_cols = {"gene_name", "product", "gene_category"}
        group_cols = [c for c in df.columns if c not in metadata_cols]
        for col in group_cols:
            for val in df[col]:
                assert val in valid_values, f"Unexpected value '{val}' in column '{col}'"


@pytest.mark.kg
class TestGeneSetCompareIntegration:
    def test_overlapping_sets(self, conn):
        set_a = [KNOWN_EXPRESSED_GENES[0], KNOWN_GENE]
        set_b = [KNOWN_EXPRESSED_GENES[1], KNOWN_GENE]

        result = gene_set_compare(set_a=set_a, set_b=set_b, conn=conn)

        assert KNOWN_GENE in result["overlap"].index
        assert KNOWN_EXPRESSED_GENES[0] in result["only_a"].index
        assert KNOWN_EXPRESSED_GENES[1] in result["only_b"].index
        assert isinstance(result["shared_groups"], list)
        assert isinstance(result["divergent_groups"], list)
        assert len(result["summary_per_group"]) > 0
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/integration/test_analysis.py -v -m kg`
Expected: all tests PASS (requires running Neo4j)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_analysis.py
git commit -m "test: add integration tests for analysis utilities"
```

---

### Task 6: Run full test suite and verify no regressions

**Files:** none (verification only)

- [ ] **Step 1: Run all unit tests**

Run: `pytest tests/unit/ -v`
Expected: all PASS, no import errors from the new `analysis` package

- [ ] **Step 2: Run all integration tests**

Run: `pytest -m kg -v`
Expected: all PASS including new analysis tests

- [ ] **Step 3: Verify clean import**

Run: `python -c "from multiomics_explorer.analysis import response_matrix, gene_set_compare; print('OK')"`
Expected: prints `OK`
