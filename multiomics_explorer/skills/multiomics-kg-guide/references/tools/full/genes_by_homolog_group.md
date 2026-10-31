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

## Response format

### Envelope

```expected-keys
total_matching, total_genes, total_categories, offset, genes_per_group_max, genes_per_group_median, by_organism, top_categories, top_groups, not_found_groups, not_matched_groups, not_found_organisms, not_matched_organisms, resolved_aliases, warnings, returned, truncated, results
```

- **total_matching** (int): Gene×group rows matching filters (e.g. 33)
- **total_genes** (int): Distinct genes (a gene in 2 input groups counted once, e.g. 30)
- **total_categories** (int): Distinct gene categories (e.g. 12)
- **offset** (int): Offset into full result set (e.g. 0)
- **genes_per_group_max** (int): Largest group's gene count (e.g. 13)
- **genes_per_group_median** (float): Median gene count across groups (e.g. 3.0)
- **by_organism** (list[HomologGroupOrganismBreakdown]): Member counts per organism, sorted by count desc (all)
- **top_categories** (list[HomologGroupCategoryBreakdown]): Top 5 gene categories by member count, sorted by count desc
- **top_groups** (list[HomologGroupGroupBreakdown]): Top 5 groups by member count, sorted by count desc
- **not_found_groups** (list[string]): Input group_ids not found in KG
- **not_matched_groups** (list[string]): Groups that exist but have 0 member genes after organism filter
- **not_found_organisms** (list[string]): Organism filter values matching zero Gene nodes in KG
- **not_matched_organisms** (list[string]): Organisms in KG but with zero genes in the requested groups
- **resolved_aliases** (object): Bare group_ids (e.g. 'CK_00000570', 'COG0592@2') coerced to canonical prefixed form, {input: [canonical]}. Empty when none were coerced.
- **warnings** (list[string]): Advisory diagnostics; empty when clean. Never changes which rows are returned.
- **returned** (int): Results in this response
- **truncated** (bool): True if total_matching > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0315') |
| gene_name | string \| None (optional) | Gene name (e.g. 'psbB') |
| product | string \| None (optional) | Gene product (e.g. 'photosystem II chlorophyll-binding protein CP47') |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4') |
| gene_category | string \| None (optional) | Functional category (e.g. 'Photosynthesis') |
| group_id | string | Ortholog group ID (e.g. 'cyanorak:CK_00000570') |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| gene_summary | string \| None (optional) | Concatenated summary text |
| function_description | string \| None (optional) | Curated functional description |
| consensus_product | string \| None (optional) | Group consensus product (e.g. 'photosystem II chlorophyll-binding protein CP47') |
| source | string \| None (optional) | OG source (e.g. 'cyanorak') |

## Few-shot examples

### Example 1: Find members of an ortholog group

```example-call
genes_by_homolog_group(group_ids=["cyanorak:CK_00000570"])
```

```example-response
{
  "total_matching": 96,
  "total_genes": 96,
  "total_categories": 1,
  "offset": 0,
  "genes_per_group_max": 96,
  "genes_per_group_median": 96.0,
  "by_organism": [
    {"organism_name": "Cyanobium NS01", "count": 1},
    {"organism_name": "Cyanobium PCC6307", "count": 1},
    {"organism_name": "Cyanobium PCC7001", "count": 1},
    {"organism_name": "Prochlorococcus AS9601", "count": 1},
    {"organism_name": "Prochlorococcus EQPAC1", "count": 1},
    ...
  ],
  "top_categories": [{"category": "Photosynthesis", "count": 96}],
  "top_groups": [{"group_id": "cyanorak:CK_00000570", "count": 96}],
  "not_found_groups": [],
  "not_matched_groups": [],
  "not_found_organisms": [],
  "not_matched_organisms": [],
  "resolved_aliases": {},
  "warnings": [],
  "returned": 5,
  "truncated": true,
  "results": [
    {
      "locus_tag": "CyaNS01_02480",
      "gene_name": "psbB",
      "product": "photosystem II chlorophyll-binding protein CP47",
      "organism_name": "Cyanobium NS01",
      "gene_category": "Photosynthesis",
      "group_id": "cyanorak:CK_00000570"
    },
    {
      "locus_tag": "Cyagr_1622",
      "gene_name": "psbB",
      "product": "photosystem II chlorophyll-binding protein CP47",
      "organism_name": "Cyanobium PCC6307",
      "gene_category": "Photosynthesis",
      "group_id": "cyanorak:CK_00000570"
    },
    {
      "locus_tag": "CPCC7001_890",
      "gene_name": "psbB",
      "product": "photosystem II chlorophyll-binding protein CP47",
      "organism_name": "Cyanobium PCC7001",
      "gene_category": "Photosynthesis",
      "group_id": "cyanorak:CK_00000570"
    },
    ...
  ]
}
```

### Example 2: Filter to specific organisms

```example-call
genes_by_homolog_group(group_ids=["cyanorak:CK_00000570"], organisms=["MED4", "AS9601"])
```

### Example 3: Compare membership across groups

```example-call
genes_by_homolog_group(group_ids=["cyanorak:CK_00000570", "eggnog:COG0592@2"], summary=True)
```

```example-response
{
  "total_matching": 214,
  "total_genes": 214,
  "total_categories": 2,
  "offset": 0,
  "genes_per_group_max": 118,
  "genes_per_group_median": 107.0,
  "by_organism": [
    {"organism_name": "Cyanobium NS01", "count": 2},
    {"organism_name": "Cyanobium PCC6307", "count": 2},
    {"organism_name": "Cyanobium PCC7001", "count": 2},
    {"organism_name": "Prochlorococcus AS9601", "count": 2},
    {"organism_name": "Prochlorococcus EQPAC1", "count": 2},
    ...
  ],
  "top_categories": [{"category": "Replication and repair", "count": 118}, {"category": "Photosynthesis", "count": 96}],
  "top_groups": [{"group_id": "eggnog:COG0592@2", "count": 118}, {"group_id": "cyanorak:CK_00000570", "count": 96}],
  "not_found_groups": [],
  "not_matched_groups": [],
  "not_found_organisms": [],
  "not_matched_organisms": [],
  "resolved_aliases": {},
  "warnings": [],
  "returned": 0,
  "truncated": true,
  "results": []
}
```

### Example 4: From text search to member genes

```
Step 1: search_homolog_groups(search_text="photosystem II")
        → collect group_ids from results (e.g. "cyanorak:CK_00000570")

Step 2: genes_by_homolog_group(group_ids=["cyanorak:CK_00000570"])
        → find member genes per organism

Step 3: gene_overview(locus_tags=["PMM0315", ...])
        → check data availability for discovered genes
```

## Chaining patterns

```
search_homolog_groups → genes_by_homolog_group
genes_by_homolog_group → gene_overview
genes_by_homolog_group → differential_expression_by_gene
gene_homologs → genes_by_homolog_group
```

## Common mistakes

- Bare group ids ('CK_00000570', 'COG0592@2') are accepted and coerced to canonical — check `resolved_aliases` for the mapping; prefer the prefixed form ('cyanorak:CK_00000570') to skip coercion.

- A gene in multiple input groups appears once per group — rows are gene × group, not distinct genes. Use total_genes for the deduplicated count.

- organisms is a list, not a string — use ['MED4'] not 'MED4'

- Four diagnostic buckets, all flat lists: `not_found_groups` (group id absent from the KG) / `not_matched_groups` (group exists, no member passes the organisms filter) and `not_found_organisms` / `not_matched_organisms` (organism name unknown / known but has no member in these groups). The `_groups` / `_organisms` suffixes are this tool's spelling of the not_found / not_matched pair — See docs://guide/conventions for the shared not_found / not_matched semantics.

```mistake
genes_by_homolog_group(group_ids=['photosystem'])  # passing text, not IDs
```

```correction
search_homolog_groups(search_text='photosystem')  # search first, then use IDs
```

```mistake
len(results)  # actual count
```

```correction
response['total_matching']  # use total, not len
```

- `organisms` entries are word-matched against preferred_name + name_synonyms, so a genus word (e.g. 'Alteromonas') matches every strain in that genus rather than raising ambiguous.

## Package import equivalent

```python
from multiomics_explorer import genes_by_homolog_group

result = genes_by_homolog_group(group_ids=...)
# returns dict with keys: total_matching, total_genes, total_categories, offset, genes_per_group_max, genes_per_group_median, by_organism, top_categories, top_groups, not_found_groups, not_matched_groups, not_found_organisms, not_matched_organisms, resolved_aliases, warnings, returned, truncated, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
