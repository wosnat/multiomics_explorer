# A3 Enrichment Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Default `informative_only=True` on `pathway_enrichment` + `cluster_enrichment` and surface `is_informative: bool` per result row, matching Cluster A2 parity.

**Architecture:** Mode B (cross-tool small change) per the `add-or-update-tool` skill. Phase 2 is a single test-updater dispatch (RED), then 4 parallel implementers (GREEN, file-owned), then code review + 3 pytest gates + 1 regression rebaseline (VERIFY). Spec is frozen at `docs/superpowers/specs/2026-05-04-a3-enrichment-defaults-design.md` (commit `afcadf8`) — adding fields, removing parameters, or changing query architecture during build requires re-approval.

**Tech Stack:** Python 3.11, Pydantic v2, FastMCP 3.x, Neo4j (KG), pytest, uv.

---

## File structure

Files touched in this plan, by layer:

| Layer | File | Nature |
|---|---|---|
| KG | `kg/queries_lib.py` | None (already supports the filter + emits the column) |
| Analysis | `analysis/enrichment.py` | None (`fisher_ora` auto-passes through term2gene non-key columns) |
| API | `api/functions.py` (`pathway_enrichment`, `cluster_enrichment`) | Add `informative_only: bool = True` param; thread to `genes_by_ontology(...)`; record in `result.params` |
| MCP wrapper | `mcp_server/tools.py` (2 wrappers) | Add `Annotated[bool, Field(default=True, ...)]` param; thread through |
| MCP schema | `mcp_server/tools.py::PathwayEnrichmentResult` (line 28), `ClusterEnrichmentResult` (line 267) | Add `is_informative: bool` field after `level` |
| About-content | `inputs/tools/pathway_enrichment.yaml`, `inputs/tools/cluster_enrichment.yaml` | Param doc + default-flip mistake entry + chaining link to `enrichment.md` |
| About-content | `skills/multiomics-kg-guide/references/analysis/enrichment.md` | New `## Informative-only filtering` section |
| Examples | `examples/pathway_enrichment.py` | New `demo_informative_only()` block |
| Top-level docs | `CLAUDE.md` | `[ENR]` markers + footnote |
| Tests | `tests/unit/test_query_builders.py`, `test_api_functions.py`, `test_tool_wrappers.py` | New `Test*InformativeOnly*` classes per layer |
| Test fixtures | `tests/fixtures/*.py`, `tests/unit/test_tool_correctness.py`, `tests/unit/test_api_contract.py` | Cross-file fixture cascade for new required `is_informative` field |
| Regression | `tests/regression/test_regression/pathway_enrichment_med4_cyanorak_level1_10exp.yml` | `--force-regen` (default-True drops uninformative-flagged term rows) |

---

## Task 1: Set up worktree and baseline branch check

**Files:**
- No code changes; orchestration only.

- [ ] **Step 1: Create isolated worktree (optional but recommended for parallel agent work)**

Per `superpowers:using-git-worktrees`. From the repo root:

```bash
git fetch origin
git worktree list
# If a previous a3-enrichment-defaults worktree exists, remove it first:
# git worktree remove --force ../multiomics_explorer-a3 2>/dev/null
# git branch -D a3-enrichment-defaults 2>/dev/null
git worktree add -b a3-enrichment-defaults ../multiomics_explorer-a3 main
cd ../multiomics_explorer-a3
```

Expected: new worktree at `../multiomics_explorer-a3` on branch `a3-enrichment-defaults` based on `main`.

- [ ] **Step 2: Verify the worktree branch HEAD matches main HEAD**

Per the add-or-update-tool skill: `EnterWorktree` re-uses an existing branch by name if one already exists; a stale branch can leave you on an outdated base. Verify:

```bash
git log --oneline -1
# In another terminal (or with -C path) on the original repo:
git -C /home/osnat/github/multiomics_explorer log --oneline -1 main
```

Expected: both show the same commit (currently `afcadf8 docs(spec): A3 enrichment defaults …`).

If they differ:

```bash
git reset --hard main
git log --oneline -1   # confirm match
```

- [ ] **Step 3: Confirm clean working tree + record starting state**

```bash
git status -s        # expect empty
pytest tests/unit/ -q --tb=no | tail -5
```

Expected: empty `git status`. All unit tests green (record the count for later comparison).

- [ ] **Step 4: Commit the worktree marker (no-op safe-point)**

Skip — no commit yet, the worktree is just a base for the next tasks.

---

## Task 2: Stage 1 RED — dispatch test-updater agent

**Files:** dispatch only — agent will modify multiple test/fixture files.

- [ ] **Step 1: Dispatch the test-updater agent with the brief below**

Use the Agent tool with `subagent_type: test-updater`. Brief:

```
You are the test-updater for A3 enrichment defaults.

FROZEN SPEC: docs/superpowers/specs/2026-05-04-a3-enrichment-defaults-design.md
(commit afcadf8). Read it before writing tests.

YOUR JOB: Write failing tests across the 3 layered test files + extend
cross-file fixtures so existing tests still pass after the new required
Pydantic field lands. Do NOT implement any production code.

EXPECTED FILES TO MODIFY:
1. tests/unit/test_query_builders.py — add TestPathwayEnrichmentBuilderInformativeOnly,
   TestClusterEnrichmentBuilderInformativeOnly. These verify the api → genes_by_ontology
   threading via mocks; the builders themselves are unchanged.
2. tests/unit/test_api_functions.py — add TestPathwayEnrichmentInformativeOnly,
   TestClusterEnrichmentInformativeOnly with cases:
     a) default informative_only=True excludes uninformative term rows
     b) informative_only=False includes them
     c) result.params["informative_only"] is recorded with the requested value
     d) is_informative column present in result.results DataFrame
   Use mocked genes_by_ontology returns with mixed informative/uninformative rows.
3. tests/unit/test_tool_wrappers.py — add TestPathwayEnrichmentInformativeOnlyWrapper,
   TestClusterEnrichmentInformativeOnlyWrapper. Cases: MCP wrapper threads informative_only;
   is_informative field present on per-row Pydantic models; field is required.
4. tests/fixtures/*.py — extend any fixture constructing PathwayEnrichmentResult /
   ClusterEnrichmentResult to include is_informative=True. Pydantic will fail without it.
5. tests/unit/test_tool_correctness.py — if _SAMPLE_API_RETURN for either tool is
   constructed inline, extend per-row dicts with is_informative.
6. tests/unit/test_api_contract.py — update expected_keys for result.params (new
   informative_only key in both tools).

EXPECTED EXISTING TESTS (do not modify, just be aware):
- tests/unit/test_tool_wrappers.py:3858 / 3902 already iterate
  PathwayEnrichmentResult.model_fields and ClusterEnrichmentResult.model_fields. These
  will automatically cover Field(description=...) requirements on the new is_informative
  field once the api-updater adds it; you do not need to add a new test for that.

ANTI-SCOPE-CREEP GUARDRAIL: ADD only — do NOT modify, rename, or rebaseline any
existing test, case, or yml. If an unrelated test fails in your environment, REPORT
AS A CONCERN; do not silently retune. Pinned baselines are KG-state guards.

EXPECTED PASS/FAIL AFTER YOUR WORK:
- New Test*InformativeOnly* classes RED (fail because api/wrapper code doesn't exist yet).
- All other existing tests still GREEN (fixture cascade keeps them passing).
- Regression and integration tests are NOT touched in this stage.

REPORT: DONE / DONE_WITH_CONCERNS / BLOCKED per superpowers:subagent-driven-development.
Include `pytest tests/unit/ -q --tb=no | tail -10` output in your report.
```

- [ ] **Step 2: Review the agent's diff**

```bash
git diff --stat
git diff tests/
```

Expected: only `tests/` files modified. New test classes named exactly as specified above.

- [ ] **Step 3: Run unit tests to verify the RED state is exactly what we want**

```bash
pytest tests/unit/ -q --tb=line 2>&1 | tail -30
```

Expected:
- New `Test*InformativeOnly*` classes FAIL (api/wrapper code doesn't exist yet).
- All other tests PASS (fixture cascade keeps them passing).

If any unrelated unit test is red, halt and investigate — likely a fixture cascade miss.

- [ ] **Step 4: Commit the RED tests**

```bash
git add tests/
git commit -m "$(cat <<'EOF'
test(a3): RED tests for enrichment informative_only + is_informative

A3 Stage 1: failing tests across 3 layered test files plus fixture
cascade for the new required is_informative Pydantic field.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Stage 2 GREEN — dispatch 4 implementer agents in parallel

**Files:** dispatch only — each agent owns a different file.

- [ ] **Step 1: Dispatch all 4 implementers in ONE message (parallel)**

Use the Agent tool with 4 simultaneous tool calls in one assistant message. Each agent gets its own brief. The 4 agents:

**Agent A — query-builder (no-op confirmation):**

```
subagent_type: query-builder

You own kg/queries_lib.py for A3.

FROZEN SPEC: docs/superpowers/specs/2026-05-04-a3-enrichment-defaults-design.md

EXPECTED OUTCOME: NO CODE CHANGES. The spec confirms kg/queries_lib.py
already supports informative_only on the genes_by_ontology builders that
pathway_enrichment / cluster_enrichment internally invoke, and detail
rows already emit is_informative.

YOUR JOB: Verify by reading the spec + grep for `informative_only` and
`is_informative` in kg/queries_lib.py. Confirm no changes are needed.

REPORT: DONE / DONE_WITH_CONCERNS / BLOCKED. If you detect that the spec's
"no changes" claim is wrong (e.g. a builder is missing the param), report
DONE_WITH_CONCERNS and stop — do NOT attempt the fix; surface to the orchestrator.

ANTI-SCOPE-CREEP: Do not modify any file. Do not rename anything. If you
think a refactor would help, report it as a concern; do not act.
```

**Agent B — api-updater:**

```
subagent_type: api-updater

You own api/functions.py and analysis/*.py for A3.

FROZEN SPEC: docs/superpowers/specs/2026-05-04-a3-enrichment-defaults-design.md

YOUR JOB: Make the RED tests in tests/unit/test_api_functions.py and
tests/unit/test_query_builders.py (the api → builder threading tests)
GREEN. Specifically:

1. api/functions.py::pathway_enrichment (line 4270): add
   `informative_only: bool = True` parameter. Thread it to the internal
   genes_by_ontology(...) call (currently around line 4363 — pass
   informative_only=informative_only). Record it in result.params dict.

2. api/functions.py::cluster_enrichment (line 4455): same shape — add
   the same param, thread to internal genes_by_ontology call, record in
   result.params.

3. Implement as a parallel small change: pathway_enrichment is the
   template; cluster_enrichment follows the same pattern within the same file.

4. analysis/enrichment.py: NO CHANGES. fisher_ora already auto-passes
   through term2gene non-key columns (lines 367-374), so is_informative
   flows automatically once it's in the term2gene DataFrame.

ANTI-SCOPE-CREEP: ADD only — do NOT modify, rename, or rebaseline any
existing test, case, or yml. If an unrelated test fails in your environment,
REPORT AS A CONCERN; do not silently retune. Pinned baselines are KG-state guards.

SCOPED SELF-VERIFY:
  pytest tests/unit/test_api_functions.py -q -k "Enrichment"
  pytest tests/unit/test_query_builders.py -q -k "Enrichment"
Both should be green when you finish.

REPORT: DONE / DONE_WITH_CONCERNS / BLOCKED with the self-verify output.
```

**Agent C — tool-wrapper:**

```
subagent_type: tool-wrapper

You own mcp_server/tools.py for A3.

FROZEN SPEC: docs/superpowers/specs/2026-05-04-a3-enrichment-defaults-design.md

YOUR JOB: Make the RED tests in tests/unit/test_tool_wrappers.py
(Test*InformativeOnlyWrapper) GREEN. Specifically:

1. PathwayEnrichmentResult (line 28): add `is_informative: bool` field
   AFTER the `level` field (around line 73). Required field (not Optional).
   Use this Field description verbatim from the spec:
     "True if the term is not flagged is_uninformative in the KG. Always
      present, regardless of informative_only setting, so callers can
      post-filter or diagnose. With default informative_only=True, all
      rows have is_informative=True by construction; pass
      informative_only=False to opt out and see uninformative terms."

2. ClusterEnrichmentResult (line 267): add the same `is_informative: bool`
   field after `level` with the same Field description.

3. Wrapper tools.py::pathway_enrichment (line 5543): add
   `informative_only: Annotated[bool, Field(default=True, description=...)]`
   parameter to the wrapper signature. Thread to the internal
   api.pathway_enrichment(...) call. Use this description verbatim:
     "When True (default), exclude ontology terms flagged uninformative
      in the KG (e.g. KEGG map00001 'metabolic pathways', GO root
      go:0008150). Term-side filter — never restricts the gene set,
      background, or DE inputs. Pass False to include uninformative
      terms; per-row is_informative still surfaces in either mode."

4. Wrapper tools.py::cluster_enrichment (line 5666): same shape, same
   description.

5. Implement as a parallel small change: pathway_enrichment is the
   template; cluster_enrichment follows the same pattern within the same file.

ANTI-SCOPE-CREEP: ADD only — do NOT modify, rename, or rebaseline any
existing test, case, or yml. If an unrelated test fails in your environment,
REPORT AS A CONCERN; do not silently retune. Pinned baselines are KG-state guards.

SCOPED SELF-VERIFY:
  pytest tests/unit/test_tool_wrappers.py -q -k "Enrichment"
Both new wrapper test classes plus the existing Pydantic-introspection
tests should be green.

REPORT: DONE / DONE_WITH_CONCERNS / BLOCKED with the self-verify output.
```

**Agent D — doc-updater:**

```
subagent_type: doc-updater

You own inputs/tools/*.yaml, skills/.../analysis/*.md, examples/*.py,
and CLAUDE.md for A3.

FROZEN SPEC: docs/superpowers/specs/2026-05-04-a3-enrichment-defaults-design.md

YOUR JOB: Update human-authored about-content + regenerate generated md.
Specifically:

1. inputs/tools/pathway_enrichment.yaml — add:
   - new param doc for `informative_only` referencing default=True and
     "term-side filter only" semantics
   - new mistake entry under `mistakes`: "Caller pinning row counts
     from pre-2026-05 runs sees fewer rows by default. Pass
     informative_only=False to restore old behavior, or accept the new
     default (recommended)."
   - in the chaining/related section, link to the analysis doc:
     skills/multiomics-kg-guide/references/analysis/enrichment.md
   - DO NOT add is_informative under verbose_fields — it is a required
     compact-tier field, auto-documented from the Pydantic Field description.

2. inputs/tools/cluster_enrichment.yaml — same shape as above, parallel
   small change.

3. skills/multiomics-kg-guide/references/analysis/enrichment.md — add a
   new top-level section `## Informative-only filtering (default 2026-05)`
   covering: rationale (uninformative term noise in Fisher tests),
   term-side-only semantics (no impact on gene set / background / DE inputs),
   Fisher denominator behavior (denominator is informative-only term set
   when default), opt-out guidance (`informative_only=False`), KG drift
   caveat (if KG flags shift, prior runs become non-reproducible — pin
   via param when reproducibility matters).

4. examples/pathway_enrichment.py — add a new demo block named
   `demo_informative_only()`. It should run the same pathway_enrichment
   call once with `informative_only=True` (default) and once with
   `informative_only=False`. Print `len(result.results)` for each, and
   print `result.results[["term_id","term_name","is_informative","p_adjust"]].head(10)`
   for the False-run to surface the column. Add a docstring explaining
   the side-by-side pattern. Wire it into the bottom of the file's main
   block alongside the existing demos.

5. CLAUDE.md — in the MCP-tools table, add `[ENR]` markers to the
   `pathway_enrichment` and `cluster_enrichment` rows. Add a footnote at
   the bottom of the table (analogous to the existing `[AQ]` footnote):
     "`[ENR]` Default `informative_only=True` as of 2026-05 release —
      uninformative terms (e.g. KEGG map00001 'metabolic pathways', GO
      root go:0008150) excluded by default. Pass `informative_only=False`
      to opt out. Per-row `is_informative` surfaced for diagnosis."

6. After YAML edits, regenerate generated md:
     uv run python scripts/build_about_content.py

ANTI-SCOPE-CREEP: ADD only — do NOT modify, rename, or rebaseline any
existing test, case, or yml. Do not edit any other YAML or md beyond
the four listed above (plus CLAUDE.md). If you find a typo or stale
note in unrelated content, REPORT AS A CONCERN; do not fix.

SCOPED SELF-VERIFY:
  uv run python scripts/build_about_content.py
  git diff --stat
Expect: 2 YAMLs, 1 analysis md, 1 example py, CLAUDE.md, and exactly 2
generated tool md files (pathway_enrichment.md, cluster_enrichment.md
under skills/multiomics-kg-guide/references/tools/) modified.

REPORT: DONE / DONE_WITH_CONCERNS / BLOCKED with the self-verify output.
```

- [ ] **Step 2: Wait for all 4 agents to report**

Each should report `DONE` (or `DONE_WITH_CONCERNS` with details). If any agent reports `BLOCKED`, halt and resolve before proceeding.

- [ ] **Step 3: Run the full unit suite**

```bash
pytest tests/unit/ -q --tb=line 2>&1 | tail -20
```

Expected: all tests green, including the new `Test*InformativeOnly*` classes.

If anything is red:
- Cross-file fixture miss → return to test-updater (Task 2) brief, surface the missed fixture, re-dispatch test-updater for that file.
- Implementer bug → return to the relevant implementer with the failing-test output as additional brief.

- [ ] **Step 4: Commit Stage 2 GREEN**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/mcp_server/tools.py multiomics_explorer/inputs/tools/pathway_enrichment.yaml multiomics_explorer/inputs/tools/cluster_enrichment.yaml multiomics_explorer/skills/multiomics-kg-guide/ examples/pathway_enrichment.py CLAUDE.md
git commit -m "$(cat <<'EOF'
feat(a3): enrichment informative_only default-True + is_informative on rows

A3 Stage 2: add informative_only=True default to pathway_enrichment and
cluster_enrichment; surface is_informative per result row on both
Pydantic envelopes. analysis/enrichment.py untouched — fisher_ora's
term2gene auto-passthrough carries the new column.

About-content: param doc + default-flip mistake entry on both YAMLs;
new informative-only-filtering section in enrichment.md;
demo_informative_only() side-by-side block in examples; [ENR] markers
in CLAUDE.md tool table.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Stage 3 VERIFY — code review (background)

**Files:** dispatch only.

- [ ] **Step 1: Dispatch the code-reviewer subagent in the background**

Per the add-or-update-tool skill: this is a HARD GATE, not optional. Mocked
unit tests can't validate actual Cypher; only the reviewer reading the live
code catches things like wrong threading, wrong default values, or filters
that match-everything.

Use the Agent tool with `subagent_type: superpowers:code-reviewer` and
`run_in_background: true`. Brief:

```
Review the diff on branch a3-enrichment-defaults against:
  docs/superpowers/specs/2026-05-04-a3-enrichment-defaults-design.md (commit afcadf8)

Focus areas (in order):
1. Correctness of informative_only threading: api → genes_by_ontology call
   actually receives the param (not silently dropped); MCP wrapper actually
   passes it to the api function (not bound to a different default at the
   wrapper layer).
2. is_informative field placement and Field description match the spec
   verbatim. Required (not Optional).
3. Pydantic auto-passthrough: confirm the column actually appears in
   result.results, not just declared on the model. fisher_ora at
   analysis/enrichment.py:367-374 should be the carry-through path —
   verify it's not bypassed.
4. About-content drift: YAML param descriptions should match the wrapper
   Field descriptions. CLAUDE.md footnote present and correctly formatted.
5. Fixture cascade: any places constructing PathwayEnrichmentResult /
   ClusterEnrichmentResult that didn't get is_informative=True will fail
   Pydantic validation at runtime. Look for missed sites.
6. Anti-scope-creep: any unrelated test or yml edits? Any baseline
   regenerations outside of Stage 3 (Task 6)? If so, flag.

Report findings as CRITICAL / IMPORTANT / NIT.
```

The agent runs in background; continue with the foreground gates while it works.

---

## Task 5: Stage 3 VERIFY — foreground pytest gates

**Files:** no edits — gates only.

- [ ] **Step 1: Unit suite (foreground)**

```bash
pytest tests/unit/ -q --tb=short 2>&1 | tail -10
```

Expected: all green.

- [ ] **Step 2: Integration suite (foreground, requires Neo4j at localhost:7687)**

```bash
pytest tests/integration/ -m kg -q --tb=short 2>&1 | tail -10
```

Expected: all green. If a KG-side change is needed, integration tests will catch it here (mocks won't).

- [ ] **Step 3: If unit + integration green, proceed to regression. If not, halt and investigate.**

Halt criteria:
- Any test red → either an implementer bug (re-dispatch with the output as additional brief) or a Cypher correctness issue the code-reviewer should also catch (wait for the review report).

---

## Task 6: Stage 3 VERIFY — regression rebaseline

**Files:**
- Modify: `tests/regression/test_regression/pathway_enrichment_med4_cyanorak_level1_10exp.yml`

- [ ] **Step 1: Snapshot row count of current baseline**

```bash
grep -c "^- " tests/regression/test_regression/pathway_enrichment_med4_cyanorak_level1_10exp.yml
```

Record the count for comparison.

- [ ] **Step 2: Regenerate the baseline**

```bash
pytest tests/regression/test_regression/test_regression.py -m kg -q --force-regen 2>&1 | tail -10
```

Expected: regen succeeds. The pathway_enrichment baseline rebuilds.

- [ ] **Step 3: Verify the rebaselined file is consistent**

```bash
pytest tests/regression/ -m kg -q --tb=short 2>&1 | tail -10
git diff --stat tests/regression/
grep -c "^- " tests/regression/test_regression/pathway_enrichment_med4_cyanorak_level1_10exp.yml
```

Expected:
- Regression suite green.
- Diff shows the one baseline file modified.
- New row count equal-or-fewer than before (default-True drops uninformative-flagged term rows). If the new count is HIGHER, that's unexpected and needs investigation — possibly a Cypher correctness bug.

- [ ] **Step 4: Inspect the diff manually**

```bash
git diff tests/regression/test_regression/pathway_enrichment_med4_cyanorak_level1_10exp.yml | head -80
```

Look for: rows removed (any term whose `is_informative: false` would have appeared), `is_informative: true` on remaining rows, no other unexpected changes (e.g. p-value drift in unrelated rows would suggest a bug).

- [ ] **Step 5: Commit the rebaselined file**

```bash
git add tests/regression/test_regression/pathway_enrichment_med4_cyanorak_level1_10exp.yml
git commit -m "$(cat <<'EOF'
test(a3): regenerate pathway_enrichment regression baseline

Default informative_only=True now drops uninformative-flagged term rows
from the baseline. Remaining rows all carry is_informative=true.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Address code-reviewer findings (if any)

**Files:** depends on the review.

- [ ] **Step 1: Read the code-reviewer report**

When the background agent reports back, review findings.

- [ ] **Step 2: Branch on severity**

- **CRITICAL or IMPORTANT findings:** re-dispatch the relevant implementer agent (per Stage 2 brief shape) with the review feedback as additional brief. Re-run all 3 pytest gates (Task 5) + regression check (Task 6 step 3) after the fix.

- **NIT only:** address inline if trivial; otherwise capture as a follow-up todo and proceed.

- **No findings:** skip to Task 8.

- [ ] **Step 3: Commit any fixes**

```bash
git add -p     # review each hunk
git commit -m "fix(a3): address code-review findings

<list findings addressed>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
"
```

---

## Task 8: Verify before claiming done

**Files:** no edits.

- [ ] **Step 1: Run all 3 pytest gates one more time as the final verification**

```bash
pytest tests/unit/ -q --tb=no | tail -3
pytest tests/integration/ -m kg -q --tb=no | tail -3
pytest tests/regression/ -m kg -q --tb=no | tail -3
```

Expected: all three lines end in `passed` with no failures or errors.

- [ ] **Step 2: Verify the spec acceptance criteria**

Walk the spec's "Decisions locked" table and "Layer touch summary" table; confirm every change shipped:

- [ ] `informative_only: bool = True` on `api.pathway_enrichment` — verify with `grep -n "informative_only" multiomics_explorer/api/functions.py`
- [ ] `informative_only: bool = True` on `api.cluster_enrichment` — same grep
- [ ] `informative_only` Annotated param on both MCP wrappers — `grep -n "informative_only" multiomics_explorer/mcp_server/tools.py`
- [ ] `is_informative` field on `PathwayEnrichmentResult` and `ClusterEnrichmentResult` — `grep -n "is_informative" multiomics_explorer/mcp_server/tools.py`
- [ ] `[ENR]` markers + footnote in `CLAUDE.md` — `grep -n "ENR" CLAUDE.md`
- [ ] Mistake entry in both YAMLs — `grep -n "informative_only" multiomics_explorer/inputs/tools/pathway_enrichment.yaml multiomics_explorer/inputs/tools/cluster_enrichment.yaml`
- [ ] `Informative-only filtering` section in `enrichment.md` — `grep -n "Informative-only" multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md`
- [ ] `demo_informative_only()` block in example — `grep -n "demo_informative_only" examples/pathway_enrichment.py`
- [ ] Regression baseline regenerated — `git log --oneline -3`

- [ ] **Step 3: Confirm clean working tree**

```bash
git status -s
```

Expected: empty.

---

## Task 9: Branch close + PR

**Files:** no edits.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin a3-enrichment-defaults
```

- [ ] **Step 2: Open the PR via gh**

```bash
gh pr create --title "feat(cluster-a3): enrichment informative_only=True + is_informative on rows" --body "$(cat <<'EOF'
## Summary

- Default `informative_only=True` on `pathway_enrichment` + `cluster_enrichment` (parity with `ontology_landscape` from Cluster A2).
- New `is_informative: bool` field on `PathwayEnrichmentResult` + `ClusterEnrichmentResult` per result row (parity with browse/discovery surfaces).
- About-content + example + `[ENR]` flag in CLAUDE.md surface the default-flip behavior loudly (analogous to the Cluster A1 `[AQ]` pattern).
- `analysis/enrichment.py` untouched — `fisher_ora`'s term2gene auto-passthrough carries the new column without code change.
- Closes A3 of the explorer surface refresh queue (Cluster A1+A2 merged 2026-05-04 in `8bbbcbb`).

## Test plan

- [ ] All unit tests pass (new `Test*InformativeOnly*` classes + existing tests)
- [ ] All integration tests pass (`-m kg`)
- [ ] Regression baseline `pathway_enrichment_med4_cyanorak_level1_10exp.yml` regenerated; row count equal-or-fewer; remaining rows all `is_informative: true`
- [ ] Code review by `superpowers:code-reviewer` returned clean (or findings addressed inline)

Spec: `docs/superpowers/specs/2026-05-04-a3-enrichment-defaults-design.md`
Plan: `docs/superpowers/plans/2026-05-04-a3-enrichment-defaults.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Save outcome to memory**

After PR is merged, update memory file `project_explorer_surface_refresh_paused.md` to reflect A3 shipped, and create a fresh `project_a3_shipped.md` capturing any lessons (parallel to `project_cluster_a_shipped.md`). Use the same shape: what landed, lessons, what's still queued.

---

## Self-review

**Spec coverage check:**
- Default `informative_only=True` on both tools → Task 3 (api-updater + tool-wrapper)
- `is_informative` per-row → Task 3 (tool-wrapper Pydantic models + auto-passthrough)
- About-content updates (2 YAMLs + enrichment.md + example + CLAUDE.md) → Task 3 (doc-updater)
- 3 layered tests + fixture cascade → Task 2 (test-updater) and verified in Task 3 step 3 + Task 5
- Regression rebaseline → Task 6
- Code review hard gate → Task 4
- Out of scope items (no `cluster_enrichment` baseline, no `fisher_ora` changes, no background gene-set logic, other clusters) → not in any task ✓

**Placeholder scan:** No TBD/TODO/"implement later". Each step shows the actual command or brief content.

**Type consistency:** `informative_only` and `is_informative` used consistently throughout. Field name (snake_case) matches the spec.

**Mode B briefing distinction:** All 4 implementer agents get the "treat as parallel small change vs. template-extend" framing — pathway_enrichment is the template, cluster_enrichment follows.

**Anti-scope-creep:** Embedded in every Stage 2 implementer brief verbatim, plus a final cross-check in Task 4 step 1 (code-review focus area #6).
