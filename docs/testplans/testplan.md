# Multiomics Explorer — Test Plan

## Current State

**Existing tests (452 LOC across 4 files):**

| File | Tests | Neo4j? |
|------|-------|--------|
| `tests/unit/test_settings.py` | 4 unit tests | No |
| `tests/unit/test_query_builders.py` | 19 unit tests (all 9 builders) | No |
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

### 2. Integration Tests (Neo4j required, `@pytest.mark.kg`)

#### `tests/integration/test_mcp_tools.py` — MCP tools end-to-end (P1)

- [x] `get_schema()` returns node counts and relationship types
- [x] `find_gene()` with invalid Lucene syntax triggers fallback (not crash)
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

- [x] `get_gene()` with empty string identifier
- [x] `search_genes()` with special characters in search term
- [x] `query_expression()` with conflicting filters (returns empty, no crash)
- [x] `run_cypher()` with syntax-invalid Cypher (returns Neo4j error, no crash)
- [x] `get_gene_details()` for gene with no protein/no homologs

### 4. Regression Expansion (P2)

Add cases to `tests/evals/cases.yaml`:

- [x] `find_gene` full-text search (currently untested in evals)
- [x] `compare_conditions` cross-strain comparison
- [x] `get_homologs` with expression data included

---

## Priority Summary

| Priority | Area | Rationale |
|----------|------|-----------|
| **P0** | Write-blocking in `run_cypher` | Safety-critical — prevents accidental graph mutation |
| **P1** | Schema diffing unit tests | Key for detecting KG rebuild breakage |
| **P1** | MCP tool error paths | Prevents crashes exposed to Claude Code users |
| **P2** | CLI command smoke tests | Ensures CLI remains functional |
| **P2** | Eval case expansion | Fills gaps in `find_gene`, `compare_conditions` |
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

## Change Log

| Date | Change |
|------|--------|
| 2026-03-13 | Initial test plan created |
| 2026-03-13 | Implemented P0 write-blocking (26 tests) and P1 schema diffing (18 tests) — all 44 passing |
| 2026-03-13 | Implemented P1 integration (13 tests), P2 CLI (5 tests), P2 eval expansion (4 cases), edge cases — 123/123 passing |
| 2026-03-13 | Implemented P3 connection tests (3), P3 MCP server lifespan tests (3), P1 conflicting-filters edge case — 76 unit tests passing, test plan complete |
