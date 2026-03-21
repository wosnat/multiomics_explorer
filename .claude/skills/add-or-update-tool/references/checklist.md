# Add-tool checklist

## Files to create/edit

| Step | File | What to add |
|---|---|---|
| 4 | `multiomics_explorer/kg/queries_lib.py` | `build_{name}()` + optional `build_{name}_summary()` |
| 5 | `multiomics_explorer/api/functions.py` | `{name}()` function |
| 6 | `multiomics_explorer/api/__init__.py` | Add to `__all__` |
| 6 | `multiomics_explorer/__init__.py` | Add to `__all__` + import |
| 7 | `multiomics_explorer/mcp_server/tools.py` | `@mcp.tool()` wrapper inside `register_tools()` |
| 8 | `tests/integration/test_mcp_tools.py` | Smoke test |
| 9 | `tests/evals/cases.yaml` | Eval cases |
| 9 | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS` |
| 10 | `skills/.../references/tools/{name}.md` | About-mode content |
| — | `tests/unit/test_query_builders.py` | `class TestBuild{Name}` |
| — | `tests/unit/test_api_functions.py` | `class Test{Name}` |
| — | `tests/unit/test_tool_wrappers.py` | `class Test{Name}Wrapper` + update `EXPECTED_TOOLS` |

## Template: query builder

```python
def build_{name}(
    *, required_param: str,
    optional_param: str | None = None,
) -> tuple[str, dict]:
    """Build Cypher for {description}.

    RETURN keys: key1, key2, key3.
    """
    cypher = (
        "MATCH (n:NodeType)\n"
        "WHERE n.prop = $required_param\n"
        "  AND ($optional_param IS NULL OR n.other = $optional_param)\n"
        "RETURN n.prop AS key1, n.other AS key2\n"
        "ORDER BY n.prop"
    )
    return cypher, {
        "required_param": required_param,
        "optional_param": optional_param,
    }
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
@mcp.tool()
def {name}(
    ctx: Context,
    required_param: str,
    optional_param: str | None = None,
    limit: int = 25,
) -> str:
    """LLM-facing description.

    Args:
        required_param: Description.
        optional_param: Optional filter.
        limit: Max results (default 25, max 50).
    """
    logger.info("{name} required_param=%s", required_param)
    try:
        conn = _conn(ctx)
        limit = min(limit, 50)
        results = api.{name}(required_param, optional_param=optional_param, conn=conn)
        if not results:
            return "No results found."
        return _fmt(results, limit=limit)
    except ValueError as e:
        logger.warning("{name} error: %s", e)
        return f"Error: {e}"
    except Exception as e:
        logger.warning("{name} unexpected error: %s", e)
        return f"Error in {name}: {e}"
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
- Not including `ORDER BY` in Cypher → non-deterministic test results
- Using f-strings for user input in Cypher instead of `$param` placeholders
- Forgetting `_default_conn(conn)` call in API function
