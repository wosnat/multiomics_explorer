# list_metabolite_assays

## What it does

Discover MetaboliteAssay nodes — discovery surface for the
metabolomics measurement layer. Mirrors `list_derived_metrics`.

Inspect `value_kind` (routes drill-down), `rankable` (gates
rankable filters on the numeric drill-down), `compartment`
(whole_cell vs extracellular), and per-row
`detection_status_counts` (signals how much of the assay is
detected / sporadic / not_detected — primary headline per audit
§4.3.3).

A row with `value=0` / `flag_value=false` /
`detection_status='not_detected'` on the drill-down tools is
*tested-absent* (assayed and not found, real biology) — distinct
from a missing row, which is *unmeasured* (not in the assay's
scope). See parent spec §10.

After this, drill via:
- metabolites_by_quantifies_assay(assay_ids=[...]) — numeric arm details
- metabolites_by_flags_assay(assay_ids=[...]) — boolean arm details
- assays_by_metabolite(metabolite_ids=[...]) — reverse lookup across both arms
- list_metabolites(metabolite_ids=[...]) — chemistry context for measured compounds

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Full-text search over MetaboliteAssay name, field_description, treatment, experimental_context. E.g. 'chitosan', 'cellular concentration', 'KEGG export'. |
| organism | string \| None | None | Organism (case-insensitive substring CONTAINS). E.g. 'MIT9301', 'Prochlorococcus MIT9313'. |
| metric_types | list[string] \| None | None | Filter by metric_type tags. Live values: 'cellular_concentration', 'extracellular_concentration', 'presence_flag_intracellular', 'presence_flag_extracellular'. |
| value_kind | string ('numeric', 'boolean') \| None | None | 'numeric' → metabolites_by_quantifies_assay drill-down; 'boolean' → metabolites_by_flags_assay. |
| compartment | string \| None | None | 'whole_cell' or 'extracellular'. Exact match. |
| treatment_type | list[string] \| None | None | ANY-overlap. E.g. ['carbon'], ['phosphorus', 'growth_phase']. |
| background_factors | list[string] \| None | None | ANY-overlap. E.g. ['axenic', 'light']. |
| growth_phases | list[string] \| None | None | ANY-overlap. Empty today — KG-MET-017 backfill pending. |
| publication_doi | list[string] \| None | None | DOI(s). Exact match. E.g. ['10.1073/pnas.2213271120', '10.1128/msystems.01261-22']. |
| experiment_ids | list[string] \| None | None | Experiment node id(s). |
| assay_ids | list[string] \| None | None | MetaboliteAssay id(s). `not_found.assay_ids` lists unknowns. |
| metabolite_ids | list[string] \| None | None | Restrict to assays measuring at least one of these metabolites (1-hop via Assay_quantifies_metabolite | Assay_flags_metabolite). Full prefixed IDs, e.g. ['kegg.compound:C00074']. |
| exclude_metabolite_ids | list[string] \| None | None | Exclude assays measuring any of these metabolites (set-difference cross-tool convention). |
| rankable | bool \| None | None | True → assays supporting rank/percentile/bucket on metabolites_by_quantifies_assay's rankable-gated filters. |
| summary | bool | False | Return summary fields only (results=[]). |
| verbose | bool | False | Include heavy-text fields per row: treatment, light_condition, experimental_context. |
| limit | int | 20 | Max results (default 20 covers all 14 assays today). |
| offset | int | 0 | Pagination offset (0-indexed). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, metabolite_count_total, by_organism, by_value_kind, by_compartment, top_metric_types, by_treatment_type, by_background_factors, by_growth_phase, by_detection_status, score_max, score_median, returned, offset, truncated, not_found, results
```

- **total_entries** (int): Total MetaboliteAssay nodes in KG (10 today)
- **total_matching** (int): Assays matching all filters
- **metabolite_count_total** (int): Cumulative sum of total_metabolite_count across matching assays. Same metabolite measured by N assays counts N times. For distinct count, use assays_by_metabolite(metabolite_ids=..., summary=True) or list_metabolites(metabolite_ids=...).
- **by_organism** (list[LmaOrganismBreakdown]): Counts per organism, sorted desc
- **by_value_kind** (list[LmaValueKindBreakdown]): Counts per value_kind. Routes drill-down: numeric → metabolites_by_quantifies_assay, boolean → metabolites_by_flags_assay.
- **by_compartment** (list[LmaCompartmentBreakdown]): Counts per compartment
- **top_metric_types** (list[LmaMetricTypeBreakdown]): Counts per metric_type, sorted desc. Pass to metabolites_by_quantifies_assay or metabolites_by_flags_assay (assay-id resolution required first).
- **by_treatment_type** (list[LmaTreatmentTypeBreakdown])
- **by_background_factors** (list[LmaBackgroundFactorBreakdown])
- **by_growth_phase** (list[LmaGrowthPhaseBreakdown]): Empty today — KG-MET-017 backfill pending.
- **by_detection_status** (list[LmaDetectionStatusBreakdown]): Envelope-level rollup of detection_status across all numeric edges of matching assays. Audit §4.3.3 primary headline. ~75% of numeric edges are not_detected (tested-absent — real biology, see parent §10).
- **score_max** (float | None): Max Lucene score (only with search_text)
- **score_median** (float | None): Median Lucene score (only with search_text)
- **returned** (int): Rows in this response
- **offset** (int): Pagination offset used
- **truncated** (bool): True when total_matching > returned
- **not_found** (LmaNotFound): Per-batch-input unknown IDs (parent §11 Conv B / §13.6)

### Per-result fields

| Field | Type | Description |
|---|---|---|
| assay_id | string | Unique id (e.g. 'metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration'). Pass to drill-downs. |
| name | string | Human-readable assay name (e.g. 'MIT9301 intracellular metabolite concentration (mol/cell)') |
| metric_type | string | Category tag (e.g. 'cellular_concentration', 'extracellular_concentration', 'presence_flag_intracellular') |
| value_kind | string ('numeric', 'boolean') | Routes drill-down: 'numeric' → metabolites_by_quantifies_assay, 'boolean' → metabolites_by_flags_assay |
| rankable | bool | True if metric_bucket / metric_percentile / rank_by_metric filters apply on the numeric drill-down (rankable=False on boolean assays) |
| unit | string | Measurement unit (e.g. 'mol/cell', 'fg/cell'); empty string on boolean assays |
| field_description | string | Canonical provenance description for the assay (e.g. 'Intracellular metabolite concentration in fg/cell, blank-corrected, replicate-aggregated; Capovilla 2023 Table sd03.') |
| organism_name | string | Full organism name (e.g. 'Prochlorococcus MIT9313') |
| experiment_id | string | Parent Experiment node id |
| publication_doi | string | Parent publication DOI (e.g. '10.1073/pnas.2213271120') |
| compartment | string | 'whole_cell' or 'extracellular' |
| omics_type | string | Always 'METABOLOMICS' for assays |
| treatment_type | list[string] (optional) | Treatment type(s) (e.g. ['carbon']) |
| background_factors | list[string] (optional) | Background factor(s) (e.g. ['axenic', 'light']) |
| growth_phases | list[string] (optional) | Growth phases — empty today (KG-MET-017 backfill pending) |
| total_metabolite_count | int | Distinct metabolites measured by this assay (e.g. 92) |
| aggregation_method | string | How replicates were aggregated (e.g. 'mean_across_replicates') |
| preferred_id | string | Xref hint (e.g. 'metabolite_assay_id') |
| value_min | float \| None (optional) | Min observed value across all measurements on this assay (e.g. 0.0) |
| value_q1 | float \| None (optional) | Q1 of values (e.g. 0.0012) |
| value_median | float \| None (optional) | Median (e.g. 0.0056) |
| value_q3 | float \| None (optional) | Q3 (e.g. 0.012) |
| value_max | float \| None (optional) | Max (e.g. 0.16) |
| timepoints | list[string] (optional) | Timepoint labels (e.g. ['4 days', '6 days']). Empty list when the parent experiment is not time-resolved (per Phase 5 D3). |
| detection_status_counts | list[LmaDetectionStatusCount] (optional) | Per-status counts over outgoing Assay_quantifies_metabolite edges. Empty list on boolean assays. Lets the LLM route to detection-status-rich assays without a drill-down round-trip. |
| score | float \| None (optional) | Lucene relevance score (only when search_text was provided) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| treatment | string \| None (optional) | Treatment description (verbose only) |
| light_condition | string \| None (optional) | Light condition (verbose only, e.g. 'continuous light') |
| experimental_context | string \| None (optional) | Long-form context (verbose only) |

## Few-shot examples

### Example 1: Orient — what assays exist

```example-call
list_metabolite_assays(summary=True)
```

```example-response
total_entries: 14
total_matching: 14
by_value_kind: [{value_kind: numeric, count: 12}, {value_kind: boolean, count: 2}]
by_compartment: [{compartment: whole_cell, count: 9}, {compartment: extracellular, count: 3}, {compartment: vesicle, count: 2}]
by_organism: [5 organisms across 3 papers — MIT9313, MIT9301, MIT9312, MIT0801, MIT9303]
by_detection_status: [{not_detected: 1046}, {detected: 360}, {sporadic: 74}]
results: []  # summary=True
```

### Example 2: Discovery via fulltext (Capovilla chitosan paper)

```example-call
list_metabolite_assays(search_text="chitosan")
```

### Example 3: Pre-flight for numeric drill-down

```example-call
list_metabolite_assays(value_kind="numeric", rankable=True)
```

### Example 4: Find assays measuring a specific metabolite

```example-call
list_metabolite_assays(metabolite_ids=["kegg.compound:C00074"])
```

### Example 5: Per-paper inventory

```example-call
list_metabolite_assays(publication_doi=["10.1073/pnas.2213271120"])
```

## Chaining patterns

```
list_metabolite_assays → metabolites_by_quantifies_assay(assay_ids=[...])
list_metabolite_assays → metabolites_by_flags_assay(assay_ids=[...])
list_metabolite_assays → assays_by_metabolite(metabolite_ids=[...])  # cross-organism reverse view
list_metabolite_assays → list_metabolites(metabolite_ids=[...])  # chemistry context for measured compounds
```

## Common mistakes

```mistake
Filter out value=0 / flag_value=false rows on drill-downs assuming they're noise.
```

```correction
Those rows are tested-absent — the metabolite was *assayed and not found*. Real biology. Keep them unless explicitly investigating presence-only.
```

```mistake
A metabolite missing from drill-down results means it was not detected.
```

```correction
Missing means *unmeasured* (not in the assay's scope). For 'tested and not found,' look for value=0 / flag_value=false / detection_status='not_detected' rows in the drill-down output.
```

```mistake
growth_phases=[] means the assay has no growth-state metadata.
```

```correction
growth_phases=[] today reflects unpopulated KG state (KG-MET-017 — KG team backfill pending). The schema field exists; values populate without explorer-side code change when the KG ask lands.
```

```mistake
metabolite_count_total = total distinct metabolites across matching assays.
```

```correction
metabolite_count_total is *cumulative*: same metabolite measured by N assays counts N times. For distinct counts route to assays_by_metabolite(metabolite_ids=..., summary=True) → metabolites_matched, or list_metabolites(metabolite_ids=...).
```

```mistake
Calling metabolites_by_quantifies_assay with bucket / metric_percentile filters before checking assay rankable.
```

```correction
Call list_metabolite_assays(value_kind='numeric', rankable=True) first. Drill-down's rankable-gated filters raise if every selected assay has rankable=False, soft-exclude on mixed input.
```

## Package import equivalent

```python
from multiomics_explorer import list_metabolite_assays

result = list_metabolite_assays()
# returns dict with keys: total_entries, total_matching, metabolite_count_total, by_organism, by_value_kind, by_compartment, top_metric_types, by_treatment_type, by_background_factors, by_growth_phase, by_detection_status, score_max, score_median, offset, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
