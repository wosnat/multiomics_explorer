# Multiomics Explorer — Test Plan

## Current State

**Existing tests (10 files, 108+ unit + integration/eval/regression):**

| File | Tests | Neo4j? |
|------|-------|--------|
| `tests/unit/test_settings.py` | 4 unit tests | No |
| `tests/unit/test_query_builders.py` | 21 unit tests (all 10 builders) | No |
| `tests/unit/test_write_blocking.py` | 15 unit tests (regex + `_fmt`) | No |
| `tests/unit/test_schema.py` | 18 unit tests (diffing, baseline, formatting) | No |
| `tests/unit/test_connection.py` | 3 unit tests (error handling, lifecycle) | No |
| `tests/unit/test_mcp_server.py` | 3 unit tests (lifespan, KGContext) | No |
| `tests/unit/test_tool_wrappers.py` | 35 unit tests (all 9 MCP tool wrappers + registration) | No |
| `tests/integration/test_mcp_tools.py` | 13 integration tests | Yes |
| `tests/evals/test_eval.py` | 15 parameterized integration tests | Yes |
| `tests/regression/test_regression.py` | 15 golden-file baselines | Yes |

---

## Proposed New Tests

### 1. Unit Tests (no Neo4j needed)

#### `tests/unit/test_write_blocking.py` — Write-blocking in `run_cypher` (P0)

Safety-critical — prevents accidental graph mutation via MCP.

- [x] Rejects `CREATE` keyword
- [x] Rejects `DELETE` keyword
- [x] Rejects `MERGE` keyword
- [x] Rejects `SET` keyword
- [x] Rejects `REMOVE` keyword
- [x] Rejects `DROP` keyword
- [x] Rejects `DETACH DELETE`
- [x] Allows reads containing write-keyword substrings (e.g. `WHERE x.description CONTAINS "SET"`)
- [x] `_fmt()` formats empty results correctly
- [x] `_fmt()` formats single-row results correctly
- [x] `_fmt()` formats multi-row results correctly

#### `tests/unit/test_schema.py` — Schema diffing, baseline, formatting (P1)

Key for detecting KG rebuild breakage.

- [x] `diff_schemas()` detects added node labels
- [x] `diff_schemas()` detects removed node labels
- [x] `diff_schemas()` detects added relationship types
- [x] `diff_schemas()` detects removed relationship types
- [x] `diff_schemas()` detects property changes on nodes
- [x] `diff_schemas()` detects property changes on relationships/edges
- [x] `diff_schemas()` returns empty diff for identical schemas
- [x] `to_prompt_string()` produces valid formatted output
- [x] `save_baseline()` / `load_baseline()` round-trip correctly

#### `tests/unit/test_connection.py` — Connection error handling (P3)

- [x] `GraphConnection` raises on invalid URI
- [x] `verify_connectivity()` fails gracefully when Neo4j is down
- [x] Context manager cleans up driver on exit

#### `tests/unit/test_mcp_server.py` — Lifespan & context (P3)

- [x] `KGContext` dataclass holds connection correctly
- [x] Lifespan manager creates and closes connection
- [x] Lifespan raises `RuntimeError` when Neo4j is unreachable

#### `tests/unit/test_tool_wrappers.py` — MCP tool wrapper logic (P1)

Tests all 8 tool functions' wrapper logic (input validation, response formatting,
error messages, multi-query orchestration) with a mocked Neo4j connection.

**Tool registration:**
- [x] All 9 expected tools are registered
- [x] No unexpected extra tools

**`get_schema`:**
- [x] Calls `load_schema_from_neo4j` and returns its prompt string

**`resolve_gene`:**
- [x] Not-found returns JSON with empty results and message
- [x] Not-found with organism includes organism in message
- [x] Single match returns results without ambiguity message
- [x] Multiple matches returns results with "Ambiguous" message

**`search_genes`:**
- [x] Empty result returns JSON envelope with `results`, `total`, `query`
- [x] Non-empty result populates envelope correctly
- [x] Limit capped at 50
- [x] Lucene parse error triggers escaped retry (fallback path)

**`get_gene_details`:**
- [x] Gene not found (null gene) returns "not found" message
- [x] Gene not found (empty results) returns "not found" message
- [x] Two-query orchestration assembles `_homologs` key into result

**`query_expression`:**
- [x] No filters returns error without calling Neo4j
- [x] Empty results returns "No expression data" message
- [x] Non-empty results returns JSON array

**`compare_conditions`:**
- [x] No filters returns error without calling Neo4j
- [x] Empty results returns "No expression data" message
- [x] Non-empty results returns JSON array

**`get_homologs`:**
- [x] No homologs returns "No homologs found" message
- [x] Without expression returns JSON array of homologs
- [x] With expression merges `homologs` + `expression` into single response

**`list_filter_values`:**
- [ ] Returns combined JSON with `gene_categories` and `condition_types` keys
- [ ] Each sub-list has expected keys (`category`/`gene_count` and `condition_type`/`cnt`)
- [ ] Caching returns same result on subsequent calls

**`run_cypher`:**
- [x] Write keyword returns error message without calling Neo4j
- [x] LIMIT injected when absent from query
- [x] LIMIT not duplicated when already present
- [x] Limit parameter capped at 200
- [x] Empty results returns "no results" message
- [x] Trailing semicolon stripped before LIMIT injection

### 2. Integration Tests (Neo4j required, `@pytest.mark.kg`)

#### `tests/integration/test_mcp_tools.py` — MCP tools end-to-end (P1)

- [x] `get_schema()` returns node counts and relationship types
- [x] `search_genes()` with invalid Lucene syntax triggers fallback (not crash)
- [x] `query_expression()` with ortholog inclusion returns more rows than without
- [x] `compare_conditions()` with two conditions returns comparison data
- [x] `get_homologs()` with `include_expression=True` adds expression columns

#### `tests/integration/test_cli.py` — CLI smoke tests (P2)

- [x] `schema` command exits 0 and prints node labels
- [x] `schema-validate` passes against current baseline
- [x] `stats` command exits 0 and shows counts
- [x] `cypher` command executes a simple query and prints results

### 3. Edge Cases & Error Paths (P1)

Add to relevant unit/integration test files.

- [x] `resolve_gene()` with empty string identifier
- [x] `query_expression()` with conflicting filters (returns empty, no crash)
- [x] `run_cypher()` with syntax-invalid Cypher (returns Neo4j error, no crash)
- [x] `get_gene_details()` for gene with no protein/no homologs

### 4. Regression Expansion (P2)

Add cases to `tests/evals/cases.yaml`:

- [x] `search_genes` full-text search (currently untested in evals)
- [x] `compare_conditions` cross-strain comparison
- [x] `get_homologs` with expression data included

---

## Priority Summary

| Priority | Area | Rationale |
|----------|------|-----------|
| **P0** | Write-blocking in `run_cypher` | Safety-critical — prevents accidental graph mutation |
| **P1** | Schema diffing unit tests | Key for detecting KG rebuild breakage |
| **P1** | MCP tool wrapper logic | Validates response formatting, input validation, error messages |
| **P1** | MCP tool error paths | Prevents crashes exposed to Claude Code users |
| **P2** | CLI command smoke tests | Ensures CLI remains functional |
| **P2** | Eval case expansion | Fills gaps in `search_genes`, `compare_conditions` |
| **P3** | Connection error handling | Nice-to-have robustness |
| **P3** | LLM agent isolation tests | Blocked until `CypherAgent` is more mature |

## File Organization

```
tests/
  unit/
    test_settings.py          # existing (4 tests)
    test_query_builders.py    # existing (19 tests)
    test_write_blocking.py    # NEW — run_cypher safety
    test_schema.py            # NEW — diffing, baseline, prompt formatting
    test_connection.py        # NEW — error handling, lifecycle
    test_tool_wrappers.py     # NEW — MCP tool wrapper logic (29 tests)
  evals/
    cases.yaml                # expand with ~5 new cases
    test_eval.py              # existing
  regression/
    test_regression.py        # existing (auto-picks up new cases)
  integration/
    test_mcp_tools.py         # NEW — tool-level integration
    test_cli.py               # NEW — CLI smoke tests
```

---

### `list_filter_values` Tool Tests

#### Unit tests (`tests/unit/test_query_builders.py`)
- [ ] `build_list_gene_categories`: verify Cypher structure (MATCH Gene, gene_category)
- [ ] `build_list_condition_types`: verify Cypher structure (MATCH EnvironmentalCondition)

#### Unit tests (`tests/unit/test_tool_wrappers.py`)
- [ ] Mock both query results, verify combined JSON structure: `{"gene_categories": [...], "condition_types": [...]}`
- [ ] Verify each sub-list has expected keys
- [ ] Caching returns same result on subsequent calls

#### Integration tests (`tests/integration/test_tool_correctness_kg.py`)
- [ ] Known categories present: "Photosynthesis", "Transport", "Stress response and adaptation", "Translation"
- [ ] Known condition types present: "nitrogen_stress", "light_stress", "coculture"
- [ ] All counts > 0
- [ ] At least 20 gene categories returned
- [ ] At least 5 condition types returned

#### Eval cases (`tests/evals/cases.yaml`)
- [ ] `list_filter_values` — combined tool response
- [ ] `list_filter_values_categories` — raw_cypher snapshot of gene categories
- [ ] `list_filter_values_conditions` — raw_cypher snapshot of condition types

---

## Change Log

| Date | Change |
|------|--------|
| 2026-03-13 | Initial test plan created |
| 2026-03-13 | Implemented P0 write-blocking (26 tests) and P1 schema diffing (18 tests) — all 44 passing |
| 2026-03-13 | Implemented P1 integration (13 tests), P2 CLI (5 tests), P2 eval expansion (4 cases), edge cases — 123/123 passing |
| 2026-03-13 | Implemented P3 connection tests (3), P3 MCP server lifespan tests (3), P1 conflicting-filters edge case — 76 unit tests passing, test plan complete |
| 2026-03-13 | Added P1 MCP tool wrapper tests (29 tests) — covers input validation, response formatting, error messages, multi-query orchestration for all 8 tools — 105 unit tests passing |
| 2026-03-13 | Added `get_schema` wrapper test and tool registration smoke tests — 108 unit tests passing |
