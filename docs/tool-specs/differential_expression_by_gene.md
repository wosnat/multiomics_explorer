# Tool spec: differential_expression_by_gene

## Purpose

Given an organism, gene locus tags, and/or experiment IDs, return differential
expression results. One row per gene × experiment × timepoint (long form, all
context inlined — no separate metadata tables).

At least one of `organism`, `locus_tags`, or `experiment_ids` is required.

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

**Workflow note:** KG rebuild complete. Verified: `r.expression_status` on all
188,501 edges (19,783 significant_up / 22,904 significant_down / 145,814 not_significant).

## Use cases

- **Organism overview** — "What's the expression landscape for MED4?" →
  `organism="MED4"`, `summary=True` — 47K edges summarised without row data
- **Organism top responders** — "Strongest responders in MED4" →
  `organism="MED4"`, `significant_only=True`, `limit=20`
- **Gene profile across conditions** — "Show expression of psbA across all
  experiments" → `locus_tags=["PMM0001"]`, no experiment filter
- **Batch gene × experiment** — "Expression of [PMM0001, PMM0845] in iron
  stress experiments" → both filters, `significant_only=True`
- **Top DE genes in experiment** — "Strongest responders in experiment X" →
  `experiment_ids=[...]`, `significant_only=True`, `limit=20`
- **Time course profile** — "Expression of [genes] across all time points in
  experiment Y" → `experiment_ids=[Y]`, default limit, look at timepoint fields
- **Filter by direction** — "Upregulated genes in coculture" →
  `direction="up"` (implies significant — no need for `significant_only=True`)
- **Chained with Phase 2** — `genes_by_function` → locus_tags →
  `differential_expression_by_gene`

## KG dependencies

All properties present in live KG (2026-03-24). `expression_status` added
in KG rebuild 2026-03-24 — see `docs/kg-specs/kg-spec-expression-call.md`.

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
`omics_type`, `coculture_partner`, `gene_count`, `significant_up_count`, `significant_down_count`,
`time_point_count`, `time_point_hours`, `time_point_significant_up`, `time_point_significant_down`.

### Gene node

Used for: `locus_tag`, `organism_strain`, `gene_name`, `product`
(from `function_description`), `gene_category`, `function_description`.

Precomputed: `expression_edge_count`, `significant_up_count`, `significant_down_count` —
available for verbose mode as context, but **not** used in summary (summary is computed
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
    organism: Annotated[str | None, Field(
        description="Organism name or partial match (e.g. 'MED4', "
                    "'Prochlorococcus MED4'). Fuzzy word-based matching "
                    "(same as list_experiments). "
                    "Get valid names from list_organisms.",
    )] = None,
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

    At least one of organism, locus_tags, or experiment_ids is required.
    All inputs must refer to the same organism — call once per organism.

    When organism is the only filter, it scopes to that organism's full
    expression data (e.g. MED4 = 47K edges). Combine with summary=True or
    significant_only=True + limit for manageable results.

    When locus_tags and/or experiment_ids are also provided, organism acts as
    validation (must match the organism inferred from those IDs).

    The `expression_status` field uses the publication-specific threshold from
    each experiment's original paper (not a uniform padj<0.05 cutoff). A row
    with padj=0.03 may still be `"not_significant"` if the paper used a stricter
    threshold or required a minimum fold-change.

    For cross-organism comparison via ortholog groups, use
    differential_expression_by_ortholog.
    """
```

### Parameter interactions: `organism`, `locus_tags`, `experiment_ids`

At least one required. `ValueError` raised when none provided.

| organism | locus_tags | experiment_ids | Behavior |
|---|---|---|---|
| None | None | None | **Reject** — `ValueError("at least one of organism, locus_tags, or experiment_ids is required")` |
| None | `[lts]` | None | All experiments for those genes. Organism inferred from genes. |
| None | None | `[eids]` | All genes in those experiments. Organism inferred from experiments. |
| None | `[lts]` | `[eids]` | Intersection — those genes in those experiments. Organism inferred + cross-validated. |
| `"org"` | None | None | All expression for that organism. Fuzzy match resolves to full `organism_strain`. |
| `"org"` | `[lts]` | None | Organism validates gene organism. Functionally same as `(None, lts, None)` after validation. |
| `"org"` | None | `[eids]` | Organism validates experiment organism. Functionally same as `(None, None, eids)` after validation. |
| `"org"` | `[lts]` | `[eids]` | Organism validates both. Functionally same as `(None, lts, eids)` after validation. |

**Organism fuzzy matching** — same word-based CONTAINS as `list_experiments`:
`"MED4"` matches `"Prochlorococcus MED4"`, `"HOT1A3"` matches
`"Alteromonas macleodii HOT1A3"`. Uses `e.organism_strain` (verified:
`g.organism_strain == e.organism_strain` for all 188,501 edges).

**Scale by organism (significant-only):**
MED4 = 8,460 rows, HOT1A3 = 12,168, MIT1002 = 7,296, NATL2A = 5,754,
MIT9313 = 6,640, others < 1K. All manageable with `summary=True` or `limit`.

**Return envelope:** `organism_strain, matching_genes, total_rows, rows_by_status,
median_abs_log2fc, max_abs_log2fc, experiment_count, top_categories, experiments,
returned, truncated, not_found, no_expression, results`

**Per-result columns (compact — 11):**
`locus_tag`, `gene_name`,
`experiment_id`, `treatment_type`, `timepoint`, `timepoint_hours`, `timepoint_order`,
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
global level, per-experiment, and per-timepoint. api/ fills missing zero-count keys
(`apoc.coll.frequencies` omits keys with count=0; all three keys always present in output).

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
| `rows_by_treatment_type` | dict | `{"nitrogen_stress": N, "coculture": N, ...}` — row counts by treatment type |
| `top_categories` | list | Top gene categories by distinct significantly-expressed genes, max 5. `[{"category": str, "total_genes": int, "significant_genes": int}]`. `total_genes` = distinct matched genes in that category (= input genes when `locus_tags` provided; = all matched genes otherwise); `significant_genes` = those with at least one significant row. |
| `returned` | int | Rows in `results` |
| `truncated` | bool | True if `total_rows > returned` |

### `experiments` entry (top-level list)

| Field | Type | Description |
|---|---|---|
| `experiment_id` | str | |
| `experiment_name` | str | Human-readable name from `e.name` |
| `treatment_type` | str | Treatment category (e.g. "nitrogen_stress", "coculture") |
| `omics_type` | str | |
| `coculture_partner` | str \| null | Coculture partner organism, if applicable |
| `is_time_course` | str | `"true"` / `"false"` — from Experiment node |
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

### Input validation (raises ValueError)

Enforced in api/ before any KG queries run.

**Require at least one filter:**

| Case | Error message |
|---|---|
| All three None | `"at least one of organism, locus_tags, or experiment_ids is required"` |

**Single-organism enforcement** — lightweight pre-queries resolve
`DISTINCT organism_strain` for each input set:

| Case | Error message |
|---|---|
| `organism` fuzzy match resolves to 0 organisms | `"no organism matching 'xyz' found"` |
| `organism` fuzzy match resolves to >1 organisms | `"organism 'pro' matches multiple organisms: MED4, MIT9313, ... — be more specific"` |
| `locus_tags` from multiple organisms | `"locus_tags span multiple organisms: MED4, MIT9313 — call once per organism"` |
| `experiment_ids` from multiple organisms | `"experiment_ids span multiple organisms: MED4, HOT1A3 — call once per organism"` |
| `locus_tags` organism ≠ `experiment_ids` organism | `"locus_tags are MED4 genes but experiment_ids cover HOT1A3 — organisms must match"` |
| `organism` ≠ inferred organism from locus_tags/experiment_ids | `"organism 'MED4' does not match locus_tags organism 'MIT9313'"` |

Pre-query resolves `DISTINCT g.organism_strain` for locus_tags and
`DISTINCT e.organism_strain` for experiment_ids. For `organism` alone,
the fuzzy match is applied in the WHERE clause and the resulting
`DISTINCT e.organism_strain` is checked. Cheap (index lookups).
`organism_strain` in the response is set from the validated single value.

---

## Result-size controls

| Scenario | Recommended call |
|---|---|
| Quick overview (what's available?) | `summary=True` — no rows, just counts |
| Organism-wide landscape | `organism="MED4"`, `summary=True` |
| Organism top responders | `organism="MED4"`, `significant_only=True`, `limit=20` |
| Strongest responders in an experiment | `experiment_ids=[...]`, `significant_only=True`, `limit=20` |
| Full profile for 1–3 genes | `locus_tags=[...]`, `limit=None` in api/ (all rows); set large limit in MCP |
| Batch annotation of gene list | `significant_only=True`, `summary=True` first |

`limit=None` in api/ returns all matching rows. MCP `limit` has `ge=1` — use a
large value (e.g. 200) when you need many rows via MCP.

**Default limit:** 5 (MCP), None (api/).

---

## Special handling

### Multi-query pattern

All summary queries always run. Detail query skipped when `limit=0` / `summary=True`.
All queries share the same WHERE clause (same filter parameters).

**Summary query 1 — global stats:**
Returns `total_rows`, `matching_genes`, `rows_by_status`, `median_abs_log2fc`, `max_abs_log2fc`.

`rows_by_status` uses `apoc.coll.frequencies(collect(r.expression_status))` —
single aggregation over the precomputed enum; always all three keys present.

Uses `percentileCont(CASE WHEN r.expression_status <> "not_significant" THEN abs(r.log2_fold_change) ELSE null END, 0.5)` — nulls from CASE are silently ignored by `percentileCont`, confirmed against live KG.

**Summary query 2 — per-experiment with nested timepoints:**
Returns `organism_strain` and `experiments` list. Each experiment entry
contains a nested `timepoints` list (or null for non-time-course, handled in api/).
`matching_genes` (global) comes from query 1; `experiment_count = len(experiments)`
computed in api/. Single-timepoint experiments return `timepoints` with one entry
(not empty — consistent structure).

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

### Common mistakes

**1. Treating truncated results as complete.**
The `limit` controls total result rows (gene × experiment × timepoint). When `truncated=true`,
the result set is a partial slice sorted by `|log2FC| DESC` — it may contain only a subset of
timepoints for a gene, only some experiments, or only the strongest-responding genes. Do not
interpret the absence of a row as "no change" when the output is truncated. Always check
`truncated` before drawing conclusions about presence/absence. Use `summary=True` for reliable
counts, or increase `limit` to get the full picture.

**2. Assuming `no_expression` means "not differentially expressed".**
A gene in `no_expression` has zero `Changes_expression_of` edges matching the active filters.
This does **not** mean the gene was measured and found unchanged. Possible reasons:

- **Publication-level filtering:** Some publications report all genes assayed (full genome),
  others report only a subset (e.g. top 50 by effect size, or only significant hits). A gene
  absent from a subset-reporting publication was likely measured but filtered out by the
  authors before data was deposited — it may or may not be differentially expressed.
- **Not sequenced:** The gene's organism was not included in the experiment.
- **Filter mismatch:** The gene has expression data, but not in the experiments matching
  the current `experiment_ids` / `organism` filters.

The KG build pipeline tracks publication reporting scope (full vs filtered), but this
metadata is not yet exposed through the expression tool. For now, treat `no_expression`
as "no data available" rather than "no change observed".

---

## Query Builders

**File:** `kg/queries_lib.py`

Three summary builders + one detail builder, all sharing the same WHERE clause
helper. The api/ layer calls all three summary builders and merges results.

### `_differential_expression_where` (private helper)

```python
def _differential_expression_where(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[list[str], dict]:
    """Build WHERE conditions + params shared by all de_by_gene builders.

    direction takes precedence over significant_only (direction implies significance).
    organism uses fuzzy word-based matching (same as list_experiments).
    """
    conditions: list[str] = []
    params: dict = {}
    if organism:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(e.organism_strain) CONTAINS word)"
        )
        params["organism"] = organism
    if locus_tags:
        conditions.append("g.locus_tag IN $locus_tags")
        params["locus_tags"] = locus_tags
    if experiment_ids:
        conditions.append("e.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids
    if direction == "up":
        conditions.append('r.expression_status = "significant_up"')
    elif direction == "down":
        conditions.append('r.expression_status = "significant_down"')
    elif significant_only:
        conditions.append('r.expression_status <> "not_significant"')
    return conditions, params
```

All four builders call this helper. The `where_block` is constructed as:
```python
where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""
```

### Pre-query: organism validation

Three lightweight builders used by api/ before any summary queries run.
Not added to `TOOL_BUILDERS` in regression tests (not tools themselves).

```python
def build_resolve_organism_for_organism(
    *, organism: str,
) -> tuple[str, dict]:
    """Resolve distinct organism_strain values for a fuzzy organism name.

    RETURN keys: organisms (list[str]).
    Uses the same word-based CONTAINS matching as list_experiments.
    Used for single-organism pre-validation in differential_expression_by_gene.
    """
```

```cypher
MATCH (e:Experiment)-[:Changes_expression_of]->()
WHERE ALL(word IN split(toLower($organism), ' ')
      WHERE toLower(e.organism_strain) CONTAINS word)
RETURN collect(DISTINCT e.organism_strain) AS organisms
```

```python
def build_resolve_organism_for_locus_tags(
    *, locus_tags: list[str],
) -> tuple[str, dict]:
    """Resolve distinct organism_strain values for a list of locus_tags.

    RETURN keys: organisms (list[str]).
    Used for single-organism pre-validation in differential_expression_by_gene.
    """
```

```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})
RETURN collect(DISTINCT g.organism_strain) AS organisms
```

```python
def build_resolve_organism_for_experiments(
    *, experiment_ids: list[str],
) -> tuple[str, dict]:
    """Resolve distinct organism_strain values for a list of experiment IDs.

    RETURN keys: organisms (list[str]).
    Used for single-organism pre-validation in differential_expression_by_gene.
    """
```

```cypher
UNWIND $experiment_ids AS eid
MATCH (e:Experiment {id: eid})
RETURN collect(DISTINCT e.organism_strain) AS organisms
```

api/ calls one, two, or all three depending on which inputs are provided.
Checks `len(organisms) > 1` → ValueError, then checks cross-set consistency
if multiple inputs are provided.

### `build_differential_expression_by_gene_summary_global`

```python
def build_differential_expression_by_gene_summary_global(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[str, dict]:
    """Global aggregate stats for differential_expression_by_gene.

    RETURN keys: total_rows, matching_genes, rows_by_status,
    rows_by_treatment_type, median_abs_log2fc, max_abs_log2fc.
    rows_by_status = apoc list [{item, count}] — api/ converts to dict.
    rows_by_treatment_type = apoc list [{item, count}] — api/ converts to dict.
    """
```

```cypher
MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)
{where_block}
RETURN count(*) AS total_rows,
       count(DISTINCT g.locus_tag) AS matching_genes,
       apoc.coll.frequencies(collect(r.expression_status)) AS rows_by_status,
       apoc.coll.frequencies(collect(e.treatment_type)) AS rows_by_treatment_type,
       percentileCont(
           CASE WHEN r.expression_status <> "not_significant"
                THEN abs(r.log2_fold_change) ELSE null END, 0.5
       ) AS median_abs_log2fc,
       max(CASE WHEN r.expression_status <> "not_significant"
               THEN abs(r.log2_fold_change) END) AS max_abs_log2fc
```

- `count(*)` not `count(r.time_point)` — field-level count drops NULLs, would undercount.
- `percentileCont(CASE ... ELSE null, 0.5)` — nulls silently ignored, confirmed on live KG.
- `max(CASE ...)` — returns null when no significant rows; correct for `float | None`.
- `rows_by_status` only includes non-zero keys from APOC — api/ fills missing keys with 0.

### `build_differential_expression_by_gene_summary_by_experiment`

```python
def build_differential_expression_by_gene_summary_by_experiment(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[str, dict]:
    """Per-experiment breakdown with nested timepoints (single organism enforced).

    RETURN keys: organism_strain, experiments.
    experiments: list of dicts, each with nested timepoints.
    rows_by_status at both experiment and timepoint level (APOC list format).
    is_time_course included per experiment so api/ can null-out timepoints.
    matching_genes (global) and experiment_count come from api/ post-processing:
      matching_genes = from global summary query
      experiment_count = len(experiments)
    """
```

Full Cypher — verified against live KG:

```cypher
MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)
{where_block}
// Pass 1: group by (experiment × timepoint) — g must NOT be in this WITH
// (including g gives groups of (g,e,tp), 3×5=15 entries instead of 5)
WITH e, r.time_point AS tp, r.time_point_order AS tpo, r.time_point_hours AS tph,
     collect(DISTINCT g.locus_tag) AS tp_genes,
     collect(r.expression_status) AS tp_calls

// Pass 2: roll up to experiment level
// rows_by_status: flatten all per-timepoint call lists then compute frequencies
WITH e,
     size(apoc.coll.toSet(apoc.coll.flatten(collect(tp_genes)))) AS matching_genes,
     apoc.coll.frequencies(apoc.coll.flatten(collect(tp_calls))) AS rows_by_status,
     collect({timepoint: tp, timepoint_hours: tph, timepoint_order: tpo,
              matching_genes: size(tp_genes),
              rows_by_status: apoc.coll.frequencies(tp_calls)}) AS timepoints

// Pass 3: collect experiments — organism already validated as single value
WITH collect({experiment_id: e.id, experiment_name: e.name,
              treatment_type: e.treatment_type, omics_type: e.omics_type,
              coculture_partner: e.coculture_partner,
              is_time_course: e.is_time_course,
              matching_genes: matching_genes,
              rows_by_status: rows_by_status,
              timepoints: timepoints}) AS experiments,
     e.organism_strain AS organism_strain
RETURN organism_strain, experiments
```

**Null handling (verified against live KG):**
- `collect()` on a scalar **silently drops NULLs** — do NOT use
  `collect(r.time_point)` directly. Use GROUP BY so each NULL
  timepoint forms its own group row, then collect the map.
- `collect({timepoint: tp, ...})` with `tp = null` **preserves the
  null** inside the map — safe for nested structures.
- `r.expression_status` is never null — `collect(r.expression_status)` is safe.
- `apoc.coll.toSet(apoc.coll.flatten(collect(tp_genes)))` — correctly
  deduplicates genes across timepoints. Do NOT use `sum(size(tp_genes))`.

Returns `is_time_course` per experiment so api/ can set `timepoints=null`
for non-time-course experiments (matching `list_experiments` pattern).

### `build_differential_expression_by_gene_summary_diagnostics`

```python
def build_differential_expression_by_gene_summary_diagnostics(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
) -> tuple[str, dict]:
    """Top categories + batch diagnostics for differential_expression_by_gene.

    RETURN keys: top_categories, not_found, no_expression.
    not_found and no_expression are empty lists when locus_tags is None.
    Constructs different Cypher depending on whether locus_tags is provided.
    """
```

**When `locus_tags` is None** — simple MATCH, no batch diagnostics:

```cypher
MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)
{where_block}
WITH g.gene_category AS category,
     count(DISTINCT g.locus_tag) AS total_genes,
     count(DISTINCT CASE WHEN r.expression_status <> "not_significant"
                         THEN g.locus_tag END) AS significant_genes
ORDER BY significant_genes DESC
RETURN [] AS not_found, [] AS no_expression,
       collect({category: category, total_genes: total_genes,
                significant_genes: significant_genes})[0..5] AS top_categories
```

**When `locus_tags` is provided** — UNWIND for batch diagnostics; verified on live KG:

```cypher
// Pass 1: classify each input locus_tag
// where_block_no_lt = same conditions but WITHOUT the g.locus_tag IN $locus_tags condition
UNWIND $locus_tags AS lt
OPTIONAL MATCH (g:Gene {locus_tag: lt})
OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g)
{where_block_no_lt}
WITH lt, g, count(r) AS edge_count

WITH collect(CASE WHEN g IS NULL           THEN lt END) AS not_found_raw,
     collect(CASE WHEN g IS NOT NULL AND edge_count = 0 THEN lt END) AS no_expr_raw,
     collect(CASE WHEN g IS NOT NULL AND edge_count > 0 THEN g  END) AS matched_genes

// Pass 2: top_categories over matched genes only
UNWIND CASE WHEN size(matched_genes) > 0 THEN matched_genes ELSE [null] END AS g
OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g)
{where_block_no_lt}
WITH [x IN not_found_raw WHERE x IS NOT NULL] AS not_found,
     [x IN no_expr_raw  WHERE x IS NOT NULL] AS no_expression,
     g.gene_category AS category,
     count(DISTINCT g.locus_tag) AS total_genes,
     count(DISTINCT CASE WHEN r.expression_status <> "not_significant"
                         THEN g.locus_tag END) AS significant_genes
ORDER BY significant_genes DESC
RETURN not_found, no_expression,
       collect({category: category, total_genes: total_genes,
                significant_genes: significant_genes})[0..5] AS top_categories
```

`where_block_no_lt` = same `_differential_expression_where()` conditions but
with `locus_tags=None` (organism + experiment_ids + direction + significant_only).
The locus_tag filter is already applied via `UNWIND + OPTIONAL MATCH`.

`collect(CASE WHEN g IS NULL THEN lt END)` — collect() drops NULLs, so
this collects only the locus_tags where g was not found. The `WHERE x IS NOT NULL`
in `[x IN ... WHERE x IS NOT NULL]` is defensive (belt-and-suspenders).

`UNWIND CASE WHEN size(matched_genes) > 0 THEN matched_genes ELSE [null]` —
when matched_genes is empty, UNWIND [null] gives g=null; OPTIONAL MATCH on
null g produces no results; WITH aggregates over zero rows → empty collect().
This is the established pattern (see `build_gene_homologs_summary`).

### `build_differential_expression_by_gene`

```python
def build_differential_expression_by_gene(
    *,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    direction: str | None = None,
    significant_only: bool = False,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for differential_expression_by_gene.

    RETURN keys (compact — 11): locus_tag, gene_name,
    experiment_id, treatment_type, timepoint, timepoint_hours, timepoint_order,
    log2fc, padj, rank, expression_status.
    RETURN keys (verbose): adds product, experiment_name, treatment,
    gene_category, omics_type, coculture_partner.
    """
```

Property mappings:
- `g.locus_tag` → `locus_tag`
- `g.gene_name` → `gene_name` (nullable)
- `g.function_description` → `product` (verbose)
- `e.id` → `experiment_id`
- `e.name` → `experiment_name` (verbose)
- `e.treatment_type` → `treatment_type`
- `e.treatment` → `treatment` (verbose)
- `e.omics_type` → `omics_type` (verbose)
- `e.coculture_partner` → `coculture_partner` (verbose)
- `r.log2_fold_change` → `log2fc`
- `r.adjusted_p_value` → `padj`
- `r.rank_by_effect` → `rank`
- `r.expression_status` → `expression_status`
- `r.time_point` → `timepoint`
- `r.time_point_hours` → `timepoint_hours`
- `r.time_point_order` → `timepoint_order`

**Note:** `organism_strain` is NOT returned per row — it's in the top-level
envelope (single organism enforced). Avoids repeating it across all rows.

LIMIT: `LIMIT $limit` with `params["limit"] = limit` when `limit is not None`.

```cypher
MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)
{where_block}
RETURN g.locus_tag AS locus_tag,
       g.gene_name AS gene_name,
       e.id AS experiment_id,
       e.treatment_type AS treatment_type,
       r.time_point AS timepoint,
       r.time_point_hours AS timepoint_hours,
       r.time_point_order AS timepoint_order,
       r.log2_fold_change AS log2fc,
       r.adjusted_p_value AS padj,
       r.rank_by_effect AS rank,
       r.expression_status AS expression_status
       {verbose_cols}
ORDER BY ABS(r.log2_fold_change) DESC, g.locus_tag ASC, e.id ASC, r.time_point_order ASC
{limit_clause}
```

### Cypher review notes and sticky points

Review of query builders (this spec) and `post-import.cypher` (KG build repo).
Findings verified against live KG (2026-03-25).

#### KG invariants (verified)

These hold for all 188,501 edges. Queries that depend on them should have
integration tests that assert them, so a KG rebuild that breaks an invariant
is caught immediately.

| Invariant | Verified | Depends on |
|---|---|---|
| `g.organism_strain == e.organism_strain` for every `Changes_expression_of` edge | 0 mismatches | KG build pipeline — edges only connect experiments to genes of the same organism |
| `r.expression_status` is never null | all 188,501 edges have a value | `post-import.cypher` CASE expression covers all combinations |
| Coculture experiments: edges only point to the experiment's own organism, never the partner | confirmed — `gene_orgs` always single-element | KG build — DE analysis is per-organism even in coculture |
| Non-time-course experiments have at most 1 distinct `r.time_point` per experiment | 0 experiments with >1 | KG build — single-TP experiments get one time_point label (or null) |
| 2 HOT1A3 experiments have `gene_count = 0` (no expression edges) | `10.1038/ismej.2016.70_coculture_prochlorococcus_mit9313_high_...` and `..._mit9313_hot1a3_...` | KG build — Alteromonas-side DE not computed for these coculture experiments |

**Test guideline:** Add an integration test class `TestExpressionKGInvariants` that
asserts each invariant with a Cypher query. Run with `pytest -m kg`. If any fails
after a KG rebuild, the expression tool's assumptions are broken.

```python
# Example invariant tests (integration, requires live KG)
def test_organism_match_on_all_edges(conn):
    """g.organism_strain must equal e.organism_strain for every expression edge."""
    result = conn.execute(
        "MATCH (e:Experiment)-[:Changes_expression_of]->(g:Gene) "
        "WHERE e.organism_strain <> g.organism_strain RETURN count(*) AS n"
    )
    assert result[0]["n"] == 0

def test_expression_status_never_null(conn):
    """expression_status must be set on every edge (post-import.cypher)."""
    result = conn.execute(
        "MATCH ()-[r:Changes_expression_of]->() "
        "WHERE r.expression_status IS NULL RETURN count(*) AS n"
    )
    assert result[0]["n"] == 0

def test_non_tc_single_timepoint(conn):
    """Non-time-course experiments must have at most 1 distinct timepoint."""
    result = conn.execute(
        "MATCH (e:Experiment)-[r:Changes_expression_of]->() "
        "WHERE e.is_time_course = 'false' "
        "WITH e.id AS eid, collect(DISTINCT r.time_point) AS tps "
        "WHERE size(tps) > 1 RETURN count(*) AS n"
    )
    assert result[0]["n"] == 0
```

#### `post-import.cypher` — `rank_by_effect`

```cypher
MATCH (e)-[r:Changes_expression_of]->(g:Gene)
WITH r.time_point_order AS tp, r, abs(r.log2_fold_change) AS abs_fc
ORDER BY tp, abs_fc DESC
WITH tp, collect(r) AS edges
UNWIND range(0, size(edges)-1) AS i
SET (edges[i]).rank_by_effect = i + 1
```

**Tied |log2FC| values get arbitrary rank ordering** — no tiebreaker beyond
`abs_fc DESC`. For two genes with identical |log2FC|, their relative rank is
non-deterministic across KG rebuilds. This is acceptable for the ranking use
case but means rank-based assertions in tests must allow for ties.

**Potential improvement:** add `g.locus_tag ASC` as tiebreaker for deterministic
ranks across rebuilds:
```cypher
ORDER BY tp, abs_fc DESC, g.locus_tag ASC
```

**Test guideline:** Integration tests that assert specific `rank` values should
either (a) pick genes with unique |log2FC| in their experiment×timepoint, or
(b) assert rank is within the expected tied range rather than an exact value.

#### `summary_by_experiment` — GROUP BY fragility

The final WITH:
```cypher
WITH collect({...}) AS experiments,
     e.organism_strain AS organism_strain
```
uses `e.organism_strain` as an implicit GROUP BY key. With single-organism
enforcement, this produces exactly one row. If pre-validation ever fails to
run (bug in api/), this would silently split experiments into per-organism
groups and only return the last one.

**Test guideline:** Integration test should call with known multi-organism inputs
(bypassing api/ validation) at the query-builder level and verify the query
returns multiple `organism_strain` groups — confirming the grouping behavior
is understood, not that it's "safe".

```python
# Unit test: builder produces valid Cypher for multi-organism case
def test_by_experiment_groups_by_organism(conn):
    """Without api/ validation, query groups by organism_strain."""
    cypher, params = build_differential_expression_by_gene_summary_by_experiment(
        organism=None, locus_tags=None, experiment_ids=None,
    )
    # Run against KG — should return multiple rows (one per organism)
    results = conn.execute(cypher, params)
    orgs = [r["organism_strain"] for r in results]
    assert len(orgs) > 1, "expected multiple organism groups without filters"
```

#### `summary_diagnostics` — `no_expression` respects active filters

When `locus_tags` + `experiment_ids` are both provided, `no_expression` means
"gene exists but has no expression in *those specific experiments*" (not globally).
This is because `where_block_no_lt` includes the `experiment_ids` condition.

A gene could have expression data globally but appear in `no_expression` when
filtered to experiments it wasn't profiled in. This is correct behavior.

**Test guideline:** Test with a gene that has expression in experiment A but not
experiment B. Call with `locus_tags=[gene]`, `experiment_ids=[B]` → gene should
appear in `no_expression`. Call with `experiment_ids=[A]` → gene should NOT be
in `no_expression`.

```python
# Integration test: no_expression is filter-aware
def test_no_expression_respects_experiment_filter(conn):
    """Gene with expression in exp A but not exp B → no_expression when filtered to B."""
    # PMM0001 has expression in MED4 experiments but not in MIT9313 experiments
    # Pick a MED4 gene and a non-MED4 experiment
    cypher_a, params_a = build_differential_expression_by_gene_summary_diagnostics(
        locus_tags=["PMM0001"],
        experiment_ids=["<med4_experiment_id>"],  # experiment where PMM0001 IS profiled
    )
    result_a = conn.execute(cypher_a, params_a)
    assert "PMM0001" not in result_a[0]["no_expression"]

    # Now filter to an experiment where PMM0001 is NOT profiled
    # (would need a real experiment ID from a different organism — but single-organism
    # validation would block this in api/. Test at builder level only.)
```

#### `summary_global` — `percentileCont` with all-null input

When `significant_only=True` and no matching significant rows exist (e.g. an
experiment where everything is non-significant), the CASE expression produces
all nulls → `percentileCont` receives an empty set → returns null. This is the
correct behavior (`median_abs_log2fc: null`).

Similarly, `max(CASE ...)` returns null with no significant rows.

**Test guideline:** Test with `significant_only=True` on an experiment/gene
combination with zero significant rows → verify `median_abs_log2fc` and
`max_abs_log2fc` are both null (not 0, not error).

#### `summary_diagnostics` — `count(*)` with OPTIONAL MATCH returning no edges

When a gene exists but has no expression edges (or none matching filters),
`OPTIONAL MATCH (e:Experiment)-[r:Changes_expression_of]->(g)` produces
`e=null, r=null`. Then `count(*)` returns 1 (counts the null row), not 0.
This means `edge_count = 1` for a gene with no edges, which would
misclassify it as having expression.

**This is a bug in the spec.** Fix: use `count(r)` instead of `count(*)`.
`count(r)` returns 0 when `r IS NULL` (OPTIONAL MATCH found nothing).

```cypher
// WRONG:
WITH lt, g, count(*) AS edge_count  -- returns 1 even when r is null

// CORRECT:
WITH lt, g, count(r) AS edge_count  -- returns 0 when no edges match
```

**Test guideline:** Test with a gene that exists in the KG but has zero
expression edges. Verify it appears in `no_expression`, not in
`matched_genes`.

```python
# Integration test: gene with no expression edges
def test_gene_with_no_expression_classified_correctly(conn):
    """Gene in KG but with no expression data → no_expression, not matched."""
    # MIT1002_02071 has expression_edge_count = 0 (verified on live KG)
    cypher, params = build_differential_expression_by_gene_summary_diagnostics(
        organism="MIT1002",
        locus_tags=["MIT1002_02071"],
    )
    result = conn.execute(cypher, params)
    assert "MIT1002_02071" in result[0]["no_expression"]
    # top_categories should be empty (no matched genes)
    cats = result[0]["top_categories"]
    assert all(c["total_genes"] == 0 for c in cats) or len(cats) == 0
```

#### `_differential_expression_where` — organism fuzzy match on `e.organism_strain`

The organism filter uses `e.organism_strain` (not `g.organism_strain`). Since
`g.organism_strain == e.organism_strain` for all edges (invariant above), this
is equivalent. However, the choice of `e.organism_strain` is deliberate: the
MATCH pattern is `(e:Experiment)-[r]->(g:Gene)`, and filtering on `e` allows
Neo4j to use the `experiment_organism_idx` index for the initial node scan.

**Test guideline:** Verify the organism fuzzy match resolves correctly:
- `"MED4"` → matches `Prochlorococcus MED4` only
- `"Alteromonas"` → matches all 3 Alteromonas strains (pre-validation rejects as multi-organism)
- `"Prochlorococcus MED4"` → exact match (all words match)
- `"ZZZZZ"` → no match

---

## API Function

**File:** `api/functions.py`

```python
def differential_expression_by_gene(
    organism: str | None = None,
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
        ValueError: if no filter provided (organism/locus_tags/experiment_ids
            all None), if inputs span multiple organisms, if organisms don't
            match each other, or if organism fuzzy match is ambiguous.

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
- Validate at least one of `{organism, locus_tags, experiment_ids}` is provided
- **Pre-query organism validation** (before any summary queries):
  - If `organism` provided: resolve via fuzzy match against `DISTINCT e.organism_strain`
    (same word-based CONTAINS as list_experiments). Raise if 0 or >1 matches.
  - Resolve `DISTINCT g.organism_strain` for `locus_tags` (if provided)
  - Resolve `DISTINCT e.organism_strain` for `experiment_ids` (if provided)
  - Raise `ValueError` if any set has >1 organism, or if sets are disjoint
  - When `organism` is combined with locus_tags/experiment_ids, validate they agree
  - Set `organism_strain` in response from the validated single value
- Always run summary queries → all summary fields
- Skip detail when `limit=0`
- Rename KG properties to output field names (`log2_fold_change` → `log2fc`, etc.)
- Convert APOC `apoc.coll.frequencies` result `[{item, count}]` → `{item: count}` dict for `rows_by_status`; fill missing keys (`significant_up`, `significant_down`, `not_significant`) with 0
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
    treatment_type: str = Field(description="Treatment category (e.g. 'nitrogen_stress', 'coculture')")
    omics_type: str = Field(description="Omics type (e.g. 'RNASEQ', 'PROTEOMICS')")
    coculture_partner: str | None = Field(default=None, description="Coculture partner organism, if applicable")
    is_time_course: str = Field(description="'true' or 'false'")
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
    treatment_type: str = Field(description="Treatment type from experiment (e.g. 'nitrogen_stress')")
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
    rows_by_treatment_type: dict[str, int] = Field(description="Row counts by treatment type (e.g. {'nitrogen_stress': 15})")
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
| 5 | Pre-query | `kg/queries_lib.py` | `build_resolve_organism_for_organism()` + `build_resolve_organism_for_locus_tags()` + `build_resolve_organism_for_experiments()` (lightweight organism validation queries) |
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
  "rows_by_treatment_type": {"nutrient_starvation": 15},
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
      "treatment_type": "nutrient_starvation",
      "omics_type": "RNASEQ",
      "coculture_partner": null,
      "is_time_course": "true",
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
    {"locus_tag": "ACZ81_01830", "gene_name": "amtB", "experiment_id": "...", "treatment_type": "nutrient_starvation",
     "timepoint": "days 60+89", "timepoint_hours": null,  "timepoint_order": 3,
     "log2fc":  3.591, "padj": 1.13e-12, "rank":  77,  "expression_status": "significant_up"},
    {"locus_tag": "ACZ81_15555", "gene_name": "glnL", "experiment_id": "...", "treatment_type": "nutrient_starvation",
     "timepoint": "days 60+89", "timepoint_hours": null,  "timepoint_order": 3,
     "log2fc":  1.978, "padj": 2.31e-6,  "rank": 410,  "expression_status": "significant_up"},
    {"locus_tag": "ACZ81_15560", "gene_name": "glnG", "experiment_id": "...", "treatment_type": "nutrient_starvation",
     "timepoint": "days 60+89", "timepoint_hours": null,  "timepoint_order": 3,
     "log2fc":  1.745, "padj": 2.11e-5,  "rank": 544,  "expression_status": "significant_up"},
    {"locus_tag": "ACZ81_01830", "gene_name": "amtB", "experiment_id": "...", "treatment_type": "nutrient_starvation",
     "timepoint": "day 18",     "timepoint_hours": 432.0, "timepoint_order": 1,
     "log2fc":  0.856, "padj": 0.259,    "rank": 1104, "expression_status": "not_significant"},
    {"locus_tag": "ACZ81_01830", "gene_name": "amtB", "experiment_id": "...", "treatment_type": "nutrient_starvation",
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
| Pre-query builders | `test_query_builders.py` | `TestBuildResolveOrganismForOrganism`, `TestBuildResolveOrganismForLocusTags`, `TestBuildResolveOrganismForExperiments` |
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

- `organism` only → all expression for that organism
- `organism` only, `summary=True` → summary without rows
- `organism` only, `significant_only=True`, `limit=20` → top responders
- `organism` fuzzy match ("MED4") → resolves to full name
- `organism` ambiguous ("Prochlorococcus") → ValueError (matches multiple)
- `organism` no match ("ZZZZZ") → ValueError
- `organism` + `locus_tags` match → organism validates, same as locus_tags alone
- `organism` + `locus_tags` mismatch → ValueError
- No filters (all three None) → ValueError
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
when `total_rows == returned` (no truncation).

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

---

## Resolved: Cross-tool output consistency

**Decision: Align now.** Refactor `list_experiments` and `gene_overview` to use the
same output patterns as `differential_expression_by_gene` before shipping. Pre-release,
no external consumers — only cost is test/fixture updates.

**Unified patterns adopted across all three tools:**
- **`rows_by_status` dict** instead of separate `significant_up_count` / `significant_down_count` fields
- **Nested timepoint objects** instead of parallel arrays
- **`gene_count`** remains as-is in `list_experiments` (precomputed, different semantics from
  `matching_genes` in the expression tool — not a consistency issue)

### Side-by-side output examples

Scenario: HOT1A3 nitrogen starvation experiment with 3 timepoints (day 18, day 31, days 60+89),
queried for 5 nitrogen-related genes (amtB, glnD, glnL, glnG, glnE).

#### `list_experiments` — experiment discovery (one result row per experiment)

```json
{
  "total_matching": 1,
  "results": [
    {
      "experiment_id": "10.1101/2025.11.24.690089_..._axenic",
      "publication_doi": "10.1101/2025.11.24.690089",
      "organism_strain": "Alteromonas macleodii HOT1A3",
      "treatment_type": "nutrient_starvation",
      "omics_type": "RNASEQ",
      "is_time_course": "true",
      "gene_count": 2814,
      "rows_by_status": {"significant_up": 412, "significant_down": 389, "not_significant": 7630},
      "timepoints": [
        {"timepoint": "day 18",     "timepoint_order": 1, "timepoint_hours": 432.0,
         "gene_count": 2814, "rows_by_status": {"significant_up": 98,  "significant_down": 112, "not_significant": 2604}},
        {"timepoint": "day 31",     "timepoint_order": 2, "timepoint_hours": 744.0,
         "gene_count": 2814, "rows_by_status": {"significant_up": 134, "significant_down": 156, "not_significant": 2524}},
        {"timepoint": "days 60+89", "timepoint_order": 3, "timepoint_hours": null,
         "gene_count": 2814, "rows_by_status": {"significant_up": 180, "significant_down": 121, "not_significant": 2513}}
      ]
    }
  ]
}
```

#### `gene_overview` — gene routing (one result row per gene, expression as availability signal)

```json
{
  "total_matching": 5,
  "results": [
    {
      "locus_tag": "ACZ81_01830",
      "gene_name": "amtB",
      "product": "ammonium transporter",
      "gene_category": "Inorganic ion transport",
      "organism_strain": "Alteromonas macleodii HOT1A3",
      "expression_edge_count": 3,
      "rows_by_status": {"significant_up": 1, "significant_down": 0, "not_significant": 2}
    },
    {
      "locus_tag": "ACZ81_15555",
      "gene_name": "glnL",
      "product": "nitrogen regulation protein NR(II)",
      "gene_category": "Signal transduction",
      "organism_strain": "Alteromonas macleodii HOT1A3",
      "expression_edge_count": 3,
      "rows_by_status": {"significant_up": 1, "significant_down": 0, "not_significant": 2}
    }
  ]
}
```

#### `differential_expression_by_gene` — expression analysis (one result row per gene x timepoint)

```json
{
  "organism_strain": "Alteromonas macleodii HOT1A3",
  "matching_genes": 5,
  "total_rows": 15,
  "rows_by_status": {"significant_up": 3, "significant_down": 0, "not_significant": 12},
  "rows_by_treatment_type": {"nutrient_starvation": 15},
  "experiments": [
    {
      "experiment_id": "10.1101/2025.11.24.690089_..._axenic",
      "experiment_name": "HOT1A3 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "treatment_type": "nutrient_starvation",
      "omics_type": "RNASEQ",
      "coculture_partner": null,
      "is_time_course": "true",
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
  "results": [
    {"locus_tag": "ACZ81_01830", "gene_name": "amtB", "experiment_id": "...", "treatment_type": "nutrient_starvation",
     "timepoint": "days 60+89", "log2fc": 3.591, "padj": 1.13e-12, "rank": 77, "expression_status": "significant_up"},
    {"locus_tag": "ACZ81_15555", "gene_name": "glnL", "experiment_id": "...", "treatment_type": "nutrient_starvation",
     "timepoint": "days 60+89", "log2fc": 1.978, "padj": 2.31e-6,  "rank": 410, "expression_status": "significant_up"}
  ]
}
```

#### Comparison: same data, different zoom level

| Aspect | `list_experiments` | `gene_overview` | `differential_expression_by_gene` |
|---|---|---|---|
| **Question answered** | "What experiments exist?" | "What data is available for these genes?" | "How do these genes respond?" |
| **Row granularity** | 1 row per experiment | 1 row per gene | 1 row per gene x timepoint |
| **Gene counts** | `gene_count` (all genes in experiment) | `expression_edge_count` (edges per gene) | `matching_genes` (genes matching filters) |
| **Significance** | `rows_by_status` dict | `rows_by_status` dict | `rows_by_status` dict |
| **Treatment type** | On each result row | N/A | On each result row + `rows_by_treatment_type` summary |
| **Coculture partner** | On each result row | N/A | In experiment summary; on rows in verbose |
| **Timepoints** | Nested `timepoints[]` objects | Not shown (wrong zoom level) | Nested `timepoints[]` objects |
| **Expression values** | Not shown (wrong zoom level) | Not shown (availability only) | `log2fc`, `padj`, `rank`, `expression_status` |

### Refactoring scope for alignment

**`list_experiments`** (changes from current):
- `significant_up_count` + `significant_down_count` → `rows_by_status: {significant_up, significant_down, not_significant}` (experiment level)
- Parallel arrays → nested `timepoints[]` objects with unified field names:
  - `time_point_labels[i]` → `timepoints[i].timepoint`
  - `time_point_orders[i]` → `timepoints[i].timepoint_order`
  - `time_point_hours[i]` → `timepoints[i].timepoint_hours`
  - `time_point_totals[i]` → `timepoints[i].gene_count`
  - `time_point_significant_up[i]` + `time_point_significant_down[i]` → `timepoints[i].rows_by_status`
- `time_point_count` → dropped (redundant: `len(timepoints)`)
- Naming: `timepoints` (no underscore) — matches expression tool

**`gene_overview`** (changes from current):
- `significant_up_count` + `significant_down_count` → `rows_by_status: {significant_up, significant_down, not_significant}`
- Keep `expression_edge_count` (total edges, useful as availability signal)
- `not_significant` count derived: `expression_edge_count - significant_up - significant_down` (precomputed on Gene node)

**Note:** `is_time_course` stays as string `"true"/"false"` across all tools (KG stores it that way).
Converting to proper bool is a possible future improvement but not part of this alignment.

## Open Questions

### Experiment reporting scope (`reporting_scope` on Experiment node)

Some publications report all genes assayed (full genome), others report only a subset
(top N, significant-only, or other author-defined filter). This is tracked per-experiment
in the KG build pipeline but not yet exposed on the Experiment node.

Adding a `reporting_scope` property (e.g. `"full"` / `"filtered"`) to the Experiment node
would let the expression tool disambiguate `no_expression`: "not measured / filtered out by
authors" vs "measured and not differentially expressed". Currently `no_expression` conflates
these — see Common mistakes §2.

**Depends on:** KG schema change + rebuild. Design the enum values when ready to implement.
