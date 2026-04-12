# `pathway_enrichment` Design Spec

**Status:** Draft
**Date:** 2026-04-12
**Parent spec:** [2026-04-12-kg-enrichment-surface-design.md](2026-04-12-kg-enrichment-surface-design.md)
**Depends on:** [Child 1](2026-04-12-ontology-landscape-design.md) (hierarchy helper) + [Child 2](2026-04-12-genes-by-ontology-redefinition-design.md) (`genes_by_ontology` redefinition — referenced in methodology doc examples)
**Scope:** Child 3 of the KG enrichment surface work. One new MCP tool, two new L1/L2 primitives, one new MCP resource.

## What's in this spec

1. **`pathway_contingency_counts_query`** — new L1 builder. Returns per-pathway `(a, b, c, d)` counts for Fisher.
2. **`pathway_enrichment` MCP tool** — new. End-to-end ORA: Fisher + BH + signed score + NaN handling.
3. **`signed_enrichment_score` util** — new L2 standalone function.
4. **`multiomics_explorer/analysis/enrichment.md`** — new MCP resource at `docs://analysis/enrichment`. Methodology reference.

## Architectural principle

Counts in Cypher, math in Python. Fisher-exact needs four integers per pathway `(a, b, c, d)` — those are aggregate counts over graph patterns, not gene lists. The KG's job is to serve counts; scipy's job is to test them.

Concretely: `pathway_contingency_counts_query` returns one row per pathway with `(pathway_id, pathway_name, a, b, c, d, M)`. L2 runs Fisher + BH on the resulting DataFrame. No (gene × term) payload is pulled into pandas just to count intersections.

## `pathway_contingency_counts_query` (L1)

**Signature:**

```
pathway_contingency_counts_query(
    ontology: str,
    level: int,
    organism: str,
    de_locus_tags: list[str],
    background_locus_tags: list[str],
    min_gene_set_size: int,
    max_gene_set_size: int,
) -> tuple[str, dict]
```

**Returns one row per pathway:**
- `pathway_id, pathway_name`
- `a` — DE genes in pathway (k)
- `b` — DE genes not in pathway
- `c` — non-DE background genes in pathway
- `d` — non-DE background genes not in pathway
- `M` — total pathway size within the background (a + c)
- `gene_count` — total pathway size genome-wide (may differ from M when the background is narrower than the genome)

**Filtering:** pathways with `M < min_gene_set_size` or `M > max_gene_set_size` are excluded at the Cypher layer, not post-hoc in Python. Saves roundtripping large irrelevant pathways.

**Hierarchy expansion:** uses Child 1's unified hierarchy helper to map leaf annotations up to level-N pathways.

**Single query per call.** Not one per pathway.

## `pathway_enrichment` MCP tool

### Signature

```
pathway_enrichment(
    organism: str,
    experiment_ids: list[str],
    ontology: str,
    level: int,
    direction: str = 'both',  # 'up' | 'down' | 'both'
    min_gene_set_size: int = 5,
    max_gene_set_size: int = 500,
    pvalue_cutoff: float = 0.05,
    background: str | list[str] = 'table_scope',
    timepoint_filter: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,  # MCP default 100
    offset: int = 0,
)
```

**Groups tested:** cartesian of `experiment_ids × timepoints-present × direction`. `direction='both'` runs up and down separately; `signed_enrichment_score` (below) can collapse.

### Background (universe)

- `'table_scope'` (default): per-experiment quantified gene set. Per B1 decision D2: an unquantified gene cannot be DE, so it shouldn't inflate the denominator.
- `'organism'`: full organism gene set.
- `list[str]`: explicit locus_tag list (escape hatch for custom backgrounds).

Each cluster can have a different universe size when `background='table_scope'`, because `table_scope` varies per experiment. Response surfaces this per-cluster.

### Single-organism enforcement

Mirrors `differential_expression_by_gene`. Enrichment across organisms is not meaningful — different gene universes, different pathway memberships. `ValueError` at L2 if `experiment_ids` span multiple organisms.

### NaN-timepoint handling

If an experiment's DE table uses NaN timepoints (Steglich, Tolonen cyanate, Tolonen urea per B1), they are treated as a single group named `"NA"`. **Not silently dropped** (this was the B1 NaN bug).

### Each result row (long format, compareCluster-compatible)

- `cluster` — `"{experiment_id}|{timepoint}|{direction}"`
- `experiment_id`, `timepoint`, `direction` — also as separate columns
- `term_id`, `term_name`
- `gene_ratio` — `"k/n"` string
- `gene_ratio_numeric` — k/n float
- `bg_ratio` — `"M/N"` string
- `bg_ratio_numeric` — M/N float
- `rich_factor` — k/M
- `fold_enrichment` — (k/n) / (M/N)
- `pvalue`, `p_adjust` (BH within cluster), `qvalue` (Storey, optional; null if unavailable from statsmodels)
- `count` — k
- `bg_count` — M
- `gene_ids` — "/"-separated locus_tags of k DE genes in pathway (**verbose only**)
- `signed_score` — `sign × -log10(p_adjust)`; sign from the dominant direction when `direction='both'` and both sides are tested

**Row sort order:** by `p_adjust` ascending within each cluster, then clusters ordered by `experiment_id, timepoint, direction`. Stable across limit/offset calls.

**BH scope:** applied per `cluster` group (matches B1; matches clusterProfiler's compareCluster convention inferred from their source).

### Response envelope

- `results` — per-(cluster × pathway) rows (or `[]` when `summary=True`).
- `returned`, `total_rows`, `truncated`, `offset`.
- `n_tests` — total Fisher tests run (= `total_rows` pre-filter).
- `n_significant` — count with `p_adjust < pvalue_cutoff`.
- `top_pathways_by_padj` — top N across all clusters (always present, independent of pagination).
- `by_experiment`, `by_direction`, `by_timepoint` — significance counts.
- `by_cluster` — per-cluster `{n_tests, n_significant, universe_size}`.
- `not_found` — experiment_ids requested but absent from the KG.
- `not_matched` — experiment_ids found but not matching `organism` or lacking DE data.
- `clusters_skipped` — clusters with zero pathways ≥ `min_gene_set_size` after background intersection.

## `signed_enrichment_score` (L2 standalone util)

```
signed_enrichment_score(
    df: pd.DataFrame,
    direction_col: str = 'direction',
    padj_col: str = 'p_adjust',
) -> pd.DataFrame
```

**Role:** collapse up/down rows into a single signed score per `(cluster-without-direction, term_id)`. Signed score = `sign × -log10(padj)`; sign from whichever direction has the smaller `padj` when both are significant.

**Standalone so callers can recompute after filtering.** Not internal-only to `pathway_enrichment` because the signed score is a visualization primitive that analysts re-derive under different cutoffs.

**Import path:** `from multiomics_explorer import signed_enrichment_score`.

## MCP resource `docs://analysis/enrichment`

**Canonical file:** `multiomics_explorer/analysis/enrichment.md`. Single source; served as the MCP resource following the V2 resource pattern (matches `docs://analysis/response_matrix`).

### Outline

1. **When to use enrichment.** DE result → which pathways are overrepresented?
2. **Tool sequence:**
   - `ontology_landscape` — pick ontology + level by `relevance_rank`.
   - `genes_by_ontology(level=N)` — inspect pathway definitions, sanity-check marker genes.
   - `pathway_enrichment` — run the tests.
3. **Ontology selection methodology:**
   - Hierarchy level convention: `level=0` is root (broadest), higher integers more specific. Terms at level N have N ancestors.
   - `genome_coverage` is required (not optional) — term-size stats alone are misleading.
   - Tree-vs-DAG caveat (CyanoRak/TIGR/COG: tree-native; GO: best-effort).
   - Per-experiment coverage caveat when experiment sizes vary (Steglich's 198-gene DE universe vs. MED4's 1,976 genome).
4. **Background set:**
   - Why `table_scope` (cite B1 decision D2).
   - When to use `organism` instead.
   - Custom locus_tag lists as escape hatch.
5. **Interpretation:**
   - Signed score as a visualization scalar; caveat when both directions significant.
   - Catch-all categories (B1 caveat C3: R.2 "Conserved hypothetical proteins", D.1 "Adaptation/acclimation").
   - Cross-experiment FDR (B1 caveat C4: BH is within-cluster; biological replication across experiments provides confidence, not statistical correction).
6. **Divergences from clusterProfiler:**
   - Per-experiment `table_scope` background (not a single universe).
   - `genome_coverage`-driven ontology selection.
   - Tree-vs-DAG honesty in tool output.
   - `min_gene_set_size=5` default (not 10).
7. **Deferred methodology** (pointers, not implementations):
   - GSEA for rank-based enrichment.
   - `simplify()` / GOSemSim for GO-DAG redundancy collapse.
   - topGO elim/weight.
   - `gson` export for round-tripping to R.
8. **References:**
   - yulab-smu biomedical-knowledge-mining book: https://yulab-smu.top/biomedical-knowledge-mining-book/
   - Xu, S. et al. *Nat Protoc* 19, 3292–3320 (2024). doi:10.1038/s41596-024-01020-z
   - Yu, G. et al. clusterProfiler. *OMICS* 16, 284–287 (2012).
   - B1 analysis: `multiomics_research/analyses/2026-04-09-1713-pathway_enrichment_b1/`

### Resource registration

Register as a static MCP resource (see project backlog: "MCP resource templates don't list — register static resources for discoverability").

## YAML about-content

`inputs/tools/pathway_enrichment.yaml`:

- **examples:**
  - Single experiment, default direction='both', table_scope background.
  - Multi-experiment compareCluster analog: list of 10 experiments, one call.
  - `summary=True` for breakdowns only (`by_experiment`, `top_pathways_by_padj`).
  - `verbose=True` to include `gene_ids` for downstream gene-level followup.
- **chaining:**
  - `ontology_landscape → genes_by_ontology(level=N) → pathway_enrichment` (full pipeline).
  - `pathway_enrichment → gene_overview` (drill from enriched pathway's `gene_ids` into gene details).
  - `differential_expression_by_gene → pathway_enrichment` (DE results motivate enrichment).
- **verbose_fields:** `gene_ids`.
- **mistakes:**
  - "Default background is `table_scope` (per-experiment quantified set). Using `'organism'` inflates the denominator and underestimates enrichment. See `docs://analysis/enrichment` for the full methodology note."
  - "BH correction is per-cluster (experiment × timepoint × direction), NOT across clusters. Cross-experiment FDR is biological replication, not statistical."
  - "Single-organism enforced. Enrichment across organisms is not meaningful — run separate calls per organism."
  - "When `direction='both'` and a pathway is enriched up AND down significantly, `signed_score` retains only the dominant direction. Full bidirectional info is in the per-direction rows."
  - wrong: `"pathway_enrichment(..., background='genome')"  # not a valid string`
    right: `"pathway_enrichment(..., background='organism')  # or 'table_scope' (default), or a locus_tag list"`

## Tests

- **Unit:**
  - Fisher + BH math: mock L1 output, assert p_adjust values match scipy+statsmodels reference.
  - Signed score: up-only row, down-only row, both-significant (dominant direction wins).
  - NaN-timepoint grouping: synthetic DE with NaN timepoints produces a single `"NA"` cluster, not dropped.
  - Single-organism validation: mixed-organism experiment_ids → `ValueError`.
- **Integration (`-m kg`):**
  - B1 reproduction: MED4 × CyanoRak level 1 × 10 experiments × `direction='both'` should produce ≥ the 18 unique enriched pathways the B1 analysis found. Exact count may drift with KG rebuilds; assert key pathways (E.4 N-metabolism, J.1–J.8 photosynthesis, K.2 ribosomal) appear where expected.
  - NaN-timepoint experiments (Steglich, Tolonen cyanate, Tolonen urea): present in `by_cluster` with non-null counts.
  - `clusters_skipped` reported for deliberately-undersized test cases.
- **Regression fixtures:** freeze the B1 reproduction in `tests/regression/`. Regenerate after any KG rebuild.

## Layer-rules compliance

- L1: `pathway_contingency_counts_query` returns `tuple[str, dict]`. No execution, no formatting.
- L2: `pathway_enrichment()` builds full response dict. Orchestrates DE fetch (reuses existing `differential_expression_by_gene` builders), contingency-counts query, Fisher (`scipy.stats.fisher_exact`), BH (`statsmodels.stats.multitest.multipletests(method='fdr_bh')`), signed score. Single-organism validation.
- L3: thin MCP wrapper. Pydantic response model. Default `limit=100`. `await ctx.info/warning` for batch / skipped-cluster messages.
- L4: skill reference auto-generated.

## Out of scope for this spec

- `ontology_landscape` — Child 1.
- `genes_by_ontology` redefinition — Child 2.
- Unified hierarchy helper — Child 1 (this spec consumes it).
- GSEA / rank-based methods — parent spec's out-of-scope list.
- Enrichment visualizations — callers plot; we return data.

## Open questions deferred to plan stage

- `qvalue` computation (Storey): include only if statsmodels offers it trivially; otherwise leave the column null. Decision deferred to implementation.
- Whether `pathway_enrichment` should accept an explicit `pathway_definitions` DataFrame as an escape hatch (caller-supplied TERM2GENE). Leaning no — scope creep, and `genes_by_ontology(level=N)` already supplies it.
- Whether `top_pathways_by_padj` N should be configurable (default hard-coded to 10 or 20?).
- `clusters_skipped` shape — list of cluster strings, or dict with reason? Match existing conventions during planning.
