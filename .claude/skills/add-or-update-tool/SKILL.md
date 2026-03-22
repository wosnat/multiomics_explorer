---
name: add-or-update-tool
description: Complete lifecycle for adding a new MCP tool or modifying an existing one. Two phases — definition (scope, KG exploration, schema iteration) then build (query builder, API, MCP wrapper, skills (about tool), tests, docs, review).
disable-model-invocation: true
argument-hint: "[tool name and description, e.g. 'list_experiments - new tool' or 'search_genes - add min_quality param']"
---

# Add or update a tool

See [checklist](references/checklist.md) for templates and file paths.
See the **testing** skill for per-layer test patterns and fixtures.

## Phase 1: Definition (iterative, user-driven)

All steps in this phase require user review and approval before
proceeding. Do not move to Phase 2 without explicit user sign-off.

**Before starting:** ask clarifying questions about the tool's
purpose, intended behavior, expected data shape, and how it fits
into existing tool chains. Do not assume scope.

**If modifying an existing tool,** first read all 4 layers:

| Layer | What to read |
|---|---|
| queries_lib.py | Builder signature, Cypher, RETURN columns, params |
| api/functions.py | Function signature, validation, special handling |
| mcp_server/tools.py | Wrapper signature, docstring, formatting, modes |
| Skills | About content in `multiomics_explorer/skills/multiomics-kg-guide/references/tools/` |
| Tests | All test classes for this tool across test files |
| Fixtures | `tests/fixtures/gene_data.py` projection helpers if applicable |

Steps 1–2 loop until scope and KG schema are stable.

### Step 1: Define what's needed

- What the tool does (or what's changing), who calls it, what chains
  it participates in
- Decide on result-size controls — see **Deciding result-size controls**
- These requirements drive what the KG needs to support
- → **Review:** present requirements to user for feedback

#### Deciding result-size controls

Not all tools need the same controls. Choose based on result set size:

| Result size | Controls | Examples |
|---|---|---|
| Always small (<30 rows) | No modes needed. Consider `verbose` if some columns are secondary (heavy text, taxonomy hierarchies). Consider `limit` if set will grow. | `list_organisms`, `list_publications` |
| Frequently large (100+ rows) | summary + detail modes, `limit` | `query_expression`, `search_genes`, `genes_by_ontology` |

**`verbose`** (bool, default False): Controls per-row column width.
Omits secondary columns by default — heavy text (abstract, description),
taxonomy hierarchies, or other fields not needed for routing. The builder
adds/removes RETURN columns based on this flag. Orthogonal to modes —
`verbose` controls which columns, modes control which rows.

**`limit`** (int): For tools with large or growing result sets. Also
appropriate for currently-small tools expected to grow.

**summary/detail modes**: Only for large-result-set tools.
Both modes return a unified response model with breakdowns + results.
Summary: breakdowns populated, `results: []`, `truncated: True`.
Detail: breakdowns populated, results populated with LIMIT.
Both modes always run the summary query (cheap). Detail additionally
runs the detail query with LIMIT in Cypher.

**About content**: Served via MCP resource `docs://tools/{tool_name}`,
not as a tool mode parameter. Markdown files live at
`multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md`.

### Step 2: KG exploration + iteration

- Query live KG (`run_cypher`) to check whether current nodes,
  edges, properties, and data volumes support the requirements
- If schema changes needed, write a KG change spec at
  **`docs/kg-specs/kg-spec-{tool-name}.md`** using [template](assets/kg-spec-template.md)
- User coordinates with KG repo (manual — may involve KG rebuild)
- After KG changes land, re-query live KG to verify
- Refine requirements based on what the KG can actually support —
  this may reveal new needs
- → **Review:** present updated findings to user. Repeat steps 1–2.

### Output: implementation plan

Once scope and KG schema are stable, write the implementation plan at
**`docs/tool-specs/{tool-name}.md`** using
[template](assets/tool-spec-template.md). Document:
- Purpose, use cases, tool chains
- Result-size controls: modes, verbose, limit — or "none needed"
- Return field names (use standard names from layer-rules)
- Any special handling (caching, multi-query orchestration, etc.)
- → **Gate:** user approves implementation plan before proceeding
  to build.

## Phase 2: Build (gated steps)

For new tools, create at each layer. For existing tools, update.

**Optional: parallelize with agents.** For changes spanning all layers,
use the specialized agents (`.claude/agents/`) to work in parallel:
query-builder → api-updater → tool-wrapper → test-updater +
doc-updater in parallel → code-reviewer last.

### Layer 1: Query builder → `kg/queries_lib.py`

- `def build_{name}(*, ...) -> tuple[str, dict]`
- Add summary variant `build_{name}_summary()` if tool has summary mode.
  Summary builder uses `apoc.coll.frequencies()` for per-dimension
  breakdowns. For fulltext search tools, also collect `score_max` and
  `score_median`.
- If tool has `verbose`, use conditional RETURN columns (see checklist)
- Keyword-only args, `$param` placeholders, `AS snake_case` aliases
- WHERE clause: build conditions list + params dict, join with AND
- For exact-match filters where multiple values make sense, use
  `list[str] | None` with Cypher `IN`. CONTAINS filters stay as `str`.
- Every query MUST have `ORDER BY` — use natural sort key or alphabetical fallback
- APOC is available — prefer `apoc.coll.*` for aggregations over
  multi-pass UNWIND patterns
- → **Gate:** `pytest tests/unit/test_query_builders.py::TestBuild{Name} -v`

### Layer 2: API function → `api/functions.py`

- Calls builder + `conn.execute_query`
- Pass through `verbose` and/or `mode` to dispatch as applicable
- `conn: GraphConnection | None = None` as keyword-only last param
- Document return dict keys in docstring (note verbose-only keys)
- Wire exports: add to `api/__init__.py` and
  `multiomics_explorer/__init__.py` `__all__`
- → **Gate:** `pytest tests/unit/test_api_functions.py::Test{Name} -v`

### Layer 3: MCP wrapper → `mcp_server/tools.py`

- `@mcp.tool(tags={...}, annotations={"readOnlyHint": True})` inside `register_tools(mcp)`
- `ctx: Context` first, then tool params, then structural params
  (`verbose`, `mode`, `limit` as applicable)
- Use `Annotated[type, Field(description=...)]` for all params —
  descriptions go in Field, not in docstring `Args:` section
- Use `Literal["val1", "val2"]` for params with fixed valid values
  known at code time (e.g. mode, ontology). Not for KG-derived values
  (e.g. treatment_type) — those use `list_filter_values` for discovery.
- Use `Field(ge=..., le=...)` for numeric constraints (e.g. limit)
- Use `ToolError` for errors instead of returning error strings
- `async def` — tools are async. Use `await ctx.info()`, `await ctx.warning()`,
  `await ctx.error()` for MCP client-visible logging (replaces `logger.info/warning`)
- Define Pydantic `BaseModel` classes for response: `{Name}Result` (per-row)
  and `{Name}Response` (envelope). Envelope fields:
  - `total_entries` — always (total in KG)
  - `total_matching` — only for tools with filters (count after filtering)
  - `returned` — always (len of results list)
  - `truncated` — always (True if limit cut results; True in summary mode)
  - `results` — always (list of `{Name}Result`)
  For tools with summary/detail modes, use a **unified response model**.
  Add breakdown fields (e.g. `by_organism`, `by_treatment_type`) to the
  same `{Name}Response`. Both modes return the same type — summary has
  `results: []`, detail has results populated. Breakdowns always populated.
  Return type annotation → FastMCP auto-generates `outputSchema`.
- Include examples in `Field(description=...)` for all result fields
  (e.g. `"Genus (e.g. 'Prochlorococcus')"`) — helps Claude and
  researchers understand the data shape from the schema alone.
- Docstring is tool-level purpose only (when to use, what it returns) —
  return schema is in the Pydantic models, not the docstring
- Mode dispatch if tool has summary/detail modes
- → **Gate:** `pytest tests/unit/test_tool_wrappers.py::Test{Name}Wrapper -v`

### Layer 4: About content (MCP resource)

About content is auto-generated from Pydantic models + human-authored
input YAML, then served via MCP resource at `docs://tools/{name}`.

1. Create input YAML (or generate skeleton):
   ```bash
   uv run python scripts/build_about_content.py --skeleton {name}
   ```
   Edit `multiomics_explorer/inputs/tools/{name}.yaml`:

   ```yaml
   examples:
     - title: Short description of this example
       call: tool_name(param="value")        # tool call to show
       response: |                            # optional — truncated example response
         {"total_entries": 15, "results": [{"field": "value", ...}]}

     - title: Multi-step chaining example
       steps: |                               # use steps instead of call for chains
         Step 1: first_tool(param="value")
                 → what to extract from result

         Step 2: tool_name(param=extracted_value)
                 → what to do next

   verbose_fields:                            # fields only returned with verbose=True
     - abstract                               # splits per-result table in generated about
     - description

   chaining:                                  # tool flow patterns
     - "previous_tool → tool_name → next_tool"

   mistakes:                                  # notes/gotchas or wrong/right pairs
     - "plain note renders as bullet"         # → "Good to know" section
     - wrong: "len(results)  # wrong"         # → "Common mistakes" section
       right: "response['total_matching']"
   ```

2. Build the about markdown:
   ```bash
   uv run python scripts/build_about_content.py {name}
   ```
   Outputs to `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md`.
   Params table, response format, expected-keys are auto-generated from
   Pydantic models. Examples and chaining come from the input YAML.

3. Verify:
   - → **Gate:** `pytest tests/unit/test_about_content.py -v` (consistency)
   - → **Gate:** `pytest tests/integration/test_about_examples.py -v` (examples execute against KG)

### Unit tests (all three layers)

Run alongside or after each layer. Each layer has its own test class:

| Layer | Test file | Test class |
|---|---|---|
| Query builder | `tests/unit/test_query_builders.py` | `TestBuild{Name}` |
| API function | `tests/unit/test_api_functions.py` | `Test{Name}` |
| MCP wrapper | `tests/unit/test_tool_wrappers.py` | `Test{Name}Wrapper` + update `EXPECTED_TOOLS` |

→ **Gate:** `pytest tests/unit/ -v`

### Integration + regression tests

- Integration: add/update in `tests/integration/test_mcp_tools.py`
- Regression: add/update cases in `tests/evals/cases.yaml`,
  add builder to `TOOL_BUILDERS` in `tests/regression/test_regression.py`
- Generate baselines: `pytest tests/regression/ --force-regen -m kg`
- → **Gate:** all tests pass:
  ```bash
  pytest tests/unit/ -v
  pytest -m kg -v
  pytest tests/regression/ -m kg
  ```

### Documentation

- Update `CLAUDE.md` tool table with new/changed tool

### Code review

Run through code-review checklist.
Layer boundaries, signatures, tests, naming, docs all verified.

## Cascading renames (modify only)

When renaming affects multiple layers:

| What's renamed | Files to update |
|---|---|
| Builder function | queries_lib.py, api/functions.py imports, test imports, TOOL_BUILDERS |
| API function | api/functions.py, `__init__.py` (both), tools.py import, all tests |
| MCP tool | tools.py, EXPECTED_TOOLS in test_tool_wrappers.py, cases.yaml |
| RETURN column | Builder Cypher, fixture projection helpers (`as_*_result`), all test assertions |
| Parameter name | Builder, API, MCP wrapper, all test call sites |

Use grep to find all references before renaming:
```bash
grep -r "old_name" multiomics_explorer/ tests/
```
