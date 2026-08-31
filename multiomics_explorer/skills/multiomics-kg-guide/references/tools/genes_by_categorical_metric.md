# genes_by_categorical_metric

## What it does

Categorical DerivedMetric edges — one row per gene × DM × edge value; cross-organism.

Use to slice genes by a category label after `list_derived_metrics`; values `genes_by_numeric_metric`, flags `genes_by_boolean_metric`.
Filters: derived_metric_ids XOR metric_types, organism, locus_tags, categories, plus the publication / experiment / condition filters.
Returns: by_category, by_metric (vs full-DM, allowed_categories), by_organism, not_found_ids, not_found_metric_types, not_matched_ids, not_matched_metric_types; one row = one edge.
docs://tools/genes_by_categorical_metric; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| derived_metric_ids | list[string] \| None | None | Categorical DerivedMetric node IDs. Use when the same `metric_type` appears across organisms / publications and you need to pin one. Discover IDs via `list_derived_metrics(value_kind='categorical')`. Mutually exclusive with `metric_types`. An id that exists as a different kind (numeric / boolean) moves to `not_matched_ids` with a `warnings` entry naming the sibling tool. |
| metric_types | list[string] \| None | None | Categorical metric-type tags (e.g. ['predicted_subcellular_localization', 'darkness_survival_class']). Unions every DM carrying that tag, then narrows by scoping filters. Same tag can span organisms / publications — pin one specific DM via `derived_metric_ids` instead. Mutually exclusive with `derived_metric_ids`. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| locus_tags | list[string] \| None | None | Restrict drill-down to a specific gene set (e.g. DE hits from `differential_expression_by_gene`). Filter on `g.locus_tag IN $locus_tags` post-MATCH. Genes with no edge for the selected DM produce no row. |
| experiment_ids | list[string] \| None | None | Scope to DMs from one or more experiments. |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| categories | list[string] \| None | None | Filter on `r.value`: keep rows whose value is in this set. Validated against the union of the selected DMs' `allowed_categories` — unknown values raise `ValueError` listing the allowed set. E.g. ['Outer Membrane', 'Periplasmic'] for `predicted_subcellular_localization`. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 25 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### PSORTb membrane categories — cross-organism slice

```python
genes_by_categorical_metric(metric_types=['predicted_subcellular_localization'], categories=['Outer Membrane', 'Periplasmic'])
```

## Response sketch

```expected-keys
total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_category, top_categories, by_metric, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, returned, offset, truncated, results
```

Result row: `locus_tag, gene_name, product, gene_category, organism_name, derived_metric_id, name, value_kind, rankable, has_p_value, value, metric_type, …`

## Common mistakes

- Unknown category raises with the allowed-set in the error. `categories=['foo']` raises `ValueError` listing every value in the union of selected DMs' `allowed_categories`. Pull the set from `list_derived_metrics(value_kind='categorical')` verbose output, or read it from the error message itself — the tool surfaces the full union without a follow-up call.

- `allowed_categories` ⊋ `dm_by_category`. A category may be declared in `allowed_categories` (schema-level) but unobserved in any gene (absent from `dm_by_category`). Example: MED4 PSORTb declares `Extracellular` but no gene is classified that way — `dm_by_category` omits it. Both per-DM context fields appear in each `by_metric` row; inspect them together before assuming a category exists in the data.

- Sparse `rankable` / `has_p_value` echoes. Both are always `False` on every row from categorical DMs in the current KG — kept for cross-tool row-shape consistency with `genes_by_numeric_metric`, not because this tool reads them as a meaningful signal. Don't gate downstream logic on them.

## Chaining patterns

- list_derived_metrics(value_kind='categorical') → genes_by_categorical_metric(metric_types=[...], categories=[...]) → gene_overview / genes_by_function
- differential_expression_by_gene → top hits → genes_by_categorical_metric(metric_types=[...], locus_tags=hits)
- genes_by_categorical_metric (no organism filter) → split via envelope by_organism for cross-strain comparison

Full reference (all examples, full response format, verbose fields): `docs://tools/genes_by_categorical_metric/full`
