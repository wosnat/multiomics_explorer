# Tool spec: kg_schema (rename from get_schema)

## Purpose

Return the knowledge graph schema: all node labels with property names and
types, and all relationship types with source/target labels and property names.
Lets the LLM understand what's queryable before constructing Cypher or using
other tools.

## Out of Scope

- Node counts — these can be obtained via `run_cypher`
- Data values — use `list_filter_values` for categorical filter values
- This tool does not query genes, experiments, or any data nodes

## Status / Prerequisites

- [x] No KG changes needed — uses existing `kg/schema.py` introspection
- [x] Scope reviewed with user
- [x] Result-size controls decided: none (schema is always small and complete)
- [ ] Ready for Phase 2 (build)

## Use cases

- LLM calls this first (or early) when asked to construct a Cypher query, to
  know what labels and properties exist
- LLM calls this to confirm a property name before using `run_cypher`
- Tool chain: `kg_schema` → `run_cypher`

## KG dependencies

Uses `kg/schema.py` directly — calls `load_schema_from_neo4j(conn)` which
introspects Neo4j via APOC metadata queries. No Cypher builder in queries_lib.

---

## Tool Signature

```python
@mcp.tool(
    tags={"utility", "schema"},
    annotations={"readOnlyHint": True},
)
async def kg_schema(
    ctx: Context,
) -> KgSchemaResponse:
    """Get the knowledge graph schema: node labels with property names/types,
    and relationship types with source/target labels.

    Return schema is in Pydantic models (auto-generated as outputSchema).
    """
```

**Return envelope:** `{nodes, relationships}` — no pagination; schema is always complete.

**`nodes`:** `dict[str, dict]` — `{label: {properties: {name: type_string}}}`

**`relationships`:** `dict[str, dict]` — `{type: {source_labels, target_labels, properties}}`

## Result-size controls

Schema is always small (tens of node labels, tens of relationship types).
No `summary`, `verbose`, `limit`, or `not_found`.

**Sort key:** alphabetical on node/relationship name (already enforced in `to_dict()`)

---

## Special notes

- **No query builder** — `kg_schema` uses `kg/schema.py` introspection, not
  `queries_lib.py`. No entry in `TOOL_BUILDERS` and no regression golden file.
- **`to_prompt_string()` goes away** — the current wrapper calls
  `schema.to_prompt_string()` directly, bypassing `api/`. After v3, the MCP
  wrapper calls `api.kg_schema()` which calls `schema.to_dict()`. The formatted
  string output is replaced by a structured `KgSchemaResponse`.
- **Non-standard envelope** — `KgSchemaResponse` has `nodes` and `relationships`
  instead of the usual `total_matching / returned / truncated / results` fields.
  The schema is a single structured object, not a list of rows.

---

## Implementation Plan

This is a **rename + v3 pattern upgrade**. The core logic (`load_schema_from_neo4j`)
is unchanged. No new query builder needed.

### What changes

| Layer | Change |
|---|---|
| `kg/queries_lib.py` | No change — schema uses `kg/schema.py`, not queries_lib |
| `api/functions.py` | Rename `get_schema` → `kg_schema` |
| `api/__init__.py` | Update import + `__all__`: `get_schema` → `kg_schema` |
| `multiomics_explorer/__init__.py` | Update import + `__all__`: `get_schema` → `kg_schema` |
| `mcp_server/tools.py` | Rename + v3 pattern (see below) |
| `tests/unit/test_api_functions.py` | Rename class + call sites |
| `tests/unit/test_tool_wrappers.py` | Full rewrite of wrapper test class + error tests (see below) |
| `tests/integration/test_api_contract.py` | Rename class + call sites |
| `tests/integration/test_mcp_tools.py` | Add smoke test |
| `tests/evals/cases.yaml` | No entry — eval framework checks `results` rows; `kg_schema` has no results list |
| About content | New input YAML + build |
| `CLAUDE.md` | Update tool table row |

---

## Pydantic models

```python
class KgSchemaResponse(BaseModel):
    nodes: dict[str, dict] = Field(
        description="Node labels mapped to their property definitions. "
                    "Each value is {'properties': {'prop_name': 'type_string', ...}}."
    )
    relationships: dict[str, dict] = Field(
        description="Relationship types mapped to their definitions. "
                    "Each value is {'source_labels': [...], 'target_labels': [...], "
                    "'properties': {'prop_name': 'type_string', ...}}."
    )
```

No `{Name}Result` per-row model — `KgSchemaResponse` IS the envelope.

---

## API Function

```python
def kg_schema(
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Get the knowledge graph schema as a plain dict.

    Returns dict with keys:
      nodes: {label: {properties: {name: type}}}
      relationships: {type: {source_labels, target_labels, properties}}
    """
    conn = _default_conn(conn)
    schema = load_schema_from_neo4j(conn)
    return schema.to_dict()
```

Rename only — logic unchanged.

---

## MCP Wrapper

```python
async def kg_schema(ctx: Context) -> KgSchemaResponse:
    """..."""
    data = api.kg_schema(conn=_conn(ctx))
    return KgSchemaResponse(**data)
```

- `async def` (was `def`)
- Calls `api.kg_schema()` — fixes the layer bypass (old wrapper called
  `load_schema_from_neo4j` directly and called `schema.to_prompt_string()`)
- Errors propagate naturally — remove the old `try/except` error-string returns;
  `ToolError` is used if explicit error handling is needed

---

## Tests

### Unit: API function (`test_api_functions.py`)

Rename `TestGetSchema` → `TestKgSchema`. Update all `api.get_schema` call
sites to `api.kg_schema`. Assertions unchanged (returns dict with `nodes`
and `relationships`).

### Unit: MCP wrapper (`test_tool_wrappers.py`)

**`TestKgSchemaWrapper`** (rename from `TestGetSchemaWrapper`, full rewrite):

```python
class TestKgSchemaWrapper:
    _SAMPLE_API_RETURN = {
        "nodes": {"Gene": {"properties": {"locus_tag": "STRING"}}},
        "relationships": {"Has_function": {"source_labels": ["Gene"], "target_labels": ["GOTerm"], "properties": {}}},
    }

    @pytest.mark.asyncio
    async def test_returns_schema(self, tool_fns, mock_ctx):
        with patch("multiomics_explorer.api.functions.kg_schema",
                   return_value=self._SAMPLE_API_RETURN):
            result = await tool_fns["kg_schema"](mock_ctx)
        assert "Gene" in result.nodes
        assert "Has_function" in result.relationships

    @pytest.mark.asyncio
    async def test_nodes_have_properties(self, tool_fns, mock_ctx):
        with patch("multiomics_explorer.api.functions.kg_schema",
                   return_value=self._SAMPLE_API_RETURN):
            result = await tool_fns["kg_schema"](mock_ctx)
        assert "properties" in result.nodes["Gene"]
```

**`EXPECTED_TOOLS`**: replace `"get_schema"` with `"kg_schema"`.

**`TestErrorHandling`**: remove `test_get_schema_value_error` and
`test_get_schema_generic_error` — the only real error is KG unavailability,
which propagates naturally from `api.kg_schema()`. No replacement needed.

### Integration: API contract (`test_api_contract.py`)

Rename `TestGetSchemaContract` → `TestKgSchemaContract`.
Update `api.get_schema` → `api.kg_schema`. Assertions unchanged.

### Integration: smoke test (`test_mcp_tools.py`)

Add:
```python
@pytest.mark.kg
async def test_kg_schema(client):
    result = await client.call_tool("kg_schema", {})
    data = result[0].model_dump()
    assert "Gene" in data["nodes"]
    assert len(data["relationships"]) > 0
```

### Regression / eval cases

**Not applicable** — no query builder, so no `TOOL_BUILDERS` entry and no
regression golden file. No eval case (eval framework checks `results` rows;
`kg_schema` has no results list).

---

## About Content

### Input YAML

`multiomics_explorer/inputs/tools/kg_schema.yaml`

```yaml
examples:
  - title: Get the full schema
    call: kg_schema()
    response: |
      {"nodes": {"Gene": {"properties": {"locus_tag": "STRING", ...}}, ...}, "relationships": {"Has_function": {"source_labels": ["Gene"], "target_labels": ["GOTerm"], "properties": {}}, ...}}

chaining:
  - "kg_schema → run_cypher"

mistakes:
  - "Schema does not include node counts — use run_cypher for counts"
  - wrong: "kg_schema() to discover valid filter values for organism"
    right: "list_filter_values() for categorical filter options; list_organisms() for organism details"
```

Build: `uv run python scripts/build_about_content.py kg_schema`

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Rename `get_schema` → `kg_schema` in tool table |
