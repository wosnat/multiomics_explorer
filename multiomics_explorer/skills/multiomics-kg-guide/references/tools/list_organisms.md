# list_organisms

## What it does

Every organism with taxonomy and per-organism capability rollups — gene, publication, experiment (profiled and coculture-partner), DM, chemistry, metabolomics and annotation counts.

Use to pick an organism or check what data it carries before scoping another tool; for gene lookup use `resolve_gene`.
Filters: organism_names, compartment.
Returns: by_organism_type, top_metabolic_capability, top_annotation_capability, by_measurement_capability, not_found; one row = one OrganismTaxon.
docs://tools/list_organisms; summary=True caps the same rollups at 10 (smaller than the default call).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism_names | list[string] \| None | None | Filter by organism: case-insensitive word match on preferred_name and name_synonyms, like every other tool's organism param ('MED4', 'Prochlorococcus MED4'; the synonym 'Meiothermus taiwanensis' resolves to 'Meiothermus ruber'); a genus word like 'Alteromonas' matches every strain. Unknown names are reported in not_found rather than raising. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's full page, docs://tools/{tool}/full. |
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

Result row: `organism_name, organism_type, genus, species, strain, clade, ncbi_taxon_id, gene_count, publication_count, experiment_count, partner_experiment_count, treatment_types, …`

## Common mistakes

- `experiment_count` counts only experiments that profile this organism. experiment_count=0 on a treatment taxon (e.g. a phage or a coculture helper) does not mean it is absent from the experimental data — experiments where it is the coculture partner (either `coculture_role`) are counted in `partner_experiment_count` and listed via list_experiments(coculture_partner=organism_name). The two counts are disjoint; a profiled strain can carry both.

- `catalyzed_metabolite_count` counts catalysis capability only — distinct metabolites reachable through Gene → Reaction → Metabolite. Transport reach is the separate `transported_metabolite_count` (distinct metabolites curated on the TC systems the organism's genes point at directly, `tcdb_gate='direct'`; family-level calls and weak hits do not count). Measurement-side coverage is `measured_metabolite_count`. catalyzed_metabolite_count=0 means no catalysis path in this organism, not that chemistry is absent from the KG.

- `go_transport_metabolite_count` counts metabolites reached through direct GO transport terms (chemical roles and is_a-inherited targets excluded). It is a separate route from `transported_metabolite_count` (TCDB); the two overlap and do not add up to a total transport reach.

## Chaining patterns

- list_organisms → genes_by_function
- list_organisms → list_publications
- list_organisms → resolve_gene
- list_organisms → genes_by_ontology
- list_organisms → list_clustering_analyses(organism=...)
- list_organisms(compartment=...) → use derived_metric_value_kinds per result row to route to genes_by_{boolean,numeric,categorical}_metric (docs://analysis/derived_metrics)
- list_organisms (per-row catalyzed_metabolite_count > 0) → list_metabolites(organism_names=[organism_name]) for chemistry drill-down
- list_organisms(summary=True) → top_annotation_capability → genes_by_ontology(ontology='merops', organism=..., call_class=['peptidase']) for the peptidase genes behind peptidase_gene_count
- list_organisms → per-row interpro_gene_count / ncbifam_gene_count → ontology_landscape(organism=..., ontology=['interpro', 'ncbifam']) before enrichment on a domain ontology
- list_organisms (per-row measured_metabolite_count > 0) → list_metabolite_assays(organism=...) for the metabolomics measurement layer
- list_organisms → list_experiments(organism=...) to scope experiments to the chosen organism
- list_organisms (per-row partner_experiment_count > 0) → list_experiments(coculture_partner=organism_name) for the experiments in which this organism is the coculture partner

Full reference (all examples, full response format, verbose fields): `docs://tools/list_organisms/full`
