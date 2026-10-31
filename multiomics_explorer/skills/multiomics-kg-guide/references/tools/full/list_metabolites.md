# list_metabolites

## What it does

Browse the chemistry layer — KEGG metabolism, TCDB transport substrates, GO transport targets, and compounds measured by an assay.

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
| elements | list[string] \| None | None | Element-presence filter (Hill-notation symbols, e.g. 'Fe', 'N'). AND of presence — ['N', 'P'] matches metabolites containing BOTH. A case-insensitive symbol ('n', 'fe') or a full element name ('Nitrogen') for one of the 15 elements this KG's chemistry layer carries (C, H, N, O, P, S, Fe, Mg, Mn, Zn, Cu, Co, Mo, Ni, Se) is normalized silently; anything else is dropped from the filter and reported in `not_found.elements` with a warning. Use this rather than substring-matching on `formula` (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N'). Empty/null formula metabolites never match. |
| min_mass | float \| None | None | Minimum monoisotopic mass (Da). Excludes metabolites with null `mass` (~22%). E.g. 60.0. |
| max_mass | float \| None | None | Maximum monoisotopic mass (Da). E.g. 1000.0. |
| organism_names | list[string] \| None | None | Metabolites reached by ANY of these organisms (case-insensitive `preferred_name`), by any route. With `evidence_sources`, a listed organism must reach it by one of those routes. E.g. ['Prochlorococcus MED4']. Unknown: `not_found.organism_names`. |
| pathway_ids | list[string] \| None | None | Filter by KEGG pathway membership (`KeggTerm.id`). E.g. ['kegg.pathway:ko00910'] for nitrogen metabolism. Joined via `Metabolite_in_pathway`. `not_found.pathway_ids` lists unknown IDs. |
| evidence_sources | list[string ('metabolism', 'transport', 'metabolomics', 'go_transport')] \| None | None | Filter by evidence path (ANY): 'metabolism', 'transport' (TCDB substrate), 'metabolomics' (measured), 'go_transport'. Alone = metabolite-level ('transport' = some TCDB system lists it); with `organism_names` = that organism's route. |
| structure_kind | list[string] \| None | None | Structure kind(s) (OR): 'defined' (one molecule), 'generic' (a compound class) or 'polymer'. E.g. ['defined'] drops generic substrates like 'amino acid'. Values: list_filter_values('structure_kind'). |
| kegg_functional_categories | list[string] \| None | None | KEGG br08001 categories (OR). Hand-curated and partial: only ~10% of metabolites are listed, so a missing category means 'KEGG did not list it', not 'not in it' (fumarate is unclassified). Values: list_filter_values('kegg_functional_category'). |
| kegg_brite_classes | list[string] \| None | None | Classes from 7 other KEGG compound BRITE trees, as 'Tree: Class' (OR), e.g. 'Lipids: Fatty acyls'. Curated and partial (~20% of metabolites): unlisted = 'KEGG did not list it', not 'not in it'. Values: list_filter_values('kegg_brite_class'). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's full page, docs://tools/{tool}/full. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Response format

### Envelope

```expected-keys
total_entries, total_matching, top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, mass_stats, by_measurement_coverage, by_structure_kind, by_kegg_functional_category, by_kegg_brite_class, score_max, score_median, returned, offset, truncated, not_found, resolved_aliases, warnings, results
```

- **total_entries** (int): Total Metabolite nodes in KG (unfiltered).
- **total_matching** (int): Metabolites matching filters.
- **top_organisms** (list[MetTopOrganism]): Top 10 organisms by metabolite count (within matched set), sorted desc. With evidence_sources, an organism counts only by those routes.
- **top_metabolite_pathways** (list[MetTopPathway]): Top 10 pathways by metabolite count (within matched set), sorted desc. Metabolite-pathway rollup (distinct from KO-pathway annotations on `genes_by_ontology`).
- **by_evidence_source** (list[MetEvidenceSourceBreakdown]): Frequency of evidence_sources values across matched set. Bounded by the {metabolism, transport, metabolomics, go_transport} domain.
- **xref_coverage** (MetXrefCoverage): Cross-ref ID coverage within matched set.
- **mass_stats** (MetMassStats): Mass distribution within matched set.
- **by_measurement_coverage** (MetMeasurementCoverage): Metabolomics measurement coverage rollup across matched metabolites. Two sub-rollups: by_paper_count (frequency by measured_paper_count value) + by_compartment (frequency by measured_compartments value).
- **by_structure_kind** (list[MetStructureKindBucket]): Matched metabolites per structure_kind ('defined' / 'generic' / 'polymer'), sorted desc.
- **by_kegg_functional_category** (list[MetKeggFunctionalCategoryBucket]): Matched metabolites per KEGG br08001 category, sorted desc, always ending with 'not classified' (KEGG did not list them; not a filter value). Unlisted is not 'in none of these'.
- **by_kegg_brite_class** (list[MetKeggBriteClassBucket]): Matched metabolites per 'Tree: Class' from 7 KEGG compound BRITE trees, sorted desc, always ending with 'not classified' (KEGG did not list them; not a filter value).
- **score_max** (float | None): Max Lucene score (only with `search_text`).
- **score_median** (float | None): Median Lucene score (only with `search_text`).
- **returned** (int): Metabolites in this response.
- **offset** (int): Offset into full result set.
- **truncated** (bool): True if total_matching > returned.
- **not_found** (MetNotFound): Per-filter buckets for unknown input IDs.
- **resolved_aliases** (object): Metabolite inputs resolved to a different canonical ID (bare, xref, secondary or retired ids), `{input: [canonical]}`, across `metabolite_ids` and `exclude_metabolite_ids`. Inputs already canonical are not listed.
- **warnings** (list[string]): Diagnostics: a removed compound (names the id now holding its measurements), a chemical role rather than a metabolite, an id-shaped NAME (use `search_text`), an unknown vocabulary value, or an unrecognized `elements` entry.
- **no_formula_excluded** (int | None): Metabolites passing every other filter but dropped by `elements` because they have no formula (generic classes like 'amino acid' never match an element filter). Null when no `elements` filter.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| metabolite_id | string | Full prefixed ID (e.g. 'kegg.compound:C00031'). Most carry the kegg.compound: namespace; a smaller set carry chebi: (TCDB-curated transport-only substrates). |
| name | string | Metabolite name (e.g. 'D-Glucose', 'L-Glutamate'). |
| formula | string \| None (optional) | Hill-notation chemical formula (e.g. 'C6H12O6'). Null on a minority of metabolites (mostly TCDB-curated generic substrates). |
| elements | list[string] (optional) | Sorted unique element symbols present in formula (e.g. ['C','H','O']). Empty when formula is null. Filter on this — never on `formula` substring (Hill notation has element-clash footguns: 'Cl' contains 'C', 'Na' contains 'N'). Presence list (no atom counts; stoichiometry lives in `formula`). |
| mass | float \| None (optional) | Monoisotopic mass in Da (e.g. 180.156). Null on a minority of metabolites. |
| catalyst_gene_count | int (optional) | Distinct catalyst genes via Gene → Reaction → Metabolite (catalysis arm only). Transport-only metabolites read 0 here with transporter_gene_count > 0; evidence_sources==['metabolomics'] means no gene path at all. Drill in via genes_by_metabolite. |
| organism_count | int (optional) | Distinct organisms reaching this metabolite via KEGG reactions or TCDB transport only; GO reach is go_transport_organism_count. The organism_names filter matches either. |
| transporter_count | int (optional) | Distinct TCDB systems curated with this metabolite that some gene points at directly (tcdb_gate='direct'). Systems, not genes — pair with transporter_gene_count and catalyst_gene_count; drill via genes_by_metabolite. |
| transporter_gene_count | int (optional) | Distinct genes (all organisms) with a direct TCDB system curated with this metabolite (precomputed Metabolite.transporter_gene_count). catalyst_gene_count=0 with transporter_gene_count>0 = transport-only; drill via genes_by_metabolite. |
| evidence_sources | list[string] (optional) | Path provenance, any of 'metabolism', 'transport', 'metabolomics', 'go_transport' (e.g. ['metabolism', 'transport']). Definitions: list_filter_values(filter_type='evidence_source'). |
| go_transport_organism_names | list[string] \| None (optional) | Organisms with a gene directly annotated to a GO transport term for this target. Absent = no directly annotated gene path, not 'no GO transport edge'. Drill via genes_by_metabolite(evidence_sources=['go_transport']). |
| go_transport_organism_count | int \| None (optional) | Number of organisms in go_transport_organism_names. Absent = no directly annotated gene path, not 'no GO transport edge'. |
| chebi_id | string \| None (optional) | ChEBI ID (raw numeric, e.g. '4167'). Populated on most metabolites — 100% of chebi:-IDed transport-only metabolites (extracted from the ID itself), plus the kegg.compound:-IDed metabolites that cross-ref ChEBI. |
| pathway_ids | list[string] (optional) | KEGG pathway memberships (e.g. ['kegg.pathway:ko00010', 'kegg.pathway:ko01100']). Empty when no Metabolite_in_pathway edges. Drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...). |
| pathway_count | int (optional) | Distinct count of KEGG pathways this metabolite is in (e.g. 5). Routing signal — when > 0, drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...) for genes annotated to those pathways. Equal to size(pathway_ids). |
| measured_assay_count | int (optional) | Distinct MetaboliteAssay edges anchored to this metabolite (precomputed Metabolite.measured_assay_count). When > 0, the metabolite has experimental measurement coverage. |
| measured_paper_count | int (optional) | Distinct papers measuring this metabolite (precomputed). Non-zero on metabolites with metabolomics evidence. |
| measured_organisms | list[string] (optional) | Organism preferred_names with at least one MetaboliteAssay anchored to this metabolite. Populated when measured_assay_count > 0; [] otherwise. |
| measured_compartments | list[string] (optional) | Wet-lab compartments observed for this metabolite (subset of {'whole_cell', 'extracellular', 'vesicle'}). Empty on unmeasured metabolites — use len(measured_compartments) >= 1 to filter for measurement-anchored rows. |
| score | float \| None (optional) | Lucene relevance score (only with `search_text`). |
| structure_kind | string \| None (optional) | 'defined' (one molecule), 'generic' (a compound class, e.g. 'amino acid') or 'polymer'. Generic / polymer entries carry a generic formula (R or * groups) and no mass. Values: list_filter_values('structure_kind'). |
| kegg_functional_categories | list[string] \| None (optional) | KEGG br08001 categories this metabolite is listed under. Absent = KEGG did not list it (~90% of metabolites), not 'none apply'. Curated, functional headings (amines sit under Peptides). |
| kegg_brite_classes | list[string] \| None (optional) | 'Tree: Class' from 7 KEGG compound BRITE trees (lipids, phytochemicals, glycosides, pesticides, toxins, endocrine disruptors, bioactive peptides). Absent = KEGG did not list it (~80% of metabolites). |
| stereo_relatives | list[MetaboliteStereoRelative] \| None (optional) | Other stereo forms of this metabolite (1 hop), e.g. Cysteine -> L-Cysteine, D-Cysteine. Counts never combine across stereo forms: a 0 here can be non-zero on a relative. Absent when none. |

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

### Example 3: Cross-organism survey — metabolites either partner reaches (union; intersect two single-organism calls for 'both')

```example-call
list_metabolites(organism_names=["Prochlorococcus MED4", "Alteromonas macleodii MIT1002"], summary=True)
```

### Example 4: Lucene search by name

```example-call
list_metabolites(search_text="glucose", limit=3)
```

### Example 5: Retired id — resolves to the surviving node and shows in resolved_aliases

```example-call
list_metabolites(metabolite_ids=["chebi:14654"])
```

```example-response
{
  "total_entries": 3251,
  "total_matching": 1,
  "top_organisms": [
    {"organism_name": "Alteromonas macleodii 83-1", "count": 1},
    {"organism_name": "Alteromonas macleodii AD45", "count": 1},
    {"organism_name": "Alteromonas macleodii ATCC27126", "count": 1},
    ...
  ],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko00910",
      "metabolite_pathway_name": "Nitrogen metabolism",
      "count": 1
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01100",
      "metabolite_pathway_name": "Metabolic pathways",
      "count": 1
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01120",
      "metabolite_pathway_name": "Microbial metabolism in diverse environments",
      "count": 1
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "go_transport", "count": 1},
    {"evidence_source": "metabolism", "count": 1},
    {"evidence_source": "transport", "count": 1}
  ],
  "xref_coverage": {"with_chebi": 1, "with_hmdb": 0, "with_mnxm": 1},
  "mass_stats": {"mass_min": 63.012, "mass_median": 63.012, "mass_max": 63.012},
  "by_measurement_coverage": {"by_paper_count": [{"paper_count": 0, "count": 1}], "by_compartment": []},
  "by_structure_kind": [{"structure_kind": "defined", "count": 1}],
  "by_kegg_functional_category": [{"kegg_functional_category": "not classified", "count": 1}],
  "by_kegg_brite_class": [{"kegg_brite_class": "not classified", "count": 1}],
  "...": "4 empty fields omitted (score_max, score_median, warnings, no_formula_excluded)",
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "resolved_aliases": {"chebi:14654": ["kegg.compound:C00244"]},
  "results": [
    {
      "metabolite_id": "kegg.compound:C00244",
      "name": "Nitrate",
      "formula": "HNO3",
      "elements": ["H", "N", "O"],
      "mass": 63.012,
      "catalyst_gene_count": 78,
      "organism_count": 74,
      "transporter_count": 5,
      "transporter_gene_count": 168,
      "evidence_sources": ["go_transport", "metabolism", "transport"],
      "go_transport_organism_names": ["Alteromonas (MarRef v6)", "Alteromonas macleodii 83-1", "Alteromonas macleodii AD45", ...],
      "go_transport_organism_count": 73,
      "chebi_id": "48107",
      "pathway_ids": ["kegg.pathway:ko00910", "kegg.pathway:ko01100", "kegg.pathway:ko01120", ...],
      "pathway_count": 6,
      "measured_assay_count": 0,
      "measured_paper_count": 0,
      "measured_organisms": [],
      "measured_compartments": [],
      "structure_kind": "defined"
    }
  ]
}
```

### Example 6: Generic classes and polymers — what is not a single molecule

```example-call
list_metabolites(structure_kind=["generic"], summary=True)
```

```example-response
{
  "total_entries": 3251,
  "total_matching": 641,
  "top_organisms": [
    {"organism_name": "Pseudomonas putida KT2440", "count": 322},
    {"organism_name": "Alteromonas macleodii EZ55", "count": 315},
    {"organism_name": "Alteromonas macleodii MIT1002", "count": 312},
    ...
  ],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko01100",
      "metabolite_pathway_name": "Metabolic pathways",
      "count": 156
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01110",
      "metabolite_pathway_name": "Biosynthesis of secondary metabolites",
      "count": 44
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00061",
      "metabolite_pathway_name": "Fatty acid biosynthesis",
      "count": 42
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "metabolism", "count": 349},
    {"evidence_source": "transport", "count": 298},
    {"evidence_source": "go_transport", "count": 82}
  ],
  "xref_coverage": {"with_chebi": 554, "with_hmdb": 2, "with_mnxm": 639},
  "mass_stats": {"mass_min": null, "mass_median": null, "mass_max": null},
  "by_measurement_coverage": {"by_paper_count": [{"paper_count": 0, "count": 641}], "by_compartment": []},
  "by_structure_kind": [{"structure_kind": "generic", "count": 641}],
  "by_kegg_functional_category": [
    {"kegg_functional_category": "Lipids", "count": 19},
    {"kegg_functional_category": "Antibiotics", "count": 2},
    {"kegg_functional_category": "not classified", "count": 620}
  ],
  "by_kegg_brite_class": [
    {"kegg_brite_class": "Lipids: Fatty acyls", "count": 39},
    {"kegg_brite_class": "Lipids: Glycerophospholipids", "count": 24},
    {"kegg_brite_class": "Lipids: Glycerolipids", "count": 9},
    ...,
    {"kegg_brite_class": "not classified", "count": 565}
  ],
  "...": "5 empty fields omitted",
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "results": []
}
```

### Example 7: KEGG functional category — describe, don't exclude (read the "not classified" tail)

```example-call
list_metabolites(kegg_functional_categories=["Peptides"], limit=3)
```

```example-response
{
  "total_entries": 3251,
  "total_matching": 59,
  "top_organisms": [
    {"organism_name": "Ruegeria pomeroyi DSS-3", "count": 48},
    {"organism_name": "Alteromonas mediterranea AltDE", "count": 47},
    {"organism_name": "Pseudomonas putida KT2440", "count": 47},
    ...
  ],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko01100",
      "metabolite_pathway_name": "Metabolic pathways",
      "count": 56
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01110",
      "metabolite_pathway_name": "Biosynthesis of secondary metabolites",
      "count": 33
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00470",
      "metabolite_pathway_name": "D-Amino acid metabolism",
      "count": 29
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "metabolism", "count": 52},
    {"evidence_source": "transport", "count": 43},
    {"evidence_source": "metabolomics", "count": 26},
    ...
  ],
  "xref_coverage": {"with_chebi": 59, "with_hmdb": 54, "with_mnxm": 58},
  "mass_stats": {"mass_min": 62.092, "mass_median": 135.188, "mass_max": 650.976},
  "by_measurement_coverage": {
    "by_paper_count": [{"paper_count": 0, "count": 33}, {"paper_count": 1, "count": 14}, {"paper_count": 2, "count": 12}],
    "by_compartment": [
      {"compartment": "extracellular", "count": 20},
      {"compartment": "vesicle", "count": 18},
      {"compartment": "whole_cell", "count": 26}
    ]
  },
  "by_structure_kind": [{"structure_kind": "defined", "count": 59}],
  "by_kegg_functional_category": [
    {"kegg_functional_category": "Peptides", "count": 59},
    {"kegg_functional_category": "Hormones and transmitters", "count": 9},
    {"kegg_functional_category": "not classified", "count": 0}
  ],
  "by_kegg_brite_class": [
    {"kegg_brite_class": "Phytochemical compounds: Alkaloids", "count": 3},
    {"kegg_brite_class": "Lipids: Fatty acyls", "count": 1},
    {"kegg_brite_class": "not classified", "count": 55}
  ],
  "...": "5 empty fields omitted",
  "returned": 3,
  "offset": 0,
  "truncated": true,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "results": [
    {
      "metabolite_id": "kegg.compound:C00025",
      "name": "L-Glutamate",
      "formula": "C5H8NO4",
      "elements": ["C", "H", "N", ...],
      "mass": 146.122,
      "catalyst_gene_count": 4836,
      "organism_count": 118,
      "transporter_count": 1,
      "transporter_gene_count": 2,
      "evidence_sources": ["go_transport", "metabolism", "metabolomics", ...],
      "go_transport_organism_names": ["Cyanobium NS01", "Cyanobium PCC6307", "Cyanobium PCC7001", ...],
      "go_transport_organism_count": 73,
      "chebi_id": "16015",
      "pathway_ids": ["kegg.pathway:ko00220", "kegg.pathway:ko00250", "kegg.pathway:ko00330", ...],
      "pathway_count": 31,
      "measured_assay_count": 12,
      "measured_paper_count": 2,
      "measured_organisms": ["Prochlorococcus MIT0801", "Prochlorococcus MIT9301", "Prochlorococcus MIT9312", ...],
      "measured_compartments": ["extracellular", "vesicle", "whole_cell"],
      "structure_kind": "defined",
      "kegg_functional_categories": ["Hormones and transmitters", "Peptides"],
      "stereo_relatives": [
        {
          "metabolite_id": "kegg.compound:C00217",
          "name": "D-Glutamate",
          "relation": "enantiomer",
          "catalyst_gene_count": 260,
          "transporter_gene_count": 2
        },
        {
          "metabolite_id": "kegg.compound:C00302",
          "name": "Glutamate",
          "relation": "unspecified_form",
          "catalyst_gene_count": 167,
          "transporter_gene_count": 391
        }
      ]
    },
    {
      "metabolite_id": "kegg.compound:C00064",
      "name": "L-Glutamine",
      "formula": "C5H10N2O3",
      "elements": ["C", "H", "N", ...],
      "mass": 146.146,
      "catalyst_gene_count": 2938,
      "organism_count": 118,
      "transporter_count": 0,
      "transporter_gene_count": 0,
      "evidence_sources": ["metabolism", "metabolomics", "transport"],
      "go_transport_organism_names": null,
      "go_transport_organism_count": null,
      "chebi_id": "18050",
      "pathway_ids": ["kegg.pathway:ko00220", "kegg.pathway:ko00230", "kegg.pathway:ko00240", ...],
      "pathway_count": 17,
      "measured_assay_count": 12,
      "measured_paper_count": 2,
      "measured_organisms": ["Prochlorococcus MIT0801", "Prochlorococcus MIT9301", "Prochlorococcus MIT9312", ...],
      "measured_compartments": ["extracellular", "vesicle", "whole_cell"],
      "structure_kind": "defined",
      "kegg_functional_categories": ["Peptides"],
      "stereo_relatives": [
        {
          "metabolite_id": "kegg.compound:C00819",
          "name": "D-Glutamine",
          "relation": "enantiomer",
          "catalyst_gene_count": 23,
          "transporter_gene_count": 0
        },
        {
          "metabolite_id": "kegg.compound:C00303",
          "name": "Glutamine",
          "relation": "unspecified_form",
          "catalyst_gene_count": 0,
          "transporter_gene_count": 422
        }
      ]
    },
    {
      "metabolite_id": "kegg.compound:C00037",
      "name": "Glycine",
      "formula": "C2H5NO2",
      "elements": ["C", "H", "N", ...],
      "mass": 75.067,
      "catalyst_gene_count": 2148,
      "organism_count": 118,
      "transporter_count": 8,
      "transporter_gene_count": 120,
      "evidence_sources": ["go_transport", "metabolism", "transport"],
      "go_transport_organism_names": ["Pseudomonas putida KT2440"],
      "go_transport_organism_count": 1,
      "chebi_id": "15428",
      "pathway_ids": ["kegg.pathway:ko00120", "kegg.pathway:ko00230", "kegg.pathway:ko00260", ...],
      "pathway_count": 26,
      "measured_assay_count": 0,
      "measured_paper_count": 0,
      "measured_organisms": [],
      "measured_compartments": [],
      "structure_kind": "defined",
      "kegg_functional_categories": ["Hormones and transmitters", "Peptides"]
    }
  ]
}
```

### Example 8: KEGG BRITE class — top-level class of one of the 7 other compound trees

```example-call
list_metabolites(kegg_brite_classes=["Lipids: Fatty acyls"], limit=3)
```

```example-response
{
  "total_entries": 3251,
  "total_matching": 257,
  "top_organisms": [
    {"organism_name": "Ruegeria pomeroyi DSS-3", "count": 193},
    {"organism_name": "Pseudomonas putida KT2440", "count": 187},
    {"organism_name": "Alteromonas macleodii EZ55", "count": 181},
    ...
  ],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko01100",
      "metabolite_pathway_name": "Metabolic pathways",
      "count": 202
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01120",
      "metabolite_pathway_name": "Microbial metabolism in diverse environments",
      "count": 84
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01212",
      "metabolite_pathway_name": "Fatty acid metabolism",
      "count": 72
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "metabolism", "count": 231},
    {"evidence_source": "transport", "count": 55},
    {"evidence_source": "go_transport", "count": 6},
    ...
  ],
  "xref_coverage": {"with_chebi": 250, "with_hmdb": 154, "with_mnxm": 256},
  "mass_stats": {"mass_min": 45.017, "mass_median": 279.89, "mass_max": 1120.059},
  "by_measurement_coverage": {
    "by_paper_count": [{"paper_count": 0, "count": 251}, {"paper_count": 1, "count": 6}],
    "by_compartment": [{"compartment": "extracellular", "count": 5}, {"compartment": "whole_cell", "count": 6}]
  },
  "by_structure_kind": [{"structure_kind": "defined", "count": 218}, {"structure_kind": "generic", "count": 39}],
  "by_kegg_functional_category": [
    {"kegg_functional_category": "Organic acids", "count": 22},
    {"kegg_functional_category": "Lipids", "count": 18},
    {"kegg_functional_category": "Hormones and transmitters", "count": 1},
    ...,
    {"kegg_functional_category": "not classified", "count": 219}
  ],
  "by_kegg_brite_class": [
    {"kegg_brite_class": "Lipids: Fatty acyls", "count": 257},
    {"kegg_brite_class": "Phytochemical compounds: Fatty acids related compounds", "count": 9},
    {"kegg_brite_class": "Phytochemical compounds: Phenylpropanoids", "count": 6},
    ...,
    {"kegg_brite_class": "not classified", "count": 0}
  ],
  "...": "5 empty fields omitted",
  "returned": 3,
  "offset": 0,
  "truncated": true,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "results": [
    {
      "metabolite_id": "kegg.compound:C00022",
      "name": "Pyruvate",
      "formula": "C3H3O3",
      "elements": ["C", "H", "O"],
      "mass": 87.054,
      "catalyst_gene_count": 2967,
      "organism_count": 118,
      "transporter_count": 5,
      "transporter_gene_count": 96,
      "evidence_sources": ["metabolism", "transport"],
      "go_transport_organism_names": null,
      "go_transport_organism_count": null,
      "chebi_id": "32816",
      "pathway_ids": ["kegg.pathway:ko00010", "kegg.pathway:ko00020", "kegg.pathway:ko00030", ...],
      "pathway_count": 48,
      "measured_assay_count": 0,
      "measured_paper_count": 0,
      "measured_organisms": [],
      "measured_compartments": [],
      "structure_kind": "defined",
      "kegg_functional_categories": ["Organic acids"],
      "kegg_brite_classes": ["Lipids: Fatty acyls"]
    },
    {
      "metabolite_id": "kegg.compound:C00024",
      "name": "Acetyl-CoA",
      "formula": "C23H34N7O17P3S",
      "elements": ["C", "H", "N", ...],
      "mass": 805.546,
      "catalyst_gene_count": 2657,
      "organism_count": 118,
      "transporter_count": 0,
      "transporter_gene_count": 0,
      "evidence_sources": ["go_transport", "metabolism", "metabolomics", ...],
      "go_transport_organism_names": ["Synechococcus ROS8604"],
      "go_transport_organism_count": 1,
      "chebi_id": "15351",
      "pathway_ids": ["kegg.pathway:ko00010", "kegg.pathway:ko00020", "kegg.pathway:ko00061", ...],
      "pathway_count": 49,
      "measured_assay_count": 2,
      "measured_paper_count": 1,
      "measured_organisms": ["Prochlorococcus MIT9303", "Prochlorococcus MIT9313"],
      "measured_compartments": ["whole_cell"],
      "structure_kind": "defined",
      "kegg_brite_classes": ["Lipids: Fatty acyls"]
    },
    {
      "metabolite_id": "kegg.compound:C00033",
      "name": "Acetate",
      "formula": "C2H3O2",
      "elements": ["C", "H", "O"],
      "mass": 59.044,
      "catalyst_gene_count": 1313,
      "organism_count": 118,
      "transporter_count": 8,
      "transporter_gene_count": 24,
      "evidence_sources": ["go_transport", "metabolism", "transport"],
      "go_transport_organism_names": ["Pseudomonas putida KT2440", "Shewanella sp. W3-18-1"],
      "go_transport_organism_count": 2,
      "chebi_id": "15366",
      "pathway_ids": ["kegg.pathway:ko00010", "kegg.pathway:ko00430", "kegg.pathway:ko00440", ...],
      "pathway_count": 16,
      "measured_assay_count": 0,
      "measured_paper_count": 0,
      "measured_organisms": [],
      "measured_compartments": [],
      "structure_kind": "defined",
      "kegg_functional_categories": ["Organic acids"],
      "kegg_brite_classes": ["Lipids: Fatty acyls"]
    }
  ]
}
```

### Example 9: TCDB substrate catalogue (metabolite-level)

```example-call
list_metabolites(evidence_sources=["transport"], summary=True)
```

*Every compound some TCDB system lists as a substrate, catalysed or not: `evidence_sources` is ANY-match and catalogue-level. Transport-only = rows with `catalyst_gene_count = 0` and `transporter_gene_count > 0`; filter rows client-side.*

### Example 10: One organism's transport reach — organism_names + evidence_sources scope each other

```example-call
list_metabolites(organism_names=["Prochlorococcus MED4"], evidence_sources=["transport"], elements=["N"], summary=True)
```

*With both filters set, a metabolite matches only when MED4 itself reaches it by a TCDB transport route, so the roster is far smaller than the `evidence_sources=['transport']` catalogue for N. `top_organisms` counts each organism by the listed routes only.*

### Example 11: Transport-only metabolite by ID — reading the two gene counts together

```example-call
list_metabolites(metabolite_ids=["chebi:17234"])
```

```example-response
{
  "total_entries": 3251,
  "total_matching": 1,
  "top_organisms": [
    {"organism_name": "Alteromonas macleodii 83-1", "count": 1},
    {"organism_name": "Alteromonas macleodii AD45", "count": 1},
    {"organism_name": "Alteromonas macleodii ATCC27126", "count": 1},
    ...
  ],
  "...": "6 empty fields omitted",
  "by_evidence_source": [{"evidence_source": "transport", "count": 1}],
  "xref_coverage": {"with_chebi": 1, "with_hmdb": 0, "with_mnxm": 1},
  "mass_stats": {"mass_min": 180.156, "mass_median": 180.156, "mass_max": 180.156},
  "by_measurement_coverage": {"by_paper_count": [{"paper_count": 0, "count": 1}], "by_compartment": []},
  "by_structure_kind": [{"structure_kind": "defined", "count": 1}],
  "by_kegg_functional_category": [{"kegg_functional_category": "not classified", "count": 1}],
  "by_kegg_brite_class": [{"kegg_brite_class": "not classified", "count": 1}],
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "results": [
    {
      "metabolite_id": "chebi:17234",
      "name": "glucose",
      "formula": "C6H12O6",
      "elements": ["C", "H", "O"],
      "mass": 180.156,
      "catalyst_gene_count": 0,
      "organism_count": 78,
      "transporter_count": 12,
      "transporter_gene_count": 136,
      "evidence_sources": ["transport"],
      "go_transport_organism_names": null,
      "go_transport_organism_count": null,
      "chebi_id": "17234",
      "pathway_ids": [],
      "pathway_count": 0,
      "measured_assay_count": 0,
      "measured_paper_count": 0,
      "measured_organisms": [],
      "measured_compartments": [],
      "structure_kind": "defined",
      "stereo_relatives": [
        {
          "metabolite_id": "kegg.compound:C00031",
          "name": "D-Glucose",
          "relation": "specific_form",
          "catalyst_gene_count": 745,
          "transporter_gene_count": 18
        }
      ]
    }
  ]
}
```

### Example 12: Stereo relatives — generic Cysteine carries the transport, L-Cysteine the catalysis

```example-call
list_metabolites(metabolite_ids=["kegg.compound:C00736", "kegg.compound:C00097"])
```

*Each row's `stereo_relatives` names the other stereo forms with their own KG-wide gene counts: Cysteine's `specific_form` relatives are L- and D-Cysteine, L-Cysteine's are its `enantiomer` D-Cysteine and its `unspecified_form` Cysteine. No count combines across forms. Rows with no relative have no `stereo_relatives` key.*

### Example 13: Measured metabolites — measurement coverage envelope

```example-call
list_metabolites(evidence_sources=["metabolomics"], summary=True)
```

```example-response
{
  "total_entries": 3251,
  "total_matching": 135,
  "top_organisms": [
    {"organism_name": "Prochlorococcus MIT9313", "count": 134},
    {"organism_name": "Prochlorococcus MIT9301", "count": 96},
    {"organism_name": "Prochlorococcus MIT0801", "count": 92},
    ...
  ],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko01100",
      "metabolite_pathway_name": "Metabolic pathways",
      "count": 122
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01110",
      "metabolite_pathway_name": "Biosynthesis of secondary metabolites",
      "count": 67
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01240",
      "metabolite_pathway_name": "Biosynthesis of cofactors",
      "count": 49
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "metabolomics", "count": 135},
    {"evidence_source": "metabolism", "count": 119},
    {"evidence_source": "transport", "count": 102},
    ...
  ],
  "xref_coverage": {"with_chebi": 135, "with_hmdb": 126, "with_mnxm": 133},
  "mass_stats": {"mass_min": 89.094, "mass_median": 179.172, "mass_max": 1353.372},
  "by_measurement_coverage": {
    "by_paper_count": [{"paper_count": 1, "count": 93}, {"paper_count": 2, "count": 37}, {"paper_count": 3, "count": 5}],
    "by_compartment": [
      {"compartment": "extracellular", "count": 96},
      {"compartment": "vesicle", "count": 70},
      {"compartment": "whole_cell", "count": 135}
    ]
  },
  "by_structure_kind": [{"structure_kind": "defined", "count": 135}],
  "by_kegg_functional_category": [
    {"kegg_functional_category": "Peptides", "count": 26},
    {"kegg_functional_category": "Vitamins and cofactors", "count": 16},
    {"kegg_functional_category": "Nucleic acids", "count": 13},
    ...,
    {"kegg_functional_category": "not classified", "count": 65}
  ],
  "by_kegg_brite_class": [
    {"kegg_brite_class": "Lipids: Fatty acyls", "count": 6},
    {"kegg_brite_class": "Phytochemical compounds: Alkaloids", "count": 6},
    {"kegg_brite_class": "Glycosides: N-glycosides", "count": 5},
    ...,
    {"kegg_brite_class": "not classified", "count": 111}
  ],
  "...": "5 empty fields omitted",
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "results": []
}
```

### Example 14: Multi-step — find N-metabolites then drill into catalysts

```
Step 1: list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"], limit=10)
        → extract metabolite_ids of interest

Step 2: genes_by_metabolite(metabolite_ids=[chosen_ids], organism="Prochlorococcus MED4")
        → catalysing genes per metabolite
```

### Example 15: Currency-cofactor strip — exclude ATP/ADP/NADH/NADPH/H2O when top_metabolites is dominated by them

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

### Example 16: GO transport route — metabolites a GO transport term names (evidence_sources=['go_transport'])

```example-call
list_metabolites(evidence_sources=["go_transport"], organism_names=["Prochlorococcus MED4"], limit=5)
```

*Rows carry `go_transport_organism_names` / `go_transport_organism_count` (organisms with a gene annotated to a GO term that names this metabolite, direct annotations only). With `evidence_sources=['go_transport']` set, `organism_names` matches only organisms on the GO list (`go_transport_organism_names`), and `top_organisms` counts the GO route only; `organism_count` and the gene counts still ignore the GO route. A metabolite with no `go_transport_organism_names` may still have a GO edge reached only through ancestor terms: absent means no directly annotated gene path.*

## Chaining patterns

```
list_organisms (per-row catalyzed_metabolite_count > 0) → list_metabolites(organism_names=[...])
list_metabolites → genes_by_metabolite(metabolite_ids=[...], organism=...)
list_metabolites (per-row `transporter_gene_count > 0`) → genes_by_metabolite(metabolite_ids=[...], organism=..., evidence_sources=['transport']) — distinct genes in the direct transport rows, unioned over organisms, equal transporter_gene_count
list_metabolites (per-row `stereo_relatives`) → genes_by_metabolite(metabolite_ids=[generic id], organism=..., include_stereo_forms=True) — transport on the generic form plus catalysis on the specific form, per organism
list_metabolites (per-row pathway_ids) → genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...)
differential_expression_by_gene → metabolites_by_gene(metabolite_elements=['N']) → list_metabolites for chemistry context
list_metabolites (per-row `kegg_brite_classes`, top level only) → run_cypher over `MetaboliteClass` for the deeper KEGG compound classes (docs://analysis/metabolites)
list_metabolites (per-row `measured_assay_count > 0`) → assays_by_metabolite(metabolite_ids=[...]) — reverse lookup of all measurement evidence (numeric + boolean) for the measured compounds (cross-organism by default).
list_metabolites(evidence_sources=['go_transport'], organism_names=[...]) → genes_by_metabolite(metabolite_ids=[...], organism=..., evidence_sources=['go_transport']) for the genes carrying the GO term
```

## Common mistakes

- Direction-agnostic — KEGG equation order is unreliable upstream, so the catalysis join does NOT distinguish substrates from products, and the transport counts here carry no direction (TCDB's node-level `tcdb_direction` hint is on `genes_by_metabolite` rows, mostly `unknown`). Layer DE direction (`differential_expression_by_gene`) and functional annotation to disambiguate. See docs://analysis/metabolites.

- catalyst_gene_count counts the catalysis arm only (genes reaching the metabolite via Gene → Reaction → Metabolite). catalyst_gene_count = 0 does NOT mean metabolomics-only: transport-only metabolites (TCDB substrates with no local catalysis) also read 0. Discriminate via the paired counts: catalyst_gene_count = 0 with `transporter_gene_count > 0` is transport-only; both 0 with `evidence_sources == ['metabolomics']` is measurement-only (no gene path). `transporter_gene_count` counts distinct genes with a direct TCDB call (`tcdb_gate='direct'`) on a system curated with the metabolite, all organisms — it equals the distinct genes `genes_by_metabolite` returns in its default (direct) transport rows, unioned over organisms. `'transport'` in `evidence_sources` only means TCDB lists the metabolite as a substrate of a kept system; many such metabolites read `transporter_gene_count = 0`, so route on the count, not the tag.

- A 0 `catalyst_gene_count` on a generic (stereo-unspecified) metabolite does not mean no enzyme acts on the compound. Stereo forms are separate nodes and no count combines across them: TCDB names substrates generically, so transport sits on 'Cysteine' (`kegg.compound:C00736`, 0 catalysts), while KEGG reactions use the specific form, so catalysis sits on 'L-Cysteine' (`kegg.compound:C00097`). Read the row's `stereo_relatives` (`relation` = `specific_form` / `unspecified_form` / `enantiomer`, each with its own `catalyst_gene_count` / `transporter_gene_count`), then use `genes_by_metabolite(..., include_stereo_forms=True)` for a per-organism transport ↔ catalysis join. A generic's `specific_form` relatives can include a D-form. Stereo links cover the KG's curated generic → specific pairs only, so a missing `stereo_relatives` is not proof that no other form exists: `search_text` by name lists every form.

```mistake
list_metabolites(organism_names=['Prochlorococcus MED4'], evidence_sources=['transport'])  # read as 'transport catalogue, plus MED4 reaches it somehow'
```

```correction
With both filters set, the organism must reach the metabolite by one of the
listed routes: here, a MED4 gene with a direct TCDB call on a system that
carries the compound. `metabolism` = a MED4 gene's KEGG reaction,
`metabolomics` = a MED4 assay measured it, `go_transport` = MED4 is on the
row's `go_transport_organism_names`. Either filter alone is unchanged:
`organism_names` alone = reached by any route; `evidence_sources` alone = the
catalogue sense (`transport` = some TCDB system lists the compound, whether or
not any organism's gene reaches it). With `evidence_sources` set, envelope
`top_organisms` counts each organism by the listed routes only. Per-row
`organism_names` / `organism_count` stay any-route.

```

- organism_names with multiple values is UNION, not intersection. To find metabolites BOTH organisms reach, run two single-org calls and intersect by `metabolite_id` (per-row `organism_count` tells you how many organisms reach a metabolite, but not which — the envelope `top_organisms` rollup is the only per-organism breakdown).

- `elements` never matches a metabolite with no formula (empty `elements`) — mostly generic classes such as 'amino acid', 'dipeptide' or 'Polyamine'. When the filter is set, the envelope's `no_formula_excluded` counts metabolites that pass every other filter but have no formula, and a `warnings` entry fires when it is > 0. Re-run without `elements` to inspect them.

- `search_text` is a Lucene search over the metabolite name, formula and identifiers (KEGG / ChEBI / MNX / HMDB ids, InChIKey) — a formula hit is a token match, not a composition query. For element/composition questions use `elements` (presence list).

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
`Fe`) for the 15 elements this KG's chemistry layer carries. An
unrecognized element (not a known symbol or full name) is dropped from
the filter, reported in `not_found.elements`, and adds a `warnings` entry.

```

```mistake
list_metabolites(kegg_functional_categories=['Organic acids'])  # read as 'all organic acids'; anything missing is not one
```

```correction
`kegg_functional_categories` (KEGG br08001) and `kegg_brite_classes` (KEGG's 7 other
compound trees) are hand-curated lists of representative compounds, not a full
classification: ~10% of metabolites carry a functional category and ~20% a BRITE
class. A missing value means "KEGG did not list it", not "not in it" — fumarate is an
organic acid with no category. The headings are functional (amines sit under
Peptides). Use them to describe or group results, never to exclude; for enrichment
use the classified metabolites as background; for composition use `elements`. The
envelope's trailing `"not classified"` entry counts the unlisted metabolites; it is
not a filter value. Details: docs://analysis/metabolites.

```

- `structure_kind` separates single molecules (`defined`) from classes and polymers (`generic` / `polymer`, e.g. 'Amino acid', 'Acyl-CoA', glycogen). Generic and polymer nodes have no `mass` and carry generic formulas with a placeholder ('Amino acid' is `C2H4NO2*`), whose atoms still feed the `elements` filter — add `structure_kind=['defined']` when a question is about specific molecules.

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
IDs in any form (bare, prefixed, ChEBI / HMDB / MNX / InChIKey, retired) resolve before the query; read `resolved_aliases`. Removed compounds and chemical-role ids stay in `not_found` with a warning (roles go to `genes_by_metabolite`). The xref filters normalise the same way but add nothing to `resolved_aliases`. See docs://analysis/metabolites, 'Metabolite ID forms'.
```

- See `docs://analysis/metabolites` (evidence sources: metabolism, TCDB transport, GO transport, metabolomics) and `docs://analysis/transport` for reading the transport routes; `docs://guide/concepts` has the chemistry layer overview.

- `evidence_sources=['go_transport']` alone is a metabolite-level filter (a GO transport term names this compound). Combined with `organism_names`, the organism must be on the row's `go_transport_organism_names`; `organism_names` alone matches organisms on either the KEGG / TCDB / assay list or the GO list. `catalyst_gene_count`, `transporter_gene_count` and `organism_count` stay KEGG / TCDB / assay only (no blending), so a GO-only metabolite reads zero on all three. Drill the GO route with `genes_by_metabolite`. See `docs://analysis/transport`.

## Package import equivalent

```python
from multiomics_explorer import list_metabolites

result = list_metabolites()
# returns dict with keys: total_entries, total_matching, top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, mass_stats, by_measurement_coverage, by_structure_kind, by_kegg_functional_category, by_kegg_brite_class, score_max, score_median, returned, offset, truncated, not_found, resolved_aliases, warnings, no_formula_excluded, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
