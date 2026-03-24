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

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_organism, by_category, score_max, score_median, returned, truncated, results
```

- **total_entries** (int): Total genes matching search text (before filters)
- **total_matching** (int): Total genes matching search + all filters
- **by_organism** (list[FunctionOrganismBreakdown]): Gene counts per organism, sorted desc
- **by_category** (list[FunctionCategoryBreakdown]): Gene counts per category, sorted desc
- **score_max** (float): Highest relevance score
- **score_median** (float): Median relevance score
- **returned** (int): Number of results returned
- **truncated** (bool): True when total_matching > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001') |
| gene_name | string \| None (optional) | Gene name (e.g. 'dnaN') |
| product | string \| None (optional) | Gene product (e.g. 'DNA polymerase III subunit beta') |
| organism_strain | string | Organism strain (e.g. 'Prochlorococcus MED4') |
| gene_category | string \| None (optional) | Functional category (e.g. 'Photosynthesis') |
| annotation_quality | int | Annotation quality 0-3 (3=best) |
| score | float | Fulltext relevance score |
| function_description | string \| None (optional) | Functional description text |
| gene_summary | string \| None (optional) | Combined gene annotation summary |

## Few-shot examples

<!-- TODO: Add examples -->

## Chaining patterns

<!-- TODO: Add chaining patterns -->

## Package import equivalent

```python
from multiomics_explorer import genes_by_function

result = genes_by_function(search_text=...)
# returns dict with keys: total_entries, total_matching, by_organism, by_category, score_max, score_median, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
