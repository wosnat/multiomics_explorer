# Control-timing surface (Mode B, 4 tools + docs)

**Status:** FROZEN 2026-10-18 (user-approved; DE rows carry `control_timing` on every row) · **KG:** 2026-10-18T07:51Z (`Experiment.control_timing`,
`Experiment.design_notes`) · **Dialog:** `docs/kg-specs/2026-10-13-per-arm-sampling-shared-model-explorer-asks.md`
(SIM-001..004, T1–T5, KG update 2026-10-18). Additive; no `mcp_min_version` bump.

## Purpose

A DE row's `timepoint` / `growth_phase` describe the **treatment arm**. On 22 experiments the
control was sampled at another time (`baseline` 18, `mixed` 4), and on many `matched` ones the
match is by growth state, not calendar day (e.g. Weissberg MED4 coculture d18 vs axenic d14, in
death phase). Today nothing in the tool surface says so. Surface the curated field where plans are
made (`list_experiments`) and where DE rows are read (both DE tools).

## KG facts (verified live, 2026-10-18T07:51Z)

| Fact | Value |
|---|---|
| `control_timing` | closed CV `{matched, baseline, mixed}`; 151 / 18 / 4; present on all 173 DE experiments, absent on the 35 without DE edges |
| `design_notes` | sparse free text on 138 experiments (116 matched, 18 baseline, 4 mixed); never `''`; avg 262 chars, max 947 |
| `experimentFullText` | already indexes `design_notes` (`search_text='viability'` hits the E7 experiment) |
| DE edges on non-matched experiments | 102,089 of 323,849 |

## Changes per tool

### 1. `list_experiments`
- **Row, compact:** `control_timing: str | None` (null on experiments with no DE contrast, like `table_scope`).
- **Row, compact, sparse:** `design_notes: str` — omitted from the row when the KG has none (api drops the key; `ExperimentResult` is a `SparseRow`).
- **Filter:** `control_timing: list[str] | None` → `e.control_timing IN $control_timings`. Closed-vocab warning on unknown values via `_CLOSED_VOCAB_PARAMS` (same as `table_scope`); experiments with no DE never match.
- **Summary:** `by_control_timing: list[{control_timing, count}]` from `apoc.coll.frequencies(collect(e.control_timing))` (no-DE experiments not counted, like `by_table_scope`).

```cypher
-- verified: 22 rows
MATCH (p:Publication)-[:Has_experiment]->(e:Experiment) WHERE e.control_timing IN $control_timings RETURN count(e)
-- verified: MED4 → matched 29 / baseline 6 / mixed 2
... WITH collect(e.control_timing) AS cts RETURN apoc.coll.frequencies(cts) AS by_control_timing
```

### 2. `list_filter_values`
- New `filter_type='control_timing'` (node, `Experiment`), read from `ControlledVocabulary` with value descriptions (registry entry next to `table_scope`).

### 3. `differential_expression_by_gene`
- **Row, compact:** `control_timing: str` on every row (`e.control_timing AS control_timing`; every DE experiment carries it). In a `mixed` experiment every row reads `mixed` (no per-timepoint field exists; `design_notes` names the timepoints).
- **Envelope `experiments[]`, compact:** `control_timing` (always — DE experiments always carry it) and sparse `design_notes` (omitted when absent). Added to `_DE_EXPERIMENT_COMPACT_KEYS`.

```cypher
-- verified (PMM0001): 37 rows — baseline 14, matched 23
RETURN e.control_timing AS control_timing
```

### 4. `differential_expression_by_ortholog`
- **Row, compact:** `control_timing: str` on every row (`e.control_timing AS control_timing`). No `design_notes` (rows are group × experiment × timepoint; drill via `list_experiments(experiment_ids=…)`). `top_experiments` unchanged.

## Docs
- `docs://guide/conventions`: one paragraph — `time_point` / `growth_phase` describe the treatment arm; `control_timing` says whether the control was sampled at the same time or growth state (`matched`), once at another time (`baseline`) or partly (`mixed`); read `design_notes` before comparing timepoints, including on `matched` experiments matched by growth state.
- Tool YAMLs (`list_experiments`, `differential_expression_by_gene`, `differential_expression_by_ortholog`, `list_filter_values`): one example (`list_experiments(control_timing=['baseline','mixed'])`), one mistake each ("a DE timepoint label is the treatment arm's; check `control_timing` / `design_notes`").
- CLAUDE.md rows for the 3 tools (+ `list_filter_values` vocab list); regenerate; refresh examples.

## Tests
- Unit: builders (column + filter + summary key), api (sparse-key drop for `design_notes` on the by_gene envelope and `list_experiments` rows, closed-vocab warning), wrappers (field present / omitted on wire).
- Edge cases: `list_experiments(control_timing=['mixed'], organism='Alteromonas…')` → empty envelope, no crash; unknown value → warning.
- Integration (live): filter count 22 for `['baseline','mixed']`; E7 experiment `control_timing='matched'` with `design_notes`; every DE row carries `control_timing` (baseline / matched both present for PMM0001).
- Regression: `--force-regen` for `list_experiments_*` and DE goldens (new columns only — verify no other diffs).

## Out of scope
`list_publications` rollup; `gene_response_profile`; a control-arm growth-phase filter (declined ARM-005); `statistical_model_id` (dropped KG-side).
