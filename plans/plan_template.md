# Plan Template

Use this template when writing implementation plans for MCP tool changes
(new tools, renames, refactors, new parameters). Copy this file and fill in
each section.

---

# Plan: `<tool_name>` — <short description>

<1-3 sentence summary: what this plan covers, what motivated it, and what
kind of change it is (new tool / rename / refactor / new parameter).>

## Status / Prerequisites

List any prerequisites that must be done before this plan can start.
Check off completed items. Remove this section if there are none.

- [ ] KG change: <description>
- [x] Already done: <description>

## Issues Found in Review

Optional. Document any issues discovered during investigation that informed
the plan. Use subsections with strikethrough for resolved issues:

### ~~A. Issue title~~ (fixed / not a bug)
Explanation of why this is no longer relevant.

### B. Active issue title
Description of the problem and how this plan addresses it.

## Out of Scope

Explicitly list what this plan does NOT cover, with pointers to other plans
where applicable:

- <Related but excluded change> — see `<other_plan>.md`
- <Future enhancement> — tracked in `<location>`

---

## Tool Signature

The complete Python signature with docstring. This is the contract — all
other sections implement what's described here.

```python
@mcp.tool()
def tool_name(
    ctx: Context,
    param1: str,
    param2: str | None = None,
    limit: int = 25,
) -> str:
    """One-line summary.

    Longer description if needed.

    Args:
        param1: Description.
        param2: Description. Reference other tools for valid values
            (e.g. "Use list_filter_values to see valid categories").
        limit: Max results (default N, max M).
    """
```

**Return columns:**
`col1`, `col2`, `col3`, ...

Optional: describe conditional columns (e.g. columns that only appear when
a flag is set).

---

## KG-side Changes

Optional. List any changes needed in the `multiomics_biocypher_kg` repo.
Use strikethrough + checkmarks for completed items.

- [x] ~~K1: <done item>~~
- [ ] K2: <pending item>

Remove this section if no KG changes are needed.

## Implementation Order

Summary table showing the sequence across both repos (if applicable).

| Order | Change | Where | Status |
|-------|--------|-------|--------|
| 1 | <KG prerequisite> | KG | done |
| 2 | <First explorer change> | Explorer | this file |
| 3 | <Next change> | Explorer | this file |

Note which steps can run in parallel and which have dependencies.

## Agent Assignments

Assign each step to a specialized agent. Use the table format below.
Mark dependencies so agents can run in parallel where possible.

| Step | Agent | Task | Depends on |
|------|-------|------|------------|
| 1 | **query-builder** | Add `build_<tool_name>` to `queries_lib.py` | — |
| 2 | **tool-wrapper** | Add `<tool_name>` tool to `tools.py` | query-builder |
| 3a | **test-updater** | Add unit, integration, eval, and regression tests | tool-wrapper |
| 3b | **doc-updater** | Update `CLAUDE.md`, `README.md`, `AGENT.md`, `docs/testplans/testplan.md` | tool-wrapper |
| 4 | **code-reviewer** | Review all changes against this plan, run unit tests, grep for stale refs | test-updater, doc-updater |

Notes:
- Steps with different numbers are sequential.
- Steps with the same number + letter suffix (3a, 3b) can run in parallel.

---

## Query Builders

**Files:** `queries_lib.py`

### `build_<tool_name>`

```cypher
MATCH ...
WHERE ...
RETURN ...
ORDER BY ...
LIMIT $limit
```

Explain the query strategy:
- Why this approach over alternatives
- Performance considerations (e.g. "avoids expensive OPTIONAL MATCH")
- How it handles cross-organism results
- Edge cases (nulls, missing properties)

For tools with multiple query modes (e.g. ID detection vs text search),
document each variant and the detection logic.

---

## Tool Wrapper Logic

**Files:** `tools.py`

Describe any post-query Python logic that lives in the tool wrapper rather
than in Cypher. Common patterns:

- Post-query deduplication or grouping
- Caching (e.g. lifespan context cache for stable data)
- Input validation or detection (e.g. regex to distinguish IDs from text)
- Response formatting

Include code snippets for non-trivial logic.

Skip this section if the wrapper is a straightforward query-and-format.

---

## Tests

Tests follow the project structure: unit -> integration -> eval/regression.

### Unit tests

**`tests/unit/test_query_builders.py`:**
- [ ] <What to verify about the Cypher structure>
- [ ] <Parameter handling>
- [ ] <WHERE clause conditions>

**`tests/unit/test_tool_wrappers.py`:**
- [ ] Mock query results, verify JSON response structure
- [ ] Verify expected columns: `col1`, `col2`, ...
- [ ] Empty result handling
- [ ] Tool registration count updated (N -> N+1)
- [ ] <Any tool-wrapper-specific logic (dedup, caching, etc.)>

**`tests/unit/test_tool_correctness.py`** (if applicable):
- [ ] <Rename/update existing test class>
- [ ] <Update tool name references>

### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

List specific test scenarios against the live KG:
- [ ] <Basic happy-path query>
- [ ] <With organism filter>
- [ ] <Cross-organism results (both Pro and Alt)>
- [ ] <Edge cases (nulls, empty results)>
- [ ] <Specific known values to assert>

### Eval cases (`tests/evals/cases.yaml`)

```yaml
- id: <tool_name>_<scenario>
  tool: <tool_name>
  desc: <what this case validates>
  params:
    param1: value1
  expect:
    min_rows: N
    columns: [col1, col2, ...]
    contains:
      col_name: expected_value
```

Include cases for:
- Basic functionality
- Each optional parameter
- Cross-organism results
- Edge cases

### Regression snapshots (`tests/regression/`)

```bash
# After implementation:
pytest tests/regression/ --force-regen -m kg
pytest tests/regression/ -m kg
```

Note any special considerations (e.g. if post-query logic means regression
tests need to go through the tool wrapper rather than `TOOL_BUILDERS`).

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add row to MCP Tools table |
| `README.md` | Add entry to MCP tools section, bump tool count |
| `AGENT.md` | Add row to tools table |
| `docs/testplans/testplan.md` | Add test plan section (copy checklist from Tests above) |
