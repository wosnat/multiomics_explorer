# Phase 2 — Cross-cutting renames + filter additions: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land 4 cross-cutting Phase 2 items (search→search_text rename, top_pathways→top_metabolite_pathways rename, exclude_metabolite_ids filter addition on 3 tools, direction='both' option on DE) cleanly on top of Phase 1.

**Architecture:** Mode B parallel build per `add-or-update-tool` skill — 4 file-owned implementer agents dispatched in one message at Stage 2 GREEN, after Stage 1 RED test-updater seeds failing tests. 4-layer architecture (kg/queries_lib.py, api/functions.py, mcp_server/tools.py, inputs/tools/*.yaml) with tests across unit/integration/regression. Pure renames + additive filter — no aggregation logic shifts, no semantic behavior changes.

**Tech Stack:** Python 3.11, uv, pytest, fastmcp 3.x, Pydantic v2, neo4j-driver, Cypher (live KG @ localhost:7687).

**Spec (frozen, source of truth):** [docs/tool-specs/2026-05-05-phase2-cross-cutting-renames.md](../../tool-specs/2026-05-05-phase2-cross-cutting-renames.md). All decisions locked in §9 of the spec; do not adapt mid-build. Re-approval required if any item slips.

**Roadmap context:** [docs/superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md](../specs/2026-05-05-metabolites-surface-refresh-roadmap.md) — Phase 2 of 5.

---

## File Structure

| Layer | File | Owner agent | Items touched |
|---|---|---|---|
| Query builders | `multiomics_explorer/kg/queries_lib.py` | `query-builder` | 1 (search_text param rename), 2 (RETURN-alias rename in 2 summary builders), 3 (NOT-IN block in 5 WHERE helpers), 4 (new branch in `_differential_expression_where`) |
| API | `multiomics_explorer/api/functions.py` | `api-updater` | 1 (kwarg rename), 3 (3 signatures), 4 (validator + signature) |
| API exports | `multiomics_explorer/api/__init__.py`, `multiomics_explorer/__init__.py` | `api-updater` | None (no new top-level functions) |
| MCP wrappers + Pydantic | `multiomics_explorer/mcp_server/tools.py` | `tool-wrapper` | 1 (Annotated rename), 2 (4 Pydantic field renames + 2 envelope keys), 3 (3 Annotated additions), 4 (Literal extension) |
| About-content YAMLs | `inputs/tools/{list_metabolites,metabolites_by_gene,genes_by_metabolite,differential_expression_by_gene}.yaml` | `doc-updater` | All 4 items |
| Tool table + examples | `CLAUDE.md`, `multiomics_explorer/examples/metabolites.py` | `doc-updater` | 1 (call-site update), 2 (tool table refs), 3 (tool table refs), 4 (tool table refs) |
| Tests — unit query builder | `tests/unit/test_query_builders.py` | `test-updater` (RED stage) | All 4 items |
| Tests — unit API | `tests/unit/test_api_functions.py` | `test-updater` (RED stage) | All 4 items |
| Tests — unit wrapper | `tests/unit/test_tool_wrappers.py` | `test-updater` (RED stage) | All 4 items |
| Tests — integration | `tests/integration/test_mcp_tools.py`, `tests/integration/test_api_contract.py` | `test-updater` (RED stage) — and api-updater for 2 line-1298/1326 call-site updates | Items 1, 3, 4 |
| Regression baseline | `tests/regression/` (fixture files regenerated) | Plan owner (run `--force-regen`) | Items 2, 4 (envelope/branch shape changes) |

---

## Prerequisites (gate before starting)

### Phase 1 dependency

Phase 2 builds on top of Phase 1's surface. Phase 1 is currently in flight on worktree `metabolites-phase1-plumbing`. **Do not start Phase 2 build until Phase 1 has merged to main.**

- [ ] **Verify Phase 1 has landed.**

```bash
git -C /home/osnat/github/multiomics_explorer fetch origin
git -C /home/osnat/github/multiomics_explorer log --oneline main | head -20 | grep -iE 'phase.1|pass.through|metabolites.refresh' || echo "PHASE 1 NOT YET MERGED — HALT"
```

Expected: at least one commit referencing Phase 1 / pass-through-plumbing on main. If output is `PHASE 1 NOT YET MERGED — HALT`, stop and wait.

- [ ] **Capture post-Phase-1 main HEAD.**

```bash
git -C /home/osnat/github/multiomics_explorer rev-parse main
```

Record this SHA as the Phase 2 baseline. The implementation plan's anchor patterns (function names, surrounding code) replace the spec's line-number references which were pre-Phase-1.

---

## Task 0: Worktree + baseline

**Files:** No code changes; environment setup only.

- [ ] **Step 1: Create Phase 2 worktree.**

```bash
cd /home/osnat/github/multiomics_explorer
git worktree add .claude/worktrees/metabolites-phase2-renames -b worktree-metabolites-phase2-renames main
cd .claude/worktrees/metabolites-phase2-renames
```

Expected: new worktree at `.claude/worktrees/metabolites-phase2-renames` on branch `worktree-metabolites-phase2-renames`, branched from main.

- [ ] **Step 2: Verify worktree HEAD == main HEAD.**

```bash
git log --oneline -1
git -C /home/osnat/github/multiomics_explorer log --oneline -1 main
```

Expected: identical SHAs. Per `add-or-update-tool` skill: "EnterWorktree re-uses existing branch by name if one already exists, so a stale branch surviving from a previous session can leave you on an outdated base." If they differ, `git reset --hard main` (safe — fresh worktree, no work) and re-baseline.

- [ ] **Step 3: Sanity check — pytest baseline green.**

```bash
uv run pytest tests/unit/ -q --tb=no 2>&1 | tail -20
```

Expected: all green. Any unrelated red here means the post-Phase-1 main is broken — halt and surface to user.

- [ ] **Step 4: Commit worktree-setup checkpoint (no code yet, just the branch baseline).**

No commit needed at this step — branch baseline is implicit in the merge-base with main.

---

## Task 1: Stage 1 RED — Failing tests written by `test-updater` agent

**Files (additions only — no rebaselining):**
- Modify: `tests/unit/test_query_builders.py`
- Modify: `tests/unit/test_api_functions.py`
- Modify: `tests/unit/test_tool_wrappers.py` (incl. `EXPECTED_TOOLS` registry update)
- Modify: `tests/integration/test_mcp_tools.py` (KG round-trip cases for items 1, 3, 4)
- Modify: `tests/integration/test_api_contract.py` (lines for `search=` → `search_text=` on `list_metabolites` calls — anchor: search for `list_metabolites(search=`)

- [ ] **Step 1: Dispatch `test-updater` agent.**

```
Agent({
  description: "Phase 2 RED — failing tests for 4 items",
  subagent_type: "test-updater",
  prompt: <see brief below>
})
```

**Brief content for `test-updater`:**

```
You are writing RED-stage failing tests for Phase 2 of the metabolites surface refresh. The frozen spec is at docs/tool-specs/2026-05-05-phase2-cross-cutting-renames.md — read it in full before writing tests.

Your scope is the test files only. Do NOT touch any non-test file. Do NOT modify any existing test that is not directly affected by a Phase 2 rename. ADD tests; only RENAME existing test calls where the spec explicitly says so (e.g., `search=` → `search_text=` in TestListMetabolites and TestApiContract).

Items to cover:

1. Item 1 — search→search_text rename:
   - Update existing TestListMetabolites tests at tests/unit/test_api_functions.py (rename kwarg in test_lucene_retry_on_parse_error and test_search_empty_validation calls).
   - Update tests/integration/test_api_contract.py (the 2 list_metabolites(search=...) call sites).
   - Add TestBuildListMetabolites.test_search_text_param_threads asserting builder accepts search_text= kwarg and produces the expected fulltext-index Cypher.

2. Item 2 — top_pathways → top_metabolite_pathways rename + element-key renames:
   - Add TestBuildListMetabolitesSummary.test_top_metabolite_pathways_alias asserting RETURN aliases include 'metabolite_pathway_id', 'metabolite_pathway_name', 'top_metabolite_pathways'.
   - Add TestBuildMetabolitesByGeneSummary.test_top_metabolite_pathways_alias mirror.
   - Update TestListMetabolites._SUMMARY_ROW mock fixture (top_pathways → top_metabolite_pathways; pathway_id → metabolite_pathway_id; pathway_name → metabolite_pathway_name).
   - Update test_returns_dict_envelope assertion to "top_metabolite_pathways" in out.
   - Mirror for TestMetabolitesByGene.
   - Pydantic validation tests in test_tool_wrappers.py: TestListMetabolitesWrapper.test_top_metabolite_pathways_field, mirror for metabolites_by_gene.

3. Item 3 — exclude_metabolite_ids filter:
   - Add test_exclude_metabolite_ids_filter to TestBuildListMetabolites + TestBuildListMetabolitesSummary asserting:
     (a) generated Cypher contains "(NOT (m.id IN $exclude_metabolite_ids))" — note the parens (CyVer false-positive on unparenthesized form, see spec §6.3);
     (b) params["exclude_metabolite_ids"] is set;
     (c) when both metabolite_ids and exclude_metabolite_ids are passed, both clauses appear AND-joined.
   - Mirror for genes_by_metabolite (both arms — _genes_by_metabolite_metabolism_where AND _genes_by_metabolite_transport_where).
   - Mirror for metabolites_by_gene (both arms).
   - Add test_exclude_metabolite_ids_passed mock-driver tests in test_api_functions.py for all 3 tools.
   - Add Pydantic param-validation tests in test_tool_wrappers.py for all 3 tools.
   - KG-integration test in test_mcp_tools.py: pass exclude list of 5 cofactors (kegg.compound: prefix per spec worked example: C00002, C00008, C00004, C00005, C00001) and assert their rows drop out.

4. Item 4 — direction='both' on DE:
   - Add TestBuildDifferentialExpressionByGene.test_direction_both_filter asserting Cypher contains "r.expression_status IN ['significant_up', 'significant_down']".
   - Add test_direction_both_returns_both_statuses mock-driver test in TestDifferentialExpressionByGene.
   - Add TestDifferentialExpressionByGeneWrapper.test_direction_both_accepted Pydantic validation test (Literal accepts 'both', rejects 'invalid').
   - KG-integration test: assert direction='both' returns same total_matching as direction=None, significant_only=True on a known fixture organism+experiment (functional-equivalence proof per spec §6.4 verification).

Update EXPECTED_TOOLS registry in test_tool_wrappers.py:
- list_metabolites: rename `search` → `search_text` in param list; add `exclude_metabolite_ids` after `metabolite_ids`.
- genes_by_metabolite: add `exclude_metabolite_ids` after `metabolite_ids`.
- metabolites_by_gene: add `exclude_metabolite_ids` after `metabolite_ids`.
- differential_expression_by_gene: expand direction Literal to include 'both'.
TOOL_BUILDERS registry untouched (no new builders).

Anti-scope-creep guardrail: ADD only — do NOT modify any unrelated test, case, or yaml. If an unrelated test fails in your environment after writing the new tests, REPORT AS A CONCERN; do not silently retune. Pinned baselines are KG-state guards.

Self-verify before reporting DONE: run `uv run pytest tests/unit/ -q --tb=no` and confirm exactly the new tests are red, the 4 internal-call-site renames pass, and rest is green. Report DONE / DONE_WITH_CONCERNS / BLOCKED per superpowers:subagent-driven-development.
```

- [ ] **Step 2: Wait for `test-updater` to report back.**

Expected report: DONE with newly added tests red and internal-call-site renames green. If DONE_WITH_CONCERNS, surface to user before proceeding.

- [ ] **Step 3: Verify the RED state.**

```bash
uv run pytest tests/unit/ -q --tb=no 2>&1 | tail -30
```

Expected: only the new Phase 2 tests are red; all existing tests green except the 4 renamed `search=` call sites which should now pass under `search_text=`. Unrelated red → halt and investigate.

- [ ] **Step 4: Commit RED state.**

```bash
git add tests/
git commit -m "$(cat <<'EOF'
test(phase2): seed RED-stage failing tests for cross-cutting renames

Adds failing tests for Phase 2 items:
- search→search_text rename on list_metabolites
- top_pathways→top_metabolite_pathways rename on list_metabolites + metabolites_by_gene
- exclude_metabolite_ids filter on 3 chemistry tools
- direction='both' option on differential_expression_by_gene

Also renames 4 internal call sites passing search= → search_text= on list_metabolites.

Frozen spec: docs/tool-specs/2026-05-05-phase2-cross-cutting-renames.md.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Stage 2 GREEN — Parallel 4-agent dispatch

**Files (each agent owns one file):**
- `multiomics_explorer/kg/queries_lib.py` (`query-builder`)
- `multiomics_explorer/api/functions.py` (`api-updater`)
- `multiomics_explorer/mcp_server/tools.py` (`tool-wrapper`)
- About-content YAMLs + CLAUDE.md + `examples/metabolites.py` (`doc-updater`)

Per `add-or-update-tool` skill Stage 2 — dispatch all 4 agents in **one** message in parallel. File-ownership = collision-safe by construction. Each agent gets the frozen spec, its file, a pointer to `layer-rules` skill, the anti-scope-creep guardrail, and the Mode B briefing addendum ("implement tool 1 as template within your file, then extend to N").

- [ ] **Step 1: Dispatch all 4 agents in a single message.** Each is briefed below. Send all 4 Agent calls in one assistant message for true parallelism (per `superpowers:dispatching-parallel-agents`).

### Agent A — `query-builder`

```
Agent({
  description: "Phase 2 GREEN — query builder",
  subagent_type: "query-builder",
  prompt: <see brief A below>
})
```

**Brief A — `query-builder`:**

```
You own multiomics_explorer/kg/queries_lib.py for Phase 2 of the metabolites surface refresh. Read the frozen spec docs/tool-specs/2026-05-05-phase2-cross-cutting-renames.md before editing.

Tests are red in your scope (tests/unit/test_query_builders.py). Make them green by ADDING / RENAMING in your owned file ONLY. Do not edit any other file.

Items to implement (anchor patterns — line numbers in spec are pre-Phase-1 and may have shifted):

Item 1 — search→search_text param rename in `_list_metabolites_where`, `build_list_metabolites`, `build_list_metabolites_summary`. Pure Python kwarg rename. The Cypher param name `$search` (used by `db.index.fulltext.queryNodes(...)` second arg) STAYS unchanged — only the Python kwarg renames. The internal mapping `params["search"] = search_text` makes this explicit. Anchor: grep for `def _list_metabolites_where`, `def build_list_metabolites`.

Item 2 — RETURN-alias renames in `build_list_metabolites_summary` (the top_pathways subquery / call block) and `build_metabolites_by_gene_summary` (its top_pathways subquery). Rename:
- envelope key: top_pathways → top_metabolite_pathways
- per-element keys inside the collected list: pathway_id → metabolite_pathway_id, pathway_name → metabolite_pathway_name
Other element keys (count on list_metabolites; gene_count, pathway_reaction_count, pathway_metabolite_count on metabolites_by_gene) are UNCHANGED. Anchor: grep for `top_pathways:` in your file.

Item 3 — exclude_metabolite_ids parameter addition. Add to:
- `_list_metabolites_where` (one site)
- `_genes_by_metabolite_metabolism_where`, `_genes_by_metabolite_transport_where` (both arms)
- `_metabolites_by_gene_metabolism_where`, `_metabolites_by_gene_transport_where` (both arms)
- The 6 builders that call them: build_list_metabolites + summary, build_genes_by_metabolite + summary, build_metabolites_by_gene + summary

Pattern (mirror metabolite_ids include block; PARENTHESIZE per spec §6.3 to dodge CyVer false-positive):

```python
if exclude_metabolite_ids:
    conditions.append("(NOT (m.id IN $exclude_metabolite_ids))")
    params["exclude_metabolite_ids"] = exclude_metabolite_ids
```

Place IMMEDIATELY AFTER each existing `if metabolite_ids:` block. Treat empty list as None (Python truthy check covers this).

Item 4 — new direction='both' branch in `_differential_expression_where`. Insert as a new elif between the existing `direction == "down"` and `significant_only` branches:

```python
elif direction == "both":
    conditions.append("r.expression_status IN ['significant_up', 'significant_down']")
```

Anti-scope-creep guardrail: ADD/RENAME only — do NOT modify any unrelated function, helper, Cypher fragment, or signature. If you observe pre-existing red tests outside your scope, REPORT AS A CONCERN; do not retune. Phase 1 has just landed — line numbers shifted from pre-Phase-1; use grep / function-name anchors.

Mode B addendum: implement Item 3 for `list_metabolites` (1 WHERE helper) as template; then extend to `genes_by_metabolite` (2 WHERE helpers) and `metabolites_by_gene` (2 WHERE helpers) — pattern is identical, only placement varies.

Self-verify: `uv run pytest tests/unit/test_query_builders.py -q --tb=short`. All Phase 2 query-builder tests should pass. Report DONE / DONE_WITH_CONCERNS / BLOCKED.
```

### Agent B — `api-updater`

```
Agent({
  description: "Phase 2 GREEN — API + internal callers",
  subagent_type: "api-updater",
  prompt: <see brief B below>
})
```

**Brief B — `api-updater`:**

```
You own multiomics_explorer/api/functions.py + the 4 internal call sites that pass `search=` to `list_metabolites` for Phase 2. Read the frozen spec docs/tool-specs/2026-05-05-phase2-cross-cutting-renames.md before editing.

Internal call sites for Item 1 (search→search_text rename) — update all 4:
1. tests/unit/test_api_functions.py — TestListMetabolites.test_lucene_retry_on_parse_error (search="glucose*" → search_text="glucose*")
2. tests/unit/test_api_functions.py — TestListMetabolites.test_search_empty_validation (search="" → search_text=""; search="   " → search_text="   ")
3. tests/integration/test_api_contract.py — list_metabolites(search="glucose", ...) → search_text="glucose"
4. tests/integration/test_api_contract.py — list_metabolites(search="   ", ...) → search_text="   "
(examples/metabolites.py:127 is owned by doc-updater, not you)

Item 1 in api/functions.py — rename `search` → `search_text` in `def list_metabolites(...)` signature + docstring + internal pass-through to builder. Builder kwarg also renamed (query-builder agent owns that file; you pass `search_text=search_text` to the builder).

Item 3 — add `exclude_metabolite_ids: list[str] | None = None` parameter immediately after `metabolite_ids` to:
- list_metabolites
- genes_by_metabolite
- metabolites_by_gene
Pass through to builders. Update each docstring with one-line description ("Exclude metabolites with these IDs. Set-difference semantics with metabolite_ids — exclude wins on overlap.").

Item 4 — extend `_VALID_DIRECTIONS` constant (or wherever validation occurs in api/functions.py around line ~2078-2081) to include 'both'. Update `differential_expression_by_gene` docstring to mention 'both' as the explicit spelling for "return up + down significant rows" — functionally equivalent to `direction=None, significant_only=True`.

Item 2 — NO API-LAYER CHANGE. The envelope rename is a Cypher RETURN-alias rename + Pydantic field rename; the API function passes envelope through unchanged.

Anti-scope-creep guardrail: ADD/RENAME only. The 1 rename + 3 param additions + 1 validator update + 4 internal call-site updates are your entire scope.

Mode B addendum: Item 3 — implement on list_metabolites first as template, then extend to genes_by_metabolite and metabolites_by_gene with identical 2-line addition.

Self-verify: `uv run pytest tests/unit/test_api_functions.py -q --tb=short`. All Phase 2 API tests should pass. Report DONE / DONE_WITH_CONCERNS / BLOCKED.
```

### Agent C — `tool-wrapper`

```
Agent({
  description: "Phase 2 GREEN — MCP wrappers + Pydantic models",
  subagent_type: "tool-wrapper",
  prompt: <see brief C below>
})
```

**Brief C — `tool-wrapper`:**

```
You own multiomics_explorer/mcp_server/tools.py for Phase 2 of the metabolites surface refresh. Read the frozen spec docs/tool-specs/2026-05-05-phase2-cross-cutting-renames.md before editing.

Items to implement:

Item 1 — rename Annotated kwarg `search` → `search_text` in the @mcp.tool wrapper for list_metabolites. Update Field(description=...). Pass through to API as search_text=search_text.

Item 2 — Pydantic field renames + envelope key renames:
- MetTopPathway model: rename `pathway_id` → `metabolite_pathway_id`, `pathway_name` → `metabolite_pathway_name`. UNCHANGED: `count`.
- MbgTopPathway model: rename `pathway_id` → `metabolite_pathway_id`, `pathway_name` → `metabolite_pathway_name`. UNCHANGED: `gene_count`, `pathway_reaction_count`, `pathway_metabolite_count`.
- ListMetabolitesResponse: rename envelope field `top_pathways` → `top_metabolite_pathways`.
- MetabolitesByGeneResponse: rename envelope field `top_pathways` → `top_metabolite_pathways`.
Update Field(description=...) on each renamed field to mention "metabolite-pathway rollup (distinct from KO-pathway annotations on genes_by_ontology)".

Item 3 — add Annotated parameter `exclude_metabolite_ids: Annotated[list[str] | None, Field(description="Exclude metabolites with these IDs. Set-difference semantics with `metabolite_ids` — exclude wins on overlap. Empty list is no-op.")] = None` immediately after the `metabolite_ids` parameter to:
- list_metabolites @mcp.tool wrapper
- genes_by_metabolite @mcp.tool wrapper
- metabolites_by_gene @mcp.tool wrapper

Pass through to API.

Item 4 — change `direction` Literal in differential_expression_by_gene wrapper from `Literal["up", "down"] | None` to `Literal["up", "down", "both"] | None`. Update Field(description=...) to mention 'both' as explicit spelling for both-arm DE (functionally identical to `direction=None, significant_only=True`).

Anti-scope-creep guardrail: ADD/RENAME only. The 5 Pydantic field/envelope renames + 3 param additions + 1 Literal extension are your entire scope. Do not touch any other tool's wrapper, response model, or pass-through plumbing.

Mode B addendum: Item 3 — implement on list_metabolites first as template, extend to peers identically.

Self-verify: `uv run pytest tests/unit/test_tool_wrappers.py -q --tb=short`. All Phase 2 wrapper tests should pass; EXPECTED_TOOLS registry should match (test-updater agent already updated it in RED stage). Report DONE / DONE_WITH_CONCERNS / BLOCKED.
```

### Agent D — `doc-updater`

```
Agent({
  description: "Phase 2 GREEN — about-content + CLAUDE.md + examples",
  subagent_type: "doc-updater",
  prompt: <see brief D below>
})
```

**Brief D — `doc-updater`:**

```
You own about-content YAMLs + CLAUDE.md + multiomics_explorer/examples/metabolites.py for Phase 2 of the metabolites surface refresh. Read the frozen spec docs/tool-specs/2026-05-05-phase2-cross-cutting-renames.md before editing.

Files in scope:
- multiomics_explorer/inputs/tools/list_metabolites.yaml
- multiomics_explorer/inputs/tools/metabolites_by_gene.yaml
- multiomics_explorer/inputs/tools/genes_by_metabolite.yaml
- multiomics_explorer/inputs/tools/differential_expression_by_gene.yaml
- multiomics_explorer/examples/metabolites.py (line ~127, the search="glutamine" call)
- CLAUDE.md (tool table rows for the 4 affected tools)

Per-file changes:

list_metabolites.yaml — Item 1 (rename `search:` examples to `search_text:`); Item 2 (update example responses that quote `top_pathways` / `pathway_id` / `pathway_name`; rename to top_metabolite_pathways / metabolite_pathway_id / metabolite_pathway_name); Item 3 (add new mistake entry: "When the top_metabolites rollup is dominated by ATP / ADP / NADH / NADPH / H2O, pass exclude_metabolite_ids=[<kegg.compound:Cxxxxx>] to strip cofactor noise. Set-difference semantics with metabolite_ids — exclude wins on overlap."; add new example showing the 5-cofactor exclude per spec §6.3 worked example).

metabolites_by_gene.yaml — Item 2 (same `top_pathways` envelope rename); Item 3 (mistake + example for exclude_metabolite_ids).

genes_by_metabolite.yaml — Item 3 (mistake + example for exclude_metabolite_ids). NO Item 2 changes (this tool does not carry top_pathways today).

differential_expression_by_gene.yaml — Item 4 (new example: direction='both' returning union; new mistake entry: "direction='both' is functionally identical to direction=None, significant_only=True — pick whichever spelling is clearer at the call site. Default direction=None is unchanged.").

examples/metabolites.py — line ~127, change `list_metabolites(search="glutamine", limit=5)` to `list_metabolites(search_text="glutamine", limit=5)`. Update any narrative comments nearby that reference `search=` or `top_pathways` / `pathway_id`.

CLAUDE.md — update the 4 tool-table rows:
- list_metabolites row: any reference to `search` → `search_text`; any reference to `top_pathways` → `top_metabolite_pathways`; mention `exclude_metabolite_ids` filter.
- metabolites_by_gene row: rename `top_pathways` → `top_metabolite_pathways`; mention `exclude_metabolite_ids`.
- genes_by_metabolite row: mention `exclude_metabolite_ids`.
- differential_expression_by_gene row: add 'both' to direction options enumeration if listed.

After all YAML edits, regenerate about-content:
```
uv run python scripts/build_about_content.py
```
This writes directly to skills/multiomics-kg-guide/references/tools/*.md — no separate sync step. Verify generated md reflects the renamed fields.

Anti-scope-creep guardrail: ADD/RENAME only. Do not touch any non-listed YAML or md file. If you observe other YAMLs that reference top_pathways or pathway_id (e.g., in chaining entries pointing to list_metabolites from another tool's docs), report as a concern; do not silently retune.

Self-verify:
1. `uv run pytest tests/unit/test_about_content.py -q --tb=short` (consistency with Pydantic schema)
2. `uv run pytest tests/integration/test_about_examples.py -q --tb=short` (examples execute against KG)
Report DONE / DONE_WITH_CONCERNS / BLOCKED.
```

- [ ] **Step 2: Wait for all 4 agents to report.**

Expected: 4 × DONE. If any agent reports DONE_WITH_CONCERNS or BLOCKED, surface to user before proceeding to Stage 3.

- [ ] **Step 3: Run unit tests across the full repo.**

```bash
uv run pytest tests/unit/ -q --tb=no 2>&1 | tail -30
```

Expected: all green. If red persists, dispatch the relevant agent with feedback (one fix loop allowed per `add-or-update-tool` skill Stage 3).

- [ ] **Step 4: Commit GREEN state.**

```bash
git add multiomics_explorer/ tests/ examples/ CLAUDE.md
git commit -m "$(cat <<'EOF'
feat(phase2): land cross-cutting renames + filter additions

- Item 1: rename `search` → `search_text` on list_metabolites for API consistency
- Item 2: rename envelope `top_pathways` → `top_metabolite_pathways` and per-element `pathway_id` / `pathway_name` → `metabolite_pathway_id` / `metabolite_pathway_name` on list_metabolites + metabolites_by_gene
- Item 3: add `exclude_metabolite_ids` filter on list_metabolites + metabolites_by_gene + genes_by_metabolite (set-difference semantics; CyVer-safe parens)
- Item 4: accept `direction='both'` on differential_expression_by_gene (functionally equivalent to `direction=None, significant_only=True`; API-discoverability sugar)

All renames are pure-string substitutions; no aggregation logic shifts. The 1 filter is a pure addition; the 1 direction option is a pure branch addition. All 4 internal call sites for `search=` updated.

Frozen spec: docs/tool-specs/2026-05-05-phase2-cross-cutting-renames.md.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Stage 3 VERIFY — Code review + integration tests + regression regen

Per `add-or-update-tool` skill Stage 3: code review is a HARD GATE (mocked unit tests can't validate actual Cypher). Code review may run alongside or after the KG gates.

- [ ] **Step 1: Dispatch code-reviewer in background.**

Use `superpowers:requesting-code-review` skill. Brief includes:
- Diff scope: Phase 2 GREEN commit + RED commit
- Spec link: docs/tool-specs/2026-05-05-phase2-cross-cutting-renames.md
- Particular attention areas (from spec §11 acceptance criteria):
  - The `search_text` rename touches Python kwarg only — Cypher `$search` param alias intact (verify by grep).
  - The `top_metabolite_pathways` Cypher RETURN aliases cascade correctly through query builder → API merge → Pydantic envelope.
  - The 5 `(NOT (m.id IN $exclude_metabolite_ids))` blocks are placed inside the right WHERE helpers (per-arm scope on the 2 chemistry drill-down tools — exclude must apply on BOTH metabolism + transport arms).
  - The new `direction == "both"` branch is ordered before the `significant_only` branch.
  - Parenthesization on the NOT-IN clause matches spec §6.3 (CyVer false-positive on unparenthesized form).

```bash
# Dispatched in background via Agent tool — see superpowers:requesting-code-review for the exact dispatch shape.
```

- [ ] **Step 2: Run integration tests (foreground).**

```bash
uv run pytest tests/integration/ -m kg -q --tb=short
```

Expected: all green. The KG round-trip cases for items 1, 3, 4 in `test_mcp_tools.py` validate end-to-end behavior.

- [ ] **Step 3: Regenerate regression fixtures.**

The 2 envelope-rename tools (`list_metabolites`, `metabolites_by_gene`) and DE direction='both' will mismatch existing fixtures.

```bash
uv run pytest tests/regression/ --force-regen -m kg -q
```

Expected: fixtures regenerated cleanly. Inspect the diff to confirm only Phase 2 fields changed (renames + additions) — no semantic shifts on unaffected tools.

- [ ] **Step 4: Verify regression baseline holds (re-run without --force-regen).**

```bash
uv run pytest tests/regression/ -m kg -q --tb=short
```

Expected: all green.

- [ ] **Step 5: Wait for code-reviewer report.**

Foreground gates pass; now wait for the background reviewer. Two outcomes:
- All findings clean → proceed to Step 6.
- Findings reported → triage:
  - Genuine issues: dispatch the relevant implementer agent (single-file scope) with the feedback. Re-run unit + integration after fix.
  - Disagreements: respond per `superpowers:receiving-code-review` with technical justification.

- [ ] **Step 6: Commit regression-fixture regen.**

```bash
git add tests/regression/
git commit -m "$(cat <<'EOF'
test(phase2): regenerate regression fixtures for renamed envelopes + new direction option

list_metabolites + metabolites_by_gene summary fixtures pick up the renamed top_metabolite_pathways envelope key + metabolite_pathway_id / metabolite_pathway_name element keys.

differential_expression_by_gene fixtures pick up direction='both' branch. No fixtures changed for unaffected tools.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Finalization — verification-before-completion + branch close

- [ ] **Step 1: Run full test suite once more (cold).**

```bash
uv run pytest tests/unit/ tests/integration/ -m "not slow" -q --tb=no 2>&1 | tail -30
uv run pytest tests/regression/ -m kg -q --tb=no 2>&1 | tail -10
```

Expected: all green.

- [ ] **Step 2: Verify all 4 internal `search=` call sites are updated.**

```bash
grep -rn "list_metabolites(search=" /home/osnat/github/multiomics_explorer/ --include="*.py" --include="*.yaml" --include="*.md" 2>/dev/null
```

Expected: empty output. Any hits indicate a missed call site → fix before declaring done.

- [ ] **Step 3: Verify all `top_pathways` envelope references are updated.**

```bash
grep -rn '"top_pathways"\|top_pathways:' /home/osnat/github/multiomics_explorer/multiomics_explorer/ /home/osnat/github/multiomics_explorer/tests/ --include="*.py" --include="*.yaml" 2>/dev/null
```

Expected: empty output, OR only matches in the `pathway_enrichment` / `cluster_enrichment` tools which have their own (separate) `top_pathways` semantics — confirm by file. If `list_metabolites` or `metabolites_by_gene` references remain, fix before declaring done.

- [ ] **Step 4: Verify `pathway_id` / `pathway_name` are updated in chemistry tools (not in pathway_enrichment which is separate).**

```bash
grep -rn 'pathway_id\|pathway_name' /home/osnat/github/multiomics_explorer/multiomics_explorer/ /home/osnat/github/multiomics_explorer/tests/ --include="*.py" --include="*.yaml" 2>/dev/null | grep -E 'list_metabolites|metabolites_by_gene'
```

Expected: empty output for the 2 renamed tools' contexts. (Other tools may legitimately use `pathway_id` for their own purposes — KO-pathway-annotation in `genes_by_ontology`, etc. — those are out of scope.)

- [ ] **Step 5: Verify the rebuilt about-content reflects renames.**

```bash
grep -E "top_metabolite_pathways|metabolite_pathway_id|search_text|exclude_metabolite_ids|direction.*both" /home/osnat/github/multiomics_explorer/multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_metabolites.md /home/osnat/github/multiomics_explorer/multiomics_explorer/skills/multiomics-kg-guide/references/tools/metabolites_by_gene.md /home/osnat/github/multiomics_explorer/multiomics_explorer/skills/multiomics-kg-guide/references/tools/genes_by_metabolite.md /home/osnat/github/multiomics_explorer/multiomics_explorer/skills/multiomics-kg-guide/references/tools/differential_expression_by_gene.md
```

Expected: hits across all 4 tools showing the new fields/options surface.

- [ ] **Step 6: Final commit if any verification shook loose lingering edits.**

If grep verification found residual stale references and required a fix, commit those:

```bash
git add <files>
git commit -m "$(cat <<'EOF'
fix(phase2): clean up residual references found during verification

[describe what was missed]
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If no residual edits — skip this step.

- [ ] **Step 7: Apply `superpowers:verification-before-completion` skill discipline.**

Confirm with explicit evidence:
1. All unit tests pass (Step 1 output).
2. All integration tests pass (Step 1 output).
3. All regression tests pass (Step 1 output).
4. Code review clean or all findings addressed (Task 3 Step 5 outcome).
5. No stale call sites for `search=`, `top_pathways`, or `pathway_id`/`pathway_name` in chemistry-tool contexts (Steps 2-4 output).
6. About-content regenerated and contains the new field references (Step 5 output).

Only after all 6 confirmations → proceed to Step 8.

- [ ] **Step 8: Apply `superpowers:finishing-a-development-branch` skill.**

Per the skill's structured options:
- (a) Merge the worktree branch directly to main (fast-forward) — simplest if no PR review required.
- (b) Push branch + open PR for explicit review.
- (c) Hold on the branch pending Phase 3 staging (if Phase 3 is queued and may benefit from sharing the branch).

Recommended default: (a) fast-forward merge to main, mirroring how recent metabolites work has landed (project memory `project_metabolites_assets_design.md`). Confirm with user before merging.

```bash
# Option (a) merge sequence (run from main worktree, NOT the Phase 2 worktree):
cd /home/osnat/github/multiomics_explorer
git merge --ff-only worktree-metabolites-phase2-renames
git worktree remove .claude/worktrees/metabolites-phase2-renames
git branch -D worktree-metabolites-phase2-renames  # only after merge confirmed clean
```

- [ ] **Step 9: Update memory.**

Update `MEMORY.md` and the existing `project_metabolites_phase2_spec.md`:
- Mark Phase 2 as shipped with the merge SHA.
- Add a one-liner referencing the writing-plans cycle that drove it.
- Note any deviations from spec (none expected — spec freeze + agent dispatch should produce literal implementation).

---

## Self-Review (run before declaring plan complete)

Per `superpowers:writing-plans` skill self-review checklist:

**Spec coverage check.** Each spec section / item maps to a task:
- Spec §6.1 (Item 1 — search_text) → Task 1 (test-updater) + Task 2 Agents A, B (query-builder + api-updater) + Task 2 Agent D (examples + CLAUDE.md). ✓
- Spec §6.2 (Item 2 — top_metabolite_pathways) → Task 1 + Task 2 Agents A, C, D. ✓
- Spec §6.3 (Item 3 — exclude_metabolite_ids) → Task 1 + Task 2 Agents A, B, C, D. ✓
- Spec §6.4 (Item 4 — direction='both') → Task 1 + Task 2 Agents A, B, C, D. ✓
- Spec §7 (Implementation file map) → Task 2 owners match exactly. ✓
- Spec §8 (Test cases per layer) → Task 1 covers all 4 layers' additions. ✓
- Spec §9 (Open questions) → all 5 closed pre-freeze; no decision-loop in plan. ✓
- Spec §10 (Phase 1 interaction) → Prerequisites + Task 0 enforce post-Phase-1 baseline; anchor patterns used in agent briefs. ✓
- Spec §11 (Acceptance criteria) → Task 4 verification steps cover each criterion. ✓

**Placeholder scan.** No "TBD" / "fill in" / "implement later" / "similar to Task N" placeholders. Each agent brief is self-contained with item-by-item directives.

**Type consistency.** Field renames consistent across the plan: `search` → `search_text` (not `searchText` or `query`), `top_pathways` → `top_metabolite_pathways` (consistently spelled), `pathway_id` → `metabolite_pathway_id`, `pathway_name` → `metabolite_pathway_name`, `exclude_metabolite_ids` (snake_case throughout). Direction Literal `"up" | "down" | "both" | None` consistent.

**Line-number caveat.** All file:line references in the spec are pre-Phase-1 and will shift. The plan acknowledges this in Prerequisites + Task 0 + each agent brief by directing implementers to use grep / function-name anchors. ✓

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-05-phase2-cross-cutting-renames.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. The Mode B parallel-build dispatch in Task 2 fits naturally inside `superpowers:subagent-driven-development` — that skill explicitly handles the case where 4 file-owned agents go in parallel (collision-safe by file ownership).

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints. Same skill + agent dispatch happens at Task 2; the difference is whether intervening tasks (RED, VERIFY) run in this session vs. fresh subagents.

**Which approach?**

Default recommendation: **(1) Subagent-Driven**, gated on Phase 1 having landed first. Phase 2 should ship right after Phase 1 per roadmap §6 sequencing — no benefit to delaying.
