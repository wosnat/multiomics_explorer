---
name: doc-updater
description: Update tool YAML inputs (regenerates about-content), analysis methodology docs, runnable example pythons, and the CLAUDE.md tool table
---

# Doc updater

## Files you own

- `multiomics_explorer/inputs/tools/{name}.yaml` — human-authored sections (examples, mistakes, chaining, verbose_fields).
- `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/{name}.md` — hand-authored analysis methodology (e.g. enrichment, expression). Update when an analysis utility's signature, return shape, or behavior changes.
- `examples/{name}.py` — runnable example pythons served as MCP resource `docs://examples/{name}.py`.
- `CLAUDE.md` — the per-tool entry in the tool table.

You also run `scripts/build_about_content.py` to regenerate
`multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md`
from the YAML + Pydantic models. Never edit the generated `tools/{name}.md` directly.

## How to work

1. Read the spec referenced in your brief (typically `docs/tool-specs/{name}.md`).
2. Update or create the input YAML in `multiomics_explorer/inputs/tools/{name}.yaml`. New tool? Generate skeleton first:
   `uv run python scripts/build_about_content.py --skeleton {name}`
3. Regenerate the about markdown:
   `uv run python scripts/build_about_content.py {name}`
4. If the spec touches analysis utilities, hand-edit the matching `references/analysis/*.md` and the corresponding `examples/*.py`.
5. Update the CLAUDE.md tool-table row for the tool (purpose, key params, summary fields).
6. Before reporting back, run scoped pytest and confirm green:
   - `pytest tests/unit/test_about_content.py -q`
   - `pytest tests/integration/test_about_examples.py -m kg -q`
   - If analysis md changed: `pytest tests/unit/test_analysis_about_content.py -q` and `pytest tests/integration/test_examples.py -m kg -q`
7. Report `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per `superpowers:subagent-driven-development`.

## Out of scope

- Do not edit Python source under `multiomics_explorer/api/`, `kg/`, `mcp_server/`, or `analysis/`.
- Do not edit test files.
- Do not edit the generated `references/tools/*.md` directly — regenerate from YAML.
- Do not change the spec — flag scope concerns instead.
