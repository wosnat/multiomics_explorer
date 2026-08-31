# ontology_landscape

## What it does

Rank (ontology × level) strata by enrichment suitability — term-size distribution, genome coverage, relevance_rank.

Use as the pre-flight that picks (ontology, level) for `pathway_enrichment` / `cluster_enrichment`; the terms are `search_ontology`, gene sets `genes_by_ontology`.
Filters: organism, ontology, tree, experiment_ids, min/max_gene_set_size, informative_only, call_class, interpro_type.
Returns: organism_gene_count, n_ontologies, by_ontology, not_found, not_matched; one row = one stratum (BRITE per tree, InterPro per type).
docs://tools/ontology_landscape; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') \| list[string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops')] \| None | None | If None, surveys all 17 ontologies. Accepts a list; a facet carried by only some of them drops the rest into skipped_ontologies. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Narrows brite and leaves any other ontology in the list untouched; raises when brite is not among them. See docs://guide/conventions for the BRITE-tree scoping rule. |
| experiment_ids | list[string] \| None | None | Restrict coverage computation to genes quantified in these experiments. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int \| None | 15 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |
| min_gene_set_size | int | 5 | Exclude terms with fewer genes than this (default 5). |
| max_gene_set_size | int | 500 | Exclude terms with more genes than this (default 500). |
| informative_only | bool | True | True drops terms the KG flags uninformative (roots, catch-alls). |
| call_class | list[string ('peptidase', 'inhibitor', 'nonpeptidase_homolog')] \| None | None | MEROPS peptidase-call filter: keep rows whose call_class is in this list. Merops only; unfiltered mixes in catalytically-dead nonpeptidase_homolog rows. |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type (e.g. 'DOMAIN', 'FAMILY'). InterPro only; required on interpro enrichment/landscape strata - ranking across mixed entry types is not meaningful. |

**Discovery:** use `list_organisms` for valid organism names.

## Example

### Default survey — which ontology/level should I use for MED4?

```python
ontology_landscape(organism="MED4")
```

## Response sketch

```expected-keys
organism_name, organism_gene_count, n_ontologies, by_ontology, not_found, not_matched, total_matching, returned, truncated, offset, results
```

Result row: `ontology_type, level, tree, tree_code, interpro_type, relevance_rank, n_terms_with_genes, n_genes_at_level, genome_coverage, min_genes_per_term, q1_genes_per_term, median_genes_per_term, …`

## Common mistakes

- Don't pick a level by term-size stats alone -- always check genome_coverage. An ontology may have appealing median term size at a level that covers only 18% of the genome.

- Top-ranked flat ontologies (cog_category, ncbifam) are valid enrichment surfaces but offer no level choice. For hierarchical drill-down, filter results to rows where n_levels_in_ontology > 1. Rows carry `level` only — the meaning of each level (`tc_class`, `tigr_mainrole`, ...) is documented per ontology at docs://ontologies/{key}; there is no `level_kind` column here.

- KEGG has ~40% orphan KOs lacking pathway membership. If L3 coverage is substantially higher than L0-L2 coverage, the gap is structural -- those genes have KO-level annotations only.

## Chaining patterns

- ontology_landscape -> genes_by_ontology(level=N) -> pathway_enrichment
- list_experiments -> ontology_landscape(experiment_ids=...)
- ontology_landscape(ontology='interpro', ...) -> pathway_enrichment(ontology='interpro', interpro_type=..., level=...) (interpro_type is required on interpro enrichment)
- ontology_landscape(ontology='merops', call_class=['peptidase']) -> genes_by_ontology(ontology='merops', call_class=['peptidase'], level=...) -> pathway_enrichment(ontology='merops', call_class=['peptidase'], ...)

Full reference (all examples, full response format, verbose fields): `docs://tools/ontology_landscape/full`
