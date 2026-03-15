---
name: update-tests
description: Update correctness tests after MCP tool changes (new params, renamed fields, changed query logic). Use when tool signatures, query builders, or return shapes have changed.
disable-model-invocation: true
argument-hint: "[tool-name or 'all']"
---

# Update Correctness Tests After Tool Changes

You are updating the test suite to match changes made to MCP tools or query builders.

## Scope

If `$ARGUMENTS` names a specific tool (e.g., `resolve_gene`, `query_expression`), only update tests for that tool. If `$ARGUMENTS` is `all` or empty, audit every tool.

## Step 1: Detect what changed

Compare the current tool/query code against what the tests expect:

1. Read `multiomics_explorer/mcp_server/tools.py` — check each tool's signature (params, defaults, return format)
2. Read `multiomics_explorer/kg/queries_lib.py` — check each builder's Cypher, returned columns, and param names
3. Read the projection helpers in `tests/fixtures/gene_data.py` (`as_resolve_gene_result`, `as_search_genes_result`) — do they match the current RETURN columns?

List every discrepancy found.

## Step 2: Update fixtures

If RETURN columns changed, update:
- `tests/fixtures/gene_data.py` — the `as_resolve_gene_result()` and `as_search_genes_result()` helpers must match the current query RETURN columns exactly
- Also update `scripts/build_test_fixtures.py` so re-running it produces the correct helpers

## Step 3: Update unit tests

File: `tests/unit/test_tool_correctness.py`

For each changed tool:
- Update mock return shapes to match new RETURN columns
- Add/remove test cases if params were added/removed
- Update assertions on field names, JSON structure, or error messages
- If a param was renamed, update all `call_args` assertions

Also check `tests/unit/test_tool_wrappers.py` and `tests/unit/test_query_builders.py` for the same tool.

## Step 4: Update KG integration tests

File: `tests/integration/test_tool_correctness_kg.py`

- Update assertions on returned field names
- Add tests for new params/filters
- Remember: KG data has char escaping (`'` -> `^`, `|` -> `,`), use `_kg_escape()` when comparing text fields

Also check `tests/integration/test_mcp_tools.py`.

## Step 5: Update eval/regression cases

File: `tests/evals/cases.yaml`

- Update `columns` lists if RETURN fields changed
- Update `row0` / `contains` assertions if field names changed
- Add new cases for new tool params

The tool-to-builder mapping in `tests/regression/test_regression.py` (`TOOL_BUILDERS` dict) may also need updating.

## Step 6: Verify

Run all tests and fix any failures:

```bash
pytest tests/unit/ -v
pytest tests/integration/ -v -m kg
pytest tests/regression/ -m kg
```

If regression baselines need updating after intentional changes:
```bash
pytest tests/regression/ --force-regen -m kg
```

## Key files reference

| File | Purpose |
|------|---------|
| `multiomics_explorer/mcp_server/tools.py` | Tool implementations (signatures, wrappers) |
| `multiomics_explorer/kg/queries_lib.py` | Query builders (Cypher, params, RETURN columns) |
| `tests/fixtures/gene_data.py` | Fixture data + projection helpers |
| `scripts/build_test_fixtures.py` | Fixture generator script |
| `tests/unit/test_tool_correctness.py` | Mocked correctness tests (54 tests) |
| `tests/unit/test_tool_wrappers.py` | Tool wrapper logic tests |
| `tests/unit/test_query_builders.py` | Query builder structure tests |
| `tests/integration/test_tool_correctness_kg.py` | KG integration correctness tests (49 tests) |
| `tests/integration/test_mcp_tools.py` | KG integration smoke tests |
| `tests/evals/cases.yaml` | Eval/regression test case definitions (36 cases) |
| `tests/regression/test_regression.py` | Regression test runner + TOOL_BUILDERS map |
