# Tool spec: `list_filter_values` — v3 upgrade

List valid categorical filter values used across tools. Currently
returns gene categories only. This is a discovery/lookup tool —
researchers call it to find valid `category` values before filtering
`genes_by_function`.

## Out of Scope

- Treatment types, omics types — already on `list_organisms` and
  `list_experiments` with richer context.
- Summary/detail modes — not needed, result is always small.
- Filtering by substring — only ~26 values per type, Claude filters in context.

## Status / Prerequisites

- [x] No KG changes needed — existing `Gene.gene_category` property
- [x] Scope reviewed with user
- [x] Result-size controls decided: no modes, no limit, no verbose
- [x] Ready for Phase 2 (build)

## Use cases

- **Filter value discovery:** "What gene categories can I filter by?"
  before calling `genes_by_function(category=...)`.
- **Chaining:** `list_filter_values` → `genes_by_function(category=...)`.

## KG dependencies

- `Gene` nodes with `gene_category` property.
- No joins, no precomputed stats needed.
- Existing `build_list_gene_categories()` builder in `kg/queries_lib.py`
  is correct and unchanged.

---

## Tool Signature

```python
@mcp.tool(
    tags={"filters", "discovery"},
    annotations={"readOnlyHint": True},
)
async def list_filter_values(
    ctx: Context,
    filter_type: Annotated[Literal["gene_category"], Field(
        description="Which filter's valid values to return. "
        "'gene_category': values for the category filter in genes_by_function.",
    )] = "gene_category",
) -> ListFilterValuesResponse:
    """List valid values for categorical filters used across tools.

    Returns valid values and counts for the requested filter type.
    Use the returned values as filter parameters in other tools.
    """
```

One parameter — `filter_type` defaults to `"gene_category"` (the only current
type). Extend the `Literal` and add a builder + branch in api/ as new types are
needed. Result set is always small (~26 rows per type).

**Return envelope:** `{filter_type, total_entries, returned, truncated, results: [...]}`

**Per-result columns (all filter types):**

| Field | Type | Description |
|---|---|---|
| value | str | Filter value (e.g. "Photosynthesis", "Transport") |
| count | int | Number of genes/items with this value |

## Result-size controls

### Option A: Small result set (no modes needed)

Result set is fixed at ~26 rows (TIGR/COG functional role categories).
No `summary`, no `verbose`, no `limit`.

**Sort key:** `count DESC` — most-used values first.

**Caching:** No — each type query reads ~26 rows. Trivially fast.
Removing the v1 cache simplifies code.

**Extensibility:** To add a new filter type (e.g. `"annotation_quality"`):
1. Add new value to `Literal` in MCP wrapper
2. Add builder `build_list_{type}_values()` in `kg/queries_lib.py`
3. Add branch in `api/list_filter_values()` dispatching on `filter_type`
4. Result columns can differ per type — `FilterValueResult` uses generic
   `value`/`count` fields (see MCP wrapper below)

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | No changes — `build_list_gene_categories()` is correct |
| 2 | API function | `api/functions.py` | Update `list_filter_values()` return dict to standard envelope |
| 3 | MCP wrapper | `mcp_server/tools.py` | Pydantic models, async, ToolError, remove caching |
| 4 | Unit tests | `tests/unit/test_query_builders.py` | No changes to builder tests |
| 5 | Unit tests | `tests/unit/test_api_functions.py` | Update `TestListFilterValues` for new envelope shape |
| 6 | Unit tests | `tests/unit/test_tool_wrappers.py` | Rewrite `TestListFilterValuesWrapper` for Pydantic response |
| 7 | Integration | `tests/integration/test_mcp_tools.py` | Update smoke test for new response shape |
| 8 | Integration | `tests/integration/test_api_contract.py` | Update `TestListFilterValuesContract` — check `filter_type`, `total_entries`, `results` keys (not `gene_categories`) |
| 9 | Integration | `tests/integration/test_tool_correctness_kg.py` | No changes needed |
| 10 | Regression | `tests/regression/test_regression.py` | No changes (builder name unchanged) |
| 11 | Eval cases | `tests/evals/cases.yaml` | Add `columns: [value, count]` to `list_filter_values` case |
| 12 | Eval runner | `tests/evals/test_eval.py` | Update special-case handler to call `api.list_filter_values()["results"]` instead of builder directly (so output matches normalized `{value, count}` shape) |
| 13 | About content | `multiomics_explorer/inputs/tools/list_filter_values.yaml` | Create input YAML |
| 14 | About content | `multiomics_explorer/skills/.../tools/list_filter_values.md` | Build |
| 15 | Docs | `CLAUDE.md` | No change needed (description is accurate) |

---

## Query Builder

**File:** `kg/queries_lib.py`

**No changes.** `build_list_gene_categories()` is already correct:

```python
def build_list_gene_categories() -> tuple[str, dict]:
    cypher = (
        "MATCH (g:Gene) WHERE g.gene_category IS NOT NULL\n"
        "RETURN g.gene_category AS category, count(*) AS gene_count\n"
        "ORDER BY gene_count DESC"
    )
    return cypher, {}
```

Verified against live KG — returns 26 rows, all `gene_count > 0`,
sorted by gene_count DESC. No changes needed.

---

## API Function

**File:** `api/functions.py`

```python
def list_filter_values(
    filter_type: str = "gene_category",
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List valid values for a categorical filter.

    Returns dict with keys: filter_type, total_entries, returned, truncated, results.
    Per result: value, count.
    """
    conn = _default_conn(conn)
    if filter_type == "gene_category":
        cypher, params = build_list_gene_categories()
    else:
        raise ValueError(f"Unknown filter_type: {filter_type!r}")
    rows = conn.execute_query(cypher, **params)
    # Normalise to generic {value, count} shape
    results = [{"value": r["category"], "count": r["gene_count"]} for r in rows]
    total = len(results)
    return {
        "filter_type": filter_type,
        "total_entries": total,
        "returned": total,
        "truncated": False,
        "results": results,
    }
```

No slicing (no limit). `truncated` is always False. Single query per type.
`ValueError` for unknown `filter_type` — MCP raises `ToolError`.

**Generic result shape:** `{value, count}` rather than type-specific field
names (`category`, `gene_count`). This keeps `FilterValueResult` stable as new
types are added. The `filter_type` in the response tells the caller what `value`
represents.

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

```python
class FilterValueResult(BaseModel):
    value: str = Field(
        description="Filter value (e.g. 'Photosynthesis', 'Transport', 'Unknown')"
    )
    count: int = Field(
        description="Number of genes/items with this value (e.g. 770)"
    )

class ListFilterValuesResponse(BaseModel):
    filter_type: str = Field(description="The filter type returned (e.g. 'gene_category')")
    total_entries: int = Field(description="Total distinct values for this filter (e.g. 26)")
    returned: int = Field(description="Number of results returned (e.g. 26)")
    truncated: bool = Field(description="True if total_entries > returned")
    results: list[FilterValueResult] = Field(default_factory=list)
```

```python
@mcp.tool(
    tags={"filters", "discovery"},
    annotations={"readOnlyHint": True},
)
async def list_filter_values(
    ctx: Context,
    filter_type: Annotated[Literal["gene_category"], Field(
        description="Which filter's valid values to return. "
        "'gene_category': values for the category filter in genes_by_function.",
    )] = "gene_category",
) -> ListFilterValuesResponse:
    """List valid values for categorical filters used across tools.

    Returns valid values and counts for the requested filter type.
    Use the returned values as filter parameters in other tools.
    """
    await ctx.info(f"list_filter_values filter_type={filter_type}")
    try:
        conn = _conn(ctx)
        data = api.list_filter_values(filter_type=filter_type, conn=conn)
        results = [FilterValueResult(**r) for r in data["results"]]
        response = ListFilterValuesResponse(**{**data, "results": results})
        await ctx.info(f"Returning {response.total_entries} values for {filter_type}")
        return response
    except ValueError as e:
        await ctx.warning(f"list_filter_values error: {e}")
        raise ToolError(str(e))
    except Exception as e:
        await ctx.error(f"list_filter_values unexpected error: {e}")
        raise ToolError(f"Error in list_filter_values: {e}")
```

Key changes from v1:
- `async def` with `await ctx.info()`
- Pydantic `FilterValueResult` + `ListFilterValuesResponse` (not JSON string)
- `ToolError` instead of returning error string
- Remove caching (`_filter_values_cache`)
- Remove `logger` calls

---

## Tests

### Unit: query builder (`test_query_builders.py`)

No changes needed — `build_list_gene_categories()` builder is unchanged.

### Unit: API function (`test_api_functions.py`)

Update `TestListFilterValues` for new envelope:

```
class TestListFilterValues:
    test_returns_standard_envelope       — keys: filter_type, total_entries, returned, truncated, results
    test_results_have_value_count_fields — each result has value, count (not category/gene_count)
    test_gene_category_default           — default filter_type="gene_category" works
    test_unknown_filter_type_raises      — ValueError for unrecognised filter_type
    test_truncated_always_false          — truncated is always False
    test_one_query_executed              — single execute_query call
    test_creates_conn_when_none          — default conn used when None
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

Rewrite `TestListFilterValuesWrapper`:

```
class TestListFilterValuesWrapper:
    test_returns_response_envelope     — response has filter_type, total_entries, returned, truncated, results
    test_result_fields                 — each result has value and count
    test_filter_type_forwarded         — filter_type param passed to api
    test_empty_results                 — total_entries=0, results=[]
    test_truncated_always_false        — truncated is always False
    test_value_error_raises_tool_error — ValueError from api raises ToolError
    test_generic_error                 — unexpected exception raises ToolError
    test_no_caching                    — api.list_filter_values called on every invocation (not skipped by lifespan cache)
```

Also update `EXPECTED_TOOLS` — tool name unchanged, no action needed.

### Integration (`test_mcp_tools.py`)

Update smoke test to check for `filter_type`, `total_entries`, `returned`, `results`
keys (not `gene_categories`).

### Regression (`test_regression.py`)

No changes — builder `build_list_gene_categories` name is unchanged.
Baselines remain valid.

---

## About Content

About content is auto-generated from Pydantic models + human-authored
input YAML. Served via MCP resource at `docs://tools/list_filter_values`.

### Input YAML

**File:** `multiomics_explorer/inputs/tools/list_filter_values.yaml`

```bash
uv run python scripts/build_about_content.py --skeleton list_filter_values
```

```yaml
examples:
  - title: List gene categories
    call: list_filter_values(filter_type="gene_category")
    response: |
      {
        "filter_type": "gene_category",
        "total_entries": 26,
        "returned": 26,
        "truncated": false,
        "results": [
          {"value": "Unknown", "count": 12183},
          {"value": "Coenzyme metabolism", "count": 2146},
          {"value": "Stress response and adaptation", "count": 2073}
        ]
      }

  - title: Find genes in a category
    steps: |
      Step 1: list_filter_values(filter_type="gene_category")
              → extract value strings from results

      Step 2: genes_by_function(search_text="photosystem", category="Photosynthesis")
              → get photosynthesis genes matching "photosystem"

chaining:
  - "list_filter_values → genes_by_function(category=...)"

mistakes:
  - "count is summed across all organisms — a category with count=770 may cover genes in 10+ organisms"
  - wrong: "list_filter_values(category='Photosynthesis')  # no such param"
    right: "list_filter_values(filter_type='gene_category')  # then pass value to genes_by_function"
```

### Build

```bash
uv run python scripts/build_about_content.py list_filter_values
```

### Verify

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -v
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | No change — existing description is accurate |
