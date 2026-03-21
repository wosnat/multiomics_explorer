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
| 2. API functions | `api/functions.py` | `list[dict]` or `dict` | Format JSON, apply display limits, import from mcp_server/ |
| 3. MCP wrappers | `mcp_server/tools.py` | `list[dict]` or `dict` | Call queries_lib directly, return error strings (use ToolError) |
| 4. Skills | `skills/*/references/tools/*.md` | Markdown content | Contain stale examples, disagree with tool behavior |

## Layer 1: `kg/queries_lib.py`

Pure Cypher builders. `def build_{name}(*, ...) -> tuple[str, dict]`.
Keyword-only args. `$param` placeholders. `AS snake_case` aliases.
No execution, no formatting, no imports from upper layers.

## Layer 2: `api/functions.py`

Build + execute. Positional args, then `*, conn: GraphConnection | None = None`.
Validates inputs (raises `ValueError`). Handles Lucene retry for fulltext queries.
Re-exported from `multiomics_explorer/__init__.py`.

## Layer 3: `mcp_server/tools.py`

Wraps api/ only. `@mcp.tool(tags={...}, annotations={"readOnlyHint": True})`
inside `register_tools(mcp)`. First param `ctx: Context`.
Use `Annotated[type, Field(description=...)]` for param descriptions.
Use `ToolError` for errors (not error strings). Logs every call.

## Layer 4: Skills

About-mode content in `skills/multiomics-kg-guide/references/tools/{tool-name}.md`.
Uses `example-call`, `expected-keys` tagged blocks for testable examples.
Update when tool behavior changes. Sync via `scripts/sync_skills.sh`.
