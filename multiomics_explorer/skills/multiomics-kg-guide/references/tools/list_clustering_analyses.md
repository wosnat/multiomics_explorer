# list_clustering_analyses

## What it does

Browse, search, and filter clustering analyses — each analysis
groups related gene clusters from one study / organism, with the
cluster children inlined per result. Lucene full-text over analysis
name, cluster names, descriptions, experimental_context. See
`docs://guide/conventions` for Lucene scoring.

Routing: `genes_in_cluster(cluster_ids=[id])` for per-cluster
members; `genes_in_cluster(analysis_id=...)` for all clusters in
one analysis; `gene_clusters_by_gene(locus_tags=[...],
analysis_ids=[id])` to scope a per-gene cluster lookup.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Lucene full-text query over analysis name, cluster names, functional/behavioral descriptions, experimental_context. Results ranked by score. |
| organism | string \| None | None | Organism: word-based, case-insensitive match on preferred_name + name_synonyms ('MED4' works; a genus word like 'Alteromonas' matches every strain). |
| cluster_type | string \| None | None | Filter by cluster type. Live vocabulary: list_filter_values(filter_type='cluster_type'). Offline examples: 'condition_comparison', 'decay_pattern', 'diel', 'expression_bin', 'genomic_island', 'time_course'. |
| treatment_type | list[string] \| None | None | Filter by treatment type(s). E.g. ['nitrogen']. Live vocabulary: list_filter_values(filter_type='treatment_type') or list_experiments(summary=True). |
| background_factors | list[string] \| None | None | Filter by background factors. E.g. ['axenic', 'diel']. |
| growth_phases | list[string] \| None | None | Filter by growth phase(s) (case-insensitive). Physiological state of the culture at sampling time. E.g. ['exponential', 'nutrient_limited']. |
| omics_type | string \| None | None | Filter: 'EXOPROTEOMICS', 'METABOLOMICS', 'MICROARRAY', 'PAIRED_RNASEQ_PROTEOME', 'PROTEOMICS', 'RNASEQ', 'VESICLE_DNASEQ', 'VESICLE_PROTEOMICS'. |
| publication_dois | list[string] \| None | None | Filter by publication DOI(s). |
| experiment_ids | list[string] \| None | None | Filter by experiment IDs. |
| analysis_ids | list[string] \| None | None | Filter by analysis IDs. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include treatment, light_condition, experimental_context on analyses; functional_description, expression_dynamics, temporal_pattern on inline clusters. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_organism, by_cluster_type, by_treatment_type, by_background_factors, by_omics_type, by_growth_phase, score_max, score_median, returned, offset, truncated, warnings, results
```

- **total_entries** (int): Total analyses in KG (before filters)
- **total_matching** (int): Analyses matching current filters
- **by_organism** (list[GeneClusterOrganismBreakdown]): Analyses per organism
- **by_cluster_type** (list[GeneClusterTypeBreakdown]): Analyses per cluster type
- **by_treatment_type** (list[GeneClusterTreatmentBreakdown]): Analyses per treatment type
- **by_background_factors** (list[GeneClusterBackgroundFactorBreakdown]): Analyses per background factor
- **by_omics_type** (list[GeneClusterOmicsBreakdown]): Analyses per omics type
- **by_growth_phase** (list[GrowthPhaseBreakdown]): Analysis counts per growth phase, sorted by count descending
- **score_max** (float | None): Highest Lucene score (search only)
- **score_median** (float | None): Median Lucene score (search only)
- **returned** (int): Results in this response
- **offset** (int): Offset into result set
- **truncated** (bool): True if total_matching > offset + returned
- **warnings** (list[string]): A closed-vocabulary filter value (cluster_type / treatment_type / background_factors / growth_phases / omics_type) not found in the live vocabulary (see list_filter_values), or an organism that matches no OrganismTaxon. Advisory only — never changes which rows are returned. Empty when clean.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| analysis_id | string | ClusteringAnalysis node ID (e.g. 'clustering_analysis:msb4100087:med4_kmeans_nstarvation') |
| name | string | Analysis name (e.g. 'MED4 nitrogen stress response clustering') |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4') |
| cluster_method | string \| None (optional) | Clustering method, free text (e.g. 'K-means (K=9)', 'Fuzzy c-means (K=5)') |
| cluster_type | string | Cluster category (e.g. 'condition_comparison') |
| cluster_count | int | Number of clusters in this analysis |
| total_gene_count | int | Total genes across all clusters |
| treatment_type | list[string] | Treatment types (e.g. ['nitrogen', 'coculture']) |
| growth_phases | list[string] (optional) | Distinct growth phases. Physiological state of the culture at sampling — timepoint-level, not gene-specific. |
| background_factors | list[string] (optional) | Background experimental factors (e.g. ['axenic', 'light']) |
| omics_type | string \| None (optional) | Omics data type (e.g. 'MICROARRAY') |
| experiment_ids | list[string] (optional) | Linked experiment IDs |
| clusters | list[InlineCluster] (optional) | Clusters belonging to this analysis |
| score | float \| None (optional) | Lucene relevance score (only when search_text used) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| treatment | string \| None (optional) | Free-text condition description |
| light_condition | string \| None (optional) | Light regime, free text (e.g. 'continuous light', '14:10 light:dark cycle') |
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

- growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — NOT a gene-specific property

- Valid `cluster_type` values come from the KG vocabulary — enumerate them with list_filter_values(filter_type='cluster_type') (currently six: time_course, diel, condition_comparison, expression_bin, decay_pattern, genomic_island). The list quoted in the parameter description is documentation, not the source.

- `treatment_type` is dense and never empty. A characterization study with no perturbation names what was measured — `rna_decay` (decay_pattern clusters from an mRNA half-life survey), `genomic_analysis` (sequence-predicted genomic-island sets) — so `treatment_type=[...]` filters reach it. `background_factors` is `[]` only on the genomic_island analyses (sequence-only, no experimental context); every expression-derived analysis carries at least one factor.

- treatment_type / background_factors / growth_phase values are LIVE vocabularies read from the KG, not enums: an unknown value (e.g. 'nitrogen_stress' instead of 'nitrogen') returns 0 rows, never an error. Check list_filter_values(filter_type='growth_phase') or list_experiments(summary=True)'s by_treatment_type / by_background_factors rollup before filtering. Current treatment values are short nouns (nitrogen, light, carbon, iron, darkness, phosphorus, salt, viral, coculture, diel, ...); background_factors are light, axenic, coculture, darkness, diel, viral, chemical. On analyses the same short nouns apply (darkness, viral, iron, nitrogen, diel, temperature, light, oxygen, rna_decay, genomic_analysis).

- `organism=` is a word-based, case-insensitive match on preferred_name + name_synonyms — 'MED4' works. 'Meiothermus ruber' names two OrganismTaxon nodes; the clustering analyses attach to the genome strain.

- DataFrame conversion: `to_dataframe(result)` auto-dispatches and returns one row per analysis × cluster (compact: cluster_id / cluster_name / cluster_member_count; verbose=True adds cluster descriptions). See `docs://guide/python_api`.

## Package import equivalent

```python
from multiomics_explorer import list_clustering_analyses

result = list_clustering_analyses()
# returns dict with keys: total_entries, total_matching, by_organism, by_cluster_type, by_treatment_type, by_background_factors, by_omics_type, by_growth_phase, score_max, score_median, returned, offset, truncated, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
