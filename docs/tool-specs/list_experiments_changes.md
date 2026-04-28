# list_experiments: profiled-only `organism=` + per-TP `growth_phase` — What to Change

## Executive Summary

Two related fixes to `list_experiments`, both surfaced as silent-wrong-filter
hazards by recent analyses (gaps_and_friction F2 and F3 in
`multiomics_research/analyses/2026-04-27-1117-prochlorococcus_stress_axenic_vs_coculture/`).

**F2 — `organism=` becomes profiled-only (BREAKING).** Today
`organism="MED4"` matches `e.organism_name OR e.coculture_partner`. The
filter silently returns experiments where MED4 is the coculture partner,
inflating the result set for the overwhelmingly common intent ("give me
experiments where MED4 is the profiled organism"). Live-KG: 48 rows today
vs 39 profiled-only. After this change `organism=` filters
`e.organism_name` only; `coculture_partner=` (already exists) covers the
partner-side filter; the two compose with AND.

**F3 — per-timepoint `growth_phase` on each timepoint dict.** The Cypher
already returns `time_point_growth_phases` as a list parallel to
`time_point_orders`, but the api-layer timepoint-assembly loop never
zips it onto the per-TP dicts. Consumers reaching for "what's the
growth phase at this TP?" via `experiments_to_dataframe` instead get
the experiment-level `" | "`-joined string copied identically onto every
TP row — silently wrong for any phase-filter downstream. The fix
zips per-TP, drops the redundant experiment-level field, and lets
`experiments_to_dataframe` flow the value through automatically.

## Out of Scope

- **Renaming the experiment-level `growth_phases` set field.** That
  field carries the deduped set of phases observed across the
  experiment; it remains useful for high-level summary and stays.
- **Touching `differential_expression_by_gene`'s per-TP wiring.** That
  query (`queries_lib.py:2459`) already includes growth_phase from the
  edge per TP — it's correct.
- **Adding a `partial_match=` boolean to `organism=`.** The CONTAINS
  semantics on `organism_name` (case-insensitive substring) is
  preserved. The OR-against-partner branch is the only thing dropped.
- **A new `any_organism=` parameter.** Anyone wanting the union still
  composes `organism=` and `coculture_partner=`, or makes two calls.
  No evidence of demand for the OR-shape today.
- **Cyanorak `D.3` / GO BP cell-death common-mistakes** (gaps_and_friction
  F4). Separate, smaller doc-only change.

## Status / Prerequisites

- [x] Scope reviewed with user (B-shape chosen for F2; F3 design
      approved 2026-04-28)
- [x] No KG schema changes needed (data already there)
- [x] Cypher / impact verified against live KG (see "KG verification" below)
- [x] Result-size controls: no new modes — existing `summary` / `verbose`
      / `limit` / `offset` semantics unchanged
- [ ] Ready for Phase 2 (build) — pending user spec sign-off

## Use cases

- **F2 fix.** Any analysis that scopes by organism via `list_experiments`
  intends "profiled organism" — this is the load-bearing meaning across
  all 8+ existing test call sites and every analysis to date. The
  partner-side leak surfaces only when a count check catches it.
- **F3 fix.** Within-condition trajectory analyses, axenic-vs-coculture
  comparisons, and any time-course analysis that needs to know the
  physiological phase at each measured TP (e.g., distinguishing
  `nutrient_limited` from `death` on calendar-shared timepoints in the
  axenic-vs-coculture analysis). Currently every such analysis must
  zip `result["results"][i]["timepoints"]` against
  `result["results"][i]["time_point_growth_phases"]` by index — an
  easy-to-miss step that yields a silently-wrong filter when skipped.

## KG dependencies

No schema changes. Reuses existing `Experiment` properties:
`organism_name`, `coculture_partner`, `time_point_orders`,
`time_point_growth_phases` (already returned by `build_list_experiments`
via `coalesce(e.time_point_growth_phases, [])`).

---

## Tool Signature (after change)

```python
@mcp.tool(
    tags={"experiments", "discovery"},
    annotations={"readOnlyHint": True, ...},
)
async def list_experiments(
    ctx: Context,
    organism: Annotated[str | None, Field(
        description=(
            "Filter to experiments where this organism is the profiled "
            "organism (case-insensitive substring on organism_name). "
            "For partner-side filtering, use coculture_partner=."
        ),
    )] = None,
    # ... all other params unchanged ...
) -> ListExperimentsResponse:
    ...
```

Param-surface changes are limited to `organism=`'s description. No new
or removed parameters.

**Return envelope:** unchanged (`total_entries, total_matching,
by_organism, by_treatment_type, by_background_factors, by_omics_type,
by_publication, by_table_scope, by_cluster_type, by_growth_phase,
by_value_kind, by_metric_type, by_compartment, time_course_count,
returned, truncated, not_found, results`).

**Per-result columns (compact)** — diff from today:

| Field | Before | After |
|---|---|---|
| `time_point_growth_phases` | list[str] (parallel to `time_point_orders`) | **removed** — value flows through `timepoints[].growth_phase` |
| `timepoints[].growth_phase` | absent | **new** — string per timepoint, sourced from `e.time_point_growth_phases[order-1]` |
| `growth_phases` | list[str] (deduped set) | unchanged |

All other compact and verbose fields unchanged.

## Result-size controls

No mode changes. Existing `summary` / `verbose` / `limit` / `offset`
semantics are unchanged.

**Sort key:** unchanged — `p.publication_year DESC, e.organism_name,
e.name` for the no-search path; `score DESC, e.organism_name, e.name`
when `search_text` is provided.

**Default limit:** unchanged.

**Verbose:** unchanged. Compact-vs-verbose split is identical to today
except `time_point_growth_phases` is removed entirely (not demoted to
verbose).

## Special handling

- **No caching.** Reads precomputed Experiment properties.
- **No KG roundtrip change.** F2 only narrows the WHERE clause; F3
  only adjusts the api-layer timepoint-assembly loop. Same number of
  Cypher queries.
- **Lucene retry on `search_text`** — unchanged.

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `_list_experiments_where`: drop the `OR ALL(...e.coculture_partner...)` half of the `organism` clause. |
| 2 | API function | `api/functions.py` | `list_experiments`: in the timepoint-assembly loop (≈L1041–1068), pop `time_point_growth_phases`, set `tp["growth_phase"] = tp_growth_phases[i] if i < len(tp_growth_phases) else None`. Remove the experiment-level `time_point_growth_phases` from the result dict. Update docstring. |
| 3 | DataFrame helper | `analysis/frames.py` | `experiments_to_dataframe`: in the per-TP record block, add `record["tp_growth_phase"] = tp.get("growth_phase")`. (No experiment-level field to strip — already gone.) |
| 4 | MCP wrapper | `mcp_server/tools.py` | `ListExperimentsResult`: remove `time_point_growth_phases` field. `TimepointSummary` (or whichever Pydantic model represents per-TP rows): add `growth_phase: str \| None` Field with description. Update `organism` Field description in the wrapper. |
| 5 | Inputs YAML | `inputs/tools/list_experiments.yaml` | Add a `mistakes` entry calling out the prior OR-semantics in case anyone has stale notes. Update example response if it shows `time_point_growth_phases`. |
| 6 | Unit tests | `tests/unit/test_query_builders.py` | `TestBuildListExperiments`: add a test asserting `organism="MED4"` Cypher contains exactly one `e.organism_name CONTAINS` substring and ZERO `e.coculture_partner` references. Update any existing assertion that expected the OR clause. |
| 7 | Unit tests | `tests/unit/test_api_functions.py` | `TestListExperiments`: add a test asserting per-TP `growth_phase` is populated when `time_point_growth_phases` is non-empty in the mocked Cypher result, and that the experiment-level `time_point_growth_phases` key is absent from `result["results"][i]`. |
| 8 | Unit tests | `tests/unit/test_tool_wrappers.py` | `TestListExperimentsWrapper`: assert the response model exposes `growth_phase` per timepoint; assert it does NOT expose `time_point_growth_phases` on the experiment. |
| 9 | Unit tests | `tests/unit/test_frames.py` (or wherever `experiments_to_dataframe` is tested) | Add: build a result with two TPs whose phases differ; assert `df["tp_growth_phase"]` differs across rows for the same experiment. |
| 10 | Integration | `tests/integration/test_mcp_tools.py` | Update existing `list_experiments(organism="MED4")` calls' count expectations if they were exact (they are `>= N` checks, so likely no change). Add a case: pick a known time-course experiment with phase-varying TPs (e.g., `..._med4_proteomics_axenic`), assert `result["results"][0]["timepoints"][0]["growth_phase"]` is non-null and the values vary across TPs. |
| 11 | Regression baselines | `tests/regression/test_regression/list_experiments_*.yml` | Regenerate all 9 baselines (`--force-regen -m kg`). The `_organism` and `_summary_organism` cases will return fewer rows; the others should be byte-identical except where `time_point_growth_phases` is removed and per-TP `growth_phase` appears. |
| 12 | Eval cases | `tests/evals/cases.yaml` | `list_experiments_organism` `min_rows: 10` still satisfies the new shape (live-KG: 39 rows). No change needed. (Optional: tighten `min_rows` to a value that would have caught the F2 leak — e.g. 35.) |
| 13 | About content | regenerate via `uv run python scripts/build_about_content.py list_experiments` after Pydantic + YAML edits |
| 14 | Docs | `CLAUDE.md` | Update the `list_experiments` row to reflect: (a) `organism=` is profiled-only, (b) per-TP `growth_phase` field on timepoint dicts. |

---

## Query Builder

**File:** `multiomics_explorer/kg/queries_lib.py`

### `_list_experiments_where` — `organism` clause change

**Before** (lines 1201–1208):

```python
if organism:
    conditions.append(
        "(ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(e.organism_name) CONTAINS word)"
        " OR ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(e.coculture_partner) CONTAINS word))"
    )
    params["organism"] = organism
```

**After:**

```python
if organism:
    conditions.append(
        "ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(e.organism_name) CONTAINS word)"
    )
    params["organism"] = organism
```

The space-split CONTAINS semantics is preserved (multi-word inputs like
`"Prochlorococcus MED4"` still match either order). Only the
partner-side OR is dropped.

`coculture_partner=` clause (lines 1238–1242) is unchanged; AND-combines
with `organism=` when both are passed.

`build_list_experiments` and `build_list_experiments_summary` both
inherit the change automatically (both share `_list_experiments_where`).
No RETURN-clause change needed for F2.

### KG verification (verified 2026-04-28)

| Query shape | Today | After (B-shape) |
|---|---|---|
| `organism="MED4"` row count | 48 | 39 |
| Of which: profiled-only | 39 | 39 |
| Of which: partner-only-MED4 (HOT1A3 profiled) | 9 | 0 (dropped) |
| `organism="MED4" AND coculture_partner="Alteromonas"` | filter combinatorics tested | composes correctly with AND |

(Counts from `mcp__multiomics-kg__run_cypher` 2026-04-28.)

---

## API Function

**File:** `multiomics_explorer/api/functions.py`

### `list_experiments` — timepoint assembly (F3)

**Before** (lines 1041–1068):

```python
# Assemble timepoints from parallel arrays
tp_count = r.pop("time_point_count", 0)
tp_labels = r.pop("time_point_labels", [])
tp_orders = r.pop("time_point_orders", [])
tp_hours = r.pop("time_point_hours", [])
tp_totals = r.pop("time_point_totals", [])
tp_sig_up = r.pop("time_point_significant_up", [])
tp_sig_down = r.pop("time_point_significant_down", [])

if r["is_time_course"] and tp_count > 0:
    timepoints = []
    for i in range(tp_count):
        tp_total = tp_totals[i]
        tp_up = tp_sig_up[i]
        tp_down = tp_sig_down[i]
        tp = {
            "timepoint": tp_labels[i] if tp_labels[i] != "" else None,
            "timepoint_order": tp_orders[i],
            "timepoint_hours": tp_hours[i] if tp_hours[i] != -1.0 else None,
            "gene_count": tp_total,
            "genes_by_status": {
                "significant_up": tp_up,
                "significant_down": tp_down,
                "not_significant": tp_total - tp_up - tp_down,
            },
        }
        timepoints.append(tp)
    r["timepoints"] = timepoints
# Non-time-course: omit timepoints key entirely
```

**After (additions in bold-equivalent comments):**

```python
# Assemble timepoints from parallel arrays
tp_count = r.pop("time_point_count", 0)
tp_labels = r.pop("time_point_labels", [])
tp_orders = r.pop("time_point_orders", [])
tp_hours = r.pop("time_point_hours", [])
tp_totals = r.pop("time_point_totals", [])
tp_sig_up = r.pop("time_point_significant_up", [])
tp_sig_down = r.pop("time_point_significant_down", [])
tp_growth_phases = r.pop("time_point_growth_phases", [])  # NEW: pop, do not retain at experiment level

if r["is_time_course"] and tp_count > 0:
    timepoints = []
    for i in range(tp_count):
        tp_total = tp_totals[i]
        tp_up = tp_sig_up[i]
        tp_down = tp_sig_down[i]
        tp = {
            "timepoint": tp_labels[i] if tp_labels[i] != "" else None,
            "timepoint_order": tp_orders[i],
            "timepoint_hours": tp_hours[i] if tp_hours[i] != -1.0 else None,
            "growth_phase": (                                       # NEW
                tp_growth_phases[i]
                if i < len(tp_growth_phases) and tp_growth_phases[i]
                else None
            ),
            "gene_count": tp_total,
            "genes_by_status": {
                "significant_up": tp_up,
                "significant_down": tp_down,
                "not_significant": tp_total - tp_up - tp_down,
            },
        }
        timepoints.append(tp)
    r["timepoints"] = timepoints
# Non-time-course: omit timepoints key entirely. tp_growth_phases is
# popped above so the experiment-level field never leaks into r.
```

The `pop` (rather than `get`) on `time_point_growth_phases` is the
mechanism that strips the experiment-level field from the response —
matches the existing pattern for `time_point_labels` etc.

### Docstring updates

- `organism:` → "Filter to experiments where this organism is the
  profiled organism (case-insensitive substring on `organism_name`)."
- Per-result list: replace `time_point_growth_phases` with
  `growth_phase` listed under "per timepoint dict" alongside
  `timepoint`, `timepoint_order`, `timepoint_hours`, `gene_count`,
  `genes_by_status`.

---

## DataFrame Helper

**File:** `multiomics_explorer/analysis/frames.py`

### `experiments_to_dataframe` (lines 84–144) — add per-TP growth phase

In the per-TP record-builder block (lines ≈120–130), add:

```python
record["tp_growth_phase"] = tp.get("growth_phase")
```

That's it — no experiment-level cleanup needed because the api-layer
fix already strips `time_point_growth_phases`. No change to the
non-time-course branch (lines 131–140); growth_phase is a per-TP
concept that doesn't apply.

Also update the module docstring's example column-list to include
`tp_growth_phase`.

---

## MCP Wrapper

**File:** `multiomics_explorer/mcp_server/tools.py`

### Pydantic models (diff)

`ExperimentResult` (per-experiment model, defined in
`register_tools()`-scope at `tools.py:1748`):
- **Remove** the `time_point_growth_phases: list[str] = Field(...)`
  field (currently at line 1769).

`TimePoint` (per-timepoint model, defined just above at
`tools.py:1742`):
- **Add** `growth_phase: str | None = Field(default=None,
  description="Growth phase observed at this timepoint (e.g.
  'nutrient_limited', 'death'). Null when not annotated.")`

### Wrapper signature

`organism` Field description (in the `@mcp.tool` decorator):

```python
organism: Annotated[str | None, Field(
    description=(
        "Filter to experiments where this organism is the profiled "
        "organism (case-insensitive substring on organism_name). "
        "For partner-side filtering, use coculture_partner=."
    ),
)] = None,
```

No other wrapper changes.

---

## Tests

### Unit: query builder (`tests/unit/test_query_builders.py`)

Extend `TestBuildListExperiments`:

```
test_organism_filter_is_profiled_only
    cypher, params = build_list_experiments(organism="MED4")
    # Exactly one CONTAINS clause referencing organism_name
    assert cypher.count("e.organism_name) CONTAINS") == 1
    # Zero references to coculture_partner via the organism clause
    # (coculture_partner test below covers the dedicated param)
    assert "e.coculture_partner) CONTAINS word" not in cypher
    assert params["organism"] == "MED4"

test_organism_and_coculture_partner_compose_with_and
    cypher, params = build_list_experiments(
        organism="MED4", coculture_partner="Alteromonas",
    )
    # Both filters present, joined with AND
    assert "organism_name" in cypher
    assert "coculture_partner" in cypher
    # Verify AND structure (no OR between them)
```

The existing `test_coculture_partner_filter` (test_query_builders.py:2212)
still covers the partner-only case.

### Unit: API function (`tests/unit/test_api_functions.py`)

Extend `TestListExperiments`:

```
test_per_tp_growth_phase_populated
    # Mock conn.execute_query to return a row with parallel arrays
    # including time_point_growth_phases=["nutrient_limited", "death", "death"]
    # Assert each result["results"][0]["timepoints"][i]["growth_phase"]
    # equals the expected value at index i.

test_experiment_level_time_point_growth_phases_absent
    # Same mock setup
    # Assert "time_point_growth_phases" NOT in result["results"][0]

test_growth_phase_none_when_array_short
    # Mock with time_point_count=3 but time_point_growth_phases=["a"]
    # Assert tp[1]["growth_phase"] is None and tp[2]["growth_phase"] is None
```

### Unit: MCP wrapper (`tests/unit/test_tool_wrappers.py`)

Extend `TestListExperimentsWrapper`:

```
test_per_tp_growth_phase_in_response_model
    # Build a stub response dict with timepoints carrying growth_phase
    # Wrap via the tool wrapper, assert response.results[0].timepoints[0].growth_phase
    # equals the input.

test_experiment_level_time_point_growth_phases_field_absent
    # Verify ListExperimentsResult schema no longer has the field.
```

`EXPECTED_TOOLS` already lists `list_experiments` — no change.

### Unit: DataFrame helper (`tests/unit/test_frames.py` or equivalent)

```
test_experiments_to_dataframe_emits_tp_growth_phase
    # Build a result dict with one experiment, two TPs
    # whose timepoints[].growth_phase differs
    # Assert df["tp_growth_phase"] differs across rows for the same experiment_id

test_experiments_to_dataframe_tp_growth_phase_none_for_non_time_course
    # Non-time-course experiment → single row with tp_growth_phase=None
```

### Integration (`tests/integration/test_mcp_tools.py`)

Existing `list_experiments(organism="MED4")` calls (lines 410, 444,
1152, 1181, 1200, 1221) all use `>=` comparisons or full-list checks —
verify each still passes when 9 partner-only experiments drop. None
appears to assert exact counts; spot-check during build.

Add new case: pick a time-course experiment known to have phase-varying
TPs (e.g., `..._med4_proteomics_axenic` with phases `nutrient_limited |
death | death`):

```
def test_list_experiments_per_tp_growth_phase(conn):
    result = api.list_experiments(
        experiment_ids=["...med4_proteomics_axenic..."],
        conn=conn,
    )
    timepoints = result["results"][0]["timepoints"]
    assert timepoints[0]["growth_phase"] == "nutrient_limited"
    assert timepoints[1]["growth_phase"] == "death"
    # Experiment-level field absent
    assert "time_point_growth_phases" not in result["results"][0]
```

### Regression (`tests/regression/test_regression.py`)

`TOOL_BUILDERS` entries for `list_experiments` and
`list_experiments_summary` are already present (lines 80–81). No code
change. Regenerate all 9 baselines:

```bash
pytest tests/regression/ -k list_experiments --force-regen -m kg
pytest tests/regression/ -k list_experiments -m kg   # verify clean
```

The `_organism` and `_summary_organism` baselines will reflect the
new lower row count (39 vs 48). The other 7 baselines should differ
only in the per-TP `growth_phase` shape change.

### Eval cases (`tests/evals/cases.yaml`)

No mandatory change. `list_experiments_organism` `min_rows: 10` still
holds (39 rows after change). Optional: tighten to `min_rows: 35` to
catch any future regression that re-introduces the OR-leak.

---

## About Content

**File:** `multiomics_explorer/inputs/tools/list_experiments.yaml`

Add to `mistakes`:

```yaml
- "`organism=` filters the profiled organism only (case-insensitive substring on `organism_name`). It does NOT match coculture partners — for partner-side filtering use `coculture_partner=`. Prior versions OR'd the two; if you have notes from earlier sessions assuming the OR-semantics, the count will now be lower."

- wrong: "result['results'][0]['time_point_growth_phases']"
  right: "result['results'][0]['timepoints'][i]['growth_phase']"
```

If the existing example response shows `time_point_growth_phases`, update
it to show the per-TP `growth_phase` field instead.

Then regenerate:

```bash
uv run python scripts/build_about_content.py list_experiments
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | `list_experiments` row in the MCP-tools table: change the description so `organism=` is described as profiled-only, and call out per-TP `growth_phase`. Specifically: drop any wording that suggests organism matches partner; add "Per timepoint: `growth_phase` (str \| None)." Mirror the existing wording style. |
| `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/to_dataframe.md` | If this file documents `experiments_to_dataframe`'s columns, add `tp_growth_phase` to the per-TP-row column list. |
| `tests/regression/test_regression/list_experiments_*.yml` (×9) | Regenerated by `--force-regen` in the regression step above. Not hand-edited. |
