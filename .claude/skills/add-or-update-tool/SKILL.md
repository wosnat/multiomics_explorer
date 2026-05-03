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
