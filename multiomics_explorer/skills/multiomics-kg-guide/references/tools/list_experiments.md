# list_experiments

## What it does

Differential-expression and characterization experiments with per-timepoint, DM and metabolomics rollups.

Use to pick experiment_ids and read each one's table_scope before interpreting missing DE rows; for study-level metadata use `list_publications`.
Filters: organism, coculture_partner, table_scope, experiment_ids, search_text, time_course_only, plus the publication / condition filters.
Returns: by_organism, by_treatment_type, by_table_scope, by_omics_type, by_growth_phase, not_found; one row = one experiment.
docs://tools/list_experiments; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| omics_type | list[string] \| None | None | Keep experiments whose omics_type is in this list. Values: list_filter_values('omics_type'). |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| coculture_partner | string \| None | None | Filter by coculture partner organism (word-based, case-insensitive match). Narrows coculture experiments. E.g. 'Alteromonas', 'HOT1A3'. |
| search_text | string \| None | None | Free-text search on experiment name, treatment, control, experimental context, and light condition (Lucene fulltext, case-insensitive). E.g. 'continuous light', 'diel'. |
| time_course_only | bool | False | If true, return only time-course experiments (multiple time points). |
| table_scope | list[string] \| None | None | Filter by table scope — what genes the source DE table contains. Values: 'all_detected_genes', 'significant_any_timepoint', 'significant_only', 'top_n', 'filtered_subset'. E.g. ['all_detected_genes'] for fair cross-experiment comparison. |
| experiment_ids | list[string] \| None | None | Restrict to specific experiments by id (exact match). Combines with other filters via AND. `not_found` in the response lists any provided ids that did not match. Mirrors the filter shape on sibling tools (pathway_enrichment, ontology_landscape). |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Orient — what experiments exist?

```python
list_experiments(summary=True)
```

## Response sketch

```expected-keys
total_entries, total_matching, returned, offset, truncated, by_organism, by_treatment_type, by_background_factors, by_omics_type, by_publication, by_table_scope, by_cluster_type, by_growth_phase, by_value_kind, by_metric_type, by_compartment, time_course_count, score_max, score_median, not_found, warnings, results
```

Result row: `experiment_id, experiment_name, publication_doi, authors, organism_name, treatment_type, background_factors, coculture_partner, omics_type, is_time_course, table_scope, table_scope_detail, …`

## Common mistakes

- If a result row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric. Empty derived_metric_value_kinds means no DM evidence on this experiment.

- Default is detail (summary=false) — use summary=true to see only breakdowns. When summary=true, verbose and limit have no effect.

- gene_count is total genes with expression data, not total significant genes — use genes_by_status for the breakdown.

## Chaining patterns

- list_organisms → list_experiments
- list_publications → list_experiments
- list_filter_values → list_experiments
- list_experiments(search_text=..., verbose=True) → classify → list_experiments(experiment_ids=[...]) for the picked subset
- list_experiments → differential_expression_by_gene
- list_experiments → list_clustering_analyses(experiment_ids=[...])
- list_experiments(compartment=...) → use derived_metric_value_kinds per result row to route to genes_by_{boolean,numeric,categorical}_metric
- list_filter_values(filter_type='metric_type') → list_experiments(search_text='<metric_type>') to find experiments with that metric
- list_experiments (per-row `metabolite_count > 0`) → list_metabolite_assays(experiment_ids=[...]) to inspect the experiment's MetaboliteAssay nodes (numeric vs boolean, compartment, detection-status rollup).
- list_experiments → list_derived_metrics(experiment_ids=[...]) for the experiment's non-DE, column-level evidence (rhythmicity flags, amplitudes, trait classes)
- list_experiments → pathway_enrichment(experiment_ids=[...], organism=...) for ORA over that experiment's DE gene sets

Full reference (all examples, full response format, verbose fields): `docs://tools/list_experiments/full`
