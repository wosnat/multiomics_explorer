# differential_expression_by_ortholog

## What it does

DE framed by ortholog group across organisms — one row per group × experiment × timepoint, values are member gene counts per status.

Use to compare a group's response across strains; per-gene detail is `differential_expression_by_gene`, membership `genes_by_homolog_group`.
Filters: group_ids, organisms, experiment_ids, direction, significant_only, growth_phases.
Returns: by_organism, rows_by_status, by_table_scope, top_groups, a not_found / not_matched pair per input; one row = group × experiment × timepoint.
docs://tools/differential_expression_by_ortholog; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| group_ids | list[string] | — | Ortholog group IDs (from search_homolog_groups or gene_homologs). E.g. ['cyanorak:CK_00000570']. Bare ids are accepted (e.g. 'CK_00000570', 'COG0592@2') and coerced to canonical (see `resolved_aliases`). |
| organisms | list[string] \| None | None | Organisms, each word-matched as `organism`. Omit for all. |
| experiment_ids | list[string] \| None | None | Filter to these experiments. Get IDs from list_experiments. |
| direction | string ('up', 'down', 'both') \| None | None | Filter by expression direction. `'up'` / `'down'` restrict to one arm. `'both'` is the union of significant up + significant down — functionally identical to `direction=None, significant_only=True`; pick whichever spelling is clearer at the call site. Default `None` is unchanged. |
| significant_only | bool | False | If true, return only statistically significant rows. |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Example

### Expression across orthologs in a group

```python
differential_expression_by_ortholog(group_ids=["cyanorak:CK_00000570"])
```

## Response sketch

```expected-keys
total_matching, matching_genes, matching_groups, experiment_count, median_abs_log2fc, max_abs_log2fc, returned, offset, truncated, by_organism, rows_by_status, rows_by_treatment_type, rows_by_background_factors, rows_by_growth_phase, by_table_scope, top_groups, top_experiments, not_found_groups, not_matched_groups, not_found_organisms, not_matched_organisms, not_found_experiments, not_matched_experiments, resolved_aliases, warnings, results
```

Result row: `group_id, consensus_gene_name, consensus_product, experiment_id, treatment_type, background_factors, organism_name, coculture_partner, timepoint, timepoint_hours, timepoint_order, genes_with_expression, …`

## Common mistakes

- group_ids must be full IDs with prefix (e.g. 'cyanorak:CK_00000570')

- organisms is a list, not a string — use ['MED4'] not 'MED4'

- This tool does NOT enforce single organism — that is the point

## Chaining patterns

- search_homolog_groups → differential_expression_by_ortholog
- gene_homologs → differential_expression_by_ortholog
- genes_by_homolog_group (triage) → differential_expression_by_ortholog
- differential_expression_by_ortholog → genes_by_homolog_group(organisms=[...]) → differential_expression_by_gene per organism (per-gene detail behind a group × experiment row; loop it in Python per docs://guide/python_api)

Full reference (all examples, full response format, verbose fields): `docs://tools/differential_expression_by_ortholog/full`
