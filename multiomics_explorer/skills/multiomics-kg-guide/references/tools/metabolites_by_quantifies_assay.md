# metabolites_by_quantifies_assay

## What it does

Drill into numeric MetaboliteAssay edges — one row per
(metabolite × assay-edge). `value` (raw concentration /
intensity) is always returned; `metric_bucket` /
`metric_percentile` / `rank_by_metric` populated only on
rankable-assay rows (mirrors `genes_by_numeric_metric`'s
rankable gate). Rankable-gated filters raise if every selected
assay has `rankable=false`, soft-exclude on mixed input. Tested-
absent rows (`value=0` / `detection_status='not_detected'`) are
real biology and kept by default. Cross-organism by design.
Pre-flight via
`list_metabolite_assays(value_kind='numeric', rankable=True)`. Bare /
xref metabolite IDs are coerced to canonical (`resolved_aliases`;
collisions expand + warn).

Routing: drill across to `assays_by_metabolite(metabolite_ids=[...])`
for the boolean-arm complement and the cross-organism reverse view,
or `genes_by_metabolite(metabolite_ids=[...], organism=...)` for
gene catalysts/transporters. See `docs://guide/conventions` for
tested-absent semantics and `docs://analysis/metabolites` for
the metabolomics decision tree.

`organism` matches by case-insensitive CONTAINS (not word-match);
cross-organism is the default. A `metabolite_ids` entry absent from
the KG lands in `not_found.metabolite_ids`; one present but
unmeasured by the selected assays contributes zero rows.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| assay_ids | list[string] | — | MetaboliteAssay IDs to drill into (full prefixed). Discover via `list_metabolite_assays(value_kind='numeric')`. E.g. ['metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration']. `not_found.assay_ids` lists IDs absent from the KG. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| metabolite_ids | list[string] \| None | None | Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites). |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap. |
| experiment_ids | list[string] \| None | None | Filter to assays from these experiments. |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| min_value | float \| None | None | Lower bound on `value` (raw concentration / intensity). **Caution**: `value > 0` strips tested-absent rows (`value=0` / `detection_status='not_detected'`) — use deliberately, never as default. See `docs://guide/conventions`. |
| max_value | float \| None | None | Upper bound on `value`. Always applicable. |
| detection_status | list[string] \| None | None | Detection-status filter — primary qualitative headline. Values: 'detected', 'sporadic', 'not_detected'. Excluding 'not_detected' strips tested-absent rows; surface as caller choice, never default. See `docs://guide/conventions`. |
| timepoint | list[string] \| None | None | Timepoint label(s) — exact match. E.g. ['4 days'], ['6 days']. Non-temporal experiments expose no timepoint here (rows surface with `timepoint=null`). |
| metric_bucket | list[string] \| None | None | Bucket label(s) — subset of {'top_decile','top_quartile','mid','low'}. **Rankable-gated** — raises if every selected assay has `rankable=false`. Soft-excludes non-rankable assays from mixed input (surfaced in envelope `excluded_assays`). Tested-absent rows (`detection_status='not_detected'`) never match — their `metric_bucket` is nulled for display regardless of the stored value. |
| min_percentile | float \| None | None | Lower bound on `metric_percentile` (0-100). **Rankable-gated.** Tested-absent rows (`detection_status='not_detected'`) never match — their `metric_percentile` is nulled for display. |
| max_percentile | float \| None | None | Upper bound on `metric_percentile`. **Rankable-gated.** Tested-absent rows (`detection_status='not_detected'`) never match — their `metric_percentile` is nulled for display. |
| max_rank | int \| None | None | Cap on `rank_by_metric` (1 = highest). Top-N drill-down. **Rankable-gated.** Tested-absent rows (`detection_status='not_detected'`) never match — their `rank_by_metric` is nulled for display. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields in docs://tools/{name}. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, by_detection_status, by_metric_bucket, by_assay, by_compartment, by_organism, by_metric, excluded_assays, warnings, resolved_aliases, not_found, returned, truncated, offset, results
```

- **total_matching** (int): Row count in the filtered slice.
- **by_detection_status** (list[MqaByDetectionStatus]): Counts per detection_status — primary qualitative headline. 'not_detected' rows are tested-absent (real biology, kept by default — about 70% of numeric edges).
- **by_metric_bucket** (list[MqaByMetricBucket]): Counts per rank-bucket on rankable rows.
- **by_assay** (list[MqaByAssay]): Counts per assay_id. Pass these `assay_id`s to `metabolites_by_flags_assay(assay_ids=[...])` for the boolean complement.
- **by_compartment** (list[MqaByCompartment]): Counts per compartment.
- **by_organism** (list[MqaByOrganism]): Counts per organism (cross-organism by default).
- **by_metric** (list[MqaByMetric]): Per-assay precomputed-vs-filtered: pairs the filtered slice min/max with the full-assay precomputed range so the LLM can read 'top-decile slice 0.012-0.16 out of full range 0-0.16' inline.
- **excluded_assays** (list[string]): `assay_ids` soft-excluded under rankable-gating (non-rankable assays dropped when a rankable filter is set).
- **warnings** (list[string]): Human-readable rankable-gating diagnostics, bare-ID collision notes (one input → several metabolites, expanded to all), and a sibling-tool notice when a requested assay_id exists as value_kind='boolean' (genuinely found, excluded from `not_found.assay_ids` — use `metabolites_by_flags_assay` instead).
- **resolved_aliases** (object): Bare / xref metabolite inputs coerced to canonical IDs, `{input: [canonical, ...]}` — only coerced entries, across both `metabolite_ids` and `exclude_metabolite_ids`. A list longer than 1 is a collision (expanded to all; see `warnings`).
- **not_found** (MqaNotFound): Per-batch-input unknown IDs (4 buckets: assay_ids, metabolite_ids, experiment_ids, publication_doi).
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
| metric_bucket | string \| None (optional) | Bucket label ('top_decile' / 'top_quartile' / 'mid' / 'low'). Populated only on rankable assays, and null on tested-absent (`detection_status='not_detected'`) rows even then — a stored bucket from raw-zero coincidence is not a ranking signal. |
| metric_percentile | float \| None (optional) | Percentile (0-100). Populated only on rankable assays; null on tested-absent rows (see `metric_bucket`). |
| rank_by_metric | int \| None (optional) | Rank by value (1 = highest). Populated only on rankable assays; null on tested-absent rows (see `metric_bucket`). |
| detection_status | string \| None (optional) | One of 'detected', 'sporadic', 'not_detected'. 'not_detected' = tested-absent (real biology, kept by default). Numeric edge only. |
| timepoint | string \| None (optional) | Timepoint label ('4 days', '6 days'). Null on non-temporal experiments (sentinel timepoints stripped). |
| timepoint_hours | float \| None (optional) | Timepoint in hours. Null on non-temporal experiments. |
| timepoint_order | int \| None (optional) | Timepoint order index. Null on non-temporal experiments. |
| growth_phase | string \| None (optional) | Growth phase. Currently unpopulated — KG-side backfill pending. |
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
{
  "results": [
    {
      "metabolite_id": "kegg.compound:C00085",
      "name": "D-Fructose 6-phosphate",
      "kegg_compound_id": "C00085",
      "value": 0.4465,
      "value_sd": 0.0643467170879758,
      "n_replicates": 2,
      "n_non_zero": 2,
      "metric_type": "cellular_concentration",
      "metric_bucket": "top_decile",
      "metric_percentile": 100.0,
      "rank_by_metric": 1,
      "detection_status": "detected",
      "timepoint": "6 days",
      "timepoint_hours": 144.0,
      "timepoint_order": 2,
      "growth_phase": null,
      "condition_label": "control",
      "assay_id": "metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration",
      "organism_name": "Prochlorococcus MIT9313",
      "compartment": "whole_cell"
    },
    {
      "metabolite_id": "kegg.compound:C00085",
      "name": "D-Fructose 6-phosphate",
      "kegg_compound_id": "C00085",
      "value": 0.289,
      "value_sd": 0.26416093579482947,
      "n_replicates": 3,
      "n_non_zero": 2,
      "metric_type": "cellular_concentration",
      "metric_bucket": "top_decile",
      "metric_percentile": 98.41269841269842,
      "rank_by_metric": 2,
      "detection_status": "sporadic",
      "timepoint": "4 days",
      "timepoint_hours": 96.0,
      "timepoint_order": 1,
      "growth_phase": null,
      "condition_label": "control",
      "assay_id": "metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration",
      "organism_name": "Prochlorococcus MIT9313",
      "compartment": "whole_cell"
    },
    {
      "metabolite_id": "kegg.compound:C00085",
      "name": "D-Fructose 6-phosphate",
      "kegg_compound_id": "C00085",
      "value": 0.2385,
      "value_sd": 0.03747665940288703,
      "n_replicates": 2,
      "n_non_zero": 2,
      "metric_type": "cellular_concentration",
      "metric_bucket": "top_decile",
      "metric_percentile": 96.82539682539682,
      "rank_by_metric": 3,
      "detection_status": "detected",
      "timepoint": "6 days",
      "timepoint_hours": 144.0,
      "timepoint_order": 2,
      "growth_phase": null,
      "condition_label": "chitosan",
      "assay_id": "metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration",
      "organism_name": "Prochlorococcus MIT9313",
      "compartment": "whole_cell"
    },
    ...
  ],
  "total_matching": 64,
  "by_detection_status": [
    {"detection_status": "sporadic", "count": 30},
    {"detection_status": "detected", "count": 27},
    {"detection_status": "not_detected", "count": 7}
  ],
  "by_metric_bucket": [
    {"bucket": "mid", "count": 32},
    {"bucket": "low", "count": 16},
    {"bucket": "top_quartile", "count": 9},
    {"bucket": "top_decile", "count": 7}
  ],
  "by_assay": [
    {
      "assay_id": "metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration",
      "count": 64
    }
  ],
  "by_compartment": [{"compartment": "whole_cell", "count": 64}],
  "by_organism": [{"organism_name": "Prochlorococcus MIT9313", "count": 64}],
  "by_metric": [
    {
      "assay_id": "metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration",
      "name": "MIT9313 cellular metabolite concentration (fg/cell)",
      "metric_type": "",
      "count": 64,
      "filtered_value_min": 0.0,
      "filtered_value_max": 0.4465,
      "assay_value_min": 0.0,
      "assay_value_q1": 0.0010333333333333334,
      "assay_value_median": 0.0046,
      "assay_value_q3": 0.010866666666666665,
      "assay_value_max": 0.4465,
      "rankable": true
    }
  ],
  "excluded_assays": [],
  "warnings": [],
  "resolved_aliases": {},
  "not_found": {"assay_ids": [], "metabolite_ids": [], "experiment_ids": [], "publication_doi": []},
  "returned": 5,
  "truncated": true,
  "offset": 0
}
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

- Numeric arm only (`Assay_quantifies_metabolite`). Siblings: `metabolites_by_flags_assay` is the boolean-arm twin (presence flags, no values); `assays_by_metabolite` is the metabolite-anchored reverse lookup over both arms.

```mistake
A requested assay_id silently disappears from the results and not_found.assay_ids stays empty.
```

```correction
A boolean assay_id is genuinely found (it exists as `value_kind='boolean'`)
but this tool only drills numeric edges — it's excluded from
`not_found.assay_ids` and reported via a `warnings` entry naming
`metabolites_by_flags_assay` as the tool to use instead.

```

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
selected assay is non-rankable. `warnings` also carries metabolite-ID
collision notes when an ambiguous CHEBI / HMDB / MNXM input expanded to
several metabolites (see `resolved_aliases`).

```

```mistake
Expect not_found to be a flat list[str].
```

```correction
Drill-downs use a structured NotFound (4 keys: assay_ids, metabolite_ids,
experiment_ids, publication_doi) — multi-batch input → structured.
Inspect each bucket separately to see which input was bad. Mirrors
`MetNotFound` on `list_metabolites` and `GbmNotFound` on
`genes_by_metabolite`.

```

```mistake
Apply min_value=0.001 by default to 'clean' the data.
```

```correction
`min_value > 0` strips tested-absent rows (`value=0` /
`detection_status='not_detected'`). About 70% of numeric edges are
not_detected — min_value would discard the majority of measured
biology. Surface as caller choice, never default-on. See
`docs://guide/conventions`.

```

```mistake
Treat metric_bucket / metric_percentile / rank_by_metric as always populated.
```

```correction
Rankable-gated columns are null on rows whose parent assay has
`rankable=false`. Boolean assays surface in `metabolites_by_flags_assay`
instead. Per-row null on these columns means "not applicable" not
"missing data".

```

```mistake
A row with detection_status='not_detected' but a non-null metric_bucket means the KG ranked it.
```

```correction
Tested-absent rows are nulled on `metric_bucket` / `metric_percentile` /
`rank_by_metric` for display, even on a rankable assay — a raw-zero
value can otherwise tie into a high bucket/percentile purely because
most edges on the assay are zero (e.g. `value=0` landing in
'top_quartile' simply because so much of the assay's mass sits at
zero). `metric_bucket` / `min_percentile` / `max_percentile` /
`max_rank` filters never select `not_detected` rows for the
same reason — filter and display agree.

```

```mistake
growth_phase populated on every row.
```

```correction
growth_phase is currently null on every row — the schema field exists
on Experiment, but `time_point_growth_phases[]` is empty for every
metabolomics experiment in the current KG (KG-side backfill pending).
Forward-compat surface; values populate without explorer-side code
change when the upstream backfill lands.

```

```mistake
metabolites_by_quantifies_assay(metabolite_ids=['C00064'])  # then treating `C00064` in `not_found` as 'no such metabolite'
```

```correction
Bare / xref metabolite IDs on `metabolite_ids` / `exclude_metabolite_ids` are resolved via
the node's cross-references before the query runs: `C00064` →
`kegg.compound:C00064`, `CHEBI:17234` / `17234` → the `chebi_id` match,
`HMDB0000122` → `hmdb_id`, `MNXM1095050` → `mnxm_id`. Canonical forms
(`kegg.compound:` / `chebi:` / `mnx:`) pass through untouched. Coerced
inputs are listed in envelope `resolved_aliases` (`{input: [canonical, ...]}`).
CHEBI / HMDB / MNXM xrefs are not unique — an ambiguous input expands to
ALL matching metabolites and appends a `warnings` entry; pass the canonical
id to narrow. Unresolved inputs stay verbatim and surface in `not_found`
in the form you passed.

```

- See `docs://analysis/metabolites` for the 3 source pipelines decision tree and `docs://guide/conventions` for tested-absent semantics (about 70% of numeric edges are not_detected, kept by default).

## Package import equivalent

```python
from multiomics_explorer import metabolites_by_quantifies_assay

result = metabolites_by_quantifies_assay(assay_ids=...)
# returns dict with keys: total_matching, by_detection_status, by_metric_bucket, by_assay, by_compartment, by_organism, by_metric, excluded_assays, warnings, resolved_aliases, not_found, returned, truncated, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
