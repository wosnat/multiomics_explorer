# genes_by_homolog_group

## What it does

Find member genes of ortholog groups.

Takes group IDs from search_homolog_groups or gene_homologs and
returns member genes per organism. One row per gene × group.

For group discovery by text, use search_homolog_groups first.
For gene → group direction, use gene_homologs.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| group_ids | list[string] | — | Ortholog group IDs (from search_homolog_groups or gene_homologs). E.g. ['cyanorak:CK_00000570']. |
| organism | string \| None | None | Filter by organism (case-insensitive substring). E.g. 'MED4', 'Alteromonas'. Use list_organisms to see valid values. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include gene_summary, function_description, consensus_product, source in results. |
| limit | int | 5 | Max results. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, total_genes, by_organism, by_category, by_group, not_found, returned, truncated, results
```

- **total_matching** (int): Gene×group rows matching filters (e.g. 33)
- **total_genes** (int): Distinct genes (a gene in 2 input groups counted once, e.g. 30)
- **by_organism** (list[HomologGroupOrganismBreakdown]): Member counts per organism, sorted by count desc
- **by_category** (list[HomologGroupCategoryBreakdown]): Member counts per gene category, sorted by count desc
- **by_group** (list[HomologGroupGroupBreakdown]): Member counts per input group, sorted by count desc
- **not_found** (list[string]): Input group_ids not found in KG
- **returned** (int): Results in this response
- **truncated** (bool): True if total_matching > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0315') |
| gene_name | string \| None (optional) | Gene name (e.g. 'psbB') |
| product | string \| None (optional) | Gene product (e.g. 'photosystem II chlorophyll-binding protein CP47') |
| organism_strain | string | Organism (e.g. 'Prochlorococcus MED4') |
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
{"total_matching": 9, "total_genes": 9, "by_organism": [{"organism": "Prochlorococcus MED4", "count": 1}], "by_category": [{"category": "Photosynthesis", "count": 9}], "by_group": [{"group_id": "cyanorak:CK_00000570", "count": 9}], "not_found": [], "returned": 5, "truncated": true, "results": [{"locus_tag": "A9601_03391", "gene_name": "psbB", "product": "photosystem II chlorophyll-binding protein CP47", "organism_strain": "Prochlorococcus AS9601", "gene_category": "Photosynthesis", "group_id": "cyanorak:CK_00000570"}]}
```

### Example 2: Filter to one organism

```example-call
genes_by_homolog_group(group_ids=["cyanorak:CK_00000570"], organism="MED4")
```

### Example 3: Compare membership across groups

```example-call
genes_by_homolog_group(group_ids=["cyanorak:CK_00000570", "eggnog:COG0592@2"], summary=True)
```

```example-response
{"total_matching": 22, "total_genes": 13, "by_group": [{"group_id": "eggnog:COG0592@2", "count": 13}, {"group_id": "cyanorak:CK_00000570", "count": 9}], "returned": 0, "truncated": true, "results": []}
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

- group_ids must be full IDs with prefix (e.g. 'cyanorak:CK_00000570', not 'CK_00000570')

- A gene in multiple input groups appears once per group — rows are gene × group, not distinct genes. Use total_genes for the deduplicated count.

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

## Package import equivalent

```python
from multiomics_explorer import genes_by_homolog_group

result = genes_by_homolog_group(group_ids=...)
# returns dict with keys: total_matching, total_genes, by_organism, by_category, by_group, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
