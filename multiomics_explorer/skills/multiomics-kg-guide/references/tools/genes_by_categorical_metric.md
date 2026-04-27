# genes_by_categorical_metric

## What it does

Pass `derived_metric_ids` XOR `metric_types` (one required); `categories` must be a subset of the union of selected DMs' `allowed_categories` (raises with the allowed set listed otherwise) — inspect `list_derived_metrics(value_kind='categorical')` first to see each DM's allowed set.

Categorical DM drill-down — one row per gene × DM × edge value.
`r.value` is a category label. Cross-organism by design; envelope
`by_organism` and per-row `organism_name` make cross-strain rows
self-describing. The `by_metric` envelope rollup pairs filtered-slice
category histogram (`by_category`) with full-DM precomputed
histogram (`dm_by_category`) plus the schema-declared
`allowed_categories` so callers can detect declared-but-unobserved
categories without an extra call.

Wrong-kind IDs (numeric / boolean) surface silently in
`not_found_ids` — inspect `list_derived_metrics(value_kind='categorical')`
first to pick valid categorical DMs.

`excluded_derived_metrics` and `warnings` are always `[]` (no
rankable / has_p_value gates apply to categorical DMs); kept as
envelope keys for cross-tool shape consistency with
`genes_by_numeric_metric`.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| derived_metric_ids | list[string] \| None | None | Categorical DerivedMetric node IDs. Use when the same `metric_type` appears across organisms / publications and you need to pin one. Discover IDs via `list_derived_metrics(value_kind='categorical')`. Mutually exclusive with `metric_types`. Wrong-kind IDs (numeric / boolean) surface silently in `not_found_ids`. |
| metric_types | list[string] \| None | None | Categorical metric-type tags (e.g. ['predicted_subcellular_localization', 'darkness_survival_class']). Unions every DM carrying that tag, then narrows by scoping filters. Same tag can appear across organisms (e.g. 'predicted_subcellular_localization' is on both MED4 + MIT9313). Mutually exclusive with `derived_metric_ids`. |
| organism | string \| None | None | Organism to scope the DM set to. Accepts short strain code ('MED4', 'NATL2A', 'MIT9313') or full name. Case-insensitive substring match. Single-organism is **not** enforced — omit to drill across all organisms a metric_type spans. |
| locus_tags | list[string] \| None | None | Restrict drill-down to a specific gene set (e.g. DE hits from `differential_expression_by_gene`). Filter on `g.locus_tag IN $locus_tags` post-MATCH. Genes with no edge for the selected DM produce no row. |
| experiment_ids | list[string] \| None | None | Scope to DMs from one or more experiments. |
| publication_doi | list[string] \| None | None | Scope to DMs from one or more publications. |
| compartment | string \| None | None | Sample compartment ('whole_cell', 'vesicle', 'exoproteome', 'spent_medium', 'lysate'). Exact match. |
| treatment_type | list[string] \| None | None | Treatment type(s). ANY-overlap. Case-insensitive. |
| background_factors | list[string] \| None | None | Background factor(s). ANY-overlap. Case-insensitive. |
| growth_phases | list[string] \| None | None | Growth phase(s). ANY-overlap. Case-insensitive. |
| categories | list[string] \| None | None | Filter on `r.value`: keep rows whose value is in this set. Validated against the union of the selected DMs' `allowed_categories` — unknown values raise `ValueError` listing the allowed set. E.g. ['Outer Membrane', 'Periplasmic'] for `predicted_subcellular_localization`. |
| summary | bool | False | Return summary fields only (counts, breakdowns, by_metric, diagnostics). Sugar for limit=0; results=[]. |
| verbose | bool | False | Include heavy text fields per row: gene_function_description, gene_summary, allowed_categories, plus DM context (metric_type, field_description, unit, compartment, experiment_id, publication_doi, treatment_type, background_factors, treatment, light_condition, experimental_context). |
| limit | int | 5 | Max rows to return. Paginate with `offset`. Use `summary=True` for summary-only (sets limit=0). |
| offset | int | 0 | Pagination offset (starting row, 0-indexed). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_category, top_categories, by_metric, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, returned, offset, truncated, results
```

- **total_matching** (int): Rows post-filter (gene × DM pairs).
- **total_derived_metrics** (int): Distinct DMs contributing rows.
- **total_genes** (int): Distinct genes in results.
- **by_organism** (list[GenesByNumericMetricOrganismBreakdown]): Rows per organism.
- **by_compartment** (list[GenesByNumericMetricCompartmentBreakdown]): Rows per compartment.
- **by_publication** (list[GenesByNumericMetricPublicationBreakdown]): Rows per publication.
- **by_experiment** (list[GenesByNumericMetricExperimentBreakdown]): Rows per experiment.
- **by_category** (list[GenesByCategoricalMetricCategoryFreq]): Frequency rollup of `r.value` across surviving rows. Cross-DM unioned — a category present in two DMs sums.
- **top_categories** (list[GenesByNumericMetricCategoryBreakdown]): Top 5 gene categories by count.
- **by_metric** (list[GenesByCategoricalMetricBreakdown]): Per-DM rollup: filtered-slice category histogram + full-DM precomputed histogram. Sorted by count desc.
- **genes_per_metric_max** (int): Largest per-DM gene count.
- **genes_per_metric_median** (float): Median per-DM gene count.
- **not_found_ids** (list[string]): `derived_metric_ids` inputs not present in KG (or scoped out / wrong value_kind).
- **not_matched_ids** (list[string]): `derived_metric_ids` in KG but produced 0 rows after edge-level filters.
- **not_found_metric_types** (list[string]): `metric_types` inputs that match no DM after scoping.
- **not_matched_metric_types** (list[string]): `metric_types` whose DMs produced 0 rows.
- **not_matched_organism** (string | None): `organism` arg that matched no surviving DM.
- **excluded_derived_metrics** (list[ExcludedDerivedMetric]): Always [] for categorical DMs (no rankable / has_p_value gates). Kept for cross-tool envelope-shape consistency.
- **warnings** (list[string]): Always [] for categorical DMs. Kept for cross-tool envelope-shape consistency.
- **returned** (int): Length of results list.
- **offset** (int): Pagination offset used.
- **truncated** (bool): True when total_matching > offset + returned.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0097'). |
| gene_name | string \| None (optional) | Gene symbol; null when KG has none. |
| product | string \| None (optional) | Gene product. |
| gene_category | string \| None (optional) | Coarse functional category. |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4'). |
| derived_metric_id | string | Unique parent-DM id. |
| name | string | DM human label. |
| value_kind | string | Always 'categorical' for this tool; kept for cross-tool row-shape consistency with `genes_by_numeric_metric`. |
| rankable | bool | DM-level rankable flag (always False today for categorical DMs). |
| has_p_value | bool | DM-level p-value flag (always False today for categorical DMs). |
| value | string | Category label (one of the parent DM's `allowed_categories`). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| metric_type | string \| None (optional) | Category tag. Verbose only. |
| field_description | string \| None (optional) | Detailed explanation of what this DM measures. Verbose only. |
| unit | string \| None (optional) | Measurement unit (typically null for categorical DMs). Verbose only. |
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
| allowed_categories | list[string] \| None (optional) | Schema-declared full set for this row's parent DM. Verbose only. |

## Few-shot examples

### Example 1: PSORTb membrane categories — cross-organism slice

```example-call
genes_by_categorical_metric(metric_types=['predicted_subcellular_localization'], categories=['Outer Membrane', 'Periplasmic'])
```

```example-response
{
  "total_matching": 14,
  "total_derived_metrics": 2,
  "total_genes": 14,
  "by_organism": [
    {"organism_name": "Prochlorococcus MED4", "count": 8},
    {"organism_name": "Prochlorococcus MIT9313", "count": 6}
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 14}],
  "by_publication": [{"publication_doi": "10.1126/science.1243457", "count": 14}],
  "by_category": [
    {"category": "Outer Membrane", "count": 8},
    {"category": "Periplasmic", "count": 6}
  ],
  "by_metric": [
    {"derived_metric_id": "derived_metric:pnas.1402782111:s2_med4_vesicle_proteome:predicted_subcellular_localization", "metric_type": "predicted_subcellular_localization", "name": "MED4 PSORTb localization", "value_kind": "categorical", "count": 8, "by_category": [{"category": "Outer Membrane", "count": 5}, {"category": "Periplasmic", "count": 3}], "allowed_categories": ["Cytoplasmic", "Cytoplasmic Membrane", "Periplasmic", "Outer Membrane", "Extracellular", "Unknown"], "dm_total_gene_count": 32, "dm_by_category": [{"category": "Cytoplasmic", "count": 11}, {"category": "Cytoplasmic Membrane", "count": 6}, {"category": "Outer Membrane", "count": 5}, {"category": "Periplasmic", "count": 3}, {"category": "Unknown", "count": 7}]},
    {"derived_metric_id": "derived_metric:pnas.1402782111:s2_mit9313_vesicle_proteome:predicted_subcellular_localization", "metric_type": "predicted_subcellular_localization", "name": "MIT9313 PSORTb localization", "value_kind": "categorical", "count": 6, "by_category": [{"category": "Outer Membrane", "count": 3}, {"category": "Periplasmic", "count": 3}], "allowed_categories": ["Cytoplasmic", "Cytoplasmic Membrane", "Periplasmic", "Outer Membrane", "Extracellular", "Unknown"], "dm_total_gene_count": 26, "dm_by_category": [{"category": "Cytoplasmic", "count": 9}, {"category": "Cytoplasmic Membrane", "count": 5}, {"category": "Outer Membrane", "count": 3}, {"category": "Periplasmic", "count": 3}, {"category": "Unknown", "count": 6}]}
  ],
  "top_categories": [
    {"gene_category": "Translation", "count": 4},
    {"gene_category": "Unknown", "count": 3}
  ],
  "genes_per_metric_max": 8,
  "genes_per_metric_median": 7.0,
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
    {"locus_tag": "PMM0097", "organism_name": "Prochlorococcus MED4", "derived_metric_id": "derived_metric:pnas.1402782111:s2_med4_vesicle_proteome:predicted_subcellular_localization", "name": "MED4 PSORTb localization", "value_kind": "categorical", "rankable": false, "has_p_value": false, "value": "Outer Membrane"},
    {"locus_tag": "PMM0254", "organism_name": "Prochlorococcus MED4", "derived_metric_id": "derived_metric:pnas.1402782111:s2_med4_vesicle_proteome:predicted_subcellular_localization", "name": "MED4 PSORTb localization", "value_kind": "categorical", "rankable": false, "has_p_value": false, "value": "Outer Membrane"}
  ]
}
```

### Example 2: Darkness survival classes — single-organism scoping

```example-call
genes_by_categorical_metric(metric_types=['darkness_survival_class'], categories=['darkness_axenic+darkness_coculture'])
```

```example-response
{
  "total_matching": 24,
  "total_derived_metrics": 1,
  "total_genes": 24,
  "by_organism": [{"organism_name": "Prochlorococcus NATL2A", "count": 24}],
  "by_compartment": [{"compartment": "whole_cell", "count": 24}],
  "by_category": [{"category": "darkness_axenic+darkness_coculture", "count": 24}],
  "by_metric": [
    {"derived_metric_id": "derived_metric:1462-2920.14179:darkness_survival:darkness_survival_class", "metric_type": "darkness_survival_class", "value_kind": "categorical", "count": 24, "by_category": [{"category": "darkness_axenic+darkness_coculture", "count": 24}], "allowed_categories": ["darkness_axenic", "darkness_coculture", "darkness_axenic+darkness_coculture", "neither"], "dm_total_gene_count": 1377, "dm_by_category": [{"category": "darkness_axenic", "count": 102}, {"category": "darkness_coculture", "count": 187}, {"category": "darkness_axenic+darkness_coculture", "count": 24}, {"category": "neither", "count": 1064}]}
  ],
  "not_matched_organism": null,
  "excluded_derived_metrics": [],
  "warnings": [],
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "results": [
    {"locus_tag": "PMN2A_0042", "organism_name": "Prochlorococcus NATL2A", "derived_metric_id": "derived_metric:1462-2920.14179:darkness_survival:darkness_survival_class", "value_kind": "categorical", "rankable": false, "has_p_value": false, "value": "darkness_axenic+darkness_coculture"}
  ]
}
```

### Example 3: Summary-only — full-DM histogram + allowed_categories context

```example-call
genes_by_categorical_metric(metric_types=['predicted_subcellular_localization'], summary=True)
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
  "by_category": [
    {"category": "Cytoplasmic", "count": 20},
    {"category": "Unknown", "count": 13},
    {"category": "Cytoplasmic Membrane", "count": 11},
    {"category": "Outer Membrane", "count": 8},
    {"category": "Periplasmic", "count": 6}
  ],
  "by_metric": [
    {"derived_metric_id": "derived_metric:pnas.1402782111:s2_med4_vesicle_proteome:predicted_subcellular_localization", "metric_type": "predicted_subcellular_localization", "value_kind": "categorical", "count": 32, "allowed_categories": ["Cytoplasmic", "Cytoplasmic Membrane", "Periplasmic", "Outer Membrane", "Extracellular", "Unknown"], "dm_total_gene_count": 32, "dm_by_category": [{"category": "Cytoplasmic", "count": 11}, {"category": "Cytoplasmic Membrane", "count": 6}, {"category": "Outer Membrane", "count": 5}, {"category": "Periplasmic", "count": 3}, {"category": "Unknown", "count": 7}]},
    {"derived_metric_id": "derived_metric:pnas.1402782111:s2_mit9313_vesicle_proteome:predicted_subcellular_localization", "metric_type": "predicted_subcellular_localization", "value_kind": "categorical", "count": 26, "allowed_categories": ["Cytoplasmic", "Cytoplasmic Membrane", "Periplasmic", "Outer Membrane", "Extracellular", "Unknown"], "dm_total_gene_count": 26, "dm_by_category": [{"category": "Cytoplasmic", "count": 9}, {"category": "Cytoplasmic Membrane", "count": 5}, {"category": "Outer Membrane", "count": 3}, {"category": "Periplasmic", "count": 3}, {"category": "Unknown", "count": 6}]}
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

### Example 4: DE → top hits → categorical classification intersection

```
Step 1: differential_expression_by_gene(organism="MED4", significant_only=True, limit=20)
        → extract `locus_tag` from each result row (top-20 |log2FC|).

Step 2: genes_by_categorical_metric(
          metric_types=["predicted_subcellular_localization"],
          locus_tags=[<those 20 locus_tags>])
        → which DE hits have a vesicle-PSORTb classification?
          Per-row `value` carries the category label; envelope
          `by_category` shows the slice's class distribution.

Step 3 (drill-down): gene_overview(locus_tags=[<intersected genes>])
        → routing context for the genes that are both DE-significant
          AND classified to a target compartment.
```

## Chaining patterns

```
list_derived_metrics(value_kind='categorical') → genes_by_categorical_metric(metric_types=[...], categories=[...]) → gene_overview / genes_by_function
differential_expression_by_gene → top hits → genes_by_categorical_metric(metric_types=[...], locus_tags=hits)
genes_by_categorical_metric (no organism filter) → split via envelope by_organism for cross-strain comparison
```

## Common mistakes

- Unknown category raises with the allowed-set in the error. `categories=['foo']` raises `ValueError` listing every value in the union of selected DMs' `allowed_categories`. Pull the set from `list_derived_metrics(value_kind='categorical')` verbose output, or read it from the error message itself — the tool surfaces the full union without a follow-up call.

- `allowed_categories` ⊋ `dm_by_category`. A category may be declared in `allowed_categories` (schema-level) but unobserved in any gene (absent from `dm_by_category`). Example: MED4 PSORTb declares `Extracellular` but no gene is classified that way — `dm_by_category` omits it. Both per-DM context fields appear in each `by_metric` row; inspect them together before assuming a category exists in the data.

- Sparse `rankable` / `has_p_value` echoes. Both are always `False` on every row from current categorical DMs — kept for cross-tool row-shape consistency with `genes_by_numeric_metric`, not because this tool reads them as a meaningful signal. Don't gate downstream logic on them.

```mistake
genes_by_categorical_metric(derived_metric_ids=['derived_metric:...:damping_ratio'])
```

```correction
genes_by_categorical_metric(metric_types=['predicted_subcellular_localization'])
```

## Package import equivalent

```python
from multiomics_explorer import genes_by_categorical_metric

result = genes_by_categorical_metric()
# returns dict with keys: total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_category, top_categories, by_metric, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
