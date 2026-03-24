# Tool spec: `run_cypher` — v3 upgrade

Raw Cypher escape hatch. Executes arbitrary read-only queries against the KG
with syntax and schema validation via CyVer before execution.

## Out of Scope

- Summary/verbose modes — raw results, nothing to hide or aggregate.
- Parameterized queries (`$param`) — users write literal values.
  The underlying query builders use `$param`; `run_cypher` is for ad-hoc queries.
- Write operations — blocked by regex (`_WRITE_KEYWORDS`) in api/.
- Per-label result grouping — raw tabular output, caller interprets.

## Status / Prerequisites

- [x] No KG changes needed
- [x] CyVer already in `pyproject.toml` (`cyver>=2.0.2`)
- [x] `conn.driver` exposed on `GraphConnection` — CyVer validators can use it
- [x] Scope reviewed with user
- [x] Result-size controls decided: `limit` default 25, max 200, `truncated` heuristic
- [x] Ready for Phase 2 (build)

## Use cases

- Ad-hoc exploration: "How many Experiment nodes exist?" or
  "What treatment types are on Experiment nodes?"
- Schema investigation when `kg_schema` doesn't have enough detail.
- Cross-tool queries not covered by any dedicated tool.
- Development: test new Cypher patterns before formalizing into a builder.

## KG dependencies

Any — raw pass-through. No specific nodes or properties assumed.

---

## Tool Signature

```python
@mcp.tool(
    tags={"raw", "escape-hatch"},
    annotations={"readOnlyHint": True},
)
async def run_cypher(
    ctx: Context,
    query: Annotated[str, Field(
        description="Cypher query string. Write operations are blocked. "
        "A LIMIT clause is added automatically if absent.",
    )],
    limit: Annotated[int, Field(
        description="Max results (default 25, max 200).",
        ge=1,
    )] = 25,
) -> RunCypherResponse:
    """Execute a raw Cypher query against the knowledge graph (read-only).

    Use this as an escape hatch when other tools don't cover your query.
    Write operations are blocked. Queries are validated for syntax and schema
    correctness before execution — warnings are returned in the response.
    """
```

**Return envelope:** `{returned, truncated, warnings, results: [...]}`

`truncated` is a heuristic: `True` when `returned == limit` (may be more rows).
`warnings` are non-blocking schema/property issues from CyVer (e.g. unknown
label, unknown property key). Syntax errors raise `ToolError` before execution.

---

## CyVer integration

CyVer validates queries against the live KG via `EXPLAIN`. Run in this order:

1. **Write blocking** (existing `_WRITE_KEYWORDS` regex) — `ValueError` → `ToolError`
2. **`SyntaxValidator`** — if `valid == False`, raise `ValueError` with the
   error description (line/column included). No execution.
3. **`SchemaValidator`** — if score < 1.0, collect warnings from `meta`.
4. **`PropertiesValidator`** — if score < 1.0, collect warnings from `meta`.
5. **Execute** the query.

All CyVer validators live in the **API layer** (`api/functions.py`), where
the complete response dict is assembled. CyVer needs `conn.driver` (neo4j
`Driver` object), available as `GraphConnection.driver`.

**Driver notification noise:** CyVer uses `EXPLAIN` internally. The neo4j
driver logs EXPLAIN notifications via the `neo4j` logger. Suppress in tests:
```python
import logging
logging.getLogger("neo4j").setLevel(logging.ERROR)
```

**`SyntaxValidator` false negative:** Parameterized queries (`$param`) return
`False` from `SyntaxValidator` — `ParameterNotProvided` is a notification, not
a real syntax error. Not an issue here since `run_cypher` users write literal
values. Document in docstring.

---

## Result-size controls

### Option A: Small result set (no modes needed)

No `summary` or `verbose`. Result count controlled entirely by `limit`.

**Sort key:** Caller-defined (raw query, no imposed ORDER BY).

**Default limit:** 25. Max 200 (capped in api/).

**`truncated` heuristic:** `returned == limit` — may be more rows if exactly
`limit` results came back. Cannot know true total without a COUNT query.

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | API function | `api/functions.py` | Update `run_cypher()` — add limit param, move limit-injection + semicolon stripping from MCP, add CyVer validation, return dict |
| 2 | MCP wrapper | `mcp_server/tools.py` | Pydantic models, async, ToolError, remove limit logic |
| 3 | Unit tests | `tests/unit/test_api_functions.py` | `TestRunCypher` — new envelope, CyVer mocked |
| 4 | Unit tests | `tests/unit/test_tool_wrappers.py` | Rewrite `TestRunCypherWrapper` — async, Pydantic |
| 5 | Unit tests | `tests/unit/test_write_blocking.py` | No changes — `_WRITE_KEYWORDS` unchanged |
| 6 | Integration | `tests/integration/test_mcp_tools.py` | Update smoke test for new response shape |
| 7 | About content | `multiomics_explorer/inputs/tools/run_cypher.yaml` | Create input YAML |
| 8 | About content | `multiomics_explorer/skills/.../tools/run_cypher.md` | Build |
| 9 | Docs | `CLAUDE.md` | Update row (add CyVer mention) |

No query builder needed — raw pass-through.
No eval cases / regression fixtures — query is caller-supplied.

---

## API Function

**File:** `api/functions.py`

```python
# Top-level imports (with existing imports in functions.py)
from CyVer import SyntaxValidator, SchemaValidator, PropertiesValidator

# Module-level: suppress neo4j driver EXPLAIN notification noise from CyVer
import logging as _logging
_logging.getLogger("neo4j").setLevel(_logging.ERROR)


def run_cypher(
    query: str,
    limit: int = 25,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Execute a raw Cypher query (read-only).

    Write operations are blocked via keyword detection.
    Syntax is validated via CyVer before execution; schema and property
    warnings are included in the returned dict.

    Returns dict with keys: returned, truncated, warnings, results.

    Raises ValueError if the query contains write keywords or has a syntax error.
    """
    conn = _default_conn(conn)
    limit = min(limit, 200)

    # 1. Write blocking
    if _WRITE_KEYWORDS.search(query):
        raise ValueError("Write operations are not allowed. This interface is read-only.")

    # 2. Syntax validation (hard block)
    valid, meta = SyntaxValidator(conn.driver).validate(query)
    if not valid:
        msg = meta[0]["description"] if meta else "Syntax error"
        raise ValueError(f"Syntax error: {msg}")

    # 3–4. Schema + property warnings (soft); deduplicate preserving order
    raw_warnings = []
    _, schema_meta = SchemaValidator(conn.driver).validate(query)
    raw_warnings.extend(m["description"] for m in schema_meta)
    _, prop_meta = PropertiesValidator(conn.driver).validate(query)
    raw_warnings.extend(m["description"] for m in prop_meta)
    warnings = list(dict.fromkeys(raw_warnings))

    # 5. Limit injection + semicolon strip
    if not re.search(r"\bLIMIT\b", query, re.IGNORECASE):
        query = query.rstrip().rstrip(";")
        query += f"\nLIMIT {limit}"

    # 6. Execute
    results = conn.execute_query(query)
    return {
        "returned": len(results),
        "truncated": len(results) == limit,
        "warnings": warnings,
        "results": results,
    }
```

**Notes:**
- `limit` param added (was only in MCP layer before).
- Limit injection + semicolon stripping moved from MCP to here.
- CyVer imported at module level (top of `functions.py` with other imports).
- `logging.getLogger("neo4j")` set at module level — one-time side effect,
  not repeated on every call. Affects all neo4j logging in the process;
  acceptable since CyVer EXPLAIN noise is otherwise unavoidable.
- `dict.fromkeys()` deduplicates warnings while preserving insertion order —
  SchemaValidator and PropertiesValidator can both flag the same unknown label.
- CyVer validators are stateless and cheap to construct per call.

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

```python
class RunCypherResponse(BaseModel):
    returned: int = Field(description="Number of rows returned (e.g. 12)")
    truncated: bool = Field(
        description="True when returned == limit (more rows may exist)"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Schema or property warnings from CyVer (non-blocking). "
        "Empty list means query is fully valid against the current KG schema.",
    )
    results: list[dict] = Field(
        default_factory=list,
        description="Raw query results, one dict per row",
    )


@mcp.tool(
    tags={"raw", "escape-hatch"},
    annotations={"readOnlyHint": True},
)
async def run_cypher(
    ctx: Context,
    query: Annotated[str, Field(
        description="Cypher query string. Write operations are blocked. "
        "A LIMIT clause is added automatically if absent.",
    )],
    limit: Annotated[int, Field(
        description="Max results (default 25, max 200).",
        ge=1,
    )] = 25,
) -> RunCypherResponse:
    """Execute a raw Cypher query against the knowledge graph (read-only).

    Use this as an escape hatch when other tools don't cover your query.
    Write operations are blocked. Queries are validated for syntax and schema
    correctness before execution — warnings are returned in the response.
    """
    await ctx.info(f"run_cypher limit={limit}")
    try:
        conn = _conn(ctx)
        data = api.run_cypher(query, limit=limit, conn=conn)
        response = RunCypherResponse(**data)
        await ctx.info(
            f"Returning {response.returned} rows"
            + (f" ({len(response.warnings)} warnings)" if response.warnings else "")
        )
        return response
    except ValueError as e:
        await ctx.warning(f"run_cypher error: {e}")
        raise ToolError(str(e))
    except Exception as e:
        await ctx.error(f"run_cypher unexpected error: {e}")
        raise ToolError(f"Error in run_cypher: {e}")
```

Key changes from v1:
- `async def` with `await ctx.info/warning/error()`
- Pydantic `RunCypherResponse` (not JSON string return)
- `ToolError` instead of returning error strings
- Remove `logger` calls, remove limit logic (moved to api/)
- `warnings` field surfaces CyVer schema/property issues
- Syntax errors → `ToolError` before any execution

---

## Tests

### Unit: API function (`test_api_functions.py`)

CyVer validators must be mocked — unit tests do not hit the KG.

```
class TestRunCypher:
    test_returns_standard_envelope        — keys: returned, truncated, warnings, results
    test_write_blocked_raises_value_error — CREATE/MERGE/etc. raises ValueError
    test_foreach_blocked                  — FOREACH pattern raises ValueError
    test_load_csv_blocked                 — LOAD CSV raises ValueError
    test_call_procedure_blocked           — CALL apoc.* raises ValueError
    test_syntax_error_raises_value_error  — SyntaxValidator returns False → ValueError with message
    test_syntax_error_message_propagated  — ValueError message includes CyVer description
    test_schema_warnings_in_response      — SchemaValidator meta → warnings list
    test_property_warnings_in_response    — PropertiesValidator meta → warnings list
    test_no_warnings_when_valid           — all validators pass → warnings=[]
    test_duplicate_warnings_deduplicated  — same message from schema+props → appears once
    test_validators_use_conn_driver       — validators instantiated with conn.driver, not conn
    test_limit_injected_when_absent       — LIMIT added to query
    test_limit_not_duplicated_when_present — existing LIMIT preserved
    test_limit_capped_at_200              — limit=500 → LIMIT 200 in query
    test_semicolon_stripped               — trailing ; removed before LIMIT
    test_truncated_when_returned_equals_limit
    test_not_truncated_when_returned_lt_limit
    test_empty_results                    — returned=0, truncated=False
    test_creates_conn_when_none
```

**Note on write blocking coverage:** `test_write_blocking.py` tests `_WRITE_KEYWORDS`
regex directly (unchanged). The per-pattern tests above (`test_foreach_blocked` etc.)
verify the regex is wired through the function — not redundant.

Mock pattern — patch where imported (`multiomics_explorer.api.functions`),
not the source module (`CyVer`):
```python
from unittest.mock import patch, MagicMock

MOD = "multiomics_explorer.api.functions"

def test_schema_warnings_in_response(mock_conn):
    mock_conn.execute_query.return_value = [{"n": 1}]
    with patch(f"{MOD}.SyntaxValidator") as sv_cls, \
         patch(f"{MOD}.SchemaValidator") as schv_cls, \
         patch(f"{MOD}.PropertiesValidator") as pv_cls:
        sv_cls.return_value.validate.return_value = (True, [])
        schv_cls.return_value.validate.return_value = (
            0.5,
            [{"code": "UnknownLabelWarning",
              "description": "Label Foo not in database"}]
        )
        pv_cls.return_value.validate.return_value = (1.0, [])
        result = run_cypher("MATCH (n:Foo) RETURN n", conn=mock_conn)
    assert result["warnings"] == ["Label Foo not in database"]
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

Rewrite `TestRunCypherWrapper` — all tests become async:

```
class TestRunCypherWrapper:
    test_returns_response_envelope         — has returned, truncated, warnings, results
    test_write_blocked_raises_tool_error   — ValueError from api → ToolError
    test_syntax_error_raises_tool_error    — ValueError (syntax) → ToolError
    test_cyver_exception_raises_tool_error — CyVer validator throws → ToolError (not 500)
    test_limit_forwarded                   — limit param passed to api
    test_warnings_in_response              — warnings propagated from api dict
    test_empty_warnings_when_valid         — warnings=[] when api returns []
    test_empty_results                     — returned=0
    test_generic_error_raises_tool_error   — RuntimeError → ToolError
```

### Unit: write blocking (`test_write_blocking.py`)

No changes — `_WRITE_KEYWORDS` regex is unchanged in api/.

### Integration (`tests/integration/test_mcp_tools.py`)

Update smoke test:
- Valid query → `returned > 0`, `warnings == []`, response has correct keys
- Query referencing non-existent label → `warnings` non-empty, describes the unknown label
- Write query → `ToolError` raised
- Syntax error query → `ToolError` raised

---

## About Content

### Input YAML

**File:** `multiomics_explorer/inputs/tools/run_cypher.yaml`

```yaml
examples:
  - title: Count genes per organism
    call: run_cypher(query="MATCH (g:Gene) RETURN g.ncbi_taxon_id AS taxon, count(g) AS gene_count ORDER BY gene_count DESC")
    response: |
      {
        "returned": 25,
        "truncated": false,
        "warnings": [],
        "results": [
          {"taxon": "1219", "gene_count": 1921},
          {"taxon": "324", "gene_count": 1470}
        ]
      }

  - title: Explore experiment schema
    call: run_cypher(query="MATCH (e:Experiment) RETURN keys(e) AS props LIMIT 1")

  - title: Query with schema warning
    call: run_cypher(query="MATCH (g:Gene)-[:HAS_FUNCTION]->(f:Function) RETURN g.locus_tag LIMIT 5")
    response: |
      {
        "returned": 0,
        "truncated": false,
        "warnings": [
          "One of the relationship types in your query is not available in the database (the missing relationship type is: HAS_FUNCTION)"
        ],
        "results": []
      }

chaining:
  - "kg_schema → run_cypher (use schema to write correct queries)"
  - "run_cypher → formalize into query builder once pattern is validated"

mistakes:
  - "Warnings are non-blocking — the query still executes. Check warnings before trusting empty results."
  - wrong: "run_cypher(query='MATCH (g:Gene) WHERE g.locus_tag = $tag RETURN g', params={'tag': 'PMM0001'})"
    right: "run_cypher(query=\"MATCH (g:Gene) WHERE g.locus_tag = 'PMM0001' RETURN g\")"
  - "No LIMIT in query? One is added automatically at the default (25). Pass limit= to increase."
```

### Build

```bash
uv run python scripts/build_about_content.py run_cypher
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Update row: add "validates syntax and schema via CyVer" to description |
