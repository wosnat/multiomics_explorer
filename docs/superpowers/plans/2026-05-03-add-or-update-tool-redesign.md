# `add-or-update-tool` Skill Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slim the `add-or-update-tool` skill, the 5 project agents, and add a CLAUDE.md discoverability pointer so that future tool builds run with parallel TDD discipline and reuse `superpowers:` skills instead of restating their content.

**Architecture:** Markdown edits only. No production code changes. Each agent file shrinks to ~15 lines around a uniform template (file ownership + layer-rules pointer + TDD instruction + scoped self-verify). The skill SKILL.md is restructured around three Phase-2 stages (RED → GREEN → VERIFY) and delegates discipline to `superpowers:` skills. The custom `code-reviewer` agent is removed in favor of the standard built-in invoked via `superpowers:requesting-code-review`.

**Tech Stack:** Markdown, git, pytest (smoke).

**Spec:** `docs/superpowers/specs/2026-05-03-add-or-update-tool-redesign.md`

---

## File Structure

| File | Action | Responsibility after edit |
|---|---|---|
| `.claude/agents/query-builder.md` | Slim | File ownership + scoped pytest |
| `.claude/agents/api-updater.md` | Slim + scope expansion (analysis/) | File ownership (incl. analysis/) + scoped pytest |
| `.claude/agents/tool-wrapper.md` | Slim | File ownership + scoped pytest |
| `.claude/agents/doc-updater.md` | Slim + rescope (drop unrelated docs, add analysis md + examples + CLAUDE.md tool table) | YAML inputs + analysis md + examples + tool table |
| `.claude/agents/test-updater.md` | Slim + reframe as RED-writer | Failing tests + registries |
| `.claude/agents/code-reviewer.md` | Delete | (replaced by standard built-in) |
| `.claude/skills/add-or-update-tool/SKILL.md` | Slim from ~325 → ~120 lines | Phase 1 KG iteration + Phase 2 stage flow + reuse map |
| `CLAUDE.md` | One-line addition | Discoverability pointer |

Each task produces one commit. Final PR after Task 9.

---

## Task 0: Create branch

**Files:** none (git only)

- [ ] **Step 1: Verify clean state on main**

Run: `git -C /home/osnat/github/multiomics_explorer status --short`
Expected: only the pre-existing unrelated tracked changes (regression yml files + the kg-side-frictions-reframed spec). The redesign spec is already committed.

- [ ] **Step 2: Create and checkout feature branch**

```bash
git -C /home/osnat/github/multiomics_explorer checkout -b feat/skill-redesign-add-or-update-tool
```

Run: `git -C /home/osnat/github/multiomics_explorer branch --show-current`
Expected: `feat/skill-redesign-add-or-update-tool`

---

## Task 1: Slim `query-builder` agent

**Files:**
- Modify: `.claude/agents/query-builder.md` (full rewrite, ~42 → ~22 lines)

- [ ] **Step 1: Replace agent file content**

Write the following exact content to `.claude/agents/query-builder.md`:

```markdown
---
name: query-builder
description: Implement query builders in queries_lib.py per the frozen tool spec
---

# Query builder

## File you own

- `multiomics_explorer/kg/queries_lib.py` — the only file you edit.

## How to work

1. Read the spec referenced in your brief (typically `docs/tool-specs/{name}.md`).
2. Tests are already failing in your scope. Make them green.
3. Follow the `layer-rules` skill for Cypher conventions (`$param`, `AS` aliases, `ORDER BY`, organism filter, builder return tuple).
4. Before reporting back, run scoped pytest and confirm green:
   `pytest tests/unit/test_query_builders.py::TestBuild{Name} -q`
5. Report `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per `superpowers:subagent-driven-development`.

## Out of scope

- Do not edit any file other than your owned file.
- Do not run unrelated tests.
- Do not change the spec — flag scope concerns instead.
```

- [ ] **Step 2: Verify line count and structure**

Run: `wc -l /home/osnat/github/multiomics_explorer/.claude/agents/query-builder.md`
Expected: 21–25 lines.

Run: `grep -c '^## ' /home/osnat/github/multiomics_explorer/.claude/agents/query-builder.md`
Expected: `3` (File you own / How to work / Out of scope).

- [ ] **Step 3: Commit**

```bash
git -C /home/osnat/github/multiomics_explorer add .claude/agents/query-builder.md
git -C /home/osnat/github/multiomics_explorer commit -m "refactor(agents): slim query-builder to ownership + TDD self-verify template"
```

---

## Task 2: Slim `api-updater` agent (incl. analysis/ scope)

**Files:**
- Modify: `.claude/agents/api-updater.md` (full rewrite, ~45 → ~28 lines)

- [ ] **Step 1: Replace agent file content**

Write the following exact content to `.claude/agents/api-updater.md`:

```markdown
---
name: api-updater
description: Implement API functions in api/functions.py and analysis utilities in analysis/*.py per the frozen tool spec
---

# API updater

## Files you own

- `multiomics_explorer/api/functions.py`
- `multiomics_explorer/api/__init__.py` (`__all__`)
- `multiomics_explorer/__init__.py` (`__all__` and re-exports)
- `multiomics_explorer/analysis/*.py` (when the spec touches analysis utilities — enrichment, expression, frames, etc.)

## How to work

1. Read the spec referenced in your brief (typically `docs/tool-specs/{name}.md`).
2. Tests are already failing in your scope. Make them green.
3. Follow the `layer-rules` skill for API conventions (positional first then `*, conn=None`, `_default_conn(conn)`, `ValueError` on bad input, return `dict`/`list[dict]` only).
4. Wire exports in BOTH `api/__init__.py` and `multiomics_explorer/__init__.py` for any new function.
5. Before reporting back, run scoped pytest and confirm green:
   - `pytest tests/unit/test_api_functions.py::Test{Name} -q`
   - If analysis files changed: also `pytest tests/unit/test_analysis.py -q`
6. Report `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per `superpowers:subagent-driven-development`.

## Out of scope

- Do not edit any file other than your owned files.
- Do not run unrelated tests.
- Do not change the spec — flag scope concerns instead.
```

- [ ] **Step 2: Verify line count and structure**

Run: `wc -l /home/osnat/github/multiomics_explorer/.claude/agents/api-updater.md`
Expected: 26–30 lines.

Run: `grep -c '^## ' /home/osnat/github/multiomics_explorer/.claude/agents/api-updater.md`
Expected: `3`.

- [ ] **Step 3: Commit**

```bash
git -C /home/osnat/github/multiomics_explorer add .claude/agents/api-updater.md
git -C /home/osnat/github/multiomics_explorer commit -m "refactor(agents): slim api-updater + add analysis/ to scope"
```

---

## Task 3: Slim `tool-wrapper` agent

**Files:**
- Modify: `.claude/agents/tool-wrapper.md` (full rewrite, ~44 → ~22 lines)

- [ ] **Step 1: Replace agent file content**

Write the following exact content to `.claude/agents/tool-wrapper.md`:

```markdown
---
name: tool-wrapper
description: Implement MCP tool wrappers in mcp_server/tools.py per the frozen tool spec
---

# Tool wrapper

## File you own

- `multiomics_explorer/mcp_server/tools.py` — the only file you edit.

## How to work

1. Read the spec referenced in your brief (typically `docs/tool-specs/{name}.md`).
2. Tests are already failing in your scope. Make them green.
3. Follow the `layer-rules` skill for wrapper conventions (`ctx: Context` first, call `api/` only — never `queries_lib`, `Annotated[type, Field(description=...)]` for params, Pydantic envelope with the standard fields, `ToolError` not raise, `await ctx.info/warning/error`).
4. Before reporting back, run scoped pytest and confirm green:
   `pytest tests/unit/test_tool_wrappers.py::Test{Name}Wrapper -q`
5. Report `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per `superpowers:subagent-driven-development`.

## Out of scope

- Do not edit any file other than your owned file.
- Do not run unrelated tests.
- Do not change the spec — flag scope concerns instead.
```

- [ ] **Step 2: Verify line count and structure**

Run: `wc -l /home/osnat/github/multiomics_explorer/.claude/agents/tool-wrapper.md`
Expected: 21–25 lines.

Run: `grep -c '^## ' /home/osnat/github/multiomics_explorer/.claude/agents/tool-wrapper.md`
Expected: `3`.

- [ ] **Step 3: Commit**

```bash
git -C /home/osnat/github/multiomics_explorer add .claude/agents/tool-wrapper.md
git -C /home/osnat/github/multiomics_explorer commit -m "refactor(agents): slim tool-wrapper to ownership + TDD self-verify template"
```

---

## Task 4: Slim + rescope `doc-updater` agent

**Files:**
- Modify: `.claude/agents/doc-updater.md` (full rewrite, ~46 → ~36 lines, scope changes substantially)

The current scope lists obsolete paths (`docs/architecture_target_v2.md`, `docs/transition_plan_v2.md`, `docs/methodology/llm_omics_analysis_v2.md`) and over-broad skill paths. The new scope is the documentation surface that actually moves per-tool.

- [ ] **Step 1: Replace agent file content**

Write the following exact content to `.claude/agents/doc-updater.md`:

```markdown
---
name: doc-updater
description: Update tool YAML inputs (regenerates about-content), analysis methodology docs, runnable example pythons, and the CLAUDE.md tool table
---

# Doc updater

## Files you own

- `multiomics_explorer/inputs/tools/{name}.yaml` — human-authored sections (examples, mistakes, chaining, verbose_fields).
- `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/{name}.md` — hand-authored analysis methodology (e.g. enrichment, expression). Update when an analysis utility's signature, return shape, or behavior changes.
- `examples/{name}.py` — runnable example pythons served as MCP resource `docs://examples/{name}.py`.
- `CLAUDE.md` — the per-tool entry in the tool table.

You also run `scripts/build_about_content.py` to regenerate
`multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md`
from the YAML + Pydantic models. Never edit the generated `tools/{name}.md` directly.

## How to work

1. Read the spec referenced in your brief (typically `docs/tool-specs/{name}.md`).
2. Update or create the input YAML in `multiomics_explorer/inputs/tools/{name}.yaml`. New tool? Generate skeleton first:
   `uv run python scripts/build_about_content.py --skeleton {name}`
3. Regenerate the about markdown:
   `uv run python scripts/build_about_content.py {name}`
4. If the spec touches analysis utilities, hand-edit the matching `references/analysis/*.md` and the corresponding `examples/*.py`.
5. Update the CLAUDE.md tool-table row for the tool (purpose, key params, summary fields).
6. Before reporting back, run scoped pytest and confirm green:
   - `pytest tests/unit/test_about_content.py -q`
   - `pytest tests/integration/test_about_examples.py -m kg -q`
   - If analysis md changed: `pytest tests/unit/test_analysis_about_content.py -q` and `pytest tests/integration/test_examples.py -m kg -q`
7. Report `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per `superpowers:subagent-driven-development`.

## Out of scope

- Do not edit Python source under `multiomics_explorer/api/`, `kg/`, `mcp_server/`, or `analysis/`.
- Do not edit test files.
- Do not edit the generated `references/tools/*.md` directly — regenerate from YAML.
- Do not change the spec — flag scope concerns instead.
```

- [ ] **Step 2: Verify line count and structure**

Run: `wc -l /home/osnat/github/multiomics_explorer/.claude/agents/doc-updater.md`
Expected: 34–40 lines.

Run: `grep -c '^## ' /home/osnat/github/multiomics_explorer/.claude/agents/doc-updater.md`
Expected: `3`.

- [ ] **Step 3: Commit**

```bash
git -C /home/osnat/github/multiomics_explorer add .claude/agents/doc-updater.md
git -C /home/osnat/github/multiomics_explorer commit -m "refactor(agents): rescope doc-updater to YAML + analysis md + examples + CLAUDE.md tool table"
```

---

## Task 5: Slim + reframe `test-updater` agent (RED writer)

**Files:**
- Modify: `.claude/agents/test-updater.md` (full rewrite, ~50 → ~36 lines)

- [ ] **Step 1: Replace agent file content**

Write the following exact content to `.claude/agents/test-updater.md`:

```markdown
---
name: test-updater
description: Write failing unit tests across query builder, api function, and tool wrapper test files; update EXPECTED_TOOLS and TOOL_BUILDERS registries
---

# Test updater

## Files you own

- `tests/unit/test_query_builders.py` — `TestBuild{Name}` class
- `tests/unit/test_api_functions.py` — `Test{Name}` class
- `tests/unit/test_tool_wrappers.py` — `Test{Name}Wrapper` class + `EXPECTED_TOOLS` list
- `tests/regression/test_regression.py` — `TOOL_BUILDERS` dict
- `tests/regression/cases.yaml` — case entries for the new/changed tool
- `tests/fixtures/gene_data.py` — projection helpers (`as_*_result`) when RETURN columns change

## Two stages

### Stage 1 (RED — primary role)

Briefed with the frozen spec. Write the full failing test suite for the new/changed tool *before* implementation begins. Tests must encode the spec's contract: parameters, response shape, summary/verbose/limit semantics, `not_found` behavior, error paths.

After writing, the orchestrator runs `pytest tests/unit/ -q` and expects exactly the new tests RED. Unrelated red is a halt condition.

### Stage 3 (follow-up — when invoked)

Code review may flag a missing case after Stage 2 lands. When re-dispatched in Stage 3, add the missing test class methods and re-run scoped pytest.

## How to work

1. Read the spec referenced in your brief (typically `docs/tool-specs/{name}.md`).
2. Follow the `testing` skill for per-layer test patterns and fixtures (mock_conn, tool_fns, EXPECTED_TOOLS, TOOL_BUILDERS, char-escape rules).
3. In Stage 1, write tests as red — the implementation files do not yet contain the tool.
4. Before reporting back, run `pytest tests/unit/ -q --tb=no` and confirm exactly your new tests are red and the rest of the suite is green.
5. Report `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per `superpowers:subagent-driven-development`.

## Out of scope

- Do not edit production code under `multiomics_explorer/`.
- Do not edit input YAML, generated about markdown, analysis md, or example pythons.
- Do not change the spec — flag scope concerns instead.
```

- [ ] **Step 2: Verify line count and structure**

Run: `wc -l /home/osnat/github/multiomics_explorer/.claude/agents/test-updater.md`
Expected: 33–40 lines.

Run: `grep -c '^## ' /home/osnat/github/multiomics_explorer/.claude/agents/test-updater.md`
Expected: `4` (Files you own / Two stages / How to work / Out of scope).

- [ ] **Step 3: Commit**

```bash
git -C /home/osnat/github/multiomics_explorer add .claude/agents/test-updater.md
git -C /home/osnat/github/multiomics_explorer commit -m "refactor(agents): reframe test-updater as RED-writer with two-stage role"
```

---

## Task 6: Delete custom `code-reviewer` agent

The custom agent duplicates work covered by the standard built-in `code-reviewer` subagent invoked via `superpowers:requesting-code-review`. The standard agent is what `superpowers:subagent-driven-development` already integrates with.

**Files:**
- Delete: `.claude/agents/code-reviewer.md`
- Modify: `.claude/skills/add-or-update-tool/SKILL.md:149` (the prose reference will be rewritten in Task 7; clear it here too)

- [ ] **Step 1: Confirm only known reference is in SKILL.md**

Run: `grep -rn "code-reviewer" /home/osnat/github/multiomics_explorer/.claude/ /home/osnat/github/multiomics_explorer/multiomics_explorer/ 2>/dev/null | grep -v ".venv"`
Expected: two lines only — the agent file itself and `SKILL.md:149`. If anything else references it, halt and surface to the user.

- [ ] **Step 2: Delete the agent file**

```bash
git -C /home/osnat/github/multiomics_explorer rm .claude/agents/code-reviewer.md
```

- [ ] **Step 3: Verify deletion**

Run: `ls /home/osnat/github/multiomics_explorer/.claude/agents/`
Expected: 5 files — `query-builder.md`, `api-updater.md`, `tool-wrapper.md`, `doc-updater.md`, `test-updater.md`. No `code-reviewer.md`.

- [ ] **Step 4: Commit**

```bash
git -C /home/osnat/github/multiomics_explorer commit -m "refactor(agents): drop custom code-reviewer in favor of superpowers built-in"
```

(The dangling SKILL.md reference at line 149 is fixed in Task 7.)

---

## Task 7: Slim `add-or-update-tool/SKILL.md`

**Files:**
- Modify: `.claude/skills/add-or-update-tool/SKILL.md` (full rewrite, ~325 → ~120 lines)

The current SKILL.md restates layer rules, test patterns, and sequential per-layer gates. The slimmed version delegates to `layer-rules` and `testing` skills, anchors Phase 2 around Stage 1/2/3, and points to `superpowers:` skills for cross-cutting discipline.

- [ ] **Step 1: Replace SKILL.md content**

Write the following exact content to `.claude/skills/add-or-update-tool/SKILL.md`:

````markdown
---
name: add-or-update-tool
description: Complete lifecycle for adding a new MCP tool or modifying an existing one. Phase 1 is user-driven scope + KG iteration; Phase 2 is parallel TDD build via 4 file-owned agents.
disable-model-invocation: true
argument-hint: "[tool name and description, e.g. 'list_experiments - new tool' or 'genes_by_function - add min_quality param']"
---

# Add or update a tool

This skill orchestrates two phases. Phase 1 is project-specific (scope, KG
iteration, Cypher verification, frozen spec). Phase 2 reuses `superpowers:`
skills for TDD, parallel dispatch, and code review.

References:
- [field-rubric](references/field-rubric.md) — response-schema quality criteria
- [checklist](references/checklist.md) — per-layer file paths + templates
- `layer-rules` skill — Cypher conventions, file ownership, rename cascades
- `testing` skill — per-layer test patterns, EXPECTED_TOOLS, TOOL_BUILDERS, fixtures

## Two execution modes

The skill handles both shapes from one orchestration:

| Mode | Trigger | Phase 1 cost | Phase 2 briefing |
|---|---|---|---|
| A: single tool deep build | One tool, new or significant change | Heavy (KG iteration loop) | One entity per agent |
| B: cross-tool small change | Spec names ≥2 tools | Light (one-page spec, no KG iteration) | N entities per agent — "do tool 1 as template, extend to 2..N within your file" |

Mode detection rule: if the spec lists ≥2 tools by name, use Mode B briefings.

## Phase 1: Definition (user-driven, gated)

All steps require user review before proceeding. Phase 2 does not begin
without an explicit spec freeze.

If modifying an existing tool, first read all 4 layers (queries_lib.py, api/functions.py, mcp_server/tools.py, inputs/tools/{name}.yaml) plus tests for that tool.

### Step 1: Define what's needed

- What the tool does (or what's changing), who calls it, what chains it participates in
- Result-size controls (see below)
- These requirements drive what the KG needs to support
- → User review

#### Deciding result-size controls

All tools return summary fields + `results` list. The question is which summary fields and what defaults.

**ID params are always lists.** Any tool accepting an ID list is a batch tool — every ID-list tool supports `limit`, `summary`, summary fields, and `not_found`.

| Result size | Controls | Examples |
|---|---|---|
| Always small (<30 rows) | `verbose` for column control. Consider `limit` if set will grow. Minimal summary fields (total). | `list_organisms`, `resolve_gene` |
| Batch input (ID lists) | `summary`, `verbose`, `limit`. Rich summary fields. `not_found` for missing IDs. | `gene_overview`, `gene_ontology_terms`, `gene_homologs` |
| Frequently large (100+ rows) | `summary`, `verbose`, `limit`. Rich summary fields (breakdowns, distributions). | `differential_expression_by_gene`, `genes_by_function`, `genes_by_ontology` |

`summary=True` is sugar for `limit=0`. `verbose=True` adds heavy text columns; short categoricals stay in compact. About content is served via MCP resource `docs://tools/{name}`, not as a tool parameter.

### Step 2: KG exploration + iteration

- Query live KG (`run_cypher`) to check whether nodes/edges/properties/data volumes support the requirements.
- If schema changes needed, write a KG-side spec at `docs/kg-specs/kg-spec-{tool-name}.md` using [template](assets/kg-spec-template.md). User coordinates with the KG repo (manual; may involve KG rebuild).
- Re-query after KG changes land. Refine requirements.
- → User review. Loop with Step 1 until stable.

### Step 3: Draft and verify Cypher

Before writing the spec, draft the actual Cypher and verify against the live KG:

- Detail query with representative inputs — verify columns, row counts, sort order, values.
- Summary query — `total_matching` must equal detail row count.
- Filter no-ops — run with and without each filter; if it doesn't change results, document why or remove it.
- Edge cases — gene/entity with no results; nonexistent input; mixed found/not-found batch.
- Multi-dimension tools (e.g. ontologies) — decide orchestration pattern (per-dimension builders + api loop, vs. UNION).

Mark verified queries in the spec as "verified against live KG".

### Output: frozen spec

Once scope, KG schema, and Cypher are stable, write the spec at `docs/tool-specs/{tool-name}.md` using [template](assets/tool-spec-template.md). Spec covers purpose, use cases, tool chains, result-size controls, return field names (per `layer-rules`), verified Cypher, special handling.

→ **Gate:** user approves frozen spec. **Spec is frozen after approval.** Adding fields, removing parameters, or changing query architecture during build requires re-approval and bumps back to Phase 1.

## Phase 2: Build (parallel, TDD-disciplined)

Optional: open a worktree via `superpowers:using-git-worktrees` if the build will run alongside other work.

Phase 2 is three stages. Pytest invocations in the orchestrator: 3 (plus scoped self-verifies inside each agent).

### Stage 1 — RED

Dispatch `test-updater` agent with the frozen spec. It writes failing tests across `test_query_builders.py`, `test_api_functions.py`, `test_tool_wrappers.py` and updates `EXPECTED_TOOLS` and `TOOL_BUILDERS`.

Run `pytest tests/unit/ -q --tb=no`. Expect exactly the new tests red, rest green. Unrelated red → halt and investigate.

### Stage 2 — GREEN (parallel)

Dispatch the 4 implementer agents in **one** message, in parallel. Each owns a different file → collision-safe by construction. (`superpowers:subagent-driven-development` warns against parallel implementers in the general case; the layer-cut here is the exception.)

| Agent | Owns |
|---|---|
| `query-builder` | `kg/queries_lib.py` |
| `api-updater` | `api/functions.py` (+ `__init__.py` exports, `analysis/*.py` if touched) |
| `tool-wrapper` | `mcp_server/tools.py` |
| `doc-updater` | `inputs/tools/*.yaml` (regen via `build_about_content.py`), `references/analysis/*.md`, `examples/*.py`, `CLAUDE.md` tool table |

Each agent is briefed with: the frozen spec, its file(s), a pointer to `layer-rules` skill, "tests are red in your scope; make them green," and its scoped self-verify command.

For Mode B (cross-tool), each brief gains: "Implement tool 1 as the template within your file, then extend to tools 2..N."

Each agent reports `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per `superpowers:subagent-driven-development`.

### Stage 3 — VERIFY

Once all 4 agents report green:

1. **Background**: dispatch the standard `code-reviewer` subagent via `superpowers:requesting-code-review` against the diff + spec.
2. **Foreground**: `pytest tests/unit/ -q`
3. **Foreground**: `pytest tests/integration/ -m kg -q`
4. **Foreground**: `pytest tests/regression/ -m kg -q`
   If the spec declared new or renamed columns, run `pytest tests/regression/ --force-regen -m kg -q` first, then verify.

Code review report returns alongside or after the KG gates. Findings either land clean or trigger one fix loop (re-dispatch the relevant agent with feedback as additional brief).

Then `superpowers:verification-before-completion` for the claim of done, and `superpowers:finishing-a-development-branch` for branch close + PR.

## Skills + agents map

| Concern | Use |
|---|---|
| Phase 1 scope brainstorm | `superpowers:brainstorming` |
| Phase 1 plan from spec | `superpowers:writing-plans` |
| Phase 2 RED → GREEN discipline | `superpowers:test-driven-development` |
| Phase 2 parallel dispatch | `superpowers:dispatching-parallel-agents` (inside `superpowers:subagent-driven-development`) |
| Code review | `superpowers:requesting-code-review` |
| Verify before claiming done | `superpowers:verification-before-completion` |
| Branch isolation (optional) | `superpowers:using-git-worktrees` |
| Branch close + PR | `superpowers:finishing-a-development-branch` |
| Layer conventions | `layer-rules` skill |
| Test patterns | `testing` skill |

## When something doesn't fit

If a layer ownership question doesn't have a clear answer (e.g. a new helper that crosses files), pause and surface to the user. Do not let an agent expand scope unilaterally.
````

- [ ] **Step 2: Verify line count and structure**

Run: `wc -l /home/osnat/github/multiomics_explorer/.claude/skills/add-or-update-tool/SKILL.md`
Expected: 110–135 lines (target ~120).

Run: `grep -c '^## ' /home/osnat/github/multiomics_explorer/.claude/skills/add-or-update-tool/SKILL.md`
Expected: `5` (Two execution modes / Phase 1 / Phase 2 / Skills + agents map / When something doesn't fit).

Run: `grep -n "code-reviewer" /home/osnat/github/multiomics_explorer/.claude/skills/add-or-update-tool/SKILL.md`
Expected: only the `superpowers:requesting-code-review` line and the "Background: dispatch the standard `code-reviewer`" line. No reference to a custom agent file.

- [ ] **Step 3: Commit**

```bash
git -C /home/osnat/github/multiomics_explorer add .claude/skills/add-or-update-tool/SKILL.md
git -C /home/osnat/github/multiomics_explorer commit -m "refactor(skill): slim add-or-update-tool to Phase 1 + 3-stage Phase 2 + reuse map"
```

---

## Task 8: Add CLAUDE.md discoverability pointer

**Files:**
- Modify: `CLAUDE.md` — insert one short paragraph under the "MCP Server" section heading.

- [ ] **Step 1: Locate the insertion point**

Run: `grep -n '## MCP Server' /home/osnat/github/multiomics_explorer/CLAUDE.md`
Expected: one match (the heading line).

- [ ] **Step 2: Insert the pointer paragraph**

Insert the following block immediately after the `## MCP Server` heading line and the blank line that follows it (before the existing `The MCP server (...)` sentence):

```markdown
**Adding or modifying a tool?** Use the `add-or-update-tool` skill — it
orchestrates Phase 1 (scope + KG iteration + Cypher verification) and
Phase 2 (parallel TDD build with file-owned agents). See
`docs/superpowers/specs/2026-05-03-add-or-update-tool-redesign.md` for the
design.

```

- [ ] **Step 3: Verify the insertion**

Run: `grep -n -A2 'Adding or modifying a tool' /home/osnat/github/multiomics_explorer/CLAUDE.md`
Expected: a match showing the block immediately under the MCP Server heading.

- [ ] **Step 4: Commit**

```bash
git -C /home/osnat/github/multiomics_explorer add CLAUDE.md
git -C /home/osnat/github/multiomics_explorer commit -m "docs(claude): add discoverability pointer to add-or-update-tool skill"
```

---

## Task 9: Smoke validation + handoff

**Files:** none (verification + branch handoff)

- [ ] **Step 1: Confirm no production code changed**

Run: `git -C /home/osnat/github/multiomics_explorer diff main..HEAD --stat`
Expected: only files under `.claude/agents/`, `.claude/skills/add-or-update-tool/`, `CLAUDE.md`. No file under `multiomics_explorer/`, `tests/`, `scripts/`, `docs/superpowers/specs/` (except already-committed redesign spec on main).

- [ ] **Step 2: Run unit tests to confirm nothing broke**

Run: `pytest tests/unit/ -q`
Expected: all pass (no production change → no test regression).

- [ ] **Step 3: List agent files for visual sanity check**

Run: `wc -l /home/osnat/github/multiomics_explorer/.claude/agents/*.md`
Expected: each file ≤ 40 lines, total across 5 files ≤ 160 lines.

- [ ] **Step 4: Confirm SKILL.md target hit**

Run: `wc -l /home/osnat/github/multiomics_explorer/.claude/skills/add-or-update-tool/SKILL.md`
Expected: 110–135 lines.

- [ ] **Step 5: Hand off to `superpowers:finishing-a-development-branch`**

Invoke the skill to open the PR. Title: `refactor(skill): redesign add-or-update-tool — TDD + parallel agents`. Body should reference the spec at `docs/superpowers/specs/2026-05-03-add-or-update-tool-redesign.md` and list the validation criteria (to be confirmed during the next real tool build, `list_metabolites` Phase 2).

---

## Validation criteria (post-merge, during next real build)

These are not part of this plan's tasks — they are the success signals to watch for during `list_metabolites` Phase 2 (the redesign's first real test):

- Stage 2 wallclock dominated by the slowest agent, not the sum of 4.
- Code review report arrives without an explicit "now run code review" step.
- Total orchestrator pytest invocations ≤ 3 (excluding agent self-verifies).

If any of these fail on the first real run, revisit the design before the next tool.
