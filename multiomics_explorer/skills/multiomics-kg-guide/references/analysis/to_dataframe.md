# DataFrame Conversion Utilities

Three functions for converting API results to CSV-safe DataFrames.
Imported from `multiomics_explorer.analysis`.

## `to_dataframe(result)` — universal converter

### What it does

Converts any API result dict into a flat, CSV-safe DataFrame.
Automatically handles list columns (joins with ` | `), dict columns
(inlines as prefixed columns), and nested structures (drops with
warning suggesting the dedicated function).

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| result | dict | required | Return value from any API function |

### Response format

Single `pd.DataFrame`. One row per entry in `result["results"]`.
All columns are scalar-valued (safe for `.to_csv()`).

### Few-shot examples

**Simple — flat results:**
```python
from multiomics_explorer import genes_by_function
from multiomics_explorer.analysis import to_dataframe

result = genes_by_function("nitrogen")
df = to_dataframe(result)
df.to_csv("nitrogen_genes.csv", index=False)
```

**With nested fields — warning emitted:**
```python
from multiomics_explorer import gene_response_profile
from multiomics_explorer.analysis import to_dataframe

result = gene_response_profile(locus_tags=["PMM0370", "PMM0920"])
df = to_dataframe(result)
# WARNING: Dropped nested column 'response_summary'.
# Use profile_summary_to_dataframe() to extract it as a separate DataFrame.
```

**list_experiments — genes_by_status auto-inlined:**
```python
from multiomics_explorer import list_experiments
from multiomics_explorer.analysis import to_dataframe

result = list_experiments()
df = to_dataframe(result)
# genes_by_status dict becomes:
#   genes_by_status_significant_up, genes_by_status_significant_down,
#   genes_by_status_not_significant
# timepoints list is dropped with warning
```

### Common mistakes

| Mistake | Fix |
|---------|-----|
| Ignoring the warning about dropped columns | Read the warning — it names the dedicated function |
| Using `pd.DataFrame(result["results"])` directly | Use `to_dataframe(result)` instead — it handles nested fields |
| Expecting `to_dataframe` to return the gene x group detail | Use `profile_summary_to_dataframe()` for that |

---

## `profile_summary_to_dataframe(result)` — gene x group detail

### What it does

Extracts the `response_summary` dict from each gene in a
`gene_response_profile` result. Returns one row per gene x group.

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| result | dict | required | Return value from `gene_response_profile()` |

### Response format

`pd.DataFrame` with columns: `locus_tag`, `gene_name`, `group`,
`experiments_total`, `experiments_tested`, `experiments_up`,
`experiments_down`, `timepoints_total`, `timepoints_tested`,
`timepoints_up`, `timepoints_down`, `up_best_rank`,
`up_median_rank`, `up_max_log2fc`, `down_best_rank`,
`down_median_rank`, `down_max_log2fc`.

Directional fields are NaN when no experiments in that direction.

### Few-shot examples

```python
from multiomics_explorer import gene_response_profile
from multiomics_explorer.analysis import to_dataframe, profile_summary_to_dataframe

result = gene_response_profile(locus_tags=["PMM0370", "PMM0920"])

# Gene-level flat table
genes_df = to_dataframe(result)

# Gene x group detail table
summary_df = profile_summary_to_dataframe(result)
summary_df.to_csv("response_detail.csv", index=False)
```

### Common mistakes

| Mistake | Fix |
|---------|-----|
| Passing a `list_experiments` result | This function is for `gene_response_profile` only |
| Expecting the gene-level flat table | Use `to_dataframe()` for that |

---

## `experiments_to_dataframe(result)` — experiment x timepoint

### What it does

Expands time-course experiments into one row per timepoint.
Non-time-course experiments get a single row with NaN timepoint
fields. `genes_by_status` dicts are inlined at both levels.

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| result | dict | required | Return value from `list_experiments()` |

### Response format

`pd.DataFrame` with all scalar experiment fields plus:
`timepoint`, `timepoint_order`, `timepoint_hours`,
`tp_gene_count`, `tp_significant_up`, `tp_significant_down`,
`tp_not_significant`.

Experiment-level `genes_by_status` is inlined as
`genes_by_status_significant_up`, etc.

### Few-shot examples

```python
from multiomics_explorer import list_experiments
from multiomics_explorer.analysis import experiments_to_dataframe

result = list_experiments(organism="MED4")
tp_df = experiments_to_dataframe(result)
tp_df.to_csv("med4_timepoints.csv", index=False)
```

### Common mistakes

| Mistake | Fix |
|---------|-----|
| Passing a `gene_response_profile` result | This function is for `list_experiments` only |
| Using `to_dataframe()` when you want timepoint detail | `to_dataframe()` drops timepoints — use this function |

---

## `analyses_to_dataframe(result)` — analysis × cluster

### What it does

Expands each clustering analysis into one row per cluster. Analysis-level
scalar fields repeat for every cluster row. The `clusters` list column is
unwound — never appears raw in the output.

Compact cluster columns (always present): `cluster_id`, `cluster_name`,
`cluster_member_count`.

Verbose cluster columns (present only when the result was fetched with
`verbose=True`): `cluster_functional_description`,
`cluster_behavioral_description`, `cluster_peak_time_hours`,
`cluster_period_hours`.

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| result | dict | required | Return value from `list_clustering_analyses()` |

### Response format

`pd.DataFrame` with all scalar analysis fields plus `cluster_id`,
`cluster_name`, `cluster_member_count`. List columns (`treatment_type`,
`background_factors`, `experiment_ids`) are joined with ` | `.

### Few-shot examples

**Compact — iterate over analyses and their clusters:**
```python
from multiomics_explorer import list_clustering_analyses
from multiomics_explorer.analysis import analyses_to_dataframe

result = list_clustering_analyses(organism="MED4")
df = analyses_to_dataframe(result)
df.to_csv("med4_clusters.csv", index=False)
```

**Verbose — include cluster descriptions:**
```python
from multiomics_explorer import list_clustering_analyses
from multiomics_explorer.analysis import analyses_to_dataframe

result = list_clustering_analyses(organism="MED4", verbose=True)
df = analyses_to_dataframe(result)
# Extra columns: cluster_functional_description, cluster_behavioral_description,
#                cluster_peak_time_hours, cluster_period_hours
```

### Common mistakes

| Mistake | Fix |
|---------|-----|
| Passing a `list_experiments` result | This function is for `list_clustering_analyses` only |
| Using `to_dataframe()` when you want cluster detail | `to_dataframe()` drops the clusters list — use this function |
