# cluster_enrichment

## What it does

Cluster-membership over-representation analysis (Fisher + BH).

Runs ORA on every cluster in a clustering analysis. Use
list_clustering_analyses to find analysis IDs. Background
defaults to the union of all clustered genes.
See docs://analysis/enrichment for methodology;
docs://examples/pathway_enrichment.py for runnable code (the custom
term2gene path covers cluster-membership enrichment).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| analysis_id | string | — | Clustering analysis ID. Get from list_clustering_analyses. |
| organism | string | — | Organism (case-insensitive fuzzy match). Single-organism enforced. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy') | — | Ontology for pathway definitions. Run ontology_landscape first. |
| tree | string \| None | None | BRITE tree name filter. Only valid when ontology='brite'. |
| level | int \| None | None | Hierarchy level (0 = root). At least one of level or term_ids required. |
| term_ids | list[string] \| None | None | Specific term IDs to test. |
| background | string | cluster_union | 'cluster_union' (default), 'organism', or explicit locus_tag list. |
| min_gene_set_size | int | 5 | Per-cluster M filter: drop pathways with fewer members. |
| max_gene_set_size | int \| None | 500 | Per-cluster M filter upper bound. None disables. |
| min_cluster_size | int | 3 | Skip clusters with fewer members than this. |
| max_cluster_size | int \| None | None | Skip clusters with more members. None disables. |
| pvalue_cutoff | float | 0.05 | Significance threshold for p_adjust. |
| summary | bool | False | If true, omit results (envelope only). |
| limit | int | 5 | Max rows returned. |
| offset | int | 0 | Skip N rows before limit. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
analysis_id, analysis_name, organism_name, cluster_method, cluster_type, omics_type, treatment_type, background_factors, growth_phases, experiment_ids, ontology, level, tree, total_matching, returned, truncated, offset, n_significant, by_cluster, by_term, clusters_tested, not_found, not_matched, clusters_skipped, term_validation, enrichment_params, results
```

- **analysis_id** (string | None): Clustering analysis ID
- **analysis_name** (string | None): Clustering analysis name
- **organism_name** (string): Single organism
- **cluster_method** (string | None): Clustering method
- **cluster_type** (string | None): Cluster type
- **omics_type** (string | None): Omics type
- **treatment_type** (list[string]): Treatment types
- **background_factors** (list[string]): Background factors
- **growth_phases** (list[string]): Growth phases
- **experiment_ids** (list[string]): Linked experiment IDs
- **ontology** (string): Ontology used
- **level** (int | None): Hierarchy level
- **tree** (string | None): BRITE tree (if applicable)
- **total_matching** (int): Total Fisher tests run
- **returned** (int): Rows in this response
- **truncated** (bool): True when total_matching exceeds offset+returned
- **offset** (int): Pagination offset
- **n_significant** (int): Rows with p_adjust below cutoff
- **by_cluster** (list[ClusterEnrichmentByCluster]): Per-cluster significance counts
- **by_term** (list[ClusterEnrichmentByTerm]): Top terms by number of clusters
- **clusters_tested** (int): Clusters passing size filter
- **not_found** (list[string]): Analysis IDs absent from KG
- **not_matched** (list[string]): Analysis IDs wrong organism
- **clusters_skipped** (list[ClusterEnrichmentClusterSkipped]): Clusters filtered out or producing no rows
- **term_validation** (PathwayEnrichmentTermValidation): Namespaced passthrough of term_id validation from genes_by_ontology
- **enrichment_params** (object | None): ORA parameters used for this call. See docs://analysis/enrichment.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| cluster | string | Cluster name from the clustering analysis |
| cluster_id | string | Cluster ID from KG |
| term_id | string | Ontology term ID |
| term_name | string | Ontology term display name |
| level | int \| None (optional) | Hierarchy depth (0 = root) |
| tree | string \| None (optional) | BRITE tree name (sparse: BRITE only) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: BRITE only) |
| gene_ratio | string | 'k/n' string — cluster genes in pathway over total cluster genes (clusterProfiler: GeneRatio) |
| gene_ratio_numeric | float | k/n as float |
| bg_ratio | string | 'M/N' string — pathway members over background size (clusterProfiler: BgRatio) |
| bg_ratio_numeric | float | M/N as float |
| rich_factor | float | k/M — fraction of pathway's background members in cluster (clusterProfiler: RichFactor) |
| fold_enrichment | float | (k/n) / (M/N) — observed over null (clusterProfiler: FoldEnrichment) |
| pvalue | float | Fisher-exact p-value (one-sided enrichment) |
| p_adjust | float | Benjamini-Hochberg FDR within cluster (clusterProfiler: p.adjust) |
| count | int | k — cluster genes in pathway (clusterProfiler: Count) |
| bg_count | int | M — pathway members in cluster's background |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| cluster_functional_description | string \| None (optional) | Verbose: functional description of cluster |
| cluster_expression_dynamics | string \| None (optional) | Verbose: expression dynamics of cluster |
| cluster_temporal_pattern | string \| None (optional) | Verbose: temporal pattern of cluster |
| cluster_member_count | int \| None (optional) | Verbose: total genes in this cluster |

## Few-shot examples

### Example 1: Single analysis, CyanoRak level 1

```example-call
cluster_enrichment(analysis_id="clustering_analysis:journal.pone.0005135:med4_diel_clusters", organism="MED4", ontology="cyanorak_role", level=1)
```

### Example 2: Summary-only (envelope, no rows)

```example-call
cluster_enrichment(analysis_id="clustering_analysis:journal.pone.0005135:med4_diel_clusters", organism="MED4", ontology="cyanorak_role", level=1, summary=True)
```

### Example 3: BRITE tree-scoped

```example-call
cluster_enrichment(analysis_id="clustering_analysis:journal.pone.0005135:med4_diel_clusters", organism="MED4", ontology="brite", tree="transporters", level=1)
```

### Example 4: Organism background instead of cluster union

```example-call
cluster_enrichment(analysis_id="clustering_analysis:journal.pone.0005135:med4_diel_clusters", organism="MED4", ontology="cyanorak_role", level=1, background="organism")
```

### Example 5: From landscape to cluster enrichment

```
Step 1: list_clustering_analyses(organism="MED4")
        → pick an analysis_id

Step 2: ontology_landscape(organism="MED4")
        → pick (ontology, level) by relevance_rank

Step 3: cluster_enrichment(analysis_id=<picked>, organism="MED4", ontology=<picked>, level=<picked>)
        → Fisher ORA results per cluster
```

## Chaining patterns

```
list_clustering_analyses → cluster_enrichment
ontology_landscape → cluster_enrichment
cluster_enrichment → gene_overview
cluster_enrichment → genes_in_cluster
```

## Common mistakes

- Default background is `cluster_union` (union of all clustered genes, including size-filtered). Use `'organism'` only when clustering covers the full genome.

- BH correction is per-cluster, NOT across clusters.

- Single-organism enforced.

- No signed_score — clusters aren't directional. For direction-aware enrichment, use pathway_enrichment with DE experiments.

- At least one of `level` or `term_ids` must be provided.

- `min/max_gene_set_size` is the pathway M filter (per-cluster, clusterProfiler semantics). `min/max_cluster_size` is the cluster membership filter.

- For BRITE, scope to a specific tree with `tree=`. Use `list_filter_values('brite_tree')` to discover trees.

```mistake
cluster_enrichment(..., background='table_scope')  # not valid
```

```correction
cluster_enrichment(..., background='cluster_union')  # or 'organism', or a locus_tag list
```

## Package import equivalent

```python
from multiomics_explorer import cluster_enrichment

result = cluster_enrichment(analysis_id=..., organism=..., ontology=...)
# returns EnrichmentResult; access result.results
# and accessors. Call result.to_envelope() for the
# MCP-equivalent dict shape.
# See docs://examples/pathway_enrichment.py for runnable code.
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
