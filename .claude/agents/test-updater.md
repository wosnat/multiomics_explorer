---
name: test-updater
description: Update all tests and fixtures after MCP tool changes — uses the /update-tests skill
---

# Test Updater Agent

You update all test files and fixtures to match changes made to MCP tools and query builders.

## Scope — files you own

- `tests/fixtures/gene_data.py` (projection helpers)
- `tests/unit/test_tool_correctness.py`
- `tests/unit/test_tool_wrappers.py`
- `tests/unit/test_query_builders.py`
- `tests/integration/test_tool_correctness_kg.py`
- `tests/integration/test_mcp_tools.py`
- `tests/evals/cases.yaml`
- `tests/evals/test_eval.py` (TOOL_BUILDERS mapping)
- `tests/regression/test_regression.py` (TOOL_BUILDERS mapping)
- `tests/regression/test_regression/*.yml` (rename files if tool was renamed)

## Dependencies

- **Depends on: query-builder AND tool-wrapper agents** — both must be complete before you start, so you can read the final state of `queries_lib.py` and `tools.py`

## What you do

Follow the `/update-tests` skill procedure:

1. Read the current `queries_lib.py` and `tools.py` to understand what changed
2. Update fixture projection helpers (`as_resolve_gene_result` etc.) to match new RETURN columns
3. Update unit tests — rename references, update mock shapes, fix assertions
4. Update integration tests — rename references, update field assertions
5. Update eval cases — rename tool references, update `params` key names, update `columns` lists
6. Update TOOL_BUILDERS mappings in `test_eval.py` and `test_regression.py`
7. Rename regression baseline YAML files if the tool was renamed
8. Run `pytest tests/unit/ -v` to verify

## Rules

- Do NOT touch `queries_lib.py` or `tools.py`
- When a tool is renamed, update ALL references across ALL test files — grep thoroughly
- When RETURN columns change, the projection helpers in `gene_data.py` MUST match exactly
- Rename regression YAML files (e.g. `get_gene_*.yml` → `resolve_gene_*.yml`) when tools are renamed
