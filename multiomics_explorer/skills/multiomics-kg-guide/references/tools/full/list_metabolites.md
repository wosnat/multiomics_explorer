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

## Response format

### Envelope

```expected-keys
total_entries, total_matching, top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, mass_stats, by_measurement_coverage, score_max, score_median, returned, offset, truncated, not_found, resolved_aliases, warnings, results
```

- **total_entries** (int): Total Metabolite nodes in KG (unfiltered).
- **total_matching** (int): Metabolites matching filters.
- **top_organisms** (list[MetTopOrganism]): Top 10 organisms by metabolite count (within matched set), sorted desc.
- **top_metabolite_pathways** (list[MetTopPathway]): Top 10 pathways by metabolite count (within matched set), sorted desc. Metabolite-pathway rollup (distinct from KO-pathway annotations on `genes_by_ontology`).
- **by_evidence_source** (list[MetEvidenceSourceBreakdown]): Frequency of evidence_sources values across matched set. Bounded by the {metabolism, transport, metabolomics} domain.
- **xref_coverage** (MetXrefCoverage): Cross-ref ID coverage within matched set.
- **mass_stats** (MetMassStats): Mass distribution within matched set.
- **by_measurement_coverage** (MetMeasurementCoverage): Metabolomics measurement coverage rollup across matched metabolites. Two sub-rollups: by_paper_count (frequency by measured_paper_count value) + by_compartment (frequency by measured_compartments value).
- **score_max** (float | None): Max Lucene score (only with `search_text`).
- **score_median** (float | None): Median Lucene score (only with `search_text`).
- **returned** (int): Metabolites in this response.
- **offset** (int): Offset into full result set.
- **truncated** (bool): True if total_matching > returned.
- **not_found** (MetNotFound): Per-filter buckets for unknown input IDs.
- **resolved_aliases** (object): Bare / xref metabolite inputs coerced to canonical IDs, `{input: [canonical, ...]}` — only coerced entries, across both `metabolite_ids` and `exclude_metabolite_ids`. A list longer than 1 is a collision (expanded to all; see `warnings`).
- **warnings** (list[string]): Diagnostic strings, e.g. a bare ID that resolved to more than one metabolite (expanded to all — pass the canonical id to narrow), a `metabolite_ids` / `exclude_metabolite_ids` entry matching no recognized id pattern at all (likely a NAME — resolve it with `search_text` instead), or an `elements` entry that isn't a recognized symbol or name (see `not_found.elements`).

### Per-result fields

| Field | Type | Description |
|---|---|---|
| metabolite_id | string | Full prefixed ID (e.g. 'kegg.compound:C00031'). Most carry the kegg.compound: namespace; a smaller set carry chebi: (TCDB-curated transport-only substrates). |
| name | string | Metabolite name (e.g. 'D-Glucose', 'L-Glutamate'). |
| formula | string \| None (optional) | Hill-notation chemical formula (e.g. 'C6H12O6'). Null on a minority of metabolites (mostly TCDB-curated generic substrates). |
| elements | list[string] (optional) | Sorted unique element symbols present in formula (e.g. ['C','H','O']). Empty when formula is null. Filter on this — never on `formula` substring (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N'). Presence list (no atom counts; stoichiometry lives in `formula`). |
| mass | float \| None (optional) | Monoisotopic mass in Da (e.g. 180.156). Null on a minority of metabolites. |
| catalyst_gene_count | int (optional) | Distinct catalyst genes via Gene → Reaction → Metabolite (catalysis arm only). Transport-only metabolites read 0 here with transporter_gene_count > 0; evidence_sources==['metabolomics'] means no gene path at all. Drill in via genes_by_metabolite. |
| organism_count | int (optional) | Distinct organisms reaching this metabolite via any chemistry path. When > 0, narrow with organism_names filter. |
| transporter_count | int (optional) | Distinct transporter systems (TcdbFamily nodes) whose substrate edge to this metabolite is substrate_depth='most_specific'. Systems, not genes — pair with transporter_gene_count and catalyst_gene_count; drill via genes_by_metabolite. |
| transporter_gene_count | int (optional) | Distinct genes (all organisms) whose deepest TCDB attachment transports this metabolite (precomputed Metabolite.transporter_gene_count). catalyst_gene_count=0 with transporter_gene_count>0 = transport-only; drill via genes_by_metabolite. |
| evidence_sources | list[string] (optional) | Path provenance — values from {'metabolism', 'transport', 'metabolomics'}. 'metabolism' = at least one Reaction in KG involves this compound; 'transport' = at least one TcdbFamily curates this as substrate; 'metabolomics' = at least one MetaboliteAssay measures this compound. E.g. ['metabolism', 'transport']. |
| chebi_id | string \| None (optional) | ChEBI ID (raw numeric, e.g. '4167'). Populated on most metabolites — 100% of chebi:-IDed transport-only metabolites (extracted from the ID itself), plus the kegg.compound:-IDed metabolites that cross-ref ChEBI. |
| pathway_ids | list[string] (optional) | KEGG pathway memberships (e.g. ['kegg.pathway:ko00010', 'kegg.pathway:ko01100']). Empty when no Metabolite_in_pathway edges. Drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...). |
| pathway_count | int (optional) | Distinct count of KEGG pathways this metabolite is in (e.g. 5). Routing signal — when > 0, drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...) for genes annotated to those pathways. Equal to size(pathway_ids). |
| measured_assay_count | int (optional) | Distinct MetaboliteAssay edges anchored to this metabolite (precomputed Metabolite.measured_assay_count). When > 0, the metabolite has experimental measurement coverage. |
| measured_paper_count | int (optional) | Distinct papers measuring this metabolite (precomputed). Non-zero on metabolites with metabolomics evidence. |
| measured_organisms | list[string] (optional) | Organism preferred_names with at least one MetaboliteAssay anchored to this metabolite. Populated when measured_assay_count > 0; [] otherwise. |
| measured_compartments | list[string] (optional) | Wet-lab compartments observed for this metabolite (subset of {'whole_cell', 'extracellular', 'vesicle'}). Empty on unmeasured metabolites — use len(measured_compartments) >= 1 to filter for measurement-anchored rows. |
| score | float \| None (optional) | Lucene relevance score (only with `search_text`). |

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

### Example 5: Transport-only metabolites (TCDB substrates without local catalysis)

```example-call
list_metabolites(evidence_sources=["transport"], summary=True)
```

### Example 6: Transport-only metabolite by ID — reading the two gene counts together

```example-call
list_metabolites(metabolite_ids=["chebi:14313"])
```

```example-response
{
  "total_entries": 3356,
  "total_matching": 1,
  "top_organisms": [
    {"organism_name": "Alteromonas macleodii AD45", "count": 1},
    {"organism_name": "Alteromonas macleodii ATCC27126", "count": 1},
    {"organism_name": "Alteromonas macleodii BGP6", "count": 1},
    {"organism_name": "Alteromonas macleodii BS11", "count": 1},
    {"organism_name": "Alteromonas macleodii EZ55", "count": 1},
    ...
  ],
  "top_metabolite_pathways": [],
  "by_evidence_source": [{"evidence_source": "transport", "count": 1}],
  "xref_coverage": {"with_chebi": 1, "with_hmdb": 0, "with_mnxm": 1},
  "mass_stats": {"mass_min": 180.156, "mass_median": 180.156, "mass_max": 180.156},
  "by_measurement_coverage": {"by_paper_count": [{"paper_count": 0, "count": 1}], "by_compartment": []},
  "score_max": null,
  "score_median": null,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": []},
  "resolved_aliases": {},
  "warnings": [],
  "results": [
    {
      "metabolite_id": "chebi:14313",
      "name": "glucose",
      "formula": "C6H12O6",
      "elements": ["C", "H", "O"],
      "mass": 180.156,
      "catalyst_gene_count": 0,
      "organism_count": 43,
      "transporter_count": 18,
      "transporter_gene_count": 3091,
      "evidence_sources": ["transport"],
      "chebi_id": "14313",
      "pathway_ids": [],
      "pathway_count": 0,
      "measured_assay_count": 0,
      "measured_paper_count": 0,
      "measured_organisms": [],
      "measured_compartments": []
    }
  ]
}
```

### Example 7: Measured metabolites — measurement coverage envelope

```example-call
list_metabolites(evidence_sources=["metabolomics"], summary=True)
```

```example-response
{
  "total_entries": 3356,
  "total_matching": 149,
  "top_organisms": [
    {"organism_name": "Prochlorococcus MIT9313", "count": 146},
    {"organism_name": "Prochlorococcus MIT9301", "count": 132},
    {"organism_name": "Prochlorococcus MIT9312", "count": 132},
    {"organism_name": "Prochlorococcus MIT0801", "count": 128},
    {"organism_name": "Pseudomonas putida KT2440", "count": 123},
    ...
  ],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko01100",
      "metabolite_pathway_name": "Metabolic pathways",
      "count": 119
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01110",
      "metabolite_pathway_name": "Biosynthesis of secondary metabolites",
      "count": 64
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01240",
      "metabolite_pathway_name": "Biosynthesis of cofactors",
      "count": 47
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01120",
      "metabolite_pathway_name": "Microbial metabolism in diverse environments",
      "count": 38
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko02010",
      "metabolite_pathway_name": "ABC transporters",
      "count": 38
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "metabolomics", "count": 149},
    {"evidence_source": "metabolism", "count": 117},
    {"evidence_source": "transport", "count": 103}
  ],
  "xref_coverage": {"with_chebi": 143, "with_hmdb": 128, "with_mnxm": 140},
  "mass_stats": {"mass_min": 89.094, "mass_median": 175.188, "mass_max": 1347.385},
  "by_measurement_coverage": {
    "by_paper_count": [{"paper_count": 1, "count": 119}, {"paper_count": 2, "count": 25}, {"paper_count": 3, "count": 5}],
    "by_compartment": [
      {"compartment": "extracellular", "count": 92},
      {"compartment": "vesicle", "count": 69},
      {"compartment": "whole_cell", "count": 149}
    ]
  },
  "score_max": null,
  "score_median": null,
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": []},
  "resolved_aliases": {},
  "warnings": [],
  "results": []
}
```

### Example 8: Multi-step — find N-metabolites then drill into catalysts

```
Step 1: list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"], limit=10)
        → extract metabolite_ids of interest

Step 2: genes_by_metabolite(metabolite_ids=[chosen_ids], organism="Prochlorococcus MED4")
        → catalysing genes per metabolite
```

### Example 9: Currency-cofactor strip — exclude ATP/ADP/NADH/NADPH/H2O when top_metabolites is dominated by them

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
list_organisms (per-row catalyzed_metabolite_count > 0) → list_metabolites(organism_names=[...])
list_metabolites → genes_by_metabolite(metabolite_ids=[...], organism=...)
list_metabolites (per-row `transporter_gene_count > 0`) → genes_by_metabolite(metabolite_ids=[...], organism=..., evidence_sources=['transport']) — distinct genes in the transport rows, summed over organisms, equal transporter_gene_count
list_metabolites (per-row pathway_ids) → genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...)
differential_expression_by_gene → metabolites_by_gene(metabolite_elements=['N']) → list_metabolites for chemistry context
list_metabolites (per-row `measured_assay_count > 0`) → assays_by_metabolite(metabolite_ids=[...]) — reverse lookup of all measurement evidence (numeric + boolean) for the measured compounds (cross-organism by default).
```

## Common mistakes

- Direction-agnostic — KEGG equation order is unreliable upstream, so joins through Reaction_has_metabolite (catalysis) and Tcdb_family_transports_metabolite (transport) do NOT distinguish substrates from products. Layer DE direction (`differential_expression_by_gene`) and functional annotation to disambiguate. See docs://analysis/metabolites.

- catalyst_gene_count counts the catalysis arm only (genes reaching the metabolite via Gene → Reaction → Metabolite). catalyst_gene_count = 0 does NOT mean metabolomics-only: transport-only metabolites (TCDB substrates with no local catalysis) also read 0. Discriminate via the paired counts: catalyst_gene_count = 0 with `transporter_gene_count > 0` is transport-only; both 0 with `evidence_sources == ['metabolomics']` is measurement-only (no gene path). `transporter_gene_count` counts distinct genes over their deepest TCDB attachments, all organisms — it equals the distinct genes `genes_by_metabolite` returns in transport rows, summed over organisms.

- organism_names with multiple values is UNION, not intersection. To find metabolites BOTH organisms reach, run two single-org calls and intersect by `metabolite_id` (per-row `organism_count` tells you how many organisms reach a metabolite, but not which — the envelope `top_organisms` rollup is the only per-organism breakdown).

- `search_text` is a Lucene search over the metabolite name only — NOT the formula. For element/composition queries, use `elements` (presence list).

```mistake
list_metabolites(metabolite_ids=['glutamate'])  # a name, not an id
```

```correction
`metabolite_ids` takes IDs only (canonical or a recognized bare/xref
form) — a metabolite NAME matches no known id pattern, so it's forwarded
verbatim, lands in `not_found.metabolite_ids`, and a `warnings` entry
points at `search_text` to resolve the name first.

```

```mistake
list_metabolites(elements=['Nitrogen'])  # or lowercase 'n'/'fe'
```

```correction
Both are accepted and normalized silently to the correct symbol (`N`,
`Fe`) for the ~12 elements this KG's chemistry layer carries. An
unrecognized element (not a known symbol or full name) is dropped from
the filter, reported in `not_found.elements`, and adds a `warnings` entry.

```

- evidence_sources='metabolomics' selects metabolites measured by a MetaboliteAssay. Drill in via list_metabolite_assays(metabolite_ids=[...]) or assays_by_metabolite to inspect the measurement evidence.

- Same metabolite measured in both whole_cell and extracellular returns one row with `measured_compartments=['extracellular','whole_cell']` (sorted), not two rows — Metabolite is compartment-agnostic.

- When a roster is dominated by ATP / ADP / NADH / NADPH / H2O (currency cofactors that every organism reaches), pass `exclude_metabolite_ids=[<kegg.compound:Cxxxxx>]` to strip them — the same list works on the gene-anchored `metabolites_by_gene`, whose `top_metabolites` rollup is where the noise usually shows first. KG namespace is `kegg.compound:` (not `chebi:`).

```mistake
list_metabolites(elements=['N'], catalyst_gene_count_min=1)  # catalyst_gene_count_min isn't a param
```

```correction
list_metabolites(elements=['N'])  # then filter rows in code by catalyst_gene_count > 0
```

```mistake
list_metabolites(organism_names=['MED4'])  # short name doesn't match
```

```correction
list_metabolites(organism_names=['Prochlorococcus MED4'])  # full preferred_name
```

```mistake
list_metabolites(metabolite_ids=['C00064'])  # then treating `C00064` in `not_found` as 'no such metabolite'
```

```correction
Bare / xref metabolite IDs on `metabolite_ids` / `exclude_metabolite_ids` are resolved via
the node's cross-references before the query runs: `C00064` →
`kegg.compound:C00064`, `CHEBI:17234` / `17234` → the `chebi_id` match,
`HMDB0000122` → `hmdb_id`, `MNXM1095050` → `mnxm_id`. Canonical forms
(`kegg.compound:` / `chebi:` / `mnx:`) pass through untouched. Coerced
inputs are listed in envelope `resolved_aliases` (`{input: [canonical, ...]}`).
CHEBI / HMDB / MNXM xrefs are not unique — an ambiguous input expands to
ALL matching metabolites and appends a `warnings` entry; pass the canonical
id to narrow. Unresolved inputs stay verbatim and surface in `not_found`
in the form you passed. The dedicated exact-xref filters (`kegg_compound_ids`, `chebi_ids`, `hmdb_ids`, `mnxm_ids`) are a separate, uncoerced mechanism — they match the xref property directly.

```

- See `docs://analysis/metabolites` for the 3 source pipelines decision tree (metabolism / transport / metabolomics) and `docs://guide/concepts` for the chemistry layer overview.

## Package import equivalent

```python
from multiomics_explorer import list_metabolites

result = list_metabolites()
# returns dict with keys: total_entries, total_matching, top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, mass_stats, by_measurement_coverage, score_max, score_median, returned, offset, truncated, not_found, resolved_aliases, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
