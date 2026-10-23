# genes_by_metabolite

## What it does

Metabolite IDs to gene catalysts (via Reaction) and transporters (via TcdbFamily, deepest attachment) in ONE organism.

Use for compound → genes; mirror `metabolites_by_gene`, family-level TCDB `genes_by_ontology`.
Filters: metabolite_ids (+exclude, +stereo forms), organism, ec_numbers, metabolite_pathway_ids, gene_categories, substrate_depth, evidence_sources.
Returns: by_metabolite, by_evidence_source, by_substrate_depth, top_genes, top_reactions, top_tcdb_families, not_matched; one row = gene × metabolite.
docs://tools/genes_by_metabolite; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| metabolite_ids | list[string] | — | Metabolite IDs in any form (KEGG, ChEBI, MNX, HMDB, InChIKey; bare or prefixed). Retired ids resolve (see resolved_aliases); removed compounds and chemical roles warn. docs://analysis/metabolites. |
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Must resolve to ONE organism — an ambiguous match (e.g. a genus word) raises; see list_organisms. |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; any id form, bare or prefixed, retired ids resolve (see resolved_aliases); exclude wins on overlap. |
| ec_numbers | list[string] \| None | None | Narrow metabolism rows to those whose Reaction carries any of these EC numbers. **Metabolism arm only — does not affect transport rows**, which are returned unchanged. To restrict to metabolism rows alone, combine with `evidence_sources=['metabolism']`. E.g. ['6.3.1.2'] for glutamine synthetase. |
| metabolite_pathway_ids | list[string] \| None | None | Filter to rows where the **metabolite** is in any of these KEGG pathways (`KeggTerm.id`, e.g. ['kegg.pathway:ko00910'] for nitrogen metabolism). Anchored on `Metabolite.pathway_ids` (transport-extended), so applies uniformly to both arms. **Not gene-anchored** — for filtering by genes' KEGG-pathway annotations, route through `genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...)` first to obtain locus_tags. `not_found.metabolite_pathway_ids` lists IDs that don't exist as a KeggTerm. |
| mass_balance | string ('balanced', 'unbalanced') \| None | None | Narrow metabolism rows to those whose Reaction has this mass balance status. **Metabolism arm only — does not affect transport rows**. Combine with `evidence_sources=['metabolism']` to restrict to metabolism rows alone. |
| gene_categories | list[string] \| None | None | Filter on `Gene.gene_category` (exact match, applies to both arms uniformly). Use `list_filter_values(filter_type="gene_category")` to discover valid values. |
| substrate_depth | list[string ('most_specific', 'inherited')] \| None | None | Keep transport rows whose edge `substrate_depth` is in this list. 'most_specific' = most specific surviving transporter node for the substrate (gene-pruned hierarchy, not a curation level). Transport arm only. |
| evidence_sources | list[string ('metabolism', 'transport', 'go_transport')] \| None | None | Path selector — restricts which arms execute (metabolism, transport, go_transport). Default fires all three. `['metabolism']` skips transport rollup noise. 'metabolomics' is NOT valid here (no gene anchor); see `list_metabolites`. |
| go_include_ancestors | bool | False | GO route only: also return inherited rows, where a gene's GO term reaches the target through is_a ancestors (go_term_depth > 0). Default False = directly annotated terms. |
| include_stereo_forms | bool | False | Also query the generic <-> specific stereo forms of each metabolite_id (e.g. Cysteine <-> L-Cysteine; TCDB lists generic names, KEGG reactions use specific forms). Added rows carry via_stereo_form_of. Enantiomers are never added. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 10 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Discovery → drill-down — urea catalysts and transporters in MED4

```python
genes_by_metabolite(metabolite_ids=["kegg.compound:C00086"], organism="Prochlorococcus MED4")
```

## Response sketch

```expected-keys
total_matching, returned, offset, truncated, warnings, stereo_relatives, stereo_forms_added, resolved_aliases, not_found, not_matched, by_metabolite, by_evidence_source, by_substrate_depth, rows_by_go_term_depth, top_reactions, top_tcdb_families, top_gene_categories, top_genes, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

Result row: `locus_tag, gene_name, product, evidence_source, substrate_depth, tcdb_evidence_score, transport_substrate_resolution, reaction_id, reaction_name, ec_numbers, mass_balance, tcdb_family_id, …`

## Common mistakes

- Metabolite-anchored (metabolite → genes). The gene-anchored mirror is `metabolites_by_gene` (locus_tags → metabolites); both share the same row class, discriminators and per-arm filter scope, so read whichever matches your anchor rather than post-filtering the other.

Chaining patterns: see `docs://tools/genes_by_metabolite/full`.

Full reference (all examples, full response format, verbose fields): `docs://tools/genes_by_metabolite/full`
