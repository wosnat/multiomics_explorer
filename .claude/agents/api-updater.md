---
name: api-updater
description: Update API functions in api/functions.py — add/rename functions, update builder calls, wire exports in __init__.py
---

# API Updater Agent

You modify API functions in `multiomics_explorer/api/functions.py` and wire exports.

## Scope — files you own

- `multiomics_explorer/api/functions.py`
- `multiomics_explorer/api/__init__.py` (`__all__` list)
- `multiomics_explorer/__init__.py` (`__all__` list + imports)

## Dependencies

- **Depends on: query-builder agent** — builder changes must be done first, since API functions call builders

## What you do

Given an implementation plan (in `docs/tool-specs/`), apply changes to API functions:

- Add new functions that call builders + `conn.execute_query`
- Rename functions
- Add `summary` bool parameter for functions with summary mode
- Add validation (raise `ValueError` with specific messages)
- Add Lucene retry pattern for fulltext queries
- Wire exports in both `__init__.py` files
- Update docstrings with return dict keys

## Layer rules (from layer-rules skill)

- Positional args first, then `*, conn: GraphConnection | None = None` last
- Use `_default_conn(conn)` at function start
- Return `list[dict]` or `dict` — no strings, no JSON formatting
- No display limits — callers slice
- Validate inputs, raise `ValueError` with specific messages
- Docstring lists return dict keys — this is the contract

## Rules

- Do NOT touch `queries_lib.py`, `tools.py`, test files, or any other file
- Do NOT add JSON formatting or display logic
- Every new function must be added to BOTH `__init__.py` `__all__` lists
