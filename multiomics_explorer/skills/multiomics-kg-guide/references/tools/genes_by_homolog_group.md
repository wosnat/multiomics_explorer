# genes_by_homolog_group

## What it does

Group IDs to their member genes per organism — one row per gene × group.

Use to enumerate a group's members; for a gene's own groups use `gene_homologs`, for expression across organisms `differential_expression_by_ortholog`.
Filters: group_ids, organisms.
Returns: by_organism, top_categories, top_groups, genes-per-group stats, and a not_found / not_matched pair for each of groups and organisms; one row = (locus_tag, group_id).
docs://tools/genes_by_homolog_group; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| group_ids | list[string] | — | Ortholog group IDs (from search_homolog_groups or gene_homologs). E.g. ['cyanorak:CK_00000570']. Bare ids are accepted (e.g. 'CK_00000570', 'COG0592@2') and coerced to canonical (see `resolved_aliases`). |
| organisms | list[string] \| None | None | Organisms, each word-matched as `organism`. Omit for all. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Example

### Find members of an ortholog group

```python
genes_by_homolog_group(group_ids=["cyanorak:CK_00000570"])
```

## Response sketch

```expected-keys
total_matching, total_genes, total_categories, offset, genes_per_group_max, genes_per_group_median, by_organism, top_categories, top_groups, not_found_groups, not_matched_groups, not_found_organisms, not_matched_organisms, resolved_aliases, warnings, returned, truncated, results
```

Result row: `locus_tag, gene_name, product, organism_name, gene_category, group_id, gene_summary, function_description, consensus_product, source`

## Common mistakes

- group_ids must be full IDs with prefix (e.g. 'cyanorak:CK_00000570', not 'CK_00000570')

- A gene in multiple input groups appears once per group — rows are gene × group, not distinct genes. Use total_genes for the deduplicated count.

- organisms is a list, not a string — use ['MED4'] not 'MED4'

## Chaining patterns

- search_homolog_groups → genes_by_homolog_group
- genes_by_homolog_group → gene_overview
- genes_by_homolog_group → differential_expression_by_gene
- gene_homologs → genes_by_homolog_group

Full reference (all examples, full response format, verbose fields): `docs://tools/genes_by_homolog_group/full`
