# Using the Python API

The `multiomics_explorer` package exposes the same 37 tools available
via MCP, plus a handful of analysis utilities, as ordinary Python
functions. Use the package when you need bulk extraction, multi-step
pipelines, custom plotting, or DataFrame workflows. Use MCP when you
need reasoning, interactive exploration, or single-question slices.

**Domain-specific deep references** (read these for methodology + worked
code beyond what this guide covers):

- `docs://analysis/enrichment` — pathway enrichment with `EnrichmentResult`,
  background semantics, `informative_only` rationale, custom TERM2GENE.
- `docs://analysis/metabolites` — chemistry layer (3 source pipelines)
  with track-by-track decision tree.
- `docs://analysis/derived_metrics` — DerivedMetric family (numeric /
  boolean / categorical drill-downs, rankable / has_p_value gating).

**Runnable example scripts** (`uv run python examples/<file>`):

- `docs://examples/pathway_enrichment.py` — `EnrichmentResult` accessors,
  custom term2gene, `informative_only` side-by-side comparison.
- `docs://examples/metabolites.py` — 7 worked scenarios spanning the 3
  metabolite source pipelines.

**Other guides:**

- `docs://guide/start_here` — tool-selection map (which tool for which question).
- `docs://guide/concepts` — node and edge meanings, evidence layers, cross-cutting axes.
- `docs://guide/conventions` — `not_found`, tested-absent rows, filter
  semantics, pagination, transport-confidence, AQ / informative_only defaults.

---

## When to use Python vs MCP

| Use case | Surface |
|---|---|
| "What does gene X do?" — single question | MCP |
| "Pick the right ontology level for enrichment" — exploratory recon | MCP |
| "Run enrichment on 12 experiments and write a CSV" | Python |
| "Build a gene × treatment response matrix and plot a heatmap" | Python |
| "Need all matching rows without pagination" | Python |
| "Need the `EnrichmentResult` accessors (`.explain()`, `.overlap_genes()`)" | Python |
| "Reuse a Neo4j connection across many calls" | Python |
| "One-off DataFrame for a CSV export" | Python (`to_dataframe`) |

The two surfaces share signatures (parameter names match) but differ in
**pagination** and **return shape** — see below.

---

## Import topology

The public-facing package surface is **one namespace**:
`multiomics_explorer`. Everything you need is reachable from the top
level.

```python
from multiomics_explorer import (
    # 37 API functions — same names as the MCP tools.
    list_metabolites, gene_overview,
    differential_expression_by_gene, pathway_enrichment,

    # Enrichment building blocks (9 names — see docs://analysis/enrichment).
    EnrichmentInputs, EnrichmentResult,
    de_enrichment_inputs, cluster_enrichment_inputs,
    fisher_ora, signed_enrichment_score,
    DEStats, GeneRef, EnrichmentExplanation,

    # Analysis utilities (3 names).
    response_matrix, gene_set_compare, to_dataframe,

    # Connection management — only when sharing a Neo4j driver across calls.
    GraphConnection,
)
```

That's the contract. `multiomics_explorer.__all__` lists every public
name (50 total: 37 API + 9 enrichment + 3 analysis utilities + `GraphConnection`).

Deeper paths (`multiomics_explorer.api`, `multiomics_explorer.analysis`,
`multiomics_explorer.analysis.frames`,
`multiomics_explorer.analysis.enrichment`,
`multiomics_explorer.analysis.expression`,
`multiomics_explorer.kg.connection`) are internal implementation
detail. They work today because the public surface re-exports them, but
**don't import from them in user code** — the top-level re-export
contract is what's stable.

---

## Three return shapes

The 37 API functions plus the analysis utilities cluster into three
return types:

### 1. `dict` (default — 32 of 37 API functions)

```python
result = list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"])
# {
#   "total_matching": 1563,
#   "by_organism": [...],
#   "top_metabolite_pathways": [...],
#   "results": [ {...}, {...}, ... ],
#   "not_found": {...},
#   ...
# }
```

The dict shape mirrors the MCP envelope but is **unpaginated** — the
`results` list contains every matching row. `total_matching ==
len(result["results"])` always. The `returned` and `truncated` fields
are present but reflect the full set (no pagination occurred).

### 2. `EnrichmentResult` (3 functions: `pathway_enrichment`, `cluster_enrichment`, `fisher_ora`)

```python
result = pathway_enrichment(
    organism="MED4", experiment_ids=["exp1"],
    ontology="cyanorak_role", level=1,
)
# EnrichmentResult object with:
#   result.results          ← pandas DataFrame, one row per (cluster × term)
#   result.inputs           ← EnrichmentInputs (gene_sets, background, metadata)
#   result.term2gene        ← DataFrame used for overlap
#   result.params           ← dict of ORA parameters for reproducibility
#   result.kind             ← "pathway" or "cluster"
# Accessors (compute non-trivially):
#   result.explain(cluster, term_id)         → EnrichmentExplanation (Jupyter-rendered)
#   result.overlap_genes(cluster, term_id)   → list[GeneRef]
#   result.background_genes(cluster, term_id)→ list[GeneRef]
#   result.cluster_context(cluster)          → dict
#   result.why_skipped(cluster)              → str | None
#   result.to_compare_cluster_frame()        → clusterProfiler-style DataFrame
#   result.missing_terms()                   → dict[str, list[str]]
#   result.generate_summary()                → aggregate dict
#   result.to_envelope(summary=False, limit=None, offset=0)  → MCP-shaped dict
```

`fisher_ora` returns the same object when called directly with custom
gene sets / TERM2GENE. See `docs://analysis/enrichment` §18 for the
full accessor reference.

### 3. `pandas.DataFrame` (2 analysis utilities: `response_matrix`, `gene_set_compare`)

Both wrap `gene_response_profile` and reshape its result. They are the
right entry points when you need a matrix view across treatments
rather than per-gene response stats. Detailed reference is the
"Cross-experiment summarization" section below.

---

## Result → pandas DataFrame

`to_dataframe(result)` is the single entry point. It auto-dispatches
based on the result shape:

```python
from multiomics_explorer import to_dataframe, genes_by_function

# Most tools — flat one-row-per-result conversion.
df = to_dataframe(genes_by_function(query="nitrogen", organism="MED4"))

# gene_response_profile result — auto-unwound to gene × treatment group.
df = to_dataframe(gene_response_profile(locus_tags=["PMM0370"]))

# list_experiments result — auto-unwound to experiment × timepoint.
df = to_dataframe(list_experiments(organism="MED4"))

# list_clustering_analyses result — auto-unwound to analysis × cluster.
df = to_dataframe(list_clustering_analyses(organism="MED4"))
```

| Input | Output |
|---|---|
| Any tool result with no nested fields | One row per `result["results"]` entry, list columns joined by ` \| `, dict columns inlined as `{col}_{key}` |
| `gene_response_profile()` result | One row per gene × treatment group (`response_summary` unwound) |
| `list_experiments()` result | One row per experiment × timepoint (`timepoints` unwound; `genes_by_status` inlined at both levels) |
| `list_clustering_analyses()` result | One row per analysis × cluster (`clusters` unwound; verbose adds cluster description columns) |
| `EnrichmentResult` (any) | `result.results` is already a DataFrame — no conversion needed |

### Notes

- Avoid `pd.DataFrame(result["results"])` directly — it doesn't process list/dict columns, so anything non-scalar causes downstream pain.
- Unrecognized nested columns (rare) get dropped with a `UserWarning`; the three known nested-content tools auto-dispatch.

---

## Cross-experiment summarization (`response_matrix` + `gene_set_compare`)

Two analysis utilities turn `gene_response_profile` output into matrix
views across treatments. Both group experiments by `treatment_type` by
default; pass `group_map` for custom groupings. Both share the
"direction classification" cell vocabulary:

| Value | Meaning |
|---|---|
| `"up"` | Only upregulated experiments in this group |
| `"down"` | Only downregulated experiments |
| `"mixed"` | Both up and down experiments |
| `"not_responded"` | Expression edges exist but none significant, OR gene inferred as tested via full-coverage scope (`groups_tested_not_responded`) |
| `"not_known"` | No expression data for this gene in this group |

### `response_matrix(genes, organism=None, ...)` — gene × group pivot

Returns a `pandas.DataFrame` indexed by `locus_tag` with one column per
group. Metadata columns `gene_name`, `product`, `gene_category` are
appended. Empty DataFrame (with `index.name="locus_tag"`) when no
results found.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `genes` | `list[str]` | required | Locus tags to query |
| `organism` | `str \| None` | `None` | Organism filter (fuzzy match) |
| `experiment_ids` | `list[str] \| None` | `None` | Experiment filter (ignored when `group_map` is set) |
| `group_map` | `dict[str, str] \| None` | `None` | `experiment_id → group label` for custom grouping |
| `conn` | `GraphConnection \| None` | `None` | Reuse an existing Neo4j connection |

**Basic treatment-type matrix:**

```python
from multiomics_explorer import response_matrix

df = response_matrix(
    genes=["PMM0370", "PMM0920", "PMM0965"],
    organism="MED4",
)
# Columns: "nitrogen_stress", "light_stress", ..., "gene_name", "product", "gene_category"
print(df[["nitrogen_stress", "light_stress"]])
```

**Custom grouping with `group_map`:**

```python
from multiomics_explorer import response_matrix

group_map = {
    "GSE37441_MED4_Nlimit_1": "early_N",
    "GSE37441_MED4_Nlimit_2": "early_N",
    "GSE59000_MED4_Nrecovery": "late_N",
}
df = response_matrix(
    genes=["PMM0370", "PMM0920"],
    group_map=group_map,
)
# Columns: "early_N", "late_N", "gene_name", "product", "gene_category"
```

**Chaining from gene search:**

```python
from multiomics_explorer import genes_by_function, response_matrix

hits = genes_by_function(search_text="nitrogen", organism="MED4")
locus_tags = [r["locus_tag"] for r in hits["results"][:20]]
df = response_matrix(genes=locus_tags, organism="MED4")
```

**Common mistakes**

| Mistake | Fix |
|---|---|
| Passing `experiment_ids` when `group_map` is set | `group_map` overrides — pass experiments via `group_map` for custom grouping |
| Expecting numeric values (log2FC, p-values) in cells | `response_matrix` cells are categorical strings. Use `gene_response_profile` for rank/log2FC, or `differential_expression_by_gene` for per-timepoint numerics |
| Calling for a single gene | `gene_response_profile` directly returns richer per-group statistics |
| Assuming `"not_responded"` always means edge-based | Can also be inference-based via `groups_tested_not_responded` (full-coverage scope). Use `gene_response_profile` to distinguish |

### `gene_set_compare(set_a, set_b, ...)` — two-set partition

Compares response profiles for two gene sets. Builds a single response
matrix for the union, partitions by membership, and produces per-group
summary statistics.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `set_a` | `list[str]` | required | First gene set (locus tags) |
| `set_b` | `list[str]` | required | Second gene set |
| `organism` | `str \| None` | `None` | Organism filter |
| `set_a_name` | `str` | `"set_a"` | Label for set A in summary columns |
| `set_b_name` | `str` | `"set_b"` | Label for set B in summary columns |
| `experiment_ids` | `list[str] \| None` | `None` | Experiment filter (ignored when `group_map` is set) |
| `group_map` | `dict[str, str] \| None` | `None` | `experiment_id → group label` for custom grouping |
| `conn` | `GraphConnection \| None` | `None` | Reuse an existing Neo4j connection |

Returns a `dict`:

| Key | Type | Description |
|---|---|---|
| `overlap` | `DataFrame` | Genes present in both sets (same shape as `response_matrix` output) |
| `only_a` | `DataFrame` | Genes only in `set_a` |
| `only_b` | `DataFrame` | Genes only in `set_b` |
| `shared_groups` | `list[str]` | Groups where both sets have ≥1 responding gene |
| `divergent_groups` | `list[str]` | Groups where exactly one set has responding genes |
| `summary_per_group` | `DataFrame` | Indexed by group, columns: `{set_a_name}`, `{set_b_name}`, `overlap`, `shared` |

`summary_per_group` columns:

| Column | Type | Description |
|---|---|---|
| `{set_a_name}` | `int` | Count of responding genes from `set_a` in this group |
| `{set_b_name}` | `int` | Count of responding genes from `set_b` in this group |
| `overlap` | `int` | Count of responding overlap genes in this group |
| `shared` | `bool` | True if both sets have ≥1 responding gene |

"Responding" means the cell value is `"up"`, `"down"`, or `"mixed"`.

```python
from multiomics_explorer import gene_set_compare

result = gene_set_compare(
    set_a=["PMM0370", "PMM0920", "PMM0965"],
    set_b=["PMM0468", "PMM0552", "PMM0965"],
    organism="MED4",
    set_a_name="early_responders",
    set_b_name="late_responders",
)

print(result["overlap"])              # PMM0965
print(result["summary_per_group"])
#                      early_responders  late_responders  overlap  shared
# nitrogen_stress                    3                2        1    True
# light_stress                       0                1        0   False
print(result["shared_groups"])        # ["nitrogen_stress"]
```

**Common mistakes**

| Mistake | Fix |
|---|---|
| Expecting `overlap` to contain only responding shared genes | `overlap` contains genes in both input lists regardless of response. "Shared" in `summary_per_group` is the responding-gene concept |
| Assuming `shared_groups` + `divergent_groups` are exhaustive | Groups where neither set responds appear in neither list |

---

## Pagination & bulk extraction

The biggest behavioral difference between MCP and the package is
**pagination**:

- **MCP:** every tool paginates with `limit` (default 5 on most tools)
  and `offset`. `truncated=true` indicates more rows beyond the page.
- **Package:** the same `limit` / `offset` parameters exist, but
  defaults are wide-open — most tools default to `limit=None`,
  returning every matching row in a single call.

For bulk extraction, leave `limit=None` (the default on the package)
and let the function return the full set:

```python
from multiomics_explorer import differential_expression_by_gene

# Returns every DE row for the experiment, regardless of count.
result = differential_expression_by_gene(
    organism="MED4",
    experiment_ids=["my_experiment"],
    significant_only=True,
)
# len(result["results"]) == result["total_matching"]
```

If you need MCP-style pagination from Python (e.g. to feed a UI), pass
explicit `limit=` and `offset=` and inspect `truncated`.

### `EnrichmentResult.to_envelope`

Conversion in the other direction — package result → MCP-shaped
paginated dict — is supported on `EnrichmentResult`:

```python
result = pathway_enrichment(organism="MED4", experiment_ids=["exp1"], ...)
mcp_dict = result.to_envelope(limit=20, offset=0)
# Same shape as docs://tools/pathway_enrichment, with truncated/returned set.
```

The MCP tool wrapper calls `.to_envelope()` internally; Python callers
rarely need it.

---

## Connection management

Every API function accepts `conn: GraphConnection | None = None` as a
keyword-only argument (positional or keyword — kwarg is conventional).
When `conn=None` (the default), the function creates a fresh
`GraphConnection` per call:

```python
def _default_conn(conn: GraphConnection | None) -> GraphConnection:
    if conn is None:
        return GraphConnection()
    return conn
```

`GraphConnection` is lazy — the underlying Neo4j driver is created on
first use. For one-off scripts the default is fine; the connection
overhead per call is small.

For multi-call workflows (a notebook session, a pipeline that fans
out 50+ tool calls), share a single connection to avoid opening 50+
drivers:

```python
from multiomics_explorer import (
    gene_overview, differential_expression_by_gene, GraphConnection,
)

with GraphConnection() as conn:
    overview = gene_overview(locus_tags=["PMM0001", "PMM0002"], conn=conn)
    de = differential_expression_by_gene(
        organism="MED4",
        locus_tags=[r["locus_tag"] for r in overview["results"]],
        conn=conn,
    )
# Driver closed cleanly on context-manager exit.
```

`GraphConnection()` reads connection settings from `.env` /
environment variables (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`).
Pass an explicit `Settings` object only when overriding programmatically.

---

## Two worked recipes

### Recipe 1: DE → pathway enrichment → CSV

The full DE-driven enrichment pipeline in five calls. Equivalent to
the `pathway_enrichment` MCP tool but exposes intermediate
DataFrames for inspection.

```python
from multiomics_explorer import (
    de_enrichment_inputs, fisher_ora, signed_enrichment_score,
    genes_by_ontology,
)
from multiomics_explorer import to_dataframe

# 1. Build per-cluster gene sets + table_scope backgrounds from DE results.
inputs = de_enrichment_inputs(
    experiment_ids=["my_exp_1", "my_exp_2"],
    organism="MED4",
    direction="both",
    significant_only=True,
)

# 2. Fetch TERM2GENE for the chosen (ontology, level).
term2gene = to_dataframe(
    genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)
)

# 3. Run Fisher ORA — returns EnrichmentResult.
result = fisher_ora(inputs, term2gene, min_gene_set_size=5, max_gene_set_size=500)

# 4. Attach direction, compute signed score.
df = result.results.copy()
df["direction"] = df["cluster"].map(lambda c: inputs.cluster_metadata[c]["direction"])
collapsed = signed_enrichment_score(df)

# 5. Export.
collapsed.to_csv("enrichment.csv", index=False)
```

`docs://analysis/enrichment` §4 has the same recipe with full
narrative, plus variants for cluster-membership enrichment, ortholog
groups, and custom gene lists. Runnable: `docs://examples/pathway_enrichment.py`.

### Recipe 2: discovery → drill-down → DataFrame

Standard "explore then materialize" pattern. Use `summary=True` for the
recon pass; drop it for detail; convert to DataFrame for export.

```python
from multiomics_explorer import (
    list_metabolites, genes_by_metabolite, to_dataframe, GraphConnection,
)

with GraphConnection() as conn:
    # Recon — what N-bearing metabolites does MED4 reach?
    summary = list_metabolites(
        organism_names=["Prochlorococcus MED4"],
        elements=["N"],
        summary=True,
        conn=conn,
    )
    # summary["top_metabolite_pathways"], summary["by_evidence_source"], ...

    # Detail — fetch full rows.
    detail = list_metabolites(
        organism_names=["Prochlorococcus MED4"],
        elements=["N"],
        conn=conn,
    )
    df_metabolites = to_dataframe(detail)

    # Drill — gene catalysts/transporters per metabolite.
    metabolite_ids = [r["metabolite_id"] for r in detail["results"][:20]]
    drill = genes_by_metabolite(
        metabolite_ids=metabolite_ids,
        organism="Prochlorococcus MED4",
        conn=conn,
    )
    df_genes = to_dataframe(drill)

# Both DataFrames closed-form for plotting / CSV.
```

For the chemistry-specific worked examples (3 source pipelines × 7
scenarios) see `docs://examples/metabolites.py`.

---

## Where to go next

- `docs://analysis/enrichment` — `EnrichmentResult` accessors, custom
  TERM2GENE, background semantics, `informative_only` rationale.
- `docs://analysis/derived_metrics` — DerivedMetric family in Python.
- `docs://analysis/metabolites` — chemistry layer (3 source pipelines).
- `docs://examples/pathway_enrichment.py` — runnable enrichment example.
- `docs://examples/metabolites.py` — runnable metabolites workflow examples.
- Per-tool docs (`docs://tools/{name}`) — every tool md has a
  "Package import equivalent" section showing the matching Python
  signature, the import statement, and the dict shape returned.
