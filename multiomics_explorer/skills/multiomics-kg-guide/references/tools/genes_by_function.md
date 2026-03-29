# genes_by_function

## What it does

Search genes by functional annotation text.

Full-text search across gene names, products, and functional
descriptions. Supports Lucene syntax: quoted phrases, AND/OR,
wildcards (*), fuzzy (~). Results ranked by relevance score.

For ontology-based search, use genes_by_ontology.
For gene details, use gene_overview.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string | — | Free-text query (Lucene syntax supported). E.g. 'photosystem', 'nitrogen AND transport', 'dnaN~'. |
| organism | string \| None | None | Filter by organism (case-insensitive substring). E.g. 'MED4', 'Prochlorococcus MED4'. Use list_organisms to see valid values. |
| category | string \| None | None | Filter by gene_category. E.g. 'Photosynthesis', 'Transport'. Use list_filter_values to see valid values. |
| min_quality | int | 0 | Minimum annotation_quality (0-3). 0=hypothetical, 1=has description, 2=named product, 3=well-annotated. Use 2 to skip hypothetical proteins. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include function_description and gene_summary. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_search_hits, total_matching, by_organism, by_category, score_max, score_median, returned, offset, truncated, results
```

- **total_search_hits** (int): Total genes matching search text (before organism/category/quality filters)
- **total_matching** (int): Total genes matching search + all filters
- **by_organism** (list[FunctionOrganismBreakdown]): Gene counts per organism, sorted desc
- **by_category** (list[FunctionCategoryBreakdown]): Gene counts per category, sorted desc
- **score_max** (float | None): Highest relevance score (null if 0 matches)
- **score_median** (float | None): Median relevance score (null if 0 matches)
- **returned** (int): Number of results returned
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True when total_matching > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001') |
| gene_name | string \| None (optional) | Gene name (e.g. 'dnaN') |
| product | string \| None (optional) | Gene product (e.g. 'DNA polymerase III subunit beta') |
| organism_name | string | Organism name (e.g. 'Prochlorococcus MED4') |
| gene_category | string \| None (optional) | Functional category (e.g. 'Photosynthesis') |
| annotation_quality | int | Annotation quality 0-3 (3=best) |
| score | float | Fulltext relevance score |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| function_description | string \| None (optional) | Functional description text |
| gene_summary | string \| None (optional) | Combined gene annotation summary |

## Few-shot examples

### Example 1: Search for photosynthesis genes

```example-call
genes_by_function(search_text="photosystem")
```

```example-response
{"total_search_hits": 312, "total_matching": 312, "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 42}, ...], "by_category": [{"category": "Photosynthesis", "count": 280}, ...], "score_max": 8.4, "score_median": 5.1, "returned": 5, "truncated": true, "offset": 0, "results": [{"locus_tag": "PMM0001", "gene_name": "psbA", "product": "Photosystem II D1 protein", "organism_name": "Prochlorococcus MED4", "gene_category": "Photosynthesis", "annotation_quality": 3, "score": 8.4}]}
```

### Example 2: Search with organism filter and verbose output

```example-call
genes_by_function(search_text="nitrogen transport", organism="MED4", verbose=True)
```

### Example 3: Get counts only (no rows)

```example-call
genes_by_function(search_text="chaperone", summary=True)
```

```example-response
{"total_search_hits": 87, "total_matching": 87, "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 18}, ...], "by_category": [{"category": "Protein folding and degradation", "count": 54}, ...], "score_max": 7.2, "score_median": 4.3, "returned": 0, "truncated": true, "offset": 0, "results": []}
```

### Example 4: Chaining — find genes then inspect details

```
Step 1: genes_by_function(search_text="ferredoxin", summary=True)
        → note total_matching and by_organism breakdown

Step 2: genes_by_function(search_text="ferredoxin", organism="MIT9313", limit=20)
        → collect locus_tags from results

Step 3: gene_overview(locus_tags=["PMT0001", ...])
        → get expression availability and annotation details
```

## Chaining patterns

```
genes_by_function → gene_overview
genes_by_function → gene_ontology_terms
genes_by_function → genes_by_ontology (use term IDs from gene_ontology_terms)
search_ontology → genes_by_ontology (ontology-first route, alternative to genes_by_function)
```

## Common mistakes

```mistake
genes_by_function(search_text='GO:0015977')
```

```correction
genes_by_ontology(term_ids=['go:0015977']) for ontology term lookup; genes_by_function is for free-text search
```

```mistake
len(result['results'])  # to count matches
```

```correction
result['total_matching']  # results may be truncated
```

- Use summary=True to get organism/category breakdowns without fetching gene rows

- Use min_quality=2 to skip hypothetical proteins and get better-annotated results

## Package import equivalent

```python
from multiomics_explorer import genes_by_function

result = genes_by_function(search_text=...)
# returns dict with keys: total_search_hits, total_matching, by_organism, by_category, score_max, score_median, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
