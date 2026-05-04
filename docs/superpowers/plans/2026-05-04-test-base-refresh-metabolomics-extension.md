# Test-base refresh — metabolomics-extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh the test base so the suite is green against the metabolomics-extension KG without absorbing real regressions, and add three positive guard-rail tests pinning the new schema behaviors.

**Architecture:** Sequential layer-by-layer triage. Each phase classifies its failures, fixes them, and appends to a change-report markdown before moving on. `--force-regen` runs only after phases 1–5 are zero-failure. Tools/queries/api untouched per scope posture B.

**Tech Stack:** pytest, pytest-regressions, Neo4j (bolt://localhost:7687), Cypher, YAML.

**Spec:** [docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-design.md](../specs/2026-05-04-test-base-refresh-metabolomics-extension-design.md)

**KG-side reference:** [multiomics_biocypher_kg/docs/kg-changes/metabolomics-extension.md](../../../../multiomics_biocypher_kg/docs/kg-changes/metabolomics-extension.md)

---

## File map

**Created:**
- `tests/integration/test_metabolomics_extension_invariants.py` — 3 guard-rail tests pinning new schema behaviors
- `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md` — change report (sibling of design doc)

**Modified (likely):**
- `multiomics_explorer/kg/constants.py` — if new omics types / cluster types / etc. enter the KG (extension doc says no, but phase 1 checks)
- `tests/integration/test_kg_constants_drift.py` — only if a constant in this file (the `EXPECTED_STATUSES` set on `TestExpressionConstants`) drifts; otherwise the existing tests assert against `kg/constants.py`
- `tests/integration/test_tool_correctness_kg.py` — assertion edits per phase 4
- `tests/integration/test_mcp_tools.py` — assertion edits per phase 4
- `tests/integration/test_api_contract.py` — only if envelope shape regressed (shouldn't, no tool changes)
- `tests/integration/test_about_examples.py` — example assertion edits per phase 4
- `tests/integration/test_param_edge_cases.py` — assertion edits per phase 4
- `tests/integration/test_examples.py` — assertion edits per phase 4
- `tests/integration/test_analysis.py` — assertion edits per phase 4
- `tests/evals/cases.yaml` — `row0` / `contains` / `columns` edits per phase 5
- `tests/regression/test_regression/*.yml` — bulk regen via `--force-regen`, classified per phase 6

**Branch:** `refresh/test-base-metabolomics-extension` (off `main`).

---

### Task 0: Branch setup and report scaffold

**Files:**
- Create: `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md`

- [ ] **Step 1: Create branch off main**

```bash
git checkout -b refresh/test-base-metabolomics-extension
```

- [ ] **Step 2: Verify Neo4j has new KG loaded**

Run: `uv run python scripts/validate_connection.py 2>&1 | grep -E 'MetaboliteAssay|All checks passed'`
Expected: line containing `MetaboliteAssay: <count>` (count > 0) and `All checks passed.`

If `MetaboliteAssay` count is 0 or absent, **STOP** — the new KG isn't loaded. Surface to user.

- [ ] **Step 3: Scaffold the change report**

Create `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md` with:

```markdown
# Test-base refresh report — metabolomics-extension

**Branch:** refresh/test-base-metabolomics-extension
**KG build:** verified loaded with MetaboliteAssay node type ([N] nodes)
**Started:** 2026-05-04
**Spec:** [2026-05-04-test-base-refresh-metabolomics-extension-design.md](2026-05-04-test-base-refresh-metabolomics-extension-design.md)

## Phase 0: Baseline failure surface

_To be filled after Task 1._

## Phase 1: Schema drift

_To be filled after Task 2._

## Phase 2: Unit tests

_To be filled after Task 3._

## Phase 3: CyVer

_To be filled after Task 4._

## Phase 4: Integration correctness

_To be filled after Task 5._

## Phase 5: Eval cases

_To be filled after Task 6._

## Phase 6: Regression baselines

_To be filled after Task 7._

## Phase 7: Guard rails added

_To be filled after Task 8._

## Phase 8: Final verification

_To be filled after Task 9._

## Open follow-ups (out of scope)

_To be filled at end._
```

Replace `[N]` with the actual MetaboliteAssay count from step 2.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md
git commit -m "chore(test-refresh): scaffold change report for metabolomics-extension refresh"
```

---

### Task 1: Phase 0 — Baseline failure snapshot

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md` (Phase 0 section)

- [ ] **Step 1: Run full suite, capture failure surface (do not fix)**

```bash
mkdir -p /tmp/test-refresh-logs
uv run pytest tests/ 2>&1 | tee /tmp/test-refresh-logs/phase0-baseline.log
```

Note: this run will likely have many failures. **Do not fix anything yet.** The point is to capture the unfiltered failure surface as ground truth.

- [ ] **Step 2: Summarize failures by file**

Run:

```bash
grep -E "^FAILED" /tmp/test-refresh-logs/phase0-baseline.log | awk -F'::' '{print $1}' | sort | uniq -c | sort -rn
```

- [ ] **Step 3: Append to report**

Replace the Phase 0 section in the report with:

```markdown
## Phase 0: Baseline failure surface

Captured from `pytest tests/` against new KG, no fixes applied.

**Total failures:** [N]
**Failures by file:**
| File | Failure count |
|---|---|
| tests/integration/test_kg_constants_drift.py | [N] |
| tests/integration/test_tool_correctness_kg.py | [N] |
| ... | ... |

**Errors (collection / import):** [N — from "ERROR" not "FAILED" lines]

Log: `/tmp/test-refresh-logs/phase0-baseline.log`
```

Fill in the table from the actual output.

- [ ] **Step 4: Commit the report update**

```bash
git add docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md
git commit -m "chore(test-refresh): phase 0 — baseline failure surface captured"
```

---

### Task 2: Phase 1 — Schema drift (constants)

**Files:**
- Modify: `multiomics_explorer/kg/constants.py` (only if drift surfaces undocumented additions)
- Modify: `tests/integration/test_kg_constants_drift.py` (only if `TestExpressionConstants.EXPECTED_STATUSES` drifts)
- Modify: `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md` (Phase 1 section)

- [ ] **Step 1: Run drift tests**

```bash
uv run pytest tests/integration/test_kg_constants_drift.py -m kg -v 2>&1 | tee /tmp/test-refresh-logs/phase1-drift.log
```

- [ ] **Step 2: For each failure, classify against the metabolomics-extension doc**

Per spec §4 phase 1: a failure is acceptable only if the new value is documented in `metabolomics-extension.md`. The extension doc adds:

- New node label `MetaboliteAssay` (not in any drift constant — additive, not asserted by an exhaustive set)
- New edges (not asserted by drift constants)
- New compartment `extracellular` — **not in `kg/constants.py`** (compartments aren't asserted there); but `Experiment` validation now uses `extracellular`. The drift test does not currently assert compartment vocab, so likely no failure here.
- New organism `MIT0801` — not asserted by drift constants
- No new omics type, no new cluster type, no new OG source/level

**Expected:** drift tests should pass as-is. The new entities are additive node/edge labels and properties, not changes to the asserted constants (`VALID_OG_SOURCES`, `VALID_TAXONOMIC_LEVELS`, `MAX_SPECIFICITY_RANK`, `VALID_CLUSTER_TYPES`, `VALID_OMICS_TYPES`, `EXPECTED_STATUSES`, `ONTOLOGY_CONFIG`).

If any drift test fails:
- Read the drift message — it shows `Missing from constant: {…}` or `Extra in constant (not in KG): {…}`.
- If `Missing` is documented in metabolomics-extension.md, add it to the constant in `kg/constants.py`.
- If `Missing` is NOT documented, **STOP** — flag in report and surface to user.
- If `Extra` exists, the KG dropped a value (unexpected). Flag in report and surface.

- [ ] **Step 3: Re-run and confirm green**

```bash
uv run pytest tests/integration/test_kg_constants_drift.py -m kg -v
```

Expected: PASS.

- [ ] **Step 4: Append to report**

Replace Phase 1 section with:

```markdown
## Phase 1: Schema drift

**Failures observed:** [N]

[For each failure, one row:]
| Test | Drift message | Resolution | Documented in extension doc? |
|---|---|---|---|
| ... | ... | ... | yes/no |

**Files modified:** [list, or "none"]

**Result:** all drift tests green.
```

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/kg/constants.py tests/integration/test_kg_constants_drift.py docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md
git commit -m "chore(test-refresh): phase 1 — schema drift constants synced with metabolomics-extension"
```

If no files were modified except the report, the commit message becomes:
`chore(test-refresh): phase 1 — schema drift confirmed clean (additive only)`

---

### Task 3: Phase 2 — Unit tests

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md` (Phase 2 section)

- [ ] **Step 1: Run unit tests**

```bash
uv run pytest tests/unit/ -v 2>&1 | tee /tmp/test-refresh-logs/phase2-unit.log
```

- [ ] **Step 2: Inspect failures**

Unit tests are designed to be data-independent (mocks, no Neo4j). If any unit test fails, the cause is one of:

a. A unit test imports a constant from `kg/constants.py` whose value just changed in Phase 1 — update the test's mock data or expected value.
b. A unit test exercises a query builder whose Cypher structure changed (shouldn't happen — out of scope).
c. A genuine code bug.

**For (a):** edit the unit test to match the new constant. Document.
**For (b) and (c):** STOP. Surface to user — these are tool-layer changes, out of scope.

- [ ] **Step 3: Re-run and confirm green**

```bash
uv run pytest tests/unit/ -v
```

Expected: PASS.

- [ ] **Step 4: Append to report**

```markdown
## Phase 2: Unit tests

**Failures observed:** [N]

[Per failure:]
| Test | Cause | Resolution |
|---|---|---|
| ... | ... | ... |

**Files modified:** [list, or "none"]

**Result:** all unit tests green.
```

- [ ] **Step 5: Commit**

```bash
git add tests/unit/ docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md
git commit -m "chore(test-refresh): phase 2 — unit tests verified green"
```

---

### Task 4: Phase 3 — CyVer

**Files:**
- Modify: `tests/integration/test_cyver_queries.py` (only if a new map-projection key needs adding to `_KNOWN_MAP_KEYS`)
- Modify: `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md` (Phase 3 section)

- [ ] **Step 1: Run CyVer tests**

```bash
uv run pytest tests/integration/test_cyver_queries.py -m kg -v 2>&1 | tee /tmp/test-refresh-logs/phase3-cyver.log
```

- [ ] **Step 2: Inspect failures**

CyVer validates each query builder's Cypher against the live schema. Failure modes:

a. **Unknown property / label / relationship in builder Cypher** — the builder references something that doesn't exist. Out of scope (tool change). STOP and surface.

b. **Unknown map-projection key flagged as alias** — the builder projects a property like `g{.measured_assay_count}`, which CyVer can't resolve. Add the key name to `_KNOWN_MAP_KEYS` in `tests/integration/test_cyver_queries.py`. **Only if a builder already projects it** — we're not adding new projections.

For our scope, (a) shouldn't happen (no builder changes in this branch). (b) is also unlikely because builders aren't projecting new metabolomics fields. The expected outcome is **green**.

- [ ] **Step 3: Re-run and confirm green**

```bash
uv run pytest tests/integration/test_cyver_queries.py -m kg -v
```

Expected: PASS.

- [ ] **Step 4: Append to report**

```markdown
## Phase 3: CyVer

**Failures observed:** [N]

[Per failure:]
| Builder / test | Failure | Resolution |
|---|---|---|
| ... | ... | ... |

**Files modified:** [list, or "none"]

**Result:** all CyVer tests green.
```

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_cyver_queries.py docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md
git commit -m "chore(test-refresh): phase 3 — CyVer verified green"
```

---

### Task 5: Phase 4 — Integration correctness

**Files:**
- Modify: any of `tests/integration/test_tool_correctness_kg.py`, `test_mcp_tools.py`, `test_api_contract.py`, `test_about_examples.py`, `test_param_edge_cases.py`, `test_examples.py`, `test_analysis.py`
- Modify: `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md` (Phase 4 section)

- [ ] **Step 1: Run integration correctness tests**

```bash
uv run pytest \
  tests/integration/test_tool_correctness_kg.py \
  tests/integration/test_mcp_tools.py \
  tests/integration/test_api_contract.py \
  tests/integration/test_about_examples.py \
  tests/integration/test_param_edge_cases.py \
  tests/integration/test_examples.py \
  tests/integration/test_analysis.py \
  -m kg -v 2>&1 | tee /tmp/test-refresh-logs/phase4-integration.log
```

- [ ] **Step 2: For each failure, choose a fix strategy in priority order**

For every failure:

1. **Rebind to a stable reference** (preferred). Examples:
   - `assert result["total"] == 12` → `assert "PMM1714" in {r["locus_tag"] for r in result["rows"]}`
   - `assert len(by_organism) == 5` → `assert "prochlorococcus_med4" in by_organism`
   - `assert top_metabolites[0]["id"] == "kegg:C00001"` → `assert any(m["id"] == "kegg:C00001" for m in top_metabolites)`

2. **Loosen `==` to `>=`** (fallback only). Document explicitly.
   - `assert total == 12` → `assert total >= 12  # was 12 pre-metabolomics-extension; expanded by data drift / materialization expansion`

3. **Update the value to the new exact value** (only if the test is intentionally pinning a precise count and that count is still meaningful).

4. **API contract tests** (`test_api_contract.py`) — these capture *shape* (keys, types), not values. They should NOT fail. If one does, the envelope shape regressed. STOP and surface — out of scope.

5. **About-examples** (`test_about_examples.py`) — these run examples from `inputs/tools/*.yaml`. If an example assertion fails, fix the assertion *in the YAML* (not the example query itself). Regenerate the about-content:

```bash
uv run python scripts/build_about_content.py
```

- [ ] **Step 3: Re-run and confirm green**

```bash
uv run pytest \
  tests/integration/test_tool_correctness_kg.py \
  tests/integration/test_mcp_tools.py \
  tests/integration/test_api_contract.py \
  tests/integration/test_about_examples.py \
  tests/integration/test_param_edge_cases.py \
  tests/integration/test_examples.py \
  tests/integration/test_analysis.py \
  -m kg -v
```

Expected: PASS.

- [ ] **Step 4: Append to report**

```markdown
## Phase 4: Integration correctness

**Failures observed:** [N]

| Test | Failure mode | Fix strategy | Diff class |
|---|---|---|---|
| test_tool_correctness_kg.py::test_X | hardcoded count `==12` failed (got 14) | rebound to `"PMM1714" in result` | data_drift |
| ... | ... | ... | ... |

**Loosenings (fallback `>=`):** [N — list each, with reason]

**Files modified:** [list]

**Result:** all integration correctness tests green.
```

- [ ] **Step 5: Commit**

```bash
git add tests/integration/ multiomics_explorer/inputs/tools/ multiomics_explorer/skills/multiomics-kg-guide/references/tools/ docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md
git commit -m "chore(test-refresh): phase 4 — integration assertions rebound to stable references"
```

---

### Task 6: Phase 5 — Eval cases

**Files:**
- Modify: `tests/evals/cases.yaml`
- Modify: `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md` (Phase 5 section)

- [ ] **Step 1: Run eval tests**

```bash
uv run pytest tests/evals/test_eval.py -m kg -v 2>&1 | tee /tmp/test-refresh-logs/phase5-evals.log
```

- [ ] **Step 2: For each failing case, edit cases.yaml**

Eval cases assert one or more of:
- `columns: [...]` — exact list of returned columns
- `row0: {key: value, ...}` — first row content
- `contains: {...}` — subset assertions

For each failure:
- If `columns` mismatch: a tool returned a new column → **out of scope (tool change), STOP**. If the column was *removed* by something we changed in earlier phases, update the list.
- If `row0` mismatch: data drift changed the top row. Either rebind to `contains`, or pin to a deterministic row by adding a more specific filter to the case.
- If `contains` mismatch: refresh the expected subset.

- [ ] **Step 3: Re-run and confirm green**

```bash
uv run pytest tests/evals/test_eval.py -m kg -v
```

Expected: PASS.

- [ ] **Step 4: Append to report**

```markdown
## Phase 5: Eval cases

**Failures observed:** [N]

| Case ID | Failure mode | Fix |
|---|---|---|
| ... | ... | ... |

**Files modified:** [tests/evals/cases.yaml]

**Result:** all eval cases green.
```

- [ ] **Step 5: Commit**

```bash
git add tests/evals/cases.yaml docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md
git commit -m "chore(test-refresh): phase 5 — eval cases refreshed for metabolomics-extension data"
```

---

### Task 7: Phase 6 — Regression baselines (the bulk diff)

**Files:**
- Modify: `tests/regression/test_regression/*.yml` (149 files, bulk regen)
- Modify: `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md` (Phase 6 section)

- [ ] **Step 1: Verify pre-state — phases 0–5 all green**

```bash
uv run pytest tests/ --ignore=tests/regression/ -v
```

Expected: all green (or skips for unavailable Neo4j features). If any fail, **STOP** — return to the appropriate earlier phase.

- [ ] **Step 2: Snapshot pre-regen baselines**

```bash
git status tests/regression/test_regression/
```

Expected: clean (no uncommitted YAML changes from earlier phases).

- [ ] **Step 3: Force-regen all baselines**

```bash
uv run pytest tests/regression/ -m kg --force-regen 2>&1 | tee /tmp/test-refresh-logs/phase6-regen.log
```

- [ ] **Step 4: Inspect what changed**

```bash
git diff --stat tests/regression/test_regression/ | tee /tmp/test-refresh-logs/phase6-diff-stat.txt
```

This gives a one-line-per-baseline summary: filename + line counts changed.

- [ ] **Step 5: Classify every changed baseline**

For each baseline with non-zero diff:

```bash
git diff tests/regression/test_regression/<filename>.yml
```

Apply the rubric from spec §5:

| Class | Trigger to look for in the diff |
|---|---|
| `data_drift` | Counts grew (e.g., `total: 100` → `total: 117`); new gene IDs / locus tags in lists |
| `materialization_expansion` | New rows in `genes_by_metabolite_*.yml` / `metabolites_by_gene_*.yml`; affected organisms have measurement-only edges |
| `new_compartment` | `extracellular` appears in `compartments_observed`, `by_compartment`, `compartments` |
| `new_organism` | `MIT0801` (or `prochlorococcus_mit0801`) appears in `by_organism`, `top_organisms`, `organism_names` |
| `evidence_source_extension` | `evidence_sources` arrays now include `"metabolomics"` or `"measured"` |
| `unclassified` | None of the above explains the diff |

A baseline can have multiple classes. **Any baseline that's `unclassified` after this triage requires escalation — DO NOT commit until classified.**

- [ ] **Step 6: Build the per-baseline classification table**

For each non-empty diff, fill one row of the table in the report. A pragmatic approach: iterate through the file list from step 4, examine each diff, append a row.

**If the per-baseline list is too long to enumerate exhaustively** (e.g., > 100 changed baselines), the report can group by class:

```markdown
### Group: data_drift only ([N] baselines)

These all have count growths and/or new gene IDs proportional to the documented load:
- list_publications_*.yml: publication count grew from 38 → 41
- list_organisms_*.yml: organism count grew from 36 → 37 (+ MIT0801)
- ...

### Group: materialization_expansion ([N] baselines)
- genes_by_metabolite_*.yml: row counts grew due to Organism_has_metabolite measurement-path edges
- metabolites_by_gene_*.yml: same
- ...

### Group: new_organism ([N] baselines)
- ...

### Group: unclassified ([N] baselines)
**Each one listed individually with diff fragments — these are escalation candidates.**
```

- [ ] **Step 7: If any unclassified diff exists, STOP**

Surface the unclassified list to the user. Do not proceed to step 8 without resolution. The user will either:
- Reclassify (e.g., "that's actually data drift — the count just looks wrong because…")
- Identify a real regression (then we re-scope)

- [ ] **Step 8: Re-run baselines without `--force-regen` to confirm reproducibility**

```bash
uv run pytest tests/regression/ -m kg
```

Expected: PASS (regenerated baselines match next run).

- [ ] **Step 9: Append to report**

```markdown
## Phase 6: Regression baselines

**Total baselines:** 149
**Unchanged:** [N]
**Changed:** [N]

### Class breakdown
| Class | Count |
|---|---|
| data_drift only | [N] |
| materialization_expansion | [N] |
| new_compartment | [N] |
| new_organism | [N] |
| evidence_source_extension | [N] |
| multi-class | [N] |
| unclassified | 0 (all resolved) |

### Per-group detail
[as described in step 6]

### Reproducibility check
Final `pytest tests/regression/ -m kg` (no `--force-regen`): PASS
```

- [ ] **Step 10: Commit**

```bash
git add tests/regression/test_regression/ docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md
git commit -m "chore(test-refresh): phase 6 — regression baselines refreshed and classified"
```

---

### Task 8: Phase 7 — Guard rails (the only TDD work in this plan)

**Files:**
- Create: `tests/integration/test_metabolomics_extension_invariants.py`
- Modify: `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md` (Phase 7 section)

- [ ] **Step 1: Write the failing test file**

Create `tests/integration/test_metabolomics_extension_invariants.py`:

```python
"""Positive invariants pinning the metabolomics-extension KG schema.

If any of these tests fails, the KG has reverted to a state without
the metabolomics-extension's documented behaviors:

  - MetaboliteAssay node type
  - Organism_has_metabolite measurement-only path materialization
  - Metabolite.evidence_sources tagging with "metabolomics"

See docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-design.md.
"""

import pytest

pytestmark = pytest.mark.kg


def test_metabolite_assay_nodes_present(run_query):
    """MetaboliteAssay node type loaded with at least one node."""
    rows = run_query("MATCH (m:MetaboliteAssay) RETURN count(m) AS n")
    assert rows[0]["n"] > 0, (
        "No MetaboliteAssay nodes found. The metabolomics-extension introduces "
        "this node type via the metabolite_assay_adapter — its absence means the "
        "KG was rebuilt without the extension."
    )


def test_organism_has_metabolite_measured_path_materialized(run_query):
    """Organism_has_metabolite edges include the measurement-only path.

    The extension's post-import step materializes Organism_has_metabolite
    edges for any (Organism, Metabolite) pair connected by a MetaboliteAssay,
    even with no gene-catalysis or gene-transport path. Each such edge
    carries 'measured' in its evidence_sources array.
    """
    rows = run_query(
        "MATCH ()-[r:Organism_has_metabolite]-() "
        "WHERE 'measured' IN coalesce(r.evidence_sources, []) "
        "RETURN count(r) AS n"
    )
    assert rows[0]["n"] > 0, (
        "No Organism_has_metabolite edges with 'measured' in evidence_sources. "
        "The materialization expansion documented in metabolomics-extension.md "
        "did not run, or the post-import step regressed."
    )


def test_metabolite_metabolomics_evidence_tag_present(run_query):
    """Metabolite.evidence_sources tagging includes 'metabolomics'."""
    rows = run_query(
        "MATCH (m:Metabolite) "
        "WHERE 'metabolomics' IN coalesce(m.evidence_sources, []) "
        "RETURN count(m) AS n"
    )
    assert rows[0]["n"] > 0, (
        "No Metabolite nodes have 'metabolomics' in evidence_sources. "
        "The extension's evidence_sources tagging on paper-measured metabolites "
        "did not run, or the post-import step regressed."
    )
```

- [ ] **Step 2: Run the new tests — confirm they pass against current KG**

```bash
uv run pytest tests/integration/test_metabolomics_extension_invariants.py -m kg -v
```

Expected: 3 PASS.

(Note: this is "test passes by inspection" rather than canonical TDD red-green. The KG already has the loaded state, so the invariants are satisfied. The TDD value is that *if the KG ever regresses to pre-extension*, these tests fail loudly. To verify they would catch a regression, do step 3.)

- [ ] **Step 3: Sanity-check each test catches its intended regression (mental model)**

Read each test. Confirm:
- Test 1 would fail if `MetaboliteAssay` node type didn't exist (count=0).
- Test 2 would fail if `Organism_has_metabolite` edges had no `'measured'` evidence (count=0).
- Test 3 would fail if `Metabolite.evidence_sources` never contained `'metabolomics'` (count=0).

No code changes here — just verify by reading.

- [ ] **Step 4: Append to report**

```markdown
## Phase 7: Guard rails added

New file: `tests/integration/test_metabolomics_extension_invariants.py`

| Test | Pins | Failure-mode if KG regresses |
|---|---|---|
| test_metabolite_assay_nodes_present | MetaboliteAssay node type loaded | Count = 0 → FAIL |
| test_organism_has_metabolite_measured_path_materialized | measurement-only Organism_has_metabolite edges | Count = 0 → FAIL |
| test_metabolite_metabolomics_evidence_tag_present | 'metabolomics' tagging on Metabolite.evidence_sources | Count = 0 → FAIL |

All 3 PASS against current KG.
```

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_metabolomics_extension_invariants.py docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md
git commit -m "test(integration): pin metabolomics-extension invariants

Three positive Cypher assertions catching regression to pre-extension
KG: MetaboliteAssay nodes, Organism_has_metabolite measurement-path
edges, Metabolite.evidence_sources='metabolomics' tagging."
```

---

### Task 9: Phase 8 — Final verification + report finalize

**Files:**
- Modify: `docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md` (Phase 8 + follow-ups sections)

- [ ] **Step 1: Run full suite**

```bash
time uv run pytest tests/ -v 2>&1 | tee /tmp/test-refresh-logs/phase8-final.log
```

Expected: all PASS (ignoring legitimate skips for missing Neo4j features).

- [ ] **Step 2: Capture summary line**

```bash
grep -E "passed|failed|error" /tmp/test-refresh-logs/phase8-final.log | tail -5
```

Expected last line shape: `===== N passed, M skipped in T s =====` with no `failed` or `error`.

- [ ] **Step 3: If anything failed, STOP**

Surface to user. Do not declare done.

- [ ] **Step 4: Finalize the report**

Replace Phase 8 section:

```markdown
## Phase 8: Final verification

```
[paste final pytest summary line]
```

**Duration:** [from `time` output]
**Status:** all green
```

Replace "Open follow-ups" section with:

```markdown
## Open follow-ups (out of scope)

These were deferred per spec §8 and merit separate specs:

- **Surface measurement evidence in tool outputs.** `list_metabolites` doesn't filter by `evidence_sources='measured'`. `Metabolite.measured_assay_count` / `measured_organisms` / `measured_paper_count` aren't projected. `Experiment.metabolite_count` and `Publication.metabolite_count` aren't projected.
- **`MetaboliteAssay` discovery surface.** No tool currently lists, filters, or queries `MetaboliteAssay` nodes.
- **`genes_by_metabolite` / `metabolites_by_gene` materialization-aware filtering.** The expansion now mixes paths with different semantics (catalysis, transport, measurement). A future tool revision may want an `evidence_sources` filter (e.g., `evidence_sources=['metabolism', 'transport']` to restore pre-extension semantics).
- **Sentinel biological-truth assertions** (option C from brainstorming). A curated set of "known answers" (e.g., known KEGG annotations for canonical genes) as integration tests independent of count drift.

Each item above should get its own spec via `superpowers:brainstorming` when prioritized.
```

- [ ] **Step 5: Commit final report**

```bash
git add docs/superpowers/specs/2026-05-04-test-base-refresh-metabolomics-extension-report.md
git commit -m "chore(test-refresh): phase 8 — final green run, follow-ups documented"
```

- [ ] **Step 6: Surface branch state to user**

Print summary:
- Branch name
- Commit count on branch
- Total tests passed
- Number of regression baselines changed (from phase 6)
- Number of guard rails added (3)
- Link to report

Do NOT push or open a PR — that's the user's call.

---

## Self-review

After plan completion, verify:

- [ ] Spec coverage: every numbered section in the design doc maps to a task
  - §1 Context → Task 0 step 2 (KG verification)
  - §2 Why this matters → encoded in phase ordering rationale
  - §3 Risk → encoded in Task 7's pre-state check (step 1)
  - §4 Process flow → Tasks 1–9 (one per phase)
  - §5 Diff classification → Task 7 step 5
  - §6 Guard rails → Task 8
  - §7 Change report → scaffolded in Task 0, filled per-phase
  - §8 Out of scope → enforced via STOP-and-surface in each phase
  - §9 Deliverables → Tasks 0, 7, 8, 9
  - §10 Branch posture → Task 0 step 1
  - §11 Risks → mitigations encoded in phase ordering and STOP gates

- [ ] No placeholders other than `[N]` value-fillers in report templates (intentional — the values come from runtime output)

- [ ] Type/identifier consistency:
  - `run_query` fixture (not `conn.execute_query`) used in guard-rail tests — matches `tests/conftest.py` and `test_kg_constants_drift.py` style
  - `pytestmark = pytest.mark.kg` placed at module level — matches existing convention
  - File path `test_metabolomics_extension_invariants.py` consistent across spec, plan, and code blocks
  - Report path `2026-05-04-test-base-refresh-metabolomics-extension-report.md` consistent everywhere

- [ ] Each phase commits independently so the change-report can reference commit hashes if needed

- [ ] No phase forces user-facing escalations through (every phase has explicit STOP gates for out-of-scope conditions)
