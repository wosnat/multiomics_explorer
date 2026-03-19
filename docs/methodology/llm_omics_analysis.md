# LLM-driven omics analysis: methodology

## System overview

This is a research system for multi-omics analysis of Prochlorococcus and
Alteromonas. The system components:

- **Knowledge graph** (Neo4j) — the data layer. Genes, expression,
  orthologs, ontology, publications, experiments.
- **MCP server** — structured access to the KG. Navigation, filtering,
  summarization.
- **Python/R** — computation. Statistics, enrichment, clustering,
  visualization.
- **VS Code + Claude Code** — the primary interface. An agentic LLM with
  filesystem, shell, and code execution.

The agent orchestrates the other three: it queries the KG through MCP tools,
writes data to files, runs analysis code, and produces artifacts (tables,
plots, reports). The MCP tools are not the analysis — they are the data
access layer.

The KG + MCP server is also available standalone (Claude Desktop or similar
chat interfaces) for quick exploration — browsing experiments, looking up
genes, getting summaries. This is a secondary usage mode with inherent
limitations.

---

## The fundamental tension

LLMs operate under a context window constraint. MCP tools manage this by
applying limits — return 100 rows, truncate long lists, summarize where
possible. This works well for lookup-style queries: "what is gene PMM0120?",
"what organisms are in the KG?".

Omics analysis is different. A differential expression experiment may produce
800 significant genes. Pathway enrichment requires the full gene list to be
correct. Dropping 700 genes silently produces wrong biological conclusions —
and the LLM has no way to know. The limit that protects the context window
destroys the analysis.

**The agentic mode resolves this tension** with a dual interface. The agent
uses MCP tools for reasoning (tier-1 summaries in context) and imports the
Python package in scripts for bulk data (Neo4j → file, bypassing context).
The context window holds the plan, the intermediate summaries, and the
interpretation — not the raw data.

Chat mode cannot resolve this tension — it can only manage it through
summaries and limits. This is why chat mode is suitable for exploration
but not for quantitative analysis.

---

## Client/server boundary

Understanding where things run is essential to understanding the system's
constraints.

```
┌─────────────────────────────────────────────────┐
│  Client (VS Code + Claude Code)                 │
│                                                 │
│  ┌─────────────┐   ┌──────────┐   ┌─────────┐  │
│  │ LLM context │   │ File I/O │   │ Shell / │  │
│  │   window    │   │  (Write, │   │ Python  │  │
│  │             │   │   Read)  │   │         │  │
│  └──────┬──────┘   └──────────┘   └─────────┘  │
│         │                                       │
│         │ MCP tool call (JSON-RPC)              │
│         │ → parameters in, text result out      │
│         │                                       │
├─────────┼───────────────────────────────────────┤
│         ▼                                       │
│  Server (MCP process)                           │
│                                                 │
│  ┌─────────────┐   ┌──────────┐                 │
│  │ Tool logic  │──▶│  Neo4j   │                 │
│  │ (Python)    │◀──│  driver  │                 │
│  └─────────────┘   └──────────┘                 │
│                                                 │
│  No filesystem access to client workspace       │
│  No knowledge of analyses/ directory            │
│  Returns: text/string to the LLM context        │
└─────────────────────────────────────────────────┘
```

**MCP tools cannot write files.** They return data as text to the LLM's
context window. Every MCP tool result — whether 10 rows or 10,000 —
passes through the agent's context on its way to anywhere else.

This means:
- **All file writes are agent-side.** The agent receives MCP output in
  context, then uses its filesystem tools to write it to disk. The MCP
  server never touches `analyses/`.
- **Everything through MCP transits the context window.** There is no
  way around this — it's how MCP works. Tier-1 summaries are always
  cheap (a few lines of metadata). Tier-2 detail is the variable cost,
  controlled by the `limit` parameter.

### The context transit problem

In chat mode this is the whole problem — the context window IS the only
place data can go. Limits are essential.

In agentic mode the context window is still a bottleneck for MCP data.
The agent can write to files, but it has to receive the data in context
first. Pulling full datasets through MCP wastes context on data the
agent doesn't need to reason over.

**Solution: dual interface — MCP server + Python package.**

The same functions are available two ways:

1. **MCP tools** — for the LLM's reasoning. Returns tier-1 summaries
   and tier-2 detail through context. Subject to context transit limits.
2. **Python package** — for data extraction and computation. Same
   functions, same parameters, but called directly in a script. Results
   go Neo4j → Python → file, never through LLM context.

```
Agent reasoning (in context):
  MCP query_expression(experiment_id="...", significant_only=True)
  → tier-1 summary: 823 genes, 412 up, 411 down
  → tier-2: top 100 by effect size

Bulk extraction (bypasses context):
  Agent writes a Python script:
    from multiomics_explorer import query_expression
    import csv
    results = query_expression(experiment_id="...", significant_only=True)
    # write list[dict] to CSV, or pd.DataFrame(results).to_csv(...)
  Agent runs the script → data on disk
```

The agent already knows the function name and parameters — it just used
them in the MCP call. Switching from MCP to Python import is trivial.

**Why this works:**
- Same function, same parameters, two access paths
- No Cypher exposure — the Python package handles query building
  internally, same as the MCP server
- No code injection risk — no generated code, just a function call
- The agent chooses per-call: MCP for reasoning, Python for data
- Chat mode uses MCP only (no Python access) and gets tier-1/tier-2
- Agentic mode uses both: MCP for thinking, Python for doing

### Package architecture: where tiers live

The core query functions know nothing about tiers. The MCP wrapper adds
them. The package re-exports the raw functions.

```
queries_lib.py                      The shared core
  query_expression(...)  ──────────▶  returns list[dict] (all rows)
  list_experiments(...)  ──────────▶  returns list[dict]
  search_genes(...)      ──────────▶  returns list[dict]
                                       │
                         ┌─────────────┴─────────────┐
                         │                           │
                    mcp tools.py              package API (__init__.py)
                         │                           │
                    1. call query func          re-export as-is
                    2. compute tier-1           caller gets list[dict]
                       from full results       caller does what it wants
                    3. apply limit → tier-2      (DataFrame, CSV, iterate)
                    4. format JSON response
                    5. return tier-1 + tier-2
                       + truncation metadata
```

**The function doesn't decide what to return.** It always returns
everything. The MCP wrapper is the only place that computes summaries,
applies limits, and formats for LLM consumption.

### Return type: `list[dict]`, not DataFrame

The package API returns `list[dict]` — the native format from Neo4j's
`.data()` method, and what `execute_query` already produces.

**Why not DataFrame:**

Omics data frequently has list-valued fields — a gene with multiple
GO terms, an ortholog group containing multiple locus tags, an
experiment with multiple time points. In `list[dict]` this is natural:

```python
{"gene": "PMM0120", "go_terms": ["GO:0006412", "GO:0005840"],
 "ortholog_group": "464SN@72275"}
```

In a DataFrame, list-valued cells become object-dtype columns. CSV
round-tripping breaks (lists serialize as string literals like
`"['GO:0006412', 'GO:0005840']"`), and filtering/grouping on those
columns is awkward.

**`list[dict]` is the universal interchange format.** The caller
decides what to do with it:

```python
from multiomics_explorer import query_expression

results = query_expression(experiment_id="...", significant_only=True)

# Want a DataFrame? (for flat, tabular data)
df = pd.DataFrame(results)
df.to_csv("de_genes.csv", index=False)

# Want to iterate?
for row in results:
    print(row["gene"], row["log2fc"])

# Want JSON?
json.dumps(results)

# Want to flatten nested fields first?
flat = [{"gene": r["gene"], "go_term": t}
        for r in results for t in r.get("go_terms", [])]
```

The package doesn't impose a data structure. It returns what Neo4j
gives, and the caller chooses the representation that fits their
analysis.

### Result schemas

**MCP tools** return text (JSON-formatted). MCP protocol has no result
schema mechanism — the LLM reads the output as text. The two-tier
structure (summary + rows + truncation metadata) is implicit in the
MCP wrapper's formatting. Tool docstrings describe what to expect.

**Package API** returns `list[dict]` with keys that depend on the
function. These should be documented (at minimum in docstrings), and
may benefit from TypedDict definitions for IDE support:

```python
class ExpressionResult(TypedDict):
    gene: str
    product: str
    organism_strain: str
    experiment_id: str
    direction: str
    log2fc: float
    padj: float | None
    # ...

def query_expression(...) -> list[ExpressionResult]: ...
```

This is an implementation decision — TypedDict, dataclass, or just
docstrings. The key point: the dict keys are a contract. They must
be stable across versions and documented for script authors.

### How the two callers differ

```python
# In mcp_server/tools.py (MCP wrapper):
@mcp.tool()
def query_expression(experiment_id: str, significant_only: bool = True,
                     limit: int = 100):
    # 1. Call the shared core — gets ALL results as list[dict]
    results = queries_lib.query_expression(
        experiment_id=experiment_id, significant_only=significant_only)

    # 2. Compute tier-1 from full results (always complete)
    directions = Counter(r["direction"] for r in results)
    categories = Counter(r["category"] for r in results)
    summary = {
        "total_genes": len(results),
        "direction_summary": dict(directions),
        "top_categories": dict(categories.most_common(10)),
        "truncated": len(results) > limit,
    }

    # 3. Apply limit for tier-2 (sort by |log2fc|, take top N)
    ranked = sorted(results, key=lambda r: abs(r["log2fc"]), reverse=True)
    detail = ranked[:limit]

    # 4. Format and return for LLM context
    return format_response(summary=summary, rows=detail)


# In an extraction script (package import):
from multiomics_explorer import query_expression
import pandas as pd

results = query_expression(experiment_id="...", significant_only=True)
pd.DataFrame(results).to_csv("data/de_genes.csv", index=False)
# Full data, no tiers, no limits. Caller converts to DataFrame if needed.
```

The package API (`multiomics_explorer.query_expression`) is just
`queries_lib.query_expression` re-exported. The MCP wrapper is the
only code that knows about tiers.

This is largely the existing architecture — `queries_lib.py` already
builds queries, `tools.py` already wraps them. The change is making
the package API explicitly public and documented for direct use.

### How the agent knows what to expect

The two interfaces return different formats by design. The agent needs
to be told this exists and when to use each. But different agents see
different documentation depending on where they're running.

**Three documentation surfaces, three audiences:**

```
┌────────────────────────────────────────────────────────┐
│ MCP server instructions (FastMCP `instructions` param) │
│                                                        │
│ Seen by: EVERY MCP client (Claude Desktop, any agent   │
│ with the MCP server configured, chat mode)             │
│                                                        │
│ Content:                                               │
│ - Response format: summary + detail + truncation       │
│ - Don't count from truncated lists, use metadata       │
│ - Tier-1 is always complete regardless of limit        │
│ - MCP tools always apply a limit (default 100)         │
│ - For full datasets in scripts: pip install the        │
│   package, import functions directly                   │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│ MCP tool docstrings (per-tool)                         │
│                                                        │
│ Seen by: EVERY MCP client                              │
│                                                        │
│ Content (example for query_expression):                │
│ - What the tool returns and when to use it             │
│ - "Returns summary (complete) + top N rows (limited)"  │
│ - "For full results in a script:                       │
│    from multiomics_explorer import query_expression"   │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│ Repo CLAUDE.md                                         │
│                                                        │
│ Seen by: Claude Code working INSIDE this repo only     │
│                                                        │
│ Content:                                               │
│ - Full dual-interface methodology                      │
│ - MCP for reasoning, package import for data           │
│ - analyses/ directory structure and conventions        │
│ - Workflow patterns (MCP → script → analyze)           │
│ - When to use each interface                           │
└────────────────────────────────────────────────────────┘
```

**The split:**

**MCP server instructions** carry the full dual-interface contract.
This is what every client sees — including agents in other repos who
`pip install multiomics-explorer` and configure the MCP server. This
is the primary documentation surface for external users.

Should include:
- Response format: summary + detail + truncation metadata
- Don't count from truncated lists — use `total` from metadata
- Tier-1 summary is always computed over ALL results
- For full datasets: import the package in a script
  (`from multiomics_explorer import query_expression` → list[dict])
- Same functions, same parameters, different return format

**MCP tool docstrings** reinforce per-tool: what it returns, and the
package import cross-reference.

**Repo CLAUDE.md** adds project-specific methodology: `analyses/`
directory conventions, workflow patterns, file organization. Only
relevant when working inside this repo.

**What each audience gets:**

| Audience | Sees | Gets |
|---|---|---|
| Chat user (Claude Desktop) | MCP instructions + docstrings | Full response contract. Package hint visible but not actionable. |
| Agent in their own repo + MCP | MCP instructions + docstrings | Full dual-interface contract. Can import package in scripts. |
| Agent in this repo (CC) | All three | Full methodology + project conventions |

The key insight: **MCP server instructions are the portable
documentation.** They travel with the MCP server wherever it's
configured. A user who `pip install`s the package and adds it to
their `.mcp.json` gets the full dual-interface guidance automatically
— no need to copy CLAUDE.md content.

Repo CLAUDE.md is only for repo-specific conventions that don't
apply to external users (directory structure, analysis workflow
patterns). It should reference the methodology doc for the full
picture, not duplicate the MCP instructions.

### MCP server instructions draft

```python
# In server.py:
mcp = FastMCP(
    "multiomics-kg",
    instructions="""
Multi-omics knowledge graph for Prochlorococcus and Alteromonas.

## Response format

Tools that return large result sets (query_expression, search_genes,
genes_by_ontology) use a two-tier response:

- **Summary**: total counts, direction breakdown, top categories.
  Computed over ALL matching results, always complete regardless of
  limit. Use this for quantitative questions.
- **Detail**: top N rows by effect size (controlled by `limit`
  parameter). May be truncated.
- **Metadata**: `total`, `returned`, `truncated` fields.

IMPORTANT: If `truncated: true`, do NOT count rows to answer "how
many" questions. Use the `total` field from metadata.

## Dual data access

These tools are also available as a Python package. If you have code
execution capability (Claude Code, agentic frameworks):

    pip install multiomics-explorer

    from multiomics_explorer import query_expression
    import pandas as pd
    results = query_expression(experiment_id="...", significant_only=True)
    pd.DataFrame(results).to_csv("de_genes.csv", index=False)

Same functions, same parameters. MCP tools return formatted text
with summaries and limits. The package returns list[dict]
with all rows, no limits.

Use MCP tools for reasoning (exploring, navigating, summarizing).
Use the package import in scripts for bulk data (enrichment,
clustering, export, plotting) — data goes directly to file without
passing through your context window.
""",
)
```

---

## The agentic analysis stack

### Layer 1: Data access (dual interface)

The same query functions are available two ways:

**MCP tools** — for the agent's reasoning. Return tier-1 summaries and
tier-2 detail through the LLM context. Subject to context window limits.
Used for navigation, exploration, and deciding what to analyze.

**Python package** — for bulk data extraction. Same functions, same
parameters, called directly in scripts. Results go Neo4j → Python → file,
bypassing the LLM context entirely. Used when the agent needs full
datasets for computation.

Both access the same KG through the same query logic.

### Layer 2: Data staging (filesystem)

The agent writes query results to files when:
- The result set is too large for useful context-window reasoning
- The data will be consumed by a Python/R script
- The results need to persist beyond the conversation
- Multiple queries need to be combined for analysis

For bulk extraction, scripts import the Python package directly and
write to files — data never enters the LLM context. For small results,
the agent can write MCP output to files from context.

### Layer 3: Computation (Python/R)

Statistical tests, enrichment analysis, clustering, set operations,
visualization. The agent writes and executes code that operates on staged
data files and can also import the package directly for additional
queries during computation.

This is where scientific rigor lives. The package provides correct,
complete data. Python provides correct, reproducible analysis. The agent
connects them.

### Layer 4: Interpretation (LLM reasoning)

The agent reads computation outputs (statistics, plots, tables) and
provides biological interpretation. This is what the LLM is uniquely
good at — synthesizing results into narrative, connecting findings to
biological context, suggesting follow-up analyses.

### How the layers interact

**Simple lookup** — MCP only, no files:
```
User: "What is PMM0120?"
    → MCP gene_overview → agent interprets → response
```

**Exploratory analysis** — MCP summaries, no bulk data:
```
User: "What happens when you starve MED4 of nitrogen?"
    → MCP list_experiments → MCP query_expression (tier-1 + tier-2)
    → agent interprets summaries + top hits → response
```

**Quantitative analysis** — MCP for reasoning, Python package for data:
```
User: "What pathways are enriched under nitrogen stress?"
    → MCP query_expression (tier-1 summary)         agent reasons
    → agent writes script: import multiomics_explorer   Neo4j → CSV
    → agent writes analysis script                   CSV → stats + plots
    → agent reads results, interprets                → response + artifacts
```

The key insight: **MCP and Python package both call the same query
functions**, but for different purposes. MCP formats results for the
agent's context window (tier-1/tier-2). The Python package returns raw
data for scripts to write to files. Data for computation never needs to
pass through the LLM context.

---

## MCP tool design principles

These principles govern how MCP tools return data, with the agentic
workflow as the primary design target.

### 1. Two-tier response: summary + detail

Every tool that queries potentially large result sets returns both:

**Tier 1: Complete summary** — computed server-side over ALL matching data,
regardless of limits.

```
metadata:
  total_genes: 823
  significant_genes: 823
  direction_summary: {up: 412, down: 411}
  top_categories: [{category: "photosynthesis", count: 45}, ...]
  time_points_covered: ["1h", "2h", "4h", "8h"]
  truncated: true
```

**Tier 2: Representative detail** — limited subset, ordered by effect size.

```
rows: [...first 100 genes by |log2FC|...]
```

The agent uses tier-1 to reason about what to do next. It uses tier-2 for
quick inspection. When it needs the full dataset, it imports the package
in a script (see "Dual interface for data access" below).

In chat mode, tier-1 is the answer for quantitative questions. Tier-2
provides examples to cite. The combination is the best a context-limited
LLM can do.

### 2. Explicit incompleteness

When results are truncated, the tool must say so:

- `total`: how many results exist
- `returned`: how many are in this response
- `truncated`: boolean

The agent uses this to decide: is tier-2 sufficient, or should it use
the package import for full data?

### 3. Dual interface for data access

MCP tools are for reasoning — tier-1 summaries and tier-2 samples in
context. The Python package is for data — same functions, same
parameters, called in a script that writes directly to file. No
`limit=0` on MCP tools. The escape hatch is the other interface.

`run_cypher` is available for ad-hoc queries that don't map to an
existing function — through MCP (with limit) for exploration, or as
a package import for bulk extraction.

### 4. Narrow then deep

The default workflow:
1. **Browse** — navigation tools to understand what data exists
2. **Narrow** — filter to a specific experiment, gene set, or condition
3. **Deep dive** — pull detailed or full results for the narrowed scope

### 5. Tool chains over monolithic queries

No single tool call should need to return thousands of rows when a
two-step chain avoids it:

- `genes_by_ontology("photosynthesis")` → 45 gene IDs
- `query_expression(gene_ids=[...], experiment_id="...")` → 45 rows

---

## File organization

The agentic workflow produces files at every stage — data pulled from the
KG, scripts that analyze it, outputs from those scripts, and write-ups
that interpret the results. These live in the project tree alongside the
code.

### Directory structure

```
multiomics_explorer/
├── analyses/                          # all analysis work
│   ├── {analysis_name}/               # one directory per analysis
│   │   ├── data/                      #   staged data from MCP/KG
│   │   ├── scripts/                   #   Python/R analysis scripts
│   │   ├── results/                   #   outputs: tables, plots, stats
│   │   └── README.md                  #   what question, what conclusion
│   └── ...
├── docs/
│   ├── analysis/                      # polished analysis write-ups
│   │   └── catalase_expression.md     #   (existing)
│   └── methodology/                   # this document and friends
└── ...
```

### `analyses/` — the working directory

Each analysis gets its own directory named for the question or topic:

```
analyses/
├── med4_nitrogen_response/
│   ├── data/
│   │   ├── de_genes.csv               # full DE gene list from KG
│   │   └── go_terms.csv               # GO annotations for DE genes
│   ├── scripts/
│   │   ├── enrichment.py              # GO enrichment (Fisher's exact)
│   │   └── volcano.py                 # volcano plot
│   ├── results/
│   │   ├── enrichment_results.csv     # enriched GO terms with p-values
│   │   ├── volcano_plot.png           # volcano plot
│   │   └── summary_stats.json         # total DE, up/down counts, etc.
│   └── README.md
├── photosynthesis_n_vs_light/
│   ├── data/
│   │   ├── n_stress_de.csv
│   │   └── light_stress_de.csv
│   ├── scripts/
│   │   └── compare_enrichment.py
│   ├── results/
│   │   ├── enrichment_comparison.csv
│   │   └── comparison_plot.png
│   └── README.md
└── catalase_coculture_timecourse/
    ├── data/
    │   └── catalase_timecourse.csv
    ├── scripts/
    │   └── trajectory_plot.py
    ├── results/
    │   └── catalase_trajectories.png
    └── README.md
```

**Naming:** Short, descriptive, snake_case. The name should tell you
the question, not the date. If the same question is revisited, update
the existing directory.

**`data/`** — raw data extracted from the KG via package import. CSVs
with clear column headers. These are inputs to analysis scripts, not
final outputs. Extraction scripts write these; analysis scripts read
them.

**`scripts/`** — standalone Python/R scripts that perform the analysis.
Each script reads from `data/`, writes to `results/`. Scripts should be
re-runnable without the agent — a researcher can `python scripts/enrichment.py`
to verify or modify the analysis.

**`results/`** — outputs from scripts. Tables (CSV), plots (PNG/SVG),
statistics (JSON). These are the artifacts the researcher cares about.

**`README.md`** — what question was asked, what data was used, what the
conclusion was. Brief — the scripts and results speak for themselves.

### `docs/analysis/` — polished write-ups

When an analysis is mature enough to document, the write-up goes in
`docs/analysis/`. These are narrative documents that reference the
`analyses/` artifacts but stand on their own. The existing
`catalase_expression.md` is an example.

Not every analysis gets a write-up. `analyses/` is the working bench;
`docs/analysis/` is the publication shelf.

### What goes in `.gitignore`

Large intermediate data files (if any exceed a few MB) should be
gitignored. Analysis scripts and results should be committed — they're
the reproducible record.

```
# Large intermediate data
analyses/*/data/*.parquet
```

### What the agent should do

When starting an analysis:
1. Create `analyses/{analysis_name}/` with `data/`, `scripts/`,
   `results/` subdirectories
2. Write extraction script (imports package, writes to `data/`)
3. Write analysis scripts to `scripts/`
4. Run scripts, outputs land in `results/`
5. Write `README.md` summarizing the analysis

When revisiting an analysis:
- Check if `analyses/{topic}/` already exists
- Update or extend rather than creating a parallel directory

---

## Analysis workflow patterns

Multi-step patterns for common omics analysis tasks. These describe the
full agentic workflow, noting where chat mode diverges.

### Pattern: Experiment characterization

> "What happens when you starve MED4 of nitrogen?"

```
analyses/med4_nitrogen_response/
├── data/
│   ├── de_genes.csv                  # step 3
│   └── go_annotations.csv            # step 3b
├── scripts/
│   ├── enrichment.py                 # step 4
│   └── volcano.py                    # step 4
├── results/
│   ├── enriched_go_terms.csv         # step 4 output
│   ├── volcano_plot.png              # step 4 output
│   └── summary_stats.json            # step 4 output
└── README.md                         # step 5
```

1. `list_experiments(organism="MED4", condition_type="nitrogen_stress")`
   → find relevant experiment IDs
2. `query_expression(experiment_id="...", significant_only=True)`
   → tier-1 summary for reasoning (total genes, direction split,
   top categories), tier-2 for quick inspection of top hits
3. Write and run `scripts/extract_data.py`: imports `multiomics_explorer`
   package → queries Neo4j directly → `data/de_genes.csv`,
   `data/go_annotations.csv` (bypasses LLM context entirely)
4. Write and run `scripts/enrichment.py`: reads `data/`, Fisher's exact
   test against KG gene universe → `results/enriched_go_terms.csv`
   Write and run `scripts/volcano.py` → `results/volcano_plot.png`
5. Write `README.md`: biological narrative from enrichment results + top hits

*Chat mode stops at step 2.* Describes the response from tier-1 statistics
and tier-2 examples. Qualitative, not quantitative.

### Pattern: Gene-centric survey

> "How does PMM0120 respond across all stress conditions?"

1. `query_expression(gene_ids=["PMM0120"], significant_only=False)`
   → all experiments where PMM0120 has results
2. Result set is inherently small — no truncation, no file staging needed
3. Interpret directly from the response

Both modes handle this identically. Gene-centric queries are naturally
small. No tension.

### Pattern: Comparative pathway analysis

> "Is photosynthesis more affected by nitrogen stress or light stress?"

```
analyses/photosynthesis_n_vs_light/
├── data/
│   ├── n_stress_de.csv
│   └── light_stress_de.csv
├── scripts/
│   └── compare_enrichment.py
├── results/
│   ├── enrichment_comparison.csv
│   └── comparison_barplot.png
└── README.md
```

1. `list_experiments` for each condition → experiment IDs
2. `query_expression` for each → tier-1 summaries for reasoning
3. Write and run `scripts/extract_data.py`: imports package, queries
   Neo4j for both experiments → `data/n_stress_de.csv`,
   `data/light_stress_de.csv`
4. Write and run `scripts/compare_enrichment.py`: Fisher's exact on
   photosynthesis genes per condition → `results/enrichment_comparison.csv`,
   `results/comparison_barplot.png`
5. `README.md`: "photosynthesis genes are 3.2x enriched under N stress
   (p=0.002) vs 1.4x under light stress (p=0.12, n.s.)"

*Chat mode does steps 1–2 only.* Compares tier-1 category counts
qualitatively: "photosynthesis appears more affected by nitrogen."

### Pattern: Ortholog conservation

> "Is the nitrogen response conserved across Prochlorococcus strains?"

```
analyses/n_response_conservation/
├── data/
│   └── ortholog_expression.csv
├── scripts/
│   └── conservation_analysis.py
├── results/
│   ├── conservation_scores.csv
│   └── conservation_heatmap.png
└── README.md
```

1. `query_expression(gene_ids=[...], include_orthologs=True,
   condition_type="nitrogen_stress")` → tier-1 per-organism summary
2. Write and run `scripts/extract_data.py`: imports package, queries
   Neo4j for full ortholog × experiment matrix →
   `data/ortholog_expression.csv`
3. Write and run `scripts/conservation_analysis.py`: conservation score
   per ortholog group (fraction of strains with significant same-direction
   response) → `results/conservation_scores.csv`,
   `results/conservation_heatmap.png`
4. `README.md`: which functional groups are conserved vs strain-specific

### Pattern: Time-course trajectory

> "How does the stress response unfold over time?"

```
analyses/n_starvation_timecourse/
├── data/
│   └── timecourse_de.csv
├── scripts/
│   ├── cluster_trajectories.py
│   └── heatmap.py
├── results/
│   ├── gene_clusters.csv
│   ├── trajectory_heatmap.png
│   └── cluster_summary.json
└── README.md
```

1. `list_experiments(time_course_only=True, condition_type="...")`
2. `query_expression(experiment_id="...", significant_only=True)`
   → tier-1 per-time-point summary (gene counts evolving over time)
3. Write and run `scripts/extract_data.py`: imports package, full
   time-course from Neo4j → `data/timecourse_de.csv`
4. Write and run `scripts/cluster_trajectories.py`: k-means on
   fold-change trajectories → `results/gene_clusters.csv`
   Write and run `scripts/heatmap.py` → `results/trajectory_heatmap.png`
5. `README.md`: temporal waves of the stress response, early vs late
   responders

### Pattern: Publication-ready export

> "Generate a supplementary table of all DE genes"

```
analyses/supplementary_tables/
├── data/
│   ├── de_genes_raw.csv
│   └── ortholog_annotations.csv
├── scripts/
│   └── format_table.py
└── results/
    └── table_S1_de_genes.tsv
```

1. Write and run `scripts/extract_data.py`: imports package, full DE
   results + ortholog annotations from Neo4j → `data/de_genes_raw.csv`,
   `data/ortholog_annotations.csv`
2. Write and run `scripts/format_table.py`: merge, format standard
   column headers → `results/table_S1_de_genes.tsv`

Chat mode cannot do this.

---

## What the agent should NOT do

- **Count genes from a truncated list.** If `truncated: true`, use
  `total` from metadata, not `len(rows)`.
- **Infer absence from a truncated list.** "Not in tier-2" ≠ "not DE."
  Query specifically for the gene.
- **Aggregate in context when tier-1 has the answer.** Don't pull full
  data just to count categories — the tier-1 summary already has this.
- **Skip the computation layer.** When making quantitative claims (fold
  enrichment, p-values, conservation scores), run the statistics in
  Python. Don't eyeball numbers from tier-2 and call it analysis.
- **Treat MCP tool output as the final analysis.** MCP provides data.
  Python provides analysis. The agent interprets. Conflating these
  layers produces bad science.

---

## Chat mode: scope and limitations

The KG + MCP server is also available via chat interfaces (Claude Desktop,
etc.) without the agentic stack. In this mode:

**Suitable for:**
- Browsing: "What experiments exist for MED4?"
- Lookup: "What is the function of PMM0120?"
- Targeted comparison: "Is PMM0120 upregulated under nitrogen stress?"
- Tier-1 summaries: "How many genes respond to coculture?"
- Guiding exploration: "What should I look at next?"

**Not suitable for:**
- Quantitative enrichment analysis
- Full gene list export
- Multi-experiment meta-analysis
- Anything requiring statistical rigor beyond what tier-1 provides
- Producing artifacts (files, plots)

The tier-1 summary is the ceiling of what chat mode can do for
quantitative questions. It's designed to be as informative as possible
within that constraint, but researchers should use the agentic system
for real analysis.

---

## Roadmap

### Phase 1: Build (now)

KG redesign (expression edges, Experiment node) + MCP tools + Python
package API. All in this repo + the KG repo. Local Neo4j, local
everything.

**Deliverables:**
- KG with Experiment nodes, `Changes_expression_of` edges, time-course
  support, EnvironmentalCondition absorbed into Experiment
- MCP tools: list_publications, list_experiments, query_expression
  (redefined), remove compare_conditions
- Python package API: same functions as MCP, returning list[dict]
- MCP server instructions with dual-interface guidance
- Tier-1/tier-2 response pattern in MCP tools
- Updated CLAUDE.md for this repo

**Not yet:** MCP prompts, skills, init-claude, cloud deployment,
pip packaging. These depend on learning from phase 2.

### Phase 2: Stress test (weeks after phase 1)

New local repo, separate from this one. Use Claude Code as the
researcher — real analysis questions against the KG. Combination of:
- Exercising MCP tools for exploration and reasoning
- Writing extraction + analysis scripts using the package API
- Testing the dual-interface workflow end to end
- Identifying where the methodology works and where it breaks
- Defining analysis patterns that become prompts/skills later
- Enable usage logging (see below) to capture tool call patterns

**This phase produces:**
- Validated (or revised) workflow patterns
- Real analysis examples that inform prompt/skill design
- Bug reports and API friction points
- The `analyses/` directory convention, tested in practice
- Methodology refinements to this document
- Baseline usage data for evaluation framework design

### Phase 3: Deploy to researchers (April–May 2026)

KG on Neo4j cloud. Package published via pip. 3–4 researchers
install and use it in their own projects with Claude Code.

**Deliverables:**
- Neo4j Aura instance with read-only user
- `pip install multiomics-explorer` (PyPI or private index)
- MCP prompts shipping with the server (informed by phase 2)
- `multiomics-explorer init-claude` command (skills, CLAUDE.md
  snippet, .mcp.json scaffolding)
- Usage logging enabled by default (local JSONL file)
- Onboarding docs

**Researchers provide:**
- Real-world stress testing across different research questions
- Feedback on workflow patterns, tool ergonomics, documentation
- Methodology refinements — what works, what's missing
- Analysis examples that further refine prompts and skills
- Usage logs (shared voluntarily) for evaluation

### Phase 4: Production deploy

Incorporate feedback from phase 3. Stabilize API, prompts, skills.
Formalize evaluation framework from accumulated usage data.
Broader release.

---

## Deployment architecture

### What ships

One installable package, multiple interfaces:

1. **`multiomics-explorer` Python package** — the core library.
   Query functions, Neo4j connection, data models. Usable as a
   direct Python import in scripts and notebooks.
2. **`multiomics-kg-mcp` MCP server** — wraps the package functions
   for LLM access. Adds tier-1/tier-2 formatting, limits, truncation
   metadata. Includes MCP prompts for guided workflows.
3. **`multiomics-explorer init-claude`** CLI command — scaffolds
   Claude Code integration into the user's project (skills, CLAUDE.md
   snippet, .mcp.json).

All installed together (`pip install multiomics-explorer` or `uv sync`).

### Workflow distribution: MCP prompts + Claude Code skills (phase 3)

Analysis workflow patterns are distributed at two levels. These are
designed now but built after phase 2 validates the patterns.

**MCP prompts — available to every client, automatically.**

MCP protocol supports server-defined prompts — predefined templates
that any client can discover and invoke. They ship with the MCP server,
no setup needed.

```python
# In server.py:
@mcp.prompt()
def characterize_experiment(experiment_id: str):
    """Characterize the transcriptional response of an experiment.
    Produces a summary, enrichment analysis, and volcano plot."""
    return f"""Characterize experiment {experiment_id}:

1. Call query_expression(experiment_id="{experiment_id}",
   significant_only=True) for tier-1 summary.
2. If you have code execution: write a script that imports
   multiomics_explorer.query_expression to extract full data,
   then run GO enrichment (Fisher's exact) and generate a
   volcano plot.
3. If chat only: interpret the tier-1 summary and tier-2 top
   hits. Note any truncation.
4. Report: total DE genes, direction split, top enriched
   categories, notable genes."""

@mcp.prompt()
def compare_conditions(condition_a: str, condition_b: str,
                       organism: str | None = None):
    """Compare transcriptional responses between two conditions."""
    return f"""Compare {condition_a} vs {condition_b}:
    ..."""

@mcp.prompt()
def gene_survey(gene_id: str):
    """Survey a gene's response across all experiments."""
    return f"""Survey {gene_id} across all conditions:
    ..."""
```

Prompts are mode-aware — they include both the chat path ("interpret
tier-1") and the agentic path ("write a script"). The LLM follows
whichever it can execute.

**MCP prompts shipped with the server:**

| Prompt | Pattern | Needs code execution? |
|---|---|---|
| `characterize_experiment` | Experiment characterization | Optional (richer with) |
| `compare_conditions` | Comparative pathway analysis | Optional |
| `gene_survey` | Gene-centric survey | No |
| `ortholog_conservation` | Ortholog conservation | Yes |
| `timecourse_analysis` | Time-course trajectory | Yes |
| `export_de_genes` | Publication-ready export | Yes |

**Claude Code skills — for agentic users, via `init-claude`.**

Skills are project-local (`.claude/skills/`). They don't travel with
pip install. Users get them by running:

```bash
multiomics-explorer init-claude
```

This creates:

```
.claude/
├── skills/
│   ├── characterize-experiment.md
│   ├── compare-conditions.md
│   ├── gene-survey.md
│   ├── ortholog-conservation.md
│   ├── timecourse-analysis.md
│   └── export-de-genes.md
├── CLAUDE.md (snippet appended or created)
└── (existing settings preserved)

.mcp.json (created if not present)
```

Skills are more structured than MCP prompts — they include specific
file paths, directory conventions, and step-by-step instructions
tailored to Claude Code's tool set. They reference the `analyses/`
directory pattern.

Example skill (`characterize-experiment.md`):

```markdown
---
name: characterize-experiment
description: Full characterization of a DE experiment
---

# Characterize experiment

Given an experiment ID, produce a full characterization:

## Steps

1. MCP: `list_experiments` to confirm experiment exists and get metadata
2. MCP: `query_expression(experiment_id=$EXPERIMENT_ID,
   significant_only=True)` — read tier-1 summary, note total genes
   and direction split
3. Create `analyses/{experiment_name}/` with data/, scripts/, results/
4. Write `scripts/extract_data.py`:
   ```python
   from multiomics_explorer import query_expression
   import pandas as pd
   results = query_expression(experiment_id="$EXPERIMENT_ID",
                              significant_only=True)
   pd.DataFrame(results).to_csv("data/de_genes.csv", index=False)
   ```
5. Run the extraction script
6. Write `scripts/enrichment.py` — Fisher's exact test on GO categories
7. Write `scripts/volcano.py` — volcano plot from de_genes.csv
8. Run both analysis scripts
9. Read results, write README.md with biological interpretation
```

**Why both:** MCP prompts are the baseline — they work for every
client (Claude Desktop, any agentic framework, any MCP-compatible
tool) with zero setup. Skills are the power layer — structured
multi-step workflows with file conventions, specific to Claude Code
agentic use. A user who only configures the MCP server gets prompts.
A user who runs `init-claude` gets skills on top.

### The `init-claude` command (phase 3)

```bash
$ multiomics-explorer init-claude

Created .mcp.json with multiomics-kg MCP server config
Created .claude/skills/ with 6 analysis workflow skills
Appended KG dual-interface guidance to CLAUDE.md

To complete setup:
  - Add Neo4j credentials to .env:
    NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
    NEO4J_USER=reader
    NEO4J_PASSWORD=<password>
  - Or set them in .mcp.json env block

Available skills:
  /characterize-experiment  — Full DE experiment characterization
  /compare-conditions       — Cross-condition pathway comparison
  /gene-survey              — Gene response across all experiments
  /ortholog-conservation    — Cross-strain conservation analysis
  /timecourse-analysis      — Time-course clustering and visualization
  /export-de-genes          — Publication-ready supplementary tables
```

Idempotent — safe to run multiple times. Preserves existing config.
Updates skills to latest version from the installed package.

### Authentication

Single read-only Neo4j user for the cloud KG. All users share the
same credentials. This is published research data — there's nothing
to protect beyond preventing writes (which the Neo4j user role
enforces).

Credentials in `.env` or environment variables:
```
NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
NEO4J_USER=reader
NEO4J_PASSWORD=<read-only-password>
```

The read-only user is configured on Neo4j Aura with the `reader` role.
Write operations are blocked at the database level — the `run_cypher`
MCP tool's write-blocking is defense in depth, not the primary control.

### Agentic setup (VS Code + Claude Code)

```
User's machine                           Cloud
├── VS Code + Claude Code          ┌──────────────┐
├── MCP server (local, stdio) ────▶│  Neo4j Aura  │
├── Python scripts (import pkg) ──▶│  (read-only) │
└── .env (shared credentials)      └──────────────┘
```

User installs the package and configures the MCP server. Both MCP and
scripts use the same `connection.py` → same `.env` credentials.

**`.mcp.json`** at project root (VS Code convention):

```json
{
  "mcpServers": {
    "multiomics-kg": {
      "command": "uv",
      "args": ["run", "multiomics-kg-mcp"],
      "env": {
        "NEO4J_URI": "neo4j+s://xxxx.databases.neo4j.io",
        "NEO4J_USER": "reader",
        "NEO4J_PASSWORD": "<read-only-password>"
      }
    }
  }
}
```

Or credentials in `.env` (gitignored), and `.mcp.json` without the
`env` block.

The agent has the full stack:
- MCP tools for reasoning (tier-1/tier-2 in context)
- Python package for bulk data (import in scripts, write to files)
- Shell for running analysis scripts

### Chat-mode setup (Claude Desktop, etc.)

Same `.mcp.json` / MCP config, same local installation. The user
gets MCP tools only — no scripts, no filesystem, no Python execution.
Tier-1 summaries and tier-2 detail are the ceiling.

Works for exploration, lookups, and qualitative summaries. Not for
quantitative analysis.

### Future: remote MCP for zero-install access (phase 4+)

A remote MCP server (SSE / streamable HTTP) could serve chat-mode
users who don't want to install anything. They get exploration access
by pointing Claude Desktop at a URL.

Agentic users still install locally — they need the Python package
for direct imports regardless. The remote MCP server is a convenience
for lightweight access, not a replacement for the local installation.

---

## Usage logging and evaluation

### Why capture usage

The system is a research tool — its value depends on whether it helps
researchers answer real questions. We need to learn:

- Which tools are useful and which are never called
- What parameter combinations are common (informs defaults and tier-1
  summary design)
- What workflows emerge (informs prompt and skill design)
- Where the system fails (truncation surprises, missing data, wrong
  results)
- How tool design changes affect usage over time

This isn't analytics for a product — it's instrumentation for a
research system that's co-evolving with its users.

### What to capture

#### MCP tool call log (passive, automatic)

Every MCP tool call is logged to a local JSONL file. No infrastructure
needed — the MCP server writes one line per call.

```jsonl
{"ts": "2026-05-01T14:23:01Z", "tool": "query_expression", "params": {"experiment_id": "doi:10.1038/...", "significant_only": true, "limit": 100}, "result_total": 823, "result_returned": 100, "truncated": true, "duration_ms": 340, "error": null}
{"ts": "2026-05-01T14:23:15Z", "tool": "search_genes", "params": {"search_text": "photosystem"}, "result_total": 12, "result_returned": 10, "truncated": true, "duration_ms": 120, "error": null}
{"ts": "2026-05-01T14:24:02Z", "tool": "query_expression", "params": {"gene_ids": ["PMM0120"]}, "result_total": 8, "result_returned": 8, "truncated": false, "duration_ms": 95, "error": null}
{"ts": "2026-05-01T14:25:30Z", "tool": "resolve_gene", "params": {"identifier": "fake_gene"}, "result_total": 0, "result_returned": 0, "truncated": false, "duration_ms": 45, "error": null}
{"ts": "2026-05-01T14:26:01Z", "tool": "run_cypher", "params": {"query": "MATCH ..."}, "result_total": null, "result_returned": 25, "truncated": null, "duration_ms": 200, "error": "write operations are not allowed"}
```

**Fields per entry:**

| Field | Type | Meaning |
|---|---|---|
| `ts` | ISO timestamp | When the tool was called |
| `tool` | str | Tool name |
| `params` | dict | Parameters passed (excluding ctx) |
| `result_total` | int \| null | Total results before limit (from tier-1) |
| `result_returned` | int | Results returned to the LLM |
| `truncated` | bool \| null | Whether results were truncated |
| `duration_ms` | int | Wall-clock time for the call |
| `error` | str \| null | Error message if the call failed |

**What this tells you:**

| Pattern | Signal |
|---|---|
| Tool X is never called | Tool is undiscoverable or unnecessary |
| Tool X always called with same params | Defaults are wrong, or a prompt/skill should encode this |
| Same tool called twice in a row with different params | First call didn't return what was needed — filter or default issue |
| `truncated: true` on most calls | Limit too low, or tier-1 summary isn't sufficient |
| `run_cypher` called frequently | Structured tools don't cover common queries |
| High `duration_ms` | Query needs optimization |
| `error` spikes | Something broke |
| Tool A always followed by tool B | Workflow pattern → candidate for a prompt/skill |

#### Analysis artifacts (passive, already captured)

The `analyses/` directory structure captures what the agent produced:
- `scripts/` — what analysis was run
- `data/` — what data was extracted
- `results/` — what outputs were generated
- `README.md` — what the question was and what was concluded

This is a retrospective record of successful analyses. No additional
logging needed — the artifacts speak for themselves.

#### Researcher feedback (lightweight, explicit)

For phase 3, researchers can flag issues in a simple format. A
`feedback.yaml` file in their project or analysis directory:

```yaml
- date: 2026-05-15
  tool: query_expression
  issue: tier-1 summary didn't include time-point breakdown
  severity: minor
  context: was looking at a time-course experiment

- date: 2026-05-16
  workflow: characterize-experiment
  issue: enrichment script failed because GO terms had no genes
  severity: major
  context: Alteromonas gene with sparse annotation
```

Low friction — the researcher (or agent) appends a YAML entry when
something doesn't work. Better than nothing, worse than automatic.

### What NOT to capture

- **Full MCP response text** — too large, contains research data.
  The structured log fields (total, returned, truncated) capture
  what matters.
- **Conversation content** — Claude Code conversations are the
  researcher's work. Don't capture them without explicit consent.
- **Package API calls** — scripts run independently, adding
  logging to every function call is intrusive. Capture tool usage
  patterns at the MCP level; the package API is for computation.
- **Neo4j query logs** — available from Neo4j itself if needed for
  performance debugging, but not part of the evaluation framework.

### From logs to evaluation

The usage log is raw data. Turning it into evaluation requires
analysis — which is itself a research question for the system.

**Phase 2** (local stress test): Review your own usage logs. Which
tools did you call most? Where did you reach for `run_cypher`? Where
did you retry with different params? These patterns inform tool
redesign and prompt/skill creation.

**Phase 3** (researcher deploy): Collect usage logs from consenting
researchers. Analyze in aggregate:

- Tool usage distribution → which tools matter
- Workflow sequences → which prompts/skills to build
- Truncation frequency → are limits right
- Error frequency per tool → reliability issues
- `run_cypher` usage → missing structured tools
- Time-to-result per workflow → where is friction

**Phase 4** (production): Formalize into a recurring evaluation:

- Curated eval cases from real researcher questions (extending
  `cases.yaml`)
- Automated checks: does the system still answer these questions
  correctly after a tool/KG change?
- Usage dashboards if the user base grows

### Implementation

**Phase 1:** Add the JSONL logging to `mcp_server/tools.py`. A
decorator or helper that wraps each tool call:

```python
def _log_call(tool_name, params, result_total, result_returned,
              truncated, duration_ms, error=None):
    entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "tool": tool_name,
        "params": params,
        "result_total": result_total,
        "result_returned": result_returned,
        "truncated": truncated,
        "duration_ms": duration_ms,
        "error": error,
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")
```

`LOG_PATH` defaults to `~/.multiomics_explorer/usage.jsonl`.
Configurable via environment variable. Can be disabled with
`MULTIOMICS_LOG=false`.

**Phase 2:** Use it yourself. Analyze with pandas.

**Phase 3:** Ships enabled by default. Researchers can disable.
Log stays local — researchers share voluntarily.

---

## Open questions

### MCP tool design

- **Enrichment as an MCP tool:** The agentic mode can run enrichment in
  Python. But a server-side enrichment tool (hypergeometric test against
  KG gene universe) would be faster, available in chat mode, and ensure
  the correct background set. Worth building?

- **Adaptive defaults:** Should the default `limit` differ by query
  shape? Gene-centric queries are naturally small. Experiment-centric
  queries can be huge. Auto-adjusting the default limit based on the
  query parameters could help both modes.

### Agentic workflow

- **Analysis templates as library modules:** Skills guide the agent
  through workflow steps, but the agent still writes analysis scripts
  (enrichment, clustering, volcano plots) from scratch each time.
  Should common analysis functions live in the package as importable
  modules (e.g., `multiomics_explorer.analysis.enrichment`)? The
  agent would import them in scripts rather than reimplementing.
  More reliable, but less flexible.

### Resolved

- **CLAUDE.md guidance:** Five surfaces — MCP server instructions (all
  clients), tool docstrings (all clients), MCP prompts (all clients),
  Claude Code skills (via `init-claude`), repo CLAUDE.md (in-repo only).
  See "How the agent knows what to expect" and "Workflow distribution."

- **Workflow distribution:** MCP prompts as portable baseline + Claude
  Code skills via `init-claude` for power users. See "Workflow
  distribution" section.
