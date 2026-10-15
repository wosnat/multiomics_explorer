# Tool spec: metabolite identity surface (cross-tool, Mode B) — backlog 2c.8, part 1 + 2

## Purpose

The KG's metabolite identity rebuilds (KG doc
`multiomics_biocypher_kg/docs/kg-changes/metabolite-identity-and-classes.md`, explorer work list
§27 / §37, follow-up §38) did the following:
- merged duplicate metabolites, with stereo forms kept apart by the MNX stereo guard;
- re-keyed `chebi:` nodes to KEGG ids;
- turned 57 role terms into `ChemicalRole` nodes;
- added `structure_kind`, `kegg_functional_categories`, `kegg_brite_classes` and assay-edge
  `stereo_assignment`.

The explorer absorbed both builds (commits `0312ec0`, `f01f10f`; live build 2026-10-15T19:17Z)
without code changes, so:

1. **Retired ids fail.** 311 old `Metabolite.id`s are gone. `chebi:14654` (nitrate),
   `kegg.compound:C00085` (D-fructose 6-phosphate), `chebi:10004` (a role) all land in `not_found`
   with no hint, because prefixed inputs bypass the resolver today. **This must ship before the KG
   release** that bumps `mcp_min_version`.
2. **New KG information isn't shown:**
   - whether a metabolite is a defined molecule or a generic class / polymer;
   - its KEGG classification (functional category and BRITE class);
   - whether a measurement's stereo form was stated by the paper or assumed by the KG.

## Out of scope (piece 3, separate spec)

- The "other stereo form" hint (`Metabolite_is_stereo_form_of` / `_is_enantiomer_of`, e.g. generic
  Cysteine 0 catalysts vs L-Cysteine 652). Needs its own design: row field vs warning, which tools,
  1- vs 2-hop.
- A `ChemicalRole` or `MetaboliteClass` tool mode (`search_ontology` / `ontology_term_details`),
  and BRITE classes below the top level (`kegg_brite_classes` carries level 0 only).
  Roles stay `run_cypher`-only; this spec adds one few-shot example.
- `structure_kind` / `kegg_functional_categories` / `kegg_brite_classes` on tools other than `list_metabolites`.
- Exposing `all_identifiers`, `identity_basis`, `recurated_from_ids` as row fields.

## Tools touched

| Change | Tools |
|---|---|
| A. CURIE resolver for `metabolite_ids` / `exclude_metabolite_ids` | `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`, `list_metabolite_assays`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite` |
| B. xref filters match any identifier | `list_metabolites` (`kegg_compound_ids`, `chebi_ids`, `hmdb_ids`, `mnxm_ids`) |
| C. `structure_kind` + `kegg_functional_categories` (row, filter, envelope) | `list_metabolites` |
| C2. `kegg_brite_classes`, the 7 other KEGG compound trees (row, filter, envelope) | `list_metabolites` |
| D. `stereo_assignment` (row, filter, envelope, warning) | `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite` |
| E. New `filter_type`s | `list_filter_values` (`structure_kind`, `kegg_functional_category`, `kegg_brite_class`, `stereo_assignment`) |
| F. Docs | YAMLs of all of the above, `conventions.md`, `analysis/metabolites.md`, `kg/queries.py` few-shot, CLAUDE.md tool rows |

## KG facts (live, build 2026-10-15T19:17:46Z, verified)

- `Metabolite` 3,214 nodes; 0 `mnx:` ids. Ten nodes carry more than one KEGG id, all conjugate
  pairs or true duplicates; stereo forms are never merged.
- `Metabolite.all_identifiers` (dense, `str[]`, CURIE-only), with prefixes `chebi`, `mnx`,
  `kegg.compound`, `inchikey` and `hmdb`. **Every entry is on exactly one node** (0 duplicates; KG test across `Metabolite` ∪ `ChemicalRole`).
  Forms: prefix lower case; `kegg.compound:C00244`, `chebi:14654` (digits, no leading zeros;
  primary + secondary), `mnx:MNXM732398` (and one non-`MNXM` local part: `mnx:WATER`),
  `hmdb:HMDB0000122` (always 7 digits), `inchikey:GRYLNZFGIOXLOG-UHFFFAOYSA-N`.
- `Metabolite.recurated_from_ids` (sparse, 13 nodes): ids of dropped nodes whose paper rows now
  point here, e.g. `kegg.compound:C00525` (D-Trp) on L-Trp `C00078`. **No identity meaning**; never
  in `all_identifiers`.
- `ChemicalRole` (111 nodes): `id = chebi.role:<n>`; `all_identifiers` = own id + `chebi:` CURIEs
  of its primary and secondary ids (e.g. `chebi:10004` → `chebi.role:33229` "vitamin (role)").
- `Metabolite.structure_kind` (dense, closed vocab): `defined` 2,564 · `generic` 624 · `polymer` 26.
- `Metabolite.kegg_functional_categories` (sparse `str[]`, closed vocab, 9 values, 334 nodes;
  renamed from `kegg_compound_categories`): Carbohydrates 65 · Peptides 60 · Nucleic acids 47 ·
  Vitamins and cofactors 41 · Lipids 40 · Organic acids 35 · Antibiotics 28 · Hormones and
  transmitters 24 · Steroids 15.
- `Metabolite.kegg_brite_classes` (sparse `str[]`, closed vocab, 28 values, 652 nodes):
  - values are `"<Tree>: <class>"` from the 7 KEGG compound BRITE trees other than br08001;
  - the vocabulary node has **no `value_descriptions`**, because the values contain `": "`; tree
    codes are named in its `description`.
- `stereo_assignment` (dense on both assay edges, closed vocab `{as_reported, dominant_form_assumed}`):
  `Assay_quantifies_metabolite` 1,342 / 138 · `Assay_flags_metabolite` 144 / 42.
- `ControlledVocabulary` nodes exist for `Metabolite.structure_kind`,
  `Metabolite.kegg_functional_categories`, `Metabolite.kegg_brite_classes`,
  `Assay_quantifies_metabolite.stereo_assignment` and `Assay_flags_metabolite.stereo_assignment`.

---

## A. CURIE resolver (replaces `docs/tool-specs/bare-metabolite-id-coercion.md` rules)

### Normalisation (api layer, pure Python, per input string)

| Input shape (case-insensitive unless noted) | Normalised CURIE |
|---|---|
| `kegg.compound:<x>` | `kegg.compound:` + upper(x) |
| `C\d{5}` | `kegg.compound:` + upper |
| `chebi:<digits>` / `CHEBI:<digits>` / bare `<digits>` | `chebi:` + digits with leading zeros stripped |
| `mnx:<x>` | `mnx:` + upper(x) (keeps `mnx:WATER`) |
| `MNXM\d+` | `mnx:` + upper |
| `hmdb:<x>` / `HMDB\d+` | `hmdb:HMDB` + digits left-padded to 7 (`HMDB02878` → `HMDB0002878`) |
| `inchikey:<key>` / bare `[A-Z]{14}-[A-Z]{10}-[A-Z]` | `inchikey:` + upper |
| `chebi.role:<digits>` | unchanged (routes to the role check below) |
| anything else (unknown prefix, a name like `glutamate`) | unchanged — lands in `not_found`; the existing shape warning fires |

### Lookup (one round-trip; new builder `build_resolve_metabolite_curies(curies)` replaces `build_resolve_metabolite_aliases`)

Verified against live KG. Index path first (`Metabolite.id`), `all_identifiers` scan only on a miss:

```cypher
UNWIND $curies AS c
OPTIONAL MATCH (m:Metabolite {id: c})
WITH c, collect(m.id) AS direct
CALL {
  WITH c, direct
  OPTIONAL MATCH (m:Metabolite) WHERE size(direct) = 0 AND c IN m.all_identifiers
  RETURN collect(m.id) AS via_alias
}
WITH c, direct + via_alias AS canonical
OPTIONAL MATCH (t:Metabolite) WHERE size(canonical) = 0 AND c IN coalesce(t.recurated_from_ids, [])
WITH c, canonical, [x IN collect({id: t.id, name: t.name}) WHERE x.id IS NOT NULL] AS recurated_to
OPTIONAL MATCH (r:ChemicalRole) WHERE size(canonical) = 0 AND (r.id = c OR c IN r.all_identifiers)
RETURN c AS curie, canonical, recurated_to,
       [x IN collect({id: r.id, name: r.name}) WHERE x.id IS NOT NULL] AS roles
```

Live results (build 2026-10-15T19:17Z):

| Input | `canonical` | `recurated_to` | `roles` |
|---|---|---|---|
| `kegg.compound:C00244` | `[kegg.compound:C00244]` | | |
| `chebi:14654` | `[kegg.compound:C00244]` | | |
| `kegg.compound:C00085` | `[kegg.compound:C00085]` (its own node again) | | |
| `kegg.compound:C01327` (HCl) | `[kegg.compound:C00698]` (Cl⁻, merged member) | | |
| `chebi:14313` | `[chebi:17234]` | | |
| `mnx:WATER` | `[kegg.compound:C00001]` | | |
| `inchikey:GRYLNZFGIOXLOG-UHFFFAOYSA-N` | `[kegg.compound:C00244]` | | |
| `hmdb:HMDB0000122` | `[kegg.compound:C00031]` (D-Glucose; moved by KG ask 5 in build T19:58Z) | | |
| `kegg.compound:C00525` | `[]` | `[C00078 L-Tryptophan]` | |
| `mnx:MNXM1565340` | `[]` | `[C00062 L-Arginine]` | |
| `chebi:10004` | `[]` | | `[chebi.role:33229 vitamin (role)]` |
| `chebi.role:33229` | `[]` | | `[chebi.role:33229 vitamin (role)]` |
| `kegg.compound:C99999` | `[]` | | |

Timing: 12 mixed ids ≈ 95 ms; 200 canonical ids ≈ 210 ms; 200 retired-id misses ≈ 1.0 s.

### Helper contract (`_canonicalize_metabolite_ids`, same signature and return shape)

Returns `(canonical_ids, resolved_aliases, warnings)`:
- **Resolved** (`canonical` non-empty): replaced by the canonical id(s), first-seen order, deduped.
  `resolved_aliases[raw] = canonical` whenever `raw != canonical[0]`, so case / prefix / retired-id
  normalisation is always reported, and an input that already is the canonical id is not.
  `len(canonical) > 1` cannot happen on this KG (uniqueness test); keep the existing expand-and-warn
  path as a defensive fallback.
- **Recurated** (`recurated_to` non-empty): kept **verbatim** (lands in `not_found`), plus a warning:
  `"'kegg.compound:C00525' was removed; its paper measurements now live on kegg.compound:C00078 (L-Tryptophan) — pass that id to see them."`
  It is not resolved because the two are different compounds (D-Trp vs L-Trp).
- **Role** (`roles` non-empty): kept verbatim (lands in `not_found`), plus a warning:
  `"'chebi:10004' is the chemical role 'vitamin (role)' (chebi.role:33229), not a metabolite — TCDB families that transport it are reachable through run_cypher (see docs://analysis/metabolites)."`
- **Unresolved:** kept verbatim (lands in `not_found`), as today.
- Always one round-trip when `ids` is non-empty (today: zero for already-prefixed inputs). `None` /
  `[]` unchanged.
- `_canonicalize_metabolite_id_params` (pair wrapper) unchanged.
- `_looks_like_metabolite_id` / `_metabolite_id_shape_warnings` accept the new shapes (`hmdb:`,
  `inchikey:`, bare InChIKey, `chebi.role:`) so they don't get the "not a metabolite id" warning.
  `_CANONICAL_METABOLITE_PREFIXES` → `("kegg.compound", "chebi", "mnx", "hmdb", "inchikey", "chebi.role")`.

No change to any tool's builder: they keep `m.id IN $metabolite_ids`, fed canonical ids.

## B. `list_metabolites` xref filters match any identifier

`kegg_compound_ids`, `chebi_ids`, `hmdb_ids`, `mnxm_ids`: each value is normalised with the
namespace's rule from A (a bare `C00085`, `kegg.compound:C00085`, `14654`, `CHEBI:14654`,
`HMDB02878` all work; a value from the wrong namespace for its filter is normalised by its own
shape, which is fine because the CURIE carries the namespace). Each filter becomes, in
`_list_metabolites_where` (one condition per filter, AND across filters as today):

```cypher
ANY(x IN $kegg_compound_curies WHERE x IN coalesce(m.all_identifiers, []))
```

Verified: `C00085` → `[kegg.compound:C00085]`; `C01327` → `[kegg.compound:C00698]`; `chebi:14654` and `chebi:17632` → `[kegg.compound:C00244]`;
`hmdb:HMDB0000122` → `[kegg.compound:C00031]`; `mnx:MNXM732398` → `[kegg.compound:C00244]`.
Params keep their names and types (`list[str] | None`). Docstrings: "matches any of the metabolite's
identifiers, including secondary and retired ones".

## C. `list_metabolites`: `structure_kind` + `kegg_functional_categories`

**Row fields (compact):**
- `structure_kind: str`. Always present: `defined` / `generic` / `polymer`.
- `kegg_functional_categories: list[str]`, read from `m.kegg_functional_categories`. Sparse:
  **absent** when KEGG doesn't list the metabolite. Absent means "not listed"; it does **not**
  mean "not in this category".

**Filters** (new params, both `list[str] | None = None`):
- `structure_kind`: `m.structure_kind IN $structure_kind`. `['generic', 'polymer']` → 650.
- `kegg_functional_categories`: `ANY(c IN coalesce(m.kegg_functional_categories, []) WHERE c IN $kegg_functional_categories)`. `['Peptides']` → 60.

**Exact Pydantic descriptions** (frozen wording; each ≤ 250 chars). The filter param is where an
agent decides to narrow, so it carries the partial-coverage warning itself, not just a pointer:
- `kegg_functional_categories` **filter param** (244 chars):
  > KEGG br08001 categories (OR). Hand-curated and partial: only ~10% of metabolites are listed, so a missing category means 'KEGG did not list it', not 'not in it' (fumarate is unclassified). Values: list_filter_values('kegg_functional_category').
- `kegg_functional_categories` **row field** (185 chars):
  > KEGG br08001 categories this metabolite is listed under. Absent = KEGG did not list it (~90% of metabolites), not 'none apply'. Curated, functional headings (amines sit under Peptides).
- The api docstring arg and the YAML params text carry the same content. They may add the
  enrichment-background rule and the `docs://analysis/metabolites` link.
- `kg_claims.yaml` pins the "~10%" / "~90%" figures with a claim of 334 classified of 3,214.
  `used_in` lists `mcp_server/tools.py`, `api/functions.py`, `list_metabolites.yaml` and
  `analysis/metabolites.md`.

Both register in `_CLOSED_VOCAB_PARAMS`:
- `structure_kind` → `("Metabolite", "structure_kind", "structure_kind")`;
- `kegg_functional_categories` → `("Metabolite", "kegg_functional_categories", "kegg_functional_category")`.

An unknown value warns (it never raises) and matches nothing, as for other closed vocabularies.

**Envelope** (always present, also on `summary=True`; `[]` on an empty match). Shape follows the
other `by_*` lists:
- `by_structure_kind: [{structure_kind, count}]`.
- `by_kegg_functional_category: [{kegg_functional_category, count}]`: metabolites per category,
  sorted by count desc. A metabolite in two categories counts in both.
  - It always ends with `{kegg_functional_category: "not classified", count: N}`: the matched
    metabolites KEGG doesn't list. The entry is present even when N = 0.
  - `"not classified"` is an envelope label only. It is **not** a vocabulary value and **not**
    accepted by the filter; passing it warns like any unknown value. The docs say unclassified
    means "KEGG doesn't list it", not "in none of these categories".

Summary Cypher additions (inside the existing `WITH … count(m)` aggregation, both variants):

```cypher
collect(m.structure_kind) AS sks,
apoc.coll.flatten(collect(coalesce(m.kegg_functional_categories, []))) AS kfcs,
sum(CASE WHEN size(coalesce(m.kegg_functional_categories, [])) = 0 THEN 1 ELSE 0 END)
  AS kegg_functional_unclassified
…
RETURN …, apoc.coll.frequencies(sks) AS by_structure_kind,
          apoc.coll.frequencies(kfcs) AS by_kegg_functional_category,
          kegg_functional_unclassified
```

The api layer renames the frequency rows, sorts them, and appends the `"not classified"` entry
from `kegg_functional_unclassified`. The raw count isn't exposed as its own key.

Verified on `evidence_sources=['transport'], elements=['N']`: 672 metabolites.
- `by_structure_kind`: defined 606 / generic 62 / polymer 4.
- `by_kegg_functional_category`: Peptides 47, Nucleic acids 28, Vitamins and cofactors 23,
  Antibiotics 23, Hormones and transmitters 15, Carbohydrates 7, Lipids 6, Steroids 2,
  **not classified 533**.
- Whole KG: 2,880 of 3,214 not classified.

## C2. `list_metabolites`: `kegg_brite_classes` (the other 7 KEGG compound trees)

Read from the KG property `m.kegg_brite_classes`, which covers the 7 KEGG compound BRITE trees
beyond br08001:
- Lipids br08002;
- Phytochemical compounds br08003;
- Glycosides br08021;
- Pesticides br08007;
- Natural toxins br08009;
- Endocrine disrupting compounds br08006;
- Bioactive peptides br08005.

The KG computes the values post-import (ask 6, landed). Format: `"<Tree title>: <top-level class>"`,
e.g. `Lipids: Fatty acyls`, `Phytochemical compounds: Terpenoids`, `Pesticides: Pesticides`. Only
level-0 classes appear; deeper levels stay `run_cypher`-only through `MetaboliteClass`. The tree
prefix keeps same-named classes apart: br08001 `Lipids` vs the lipid tree; `Pesticides:
Pesticides` vs `Endocrine disrupting compounds: Pesticides and herbicides`.

**Row field (compact):** `kegg_brite_classes: list[str]`, sparse: **absent** when the metabolite has none.

| Metabolite | `kegg_functional_categories` | `kegg_brite_classes` |
|---|---|---|
| Ouabain `C01443` | Steroids | Glycosides: O-glycosides · Lipids: Sterol lipids · Natural toxins: Phytotoxins · Phytochemical compounds: Terpenoids |
| Butanoic acid `C00246` | Lipids · Organic acids | Lipids: Fatty acyls · Phytochemical compounds: Fatty acids related compounds |
| L-Glutamine `C00064` | Peptides | *(absent)* |
| Fumarate `C00122` | *(absent)* | *(absent)* |

**Per compound, both fields together:** 1 value for 682 metabolites, 2 for 169, 3 for 24, 4 for 6,
5 for 2 (mean ≈ 1.27). Lists stay short.

**Filter** `kegg_brite_classes: list[str] | None = None`:
`ANY(x IN coalesce(m.kegg_brite_classes, []) WHERE x IN $kegg_brite_classes)`.
`['Lipids: Fatty acyls']` → 254. It registers in `_CLOSED_VOCAB_PARAMS` as
`("Metabolite", "kegg_brite_classes", "kegg_brite_class")`; an unknown value warns.

**Envelope:** `by_kegg_brite_class: [{kegg_brite_class, count}]`, sorted by count desc, then a
trailing `{kegg_brite_class: "not classified", count: N}`. The same rules apply as in C, with the
same summary-Cypher pattern (`kbcs` flatten + a `kegg_brite_unclassified` sum).

**Coverage, verified:**
- Whole KG: 652 of 3,214 metabolites (~20%) carry a class, and 2,562 are not classified. With both
  fields, 883 (~27%) have something.
- Metabolites with catalyst genes (2,221): 503 carry a BRITE class and 247 a functional category;
  687 have either.
- Value counts: Lipids: Fatty acyls 254 · Lipids: Prenol lipids 137 · Phytochemical compounds:
  Terpenoids 57 · Lipids: Sterol lipids 38 · Phytochemical compounds: Alkaloids 37 · Lipids:
  Polyketides 34 · Pesticides: Pesticides 30 · Lipids: Glycerophospholipids 27 · Glycosides:
  N-glycosides 22 · Phytochemical compounds: Phenylpropanoids 21 · … (28 values).

**Exact Pydantic descriptions** (frozen wording):
- `kegg_brite_classes` **filter param** (241 chars):
  > Classes from 7 other KEGG compound BRITE trees, as 'Tree: Class' (OR), e.g. 'Lipids: Fatty acyls'. Curated and partial (~20% of metabolites): unlisted = 'KEGG did not list it', not 'not in it'. Values: list_filter_values('kegg_brite_class').
- `kegg_brite_classes` **row field** (199 chars):
  > 'Tree: Class' from 7 KEGG compound BRITE trees (lipids, phytochemicals, glycosides, pesticides, toxins, endocrine disruptors, bioactive peptides). Absent = KEGG did not list it (~80% of metabolites).
- `kg_claims.yaml` pins the 652-of-3,214 figure behind "~20%" / "~80%".

**`list_filter_values(filter_type='kegg_brite_class')`** is a normal vocabulary read (closed,
28 values). The vocabulary node has **no `value_descriptions`** (the values contain `": "`), so the
rows carry no per-value description. The tree codes come from the node's `description`, which the
response's `description` field passes through.

## D. Assay tools: `stereo_assignment`

**Row field (compact)** `stereo_assignment: str` (`as_reported` / `dominant_form_assumed`), read
from `r.stereo_assignment`:
- `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`;
- `assays_by_metabolite`: both arms carry it (it's a shared field, not arm-specific).

It's compact, not verbose: it qualifies the row's identity ("the paper said Alanine; the KG put it
on L-Ala").

**Filter** (new param on all three) `stereo_assignment: list[str] | None = None` →
`r.stereo_assignment IN $stereo_assignment`. Typical use is `['as_reported']`, to drop rows whose
stereo form the KG assumed. It's a closed vocabulary: register it for warnings with
`applies_to = Assay_quantifies_metabolite` / `Assay_flags_metabolite` (edge). The `_CLOSED_VOCAB_PARAMS`
reader is node-only today, so the api-updater either extends the entry to edge kind or validates
against `_read_vocab_values(conn, <edge type>, "stereo_assignment", "edge")` directly. **Layer-owner
call: api-updater; must not touch other tools' validation.**

**Envelope** (always present, over the matched set, not the page):
`by_stereo_assignment: [{stereo_assignment, count}]`, from `collect(r.stereo_assignment)` +
`apoc.coll.frequencies` in each summary builder (both arms of the `assays_by_metabolite` UNION).

**Warning** (added to `warnings` when the matched set has any `dominant_form_assumed` row):
`"N of M rows assume the dominant stereo form — the paper named no form (e.g. 'Alanine' placed on L-Alanine); filter stereo_assignment=['as_reported'] to drop them."`

Verified live:
- Per assay, numeric: Kujawinski S7 assays 49 / 21 each; msystems KEGG-export 88/4, 264/12, 176/8;
  pnas MIT9303 30/2, MIT9313 60/4.
- Boolean presence flags: 72 / 21 each.
- `kegg.compound:C00041` (L-Ala): 4 quantifies + 2 flags edges, all `dominant_form_assumed`.

## E. `list_filter_values`

New `filter_type`s, all read from `ControlledVocabulary` with the pivot fallback + warning, as
existing entries are:
- `structure_kind`: node `Metabolite.structure_kind`.
- `kegg_functional_category`: node `Metabolite.kegg_functional_categories`, singular filter_type name
  following `gene_category`. Rows carry the value description where the KG provides one.
- `stereo_assignment`: edge, applies to `Assay_quantifies_metabolite` + `Assay_flags_metabolite`.
  Add to `_MULTI_LABEL_VOCABS` like `detection_status`.
- `kegg_brite_class`: node `Metabolite.kegg_brite_classes`. It has no per-value descriptions (see C2).

The `filter_type` Literal / docs gain the four names. `tests/unit/test_docs_lint.py` vocab checks
and `inputs/lint/vocab_snapshot.yaml` cover them (run `scripts/snapshot_vocab.py`).

## F. Docs (doc-updater)

- `inputs/tools/list_metabolites.yaml`:
  - an example per new field / filter (`structure_kind=['generic']`; `kegg_functional_categories=['Peptides']`);
  - mistakes:
    - KEGG categories are partial and curated, not a full classification (short form of points 1–5
      in the KEGG-methodology item below; link `docs://analysis/metabolites`);
    - generic nodes carry generic formulas (`C2H4NO2R`) and no mass;
  - the xref-filter note (any identifier, incl. retired).
- The three assay YAMLs: a `stereo_assignment` mistake / example (`stereo_assignment=['as_reported']`)
  and the envelope key.
- `list_filter_values.yaml`: the three new filter types.
- All 7 resolver tools' YAML id-form notes:
  - retired ids resolve, and show up in `resolved_aliases`;
  - removed ids and role ids warn;
  - the "`mnx:` … pass through untouched" sentence goes.
- **KEGG classification is partial — methodology must be explained** (required content, not
  optional polish). The facts below have to reach the reader in `analysis/metabolites.md` (a new
  subsection, "KEGG compound categories: what they are and aren't"). `list_metabolites.yaml`
  carries a short version in its mistakes section. The `kegg_functional_categories` and
  `kegg_brite_classes` field / filter descriptions carry the warning themselves (frozen wording in
  C / C2).
  1. **Source and method.** The categories are the 9 top-level groups of KEGG BRITE hierarchy
     **br08001 "Compounds with biological roles"**. This is a hand-curated KEGG list: curators place
     selected **representative** compounds under functional headings (Peptides, Carbohydrates,
     Lipids, Nucleic acids, Vitamins and cofactors, Organic acids, Hormones and transmitters,
     Antibiotics, Steroids). It is not an exhaustive or rule-based chemical classification. A
     compound is in a category only if KEGG listed it there. The KG copies these assignments and
     never infers a category.
  2. **Coverage is low.** Only 334 of 3,214 metabolites (~10%) carry a category. Even common
     central metabolites the KG catalyses are unclassified: 1,974 metabolites with catalyst genes
     have no category. Examples: fumarate, ethanol, L-carnitine, D-ribulose 5-phosphate.
  3. **Absence means "KEGG didn't list it"**, not "not in this category". Fumarate is an organic
     acid but has no category. The envelope's `"not classified"` count makes this visible. Never
     read a missing category as a negative.
  4. **Functional, not structural headings.** Amino acids *and* amines (putrescine, dopamine) sit
     under **Peptides**; myo-inositol under **Carbohydrates**; retinol under **Vitamins**. A
     compound can sit in more than one category.
  5. **Consequences for analysis.**
     - Use categories to *describe or group* a result list, not to *exclude* compounds.
     - For enrichment or "over-represented category" claims, the background must be the classified
       metabolites only, never all metabolites.
     - For composition questions (N-containing, P-containing), use `elements` instead.
  6. **The second field, `kegg_brite_classes`**, holds KEGG's 7 other compound BRITE trees:
     - Lipids br08002 (LIPID MAPS-style classes);
     - Phytochemical compounds br08003;
     - Glycosides br08021;
     - Pesticides br08007;
     - Natural toxins br08009;
     - Endocrine disrupting compounds br08006;
     - Bioactive peptides br08005.

     These are the same kind of hand-curated, representative-compound lists. Some are chemical
     (lipid and phytochemical classes, glycosides) and some are use / effect groups (pesticides,
     toxins, endocrine disruptors). Coverage:
     - 652 of 3,214 metabolites (~20%) have a class;
     - with both fields, 883 (~27%) have something;
     - 687 of 2,221 metabolites with catalyst genes have something.

     Values are `Tree: Class` at the top level only; deeper levels are `run_cypher`-only (add a
     few-shot example). Points 3 and 5 apply unchanged.
  7. **Two fields, two questions.** `kegg_functional_categories` answers "what is it for, in
     KEGG's functional grouping"; `kegg_brite_classes` answers "what kind of compound is it, or what
     is it used as". They overlap: butanoic acid is `Lipids` + `Organic acids` functionally, and
     `Lipids: Fatty acyls` + `Phytochemical compounds: Fatty acids related compounds` in BRITE.
- `references/guide/conventions.md`: metabolite id resolution, and the asymmetry that
  `Metabolite.all_identifiers` holds CURIEs while `Gene.all_identifiers` holds bare ids.
- `references/analysis/metabolites.md`:
  - id forms + retired-id resolution;
  - a `stereo_assignment` caveat in the measured-metabolite section;
  - "lumping" defined via `TcdbFamily.substrate_breadth` (not the `level ≥ 2 AND metabolite_count ≥ 50` threshold, which no longer reproduces the set);
  - the `ChemicalRole` route ("which TCDB families transport siderophores");
  - the KEGG compound categories subsection (the KEGG-methodology item above).
- `kg/queries.py` few-shot (doc-updater owns this one addition): the siderophore route —
  `chemicalRoleFullText` → `Chemical_role_is_a_chemical_role*0..` →
  `Tcdb_family_transports_chemical_role` → `TcdbFamily`.
  A second few-shot example: metabolites in a deeper KEGG compound class, e.g. br08002 Lipids,
  via `MetaboliteClass` + `Metabolite_in_metabolite_class` + `Metabolite_class_is_a_metabolite_class*0..`.
- `mcp_server/tools.py` `transport_substrate_resolution` descriptions mention
  `TcdbFamily.substrate_breadth = 'lumping'` (tool-wrapper owns this).
- CLAUDE.md tool rows for `list_metabolites`, the three assay tools and `list_filter_values`.
- Regenerate: `uv run python scripts/build_about_content.py` then `--lint`.

## Tests

**Unit (test-updater, RED first):**
- **Normaliser:** table-driven over every row of A's normalisation table, including `HMDB02878` →
  `hmdb:HMDB0002878`, `CHEBI:0014654` → `chebi:14654`, lower-case `c00085`, bare InChIKey, `mnx:water`
  → `mnx:WATER`, `glutamate` unchanged.
- **`build_resolve_metabolite_curies`:** the query contains the index-first `MATCH (m:Metabolite {id: c})`,
  the `all_identifiers` fallback, the `recurated_from_ids` and `ChemicalRole` branches; params
  `{curies}`.
- **`_canonicalize_metabolite_ids`** with mocked rows:
  - a resolved retired id → `resolved_aliases`;
  - a canonical input → no alias entry;
  - recurated → verbatim + warning text;
  - role → verbatim + warning text;
  - unresolved → verbatim;
  - one round-trip even when every input is prefixed.
- **`_list_metabolites_where`:** the xref filters emit the `all_identifiers` ANY clause with normalised
  CURIE params; the `structure_kind` / `kegg_functional_categories` clauses.
- **`kegg_brite_classes`:** property read + `ANY(...)` filter clause in `_list_metabolites_where`.
- **Summary builders:**
  - `by_structure_kind` / `by_kegg_functional_category` + `kegg_functional_unclassified` (both search and
    non-search variants); the api appends the trailing `"not classified"` entry (including count 0);
  - `by_stereo_assignment` on the 3 assay summaries (both UNION arms).
- **Detail builders:** `stereo_assignment` column on the 3 assay tools; `structure_kind` /
  `kegg_functional_categories` / `kegg_brite_classes` on `list_metabolites`.
- **Summary:** `by_kegg_brite_class` + its `"not classified"` entry.
- **`stereo_assignment` filter clause** on the 3 assay `_where` builders.
- **Wrappers:** the new params, Pydantic fields, envelope keys; `kegg_functional_categories` and
  `kegg_brite_classes` sparse (stripped when null / empty).
- **`list_filter_values`:** the 4 new filter types (all vocabulary reads).

**Integration (`-m kg`), using the live values above:**
- `list_metabolites(metabolite_ids=['chebi:14654'])` → 1 row `kegg.compound:C00244`,
  `resolved_aliases == {'chebi:14654': ['kegg.compound:C00244']}`, `not_found.metabolite_ids == []`.
- `kegg.compound:C00525` → `not_found` contains it + recurated warning naming `kegg.compound:C00078`.
- `chebi:10004` → `not_found` + role warning naming `chebi.role:33229`.
- `genes_by_metabolite(['chebi:14654'], 'MED4')` returns rows for nitrate (both arms now on one node).
- `kegg_compound_ids=['C01327']` → `[kegg.compound:C00698]` (merged member); `['C00085']` → `[kegg.compound:C00085]`.
- `structure_kind=['generic', 'polymer']` → 650; `kegg_functional_categories=['Peptides']` → 60;
  `kegg_brite_classes=['Lipids: Fatty acyls']` → 254.
- `metabolite_ids=['kegg.compound:C01443']` (ouabain) → `kegg_brite_classes` holds the 4 values in C2.
- `summary=True` → `by_kegg_brite_class[-1] == {'kegg_brite_class': 'not classified', 'count': 2562}`.
- An unknown `kegg_brite_classes` value warns and matches nothing.
- Docs check: `analysis/metabolites.md` contains the KEGG-categories subsection, with the source tree (br08001), the coverage number and the "absence ≠ negative" rule. A `kg_claims.yaml` entry pins the 334-classified count, so the number can't drift silently.
- `list_metabolites(summary=True)` → `by_kegg_functional_category[-1] == {'kegg_functional_category': 'not classified', 'count': 2880}`.
- Assay `by_stereo_assignment` sums equal `total_matching`. `stereo_assignment=['dominant_form_assumed']`
  on the msystems presence flags → 21 per assay.
- **Edge-case scenarios** (`tests/integration/edge_cases/scenarios.py`): retired id, role id,
  recurated id, mixed batch (canonical + retired + unknown), and an empty `stereo_assignment`
  intersection.

**Regression:** new goldens:
- `list_metabolites_retired_ids` (the mixed batch above);
- `list_metabolites_structure_kind_generic` (`summary=True`);
- `mfa_msystems_as_reported_only`.

Existing goldens gain the new compact columns / envelope keys: regenerate with `--force-regen` and
classify. The only expected diff is the new keys.

## Special handling / risks

- **Performance:** a batch of many retired ids scans `all_identifiers` per miss (≈ 5 ms each).
  That's acceptable at tool batch sizes. Don't add an index; the KG has none for list membership.
- **`assays_by_metabolite` polymorphic rows** stay `BaseModel`; `stereo_assignment` is common to both
  arms, so it's never `None`.
- **KG ask 5 delivered** (build 2026-10-15T19:58Z): generic sugar HMDB / ChEBI records sit on the
  generic nodes (`HMDB0000122`, `CHEBI:17634` → D-Glucose `C00031`).
- `stereo_assignment` validation is the first closed-vocab **edge** filter routed through
  `_CLOSED_VOCAB_PARAMS`. Keep the change local to that table / helper.

## Status

- [x] KG changes landed (builds 2026-10-15T16:26Z and T19:17Z, absorbed `0312ec0` and `f01f10f`)
- [x] Scope reviewed with user (pieces 1 + 2 now; piece 3 later; xref filters → `all_identifiers`)
- [x] Cypher verified against live KG, build 2026-10-15T19:17Z (sections A, B, C, C2, D)
- [x] Frozen (user approval 2026-10-15)
