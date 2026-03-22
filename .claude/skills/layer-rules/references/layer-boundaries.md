# Layer boundaries — detailed conventions

## Layer 1: `kg/queries_lib.py`

### Signature pattern

```python
def build_{name}(
    *, param1: str, param2: str | None = None,
) -> tuple[str, dict]:
```

- All parameters are keyword-only (after `*`)
- Returns `(cypher_string, params_dict)`
- No `conn` parameter — this layer has no knowledge of connections

### Cypher conventions

- Use `$param_name` placeholders — never f-string interpolate user input
- Alias all RETURN columns: `g.locus_tag AS locus_tag`
- Include `ORDER BY` for deterministic results
- Organism filter pattern: `ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_strain) CONTAINS word)`
- NULL-safe optional filters: `$param IS NULL OR ...`
- For ontology queries, use `ONTOLOGY_CONFIG` dict
- **APOC is available.** Use `apoc.coll.frequencies()` for per-dimension
  breakdowns in summary queries, `apoc.coll.max/min/sort` for
  distributions. Prefer APOC over multi-pass UNWIND aggregation.

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
- Handle modes or limits (those belong in api/ or tools.py)
- Log (no logger calls)

### Naming

Target convention for new tools: `build_{name}` where `{name}` matches
the api function name.

Existing variations:
- `build_get_gene_details` → `get_gene_details`
- `build_get_homologs_groups` + `build_get_homologs_members` → `get_homologs`
- `build_gene_stub` (helper, not a tool)
- `build_list_gene_categories` (used by `list_filter_values`)

Multi-query tools may have multiple builders (e.g., `_groups` + `_members`).

---

## Layer 2: `api/functions.py`

### Signature pattern

```python
def {name}(
    positional_arg: str,
    optional_arg: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> list[dict]:
```

- Positional args first, then keyword-only with `conn` always last
- `conn` defaults to `None` — uses `_default_conn(conn)` to create if needed
- Returns `list[dict]` or `dict` (for single-entity lookups like `get_gene_details`)

### Module docstring contract

```
No limit parameters — callers slice results as needed.
No JSON formatting — returns Python dicts/lists.
Validation errors raise ValueError with specific messages.
```

### Error handling

- Raise `ValueError` with specific messages for invalid inputs
  (e.g., `"identifier must not be empty."`)
- Lucene retry pattern for fulltext queries: catch `Neo4jClientError`,
  escape special chars with `_LUCENE_SPECIAL`, retry once

### Lucene retry pattern (actual code)

```python
try:
    results = conn.execute_query(cypher, **params)
except Neo4jClientError:
    logger.debug("...: Lucene parse error, retrying with escaped query")
    escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
    cypher, params = build_search_...(search_text=escaped, ...)
    results = conn.execute_query(cypher, **params)
```

### Docstring conventions

- First line: what the function does
- `Returns list of dicts with keys: key1, key2, ...` — this is the contract

### Exports

Every API function must be:
1. Added to `api/__init__.py` `__all__` list
2. Re-exported from `multiomics_explorer/__init__.py` `__all__`

### What this layer must NOT do

- Format JSON or produce strings for display
- Import from `mcp_server/`
- Catch exceptions silently (except Lucene retry)

### Limit handling

**Tools with summary/detail modes:** API runs 2-query pattern:
1. Summary query (via `build_{name}_summary()`) — returns `total_entries`,
   `total_matching`, and breakdowns
2. Detail query (via `build_{name}()`) with LIMIT in Cypher — returns rows

Both modes always run the summary query. Detail additionally runs the
detail query. API returns breakdowns + results in a unified dict.

**Tools with filters but no modes:** Same 2-query pattern but summary
query is just counts (`total_entries`, `total_matching`).

**Tools without filters (e.g. `list_organisms`):** API accepts `limit`,
runs single query (no LIMIT in Cypher), slices in Python. This gives
`total_entries` from the full result set without a separate count query.

---

## Layer 3: `mcp_server/tools.py`

### Registration pattern (v1 — existing tools, being migrated)

Existing tools use sync `def`, `logger`, `_fmt`, error strings.
These will be migrated to v2 in Phase D.

### Registration pattern (v2 — new tools)

```python
def register_tools(mcp: FastMCP):
    class {Name}Result(BaseModel):
        field1: str = Field(description="What this is (e.g. 'example')")
        field2: int = Field(default=0, description="What this means (e.g. 42)")

    class {Name}Response(BaseModel):
        total_entries: int = Field(description="Total rows in KG")
        total_matching: int = Field(description="Rows matching filters")  # only for tools with filters
        returned: int = Field(description="Rows in this response")
        truncated: bool = Field(description="True if total_matching > returned")
        results: list[{Name}Result]

    @mcp.tool(
        tags={"domain", "action"},
        annotations={"readOnlyHint": True},
    )
    async def tool_name(
        ctx: Context,
        param: Annotated[str, Field(description="...")],
        limit: Annotated[int, Field(description="Max results.", ge=1)] = 50,
    ) -> {Name}Response:
        """Tool purpose. What it does and when to use it."""
        await ctx.info(f"tool_name param={param}")
        try:
            conn = _conn(ctx)
            result = api.tool_name(param, limit=limit, conn=conn)
            rows = [{Name}Result(**r) for r in result["results"]]
            return {Name}Response(
                total_entries=result["total_entries"],
                total_matching=result["total_matching"],
                returned=len(rows),
                truncated=result["total_matching"] > len(rows),
                results=rows,
            )
        except ValueError as e:
            await ctx.warning(f"tool_name error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"tool_name unexpected error: {e}")
            raise ToolError(f"Error in tool_name: {e}")
```

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

### Error handling

- `ValueError` from api/: `raise ToolError(str(e))`
- `Exception`: `raise ToolError(f"Error in {tool_name}: {e}")`
- Empty results: return `[]` — not an error, let the LLM decide what to do

### Return type

- Define Pydantic `BaseModel` response models (`{Name}Result` per row,
  `{Name}Response` envelope). Return type annotation on the tool
  function → FastMCP auto-generates `outputSchema` in the MCP tool def.
- Return Pydantic model instances — FastMCP handles serialization
- No `json.dumps`, no `_fmt` — return model instances directly
- Pydantic models at MCP boundary only. API layer returns plain `dict`.
- **Tools with summary/detail modes:** Use unified response model.
  Envelope includes breakdowns (from summary query) + results (from
  detail query). Both modes return the same `{Name}Response` type:
  - Summary mode: breakdowns populated, `results: []`, `returned: 0`,
    `truncated: True` (signals results exist but aren't shown)
  - Detail mode: breakdowns populated, results populated, `returned`
    and `truncated` reflect the limit
  Both modes always run the summary query (cheap aggregation).
  Detail additionally runs the detail query with LIMIT in Cypher.
- **Tools with filters but no modes:** 2-query pattern: summary query
  for `total_entries` + `total_matching`, data query with LIMIT.
  API returns `{total_entries, total_matching, results}`.
  MCP wrapper adds `returned` and `truncated`.
- **Tools without filters + limit:** Single query, slice in Python.
  API returns `{total_entries, results}` (no `total_matching`).
  MCP wrapper adds `returned` and `truncated`.

### Docstring conventions (LLM-facing)

- First paragraph: what the tool does, when to use it
- Param descriptions go in `Field(description=...)`, not `Args:`
- Return schema is in Pydantic models (auto-generated as `outputSchema`) —
  do not duplicate return fields in the docstring
- Mention related tools for chaining ("Use list_organisms to see valid organisms")

### Target pattern (v2, with FastMCP features)

New tools should use `Annotated`, `Field`, `Literal`, `ToolError`:

```python
from typing import Annotated, Literal
from pydantic import Field
from fastmcp.exceptions import ToolError

@mcp.tool(
    tags={"domain_tag", "action_tag"},
    annotations={"readOnlyHint": True},
)
async def tool_name(
    ctx: Context,
    param: Annotated[str, Field(description="...")],
    mode: Annotated[
        Literal["summary", "detail"],
        Field(description="'summary' returns breakdowns to guide filtering. "
              "'detail' returns individual rows. Start with summary."),
    ] = "summary",
    verbose: Annotated[bool, Field(
        description="Detail mode only. Include secondary fields.",
    )] = False,
    limit: Annotated[
        int, Field(ge=1, le=500, description="Detail mode only. Max rows."),
    ] = 50,
) -> {Name}Response:
```

**Key conventions:**
- Param descriptions go in `Field(description=...)`, not in docstring `Args:`
- Use `Literal["val1", "val2"]` for params with fixed valid values
  known at code time (e.g. mode, ontology). Not for KG-derived values
  (e.g. treatment_type) — those use `list_filter_values` for discovery.
- Use `Field(ge=..., le=...)` for numeric constraints
- Use `ToolError` for errors — always visible to client
- `async def` tools with `await ctx.info/warning/error()` for MCP client-visible logging
- Use `tags` for categorization (e.g. `{"publications", "discovery"}`)
- All tools are read-only: `annotations={"readOnlyHint": True}`

### What this layer must NOT do

- Call `queries_lib` directly — always go through `api/`
- Return error strings — use `ToolError` instead
- Execute raw Cypher (except through `api.run_cypher`)

---

## Layer 4: Skills (MCP resources)

### About content

Per-tool files at `skills/multiomics-kg-guide/references/tools/{tool-name}.md`.
Served via MCP resource at URI `docs://tools/{tool-name}` (not a tool mode parameter).

Content per tool:
- What the tool does (beyond the docstring)
- Parameter guide with valid values
- Response guide: fields in summary and detail modes
- Examples using tagged fenced blocks
- Common mistakes with corrections
- Chaining patterns

### Tagged block format

````markdown
```example-call
tool_name(param="value", mode="summary")
```

```expected-keys
key1, key2, key3
```
````

Tests extract `expected-keys` blocks and verify against actual tool output.

### Sync

Research skills source: `multiomics_explorer/skills/`
Dev copy: `.claude/skills/research/` (gitignored)
Sync: `scripts/sync_skills.sh`

Update about content whenever tool return fields change.

---

## Standard parameter names

| Name | Layer | Used in |
|---|---|---|
| `identifier` | all | resolve_gene |
| `gene_id` | builders + api | get_gene_details, get_homologs, gene_ontology_terms |
| `gene_ids` | builders + api | gene_overview |
| `search_text` | all | search_genes, search_ontology |
| `organism` | all | resolve_gene, search_genes, genes_by_ontology |
| `ontology` | all | search_ontology, genes_by_ontology, gene_ontology_terms |
| `term_ids` | all | genes_by_ontology |
| `category` | all | search_genes |
| `conn` | api only | all api functions (keyword-only, last) |
| `ctx` | MCP only | all MCP wrappers (first param, injected by FastMCP) |
| `limit` | MCP + api | tools with large or growing result sets |
| `mode` | MCP + api (v2) | `Literal["summary", "detail"]` at MCP, `str` at API. Same name at both layers for LLM consistency. About content served via MCP resource `docs://tools/{name}`, not a mode value |
| `verbose` | all | include secondary columns (heavy text, taxonomy hierarchies, descriptive fields). Orthogonal to modes — verbose controls columns, modes control rows |

## String matching rules

All string filters must be case-insensitive. Use `toLower()` on both
sides for CONTAINS/exact matches. Fulltext indexes are inherently
case-insensitive.

Fulltext search tools must return `score` in RETURN columns and
ORDER BY score DESC. This lets the LLM see relevance ranking.
In summary mode, include `score_max` and `score_median` for distribution
context — lets Claude judge if top results are highly relevant or barely
matching.

## Standard return field names

| Field | Used in |
|---|---|
| `locus_tag` | resolve_gene, search_genes, gene_overview, genes_by_ontology, homologs |
| `gene_name` | resolve_gene, search_genes, gene_overview, homologs |
| `product` | resolve_gene, search_genes, gene_overview, homologs |
| `organism_strain` | resolve_gene, search_genes, gene_overview, genes_by_ontology, homologs |
| `annotation_quality` | search_genes, gene_overview |
| `score` | search_genes, search_ontology, list_experiments (when search_text used) |
| `score_max`, `score_median` | summary mode of fulltext search tools |
| `id`, `name` | search_ontology, gene_ontology_terms |
| `gene_category` | gene_overview |
| `gene_summary` | search_genes, gene_overview |
| `experiment_id` | list_experiments |
| `experiment_count` | list_experiments summary breakdowns |
| `treatment_type` | list_experiments |
| `omics_type` | list_experiments |
| `publication_doi` | list_experiments, list_publications |

## Docstring conventions by layer

| Layer | Audience | Content |
|---|---|---|
| `queries_lib.py` | Developers | Brief: what Cypher pattern, what RETURN columns |
| `api/functions.py` | Developers + scripts | Return dict keys listed, exceptions documented |
| `mcp_server/tools.py` | LLMs | Purpose + when to use. Param descriptions in `Field()`, not `Args:`. Return schema in Pydantic models. |
