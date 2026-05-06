# Tool spec: Phase 5 — Greenfield assay tools (slice scope)

**Date:** 2026-05-05.
**Status:** **FROZEN 2026-05-06** — Phase 1 complete. Step 1 (scope) closed via D1–D8. Step 2 (KG verification) inline §3. Step 3 (Cypher × 8) verified live and inlined §12. Pre-split review against `layer-rules` + `add-or-update-tool` + field-rubric incorporated. **Split into per-ship frozen specs 2026-05-06**:

- [docs/tool-specs/list_metabolite_assays.md](list_metabolite_assays.md) — Tool 1, Mode A single-tool deep build (ships first).
- [docs/tool-specs/metabolites_by_assay.md](metabolites_by_assay.md) — Mode B 3-tool slice covering `metabolites_by_quantifies_assay` + `metabolites_by_flags_assay` + `assays_by_metabolite` (ships after Tool 1 lands).

This parent doc remains the canonical reference for KG verification (§3), tested-absent invariant (§10), cross-tool conventions (§11), verified Cypher (§12), and Phase 2 deliverables (§13). The per-ship specs link back here for those.
**Roadmap:** [docs/superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md §3 Phase 5](../superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md).
**Audit driver:** [docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md Part 3b §§3b.1, 3b.3a–3b.3c](../superpowers/specs/2026-05-04-metabolites-surface-audit.md).
**Mirror reference (DM pipeline):**
- [docs/tool-specs/list_derived_metrics.md](list_derived_metrics.md) → `list_metabolite_assays`
- [docs/tool-specs/genes_by_numeric_metric.md](genes_by_numeric_metric.md) → `metabolites_by_quantifies_assay`
- [docs/tool-specs/genes_by_boolean_and_categorical_metric.md](genes_by_boolean_and_categorical_metric.md) (boolean half) → `metabolites_by_flags_assay`
- [docs/tool-specs/gene_derived_metrics.md](gene_derived_metrics.md) → `assays_by_metabolite`
- [docs/superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md](../superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md) — DM-family design spec (shared invariants, gate logic, envelope conventions)
**add-or-update-tool mode:** **B** — slice names ≥ 2 tools (4). Phase 1 is light (no KG iteration; release shipped earlier — verification confirms readiness). Phase 2 briefings will use one entity per agent for `list_metabolite_assays` and a Mode-B template "do the numeric drill-down first, extend pattern to boolean and reverse-lookup" for the 3-tool drill-down slice.

---

## 1. Purpose

Close the Track-B (measurement-anchored) workflow gap by surfacing the four `MetaboliteAssay`-anchored tools that mirror the DM pipeline:

| New tool | DM analog | Role |
|---|---|---|
| `list_metabolite_assays` | `list_derived_metrics` | Discovery / pre-flight for drill-downs |
| `metabolites_by_quantifies_assay` | `genes_by_numeric_metric` | Numeric drill-down (concentration / intensity edges) |
| `metabolites_by_flags_assay` | `genes_by_boolean_metric` | Boolean drill-down (presence / detection edges) |
| `assays_by_metabolite` | `gene_derived_metrics` | Batch reverse-lookup, polymorphic across edge types |

The DM pipeline's structure (entity → edge fan-out, value_kind branching, rankable gating, summary envelope shape) maps **almost 1:1** because the KG modellers built `MetaboliteAssay` as a structural twin of `DerivedMetric` (audit §1.2 + §4.3.1 resolution).

## 2. Out of scope

- `metabolite_response_profile` (analog of `gene_response_profile`) — DEFER per audit §3b.2 (premature at 10-assay scale).
- `differential_metabolite_abundance` — DEFER per audit §3b.4 (FC-shaped surface; may never be needed).
- DM-family extension to `Metabolite` — NOT-NEEDED per audit §3b.5 (Assay IS the DM analog).
- No categorical assay edge in current KG — only numeric (`Assay_quantifies_metabolite`) + boolean (`Assay_flags_metabolite`). No `metabolites_by_categorical_assay` in this slice (and no analog needed).

## 3. KG verification (Step 2 — closed 2026-05-05)

Verified live against the rebuilt KG (post-2026-05-05). All node / edge / index requirements present.

### 3.1 `MetaboliteAssay` node

- **10 nodes** total — 4 organisms (MED4, MIT9303, NATL2A, MIT9301), 2 papers (`10.1073/pnas.2213271120`, `10.1128/mSystems.01261-22`), 8 experiments.
- **value_kind / rankable distribution:**
  - `numeric` + `rankable="true"` × 8 (5 whole_cell + 3 extracellular)
  - `boolean` + `rankable="false"` × 2 (whole_cell)
- All `omics_type = "METABOLOMICS"`.
- `rankable` and (per edge) `flag_value` are **string-typed booleans** (`"true"` / `"false"`) — same convention as DM. API layer coerces at boundaries.
- **Node properties (26 — full list verified):** `aggregation_method, background_factors, compartment, experiment_id, experimental_context, field_description, growth_phases, id, light_condition, metric_type, name, omics_type, organism_name, preferred_id, publication_doi, rankable, total_metabolite_count, treatment, treatment_type, unit, value_kind, value_max, value_median, value_min, value_q1, value_q3`.
- **Δ vs audit row schema:** audit listed 24 properties; live KG adds `preferred_id` (xref-routing hint) — surface in row schema. (Audit's `time_points` row field stays as edge aggregation, not a node property.)

### 3.2 Edges

- `Assay_quantifies_metabolite` (numeric arm) — **1,200 edges**, 15 properties: `id, metric_type, condition_label, time_point, time_point_order, time_point_hours, value, value_sd, n_replicates, n_non_zero, metric_percentile, replicate_values, detection_status, rank_by_metric, metric_bucket`.
  - `metric_bucket` distinct values: `top_decile, top_quartile, mid, low` (DM-parallel — same buckets).
  - `detection_status` distinct values: `detected, sporadic, not_detected` (audit §4.3.3 confirms primary headline rollup).
  - `time_point` distinct values: `"4 days", "6 days", ""`. The empty string appears when the **parent experiment is not time-resolved** — `time_point` is an experiment-level dimension propagated to its edges, not a function of the edge type. (Today the only time-resolved metabolomics experiments are Capovilla 2023's chitosan timecourse — 4d / 6d. The boolean arm's experiments happen to be all single-timepoint, but that's empirical, not schema.)
- `Assay_flags_metabolite` (boolean arm) — **186 edges**, 6 properties: `id, metric_type, condition_label, flag_value, n_replicates, n_positive`.
  - `flag_value` distinct values: `"true", "false"` (string-typed, like DM).
- `ExperimentHasMetaboliteAssay` (10 edges, 1:1) and `PublicationHasMetaboliteAssay` (10 edges, 1:1) provide back-pointers; `MetaboliteAssayBelongsToOrganism` (10 edges, 1:1) ditto.

### 3.3 Indexes

- `metaboliteAssayFullText` (FULLTEXT) over **`name, field_description, treatment, experimental_context`** — richer than DM's `derivedMetricFullText` (which covers only `name, field_description`). `list_metabolite_assays` will inherit the wider corpus for free.
- RANGE indexes on `MetaboliteAssay.{compartment, experiment_id, metric_type, organism_name, value_kind}`.
- `Metabolite.{id, kegg_compound_id, chebi_id, hmdb_id, mnxm_id}` RANGE — already used by `list_metabolites`; reused by `assays_by_metabolite`.

### 3.4 Denormalization

`MetaboliteAssay` carries `organism_name`, `experiment_id`, `publication_doi` directly (verified — same as DM). **No `Experiment` / `Publication` / `OrganismTaxon` joins needed for scoping.** Same simplification as `list_derived_metrics`.

### 3.5 Growth state — schema present, data unpopulated (verified 2026-05-06)

Three places growth state could live; one place is reachable, none populated today:

| Location | Field | Live state | Reachable per-edge? |
|---|---|---|---|
| `Assay_quantifies_metabolite` edge | (none) | — | not on edge |
| `Assay_flags_metabolite` edge | (none) | — | not on edge |
| `MetaboliteAssay` node | `growth_phases: list[str]` | `[]` on all 10 assays | row-level only |
| `Experiment` node | `time_point_growth_phases: list[str]` (parallel-indexed with `time_point_order`) | `[]` on all 5 metabolomics experiments sampled | yes, via `(a)<-[:ExperimentHasMetaboliteAssay]-(e)` + `e.time_point_growth_phases[r.time_point_order]` |

**Implication:** the surface for per-timepoint growth state already exists in the schema (Experiment-side), but the array is empty for every metabolomics experiment in today's KG. The DM family has the same shape (`dm.growth_phases` — populated for some Biller DMs, empty for Waldbauer) and tools surface it as forward-compat. Same convention applies here.

**KG-side ask (proposed, see §5 D8):** backfill `Experiment.time_point_growth_phases` for metabolomics experiments. Until then, `growth_phase` on numeric drill-down rows is `null`. **Surface decision = D8.**

---

## 4. Per-tool scope

### 4.1 `list_metabolite_assays` (Tool 1)

Discovery surface for `MetaboliteAssay` nodes; pre-flight inspection point for the 3 drill-down tools (`rankable` and `value_kind` gate which drill-down filters apply, mirroring DM).

#### 4.1.1 Tool signature (mirrored from `list_derived_metrics`)

```python
list_metabolite_assays(
    search_text: str | None = None,                      # full-text via metaboliteAssayFullText (4-field index — wider corpus than DM)
    organism: str | None = None,                         # singular (matches list_derived_metrics CONTAINS-style)
    metric_types: list[str] | None = None,
    value_kind: Literal["numeric", "boolean"] | None = None,    # no categorical — assay edges are numeric + boolean only
    compartment: str | None = None,                      # values: whole_cell, extracellular
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    assay_ids: list[str] | None = None,                  # batch-by-id; parallel to derived_metric_ids
    metabolite_ids: list[str] | None = None,             # NEW vs DM — find assays measuring specific compounds (1-hop via Assay_quantifies_metabolite | Assay_flags_metabolite)
    exclude_metabolite_ids: list[str] | None = None,     # set-difference w/ metabolite_ids; cross-tool convention from Phase 2 (list_metabolites, genes_by_metabolite, metabolites_by_gene)
    rankable: bool | None = None,                        # bool at API boundary; coerced to "true"/"false" string before Cypher
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = 20,
    offset: int = 0,
) -> ListMetaboliteAssaysResponse
```

**Filters dropped vs `list_derived_metrics`** (justified):
- `omics_type` — every assay is METABOLOMICS; redundant.
- `has_p_value` — `MetaboliteAssay` has no p-value flag; not applicable.

**Filters added vs `list_derived_metrics`:**
- `metabolite_ids` — only assay-side analog (a DM-on-Gene equivalent doesn't exist because every DM is per-gene by construction; on assays, callers may want "which assays measured glucose").

#### 4.1.2 Per-row (compact)

| Field | Source | DM parallel |
|---|---|---|
| `assay_id` | `a.id` | `derived_metric_id` |
| `name` | `a.name` | `name` |
| `metric_type` | `a.metric_type` | `metric_type` |
| `value_kind` | `a.value_kind` | `value_kind` (no `'categorical'`) |
| `rankable` | `a.rankable` (str→bool coerce) | `rankable` |
| `unit` | `a.unit` | `unit` |
| `field_description` | `a.field_description` | `field_description` (audit KG-MET-001 calls this canonical provenance) |
| `organism_name` | `a.organism_name` | `organism_name` |
| `experiment_id` | `a.experiment_id` | `experiment_id` |
| `publication_doi` | `a.publication_doi` | `publication_doi` |
| `compartment` | `a.compartment` | `compartment` |
| `omics_type` | `a.omics_type` | `omics_type` (always `"METABOLOMICS"`) |
| `treatment_type` | `a.treatment_type` | `treatment_type` |
| `background_factors` | `a.background_factors` (coalesce []) | `background_factors` |
| `growth_phases` | `a.growth_phases` (coalesce []) | `growth_phases` |
| `total_metabolite_count` | `a.total_metabolite_count` | `total_gene_count` |
| `aggregation_method` | `a.aggregation_method` | (assay-specific) |
| `preferred_id` | `a.preferred_id` | (assay-specific xref hint) |
| `value_min / value_q1 / value_median / value_q3 / value_max` | `a.*` | (precomputed; numeric DMs lack these on the node — assays surface them) |
| `timepoints` | `[label IN collect(DISTINCT r.time_point) WHERE label <> "" \| label]` over outgoing `Assay_quantifies_metabolite` edges. Reflects the parent **experiment's** time axis. **Per D3 closure:** strip the `""` sentinel during aggregation; non-temporal experiments yield `[]` rather than `[""]`. Renamed from `time_points` to single-word `timepoints` to match the row-level naming. | (DM has no analog) |
| `detection_status_counts` | per-row rollup `apoc.coll.frequencies(collect(r.detection_status))` over outgoing `Assay_quantifies_metabolite` edges, **only when `value_kind='numeric'`** (sparse on boolean rows). Surfaces the audit §4.3.3 primary-headline summary at discovery time so callers can route to detection-status-rich assays without a drill-down round-trip. | (DM has no analog) |
| `score` | from fulltext (when `search_text`) | `score` |

**Verbose adds:** `treatment, light_condition, experimental_context` (parallel to DM verbose adds; all three present on the node — verified).

#### 4.1.3 Envelope (summary mode, mirrored from DM)

| Field | Source |
|---|---|
| `total_entries` | `count(all MetaboliteAssay)` (unfiltered baseline) |
| `total_matching` | filtered count |
| `by_organism` | apoc frequencies |
| `by_value_kind` | apoc frequencies |
| `by_compartment` | apoc frequencies |
| `top_metric_types` | apoc frequencies sorted desc |
| `by_treatment_type` | apoc frequencies on flattened list |
| `by_background_factors` | apoc frequencies on flattened list |
| `by_growth_phase` | apoc frequencies on flattened list |
| `metabolite_count_total` | `sum(a.total_metabolite_count)` — **cumulative** across matching assays. The same metabolite measured by N assays counts N times. (Per field-rubric clause 7 — name predicts shape: `_total` suffix = cross-row sum, distinct from per-row `total_metabolite_count`. Mirrors `metabolite_count_total` on `genes_by_metabolite`.) For distinct-metabolite counts route to `assays_by_metabolite(metabolite_ids=..., summary=True)` (returns `metabolites_matched`) or `list_metabolites(metabolite_ids=...)`. |
| `by_detection_status` | apoc frequencies over `Assay_quantifies_metabolite` edges of matching numeric assays (rolls the numeric-arm headline summary up to envelope level). Empty `[]` when the matching set is all boolean. |
| `score_max` / `score_median` | when `search_text` set |
| `returned`, `truncated`, `offset` | structural |

`by_omics_type` dropped (constant). `by_compartment_with_metabolite_counts` not in scope (premature; `compartment` filter + per-row `compartment` covers it).

**Sort key:** `score DESC` (when search), then `organism_name ASC, value_kind ASC, id ASC` — matches DM.

---

### 4.2 `metabolites_by_quantifies_assay` (Tool 2)

Numeric drill-down — analog of `genes_by_numeric_metric`. One row per (metabolite × assay-edge).

#### 4.2.1 Tool signature

```python
metabolites_by_quantifies_assay(
    # Selection (required; per D1 closure 2026-05-06 — assay_ids only)
    assay_ids: list[str],                                # required, non-empty
    # Scoping (intersected with selection)
    organism: str | None = None,                         # CONTAINS match
    metabolite_ids: list[str] | None = None,             # restrict to specific metabolites
    exclude_metabolite_ids: list[str] | None = None,     # set-difference cross-tool convention (Phase 2)
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    # Edge-level filters: always-available
    value_min: float | None = None,
    value_max: float | None = None,
    detection_status: list[str] | None = None,           # primary headline filter (audit §4.3.3); values: detected, sporadic, not_detected
    timepoint: list[str] | None = None,                  # exact-match list of LABEL strings (e.g. ["4 days"]); per D3 closure, output column is single-word `timepoint`
    # Edge-level filters: rankable-gated (raise on all-non-rankable; soft-exclude on mixed)
    metric_bucket: list[str] | None = None,              # subset of {top_decile, top_quartile, mid, low}
    metric_percentile_min: float | None = None,
    metric_percentile_max: float | None = None,
    rank_by_metric_max: int | None = None,
    # Structural
    summary: bool = False,
    verbose: bool = False,
    limit: int = 5,
    offset: int = 0,
) -> MetabolitesByQuantifiesAssayResponse
```

No `has_p_value`-gated filters — the boolean `Assay_quantifies_metabolite` schema carries no p-value column. Forward-compat: skip the `significant_only` / `max_adjusted_p_value` block until the KG ships an analog.

#### 4.2.2 Per-row

`metabolite_id, name, value, value_sd, replicate_values, n_replicates, n_non_zero, metric_type, metric_bucket, metric_percentile, rank_by_metric, detection_status, timepoint, timepoint_hours, timepoint_order, growth_phase (sparse — see D8), condition_label, assay_id, assay_name (verbose), kegg_compound_id, organism_name, compartment` (last 3 from parent assay node — denormalize for cross-strain self-describing rows). `timepoint*` fields are coerced from edge sentinels per D3 closure (`""` → `None`, `-1.0` → `None`, `0` → `None`). `growth_phase` resolves via `e.time_point_growth_phases[r.time_point_order]` JOIN to the parent Experiment; today returns `null` (array unpopulated for metabolomics experiments — KG-side ask, see §5 D8).

**Tested-absent ≠ unmeasured** (§10): `value = 0` / `n_non_zero = 0` / `detection_status = 'not_detected'` mean the metabolite *was assayed and not found* — that's biology, kept in `results` and counted in `total_matching` + envelope rollups. A *missing row* means the metabolite was *not in this assay's scope* — we have no information. The two states must not be conflated. Filters that strip tested-absent rows (`value_min > 0`, `detection_status` filter that excludes `not_detected`) discard real signal — surface as caller choice, never default-on.

**Verbose adds:** `assay_name, field_description, experimental_context, light_condition, replicate_values` — parallel to DM verbose layer.

#### 4.2.3 Envelope

`total_matching, by_detection_status` (primary headline per audit §4.3.3), `by_metric_bucket, by_assay, by_compartment, by_organism, by_metabolite (top N), excluded_assays, warnings, not_found` — same shape as DM `excluded_derived_metrics` / `warnings`.

**`not_found` is structured** (multi-batch input — `assay_ids` and optional `metabolite_ids`): per the cross-tool convention (Finding B in §11) drill-downs with multiple batch inputs return a typed `NotFound` Pydantic model with one field per batch param: `{assay_ids: [...unknown...], metabolite_ids: [...unknown...]}`. Mirrors `GbmNotFound` on `genes_by_metabolite` and `MetNotFound` on `list_metabolites`.

`by_metric` envelope (audit-style precomputed-vs-filtered pairing): for each selected assay carry `dm_value_min / q1 / median / q3 / max` from the assay node alongside `filtered_value_min / median / max` over the slice — lets callers read "your top-decile slice 0.012–0.16 out of full assay range 0–0.16" inline (mirrors DM's `by_metric` rollup).

#### 4.2.4 Sort key

`r.rank_by_metric ASC NULLS LAST, m.id ASC, a.id ASC, r.time_point_order ASC`. Top-ranked rows first when the assay is rankable (`rank_by_metric=1` is highest); non-rankable assays fall through to `m.id` for deterministic order. Mirrors `genes_by_numeric_metric`'s sort.

#### 4.2.5 Mirror deviation notes

- `metric_percentile` ∈ [0, 100] (verified live — example row had 64.5). Same as DM.

---

### 4.3 `metabolites_by_flags_assay` (Tool 3)

Boolean drill-down — analog of `genes_by_boolean_metric`. One row per (metabolite × flag-edge).

#### 4.3.1 Tool signature

```python
metabolites_by_flags_assay(
    # Selection (required; per D1 closure 2026-05-06 — assay_ids only)
    assay_ids: list[str],                                # required, non-empty
    # Scoping (same block as numeric)
    organism: str | None = None,
    metabolite_ids: list[str] | None = None,
    exclude_metabolite_ids: list[str] | None = None,     # set-difference cross-tool convention (Phase 2)
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    # Edge-level filter: kind-specific
    flag_value: bool | None = None,                      # API → "true"/"false" string for Cypher
    # Structural
    summary: bool = False,
    verbose: bool = False,
    limit: int = 5,
    offset: int = 0,
) -> MetabolitesByFlagsAssayResponse
```

#### 4.3.2 Per-row

`metabolite_id, name, flag_value (bool), n_positive, n_replicates, metric_type, condition_label, assay_id, kegg_compound_id, organism_name, compartment`.

**Verbose adds:** `assay_name, field_description`.

**Tested-absent ≠ unmeasured** (§10): `flag_value = false` means *assayed and not found* — real biology, kept in `results` and counted in `total_matching` + `by_value`. A *missing row* means *not in this assay's scope* — no information. `flag_value=False` filter is the explicit way to ask for tested-absent rows; never default-strip them.

#### 4.3.3 Envelope

`total_matching, by_value (true/false counts), by_assay, by_compartment, by_organism, by_metric (precomputed dm_true_count / dm_false_count vs filtered counts — mirrors DM), not_found`.

**`not_found` is structured** (multi-batch input — `assay_ids` and optional `metabolite_ids`): same convention as `metabolites_by_quantifies_assay` (Finding B in §11) — typed `NotFound` Pydantic model with `{assay_ids: [...], metabolite_ids: [...]}`.

**No `by_detection_status`** — that field exists only on the numeric edge (`Assay_quantifies_metabolite`). On the boolean arm, `flag_value` IS the qualitative-detection signal; `by_value` is its envelope rollup. Document the parallel in the YAML mistakes section so callers don't expect a `by_detection_status` here.

**Note (parallels DM):** `flag_value=False` may return zero rows today since the boolean arm has 119 `"false"` rows + 67 `"true"` rows (out of 186) — but that depends on filters. Unlike `genes_by_boolean_metric` (whose KG storage is positive-only), `Assay_flags_metabolite` stores both true and false flags, so `flag=False` will return real rows here. Document that distinction in tool description.

#### 4.3.4 Sort key

`r.flag_value DESC, m.id ASC, a.id ASC`. Presence-flag-true rows first (so callers reading the truncated head see what was found before what was tested-absent), then alphabetical by metabolite. Mirrors `genes_by_boolean_metric`.

---

### 4.4 `assays_by_metabolite` (Tool 4)

Batch reverse-lookup — analog of `gene_derived_metrics`. Merged across edge types with polymorphic `value` / `flag_value` columns.

#### 4.4.1 Tool signature

```python
assays_by_metabolite(
    metabolite_ids: list[str],                            # required, non-empty
    organism: str | None = None,                          # CONTAINS match (single-organism not enforced — see D2)
    evidence_kind: Literal["quantifies", "flags"] | None = None,    # filter by edge type
    exclude_metabolite_ids: list[str] | None = None,     # set-difference cross-tool convention (Phase 2)
    metric_types: list[str] | None = None,
    compartment: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int = 5,
    offset: int = 0,
) -> AssaysByMetaboliteResponse
```

#### 4.4.2 Per-row (polymorphic, parallel to `gene_derived_metrics`)

`metabolite_id, metabolite_name, assay_id, assay_name, evidence_kind, value (numeric arm only), value_sd (numeric only), flag_value (boolean only), n_replicates, n_positive (boolean only), metric_type, metric_bucket (numeric, rankable only), metric_percentile (numeric, rankable only), detection_status (numeric only), timepoint (numeric only — coerced per D3), timepoint_hours (numeric only — coerced per D3), timepoint_order (numeric only — coerced per D3), growth_phase (numeric only — Experiment-JOIN; null today, see D8), condition_label, organism_name, compartment, experiment_id, publication_doi`.

Sparse cross-arm fields are explicitly `None` — mirror Phase 3's union-shape `None`-padding decision on `genes_by_metabolite`/`metabolites_by_gene`. Document in docstring.

**Verbose adds:** `assay_field_description, replicate_values, experimental_context`.

#### 4.4.3 Envelope

`total_matching, returned, truncated, not_found, not_matched, by_evidence_kind, by_organism, by_compartment, by_assay, by_detection_status (numeric rows only — empty when evidence_kind='flags' or filters exclude all numeric rows), by_flag_value (boolean rows only — symmetric counterpart), metabolites_with_evidence, metabolites_without_evidence` (parallel to `gene_derived_metrics`'s `genes_with_metrics` / `genes_without_metrics`).

**Per-arm rollups documented:** because rows mix `quantifies` + `flags` evidence with sparse cross-arm fields, the envelope keeps two parallel detection-style breakdowns — `by_detection_status` over the numeric subset, `by_flag_value` over the boolean subset — rather than a unified rollup. Mirrors the union-shape `None`-padding decision (Phase 3) at envelope level.

**Diagnosability buckets** (parallel to DM):
- `not_found` — metabolite IDs absent from the KG entirely. **Unmeasured** (§10).
- `not_matched` — IDs present in KG but no `Assay_quantifies_metabolite` / `Assay_flags_metabolite` edge after filters (includes evidence_kind-mismatch when filter is set). **Unmeasured** for this filter scope (§10).
- Rows in `results` with `value = 0` / `flag_value = false` / `detection_status = 'not_detected'` are **tested-absent** (§10) — assayed and not found, distinct from `not_found` / `not_matched`. Document this boundary in the tool docstring so callers don't conflate "no row" with "row showing absence."

#### 4.4.4 Sort key

`m.id ASC, evidence_kind DESC, a.id ASC, r.time_point_order ASC NULLS LAST`. Group rows by the input metabolite first (caller's batch ordering self-evident), then `evidence_kind DESC` puts the data-richer numeric arm (`quantifies`, 15 fields) before the boolean arm (`flags`, 6 fields) within each metabolite — truncated heads surface the richer signal first. (ASCII order: `quantifies` > `flags`, so DESC works without a CASE.) Mirrors `gene_derived_metrics`'s `g.locus_tag ASC, dm.id ASC` grouping shape.

---

## 5. Open decisions for user closure

These need closure **before scope freeze**. Ranked by impact on surface area.

### D1 — Drill-down selection: `assay_ids` only, or `assay_ids` XOR `metric_types`?  **CLOSED → Option A** (2026-05-06)

`assay_ids` is the only selection parameter on `metabolites_by_quantifies_assay` and `metabolites_by_flags_assay`. Callers discover IDs via `list_metabolite_assays(metric_types=[...])` first (one extra round-trip; matches audit §3b.3). `metric_types` can be added later without breaking when usage demands it.

**Implication for §4.2.1 / §4.3.1 signatures:** drop the `metric_types: list[str] | None = None` line from both drill-downs.

### D2 — `assays_by_metabolite`: is `organism` optional or required?  **CLOSED → Option A** (2026-05-06)

`organism` is an **optional** scope filter, default `None` → cross-organism rows. Pass `organism="MED4"` to narrow. Cross-organism is the natural shape because `metabolite_ids` are organism-agnostic (one Metabolite node shared across organisms — audit §4.3.5). Closest parallel: `differential_expression_by_ortholog`, also cross-organism by design.

`organism_name` is on every row (§4.4.2) and `by_organism` is in the envelope (§4.4.3) regardless — the cross-organism shape is always self-describing.

### D3 — `time_point` empty-string handling (experiment-level signal)  **CLOSED → mirror `list_experiments` precedent** (2026-05-06)

Surveyed existing tools. The convention is already set in `list_experiments` and `differential_expression_by_gene`:

| Concern | Existing convention | Reference |
|---|---|---|
| Cypher column names | `r.time_point AS timepoint`, `r.time_point_hours AS timepoint_hours`, `r.time_point_order AS timepoint_order` (single-word output names) | [queries_lib.py:3218-3220](../../multiomics_explorer/kg/queries_lib.py#L3218-L3220) (`differential_expression_by_gene`) |
| Sentinel coercion in API | `""` (label) → `None`, `-1.0` (hours) → `None` | [api/functions.py:1180-1182](../../multiomics_explorer/api/functions.py#L1180-L1182) (`list_experiments`) |
| Pydantic types | `timepoint: str \| None`, `timepoint_hours: float \| None`, `timepoint_order: int` (non-null on labeled rows) | [mcp_server/tools.py:2708-2710](../../multiomics_explorer/mcp_server/tools.py#L2708-L2710) (`list_experiments`) |

**Live verification on assay edges (2026-05-06):** the same three sentinels exist:
- 1104/1200 numeric-arm edges: `time_point=""`, `time_point_hours=-1`, `time_point_order=0` (non-temporal experiments — the 6 Kujawinski papers + the chitosan T0 rows).
- 64 + 32 / 1200 numeric-arm edges: `time_point="4 days"|"6 days"`, `time_point_hours=96|144`, `time_point_order=1|2` (the Capovilla 2023 chitosan timecourse).

**Closure:**
1. **Cypher column rename:** `r.time_point AS timepoint`, `r.time_point_hours AS timepoint_hours`, `r.time_point_order AS timepoint_order` (drop the snake-snake — match DE / list_experiments).
2. **API sentinel coercion:** `timepoint == ""` → `None`; `timepoint_hours == -1.0` → `None`; `timepoint_order == 0` → `None` (extends the list_experiments convention since `0` is the assay-edge sentinel for non-temporal).
3. **Pydantic types on per-row models:** `timepoint: str | None`, `timepoint_hours: float | None`, `timepoint_order: int | None`. (DE/list_experiments use non-null `timepoint_order`; assay rows differ because non-temporal rows still carry the field.)
4. **Filter param rename:** `time_point: list[str]` → `timepoint: list[str]` (matches output column naming). Filter accepts label strings like `["4 days"]`; non-temporal rows are reachable by omitting the filter, **not** by passing `[""]`.
5. **YAML mistakes:** add an entry — *wrong:* "Read `timepoint=null` as missing data." *right:* "`timepoint=null` means the experiment is not time-resolved (one snapshot, no time axis). Distinct from a missing row, which is unmeasured (§10)."

**Apoc rollup note (subsumed):** today no `by_timepoint` envelope key is in scope. If one is added later, coerce sentinels there too (drop or rename `{item: "", count: N}` to `{item: null, count: N}`).

### D4 — `flag_value` storage form (string `"true"` / `"false"` vs bool)  **CLOSED → mirror DM** (2026-05-06)

Mirror DM. Per-row `flag_value: bool`; Cypher comparisons use the string form (`= "true"` / `= "false"`). One coercion line in API. Pydantic: `flag_value: bool` (non-nullable on boolean rows). MCP tool param `flag_value: bool | None = None` accepts Python `True` / `False` / `None`; API converts to the string form before interpolating into Cypher.

Symmetric coercion: API also reads `MetaboliteAssay.rankable: "true"|"false"` → `bool` per-row (already in §4.1.2). Same one-line helper.

### D5 — `list_metabolite_assays` envelope: include `score_max` / `score_median`?  **CLOSED → ADD** (2026-05-06)

Add `score_max` and `score_median` to the envelope, present only when `search_text` is set (parallel to DM). Reuse DM's helper signature: `apoc.coll.max(scores) AS score_max, apoc.coll.sort(scores)[size(scores)/2] AS score_median`. Pydantic: `score_max: float | None = Field(default=None, ...)`, same for `score_median`.

The `metaboliteAssayFullText` index covers 4 fields (`name, field_description, treatment, experimental_context`) vs DM's 2 — score distributions will differ from DM's but the envelope surface convention is identical.

### D6 — Should `metabolites_by_quantifies_assay` / `_flags_assay` accept `locus_tags` for "filter to assays that measured these specific genes' substrates"?  **CLOSED → NO** (2026-05-06)

No `locus_tags` parameter on either drill-down. The workflow is a two-call chain:

```
metabolites_by_gene(locus_tags=[...]) → take row metabolite_ids
metabolites_by_quantifies_assay(assay_ids=[...], metabolite_ids=[...])  # or _flags_assay
```

Reasons: (a) the deeper "assays that measured this gene's substrates" requires a `Gene → Reaction → Metabolite ← MetaboliteAssay` 3-hop chain that doesn't fit a drill-down's row schema; (b) splitting into two calls lets the caller see the gene-side roster (cofactor sprawl, transport-confidence tiers) before hitting the assay layer; (c) keeps per-tool surface tight. Document the chain in YAML `chaining:` for both drill-downs.

### D8 — Growth state on metabolomics: KG-side gap, not an explorer surface decision  **CLOSED → KG ASK** (2026-05-06)

Per user direction: this is a KG-side gap that closes on the KG side. Logged as **KG-MET-017** in [docs/kg-specs/2026-05-06-metabolites-followup-asks.md §3](../kg-specs/2026-05-06-metabolites-followup-asks.md) (new followup-batch doc; the original 2026-05-05 ask doc was the delivery snapshot and stays frozen). The ask: populate `growth_phases` on the analysis node (or per-timepoint on the parallel array on `Experiment`) — mirroring `DerivedMetric.growth_phases`.

**Explorer surface stays forward-compat** (per the spec's existing decision to surface `growth_phases` row field + filter on `list_metabolite_assays`, and per-edge `growth_phase` on numeric drill-down + reverse-lookup rows via Experiment JOIN). Today the values resolve to `null` / `[]` until KG-MET-017 lands; explorer code needs no change when it does — fields light up automatically.

**No code change in this slice.** Just keep the row/filter surfaces as currently spec'd in §4.1 / §4.2 / §4.4 and document in the YAML mistakes section that today's `null` reflects the unpopulated KG state, not "no growth-state metadata for this measurement."

### D7 — Worktree: open one for Phase 5, or land directly on main?  **CLOSED → WORKTREE** (2026-05-06)

Open a worktree for Phase 5. Phase 5 adds ~20–30 file touches across 4 tools and is expected to run alongside potential Phase 3/4 work. Conventional name: `metabolites-phase5-assay-tools` (matches existing `metabolites-phase2-renames` worktree convention). Open via `superpowers:using-git-worktrees` skill at the start of Phase 2 build (after frozen spec).

Sub-decision (deferred to build start): one worktree for both ships (Tool 1 + 3-tool slice), or one each. Recommendation: **one worktree, two PRs from sequential branches** — Tool 1 lands first; the 3-tool slice rebases on top. Keeps the file-ownership model coherent across the two ships (same agent files, no merge conflicts).

---

## 6. Sequencing within Phase 5

Per [roadmap §3 Phase 5 Sequencing](../superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md):

1. **Tool 1 first** — `list_metabolite_assays` (single-tool deep build, Mode A). Ships its own PR. Gives drill-down callers `assay_id` / `value_kind` / `rankable` to inspect.
2. **Tools 2–4 as a single Mode-B slice** — `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite` share envelope shape, Pydantic patterns, scoping-block code, and the str↔bool coercion. Mode-B briefing per [add-or-update-tool SKILL.md §Mode B](../../.claude/skills/add-or-update-tool/SKILL.md): "Implement `metabolites_by_quantifies_assay` as the template within your file, then extend pattern to `metabolites_by_flags_assay` and `assays_by_metabolite`."
   - Implementer order suggestion (within agent file): numeric drill-down → boolean drill-down → reverse-lookup. Numeric carries the most edge-filter logic; the others reuse it.

This is **two writing-plans cycles** total (one per ship).

---

## 7. Ready-to-plan gate

| Gate | Status |
|---|---|
| Audit Part 3b reviewed | ✅ ([audit](../superpowers/specs/2026-05-04-metabolites-surface-audit.md)) |
| Roadmap Phase 5 reviewed | ✅ ([roadmap §3 Phase 5](../superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md)) |
| KG schema verified live | ✅ (§3 above; 2026-05-05) |
| Mirror reference identified (DM pipeline) | ✅ (§1 table; specs cross-linked) |
| Open decisions D1–D8 closed | ✅ (§5; all closed 2026-05-06; KG-MET-017 logged in followup-asks doc) |
| User scope review | ✅ (D1–D8 closed inline) |
| Step 3 Cypher drafts verified live | ⏳ (in flight — one detail + one summary query per tool, 8 total) |
| Frozen spec | ⏳ (this doc post-Step-3, plus Cypher embedded per tool) |

**Next action:** run Step 3 (Cypher verification — 8 queries: detail + summary for each of 4 tools) and inline the verified queries here. Then split this doc into per-ship frozen specs (Tool 1 + 3-tool slice) and dispatch the writing-plans cycles. Worktree (D7 closure: yes) opened at start of Phase 2 build, after frozen specs.

---

## 8. Phase 2 build hint (preview, not committed)

Once frozen, Phase 2 dispatches per `add-or-update-tool` SKILL.md §Phase 2:

| Stage | Action |
|---|---|
| RED | `test-updater` writes failing tests across `test_query_builders.py`, `test_api_functions.py`, `test_tool_wrappers.py` for all 4 tools; updates `EXPECTED_TOOLS` + `TOOL_BUILDERS` registries. |
| GREEN (parallel) | 4 implementer agents in one message: `query-builder` (queries_lib.py), `api-updater` (api/functions.py + exports), `tool-wrapper` (mcp_server/tools.py), `doc-updater` (4× yaml + about regen + CLAUDE.md table). Mode-B briefing for the 3-tool drill-down slice; Mode-A briefing for `list_metabolite_assays`. Anti-scope-creep guardrail mandatory. |
| VERIFY | code-reviewer + `pytest tests/unit/`, `tests/integration/ -m kg`, `tests/regression/ -m kg`. |

Code-reviewer is the **hard gate** that catches Cypher label / direction / filter bugs that mocked unit tests miss (per skill — list_metabolites caught a `MATCH (o:Organism)` typo that 1676 unit tests missed; precedent applies here).

---

## 9. Risks / open questions

- **Scale today is small** (10 assays / 1,200+186 edges) — drill-down `total_matching` will be modest, so envelope rollups must remain correct on tiny slices (DM tests validate the shape; reuse fixture pattern).
- **`detection_status` headline** is the primary metabolomics interpretive hook (audit §4.3.3). Make sure `metabolites_by_quantifies_assay`'s envelope leads with `by_detection_status`, not with `by_metric_bucket` — the bucket distribution is ~uniform by construction, the detection_status distribution is biology.
- **Two boolean-arm metric types** (`presence_flag_intracellular`, `presence_flag_extracellular`) and `compartment` (`whole_cell`, `extracellular`) are not 1:1 — verify in Step 3 that filtering by compartment vs metric_type behaves as users expect on the boolean arm. (Likely fine; mention in YAML mistakes.)
- **`time_point = ""` is experiment-level**, not edge-type-level — non-time-resolved experiments. D3 closure decides whether to coerce on the numeric-arm rows; framing in YAML mistakes should disambiguate ("empty time_point ≡ experiment has no time axis," not "boolean assay" or "missing data").
- **Growth state is not on the edge** — verified live (§3.5). Reachable per-timepoint via `Experiment.time_point_growth_phases[time_point_order]` JOIN; assay-level via `MetaboliteAssay.growth_phases`. **Both arrays are empty today on every metabolomics record.** D8 closes the surface choice (forward-compat surface vs skip) and the companion KG-side backfill ask. YAML mistakes / docstring should call out today's null state so callers don't read `null` as "this measurement has no growth-state metadata."
- **Tested-absent ≠ unmeasured** is a top-level invariant — codified in §10. Every tool's docstring, every YAML `mistakes:` section, and the metabolomics analysis doc must carry the distinction so callers don't (a) silently filter out `value=0` / `flag_value=false` rows assuming noise, or (b) infer absence from a missing row.
- **`by_detection_status` is numeric-arm-only** — surfaced on `list_metabolite_assays` (envelope rollup over numeric assays + per-row counts on numeric rows), `metabolites_by_quantifies_assay` (primary headline per audit §4.3.3), and `assays_by_metabolite` (numeric-row subset; mirrored by `by_flag_value` on the boolean subset). Not surfaced on `metabolites_by_flags_assay` — `flag_value` is the parallel field there.

---

## 10. Interpretive convention: tested-absent vs unmeasured

In metabolomics, two row states must not be conflated:

| State | Numeric arm | Boolean arm | What it means |
|---|---|---|---|
| Measured-present | `value > 0` and/or `detection_status ∈ {detected, sporadic}` | `flag_value = true` | Metabolite assayed and found. |
| **Tested-absent** | `value = 0`, `n_non_zero = 0`, `detection_status = 'not_detected'` | `flag_value = false` | Metabolite *assayed and not found*. **Real biological data — keep in `results`, count toward `total_matching` and envelope rollups.** |
| **Unmeasured** | no row in result; `metabolite_id` in `not_found` / `not_matched` | no row in result | Metabolite *not in this assay's scope*. **No information — do not infer absence.** |

Tested-absent rows answer the biological question "is X actually absent under condition Y." Discarding them silently misreads the question. Unmeasured rows carry zero information either way and must not be conflated with absence.

### Implications for the tool surface

| Surface | Behavior |
|---|---|
| `total_matching` | Counts measured rows = present + tested-absent. Excludes unmeasured (no row exists to count). |
| `results` (default) | Includes tested-absent rows by default. |
| Envelope rollups (`by_detection_status`, `by_value`, `by_flag_value`, `by_assay`, `by_compartment`, `by_organism`, `by_metric`) | Include tested-absent rows. Lets callers see how much of `total_matching` is biological absence. |
| Edge-level filters (`value_min > 0`, `detection_status` list excluding `not_detected`, `flag_value=True`) | Caller-surfaced; never silently default-on. Each one drops tested-absent rows when set. |
| `assays_by_metabolite` `not_found` / `not_matched` buckets | Unmeasured-only. Tested-absent rows go in `results`, not these buckets. |

### Required propagation (Phase 2 deliverable)

| Surface | Phase 2 owner | What lands |
|---|---|---|
| Tool docstring (`mcp_server/tools.py` `@mcp.tool` body) — all 4 tools | `tool-wrapper` agent | One sentence per tool: "A row with `value=0` / `flag_value=false` / `detection_status='not_detected'` is *tested-absent* (assayed and not found, kept in results). A missing row is *unmeasured* (not in this assay's scope). Don't conflate." |
| `inputs/tools/{name}.yaml` `mistakes:` section — all 4 tools | `doc-updater` agent | A `mistakes:` entry: `wrong: "Filter out value=0 / flag_value=false rows assuming they are noise."` `right: "These rows are tested-absent — the metabolite was assayed and not found. They are biology. Keep them unless explicitly investigating presence-only."` |
| `inputs/tools/{name}.yaml` `mistakes:` section — all 4 tools | `doc-updater` agent | A `mistakes:` entry: `wrong: "A metabolite missing from results means it was not detected."` `right: "Missing means unmeasured (out of scope for this assay). For 'tested and not found,' look for a value=0 / flag_value=false / detection_status='not_detected' row."` |
| `skills/multiomics-kg-guide/references/analysis/metabolomics.md` (hand-authored) | `doc-updater` agent | Top-level §"Tested-absent vs unmeasured" carrying this convention as canonical for cross-tool workflows. |
| `CLAUDE.md` MCP-tools-table rows for new tools | `doc-updater` agent | One-line note on each row that the tool returns tested-absent rows by default. |

### Audit cross-reference

Audit §4.3.3 (`detection_status` resolution) names `detected / sporadic / not_detected` as the primary headline summary for the metabolomics layer. This convention extends that decision to its full implication: the *not_detected* bucket is data, not omission, and the tool surface treats it as such everywhere. Audit §4.5 confounders (cofactor flooding, family_inferred dominance) covered other interpretation traps but did not call out the absence-vs-missing distinction explicitly — Phase 5 codifies it here.

---

## 11. Cross-tool convention audit

The DM pipeline is the closest mirror, but Phase 5 surfaces share field-naming + envelope-shape conventions with the broader tool family (`list_*`, batch reverse-lookups, chemistry drill-downs). This audit names each convention and traces it to the source tool(s), so the `tool-wrapper` / `api-updater` / `query-builder` agents in Phase 2 can mirror the right precedent rather than the closest one.

### 11.1 Convention table

| # | Convention | Source tools | Phase 5 application |
|---|---|---|---|
| A | `exclude_metabolite_ids: list[str] \| None` set-difference filter wherever `metabolite_ids` is accepted | `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene` (Phase 2 cross-cutting) | Added to all 4 Phase 5 tools (§4.1.1, §4.2.1, §4.3.1, §4.4.1). Set-difference semantics; exclude wins on overlap with `metabolite_ids`; empty list is no-op. |
| B | `not_found` shape: flat `list[str]` for single-batch tools; structured Pydantic class for multi-batch | flat: `gene_overview` (only `locus_tags`), `list_publications` (only `publication_dois`). Structured: `MetNotFound` on `list_metabolites` (`metabolite_ids` + `organism_names` + `pathway_ids`), `GbmNotFound` on `genes_by_metabolite` (3+ batch inputs). | Drill-downs `metabolites_by_quantifies_assay` / `metabolites_by_flags_assay` use STRUCTURED `NotFound` (assay_ids + metabolite_ids). `assays_by_metabolite` uses FLAT `list[str]` (only `metabolite_ids` is batch). `list_metabolite_assays` uses STRUCTURED if `assay_ids` + `metabolite_ids` are both batch (decide during Phase 2). |
| C | `organism: str \| None` (singular, CONTAINS / fuzzy-word match) on analytical-entity-anchored tools | `list_derived_metrics`, `list_publications`, `list_experiments`, `gene_overview`, `genes_by_metabolite` (single-org enforced), `metabolites_by_gene` | Singular `organism` on `list_metabolite_assays` and `assays_by_metabolite` (`MetaboliteAssay` is analytical-entity-shaped — closer to DM than to `Metabolite` itself). |
| D | `organism_names: list[str] \| None` (plural, set-membership) on Metabolite-anchored / Organism-anchored tools | `list_metabolites`, `list_organisms` | NOT used in Phase 5 (no Phase 5 tool sits at the Metabolite-anchored discovery layer; that's `list_metabolites`). |
| E | Pydantic typed sub-models for envelope rollups (NOT generic `list[dict]`) | universal — every envelope breakdown is a typed BaseModel: `MetTopOrganism`, `PubOrganismBreakdown`, `OverviewCategoryBreakdown`, `GbmByMetabolite`, etc. | Phase 2 deliverable: `tool-wrapper` agent must define typed sub-models for every breakdown in §4.1.3 / §4.2.3 / §4.3.3 / §4.4.3. Generic `list[dict]` is anti-pattern — explicit non-goal. Naming convention: `<ShortPrefix><Domain>` (e.g. `LmaTopOrganism` for `list_metabolite_assays`). |
| F | `treatment_type: list[str] \| None` (set-membership ANY-overlap) on analytical-entity tools | `list_derived_metrics`, `list_experiments`, `gene_derived_metrics`, all DM drill-downs | Already in spec ✓. (Note: `list_publications` uses singular `treatment_type: str` — odd outlier, don't mirror.) |
| G | Default `limit`: 5 for large surfaces (1000+ rows), 20 for small surfaces (covers entire KG today) | `list_metabolites=5` (1700+ metabolites), `list_publications=5`, `gene_overview=5`; `list_derived_metrics=20` (13 DMs); `list_experiments=5` | `list_metabolite_assays=20` (10 assays — covers all). Drill-downs and reverse-lookup `=5` (mirrors per-row defaults on edge tools). |
| H | `summary=True` is sugar for `limit=0`; `results=[]` on summary; envelope always populated | universal | Already in spec ✓. |
| I | Verbose adds heavy-text fields only; structural fields stay in compact | universal | Already in spec ✓ — see verbose-adds lines in §4.1.2 / §4.2.2 / §4.3.2 / §4.4.2. |
| J | `score: float \| None` per-row + `score_max` / `score_median` envelope when `search_text` provided | `list_metabolites`, `list_derived_metrics` | Already in spec ✓ (D5 closure). |
| K | String-typed booleans on KG (`"true"`/`"false"`) coerced to Python bool at API boundary | `DerivedMetric.rankable`, DM edge `flag_value`, `MetaboliteAssay.rankable`, `Assay_flags_metabolite.flag_value` | Already in spec ✓ (D4 closure). |
| L | `compartment: str \| None` (singular, exact match) | `list_publications`, `list_experiments`, `list_derived_metrics`, `gene_derived_metrics`, all DM drill-downs | Already in spec ✓. |
| M | `evidence_sources: list[Literal[...]] \| None` set-membership for path selectors | `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene` | NOT used in Phase 5 — assays have only one evidence type (METABOLOMICS); path-selector vocabulary doesn't apply. |
| N | Tool tags: `{"<domain>", "<role>", ...}`; annotations `{readOnlyHint: True, destructiveHint: False, idempotentHint: True, openWorldHint: False}` on all read-only tools | universal | Phase 2 deliverable. Suggested tags: `list_metabolite_assays` → `{"metabolomics", "discovery", "catalog"}`; drill-downs → `{"metabolomics", "metabolites", "drill-down"}` + `"numeric"` / `"boolean"`; reverse-lookup → `{"metabolomics", "metabolites", "batch"}`. |
| O | `await ctx.info(f"<tool> <key params>")` log line at top of every wrapper | universal | Phase 2 deliverable — `tool-wrapper` agent. |
| P | Tool docstring leads with operative semantics, not return-shape (return shape is in Pydantic models) | universal | Already in spec ✓ (per-tool docstring snippets in §4 surface operative semantics + §10 tested-absent-vs-unmeasured invariant). |

### 11.2 Phase 2 anti-pattern checklist

These are mirror-violations the `tool-wrapper` / `api-updater` agents must avoid (each one has bitten existing tools and was fixed):

- **Generic `list[dict]` in envelope** (Convention E) — every breakdown gets a typed Pydantic sub-model.
- **Flat `not_found` on multi-batch-input tools** (Convention B) — structured `NotFound` Pydantic class. Otherwise callers can't tell which batch input was bad.
- **Plural `organism_names` on analytical-entity tools** (Convention C/D) — would diverge from DM. Use singular `organism: str | None` with CONTAINS match.
- **Single `str` on filters that should accept multiple values** (Convention F) — `treatment_type` is `list[str]`, not `str`. Same for `background_factors`, `growth_phases`, `metric_types`.
- **Forgetting `exclude_metabolite_ids` when `metabolite_ids` is accepted** (Convention A) — Phase 2 cross-cutting; missing it is a regression.
- **Returning string `"true"` / `"false"` to the caller** (Convention K) — coerce at API boundary; per-row Pydantic field is bool.
- **Generic `dict` return type on the wrapper function** — return type must be `<ToolName>Response` so FastMCP can auto-generate the outputSchema. `gene_details` is the one exception (single-row pass-through with sparse fields), and it's documented as such.

### 11.3 What this audit does NOT change

Decisions D1–D8 (§5) and the §10 tested-absent-vs-unmeasured invariant remain as closed; this audit confirms they are consistent with broader conventions. Specifically:

- D1 (`assay_ids` only on drill-downs) — consistent with `genes_by_metabolite`'s required `metabolite_ids` selection.
- D2 (optional `organism` on reverse-lookup) — consistent with `differential_expression_by_ortholog`'s cross-organism default.
- D3 (timepoint sentinel coercion) — consistent with `list_experiments` / `differential_expression_by_gene` precedent (already cited in D3 closure).
- D4 (string→bool coercion) — Convention K.
- D5 (score envelope) — Convention J.
- D7 (worktree) — universal Phase 2 build pattern.
- D8 (KG-side gap) — KG-MET-017; Phase 5 surface unchanged.

---

## 12. Verified Cypher (Step 3, live KG 2026-05-06)

All 8 queries (4 detail + 4 summary) verified against the live KG. Total counts and distributions reproduce the §3 fixtures. Production builders embed the same patterns with `_<tool>_where()` helpers (mirroring `_list_derived_metrics_where()`). Each subsection shows the verified detail-mode + summary-mode skeletons with parameter slots; the full WHERE-clause construction belongs in the per-tool query builder during Phase 2.

### 12.1 `list_metabolite_assays`

**Detail (verified — returns all 10 assays with correct sentinel coercions, per-row `detection_status_counts` rollup over numeric assay edges):**

```cypher
// When search_text: CALL db.index.fulltext.queryNodes('metaboliteAssayFullText', $search_text)
//                   YIELD node AS a, score
//                   WHERE <_list_metabolite_assays_where conditions>
// Else:
MATCH (a:MetaboliteAssay)
WHERE <_list_metabolite_assays_where conditions>     // organism CONTAINS, IN-list filters, etc.
OPTIONAL MATCH (a)-[r:Assay_quantifies_metabolite]->(:Metabolite)
WITH a, [label IN collect(DISTINCT r.time_point) WHERE label IS NOT NULL AND label <> "" | label]
       AS timepoints,
     [s IN collect(r.detection_status) WHERE s IS NOT NULL] AS detection_statuses
WITH a, timepoints,
     CASE WHEN size(detection_statuses) = 0
          THEN [] ELSE apoc.coll.frequencies(detection_statuses) END
       AS detection_status_counts
RETURN
  a.id AS assay_id, a.name AS name, a.metric_type AS metric_type,
  a.value_kind AS value_kind,
  (a.rankable = "true") AS rankable,                    // D4: string → bool
  a.unit AS unit, a.field_description AS field_description,
  a.organism_name AS organism_name, a.experiment_id AS experiment_id,
  a.publication_doi AS publication_doi, a.compartment AS compartment,
  a.omics_type AS omics_type,
  coalesce(a.treatment_type, []) AS treatment_type,
  coalesce(a.background_factors, []) AS background_factors,
  coalesce(a.growth_phases, []) AS growth_phases,       // KG-MET-017: [] today
  a.total_metabolite_count AS total_metabolite_count,
  a.aggregation_method AS aggregation_method,
  a.preferred_id AS preferred_id,
  a.value_min AS value_min, a.value_q1 AS value_q1,
  a.value_median AS value_median, a.value_q3 AS value_q3, a.value_max AS value_max,
  timepoints,                                            // D3: "" stripped
  detection_status_counts                                // numeric assays only; [] on boolean
  // when search_text: + score
  // when verbose: + a.treatment AS treatment,
  //                + a.light_condition AS light_condition,
  //                + a.experimental_context AS experimental_context
ORDER BY                                                 // when search_text: score DESC,
  a.organism_name ASC, a.value_kind ASC, a.id ASC
SKIP $offset LIMIT $limit
```

**Summary (verified — `total_entries=10`, `total_matching=10`, `by_detection_status`={detected: 247, sporadic: 51, not_detected: 902} confirms tested-absent dominates 75% of all numeric edges, validating §10):**

```cypher
CALL { MATCH (all_a:MetaboliteAssay) RETURN count(all_a) AS total_entries }
// When search_text: as above
MATCH (a:MetaboliteAssay)
WHERE <_list_metabolite_assays_where conditions>
OPTIONAL MATCH (a)-[r:Assay_quantifies_metabolite]->(:Metabolite)
WITH total_entries, a, [s IN collect(r.detection_status) WHERE s IS NOT NULL] AS det
WITH total_entries,
     collect(a.organism_name) AS orgs,
     collect(a.value_kind) AS vks,
     collect(a.compartment) AS comps,
     collect(a.metric_type) AS mts,
     apoc.coll.flatten(collect(coalesce(a.treatment_type, []))) AS tts,
     apoc.coll.flatten(collect(coalesce(a.background_factors, []))) AS bfs,
     apoc.coll.flatten(collect(coalesce(a.growth_phases, []))) AS gps,
     apoc.coll.flatten(collect(det)) AS all_det,
     count(a) AS total_matching,
     sum(a.total_metabolite_count) AS metabolite_count_total
     // when search_text: + max(score) AS score_max,
     //                   percentileDisc(score, 0.5) AS score_median
RETURN total_entries, total_matching, metabolite_count_total,
       apoc.coll.frequencies(orgs) AS by_organism,
       apoc.coll.frequencies(vks) AS by_value_kind,
       apoc.coll.frequencies(comps) AS by_compartment,
       apoc.coll.frequencies(mts) AS top_metric_types,
       apoc.coll.frequencies(tts) AS by_treatment_type,
       apoc.coll.frequencies(bfs) AS by_background_factors,
       apoc.coll.frequencies(gps) AS by_growth_phase,
       apoc.coll.frequencies(all_det) AS by_detection_status
       // when search_text: + score_max, score_median
```

### 12.2 `metabolites_by_quantifies_assay`

**Detail (verified on `assay_ids=['metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration']` — top-5 rows are F6P + Citrate at top_decile rank, sentinel coercions correct, growth_phase=null per KG-MET-017):**

```cypher
MATCH (a:MetaboliteAssay)-[r:Assay_quantifies_metabolite]->(m:Metabolite)
WHERE a.id IN $assay_ids
  AND <_metabolites_by_quantifies_assay_where conditions>   // scoping + edge filters
OPTIONAL MATCH (a)<-[:ExperimentHasMetaboliteAssay]-(e:Experiment)
RETURN
  m.id AS metabolite_id, m.name AS name, m.kegg_compound_id AS kegg_compound_id,
  r.value AS value, r.value_sd AS value_sd, r.n_replicates AS n_replicates,
  r.n_non_zero AS n_non_zero,
  r.metric_type AS metric_type, r.metric_bucket AS metric_bucket,
  r.metric_percentile AS metric_percentile, r.rank_by_metric AS rank_by_metric,
  r.detection_status AS detection_status,
  CASE WHEN r.time_point = '' THEN null ELSE r.time_point END AS timepoint,
  CASE WHEN r.time_point_hours = -1.0 THEN null ELSE r.time_point_hours END AS timepoint_hours,
  CASE WHEN r.time_point_order = 0 THEN null ELSE r.time_point_order END AS timepoint_order,
  CASE WHEN r.time_point_order > 0
            AND size(coalesce(e.time_point_growth_phases, [])) >= r.time_point_order
       THEN e.time_point_growth_phases[r.time_point_order - 1]
       ELSE null END AS growth_phase,                        // KG-MET-017: null today
  r.condition_label AS condition_label,
  a.id AS assay_id, a.organism_name AS organism_name, a.compartment AS compartment
  // when verbose: + a.name AS assay_name, a.field_description AS field_description,
  //                a.experimental_context AS experimental_context,
  //                a.light_condition AS light_condition, r.replicate_values AS replicate_values
ORDER BY r.rank_by_metric ASC, m.id ASC, a.id ASC, r.time_point_order ASC
SKIP $offset LIMIT $limit
```

**Summary (verified — total_matching=64 for MIT9313 chitosan assay, `by_detection_status`={detected: 27, sporadic: 30, not_detected: 7}, `by_metric_bucket`={mid: 32, low: 16, top_quartile: 9, top_decile: 7}):**

```cypher
MATCH (a:MetaboliteAssay)-[r:Assay_quantifies_metabolite]->(m:Metabolite)
WHERE a.id IN $assay_ids
  AND <_metabolites_by_quantifies_assay_where conditions>
WITH collect(r.detection_status) AS dets,
     collect(r.metric_bucket) AS buckets,
     collect(a.id) AS assay_ids_collected,
     collect(a.compartment) AS comps,
     collect(a.organism_name) AS orgs,
     collect({metabolite_id: m.id, name: m.name}) AS mets,
     collect(r.value) AS vals,
     count(*) AS total_matching
RETURN total_matching,
       apoc.coll.frequencies(dets) AS by_detection_status,        // primary headline (audit §4.3.3)
       apoc.coll.frequencies(buckets) AS by_metric_bucket,
       apoc.coll.frequencies(assay_ids_collected) AS by_assay,
       apoc.coll.frequencies(comps) AS by_compartment,
       apoc.coll.frequencies(orgs) AS by_organism,
       apoc.coll.min(vals) AS filtered_value_min,
       apoc.coll.max(vals) AS filtered_value_max
       // by_metric envelope (per-assay precomputed-vs-filtered) computed in api/ layer
       // by enriching with a.value_min / value_q1 / value_median / value_q3 / value_max
```

### 12.3 `metabolites_by_flags_assay`

**Detail (verified on `assay_ids=['metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular']` — top-5 rows are flag_value=true alphabetical by metabolite, bool coercion correct, kegg_compound_id null on chebi-only metabolites):**

```cypher
MATCH (a:MetaboliteAssay)-[r:Assay_flags_metabolite]->(m:Metabolite)
WHERE a.id IN $assay_ids
  AND <_metabolites_by_flags_assay_where conditions>
RETURN
  m.id AS metabolite_id, m.name AS name, m.kegg_compound_id AS kegg_compound_id,
  (r.flag_value = 'true') AS flag_value,                  // D4: string → bool
  r.n_positive AS n_positive, r.n_replicates AS n_replicates,
  r.metric_type AS metric_type, r.condition_label AS condition_label,
  a.id AS assay_id, a.organism_name AS organism_name, a.compartment AS compartment
  // when verbose: + a.name AS assay_name, a.field_description AS field_description
ORDER BY r.flag_value DESC, m.id ASC, a.id ASC
SKIP $offset LIMIT $limit
```

**Summary (verified — total_matching=93, `by_value`={false: 58, true: 35}; tested-absent dominates 62% of boolean rows, again validating §10):**

```cypher
MATCH (a:MetaboliteAssay)-[r:Assay_flags_metabolite]->(m:Metabolite)
WHERE a.id IN $assay_ids
  AND <_metabolites_by_flags_assay_where conditions>
WITH collect(r.flag_value) AS flags,
     collect(a.id) AS assay_ids_collected,
     collect(a.compartment) AS comps,
     collect(a.organism_name) AS orgs,
     count(*) AS total_matching
RETURN total_matching,
       apoc.coll.frequencies(flags) AS by_value,
       apoc.coll.frequencies(assay_ids_collected) AS by_assay,
       apoc.coll.frequencies(comps) AS by_compartment,
       apoc.coll.frequencies(orgs) AS by_organism
       // by_metric envelope (per-assay dm_true_count vs filtered count) computed in api/ layer
```

### 12.4 `assays_by_metabolite`

**CyVer caveat (Step 3 lesson):** the polymorphic `r:Assay_quantifies_metabolite|Assay_flags_metabolite` shape with cross-arm property reads in CASE expressions trips a CyVer schema warning ("`Assay_quantifies_metabolite` does not have property `flag_value`"). The fix is **`UNION ALL` with distinct relationship variable names per branch** (`rq` for quantifies, `rf` for flags) — verified clean. This pattern must be embedded in the production builder; do not use the merged `[r:A|B]` form even though it parses.

**Detail (verified on `metabolite_ids=['kegg.compound:C00074']` (PEP) — 18 quantifies rows + 2 flags rows = 20 total; `evidence_kind DESC` correctly puts data-richer numeric rows first within each metabolite):**

```cypher
CALL {
  MATCH (a:MetaboliteAssay)-[rq:Assay_quantifies_metabolite]->(m:Metabolite)
  WHERE m.id IN $metabolite_ids
    AND <_assays_by_metabolite_where conditions>           // organism, evidence_kind in {None, 'quantifies'}, etc.
  OPTIONAL MATCH (a)<-[:ExperimentHasMetaboliteAssay]-(e:Experiment)
  RETURN
    m.id AS metabolite_id, m.name AS metabolite_name,
    a.id AS assay_id, a.name AS assay_name,
    'quantifies' AS evidence_kind,
    rq.value AS value, rq.value_sd AS value_sd,
    null AS flag_value, null AS n_positive,
    rq.n_replicates AS n_replicates,
    rq.metric_type AS metric_type,
    rq.metric_bucket AS metric_bucket, rq.metric_percentile AS metric_percentile,
    rq.detection_status AS detection_status,
    CASE WHEN rq.time_point = '' THEN null ELSE rq.time_point END AS timepoint,
    CASE WHEN rq.time_point_hours = -1.0 THEN null ELSE rq.time_point_hours END AS timepoint_hours,
    CASE WHEN rq.time_point_order = 0 THEN null ELSE rq.time_point_order END AS timepoint_order,
    CASE WHEN rq.time_point_order > 0
              AND size(coalesce(e.time_point_growth_phases, [])) >= rq.time_point_order
         THEN e.time_point_growth_phases[rq.time_point_order - 1]
         ELSE null END AS growth_phase,                    // KG-MET-017: null today
    rq.condition_label AS condition_label,
    a.organism_name AS organism_name, a.compartment AS compartment,
    a.experiment_id AS experiment_id, a.publication_doi AS publication_doi
  UNION ALL
  MATCH (a:MetaboliteAssay)-[rf:Assay_flags_metabolite]->(m:Metabolite)
  WHERE m.id IN $metabolite_ids
    AND <_assays_by_metabolite_where conditions>           // evidence_kind in {None, 'flags'}, etc.
  RETURN
    m.id AS metabolite_id, m.name AS metabolite_name,
    a.id AS assay_id, a.name AS assay_name,
    'flags' AS evidence_kind,
    null AS value, null AS value_sd,
    (rf.flag_value = 'true') AS flag_value,
    rf.n_positive AS n_positive,
    rf.n_replicates AS n_replicates,
    rf.metric_type AS metric_type,
    null AS metric_bucket, null AS metric_percentile, null AS detection_status,
    null AS timepoint, null AS timepoint_hours, null AS timepoint_order,
    null AS growth_phase,
    rf.condition_label AS condition_label,
    a.organism_name AS organism_name, a.compartment AS compartment,
    a.experiment_id AS experiment_id, a.publication_doi AS publication_doi
}
ORDER BY metabolite_id ASC, evidence_kind DESC, assay_id ASC,
         coalesce(timepoint_order, 999999) ASC
SKIP $offset LIMIT $limit
```

**Summary (verified for PEP — `total_matching=20`, `by_evidence_kind`={quantifies: 18, flags: 2}, `by_detection_status`={not_detected: 12, detected: 3, sporadic: 3}, `by_flag_value`={false: 2}; 14/20 = 70% of all PEP measurements are tested-absent):**

```cypher
CALL {
  MATCH (a:MetaboliteAssay)-[rq:Assay_quantifies_metabolite]->(m:Metabolite)
  WHERE m.id IN $metabolite_ids
    AND <_assays_by_metabolite_where conditions>
  RETURN m.id AS metabolite_id, a.id AS assay_id, a.organism_name AS organism_name,
         a.compartment AS compartment, 'quantifies' AS evidence_kind,
         rq.detection_status AS det, null AS flag
  UNION ALL
  MATCH (a:MetaboliteAssay)-[rf:Assay_flags_metabolite]->(m:Metabolite)
  WHERE m.id IN $metabolite_ids
    AND <_assays_by_metabolite_where conditions>
  RETURN m.id AS metabolite_id, a.id AS assay_id, a.organism_name AS organism_name,
         a.compartment AS compartment, 'flags' AS evidence_kind,
         null AS det, rf.flag_value AS flag
}
WITH collect(metabolite_id) AS m_ids,
     collect(assay_id) AS assay_ids_collected,
     collect(organism_name) AS orgs,
     collect(compartment) AS comps,
     collect(evidence_kind) AS evks,
     [d IN collect(det) WHERE d IS NOT NULL] AS dets,
     [f IN collect(flag) WHERE f IS NOT NULL] AS flags,
     count(*) AS total_matching
RETURN total_matching,
       apoc.coll.frequencies(evks) AS by_evidence_kind,
       apoc.coll.frequencies(orgs) AS by_organism,
       apoc.coll.frequencies(comps) AS by_compartment,
       apoc.coll.frequencies(assay_ids_collected) AS by_assay,
       apoc.coll.frequencies(dets) AS by_detection_status,        // numeric subset
       apoc.coll.frequencies(flags) AS by_flag_value,             // boolean subset
       size(apoc.coll.toSet(m_ids)) AS metabolites_matched
       // not_found / not_matched / metabolites_with_evidence / metabolites_without_evidence
       // computed in api/ layer by diffing $metabolite_ids against m_ids
```

### 12.5 Cross-cutting Step-3 lessons

| Lesson | Captured in spec |
|---|---|
| `[r:A\|B]` polymorphic edge match warns under CyVer when CASE expressions read cross-arm props. **Use `UNION ALL` with distinct rel-vars (`rq`, `rf`).** | §12.4 caveat block + §11.2 anti-pattern checklist (add to Phase 2 brief). |
| `detection_status` counts surface as the **majority signal** in every aggregation — 75% of numeric edges are `not_detected`, 62% of boolean rows are `false`. The §10 invariant is not theoretical; without it the entire metabolomics layer collapses to "what's detected" and discards 70% of the data. | §10, §3.2, §12.1 / §12.2 / §12.3 / §12.4 summary commentary. |
| Sentinel triple `("", -1.0, 0)` for non-temporal numeric edges — verified live (1104/1200 rows). API coerces all three to `None`; per-row Pydantic uses `\| None` types. | D3, §12.2 / §12.4 detail Cypher (CASE-coercion inline). |
| `growth_phase` JOIN to `Experiment.time_point_growth_phases[time_point_order - 1]` is the right reachability path — schema verified, but value is `null` everywhere today (KG-MET-017). | §3.5 verification table, §12.2 / §12.4 detail Cypher (CASE-guarded inline lookup). |
| `collect()` over scalar fields silently drops NULLs — use `[x IN collect(field) WHERE x IS NOT NULL]` filter when NULLs are meaningful, OR `collect({key: field})` to preserve via map projection (per `layer-rules` references/layer-boundaries.md §"NULL behaviour in aggregation"). | §12.1 (`detection_statuses` filter), §12.4 (`dets`/`flags` filters); enforced as Convention in §13.5. |

---

## 13. Phase 2 build deliverables (review-driven additions)

The pre-split review against `add-or-update-tool` SKILL.md, `layer-rules` SKILL.md + references, and the field-rubric surfaces concrete deliverables for the Phase 2 build that aren't otherwise visible from the per-tool sections. Each item names the owning Phase 2 agent.

### 13.1 Query builder names (Layer 1)

The `query-builder` agent owns these in `kg/queries_lib.py`. Naming follows the layer-rules convention `build_{name}{,_summary,_diagnostics}` and the DM-family precedent for shared helpers.

| Builder | Purpose | DM analog |
|---|---|---|
| `_list_metabolite_assays_where()` | Shared WHERE-clause builder for `list_metabolite_assays`'s detail + summary; mirrors `_list_derived_metrics_where()` | `_list_derived_metrics_where()` |
| `build_list_metabolite_assays()` | Detail Cypher (§12.1) | `build_list_derived_metrics()` |
| `build_list_metabolite_assays_summary()` | Summary Cypher (§12.1) | `build_list_derived_metrics_summary()` |
| `build_metabolites_by_quantifies_assay()` | Detail Cypher (§12.2) | `build_genes_by_numeric_metric()` |
| `build_metabolites_by_quantifies_assay_summary()` | Summary Cypher (§12.2) | `build_genes_by_numeric_metric_summary()` |
| `build_metabolites_by_quantifies_assay_diagnostics()` | Pre-flight rankable-gating probe — checks whether all selected `assay_ids` have `rankable=true` before applying rankable-gated edge filters; raises if all-non-rankable, soft-excludes mixed | `build_genes_by_numeric_metric_diagnostics()` |
| `build_metabolites_by_flags_assay()` | Detail Cypher (§12.3) | `build_genes_by_boolean_metric()` |
| `build_metabolites_by_flags_assay_summary()` | Summary Cypher (§12.3) | `build_genes_by_boolean_metric_summary()` |
| `build_assays_by_metabolite()` | Detail Cypher (§12.4) — `UNION ALL` with `rq` / `rf` rel-vars per CyVer caveat | `build_gene_derived_metrics()` |
| `build_assays_by_metabolite_summary()` | Summary Cypher (§12.4) — same `UNION ALL` shape | `build_gene_derived_metrics_summary()` |

`metabolites_by_flags_assay` does not need a `_diagnostics` builder — boolean DM precedent shows the `flag_value` filter has no gate to probe.

### 13.2 CyVer registry updates (Layer 1)

After the builders are added, register them in `tests/integration/test_cyver_queries.py` so SchemaValidator + PropertiesValidator + SyntaxValidator run on every test pass. Two registries to update:

- `_BUILDERS` list: append all 9 new builder functions (excluding the `_where` helper — only top-level builders).
- `_KNOWN_MAP_KEYS` set: add the new map projection keys this slice introduces — `metabolite_id`, `name` (already exists?), `kegg_compound_id`, `assay_id`, `assay_name`, `evidence_kind`, `flag_value`, `n_positive`, `det`, `flag` (UNION ALL aliases). Verify against the existing set; add only the new ones.

### 13.3 Layer-2 exports (Layer 2)

After API functions are added, re-export per layer-rules §"Exports":

- `multiomics_explorer/api/__init__.py` `__all__`: add `list_metabolite_assays`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite`.
- `multiomics_explorer/__init__.py` `__all__`: same four names.

### 13.4 Anti-scope-creep guardrail (Phase 2 §Stage 2)

Per `add-or-update-tool` SKILL.md §Stage 2 — every implementer agent's brief MUST contain verbatim:

> "ADD only — do NOT modify, rename, or rebaseline any existing test, case, or yml. If an unrelated test fails in your environment, REPORT AS A CONCERN; do not silently retune. Pinned baselines are KG-state guards."

Reason: agents that observe pre-existing failures (stale base, KG drift, sibling-work conflicts) will "fix" them by editing baselines downward — silently masking real signals. The list_metabolites build hit this; the lesson is folded back into the skill.

### 13.5 Field-rubric checklist (Phase 2 deliverable per `tool-wrapper` agent)

Every Pydantic field description on the 4 new tools MUST satisfy the field-rubric ([`docs/superpowers/specs/2026-04-29-mcp-usability-audit.md`](../superpowers/specs/2026-04-29-mcp-usability-audit.md), distilled in `add-or-update-tool/references/field-rubric.md`):

- [ ] **Field examples are real KG values** — pulled from §3 verification (e.g. `'kegg.compound:C00074'` for metabolite_id; `'metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration'` for assay_id; `'4 days'` for timepoint; `0.4465` for value). No `'foo'` / `'TBD'` / fictional placeholders.
- [ ] **Presence-only fields say so** — none in this slice; flag if any surface during build.
- [ ] **Coarse-summary fields signpost drill-downs by name** — every `by_*` envelope key on `list_metabolite_assays` names the drill-down tool that surfaces row-level content. Examples to land in Phase 2:
  - `by_value_kind` → "Routes to drill-down: `numeric` → `metabolites_by_quantifies_assay`, `boolean` → `metabolites_by_flags_assay`."
  - `by_detection_status` → "Filter on `metabolites_by_quantifies_assay(detection_status=...)` to drill into rows with each status."
  - `by_assay` → "Pass these `assay_id`s to `metabolites_by_quantifies_assay(assay_ids=[...])` or `metabolites_by_flags_assay`."
- [ ] **Tool docstring includes downstream direction** — every wrapper docstring lists "After this tool, drill into Y for Z" patterns. Templates:
  - `list_metabolite_assays`: "After this, drill via `metabolites_by_quantifies_assay(assay_ids=[...])` (numeric arm), `metabolites_by_flags_assay(assay_ids=[...])` (boolean arm), or `assays_by_metabolite(metabolite_ids=[...])` (reverse-lookup)."
  - `metabolites_by_quantifies_assay`: "Pre-flight: `list_metabolite_assays(rankable=True, value_kind='numeric')` to confirm rankable-gated filters apply. Drill across to: `assays_by_metabolite(metabolite_ids=[...])` for the same metabolites' boolean evidence; `genes_by_metabolite(metabolite_ids=[...], organism=...)` for gene catalysts/transporters."
  - `metabolites_by_flags_assay`: parallel pattern.
  - `assays_by_metabolite`: "Originates from `list_metabolites(metabolite_ids=[...])` or `metabolites_by_gene(locus_tags=[...])`. Drill back to numeric details via `metabolites_by_quantifies_assay(assay_ids=[...], metabolite_ids=[...])`."
- [ ] **Response rows are typed Pydantic models** — Convention E in §11 (already in spec).
- [ ] **Empty-result shapes are unambiguous** — §10 + §11 Convention B distinguish *tested-absent* (real biology, in `results`), *unmeasured* (`not_found` / `not_matched`), and *excluded-by-gate* (`excluded_assays` on the rankable-gated drill-down). Each state has its own envelope key with description.
- [ ] **Field name predicts shape** — review surfaced one rename: envelope `total_metabolite_count` → `metabolite_count_total` (cumulative-across-assays sum, not distinct count). Applied in §4.1.3 + §12.1.
- [ ] **No Cypher-syntax jargon in user-facing descriptions** — Pydantic Field text must not mention `apoc.coll.frequencies`, `MATCH`, `coalesce`, `CASE WHEN`, etc. Cypher details belong in builder docstrings only.

### 13.6 Structured `not_found` is a documented deviation (Layer 2 + Layer 3)

The layer-rules baseline (`layer-boundaries.md` §"Envelope fields") specifies `not_found: list[str]` (flat). The drill-down tools `metabolites_by_quantifies_assay` and `metabolites_by_flags_assay` use a STRUCTURED `NotFound` Pydantic model (Convention B in §11) because they accept multiple batch inputs (`assay_ids` + `metabolite_ids`). Precedents: `MetNotFound` on `list_metabolites`, `GbmNotFound` on `genes_by_metabolite`. **Document the deviation** in each tool's wrapper docstring + YAML mistakes section so callers and future contributors can see the convention is principled (multi-batch input → structured) rather than ad-hoc.

`assays_by_metabolite` has only one batch input (`metabolite_ids`) → flat `not_found: list[str]` per the baseline.

### 13.7 NULL-handling in aggregation (Layer 1 lesson, recurring)

Per `layer-rules` §NULL behavior — `collect(scalar_field)` silently drops NULLs. Phase 5 hits this in two places:
- §12.1 `[s IN collect(r.detection_status) WHERE s IS NOT NULL]` — preserves NULLs for explicit handling (NULL on boolean assays → empty list per-row).
- §12.4 `[d IN collect(det) WHERE d IS NOT NULL]` and `[f IN collect(flag) WHERE f IS NOT NULL]` — preserves NULL boundaries between numeric and boolean arms in the UNION ALL.

The `query-builder` agent's brief should call this out so similar patterns elsewhere in the new builders use the same defensive `[x IN collect(...) WHERE x IS NOT NULL]` form, rather than `collect()` alone.

### 13.8 Phase 2 dispatch summary

| Stage | Owner | Inputs | Acceptance |
|---|---|---|---|
| RED | `test-updater` | This frozen spec + per-tool sections (§4) + verified Cypher (§12) | All 4 tools' tests written and red; `EXPECTED_TOOLS` + `TOOL_BUILDERS` (registry tests + eval tests) updated; unrelated tests still green |
| GREEN: queries_lib.py | `query-builder` | §12 verified Cypher + §13.1 builder names + §13.7 NULL-handling guidance + anti-scope-creep guardrail | All builders compile + match §12 query strings + CyVer registry §13.2 updated |
| GREEN: api/functions.py + exports | `api-updater` | §4.X.1 signatures + §11 conventions (especially §11.2 anti-patterns) + §13.3 exports + anti-scope-creep guardrail | 4 API functions assembled with summary + detail dispatch; `__all__` updated; ValueError on bad inputs; Lucene retry on `list_metabolite_assays` |
| GREEN: mcp_server/tools.py | `tool-wrapper` | §4.X Pydantic shapes + §11 Conventions E/N/O/P + §13.5 field-rubric + §13.6 not_found deviation + §10 tested-absent docstring snippets + anti-scope-creep guardrail | 4 MCP wrappers; typed Pydantic envelopes (no `list[dict]`); Field descriptions with real KG examples; tool docstrings with drill-down signposting |
| GREEN: yaml + about + CLAUDE.md | `doc-updater` | §10 propagation table + chaining patterns from §13.5 + anti-scope-creep guardrail | 4 yaml files with `mistakes:` carrying tested-absent + structured-`not_found` + KG-MET-017-null entries; about content regenerated; CLAUDE.md MCP tools table updated |
| VERIFY | `code-reviewer` (subagent) + `pytest tests/unit/`, `tests/integration/ -m kg`, `tests/regression/ -m kg` | All Phase 2 outputs | Hard gate: code review confirms Cypher labels/directions + tests pass |
