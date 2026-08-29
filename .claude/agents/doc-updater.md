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
3. Example `call:`s use real inputs (verify against the live KG). Do NOT hand-type `response:` blocks —
   fill them from the live KG: `uv run python scripts/refresh_examples.py --write {name}`, then
   `--check --tool {name}` must report no `drift` / `empty` / `error`. Mark an example
   `illustrative: true` (+ `note:`) only when its point cannot be reproduced live.
   Quote vocabulary values at most once and point at `list_filter_values`; a KG number quoted in
   prose needs an `inputs/lint/kg_claims.yaml` entry. Renamed/removed identifiers go into
   `inputs/lint/stale_identifiers.yaml`.
4. Regenerate the about markdown:
   `uv run python scripts/build_about_content.py {name}`
5. If the spec touches analysis utilities, hand-edit the matching `references/analysis/*.md` and the corresponding `examples/*.py` — every Python snippet you leave in an analysis md must have been executed against the live KG.
6. Update the CLAUDE.md tool-table row for the tool: one routing sentence (what + when vs siblings) + the 3-5 load-bearing field names; ≤ 700 chars, no `§` refs, no config internals, no changelog phrasing. Detail lives on the page.
7. Before reporting back, run scoped pytest and confirm green:
   - `pytest tests/unit/test_about_content.py tests/unit/test_docs_lint.py -q`
   - `pytest tests/integration/test_about_examples.py -m kg -q -k {name}`
   - If analysis md changed: `pytest tests/unit/test_analysis_about_content.py -q` and `pytest tests/integration/test_examples.py -m kg -q`
8. Report `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED` per `superpowers:subagent-driven-development`.

## Out of scope

- Do not edit Python source under `multiomics_explorer/api/`, `kg/`, `mcp_server/`, or `analysis/`.
- Do not edit test files.
- Do not edit the generated `references/tools/*.md` directly — regenerate from YAML.
- Do not change the spec — flag scope concerns instead.
