# gene_response_profile

## What it does

Cross-experiment rollup for ONE organism (inferred from locus_tags) — one row per gene, responses bucketed per treatment group with timepoints collapsed, broadest first.

Use to see which treatments a gene set responds to; for log2FC per timepoint use `differential_expression_by_gene`.
Filters: locus_tags, organism, treatment_type, background_factors, experiment_ids, group_by.
Returns: genes_queried, genes_with_response, not_found, no_expression, filtered_out; one row = one gene with response_summary and groups_tested_not_responded.
docs://tools/gene_response_profile.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags. E.g. ['PMM0370', 'PMM0920']. Get these from resolve_gene / gene_overview. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| experiment_ids | list[string] \| None | None | Restrict to specific experiments. Get these from list_experiments. |
| group_by | string ('treatment_type', 'experiment') | treatment_type | Group response summary by treatment_type (aggregates across experiments) or experiment (one entry per experiment). |
| limit | int | 50 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Gene response overview

```python
gene_response_profile(locus_tags=["PMM0370", "PMM0920"])
```

## Response sketch

```expected-keys
organism_name, genes_queried, genes_with_response, not_found, no_expression, filtered_out, warnings, returned, offset, truncated, results
```

Result row: `locus_tag, gene_name, product, gene_category, groups_responded, groups_not_responded, groups_tested_not_responded, groups_not_known, response_summary`

## Common mistakes

- Sibling tools: gene_response_profile is the cross-experiment ROLLUP (one row per gene, responses bucketed per treatment group, timepoints collapsed). differential_expression_by_gene is the row-level view (gene × experiment × timepoint with log2fc / padj). Profile first to see which treatments matter, then drill into one experiment with differential_expression_by_gene.

```mistake
Assuming groups_not_known means 'gene does not respond to this treatment'
```

```correction
groups_not_known means no expression data exists — the gene was not profiled or not reported for that treatment. Check experiments_total in the response_summary for coverage. groups_tested_not_responded is the stronger 'absent but inferred-tested' bucket (all experiments in the group report a full-coverage scope).
```

- treatment_type / background_factors / growth_phase values are LIVE vocabularies read from the KG, not enums. An unknown treatment_type value (e.g. 'Fe' instead of 'iron') reports in the envelope `warnings` (e.g. "treatment_type value 'Fe' matched nothing — valid values: ... (list_filter_values(filter_type='treatment_type'))") — check `warnings` before trusting an empty or reduced result. Check list_filter_values(filter_type='growth_phase') or list_experiments(summary=True)'s by_treatment_type / by_background_factors rollup before filtering. Current treatment values are short nouns (nitrogen, light, carbon, iron, darkness, phosphorus, salt, viral, coculture, diel, ...); background_factors are light, axenic, coculture, darkness, diel, viral, chemical. Here the group keys of response_summary and the treatment_type filter use those values.

## Chaining patterns

- genes_by_function → gene_response_profile
- genes_by_ontology → gene_response_profile
- gene_overview → gene_response_profile (check expression_edge_count first)
- gene_response_profile → differential_expression_by_gene (drill into specific experiment)

Full reference (all examples, full response format, verbose fields): `docs://tools/gene_response_profile/full`
