# Working with metabolites

LLM-facing decision-tree guide for metabolite questions. The KG models metabolites via three distinct source pipelines (metabolism, transport, metabolomics), each answering a different question class; transport evidence has two routes, TCDB `transport` and GO `go_transport` (`docs://analysis/transport`). **Read the disambiguation table first; pick the right row before drilling.**

Runnable companion: `docs://examples/metabolites.py` (7 scenarios).

> **Counts and per-gene distributions below are an illustrative snapshot** and
> drift with each KG rebuild. Use them for rough scale only; call
> `list_metabolites`, `list_metabolite_assays`, or `kg_release_info` for current
> figures.

## Source disambiguation

| `evidence_source` | Path in KG | Question it answers | Native tools | Key caveats |
|---|---|---|---|---|
| `metabolism` | `Gene → Reaction → Metabolite` (KEGG-derived) | "Which metabolites is this gene's reaction involved in?" | `genes_by_metabolite`, `metabolites_by_gene` (with `evidence_sources=['metabolism']`) | KO inference may be putative; `Reaction_has_metabolite` is undirected — upstream KEGG direction is unreliable, so the convention is permanent: use "involved in" framing, never "produces"/"consumes"; promiscuous enzymes inflate counts |
| `transport` | `Gene → TcdbFamily (tc_system) → Metabolite` (TCDB-derived) | "Which metabolites does this gene transport, through a TCDB system it is directly assigned to?" | `genes_by_metabolite`, `metabolites_by_gene` (with `evidence_sources=['transport']`) | Default rows need a `direct` system call; genes TCDB placed only at family or subfamily level need `include_tcdb_family_substrates=True` (family rows, a recall expansion); TCDB curation can be narrow (Pst → triphosphate only); direction is node-level (`tcdb_direction`), not per gene |
| `metabolomics` | `MetaboliteAssay → Metabolite` (mass-spec) | "Which metabolites were measured under this condition?" | `list_metabolite_assays` (discovery), `metabolites_by_quantifies_assay` / `metabolites_by_flags_assay` (per-arm drill-down), `assays_by_metabolite` (reverse lookup) — see Track B | No gene anchor; `Assay_quantifies` (concentration/intensity) ≠ `Assay_flags` (qualitative detection); compartment matters (`whole_cell` / `extracellular` / `vesicle`); ~149 of ~3.3k metabolites measured (~95% are annotation-only); 3 papers, 14 assays (12 numeric + 2 boolean), 12 experiments; replicate / normalisation conventions vary by paper |

The `metabolism` and `transport` rows share tools — the `evidence_source` field on result rows is the discriminator, and `tcdb_route ∈ {direct, family}`, `tcdb_identity` and `tcdb_calls` further qualify transport rows (see "Direct vs family substrates" under Track A2). The `metabolomics` row has dedicated tools — see Track B.

The `Metabolite.evidence_sources` list field on each Metabolite node already indicates which of the three pipelines contribute (e.g., `['metabolism', 'transport', 'metabolomics']`); read this to route quickly.

A fourth value, `go_transport`, marks the 208 metabolites that a GO transport term names as its primary input (GO's `has primary input` axiom; edges `Molecular_function_transports_metabolite` / `Biological_process_transports_metabolite` from the GO term). It is a term definition, not a gene fact, and it is kept apart from `transport` (TCDB): `organism_count`, `transporter_gene_count` and `catalyst_gene_count` ignore it. It is surfaced in `genes_by_metabolite` and `metabolites_by_gene` (`evidence_sources` accepts `go_transport`; GO rows carry `go_term_id`, `go_namespace`, `go_evidence`, `go_term_depth`, `target_kind`), in `gene_overview` (`evidence_sources` tag) and in `list_metabolites` (`go_transport_organism_names`). How to read the three transport-relevant routes side by side, what an empty GO answer means, and the Cypher examples: `docs://analysis/transport`.

**Metabolite ID forms.** Canonical `Metabolite.id` carries a namespace prefix: `kegg.compound:C00064`
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

Three inputs stay verbatim and land in `not_found`:

- **A removed compound** whose paper measurements were moved to a different compound — e.g.
  `kegg.compound:C00525` (D-tryptophan), whose rows now sit on L-tryptophan
  `kegg.compound:C00078`. A `warnings` entry names the new id. It is not resolved, because the
  two are different compounds; pass the new id yourself if the paper's stereo call is not the
  point.
- **A chemical-role id** — `chebi:10004` or `chebi.role:33229` ('vitamin (role)'). Roles
  (vitamin, siderophore, antibiotic, …) are `ChemicalRole` nodes, not metabolites; a
  `warnings` entry names the role. See "Chemical roles" under Track A f for the route to the
  TCDB families that transport them.
- **Anything else unknown** — a name such as `glutamate` (resolve names with
  `list_metabolites(search_text=...)` first), or an id the KG never carried.

`list_metabolites`' xref filters (`kegg_compound_ids`, `chebi_ids`, `hmdb_ids`, `mnxm_ids`)
normalise each value the same way and match it against `all_identifiers`, so secondary and
retired ids match too. They are filters, not resolution: they report nothing in
`resolved_aliases`.

**Molecule vs class (`structure_kind`).** `list_metabolites` rows carry `structure_kind`:
`defined` (one molecule), `generic` (a class such as 'Amino acid' or 'Acyl-CoA') or `polymer`
(DNA, glycogen). Generic and polymer nodes have no `mass` and carry generic formulas with a
placeholder (`C2H4NO2*` for 'Amino acid'), whose element set still feeds the `elements`
filter. Filter `structure_kind=['defined']` when a question is about specific molecules.

**Row schema is unified across both annotation arms.** `genes_by_metabolite` and `metabolites_by_gene` rows carry the full cross-arm key set — every row has `evidence_source`, `reaction_id`, `reaction_name`, `ec_numbers`, `mass_balance`, `tcdb_route`, `tcdb_family_id`, `tcdb_family_name`, `tcdb_calls`, `tcdb_identity`, `tcdb_direction`, with explicit `None` on the fields belonging to the other arm. Code against `evidence_source` to discriminate (or `tcdb_route is not None` for TCDB rows); the cross-arm `None`s mean every row has identical keys, no `KeyError` branching.

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
2. **Coverage is low.** Only 335 of 3,243 metabolites (~10%) carry a category. Common central
   metabolites the KG catalyses are often unclassified: 1,974 metabolites with catalyst genes
   have no category — fumarate, ethanol, L-carnitine and D-ribulose 5-phosphate among them.
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
   Coverage:
   - 652 of 3,243 metabolites (~20%) have a class;
   - with both fields, 884 (~27%) have something;
   - 687 of the 2,221 metabolites with catalyst genes have something.

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

## When to surface caveats inline

Always restate the row's caveats when the answer touches it. The LLM should never claim:

- "This gene produces X" — only "this gene catalyses a reaction involving X". This is the permanent convention: upstream KEGG annotation direction is unreliable, so the KG intentionally stays undirected.
- "This gene transports X" from a family row — a `tcdb_route='family'` row means the gene's TCDB family or subfamily has some system curated with X; the annotation can't pin the system. Say "this gene belongs to a TCDB family that includes a system moving X, so X is candidate-only". Quote `tcdb_identity` and `tcdb_calls` when you rank candidates; even a direct row is a homology call, not a measured activity.
- "No gene in this organism acts on X" from a `0` on one stereo form — a generic node (Cysteine) has 0 reactions by construction and the catalysts sit on the specific form (L-Cysteine). Read `stereo_relatives` first (see "Stereo forms: generic vs specific nodes").
- "Metabolite X was not produced under condition Y" based on metabolomics absence — say "X was not detected in the targeted panel under condition Y" (targeted ≠ comprehensive).

---

## Track A1 — Reaction (KEGG) annotation

For the chemistry the gene's reaction is involved in via curated KEGG annotations. Always restate inline: KO inference may be putative; reaction direction is **permanently undirected** in this KG (upstream KEGG direction is unreliable); promiscuous enzymes inflate counts. Reversibility is also not encoded on `Reaction` nodes — KEGG lacks an `is_reversible` flag upstream, so the KG carries no direction *and* no reversibility on reactions (permanently unmitigable).

### Distinguishing reaction direction

KEGG reactions are stored in the KG **without substrate-vs-product
direction** — KEGG equation order is unreliable upstream, so we do not
encode it. Joins through `Reaction_has_metabolite` and
`Tcdb_family_transports_metabolite` return both produced and
consumed metabolites identically.

To distinguish directionality, layer:

- **DE direction** (`differential_expression_by_gene` `direction='up'`
  vs `'down'`) — transcriptional response under treatment.
- **Functional annotation** (`gene_overview` Pfam/KO labels —
  `*-synthase` vs `*-permease`, `*-dehydrogenase` vs
  `*-hydratase`) — text-level disambiguation.

### a — Metabolite discovery & filtering

**Tool:** `list_metabolites`.

**When:** "what metabolites does the KG know about, filtered by element / mass / pathway / xref / organism" — discovery before downstream drill-down.

```python
result = list_metabolites(
    elements=["N"],                  # presence-only AND-of (here: N-bearing)
    pathway_ids=["map00910"],        # nitrogen metabolism
    organism_names=["Prochlorococcus MED4"],
    limit=20,
)
# Read result["top_metabolite_pathways"], result["top_organisms"], result["xref_coverage"],
# result["mass_stats"], result["by_evidence_source"].
```

The envelope `by_evidence_source` already breaks down by metabolism / transport / metabolomics — useful for routing.

### b1 — Reaction-anchored: compound → genes

**Tool:** `genes_by_metabolite` filtered to `evidence_sources=['metabolism']`.

**When:** "which MED4 genes catalyse a reaction involving glucose?"

```python
result = genes_by_metabolite(
    metabolite_ids=["C00031"],            # glucose — bare KEGG ID, coerced to kegg.compound:C00031
    organism="MED4",
    evidence_sources=["metabolism"],
)
# Each row has evidence_source="metabolism", an EC number, a reaction_id.
```

### c1 — Reaction-anchored: gene → metabolites

**Tool:** `metabolites_by_gene` filtered to `evidence_sources=['metabolism']`.

**When:** "which metabolites does PMM0001 catalyse reactions involving?"

```python
result = metabolites_by_gene(
    locus_tags=["PMM0001"],
    organism="MED4",
    evidence_sources=["metabolism"],
)
# Read result["by_element"] (chemistry signature) and result["top_metabolite_pathways"]
# (chemistry-pathway distinction — see caveat below).
```

**`by_element` semantics — presence-only, not stoichiometric.** Each row carries `metabolite_count` = the count of *distinct compounds in the full match set* that contain that element at all. E.g., `[('H', 6), ('O', 6), ('P', 6), ('C', 5), ('N', 4)]` over 6 distinct compounds means 6 contain H/O/P, 5 contain C, 4 contain N. It does **not** count atoms per compound (stoichiometry lives in `metabolite.formula`, e.g. `HO7P2` for diphosphate), and it is **not** mass-balanced across reactions — the KG intentionally carries no substrate-vs-product role on `Reaction_has_metabolite`. The per-row `elements` field is the same shape: a set of symbols, no counts. The envelope aggregates over `total_matching`, not the truncated page.

**Caveat — element filters skip formula-less metabolites.** `elements` / `metabolite_elements` never match a metabolite with no formula (mostly generic classes such as "amino acid", "dipeptide", "Polyamine"). When the filter is set, the envelope reports what it dropped (`no_formula_excluded`, plus `no_formula_excluded_metabolites` on `metabolites_by_gene`) and adds a `warnings` entry. Re-run without the element filter to inspect them.

**Caveat — `top_metabolite_pathways` is metabolite-anchored, NOT KO-anchored.** The chemistry-side `top_metabolite_pathways` traverses `Metabolite → KeggTerm` via the denormalized `m.pathway_ids` field (sourced from `Metabolite_in_pathway` edges). Target pathways are filtered by `KeggTerm.reaction_count >= 3` to drop signaling/disease pathways with no chemistry breadth — that's a *gate* on the target node, not part of the traversal. So this rollup answers **"which pathways do my gene's metabolites participate in?"** The envelope key is **`top_metabolite_pathways`** with per-element keys `metabolite_pathway_id` / `metabolite_pathway_name`, distinct from **ko-pathway** annotations (anchored on `Gene → KeggTerm` via the KO hierarchy, surfaced by `genes_by_ontology(ontology="kegg", ...)`, `pathway_enrichment`, etc.). They reach the same KEGG pathway maps but via different membership relations. Disambiguate explicitly when answering.

---

## Track A2 — Transport (TCDB) annotation

For substrates of the TCDB systems a gene is assigned to. Always restate inline: direct or family row, `tcdb_identity`, and that direction (`tcdb_direction`) is TCDB's statement about the node, not a per-gene fact.

### b2 — Transport-anchored: compound → genes

**Tool:** `genes_by_metabolite` filtered to `evidence_sources=['transport']`.

**When:** "which MED4 genes are predicted to transport nitrite?"

```python
result = genes_by_metabolite(
    metabolite_ids=["kegg.compound:C00088"],   # nitrite
    organism="MED4",
    evidence_sources=["transport"],
)
# Direct rows only by default: cynA / cynB / cynD on tcdb:3.A.1.16.1 / 3.A.1.16.2.
# Each row: tcdb_route="direct", tcdb_family_id = the system, tcdb_identity, tcdb_calls.
# result["tcdb_family_substrates_not_shown"] says what include_tcdb_family_substrates=True would add.
```

### c2 — Transport-anchored: gene → metabolites

**Tool:** `metabolites_by_gene` filtered to `evidence_sources=['transport']`.

**When:** "what does this gene's TCDB system transport?"

```python
result = metabolites_by_gene(
    locus_tags=["PMM0372"],                    # cynD
    organism="MED4",
    evidence_sources=["transport"],
)
# Two direct systems: tcdb:3.A.1.16.2 (cyanate, nitrite) and tcdb:3.A.1.16.1 (nitrate, nitrite).
# result["by_gene"][0]: tcdb_direct_rows, tcdb_family_rows, tcdb_assignment_count (2).
```

### g — Direct vs family substrates

TCDB curates substrates on **systems** (5-part TC numbers such as `tcdb:3.A.1.4.4`, level kind `tc_system`) and nowhere else. The KG stamps every gene → TCDB edge with a gate (`tcdb_gate`):

| `tcdb_gate` | Which calls | What it feeds |
|---|---|---|
| `direct` | a rank-1 DIAMOND best hit at tier ≤ 2 (≥ 40% identity), a tier-1 DIAMOND call, or an eggNOG call onto a system | transport rows, `transported_metabolite_count`, `transporter_gene_count` |
| `annotated` | other eggNOG calls; tier-2 DIAMOND calls (family / subfamily) | the TCDB annotation (`tcdb_assignment_count`, ontology rows, TERM2GENE) and family-walk starts |
| `below_gate` | tier-3 calls, near-tie best hits, best hits under 40% identity | nothing; evidence only (`include_weak_tcdb_hits=True` on `gene_ontology_terms`) |

**Direct rows (default).** One row per gene × system × metabolite, from `direct` edges only. Distinct Metabolite targets across a gene's direct rows equal `gene_overview.transported_metabolite_count`, and distinct genes across a metabolite's direct rows, summed over organisms, equal `list_metabolites.transporter_gene_count`. Rank within the route by `tcdb_identity` (percent identity of the representative DIAMOND edge; null on eggNOG-only calls), then by `tcdb_calls` (eggNOG plus a DIAMOND kind is independent agreement; `diamond_best_hit` and `diamond_tier` come from one DIAMOND run).

**Family rows (`include_tcdb_family_substrates=True`).** A fallback for genes TCDB could not place in a system. The walk starts from the gene's deepest `annotated` family or subfamily call, goes down to every system below it, and adds one `tcdb_route='family'` row per (gene, attached node, metabolite), with `tcdb_substrate_system_count` = how many of those systems carry the metabolite. The switch only adds rows. It never walks above a direct system the gene already has (that would add only the sibling systems' substrates), never starts from a class or subclass, and never starts from a node curated with more than 200 substrates (ABC `tcdb:3.A.1`, MFS `tcdb:2.A.1`): those genes are listed in `tcdb_family_substrates_skipped` (substrate unknown; `metabolites_by_gene` also warns, `genes_by_metabolite` does not).

- **Motivating case: phosphate in MED4.** `genes_by_metabolite(['kegg.compound:C00009'], organism='MED4')` (orthophosphate) returns no transport rows. phnD (PMM0673), the phosphonate-binding protein, has only an eggNOG call on subfamily `tcdb:3.A.1.9` (PhnT) plus a weak hit on the ABC superfamily. The envelope's `tcdb_family_substrates_not_shown` reads `{genes: 4, metabolites: 1, rows: 4}` (phnC, phnD, phnE, PMM0717) and the warning says to pass `include_tcdb_family_substrates=True`; with it, phnD reaches orthophosphate, phosphonic acid, phosphite, phosphinate and Fe³⁺ through `tcdb:3.A.1.9`.
- **Curation caveat: Pst.** MED4 pstA/B/C/S have direct calls onto `tcdb:3.A.1.7.6` ("High affinity phosphate-specific transporter, PstABCS"), which TCDB curates with **triphosphate only**. They therefore drop out of the orthophosphate answer, and because they have a direct system, no family walk brings them back. When a substrate answer looks too narrow, read the system names in `tcdb_family_name` and `top_tcdb_families`.
- **A real transporter can sit in family rows only.** MED4 gltS (PMM0628) has an eggNOG call on the glutamate:Na+ symporter family `tcdb:2.A.27` and only weak DIAMOND hits, so it has no direct rows; the walk reaches glutamate through the family.
- **Catch-all substrates.** TCDB curates some generic substrates ("molecule", "Peptide", "Protein"); they pass through as curated and can top family-row counts. Treat them as "some substrate".
- **Family rows are a recall expansion.** They say the gene's family moves the compound somewhere, not that the gene does. Most of their noise is eggNOG family calls on genes that are not transporters at all (cell-division, chaperone and protease genes among them). The KG has no per-gene transporter call yet, so do not count family rows as transport capability.

**Choose by question shape:**

- **Default (direct rows)** — conservative. Use for cross-organism inference and whenever over-claiming a substrate would mislead.
- **`include_tcdb_family_substrates=True`** — broad screen ("which transporters could plausibly act on these N substrates?"), or when the direct answer is empty and `tcdb_family_substrates_not_shown` is non-zero. Report family rows as candidates.
- **Pivot** for a single transporter family: `genes_by_ontology(ontology="tcdb", term_ids=[...])`. (For substrate-anchored questions prefer the metabolite-anchored route above.)

Scale in MED4: 203 genes carry a gate-passing TCDB call, 89 reach a substrate directly, and 98 have a gate-passing call but no direct edge (their transport arm is empty by default).

---

## Track A — Combined annotation workflows

Workflows that cross both reaction and transport arms, or that consume the annotation-side results downstream.

### d — Cross-feeding bridge (Workflow B′)

**When:** "what could MED4 produce that ALT might consume?" — between-organism metabolic coupling.

**Three structural confounders — apply mitigations or the bridge degenerates to "both organisms have water and ATP":**

| # | Confounder | Arm | Mitigation |
|---|---|---|---|
| 1 | **Currency cofactors flood the rollup.** `top_metabolites` is sorted by gene_count, which is exactly the wrong sort for cross-feeding because the highest-reach metabolites are universal (H2O, ATP/ADP/AMP, Pi, PPi, NAD(P)(H), CO2). | metabolism | Pass `exclude_metabolite_ids=CURRENCY_METABOLITES_MIN8` directly on the next call (tool-side filter — pushes the mitigation into the query so envelope rollups also benefit; available on `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`). Minimal-8 (H2O, CO2, ATP, ADP, AMP, Pi, PPi, NAD(P)(H)) is the conservative default — see `examples/metabolites.py::CURRENCY_METABOLITES_MIN8`. Extend with H+, Glu/Gln, CoA, FAD if the seed pulls them in (these are borderline and depend on whether you care about central-N flux as a signal). Set-difference semantics with `metabolite_ids` — exclude wins on overlap. |
| 2 | **Family-level transport casts a wide net.** Family rows (`include_tcdb_family_substrates=True`) reflect a family's whole curated range, not a per-gene substrate. For cross-feeding *inferences* (which over-claim a specific substrate flowing between organisms), keep the default direct rows. | transport | Leave `include_tcdb_family_substrates` off on the Step-2 `genes_by_metabolite` call; rank the direct rows by `tcdb_identity`, then `tcdb_calls`. **Note:** for *broad-screen* questions (e.g. "which transporters could plausibly act on N?", scenario `n_source_de`) the opposite call applies — turn the walk on so family-level candidates are included. |
| 3 | **Transport polarity is node-level at best.** TCDB rows carry `tcdb_direction` (`uptake` / `export` / `unknown`), read from TCDB's numbering or names for the node, not measured per gene, and most nodes read `unknown`. KEGG reactions are undirected. Even with clean filters, "MED4 has cynA, ALT has nrtA" tells you both touch the substrate, not who's the producer. | both | Use `tcdb_direction` as a hint only and surface the limitation in the answer ("compatible with", not "confirmed"). The Track-B measurement layer can corroborate (extracellular elevation in coculture) but cannot confirm causality. |

**Pattern (two-step, with all three mitigations applied):**

```python
# 0. Derive a biologically-motivated seed (don't pick random PMM IDs — housekeeping
#    genes carry only currency cofactors and zero transport).
CURRENCY = [  # minimal-8 (H2O, CO2, ATP, ADP, AMP, Pi, PPi, NAD(P)(H))
    "kegg.compound:C00001", "kegg.compound:C00011", "kegg.compound:C00002",
    "kegg.compound:C00008", "kegg.compound:C00020", "kegg.compound:C00009",
    "kegg.compound:C00013", "kegg.compound:C00003", "kegg.compound:C00004",
    "kegg.compound:C00005", "kegg.compound:C00006",
]
seed = genes_by_ontology(
    organism="MED4",
    ontology="kegg",
    term_ids=["kegg.pathway:ko00910"],   # Nitrogen metabolism — both arms exercised
)
seed_locus_tags = sorted({r["locus_tag"] for r in seed["results"]})

# 1. Harvest MED4-side metabolite IDs from gene-anchored chemistry. Apply
#    confounder #1 mitigation at the tool level via `exclude_metabolite_ids`
#    so the envelope's `top_metabolites` rollup itself is currency-free
#    (tool-side set-difference; exclude wins on overlap).
med4_chem = metabolites_by_gene(
    locus_tags=seed_locus_tags,
    organism="MED4",
    exclude_metabolite_ids=CURRENCY,                     # confounder #1 — tool-side
    summary=True,
)
metabolite_ids = [m["metabolite_id"] for m in med4_chem["top_metabolites"]]

# 2. Cross to ALT — split per-arm so both have airtime; the transport side keeps
#    direct TCDB rows only (the default). Pass `exclude_metabolite_ids`
#    again as a belt-and-braces guard (cross-organism enrichment can re-introduce
#    currency hits — exclude is harmless if the input is already clean).
alt_transport = genes_by_metabolite(
    metabolite_ids=metabolite_ids,
    organism="Alteromonas macleodii HOT1A3",   # one strain, not the species — keeps locus tags consistent and cuts cross-strain duplicate rows
    evidence_sources=["transport"],
    # confounder #2: include_tcdb_family_substrates stays False (direct rows only)
    exclude_metabolite_ids=CURRENCY,
)
alt_metab = genes_by_metabolite(
    metabolite_ids=metabolite_ids,
    organism="Alteromonas macleodii HOT1A3",   # one strain, not the species — keeps locus tags consistent and cuts cross-strain duplicate rows
    evidence_sources=["metabolism"],
    exclude_metabolite_ids=CURRENCY,
)
# Frame results as "compatible with cross-feeding" — confounder #3 is unmitigable.
```

See `examples/metabolites.py --scenario cross_feeding` for the runnable end-to-end with both arms printed and the cyn-cluster + glnA + glsF seed.

### e — N-source / nutrient-class workflow

**When:** "which MED4 genes act on nitrogen-containing metabolites — and which of those respond to N starvation?"

```python
# 1. N-bearing chemistry-side gene set.
chem = metabolites_by_gene(
    locus_tags=[...candidate pool...],
    organism="MED4",
    metabolite_elements=["N"],          # presence-only AND-of
    summary=True,
)
locus_tags = [g["locus_tag"] for g in chem["by_gene"]]

# 2. DE under N starvation.
de = differential_expression_by_gene(
    organism="MED4",
    locus_tags=locus_tags,
    direction="both",
    significant_only=True,
)
```

**Caveat — promiscuous enzymes and family-level transport substrates inflate the gene set fed to DE.** Tighten via `evidence_sources=['metabolism']`, or leave `include_tcdb_family_substrates` off, if results are noisy; `by_gene[].tcdb_direct_rows` / `tcdb_family_rows` tell you which genes contribute only family-level reach. Symmetric primitives exist for `metabolite_elements=['P']`, `['S']`, `['Fe']`, etc.

### f — Ontology bridges

**TCDB substrate-anchored:** for "which genes transport substrate X?", prefer the metabolite-anchored route (`genes_by_metabolite(metabolite_ids=[...], evidence_sources=['transport'])`) over the family-anchored route (`genes_by_ontology(ontology='tcdb', ...)`). The metabolite-anchored route includes all families curating the substrate; the ontology route is family-anchored and misses cross-family substrate hits.

**TCDB family-anchored context:** to see what a family *is* before trusting its substrate set — its level (class / subclass / family / subfamily), parents and children, `member_count` vs `gene_count`, and the Pfam domains / GO terms it is built from (`links_out`, composition) — use `ontology_term_details(term_ids=['tcdb:3.A.1'])`. Browse families by size with `search_ontology(ontology=['tcdb'], level=2)`. The full TCDB reference (identifier form, the `tcdb_gate` / `tcdb_call` edge model, `direction`, `tcdb_substrate_count`, pitfalls) is `docs://ontologies/tcdb`; the other ontologies are indexed at `docs://ontologies/index`.

**Chemical roles (siderophores, vitamins, antibiotics):** role terms are `ChemicalRole` nodes
(`chebi.role:<n>`), not metabolites, so `list_metabolites` does not return them. A role id is a
valid input to `genes_by_metabolite` and `metabolites_by_gene`, which return TCDB and GO role
rows (`target_kind='chemical_role'`). TCDB curates some substrates only as a role
("siderophore"); to see which systems carry a role and its narrower roles, use `run_cypher`:

```cypher
CALL db.index.fulltext.queryNodes('chemicalRoleFullText', 'siderophore')
YIELD node AS role, score
WITH role ORDER BY score DESC LIMIT 1
MATCH (sub:ChemicalRole)-[:Chemical_role_is_a_chemical_role*0..]->(role)
MATCH (s:TcdbFamily {level_kind: 'tc_system'})-[:Tcdb_family_transports_chemical_role]->(sub)
RETURN role.id AS role_id, s.id AS tcdb_system_id, s.name AS tcdb_system_name,
       s.gene_count AS gene_count, collect(DISTINCT sub.name) AS via_roles
ORDER BY gene_count DESC, tcdb_system_id
```

`*0..` includes the role itself plus its narrower roles. Substrate edges leave systems only, and
most systems carry no genes (`gene_count = 0`: TCDB's range, not this KG's genomes). For the genes,
call `genes_by_metabolite(metabolite_ids=[role_id], organism=...)`.

**KEGG pathway-anchored — pick the right surface:**
- **metabolite_pathways** (compound-anchored): which metabolites are in pathway X → `list_metabolites(pathway_ids=[...])`. Edge: `Metabolite_in_pathway`.
- **ko_pathways** (gene-KO-anchored): which genes are annotated to KOs in pathway X → `genes_by_ontology(ontology='kegg', ...)`. Edges: `Gene_has_kegg_ko` + `Kegg_term_is_a_kegg_term`.
- **reaction_pathways** (reaction-anchored, not currently surfaced as a rollup): which reactions a gene catalyses map to pathway X. Reach via `run_cypher` over `Gene_catalyzes_reaction` + `Reaction_in_kegg_pathway`.

The same KEGG pathway map (e.g. `kegg.pathway:ko00910` Nitrogen metabolism) can be reached from all three anchors, but membership relations are different — a gene whose KO is in pathway X may not catalyse any reaction whose metabolites are in pathway X (and vice versa). Always name the anchor when answering.

---

## Tested-absent vs unmeasured

> **Top-level invariant for the metabolomics layer.** Propagated across the 4 metabolomics tools (`list_metabolite_assays`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite`). Read this once; it determines how every row of every drill-down output is interpreted.

In metabolomics, **two row states must not be conflated**:

| State | Numeric arm | Boolean arm | What it means |
|---|---|---|---|
| Measured-present | `value > 0` and/or `detection_status ∈ {detected, sporadic}` | `flag_value = true` | Metabolite assayed and found. |
| **Tested-absent** | `value = 0`, `n_non_zero = 0`, `detection_status = 'not_detected'` | `flag_value = false` | Metabolite *assayed and not found*. **Real biological data — keep in `results`, count toward `total_matching` and envelope rollups.** |
| **Unmeasured** | no row in result; `metabolite_id` in `not_found` / `not_matched` | no row in result | Metabolite *not in this assay's scope*. **No information — do not infer absence.** |

Tested-absent rows answer the biological question "is X actually absent under condition Y." Discarding them silently misreads the question. Unmeasured rows carry zero information either way and must not be conflated with absence.

On the numeric arm (`metabolites_by_quantifies_assay` and the quantifies rows of `assays_by_metabolite`), a tested-absent row's `metric_bucket` / `metric_percentile` / `rank_by_metric` are always null — a raw-zero value can otherwise tie into a high bucket purely because most of the assay's edges are zero — and the rank-gated filters (`metric_bucket`, `min_percentile` / `max_percentile`, `max_rank`) never select `not_detected` rows for the same reason.

### Cross-tool implications

| Surface | Behavior |
|---|---|
| `total_matching` | Counts measured rows = present + tested-absent. Excludes unmeasured (no row exists to count). |
| `results` (default) | Includes tested-absent rows by default. |
| Envelope rollups (`by_detection_status`, `by_value`, `by_flag_value`, `by_assay`, `by_compartment`, `by_organism`, `by_metric`) | Include tested-absent rows. Lets callers see how much of `total_matching` is biological absence. |
| Edge-level filters (`min_value > 0`, `detection_status` list excluding `not_detected`, `flag_value=True`) | Caller-surfaced; never silently default-on. Each one drops tested-absent rows when set. |
| `assays_by_metabolite` `not_found` / `not_matched` buckets | **Unmeasured-only**. Tested-absent rows go in `results`, not these buckets. |

### Empirical scale

`detection_status` (`detected / sporadic / not_detected`) is the primary headline summary for the metabolomics layer. The breakdown shows tested-absent dominates:

- **Numeric arm (12 assays):** 70.7% of `Assay_quantifies` edges are `not_detected` (1046 of 1480 rows). Tested-absent is the majority signal, not an exception.
- **Boolean arm (2 assays, 186 rows total):** 68.8% have `flag_value = false` (128 of 186 rows).
- **PEP (`kegg.compound:C00074`):** 14 of 20 measurements (70%) are tested-absent across the 14 assays (12 `not_detected` quantifies-edges + 2 `flag_value=false` boolean-edges).

Default-filtering tested-absent rows would discard the majority of measured biology under this KG state.

### Tool-specific framing

- **`list_metabolite_assays`** (discovery / pre-flight): envelope `by_detection_status` rollup over numeric assays; per-row `detection_status_counts` on numeric rows. Use this surface to gauge tested-absent share before drilling.
- **`metabolites_by_quantifies_assay`** (numeric drill-down): `by_detection_status` is the primary headline. Edge-level `min_value > 0` and `detection_status` filters surfaced as caller choices, never default-on.
- **`metabolites_by_flags_assay`** (boolean drill-down): `by_flag_value` mirror; `flag_value=False` is the explicit way to ask for tested-absent rows.
- **`assays_by_metabolite`** (reverse lookup): `not_found` / `not_matched` buckets are unmeasured-only — the metabolite was never in the KG's metabolomics scope. Tested-absent rows for IN-scope metabolites are in `results`.

### Cross-references

- Tool-level YAML mistakes (each carries the wrong/right pair): `inputs/tools/list_metabolite_assays.yaml`, plus the 3 drill-down YAMLs.

---

## Track B — Metabolomics measurement

Four native tools cover the measurement layer (no `run_cypher` needed):

- **`list_metabolite_assays`** — discovery surface. Inspect `value_kind` (numeric/boolean → routes drill-down), `rankable` (gates `metric_bucket` / `min_percentile` / `max_percentile` / `max_rank` on the numeric drill-down), `compartment`, and per-row `detection_status_counts` (numeric assays) before drilling.
- **`metabolites_by_quantifies_assay`** — numeric-arm drill-down. One row per (metabolite × assay-edge) with `value`, `detection_status`, `timepoint*` and rankable-gated `metric_bucket` / `metric_percentile` / `rank_by_metric`. `by_detection_status` is the primary headline.
- **`metabolites_by_flags_assay`** — boolean-arm drill-down. Edge filter `flag_value` (`True` = presence flagged, `False` = tested-absent — real biology, 68.8% of boolean rows in the live KG).
- **`assays_by_metabolite`** — polymorphic reverse lookup. Cross-organism by default. Numeric rows carry `value` / `detection_status` / `timepoint*`; boolean rows carry `flag_value` / `n_positive`. Cross-arm fields explicit `None` (union-shape padding).

### Caveats — always restate when surfacing measurement results

- **No gene anchor.** A metabolite measurement says nothing about which gene produced/consumed it.
- **`Assay_quantifies` vs `Assay_flags`.** Quantifies = concentration/intensity (with `value`, `value_sd`, `n_replicates`, `metric_percentile`, `rank_by_metric`); Flags = qualitative detection (with `flag_value`, `n_positive`, `n_replicates`). Their downstream interpretation differs — split per DM convention into two drill-down tools.
- **Compartment matters.** `whole_cell` measures pool; `extracellular` measures excretion / uptake / spent media; `vesicle` measures cargo packaged into extracellular vesicles. Filter via the `compartment=` kwarg on every Track-B tool.
- **Targeted panel ≠ full metabolome.** Absence in measurement ≠ absence in cell. The current KG covers ~135 distinct metabolites across 14 assays in 3 papers — out of ~3.2k metabolites total, so ~96% have no measurement coverage.
- **Stereo form may be the KG's call, not the paper's.** Every measurement row carries
  `stereo_assignment`: `as_reported` (the paper named the form, or the compound has no stereo
  variant) or `dominant_form_assumed` (the paper gave no form — e.g. 'Alanine' — and the KG
  placed the row on one form of the stereo family, usually the one with the most catalysing
  genes, here L-alanine `kegg.compound:C00041`). The drill-downs add `by_stereo_assignment` to the envelope and a
  `warnings` entry when assumed rows are present; pass `stereo_assignment=['as_reported']` to
  keep only the paper's own calls. Say "measured as alanine (L-form assumed)" when quoting an
  assumed row. Transport for the same compound usually sits on the generic node (Alanine
  `kegg.compound:C01401`): see "Stereo forms: generic vs specific nodes".
- **Replicate / normalisation conventions vary by paper.** Read `value_sd` and `n_replicates` on the edge, plus `field_description` on the parent assay (canonical provenance read — `verbose=True` surfaces it). The `value` itself is processed per the paper's pipeline.
- **Tested-absent vs unmeasured.** See "Tested-absent vs unmeasured" above — the top-level invariant. Tested-absent rows (`value=0` / `detection_status='not_detected'` / `flag_value=false`) are biology, not noise; default-filtering them strips the majority of the layer.

### Discovery

```python
# 1. Inventory all metabolomics assays (mirrors list_derived_metrics — call first).
assays = list_metabolite_assays(summary=True)
# Read assays['by_value_kind'] (numeric vs boolean — picks the drill-down tool),
# assays['by_compartment'] (whole_cell / extracellular / vesicle),
# assays['by_treatment_type'], assays['by_detection_status']
# (cross-assay rollup for the numeric arm — primary headline).

# 2. Narrow by treatment / paper / organism.
p_assays = list_metabolite_assays(treatment_type=["phosphorus"], rankable=True)
# Today returns 2 numeric assays from 10.1128/msystems.01261-22 against MIT9301.
# Dropping rankable=True returns 4 (those 2 + 2 boolean assays, which are
# non-rankable and surface in excluded_assays if you pass rankable-gated
# filters with mixed input).
```

Current KG state:

| Paper | Assays | Compartments | Value kinds | Note |
|---|---|---|---|---|
| `10.1128/msystems.01261-22` (Kujawinski 2023) | 8 | whole_cell, extracellular | numeric (6) + boolean (2) | P-stress on MIT9301; KEGG-tagged + paper-level S2 flag table |
| `10.1073/pnas.2213271120` (Capovilla 2023, chitin paper) | 2 | whole_cell | numeric | MIT9303/MIT9313, carbon (chitosan addition) |
| `10.1111/1462-2920.15834` (vesicle paper) | 4 | whole_cell, vesicle | numeric | MIT9312 / MIT9313, growth_phase + compartment treatment |

Treatments observed: `phosphorus`, `growth_phase`, `carbon`, `compartment`. Compartments: `whole_cell` (9), `extracellular` (3), `vesicle` (2). Organisms: MIT9313 (5), MIT9301 (4), MIT9312 (2), MIT0801 (2), MIT9303 (1).

### Assay → metabolite drill-down

```python
# Numeric arm — pick assay_ids from list_metabolite_assays(value_kind='numeric').
result = metabolites_by_quantifies_assay(
    assay_ids=["metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration"],
    detection_status=["detected", "sporadic"],   # opt-out of tested-absent for a 'present-only' slice
    limit=20,
)
# Each row: metabolite_id, name, value, value_sd, detection_status,
# timepoint*, plus rankable-gated metric_bucket / metric_percentile / rank_by_metric.
# Envelope: by_detection_status (primary headline), by_metric (filtered slice +
# full-assay range echo), by_metric_bucket (rankable subset), by_assay.

# Top-decile drill on a rankable assay:
top_decile = metabolites_by_quantifies_assay(
    assay_ids=[<rankable_numeric_assay_id>],
    metric_bucket=["top_decile"],         # rankable-gated — raises if none of the assay set is rankable
    max_rank=10,                          # top-10 by rank_by_metric
)

# Boolean arm — pick assay_ids from list_metabolite_assays(value_kind='boolean').
flags = metabolites_by_flags_assay(
    assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"],
    flag_value=False,                     # tested-absent slice (real biology — 68.8% of boolean rows)
    limit=20,
)
# Each row: metabolite_id, name, flag_value, n_positive, n_replicates,
# metric_type, condition_label, assay_id.
```

### Metabolite → assay reverse lookup

```python
# Polymorphic — both arms merged via UNION ALL. Cross-organism by default.
result = assays_by_metabolite(
    metabolite_ids=["kegg.compound:C00064"],   # glutamine; ['kegg.compound:C00074'] is PEP
    limit=20,
)
# Numeric rows carry value / detection_status / timepoint*; boolean rows carry
# flag_value / n_positive. Cross-arm fields are explicit None.
# Envelope: by_evidence_kind (quantifies vs flags split), by_detection_status,
# by_flag_value, by_assay, by_organism, by_compartment.
# Three states per metabolite:
#   1. id in `not_found`      → not in KG (unmeasured)
#   2. id in `not_matched`    → in KG, no edge after filters (unmeasured for this scope)
#   3. row in `results` with `value=0` / `flag_value=false` → tested-absent (real biology)

# Scope to one arm if needed:
quantifies_only = assays_by_metabolite(
    metabolite_ids=["kegg.compound:C00064"],
    evidence_kind="quantifies",            # filtered-out arm's envelope rollup is empty
)
# `metabolites_matched` (distinct metabolite count) is the right field — NOT total_matching, which is row count.
```

For numeric details on a specific assay × metabolite combo, drill back via `metabolites_by_quantifies_assay(assay_ids=[...], metabolite_ids=[...])`.

### Cross-omics anchoring

When the user asks "did P stress change metabolite X (and which P-acting genes responded)?", combine:

```python
# 1. Metabolomics evidence — pick relevant assays then drill numeric values.
p_assays = list_metabolite_assays(treatment_type=["phosphorus"], value_kind="numeric")
mvals = metabolites_by_quantifies_assay(
    assay_ids=[a["assay_id"] for a in p_assays["results"]],
    metabolite_ids=["kegg.compound:C00074"],   # PEP, for example
    detection_status=["detected", "sporadic"],
)

# 2. Expression evidence — which P-acting genes responded under N starvation
#    (or P-stress). Follow the chemistry-filtered DE pattern below
#    (metabolites_by_gene metabolite_elements=['P'] → differential_expression_by_gene).

# 3. Surface both with their caveats; do not conflate "metabolite changed" with
#    "metabolite caused effect" or vice versa.
```

Time-point alignment between metabolomics and expression assays still varies by paper — confirm experiment `id` matches before joining (the current KG has no nitrogen-stress metabolomics experiments, so the canonical N-DE workflow can't be mirrored on the metabolite side; phosphorus and carbon are the available stress-treatment cross-omics pairings).

---

## Quick decision tree

```
User asks about a metabolite or chemistry
├─ "Can / does gene X act on metabolite M?"
│   ├─ "produce / catalyse" → Track A1 b1/c1 (metabolism arm)
│   └─ "transport" → Track A2 b2/c2 (transport arm) + g (substrate resolution / depth)
├─ "Which genes act on M?" → genes_by_metabolite (read evidence_source split)
├─ "M shows transport only / 0 catalysts" → read stereo_relatives; genes_by_metabolite(include_stereo_forms=True) for transport ↔ catalysis joins (Stereo forms section)
├─ "Which metabolites does gene X act on?" → metabolites_by_gene
├─ "Find metabolite by name → metabolite_id" → list_metabolites(search_text="...")  ← name-search hook; precedes any compound-anchored chain
├─ "Find metabolites by element / pathway / mass" → list_metabolites
├─ "Which metabolites are lipids / sugars / vitamins?" → list_metabolites(kegg_functional_categories=… / kegg_brite_classes=…) — partial, see KEGG compound categories
├─ "Which transporters carry siderophores / vitamins (a chemical role)?" → run_cypher ChemicalRole route (Track A f)
├─ "Cross-feeding between organisms" → Track A d — Cross-feeding bridge
├─ "N-source / chemistry-filtered DE" → Track A e — N-source / nutrient-class workflow
├─ "Genes that transport substrate X" → Track A2 b2 (metabolite-anchored; see also Track A f — Ontology bridges)
├─ "Genes annotated to TCDB family / KEGG term" → genes_by_ontology
├─ "What metabolomics assays exist for treatment / paper / organism?" → list_metabolite_assays  (Track B discovery)
├─ "Was metabolite M measured? At what level?" → assays_by_metabolite (cross-organism reverse lookup)
├─ "Top-N / detected-only metabolites in this numeric assay?" → metabolites_by_quantifies_assay
└─ "Which metabolites were flagged present/absent in this paper's S2 table?" → metabolites_by_flags_assay
```
