# list_metabolites

## What it does

Browse and filter metabolites in the chemistry layer.

**Direction-agnostic.** Joins through `Reaction_has_metabolite` and
(post-TCDB) `Tcdb_family_transports_metabolite` are direction-agnostic —
a metabolite that is *produced* and one that is *consumed* surface
identically. KEGG equation order is arbitrary. To distinguish, layer
transcriptional evidence (`differential_expression_by_gene`) and
functional annotation (`gene_overview` Pfam/KO `*-synthase` vs
`*-permease`).

Per-row `elements` and the `elements=` filter are presence-only
(presence list, not stoichiometric — atom counts live in formula).

After this tool, drill in via:
- genes_by_metabolite(metabolite_ids=[id], organism=...) — find the
  catalysts / transporters per organism (replaces what would
  otherwise be an inline per-row top-N gene list here)
- gene_metabolic_role(locus_tags=[...], organism=..., metabolite_elements=...) — gene-centric chemistry
- genes_by_ontology(ontology="kegg", term_ids=[pathway_id], organism=...) — pathway → genes

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Free-text search on metabolite name (Lucene syntax). Index covers Metabolite.name only — element/formula composition is filtered through `elements` (presence list), not search. E.g. 'glucose', 'phosphate AND amino'. |
| metabolite_ids | list[string] \| None | None | Restrict to specific metabolites by full prefixed ID (case-sensitive). E.g. ['kegg.compound:C00031', 'kegg.compound:C00002']. Combines with other filters via AND. `not_found.metabolite_ids` lists any IDs that don't exist in the KG. |
| exclude_metabolite_ids | list[string] \| None | None | Exclude metabolites with these IDs. Set-difference semantics with `metabolite_ids` — exclude wins on overlap. Empty list is no-op. |
| kegg_compound_ids | list[string] \| None | None | Filter by raw KEGG C-numbers (e.g. ['C00031']). Convenience over `metabolite_ids` when working with KEGG-anchored data; the prefixed equivalent is `kegg.compound:C*`. |
| chebi_ids | list[string] \| None | None | Filter by raw ChEBI numeric IDs (e.g. ['4167', '15422']). 90% of Metabolite nodes carry a `chebi_id`. |
| hmdb_ids | list[string] \| None | None | Filter by raw HMDB IDs (e.g. ['HMDB0000122']). 47% coverage. |
| mnxm_ids | list[string] \| None | None | Filter by raw MetaNetX IDs (e.g. ['MNXM1364061']). 100% coverage — every Metabolite has a `mnxm_id`. |
| elements | list[string] \| None | None | Element-presence filter (Hill-notation symbols). AND of presence — ['N', 'P'] matches metabolites containing BOTH. Replaces error-prone formula-substring matching. Empty/null formula metabolites (~10%) never match. E.g. ['N'] for nitrogen-containing metabolites (yields 1,563 today). |
| mass_min | float \| None | None | Minimum monoisotopic mass (Da). Excludes metabolites with null `mass` (~22%). E.g. 60.0. |
| mass_max | float \| None | None | Maximum monoisotopic mass (Da). E.g. 1000.0. |
| organism_names | list[string] \| None | None | Restrict to metabolites reachable by these organisms (case-insensitive on `preferred_name`). UNION semantics — a metabolite reached by ANY listed organism qualifies. Joined via `Organism_has_metabolite` (catalysis OR transport post-TCDB). E.g. ['Prochlorococcus MED4']. `not_found.organism_names` lists any unknown names. |
| pathway_ids | list[string] \| None | None | Filter by KEGG pathway membership (`KeggTerm.id`). E.g. ['kegg.pathway:ko00910'] for nitrogen metabolism. Joined via `Metabolite_in_pathway` (transport-extended post-TCDB; 395 distinct pathways are metabolite-reachable). `not_found.pathway_ids` lists any IDs that don't exist as a KeggTerm. |
| evidence_sources | list[string ('metabolism', 'transport', 'metabolomics')] \| None | None | Filter by evidence path. Set-membership ANY semantics — ['transport'] returns transport-only AND dual (1,097 today). Valid values: 'metabolism' (catalysis-reachable), 'transport' (TCDB-curated substrate). `'metabolomics'` is accepted as a filter value for forward-compat with the future metabolomics-DM spec; no row matches yet. Other values raise at the MCP boundary (Pydantic Literal validation). |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include heavy-text and structural-fingerprint fields (inchikey, smiles, mnxm_id, hmdb_id, pathway_names). |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

## Response format

### Envelope

```expected-keys
total_entries, total_matching, top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, mass_stats, by_measurement_coverage, score_max, score_median, returned, offset, truncated, not_found, results
```

- **total_entries** (int): Total Metabolite nodes in KG (unfiltered, 3,025 today)
- **total_matching** (int): Metabolites matching filters
- **top_organisms** (list[MetTopOrganism]): Top 10 organisms by metabolite count (within matched set), sorted desc
- **top_metabolite_pathways** (list[MetTopPathway]): Top 10 pathways by metabolite count (within matched set), sorted desc. Metabolite-pathway rollup (distinct from KO-pathway annotations on `genes_by_ontology`).
- **by_evidence_source** (list[MetEvidenceSourceBreakdown]): Frequency of evidence_sources values across matched set. Today: at most 2 entries (metabolism, transport).
- **xref_coverage** (MetXrefCoverage): Cross-ref ID coverage within matched set
- **mass_stats** (MetMassStats): Mass distribution within matched set
- **by_measurement_coverage** (MetMeasurementCoverage): Metabolomics measurement coverage rollup across matched metabolites. Two sub-rollups: by_paper_count (frequency by measured_paper_count value) + by_compartment (frequency by measured_compartments value). Phase 1 plumbing — spec §6.6.
- **score_max** (float | None): Max Lucene score (only with search)
- **score_median** (float | None): Median Lucene score (only with search)
- **returned** (int): Metabolites in this response
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if total_matching > returned
- **not_found** (MetNotFound): Per-filter buckets for unknown input IDs

### Per-result fields

| Field | Type | Description |
|---|---|---|
| metabolite_id | string | Full prefixed ID (e.g. 'kegg.compound:C00031'). 85% kegg.compound, 15% chebi (TCDB-only substrates). |
| name | string | Metabolite name (e.g. 'D-Glucose', 'L-Glutamate') |
| formula | string \| None (optional) | Hill-notation chemical formula (e.g. 'C6H12O6'). Null on ~9% of metabolites (mostly TCDB-curated generic substrates). |
| elements | list[string] (optional) | Sorted unique element symbols present in formula (e.g. ['C','H','O']). Empty when formula is null. Filter on this — never on `formula` substring (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N'). Presence list (no atom counts; stoichiometry lives in `formula`). |
| mass | float \| None (optional) | Monoisotopic mass in Da (e.g. 180.156). Null on ~22% of metabolites. |
| gene_count | int (optional) | Distinct genes reachable via Gene → Reaction → Metabolite OR Gene → TcdbFamily → Metabolite (UNION post-TCDB; e.g. 320 for glucose). When > 0, drill in via genes_by_metabolite(metabolite_ids=[id], organism=...). All metabolites have gene_count > 0 today (post-2026-05-03 transport-arm fix); the future metabolomics-DM spec will introduce metabolites measured without any gene path, which will surface here with gene_count=0 — 0 ≠ 'absent from KG'. |
| organism_count | int (optional) | Distinct organisms reaching this metabolite via any chemistry path (e.g. 31 for ATP). When > 0, narrow with organism_names filter. |
| transporter_count | int (optional) | Distinct `tc_specificity` leaf TcdbFamily nodes annotated as transporting this metabolite (e.g. 17 for glucose, 229 for sodium). Scoped to leaves so the count reflects 'actual transporter systems' rather than counting ancestor families that inherit the substrate via the 2026-05-03 rollup. Source: TCDB-CAZy ontology. |
| evidence_sources | list[string] (optional) | Path provenance — values from {'metabolism', 'transport'}. 'metabolism' = at least one Reaction in KG involves this compound; 'transport' = at least one TcdbFamily curates this as substrate. 'metabolomics' is reserved for the future metabolomics-DM spec — no row carries it today. E.g. ['metabolism', 'transport']. |
| chebi_id | string \| None (optional) | ChEBI ID (raw numeric, e.g. '4167'). Populated on 90% of metabolites overall — 100% of the 452 chebi:-IDed transport-only metabolites (extracted from the ID itself), plus the kegg.compound:-IDed metabolites that cross-ref ChEBI. |
| pathway_ids | list[string] (optional) | KEGG pathway memberships (e.g. ['kegg.pathway:ko00010', 'kegg.pathway:ko01100']). Empty when no Metabolite_in_pathway edges. Drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...). |
| pathway_count | int (optional) | Distinct count of KEGG pathways this metabolite is in (e.g. 5). Routing signal — when > 0, drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...) for genes annotated to those pathways. Equal to size(pathway_ids). |
| measured_assay_count | int (optional) | Distinct MetaboliteAssay edges anchored to this metabolite (precomputed Metabolite.measured_assay_count). Non-zero on 149 of 3230 metabolites today (~5% coverage; KG release 2026-05-06). When > 0, the metabolite has experimental measurement coverage. |
| measured_paper_count | int (optional) | Distinct papers (1, 2, or 3) measuring this metabolite (precomputed). Non-zero on 149 metabolites today: 5 measured by all 3 papers, 25 by 2, 119 by 1. |
| measured_organisms | list[string] (optional) | Organism preferred_names with at least one MetaboliteAssay anchored to this metabolite. Populated when measured_assay_count > 0; [] otherwise. |
| measured_compartments | list[string] (optional) | Wet-lab compartments observed for this metabolite (subset of {'whole_cell', 'extracellular', 'vesicle'}). Populated by post-import on all 149 measured metabolites; [] on the 3081 unmeasured. Use len(measured_compartments) >= 1 to filter for measurement-anchored rows. |
| score | float \| None (optional) | Lucene relevance score (only with `search`). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| inchikey | string \| None (optional) | InChIKey structural fingerprint (e.g. 'WQZGKKKJIJFFOK-GASJEMHNSA-N'). Verbose only. |
| smiles | string \| None (optional) | SMILES structural string (e.g. 'OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O'). Verbose only. |
| mnxm_id | string \| None (optional) | MetaNetX canonical ID (e.g. 'MNXM1364061'). Verbose only — populated on 100% of metabolites. |
| hmdb_id | string \| None (optional) | HMDB ID (e.g. 'HMDB0304632'). Verbose only — populated on 47%. |
| pathway_names | list[string] \| None (optional) | Pathway names aligned with pathway_ids (verbose only). |

## Few-shot examples

### Example 1: All N-bearing metabolites in MED4 (the N-source workflow primitive)

```example-call
list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"], limit=5)
```

### Example 2: Pathway-anchored — metabolites in nitrogen metabolism

```example-call
list_metabolites(pathway_ids=["kegg.pathway:ko00910"], limit=10)
```

### Example 3: Cross-organism survey — metabolites both partners reach

```example-call
list_metabolites(organism_names=["Prochlorococcus MED4", "Alteromonas macleodii MIT1002"], summary=True)
```

### Example 4: Lucene search by name

```example-call
list_metabolites(search_text="glucose", limit=3)
```

### Example 5: Transport-only metabolites (TCDB-curated substrates without local catalysis)

```example-call
list_metabolites(evidence_sources=["transport"], summary=True)
```

### Example 6: Measured metabolites — measurement coverage envelope

```example-call
list_metabolites(evidence_sources=["metabolomics"], summary=True)
```

```example-response
{"total_entries": 3218, "total_matching": 107,
 "by_measurement_coverage": {
   "by_paper_count": [{"paper_count": 1, "n": 99}, {"paper_count": 2, "n": 8}],
   "by_compartment": [{"compartment": "whole_cell", "n": 99}, {"compartment": "extracellular", "n": 92}]
 },
 "returned": 0, "truncated": true, "offset": 0, "results": []}
```

### Example 7: Multi-step — find N-metabolites then drill into catalysts

```
Step 1: list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"], limit=10)
        → extract metabolite_ids of interest

Step 2: genes_by_metabolite(metabolite_ids=[chosen_ids], organism="Prochlorococcus MED4")
        → catalysing genes per metabolite
```

### Example 8: Currency-cofactor strip — exclude ATP/ADP/NADH/NADPH/H2O when top_metabolites is dominated by them

```example-call
list_metabolites(
  organism_names=["Prochlorococcus MED4"],
  exclude_metabolite_ids=[
    "kegg.compound:C00002",  # ATP
    "kegg.compound:C00008",  # ADP
    "kegg.compound:C00004",  # NADH
    "kegg.compound:C00005",  # NADPH
    "kegg.compound:C00001",  # H2O
  ],
  summary=True,
)

```

## Chaining patterns

```
list_organisms (per-row metabolite_count > 0) → list_metabolites(organism_names=[...])
list_metabolites → genes_by_metabolite(metabolite_ids=[...], organism=...)
list_metabolites (per-row pathway_ids) → genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...)
differential_expression_by_gene → gene_metabolic_role(metabolite_elements=['N']) → list_metabolites for chemistry context
list_metabolites (per-row `measured_assay_count > 0`) → assays_by_metabolite(metabolite_ids=[...]) — reverse lookup of all measurement evidence (numeric + boolean) for the measured compounds (cross-organism by default).
```

## Common mistakes

- Direction-agnostic. Joining through Reaction_has_metabolite (catalysis) and Tcdb_family_transports_metabolite (transport) does NOT distinguish substrates from products. KEGG equation order is arbitrary. Layer DE direction (`differential_expression_by_gene`) and functional annotation to disambiguate.

- elements is presence-only, AND-of. ['N','P'] requires BOTH N and P to be present. Use the `elements` filter — never substring-match on `formula` (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N').

- gene_count = 0 does not mean the metabolite is absent from the KG. As of the 2026-05-03 transport-arm fix every Metabolite has gene_count > 0; the future metabolomics-DM spec will reintroduce gene_count=0 (measured-only metabolites with no gene path).

- organism_names with multiple values is UNION, not intersection. To find metabolites BOTH organisms reach, run two single-org calls and intersect by metabolite_id (or filter per-row by organism_count and inspect `m.organism_names` for the full UNION list).

- metaboliteFullText covers Metabolite.name only — NOT formula. For element/composition queries, use `elements` (presence list).

- evidence_sources accepts 'metabolomics' as forward-compat for the future metabolomics-DM spec; no row matches it today.

- `measured_compartments` is populated on all 107 measured metabolites (defaults to `[]` on the 3111 unmeasured); use `len(m['measured_compartments']) >= 1` to filter for measurement-anchored rows. Same metabolite measured in both whole_cell and extracellular returns one row with `measured_compartments=['extracellular','whole_cell']` (sorted), not two rows — Metabolite is compartment-agnostic per KG-MET-002.

- When the `top_metabolites` rollup is dominated by ATP / ADP / NADH / NADPH / H2O, pass `exclude_metabolite_ids=[<kegg.compound:Cxxxxx>]` to strip cofactor noise. Set-difference semantics with `metabolite_ids` — exclude wins on overlap. KG namespace is `kegg.compound:` (not `chebi:`).

- Per-row `elements` is a presence list — no atom counts per compound. Stoichiometry lives in `formula`. Filter on `elements` (e.g. `elements=['N']` for N-bearing compounds), never on `formula` substring (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N').

```mistake
list_metabolites(elements=['N'], gene_count_min=1)  # gene_count_min isn't a param
```

```correction
list_metabolites(elements=['N'])  # then filter rows in code by gene_count > 0
```

```mistake
list_metabolites(organism_names=['MED4'])  # short name doesn't match
```

```correction
list_metabolites(organism_names=['Prochlorococcus MED4'])  # full preferred_name
```

## Package import equivalent

```python
from multiomics_explorer import list_metabolites

result = list_metabolites()
# returns dict with keys: total_entries, total_matching, top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, mass_stats, by_measurement_coverage, score_max, score_median, offset, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
