# LLM-driven omics analysis: methodology

## System overview

A research system for multi-omics analysis of Prochlorococcus and
Alteromonas. The components:

- **Knowledge graph** (Neo4j) — the data layer. Genes,
  expression, orthologs, ontology, publications, experiments.
  Includes precomputed summary statistics for cheap access.
- **MCP server** (remote) — structured, composable access to the KG.
  Navigation, filtering, summarization. Narrow scope per tool,
  designed for chaining.
- **Python package** (local install) — same query functions as MCP,
  returning complete data as `list[dict]`. For bulk extraction and
  computation in scripts.
- **Skills** — executable instructions that teach Claude how to use
  the system. Two sets: dev skills (for building the system) and
  research skills (for doing science).
- **VS Code + Claude Code** — the primary interface. Claude
  orchestrates the other components: queries the KG, writes scripts,
  runs analysis, produces artifacts.

The target audience for this system is Claude. The researchers ask
questions; Claude needs to do the right thing without being told how.
Skills encode the methodology as executable instructions so the system
works robustly out of the box, even for researchers new to agentic
work.

---

## The fundamental tension

LLMs operate under a context window constraint. MCP tools manage this
by applying limits — return 100 rows, truncate, summarize. This works
for lookups: "what is gene PMM0120?", "what organisms are in the KG?".

Omics analysis is different. A differential expression experiment may
produce 800 significant genes. Pathway enrichment requires the full
gene list. Dropping 700 genes silently produces wrong biological
conclusions — and the LLM has no way to know.

**The dual interface resolves this.** Claude uses MCP tools for
reasoning (summaries in context) and imports the Python package in
scripts for bulk data (Neo4j → file, bypassing context). The context
window holds the plan, the summaries, and the interpretation — not
the raw data.

---

## Design principles

### 1. Skills as the organizing principle

The system's methodology is encoded as skills — structured,
executable instructions that Claude follows. Not documentation for
humans to read and internalize, but protocols for Claude to execute.

**Two skill sets:**

- **Dev skills** live in this repo. They guide Claude in building
  and testing the system itself: layer architecture, tool development
  workflow, testing conventions, naming standards.
- **Research skills** ship with the Python package. They guide Claude
  in doing science: analysis workflows, quality gates, when to use
  MCP vs package import, how to produce reproducible artifacts.

**Why skills, not docs:** A researcher who's never used Claude Code
should be able to ask "what pathways are enriched under nitrogen
stress in MED4?" and Claude should — without prompting — navigate
the KG, extract complete data, run proper statistics, and produce
artifacts. Skills make this happen by encoding the methodology as
executable instructions. Docs require the user to read and
internalize them first.

**Research skills are layered** — progressive capability, not a
flat list:

1. **Tool Wrapper skills** (always active) — baseline competence.
   How to use each MCP tool, how to read summary vs detail
   responses, what parameters mean, when to switch to package
   import. Claude always has this layer. A simple lookup
   ("what is PMM0120?") needs only this.

2. **Pipeline skills** (activated for multi-step analyses) —
   workflow patterns with quality gates. Experiment
   characterization, comparative analysis, time-course clustering.
   These compose tool wrapper knowledge into gated sequences. Claude
   invokes a pipeline when the question warrants a structured
   analysis.

3. **Inversion skills** (activated for ambiguous questions) —
   context gathering before action. "What pathways are enriched?"
   → which organism? which condition? what's the comparison?
   Claude falls back to this when it can't determine which pipeline
   to use or when the question is under-specified.

The layering means Claude always has tool competence (layer 1),
invokes pipelines when the question warrants it (layer 2), and
gathers context when it needs to (layer 3). A typical research
workflow composes all three: Inversion (clarify the question) →
Pipeline (execute the analysis) with Reviewer gates (validate data
completeness at each step) and Generator output (produce artifacts
in the standard structure).

**Skill patterns** (from the agent skills design literature):

| Pattern | Layer | Use in this system |
|---|---|---|
| **Tool Wrapper** | 1 | How to use MCP tools, read responses, choose summary vs detail, switch to package import |
| **Pipeline** | 2 | Multi-step analysis workflows with gates — browse → narrow → extract → analyze → interpret |
| **Inversion** | 3 | Gathering research context — clarifying the question before entering a pipeline |
| **Generator** | within pipelines | Producing analysis artifacts in the `analyses/` structure |
| **Reviewer** | within pipelines | Quality gates — truncation awareness, statistical rigor, data completeness |

### 2. Narrow tools, composable chains

Each MCP tool has a specific, well-defined scope. Tools do one thing
and do it well. Complex analyses emerge from chaining tools, not from
monolithic tools that try to do everything.

**Chaining is the primary interaction pattern.** The system is
designed to support it:

```
resolve_gene("catalase")
  → locus_tags by organism
gene_overview(locus_tags=[...])
  → annotation types, expression counts, ortholog summary
query_expression(locus_tag="PMM0120", significant_only=True)
  → expression data for that gene
```

Each tool's response is self-describing — it provides the information
Claude needs to decide what to call next. Summaries aren't just
answers to the researcher's question; they're navigational, guiding
the next link in the chain.

**Tool scope principle:** if a tool needs to make internal decisions
about what data to fetch next based on intermediate results, that
logic belongs in the tool (server-side). If the decision requires
reasoning about the research question, it belongs in the chain
(Claude-side).

### 3. Summary mode and precomputed statistics

Every tool that returns potentially large result sets has a summary
mode. Summary mode returns precomputed statistics from the KG —
counts, breakdowns, distributions — without fetching and aggregating
raw rows.

**Why precompute:** When the KG is remote (Aura), every query has
network cost. Computing a summary by fetching 800 rows and counting
them client-side is expensive. Reading a precomputed count from a
KG node property is cheap. Summary mode makes each link in the
chain fast, which makes chaining practical over a network.

**How it works:**

- Summary mode is the interface contract. The implementation is
  per-tool, decided in coordination with the KG build pipeline:
  - **Precomputed properties** — statistics baked into KG nodes at
    build time. Cheapest at query time. Best for stable aggregates
    (gene counts per experiment, direction breakdowns).
  - **Summary queries** — lightweight Cypher that aggregates without
    returning raw rows (COUNT, collect, etc.). More flexible than
    precomputed properties, still much cheaper than fetching all rows.
  - The choice is part of the handshake between this repo and the KG
    build pipeline. Each tool's summary implementation is documented
    in its query builder.
- Summary mode is available at every layer: query builders can
  generate summary queries, API functions expose a `summary`
  parameter, MCP tools use summary mode by default.
- Full detail mode fetches raw rows when needed (with limits in MCP,
  unlimited in the package API).

**This replaces the old tier-1/tier-2 concept** with a cleaner
separation: summary mode (precomputed, cheap, always complete) vs
detail mode (raw rows, limited in MCP, unlimited in package). The
key insight is the same — summaries are computed over all data, not
just the returned subset — but the mechanism moves from MCP-side
aggregation to KG-side precomputation.

Summary mode is useful across both interfaces:
- **MCP**: Claude gets counts and breakdowns cheaply to guide
  reasoning and chain decisions, without fetching raw rows.
- **Package**: Scripts get summary statistics directly — no need
  to pull 800 rows just to count directions or categories.

### 4. Dual data access

The same query functions are available two ways:

- **MCP tools** — for Claude's reasoning. Returns summaries and
  limited detail through context. Subject to context window limits.
  Every MCP result transits the context window — there is no way
  around this.
- **Python package** — for data extraction and computation. Same
  functions, same parameters, called in scripts. Results go
  Neo4j → Python → file, bypassing context entirely. Supports
  both summary mode (precomputed stats) and full results.

```
Claude reasoning (in context):
  MCP query_expression(experiment_id="...", significant_only=True)
  → summary: 823 genes, 412 up, 411 down
  → detail: top 100 by effect size

Bulk extraction (bypasses context):
  Agent writes a script:
    from multiomics_explorer import query_expression
    results = query_expression(experiment_id="...",
                               significant_only=True)
    pd.DataFrame(results).to_csv("data/de_genes.csv", index=False)
  Agent runs the script → complete data on disk
```

Claude already knows the function name and parameters — it just used
them in the MCP call. Switching from MCP to package import is
trivial. Research skills encode the decision logic: use MCP for
reasoning, package import for data.

### 5. Quality gates over guidelines

Rules like "don't count genes from a truncated list" and "don't run
enrichment on incomplete data" are not guidelines for the user to
remember. They are quality gates encoded in skills that Claude
checks at each step of a workflow.

**Gates, not suggestions:**

- If `truncated: true`, use `total` from metadata, not `len(rows)`.
  Don't infer absence from a truncated list.
- Before running enrichment: verify the full gene list was extracted
  (package import, not MCP detail).
- Before reporting statistics: verify the computation ran in Python,
  not eyeballed from detail-mode rows.
- After computation: verify outputs exist and are non-empty before
  interpreting.

These are encoded as Reviewer-pattern checks within Pipeline skills.
Claude evaluates them at each gate. If a gate fails, Claude fixes
the issue before proceeding — it doesn't skip ahead and hope.

### 6. Self-describing tools

Tools should be able to describe their own usage, parameters,
chaining patterns, and when to switch to package import. This
makes the system self-teaching — any client (including chat mode)
can learn how to use a tool by asking the tool itself.

This is critical for "robust out of the box." A researcher's
Claude doesn't need pre-loaded skills to use the tools competently
if the tools can explain themselves. Skills build on top of this
baseline — they encode multi-step workflows and quality gates —
but basic tool competence is self-serve.

The mechanism (a `mode` parameter, dedicated endpoints, enriched
docstrings) is an architecture decision. The principle is: **a
tool that can't explain itself is incomplete.**

### 7. Reproducible artifacts

Analysis work produces files, not just chat responses. The standard
structure:

```
analyses/{analysis_name}/
├── data/          # staged data from KG (via package import)
├── scripts/       # Python/R analysis scripts
├── results/       # outputs: tables, plots, statistics
└── README.md      # question, method, conclusion
```

Scripts are re-runnable without Claude — a researcher can
`python scripts/enrichment.py` to verify or modify the analysis.
Data extraction scripts import the package directly. Analysis
scripts read from `data/`, write to `results/`.

This is the Generator pattern: a template that Claude fills for
each analysis. The structure is consistent; the content varies.

---

## How skills guide research

### Layer 1: Tool competence (always active)

Claude always knows how to use the MCP tools and the Python
package effectively. This layer covers:

- **Reading responses** — understanding summary vs detail mode,
  interpreting truncation metadata, using `total` not `len(rows)`.
- **Tool selection** — which tool answers which kind of question,
  how tools chain together (resolve → overview → query).
- **Interface selection** — when to use MCP (reasoning, navigation,
  small results) vs package import (bulk data, computation,
  complete results).
- **Self-describing navigation** — each tool response guides the
  next call in the chain.

A simple lookup ("what is PMM0120?") needs only this layer.
Self-describing tools (principle 6) provide the foundation —
skills build on top.

### Layer 2: Analysis workflows (activated for multi-step questions)

When a question requires structured analysis, Claude follows a
pipeline with quality gates. Common patterns:

**Experiment characterization** — "What happens when you starve
MED4 of nitrogen?" Browse experiments → summarize expression →
gate: right experiment? → extract full data → analyze (enrichment,
volcano) → gate: outputs valid? → interpret.

**Gene-centric survey** — "How does PMM0120 respond across all
conditions?" Resolve gene → query expression → interpret directly.
Naturally small results, no extraction step needed.

**Comparative pathway analysis** — "Is photosynthesis more
affected by nitrogen or light stress?" Summarize both conditions →
gate: right experiments? → extract both → statistical comparison →
interpret with effect sizes and p-values.

**Ortholog conservation** — "Is the nitrogen response conserved
across strains?" Identify orthologs → extract cross-strain
expression matrix → compute conservation scores → interpret.

**Time-course trajectory** — "How does the response unfold over
time?" Browse time-course experiments → summarize per time point →
extract full trajectory → cluster → interpret temporal waves.

**Publication-ready export** — "Generate a supplementary table."
Pure extraction + formatting via package import. No MCP needed.

Each pipeline shares the same structure: browse → narrow → gate →
extract → gate → analyze → gate → interpret. The gates are quality
checks (data completeness, correct row counts, non-empty outputs)
that prevent Claude from proceeding with bad data.

*Chat mode stops at the summary step.* Qualitative, not
quantitative. Summary mode is designed to make this ceiling as
informative as possible.

### Layer 3: Context gathering (activated for ambiguous questions)

When Claude can't determine which pipeline to use or the question
is under-specified, it gathers context before acting:

- "What pathways are enriched?" → which organism? which condition?
  what's the comparison group?
- "Compare these genes" → across what dimension? expression?
  conservation? annotation?
- "Analyze this experiment" → characterize? specific pathway? vs
  another condition?

This prevents Claude from guessing and running the wrong analysis.
Better to ask one clarifying question than to produce a wrong
result the researcher might trust.

### How the layers compose

A typical interaction flows through all three:

1. Researcher asks an ambiguous question (layer 3 activates →
   clarify)
2. Claude identifies the right pipeline (layer 2 activates →
   gated workflow)
3. Each step in the pipeline uses tools competently (layer 1 →
   correct tool usage, summary vs detail, MCP vs package import)

Simple questions skip layers 2 and 3. Well-specified complex
questions skip layer 3. The layering ensures Claude always responds
appropriately to the complexity of the question.

---

## Dev skills

Dev skills live in this repo and guide Claude in building and
testing the system. They enforce the architecture. Details of
which skills exist and where they live belong in the architecture
doc — here we describe what they cover:

- **Layer rules** (Tool Wrapper, always active) — the layer
  architecture conventions. What each layer does, what it returns,
  what it doesn't touch. Prevents drift as the codebase grows.
- **Tool lifecycle** (Pipeline) — adding or modifying an MCP tool.
  Query builder → API function → wrapper → tests → docstring →
  skill (update tool wrapper skill, add/update pipeline skills that
  use the tool), with gates (tests pass) at each step. The tool
  isn't done until Claude knows how to use it.
- **Testing** (Pipeline + Tool Wrapper) — what to test at each
  layer, how to add and update tests across all layers, how to
  regenerate fixtures, when to update regression cases. Covers
  the full test lifecycle: adding tests for new tools, updating
  tests when tools change, maintaining regression fixtures.
- **Code review** (Reviewer) — validate changes against the
  architecture: layer boundaries respected, tests updated, skills
  updated, naming conventions followed.

---

## Chat mode: scope and limitations

The KG + MCP server is available via chat interfaces (Claude Desktop,
etc.) without the agentic stack. In this mode:

**Suitable for:**
- Browsing: "What experiments exist for MED4?"
- Lookup: "What is the function of PMM0120?"
- Targeted queries: "Is PMM0120 upregulated under nitrogen stress?"
- Summary statistics: "How many genes respond to coculture?"

**Not suitable for:**
- Quantitative enrichment analysis
- Full gene list export
- Multi-experiment meta-analysis
- Anything requiring statistical rigor beyond summary statistics
- Producing artifacts (files, plots)

Summary mode is the ceiling of what chat mode can do for quantitative
questions. It's designed to be as informative as possible within that
constraint.

**Skills in chat mode:** Layer 1 (tool competence) is fully relevant
to chat — how to read responses, chain tools, interpret truncation
metadata. But chat has no `.claude/skills/`. Layer 1 knowledge
reaches chat-mode Claude through MCP server instructions and tool
docstrings. Same content, different delivery surface. Layers 2 and 3
(pipelines, inversion) are not actionable in chat mode — they
require file I/O and code execution.

---

## Deployment architecture

Deployment details (topology, transport, `init-claude` implementation)
belong in the architecture doc. This section covers the high-level
shape.

### What ships

One installable package, multiple interfaces:

1. **`multiomics-explorer` Python package** — query functions, Neo4j
   connection. Usable as direct Python import in scripts.
2. **`multiomics-kg-mcp` MCP server** — wraps package functions for
   LLM access. Adds summary/detail formatting, limits. Runs on a
   remote server.
3. **`multiomics-explorer init-claude`** CLI command — scaffolds
   Claude Code integration: research skills, CLAUDE.md snippet,
   .mcp.json config.

### Topology

```
Researcher's machine              Remote
├── VS Code + Claude Code         ├── Neo4j Aura (KG)
├── multiomics-explorer (pip) ───►│
├── Research skills (.claude/)    ├── MCP server ──► Aura
└── Claude ──── MCP (HTTP) ──────►│
```

Two data paths, both hitting remote Neo4j:
- **MCP**: Claude → remote MCP server → Aura → summary/detail
  through context
- **Package import**: script on researcher's machine → Aura → local
  file, bypasses context

### Authentication

Single read-only Neo4j user. All users share the same credentials.
This is published research data — nothing to protect beyond
preventing writes (enforced by Neo4j user role).

### The `init-claude` command

```bash
$ multiomics-explorer init-claude

Created .mcp.json with multiomics-kg MCP server config
Created .claude/skills/ with research workflow skills
Appended KG dual-interface guidance to CLAUDE.md

Available skills:
  /characterize-experiment  — Full DE experiment characterization
  /compare-conditions       — Cross-condition pathway comparison
  /gene-survey              — Gene response across all experiments
  /ortholog-conservation    — Cross-strain conservation analysis
  /timecourse-analysis      — Time-course clustering
  /export-de-genes          — Publication-ready supplementary tables
```

Idempotent. Updates skills to latest version from installed package.

---

## Usage logging and evaluation

### Logging principles

Usage logging should capture both **what tools were called** and
**what workflow triggered them**. Tool-level logs (parameters,
latency, truncation) reveal tool design issues. Skill-level context
(which pipeline, which step) reveals workflow design issues. Without
both, you can see that `query_expression` was called twice in a row
but not whether that was a pipeline step or a confused retry.

Where logs live, how skill context flows to the tool layer, and
access model (local vs remote) are architecture decisions.

### MCP tool call log

Every MCP tool call is logged:

```jsonl
{"ts": "...", "tool": "query_expression", "params": {...},
 "result_total": 823, "result_returned": 100, "truncated": true,
 "duration_ms": 340, "error": null}
```

**What patterns reveal:**

| Pattern | Signal |
|---|---|
| Tool X never called | Undiscoverable or unnecessary |
| Same tool, same params repeated | Defaults wrong, or skill should encode this |
| `run_cypher` called frequently | Structured tools don't cover common queries |
| High `duration_ms` | Query needs optimization or precomputation |
| Tool A always followed by tool B | Workflow pattern → candidate for a skill |
| `truncated: true` on most calls | Limit too low or summary insufficient |

### Analysis artifacts

The `analyses/` directory structure captures what Claude produced:
scripts, data, results, README. This is a retrospective record of
analyses. No additional logging needed.

### From logs to evaluation

**Phase 2** (stress test): Review own usage logs. Which tools matter?
Where did Claude reach for `run_cypher`? Where did it retry?

**Phase 3** (researcher deploy): Aggregate logs from consenting
researchers. Tool usage distribution, workflow sequences, truncation
frequency, error rates.

**Phase 4** (production): Formalize into recurring evaluation with
curated test cases from real researcher questions.

---

## Roadmap

### Phase 1: Build (now)

KG redesign + MCP tools + Python package API + dev skills.
Local Neo4j for development.

**Deliverables:**
- KG with precomputed summary statistics, Experiment nodes,
  expression edges
- MCP tools with summary/detail/about modes (about = the
  self-describing tool capability — see principle 2)
- Python package API with summary support
- Dev skills: layer rules, tool lifecycle (including skill
  building), testing conventions, code review
- Layer 1 research skills: tool wrapper skills for tool competence
  (also expressed in MCP server instructions + docstrings)
- Updated tests and regression fixtures

### Phase 2: Stress test

Separate repo. Use Claude Code as the researcher — real analysis
questions. Exercise layer 1 skills, draft layer 2 pipeline skills
from observed patterns, identify where layer 3 (inversion) is
needed.

**Produces:**
- Validated (or revised) tool wrapper skills (layer 1)
- Draft pipeline skills (layer 2) from real workflow patterns
- Draft inversion skills (layer 3) from observed ambiguity points
- Assessment: does Claude pick the right pipeline? Is a skill
  selection mechanism needed?
- Bug reports and API friction points
- Usage data (tool-level + skill context) for evaluation

### Phase 3: Deploy to researchers (April–May 2026)

KG on Aura. MCP server deployed remotely. Package on PyPI.
3–4 researchers install and use it.

**Deliverables:**
- Neo4j Aura instance
- Remote MCP server
- `pip install multiomics-explorer`
- `init-claude` with all three skill layers
- Usage logging with skill context
- MCP server instructions carrying layer 1 content for chat mode

### Phase 4: Production

Incorporate feedback. Refine skills based on usage logs and
researcher experience. Formalize evaluation. Assess skill
selection needs. Broader release.

---

## Open questions

- **Enrichment as an MCP tool:** Server-side enrichment (against KG
  gene universe) would be faster, available in chat mode, and ensure
  correct background set. Worth building?

- **Analysis templates as library modules:** Should common analyses
  (enrichment, clustering, volcano plots) live in the package as
  importable modules? More reliable than Claude writing from scratch
  each time, but less flexible.

- **MCP server deployment:** Remote MCP server transport (SSE /
  streamable HTTP), hosting, authentication. Not yet scoped.

- **Precomputed vs summary queries per tool:** Each tool needs a
  decision: precomputed properties (cheapest, rigid) vs summary
  queries (flexible, still cheap) vs hybrid. This is a per-tool
  handshake with the KG build pipeline. Criteria: query frequency,
  stability of the aggregate, cost of the summary query.

- **Caching:** The API/MCP layer uses a read-only Neo4j user, so
  it can't write cache entries to the KG. Options: precomputation
  at KG build time (the primary strategy), application-side cache
  on the MCP server (in-memory or local), or accept the query cost.
  Architecture decision, not methodology.
