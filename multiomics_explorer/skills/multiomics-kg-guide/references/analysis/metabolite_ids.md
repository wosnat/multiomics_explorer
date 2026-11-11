# Metabolite ids, stereo forms and compound classes

Read when a metabolite id didn't resolve or resolved to something else (`not_found`, `resolved_aliases`), when an answer splits across stereo forms (Cysteine vs L-Cysteine; a `stereo_relatives` hint or a "Stereo forms hold more rows" warning), or when a row is a compound class rather than one molecule (`structure_kind='generic'`, KEGG compound categories). For which pipeline answers a metabolite question, start at `docs://analysis/metabolites`.

> Counts below are an illustrative snapshot and drift with each KG rebuild. Call
> `list_metabolites` or `kg_release_info` for current figures.

## Metabolite ID forms

Canonical `Metabolite.id` carries a namespace prefix: `kegg.compound:C00064`
(KEGG-keyed, the large majority) or `chebi:17234` (ChEBI-only, mostly TCDB substrates). Each
node also lists every identifier it answers to in `all_identifiers` — lower-case-prefixed
CURIEs for KEGG, ChEBI (primary and secondary), MetaNetX, HMDB and InChIKey
(`kegg.compound:C00244`, `chebi:14654`, `mnx:MNXM732398`, `hmdb:HMDB0000122`,
`inchikey:GRYLNZFGIOXLOG-UHFFFAOYSA-N`). Every entry sits on exactly one node.

Every `metabolite_ids` / `exclude_metabolite_ids` parameter on the seven chemistry /
metabolomics tools (`list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`,
`list_metabolite_assays`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`,
`assays_by_metabolite`) resolves its inputs before the query runs:

1. **Normalise the form.** `C00064` / `kegg.compound:c00064` → `kegg.compound:C00064`;
   `CHEBI:17234` / bare `17234` → `chebi:17234`; `MNXM732398` → `mnx:MNXM732398`;
   `HMDB02878` → `hmdb:HMDB0002878` (digits padded to 7); a bare InChIKey →
   `inchikey:<KEY>`.
2. **Look it up** as a node id first, then in every node's `all_identifiers`. This is how
   **retired ids** resolve: ids of nodes an earlier KG build merged or re-keyed now sit in
   the surviving node's `all_identifiers` (`chebi:14654` → nitrate `kegg.compound:C00244`;
   `kegg.compound:C01327`, hydrogen chloride, → chloride `kegg.compound:C00698`).
3. **Report.** Every input that isn't already the canonical id is listed in
   `resolved_aliases` (`{input: [canonical, ...]}`, empty when none), so a case fix, a
   prefix fix and a retired-id hop are all visible. Exclude-wins-on-overlap is evaluated on
   the canonical ids, so mixed forms across `metabolite_ids` and `exclude_metabolite_ids`
   still overlap correctly.

Three kinds of input do not resolve to a metabolite:

- **A removed compound** (stays verbatim in `not_found`) whose paper measurements were moved to a different compound — e.g.
  `kegg.compound:C00525` (D-tryptophan), whose rows now sit on L-tryptophan
  `kegg.compound:C00078`. A `warnings` entry names the new id. It is not resolved, because the
  two are different compounds; pass the new id yourself if the paper's stereo call is not the
  point.
- **A chemical-role id** — `chebi:10004` or `chebi.role:33229` ('vitamin (role)'). Roles
  (vitamin, siderophore, antibiotic, …) are `ChemicalRole` nodes, not metabolites.
  `genes_by_metabolite` and `metabolites_by_gene` resolve them (`chebi:10004` →
  `chebi.role:33229` in `resolved_aliases`) and return TCDB / GO role rows
  (`target_kind='chemical_role'`); a role with no edges in the organism lands in
  `not_matched`. `list_metabolites` and the four metabolomics tools keep the id verbatim in
  `not_found` with a `warnings` entry naming the role. Which TCDB systems carry a role:
  "Chemical roles" in `docs://analysis/metabolites`.
- **Anything else unknown** (stays in `not_found`) — a name such as `glutamate` (resolve names with
  `list_metabolites(search_text=...)` first), or an id the KG never carried.

`list_metabolites`' xref filters (`kegg_compound_ids`, `chebi_ids`, `hmdb_ids`, `mnxm_ids`)
normalise each value the same way and match it against `all_identifiers`, so secondary and
retired ids match too. They are filters, not resolution: they report nothing in
`resolved_aliases`.

## Molecule vs class (`structure_kind`)

`list_metabolites` rows carry `structure_kind`: `defined` (one molecule), `generic` (a class
such as 'Amino acid' or 'Acyl-CoA') or `polymer` (DNA, glycogen); `genes_by_metabolite` /
`metabolites_by_gene` rows carry the same value as `metabolite_structure_kind`. Generic and
polymer nodes have no `mass` and carry generic formulas with a placeholder (`C2H4NO2*` for
'Amino acid'), whose element set still feeds the `elements` filter. Filter
`structure_kind=['defined']` when a question is about specific molecules.

## Stereo forms: generic vs specific nodes

**The rule: a compound's stereo forms are separate metabolite nodes, and no count or row ever
combines across them.** "Cysteine" (`kegg.compound:C00736`, stereo form unspecified),
"L-Cysteine" (`kegg.compound:C00097`) and "D-Cysteine" (`kegg.compound:C00793`) are three
nodes, each with its own `catalyst_gene_count`, `transporter_gene_count` and gene rows.

**Why the split matters.** The three evidence sources name compounds differently, so they land
on different nodes of the same family:

| Source | Names compounds… | So its evidence sits on… | Example |
|---|---|---|---|
| TCDB substrate lists (`transport`) | generically ("cysteine", "alanine") | the **unspecified** node | Cysteine `C00736`: transporter genes only, **0** catalyst genes |
| KEGG reactions (`metabolism`) | as the specific form | the **specific** node | L-Cysteine `C00097`: the catalysts (and some transport) |
| Measured compounds whose paper gave no form (`metabolomics`) | placed on the most-catalysed form (`stereo_assignment='dominant_form_assumed'`) | usually the **specific L-form** | 'Alanine' measurements sit on L-Alanine `C00041`, while most alanine transport sits on Alanine `C01401` |

A question that joins transport to catalysis ("is the cysteine this transporter imports also
used by an enzyme here?") therefore needs both nodes. Stay on one and you silently get half the
answer: in MED4, `genes_by_metabolite` on Cysteine returns transport rows only (0 reactions),
while L-Cysteine carries the reactions. A `0` on one form is not a `0` for the compound.

**Relations.** The KG links forms with two edges, and the tools name what the relative is to the
metabolite it's attached to:

- `specific_form`: the relative is a stereo-specified form of this generic node
  (Cysteine → L-Cysteine, D-Cysteine).
- `unspecified_form`: the relative is the generic node of this specific form
  (L-Cysteine → Cysteine).
- `enantiomer`: the mirror-image form (L-Cysteine ↔ D-Cysteine). Only `list_metabolites` lists
  enantiomers. They are different compounds with different enzymes, so the gene tools never hint
  at them or add them.

A generic node's `specific_form` relatives can include a **D-form**: Alanine `C01401` has both
L-Alanine `C00041` and D-Alanine `C00133` as specific forms. Relatives are named, never
filtered. You decide which one fits the question.

**How to read it in each tool.**

- **`list_metabolites`**: per-row `stereo_relatives` (absent when the node has none), with
  `metabolite_id`, `name`, `relation` and the relative's own KG-wide `catalyst_gene_count` /
  `transporter_gene_count`. This is the first look: a generic row with `catalyst_gene_count = 0`
  whose `specific_form` relative has hundreds of catalysts is the split, not missing biology.
- **`genes_by_metabolite`**: envelope `stereo_relatives`, keyed by input metabolite id. Each
  entry carries `metabolite_id`, `name`, `relation` (`specific_form` / `unspecified_form`
  only) and **organism-scoped** `reaction_count` / `transporter_count` / `gene_count`, under
  the same filters as your call. These are exactly what `genes_by_metabolite` would report in
  `by_metabolite` for that relative. Only relatives with genes in this organism are listed, and
  relatives you passed in `metabolite_ids` or `exclude_metabolite_ids` are never hinted. The
  matching `by_metabolite` entry carries `stereo_relative_ids`, and the first `warnings` entry
  ("Stereo forms hold more rows: …") names the relatives with their counts. The hint fires
  whenever a relative has rows, even when the input has rows of its own.
- **`metabolites_by_gene`**: the same envelope `stereo_relatives`, keyed by every metabolite in
  your result that has a stereo relative, and per-row `stereo_relative_ids`. The relative's
  counts cover the **whole organism**, not just your input genes: the question it answers is
  "where else does this compound have genes here".
- **Metabolomics tools**: every measurement row carries `stereo_assignment` (`as_reported` /
  `dominant_form_assumed`); `stereo_assignment=['as_reported']` keeps only the paper's own
  calls. See the measurement caveats in `docs://analysis/metabolites`.

**When to cross the split: `genes_by_metabolite(include_stereo_forms=True)`.** This adds each
input's generic ↔ specific relatives to the query. The added rows and `by_metabolite` entries
carry `via_stereo_form_of` (the input id they came from), and the envelope's
`stereo_forms_added` maps each input to every relative it queried, including relatives with no
rows in this organism (those add nothing and never land in `not_matched`). No hint fires,
because the relatives are already in the result. Use it for:

- transport ↔ catalysis joins (generic transport, specific catalysis);
- "every gene that touches cysteine, in any form" screens.

Don't use it for:

- **exact-form questions** ("which genes act on L-cysteine specifically"): query the one id;
- **D-amino-acid biology** (peptidoglycan D-Ala, racemases): the expansion from a generic
  node can pull in the L-form *and* the D-form, so check the `via_stereo_form_of` rows by
  `metabolite_name` and drop the form that doesn't belong.

Enantiomers are never added, and the expansion is one hop. D-Alanine does not reach L-Alanine
through Alanine.

**MED4 worked example (cysteine).**

```python
from multiomics_explorer import genes_by_metabolite

r = genes_by_metabolite(metabolite_ids=["kegg.compound:C00736"],   # Cysteine (generic)
                        organism="Prochlorococcus MED4", summary=True)
# No direct rows: no MED4 gene has a TCDB system curated with Cysteine, and it has
#   0 reactions (KEGG uses L-Cysteine). Cysteine lands in not_matched.
# r["stereo_relatives"]["kegg.compound:C00736"]: L-Cysteine kegg.compound:C00097,
#   relation 'specific_form', with its own reaction / gene counts.
#   D-Cysteine is not listed: it has no MED4 genes.
# r["warnings"][0] starts "Stereo forms hold more rows: Cysteine (...) → L-Cysteine (...)";
# another warning says 5 genes reach Cysteine only through a family call
#   (tcdb_family_substrates_not_shown).

r = genes_by_metabolite(metabolite_ids=["kegg.compound:C00736"],
                        organism="Prochlorococcus MED4",
                        include_tcdb_family_substrates=True)
# 5 family rows: mcyH, mdlB, hetA, sodX on tcdb:3.A.1.106, glcH on tcdb:2.A.2
#   (tcdb_route='family' — candidates, not system calls).

r = genes_by_metabolite(metabolite_ids=["kegg.compound:C00736"],
                        organism="Prochlorococcus MED4", include_stereo_forms=True)
# r["stereo_forms_added"] == {"kegg.compound:C00736":
#     ["kegg.compound:C00097", "kegg.compound:C00793"]}   # L- and D-Cysteine queried;
#   D-Cysteine has no MED4 rows, so it adds nothing (and is not in not_matched).
# L-Cysteine's metabolism rows now appear, each with via_stereo_form_of="kegg.compound:C00736";
# r["by_metabolite"] has an L-Cysteine entry tagged the same way.
```

The gene-anchored route is the same split seen from the other side. `metabolites_by_gene` on
MED4's cysteine transporter candidates (e.g. PMM0065 mcyH, family `tcdb:3.A.1.106`) with
`include_tcdb_family_substrates=True` returns a Cysteine family row plus a `stereo_relatives`
entry pointing at L-Cysteine. Chain it into `genes_by_metabolite(metabolite_ids=
["kegg.compound:C00736"], organism=..., include_tcdb_family_substrates=True,
include_stereo_forms=True)` to get the transporter candidates and the L-cysteine enzymes in
one result.

**What is and isn't linked.** A link exists when ChEBI places the specific form under the
generic one with the same formula and charge (plus a short curated list), so common generic
substrates are covered: 'glucose' `chebi:17234` → D-Glucose `kegg.compound:C00031`, mannose →
D-Mannose, isoleucine → L-Isoleucine, fructose → D-Fructose. Two kinds are deliberately **not**
linked:
- **class terms** such as 'amino acid' `chebi:33709`, glucoside or galactoside, whose members are
  different compounds, not stereo forms;
- **ring vs open-chain forms** such as keto-D-fructose `kegg.compound:C10906` vs D-Fructose.

So a missing hint means "no stereo form in the KG", not "no related compound". For a class term
or an open-chain form, search by name (`list_metabolites(search_text="fructose")` lists every
node) and pass the form you want to `genes_by_metabolite` yourself.

An id that names a stereo form the KG has no node for (e.g. D-pipecolic acid `chebi:41582`) stays
in `not_found` with a warning naming the stereo-unspecified node it was removed from.

## KEGG compound categories: what they are and aren't

`list_metabolites` carries two KEGG classification fields — `kegg_functional_categories` and
`kegg_brite_classes` — as row fields, filters and envelope rollups
(`by_kegg_functional_category`, `by_kegg_brite_class`). Both are useful for describing a result
list and both are **partial**. Read this before using either to include, exclude or count.

1. **Source and method.** `kegg_functional_categories` holds the 9 top-level groups of KEGG BRITE
   hierarchy **br08001 "Compounds with biological roles"** (values:
   `list_filter_values('kegg_functional_category')`). br08001 is a hand-curated KEGG list:
   curators place selected **representative** compounds under functional headings. It is not an
   exhaustive or rule-based chemical classification. A compound is in a category only if KEGG
   listed it there; the KG copies KEGG's assignments and never infers a category.
2. **Coverage is low.** About one metabolite in ten (~10%) carries a category. Common central
   metabolites the KG catalyses are often unclassified — fumarate, ethanol, L-carnitine and
   D-ribulose 5-phosphate among them. `list_metabolites(summary=True)`'s
   `by_kegg_functional_category` gives the live split.
3. **Absence means "KEGG didn't list it", not "not in this category".** Fumarate is an organic
   acid and carries no category. The envelope's trailing `"not classified"` entry counts these
   metabolites so the gap stays visible. Never read a missing category as a negative.
   `"not classified"` is an envelope label only — the filter does not accept it.
4. **Functional, not structural headings.** Amino acids *and* amines (putrescine, dopamine) sit
   under Peptides; myo-inositol under Carbohydrates; retinol under Vitamins and cofactors. A
   compound can sit in more than one category (dopamine is also under Hormones and transmitters).
5. **Consequences for analysis.**
   - Use categories to *describe or group* a result list, not to *exclude* compounds.
   - For enrichment or "over-represented category" claims, the background is the classified
     metabolites only (those with at least one value in the field you test), never all
     metabolites — an unclassified compound is not a non-member.
   - For composition questions (N-containing, P-containing), use the `elements` filter instead.
6. **The second field, `kegg_brite_classes`**, holds KEGG's 7 other compound BRITE trees, as
   `"Tree: Class"` strings (values: `list_filter_values('kegg_brite_class')`):
   - Lipids br08002 (LIPID MAPS-style classes);
   - Phytochemical compounds br08003;
   - Glycosides br08021;
   - Pesticides br08007;
   - Natural toxins br08009;
   - Endocrine disrupting compounds br08006;
   - Bioactive peptides br08005.

   These are the same kind of hand-curated, representative-compound lists. Some are chemical
   (lipid and phytochemical classes, glycosides); others group compounds by use or effect
   (pesticides, toxins, endocrine disruptors). The tree prefix keeps same-named classes apart
   (`Pesticides: Pesticides` vs `Endocrine disrupting compounds: Pesticides and herbicides`).
   Coverage is about one metabolite in five (~20%); with both fields, roughly a quarter have
   something, and most metabolites with catalyst genes still have neither.

   Only the top level of each tree is on the row. Deeper classes (e.g. the lipid subclass
   'Fatty Acids and Conjugates') are `run_cypher`-only, through the `MetaboliteClass` hierarchy
   (`tree_code`, `level` 0 = top class):

   ```cypher
   MATCH (cls:MetaboliteClass {tree_code: 'br08002'})
   WHERE cls.name CONTAINS 'Fatty Acids and Conjugates'
   MATCH (sub:MetaboliteClass)-[:Metabolite_class_is_a_metabolite_class*0..]->(cls)
   MATCH (m:Metabolite)-[:Metabolite_in_metabolite_class]->(sub)
   RETURN cls.id AS class_id, m.id AS metabolite_id, m.name AS name,
          collect(DISTINCT sub.name) AS via_classes
   ORDER BY name
   LIMIT 50
   ```

   Points 3 and 5 apply unchanged.
7. **Two fields, two questions.** `kegg_functional_categories` answers "what is it for, in
   KEGG's functional grouping"; `kegg_brite_classes` answers "what kind of compound is it, or
   what is it used as". They overlap: butanoic acid is Lipids + Organic acids functionally, and
   `Lipids: Fatty acyls` + `Phytochemical compounds: Fatty acids related compounds` in BRITE.

See also: `docs://analysis/metabolites` (which pipeline answers the question),
`docs://analysis/transport` (transport routes), `docs://tools/list_metabolites`.
