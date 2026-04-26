# Tool spec: genes_by_numeric_metric

**Design spec:** [`docs/superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md`](../superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md) — shared slice-1 contract (KG invariants, gate-aware validation flow, envelope conventions, defensive CASE-gating). This file adds tool-specific verified Cypher, Pydantic surface, and the per-DM `by_metric` shape that pairs filtered-slice stats (query-time) with full-DM context (precomputed).

**Companion KG specs:**
- [`docs/kg-specs/2026-04-26-unify-derived-metric-edge-value.md`](../kg-specs/2026-04-26-unify-derived-metric-edge-value.md) — already landed; `r.value` is uniform across all 3 DM edge types.
- [`docs/kg-specs/2026-04-26-derived-metric-numeric-distribution-stats.md`](../kg-specs/2026-04-26-derived-metric-numeric-distribution-stats.md) — **drafted in this iteration**; precomputes `dm.value_min/q1/median/q3/max` on every numeric DM. The `by_metric` envelope below assumes these props are available; if the rebuild slips, fall back to query-time-only stats and re-introduce the precomputed columns when the KG ships them.

## Purpose

Drill-down on `Derived_metric_quantifies_gene` — Tool 3 of slice 1, mirrors `genes_in_cluster`. Answers "given a numeric DM (or set of them), which genes carry the highest values / pass a percentile gate / fall in a named bucket / sit at a specific rank?" One row per gene × DM, with edge-level filters (`min_value` / `bucket` / `min_percentile` / `max_rank` / etc.) that gate against the parent DM's `rankable` flag. Cross-organism by design (drill-downs intentionally allow comparing ortholog response across strains; single-organism scoping stays opt-in via `organism` or `locus_tags`).

The tool's primary footgun is using a rankable-gated filter on a non-rankable DM. The slice-1 spec's "two-branch" validation pattern — *some* selected DMs gate-incompatible → soft-exclude into envelope `excluded_derived_metrics` + `warnings`; *all* selected DMs gate-incompatible → hard-fail `ValueError` — lands here as the canonical surface for the LLM to learn from.

## Out of Scope

- **Discovery / per-paper inventory** — use `list_derived_metrics` to find DMs by tag, organism, or text search. Inspect `rankable` / `has_p_value` there before drilling down.
- **Boolean / categorical DM drill-down** — pivot to `genes_by_boolean_metric` (slice-1 tool 4) or `genes_by_categorical_metric` (slice-1 tool 5). This tool's `value_kind='numeric'` enforcement is strict.
- **Gene-anchored batch view across all kinds** — use `gene_derived_metrics`, which returns a polymorphic-`value` row per gene × DM and lets a caller branch on `value_kind`.
- **Cross-DM gene-set extraction (TERM2GENE for enrichment)** — slice-1 design spec §"Out of slice 1". May ship as a separate utility outside MCP.
- **Differential expression** — use `differential_expression_by_gene` / `_by_ortholog`. This tool surfaces *non-DE* evidence (column-level scalar summaries — diel amplitudes, vesicle abundances, damping ratios).

## Status / Prerequisites

- [x] Slice-1 design spec reviewed and approved (2026-04-23)
- [x] KG cleanup landed (2026-04-26, [unify-derived-metric-edge-value](../kg-specs/2026-04-26-unify-derived-metric-edge-value.md)): all 3 DM edge types expose `r.value` uniformly. Verified live: 5,114 quantifies edges with `r.value` populated.
- [x] KG invariants verified live (2026-04-26, refreshed in this iteration — KG has grown since slice spec; baselines below)
- [x] Per-DM full-distribution KG spec drafted ([numeric-distribution-stats](../kg-specs/2026-04-26-derived-metric-numeric-distribution-stats.md))
- [x] **Per-DM full-distribution KG rebuild landed** (2026-04-26). Verified live: all 15 numeric DMs carry `value_min/q1/median/q3/max`; cross-check vs `percentileCont` matches within 1e-9 tolerance; quartile bounds hold on every DM; by_metric projection (filtered + full-DM context) returns expected shape on canonical worked example. The `by_metric.dm_value_*` columns are now first-class — no skip-marker fallback needed.
- [ ] Build plan approved (then Phase 2)

**Spec freeze.** Per the `add-or-update-tool` skill: once the user signs off, this spec is frozen — adding result fields, removing parameters, or changing the query architecture during build requires re-approval. Design iteration belongs in Phase 1.

## Use cases

- **Top-N drill-down.** "Which 20 MED4 genes have the highest `damping_ratio`?" — `metric_types=['damping_ratio'], max_rank=20` (rankable-gated).
- **Percentile / bucket gating.** "Top decile of vesicle / cell enrichment in MIT9313" — `metric_types=['log2_vesicle_cell_enrichment'], organism='MIT9313', bucket=['top_decile']`.
- **Raw-value thresholds on non-rankable DMs.** "Mascot identification probability above 99% in the MED4 vesicle proteome" — `metric_types=['mascot_identification_probability'], organism='MED4', min_value=99` (raw threshold; mascot probability is non-rankable, so `bucket` would raise — `min_value` does not).
- **DE follow-up.** Given a hit list from `differential_expression_by_gene`, scope a numeric DM drill-down to those genes — `genes_by_numeric_metric(metric_types=[...], locus_tags=hits)` — to see which DE hits also lead the diel amplitude distribution.
- **Cross-organism comparison.** "How does diel `damping_ratio` compare across MED4 and MIT9313 paired RNAseq/proteome experiments?" — drill-down without organism scope; envelope `by_organism` rolls up rows per strain.
- **Tool chaining.** `list_derived_metrics(value_kind='numeric', rankable=True)` → pick `derived_metric_ids` → `genes_by_numeric_metric(derived_metric_ids=[...], bucket=['top_decile'])` → top-decile gene list → `gene_overview(locus_tags=[...])` for routing.

## KG dependencies

Verified live 2026-04-26 (post 2026-04-26 edge-value unification rebuild; pre per-DM distribution rebuild):

- `Gene` nodes — `locus_tag` (key), `gene_name`, `product`, `gene_category`, `organism_name` (per-row identity columns). Heavy text for verbose: `function_description`, `gene_summary`.
- `DerivedMetric` nodes — for filter, identity, and (post-rebuild) full-DM distribution context:
  - Identity: `id, name, metric_type, value_kind, rankable, has_p_value, unit, field_description`.
  - Scoping (DM-level): `organism_name, experiment_id, publication_doi, compartment, omics_type, treatment_type, background_factors, growth_phases`.
  - Verbose: `treatment, light_condition, experimental_context`.
  - **Pending KG rebuild** (per [numeric-distribution-stats](../kg-specs/2026-04-26-derived-metric-numeric-distribution-stats.md)): `value_min, value_max, value_median, value_q1, value_q3` (numeric DMs only).
- `Derived_metric_quantifies_gene` edges — value + rank/percentile/bucket extras. Schema (verified live):
  - Always: `id, metric_type, value` (float).
  - When parent `dm.rankable='true'`: `rank_by_metric, metric_percentile, metric_bucket`.
  - When parent `dm.has_p_value='true'`: `adjusted_p_value, significant, p_value` — **none today** (0/15 numeric DMs); column family triggers CyVer schema warnings if referenced. Forward-compat surface only.

### Refreshed live-KG baselines (2026-04-26 — supersedes slice spec)

| Quantity | Slice spec (2026-04-23) | Today (2026-04-26) |
|---|---|---|
| Numeric `DerivedMetric` nodes | 6 | **15** |
| ↳ `rankable=true` | 4 | **11** |
| ↳ `rankable=false` | 2 | **4** |
| ↳ `has_p_value=true` | 0 | **0** (unchanged) |
| `Derived_metric_quantifies_gene` edges | 1,872 | **5,114** |
| ↳ edges with `rank_by_metric` populated | 1,248 (4 rankable × 312) | **4,432** (rankable subset; matches 5,114 − 624 non-rankable Waldbauer phase + 58 mascot non-rankable) |
| Numeric DMs spanning >1 organism (same `metric_type`) | 0 | **4** (`mascot_identification_probability`, `cell_abundance_biovolume_normalized`, `vesicle_abundance_biovolume_normalized`, `log2_vesicle_cell_enrichment`) |
| Compartments populated for numeric DMs | `whole_cell` | `whole_cell` (6), `vesicle` (9) |

The 4 cross-organism `metric_type` tags are why **single-organism is not enforced** — drilling down without `organism` is a valid biological question (e.g. "compare top-decile cell-abundance proteins between MIT9312 and MIT9313").

### Verified canonical scenarios (used as test fixtures + YAML examples)

Verified against live KG 2026-04-26:

| Scenario | Result |
|---|---|
| `metric_types=['damping_ratio']` (no edge filter) | 312 rows (= MED4 paired-diel gene set) |
| `metric_types=['damping_ratio'], bucket=['top_decile']` | **32 rows** (≈10% of 312); ranked 1–32 by `r.rank_by_metric`, values 25.3 → 12.2; gene_categories include Translation (6), Photosynthesis (5), Carbohydrate metabolism (5) |
| `metric_types=['damping_ratio','peak_time_protein_h'], bucket=['top_decile']` (mixed-rankable) | 32 rows (damping_ratio only); `peak_time_protein_h` excluded → `excluded_derived_metrics: [{rankable: false, reason: 'non-rankable; bucket filter does not apply'}]` |
| `metric_types=['peak_time_transcript_h'], bucket=['top_decile']` (all non-rankable) | **`ValueError`** — every selected DM has `rankable=false`; api/ raises before running summary/detail |
| `metric_types=['cell_abundance_biovolume_normalized'], bucket=['top_quartile']` (cross-organism, both rankable) | 308 rows (152 from MIT9312 + 156 from MIT9313); per-DM `count` 152 / 156, `value_max` 8.02e-7 / 2.98e-6, `value_median` 7.67e-9 / 1.87e-8 |
| `metric_types=['cell_abundance_biovolume_normalized']` (no edge filter, full DM) | 2,053 rows (1,014 MIT9312 + 1,039 MIT9313 — every `total_gene_count` row) |
| `significant_only=True` on any numeric DM | **`ValueError`** — 0/15 DMs have `has_p_value=true`; intentional today |

## Tool Signature

```python
@mcp.tool(
    tags={"derived-metrics", "genes", "drill-down", "numeric"},
    annotations={"readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def genes_by_numeric_metric(
    ctx: Context,
    # ── Selection (exactly one required, mutually exclusive) ────────
    derived_metric_ids: Annotated[list[str] | None, Field(
        description="DerivedMetric node IDs to drill into. Use when the "
                    "same `metric_type` appears across publications / "
                    "organisms and you need to pin one. Discover IDs via "
                    "`list_derived_metrics`. Mutually exclusive with "
                    "`metric_types`.",
    )] = None,
    metric_types: Annotated[list[str] | None, Field(
        description="Metric-type tags (e.g. ['damping_ratio', "
                    "'diel_amplitude_protein_log2']). Unions every DM "
                    "carrying that tag, then narrows by scoping filters. "
                    "Same tag can appear across organisms (e.g. "
                    "'cell_abundance_biovolume_normalized' is on both "
                    "MIT9312 and MIT9313 today). Mutually exclusive with "
                    "`derived_metric_ids`.",
    )] = None,
    # ── DM-scoping filters (intersected with selection) ─────────────
    organism: Annotated[str | None, Field(
        description="Organism to scope the DM set to. Accepts short strain "
                    "code ('MED4', 'NATL2A', 'MIT9312') or full name. "
                    "Case-insensitive substring match. Single-organism is "
                    "**not** enforced — omit to drill across all "
                    "organisms a metric_type spans.",
    )] = None,
    locus_tags: Annotated[list[str] | None, Field(
        description="Restrict drill-down to a specific gene set (e.g. DE "
                    "hits from `differential_expression_by_gene`). Filter "
                    "on `g.locus_tag IN $locus_tags` post-MATCH. Genes "
                    "with no edge for the selected DM produce no row "
                    "(silent — surfaced via `total_genes` shortfall).",
    )] = None,
    experiment_ids: Annotated[list[str] | None, Field(
        description="Scope to DMs from one or more experiments.",
    )] = None,
    publication_doi: Annotated[list[str] | None, Field(
        description="Scope to DMs from one or more publications.",
    )] = None,
    compartment: Annotated[str | None, Field(
        description="Sample compartment ('whole_cell', 'vesicle', "
                    "'exoproteome', 'spent_medium', 'lysate'). Exact match.",
    )] = None,
    treatment_type: Annotated[list[str] | None, Field(
        description="Treatment type(s) (e.g. ['diel', 'compartment']). "
                    "ANY-overlap. Case-insensitive.",
    )] = None,
    background_factors: Annotated[list[str] | None, Field(
        description="Background factor(s) (e.g. ['axenic', 'light']). "
                    "ANY-overlap. Case-insensitive.",
    )] = None,
    growth_phases: Annotated[list[str] | None, Field(
        description="Growth phase(s). ANY-overlap. Case-insensitive.",
    )] = None,
    # ── Edge-level filters: always-available (any numeric DM) ───────
    min_value: Annotated[float | None, Field(
        description="Lower bound on `r.value`. Always applicable — no gate. "
                    "Use for raw-threshold queries on non-rankable DMs "
                    "(e.g. mascot probability ≥ 99).",
    )] = None,
    max_value: Annotated[float | None, Field(
        description="Upper bound on `r.value`. Always applicable.",
    )] = None,
    # ── Edge-level filters: RANKABLE-GATED (raises if all selected DMs are non-rankable) ──
    min_percentile: Annotated[float | None, Field(
        description="Lower bound on `r.metric_percentile` (0–100). "
                    "**Rankable-gated** — raises if every selected DM has "
                    "`rankable=False`. Soft-excludes non-rankable DMs from "
                    "mixed input, surfaced in `excluded_derived_metrics`.",
        ge=0, le=100,
    )] = None,
    max_percentile: Annotated[float | None, Field(
        description="Upper bound on `r.metric_percentile`. **Rankable-gated.**",
        ge=0, le=100,
    )] = None,
    bucket: Annotated[list[str] | None, Field(
        description="Bucket label(s) — subset of "
                    "{'top_decile','top_quartile','mid','low'}. "
                    "**Rankable-gated.** Today's KG buckets correspond to "
                    "decile / quartile splits computed at import time per DM.",
    )] = None,
    max_rank: Annotated[int | None, Field(
        description="Cap on `r.rank_by_metric` (1 = highest). Use for "
                    "top-N drill-down. **Rankable-gated.**",
        ge=1,
    )] = None,
    # ── Edge-level filters: HAS_P_VALUE-GATED (always raises today — 0/15 DMs have p-values) ──
    significant_only: Annotated[bool, Field(
        description="Filter to `r.significant=true`. **has_p_value-gated** — "
                    "raises against today's KG (no DM has p-values yet). "
                    "Forward-compat surface; check "
                    "`list_derived_metrics(has_p_value=True)` before using.",
    )] = False,
    max_adjusted_p_value: Annotated[float | None, Field(
        description="Upper bound on `r.adjusted_p_value`. **has_p_value-gated**.",
        ge=0, le=1,
    )] = None,
    # ── Result-size controls ────────────────────────────────────────
    summary: Annotated[bool, Field(
        description="Return summary fields only (counts, breakdowns, "
                    "by_metric, diagnostics). Sugar for limit=0; results=[].",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include heavy text fields per row: "
                    "gene_function_description, gene_summary, plus DM "
                    "context (metric_type, field_description, unit, "
                    "compartment, experiment_id, publication_doi, "
                    "treatment_type, background_factors, treatment, "
                    "light_condition, experimental_context). p_value (raw) "
                    "is reserved for future has_p_value DMs.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max rows to return. Paginate with `offset`. Use "
                    "`summary=True` for summary-only (sets limit=0).",
        ge=1,
    )] = 5,
    offset: Annotated[int, Field(
        description="Pagination offset (starting row, 0-indexed).",
        ge=0,
    )] = 0,
) -> GenesByNumericMetricResponse:
    """Pass `derived_metric_ids` XOR `metric_types` (one required); rankable-gated filters (`bucket`, `min/max_percentile`, `max_rank`) raise if every selected DM has `rankable=False` and soft-exclude on mixed input — inspect `list_derived_metrics(value_kind='numeric', rankable=True)` first to see which DMs support which filters.

    Numeric DM drill-down — one row per gene × DM. `r.value` (float) is
    always returned; `rank_by_metric` / `metric_percentile` /
    `metric_bucket` are populated only on rows from rankable DMs (null
    otherwise — same shape as `gene_derived_metrics`). Cross-organism by
    design; envelope `by_organism` and per-row `organism_name` make
    cross-strain rows self-describing. The `by_metric` envelope rollup
    pairs filtered-slice value distribution with full-DM distribution
    (precomputed) so callers can read "your top-decile slice 12.2–25.3
    out of full DM range 0–28" directly.

    `excluded_derived_metrics` + `warnings` envelope keys are the
    primary diagnostic when a real DM produces zero rows; check these
    before assuming the result is empty for biological reasons.
    """
```

## Result-size controls

Drill-down with potentially-large rowsets — the `summary` + `verbose` + `limit` triplet, default `limit=5` (matches `gene_derived_metrics` and `genes_in_cluster` precedent: LLM gets summary + a few example rows in one call). Detail and `by_metric` aggregations are skipped when `limit==0` (i.e. `summary=True`); the cheaper rollup-only path still runs.

### Summary envelope

| Field | Type | Description |
|---|---|---|
| `total_matching` | int | Rows (gene × DM pairs) matching all filters, post-gate. |
| `total_derived_metrics` | int | Distinct DMs that contributed rows after selection + scoping + gate exclusion. **Pre-gating count = `total_derived_metrics + len(excluded_derived_metrics)`** (matches the slice spec convention; mirrors `list_clustering_analyses` / `genes_in_cluster` single-scalar pattern). |
| `total_genes` | int | Distinct genes in `results` (any DM). Mirrors `genes_by_homolog_group.total_genes`. |
| `by_organism` | list[{organism_name, count}] | Rows per organism. |
| `by_compartment` | list[{compartment, count}] | Rows per compartment (e.g. `whole_cell`, `vesicle`). |
| `by_publication` | list[{publication_doi, count}] | Rows per parent publication. |
| `by_experiment` | list[{experiment_id, count}] | Rows per parent experiment. |
| `by_metric` | list[*GenesByNumericMetricBreakdown*] (see below) | **Per-DM rollup with value distribution.** Replaces the slice spec's `by_metric_type` (per-tag rollup) since the same tag can split across DMs (e.g. cell_abundance MIT9312 vs MIT9313 are two distinct DMs but one tag). Each entry carries filtered-slice stats (query-time `percentileCont`) + full-DM stats (precomputed DM-node props). Sorted by count desc. |
| `top_categories` | list[{gene_category, count}] | Top 5 gene categories by row count (matches `genes_in_cluster.top_categories`). |
| `genes_per_metric_max` | int | Largest per-DM gene count (= `max(by_metric[i].count)`). Convenience derivation. |
| `genes_per_metric_median` | float | Median per-DM gene count. Convenience derivation. |
| `not_found_ids` | list[str] | Inputs from `derived_metric_ids` not present in KG. |
| `not_matched_ids` | list[str] | Inputs from `derived_metric_ids` present in KG but produced 0 rows after all filters (excludes gate-excluded DMs — those land in `excluded_derived_metrics`). |
| `not_found_metric_types` | list[str] | Inputs from `metric_types` that match no DM in KG (after scoping). |
| `not_matched_metric_types` | list[str] | Inputs from `metric_types` whose DMs all produced 0 rows after edge-level filters. |
| `not_matched_organism` | str \| None | Set when `organism` was provided and no surviving DM is from that organism. |
| `excluded_derived_metrics` | list[*ExcludedDerivedMetric*] (see below) | DMs that passed selection + scoping but were dropped because a rankable- or has_p_value-gated filter does not apply. **Always present — empty list when no exclusions, never missing.** Primary LLM diagnostic for empty results from real DMs. |
| `warnings` | list[str] | Human-readable summary of `excluded_derived_metrics` (e.g. `["1 non-rankable DM excluded by `bucket` filter (peak_time_protein_h)"]`). Always present, empty list by default. |
| `returned` | int | `len(results)`. |
| `offset` | int | Echo of input. |
| `truncated` | bool | `total_matching > offset + returned`. |
| `results` | list[*GenesByNumericMetricResult*] | One row per gene × DM. Empty when `summary=True`. |

#### `by_metric` entry shape (`GenesByNumericMetricBreakdown`)

```
{
  derived_metric_id, name, metric_type, value_kind, count,
  value_min,    value_q1,    value_median,    value_q3,    value_max,        # filtered slice (query-time percentileCont)
  dm_value_min, dm_value_q1, dm_value_median, dm_value_q3, dm_value_max,     # full DM (precomputed dm.value_*)
  rank_min, rank_max                                                         # filtered slice, rankable-only
}
```

**Filtered vs full-DM:** filtered stats (`value_*`) describe the rows that survived the user's filters — what the caller is actually looking at. Full-DM stats (`dm_value_*`) describe the DM as a whole — read from precomputed node props after the [numeric-distribution-stats KG rebuild](../kg-specs/2026-04-26-derived-metric-numeric-distribution-stats.md). Both coexist in the same entry so the LLM can compare slice to baseline ("top decile is 12.2–25.3 out of full range 0–28") without round-tripping to `list_derived_metrics`.

`rank_min` / `rank_max` are populated only on rankable DMs (the underlying `r.rank_by_metric` is null for non-rankable; `apoc.coll.min`/`max` over an all-null list returns null cleanly). For a top-decile filter, `rank_min` is typically 1 (since rank=1 is the highest value) and `rank_max` is roughly `total_gene_count / 10`.

#### `excluded_derived_metrics` entry shape (`ExcludedDerivedMetric`)

```
{
  derived_metric_id, metric_type,
  rankable: bool, has_p_value: bool,
  reason: str        # e.g. "non-rankable; `bucket` filter does not apply"
}
```

Populated entirely from the diagnostics builder output (see §"Query Builder"); api/ formats `reason` based on which gated filter fired and the DM's actual flag values.

### Detail mode — per-row compact (14 RETURN columns; 16 Pydantic compact fields = 14 + 2 deferred forward-compat)

**Identity / routing (5):** `locus_tag`, `gene_name`, `product`, `gene_category`, `organism_name`

**DM identity (2):** `derived_metric_id`, `name` (DM human label — saves a round-trip to `list_derived_metrics` for opaque metric_type codes; mirrors `genes_in_cluster.cluster_name`)

**Gate echoes (3):** `value_kind` (always `'numeric'` for this tool — kept for cross-tool row-shape consistency with `gene_derived_metrics`), `rankable`, `has_p_value` (echoed from parent DM as Python `bool` after string coercion — `dm.rankable = 'true' AS rankable`)

**Numeric value (4):** `value` (float, from `r.value`); `rank_by_metric`, `metric_percentile`, `metric_bucket` — all CASE-gated on `dm.rankable = 'true'` (null on non-rankable rows)

### Detail mode — Pydantic-only forward-compat (2 fields, NOT in current Cypher RETURN)

Same deferral pattern as [`gene_derived_metrics`](gene_derived_metrics.md) §"Detail (per-row compact)":

- `adjusted_p_value` — declared in `GenesByNumericMetricResult` with `default=None`.
- `significant` — same.

**Both are intentionally absent from the current Cypher RETURN.** No edge in today's KG carries `adjusted_p_value` (0/15 DMs have `has_p_value='true'`) and including the CASE-gated columns produces CyVer schema warnings (`The label Derived_metric_quantifies_gene does not have the following properties: adjusted_p_value, significant`). Re-add the gated RETURN columns when a `has_p_value='true'` DM lands:

```cypher
CASE WHEN dm.has_p_value = 'true' THEN r.adjusted_p_value ELSE null END AS adjusted_p_value,
CASE WHEN dm.has_p_value = 'true' THEN r.significant      ELSE null END AS significant
```

### Verbose adds (14 in Pydantic, 13 in current Cypher RETURN)

DM context (8): `metric_type`, `field_description`, `unit`, `compartment`, `experiment_id`, `publication_doi`, `treatment_type` (list), `background_factors` (list)

Heavy text — DM (3): `treatment`, `light_condition`, `experimental_context`

Heavy text — gene (2, mirrors `genes_in_cluster` verbose): `gene_function_description`, `gene_summary`

Forward-compat (1, Pydantic-only): `p_value` (raw, edge-side) — gated on `has_p_value='true'`; deferred from current Cypher RETURN. Re-add `CASE WHEN dm.has_p_value='true' THEN r.p_value ELSE null END AS p_value` to the verbose block when a has_p_value DM lands.

### Sort key

`r.rank_by_metric ASC, r.value DESC, dm.id ASC, g.locus_tag ASC`

Verified live with `damping_ratio` top-decile (32 rows): rank-ordered 1–32, ties on rank break by value descending, then deterministic by `dm.id` then `g.locus_tag` so paginated calls are stable.

For non-rankable DMs in mixed-result calls (no rankable filters used), `r.rank_by_metric` is null on those rows — Neo4j's default ASC sort places nulls last, so non-rankable rows fall after rankable ones within a result page. This is the desired ordering: rank-first when ranks exist, raw value otherwise.

## Special handling

- **Mutual exclusion: `derived_metric_ids` XOR `metric_types`.** Exactly one required. Both → `ValueError("provide one of derived_metric_ids or metric_types, not both")`. Neither → `ValueError("must provide one of derived_metric_ids or metric_types")`.
- **Strict `value_kind='numeric'` enforcement.** All selected DMs must have `value_kind='numeric'`; offending IDs raise `ValueError` listing each DM's actual `value_kind` and pointing to the matching `genes_by_{kind}_metric` tool. Caught at the diagnostics-query stage (Q1) before any aggregation runs.
- **Rankable-gated validation (two-branch).** Filters `bucket`, `min_percentile`, `max_percentile`, `max_rank`:
  - **All selected DMs `rankable=false`** → `ValueError` listing each selected DM's `rankable` state + which filter(s) triggered. Hard-fail.
  - **Some selected DMs `rankable=false`** → proceed with rankable-only set; surface the dropped DMs in `excluded_derived_metrics` + append to `warnings`. Soft-exclude.
- **has_p_value-gated validation (two-branch, same shape).** Filters `significant_only`, `max_adjusted_p_value`. Today every numeric DM has `has_p_value=false`, so any use of these filters hits the all-fail branch and raises — **intentional diagnostic**, not a bug. Re-tunable when a has_p_value DM lands.
- **Cross-organism by design.** No single-organism enforcement. The `organism` filter is opt-in scoping; `locus_tags` is too. Mirrors `genes_in_cluster` (which also doesn't gate cross-organism). Per-row `organism_name` plus envelope `by_organism` keep results self-describing.
- **`compartment` is exact-match `str`.** Matches `list_derived_metrics` / `gene_derived_metrics` precedent (controlled vocabulary; case-sensitive). Surface kept as `str` rather than `Literal[...]` so new compartments (slice 3) don't require re-typing.
- **Treatment / background / growth-phase filters are case-insensitive ANY-overlap.** Reuses `_list_derived_metrics_where` directly — same exact pattern as the entry-point tool.
- **Defensive CASE-gating on every gate-dependent RETURN column.** Per slice spec canonical pattern. The DM-level `dm.rankable` / `dm.has_p_value` flag is the source of truth, **not** edge property presence — robust to KG build bugs (e.g. a future DM accidentally getting `rankable='false'` set but edges still carrying `rank_by_metric`).
- **Forward-compat `adjusted_p_value` / `significant` / `p_value`.** Pydantic models declare these with `default=None`; Cypher RETURN currently omits them (CyVer warnings on missing props). Re-add CASE-gated RETURN lines when a `has_p_value='true'` DM lands — see the deferred-block snippet under "Detail mode — Pydantic-only forward-compat" above.
- **String-typed booleans on KG.** `dm.rankable` and `dm.has_p_value` are stored as Cypher strings `"true"` / `"false"` (BioCypher emits them as such; see [companion KG spec §"Out of scope"](../kg-specs/2026-04-26-unify-derived-metric-edge-value.md)). All builders compare with `dm.rankable = 'true'` etc. and coerce to Python `bool` via `dm.rankable = 'true' AS rankable` in RETURN. API params stay normal `bool` — coercion happens at the builder boundary.
- **3-query orchestration in api/.** Diagnostics → validate gates → summary + detail. See §"Query Builder" + §"API Function".
- **`summary=True` shortcut.** Forces `limit=0`; detail query skipped. Diagnostics + summary still run (envelope is fully populated; `results=[]`).
- **Truncation logic.** `truncated = total_matching > offset + returned`. True when `summary=True` and `total_matching > 0` (mirrors slice convention).
- **`omics_type` deliberately omitted from the tool surface.** `_list_derived_metrics_where` accepts an `omics_type` filter, but `genes_by_numeric_metric` does not surface it (mirrors `gene_derived_metrics`). DM-level `omics_type` is highly correlated with `compartment` + `experiment_id` for numeric DMs in the current KG — adding it would be a third near-duplicate filter without payoff for slice 1. Re-evaluate when a DM lands where `omics_type` orthogonally differentiates from the existing surface.

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_genes_by_numeric_metric_diagnostics()` (new), `build_genes_by_numeric_metric_summary()` (new), `build_genes_by_numeric_metric()` (new) |
| 2 | Unit test | `tests/unit/test_query_builders.py` | `TestBuildGenesByNumericMetricDiagnostics`, `TestBuildGenesByNumericMetricSummary`, `TestBuildGenesByNumericMetric` |
| 3 | API function | `api/functions.py` | `genes_by_numeric_metric()` (orchestrates 3 queries + gate validation) |
| 4 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add to imports + `__all__` |
| 5 | Unit test | `tests/unit/test_api_functions.py` | `TestGenesByNumericMetric` (mocked GraphConnection; covers gate validation paths) |
| 6 | MCP wrapper | `mcp_server/tools.py` | Pydantic models + `@mcp.tool` wrapper |
| 7 | Unit test | `tests/unit/test_tool_wrappers.py` | `TestGenesByNumericMetricWrapper` + `EXPECTED_TOOLS` |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | `TestGenesByNumericMetric` (`@pytest.mark.kg`) |
| 8a | Contract | `tests/integration/test_api_contract.py` | `TestGenesByNumericMetricContract` — pin envelope + result keys (incl. `excluded_derived_metrics` + `warnings` always present) |
| 8b | Correctness | `tests/integration/test_tool_correctness_kg.py` | `TestBuildGenesByNumericMetricCorrectnessKG` if pattern applies |
| 9 | Regression | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS` (3 builder entries — diagnostics / summary / detail), regenerate baselines |
| 9a | Eval | `tests/evals/test_eval.py` | Add to `TOOL_BUILDERS` |
| 10 | Eval cases | `tests/evals/cases.yaml` | Add 3–4 cases (top-decile, mixed-rankable soft-exclude, all-non-rankable hard-fail, cross-organism) |
| 11 | About content | `multiomics_explorer/inputs/tools/genes_by_numeric_metric.yaml` | Author YAML |
| 12 | About markdown | (generated) | `uv run python scripts/build_about_content.py genes_by_numeric_metric` |
| 13 | CLAUDE.md | `CLAUDE.md` | Add row to MCP Tools table |
| 14 | Code review | — | Per `.claude/skills/code-review/SKILL.md` |

Detailed bite-sized task list lives in `docs/superpowers/plans/2026-04-26-genes-by-numeric-metric.md` (writing-plans format) — to be authored once this spec is approved.

---

## Query Builder

**File:** `multiomics_explorer/kg/queries_lib.py`

Three builders. The diagnostics builder runs first (api/ uses its output to validate gates and decide hard-fail vs soft-exclude); summary and detail then run over the surviving DM ID list. Reuses `_list_derived_metrics_where` for DM-scoping conditions — identical filter surface as the entry-point tool.

### `build_genes_by_numeric_metric_diagnostics`

Pre-flight: resolves `derived_metric_ids` / `metric_types` to the DM set + identity + gate flags. **Always returns the canonical column shape** (one row per surviving DM) so api/ can iterate over it without conditional handling.

```python
def build_genes_by_numeric_metric_diagnostics(
    *,
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Pre-flight DM selection + gate-state probe.

    api/ runs this BEFORE summary/detail so it can:
      1. Validate every selected DM has `value_kind='numeric'` (raise on
         mismatch).
      2. Compute `excluded_derived_metrics` for rankable-/p-value-gated
         filters that don't apply to some/all selected DMs.
      3. Pass the surviving DM ID list to summary/detail.

    Reuses `_list_derived_metrics_where` for DM-scoping conditions.
    Hardcoded `dm.value_kind = 'numeric'` predicate (this tool only
    drills into numeric DMs; mismatches surface here as zero-row results
    that api/ converts to a ValueError listing offending IDs).

    RETURN keys (one row per surviving DM):
      derived_metric_id, metric_type, value_kind, name,
      rankable, has_p_value, total_gene_count, organism_name.
    """
```

Cypher (verified live 2026-04-26 with `metric_types=['damping_ratio','peak_time_protein_h']`):

```cypher
MATCH (dm:DerivedMetric)
WHERE <AND-joined conditions from _list_derived_metrics_where(value_kind='numeric', ...)>
RETURN dm.id                AS derived_metric_id,
       dm.metric_type       AS metric_type,
       dm.value_kind        AS value_kind,
       dm.name              AS name,
       dm.rankable = 'true' AS rankable,
       dm.has_p_value = 'true' AS has_p_value,
       dm.total_gene_count  AS total_gene_count,
       dm.organism_name     AS organism_name
ORDER BY dm.id ASC
```

WHERE construction reuses the existing helper at [`queries_lib.py:4250`](../../multiomics_explorer/kg/queries_lib.py#L4250). Pass `value_kind='numeric'` plus the user's selection (`derived_metric_ids` and/or `metric_types`) and DM-scoping params; helper emits its own `dm.value_kind = $value_kind` clause + the per-filter conditions, AND-joined. **No separate literal `dm.value_kind = 'numeric'` predicate is needed in the builder body** — the helper covers it. Confusingly, the helper's `value_kind` arg is shared with `list_derived_metrics` (where it's a user filter); here it's used as a strict tool-level guard.

**`total_gene_count` consumption in api/.** Surfaced in the diagnostics RETURN so api/ can compute `not_matched_ids` accurately: a DM with `total_gene_count > 0` but zero rows in `by_metric` was filtered out at the edge layer; a DM with `total_gene_count = 0` (rare — implies the rollup ran on an empty edge set) is structurally barren and lands in a different diagnostic bucket. For slice 1, both collapse into `not_matched_ids` (no behavioral split today), but the column gives the api/ a hook for future refinement without re-querying the KG.

**Verified live** (canonical worked example): with `metric_types=['damping_ratio','peak_time_protein_h']` returns 2 rows — `damping_ratio` (rankable=true) and `peak_time_protein_h` (rankable=false), both `has_p_value=false`, both `total_gene_count=312`. api/ sees the mixed-rankable set → if user passed a rankable-gated filter, soft-exclude `peak_time_protein_h` into `excluded_derived_metrics`.

### `build_genes_by_numeric_metric_summary`

Takes the **gate-validated** `derived_metric_ids` list (api/ has already resolved metric_types and excluded incompatible DMs), plus all edge-level filters that survived gate validation. Produces the envelope rollups in one query.

```python
def build_genes_by_numeric_metric_summary(
    *,
    derived_metric_ids: list[str],     # gate-validated; never empty when called
    locus_tags: list[str] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_percentile: float | None = None,
    max_percentile: float | None = None,
    bucket: list[str] | None = None,
    max_rank: int | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_numeric_metric.

    `significant_only` / `max_adjusted_p_value` are **not** parameters —
    they would never reach this builder against today's KG (api/ raises
    on the all-fail branch). When a has_p_value DM lands, add the
    corresponding edge-level WHERE conditions here.

    RETURN keys: total_matching, total_derived_metrics, total_genes,
    by_organism, by_compartment, by_publication, by_experiment,
    by_metric, top_categories, genes_per_metric_max,
    genes_per_metric_median.
    """
```

Cypher pattern (verified live; uses the row-collect-then-derive idiom from `gene_derived_metrics_summary`):

```cypher
MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene]->(g:Gene)
WHERE dm.id IN $derived_metric_ids
  <AND edge-level filter conditions>
WITH collect({
  dm_id: dm.id, dm_name: dm.name, mt: dm.metric_type, vk: dm.value_kind,
  org: g.organism_name, cat: coalesce(g.gene_category, 'Unknown'),
  comp: dm.compartment, doi: dm.publication_doi, exp: dm.experiment_id,
  lt: g.locus_tag,
  value: r.value, rank: r.rank_by_metric,
  // full-DM stats from precomputed DM-node props (post-rebuild)
  dm_vmin: dm.value_min, dm_vq1: dm.value_q1, dm_vmed: dm.value_median,
  dm_vq3: dm.value_q3,   dm_vmax: dm.value_max
}) AS rows
RETURN
  size(rows) AS total_matching,
  size(apoc.coll.toSet([x IN rows | x.dm_id])) AS total_derived_metrics,
  size(apoc.coll.toSet([x IN rows | x.lt])) AS total_genes,
  apoc.coll.frequencies([x IN rows | x.org])  AS by_organism,
  apoc.coll.frequencies([x IN rows | x.comp]) AS by_compartment,
  apoc.coll.frequencies([x IN rows | x.doi])  AS by_publication,
  apoc.coll.frequencies([x IN rows | x.exp])  AS by_experiment,
  apoc.coll.frequencies([x IN rows | x.cat])  AS top_categories_raw,
  // Per-DM rollup with filtered-slice stats + full-DM context
  [dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |
    {derived_metric_id: dm_id,
     name:        head([x IN rows WHERE x.dm_id = dm_id | x.dm_name]),
     metric_type: head([x IN rows WHERE x.dm_id = dm_id | x.mt]),
     value_kind:  head([x IN rows WHERE x.dm_id = dm_id | x.vk]),
     count:       size([x IN rows WHERE x.dm_id = dm_id]),
     value_min:    apoc.coll.min([x IN rows WHERE x.dm_id = dm_id | x.value]),
     value_max:    apoc.coll.max([x IN rows WHERE x.dm_id = dm_id | x.value]),
     value_median: apoc.coll.sort([x IN rows WHERE x.dm_id = dm_id | x.value])
                     [toInteger(size([x IN rows WHERE x.dm_id = dm_id]) / 2)],
     // q1/q3 via sorted-list index (mirrors median pattern; api/ may
     // refine to true-quartile interpolation if needed):
     value_q1: apoc.coll.sort([x IN rows WHERE x.dm_id = dm_id | x.value])
                 [toInteger(size([x IN rows WHERE x.dm_id = dm_id]) * 0.25)],
     value_q3: apoc.coll.sort([x IN rows WHERE x.dm_id = dm_id | x.value])
                 [toInteger(size([x IN rows WHERE x.dm_id = dm_id]) * 0.75)],
     // Full-DM stats from precomputed DM-node props
     dm_value_min:    head([x IN rows WHERE x.dm_id = dm_id | x.dm_vmin]),
     dm_value_q1:     head([x IN rows WHERE x.dm_id = dm_id | x.dm_vq1]),
     dm_value_median: head([x IN rows WHERE x.dm_id = dm_id | x.dm_vmed]),
     dm_value_q3:     head([x IN rows WHERE x.dm_id = dm_id | x.dm_vq3]),
     dm_value_max:    head([x IN rows WHERE x.dm_id = dm_id | x.dm_vmax]),
     // Rank distribution — null on non-rankable rows
     rank_min: apoc.coll.min(
       [x IN rows WHERE x.dm_id = dm_id AND x.rank IS NOT NULL | x.rank]),
     rank_max: apoc.coll.max(
       [x IN rows WHERE x.dm_id = dm_id AND x.rank IS NOT NULL | x.rank])
    }] AS by_metric,
  // Per-DM count distribution → top-level convenience stats
  apoc.coll.max([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |
                 size([x IN rows WHERE x.dm_id = dm_id])]) AS genes_per_metric_max,
  toFloat(apoc.coll.sort([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |
                          size([x IN rows WHERE x.dm_id = dm_id])])
          [toInteger(size(apoc.coll.toSet([x IN rows | x.dm_id])) / 2)])
    AS genes_per_metric_median
```

**WHERE-construction (edge-level filters):**

```
locus_tags        → g.locus_tag IN $locus_tags
min_value         → r.value >= $min_value
max_value         → r.value <= $max_value
min_percentile    → r.metric_percentile >= $min_percentile
max_percentile    → r.metric_percentile <= $max_percentile
bucket            → r.metric_bucket IN $bucket
max_rank          → r.rank_by_metric <= $max_rank
```

All AND-joined. The rankable-gated filters (`min_percentile`, `max_percentile`, `bucket`, `max_rank`) are safe to apply unconditionally here — api/ has already gate-validated and `derived_metric_ids` only contains rankable DMs when one of these filters is in play.

**Verified live (filtered-slice + full-DM stats):** `metric_type=cell_abundance_biovolume_normalized, bucket=top_quartile` → 308 rows; `by_metric` has 2 entries (MIT9312 / MIT9313) with `count` 152 / 156, `value_max` 8.02e-7 / 2.98e-6, `value_median` (filtered top-quartile slice) ≠ `dm_value_median` (full-DM, 7.67e-9 / 1.87e-8). Distinct slice-vs-baseline values confirmed.

**Top-categories cap.** Cypher returns the unsorted full frequency map (`top_categories_raw`); api/ trims to top-5 and renames to `top_categories` (mirrors `genes_in_cluster` Layer-2 pattern at [`api/functions.py`](../../multiomics_explorer/api/functions.py)). Keeps the builder generic.

**`top_categories` empty edge case.** When all genes have `gene_category` null, `coalesce(..., 'Unknown')` ensures a single `Unknown` bucket appears (matches `genes_in_cluster` summary behavior).

### `build_genes_by_numeric_metric` (detail)

```python
def build_genes_by_numeric_metric(
    *,
    derived_metric_ids: list[str],     # gate-validated; never empty when called
    locus_tags: list[str] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_percentile: float | None = None,
    max_percentile: float | None = None,
    bucket: list[str] | None = None,
    max_rank: int | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_numeric_metric.

    Same edge-level filter set as the summary builder. Returns 14 compact
    columns (per-row gene + DM identity + gate echoes + value extras),
    plus 12 verbose columns when verbose=True.

    NOTE: adjusted_p_value, significant declared in Pydantic Result with
    default=None, NOT in current Cypher RETURN — see spec §"Detail mode
    — Pydantic-only forward-compat".

    RETURN keys (compact, 14 columns):
      locus_tag, gene_name, product, gene_category, organism_name,
      derived_metric_id, name, value_kind, rankable, has_p_value,
      value, rank_by_metric, metric_percentile, metric_bucket.

    RETURN keys (verbose adds, 13 in current Cypher):
      metric_type, field_description, unit, compartment, experiment_id,
      publication_doi, treatment_type, background_factors, treatment,
      light_condition, experimental_context,
      gene_function_description, gene_summary.
    """
```

Cypher (verified live with `damping_ratio` + `bucket=top_decile`):

```cypher
MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene]->(g:Gene)
WHERE dm.id IN $derived_metric_ids
  <AND edge-level filter conditions>
RETURN g.locus_tag       AS locus_tag,
       g.gene_name       AS gene_name,
       g.product         AS product,
       g.gene_category   AS gene_category,
       g.organism_name   AS organism_name,
       dm.id             AS derived_metric_id,
       dm.name           AS name,
       dm.value_kind     AS value_kind,
       dm.rankable      = 'true' AS rankable,
       dm.has_p_value   = 'true' AS has_p_value,
       r.value           AS value,
       CASE WHEN dm.rankable = 'true' THEN r.rank_by_metric    ELSE null END AS rank_by_metric,
       CASE WHEN dm.rankable = 'true' THEN r.metric_percentile ELSE null END AS metric_percentile,
       CASE WHEN dm.rankable = 'true' THEN r.metric_bucket     ELSE null END AS metric_bucket
       <verbose RETURN block when verbose=true>
ORDER BY r.rank_by_metric ASC, r.value DESC, dm.id ASC, g.locus_tag ASC
SKIP $offset
LIMIT $limit
```

Verbose RETURN additions (13 columns):

```
,
       dm.metric_type         AS metric_type,
       dm.field_description   AS field_description,
       dm.unit                AS unit,
       dm.compartment         AS compartment,
       dm.experiment_id       AS experiment_id,
       dm.publication_doi     AS publication_doi,
       coalesce(dm.treatment_type, [])     AS treatment_type,
       coalesce(dm.background_factors, []) AS background_factors,
       dm.treatment           AS treatment,
       dm.light_condition     AS light_condition,
       dm.experimental_context AS experimental_context,
       g.function_description AS gene_function_description,
       g.gene_summary         AS gene_summary
```

`p_value` (edge-side) is intentionally absent until a `has_p_value='true'` DM lands. Re-add `,\n       CASE WHEN dm.has_p_value = 'true' THEN r.p_value ELSE null END AS p_value` when that ships.

**Variable scoping.** Single MATCH chain; RETURN reads directly from `r.*`, `dm.*`, `g.*`. No `WITH g, dm, r, properties(r) AS p` projection needed (the 2026-04-26 edge-value unification rebuild made it unnecessary). No UNWIND of intermediate collects. SKIP/LIMIT on a deterministic ORDER BY → stable pagination.

**No DISTINCT.** Each `(dm, r, g)` triple is unique by edge cardinality (one quantifies-edge per DM × Gene). Mirrors `gene_derived_metrics`.

**Verified live** (canonical worked example): `metric_types=['damping_ratio'], bucket=['top_decile']` → 32 rows, sort-key validated:
- Row 1: PMM1545 (rpsH, 30S ribosomal protein S8, Translation), value=25.3, rank=1, percentile=100, bucket=top_decile.
- Row 2: PMM0930 (phdB, pyruvate dehydrogenase E1β, Carbohydrate metabolism), value=23, rank=2, percentile=99.68.
- Row 3: PMM0161 (gltA, citrate synthase, Carbohydrate metabolism), value=21.4, rank=3.
- Tied values (PMM0871 + PMM1610 both 21.3) break by `dm.id` then `g.locus_tag`.

---

## API Function

**File:** `multiomics_explorer/api/functions.py`

```python
def genes_by_numeric_metric(
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    min_percentile: float | None = None,
    max_percentile: float | None = None,
    bucket: list[str] | None = None,
    max_rank: int | None = None,
    significant_only: bool = False,
    max_adjusted_p_value: float | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Numeric DerivedMetric drill-down. Cross-organism by design.

    3-query orchestration:
      1. diagnostics — resolve selection, fetch gate states.
      2. (api/ validates) — value_kind=='numeric' check; rankable / has_p_value
         gate compat; build excluded_derived_metrics + warnings.
      3. summary — aggregations over surviving DM ID list (always runs).
      4. detail — rows; skipped when limit==0.

    Returns dict with envelope + results (see spec §"Summary envelope").

    Raises:
        ValueError: derived_metric_ids+metric_types both/neither set;
                    selected DM has value_kind != 'numeric';
                    rankable-gated filter used and ALL selected DMs
                    rankable=False;
                    has_p_value-gated filter used and ALL selected DMs
                    has_p_value=False.
    """
```

### Implementation flow

1. **Mutual-exclusion check.** `derived_metric_ids` XOR `metric_types`; raise on both/neither.
2. **`summary=True` → `limit=0`.**
3. **Q1: diagnostics.** Run `build_genes_by_numeric_metric_diagnostics(...)` with selection + DM-scoping params. Returns one row per surviving DM with identity + gate flags.
4. **Validate value_kind.** Diagnostics builder hardcodes `dm.value_kind='numeric'` so any DM not in result was either (a) wrong value_kind, (b) didn't pass scoping, or (c) didn't exist. Cross-check input lists:
   - `derived_metric_ids` not in diagnostics result → `not_found_ids` (not in KG) **or** scoped out (api/ can't disambiguate without a second query — for slice 1, surface as `not_found_ids` and document the conflation; future improvement: split via a value_kind-blind lookup).
   - `metric_types` with no DM in diagnostics result → `not_found_metric_types`.
   - Pre-flight: if any `derived_metric_ids` resolves to a wrong-`value_kind` DM, raise — but with the hardcoded `value_kind='numeric'` predicate, those DMs simply don't appear, so we'd need an extra query to detect the case explicitly. **Slice-1 simplification:** they fall into `not_found_ids` (the LLM sees an empty result and consults `list_derived_metrics`); a richer "wrong value_kind" diagnostic can ship in a follow-up.
5. **Validate rankable gate.** If any of `min_percentile, max_percentile, bucket, max_rank` is set:
   - `rankable_dms = [d for d in diagnostics if d['rankable']]`
   - `non_rankable_dms = [d for d in diagnostics if not d['rankable']]`
   - If `not rankable_dms` → `raise ValueError(f"All {len(non_rankable_dms)} selected DMs are non-rankable; cannot apply rankable-gated filter(s) {triggered_filters}. Inspect rankable=true DMs via list_derived_metrics(value_kind='numeric', rankable=True).")`.
   - Else if `non_rankable_dms` → for each: append to `excluded_derived_metrics` with `reason=f"non-rankable; {triggered_filter} filter does not apply"`. Append a single human-readable line to `warnings`.
6. **Validate has_p_value gate.** If any of `significant_only, max_adjusted_p_value` is set:
   - Symmetric two-branch logic. Today every selected DM has `has_p_value=False` → always-raise branch fires.
7. **Build surviving-DM ID list.** `derived_metric_ids = [d['derived_metric_id'] for d in diagnostics if not in excluded_set]`.
8. **Q2: summary.** Run `build_genes_by_numeric_metric_summary(derived_metric_ids=surviving, ...edge_filters)`. **Always runs** (cheap; carries `total_matching`, `excluded_derived_metrics` plumbing, etc.).
9. **Top-categories cap + rename.** `top_categories = sorted(top_categories_raw, key=lambda x: x['count'], reverse=True)[:5]`; rename frequency keys (`item` → `gene_category`). Mirrors `genes_in_cluster` Layer-2 pattern.
10. **`by_metric` post-processing.** Sort by `count` desc (Cypher set-iteration order is non-deterministic). Filter the entry's `dm_value_*` columns to null when DM is non-rankable in mixed-rankable result sets — they're computed regardless, but if the DM has `rankable=False` and `dm_value_*` props are populated (post-rebuild), they're still meaningful (full distribution doesn't depend on rankability).
11. **Q3: detail.** Skipped when `limit==0`. Otherwise `build_genes_by_numeric_metric(derived_metric_ids=surviving, ...edge_filters, verbose, limit, offset)`.
12. **Build envelope dict.** All keys present (defaults: empty list / None / 0 / False). `truncated = total_matching > offset + len(results)`.
13. **Frequency-list rename to nested `{<key>, count}` shape.** Mirrors `gene_derived_metrics` `_rename_freq` pattern:
    - `by_organism` → `{organism_name, count}`
    - `by_compartment` → `{compartment, count}`
    - `by_publication` → `{publication_doi, count}`
    - `by_experiment` → `{experiment_id, count}`
    - `top_categories_raw` → top-5 `{gene_category, count}`
    - `by_metric` is **already shaped** (per-DM dicts with all stats) — no rename, just sort.

### `not_matched_*` field semantics

- `not_matched_ids` (from `derived_metric_ids`): IDs that survived diagnostics + gate validation but produced 0 rows after edge-level filters in summary. Computed as `set(surviving_dms_after_gate) - set(by_metric[i].derived_metric_id for ...)`.
- `not_matched_metric_types` (from `metric_types`): tags whose every DM either fell into `excluded_derived_metrics` OR produced 0 rows. Computed by walking diagnostics input → DM IDs → row contribution.
- `not_matched_organism`: set when `organism` was provided AND no row in `by_organism` matches the requested organism (case-insensitive). Mirrors `genes_in_cluster.not_matched_organism` semantics.

### Wire exports

Add `genes_by_numeric_metric` to:
- `multiomics_explorer/api/__init__.py` `__all__`
- `multiomics_explorer/__init__.py` `__all__`

---

## MCP Wrapper

**File:** `multiomics_explorer/mcp_server/tools.py`

Pydantic models defined inside `register_tools(mcp)` (mirrors prior tools):

```python
# ── Breakdown models (one per by_* dimension) ───────────────────────

class GenesByNumericMetricOrganismBreakdown(BaseModel):
    organism_name: str = Field(description="Organism (e.g. 'Prochlorococcus MED4').")
    count: int = Field(description="Rows from this organism in current result.")

class GenesByNumericMetricCompartmentBreakdown(BaseModel):
    compartment: str = Field(description="Sample compartment.")
    count: int = Field()

class GenesByNumericMetricPublicationBreakdown(BaseModel):
    publication_doi: str = Field()
    count: int = Field()

class GenesByNumericMetricExperimentBreakdown(BaseModel):
    experiment_id: str = Field()
    count: int = Field()

class GenesByNumericMetricCategoryBreakdown(BaseModel):
    gene_category: str = Field(description="Gene functional category.")
    count: int = Field()

class GenesByNumericMetricBreakdown(BaseModel):
    """Per-DM rollup: filtered-slice value distribution + full-DM context."""
    derived_metric_id: str = Field(description="Unique DM id.")
    name: str = Field(description="DM human label.")
    metric_type: str = Field(description="Category tag.")
    value_kind: Literal["numeric"] = Field(
        description="Always 'numeric' in this tool; kept for cross-tool "
                    "row-shape consistency.")
    count: int = Field(description="Rows contributed by this DM after filters.")
    # Filtered slice (query-time)
    value_min: float | None = Field(default=None, description="Min `r.value` in filtered slice.")
    value_q1: float | None = Field(default=None, description="Q1 of `r.value` in filtered slice.")
    value_median: float | None = Field(default=None, description="Median.")
    value_q3: float | None = Field(default=None, description="Q3.")
    value_max: float | None = Field(default=None, description="Max.")
    # Full DM (precomputed dm.value_*)
    dm_value_min: float | None = Field(default=None,
        description="Full-DM min (precomputed `dm.value_min`). Always "
                    "populated for numeric DMs after the 2026-04-26 KG rebuild.")
    dm_value_q1: float | None = Field(default=None,
        description="Full-DM Q1 (precomputed `dm.value_q1`).")
    dm_value_median: float | None = Field(default=None,
        description="Full-DM median (precomputed `dm.value_median`).")
    dm_value_q3: float | None = Field(default=None,
        description="Full-DM Q3 (precomputed `dm.value_q3`).")
    dm_value_max: float | None = Field(default=None,
        description="Full-DM max (precomputed `dm.value_max`).")
    # Rank distribution (filtered, rankable-only)
    rank_min: int | None = Field(default=None,
        description="Min rank in filtered slice. Null on non-rankable DMs.")
    rank_max: int | None = Field(default=None,
        description="Max rank in filtered slice. Null on non-rankable DMs.")

class ExcludedDerivedMetric(BaseModel):
    derived_metric_id: str = Field()
    metric_type: str = Field()
    rankable: bool = Field()
    has_p_value: bool = Field()
    reason: str = Field(description="Human-readable explanation, e.g. "
        "'non-rankable; bucket filter does not apply'.")

# ── Per-row result model ────────────────────────────────────────────

class GenesByNumericMetricResult(BaseModel):
    # Identity / routing (5)
    locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM1545').")
    gene_name: str | None = Field(default=None,
        description="Gene name (e.g. 'rpsH'); null when KG has none.")
    product: str | None = Field(default=None,
        description="Gene product (e.g. '30S ribosomal protein S8').")
    gene_category: str | None = Field(default=None,
        description="Functional category (e.g. 'Translation').")
    organism_name: str = Field(description="Organism (e.g. 'Prochlorococcus MED4').")
    # DM identity (2)
    derived_metric_id: str = Field()
    name: str = Field(description="DM human label.")
    # Gate echoes (3) — sourced from parent DM, coerced to Python bool
    value_kind: Literal["numeric"] = Field()
    rankable: bool = Field(description="Echoed from parent DM; True iff "
        "`rank_by_metric`/`metric_percentile`/`metric_bucket` carry data.")
    has_p_value: bool = Field(description="Echoed from parent DM; True iff "
        "`adjusted_p_value`/`significant` carry data (none in current KG).")
    # Numeric value (4)
    value: float = Field(description="Measurement value.")
    rank_by_metric: int | None = Field(default=None,
        description="Rank by value (1=highest). Populated only when "
                    "rankable=True.")
    metric_percentile: float | None = Field(default=None,
        description="Percentile (0–100). Same gate as rank_by_metric.")
    metric_bucket: str | None = Field(default=None,
        description="Bucket label (top_decile / top_quartile / mid / low). "
                    "Same gate.")
    # Pydantic-only forward-compat (2; not in current Cypher RETURN)
    adjusted_p_value: float | None = Field(default=None,
        description="BH-adjusted p-value. Populated only when "
                    "has_p_value=True. None in current KG.")
    significant: bool | None = Field(default=None,
        description="Significance flag. Same gate as adjusted_p_value.")
    # ── Verbose adds (default None / [] when verbose=False) ──────────
    metric_type: str | None = Field(default=None, description="Category tag. Verbose only.")
    field_description: str | None = Field(default=None, description="Verbose only.")
    unit: str | None = Field(default=None, description="Measurement unit. Verbose only.")
    compartment: str | None = Field(default=None, description="Verbose only.")
    experiment_id: str | None = Field(default=None, description="Verbose only.")
    publication_doi: str | None = Field(default=None, description="Verbose only.")
    treatment_type: list[str] = Field(default_factory=list, description="Verbose only.")
    background_factors: list[str] = Field(default_factory=list, description="Verbose only.")
    treatment: str | None = Field(default=None, description="Verbose only.")
    light_condition: str | None = Field(default=None, description="Verbose only.")
    experimental_context: str | None = Field(default=None, description="Verbose only.")
    gene_function_description: str | None = Field(default=None, description="Verbose only.")
    gene_summary: str | None = Field(default=None, description="Verbose only.")
    p_value: float | None = Field(default=None,
        description="Raw p-value; gated on has_p_value=True. Verbose only. "
                    "None in current KG.")

# ── Envelope ────────────────────────────────────────────────────────

class GenesByNumericMetricResponse(BaseModel):
    total_matching: int = Field(description="Rows after all filters + gate exclusion.")
    total_derived_metrics: int = Field(description="Distinct DMs contributing rows.")
    total_genes: int = Field(description="Distinct genes in results.")
    by_organism: list[GenesByNumericMetricOrganismBreakdown] = Field(default_factory=list)
    by_compartment: list[GenesByNumericMetricCompartmentBreakdown] = Field(default_factory=list)
    by_publication: list[GenesByNumericMetricPublicationBreakdown] = Field(default_factory=list)
    by_experiment: list[GenesByNumericMetricExperimentBreakdown] = Field(default_factory=list)
    by_metric: list[GenesByNumericMetricBreakdown] = Field(default_factory=list,
        description="Per-DM rollup: filtered-slice value distribution + "
                    "full-DM context. Sorted by count desc.")
    top_categories: list[GenesByNumericMetricCategoryBreakdown] = Field(default_factory=list,
        description="Top 5 gene categories by count.")
    genes_per_metric_max: int = Field(default=0,
        description="Largest per-DM gene count.")
    genes_per_metric_median: float = Field(default=0.0,
        description="Median per-DM gene count.")
    not_found_ids: list[str] = Field(default_factory=list,
        description="`derived_metric_ids` inputs not present in KG.")
    not_matched_ids: list[str] = Field(default_factory=list,
        description="`derived_metric_ids` in KG but produced 0 rows after "
                    "edge-level filters (excludes gate-excluded DMs).")
    not_found_metric_types: list[str] = Field(default_factory=list,
        description="`metric_types` inputs that match no DM after scoping.")
    not_matched_metric_types: list[str] = Field(default_factory=list,
        description="`metric_types` whose DMs produced 0 rows.")
    not_matched_organism: str | None = Field(default=None,
        description="`organism` arg that matched no surviving DM.")
    excluded_derived_metrics: list[ExcludedDerivedMetric] = Field(default_factory=list,
        description="DMs dropped by rankable / has_p_value gate. Always "
                    "present (empty list when no exclusions).")
    warnings: list[str] = Field(default_factory=list,
        description="Human-readable summary of excluded_derived_metrics.")
    returned: int = Field(description="Length of results list.")
    offset: int = Field(default=0, description="Pagination offset used.")
    truncated: bool = Field(description="True when total_matching > offset + returned.")
    results: list[GenesByNumericMetricResult] = Field(default_factory=list,
        description="One row per gene × DM. Empty when summary=True.")
```

**Wrapper body:** `await ctx.info(...)`, call `api.genes_by_numeric_metric`, build each breakdown list (and `results`) into **new local variables** (don't mutate the api/ return dict — see `add-or-update-tool` checklist gotcha). Construct `GenesByNumericMetricResponse(...)` with explicit kwargs. `ToolError` on `ValueError`. ctx.info / ctx.warning messages mirror `gene_derived_metrics` style — log a brief summary on entry (selection size, gate-filter presence) and a warning when `excluded_derived_metrics` is non-empty.

---

## Tests

### Unit: `tests/unit/test_query_builders.py`

`TestBuildGenesByNumericMetricDiagnostics`:

- `test_metric_types_filter` — `dm.metric_type IN $metric_types` clause + param.
- `test_derived_metric_ids_filter` — `dm.id IN $derived_metric_ids` clause.
- `test_value_kind_hardcoded` — `dm.value_kind = 'numeric'` always present in WHERE.
- `test_returns_canonical_columns` — exactly 8 RETURN columns: derived_metric_id, metric_type, value_kind, name, rankable, has_p_value, total_gene_count, organism_name.
- `test_organism_filter` — uses space-split CONTAINS pattern from `_list_derived_metrics_where`.
- `test_compartment_filter` — `dm.compartment = $compartment` exact-match.
- `test_treatment_type_lower` / `test_background_factors_lower` — case-insensitive ANY-overlap.
- `test_combined_filters` — AND-joined.
- `test_order_by` — `dm.id ASC`.

`TestBuildGenesByNumericMetricSummary`:

- `test_minimal_call` — `derived_metric_ids` only, no edge filters; bare MATCH + WHERE on `dm.id IN`.
- `test_locus_tags_filter`, `test_min_max_value`, `test_min_max_percentile`, `test_bucket_filter`, `test_max_rank` — each adds the expected clause + param.
- `test_combined_edge_filters` — multiple filters AND-joined.
- `test_returns_expected_envelope_columns` — total_matching, total_derived_metrics, total_genes + 5 frequency-style breakdowns + by_metric (richly shaped) + top_categories_raw + genes_per_metric_max + genes_per_metric_median.
- `test_by_metric_shape` — `by_metric` projection includes per-DM dict with `derived_metric_id, name, metric_type, value_kind, count, value_min, value_q1, value_median, value_q3, value_max, dm_value_min, dm_value_q1, dm_value_median, dm_value_q3, dm_value_max, rank_min, rank_max`.
- `test_dm_value_props_in_return` — RETURN references all 5 precomputed DM-distribution props (`dm.value_min, dm.value_q1, dm.value_median, dm.value_q3, dm.value_max`); the rollup landed 2026-04-26, so these resolve to floats at query time on every numeric DM. Asserts the 5 prop reads appear in the Cypher string.
- `test_value_median_via_sorted_index` — RETURN computes `value_median` via `apoc.coll.sort(values)[size/2]` (not `percentileCont`, since this is post-collect not pre-collect aggregation).
- `test_rank_min_max_filter_nulls` — RETURN's `rank_min` / `rank_max` filter to `x.rank IS NOT NULL` so non-rankable DMs cleanly produce null instead of non-min comparisons.

`TestBuildGenesByNumericMetric` (detail):

- `test_returns_expected_compact_columns` — exactly **14** compact RETURN columns. Slice-spec compact total is 22 (16 shared drill-down columns + 6 numeric extras incl. `adjusted_p_value` / `significant`). Trim: 6 fields moved to verbose (`metric_type`, `compartment`, `experiment_id`, `publication_doi`, `treatment_type`, `background_factors`) + 2 fields Pydantic-only forward-compat (`adjusted_p_value`, `significant`) → 22 − 8 = 14. Asserts the 6 verbose-moved fields and the 2 forward-compat fields are absent from compact RETURN.
- `test_value_is_direct_r_access` — RETURN contains `r.value AS value` (single column).
- `test_rankable_case_gates` — `rank_by_metric`, `metric_percentile`, `metric_bucket` all wrapped in `CASE WHEN dm.rankable = 'true' …`.
- `test_has_p_value_columns_deferred` — RETURN does **not** contain `adjusted_p_value` / `significant` today.
- `test_p_value_deferred_in_verbose` — verbose RETURN does **not** contain `r.p_value` today.
- `test_rankable_has_p_value_coerced` — RETURN includes `dm.rankable = 'true' AS rankable` and `dm.has_p_value = 'true' AS has_p_value` (Python bool coercion).
- `test_verbose_adds_columns` — verbose path appends 13 fields: metric_type, field_description, unit, compartment, experiment_id, publication_doi, treatment_type, background_factors, treatment, light_condition, experimental_context, gene_function_description, gene_summary. Asserts `p_value` is **not** in the verbose RETURN today (Pydantic-only forward-compat).
- `test_order_by` — `r.rank_by_metric ASC, r.value DESC, dm.id ASC, g.locus_tag ASC`.
- `test_limit_offset` — SKIP / LIMIT only when set.

### Unit: `tests/unit/test_api_functions.py::TestGenesByNumericMetric`

Mocked `GraphConnection`. Cover (mirrors `gene_derived_metrics` + `genes_in_cluster` patterns):

- envelope shape (~20 envelope keys + results),
- mutual-exclusion `derived_metric_ids` XOR `metric_types` (both → ValueError, neither → ValueError),
- `summary=True` → `limit=0`; detail query NOT called; `results==[]`,
- 3-query orchestration: assert call sequence diagnostics → summary → detail (or only first two when summary=True),
- gate-validation flow (mocked diagnostics result):
  - all-rankable + bucket → no exclusions, no warnings.
  - mixed rankable + bucket → soft-exclude non-rankable into `excluded_derived_metrics`, populate `warnings`.
  - all non-rankable + bucket → `ValueError` with offending DM list.
  - any has_p_value-gated filter against today's mock (all has_p_value=False) → `ValueError`.
- `not_found_ids` plumbing (input `derived_metric_ids` not in diagnostics result),
- `not_found_metric_types` plumbing,
- `not_matched_organism` (organism arg set, no surviving DM matches),
- `top_categories` capped at 5,
- `by_metric` sorted by `count` desc,
- frequency-list rename (`item` → semantic key) for the 4 freq breakdowns,
- `truncated` arithmetic (3 cases: full / partial / empty).

### Unit: `tests/unit/test_tool_wrappers.py::TestGenesByNumericMetricWrapper`

- update `EXPECTED_TOOLS`,
- `test_returns_response_envelope`,
- `test_excluded_dm_envelope_field` — Pydantic accepts list[ExcludedDerivedMetric] including empty list,
- `test_warnings_default_empty`,
- `test_summary_empty_results`,
- `test_value_error_to_tool_error`.

### Integration (KG, `@pytest.mark.kg`): `tests/integration/test_mcp_tools.py::TestGenesByNumericMetric`

Baselines pinned to 2026-04-26 KG state; refresh when new DMs land or per-DM distribution rebuild changes precomputed stats.

- `test_damping_ratio_top_decile` — `metric_types=['damping_ratio'], bucket=['top_decile']` → 32 rows; sort key validated; `total_genes==32`; `by_metric[0]` = damping_ratio with `count=32, value_min≈12.2, value_median≈15.9, value_max=25.3, rank_min=1, rank_max=32`.
- `test_top_decile_full_dm_context` — same call, asserts `by_metric[0]` carries the full-DM precomputed stats: `dm_value_min≈0.2, dm_value_q1≈2.8, dm_value_median≈4.9, dm_value_q3≈7.8, dm_value_max=25.3`. Confirms slice ⊂ baseline (filtered median 15.9 ≫ full-DM median 4.9). Verified live 2026-04-26 post-rebuild.
- `test_mixed_rankable_soft_exclude` — `metric_types=['damping_ratio','peak_time_protein_h'], bucket=['top_decile']` → 32 rows from damping_ratio only; `excluded_derived_metrics` has 1 entry (`derived_metric_id` ending `peak_time_protein_h`, `rankable=False`, `reason` mentions `bucket`); `warnings` has 1 line.
- `test_all_non_rankable_hard_fail` — `metric_types=['peak_time_transcript_h'], bucket=['top_decile']` → raises `ValueError`; error message lists the DM's `rankable=False` state and the offending filter.
- `test_p_value_filter_hard_fail_today` — `metric_types=['damping_ratio'], significant_only=True` → `ValueError`; intentional today (0/15 has_p_value).
- `test_max_rank_top_n` — `metric_types=['damping_ratio'], max_rank=5` → 5 rows, ranks 1–5.
- `test_min_value_threshold_non_rankable` — `metric_types=['mascot_identification_probability'], organism='MED4', min_value=99` → rows where mascot probability ≥ 99 (raw threshold; non-rankable DM, but `min_value` doesn't gate).
- `test_cross_organism_no_scope` — `metric_types=['cell_abundance_biovolume_normalized'], bucket=['top_quartile']` → 308 rows; `by_organism` has 2 entries (MIT9312 152, MIT9313 156); `by_metric` has 2 DMs; `not_matched_organism is None`.
- `test_cross_organism_with_scope` — same call + `organism='MIT9313'` → 156 rows; `by_organism` has 1 entry; `not_matched_organism is None`.
- `test_locus_tags_intersection` — pick top-5 ranked damping_ratio genes via prior call → re-call with `locus_tags=[those 5]` → 5 rows.
- `test_summary_only` — `metric_types=['damping_ratio'], bucket=['top_decile'], summary=True` → `results==[]`; envelope fully populated; `truncated=True` (since total_matching=32, returned=0).
- `test_truncation_pagination` — `metric_types=['damping_ratio'], limit=10` → `returned=10, truncated=True, total_matching=312`; second call with `offset=10, limit=10` → next 10 rows by sort key.
- `test_verbose_columns` — `metric_types=['damping_ratio'], limit=1, verbose=True` → row has `metric_type, unit, compartment, experiment_id, treatment, light_condition, experimental_context, gene_function_description, gene_summary`; `p_value is None`.
- `test_by_metric_filtered_vs_full_dm` — `metric_types=['damping_ratio'], bucket=['top_decile']` → `by_metric[0].value_min ≈ 12.2` (filtered), `by_metric[0].dm_value_min ≈ 0.2` (full DM, precomputed); `by_metric[0].value_max == by_metric[0].dm_value_max == 25.3` (slice's max is the DM's max — top-decile includes the global maximum). Verified live 2026-04-26.

### Contract: `tests/integration/test_api_contract.py::TestGenesByNumericMetricContract`

Per `add-or-update-tool` checklist: api/ return shape changes need a contract test. Pin all envelope keys (~20) + the union of compact/verbose result keys + per-`by_metric`-entry shape (15 fields, including post-rebuild `dm_value_*`). Fails fast on accidental shape drift.

### Correctness: `tests/integration/test_tool_correctness_kg.py`

Add `TestBuildGenesByNumericMetricCorrectnessKG` if the file uses per-builder classes — exercise live KG with fixed input, assert column presence + types. Skip if pattern doesn't apply.

### Regression: `tests/evals/cases.yaml` + both `TOOL_BUILDERS` dicts

Two registration sites — both must be updated:

- `tests/evals/test_eval.py` — add `"genes_by_numeric_metric": build_genes_by_numeric_metric` to `TOOL_BUILDERS`.
- `tests/regression/test_regression.py` — add the same. Builders register the **detail builder** (the summary builder is a separate convention — see `gene_derived_metrics` precedent for builder-name suffix).

Add 4 representative cases to `tests/evals/cases.yaml`:
- single-DM top-decile
- mixed-rankable soft-exclude
- cross-organism (no scope)
- summary-only

Regenerate baselines: `pytest tests/regression/ --force-regen -m kg`.

### About-content tests

Per the `add-or-update-tool` skill:

- `pytest tests/unit/test_about_content.py -v` — Pydantic ↔ generated markdown consistency.
- `pytest tests/integration/test_about_examples.py -v` — YAML examples execute against live KG.

---

## About Content

**File:** `multiomics_explorer/inputs/tools/genes_by_numeric_metric.yaml`

Per the slice spec §"Required `mistakes` + `chaining` coverage":

- `chaining:` — required entries:
  - `"list_derived_metrics(value_kind='numeric', rankable=True) → genes_by_numeric_metric(derived_metric_ids=[...], bucket=[...])"` — discover-then-drill pattern.
  - `"differential_expression_by_gene → top hits → genes_by_numeric_metric(metric_types=[...], locus_tags=hits)"` — DE follow-up.
  - `"genes_by_numeric_metric → gene_overview(locus_tags=results)"` — drill-down then routing.
- `mistakes:` — required first bullet (slice spec §"Required `mistakes` + `chaining` coverage"):
  - *Non-rankable DM + rankable-gated filter.* "Calling with `metric_types=['peak_time_transcript_h']` + `bucket=['top_decile']` raises — `peak_time_transcript_h` is non-rankable. Inspect `list_derived_metrics(value_kind='numeric', rankable=True)` to see which DMs support `bucket` / `min_percentile` / `max_percentile` / `max_rank`. Mixed rankable/non-rankable DM sets don't raise — instead the envelope's `excluded_derived_metrics` + `warnings` pinpoint the excluded ones."
  - *P-value filter on current KG.* "`significant_only=True` or `max_adjusted_p_value=0.05` raises today because no DM has `has_p_value='true'`. The surface exists for future DMs; check `list_derived_metrics(has_p_value=True)` first."
  - *Sparse columns in results.* "`rank_by_metric` / `metric_percentile` / `metric_bucket` are null in rows from non-rankable DMs (e.g. `peak_time_*_h`); don't treat null as missing data — it's gate-driven. Per-row `rankable` (echoed from the parent DM) tells you which to expect."
  - *Cross-organism by default.* "No single-organism enforcement. `metric_types=['cell_abundance_biovolume_normalized']` returns rows from MIT9312 AND MIT9313 (the same metric_type spans both). Use `organism='MIT9312'` to scope; check per-row `organism_name` and envelope `by_organism` for cross-strain rows."
  - *`by_metric` is per-DM, not per-tag.* "Each `by_metric` entry is one DerivedMetric (uniquely identified by `derived_metric_id`). The same `metric_type` tag can appear across organisms (4 such tags in current KG). Use the per-DM rollup to disambiguate."
  - *Wrong-`value_kind` IDs land in `not_found_ids`, not a typed error.* "Passing a `derived_metric_ids` of a boolean or categorical DM today produces `not_found_ids=[that_id]` rather than a `value_kind` mismatch error — the diagnostics query hardcodes `value_kind='numeric'`, so non-numeric DMs simply don't appear in the result. Inspect via `list_derived_metrics(derived_metric_ids=[...])` to see the DM's actual `value_kind` and pivot to `genes_by_boolean_metric` or `genes_by_categorical_metric`. Slice-1 simplification — a richer 'wrong value_kind' diagnostic ships in a follow-up."
  - *Filtered slice vs full DM.* "`by_metric[i].value_*` describes rows that survived your filters. `by_metric[i].dm_value_*` describes the full DM (precomputed). They're different — your top-decile slice is intentionally narrower than the full DM range."
- `examples:` — at minimum:
  - `genes_by_numeric_metric(metric_types=['damping_ratio'], bucket=['top_decile'])` — canonical worked example, 32 rows.
  - `genes_by_numeric_metric(metric_types=['damping_ratio','peak_time_protein_h'], bucket=['top_decile'])` — soft-exclude scenario; show envelope `excluded_derived_metrics` + `warnings`.
  - `genes_by_numeric_metric(metric_types=['cell_abundance_biovolume_normalized'], bucket=['top_quartile'])` — cross-organism (308 rows from MIT9312 + MIT9313).
  - `genes_by_numeric_metric(metric_types=['damping_ratio'], summary=True)` — summary-only; `by_metric` populated.
  - Multi-step chain: `differential_expression_by_gene` → top 20 hits → `genes_by_numeric_metric(metric_types=['damping_ratio'], locus_tags=hits)` → which DE hits also lead the damping_ratio distribution.
- `verbose_fields:` — `metric_type, field_description, unit, compartment, experiment_id, publication_doi, treatment_type, background_factors, treatment, light_condition, experimental_context, gene_function_description, gene_summary, p_value`.

Pydantic docstring first line (per slice spec §S2 preamble hoist) lands **gate awareness** — the most common LLM footgun is using a rankable-gated filter on a non-rankable DM. The full first-line text is in §"Tool Signature" above.

### Build the about markdown

```bash
uv run python scripts/build_about_content.py genes_by_numeric_metric
```

**Output:** `multiomics_explorer/skills/multiomics-kg-guide/references/tools/genes_by_numeric_metric.md`

### Verify

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -v
```

---

## Documentation Updates

| File | What to update |
|---|---|
| `CLAUDE.md` | Add row to MCP Tools table — purpose: "Drill-down on `Derived_metric_quantifies_gene` (numeric DM family). Edge filters: raw-value threshold (always available), bucket / percentile / rank (rankable-gated, soft-exclude on mixed input), p-value (has_p_value-gated; raises today). Cross-organism by design. `by_metric` envelope pairs filtered-slice value distribution with full-DM context (precomputed)." |
| [`docs/superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md`](../superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md) | Light edit to "Tool 3" section once this spec is approved — reference back to this file for verified Cypher + the `by_metric` shape change (was `by_metric_type`). |
