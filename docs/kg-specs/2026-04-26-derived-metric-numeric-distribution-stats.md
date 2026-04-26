# KG change spec: precompute per-DerivedMetric numeric value distribution

**Date:** 2026-04-26
**Driver:** [docs/tool-specs/genes_by_numeric_metric.md](../tool-specs/genes_by_numeric_metric.md) (slice-1, tool 3 of 5) — supplies full-DM distribution context as a precomputed DM-node property.
**Slice spec:** [docs/superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md](../superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md)
**Companion spec:** [docs/kg-specs/2026-04-26-unify-derived-metric-edge-value.md](2026-04-26-unify-derived-metric-edge-value.md) (already landed; this spec layers on top)

## Summary

Add five precomputed numeric-distribution properties to every `DerivedMetric` node where `value_kind='numeric'`: `value_min`, `value_max`, `value_median`, `value_q1`, `value_q3` (all `float`). Computed once at post-import rollup time over the parent DM's `Derived_metric_quantifies_gene.value` edges, alongside the existing `total_gene_count` rollup. Boolean and categorical DMs are explicitly out of scope for slice 1 (their per-DM distribution stats — flag/category counts — would parallel this design and slot in alongside slices 4–5 when those tools are written).

The new props let `list_derived_metrics` (already shipped, verbose mode) and `genes_by_numeric_metric.by_metric` (this slice) carry full-DM distribution context as cheap node-property reads, instead of re-aggregating over thousands of edges per call. The filtered-subset distribution (the rows that survived the *user's query filters*) remains a query-time `percentileCont` aggregation in `genes_by_numeric_metric` — those stats are inherently per-call and cannot be precomputed. The two coexist: filtered stats describe *the result*, precomputed stats describe *the DM as a whole*.

## Current state (verified live 2026-04-26)

Numeric DerivedMetrics in the live KG: **15** (per `list_derived_metrics(value_kind='numeric')`). Existing rollup props on every DM:

```
total_gene_count: int  ✓ (already precomputed at import; e.g. 312 for damping_ratio, 1014 for cell_abundance MIT9312)
allowed_categories: list[str] | null  (categorical DMs only)
```

No precomputed value-distribution stats today. Reproducing per-DM stats in Cypher requires the per-DM aggregation pattern verified against the live KG:

```cypher
MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene]->(g:Gene)
WHERE dm.value_kind = 'numeric'
WITH dm, count(*) AS n,
     min(r.value)             AS v_min,
     max(r.value)             AS v_max,
     percentileCont(r.value, 0.25) AS v_q1,
     percentileCont(r.value, 0.5)  AS v_median,
     percentileCont(r.value, 0.75) AS v_q3
RETURN dm.id, dm.metric_type, n, v_min, v_q1, v_median, v_q3, v_max
ORDER BY dm.id;
```

Cost today: scans 5,114 edges per call; aggregation is server-side (`percentileCont` is a Cypher built-in). Single-DM cost is bounded by `dm.total_gene_count` — at most ~1,039 rows for the largest DM today (`cell_abundance_biovolume_normalized` MIT9313). Per-call latency is ~ms range, but the work is **redundant across every call** to either `list_derived_metrics` verbose or `genes_by_numeric_metric` envelope, even when no user filter has narrowed the slice.

Live-KG sample (2026-04-26 — for verification reference):

| DM (metric_type, organism) | total_gene_count | min | q1 | median | q3 | max |
|---|---|---|---|---|---|---|
| damping_ratio (MED4) | 312 | (verify) | — | — | — | (verify) |
| diel_amplitude_protein_log2 (MED4) | 312 | — | — | — | — | — |
| peak_time_protein_h (MED4) | 312 | 0 | — | 12.4 | — | 24 |
| cell_abundance_biovolume_normalized (MIT9312) | 1,014 | 8.85e-10 | — | 7.67e-9 | — | 8.02e-7 |
| cell_abundance_biovolume_normalized (MIT9313) | 1,039 | 2.24e-9 | — | 1.87e-8 | — | 2.98e-6 |

(Min / median / max columns above are populated from earlier live verification queries in the slice spec definition iteration; q1 / q3 columns to be filled by the verification queries §below at rebuild time.)

## Required changes

### Property changes

| Node/Edge | Property | Change | Notes |
|---|---|---|---|
| `DerivedMetric` (numeric only) | `value_min` | **add** (`float`) | min of `Derived_metric_quantifies_gene.value` over all this DM's edges. Equals `min(r.value)` Cypher aggregation. |
| `DerivedMetric` (numeric only) | `value_max` | **add** (`float`) | max of `r.value`. |
| `DerivedMetric` (numeric only) | `value_median` | **add** (`float`) | `percentileCont(r.value, 0.5)`. |
| `DerivedMetric` (numeric only) | `value_q1` | **add** (`float`) | `percentileCont(r.value, 0.25)`. |
| `DerivedMetric` (numeric only) | `value_q3` | **add** (`float`) | `percentileCont(r.value, 0.75)`. |

All five props are `null` on boolean and categorical DMs (no edge to compute over with this name; `Derived_metric_flags_gene.value` is string-typed, `Derived_metric_classifies_gene.value` is a category string). The BioCypher schema YAML should declare them `optional: true` so importer doesn't reject categorical/boolean DM rows that omit them.

No new nodes, edges, indexes, or constraints. No edge-property changes. Existing `total_gene_count` rollup unchanged.

### BioCypher / build-pipeline notes

- Add the five props under `DerivedMetric` in the schema YAML, marked `value_kind`-conditional (or `optional: true` if the schema doesn't support conditional emission — the rollup adapter populates them only when `value_kind='numeric'`).
- The rollup step that already computes `total_gene_count` (post-import, after edges are materialized) gains a numeric-DM branch that aggregates over `Derived_metric_quantifies_gene` and writes the five props back to the DM node. APOC is available in the importer container, so `apoc.coll.percentile(...)` or pure Python (`statistics.median`, `statistics.quantiles`) both work — pick whichever the existing rollup adapter already uses.
- Idempotency: the rollup is keyed off `dm.id`; re-running the importer on a clean DB produces identical values. No migration concern (these props don't exist today).

### Out of scope for this spec (deferred to slice-1 sibling tool specs)

- **Boolean DMs — `flag_true_count`, `flag_false_count`.** Same precompute pattern, different aggregation (`COUNT(r.value = 'true')`). File alongside `docs/tool-specs/genes_by_boolean_metric.md` (slice-1 tool 4) — that tool's `by_metric` envelope would benefit from the same node-property cheapness.
- **Categorical DMs — `category_distribution: map<str, int>`.** Counts per category, e.g. `{Cytoplasmic Membrane: 47, Cytoplasm: 134, ...}`. File alongside `docs/tool-specs/genes_by_categorical_metric.md` (slice-1 tool 5).
- **Rankable bucket distribution — `bucket_distribution: map<str, int>`.** Counts per `metric_bucket` value (`{top_decile: 31, top_quartile: 78, ...}`). Trivially derivable today from `total_gene_count` + bucket-rule definitions, and `genes_by_numeric_metric.by_metric` already exposes per-call bucket breakdowns when filters apply. Skip.
- **Bool-as-Neo4j-native, gene-side rollup unification, p-value column family** — see [companion KG spec §"Out of scope"](2026-04-26-unify-derived-metric-edge-value.md). Unrelated to numeric distribution precompute.
- **Filtered-subset stats.** Inherently per-call (depends on user filters); cannot be precomputed. Stays as `percentileCont` aggregation in the explorer's summary builder. See `docs/tool-specs/genes_by_numeric_metric.md` §"Query Builder".

## Example Cypher (desired)

After the rebuild, `list_derived_metrics` verbose can surface per-DM distribution as plain node-property reads — no edge traversal, no aggregation:

```cypher
MATCH (dm:DerivedMetric)
WHERE dm.value_kind = 'numeric'
RETURN dm.id, dm.metric_type, dm.total_gene_count,
       dm.value_min, dm.value_q1, dm.value_median, dm.value_q3, dm.value_max;
-- 15 rows, no aggregation, sub-ms.
```

Same pattern lights up `genes_by_numeric_metric.by_metric` envelope entries: each entry can carry **both** the filtered-subset stats (computed in the summary builder via `percentileCont` over rows that passed user filters) **and** the full-DM context (read from the precomputed DM-node props). The two together let the LLM see "your top-decile slice spans 12.2–25.3 out of the full DM range 0.1–25.3" in one envelope rollup instead of round-tripping to `list_derived_metrics`.

Concretely, the `by_metric` projection for one DM after the rebuild looks like:

```cypher
{
  derived_metric_id: dm.id,
  name: dm.name,
  metric_type: dm.metric_type,
  value_kind: dm.value_kind,
  count: <filtered row count>,
  value_min: <filtered min, percentileCont aggregation>,
  value_q1: <filtered>,
  value_median: <filtered>,
  value_q3: <filtered>,
  value_max: <filtered>,
  // full-DM context, plain reads:
  dm_value_min: dm.value_min,
  dm_value_q1: dm.value_q1,
  dm_value_median: dm.value_median,
  dm_value_q3: dm.value_q3,
  dm_value_max: dm.value_max,
  // rank stats (rankable-only) — query-time only, no DM-node analog
  rank_min: <filtered min(r.rank_by_metric) or null>,
  rank_max: <filtered max>
}
```

## Verification queries

Run these after KG rebuild to confirm the precompute landed:

```cypher
-- 1. Every numeric DM has all five new props populated.
MATCH (dm:DerivedMetric {value_kind: 'numeric'})
RETURN count(dm) AS total_numeric_dms,
       sum(CASE WHEN dm.value_min    IS NOT NULL THEN 1 ELSE 0 END) AS with_min,
       sum(CASE WHEN dm.value_max    IS NOT NULL THEN 1 ELSE 0 END) AS with_max,
       sum(CASE WHEN dm.value_median IS NOT NULL THEN 1 ELSE 0 END) AS with_median,
       sum(CASE WHEN dm.value_q1     IS NOT NULL THEN 1 ELSE 0 END) AS with_q1,
       sum(CASE WHEN dm.value_q3     IS NOT NULL THEN 1 ELSE 0 END) AS with_q3;
-- expected: all six counts equal 15 (today's numeric-DM total).

-- 2. Boolean and categorical DMs have null distribution props (sanity check —
--    schema is `optional: true` so the importer must not have populated them).
MATCH (dm:DerivedMetric)
WHERE dm.value_kind <> 'numeric'
RETURN dm.value_kind,
       sum(CASE WHEN dm.value_min IS NOT NULL THEN 1 ELSE 0 END) AS leaked_min,
       sum(CASE WHEN dm.value_median IS NOT NULL THEN 1 ELSE 0 END) AS leaked_median;
-- expected: both columns 0 for both 'boolean' and 'categorical'.

-- 3. Cross-check precomputed stats against live aggregation. Tolerance: exact
--    match for min/max; allow tiny floating-point drift (≈1e-9 relative) on
--    quartile / median if the rollup uses a different percentile method than
--    Cypher's percentileCont. If drift exceeds that, the rollup needs to use
--    Cypher-compatible interpolation (or document the deviation).
MATCH (dm:DerivedMetric {value_kind: 'numeric'})
MATCH (dm)-[r:Derived_metric_quantifies_gene]->(:Gene)
WITH dm, count(r) AS n,
     min(r.value)                  AS computed_min,
     max(r.value)                  AS computed_max,
     percentileCont(r.value, 0.5)  AS computed_median,
     percentileCont(r.value, 0.25) AS computed_q1,
     percentileCont(r.value, 0.75) AS computed_q3
RETURN dm.id,
       n = dm.total_gene_count                                       AS row_count_matches,
       dm.value_min        = computed_min                            AS min_matches,
       dm.value_max        = computed_max                            AS max_matches,
       abs(dm.value_median - computed_median) < 1e-9 * abs(computed_median + 1) AS median_close,
       abs(dm.value_q1     - computed_q1)     < 1e-9 * abs(computed_q1 + 1)     AS q1_close,
       abs(dm.value_q3     - computed_q3)     < 1e-9 * abs(computed_q3 + 1)     AS q3_close;
-- expected: all six boolean columns true on every row.

-- 4. Sanity bounds — quartiles ordered, median in [q1, q3], min ≤ q1, q3 ≤ max.
MATCH (dm:DerivedMetric {value_kind: 'numeric'})
RETURN dm.id,
       dm.value_min <= dm.value_q1                     AS min_le_q1,
       dm.value_q1  <= dm.value_median                 AS q1_le_median,
       dm.value_median <= dm.value_q3                  AS median_le_q3,
       dm.value_q3  <= dm.value_max                    AS q3_le_max;
-- expected: all four boolean columns true on every row.

-- 5. Spot-check a known DM. peak_time_protein_h is non-rankable, range 0–24h
--    by construction (clock-hour phase metric); median should be ~12h since
--    Waldbauer's 14:10 cycle phases roughly distribute across the day.
MATCH (dm:DerivedMetric {metric_type: 'peak_time_protein_h'})
RETURN dm.value_min, dm.value_q1, dm.value_median, dm.value_q3, dm.value_max;
-- expected: min 0, max 24, median ≈ 12.4 (matches earlier live aggregation).
```

## Downstream impact (explorer side, after rebuild)

| File | Change |
|---|---|
| [`docs/tool-specs/list_derived_metrics.md`](../tool-specs/list_derived_metrics.md) | Add the 5 numeric-only props to verbose RETURN — gated on `dm.value_kind = 'numeric'` (CASE pattern, mirrors `allowed_categories` gating on `value_kind = 'categorical'`). Add to `ListDerivedMetricsResult` Pydantic model with `default=None`. Add a verbose test confirming non-numeric DMs have null distribution fields. |
| [`docs/tool-specs/genes_by_numeric_metric.md`](../tool-specs/genes_by_numeric_metric.md) (this slice) | `by_metric` envelope entries gain `dm_value_min / dm_value_q1 / dm_value_median / dm_value_q3 / dm_value_max` alongside the query-time-aggregated filtered stats. |
| `multiomics_explorer/kg/queries_lib.py` | When `build_list_derived_metrics` (verbose) and `build_genes_by_numeric_metric_summary` ship, both reference the new DM-node props directly — no migration; the props simply weren't available before. |

`gene_derived_metrics` (already shipped) does **not** need full-DM distribution context — that tool is gene-anchored, not DM-anchored, and per-DM stats would bloat each row. Skip retrofit.

## Status

- [x] Spec reviewed with user (2026-04-26)
- [x] Schema updated in `multiomics_biocypher_kg` (BioCypher YAML)
- [x] Rollup adapter updated to compute + write the 5 numeric-DM props
- [x] KG rebuilt (2026-04-26)
- [x] Verification queries 1–5 pass — confirmed live:
   - **V1**: 15/15 numeric DMs have all 5 props populated.
   - **V2**: zero leakage (boolean=16, categorical=3, all `value_*` props null).
   - **V3**: precomputed stats match `percentileCont` aggregation within 1e-9 relative tolerance on all 15 DMs (rollup uses Cypher-compatible interpolation).
   - **V4**: `min ≤ q1 ≤ median ≤ q3 ≤ max` holds on every DM.
   - **V5**: `peak_time_protein_h` spot-check — `(min, q1, median, q3, max) = (0, 6.68, 12.35, 18.9, 24)` over 312 genes; matches the expected ~uniform clock-hour distribution.
   - **Smoke**: by_metric projection (filtered slice + full-DM context) works as designed for `damping_ratio top_decile` — 32 rows; filtered `value_median=15.9` clearly an upper-tail slice of full-DM `dm_value_median=4.9`.
- [ ] [`docs/tool-specs/list_derived_metrics.md`](../tool-specs/list_derived_metrics.md) updated to surface the new props (verbose RETURN + Pydantic + tests) — follow-up task, not blocking slice 1.
- [x] [`docs/tool-specs/genes_by_numeric_metric.md`](../tool-specs/genes_by_numeric_metric.md) `by_metric` design uses the precomputed props (drafted as part of this slice; ready for sign-off).
