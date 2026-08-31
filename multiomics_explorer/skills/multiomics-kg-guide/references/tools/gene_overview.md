# gene_overview

## What it does

Batch gene triage: identity plus per-gene data-availability signals — expression, ortholog, cluster, DM, chemistry, annotation-family and literature counts.

Use to decide which drill-down has evidence for a gene batch; for the raw node dump use `gene_details`.
Filters: locus_tags.
Returns: by_organism, by_category, by_annotation_type, has_* batch counts, top_discussing_publications, not_found; one row = one gene's routing counts.
docs://tools/gene_overview; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845']. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int \| None | None | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Example

### Overview of a single gene

```python
gene_overview(locus_tags=["PMM1428"])
```

## Response sketch

```expected-keys
total_matching, by_organism, by_category, by_annotation_type, by_annotation_state, has_expression, has_significant_expression, has_orthologs, has_clusters, has_derived_metrics, has_chemistry, has_discussed, top_discussing_publications, has_ncbifam, has_tcdb, has_cazy, by_merops_class, returned, offset, truncated, not_found, warnings, results
```

Result row: `locus_tag, gene_name, product, gene_category, annotation_quality, organism_name, annotation_types, annotation_state, informative_annotation_types, expression_edge_count, significant_up_count, significant_down_count, …`

## Common mistakes

- annotation_quality / min_quality semantics shifted in 2026-05 KG release. Existing notebooks using min_quality may select a different gene set than before. See docs://guide/conventions.

- If a result row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric. Empty derived_metric_value_kinds means no DM evidence on this gene.

- annotation_types lists which ontology types have data — use gene_ontology_terms to get the actual terms.

## Chaining patterns

- resolve_gene → gene_overview
- genes_by_function → gene_overview
- gene_overview → gene_ontology_terms
- gene_overview → gene_homologs
- gene_overview → differential_expression_by_gene
- gene_overview → gene_clusters_by_gene
- gene_overview(locus_tags=...) → for genes with derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric; for ['numeric'] use genes_by_numeric_metric; for ['categorical'] use genes_by_categorical_metric
- gene_overview(verbose=True) → see compartments_observed for vesicle/whole-cell triage
- gene_overview (per-row `evidence_sources` non-empty) → metabolites_by_gene OR genes_by_metabolite for chemistry drill-down.
- gene_overview (per-row `transport_substrate_resolution='resolved'`, after reading `tcdb_evidence_score_max`) → metabolites_by_gene(locus_tags=[...], organism=..., evidence_sources=['transport']) — distinct metabolites in the rows equal `transported_metabolite_count`.
- gene_overview (per-row `discussed_in_publication_count` > 0) → use verbose=True for the per-gene {doi, prominence, evidence} list, or discussed_by_publication(publication_dois=[...]) for the paper's full discussed set.
- gene_overview (per-row `tcdb_family_count` > 0) → gene_ontology_terms(locus_tags=[...], ontology=['tcdb']) for the family IDs and evidence; `cazy_family_count` > 0 → gene_ontology_terms(locus_tags=[...], ontology=['cazy']), or genes_by_ontology(ontology='cazy', organism=...) for peers.
- gene_overview envelope `has_tcdb` / `has_cazy` = batch triage (how many input genes carry a transporter-family / carbohydrate-active-enzyme call) before deciding whether a pathway_enrichment(ontology='tcdb'|'cazy') run is worth it.
- gene_overview (per-row `merops_classes` non-empty) → gene_ontology_terms(locus_tags=[...], ontology=['merops'], verbose=True) for the confidence_score / pfam_support detail behind the call, or genes_by_ontology(ontology='merops', call_class=['peptidase']) to find peers.
- `merops_classes` is a list (`[]` default) because a gene can carry both a `peptidase` and a `nonpeptidase_homolog` MEROPS call on different families — don't assume at most one value. `merops_evidence_score_max` is sparse and uncoalesced (null = no MEROPS call at all, the twin contract of `tcdb_evidence_score_max`) — rank by it, never filter by it.
- gene_overview (per-row derived_metric_count > 0) → gene_derived_metrics(locus_tags=[...], organism=...) for the gene's full DM profile across numeric, boolean and categorical kinds

Full reference (all examples, full response format, verbose fields): `docs://tools/gene_overview/full`
