# `pathway_enrichment` Design Spec

**Status:** Draft (rewritten 2026-04-15 after Children 1 + 2 landed)
**Date:** 2026-04-12 (full rewrite 2026-04-15)
**Parent spec:** [2026-04-12-kg-enrichment-surface-design.md](2026-04-12-kg-enrichment-surface-design.md)
**Depends on (shipped):**
- Child 1 — `ontology_landscape` + `_hierarchy_walk` helper (2026-04-14).
- Child 2 — `genes_by_ontology` redefined as TERM2GENE long-format with four validation buckets (2026-04-14, branch `feat/genes-by-ontology-redefinition`).

**Scope:** Child 3 of the KG enrichment surface work. One new MCP tool, one new package module, zero new L1 builders.

## What's in this spec

1. **`multiomics_explorer/analysis/enrichment.py`** — new package module with three public functions + one dataclass. Gene-list-first primitive; DE path is a convenience wrapper.
2. **`pathway_enrichment` MCP tool** — thin wrapper over the package. DE-driven ORA end-to-end.
3. **Two documentation outputs:**
   - **Tool-about reference** auto-generated from `inputs/tools/pathway_enrichment.yaml`. Audience: MCP tool caller. Signature + examples + chaining + mistakes.
   - **Methodology doc** at `multiomics_explorer/analysis/enrichment.md`, served as `docs://analysis/enrichment`. Audience: Python user. Building blocks + code examples (DE, cluster, ortholog, custom gene lists) + biological methodology.
4. **`examples/pathway_enrichment.py`** — runnable collateral for the methodology doc's code examples, exercised by an integration test.

## What's not in this spec

- No new L1 Cypher builders. Every KG access reuses shipped builders (`differential_expression_by_gene`, `genes_by_ontology`, organism gene-count helpers).
- `pathway_contingency_counts_query` from the 2026-04-12 draft is **deleted** — redundant once `genes_by_ontology` emits TERM2GENE directly.

## Framing

Enrichment is fundamentally a **gene-list-against-pathway** operation. The enrichment primitive knows nothing about DE, experiments, table-scope, or the KG. It takes gene sets, a background, and a TERM2GENE map, and runs Fisher + BH.

The MCP tool is the DE-wired convenience (reproduces B1 in one call; the common case). Python callers (research repo, notebooks, cluster-membership analyses, custom gene lists) import the primitive directly.

## Architectural principle

Counts via existing L1 builders; math in Python. Cyanobacterial genomes are small (~2k genes); even 200 clusters × 500 pathways × pandas intersection is microseconds. Adding a bespoke Cypher contingency query buys no performance and doubles the surface.

## Package layout — `multiomics_explorer/analysis/enrichment.py`

Four public names, all importable from `multiomics_explorer`:

### `EnrichmentInputs` (dataclass)

```python
@dataclass
class EnrichmentInputs:
    organism_name: str                       # single-organism (enforced)
    gene_sets: dict[str, list[str]]          # cluster -> foreground locus_tags
    background: dict[str, list[str]]         # cluster -> universe locus_tags (per-cluster)
    cluster_metadata: dict[str, dict]        # cluster -> metadata dict (see fields below)
```

`cluster_metadata[cluster]` carries the compact field set:

```
experiment_id, name,
timepoint, timepoint_hours, timepoint_order,
direction,
omics_type, table_scope,
treatment_type, background_factors, is_time_course
```

### `de_enrichment_inputs(...)` — DE → EnrichmentInputs

```python
def de_enrichment_inputs(
    experiment_ids: list[str],
    organism: str,                           # required — single-organism enforced
    direction: str = 'both',                 # 'up' | 'down' | 'both'
    significant_only: bool = True,
    timepoint_filter: list[str] | None = None,
    *, conn=None,
) -> EnrichmentInputs
```

**Single-organism enforced** via `_validate_organism_inputs(organism, locus_tags=None, experiment_ids, conn)` — same contract as `differential_expression_by_gene` and `pathway_enrichment`. Mixed-organism `experiment_ids` raises `ValueError`. Experiments not belonging to `organism` raise `ValueError` (not silently dropped — the returned `EnrichmentInputs` has a single `organism_name`, so the validation is meaningful).

One `differential_expression_by_gene` call (without `significant_only` filter to get the full universe). Partitions rows by `(experiment_id, timepoint, direction)` into clusters named `"{experiment_id}|{timepoint}|{direction}"`. NaN timepoints group as `"NA"` (not dropped). `gene_sets` uses `significant_only` semantics; `background` is always the full per-cluster quantified set (the table_scope universe).

### `fisher_ora(...)` — the primitive

```python
def fisher_ora(
    gene_sets: dict[str, list[str]],
    background: dict[str, list[str]] | list[str],   # per-cluster OR shared universe
    term2gene: pd.DataFrame,                        # see column contract below
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
) -> pd.DataFrame
```

**Size filter is per-cluster on M (background-scoped pathway size).** For each (cluster, term), compute `M = |pathway_members ∩ cluster_background|`. Drop (cluster, term) pairs where `M < min_gene_set_size` or `M > max_gene_set_size`. This matches clusterProfiler's ORA semantics. A given pathway can be tested in one cluster and dropped in another when `background='table_scope'` varies per cluster — that's the intended behavior. `max_gene_set_size=None` disables the upper bound.

**`term2gene` column contract.**
- **Required:** `term_id` (str), `term_name` (str), `locus_tag` (str).
- **Optional (passed through to output rows):** `level` (int), any other column present on the input frame.

Designed so the idiomatic chain just works:

```python
from multiomics_explorer.analysis.frames import to_dataframe
from multiomics_explorer.api import genes_by_ontology

gbo = genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)
term2gene = to_dataframe(gbo)                       # -> DataFrame with the needed columns
df = fisher_ora(gene_sets, background, term2gene)   # no manual column renaming
```

`genes_by_ontology` is the canonical TERM2GENE source, but any DataFrame with the required columns works (clusterProfiler's `TERM2GENE` frames, hand-curated CSVs, custom ontology annotations).

Pure pandas/scipy. Direction-agnostic. For each (cluster, term): Fisher-exact (scipy) + BH within cluster (statsmodels `fdr_bh`). Output is long-format DataFrame with compareCluster-compatible columns. Size filter applied per-cluster to the pathway's count within that cluster's background. `signed_score` is **not** computed here — it requires direction, which this primitive doesn't know about. Callers compute it in one of two ways:

- Post-hoc: pass the result DataFrame (with a `direction` column attached from their own metadata) to `signed_enrichment_score`, which re-derives the signed score.
- Inline: the api-layer `pathway_enrichment` wrapper attaches `direction` from `cluster_metadata` and computes `signed_score = sign × -log10(p_adjust)` directly.

### `signed_enrichment_score(...)` — util

```python
def signed_enrichment_score(
    df: pd.DataFrame,
    direction_col: str = 'direction',
    padj_col: str = 'p_adjust',
) -> pd.DataFrame
```

Collapse `|up`/`|down` cluster pairs into one row per `(stem, term)`. Sign from the direction with the smaller `p_adjust`; score = `sign × -log10(min_padj)`. Standalone so callers re-derive under new cutoffs.

## `pathway_enrichment` MCP tool

### Signature

```python
pathway_enrichment(
    organism: str,
    experiment_ids: list[str],
    ontology: str,
    level: int | None = None,               # at least one of level/term_ids required
    term_ids: list[str] | None = None,
    direction: str = 'both',                # 'up' | 'down' | 'both'
    significant_only: bool = True,
    background: str | list[str] = 'table_scope',   # 'table_scope' | 'organism' | locus_tags
    min_gene_set_size: int = 5,
    max_gene_set_size: int = 500,
    pvalue_cutoff: float = 0.05,
    timepoint_filter: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,               # MCP default 100
    offset: int = 0,
)
```

### Size-filter semantics

`min_gene_set_size` / `max_gene_set_size` filter on **M**, the pathway's gene count within the current cluster's background (the "a + c" cell of Fisher's 2×2). Matches clusterProfiler. Key consequences:

- The filter is **per-cluster**, not global. Under `background='table_scope'` (default), different clusters have different backgrounds, so a pathway may be tested in one cluster and dropped in another. Intended.
- **Distinct from `ontology_landscape`'s filter**, which is organism-scoped (used for ranking levels by `genome_coverage`). Same parameter name, different scope. Document in the methodology note.
- **`pathway_enrichment` calls `genes_by_ontology` with wide bounds** internally (`min_gene_set_size=0`, `max_gene_set_size=None`) so the organism-scoped filter doesn't pre-exclude pathways that would have been valid under M. The caller's bounds apply only in `fisher_ora`.
- `max_gene_set_size=None` disables the upper bound (useful for inspection / debugging).

### Error handling

Three failure categories, handled differently:

#### 1. Input validation (raise `ValueError` at L2; MCP `ToolError` at L3)

Caller-fixable mistakes. Fail fast before any KG call.

- `ontology not in ALL_ONTOLOGIES`.
- `level is None and not term_ids` (mirrors `genes_by_ontology`).
- `direction not in {'up', 'down', 'both'}`.
- `background` neither `'table_scope'` / `'organism'` nor a non-empty `list[str]`.
- `min_gene_set_size < 0`; `max_gene_set_size < min_gene_set_size` when `max_gene_set_size is not None`.
- `not (0 < pvalue_cutoff < 1)`.
- `experiment_ids` empty list → `ValueError("at least one experiment_id required")`.
- Mixed-organism `experiment_ids`, or experiments not belonging to `organism` → raised by `_validate_organism_inputs` and propagated.
- Ambiguous organism fuzzy match → raised by `_validate_organism_inputs` and propagated.

#### 2. Partial success (surface in envelope, do not raise)

Sub-tool validation buckets become envelope fields. The tool returns a successful response with the problem locations called out, rather than refusing to run.

- Some `experiment_ids` absent from KG → `not_found`.
- Some `experiment_ids` exist but wrong organism or no DE rows → `not_matched`.
- Some `term_ids` absent / wrong ontology / wrong level → `term_validation.not_found` / `.wrong_ontology` / `.wrong_level` (namespaced passthrough from `genes_by_ontology`).
- A cluster has empty `gene_sets[cluster]` (e.g., `significant_only=True` and no hits) → `clusters_skipped` with `reason="empty_gene_set"`.
- A cluster has no pathways passing the M filter → `clusters_skipped` with `reason="no_pathways_in_size_range"`.
- A cluster has empty background → `clusters_skipped` with `reason="empty_background"`.

When any validation bucket is non-empty, the MCP wrapper calls `await ctx.warning(...)` with a compact summary. `results` may still be non-empty if some clusters succeeded.

#### 3. Vacuous success (return valid empty envelope, do not raise)

The call is well-formed but yields zero rows. Return the full envelope with `results=[]`, all `by_*` breakdowns empty or zeroed, `n_tests=0`, `n_significant=0`. Caller can distinguish from "error" by the success status.

Triggers:
- All experiments in `not_found` / `not_matched` → empty `gene_sets`, empty `results`. `clusters_skipped` lists every requested cluster.
- `genes_by_ontology` returns zero rows (e.g., `ontology='cog_category', level=3` — flat ontology at non-existent level). Surfaced via `term_validation` where applicable; `results=[]`.
- Every cluster is in `clusters_skipped`.

#### 4. Propagated errors (do not swallow)

Let these bubble up:
- Neo4j connection errors, query timeouts, transaction memory-cap violations.
- Unexpected `TypeError` / `KeyError` from malformed sub-tool responses (indicates a bug, not a user error).

Rationale: swallowing infrastructure errors into the envelope hides real problems; they have different remediation than validation or data-shape issues.

#### Observability — `ctx.info` / `ctx.warning`

- `ctx.info` at: DE fetch complete (`N experiments, M DE rows`), TERM2GENE fetch complete (`K pathways`), Fisher complete (`P tests, Q significant`).
- `ctx.warning` at: any non-empty validation bucket (experiments or terms); any `clusters_skipped`; significance share below a low threshold (e.g., <1% of tests significant — signal that bounds might be too tight).

### Pipeline (api/ layer)

1. Validate inputs.
2. `inputs = de_enrichment_inputs(experiment_ids, organism, direction, significant_only, timepoint_filter)`.
3. Resolve background:
   - `'table_scope'` (default): use `inputs.background` as-is (per-cluster universe).
   - `'organism'`: fetch organism locus_tags once; broadcast to every cluster.
   - `list[str]`: broadcast caller-supplied list to every cluster.
4. `gbo_result = genes_by_ontology(ontology, organism, level, term_ids, min_gene_set_size=0, max_gene_set_size=None)`. Wide bounds intentional — the real size filter is M-based and happens in `fisher_ora`. Collect its validation buckets for envelope passthrough. Build `term2gene` DataFrame via `to_dataframe(gbo_result)` — same chain exposed to Python callers.
5. `df = fisher_ora(inputs.gene_sets, background, term2gene, min_gene_set_size, max_gene_set_size)`.
6. Attach cluster metadata (one row-level join against `cluster_metadata`) to `df`. Compute `signed_score = sign × -log10(p_adjust)` using the row's `direction` (up → +, down → −).
7. Assemble response envelope. Apply `limit`/`offset` for pagination.

**BH scope:** applied per cluster (matches clusterProfiler's compareCluster convention; matches B1).

## Result row shape

### Always present (compact)

```
cluster,
experiment_id, name,
timepoint, timepoint_hours, timepoint_order,
direction,
omics_type, table_scope,
treatment_type, background_factors, is_time_course,
term_id, term_name, level,
gene_ratio, gene_ratio_numeric,
bg_ratio, bg_ratio_numeric,
rich_factor, fold_enrichment,
pvalue, p_adjust,
count, bg_count,
signed_score
```

- `cluster` = `"{experiment_id}|{timepoint}|{direction}"`.
- `gene_ratio` = `"k/n"` string; `gene_ratio_numeric` = k/n float.
- `bg_ratio` = `"M/N"` string; `bg_ratio_numeric` = M/N float.
- `rich_factor` = k/M. `fold_enrichment` = (k/n) / (M/N).
- `signed_score` = `sign × -log10(p_adjust)`, sign from row's `direction` (up → +, down → −).

### Verbose only (drill-down payload)

```
foreground_gene_ids: list[str]    # k DE genes in this pathway
background_gene_ids: list[str]    # pathway members in background NOT in DE set (non-overlapping)
```

`background_gene_ids` can be large (up to `max_gene_set_size − k`). Verbose-only keeps default payloads lean.

### Explicitly not on rows

- `qvalue` — dropped. Callers wanting Storey q-values run them on the returned DataFrame.
- Free-text / niche experiment fields (`treatment`, `control`, `statistical_test`, `experimental_context`, `growth_phases`, `medium`, `light_condition`, `light_intensity`, `temperature`, `coculture_partner`, `table_scope_detail`) — look up via `list_experiments` by `experiment_id`.

### Sort order

**Global sort by `p_adjust` asc across all clusters.** Tie-break: `cluster` asc, then `term_id` asc. Stable across `limit/offset` pagination.

Rationale: with `limit=100` default, callers see the top 100 most-significant hits across the entire study, not 100 rows from the alphabetically-first cluster. Matches the analytical workflow ("show me what's enriched anywhere") rather than a per-cluster scan.

Callers who want per-cluster grouping do it in pandas: `df.sort_values(['cluster', 'p_adjust']).groupby('cluster')`.

## Response envelope

```python
{
    # Echo
    "organism_name": "MED4",
    "ontology": "cyanorak_role",
    "level": 1,

    # Counts
    "total_rows": 1040,                # (cluster × term) rows post-size-filter
    "returned": 100,
    "truncated": True,
    "offset": 0,
    "n_tests": 1040,                   # = total_rows
    "n_significant": 87,               # rows with p_adjust < pvalue_cutoff

    # Breakdowns
    "by_experiment": [
        {"experiment_id": ..., "name": ..., "omics_type": ..., "table_scope": ...,
         "treatment_type": ..., "background_factors": ..., "is_time_course": ...,
         "n_tests": ..., "n_significant": ..., "n_clusters": ...},
        ...
    ],
    "by_direction": [
        {"direction": "up", "n_tests": ..., "n_significant": ...},
        {"direction": "down", "n_tests": ..., "n_significant": ...},
    ],
    "by_omics_type": [
        {"omics_type": "transcriptomics", "n_tests": ..., "n_significant": ...},
        ...
    ],
    "cluster_summary": {
        "n_clusters": 200,
        "n_tests_min": 18, "n_tests_median": 52, "n_tests_max": 68,
        "n_significant_min": 0, "n_significant_median": 4, "n_significant_max": 17,
        "universe_size_min": 198, "universe_size_median": 1543, "universe_size_max": 1976,
    },
    "top_clusters_by_min_padj": [      # top 5
        {"cluster": "exp3|T4|up",
         "experiment_id": ..., "name": ...,
         "timepoint": ..., "timepoint_hours": ..., "timepoint_order": ...,
         "direction": ..., "omics_type": ..., "table_scope": ...,
         "treatment_type": ..., "background_factors": ..., "is_time_course": ...,
         "n_tests": ..., "n_significant": ..., "universe_size": ...,
         "min_padj": 1.4e-8},
        ...
    ],
    "top_pathways_by_padj": [          # top 10 across all clusters
        {"cluster": ..., "term_id": ..., "term_name": ...,
         "p_adjust": ..., "signed_score": ...},
        ...
    ],

    # Validation — experiments (flat, matches DE/landscape convention)
    "not_found": [],                   # experiment_ids absent from KG
    "not_matched": [],                 # wrong organism, or no DE rows

    # Validation — terms (namespaced passthrough from genes_by_ontology)
    "term_validation": {
        "not_found": [],
        "wrong_ontology": [],
        "wrong_level": [],
        "filtered_out": [],
    },

    # Skipped clusters
    "clusters_skipped": [
        {"cluster": "exp5|NA|down", "reason": "empty_gene_set"},
        {"cluster": "exp2|T1|up", "reason": "no_pathways_in_size_range"},
        ...
    ],

    "results": [...],                  # or [] when summary=True
}
```

**Sort rules for ordered fields:**
- `top_clusters_by_min_padj`: `min_padj` asc, tie-break `cluster` asc.
- `top_pathways_by_padj`: `p_adjust` asc, tie-break `cluster` asc then `term_id` asc.
- `by_experiment`, `by_direction`, `by_omics_type`: deterministic order by the grouping key.

**Deliberately dropped from earlier drafts:**
- `by_timepoint` — cross-experiment timepoint aggregation is meaningless (T0 in exp1 ≠ T0 in exp2).
- `by_cluster` full list — replaced by `cluster_summary` distribution + `top_clusters_by_min_padj` top-K.
- `by_table_scope` — not comparable across values (different universes). `by_omics_type` covers the analytical cross-cut.

## compareCluster alignment

Columns that match clusterProfiler's compareCluster output (for easy porting):
`cluster` (Cluster), `term_id` (ID), `term_name` (Description), `gene_ratio` (GeneRatio), `bg_ratio` (BgRatio), `rich_factor` (RichFactor), `fold_enrichment` (FoldEnrichment), `pvalue`, `p_adjust`, `count` (Count), `foreground_gene_ids` (geneID, verbose).

Extensions (not in clusterProfiler): `signed_score`, `bg_count`, `gene_ratio_numeric`, `bg_ratio_numeric`, `level`, `direction`, `background_gene_ids`, per-cluster experimental context.

Dropped vs clusterProfiler: `qvalue` (dropped per decision).

## Documentation outputs

Two separate `.md` outputs, different audiences, different build paths:

### 1. Tool-about reference — auto-generated from YAML

**Source:** `inputs/tools/pathway_enrichment.yaml`.
**Output:** `skills/multiomics-kg-guide/references/tools/pathway_enrichment.md` (and equivalent) via `scripts/build_about_content.py` + `scripts/sync_skills.sh`.
**Audience:** MCP tool user (human or agent invoking the tool).
**Content:** *how to call the tool* — signature, examples, chaining, verbose fields, common mistakes. No Python code beyond MCP tool-call syntax; no biology background; no primitive-level detail.

YAML content:

**Examples:**
- Single experiment, `direction='both'`, default `table_scope` background.
- Multi-experiment compareCluster analog: list of 10 experiments in one call.
- `summary=True` for envelope-only output.
- `verbose=True` to include `foreground_gene_ids` + `background_gene_ids`.
- `term_ids=[...]` to scope to specific pathways at a given level.

**Chaining:**
- `ontology_landscape → genes_by_ontology(level=N) → pathway_enrichment` (full pipeline).
- `pathway_enrichment → gene_overview` (drill from enriched pathway into gene details).
- `differential_expression_by_gene → pathway_enrichment` (DE motivates enrichment).

**Verbose fields:** `foreground_gene_ids`, `background_gene_ids`.

**Mistakes / good-to-know:**
- "Default background is `table_scope` (per-experiment quantified set). `'organism'` inflates the denominator and underestimates enrichment. See `docs://analysis/enrichment` for the full methodology note."
- "BH correction is per-cluster (experiment × timepoint × direction), NOT across clusters. Cross-experiment FDR is biological replication, not statistical."
- "Single-organism enforced. Run separate calls per organism."
- "Timepoints aren't comparable across experiments — `T0` in exp1 ≠ `T0` in exp2. That's why there's no `by_timepoint` breakdown."
- "For cluster-membership / ortholog-group / custom-list enrichment, use the Python `fisher_ora` primitive (see `docs://analysis/enrichment`). The MCP tool is the DE-wired convenience only. Idiom: `term2gene = to_dataframe(genes_by_ontology(...))` then `fisher_ora(gene_sets, background, term2gene)` — no manual column munging."
- "At least one of `level` or `term_ids` must be provided (matches `genes_by_ontology`)."
- "`min/max_gene_set_size` here means **M** — pathway size within each cluster's background (clusterProfiler semantics). This differs from `ontology_landscape`'s filter, which is organism-scoped. A pathway may be tested in one cluster and dropped in another when `background='table_scope'`."
- wrong: `pathway_enrichment(..., background='genome')  # not a valid string`
  right: `pathway_enrichment(..., background='organism')  # or 'table_scope' (default), or a locus_tag list`

### 2. Methodology doc — hand-written

**Source & canonical location:** `multiomics_explorer/analysis/enrichment.md`.
**Output:** served as the `docs://analysis/enrichment` MCP resource (same file, V2 resource pattern; matches `docs://analysis/response_matrix`).
**Audience:** Python user / analyst / LLM agent doing enrichment in a notebook or a research analysis. Needs to understand the building blocks, not just the MCP tool.
**Content:** *how to do enrichment in Python* — building blocks, code examples, non-DE gene-list options, biological methodology. The MCP tool is a single subsection; not the main topic.

#### Outline

1. **What enrichment is.** DE result (or any gene set) → which pathways are overrepresented relative to a background?

2. **Building blocks (Python API).**
   - `de_enrichment_inputs(experiment_ids, direction, significant_only, timepoint_filter)` — DE → `EnrichmentInputs` (gene_sets, per-cluster background, cluster_metadata).
   - `fisher_ora(gene_sets, background, term2gene, min/max_gene_set_size)` — pure Fisher + BH primitive. Direction-agnostic. Accepts any gene-list source.
   - `signed_enrichment_score(df, direction_col, padj_col)` — collapse `|up`/`|down` cluster pairs into one signed row per pathway.
   - `genes_by_ontology(ontology, organism, level, term_ids=...)` — TERM2GENE source for `fisher_ora`.
   - `list_organisms(...)` / explicit locus_tag list — alternative backgrounds.

3. **Code example — choosing ontology + level with `ontology_landscape`:**
   ```python
   from multiomics_explorer.api import ontology_landscape
   from multiomics_explorer.analysis.frames import to_dataframe

   # Characterize all ontologies for MED4; optionally weight by experiments.
   landscape = ontology_landscape(
       organism="MED4",
       experiment_ids=["exp1", "exp2", ...],   # optional, ranks by experiment coverage
       min_gene_set_size=5, max_gene_set_size=500,
   )
   df_landscape = to_dataframe(landscape)

   # Rows are (ontology x level) combinations ranked by relevance_rank.
   # Key signals: genome_coverage, median_genes_per_term, best_effort_share (GO only).
   df_landscape.sort_values("relevance_rank").head(10)
   # -> pick an (ontology, level) with good coverage + reasonable term sizes.
   ```
   Pick `(ontology, level)` from the top of `df_landscape` before running enrichment. Genome coverage is required — term-size distributions alone mislead (B1's original bug).

4. **Code example — DE path (reproduces the MCP tool):**
   ```python
   from multiomics_explorer import (
       de_enrichment_inputs, fisher_ora, signed_enrichment_score,
   )
   from multiomics_explorer.api import genes_by_ontology
   from multiomics_explorer.analysis.frames import to_dataframe

   inputs = de_enrichment_inputs(
       experiment_ids=["exp1", "exp2", ...],
       organism="MED4",
       direction="both", significant_only=True,
   )
   gbo = genes_by_ontology(
       ontology="cyanorak_role", organism="MED4", level=1,
   )
   term2gene = to_dataframe(gbo)
   df = fisher_ora(
       inputs.gene_sets, inputs.background, term2gene,
       min_gene_set_size=5, max_gene_set_size=500,
   )
   # attach direction for signed_score
   df["direction"] = df["cluster"].map(
       lambda c: inputs.cluster_metadata[c]["direction"]
   )
   collapsed = signed_enrichment_score(df)
   ```

5. **Code example — cluster-membership enrichment (non-DE):**
   ```python
   from multiomics_explorer.api import gene_clusters_by_gene, genes_by_ontology
   from multiomics_explorer.analysis.frames import to_dataframe
   # Gene sets from a clustering analysis: one cluster per row.
   analysis = ...  # list_clustering_analyses(...) result
   gene_sets = {
       f"cluster_{cid}": cluster_members
       for cid, cluster_members in analysis["clusters"].items()
   }
   # Background: all genes that were clustered (the analysis universe).
   background = {c: analysis["universe"] for c in gene_sets}  # shared universe
   term2gene = to_dataframe(
       genes_by_ontology(ontology="cyanorak_role", organism="MED4", level=1)
   )
   df = fisher_ora(gene_sets, background, term2gene)
   ```

6. **Code example — ortholog-group enrichment (non-DE):**
   ```python
   # Gene sets: members of specific ortholog groups.
   from multiomics_explorer.api import genes_by_homolog_group
   gbo_homolog = genes_by_homolog_group(group_ids=[...], organisms=["MED4"])
   gene_sets = {group_id: [...] for group_id in ...}
   # Background: organism gene set.
   organism_genes = [...]  # from list_organisms / resolve_gene enumeration
   df = fisher_ora(gene_sets, organism_genes, term2gene)
   ```

7. **Code example — custom gene list:**
   ```python
   # Any list of locus_tags works — clustering results, manual curation,
   # upstream analyses, etc.
   gene_sets = {"my_hypothesis_set": ["PMM0123", "PMM0456", ...]}
   background = caller_supplied_universe   # list[str]
   df = fisher_ora(gene_sets, background, term2gene)
   ```

8. **Choosing a background.**
   - `table_scope` (DE path): per-experiment quantified gene set. Cite B1 decision D2 — unquantified genes can't be DE.
   - `organism`: full organism gene set. Use when the gene set came from a whole-genome analysis.
   - Custom list: whatever defines *could this gene have been in the foreground*. For clustering, it's the clustered universe; for manual curation, it's the curator's candidate pool.

9. **Choosing an ontology + level (narrative).**
   - `ontology_landscape` ranks `(ontology × level)` combinations by `genome_coverage × size_factor(median_genes_per_term)`. See the code example in section 3.
   - `relevance_rank` bakes in both genome coverage and median term size — 1st is best. `experiment_ids` re-ranks by experiment-specific coverage when supplied.
   - Hierarchy-level convention: `level=0` is root (broadest), higher integers more specific.
   - Tree-vs-DAG caveat: CyanoRak / TIGR / COG are tree-native; GO is a DAG with best-effort levels (`level_is_best_effort`).

10. **Interpretation.**
   - Signed score as a visualization scalar; caveat when both directions significant (use `signed_enrichment_score` to collapse).
   - Catch-all categories (B1 caveat C3: CyanoRak R.2 "Conserved hypothetical proteins", D.1 "Adaptation/acclimation" routinely enrich and should be interpreted with care).
   - Cross-experiment FDR (B1 caveat C4: BH is within-cluster; biological replication across experiments provides confidence, not statistical correction).

11. **Gotchas.**
    - **`min/max_gene_set_size` means different things in different tools.** In `ontology_landscape` it filters organism-scoped pathway size (for ranking levels). In `pathway_enrichment` / `fisher_ora` it filters per-cluster M (pathway size within the cluster's background — clusterProfiler semantics). Passing the same bound value across the chain is correct but the filter is applied at different scopes. Under `background='table_scope'`, a pathway can be tested in one cluster and dropped in another.
    - **`background='table_scope'` means per-cluster universes, not one.** Each experiment's quantified gene set is its own background. Cross-experiment comparisons of `fold_enrichment` carry the caveat that `N` differs per cluster.
    - **NaN timepoints are a cluster named `"NA"`.** Not dropped. Surfaces in `by_experiment` and result rows like any other timepoint.
    - **Timepoints don't align across experiments.** `T0` in exp1 ≠ `T0` in exp2 — that's why there's no `by_timepoint` breakdown. Group by `(experiment_id, timepoint)` or by `treatment_type` if you need a cross-experiment axis.
    - **GO levels are best-effort.** Any pathway coming from GO with `level_is_best_effort=True` (from `genes_by_ontology`'s verbose output) should carry an asterisk in interpretation — min-path-from-root is ambiguous for DAG children.

12. **Divergences from clusterProfiler.**
    - Per-experiment `table_scope` background (not a single universe).
    - `genome_coverage`-driven ontology selection (not in clusterProfiler).
    - Tree-vs-DAG honesty in tool output (`level_is_best_effort`).
    - `min_gene_set_size=5` default (cyanobacterial genomes are small).
    - `qvalue` dropped — BH only; callers compute Storey if needed.

13. **The MCP tool.** One subsection near the end: `pathway_enrichment` is the DE-path wrapper. Examples in the YAML / tool-about doc. For any other gene-list source, use the Python API directly.

14. **Output field reference.** Every field in the result rows and envelope, with the clusterProfiler mapping where it exists. A dedicated subsection because the clusterProfiler names (`gene_ratio`, `bg_ratio`, `rich_factor`, `fold_enrichment`, `count`, `bg_count`) are idiomatic but not self-explanatory.

    **Fisher's 2×2 table** — the foundation. For a single (cluster, term):

    |                        | In pathway | Not in pathway | Total |
    | ---------------------- | ---------- | -------------- | ----- |
    | **DE gene set**        | `a = k`    | `b = n − k`    | `n`   |
    | **Background (not DE)**| `c = M − k`| `d = N − n − c`| `N − n` |
    | **Total (background)** | `M`        | `N − M`        | `N`   |

    where `k = count`, `n = DE set size`, `M = bg_count` (pathway members in background), `N = background size`. The Fisher-exact test asks: is `k` larger than expected under the null (uniform draw from the background)?

    **Result row fields:**

    | Field | clusterProfiler | Meaning |
    |---|---|---|
    | `cluster` | `Cluster` | `"{experiment}|{timepoint}|{direction}"` cluster key |
    | `term_id` | `ID` | Ontology term ID |
    | `term_name` | `Description` | Human-readable term label |
    | `level` | — | Hierarchy depth of the term (0=root) |
    | `count` | `Count` | `k` — DE genes in the pathway |
    | `bg_count` | — | `M` — pathway members in the cluster's background |
    | `gene_ratio` | `GeneRatio` | `"k/n"` string — DE genes in pathway over total DE genes in cluster |
    | `gene_ratio_numeric` | — | `k/n` float |
    | `bg_ratio` | `BgRatio` | `"M/N"` string — pathway members over background size |
    | `bg_ratio_numeric` | — | `M/N` float |
    | `rich_factor` | `RichFactor` | `k/M` — fraction of the pathway's background members that are DE |
    | `fold_enrichment` | `FoldEnrichment` | `(k/n) / (M/N)` — observed enrichment over null expectation. `>1` means enriched |
    | `pvalue` | `pvalue` | Fisher-exact p-value (one-sided, enrichment direction) |
    | `p_adjust` | `p.adjust` | Benjamini-Hochberg FDR within the cluster |
    | `signed_score` | — | `sign × −log10(p_adjust)` — sign from direction (up:+, down:−) |
    | `foreground_gene_ids` | `geneID` (split) | `list[str]` — the k DE genes in the pathway (verbose) |
    | `background_gene_ids` | — | `list[str]` — pathway members in background *not* in DE set (verbose) |

    **Context fields (experiment-level, threaded per row):** `experiment_id`, `name`, `timepoint`, `timepoint_hours`, `timepoint_order`, `direction`, `omics_type`, `table_scope`, `treatment_type`, `background_factors`, `is_time_course` — all defined by their experiment source; see `list_experiments`.

    **Envelope fields:**

    | Field | Meaning |
    |---|---|
    | `total_rows`, `returned`, `truncated`, `offset` | Pagination |
    | `n_tests` | Total Fisher tests run (= total result rows pre-filter) |
    | `n_significant` | Rows with `p_adjust < pvalue_cutoff` |
    | `by_experiment` | Per-experiment `{n_tests, n_significant, n_clusters}` plus experiment metadata |
    | `by_direction` | Per-direction `{n_tests, n_significant}` |
    | `by_omics_type` | Per-omics-type `{n_tests, n_significant}` |
    | `cluster_summary` | `n_clusters` + min/median/max of `n_tests`, `n_significant`, `universe_size` |
    | `top_clusters_by_min_padj` | Top 5 clusters by their smallest `p_adjust`, full metadata |
    | `top_pathways_by_padj` | Top 10 pathways across all clusters by `p_adjust`. Fixed slice of what `results` already carries — `results` is globally sorted by `p_adjust` asc, so pagination (`limit`/`offset`) on `results` recovers positions 11+ |
    | `not_found` | Requested `experiment_ids` absent from KG |
    | `not_matched` | Experiment IDs found but wrong organism or no DE rows |
    | `term_validation` | Namespaced `{not_found, wrong_ontology, wrong_level, filtered_out}` for `term_ids` (passthrough from `genes_by_ontology`) |
    | `clusters_skipped` | Clusters with `{cluster, reason}`: `empty_gene_set`, `no_pathways_in_size_range`, `empty_background` |

15. **Deferred methodology** (pointers, not implementations): GSEA, `simplify()` / GOSemSim, topGO elim/weight, `gson` export.

16. **References:**
    - yulab-smu biomedical-knowledge-mining book: https://yulab-smu.top/biomedical-knowledge-mining-book/
    - Xu, S. et al. *Nat Protoc* **19**, 3292–3320 (2024). doi:10.1038/s41596-024-01020-z
    - Yu, G. et al. clusterProfiler. *OMICS* **16**, 284–287 (2012).
    - B1 analysis: `multiomics_research/analyses/2026-04-09-1713-pathway_enrichment_b1/`.

#### Resource registration

Register as a static MCP resource (see project backlog: "MCP resource templates don't list — register static resources for discoverability").

### 3. Example script — runnable collateral

**Location:** `examples/pathway_enrichment.py` (new top-level `examples/` directory).
**Audience:** anyone copy-pasting into a notebook or running end-to-end.
**Purpose:** each code snippet in `enrichment.md` has a runnable counterpart. Executable, import-checked in CI, and exercised by an integration test to keep it from bit-rotting.

**Structure:** five numbered scenarios matching the methodology doc's code examples:

```
examples/pathway_enrichment.py
  main() — parses --scenario argument, dispatches to one of:
  scenario_1_landscape()  # pick (ontology, level) via ontology_landscape
  scenario_2_de()         # DE path — reproduces the MCP tool output
  scenario_3_cluster()    # cluster-membership enrichment
  scenario_4_homolog()    # ortholog-group enrichment
  scenario_5_custom()     # manual gene list
```

Each scenario function:
- Is fully self-contained (own imports, own connection setup).
- Prints a brief summary of results (top 5 pathways by `p_adjust`).
- Has a module-level docstring matching the methodology doc's narrative.

**Wiring:**
- `enrichment.md` code examples quote the relevant functions verbatim (same code paths, so doc and script can't drift).
- `tests/integration/test_examples.py` (new) parametrizes over scenarios and runs them against the live KG under `-m kg`. Serves as a smoke test.
- `examples/README.md` (minimal) indexes the directory.

## Tests

### Unit — new `tests/unit/test_enrichment.py`

- `fisher_ora`: math correctness against scipy + statsmodels reference; per-cluster BH; per-cluster vs shared background branches; **size filter is per-cluster on M**, tests both bounds (a pathway passes in one cluster and is filtered in another when backgrounds differ); `max_gene_set_size=None` disables upper bound. TERM2GENE contract: accepts `to_dataframe(genes_by_ontology(...))` output unchanged (integration-style unit test with a mocked `genes_by_ontology` result). Raises clear error on missing required columns. (No `signed_score` assertion — primitive doesn't compute it.)
- `signed_enrichment_score`: up-only, down-only, both-significant (dominant wins); re-derivation under new `padj_col` / cutoff.
- `de_enrichment_inputs`: partitioning (`exp|tp|direction` keys); NaN-timepoint grouping as `"NA"`; `timepoint_filter` behavior; full-universe `background` vs `significant_only` `gene_sets`; single-organism enforcement (mixed-organism `experiment_ids` → `ValueError`; experiments not belonging to `organism` → `ValueError`).

### Unit — `tests/unit/test_api_functions.py`

- `pathway_enrichment` orchestration with mocked conn: XOR validation of `level`/`term_ids`; mixed-organism `ValueError`; background-mode dispatch; `term_validation` passthrough from `genes_by_ontology`; envelope composition (breakdowns, `cluster_summary`, `top_*`, `clusters_skipped`).
- **Error handling coverage:**
  - Input validation: each `ValueError` case (bad ontology, no level/term_ids, bad direction, bad background shape, negative `min_gene_set_size`, `max < min`, empty `experiment_ids`, `pvalue_cutoff` out of range).
  - Partial success: some `experiment_ids` not_found / not_matched; some `term_ids` wrong_ontology / wrong_level; mix of passing and `empty_gene_set` clusters — `results` non-empty, validation buckets populated, warnings issued.
  - Vacuous success: all experiments missing → valid empty envelope (`results=[]`, `n_tests=0`), no raise.
  - Propagated: simulate Neo4j error from the mocked conn → propagates, not swallowed.

### Unit — `tests/unit/test_tool_wrappers.py`

- MCP Pydantic round-trip; `limit=100` default; `summary=True` returns empty `results`; `verbose=True` includes gene_id lists; `ctx.warning` on non-empty validation buckets.
- **Field-description coverage:** assert every field on the result-row model and envelope model has a non-empty `Field(description=...)` value (prevents silently shipping an undocumented field). Spot-check that clusterProfiler-named fields (`gene_ratio`, `bg_ratio`, `rich_factor`, `fold_enrichment`, `count`, `bg_count`) mention their clusterProfiler equivalent in the description.

### Unit — `tests/unit/test_frames.py`

- **Default framer handles `pathway_enrichment` output:** feed a synthetic envelope (scalars + list-of-strings in `treatment_type` / `background_factors` / `foreground_gene_ids` / `background_gene_ids`) to `to_dataframe` and assert it produces a clean DataFrame with joined-string columns, no `UserWarning` about dropped complex values, and expected column names. Both compact-only and verbose variants.

### Integration (`-m kg`)

- **B1 reproduction:** MED4 × CyanoRak level 1 × 10 experiments × `direction='both'` surfaces the B1 enriched pathways (E.4 N-metabolism, J.1–J.8 photosynthesis, K.2 ribosomal). Exact count may drift with KG rebuilds; assert key pathways appear where expected.
- **NaN-timepoint experiments** (Steglich, Tolonen cyanate, Tolonen urea): clusters with timepoint `"NA"` present in `by_experiment` with non-null counts.
- `'organism'` background: universe size equals `list_organisms` gene count for MED4.
- Explicit locus_tag background: universe size equals caller's list length.
- `clusters_skipped` populated for deliberately-undersized test cases.

### Regression

Freeze the B1 reproduction in `tests/regression/`. Regenerate after KG rebuilds per the established protocol.

### Example-script smoke test

`tests/integration/test_examples.py` (new, `-m kg`): parametrize over the four scenarios in `examples/pathway_enrichment.py`; run each end-to-end; assert non-empty result for the DE scenario and clean exit for the rest. Keeps the example code compiling, importable, and runnable as the API evolves.

## Layer-rules compliance

- **L1:** no new builders. `pathway_contingency_counts_query` is deleted from the earlier draft.
- **L2 — package (`analysis/enrichment.py`):** `EnrichmentInputs` dataclass, `de_enrichment_inputs`, `fisher_ora`, `signed_enrichment_score`. Pure Python; pandas + scipy + statsmodels deps.
- **L2 — api (`api/functions.py`):** new `pathway_enrichment()` composes `de_enrichment_inputs`, `genes_by_ontology`, `fisher_ora`. Validates inputs. Assembles envelope dict.
- **L2 — frames (`analysis/frames.py`):** no bespoke framer expected. Result rows are scalars plus a few `list[str]` columns (`treatment_type`, `background_factors`, `foreground_gene_ids`, `background_gene_ids`), all of which the default `to_dataframe()` handles by joining with `" | "`. **Validated by test** (see Tests section). If the test surfaces nesting the default framer can't handle, add a dedicated converter — otherwise no new code in `frames.py`.
- **L3 (`mcp_server/tools.py`):** thin wrapper. Pydantic response model. `limit=100` default. `ToolError` on invalid input. `await ctx.info` for DE / TERM2GENE fetches; `ctx.warning` when any validation bucket non-empty.
  - **Every Pydantic field on the result-row and envelope models carries a `Field(description=...)`** explaining the meaning and, where applicable, the clusterProfiler equivalent (e.g., `"k/n — DE genes in pathway over total DE genes in cluster (clusterProfiler: GeneRatio)"`). `scripts/build_about_content.py` pulls these descriptions into the auto-generated tool-about doc's response-format section, so MCP callers see the field meanings without leaving the tool page.
- **L4:** `inputs/tools/pathway_enrichment.yaml`; skill reference auto-regenerated via `scripts/build_about_content.py` + `scripts/sync_skills.sh`.

## Public exports

```python
# multiomics_explorer/__init__.py additions
from multiomics_explorer.analysis.enrichment import (
    EnrichmentInputs,
    de_enrichment_inputs,
    fisher_ora,
    signed_enrichment_score,
)
```

## Out of scope

- GSEA / rank-based methods — parent spec's deferred list.
- Enrichment visualizations (emapplot, cnetplot, upsetplot).
- `simplify()` / GOSemSim.
- `gson` export.
- Multi-ontology combined enrichment.
- A separate MCP tool for gene-list (non-DE) enrichment — the primitive supports it from Python; MCP wrapper can be added if demand emerges.
- Research-repo `enrich_utils/` migration.

## Migration from earlier (2026-04-12) draft

**Removed:**
- `pathway_contingency_counts_query` L1 builder — deleted.
- `qvalue` column on result rows — dropped.
- `by_timepoint` envelope breakdown — dropped (meaningless across experiments).
- `by_cluster` full list — replaced by `cluster_summary` + `top_clusters_by_min_padj`.
- `by_table_scope` envelope breakdown — dropped; `by_omics_type` added instead.
- Verbose experiment fields on result rows (`treatment`, `control`, `statistical_test`, `experimental_context`, `growth_phases`, `medium`, `light_condition`, `light_intensity`, `temperature`, `coculture_partner`, `table_scope_detail`) — moved off the surface; callers use `list_experiments`.

**Added / restructured:**
- Package module `analysis/enrichment.py` with `EnrichmentInputs`, `de_enrichment_inputs`, `fisher_ora`, `signed_enrichment_score`.
- Gene-list-first primitive; DE path is the wrapper.
- Two distinct doc outputs: tool-about (auto-generated from YAML) for MCP callers; hand-written methodology doc (`enrichment.md`) for Python users, with code examples covering DE + non-DE (cluster, ortholog, custom) scenarios.
- Runnable `examples/pathway_enrichment.py` collateral exercised by a new integration smoke test.
- `term_validation` namespaced sub-dict in envelope (passthrough from `genes_by_ontology`'s four buckets).
- `cluster_summary` distribution + `top_clusters_by_min_padj` top-K replace full `by_cluster`.
- Rich per-cluster metadata (3 timepoint fields + omics_type + table_scope + is_time_course + treatment_type + background_factors).
- `background_gene_ids` (non-overlapping) added alongside `foreground_gene_ids` in verbose.
- Sort tie-break rule: by `p_adjust` asc, tie-break `cluster` asc then `term_id` asc.

## Open questions deferred to plan stage

- For Python callers who want `signed_score` out of `fisher_ora` results without going through the MCP wrapper: document the pattern — attach a `direction` column to the DataFrame (from their own metadata) and pass through `signed_enrichment_score` or compute `sign × -log10(p_adjust)` directly. Doc-only.
