# `list_derived_metrics` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `list_derived_metrics` MCP tool — the entry-point discovery tool for `DerivedMetric` nodes, mirroring `list_clustering_analyses`. Callers use it before drill-down tools (`gene_derived_metrics`, `genes_by_{numeric,boolean,categorical}_metric`) to inspect `value_kind`, `rankable`, `has_p_value`, `allowed_categories`, and `compartment`.

**Architecture:** Four-layer build. L1 query builder (`kg/queries_lib.py`) has one shared WHERE helper plus detail and summary builders. L2 api function (`api/functions.py`) assembles the response envelope with Lucene retry + `_rename_freq`. L3 MCP wrapper (`mcp_server/tools.py`) with Pydantic `ListDerivedMetricsResult` / `ListDerivedMetricsResponse` models. L4 YAML authoring + generated markdown for about-content. No edge traversals — `DerivedMetric` is fully denormalized so filtering is pure node-lookup.

**Tech Stack:** Python 3.13, Neo4j via the project's `GraphConnection`, APOC (`apoc.coll.frequencies`, `apoc.coll.flatten`), `derivedMetricFullText` index for Lucene search, FastMCP for MCP, Pydantic v2, pytest.

**Spec:** [`docs/tool-specs/list_derived_metrics.md`](../../tool-specs/list_derived_metrics.md) (frozen — refer to it for envelope shape, per-row columns, verified Cypher).
**Design context:** [`docs/superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md`](../specs/2026-04-23-derived-metric-mcp-tools-design.md) (KG invariants, gate diagnostics, canonical CASE-gating pattern).

---

### Task 1: Add `_list_derived_metrics_where` helper tests

**Files:**
- Modify: `tests/unit/test_query_builders.py` (append at end)

- [ ] **Step 1: Add the test class**

```python
class TestListDerivedMetricsWhere:
    """Tests for the shared WHERE-clause helper."""

    def test_no_filters_returns_empty(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where()
        assert conditions == []
        assert params == {}

    def test_organism_space_split_contains(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(organism="MED4")
        assert len(conditions) == 1
        assert "ALL(word IN split(toLower($organism), ' ')" in conditions[0]
        assert "toLower(dm.organism_name) CONTAINS word" in conditions[0]
        assert params == {"organism": "MED4"}

    def test_metric_types_list(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(
            metric_types=["damping_ratio", "peak_time_protein_h"])
        assert conditions == ["dm.metric_type IN $metric_types"]
        assert params == {"metric_types": ["damping_ratio", "peak_time_protein_h"]}

    def test_value_kind(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(value_kind="numeric")
        assert conditions == ["dm.value_kind = $value_kind"]
        assert params == {"value_kind": "numeric"}

    def test_compartment(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(compartment="whole_cell")
        assert conditions == ["dm.compartment = $compartment"]
        assert params == {"compartment": "whole_cell"}

    def test_omics_type_upper(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(omics_type="rnaseq")
        assert conditions == ["toUpper(dm.omics_type) = $omics_type_upper"]
        assert params == {"omics_type_upper": "RNASEQ"}

    def test_treatment_type_any_lowered(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(treatment_type=["Diel", "DARKNESS"])
        assert len(conditions) == 1
        assert "ANY(t IN coalesce(dm.treatment_type, [])" in conditions[0]
        assert "toLower(t) IN $treatment_types_lower" in conditions[0]
        assert params == {"treatment_types_lower": ["diel", "darkness"]}

    def test_background_factors_any_lowered_null_safe(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(background_factors=["Axenic"])
        assert len(conditions) == 1
        assert "ANY(bf IN coalesce(dm.background_factors, [])" in conditions[0]
        assert params == {"background_factors_lower": ["axenic"]}

    def test_growth_phases_any_lowered(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(growth_phases=["Darkness"])
        assert len(conditions) == 1
        assert "ANY(gp IN coalesce(dm.growth_phases, [])" in conditions[0]
        assert params == {"growth_phases_lower": ["darkness"]}

    def test_publication_doi_list(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(
            publication_doi=["10.1128/mSystems.00040-18"])
        assert conditions == ["dm.publication_doi IN $publication_doi"]
        assert params == {"publication_doi": ["10.1128/mSystems.00040-18"]}

    def test_experiment_ids_list(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(experiment_ids=["exp_1"])
        assert conditions == ["dm.experiment_id IN $experiment_ids"]
        assert params == {"experiment_ids": ["exp_1"]}

    def test_derived_metric_ids_list(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(derived_metric_ids=["dm:1", "dm:2"])
        assert conditions == ["dm.id IN $derived_metric_ids"]
        assert params == {"derived_metric_ids": ["dm:1", "dm:2"]}

    def test_rankable_true_coerces_to_string(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(rankable=True)
        assert conditions == ["dm.rankable = $rankable_str"]
        assert params == {"rankable_str": "true"}

    def test_rankable_false_coerces_to_string(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(rankable=False)
        assert conditions == ["dm.rankable = $rankable_str"]
        assert params == {"rankable_str": "false"}

    def test_has_p_value_coerces_to_string(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        _, params_true = _list_derived_metrics_where(has_p_value=True)
        _, params_false = _list_derived_metrics_where(has_p_value=False)
        assert params_true == {"has_p_value_str": "true"}
        assert params_false == {"has_p_value_str": "false"}

    def test_combined_filters(self):
        from multiomics_explorer.kg.queries_lib import _list_derived_metrics_where
        conditions, params = _list_derived_metrics_where(
            organism="NATL2A", value_kind="boolean", rankable=False)
        assert len(conditions) == 3
        assert params.keys() == {"organism", "value_kind", "rankable_str"}
```

- [ ] **Step 2: Run tests — expect `ImportError` / `AttributeError`**

Run: `pytest tests/unit/test_query_builders.py::TestListDerivedMetricsWhere -v`
Expected: every test FAILs with `ImportError: cannot import name '_list_derived_metrics_where'`.

---

### Task 2: Implement `_list_derived_metrics_where` helper

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (append at end, before any existing helper that logically belongs *after* in reading order — use top-level search for the insertion point: place it immediately above any future `build_list_derived_metrics*` slot, e.g. after `build_genes_in_cluster`)

- [ ] **Step 1: Add the helper**

```python
def _list_derived_metrics_where(
    *,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    omics_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    rankable: bool | None = None,
    has_p_value: bool | None = None,
) -> tuple[list[str], dict]:
    """Shared WHERE builder for build_list_derived_metrics{,_summary}.

    Returns (conditions, params). All filters are AND-joined at the caller.
    Organism uses space-split CONTAINS (mirrors _list_experiments_where).
    rankable / has_p_value bool params are coerced to string "true"/"false"
    for comparison against KG-stored strings.
    """
    conditions: list[str] = []
    params: dict = {}

    if organism:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(dm.organism_name) CONTAINS word)"
        )
        params["organism"] = organism

    if metric_types:
        conditions.append("dm.metric_type IN $metric_types")
        params["metric_types"] = metric_types

    if value_kind:
        conditions.append("dm.value_kind = $value_kind")
        params["value_kind"] = value_kind

    if compartment:
        conditions.append("dm.compartment = $compartment")
        params["compartment"] = compartment

    if omics_type:
        conditions.append("toUpper(dm.omics_type) = $omics_type_upper")
        params["omics_type_upper"] = omics_type.upper()

    if treatment_type:
        conditions.append(
            "ANY(t IN coalesce(dm.treatment_type, [])"
            " WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]

    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(dm.background_factors, [])"
            " WHERE toLower(bf) IN $background_factors_lower)"
        )
        params["background_factors_lower"] = [bf.lower() for bf in background_factors]

    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(dm.growth_phases, [])"
            " WHERE toLower(gp) IN $growth_phases_lower)"
        )
        params["growth_phases_lower"] = [gp.lower() for gp in growth_phases]

    if publication_doi:
        conditions.append("dm.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    if experiment_ids:
        conditions.append("dm.experiment_id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids

    if derived_metric_ids:
        conditions.append("dm.id IN $derived_metric_ids")
        params["derived_metric_ids"] = derived_metric_ids

    if rankable is not None:
        conditions.append("dm.rankable = $rankable_str")
        params["rankable_str"] = "true" if rankable else "false"

    if has_p_value is not None:
        conditions.append("dm.has_p_value = $has_p_value_str")
        params["has_p_value_str"] = "true" if has_p_value else "false"

    return conditions, params
```

- [ ] **Step 2: Run tests — expect PASS**

Run: `pytest tests/unit/test_query_builders.py::TestListDerivedMetricsWhere -v`
Expected: all 15 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_query_builders.py multiomics_explorer/kg/queries_lib.py
git commit -m "feat(kg): add _list_derived_metrics_where helper"
```

---

### Task 3: Add `build_list_derived_metrics_summary` tests

**Files:**
- Modify: `tests/unit/test_query_builders.py` (append)

- [ ] **Step 1: Add the test class**

```python
class TestBuildListDerivedMetricsSummary:
    """Tests for build_list_derived_metrics_summary."""

    def test_no_filters_no_search(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics_summary
        cypher, params = build_list_derived_metrics_summary()
        assert "MATCH (dm:DerivedMetric)" in cypher
        assert "CALL db.index.fulltext.queryNodes" not in cypher
        assert "WHERE" not in cypher
        assert "count(dm) AS total_matching" in cypher
        assert "apoc.coll.frequencies(organisms) AS by_organism" in cypher
        assert "apoc.coll.frequencies(value_kinds) AS by_value_kind" in cypher
        assert "apoc.coll.frequencies(metric_types) AS by_metric_type" in cypher
        assert "apoc.coll.frequencies(compartments) AS by_compartment" in cypher
        assert "apoc.coll.frequencies(omics_types) AS by_omics_type" in cypher
        assert (
            "apoc.coll.frequencies(treatment_types_flat) AS by_treatment_type"
            in cypher
        )
        assert (
            "apoc.coll.frequencies(background_factors_flat) AS by_background_factors"
            in cypher
        )
        assert (
            "apoc.coll.frequencies(growth_phases_flat) AS by_growth_phase"
            in cypher
        )
        assert "MATCH (all_dm:DerivedMetric) RETURN count(all_dm) AS total_entries" in cypher
        assert params == {}

    def test_search_text_uses_fulltext_index(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics_summary
        cypher, params = build_list_derived_metrics_summary(search_text="diel")
        assert (
            "CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)"
            in cypher
        )
        assert "YIELD node AS dm, score" in cypher
        assert "max(score) AS score_max" in cypher
        assert "percentileDisc(score, 0.5) AS score_median" in cypher
        assert params == {"search_text": "diel"}

    def test_shares_where_clause(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics_summary
        cypher, params = build_list_derived_metrics_summary(
            organism="MED4", value_kind="numeric", rankable=True)
        assert "WHERE" in cypher
        assert "dm.value_kind = $value_kind" in cypher
        assert "dm.rankable = $rankable_str" in cypher
        assert params == {
            "organism": "MED4",
            "value_kind": "numeric",
            "rankable_str": "true",
        }

    def test_null_safe_flatten(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics_summary
        cypher, _ = build_list_derived_metrics_summary()
        # All three list-typed aggregations must tolerate null via coalesce(..., [])
        assert "apoc.coll.flatten(collect(coalesce(dm.treatment_type, [])))" in cypher
        assert "apoc.coll.flatten(collect(coalesce(dm.background_factors, [])))" in cypher
        assert "apoc.coll.flatten(collect(coalesce(dm.growth_phases, [])))" in cypher
```

- [ ] **Step 2: Run tests — expect `ImportError`**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListDerivedMetricsSummary -v`
Expected: FAIL.

---

### Task 4: Implement `build_list_derived_metrics_summary`

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (after `_list_derived_metrics_where`)

- [ ] **Step 1: Add the builder**

```python
def build_list_derived_metrics_summary(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    omics_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    rankable: bool | None = None,
    has_p_value: bool | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for list_derived_metrics.

    RETURN keys: total_entries, total_matching, by_organism, by_value_kind,
    by_metric_type, by_compartment, by_omics_type, by_treatment_type,
    by_background_factors, by_growth_phase.
    When search_text: adds score_max, score_median.
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, omics_type=omics_type,
        treatment_type=treatment_type, background_factors=background_factors,
        growth_phases=growth_phases, publication_doi=publication_doi,
        experiment_ids=experiment_ids, derived_metric_ids=derived_metric_ids,
        rankable=rankable, has_p_value=has_p_value,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)\n"
            "YIELD node AS dm, score\n"
        )
        score_cols = (
            ",\n     max(score) AS score_max"
            ",\n     percentileDisc(score, 0.5) AS score_median"
        )
        score_return = ", score_max, score_median"
    else:
        match_block = "MATCH (dm:DerivedMetric)\n"
        score_cols = ""
        score_return = ""

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "WITH collect(dm.organism_name) AS organisms,\n"
        "     collect(dm.value_kind) AS value_kinds,\n"
        "     collect(dm.metric_type) AS metric_types,\n"
        "     collect(dm.compartment) AS compartments,\n"
        "     collect(dm.omics_type) AS omics_types,\n"
        "     apoc.coll.flatten(collect(coalesce(dm.treatment_type, []))) AS treatment_types_flat,\n"
        "     apoc.coll.flatten(collect(coalesce(dm.background_factors, []))) AS background_factors_flat,\n"
        "     apoc.coll.flatten(collect(coalesce(dm.growth_phases, []))) AS growth_phases_flat,\n"
        f"     count(dm) AS total_matching{score_cols}\n"
        "CALL { MATCH (all_dm:DerivedMetric) RETURN count(all_dm) AS total_entries }\n"
        "RETURN total_entries, total_matching,\n"
        "       apoc.coll.frequencies(organisms) AS by_organism,\n"
        "       apoc.coll.frequencies(value_kinds) AS by_value_kind,\n"
        "       apoc.coll.frequencies(metric_types) AS by_metric_type,\n"
        "       apoc.coll.frequencies(compartments) AS by_compartment,\n"
        "       apoc.coll.frequencies(omics_types) AS by_omics_type,\n"
        "       apoc.coll.frequencies(treatment_types_flat) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(background_factors_flat) AS by_background_factors,\n"
        f"       apoc.coll.frequencies(growth_phases_flat) AS by_growth_phase{score_return}"
    )
    return cypher, params
```

- [ ] **Step 2: Run tests — expect PASS**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListDerivedMetricsSummary -v`
Expected: all 4 tests PASS.

- [ ] **Step 3: Live-KG smoke check** (manual, not committed)

Run:
```bash
uv run python -c "
from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.queries_lib import build_list_derived_metrics_summary
conn = GraphConnection()
cypher, params = build_list_derived_metrics_summary(
    organism='MED4', value_kind='numeric', rankable=True)
rows = conn.execute_query(cypher, **params)
print(rows[0])
conn.close()
"
```
Expected: `{'total_entries': 13, 'total_matching': 4, 'by_organism': [{'count': 4, 'item': 'Prochlorococcus MED4'}], ...}`.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_query_builders.py multiomics_explorer/kg/queries_lib.py
git commit -m "feat(kg): add build_list_derived_metrics_summary"
```

---

### Task 5: Add `build_list_derived_metrics` (detail) tests

**Files:**
- Modify: `tests/unit/test_query_builders.py` (append)

- [ ] **Step 1: Add the test class**

```python
class TestBuildListDerivedMetrics:
    """Tests for build_list_derived_metrics (detail)."""

    def test_no_filters_compact_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, params = build_list_derived_metrics()
        # Compact RETURN — all 18 columns present with aliases
        assert "dm.id AS derived_metric_id" in cypher
        assert "dm.name AS name" in cypher
        assert "dm.metric_type AS metric_type" in cypher
        assert "dm.value_kind AS value_kind" in cypher
        assert "dm.rankable AS rankable" in cypher
        assert "dm.has_p_value AS has_p_value" in cypher
        assert "dm.unit AS unit" in cypher
        assert "CASE WHEN dm.value_kind = 'categorical'" in cypher
        assert "THEN dm.allowed_categories ELSE null END AS allowed_categories" in cypher
        assert "dm.field_description AS field_description" in cypher
        assert "dm.organism_name AS organism_name" in cypher
        assert "dm.experiment_id AS experiment_id" in cypher
        assert "dm.publication_doi AS publication_doi" in cypher
        assert "dm.compartment AS compartment" in cypher
        assert "dm.omics_type AS omics_type" in cypher
        assert "coalesce(dm.treatment_type, []) AS treatment_type" in cypher
        assert "coalesce(dm.background_factors, []) AS background_factors" in cypher
        assert "dm.total_gene_count AS total_gene_count" in cypher
        assert "coalesce(dm.growth_phases, []) AS growth_phases" in cypher
        # p_value_threshold is intentionally absent (property doesn't exist)
        assert "p_value_threshold" not in cypher
        assert params == {}

    def test_order_by_default(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, _ = build_list_derived_metrics()
        assert (
            "ORDER BY dm.organism_name ASC, dm.value_kind ASC, dm.id ASC"
            in cypher
        )

    def test_search_text_adds_score_and_sort(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, params = build_list_derived_metrics(search_text="diel")
        assert (
            "CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)"
            in cypher
        )
        assert "       score" in cypher
        assert (
            "ORDER BY score DESC, dm.organism_name ASC, dm.value_kind ASC, dm.id ASC"
            in cypher
        )
        assert params == {"search_text": "diel"}

    def test_verbose_adds_three_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, _ = build_list_derived_metrics(verbose=True)
        assert "dm.treatment AS treatment" in cypher
        assert "dm.light_condition AS light_condition" in cypher
        assert "dm.experimental_context AS experimental_context" in cypher
        # p_value_threshold still NOT in Cypher — see spec §Verbose adds
        assert "p_value_threshold" not in cypher

    def test_verbose_false_omits_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, _ = build_list_derived_metrics(verbose=False)
        assert "dm.treatment AS treatment" not in cypher
        assert "dm.light_condition" not in cypher
        assert "dm.experimental_context" not in cypher

    def test_limit_and_offset(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, params = build_list_derived_metrics(limit=5, offset=10)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params == {"limit": 5, "offset": 10}

    def test_limit_none_omits_clause(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, params = build_list_derived_metrics(limit=None, offset=0)
        assert "LIMIT" not in cypher
        assert "SKIP" not in cypher
        assert params == {}

    def test_combined_filters(self):
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, params = build_list_derived_metrics(
            organism="NATL2A", value_kind="boolean", rankable=False, limit=10)
        assert "WHERE" in cypher
        assert "dm.value_kind = $value_kind" in cypher
        assert "dm.rankable = $rankable_str" in cypher
        assert params == {
            "organism": "NATL2A",
            "value_kind": "boolean",
            "rankable_str": "false",
            "limit": 10,
        }

    def test_allowed_categories_case_gated(self):
        """Defensive CASE-gating: allowed_categories null unless value_kind='categorical'."""
        from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
        cypher, _ = build_list_derived_metrics()
        # Must use CASE, not raw dm.allowed_categories
        assert "dm.allowed_categories AS allowed_categories" not in cypher
        assert (
            "CASE WHEN dm.value_kind = 'categorical'"
            "\n            THEN dm.allowed_categories ELSE null END AS allowed_categories"
            in cypher
        )
```

- [ ] **Step 2: Run tests — expect `ImportError`**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListDerivedMetrics -v`
Expected: FAIL.

---

### Task 6: Implement `build_list_derived_metrics` (detail)

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (after `build_list_derived_metrics_summary`)

- [ ] **Step 1: Add the builder**

```python
def build_list_derived_metrics(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    omics_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    rankable: bool | None = None,
    has_p_value: bool | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for list_derived_metrics.

    RETURN keys (compact): derived_metric_id, name, metric_type, value_kind,
    rankable, has_p_value, unit, allowed_categories (CASE-gated on
    value_kind='categorical'), field_description, organism_name,
    experiment_id, publication_doi, compartment, omics_type,
    treatment_type, background_factors, total_gene_count, growth_phases.
    When search_text: adds score.
    When verbose: adds treatment, light_condition, experimental_context.

    NOTE: p_value_threshold is intentionally absent from the RETURN — the
    property does not exist on any DerivedMetric in the current KG. See
    docs/tool-specs/list_derived_metrics.md §Verbose adds for the
    reinstatement rule (CASE-gated on dm.has_p_value='true').
    """
    conditions, params = _list_derived_metrics_where(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, omics_type=omics_type,
        treatment_type=treatment_type, background_factors=background_factors,
        growth_phases=growth_phases, publication_doi=publication_doi,
        experiment_ids=experiment_ids, derived_metric_ids=derived_metric_ids,
        rankable=rankable, has_p_value=has_p_value,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)\n"
            "YIELD node AS dm, score\n"
        )
        score_col = ",\n       score"
        order_prefix = "score DESC, "
    else:
        match_block = "MATCH (dm:DerivedMetric)\n"
        score_col = ""
        order_prefix = ""

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "RETURN dm.id AS derived_metric_id,\n"
        "       dm.name AS name,\n"
        "       dm.metric_type AS metric_type,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.rankable AS rankable,\n"
        "       dm.has_p_value AS has_p_value,\n"
        "       dm.unit AS unit,\n"
        "       CASE WHEN dm.value_kind = 'categorical'\n"
        "            THEN dm.allowed_categories ELSE null END AS allowed_categories,\n"
        "       dm.field_description AS field_description,\n"
        "       dm.organism_name AS organism_name,\n"
        "       dm.experiment_id AS experiment_id,\n"
        "       dm.publication_doi AS publication_doi,\n"
        "       dm.compartment AS compartment,\n"
        "       dm.omics_type AS omics_type,\n"
        "       coalesce(dm.treatment_type, []) AS treatment_type,\n"
        "       coalesce(dm.background_factors, []) AS background_factors,\n"
        "       dm.total_gene_count AS total_gene_count,\n"
        f"       coalesce(dm.growth_phases, []) AS growth_phases{score_col}{verbose_cols}\n"
        f"ORDER BY {order_prefix}dm.organism_name ASC, dm.value_kind ASC, dm.id ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params
```

- [ ] **Step 2: Run tests — expect PASS**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListDerivedMetrics -v`
Expected: all 9 tests PASS.

- [ ] **Step 3: Live-KG smoke check** (manual)

Run:
```bash
uv run python -c "
from multiomics_explorer.kg.connection import GraphConnection
from multiomics_explorer.kg.queries_lib import build_list_derived_metrics
conn = GraphConnection()
cypher, params = build_list_derived_metrics(
    organism='MED4', value_kind='numeric', rankable=True,
    limit=10, offset=0)
for r in conn.execute_query(cypher, **params):
    print(r['derived_metric_id'], r['metric_type'], r['total_gene_count'])
conn.close()
"
```
Expected: 4 rows, all Waldbauer DMs, all `total_gene_count == 312`, `rankable='true'`.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_query_builders.py multiomics_explorer/kg/queries_lib.py
git commit -m "feat(kg): add build_list_derived_metrics (detail builder)"
```

---

### Task 7: Add API function `list_derived_metrics` tests

**Files:**
- Modify: `tests/unit/test_api_functions.py` (append)

- [ ] **Step 1: Add the test class**

```python
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
        assert out["score_median"] is None
```

- [ ] **Step 2: Run tests — expect `ImportError`**

Run: `pytest tests/unit/test_api_functions.py::TestListDerivedMetrics -v`
Expected: FAIL.

---

### Task 8: Implement `api.list_derived_metrics`

**Files:**
- Modify: `multiomics_explorer/api/functions.py` (append before the last function or near `list_clustering_analyses`)

- [ ] **Step 1: Add the function**

```python
def list_derived_metrics(
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: Literal["numeric", "boolean", "categorical"] | None = None,
    compartment: str | None = None,
    omics_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    rankable: bool | None = None,
    has_p_value: bool | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Browse, search, and filter DerivedMetric nodes.

    Returns dict with keys: total_entries, total_matching, by_organism,
    by_value_kind, by_metric_type, by_compartment, by_omics_type,
    by_treatment_type, by_background_factors, by_growth_phase,
    score_max, score_median, returned, offset, truncated, results.
    Per result (compact): derived_metric_id, name, metric_type, value_kind,
    rankable, has_p_value, unit, allowed_categories, field_description,
    organism_name, experiment_id, publication_doi, compartment, omics_type,
    treatment_type, background_factors, total_gene_count, growth_phases,
    score (when searching).
    Per result (verbose): adds treatment, light_condition, experimental_context.

    summary=True: results=[], summary fields only.
    """
    if search_text is not None and not search_text.strip():
        raise ValueError("search_text must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    filter_kwargs = dict(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, omics_type=omics_type,
        treatment_type=treatment_type, background_factors=background_factors,
        growth_phases=growth_phases, publication_doi=publication_doi,
        experiment_ids=experiment_ids, derived_metric_ids=derived_metric_ids,
        rankable=rankable, has_p_value=has_p_value,
    )

    effective_text = search_text

    # Summary query — always runs
    try:
        sum_cypher, sum_params = build_list_derived_metrics_summary(
            search_text=effective_text, **filter_kwargs)
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
    except Neo4jClientError:
        if search_text is not None:
            logger.debug("list_derived_metrics: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            sum_cypher, sum_params = build_list_derived_metrics_summary(
                search_text=effective_text, **filter_kwargs)
            raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
        else:
            raise

    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_entries": raw_summary["total_entries"],
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_value_kind": _rename_freq(raw_summary["by_value_kind"], "value_kind"),
        "by_metric_type": _rename_freq(raw_summary["by_metric_type"], "metric_type"),
        "by_compartment": _rename_freq(raw_summary["by_compartment"], "compartment"),
        "by_omics_type": _rename_freq(raw_summary["by_omics_type"], "omics_type"),
        "by_treatment_type": _rename_freq(
            raw_summary["by_treatment_type"], "treatment_type"),
        "by_background_factors": _rename_freq(
            raw_summary["by_background_factors"], "background_factor"),
        "by_growth_phase": _rename_freq(
            raw_summary.get("by_growth_phase", []), "growth_phase"),
    }

    if search_text is not None:
        envelope["score_max"] = raw_summary.get("score_max")
        envelope["score_median"] = raw_summary.get("score_median")
    else:
        envelope["score_max"] = None
        envelope["score_median"] = None

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    try:
        det_cypher, det_params = build_list_derived_metrics(
            search_text=effective_text, **filter_kwargs,
            verbose=verbose, limit=limit, offset=offset)
        results = conn.execute_query(det_cypher, **det_params)
    except Neo4jClientError:
        if search_text is not None and effective_text == search_text:
            logger.debug("list_derived_metrics detail: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            det_cypher, det_params = build_list_derived_metrics(
                search_text=effective_text, **filter_kwargs,
                verbose=verbose, limit=limit, offset=offset)
            results = conn.execute_query(det_cypher, **det_params)
        else:
            raise

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope
```

- [ ] **Step 2: Add imports at top of file** (if not already present)

Search-and-confirm:
```bash
grep -n "build_list_derived_metrics\|Literal" multiomics_explorer/api/functions.py | head
```

Expected imports already in file: `Literal`, `Neo4jClientError`, `_LUCENE_SPECIAL`, `logger`. Add to the `from multiomics_explorer.kg.queries_lib import ...` block:
```python
    build_list_derived_metrics,
    build_list_derived_metrics_summary,
```

- [ ] **Step 3: Run tests — expect PASS**

Run: `pytest tests/unit/test_api_functions.py::TestListDerivedMetrics -v`
Expected: all 8 tests PASS.

(If `test_importable_from_package` fails, proceed to Task 9 first, then re-run.)

---

### Task 9: Wire package exports

**Files:**
- Modify: `multiomics_explorer/api/__init__.py`
- Modify: `multiomics_explorer/__init__.py`

- [ ] **Step 1: Add to `api/__init__.py`**

Insert the import and the `__all__` entry alongside `list_clustering_analyses`:

```python
from multiomics_explorer.api.functions import (
    ...
    list_clustering_analyses,
    list_derived_metrics,  # <-- new
    ...
)

__all__ = [
    ...
    "list_clustering_analyses",
    "list_derived_metrics",  # <-- new
    ...
]
```

- [ ] **Step 2: Add to top-level `multiomics_explorer/__init__.py`**

Insert alongside `list_clustering_analyses`:
```python
from multiomics_explorer.api import (
    ...
    list_clustering_analyses,
    list_derived_metrics,  # <-- new
    ...
)

__all__ = [
    ...
    "list_clustering_analyses",
    "list_derived_metrics",  # <-- new
    ...
]
```

- [ ] **Step 3: Confirm importable**

```bash
uv run python -c "from multiomics_explorer import list_derived_metrics; print(list_derived_metrics)"
```
Expected: prints `<function list_derived_metrics at 0x...>`.

- [ ] **Step 4: Re-run all L1+L2 unit tests**

Run: `pytest tests/unit/test_query_builders.py::TestListDerivedMetricsWhere tests/unit/test_query_builders.py::TestBuildListDerivedMetricsSummary tests/unit/test_query_builders.py::TestBuildListDerivedMetrics tests/unit/test_api_functions.py::TestListDerivedMetrics -v`
Expected: all PASS (36 tests).

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/api/__init__.py multiomics_explorer/__init__.py tests/unit/test_api_functions.py
git commit -m "feat(api): add list_derived_metrics"
```

---

### Task 10: Add MCP wrapper + Pydantic models tests

**Files:**
- Modify: `tests/unit/test_tool_wrappers.py` (append; also update `EXPECTED_TOOLS`)

- [ ] **Step 1: Add `"list_derived_metrics"` to `EXPECTED_TOOLS`**

Search for the constant and add the string alphabetically or alongside `list_clustering_analyses`:
```python
EXPECTED_TOOLS = {
    ...
    "list_clustering_analyses",
    "list_derived_metrics",  # <-- new
    ...
}
```

- [ ] **Step 2: Add the wrapper test class**

```python
class TestListDerivedMetricsWrapper:
    """Tests for the list_derived_metrics MCP wrapper."""

    _MINIMAL_ENVELOPE = {
        "total_entries": 13,
        "total_matching": 0,
        "by_organism": [],
        "by_value_kind": [],
        "by_metric_type": [],
        "by_compartment": [],
        "by_omics_type": [],
        "by_treatment_type": [],
        "by_background_factors": [],
        "by_growth_phase": [],
        "score_max": None,
        "score_median": None,
        "returned": 0,
        "offset": 0,
        "truncated": False,
        "results": [],
    }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, monkeypatch):
        from multiomics_explorer.mcp_server import tools as tools_mod
        from fastmcp import Client
        from unittest.mock import MagicMock
        monkeypatch.setattr(
            tools_mod.api, "list_derived_metrics",
            MagicMock(return_value=self._MINIMAL_ENVELOPE),
        )
        async with Client(tools_mod.mcp) as client:
            result = await client.call_tool("list_derived_metrics", {})
        envelope = result.structured_content
        assert envelope["total_entries"] == 13
        assert envelope["total_matching"] == 0
        assert envelope["results"] == []
        assert envelope["truncated"] is False

    @pytest.mark.asyncio
    async def test_summary_mode(self, monkeypatch):
        from multiomics_explorer.mcp_server import tools as tools_mod
        from fastmcp import Client
        from unittest.mock import MagicMock
        summary_env = {**self._MINIMAL_ENVELOPE, "total_matching": 13, "truncated": True}
        monkeypatch.setattr(
            tools_mod.api, "list_derived_metrics",
            MagicMock(return_value=summary_env),
        )
        async with Client(tools_mod.mcp) as client:
            result = await client.call_tool("list_derived_metrics", {"summary": True})
        envelope = result.structured_content
        assert envelope["total_matching"] == 13
        assert envelope["truncated"] is True
        assert envelope["results"] == []

    @pytest.mark.asyncio
    async def test_bool_params_forwarded(self, monkeypatch):
        from multiomics_explorer.mcp_server import tools as tools_mod
        from fastmcp import Client
        from unittest.mock import MagicMock
        mock_api = MagicMock(return_value=self._MINIMAL_ENVELOPE)
        monkeypatch.setattr(tools_mod.api, "list_derived_metrics", mock_api)
        async with Client(tools_mod.mcp) as client:
            await client.call_tool(
                "list_derived_metrics",
                {"rankable": True, "has_p_value": False},
            )
        _, kwargs = mock_api.call_args
        assert kwargs["rankable"] is True
        assert kwargs["has_p_value"] is False

    @pytest.mark.asyncio
    async def test_value_kind_literal_enforced(self, monkeypatch):
        from multiomics_explorer.mcp_server import tools as tools_mod
        from fastmcp import Client
        from fastmcp.exceptions import ToolError
        async with Client(tools_mod.mcp) as client:
            with pytest.raises(ToolError):
                await client.call_tool(
                    "list_derived_metrics", {"value_kind": "invalid"},
                )

    @pytest.mark.asyncio
    async def test_value_error_becomes_tool_error(self, monkeypatch):
        from multiomics_explorer.mcp_server import tools as tools_mod
        from fastmcp import Client
        from fastmcp.exceptions import ToolError
        from unittest.mock import MagicMock
        monkeypatch.setattr(
            tools_mod.api, "list_derived_metrics",
            MagicMock(side_effect=ValueError("search_text must not be empty.")),
        )
        async with Client(tools_mod.mcp) as client:
            with pytest.raises(ToolError):
                await client.call_tool("list_derived_metrics", {"search_text": ""})
```

- [ ] **Step 3: Run tests — expect most to FAIL** (tool not registered; EXPECTED_TOOLS check fails too)

Run: `pytest tests/unit/test_tool_wrappers.py::TestListDerivedMetricsWrapper -v`
Expected: FAIL.

Also: `pytest tests/unit/test_tool_wrappers.py -k EXPECTED_TOOLS -v` — should fail until Task 11.

---

### Task 11: Implement MCP wrapper + Pydantic models

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` (inside `register_tools(mcp)`, alongside `list_clustering_analyses` wrapper)

- [ ] **Step 1: Define the Pydantic models and the tool** (exact code — copy-paste-ready)

Insert inside `register_tools(mcp)`, placed just after the `list_clustering_analyses` wrapper block. The exact field descriptions come from the tool spec at [`docs/tool-specs/list_derived_metrics.md#MCP Wrapper`](../../tool-specs/list_derived_metrics.md).

```python
    class ListDerivedMetricsResult(BaseModel):
        derived_metric_id: str = Field(
            description=(
                "Unique id for this DerivedMetric. Pass to `derived_metric_ids` "
                "on drill-down tools (gene_derived_metrics, genes_by_*_metric) "
                "to select this exact DM."
            ),
        )
        name: str = Field(
            description=(
                "Human-readable DM name "
                "(e.g. 'Transcript:protein amplitude ratio')."
            ),
        )
        metric_type: str = Field(
            description=(
                "Category tag identifying what is measured "
                "(e.g. 'diel_amplitude_protein_log2'). The same metric_type may "
                "appear across organisms / publications — pair with organism or "
                "publication_doi when that matters, or use derived_metric_id to "
                "pin one specific DM."
            ),
        )
        value_kind: Literal["numeric", "boolean", "categorical"] = Field(
            description=(
                "Routes to the correct drill-down tool: 'numeric' → "
                "genes_by_numeric_metric, 'boolean' → genes_by_boolean_metric, "
                "'categorical' → genes_by_categorical_metric."
            ),
        )
        rankable: bool = Field(
            description=(
                "True if this DM supports rank / percentile / bucket analysis "
                "on genes_by_numeric_metric. When False, the `bucket`, "
                "`min_percentile`, `max_percentile`, and `max_rank` filters on "
                "that drill-down do not apply — passing them with only "
                "non-rankable DMs raises; mixing rankable + non-rankable drops "
                "the non-rankable ones and lists them in the drill-down's "
                "`excluded_derived_metrics`."
            ),
        )
        has_p_value: bool = Field(
            description=(
                "True if this DM carries statistical p-values, enabling "
                "`significant_only` and `max_adjusted_p_value` on drill-downs. "
                "No DM in the current KG has p-values."
            ),
        )
        unit: str = Field(
            description=(
                "Measurement unit for numeric DMs (e.g. 'hours', 'log2'). "
                "Empty string for boolean and categorical DMs."
            ),
        )
        allowed_categories: list[str] | None = Field(
            description=(
                "Valid category strings for this DM. Non-null only when "
                "value_kind='categorical'; pass a subset as `categories` to "
                "genes_by_categorical_metric."
            ),
        )
        field_description: str = Field(
            description=(
                "Detailed explanation of what this DM measures and how to "
                "interpret its values."
            ),
        )
        organism_name: str = Field(
            description=(
                "Full organism name (e.g. 'Prochlorococcus MED4', "
                "'Alteromonas macleodii MIT1002')."
            ),
        )
        experiment_id: str = Field(
            description=(
                "Parent Experiment node id. Look up context via list_experiments."
            ),
        )
        publication_doi: str = Field(
            description="Parent publication DOI (e.g. '10.1128/mSystems.00040-18').",
        )
        compartment: str = Field(
            description=(
                "Sample compartment or scope (e.g. 'whole_cell', 'vesicle', "
                "'exoproteome', 'spent_medium', 'lysate')."
            ),
        )
        omics_type: str = Field(
            description=(
                "Omics assay type (e.g. 'RNASEQ', 'PROTEOME', "
                "'PAIRED_RNASEQ_PROTEOME')."
            ),
        )
        treatment_type: list[str] = Field(
            description="Treatment type(s) (e.g. ['diel'], ['darkness']).",
        )
        background_factors: list[str] = Field(
            description=(
                "Background experimental factors (e.g. ['axenic'], "
                "['coculture', 'diel']). May be empty."
            ),
        )
        total_gene_count: int = Field(
            description=(
                "Number of distinct genes with at least one measurement for "
                "this DM."
            ),
        )
        growth_phases: list[str] = Field(
            description=(
                "Growth phase(s) this DM pertains to (e.g. ['darkness']). "
                "May be empty."
            ),
        )
        score: float | None = Field(
            default=None,
            description=(
                "Full-text relevance score; present only when search_text was "
                "provided."
            ),
        )
        treatment: str | None = Field(
            default=None,
            description="Treatment description in plain language (verbose mode only).",
        )
        light_condition: str | None = Field(
            default=None,
            description="Light regime (e.g. 'light:dark cycle'; verbose mode only).",
        )
        experimental_context: str | None = Field(
            default=None,
            description=(
                "Longer description of the experimental setup that produced "
                "this DM (verbose mode only)."
            ),
        )
        p_value_threshold: float | None = Field(
            default=None,
            description=(
                "Threshold that defines statistical significance for this DM. "
                "Non-null only when has_p_value=True (verbose mode only; no DM "
                "in current KG has a threshold)."
            ),
        )

    class ListDerivedMetricsResponse(BaseModel):
        total_entries: int = Field(description="Total DMs in the KG (unfiltered baseline).")
        total_matching: int = Field(description="DMs matching all applied filters.")
        by_organism: list[dict] = Field(
            description=(
                "Counts per organism (list of {organism_name, count}, "
                "sorted by count desc)."
            ),
        )
        by_value_kind: list[dict] = Field(
            description="Counts per value_kind (list of {value_kind, count}).",
        )
        by_metric_type: list[dict] = Field(
            description="Counts per metric_type (list of {metric_type, count}).",
        )
        by_compartment: list[dict] = Field(
            description="Counts per compartment (list of {compartment, count}).",
        )
        by_omics_type: list[dict] = Field(
            description="Counts per omics_type (list of {omics_type, count}).",
        )
        by_treatment_type: list[dict] = Field(
            description=(
                "Counts per treatment_type (list of {treatment_type, count}; "
                "DM treatment_type lists are flattened before counting)."
            ),
        )
        by_background_factors: list[dict] = Field(
            description=(
                "Counts per background_factor (list of "
                "{background_factor, count}; flattened)."
            ),
        )
        by_growth_phase: list[dict] = Field(
            description=(
                "Counts per growth_phase (list of {growth_phase, count}; "
                "flattened)."
            ),
        )
        score_max: float | None = Field(
            default=None,
            description=(
                "Max relevance score; present only when search_text was provided."
            ),
        )
        score_median: float | None = Field(
            default=None,
            description=(
                "Median relevance score; present only when search_text was "
                "provided."
            ),
        )
        returned: int = Field(description="Number of rows in results.")
        offset: int = Field(description="Pagination offset used for this call.")
        truncated: bool = Field(
            description=(
                "True when total_matching > returned (more rows available — "
                "paginate with offset)."
            ),
        )
        results: list[ListDerivedMetricsResult] = Field(
            description="Matching DerivedMetric entries. Empty when summary=True.",
        )

    @mcp.tool(
        tags={"derived-metrics", "discovery", "catalog"},
        annotations={"readOnlyHint": True},
    )
    async def list_derived_metrics(
        ctx: Context,
        search_text: Annotated[str | None, Field(
            description=(
                "Full-text search over DM name and field_description. "
                "Examples: 'diel amplitude', 'darkness survival', 'peak time'."
            ),
        )] = None,
        organism: Annotated[str | None, Field(
            description=(
                "Organism to filter by. Accepts short strain code "
                "('MED4', 'NATL2A', 'MIT1002') or full name "
                "('Prochlorococcus MED4'). Case-insensitive substring match."
            ),
        )] = None,
        metric_types: Annotated[list[str] | None, Field(
            description=(
                "Filter by metric_type tags (e.g. 'diel_amplitude_protein_log2', "
                "'periodic_in_coculture_LD'). The same metric_type may appear "
                "across organisms / publications — use derived_metric_ids to "
                "pin one specific DM when that matters."
            ),
        )] = None,
        value_kind: Annotated[Literal["numeric", "boolean", "categorical"] | None, Field(
            description=(
                "Filter by value kind. Determines which drill-down tool "
                "applies: 'numeric' → genes_by_numeric_metric, 'boolean' → "
                "genes_by_boolean_metric, 'categorical' → "
                "genes_by_categorical_metric."
            ),
        )] = None,
        compartment: Annotated[str | None, Field(
            description=(
                "Sample compartment / scope. Current values: 'whole_cell', "
                "'vesicle', 'exoproteome', 'spent_medium', 'lysate'."
            ),
        )] = None,
        omics_type: Annotated[str | None, Field(
            description=(
                "Omics assay type. Examples: 'RNASEQ', 'PROTEOME', "
                "'PAIRED_RNASEQ_PROTEOME'. Case-insensitive."
            ),
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description=(
                "Treatment type(s) to match. Returns DMs whose treatment_type "
                "list overlaps ANY of the given values (e.g. 'diel', "
                "'darkness', 'nitrogen_starvation'). Case-insensitive."
            ),
        )] = None,
        background_factors: Annotated[list[str] | None, Field(
            description=(
                "Background experimental factor(s) to match (e.g. 'axenic', "
                "'coculture', 'diel'). Returns DMs overlapping ANY given "
                "value. Case-insensitive."
            ),
        )] = None,
        growth_phases: Annotated[list[str] | None, Field(
            description=(
                "Growth phase(s) to match (e.g. 'darkness', 'exponential'). "
                "Case-insensitive."
            ),
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description=(
                "Filter by one or more publication DOIs "
                "(e.g. '10.1128/mSystems.00040-18'). Exact match."
            ),
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(
            description="Filter by one or more Experiment node ids.",
        )] = None,
        derived_metric_ids: Annotated[list[str] | None, Field(
            description=(
                "Look up specific DMs by their unique id (matches "
                "`derived_metric_id` on each result). Use to pin one DM when "
                "the same metric_type appears across publications or "
                "organisms."
            ),
        )] = None,
        rankable: Annotated[bool | None, Field(
            description=(
                "Filter to DMs that support rank / percentile / bucket "
                "analysis. Set to True before calling genes_by_numeric_metric "
                "with `bucket`, `min_percentile`, `max_percentile`, or "
                "`max_rank` — those filters require rankable=True on every "
                "selected DM."
            ),
        )] = None,
        has_p_value: Annotated[bool | None, Field(
            description=(
                "Filter to DMs that carry statistical p-values. Set to True "
                "before using `significant_only` or `max_adjusted_p_value` on "
                "drill-downs. No DM in the current KG carries p-values, so "
                "has_p_value=True returns zero rows today — kept available "
                "because the drill-down p-value filters raise when no "
                "selected DM supports them."
            ),
        )] = None,
        summary: Annotated[bool, Field(
            description=(
                "Return summary fields only (counts and breakdowns, no "
                "individual results). Use for quick orientation."
            ),
        )] = False,
        verbose: Annotated[bool, Field(
            description=(
                "Include detailed text fields per result: treatment, "
                "light_condition, experimental_context, p_value_threshold."
            ),
        )] = False,
        limit: Annotated[int, Field(
            description="Max results to return. Paginate with offset.", ge=0,
        )] = 20,
        offset: Annotated[int, Field(
            description="Pagination offset (starting row, 0-indexed).", ge=0,
        )] = 0,
    ) -> ListDerivedMetricsResponse:
        """Discover DerivedMetric (DM) nodes — column-level scalar summaries
        of gene behavior (e.g. rhythmicity flags, diel amplitudes,
        darkness-survival class) that sit alongside DE and gene clusters as
        non-DE evidence.

        Call this first, before `gene_derived_metrics` or the three
        `genes_by_{kind}_metric` drill-downs. Inspect `value_kind` (routes
        you to the right drill-down), `rankable` (gates bucket / percentile
        / rank filters), `has_p_value` (gates significance filters), and
        `allowed_categories` (for categorical DMs) here — drill-down tools
        will raise if you pass filters that the selected DM set doesn't
        support.
        """
        try:
            data = api.list_derived_metrics(
                search_text=search_text, organism=organism,
                metric_types=metric_types, value_kind=value_kind,
                compartment=compartment, omics_type=omics_type,
                treatment_type=treatment_type,
                background_factors=background_factors,
                growth_phases=growth_phases, publication_doi=publication_doi,
                experiment_ids=experiment_ids,
                derived_metric_ids=derived_metric_ids,
                rankable=rankable, has_p_value=has_p_value,
                summary=summary, verbose=verbose,
                limit=limit, offset=offset,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

        return ListDerivedMetricsResponse(**data)
```

- [ ] **Step 2: Run unit tests — expect PASS**

Run: `pytest tests/unit/test_tool_wrappers.py::TestListDerivedMetricsWrapper -v`
Expected: all 5 tests PASS.

Run full `test_tool_wrappers.py` to confirm `EXPECTED_TOOLS` check:
Run: `pytest tests/unit/test_tool_wrappers.py -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "feat(mcp): add list_derived_metrics wrapper + Pydantic models"
```

---

### Task 12: Live-KG integration tests

**Files:**
- Modify: `tests/integration/test_mcp_tools.py` (append)

- [ ] **Step 1: Add the integration test class**

Baselines are pinned to the 2026-04-23 KG state (13 DMs total, 6 MED4 numeric / 5 NATL2A Biller / 2 MIT1002 Biller); refresh with `@pytest.mark.kg` rerun when new DM papers land.

```python
@pytest.mark.kg
class TestListDerivedMetrics:
    """Live-KG integration tests for list_derived_metrics."""

    def test_no_filters_13_dms(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(conn=conn, limit=None)
        assert out["total_entries"] == 13
        assert out["total_matching"] == 13
        assert len(out["results"]) == 13

    def test_value_kind_numeric_6(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(value_kind="numeric", conn=conn, limit=None)
        assert out["total_matching"] == 6
        assert all(r["compartment"] == "whole_cell" for r in out["results"])

    def test_value_kind_boolean_6(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(value_kind="boolean", conn=conn, limit=None)
        assert out["total_matching"] == 6
        # 4 NATL2A + 2 MIT1002
        organisms = {r["organism_name"] for r in out["results"]}
        assert organisms == {
            "Prochlorococcus NATL2A", "Alteromonas macleodii MIT1002",
        }

    def test_value_kind_categorical_1(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(value_kind="categorical", conn=conn, limit=None)
        assert out["total_matching"] == 1
        row = out["results"][0]
        assert row["metric_type"] == "darkness_survival_class"
        assert row["allowed_categories"] is not None
        assert len(row["allowed_categories"]) == 3

    def test_rankable_true_4(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(rankable=True, conn=conn, limit=None)
        assert out["total_matching"] == 4
        assert all(r["rankable"] == "true" for r in out["results"])

    def test_rankable_false_2(self, conn):
        """Sanity-checks bool→'false' string coercion path."""
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(rankable=False, conn=conn, limit=None)
        assert out["total_matching"] == 2
        metric_types = {r["metric_type"] for r in out["results"]}
        assert metric_types == {"peak_time_protein_h", "peak_time_transcript_h"}

    def test_has_p_value_true_empty(self, conn):
        """Intentional: no DM in current KG has p-values."""
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(has_p_value=True, conn=conn, limit=None)
        assert out["total_matching"] == 0
        assert out["results"] == []

    def test_organism_short_code(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(organism="MED4", conn=conn, limit=None)
        assert out["total_matching"] == 6
        assert all(r["organism_name"] == "Prochlorococcus MED4" for r in out["results"])

    def test_organism_full_name(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(
            organism="Prochlorococcus NATL2A", conn=conn, limit=None)
        assert out["total_matching"] == 5

    def test_organism_alteromonas(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(organism="MIT1002", conn=conn, limit=None)
        assert out["total_matching"] == 2

    def test_search_text_diel_amplitude(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(search_text="diel amplitude", conn=conn, limit=5)
        # Top hits must include both diel_amplitude_* DMs
        top_metric_types = [r["metric_type"] for r in out["results"][:2]]
        assert "diel_amplitude_protein_log2" in top_metric_types
        assert "diel_amplitude_transcript_log2" in top_metric_types
        assert out["score_max"] is not None
        assert out["score_median"] is not None

    def test_publication_biller_7(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(
            publication_doi=["10.1128/mSystems.00040-18"], conn=conn, limit=None)
        assert out["total_matching"] == 7

    def test_derived_metric_ids_direct(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        target = (
            "derived_metric:journal.pone.0043432:"
            "table_s2_waldbauer_diel_metrics:damping_ratio"
        )
        out = list_derived_metrics(derived_metric_ids=[target], conn=conn)
        assert out["total_matching"] == 1
        assert out["results"][0]["derived_metric_id"] == target

    def test_summary_results_empty(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(summary=True, conn=conn)
        assert out["results"] == []
        assert out["returned"] == 0
        assert len(out["by_value_kind"]) == 3  # numeric, boolean, categorical
        assert len(out["by_organism"]) == 3

    def test_verbose_adds_fields(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(verbose=True, limit=1, conn=conn)
        row = out["results"][0]
        assert "treatment" in row
        assert "light_condition" in row
        assert "experimental_context" in row
        # p_value_threshold NOT in Cypher — still keyed in Pydantic default, absent here
        assert row.get("p_value_threshold") is None

    def test_envelope_keys_always_present(self, conn):
        """Zero-row filter case: breakdowns are [], not missing."""
        from multiomics_explorer.api import list_derived_metrics
        out = list_derived_metrics(
            derived_metric_ids=["nonexistent:id"], conn=conn, limit=None)
        assert out["total_matching"] == 0
        for key in (
            "by_organism", "by_value_kind", "by_metric_type", "by_compartment",
            "by_omics_type", "by_treatment_type", "by_background_factors",
            "by_growth_phase",
        ):
            assert key in out
            assert out[key] == []
        assert out["results"] == []
        assert out["score_max"] is None

    def test_pagination_offset(self, conn):
        from multiomics_explorer.api import list_derived_metrics
        page1 = list_derived_metrics(conn=conn, limit=5, offset=0)
        page2 = list_derived_metrics(conn=conn, limit=5, offset=5)
        page1_ids = {r["derived_metric_id"] for r in page1["results"]}
        page2_ids = {r["derived_metric_id"] for r in page2["results"]}
        assert page1_ids.isdisjoint(page2_ids)
        assert page1["truncated"] is True
        assert page2["truncated"] is True  # 5 + 5 = 10 < 13
```

- [ ] **Step 2: Run live-KG integration tests**

```bash
pytest tests/integration/test_mcp_tools.py::TestListDerivedMetrics -v -m kg
```
Expected: all 17 tests PASS against the live KG.

If you see `test_value_kind_boolean_6` fail with 4 rows and `organisms == {"Prochlorococcus NATL2A"}` only — the MIT1002 DMs are new (Biller coculture extracts). Re-run `MATCH (dm:DerivedMetric) WHERE dm.value_kind='boolean' RETURN DISTINCT dm.organism_name` to confirm and update the baseline.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_mcp_tools.py
git commit -m "test(kg): integration tests for list_derived_metrics"
```

---

### Task 13: Author about-content YAML

**Files:**
- Create: `multiomics_explorer/inputs/tools/list_derived_metrics.yaml`

- [ ] **Step 1: Generate skeleton**

```bash
uv run python scripts/build_about_content.py --skeleton list_derived_metrics
```
Creates the file with auto-filled structure. Overwrite with the curated content below.

- [ ] **Step 2: Write the YAML**

```yaml
# Human-authored content for list_derived_metrics about page.
# Auto-generated sections (params, response format, expected-keys)
# come from Pydantic models via scripts/build_about_content.py.

examples:
  - title: Orient — what DerivedMetrics exist in the KG?
    call: list_derived_metrics(summary=True)

  - title: Pre-flight for numeric drill-down — which DMs support rank/bucket?
    call: list_derived_metrics(value_kind="numeric", rankable=True)

  - title: Find rhythm / diel evidence via full-text
    call: list_derived_metrics(search_text="diel amplitude", limit=5)

  - title: Per-publication inventory
    call: list_derived_metrics(publication_doi=["10.1128/mSystems.00040-18"])

  - title: Per-organism inventory
    call: list_derived_metrics(organism="NATL2A", verbose=True)

  - title: Pick one DM unambiguously, then drill down
    steps: |
      Step 1: list_derived_metrics(search_text="damping ratio")
              → copy the derived_metric_id of the best match

      Step 2: genes_by_numeric_metric(
                derived_metric_ids=["derived_metric:...:damping_ratio"],
                bucket=["top_decile"])
              → top-decile genes by transcript-to-protein damping

verbose_fields:
  - treatment
  - light_condition
  - experimental_context
  - p_value_threshold

chaining:
  - "list_derived_metrics → gene_derived_metrics(locus_tags, derived_metric_ids)"
  - "list_derived_metrics(value_kind='numeric', rankable=True) → genes_by_numeric_metric(derived_metric_ids, bucket=[...])"
  - "list_derived_metrics(value_kind='boolean') → genes_by_boolean_metric(derived_metric_ids, flag=True)"
  - "list_derived_metrics(value_kind='categorical') → genes_by_categorical_metric(derived_metric_ids, categories=[...])"

mistakes:
  - >-
    Call this FIRST before drill-downs. Inspect rankable / has_p_value /
    value_kind / allowed_categories / compartment here — the downstream drill-down
    tools (genes_by_numeric_metric, genes_by_boolean_metric,
    genes_by_categorical_metric) hard-fail (by design) when the selected DM set
    doesn't support the requested filter. E.g. passing bucket=['top_decile'] with
    a non-rankable DM raises; passing significant_only=True when no selected DM
    has has_p_value=True raises.
  - >-
    metric_type is a category tag, not a primary key — the same metric_type can
    appear across organisms or publications (periodic_in_coculture_LD exists
    once for NATL2A and once for MIT1002). Use derived_metric_ids to pin one
    specific DM; use metric_types to union across every DM with that tag.
  - >-
    has_p_value=True returns zero rows against today's KG — no DM currently
    carries p-values. The filter exists for forward-compat; drill-down p-value
    filters (significant_only, max_adjusted_p_value) will raise with a
    diagnostic error.
  - >-
    allowed_categories is non-null only when value_kind='categorical'. For
    boolean and numeric DMs it is null — not a bug.
  - wrong: list_derived_metrics(rankable="true")
    right: list_derived_metrics(rankable=True)
  - wrong: list_derived_metrics(organism="Prochlorococcus MED4 strain")
    right: list_derived_metrics(organism="MED4")
```

- [ ] **Step 3: Build the markdown**

```bash
uv run python scripts/build_about_content.py list_derived_metrics
```
Generates `multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_derived_metrics.md`.

- [ ] **Step 4: Run about-content tests**

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -v -m kg
```
Expected: all PASS. `test_about_examples` runs each YAML `examples:` call against the live KG.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/inputs/tools/list_derived_metrics.yaml multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_derived_metrics.md
git commit -m "docs: about-content for list_derived_metrics"
```

---

### Task 14: Regression baselines

**Files:**
- Modify: `tests/regression/test_regression.py`
- Modify: `tests/evals/cases.yaml`

- [ ] **Step 1: Register the builder in `TOOL_BUILDERS`**

Open `tests/regression/test_regression.py`, find `TOOL_BUILDERS`, and add:

```python
TOOL_BUILDERS = {
    ...
    "list_derived_metrics": build_list_derived_metrics,
    "list_derived_metrics_summary": build_list_derived_metrics_summary,
    ...
}
```

Make sure the imports include `build_list_derived_metrics` / `_summary`.

- [ ] **Step 2: Add eval cases**

Open `tests/evals/cases.yaml` and add, alongside existing `list_*` cases:

```yaml
- id: list_derived_metrics_all
  tool: list_derived_metrics
  desc: All DMs returned when no filters
  params: {}
  expect:
    min_rows: 13
    columns:
      - derived_metric_id
      - name
      - metric_type
      - value_kind
      - rankable
      - has_p_value
      - unit
      - allowed_categories
      - field_description
      - organism_name
      - experiment_id
      - publication_doi
      - compartment
      - omics_type
      - treatment_type
      - background_factors
      - total_gene_count
      - growth_phases

- id: list_derived_metrics_rankable_true
  tool: list_derived_metrics
  desc: Rankable-only filter yields 4 DMs
  params:
    rankable: true
  expect:
    min_rows: 4
    max_rows: 4

- id: list_derived_metrics_rankable_false
  tool: list_derived_metrics
  desc: Non-rankable filter yields 2 DMs
  params:
    rankable: false
  expect:
    min_rows: 2
    max_rows: 2

- id: list_derived_metrics_has_p_value_empty
  tool: list_derived_metrics
  desc: No DM carries p-values in current KG (intentional signal)
  params:
    has_p_value: true
  expect:
    min_rows: 0
    max_rows: 0

- id: list_derived_metrics_search_diel
  tool: list_derived_metrics
  desc: Full-text diel returns amplitude DMs ranked highest
  params:
    search_text: "diel amplitude"
  expect:
    min_rows: 2
```

- [ ] **Step 3: Regenerate regression baselines**

```bash
pytest tests/regression/ --force-regen -m kg
```
New golden files appear under `tests/regression/test_regression/`.

- [ ] **Step 4: Verify baselines match on re-run**

```bash
pytest tests/regression/ -m kg -v
```
Expected: all PASS (no diffs).

- [ ] **Step 5: Commit**

```bash
git add tests/regression/test_regression.py tests/evals/cases.yaml tests/regression/test_regression/
git commit -m "test(regression): baselines + eval cases for list_derived_metrics"
```

---

### Task 15: CLAUDE.md — add the tool row

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add a row to the MCP Tools table**

Insert alongside `list_clustering_analyses` (alphabetical or grouped):

```markdown
| `list_derived_metrics` | Discover DerivedMetric nodes (non-DE column-level evidence — rhythmicity flags, diel amplitudes, darkness-survival class). Entry point for the DM tool family. Inspect `rankable` / `has_p_value` / `value_kind` / `allowed_categories` here before drill-down tools — those filters require gate-compatible DMs and raise otherwise. Filterable by organism/metric_types/value_kind/compartment/omics_type/treatment_type/background_factors/growth_phases/publication/experiment/rankable/has_p_value. Summary breakdowns + Lucene search. |
```

- [ ] **Step 2: Run full unit + integration suite**

```bash
pytest tests/unit/ -v
pytest tests/integration/test_mcp_tools.py::TestListDerivedMetrics -v -m kg
pytest tests/unit/test_about_content.py -v
```
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document list_derived_metrics in CLAUDE.md"
```

---

### Task 16: Code review

**Files:** (no code changes — review only)

- [ ] **Step 1: Invoke the code-review skill**

Follow `.claude/skills/code-review/SKILL.md`. Focus areas:
- Layer boundaries — no api logic in tool wrapper, no Pydantic in api function.
- Every filter param reflected in 3 layers (builder, api, MCP wrapper).
- Lucene retry pattern matches `list_clustering_analyses`.
- `_rename_freq` applied to every breakdown (8 renames).
- `bool → "true"/"false"` coercion only happens inside the builder WHERE helper.
- Test coverage: each filter has a dedicated unit test in `TestListDerivedMetricsWhere`; each has a live-KG integration baseline.
- CASE-gated `allowed_categories` is present and tested.
- `p_value_threshold` absence from Cypher is documented inline (as a comment) and echoed in `§Verbose adds`.
- `EXPECTED_TOOLS` updated.

- [ ] **Step 2: Address any findings, commit fixes as follow-up commits**

- [ ] **Step 3: Final smoke test end-to-end**

```bash
# MCP server boots
uv run multiomics-kg-mcp &
PID=$!
sleep 2
kill $PID
# No errors; tool registered
```

---

## Self-review checklist

### Spec coverage

| Spec section | Task(s) |
|---|---|
| `_list_derived_metrics_where` helper | 1, 2 |
| `build_list_derived_metrics_summary` | 3, 4 |
| `build_list_derived_metrics` (detail, CASE-gated `allowed_categories`) | 5, 6 |
| `p_value_threshold` absence from Cypher (forward-compat reinstatement rule) | 6 (inline comment), 13 (YAML verbose_fields keeps it) |
| `api.list_derived_metrics` (2-query, Lucene retry, `_rename_freq`) | 7, 8 |
| Package exports | 9 |
| Pydantic `ListDerivedMetricsResult` / `ListDerivedMetricsResponse` | 10, 11 |
| MCP wrapper (`@mcp.tool`, `ToolError`, `Annotated[..., Field(...)]`) | 10, 11 |
| `EXPECTED_TOOLS` update | 10 |
| Integration tests — 17 scenarios (8 filters, 3 value_kinds, rankable True/False, organism forms, search, pub, direct id, summary, verbose, pagination, envelope presence) | 12 |
| YAML authoring — first-bullet `mistakes` rule, 6 chaining entries, 6 mistakes, 6 examples | 13 |
| Regression + eval | 14 |
| CLAUDE.md | 15 |
| Code review | 16 |

All spec requirements covered.

### Placeholder scan

No TBDs, TODOs, or vague handwaves. Each step contains executable code or commands.

### Type consistency

- `ListDerivedMetricsResult` fields match the detail Cypher RETURN aliases 1:1.
- `ListDerivedMetricsResponse` fields match the `api.list_derived_metrics` return dict keys 1:1.
- `EXPECTED_TOOLS` gets the string `"list_derived_metrics"` (no typos).
- Builder function name is stable across tasks: `build_list_derived_metrics`, `build_list_derived_metrics_summary`, `_list_derived_metrics_where`.
- API function name is stable: `list_derived_metrics`.
- `rankable_str` / `has_p_value_str` / `omics_type_upper` / `treatment_types_lower` / `background_factors_lower` / `growth_phases_lower` — param naming is consistent between tests and implementation.
