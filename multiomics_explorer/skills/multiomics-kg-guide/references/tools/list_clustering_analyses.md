# list_clustering_analyses

## What it does

Browse, search, and filter clustering analyses.

Each analysis groups related gene clusters from one study/organism.
Returns analysis IDs for use with genes_in_cluster(analysis_id=...).
Inline clusters included — use genes_in_cluster to drill into members.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Lucene full-text query over analysis name, cluster names, functional/behavioral descriptions, experimental_context. Results ranked by score. |
| organism | string \| None | None | Filter by organism (case-insensitive partial match). |
| cluster_type | string \| None | None | Filter: 'diel_cycling', 'diel_expression_pattern', 'expression_classification', 'expression_level', 'expression_pattern', 'periodicity_classification', 'response_pattern'. |
| treatment_type | list[string] \| None | None | Filter by treatment type(s). E.g. ['nitrogen_stress']. |
| background_factors | list[string] \| None | None | Filter by background factors. E.g. ['axenic', 'diel_cycle']. |
| omics_type | string \| None | None | Filter: 'EXOPROTEOMICS', 'MICROARRAY', 'PROTEOMICS', 'RNASEQ'. |
| publication_doi | list[string] \| None | None | Filter by publication DOI(s). |
| experiment_ids | list[string] \| None | None | Filter by experiment IDs. |
| analysis_ids | list[string] \| None | None | Filter by analysis IDs. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include treatment, light_condition, experimental_context on analyses; functional_description, behavioral_description, peak_time_hours, period_hours on inline clusters. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_organism, by_cluster_type, by_treatment_type, by_background_factors, by_omics_type, score_max, score_median, returned, offset, truncated, results
```

- **total_entries** (int): Total analyses in KG (before filters)
- **total_matching** (int): Analyses matching current filters
- **by_organism** (list[GeneClusterOrganismBreakdown]): Analyses per organism
- **by_cluster_type** (list[GeneClusterTypeBreakdown]): Analyses per cluster type
- **by_treatment_type** (list[GeneClusterTreatmentBreakdown]): Analyses per treatment type
- **by_background_factors** (list[GeneClusterBackgroundFactorBreakdown]): Analyses per background factor
- **by_omics_type** (list[GeneClusterOmicsBreakdown]): Analyses per omics type
- **score_max** (float | None): Highest Lucene score (search only)
- **score_median** (float | None): Median Lucene score (search only)
- **returned** (int): Results in this response
- **offset** (int): Offset into result set
- **truncated** (bool): True if total_matching > offset + returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| analysis_id | string | ClusteringAnalysis node ID (e.g. 'ca:msb4100087:med4:nitrogen') |
| name | string | Analysis name (e.g. 'MED4 nitrogen stress response clustering') |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4') |
| cluster_method | string \| None (optional) | Clustering method (e.g. 'K-means', 'fuzzy c-means') |
| cluster_type | string | Cluster category (e.g. 'stress_response') |
| cluster_count | int | Number of clusters in this analysis |
| total_gene_count | int | Total genes across all clusters |
| treatment_type | list[string] | Treatment types (e.g. ['nitrogen_stress']) |
| background_factors | list[string] (optional) | Background experimental factors (e.g. ['axenic', 'continuous_light']) |
| omics_type | string \| None (optional) | Omics data type (e.g. 'MICROARRAY') |
| experiment_ids | list[string] (optional) | Linked experiment IDs |
| clusters | list[InlineCluster] (optional) | Clusters belonging to this analysis |
| score | float \| None (optional) | Lucene relevance score (only when search_text used) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| treatment | string \| None (optional) | Free-text condition description |
| light_condition | string \| None (optional) | Light regime (e.g. 'diel_cycle') |
| experimental_context | string \| None (optional) | Full experimental context description |

## Few-shot examples

### Example 1: Orient — what clustering analyses exist?

```example-call
list_clustering_analyses(summary=True)
```

### Example 2: Search for nitrogen-related analyses

```example-call
list_clustering_analyses(search_text="starvation")
```

### Example 3: Browse all MED4 analyses with cluster details

```example-call
list_clustering_analyses(organism="MED4", verbose=True)
```

### Example 4: Find analyses then drill into member genes

```
Step 1: list_clustering_analyses(search_text="starvation")
        → extract analysis_id values from results

Step 2: genes_in_cluster(analysis_id="clustering_analysis:msb4100087:med4_kmeans_nstarvation")
        → see all member genes across all clusters in the analysis

Step 3: gene_overview(locus_tags=["PMM0370", "PMM0920", ...])
        → check data availability for cluster members
```

## Chaining patterns

```
list_clustering_analyses → genes_in_cluster(analysis_id=...) → gene_overview
list_clustering_analyses → genes_in_cluster → differential_expression_by_gene
list_clustering_analyses → gene_clusters_by_gene (reverse lookup)
```

## Common mistakes

- Analysis IDs are not in the fulltext index — use search_text for text queries, analysis_ids for direct lookup

- score_max/score_median are null when no search_text is given (browsing mode)

```mistake
genes_in_cluster(cluster_ids=['nitrogen'])  # passing text, not IDs
```

```correction
list_clustering_analyses(search_text='nitrogen')  # search first, then use analysis_id
```

```mistake
len(results)  # actual count
```

```correction
response['total_matching']  # use total, not len — results may be truncated
```

## Package import equivalent

```python
from multiomics_explorer import list_clustering_analyses

result = list_clustering_analyses()
# returns dict with keys: total_entries, total_matching, by_organism, by_cluster_type, by_treatment_type, by_background_factors, by_omics_type, score_max, score_median, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
