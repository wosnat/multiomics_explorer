---
name: add-or-update-tool
description: Complete lifecycle for adding a new MCP tool or modifying an existing one. Two phases — definition (scope, KG exploration, schema iteration, mode planning) then build (query builder, API, MCP wrapper, tests, skills, review).
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
| Skills | About-mode content, pipeline skill references |
| Tests | All test classes for this tool across test files |
| Fixtures | `tests/fixtures/gene_data.py` projection helpers if applicable |

Steps 1–2 loop until scope, modes, and KG schema are all stable.

### Step 1: Define what's needed

- What the tool does (or what's changing), who calls it, what chains
  it participates in
- Draft both modes — what would summary and detail return?
  What aggregations, fields, sort keys?
- These requirements drive what the KG needs to support
- → **Review:** present requirements to user for feedback

### Step 2: KG exploration + iteration

- Query live KG (`run_cypher`) to check whether current nodes,
  edges, properties, and data volumes support the requirements
- If schema changes needed, write a KG change spec at
  **`docs/kg-specs/{tool-name}.md`** using [template](assets/kg-spec-template.md)
- User coordinates with KG repo (manual — may involve KG rebuild)
- After KG changes land, re-query live KG to verify
- Refine requirements and mode design based on what the KG
  can actually support — this may reveal new needs
- → **Review:** present updated findings to user. Repeat steps 1–2.

### Output: implementation plan

Once scope, modes, and KG schema are stable, write the implementation
plan at **`docs/tool-specs/{tool-name}.md`** using
[template](assets/tool-spec-template.md). Document:
- Purpose, use cases, tool chains
- **Summary mode:** aggregations, counts/distributions,
  availability signals, dimensions to break down by
- **Detail mode:** return fields, sort key, default limit,
  truncation metadata
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
- Add summary variant `build_{name}_summary()` if tool has summary mode
- Keyword-only args, `$param` placeholders, `AS snake_case` aliases
- → **Gate:** `pytest tests/unit/test_query_builders.py::TestBuild{Name} -v`

### Layer 2: API function → `api/functions.py`

- Calls builder + `conn.execute_query`
- `summary` bool param if tool has summary mode
- `conn: GraphConnection | None = None` as keyword-only last param
- Document return dict keys in docstring
- Wire exports: add to `api/__init__.py` and
  `multiomics_explorer/__init__.py` `__all__`
- → **Gate:** `pytest tests/unit/test_api_functions.py::Test{Name} -v`

### Layer 3: MCP wrapper → `mcp_server/tools.py`

- `@mcp.tool()` inside `register_tools(mcp)`
- `ctx: Context` first, then tool params, then `mode`, `limit`
- Summary/detail/about mode dispatch
- LLM-facing docstring with `Args:` section
- → **Gate:** `pytest tests/unit/test_tool_wrappers.py::Test{Name}Wrapper -v`

### Layer 4: Skill updates

- Write or update about-mode content in
  `skills/multiomics-kg-guide/references/tools/{name}.md`
  using [template](assets/about-content-template.md)
- Include `example-call` and `expected-keys` tagged blocks
- Update multiomics-kg-guide `SKILL.md` if the tool changes the landscape
- Update pipeline skills that reference the tool
- Sync: `scripts/sync_skills.sh`
- → **Gate:** skill content matches actual tool behavior

### Tests

- Integration: add/update in `tests/integration/test_mcp_tools.py`
  and `test_tool_correctness_kg.py`
- Regression: add/update cases in `tests/evals/cases.yaml`,
  add builder to `TOOL_BUILDERS` in `tests/regression/test_regression.py`
- Generate baselines: `pytest tests/regression/ --force-regen -m kg`
- → **Gate:** all tests pass:
  ```bash
  pytest tests/unit/ -v
  pytest -m kg -v
  pytest tests/regression/ -m kg
  ```

### Code review

Run through code-review checklist.
Layer boundaries, signatures, tests, naming, skills all verified.

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
