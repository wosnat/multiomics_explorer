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
Tool docstrings + every `Field(description=...)` are agent-outfacing
— follow the 9 outfacing-doc rules (see [layer boundaries](references/layer-boundaries.md)
and [readability-pass spec](../../../docs/superpowers/specs/2026-05-07-mcp-docs-readability-pass-design.md)).
Inline `# ...` Python comments are not.

## Layer 4: Skills (MCP resources)

Per-tool about content auto-generated from Pydantic models + input
YAML (`inputs/tools/{name}.yaml`) via `scripts/build_about_content.py`.
Served at `docs://tools/{tool-name}`. Update YAML when tool behavior
changes, then rebuild — the generator writes directly to the skills
tree. **Never hand-edit rendered md.** YAML examples / mistakes /
chaining follow the same 9 outfacing-doc rules as Layer 3. After regen,
run `uv run python scripts/build_about_content.py --lint {tool_name}`.

## Cross-layer: empty-data-layer safety

The KG holds entities that exist genomically but lack a data layer —
genome-only / metabolomics-only organisms (no expression), genes with no
DE / orthologs / chemistry / DMs, coordinate-less genes. Every tool must
return a well-formed **empty** envelope for these — never crash, never mislead:

- **Layer 1 (builders):** summary/stat queries must aggregate
  (`count` / `collect` / `apoc.coll.frequencies`) so they return exactly one
  row even on empty input — never a bare per-row projection that a Layer-2
  `[0]` would index into. When a projected value feeds a **non-nullable**
  Pydantic field, filter nulls in the builder
  (`[x IN collect({...}) WHERE x.field IS NOT NULL]`) — a synthetic null (e.g.
  from `UNWIND CASE WHEN size(xs)>0 THEN xs ELSE [null] END`) crashes model
  construction at Layer 3.
- **Layer 2 (api):** index query results empty-safe (`rows[0] if rows else {}`);
  default counts to `0`, lists to `[]`. Entity/organism resolvers gate on
  *genomic* presence (e.g. `OrganismTaxon.gene_count > 0`), never on
  *expression* (`Experiment`) data — gating genomic lookups on expression made
  genome-only strains unresolvable.
- **Layer 3 (wrappers):** an empty data layer is a normal result
  (`total_matching=0`, `results=[]`), not a `ToolError`.

Enforced by the corner-case harness (`tests/integration/edge_cases/` +
`test_edge_case_contracts.py`): every tool has degenerate-input scenarios
checked against structural invariants, with a coverage gate. See the `testing`
skill and the `add-or-update-tool` skill (Stage 1) for how to add scenarios.

## Analysis utilities (`analysis/expression.py`)

Compose API results into DataFrames. Reference docs live in
`skills/multiomics-kg-guide/references/analysis/`. When function
signatures, return shapes, or behavior change → update corresponding
reference doc. Served at `docs://analysis/{name}`.
