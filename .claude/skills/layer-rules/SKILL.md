---
name: layer-rules
description: Architecture layer conventions for multiomics_explorer. Apply when writing or reviewing code in kg/, api/, or mcp_server/, or when updating skills.
argument-hint: "[optional: layer name like 'queries_lib', 'api', 'tools', or 'skills']"
---

# Layer rules

See [layer boundaries](references/layer-boundaries.md) for full details.

## Quick reference

| Layer | File | Returns | Must NOT |
|---|---|---|---|
| 1. Query builders | `kg/queries_lib.py` | `tuple[str, dict]` | Execute queries, format output, import from api/ or mcp_server/ |
| 2. API functions | `api/functions.py` | `dict` (summary fields + `results` list) | Format JSON, import from mcp_server/ |
| 3. MCP wrappers | `mcp_server/tools.py` | Pydantic model (same shape as api/ dict) | Call queries_lib directly, compute response fields (api/ owns that), return error strings (use ToolError) |
| 4. Skills | `skills/*/references/tools/*.md` | Markdown (auto-generated from Pydantic + YAML) | Contain stale examples, disagree with tool behavior |

## Layer 1: `kg/queries_lib.py`

Pure Cypher builders. `def build_{name}(*, ...) -> tuple[str, dict]`.
Keyword-only args. `$param` placeholders. `AS snake_case` aliases.
`verbose` param controls RETURN columns. APOC available — use
`apoc.coll.frequencies()` for breakdowns, `apoc.map.*` for dynamic
result construction, `apoc.convert.fromJsonMap` for JSON properties.
No execution, no formatting, no imports from upper layers.

## Layer 2: `api/functions.py`

Build + execute. Assembles the **complete response dict**: summary
fields + `results` + `returned` + `truncated` + `not_found` (for
batch tools). MCP just wraps it — no field computation in MCP.
Accepts `summary`, `verbose`, `limit`, `conn` params.
Validates inputs (raises `ValueError`). Handles Lucene retry.
Re-exported from `multiomics_explorer/__init__.py`.

## Layer 3: `mcp_server/tools.py`

Thin wrapper — calls api/, validates via `Response(**data)`.
Same params as api/ (minus `conn`, plus `ctx`). Adds default `limit`
(small, e.g. 5). `async def` with `await ctx.info/warning/error()`.
Pydantic response models → FastMCP auto-generates `outputSchema`.

## Layer 4: Skills (MCP resources)

Per-tool about content auto-generated from Pydantic models + input
YAML (`inputs/tools/{name}.yaml`) via `scripts/build_about_content.py`.
Served at `docs://tools/{tool-name}`. Update YAML when tool behavior
changes, then rebuild. Sync via `scripts/sync_skills.sh`.
