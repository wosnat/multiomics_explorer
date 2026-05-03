---
name: query-builder
description: Implement query builders in queries_lib.py per the frozen tool spec
---

# Query builder

## File you own

- `multiomics_explorer/kg/queries_lib.py` — the only file you edit.

## How to work

1. Read the spec referenced in your brief (typically `docs/tool-specs/{name}.md`).
2. Tests are already failing in your scope. Make them green.
3. Follow the `layer-rules` skill for Cypher conventions (`$param`, `AS` aliases, `ORDER BY`, organism filter, builder return tuple).
4. Before reporting back, run scoped pytest and confirm green:
   `pytest tests/unit/test_query_builders.py::TestBuild{Name} -q`
5. Report `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per `superpowers:subagent-driven-development`.

## Out of scope

- Do not edit any file other than your owned file.
- Do not run unrelated tests.
- Do not change the spec — flag scope concerns instead.
