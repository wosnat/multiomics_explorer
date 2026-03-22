# Tool spec: {tool-name}

## Purpose

What the tool does and why it's needed.

## Out of Scope

What this tool does NOT do. Defer to other tools or future phases.

## Status / Prerequisites

- [ ] KG spec complete (if needed): `docs/kg-specs/{tool-name}.md`
- [ ] KG changes landed (if needed)
- [ ] Scope reviewed with user
- [ ] Result-size controls decided
- [ ] Ready for Phase 2 (build)

## Use cases

- Who calls this tool and in what context
- What chains it participates in (what tool comes before/after)

## KG dependencies

Nodes, edges, and properties this tool queries.
Link to KG spec if schema changes were needed: `docs/kg-specs/{tool-name}.md`

---

## Tool Signature

```python
@mcp.tool(
    tags={"tag1", "tag2"},
    annotations={"readOnlyHint": True},
)
async def {name}(
    ctx: Context,
    param: Annotated[str, Field(
        description="Description.",
    )],
    optional_param: Annotated[str | None, Field(
        description="Optional filter.",
    )] = None,
    verbose: Annotated[bool, Field(
        description="Include heavy text fields.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 50,
) -> {Name}Response:
    """Tool-level purpose description.

    Return schema is in Pydantic models (auto-generated as outputSchema).
    """
```

**Return envelope:** `{total_entries, total_matching, returned, truncated, results: [...]}`

**Per-result columns (compact):** field1, field2, ...

**Verbose adds:** heavy_field1, heavy_field2

## Result-size controls

Choose one section below based on the tool's result set size.
Delete the other.

### Option A: Small result set (no modes needed)

Result set is always small. No summary/detail modes.

**Sort key:** (required — every tool must have deterministic ORDER BY.
If no natural sort key, use alphabetical on the primary identifier.)

**Default limit:** —

**Verbose:** yes / no
If yes — what fields are omitted by default and included with
`verbose=True`:
- Compact (default): field1, field2, ...
- Verbose adds: heavy_field1, heavy_field2, ...

### Option B: Large result set (summary/detail modes)

About content is served via MCP resource `docs://tools/{name}`, not as
a tool mode parameter.

#### Summary mode

| Field | Type | Description |
|---|---|---|
| total_entries | int | All rows (unfiltered) |
| total_matching | int | Rows matching filters |
| — | — | Additional aggregations/breakdowns |

#### Detail mode

| Field | Type | Description |
|---|---|---|
| — | — | — |

**Sort key:** field (direction)
**Default limit:** —

## Special handling

- Caching: yes/no, what to cache
- Multi-query orchestration: does the API function make multiple builder calls?
- Lucene retry: does this tool use fulltext search?
- Grouping: group results by organism or other dimension?

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_{name}()` + `build_{name}_summary()` |
| 2 | API function | `api/functions.py` | `{name}()` |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add to imports + `__all__` |
| 4 | MCP wrapper | `mcp_server/tools.py` | `@mcp.tool()` wrapper |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | `TestBuild{Name}` + `TestBuild{Name}Summary` |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | `Test{Name}` |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | `Test{Name}Wrapper` + update `EXPECTED_TOOLS` |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | Smoke test against live KG |
| 9 | Regression | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS` |
| 10 | Eval cases | `tests/evals/cases.yaml` | Regression + correctness cases |
| 11 | About content | `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md` | Per-tool about text |
| 12 | Docs | `CLAUDE.md` | Add row to MCP Tools table |

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_{name}`

```python
def build_{name}(
    *,
    param: str,
    optional_param: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build Cypher for {description}.

    RETURN keys (compact): field1, field2, field3.
    RETURN keys (verbose): adds heavy_field1.
    """
```

### `build_{name}_summary`

```python
def build_{name}_summary(
    *,
    param: str,
    optional_param: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for {name}.

    RETURN keys: total_entries, total_matching.
    """
```

Both builders share the same WHERE clause construction.

**Cypher:** (show the actual queries)

**WHERE clause construction:** (show the conditions/params pattern)

**Design notes:** (key decisions — sort order, precomputed vs aggregated, etc.)

---

## API Function

**File:** `api/functions.py`

```python
def {name}(
    param: str,
    optional_param: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Description.

    Returns dict with keys: total_entries, total_matching, results.
    Per result: field1, field2, field3.
    """
```

Notes on 2-query pattern, Lucene retry, validation, etc.

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

Define Pydantic response models (`{Name}Result` + `{Name}Response`)
and the `@mcp.tool()` wrapper. FastMCP auto-generates `outputSchema`
from the return type annotation.

(Show response models with `Field(description=...)` on all fields.
Include examples in descriptions — e.g. `"Genus (e.g. 'Prochlorococcus')"`.
Show full wrapper code with Annotated/Field/ToolError/tags/annotations.
Return type is the response model, not `dict`.)

---

## Tests

### Unit: query builder (`test_query_builders.py`)

```
class TestBuild{Name}:
    test_no_filters
    test_{filter}_filter (one per filter)
    test_combined_filters
    test_returns_expected_columns
    test_order_by
    test_verbose_false
    test_verbose_true
    test_limit_clause
    test_limit_none

class TestBuild{Name}Summary:
    test_no_filters
    test_with_filters
    test_shares_where_clause
```

### Unit: API function (`test_api_functions.py`)

```
class Test{Name}:
    test_returns_dict
    test_passes_params
    test_creates_conn_when_none
    test_importable_from_package
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

```
class Test{Name}Wrapper:
    test_returns_dict_envelope
    test_empty_results
    test_params_forwarded
    test_truncation_metadata

Update EXPECTED_TOOLS to include "{name}".
```

### Integration (`test_mcp_tools.py`)

Against live KG:
- No filters → returns expected count
- Per-filter tests
- Each result has expected fields

### Regression (`test_regression.py`)

Add to `TOOL_BUILDERS`:
```python
"{name}": build_{name},
```

### Eval cases (`cases.yaml`)

```yaml
- id: {name}_all
  tool: {name}
  desc: All results returned when no filters
  params: {}
  expect:
    min_rows: 1
    columns: [field1, field2, field3]
```

(Add per-filter cases)

---

## About Content

About content is auto-generated from Pydantic models + human-authored
input YAML. Served via MCP resource at `docs://tools/{name}`.

### Input YAML

**File:** `multiomics_explorer/inputs/tools/{name}.yaml`

Create with `uv run python scripts/build_about_content.py --skeleton {name}`,
then fill in:

- **examples** — each with `title` + `call` (single tool) or `steps`
  (multi-step chain), and optional `response` (truncated example output)
- **verbose_fields** — list of field names only returned with
  `verbose=True`. Splits per-result table into compact + verbose sections.
- **chaining** — tool flow patterns (e.g. `"tool_a → tool_b → tool_c"`)
- **mistakes** — plain strings (→ "Good to know" section) or
  `wrong`/`right` dicts (→ "Common mistakes" section)

See `multiomics_explorer/inputs/tools/list_organisms.yaml` and
`list_publications.yaml` for working examples.

### Build

```bash
uv run python scripts/build_about_content.py {name}
```

**Output:** `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md`

Auto-generated from Pydantic models: parameters table, response format,
expected-keys, package import. From input YAML: examples, chaining, mistakes.

### Verify

```bash
pytest tests/unit/test_about_content.py -v          # consistency with tool schema
pytest tests/integration/test_about_examples.py -v  # examples execute against KG
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add row to MCP Tools table |
