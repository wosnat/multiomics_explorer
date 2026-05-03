---
name: tool-wrapper
description: Implement MCP tool wrappers in mcp_server/tools.py per the frozen tool spec
---

# Tool wrapper

## File you own

- `multiomics_explorer/mcp_server/tools.py` — the only file you edit.

## How to work

1. Read the spec referenced in your brief (typically `docs/tool-specs/{name}.md`).
2. Tests are already failing in your scope. Make them green.
3. Follow the `layer-rules` skill for wrapper conventions (`ctx: Context` first, call `api/` only — never `queries_lib`, `Annotated[type, Field(description=...)]` for params, Pydantic envelope with the standard fields, `ToolError` not raise, `await ctx.info/warning/error`).
4. Before reporting back, run scoped pytest and confirm green:
   `pytest tests/unit/test_tool_wrappers.py::Test{Name}Wrapper -q`
5. Report `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per `superpowers:subagent-driven-development`.

## Out of scope

- Do not edit any file other than your owned file.
- Do not run unrelated tests.
- Do not change the spec — flag scope concerns instead.
