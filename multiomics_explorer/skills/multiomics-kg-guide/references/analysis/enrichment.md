# Pathway Enrichment Methodology

**Served as:** `docs://analysis/enrichment`  
**Runnable examples:** `docs://examples/pathway_enrichment.py`

This document explains how to run pathway enrichment analyses in Python using the
`multiomics_explorer` package. It covers the building blocks, five worked code examples
(landscape scouting, DE path, cluster-membership, ortholog-group, and custom gene lists),
biological methodology, and a field reference with clusterProfiler mappings.

For runnable versions of every example below, see `docs://examples/pathway_enrichment.py`.
For the MCP convenience wrapper (`pathway_enrichment` tool), see the last section and
`docs://tools/pathway_enrichment`.

---

## 1. What enrichment is

Given a gene set (for example, the differentially expressed genes from an experiment) and
a background (the genes that could in principle have appeared in that set), over-representation
analysis (ORA) asks: which functional categories are more represented in the gene set than we
would expect by chance?

The test is a one-sided Fisher exact test per (gene set, pathway) pair. The null hypothesis is
that set membership is independent of pathway membership — i.e., the overlap `k` is no larger
than a random draw from the background would produce. Significant `p_adjust` values flag
pathways that are enriched beyond chance.

The primitive is gene-list-first: it knows nothing about experiments, time points, or the KG.
It accepts any foreground gene set, any background, and any TERM2GENE mapping. The DE-wired
path (including the MCP tool) is a convenience layer on top.

---

## 2. Building blocks (Python API)

All four names are importable from `multiomics_explorer` directly:

```python
from multiomics_explorer import (
    de_enrichment_inputs,
    fisher_ora,
    signed_enrichment_score,
    EnrichmentInputs,
)
from multiomics_explorer.api import genes_by_ontology
from multiomics_explorer.analysis.frames import to_dataframe
```

### `de_enrichment_inputs(experiment_ids, organism, direction, significant_only, timepoint_filter)`

Calls `differential_expression_by_gene` and partitions the result into clusters named
`"{experiment_id}|{timepoint}|{direction}"`. Returns an `EnrichmentInputs` object carrying:

- `gene_sets` — dict of cluster → significant DE locus_tags (respects `direction` and
  `significant_only`).
- `background` — dict of cluster → all quantified locus_tags for that experiment/timepoint
  (the `table_scope` universe; see §9).
- `cluster_metadata` — dict of cluster → experiment context fields.
- `not_found`, `not_matched`, `no_expression` — partial-failure buckets (individual
  experiments with problems do not raise; they are collected here).

### `fisher_ora(gene_sets, background, term2gene, min_gene_set_size=5, max_gene_set_size=500)`

Pure Fisher + Benjamini-Hochberg primitive. Direction-agnostic. Accepts any gene-list source —
not just DE results. `background` may be a per-cluster dict or a shared list. Returns a long
DataFrame (one row per cluster × term pair) with compareCluster-compatible columns.

The size filter acts on **M** (pathway members within the cluster's background), not the global
pathway size. See §12 Gotchas.

### `signed_enrichment_score(df, direction_col='direction', padj_col='p_adjust')`

Collapses `|up` / `|down` cluster pairs into one row per `(stem, term)`. Sign comes from
whichever direction has the smaller `p_adjust`; score is `sign × −log10(min_padj)`. Use this
after attaching a `direction` column to the `fisher_ora` output. Standalone so you can
re-derive under new cutoffs without re-running Fisher.

### `genes_by_ontology(ontology, organism, level, term_ids=None, ...)`

The canonical TERM2GENE source. Returns (gene × term) pairs annotated to the requested ontology
level with hierarchy expansion. Pass the result through `to_dataframe` and feed it straight into
`fisher_ora` — no manual column renaming required. Any DataFrame with `term_id`, `term_name`,
and `locus_tag` columns also works (clusterProfiler TERM2GENE frames, hand-curated CSVs, etc.).

---

## 3. Code example — choosing ontology and level with `ontology_landscape`

Run this first, before any enrichment. It ranks all (ontology × level) combinations by
`relevance_rank` so you can pick a combination with good genome coverage and reasonable term
sizes. Genome coverage is required — term-size distributions alone mislead (this was the root
cause of B1's original over-reliance on a single ontology level without checking coverage).

```python
from multiomics_explorer.api import ontology_landscape
from multiomics_explorer.analysis.frames import to_dataframe

# Survey all ontologies for MED4.
# Supply experiment_ids to weight coverage by the experiments you plan to use.
landscape = ontology_landscape(
    organism="MED4",
    experiment_ids=["exp1", "exp2"],   # optional — re-ranks by experiment coverage
    min_gene_set_size=5,
    max_gene_set_size=500,
)
df_landscape = to_dataframe(landscape)

# Rows are (ontology × level) combinations. Sort ascending — rank 1 is best.
df_landscape.sort_values("relevance_rank").head(10)
# Key columns: ontology, level, genome_coverage, median_genes_per_term, best_effort_share (GO only)
# -> pick an (ontology, level) with genome_coverage > ~0.6 and median_genes_per_term 5–100.
```

`relevance_rank` bakes in both genome coverage and median term size; experiment-specific
coverage is incorporated when you supply `experiment_ids`. See §10 for the full narrative.

---

## 4. Code example — DE path (reproduces the MCP tool)

The standard enrichment pipeline for differential expression results:

```python
from multiomics_explorer import (
    de_enrichment_inputs, fisher_ora, signed_enrichment_score,
)
from multiomics_explorer.api import genes_by_ontology
from multiomics_explorer.analysis.frames import to_dataframe

# Step 1: build gene sets from DE results.
inputs = de_enrichment_inputs(
    experiment_ids=["exp1", "exp2"],
    organism="MED4",
    direction="both",        # 'up' | 'down' | 'both'
    significant_only=True,   # foreground = significant DE genes
)
# inputs.gene_sets     -> {cluster: [locus_tags, ...]}
# inputs.background    -> {cluster: [universe locus_tags, ...]}  (table_scope)
# inputs.not_found     -> experiment_ids absent from KG
# inputs.not_matched   -> experiment_ids that belong to a different organism
# inputs.no_expression -> experiments with no DE rows

# Step 2: fetch TERM2GENE for the chosen (ontology, level).
gbo = genes_by_ontology(
    ontology="cyanorak_role", organism="MED4", level=1,
)
term2gene = to_dataframe(gbo)   # columns: term_id, term_name, locus_tag, level, ...

# Step 3: run Fisher ORA (BH applied per cluster).
df = fisher_ora(
    inputs.gene_sets, inputs.background, term2gene,
    min_gene_set_size=5, max_gene_set_size=500,
)

# Step 4: attach direction and compute signed score.
df["direction"] = df["cluster"].map(
    lambda c: inputs.cluster_metadata[c]["direction"]
)
collapsed = signed_enrichment_score(df)
# collapsed: one row per (stem, term) — signed_score is the visualization scalar.
```

---

## 5. Code example — cluster-membership enrichment (non-DE)

Use `list_clustering_analyses` and `genes_in_cluster` to build gene sets from a published
co-expression clustering. The background is the analysis universe (all genes that were
clustered), not the full genome.

```python
from multiomics_explorer.api import (
    list_clustering_analyses, genes_in_cluster, genes_by_ontology,
)
from multiomics_explorer.analysis.frames import to_dataframe
from multiomics_explorer import fisher_ora

# Fetch an analysis and its clusters.
analyses = list_clustering_analyses(organism="MED4")
analysis_id = analyses["results"][0]["analysis_id"]   # choose one

cluster_result = genes_in_cluster(analysis_id=analysis_id)
# cluster_result["results"] is a list of {cluster_id, genes: [...], ...}

# Build gene_sets and a shared background (all genes that were clustered).
gene_sets = {}
all_genes = set()
for row in cluster_result["results"]:
    members = [g["locus_tag"] for g in row["genes"]]
    gene_sets[row["cluster_id"]] = members
    all_genes.update(members)
background = {c: list(all_genes) for c in gene_sets}  # shared universe

# TERM2GENE and Fisher.
term2gene = to_dataframe(
    genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)
)
df = fisher_ora(gene_sets, background, term2gene)
```

**MCP convenience:** The `cluster_enrichment` tool automates this pipeline in a single
call — pass `analysis_id`, `organism`, `ontology`, and `level`. Background defaults to
`cluster_union` (all clustered genes). See `docs://tools/cluster_enrichment`.

---

## 6. Code example — ortholog-group enrichment (non-DE)

Use `genes_by_homolog_group` to turn ortholog group memberships into gene sets, then test
against the full organism gene set as background.

```python
from multiomics_explorer.api import (
    genes_by_homolog_group, list_organisms, genes_by_ontology,
)
from multiomics_explorer.analysis.frames import to_dataframe
from multiomics_explorer import fisher_ora

# Gene sets: genes belonging to each ortholog group of interest.
homolog_result = genes_by_homolog_group(
    group_ids=["OG0001234", "OG0005678"],
    organisms=["MED4"],
)
gene_sets = {}
for row in homolog_result["results"]:
    gene_sets[row["group_id"]] = row["locus_tags"]

# Background: all organism genes.
org_result = list_organisms(verbose=False)
org_entry = next(o for o in org_result["results"] if o["name"] == "MED4")
organism_genes = org_entry["locus_tags"]   # full genome gene set
# (or fetch via run_cypher / resolve_gene enumeration if list_organisms doesn't expose locus_tags)

term2gene = to_dataframe(
    genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)
)
df = fisher_ora(gene_sets, organism_genes, term2gene)
```

---

## 7. Code example — custom gene list (simplest form)

Any dict of locus_tags works. Caller supplies the background.

```python
from multiomics_explorer.api import genes_by_ontology
from multiomics_explorer.analysis.frames import to_dataframe
from multiomics_explorer import fisher_ora

# Hand-curated or upstream-analysis gene sets.
gene_sets = {
    "nitrogen_responsive":  ["PMM0123", "PMM0456", "PMM0789"],
    "photosystem_II_repair": ["PMM1001", "PMM1002", "PMM1004"],
}
# Background: whatever pool these genes were drawn from.
background = my_candidate_universe   # list[str] — shared across all clusters

term2gene = to_dataframe(
    genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)
)
df = fisher_ora(gene_sets, background, term2gene)
```

---

## 8. BRITE enrichment

BRITE is a collection of hierarchical classification trees from KEGG. Unlike other ontologies,
BRITE encompasses multiple independent trees (enzymes, transporters, protein families, etc.),
each with its own hierarchy. Running all-BRITE enrichment without tree scoping is typically
dominated by enzymes (~1,776 terms at level 3), drowning out signal from smaller trees.

**Always scope BRITE enrichment to a specific tree using the `tree` parameter.**

### Worked example: transporter enrichment

```python
from multiomics_explorer.api import (
    list_filter_values, ontology_landscape, genes_by_ontology,
)
from multiomics_explorer import de_enrichment_inputs, fisher_ora
from multiomics_explorer.analysis.frames import to_dataframe

# Step 1: Discover available BRITE trees.
trees = list_filter_values("brite_tree")
# trees["results"] -> [{"value": "enzymes", "count": 1776},
#                       {"value": "transporters", "count": 84}, ...]

# Step 2: Check coverage for the target tree.
landscape = ontology_landscape(
    organism="MED4", ontology="brite", tree="transporters",
)
df_landscape = to_dataframe(landscape)
# Pick a level with good coverage — level=1 is BRITE category.

# Step 3: Build TERM2GENE scoped to transporters.
term2gene = to_dataframe(
    genes_by_ontology(
        ontology="brite", organism="MED4", level=1, tree="transporters",
    )
)

# Step 4: Run enrichment (same Fisher pipeline as any other ontology).
inputs = de_enrichment_inputs(
    experiment_ids=["exp1"], organism="MED4",
    direction="both", significant_only=True,
)
df = fisher_ora(inputs.gene_sets, inputs.background, term2gene)
```

The MCP tool supports the same workflow in a single call:

```
pathway_enrichment(
    organism="MED4",
    experiment_ids=[...],
    ontology="brite",
    tree="transporters",
    level=1,
)
```

The `tree` parameter is accepted by `search_ontology`, `genes_by_ontology`, `gene_ontology_terms`,
`ontology_landscape`, and `pathway_enrichment`. Use `list_filter_values("brite_tree")` to
discover valid tree names.

---

## 9. Choosing a background

The background defines the denominator of the test: which genes *could* have appeared in the
foreground? Getting it right matters more than the choice of ontology.

### `table_scope` (DE path default)

Each experiment quantifies a subset of the genome. Genes not in the quantified set cannot be
differentially expressed — they are structurally absent from the numerator. Using them in the
denominator inflates `N`, artificially depresses `bg_ratio`, and understates enrichment. The
`de_enrichment_inputs` function builds per-cluster backgrounds from `table_scope` automatically.

Use `table_scope` (the default) whenever your gene sets came from a DE table.

### `organism` background

The full organism gene set (all annotated loci). Use this when the gene set came from a
whole-genome analysis — for example, a genome-wide scan, a purely sequence-based partition, or
an analysis not tied to any quantification table. Inflate-denominator caveat: if only a fraction
of the genome was actually measured, the organism background overstates `N`.

### Custom list

Supply any `list[str]` to `fisher_ora`'s `background` parameter (shared across all clusters)
or a per-cluster `dict[str, list[str]]`. The rule is: the background should be the set of genes
that *could* have been selected for the foreground by the same process that produced it.

- For co-expression clustering, the background is the clustering universe (all genes that were
  fed into the clustering algorithm, not all genes in the genome).
- For manual curation, the background is the candidate pool the curator drew from.
- For ortholog-group enrichment, the background is the organism gene set (all genes could have
  been assigned to any group).

---

## 10. Choosing an ontology and level (narrative)

Use `ontology_landscape` (§3) to scout before committing to an ontology and level. The key
signals are:

- **`genome_coverage`** — fraction of the organism's genes that appear in at least one term at
  this level. Coverage below ~0.5 means that enrichment results will miss most of the biology.
  This is the dominant signal; avoid levels with poor coverage regardless of term-size
  distribution.
- **`median_genes_per_term`** — a term with 1 000 genes is nearly impossible to enrich
  meaningfully; a term with 2 genes is nearly impossible to pass `min_gene_set_size`. Aim for
  roughly 10–200 per term at the level you select.
- **`relevance_rank`** — composite score baking in both signals. Rank 1 is best. Supply
  `experiment_ids` to the landscape call to weight by experiment-specific coverage rather than
  genome-wide.

**Hierarchy-level convention:** `level=0` is the root (broadest term), higher integers are more
specific. A level-1 CyanoRak category is a broad functional class; level-2 is a sub-class.

**Tree-vs-DAG caveat:** CyanoRak, TIGR, and COG are trees — each term has a unique path from
root, so `level` is exact. GO is a directed acyclic graph (DAG) — a term may have multiple paths
from root of different lengths. `genes_by_ontology` uses min-path-from-root as a best-effort
proxy, flagging affected terms with `level_is_best_effort=True` in verbose output. Treat GO
level assignments as approximate.

---

## 11. Interpretation

### Signed enrichment score as a visualization scalar

`signed_score = sign × −log10(p_adjust)`, where sign is `+1` for upregulated clusters and `−1`
for downregulated clusters. This is a convenient single number for dot-plot or heatmap
visualizations. It conflates significance and direction into one axis.

**Caveat:** when a pathway is significantly enriched in *both* `up` and `down` clusters for the
same experiment, collapsing to a single `signed_score` loses information. Inspect both rows
before relying on the scalar alone. `signed_enrichment_score` picks the dominant direction (lower
`p_adjust` wins) and reports which direction was selected.

### Catch-all categories

Broad functional categories routinely achieve high enrichment scores because they contain many
genes and are almost always partially represented in a DE set. Known problematic categories in
CyanoRak:

- **R.2 "Conserved hypothetical proteins"** (B1 caveat C3) — large catch-all bucket. A
  significant result here often reflects the size of the category, not a coherent biological
  signal.
- **D.1 "Adaptation / acclimation"** — functionally heterogeneous; enrichment is expected across
  many treatments.

Interpret these categories cautiously. Consider filtering them or downweighting them in
visualizations. The `fold_enrichment` column (as opposed to raw `p_adjust`) is a better signal
for these buckets because it penalizes large `M`.

### Cross-experiment FDR

BH correction is applied **per cluster** (one experiment × one timepoint × one direction = one
cluster). It controls the false-discovery rate within that cluster's set of Fisher tests, not
across the full multi-experiment run.

Seeing the same pathway significantly enriched in many independent experiments (across
`by_experiment`) is biological replication, not a statistical artifact — it is strong evidence.
But no single statistical correction spans the whole run. If you want cross-experiment correction,
collect the per-cluster `pvalue` values and apply BH across the full table manually (B1 caveat C4).

---

## 12. Gotchas

- **`min/max_gene_set_size` means different things in different tools.** In `ontology_landscape`
  the filter is organism-scoped (pathway size across the whole genome; used to rank levels).
  In `pathway_enrichment` / `fisher_ora` it filters per-cluster **M** — the pathway's gene count
  within that specific cluster's background (clusterProfiler semantics). The parameter name is
  the same but the scope differs. Under `background='table_scope'`, a pathway can pass the filter
  in one cluster and be dropped in another because their backgrounds differ. That is intended.

- **`background='table_scope'` means per-cluster universes, not one shared universe.** Each
  cluster has its own background (the quantified gene set of that experiment). Cross-cluster
  comparisons of `fold_enrichment` carry the caveat that `N` differs per cluster. Do not average
  `fold_enrichment` across clusters from different experiments.

- **NaN timepoints become a cluster named `"NA"`.** When `differential_expression_by_gene`
  returns rows with a null timepoint (experiments without time-series structure), those rows are
  grouped under the timepoint key `"NA"` — not dropped. They appear in `by_experiment` and in
  result rows like any other timepoint. This is by design: you should see enrichment results for
  non-time-course experiments.

- **Timepoints do not align across experiments.** `T0` in experiment A is not the same
  biological time as `T0` in experiment B. That is why there is no `by_timepoint` breakdown in
  the envelope. If you need a cross-experiment axis, group by `treatment_type` or use
  `differential_expression_by_ortholog` to compare across organisms. Do not aggregate by raw
  timepoint string across experiments.

- **GO levels are best-effort.** Any GO term carrying `level_is_best_effort=True` in
  `genes_by_ontology` verbose output has an ambiguous depth because GO is a DAG. The level
  reported is the min-path from root. Two terms at the same `level` may represent very different
  degrees of specificity. Treat GO level uniformity as approximate; prefer CyanoRak, COG, or KEGG
  when exact level semantics matter.

---

## 13. Divergences from clusterProfiler

| Difference | This implementation | clusterProfiler |
|---|---|---|
| Background | Per-experiment `table_scope` (quantified gene set) | Single user-supplied universe |
| Ontology selection | `genome_coverage`-driven via `ontology_landscape` | Manual; no built-in coverage ranking |
| DAG-level honesty | `level_is_best_effort` flag on GO terms | GO levels used as-is |
| `min_gene_set_size` default | 5 (cyanobacterial genomes are small, ~2k genes) | 10 |
| q-value | Dropped — BH only | Storey q-value optionally computed |
| BH scope | Per-cluster (experiment × timepoint × direction) | Per-cluster in compareCluster |

The column names `gene_ratio`, `bg_ratio`, `rich_factor`, `fold_enrichment`, `count`, and
`bg_count` are deliberately clusterProfiler-compatible; `cluster` maps to clusterProfiler's
`Cluster`; `term_id` / `term_name` map to `ID` / `Description`. See §15 for the full mapping.

---

## 14. The MCP tool

`pathway_enrichment` is the DE-path convenience wrapper. It runs the full pipeline
(`de_enrichment_inputs` → `genes_by_ontology` → `fisher_ora` → attach direction →
`signed_enrichment_score`) in a single MCP call. It is the right choice when you want DE-driven
ORA from experiment IDs without writing Python.

For cluster-membership enrichment, use the `cluster_enrichment` MCP tool — it automates the
pattern from §5 in a single call. For ortholog groups or custom gene lists, use the Python
primitives directly.

Examples, parameter details, and chaining patterns are in `docs://tools/pathway_enrichment`.

---

## 15. Output field reference

### Fisher's 2×2 table

For a single (cluster, term) pair:

|                         | In pathway  | Not in pathway  | Total   |
| ----------------------- | ----------- | --------------- | ------- |
| **DE gene set**         | `a = k`     | `b = n − k`     | `n`     |
| **Background (not DE)** | `c = M − k` | `d = N − n − c` | `N − n` |
| **Total (background)**  | `M`         | `N − M`         | `N`     |

where `k = count`, `n = DE set size`, `M = bg_count` (pathway members in the cluster's
background), `N = background size`. The Fisher exact test (one-sided) asks whether `k` is larger
than expected under a uniform draw from the background.

### Result row fields

| Field | clusterProfiler | Meaning |
|---|---|---|
| `cluster` | `Cluster` | `"{experiment_id}\|{timepoint}\|{direction}"` cluster key |
| `term_id` | `ID` | Ontology term identifier |
| `term_name` | `Description` | Human-readable term label |
| `level` | — | Hierarchy depth of the term (0 = root, higher = more specific) |
| `count` | `Count` | `k` — DE genes in the pathway |
| `bg_count` | — | `M` — pathway members within the cluster's background |
| `gene_ratio` | `GeneRatio` | `"k/n"` string — DE genes in pathway over total DE genes in cluster |
| `gene_ratio_numeric` | — | `k/n` float |
| `bg_ratio` | `BgRatio` | `"M/N"` string — pathway members over background size |
| `bg_ratio_numeric` | — | `M/N` float |
| `rich_factor` | `RichFactor` | `k/M` — fraction of pathway's background members that are DE |
| `fold_enrichment` | `FoldEnrichment` | `(k/n) / (M/N)` — observed over null expectation; `>1` means enriched |
| `pvalue` | `pvalue` | Fisher exact p-value (one-sided, enrichment direction) |
| `p_adjust` | `p.adjust` | Benjamini-Hochberg FDR within the cluster |
| `signed_score` | — | `sign × −log10(p_adjust)`, sign from direction (up: +1, down: −1) |
| `foreground_gene_ids` | `geneID` (split) | `list[str]` — the `k` DE genes in the pathway (verbose only) |
| `background_gene_ids` | — | `list[str]` — pathway members in background not in DE set (verbose only) |

**Context fields (experiment-level, threaded per row):** `experiment_id`, `name`, `timepoint`,
`timepoint_hours`, `timepoint_order`, `direction`, `omics_type`, `table_scope`,
`treatment_type`, `background_factors`, `is_time_course` — all sourced from the experiment; see
`list_experiments` for field definitions.

### Envelope fields

| Field | Meaning |
|---|---|
| `total_matching`, `returned`, `truncated`, `offset` | Pagination. `total_matching` is the pre-pagination row count — one row equals one Fisher test |
| `n_significant` | Rows with `p_adjust < pvalue_cutoff` |
| `by_experiment` | Per-experiment `{n_tests, n_significant, n_clusters}` plus experiment metadata |
| `by_direction` | Per-direction `{n_tests, n_significant}` |
| `by_omics_type` | Per-omics-type `{n_tests, n_significant}` |
| `cluster_summary` | `n_clusters` + min/median/max of `n_tests`, `n_significant`, `universe_size` across clusters |
| `top_clusters_by_min_padj` | Top 5 clusters by their smallest `p_adjust`, with full metadata |
| `top_pathways_by_padj` | Top 10 (cluster, term) pairs by `p_adjust` across all clusters. `results` is globally sorted by `p_adjust` asc, so pagination recovers positions 11+ |
| `not_found` | Requested `experiment_ids` absent from the KG |
| `not_matched` | Experiment IDs found but belonging to a different organism |
| `no_expression` | Experiment matches organism but has no DE rows (reuses DE tool's term) |
| `term_validation` | Namespaced `{not_found, wrong_ontology, wrong_level, filtered_out}` for `term_ids` (passthrough from `genes_by_ontology`) |
| `clusters_skipped` | Clusters with `{cluster, reason}`: `empty_gene_set`, `no_pathways_in_size_range`, `empty_background` |

---

## 16. Deferred methodology

The following approaches are not implemented but are natural next steps:

- **GSEA (gene-set enrichment analysis)** — rank-based; captures graded DE signals rather than
  binary significant/not significant cut-offs.
- **`simplify()` / GOSemSim** — remove redundant GO terms from ORA results using semantic
  similarity.
- **topGO `elim` / `weight` algorithms** — account for GO DAG structure during testing rather
  than after (reduces dependency inflation for GO-specific enrichment).
- **`gson` export** — interoperability with clusterProfiler's file format for downstream R
  workflows.

---

## 18. `EnrichmentResult` — rich return type

Both `pathway_enrichment` and `cluster_enrichment` return an `EnrichmentResult`
object (not a dict). `fisher_ora` also returns one when called directly.

**Attributes:**
- `result.results` — pandas DataFrame, one row per (cluster × term).
- `result.inputs` — `EnrichmentInputs` (gene_sets, background, cluster_metadata,
  optional `gene_stats`).
- `result.term2gene` — DataFrame used for overlap computation and GeneRef data.
- `result.params` — dict of ORA parameters for reproducibility.
- `result.kind` — `"pathway"` or `"cluster"`.

**Accessors** (only methods that join results + inputs or compute something
non-trivial; pure slicing uses `result.results` directly):
- `explain(cluster, term_id) -> EnrichmentExplanation` — full narrative +
  Fisher numbers + sorted gene refs. `_repr_markdown_` renders in Jupyter.
- `overlap_genes(cluster, term_id) -> list[GeneRef]` — the k genes.
- `background_genes(cluster, term_id) -> list[GeneRef]` — the M genes.
- `cluster_context(cluster) -> dict` — metadata + n_tests + n_significant.
- `why_skipped(cluster) -> str | None` — reason from clusters_skipped.
- `to_compare_cluster_frame() -> pd.DataFrame` — clusterProfiler convention
  (`Cluster`, `ID`, `Description`, `GeneRatio`, `BgRatio`, `pvalue`, `p.adjust`, `geneID`).
- `missing_terms() -> dict[str, list[str]]` — term_validation buckets.
- `generate_summary() -> dict` — aggregate view (no rows, no pagination).
- `to_envelope(*, summary=False, limit=None, offset=0) -> dict` —
  MCP-compatible dict. Called internally by MCP tool wrappers; Python
  callers rarely need it.

**Pydantic models:** `DEStats`, `GeneRef`, `EnrichmentExplanation` — see
module docstrings for field semantics.

**`term2gene` required vs optional columns:**

| Column | Status | Used by |
|---|---|---|
| `term_id` | required | Fisher math |
| `term_name` | required | Narrative |
| `locus_tag` | required | Fisher math |
| `gene_name` | *optional* | `GeneRef.gene_name` (None if absent) |
| `product` | *optional* | `GeneRef.product` (None if absent) |
| `level` | *contextual* | Pass-through from `genes_by_ontology` (ontology hierarchy level). Not read by Fisher; available on `result.term2gene` for downstream filtering. |
| `gene_category` | *contextual* | Pass-through from `genes_by_ontology` (gene's KG category). Same: not read by Fisher; surfaces in the DataFrame for downstream use. |

Custom-built term2gene works — missing optional columns just yield `None`
GeneRef fields. Additional columns (beyond required + optional + the
contextual ones above) flow through unchanged: `fisher_ora` reads only the
required columns and ignores the rest.

**`fisher_ora` signature change:** takes `EnrichmentInputs` + `term2gene` and
returns `EnrichmentResult`. Callers without a KG construct `EnrichmentInputs`
with just `gene_sets`, `background`, `organism_name`; `gene_stats` defaults
to empty.

**MCP schema change:** the `verbose` parameter was removed from
`pathway_enrichment` and `cluster_enrichment` tool schemas (it was phantom
— stripping columns that were never populated). Rich per-row overlap lives
in the Python API (`.explain()` / accessors).

---

## 19. References

- **yulab-smu biomedical knowledge mining book:**
  https://yulab-smu.top/biomedical-knowledge-mining-book/
- Xu, S. et al. Using clusterProfiler to characterize multiomics data. *Nat Protoc* **19**,
  3292–3320 (2024). doi:10.1038/s41596-024-01020-z
- Yu, G. et al. clusterProfiler: an R Package for Comparing Biological Themes Among Gene
  Clusters. *OMICS* **16**, 284–287 (2012).
- B1 analysis: `multiomics_research/analyses/2026-04-09-1713-pathway_enrichment_b1/`
- Runnable examples: `docs://examples/pathway_enrichment.py`
