# Tool spec: differential_expression_by_gene

## Purpose

Given gene locus tags and/or experiment IDs, return differential expression
results for those genes across experiments. One row per gene × experiment ×
timepoint (long form, all context inlined — no separate metadata tables).

Phase 3 — Expression. Gene-centric. Same organism at a time.

Use `differential_expression_by_ortholog` for cross-organism comparison via
homology.

## Out of Scope

- **Cross-organism comparison** — use `differential_expression_by_ortholog`
- **Experiment metadata / discovery** — use `list_experiments`
- **Gene discovery** — use `genes_by_function`, `genes_by_ontology`, etc.
- **Raw expression Cypher** — use `run_cypher` (available now as escape hatch)

## Status / Prerequisites

- [x] KG explored (2026-03-24)
- [x] KG spec: `docs/kg-specs/kg-spec-expression-call.md` — `expression_status` on edges + directional counts on Experiment/Gene nodes
- [x] Scope reviewed with user
- [x] KG rebuilt (2026-03-24) — `r.expression_status` verified on all 188,501 edges
- [x] Ready for Phase 2 (build)

**Workflow note:** KG rebuild in progress. Once complete, verify `r.expression_status`
is populated on edges, then proceed to Phase 2 (build).

## Use cases

- **Gene profile across conditions** — "Show expression of psbA across all
  experiments" → `locus_tags=["PMM0001"]`, no experiment filter
- **Batch gene × experiment** — "Expression of [PMM0001, PMM0845] in iron
  stress experiments" → both filters, `significant_only=True`
- **Top DE genes in experiment** — "Strongest responders in experiment X" →
  `experiment_ids=[...]`, `significant_only=True`, `limit=20`
- **Time course profile** — "Expression of [genes] across all time points in
  experiment Y" → `experiment_ids=[Y]`, default limit, look at timepoint fields
- **Filter by direction** — "Upregulated genes in coculture" →
  `direction="up"`, `significant_only=True`
- **Chained with Phase 2** — `genes_by_function` → locus_tags →
  `differential_expression_by_gene`

## KG dependencies

Existing properties verified in live KG (2026-03-24). One new property
needed: `expression_status` — see `docs/kg-specs/kg-spec-expression-call.md`.

### Edge properties (`Changes_expression_of`)

| KG property | Output field | Notes |
|---|---|---|
| `log2_fold_change` | `log2fc` | float |
| `adjusted_p_value` | `padj` | float |
| `expression_direction` | — | Used at KG build time to compute `expression_status` |
| `significant` | — | Used at KG build time to compute `expression_status` |
| `expression_status` | `expression_status` | **New** — precomputed enum: `"significant_up"`, `"significant_down"`, `"not_significant"` |
| `rank_by_effect` | `rank` | rank by \|log2FC\| within experiment × timepoint; 1 = strongest |
| `time_point` | `timepoint` | label string (e.g. "20h", "day 31") |
| `time_point_hours` | `timepoint_hours` | float, nullable |
| `time_point_order` | `timepoint_order` | int, for sorting time courses |

**`rank_by_effect` scope confirmed**: ranks within (experiment × timepoint);
`max_rank == gene_count` for that time point. Applies to both time course and
single-timepoint experiments.

### Experiment node

Used for: `name` (→ `experiment_name`), `treatment_type`, `treatment`, `organism_strain`,
`omics_type`, `coculture_partner`, `gene_count`, `significant_count`,
`time_point_count`, `time_point_hours`, `time_point_significants`.

### Gene node

Used for: `locus_tag`, `organism_strain`, `gene_name`, `product`
(from `function_description`), `gene_category`, `function_description`.

Precomputed: `expression_edge_count`, `significant_expression_count` — available
for verbose mode as context, but **not** used in summary (summary is computed
from edges to respect the active filters).

### Scale

- 188,501 total edges; 42,687 significant
- 76 experiments: 47 single-timepoint, 29 time-course (2–7 time points each)
- Focused queries (locus_tags + experiment_ids) scan < ~10K edges

---

## Tool Signature

```python
@mcp.tool(
    tags={"expression", "genes"},
    annotations={"readOnlyHint": True},
)
async def differential_expression_by_gene(
    ctx: Context,
    locus_tags: Annotated[list[str] | None, Field(
        description="Gene locus tags. E.g. ['PMM0001', 'PMM0845']. "
                    "Get these from resolve_gene / gene_overview.",
    )] = None,
    experiment_ids: Annotated[list[str] | None, Field(
        description="Experiment IDs to restrict to. "
                    "Get these from list_experiments.",
    )] = None,
    direction: Annotated[Literal["up", "down"] | None, Field(
        description="Filter by expression direction.",
    )] = None,
    significant_only: Annotated[bool, Field(
        description="If true, return only statistically significant results.",
    )] = False,
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Add product, experiment_name, treatment, "
                    "gene_category, omics_type, coculture_partner to each row.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> DifferentialExpressionByGeneResponse:
    """Gene-centric differential expression. One row per gene × experiment × timepoint.

    Returns summary statistics (always) + top results sorted by |log2FC|
    (strongest effects first). Default limit=5 gives a quick overview.
    Set summary=True for counts only, or increase limit for more rows.

    All inputs must refer to the same organism. If locus_tags span multiple
    organisms, or experiment_ids span multiple organisms, or locus_tag organisms
    don't match experiment organisms, a ValueError is raised. Call once per
    organism.

    At least one of locus_tags or experiment_ids is strongly recommended.
    Without any filter, results cover the full KG (188K rows).

    The `expression_status` field uses the publication-specific threshold from
    each experiment's original paper (not a uniform padj<0.05 cutoff). A row
    with padj=0.03 may still be `"not_significant"` if the paper used a stricter
    threshold or required a minimum fold-change.

    For cross-organism comparison via ortholog groups, use
    differential_expression_by_ortholog.
    """
```

**Return envelope:** `organism_strain, matching_genes, total_rows, rows_by_status,
median_abs_log2fc, max_abs_log2fc, experiment_count, top_categories, experiments,
returned, truncated, not_found, no_expression, results`

**Per-result columns (compact — 11):**
`locus_tag`, `gene_name`,
`experiment_id`, `condition_type`, `timepoint`, `timepoint_hours`, `timepoint_order`,
`log2fc`, `padj`, `rank`, `expression_status`

**Verbose adds (6):**
`product`, `experiment_name`, `treatment`,
`gene_category`, `omics_type`, `coculture_partner`

**Sort key:** `ABS(log2fc) DESC, locus_tag ASC, experiment_id ASC,
timepoint_order ASC` — strongest effects first; stable within a gene × experiment
series.

---

## Summary fields

**Naming convention:**
- `_rows` suffix → gene × experiment × timepoint rows
- `_genes` suffix → distinct genes
- `rows_by_status` → dict keyed by `expression_status` values, counting rows

### `expression_status` enum (on KG edge + result rows)

| Value | Meaning |
|---|---|
| `"significant_up"` | Significant and upregulated (per publication threshold) |
| `"significant_down"` | Significant and downregulated (per publication threshold) |
| `"not_significant"` | Not significant; direction readable from `log2fc` sign |

Stored as `r.expression_status` on `Changes_expression_of` edges (KG schema change —
see `docs/kg-specs/kg-spec-expression-call.md`). Derived from existing `r.significant`
+ `r.expression_direction` at KG build time.

### `rows_by_status` dict

`{"significant_up": N, "significant_down": N, "not_significant": N}` — appears at
global level, per-experiment, and per-timepoint. Always all three keys present.

### Always present (organism-level — single organism enforced)

| Field | Type | Description |
|---|---|---|
| `organism_strain` | str | The single organism all inputs belong to |
| `matching_genes` | int | Distinct genes present in results (after filters) |
| `total_rows` | int | Total gene × experiment × timepoint rows matching all filters |
| `rows_by_status` | dict | `{"significant_up": N, "significant_down": N, "not_significant": N}` |
| `median_abs_log2fc` | float \| null | Median \|log2FC\| for significant rows only; null if none |
| `max_abs_log2fc` | float \| null | Max \|log2FC\| for significant rows only; null if none |
| `experiment_count` | int | Number of experiments in results (after filters) |
| `top_categories` | list | Top gene categories by distinct significantly-expressed genes, max 5. `[{"category": str, "total_genes": int, "significant_genes": int}]`. `total_genes` = all input genes in that category; `significant_genes` = those with at least one significant row. |
| `returned` | int | Rows in `results` |
| `truncated` | bool | True if `total_rows > returned` |

### `experiments` entry (top-level list)

| Field | Type | Description |
|---|---|---|
| `experiment_id` | str | |
| `experiment_name` | str | Human-readable name from `e.name` |
| `omics_type` | str | |
| `matching_genes` | int | Distinct genes in this experiment (after all active filters) |
| `rows_by_status` | dict | `{"significant_up": N, "significant_down": N, "not_significant": N}` |
| `timepoints` | list \| null | Per-timepoint breakdown (see below). Null when `is_time_course=false`. |

### `timepoints` entry (nested in `experiments`)

| Field | Type | Description |
|---|---|---|
| `timepoint` | str \| null | Timepoint label (e.g. "2h", "day 31"). Null for experiments with no label on edges. |
| `timepoint_hours` | float \| null | Numeric hours. Null for non-numeric timepoints (e.g. "days 60+89"). No sentinel — genuine null. |
| `timepoint_order` | int | Sort key. Always populated. |
| `matching_genes` | int | Distinct genes at this timepoint |
| `rows_by_status` | dict | `{"significant_up": N, "significant_down": N, "not_significant": N}` |

### Batch handling

| Field | Type | Description |
|---|---|---|
| `not_found` | list[str] | Input locus_tags that don't exist in KG |
| `no_expression` | list[str] | Locus tags in KG but with no expression data matching filters |

`no_expression` is biologically meaningful — some genes were never profiled, or
the given experiment filters exclude all their data. Distinguishing from `not_found`
(bad ID) is important.

**`not_found` / `no_expression` only populated when `locus_tags` is provided.**
When querying by `experiment_ids` only, these fields are empty lists.

### Single-organism validation (raises ValueError)

Enforced in api/ before any KG queries run, using a lightweight pre-query
that resolves organism_strain for all input IDs:

| Case | Error message |
|---|---|
| `locus_tags` from multiple organisms | `"locus_tags span multiple organisms: MED4, MIT9313 — call once per organism"` |
| `experiment_ids` from multiple organisms | `"experiment_ids span multiple organisms: MED4, HOT1A3 — call once per organism"` |
| `locus_tags` organism ≠ `experiment_ids` organism | `"locus_tags are MED4 genes but experiment_ids cover HOT1A3 — organisms must match"` |

Pre-query resolves `DISTINCT g.organism_strain` for locus_tags and
`DISTINCT e.organism_strain` for experiment_ids. Cheap (index lookup).
`organism_strain` in the response is set from the validated single value.

---

## Result-size controls

| Scenario | Recommended call |
|---|---|
| Quick overview (what's available?) | `summary=True` — no rows, just counts |
| Strongest responders in an experiment | `significant_only=True`, `limit=20` |
| Full profile for 1–3 genes | `locus_tags=[...]`, `limit=0` (all rows) |
| Batch annotation of gene list | `significant_only=True`, `summary=True` first |

`limit=0` in the MCP tool returns all matching rows — use with `significant_only=True`
or after checking `total_matching` via summary.

**Default limit:** 5 (MCP), None (api/).

---

## Special handling

### Multi-query pattern

All summary queries always run. Detail query skipped when `limit=0` / `summary=True`.
All queries share the same WHERE clause (same filter parameters).

**Summary query 1 — global stats:**
Returns `total_rows`, `rows_by_status`, `median_abs_log2fc`, `max_abs_log2fc`.

`rows_by_status` uses `apoc.coll.frequencies(collect(r.expression_status))` —
single aggregation over the precomputed enum; always all three keys present.

Uses `percentileCont(CASE WHEN r.expression_status <> "not_significant" THEN abs(r.log2_fold_change) ELSE null END, 0.5)` — nulls from CASE are silently ignored by `percentileCont`, confirmed against live KG.

**Summary query 2 — per-experiment with nested timepoints:**
Returns `experiments` list (flat — single organism enforced, no organism
grouping needed). Each experiment entry contains a nested `timepoints` list
(or null for non-time-course, handled in api/). Also returns `organism_strain`,
`matching_genes`, `experiment_count` from this query.
Aggregates at (experiment × timepoint) level, then re-aggregates to experiment
level using `collect()`. Single-timepoint experiments return `timepoints` with
one entry (not empty — consistent structure).

**Summary query 3 — categories + batch diagnostics:**
Returns `top_categories`, `not_found`, `no_expression`.
(Organism validation is a separate pre-query in api/, not part of this builder.)

`top_categories` uses two counts per category:
- `total_genes`: `count(DISTINCT g.locus_tag)` — all input genes in that category
- `significant_genes`: `count(DISTINCT CASE WHEN r.expression_status <> "not_significant" THEN g.locus_tag END)`
Both count distinct genes, not rows. Sorted by `significant_genes DESC`, top 5.

`experiment_count` is computed in api/ as `len(experiments)` from query 2 — not a separate query field.

**Detail query:**
Returns result rows. Skipped when `limit=0`.

### Significant-only filtering and `expression_status`

`r.expression_status` is a precomputed property on `Changes_expression_of` edges
(see `docs/kg-specs/kg-spec-expression-call.md`). Three values:
`"significant_up"`, `"significant_down"`, `"not_significant"`.

Result rows carry `expression_status` directly from the edge. For non-significant
rows, direction is still readable from `log2fc` sign.

`significant_only=True` → `WHERE r.expression_status <> "not_significant"` in all queries.

`direction="up"` → `WHERE r.expression_status = "significant_up"` (implies significant).
`direction="down"` → `WHERE r.expression_status = "significant_down"` (implies significant).
Both direction values imply significance — non-significant rows are excluded when
direction is set, regardless of `significant_only`.

`rows_by_status` uses `apoc.coll.frequencies(collect(r.expression_status))` — single
aggregation instead of two conditional sums. Safe: `expression_status` is never null.

### Time course vs single-timepoint

The output schema is uniform. For time course experiments, each gene has N rows
(one per timepoint); sort by `timepoint_order ASC` to reconstruct the series.

Null handling (verified against live KG — no sentinels on edges):
- `timepoint`: null for experiments with no label on the edge (e.g. some single-timepoint experiments)
- `timepoint_hours`: null for non-numeric timepoints (e.g. "days 60+89")
- `timepoint_order`: always an integer (1 for single-timepoint experiments)

### No Lucene / no fulltext

Filtering is by exact match on IDs and enum values only.
Text search on gene names → use `genes_by_function` upstream.
Text search on experiments → use `list_experiments` upstream.

---

## Query Builders

**File:** `kg/queries_lib.py`

Three summary builders, all sharing the same signature and WHERE clause logic.
The api/ layer calls all three and merges results.

### `build_differential_expression_by_gene_summary_global`

```python
def build_differential_expression_by_gene_summary_global(
    *,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[str, dict]:
    """Global aggregate stats for differential_expression_by_gene.

    RETURN keys: total_rows, rows_by_status, median_abs_log2fc, max_abs_log2fc.
    rows_by_status = {"significant_up": N, "significant_down": N, "not_significant": N}
    """
```

Uses `apoc.coll.frequencies(collect(r.expression_status))` for `rows_by_status` —
`expression_status` is never null, so `collect()` is safe here.
Uses `percentileCont(CASE WHEN r.expression_status <> "not_significant" THEN
abs(r.log2_fold_change) ELSE null END, 0.5)` — nulls from CASE are
silently ignored by `percentileCont`, confirmed against live KG.
Uses `count(*)` (not `count(r.time_point)`) for `total_rows` — field-level
count excludes NULLs and would undercount experiments with no timepoint label.

### `build_differential_expression_by_gene_summary_by_experiment`

```python
def build_differential_expression_by_gene_summary_by_experiment(
    *,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[str, dict]:
    """Per-experiment breakdown with nested timepoints (single organism enforced).

    RETURN keys: organism_strain, matching_genes, experiment_count, experiments.
    experiments is a list of dicts, each with nested timepoints list.
    rows_by_status = {"significant_up": N, "significant_down": N, "not_significant": N}
    at both experiment and timepoint level.
    api/ strips timepoints key for non-time-course experiments.
    """
```

Two-pass aggregation — verified against live KG:

```cypher
// Pass 1: group by (experiment × timepoint) — g must NOT be in this WITH clause
// (keeping g would make each group (g, e, tp), giving 3×5=15 entries instead of 5)
WITH e, r.time_point AS tp, r.time_point_order AS tpo, r.time_point_hours AS tph,
  collect(DISTINCT g.locus_tag) AS tp_genes,
  collect(r.expression_status) AS tp_calls  // raw list — frequencies computed below

// Pass 2: roll up to experiment level
// rows_by_status: flatten all per-timepoint call lists then compute frequencies
WITH e,
  size(apoc.coll.toSet(apoc.coll.flatten(collect(tp_genes)))) AS matching_genes,
  apoc.coll.frequencies(apoc.coll.flatten(collect(tp_calls))) AS rows_by_status,
  collect({timepoint: tp, timepoint_hours: tph, timepoint_order: tpo,
           matching_genes: size(tp_genes),
           rows_by_status: apoc.coll.frequencies(tp_calls)}) AS timepoints

// Pass 3: collect experiments (organism already validated as single value)
WITH collect({experiment_id: e.id, experiment_name: e.name, omics_type: e.omics_type,
              is_time_course: e.is_time_course,
              matching_genes: matching_genes,
              rows_by_status: rows_by_status,
              timepoints: timepoints}) AS experiments,
     e.organism_strain AS organism_strain  // same value for all rows — safe to use
RETURN organism_strain, experiments
```

`gene_count` at experiment level = `apoc.coll.toSet(apoc.coll.flatten(...))` on
the per-timepoint gene lists — correctly deduplicates genes across timepoints.
Do NOT use `sum(tp_gene_count)` — that would give rows × timepoints, not distinct genes.

**Null handling (verified against live KG):**
- `collect()` on a scalar **silently drops NULLs** — do NOT use
  `collect(r.time_point)` directly. Use GROUP BY so each NULL
  timepoint forms its own group row, then collect the map.
- `collect({timepoint: tp, ...})` with `tp = null` **preserves the
  null** inside the map — safe for nested structures.
- `r.expression_status` is never null — `collect(r.expression_status)` is safe.

Returns `is_time_course` per experiment so api/ can decide whether to
populate or omit `timepoints` — matching `list_experiments` pattern
exactly: omit key for non-time-course, Pydantic model defaults to `null`.

### `build_differential_expression_by_gene_summary_diagnostics`

```python
def build_differential_expression_by_gene_summary_diagnostics(
    *,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[str, dict]:
    """Top categories + batch diagnostics for differential_expression_by_gene.

    RETURN keys: top_categories, not_found, no_expression.
    """
```

`top_categories` uses `count(DISTINCT g.locus_tag)` — counts unique genes
not rows, to avoid inflation from genes appearing in many experiments.
Confirmed against live KG.

`not_found` / `no_expression` only computed when `locus_tags` is provided,
using UNWIND + OPTIONAL MATCH pattern. Both are empty lists when only
`experiment_ids` is provided.

### `build_differential_expression_by_gene`

```python
def build_differential_expression_by_gene(
    *,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for differential_expression_by_gene.

    RETURN keys (compact): locus_tag, gene_name, organism_strain,
    experiment_id, condition_type, timepoint, timepoint_hours, timepoint_order,
    log2fc, padj, rank, expression_status.
    RETURN keys (verbose): adds product, experiment_name, treatment,
    gene_category, omics_type, coculture_partner.
    """
```

Property mappings:
- `g.gene_name` → `gene_name` (nullable)
- `g.function_description` → `product` (verbose)
- `e.name` → `experiment_name` (verbose)
- `e.treatment_type` → `condition_type`
- `e.treatment` → `treatment`
- `r.log2_fold_change` → `log2fc`
- `r.adjusted_p_value` → `padj`
- `r.rank_by_effect` → `rank`
- `r.expression_status` → `expression_status` (precomputed enum on edge)
- `r.time_point` → `timepoint`
- `r.time_point_hours` → `timepoint_hours`

Sort: `ORDER BY ABS(r.log2_fold_change) DESC, g.locus_tag ASC, e.id ASC, r.time_point_order ASC`

---

## API Function

**File:** `api/functions.py`

```python
def differential_expression_by_gene(
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Query gene-centric differential expression data.

    Returns dict with summary fields + results list. Results are long form:
    one row per gene × experiment × timepoint, all context inlined.

    Raises:
        ValueError: if locus_tags or experiment_ids span multiple organisms,
            or if their organisms don't match each other.

    Returns:
        dict with keys: organism_strain, matching_genes, total_rows,
        rows_by_status, median_abs_log2fc, max_abs_log2fc, experiment_count,
        top_categories, experiments, returned, truncated, not_found,
        no_expression, results.
        experiments list is flat (single organism); each entry has nested timepoints.
    """
```

- `summary=True` → `limit=0`
- `limit=0` → `results=[]`, `returned=0`, `truncated = total_rows > 0` (signals rows exist but aren't returned)
- Validate `direction` against `{"up", "down"}`
- **Pre-query organism validation** (before any summary queries):
  - Resolve `DISTINCT g.organism_strain` for `locus_tags` (if provided)
  - Resolve `DISTINCT e.organism_strain` for `experiment_ids` (if provided)
  - Raise `ValueError` if either set has > 1 organism, or if sets are disjoint
  - Set `organism_strain` in response from the validated single value
- Always run summary queries → all summary fields
- Skip detail when `limit=0`
- Rename KG properties to output field names (`log2_fold_change` → `log2fc`, etc.)
- Convert APOC `apoc.coll.frequencies` result `[{item, count}]` → `{item: count}` dict for `rows_by_status`
- Sort `experiments` by `(rows_by_status["significant_up"] + rows_by_status["significant_down"]) DESC`
- Strip `timepoints` key (set to null) for experiments where `is_time_course = "false"`

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

```python
class ExpressionStatusBreakdown(BaseModel):
    significant_up: int = Field(default=0, description="Rows with significant upregulation (e.g. 3)")
    significant_down: int = Field(default=0, description="Rows with significant downregulation (e.g. 1)")
    not_significant: int = Field(default=0, description="Rows not meeting significance threshold (e.g. 12)")

class ExpressionTimepoint(BaseModel):
    timepoint: str | None = Field(description="Timepoint label (e.g. 'day 18', 'days 60+89'). Null when edge has no label.")
    timepoint_hours: float | None = Field(description="Hours numeric value (e.g. 432.0). Null for non-numeric labels like 'days 60+89'.")
    timepoint_order: int = Field(description="Sort key for time course reconstruction (e.g. 1)")
    matching_genes: int = Field(description="Distinct genes at this timepoint (e.g. 5)")
    rows_by_status: ExpressionStatusBreakdown = Field(description="Row counts by expression_status at this timepoint")

class ExpressionByExperiment(BaseModel):
    experiment_id: str = Field(description="Experiment ID (e.g. '10.1101/2025.11.24.690089_...')")
    experiment_name: str = Field(description="Human-readable name (e.g. 'HOT1A3 PRO99-lowN nutrient starvation (RNASEQ)')")
    omics_type: str = Field(description="Omics type (e.g. 'RNASEQ', 'PROTEOMICS')")
    matching_genes: int = Field(description="Distinct genes with data in this experiment (e.g. 5)")
    rows_by_status: ExpressionStatusBreakdown = Field(description="Row counts by expression_status across all timepoints")
    timepoints: list[ExpressionTimepoint] | None = Field(default=None, description="Per-timepoint breakdown, sorted by timepoint_order. Null for non-time-course experiments.")

class ExpressionTopCategory(BaseModel):
    category: str = Field(description="Gene category (e.g. 'Signal transduction')")
    total_genes: int = Field(description="All input genes in this category (e.g. 2)")
    significant_genes: int = Field(description="Genes with at least one significant row (e.g. 2)")

class ExpressionRow(BaseModel):
    # Compact (always present)
    locus_tag: str = Field(description="Gene locus tag (e.g. 'ACZ81_01830')")
    gene_name: str | None = Field(description="Gene name (e.g. 'amtB'). Null if unannotated.")
    experiment_id: str = Field(description="Experiment ID (e.g. '10.1101/2025.11.24.690089_...')")
    condition_type: str = Field(description="Treatment type from experiment (e.g. 'nitrogen_stress')")
    timepoint: str | None = Field(description="Timepoint label (e.g. 'days 60+89'). Null when edge has no label.")
    timepoint_hours: float | None = Field(description="Numeric hours (e.g. 432.0). Null for non-numeric labels.")
    timepoint_order: int = Field(description="Sort key for time course order (e.g. 3)")
    log2fc: float = Field(description="Log2 fold change (e.g. 3.591). Positive = up.")
    padj: float | None = Field(description="Adjusted p-value (e.g. 1.13e-12). Null if not computed.")
    rank: int = Field(description="Rank by |log2FC| within experiment × timepoint; 1 = strongest (e.g. 77)")
    expression_status: Literal["significant_up", "significant_down", "not_significant"] = Field(
        description="Significance call using publication-specific threshold (e.g. 'significant_up')"
    )
    # Verbose (present when verbose=True)
    product: str | None = Field(default=None, description="Gene product description (e.g. 'Ammonium transporter')")
    experiment_name: str | None = Field(default=None, description="Human-readable experiment name")
    treatment: str | None = Field(default=None, description="Treatment details (e.g. 'PRO99-lowN nutrient starvation')")
    gene_category: str | None = Field(default=None, description="Gene functional category (e.g. 'Inorganic ion transport')")
    omics_type: str | None = Field(default=None, description="Omics type (e.g. 'RNASEQ')")
    coculture_partner: str | None = Field(default=None, description="Coculture partner organism, if applicable")

class DifferentialExpressionByGeneResponse(BaseModel):
    organism_strain: str = Field(description="Single organism for all results (e.g. 'Alteromonas macleodii HOT1A3')")
    matching_genes: int = Field(description="Distinct genes in results after filters (e.g. 5)")
    total_rows: int = Field(description="Total gene × experiment × timepoint rows matching filters (e.g. 15)")
    rows_by_status: ExpressionStatusBreakdown = Field(description="Row counts by expression_status across all results")
    median_abs_log2fc: float | None = Field(description="Median |log2FC| for significant rows only (e.g. 1.978). Null if no significant rows.")
    max_abs_log2fc: float | None = Field(description="Max |log2FC| for significant rows only (e.g. 3.591). Null if no significant rows.")
    experiment_count: int = Field(description="Number of experiments in results (e.g. 1)")
    top_categories: list[ExpressionTopCategory] = Field(description="Top gene categories by significant gene count, max 5")
    experiments: list[ExpressionByExperiment] = Field(description="Per-experiment summary with nested timepoint breakdown, sorted by significant row count desc")
    not_found: list[str] = Field(default_factory=list, description="Input locus_tags not found in KG")
    no_expression: list[str] = Field(default_factory=list, description="Locus tags in KG but with no expression data matching filters")
    returned: int = Field(description="Rows in results (e.g. 5)")
    truncated: bool = Field(description="True if total_rows > returned")
    results: list[ExpressionRow] = Field(default_factory=list)
```

Thin wrapper: `Response(**data)` with standard error handling
(ValueError → ToolError, Exception → ToolError with prefix).

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_differential_expression_by_gene_summary_global()` |
| 2 | Query builder | `kg/queries_lib.py` | `build_differential_expression_by_gene_summary_by_experiment()` |
| 3 | Query builder | `kg/queries_lib.py` | `build_differential_expression_by_gene_summary_diagnostics()` |
| 4 | Query builder | `kg/queries_lib.py` | `build_differential_expression_by_gene()` |
| 5 | Pre-query | `kg/queries_lib.py` | `build_resolve_organism_for_locus_tags()` + `build_resolve_organism_for_experiments()` (lightweight organism validation queries) |
| 6 | API function | `api/functions.py` | `differential_expression_by_gene()` |
| 7 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add to imports + `__all__` |
| 8 | MCP wrapper | `mcp_server/tools.py` | `@mcp.tool()` wrapper inside `register_tools()` |
| 9 | Unit tests | `tests/unit/test_query_builders.py` | 4 builder test classes |
| 10 | Unit tests | `tests/unit/test_api_functions.py` | `TestDifferentialExpressionByGene` |
| 11 | Unit tests | `tests/unit/test_tool_wrappers.py` | `TestDifferentialExpressionByGeneWrapper` + update `EXPECTED_TOOLS` |
| 12 | Integration | `tests/integration/test_mcp_tools.py` | Smoke test against live KG |
| 13 | Integration | `tests/integration/test_api_contract.py` | `TestDifferentialExpressionByGeneContract` |
| 14 | Regression | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS` |
| 15 | Eval cases | `tests/evals/cases.yaml` + `tests/evals/test_eval.py` | Eval cases + add to `TOOL_BUILDERS` |
| 16 | About content | `multiomics_explorer/inputs/tools/differential_expression_by_gene.yaml` | Input YAML |
| 17 | Docs | `CLAUDE.md` | Add row to MCP Tools table |

---

## Example Response

**Call:** `locus_tags=["ACZ81_01830","ACZ81_04825","ACZ81_15555","ACZ81_15560","ACZ81_13905"]`
(amtB, glnD, glnL, glnG, glnE — HOT1A3 nitrogen regulators),
`experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_hot1a3_rnaseq_axenic"]`,
`limit=5`. Verified against live KG (2026-03-24).

```json
{
  "organism_strain": "Alteromonas macleodii HOT1A3",
  "matching_genes": 5,
  "total_rows": 15,
  "rows_by_status": {"significant_up": 3, "significant_down": 0, "not_significant": 12},
  "median_abs_log2fc": 1.978,
  "max_abs_log2fc": 3.591,
  "experiment_count": 1,
  "top_categories": [
    {"category": "Signal transduction",        "total_genes": 2, "significant_genes": 2},
    {"category": "Inorganic ion transport",     "total_genes": 1, "significant_genes": 1},
    {"category": "Post-translational modification", "total_genes": 1, "significant_genes": 0},
    {"category": "Coenzyme metabolism",         "total_genes": 1, "significant_genes": 0}
  ],
  "experiments": [
    {
      "experiment_id": "10.1101/2025.11.24.690089_..._axenic",
      "experiment_name": "HOT1A3 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "omics_type": "RNASEQ",
      "matching_genes": 5,
      "rows_by_status": {"significant_up": 3, "significant_down": 0, "not_significant": 12},
      "timepoints": [
        {"timepoint": "day 18",     "timepoint_hours": 432.0, "timepoint_order": 1,
         "matching_genes": 5, "rows_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 5}},
        {"timepoint": "day 31",     "timepoint_hours": 744.0, "timepoint_order": 2,
         "matching_genes": 5, "rows_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 5}},
        {"timepoint": "days 60+89", "timepoint_hours": null,  "timepoint_order": 3,
         "matching_genes": 5, "rows_by_status": {"significant_up": 3, "significant_down": 0, "not_significant": 2}}
      ]
    }
  ],
  "not_found": [],
  "no_expression": [],
  "returned": 5,
  "truncated": true,
  "results": [
    {"locus_tag": "ACZ81_01830", "gene_name": "amtB", "experiment_id": "...", "condition_type": "nitrogen_stress",
     "timepoint": "days 60+89", "timepoint_hours": null,  "timepoint_order": 3,
     "log2fc":  3.591, "padj": 1.13e-12, "rank":  77,  "expression_status": "significant_up"},
    {"locus_tag": "ACZ81_15555", "gene_name": "glnL", "experiment_id": "...", "condition_type": "nitrogen_stress",
     "timepoint": "days 60+89", "timepoint_hours": null,  "timepoint_order": 3,
     "log2fc":  1.978, "padj": 2.31e-6,  "rank": 410,  "expression_status": "significant_up"},
    {"locus_tag": "ACZ81_15560", "gene_name": "glnG", "experiment_id": "...", "condition_type": "nitrogen_stress",
     "timepoint": "days 60+89", "timepoint_hours": null,  "timepoint_order": 3,
     "log2fc":  1.745, "padj": 2.11e-5,  "rank": 544,  "expression_status": "significant_up"},
    {"locus_tag": "ACZ81_01830", "gene_name": "amtB", "experiment_id": "...", "condition_type": "nitrogen_stress",
     "timepoint": "day 18",     "timepoint_hours": 432.0, "timepoint_order": 1,
     "log2fc":  0.856, "padj": 0.259,    "rank": 1104, "expression_status": "not_significant"},
    {"locus_tag": "ACZ81_01830", "gene_name": "amtB", "experiment_id": "...", "condition_type": "nitrogen_stress",
     "timepoint": "day 31",     "timepoint_hours": 744.0, "timepoint_order": 2,
     "log2fc":  0.556, "padj": 0.510,    "rank": 1716, "expression_status": "not_significant"}
  ]
}
```

**Notes on this example:**
- Response is **late-stage** — no significant expression at day 18 or day 31, all 3 significant events at days 60+89. Visible immediately from `timepoints[].rows_by_status`.
- `glnE` (ACZ81_13905) has padj=0.035 but `expression_status="not_significant"` — the paper uses a stricter threshold than padj<0.05.
- `rows_by_status` from `apoc.coll.frequencies` omits zero-count keys; api/ fills in `"significant_down": 0`.
- Timepoints from `collect()` are unordered — api/ sorts by `timepoint_order`.

---

## Tests

| Layer | File | Test class |
|---|---|---|
| Query builder (global summary) | `test_query_builders.py` | `TestBuildDifferentialExpressionByGeneSummaryGlobal` |
| Query builder (by_experiment summary) | `test_query_builders.py` | `TestBuildDifferentialExpressionByGeneSummaryByExperiment` |
| Query builder (diagnostics summary) | `test_query_builders.py` | `TestBuildDifferentialExpressionByGeneSummaryDiagnostics` |
| Query builder (detail) | `test_query_builders.py` | `TestBuildDifferentialExpressionByGene` |
| API | `test_api_functions.py` | `TestDifferentialExpressionByGene` |
| MCP wrapper | `test_tool_wrappers.py` | `TestDifferentialExpressionByGeneWrapper` + update EXPECTED_TOOLS |
| Integration | `test_mcp_tools.py` | New class |
| Integration | `test_tool_correctness_kg.py` | `TestDifferentialExpressionByGeneCorrectnessKG` |
| Contract | `test_api_contract.py` | `TestDifferentialExpressionByGeneContract` |
| Regression | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS` |
| Evals | `tests/evals/cases.yaml` | New cases |
| Evals | `tests/evals/test_eval.py` | Add to `TOOL_BUILDERS` |

**Key test scenarios:**

- Single gene, no experiment filter → multiple experiments returned
- Single experiment, no gene filter, `significant_only=True` → top DE genes
- `summary=True` → `results=[]`, summary fields populated
- `direction="up"` + `significant_only=True` → only up-significant rows
- `not_found` — locus_tag that doesn't exist in KG
- `no_expression` — locus_tag that exists but has no expression data
- Multi-organism locus_tags → ValueError with organism list in message
- Multi-organism experiment_ids → ValueError with organism list in message
- locus_tags organism ≠ experiment_ids organism → ValueError
- Time course experiment — same gene appears N times (N time points)
- `limit=0` → all rows returned (use small fixture)
- Both `locus_tags` and `experiment_ids` provided → intersection

**Summary field consistency:** `total_rows` must equal the number of edges
that would be returned without `limit`. `rows_by_status` values must sum to
`total_rows`. `matching_genes` must equal `len({r["locus_tag"] for r in results})`
when `limit=None`.

---

## About Content

- Create `inputs/tools/differential_expression_by_gene.yaml`
- Run `build_about_content.py differential_expression_by_gene`
- Verify: `test_about_content.py` + `test_about_examples.py`

---

## Documentation

- `CLAUDE.md`: add to tool table
- `transition_plan_v3.md`: mark E2 `differential_expression_by_gene` as done when complete

## Code Review

Run code-review skill (full checklist) as final step.
