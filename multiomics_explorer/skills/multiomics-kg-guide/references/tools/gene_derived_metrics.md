# gene_derived_metrics

## What it does

DerivedMetric annotations for a gene batch in ONE organism (inferred when omitted) — one row per gene × DM with a polymorphic value.

Use for a gene's whole DM profile; for edge-level filtering pivot to the `genes_by_{numeric,boolean,categorical}_metric` trio.
Filters: locus_tags, organism, metric_types, value_kind, derived_metric_ids, plus the compartment / publication / condition filters.
Returns: by_value_kind, by_metric_type, by_metric, genes_with_metrics, not_found, not_matched; one row = (locus_tag, derived_metric_id, value).
docs://tools/gene_derived_metrics; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up (e.g. ['PMM1714', 'PMM0001']). Required, non-empty. Single organism enforced — locus_tags must all resolve to the same organism (or pair with `organism` to disambiguate). |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| metric_types | list[string] \| None | None | Filter by metric_type tags (e.g. 'diel_amplitude_protein_log2'). Same metric_type may appear across publications — pair with publication_dois or use derived_metric_ids to pin one specific DM. |
| value_kind | string ('numeric', 'boolean', 'categorical') \| None | None | Restrict to one DM kind. Each kind has a different `value` column type — 'numeric' → float, 'boolean' → 'flagged'/'not_flagged', 'categorical' → category string. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| derived_metric_ids | list[string] \| None | None | Look up specific DMs by their unique id. Use to pin one DM when the same metric_type appears across publications. Pair with `list_derived_metrics`. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Gene with all three DM kinds (boolean + categorical + numeric)

```python
gene_derived_metrics(locus_tags=["PMM1714"])
```

## Response sketch

```expected-keys
total_matching, total_derived_metrics, genes_with_metrics, genes_without_metrics, not_found, not_matched, by_value_kind, by_metric_type, by_metric, by_compartment, by_treatment_type, by_background_factors, by_publication, returned, offset, truncated, warnings, results
```

Result row: `locus_tag, gene_name, derived_metric_id, value_kind, name, value, rankable, has_p_value, rank_by_metric, metric_percentile, metric_bucket, adjusted_p_value, …`

## Common mistakes

- The `value` column is polymorphic — branch on each row's `value_kind` (`'numeric'` → float, `'boolean'` → `'flagged'`/`'not_flagged'` string, `'categorical'` → category string). Numeric rows additionally have `rank_by_metric`, `metric_percentile`, `metric_bucket` populated when their parent DM is rankable; null otherwise (e.g. `peak_time_protein_h`).

- For numeric edge filtering (metric_bucket / percentile / rank / value thresholds), pivot to `genes_by_numeric_metric`. This tool intentionally has no edge-level numeric filters — it is the gene-anchor surface only.

- `not_matched` ≠ no DM signal at all. `not_matched` lists genes that exist in the KG but have zero DM rows AFTER the applied filters. A gene with only boolean DM signal called with `value_kind='numeric'` lands in `not_matched`. Inspect `gene_overview`'s per-row `derived_metric_count` / `derived_metric_value_kinds` (verbose adds per-kind counts) for unfiltered availability.

## Chaining patterns

- gene_derived_metrics → genes_by_numeric_metric(derived_metric_ids, metric_bucket=[...])
- differential_expression_by_gene → gene_derived_metrics(locus_tags)
- resolve_gene → gene_derived_metrics(locus_tags)

Full reference (all examples, full response format, verbose fields): `docs://tools/gene_derived_metrics/full`
