# Target architecture

This document describes the target code architecture for the
multiomics_explorer package. See `architecture.md` for the current
state and `transition_plan.md` for how to get from here to there.

For the methodology behind these decisions (why dual interface, why
tier-1/tier-2, why list[dict]), see `methodology/llm_omics_analysis.md`.

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
├── api/                        # Public Python API (NEW)
│   ├── __init__.py             #   Re-exports for `from multiomics_explorer import ...`
│   └── functions.py            #   High-level functions → list[dict]
├── mcp_server/                 # MCP server for LLM access
│   ├── server.py               #   FastMCP entry point with Neo4j lifespan
│   └── tools.py                #   MCP tool wrappers (tier-1/tier-2 formatting)
├── cli/                        # Typer CLI
│   └── main.py
└── config/                     # Settings
    └── settings.py             #   Pydantic Settings from .env
```

### Modules to remove

The current repo has several inactive skeleton modules not shown in
the target structure above. See `transition_plan.md` Step 1 for the
removal plan and dependency cleanup.

---

## Layer diagram

```
┌──────────────────────────────────────────────────────┐
│                    Consumers                          │
│                                                      │
│   Claude Code      Claude Desktop      Python        │
│   (agentic)        (chat)              scripts       │
└───────┬──────────────┬─────────────────┬─────────────┘
        │              │                 │
        │   MCP        │   MCP           │  import
        │              │                 │
┌───────▼──────────────▼──┐    ┌────────▼──────────────┐
│   mcp_server/           │    │   api/                 │
│                         │    │                        │
│   tools.py              │    │   functions.py         │
│   - tier-1 summary      │    │   - returns list[dict] │
│   - tier-2 detail       │    │   - no limits          │
│   - truncation metadata │    │   - no formatting      │
│   - limit parameter     │    │                        │
└───────────┬─────────────┘    └────────┬──────────────┘
            │                           │
            └─────────┬─────────────────┘
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

**Key pattern:** Functions in `queries_lib.py` return
`tuple[str, dict]` — a Cypher query string and its parameters. They
do NOT execute the query or touch the database. This keeps them
testable without Neo4j.

```python
# queries_lib.py
def build_query_expression(
    *, experiment_id: str | None = None,
    gene_ids: list[str] | None = None,
    significant_only: bool | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
) -> tuple[str, dict]:
    """Build Cypher for expression query. Returns (cypher, params)."""
    ...
```

`connection.py` provides `GraphConnection.execute_query()` which runs
any `(cypher, params)` tuple and returns `list[dict]`.

**Rules:**
- No formatting, no limits, no tier logic
- No MCP or API imports — this layer has no knowledge of consumers
- Functions are keyword-only (`*`) for clarity
- Query builders are unit-testable (test the generated Cypher, not the
  results)

### 2. `api/` — public Python API

**Responsibility:** High-level functions that combine query building +
execution. This is what external scripts import.

```python
# api/functions.py
def query_expression(
    experiment_id: str | None = None,
    gene_ids: list[str] | None = None,
    significant_only: bool | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """Query expression data. Returns all matching results."""
    if conn is None:
        conn = GraphConnection()
    cypher, params = queries_lib.build_query_expression(
        experiment_id=experiment_id, gene_ids=gene_ids, ...)
    return conn.execute_query(cypher, **params)
```

**Re-exported from package root:**

```python
# __init__.py
from multiomics_explorer.api.functions import (
    query_expression,
    list_experiments,
    list_publications,
    search_genes,
    ...
)
```

So users write:
```python
from multiomics_explorer import query_expression
results = query_expression(experiment_id="...")
```

**Rules:**
- Returns `list[dict]` — no formatting, no limits, no tiers
- Accepts an optional `conn` parameter (for connection reuse in
  scripts that make multiple calls). Creates one if not provided.
- Parameters match MCP tool parameters (same names, same types)
- Docstrings document the dict keys returned

### 3. `mcp_server/` — MCP tool wrappers

**Responsibility:** Wrap `api/` functions for LLM consumption. Add
tier-1 summaries, tier-2 detail, limits, truncation metadata, and
text formatting.

```python
# mcp_server/tools.py
@mcp.tool()
def query_expression(ctx: Context, experiment_id: str | None = None,
                     ..., limit: int = 100) -> str:
    conn = _conn(ctx)
    results = api.query_expression(experiment_id=experiment_id, ..., conn=conn)

    summary = _compute_summary(results)
    detail = _apply_limit(results, limit)

    return _format_response(summary=summary, rows=detail,
                            total=len(results), returned=len(detail))
```

**Rules:**
- Calls `api/` functions, never `queries_lib` directly
- Adds `limit` parameter (not present in api/ or kg/)
- Computes tier-1 summary over full results before applying limit
- Returns formatted text (JSON string) with summary + detail +
  truncation metadata
- Tool docstrings describe the response format and cross-reference
  the package import for full data

---

## Tool design guidelines

### When to create a new tool vs extend an existing one

**Create a new tool when:**
- The question it answers is fundamentally different ("what experiments
  exist?" vs "what genes changed?")
- It queries a different subgraph or node type
- The return schema (dict keys) is different from existing tools
- An LLM would struggle to discover the functionality as a parameter
  of an existing tool

**Extend an existing tool when:**
- The change adds a filter or mode to the same question
- The return schema stays the same (same dict keys)
- An LLM would naturally express the new functionality as a parameter
  ("show me only the upregulated ones" → `direction="up"`)

**Example:** `query_expression` has experiment-centric and gene-centric
modes (different defaults for `significant_only`) as parameters of one
tool — not two tools — because the return schema is the same and the
LLM thinks of them as the same question with different anchors.

### What to build at each layer

When adding a new tool or modifying an existing one, all three layers
need work. Here's the checklist:

#### `queries_lib.py` — the query

| Do | Don't |
|---|---|
| Build parameterized Cypher | Execute queries |
| Accept filter parameters as kwargs | Accept `limit` — that's MCP's job |
| Return `tuple[str, dict]` | Return results or formatted text |
| Handle Cypher construction logic (WHERE clauses, OPTIONAL MATCH) | Handle business logic (multi-query composition, validation) |
| Use `$param` placeholders, never f-strings for values | Embed user values into Cypher strings |

**Ask:** "Is this a single Cypher query?" If yes, it belongs here.
If the function needs to run multiple queries or make decisions based
on results, that logic goes in api/.

#### `api/functions.py` — the function

| Do | Don't |
|---|---|
| Call query builders + `execute_query` | Build Cypher directly |
| Orchestrate multi-query workflows | Apply limits for LLM context |
| Validate parameters, raise `ValueError` | Format output as text |
| Accept optional `conn` parameter | Know about MCP, tiers, or LLMs |
| Document return dict keys in docstring | Add `limit` parameter (see exception below) |
| Handle business logic (dedup, member grouping, ortholog expansion) | |

**Exception — structural limits:** Some functions have limits that are
about data structure, not context windows. `member_limit` on
`get_homologs` caps members per ortholog group — a script user also
wants this. These stay in api/. The test: "would a script user
pass this parameter?" If yes, it's an api/ parameter.

**Ask:** "Can I call this function in a script and get useful results
without any MCP infrastructure?" If yes, the scope is right.

#### `mcp_server/tools.py` — the wrapper

| Do | Don't |
|---|---|
| Call api/ functions | Call `queries_lib` or `execute_query` directly |
| Add `limit` parameter for context management | Implement business logic |
| Compute tier-1 summary from full results | Return raw `list[dict]` |
| Apply limit for tier-2 detail | Validate parameters (api/ does this) |
| Format response as JSON text | Raise exceptions (catch and return error text) |
| Add truncation metadata (total, returned, truncated) | |
| Write docstrings for LLM audience | |
| Cross-reference package import in docstring | |

**Ask:** "Is this about how the LLM sees the data?" If yes, it
belongs here.

### Deciding tier-1/tier-2 for a tool

Not every tool needs tier-1/tier-2. The decision depends on whether
the result set can be large enough to require truncation.

| Result size | Tier pattern | Example tools |
|---|---|---|
| Always small (<20 rows) | Just return all rows, no tiers | `list_organisms`, `list_filter_values`, `gene_overview`, `resolve_gene` |
| Usually small, occasionally large | Add truncation metadata but no summary | `get_homologs`, `gene_ontology_terms` |
| Frequently large (100+ rows) | Full tier-1 summary + tier-2 detail | `query_expression`, `search_genes`, `genes_by_ontology` |

**Tier-1 summary fields are tool-specific.** Each tool computes
the summary that's most useful for LLM reasoning about its results:

| Tool | Useful tier-1 fields |
|---|---|
| `query_expression` | total genes, direction breakdown (up/down), top functional categories, time points covered |
| `search_genes` | total matches, organism breakdown, category breakdown |
| `genes_by_ontology` | total genes, organism breakdown, genes per term |

**The default limit should match typical LLM usage.** If the LLM
usually wants the top hits, a small limit (10–25) is fine. If the LLM
often needs to scan the full list, a larger limit (100) avoids
unnecessary truncation.

| Tool | Default limit | Rationale |
|---|---|---|
| `query_expression` | 100 | Experiment characterization wants many genes |
| `search_genes` | 10 | Usually looking for a specific gene |
| `genes_by_ontology` | 25 | Browsing genes in a category |
| `get_homologs` | no top-level limit | Small result sets (1–3 groups) |
| `run_cypher` | 25 | Safety net for arbitrary queries |

### Adding a new tool — complete checklist

1. **`queries_lib.py`** — add `build_{action}()` → `tuple[str, dict]`
   - Unit test: verify Cypher + params for known inputs
2. **`api/functions.py`** — add `{action}()` → `list[dict]` or `dict`
   - Document return dict keys in docstring
   - Add to `EXPECTED_KEYS` in `test_api_contract.py`
   - Unit test: mock `execute_query`, verify logic
   - Integration test: run against live KG, verify keys
3. **`__init__.py`** — add to re-exports
4. **`mcp_server/tools.py`** — add `@mcp.tool()` wrapper
   - Decide tier pattern (none / metadata-only / full tier-1/tier-2)
   - Set default limit
   - Write LLM-facing docstring (Args, response format, truncation
     warning if applicable, package import cross-reference)
   - If tier-1/tier-2: add to `TIER_TOOLS` in docstring structure test
   - Unit test: mock api/, verify formatting
5. **CLAUDE.md** — add to tool table if it changes the tool landscape
6. **MCP server instructions** — update if the new tool changes
   guidance (rare)

---

## Parameter and return conventions

### Standard parameter names

Use these names consistently across all layers. Don't invent
synonyms — `gene_id` is always `gene_id`, never `locus_tag_input`
or `gene_identifier` or `gene`.

**Gene identification:**

| Parameter | Type | Meaning | Example |
|---|---|---|---|
| `gene_id` | `str` | Single gene locus_tag | `"PMM0120"` |
| `gene_ids` | `list[str]` | Multiple gene locus_tags | `["PMM0120", "PMM0121"]` |
| `identifier` | `str` | Ambiguous gene identifier (for resolution) | `"PMM0120"`, `"petB"`, `"cytochrome"` |

`gene_id` / `gene_ids` are used when the input must be a locus_tag.
`identifier` is used only by `resolve_gene`, which accepts any form
(locus_tag, gene name, partial match) and resolves to locus_tags.

**Organism filtering:**

| Parameter | Type | Meaning | Example |
|---|---|---|---|
| `organism` | `str \| None` | Organism filter (strain name, CONTAINS match) | `"MED4"`, `"Prochlorococcus MED4"` |

Always `organism`, never `organism_name` or `strain`. The filter does
CONTAINS matching, so both `"MED4"` and `"Prochlorococcus MED4"` work.

**Experiment filtering (new with KG redesign):**

| Parameter | Type | Meaning | Example |
|---|---|---|---|
| `experiment_id` | `str \| None` | Experiment node ID | `"doi:10.1038/...\_coculture_vs_axenic_MED4"` |
| `condition_type` | `str \| None` | Experiment condition type | `"nitrogen_stress"`, `"coculture"` |

**Expression filters:**

| Parameter | Type | Meaning | Example |
|---|---|---|---|
| `direction` | `str \| None` | `"up"` or `"down"` | `"up"` |
| `min_log2fc` | `float \| None` | Minimum \|log2FC\| | `1.0` |
| `max_pvalue` | `float \| None` | Maximum adjusted p-value | `0.05` |
| `significant_only` | `bool \| None` | Filter to significant results | `True` |

**Ontology:**

| Parameter | Type | Meaning | Example |
|---|---|---|---|
| `ontology` | `str` | Ontology type | `"GO"`, `"KEGG"`, `"EC"` |
| `term_ids` | `list[str]` | Ontology term IDs | `["GO:0006412"]` |
| `search_text` | `str` | Free-text search query | `"photosystem"` |

**Ortholog filtering:**

| Parameter | Type | Meaning | Example |
|---|---|---|---|
| `source` | `str \| None` | OG database source | `"cyanorak"`, `"eggnog"` |
| `taxonomic_level` | `str \| None` | OG taxonomic level | `"Cyanobacteria"` |
| `max_specificity_rank` | `int \| None` | Cap OG breadth (0–3) | `1` |
| `exclude_paralogs` | `bool` | Exclude same-strain members | `True` |

**Structural parameters (api/ layer):**

| Parameter | Type | Meaning |
|---|---|---|
| `conn` | `GraphConnection \| None` | Connection reuse. Always optional, always last. |
| `member_limit` | `int` | Per-group member cap (structural, not context-related) |

**MCP-only parameters:**

| Parameter | Type | Meaning |
|---|---|---|
| `limit` | `int` | Top-level result limit for LLM context. Never in api/. |
| `ctx` | `Context` | MCP context (connection, debug flags). Always first. |

### Standard return field names

Use these names in Cypher RETURN clauses and dict keys. Consistency
here means scripts can process results from different tools without
mapping field names.

**Gene fields:**

| Field | Type | Meaning |
|---|---|---|
| `locus_tag` | `str` | Gene identifier (primary key) |
| `gene_name` | `str \| None` | Short gene name (`petB`, `dnaN`) |
| `product` | `str` | Functional description |
| `organism_name` | `str` | Full organism name |
| `organism_strain` | `str` | Strain name |
| `category` | `str \| None` | Functional category |

Note: when a gene is the primary subject, use `locus_tag`. When a
gene appears as a column in expression results, use `gene` (shorter,
since it's one column among many). This matches current usage in
`query_expression` vs `search_genes`.

**Expression fields:**

| Field | Type | Meaning |
|---|---|---|
| `gene` | `str` | locus_tag (short name in expression context) |
| `product` | `str` | Gene product description |
| `organism_strain` | `str` | Strain name |
| `experiment_id` | `str` | Experiment node ID |
| `experiment_name` | `str` | Human-readable experiment description |
| `condition_type` | `str` | Condition category |
| `time_point` | `str \| None` | Time point label (null for single-point) |
| `direction` | `str` | `"up"` or `"down"` |
| `log2fc` | `float` | Log2 fold change |
| `padj` | `float \| None` | Adjusted p-value |

**Ontology fields:**

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | Term ID (`GO:0006412`, `K00001`) |
| `name` | `str` | Term name |
| `score` | `float` | Search relevance score (search_ontology only) |

**Ortholog fields:**

| Field | Type | Meaning |
|---|---|---|
| `og_name` | `str` | Ortholog group name |
| `source` | `str` | OG database (`cyanorak`, `eggnog`) |
| `taxonomic_level` | `str` | Taxonomic scope |
| `member_count` | `int` | Total members in group |
| `organism_count` | `int` | Distinct organisms in group |

**Count/summary fields:**

| Field | Type | Meaning |
|---|---|---|
| `gene_count` | `int` | Number of genes |
| `count` | `int` | Generic count (when context is clear) |
| `total` | `int` | Total results (in truncation metadata) |
| `returned` | `int` | Results in this response |
| `truncated` | `bool` | Whether results were truncated |

### Current inconsistencies

See `transition_plan.md` Step 2 for the full list and migration plan.

---

## Naming conventions

### Function names

| Layer | Pattern | Example |
|---|---|---|
| `queries_lib.py` | `build_{action}` | `build_query_expression` |
| `api/functions.py` | `{action}` | `query_expression` |
| `mcp_server/tools.py` | `{action}` (same) | `query_expression` |

The MCP tool and API function share the same name. The MCP tool has an
additional `limit` parameter and `ctx` parameter. The query builder has
a `build_` prefix.

### Parameters

Same names across all three layers where applicable. A parameter called
`experiment_id` in the MCP tool is `experiment_id` in the API function
and `experiment_id` in the query builder.

### Return types

| Layer | Returns |
|---|---|
| `queries_lib.py` | `tuple[str, dict]` (Cypher + params) |
| `api/functions.py` | `list[dict]` or `dict` (see below) |
| `mcp_server/tools.py` | `str` (formatted JSON text) |

### api/ return type patterns

Some functions return flat lists (tabular results). Others return
structured objects (a gene + its groups, a filter set, etc.).

| Pattern | Return type | Examples |
|---|---|---|
| Flat list | `list[dict]` | `query_expression`, `search_genes`, `list_organisms`, `genes_by_ontology` |
| Structured | `dict` | `get_homologs`, `gene_overview`, `list_filter_values` |

Both are natural Python structures from Neo4j data. The MCP wrapper
serializes either to JSON text.

### Multi-query functions

Some api/ functions orchestrate multiple queries. This logic lives in
`api/functions.py`, not in the query builders or MCP wrappers.

Example: `get_homologs` runs up to 3 queries:

```python
# api/functions.py
def get_homologs(
    gene_id: str,
    source: str | None = None,
    taxonomic_level: str | None = None,
    max_specificity_rank: int | None = None,
    exclude_paralogs: bool = True,
    include_members: bool = False,
    member_limit: int = 50,
    conn: GraphConnection | None = None,
) -> dict:
    """Find orthologs grouped by ortholog group.

    Returns dict with keys:
      query_gene: dict — the input gene's metadata
      ortholog_groups: list[dict] — groups with counts, function,
          genera, and optionally member genes

    Raises ValueError if gene not found.
    """
    if conn is None:
        conn = GraphConnection()

    # 1. Gene metadata
    cypher, params = build_gene_stub(gene_id=gene_id)
    gene_rows = conn.execute_query(cypher, **params)
    if not gene_rows:
        raise ValueError(f"Gene '{gene_id}' not found.")

    # 2. Ortholog groups
    cypher, params = build_get_homologs_groups(
        gene_id=gene_id, source=source,
        taxonomic_level=taxonomic_level,
        max_specificity_rank=max_specificity_rank)
    groups = conn.execute_query(cypher, **params)

    # 3. Members (optional, per-group truncation)
    if include_members:
        cypher, params = build_get_homologs_members(
            gene_id=gene_id, source=source,
            taxonomic_level=taxonomic_level,
            max_specificity_rank=max_specificity_rank,
            exclude_paralogs=exclude_paralogs)
        members = conn.execute_query(cypher, **params)
        _attach_members_to_groups(groups, members, member_limit)

    return {"query_gene": gene_rows[0], "ortholog_groups": groups}
```

**Where each concern lives:**

| Concern | Layer | Rationale |
|---|---|---|
| Cypher query construction | `queries_lib.py` | Testable without DB |
| Query execution | `api/functions.py` | Orchestrates multiple queries |
| Multi-query composition | `api/functions.py` | Business logic (gene → groups → members) |
| Parameter validation | `api/functions.py` | Raises ValueError for invalid inputs |
| Per-group member truncation | `api/functions.py` | Structural concern — scripts also need this |
| Top-level result limit | `mcp_server/tools.py` | Context window concern — MCP only |
| Tier-1/tier-2 formatting | `mcp_server/tools.py` | LLM presentation concern |
| Error → user message | `mcp_server/tools.py` | Catches ValueError, returns friendly text |

**Rule of thumb:** if a script user would also want the behavior,
it goes in api/. If only the LLM needs it (limits, summaries,
formatting), it goes in MCP.

---

## Docstring conventions

Docstrings serve different audiences at each layer. MCP tool docstrings
are read by LLMs. API function docstrings are read by developers writing
scripts. Query builder docstrings are read by contributors working on
the core layer.

### `queries_lib.py` — for contributors

Minimal. What the query does, what parameters control, what Cypher
pattern it uses. Audience is someone editing the query builders.

```python
def build_query_expression(
    *,
    experiment_id: str | None = None,
    gene_ids: list[str] | None = None,
    significant_only: bool | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
) -> tuple[str, dict]:
    """Build Cypher for expression data query.

    Matches (Experiment)-[DE_IN]->(Gene) with optional filters.
    At least one of experiment_id or gene_ids must be provided.
    """
```

No need to document return dict keys here — the query builder
returns (cypher, params), not results. The Cypher RETURN clause
defines the result shape.

### `api/functions.py` — for script authors

This is the public contract. Must document:
- What the function does (one line)
- Parameters with types and semantics
- Return type and dict keys (this is the schema)
- Exceptions raised
- Example usage

```python
def query_expression(
    experiment_id: str | None = None,
    gene_ids: list[str] | None = None,
    significant_only: bool | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
    conn: GraphConnection | None = None,
) -> list[dict]:
    """Query differential expression data.

    At least one of experiment_id or gene_ids must be provided.

    Args:
        experiment_id: Experiment node ID (from list_experiments).
        gene_ids: One or more gene locus_tags.
        significant_only: Filter to significant results only.
            Defaults to None (return all).
        direction: Filter by "up" or "down".
        min_log2fc: Minimum absolute log2 fold change.
        max_pvalue: Maximum adjusted p-value.
        conn: Neo4j connection. Creates a default if not provided.

    Returns:
        list[dict] with keys:
            gene (str): locus_tag
            product (str): gene product description
            organism_strain (str): organism strain name
            experiment_id (str): experiment node ID
            experiment_name (str): human-readable experiment name
            condition_type (str): e.g. "nitrogen_stress", "coculture"
            time_point (str | None): time point label (null if single-point)
            direction (str): "up" or "down"
            log2fc (float): log2 fold change
            padj (float | None): adjusted p-value

    Raises:
        ValueError: If neither experiment_id nor gene_ids is provided.
        ValueError: If direction is not "up" or "down".

    Example:
        >>> from multiomics_explorer import query_expression
        >>> results = query_expression(experiment_id="doi:10.1038/...")
        >>> len(results)
        823
        >>> results[0]["gene"]
        'PMM0120'
    """
```

**The return dict keys section is critical.** This is the only place
where the result schema is defined. Script authors need to know what
keys to expect. If the keys change, this docstring must be updated.

### `mcp_server/tools.py` — for LLMs

MCP tool docstrings are the primary way LLMs learn what a tool does,
when to use it, and what to expect. They are read by every MCP client.
They should be written for an LLM audience — clear, specific, action-
oriented.

**Structure:**

```python
@mcp.tool()
def query_expression(
    ctx: Context,
    experiment_id: str | None = None,
    gene_ids: list[str] | None = None,
    significant_only: bool | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
    limit: int = 100,
) -> str:
    """Query differential expression results.

    Returns a summary (computed over ALL matching results) plus
    a detail section (top genes by effect size, limited).

    At least one of experiment_id or gene_ids is required.

    Two primary modes:
    - Experiment-centric: provide experiment_id → significant genes
      for that experiment. Default: significant_only=True.
    - Gene-centric: provide gene_ids → all experiments where those
      genes have results. Default: significant_only=False.

    Response format:
        summary: total genes, direction breakdown, top categories
            (always complete — computed over full result set)
        rows: top N genes ordered by |log2FC| (controlled by limit)
        metadata: total, returned, truncated

    IMPORTANT: If truncated is true, do not count rows to answer
    "how many" questions — use the total field from summary.

    For full results without limits, import the package in a script:
        from multiomics_explorer import query_expression
        results = query_expression(experiment_id="...")

    Args:
        experiment_id: Experiment ID from list_experiments.
        gene_ids: Gene locus_tags (e.g. ["PMM0120"]).
        significant_only: Filter to significant only. Defaults to
            True for experiment-centric, False for gene-centric.
        direction: "up" or "down".
        min_log2fc: Minimum |log2FC| threshold.
        max_pvalue: Maximum adjusted p-value threshold.
        limit: Max genes in detail section (default 100).
    """
```

**MCP docstring rules:**

1. **First line = what the tool does.** The LLM may only read the
   first line when deciding which tool to use.

2. **When to use this tool.** If there's ambiguity with another tool,
   clarify. "Use gene_overview for quick routing signals. Use
   query_expression for actual expression data."

3. **Response format.** Describe the structure the LLM will receive.
   For tier-1/tier-2 tools, explain that summary is always complete
   and detail may be truncated.

4. **Truncation warning.** Any tool that limits results must include
   the IMPORTANT note about not counting truncated rows.

5. **Package import cross-reference.** Every tool that applies limits
   should note: "For full results, import the package in a script."

6. **Args section.** Brief, focused on what the LLM needs to decide
   parameter values. Include valid values for enum-like params.
   Reference other tools for discovering valid values ("Use
   list_experiments to find experiment IDs").

7. **No implementation details.** The LLM doesn't need to know about
   Cypher patterns, Neo4j internals, or layer structure. Focus on
   what the tool accepts and returns.

### Docstring acceptance tests

Docstrings are a contract. If they drift from reality, the LLM makes
wrong assumptions and scripts break on unexpected keys. Two levels of
automated testing:

**API return key contracts (integration test, requires KG):**

Each api/ function documents its return dict keys. An integration test
calls the function against the live KG and asserts the keys match.

```python
# tests/integration/test_api_contract.py

# Authoritative source: kept in sync with api/ docstrings.
# If a key is added/removed in the Cypher RETURN clause,
# this dict and the docstring must both be updated.
EXPECTED_KEYS = {
    "query_expression": {
        "gene", "product", "organism_strain", "experiment_id",
        "experiment_name", "condition_type", "time_point",
        "direction", "log2fc", "padj",
    },
    "search_genes": {
        "locus_tag", "product", "organism_name",
        "organism_strain", "category", "score",
    },
    # ... every api/ function with list[dict] return
}

# Known-good params that return at least one result.
KNOWN_PARAMS = {
    "query_expression": {"gene_ids": ["PMM0120"]},
    "search_genes": {"search_text": "photosystem"},
    # ...
}

@pytest.mark.kg
@pytest.mark.parametrize("func_name", EXPECTED_KEYS)
def test_return_keys_match_contract(func_name):
    """Verify api function returns the documented dict keys."""
    func = getattr(api, func_name)
    results = func(**KNOWN_PARAMS[func_name])
    assert len(results) > 0, f"{func_name} returned no results"
    actual_keys = set(results[0].keys())
    assert actual_keys == EXPECTED_KEYS[func_name], (
        f"{func_name} key mismatch.\n"
        f"  Expected: {sorted(EXPECTED_KEYS[func_name])}\n"
        f"  Actual:   {sorted(actual_keys)}"
    )
```

Catches: Cypher RETURN clause changed but docstring not updated.
New key added to query but not documented. Documented key removed.

**MCP docstring structure lint (unit test, no KG):**

Can't test whether a docstring is helpful to an LLM, but can enforce
that required sections are present.

```python
# tests/unit/test_docstring_structure.py

# Tools that use tier-1/tier-2 response pattern
TIER_TOOLS = {"query_expression", "search_genes", "genes_by_ontology"}

def test_all_mcp_tools_have_docstrings():
    for name, func in get_registered_tools():
        assert func.__doc__, f"MCP tool '{name}' missing docstring"

def test_all_mcp_tools_have_args_section():
    for name, func in get_registered_tools():
        assert "Args:" in func.__doc__, (
            f"MCP tool '{name}' missing Args section")

def test_tier_tools_have_response_format():
    for name, func in get_registered_tools():
        if name in TIER_TOOLS:
            doc = func.__doc__
            assert "summary" in doc.lower(), (
                f"Tier tool '{name}' missing response format description")
            assert "truncat" in doc.lower(), (
                f"Tier tool '{name}' missing truncation warning")

def test_tier_tools_have_package_crossref():
    for name, func in get_registered_tools():
        if name in TIER_TOOLS:
            assert "from multiomics_explorer import" in func.__doc__, (
                f"Tier tool '{name}' missing package import cross-reference")
```

Catches: New tool added without docstring. Tier tool missing truncation
warning. Package import cross-reference forgotten.

### Docstring maintenance

When changing a function's behavior or return structure:

| Change | Update |
|---|---|
| New/removed dict key in results | api/ docstring + `EXPECTED_KEYS` in test |
| New parameter | All three layers |
| Changed tier-1 summary fields | MCP docstring (response format section) |
| Changed tool behavior/scope | MCP docstring (first line + when-to-use) |
| New Cypher pattern | queries_lib docstring only |
| New tier-1/tier-2 tool | Add to `TIER_TOOLS` set in test |

---

## Testing strategy

### Test categories

```
tests/
├── unit/                               # No Neo4j needed. Fast. Run always.
│   ├── test_query_builders.py          #   Cypher generation + params
│   ├── test_api_functions.py           #   Business logic (mocked DB)
│   ├── test_tool_wrappers.py           #   Tier-1/tier-2 formatting (mocked api/)
│   ├── test_tool_correctness.py        #   Tool output assertions (mocked DB)
│   ├── test_docstring_structure.py     #   Docstring lint
│   ├── test_connection.py              #   Connection error handling
│   ├── test_settings.py                #   Config loading
│   └── test_write_blocking.py          #   Cypher write keyword blocking
├── integration/                        # Requires Neo4j. Run with -m kg.
│   ├── test_api.py                     #   API functions against live KG
│   ├── test_api_contract.py            #   Return key assertions
│   ├── test_mcp_tools.py              #   MCP tools via protocol
│   └── test_tool_correctness_kg.py     #   Semantic correctness
├── regression/                         # Requires Neo4j. Snapshot-based.
│   └── test_regression.py              #   Golden-file comparison
└── evals/                              # Shared test cases
    ├── cases.yaml                      #   Test case definitions
    └── test_eval.py                    #   Eval runner
```

### Coverage requirements per layer

Every tool/function must have tests at each layer. When adding a new
tool or modifying an existing one, this is the minimum test coverage:

#### `queries_lib.py` — unit tests

| Must test | How | Example |
|---|---|---|
| Default params produce valid Cypher | Assert `WHERE` clauses, `RETURN` columns | `build_query_expression()` without filters |
| Each filter adds the right WHERE clause | Enable one filter at a time, assert Cypher contains it | `direction="up"` adds `WHERE r.direction = $direction` |
| Parameter values land in params dict | Assert params dict has correct keys and values | `params["direction"] == "up"` |
| Edge cases | None/empty params, boundary values | `gene_ids=[]`, `min_log2fc=0.0` |
| Invalid params raise errors | Where applicable (ontology validation) | `ontology="invalid"` → `ValueError` |

**Every `build_*` function gets its own test class** with test methods
for default, each filter, and edge cases.

#### `api/functions.py` — unit + integration tests

**Unit (mocked DB):**

| Must test | How |
|---|---|
| Calls the right query builder | Mock `build_*`, assert called with correct kwargs |
| Passes results through correctly | Mock `execute_query`, verify return value |
| Multi-query orchestration | Mock multiple `execute_query` calls, verify composition logic |
| Validation raises ValueError | Pass invalid params, assert exception |
| Default connection creation | Call without `conn`, verify it creates one |
| Connection reuse | Pass explicit `conn`, verify it's used |

**Integration (live KG):**

| Must test | How |
|---|---|
| Returns non-empty results for known inputs | Call with params that are known to match data |
| Return keys match contract | Assert `set(result[0].keys()) == EXPECTED_KEYS[func]` |
| Return types are correct | Assert `isinstance(result[0]["log2fc"], float)`, etc. |
| Filters actually filter | Call with/without filter, verify result set changes |

#### `mcp_server/tools.py` — unit tests

| Must test | How |
|---|---|
| Calls api/ function with correct params | Mock api/, assert called correctly |
| Tier-1 summary is computed from full results | Mock api/ to return N results, assert summary.total == N |
| Tier-2 applies limit | Mock api/ to return 200 results, assert detail has `limit` rows |
| Truncation metadata is correct | Mock api/ with results > limit, assert `truncated: true` |
| Truncation metadata when not truncated | Mock api/ with results < limit, assert `truncated: false` |
| Output is valid JSON | Parse the return string |
| Error handling | Mock api/ to raise ValueError, assert friendly error message |
| Docstring exists | Assert `func.__doc__` is not None |

### Regression tests

Snapshot-based tests using `pytest-regressions`. Detect any change in
query results after KG rebuilds or code changes.

**How they work:**

1. Test cases defined in `tests/evals/cases.yaml` — shared with
   eval tests
2. Each case specifies: tool, params, and expected result properties
3. First run generates golden files (YAML snapshots of full results)
4. Subsequent runs compare against golden files
5. `--force-regen` flag regenerates after intentional changes

**Coverage requirements:**

Every tool must have regression cases covering:

| Category | What to test | Example case |
|---|---|---|
| Happy path | Typical query with known results | `resolve_gene_by_locus_tag`: PMM0001 |
| Each filter | One case per filter parameter | `search_genes_with_organism`: organism="MED4" |
| Empty results | Query that legitimately returns nothing | `resolve_gene_not_found`: FAKE_GENE_999 |
| Edge cases | Boundary values, unusual inputs | Gene with no expression data |
| Cross-tool consistency | Same gene queried through different tools | PMM0120 via resolve_gene, gene_overview, query_expression |

### Data diversity in regression cases

Regression tests must exercise the diversity of the KG data, not just
code paths. A test that only uses MED4 genes with full annotations will
miss bugs that surface for poorly-annotated genes, Alteromonas-specific
edges, or strains with sparse data.

**Dimension 1: Organism diversity**

The KG has three genera with different properties:

| Genus | Strains with genes | Notes |
|---|---|---|
| Prochlorococcus | MED4, MIT9313, MIT9312, AS9601, MIT9301, NATL1A, NATL2A, RSP50 | Primary focus. Most expression data. Clades HL/LL. |
| Alteromonas | MIT1002, HOT1A3, EZ55 | Heterotroph. Different gene families. Coculture partner. |
| Synechococcus | WH8102, CC9311 | Outgroup. Fewer orthologs with Pro. Sparser data. |

Regression cases should include at least one gene from each genus.
Within Prochlorococcus, include both HL (MED4) and LL (MIT9313) clades
— they have different genome sizes and gene content.

**Dimension 2: Annotation completeness**

Genes vary widely in how much is known about them:

| Level | Characteristics | Test with |
|---|---|---|
| Well-annotated | Has product name, GO terms, KEGG, EC, Pfam, ortholog groups | e.g., photosystem genes, ribosomal proteins |
| Partially annotated | Has product name but sparse ontology | e.g., transport genes with KEGG but no EC |
| Hypothetical with clues | "hypothetical protein" but has Pfam domain or ortholog group | Common in Pro — tests that annotations connect |
| Hypothetical minimal | "hypothetical protein", no GO/KEGG/EC, maybe no orthologs | Tests empty/null handling across all tools |

Every tool should have regression cases at multiple annotation levels.
A `gene_ontology_terms` test that only uses well-annotated genes won't
catch issues with genes that have zero terms.

**Dimension 3: Expression data availability**

| Level | Characteristics | Test with |
|---|---|---|
| Expression-rich | Multiple experiments, multiple conditions, significant results | Core Pro genes (PMM0120 etc.) |
| Expression-sparse | In the KG but only 1–2 experiments, maybe not significant | Less-studied Pro genes |
| No expression data | Gene exists but no expression edges | Most Alt/Syn genes, or newly added Pro genes |
| Coculture-only | Expression only from coculture experiments, not environmental | Alteromonas genes |
| Time-course | Expression across multiple time points | Genes in time-course experiments |

Tests for `query_expression` and `gene_overview` must cover all these
levels. A gene with no expression data should return empty results
gracefully, not error.

**Dimension 4: Ortholog group structure**

| Level | Characteristics | Test with |
|---|---|---|
| Multi-source | Has both Cyanorak and eggNOG groups | Core Pro genes |
| Single-source | Only eggNOG (Alteromonas, Synechococcus) | Alt/Syn genes |
| No orthologs | Gene not in any ortholog group | Rare, but exists (strain-specific genes) |
| Large group | Ortholog group with 50+ members | Conserved housekeeping genes |
| Small group | Ortholog group with 2–3 members | Strain-specific clusters |

**Dimension 5: Edge cases in the data**

| Case | What it tests | Example |
|---|---|---|
| Gene in multiple organisms | resolve_gene returns multiple hits | dnaN, ribosomal proteins |
| Gene with special characters in product | String handling in Cypher/JSON | Products with apostrophes (stored as ^), commas |
| Organism with zero genes | Genus-level nodes (Phage, Marinobacter) | list_organisms handles gracefully |
| Ontology term with no genes | Term exists but nothing annotated to it | Rare GO terms |
| Very long product description | Truncation/display issues | Some Alteromonas genes |

**Minimum diversity matrix per tool:**

Each tool's regression cases should cover at least 5 inputs from each
dimension:

| Dimension | Minimum 5 from |
|---|---|
| Organisms | 5 different strains spanning Pro HL, Pro LL, Alt, Syn |
| Annotation level | 5 genes across well-annotated, partial, hypothetical |
| Expression availability | 5 genes across expression-rich, sparse, none, coculture, time-course |
| Result size | 5 queries across many-results, few-results, empty |

5 per dimension gives enough coverage to catch patterns that a single
example would miss — e.g., a bug that only affects LL clade genes, or
null handling that works for one hypothetical gene but not another
because of a different combination of missing fields.

Cases naturally cover multiple dimensions (a well-annotated MED4 gene
covers Pro + HL + well-annotated + expression-rich in one case). The
goal is that across all cases for a tool, every dimension has at least
5 representatives.

**Case definition format** (`cases.yaml`):

```yaml
- id: query_expression_experiment_centric
  tool: query_expression
  desc: Experiment-centric query returns DE genes for known experiment
  params:
    experiment_id: "doi:10.1038/..."
    significant_only: true
  expect:
    min_rows: 10
    columns: [gene, product, organism_strain, experiment_id,
              direction, log2fc, padj]
    contains:
      direction: up   # at least one upregulated gene
```

**`expect` fields:**

| Field | Meaning |
|---|---|
| `min_rows` | Minimum result count (default 1) |
| `max_rows` | Maximum result count (optional) |
| `columns` | Required keys in result dicts |
| `contains` | At least one row must have this key:value |
| `row0` | First row must match these key:values |

**When to regenerate:**
- After KG rebuild (data changed) → `--force-regen`, review diffs
- After Cypher query change (different columns/ordering) → `--force-regen`, review diffs
- After code-only change (no query/data change) → should pass without regen. If it doesn't, something broke.

### Adding tests for a new tool — checklist

1. **`test_query_builders.py`** — new test class:
   - `test_default_query` — no filters
   - `test_{filter}_filter` — one per filter parameter
   - `test_params_values` — verify params dict
   - `test_edge_cases` — empty/None/boundary inputs

2. **`test_api_functions.py`** — new test class:
   - `test_calls_correct_builder` — mock builder, assert called
   - `test_returns_execute_result` — mock execute_query, verify passthrough
   - `test_validation` — invalid params → ValueError
   - `test_multi_query_composition` — if function runs multiple queries
   - `test_conn_default_creation` — no conn passed

3. **`test_tool_wrappers.py`** — new test class:
   - `test_calls_api_function` — mock api, assert called
   - `test_output_is_valid_json` — parse return string
   - `test_tier1_summary` — if tier-1/tier-2 tool
   - `test_tier2_limit` — if tier-1/tier-2 tool
   - `test_truncation_metadata` — if tool applies limit
   - `test_error_handling` — api raises ValueError

4. **`test_api_contract.py`** — add to `EXPECTED_KEYS` dict

5. **`test_docstring_structure.py`** — add to `TIER_TOOLS` if applicable

6. **`cases.yaml`** — add regression cases:
   - Happy path (1–2 cases)
   - Each filter (1 case per filter)
   - Empty results (1 case)
   - Cross-tool consistency if applicable

7. **Run regression** — `pytest tests/regression/ --force-regen` to
   generate initial golden files, review them, commit.

---

## Documentation structure

```
docs/
├── methodology/
│   └── llm_omics_analysis.md       # WHY: dual interface, tiers, workflow patterns
├── architecture.md                  # Current state (to be updated as we transition)
├── architecture_target.md           # THIS DOC: target code architecture
├── transition_plan.md               # HOW: steps to get from current → target
├── analysis/                        # Polished analysis write-ups
│   └── catalase_expression.md
└── testplans/
    └── testplan.md
```

---

## Error handling

Errors originate at different layers and must be handled differently
depending on the consumer.

### Error flow across layers

```
Neo4j error (timeout, connection lost, bad Cypher)
    ↓
connection.py — raises neo4j.exceptions.*
    ↓
api/functions.py — catches some, raises others
    ↓
mcp_server/tools.py — catches all, returns friendly text
    or
script (user code) — catches or lets propagate
```

### `kg/connection.py`

Lets Neo4j driver exceptions propagate. Does not catch or wrap them.

| Error | What happens |
|---|---|
| `ServiceUnavailable` | Neo4j is down. Propagates up. |
| `AuthError` | Bad credentials. Propagates up. |
| `ClientError` | Bad Cypher syntax. Propagates up. |
| Query timeout | Neo4j kills the query. Propagates as `TransientError`. |

`verify_connectivity()` returns `bool` — the only place that swallows
connection errors. Used for health checks, not query execution.

### `api/functions.py`

Validates parameters and raises `ValueError` for bad inputs. Lets
Neo4j errors propagate — the api layer doesn't know whether the
caller is MCP or a script, so it can't decide how to present the
error.

| Error | What api/ does |
|---|---|
| Invalid parameter value | `raise ValueError("direction must be 'up' or 'down'")` |
| Missing required param | `raise ValueError("at least one of experiment_id or gene_ids required")` |
| Gene not found | `raise ValueError("Gene 'XXX' not found.")` |
| Neo4j errors | Propagate unchanged |
| Empty results | Return empty `list` or `dict` — not an error |

**Important:** empty results are not errors. "Zero genes are
differentially expressed" is a valid result. The api layer returns
`[]`, and the caller interprets.

### `mcp_server/tools.py`

Catches all exceptions and returns user-friendly text. MCP tools
must never raise — the LLM sees the return string, not a traceback.

```python
@mcp.tool()
def query_expression(ctx, experiment_id=None, ...):
    try:
        conn = _conn(ctx)
        results = api.query_expression(
            experiment_id=experiment_id, ..., conn=conn)
        return _format_response(results, ...)
    except ValueError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error querying expression data: {e}"
```

| Error | What MCP returns |
|---|---|
| `ValueError` from api/ | `"Error: direction must be 'up' or 'down'"` |
| Neo4j timeout | `"Error querying expression data: <timeout message>"` |
| Neo4j down | `"Error: could not connect to the knowledge graph."` |
| Empty results | Normal response with `total: 0` — not an error |

### Scripts (user code)

Scripts that import the package get raw exceptions. They handle them
however they want:

```python
from multiomics_explorer import query_expression

try:
    results = query_expression(experiment_id="nonexistent")
except ValueError as e:
    print(f"Bad input: {e}")
# Neo4j errors propagate as neo4j.exceptions.*
```

### What NOT to do

- Don't return empty string or `None` from MCP tools on error —
  always return an error message the LLM can read.
- Don't catch exceptions in api/ to return error strings — that's
  MCP's job. Api/ raises, MCP catches.
- Don't use generic `Exception` in api/ validation — always
  `ValueError` with a specific message.
- Don't treat empty results as errors anywhere in the stack.

---

## Logging

### What to log at each layer

| Layer | What | Level | Why |
|---|---|---|---|
| `connection.py` | Cypher query + params | `DEBUG` | Query debugging and performance |
| `connection.py` | Connection failures | `WARNING` | Operational monitoring |
| `api/functions.py` | Validation failures | `DEBUG` | Helps diagnose bad inputs |
| `api/functions.py` | Multi-query orchestration steps | `DEBUG` | Trace complex workflows |
| `mcp_server/tools.py` | Tool call + params | `INFO` | Audit trail of what the LLM requested |
| `mcp_server/tools.py` | Errors caught and returned | `WARNING` | Operational monitoring |
| `mcp_server/server.py` | Server startup/shutdown | `INFO` | Lifecycle events |

### Logger naming

Each module uses `logging.getLogger(__name__)`:

```python
# In multiomics_explorer/api/functions.py
logger = logging.getLogger(__name__)
# Logger name: "multiomics_explorer.api.functions"
```

This allows filtering by layer:
```
# See all API activity
logging.getLogger("multiomics_explorer.api").setLevel(logging.DEBUG)

# See only MCP tool calls
logging.getLogger("multiomics_explorer.mcp_server").setLevel(logging.INFO)
```

### What NOT to log

- Neo4j result data — can be large, contains research data
- Full MCP responses — logged by MCP protocol layer already
- Credentials — never log connection strings with passwords

### Debug mode

The MCP server has a `debug_queries` flag (set via environment
variable or lifespan context). When enabled, MCP tool responses
include the Cypher query and params as a `_debug` block. This is
separate from Python logging — it's embedded in the tool response
for the LLM to see.

---

## KG schema coupling

This repo reads from a Neo4j graph built by the separate
`multiomics_biocypher_kg` repo. The two repos are coupled by the
graph schema — node labels, relationship types, and property names.

### Where schema assumptions live

| File | Schema assumptions |
|---|---|
| `queries_lib.py` | Node labels, relationship types, property names in Cypher |
| `constants.py` | Valid enum values (OG sources, taxonomic levels) |
| `schema.py` | Schema introspection (discovers labels/rels dynamically) |
| `tests/evals/cases.yaml` | Specific gene IDs, expected property values |
| `tests/regression/` | Golden files with exact query results |

`queries_lib.py` is the primary coupling point. Every Cypher query
assumes specific labels (`Gene`, `Experiment`, `OrthologGroup`),
relationship types (`DE_IN`, `Gene_in_ortholog_group`), and property
names (`locus_tag`, `log2_fold_change`).

### When the KG schema changes

Schema changes in the KG repo require coordinated updates here:

| KG change | Explorer impact | What to update |
|---|---|---|
| New node type | New queries possible | queries_lib + api + MCP tool |
| Renamed property | Cypher breaks | queries_lib (Cypher) + return key conventions |
| New property on existing node | New data available | queries_lib RETURN clause + api docstring |
| Removed relationship type | Cypher breaks | queries_lib + api + MCP tool |
| New relationship type | New queries possible | queries_lib + api + MCP tool |
| Data change (same schema) | Results change | Regression test regeneration |

### How to detect schema drift

1. **Integration tests fail** — Cypher references a label/property
   that no longer exists. Neo4j returns `ClientError`.
2. **Regression tests fail** — schema is the same but data changed
   (KG rebuild with new papers). `--force-regen` and review diffs.
3. **`get_schema` tool** — returns live schema from Neo4j. Compare
   against what `queries_lib.py` assumes.

### Schema versioning (not implemented yet)

Currently there's no formal schema version. The KG repo and explorer
repo are kept in sync manually. For phase 3 (multiple researchers),
consider:
- A schema version property on a metadata node in the KG
- Explorer checks schema version at startup, warns on mismatch
- `get_schema` response includes version for debugging

### Coordinated deployment

When schema changes, both repos must be updated together:
1. KG repo: update adapters, rebuild KG
2. Explorer repo: update queries_lib, api, MCP tools, tests
3. Regenerate regression fixtures: `--force-regen`
4. Deploy new KG + new explorer together

See methodology doc "Roadmap" for the phased deployment plan.

---

## Configuration

### `.env` (gitignored)

```
NEO4J_URI=bolt://localhost:7687       # local dev
NEO4J_USER=                           # empty for local
NEO4J_PASSWORD=                       # empty for local
```

### `pyproject.toml` entry points

```toml
[project.scripts]
multiomics-explorer = "multiomics_explorer.cli.main:app"
multiomics-kg-mcp = "multiomics_explorer.mcp_server.server:main"
```

Phase 3 adds: `multiomics-explorer init-claude` CLI command.

### MCP server instructions

The `instructions` parameter in FastMCP carries the dual-interface
contract (response format, truncation rules, package import guidance).
See methodology doc for the draft content.
