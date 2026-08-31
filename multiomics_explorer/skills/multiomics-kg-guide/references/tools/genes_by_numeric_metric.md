# genes_by_numeric_metric

## What it does

Numeric DerivedMetric edges — one row per gene × DM with its raw value; cross-organism.

Use for value, percentile, bucket or rank cutoffs after `list_derived_metrics`; flags `genes_by_boolean_metric`, labels `genes_by_categorical_metric`.
Filters: derived_metric_ids XOR metric_types, organism, locus_tags, min/max_value, min/max_percentile, metric_bucket, max_rank.
Returns: by_metric (vs full-DM), by_organism, excluded_derived_metrics, not_found_ids, not_found_metric_types, not_matched_ids, not_matched_metric_types; one row = one edge.
docs://tools/genes_by_numeric_metric; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| derived_metric_ids | list[string] \| None | None | DerivedMetric node IDs to drill into. Use when the same `metric_type` appears across publications / organisms and you need to pin one. Discover IDs via `list_derived_metrics`. Mutually exclusive with `metric_types`. An id that exists as a different kind (boolean / categorical) moves to `not_matched_ids` with a `warnings` entry naming the sibling tool. |
| metric_types | list[string] \| None | None | Metric-type tags (e.g. ['damping_ratio', 'diel_amplitude_protein_log2']). Unions every DM carrying that tag, then narrows by scoping filters. Same tag can span organisms / publications — pin one specific DM via `derived_metric_ids` instead. Mutually exclusive with `derived_metric_ids`. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| locus_tags | list[string] \| None | None | Restrict drill-down to a specific gene set (e.g. DE hits from `differential_expression_by_gene`). Filter on `g.locus_tag IN $locus_tags` post-MATCH. Genes with no edge for the selected DM produce no row (silent — surfaced via `total_genes` shortfall). |
| experiment_ids | list[string] \| None | None | Scope to DMs from one or more experiments. |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| min_value | float \| None | None | Lower bound on `r.value`. Always applicable — no gate. Use for raw-threshold queries on non-rankable DMs (e.g. mascot probability >= 99). |
| max_value | float \| None | None | Upper bound on `r.value`. Always applicable. |
| min_percentile | float \| None | None | Lower bound on `r.metric_percentile` (0-100). **Rankable-gated** — raises if every selected DM has `rankable=False`. Soft-excludes non-rankable DMs from mixed input, surfaced in `excluded_derived_metrics`. |
| max_percentile | float \| None | None | Upper bound on `r.metric_percentile`. **Rankable-gated.** |
| metric_bucket | list[string ('top_decile', 'top_quartile', 'mid', 'low')] \| None | None | Bucket label(s). **Rankable-gated.** Buckets are decile / quartile splits computed at import time per DM. |
| max_rank | int \| None | None | Cap on `r.rank_by_metric` (1 = highest). Use for top-N drill-down. **Rankable-gated.** |
| significant_only | bool | False | Filter to `r.significant='significant'`. **has_p_value-gated** — raises in the current KG (no DM has p-values yet). Forward-compat surface; check `list_derived_metrics(has_p_value=True)` before using. |
| max_adjusted_p_value | float \| None | None | Upper bound on `r.adjusted_p_value`. **has_p_value-gated**. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 25 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Canonical worked example — top-decile damping_ratio

```python
genes_by_numeric_metric(metric_types=['damping_ratio'], metric_bucket=['top_decile'])
```

## Response sketch

```expected-keys
total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_metric, top_categories, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, returned, offset, truncated, results
```

Result row: `locus_tag, gene_name, product, gene_category, organism_name, derived_metric_id, name, value_kind, rankable, has_p_value, value, rank_by_metric, …`

## Common mistakes

- Non-rankable DM + rankable-gated filter. Calling with `metric_types=['peak_time_transcript_h']` + `metric_bucket=['top_decile']` raises — `peak_time_transcript_h` is non-rankable. Inspect `list_derived_metrics(value_kind='numeric', rankable=True)` to see which DMs support `metric_bucket` / `min_percentile` / `max_percentile` / `max_rank`. Mixed rankable/non-rankable DM sets don't raise — instead the envelope's `excluded_derived_metrics` + `warnings` pinpoint the excluded ones.

- P-value filter on current KG. `significant_only=True` or `max_adjusted_p_value=0.05` raises in the current KG because no DM has `has_p_value='p_value'`. The surface exists for future DMs; check `list_derived_metrics(has_p_value=True)` first.

- Sparse columns in results. `rank_by_metric` / `metric_percentile` / `metric_bucket` are null in rows from non-rankable DMs (e.g. `peak_time_*_h`); don't treat null as missing data — it's gate-driven. Per-row `rankable` (echoed from the parent DM) tells you which to expect.

## Chaining patterns

- list_derived_metrics(value_kind='numeric', rankable=True) → genes_by_numeric_metric(derived_metric_ids=[...], metric_bucket=[...])
- differential_expression_by_gene → top hits → genes_by_numeric_metric(metric_types=[...], locus_tags=hits)
- genes_by_numeric_metric → gene_overview(locus_tags=results)

Full reference (all examples, full response format, verbose fields): `docs://tools/genes_by_numeric_metric/full`
