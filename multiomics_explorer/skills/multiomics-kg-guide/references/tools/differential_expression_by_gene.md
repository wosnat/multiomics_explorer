# differential_expression_by_gene

## What it does

DE rows for ONE organism (inferred from locus_tags / experiment_ids) — one row per gene × experiment × timepoint, sorted by |log2FC|.

Use for row-level fold changes and timepoint dynamics; a cross-experiment rollup is `gene_response_profile`, cross-organism `differential_expression_by_ortholog`.
Filters: organism, locus_tags, experiment_ids, direction, significant_only, growth_phases.
Returns: rows_by_status, by_table_scope, experiments, not_found, no_expression, filtered_out; one row = gene × experiment × timepoint.
docs://tools/differential_expression_by_gene; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| locus_tags | list[string] \| None | None | Gene locus tags. E.g. ['PMM0001', 'PMM0845']. Get these from resolve_gene / gene_overview. |
| experiment_ids | list[string] \| None | None | Experiment IDs to restrict to. Get these from list_experiments. |
| direction | string ('up', 'down', 'both') \| None | None | Filter by expression direction. `'up'` / `'down'` restrict to one arm. `'both'` is the union of significant up + significant down — functionally identical to `direction=None, significant_only=True`; pick whichever spelling is clearer at the call site. Default `None` is unchanged. |
| significant_only | bool | False | If true, return only statistically significant results. |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Example

### Organism overview (summary only)

```python
differential_expression_by_gene(organism="MED4", summary=True)
```

## Response sketch

```expected-keys
organism_name, matching_genes, total_matching, rows_by_status, median_abs_log2fc, max_abs_log2fc, experiment_count, rows_by_treatment_type, rows_by_background_factors, rows_by_growth_phase, by_table_scope, top_categories, experiments, not_found, no_expression, filtered_out, warnings, not_found_experiments, not_matched_experiments, returned, offset, truncated, results
```

Result row: `locus_tag, gene_name, experiment_id, treatment_type, timepoint, timepoint_hours, timepoint_order, log2fc, padj, rank, rank_up, rank_down, …`

## Common mistakes

```mistake
Interpreting absence of a row as 'no change' when truncated=true
```

```correction
Check truncated flag; use summary=True for reliable counts or increase limit
```

```mistake
Assuming no_expression means 'not differentially expressed'
```

```correction
no_expression means no data available — gene may not have been profiled in those experiments
```

```mistake
Reading an empty `results=[]` as 'no DE response' when experiment_ids was passed
```

```correction
Check not_found_experiments (typo'd id) and not_matched_experiments (id real but no edges satisfy the filter — e.g. vesicle proteomics, or a too-strict significant_only). Empty results + non-empty not_matched_experiments means the filter eliminated every row, not that the gene didn't respond.
```

## Chaining patterns

- genes_by_function → differential_expression_by_gene
- genes_by_ontology → differential_expression_by_gene
- gene_overview → differential_expression_by_gene (check expression_edge_count first)
- list_experiments → differential_expression_by_gene (filter by table_scope there, pass experiment_ids)
- differential_expression_by_gene → list_experiments(experiment_ids=[...]) to get the partner organism of a coculture experiment — `coculture_partner` is verbose-only in the compact experiments[] envelope

Full reference (all examples, full response format, verbose fields): `docs://tools/differential_expression_by_gene/full`
