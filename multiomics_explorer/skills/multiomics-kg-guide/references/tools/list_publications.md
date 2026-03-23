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
| search_text | string \| None | None | Free-text search on title, abstract, and description (Lucene syntax). E.g. 'nitrogen', 'co-culture AND phage'. |
| author | string \| None | None | Filter by author name (case-insensitive). E.g. 'Sher', 'Chisholm'. |
| verbose | bool | False | Include abstract and description. Default compact for routing. |
| limit | int | 5 | Max results. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_organism, by_treatment_type, by_omics_type, returned, truncated, results
```

- **total_entries** (int): Total publications in KG (unfiltered)
- **total_matching** (int): Publications matching filters
- **by_organism** (list[PubOrganismBreakdown]): Publication counts per organism, sorted by count descending
- **by_treatment_type** (list[PubTreatmentTypeBreakdown]): Publication counts per treatment type, sorted by count descending
- **by_omics_type** (list[PubOmicsTypeBreakdown]): Publication counts per omics platform, sorted by count descending
- **returned** (int): Publications in this response
- **truncated** (bool): True if total_matching > returned

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
| omics_types | list[string] (optional) | Omics data types (e.g. RNASEQ, PROTEOMICS) |
| score | float \| None (optional) | Lucene relevance score (only with search_text) |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| abstract | string \| None (optional) | Publication abstract (only with verbose=True) |
| description | string \| None (optional) | Curated study description (only with verbose=True) |

## Few-shot examples

### Example 1: Browse all studies

```example-call
list_publications()
```

```example-response
{
  "total_entries": 21, "total_matching": 21,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "publication_count": 11}, ...],
  "by_treatment_type": [{"treatment_type": "coculture", "publication_count": 5}, ...],
  "by_omics_type": [{"omics_type": "RNASEQ", "publication_count": 12}, ...],
  "returned": 5, "truncated": true,
  "results": [
    {"doi": "10.1101/2025.11.24.690089", "title": "Transcriptomic and Proteomic...", "year": 2025, "experiment_count": 10, ...},
    {"doi": "10.1038/ismej.2016.70", "title": "Transcriptional response of Prochlorococcus...", "year": 2016, "experiment_count": 5, ...}
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

Step 2: list_experiments(doi=result["doi"])
        → drill into experiments from a specific paper

Step 3: genes_by_function(search_text="photosystem", organism="MED4")
        → find genes of interest
```

## Chaining patterns

```
list_publications → list_experiments → query_expression
list_publications → genes_by_function
```

## Package import equivalent

```python
from multiomics_explorer import list_publications

result = list_publications()
# returns dict with keys: total_entries, total_matching, by_organism, by_treatment_type, by_omics_type, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
