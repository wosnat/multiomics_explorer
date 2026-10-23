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
| organism_names | list[string] \| None | None | Restrict to metabolites reachable by these organisms (case-insensitive on `preferred_name`). UNION semantics — a metabolite reached by ANY listed organism qualifies. Joined via `Organism_has_metabolite` (catalysis OR transport). E.g. ['Prochlorococcus MED4']. `not_found.organism_names` lists any unknown names. |
| pathway_ids | list[string] \| None | None | Filter by KEGG pathway membership (`KeggTerm.id`). E.g. ['kegg.pathway:ko00910'] for nitrogen metabolism. Joined via `Metabolite_in_pathway`. `not_found.pathway_ids` lists unknown IDs. |
| evidence_sources | list[string ('metabolism', 'transport', 'metabolomics', 'go_transport')] \| None | None | Filter by evidence path (ANY). Values: 'metabolism' (catalysis-reachable), 'transport' (TCDB substrate), 'metabolomics' (measured by a MetaboliteAssay), 'go_transport' (named by a GO transport term). Other values raise at the MCP boundary. |
| structure_kind | list[string] \| None | None | Structure kind(s) (OR): 'defined' (one molecule), 'generic' (a compound class) or 'polymer'. E.g. ['defined'] drops generic substrates like 'amino acid'. Values: list_filter_values('structure_kind'). |
| kegg_functional_categories | list[string] \| None | None | KEGG br08001 categories (OR). Hand-curated and partial: only ~10% of metabolites are listed, so a missing category means 'KEGG did not list it', not 'not in it' (fumarate is unclassified). Values: list_filter_values('kegg_functional_category'). |
| kegg_brite_classes | list[string] \| None | None | Classes from 7 other KEGG compound BRITE trees, as 'Tree: Class' (OR), e.g. 'Lipids: Fatty acyls'. Curated and partial (~20% of metabolites): unlisted = 'KEGG did not list it', not 'not in it'. Values: list_filter_values('kegg_brite_class'). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Response format

### Envelope

```expected-keys
total_entries, total_matching, top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, mass_stats, by_measurement_coverage, by_structure_kind, by_kegg_functional_category, by_kegg_brite_class, score_max, score_median, returned, offset, truncated, not_found, resolved_aliases, warnings, results
```

- **total_entries** (int): Total Metabolite nodes in KG (unfiltered).
- **total_matching** (int): Metabolites matching filters.
- **top_organisms** (list[MetTopOrganism]): Top 10 organisms by metabolite count (within matched set), sorted desc.
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
| organism_count | int (optional) | Distinct organisms reaching this metabolite via any chemistry path. When > 0, narrow with organism_names filter. |
| transporter_count | int (optional) | Distinct transporter systems (TcdbFamily nodes) whose substrate edge to this metabolite is substrate_depth='most_specific'. Systems, not genes — pair with transporter_gene_count and catalyst_gene_count; drill via genes_by_metabolite. |
| transporter_gene_count | int (optional) | Distinct genes (all organisms) whose deepest TCDB attachment transports this metabolite (precomputed Metabolite.transporter_gene_count). catalyst_gene_count=0 with transporter_gene_count>0 = transport-only; drill via genes_by_metabolite. |
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

### Example 3: Cross-organism survey — metabolites both partners reach

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
  "total_entries": 3243,
  "total_matching": 1,
  "top_organisms": [
    {"organism_name": "Alteromonas macleodii AD45", "count": 1},
    {"organism_name": "Alteromonas macleodii ATCC27126", "count": 1},
    {"organism_name": "Alteromonas macleodii BGP6", "count": 1},
    {"organism_name": "Alteromonas macleodii BS11", "count": 1},
    {"organism_name": "Alteromonas macleodii EZ55", "count": 1},
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
    {"metabolite_pathway_id": "kegg.pathway:ko01310", "metabolite_pathway_name": "Nitrogen cycle", "count": 1},
    {
      "metabolite_pathway_id": "kegg.pathway:ko02010",
      "metabolite_pathway_name": "ABC transporters",
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
  "score_max": null,
  "score_median": null,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "resolved_aliases": {"chebi:14654": ["kegg.compound:C00244"]},
  "warnings": [],
  "no_formula_excluded": null,
  "results": [
    {
      "metabolite_id": "kegg.compound:C00244",
      "name": "Nitrate",
      "formula": "HNO3",
      "elements": ["H", "N", "O"],
      "mass": 63.012,
      "catalyst_gene_count": 33,
      "organism_count": 43,
      "transporter_count": 15,
      "transporter_gene_count": 3549,
      "evidence_sources": ["go_transport", "metabolism", "transport"],
      "go_transport_organism_names": [
        "Alteromonas (MarRef v6)",
        "Alteromonas macleodii AD45",
        "Alteromonas macleodii ATCC27126",
        "Alteromonas macleodii BGP6",
        "Alteromonas macleodii BS11",
        ...
      ],
      "go_transport_organism_count": 26,
      "chebi_id": "48107",
      "pathway_ids": [
        "kegg.pathway:ko00910",
        "kegg.pathway:ko01100",
        "kegg.pathway:ko01120",
        "kegg.pathway:ko01310",
        "kegg.pathway:ko02010",
        ...
      ],
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
  "total_entries": 3243,
  "total_matching": 649,
  "top_organisms": [
    {"organism_name": "Alteromonas macleodii EZ55", "count": 537},
    {"organism_name": "Alteromonas macleodii MIT1002", "count": 536},
    {"organism_name": "Alteromonas macleodii HOT1A3", "count": 535},
    {"organism_name": "Alteromonas macleodii BGP6", "count": 534},
    {"organism_name": "Alteromonas mediterranea AltDE1", "count": 533},
    ...
  ],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko01100",
      "metabolite_pathway_name": "Metabolic pathways",
      "count": 147
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00061",
      "metabolite_pathway_name": "Fatty acid biosynthesis",
      "count": 42
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01212",
      "metabolite_pathway_name": "Fatty acid metabolism",
      "count": 35
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01110",
      "metabolite_pathway_name": "Biosynthesis of secondary metabolites",
      "count": 34
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00970",
      "metabolite_pathway_name": "Aminoacyl-tRNA biosynthesis",
      "count": 25
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "metabolism", "count": 332},
    {"evidence_source": "transport", "count": 330},
    {"evidence_source": "go_transport", "count": 77}
  ],
  "xref_coverage": {"with_chebi": 566, "with_hmdb": 2, "with_mnxm": 647},
  "mass_stats": {"mass_min": null, "mass_median": null, "mass_max": null},
  "by_measurement_coverage": {"by_paper_count": [{"paper_count": 0, "count": 649}], "by_compartment": []},
  "by_structure_kind": [{"structure_kind": "generic", "count": 649}],
  "by_kegg_functional_category": [
    {"kegg_functional_category": "Lipids", "count": 19},
    {"kegg_functional_category": "Antibiotics", "count": 2},
    {"kegg_functional_category": "not classified", "count": 628}
  ],
  "by_kegg_brite_class": [
    {"kegg_brite_class": "Lipids: Fatty acyls", "count": 34},
    {"kegg_brite_class": "Lipids: Glycerophospholipids", "count": 26},
    {"kegg_brite_class": "Lipids: Glycerolipids", "count": 9},
    {"kegg_brite_class": "Lipids: Sphingolipids", "count": 3},
    {"kegg_brite_class": "Lipids: Sterol lipids", "count": 1},
    ...
  ],
  "score_max": null,
  "score_median": null,
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "resolved_aliases": {},
  "warnings": [],
  "no_formula_excluded": null,
  "results": []
}
```

### Example 7: KEGG functional category — describe, don't exclude (read the "not classified" tail)

```example-call
list_metabolites(kegg_functional_categories=["Peptides"], limit=3)
```

```example-response
{
  "total_entries": 3243,
  "total_matching": 61,
  "top_organisms": [
    {"organism_name": "Alteromonas mediterranea AltDE", "count": 54},
    {"organism_name": "Alteromonas macleodii ATCC27126", "count": 53},
    {"organism_name": "Alteromonas macleodii MIT1002", "count": 53},
    {"organism_name": "Alteromonas macleodii BS11", "count": 53},
    {"organism_name": "Alteromonas macleodii EZ55", "count": 53},
    ...
  ],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko01100",
      "metabolite_pathway_name": "Metabolic pathways",
      "count": 58
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01110",
      "metabolite_pathway_name": "Biosynthesis of secondary metabolites",
      "count": 33
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00470",
      "metabolite_pathway_name": "D-Amino acid metabolism",
      "count": 30
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01230",
      "metabolite_pathway_name": "Biosynthesis of amino acids",
      "count": 25
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko04974",
      "metabolite_pathway_name": "Protein digestion and absorption",
      "count": 24
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "metabolism", "count": 52},
    {"evidence_source": "transport", "count": 47},
    {"evidence_source": "metabolomics", "count": 26},
    {"evidence_source": "go_transport", "count": 24}
  ],
  "xref_coverage": {"with_chebi": 61, "with_hmdb": 56, "with_mnxm": 61},
  "mass_stats": {"mass_min": 62.092, "mass_median": 133.171, "mass_max": 776.872},
  "by_measurement_coverage": {
    "by_paper_count": [{"paper_count": 0, "count": 35}, {"paper_count": 1, "count": 14}, {"paper_count": 2, "count": 12}],
    "by_compartment": [
      {"compartment": "extracellular", "count": 19},
      {"compartment": "vesicle", "count": 18},
      {"compartment": "whole_cell", "count": 26}
    ]
  },
  "by_structure_kind": [{"structure_kind": "defined", "count": 61}],
  "by_kegg_functional_category": [
    {"kegg_functional_category": "Peptides", "count": 61},
    {"kegg_functional_category": "Hormones and transmitters", "count": 10},
    {"kegg_functional_category": "not classified", "count": 0}
  ],
  "by_kegg_brite_class": [
    {"kegg_brite_class": "Phytochemical compounds: Alkaloids", "count": 3},
    {"kegg_brite_class": "Lipids: Fatty acyls", "count": 1},
    {"kegg_brite_class": "not classified", "count": 57}
  ],
  "score_max": null,
  "score_median": null,
  "returned": 3,
  "offset": 0,
  "truncated": true,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "resolved_aliases": {},
  "warnings": [],
  "no_formula_excluded": null,
  "results": [
    {
      "metabolite_id": "kegg.compound:C00025",
      "name": "L-Glutamate",
      "formula": "C5H8NO4",
      "elements": ["C", "H", "N", "O"],
      "mass": 146.122,
      "catalyst_gene_count": 1905,
      "organism_count": 43,
      "transporter_count": 5,
      "transporter_gene_count": 786,
      "evidence_sources": ["go_transport", "metabolism", "metabolomics", "transport"],
      "go_transport_organism_names": [
        "Prochlorococcus AS9601",
        "Prochlorococcus MED4",
        "Prochlorococcus MIT0604",
        "Prochlorococcus MIT0801",
        "Prochlorococcus MIT1314",
        ...
      ],
      "go_transport_organism_count": 27,
      "chebi_id": "16015",
      "pathway_ids": [
        "kegg.pathway:ko00220",
        "kegg.pathway:ko00250",
        "kegg.pathway:ko00330",
        "kegg.pathway:ko00332",
        "kegg.pathway:ko00340",
        ...
      ],
      "pathway_count": 52,
      "measured_assay_count": 12,
      "measured_paper_count": 2,
      "measured_organisms": [
        "Prochlorococcus MIT0801",
        "Prochlorococcus MIT9301",
        "Prochlorococcus MIT9312",
        "Prochlorococcus MIT9313"
      ],
      "measured_compartments": ["extracellular", "vesicle", "whole_cell"],
      "structure_kind": "defined",
      "kegg_functional_categories": ["Hormones and transmitters", "Peptides"],
      "stereo_relatives": [
        {
          "metabolite_id": "kegg.compound:C00217",
          "name": "D-Glutamate",
          "relation": "enantiomer",
          "catalyst_gene_count": 101,
          "transporter_gene_count": 28
        },
        {
          "metabolite_id": "kegg.compound:C00302",
          "name": "Glutamate",
          "relation": "unspecified_form",
          "catalyst_gene_count": 69,
          "transporter_gene_count": 2848
        }
      ]
    },
    {
      "metabolite_id": "kegg.compound:C00064",
      "name": "L-Glutamine",
      "formula": "C5H10N2O3",
      "elements": ["C", "H", "N", "O"],
      "mass": 146.146,
      "catalyst_gene_count": 1096,
      "organism_count": 43,
      "transporter_count": 12,
      "transporter_gene_count": 2365,
      "evidence_sources": ["metabolism", "metabolomics", "transport"],
      "go_transport_organism_names": null,
      "go_transport_organism_count": null,
      "chebi_id": "18050",
      "pathway_ids": [
        "kegg.pathway:ko00220",
        "kegg.pathway:ko00230",
        "kegg.pathway:ko00240",
        "kegg.pathway:ko00250",
        "kegg.pathway:ko00470",
        ...
      ],
      "pathway_count": 24,
      "measured_assay_count": 12,
      "measured_paper_count": 2,
      "measured_organisms": [
        "Prochlorococcus MIT0801",
        "Prochlorococcus MIT9301",
        "Prochlorococcus MIT9312",
        "Prochlorococcus MIT9313"
      ],
      "measured_compartments": ["extracellular", "vesicle", "whole_cell"],
      "structure_kind": "defined",
      "kegg_functional_categories": ["Peptides"],
      "stereo_relatives": [
        {
          "metabolite_id": "kegg.compound:C00819",
          "name": "D-Glutamine",
          "relation": "enantiomer",
          "catalyst_gene_count": 13,
          "transporter_gene_count": 0
        }
      ]
    },
    {
      "metabolite_id": "kegg.compound:C00037",
      "name": "Glycine",
      "formula": "C2H5NO2",
      "elements": ["C", "H", "N", "O"],
      "mass": 75.067,
      "catalyst_gene_count": 832,
      "organism_count": 43,
      "transporter_count": 10,
      "transporter_gene_count": 2011,
      "evidence_sources": ["go_transport", "metabolism", "transport"],
      "go_transport_organism_names": ["Pseudomonas putida KT2440"],
      "go_transport_organism_count": 1,
      "chebi_id": "15428",
      "pathway_ids": [
        "kegg.pathway:ko00120",
        "kegg.pathway:ko00230",
        "kegg.pathway:ko00260",
        "kegg.pathway:ko00310",
        "kegg.pathway:ko00440",
        ...
      ],
      "pathway_count": 30,
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
  "total_entries": 3243,
  "total_matching": 254,
  "top_organisms": [
    {"organism_name": "Ruegeria pomeroyi DSS-3", "count": 214},
    {"organism_name": "Pseudomonas putida KT2440", "count": 208},
    {"organism_name": "Alteromonas macleodii EZ55", "count": 205},
    {"organism_name": "Alteromonas macleodii MIT1002", "count": 202},
    {"organism_name": "Alteromonas macleodii AD45", "count": 202},
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
      "count": 83
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01212",
      "metabolite_pathway_name": "Fatty acid metabolism",
      "count": 72
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01110",
      "metabolite_pathway_name": "Biosynthesis of secondary metabolites",
      "count": 52
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00061",
      "metabolite_pathway_name": "Fatty acid biosynthesis",
      "count": 41
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "metabolism", "count": 225},
    {"evidence_source": "transport", "count": 58},
    {"evidence_source": "metabolomics", "count": 6},
    {"evidence_source": "go_transport", "count": 5}
  ],
  "xref_coverage": {"with_chebi": 247, "with_hmdb": 158, "with_mnxm": 253},
  "mass_stats": {"mass_min": 45.017, "mass_median": 281.46, "mass_max": 1120.059},
  "by_measurement_coverage": {
    "by_paper_count": [{"paper_count": 0, "count": 248}, {"paper_count": 1, "count": 6}],
    "by_compartment": [{"compartment": "extracellular", "count": 5}, {"compartment": "whole_cell", "count": 6}]
  },
  "by_structure_kind": [{"structure_kind": "defined", "count": 220}, {"structure_kind": "generic", "count": 34}],
  "by_kegg_functional_category": [
    {"kegg_functional_category": "Organic acids", "count": 22},
    {"kegg_functional_category": "Lipids", "count": 21},
    {"kegg_functional_category": "Hormones and transmitters", "count": 1},
    {"kegg_functional_category": "Peptides", "count": 1},
    {"kegg_functional_category": "not classified", "count": 213}
  ],
  "by_kegg_brite_class": [
    {"kegg_brite_class": "Lipids: Fatty acyls", "count": 254},
    {"kegg_brite_class": "Phytochemical compounds: Fatty acids related compounds", "count": 9},
    {"kegg_brite_class": "Phytochemical compounds: Phenylpropanoids", "count": 6},
    {"kegg_brite_class": "Pesticides: Pesticides", "count": 1},
    {"kegg_brite_class": "Phytochemical compounds: Terpenoids", "count": 1},
    ...
  ],
  "score_max": null,
  "score_median": null,
  "returned": 3,
  "offset": 0,
  "truncated": true,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "resolved_aliases": {},
  "warnings": [],
  "no_formula_excluded": null,
  "results": [
    {
      "metabolite_id": "kegg.compound:C00022",
      "name": "Pyruvate",
      "formula": "C3H3O3",
      "elements": ["C", "H", "O"],
      "mass": 87.054,
      "catalyst_gene_count": 1305,
      "organism_count": 43,
      "transporter_count": 7,
      "transporter_gene_count": 2900,
      "evidence_sources": ["metabolism", "transport"],
      "go_transport_organism_names": null,
      "go_transport_organism_count": null,
      "chebi_id": "32816",
      "pathway_ids": [
        "kegg.pathway:ko00010",
        "kegg.pathway:ko00020",
        "kegg.pathway:ko00030",
        "kegg.pathway:ko00040",
        "kegg.pathway:ko00053",
        ...
      ],
      "pathway_count": 54,
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
      "elements": ["C", "H", "N", "O", "P", ...],
      "mass": 805.546,
      "catalyst_gene_count": 1158,
      "organism_count": 43,
      "transporter_count": 1,
      "transporter_gene_count": 598,
      "evidence_sources": ["metabolism", "metabolomics", "transport"],
      "go_transport_organism_names": null,
      "go_transport_organism_count": null,
      "chebi_id": "15351",
      "pathway_ids": [
        "kegg.pathway:ko00010",
        "kegg.pathway:ko00020",
        "kegg.pathway:ko00061",
        "kegg.pathway:ko00062",
        "kegg.pathway:ko00071",
        ...
      ],
      "pathway_count": 57,
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
      "catalyst_gene_count": 512,
      "organism_count": 43,
      "transporter_count": 13,
      "transporter_gene_count": 4031,
      "evidence_sources": ["go_transport", "metabolism", "transport"],
      "go_transport_organism_names": ["Pseudomonas putida KT2440", "Shewanella sp. W3-18-1"],
      "go_transport_organism_count": 2,
      "chebi_id": "15366",
      "pathway_ids": [
        "kegg.pathway:ko00010",
        "kegg.pathway:ko00430",
        "kegg.pathway:ko00440",
        "kegg.pathway:ko00534",
        "kegg.pathway:ko00620",
        ...
      ],
      "pathway_count": 20,
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

### Example 9: Transport-only metabolites (TCDB substrates without local catalysis)

```example-call
list_metabolites(evidence_sources=["transport"], summary=True)
```

### Example 10: Transport-only metabolite by ID — reading the two gene counts together

```example-call
list_metabolites(metabolite_ids=["chebi:17234"])
```

```example-response
{
  "total_entries": 3243,
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
  "by_structure_kind": [{"structure_kind": "defined", "count": 1}],
  "by_kegg_functional_category": [{"kegg_functional_category": "not classified", "count": 1}],
  "by_kegg_brite_class": [{"kegg_brite_class": "not classified", "count": 1}],
  "score_max": null,
  "score_median": null,
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "resolved_aliases": {},
  "warnings": [],
  "no_formula_excluded": null,
  "results": [
    {
      "metabolite_id": "chebi:17234",
      "name": "glucose",
      "formula": "C6H12O6",
      "elements": ["C", "H", "O"],
      "mass": 180.156,
      "catalyst_gene_count": 0,
      "organism_count": 43,
      "transporter_count": 18,
      "transporter_gene_count": 3091,
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
          "catalyst_gene_count": 284,
          "transporter_gene_count": 1436
        }
      ]
    }
  ]
}
```

### Example 11: Stereo relatives — generic Cysteine carries the transport, L-Cysteine the catalysis

```example-call
list_metabolites(metabolite_ids=["kegg.compound:C00736", "kegg.compound:C00097"])
```

*Each row's `stereo_relatives` names the other stereo forms with their own KG-wide gene counts: Cysteine's `specific_form` relatives are L- and D-Cysteine, L-Cysteine's are its `enantiomer` D-Cysteine and its `unspecified_form` Cysteine. No count combines across forms. Rows with no relative have no `stereo_relatives` key.*

```example-response
{
  "total_entries": 3243,
  "total_matching": 2,
  "top_organisms": [
    {"organism_name": "Alteromonas macleodii AD45", "count": 2},
    {"organism_name": "Alteromonas macleodii ATCC27126", "count": 2},
    {"organism_name": "Alteromonas macleodii BGP6", "count": 2},
    {"organism_name": "Alteromonas macleodii BS11", "count": 2},
    {"organism_name": "Alteromonas macleodii EZ55", "count": 2},
    ...
  ],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko00270",
      "metabolite_pathway_name": "Cysteine and methionine metabolism",
      "count": 1
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00311",
      "metabolite_pathway_name": "Penicillin and cephalosporin biosynthesis",
      "count": 1
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00430",
      "metabolite_pathway_name": "Taurine and hypotaurine metabolism",
      "count": 1
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00460",
      "metabolite_pathway_name": "Cyanoamino acid metabolism",
      "count": 1
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko00470",
      "metabolite_pathway_name": "D-Amino acid metabolism",
      "count": 1
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "transport", "count": 2},
    {"evidence_source": "go_transport", "count": 1},
    {"evidence_source": "metabolism", "count": 1},
    {"evidence_source": "metabolomics", "count": 1}
  ],
  "xref_coverage": {"with_chebi": 2, "with_hmdb": 2, "with_mnxm": 2},
  "mass_stats": {"mass_min": 121.161, "mass_median": 121.161, "mass_max": 121.161},
  "by_measurement_coverage": {
    "by_paper_count": [{"paper_count": 0, "count": 1}, {"paper_count": 1, "count": 1}],
    "by_compartment": [{"compartment": "extracellular", "count": 1}, {"compartment": "whole_cell", "count": 1}]
  },
  "by_structure_kind": [{"structure_kind": "defined", "count": 2}],
  "by_kegg_functional_category": [
    {"kegg_functional_category": "Peptides", "count": 1},
    {"kegg_functional_category": "not classified", "count": 1}
  ],
  "by_kegg_brite_class": [{"kegg_brite_class": "not classified", "count": 2}],
  "score_max": null,
  "score_median": null,
  "returned": 2,
  "offset": 0,
  "truncated": false,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "resolved_aliases": {},
  "warnings": [],
  "no_formula_excluded": null,
  "results": [
    {
      "metabolite_id": "kegg.compound:C00097",
      "name": "L-Cysteine",
      "formula": "C3H7NO2S",
      "elements": ["C", "H", "N", "O", "S"],
      "mass": 121.161,
      "catalyst_gene_count": 652,
      "organism_count": 43,
      "transporter_count": 6,
      "transporter_gene_count": 2554,
      "evidence_sources": ["go_transport", "metabolism", "metabolomics", "transport"],
      "go_transport_organism_names": [
        "Alteromonas macleodii AD45",
        "Alteromonas macleodii ATCC27126",
        "Alteromonas macleodii BGP6",
        "Alteromonas macleodii BS11",
        "Alteromonas macleodii EZ55",
        ...
      ],
      "go_transport_organism_count": 13,
      "chebi_id": "17561",
      "pathway_ids": [
        "kegg.pathway:ko00260",
        "kegg.pathway:ko00270",
        "kegg.pathway:ko00311",
        "kegg.pathway:ko00430",
        "kegg.pathway:ko00460",
        ...
      ],
      "pathway_count": 23,
      "measured_assay_count": 8,
      "measured_paper_count": 1,
      "measured_organisms": ["Prochlorococcus MIT0801", "Prochlorococcus MIT9301", "Prochlorococcus MIT9313"],
      "measured_compartments": ["extracellular", "whole_cell"],
      "structure_kind": "defined",
      "kegg_functional_categories": ["Peptides"],
      "stereo_relatives": [
        {
          "metabolite_id": "kegg.compound:C00793",
          "name": "D-Cysteine",
          "relation": "enantiomer",
          "catalyst_gene_count": 12,
          "transporter_gene_count": 0
        },
        {
          "metabolite_id": "kegg.compound:C00736",
          "name": "Cysteine",
          "relation": "unspecified_form",
          "catalyst_gene_count": 0,
          "transporter_gene_count": 3197
        }
      ]
    },
    {
      "metabolite_id": "kegg.compound:C00736",
      "name": "Cysteine",
      "formula": "C3H7NO2S",
      "elements": ["C", "H", "N", "O", "S"],
      "mass": 121.161,
      "catalyst_gene_count": 0,
      "organism_count": 43,
      "transporter_count": 12,
      "transporter_gene_count": 3197,
      "evidence_sources": ["transport"],
      "go_transport_organism_names": null,
      "go_transport_organism_count": null,
      "chebi_id": "15356",
      "pathway_ids": [],
      "pathway_count": 0,
      "measured_assay_count": 0,
      "measured_paper_count": 0,
      "measured_organisms": [],
      "measured_compartments": [],
      "structure_kind": "defined",
      "stereo_relatives": [
        {
          "metabolite_id": "kegg.compound:C00097",
          "name": "L-Cysteine",
          "relation": "specific_form",
          "catalyst_gene_count": 652,
          "transporter_gene_count": 2554
        },
        {
          "metabolite_id": "kegg.compound:C00793",
          "name": "D-Cysteine",
          "relation": "specific_form",
          "catalyst_gene_count": 12,
          "transporter_gene_count": 0
        }
      ]
    }
  ]
}
```

### Example 12: Measured metabolites — measurement coverage envelope

```example-call
list_metabolites(evidence_sources=["metabolomics"], summary=True)
```

```example-response
{
  "total_entries": 3243,
  "total_matching": 135,
  "top_organisms": [
    {"organism_name": "Prochlorococcus MIT9313", "count": 134},
    {"organism_name": "Prochlorococcus MIT9301", "count": 127},
    {"organism_name": "Prochlorococcus MIT0801", "count": 126},
    {"organism_name": "Synechococcus elongatus PCC 7942", "count": 121},
    {"organism_name": "Alteromonas mediterranea AltDE1", "count": 121},
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
    {
      "metabolite_pathway_id": "kegg.pathway:ko02010",
      "metabolite_pathway_name": "ABC transporters",
      "count": 39
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01120",
      "metabolite_pathway_name": "Microbial metabolism in diverse environments",
      "count": 39
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "metabolomics", "count": 135},
    {"evidence_source": "metabolism", "count": 119},
    {"evidence_source": "transport", "count": 104},
    {"evidence_source": "go_transport", "count": 41}
  ],
  "xref_coverage": {"with_chebi": 135, "with_hmdb": 126, "with_mnxm": 133},
  "mass_stats": {"mass_min": 89.094, "mass_median": 179.172, "mass_max": 1353.372},
  "by_measurement_coverage": {
    "by_paper_count": [{"paper_count": 1, "count": 93}, {"paper_count": 2, "count": 37}, {"paper_count": 3, "count": 5}],
    "by_compartment": [
      {"compartment": "extracellular", "count": 92},
      {"compartment": "vesicle", "count": 70},
      {"compartment": "whole_cell", "count": 135}
    ]
  },
  "by_structure_kind": [{"structure_kind": "defined", "count": 135}],
  "by_kegg_functional_category": [
    {"kegg_functional_category": "Peptides", "count": 26},
    {"kegg_functional_category": "Vitamins and cofactors", "count": 16},
    {"kegg_functional_category": "Nucleic acids", "count": 13},
    {"kegg_functional_category": "Organic acids", "count": 8},
    {"kegg_functional_category": "Carbohydrates", "count": 5},
    ...
  ],
  "by_kegg_brite_class": [
    {"kegg_brite_class": "Lipids: Fatty acyls", "count": 6},
    {"kegg_brite_class": "Phytochemical compounds: Alkaloids", "count": 6},
    {"kegg_brite_class": "Glycosides: N-glycosides", "count": 5},
    {"kegg_brite_class": "Lipids: Prenol lipids", "count": 3},
    {"kegg_brite_class": "Pesticides: Pesticides", "count": 3},
    ...
  ],
  "score_max": null,
  "score_median": null,
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "resolved_aliases": {},
  "warnings": [],
  "no_formula_excluded": null,
  "results": []
}
```

### Example 13: Multi-step — find N-metabolites then drill into catalysts

```
Step 1: list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"], limit=10)
        → extract metabolite_ids of interest

Step 2: genes_by_metabolite(metabolite_ids=[chosen_ids], organism="Prochlorococcus MED4")
        → catalysing genes per metabolite
```

### Example 14: Currency-cofactor strip — exclude ATP/ADP/NADH/NADPH/H2O when top_metabolites is dominated by them

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

### Example 15: GO transport route — metabolites a GO transport term names (evidence_sources=['go_transport'])

```example-call
list_metabolites(evidence_sources=["go_transport"], organism_names=["Prochlorococcus MED4"], limit=5)
```

*Rows carry `go_transport_organism_names` / `go_transport_organism_count` (organisms with a gene annotated to a GO term that names this metabolite, direct annotations only). The `organism_names` filter matches either the KEGG/TCDB/assay organism list or the GO list, so GO-only metabolites appear for the organism too; `organism_count` and the gene counts still ignore the GO route. A metabolite with no `go_transport_organism_names` may still have a GO edge reached only through ancestor terms: absent means no directly annotated gene path.*

```example-response
{
  "total_entries": 3243,
  "total_matching": 165,
  "top_organisms": [
    {"organism_name": "Prochlorococcus MED4", "count": 165},
    {"organism_name": "Ruegeria pomeroyi DSS-3", "count": 165},
    {"organism_name": "Pseudomonas putida KT2440", "count": 164},
    {"organism_name": "Synechococcus WH8102", "count": 164},
    {"organism_name": "Prochlorococcus MIT9303", "count": 164},
    ...
  ],
  "top_metabolite_pathways": [
    {
      "metabolite_pathway_id": "kegg.pathway:ko01100",
      "metabolite_pathway_name": "Metabolic pathways",
      "count": 79
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko02010",
      "metabolite_pathway_name": "ABC transporters",
      "count": 55
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01110",
      "metabolite_pathway_name": "Biosynthesis of secondary metabolites",
      "count": 44
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko01120",
      "metabolite_pathway_name": "Microbial metabolism in diverse environments",
      "count": 33
    },
    {
      "metabolite_pathway_id": "kegg.pathway:ko04974",
      "metabolite_pathway_name": "Protein digestion and absorption",
      "count": 24
    },
    ...
  ],
  "by_evidence_source": [
    {"evidence_source": "go_transport", "count": 165},
    {"evidence_source": "transport", "count": 156},
    {"evidence_source": "metabolism", "count": 92},
    {"evidence_source": "metabolomics", "count": 41}
  ],
  "xref_coverage": {"with_chebi": 164, "with_hmdb": 94, "with_mnxm": 165},
  "mass_stats": {"mass_min": 18.015, "mass_median": 131.175, "mass_max": 719.349},
  "by_measurement_coverage": {
    "by_paper_count": [
      {"paper_count": 0, "count": 124},
      {"paper_count": 1, "count": 22},
      {"paper_count": 2, "count": 17},
      {"paper_count": 3, "count": 2}
    ],
    "by_compartment": [
      {"compartment": "extracellular", "count": 34},
      {"compartment": "vesicle", "count": 24},
      {"compartment": "whole_cell", "count": 41}
    ]
  },
  "by_structure_kind": [
    {"structure_kind": "defined", "count": 120},
    {"structure_kind": "generic", "count": 41},
    {"structure_kind": "polymer", "count": 4}
  ],
  "by_kegg_functional_category": [
    {"kegg_functional_category": "Peptides", "count": 22},
    {"kegg_functional_category": "Carbohydrates", "count": 6},
    {"kegg_functional_category": "Nucleic acids", "count": 6},
    {"kegg_functional_category": "Organic acids", "count": 5},
    {"kegg_functional_category": "Vitamins and cofactors", "count": 5},
    ...
  ],
  "by_kegg_brite_class": [
    {"kegg_brite_class": "Lipids: Fatty acyls", "count": 5},
    {"kegg_brite_class": "Lipids: Polyketides", "count": 2},
    {"kegg_brite_class": "Pesticides: Pesticides", "count": 2},
    {"kegg_brite_class": "Phytochemical compounds: Alkaloids", "count": 2},
    {"kegg_brite_class": "not classified", "count": 154}
  ],
  "score_max": null,
  "score_median": null,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "not_found": {"metabolite_ids": [], "organism_names": [], "pathway_ids": [], "elements": []},
  "resolved_aliases": {},
  "warnings": [],
  "no_formula_excluded": null,
  "results": [
    {
      "metabolite_id": "kegg.compound:C00001",
      "name": "H2O",
      "formula": "H2O",
      "elements": ["H", "O"],
      "mass": 18.015,
      "catalyst_gene_count": 10249,
      "organism_count": 43,
      "transporter_count": 15,
      "transporter_gene_count": 1900,
      "evidence_sources": ["go_transport", "metabolism", "transport"],
      "go_transport_organism_names": [
        "Meiothermus ruber",
        "Pseudomonas putida KT2440",
        "Ruegeria pomeroyi DSS-3",
        "Shewanella sp. W3-18-1",
        "Synechococcus PCC 7002"
      ],
      "go_transport_organism_count": 5,
      "chebi_id": "15377",
      "pathway_ids": [
        "kegg.pathway:ko00190",
        "kegg.pathway:ko00195",
        "kegg.pathway:ko00710",
        "kegg.pathway:ko01100",
        "kegg.pathway:ko04918",
        ...
      ],
      "pathway_count": 17,
      "measured_assay_count": 0,
      "measured_paper_count": 0,
      "measured_organisms": [],
      "measured_compartments": [],
      "structure_kind": "defined"
    },
    {
      "metabolite_id": "kegg.compound:C00009",
      "name": "Orthophosphate",
      "formula": "HO4P",
      "elements": ["H", "O", "P"],
      "mass": 95.978,
      "catalyst_gene_count": 4069,
      "organism_count": 43,
      "transporter_count": 15,
      "transporter_gene_count": 2867,
      "evidence_sources": ["go_transport", "metabolism", "transport"],
      "go_transport_organism_names": [
        "Alteromonas (MarRef v6)",
        "Alteromonas macleodii AD45",
        "Alteromonas macleodii ATCC27126",
        "Alteromonas macleodii BGP6",
        "Alteromonas macleodii BS11",
        ...
      ],
      "go_transport_organism_count": 43,
      "chebi_id": "26078",
      "pathway_ids": [
        "kegg.pathway:ko00190",
        "kegg.pathway:ko00195",
        "kegg.pathway:ko02010",
        "kegg.pathway:ko02020",
        "kegg.pathway:ko02024",
        ...
      ],
      "pathway_count": 10,
      "measured_assay_count": 0,
      "measured_paper_count": 0,
      "measured_organisms": [],
      "measured_compartments": [],
      "structure_kind": "defined"
    },
    {
      "metabolite_id": "kegg.compound:C00014",
      "name": "Ammonia",
      "formula": "H4N",
      "elements": ["H", "N"],
      "mass": 18.039,
      "catalyst_gene_count": 2106,
      "organism_count": 43,
      "transporter_count": 9,
      "transporter_gene_count": 442,
      "evidence_sources": ["go_transport", "metabolism", "transport"],
      "go_transport_organism_names": [
        "Alteromonas (MarRef v6)",
        "Alteromonas macleodii AD45",
        "Alteromonas macleodii ATCC27126",
        "Alteromonas macleodii BGP6",
        "Alteromonas macleodii BS11",
        ...
      ],
      "go_transport_organism_count": 43,
      "chebi_id": "16134",
      "pathway_ids": [
        "kegg.pathway:ko00220",
        "kegg.pathway:ko00230",
        "kegg.pathway:ko00250",
        "kegg.pathway:ko00260",
        "kegg.pathway:ko00460",
        ...
      ],
      "pathway_count": 19,
      "measured_assay_count": 0,
      "measured_paper_count": 0,
      "measured_organisms": [],
      "measured_compartments": [],
      "structure_kind": "defined"
    },
    ...
  ]
}
```

## Chaining patterns

```
list_organisms (per-row catalyzed_metabolite_count > 0) → list_metabolites(organism_names=[...])
list_metabolites → genes_by_metabolite(metabolite_ids=[...], organism=...)
list_metabolites (per-row `transporter_gene_count > 0`) → genes_by_metabolite(metabolite_ids=[...], organism=..., evidence_sources=['transport']) — distinct genes in the transport rows, summed over organisms, equal transporter_gene_count
list_metabolites (per-row `stereo_relatives`) → genes_by_metabolite(metabolite_ids=[generic id], organism=..., include_stereo_forms=True) — transport on the generic form plus catalysis on the specific form, per organism
list_metabolites (per-row pathway_ids) → genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...)
differential_expression_by_gene → metabolites_by_gene(metabolite_elements=['N']) → list_metabolites for chemistry context
list_metabolites (per-row `kegg_brite_classes`, top level only) → run_cypher over `MetaboliteClass` for the deeper KEGG compound classes (docs://analysis/metabolites)
list_metabolites (per-row `measured_assay_count > 0`) → assays_by_metabolite(metabolite_ids=[...]) — reverse lookup of all measurement evidence (numeric + boolean) for the measured compounds (cross-organism by default).
list_metabolites(evidence_sources=['go_transport'], organism_names=[...]) → genes_by_metabolite(metabolite_ids=[...], organism=..., evidence_sources=['go_transport']) for the genes carrying the GO term
```

## Common mistakes

- Direction-agnostic — KEGG equation order is unreliable upstream, so joins through Reaction_has_metabolite (catalysis) and Tcdb_family_transports_metabolite (transport) do NOT distinguish substrates from products. Layer DE direction (`differential_expression_by_gene`) and functional annotation to disambiguate. See docs://analysis/metabolites.

- catalyst_gene_count counts the catalysis arm only (genes reaching the metabolite via Gene → Reaction → Metabolite). catalyst_gene_count = 0 does NOT mean metabolomics-only: transport-only metabolites (TCDB substrates with no local catalysis) also read 0. Discriminate via the paired counts: catalyst_gene_count = 0 with `transporter_gene_count > 0` is transport-only; both 0 with `evidence_sources == ['metabolomics']` is measurement-only (no gene path). `transporter_gene_count` counts distinct genes over their deepest TCDB attachments, all organisms — it equals the distinct genes `genes_by_metabolite` returns in transport rows, summed over organisms.

- A 0 `catalyst_gene_count` on a generic (stereo-unspecified) metabolite does not mean no enzyme acts on the compound. Stereo forms are separate nodes and no count combines across them: TCDB names substrates generically, so transport sits on 'Cysteine' (`kegg.compound:C00736`, 0 catalysts), while KEGG reactions use the specific form, so catalysis sits on 'L-Cysteine' (`kegg.compound:C00097`). Read the row's `stereo_relatives` (`relation` = `specific_form` / `unspecified_form` / `enantiomer`, each with its own `catalyst_gene_count` / `transporter_gene_count`), then use `genes_by_metabolite(..., include_stereo_forms=True)` for a per-organism transport ↔ catalysis join. A generic's `specific_form` relatives can include a D-form. Stereo links are incomplete (e.g. 'glucose' `chebi:17234` has none yet), so an absent `stereo_relatives` is not proof of no other form: `search_text` by name lists every form.

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
`Fe`) for the ~12 elements this KG's chemistry layer carries. An
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
Metabolite IDs on `metabolite_ids` / `exclude_metabolite_ids` are normalised and
looked up in every identifier the metabolite carries before the query runs:
`C00064` / `kegg.compound:c00064` → `kegg.compound:C00064`, `CHEBI:17234` /
`17234` → `chebi:17234`; `HMDB0000122`, `MNXM732398` and bare InChIKeys resolve
the same way. Retired ids of merged or re-keyed nodes resolve to the surviving
node (`chebi:14654` → nitrate `kegg.compound:C00244`). Every input that isn't
already canonical is listed in envelope `resolved_aliases`
(`{input: [canonical, ...]}`). A removed compound whose measurements moved to
another compound, and a chemical-role id (`chebi:10004`, 'vitamin (role)'),
stay verbatim in `not_found` with a `warnings` entry naming the replacement or
the role. Other unresolved inputs stay verbatim in `not_found` in the form you
passed. The xref filters (`kegg_compound_ids`, `chebi_ids`, `hmdb_ids`, `mnxm_ids`) normalise each value the same way and match any of the metabolite's identifiers, including secondary and retired ones; they are filters, so they add nothing to `resolved_aliases`.

```

- See `docs://analysis/metabolites` for the 3 source pipelines decision tree (metabolism / transport / metabolomics) and `docs://guide/concepts` for the chemistry layer overview.

- `evidence_sources=['go_transport']` is a metabolite-level filter (a GO transport term names this compound), independent of the organism filter; the organism clause matches the union of `organism_names` and `go_transport_organism_names`. `catalyst_gene_count`, `transporter_gene_count` and `organism_count` stay KEGG / TCDB / assay only (no blending), so a GO-only metabolite reads zero on all three. Drill the GO route with `genes_by_metabolite`. See `docs://analysis/transport`.

## Package import equivalent

```python
from multiomics_explorer import list_metabolites

result = list_metabolites()
# returns dict with keys: total_entries, total_matching, top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, mass_stats, by_measurement_coverage, by_structure_kind, by_kegg_functional_category, by_kegg_brite_class, score_max, score_median, returned, offset, truncated, not_found, resolved_aliases, warnings, no_formula_excluded, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
