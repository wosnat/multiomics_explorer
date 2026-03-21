# Add-tool checklist

## Files to create/edit

| Step | File | What to add |
|---|---|---|
| L1 | `multiomics_explorer/kg/queries_lib.py` | `build_{name}()` + `build_{name}_summary()` |
| L2 | `multiomics_explorer/api/functions.py` | `{name}()` function |
| L2 | `multiomics_explorer/api/__init__.py` | Add to imports + `__all__` |
| L2 | `multiomics_explorer/__init__.py` | Add to imports + `__all__` |
| L3 | `multiomics_explorer/mcp_server/tools.py` | `@mcp.tool()` wrapper inside `register_tools()` |
| L4 | `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md` | About content |
| UT | `tests/unit/test_query_builders.py` | `class TestBuild{Name}` |
| UT | `tests/unit/test_api_functions.py` | `class Test{Name}` |
| UT | `tests/unit/test_tool_wrappers.py` | `class Test{Name}Wrapper` + update `EXPECTED_TOOLS` |
| IT | `tests/integration/test_mcp_tools.py` | Smoke test against live KG |
| RG | `tests/evals/cases.yaml` | Eval cases |
| RG | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS` |
| DC | `CLAUDE.md` | Add row to MCP Tools table |

## Template: query builder

```python
def build_{name}(
    *, required_param: str,
    optional_param: str | None = None,
) -> tuple[str, dict]:
    """Build Cypher for {description}.

    RETURN keys: key1, key2, key3.
    """
    conditions: list[str] = []
    params: dict = {"required_param": required_param}

    if optional_param:
        conditions.append("n.other = $optional_param")
        params["optional_param"] = optional_param

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        "MATCH (n:NodeType {prop: $required_param})\n"
        f"{where_block}"
        "RETURN n.prop AS key1, n.other AS key2\n"
        "ORDER BY n.prop"
    )
    return cypher, params
```

### With `verbose` (conditional RETURN columns)

```python
def build_{name}(
    *, required_param: str,
    verbose: bool = False,
) -> tuple[str, dict]:
    """Build Cypher for {description}.

    RETURN keys (compact): key1, key2, key3.
    RETURN keys (verbose): adds heavy_text_field.
    """
    verbose_cols = ",\n       n.heavy_text AS heavy_text_field" if verbose else ""

    cypher = (
        "MATCH (n:NodeType {prop: $required_param})\n"
        "RETURN n.prop AS key1, n.other AS key2"
        f"{verbose_cols}\n"
        "ORDER BY n.prop"
    )
    return cypher, {"required_param": required_param}
```

## Template: API function

```python
def {name}(
    required_param: str,
    optional_param: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """Description.

    Returns list of dicts with keys: key1, key2, key3.
    """
    if not required_param or not required_param.strip():
        raise ValueError("required_param must not be empty.")
    conn = _default_conn(conn)
    cypher, params = build_{name}(
        required_param=required_param,
        optional_param=optional_param,
    )
    return conn.execute_query(cypher, **params)
```

## Template: MCP wrapper

```python
from typing import Annotated
from pydantic import Field
from fastmcp.exceptions import ToolError

@mcp.tool(
    tags={"tag1", "tag2"},
    annotations={"readOnlyHint": True},
)
def {name}(
    ctx: Context,
    required_param: Annotated[str, Field(
        description="Description of param.",
    )],
    optional_param: Annotated[str | None, Field(
        description="Optional filter.",
    )] = None,
    limit: Annotated[int, Field(
        description="Max results.", ge=1, le=50,
    )] = 25,
) -> dict:
    """LLM-facing description (purpose + when to use).

    Keep the docstring to overall tool purpose. Parameter descriptions
    go in Field(description=...). Document return fields in docstring.

    Response: {total, returned, truncated, results: [...]}.
    Per result: key1, key2, key3.
    """
    logger.info("{name} required_param=%s", required_param)
    try:
        conn = _conn(ctx)
        result = api.{name}(required_param, optional_param=optional_param, limit=limit, conn=conn)
        return {
            "total_entries": result["total_entries"],
            "total_matching": result["total_matching"],
            "returned": len(result["results"]),
            "truncated": result["total_matching"] > len(result["results"]),
            "results": result["results"],
        }
    except ValueError as e:
        logger.warning("{name} error: %s", e)
        raise ToolError(str(e))
    except Exception as e:
        logger.warning("{name} unexpected error: %s", e)
        raise ToolError(f"Error in {name}: {e}")
```

## Template: cases.yaml entry

```yaml
- id: {name}_basic
  tool: {name}
  desc: Basic query returns expected results
  params:
    required_param: value
  expect:
    min_rows: 1
    columns: [key1, key2, key3]
```

## Common gotchas

- Forgetting to add to `__init__.py` exports (both `api/` and package root)
- Forgetting to update `EXPECTED_TOOLS` list in `test_tool_wrappers.py`
- Forgetting to add builder to `TOOL_BUILDERS` in `test_regression.py`
- Forgetting to update `CLAUDE.md` tool table
- Every query MUST have `ORDER BY` — if no natural sort key, sort alphabetically by primary identifier. Non-deterministic results break regression tests.
- String filters must be case-insensitive — use `toLower()` on both sides
- Fulltext search tools must return `score` in RETURN columns and ORDER BY score DESC
- Using f-strings for user input in Cypher instead of `$param` placeholders
- Forgetting `_default_conn(conn)` call in API function
