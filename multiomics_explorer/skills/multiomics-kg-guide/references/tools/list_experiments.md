# list_experiments

## What it does

List differential expression experiments in the knowledge graph.

Returns summary breakdowns (by organism, treatment type, omics type,
table scope) plus individual experiments. Use summary=true to see only
breakdowns, then drill into detail with filters.

table_scope indicates what genes each experiment's source DE table
contains — critical for interpreting missing genes. Use
table_scope=['all_detected_genes'] to restrict to experiments that
report all assayed genes (fair for cross-experiment comparison).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string \| None | None | Filter by organism name (case-insensitive partial match on profiled organism and coculture partner). E.g. 'MED4', 'Alteromonas'. |
| treatment_type | list[string] \| None | None | Filter by treatment type(s) (case-insensitive exact match). E.g. ['coculture', 'nitrogen_stress']. Use list_filter_values to see valid values. |
| background_factors | list[string] \| None | None | Filter by background experimental factors (case-insensitive exact match). E.g. ['axenic', 'diel_cycle']. Background factors describe experimental context beyond the primary treatment. |
| growth_phases | list[string] \| None | None | Filter by growth phase(s) (case-insensitive). Physiological state of the culture at sampling time. E.g. ['exponential', 'nutrient_limited']. |
| omics_type | list[string] \| None | None | Filter by omics platform(s) (case-insensitive). E.g. ['RNASEQ', 'PROTEOMICS']. |
| publication_doi | list[string] \| None | None | Filter by publication DOI(s) (case-insensitive exact match). Get DOIs from list_publications. E.g. ['10.1038/ismej.2016.70']. |
| coculture_partner | string \| None | None | Filter by coculture partner organism (case-insensitive partial match). Narrows coculture experiments. E.g. 'Alteromonas', 'HOT1A3'. |
| search_text | string \| None | None | Free-text search on experiment name, treatment, control, experimental context, and light condition (Lucene fulltext, case-insensitive). E.g. 'continuous light', 'diel'. |
| time_course_only | bool | False | If true, return only time-course experiments (multiple time points). |
| table_scope | list[string] \| None | None | Filter by table scope — what genes the source DE table contains. Values: 'all_detected_genes', 'significant_any_timepoint', 'significant_only', 'top_n', 'filtered_subset'. E.g. ['all_detected_genes'] for fair cross-experiment comparison. |
| summary | bool | False | When true, return only summary breakdowns (by organism, treatment type, omics type, table scope) with no individual experiments. Use to orient before drilling into detail. |
| verbose | bool | False | Include publication title, treatment/control descriptions, and experimental conditions (light, medium, temperature, statistical test, context). |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, returned, offset, truncated, by_organism, by_treatment_type, by_background_factors, by_omics_type, by_publication, by_table_scope, by_cluster_type, by_growth_phase, time_course_count, score_max, score_median, results
```

- **total_entries** (int): Total experiments in the KG (unfiltered)
- **total_matching** (int): Experiments matching filters
- **returned** (int): Number of results returned (0 when summary=true)
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if results were truncated by limit or summary=true
- **by_organism** (list[OrganismBreakdown]): Experiment counts per organism, sorted by count descending
- **by_treatment_type** (list[TreatmentTypeBreakdown]): Experiment counts per treatment type, sorted by count descending
- **by_background_factors** (list[BackgroundFactorBreakdown]): Experiment counts per background factor, sorted by count descending
- **by_omics_type** (list[OmicsTypeBreakdown]): Experiment counts per omics platform, sorted by count descending
- **by_publication** (list[PublicationBreakdown]): Experiment counts per publication, sorted by count descending
- **by_table_scope** (list[TableScopeBreakdown]): Experiment counts per table scope, sorted by count descending
- **by_cluster_type** (list[ClusterTypeBreakdown]): Experiment counts per cluster type, sorted by count descending
- **by_growth_phase** (list[GrowthPhaseBreakdown]): Experiment counts per growth phase, sorted by count descending
- **time_course_count** (int): Number of time-course experiments in matching set
- **score_max** (float | None): Max Lucene relevance score, present only when search_text is used (e.g. 4.52)
- **score_median** (float | None): Median Lucene relevance score, present only when search_text is used (e.g. 1.23)

### Per-result fields

| Field | Type | Description |
|---|---|---|
| experiment_id | string | Experiment identifier (e.g. '10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq') |
| experiment_name | string | Experiment display name (e.g. 'MED4 Coculture with Alteromonas HOT1A3 vs Pro99 medium growth conditions (RNASEQ)') |
| publication_doi | string | Publication DOI (e.g. '10.1038/ismej.2016.70') |
| organism_name | string | Profiled organism (e.g. 'Prochlorococcus MED4') |
| treatment_type | list[string] | Treatment categories (e.g. ['coculture'], ['nitrogen_stress', 'coculture']) |
| background_factors | list[string] (optional) | Background experimental factors (e.g. ['axenic', 'continuous_light']). Empty list when none specified. |
| coculture_partner | string \| None (optional) | Interacting organism — coculture partner or phage. Null when no interacting organism (e.g. 'Alteromonas macleodii HOT1A3', 'Phage') |
| omics_type | string | Omics platform (e.g. 'RNASEQ', 'MICROARRAY', 'PROTEOMICS') |
| is_time_course | bool | Whether experiment has multiple time points |
| table_scope | string \| None (optional) | What genes the source DE table contains. Values: all_detected_genes, significant_any_timepoint, significant_only, top_n, filtered_subset. Critical for interpreting missing genes. |
| table_scope_detail | string \| None (optional) | Free-text clarification of table_scope (e.g. 'FDR < 0.05 and |logFC| > 0.8') |
| gene_count | int | Total genes with expression data (e.g. 1696) |
| genes_by_status | GeneStatusBreakdown | Gene counts by expression status |
| timepoints | list[TimePoint] \| None (optional) | Per-timepoint gene counts. Omitted for non-time-course experiments. |
| clustering_analysis_count | int (optional) | Number of clustering analyses for this experiment (e.g. 4) |
| cluster_types | list[string] (optional) | Distinct cluster types (e.g. ['condition_comparison']) |
| growth_phases | list[string] (optional) | Distinct growth phases in this experiment. Physiological state of the culture at sampling — timepoint-level, not gene-specific. |
| time_point_growth_phases | list[string] (optional) | Growth phase per timepoint, parallel to timepoints array. Same phase for all genes at each timepoint. |
| score | float \| None (optional) | Lucene relevance score, present only when search_text is used (e.g. 2.45) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| publication_title | string \| None (optional) | Publication title |
| treatment | string \| None (optional) | Treatment description (e.g. 'Coculture with Alteromonas HOT1A3') |
| control | string \| None (optional) | Control description (e.g. 'Pro99 medium growth conditions') |
| light_condition | string \| None (optional) | Light regime (e.g. 'continuous light') |
| light_intensity | string \| None (optional) | Light intensity (e.g. '10 umol photons m-2 s-1') |
| medium | string \| None (optional) | Growth medium (e.g. 'Pro99') |
| temperature | string \| None (optional) | Temperature (e.g. '24C') |
| statistical_test | string \| None (optional) | Statistical method (e.g. 'Rockhopper') |
| experimental_context | string \| None (optional) | Context summary (e.g. 'in Pro99 medium under continuous light') |
| cluster_count | int \| None (optional) | Total gene clusters across analyses (only with verbose=True, e.g. 20) |

## Few-shot examples

### Example 1: Orient — what experiments exist?

```example-call
list_experiments(summary=True)
```

```example-response
{"total_entries": 76, "total_matching": 76,
 "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 30}, ...],
 "by_treatment_type": [{"treatment_type": "coculture", "count": 16}, ...],
 "by_omics_type": [{"omics_type": "RNASEQ", "count": 48}, ...],
 "by_table_scope": [{"table_scope": "all_detected_genes", "count": 40}, ...],
 "by_cluster_type": [{"cluster_type": "condition_comparison", "count": 7}, ...],
 "time_course_count": 29, "returned": 0, "truncated": true, "offset": 0, "results": []}
```

### Example 2: Summary for MED4 only

```example-call
list_experiments(summary=True, organism="MED4")
```

### Example 3: Browse coculture experiments with Alteromonas

```example-call
list_experiments(treatment_type=["coculture"], coculture_partner="Alteromonas")
```

### Example 4: Time-course nitrogen stress in MED4

```example-call
list_experiments(organism="MED4", treatment_type=["nitrogen_stress"], time_course_only=True)
```

### Example 5: From publication to expression data

```
Step 1: list_publications(search_text="Biller")
        → get DOI from results

Step 2: list_experiments(publication_doi=["10.1038/ismej.2016.70"])
        → browse experiments, pick experiment_id

Step 3: differential_expression_by_gene(organism="MED4", experiment_ids=["..."])
        → get gene-level results
```

### Example 6: Orient then drill down

```
Step 1: list_experiments(summary=True)
        → see 76 total, by_organism: MED4 (30), by_treatment_type: coculture (16), by_omics_type: RNASEQ (48)

Step 2: list_experiments(organism="MED4", treatment_type=["coculture"])
        → browse the MED4 coculture experiments

Step 3: differential_expression_by_gene(organism="MED4", experiment_ids=["..."])
        → get gene-level results
```

## Chaining patterns

```
list_organisms → list_experiments
list_publications → list_experiments
list_filter_values → list_experiments
list_experiments → differential_expression_by_gene
list_experiments → list_clustering_analyses(experiment_ids=[...])
```

## Common mistakes

- Default is detail (summary=false) — use summary=true to see only breakdowns

- gene_count is total genes with expression data, not total significant genes — use genes_by_status for the breakdown

- timepoints is omitted for non-time-course experiments, not an empty list

- When summary=true, verbose and limit have no effect

- Check table_scope before interpreting missing genes — some experiments only include significant genes

- growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — NOT a gene-specific property

```mistake
list_experiments(publication='Biller 2018')
```

```correction
list_publications(search_text='Biller') then list_experiments(publication_doi=['10.1038/...'])
```

## Package import equivalent

```python
from multiomics_explorer import list_experiments

result = list_experiments()
# returns dict with keys: total_entries, total_matching, offset, by_organism, by_treatment_type, by_background_factors, by_omics_type, by_publication, by_table_scope, by_cluster_type, by_growth_phase, time_course_count, score_max, score_median, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
