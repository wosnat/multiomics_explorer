# gene_clusters_by_gene

## What it does

Find which gene clusters contain the given genes.

Gene-centric lookup: 'what clusters are these genes in?'
Single organism enforced. One row per gene × cluster.

Use list_gene_clusters for discovery by text search.
Use genes_in_cluster to drill into a cluster's full membership.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags (e.g. ['PMM0370', 'PMM0920']). |
| organism | string \| None | None | Organism name (case-insensitive partial match); inferred from genes if omitted. Single organism enforced. |
| cluster_type | string \| None | None | Filter: 'diel_periodicity', 'stress_response', or 'expression_level'. |
| treatment_type | list[string] \| None | None | Filter by treatment type(s). |
| publication_doi | list[string] \| None | None | Filter by publication DOI(s). |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include functional_description, behavioral_description, treatment_type, treatment, source_paper, p_value. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, total_clusters, genes_with_clusters, genes_without_clusters, not_found, not_matched, by_cluster_type, by_treatment_type, by_publication, returned, offset, truncated, results
```

- **total_matching** (int): Gene × cluster rows matching filters
- **total_clusters** (int): Distinct clusters matched
- **genes_with_clusters** (int): Input genes with at least one cluster membership
- **genes_without_clusters** (int): Input genes with zero memberships after filters
- **not_found** (list[string]): Locus tags not found in KG
- **not_matched** (list[string]): Locus tags in KG but no cluster memberships after filters
- **by_cluster_type** (list[GeneClusterTypeBreakdown]): Rows per cluster type
- **by_treatment_type** (list[GeneClusterTreatmentBreakdown]): Rows per treatment type
- **by_publication** (list[GeneClusterPublicationBreakdown]): Rows per publication
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
| cluster_type | string | Cluster category (e.g. 'stress_response') |
| membership_score | float \| None (optional) | Fuzzy membership score (null for K-means) |
| member_count | int | Total genes in this cluster (e.g. 5) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| functional_description | string \| None (optional) | What the cluster genes ARE (cluster-level) |
| behavioral_description | string \| None (optional) | What the cluster genes DO together (cluster-level) |
| treatment_type | list[string] \| None (optional) | Treatment types for this cluster |
| treatment | string \| None (optional) | Free-text condition description |
| source_paper | string \| None (optional) | Paper reference |
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
gene_clusters_by_gene(locus_tags=["PMM0370"], cluster_type="stress_response", verbose=True)
```

## Chaining patterns

```
resolve_gene → gene_clusters_by_gene → genes_in_cluster
gene_clusters_by_gene → genes_in_cluster (see all cluster members)
```

## Good to know

- Single organism enforced — don't mix PMM (MED4) and PMT (MIT9313) locus tags in one call.

## Package import equivalent

```python
from multiomics_explorer import gene_clusters_by_gene

result = gene_clusters_by_gene(locus_tags=...)
# returns dict with keys: total_matching, total_clusters, genes_with_clusters, genes_without_clusters, not_found, not_matched, by_cluster_type, by_treatment_type, by_publication, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
