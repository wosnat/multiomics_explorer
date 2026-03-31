# genes_in_cluster

## What it does

Get member genes of gene clusters.

Takes cluster IDs from list_gene_clusters or gene_clusters_by_gene
and returns their member genes. One row per gene × cluster.

For cluster discovery by text, use list_gene_clusters first.
For gene → cluster direction, use gene_clusters_by_gene.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| cluster_ids | list[string] | — | GeneCluster node IDs (from list_gene_clusters or gene_clusters_by_gene). |
| organism | string \| None | None | Filter by organism (case-insensitive partial match). Single organism enforced. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include function_description, gene_summary (gene-level), p_value (edge-level), functional_description, behavioral_description (cluster-level). |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, by_organism, by_cluster, top_categories, genes_per_cluster_max, genes_per_cluster_median, not_found_clusters, not_matched_clusters, not_matched_organism, returned, offset, truncated, results
```

- **total_matching** (int): Gene × cluster rows
- **by_organism** (list[GeneClusterOrganismBreakdown]): Members per organism
- **by_cluster** (list[GenesInClusterClusterBreakdown]): Members per cluster
- **top_categories** (list[GenesInClusterCategoryBreakdown]): Top 5 gene categories by count
- **genes_per_cluster_max** (int): Largest cluster's gene count
- **genes_per_cluster_median** (float): Median gene count across clusters
- **not_found_clusters** (list[string]): Cluster IDs not found in KG
- **not_matched_clusters** (list[string]): Clusters found but no members after organism filter
- **not_matched_organism** (string | None): Organism that didn't match any cluster's organism
- **returned** (int): Results in this response
- **offset** (int): Offset into result set
- **truncated** (bool): True if total_matching > offset + returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0370') |
| gene_name | string \| None (optional) | Gene name (e.g. 'cynA') |
| product | string \| None (optional) | Gene product (e.g. 'cyanate ABC transporter') |
| gene_category | string \| None (optional) | Functional category (e.g. 'N-metabolism') |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4') |
| cluster_id | string | Cluster node ID |
| cluster_name | string | Cluster name |
| membership_score | float \| None (optional) | Fuzzy membership score (null for K-means) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| function_description | string \| None (optional) | Gene functional description (gene-level) |
| gene_summary | string \| None (optional) | Gene summary text (gene-level) |
| p_value | float \| None (optional) | Assignment p-value (edge-level) |
| functional_description | string \| None (optional) | What the cluster genes ARE (cluster-level) |
| behavioral_description | string \| None (optional) | What the cluster genes DO together (cluster-level) |

## Few-shot examples

### Example 1: Get members of an N-transport cluster

```example-call
genes_in_cluster(cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
```

### Example 2: Drill into multiple clusters at once

```example-call
genes_in_cluster(cluster_ids=["cluster:msb4100087:med4:up_n_transport", "cluster:msb4100087:med4:down_translation"], limit=20)
```

### Example 3: Verbose view with cluster context

```example-call
genes_in_cluster(cluster_ids=["cluster:msb4100087:med4:up_n_transport"], verbose=True)
```

## Chaining patterns

```
list_gene_clusters → genes_in_cluster → gene_overview
gene_clusters_by_gene → genes_in_cluster → differential_expression_by_gene
```

## Good to know

- Cluster IDs come from list_gene_clusters or gene_clusters_by_gene results — they are not gene locus tags.

## Package import equivalent

```python
from multiomics_explorer import genes_in_cluster

result = genes_in_cluster(cluster_ids=...)
# returns dict with keys: total_matching, by_organism, by_cluster, top_categories, genes_per_cluster_max, genes_per_cluster_median, not_found_clusters, not_matched_clusters, not_matched_organism, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
