# list_filter_values

## What it does

List valid values for categorical filters used across tools.

Returns valid values and counts for the requested filter type.
Use the returned values as filter parameters in `genes_by_function`
(category filter).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| filter_type | string ('gene_category', 'brite_tree', 'growth_phase') | gene_category | Which filter's valid values to return. 'gene_category': values for the category filter in genes_by_function. 'brite_tree': BRITE tree names for the tree filter in ontology tools. 'growth_phase': physiological states of the culture at sampling time (timepoint-level condition, not gene-specific). |

## Response format

### Envelope

```expected-keys
filter_type, total_entries, returned, truncated, results
```

- **filter_type** (string): The filter type returned (e.g. 'gene_category')
- **total_entries** (int): Total distinct values for this filter (e.g. 26)
- **returned** (int): Number of results returned (e.g. 26)
- **truncated** (bool): True if total_entries > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| value | string | Filter value (e.g. 'Photosynthesis', 'Transport', 'Unknown') |
| count | int | Number of genes/items with this value (e.g. 770) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: only for brite_tree filter, e.g. 'ko01000') |

## Few-shot examples

### Example 1: List gene categories

```example-call
list_filter_values(filter_type="gene_category")
```

```example-response
{
  "filter_type": "gene_category",
  "total_entries": 26,
  "returned": 26,
  "truncated": false,
  "results": [
    {"value": "Unknown", "count": 12183},
    {"value": "Coenzyme metabolism", "count": 2146},
    {"value": "Stress response and adaptation", "count": 2073}
  ]
}
```

### Example 2: List BRITE trees

```example-call
list_filter_values(filter_type="brite_tree")
```

```example-response
{
  "filter_type": "brite_tree",
  "total_entries": 12,
  "returned": 12,
  "truncated": false,
  "results": [
    {"value": "enzymes", "tree_code": "ko01000", "count": 1776},
    {"value": "transporters", "tree_code": "ko02000", "count": 84},
    {"value": "protein families: signaling and cellular processes", "tree_code": "ko04131", "count": 150}
  ]
}
```

### Example 3: Find genes in a category

```
Step 1: list_filter_values(filter_type="gene_category")
        → extract value strings from results

Step 2: genes_by_function(search_text="photosystem", category="Photosynthesis")
        → get photosynthesis genes matching "photosystem"
```

### Example 4: Discover BRITE trees, then scope enrichment

```
Step 1: list_filter_values(filter_type="brite_tree")
        → discover available trees (e.g. "transporters", "enzymes")

Step 2: ontology_landscape(organism="MED4", ontology="brite", tree="transporters")
        → check coverage and pick level

Step 3: pathway_enrichment(organism="MED4", experiment_ids=[...], ontology="brite", tree="transporters", level=1)
        → run enrichment scoped to transporter categories
```

## Chaining patterns

```
list_filter_values → genes_by_function(category=...)
list_filter_values('brite_tree') → ontology_landscape(tree=...) → pathway_enrichment(tree=...)
```

## Common mistakes

- count is summed across all organisms — a category with count=770 may cover genes in 10+ organisms

- For brite_tree: count is the number of ontology terms in the tree, not genes. Use ontology_landscape to check gene coverage.

```mistake
list_filter_values(category='Photosynthesis')  # no such param
```

```correction
list_filter_values(filter_type='gene_category')  # then pass value to genes_by_function
```

- growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — NOT a gene-specific property

## Package import equivalent

```python
from multiomics_explorer import list_filter_values

result = list_filter_values()
# returns dict with keys: filter_type, total_entries, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
