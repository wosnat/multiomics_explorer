# list_clustering_analyses

## What it does

Published clustering analyses with their GeneCluster children inlined; Lucene over analysis and cluster names, descriptions and context.

Use to discover an analysis_id or cluster_ids; for a cluster's members use `genes_in_cluster`, for one gene's memberships `gene_clusters_by_gene`.
Filters: search_text, organism, cluster_type, analysis_ids, plus the omics / publication / experiment / condition filters.
Returns: by_organism, by_cluster_type, by_treatment_type, by_omics_type, score stats; one row = one analysis with its clusters.
docs://tools/list_clustering_analyses; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Lucene full-text query over analysis name, cluster names, functional/behavioral descriptions, experimental_context. Results ranked by score. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| cluster_type | string \| None | None | Filter by cluster type. Live vocabulary: list_filter_values(filter_type='cluster_type'). Offline examples: 'condition_comparison', 'decay_pattern', 'diel', 'expression_bin', 'genomic_island', 'time_course'. |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| omics_type | list[string] \| None | None | Keep experiments whose omics_type is in this list. Values: list_filter_values('omics_type'). |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| experiment_ids | list[string] \| None | None | Filter by experiment IDs. |
| analysis_ids | list[string] \| None | None | Filter by analysis IDs. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Orient — what clustering analyses exist?

```python
list_clustering_analyses(summary=True)
```

## Response sketch

```expected-keys
total_entries, total_matching, by_organism, by_cluster_type, by_treatment_type, by_background_factors, by_omics_type, by_growth_phase, score_max, score_median, returned, offset, truncated, warnings, results
```

Result row: `analysis_id, name, organism_name, cluster_method, cluster_type, cluster_count, total_gene_count, treatment_type, growth_phases, background_factors, omics_type, experiment_ids, …`

## Common mistakes

- Analysis IDs are not in the fulltext index — use search_text for text queries, analysis_ids for direct lookup

- score_max/score_median are null when no search_text is given (browsing mode)

```mistake
genes_in_cluster(cluster_ids=['nitrogen'])  # passing text, not IDs
```

```correction
list_clustering_analyses(search_text='nitrogen')  # search first, then use analysis_id
```

## Chaining patterns

- list_clustering_analyses → genes_in_cluster(analysis_id=...) → gene_overview
- list_clustering_analyses → genes_in_cluster → differential_expression_by_gene
- list_clustering_analyses → gene_clusters_by_gene (reverse lookup)

Full reference (all examples, full response format, verbose fields): `docs://tools/list_clustering_analyses/full`
