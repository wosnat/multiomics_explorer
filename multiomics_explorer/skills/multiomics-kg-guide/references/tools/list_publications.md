# list_publications

## What it does

Publications with experiment, DM, metabolomics and literature-index rollups.

Use as the study-level discovery entry point; for per-experiment detail use `list_experiments(publication_dois=[...])`, for the entities a paper names `discussed_by_publication`.
Filters: organism, search_text, author, publication_dois, compartment, plus the condition filters.
Returns: by_organism, by_treatment_type, by_omics_type, by_compartment, by_discusses_coverage, not_found; one row = one publication.
docs://tools/list_publications; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| search_text | string \| None | None | Free-text search on title, abstract, and description (Lucene syntax). E.g. 'nitrogen', 'co-culture AND phage'. |
| author | string \| None | None | Filter by author name (case-insensitive). E.g. 'Sher', 'Chisholm'. |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Browse all studies

```python
list_publications()
```

## Response sketch

```expected-keys
total_entries, total_matching, by_organism, by_treatment_type, by_background_factors, by_omics_type, by_cluster_type, by_value_kind, by_metric_type, by_compartment, by_discusses_coverage, returned, offset, truncated, not_found, warnings, results
```

Result row: `doi, title, authors, year, journal, study_type, organisms, experiment_count, treatment_types, background_factors, omics_types, clustering_analysis_count, …`

## Common mistakes

- If a result row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric. Empty derived_metric_value_kinds means no DM evidence on this publication.

- treatment_type / background_factors / growth_phase values are LIVE vocabularies read from the KG, not enums: an unknown value (e.g. 'nitrogen_stress' instead of 'nitrogen') returns 0 rows, never an error. Check list_filter_values(filter_type='growth_phase') or a summary=True call's by_treatment_type / by_background_factors rollup before filtering. Current treatment values are short nouns (nitrogen, light, carbon, iron, darkness, phosphorus, salt, viral, coculture, diel, ...); background_factors are light, axenic, coculture, darkness, diel, viral, chemical. On this tool the rollups come from an unfiltered list_publications() call.

- `organism=` is a word-based, case-insensitive match on preferred_name + name_synonyms — 'MED4' works. Two OrganismTaxon nodes share the name 'Meiothermus ruber' (genome strain + treatment taxon), so organism='Meiothermus ruber' counts papers tied to either.

## Chaining patterns

- list_publications → list_experiments → differential_expression_by_gene
- list_publications → genes_by_function
- list_publications → list_clustering_analyses(publication_dois=[...])
- list_publications(search_text=..., verbose=True) → classify → list_publications(publication_dois=[...]) for the picked subset
- list_publications(compartment=...) → use derived_metric_value_kinds per result row to route to genes_by_{boolean,numeric,categorical}_metric
- list_filter_values(filter_type='metric_type') → list_publications(search_text='<metric_type>') to find publications with that metric
- list_publications (per-row `metabolite_count > 0`) → list_metabolite_assays(publication_dois=[...]) to inspect the paper's MetaboliteAssay nodes (numeric vs boolean, compartment, detection-status rollup).
- list_publications (per-row `discussed_gene_count` or `discussed_pathway_count` > 0) → discussed_by_publication(publication_dois=[...]) to list the genes + KEGG pathways the paper names in prose.
- list_publications → list_derived_metrics(publication_dois=[doi]) for the paper's non-DE, column-level evidence

Full reference (all examples, full response format, verbose fields): `docs://tools/list_publications/full`
