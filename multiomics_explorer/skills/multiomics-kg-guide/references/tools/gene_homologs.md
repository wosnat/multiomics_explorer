# gene_homologs

## What it does

Ortholog group memberships for a gene batch — one row per gene × group, most-specific (curated) first.

Use to find a gene's groups before a cross-organism comparison; for a group's members use `genes_by_homolog_group`, for text search `search_homolog_groups`.
Filters: locus_tags, source, taxonomic_level, max_specificity_rank.
Returns: by_organism, by_source, top_cyanorak_roles, not_found, no_groups; one row = (locus_tag, group_id, source, taxonomic_level).
docs://tools/gene_homologs; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845']. |
| source | string \| None | None | Filter by OG source: 'cyanorak' or 'eggnog'. |
| taxonomic_level | string \| None | None | Filter by taxonomic level. E.g. 'curated', 'Prochloraceae', 'Bacteria'. |
| max_specificity_rank | int \| None | None | Cap group breadth. 0=curated only, 1=+family, 2=+order, 3=+domain (all). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int \| None | None | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Example

### Look up ortholog groups for a gene

```python
gene_homologs(locus_tags=["PMM0001"])
```

## Response sketch

```expected-keys
total_matching, by_organism, by_source, returned, offset, truncated, not_found, no_groups, top_cyanorak_roles, top_cog_categories, warnings, results
```

Result row: `locus_tag, organism_name, group_id, consensus_gene_name, consensus_product, taxonomic_level, source, specificity_rank, member_count, organism_count, genera, has_cross_genus_members, …`

## Common mistakes

- A gene typically belongs to 1-4 groups: one cyanorak curated group (Pro/Syn only) plus up to three eggNOG groups at nested taxonomic levels (e.g. Bacteria-level COG, Cyanobacteria, Prochloraceae). Rows are gene × group — use source / taxonomic_level / max_specificity_rank to pick one level.

- not_found means the gene doesn't exist in the KG; no_groups means the gene exists but has no ortholog group membership. `no_groups` is this tool's name for the not_matched bucket — see docs://guide/conventions for the shared not_found / not_matched semantics.

- For member genes within a group, use genes_by_homolog_group (not this tool)

## Chaining patterns

- resolve_gene → gene_homologs → genes_by_homolog_group
- search_homolog_groups → genes_by_homolog_group → gene_homologs

Full reference (all examples, full response format, verbose fields): `docs://tools/gene_homologs/full`
