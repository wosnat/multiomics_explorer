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
- Apply display limits (no `limit` parameter — callers slice)
- Import from `mcp_server/`
- Catch exceptions silently (except Lucene retry)

---

## Layer 3: `mcp_server/tools.py`

### Registration pattern

```python
def register_tools(mcp: FastMCP):
    @mcp.tool()
    def tool_name(
        ctx: Context,
        param1: str,
        param2: str | None = None,
        limit: int = 10,
    ) -> str:
        """LLM-facing docstring.

        Args:
            param1: Description visible to MCP clients.
            param2: Optional filter description.
            limit: Max results (default N, max M).
        """
        logger.info("tool_name param1=%s", param1)
        try:
            conn = _conn(ctx)
            results = api.tool_name(param1, param2=param2, conn=conn)
            if not results:
                return "No results found."
            return _fmt(results, limit=limit)
        except ValueError as e:
            logger.warning("tool_name error: %s", e)
            return f"Error: {e}"
        except Exception as e:
            logger.warning("tool_name unexpected error: %s", e)
            return f"Error in tool_name: {e}"
```

### Helpers

- `_conn(ctx)` — extracts `GraphConnection` from lifespan context
- `_fmt(results, limit)` — slices and `json.dumps` with indent=2
- `_group_by_organism(results)` — groups gene results by `organism_strain`
- `_no_groups_msg(gene_id)` — standard message for no homolog groups

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

- `ValueError` from api/: return `f"Error: {e}"`
- `Exception`: return `f"Error in {tool_name}: {e}"`
- Never raise — always return a string

### Docstring conventions (LLM-facing)

- First paragraph: what the tool does, when to use it
- `Args:` section with per-parameter descriptions
- Mention related tools for chaining ("Use list_organisms to see valid organisms")
- Mention valid values or ranges

### Target pattern (v2, with FastMCP features)

New tools should use `Annotated`, `Field`, `Literal`, `ToolError`:

```python
from typing import Annotated, Literal
from pydantic import Field
from fastmcp.exceptions import ToolError

@mcp.tool(annotations={"readOnlyHint": True})
def tool_name(
    ctx: Context,
    param: Annotated[str, Field(description="...")],
    mode: Annotated[
        Literal["summary", "detail", "about"],
        Field(description="Response mode"),
    ] = "summary",
    limit: Annotated[
        int, Field(ge=1, le=500, description="Max rows in detail mode"),
    ] = 100,
) -> dict | str:
```

### What this layer must NOT do

- Call `queries_lib` directly — always go through `api/`
- Raise exceptions to the MCP client
- Execute raw Cypher (except through `api.run_cypher`)

---

## Layer 4: Skills

### About-mode content

Per-tool files at `skills/multiomics-kg-guide/references/tools/{tool-name}.md`.

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

Update about-mode content whenever tool return fields change.

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
| `limit` | MCP only | tools with large result sets |
| `mode` | MCP only (v2) | summary/detail/about |
| `summary` | api (v2) | functions with summary variant |

## Standard return field names

| Field | Used in |
|---|---|
| `locus_tag` | resolve_gene, search_genes, gene_overview, genes_by_ontology, homologs |
| `gene_name` | resolve_gene, search_genes, gene_overview, homologs |
| `product` | resolve_gene, search_genes, gene_overview, homologs |
| `organism_strain` | resolve_gene, search_genes, gene_overview, genes_by_ontology, homologs |
| `annotation_quality` | search_genes, gene_overview |
| `score` | search_genes, search_ontology |
| `id`, `name` | search_ontology, gene_ontology_terms |
| `gene_category` | gene_overview |
| `gene_summary` | search_genes, gene_overview |

## Docstring conventions by layer

| Layer | Audience | Content |
|---|---|---|
| `queries_lib.py` | Developers | Brief: what Cypher pattern, what RETURN columns |
| `api/functions.py` | Developers + scripts | Return dict keys listed, exceptions documented |
| `mcp_server/tools.py` | LLMs | Full `Args:` section, chaining hints, valid values |
