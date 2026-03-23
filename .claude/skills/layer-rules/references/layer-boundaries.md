# Layer boundaries — detailed conventions

## Layer 1: `kg/queries_lib.py`

### Signature pattern

```python
def build_{name}(
    *, param1: str, param2: str | None = None,
    verbose: bool = False,
) -> tuple[str, dict]:
```

- All parameters are keyword-only (after `*`)
- Returns `(cypher_string, params_dict)`
- No `conn` parameter — this layer has no knowledge of connections
- `verbose` controls RETURN columns — compact by default, heavy
  text fields (abstract, description, full annotations) when True

### Cypher conventions

- Use `$param_name` placeholders — never f-string interpolate user input
- Alias all RETURN columns: `g.locus_tag AS locus_tag`
- Include `ORDER BY` for deterministic results
- Organism filter pattern: `ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_strain) CONTAINS word)`
- NULL-safe optional filters: `$param IS NULL OR ...`
- For ontology queries, use `ONTOLOGY_CONFIG` dict
- **APOC is available.** Use throughout:
  - `apoc.coll.frequencies()` for per-dimension breakdowns in summary queries
  - `apoc.coll.max/min/sort` for distributions
  - `apoc.map.fromPairs` / `apoc.map.merge` for dynamic result dicts
    (e.g., verbose vs compact RETURN without duplicating the query)
  - `apoc.convert.fromJsonMap` for parsing JSON-encoded precomputed
    properties stored as strings
  - `apoc.text.join` for string aggregation
  - Don't use APOC for things Cypher does natively (aggregation, path
    traversal, basic filtering)

### List-type filter parameters

For exact-match filters where multiple values make sense (e.g.
treatment types, omics types, DOIs), use `list[str] | None` with
Cypher `IN` matching. Normalize case in Python before passing to
Cypher (`toLower`/`toUpper` as appropriate).

```python
if treatment_type:
    conditions.append("toLower(e.treatment_type) IN $treatment_types")
    params["treatment_types"] = [t.lower() for t in treatment_type]
```

CONTAINS filters stay as single `str` (fuzzy match doesn't combine
well as a list).

### What this layer must NOT do

- Execute queries (no `conn.execute_query`)
- Import from `api/` or `mcp_server/`
- Format output (no JSON, no grouping)
- Handle modes or limits (those belong in api/)
- Log (no logger calls)

### Naming

Target convention: `build_{name}` where `{name}` matches the api
function name. Summary variant: `build_{name}_summary`.

Existing variations (transitional):
- `build_get_gene_details` → being retired
- `build_get_homologs_groups` + `build_get_homologs_members` → `gene_homologs`
- `build_gene_stub` (helper, not a tool)
- `build_list_gene_categories` (used by `list_filter_values`)

Multi-query tools may have multiple builders (e.g., `_groups` + `_members`).

---

## Layer 2: `api/functions.py`

### Signature pattern

```python
def {name}(
    locus_tags: list[str],              # ID params are always lists
    organism: str | None = None,         # filters are singular
    summary: bool = False,               # mode switches are booleans
    verbose: bool = False,
    limit: int | None = None,            # None = all rows
    *,
    conn: GraphConnection | None = None,
) -> dict:
```

- Positional args first, then keyword-only with `conn` always last
- `conn` defaults to `None` — uses `_default_conn(conn)` to create if needed
- Always returns `dict` with summary fields + `results` list

### Parameter guidelines

- **ID parameters are always lists** — `locus_tags`, `experiment_ids`,
  `group_ids`. Never singular `locus_tag` or `group_id`. Exception:
  `identifier` in `resolve_gene` (ambiguous input, not ID lookup).
- **Any tool that accepts an ID list is a batch tool.** Batch input
  can be arbitrarily large. Therefore every ID-list tool supports
  `limit`, `summary`, summary fields, and `not_found`.
- **Filters are singular** — `organism`, `direction`, `source`.
- **Booleans for mode switches** — `summary`, `verbose`.

### Response dict — api/ assembles everything

The api/ layer owns the complete response dict. MCP just wraps it.

```python
return {
    # Summary fields (always present, computed over full result set)
    "total_matching": matching,        # count matching all filters (full set)
    "total_entries": total,            # total in KG before filtering (omit for no-filter tools)
    "returned": len(results),
    "truncated": total_matching > len(results),
    "not_found": missing_ids,         # batch tools only — list of input IDs not matched
    "direction_breakdown": {...},     # tool-specific summary fields
    # Results (flat list of dicts, long form)
    "results": results,
}
```

- `total_matching` — count of results matching all filters. For no-filter tools, equals total in KG.
- Both can be present. Always include at least one.
- `not_found` — present on batch tools (accept ID lists). Empty list when all matched.
- `returned` and `truncated` computed here, not in MCP.

### `summary` and `limit`

- `summary=True` → sets `limit=0` (sugar for "summary fields only, no rows")
- `summary=False` (default in api/) → `results` populated, capped by `limit`
- `limit=None` (default in api/) → all rows

### 2-query pattern

For tools with summary fields:
1. Summary query (via `build_{name}_summary()`) — always runs (cheap)
2. Detail query (via `build_{name}()`) — only runs when `limit != 0`

```python
# Summary query — always runs
sum_cypher, sum_params = queries_lib.build_{name}_summary(...)
result = conn.execute_query(sum_cypher, **sum_params)

# Detail query — skip when summary only
if limit == 0:
    result["results"] = []
else:
    det_cypher, det_params = queries_lib.build_{name}(...)
    all_rows = conn.execute_query(det_cypher, **det_params)
    result["results"] = all_rows[:limit] if limit else all_rows

result["returned"] = len(result["results"])
result["truncated"] = result["total_matching"] > result["returned"]
return result
```

For tools without filters (e.g. `list_organisms`): single query,
slice in Python. `total_matching` from full result set.

### Error handling

- Raise `ValueError` with specific messages for invalid inputs
- Lucene retry pattern for fulltext queries: catch `Neo4jClientError`,
  escape special chars with `_LUCENE_SPECIAL`, retry once

### Exports

Every API function must be:
1. Added to `api/__init__.py` `__all__` list
2. Re-exported from `multiomics_explorer/__init__.py` `__all__`

### What this layer must NOT do

- Format JSON or produce strings for display
- Import from `mcp_server/`
- Catch exceptions silently (except Lucene retry)

---

## Layer 3: `mcp_server/tools.py`

### MCP wrappers are thin

The api/ layer assembles the complete response dict. MCP just:
1. Forwards parameters (adds default `limit`, e.g. 5)
2. Validates via `Response(**data)`
3. Logs via `ctx.info/warning/error`

No field computation in MCP. If the dict is wrong, fix it in api/.

### Registration pattern

```python
def register_tools(mcp: FastMCP):
    class {Name}Result(BaseModel):
        field1: str = Field(description="What this is (e.g. 'example')")
        field2: int = Field(default=0, description="What this means (e.g. 42)")

    class {Name}Response(BaseModel):
        total_matching: int = Field(description="Total matching filters (or total in KG if no filters)")
        total_matching: int = Field(description="Rows matching filters")
        returned: int = Field(description="Rows in this response")
        truncated: bool = Field(description="True if total_matching > returned")
        not_found: list[str] = Field(default_factory=list, description="Input IDs not found")
        results: list[{Name}Result] = Field(default_factory=list)

    @mcp.tool(
        tags={"domain", "action"},
        annotations={"readOnlyHint": True},
    )
    async def tool_name(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(description="Gene locus tags")],
        summary: Annotated[bool, Field(
            description="If true, return summary fields only (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include secondary fields in results rows.",
        )] = False,
        limit: Annotated[int, Field(description="Max results.", ge=1)] = 5,
    ) -> {Name}Response:
        """Tool purpose. What it does and when to use it."""
        await ctx.info(f"tool_name limit={limit}")
        try:
            conn = _conn(ctx)
            data = api.tool_name(
                locus_tags=locus_tags, summary=summary,
                verbose=verbose, limit=limit, conn=conn)
            data["results"] = [{Name}Result(**r) for r in data["results"]]
            return {Name}Response(**data)
        except ValueError as e:
            await ctx.warning(f"tool_name error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"tool_name unexpected error: {e}")
            raise ToolError(f"Error in tool_name: {e}")
```

### Key conventions

- `ctx: Context` first, then tool params, then structural params
  (`summary`, `verbose`, `limit`)
- Param descriptions go in `Field(description=...)`, not in docstring
- Use `Literal["val1", "val2"]` for fixed valid values known at code time
- Use `Field(ge=..., le=...)` for numeric constraints
- `ToolError` for errors — always visible to client
- `async def` with `await ctx.info/warning/error()`
- Tags for categorization, `annotations={"readOnlyHint": True}` always
- Pydantic `Field(description=...)` with examples on all result fields
- Docstring is tool-level purpose only — return schema in Pydantic models

### Helpers

- `_conn(ctx)` — extracts `GraphConnection` from lifespan context
- `_group_by_organism(results)` — groups gene results by `organism_strain`

### Caching pattern

```python
lc = ctx.request_context.lifespan_context
cached = getattr(lc, "_cache_attr", None)
if cached is not None:
    return cached
# ... compute response ...
lc._cache_attr = response
```

### What this layer must NOT do

- Call `queries_lib` directly — always go through `api/`
- Compute response fields (`returned`, `truncated`, `not_found`) — api/ owns that
- Return error strings — use `ToolError` instead
- Execute raw Cypher (except through `api.run_cypher`)

---

## Layer 4: Skills (MCP resources)

### About content

Auto-generated from Pydantic models + human-authored input YAML.
No hand-written tagged blocks needed — params table, response
format, and expected keys come from the Pydantic models.

**Source files:**
- Input YAML: `multiomics_explorer/inputs/tools/{name}.yaml`
- Build script: `scripts/build_about_content.py`
- Output: `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md`
- Served via MCP resource at `docs://tools/{tool-name}`

**Human authors the YAML** (examples, chaining, mistakes).
**Script extracts from Pydantic** (params, response format, keys).

### Sync

Research skills source: `multiomics_explorer/skills/`
Dev copy: `.claude/skills/research/` (gitignored)
Sync: `scripts/sync_skills.sh`

Update YAML + rebuild when tool behavior changes.

---

## Standard parameter names

| Name | Type | Layer | Used in |
|---|---|---|---|
| `identifier` | `str` | all | resolve_gene |
| `locus_tags` | `list[str]` | all | gene_overview, gene_ontology_terms, gene_homologs, differential_expression_by_gene |
| `experiment_ids` | `list[str]` | all | differential_expression_by_gene, differential_expression_by_ortholog |
| `group_ids` | `list[str]` | all | genes_by_homolog_group |
| `search_text` | `str` | all | genes_by_function, search_ontology |
| `organism` | `str \| None` | all | resolve_gene, genes_by_function, genes_by_ontology |
| `ontology` | `str` | all | search_ontology, genes_by_ontology, gene_ontology_terms |
| `term_ids` | `list[str]` | all | genes_by_ontology |
| `category` | `str \| None` | all | genes_by_function |
| `summary` | `bool` | api/ + MCP | sugar for `limit=0`. Default False in api/, False in MCP (small default limit gives rows) |
| `verbose` | `bool` | all | include secondary columns. Controls which columns, not which rows. |
| `limit` | `int \| None` | api/ + MCP | caps `results` length. Default None in api/, small cap (e.g. 5) in MCP |
| `conn` | `GraphConnection \| None` | api/ only | keyword-only, always last |
| `ctx` | `Context` | MCP only | first param, injected by FastMCP |

**ID params are always lists.** No singular `locus_tag`, `group_id`, etc.
Callers never check whether to pass a string or list.

## String matching rules

All string filters must be case-insensitive. Use `toLower()` on both
sides for CONTAINS/exact matches. Fulltext indexes are inherently
case-insensitive.

Fulltext search tools must return `score` in RETURN columns and
ORDER BY score DESC. This lets the LLM see relevance ranking.
In summary queries, include `score_max` and `score_median` for
distribution context.

## Standard return field names

| Field | Used in |
|---|---|
| `locus_tag` | resolve_gene, genes_by_function, gene_overview, genes_by_ontology, gene_homologs |
| `gene_name` | resolve_gene, genes_by_function, gene_overview, gene_homologs |
| `product` | resolve_gene, genes_by_function, gene_overview, gene_homologs |
| `organism_strain` | resolve_gene, genes_by_function, gene_overview, genes_by_ontology, gene_homologs |
| `annotation_quality` | genes_by_function, gene_overview |
| `score` | genes_by_function, search_ontology, list_experiments (when search_text used) |
| `score_max`, `score_median` | summary fields of fulltext search tools |
| `id`, `name` | search_ontology, gene_ontology_terms |
| `gene_category` | gene_overview |
| `gene_summary` | genes_by_function, gene_overview |
| `experiment_id` | list_experiments |
| `experiment_count` | list_experiments summary breakdowns |
| `treatment_type` | list_experiments |
| `omics_type` | list_experiments |
| `publication_doi` | list_experiments, list_publications |

### Envelope fields

| Field | When present | Meaning |
|---|---|---|
| `total_matching` | Always | Count of results matching all filters (full set, not capped by limit) |
| `total_entries` | Tools with filters | Total in KG before filtering. Gives filter selectivity context ("3 of 15"). Omit for no-filter tools. |
| `returned` | Always | `len(results)` — rows in this response |
| `truncated` | Always | `True` when `total_matching > returned` (including `summary=True` with matches) |
| `not_found` | Batch tools only (accept ID lists) | Input IDs with no match. Empty list when all matched. Not on search tools. |
| `results` | Always | Flat `list[dict]`, long form (one row per entity × dimension) |

## Docstring conventions by layer

| Layer | Audience | Content |
|---|---|---|
| `queries_lib.py` | Developers | Brief: what Cypher pattern, what RETURN columns, verbose-only keys |
| `api/functions.py` | Developers + scripts | Return dict keys listed (summary fields + result keys), exceptions documented |
| `mcp_server/tools.py` | LLMs | Purpose + when to use. Param descriptions in `Field()`. Return schema in Pydantic models. |
