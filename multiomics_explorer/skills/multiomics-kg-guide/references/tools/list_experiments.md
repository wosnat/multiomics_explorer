# list_experiments

## What it does

List differential expression experiments in the knowledge graph.

Start with mode='summary' to see experiment counts by organism, treatment
type, and omics type. Then use mode='detail' with filters to browse
individual experiments. Pass experiment IDs to query_expression for
gene-level results.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string \| None | None | Filter by organism name (case-insensitive partial match on profiled organism and coculture partner). E.g. 'MED4', 'Alteromonas'. |
| treatment_type | list[string] \| None | None | Filter by treatment type(s) (case-insensitive exact match). E.g. ['coculture', 'nitrogen_stress']. Use list_filter_values to see valid values. |
| omics_type | list[string] \| None | None | Filter by omics platform(s) (case-insensitive). E.g. ['RNASEQ', 'PROTEOMICS']. |
| publication_doi | list[string] \| None | None | Filter by publication DOI(s) (case-insensitive exact match). Get DOIs from list_publications. E.g. ['10.1038/ismej.2016.70']. |
| coculture_partner | string \| None | None | Filter by coculture partner organism (case-insensitive partial match). Narrows coculture experiments. E.g. 'Alteromonas', 'HOT1A3'. |
| search_text | string \| None | None | Free-text search on experiment name, treatment, control, experimental context, and light condition (Lucene fulltext, case-insensitive). E.g. 'continuous light', 'diel'. |
| time_course_only | bool | False | If true, return only time-course experiments (multiple time points). |
| mode | string | summary | 'summary' returns breakdowns by organism, treatment type, and omics type to guide filtering. 'detail' returns individual experiments with gene counts. Start with summary to orient, then use detail with filters. |
| verbose | bool | False | Detail mode only. Include experiment name, publication title, treatment/control descriptions, and experimental conditions (light, medium, temperature, statistical test, context). |
| limit | int | 50 | Detail mode only. Max results. |

**Discovery:** use `list_filter_values` for valid treatment types,
`list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, returned, truncated, by_organism, by_treatment_type, by_omics_type, by_publication, time_course_count, score_max, score_median, results
```

- **total_entries** (int): Total experiments in the KG (unfiltered)
- **total_matching** (int): Experiments matching filters
- **returned** (int): Number of results returned (0 in summary mode)
- **truncated** (bool): True if results were truncated by limit, or summary mode
- **by_organism** (list[OrganismBreakdown]): Experiment counts per organism, sorted by count descending
- **by_treatment_type** (list[TreatmentTypeBreakdown]): Experiment counts per treatment type, sorted by count descending
- **by_omics_type** (list[OmicsTypeBreakdown]): Experiment counts per omics platform, sorted by count descending
- **by_publication** (list[PublicationBreakdown]): Experiment counts per publication, sorted by count descending
- **time_course_count** (int): Number of time-course experiments in matching set
- **score_max** (float | None): Max Lucene relevance score, present only when search_text is used (e.g. 4.52)
- **score_median** (float | None): Median Lucene relevance score, present only when search_text is used (e.g. 1.23)

### Per-result fields

| Field | Type | Description |
|---|---|---|
| experiment_id | string | Experiment identifier (e.g. '10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq') |
| publication_doi | string | Publication DOI (e.g. '10.1038/ismej.2016.70') |
| organism_strain | string | Profiled organism (e.g. 'Prochlorococcus MED4') |
| treatment_type | string | Treatment category (e.g. 'coculture', 'nitrogen_stress') |
| coculture_partner | string \| None (optional) | Interacting organism — coculture partner or phage. Null when no interacting organism (e.g. 'Alteromonas macleodii HOT1A3', 'Phage') |
| omics_type | string | Omics platform (e.g. 'RNASEQ', 'MICROARRAY', 'PROTEOMICS') |
| is_time_course | bool | Whether experiment has multiple time points |
| time_points | list[TimePoint] \| None (optional) | Per-time-point gene counts. Omitted for non-time-course experiments. |
| gene_count | int | Total genes with expression data (e.g. 1696) |
| significant_count | int | Genes with significant differential expression (e.g. 423) |
| score | float \| None (optional) | Lucene relevance score, present only when search_text is used (e.g. 2.45) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| name | string \| None (optional) | Experiment display name (e.g. 'MED4 Coculture with Alteromonas HOT1A3 vs Pro99 medium growth conditions (RNASEQ)') |
| publication_title | string \| None (optional) | Publication title |
| treatment | string \| None (optional) | Treatment description (e.g. 'Coculture with Alteromonas HOT1A3') |
| control | string \| None (optional) | Control description (e.g. 'Pro99 medium growth conditions') |
| light_condition | string \| None (optional) | Light regime (e.g. 'continuous light') |
| light_intensity | string \| None (optional) | Light intensity (e.g. '10 umol photons m-2 s-1') |
| medium | string \| None (optional) | Growth medium (e.g. 'Pro99') |
| temperature | string \| None (optional) | Temperature (e.g. '24C') |
| statistical_test | string \| None (optional) | Statistical method (e.g. 'Rockhopper') |
| experimental_context | string \| None (optional) | Context summary (e.g. 'in Pro99 medium under continuous light') |

## Few-shot examples

### Example 1: Orient — what experiments exist?

```example-call
list_experiments()
```

```example-response
{"total_entries": 76, "total_matching": 76,
 "by_organism": [{"organism_strain": "Prochlorococcus MED4", "experiment_count": 30}, ...],
 "by_treatment_type": [{"treatment_type": "coculture", "experiment_count": 16}, ...],
 "by_omics_type": [{"omics_type": "RNASEQ", "experiment_count": 48}, ...],
 "time_course_count": 29, "returned": 0, "truncated": true, "results": []}
```

### Example 2: Summary for MED4 only

```example-call
list_experiments(organism="MED4")
```

### Example 3: Browse coculture experiments with Alteromonas

```example-call
list_experiments(mode="detail", treatment_type=["coculture"], coculture_partner="Alteromonas")
```

### Example 4: Time-course nitrogen stress in MED4

```example-call
list_experiments(mode="detail", organism="MED4", treatment_type=["nitrogen_stress"], time_course_only=True)
```

### Example 5: From publication to expression data

```
Step 1: list_publications(search_text="Biller")
        → get DOI from results

Step 2: list_experiments(mode="detail", publication_doi=["10.1038/ismej.2016.70"])
        → browse experiments, pick experiment_id

Step 3: query_expression(experiment_id="...")
        → get gene-level results
```

### Example 6: Orient then drill down

```
Step 1: list_experiments()
        → see 76 total, by_organism: MED4 (30), by_treatment_type: coculture (16), by_omics_type: RNASEQ (48)

Step 2: list_experiments(mode="detail", organism="MED4", treatment_type=["coculture"])
        → browse the MED4 coculture experiments

Step 3: query_expression(experiment_id="...")
        → get gene-level results
```

## Chaining patterns

```
list_organisms → list_experiments
list_publications → list_experiments
list_filter_values → list_experiments
list_experiments → query_expression
```

## Common mistakes

- Default mode is summary — use mode='detail' to see individual experiments

- gene_count is total genes with expression data, not total significant genes — use significant_count for that

- time_points is omitted for non-time-course experiments, not an empty list

- verbose and limit only apply to detail mode, ignored in summary

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
# returns dict with keys: total_entries, total_matching, by_organism, by_treatment_type, by_omics_type, by_publication, time_course_count, score_max, score_median, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
