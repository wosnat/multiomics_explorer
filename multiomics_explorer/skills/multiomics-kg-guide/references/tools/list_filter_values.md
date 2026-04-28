# list_filter_values

## What it does

List valid values for categorical filters used across tools.

Returns valid values and counts for the requested filter type.
Use the returned values as filter parameters in `genes_by_function`
(category filter).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| filter_type | string ('gene_category', 'brite_tree', 'growth_phase', 'metric_type', 'value_kind', 'compartment') | gene_category | Which categorical filter to enumerate. 'gene_category' / 'brite_tree' / 'growth_phase' (existing); 'metric_type' / 'value_kind' / 'compartment' (slice 2 — DerivedMetric discovery). |

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

### Example 5: Discover available DerivedMetric tags

```example-call
list_filter_values(filter_type="metric_type")
```

```example-response
{"filter_type": "metric_type", "total_entries": 26, "returned": 26, "truncated": false,
 "results": [
   {"value": "cell_abundance_biovolume_normalized", "count": 2},
   {"value": "log2_vesicle_cell_enrichment", "count": 2},
   {"value": "mascot_identification_probability", "count": 2}
 ]}
```

### Example 6: Enumerate DerivedMetric value kinds

```example-call
list_filter_values(filter_type="value_kind")
```

```example-response
{"filter_type": "value_kind", "total_entries": 3, "returned": 3, "truncated": false,
 "results": [
   {"value": "boolean", "count": 16},
   {"value": "numeric", "count": 15},
   {"value": "categorical", "count": 3}
 ]}
```

### Example 7: List wet-lab compartments (for compartment filter)

```example-call
list_filter_values(filter_type="compartment")
```

```example-response
{"filter_type": "compartment", "total_entries": 3, "returned": 3, "truncated": false,
 "results": [
   {"value": "whole_cell", "count": 160},
   {"value": "exoproteome", "count": 7},
   {"value": "vesicle", "count": 5}
 ]}
```

## Chaining patterns

```
list_filter_values → genes_by_function(category=...)
list_filter_values('brite_tree') → ontology_landscape(tree=...) → pathway_enrichment(tree=...)
list_filter_values(filter_type='metric_type') → list_derived_metrics(metric_types=[...]) → genes_by_{kind}_metric
list_filter_values(filter_type='compartment') → list_experiments(compartment=...) / list_organisms(compartment=...) / list_publications(compartment=...)
```

## Common mistakes

- Use filter_type='metric_type' to discover DerivedMetric tags before passing them to genes_by_{kind}_metric or list_derived_metrics. filter_type='value_kind' enumerates {numeric, boolean, categorical}. filter_type='compartment' enumerates wet-lab fractions (whole_cell, vesicle, exoproteome, ...).

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
