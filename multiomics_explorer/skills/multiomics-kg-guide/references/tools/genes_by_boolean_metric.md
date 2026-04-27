# genes_by_boolean_metric

## What it does

Pass `derived_metric_ids` XOR `metric_types` (one required); wrong-kind IDs (numeric / categorical) surface silently in `not_found_ids` — inspect `list_derived_metrics(value_kind='boolean')` first to pick valid boolean DMs.

Boolean DM drill-down — one row per gene × DM × edge value. `r.value`
is the string-typed bool ('true' / 'false'). Cross-organism by
design; envelope `by_organism` and per-row `organism_name` make
cross-strain rows self-describing. The `by_metric` envelope rollup
pairs filtered-slice true/false tallies with full-DM precomputed
counts (`dm_true_count`, `dm_false_count`) so callers can read "32
of 32 MED4 vesicle-proteome members" directly.

**Positive-only storage gotcha:** every current boolean DM has
`dm.flag_false_count=0`; `flag=False` returns zero rows today. The
`by_metric[*].dm_false_count` echo makes this self-evident without
a follow-up call.

`excluded_derived_metrics` and `warnings` are always `[]` (no
rankable / has_p_value gates apply to boolean DMs); kept as
envelope keys for cross-tool shape consistency with
`genes_by_numeric_metric`.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| derived_metric_ids | list[string] \| None | None | Boolean DerivedMetric node IDs. Use when the same `metric_type` appears across organisms / publications and you need to pin one. Discover IDs via `list_derived_metrics(value_kind='boolean')`. Mutually exclusive with `metric_types`. Wrong-kind IDs (numeric / categorical) surface silently in `not_found_ids`. |
| metric_types | list[string] \| None | None | Boolean metric-type tags (e.g. ['vesicle_proteome_member', 'periodic_in_coculture_LD']). Unions every DM carrying that tag, then narrows by scoping filters. Same tag can appear across organisms (e.g. 'vesicle_proteome_member' is on both MED4 + MIT9313). Mutually exclusive with `derived_metric_ids`. |
| organism | string \| None | None | Organism to scope the DM set to. Accepts short strain code ('MED4', 'NATL2A', 'MIT9313') or full name. Case-insensitive substring match. Single-organism is **not** enforced — omit to drill across all organisms a metric_type spans. |
| locus_tags | list[string] \| None | None | Restrict drill-down to a specific gene set (e.g. DE hits from `differential_expression_by_gene`). Filter on `g.locus_tag IN $locus_tags` post-MATCH. Genes with no edge for the selected DM produce no row. |
| experiment_ids | list[string] \| None | None | Scope to DMs from one or more experiments. |
| publication_doi | list[string] \| None | None | Scope to DMs from one or more publications. |
| compartment | string \| None | None | Sample compartment ('whole_cell', 'vesicle', 'exoproteome', 'spent_medium', 'lysate'). Exact match. |
| treatment_type | list[string] \| None | None | Treatment type(s) (e.g. ['diel']). ANY-overlap. Case-insensitive. |
| background_factors | list[string] \| None | None | Background factor(s) (e.g. ['axenic', 'light']). ANY-overlap. Case-insensitive. |
| growth_phases | list[string] \| None | None | Growth phase(s). ANY-overlap. Case-insensitive. |
| flag | bool \| None | None | Filter on `r.value`: True keeps `'true'` edges, False keeps `'false'` edges. Coerced to the string-typed bool stored in the KG (BioCypher constraint). **flag=False returns zero rows today** — current KG stores only positive (true) edges; inspect `by_metric[*].dm_false_count` (always 0 today) before assuming a gene is 'not flagged'. |
| summary | bool | False | Return summary fields only (counts, breakdowns, by_metric, diagnostics). Sugar for limit=0; results=[]. |
| verbose | bool | False | Include heavy text fields per row: gene_function_description, gene_summary, plus DM context (metric_type, field_description, unit, compartment, experiment_id, publication_doi, treatment_type, background_factors, treatment, light_condition, experimental_context). |
| limit | int | 5 | Max rows to return. Paginate with `offset`. Use `summary=True` for summary-only (sets limit=0). |
| offset | int | 0 | Pagination offset (starting row, 0-indexed). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_value, top_categories, by_metric, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, returned, offset, truncated, results
```

- **total_matching** (int): Rows post-filter (gene × DM pairs).
- **total_derived_metrics** (int): Distinct DMs contributing rows.
- **total_genes** (int): Distinct genes in results.
- **by_organism** (list[GenesByNumericMetricOrganismBreakdown]): Rows per organism.
- **by_compartment** (list[GenesByNumericMetricCompartmentBreakdown]): Rows per compartment.
- **by_publication** (list[GenesByNumericMetricPublicationBreakdown]): Rows per publication.
- **by_experiment** (list[GenesByNumericMetricExperimentBreakdown]): Rows per experiment.
- **by_value** (list[GenesByBooleanMetricValueBreakdown]): Frequency rollup of `r.value` across surviving rows. Today every row is 'true' (positive-only KG storage).
- **top_categories** (list[GenesByNumericMetricCategoryBreakdown]): Top 5 gene categories by count.
- **by_metric** (list[GenesByBooleanMetricBreakdown]): Per-DM rollup: filtered-slice true/false counts + full-DM precomputed tallies. Sorted by count desc.
- **genes_per_metric_max** (int): Largest per-DM gene count.
- **genes_per_metric_median** (float): Median per-DM gene count.
- **not_found_ids** (list[string]): `derived_metric_ids` inputs not present in KG (or scoped out / wrong value_kind).
- **not_matched_ids** (list[string]): `derived_metric_ids` in KG but produced 0 rows after edge-level filters.
- **not_found_metric_types** (list[string]): `metric_types` inputs that match no DM after scoping.
- **not_matched_metric_types** (list[string]): `metric_types` whose DMs produced 0 rows.
- **not_matched_organism** (string | None): `organism` arg that matched no surviving DM.
- **excluded_derived_metrics** (list[ExcludedDerivedMetric]): Always [] for boolean DMs (no rankable / has_p_value gates). Kept for cross-tool envelope-shape consistency.
- **warnings** (list[string]): Always [] for boolean DMs. Kept for cross-tool envelope-shape consistency.
- **returned** (int): Length of results list.
- **offset** (int): Pagination offset used.
- **truncated** (bool): True when total_matching > offset + returned.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0090'). |
| gene_name | string \| None (optional) | Gene symbol; null when KG has none. |
| product | string \| None (optional) | Gene product. |
| gene_category | string \| None (optional) | Coarse functional category. |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4'). |
| derived_metric_id | string | Unique parent-DM id. |
| name | string | DM human label. |
| value_kind | string | Always 'boolean' for this tool; kept for cross-tool row-shape consistency with `genes_by_numeric_metric`. |
| rankable | bool | DM-level rankable flag (always False today for boolean DMs). |
| has_p_value | bool | DM-level p-value flag (always False today for boolean DMs). |
| value | string | 'true' or 'false' (string-typed bool — see KG-spec BioCypher constraint). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| metric_type | string \| None (optional) | Category tag. Verbose only. |
| field_description | string \| None (optional) | Detailed explanation of what this DM measures. Verbose only. |
| unit | string \| None (optional) | Measurement unit (typically null for boolean DMs). Verbose only. |
| compartment | string \| None (optional) | Sample compartment. Verbose only. |
| experiment_id | string \| None (optional) | Parent experiment id. Verbose only. |
| publication_doi | string \| None (optional) | Parent publication DOI. Verbose only. |
| treatment_type | list[string] \| None (optional) | Treatment type(s). Verbose only. |
| background_factors | list[string] \| None (optional) | Background factor(s). Verbose only. |
| treatment | string \| None (optional) | Treatment description in plain language. Verbose only. |
| light_condition | string \| None (optional) | Light regime. Verbose only. |
| experimental_context | string \| None (optional) | Longer experimental setup description. Verbose only. |
| gene_function_description | string \| None (optional) | Gene functional description (gene-level). Verbose only. |
| gene_summary | string \| None (optional) | Gene summary text (gene-level). Verbose only. |

## Few-shot examples

### Example 1: Vesicle proteome cross-organism — same metric_type spans two strains

```example-call
genes_by_boolean_metric(metric_types=['vesicle_proteome_member'])
```

```example-response
{
  "total_matching": 58,
  "total_derived_metrics": 2,
  "total_genes": 58,
  "by_organism": [
    {"organism_name": "Prochlorococcus MED4", "count": 32},
    {"organism_name": "Prochlorococcus MIT9313", "count": 26}
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 58}],
  "by_publication": [{"publication_doi": "10.1126/science.1243457", "count": 58}],
  "by_value": [{"value": "true", "count": 58}],
  "by_metric": [
    {"derived_metric_id": "derived_metric:pnas.1402782111:s2_med4_vesicle_proteome:vesicle_proteome_member", "metric_type": "vesicle_proteome_member", "name": "MED4 vesicle proteome member", "value_kind": "boolean", "count": 32, "true_count": 32, "false_count": 0, "dm_total_gene_count": 32, "dm_true_count": 32, "dm_false_count": 0},
    {"derived_metric_id": "derived_metric:pnas.1402782111:s2_mit9313_vesicle_proteome:vesicle_proteome_member", "metric_type": "vesicle_proteome_member", "name": "MIT9313 vesicle proteome member", "value_kind": "boolean", "count": 26, "true_count": 26, "false_count": 0, "dm_total_gene_count": 26, "dm_true_count": 26, "dm_false_count": 0}
  ],
  "top_categories": [
    {"gene_category": "Translation", "count": 12},
    {"gene_category": "Unknown", "count": 9}
  ],
  "genes_per_metric_max": 32,
  "genes_per_metric_median": 29.0,
  "not_found_ids": [],
  "not_matched_ids": [],
  "not_found_metric_types": [],
  "not_matched_metric_types": [],
  "not_matched_organism": null,
  "excluded_derived_metrics": [],
  "warnings": [],
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "results": [
    {"locus_tag": "PMM0090", "gene_name": null, "product": null, "gene_category": null, "organism_name": "Prochlorococcus MED4", "derived_metric_id": "derived_metric:pnas.1402782111:s2_med4_vesicle_proteome:vesicle_proteome_member", "name": "MED4 vesicle proteome member", "value_kind": "boolean", "rankable": false, "has_p_value": false, "value": "true"},
    {"locus_tag": "PMM0097", "gene_name": null, "product": null, "gene_category": null, "organism_name": "Prochlorococcus MED4", "derived_metric_id": "derived_metric:pnas.1402782111:s2_med4_vesicle_proteome:vesicle_proteome_member", "name": "MED4 vesicle proteome member", "value_kind": "boolean", "rankable": false, "has_p_value": false, "value": "true"}
  ]
}
```

### Example 2: Scoped to one strain — NATL2A periodic-LD flag set

```example-call
genes_by_boolean_metric(metric_types=['periodic_in_coculture_LD'], organism='NATL2A')
```

```example-response
{
  "total_matching": 5,
  "total_derived_metrics": 1,
  "total_genes": 5,
  "by_organism": [{"organism_name": "Prochlorococcus NATL2A", "count": 5}],
  "by_compartment": [{"compartment": "whole_cell", "count": 5}],
  "by_value": [{"value": "true", "count": 5}],
  "by_metric": [
    {"derived_metric_id": "derived_metric:1462-2920.14179:s2_natl2a_periodic_LD:periodic_in_coculture_LD", "metric_type": "periodic_in_coculture_LD", "name": "NATL2A periodic in coculture L:D", "value_kind": "boolean", "count": 5, "true_count": 5, "false_count": 0, "dm_total_gene_count": 1377, "dm_true_count": 5, "dm_false_count": 0}
  ],
  "not_found_metric_types": [],
  "not_matched_metric_types": [],
  "not_matched_organism": null,
  "excluded_derived_metrics": [],
  "warnings": [],
  "returned": 5,
  "offset": 0,
  "truncated": false,
  "results": [
    {"locus_tag": "PMN2A_0123", "organism_name": "Prochlorococcus NATL2A", "derived_metric_id": "derived_metric:1462-2920.14179:s2_natl2a_periodic_LD:periodic_in_coculture_LD", "value_kind": "boolean", "rankable": false, "has_p_value": false, "value": "true"}
  ]
}
```

### Example 3: Summary-only — full-DM context without per-row drill-down

```example-call
genes_by_boolean_metric(metric_types=['vesicle_proteome_member'], summary=True)
```

```example-response
{
  "total_matching": 58,
  "total_derived_metrics": 2,
  "total_genes": 58,
  "by_organism": [
    {"organism_name": "Prochlorococcus MED4", "count": 32},
    {"organism_name": "Prochlorococcus MIT9313", "count": 26}
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 58}],
  "by_value": [{"value": "true", "count": 58}],
  "by_metric": [
    {"derived_metric_id": "derived_metric:pnas.1402782111:s2_med4_vesicle_proteome:vesicle_proteome_member", "metric_type": "vesicle_proteome_member", "value_kind": "boolean", "count": 32, "true_count": 32, "false_count": 0, "dm_total_gene_count": 32, "dm_true_count": 32, "dm_false_count": 0},
    {"derived_metric_id": "derived_metric:pnas.1402782111:s2_mit9313_vesicle_proteome:vesicle_proteome_member", "metric_type": "vesicle_proteome_member", "value_kind": "boolean", "count": 26, "true_count": 26, "false_count": 0, "dm_total_gene_count": 26, "dm_true_count": 26, "dm_false_count": 0}
  ],
  "genes_per_metric_max": 32,
  "genes_per_metric_median": 29.0,
  "excluded_derived_metrics": [],
  "warnings": [],
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "results": []
}
```

### Example 4: DE → top hits → boolean flag intersection

```
Step 1: differential_expression_by_gene(organism="MED4", significant_only=True, limit=20)
        → extract `locus_tag` from each result row (top-20 |log2FC|).

Step 2: genes_by_boolean_metric(
          metric_types=["vesicle_proteome_member"],
          locus_tags=[<those 20 locus_tags>])
        → which DE hits are also vesicle-proteome members?
          Per-row `value="true"` confirms the flag; envelope
          `total_matching` shows the intersection size.

Step 3 (drill-down): gene_overview(locus_tags=[<intersected genes>])
        → routing context for the genes that are both DE-significant
          AND vesicle-detected.
```

## Chaining patterns

```
list_derived_metrics(value_kind='boolean') → genes_by_boolean_metric(metric_types=[...]) → gene_overview / genes_by_function
differential_expression_by_gene → top hits → genes_by_boolean_metric(metric_types=[...], locus_tags=hits)
genes_by_boolean_metric (no organism filter) → split via envelope by_organism for cross-strain comparison
```

## Common mistakes

- Positive-only storage in current KG. `flag=False` returns zero rows today because every materialized boolean edge is `r.value="true"` (slice-1 spec §"KG invariants" §4 — `dm.flag_false_count=0` on every current DM). Inspect `by_metric[*].dm_false_count` (always 0 today) before assuming a gene is "not flagged false". Mirrors the numeric tool's "p-value filter on current KG" gotcha — surface exists for future DMs.

- Sparse `rankable` / `has_p_value` echoes. Both are always `False` on every row from current boolean DMs — kept for cross-tool row-shape consistency with `genes_by_numeric_metric`, not because this tool reads them as a meaningful signal. Don't gate downstream logic on them.

```mistake
genes_by_boolean_metric(derived_metric_ids=['derived_metric:...:damping_ratio'])
```

```correction
genes_by_boolean_metric(metric_types=['vesicle_proteome_member'])
```

## Package import equivalent

```python
from multiomics_explorer import genes_by_boolean_metric

result = genes_by_boolean_metric()
# returns dict with keys: total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_value, top_categories, by_metric, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
