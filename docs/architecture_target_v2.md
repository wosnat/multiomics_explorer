# Target architecture

This document describes the target code architecture for the
multiomics_explorer package. See `methodology/llm_omics_analysis_v2.md`
for the design rationale (why dual interface, why skills, why summary
mode) and `transition_plan_v2.md` for how to get from here to there.

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
│   └── tools.py                #   MCP tool wrappers (summary/detail/about modes)
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
┌───────▼──────────────▼──┐    ┌────────▼──────────────────┐
│   mcp_server/           │    │   api/                     │
│                         │    │                            │
│   tools.py              │    │   functions.py             │
│   - summary/detail/     │    │   - returns list[dict]     │
│     about modes         │    │   - summary=True support   │
│   - limit parameter     │    │   - no limits (except      │
│   - truncation metadata │    │     structural ones)       │
│   - error → text        │    │   - no formatting          │
│   - usage logging       │    │                            │
└───────────┬─────────────┘    └────────┬──────────────────┘
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

Functions in `queries_lib.py` return `tuple[str, dict]` — a Cypher
query string and its parameters. They do NOT execute the query. This
keeps them testable without Neo4j.

```python
# queries_lib.py — detail query (returns rows)
def build_query_expression(
    *, experiment_id: str | None = None,
    locus_tags: list[str] | None = None,
    significant_only: bool | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
) -> tuple[str, dict]:
    """Build Cypher for expression data rows.

    Matches (Experiment)-[Changes_expression_of]->(Gene) with optional filters.
    Returns individual gene rows.
    """
    ...

# queries_lib.py — summary query (returns aggregations)
def build_query_expression_summary(
    *, experiment_id: str | None = None,
    locus_tags: list[str] | None = None,
    significant_only: bool | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
) -> tuple[str, dict]:
    """Build Cypher for expression summary statistics.

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

### 2. `api/` — public Python API

**Responsibility:** High-level functions that combine query building +
execution. This is what scripts import and what MCP tools call.

```python
# api/functions.py
def query_expression(
    experiment_id: str | None = None,
    locus_tags: list[str] | None = None,
    significant_only: bool | None = None,
    direction: str | None = None,
    min_log2fc: float | None = None,
    max_pvalue: float | None = None,
    summary: bool = False,
    conn: GraphConnection | None = None,
) -> list[dict] | dict:
    """Query differential expression data.

    Args:
        ...
        summary: If True, return precomputed summary statistics
            (counts, breakdowns) instead of individual rows.
        conn: Neo4j connection. Creates a default if not provided.

    Returns:
        If summary=False: list[dict] with keys: gene, product, ...
        If summary=True: dict with keys: total, direction_breakdown, ...
    """
    if conn is None:
        conn = GraphConnection()
    if summary:
        cypher, params = queries_lib.build_query_expression_summary(
            experiment_id=experiment_id, locus_tags=locus_tags, ...)
    else:
        cypher, params = queries_lib.build_query_expression(
            experiment_id=experiment_id, locus_tags=locus_tags, ...)
    return conn.execute_query(cypher, **params)
```

**Re-exported from package root:**

```python
# __init__.py
from multiomics_explorer.api.functions import (
    query_expression,
    search_genes,
    gene_overview,
    ...
)
```

**Rules:**
- Returns `list[dict]` or `dict` — no formatting
- Optional `limit` parameter on functions with potentially large
  result sets. Passed to the query builder for server-side
  `ORDER BY ... LIMIT`. Default is `None` (all rows). Scripts
  can use it for "top N" queries; MCP always passes it.
  **`limit` applies only to detail queries.** Summary queries
  always return complete aggregations regardless of limit.
- `summary` parameter available on functions where the KG supports it
- Accepts optional `conn` parameter (always last) for connection reuse
- Parameters match MCP tool parameters (same names, same types)
- Validates parameters, raises `ValueError` for bad inputs
- Orchestrates multi-query workflows (get_homologs: gene → groups →
  members)
- Docstrings document return dict keys — this is the contract

### 3. `mcp_server/` — MCP tool wrappers

**Responsibility:** Wrap `api/` functions for LLM consumption. Add
modes, limits, truncation metadata, and text formatting.

```python
# mcp_server/tools.py
from typing import Annotated, Literal
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

@mcp.tool(
    annotations={"readOnlyHint": True},
    meta={"has_summary": "true"},
)
def query_expression(
    ctx: Context,
    experiment_id: Annotated[
        str | None,
        Field(description="Experiment ID from list_experiments"),
    ] = None,
    direction: Annotated[
        Literal["up", "down"] | None,
        Field(description="Filter by direction"),
    ] = None,
    ...,
    mode: Annotated[
        Literal["summary", "detail", "about"],
        Field(description="Response mode"),
    ] = "summary",
    limit: Annotated[
        int,
        Field(ge=1, le=500, description="Max rows in detail mode"),
    ] = 100,
) -> dict | str:
    """Query differential expression results.

    Summary mode (default) returns precomputed statistics.
    Detail mode returns top genes by |log2FC|, limited.
    About mode returns usage guide with examples.
    """
    conn = _conn(ctx)
    if mode == "about":
        return _about("query_expression")
    elif mode == "summary":
        return api.query_expression(
            experiment_id=experiment_id, ...,
            summary=True, conn=conn)
    else:  # detail
        results = api.query_expression(
            experiment_id=experiment_id, ...,
            summary=False, limit=limit, conn=conn)
        return _format_detail(results)
```

**Note:** FastMCP handles error conversion automatically —
`ValueError` from api/ becomes a tool error response. No manual
try/except needed for standard cases. Use `ToolError` for
tool-specific error messages. `ctx: Context` is injected by
FastMCP and hidden from the tool schema.

**Rules:**
- Calls `api/` functions, never `queries_lib` directly
- Three modes: `summary` (default), `detail`, `about`
- `limit` parameter applies only in detail mode
- Truncation metadata (total, returned, truncated) in detail mode
- Never raises raw exceptions — uses `ToolError` for tool-specific
  messages, lets FastMCP handle the rest
- Tool docstrings are LLM-facing (see Docstring conventions)
- Logs every tool call (see Usage logging)

---

## Tool modes

### Summary mode (default)

Returns precomputed statistics. Cheap, fast, always complete.
Claude uses this for reasoning and to guide the next tool call
in a chain.

**Implementation:** Calls `api.func(summary=True)`, which generates
a summary query reading precomputed properties or aggregating
without fetching all rows.

**Not all tools need summary mode.** Tools with inherently small
result sets (list_organisms, resolve_gene, gene_overview) just
return all results directly.

Whether a tool needs summary mode depends on whether its result
set can be large enough to benefit from aggregation before
fetching rows. This is a per-tool decision made during
implementation, informed by actual KG data sizes.

**Known large result sets:**

| Tool | Summary mode | Summary fields |
|---|---|---|
| `query_expression` | Yes | total genes, direction breakdown, top categories, time points, median/max \|log2FC\| |
| `search_genes` | Yes | total matches, organism breakdown, category breakdown |
| `genes_by_ontology` | Yes | total genes, organism breakdown, genes per term |

**Known small result sets:**

| Tool | Summary mode | Rationale |
|---|---|---|
| `list_organisms` | No | Always returns all (~15 organisms) |
| `resolve_gene` | No | Typically 1–5 matches |
| `gene_overview` | No | Already a summary by design |

**Decide during implementation:**

| Tool | Notes |
|---|---|
| `search_ontology` | Can be large for broad terms — needs profiling |
| `gene_ontology_terms` | Usually small, but poorly annotated genomes may surprise |
| `get_homologs` | Groups are small, but member lists can be large |

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
  or sequences. Summaries are aggregations only.

**Per-tool summary fields:**

| Tool | Counts | Distributions | Top N | Availability |
|---|---|---|---|---|
| `query_expression` | total, per-direction | median/max \|log2FC\|, median padj | top 10 categories (with count) | time points covered |
| `search_genes` | total, per-organism | median relevance score | top 10 categories (with count) | — |
| `genes_by_ontology` | total, per-organism | — | top 10 terms (with gene count) | — |

### Detail mode

Returns raw rows with a limit, ordered by a score. For inspection
of individual records. Claude uses this when it needs to see actual
data, not just counts.

**Every detail response includes:**
- Rows ordered by an explicit sort key (|log2FC|, relevance score,
  count — documented per tool)
- The score value in each row
- Truncation metadata: `total`, `returned`, `truncated`

**Implementation:** Calls `api.func(summary=False, limit=N)`.
The limit is pushed into the Cypher query (server-side `ORDER BY
... LIMIT`) for efficiency over remote connections. Claude decides
the limit based on the summary — if summary shows 823 genes,
Claude might request detail with `limit=50` for a quick look or
`limit=200` for deeper inspection.

Truncation metadata (`total`, `returned`, `truncated`) is added
by the MCP wrapper. `total` comes from the summary (precomputed),
not from counting all rows.

**Batching:** For large result sets transferred over a remote
connection, the Neo4j driver handles streaming internally. If
profiling shows specific queries are slow in detail mode, options
include:
- Adding server-side LIMIT + ORDER BY in the Cypher query
- Pagination via cursor (skip/limit) if needed
- Splitting into multiple focused queries in the api/ layer

These are per-query optimizations, not framework-level decisions.

### About mode

Returns usage information for the tool: what it does, what
parameters mean, how it chains with other tools, when to switch
to package import. This is the self-describing tool capability
(methodology principle 6).

**Implementation:** Reads from
`skills/multiomics-kg-guide/references/tools/{tool-name}.md`. Single
source of truth — same content serves Claude Code skills (loaded
as a reference) and MCP about mode (read by the server). Does not
hit the database.

**Content per tool:**
- What the tool does (expanded beyond the docstring first line)
- Parameter guide with valid values and discovery references
  ("use list_experiments to find experiment_ids")
- Response guide: what fields are returned in summary and detail
  modes, what scores mean, what the sort key is, how to interpret
  distribution statistics
- **Examples:**
  - One-shot: concrete call with expected response shape for
    each mode (summary and detail)
  - Chain: this tool in context — what comes before, what comes
    after, showing a realistic multi-step sequence
  - Package import: equivalent call as a script
- **Common mistakes** with correct alternatives (e.g., counting
  truncated rows instead of using summary total)
- When to use summary vs detail mode
- Chaining patterns ("after resolve_gene, use gene_overview for
  data availability, then query_expression for expression data")

**About mode serves all clients equally** — chat mode and agentic
mode both get the same self-documentation. This is the baseline
for tool competence (methodology layer 1).

### About content format

Per-tool reference files (`references/tools/*.md`) use a structured
format that is both human-readable and machine-parseable. Examples
are tagged with fenced code blocks so tests can extract and
validate them automatically.

**Convention:**

````markdown
## Examples

### Summary mode

```example-call
query_expression(experiment_id="doi:10.1038/...", mode="summary")
```

```example-response
{"total": 823, "direction_breakdown": {"up": 412, "down": 411},
 "median_log2fc": 1.2, "top_categories": [{"name": "photosynthesis", "count": 45}]}
```

```expected-keys
total, direction_breakdown, median_log2fc, top_categories
```

### Detail mode

```example-call
query_expression(experiment_id="doi:10.1038/...", mode="detail", limit=50)
```

```expected-keys
locus_tag, product, organism_strain, direction, log2fc, padj
```

### Common mistakes

```mistake
# WRONG: counting rows from truncated detail
len(rows)  # gives 50, not 823
```

```correction
# RIGHT: use total from summary
summary["total"]  # gives 823
```
````

**What tests extract:**

| Block tag | Test type | What it checks |
|---|---|---|
| `example-call` + `expected-keys` | Integration (needs KG) | Run the call, verify return keys match |
| `example-call` + `example-response` | Unit (no KG) | Verify response field names match `expected-keys` |
| `expected-keys` alone | Unit (no KG) | Verify keys match `EXPECTED_KEYS` dict for the tool |

**Single source of truth:** the reference file is the skill content
(Claude reads it in about mode), the documentation (developers read
it), and the test input (test parser extracts and validates). No
separate examples file to maintain.

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
    ├── tool-chaining.md        # Common chains: resolve → overview → query
    ├── summary-vs-detail.md    # Decision tree for mode selection
    ├── mcp-vs-import.md        # Interface selection guide
    └── tools/                  # Per-tool about content (also served by MCP about mode)
        ├── query-expression.md
        ├── search-genes.md
        ├── resolve-gene.md
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
    │   └── README.md           # Template with sections to fill
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
2. Summarize: `query_expression(mode="summary")` for overview
3. **Gate:** Confirm correct experiment with user if ambiguous
4. Extract: write script importing `multiomics_explorer.query_expression`
   → `data/de_genes.csv`
5. **Gate:** Verify row count matches summary total
6. Analyze: enrichment script + volcano plot
   (see [enrichment guide](references/enrichment-guide.md))
7. **Gate:** Verify outputs exist and are non-empty
8. Interpret: write README.md with biological narrative

## Output structure

Use the [analysis template](assets/analysis-template/) for directory
layout: data/, scripts/, results/, README.md
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

## Response modes

Every tool supports up to three modes:
- **summary** (default): precomputed statistics, cheap, always complete
- **detail**: raw rows with limit, for inspection
- **about**: self-documentation, usage guide, chaining patterns

## Key rules

- If `truncated: true`, use `total` from metadata, not `len(rows)`
- Summary first, then decide on limit for detail based on summary stats
- For bulk data, use package import in a script — not detail mode with high limit
- Use summary mode for reasoning, detail mode for inspection

## References (loaded on demand)

- [Tool chaining patterns](references/tool-chaining.md)
- [Summary vs detail guide](references/summary-vs-detail.md)
- [MCP vs package import](references/mcp-vs-import.md)
- Per-tool guides: [references/tools/](references/tools/) — also
  served by each tool's `mode="about"`
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
  no formatting. summary=True generates aggregation Cypher.
- **api/functions.py** — calls builders + execute. Returns
  list[dict] or dict. No limits, no formatting. Raises ValueError.
- **mcp_server/tools.py** — calls api/ only. Three modes:
  summary/detail/about. Never raises. Logs every call.
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
   - summary/detail/about modes
   - LLM-facing docstring
   - **Gate:** unit test (mocked) passes
5. Integration test against live KG
   - **Gate:** passes, return keys match contract
6. Regression cases → `cases.yaml` + golden files
7. Skill updates
   - Update multiomics-kg-guide skill if tool changes the landscape
   - Add/update pipeline skills that use the tool
   - Write about-mode content
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
│   │           ├── query-expression.md
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
| Always small (<20 rows) | detail + about (no summary needed) | `list_organisms`, `resolve_gene`, `gene_overview` |
| Frequently large (100+ rows) | summary + detail + about | `query_expression`, `search_genes`, `genes_by_ontology` |

Summary mode is not needed when detail mode always returns
everything without truncation.

### Default limits (detail mode)

| Tool | Default limit | Rationale |
|---|---|---|
| `query_expression` | 100 | Experiment characterization wants many genes |
| `search_genes` | 10 | Usually looking for a specific gene |
| `genes_by_ontology` | 25 | Browsing genes in a category |
| `run_cypher` | 25 | Safety net for arbitrary queries |

---

## Parameter and return conventions

### Standard parameter names

Use these names consistently across all layers.

**Gene identification:**

| Parameter | Type | Meaning |
|---|---|---|
| `locus_tag` | `str` | Single gene locus tag |
| `locus_tags` | `list[str]` | Multiple gene locus tags |
| `identifier` | `str` | Ambiguous input (for resolution only — accepts locus tag, gene name, or partial match) |

Always `locus_tag` / `locus_tags`, never `gene_id` / `gene_ids`.
Matches the return field name and the KG property. The about mode
for each tool explains what a locus tag is.

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
| `direction` | `str \| None` | `"up"` or `"down"` |
| `min_log2fc` | `float \| None` | Minimum \|log2FC\| |
| `max_pvalue` | `float \| None` | Maximum adjusted p-value |
| `significant_only` | `bool \| None` | Filter to significant results |

**Mode and structural parameters:**

| Parameter | Type | Meaning | Layer |
|---|---|---|---|
| `summary` | `bool` | Summary vs full results | api/ |
| `limit` | `int \| None` | Detail result limit (server-side ORDER BY + LIMIT). Default None = all rows | api/ + MCP |
| `mode` | `str` | `"summary"`, `"detail"`, `"about"` | MCP only |
| `conn` | `GraphConnection \| None` | Connection reuse (always last) | api/ |
| `ctx` | `Context` | MCP context (always first) | MCP only |

### Standard return field names

Consistent across tools so scripts can process results without
mapping field names.

**Gene fields:** `locus_tag`, `gene_name`, `product`,
`organism_name`, `organism_strain`, `category`

**Expression fields:** `locus_tag`, `product`, `organism_strain`,
`experiment_id`, `experiment_name`, `condition_type`, `time_point`,
`direction`, `log2fc`, `padj`

**Truncation metadata (MCP detail mode):** `total`, `returned`,
`truncated`

### Return types per layer

| Layer | Returns |
|---|---|
| `queries_lib.py` | `tuple[str, dict]` (Cypher + params) |
| `api/functions.py` | `list[dict]` or `dict` |
| `mcp_server/tools.py` | `dict`, `str`, or `list[dict]` (FastMCP serializes to MCP response) |

### Naming conventions

| Layer | Function pattern | Example |
|---|---|---|
| `queries_lib.py` | `build_{action}` | `build_query_expression` |
| `api/functions.py` | `{action}` | `query_expression` |
| `mcp_server/tools.py` | `{action}` (same) | `query_expression` |

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
3. Mode descriptions (summary/detail/about)
4. Truncation warning for detail mode
5. Package import cross-reference
6. Args with valid values and discovery references

**Cross-layer consistency tests:**

`EXPECTED_KEYS` dict is the single source of truth for return
field names. Tests verify consistency in both directions:

| Test | Type | What it checks |
|---|---|---|
| Return keys vs KG | Integration | Run api/ call against live KG, assert `result.keys() == EXPECTED_KEYS[func]` |
| api/ params vs MCP params | Unit | MCP tool params (minus `ctx`, `mode`, `limit`) match api/ params (minus `conn`, `summary`) |
| About-mode `expected-keys` vs `EXPECTED_KEYS` | Unit | Parse about reference files, assert keys match |
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

---

## Usage logging

### MCP tool call log

Every MCP tool call is logged with:

| Field | Purpose |
|---|---|
| `ts` | When the tool was called |
| `tool` | Tool name |
| `params` | Parameters (excluding ctx) |
| `mode` | summary / detail / about |
| `skill_context` | Which skill triggered this call (if available) |
| `result_total` | Total results (from summary or full count) |
| `result_returned` | Results in this response |
| `truncated` | Whether results were truncated |
| `duration_ms` | Wall-clock time |
| `error` | Error message if failed |

### Skill context propagation

To connect tool calls to the workflows that triggered them, skills
can pass a `_skill` parameter (or similar mechanism) when invoking
tools. The MCP server logs this alongside the tool call. This
allows usage analysis to distinguish "query_expression called as
step 2 of characterize-experiment" from "query_expression called
ad-hoc."

The exact mechanism (parameter, header, context variable) is an
implementation decision. The requirement is: the log should capture
both what was called and why.

### Log location

When the MCP server is remote, the log lives on the server. For
researcher-accessible analytics, options include:
- Server-side log + periodic export
- Client-side logging via Claude Code hooks
- Log endpoint on the MCP server

This is a deployment decision. The tool call logging infrastructure
should support any of these.

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
│   └── test_about_mode.py             #   About mode content lint
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

**Summary mode consistency** (`test_summary_mode.py`): For tools
with summary mode, verify that summary totals match the actual
count from detail mode. This catches drift between precomputed
stats and actual data.

**About mode content** (`test_about_mode.py`): Every tool with
about mode has content. Content mentions the tool's parameters.
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

Each tool's summary mode depends on specific properties existing in
the KG. This is documented per query builder:

```python
# queries_lib.py
def build_query_expression_summary(*, ...):
    """Build Cypher for expression summary statistics.

    Reads precomputed properties:
      Experiment.de_gene_count (int)
      Experiment.direction_breakdown (str, JSON)
      Experiment.top_categories (str, JSON)
    These are populated by the KG build pipeline.
    If not available, falls back to COUNT aggregation query.
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
- Tool response format (summary/detail/about modes)
- Truncation rules
- Package import cross-reference for full data
- Summary mode is default — use detail when you need row-level data

This is the chat-mode equivalent of the tool-wrapper skills.
Same content, different delivery surface.
