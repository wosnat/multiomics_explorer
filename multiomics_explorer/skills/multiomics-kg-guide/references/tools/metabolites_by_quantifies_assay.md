# metabolites_by_quantifies_assay

## What it does

Drill into numeric MetaboliteAssay edges — one row per
(metabolite × assay-edge).

`value` (raw concentration / intensity) is always returned;
`metric_bucket` / `metric_percentile` / `rank_by_metric` populated
only on rankable-assay rows (mirrors `genes_by_numeric_metric`'s
rankable gate). Rankable-gated filters raise if every selected
assay has `rankable=false`, soft-exclude on mixed input.

A row with `value=0` / `flag_value=false` /
`detection_status='not_detected'` is *tested-absent* (assayed and
not found, kept in results). A missing row is *unmeasured* (not
in this assay's scope). Don't conflate.

Pre-flight: `list_metabolite_assays(rankable=True, value_kind='numeric')`
to confirm rankable filters apply.

Drill across:
- `assays_by_metabolite(metabolite_ids=[...])` — same metabolites'
  boolean evidence + cross-organism reverse view.
- `genes_by_metabolite(metabolite_ids=[...], organism=...)` — gene
  catalysts/transporters of these metabolites.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| assay_ids | list[string] | — | MetaboliteAssay IDs to drill into (full prefixed). Discover via `list_metabolite_assays(value_kind='numeric')`. E.g. ['metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration']. `not_found.assay_ids` lists IDs absent from the KG. |
| organism | string \| None | None | Filter to assays from this organism (case-insensitive CONTAINS). Cross-organism is the default; pass to narrow. |
| metabolite_ids | list[string] \| None | None | Restrict to specific metabolites (full prefixed IDs, e.g. ['kegg.compound:C00074']). `not_found.metabolite_ids` lists IDs absent from the KG; metabolites in the KG but not measured by any selected assay surface as zero rows (unmeasured per parent §10). |
| exclude_metabolite_ids | list[string] \| None | None | Exclude metabolites with these IDs (set-difference; exclude wins on overlap with `metabolite_ids`). |
| experiment_ids | list[string] \| None | None | Filter to assays from these experiments. |
| publication_doi | list[string] \| None | None | Filter by publication DOI(s). Exact match. E.g. ['10.1073/pnas.2213271120']. |
| compartment | string \| None | None | Sample compartment ('whole_cell' or 'extracellular'). Exact match. |
| treatment_type | list[string] \| None | None | Treatment type(s) (ANY-overlap, case-insensitive). E.g. ['carbon']. |
| background_factors | list[string] \| None | None | Background factor(s) (ANY-overlap). E.g. ['axenic']. |
| growth_phases | list[string] \| None | None | Growth phase(s) (ANY-overlap). Empty `[]` on assays today (KG-MET-017 backfill pending). |
| value_min | float \| None | None | Lower bound on `value` (raw concentration / intensity). **Caution**: `value > 0` strips tested-absent rows (`value=0` / `detection_status='not_detected'`) — use deliberately, never as default. See parent §10. |
| value_max | float \| None | None | Upper bound on `value`. Always applicable. |
| detection_status | list[string] \| None | None | Detection-status filter — primary headline per audit §4.3.3. Values: 'detected', 'sporadic', 'not_detected'. Excluding 'not_detected' strips tested-absent rows; surface as caller choice, never default. See parent §10. |
| timepoint | list[string] \| None | None | Timepoint label(s) — exact match. Live values: ['4 days'], ['6 days']. Non-temporal experiments expose no timepoint here (rows surface with `timepoint=null`). |
| metric_bucket | list[string] \| None | None | Bucket label(s) — subset of {'top_decile','top_quartile','mid','low'}. **Rankable-gated** — raises if every selected assay has `rankable=false`. Soft-excludes non-rankable assays from mixed input (surfaced in envelope `excluded_assays`). |
| metric_percentile_min | float \| None | None | Lower bound on `metric_percentile` (0-100). **Rankable-gated.** |
| metric_percentile_max | float \| None | None | Upper bound on `metric_percentile`. **Rankable-gated.** |
| rank_by_metric_max | int \| None | None | Cap on `rank_by_metric` (1 = highest). Top-N drill-down. **Rankable-gated.** |
| summary | bool | False | Return summary fields only (results=[]). |
| verbose | bool | False | Include heavy-text fields per row: assay_name, field_description, experimental_context, light_condition, replicate_values. |
| limit | int | 5 | Max rows. Paginate with `offset`. |
| offset | int | 0 | Pagination offset. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, by_detection_status, by_metric_bucket, by_assay, by_compartment, by_organism, by_metric, excluded_assays, warnings, not_found, returned, truncated, offset, results
```

- **total_matching** (int): Row count in the filtered slice.
- **by_detection_status** (list[MqaByDetectionStatus]): Counts per detection_status — primary headline (audit §4.3.3). 'not_detected' rows are tested-absent (real biology, parent §10).
- **by_metric_bucket** (list[MqaByMetricBucket]): Counts per rank-bucket on rankable rows.
- **by_assay** (list[MqaByAssay]): Counts per assay_id. Pass these `assay_id`s to `metabolites_by_flags_assay(assay_ids=[...])` for the boolean complement.
- **by_compartment** (list[MqaByCompartment]): Counts per compartment.
- **by_organism** (list[MqaByOrganism]): Counts per organism (cross-organism by default).
- **by_metric** (list[MqaByMetric]): Per-assay precomputed-vs-filtered: pairs the filtered slice min/max with the full-assay precomputed range so the LLM can read 'top-decile slice 0.012-0.16 out of full range 0-0.16' inline.
- **excluded_assays** (list[string]): `assay_ids` soft-excluded under rankable-gating (non-rankable assays dropped when a rankable filter is set).
- **warnings** (list[string]): Human-readable rankable-gating diagnostics.
- **not_found** (MqaNotFound): Per-batch-input unknown IDs (parent §13.6).
- **returned** (int): Length of `results`.
- **truncated** (bool): True when total_matching > offset + returned.
- **offset** (int): Pagination offset used.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| metabolite_id | string | Metabolite node id (e.g. 'kegg.compound:C00074' for PEP). |
| name | string | Canonical metabolite name (e.g. 'Phosphoenolpyruvate'). |
| kegg_compound_id | string \| None (optional) | KEGG compound id (e.g. 'C00074'); null if no KEGG xref. |
| value | float \| None (optional) | Raw concentration / intensity (e.g. 0.4465 for a top-decile F6P row). Null only on degenerate edges; `value=0.0` is *tested-absent*, not missing. |
| value_sd | float \| None (optional) | Standard deviation across replicates (when available). |
| n_replicates | int \| None (optional) | Number of replicates. |
| n_non_zero | int \| None (optional) | Number of replicates with non-zero signal. `n_non_zero=0` is tested-absent. |
| metric_type | string | Parent assay's metric tag (e.g. 'cellular_concentration'). |
| metric_bucket | string \| None (optional) | Bucket label ('top_decile' / 'top_quartile' / 'mid' / 'low'). Populated only on rankable assays. |
| metric_percentile | float \| None (optional) | Percentile (0-100). Populated only on rankable assays. |
| rank_by_metric | int \| None (optional) | Rank by value (1 = highest). Populated only on rankable assays. |
| detection_status | string \| None (optional) | One of 'detected', 'sporadic', 'not_detected'. 'not_detected' = tested-absent (parent §10). Numeric edge only. |
| timepoint | string \| None (optional) | Timepoint label ('4 days', '6 days'). Null on non-temporal experiments (D3 sentinel coercion). |
| timepoint_hours | float \| None (optional) | Timepoint in hours. Null on non-temporal experiments. |
| timepoint_order | int \| None (optional) | Timepoint order index. Null on non-temporal experiments. |
| growth_phase | string \| None (optional) | Growth phase. Null today — KG-MET-017 backfill pending. |
| condition_label | string \| None (optional) | Short condition descriptor (e.g. compartment + timepoint). |
| assay_id | string | Parent MetaboliteAssay id. |
| organism_name | string | Source organism. |
| compartment | string | 'whole_cell' or 'extracellular'. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| assay_name | string \| None (optional) | Human-readable assay name. Verbose only. |
| field_description | string \| None (optional) | Canonical provenance description for the assay. Verbose only. |
| experimental_context | string \| None (optional) | Long-form context. Verbose only. |
| light_condition | string \| None (optional) | Light regime (e.g. 'continuous light'). Verbose only. |
| replicate_values | list[float] \| None (optional) | Per-replicate values. Verbose only. |

## Few-shot examples

### Example 1: Canonical drill-down — MIT9313 chitosan rankable assay

```example-call
metabolites_by_quantifies_assay(assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"])
```

```example-response
total_matching: 64
by_detection_status: [{detected: 27}, {sporadic: 30}, {not_detected: 7}]
by_metric_bucket: [{mid: 32}, {low: 16}, {top_quartile: 9}, {top_decile: 7}]
by_assay: [{assay_id: "metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration", count: 64}]
by_compartment: [{whole_cell: 64}]
by_organism: [{Prochlorococcus MIT9313: 64}]
excluded_assays: []
warnings: []
not_found: {assay_ids: [], metabolite_ids: [], experiment_ids: [], publication_doi: []}
results: [F6P top_decile rank 1-3, Citrate top_decile rank 4-5, ...]  # default limit=5
```

### Example 2: Top-decile only (rankable filter applies)

```example-call
metabolites_by_quantifies_assay(assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"], metric_bucket=["top_decile"])
```

### Example 3: Tested-absent slice — explicitly ask for "not_detected" rows

```example-call
metabolites_by_quantifies_assay(assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"], detection_status=["not_detected"])
```

### Example 4: Timepoint scope — only the 4-day samples

```example-call
metabolites_by_quantifies_assay(assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"], timepoint=["4 days"])
```

### Example 5: Summary — distribution context without per-row drill-down

```example-call
metabolites_by_quantifies_assay(assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"], summary=True)
```

### Example 6: Cross-assay drill — multiple numeric assays at once

```example-call
metabolites_by_quantifies_assay(assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration", "metabolite_assay:pnas.2213271120:metabolites_extracellular_mit9313:extracellular_concentration"], metric_bucket=["top_decile"])
```

## Chaining patterns

```
list_metabolite_assays(rankable=True, value_kind='numeric') → metabolites_by_quantifies_assay(assay_ids=[...])  # pre-flight: confirm rankable-gated filters apply
metabolites_by_quantifies_assay → assays_by_metabolite(metabolite_ids=[...])  # boolean evidence + cross-organism reverse view
metabolites_by_quantifies_assay → genes_by_metabolite(metabolite_ids=[...], organism=...)  # gene catalysts/transporters of these metabolites
metabolites_by_quantifies_assay → metabolites_by_gene(locus_tags=[...], organism=...)  # gene-anchored chemistry context
```

## Common mistakes

```mistake
Filter out value=0 / flag_value=false rows assuming they are noise.
```

```correction
These rows are tested-absent — the metabolite was assayed and not found.
They are biology. Keep them unless explicitly investigating presence-only.

```

```mistake
A metabolite missing from results means it was not detected.
```

```correction
Missing means unmeasured (out of scope for this assay). For 'tested and
not found,' look for a value=0 / flag_value=false / detection_status='not_detected'
row.

```

```mistake
metabolites_by_quantifies_assay(assay_ids=[...], metric_bucket=['top_decile'])  # without checking rankable on the assay
```

```correction
Pre-flight via list_metabolite_assays(rankable=True, value_kind='numeric').
Tool soft-excludes non-rankable assays from mixed input (surfaces in
envelope `excluded_assays` + `warnings`) and raises ValueError if every
selected assay is non-rankable.

```

```mistake
Expect not_found to be a flat list[str].
```

```correction
Drill-downs use a structured NotFound (4 keys: assay_ids, metabolite_ids,
experiment_ids, publication_doi) per parent spec §13.6 — multi-batch input
→ structured. Inspect each bucket separately to see which input was bad.
Mirrors `MetNotFound` on `list_metabolites` and `GbmNotFound` on
`genes_by_metabolite`.

```

```mistake
Apply value_min=0.001 by default to 'clean' the data.
```

```correction
`value_min > 0` strips tested-absent rows (`value=0` /
`detection_status='not_detected'`). 75% of numeric edges in the live KG
are not_detected (902 of 1200) — value_min would discard the majority of
measured biology under this KG state. Surface as caller choice, never
default-on. See parent §10.

```

```mistake
Treat metric_bucket / metric_percentile / rank_by_metric as always populated.
```

```correction
Rankable-gated columns are null on rows whose parent assay has
`rankable=false`. Eight of 10 current assays are rankable; the 2 boolean
assays surface in `metabolites_by_flags_assay` instead. Per-row null on
these columns means "not applicable" not "missing data".

```

```mistake
growth_phase populated on every row.
```

```correction
growth_phase is null on every row today — the schema field exists on
Experiment, but `time_point_growth_phases[]` is empty for every
metabolomics experiment in the current KG (KG-MET-017 backfill pending).
Forward-compat surface; values populate without explorer-side code change
when the KG ask lands.

```

## Package import equivalent

```python
from multiomics_explorer import metabolites_by_quantifies_assay

result = metabolites_by_quantifies_assay(assay_ids=...)
# returns dict with keys: total_matching, by_detection_status, by_metric_bucket, by_assay, by_compartment, by_organism, by_metric, excluded_assays, warnings, not_found, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
