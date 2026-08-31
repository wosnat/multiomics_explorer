# gene_ontology_terms

## What it does

Reverse lookup: locus_tags to their ontology annotations in ONE organism, most-specific leaves (default) or rolled up to a level.

Use for what a gene carries; for which genes carry a term use `genes_by_ontology`, to find term IDs `search_ontology`.
Filters: locus_tags, organism, ontology, mode, level, tree, informative_only, include_superseded, trust filters.
Returns: by_ontology, by_term, terms-per-gene stats, trust rollups, skipped_ontologies, not_found, no_terms; one row = (locus_tag, term_id, evidence).
docs://tools/gene_ontology_terms; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845']. |
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') \| list[string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops')] \| None | None | Filter to one ontology, or a list of ontologies (trust filters/facets shape all-or-skip-or-raise per docs://guide/conventions). None returns all. |
| mode | string ('leaf', 'rollup') | leaf | 'leaf' returns most-specific annotations (default). 'rollup' walks up to ancestors at the given level. |
| level | int \| None | None | Hierarchy level (0 = broadest). In leaf mode: filter to leaves at this level. In rollup mode: required — target ancestor level. See docs://guide/conventions. |
| tree | string \| None | None | BRITE tree name filter. Narrows brite and leaves any other ontology in the list untouched; raises when brite is not among them. See docs://guide/conventions for the BRITE-tree scoping rule. |
| informative_only | bool | False | True drops terms the KG flags uninformative (roots, catch-alls). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| sources | list[string] \| None | None | Keep rows whose edge sources[] contains any of these values. Valid on the 14 functional-edge ontologies (not PSORTb/SignalP). See list_filter_values('sources'). |
| evidence | list[string] \| None | None | Keep rows whose compact evidence-ladder value is in this list. Valid on the 14 functional-edge ontologies. See docs://analysis/annotation_evidence. |
| max_tier | int \| None | None | Keep rows with edge tier <= this value OR tier IS NULL (diamond truncation depth, 1-3; null tier always kept). Valid on tcdb, merops only. |
| min_evidence_score | float \| None | None | Keep rows with edge evidence_score >= this cutoff (0-1; the only native-scalar cutoff allowed). Valid on go_bp/mf/cc, ec, pfam, cazy, tcdb, merops. |
| call_class | list[string ('peptidase', 'inhibitor', 'nonpeptidase_homolog')] \| None | None | MEROPS peptidase-call filter: keep rows whose call_class is in this list. Merops only; unfiltered mixes in catalytically-dead nonpeptidase_homolog rows. |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type (e.g. 'DOMAIN', 'FAMILY'). InterPro only; required on interpro enrichment/landscape strata - ranking across mixed entry types is not meaningful. |
| include_superseded | bool | False | TCDB leaf mode only: when True, also include rows whose gene->term attachment is less specific ('superseded') rather than the deepest ('most_specific'). Default False. |
| limit | int | 50 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Example

### GO biological process terms for a gene

```python
gene_ontology_terms(locus_tags=["PMM0001"], organism="MED4", ontology="go_bp")
```

## Response sketch

```expected-keys
total_matching, total_genes, total_terms, by_ontology, by_term, terms_per_gene_min, terms_per_gene_max, terms_per_gene_median, returned, offset, truncated, not_found, no_terms, trust_axes, by_evidence, by_tier, by_sources, by_call_class, evidence_score_stats, filters_applied, skipped_ontologies, warnings, results
```

Result row: `locus_tag, term_id, term_name, level, is_informative, ontology_type, tree, tree_code, localization_score, signal_peptide_probability, signal_peptide_cleavage_site, signal_peptide_cleavage_probability, …`

## Common mistakes

- Gene-anchored: locus_tags → the terms they carry. The term-anchored reverse (term → genes, hierarchy expanded DOWN, TERM2GENE for enrichment) is `genes_by_ontology`; for enrichment workflows that forward direction is canonical — see `docs://analysis/enrichment`.

- organism is required — single-valued. Locus tags must belong to the specified organism.

- ontology=None returns ALL ontology types — use ontology filter when you only need one type

## Chaining patterns

- gene_overview → gene_ontology_terms (check annotation_types first)
- gene_ontology_terms → genes_by_ontology (reverse: term → other genes)
- resolve_gene → gene_ontology_terms
- gene_ontology_terms(ontology=['merops'], call_class=['peptidase']) → gene_overview to cross-check merops_classes / merops_evidence_score_max
- See docs://analysis/annotation_evidence for the full trust-axis reference and rank-vs-filter guidance.

Full reference (all examples, full response format, verbose fields): `docs://tools/gene_ontology_terms/full`
