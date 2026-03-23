---
name: testing
description: Per-layer test requirements and patterns. Reference when writing, updating, or debugging tests for MCP tools, query builders, or API functions.
argument-hint: "[test layer or tool, e.g. 'unit', 'integration', 'regression', or tool name]"
---

# Testing

See [test checklist](references/test-checklist.md) for per-layer patterns
and [regression guide](references/regression-guide.md) for golden-file tests.

## Test file map

| File | What it tests | Neo4j? |
|---|---|---|
| `tests/unit/test_query_builders.py` | Cypher structure + params | No |
| `tests/unit/test_api_functions.py` | API logic with mocked conn | No |
| `tests/unit/test_tool_wrappers.py` | MCP wrapper Pydantic models + ToolError | No |
| `tests/unit/test_tool_correctness.py` | Fixture-based correctness (mocked) | No |
| `tests/unit/test_write_blocking.py` | Write keyword regex | No |
| `tests/integration/test_tool_correctness_kg.py` | Fixture-based correctness (live KG) | Yes |
| `tests/integration/test_mcp_tools.py` | MCP smoke tests | Yes |
| `tests/regression/test_regression.py` | Golden-file comparison | Yes |

## Test commands

```bash
# Unit tests (no Neo4j)
pytest tests/unit/ -v

# Integration tests (requires Neo4j at localhost:7687)
pytest -m kg -v

# Regression tests (requires Neo4j)
pytest tests/regression/ -m kg

# Regenerate regression baselines after intentional changes
pytest tests/regression/ --force-regen -m kg

# Single test class
pytest tests/unit/test_query_builders.py::TestBuildResolveGene -v
```

## Key fixtures

| Fixture | Scope | File | Purpose |
|---|---|---|---|
| `mock_conn` | function | `test_api_functions.py` | `MagicMock()` for GraphConnection |
| `tool_fns` | module | `test_tool_wrappers.py` | Dict of `{name: fn}` from registered tools |
| `mock_ctx` | function | `test_tool_wrappers.py` | MCP Context mock with `.conn` |
| `neo4j_driver` | session | `conftest.py` | Real driver, auto-skips if unreachable |
| `conn` | session | `conftest.py` | Real GraphConnection for integration |
| `GENES` / `GENES_BY_LOCUS` | — | `fixtures/gene_data.py` | Curated gene records |

## Important: EXPECTED_TOOLS

When adding a new tool, add its name to the `EXPECTED_TOOLS` list in
`tests/unit/test_tool_wrappers.py`. The `test_all_tools_registered` test
will fail otherwise.

## Important: TOOL_BUILDERS

When adding a new query builder for regression tests, add it to the
`TOOL_BUILDERS` dict in `tests/regression/test_regression.py`.

## Important: KG char escaping

KG text fields use character substitution (`'` → `^`, `|` → `,`).
Use `_kg_escape()` in integration tests when comparing text fields.
