# search_homolog_groups

## What it does

Lucene search over ortholog groups (consensus product, consensus gene name, description).

Use to find group IDs from text; for one gene's groups use `gene_homologs`, for member genes `genes_by_homolog_group`.
Filters: search_text, source, taxonomic_level, max_specificity_rank, cyanorak_roles, cog_categories.
Returns: by_source, by_level, score stats, top_cyanorak_roles, top_cog_categories; one row = one ortholog group.
docs://tools/search_homolog_groups; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string | — | Search query (Lucene syntax — boolean operators, phrase matching, wildcards). Searches consensus_product, consensus_gene_name, description, functional_description. See `docs://guide/conventions` for Lucene scoring. |
| source | string \| None | None | Filter by OG source: 'cyanorak' or 'eggnog'. |
| taxonomic_level | string \| None | None | Filter by taxonomic level. E.g. 'curated', 'Prochloraceae', 'Bacteria'. |
| max_specificity_rank | int \| None | None | Cap group breadth. 0=curated only, 1=+family, 2=+order, 3=+domain (all). |
| cyanorak_roles | list[string] \| None | None | Filter by CyanorakRole term IDs. OR within list. E.g. ['cyanorak.role:G.3', 'cyanorak.role:J.8']. |
| cog_categories | list[string] \| None | None | Filter by CogFunctionalCategory term IDs. OR within list. E.g. ['cog.category:C', 'cog.category:J']. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Example

### Search by function

```python
search_homolog_groups(search_text="photosynthesis")
```

## Response sketch

```expected-keys
total_entries, total_matching, by_source, by_level, score_max, score_median, top_cyanorak_roles, top_cog_categories, returned, offset, truncated, results
```

Result row: `group_id, group_name, consensus_gene_name, consensus_product, source, taxonomic_level, specificity_rank, member_count, organism_count, score, description, functional_description, …`

## Common mistakes

- Searching by group ID (e.g. 'COG0592') will not work — group IDs are not in the fulltext index. Use the group_id from results directly.

```mistake
len(results)  # actual result count
```

```correction
response['total_matching']  # use total, not len
```

- Hyphens in search text are Lucene operators — use spaces instead (e.g. 'beta glycosyltransferase' not 'beta-glycosyltransferase')

## Chaining patterns

- search_homolog_groups → genes_by_homolog_group → differential_expression_by_ortholog
- gene_homologs → inspect group → search_homolog_groups for similar

Full reference (all examples, full response format, verbose fields): `docs://tools/search_homolog_groups/full`
