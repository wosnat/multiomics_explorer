# genes_in_cluster

## What it does

Cluster members — one row per gene × cluster. Pass cluster_ids OR analysis_id (mutually exclusive); one organism is enforced even though organism is optional.

Use for a module's full roster; for one gene's memberships use `gene_clusters_by_gene`, to find IDs `list_clustering_analyses`.
Filters: cluster_ids, analysis_id, organism.
Returns: analysis_name, by_cluster, top_categories, genes-per-cluster stats, not_found_clusters, not_matched_clusters, not_found_analysis; one row = (locus_tag, cluster_id).
docs://tools/genes_in_cluster; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| cluster_ids | list[string] \| None | None | GeneCluster node IDs (from list_clustering_analyses or gene_clusters_by_gene). Provide this OR analysis_id. |
| analysis_id | string \| None | None | ClusteringAnalysis node ID — returns all genes in all clusters of this analysis. Provide this OR cluster_ids. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 25 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Example

### Get members of a specific cluster

```python
genes_in_cluster(cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:8"])
```

## Response sketch

```expected-keys
total_matching, analysis_name, by_organism, by_cluster, top_categories, genes_per_cluster_max, genes_per_cluster_median, not_found_clusters, not_matched_clusters, not_matched_organism, not_found_analysis, warnings, returned, offset, truncated, results
```

Result row: `locus_tag, gene_name, product, gene_category, organism_name, cluster_id, cluster_name, membership_score, gene_function_description, gene_summary, p_value, cluster_functional_description, …`

## Common mistakes

- cluster_ids come from list_clustering_analyses or gene_clusters_by_gene results — they are not gene locus tags

- Use analysis_id to get ALL genes across ALL clusters in an analysis; use cluster_ids for specific clusters

- not_found_clusters means the ID doesn't exist in the KG; not_matched_clusters means the cluster exists but has no members matching your organism filter. The `_clusters` suffix is this tool's spelling of the not_found / not_matched pair — See docs://guide/conventions for the shared not_found / not_matched semantics.

## Chaining patterns

- list_clustering_analyses → genes_in_cluster(analysis_id=...) → gene_overview
- list_clustering_analyses → genes_in_cluster → differential_expression_by_gene
- gene_clusters_by_gene → genes_in_cluster → differential_expression_by_gene

Full reference (all examples, full response format, verbose fields): `docs://tools/genes_in_cluster/full`
