# list_metabolites

## What it does

Browse the chemistry layer — KEGG-curated metabolism, TCDB-curated transport substrates, and compounds measured by a MetaboliteAssay.

Use as the compound-side entry point; genes via `genes_by_metabolite`, measurements via `assays_by_metabolite`.
Filters: search_text, metabolite_ids (+exclude), xref IDs, elements, mass, organism_names, pathway_ids, evidence_sources, structure_kind, kegg_functional_categories, kegg_brite_classes.
Returns: top_organisms, top pathways, by_evidence_source, by_structure_kind, by_kegg_*; one row = one metabolite.
docs://tools/list_metabolites; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Free-text search (Lucene) over metabolite name, formula and identifiers (KEGG / ChEBI / MNX / HMDB ids, InChIKey). A formula hit is a token match — for composition use `elements`. E.g. 'glucose', 'phosphate AND amino'. |
| metabolite_ids | list[string] \| None | None | Metabolite IDs in any form (KEGG, ChEBI, MNX, HMDB, InChIKey; bare or prefixed). Retired ids resolve (see resolved_aliases); removed compounds and chemical roles warn. docs://analysis/metabolites. |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; any id form, bare or prefixed, retired ids resolve (see resolved_aliases); exclude wins on overlap. |
| kegg_compound_ids | list[string] \| None | None | KEGG compound ids, bare or prefixed (e.g. ['C00031']). Matches any of the metabolite's identifiers, including secondary and retired ones, so a merged compound's old KEGG id still finds it. |
| chebi_ids | list[string] \| None | None | ChEBI ids, bare digits or 'CHEBI:' form (e.g. ['4167', 'CHEBI:15422']). Matches any of the metabolite's identifiers, including secondary and retired ones. |
| hmdb_ids | list[string] \| None | None | HMDB ids (e.g. ['HMDB0000122']; short 'HMDB02878' is padded). Matches any of the metabolite's identifiers, including secondary and retired ones. |
| mnxm_ids | list[string] \| None | None | MetaNetX ids (e.g. ['MNXM1364061']). Matches any of the metabolite's identifiers, including secondary and retired ones. |
| elements | list[string] \| None | None | Element-presence filter (Hill-notation symbols, e.g. 'Fe', 'N'). AND of presence — ['N', 'P'] matches metabolites containing BOTH. A case-insensitive symbol ('n', 'fe') or a full element name ('Nitrogen') for one of the ~12 elements this KG's chemistry layer carries (C, H, N, O, P, S, Fe, Mg, Mn, Zn, Cu, Co, Mo, Ni, Se) is normalized silently; anything else is dropped from the filter and reported in `not_found.elements` with a warning. Use this rather than substring-matching on `formula` (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N'). Empty/null formula metabolites never match. |
| min_mass | float \| None | None | Minimum monoisotopic mass (Da). Excludes metabolites with null `mass` (~22%). E.g. 60.0. |
| max_mass | float \| None | None | Maximum monoisotopic mass (Da). E.g. 1000.0. |
| organism_names | list[string] \| None | None | Restrict to metabolites reachable by these organisms (case-insensitive on `preferred_name`). UNION semantics — a metabolite reached by ANY listed organism qualifies. Matches `Organism_has_metabolite` (catalysis OR TCDB transport) or `go_transport_organism_names`. E.g. ['Prochlorococcus MED4']. `not_found.organism_names` lists any unknown names. |
| pathway_ids | list[string] \| None | None | Filter by KEGG pathway membership (`KeggTerm.id`). E.g. ['kegg.pathway:ko00910'] for nitrogen metabolism. Joined via `Metabolite_in_pathway`. `not_found.pathway_ids` lists unknown IDs. |
| evidence_sources | list[string ('metabolism', 'transport', 'metabolomics', 'go_transport')] \| None | None | Filter by evidence path (ANY). Values: 'metabolism' (catalysis-reachable), 'transport' (TCDB substrate), 'metabolomics' (measured by a MetaboliteAssay), 'go_transport' (named by a GO transport term). Other values raise at the MCP boundary. |
| structure_kind | list[string] \| None | None | Structure kind(s) (OR): 'defined' (one molecule), 'generic' (a compound class) or 'polymer'. E.g. ['defined'] drops generic substrates like 'amino acid'. Values: list_filter_values('structure_kind'). |
| kegg_functional_categories | list[string] \| None | None | KEGG br08001 categories (OR). Hand-curated and partial: only ~10% of metabolites are listed, so a missing category means 'KEGG did not list it', not 'not in it' (fumarate is unclassified). Values: list_filter_values('kegg_functional_category'). |
| kegg_brite_classes | list[string] \| None | None | Classes from 7 other KEGG compound BRITE trees, as 'Tree: Class' (OR), e.g. 'Lipids: Fatty acyls'. Curated and partial (~20% of metabolites): unlisted = 'KEGG did not list it', not 'not in it'. Values: list_filter_values('kegg_brite_class'). |
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
total_entries, total_matching, top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, mass_stats, by_measurement_coverage, by_structure_kind, by_kegg_functional_category, by_kegg_brite_class, score_max, score_median, returned, offset, truncated, not_found, resolved_aliases, warnings, results
```

Result row: `metabolite_id, name, formula, elements, mass, catalyst_gene_count, organism_count, transporter_count, transporter_gene_count, evidence_sources, go_transport_organism_names, go_transport_organism_count, …`

## Common mistakes

- Direction-agnostic — KEGG equation order is unreliable upstream, so joins through Reaction_has_metabolite (catalysis) and Tcdb_family_transports_metabolite (transport) do NOT distinguish substrates from products. Layer DE direction (`differential_expression_by_gene`) and functional annotation to disambiguate. See docs://analysis/metabolites.

## Chaining patterns

- list_organisms (per-row catalyzed_metabolite_count > 0) → list_metabolites(organism_names=[...])
- list_metabolites → genes_by_metabolite(metabolite_ids=[...], organism=...)
- list_metabolites (per-row `transporter_gene_count > 0`) → genes_by_metabolite(metabolite_ids=[...], organism=..., evidence_sources=['transport']) — distinct genes in the transport rows, summed over organisms, equal transporter_gene_count
- list_metabolites (per-row `stereo_relatives`) → genes_by_metabolite(metabolite_ids=[generic id], organism=..., include_stereo_forms=True) — transport on the generic form plus catalysis on the specific form, per organism
- list_metabolites (per-row pathway_ids) → genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...)
- differential_expression_by_gene → metabolites_by_gene(metabolite_elements=['N']) → list_metabolites for chemistry context
- list_metabolites (per-row `kegg_brite_classes`, top level only) → run_cypher over `MetaboliteClass` for the deeper KEGG compound classes (docs://analysis/metabolites)
- list_metabolites (per-row `measured_assay_count > 0`) → assays_by_metabolite(metabolite_ids=[...]) — reverse lookup of all measurement evidence (numeric + boolean) for the measured compounds (cross-organism by default).
- list_metabolites(evidence_sources=['go_transport'], organism_names=[...]) → genes_by_metabolite(metabolite_ids=[...], organism=..., evidence_sources=['go_transport']) for the genes carrying the GO term

Full reference (all examples, full response format, verbose fields): `docs://tools/list_metabolites/full`
