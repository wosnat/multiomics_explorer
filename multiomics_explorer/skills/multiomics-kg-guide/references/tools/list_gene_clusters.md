# list_gene_clusters

## What it does

Browse, search, and filter gene clusters.

Search across cluster names, functional descriptions, behavioral
descriptions, and experimental context. Filter by organism, cluster
type, treatment type, omics type, or publication.

Returns cluster IDs for use with genes_in_cluster.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Lucene full-text query over name, functional_description, behavioral_description, experimental_context. Results ranked by score. |
| organism | string \| None | None | Filter by organism (case-insensitive partial match). |
| cluster_type | string \| None | None | Filter: 'diel_periodicity', 'stress_response', or 'expression_level'. |
| treatment_type | list[string] \| None | None | Filter by treatment type(s). E.g. ['nitrogen_stress']. |
| background_factors | list[string] \| None | None | Filter by background factors. E.g. ['axenic', 'diel_cycle']. |
| omics_type | string \| None | None | Filter: 'MICROARRAY', 'RNASEQ', or 'PROTEOMICS'. |
| publication_doi | list[string] \| None | None | Filter by publication DOI(s). |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include functional_description, behavioral_description, cluster_method, treatment, light_condition, experimental_context, peak_time_hours, period_hours, pub_doi. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_organism, by_cluster_type, by_treatment_type, by_background_factors, by_omics_type, by_publication, score_max, score_median, returned, offset, truncated, results
```

- **total_entries** (int)
- **total_matching** (int)
- **by_organism** (list[GeneClusterOrganismBreakdown])
- **by_cluster_type** (list[GeneClusterTypeBreakdown])
- **by_treatment_type** (list[GeneClusterTreatmentBreakdown])
- **by_background_factors** (list[GeneClusterBackgroundFactorBreakdown])
- **by_omics_type** (list[GeneClusterOmicsBreakdown])
- **by_publication** (list[GeneClusterPublicationBreakdown])
- **score_max** (float | None)
- **score_median** (float | None)
- **returned** (int)
- **offset** (int)
- **truncated** (bool)

### Per-result fields

| Field | Type | Description |
|---|---|---|
| cluster_id | string |  |
| name | string |  |
| organism_name | string |  |
| cluster_type | string |  |
| treatment_type | list[string] |  |
| background_factors | list[string] (optional) | Background experimental factors (e.g. ['axenic', 'continuous_light']) |
| member_count | int |  |
| source_paper | string |  |
| score | float \| None (optional) |  |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| functional_description | string \| None (optional) |  |
| behavioral_description | string \| None (optional) |  |
| cluster_method | string \| None (optional) |  |
| treatment | string \| None (optional) |  |
| light_condition | string \| None (optional) |  |
| experimental_context | string \| None (optional) |  |
| peak_time_hours | float \| None (optional) |  |
| period_hours | float \| None (optional) |  |
| pub_doi | string \| None (optional) |  |

## Few-shot examples

### Example 1: Orient — what clusters exist?

```example-call
list_gene_clusters(summary=True)
```

```example-response
{"total_entries": 16, "total_matching": 16, "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 9}, {"organism_name": "Prochlorococcus MIT9313", "count": 7}], "by_cluster_type": [{"cluster_type": "stress_response", "count": 16}], "by_treatment_type": [{"treatment_type": "nitrogen_stress", "count": 16}], "by_omics_type": [{"omics_type": "MICROARRAY", "count": 16}], "by_publication": [{"publication_doi": "10.1038/msb4100087", "count": 16}], "score_max": null, "score_median": null, "returned": 0, "truncated": true, "offset": 0, "results": []}
```

### Example 2: Search for photosynthesis-related clusters

```example-call
list_gene_clusters(search_text="photosynthesis")
```

```example-response
{"total_entries": 16, "total_matching": 3, "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 2}, {"organism_name": "Prochlorococcus MIT9313", "count": 1}], "by_cluster_type": [{"cluster_type": "stress_response", "count": 3}], "score_max": 1.82, "score_median": 1.58, "returned": 3, "truncated": false, "offset": 0, "results": [{"cluster_id": "cluster:msb4100087:mit9313:down_photosynthesis", "name": "MIT9313 cluster 6 (down, photosynthesis)", "organism_name": "Prochlorococcus MIT9313", "cluster_type": "stress_response", "treatment_type": ["nitrogen_stress"], "member_count": 74, "source_paper": "Tolonen 2006", "score": 1.82}]}
```

### Example 3: Browse all MED4 clusters

```example-call
list_gene_clusters(organism="MED4", limit=20)
```

### Example 4: Find clusters then get member genes

```
Step 1: list_gene_clusters(search_text="N transport")
        → extract cluster_id values from results

Step 2: genes_in_cluster(cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
        → see member genes

Step 3: gene_overview(locus_tags=["PMM0370", "PMM0920", ...])
        → check data availability for cluster members
```

## Chaining patterns

```
list_gene_clusters → genes_in_cluster → gene_overview
list_gene_clusters → genes_in_cluster → differential_expression_by_gene
list_gene_clusters → gene_clusters_by_gene (reverse lookup)
```

## Common mistakes

- Cluster IDs are not in the fulltext index — use search_text for text queries, cluster_ids with genes_in_cluster

- score_max/score_median are null when no search_text is given (browsing mode)

- All clusters currently come from a single publication (Tolonen 2006) — use publication_doi filter if more sources are added

```mistake
genes_in_cluster(cluster_ids=['photosynthesis'])  # passing text, not IDs
```

```correction
list_gene_clusters(search_text='photosynthesis')  # search first, then use cluster_ids
```

```mistake
len(results)  # actual count
```

```correction
response['total_matching']  # use total, not len — results may be truncated
```

## Package import equivalent

```python
from multiomics_explorer import list_gene_clusters

result = list_gene_clusters()
# returns dict with keys: total_entries, total_matching, by_organism, by_cluster_type, by_treatment_type, by_background_factors, by_omics_type, by_publication, score_max, score_median, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
