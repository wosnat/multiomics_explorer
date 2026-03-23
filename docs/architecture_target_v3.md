# Target architecture

This document describes the target code architecture for the
multiomics_explorer package. See `methodology/llm_omics_analysis_v3.md`
for the design rationale (why dual interface, why skills, why summary
mode) and `methodology/tool_framework.md` for the authoritative tool
surface (tool names, phases, output schemas, homology framework).

---

## Package structure

```
multiomics_explorer/
├── __init__.py                 # Public API re-exports
├── kg/                         # Core layer — shared by all interfaces
│   ├── connection.py           #   Neo4j driver wrapper (GraphConnection)
│   ├── constants.py            #   Shared constants (valid sources, levels, etc.)
│   ├── queries_lib.py          #   Query builder functions → tuple[str, dict]
│   ├── queries.py              #   Curated Cypher + few-shot examples
│   └── schema.py               #   Schema introspection from live KG
├── api/                        # Public Python API
│   ├── __init__.py             #   Re-exports for `from multiomics_explorer import ...`
│   └── functions.py            #   High-level functions → list[dict]
├── mcp_server/                 # MCP server for LLM access
│   ├── server.py               #   FastMCP entry point with Neo4j lifespan
│   └── tools.py                #   MCP tool wrappers (Pydantic params/returns)
├── skills/                     # Research skills (shipped, agentskills.io format)
│   ├── multiomics-kg-guide/        #   Layer 1: Tool Wrapper (always active)
│   ├── characterize-experiment/#   Layer 2: Pipeline
│   ├── compare-conditions/     #   Layer 2: Pipeline
│   ├── gene-survey/            #   Layer 2: Pipeline
│   ├── ortholog-conservation/  #   Layer 2: Pipeline
│   ├── timecourse-analysis/    #   Layer 2: Pipeline
│   ├── export-de-genes/        #   Layer 2: Pipeline
│   └── clarify-research-question/ # Layer 3: Inversion
├── cli/                        # Typer CLI
│   └── main.py
└── config/                     # Settings
    └── settings.py             #   Pydantic Settings from .env
```

Dev skills live in `.claude/skills/` in this repo (not shipped with
the package). Research skills are copied from
`multiomics_explorer/skills/` into `.claude/skills/research/` for
dev use (see "Skills in the dev repo" below).

---

## Layer diagram

```
┌──────────────────────────────────────────────────────────┐
│                    Consumers                              │
│                                                          │
│   Claude Code      Claude Desktop      Python scripts    │
│   (agentic)        (chat)              (import)          │
│   + skills         + MCP instructions                    │
└───────┬──────────────┬─────────────────┬─────────────────┘
        │              │                 │
        │   MCP        │   MCP           │  import
        │              │                 │
┌───────▼──────────────▼──┐              │
│   mcp_server/           │              │
│                         │              │
│   tools.py              │              │
│   - Pydantic models     │              │
│   - default limits      │              │
│   - ctx logging         │              │
│   - ToolError           │              │
└───────────┬─────────────┘              │
            │  calls api/                │
            │                            │
    ┌───────▼────────────────────────────▼─────────────────┐
    │   api/                                                │
    │                                                      │
    │   functions.py                                       │
    │   - returns dict (summary fields + results)          │
    │   - limit=None default (all rows)                    │
    │   - verbose for detail level                         │
    │   - raises ValueError                                │
    └───────────────────────┬──────────────────────────────┘
                            │
                    ┌───────▼───────┐
                    │   kg/         │
                    │               │
                    │ queries_lib   │  build_*() → tuple[str, dict]
                    │ connection    │  execute_query() → list[dict]
                    │ constants     │
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │    Neo4j      │
                    │  (read-only)  │
                    └───────────────┘
```

---

## The three code layers

### 1. `kg/` — query builders + connection

**Responsibility:** Build parameterized Cypher queries. Execute them.
Return raw results.

Functions in `queries_lib.py` return `tuple[str, dict]` — a Cypher
query string and its parameters. They do NOT execute the query. This
keeps them testable without Neo4j.

```python
# queries_lib.py — detail query (returns rows)
def build_differential_expression_by_gene(
    *, experiment_ids: list[str] | None = None,
    locus_tags: list[str] | None = None,
    significant_only: bool | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
    verbose: bool = False,
) -> tuple[str, dict]:
    """Build Cypher for gene-centric expression data rows.

    Matches (Experiment)-[Changes_expression_of]->(Gene) with optional filters.
    Returns one row per gene × experiment × timepoint (long form).

    verbose=False return keys: locus_tag, gene_name, product,
    organism_strain, experiment_id, experiment_name, condition_type,
    treatment, timepoint, timepoint_hours, log2fc, padj, direction,
    rank, significant

    verbose=True adds: category, description, go_terms, ...
    """
    ...

# queries_lib.py — summary query (returns aggregations)
def build_differential_expression_by_gene_summary(
    *, experiment_ids: list[str] | None = None,
    locus_tags: list[str] | None = None,
    significant_only: bool | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
) -> tuple[str, dict]:
    """Build Cypher for gene-centric expression summary statistics.

    Returns aggregated counts and breakdowns. Reads precomputed
    properties where available, falls back to COUNT/collect.
    Different MATCH/RETURN than the detail query.
    """
    ...
```

**Rules:**
- No formatting, no mode logic
- No MCP or API imports — this layer has no knowledge of consumers
- Functions are keyword-only (`*`) for clarity
- Detail and summary are separate functions — they generate
  fundamentally different Cypher (different RETURN clauses,
  possibly different MATCH patterns). The api/ layer picks which
  one to call.
- Detail builders accept an optional `limit` parameter — when
  present, adds `ORDER BY {sort_key} LIMIT $limit` to the Cypher.
  This pushes row limiting into the database for efficiency over
  remote connections. When absent, returns all rows.
- Query builders are unit-testable (test the generated Cypher, not
  the results)

**Batching in queries:** When detail queries return large result
sets over a remote KG, query efficiency matters. Design decisions
per query builder:
- Use parameters with list values (`WHERE g.locus_tag IN $locus_tags`)
  rather than multiple round-trips
- Summary queries should read precomputed properties or use
  aggregation — never fetch all rows to count them
- For queries that join multiple patterns, consider whether the
  Cypher planner handles it efficiently or whether splitting into
  multiple focused queries (orchestrated by api/) is better

**Use APOC where it simplifies queries.** The KG is deployed with
APOC installed. Useful for:
- `apoc.coll.frequencies()` — per-dimension breakdowns in summary
  queries (e.g., direction counts, organism counts)
- `apoc.coll.max/min/sort` — distributions (score_max, score_median)
- `apoc.map.fromPairs` / `apoc.map.merge` — building result dicts
  dynamically (e.g., verbose vs compact RETURN clauses without
  duplicating the full query)
- `apoc.coll.sortMaps` — server-side sorting of collected maps
- `apoc.text.join` — string aggregation
- `apoc.convert.fromJsonMap` — parsing JSON-encoded precomputed
  properties stored as strings

Don't use APOC for things Cypher does natively (aggregation, path
traversal, basic filtering). Use it when it avoids client-side
post-processing or simplifies conditional RETURN clauses.

### 2. `api/` — public Python API

**Responsibility:** High-level functions that combine query building +
execution. This is what scripts import and what MCP tools call.

```python
# api/functions.py
def differential_expression_by_gene(
    experiment_ids: list[str] | None = None,
    locus_tags: list[str] | None = None,
    significant_only: bool | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Query gene-centric differential expression data.

    Returns dict with summary fields + results list.
    Results are long form: one row per gene × experiment × timepoint,
    all context inlined (no separate metadata tables).

    Args:
        ...
        summary: If True, return summary fields only (results=[]).
        verbose: Include full annotation fields in results rows.
        limit: Max rows in results. None = all rows. Ignored
            when summary=True.
        conn: Neo4j connection. Creates a default if not provided.

    Returns:
        dict with keys:
            total_matching (int): total genes matching filters
            direction_breakdown (dict): {"up": N, "down": N}
            results (list[dict]): each dict has keys: locus_tag,
                gene_name, product, organism_strain, experiment_id,
                experiment_name, condition_type, treatment, timepoint,
                timepoint_hours, log2fc, padj, direction, rank,
                significant
    """
    conn = _default_conn(conn)
    if summary:
        limit = 0

    # Summary query — always runs (cheap, reads precomputed stats)
    sum_cypher, sum_params = queries_lib.build_differential_expression_by_gene_summary(
        experiment_ids=experiment_ids, locus_tags=locus_tags,
        significant_only=significant_only, direction=direction,
        min_log2fc=min_log2fc, max_pvalue=max_pvalue)
    result = conn.execute_query(sum_cypher, **sum_params)
    # result is a dict: {total_matching, direction_breakdown, ...}

    # Detail query — skip when limit=0 (summary only)
    if limit == 0:
        results = []
    else:
        det_cypher, det_params = queries_lib.build_differential_expression_by_gene(
            experiment_ids=experiment_ids, locus_tags=locus_tags,
            significant_only=significant_only, direction=direction,
            min_log2fc=min_log2fc, max_pvalue=max_pvalue,
            verbose=verbose)
        all_rows = conn.execute_query(det_cypher, **det_params)
        results = all_rows[:limit] if limit else all_rows

    # api/ assembles the complete response dict — MCP just wraps it
    result["results"] = results
    result["returned"] = len(results)
    result["truncated"] = result["total_matching"] > len(results)
    return result
```

**Re-exported from package root:**

```python
# __init__.py
from multiomics_explorer.api.functions import (
    # Phase 1 — Orientation
    list_organisms,
    list_publications,
    list_experiments,
    # Phase 2 — Gene work
    resolve_gene,
    genes_by_function,
    gene_overview,
    search_ontology,
    genes_by_ontology,
    gene_ontology_terms,
    search_homolog_groups,
    genes_by_homolog_group,
    gene_homologs,
    # Phase 3 — Expression
    differential_expression_by_gene,
    differential_expression_by_ortholog,
    # Utils
    run_cypher,
    kg_schema,
    list_filter_values,
)
```

**Rules:**
- Always returns `dict` with summary fields + `results` list — no
  formatting. Summary fields are always present. `results` is a
  flat `list[dict]` in long form (one row per entity × dimension).
- `summary` = True → `results=[]` (sugar for `limit=0`). Default
  False in api/ (scripts usually want rows).
- `limit` caps the `results` list. Default is `None` (all rows).
  Summary fields always reflect the full result set regardless of
  limit — `total_matching` counts all matches, not just returned.
  Ignored when `summary=True`.
- `verbose` controls detail level in `results` rows — compact by
  default, adds heavy text fields when True
- Accepts optional `conn` parameter (always last) for connection reuse
- Parameters match MCP tool parameters (same names, same types)
- Validates parameters, raises `ValueError` for bad inputs
- Orchestrates multi-query workflows when needed (e.g.,
  `differential_expression_by_ortholog`: select ortholog group →
  find member genes → query expression per member)
- Docstrings document return dict keys — this is the contract

### 3. `mcp_server/` — MCP tool wrappers

**Responsibility:** Wrap `api/` functions for LLM consumption.
Validate via Pydantic models, apply default limits, provide
LLM-facing docstrings. The api/ layer assembles the complete
response dict — MCP just wraps it.

```python
# mcp_server/tools.py
from typing import Annotated, Literal
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

# --- Pydantic response models ---

class ExpressionRow(BaseModel):
    locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0120')")
    gene_name: str | None = Field(default=None, description="Gene name (e.g. 'katG')")
    product: str | None = Field(default=None, description="Gene product")
    organism_strain: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")
    experiment_id: str = Field(description="Experiment ID")
    experiment_name: str = Field(description="Experiment name")
    condition_type: str = Field(description="Treatment type (e.g. 'nitrogen_stress')")
    treatment: str = Field(description="Treatment description")
    timepoint: str | None = Field(default=None)
    timepoint_hours: float | None = Field(default=None)
    log2fc: float = Field(description="Log2 fold change")
    padj: float = Field(description="Adjusted p-value")
    direction: Literal["up", "down"] = Field(description="Expression direction")
    rank: int = Field(description="Rank by |log2FC| within experiment")
    significant: bool = Field(description="Passes significance threshold")

class DifferentialExpressionByGeneResponse(BaseModel):
    total_matching: int = Field(description="Total genes matching filters")
    direction_breakdown: dict[str, int] = Field(description="{'up': N, 'down': N}")
    returned: int = Field(description="Number of results returned")
    truncated: bool = Field(description="True if total_matching > returned")
    results: list[ExpressionRow] = Field(default_factory=list)

# --- Tool ---

@mcp.tool(
    tags={"expression", "genes"},
    annotations={"readOnlyHint": True},
)
async def differential_expression_by_gene(
    ctx: Context,
    experiment_ids: Annotated[
        list[str] | None,
        Field(description="Experiment IDs from list_experiments"),
    ] = None,
    locus_tags: Annotated[
        list[str] | None,
        Field(description="Gene locus_tags from resolve_gene / gene_overview"),
    ] = None,
    direction: Annotated[
        Literal["up", "down"] | None,
        Field(description="Filter by direction"),
    ] = None,
    ...,
    summary: Annotated[bool, Field(
        description="If true, return summary fields only (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include full annotation fields in results rows.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> DifferentialExpressionByGeneResponse:
    """Gene-centric differential expression. One row per gene × experiment × timepoint.

    Use differential_expression_by_ortholog for cross-organism comparison via homology.

    Returns summary fields (always) + top results by |log2FC|.
    Default limit=5 gives a quick overview with example rows.
    Set summary=True for counts only, or increase limit for more rows.
    """
    await ctx.info(f"differential_expression_by_gene limit={limit}")
    try:
        conn = _conn(ctx)
        data = api.differential_expression_by_gene(
            experiment_ids=experiment_ids, locus_tags=locus_tags,
            direction=direction, summary=summary, verbose=verbose,
            limit=limit, conn=conn)
        # api/ returns the complete dict — MCP just validates via Pydantic
        data["results"] = [ExpressionRow(**r) for r in data["results"]]
        return DifferentialExpressionByGeneResponse(**data)
    except ValueError as e:
        await ctx.warning(f"differential_expression_by_gene error: {e}")
        raise ToolError(str(e))
    except Exception as e:
        await ctx.error(f"differential_expression_by_gene unexpected error: {e}")
        raise ToolError(f"Error in differential_expression_by_gene: {e}")
```

**Pydantic models** serve double duty: FastMCP generates a JSON
schema from the return type and includes it in the tool definition,
so LLMs know the exact response shape before calling. Field
descriptions on each model attribute become part of the schema —
they document the response for LLMs without needing separate about
content. Validation catches contract drift between api/ and MCP at
call time rather than silently returning wrong shapes.

**Note:** FastMCP handles error conversion automatically —
`ValueError` from api/ becomes a tool error response. No manual
try/except needed for standard cases. Use `ToolError` for
tool-specific error messages. `ctx: Context` is injected by
FastMCP and hidden from the tool schema.

**MCP wrappers are thin.** The api/ layer assembles the complete
response dict (summary fields, results, returned, truncated,
not_found). The MCP wrapper just forwards parameters, applies a
default `limit`, and validates via `Response(**data)`. No field
computation in MCP — if the dict is wrong, fix it in api/.

**Rules:**
- Calls `api/` functions, never `queries_lib` directly
- Same parameters as api/ (minus `conn`, plus `ctx`)
- Same return shape as api/ — Pydantic model with summary fields +
  `results` list
- Pydantic response models give FastMCP a JSON schema for the tool
  definition, and validate the api/ dict at call time
- `limit` parameter caps `results` length (api/ default is None;
  MCP default is small, e.g. 5)
- Never raises raw exceptions — uses `ToolError` for tool-specific
  messages, lets FastMCP handle the rest
- Tool docstrings are LLM-facing (see Docstring conventions)
- Logs via `ctx.info/warning/error` (client-facing) and `logger`
  (server-side analytics) — see Logging section

---

## Response shape

All tools return a single dict with two parts:

```python
{
    # Summary fields — always present
    "total_matching": 823,
    "direction_breakdown": {"up": 412, "down": 411},
    ...
    # Results — flat list of dicts, long form
    "results": [
        {"locus_tag": "PMM0120", "gene_name": "katG", "log2fc": 3.2, ...},
        ...
    ]
}
```

- **`results`** is always a flat `list[dict]` in long form — one
  row per entity × dimension (e.g., gene × experiment × timepoint).
  No nested structures. Empty when `summary=True`, capped by
  `limit` otherwise.
- **Summary fields** are tool-specific (counts, breakdowns,
  distributions). Always present. Computed over the full result
  set, not just the returned rows.
- **`verbose`** controls how much detail each row in `results`
  carries. `verbose=False` (default) returns compact rows;
  `verbose=True` adds heavy text fields (descriptions, abstracts).
  Does not affect summary fields or row count.
- **`summary`** = True means `results=[]` (sugar for `limit=0`).
  Default False in both layers. MCP defaults to a small `limit`
  (e.g. 5) so the LLM gets summary fields + a few example rows
  in one call.
- **`limit`** caps `results` length. api/ defaults to `None` (all
  rows), MCP defaults to a small cap (e.g. 5). Ignored when
  `summary=True`.

This shape is the same at both the api/ and MCP layers (MCP uses
Pydantic models that mirror the dict structure). The api/ and MCP
tools share the same parameter names and return shape — the main
difference is the default `limit`.

### Precise definitions

**`total_matching`** — count of results matching all filters,
over the full result set (not capped by limit). Present on all
tools.

**`total_entries`** — total rows in the KG before filtering.
Present on tools with filters, alongside `total_matching`. Gives
context for filter selectivity ("3 of 15 organisms matched").
For tools without filters, omit — `total_matching` is the total.

**`returned`** — `len(results)` in this response. Always ≤
`total_matching`.

**`truncated`** — `True` when `total_matching > returned`. This
includes the case where `summary=True` (which sets `limit=0`, so
`returned=0`, and `truncated=True` whenever there are matching
results). `False` when all matching results are in `results`, or
when `total_matching=0`.

**`summary` parameter** — sugar for `limit=0`. If both `summary=True`
and `limit=N` are passed, `summary` wins (`limit` is ignored).
They are not orthogonal — `summary=True` always means empty results.

**`not_found`** — present on batch tools (tools accepting an ID
list parameter: `locus_tags`, `experiment_ids`, `group_ids`).
Lists the specific input IDs that had no match in the KG. Empty
list when all matched. Not present on search/filter tools
(`genes_by_function`, `search_ontology`, etc.) — those don't take
known IDs as input.

**"Long form" results** — one row per entity × dimension. No
nesting. If a gene appears in 3 experiments, that's 3 rows (not
1 row with a list of experiments). If a gene has 2 ontology terms,
that's 2 rows. The specific "entity × dimension" is defined per
tool in `tool_framework.md`.

**"Batch tool"** — any tool that accepts a list of IDs as input
(`locus_tags`, `experiment_ids`, `group_ids`). Batch tools support
`limit`, `summary`, summary fields, and `not_found`. Note: search
tools (`genes_by_function`, `search_ontology`) also support `limit`
and summary fields because they can return large result sets, but
they are not batch tools (no `not_found` — the input is a search
query, not known IDs).

**Zero-match behavior** — when `total_matching=0`:
- All summary fields are present (never omitted)
- Counts are 0, breakdowns are empty dicts/lists
- `results=[]`, `returned=0`, `truncated=False`
- `not_found` (batch tools) lists all input IDs

**Post-processing of aggregations** happens in api/, not
queries_lib or mcp_server. If a summary query returns raw
`apoc.coll.frequencies` output (`[{item, count}]`), the api/
function renames keys, sorts descending, and slices to top N.
The query builder returns raw Cypher results; api/ shapes them
into the response dict.

---

## Tool modes

### Summary fields

Always present in every response. Cheap, computed over the full
result set. Claude uses these for reasoning and to guide the next
tool call in a chain — without needing to inspect individual rows.

**Implementation:** Summary fields come from either precomputed
KG properties or lightweight aggregation queries (COUNT, collect).
They are returned alongside `results`, not as a separate mode.

Which summary fields a tool returns depends on its result set
size and what's useful for decision-making. All tools return at
least `total_matching` and `results`.

**Tools with rich summary fields** (large result sets — summary
fields guide whether/how to inspect rows):

| Tool | Summary fields |
|---|---|
| `differential_expression_by_gene` | total, direction breakdown, top categories, time points, median/max \|log2FC\| |
| `differential_expression_by_ortholog` | total clusters, direction breakdown, organism coverage, conservation pattern |
| `genes_by_function` | total, organism breakdown, category breakdown |
| `genes_by_ontology` | total, organism breakdown, genes per term |
| `gene_overview` | total, annotation type breakdown, expression availability counts |

**Tools with minimal summary fields** (small result sets —
rows are always manageable):

| Tool | Summary fields | Rationale |
|---|---|---|
| `list_organisms` | total_matching | Always returns all (~15 organisms), no filters |
| `resolve_gene` | total_matching | Typically 1–5 matches |
| `gene_homologs` | total | Groups per gene are small |

**Decide during implementation:**

| Tool | Notes |
|---|---|
| `search_ontology` | Can be large for broad terms — may need richer summaries |
| `gene_ontology_terms` | Usually small, but poorly annotated genomes may surprise |
| `search_homolog_groups` | Depends on consensus name ambiguity — profile against KG |
| `genes_by_homolog_group` | Groups are typically small, but large groups exist |

### Summary design guidelines

Summaries guide Claude's next decision. Every field should answer:
**what does Claude need to know to decide what to do next?**

**What to include:**

- **Counts** — total results, broken down by the most useful
  categorical dimension (direction for expression, organism for
  genes). Use the dimension that most affects what Claude does next.
- **Distributions for continuous values** — when the spread matters
  for decision-making, include median and range (min/max) over the
  full result set. Example: median |log2FC| and max |log2FC| tell
  Claude whether the response is mild or dramatic.
- **Top N with scores** — for high-cardinality categorical
  dimensions (functional categories, organisms), return top N
  values each with its score/count. Include distribution context
  for the scores (median/range over the full set) so Claude can
  tell if the top N are dominant or just slightly above the rest.
  Example: `top_categories: [{name: "photosynthesis", count: 45},
  {name: "transport", count: 32}, ...], category_count_median: 8,
  category_count_max: 45`.
- **Availability signals** — what data exists for the next step.
  "Expression data in 5 experiments" tells Claude whether to
  proceed with expression analysis.

**Design rules:**

- **Every ranked list needs an explicit sort key.** "Top 10" is
  meaningless without knowing top by what (|log2FC|, count,
  relevance score).
- **Include the score per row** in detail mode so Claude sees
  actual values, not just rank order.
- **Include distribution context** in summary mode — median/range
  over the *full* result set, not just the returned rows. This
  tells Claude whether the detail rows are outliers or
  representative. If top 100 all have |log2FC| > 3 but the
  median is 1.2, Claude knows it's seeing the extreme tail.
- **Categorical: counts. Continuous: median + range.** Don't
  compute means/medians for categories, don't just count
  continuous values.
- **No raw data in summaries** — no individual rows, gene lists,
  or sequences. Summaries are aggregations only. Exception:
  `not_found` lists the specific input IDs that didn't match —
  this is feedback on the request, not result data.

**Per-tool summary fields:**

| Tool | Counts | Distributions | Top N | Availability |
|---|---|---|---|---|
| `differential_expression_by_gene` | total, per-direction | median/max \|log2FC\|, median padj | top 10 categories (with count) | time points covered |
| `differential_expression_by_ortholog` | total clusters, per-direction | median/max \|log2FC\| | top organisms (with cluster count) | conservation pattern |
| `genes_by_function` | total, per-organism | median relevance score | top 10 categories (with count) | — |
| `genes_by_ontology` | total, per-organism | — | top 10 terms (with gene count) | — |

### Results list

The `results` list carries the actual rows. Controlled by `limit`
(caps row count) and `verbose` (controls per-row detail level).

**Every response with results includes:**
- `results` ordered by an explicit sort key (|log2FC|, relevance
  score, count — documented per tool)
- The score value in each row
- Summary fields including `total_matching` (full count, not just
  returned rows), `returned`, `truncated`

**Implementation:** The `limit` is pushed into the Cypher query
(server-side `ORDER BY ... LIMIT`) for efficiency over remote
connections. Claude can read `total_matching` from summary fields
to know how many rows exist, then adjust `limit` accordingly —
`limit=10` for a quick look or `limit=200` for deeper inspection.

**Batching:** For large result sets transferred over a remote
connection, the Neo4j driver handles streaming internally. If
profiling shows specific queries are slow in detail mode, options
include:
- Adding server-side LIMIT + ORDER BY in the Cypher query
- Pagination via cursor (skip/limit) if needed
- Splitting into multiple focused queries in the api/ layer

These are per-query optimizations, not framework-level decisions.

### About content

Self-describing tool documentation, served via MCP resources
(`docs://tools/{tool_name}`). This is the self-describing tool
capability (methodology principle 6).

**About content is auto-generated** from two sources:

1. **Pydantic models** (in `tools.py`) → params table, response
   format, expected-keys sections. These stay in sync with the
   code automatically.
2. **Human-authored input YAML** (`multiomics_explorer/inputs/tools/{name}.yaml`)
   → examples, chaining patterns, common mistakes. The parts that
   require domain knowledge.

The build script (`scripts/build_about_content.py`) merges both
into the final markdown at
`multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md`.

**Workflow:**

```bash
# Generate input YAML skeleton for a new tool
uv run python scripts/build_about_content.py --skeleton {name}

# Edit the YAML — add examples, chaining, mistakes
$EDITOR multiomics_explorer/inputs/tools/{name}.yaml

# Build the about markdown
uv run python scripts/build_about_content.py {name}
```

**Input YAML structure:**

```yaml
examples:
  - title: Short description
    call: tool_name(param="value")
    response: |                         # optional example response
      {"total_matching": 15, "results": [...]}

  - title: Multi-step chain
    steps: |                            # use steps for chains
      Step 1: first_tool(param="value")
              → extract locus_tags from results
      Step 2: tool_name(locus_tags=[...])

verbose_fields:                         # splits per-result table
  - abstract
  - description

chaining:
  - "previous_tool → tool_name → next_tool"

mistakes:
  - "Plain note renders as bullet"
  - wrong: "len(results)  # wrong"
    right: "response['total_matching']"
```

**What gets auto-generated vs human-authored:**

| Section | Source |
|---|---|
| Parameters table | Pydantic `Field(description=...)` on tool params |
| Response format | Pydantic response model fields |
| Expected keys | Pydantic model field names |
| Examples | Input YAML `examples` |
| Chaining patterns | Input YAML `chaining` |
| Common mistakes | Input YAML `mistakes` |

**Output serves all clients equally** — chat mode and agentic mode
both get the same self-documentation via MCP resources. Same
content also loaded as Claude Code skill references. This is the
baseline for tool competence (methodology layer 1).

**Tests verify consistency:**

| Test | What it checks |
|---|---|
| `test_about_content.py` | Generated markdown matches current Pydantic models |
| `test_about_examples.py` | Example calls execute against live KG |

---

## Skill architecture

### Research skills (shipped with package)

Live in `multiomics_explorer/skills/` and are installed into the
user's project by `init-claude`.

**Follows the [agentskills.io](https://agentskills.io/specification)
specification.** Each skill is a directory containing a `SKILL.md`
(required) plus optional `references/`, `assets/`, and `scripts/`
directories. Directory name must match the `name` field in
frontmatter.

### Skill design guidelines

**`SKILL.md`** — the core instructions. Loaded when the skill
activates. Keep under 5000 tokens / 500 lines. Contains the
steps, rules, or protocol that Claude follows. This is what Claude
reads first.

**`references/`** — knowledge that informs Claude's thinking.
Loaded on demand when Claude needs deeper context during execution.
Style guides, checklists, valid values, how-to guides. Claude
reads these to do the job *better*, but the skill works without
them for simple cases.

**`assets/`** — things Claude produces from or fills in. Templates,
scaffolds, output formats. Claude copies or adapts these rather
than generating from scratch. Ensures consistent output structure.

**`scripts/`** — executable code Claude can run. Extraction
scripts, validation scripts, formatting scripts. Claude runs these
rather than writing equivalent code from scratch.

**The design rule:** `SKILL.md` tells Claude *what to do*.
`references/` tells Claude *how to do it well*. `assets/` gives
Claude *starting material*. `scripts/` gives Claude *ready-made
tools*.

### Design per skill layer

**Layer 1: Tool Wrapper** (always active)

One skill (`multiomics-kg-guide`) that's always loaded. The `SKILL.md`
contains the essential rules Claude must always follow (mode
selection, truncation handling, interface selection). Brief — this
is always in context, so token cost matters.

Detailed guidance lives in `references/` and is loaded on demand:
chaining patterns for specific tool combinations, the full
summary-vs-detail decision tree, when and how to switch to
package import. Claude pulls these in when facing a non-obvious
tool usage decision.

No `assets/` — Tool Wrapper skills produce knowledge, not
artifacts.

```
multiomics-kg-guide/
├── SKILL.md                    # Essential rules (~500 tokens, always loaded)
│                               #   - mode selection
│                               #   - truncation handling
│                               #   - key rules (use total, not len)
└── references/                 # Loaded on demand
    ├── tool-chaining.md        # Common chains: resolve → overview → expression
    ├── summary-vs-detail.md    # Decision tree for mode selection
    ├── mcp-vs-import.md        # Interface selection guide
    └── tools/                  # Per-tool about content (served via MCP resources)
        ├── differential-expression-by-gene.md
        ├── differential-expression-by-ortholog.md
        ├── genes-by-function.md
        ├── resolve-gene.md
        ├── gene-overview.md
        ├── search-ontology.md
        ├── genes-by-ontology.md
        ├── gene-ontology-terms.md
        ├── search-homolog-groups.md
        ├── genes-by-homolog-group.md
        ├── gene-homologs.md
        ├── list-organisms.md
        ├── list-publications.md
        ├── list-experiments.md
        └── ...
```

**Layer 2: Pipeline** (activated per analysis)

Each pipeline skill's `SKILL.md` contains the gated step sequence.
Steps are numbered, gates are explicit ("do not proceed until...").
Brief enough to scan quickly — Claude needs the full picture to
plan, not encyclopedic detail.

`references/` contains domain knowledge for specific steps:
how to run enrichment correctly, what statistical test to use,
biological context for interpretation. Loaded only when Claude
reaches that step.

`assets/` contains templates for outputs: the `analyses/`
directory structure, script templates (extraction, enrichment,
plotting), README template. Claude adapts these rather than
writing from scratch, ensuring consistent structure.

`scripts/` (where applicable) contains ready-made extraction or
analysis scripts that Claude can run directly or adapt.

```
characterize-experiment/
├── SKILL.md                    # Gated workflow (loaded on activation)
│                               #   1. Browse → 2. Summarize → 3. Gate
│                               #   4. Extract → 5. Gate → 6. Analyze
│                               #   7. Gate → 8. Interpret
├── references/
│   ├── enrichment-guide.md     # How to run GO enrichment correctly
│   └── volcano-guide.md        # Volcano plot conventions
└── assets/
    ├── analysis-template/      # analyses/{name}/ directory scaffold
    │   ├── data/.gitkeep
    │   ├── scripts/.gitkeep
    │   ├── results/.gitkeep
    │   ├── README.md           # Summary, key findings, file index
    │   └── methods.md          # Publication-ready methods (research question,
    │                           #   data scope, gene selection, stats,
    │                           #   results summary, limitations)
    └── extract-template.py     # Script template for data extraction
```

**Layer 3: Inversion** (activated for ambiguous questions)

The `SKILL.md` contains the questioning protocol: what to ask,
in what order, when to stop gathering context and start working.
Includes gate conditions ("do not proceed to analysis until
organism, condition, and comparison are established").

`references/` contains the question tree for different ambiguity
types (experiment selection, gene identification, comparison
design). Loaded when Claude needs to navigate a specific type
of ambiguity.

No `assets/` — Inversion skills produce decisions, not artifacts.

```
clarify-research-question/
├── SKILL.md                    # Questioning protocol
│                               #   - What to ask first
│                               #   - Gate: have organism + condition?
│                               #   - How to confirm before proceeding
└── references/
    ├── experiment-selection.md  # How to narrow experiment choice
    └── comparison-design.md    # How to clarify comparison questions
```

### Summary: what goes where per layer

| | `SKILL.md` | `references/` | `assets/` | `scripts/` |
|---|---|---|---|---|
| **Layer 1 (Tool Wrapper)** | Essential rules (brief, always in context) | Detailed guides (on demand) | — | — |
| **Layer 2 (Pipeline)** | Gated step sequence | Domain knowledge per step | Output templates, script templates | Ready-made scripts |
| **Layer 3 (Inversion)** | Questioning protocol with gates | Question trees per ambiguity type | — | — |

**Progressive disclosure** (per agentskills.io spec):
1. **Metadata** (~100 tokens) — `name` and `description` loaded
   at startup for all skills. Description is keyword-rich for
   discovery ("experiment", "enrichment", "volcano plot").
2. **Instructions** (<5000 tokens) — full `SKILL.md` body loaded
   when the skill activates.
3. **Resources** (on demand) — `references/` and `assets/` loaded
   only when needed during execution.

**Skill format example** (Pipeline pattern):

```markdown
# skills/characterize-experiment/SKILL.md
---
name: characterize-experiment
description: Full characterization of a DE experiment — enrichment,
  volcano plot, biological interpretation. Use when asked about an
  experiment's transcriptional response, what happens under a
  condition, or to characterize differential expression results.
metadata:
  pattern: pipeline
  layer: 2
---

# Characterize experiment

## Steps

1. Browse: `list_experiments` to find the experiment
2. Summarize: check summary fields from `differential_expression_by_gene(experiment_ids=[...])`
3. **Gate:** Confirm correct experiment with user if ambiguous
4. Extract: write script importing `multiomics_explorer.differential_expression_by_gene`
   → `data/de_genes.csv`
5. **Gate:** Verify row count matches summary total
6. Analyze: enrichment script + volcano plot
   (see [enrichment guide](references/enrichment-guide.md))
7. **Gate:** Verify outputs exist and are non-empty
8. Document: fill methods.md from decisions at each gate
   (see [methods template](assets/analysis-template/methods.md))

## Output structure

Use the [analysis template](assets/analysis-template/) for directory
layout: data/, scripts/, results/, README.md, methods.md
```

**Skill format example** (Tool Wrapper pattern):

```markdown
# skills/multiomics-kg-guide/SKILL.md
---
name: multiomics-kg-guide
description: How to use multiomics KG tools effectively. Always
  active when working with the multiomics knowledge graph. Covers
  tool selection, response reading, mode selection, chaining.
metadata:
  pattern: tool-wrapper
  layer: 1
---

# Tool competence

## Response shape

Every tool returns summary fields + results list.
- **Summary fields**: counts, breakdowns — always present, computed over full data
- **Results**: flat list of dicts, capped by `limit`
- **About content**: available as MCP resources (`docs://tools/{name}`)

## Key rules

- If `truncated: true`, use `total_matching`, not `len(results)`
- Read summary fields first, then adjust `limit` if you need more rows
- For bulk data, use package import in a script — not MCP with high limit
- Use summary fields for reasoning, inspect results for specifics

## References (loaded on demand)

- [Tool chaining patterns](references/tool-chaining.md)
- [Summary vs detail guide](references/summary-vs-detail.md)
- [MCP vs package import](references/mcp-vs-import.md)
- Per-tool guides: [references/tools/](references/tools/) — also
  also served as MCP resources (`docs://tools/{name}`)
```

### Dev skills (this repo only)

Live in `.claude/skills/` in the repo. Not shipped with the package.

```
.claude/skills/
├── layer-rules/                    # Dev: Tool Wrapper pattern
│   ├── SKILL.md
│   └── references/
│       └── layer-boundaries.md
├── add-tool/                       # Dev: Pipeline pattern
│   ├── SKILL.md
│   └── references/
│       └── checklist.md
├── modify-tool/                    # Dev: Pipeline pattern
│   └── SKILL.md
├── testing/                        # Dev: Pipeline + Tool Wrapper
│   ├── SKILL.md                   #   What to test where, how to run
│   └── references/
│       ├── test-checklist.md      #   Per-layer test requirements
│       └── regression-guide.md    #   Fixtures, regeneration, diversity
├── code-review/                    # Dev: Reviewer pattern
│   ├── SKILL.md
│   └── references/
│       └── review-checklist.md
└── research/                       # Copied from multiomics_explorer/skills/
    ├── multiomics-kg-guide/            #   (same structure as shipped skills)
    ├── characterize-experiment/
    ├── ...
    └── clarify-research-question/
```

### Skills in the dev repo

The source of truth for research skills is
`multiomics_explorer/skills/`. Claude Code in this repo also needs
these skills — for testing tools, running phase 2 stress tests, and
ensuring tools are built to match their skill descriptions.

**Approach:** A copy script syncs research skills from the source
tree to `.claude/skills/research/`. No symlinks (Windows
compatibility). Run after editing research skills.

```bash
# scripts/sync_skills.sh
cp -r multiomics_explorer/skills/* .claude/skills/research/
```

`.claude/skills/research/` is gitignored — it's a build artifact,
not a source file. The `add-tool` dev skill includes a reminder to
re-sync after editing research skills.

This means Claude in the dev repo sees both:
- Dev skills from `.claude/skills/dev/` (committed)
- Research skills from `.claude/skills/research/` (copied, gitignored)

**Layer rules skill** (Tool Wrapper, always active):

```markdown
# .claude/skills/layer-rules/SKILL.md
---
name: layer-rules
description: Architecture layer conventions for multiomics_explorer.
  Apply when writing or reviewing code in kg/, api/, or mcp_server/.
metadata:
  pattern: tool-wrapper
---

# Layer rules

See [layer boundaries](references/layer-boundaries.md) for full
details.

## Quick reference

- **kg/queries_lib.py** — returns tuple[str, dict]. No execution,
  no formatting. Summary builders generate aggregation Cypher.
- **api/functions.py** — calls builders + execute. Returns dict
  with summary fields + results list. No limits, no formatting.
  Raises ValueError.
- **mcp_server/tools.py** — calls api/ only. Same params/returns
  (Pydantic models). Adds default limit. Never raises. Logs via
  ctx (client) + logger (server).
```

**Add-tool skill** (Pipeline):

```markdown
# .claude/skills/add-tool/SKILL.md
---
name: add-tool
description: Complete lifecycle for adding a new MCP tool. Use when
  creating a new tool from scratch. Covers query builder, API
  function, MCP wrapper, tests, skills, and code review.
metadata:
  pattern: pipeline
---

# Add a new tool

See [checklist](references/checklist.md) for detailed requirements
per step.

## Steps

1. Query builder → `queries_lib.py`
   - `build_{action}()` → tuple[str, dict]
   - Add summary query variant if applicable
   - **Gate:** unit test passes
2. API function → `api/functions.py`
   - Calls builder + execute_query
   - Document return dict keys in docstring
   - **Gate:** unit test (mocked) passes
3. Wire → `__init__.py` re-exports
4. MCP wrapper → `mcp_server/tools.py`
   - Pydantic response model + LLM-facing docstring
   - Same params/returns as api/ (plus limit default)
   - **Gate:** unit test (mocked) passes
5. Integration test against live KG
   - **Gate:** passes, return keys match contract
6. Regression cases → `cases.yaml` + golden files
7. Skill updates
   - Update multiomics-kg-guide skill if tool changes the landscape
   - Add/update pipeline skills that use the tool
   - Build about content (input YAML + `build_about_content.py`)
   - Sync research skills: `scripts/sync_skills.sh`
   - **Gate:** skill content matches tool behavior
8. Code review against layer-rules skill
```

### `init-claude` command

```bash
$ multiomics-explorer init-claude
```

Copies research skills from `multiomics_explorer/skills/` into
the user's `.claude/skills/`. Creates or updates `.mcp.json` with
MCP server config. Appends KG guidance to `CLAUDE.md`.

Idempotent — safe to run multiple times. Updates skills to the
version matching the installed package.

**What it creates:**

```
.claude/
├── skills/                             # agentskills.io directories
│   ├── multiomics-kg-guide/            #   Layer 1: Tool Wrapper
│   │   ├── SKILL.md
│   │   └── references/
│   │       ├── tool-chaining.md
│   │       ├── summary-vs-detail.md
│   │       ├── mcp-vs-import.md
│   │       └── tools/
│   │           ├── differential-expression-by-gene.md
│   │           ├── differential-expression-by-ortholog.md
│   │           └── ...
│   ├── characterize-experiment/        #   Layer 2: Pipeline
│   │   ├── SKILL.md
│   │   ├── references/
│   │   └── assets/
│   ├── compare-conditions/
│   │   └── SKILL.md
│   ├── gene-survey/
│   │   └── SKILL.md
│   ├── ortholog-conservation/
│   │   └── SKILL.md
│   ├── timecourse-analysis/
│   │   └── SKILL.md
│   ├── export-de-genes/
│   │   └── SKILL.md
│   └── clarify-research-question/      #   Layer 3: Inversion
│       ├── SKILL.md
│       └── references/
├── CLAUDE.md (appended)
└── (existing settings preserved)

.mcp.json (created or updated)
```

---

## Tool design guidelines

The authoritative tool surface (tool names, phases, output schemas,
homology framework) is defined in
[tool_framework.md](methodology/tool_framework.md). This section
covers implementation guidelines that apply across all tools.

### General parameter guidelines

- **ID parameters are always lists** — `locus_tags`, `experiment_ids`,
  `group_ids`, never singular `locus_tag` or `group_id`. Callers
  never need to check whether to pass a string or a list.
  The only exception is `identifier` in `resolve_gene` (ambiguous
  input for resolution, not an ID lookup).
- **Any tool that accepts an ID list is a batch tool.** Batch
  input can be arbitrarily large (e.g., 200 locus_tags from a
  previous step). Therefore every tool that accepts an ID list
  supports `limit`, `summary`, and returns summary fields — same
  uniform response shape. Don't assume "this tool's results are
  always small" — they're small per-ID, but batch input changes
  that.
- **Filters are singular** — `organism`, `direction`, `source`.
  These narrow results, not specify targets.
- **Booleans for mode switches** — `summary`, `verbose`.
  Not strings, not enums.

### When to create a new tool vs extend an existing one

**Create a new tool when:**
- The question it answers is fundamentally different
- It queries a different subgraph or node type
- The return schema (dict keys) is different
- An LLM would struggle to discover the functionality as a parameter

**Extend an existing tool when:**
- The change adds a filter or mode to the same question
- The return schema stays the same
- An LLM would naturally express it as a parameter
  ("only the upregulated ones" → `direction="up"`)

### Deciding modes for a tool

| Result size | Modes | Example tools |
|---|---|---|
| Always small (<20 rows) | minimal summary fields | `list_organisms`, `resolve_gene`, `list_publications` |
| Frequently large (100+ rows) | summary + detail + about | `differential_expression_by_gene`, `genes_by_function`, `genes_by_ontology` |

Rich summary fields aren't needed when results are always small
enough to return in full.

### Default limits (MCP)

Small defaults so the first call returns summary fields + a few
example rows. The LLM increases `limit` or sets `summary=True`
based on what it sees.

| Tool | Default limit | Rationale |
|---|---|---|
| `differential_expression_by_gene` | 5 | Quick overview with top genes by \|log2FC\| |
| `differential_expression_by_ortholog` | 5 | Quick overview with top clusters |
| `genes_by_function` | 5 | See top matches + summary counts |
| `genes_by_ontology` | 5 | See top genes + organism breakdown |
| `run_cypher` | 25 | Safety net for arbitrary queries |

api/ defaults to `limit=None` (all rows) — scripts control their
own limits.

---

## Parameter and return conventions

### Standard parameter names

Use these names consistently across all layers.

**Gene identification:**

| Parameter | Type | Meaning |
|---|---|---|
| `locus_tags` | `list[str]` | Gene locus tags — always a list, even for one gene |
| `identifier` | `str` | Ambiguous input (for resolution only — accepts locus tag, gene name, or partial match) |

ID parameters are always lists — no singular `locus_tag` param.
This keeps the interface consistent: callers never need to check
whether to pass a string or a list. `identifier` is the exception
(resolution input, not an ID lookup).

**Organism filtering:**

| Parameter | Type | Meaning |
|---|---|---|
| `organism` | `str \| None` | Organism filter (CONTAINS match) |

**Text search:**

| Parameter | Type | Meaning |
|---|---|---|
| `search_text` | `str` | Free-text search query (Lucene syntax for full-text, substring match for simple filters) |

Always `search_text`, never `query` (avoids confusion with Cypher
queries) or `text` (too generic).

**Expression filters:**

| Parameter | Type | Meaning |
|---|---|---|
| `experiment_ids` | `list[str] \| None` | Experiment IDs from `list_experiments` |
| `direction` | `str \| None` | `"up"` or `"down"` |
| `min_log2fc` | `float \| None` | Minimum \|log2FC\| |
| `max_pvalue` | `float \| None` | Maximum adjusted p-value |
| `significant_only` | `bool \| None` | Filter to significant results |

**Homology parameters:**

| Parameter | Type | Meaning |
|---|---|---|
| `group_ids` | `list[str]` | Ortholog group IDs — always a list |
| `source` | `str \| None` | OG source filter (e.g., "Cyanorak", "eggNOG") |
| `taxonomic_level` | `str \| None` | Taxonomic level filter |

**Structural parameters:**

| Parameter | Type | Meaning | Layer |
|---|---|---|---|
| `summary` | `bool` | If True, return summary fields only (`results=[]`). Sugar for `limit=0`. Default False in both layers. | api/ + MCP |
| `verbose` | `bool` | Controls detail level in `results` rows. False (default) = compact rows. True = adds heavy text fields (abstract, description, full annotations). Does not affect summary fields or row count. | api/ + MCP |
| `limit` | `int \| None` | Max rows in `results` for this call. `total_matching` always reflects the full count. Default None = all rows in api/, small cap (e.g. 5) in MCP. Ignored when `summary=True`. | api/ + MCP |
| `conn` | `GraphConnection \| None` | Connection reuse. Keyword-only, always last. | api/ only |
| `ctx` | `Context` | MCP context (always first, hidden from schema by FastMCP) | MCP only |

### Standard return field names

Consistent across tools so scripts can process results without
mapping field names.

**Gene fields:** `locus_tag`, `gene_name`, `product`,
`organism_name`, `organism_strain`, `category`

**Expression fields (gene-centric):** `locus_tag`, `gene_name`,
`product`, `organism_strain`, `experiment_id`, `experiment_name`,
`condition_type`, `treatment`, `timepoint`, `timepoint_hours`,
`log2fc`, `padj`, `direction`, `rank`, `significant`

**Expression fields (ortholog-centric):** `cluster_id`,
`consensus_product`, `consensus_gene_name`, `experiment_id`,
`experiment_name`, `condition_type`, `treatment`, `organism`,
`timepoint`, `timepoint_hours`, `log2fc`, `padj`, `direction`,
`rank`, `significant`

**Homology fields:** `locus_tag`, `group_id`, `consensus_gene_name`,
`consensus_product`, `taxonomic_level`, `source`

**Truncation metadata (always present):** `total_matching`,
`returned`, `truncated`

**Batch metadata (on functions accepting ID lists):** `not_found`
(`list[str]`, empty when all IDs matched)

### Return types per layer

| Layer | Returns |
|---|---|
| `queries_lib.py` | `tuple[str, dict]` (Cypher + params) |
| `api/functions.py` | `dict` with summary fields + `results: list[dict]` |
| `mcp_server/tools.py` | Pydantic model (same shape — FastMCP serializes to MCP response) |

### Naming conventions

| Layer | Function pattern | Example |
|---|---|---|
| `queries_lib.py` | `build_{action}` | `build_differential_expression_by_gene` |
| `api/functions.py` | `{action}` | `differential_expression_by_gene` |
| `mcp_server/tools.py` | `{action}` (same) | `differential_expression_by_gene` |

Same name across api/ and MCP. Query builder has `build_` prefix.

---

## Docstring conventions

### `queries_lib.py` — for contributors

Minimal. What the query does, what parameters control, what Cypher
pattern. List the return keys (from the RETURN clause) — just the
names, not full descriptions. The api/ docstring has the full
contract. For `_summary` builders, note which properties are
precomputed vs aggregated.

### `api/functions.py` — for script authors

The public contract. Must document:
- What the function does (one line)
- Parameters with types and semantics
- Return type and dict keys (the schema)
- Summary mode return keys (if applicable)
- Exceptions raised
- Example usage

### `mcp_server/tools.py` — for LLMs

**Structure:**
1. First line = what the tool does
2. When to use this tool (vs related tools)
3. Response shape (summary fields + results)
4. Truncation handling (use total_matching, not len(results))
5. Package import cross-reference
6. Args with valid values and discovery references

**Cross-layer consistency tests:**

`EXPECTED_KEYS` dict is the single source of truth for return
field names. Tests verify consistency in both directions:

| Test | Type | What it checks |
|---|---|---|
| Return keys vs KG | Integration | Run api/ call against live KG, assert `result.keys() == EXPECTED_KEYS[func]` |
| api/ params vs MCP params | Unit | MCP tool params (minus `ctx`) match api/ params (minus `conn`). Same names, same types. |
| About content keys vs `EXPECTED_KEYS` | Unit | Parse about reference files, assert keys match |
| MCP docstring structure | Unit | Has Args, truncation warning, package cross-ref for tools with limits |

---

## Error handling

### Error flow

```
Neo4j error (timeout, connection lost, bad Cypher)
    ↓
connection.py — raises neo4j.exceptions.*
    ↓
api/functions.py — validates params (ValueError), propagates rest
    ↓
FastMCP — converts unhandled exceptions to tool error responses
    or
mcp_server/tools.py — raises ToolError for tool-specific messages
    or
script (user code) — catches or lets propagate
```

**Key rules:**
- `api/` raises `ValueError` for bad inputs, propagates Neo4j errors
- FastMCP automatically converts unhandled exceptions to error
  responses — no manual try/except needed for standard cases
- Use `ToolError("message")` in MCP wrappers when you need a
  specific user-facing error message
- Empty results are not errors anywhere in the stack
- Scripts get raw exceptions and handle them however they want

### Partial results in batch functions

Functions that accept a list of IDs (e.g., `gene_overview(locus_tags=[...])`,
`gene_ontology_terms(locus_tags=[...])`) return partial results
when some IDs are not found. Never fail, never silently skip.

The response includes a `not_found` field listing missing IDs:

```python
{
    "total_matching": 3,
    "not_found": ["PMM9999", "FAKE001"],
    "results": [...]   # results for the 3 found IDs
}
```

**Rules:**
- All IDs not found → `results=[]`, `not_found=[all inputs]`.
  Not an error.
- Some IDs not found → partial results + `not_found` list.
  The LLM sees what matched and what didn't, and can decide
  whether to investigate ("typo? wrong organism?") or proceed.
- `not_found` is always present in batch responses. Empty list
  when all IDs matched.
- Single-ID functions (`resolve_gene(identifier=...)`) return
  empty results, not a `not_found` field — there's only one ID,
  so empty results is unambiguous.

---

## Logging

Two logging channels serve different audiences:

### Client-facing: FastMCP context logging

```python
await ctx.info(f"resolve_gene identifier={identifier}")
await ctx.info(f"Returning {response.returned} of {response.total_matching}")
await ctx.warning(f"resolve_gene error: {e}")
await ctx.error(f"resolve_gene unexpected error: {e}")
```

FastMCP sends these as MCP log notifications — the client (Claude)
sees them as progress signals. Use for:
- Tool invocation with key params (helps Claude track what happened)
- Result summary (returned N of M)
- Warnings and errors

**Rules:**
- `ctx.info` at entry (params) and exit (counts)
- `ctx.warning` for handled errors (ValueError)
- `ctx.error` for unexpected exceptions
- Keep messages short — they transit the MCP protocol

### Server-side: usage logging

Captures structured data for analytics — what was called, with
what params, how many results, how long it took.

**Fields per tool call:**

| Field | Purpose |
|---|---|
| `tool` | Tool name |
| `params` | Parameters (excluding ctx) |
| `total_matching` | Total results matching filters |
| `returned` | Results in this response |
| `truncated` | Whether results were capped by limit |
| `duration_ms` | Wall-clock time |
| `error` | Error message if failed |
| `skill_context` | Which skill triggered this call (if available) |

**Requirements:**
- Must not fire during unit/regression tests (inflates analytics)
- Should capture skill context to distinguish pipeline steps from
  ad-hoc calls
- Storage mechanism (log file, DB, structured log service) is a
  deployment decision — not scoped yet

---

## Testing strategy

### Test categories

```
tests/
├── unit/                               # No Neo4j. Fast. Run always.
│   ├── test_query_builders.py          #   Cypher generation + params
│   ├── test_api_functions.py           #   Business logic (mocked DB)
│   ├── test_tool_wrappers.py           #   Mode formatting (mocked api/)
│   ├── test_tool_correctness.py        #   Tool output assertions (mocked)
│   ├── test_docstring_structure.py     #   Docstring lint
│   └── test_about_content.py           #   About content lint
├── integration/                        # Requires Neo4j. Run with -m kg.
│   ├── test_api.py                     #   API functions against live KG
│   ├── test_api_contract.py            #   Return key assertions
│   ├── test_summary_mode.py           #   Summary vs detail consistency
│   └── test_tool_correctness_kg.py     #   Semantic correctness
├── regression/                         # Requires Neo4j. Snapshot-based.
│   └── test_regression.py              #   Golden-file comparison
└── evals/                              # Shared test cases
    └── cases.yaml                      #   Test case definitions
```

### New test types

**Summary field consistency** (`test_summary_consistency.py`):
Verify that `total_matching` in summary fields matches the actual
row count when `limit=None`. This catches drift between precomputed
stats and actual data.

**About content** (`test_about_content.py`): Every tool has about
content. Content matches current Pydantic models.
Content mentions chaining patterns. Content mentions package import.

### Coverage per layer

Same as current architecture — every tool/function needs unit tests
at each layer, integration tests against live KG, and regression
cases. See the dev skill `add-tool.md` for the complete checklist.

---

## KG schema coupling

This repo reads from a Neo4j graph built by the separate
`multiomics_biocypher_kg` repo. The two repos are coupled by:

- **Graph schema** — node labels, relationship types, property names
  (used in `queries_lib.py` Cypher)
- **Precomputed statistics** — summary properties on nodes that
  summary-mode queries read (handshake between KG build pipeline
  and query builders)
- **Constants** — valid enum values for OG sources, taxonomic levels,
  etc. (in `constants.py`)

### Precomputed statistics handshake

Each tool's summary fields may depend on specific properties existing in
the KG. This is documented per query builder:

```python
# queries_lib.py
def build_differential_expression_by_gene_summary(*, ...):
    """Build Cypher for gene-centric expression summary statistics.

    Reads precomputed properties:
      Experiment.de_gene_count (int)
      Experiment.direction_breakdown (str, JSON)
      Experiment.top_categories (str, JSON)
    These are populated by the KG build pipeline.
    If not available, falls back to COUNT aggregation query.
    """
```

```python
# queries_lib.py
def build_differential_expression_by_ortholog_summary(*, ...):
    """Build Cypher for ortholog-centric expression summary statistics.

    Reads precomputed properties:
      OrthologGroup.expression_experiment_count (int)
      OrthologGroup.expression_organism_count (int)
      OrthologGroup.conservation_pattern (str, TBD)
    These are populated by the KG build pipeline.
    """
```

When the KG build pipeline adds or changes precomputed properties,
the corresponding query builder must be updated.

### Schema change coordination

| KG change | Explorer impact |
|---|---|
| New node type | New query builder + api + MCP tool + skill |
| Renamed property | Update Cypher + return key conventions |
| New precomputed property | Update summary query in builder |
| Data change (same schema) | Regenerate regression fixtures |

---

## Deployment topology

```
Researcher's machine              Remote
├── VS Code + Claude Code         ├── Neo4j Aura (KG)
├── multiomics-explorer (pip) ───►│   - read-only user
├── Research skills (.claude/)    │   - precomputed stats
└── Claude ──── MCP (HTTP) ──────►├── MCP server
                                  │   - tools.py
                                  │   - usage log
                                  └───────────────────
```

**Two data paths:**
- MCP: Claude → remote MCP server → Aura → response through context
- Package import: local script → Aura → local file (bypasses context)

**Authentication:** Single read-only Neo4j user shared by all
researchers. Write operations blocked at database level.

**MCP transport:** Remote MCP server uses SSE or streamable HTTP.
Transport choice and hosting are deployment decisions (not yet
scoped).

---

## Dependencies

### FastMCP

The MCP server uses `fastmcp>=3.0` (not the bundled `FastMCP` in
the `mcp` package). FastMCP 3.x provides features we rely on:

| Feature | How we use it |
|---|---|
| `Annotated[type, Field(description="...")]` | Parameter descriptions in tool schema |
| `Literal["up", "down"]` | Enum validation in schema |
| `Field(ge=1, le=100)` | Constraint validation on limits |
| `ToolError` | Clean error responses without try/except boilerplate |
| `annotations={"readOnlyHint": True}` | All tools are read-only |
| `meta={}` | Custom metadata (layer, has_summary, etc.) |
| `structured_output=True` | Structured JSON alongside text responses |
| `Context` injection | Connection access, hidden from tool schema |

Import: `from fastmcp import FastMCP, Context`

---

## Configuration

### `.env` (gitignored)

```
NEO4J_URI=bolt://localhost:7687       # local dev
NEO4J_USER=                           # empty for local
NEO4J_PASSWORD=                       # empty for local
```

For Aura:
```
NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
NEO4J_USER=reader
NEO4J_PASSWORD=<read-only-password>
```

### Entry points

```toml
[project.scripts]
multiomics-explorer = "multiomics_explorer.cli.main:app"
multiomics-kg-mcp = "multiomics_explorer.mcp_server.server:main"
```

Phase 3 adds: `multiomics-explorer init-claude` subcommand.

### MCP server instructions

The `instructions` parameter in FastMCP carries layer 1 content
for chat-mode clients:
- Tool response format (summary fields + results, verbose, limit)
- Truncation rules
- Package import cross-reference for full data
- Summary mode is default — use detail when you need row-level data

This is the chat-mode equivalent of the tool-wrapper skills.
Same content, different delivery surface.
