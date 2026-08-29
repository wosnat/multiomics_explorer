# list_experiments

## What it does

List differential-expression experiments with rich breakdowns (organism, treatment, omics, table_scope, growth_phase, DM rollups, metabolomics rollups). Use `summary=true` to see only breakdowns.

table_scope is critical for interpreting missing genes — `'all_detected_genes'` keeps tested-absent rows (the `not_significant` bucket reflects real biology); `'significant_only'` collapses them. Use `table_scope=['all_detected_genes']` to restrict to experiments fair for cross-experiment comparison. See `docs://guide/conventions` for the broader tested-absent framing.

Routing: drill via `differential_expression_by_gene(experiment_ids=[id])` for per-gene DE; `list_clustering_analyses(experiment_ids=[id])`; `list_derived_metrics(experiment_ids=[id])`; `pathway_enrichment(experiment_ids=[id])`; `list_metabolite_assays(experiment_ids=[id])` when `metabolite_count > 0`.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string \| None | None | Filter to experiments where this organism is the profiled organism (word-based, case-insensitive match; 'MED4' works). For partner-side filtering, use coculture_partner=; the two filters AND-compose. |
| treatment_type | list[string] \| None | None | Filter by treatment type(s) (case-insensitive exact match). E.g. ['coculture', 'nitrogen']. Live vocabulary: list_filter_values(filter_type='treatment_type') or list_experiments(summary=True). |
| background_factors | list[string] \| None | None | Filter by background experimental factors (case-insensitive exact match). E.g. ['axenic', 'diel']. Background factors describe experimental context beyond the primary treatment. Live vocabulary: list_experiments(summary=True). |
| growth_phases | list[string] \| None | None | Filter by growth phase(s) (case-insensitive). Physiological state of the culture at sampling time. E.g. ['exponential', 'nutrient_limited']. |
| omics_type | list[string] \| None | None | Filter by omics platform(s) (case-insensitive). E.g. ['RNASEQ', 'PROTEOMICS']. |
| publication_doi | list[string] \| None | None | Filter by publication DOI(s) (case-insensitive exact match). Get DOIs from list_publications. E.g. ['10.1038/ismej.2016.70']. |
| coculture_partner | string \| None | None | Filter by coculture partner organism (word-based, case-insensitive match). Narrows coculture experiments. E.g. 'Alteromonas', 'HOT1A3'. |
| search_text | string \| None | None | Free-text search on experiment name, treatment, control, experimental context, and light condition (Lucene fulltext, case-insensitive). E.g. 'continuous light', 'diel'. |
| time_course_only | bool | False | If true, return only time-course experiments (multiple time points). |
| table_scope | list[string] \| None | None | Filter by table scope — what genes the source DE table contains. Values: 'all_detected_genes', 'significant_any_timepoint', 'significant_only', 'top_n', 'filtered_subset'. E.g. ['all_detected_genes'] for fair cross-experiment comparison. |
| experiment_ids | list[string] \| None | None | Restrict to specific experiments by id (exact match). Combines with other filters via AND. `not_found` in the response lists any provided ids that did not match. Mirrors the filter shape on sibling tools (pathway_enrichment, ontology_landscape). |
| compartment | string \| None | None | Filter by wet-lab fraction (exact match on scalar Experiment.compartment). E.g. 'whole_cell', 'vesicle', 'exoproteome'. Use list_filter_values(filter_type='compartment') to enumerate valid values. |
| summary | bool | False | When true, return only summary breakdowns (by organism, treatment type, omics type, table scope) with no individual experiments. Use to orient before drilling into detail. |
| verbose | bool | False | Include publication title, treatment/control descriptions, and experimental conditions (light, medium, temperature, statistical test, context). |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, returned, offset, truncated, by_organism, by_treatment_type, by_background_factors, by_omics_type, by_publication, by_table_scope, by_cluster_type, by_growth_phase, by_value_kind, by_metric_type, by_compartment, time_course_count, score_max, score_median, not_found, results
```

- **total_entries** (int): Total experiments in the KG (unfiltered).
- **total_matching** (int): Experiments matching filters.
- **returned** (int): Number of results returned (0 when summary=true).
- **offset** (int): Offset into full result set.
- **truncated** (bool): True if results were truncated by limit or summary=true.
- **by_organism** (list[OrganismBreakdown]): Experiment counts per organism, sorted desc.
- **by_treatment_type** (list[TreatmentTypeBreakdown]): Experiment counts per treatment type, sorted desc.
- **by_background_factors** (list[BackgroundFactorBreakdown]): Experiment counts per background factor, sorted desc.
- **by_omics_type** (list[OmicsTypeBreakdown]): Experiment counts per omics platform, sorted desc.
- **by_publication** (list[PublicationBreakdown]): Experiment counts per publication, sorted desc.
- **by_table_scope** (list[TableScopeBreakdown]): Experiment counts per table scope, sorted desc.
- **by_cluster_type** (list[ClusterTypeBreakdown]): Experiment counts per cluster type, sorted desc.
- **by_growth_phase** (list[GrowthPhaseBreakdown]): Experiment counts per growth phase, sorted desc.
- **by_value_kind** (list[ExpValueKindBreakdown]): Experiment counts by DerivedMetric value_kind across matching experiments.
- **by_metric_type** (list[ExpMetricTypeBreakdown]): Experiment counts by DerivedMetric metric_type across matching experiments.
- **by_compartment** (list[ExpCompartmentBreakdown]): Experiment counts per wet-lab compartment.
- **time_course_count** (int): Number of time-course experiments in matching set.
- **score_max** (float | None): Max Lucene relevance score, present only when search_text is used.
- **score_median** (float | None): Median Lucene relevance score, present only when search_text is used.
- **not_found** (list[string]): Input experiment_ids that did not match any Experiment node (empty unless experiment_ids was provided).

### Per-result fields

| Field | Type | Description |
|---|---|---|
| experiment_id | string | Experiment identifier (e.g. '10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq'). |
| experiment_name | string | Experiment display name. |
| publication_doi | string | Publication DOI (e.g. '10.1038/ismej.2016.70'). |
| authors | list[string] (optional) | Publication authors. Sourced from Publication.authors via the Has_experiment edge — no need to join with list_publications for author attribution. |
| organism_name | string | Profiled organism (e.g. 'Prochlorococcus MED4'). |
| treatment_type | list[string] | Treatment categories (e.g. ['coculture'], ['nitrogen', 'coculture']). Live vocabulary: list_filter_values(filter_type='treatment_type') or list_experiments(summary=True). |
| background_factors | list[string] (optional) | Background experimental factors (e.g. ['axenic', 'light']). Empty list when none specified. Live vocabulary: list_experiments(summary=True). |
| coculture_partner | string \| None (optional) | Interacting organism — coculture partner or phage. Null when no interacting organism. |
| omics_type | string | Omics platform (e.g. 'RNASEQ', 'MICROARRAY', 'PROTEOMICS'). |
| is_time_course | bool | Whether experiment has multiple time points. |
| table_scope | string \| None (optional) | What genes the source DE table contains. Values: all_detected_genes (tested-absent rows kept — `not_significant` represents real biology), significant_any_timepoint, significant_only (tested-absent rows collapsed), top_n, filtered_subset. Critical for interpreting missing genes — see docs://guide/conventions. |
| table_scope_detail | string \| None (optional) | Free-text clarification of table_scope (e.g. 'FDR < 0.05 and |logFC| > 0.8'). |
| gene_count | int | Cumulative row count across timepoints (= sum(time_point_totals) for time-course experiments — a 6-TP experiment with 1697 genes/TP has gene_count=10182). Equals distinct_gene_count for non-time-course experiments. |
| distinct_gene_count | int | Distinct gene count across the experiment — unique gene IDs with at least one measurement edge, regardless of timepoint. Use for detection-power / pathway-background sizing. distinct_gene_count <= gene_count. |
| genes_by_status | GeneStatusBreakdown | Gene counts by expression status. |
| timepoints | list[TimePoint] \| None (optional) | Per-timepoint gene counts. Omitted for non-time-course experiments. |
| clustering_analysis_count | int (optional) | Number of clustering analyses for this experiment. |
| cluster_types | list[string] (optional) | Distinct cluster types (e.g. ['condition_comparison']). |
| growth_phases | list[string] (optional) | Distinct growth phases in this experiment. Timepoint-level condition, not gene-specific. |
| derived_metric_count | int (optional) | Number of DerivedMetrics associated with this experiment. |
| derived_metric_value_kinds | list[string] (optional) | Distinct DerivedMetric value kinds for this experiment (subset of {numeric, boolean, categorical}). Use to route to genes_by_{kind}_metric. |
| compartment | string \| None (optional) | Wet-lab fraction this experiment profiles (e.g. 'whole_cell', 'vesicle', 'exoproteome'). Scalar per experiment. |
| metabolite_count | int (optional) | Distinct metabolites measured in this experiment (precomputed Experiment.metabolite_count). Non-zero on metabolomics-paired experiments. When > 0, drill via list_metabolite_assays(experiment_ids=[...]). |
| metabolite_assay_count | int (optional) | Distinct MetaboliteAssay edges anchored to this experiment (precomputed). |
| metabolite_compartments | list[string] (optional) | Wet-lab compartments measured for metabolomics in this experiment (subset of {'whole_cell', 'extracellular', 'vesicle'}). Populated only when metabolite_assay_count > 0. |
| score | float \| None (optional) | Lucene relevance score, present only when search_text is used. |
| derived_metric_gene_count | int \| None (optional) | Number of distinct genes with DerivedMetric annotations in this experiment (verbose-only). |
| derived_metric_types | list[string] \| None (optional) | Distinct DerivedMetric metric_type values for this experiment (verbose-only). |
| reports_derived_metric_types | list[string] \| None (optional) | DerivedMetric types reported by (not just associated with) this experiment (verbose-only). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| publication_title | string \| None (optional) | Publication title (verbose-only). |
| treatment | string \| None (optional) | Treatment description (verbose-only, e.g. 'Coculture with Alteromonas HOT1A3'). |
| control | string \| None (optional) | Control description (verbose-only). |
| light_condition | string \| None (optional) | Light regime (verbose-only). |
| light_intensity | string \| None (optional) | Light intensity (verbose-only). |
| medium | string \| None (optional) | Growth medium (verbose-only). |
| temperature | string \| None (optional) | Temperature (verbose-only). |
| statistical_test | string \| None (optional) | Statistical method (verbose-only). |
| experimental_context | string \| None (optional) | Context summary (verbose-only). |
| cluster_count | int \| None (optional) | Total gene clusters across analyses (verbose-only). |

## Few-shot examples

### Example 1: Orient — what experiments exist?

```example-call
list_experiments(summary=True)
```

```example-response
{
  "total_entries": 209,
  "total_matching": 209,
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "by_organism": [
    {"organism_name": "Prochlorococcus MED4", "count": 45},
    {"organism_name": "Alteromonas (MarRef v6)", "count": 20},
    {"organism_name": "Marinobacter (MarRef v6)", "count": 20},
    {"organism_name": "Prochlorococcus MIT9313", "count": 18},
    {"organism_name": "Alteromonas macleodii EZ55", "count": 12},
    ...
  ],
  "by_treatment_type": [
    {"treatment_type": "carbon", "count": 78},
    {"treatment_type": "coculture", "count": 76},
    {"treatment_type": "compartment", "count": 17},
    {"treatment_type": "nitrogen", "count": 16},
    {"treatment_type": "light", "count": 13},
    ...
  ],
  "by_background_factors": [
    {"background_factor": "light", "count": 127},
    {"background_factor": "axenic", "count": 90},
    {"background_factor": "coculture", "count": 58},
    {"background_factor": "darkness", "count": 37},
    {"background_factor": "diel", "count": 19},
    ...
  ],
  "by_omics_type": [
    {"omics_type": "PROTEOMICS", "count": 74},
    {"omics_type": "RNASEQ", "count": 71},
    {"omics_type": "MICROARRAY", "count": 30},
    {"omics_type": "METABOLOMICS", "count": 12},
    {"omics_type": "VESICLE_PROTEOMICS", "count": 10},
    ...
  ],
  "by_publication": [
    {"publication_doi": "10.1128/spectrum.03275-22", "count": 60},
    {"publication_doi": "10.1038/s43705-022-00197-2", "count": 11},
    {"publication_doi": "10.1101/2025.11.24.690089", "count": 10},
    {"publication_doi": "10.1111/1462-2920.15834", "count": 6},
    {"publication_doi": "10.1128/JB.01097-06", "count": 6},
    ...
  ],
  "by_table_scope": [
    {"table_scope": "all_detected_genes", "count": 111},
    {"table_scope": "significant_only", "count": 40},
    {"table_scope": "filtered_subset", "count": 21},
    {"table_scope": "significant_any_timepoint", "count": 13},
    {"table_scope": "top_n", "count": 7}
  ],
  "by_cluster_type": [
    {"cluster_type": "time_course", "count": 9},
    {"cluster_type": "diel", "count": 2},
    {"cluster_type": "condition_comparison", "count": 2},
    {"cluster_type": "decay_pattern", "count": 1}
  ],
  "by_growth_phase": [
    {"growth_phase": "exponential", "count": 37},
    {"growth_phase": "darkness", "count": 33},
    {"growth_phase": "stationary", "count": 32},
    {"growth_phase": "acute_stress", "count": 26},
    {"growth_phase": "acclimated_steady_state", "count": 23},
    ...
  ],
  "by_value_kind": [
    {"value_kind": "numeric", "count": 17},
    {"value_kind": "boolean", "count": 13},
    {"value_kind": "categorical", "count": 8}
  ],
  "by_metric_type": [
    {"metric_type": "log2_mv_cell_enrichment", "count": 6},
    {"metric_type": "prop_abund_cells_percent", "count": 6},
    {"metric_type": "prop_abund_mvs_percent", "count": 6},
    {"metric_type": "mascot_identification_probability", "count": 2},
    {"metric_type": "predicted_subcellular_localization", "count": 2},
    ...
  ],
  "by_compartment": [
    {"compartment": "whole_cell", "count": 183},
    {"compartment": "vesicle", "count": 13},
    {"compartment": "exoproteome", "count": 10},
    {"compartment": "extracellular", "count": 3}
  ],
  "time_course_count": 41,
  "score_max": null,
  "score_median": null,
  "not_found": [],
  "results": []
}
```

### Example 2: Summary for MED4 only

```example-call
list_experiments(summary=True, organism="MED4")
```

### Example 3: Browse coculture experiments with Alteromonas

```example-call
list_experiments(treatment_type=["coculture"], coculture_partner="Alteromonas")
```

### Example 4: Time-course nitrogen experiments in MED4

```example-call
list_experiments(organism="MED4", treatment_type=["nitrogen"], time_course_only=True)
```

*treatment_type values are short nouns from a live vocabulary ('nitrogen', not 'nitrogen_stress') — an unknown value returns 0 rows, not an error.*

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
        → read total_entries, then by_organism / by_treatment_type / by_omics_type
          to see where the bulk of the experiments sit (MED4 is the best-covered
          organism; carbon and coculture are the largest treatment groups)

Step 2: list_experiments(organism="MED4", treatment_type=["coculture"])
        → browse the MED4 coculture experiments

Step 3: differential_expression_by_gene(organism="MED4", experiment_ids=["..."])
        → get gene-level results
```

### Example 7: Fetch metadata for a known experiment_id list

```example-call
list_experiments(experiment_ids=["10.1101/2025.11.24.690089_coculture_prochlorococcus_med4_hot1a3_rnaseq", "10.1101/2025.11.24.690089_coculture_alteromonas_hot1a3_med4_rnaseq"], verbose=True)
```

*experiment_ids are the KG's Experiment.id strings (DOI-prefixed); copy them from an earlier list_experiments result — unknown ids land in not_found.*

### Example 8: Find vesicle-fraction experiments

```example-call
list_experiments(compartment="vesicle", limit=2)
```

```example-response
{
  "total_entries": 209,
  "total_matching": 13,
  "returned": 2,
  "offset": 0,
  "truncated": true,
  "by_organism": [
    {"organism_name": "Prochlorococcus MIT9313", "count": 3},
    {"organism_name": "Prochlorococcus MED4", "count": 2},
    {"organism_name": "Prochlorococcus MIT9312", "count": 2},
    {"organism_name": "Alteromonas macleodii AD45", "count": 1},
    {"organism_name": "Alteromonas macleodii ATCC27126", "count": 1},
    ...
  ],
  "by_treatment_type": [{"treatment_type": "compartment", "count": 13}],
  "by_background_factors": [
    {"background_factor": "axenic", "count": 13},
    {"background_factor": "light", "count": 7},
    {"background_factor": "darkness", "count": 6}
  ],
  "by_omics_type": [
    {"omics_type": "VESICLE_PROTEOMICS", "count": 10},
    {"omics_type": "METABOLOMICS", "count": 2},
    {"omics_type": "VESICLE_DNASEQ", "count": 1}
  ],
  "by_publication": [
    {"publication_doi": "10.1093/femsml/uqac025", "count": 6},
    {"publication_doi": "10.1111/1462-2920.15834", "count": 4},
    {"publication_doi": "10.1126/science.1243457", "count": 3}
  ],
  "by_table_scope": [
    {"table_scope": "top_n", "count": 7},
    {"table_scope": "significant_only", "count": 2},
    {"table_scope": "all_detected_genes", "count": 2}
  ],
  "by_cluster_type": [],
  "by_growth_phase": [],
  "by_value_kind": [
    {"value_kind": "numeric", "count": 11},
    {"value_kind": "boolean", "count": 2},
    {"value_kind": "categorical", "count": 2}
  ],
  "by_metric_type": [
    {"metric_type": "log2_mv_cell_enrichment", "count": 6},
    {"metric_type": "prop_abund_cells_percent", "count": 6},
    {"metric_type": "prop_abund_mvs_percent", "count": 6},
    {"metric_type": "mascot_identification_probability", "count": 2},
    {"metric_type": "predicted_subcellular_localization", "count": 2},
    ...
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 13}],
  "time_course_count": 0,
  "score_max": null,
  "score_median": null,
  "not_found": [],
  "results": [
    {
      "experiment_id": "10.1093/femsml/uqac025_vesicle_proteomics_ad45",
      "experiment_name": "AD45 vesicle vs whole-cell proteome (label-free LC-MS/MS)",
      "publication_doi": "10.1093/femsml/uqac025",
      "authors": [
        "Eduard Fadeev",
        "Cécile Carpaneto Bastos",
        "Jennifer H. Hennenfeind",
        "Steven J. Biller",
        "Daniel Sher",
        ...
      ],
      "organism_name": "Alteromonas macleodii AD45",
      "treatment_type": ["compartment"],
      "background_factors": ["axenic", "darkness"],
      "coculture_partner": null,
      "omics_type": "VESICLE_PROTEOMICS",
      "is_time_course": false,
      "table_scope": "top_n",
      "table_scope_detail": "Top-N most-abundant MV proteins per strain; complementary cell-fraction percentages provided where the protein was al...",
      "gene_count": 0,
      "distinct_gene_count": 0,
      "genes_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 0},
      "timepoints": null,
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 3,
      "derived_metric_value_kinds": ["numeric"],
      "compartment": "vesicle",
      "metabolite_count": 0,
      "metabolite_assay_count": 0,
      "metabolite_compartments": []
    },
    {
      "experiment_id": "10.1093/femsml/uqac025_vesicle_proteomics_atcc27126",
      "experiment_name": "ATCC27126 vesicle vs whole-cell proteome (label-free LC-MS/MS)",
      "publication_doi": "10.1093/femsml/uqac025",
      "authors": [
        "Eduard Fadeev",
        "Cécile Carpaneto Bastos",
        "Jennifer H. Hennenfeind",
        "Steven J. Biller",
        "Daniel Sher",
        ...
      ],
      "organism_name": "Alteromonas macleodii ATCC27126",
      "treatment_type": ["compartment"],
      "background_factors": ["axenic", "darkness"],
      "coculture_partner": null,
      "omics_type": "VESICLE_PROTEOMICS",
      "is_time_course": false,
      "table_scope": "top_n",
      "table_scope_detail": "Top-N most-abundant MV proteins per strain; complementary cell-fraction percentages provided where the protein was al...",
      "gene_count": 0,
      "distinct_gene_count": 0,
      "genes_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 0},
      "timepoints": null,
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 3,
      "derived_metric_value_kinds": ["numeric"],
      "compartment": "vesicle",
      "metabolite_count": 0,
      "metabolite_assay_count": 0,
      "metabolite_compartments": []
    }
  ]
}
```

### Example 9: Inspect metabolomics-bearing experiments (per-row metabolite rollups)

```example-call
list_experiments(experiment_ids=["10.1128/msystems.01261-22_kujawinski_metabolomics_9301_whole_cell", "10.1073/pnas.2213271120_chitosan_addition_mit9313_metabolomics"])
```

```example-response
{
  "total_entries": 209,
  "total_matching": 2,
  "returned": 2,
  "offset": 0,
  "truncated": false,
  "by_organism": [
    {"organism_name": "Prochlorococcus MIT9301", "count": 1},
    {"organism_name": "Prochlorococcus MIT9313", "count": 1}
  ],
  "by_treatment_type": [{"treatment_type": "phosphorus", "count": 1}, {"treatment_type": "carbon", "count": 1}],
  "by_background_factors": [{"background_factor": "axenic", "count": 2}, {"background_factor": "light", "count": 1}],
  "by_omics_type": [{"omics_type": "METABOLOMICS", "count": 2}],
  "by_publication": [
    {"publication_doi": "10.1128/msystems.01261-22", "count": 1},
    {"publication_doi": "10.1073/pnas.2213271120", "count": 1}
  ],
  "by_table_scope": [],
  "by_cluster_type": [],
  "by_growth_phase": [],
  "by_value_kind": [],
  "by_metric_type": [],
  "by_compartment": [{"compartment": "whole_cell", "count": 2}],
  "time_course_count": 0,
  "score_max": null,
  "score_median": null,
  "not_found": [],
  "results": [
    {
      "experiment_id": "10.1128/msystems.01261-22_kujawinski_metabolomics_9301_whole_cell",
      "experiment_name": "MIT9301 metabolite diversity (intracellular pool)",
      "publication_doi": "10.1128/msystems.01261-22",
      "authors": [
        "Elizabeth B. Kujawinski",
        "Rogier Braakman",
        "Krista Longnecker",
        "Jamie W. Becker",
        "Sallie W. Chisholm",
        ...
      ],
      "organism_name": "Prochlorococcus MIT9301",
      "treatment_type": ["phosphorus"],
      "background_factors": ["axenic"],
      "coculture_partner": null,
      "omics_type": "METABOLOMICS",
      "is_time_course": false,
      "table_scope": null,
      "table_scope_detail": "",
      "gene_count": 0,
      "distinct_gene_count": 0,
      "genes_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 0},
      "timepoints": null,
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "compartment": "whole_cell",
      "metabolite_count": 99,
      "metabolite_assay_count": 3,
      "metabolite_compartments": ["whole_cell"]
    },
    {
      "experiment_id": "10.1073/pnas.2213271120_chitosan_addition_mit9313_metabolomics",
      "experiment_name": "MIT9313 chitosan addition — intracellular metabolomics",
      "publication_doi": "10.1073/pnas.2213271120",
      "authors": [
        "Giovanna Capovilla",
        "Rogier Braakman",
        "Gregory P. Fournier",
        "Thomas Hackl",
        "Julia Schwartzman",
        ...
      ],
      "organism_name": "Prochlorococcus MIT9313",
      "treatment_type": ["carbon"],
      "background_factors": ["axenic", "light"],
      "coculture_partner": null,
      "omics_type": "METABOLOMICS",
      "is_time_course": false,
      "table_scope": null,
      "table_scope_detail": "",
      "gene_count": 0,
      "distinct_gene_count": 0,
      "genes_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 0},
      "timepoints": null,
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "compartment": "whole_cell",
      "metabolite_count": 16,
      "metabolite_assay_count": 1,
      "metabolite_compartments": ["whole_cell"]
    }
  ]
}
```

### Example 10: gene_count vs distinct_gene_count for time-course experiments

```
Each result row carries both `gene_count` (cumulative row count
across timepoints — equals `sum(time_point_totals)`) and
`distinct_gene_count` (unique genes measured, independent of
timepoint count). For non-time-course experiments they're equal.

For a time-course experiment measuring 1697 genes at 6 timepoints:
  gene_count             = 10182   (= 6 × 1697)
  distinct_gene_count    =  1697

Use `distinct_gene_count` for detection-power / pathway-background
sizing. Per-TP detail lives in `timepoints[].gene_count`.
```

## Chaining patterns

```
list_organisms → list_experiments
list_publications → list_experiments
list_filter_values → list_experiments
list_experiments(search_text=..., verbose=True) → classify → list_experiments(experiment_ids=[...]) for the picked subset
list_experiments → differential_expression_by_gene
list_experiments → list_clustering_analyses(experiment_ids=[...])
list_experiments(compartment=...) → use derived_metric_value_kinds per result row to route to genes_by_{boolean,numeric,categorical}_metric
list_filter_values(filter_type='metric_type') → list_experiments(search_text='<metric_type>') to find experiments with that metric
list_experiments (per-row `metabolite_count > 0`) → list_metabolite_assays(experiment_ids=[...]) to inspect the experiment's MetaboliteAssay nodes (numeric vs boolean, compartment, detection-status rollup).
```

## Common mistakes

- If a result row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric. Empty derived_metric_value_kinds means no DM evidence on this experiment.

- Default is detail (summary=false) — use summary=true to see only breakdowns. When summary=true, verbose and limit have no effect.

- gene_count is total genes with expression data, not total significant genes — use genes_by_status for the breakdown.

- timepoints is omitted for non-time-course experiments, not an empty list.

- `table_scope` is sparse: absent on an experiment means the experiment has no differential-expression table at all (a characterization or metabolomics-only experiment), never an empty string. `by_table_scope` has no '' bucket; `table_scope=[...]` filters simply never match those experiments.

- treatment_type / background_factors / growth_phase values are LIVE vocabularies read from the KG, not enums: an unknown value (e.g. 'nitrogen_stress' instead of 'nitrogen') returns 0 rows, never an error. Check list_filter_values(filter_type='growth_phase') or a summary=True call's by_treatment_type / by_background_factors rollup before filtering. Current treatment values are short nouns (nitrogen, light, carbon, iron, darkness, phosphorus, salt, viral, coculture, diel, ...); background_factors are light, axenic, coculture, darkness, diel, viral, chemical.

- `treatment_type` is dense and never empty on Experiment — a non-empty list is the marker of a real experiment. A characterization study with no perturbation names what was measured: `rna_decay` (mRNA half-life survey), `tss_mapping` (promoter / TSS survey), `growth_phase` (growth-curve profiling), `compartment` (vesicle vs whole-cell fractionation). Filter on those values to list characterization experiments; do not look for `treatment_type == []`. (`genomic_analysis` exists only on ClusteringAnalysis nodes, not on experiments.) `background_factors` is likewise dense and never empty on Experiment (every experiment has a held-constant context); it is `[]` only on the sequence-only genomic-island clustering analyses.

- `growth_phase` values (on `timepoints[].growth_phase` and the `growth_phases` filter) are an OPEN vocabulary — new papers add new labels. Enumerate live from the data rather than assuming a fixed set.

- For time-course experiments, top-level `gene_count` is the cumulative row count across timepoints (= `sum(time_point_totals)`). A 6-TP experiment with 1697 genes/TP has `gene_count=10182`. Use `distinct_gene_count` for detection-power or pathway-background reasoning — that's the unique-genes count regardless of timepoint. Per-TP detail lives in `timepoints[].gene_count`.

- `authors` is on every result row — no need to join with list_publications when you only need author attribution. list_publications is still the right call for richer publication metadata (abstract, journal, year).

- `organism=` filters the profiled organism only (word-based, case-insensitive match on preferred_name + name_synonyms — 'MED4' works). It does NOT match coculture partners — for partner-side filtering use `coculture_partner=`. The two filters AND-compose. A genus word alone ('Prochlorococcus') matches every strain of the genus — fine here, but the single-organism expression tools raise on it.

- metabolite_count > 0 indicates a metabolomics-paired experiment. Drill into MetaboliteAssay nodes via list_metabolite_assays(experiment_ids=[...]).

```mistake
list_experiments(omics_type='RNASEQ')  # bare string
```

```correction
list_experiments(omics_type=['RNASEQ'])  # treatment_type / background_factors / omics_type / table_scope / publication_doi / experiment_ids are lists; a bare string is iterated character by character and silently matches 0 rows
```

```mistake
list_experiments(publication='Biller 2018')
```

```correction
list_publications(search_text='Biller') then list_experiments(publication_doi=['10.1038/...'])
```

```mistake
result['results'][0]['time_point_growth_phases']
```

```correction
[tp['growth_phase'] for tp in result['results'][0]['timepoints']]
```

- DataFrame conversion: `to_dataframe(result)` auto-dispatches and returns one row per experiment × timepoint (with `timepoints` unwound and `genes_by_status` inlined at both experiment + timepoint level). See `docs://guide/python_api`.

## Package import equivalent

```python
from multiomics_explorer import list_experiments

result = list_experiments()
# returns dict with keys: total_entries, total_matching, returned, offset, truncated, by_organism, by_treatment_type, by_background_factors, by_omics_type, by_publication, by_table_scope, by_cluster_type, by_growth_phase, by_value_kind, by_metric_type, by_compartment, time_course_count, score_max, score_median, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
