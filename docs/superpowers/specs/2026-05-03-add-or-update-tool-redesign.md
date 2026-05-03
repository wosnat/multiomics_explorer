# `add-or-update-tool` skill redesign

**Date:** 2026-05-03
**Status:** Design (approved in brainstorm)
**Driver:** Tool build flow is too heavy. Code review gets skipped. No real
TDD. Skill needs to handle two different work shapes (deep single-tool vs.
cross-tool small change) with one orchestration.

## Goals

- Cut Phase 2 wallclock by parallelizing the 4 layers (file-ownership-safe).
- Bake TDD discipline (RED → GREEN → REFACTOR) into Phase 2 instead of
  optional gates.
- Make code review automatic, not skippable.
- Reuse `superpowers:` skills where they already cover the discipline; keep
  project-specific custom only where the KG/explorer truth lives.
- Handle cross-tool small changes (e.g. "add filter X to N tools") without a
  separate skill — same orchestration, broader briefing per agent.

## Non-goals

- Phase 1 (define / KG explore / Cypher verify) is *thinking time* and stays
  user-driven. No compression here.
- Permission allowlist cleanup is independent — handled by a sidecar pass
  using `/fewer-permission-prompts`.

## Two execution modes

The skill detects which mode applies from the spec:

| Mode | Trigger | Phase 1 cost | Phase 2 shape |
|---|---|---|---|
| A: single tool deep build | One tool, new or significant change | Heavy (KG iteration) | One entity per agent |
| B: cross-tool small change | Spec names ≥2 tools | Light (one-page spec) | N entities per agent |

Both modes use the same agent topology. Only the briefing volume differs.

## Agent topology — layer-cut, file ownership

Files in this codebase are layer-organized: one file per concern. So the
parallel cut is by file. Each agent owns its file and never edits another's.
Layer ownership is collision-safe by construction.

| Agent | Files owned | Self-verify scope |
|---|---|---|
| `query-builder` | `multiomics_explorer/kg/queries_lib.py` | `pytest tests/unit/test_query_builders.py::TestBuild{Name} -q` |
| `api-updater` | `multiomics_explorer/api/functions.py`, `api/__init__.py`, `multiomics_explorer/__init__.py`, **plus `multiomics_explorer/analysis/*.py`** when analysis utilities change | `pytest tests/unit/test_api_functions.py::Test{Name} -q` (+ `tests/unit/test_analysis.py -q` when analysis touched) |
| `tool-wrapper` | `multiomics_explorer/mcp_server/tools.py` | `pytest tests/unit/test_tool_wrappers.py::Test{Name}Wrapper -q` |
| `doc-updater` | `multiomics_explorer/inputs/tools/{name}.yaml` (regenerates `skills/.../tools/{name}.md` via `build_about_content.py`); `skills/.../references/analysis/{name}.md` (hand-edited); `examples/{name}.py` (hand-edited) | `pytest tests/integration/test_about_examples.py -m kg -q` and `pytest tests/integration/test_examples.py -m kg -q` and `pytest tests/unit/test_analysis_about_content.py -q` |
| `test-updater` | `tests/unit/test_query_builders.py`, `tests/unit/test_api_functions.py`, `tests/unit/test_tool_wrappers.py`, `tests/regression/cases.yaml`, also updates `EXPECTED_TOOLS` and `TOOL_BUILDERS` registries | (writes RED tests; Stage 3 self-verify is downstream of GREEN agents) |

Code review is the standard `code-reviewer` subagent (built-in via
`superpowers:requesting-code-review`). Dispatched in background at the start
of Stage 3.

## Reuse map — superpowers vs. custom

What we delegate to `superpowers:` skills:

| Concern | Superpowers skill |
|---|---|
| Phase 1 scope brainstorm | `superpowers:brainstorming` |
| Phase 1 plan from spec | `superpowers:writing-plans` |
| Phase 2 RED → GREEN discipline | `superpowers:test-driven-development` |
| Phase 2 parallel dispatch | `superpowers:dispatching-parallel-agents` (inside `superpowers:subagent-driven-development` orchestration) |
| Code review | `superpowers:requesting-code-review` |
| Verify before claiming done | `superpowers:verification-before-completion` |
| Branch isolation (optional) | `superpowers:using-git-worktrees` |
| Branch close + PR | `superpowers:finishing-a-development-branch` |

What stays project-custom:

- `layer-rules` skill — Cypher conventions, ORDER BY, `$param`, organism
  filter, file ownership map. Project's most important skill today.
- `testing` skill — per-layer test patterns, `EXPECTED_TOOLS`, `TOOL_BUILDERS`,
  fixtures, char-escape rules.
- `add-or-update-tool` skill — thinned to an orchestrator shim that wires the
  superpowers skills to project specifics.
- 5 project agents (`query-builder`, `api-updater`, `tool-wrapper`,
  `doc-updater`, `test-updater`) — slimmed to ~15 lines each: file ownership +
  pointer to `layer-rules` + TDD discipline + self-verify command.

Note on parallel-implementer red flag: `superpowers:subagent-driven-development`
warns against parallel implementer dispatch because of file collisions. Our
layer-cut is collision-safe (each agent owns one file). The slimmed skill
documents this explicitly so the orchestrator dispatches in parallel with
confidence.

## Phase 2 flow

```
Phase 1 → frozen spec at docs/tool-specs/{name}.md
                   ↓
       Optional: superpowers:using-git-worktrees
                   ↓
       Stage 1 (RED): dispatch test-updater
                   ↓
       pytest tests/unit/ -q  →  expect new tests RED
                   ↓
       Stage 2 (GREEN): dispatch 4 agents in parallel
         query-builder | api-updater | tool-wrapper | doc-updater
       (each self-verifies scoped pytest before reporting)
                   ↓
       Stage 3 (VERIFY):
         - background: dispatch code-reviewer agent
         - foreground: pytest tests/unit/ -q
         - foreground: pytest tests/integration/ -m kg -q
         - foreground: pytest tests/regression/ -m kg -q
                       (--force-regen only if columns changed per spec)
                   ↓
       superpowers:finishing-a-development-branch
```

## Stage detail

### Stage 1 — RED

`test-updater` is briefed with the frozen spec. Writes failing tests across
`test_query_builders.py`, `test_api_functions.py`, `test_tool_wrappers.py`,
plus updates `EXPECTED_TOOLS` and `TOOL_BUILDERS` registries.

Orchestrator runs `pytest tests/unit/ -q`. Expectation: exactly the new
tests are red, nothing else broke. If unrelated red appears, halt and
investigate before Stage 2.

### Stage 2 — GREEN (parallel)

Single dispatch message containing 4 parallel agent invocations. Each agent
gets:

- The frozen spec
- A pointer to its file (the only file it may edit)
- A pointer to `layer-rules` skill
- The TDD instruction: "tests already failing in your scope; make them green
  without touching other files"
- Its self-verify command (from the table above)

Each agent reports `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per
`superpowers:subagent-driven-development` semantics.

For Mode B (cross-tool), each agent's brief gains: "Implement tool 1 first
as the template within your file; then extend the pattern to tools 2..N."
No coordination between agents needed — each is serial within its own file.

### Stage 3 — VERIFY

Once all 4 agents report green:

1. **Background**: dispatch `code-reviewer` against the diff using
   `superpowers:requesting-code-review`.
2. **Foreground**: `pytest tests/unit/ -q` (full unit suite).
3. **Foreground**: `pytest tests/integration/ -m kg -q`.
4. **Foreground**: `pytest tests/regression/ -m kg -q`. If the spec declared
   new or renamed columns, run with `--force-regen` first, then verify.

Code review report returns during/after KG tests. Either lands clean or
triggers one fix loop (re-dispatch the relevant agent with the review
feedback as additional brief).

Total pytest invocations in the orchestrator: **3** (down from 7+ today).
Each agent runs one scoped pytest internally during self-verify.

### Mode B note: helper changes

When a cross-tool change involves a new helper (e.g. `_compartment_where()`
shared across N builders), the same `query-builder` agent owns both the
helper and all N builders within `queries_lib.py`. The agent serializes its
own work within its file; no orchestrator-level pre-step needed.

## CLAUDE.md pointer (discoverability)

CLAUDE.md is currently silent on skills. Add one line under the MCP Server
section so that any starting point (brainstorming, writing-plans, raw chat)
delegates tool work to the right skill:

> When adding or modifying an MCP tool, use the `add-or-update-tool` skill —
> it orchestrates Phase 1 (scope + KG iteration + Cypher verification) and
> Phase 2 (parallel TDD build).

## Skill thinning — what changes in `.claude/skills/add-or-update-tool/`

Current `SKILL.md` is ~325 lines. Target: ~120 lines.

Cuts:
- Remove restated layer rules (live in `layer-rules` skill)
- Remove restated test patterns (live in `testing` skill)
- Remove "Optional: parallelize with agents" prose — now the default
- Remove sequential per-layer gate instructions — replaced by Stage 1/2/3
- Remove "Cascading renames" table — moves to `layer-rules` skill where
  it's more discoverable

Keeps + adds:
- Phase 1 KG-iteration steps (project-specific, not in superpowers)
- `Deciding result-size controls` table (project-specific)
- The Stage 1/2/3 flow with explicit superpowers skill invocations
- Mode A vs. Mode B detection rule and briefing addendum
- Pointer to `field-rubric` and `kg-spec-template` / `tool-spec-template`
  assets (unchanged)

## Agent thinning — what changes in `.claude/agents/`

Each of the 5 agent .md files goes from ~45 lines to ~15 lines. Removes
duplicated layer-rules content. Each agent ends up with:

```
---
name: <agent-name>
description: <one-line scope>
---

# <Agent name>

## File you own

- `<file path>` — the only file you edit.

## How to work

1. Read the spec referenced in your brief.
2. Tests are already failing in your scope. Make them green.
3. Follow the `layer-rules` skill for conventions.
4. Before reporting back, run: `<scoped pytest command>` and confirm green.
5. Report `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per
   `superpowers:subagent-driven-development`.

## Out of scope

- Do not edit any file other than your owned file.
- Do not run unrelated tests.
- Do not change the spec — flag scope concerns instead.
```

The custom `code-reviewer` agent in `.claude/agents/code-reviewer.md` is
replaced by the standard built-in `code-reviewer` subagent invoked via
`superpowers:requesting-code-review`. The custom file can be deleted (or
kept as a thin alias if other places reference it by name).

## Out of scope (sidecar work)

- **Permission allowlist cleanup**: independent one-shot pass using
  `/fewer-permission-prompts` to expand `Read` and other narrow patterns
  in `.claude/settings.local.json`. One commit. Tracked separately.
- **Custom `code-review` skill**: superseded by
  `superpowers:requesting-code-review`. Keep or remove based on whether
  other skills reference it.

## Implementation order

1. Land this spec on `main` (`docs(spec):` commit).
2. Branch `feat/skill-redesign-add-or-update-tool`.
3. Slim the 5 project agents (single PR layer).
4. Slim `add-or-update-tool/SKILL.md` (single PR layer).
5. Add the CLAUDE.md pointer (one-line edit).
6. Verify against the next real tool build (`list_metabolites` Phase 2 is
   the natural smoke test — Mode A end-to-end).
7. Iterate based on what falls out of that first run.

## Validation

The redesign succeeds if, on `list_metabolites` Phase 2:
- Stage 2 wallclock is dominated by the slowest agent, not the sum of 4.
- Code review report arrives without an explicit "now run code review" step.
- Total orchestrator pytest invocations ≤ 3 (excluding agent self-verifies).
- Mode B can later land a "compartment filter to N tools" sweep without a
  separate skill.

If any of these fail on the first real run, revisit the design before the
next tool.
