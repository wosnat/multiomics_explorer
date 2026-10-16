# Working with metabolites

LLM-facing decision-tree guide for metabolite questions. The KG models metabolites via three distinct source pipelines, each answering a different question class. **Read the disambiguation table first; pick the right row before drilling.**

Runnable companion: `docs://examples/metabolites.py` (7 scenarios).

> **Counts and per-gene distributions below are an illustrative snapshot** and
> drift with each KG rebuild. Use them for rough scale only; call
> `list_metabolites`, `list_metabolite_assays`, or `kg_release_info` for current
> figures.

## Source disambiguation

| `evidence_source` | Path in KG | Question it answers | Native tools | Key caveats |
|---|---|---|---|---|
| `metabolism` | `Gene → Reaction → Metabolite` (KEGG-derived) | "Which metabolites is this gene's reaction involved in?" | `genes_by_metabolite`, `metabolites_by_gene` (with `evidence_sources=['metabolism']`) | KO inference may be putative; `Reaction_has_metabolite` is undirected — upstream KEGG direction is unreliable, so the convention is permanent: use "involved in" framing, never "produces"/"consumes"; promiscuous enzymes inflate counts |
| `transport` | `Gene → TcdbFamily → Metabolite` (TCDB-derived) | "Which metabolites does this gene transport (or could transport, via an inherited family substrate set)?" | `genes_by_metabolite`, `metabolites_by_gene` (with `evidence_sources=['transport']`) | `inherited` ≫ `most_specific` rows; superfamily-only genes read `transport_substrate_resolution='family_inferred'` (reachability, not capability) and trigger the auto-warning; rows are deepest-attachment projections; no import/export direction |
| `metabolomics` | `MetaboliteAssay → Metabolite` (mass-spec) | "Which metabolites were measured under this condition?" | `list_metabolite_assays` (discovery), `metabolites_by_quantifies_assay` / `metabolites_by_flags_assay` (per-arm drill-down), `assays_by_metabolite` (reverse lookup) — see Track B | No gene anchor; `Assay_quantifies` (concentration/intensity) ≠ `Assay_flags` (qualitative detection); compartment matters (`whole_cell` / `extracellular` / `vesicle`); ~149 of ~3.3k metabolites measured (~95% are annotation-only); 3 papers, 14 assays (12 numeric + 2 boolean), 12 experiments; replicate / normalisation conventions vary by paper |

The `metabolism` and `transport` rows share tools — the `evidence_source` field on result rows is the discriminator, and `substrate_depth ∈ {most_specific, inherited}` plus `tcdb_evidence_score` further qualify transport rows (see substrate resolution / depth under Track A2). The `metabolomics` row has dedicated tools — see Track B.

The `Metabolite.evidence_sources` list field on each Metabolite node already indicates which of the three pipelines contribute (e.g., `['metabolism', 'transport', 'metabolomics']`); read this to route quickly.

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

**Row schema is unified across both annotation arms.** `genes_by_metabolite` and `metabolites_by_gene` rows carry the full cross-arm key set — every row has `evidence_source`, `substrate_depth`, `tcdb_evidence_score`, `reaction_id`, `reaction_name`, `ec_numbers`, `mass_balance`, `tcdb_family_id`, `tcdb_family_name`, with explicit `None` on the fields belonging to the other arm. Code against `evidence_source` to discriminate (or `substrate_depth is not None` for transport-only); the cross-arm `None`s mean every row has identical keys, no `KeyError` branching.

## Stereo forms: generic vs specific nodes

**The rule: a compound's stereo forms are separate metabolite nodes, and no count or row ever
combines across them.** "Cysteine" (`kegg.compound:C00736`, stereo form unspecified),
"L-Cysteine" (`kegg.compound:C00097`) and "D-Cysteine" (`kegg.compound:C00793`) are three
nodes, each with its own `catalyst_gene_count`, `transporter_gene_count` and gene rows.

**Why the split matters.** The three evidence sources name compounds differently, so they land
on different nodes of the same family:

| Source | Names compounds… | So its evidence sits on… | Example |
|---|---|---|---|
| TCDB substrate lists (`transport`) | generically ("cysteine", "alanine") | the **unspecified** node | Cysteine `C00736`: many transporter genes, **0** catalyst genes |
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
# r["by_metabolite"][0]: reaction_count 0, transport only (TCDB names it generically).
# r["stereo_relatives"]["kegg.compound:C00736"]: L-Cysteine kegg.compound:C00097,
#   relation 'specific_form', e.g. 13 reactions / 3 transporter families / 38 genes.
#   D-Cysteine is not listed: it has no MED4 genes.
# r["warnings"][0] starts "Stereo forms hold more rows: Cysteine (...) → L-Cysteine (...)"

r = genes_by_metabolite(metabolite_ids=["kegg.compound:C00736"],
                        organism="Prochlorococcus MED4", include_stereo_forms=True)
# r["stereo_forms_added"] == {"kegg.compound:C00736":
#     ["kegg.compound:C00097", "kegg.compound:C00793"]}   # L- and D-Cysteine queried;
#   D-Cysteine has no MED4 rows, so it adds nothing (and is not in not_matched).
# L-Cysteine's metabolism rows now appear, each with via_stereo_form_of="kegg.compound:C00736";
# r["by_metabolite"] has an L-Cysteine entry tagged the same way.
```

The gene-anchored route is the same split seen from the other side. `metabolites_by_gene` on
MED4's cysteine transporters (e.g. PMM0065 mcyH, on `tcdb:3.A.1.106`) returns Cysteine
transport rows plus a `stereo_relatives` entry pointing at L-Cysteine. Chain it into
`genes_by_metabolite(metabolite_ids=["kegg.compound:C00736"], organism=...,
include_stereo_forms=True)` to get the transporters and the L-cysteine enzymes in one result.

**Stereo links are incomplete.** Some generic nodes have no link to their specific forms yet
(mannose, isoleucine and glucose among them: 'glucose' `chebi:17234` is not linked to D-Glucose
`kegg.compound:C00031`). A missing hint is therefore **not** proof that there is no other form.
When a generic substrate shows transport only, search by name:
`list_metabolites(search_text="isoleucine")` lists every node, and you can pass the specific
form's id to `genes_by_metabolite` yourself.

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
2. **Coverage is low.** Only 334 of 3,214 metabolites (~10%) carry a category. Common central
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
   - 652 of 3,214 metabolites (~20%) have a class;
   - with both fields, 883 (~27%) have something;
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
- "This gene transports X" without qualifying the evidence — when the gene reads `transport_substrate_resolution='family_inferred'`, or the row is `substrate_depth='inherited'`, X came down from a lumping family's substrate set; we don't know which specific subfamily applies. Say "this gene belongs to a TCDB family whose substrate set includes X — the annotation can't pin the subfamily, so X is candidate-only". Quote the `tcdb_evidence_score` when you rank candidates.
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

For substrates the gene's TCDB family transports. Always restate inline: substrate resolution and depth (score → resolution → depth, section g below); ABC superfamily promiscuity; no direction.

### b2 — Transport-anchored: compound → genes

**Tool:** `genes_by_metabolite` filtered to `evidence_sources=['transport']`.

**When:** "which MED4 genes are predicted to transport glycine betaine?"

```python
result = genes_by_metabolite(
    metabolite_ids=["C00719"],            # glycine betaine
    organism="MED4",
    evidence_sources=["transport"],
    substrate_depth=["most_specific"],    # tighten when inherited rows dominate
)
# Each row has evidence_source="transport", substrate_depth ∈ {most_specific, inherited}
# and tcdb_evidence_score (rank by it; never treat 0 as "absent").
```

### c2 — Transport-anchored: gene → metabolites

**Tool:** `metabolites_by_gene` filtered to `evidence_sources=['transport']`.

**When:** "what does this gene's TCDB family transport?"

```python
result = metabolites_by_gene(
    locus_tags=["PMM0001"],
    organism="MED4",
    evidence_sources=["transport"],
)
# Detail rows are sorted metabolism → most_specific → inherited, then tcdb_evidence_score desc.
# result["by_gene"][i] carries transport_substrate_resolution + tcdb_evidence_score_max.
```

### g — Substrate resolution and depth (score → resolution → depth)

Both depths are annotations, not ground truth — transporter specificity in nature is often promiscuous or under-characterized. TCDB substrates are attached to transporter family nodes and inherited down the family hierarchy, so a gene annotated to a broad family (common in homology-based annotation) still surfaces candidate substrates. Read transport evidence top-down through three fields, each answering a different question:

1. **`tcdb_evidence_score`** (row) / **`tcdb_evidence_score_max`** (gene; `gene_overview` rows, `genes_by_metabolite.top_genes[]`, `metabolites_by_gene.by_gene[]`) — *how corroborated is the gene × family call?* Rank by it; never filter by it. `0` is an uncorroborated hit; absent is `None` (no TCDB call). The `'tcdb' ∈ annotation_types` gate on `gene_overview` is the binary version of the same evidence; the score is the graded one.
2. **`transport_substrate_resolution`** (gene) — *is the gene's substrate breadth meaningful?* `family_inferred` = every deepest attachment is a lumping family (reachability, not capability); `resolved` = at least one deepest attachment is non-lumping — not all of them. A gene attached at both a specific family and the ABC superfamily is `resolved` and still carries the superfamily rollup in its `transported_metabolite_count`; only the row level separates them. The gene's value is repeated on each of its transport rows (`None` on metabolism rows) so a batch scan can drop `family_inferred` rows without joining back to `by_gene[]` / `top_genes[]`; it never varies across one gene's rows.
3. **`substrate_depth`** (row) — *where does this substrate sit for this family?* `most_specific` = the most specific **surviving** transporter node in the gene-pruned hierarchy (can be a family node, e.g. nitrite via `tcdb:2.A.16` in MED4; not a curation level); `inherited` = came down from an ancestor's substrate set (usually the ABC superfamily `tcdb:3.A.1`).

**What "lumping" means.** A TCDB family is *lumping* when the KG marks it
`TcdbFamily.substrate_breadth = 'lumping'`: a pinned set of broad superfamilies and families
(the ABC superfamily `tcdb:3.A.1`, MFS `tcdb:2.A.1`, APC `tcdb:2.A.3`, …) whose substrate list
pools what their many subfamilies carry, so a substrate count there is reachability, not
capability. The other values are `specific` (level 2 or deeper and not lumping) and
`not_assessed` (TCDB class / subclass nodes, whose substrate counts grow with level by
construction). The set is curated, not a cutoff — a `level` / `metabolite_count` threshold does
not reproduce it, so read the property instead (`ontology_term_details(term_ids=[...],
verbose=True)` shows it under `properties`). `transport_substrate_resolution` and the
`substrate_depth` warnings are built on this property.

**Rows are deepest-attachment projections.** A gene attached to a family *and* to one of its descendants contributes rows only through the descendant; the ancestor's substrate rollup is intentionally absent. So distinct metabolites across a gene's transport rows equal `gene_overview.transported_metabolite_count` (PMM0392: 13, not the ABC-superfamily plateau of 554), and distinct genes across a metabolite's transport rows, summed over organisms, equal `list_metabolites.transporter_gene_count`. Full family membership, ancestors included, is visible via `gene_ontology_terms(ontology=['tcdb'], mode='leaf', include_superseded=True)` — without `include_superseded=True` leaf mode also shows deepest attachments only.

**Choose the depth filter by question shape, not by reflex toward "high confidence":**

- **`substrate_depth=['most_specific']`** — narrower, more conservative cast. Use when the downstream inference is fragile (cross-organism cross-feeding) or when over-claiming specific substrates would mislead.
- **No filter / both depths** — broader cast that includes inherited family potential. Use for screening questions ("which transporters could plausibly act on N substrates?") where you'd rather over-include and let downstream evidence (e.g. DE response) anchor the interpretation. A real N-uptake transporter can sit entirely in inherited rows: PMM0628 (gltS) reaches its 5 substrates via `inherited` rows only, so `most_specific` alone silently excludes it (PMM0263 amt1, by contrast, has 7 `most_specific` rows and 0 inherited).
- **Pivot** for a single transporter family: `genes_by_ontology(ontology="tcdb", term_ids=[...])`. (But for substrate-anchored questions — "which genes transport X" — prefer the metabolite-anchored route under "Track A2 — Transport (TCDB) annotation".)

The auto-warning is informational, not a defect signal. `genes_by_metabolite` fires it when inherited rows dominate the transport rows (nitrite × MED4: 23 of the 29 deepest-attachment rows are inherited via `tcdb:3.A.1`); `metabolites_by_gene` fires it when input genes read `transport_substrate_resolution='family_inferred'` — their substrate breadth is reachability, not capability.

Empirical scale: the 13 MED4 genes carrying `transport_substrate_resolution='family_inferred'` (e.g. PMM0913 salY, PMM0434 ftsE) plateau at the ABC-superfamily rollup — 518 transport rows each, of which 301 are `inherited` and **217 are `most_specific` at `tcdb:3.A.1` itself** (substrates no kept child of the superfamily carries). `substrate_depth=['most_specific']` therefore does *not* remove superfamily-only genes; `most_specific` at a lumping superfamily is a superfamily-level position, not a subfamily call, and the gene-level resolution is the only guard against reading those substrates. PMM0392, by contrast, is attached to seven ABC subfamilies, so under the deepest-attachment rule it reads 12 metabolites, `resolved`, score 0.8. Expect the warning when querying common metabolites against MED4.

---

## Track A — Combined annotation workflows

Workflows that cross both reaction and transport arms, or that consume the annotation-side results downstream.

### d — Cross-feeding bridge (Workflow B′)

**When:** "what could MED4 produce that ALT might consume?" — between-organism metabolic coupling.

**Three structural confounders — apply mitigations or the bridge degenerates to "both organisms have water and ATP":**

| # | Confounder | Arm | Mitigation |
|---|---|---|---|
| 1 | **Currency cofactors flood the rollup.** `top_metabolites` is sorted by gene_count, which is exactly the wrong sort for cross-feeding because the highest-reach metabolites are universal (H2O, ATP/ADP/AMP, Pi, PPi, NAD(P)(H), CO2). | metabolism | Pass `exclude_metabolite_ids=CURRENCY_METABOLITES_MIN8` directly on the next call (tool-side filter — pushes the mitigation into the query so envelope rollups also benefit; available on `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`). Minimal-8 (H2O, CO2, ATP, ADP, AMP, Pi, PPi, NAD(P)(H)) is the conservative default — see `examples/metabolites.py::CURRENCY_METABOLITES_MIN8`. Extend with H+, Glu/Gln, CoA, FAD if the seed pulls them in (these are borderline and depend on whether you care about central-N flux as a signal). Set-difference semantics with `metabolite_ids` — exclude wins on overlap. |
| 2 | **Family-level transport casts a wide net.** Superfamily-only genes (especially ABC, `tcdb:3.A.1`) inherit ~518 substrates each via the family rollup. Substrate specificity is often unknown or context-dependent in nature — `inherited` rows reflect family-level potential, not per-substrate confirmation. For cross-feeding *inferences* (which over-claim a specific substrate flowing between organisms), the conservative `most_specific` cast is preferable. | transport | `substrate_depth=['most_specific']` on the Step-2 `genes_by_metabolite` call; then rank the survivors by `tcdb_evidence_score`. **Note:** for *broad-screen* questions (e.g. "which transporters could plausibly act on N?", scenario `n_source_de`) the opposite call applies — drop the filter so inherited biology is included; see the broad-screen note below. |
| 3 | **Transport polarity not encoded.** TCDB annotation says "transports X" without import/export direction (TCDB lacks direction upstream; permanently unmitigable). Even with clean filters, "MED4 has cynA, ALT has nrtA" tells you both touch the substrate, not who's the producer. | both | None on the annotation side — surface the limitation in the answer ("compatible with", not "confirmed"). The Track-B measurement layer can corroborate (extracellular elevation in coculture) but cannot confirm causality. |

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

# 2. Cross to ALT — split per-arm so both have airtime and the inherited
#    superfamily plateau is killed on the transport side only. Pass `exclude_metabolite_ids`
#    again as a belt-and-braces guard (cross-organism enrichment can re-introduce
#    currency hits — exclude is harmless if the input is already clean).
alt_transport = genes_by_metabolite(
    metabolite_ids=metabolite_ids,
    organism="Alteromonas macleodii HOT1A3",   # one strain, not the species — keeps locus tags consistent and cuts cross-strain duplicate rows
    evidence_sources=["transport"],
    substrate_depth=["most_specific"],                   # confounder #2
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

**Caveat — promiscuous enzymes / inherited transport substrates inflate the gene set fed to DE.** Tighten via `evidence_sources=['metabolism']` or `substrate_depth=['most_specific']` if results are noisy; `by_gene[].transport_substrate_resolution` tells you which genes contribute reachability rather than capability. Symmetric primitives exist for `metabolite_elements=['P']`, `['S']`, `['Fe']`, etc.

### f — Ontology bridges

**TCDB substrate-anchored:** for "which genes transport substrate X?", prefer the metabolite-anchored route (`genes_by_metabolite(metabolite_ids=[...], evidence_sources=['transport'])`) over the family-anchored route (`genes_by_ontology(ontology='tcdb', ...)`). The metabolite-anchored route includes all families curating the substrate; the ontology route is family-anchored and misses cross-family substrate hits.

**TCDB family-anchored context:** to see what a family *is* before trusting its substrate set — its level (class / subclass / family / subfamily), parents and children, `member_count` vs `gene_count`, and the Pfam domains / GO terms it is built from (`links_out`, composition) — use `ontology_term_details(term_ids=['tcdb:3.A.1'])`. Browse families by size with `search_ontology(ontology=['tcdb'], level=2)`. The full TCDB reference (identifier form, `attachment_depth` — visible only with `gene_ontology_terms(mode='leaf', include_superseded=True, verbose=True)` — evidence, pitfalls) is `docs://ontologies/tcdb`; the other ontologies are indexed at `docs://ontologies/index`.

**Chemical roles (siderophores, vitamins, antibiotics):** role terms are `ChemicalRole` nodes
(`chebi.role:<n>`), not metabolites, so no metabolite tool returns them and a role id passed as
`metabolite_ids` lands in `not_found` with a warning naming the role. TCDB curates some
substrates only as a role ("siderophore"), reachable through `run_cypher`:

```cypher
CALL db.index.fulltext.queryNodes('chemicalRoleFullText', 'siderophore')
YIELD node AS role, score
WITH role ORDER BY score DESC LIMIT 1
MATCH (sub:ChemicalRole)-[:Chemical_role_is_a_chemical_role*0..]->(role)
MATCH (f:TcdbFamily)-[:Tcdb_family_transports_chemical_role]->(sub)
WHERE f.substrate_breadth <> 'not_assessed'
RETURN role.id AS role_id, f.id AS tcdb_family_id, f.name AS tcdb_family_name,
       f.substrate_breadth AS substrate_breadth,
       collect(DISTINCT sub.name) AS via_roles
ORDER BY tcdb_family_id
```

`*0..` includes the role itself plus its narrower roles. Discount `lumping` families (see
"What lumping means" under g), then take the family ids to
`genes_by_ontology(ontology='tcdb', term_ids=[...], organism=...)` for the genes.

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
