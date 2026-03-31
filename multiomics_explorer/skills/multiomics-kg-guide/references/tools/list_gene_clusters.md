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
total_entries, total_matching, by_organism, by_cluster_type, by_treatment_type, by_omics_type, by_publication, score_max, score_median, returned, offset, truncated, results
```

- **total_entries** (int)
- **total_matching** (int)
- **by_organism** (list[GeneClusterOrganismBreakdown])
- **by_cluster_type** (list[GeneClusterTypeBreakdown])
- **by_treatment_type** (list[GeneClusterTreatmentBreakdown])
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

### Example 1: Search for photosynthesis-related clusters

```example-call
list_gene_clusters(search_text="photosynthesis")
```

### Example 2: Browse all MED4 clusters

```example-call
list_gene_clusters(organism="MED4", limit=20)
```

### Example 3: Filter by treatment type

```example-call
list_gene_clusters(treatment_type=["nitrogen_stress"], verbose=True)
```

### Example 4: Find clusters then get member genes

```
Step 1: list_gene_clusters(search_text="N transport")
        → extract cluster_id values from results
Step 2: genes_in_cluster(cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
        → see member genes
```

## Chaining patterns

```
list_gene_clusters → genes_in_cluster → differential_expression_by_gene
list_gene_clusters → gene_clusters_by_gene (reverse lookup)
```

## Good to know

- Cluster IDs are not in the fulltext index — use search_text for text queries, cluster_ids with genes_in_cluster.

## Package import equivalent

```python
from multiomics_explorer import list_gene_clusters

result = list_gene_clusters()
# returns dict with keys: total_entries, total_matching, by_organism, by_cluster_type, by_treatment_type, by_omics_type, by_publication, score_max, score_median, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
