# gene_clusters_by_gene

## What it does

Find which gene clusters contain the given genes.

Gene-centric lookup: 'what clusters are these genes in?'
Single organism enforced. One row per gene × cluster.

Use list_clustering_analyses for discovery by text search.
Use genes_in_cluster to drill into a cluster's full membership.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags (e.g. ['PMM0370', 'PMM0920']). |
| organism | string \| None | None | Organism name (case-insensitive partial match); inferred from genes if omitted. Single organism enforced. |
| cluster_type | string \| None | None | Filter: 'classification', 'condition_comparison', 'diel', 'time_course'. |
| treatment_type | list[string] \| None | None | Filter by treatment type(s). |
| background_factors | list[string] \| None | None | Filter by background factors. |
| publication_doi | list[string] \| None | None | Filter by publication DOI(s). |
| analysis_ids | list[string] \| None | None | Filter by clustering analysis IDs. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include cluster_method, member_count, cluster_functional_description, cluster_expression_dynamics, cluster_temporal_pattern, treatment, light_condition, experimental_context, p_value. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, total_clusters, genes_with_clusters, genes_without_clusters, not_found, not_matched, by_cluster_type, by_treatment_type, by_background_factors, by_analysis, returned, offset, truncated, results
```

- **total_matching** (int): Gene × cluster rows matching filters
- **total_clusters** (int): Distinct clusters matched
- **genes_with_clusters** (int): Input genes with at least one cluster membership
- **genes_without_clusters** (int): Input genes with zero memberships after filters
- **not_found** (list[string]): Locus tags not found in KG
- **not_matched** (list[string]): Locus tags in KG but no cluster memberships after filters
- **by_cluster_type** (list[GeneClusterTypeBreakdown]): Rows per cluster type
- **by_treatment_type** (list[GeneClusterTreatmentBreakdown]): Rows per treatment type
- **by_background_factors** (list[GeneClusterBackgroundFactorBreakdown]): Rows per background factor
- **by_analysis** (list[GeneClusterAnalysisBreakdown]): Rows per clustering analysis
- **returned** (int): Results in this response
- **offset** (int): Offset into result set
- **truncated** (bool): True if total_matching > offset + returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0370') |
| gene_name | string \| None (optional) | Gene name (e.g. 'cynA') |
| cluster_id | string | Cluster node ID (e.g. 'cluster:msb4100087:med4:up_n_transport') |
| cluster_name | string | Cluster name (e.g. 'MED4 cluster 1 (up, N transport)') |
| cluster_type | string | Cluster category (e.g. 'condition_comparison') |
| membership_score | float \| None (optional) | Fuzzy membership score (null for K-means) |
| analysis_id | string | Clustering analysis ID |
| analysis_name | string | Clustering analysis name |
| treatment_type | list[string] | Treatment types for this cluster |
| background_factors | list[string] (optional) | Background experimental factors |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| cluster_method | string \| None (optional) | Clustering method (e.g. 'K-means') |
| member_count | int \| None (optional) | Total genes in this cluster |
| cluster_functional_description | string \| None (optional) | What the cluster genes ARE (cluster-level) |
| cluster_expression_dynamics | string \| None (optional) | Expression dynamics label (e.g. 'periodic in L:D only') |
| cluster_temporal_pattern | string \| None (optional) | Detailed temporal pattern description (cluster-level) |
| treatment | string \| None (optional) | Free-text condition description |
| light_condition | string \| None (optional) | Light regime |
| experimental_context | string \| None (optional) | Full experimental context description |
| p_value | float \| None (optional) | Assignment p-value (null for most methods) |

## Few-shot examples

### Example 1: Check cluster membership for N-transport genes

```example-call
gene_clusters_by_gene(locus_tags=["PMM0370", "PMM0920", "PMM0958"])
```

### Example 2: Summary only — which genes have clusters?

```example-call
gene_clusters_by_gene(locus_tags=["PMM0370", "PMM0001"], summary=True)
```

### Example 3: Filter to stress response clusters

```example-call
gene_clusters_by_gene(locus_tags=["PMM0370"], cluster_type="condition_comparison", verbose=True)
```

### Example 4: From gene search to cluster context

```
Step 1: genes_by_function(search_text="nitrogen transport", organism="MED4")
        → collect locus_tags from results

Step 2: gene_clusters_by_gene(locus_tags=["PMM0370", "PMM0920", ...])
        → see which clusters these genes belong to, with analysis_id and analysis_name

Step 3: genes_in_cluster(analysis_id="clustering_analysis:msb4100087:med4_kmeans_nstarvation")
        → discover all genes in the same analysis
```

## Chaining patterns

```
resolve_gene → gene_clusters_by_gene → genes_in_cluster
genes_by_function → gene_clusters_by_gene → genes_in_cluster
gene_clusters_by_gene → genes_in_cluster(analysis_id=...) (see all analysis members)
gene_clusters_by_gene → differential_expression_by_gene (check expression for cluster genes)
```

## Common mistakes

- Single organism enforced — don't mix PMM (MED4) and PMT (MIT9313) locus tags in one call

- not_matched means the gene exists but has no cluster membership — it is NOT the same as not_found (gene doesn't exist in KG)

- Results are gene × cluster rows — a gene in 2 clusters appears twice. Use genes_with_clusters for the deduplicated count.

```mistake
gene_clusters_by_gene(locus_tags='PMM0370')
```

```correction
gene_clusters_by_gene(locus_tags=['PMM0370']) — always a list
```

## Package import equivalent

```python
from multiomics_explorer import gene_clusters_by_gene

result = gene_clusters_by_gene(locus_tags=...)
# returns dict with keys: total_matching, total_clusters, genes_with_clusters, genes_without_clusters, not_found, not_matched, by_cluster_type, by_treatment_type, by_background_factors, by_analysis, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
