# list_filter_values

## What it does

Valid values for one closed vocabulary, with counts where the KG pivots them and descriptions where it stores them.

Use whenever a filter takes a controlled value you would otherwise guess; for organism names use `list_organisms`, for ontology terms `search_ontology`.
Filters: filter_type, ontology.
Returns: filter_type, description, total_entries, warnings; one row = (value, count, description, applies_to).
docs://tools/list_filter_values.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| filter_type | string ('gene_category', 'brite_tree', 'growth_phase', 'metric_type', 'value_kind', 'compartment', 'omics_type', 'evidence_source', 'evidence', 'sources', 'call_class', 'interpro_type', 'ncbifam_family_type', 'merops_catalytic_type', 'merops_family_class', 'best_hit_kind', 'pfam_support', 'attachment_depth', 'trust_axes', 'link_kinds', 'cluster_type', 'treatment_type', 'background_factors', 'table_scope', 'detection_status', 'expression_status') | gene_category | Which filter to enumerate — gene/expression (incl. cluster_type, expression_status), DerivedMetric (incl. table_scope), chemistry (incl. detection_status), experiment (treatment_type, background_factors), or a trust vocabulary. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') \| None | None | Scope a trust filter_type (e.g. 'trust_axes') to one ontology key. Ignored on non-trust filter types. |

## Example

### List gene categories

```python
list_filter_values(filter_type="gene_category")
```

## Response sketch

```expected-keys
filter_type, description, total_entries, returned, truncated, warnings, results
```

Result row: `value, count, tree_code, source, applies_to, description`

## Common mistakes

- Use filter_type='metric_type' to discover DerivedMetric tags before passing them to genes_by_{kind}_metric or list_derived_metrics. filter_type='value_kind' enumerates {numeric, boolean, categorical}. filter_type='compartment' enumerates wet-lab fractions (whole_cell, vesicle, exoproteome, ...).

- count is summed across all organisms — a category with count=770 may cover genes in 10+ organisms

- `count` is None on every vocabulary-sourced row: all the trust filter types (`evidence`, `sources`, `call_class`, `interpro_type`, ...) AND `cluster_type`. Only the pivoted / precomputed types (`gene_category`, `brite_tree`, `growth_phase`, `metric_type`, `value_kind`, `compartment`, `omics_type`, `evidence_source`) carry a count. Read `applies_to` / `description` on the count-less rows instead.

## Chaining patterns

- list_filter_values → genes_by_function(gene_categories=...)
- list_filter_values(filter_type='cluster_type') → list_clustering_analyses(cluster_type=...) / gene_clusters_by_gene(cluster_type=...)
- list_filter_values('brite_tree') → ontology_landscape(tree=...) → pathway_enrichment(tree=...)
- list_filter_values(filter_type='metric_type') → list_derived_metrics(metric_types=[...]) → genes_by_{kind}_metric
- list_filter_values(filter_type='compartment') → list_experiments(compartment=...) / list_organisms(compartment=...) / list_publications(compartment=...)
- list_filter_values(filter_type='evidence_source') → list_metabolites(evidence_sources=[...]) for slicing by evidence type.
- list_filter_values(filter_type='omics_type') → list_experiments(omics_type=...) for filtering by experiment type.
- list_filter_values(filter_type='trust_axes', ontology=...) → genes_by_ontology / gene_ontology_terms / pathway_enrichment / cluster_enrichment(sources=..., evidence=..., max_tier=..., min_evidence_score=..., call_class=...) — see docs://analysis/annotation_evidence for the full per-ontology profile.
- list_filter_values(filter_type='interpro_type') → genes_by_ontology(ontology='interpro', ...) / search_ontology(ontology='interpro', interpro_type=...) / pathway_enrichment(ontology='interpro', interpro_type=...).
- list_filter_values(filter_type='call_class') → genes_by_ontology(ontology='merops', call_class=[...]).
- list_filter_values(filter_type='treatment_type') → list_experiments(treatment_type=[...]) / list_derived_metrics(treatment_type=[...]) / list_metabolite_assays(treatment_type=[...]) / list_clustering_analyses(treatment_type=[...]); same routing for filter_type='background_factors'.
- list_filter_values(filter_type='growth_phase') → list_experiments(growth_phases=[...]) / list_derived_metrics(growth_phases=[...]) / differential_expression_by_gene(growth_phases=[...])
- list_filter_values(filter_type='table_scope') → list_experiments(table_scope=[...]) to keep only experiments whose DE table reports every detected gene
- list_filter_values(filter_type='value_kind') → list_derived_metrics(value_kind=...) / list_metabolite_assays(value_kind=...) → the matching genes_by_{kind}_metric or metabolites_by_{quantifies,flags}_assay drill-down

Full reference (all examples, full response format, verbose fields): `docs://tools/list_filter_values/full`
