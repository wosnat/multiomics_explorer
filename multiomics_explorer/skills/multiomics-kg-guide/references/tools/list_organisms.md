# list_organisms

## What it does

Every organism with taxonomy and per-organism capability rollups — gene, publication, experiment, DM, chemistry, metabolomics and annotation counts.

Use to pick an organism or check what data it carries before scoping another tool; for gene lookup use `resolve_gene`.
Filters: organism_names, compartment.
Returns: by_organism_type, top_metabolic_capability, top_annotation_capability, by_measurement_capability, not_found; one row = one OrganismTaxon.
docs://tools/list_organisms; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism_names | list[string] \| None | None | Filter by organism: case-insensitive word match on preferred_name and name_synonyms, like every other tool's organism param ('MED4', 'Prochlorococcus MED4'; the synonym 'Meiothermus taiwanensis' resolves to 'Meiothermus ruber'); a genus word like 'Alteromonas' matches every strain. Unknown names are reported in not_found rather than raising. Note: two OrganismTaxon nodes share preferred_name 'Meiothermus ruber' (the genome strain + a gene-less treatment taxon) — join counts by Gene_belongs_to_organism, never by name. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Example

### Browse all organisms

```python
list_organisms()
```

## Response sketch

```expected-keys
total_entries, total_matching, by_cluster_type, by_organism_type, by_value_kind, by_metric_type, by_compartment, top_metabolic_capability, top_annotation_capability, by_measurement_capability, returned, offset, truncated, not_found, warnings, results
```

Result row: `organism_name, organism_type, genus, species, strain, clade, ncbi_taxon_id, gene_count, publication_count, experiment_count, treatment_types, background_factors, …`

## Common mistakes

- If a result row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric. Empty derived_metric_value_kinds means no DM evidence on this organism.

- gene_count and publication_count are counts of data in the KG, not biological totals.

- Organisms with gene_count=0 are parent/umbrella taxonomy nodes (e.g. genus-level 'Alteromonas').

## Chaining patterns

- list_organisms → genes_by_function
- list_organisms → list_publications
- list_organisms → resolve_gene
- list_organisms → genes_by_ontology
- list_organisms → list_clustering_analyses(organism=...)
- list_organisms(compartment=...) → use derived_metric_value_kinds per result row to route to genes_by_{boolean,numeric,categorical}_metric
- list_organisms (per-row catalyzed_metabolite_count > 0) → list_metabolites(organism_names=[organism_name]) for chemistry drill-down
- list_organisms(summary=True) → top_annotation_capability → genes_by_ontology(ontology='merops', organism=..., call_class=['peptidase']) for the peptidase genes behind peptidase_gene_count
- list_organisms → per-row interpro_gene_count / ncbifam_gene_count → ontology_landscape(organism=..., ontology=['interpro', 'ncbifam']) before enrichment on a domain ontology
- list_organisms (per-row measured_metabolite_count > 0) → list_metabolite_assays(organism=...) for the metabolomics measurement layer
- list_organisms → list_experiments(organism=...) to scope experiments to the chosen organism

Full reference (all examples, full response format, verbose fields): `docs://tools/list_organisms/full`
