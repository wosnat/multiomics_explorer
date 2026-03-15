# Code Review Fixes Tracker

## High Priority

### Security & Safety
- [x] 1. Switch `execute_query` to `session.execute_read()` in connection.py
- [x] 2. Add `FOREACH`, `LOAD CSV` to write blocklist; broaden `CALL` pattern in tools.py
- [x] 3. Add write protection to CLI `cypher` command (reuse `_WRITE_KEYWORDS` from tools.py)
- [x] 4. Narrow `find_gene` exception catch to `neo4j.exceptions.ClientError` in tools.py
- [x] 5. Fix `verify_connectivity` to catch only `ServiceUnavailable`+`AuthError` in connection.py
- [x] 6. Add try/except to CLI `cypher` and `query` commands in main.py

### Resource Management
- [x] 7. Use context manager for `GraphConnection` in CLI `interactive()` command
- [x] 8. Add threading lock for lazy driver init in connection.py

## Medium Priority

### Correctness
- [x] 10. Fix `_fmt` truthiness check: `if limit:` → `if limit is not None:`
- [x] 12. Cache `get_settings()` with `@lru_cache`

### Query Builders
- [x] 13. Guard `build_query_expression` and `build_compare_conditions` against empty WHERE clauses

## Low Priority

### Code Quality
- [x] 14. Add `ctx: Context` type annotations to all tool functions
- [x] 15. Remove unnecessary f-string prefixes in cli/main.py

## Unit Tests

- [x] 16. Fix `test_limit_capped_at_50` — verify call_args instead of `assert True`
- [x] 17. Add test for `find_gene` double-failure (both calls raise)
- [x] 18. Add wrapper tests for untested params: `find_gene(organism, min_quality)`, `query_expression(direction, include_orthologs, min_log2fc, max_pvalue)`, `compare_conditions(conditions)`
- [x] 19. Add tests for `run_cypher`: FOREACH, LOAD CSV, CALL procedure blocking + Neo4j error propagation
- [x] 22. Fix existing tests broken by narrowed exception handling (connection test, _fmt test)
