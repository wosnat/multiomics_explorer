# search_homolog_groups

## What it does

Search ortholog groups by text (Lucene). Returns group IDs for
use with genes_by_homolog_group.

Searches across consensus_product, consensus_gene_name, description,
and functional_description fields.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string | — | Search query (Lucene syntax). Searches consensus_product, consensus_gene_name, description, functional_description. |
| source | string \| None | None | Filter by OG source: 'cyanorak' or 'eggnog'. |
| taxonomic_level | string \| None | None | Filter by taxonomic level. E.g. 'curated', 'Prochloraceae', 'Bacteria'. |
| max_specificity_rank | int \| None | None | Cap group breadth. 0=curated only, 1=+family, 2=+order, 3=+domain (all). |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include description, functional_description, genera, has_cross_genus_members in results. |
| limit | int | 5 | Max results. |

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_source, by_level, score_max, score_median, returned, truncated, results
```

- **total_entries** (int): Total OrthologGroup nodes in KG (e.g. 21122)
- **total_matching** (int): Groups matching search + filters (e.g. 884)
- **by_source** (list[SearchHomologGroupsSourceBreakdown]): Groups per source, sorted by count desc
- **by_level** (list[SearchHomologGroupsLevelBreakdown]): Groups per taxonomic level, sorted by count desc
- **score_max** (float | None): Highest Lucene score (null if 0 matches, e.g. 6.13)
- **score_median** (float | None): Median Lucene score (null if 0 matches, e.g. 1.06)
- **returned** (int): Results in this response (0 when summary=true)
- **truncated** (bool): True if total_matching > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| group_id | string | OG identifier (e.g. 'cyanorak:CK_00000570') |
| group_name | string | Raw OG name (e.g. 'CK_00000570') |
| consensus_gene_name | string \| None (optional) | Consensus gene name (e.g. 'psbB'). Often null. |
| consensus_product | string | Consensus product (e.g. 'photosystem II chlorophyll-binding protein CP47') |
| source | string | Source database (e.g. 'cyanorak') |
| taxonomic_level | string | Taxonomic scope (e.g. 'curated') |
| specificity_rank | int | 0=curated, 1=family, 2=order, 3=domain (e.g. 0) |
| member_count | int | Total genes in group (e.g. 9) |
| organism_count | int | Distinct organisms (e.g. 9) |
| score | float | Lucene relevance score (e.g. 5.23) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| description | string \| None (optional) | Functional narrative from eggNOG (e.g. 'photosynthesis') |
| functional_description | string \| None (optional) | Derived from member gene roles (e.g. 'Photosynthesis and respiration > Photosystem II') |
| genera | list[string] \| None (optional) | Genera represented (e.g. ['Prochlorococcus', 'Synechococcus']) |
| has_cross_genus_members | string \| None (optional) | 'cross_genus' or 'single_genus' |

## Few-shot examples

### Example 1: Search by function

```example-call
search_homolog_groups(search_text="photosynthesis")
```

```example-response
{"total_entries": 21122, "total_matching": 884, "by_source": [{"source": "eggnog", "count": 647}, {"source": "cyanorak", "count": 237}], "by_level": [{"taxonomic_level": "Bacteria", "count": 218}, {"taxonomic_level": "curated", "count": 237}], "score_max": 6.13, "score_median": 1.06, "returned": 5, "truncated": true, "results": [{"group_id": "eggnog:30SSF@2", "group_name": "30SSF@2", "consensus_gene_name": "psbJ", "consensus_product": "photosystem II reaction center protein PsbJ", "source": "eggnog", "taxonomic_level": "Bacteria", "specificity_rank": 3, "member_count": 13, "organism_count": 13, "score": 6.13}]}
```

### Example 2: Filter to curated Cyanorak groups

```example-call
search_homolog_groups(search_text="kinase", source="cyanorak", max_specificity_rank=0)
```

### Example 3: Find groups then get member genes

```
Step 1: search_homolog_groups(search_text="nitrogen regulatory")
        → extract group_id values from results

Step 2: genes_by_homolog_group(group_ids=["cyanorak:CK_00000468"])
        → see member genes per organism
```

## Chaining patterns

```
search_homolog_groups → genes_by_homolog_group → differential_expression_by_ortholog
gene_homologs → inspect group → search_homolog_groups for similar
```

## Common mistakes

- Searching by group ID (e.g. 'COG0592') will not work — group IDs are not in the fulltext index. Use the group_id from results directly.

```mistake
len(results)  # actual result count
```

```correction
response['total_matching']  # use total, not len
```

- Hyphens in search text are Lucene operators — use spaces instead (e.g. 'beta glycosyltransferase' not 'beta-glycosyltransferase')

## Package import equivalent

```python
from multiomics_explorer import search_homolog_groups

result = search_homolog_groups(search_text=...)
# returns dict with keys: total_entries, total_matching, by_source, by_level, score_max, score_median, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
