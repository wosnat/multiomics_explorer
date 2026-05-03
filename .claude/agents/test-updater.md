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
