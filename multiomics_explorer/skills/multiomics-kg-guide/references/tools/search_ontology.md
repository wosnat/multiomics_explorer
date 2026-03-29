# search_ontology

## What it does

Browse ontology terms by text search (fuzzy, Lucene syntax).

Returns term IDs for use with genes_by_ontology. Supports fuzzy (~),
wildcards (*), exact phrases ("..."), boolean (AND, OR).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string | — | Search query (Lucene syntax). E.g. 'replication', 'oxido*', 'transport AND membrane'. |
| ontology | string | — | Ontology to search: 'go_bp', 'go_mf', 'go_cc', 'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam'. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

## Response format

### Envelope

```expected-keys
total_entries, total_matching, score_max, score_median, returned, offset, truncated, results
```

- **total_entries** (int): Total terms in this ontology (e.g. 847)
- **total_matching** (int): Terms matching the search (e.g. 31)
- **score_max** (float | None): Highest relevance score (null if 0 matches, e.g. 5.23)
- **score_median** (float | None): Median relevance score (null if 0 matches, e.g. 2.1)
- **returned** (int): Results in this response (0 when summary=true)
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if total_matching > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| id | string | Term ID (e.g. 'go:0006260') |
| name | string | Term name (e.g. 'DNA replication') |
| score | float | Fulltext relevance score (e.g. 5.23) |

## Few-shot examples

### Example 1: Search GO biological processes

```example-call
search_ontology(search_text="replication", ontology="go_bp")
```

```example-response
{
  "total_entries": 2448,
  "total_matching": 31,
  "score_max": 2.48,
  "score_median": 1.78,
  "returned": 5,
  "truncated": true,
  "results": [
    {"id": "go:0006260", "name": "DNA replication", "score": 2.48},
    {"id": "go:0006261", "name": "DNA-templated DNA replication", "score": 2.41},
    ...
  ]
}
```

### Example 2: Summary only (how many terms match?)

```example-call
search_ontology(search_text="transport", ontology="go_bp", summary=True)
```

### Example 3: From search to gene discovery

```
Step 1: search_ontology(search_text="replication", ontology="go_bp")
        → collect term IDs from results (e.g. "go:0006260")

Step 2: genes_by_ontology(term_ids=["go:0006260"], ontology="go_bp")
        → find genes annotated to these terms (with hierarchy expansion)

Step 3: gene_overview(locus_tags=["PMM0845", ...])
        → check data availability for discovered genes
```

## Chaining patterns

```
search_ontology → genes_by_ontology
search_ontology → genes_by_ontology → gene_overview
```

## Common mistakes

- search_ontology finds term IDs — use genes_by_ontology to find genes annotated to those terms

- This tool searches term names only — it does not traverse the ontology hierarchy

```mistake
search_ontology(search_text='PMM0845', ontology='go_bp')  # searching for a gene
```

```correction
resolve_gene(identifier='PMM0845')  # use resolve_gene for gene lookups
```

## Package import equivalent

```python
from multiomics_explorer import search_ontology

result = search_ontology(search_text=..., ontology=...)
# returns dict with keys: total_entries, total_matching, score_max, score_median, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
