# gene_clusters_by_gene

## What it does

Cluster memberships for a gene batch in ONE organism (inferred when omitted) — one row per gene × cluster with its analysis context.

Use for which modules a gene sits in; for a cluster's full roster use `genes_in_cluster`, to discover analyses `list_clustering_analyses`.
Filters: locus_tags, organism, cluster_type, analysis_ids, plus the publication / condition filters.
Returns: genes_with_clusters, genes_without_clusters, by_cluster_type, by_analysis, not_found, not_matched; one row = (locus_tag, cluster_id, analysis_id).
docs://tools/gene_clusters_by_gene; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags (e.g. ['PMM0370', 'PMM0920']). |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| cluster_type | string \| None | None | Filter by cluster type. Live vocabulary: list_filter_values(filter_type='cluster_type'). Offline examples: 'condition_comparison', 'decay_pattern', 'diel', 'expression_bin', 'genomic_island', 'time_course'. |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| analysis_ids | list[string] \| None | None | Filter by clustering analysis IDs. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 25 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Check cluster membership for N-transport genes

```python
gene_clusters_by_gene(locus_tags=["PMM0370", "PMM0920", "PMM0958"])
```

## Response sketch

```expected-keys
total_matching, total_clusters, genes_with_clusters, genes_without_clusters, not_found, not_matched, by_cluster_type, by_treatment_type, by_background_factors, by_analysis, returned, offset, truncated, warnings, results
```

Result row: `locus_tag, gene_name, cluster_id, cluster_name, cluster_type, membership_score, analysis_id, analysis_name, treatment_type, background_factors, cluster_method, member_count, …`

## Common mistakes

- Single organism enforced — don't mix PMM (MED4) and PMT (MIT9313) locus tags in one call

- not_matched means the gene exists but has no cluster membership (after the cluster_type / treatment_type / analysis filters) — it is NOT the same as not_found (gene doesn't exist in KG). Both are flat locus_tag lists; genes_with_clusters / genes_without_clusters are the counts. See docs://guide/conventions for the shared not_found / not_matched semantics.

- Results are gene × cluster rows — a gene in 2 clusters appears twice. Use genes_with_clusters for the deduplicated count.

## Chaining patterns

- resolve_gene → gene_clusters_by_gene → genes_in_cluster
- genes_by_function → gene_clusters_by_gene → genes_in_cluster
- gene_clusters_by_gene → genes_in_cluster(analysis_id=...) (see all analysis members)
- gene_clusters_by_gene → differential_expression_by_gene (check expression for cluster genes)

Full reference (all examples, full response format, verbose fields): `docs://tools/gene_clusters_by_gene/full`
