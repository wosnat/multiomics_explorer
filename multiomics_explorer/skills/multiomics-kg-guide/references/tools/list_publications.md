# list_publications

## What it does

List publications with experiment summaries, DM rollups, and metabolomics rollups. Use as the discovery entry point for studies.

Routing: drill via `list_experiments(publication_doi=[doi])` for per-experiment detail; `list_clustering_analyses(publication_doi=[doi])` for clustering; `list_derived_metrics(publication_doi=[doi])` for non-DE evidence; `list_metabolite_assays(publication_doi=[doi])` when `metabolite_count > 0`. Per-row `derived_metric_value_kinds` routes to `genes_by_{numeric,boolean,categorical}_metric`.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string \| None | None | Filter by organism name (case-insensitive). E.g. 'MED4', 'HOT1A3'. |
| treatment_type | string \| None | None | Filter by experiment treatment type. Use list_filter_values for valid values. |
| background_factors | string \| None | None | Filter by background factor (case-insensitive exact match). E.g. 'axenic'. |
| growth_phases | string \| None | None | Filter by growth phase (case-insensitive). E.g. 'exponential', 'nutrient_limited'. |
| search_text | string \| None | None | Free-text search on title, abstract, and description (Lucene syntax). E.g. 'nitrogen', 'co-culture AND phage'. |
| author | string \| None | None | Filter by author name (case-insensitive). E.g. 'Sher', 'Chisholm'. |
| publication_dois | list[string] \| None | None | Restrict to specific publications by DOI (case-insensitive). Combines with other filters via AND. `not_found` in the response lists any provided DOIs that did not match. Mirrors the filter shape on sibling list_* tools (list_experiments.experiment_ids). |
| compartment | string \| None | None | Filter to publications with at least one experiment in this wet-lab compartment (e.g. 'vesicle', 'whole_cell'). Use list_filter_values(filter_type='compartment') to enumerate valid values. |
| verbose | bool | False | Include abstract and description. Default compact for routing. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_organism, by_treatment_type, by_background_factors, by_omics_type, by_cluster_type, by_value_kind, by_metric_type, by_compartment, by_discusses_coverage, returned, offset, truncated, not_found, results
```

- **total_entries** (int): Total publications in KG (unfiltered).
- **total_matching** (int): Publications matching filters.
- **by_organism** (list[PubOrganismBreakdown]): Publication counts per organism, sorted desc.
- **by_treatment_type** (list[PubTreatmentTypeBreakdown]): Publication counts per treatment type, sorted desc.
- **by_background_factors** (list[PubBackgroundFactorBreakdown]): Publication counts per background factor, sorted desc.
- **by_omics_type** (list[PubOmicsTypeBreakdown]): Publication counts per omics platform, sorted desc.
- **by_cluster_type** (list[PubClusterTypeBreakdown]): Publication counts per cluster type, sorted desc.
- **by_value_kind** (list[PubValueKindBreakdown]): DerivedMetric value kind frequency rollup across matched publications.
- **by_metric_type** (list[PubMetricTypeBreakdown]): DerivedMetric type frequency rollup across matched publications.
- **by_compartment** (list[PubCompartmentBreakdown]): Wet-lab compartment frequency rollup across matched publications.
- **by_discusses_coverage** (PubDiscussesCoverageBreakdown): Binary split {has_discusses, no_discusses} of matched publications by whether they carry a narrative 'discusses' literature index (40 vs 3 in the current KG).
- **returned** (int): Publications in this response.
- **offset** (int): Offset into full result set.
- **truncated** (bool): True if total_matching > returned.
- **not_found** (list[string]): Input publication_dois that did not match any Publication node (empty unless publication_dois was provided).

### Per-result fields

| Field | Type | Description |
|---|---|---|
| doi | string | Publication DOI (e.g. '10.1038/s41396-022-01202-1'). |
| title | string | Publication title. |
| authors | list[string] | Author list (free-text, semicolon- or comma-delimited). |
| year | int | Publication year (e.g. 2022). |
| journal | string \| None (optional) | Journal name (e.g. 'ISME'). |
| study_type | string \| None (optional) | Study type tag (e.g. 'metabolomics', 'transcriptomics'). |
| organisms | list[string] (optional) | Organisms studied in this publication. |
| experiment_count | int (optional) | Number of experiments in KG from this publication. |
| treatment_types | list[string] (optional) | Experiment treatment types (e.g. coculture, nitrogen_stress). |
| background_factors | list[string] (optional) | Distinct background factors across experiments (e.g. ['axenic', 'diel_cycle']). |
| omics_types | list[string] (optional) | Omics data types (e.g. RNASEQ, PROTEOMICS). |
| clustering_analysis_count | int (optional) | Number of clustering analyses from this publication. |
| cluster_types | list[string] (optional) | Distinct cluster types (e.g. ['condition_comparison']). |
| growth_phases | list[string] (optional) | Distinct growth phases across experiments. Timepoint-level condition, not gene-specific. |
| derived_metric_count | int (optional) | Number of DerivedMetric nodes from this publication. |
| derived_metric_value_kinds | list[string] (optional) | Value kinds of DerivedMetrics in this publication (subset of {numeric, boolean, categorical}). Use to route to genes_by_{kind}_metric. |
| compartments | list[string] (optional) | Wet-lab compartments measured in this publication (e.g. ['whole_cell', 'vesicle']). |
| metabolite_count | int (optional) | Distinct metabolites measured in this publication (precomputed Publication.metabolite_count). Non-zero on metabolomics-bearing papers. When > 0, drill via list_metabolite_assays(publication_doi=[...]) to inspect the paper's MetaboliteAssay nodes. |
| metabolite_assay_count | int (optional) | Distinct MetaboliteAssay edges anchored to this publication (precomputed). Diverges from metabolite_count when the same metabolite is measured in multiple compartments per paper. |
| metabolite_compartments | list[string] (optional) | Wet-lab compartments measured for metabolomics in this publication (e.g. ['whole_cell', 'extracellular']). Populated only when metabolite_assay_count > 0; [] otherwise. |
| discussed_gene_count | int (optional) | Distinct genes this publication discusses in prose (precomputed Publication.discussed_gene_count). Recall-biased narrative index, NOT DE-table expression. When > 0, drill via discussed_by_publication(publication_dois=[doi]). |
| discussed_pathway_count | int (optional) | Distinct KEGG pathways this publication discusses in prose (precomputed Publication.discussed_pathway_count). When > 0, drill via discussed_by_publication(publication_dois=[doi], entity_kind='kegg_pathway'). |
| score | float \| None (optional) | Lucene relevance score (only with search_text). |
| derived_metric_gene_count | int \| None (optional) | Total genes annotated by DerivedMetrics in this publication (verbose-only). |
| derived_metric_types | list[string] \| None (optional) | Distinct DerivedMetric types in this publication (verbose-only). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| abstract | string \| None (optional) | Publication abstract (verbose-only). |
| description | string \| None (optional) | Curated study description (verbose-only). |
| cluster_count | int \| None (optional) | Total gene clusters across analyses (verbose-only). |

## Few-shot examples

### Example 1: Browse all studies

```example-call
list_publications()
```

```example-response
{
  "total_entries": 21, "total_matching": 21,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 11}, ...],
  "by_treatment_type": [{"treatment_type": "coculture", "count": 5}, ...],
  "by_omics_type": [{"omics_type": "RNASEQ", "count": 12}, ...],
  "by_cluster_type": [{"cluster_type": "condition_comparison", "count": 4}, ...],
  "returned": 5, "truncated": true, "offset": 0,
  "results": [
    {"doi": "10.1101/2025.11.24.690089", "title": "Transcriptomic and Proteomic...", "year": 2025, "experiment_count": 10, "clustering_analysis_count": 0, "cluster_types": [], ...},
    {"doi": "10.1038/ismej.2016.70", "title": "Transcriptional response of Prochlorococcus...", "year": 2016, "experiment_count": 5, "clustering_analysis_count": 2, "cluster_types": ["condition_comparison"], ...}
  ]
}
```

### Example 2: Find coculture studies

```example-call
list_publications(treatment_type="coculture")
```

### Example 3: Chaining to experiments

```
Step 1: list_publications(organism="MED4")
        → find papers studying MED4

Step 2: list_experiments(publication_doi=[result["doi"]])
        → drill into experiments from a specific paper

Step 3: genes_by_function(search_text="photosystem", organism="MED4")
        → find genes of interest
```

### Example 4: Fetch metadata for a known DOI list

```example-call
list_publications(publication_dois=["10.1038/ismej.2016.70", "10.1101/2025.11.24.690089"], verbose=True)
```

### Example 5: Find vesicle-fraction publications with DM evidence

```example-call
list_publications(compartment="vesicle")
```

```example-response
{"total_matching": 2, "by_value_kind": [{"value_kind": "numeric", "count": 2}], "by_compartment": [{"compartment": "vesicle", "count": 2}], "returned": 2, "truncated": false, "offset": 0,
 "results": [
   {"doi": "10.1111/1462-2920.15834", "title": "Prochlorococcus extracellular vesicles: molecular composition and adsorption to diverse microbes", "year": 2022, "derived_metric_count": 6, "derived_metric_value_kinds": ["numeric"], "compartments": ["vesicle"]}
 ]}
```

### Example 6: Find metabolomics-bearing publications

```example-call
list_publications(search_text="metabolite")
```

```example-response
{"total_matching": 2, "returned": 2, "truncated": false, "offset": 0,
 "results": [
   {"doi": "10.1038/s41396-023-01394-0", "title": "Capovilla 2023 metabolomics study", "year": 2023, "metabolite_count": 92, "metabolite_assay_count": 184, "metabolite_compartments": ["extracellular", "whole_cell"]},
   {"doi": "10.1038/s41396-023-01415-y", "title": "Kujawinski 2023 metabolomics study", "year": 2023, "metabolite_count": 15, "metabolite_assay_count": 15, "metabolite_compartments": ["whole_cell"]}
 ]}
```

### Example 7: Find publications with a narrative literature index

```example-call
list_publications()
```

```example-response
# Per-row discussed_gene_count / discussed_pathway_count expose the
# paper's prose literature index — the genes + KEGG pathways it names
# in text. The envelope by_discusses_coverage splits the corpus into
# has_discusses (40) vs no_discusses (3). Drill into a paper's named
# entities via discussed_by_publication.
{"total_matching": 21,
 "by_discusses_coverage": {"has_discusses": 40, "no_discusses": 3},
 "returned": 5, "truncated": true, "offset": 0,
 "results": [
   {"doi": "10.1038/ismej.2016.70", "title": "Transcriptional response of Prochlorococcus...", "year": 2016, "discussed_gene_count": 29, "discussed_pathway_count": 8}
 ]}
```

## Chaining patterns

```
list_publications → list_experiments → differential_expression_by_gene
list_publications → genes_by_function
list_publications → list_clustering_analyses(publication_doi=[...])
list_publications(search_text=..., verbose=True) → classify → list_publications(publication_dois=[...]) for the picked subset
list_publications(compartment=...) → use derived_metric_value_kinds per result row to route to genes_by_{boolean,numeric,categorical}_metric
list_filter_values(filter_type='metric_type') → list_publications(search_text='<metric_type>') to find publications with that metric
list_publications (per-row `metabolite_count > 0`) → list_metabolite_assays(publication_doi=[...]) to inspect the paper's MetaboliteAssay nodes (numeric vs boolean, compartment, detection-status rollup).
list_publications (per-row `discussed_gene_count` or `discussed_pathway_count` > 0) → discussed_by_publication(publication_dois=[...]) to list the genes + KEGG pathways the paper names in prose.
```

## Common mistakes

- If a result row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric. Empty derived_metric_value_kinds means no DM evidence on this publication.

- treatment_type is a string filter, not a list — use treatment_type='coculture' not treatment_type=['coculture'].

- Use the dedicated author param for author filtering (e.g. author='Biller'), not search_text — search_text searches title, abstract, and description only.

- experiment_count is per-publication — a publication with experiment_count=10 may span multiple organisms and treatment types.

- metabolite_count > 0 indicates a metabolomics-bearing publication. Drill into MetaboliteAssay nodes via list_metabolite_assays(publication_doi=[...]); inspect compartments via metabolite_compartments per row.

- discussed_gene_count / discussed_pathway_count are the paper's prose literature index — the genes + KEGG pathways it names in text (recall-biased, NOT exhaustive, NOT DE-table expression). 0 on both means no narrative index (3 such publications). Drill into the named entities via discussed_by_publication(publication_dois=[...]).

```mistake
list_experiments(publication='Biller 2018')
```

```correction
list_publications(search_text='Biller') then list_experiments(publication_doi=['10.1038/...'])
```

## Package import equivalent

```python
from multiomics_explorer import list_publications

result = list_publications()
# returns dict with keys: total_entries, total_matching, by_organism, by_treatment_type, by_background_factors, by_omics_type, by_cluster_type, by_value_kind, by_metric_type, by_compartment, by_discusses_coverage, offset, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
