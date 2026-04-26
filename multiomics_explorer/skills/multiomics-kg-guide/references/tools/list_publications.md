# list_publications

## What it does

List publications with expression data in the knowledge graph.

Returns publication metadata and experiment summaries. Use this as
an entry point to discover what studies exist, then drill into
specific experiments with list_experiments or genes with genes_by_function.

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
| verbose | bool | False | Include abstract and description. Default compact for routing. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_organism, by_treatment_type, by_background_factors, by_omics_type, by_cluster_type, returned, offset, truncated, not_found, results
```

- **total_entries** (int): Total publications in KG (unfiltered)
- **total_matching** (int): Publications matching filters
- **by_organism** (list[PubOrganismBreakdown]): Publication counts per organism, sorted by count descending
- **by_treatment_type** (list[PubTreatmentTypeBreakdown]): Publication counts per treatment type, sorted by count descending
- **by_background_factors** (list[PubBackgroundFactorBreakdown]): Publication counts per background factor, sorted by count descending
- **by_omics_type** (list[PubOmicsTypeBreakdown]): Publication counts per omics platform, sorted by count descending
- **by_cluster_type** (list[PubClusterTypeBreakdown]): Publication counts per cluster type, sorted by count descending
- **returned** (int): Publications in this response
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if total_matching > returned
- **not_found** (list[string]): Input publication_dois that did not match any Publication node (empty unless publication_dois was provided)

### Per-result fields

| Field | Type | Description |
|---|---|---|
| doi | string |  |
| title | string |  |
| authors | list[string] |  |
| year | int |  |
| journal | string \| None (optional) |  |
| study_type | string \| None (optional) |  |
| organisms | list[string] (optional) | Organisms studied in this publication |
| experiment_count | int (optional) | Number of experiments in KG from this publication |
| treatment_types | list[string] (optional) | Experiment treatment types (e.g. coculture, nitrogen_stress) |
| background_factors | list[string] (optional) | Distinct background factors across experiments (e.g. ['axenic', 'diel_cycle']) |
| omics_types | list[string] (optional) | Omics data types (e.g. RNASEQ, PROTEOMICS) |
| clustering_analysis_count | int (optional) | Number of clustering analyses from this publication (e.g. 4) |
| cluster_types | list[string] (optional) | Distinct cluster types (e.g. ['condition_comparison']) |
| growth_phases | list[string] (optional) | Distinct growth phases across experiments. Physiological state of the culture at sampling — timepoint-level, not gene-specific. |
| score | float \| None (optional) | Lucene relevance score (only with search_text) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| abstract | string \| None (optional) | Publication abstract (only with verbose=True) |
| description | string \| None (optional) | Curated study description (only with verbose=True) |
| cluster_count | int \| None (optional) | Total gene clusters across analyses (only with verbose=True, e.g. 20) |

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

## Chaining patterns

```
list_publications → list_experiments → differential_expression_by_gene
list_publications → genes_by_function
list_publications → list_clustering_analyses(publication_doi=[...])
list_publications(search_text=..., verbose=True) → classify → list_publications(publication_dois=[...]) for the picked subset
```

## Common mistakes

- treatment_type is a string filter, not a list — use treatment_type='coculture' not treatment_type=['coculture']

- Use the dedicated author param for author filtering (e.g. author='Biller'), not search_text — search_text searches title, abstract, and description only

- experiment_count is per-publication — a publication with experiment_count=10 may span multiple organisms and treatment types

```mistake
list_experiments(publication='Biller 2018')
```

```correction
list_publications(search_text='Biller') then list_experiments(publication_doi=['10.1038/...'])
```

- growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — NOT a gene-specific property

## Package import equivalent

```python
from multiomics_explorer import list_publications

result = list_publications()
# returns dict with keys: total_entries, total_matching, by_organism, by_treatment_type, by_background_factors, by_omics_type, by_cluster_type, offset, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
