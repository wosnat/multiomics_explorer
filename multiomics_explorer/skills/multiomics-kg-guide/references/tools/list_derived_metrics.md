# list_derived_metrics

## What it does

Discover DerivedMetric nodes — non-DE, column-level evidence (rhythmicity flags, diel amplitudes, survival classes).

Use as the DM-family pre-flight: read value_kind, rankable and allowed_categories here, since the drill-downs raise on an unsupported filter; one gene's values are `gene_derived_metrics`.
Filters: search_text, organism, metric_types, value_kind, rankable, has_p_value, plus compartment / publication / experiment / condition.
Returns: by_value_kind, by_metric_type, by_organism, by_compartment; one row = one DerivedMetric.
docs://tools/list_derived_metrics; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Full-text search over DM name and field_description. Examples: 'diel amplitude', 'darkness survival', 'peak time'. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| metric_types | list[string] \| None | None | Filter by metric_type tags (e.g. 'diel_amplitude_protein_log2', 'periodic_in_coculture_LD'). The same metric_type may appear across organisms / publications — use derived_metric_ids to pin one specific DM when that matters. |
| value_kind | string ('numeric', 'boolean', 'categorical') \| None | None | Filter by value kind. Determines which drill-down tool applies: 'numeric' → genes_by_numeric_metric, 'boolean' → genes_by_boolean_metric, 'categorical' → genes_by_categorical_metric. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| omics_type | list[string] \| None | None | Keep experiments whose omics_type is in this list. Values: list_filter_values('omics_type'). |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| experiment_ids | list[string] \| None | None | Filter by one or more Experiment node ids. |
| derived_metric_ids | list[string] \| None | None | Look up specific DMs by their unique id (matches `derived_metric_id` on each result). Use to pin one DM when the same metric_type appears across publications or organisms. |
| rankable | bool \| None | None | Filter to DMs that support rank / percentile / bucket analysis. Set to True before calling `genes_by_numeric_metric` with `metric_bucket`, `min/max_percentile`, or `max_rank` — those filters require rankable=True on every selected DM. See `docs://guide/conventions` (DM family gating). |
| has_p_value | bool \| None | None | Filter to DMs that carry statistical p-values. Set to True before using `significant_only` / `max_adjusted_p_value` on drill-downs. No DM in the current KG carries p-values, so has_p_value=True returns zero rows — kept because drill-down p-value filters raise when no selected DM supports them. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 20 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Orient — what DerivedMetrics exist in the KG?

```python
list_derived_metrics(summary=True)
```

## Response sketch

```expected-keys
total_entries, total_matching, by_organism, by_value_kind, by_metric_type, by_compartment, by_omics_type, by_treatment_type, by_background_factors, by_growth_phase, score_max, score_median, returned, offset, truncated, warnings, results
```

Result row: `derived_metric_id, name, metric_type, value_kind, rankable, has_p_value, unit, allowed_categories, field_description, organism_name, experiment_id, publication_doi, …`

## Common mistakes

- Call this FIRST before drill-downs. Inspect rankable / has_p_value / value_kind / allowed_categories / compartment here — the downstream drill-down tools (genes_by_numeric_metric, genes_by_boolean_metric, genes_by_categorical_metric) hard-fail (by design) when the selected DM set doesn't support the requested filter. E.g. passing metric_bucket=['top_decile'] with a non-rankable DM raises; passing significant_only=True when no selected DM has has_p_value=True raises.

- metric_type is a category tag, not a primary key — the same metric_type can appear across organisms or publications (periodic_in_coculture_LD exists once for NATL2A and once for MIT1002). Use derived_metric_ids to pin one specific DM; use metric_types to union across every DM with that tag.

- has_p_value=True returns zero rows in the current KG — no DM currently carries p-values. The filter exists for forward-compat; drill-down p-value filters (significant_only, max_adjusted_p_value) will raise with a diagnostic error.

## Chaining patterns

- list_derived_metrics → gene_derived_metrics(locus_tags, derived_metric_ids)
- list_derived_metrics(value_kind='numeric', rankable=True) → genes_by_numeric_metric(derived_metric_ids, metric_bucket=[...])
- list_derived_metrics(value_kind='boolean') → genes_by_boolean_metric(derived_metric_ids, flag_value=True)
- list_derived_metrics(value_kind='categorical') → genes_by_categorical_metric(derived_metric_ids, categories=[...])
- list_derived_metrics → genes_by_<kind>_metric → metabolites_by_gene — inspect the chemistry of DM-flagged genes (DM rows don't carry chemistry; chain through the locus_tags returned by the drill-down). See `docs://analysis/metabolites`.

Full reference (all examples, full response format, verbose fields): `docs://tools/list_derived_metrics/full`
