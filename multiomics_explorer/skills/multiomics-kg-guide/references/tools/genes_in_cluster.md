# genes_in_cluster

## What it does

Drill into gene cluster members — one row per (gene × cluster).
Provide `cluster_ids` OR `analysis_id` (mutually exclusive);
passing an `analysis_id` returns every cluster's members in one
call.

Routing: analysis discovery via `list_clustering_analyses`; gene →
cluster direction via `gene_clusters_by_gene`.

Single organism is enforced even though `organism` is optional.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| cluster_ids | list[string] \| None | None | GeneCluster node IDs (from list_clustering_analyses or gene_clusters_by_gene). Provide this OR analysis_id. |
| analysis_id | string \| None | None | ClusteringAnalysis node ID — returns all genes in all clusters of this analysis. Provide this OR cluster_ids. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields in docs://tools/{name}. |
| limit | int \| None | 25 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, analysis_name, by_organism, by_cluster, top_categories, genes_per_cluster_max, genes_per_cluster_median, not_found_clusters, not_matched_clusters, not_matched_organism, not_found_analysis, warnings, returned, offset, truncated, results
```

- **total_matching** (int): Gene × cluster rows
- **analysis_name** (string | None): Analysis name (when queried by analysis_id)
- **by_organism** (list[GeneClusterOrganismBreakdown]): Members per organism
- **by_cluster** (list[GenesInClusterClusterBreakdown]): Members per cluster
- **top_categories** (list[GenesInClusterCategoryBreakdown]): Top 5 gene categories by count
- **genes_per_cluster_max** (int): Largest cluster's gene count
- **genes_per_cluster_median** (float): Median gene count across clusters
- **not_found_clusters** (list[string]): Input cluster_ids not found in KG
- **not_matched_clusters** (list[string]): Clusters found but no members after organism filter
- **not_matched_organism** (string | None): Organism that didn't match any cluster's organism
- **not_found_analysis** (string | None): The analysis_id you passed, when no ClusteringAnalysis node with that id exists in the KG. None otherwise — including when cluster_ids was used, or when analysis_id exists but has zero clusters / member genes (that case is a normal empty result, total_matching=0).
- **warnings** (list[string]): Diagnostic strings. Currently emitted: a not_found_analysis pointer at list_clustering_analyses(organism=...).
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
| gene_function_description | string \| None (optional) | Gene functional description (gene-level) |
| gene_summary | string \| None (optional) | Gene summary text (gene-level) |
| p_value | float \| None (optional) | Assignment p-value (edge-level) |
| cluster_functional_description | string \| None (optional) | What the cluster genes ARE (cluster-level) |
| cluster_expression_dynamics | string \| None (optional) | Expression dynamics label (e.g. 'periodic in L:D only') |
| cluster_temporal_pattern | string \| None (optional) | Detailed temporal pattern description (cluster-level) |

## Few-shot examples

### Example 1: Get members of a specific cluster

```example-call
genes_in_cluster(cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:8"])
```

### Example 2: Get all genes in a clustering analysis

```example-call
genes_in_cluster(analysis_id="clustering_analysis:msb4100087:med4_kmeans_nstarvation")
```

### Example 3: Handle invalid cluster IDs gracefully

```example-call
genes_in_cluster(cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:8", "cluster:fake_id"])
```

### Example 4: From analysis search to member gene expression

```
Step 1: list_clustering_analyses(search_text="nitrogen")
        → extract analysis_id values from results

Step 2: genes_in_cluster(analysis_id="clustering_analysis:msb4100087:med4_kmeans_nstarvation")
        → get all member genes across clusters in the analysis

Step 3: differential_expression_by_gene(locus_tags=["PMM0370", "PMM0920", "PMM0958", "PMM0970", "PMM1462"])
        → check expression patterns for the cluster members
```

## Chaining patterns

```
list_clustering_analyses → genes_in_cluster(analysis_id=...) → gene_overview
list_clustering_analyses → genes_in_cluster → differential_expression_by_gene
gene_clusters_by_gene → genes_in_cluster → differential_expression_by_gene
```

## Common mistakes

- cluster_ids come from list_clustering_analyses or gene_clusters_by_gene results — they are not gene locus tags

- Use analysis_id to get ALL genes across ALL clusters in an analysis; use cluster_ids for specific clusters

- not_found_clusters means the ID doesn't exist in the KG; not_matched_clusters means the cluster exists but has no members matching your organism filter. The `_clusters` suffix is this tool's spelling of the not_found / not_matched pair — See docs://guide/conventions for the shared not_found / not_matched semantics.

- In analysis_id mode, an unknown analysis_id sets `not_found_analysis` to the id you passed (plus a `warnings` entry pointing at `list_clustering_analyses`) instead of the `total_matching=0` empty result you'd otherwise get from a valid-but-empty analysis. Check `not_found_analysis` before assuming a zero-row result means the analysis has no members for your organism filter.

- Results are gene × cluster rows — when querying multiple clusters, a gene in both appears twice. Use by_cluster to see per-cluster counts.

```mistake
genes_in_cluster(cluster_ids=['PMM0370'])  # passing a gene locus tag
```

```correction
gene_clusters_by_gene(locus_tags=['PMM0370'])  # use gene_clusters_by_gene for gene → cluster direction
```

```mistake
genes_in_cluster(cluster_ids='cluster:msb4100087:med4_kmeans_nstarvation:8')
```

```correction
genes_in_cluster(cluster_ids=['cluster:msb4100087:med4_kmeans_nstarvation:8']) — always a list
```

## Package import equivalent

```python
from multiomics_explorer import genes_in_cluster

result = genes_in_cluster()
# returns dict with keys: total_matching, analysis_name, by_organism, by_cluster, top_categories, genes_per_cluster_max, genes_per_cluster_median, not_found_clusters, not_matched_clusters, not_matched_organism, not_found_analysis, warnings, returned, offset, truncated, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
