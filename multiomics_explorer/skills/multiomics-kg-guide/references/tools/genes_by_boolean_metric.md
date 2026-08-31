# genes_by_boolean_metric

## What it does

Boolean DerivedMetric edges — one row per gene × DM × edge value; cross-organism.

Use for flag membership after `list_derived_metrics`; values `genes_by_numeric_metric`, labels `genes_by_categorical_metric`.
Filters: derived_metric_ids XOR metric_types, organism, locus_tags, flag_value, plus the publication / experiment / condition filters.
Returns: by_value, by_metric (vs full-DM, incl. false_count), by_organism, not_found_ids, not_found_metric_types, not_matched_ids, not_matched_metric_types; one row = one edge.
docs://tools/genes_by_boolean_metric; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| derived_metric_ids | list[string] \| None | None | Boolean DerivedMetric node IDs. Use when the same `metric_type` appears across organisms / publications and you need to pin one. Discover IDs via `list_derived_metrics(value_kind='boolean')`. Mutually exclusive with `metric_types`. An id that exists as a different kind (numeric / categorical) moves to `not_matched_ids` with a `warnings` entry naming the sibling tool. |
| metric_types | list[string] \| None | None | Boolean metric-type tags (e.g. ['vesicle_proteome_member', 'periodic_in_coculture_LD']). Unions every DM carrying that tag, then narrows by scoping filters. Same tag can span organisms / publications — pin one specific DM via `derived_metric_ids` instead. Mutually exclusive with `derived_metric_ids`. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| locus_tags | list[string] \| None | None | Restrict drill-down to a specific gene set (e.g. DE hits from `differential_expression_by_gene`). Filter on `g.locus_tag IN $locus_tags` post-MATCH. Genes with no edge for the selected DM produce no row. |
| experiment_ids | list[string] \| None | None | Scope to DMs from one or more experiments. |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| flag_value | bool \| None | None | Filter on `r.value`: True keeps `'flagged'` edges, False keeps `'not_flagged'` edges (tested-absent — real biology, stored on 11 of 27 boolean DMs; the rest are positive-only and return 0 rows for False). Check `by_metric[*].false_count` before reading an absent gene as 'not flagged' vs 'not assessed'. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 25 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Vesicle proteome cross-organism — same metric_type spans two strains

```python
genes_by_boolean_metric(metric_types=['vesicle_proteome_member'])
```

## Response sketch

```expected-keys
total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_value, top_categories, by_metric, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, returned, offset, truncated, results
```

Result row: `locus_tag, gene_name, product, gene_category, organism_name, derived_metric_id, name, value_kind, rankable, has_p_value, value, metric_type, …`

## Common mistakes

- Two storage conventions coexist. 11 of 27 boolean DMs (Biller 2022, Voigt 2014, Hennon 2015, Steglich 2010) store `r.value="not_flagged"` edges, so `flag_value=False` returns tested-absent rows there; the rest (Biller 2014 / 2018, Coe 2016) are positive-only and return 0 rows for `flag_value=False`. Read `by_metric[*].false_count` before reading an absent gene as "not flagged" rather than "not assessed"; `dm_false_count` is the full-DM precomputed twin (0 on positive-only DMs). Contrast `metabolites_by_flags_assay`, whose edges always store both states.

- Sparse `rankable` / `has_p_value` echoes. Both are always `False` on every row from boolean DMs in the current KG — kept for cross-tool row-shape consistency with `genes_by_numeric_metric`, not because this tool reads them as a meaningful signal. Don't gate downstream logic on them.

```mistake
genes_by_boolean_metric(derived_metric_ids=['derived_metric:...:damping_ratio'])
```

```correction
genes_by_boolean_metric(metric_types=['vesicle_proteome_member'])
```

## Chaining patterns

- list_derived_metrics(value_kind='boolean') → genes_by_boolean_metric(metric_types=[...]) → gene_overview / genes_by_function
- differential_expression_by_gene → top hits → genes_by_boolean_metric(metric_types=[...], locus_tags=hits)
- genes_by_boolean_metric (no organism filter) → split via envelope by_organism for cross-strain comparison

Full reference (all examples, full response format, verbose fields): `docs://tools/genes_by_boolean_metric/full`
