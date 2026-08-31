# list_metabolites

## What it does

Browse the chemistry layer — KEGG-curated metabolism, TCDB-curated transport substrates, and compounds measured by a MetaboliteAssay.

Use as the compound-side entry point; for a metabolite's genes use `genes_by_metabolite`, for measurement evidence `assays_by_metabolite`.
Filters: search_text, metabolite_ids (+exclude), xref ID lists, elements, min/max_mass, organism_names, pathway_ids, evidence_sources.
Returns: top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, by_measurement_coverage; one row = one metabolite.
docs://tools/list_metabolites; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Free-text search on metabolite name (Lucene syntax). Index covers Metabolite.name only — element/formula composition is filtered through `elements` (presence list), not search. E.g. 'glucose', 'phosphate AND amino'. |
| metabolite_ids | list[string] \| None | None | Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites). |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap. |
| kegg_compound_ids | list[string] \| None | None | Filter by raw KEGG C-numbers (e.g. ['C00031']). Convenience over `metabolite_ids` when working with KEGG-anchored data; the prefixed equivalent is `kegg.compound:C*`. |
| chebi_ids | list[string] \| None | None | Filter by raw ChEBI numeric IDs (e.g. ['4167', '15422']). 90% of Metabolite nodes carry a `chebi_id`. |
| hmdb_ids | list[string] \| None | None | Filter by raw HMDB IDs (e.g. ['HMDB0000122']). 47% coverage. |
| mnxm_ids | list[string] \| None | None | Filter by raw MetaNetX IDs (e.g. ['MNXM1364061']). 100% coverage — every Metabolite has a `mnxm_id`. |
| elements | list[string] \| None | None | Element-presence filter (Hill-notation symbols, e.g. 'Fe', 'N'). AND of presence — ['N', 'P'] matches metabolites containing BOTH. A case-insensitive symbol ('n', 'fe') or a full element name ('Nitrogen') for one of the ~12 elements this KG's chemistry layer carries (C, H, N, O, P, S, Fe, Mg, Mn, Zn, Cu, Co, Mo, Ni, Se) is normalized silently; anything else is dropped from the filter and reported in `not_found.elements` with a warning. Use this rather than substring-matching on `formula` (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N'). Empty/null formula metabolites never match. |
| min_mass | float \| None | None | Minimum monoisotopic mass (Da). Excludes metabolites with null `mass` (~22%). E.g. 60.0. |
| max_mass | float \| None | None | Maximum monoisotopic mass (Da). E.g. 1000.0. |
| organism_names | list[string] \| None | None | Restrict to metabolites reachable by these organisms (case-insensitive on `preferred_name`). UNION semantics — a metabolite reached by ANY listed organism qualifies. Joined via `Organism_has_metabolite` (catalysis OR transport). E.g. ['Prochlorococcus MED4']. `not_found.organism_names` lists any unknown names. |
| pathway_ids | list[string] \| None | None | Filter by KEGG pathway membership (`KeggTerm.id`). E.g. ['kegg.pathway:ko00910'] for nitrogen metabolism. Joined via `Metabolite_in_pathway`. `not_found.pathway_ids` lists unknown IDs. |
| evidence_sources | list[string ('metabolism', 'transport', 'metabolomics')] \| None | None | Filter by evidence path. Set-membership ANY semantics — ['transport'] returns transport-only AND dual. Valid values: 'metabolism' (catalysis-reachable), 'transport' (TCDB-curated substrate), 'metabolomics' (measured by a MetaboliteAssay). Other values raise at the MCP boundary. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Example

### All N-bearing metabolites in MED4 (the N-source workflow primitive)

```python
list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"], limit=5)
```

## Response sketch

```expected-keys
total_entries, total_matching, top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, mass_stats, by_measurement_coverage, score_max, score_median, returned, offset, truncated, not_found, resolved_aliases, warnings, results
```

Result row: `metabolite_id, name, formula, elements, mass, catalyst_gene_count, organism_count, transporter_count, transporter_gene_count, evidence_sources, chebi_id, pathway_ids, …`

## Common mistakes

- Direction-agnostic — KEGG equation order is unreliable upstream, so joins through Reaction_has_metabolite (catalysis) and Tcdb_family_transports_metabolite (transport) do NOT distinguish substrates from products. Layer DE direction (`differential_expression_by_gene`) and functional annotation to disambiguate. See docs://analysis/metabolites.

- catalyst_gene_count counts the catalysis arm only (genes reaching the metabolite via Gene → Reaction → Metabolite). catalyst_gene_count = 0 does NOT mean metabolomics-only: transport-only metabolites (TCDB substrates with no local catalysis) also read 0. Discriminate via the paired counts: catalyst_gene_count = 0 with `transporter_gene_count > 0` is transport-only; both 0 with `evidence_sources == ['metabolomics']` is measurement-only (no gene path). `transporter_gene_count` counts distinct genes over their deepest TCDB attachments, all organisms — it equals the distinct genes `genes_by_metabolite` returns in transport rows, summed over organisms.

- organism_names with multiple values is UNION, not intersection. To find metabolites BOTH organisms reach, run two single-org calls and intersect by `metabolite_id` (per-row `organism_count` tells you how many organisms reach a metabolite, but not which — the envelope `top_organisms` rollup is the only per-organism breakdown).

## Chaining patterns

- list_organisms (per-row catalyzed_metabolite_count > 0) → list_metabolites(organism_names=[...])
- list_metabolites → genes_by_metabolite(metabolite_ids=[...], organism=...)
- list_metabolites (per-row `transporter_gene_count > 0`) → genes_by_metabolite(metabolite_ids=[...], organism=..., evidence_sources=['transport']) — distinct genes in the transport rows, summed over organisms, equal transporter_gene_count
- list_metabolites (per-row pathway_ids) → genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...)
- differential_expression_by_gene → metabolites_by_gene(metabolite_elements=['N']) → list_metabolites for chemistry context
- list_metabolites (per-row `measured_assay_count > 0`) → assays_by_metabolite(metabolite_ids=[...]) — reverse lookup of all measurement evidence (numeric + boolean) for the measured compounds (cross-organism by default).

Full reference (all examples, full response format, verbose fields): `docs://tools/list_metabolites/full`
