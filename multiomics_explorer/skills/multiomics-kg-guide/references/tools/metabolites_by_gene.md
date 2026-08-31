# metabolites_by_gene

## What it does

Metabolites a gene batch's chemistry reaches in ONE organism — reaction and transport arms, mirroring `genes_by_metabolite`.

Use for the gene-anchored direction; compound-anchored is `genes_by_metabolite`, measurements `assays_by_metabolite`.
Filters: locus_tags, organism, metabolite_elements, metabolite_ids (+exclude), ec_numbers, substrate_depth, evidence_sources.
Returns: by_gene, by_element, by_evidence_source, by_substrate_depth, top_metabolites, top_metabolite_pathways, not_matched; one row = one gene × metabolite.
docs://tools/metabolites_by_gene; summary=True first for 50+ genes.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to drill into (case-sensitive). E.g. ['PMM0963', 'PMM0964', 'PMM0965'] for urease α/β/γ subunits. `not_found.locus_tags` lists tags that don't resolve to any Gene in the requested organism; `not_matched` lists tags that DO resolve but have no chemistry edges (no Gene_catalyzes_reaction AND no Gene_has_tcdb_family). |
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| metabolite_elements | list[string] \| None | None | Filter to rows where the metabolite contains ALL of the given element symbols (AND-of-presence). E.g. `['N']` keeps only N-bearing metabolites — the headline N-source workflow primitive. `['N', 'P']` requires both. Anchored on `Metabolite.elements` (KG-A3 Hill-parsed presence list); applies uniformly to both arms. Never substring-match on `formula` (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N'). `not_found.metabolite_elements` lists symbols that don't exist on any KG metabolite. |
| metabolite_ids | list[string] \| None | None | Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites). |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap. |
| ec_numbers | list[string] \| None | None | Narrow metabolism rows to those whose Reaction carries any of these EC numbers. **Metabolism arm only — does not affect transport rows**, which are returned unchanged. To restrict to metabolism rows alone, combine with `evidence_sources=['metabolism']`. E.g. ['3.5.1.5'] for urease. |
| metabolite_pathway_ids | list[string] \| None | None | Filter to rows where the **metabolite** is in any of these KEGG pathways (`KeggTerm.id`, e.g. ['kegg.pathway:ko00910'] for nitrogen metabolism). Anchored on `Metabolite.pathway_ids` (transport-extended), so applies uniformly to both arms. **Not gene-anchored** — for filtering by genes' KEGG-pathway annotations, route through `genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...)` first to obtain locus_tags. `not_found.metabolite_pathway_ids` lists IDs that don't exist as a KeggTerm. |
| mass_balance | string ('balanced', 'unbalanced') \| None | None | Narrow metabolism rows to those whose Reaction has this mass balance status. **Metabolism arm only — does not affect transport rows**. Combine with `evidence_sources=['metabolism']` to restrict to metabolism rows alone. |
| gene_categories | list[string] \| None | None | Filter on `Gene.gene_category` (exact match, applies to both arms uniformly). Use `list_filter_values(filter_type="gene_category")` for valid values. Note: somewhat redundant with `locus_tags` input; useful when locus_tags is a broad batch and you want chemistry from specific functional categories only. |
| substrate_depth | list[string ('most_specific', 'inherited')] \| None | None | Keep transport rows whose edge `substrate_depth` is in this list. 'most_specific' = most specific surviving transporter node for the substrate (gene-pruned hierarchy, not a curation level). Transport arm only; mutes ABC tails. |
| evidence_sources | list[string ('metabolism', 'transport')] \| None | None | Path selector — restricts which arms execute. Set to `['metabolism']` to skip transport entirely (no rollup noise); `['transport']` to skip metabolism. Default fires both arms. Note: `'metabolomics'` is NOT a valid value here — metabolomics evidence has no gene anchor and surfaces only in `list_metabolites`. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 10 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Single-gene drill-down — resolved transporter (Workflow D)

```python
metabolites_by_gene(locus_tags=["PMM0392"], organism="Prochlorococcus MED4", evidence_sources=["transport"])
```

## Response sketch

```expected-keys
total_matching, returned, offset, truncated, warnings, resolved_aliases, not_found, not_matched, by_gene, by_evidence_source, by_substrate_depth, by_element, top_metabolites, top_reactions, top_tcdb_families, top_gene_categories, top_metabolite_pathways, gene_count_total, reaction_count_total, transporter_count_total, metabolite_count_total, results
```

Result row: `locus_tag, gene_name, product, evidence_source, substrate_depth, tcdb_evidence_score, transport_substrate_resolution, reaction_id, reaction_name, ec_numbers, mass_balance, tcdb_family_id, …`

## Common mistakes

- Gene-anchored (locus_tags → metabolites). The metabolite-anchored mirror is `genes_by_metabolite` (metabolite → genes); both share the same row class, discriminators and per-arm filter scope.

Chaining patterns: see `docs://tools/metabolites_by_gene/full`.

Full reference (all examples, full response format, verbose fields): `docs://tools/metabolites_by_gene/full`
