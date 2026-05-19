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
- `layer-rules` skill — Cypher conventions, file ownership, rename cascades, outfacing-doc style rules + `--lint` workflow
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

**Before dispatching any agent, verify the worktree branch HEAD matches main HEAD** (`git log --oneline -1` on each). `EnterWorktree` re-uses an existing branch by name if one already exists, so a stale branch surviving from a previous session can leave you on an outdated base — agents will faithfully implement the spec but fail Stage 3 against the live KG. If they differ, `git reset --hard main` (safe in a fresh worktree with no work) and re-baseline before proceeding.

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

**`api-updater` outfacing-surface brief addendum.** Function docstrings on `api/functions.py` AND `multiomics_explorer/analysis/*.py` are agent-outfacing — they reach Python users via `help()` and LLM agents via the rendered tool md's "Package import equivalent" path and via `docs://analysis/{name}`. The 9 outfacing-doc style rules from the [round-1 readability-pass spec](../../../docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md) apply with a Python-API audience accent: dict keys, raised exceptions, return shape — not agent-routing language. Run `uv run python scripts/build_about_content.py --lint` after editing.

**`doc-updater` outfacing-surface brief addendum.** Analysis md (`references/analysis/*.md`) and example .py files (`examples/*.py`) are agent-outfacing — served at `docs://analysis/{name}` and `docs://examples/{file}`. The 9 rules apply with audience accents: analysis = cross-tool methodology with biological precision; examples = task-oriented runnable code where comments explain the pattern, not biology lore. Run `uv run python scripts/build_about_content.py --lint` after editing.

**Anti-scope-creep guardrail (mandatory in every brief):** "ADD only — do NOT modify, rename, or rebaseline any existing test, case, or yml. If an unrelated test fails in your environment, REPORT AS A CONCERN; do not silently retune. Pinned baselines are KG-state guards." Without this, agents that observe pre-existing failures (e.g. from a stale base, KG drift, or sibling work) will "fix" them by editing baselines downward — silently masking real signals.

For Mode B (cross-tool), each brief gains: "Implement tool 1 as the template within your file, then extend to tools 2..N."

Each agent reports `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per `superpowers:subagent-driven-development`.

### Stage 3 — VERIFY

Once all 4 agents report green:

1. **Foreground**: `uv run python scripts/build_about_content.py --lint`. Mechanical backstop for the outfacing-doc style rules (rules 1-4 in the readability-pass spec — ISO dates, "today" counts, internal-history shorthand, `§` / `parent §`). Now covers MCP md, api docstrings, analysis docstrings, hand-authored md (analysis + guide), and `examples/*.py`. Hard gate — non-zero exit blocks the rest of Stage 3. If the lint flags a domain-vocabulary false-positive (gene name, protein family, timepoint label colliding with a regex pattern), extend the regex (don't suppress) per the [readability-pass spec](../../../docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md).
2. **Background**: dispatch the standard `code-reviewer` subagent via `superpowers:requesting-code-review` against the diff + spec. **Hard gate, not optional** — mocked unit tests can't validate actual Cypher (the mock returns fake rows regardless of label correctness in the query string), and only the reviewer reading the live Cypher catches things like wrong node labels in `MATCH` clauses, wrong relationship directions, or filter clauses that match-everything. The list_metabolites smoke test caught a `MATCH (o:Organism)` typo (label is `OrganismTaxon`) that all 1676 unit tests missed.

   **Brief the reviewer with outfacing-doc style checks** in addition to layer-correctness checks (the `--lint` in step 1 catches mechanical violations; the reviewer catches the judgment-call subset):
   - Tool docstring opens with an action verb and ends with a `Routing: ...` sentence.
   - Pydantic `Field(description=...)` strings are ≤ 250 chars (tooltip ceiling).
   - `[AQ]` / `[ENR]` drift markers (where applicable) are 1-line inline, not multi-paragraph.
   - All `docs://...` cross-links resolve to existing files.
   - **Lint-extension watch:** did the reviewer spot a recurring stale-language pattern (internal shorthand, time-stamped count, dated reference, archaeology jargon) that the `--lint` regex did NOT flag? If yes, propose extending `LINT_PATTERN` in `multiomics_explorer/_outfacing_lint.py` and adding a unit test in `tests/unit/test_outfacing_lint.py` in the same PR — cite the source violation. The lint is non-exhaustive by design; new tool patterns extend it. Don't just delete the bad text without growing the regex.

   See the [readability-pass spec](../../../docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md) for the full 9 outfacing-doc style rules + the lint extension contract.

3. **Foreground**: `pytest tests/unit/ -q`
4. **Foreground**: `pytest tests/integration/ -m kg -q`
5. **Foreground**: `pytest tests/regression/ -m kg -q`
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
