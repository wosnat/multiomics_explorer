# genes_by_ontology

## What it does

Gene × term pairs for ontology terms in ONE organism (term_ids expand down the hierarchy, level rolls up, both = scoped rollup).

Use to build TERM2GENE or list a term's genes; for a gene's own annotations use `gene_ontology_terms`, for substrate-anchored TCDB / EC `genes_by_metabolite`.
Filters: ontology, organism, term_ids, level, tree, min/max_gene_set_size, informative_only, trust filters.
Returns: by_category, by_level, top_terms, trust rollups, not_found, wrong_ontology, wrong_level; one row = (locus_tag, term_id, evidence).
docs://tools/genes_by_ontology; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') | — | Ontology for these term_ids / this level. |
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'. See docs://guide/conventions for the BRITE-tree scoping rule. |
| level | int \| None | None | Hierarchy level to roll UP to (0 = broadest). At least one of `level` or `term_ids` must be provided. See docs://guide/conventions. |
| term_ids | list[string] \| None | None | Ontology term IDs (from search_ontology). Without `level`: expand DOWN from each input term. With `level`: scope rollup to these level-N terms. Bare ids are accepted (e.g. 'ko00910', 'GO:0006979') and coerced to canonical (see `resolved_aliases`). |
| min_gene_set_size | int | 5 | Exclude terms with fewer organism-scoped genes than this. Matches `ontology_landscape`'s organism-scoped convention. |
| max_gene_set_size | int | 500 | Exclude terms with more organism-scoped genes than this. Matches `ontology_landscape`'s organism-scoped convention. |
| informative_only | bool | False | True drops terms the KG flags uninformative (roots, catch-alls). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| sources | list[string] \| None | None | Keep rows whose edge sources[] contains any of these values. Valid on the 14 functional-edge ontologies (not PSORTb/SignalP). See list_filter_values('sources'). |
| evidence | list[string] \| None | None | Keep rows whose compact evidence-ladder value is in this list. Valid on the 14 functional-edge ontologies. See docs://analysis/annotation_evidence. |
| max_tier | int \| None | None | Keep rows with edge tier <= this value OR tier IS NULL (diamond truncation depth, 1-3; null tier always kept). Valid on tcdb, merops only. |
| min_evidence_score | float \| None | None | Keep rows with edge evidence_score >= this cutoff (0-1; the only native-scalar cutoff allowed). Valid on go_bp/mf/cc, ec, pfam, cazy, tcdb, merops. |
| call_class | list[string ('peptidase', 'inhibitor', 'nonpeptidase_homolog')] \| None | None | MEROPS peptidase-call filter: keep rows whose call_class is in this list. Merops only; unfiltered mixes in catalytically-dead nonpeptidase_homolog rows. |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type (e.g. 'DOMAIN', 'FAMILY'). InterPro only; required on interpro enrichment/landscape strata - ranking across mixed entry types is not meaningful. |
| limit | int | 50 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Example

### Mode 1 — gene discovery by pathway (term_ids only)

```python
genes_by_ontology(ontology="go_bp", organism="MED4", term_ids=["go:0006260"])
```

## Response sketch

```expected-keys
ontology, organism_name, total_matching, total_genes, total_terms, total_categories, genes_per_term_min, genes_per_term_median, genes_per_term_max, terms_per_gene_min, terms_per_gene_median, terms_per_gene_max, by_category, by_level, top_terms, n_best_effort_terms, not_found, wrong_ontology, wrong_level, filtered_out, resolved_aliases, returned, offset, truncated, trust_axes, warnings, filters_applied, skipped_ontologies, by_evidence, by_tier, by_sources, by_call_class, evidence_score_stats, results
```

Result row: `locus_tag, gene_name, product, gene_category, term_id, term_name, level, is_informative, tree, tree_code, localization_score, signal_peptide_probability, …`

## Common mistakes

- Term-anchored (term → genes). For 'which terms does this gene carry?' use `gene_ontology_terms(locus_tags=[...])` — same ontology surface, opposite anchor.

- At least one of `level` or `term_ids` must be set — calling without either is an error.

- Results are `(gene × term)` pairs, not distinct genes — use `total_genes` for the gene count. `total_matching` is the row count.

## Chaining patterns

- Term-anchored: term / level → (gene × term) pairs, hierarchy expanded DOWN. The gene-anchored reverse (locus_tags → their terms, leaf or rollup) is `gene_ontology_terms`.
- ontology_landscape → genes_by_ontology(level=N)
- search_ontology → genes_by_ontology(term_ids=[...])
- genes_by_ontology → pathway_enrichment
- genes_by_ontology → gene_overview
- genes_by_ontology(ontology='tcdb' | 'ec', term_ids=[...]) → genes_by_metabolite (substrate-anchored pivot — see docs://analysis/metabolites)
- From PSORTb-filtered genes → differential_expression_by_gene to ask: are outer-membrane proteins enriched in the up-regulated set?
- list_filter_values(filter_type='trust_axes') → check which trust params an ontology supports before filtering — see docs://analysis/annotation_evidence
- genes_by_ontology(ontology='merops', call_class=['peptidase']) → pathway_enrichment(ontology='merops', call_class=['peptidase']) to keep the TERM2GENE definitions and the enrichment test on the same trust-filtered gene set

Full reference (all examples, full response format, verbose fields): `docs://tools/genes_by_ontology/full`
