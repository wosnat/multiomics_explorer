# response_matrix

## What it does

Builds a pivot DataFrame of gene response directions across treatment
groups (or custom experiment groupings). Each cell is one of: "up",
"down", "mixed", "not_responded", "not_known".

Wraps `gene_response_profile` and reshapes the result into a matrix
suitable for heatmaps, set comparisons, or tabular export.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| genes | list[str] | required | Locus tags to query |
| organism | str \| None | None | Organism filter (fuzzy match) |
| experiment_ids | list[str] \| None | None | Experiment filter (ignored when group_map set) |
| group_map | dict[str, str] \| None | None | experiment_id → group label for custom grouping |
| conn | GraphConnection \| None | None | Reuse existing Neo4j connection |

## Response format

Returns a `pandas.DataFrame`:

- **Index:** `locus_tag` (one row per gene)
- **Group columns:** One per treatment type (default) or custom group label (with group_map). Values: `"up"`, `"down"`, `"mixed"`, `"not_responded"`, `"not_known"`
- **Metadata columns:** `gene_name`, `product`, `gene_category`

Empty DataFrame (with `index.name="locus_tag"`) when no results found.

### Direction classification

| Value | Meaning |
|---|---|
| `"up"` | Only upregulated experiments in this group |
| `"down"` | Only downregulated experiments |
| `"mixed"` | Both up and down experiments |
| `"not_responded"` | Expression edges exist but none significant, OR gene inferred as tested via full-coverage scope (`groups_tested_not_responded`) |
| `"not_known"` | No expression data for this gene in this group |

## Few-shot examples

### Example 1: Basic treatment-type matrix

```python
from multiomics_explorer.analysis import response_matrix

df = response_matrix(
    genes=["PMM0370", "PMM0920", "PMM0965"],
    organism="MED4",
)
# DataFrame with index=locus_tag, columns like
# "nitrogen_stress", "light_stress", ..., "gene_name", "product", "gene_category"
print(df[["nitrogen_stress", "light_stress"]])
```

### Example 2: Custom grouping with group_map

```python
from multiomics_explorer.analysis import response_matrix

# Map specific experiments to custom labels
group_map = {
    "GSE37441_MED4_Nlimit_1": "early_N",
    "GSE37441_MED4_Nlimit_2": "early_N",
    "GSE59000_MED4_Nrecovery": "late_N",
}
df = response_matrix(
    genes=["PMM0370", "PMM0920"],
    group_map=group_map,
)
# Columns: "early_N", "late_N", "gene_name", "product", "gene_category"
```

### Example 3: Chaining from gene search

```python
from multiomics_explorer import genes_by_function
from multiomics_explorer.analysis import response_matrix

# Find nitrogen-related genes, then build response matrix
hits = genes_by_function(search_text="nitrogen", organism="MED4")
locus_tags = [r["locus_tag"] for r in hits["results"][:20]]
df = response_matrix(genes=locus_tags, organism="MED4")
```

## Chaining patterns

```
genes_by_function → response_matrix (search → pivot)
gene_overview → response_matrix (check expression_edge_count > 0 first)
response_matrix → gene_set_compare (use matrix genes as input sets)
list_experiments → group_map → response_matrix (custom grouping)
```

## Common mistakes

```mistake
Passing experiment_ids when group_map is set
```

```correction
group_map overrides experiment_ids. The function uses group_map.keys() as
the experiment list. Pass experiments only via group_map when custom
grouping is needed.
```

```mistake
Expecting numeric values (log2FC, p-values) in cells
```

```correction
response_matrix returns categorical direction strings, not numeric values.
Use gene_response_profile directly for rank/log2FC statistics, or
differential_expression_by_gene for per-timepoint numeric data.
```

```mistake
Using response_matrix for a single gene
```

```correction
response_matrix is designed for gene sets. For a single gene, call
gene_response_profile directly — it returns richer per-group statistics.
```

```mistake
Assuming "not_responded" always means expression edges exist
```

```correction
"not_responded" can also mean the gene was inferred as tested via
groups_tested_not_responded (experiments with significant_only or
significant_any_timepoint scope). Use gene_response_profile directly
to distinguish between edge-based and inference-based non-response.
```
