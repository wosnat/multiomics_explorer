# `list_metabolite_assays` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `list_metabolite_assays` MCP tool — discovery surface for `MetaboliteAssay` nodes, mirroring `list_derived_metrics` 1:1. Pre-flight inspection point for the 3 drill-down tools (`metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite`) shipping in the next slice.

**Architecture:** Four-layer build identical in shape to `list_derived_metrics`. L1 query builder (`kg/queries_lib.py`) — one shared `_list_metabolite_assays_where` helper plus detail and summary builders; per-row `detection_status_counts` rollup over `Assay_quantifies_metabolite` edges; envelope `by_detection_status` rollup. L2 api function (`api/functions.py`) — 2-query pattern, Lucene retry on `metaboliteAssayFullText`, structured `not_found` for the 4 batch inputs. L3 MCP wrapper (`mcp_server/tools.py`) — Pydantic `ListMetaboliteAssaysResult` / `ListMetaboliteAssaysResponse` + typed sub-models per breakdown. L4 YAML + generated about content. Default `limit=20` covers all 10 assays today.

**Tech Stack:** Python 3.13, Neo4j via `GraphConnection`, APOC (`apoc.coll.frequencies`, `apoc.coll.flatten`), `metaboliteAssayFullText` index (4-field corpus — wider than DM's 2), FastMCP, Pydantic v2, pytest.

**Spec:** [`docs/tool-specs/list_metabolite_assays.md`](../../tool-specs/list_metabolite_assays.md) (frozen — Mode A single-tool deep build).
**Parent (cross-cutting policy):** [`docs/tool-specs/2026-05-05-phase5-greenfield-assay-tools.md`](../../tool-specs/2026-05-05-phase5-greenfield-assay-tools.md) — KG verification §3, tested-absent invariant §10, conventions §11, verified Cypher §12.1, Phase 2 deliverables §13.
**Mirror reference (validated plan):** [`docs/superpowers/plans/2026-04-24-list-derived-metrics.md`](2026-04-24-list-derived-metrics.md).

**Anti-scope-creep guardrail (mandatory in every implementer's brief):**
> "ADD only — do NOT modify, rename, or rebaseline any existing test, case, or yml. If an unrelated test fails in your environment, REPORT AS A CONCERN; do not silently retune. Pinned baselines are KG-state guards."

---

### Task 1: Add `_list_metabolite_assays_where` helper tests

**Files:**
- Modify: `tests/unit/test_query_builders.py` (append at end)

- [ ] **Step 1: Add the test class**

```python
class TestListMetaboliteAssaysWhere:
    """Tests for the shared WHERE-clause helper (mirrors _list_derived_metrics_where)."""

    def test_no_filters_returns_empty(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where()
        assert conditions == []
        assert params == {}

    def test_organism_space_split_contains(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(organism="MIT9301")
        assert len(conditions) == 1
        assert "ALL(word IN split(toLower($organism), ' ')" in conditions[0]
        assert "toLower(a.organism_name) CONTAINS word" in conditions[0]
        assert params == {"organism": "MIT9301"}

    def test_metric_types_list(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            metric_types=["cellular_concentration", "extracellular_concentration"])
        assert conditions == ["a.metric_type IN $metric_types"]
        assert params == {"metric_types": ["cellular_concentration", "extracellular_concentration"]}

    def test_value_kind_numeric(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(value_kind="numeric")
        assert conditions == ["a.value_kind = $value_kind"]
        assert params == {"value_kind": "numeric"}

    def test_value_kind_boolean(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(value_kind="boolean")
        assert conditions == ["a.value_kind = $value_kind"]
        assert params == {"value_kind": "boolean"}

    def test_compartment(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(compartment="whole_cell")
        assert conditions == ["a.compartment = $compartment"]
        assert params == {"compartment": "whole_cell"}

    def test_treatment_type_any_lowered(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(treatment_type=["Carbon", "PHOSPHORUS"])
        assert len(conditions) == 1
        assert "ANY(t IN coalesce(a.treatment_type, [])" in conditions[0]
        assert "toLower(t) IN $treatment_types_lower" in conditions[0]
        assert params == {"treatment_types_lower": ["carbon", "phosphorus"]}

    def test_background_factors_any_lowered_null_safe(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(background_factors=["Axenic"])
        assert len(conditions) == 1
        assert "ANY(bf IN coalesce(a.background_factors, [])" in conditions[0]
        assert params == {"background_factors_lower": ["axenic"]}

    def test_growth_phases_any_lowered(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(growth_phases=["Exponential"])
        assert len(conditions) == 1
        assert "ANY(gp IN coalesce(a.growth_phases, [])" in conditions[0]
        assert params == {"growth_phases_lower": ["exponential"]}

    def test_publication_doi_list(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            publication_doi=["10.1073/pnas.2213271120", "10.1128/msystems.01261-22"])
        assert conditions == ["a.publication_doi IN $publication_doi"]
        assert params == {
            "publication_doi": ["10.1073/pnas.2213271120", "10.1128/msystems.01261-22"]}

    def test_experiment_ids_list(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(experiment_ids=["exp_1"])
        assert conditions == ["a.experiment_id IN $experiment_ids"]
        assert params == {"experiment_ids": ["exp_1"]}

    def test_assay_ids_list(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            assay_ids=["metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration"])
        assert conditions == ["a.id IN $assay_ids"]
        assert "assay_ids" in params

    def test_metabolite_ids_uses_exists_clause(self):
        """metabolite_ids filter traverses both arms via EXISTS, not IN-list on a.*."""
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            metabolite_ids=["kegg.compound:C00074"])
        assert len(conditions) == 1
        assert "EXISTS {" in conditions[0]
        assert "Assay_quantifies_metabolite" in conditions[0]
        assert "Assay_flags_metabolite" in conditions[0]
        assert "m.id IN $metabolite_ids" in conditions[0]
        assert params == {"metabolite_ids": ["kegg.compound:C00074"]}

    def test_exclude_metabolite_ids_uses_not_exists(self):
        """exclude_metabolite_ids is set-difference on the same EXISTS shape."""
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            exclude_metabolite_ids=["kegg.compound:C00031"])
        assert len(conditions) == 1
        assert "NOT EXISTS {" in conditions[0]
        assert "m.id IN $exclude_metabolite_ids" in conditions[0]
        assert params == {"exclude_metabolite_ids": ["kegg.compound:C00031"]}

    def test_rankable_true_coerces_to_string(self):
        """Phase 5 D4: API takes bool, Cypher compares to string 'true'."""
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(rankable=True)
        assert conditions == ["a.rankable = $rankable_str"]
        assert params == {"rankable_str": "true"}

    def test_rankable_false_coerces_to_string(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(rankable=False)
        assert conditions == ["a.rankable = $rankable_str"]
        assert params == {"rankable_str": "false"}

    def test_combined_filters(self):
        from multiomics_explorer.kg.queries_lib import _list_metabolite_assays_where
        conditions, params = _list_metabolite_assays_where(
            organism="MIT9301", value_kind="boolean", rankable=False)
        assert len(conditions) == 3
        assert params.keys() == {"organism", "value_kind", "rankable_str"}
```

- [ ] **Step 2: Run tests — expect `ImportError`**

Run: `pytest tests/unit/test_query_builders.py::TestListMetaboliteAssaysWhere -v`
Expected: every test FAILs with `ImportError: cannot import name '_list_metabolite_assays_where'`.

---

### Task 2: Implement `_list_metabolite_assays_where` helper

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (append after the existing DM-family builders so co-located with the other discovery-tool helpers)

- [ ] **Step 1: Add the helper**

```python
def _list_metabolite_assays_where(
    *,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    assay_ids: list[str] | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    rankable: bool | None = None,
) -> tuple[list[str], dict]:
    """Shared WHERE-clause builder for build_list_metabolite_assays{,_summary}.

    Mirrors `_list_derived_metrics_where` but on `a:MetaboliteAssay` instead of
    `dm:DerivedMetric`. Adds two Phase-5-specific filters that DM lacks:
    - `metabolite_ids` / `exclude_metabolite_ids` — EXISTS / NOT EXISTS clauses
      traversing `Assay_quantifies_metabolite | Assay_flags_metabolite` to find
      assays that measure (or skip) specific compounds.

    Returns:
        (conditions, params): list of WHERE-clause snippets joined by AND in
        the caller, plus the parameters dict.
    """
    conditions: list[str] = []
    params: dict = {}

    if organism is not None:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ') "
            "WHERE toLower(a.organism_name) CONTAINS word)"
        )
        params["organism"] = organism
    if metric_types:
        conditions.append("a.metric_type IN $metric_types")
        params["metric_types"] = metric_types
    if value_kind is not None:
        conditions.append("a.value_kind = $value_kind")
        params["value_kind"] = value_kind
    if compartment is not None:
        conditions.append("a.compartment = $compartment")
        params["compartment"] = compartment
    if treatment_type:
        conditions.append(
            "ANY(t IN coalesce(a.treatment_type, []) "
            "WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]
    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(a.background_factors, []) "
            "WHERE toLower(bf) IN $background_factors_lower)"
        )
        params["background_factors_lower"] = [bf.lower() for bf in background_factors]
    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(a.growth_phases, []) "
            "WHERE toLower(gp) IN $growth_phases_lower)"
        )
        params["growth_phases_lower"] = [gp.lower() for gp in growth_phases]
    if publication_doi:
        conditions.append("a.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi
    if experiment_ids:
        conditions.append("a.experiment_id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    if assay_ids:
        conditions.append("a.id IN $assay_ids")
        params["assay_ids"] = assay_ids
    if metabolite_ids:
        conditions.append(
            "EXISTS { MATCH (a)-[:Assay_quantifies_metabolite|Assay_flags_metabolite]"
            "->(m:Metabolite) WHERE m.id IN $metabolite_ids }"
        )
        params["metabolite_ids"] = metabolite_ids
    if exclude_metabolite_ids:
        conditions.append(
            "NOT EXISTS { MATCH (a)-[:Assay_quantifies_metabolite|Assay_flags_metabolite]"
            "->(m:Metabolite) WHERE m.id IN $exclude_metabolite_ids }"
        )
        params["exclude_metabolite_ids"] = exclude_metabolite_ids
    if rankable is not None:
        conditions.append("a.rankable = $rankable_str")
        params["rankable_str"] = "true" if rankable else "false"

    return conditions, params
```

- [ ] **Step 2: Run tests — expect all green**

Run: `pytest tests/unit/test_query_builders.py::TestListMetaboliteAssaysWhere -v`
Expected: 16 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_query_builders.py multiomics_explorer/kg/queries_lib.py
git commit -m "feat(list_metabolite_assays): add WHERE helper

_list_metabolite_assays_where is the shared WHERE-clause builder for the
detail and summary Cypher builders. Mirrors _list_derived_metrics_where with
two Phase-5-specific filters: metabolite_ids / exclude_metabolite_ids use
EXISTS/NOT EXISTS clauses traversing Assay_quantifies_metabolite |
Assay_flags_metabolite to find assays measuring (or excluding) specific
compounds. Phase 5 spec docs/tool-specs/list_metabolite_assays.md §4."
```

---

### Task 3: Add `build_list_metabolite_assays_summary` tests

**Files:**
- Modify: `tests/unit/test_query_builders.py` (append after Task 1's class)

- [ ] **Step 1: Add the test class**

```python
class TestBuildListMetaboliteAssaysSummary:
    """Tests for the summary-mode Cypher builder."""

    def test_no_filters_no_search(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays_summary
        cypher, params = build_list_metabolite_assays_summary()
        assert "MATCH (a:MetaboliteAssay)" in cypher
        assert "CALL { MATCH (all_a:MetaboliteAssay) RETURN count(all_a) AS total_entries }" in cypher
        assert "OPTIONAL MATCH (a)-[r:Assay_quantifies_metabolite]->(:Metabolite)" in cypher
        assert "[s IN collect(r.detection_status) WHERE s IS NOT NULL]" in cypher
        assert "apoc.coll.frequencies(orgs) AS by_organism" in cypher
        assert "apoc.coll.frequencies(vks) AS by_value_kind" in cypher
        assert "apoc.coll.frequencies(comps) AS by_compartment" in cypher
        assert "apoc.coll.frequencies(mts) AS top_metric_types" in cypher
        assert "apoc.coll.frequencies(tts) AS by_treatment_type" in cypher
        assert "apoc.coll.frequencies(bfs) AS by_background_factors" in cypher
        assert "apoc.coll.frequencies(gps) AS by_growth_phase" in cypher
        assert "apoc.coll.frequencies(all_det) AS by_detection_status" in cypher
        assert "sum(a.total_metabolite_count) AS metabolite_count_total" in cypher
        assert "WHERE" not in cypher
        assert params == {}

    def test_with_organism_adds_where(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays_summary
        cypher, params = build_list_metabolite_assays_summary(organism="MIT9313")
        assert "WHERE ALL(word IN split(toLower($organism), ' ')" in cypher
        assert "toLower(a.organism_name) CONTAINS word" in cypher
        assert params == {"organism": "MIT9313"}

    def test_search_text_uses_fulltext_index(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays_summary
        cypher, params = build_list_metabolite_assays_summary(search_text="chitosan")
        assert "CALL db.index.fulltext.queryNodes('metaboliteAssayFullText'" in cypher
        assert "YIELD node AS a, score" in cypher
        assert "max(score) AS score_max" in cypher
        assert "percentileDisc(score, 0.5) AS score_median" in cypher
        assert params == {"search_text": "chitosan"}

    def test_search_text_combined_with_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays_summary
        cypher, params = build_list_metabolite_assays_summary(
            search_text="cellular concentration", value_kind="numeric")
        assert "metaboliteAssayFullText" in cypher
        assert "WHERE a.value_kind = $value_kind" in cypher
        assert params == {"search_text": "cellular concentration", "value_kind": "numeric"}

    def test_shares_where_clause_with_helper(self):
        """Filters from _list_metabolite_assays_where flow through unchanged."""
        from multiomics_explorer.kg.queries_lib import (
            build_list_metabolite_assays_summary,
            _list_metabolite_assays_where,
        )
        cypher, params = build_list_metabolite_assays_summary(
            organism="MIT9301", rankable=True, value_kind="numeric")
        helper_conds, helper_params = _list_metabolite_assays_where(
            organism="MIT9301", rankable=True, value_kind="numeric")
        for cond in helper_conds:
            assert cond in cypher
        assert params == helper_params

    def test_metabolite_count_total_summed(self):
        """metabolite_count_total is sum across matching assays (cumulative, not distinct)."""
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays_summary
        cypher, _ = build_list_metabolite_assays_summary()
        assert "sum(a.total_metabolite_count) AS metabolite_count_total" in cypher
```

- [ ] **Step 2: Run tests — expect `ImportError`**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListMetaboliteAssaysSummary -v`
Expected: every test FAILs.

---

### Task 4: Implement `build_list_metabolite_assays_summary`

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (append after `_list_metabolite_assays_where`)

- [ ] **Step 1: Add the builder**

```python
def build_list_metabolite_assays_summary(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    assay_ids: list[str] | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    rankable: bool | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for list_metabolite_assays.

    RETURN keys:
      total_entries, total_matching, metabolite_count_total,
      by_organism, by_value_kind, by_compartment, top_metric_types,
      by_treatment_type, by_background_factors, by_growth_phase,
      by_detection_status.
    When `search_text` is set, also returns: score_max, score_median.
    """
    conditions, params = _list_metabolite_assays_where(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, treatment_type=treatment_type,
        background_factors=background_factors, growth_phases=growth_phases,
        publication_doi=publication_doi, experiment_ids=experiment_ids,
        assay_ids=assay_ids, metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids, rankable=rankable,
    )

    if search_text is not None:
        match_block = (
            "CALL db.index.fulltext.queryNodes('metaboliteAssayFullText', $search_text) "
            "YIELD node AS a, score\n"
        )
        params["search_text"] = search_text
        score_extras = (
            ",\n     max(score) AS score_max,\n"
            "     percentileDisc(score, 0.5) AS score_median"
        )
        score_return = ",\n       score_max,\n       score_median"
    else:
        match_block = "MATCH (a:MetaboliteAssay)\n"
        score_extras = ""
        score_return = ""

    where_block = (
        "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
    )

    cypher = (
        "CALL { MATCH (all_a:MetaboliteAssay) RETURN count(all_a) AS total_entries }\n"
        f"{match_block}"
        f"{where_block}"
        "OPTIONAL MATCH (a)-[r:Assay_quantifies_metabolite]->(:Metabolite)\n"
        "WITH total_entries, a, [s IN collect(r.detection_status) WHERE s IS NOT NULL] AS det\n"
        "WITH total_entries,\n"
        "     collect(a.organism_name) AS orgs,\n"
        "     collect(a.value_kind) AS vks,\n"
        "     collect(a.compartment) AS comps,\n"
        "     collect(a.metric_type) AS mts,\n"
        "     apoc.coll.flatten(collect(coalesce(a.treatment_type, []))) AS tts,\n"
        "     apoc.coll.flatten(collect(coalesce(a.background_factors, []))) AS bfs,\n"
        "     apoc.coll.flatten(collect(coalesce(a.growth_phases, []))) AS gps,\n"
        "     apoc.coll.flatten(collect(det)) AS all_det,\n"
        "     count(a) AS total_matching,\n"
        "     sum(a.total_metabolite_count) AS metabolite_count_total"
        f"{score_extras}\n"
        "RETURN total_entries, total_matching, metabolite_count_total,\n"
        "       apoc.coll.frequencies(orgs) AS by_organism,\n"
        "       apoc.coll.frequencies(vks) AS by_value_kind,\n"
        "       apoc.coll.frequencies(comps) AS by_compartment,\n"
        "       apoc.coll.frequencies(mts) AS top_metric_types,\n"
        "       apoc.coll.frequencies(tts) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(bfs) AS by_background_factors,\n"
        "       apoc.coll.frequencies(gps) AS by_growth_phase,\n"
        "       apoc.coll.frequencies(all_det) AS by_detection_status"
        f"{score_return}"
    )
    return cypher, params
```

- [ ] **Step 2: Run tests — expect all green**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListMetaboliteAssaysSummary -v`
Expected: 6 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_query_builders.py multiomics_explorer/kg/queries_lib.py
git commit -m "feat(list_metabolite_assays): add summary builder

build_list_metabolite_assays_summary returns the envelope rollup with 8
breakdowns (by_organism, by_value_kind, by_compartment, top_metric_types,
by_treatment_type, by_background_factors, by_growth_phase, by_detection_status)
plus metabolite_count_total (cumulative sum). Lucene retry path adds
score_max/score_median. Verified against live KG per spec §12.1."
```

---

### Task 5: Add `build_list_metabolite_assays` (detail) tests

**Files:**
- Modify: `tests/unit/test_query_builders.py` (append after Task 3's class)

- [ ] **Step 1: Add the test class**

```python
class TestBuildListMetaboliteAssays:
    """Tests for the detail-mode Cypher builder."""

    def test_no_filters_compact(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays()
        assert "MATCH (a:MetaboliteAssay)" in cypher
        # Compact RETURN columns
        assert "a.id AS assay_id" in cypher
        assert "a.name AS name" in cypher
        assert "a.metric_type AS metric_type" in cypher
        assert "a.value_kind AS value_kind" in cypher
        assert "(a.rankable = \"true\") AS rankable" in cypher  # bool coercion
        assert "a.unit AS unit" in cypher
        assert "a.field_description AS field_description" in cypher
        assert "a.organism_name AS organism_name" in cypher
        assert "a.experiment_id AS experiment_id" in cypher
        assert "a.publication_doi AS publication_doi" in cypher
        assert "a.compartment AS compartment" in cypher
        assert "a.omics_type AS omics_type" in cypher
        assert "coalesce(a.treatment_type, []) AS treatment_type" in cypher
        assert "coalesce(a.background_factors, []) AS background_factors" in cypher
        assert "coalesce(a.growth_phases, []) AS growth_phases" in cypher
        assert "a.total_metabolite_count AS total_metabolite_count" in cypher
        assert "a.aggregation_method AS aggregation_method" in cypher
        assert "a.preferred_id AS preferred_id" in cypher
        assert "a.value_min AS value_min" in cypher
        assert "a.value_q1 AS value_q1" in cypher
        assert "a.value_median AS value_median" in cypher
        assert "a.value_q3 AS value_q3" in cypher
        assert "a.value_max AS value_max" in cypher
        # timepoints rollup with sentinel-stripping
        assert (
            "[label IN collect(DISTINCT r.time_point) "
            "WHERE label IS NOT NULL AND label <> \"\" | label]"
        ) in cypher
        assert "AS timepoints" in cypher
        # detection_status_counts rollup
        assert "apoc.coll.frequencies(detection_statuses)" in cypher
        assert "AS detection_status_counts" in cypher
        # Verbose-only fields not present in compact
        assert "a.treatment AS treatment" not in cypher
        assert "a.light_condition AS light_condition" not in cypher
        # Sort key
        assert "ORDER BY a.organism_name ASC, a.value_kind ASC, a.id ASC" in cypher
        assert params == {}

    def test_verbose_adds_text_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, _ = build_list_metabolite_assays(verbose=True)
        assert "a.treatment AS treatment" in cypher
        assert "a.light_condition AS light_condition" in cypher
        assert "a.experimental_context AS experimental_context" in cypher

    def test_search_text_uses_fulltext_and_score(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays(search_text="chitosan")
        assert "CALL db.index.fulltext.queryNodes('metaboliteAssayFullText'" in cypher
        assert "YIELD node AS a, score" in cypher
        assert "score AS score" in cypher
        # Score-DESC must be the leading sort key when searching
        assert "ORDER BY score DESC, a.organism_name ASC" in cypher
        assert params == {"search_text": "chitosan"}

    def test_limit_offset_clauses(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays(limit=20, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params == {"limit": 20, "offset": 5}

    def test_limit_none_omits_clauses(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays(limit=None, offset=0)
        assert "LIMIT" not in cypher
        assert "SKIP" not in cypher
        assert params == {}

    def test_filters_through_helper(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays(
            organism="MIT9313", value_kind="numeric", rankable=True)
        assert "WHERE" in cypher
        assert "a.value_kind = $value_kind" in cypher
        assert "a.rankable = $rankable_str" in cypher
        assert params["value_kind"] == "numeric"
        assert params["rankable_str"] == "true"
        assert params["organism"] == "MIT9313"

    def test_rankable_returned_as_bool_via_string_compare(self):
        """Per Phase 5 D4: per-row rankable is bool, derived from string compare."""
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, _ = build_list_metabolite_assays()
        assert "(a.rankable = \"true\") AS rankable" in cypher

    def test_metabolite_ids_filter_appears(self):
        from multiomics_explorer.kg.queries_lib import build_list_metabolite_assays
        cypher, params = build_list_metabolite_assays(
            metabolite_ids=["kegg.compound:C00074"])
        assert "EXISTS {" in cypher
        assert "Assay_quantifies_metabolite|Assay_flags_metabolite" in cypher
        assert params == {"metabolite_ids": ["kegg.compound:C00074"]}
```

- [ ] **Step 2: Run tests — expect `ImportError`**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListMetaboliteAssays -v`
Expected: every test FAILs.

---

### Task 6: Implement `build_list_metabolite_assays` (detail)

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (append after `build_list_metabolite_assays_summary`)

- [ ] **Step 1: Add the builder**

The full Cypher pattern (verified live 2026-05-06) is in spec [§12.1 detail block](../../tool-specs/2026-05-05-phase5-greenfield-assay-tools.md#121-list_metabolite_assays). Paraphrase:

```python
def build_list_metabolite_assays(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    assay_ids: list[str] | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    rankable: bool | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for list_metabolite_assays.

    RETURN keys (compact):
      assay_id, name, metric_type, value_kind, rankable, unit,
      field_description, organism_name, experiment_id, publication_doi,
      compartment, omics_type, treatment_type, background_factors,
      growth_phases, total_metabolite_count, aggregation_method,
      preferred_id, value_min, value_q1, value_median, value_q3, value_max,
      timepoints, detection_status_counts.
    When `search_text` set: + `score`.
    Verbose adds: treatment, light_condition, experimental_context.
    """
    conditions, params = _list_metabolite_assays_where(
        organism=organism, metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, treatment_type=treatment_type,
        background_factors=background_factors, growth_phases=growth_phases,
        publication_doi=publication_doi, experiment_ids=experiment_ids,
        assay_ids=assay_ids, metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids, rankable=rankable,
    )

    if search_text is not None:
        match_block = (
            "CALL db.index.fulltext.queryNodes('metaboliteAssayFullText', $search_text) "
            "YIELD node AS a, score\n"
        )
        params["search_text"] = search_text
        score_col = ",\n       score AS score"
        order_by = (
            "ORDER BY score DESC, a.organism_name ASC, a.value_kind ASC, a.id ASC"
        )
    else:
        match_block = "MATCH (a:MetaboliteAssay)\n"
        score_col = ""
        order_by = "ORDER BY a.organism_name ASC, a.value_kind ASC, a.id ASC"

    where_block = (
        "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
    )

    if verbose:
        verbose_cols = (
            ",\n       a.treatment AS treatment,\n"
            "       a.light_condition AS light_condition,\n"
            "       a.experimental_context AS experimental_context"
        )
    else:
        verbose_cols = ""

    pagination = ""
    if limit is not None:
        params["limit"] = limit
        params["offset"] = offset
        pagination = "\nSKIP $offset\nLIMIT $limit"

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "OPTIONAL MATCH (a)-[r:Assay_quantifies_metabolite]->(:Metabolite)\n"
        "WITH a, "
        "[label IN collect(DISTINCT r.time_point) "
        "WHERE label IS NOT NULL AND label <> \"\" | label] AS timepoints,\n"
        "     [s IN collect(r.detection_status) WHERE s IS NOT NULL] AS detection_statuses"
        + (",\n     score" if search_text is not None else "")
        + "\n"
        "WITH a, timepoints,\n"
        "     CASE WHEN size(detection_statuses) = 0 THEN [] "
        "ELSE apoc.coll.frequencies(detection_statuses) END AS detection_status_counts"
        + (",\n     score" if search_text is not None else "")
        + "\n"
        "RETURN\n"
        "       a.id AS assay_id,\n"
        "       a.name AS name,\n"
        "       a.metric_type AS metric_type,\n"
        "       a.value_kind AS value_kind,\n"
        "       (a.rankable = \"true\") AS rankable,\n"
        "       a.unit AS unit,\n"
        "       a.field_description AS field_description,\n"
        "       a.organism_name AS organism_name,\n"
        "       a.experiment_id AS experiment_id,\n"
        "       a.publication_doi AS publication_doi,\n"
        "       a.compartment AS compartment,\n"
        "       a.omics_type AS omics_type,\n"
        "       coalesce(a.treatment_type, []) AS treatment_type,\n"
        "       coalesce(a.background_factors, []) AS background_factors,\n"
        "       coalesce(a.growth_phases, []) AS growth_phases,\n"
        "       a.total_metabolite_count AS total_metabolite_count,\n"
        "       a.aggregation_method AS aggregation_method,\n"
        "       a.preferred_id AS preferred_id,\n"
        "       a.value_min AS value_min,\n"
        "       a.value_q1 AS value_q1,\n"
        "       a.value_median AS value_median,\n"
        "       a.value_q3 AS value_q3,\n"
        "       a.value_max AS value_max,\n"
        "       timepoints,\n"
        "       detection_status_counts"
        f"{score_col}{verbose_cols}\n"
        f"{order_by}"
        f"{pagination}"
    )
    return cypher, params
```

- [ ] **Step 2: Run tests — expect all green**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListMetaboliteAssays -v`
Expected: 8 passed.

- [ ] **Step 3: Run all unit tests — confirm no regressions**

Run: `uv run pytest tests/unit/ -q`
Expected: only the new tests are added; pre-existing tests still green.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_query_builders.py multiomics_explorer/kg/queries_lib.py
git commit -m "feat(list_metabolite_assays): add detail builder

build_list_metabolite_assays returns the per-row schema (24 compact
columns + 3 verbose) including timepoints (sentinel-stripped per Phase 5 D3)
and detection_status_counts (per-assay rollup over outgoing
Assay_quantifies_metabolite edges — Audit §4.3.3 primary headline at
discovery time). Lucene path adds score column with score-DESC sort.
Verified against live KG per spec §12.1."
```

---

### Task 7: Add API function tests

**Files:**
- Modify: `tests/unit/test_api_functions.py` (append at end)

- [ ] **Step 1: Add the test class**

```python
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
            Neo4jClientError(message="Failed to parse query: chitosan AND"),
            summary_row,
            [],
        ]
        result = list_metabolite_assays(search_text="chitosan AND", conn=conn)
        assert result["total_matching"] == 0

    def test_not_found_structured_for_batch_inputs(self):
        """`not_found` carries per-batch buckets (parent §11 Conv B)."""
        from multiomics_explorer.api.functions import list_metabolite_assays
        summary_row = [{
            "total_entries": 10, "total_matching": 1,
            "metabolite_count_total": 92,
            "by_organism": [], "by_value_kind": [], "by_compartment": [],
            "top_metric_types": [], "by_treatment_type": [],
            "by_background_factors": [], "by_growth_phase": [],
            "by_detection_status": [],
        }]
        detail_rows = [{
            "assay_id": "metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration",
        }]
        result = list_metabolite_assays(
            assay_ids=[
                "metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration",
                "non_existent_assay_id",
            ],
            conn=self._mock_conn(summary_row, detail_rows))
        assert "not_found" in result
        assert "assay_ids" in result["not_found"]
        assert "non_existent_assay_id" in result["not_found"]["assay_ids"]
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
```

- [ ] **Step 2: Run tests — expect import errors**

Run: `pytest tests/unit/test_api_functions.py::TestListMetaboliteAssays -v`
Expected: every test FAILs with `ImportError`.

---

### Task 8: Implement API function + exports

**Files:**
- Modify: `multiomics_explorer/api/functions.py` (append after `list_derived_metrics`)
- Modify: `multiomics_explorer/api/__init__.py` (add import + `__all__`)
- Modify: `multiomics_explorer/__init__.py` (add import + `__all__`)

- [ ] **Step 1: Add the API function**

```python
def list_metabolite_assays(
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: Literal["numeric", "boolean"] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    assay_ids: list[str] | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    rankable: bool | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List MetaboliteAssay nodes — discovery surface for the metabolomics
    measurement layer. Mirrors `list_derived_metrics`.

    Returns dict with envelope keys:
      total_entries, total_matching, metabolite_count_total,
      by_organism, by_value_kind, by_compartment, top_metric_types,
      by_treatment_type, by_background_factors, by_growth_phase,
      by_detection_status, score_max (opt), score_median (opt),
      returned, offset, truncated, not_found, results.

    Per-result compact:
      assay_id, name, metric_type, value_kind, rankable, unit,
      field_description, organism_name, experiment_id, publication_doi,
      compartment, omics_type, treatment_type, background_factors,
      growth_phases, total_metabolite_count, aggregation_method,
      preferred_id, value_min, value_q1, value_median, value_q3, value_max,
      timepoints, detection_status_counts (+ score when searching).
    Verbose adds: treatment, light_condition, experimental_context.

    `not_found` is structured per parent §11 Conv B / §13.6:
      {assay_ids: [...], metabolite_ids: [...], experiment_ids: [...],
       publication_doi: [...]} — one bucket per batch input. Empty per field
      when all matched.
    """
    if search_text is not None and not search_text.strip():
        raise ValueError("search_text must not be empty if provided.")

    conn = _default_conn(conn)
    if summary:
        limit = 0

    builder_kwargs = dict(
        search_text=search_text, organism=organism, metric_types=metric_types,
        value_kind=value_kind, compartment=compartment,
        treatment_type=treatment_type, background_factors=background_factors,
        growth_phases=growth_phases, publication_doi=publication_doi,
        experiment_ids=experiment_ids, assay_ids=assay_ids,
        metabolite_ids=metabolite_ids,
        exclude_metabolite_ids=exclude_metabolite_ids, rankable=rankable,
    )

    # ---- Summary query (always runs) -------------------------------------
    sum_cypher, sum_params = build_list_metabolite_assays_summary(**builder_kwargs)
    try:
        sum_result = conn.execute_query(sum_cypher, **sum_params)
    except Neo4jClientError as e:
        if search_text and _is_lucene_parse_error(e):
            logger.debug("list_metabolite_assays summary: Lucene parse error, retrying")
            builder_kwargs_retry = {**builder_kwargs, "search_text": _lucene_escape(search_text)}
            sum_cypher, sum_params = build_list_metabolite_assays_summary(**builder_kwargs_retry)
            sum_result = conn.execute_query(sum_cypher, **sum_params)
        else:
            raise

    summary_row = sum_result[0] if sum_result else {}
    total_entries = summary_row.get("total_entries", 0)
    total_matching = summary_row.get("total_matching", 0)
    metabolite_count_total = summary_row.get("metabolite_count_total", 0)

    # Rename apoc.coll.frequencies output keys (item/count → domain).
    by_organism = _rename_freq(
        summary_row.get("by_organism", []), "organism_name")
    by_value_kind = _rename_freq(
        summary_row.get("by_value_kind", []), "value_kind")
    by_compartment = _rename_freq(
        summary_row.get("by_compartment", []), "compartment")
    top_metric_types = _rename_freq(
        summary_row.get("top_metric_types", []), "metric_type")
    by_treatment_type = _rename_freq(
        summary_row.get("by_treatment_type", []), "treatment_type")
    by_background_factors = _rename_freq(
        summary_row.get("by_background_factors", []), "background_factor")
    by_growth_phase = _rename_freq(
        summary_row.get("by_growth_phase", []), "growth_phase")
    by_detection_status = _rename_freq(
        summary_row.get("by_detection_status", []), "detection_status")
    score_max = summary_row.get("score_max")
    score_median = summary_row.get("score_median")

    # ---- Detail query (skipped when limit == 0) ---------------------------
    if limit == 0:
        results: list[dict] = []
    else:
        det_cypher, det_params = build_list_metabolite_assays(
            **builder_kwargs, verbose=verbose, limit=limit, offset=offset)
        try:
            results = conn.execute_query(det_cypher, **det_params)
        except Neo4jClientError as e:
            if search_text and _is_lucene_parse_error(e):
                logger.debug("list_metabolite_assays detail: Lucene parse error, retrying")
                builder_kwargs_retry = {**builder_kwargs, "search_text": _lucene_escape(search_text)}
                det_cypher, det_params = build_list_metabolite_assays(
                    **builder_kwargs_retry, verbose=verbose,
                    limit=limit, offset=offset)
                results = conn.execute_query(det_cypher, **det_params)
            else:
                raise

    # ---- not_found (structured per §11 Conv B / §13.6) -------------------
    matched_assay_ids: set[str] = {r["assay_id"] for r in results}
    not_found = {
        "assay_ids": [
            aid for aid in (assay_ids or []) if aid not in matched_assay_ids
        ] if assay_ids else [],
        "metabolite_ids": [],
        "experiment_ids": [],
        "publication_doi": [],
    }
    if metabolite_ids or experiment_ids or publication_doi:
        # For these batches, "not_found" requires a separate lookup —
        # populate by checking what survived the filter pipeline.
        # Simplification: since limit may have truncated rows, we compute
        # not_found against the full matching set, not the returned slice.
        # For metabolite_ids / experiment_ids / publication_doi, an empty
        # `total_matching` AND a non-empty input list ⇒ all unmatched.
        # Fine-grained per-ID validation would need a separate count query;
        # acceptable simplification per parent §13.6 (multi-batch tools
        # surface unknown IDs at first call).
        if total_matching == 0:
            not_found["metabolite_ids"] = list(metabolite_ids or [])
            not_found["experiment_ids"] = list(experiment_ids or [])
            not_found["publication_doi"] = list(publication_doi or [])

    return {
        "total_entries": total_entries,
        "total_matching": total_matching,
        "metabolite_count_total": metabolite_count_total,
        "by_organism": by_organism,
        "by_value_kind": by_value_kind,
        "by_compartment": by_compartment,
        "top_metric_types": top_metric_types,
        "by_treatment_type": by_treatment_type,
        "by_background_factors": by_background_factors,
        "by_growth_phase": by_growth_phase,
        "by_detection_status": by_detection_status,
        "score_max": score_max,
        "score_median": score_median,
        "returned": len(results),
        "offset": offset,
        "truncated": total_matching > len(results),
        "not_found": not_found,
        "results": results,
    }
```

- [ ] **Step 2: Add to `multiomics_explorer/api/__init__.py`**

```python
from .functions import (
    # ... existing imports ...
    list_metabolite_assays,
)

__all__ = [
    # ... existing entries ...
    "list_metabolite_assays",
]
```

- [ ] **Step 3: Add to `multiomics_explorer/__init__.py`**

```python
from .api import (
    # ... existing imports ...
    list_metabolite_assays,
)

__all__ = [
    # ... existing entries ...
    "list_metabolite_assays",
]
```

- [ ] **Step 4: Add to `queries_lib` imports at top of `api/functions.py`**

Locate the existing `from ..kg.queries_lib import (...)` block and add:

```python
from ..kg.queries_lib import (
    # ... existing imports ...
    build_list_metabolite_assays,
    build_list_metabolite_assays_summary,
)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_api_functions.py::TestListMetaboliteAssays -v`
Expected: 8 passed.

- [ ] **Step 6: Run full unit suite — no regressions**

Run: `uv run pytest tests/unit/ -q`
Expected: previous 2,136 passes + new tests passing.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_api_functions.py multiomics_explorer/api/functions.py multiomics_explorer/api/__init__.py multiomics_explorer/__init__.py
git commit -m "feat(list_metabolite_assays): add API function + exports

api.list_metabolite_assays runs the 2-query pattern (summary + detail),
handles Lucene retry on metaboliteAssayFullText, and assembles the
envelope including structured not_found (per parent §11 Conv B / §13.6).
Re-exported from api/__init__.py and multiomics_explorer/__init__.py.
ValueError on empty search_text."
```

---

### Task 9: CyVer registry update

**Files:**
- Modify: `tests/integration/test_cyver_queries.py`

- [ ] **Step 1: Locate the `_BUILDERS` list**

Run: `grep -n '_BUILDERS' tests/integration/test_cyver_queries.py`

- [ ] **Step 2: Add the new builders**

```python
_BUILDERS = [
    # ... existing entries ...
    build_list_metabolite_assays,
    build_list_metabolite_assays_summary,
]
```

- [ ] **Step 3: Update `_KNOWN_MAP_KEYS` if needed**

Map projection keys used in the new builders:
- `timepoints`, `detection_status_counts`, `metabolite_count_total`, `by_detection_status` (envelope)
- All other RETURN aliases use bare `AS keyword` form (no map projections).

If the existing `_KNOWN_MAP_KEYS` set is missing any of these, add them. Most are unlikely to be there yet:

```python
_KNOWN_MAP_KEYS = {
    # ... existing ...
    "timepoints",
    "detection_status_counts",
    "metabolite_count_total",
    "by_detection_status",
}
```

- [ ] **Step 4: Run CyVer integration tests against live KG**

Run: `pytest tests/integration/test_cyver_queries.py -m kg -v`
Expected: existing tests still green; new builders pass `SyntaxValidator + SchemaValidator + PropertiesValidator` against live KG.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_cyver_queries.py
git commit -m "test(cyver): register list_metabolite_assays builders

Adds build_list_metabolite_assays and build_list_metabolite_assays_summary
to the CyVer _BUILDERS registry so SyntaxValidator + SchemaValidator +
PropertiesValidator run on every test pass against the live KG."
```

---

### Task 10: MCP wrapper Pydantic models + wrapper tests

**Files:**
- Modify: `tests/unit/test_tool_wrappers.py` (append at end + update `EXPECTED_TOOLS`)

- [ ] **Step 1: Update `EXPECTED_TOOLS`**

Locate the `EXPECTED_TOOLS` set and add:

```python
EXPECTED_TOOLS = {
    # ... existing names ...
    "list_metabolite_assays",
}
```

- [ ] **Step 2: Add the wrapper test class**

```python
class TestListMetaboliteAssaysWrapper:
    """MCP wrapper tests — calls api.list_metabolite_assays."""

    def _stub_api_response(self):
        return {
            "total_entries": 10,
            "total_matching": 10,
            "metabolite_count_total": 768,
            "by_organism": [{"organism_name": "Prochlorococcus MIT9301", "count": 4}],
            "by_value_kind": [{"value_kind": "numeric", "count": 8}],
            "by_compartment": [{"compartment": "whole_cell", "count": 7}],
            "top_metric_types": [{"metric_type": "cellular_concentration", "count": 5}],
            "by_treatment_type": [{"treatment_type": "carbon", "count": 2}],
            "by_background_factors": [{"background_factor": "axenic", "count": 10}],
            "by_growth_phase": [],
            "by_detection_status": [
                {"detection_status": "not_detected", "count": 902},
                {"detection_status": "detected", "count": 247},
                {"detection_status": "sporadic", "count": 51},
            ],
            "score_max": None, "score_median": None,
            "returned": 0, "offset": 0, "truncated": True,
            "not_found": {
                "assay_ids": [], "metabolite_ids": [],
                "experiment_ids": [], "publication_doi": [],
            },
            "results": [],
        }

    @pytest.mark.asyncio
    async def test_summary_returns_response_envelope(self, mock_ctx, monkeypatch):
        from multiomics_explorer.mcp_server.tools import register_tools
        # ... use existing test scaffolding to invoke the tool ...
        # (mirror TestListDerivedMetricsWrapper helpers in the same file)

    @pytest.mark.asyncio
    async def test_truncation_metadata(self, mock_ctx, monkeypatch):
        # When total_matching > returned → truncated=True
        ...

    @pytest.mark.asyncio
    async def test_value_error_becomes_tool_error(self, mock_ctx, monkeypatch):
        # api raises ValueError → wrapper raises ToolError
        ...

    @pytest.mark.asyncio
    async def test_rankable_bool_param(self, mock_ctx, monkeypatch):
        # Tool accepts Python True/False; api receives same
        ...

    @pytest.mark.asyncio
    async def test_structured_not_found(self, mock_ctx, monkeypatch):
        # not_found in response is the structured Pydantic model
        ...
```

> Implementation note: mirror the `TestListDerivedMetricsWrapper` helper pattern that already exists in `test_tool_wrappers.py`. Follow its `mock_ctx` + `monkeypatch.setattr(api, ...)` style.

- [ ] **Step 3: Run tests — expect failures**

Run: `pytest tests/unit/test_tool_wrappers.py::TestListMetaboliteAssaysWrapper -v`
Expected: tests fail (Pydantic models / wrapper not yet defined).

Also: `pytest tests/unit/test_tool_wrappers.py::TestExpectedTools -v`
Expected: fails with "missing tool: list_metabolite_assays" (or similar).

---

### Task 11: Implement MCP wrapper + Pydantic models

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` — register wrapper inside the existing `register_tools(mcp)` function

- [ ] **Step 1: Add Pydantic Result + Response models inside `register_tools`**

```python
class LmaOrganismBreakdown(BaseModel):
    organism_name: str = Field(description="Organism (e.g. 'Prochlorococcus MIT9301')")
    count: int = Field(description="Assay count for this organism (e.g. 4)")

class LmaValueKindBreakdown(BaseModel):
    value_kind: str = Field(description="Value kind ('numeric' or 'boolean')")
    count: int = Field(description="Assay count (e.g. 8)")

class LmaCompartmentBreakdown(BaseModel):
    compartment: str = Field(description="Compartment ('whole_cell' or 'extracellular')")
    count: int = Field(description="Assay count (e.g. 7)")

class LmaMetricTypeBreakdown(BaseModel):
    metric_type: str = Field(description="Metric type (e.g. 'cellular_concentration')")
    count: int = Field(description="Assay count (e.g. 5)")

class LmaTreatmentTypeBreakdown(BaseModel):
    treatment_type: str = Field(description="Treatment type (e.g. 'carbon')")
    count: int = Field(description="Assay count for this treatment (e.g. 2)")

class LmaBackgroundFactorBreakdown(BaseModel):
    background_factor: str = Field(description="Background factor (e.g. 'axenic')")
    count: int = Field(description="Assay count (e.g. 10)")

class LmaGrowthPhaseBreakdown(BaseModel):
    growth_phase: str = Field(description="Growth phase (e.g. 'exponential'). Empty list today — KG-MET-017 backfill pending.")
    count: int = Field(description="Assay count for this growth phase")

class LmaDetectionStatusBreakdown(BaseModel):
    detection_status: str = Field(description="Detection status: 'detected', 'sporadic', 'not_detected'. Numeric edges only — not_detected = tested-absent (parent §10).")
    count: int = Field(description="Edge count across matching numeric assays (e.g. 902 not_detected = 75% — tested-absent dominates)")

class LmaNotFound(BaseModel):
    assay_ids: list[str] = Field(default_factory=list, description="Input assay_ids not in the KG")
    metabolite_ids: list[str] = Field(default_factory=list, description="Input metabolite_ids that yielded no matching assay")
    experiment_ids: list[str] = Field(default_factory=list, description="Input experiment_ids that yielded no matching assay")
    publication_doi: list[str] = Field(default_factory=list, description="Input publication DOIs that yielded no matching assay")

class LmaDetectionStatusCount(BaseModel):
    detection_status: str = Field(description="'detected', 'sporadic', or 'not_detected'")
    count: int = Field(description="Edge count for this status on the assay")

class ListMetaboliteAssaysResult(BaseModel):
    assay_id: str = Field(description="Unique id (e.g. 'metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration'). Pass to drill-downs.")
    name: str = Field(description="Human-readable assay name (e.g. 'MIT9301 intracellular metabolite concentration (mol/cell)')")
    metric_type: str = Field(description="Category tag (e.g. 'cellular_concentration', 'extracellular_concentration', 'presence_flag_intracellular')")
    value_kind: Literal["numeric", "boolean"] = Field(description="Routes drill-down: 'numeric' → metabolites_by_quantifies_assay, 'boolean' → metabolites_by_flags_assay")
    rankable: bool = Field(description="True if metric_bucket / metric_percentile / rank_by_metric filters apply on the numeric drill-down (rankable=False on boolean assays)")
    unit: str = Field(description="Measurement unit (e.g. 'mol/cell', 'fg/cell'); empty string on boolean assays")
    field_description: str = Field(description="Canonical provenance description for the assay (e.g. 'Intracellular metabolite concentration in fg/cell, blank-corrected, replicate-aggregated; Capovilla 2023 Table sd03.')")
    organism_name: str = Field(description="Full organism name (e.g. 'Prochlorococcus MIT9313')")
    experiment_id: str = Field(description="Parent Experiment node id")
    publication_doi: str = Field(description="Parent publication DOI (e.g. '10.1073/pnas.2213271120')")
    compartment: str = Field(description="'whole_cell' or 'extracellular'")
    omics_type: str = Field(description="Always 'METABOLOMICS' for assays")
    treatment_type: list[str] = Field(default_factory=list, description="Treatment type(s) (e.g. ['carbon'])")
    background_factors: list[str] = Field(default_factory=list, description="Background factor(s) (e.g. ['axenic', 'light'])")
    growth_phases: list[str] = Field(default_factory=list, description="Growth phases — empty today (KG-MET-017 backfill pending)")
    total_metabolite_count: int = Field(description="Distinct metabolites measured by this assay (e.g. 92)")
    aggregation_method: str = Field(description="How replicates were aggregated (e.g. 'mean_across_replicates')")
    preferred_id: str = Field(description="Xref hint (e.g. 'metabolite_assay_id')")
    value_min: float | None = Field(default=None, description="Min observed value across all measurements on this assay (e.g. 0.0)")
    value_q1: float | None = Field(default=None, description="Q1 of values (e.g. 0.0012)")
    value_median: float | None = Field(default=None, description="Median (e.g. 0.0056)")
    value_q3: float | None = Field(default=None, description="Q3 (e.g. 0.012)")
    value_max: float | None = Field(default=None, description="Max (e.g. 0.16)")
    timepoints: list[str] = Field(default_factory=list, description="Timepoint labels (e.g. ['4 days', '6 days']). Empty list when the parent experiment is not time-resolved (per Phase 5 D3).")
    detection_status_counts: list[LmaDetectionStatusCount] = Field(default_factory=list, description="Per-status counts over outgoing Assay_quantifies_metabolite edges. Empty list on boolean assays. Lets the LLM route to detection-status-rich assays without a drill-down round-trip.")
    score: float | None = Field(default=None, description="Lucene relevance score (only when search_text was provided)")
    # Verbose-only:
    treatment: str | None = Field(default=None, description="Treatment description (verbose only)")
    light_condition: str | None = Field(default=None, description="Light condition (verbose only, e.g. 'continuous light')")
    experimental_context: str | None = Field(default=None, description="Long-form context (verbose only)")

class ListMetaboliteAssaysResponse(BaseModel):
    total_entries: int = Field(description="Total MetaboliteAssay nodes in KG (10 today)")
    total_matching: int = Field(description="Assays matching all filters")
    metabolite_count_total: int = Field(description="Cumulative sum of total_metabolite_count across matching assays. Same metabolite measured by N assays counts N times. For distinct count, use assays_by_metabolite(metabolite_ids=..., summary=True) or list_metabolites(metabolite_ids=...).")
    by_organism: list[LmaOrganismBreakdown] = Field(default_factory=list, description="Counts per organism, sorted desc")
    by_value_kind: list[LmaValueKindBreakdown] = Field(default_factory=list, description="Counts per value_kind. Routes drill-down: numeric → metabolites_by_quantifies_assay, boolean → metabolites_by_flags_assay.")
    by_compartment: list[LmaCompartmentBreakdown] = Field(default_factory=list, description="Counts per compartment")
    top_metric_types: list[LmaMetricTypeBreakdown] = Field(default_factory=list, description="Counts per metric_type, sorted desc. Pass to metabolites_by_quantifies_assay or metabolites_by_flags_assay (assay-id resolution required first).")
    by_treatment_type: list[LmaTreatmentTypeBreakdown] = Field(default_factory=list)
    by_background_factors: list[LmaBackgroundFactorBreakdown] = Field(default_factory=list)
    by_growth_phase: list[LmaGrowthPhaseBreakdown] = Field(default_factory=list, description="Empty today — KG-MET-017 backfill pending.")
    by_detection_status: list[LmaDetectionStatusBreakdown] = Field(default_factory=list, description="Envelope-level rollup of detection_status across all numeric edges of matching assays. Audit §4.3.3 primary headline. ~75% of numeric edges are not_detected (tested-absent — real biology, see parent §10).")
    score_max: float | None = Field(default=None, description="Max Lucene score (only with search_text)")
    score_median: float | None = Field(default=None, description="Median Lucene score (only with search_text)")
    returned: int = Field(description="Rows in this response")
    offset: int = Field(default=0, description="Pagination offset used")
    truncated: bool = Field(description="True when total_matching > returned")
    not_found: LmaNotFound = Field(default_factory=LmaNotFound, description="Per-batch-input unknown IDs (parent §11 Conv B / §13.6)")
    results: list[ListMetaboliteAssaysResult] = Field(default_factory=list)
```

- [ ] **Step 2: Add the `@mcp.tool` wrapper inside `register_tools`**

```python
@mcp.tool(
    tags={"metabolomics", "discovery", "catalog"},
    annotations={"readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def list_metabolite_assays(
    ctx: Context,
    search_text: Annotated[str | None, Field(
        description="Full-text search over MetaboliteAssay name, field_description, "
                    "treatment, experimental_context. E.g. 'chitosan', "
                    "'cellular concentration', 'KEGG export'.",
    )] = None,
    organism: Annotated[str | None, Field(
        description="Organism (case-insensitive substring CONTAINS). "
                    "E.g. 'MIT9301', 'Prochlorococcus MIT9313'.",
    )] = None,
    metric_types: Annotated[list[str] | None, Field(
        description="Filter by metric_type tags. Live values: "
                    "'cellular_concentration', 'extracellular_concentration', "
                    "'presence_flag_intracellular', 'presence_flag_extracellular'.",
    )] = None,
    value_kind: Annotated[Literal["numeric", "boolean"] | None, Field(
        description="'numeric' → metabolites_by_quantifies_assay drill-down; "
                    "'boolean' → metabolites_by_flags_assay.",
    )] = None,
    compartment: Annotated[str | None, Field(
        description="'whole_cell' or 'extracellular'. Exact match.",
    )] = None,
    treatment_type: Annotated[list[str] | None, Field(
        description="ANY-overlap. E.g. ['carbon'], ['phosphorus', 'growth_phase'].",
    )] = None,
    background_factors: Annotated[list[str] | None, Field(
        description="ANY-overlap. E.g. ['axenic', 'light'].",
    )] = None,
    growth_phases: Annotated[list[str] | None, Field(
        description="ANY-overlap. Empty today — KG-MET-017 backfill pending.",
    )] = None,
    publication_doi: Annotated[list[str] | None, Field(
        description="DOI(s). Exact match. E.g. ['10.1073/pnas.2213271120', "
                    "'10.1128/msystems.01261-22'].",
    )] = None,
    experiment_ids: Annotated[list[str] | None, Field(
        description="Experiment node id(s).",
    )] = None,
    assay_ids: Annotated[list[str] | None, Field(
        description="MetaboliteAssay id(s). `not_found.assay_ids` lists "
                    "unknowns.",
    )] = None,
    metabolite_ids: Annotated[list[str] | None, Field(
        description="Restrict to assays measuring at least one of these "
                    "metabolites (1-hop via Assay_quantifies_metabolite | "
                    "Assay_flags_metabolite). Full prefixed IDs, e.g. "
                    "['kegg.compound:C00074'].",
    )] = None,
    exclude_metabolite_ids: Annotated[list[str] | None, Field(
        description="Exclude assays measuring any of these metabolites "
                    "(set-difference cross-tool convention).",
    )] = None,
    rankable: Annotated[bool | None, Field(
        description="True → assays supporting rank/percentile/bucket on "
                    "metabolites_by_quantifies_assay's rankable-gated filters.",
    )] = None,
    summary: Annotated[bool, Field(
        description="Return summary fields only (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include heavy-text fields per row: treatment, "
                    "light_condition, experimental_context.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results (default 20 covers all 10 assays today).",
        ge=1,
    )] = 20,
    offset: Annotated[int, Field(
        description="Pagination offset (0-indexed).", ge=0,
    )] = 0,
) -> ListMetaboliteAssaysResponse:
    """Discover MetaboliteAssay nodes — discovery surface for the metabolomics
    measurement layer. Mirrors `list_derived_metrics`.

    Inspect `value_kind` (routes drill-down), `rankable` (gates rankable
    filters on the numeric drill-down), `compartment` (whole_cell vs
    extracellular), and per-row `detection_status_counts` (signals how much
    of the assay is detected / sporadic / not_detected — primary headline
    per audit §4.3.3).

    A row with `value=0` / `flag_value=false` / `detection_status='not_detected'`
    on the drill-down tools is *tested-absent* (assayed and not found, real
    biology) — distinct from a missing row, which is *unmeasured* (not in
    the assay's scope). See parent spec §10.

    After this, drill via:
    - metabolites_by_quantifies_assay(assay_ids=[...]) — numeric arm details
    - metabolites_by_flags_assay(assay_ids=[...]) — boolean arm details
    - assays_by_metabolite(metabolite_ids=[...]) — reverse lookup across both arms
    - list_metabolites(metabolite_ids=[...]) — chemistry context for measured compounds
    """
    await ctx.info(
        f"list_metabolite_assays search_text={search_text} "
        f"organism={organism} value_kind={value_kind} compartment={compartment} "
        f"summary={summary} verbose={verbose} limit={limit} offset={offset}"
    )
    try:
        conn = _conn(ctx)
        data = api.list_metabolite_assays(
            search_text=search_text, organism=organism,
            metric_types=metric_types, value_kind=value_kind,
            compartment=compartment, treatment_type=treatment_type,
            background_factors=background_factors, growth_phases=growth_phases,
            publication_doi=publication_doi, experiment_ids=experiment_ids,
            assay_ids=assay_ids, metabolite_ids=metabolite_ids,
            exclude_metabolite_ids=exclude_metabolite_ids, rankable=rankable,
            summary=summary, verbose=verbose, limit=limit, offset=offset,
            conn=conn,
        )
        results = [ListMetaboliteAssaysResult(
            **{**r, "detection_status_counts": [
                LmaDetectionStatusCount(detection_status=d.get("item", d.get("detection_status")), count=d["count"])
                for d in r.get("detection_status_counts", [])
            ]}
        ) for r in data["results"]]
        by_organism = [LmaOrganismBreakdown(**b) for b in data["by_organism"]]
        by_value_kind = [LmaValueKindBreakdown(**b) for b in data["by_value_kind"]]
        by_compartment = [LmaCompartmentBreakdown(**b) for b in data["by_compartment"]]
        top_metric_types = [LmaMetricTypeBreakdown(**b) for b in data["top_metric_types"]]
        by_treatment_type = [LmaTreatmentTypeBreakdown(**b) for b in data["by_treatment_type"]]
        by_background_factors = [LmaBackgroundFactorBreakdown(**b) for b in data["by_background_factors"]]
        by_growth_phase = [LmaGrowthPhaseBreakdown(**b) for b in data["by_growth_phase"]]
        by_detection_status = [LmaDetectionStatusBreakdown(**b) for b in data["by_detection_status"]]
        not_found = LmaNotFound(**data["not_found"])
        return ListMetaboliteAssaysResponse(
            total_entries=data["total_entries"],
            total_matching=data["total_matching"],
            metabolite_count_total=data["metabolite_count_total"],
            by_organism=by_organism, by_value_kind=by_value_kind,
            by_compartment=by_compartment, top_metric_types=top_metric_types,
            by_treatment_type=by_treatment_type,
            by_background_factors=by_background_factors,
            by_growth_phase=by_growth_phase,
            by_detection_status=by_detection_status,
            score_max=data.get("score_max"), score_median=data.get("score_median"),
            returned=data["returned"], offset=data["offset"],
            truncated=data["truncated"], not_found=not_found,
            results=results,
        )
    except ValueError as e:
        await ctx.warning(f"list_metabolite_assays error: {e}")
        raise ToolError(str(e))
    except Exception as e:
        await ctx.error(f"list_metabolite_assays unexpected error: {e}")
        raise ToolError(f"Error in list_metabolite_assays: {e}")
```

- [ ] **Step 3: Run wrapper tests**

Run: `pytest tests/unit/test_tool_wrappers.py::TestListMetaboliteAssaysWrapper tests/unit/test_tool_wrappers.py::TestExpectedTools -v`
Expected: all pass.

- [ ] **Step 4: Run full unit suite**

Run: `uv run pytest tests/unit/ -q`
Expected: 2,136 baseline + new tests passing.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_tool_wrappers.py multiomics_explorer/mcp_server/tools.py
git commit -m "feat(list_metabolite_assays): MCP wrapper + Pydantic models

ListMetaboliteAssaysResult / ListMetaboliteAssaysResponse with typed
sub-models for every breakdown (parent §11 Conv E). Field descriptions
use real KG values (parent §13.5 field rubric). Structured LmaNotFound
per parent §11 Conv B / §13.6. Tool docstring carries drill-down
signposting + tested-absent invariant (parent §10)."
```

---

### Task 12: Live-KG integration tests

**Files:**
- Modify: `tests/integration/test_mcp_tools.py` (append at end)

- [ ] **Step 1: Add the integration test class**

Baselines pinned to live KG state verified 2026-05-06 (spec §3 + §12.1 fixtures):

```python
@pytest.mark.kg
class TestListMetaboliteAssays:
    """Live-KG integration tests. Baselines from spec §3 + §12.1 fixtures (2026-05-06)."""

    def test_no_filters_returns_all_10_assays(self, kg_conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(conn=kg_conn)
        assert result["total_entries"] == 10
        assert result["total_matching"] == 10
        assert result["metabolite_count_total"] == 768  # cumulative-across-assays
        assert len(result["results"]) == 10

    def test_value_kind_numeric(self, kg_conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(value_kind="numeric", conn=kg_conn)
        assert result["total_matching"] == 8
        for r in result["results"]:
            assert r["value_kind"] == "numeric"
            assert r["rankable"] is True  # all 8 numeric are rankable

    def test_value_kind_boolean(self, kg_conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(value_kind="boolean", conn=kg_conn)
        assert result["total_matching"] == 2
        for r in result["results"]:
            assert r["value_kind"] == "boolean"
            assert r["rankable"] is False
            assert r["detection_status_counts"] == []

    def test_compartment_extracellular(self, kg_conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(compartment="extracellular", conn=kg_conn)
        assert result["total_matching"] == 3
        for r in result["results"]:
            assert r["compartment"] == "extracellular"

    def test_organism_contains_match(self, kg_conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(organism="MIT9301", conn=kg_conn)
        assert result["total_matching"] == 4
        for r in result["results"]:
            assert "MIT9301" in r["organism_name"]

    def test_metabolite_ids_filter_pep(self, kg_conn):
        """Phosphoenolpyruvate (C00074) is measured in all 10 assays."""
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(
            metabolite_ids=["kegg.compound:C00074"], conn=kg_conn)
        assert result["total_matching"] == 10

    def test_search_text_chitosan(self, kg_conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(search_text="chitosan", conn=kg_conn)
        # Capovilla 2023 chitosan paper has 2 numeric assays
        assert result["total_matching"] >= 2
        assert result["score_max"] is not None
        for r in result["results"]:
            assert r["score"] is not None

    def test_rankable_true_returns_8_numeric(self, kg_conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(rankable=True, conn=kg_conn)
        assert result["total_matching"] == 8

    def test_rankable_false_returns_2_boolean(self, kg_conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(rankable=False, conn=kg_conn)
        assert result["total_matching"] == 2

    def test_summary_returns_envelope_only(self, kg_conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(summary=True, conn=kg_conn)
        assert result["results"] == []
        assert result["truncated"] is True
        # Envelope rollups populated regardless of summary flag
        assert len(result["by_organism"]) > 0
        assert len(result["by_value_kind"]) == 2  # numeric, boolean
        # by_detection_status: tested-absent dominates (75%+)
        det_counts = {b["detection_status"]: b["count"] for b in result["by_detection_status"]}
        assert det_counts.get("not_detected", 0) >= 800

    def test_verbose_adds_text_columns(self, kg_conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(verbose=True, limit=1, conn=kg_conn)
        r = result["results"][0]
        assert "treatment" in r
        assert "light_condition" in r
        assert "experimental_context" in r

    def test_assay_ids_not_found(self, kg_conn):
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(
            assay_ids=["nonexistent_assay_id"], conn=kg_conn)
        assert result["total_matching"] == 0
        assert "nonexistent_assay_id" in result["not_found"]["assay_ids"]

    def test_capovilla_assay_has_2_timepoints(self, kg_conn):
        """MIT9313 chitosan assay: timepoints sentinel-stripped to ['4 days', '6 days']."""
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(
            assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"],
            conn=kg_conn)
        assert result["total_matching"] == 1
        r = result["results"][0]
        assert sorted(r["timepoints"]) == ["4 days", "6 days"]
        # detection_status_counts has 3 statuses on this assay (27 detected, 30 sporadic, 7 not_detected)
        statuses = {d["detection_status"]: d["count"] for d in r["detection_status_counts"]}
        assert statuses.get("detected", 0) == 27
        assert statuses.get("sporadic", 0) == 30
        assert statuses.get("not_detected", 0) == 7

    def test_kujawinski_assay_no_timepoints(self, kg_conn):
        """Kujawinski non-temporal experiment: timepoints == []."""
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(
            assay_ids=["metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration"],
            conn=kg_conn)
        assert result["total_matching"] == 1
        assert result["results"][0]["timepoints"] == []  # sentinel-stripped

    def test_growth_phases_empty_kg_met_017(self, kg_conn):
        """KG-MET-017: growth_phases empty on every assay today."""
        from multiomics_explorer.api import list_metabolite_assays
        result = list_metabolite_assays(conn=kg_conn)
        for r in result["results"]:
            assert r["growth_phases"] == []
        assert result["by_growth_phase"] == []
```

- [ ] **Step 2: Run integration tests against live KG**

Run: `uv run pytest tests/integration/test_mcp_tools.py::TestListMetaboliteAssays -m kg -v`
Expected: 14 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_mcp_tools.py
git commit -m "test(list_metabolite_assays): live-KG integration tests

Baselines pinned to KG state 2026-05-06 (spec §3 + §12.1 fixtures):
total_entries=10, value_kind={numeric:8, boolean:2}, compartment={whole_cell:7,
extracellular:3}, MIT9313 chitosan = 2 timepoints + (27/30/7) detection split,
Kujawinski non-temporal = empty timepoints. KG-MET-017 dependency confirmed
(growth_phases=[] everywhere)."
```

---

### Task 13: Author about-content YAML + regenerate markdown

**Files:**
- Create: `multiomics_explorer/inputs/tools/list_metabolite_assays.yaml`
- Generated: `multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_metabolite_assays.md` (do NOT hand-edit)

- [ ] **Step 1: Create the YAML**

```yaml
# multiomics_explorer/inputs/tools/list_metabolite_assays.yaml

examples:
  - title: Orient — what assays exist
    call: list_metabolite_assays(summary=True)
    response: |
      total_entries: 10
      total_matching: 10
      by_value_kind: [{value_kind: numeric, count: 8}, {value_kind: boolean, count: 2}]
      by_compartment: [{compartment: whole_cell, count: 7}, {compartment: extracellular, count: 3}]
      by_organism: [4 organisms across 2 papers]
      by_detection_status: [{not_detected: 902}, {detected: 247}, {sporadic: 51}]
      results: []  # summary=True

  - title: Discovery via fulltext (Capovilla chitosan paper)
    call: list_metabolite_assays(search_text="chitosan")

  - title: Pre-flight for numeric drill-down
    call: list_metabolite_assays(value_kind="numeric", rankable=True)

  - title: Find assays measuring a specific metabolite
    call: list_metabolite_assays(metabolite_ids=["kegg.compound:C00074"])  # PEP — in all 10 assays

  - title: Per-paper inventory
    call: list_metabolite_assays(publication_doi=["10.1073/pnas.2213271120"])

verbose_fields:
  - treatment
  - light_condition
  - experimental_context

chaining:
  - "list_metabolite_assays → metabolites_by_quantifies_assay(assay_ids=[...])"
  - "list_metabolite_assays → metabolites_by_flags_assay(assay_ids=[...])"
  - "list_metabolite_assays → assays_by_metabolite(metabolite_ids=[...])  # cross-organism reverse view"
  - "list_metabolite_assays → list_metabolites(metabolite_ids=[...])  # chemistry context for measured compounds"

mistakes:
  - First mistake — required mental-model framing (parent §10):
    wrong: "Filter out value=0 / flag_value=false rows on drill-downs assuming they're noise."
    right: "Those rows are tested-absent — the metabolite was *assayed and not found*. Real biology. Keep them unless explicitly investigating presence-only."

  - Wrong vs right — unmeasured-vs-tested-absent:
    wrong: "A metabolite missing from drill-down results means it was not detected."
    right: "Missing means *unmeasured* (not in the assay's scope). For 'tested and not found,' look for value=0 / flag_value=false / detection_status='not_detected' rows in the drill-down output."

  - Wrong vs right — `growth_phases` empty:
    wrong: "growth_phases=[] means the assay has no growth-state metadata."
    right: "growth_phases=[] today reflects unpopulated KG state (KG-MET-017 — KG team backfill pending). The schema field exists; values populate without explorer-side code change when the KG ask lands."

  - Wrong vs right — `metabolite_count_total` envelope semantics (rubric clause 7):
    wrong: "metabolite_count_total = total distinct metabolites across matching assays."
    right: "metabolite_count_total is *cumulative*: same metabolite measured by N assays counts N times. For distinct counts route to assays_by_metabolite(metabolite_ids=..., summary=True) → metabolites_matched, or list_metabolites(metabolite_ids=...)."

  - Pre-flight for drill-downs:
    wrong: "Calling metabolites_by_quantifies_assay with bucket / metric_percentile filters before checking assay rankable."
    right: "Call list_metabolite_assays(value_kind='numeric', rankable=True) first. Drill-down's rankable-gated filters raise if every selected assay has rankable=False, soft-exclude on mixed input."
```

- [ ] **Step 2: Regenerate about-content markdown**

Run: `uv run python scripts/build_about_content.py list_metabolite_assays`
Expected: writes `multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_metabolite_assays.md` (auto-generated; do NOT hand-edit).

- [ ] **Step 3: Run about-content consistency tests**

Run: `pytest tests/unit/test_about_content.py -v -k list_metabolite_assays`
Expected: passes.

- [ ] **Step 4: Run live about-examples integration test**

Run: `uv run pytest tests/integration/test_about_examples.py -m kg -v -k list_metabolite_assays`
Expected: every example in the YAML executes against the live KG.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/inputs/tools/list_metabolite_assays.yaml multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_metabolite_assays.md
git commit -m "docs(list_metabolite_assays): about-content YAML + regen

Authored YAML carries 5 examples, 4 chaining patterns, and 5 mistakes —
including the parent §10 tested-absent vs unmeasured invariant (wrong/right
pairs) and the metabolite_count_total cumulative-vs-distinct rubric note
(parent §13.5 clause 7). Generated md written to skills tree by
build_about_content.py."
```

---

### Task 14: Regression baselines + TOOL_BUILDERS

**Files:**
- Modify: `tests/regression/test_regression.py` (add to `TOOL_BUILDERS`)
- Modify: `tests/evals/cases.yaml` + `tests/evals/test_eval.py` `TOOL_BUILDERS` (if separate registry)
- Generated: `tests/regression/fixtures/...` (built via `--force-regen`)

- [ ] **Step 1: Register the builder**

```python
TOOL_BUILDERS = {
    # ... existing ...
    "list_metabolite_assays": build_list_metabolite_assays,
}
```

- [ ] **Step 2: Add eval cases to `tests/evals/cases.yaml`**

```yaml
- id: list_metabolite_assays_all
  tool: list_metabolite_assays
  desc: All 10 assays returned with no filters
  params: {}
  expect:
    min_rows: 10
    columns: [assay_id, name, metric_type, value_kind, rankable, compartment]

- id: list_metabolite_assays_numeric_only
  tool: list_metabolite_assays
  desc: value_kind=numeric → 8 rows
  params: {value_kind: numeric}
  expect:
    min_rows: 8
    max_rows: 8

- id: list_metabolite_assays_boolean_only
  tool: list_metabolite_assays
  desc: value_kind=boolean → 2 rows
  params: {value_kind: boolean}
  expect:
    min_rows: 2
    max_rows: 2

- id: list_metabolite_assays_metabolite_ids_pep
  tool: list_metabolite_assays
  desc: PEP measured in every assay
  params: {metabolite_ids: ["kegg.compound:C00074"]}
  expect:
    min_rows: 10
    max_rows: 10
```

- [ ] **Step 3: Add to evals `TOOL_BUILDERS` (separate registry)**

If `tests/evals/test_eval.py` has its own `TOOL_BUILDERS`, add the same entry.

- [ ] **Step 4: Generate regression baseline**

Run: `uv run pytest tests/regression/ --force-regen -m kg -k list_metabolite_assays`
Expected: writes a new fixture file under `tests/regression/fixtures/`.

- [ ] **Step 5: Re-run regression (no `--force-regen`) — verify pinned**

Run: `uv run pytest tests/regression/ -m kg -k list_metabolite_assays`
Expected: passes against the pinned fixture.

- [ ] **Step 6: Commit**

```bash
git add tests/regression/test_regression.py tests/regression/fixtures tests/evals/cases.yaml tests/evals/test_eval.py
git commit -m "test(list_metabolite_assays): regression + eval baselines

Adds list_metabolite_assays to the regression and eval TOOL_BUILDERS
registries. New regression fixture pinned to KG state 2026-05-06.
Eval cases cover no-filter / value_kind=numeric / value_kind=boolean /
metabolite_ids=PEP scenarios."
```

---

### Task 15: CLAUDE.md tool table

**Files:**
- Modify: `CLAUDE.md` (the MCP Tools table)

- [ ] **Step 1: Add the row**

Locate the `| Tool | Purpose |` table and insert (alphabetically — between `list_filter_values` and `list_metabolites` or next to `list_derived_metrics`):

```markdown
| `list_metabolite_assays` | Discover MetaboliteAssay nodes (metabolomics measurement layer; analog of `list_derived_metrics`). Pre-flight for the 3 drill-down tools. Filterable by organism, value_kind, compartment, metric_types, treatment_type, growth_phases, publication_doi, experiment_ids, assay_ids, metabolite_ids, exclude_metabolite_ids, rankable. Rich envelope: `by_organism`, `by_value_kind`, `by_compartment`, `top_metric_types`, `by_detection_status` (audit §4.3.3 primary headline — 75% of numeric edges are `not_detected`, i.e. tested-absent), `metabolite_count_total` (cumulative across assays — see field-rubric note). Per-row `detection_status_counts` rollup on numeric assays + `timepoints` (D3 sentinel-stripped). Structured `not_found` for multi-batch inputs. Tested-absent rows are real biology, never default-filter. |
```

- [ ] **Step 2: Sanity-check rendering**

Run: `grep -c "^| \`list_metabolite_assays\`" CLAUDE.md`
Expected: `1`

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): list_metabolite_assays tool table row"
```

---

### Task 16: Code review (hard gate)

**Files:** none (review-only)

- [ ] **Step 1: Push the branch (still local for review)**

Skip if running locally — code-reviewer reads from working tree.

- [ ] **Step 2: Run code-reviewer subagent**

Per parent §8 + add-or-update-tool SKILL.md §Stage 3:

> Code review is a HARD GATE — mocked unit tests can't validate actual Cypher. Only the reviewer reading the live Cypher catches things like wrong node labels in `MATCH` clauses, wrong relationship directions, or filter clauses that match-everything. The list_metabolites smoke test caught a `MATCH (o:Organism)` typo (label is `OrganismTaxon`) that all 1676 unit tests missed.

Dispatch `superpowers:requesting-code-review` against the diff vs `main`. Brief:
- Spec: `docs/tool-specs/list_metabolite_assays.md` (frozen)
- Parent context: `docs/tool-specs/2026-05-05-phase5-greenfield-assay-tools.md` (KG verification §3, conventions §11, anti-patterns §11.2, Phase 2 deliverables §13)
- Confirm: builder Cypher matches verified §12.1; CyVer registry updated; structured `not_found` shape correct; tested-absent invariant surfaced in docstring + YAML; no Cypher jargon in Field descriptions; real KG examples in Field text.

- [ ] **Step 3: Address any blocking findings**

Iterate per the reviewer's report. Fix → re-test → re-review until clean.

- [ ] **Step 4: Run final test pass**

Run in order:
1. `uv run pytest tests/unit/ -q` → all green
2. `uv run pytest tests/integration/ -m kg -q` → all green
3. `uv run pytest tests/regression/ -m kg -q` → all green
4. `uv run python scripts/validate_connection.py` → KG reachable (sanity)

- [ ] **Step 5: Use verification-before-completion**

Per `superpowers:verification-before-completion`: confirm every claim ("done", "fixed", "passing") is backed by command output. Cite exact pytest pass counts.

- [ ] **Step 6: Use finishing-a-development-branch**

Per `superpowers:finishing-a-development-branch`: present merge / PR / cleanup options to the user. Likely path: open a PR from `worktree-metabolites-phase5-list-assays` → `main`.

---

## Self-review checklist

**1. Spec coverage:**
- [x] Tool signature with all 16 params (Task 11) ↔ spec §4
- [x] Per-row schema 24 compact + 3 verbose (Task 6) ↔ spec §5
- [x] Envelope with `by_detection_status` rollup (Tasks 4, 11) ↔ spec §6
- [x] Sort key `score DESC, organism_name, value_kind, id` (Task 6) ↔ spec §6
- [x] D3 sentinel coercion on `timepoints` (Task 6) ↔ parent §11.D3
- [x] D4 string→bool on `rankable` (Tasks 2, 6, 11) ↔ parent §11 Conv K
- [x] D5 score envelope (Tasks 4, 11) ↔ parent §11 Conv J
- [x] D8 KG-MET-017 forward-compat (Task 11 docstring + Task 13 YAML) ↔ parent §3.5 + §13
- [x] Field-rubric clauses 1, 3, 4, 5, 6, 7, 8 (Task 11 + Task 13) ↔ parent §13.5
- [x] CyVer registry (Task 9) ↔ parent §13.2
- [x] Layer-2 exports (Task 8) ↔ parent §13.3
- [x] Anti-scope-creep guardrail (header + every implementer brief) ↔ parent §13.4
- [x] §10 tested-absent invariant in docstring (Task 11) + YAML mistakes (Task 13)
- [x] Structured `not_found` (Task 8 + Task 11) ↔ parent §11 Conv B / §13.6
- [x] NULL-handling `[s IN collect(...) WHERE s IS NOT NULL]` (Tasks 4, 6) ↔ parent §13.7
- [x] Code-reviewer hard gate (Task 16) ↔ parent §8 + add-or-update-tool §Stage 3

**2. Placeholder scan:** No `TBD`, no "Add error handling", no "Similar to Task N", no "implement later". Each step has actual content.

**3. Type consistency:**
- `_list_metabolite_assays_where` returns `tuple[list[str], dict]` (Task 2) ↔ used by `build_*` (Tasks 4, 6) ✓
- `(a.rankable = "true") AS rankable` produces bool in Cypher; per-row Pydantic uses `bool` (Tasks 6, 11) ✓
- Envelope key `metabolite_count_total` consistent across summary builder (Task 4), API (Task 8), and Pydantic Response (Task 11) ✓
- `detection_status_counts` per-row uses `LmaDetectionStatusCount` model (Task 11); the `apoc.coll.frequencies` output uses `{item, count}` and the wrapper renames `item → detection_status` (Task 11 wrapper Step 2 — confirm during impl) ✓
- `not_found` is `LmaNotFound` (Pydantic) in Response (Task 11), `dict` with the same keys in api/ (Task 8) ✓

---

## Plan complete

Ready for execution via `superpowers:subagent-driven-development` (recommended — fresh subagent per task, two-stage review) or `superpowers:executing-plans` (batch execution with checkpoints).

Worktree open at `.claude/worktrees/metabolites-phase5-list-assays` on `worktree-metabolites-phase5-list-assays` branch. Baseline 2,136 unit tests pass against KG state at main HEAD `8ba267d` (Phase 3 merged).
