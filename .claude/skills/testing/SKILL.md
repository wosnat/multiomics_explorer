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
| `tests/unit/test_about_content.py` | About-file consistency with Pydantic schemas (expected-keys, param names) | No |
| `tests/integration/test_cyver_queries.py` | CyVer schema/property validation of all builders | Yes |
| `tests/integration/test_tool_correctness_kg.py` | Fixture-based correctness (live KG) | Yes |
| `tests/integration/test_mcp_tools.py` | MCP smoke tests | Yes |
| `tests/integration/test_api_contract.py` | API return-type contracts (shape + keys) | Yes |
| `tests/integration/test_about_examples.py` | About-content examples execute against KG | Yes |
| `tests/integration/test_edge_case_contracts.py` | Corner-case matrix: every tool × degenerate inputs vs. structural invariants + coverage gate | Yes |
| `tests/integration/edge_cases/test_fixture_guards.py` | Degenerate-fixture self-validation (re-pin after KG rebuild) | Yes |
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

## Important: API contract tests

When changing the return shape of any `api/functions.py` function, update the
corresponding `Test{Name}Contract` class in `tests/integration/test_api_contract.py`.
These tests capture the pre-change shape and will silently fail otherwise.

## Important: CyVer builder coverage

When adding a new query builder, add it to the `_BUILDERS` list in
`tests/integration/test_cyver_queries.py` with representative args.
If the builder introduces new map projection keys (e.g. `{alias: g.property}`),
add the alias to `_KNOWN_MAP_KEYS`. Ontology-dependent builders auto-expand
via the `ONTOLOGY_CONFIG` loop — no per-ontology entries needed.

## Important: corner-case scenarios

When adding a tool, add a `{name}_scenarios()` builder and register it in
`SCENARIO_BUILDERS` in `tests/integration/edge_cases/scenarios.py`. The
`test_every_tool_has_edge_scenarios` coverage gate fails until the tool is
registered (or added to `_EXEMPT` for a no-entity-input tool like `kg_schema`).

- A `Scenario(label, kwargs, expects_error=None, input_ids=[])` runs the MCP
  wrapper with `kwargs` and checks the response against the invariant oracle
  (`edge_cases/invariants.py`): no crash, schema-valid, count-consistent,
  `not_found`/`not_matched` ⊆ inputs, empty-layer shape (offset-aware).
- Pick degenerate inputs from `edge_cases/fixtures.py` across the four axes:
  empty data layer (genome-only / expression-empty organism, no-DE /
  coordinate-less gene), missing & mixed batch, pagination/filter-empty,
  null props. Set `expects_error=ToolError` for documented raises; set
  `input_ids` only when the tool exposes a FLAT `not_found`/`not_matched` list.
- Add a new fixture (+ a guard in `test_fixture_guards.py`) only if no existing
  degenerate fixture fits; pin it with its discovery cypher in a comment.

This enforces the `layer-rules` "empty-data-layer safety" convention.

## Important: KG char escaping

KG text fields use character substitution (`'` → `^`, `|` → `,`).
Use `_kg_escape()` in integration tests when comparing text fields.
