# `EnrichmentResult` — Design Spec

**Status:** Draft
**Date:** 2026-04-18
**Parent:** [KG Enrichment Surface](2026-04-12-kg-enrichment-surface-design.md)
**Related:** [pathway_enrichment](2026-04-12-pathway-enrichment-design.md), [cluster_enrichment](2026-04-17-cluster-enrichment-design.md)

**Motivated by:** The Python API for `pathway_enrichment` and `cluster_enrichment` returns a flat dict. Intermediates (per-cluster foreground gene lists, per-cluster background, per-term overlap members, term2gene) are computed internally but never exposed. Analysts — especially Claude Code writing scripts that run in interactive notebooks — need to ask "why is this term enriched in this cluster?" and "which genes drove this result?" without re-running the Fisher math by hand. This spec replaces the raw-dict return with an `EnrichmentResult` class that owns the intermediates and surfaces them through typed accessors.

## Problem

Today:

```python
result = api.pathway_enrichment(...)   # returns dict (the envelope)
result["results"][0]                   # {"cluster", "term_id", "pvalue", "count", "bg_count", ...}
# But: how do I find out WHICH 12 foreground genes landed in this term?
#      Which genes constitute the background for this (cluster, term)?
#      What was the cluster's experimental context — direction, timepoint, treatment?
# The inputs.gene_sets, inputs.background, and term2gene that produced this row
# are discarded before return.
```

The existing [`_build_pathway_enrichment_envelope`](../../../multiomics_explorer/api/functions.py) already has a hook that drops `foreground_gene_ids` / `background_gene_ids` columns when `verbose=False` — i.e. the design intent is clearly to expose these — but `fisher_ora` never produces them. This spec finishes that story and expands it into a richer analyst-facing object.

## Design principle

**The class earns its place only where it does something a one-line pandas query doesn't.** Methods must either (a) join `results` with `inputs`, (b) produce a rendering (prose, compareCluster format), or (c) serialize to the MCP envelope. Pure slicing stays as pandas on `result.results`.

## Scope

**In scope:**
- New `EnrichmentResult` dataclass in `analysis/enrichment.py`
- New Pydantic models: `DEStats`, `GeneRef`, `EnrichmentExplanation`
- Extension to `EnrichmentInputs`: `gene_stats` field (DE-specific)
- Signature change: `fisher_ora(inputs: EnrichmentInputs, term2gene: DataFrame) -> EnrichmentResult`
- Refactor `api.pathway_enrichment` / `api.cluster_enrichment` to return `EnrichmentResult`
- Update MCP wrappers to call `.to_envelope()`
- Migrate all tests, examples, skill docs

**Out of scope:**
- Changes to the Fisher math
- New enrichment tools / modes (cluster vs pathway split stays as-is)
- New KG queries (all gene name / product data comes from existing query results)
- External publication of `EnrichmentResult` as a stable API (still pre-v1 internal use)
- Exposing `.explain()` over MCP. Considered a stateless `get_enrichment_explanation` tool (takes full ORA params + `cluster` + `term_id`, re-runs scoped enrichment, returns the `EnrichmentExplanation` as a dict) and a handle-based pattern (return a UUID from `pathway_enrichment`, pass it back on subsequent calls). Both deferred: the handle pattern requires server-side state with unclear GC semantics, and the stateless-re-run tool is ergonomic sugar that the LLM rarely needs — if it does, it can re-call `pathway_enrichment` with narrow `term_ids` and read the target row. Revisit if MCP-side drill-down becomes a real workflow.

## Type hierarchy

```python
# All Pydantic (typed fields, JSON-serializable)

class DEStats(BaseModel):
    """Differential-expression statistics for one gene in one experiment × timepoint."""

    log2fc: float = Field(
        description="log2 fold change from DE analysis."
    )
    padj: float = Field(
        description="BH-adjusted p-value from the source DE table."
    )
    rank: int | None = Field(
        default=None,
        description=(
            "Rank by |log2FC| within the experiment × timepoint. 1 = strongest. "
            "None when the source DE tool didn't emit a rank."
        ),
    )
    direction: Literal["up", "down", "none"] = Field(
        description="'up', 'down', or 'none' (not significant)."
    )
    significant: bool = Field(
        description="Whether the gene meets the experiment's significance threshold."
    )

class GeneRef(BaseModel):
    """A gene referenced in an enrichment result — locus_tag plus optional name/product/DE stats."""

    locus_tag: str = Field(
        description="Primary gene identifier, e.g. 'PMM0712'."
    )
    gene_name: str | None = Field(
        default=None,
        description=(
            "Short gene name (e.g. 'pstS') from term2gene's gene_name column. "
            "None when term2gene lacks the column or the cell is null."
        ),
    )
    product: str | None = Field(
        default=None,
        description=(
            "Gene product description (e.g. 'phosphate ABC transporter'). "
            "None when term2gene lacks the column or the cell is null."
        ),
    )
    # DE stats — populated when inputs.gene_stats has an entry for this locus_tag;
    # None otherwise (e.g., background gene not in DE table, or cluster_enrichment path).
    log2fc: float | None = Field(
        default=None, description="log2 fold change; None outside the DE path."
    )
    padj: float | None = Field(
        default=None, description="BH-adjusted p-value; None outside the DE path."
    )
    rank: int | None = Field(
        default=None,
        description="Rank by |log2FC| within experiment × timepoint; None outside the DE path.",
    )
    direction: Literal["up", "down", "none"] | None = Field(
        default=None, description="DE direction; None outside the DE path."
    )
    significant: bool | None = Field(
        default=None, description="DE significance flag; None outside the DE path."
    )

class EnrichmentExplanation(BaseModel):
    """Single (cluster, term_id) pair explained: Fisher numbers, ranking, gene lists, narrative."""

    # identity
    cluster: str = Field(
        description="Cluster identifier from EnrichmentInputs.gene_sets."
    )
    term_id: str = Field(
        description="Ontology term identifier (e.g. 'GO:0006810')."
    )
    term_name: str = Field(
        description="Human-readable term name (e.g. 'transport')."
    )
    cluster_kind: Literal["pathway", "cluster"] = Field(
        description=(
            "Which enrichment path produced this result — dispatches the narrative "
            "wording. 'pathway' = DE-driven; 'cluster' = clustering-analysis-driven."
        ),
    )
    cluster_metadata: dict = Field(
        description=(
            "Cluster-specific context. For pathway kind: experiment_id, timepoint, "
            "direction, omics_type, table_scope, treatment_type, background_factors. "
            "For cluster kind: analysis_id, analysis_name, cluster_type, treatment, "
            "experimental_context."
        ),
    )

    # Fisher numbers
    count: int = Field(
        description="k — genes in foreground ∩ background ∩ term."
    )
    n_foreground: int = Field(
        description="n — genes in foreground ∩ background."
    )
    bg_count: int = Field(
        description="M — genes in background ∩ term."
    )
    n_background: int = Field(
        description="N — total genes in background."
    )
    gene_ratio: str = Field(
        description="Pretty 'k/n' string (e.g. '12/87'), clusterProfiler-style."
    )
    bg_ratio: str = Field(
        description="Pretty 'M/N' string (e.g. '210/2340'), clusterProfiler-style."
    )
    fold_enrichment: float = Field(
        description="(k/n) / (M/N) — observed over expected."
    )
    rich_factor: float = Field(
        description="k / M — fraction of the term's background that landed in foreground."
    )
    pvalue: float = Field(
        description="Fisher's exact test one-sided p-value (greater)."
    )
    p_adjust: float = Field(
        description="BH-adjusted p-value within this cluster's tests."
    )

    # ranking within this cluster
    rank_in_cluster: int = Field(
        description=(
            "Rank of this term among all terms tested in this cluster, by p_adjust "
            "ascending. 1 = most significant."
        ),
    )
    n_terms_in_cluster: int = Field(
        description="Total terms tested in this cluster (denominator for rank_in_cluster)."
    )

    # genes
    overlap_genes: list[GeneRef] = Field(
        description=(
            "The k locus_tags (foreground ∩ background ∩ term) as GeneRef objects, "
            "sorted: named genes first (by rank if present, else gene_name), then "
            "unnamed (by rank if present, else locus_tag)."
        ),
    )
    background_genes: list[GeneRef] = Field(
        description=(
            "The M locus_tags (background ∩ term) as GeneRef objects, same sort. "
            "DE fields populated for any locus_tag present in inputs.gene_stats."
        ),
    )
    overlap_preview_n: int = Field(
        default=10,
        description="Max number of overlap genes to inline in the _repr_markdown_ narrative.",
    )

    def _repr_markdown_(self) -> str: ...  # human-readable narrative


# Dataclass — holds a pandas DataFrame, which Pydantic handles awkwardly
@dataclass
class EnrichmentResult:
    kind: Literal["pathway", "cluster"]
    organism_name: str
    ontology: str
    level: int | None

    results: pd.DataFrame                         # Fisher rows (one per cluster × term)
    inputs: EnrichmentInputs                      # gene_sets, background, gene_stats, cluster_metadata
    term2gene: pd.DataFrame                       # needed for overlap_genes / background_genes accessors

    term_validation: dict                         # not_found, wrong_ontology, wrong_level, filtered_out
    clusters_skipped: list[dict]                  # cluster_id, reason
    params: dict                                  # ORA call params (see "Params for interpretability" section)

    # Envelope summary helpers (by_experiment, by_direction, top_pathways_by_padj, etc.)
    # are computed on demand inside to_envelope() — no precomputed attributes on
    # the class, to avoid duplicating state that's derivable from results + inputs.

    # --- must-have accessors ---
    def explain(self, cluster: str, term_id: str) -> EnrichmentExplanation: ...
    def overlap_genes(self, cluster: str, term_id: str) -> list[GeneRef]: ...
    def background_genes(self, cluster: str, term_id: str) -> list[GeneRef]: ...
    def generate_summary(self) -> dict: ...           # Python-facing: aggregate view, no rows
    def to_envelope(
        self, *, summary: bool = False,
        limit: int | None = None, offset: int = 0,
    ) -> dict: ...                                     # MCP-facing: summary + paginated results

    # --- nice-to-have accessors ---
    def cluster_context(self, cluster: str) -> dict: ...
    def why_skipped(self, cluster: str) -> str | None: ...
    def to_compare_cluster_frame(self) -> pd.DataFrame: ...
    def missing_terms(self) -> dict[str, list[str]]: ...
```

## `EnrichmentInputs` extensions

Today:
```python
class EnrichmentInputs(BaseModel):
    organism_name: str
    gene_sets: dict[str, list[str]]
    background: dict[str, list[str]]
    cluster_metadata: dict[str, dict]
    not_found: list[str]
    not_matched: list[str]
    no_expression: list[str]
    clusters_skipped: list[dict]
    analysis_metadata: dict
```

Add one optional field (default `{}`):

```python
    gene_stats: dict[str, dict[str, DEStats]] = Field(
        default_factory=dict,
        description=(
            "cluster -> locus_tag -> DEStats. Populated by de_enrichment_inputs for "
            "every measured gene (not just foreground/significant). Empty for "
            "cluster_enrichment_inputs. Consumed by GeneRef construction in "
            "EnrichmentResult accessors."
        ),
    )
```

**Why not also a `gene_info` field (gene_name / product)?** Every locus_tag ever accessed by an `EnrichmentResult` accessor is, by definition, a gene mapped to a queried term — so it's always present in `term2gene`, which already carries `gene_name` and `product` per row. Holding a separate `gene_info` map on `EnrichmentInputs` would duplicate data that's already in `term2gene`. `GeneRef` construction reads name/product straight from the matching `term2gene` row.

`gene_stats` stays on `EnrichmentInputs` because DE stats are not in `term2gene`.

Populated by the helpers that build `EnrichmentInputs`:

- **`de_enrichment_inputs`** (used by `pathway_enrichment`): fetches the **full** DE rows for the requested experiments (no `significant_only` filter at fetch time) and:
  - Populates `gene_sets` using significance/direction filter (unchanged behavior).
  - Populates `gene_stats[cluster][locus_tag]` for **every measured gene**, regardless of significance. Cost: ~thousands of `DEStats` records per call for a ~2000-gene organism × few experiments × few timepoints. Acceptable for in-process notebook use.
- **`cluster_enrichment_inputs`** (used by `cluster_enrichment`): `gene_stats` stays empty (clustering results don't carry DE stats).

## Params for interpretability

`EnrichmentResult.params` is a free-form dict populated by the API function that built the result. It captures exactly what was called, for reproducibility and inspection — shown in `to_envelope()` output as `"enrichment_params"`.

**Both tools:**
- `organism`, `ontology`, `level`, `term_ids`, `tree`
- `min_gene_set_size`, `max_gene_set_size`, `pvalue_cutoff`
- `background_mode`: `"table_scope"` | `"organism"` | `"cluster_union"` | `{"explicit": [first_5_locus_tags, "+N more"]}` — explicit background lists are truncated to avoid bloating the envelope with thousands of locus_tags
- `n_clusters_input` (from `len(inputs.cluster_metadata)`), `n_clusters_tested` (number producing ≥1 row), `n_clusters_skipped` (`len(clusters_skipped)`)
- `term2gene_row_count`, `n_unique_terms`
- `multitest_method`: `"fdr_bh"` (hardcoded today; captured for forward-compat if ever configurable)

**`pathway_enrichment`-specific:**
- `experiment_ids`, `direction`, `significant_only`, `timepoint_filter`, `growth_phases`

**`cluster_enrichment`-specific:**
- `analysis_id`, `min_cluster_size`, `max_cluster_size`

**Not captured** (scope-creep; flag in a follow-up if needed): call timestamp, software/KG version, full per-cluster gene counts (already in `generate_summary()`'s `cluster_summary` breakdown).

Free-form dict (not a typed model) to keep forward-extension cheap — new params land as new keys without a shape change for existing consumers.

## `term2gene` required vs optional columns

`fisher_ora` / `EnrichmentResult` accept any `term2gene` DataFrame (whether built by `genes_by_ontology` or manually constructed by a user running a custom enrichment).

| Column | Status | Used by |
|---|---|---|
| `term_id` | **required** | Fisher math, result keying |
| `term_name` | **required** | Result rows, narrative |
| `locus_tag` | **required** | Fisher math, overlap computation |
| `gene_name` | *optional* | `GeneRef.gene_name`, narrative display; `None` if column absent or cell null |
| `product` | *optional* | `GeneRef.product`; `None` if column absent or cell null |

`GeneRef` construction handles missing columns gracefully — a user who built `term2gene` by hand without gene_name/product gets `GeneRef(locus_tag=..., gene_name=None, product=None, ...)`. `.explain()` still works; the narrative falls back to locus_tag-only display (`"PMM0712"` instead of `"pstS (PMM0712)"`).

This behavior must be documented in the canonical `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md` alongside the existing `_REQUIRED_TERM2GENE_COLS` contract (defined in `analysis/enrichment.py`).

## `fisher_ora` signature change

**Before:**
```python
def fisher_ora(
    gene_sets: dict[str, list[str]],
    background: dict[str, list[str]] | list[str],
    term2gene: pd.DataFrame,
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
) -> pd.DataFrame: ...
```

**After:**
```python
def fisher_ora(
    inputs: EnrichmentInputs,
    term2gene: pd.DataFrame,
    *,
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
) -> EnrichmentResult: ...
```

- Callers without a KG can still use `fisher_ora` directly — they construct `EnrichmentInputs` with just `gene_sets`, `background`, `organism_name` and leave `gene_stats` empty. `.explain()` still works, minus the DE-specific fields. Gene names / products flow from `term2gene` regardless of KG.
- `fisher_ora` stays domain-agnostic: no signed-score computation, no direction awareness. The Fisher math is unchanged.

## Domain post-processing (outside `fisher_ora`)

`api.pathway_enrichment` adds the `signed_score` column after `fisher_ora` returns (direction-aware, only meaningful for DE-framed enrichment):

```python
inputs = de_enrichment_inputs(...)
term2gene = to_dataframe(genes_by_ontology(...))
result = fisher_ora(inputs, term2gene, min_gene_set_size=..., max_gene_set_size=...)
result.results["signed_score"] = _compute_signed_score(result.results, inputs)
return result
```

`api.cluster_enrichment` has no `signed_score` step.

## `generate_summary()` and `to_envelope()` — two outputs, one shared core

**Separation of concerns:**
- `generate_summary()` — Python-facing. Returns the **aggregate** view only: totals, breakdowns, top-N, validation buckets, params. **No per-row `results` list.** For analysts who want "what happened" without the per-row payload.
- `to_envelope(...)` — MCP-facing. Wraps `generate_summary()`, adds pagination metadata and the per-row `results` payload. This is what the MCP tool wrappers call.

`generate_summary()` includes:
- `organism_name`, `ontology`, `level`
- `total_matching`, `n_significant`
- `by_experiment`, `by_direction`, `by_omics_type` (pathway only)
- `cluster_summary`, `top_clusters_by_min_padj`, `top_pathways_by_padj`
- `not_found`, `not_matched`, `no_expression`
- `term_validation`, `clusters_skipped`
- `enrichment_params`

`to_envelope(summary, limit, offset)`:
```python
def to_envelope(
    self, *, summary: bool = False,
    limit: int | None = None, offset: int = 0,
) -> dict:
    env = self.generate_summary()
    if summary:
        env["results"] = []
        env["returned"] = 0
        env["truncated"] = env["total_matching"] > 0
        env["offset"] = offset
        return env
    # ... pagination + results rows ...
    return env
```

**No `verbose` or `include_inputs` flags.** Rationale:
- Rich gene detail (overlap_genes, background_genes) lives on the `EnrichmentResult` object via `.explain()` / `.overlap_genes(c, t)` / `.background_genes(c, t)`. The serialized MCP dict stays lean and consistent.
- Python callers who need `inputs` access `result.inputs` directly. No need to teach the serializer to ship intermediates.

The resulting `to_envelope()` dict matches the **exact shape** today's `PathwayEnrichmentResponse` / `ClusterEnrichmentResponse` Pydantic models consume. The existing `_build_pathway_enrichment_envelope` / `_build_cluster_enrichment_envelope` logic is lifted into this pair of methods (summary logic into `generate_summary()`, pagination + results into `to_envelope()`) with no behavior change.

**Flag semantics:**

| Flag | Effect |
|---|---|
| default (no flags) | Full envelope — summary fields + paginated `results` rows (scalar-only). |
| `summary=True` | Empty `results`, summary fields only — matches today's behavior. |
| `limit`, `offset` | Pagination over `results` list — unchanged from today. |

`results` rows are always scalar — no list-typed columns — so `df.to_dict(orient="records")` is safe without coercion helpers.

## MCP wrapper changes

In `multiomics_explorer/mcp_server/tools.py`:

```python
# Before (line 3864):
return PathwayEnrichmentResponse(**result)

# After:
envelope = result.to_envelope(summary=summary, limit=limit, offset=offset)
return PathwayEnrichmentResponse(**envelope)
```

Same for `cluster_enrichment`. **MCP tool schemas drop the `verbose` parameter** (it was phantom today — stripping columns that were never populated). The `include_inputs` idea is dropped entirely; Python callers access `result.inputs` directly if they need it.

## Sort order for `overlap_genes` / `background_genes` lists

1. Named genes first (descending `has_name`).
2. Within named group, by `rank` ascending if present (rank 1 = strongest |log2FC|); else by `gene_name` alphabetical.
3. Within unnamed group, by `rank` ascending if present; else by `locus_tag` alphabetical.

Applies to `GeneRef` lists in both `EnrichmentExplanation.overlap_genes` / `.background_genes` and the accessor return values.

## `EnrichmentExplanation` narrative

Rendered by `_repr_markdown_` (used by Jupyter automatically). Display format: `"pstS (PMM0712)"` when `gene_name` is present, `"PMM0712"` otherwise. Narrative lists up to `overlap_preview_n` (default 10) overlap genes inline, drawn from the top of the sorted list (named first, then unnamed if the named count is < N); remainder summarized as `(+K more)`. Full lists always accessible via `EnrichmentExplanation.overlap_genes` / `.background_genes`.

**Dispatched on `cluster_kind`:**

- **pathway**: "GO:0006810 (transport) is enriched in `up_EXP042_24h` (experiment EXP042, up-regulated at 24h). 12 of 87 foreground genes hit this term; 210 of 2340 background genes carry it (fold 1.54, p.adjust 2.3e-4, rank 3 of 45). Overlap: pstS (PMM0712), phoA (PMM0834), ... (+10 more)."
- **cluster**: "GO:0006810 (transport) is enriched in `cluster_17` (analysis ANL003, cluster_type=k-means, treatment=nitrogen starvation). 12 of 87 members hit this term; 210 of 2340 background genes carry it (fold 1.54, p.adjust 2.3e-4, rank 3 of 45). Overlap: pstS (PMM0712), ..."

Background gene count is mentioned; background gene list is **not** included in the narrative prose (stays accessible as `EnrichmentExplanation.background_genes` field).

## Testing

**New unit test file: `tests/unit/test_enrichment_result.py`** (no Neo4j):

| Test | What it covers |
|---|---|
| `fisher_ora` → `EnrichmentResult` construction | Smoke: returned type, DataFrame shape, intermediates present. |
| `.overlap_genes(cluster, term_id)` | Returns `gene_sets[cluster] ∩ background[cluster] ∩ term2gene[term_id]` as `GeneRef` list, named-first-alpha-ranked order. |
| `.background_genes(cluster, term_id)` | Returns `background[cluster] ∩ term2gene[term_id]` as `GeneRef` list; DE fields populated when `gene_stats` has them. |
| `.explain(cluster, term_id)` — pathway kind | All fields populated; narrative cites gene names + rank + direction; substring assertions, not exact prose. |
| `.explain(cluster, term_id)` — cluster kind | Dispatches on `cluster_kind`; mentions analysis/cluster_type, omits DE-specific phrasing. |
| `.explain` with mixed named/unnamed genes | Named shown as `"pstS (PMM0712)"`, unnamed as `"PMM0712"`; sort order preserved. |
| `.explain` when `term2gene` lacks `gene_name` / `product` columns | `GeneRef.gene_name` / `.product` are `None`; narrative falls back to locus_tag-only display. Custom-term2gene path. |
| `.explain` when `gene_stats` empty | DE fields on `GeneRef` are `None`; narrative omits rank/direction sentence. |
| `.explain` for non-existent (cluster, term_id) | Raises `KeyError` with clear message. |
| `.cluster_context(cluster)` | Joins `inputs.cluster_metadata` + `n_tests` / `n_significant`. |
| `.why_skipped(cluster)` | Reads `clusters_skipped` reason; returns `None` if cluster produced results. |
| `.to_compare_cluster_frame()` | Column renames match clusterProfiler convention: `Cluster`, `ID`, `Description`, `GeneRatio`, `BgRatio`, `pvalue`, `p.adjust`, `geneID`. |
| `.missing_terms()` | Surfaces `term_validation` buckets. |
| `.generate_summary()` | Aggregate view — `by_experiment`, `by_direction`, `top_*`, `cluster_summary`, `enrichment_params`. **No `results` key.** No pagination fields. |
| `.to_envelope()` (default) | Summary fields + paginated scalar-only `results` rows + pagination (`returned`, `truncated`, `offset`). |
| `.to_envelope(summary=True)` | Empty `results`, summary fields intact. |
| `.to_envelope(limit=N, offset=K)` | Pagination slices `results`; `truncated` flag correct. |
| `.to_envelope()` `"enrichment_params"` key | Dict populated per the "Params for interpretability" table; pathway-specific and cluster-specific keys present only for their respective paths; explicit-list backgrounds truncated. |

**Test style:** `EnrichmentExplanation` narrative uses **substring assertions**, not snapshot comparison — phrasing is a UI concern, checks should catch semantic regressions without churning on cosmetic tweaks.

**Integration tests (`tests/integration/test_api_contract.py`, `test_mcp_tools.py`):** update `pathway_enrichment` / `cluster_enrichment` contract tests to call `.to_envelope()` before asserting dict shape. MCP-side contract is preserved; wrapper change is mechanical.

**Regression tests (`tests/regression/test_regression.py`):** Fisher math unchanged — p-value fixtures stay valid. Only return-type wrapping changes.

**Existing unit tests (`tests/unit/test_enrichment.py`, `tests/unit/test_api_functions.py`):** migrate assertions from `result["key"]` to `result.to_envelope()["key"]` or directly to the object API.

**Evals (`tests/evals/test_eval.py`):** audit for raw dict access; update to call `.to_envelope()` if needed.

## Breaking change callout

**Python API:** `api.pathway_enrichment` and `api.cluster_enrichment` now return `EnrichmentResult` instead of a dict.

**MCP schema:** the `verbose` parameter is removed from the `pathway_enrichment` and `cluster_enrichment` tool schemas. No current user relies on it (the flag had no observable effect — it stripped columns that were never populated).

**All internal callers break:**

- `multiomics_explorer/mcp_server/tools.py` — updated in this spec
- `multiomics_explorer/__init__.py` — re-exports may need adjustment
- `examples/pathway_enrichment.py` — update to show `.explain()` / DataFrame access
- `tests/unit/test_enrichment.py`, `tests/unit/test_api_functions.py`
- `tests/integration/test_api_contract.py`, `tests/integration/test_mcp_tools.py`
- `tests/regression/test_regression.py`
- `tests/evals/test_eval.py`

No external consumers (this is an internal read-only tool). Callable-shape change is fully contained.

## Documentation to update

Hand-edited sources:

- **`multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md`** — the canonical doc, served as `docs://analysis/enrichment` by the MCP server ([server.py:61-68](multiomics_explorer/mcp_server/server.py#L61-L68)). **Must reflect every API change in this spec**:
  - `EnrichmentResult` replaces the dict return type for `api.pathway_enrichment` / `api.cluster_enrichment` / `fisher_ora`
  - New Pydantic models: `DEStats`, `GeneRef`, `EnrichmentExplanation`
  - Accessors: `.explain()`, `.overlap_genes()`, `.background_genes()`, `.cluster_context()`, `.why_skipped()`, `.to_compare_cluster_frame()`, `.missing_terms()`
  - Serialization: `.generate_summary()` (Python) vs `.to_envelope()` (MCP bridge); no `verbose` or `include_inputs` flags
  - `fisher_ora` signature change — takes `EnrichmentInputs` + `term2gene`, returns `EnrichmentResult`
  - `EnrichmentInputs.gene_stats` field (new)
  - `term2gene` required vs optional columns (`gene_name`, `product` optional)
  - `enrichment_params` dict for interpretability
  - Sort order for `overlap_genes` / `background_genes`
  - Bring up to date with the 2026-04-17 `cluster_enrichment` additions that never propagated from the stale duplicate.
- **`examples/pathway_enrichment.py`** — **must be rewritten** to demonstrate every surface change:
  - New return type — show `result.results` for DataFrame access, `result.inputs` for intermediates
  - `result.explain(cluster, term_id)` returning `EnrichmentExplanation` with rich narrative (include a notebook-style `_repr_markdown_` demonstration if possible)
  - `result.overlap_genes(c, t)` and `result.background_genes(c, t)` returning `list[GeneRef]`
  - `result.to_compare_cluster_frame()` for clusterProfiler-style plotting
  - `result.generate_summary()` for the aggregate view
  - `result.to_envelope()` for the MCP-compatible dict (if relevant)
  - Custom `term2gene` path — demo a hand-built DataFrame without `gene_name` / `product` columns, showing graceful degradation
- `multiomics_explorer/inputs/tools/pathway_enrichment.yaml` — drop the `verbose` parameter from the tool schema; it was phantom (no behavior). Note that rich per-row overlap lives in the Python API (`.explain()` / accessors).
- `multiomics_explorer/inputs/tools/cluster_enrichment.yaml` — same change.

**Delete (orphaned duplicate):**

- `multiomics_explorer/analysis/enrichment.md` — not referenced by any runtime code. It was kept in sync with the skill copy manually and has already drifted. Only referenced by historical design specs, which don't need updating.

Auto-generated (regenerated from YAML + updated Pydantic response models in `tools.py`):

- `multiomics_explorer/skills/multiomics-kg-guide/references/tools/pathway_enrichment.md`
- `multiomics_explorer/skills/multiomics-kg-guide/references/tools/cluster_enrichment.md`

**Regeneration command** (run after YAML + `tools.py` edits):

```bash
uv run python scripts/build_about_content.py
```

(Delete the existing `pathway_enrichment.md` / `cluster_enrichment.md` first, or pass a regeneration flag — see `scripts/build_about_content.py --help` for current semantics.)

Do not edit the `references/tools/*.md` files by hand — they get overwritten on the next regeneration.

## Open questions deferred to implementation

- **Test-input fixtures.** Hand-rolled `EnrichmentInputs` + `term2gene` for unit tests — what shape of toy organism (a few clusters, handful of terms, a mix of named/unnamed genes, one cluster with `gene_stats` populated, one without). Pick concrete numbers at implementation time.
- **Deprecation path for direct `fisher_ora` callers using dict-form `gene_sets`.** If existing tests call `fisher_ora` with raw dicts, we either (a) wrap them in `EnrichmentInputs` at the callsites, or (b) keep a thin back-compat shim `_fisher_ora_dicts(gene_sets, background, term2gene, ...)` inside the module for tests only. Decide during implementation; prefer (a).
