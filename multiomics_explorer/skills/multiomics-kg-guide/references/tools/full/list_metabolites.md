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
| evidence_sources | list[string ('metabolism', 'transport', 'metabolomics')] \| None | None | Filter by evidence path. Set-membership ANY semantics — ['transport'] returns transport-only AND dual. Valid values: 'metabolism' (catalysis-reachable), 'transport' (TCDB-curated substrate), 'metabolomics' (measured by a MetaboliteAssay). Other values raise at the MCP boundary. |
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
- **by_evidence_source** (list[MetEvidenceSourceBreakdown]): Frequency of evidence_sources values across matched set. Bounded by the {metabolism, transport, metabolomics} domain.
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
| evidence_sources | list[string] (optional) | Path provenance — values from {'metabolism', 'transport', 'metabolomics'}. 'metabolism' = at least one Reaction in KG involves this compound; 'transport' = at least one TcdbFamily curates this as substrate; 'metabolomics' = at least one MetaboliteAssay measures this compound. E.g. ['metabolism', 'transport']. |
| chebi_id | string \| None (optional) | ChEBI ID (raw numeric, e.g. '4167'). Populated on most metabolites — 100% of chebi:-IDed transport-only metabolites (extracted from the ID itself), plus the kegg.compound:-IDed metabolites that cross-ref ChEBI. |
| pathway_ids | list[string] (optional) | KEGG pathway memberships (e.g. ['kegg.pathway:ko00010', 'kegg.pathway:ko01100']). Empty when no Metabolite_in_pathway edges. Drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...). |
| pathway_count | int (optional) | Distinct count of KEGG pathways this metabolite is in (e.g. 5). Routing signal — when > 0, drill in via genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...) for genes annotated to those pathways. Equal to size(pathway_ids). |
| measured_assay_count | int (optional) | Distinct MetaboliteAssay edges anchored to this metabolite (precomputed Metabolite.measured_assay_count). When > 0, the metabolite has experimental measurement coverage. |
| measured_paper_count | int (optional) | Distinct papers measuring this metabolite (precomputed). Non-zero on metabolites with metabolomics evidence. |
| measured_organisms | list[string] (optional) | Organism preferred_names with at least one MetaboliteAssay anchored to this metabolite. Populated when measured_assay_count > 0; [] otherwise. |
| measured_compartments | list[string] (optional) | Wet-lab compartments observed for this metabolite (subset of {'whole_cell', 'extracellular', 'vesicle'}). Empty on unmeasured metabolites — use len(measured_compartments) >= 1 to filter for measurement-anchored rows. |
| score | float \| None (optional) | Lucene relevance score (only with `search_text`). |
| structure_kind | string \| None (optional) | 'defined' (one molecule), 'generic' (a compound class, e.g. 'amino acid') or 'polymer'. Generic and polymer entries have no formula-level chemistry. Values: list_filter_values('structure_kind'). |
| kegg_functional_categories | list[string] \| None (optional) | KEGG br08001 categories this metabolite is listed under. Absent = KEGG did not list it (~90% of metabolites), not 'none apply'. Curated, functional headings (amines sit under Peptides). |
| kegg_brite_classes | list[string] \| None (optional) | 'Tree: Class' from 7 KEGG compound BRITE trees (lipids, phytochemicals, glycosides, pesticides, toxins, endocrine disruptors, bioactive peptides). Absent = KEGG did not list it (~80% of metabolites). |

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
  "total_matching": 1,
  "resolved_aliases": {"chebi:14654": ["kegg.compound:C00244"]}
}
```

### Example 6: Generic classes and polymers — what is not a single molecule

```example-call
list_metabolites(structure_kind=["generic"], summary=True)
```

```example-response
{
  "total_matching": 624
}
```

### Example 7: KEGG functional category — describe, don't exclude (read the "not classified" tail)

```example-call
list_metabolites(kegg_functional_categories=["Peptides"], limit=3)
```

```example-response
{
  "total_matching": 60
}
```

### Example 8: KEGG BRITE class — top-level class of one of the 7 other compound trees

```example-call
list_metabolites(kegg_brite_classes=["Lipids: Fatty acyls"], limit=3)
```

```example-response
{
  "total_matching": 254
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
  "total_entries": 3214,
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
      "chebi_id": "17234",
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

### Example 11: Measured metabolites — measurement coverage envelope

```example-call
list_metabolites(evidence_sources=["metabolomics"], summary=True)
```

```example-response
{
  "total_entries": 3214,
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
    {"evidence_source": "transport", "count": 104}
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

### Example 12: Multi-step — find N-metabolites then drill into catalysts

```
Step 1: list_metabolites(organism_names=["Prochlorococcus MED4"], elements=["N"], limit=10)
        → extract metabolite_ids of interest

Step 2: genes_by_metabolite(metabolite_ids=[chosen_ids], organism="Prochlorococcus MED4")
        → catalysing genes per metabolite
```

### Example 13: Currency-cofactor strip — exclude ATP/ADP/NADH/NADPH/H2O when top_metabolites is dominated by them

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
list_metabolites (per-row `kegg_brite_classes`, top level only) → run_cypher over `MetaboliteClass` for the deeper KEGG compound classes (docs://analysis/metabolites)
list_metabolites (per-row `measured_assay_count > 0`) → assays_by_metabolite(metabolite_ids=[...]) — reverse lookup of all measurement evidence (numeric + boolean) for the measured compounds (cross-organism by default).
```

## Common mistakes

- Direction-agnostic — KEGG equation order is unreliable upstream, so joins through Reaction_has_metabolite (catalysis) and Tcdb_family_transports_metabolite (transport) do NOT distinguish substrates from products. Layer DE direction (`differential_expression_by_gene`) and functional annotation to disambiguate. See docs://analysis/metabolites.

- catalyst_gene_count counts the catalysis arm only (genes reaching the metabolite via Gene → Reaction → Metabolite). catalyst_gene_count = 0 does NOT mean metabolomics-only: transport-only metabolites (TCDB substrates with no local catalysis) also read 0. Discriminate via the paired counts: catalyst_gene_count = 0 with `transporter_gene_count > 0` is transport-only; both 0 with `evidence_sources == ['metabolomics']` is measurement-only (no gene path). `transporter_gene_count` counts distinct genes over their deepest TCDB attachments, all organisms — it equals the distinct genes `genes_by_metabolite` returns in transport rows, summed over organisms.

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

## Package import equivalent

```python
from multiomics_explorer import list_metabolites

result = list_metabolites()
# returns dict with keys: total_entries, total_matching, top_organisms, top_metabolite_pathways, by_evidence_source, xref_coverage, mass_stats, by_measurement_coverage, by_structure_kind, by_kegg_functional_category, by_kegg_brite_class, score_max, score_median, returned, offset, truncated, not_found, resolved_aliases, warnings, no_formula_excluded, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
