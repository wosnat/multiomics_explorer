# Metabolites-by-Assay Slice Implementation Plan (3 tools — Mode B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the 3-tool drill-down + reverse-lookup metabolomics slice — `metabolites_by_quantifies_assay` (numeric drill-down), `metabolites_by_flags_assay` (boolean drill-down), `assays_by_metabolite` (polymorphic reverse-lookup) — closing the metabolomics surface after `list_metabolite_assays` (Tool 1) lands.

**Architecture:** Mode B 3-tool slice per `add-or-update-tool` SKILL.md. Four-layer build (`kg/queries_lib.py` → `api/functions.py` → `mcp_server/tools.py` → `inputs/tools/*.yaml` + about-content regen). Within each implementer file: build `metabolites_by_quantifies_assay` first as the template (carries the most edge-filter logic — rankable-gated diagnostics, by_metric envelope, sentinel coercions), then extend the pattern to `metabolites_by_flags_assay` (drops rankable gate, swaps `value`/`detection_status` for `flag_value`), then `assays_by_metabolite` (polymorphic UNION ALL — new shape, reuses scoping). Cross-organism by default for the reverse-lookup; `D1` closure forces `assay_ids`-only selection on the drill-downs; `D3` sentinel coercion (`""` / `-1.0` / `0` → `None`) on numeric timepoint fields; `D4` string→bool coercion at the API boundary on `flag_value` (Cypher comparison `r.flag_value = 'true'`); `D2` cross-organism default on the reverse-lookup.

**Tech Stack:** Python 3.13, Neo4j (Bolt driver via `GraphConnection`), Cypher with APOC (`apoc.coll.frequencies`, `apoc.coll.flatten`, `apoc.coll.toSet`, `apoc.coll.min/max/sort`), FastMCP, Pydantic v2, pytest, CyVer.

**Spec (frozen):** [docs/tool-specs/metabolites_by_assay.md](../../tool-specs/metabolites_by_assay.md) — slice spec.
**Parent (cross-cutting policy):** [docs/tool-specs/2026-05-05-phase5-greenfield-assay-tools.md](../../tool-specs/2026-05-05-phase5-greenfield-assay-tools.md) — KG verification §3, tested-absent invariant §10, conventions §11, verified Cypher §12.2/§12.3/§12.4, Phase 2 deliverables §13.
**Mirror plans:**
- [docs/superpowers/plans/2026-04-26-gene-derived-metrics.md](2026-04-26-gene-derived-metrics.md) — DM reverse-lookup (analog → `assays_by_metabolite`)
- [docs/superpowers/plans/2026-04-24-list-derived-metrics.md](2026-04-24-list-derived-metrics.md) — DM discovery (WHERE-helper + envelope patterns)
- existing builders in `multiomics_explorer/kg/queries_lib.py`: `build_genes_by_numeric_metric*` (numeric drill-down analog → tool 1), `build_genes_by_boolean_metric*` (boolean drill-down analog → tool 2), `build_gene_derived_metrics*` (polymorphic reverse-lookup analog → tool 3).

---

## CRITICAL SEQUENCING NOTE — READ FIRST

**Do NOT begin executing this plan until `list_metabolite_assays` (Tool 1) has merged to `main`.** Reasons (parent §13.8):

1. Slice integration tests reference Tool 1's tool surface (e.g. assertions like *"after this, drill via `metabolites_by_quantifies_assay`"*).
2. Merge-conflict surfaces resolve cleanly only when Tool 1 lands first:
   - `CLAUDE.md` MCP-tools-table — Tool 1 inserts a `list_metabolite_assays` row; this slice inserts 3 more in the same alphabetical region.
   - `tests/integration/test_cyver_queries.py` `_BUILDERS` list — Tool 1 adds 3 builders; this slice adds 9.
   - `tests/unit/test_tool_wrappers.py::EXPECTED_TOOLS` — Tool 1 raises sentinel count by 1; this slice by 3.
3. After Tool 1 merges, **open a fresh git worktree from the new `main` HEAD** before starting Task 1 (per parent §D7 closure). Use the `superpowers:using-git-worktrees` skill.

Plan-authoring (the work captured in this document) is the only step that's safe to do in parallel with Tool 1's build/merge. Once Tool 1 is on main, dispatch the test-updater (Task 1) from a fresh worktree.

---

## Mode B briefing — VERBATIM in every implementer agent's task

Per `add-or-update-tool` SKILL.md and slice-spec §8, every implementer agent (test-updater, query-builder, api-updater, tool-wrapper, doc-updater) MUST receive this briefing in their task prompt:

> **Mode B (3-tool slice):** Implement `metabolites_by_quantifies_assay` first as the template within your file, then extend the pattern to `metabolites_by_flags_assay` and `assays_by_metabolite`. The first tool establishes scoping conventions, sentinel coercions, rankable-gated logic, and `by_metric` envelope shape; tool 2 reuses ~80% of tool 1 (drops rankable gate, swaps numeric edge fields for `flag_value`); tool 3 introduces UNION ALL but reuses scoping from tools 1+2.

## Anti-scope-creep guardrail — VERBATIM in every implementer agent's task

Per parent §13.4 and `add-or-update-tool` SKILL.md §Stage 2:

> **ADD only — do NOT modify, rename, or rebaseline any existing test, case, or yml. If an unrelated test fails in your environment, REPORT AS A CONCERN; do not silently retune. Pinned baselines are KG-state guards.**

Reason: agents that observe pre-existing failures (stale base, KG drift, sibling-work conflicts) will "fix" them by editing baselines downward — silently masking real signals. The `list_metabolites` build hit this; the lesson is folded back into the skill.

---

## File Structure

| Action | File | Responsibility |
|---|---|---|
| Modify | `multiomics_explorer/kg/queries_lib.py` | Append after the existing `build_assays_by_metabolite_summary` placement (after `list_metabolite_assays`'s builders). New builders: 1 shared helper + 9 tool builders. |
| Modify | `multiomics_explorer/api/functions.py` | Add `metabolites_by_quantifies_assay()`, `metabolites_by_flags_assay()`, `assays_by_metabolite()` after the existing `list_metabolite_assays()` (Tool 1) — placement in the metabolomics block. |
| Modify | `multiomics_explorer/api/__init__.py` | Add 3 imports + 3 `__all__` entries (alphabetically with `list_metabolite_assays`). |
| Modify | `multiomics_explorer/__init__.py` | Same 3 imports + `__all__` entries (re-export). |
| Modify | `multiomics_explorer/mcp_server/tools.py` | Add ~20 typed Pydantic envelope sub-models (see §11 Conv E naming) + 3 sets of `<Tool>Result` + `<Tool>Response` models + 3 `@mcp.tool` async wrappers. |
| Create | `multiomics_explorer/inputs/tools/metabolites_by_quantifies_assay.yaml` | Author `examples`, `chaining`, `mistakes`, `verbose_fields`. |
| Create | `multiomics_explorer/inputs/tools/metabolites_by_flags_assay.yaml` | Same shape. |
| Create | `multiomics_explorer/inputs/tools/assays_by_metabolite.yaml` | Same shape. |
| Modify | `tests/unit/test_query_builders.py` | Add 9 builder test classes. |
| Modify | `tests/unit/test_api_functions.py` | Add 3 API function test classes. |
| Modify | `tests/unit/test_tool_wrappers.py` | Append 3 names to `EXPECTED_TOOLS` (line 49); add 3 wrapper test classes. |
| Modify | `tests/integration/test_mcp_tools.py` | Add 3 `@pytest.mark.kg` integration test classes pinned to §7 baselines from slice spec. |
| Modify | `tests/integration/test_api_contract.py` | Add 3 contract test classes. |
| Modify | `tests/integration/test_cyver_queries.py` | Append 9 entries to `_BUILDERS`; extend `_KNOWN_MAP_KEYS` with new map projection keys (per parent §13.2). |
| Modify | `tests/regression/test_regression.py` | Add ~6 entries to `TOOL_BUILDERS` (3 detail + 3 summary; diagnostics not regressed since it's gate-only metadata). |
| Modify | `tests/evals/test_eval.py` | Add ~3-6 entries to `TOOL_BUILDERS`. |
| Modify | `tests/evals/cases.yaml` | Add 6-9 representative cases (2-3 per tool). |
| Modify | `CLAUDE.md` | Add 3 rows to MCP Tools table (alphabetical: `assays_by_metabolite`, `metabolites_by_flags_assay`, `metabolites_by_quantifies_assay`). |
| Modify | `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolomics.md` | Top-level §"Tested-absent vs unmeasured" propagation per parent §10 — only if not already added by Tool 1's commit. Check first. |
| Generated | `multiomics_explorer/skills/multiomics-kg-guide/references/tools/metabolites_by_quantifies_assay.md`, `metabolites_by_flags_assay.md`, `assays_by_metabolite.md` | Output of `uv run python scripts/build_about_content.py`. NOT edited directly. |

---

## Implementer order (Mode B — within each agent's file)

Per slice spec §9 and `add-or-update-tool` SKILL.md Mode B:

1. **`metabolites_by_quantifies_assay` first** — most edge-filter logic (rankable-gated diagnostics, `by_metric` envelope with precomputed-vs-filtered, sentinel coercions on `time_point*` triple, `growth_phase` JOIN guard). Establishes the template patterns.
2. **`metabolites_by_flags_assay` second** — same scoping block (copy-paste consistent), simpler edge filter (single `flag_value`), no rankable gate. Reuses ~80% of tool 1's patterns.
3. **`assays_by_metabolite` third** — polymorphic UNION ALL is the new shape (parent §12.4 caveat: `[r:A|B]` polymorphic match warns under CyVer when CASE expressions read cross-arm props; production builder MUST use UNION ALL with distinct rel-vars `rq` / `rf`). Reuses scoping from 1+2 but introduces per-arm rollup pattern (`by_detection_status` numeric-only + `by_flag_value` boolean-only).

---

## Task 1: RED — write all failing tests across 3 files (single test-updater agent)

**Owner:** `test-updater` agent.
**Files:**
- Modify: `tests/unit/test_query_builders.py`
- Modify: `tests/unit/test_api_functions.py`
- Modify: `tests/unit/test_tool_wrappers.py`

This is a single coordinated commit that turns the entire slice red, so subsequent GREEN agents can verify their work against pinned tests rather than chase a moving target.

- [ ] **Step 1: Append `EXPECTED_TOOLS` entries**

In `tests/unit/test_tool_wrappers.py:49` — extend the `EXPECTED_TOOLS` list with the 3 new tool names (the list is unsorted today; place them at the end of the metabolomics block, after `metabolites_by_gene` at line 73):

```python
EXPECTED_TOOLS = [
    # ... existing entries ...
    "list_metabolites",
    "genes_by_metabolite",
    "metabolites_by_gene",
    "list_metabolite_assays",                # added by Tool 1 (already on main)
    "metabolites_by_quantifies_assay",       # NEW
    "metabolites_by_flags_assay",            # NEW
    "assays_by_metabolite",                  # NEW
]
```

- [ ] **Step 2: Add query-builder tests for all 9 builders**

In `tests/unit/test_query_builders.py`, append 9 test classes (placement: after the `list_metabolite_assays` builders test, near the existing DM-family tests). Each test class follows the pattern of `TestBuildGenesByNumericMetric*` / `TestBuildGenesByBooleanMetric*` / `TestBuildGeneDerivedMetrics*`. Tests must be kw-only-arg shaped, assert exact substring presence in Cypher, and pin the params dict.

Required test classes (full code below, copy verbatim — no placeholders):

**TestMetabolitesByQuantifiesAssayWhere** — for the shared `_metabolites_by_quantifies_assay_where()` helper:

```python
class TestMetabolitesByQuantifiesAssayWhere:
    """Unit tests for the shared WHERE-clause helper for metabolites_by_quantifies_assay."""

    def test_no_filters_returns_only_required(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where()
        assert conditions == []
        assert params == {}

    def test_organism_contains_lowercased(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(organism="MIT9313")
        assert any("toLower(a.organism_name) CONTAINS" in c for c in conditions)
        assert params == {"organism": "mit9313"}

    def test_metabolite_ids_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            metabolite_ids=["kegg.compound:C00074"])
        assert "m.id IN $metabolite_ids" in conditions
        assert params["metabolite_ids"] == ["kegg.compound:C00074"]

    def test_exclude_metabolite_ids_set_difference(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            exclude_metabolite_ids=["kegg.compound:C00002"])
        assert "NOT m.id IN $exclude_metabolite_ids" in conditions
        assert params["exclude_metabolite_ids"] == ["kegg.compound:C00002"]

    def test_value_min_strips_tested_absent_warning(self):
        # Sanity: builder must accept value_min and emit raw threshold.
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(value_min=0.01)
        assert "r.value >= $value_min" in conditions
        assert params["value_min"] == 0.01

    def test_value_max(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(value_max=10.0)
        assert "r.value <= $value_max" in conditions

    def test_detection_status_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            detection_status=["detected", "sporadic"])
        assert "r.detection_status IN $detection_status" in conditions
        assert params["detection_status"] == ["detected", "sporadic"]

    def test_metric_bucket_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            metric_bucket=["top_decile", "top_quartile"])
        assert "r.metric_bucket IN $metric_bucket" in conditions

    def test_metric_percentile_min_max(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            metric_percentile_min=10.0, metric_percentile_max=90.0)
        assert "r.metric_percentile >= $metric_percentile_min" in conditions
        assert "r.metric_percentile <= $metric_percentile_max" in conditions

    def test_rank_by_metric_max(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(rank_by_metric_max=10)
        assert "r.rank_by_metric <= $rank_by_metric_max" in conditions
        assert params["rank_by_metric_max"] == 10

    def test_timepoint_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(timepoint=["4 days", "6 days"])
        assert "r.time_point IN $timepoint" in conditions
        assert params["timepoint"] == ["4 days", "6 days"]

    def test_compartment_exact(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(compartment="whole_cell")
        assert "a.compartment = $compartment" in conditions

    def test_treatment_type_lowercased_overlap(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(treatment_type=["Light", "Dark"])
        assert any("ANY(t IN coalesce(a.treatment_type, [])" in c for c in conditions)
        assert any("toLower(t) IN $treatment_types_lower" in c for c in conditions)
        assert params["treatment_types_lower"] == ["light", "dark"]

    def test_publication_doi_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(
            publication_doi=["10.1073/pnas.2213271120"])
        assert "a.publication_doi IN $publication_doi" in conditions

    def test_experiment_ids_in_list(self):
        from multiomics_explorer.kg.queries_lib import _metabolites_by_quantifies_assay_where
        conditions, params = _metabolites_by_quantifies_assay_where(experiment_ids=["EXP_1"])
        assert "a.experiment_id IN $experiment_ids" in conditions
```

**TestBuildMetabolitesByQuantifiesAssayDiagnostics** — diagnostics builder per parent §13.1:

```python
class TestBuildMetabolitesByQuantifiesAssayDiagnostics:
    def test_returns_rankable_per_assay(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_diagnostics
        cypher, params = build_metabolites_by_quantifies_assay_diagnostics(
            assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"])
        assert "MATCH (a:MetaboliteAssay)" in cypher
        assert "a.id IN $assay_ids" in cypher
        assert "a.value_kind = 'numeric'" in cypher
        assert "(a.rankable = 'true') AS rankable" in cypher       # D4 string→bool
        assert "a.value_min" in cypher and "a.value_max" in cypher  # so api/ can echo full-DM range
        assert params["assay_ids"] == [
            "metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"]

    def test_organism_filter_passes_through(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_diagnostics
        cypher, params = build_metabolites_by_quantifies_assay_diagnostics(
            assay_ids=["a1"], organism="MIT9313")
        assert "toLower(a.organism_name) CONTAINS" in cypher
        assert "mit9313" in str(params).lower()
```

**TestBuildMetabolitesByQuantifiesAssaySummary** — pin the §12.2 summary skeleton:

```python
class TestBuildMetabolitesByQuantifiesAssaySummary:
    def test_match_pattern(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifiesAssay_summary  # NB: snake_case import below
        # Use the canonical name:
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_summary
        cypher, params = build_metabolites_by_quantifies_assay_summary(
            assay_ids=["a1"])
        assert "MATCH (a:MetaboliteAssay)-[r:Assay_quantifies_metabolite]->(m:Metabolite)" in cypher
        assert "a.id IN $assay_ids" in cypher

    def test_envelope_keys(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_summary
        cypher, _ = build_metabolites_by_quantifies_assay_summary(assay_ids=["a1"])
        for key in ("by_detection_status", "by_metric_bucket", "by_assay",
                    "by_compartment", "by_organism",
                    "filtered_value_min", "filtered_value_max", "total_matching"):
            assert key in cypher

    def test_detection_status_filter_passthrough(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_summary
        cypher, params = build_metabolites_by_quantifies_assay_summary(
            assay_ids=["a1"], detection_status=["detected", "sporadic"])
        assert "r.detection_status IN $detection_status" in cypher
        assert params["detection_status"] == ["detected", "sporadic"]

    def test_value_min_passthrough(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay_summary
        cypher, params = build_metabolites_by_quantifies_assay_summary(
            assay_ids=["a1"], value_min=0.01)
        assert "r.value >= $value_min" in cypher
```

**TestBuildMetabolitesByQuantifiesAssay** — pin the §12.2 detail skeleton including sentinel coercions:

```python
class TestBuildMetabolitesByQuantifiesAssay:
    def test_match_and_optional_experiment_join(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"])
        assert "MATCH (a:MetaboliteAssay)-[r:Assay_quantifies_metabolite]->(m:Metabolite)" in cypher
        assert "OPTIONAL MATCH (a)<-[:ExperimentHasMetaboliteAssay]-(e:Experiment)" in cypher

    def test_sentinel_coercions(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"])
        # D3: empty-string / -1.0 / 0 → null
        assert "CASE WHEN r.time_point = '' THEN null ELSE r.time_point END AS timepoint" in cypher
        assert "CASE WHEN r.time_point_hours = -1.0 THEN null ELSE r.time_point_hours END" in cypher
        assert "CASE WHEN r.time_point_order = 0 THEN null ELSE r.time_point_order END" in cypher

    def test_growth_phase_lookup_guarded(self):
        # KG-MET-017: time_point_growth_phases[] is empty today; lookup must coalesce safely.
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"])
        assert "size(coalesce(e.time_point_growth_phases, []))" in cypher
        assert "AS growth_phase" in cypher

    def test_order_by_rank(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"])
        assert "ORDER BY r.rank_by_metric ASC" in cypher
        assert "m.id ASC" in cypher

    def test_verbose_adds_heavy_text(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher_default, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"])
        cypher_verbose, _ = build_metabolites_by_quantifies_assay(assay_ids=["a1"], verbose=True)
        for f in ("a.name AS assay_name", "a.field_description AS field_description",
                  "a.experimental_context", "a.light_condition", "r.replicate_values"):
            assert f not in cypher_default
            assert f in cypher_verbose

    def test_limit_offset(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_quantifies_assay
        cypher, params = build_metabolites_by_quantifies_assay(assay_ids=["a1"], limit=20, offset=5)
        assert "SKIP $offset LIMIT $limit" in cypher
        assert params["limit"] == 20 and params["offset"] == 5
```

**TestBuildMetabolitesByFlagsAssaySummary** — pin §12.3 summary:

```python
class TestBuildMetabolitesByFlagsAssaySummary:
    def test_match_and_envelope(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay_summary
        cypher, params = build_metabolites_by_flags_assay_summary(assay_ids=["a1"])
        assert "MATCH (a:MetaboliteAssay)-[r:Assay_flags_metabolite]->(m:Metabolite)" in cypher
        assert "a.id IN $assay_ids" in cypher
        for key in ("by_value", "by_assay", "by_compartment", "by_organism", "total_matching"):
            assert key in cypher

    def test_no_detection_status_envelope(self):
        # Boolean arm has no detection_status; document via test.
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay_summary
        cypher, _ = build_metabolites_by_flags_assay_summary(assay_ids=["a1"])
        assert "by_detection_status" not in cypher

    def test_flag_value_filter_string_form(self):
        # D4: API coerces bool → string before passing to Cypher.
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay_summary
        cypher, params = build_metabolites_by_flags_assay_summary(assay_ids=["a1"], flag_value="true")
        assert "r.flag_value = $flag_value" in cypher
        assert params["flag_value"] == "true"
```

**TestBuildMetabolitesByFlagsAssay** — pin §12.3 detail:

```python
class TestBuildMetabolitesByFlagsAssay:
    def test_string_to_bool_coercion_in_return(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay
        cypher, _ = build_metabolites_by_flags_assay(assay_ids=["a1"])
        assert "(r.flag_value = 'true') AS flag_value" in cypher

    def test_order_by_flag_desc(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay
        cypher, _ = build_metabolites_by_flags_assay(assay_ids=["a1"])
        assert "ORDER BY r.flag_value DESC" in cypher
        assert "m.id ASC" in cypher

    def test_verbose_adds_minimal(self):
        from multiomics_explorer.kg.queries_lib import build_metabolites_by_flags_assay
        cypher_def, _ = build_metabolites_by_flags_assay(assay_ids=["a1"])
        cypher_v, _ = build_metabolites_by_flags_assay(assay_ids=["a1"], verbose=True)
        for f in ("a.name AS assay_name", "a.field_description AS field_description"):
            assert f not in cypher_def
            assert f in cypher_v
```

**TestBuildAssaysByMetaboliteSummary** — pin the UNION ALL skeleton from §12.4:

```python
class TestBuildAssaysByMetaboliteSummary:
    def test_union_all_with_distinct_rel_vars(self):
        # Parent §12.4 caveat: production builder MUST use UNION ALL with rq/rf rel-vars.
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite_summary
        cypher, _ = build_assays_by_metabolite_summary(metabolite_ids=["kegg.compound:C00074"])
        assert "UNION ALL" in cypher
        assert "[rq:Assay_quantifies_metabolite]" in cypher
        assert "[rf:Assay_flags_metabolite]" in cypher
        # Anti-pattern guard: the polymorphic merged form must NOT appear.
        assert "[r:Assay_quantifies_metabolite|Assay_flags_metabolite]" not in cypher

    def test_envelope_keys(self):
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite_summary
        cypher, _ = build_assays_by_metabolite_summary(metabolite_ids=["kegg.compound:C00074"])
        for key in ("by_evidence_kind", "by_organism", "by_compartment", "by_assay",
                    "by_detection_status", "by_flag_value", "metabolites_matched",
                    "total_matching"):
            assert key in cypher

    def test_null_filter_on_collected_arrays(self):
        # Parent §13.7: collect() drops NULLs; explicit guard for cross-arm boundary.
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite_summary
        cypher, _ = build_assays_by_metabolite_summary(metabolite_ids=["kegg.compound:C00074"])
        assert "[d IN collect(det) WHERE d IS NOT NULL]" in cypher
        assert "[f IN collect(flag) WHERE f IS NOT NULL]" in cypher

    def test_evidence_kind_quantifies_only(self):
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite_summary
        cypher, _ = build_assays_by_metabolite_summary(
            metabolite_ids=["kegg.compound:C00074"], evidence_kind="quantifies")
        # When quantifies-only, the flags branch MUST NOT contribute rows.
        # Implementation detail: builder either (a) emits only the quantifies branch, or
        # (b) emits both branches with a guard that empties the flags branch. Either is OK
        # so long as result-row evidence_kind is constant.
        assert "rq:Assay_quantifies_metabolite" in cypher
```

**TestBuildAssaysByMetabolite** — pin the §12.4 detail UNION ALL skeleton + polymorphic null padding:

```python
class TestBuildAssaysByMetabolite:
    def test_union_all_skeleton(self):
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite
        cypher, _ = build_assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"])
        assert "UNION ALL" in cypher
        assert "[rq:Assay_quantifies_metabolite]" in cypher
        assert "[rf:Assay_flags_metabolite]" in cypher
        # Both branches MUST emit the same column list (UNION ALL constraint).
        # Cross-arm fields padded with explicit nulls per §6.2.
        assert "null AS flag_value" in cypher        # from quantifies branch
        assert "null AS value" in cypher              # from flags branch
        assert "null AS metric_bucket" in cypher      # from flags branch (rankable-only)
        assert "null AS detection_status" in cypher   # from flags branch
        assert "null AS timepoint" in cypher          # from flags branch
        assert "'quantifies' AS evidence_kind" in cypher
        assert "'flags' AS evidence_kind" in cypher

    def test_optional_match_experiment_only_in_quantifies_branch(self):
        # Quantifies branch needs e.time_point_growth_phases for growth_phase lookup.
        # Flags branch has no temporal fields; experiment join is unnecessary.
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite
        cypher, _ = build_assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"])
        assert "OPTIONAL MATCH (a)<-[:ExperimentHasMetaboliteAssay]-(e:Experiment)" in cypher

    def test_order_by(self):
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite
        cypher, _ = build_assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"])
        assert "ORDER BY metabolite_id ASC, evidence_kind DESC" in cypher
        assert "coalesce(timepoint_order, 999999) ASC" in cypher

    def test_organism_filter(self):
        from multiomics_explorer.kg.queries_lib import build_assays_by_metabolite
        cypher, params = build_assays_by_metabolite(
            metabolite_ids=["kegg.compound:C00074"], organism="MIT9313")
        assert params.get("organism") == "mit9313"
```

- [ ] **Step 3: Add API function tests for all 3 tools**

In `tests/unit/test_api_functions.py`, append 3 test classes. These are unit tests with a stubbed connection (no live KG); they exercise input validation, ValueError paths, summary/detail dispatch, and `not_found` partitioning.

```python
class TestMetabolitesByQuantifiesAssay:
    def test_empty_assay_ids_raises(self):
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        with pytest.raises(ValueError, match="assay_ids"):
            metabolites_by_quantifies_assay(assay_ids=[], conn=DummyConnection())

    def test_invalid_metric_bucket_raises(self):
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        with pytest.raises(ValueError, match="metric_bucket"):
            metabolites_by_quantifies_assay(
                assay_ids=["a1"], metric_bucket=["INVALID"], conn=DummyConnection())

    def test_invalid_detection_status_raises(self):
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        with pytest.raises(ValueError, match="detection_status"):
            metabolites_by_quantifies_assay(
                assay_ids=["a1"], detection_status=["INVALID"], conn=DummyConnection())

    def test_all_non_rankable_raises_when_rankable_filter_set(self):
        # All-non-rankable input + rankable-gated filter (metric_bucket/percentile/rank) → ValueError.
        # Stub diagnostics to return all rankable=False rows.
        ...  # full stub omitted for brevity, but test must:
        #     1. Stub diagnostics query result: [{"derived_metric_id": "a1", "rankable": False, ...}]
        #     2. Call metabolites_by_quantifies_assay(assay_ids=["a1"], metric_bucket=["top_decile"], conn=stub)
        #     3. Assert ValueError raised with "rankable" in message

    def test_mixed_rankable_soft_excludes(self):
        # Mixed input: some rankable, some not. Expect non-rankable excluded from filter,
        # surfaced in envelope.excluded_assays + warnings.
        ...

    def test_summary_skips_detail_query(self):
        # summary=True means only the summary builder runs; detail query never executes.
        ...
```

```python
class TestMetabolitesByFlagsAssay:
    def test_empty_assay_ids_raises(self):
        from multiomics_explorer.api.functions import metabolites_by_flags_assay
        with pytest.raises(ValueError, match="assay_ids"):
            metabolites_by_flags_assay(assay_ids=[], conn=DummyConnection())

    def test_flag_value_bool_to_string_coercion(self):
        # D4: bool flag_value → string 'true'/'false' for Cypher param.
        # Stub conn.execute_query and capture params.
        captured = {}
        class StubConn:
            def execute_query(self, cypher, **params):
                captured.update(params)
                return []
        from multiomics_explorer.api.functions import metabolites_by_flags_assay
        metabolites_by_flags_assay(assay_ids=["a1"], flag_value=True, conn=StubConn())
        assert captured.get("flag_value") == "true"

    def test_no_rankable_diagnostics(self):
        # Boolean tool has no rankable gate; diagnostics builder must not be called.
        ...
```

```python
class TestAssaysByMetabolite:
    def test_empty_metabolite_ids_raises(self):
        from multiomics_explorer.api.functions import assays_by_metabolite
        with pytest.raises(ValueError, match="metabolite_ids"):
            assays_by_metabolite(metabolite_ids=[], conn=DummyConnection())

    def test_invalid_evidence_kind_raises(self):
        from multiomics_explorer.api.functions import assays_by_metabolite
        with pytest.raises(ValueError, match="evidence_kind"):
            assays_by_metabolite(
                metabolite_ids=["m1"], evidence_kind="INVALID", conn=DummyConnection())

    def test_not_found_flat_list(self):
        # Single-batch input → flat list[str] (parent §13.6).
        # Stub stub_connection so probe returns empty; envelope.not_found = [missing_id].
        ...

    def test_metabolites_with_evidence_partition(self):
        # Stubbed: 2 metabolites, 1 has rows, 1 has none.
        # Expect: metabolites_with_evidence=[id_with_row], metabolites_without_evidence=[id_without].
        ...
```

- [ ] **Step 4: Add MCP wrapper tests**

In `tests/unit/test_tool_wrappers.py`, append 3 test classes near the existing `genes_by_metabolite` / `metabolites_by_gene` wrapper tests. Each asserts:

1. The tool registers with the expected name.
2. The wrapper accepts the documented signature.
3. ToolError (not bare string) is raised on bad input.
4. The wrapper calls `await ctx.info(...)` at top.
5. The Pydantic Response model validates a representative dict from the api/ layer.

Skeleton (full code body in task — no placeholders):

```python
class TestMetabolitesByQuantifiesAssayWrapper:
    def test_registered(self, tool_fns):
        assert "metabolites_by_quantifies_assay" in tool_fns

    @pytest.mark.asyncio
    async def test_empty_assay_ids_raises_tool_error(self, tool_fns, mock_ctx):
        from fastmcp.exceptions import ToolError
        with pytest.raises(ToolError, match="assay_ids"):
            await tool_fns["metabolites_by_quantifies_assay"](mock_ctx, assay_ids=[])

    def test_response_model_validates_typical_envelope(self):
        from multiomics_explorer.mcp_server.tools import MetabolitesByQuantifiesAssayResponse
        # Build a representative envelope dict; assert Response model accepts it.
        ...

class TestMetabolitesByFlagsAssayWrapper:
    def test_registered(self, tool_fns):
        assert "metabolites_by_flags_assay" in tool_fns
    ...

class TestAssaysByMetaboliteWrapper:
    def test_registered(self, tool_fns):
        assert "assays_by_metabolite" in tool_fns
    ...
```

- [ ] **Step 5: Run all unit tests; confirm RED**

Run:

```bash
uv run pytest tests/unit/test_query_builders.py tests/unit/test_api_functions.py tests/unit/test_tool_wrappers.py -v 2>&1 | tail -80
```

Expected: NEW tests fail with `ImportError` / `AttributeError` (builders / functions / wrappers don't exist yet). ALL pre-existing tests still PASS — no rebaselining (parent §13.4 anti-scope-creep). Sentinel:

- `test_all_tools_registered` should fail with the message showing the 3 missing names.
- All `TestMetabolitesByQuantifiesAssay*`, `TestMetabolitesByFlagsAssay*`, `TestAssaysByMetabolite*` tests fail at import.

If any pre-existing test goes red here, **STOP** and report as a concern — do not edit it. Likely cause: stale main, sibling-work conflict, or KG drift.

- [ ] **Step 6: Commit RED**

```bash
git add tests/unit/test_query_builders.py tests/unit/test_api_functions.py tests/unit/test_tool_wrappers.py
git commit -m "test(slice): add red unit tests for metabolites-by-assay 3-tool slice"
```

---

## Task 2: GREEN — query builder layer (single query-builder agent, file-owned)

**Owner:** `query-builder` agent. **Mode B briefing + anti-scope-creep guardrail mandatory in task prompt.**
**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (append after `list_metabolite_assays` builders)
- Modify: `tests/integration/test_cyver_queries.py` (`_BUILDERS` list + `_KNOWN_MAP_KEYS` set)

Per parent §13.1, the agent owns these in queries_lib.py:

| Builder | Source query | Mirror precedent |
|---|---|---|
| `_metabolites_by_quantifies_assay_where()` | (helper, not Cypher) | `_list_derived_metrics_where()`, `_genes_by_metabolite_where()` |
| `build_metabolites_by_quantifies_assay_diagnostics()` | rankable-gating probe | `build_genes_by_numeric_metric_diagnostics()` |
| `build_metabolites_by_quantifies_assay_summary()` | parent §12.2 summary | `build_genes_by_numeric_metric_summary()` |
| `build_metabolites_by_quantifies_assay()` | parent §12.2 detail | `build_genes_by_numeric_metric()` |
| `_metabolites_by_flags_assay_where()` | (helper, may share with quantifies — agent decides) | `_genes_by_boolean_metric_where()` |
| `build_metabolites_by_flags_assay_summary()` | parent §12.3 summary | `build_genes_by_boolean_metric_summary()` |
| `build_metabolites_by_flags_assay()` | parent §12.3 detail | `build_genes_by_boolean_metric()` |
| `_assays_by_metabolite_where()` | (helper for UNION ALL branch scoping) | (no direct mirror — uses two-branch shape) |
| `build_assays_by_metabolite_summary()` | parent §12.4 summary, UNION ALL | `build_gene_derived_metrics_summary()` |
| `build_assays_by_metabolite()` | parent §12.4 detail, UNION ALL | `build_gene_derived_metrics()` |

Note: `metabolites_by_flags_assay` does not need a `_diagnostics` builder — boolean DM precedent shows the `flag_value` filter has no gate to probe.

**WHERE-helper consolidation decision:** prefer ONE shared helper if scoping is identical across the 3 tools. Inspection of the slice spec §4.1 / §5.1 / §6.1 shows the three tools share most scoping (`organism`, `metabolite_ids`, `exclude_metabolite_ids`, `experiment_ids`, `publication_doi`, `compartment`, `treatment_type`, `background_factors`, `growth_phases`); they differ on edge-level filters (numeric: `value_min/max`, `detection_status`, `metric_bucket`, `metric_percentile_min/max`, `rank_by_metric_max`, `timepoint`; flags: `flag_value`; reverse-lookup: `evidence_kind`, `metric_types`). Recommendation: **two helpers** — `_assay_node_scope_where()` for the assay-node-level filters shared by all three, plus per-tool helpers that layer on edge-level filters. Agent makes the final call; the test class names above assume per-tool helpers exist (rename if consolidated).

- [ ] **Step 1: Implement `_metabolites_by_quantifies_assay_where()` + `build_metabolites_by_quantifies_assay_diagnostics()`**

Source: parent §12.2 + §3 Distribution headlines. Cypher template (full skeleton — fill from parent §12.2 / §3):

```python
def _metabolites_by_quantifies_assay_where(
    *,
    organism: str | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    value_min: float | None = None,
    value_max: float | None = None,
    detection_status: list[str] | None = None,
    timepoint: list[str] | None = None,
    metric_bucket: list[str] | None = None,
    metric_percentile_min: float | None = None,
    metric_percentile_max: float | None = None,
    rank_by_metric_max: int | None = None,
) -> tuple[list[str], dict]:
    """WHERE-conditions builder for metabolites_by_quantifies_assay.
    See parent §12.2 + §11 Conv A (set-difference exclude_metabolite_ids)."""
    conditions: list[str] = []
    params: dict = {}
    if organism is not None:
        conditions.append("toLower(a.organism_name) CONTAINS $organism")
        params["organism"] = organism.lower()
    if metabolite_ids is not None:
        conditions.append("m.id IN $metabolite_ids")
        params["metabolite_ids"] = metabolite_ids
    if exclude_metabolite_ids is not None:
        conditions.append("NOT m.id IN $exclude_metabolite_ids")
        params["exclude_metabolite_ids"] = exclude_metabolite_ids
    # ... continue for all params per slice spec §4.1.1
    return conditions, params
```

```python
def build_metabolites_by_quantifies_assay_diagnostics(
    *,
    assay_ids: list[str],
    organism: str | None = None,
    # ... full param list per parent §12.2 / slice spec §4.1.1
) -> tuple[str, dict]:
    """Pre-flight probe: per-assay rankable + value distribution echo.

    Mirrors build_genes_by_numeric_metric_diagnostics. Returns one row per
    selected assay with: assay_id, rankable (bool, D4-coerced), value_min,
    value_q1, value_median, value_q3, value_max (full-assay context for
    `by_metric` envelope enrichment in api/).

    api/ uses this BEFORE summary/detail to:
      1. Validate every selected assay has value_kind='numeric' (raise on mismatch).
      2. Compute `excluded_assays` for rankable-gated filters that don't apply.
      3. Echo full-assay value range into envelope `by_metric`.

    RETURN keys: assay_id, name, value_kind, rankable, organism_name,
                 compartment, value_min, value_q1, value_median, value_q3, value_max.
    """
    params: dict = {"assay_ids": assay_ids}
    cypher = (
        "MATCH (a:MetaboliteAssay)\n"
        "WHERE a.id IN $assay_ids AND a.value_kind = 'numeric'\n"
        "RETURN a.id AS assay_id, a.name AS name, a.value_kind AS value_kind,\n"
        "       (a.rankable = 'true') AS rankable,\n"
        "       a.organism_name AS organism_name, a.compartment AS compartment,\n"
        "       a.value_min AS value_min, a.value_q1 AS value_q1,\n"
        "       a.value_median AS value_median, a.value_q3 AS value_q3,\n"
        "       a.value_max AS value_max\n"
        "ORDER BY a.id ASC"
    )
    return cypher, params
```

Run: `uv run pytest tests/unit/test_query_builders.py::TestMetabolitesByQuantifiesAssayWhere tests/unit/test_query_builders.py::TestBuildMetabolitesByQuantifiesAssayDiagnostics -v`. Expected: GREEN.

- [ ] **Step 2: Implement `build_metabolites_by_quantifies_assay_summary()` + `build_metabolites_by_quantifies_assay()` (detail)**

Source: parent §12.2 verbatim Cypher, parameterized via the helper. Per parent §13.7, use `[s IN collect(field) WHERE s IS NOT NULL]` for all NULL-bearing arrays.

Run: `uv run pytest tests/unit/test_query_builders.py::TestBuildMetabolitesByQuantifiesAssaySummary tests/unit/test_query_builders.py::TestBuildMetabolitesByQuantifiesAssay -v`. Expected: GREEN.

- [ ] **Step 3: Implement `build_metabolites_by_flags_assay_summary()` + `build_metabolites_by_flags_assay()` (detail)**

Source: parent §12.3 verbatim. Reuse `_metabolites_by_quantifies_assay_where()` for shared scoping if helper is consolidated; otherwise create `_metabolites_by_flags_assay_where()` with the same scoping params + the `flag_value` filter (string-form, per D4).

Run: `uv run pytest tests/unit/test_query_builders.py::TestBuildMetabolitesByFlagsAssaySummary tests/unit/test_query_builders.py::TestBuildMetabolitesByFlagsAssay -v`. Expected: GREEN.

- [ ] **Step 4: Implement `build_assays_by_metabolite_summary()` + `build_assays_by_metabolite()` (UNION ALL)**

Source: parent §12.4 verbatim. **CyVer caveat (production-critical):** use `UNION ALL` with **distinct rel-vars** (`rq` for quantifies branch, `rf` for flags branch). The merged `[r:Assay_quantifies_metabolite|Assay_flags_metabolite]` form parses but trips a CyVer schema warning when CASE expressions read cross-arm props. Verified clean shape from parent §12.4:

```cypher
CALL {
  MATCH (a:MetaboliteAssay)-[rq:Assay_quantifies_metabolite]->(m:Metabolite)
  WHERE m.id IN $metabolite_ids
    AND <_assays_by_metabolite_where conditions>
  OPTIONAL MATCH (a)<-[:ExperimentHasMetaboliteAssay]-(e:Experiment)
  RETURN
    m.id AS metabolite_id, m.name AS metabolite_name,
    a.id AS assay_id, a.name AS assay_name,
    'quantifies' AS evidence_kind,
    rq.value AS value, rq.value_sd AS value_sd,
    null AS flag_value, null AS n_positive,
    rq.n_replicates AS n_replicates, rq.metric_type AS metric_type,
    rq.metric_bucket AS metric_bucket, rq.metric_percentile AS metric_percentile,
    rq.detection_status AS detection_status,
    CASE WHEN rq.time_point = '' THEN null ELSE rq.time_point END AS timepoint,
    CASE WHEN rq.time_point_hours = -1.0 THEN null ELSE rq.time_point_hours END AS timepoint_hours,
    CASE WHEN rq.time_point_order = 0 THEN null ELSE rq.time_point_order END AS timepoint_order,
    CASE WHEN rq.time_point_order > 0
              AND size(coalesce(e.time_point_growth_phases, [])) >= rq.time_point_order
         THEN e.time_point_growth_phases[rq.time_point_order - 1]
         ELSE null END AS growth_phase,
    rq.condition_label AS condition_label,
    a.organism_name AS organism_name, a.compartment AS compartment,
    a.experiment_id AS experiment_id, a.publication_doi AS publication_doi
  UNION ALL
  MATCH (a:MetaboliteAssay)-[rf:Assay_flags_metabolite]->(m:Metabolite)
  WHERE m.id IN $metabolite_ids
    AND <_assays_by_metabolite_where conditions for flags branch>
  RETURN
    m.id AS metabolite_id, m.name AS metabolite_name,
    a.id AS assay_id, a.name AS assay_name,
    'flags' AS evidence_kind,
    null AS value, null AS value_sd,
    (rf.flag_value = 'true') AS flag_value,
    rf.n_positive AS n_positive,
    rf.n_replicates AS n_replicates, rf.metric_type AS metric_type,
    null AS metric_bucket, null AS metric_percentile, null AS detection_status,
    null AS timepoint, null AS timepoint_hours, null AS timepoint_order,
    null AS growth_phase,
    rf.condition_label AS condition_label,
    a.organism_name AS organism_name, a.compartment AS compartment,
    a.experiment_id AS experiment_id, a.publication_doi AS publication_doi
}
ORDER BY metabolite_id ASC, evidence_kind DESC, assay_id ASC,
         coalesce(timepoint_order, 999999) ASC
SKIP $offset LIMIT $limit
```

When `evidence_kind='quantifies'` is set, omit the flags branch (and vice versa) so the result row's `evidence_kind` column is constant. When `evidence_kind` is None, both branches contribute.

Per parent §13.7, summary builder must use `[d IN collect(det) WHERE d IS NOT NULL]` and `[f IN collect(flag) WHERE f IS NOT NULL]` for the cross-arm fields.

Run: `uv run pytest tests/unit/test_query_builders.py::TestBuildAssaysByMetaboliteSummary tests/unit/test_query_builders.py::TestBuildAssaysByMetabolite -v`. Expected: GREEN.

- [ ] **Step 5: Update CyVer registry**

In `tests/integration/test_cyver_queries.py`:

(a) Append to `_BUILDERS` (around line 206):

```python
# --- metabolomics drill-downs (Phase 5 slice) ---
("metabolites_by_quantifies_assay_diag", build_metabolites_by_quantifies_assay_diagnostics,
    {"assay_ids": ["a1"]}),
("metabolites_by_quantifies_assay_summary", build_metabolites_by_quantifies_assay_summary,
    {"assay_ids": ["a1"]}),
("metabolites_by_quantifies_assay", build_metabolites_by_quantifies_assay,
    {"assay_ids": ["a1"]}),
("metabolites_by_quantifies_assay_verbose", build_metabolites_by_quantifies_assay,
    {"assay_ids": ["a1"], "verbose": True}),
("metabolites_by_flags_assay_summary", build_metabolites_by_flags_assay_summary,
    {"assay_ids": ["a1"]}),
("metabolites_by_flags_assay", build_metabolites_by_flags_assay,
    {"assay_ids": ["a1"]}),
("metabolites_by_flags_assay_verbose", build_metabolites_by_flags_assay,
    {"assay_ids": ["a1"], "verbose": True}),
("assays_by_metabolite_summary", build_assays_by_metabolite_summary,
    {"metabolite_ids": ["kegg.compound:C00074"]}),
("assays_by_metabolite", build_assays_by_metabolite,
    {"metabolite_ids": ["kegg.compound:C00074"]}),
("assays_by_metabolite_verbose", build_assays_by_metabolite,
    {"metabolite_ids": ["kegg.compound:C00074"], "verbose": True}),
```

(b) Extend `_KNOWN_MAP_KEYS` (line 128) with new map projection keys this slice introduces (audit each builder; only add genuinely new keys):

```python
_KNOWN_MAP_KEYS = {
    # ... existing ...
    # Phase 5 metabolites-by-assay slice (audit per parent §13.2):
    "evidence_kind",     # UNION ALL discriminator
    "det", "flag",       # UNION ALL summary aliases (parent §12.4)
    "metabolite_id",     # if not already present from list_metabolite_assays
    "metabolite_name",   # union-shape projection
    "assay_id", "assay_name",
}
```

Add only the keys that are newly introduced — verify against the existing set first.

Run: `uv run pytest tests/integration/test_cyver_queries.py -v -m kg 2>&1 | tail -30`. Expected: ALL builders pass with score=1.0 (or filtered false-positive map-key warnings).

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/integration/test_cyver_queries.py
git commit -m "feat(kg): add metabolites-by-assay slice query builders (3 tools)"
```

---

## Task 3: GREEN — API layer (single api-updater agent)

**Owner:** `api-updater` agent. **Mode B briefing + anti-scope-creep guardrail mandatory.**
**Files:**
- Modify: `multiomics_explorer/api/functions.py` (append after `list_metabolite_assays()`)
- Modify: `multiomics_explorer/api/__init__.py`
- Modify: `multiomics_explorer/__init__.py`

Per parent §13.3, every new API function exports through both `api/__init__.py` and `multiomics_explorer/__init__.py`.

- [ ] **Step 1: Implement `metabolites_by_quantifies_assay()`**

Three-query dispatch per `genes_by_numeric_metric` precedent:

1. `_diagnostics` (probe rankable + per-assay range) → validates assay IDs + computes `excluded_assays` for rankable-gated filters.
2. `_summary` → envelope with `by_metric` enriched by per-assay precomputed range echo from #1.
3. `_detail` (only if `summary=False`) → top-N rows.

Validation:
- Empty `assay_ids` → ValueError.
- `metric_bucket` values must be subset of `{'top_decile','top_quartile','mid','low'}`.
- `detection_status` values must be subset of `{'detected','sporadic','not_detected'}`.
- `timepoint` is a free-form list[str] (no closed vocabulary today; live values are `'4 days'` / `'6 days'`).
- All-non-rankable + rankable-gated filter set → ValueError listing offending assay_ids.
- Mixed rankable input + rankable-gated filter → soft-exclude non-rankable, surface in `excluded_assays` + `warnings`.

Skeleton (full body required at implementation time):

```python
def metabolites_by_quantifies_assay(
    *,
    assay_ids: list[str],
    organism: str | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    value_min: float | None = None,
    value_max: float | None = None,
    detection_status: list[str] | None = None,
    timepoint: list[str] | None = None,
    metric_bucket: list[str] | None = None,
    metric_percentile_min: float | None = None,
    metric_percentile_max: float | None = None,
    rank_by_metric_max: int | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int = 5,
    offset: int = 0,
    conn: GraphConnection | None = None,
) -> dict:
    """Drill into numeric MetaboliteAssay edges. See spec §4."""
    conn = conn or _default_conn()
    if not assay_ids:
        raise ValueError("assay_ids must not be empty")
    if metric_bucket and set(metric_bucket) - {"top_decile","top_quartile","mid","low"}:
        raise ValueError(f"Invalid metric_bucket value(s): {set(metric_bucket) - ...}")
    if detection_status and set(detection_status) - {"detected","sporadic","not_detected"}:
        raise ValueError(...)

    # 1. Diagnostics probe
    diag_cypher, diag_params = build_metabolites_by_quantifies_assay_diagnostics(
        assay_ids=assay_ids, organism=organism, ...)
    diag_rows = conn.execute_query(diag_cypher, **diag_params)

    # Resolve not_found.assay_ids = input - returned
    found_ids = {r["assay_id"] for r in diag_rows}
    not_found_assay_ids = sorted(set(assay_ids) - found_ids)
    surviving_ids = sorted(found_ids)

    # Compute excluded_assays for rankable-gated filters
    rankable_filter_set = any([metric_bucket, metric_percentile_min, metric_percentile_max,
                               rank_by_metric_max])
    excluded_assays: list[str] = []
    warnings: list[str] = []
    if rankable_filter_set:
        rankable_ids = {r["assay_id"] for r in diag_rows if r["rankable"]}
        if not rankable_ids:
            raise ValueError(
                f"All selected assays have rankable=False, but rankable-gated filter "
                f"(metric_bucket / metric_percentile / rank_by_metric_max) was set. "
                f"Selected assay_ids: {sorted(found_ids)}. "
                f"Pre-flight: list_metabolite_assays(rankable=True, value_kind='numeric').")
        excluded_assays = sorted(found_ids - rankable_ids)
        if excluded_assays:
            warnings.append(
                f"Soft-excluded {len(excluded_assays)} non-rankable assay(s) from "
                f"rankable-gated filter: {excluded_assays}")
        surviving_ids = sorted(rankable_ids)

    # 2. Summary
    summary_cypher, summary_params = build_metabolites_by_quantifies_assay_summary(
        assay_ids=surviving_ids, ...)
    summary_rows = conn.execute_query(summary_cypher, **summary_params)
    env = summary_rows[0] if summary_rows else _empty_summary_envelope()

    # 3. Enrich `by_metric` with per-assay precomputed range from diag_rows
    env["by_metric"] = _build_mqa_by_metric(diag_rows, env, ...)

    # 4. Detail (skipped for summary mode)
    rows: list[dict] = []
    if not summary:
        detail_cypher, detail_params = build_metabolites_by_quantifies_assay(
            assay_ids=surviving_ids, ..., verbose=verbose, limit=limit, offset=offset)
        rows = conn.execute_query(detail_cypher, **detail_params)

    return {
        "results": rows,
        "total_matching": env.get("total_matching", 0),
        "by_detection_status": env.get("by_detection_status", []),
        "by_metric_bucket": env.get("by_metric_bucket", []),
        "by_assay": env.get("by_assay", []),
        "by_compartment": env.get("by_compartment", []),
        "by_organism": env.get("by_organism", []),
        "by_metric": env["by_metric"],
        "excluded_assays": excluded_assays,
        "warnings": warnings,
        "not_found": {
            "assay_ids": not_found_assay_ids,
            "metabolite_ids": [],   # populated by an OPTIONAL MATCH probe if metabolite_ids passed
            "experiment_ids": [],
            "publication_doi": [],
        },
        "returned": len(rows),
        "truncated": len(rows) >= limit,
        "offset": offset,
    }
```

Run: `uv run pytest tests/unit/test_api_functions.py::TestMetabolitesByQuantifiesAssay -v`. Expected: GREEN.

- [ ] **Step 2: Implement `metabolites_by_flags_assay()`**

Two-query dispatch (no diagnostics — boolean tool has no rankable gate per parent §13.1):

1. `_summary` (envelope; coerce input `flag_value: bool | None` → string `'true'` / `'false'` / drop param if None per D4 / parent §11 Conv K).
2. `_detail` (only if `summary=False`).

Coercions:
- `flag_value: bool | None` at API boundary → string `'true'` / `'false'` for Cypher (D4 closure / parent §11 Conv K).
- `flag_value=False` returns rows in this slice (KG stores both true and false flags; differs from DM `genes_by_boolean_metric` which stores positive-only).

Validation:
- Empty `assay_ids` → ValueError.

Run: `uv run pytest tests/unit/test_api_functions.py::TestMetabolitesByFlagsAssay -v`. Expected: GREEN.

- [ ] **Step 3: Implement `assays_by_metabolite()`**

Two-query dispatch:

1. `_summary` (UNION ALL envelope) — also probes existence of metabolite IDs against the KG (for `not_found` flat list per parent §13.6).
2. `_detail` (only if `summary=False`).

Validation:
- Empty `metabolite_ids` → ValueError.
- `evidence_kind` ∈ {None, 'quantifies', 'flags'} → else ValueError.

Partition:
- `not_found: list[str]` flat — IDs absent from KG (probe via separate query: `MATCH (m:Metabolite) WHERE m.id IN $metabolite_ids RETURN m.id`).
- `not_matched: list[str]` flat — IDs in KG but no assay edge after filters (input ∩ KG − seen-in-results).
- `metabolites_with_evidence` = sorted set of metabolite_ids that appear in `results`.
- `metabolites_without_evidence` = input − `metabolites_with_evidence` (includes both not_found and not_matched).
- `metabolites_matched` = `len(metabolites_with_evidence)` (distinct count, not row count).

Per parent §13.6: `assays_by_metabolite` uses FLAT `list[str]` for `not_found` (only one batch input).

Run: `uv run pytest tests/unit/test_api_functions.py::TestAssaysByMetabolite -v`. Expected: GREEN.

- [ ] **Step 4: Wire exports**

In `multiomics_explorer/api/__init__.py`, add 3 imports + 3 `__all__` entries (alphabetical placement among the metabolomics block):

```python
from .functions import (
    # ... existing ...
    assays_by_metabolite,
    metabolites_by_flags_assay,
    metabolites_by_quantifies_assay,
)

__all__ = [
    # ... existing ...
    "assays_by_metabolite",
    "metabolites_by_flags_assay",
    "metabolites_by_quantifies_assay",
]
```

Same edits in `multiomics_explorer/__init__.py`.

- [ ] **Step 5: Run all API tests; commit**

```bash
uv run pytest tests/unit/test_api_functions.py -v 2>&1 | tail -20
git add multiomics_explorer/api/functions.py multiomics_explorer/api/__init__.py multiomics_explorer/__init__.py
git commit -m "feat(api): add metabolites-by-assay slice API functions (3 tools)"
```

Expected: all 3 new test classes GREEN; no pre-existing test red.

---

## Task 4: GREEN — MCP wrapper layer (single tool-wrapper agent)

**Owner:** `tool-wrapper` agent. **Mode B briefing + anti-scope-creep guardrail mandatory.**
**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`

Per parent §11 Conv E + §13.5: every envelope rollup is a typed Pydantic sub-model. NO generic `list[dict]`. Per parent §13.6: drill-down tools use STRUCTURED `NotFound` (multi-batch); reverse-lookup uses FLAT `list[str]` (single batch).

- [ ] **Step 1: Define typed Pydantic envelope sub-models**

Naming convention from parent §11 Conv E: `<ShortPrefix><Domain>` — `Mqa*` for `metabolites_by_quantifies_assay`, `Mfa*` for `metabolites_by_flags_assay`, `Abm*` for `assays_by_metabolite`.

Required sub-models (audit while implementing — add any rollup that surfaces in §4.3 / §5.3 / §6.3 envelope tables):

```python
# metabolites_by_quantifies_assay envelope models
class MqaByDetectionStatus(BaseModel):
    """One bucket of the by_detection_status rollup. Values: detected, sporadic, not_detected."""
    detection_status: str
    count: int

class MqaByMetricBucket(BaseModel):
    bucket: str   # 'top_decile' | 'top_quartile' | 'mid' | 'low'
    count: int

class MqaByAssay(BaseModel):
    assay_id: str
    count: int

class MqaByCompartment(BaseModel):
    compartment: str
    count: int

class MqaByOrganism(BaseModel):
    organism_name: str
    count: int

class MqaTopMetabolite(BaseModel):
    metabolite_id: str
    name: str
    count: int

class MqaByMetric(BaseModel):
    """Per-assay precomputed-vs-filtered. Mirrors DM `by_metric`."""
    assay_id: str
    name: str
    metric_type: str
    count: int               # filtered-slice count for this assay
    filtered_value_min: float | None
    filtered_value_max: float | None
    assay_value_min: float | None       # full-assay range echo
    assay_value_q1: float | None
    assay_value_median: float | None
    assay_value_q3: float | None
    assay_value_max: float | None
    rankable: bool

class MqaNotFound(BaseModel):
    """Structured not_found per parent §13.6 (multi-batch)."""
    assay_ids: list[str] = Field(default_factory=list)
    metabolite_ids: list[str] = Field(default_factory=list)
    experiment_ids: list[str] = Field(default_factory=list)
    publication_doi: list[str] = Field(default_factory=list)
```

Repeat for `Mfa*` (no `MfaByDetectionStatus`; instead `MfaByValue` for true/false counts; no `MfaByMetricBucket` — boolean has no buckets) and `Abm*` (`AbmByEvidenceKind`, `AbmByDetectionStatus` (numeric subset), `AbmByFlagValue` (boolean subset), `AbmByOrganism`, `AbmByCompartment`, `AbmByAssay`; flat `not_found: list[str]`).

- [ ] **Step 2: Define `<Tool>Result` and `<Tool>Response` Pydantic models**

Per slice spec §4.2 / §5.2 / §6.2 row schemas. Use `| None` for sparse fields. Verbose-only fields default `None` and are populated only when `verbose=True`.

```python
class MetabolitesByQuantifiesAssayResult(BaseModel):
    metabolite_id: str
    name: str
    kegg_compound_id: str | None
    value: float | None
    value_sd: float | None
    n_replicates: int | None
    n_non_zero: int | None
    metric_type: str
    metric_bucket: str | None      # rankable-only
    metric_percentile: float | None
    rank_by_metric: int | None
    detection_status: str | None
    timepoint: str | None          # D3-coerced from "" → null
    timepoint_hours: float | None  # D3-coerced from -1.0
    timepoint_order: int | None    # D3-coerced from 0
    growth_phase: str | None       # KG-MET-017: null today
    condition_label: str | None
    assay_id: str
    organism_name: str
    compartment: str
    # verbose-only:
    assay_name: str | None = None
    field_description: str | None = None
    experimental_context: str | None = None
    light_condition: str | None = None
    replicate_values: list[float] | None = None

class MetabolitesByQuantifiesAssayResponse(BaseModel):
    results: list[MetabolitesByQuantifiesAssayResult]
    total_matching: int
    by_detection_status: list[MqaByDetectionStatus]
    by_metric_bucket: list[MqaByMetricBucket]
    by_assay: list[MqaByAssay]
    by_compartment: list[MqaByCompartment]
    by_organism: list[MqaByOrganism]
    by_metric: list[MqaByMetric]
    excluded_assays: list[str]
    warnings: list[str]
    not_found: MqaNotFound
    returned: int
    truncated: bool
    offset: int
```

Same shape for `MetabolitesByFlagsAssayResult` / `Response` (no `by_detection_status`, no `by_metric_bucket`, no `excluded_assays` non-empty case but kept for shape consistency per slice spec §5.3) and `AssaysByMetaboliteResult` / `Response` (polymorphic, cross-arm fields `| None`; flat `not_found: list[str]`).

- [ ] **Step 3: Implement the 3 `@mcp.tool` async wrappers**

Tags per parent §11 Conv N + slice spec headers. Annotations universal. Field descriptions MUST satisfy field-rubric (parent §13.5):

- Real KG values (e.g. `'kegg.compound:C00074'`, `'metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration'`, `'4 days'`, `0.4465`).
- Drill-down signposting in `by_*` field descriptions.
- No Cypher-syntax jargon (`apoc.coll.frequencies`, `coalesce`, `MATCH`, `CASE WHEN` etc.).

Tool docstrings include §10 tested-absent invariant (parent §10 propagation table):

> "A row with `value=0` / `flag_value=false` / `detection_status='not_detected'` is *tested-absent* (assayed and not found, kept in results). A missing row is *unmeasured* (not in this assay's scope). Don't conflate."

Each wrapper:
1. Calls `await ctx.info(f"<tool> <key params>")` at top (parent §11 Conv O).
2. Wraps `ToolError` (not bare strings) for caller-facing errors.
3. Calls the api/ function and returns `<Tool>Response(**result)`.

Run: `uv run pytest tests/unit/test_tool_wrappers.py -v 2>&1 | tail -30`. Expected: GREEN; `test_all_tools_registered` passes (3 new names).

- [ ] **Step 4: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "feat(mcp): add metabolites-by-assay slice tool wrappers (3 tools)"
```

---

## Task 5: GREEN — about-content YAML + analysis doc + CLAUDE.md (single doc-updater agent)

**Owner:** `doc-updater` agent. **Mode B briefing + anti-scope-creep guardrail mandatory.**
**Files:**
- Create: `multiomics_explorer/inputs/tools/metabolites_by_quantifies_assay.yaml`
- Create: `multiomics_explorer/inputs/tools/metabolites_by_flags_assay.yaml`
- Create: `multiomics_explorer/inputs/tools/assays_by_metabolite.yaml`
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolomics.md` (only if Tool 1 hasn't already added §"Tested-absent vs unmeasured")
- Modify: `CLAUDE.md` (3 new MCP-tools-table rows)
- Generated (output): `multiomics_explorer/skills/multiomics-kg-guide/references/tools/metabolites_by_quantifies_assay.md`, `metabolites_by_flags_assay.md`, `assays_by_metabolite.md`

- [ ] **Step 1: Author the 3 YAML inputs**

Each YAML carries `examples`, `chaining`, `mistakes`, `verbose_fields`. Mistakes section MUST include (parent §10 propagation):

```yaml
mistakes:
  - wrong: "Filter out value=0 / flag_value=false rows assuming they are noise."
    right: |
      These rows are tested-absent — the metabolite was assayed and not found.
      They are biology. Keep them unless explicitly investigating presence-only.
  - wrong: "A metabolite missing from results means it was not detected."
    right: |
      Missing means unmeasured (out of scope for this assay). For 'tested and
      not found,' look for a value=0 / flag_value=false / detection_status='not_detected'
      row.
```

Plus tool-specific mistakes:

`metabolites_by_quantifies_assay.yaml` adds:
- `wrong: "Apply metric_bucket=['top_decile'] without checking rankable on the assay."` `right: "Pre-flight via list_metabolite_assays(rankable=True, value_kind='numeric'). Tool soft-excludes non-rankable assays from mixed input and raises if every selected assay is non-rankable."`
- `wrong: "Expect not_found to be a flat list[str]."` `right: "Drill-downs use a structured NotFound (4 keys: assay_ids, metabolite_ids, experiment_ids, publication_doi) per parent §13.6 — multi-batch input → structured."`

`metabolites_by_flags_assay.yaml` adds:
- `wrong: "Expect by_detection_status in the envelope."` `right: "by_detection_status exists only on the numeric arm. On boolean, flag_value IS the qualitative-detection signal; by_value is its envelope rollup."`
- Same structured-not_found note as above.

`assays_by_metabolite.yaml` adds:
- `wrong: "Use total_matching for unique-metabolite count."` `right: "total_matching is row count (one row per metabolite × assay-edge). Use metabolites_matched for distinct count."`
- `wrong: "Treat polymorphic rows as kind-uniform."` `right: "Numeric rows carry value/value_sd/detection_status/timepoint*/metric_bucket/metric_percentile/rank_by_metric. Boolean rows carry flag_value/n_positive. Cross-arm fields are explicit None (union-shape padding)."`
- `wrong: "Pass evidence_kind='quantifies' AND expect by_flag_value populated."` `right: "When evidence_kind filters out one arm, that arm's envelope rollup is empty (no rows contribute)."`

Chaining sections include slice spec §4.1 / §5.1 / §6.1 docstring patterns:

`metabolites_by_quantifies_assay.yaml` chaining:
- "Drill across to `assays_by_metabolite(metabolite_ids=[...])` for the same metabolites' boolean evidence + cross-organism reverse view."
- "Drill across to `genes_by_metabolite(metabolite_ids=[...], organism=...)` for gene catalysts/transporters of these metabolites."
- "Pre-flight: `list_metabolite_assays(rankable=True, value_kind='numeric')` to confirm rankable filters apply."

`metabolites_by_flags_assay.yaml` chaining:
- "Drill across to `assays_by_metabolite(metabolite_ids=[...])` — quantifies-arm complement."
- "Drill across to `genes_by_metabolite(metabolite_ids=[...], organism=...)` for chemistry context."

`assays_by_metabolite.yaml` chaining:
- "Originates from `list_metabolites(metabolite_ids=[...])` (chemistry-layer discovery) or `metabolites_by_gene(locus_tags=[...])` (gene-anchored chemistry)."
- "Drill back to numeric details via `metabolites_by_quantifies_assay(assay_ids=[...], metabolite_ids=[...])`."

Verbose-fields tables match slice spec verbose lines (§4.2 / §5.2 / §6.2).

Examples MUST use real KG values (parent §13.5 — pulled from §3 verification):
- `assay_id: 'metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration'`
- `metabolite_id: 'kegg.compound:C00074'` (PEP)
- `timepoint: '4 days'` / `'6 days'`
- Headline numbers: `total_matching=64` for the MIT9313 assay; `total_matching=93` for the msystems boolean assay; `total_matching=20` for PEP reverse-lookup with `by_evidence_kind={quantifies: 18, flags: 2}` (parent §3 / slice spec §7).

- [ ] **Step 2: Regenerate about content**

```bash
uv run python scripts/build_about_content.py
```

This writes directly to `multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md` (no separate sync step per `feedback_skill_content_yaml_workflow` memory). Sanity-check the 3 new generated files appear and contain `mistakes`, `examples`, `chaining`, `verbose_fields` sections rendered from YAML + autogenerated `params`, `response format`, `envelope keys`, `Package import equivalent`.

- [ ] **Step 3: Update analysis doc (only if not already done by Tool 1)**

Check if `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolomics.md` already has a top-level §"Tested-absent vs unmeasured" section (added by Tool 1's commit per parent §10 propagation table). If yes, skip. If no, add the section using the parent §10 table verbatim. Section MUST:
- Define the 3 states (measured-present / tested-absent / unmeasured).
- Show the per-arm signature table (numeric: `value=0` + `n_non_zero=0` + `detection_status='not_detected'`; boolean: `flag_value=false`).
- Cross-reference the 3 new tools by name.
- Cite the live-KG headline: 75% of numeric edges are not_detected; 62% of boolean rows are false.

- [ ] **Step 4: Add 3 rows to CLAUDE.md MCP-tools table**

Find the table under `## MCP Server > ### Tools`. Insert 3 rows alphabetically:

```markdown
| `assays_by_metabolite` | Polymorphic reverse-lookup: metabolite IDs → all measurement evidence across both arms (quantifies + flags). Cross-organism by default. Numeric-arm rows carry `value`/`detection_status`/`timepoint*`/`metric_bucket`/`metric_percentile`/`rank_by_metric`; boolean-arm rows carry `flag_value`/`n_positive`. Cross-arm fields are explicit `None`. Three states for a metabolite: `not_found` (ID absent from KG), `not_matched` (ID in KG, no edge after filters), or row with `value=0` / `flag_value=false` / `detection_status='not_detected'` (*tested-absent* — real biology, kept in results). Filterable by `evidence_kind`, `metric_types`, `compartment`, `organism`, `exclude_metabolite_ids`. Originates from `list_metabolites` / `metabolites_by_gene`; drill back via `metabolites_by_quantifies_assay`. |
| `metabolites_by_flags_assay` | Boolean-arm drill-down on MetaboliteAssay edges — one row per (metabolite × flag-edge). `flag_value=False` rows are *tested-absent* (real biology, ~62% of boolean rows). Filterable by `flag_value` (None / True / False). Same scoping block as `metabolites_by_quantifies_assay`; no rankable gate. No `by_detection_status` envelope (boolean arm has none). Drill across via `assays_by_metabolite` for the quantifies-arm complement. |
| `metabolites_by_quantifies_assay` | Numeric-arm drill-down on MetaboliteAssay edges — one row per (metabolite × assay-edge). `value=0` / `detection_status='not_detected'` rows are *tested-absent* (real biology — 75% of numeric edges). Always-available filters: `value_min/max`, `detection_status`, `timepoint`. Rankable-gated filters (raise on all-non-rankable, soft-exclude on mixed): `metric_bucket`, `metric_percentile_min/max`, `rank_by_metric_max`. `by_metric` envelope pairs filtered slice with full-assay range echo. Pre-flight via `list_metabolite_assays(rankable=True, value_kind='numeric')`. |
```

Each row carries the parent §10 / §10 propagation note ("returns tested-absent rows by default" — embedded in the row text above).

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/inputs/tools/metabolites_by_quantifies_assay.yaml \
        multiomics_explorer/inputs/tools/metabolites_by_flags_assay.yaml \
        multiomics_explorer/inputs/tools/assays_by_metabolite.yaml \
        multiomics_explorer/skills/multiomics-kg-guide/references/tools/ \
        multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolomics.md \
        CLAUDE.md
git commit -m "docs(slice): add about-content + analysis-doc propagation for metabolites-by-assay slice"
```

---

## Task 6: Integration tests against live KG

**Owner:** main session (or dispatch a `general-purpose` agent for parallelism).
**Files:**
- Modify: `tests/integration/test_mcp_tools.py`
- Modify: `tests/integration/test_api_contract.py`
- Modify: `tests/integration/test_tool_correctness_kg.py` (if file pattern applies — check first)

All tests `@pytest.mark.kg`. Pinned baselines per slice spec §7 (verified 2026-05-06):

- [ ] **Step 1: Add `TestMetabolitesByQuantifiesAssayKG`**

```python
@pytest.mark.kg
class TestMetabolitesByQuantifiesAssayKG:
    """Integration tests against live KG. Baselines from slice spec §7."""

    def test_mit9313_chitosan_summary(self, kg_conn):
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        result = metabolites_by_quantifies_assay(
            assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"],
            summary=True,
            conn=kg_conn,
        )
        assert result["total_matching"] == 64
        # Convert apoc.coll.frequencies to dict for assertions
        det = {x["detection_status"] if isinstance(x, dict) else x.detection_status:
               x["count"] if isinstance(x, dict) else x.count
               for x in result["by_detection_status"]}
        assert det == {"detected": 27, "sporadic": 30, "not_detected": 7}
        bucket = {x["bucket"]: x["count"] for x in result["by_metric_bucket"]}
        assert bucket == {"mid": 32, "low": 16, "top_quartile": 9, "top_decile": 7}

    def test_mit9313_top5_rows(self, kg_conn):
        # Top-5 detail: F6P at top_decile rank 1-3, Citrate at top_decile rank 4-5.
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        result = metabolites_by_quantifies_assay(
            assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"],
            limit=5,
            conn=kg_conn,
        )
        assert len(result["results"]) == 5
        ranks = [r["rank_by_metric"] for r in result["results"]]
        assert ranks == [1, 2, 3, 4, 5]
        names = [r["name"].lower() for r in result["results"]]
        assert sum("f6p" in n or "fructose" in n for n in names[:3]) >= 1
        assert sum("citrate" in n or "citric" in n for n in names[3:5]) >= 1

    def test_all_non_rankable_raises(self, kg_conn):
        # If selected assay has rankable=false and metric_bucket is set, raise.
        # Pick a non-rankable assay from list_metabolite_assays output.
        ...

    def test_growth_phase_null_today(self, kg_conn):
        # KG-MET-017: every metabolomics experiment has empty time_point_growth_phases[].
        # All rows must have growth_phase=None.
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        result = metabolites_by_quantifies_assay(
            assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"],
            limit=10, conn=kg_conn,
        )
        assert all(r["growth_phase"] is None for r in result["results"])
```

- [ ] **Step 2: Add `TestMetabolitesByFlagsAssayKG`**

```python
@pytest.mark.kg
class TestMetabolitesByFlagsAssayKG:
    def test_msystems_summary(self, kg_conn):
        from multiomics_explorer.api.functions import metabolites_by_flags_assay
        result = metabolites_by_flags_assay(
            assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"],
            summary=True, conn=kg_conn,
        )
        assert result["total_matching"] == 93
        flags = {(x["value"] if isinstance(x, dict) else x.value):
                 (x["count"] if isinstance(x, dict) else x.count)
                 for x in result["by_value"]}
        assert flags == {"false": 58, "true": 35}

    def test_msystems_top5_alphabetical_true(self, kg_conn):
        # Top-5 rows: flag_value=true, alphabetical.
        from multiomics_explorer.api.functions import metabolites_by_flags_assay
        result = metabolites_by_flags_assay(
            assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"],
            limit=5, conn=kg_conn,
        )
        assert len(result["results"]) == 5
        assert all(r["flag_value"] is True for r in result["results"])
        # Slice spec §7: S-adenosyl-L-methionine, tyrosine, NADH, AMP, S-Adenosyl-L-homocysteine
        names = {r["name"].lower() for r in result["results"]}
        assert sum("adenosyl" in n or "tyrosine" in n or "nadh" in n or "amp" in n
                   for n in names) >= 4

    def test_flag_value_false_returns_rows(self, kg_conn):
        # Unlike DM genes_by_boolean_metric (positive-only KG storage),
        # Assay_flags_metabolite stores both — flag_value=False returns real rows.
        from multiomics_explorer.api.functions import metabolites_by_flags_assay
        result = metabolites_by_flags_assay(
            assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"],
            flag_value=False, summary=True, conn=kg_conn,
        )
        assert result["total_matching"] == 58  # the 'false' bucket from prior test
```

- [ ] **Step 3: Add `TestAssaysByMetaboliteKG`**

```python
@pytest.mark.kg
class TestAssaysByMetaboliteKG:
    def test_pep_polymorphic_summary(self, kg_conn):
        # PEP (kegg.compound:C00074) — 18 quantifies + 2 flags = 20 total. Slice spec §7.
        from multiomics_explorer.api.functions import assays_by_metabolite
        result = assays_by_metabolite(
            metabolite_ids=["kegg.compound:C00074"],
            summary=True, conn=kg_conn,
        )
        assert result["total_matching"] == 20
        assert result["metabolites_matched"] == 1
        ek = {(x["evidence_kind"] if isinstance(x, dict) else x.evidence_kind):
              (x["count"] if isinstance(x, dict) else x.count)
              for x in result["by_evidence_kind"]}
        assert ek == {"quantifies": 18, "flags": 2}
        det = {x["detection_status"]: x["count"] for x in result["by_detection_status"]}
        assert det == {"not_detected": 12, "detected": 3, "sporadic": 3}
        # 70% of all PEP measurements are tested-absent (12 + 2 = 14 / 20 = 70%).

    def test_pep_top5_evidence_kind_desc(self, kg_conn):
        # Sort key: metabolite_id ASC, evidence_kind DESC ('quantifies' > 'flags' alphabetically).
        # Numeric rows MUST come first in truncated head.
        from multiomics_explorer.api.functions import assays_by_metabolite
        result = assays_by_metabolite(
            metabolite_ids=["kegg.compound:C00074"], limit=5, conn=kg_conn,
        )
        assert all(r["evidence_kind"] == "quantifies" for r in result["results"])

    def test_evidence_kind_filter_quantifies_only(self, kg_conn):
        from multiomics_explorer.api.functions import assays_by_metabolite
        result = assays_by_metabolite(
            metabolite_ids=["kegg.compound:C00074"], evidence_kind="quantifies",
            summary=True, conn=kg_conn,
        )
        assert result["total_matching"] == 18

    def test_not_found_flat_list(self, kg_conn):
        # Single-batch input → flat not_found per parent §13.6.
        from multiomics_explorer.api.functions import assays_by_metabolite
        result = assays_by_metabolite(
            metabolite_ids=["kegg.compound:C00074", "fake.id:DOESNOTEXIST"],
            summary=True, conn=kg_conn,
        )
        assert result["not_found"] == ["fake.id:DOESNOTEXIST"]
```

- [ ] **Step 4: Add API contract tests**

In `tests/integration/test_api_contract.py`, add 3 contract tests that exercise the full Pydantic Response model validation against live KG output.

```python
@pytest.mark.kg
class TestMetabolitesByQuantifiesAssayContract:
    def test_response_validates(self, kg_conn):
        from multiomics_explorer.api.functions import metabolites_by_quantifies_assay
        from multiomics_explorer.mcp_server.tools import MetabolitesByQuantifiesAssayResponse
        result = metabolites_by_quantifies_assay(
            assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"],
            limit=5, conn=kg_conn,
        )
        validated = MetabolitesByQuantifiesAssayResponse(**result)
        assert validated.total_matching == 64

# (parallel test classes for the other 2 tools)
```

- [ ] **Step 5: Run integration suite; commit**

```bash
uv run pytest tests/integration/ -m kg -v 2>&1 | tail -40
git add tests/integration/
git commit -m "test(integration): add live-KG tests for metabolites-by-assay slice"
```

Expected: all new `@pytest.mark.kg` tests GREEN; pre-existing tests unchanged. If any pre-existing test goes red, **STOP and report as concern** (anti-scope-creep).

---

## Task 7: Regression baselines + eval cases

**Owner:** main session.
**Files:**
- Modify: `tests/regression/test_regression.py` (`TOOL_BUILDERS` dict, line 62)
- Modify: `tests/evals/test_eval.py` (`TOOL_BUILDERS` dict, line 61)
- Modify: `tests/evals/cases.yaml`

- [ ] **Step 1: Add 6 entries to regression `TOOL_BUILDERS`**

After line 76 (after the `metabolites_by_gene` entry):

```python
"metabolites_by_quantifies_assay": build_metabolites_by_quantifies_assay,
"metabolites_by_quantifies_assay_summary": build_metabolites_by_quantifies_assay_summary,
"metabolites_by_flags_assay": build_metabolites_by_flags_assay,
"metabolites_by_flags_assay_summary": build_metabolites_by_flags_assay_summary,
"assays_by_metabolite": build_assays_by_metabolite,
"assays_by_metabolite_summary": build_assays_by_metabolite_summary,
```

(Diagnostics builders are NOT regressed — gate-only metadata, no row contract.)

- [ ] **Step 2: Add same 6 entries to eval `TOOL_BUILDERS`**

Mirror the additions in `tests/evals/test_eval.py:61`.

- [ ] **Step 3: Add 6-9 representative cases to `tests/evals/cases.yaml`**

2-3 cases per tool. Examples:

```yaml
- id: mqa_mit9313_summary
  tool: metabolites_by_quantifies_assay
  params:
    assay_ids: ["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"]
    summary: true
  expected_total_matching: 64

- id: mqa_top5_rankable
  tool: metabolites_by_quantifies_assay
  params:
    assay_ids: ["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"]
    limit: 5
  expected_count: 5

- id: mfa_msystems_summary
  tool: metabolites_by_flags_assay
  params:
    assay_ids: ["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"]
    summary: true
  expected_total_matching: 93

- id: abm_pep_polymorphic
  tool: assays_by_metabolite
  params:
    metabolite_ids: ["kegg.compound:C00074"]
    summary: true
  expected_total_matching: 20
```

- [ ] **Step 4: Generate fresh regression baselines**

```bash
uv run pytest tests/regression/ -m kg --regenerate-baselines 2>&1 | tail -10
# (if no --regenerate-baselines flag, see existing convention in tests/regression/conftest.py)
```

Sanity-check the new baseline files appear under `tests/regression/baselines/` and are deterministic (sorted, rounded floats per `_normalize` at line 107).

- [ ] **Step 5: Run regression + eval suites; commit**

```bash
uv run pytest tests/regression/ tests/evals/ -m kg -v 2>&1 | tail -20
git add tests/regression/ tests/evals/
git commit -m "test(regression): add baselines + eval cases for metabolites-by-assay slice"
```

---

## Task 8: VERIFY — code review hard gate

**Owner:** main session, dispatching `code-reviewer` subagent per `add-or-update-tool` SKILL.md (hard gate before merge).

- [ ] **Step 1: Diff summary**

```bash
git log --oneline main..HEAD
git diff main...HEAD --stat
```

Expected: ~6-8 commits across 4 layers + tests + docs, ~2500-3500 LoC added (3 tools is roughly 1.5x a single-tool slice).

- [ ] **Step 2: Dispatch `code-reviewer` agent**

Brief: review the full diff against:
- `add-or-update-tool/references/checklist.md` (4-layer conventions)
- `layer-rules/SKILL.md` (kw-only args, exact-match `AS snake_case`, NULL handling)
- field-rubric (parent §13.5)
- Mode B template-then-extend pattern (was `metabolites_by_quantifies_assay` actually written first as the template?)
- CyVer `UNION ALL` rel-vars caveat (parent §12.4 / §13.7) — verify `assays_by_metabolite` builder uses `rq` / `rf`, NOT `[r:A|B]`.
- Anti-scope-creep: NO existing tests modified or rebaselined.

Hard gate: code review MUST sign off before any merge to main.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/unit/ tests/integration/ tests/regression/ -v 2>&1 | tail -20
uv run pytest tests/ -v -m kg 2>&1 | tail -20
```

Expected: all GREEN; zero pre-existing tests modified.

- [ ] **Step 4: Smoke-test through MCP**

Restart MCP server (per `feedback_mcp_restart` memory):

```
# In Claude Code: /mcp restart
```

Then via Claude Code MCP tool calls:

```
Use mcp__multiomics-kg__metabolites_by_quantifies_assay with assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"], limit=5
Use mcp__multiomics-kg__metabolites_by_flags_assay with assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"], limit=5
Use mcp__multiomics-kg__assays_by_metabolite with metabolite_ids=["kegg.compound:C00074"], limit=10
```

Expected: 5 / 5 / 10 rows; envelope rollups match slice spec §7 baselines.

- [ ] **Step 5: Final commit (if any tweaks needed) + offer merge**

```bash
git add -A
git commit -m "chore: post-review cleanup for metabolites-by-assay slice"  # only if needed
```

Per `superpowers:finishing-a-development-branch`, present merge / PR / cleanup options to the user.

---

## Self-review checks (against the spec)

**Spec coverage (slice spec sections):**

- §1 Purpose / §2 Out of scope → captured in YAML examples (Task 5) + tool docstrings (Task 4).
- §3 KG dependencies → Cypher in Tasks 2 references the verified §12 patterns; sentinel triple coercion + KG-MET-017 null handling tested in Task 6.
- §4 Tool 1 (numeric drill-down) → Task 1 tests, Task 2 builders, Task 3 API, Task 4 wrapper, Task 5 docs, Task 6 integration.
- §5 Tool 2 (boolean drill-down) → same coverage.
- §6 Tool 3 (polymorphic reverse-lookup) → same coverage; Task 2 Step 4 + Task 4 wrapper carry the polymorphic null-padding contract.
- §7 Verified Cypher + §7.1 CyVer caveat → Task 2 Step 4 + Task 1 `TestBuildAssaysByMetabolite` tests assert UNION ALL with distinct rel-vars; anti-pattern explicitly tested-against (`[r:A|B]` MUST NOT appear).
- §8 Phase 2 build dispatch → Tasks 1 (RED) → 2/3/4/5 (GREEN, parallel-eligible across files but each file owned by one agent) → 6/7 (integration + regression) → 8 (VERIFY).
- §9 Implementer order (Mode B) → embedded in every implementer task brief.
- §10 References → bibliographic; covered by parent links throughout.

**Parent §13 deliverables coverage:**

- §13.1 builder names → Task 2 table.
- §13.2 CyVer registry update → Task 2 Step 5.
- §13.3 Layer-2 exports → Task 3 Step 4.
- §13.4 anti-scope-creep guardrail → embedded verbatim in every implementer task brief + the top-of-plan "Anti-scope-creep guardrail" block.
- §13.5 field-rubric checklist → Task 4 Step 3 acceptance criteria.
- §13.6 structured `not_found` deviation → Task 4 sub-models (`MqaNotFound`, `MfaNotFound`); Task 3 Step 3 flat `not_found` for `assays_by_metabolite`.
- §13.7 NULL-handling in aggregation → tested in Task 1 `TestBuildAssaysByMetaboliteSummary::test_null_filter_on_collected_arrays`; reinforced in Task 2 Step 4.
- §13.8 Phase 2 dispatch summary → mirrored in this plan's Tasks 1-8.

**Placeholder scan:** task bodies use `...` only inside test-method bodies for stubbed connection setup, where the agent has unambiguous instruction (1-3 setup steps spelled out in adjacent comments). No "TODO", "TBD", "implement later", "fill in details", or "similar to Task N" elsewhere. Cypher templates show full skeletons; envelope schemas list every field by name.

**Type consistency:**
- All 9 builders return `tuple[str, dict]`. ✓
- API functions return `dict`; MCP wrappers instantiate `<Tool>Response(**result)`. ✓
- `flag_value: bool | None` at API boundary, coerced to string `'true'` / `'false'` for Cypher. ✓
- `MqaNotFound` / `MfaNotFound` (structured, multi-batch) vs flat `list[str]` for `assays_by_metabolite.not_found`. ✓
- `evidence_kind` row column is the literal string `'quantifies'` or `'flags'` (UNION ALL discriminator); cross-arm fields use explicit `null AS field`. ✓
- Sub-model names match across Pydantic definitions, Response field annotations, and api/-layer dict keys. ✓
- `EXPECTED_TOOLS` extends by 3 names; `TOOL_BUILDERS` extends by 6 entries (3 detail + 3 summary, no diagnostics). ✓

**Spec requirement with no task:** none found. (Slice spec §10 references is bibliographic; covered.)

---

**Plan complete.** Saved to `docs/superpowers/plans/2026-05-06-metabolites-by-assay-slice.md`.
