# KG Constants Drift Tests — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when hardcoded constants drift from actual KG values after rebuilds. Fix one known drift (taxonomic level) and two stale description sets (cluster_type, omics_type).

**Architecture:** New constants in `kg/constants.py`, updated tool descriptions in `tools.py`, one integration test module querying live KG to assert constants match reality.

**Tech Stack:** pytest, neo4j driver, `@pytest.mark.kg`

**Spec:** `docs/superpowers/specs/2026-04-06-kg-constants-drift-tests-design.md`

---

### Task 1: Add new constants and fix taxonomic level drift

**Files:**
- Modify: `multiomics_explorer/kg/constants.py`

- [ ] **Step 1: Update constants.py**

```python
"""Shared constants for the knowledge graph layer."""

VALID_OG_SOURCES: set[str] = {"cyanorak", "eggnog"}

VALID_TAXONOMIC_LEVELS: set[str] = {
    "curated", "Prochloraceae", "Synechococcus",
    "Alteromonadaceae", "Cyanobacteria",
    "Proteobacteria", "Bacteria",
}

MAX_SPECIFICITY_RANK: int = 3  # 0=curated, 1=family, 2=order, 3=domain

VALID_CLUSTER_TYPES: set[str] = {
    "diel_cycling",
    "diel_expression_pattern",
    "expression_classification",
    "expression_level",
    "expression_pattern",
    "periodicity_classification",
    "response_pattern",
}

VALID_OMICS_TYPES: set[str] = {
    "EXOPROTEOMICS",
    "MICROARRAY",
    "PROTEOMICS",
    "RNASEQ",
}
```

Changes:
- `Gammaproteobacteria` → `Proteobacteria` in `VALID_TAXONOMIC_LEVELS`
- Add `VALID_CLUSTER_TYPES` (7 values from KG)
- Add `VALID_OMICS_TYPES` (4 values from KG)

- [ ] **Step 2: Commit**

```bash
git add multiomics_explorer/kg/constants.py
git commit -m "fix: update taxonomic levels, add cluster_type and omics_type constants"
```

---

### Task 2: Update tool description strings to reference constants

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`

The descriptions that enumerate specific values need updating. These are the filter parameter descriptions — not output model fields (output fields use `e.g.` examples which are fine).

- [ ] **Step 1: Add import to tools.py**

At the top of `tools.py` (after line 12), add:

```python
from multiomics_explorer.kg.constants import VALID_CLUSTER_TYPES, VALID_OMICS_TYPES
```

- [ ] **Step 2: Update cluster_type filter descriptions**

There are 3 filter parameters that enumerate cluster_type values. Update each one:

**Line 2652-2653** (`list_clustering_analyses`):
```python
        cluster_type: Annotated[str | None, Field(
            description="Filter: " + ", ".join(f"'{v}'" for v in sorted(VALID_CLUSTER_TYPES)) + ".",
        )] = None,
```

**Line 2837-2839** (`gene_clusters_by_gene`):
```python
        cluster_type: Annotated[str | None, Field(
            description="Filter: " + ", ".join(f"'{v}'" for v in sorted(VALID_CLUSTER_TYPES)) + ".",
        )] = None,
```

- [ ] **Step 3: Update omics_type filter descriptions**

**Line 2662-2663** (`list_clustering_analyses`):
```python
        omics_type: Annotated[str | None, Field(
            description="Filter: " + ", ".join(f"'{v}'" for v in sorted(VALID_OMICS_TYPES)) + ".",
        )] = None,
```

- [ ] **Step 4: Verify no import errors**

Run: `python -c "from multiomics_explorer.mcp_server.tools import *"`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "fix: update cluster_type and omics_type descriptions from constants"
```

---

### Task 3: Write drift tests — ortholog group constants

**Files:**
- Create: `tests/integration/test_kg_constants_drift.py`

- [ ] **Step 1: Create test file with module docstring and first 3 tests**

```python
"""Drift tests: hardcoded constants vs live KG.

These tests detect when a KG rebuild introduces values that our
constants don't account for.  When a test fails:

  1. Update the constant in kg/constants.py (or queries_lib.py)
  2. Check if tool descriptions or validators in tools.py reference
     the old values and need updating
  3. Re-run the full test suite to catch downstream breakage

These are NOT fixture tests — do not "fix" by changing the assertions.
"""

import pytest

from multiomics_explorer.kg.constants import (
    MAX_SPECIFICITY_RANK,
    VALID_CLUSTER_TYPES,
    VALID_OMICS_TYPES,
    VALID_OG_SOURCES,
    VALID_TAXONOMIC_LEVELS,
)


pytestmark = pytest.mark.kg


def _drift_msg(name: str, location: str, expected: set, actual: set) -> str:
    """Format a helpful assertion message for drift failures."""
    missing = actual - expected
    extra = expected - actual
    lines = [f"{name} in {location} is out of sync with KG."]
    if missing:
        lines.append(f"  Missing from constant: {missing}")
    if extra:
        lines.append(f"  Extra in constant (not in KG): {extra}")
    lines.append(
        "  Update the constant, then check if tools.py descriptions"
        " or validators also need updating."
    )
    return "\n".join(lines)


class TestOrthologGroupConstants:
    """VALID_OG_SOURCES, VALID_TAXONOMIC_LEVELS, MAX_SPECIFICITY_RANK."""

    def test_valid_og_sources_match_kg(self, run_query):
        results = run_query(
            "MATCH (og:OrthologGroup) RETURN DISTINCT og.source AS val"
        )
        actual = {r["val"] for r in results}
        assert actual == VALID_OG_SOURCES, _drift_msg(
            "VALID_OG_SOURCES", "kg/constants.py", VALID_OG_SOURCES, actual
        )

    def test_valid_taxonomic_levels_match_kg(self, run_query):
        results = run_query(
            "MATCH (og:OrthologGroup) "
            "RETURN DISTINCT og.taxonomic_level AS val"
        )
        actual = {r["val"] for r in results}
        assert actual == VALID_TAXONOMIC_LEVELS, _drift_msg(
            "VALID_TAXONOMIC_LEVELS",
            "kg/constants.py",
            VALID_TAXONOMIC_LEVELS,
            actual,
        )

    def test_max_specificity_rank_match_kg(self, run_query):
        results = run_query(
            "MATCH (og:OrthologGroup) "
            "RETURN max(og.specificity_rank) AS val"
        )
        actual = results[0]["val"]
        assert actual == MAX_SPECIFICITY_RANK, (
            f"MAX_SPECIFICITY_RANK in kg/constants.py is {MAX_SPECIFICITY_RANK}"
            f" but KG max is {actual}."
            " Update the constant."
        )
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/integration/test_kg_constants_drift.py::TestOrthologGroupConstants -v`
Expected: 3 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_kg_constants_drift.py
git commit -m "test: add drift tests for ortholog group constants"
```

---

### Task 4: Write drift tests — cluster_type, omics_type, expression_status

**Files:**
- Modify: `tests/integration/test_kg_constants_drift.py`

- [ ] **Step 1: Add cluster_type and omics_type tests**

Append to the test file:

```python
class TestExperimentConstants:
    """VALID_CLUSTER_TYPES, VALID_OMICS_TYPES."""

    def test_valid_cluster_types_match_kg(self, run_query):
        results = run_query(
            "MATCH (ca:ClusteringAnalysis) "
            "RETURN DISTINCT ca.cluster_type AS val"
        )
        actual = {r["val"] for r in results}
        assert actual == VALID_CLUSTER_TYPES, _drift_msg(
            "VALID_CLUSTER_TYPES",
            "kg/constants.py",
            VALID_CLUSTER_TYPES,
            actual,
        )

    def test_valid_omics_types_match_kg(self, run_query):
        results = run_query(
            "MATCH (e:Experiment) RETURN DISTINCT e.omics_type AS val"
        )
        actual = {r["val"] for r in results}
        assert actual == VALID_OMICS_TYPES, _drift_msg(
            "VALID_OMICS_TYPES",
            "kg/constants.py",
            VALID_OMICS_TYPES,
            actual,
        )
```

- [ ] **Step 2: Add expression_status test**

Append to the test file:

```python
class TestExpressionConstants:
    """expression_status Literal on ExpressionRow (nested in tools.py)."""

    # The Literal values are hardcoded here because ExpressionRow is a
    # nested class inside a tool function and not importable.  If the
    # Literal in tools.py:1503 changes, update this set too.
    EXPECTED_STATUSES = {"significant_up", "significant_down", "not_significant"}

    def test_expression_status_match_kg(self, run_query):
        results = run_query(
            "MATCH ()-[r:Changes_expression_of]->() "
            "RETURN DISTINCT r.expression_status AS val"
        )
        actual = {r["val"] for r in results}
        assert actual == self.EXPECTED_STATUSES, _drift_msg(
            "ExpressionRow.expression_status Literal",
            "mcp_server/tools.py:1503",
            self.EXPECTED_STATUSES,
            actual,
        )
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/integration/test_kg_constants_drift.py -v`
Expected: 6 PASSED

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_kg_constants_drift.py
git commit -m "test: add drift tests for cluster_type, omics_type, expression_status"
```

---

### Task 5: Write drift tests — ONTOLOGY_CONFIG

**Files:**
- Modify: `tests/integration/test_kg_constants_drift.py`

- [ ] **Step 1: Add ONTOLOGY_CONFIG tests**

Append to the test file:

```python
from multiomics_explorer.kg.queries_lib import ONTOLOGY_CONFIG


class TestOntologyConfig:
    """Verify every ONTOLOGY_CONFIG entry maps to real KG schema elements."""

    @pytest.mark.parametrize("key", sorted(ONTOLOGY_CONFIG.keys()))
    def test_node_label_exists(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        label = cfg["label"]
        results = run_query(f"MATCH (n:`{label}`) RETURN count(n) AS cnt")
        cnt = results[0]["cnt"]
        assert cnt > 0, (
            f"ONTOLOGY_CONFIG['{key}']['label'] = '{label}' — "
            f"no nodes with this label found in KG. "
            f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
        )

    @pytest.mark.parametrize("key", sorted(ONTOLOGY_CONFIG.keys()))
    def test_gene_relationship_exists(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        rel = cfg["gene_rel"]
        results = run_query(
            f"MATCH ()-[r:`{rel}`]->() RETURN count(r) AS cnt LIMIT 1"
        )
        cnt = results[0]["cnt"]
        assert cnt > 0, (
            f"ONTOLOGY_CONFIG['{key}']['gene_rel'] = '{rel}' — "
            f"no relationships of this type found in KG. "
            f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
        )

    @pytest.mark.parametrize(
        "key",
        [k for k in sorted(ONTOLOGY_CONFIG.keys()) if ONTOLOGY_CONFIG[k]["hierarchy_rels"]],
    )
    def test_hierarchy_relationships_exist(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        for rel in cfg["hierarchy_rels"]:
            results = run_query(
                f"MATCH ()-[r:`{rel}`]->() RETURN count(r) AS cnt LIMIT 1"
            )
            cnt = results[0]["cnt"]
            assert cnt > 0, (
                f"ONTOLOGY_CONFIG['{key}']['hierarchy_rels'] contains '{rel}' — "
                f"no relationships of this type found in KG. "
                f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
            )

    @pytest.mark.parametrize("key", sorted(ONTOLOGY_CONFIG.keys()))
    def test_fulltext_index_queryable(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        idx = cfg["fulltext_index"]
        # A minimal query — just needs to not error
        results = run_query(
            f"CALL db.index.fulltext.queryNodes('{idx}', 'test') "
            f"YIELD node RETURN count(node) AS cnt"
        )
        # No assertion on count — zero results is fine, the index just needs to exist
        assert results is not None, (
            f"ONTOLOGY_CONFIG['{key}']['fulltext_index'] = '{idx}' — "
            f"fulltext index query failed. "
            f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
        )

    @pytest.mark.parametrize(
        "key",
        [k for k in sorted(ONTOLOGY_CONFIG.keys()) if "parent_label" in ONTOLOGY_CONFIG[k]],
    )
    def test_parent_label_exists(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        label = cfg["parent_label"]
        results = run_query(f"MATCH (n:`{label}`) RETURN count(n) AS cnt")
        cnt = results[0]["cnt"]
        assert cnt > 0, (
            f"ONTOLOGY_CONFIG['{key}']['parent_label'] = '{label}' — "
            f"no nodes with this label found in KG. "
            f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
        )

    @pytest.mark.parametrize(
        "key",
        [k for k in sorted(ONTOLOGY_CONFIG.keys()) if "parent_fulltext_index" in ONTOLOGY_CONFIG[k]],
    )
    def test_parent_fulltext_index_queryable(self, run_query, key):
        cfg = ONTOLOGY_CONFIG[key]
        idx = cfg["parent_fulltext_index"]
        results = run_query(
            f"CALL db.index.fulltext.queryNodes('{idx}', 'test') "
            f"YIELD node RETURN count(node) AS cnt"
        )
        assert results is not None, (
            f"ONTOLOGY_CONFIG['{key}']['parent_fulltext_index'] = '{idx}' — "
            f"fulltext index query failed. "
            f"Update ONTOLOGY_CONFIG in kg/queries_lib.py."
        )
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/integration/test_kg_constants_drift.py::TestOntologyConfig -v`
Expected: all parametrized tests PASS (9 label tests, 9 gene_rel tests, 6 hierarchy tests, 9 fulltext tests, 1 parent_label test, 1 parent_fulltext test = ~35 tests)

- [ ] **Step 3: Run full drift test file**

Run: `pytest tests/integration/test_kg_constants_drift.py -v`
Expected: all tests PASS (~41 total)

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_kg_constants_drift.py
git commit -m "test: add drift tests for ONTOLOGY_CONFIG schema elements"
```

---

### Task 6: Verify no regressions

**Files:** none (test-only)

- [ ] **Step 1: Run full KG test suite**

Run: `pytest -m kg -v`
Expected: all PASS. If any existing tests fail due to the `Gammaproteobacteria` → `Proteobacteria` fix, update those tests.

- [ ] **Step 2: Run unit tests**

Run: `pytest tests/unit/ -v`
Expected: all PASS

- [ ] **Step 3: Final commit if any test fixes were needed**

```bash
git add -u
git commit -m "fix: update tests for taxonomic level rename"
```
