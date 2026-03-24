# list_filter_values

## What it does

List valid values for categorical filters used across tools.

Returns valid values and counts for the requested filter type.
Use the returned values as filter parameters in `genes_by_function`
(category filter).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| filter_type | string | gene_category | Which filter's valid values to return. 'gene_category': values for the category filter in genes_by_function. |

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

### Example 2: Find genes in a category

```
Step 1: list_filter_values(filter_type="gene_category")
        → extract value strings from results

Step 2: genes_by_function(search_text="photosystem", category="Photosynthesis")
        → get photosynthesis genes matching "photosystem"
```

## Chaining patterns

```
list_filter_values → genes_by_function(category=...)
```

## Common mistakes

- count is summed across all organisms — a category with count=770 may cover genes in 10+ organisms

```mistake
list_filter_values(category='Photosynthesis')  # no such param
```

```correction
list_filter_values(filter_type='gene_category')  # then pass value to genes_by_function
```

## Package import equivalent

```python
from multiomics_explorer import list_filter_values

result = list_filter_values()
# returns dict with keys: filter_type, total_entries, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
