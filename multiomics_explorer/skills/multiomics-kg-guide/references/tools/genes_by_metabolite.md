# genes_by_metabolite

## What it does

Metabolite IDs to gene catalysts (via Reaction) and transporters (via TcdbFamily, deepest attachment) in ONE organism.

Use for the compound-anchored direction; the gene-anchored mirror is `metabolites_by_gene`, family-level TCDB `genes_by_ontology`.
Filters: metabolite_ids (+exclude), organism, ec_numbers, metabolite_pathway_ids, gene_categories, substrate_depth, evidence_sources.
Returns: by_metabolite, by_evidence_source, by_substrate_depth, top_genes, top_reactions, top_tcdb_families, not_matched; one row = one gene × metabolite.
docs://tools/genes_by_metabolite; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| metabolite_ids | list[string] | — | Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites). |
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap. |
| ec_numbers | list[string] \| None | None | Narrow metabolism rows to those whose Reaction carries any of these EC numbers. **Metabolism arm only — does not affect transport rows**, which are returned unchanged. To restrict to metabolism rows alone, combine with `evidence_sources=['metabolism']`. E.g. ['6.3.1.2'] for glutamine synthetase. |
| metabolite_pathway_ids | list[string] \| None | None | Filter to rows where the **metabolite** is in any of these KEGG pathways (`KeggTerm.id`, e.g. ['kegg.pathway:ko00910'] for nitrogen metabolism). Anchored on `Metabolite.pathway_ids` (transport-extended), so applies uniformly to both arms. **Not gene-anchored** — for filtering by genes' KEGG-pathway annotations, route through `genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...)` first to obtain locus_tags. `not_found.metabolite_pathway_ids` lists IDs that don't exist as a KeggTerm. |
| mass_balance | string ('balanced', 'unbalanced') \| None | None | Narrow metabolism rows to those whose Reaction has this mass balance status. **Metabolism arm only — does not affect transport rows**. Combine with `evidence_sources=['metabolism']` to restrict to metabolism rows alone. |
| gene_categories | list[string] \| None | None | Filter on `Gene.gene_category` (exact match, applies to both arms uniformly). Use `list_filter_values(filter_type="gene_category")` to discover valid values. |
| substrate_depth | list[string ('most_specific', 'inherited')] \| None | None | Keep transport rows whose edge `substrate_depth` is in this list. 'most_specific' = most specific surviving transporter node for the substrate (gene-pruned hierarchy, not a curation level). Transport arm only. |
| evidence_sources | list[string ('metabolism', 'transport')] \| None | None | Path selector — restricts which arms execute. Set to `['metabolism']` to skip transport entirely (no rollup noise); `['transport']` to skip metabolism. Default fires both arms. Note: `'metabolomics'` is NOT a valid value here — metabolomics evidence has no gene anchor and surfaces only in `list_metabolites`. |
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
total_matching, returned, offset, truncated, warnings, resolved_aliases, not_found, not_matched, by_metabolite, by_evidence_source, by_substrate_depth, top_reactions, top_tcdb_families, top_gene_categories, top_genes, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

Result row: `locus_tag, gene_name, product, evidence_source, substrate_depth, tcdb_evidence_score, transport_substrate_resolution, reaction_id, reaction_name, ec_numbers, mass_balance, tcdb_family_id, …`

## Common mistakes

- Metabolite-anchored (metabolite → genes). The gene-anchored mirror is `metabolites_by_gene` (locus_tags → metabolites); both share the same row class, discriminators and per-arm filter scope, so read whichever matches your anchor rather than post-filtering the other.

- Read transport evidence as a three-level trust ladder, top down. (1) `tcdb_evidence_score` (row) / `tcdb_evidence_score_max` (gene, in `top_genes`) — how corroborated the gene × family call is. Rank by it, never filter by it; 0 means an uncorroborated hit, not an absent call (absent is `tcdb_evidence_score_max = None`). (2) Gene-level `transport_substrate_resolution` in `top_genes` — `family_inferred` means the gene's substrate breadth is reachability through a lumping family, not capability; `resolved` means AT LEAST ONE of the gene's deepest attachments is non-lumping, not all of them — a gene attached at both a specific family and the ABC superfamily is `resolved` and still carries the superfamily rollup. (3) Per-row `substrate_depth` — `most_specific` is the most specific SURVIVING transporter node for this substrate relative to the gene-pruned hierarchy; it can be a family node (nitrite via tcdb:2.A.16) and it is not a curation level. `inherited` rows came down from an ancestor's substrate set.

- Row-level `transport_substrate_resolution` is the GENE's resolution (the same KG value `gene_overview` and `top_genes[]` carry), repeated on every transport row of that gene — it is not a per-substrate fact and it does not vary across a gene's rows. Do not read `family_inferred` on a row as "this substrate is inferred": it says the gene's whole substrate breadth is reachability through a lumping family. The per-row fact is `substrate_depth`. Metabolism rows read `None` (union padding), never `resolved`. Group rows by locus_tag when you want one resolution per gene, or read `top_genes[]` directly.

Full reference (all examples, full response format, verbose fields): `docs://tools/genes_by_metabolite/full`
