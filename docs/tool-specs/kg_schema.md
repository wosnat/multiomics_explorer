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

### Option A: Small result set (no modes needed)

Schema is always small (tens of node labels, tens of relationship types).
No `summary`, `verbose`, `limit`, or `not_found`.

**Sort key:** alphabetical on node/relationship name (already done in `to_dict()`)

**Verbose:** no

---

## Implementation Plan

This is a **rename + v3 pattern upgrade**. The core logic (`load_schema_from_neo4j`)
is unchanged. No new query builder needed.

### What changes

| Layer | Change |
|---|---|
| `kg/queries_lib.py` | No change — schema uses `kg/schema.py`, not queries_lib |
| `api/functions.py` | Rename `get_schema` → `kg_schema` |
| `api/__init__.py` | Update import + `__all__` |
| `multiomics_explorer/__init__.py` | Update import + `__all__` |
| `mcp_server/tools.py` | Rename + v3 pattern: `async def`, `ToolError`, Pydantic model, `@mcp.tool(tags=..., annotations=...)`, call `api.kg_schema()` instead of bypassing api/ |
| `tests/unit/test_api_functions.py` | Rename class + references |
| `tests/unit/test_tool_wrappers.py` | Rename class + references, update `EXPECTED_TOOLS`, update error test class, update response assertions |
| `tests/integration/test_api_contract.py` | Rename class + call site |
| `tests/evals/cases.yaml` | Add `kg_schema_all` case |
| About content | New input YAML + build |
| `CLAUDE.md` | Update tool table |

### Pydantic models

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

No `{Name}Result` per-row model — the schema is a single structured object,
not a list of rows. `KgSchemaResponse` IS the envelope.

### API function

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

### MCP wrapper

```python
async def kg_schema(ctx: Context) -> KgSchemaResponse:
    """..."""
    data = api.kg_schema(conn=_conn(ctx))
    return KgSchemaResponse(**data)
```

Errors propagate as `ToolError` — remove old try/except error-string returns.

---

## Tests

### Unit: API function (`test_api_functions.py`)

Rename `TestGetSchema` → `TestKgSchema`. Update all call sites from
`api.get_schema` → `api.kg_schema`. Assertions unchanged.

### Unit: MCP wrapper (`test_tool_wrappers.py`)

- Rename `TestGetSchemaWrapper` → `TestKgSchemaWrapper`
- Update `EXPECTED_TOOLS`: replace `"get_schema"` with `"kg_schema"`
- Rename error test methods in `TestErrorHandling`
- Update `tool_fns["get_schema"]` → `tool_fns["kg_schema"]`
- Update assertions: tool now returns a `KgSchemaResponse` (not a raw string).
  `result.nodes` and `result.relationships` replace string checks.
- Error tests: `ToolError` raised instead of error string returned.

### Integration (`test_api_contract.py`)

Rename `TestGetSchemaContract` → `TestKgSchemaContract`.
Update `api.get_schema` → `api.kg_schema`. Assertions unchanged.

### Eval cases (`cases.yaml`)

```yaml
- id: kg_schema_all
  tool: kg_schema
  desc: Schema always returns nodes and relationships
  params: {}
  expect:
    columns: [nodes, relationships]
```

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
  - wrong: "kg_schema() to get filter values for organism"
    right: "list_filter_values() for categorical filter options; list_organisms() for organism details"
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Rename `get_schema` → `kg_schema` in tool table |
