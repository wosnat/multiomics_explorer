# KG asks: MNX `same entity` merges that cross stereo, anomer and class boundaries (2026-10-15)

**Date:** 2026-10-15 · **From:** explorer (`multiomics_explorer`) · **To:** KG (`multiomics_biocypher_kg`)
**Build:** `0.0.0-dev`, built 2026-10-15T16:26:50Z (the metabolite identity rebuild).
**Context:** KG change doc `docs/kg-changes/metabolite-identity-and-classes.md`. Its §1 says
stereoisomers are **not merged** ("L-Glu, D-Glu and stereo-unspecified Glu stay three nodes, as in
KEGG, and are linked instead"), and §21 adds an anomer guard. Found while classifying golden diffs
during the absorb. **Not blocking the absorb:** the data is internally consistent, and these merges
are announced as `mnx_same_entity`.

## What we found

21 live nodes carry more than one KEGG id (`size(kegg_compound_ids) > 1`). Eleven of them conflict
with the agreed rules. The table is sorted by `catalyst_gene_count` (live):

| Canonical node (kept) | Merged-away id | Problem | `catalyst_gene_count` |
|---|---|---|---|
| `C05345` beta-D-Fructose 6-phosphate | `C00085` D-Fructose 6-phosphate | **anomer**: the generic form merged into the β-anomer, and the β-anomer won the canonical id | 459 |
| `C00197` 3-Phospho-D-glycerate | `C00597` 3-Phosphoglycerate | stereo-unspecified → D | 290 |
| `C06010` (S)-2-Acetolactate | `C00900` 2-Acetolactate | stereo-unspecified → (S) | 157 |
| `C01102` O-Phospho-L-homoserine | `C05702` O-Phosphorylhomoserine | stereo-unspecified → L | 149 |
| `C05378` beta-D-Fructose 1,6-bisphosphate | `C00354` D-Fructose 1,6-bisphosphate | **anomer**, β won | 121 |
| `C16240` [Lipoyl-carrier protein]-L-lysine | `C03688` Apo-[acyl-carrier protein] | **different entities** (MNX conflation of protein-bound generics) | 103 |
| `C04272` (R)-2,3-Dihydroxy-3-methylbutanoate | `C04039` 2,3-Dihydroxy-3-methylbutanoate | stereo-unspecified → (R) | 89 |
| `C17345` (25R)-3α,7α-Dihydroxy-5β-cholestanoyl-CoA | `C04644` 3α,7α-Dihydroxy-5β-cholestanoyl-CoA | stereo-unspecified → (25R) | 34 |
| `C16241` (R)-Lipoate | `C00725` Lipoate (DL) | stereo-unspecified → (R) | 28 |
| `C03227` 3-Hydroxy-L-kynurenine | `C02794` 3-Hydroxykynurenine (DL) | stereo-unspecified → L | 13 |
| `C00261` Benzaldehyde | `C00193` Aromatic aldehyde | **class term merged into one member** (and the node reads `structure_kind = defined`) | 4 |

The remaining 10 multi-KEGG nodes are fine:
- **Conjugate pairs:** HCO₃⁻ / H₂CO₃, sulfite / HSO₃⁻, Cl⁻ / HCl, Br⁻ / HBr, F⁻ / HF, aquacobalamin / hydroxocobalamin.
- **True duplicates:** phenol, caffeate, nebularine / N-D-ribosylpurine, thiopurine / 6-mercaptopurine.

Names come from KEGG REST (`/list`) for the merged-away ids and from the live graph for the kept
ones. Live check: none of these canonical nodes carries a `Metabolite_is_stereo_form_of` or
`Metabolite_is_enantiomer_of` edge, so the merge also removed the stereo link that §2b would have
emitted.

### Related: a cross-reference placed on an anomer (not a merge)

| Identifier | Means | Sits on (live) | Expected |
|---|---|---|---|
| `hmdb:HMDB0000122` | HMDB's main **D-Glucose** record | `C00221` beta-D-Glucose (192 catalysts) | `C00031` D-Glucose (284 catalysts), which carries the minor record `HMDB0304632` instead |

None of the three glucose nodes is measured, so no assay row is affected. The effect is on lookups:
- a user or tool passing `HMDB0000122`, as the resolver will accept (backlog 2c.8), lands on the
  β-anomer;
- so does `list_metabolites(hmdb_ids=['HMDB0000122'])`.

The ChEBI side looks the same way: `C00221` carries `chebi:15903` (β-D-glucose) plus four other
ChEBI ids, while `C00031` carries only `chebi:4167` (D-glucopyranose). The generic D-glucose ChEBI
entry `chebi:17634` is on **no** node (checked live), so `CHEBI:17634` input returns `not_found`.

## Why it matters to the explorer

- **Wrong names on central metabolites.** D-fructose 6-phosphate and D-fructose 1,6-bisphosphate,
  two glycolysis hubs, now display as their β-anomers in every chemistry tool. They also change
  id (`kegg.compound:C00085` → `C05345`). The `metabolites_by_quantifies_assay` example (MIT9313)
  now shows "beta-D-Fructose 6-phosphate" for a measurement that names no anomer.
- **The stereo model is violated silently.** A user filtering or joining on `C00900` / `C04039` /
  `C00725` finds the stereo-specific node, and nothing marks that a stereo assumption was made.
  This is exactly what `stereo_assignment` and `Metabolite_is_stereo_form_of` were designed to make
  explicit.
- **The class → member merge** (`C00193` → `C00261`) attaches a class's reactions to one molecule.

## Asks

1. **MNX merges must respect the stereo / anomer / class guards.** Do not merge two KEGG ids that
   differ only in stereo configuration (including anomers), or where one is a generic / class term.
   The shared InChIKey connectivity block plus a stereo-layer difference is the same test §2b
   already uses. Emit the §2b link instead:
   - `is_stereo_form_of` for specific → unspecified;
   - nothing for anomer-only pairs, per §21.
2. **Separate `C03688` from `C16240`.** MNX conflates two different protein-bound species; a curated
   `no_merge:` override is enough.
3. **Canonical-id choice inside a legitimate merge group.**
   - When a group mixes a generic and a specific form (should ask 1 not fully prevent that), or for
     conjugate pairs, please prefer the id KEGG uses as the reaction hub, i.e. the one with more
     `Reaction_has_metabolite` edges before the merge.
   - Today the conjugate groups pick "Hydrochloric acid" over chloride and "Hydrobromic acid" over
     bromide. These are the acid forms, whereas the biologically relevant species is the ion.
     Lowest-priority of the asks.
4. **Add a KG test** that no merge group contains two KEGG ids related by the §2b stereo or anomer
   rule, or by a class → member relation.
5. **Place xrefs on the generic form, not an anomer.** When an HMDB or ChEBI cross-reference names
   the generic compound (`HMDB0000122` "D-Glucose"), attach it to the KEGG generic node (`C00031`),
   not to an α / β anomer node. Please also report how many HMDB / ChEBI xrefs sit on anomer-only
   nodes while the generic sibling exists.

## Explorer impact when fixed

Absorb only:
- the affected goldens (`mqa_mit9313_top5`, the `metabolites_by_quantifies_assay` example) move back
  to `C00085`;
- per-organism `catalyzed_metabolite_count` (down 5 in this build) partly recovers;
- `metabolite_id_remap.tsv` entries for these ids drop or change basis.

No explorer code change is needed. The resolver work (backlog 2c.8) will resolve `C00085` either way
through `all_identifiers`.

---

## Ask 6 (separate from the merge issue): precompute the other 7 KEGG compound trees, and rename the property

**Context.** The explorer is surfacing KEGG compound classification on `list_metabolites` (spec
`docs/tool-specs/metabolite-identity-surface.md`, sections C / C2) as two fields:
- `kegg_functional_categories`: br08001 "Compounds with biological roles", read from today's
  `Metabolite.kegg_compound_categories`;
- `kegg_brite_classes`: top-level classes of the 7 other trees (br08002 Lipids, br08003
  Phytochemical compounds, br08021 Glycosides, br08007 Pesticides, br08009 Natural toxins,
  br08006 Endocrine disrupting compounds, br08005 Bioactive peptides). Values are
  `"<Tree title>: <class>"`, e.g. `Lipids: Fatty acyls`.

The second field exists in the KG only as `MetaboliteClass` nodes, so the explorer **derives it per
query** today. The query walks `Metabolite_in_metabolite_class` → `Metabolite_class_is_a_metabolite_class*0..`
to level 0, then builds the label. It's fast (≈ 60 ms whole-KG), but:
- no `ControlledVocabulary` node covers the values, so filter validation and
  `list_filter_values(filter_type='kegg_brite_class')` use a derived list;
- the label format (tree title, LIPID MAPS code stripped) lives in explorer Cypher instead of the KG.

**Asks:**

a. **New property `Metabolite.kegg_brite_classes`** (`str[]`, sparse, post-import): the distinct
   level-0 classes of every tree except br08001, formatted `"<Tree title>: <class name>"`:
   - Tree title = `MetaboliteClass.tree` with `_` → space and the first letter capitalised.
   - Class name = KEGG's name with the 2-letter LIPID MAPS code removed (`FA  Fatty acyls` →
     `Fatty acyls`).
   - Expected today: 651 metabolites, 28 distinct values, e.g. `Lipids: Fatty acyls` 253,
     `Lipids: Prenol lipids` 137, `Phytochemical compounds: Terpenoids` 57.
b. **A `ControlledVocabulary` node** for `(Metabolite, kegg_brite_classes)`, closed, with
   `value_descriptions` naming the source tree code (e.g. `Lipids: Fatty acyls` → "br08002, top level").
c. **Rename `Metabolite.kegg_compound_categories` → `kegg_functional_categories`**, with its
   `ControlledVocabulary` entry. "Compound categories" doesn't say which KEGG tree it is, and it
   reads as the umbrella for both fields. The explorer will use the new name in its output
   regardless; until the KG renames, it aliases the old property.
d. **A KG test** that `kegg_brite_classes` equals the derivation above for every metabolite.

**Explorer impact when landed:**
- the builders read the property instead of the subquery (rows and envelope unchanged);
- `list_filter_values` switches from the derived list to the vocabulary read;
- the hash re-pins;
- (c) is a one-line builder change plus a vocab mapping update.

Not blocking: the explorer ships the derived version first.

---

## KG follow-up (2026-10-15, for discussion, nothing changed yet)

Plan file on the KG side: `plans/metabolite_mnx_stereo_guard.md`.

### Root cause (asks 1–4)

The table is correct, and the cause is narrower than the asks assume.
- All 21 multi-KEGG nodes come from `mnx_same_entity` links.
- That basis (and `manual`) **deliberately skips** the KEGG↔KEGG guard in `canonical.canonicalise`. §1 says "two KEGG ids merge only on MNX evidence or a curated merge", so MNX was trusted outright.
- MNX treats a stereo-unspecified compound, or a generic sugar and its β-anomer, as one entity. Nothing downstream re-checks that.

**The canonical-id choice is not a second bug.** `_choose` already picks the KEGG id with the most references from **gene-reachable** reactions, which is your ask 3a. The β forms really are ahead on that measure:

| Pair | Kept reactions (pre-merge) | All KEGG reactions |
|---|---|---|
| `C05345` β-F6P vs `C00085` F6P | **10** vs 9 | 18 vs **29** |
| `C05378` β-F1,6BP vs `C00354` F1,6BP | **5** vs 4 | 6 vs **11** |

So the rule chose correctly. Once the merges stop, it no longer has to choose between these ids.

### Proposed fix

**1. Stereo guard on MNX links.** Refuse an MNX link between two groups with different KEGG ids when some KEGG pair across them is *stereo-distinct*. Two KEGG ids are stereo-distinct when:
- one has a non-class ChEBI term whose InChIKey shares the other's connectivity block;
- that InChIKey's stereo layer appears on none of the other's terms in that block;
- the two term names are **not** a cis/trans or E/Z pair. These are exempt, as §3.6 already treats them; this keeps caffeate merged.

The guard uses ChEBI's per-KEGG-id terms, not the node's `inchikey`. That InChIKey comes from MNX, so every member of an MNX group shares it.

Tested against today's 21 groups:
- it refuses exactly your 9 stereo/anomer pairs;
- it allows all 10 pairs you called fine;
- `manual` overrides stay exempt.

**2. Curated `keep_separate` for the two pairs no structural test can see:**
- `C00193` Aromatic aldehyde / `C00261` Benzaldehyde;
- `C03688` Apo-[ACP] / `C16240` [Lipoyl-carrier protein]-L-lysine.

The KG override key is `keep_separate:`, not `no_merge:`.

ChEBI makes `C00193` hard to catch: it cross-references `C00193` to benzaldehyde itself as well as to the class "arenecarbaldehyde". A class → member rule based on ChEBI would also split phenol (`C15584` carries the class "phenols"), so this one stays curated.

**3. Tests.**
- Unit tests for the guard.
- A step-6 stage-P check: the build fails if any written node's `kegg_compound_ids` holds a stereo-distinct pair.
- A KG test that your 11 pairs sit on 11 × 2 different nodes.

That covers ask 4. The class → member half of ask 4 can only be tested as "the curated pairs stay apart", because no general test exists for it (see point 2).

### Stereo links after the split

The existing ChEBI `is_a` walk re-creates `Metabolite_is_stereo_form_of` for 8 of the 9 pairs:
- `C00197→C00597`, `C01102→C05702`, `C03227→C02794`, `C04272→C04039`, `C06010→C00900`, `C16241→C00725`;
- `C05345→C00085`, `C05378→C00354` (the two anomer pairs).

`C17345` / `C04644` gets no edge, because ChEBI has no `is_a` between them. They become two plain nodes.

**Correction on "nothing for anomer-only pairs, per §21":** §21 says the opposite, "Anomer stereo edges are still emitted". What §21 forbids is moving a *measurement* onto an anomer. Unless you want to reopen that, the two fructose anomer edges come back.

### Open question for you: MNX fields on a split pair

After the split, both nodes still carry the same `mnxm_id`, and through it the same `inchikey`, `smiles`, `hmdb_id` and MNX ChEBI aliases. Stage H refuses to build when an identifier sits on two nodes. Proposal:
- The MNX fields stay on the node whose ChEBI InChIKey equals MNX's InChIKey (protonation ignored). β-F6P keeps `MNXM1107898` and `HMDB0003971`, because MNX describes the β-anomer.
- The other node (`C00085`) drops `mnxm_id`, `smiles` and `hmdb_id`. It takes `inchikey` from its own primary ChEBI term and keeps `formula` and `mass`, which are the same across stereoisomers.
- Where neither node matches (the two carrier proteins have no InChIKey), the node `_choose` would have kept keeps the MNX fields.

Effect for you: the generic forms (`C00085`, `C00354`, `C00597`, …) come back **without** an `mnx:` / `hmdb:` entry in `all_identifiers`. An MNX or HMDB id the resolver receives lands on the specific form. That is the same situation as ask 5, and it is what MNX asserts. Is that acceptable, or do you want the generic node to keep the MNX id (which means removing it from the specific node)?

### Ask 3b (ion over acid): proposed curated pin, not a rule

A general "prefer the charged form" rule fails. ChEBI cross-references `C00094` "Sulfite" to *sulfurous acid*, so the rule would move the sulfite node onto hydrogensulfite `C11481`. We propose instead a short `canonical:` pin list in `metabolite_identity_overrides.yaml`: `C00698` chloride, `C01324` bromide, `C00742` fluoride. Pinning changes those three nodes' ids (`C01327` → `C00698`, and so on). Do you want that in the same rebuild, or later?

### Ask 5 (HMDB0000122 on β-D-glucose): curated, follow-up

This is not a merge or pick bug, and the HMDB id comes from MNX:
- MNX's `MNXM1364060` (β-D-glucose) carries `HMDB0000122`;
- HMDB's own "D-Glucose" record has the β-D-glucopyranose structure;
- `CHEBI:17634` D-glucose has no KEGG xref and no InChIKey, so no node ever picks it up.

Fixing it means a curated xref move: `HMDB0000122` and `CHEBI:17634` → `C00031`. We'd rather not write an algorithm that second-guesses MNX and HMDB here. We will report the count you asked for (HMDB / ChEBI xrefs on anomer-only nodes whose generic sibling exists) with the rebuild. The move itself would come as a follow-up, using the same override file. Agreed?

### Ask 6 (BRITE classes + rename): accepted as proposed

Your expected numbers reproduce exactly from the committed class caches: **651 metabolites, 28 values**, `Lipids: Fatty acyls` 253, `Lipids: Prenol lipids` 137, `Phytochemical compounds: Terpenoids` 57.
- **a, b, d:** yes. `kegg_brite_classes` is computed post-import from the `MetaboliteClass` trees, with a closed `ControlledVocabulary` whose `value_descriptions` name the tree code. The KG test re-derives the property.
- **c:** yes, renamed to `kegg_functional_categories`, with a `### Breaking` CHANGELOG entry. There is no alias period on the KG side, since you already alias.

Proposal: ship asks 1–4 and 6 in one rebuild, so you re-pin the vocabulary hash once. 3b and 5 go in that rebuild only if you agree to the curated pins / moves above.

**Please answer:**
1. Who keeps the MNX fields on a split pair?
2. Do the anomer edges stay, as §21 says?
3. 3b: now or later?
4. 5: is a curated follow-up acceptable?

## Explorer reply (2026-10-15)

The root cause and the fix plan are agreed. The guard you describe (ChEBI per-KEGG-id terms,
connectivity block plus stereo layer, a cis/trans and E/Z exemption, `manual` exempt) is better than
what we asked for, and it's verified against all 21 groups. So is `keep_separate:` for the two class
and carrier-protein pairs. Thanks also for the canonical-choice numbers: ask 3a withdrawn, since the
rule chose correctly. One rebuild for asks 1–4 + 6 is good.

**Answers:**

1. **MNX fields on a split pair: go with your proposal.** The structure-matching node keeps the MNX
   fields: β-F6P keeps `MNXM1107898` / `HMDB0003971`, and the generic `C00085` drops `mnxm_id` /
   `smiles` / `hmdb_id` and takes `inchikey` from its own primary ChEBI term. That is what MNX and
   HMDB assert, and the explorer shouldn't second-guess them either. One condition:
   - **the generic node must keep its own ChEBI ids** (primary + secondary, as `chebi:` CURIEs) in
     `all_identifiers`, so a ChEBI id for the generic form resolves to the generic node.

   An MNX or HMDB id landing on the specific form is fine on our side. The stereo-form link
   connects the two, and the explorer's planned "other stereo form" hint will point from one to the
   other.
2. **Anomer edges stay.** You're right: §21 keeps anomer stereo edges and only forbids moving a
   *measurement* onto an anomer. Our "nothing for anomer-only pairs" misquoted it. Please re-create
   the `C05345→C00085` and `C05378→C00354` edges. `C17345` / `C04644` ending up as two unlinked
   nodes is fine.
3. **3b: now, in the same rebuild.** One absorb is better than two. Pin `C00698` chloride, `C01324`
   bromide, `C00742` fluoride. The old ids (`C01327` …) stay in `all_identifiers` as merged
   members, so the explorer resolver maps them, and they belong in `metabolite_id_remap.tsv`.
4. **5: a curated follow-up is acceptable.** Moving `HMDB0000122` and `CHEBI:17634` → `C00031` through the
   override file is the right mechanism. Please include the count (HMDB / ChEBI xrefs on
   anomer-only nodes whose generic sibling exists) with this rebuild, so we can judge whether the
   follow-up is one move or a list. If the override is trivial to add now, put it in this rebuild.

**Ask 6, explorer side:**
- the explorer ships `kegg_brite_classes` **derived** first, and switches to the property at absorb;
- for the rename it reads `coalesce(m.kegg_functional_categories, m.kegg_compound_categories)`, so
  the build works on either side of the rebuild;
- the KG's `### Breaking` CHANGELOG entry for (c) is fine. Please also list it in `breaking_changes`
  when the release is stamped.

## KG reply (2026-10-15): answers accepted, plus a 2× margin on the canonical choice

All four answers are adopted as written:
1. MNX fields go to the node whose structure matches.
2. Anomer edges are re-created.
3. The halide pins (3b) ship in this rebuild.
4. Ask 5 is curated: the count ships with this rebuild, and the move too if the override stays
   small.

Ask 6 is fine as planned. The rename goes in `### Breaking` and in `breaking_changes` when the
release is stamped.

### Your condition on answer 1: the generic node keeps its own ChEBI ids

Agreed, and it needs one explicit rule. Today the specific node also picks up ChEBI ids through
MNX's alias list. After the split that list could still name a generic term (e.g. `chebi:15946`
keto-D-fructose 6-phosphate, which ChEBI cross-references to `C00085`).

**Rule:** a ChEBI term that is the KEGG cross-reference of a written KEGG node is published only
on that node, never on a sibling through MNX aliases.

So `C00085` carries `chebi:15946` and `chebi:61553` (primaries and secondaries, as CURIEs) and
`C05345` does not. The existing identifier-uniqueness check (stage H) enforces this, so a
violation fails the build instead of shipping.

### New: the canonical-id rule gets the same ≥ 2× margin as the dominant-form rule

Today the two "most abundant" rules disagree:
- **dominant-form rule** (spec §2 goal 11 / §6.5): requires ≥ 2× gene-reachable catalysing
  reactions over the runner-up. A close call needs an override.
- **canonical choice inside a merge group** (spec §3.1): takes the plain maximum. 10 vs 9 is
  enough.

That inconsistency is why β-F6P won silently. Proposed spec change to §3.1:

1. **Pinned:** a `canonical:` entry in `metabolite_identity_overrides.yaml` names the winner (the
   new 3b mechanism).
2. **Otherwise:** the KEGG id with the most reaction references, **only if it has ≥ 2× the
   runner-up's**.
3. **Otherwise, the build fails** (stage P): `canonical_margin_unresolved`, listing the group and
   its counts. A human adds a `canonical:` pin.

This mirrors "a smaller margin, a tie, or a family with no catalysis requires an override". We
prefer failing the build to a silent tiebreak (lowest C-number), because a close call is exactly
the case where a human should look.

**Measured against today's groups:**

| | Groups |
|---|---|
| Below 2× today | 5: `C05345`/`C00085` 10 vs 9, `C05378`/`C00354` 5 vs 4, `C06010`/`C00900` 5 vs 3, `C04272`/`C04039` 3 vs 2, `C17345`/`C04644` 1 vs 1 |
| …of which are stereo pairs | **all 5**, so the guard splits them before the rule runs |
| Surviving groups (10) + halide pins (3) | all clear 2× or are pinned |

**Net effect on this build: zero.** It is a backstop. If MNX introduces a new conflation the
guard doesn't recognise, the build stops instead of silently renaming a hub metabolite.

The halide pins also override the margin. Cl⁻ `C00698` has 1 reaction against 13 for HCl
`C01327`, and the pin is what lets the ion win.

**Spec edits:**
- §3.1 gets the 3-step rule above;
- the overrides table (§6) gains `canonical:` (one entry per group; an entry naming a non-member
  or a merged-away id fails step 6, a stale one is reported);
- stage P (§7) gains `canonical_margin_unresolved`.

Any objection to failing the build rather than falling back to a tiebreak?

## Explorer reply (2026-10-15, 2)

**ChEBI publishing rule: agreed.** "A ChEBI term that is the KEGG cross-reference of a written
KEGG node is published only on that node" is exactly the condition. Having stage H enforce it is
the right guard.

**≥ 2× margin, failing the build on a close call: no objection. Please do it.** A silent tiebreak
that renames a hub metabolite is the worst outcome for the explorer: ids, names and goldens all
move with no announcement. A failed build with a named group is cheap to fix with a `canonical:`
pin. Two small requests:

1. **Make the failure message actionable.** It should name the group's KEGG ids and names, both
   counts, and a ready-to-paste `canonical:` line. Whoever hits it during a routine paper load
   shouldn't need to read the spec.
2. **Optional second measure before failing.** For groups where neither id has gene-reachable
   reactions (0 vs 0; TCDB-only compounds, likely as more organisms and papers arrive), consider
   applying the same 2× test to *all* KEGG reaction references before giving up. If you'd rather
   keep one measure and pin by hand, that's fine; tell us how many 0-vs-0 groups exist today. We
   expect none, given your table.

Nothing else from the explorer on this round. We'll absorb the rebuild when it lands: asks 1–4,
3b and 6, plus 5 if it fits.

## KG reply (2026-10-15, 2): both requests adopted; design closed

**1. Actionable failure message: yes.** For each unresolved group, `canonical_margin_unresolved`
prints:
- every member's KEGG id and KEGG name;
- both counts for each member (gene-reachable reactions and all KEGG reactions);
- the margin that failed;
- a ready-to-paste block:

```yaml
canonical:
  - id: "kegg.compound:C00085"
    group: ["kegg.compound:C00085", "kegg.compound:C05345"]
    reason: "<why this member>"
```

The same text goes to `metabolite_identity_report.json` (`canonical_margin_unresolved`), so it is
on record even when the console log has scrolled away.

**2. Second measure: adopted, as a fallback only.** If neither member has a gene-reachable
reaction (0 vs 0), apply the same ≥ 2× test to **all** KEGG reaction references before failing.

It never runs when the first measure has any signal. On the all-KEGG count the generic `C00085`
leads (29 vs 18, below 2×), while on gene-reachable reactions β-F6P leads, so the two can
disagree. The gene-reachable measure stays authoritative.

**Count today: 0 groups are 0 vs 0.** The closest are:
- `C00992` / `C08230` aquacobalamin / hydroxocobalamin, 1 vs 0;
- `C15586` / `C01736` nebularine, 1 vs 0.

Both pass, since 1 ≥ 2 × 0. A 1 vs 0 lead counts as a margin by design: one reaction against
none is a real hub signal.

**Final rule (spec §3.1):**
1. a `canonical:` pin, if present;
2. else most gene-reachable reaction references, if ≥ 2× the runner-up;
3. else, only when that measure is 0 vs 0: most KEGG reaction references, if ≥ 2×;
4. else step 6 fails with `canonical_margin_unresolved`.

**Rebuild scope:**
- asks 1–4;
- 3b (pins for chloride `C00698`, bromide `C01324`, fluoride `C00742`);
- 6 (`kegg_brite_classes` + its vocabulary + the `kegg_functional_categories` rename);
- the margin rule;
- the anomer-xref count;
- ask 5's `HMDB0000122` / `CHEBI:17634` → `C00031` move, if the override stays small.

Delivered with a post-rebuild section in `docs/kg-changes/metabolite-identity-and-classes.md` (§38)
and a pointer here.

## KG delivery (2026-10-15): implemented and rebuilt

Details and live numbers: `multiomics_biocypher_kg/docs/kg-changes/metabolite-identity-and-classes.md`
**§38**. In short:
- **Asks 1–4, 3b, 6 and the margin rule are shipped.**
  - `Metabolite` 3,203 → 3,214.
  - Multi-KEGG nodes 21 → 10 (the 10 you called fine).
  - `Metabolite_is_stereo_form_of` 68 → 76, including both fructose anomer links.
  - `C00085` is "D-Fructose 6-phosphate" again, and the Capovilla / Biller fructose-6P rows stay on it.
  - Halides are named for the ion.
  - `catalyzed_metabolite_count` is +5 on most organisms.
- **Two deviations from what we agreed:**
  - The `kegg_brite_classes` vocabulary node has **no `value_descriptions`**. Its values contain
    `": "`, the separator of published value descriptions, so they would not split back. The tree
    codes are in its `description` instead.
  - The `canonical_margin_unresolved` text appears only in the step-6 error and log, **not** in the
    report. A failed step 6 writes no file.
- **One addition:** a ChEBI term shared by separate KEGG nodes now goes to its single unambiguous
  owner, not to none. Benzaldehyde, (R)-lipoic acid, acetoin, D-ribulose and α-D-galactose regain
  ChEBI ids.
- **Ask 5:** 17 anomer → generic pairs, and 10 of the anomers carry an HMDB id. That makes the fix a
  curated list, not one move, so it stays a follow-up. The table is in §38.

## KG delivery, ask 5 (2026-10-15): generic sugar records moved

Shipped as curated `xref:` overrides (KG change doc §39). We checked HMDB's own record names in
MNX's local `chem_xref.tsv`.
- **Moved to the generic node:**
  - `HMDB0000122` D-Glucose → `C00031`;
  - `HMDB0000143` D-Galactose → `C00124`;
  - `HMDB0000660` D-Fructose → `C00095`;
  - `HMDB0001058` Fructose 1,6-bisphosphate → `C00354`.
- **Added, previously on no node:**
  - `HMDB0000124` Fructose 6-phosphate → `C00085`;
  - `CHEBI:17634` D-glucose → `C00031`.
- **Left in place:** records named for the anomer (α-glucose, β-galactose, β-G6P, β-GlcNAc,
  β-F6P), and GDP-mannose on KEGG's hub `C00096`.
- **No node, edge or paper-row changes**, and the release TSVs are unchanged.
- **For your resolver:** `HMDB0000122` and `CHEBI:17634` now resolve to `C00031`. `C00031`'s
  scalar `hmdb_id` is now `HMDB0000122`; `HMDB0304632` stays in `all_identifiers`.

---

## Ask 7 (2026-10-16, small, wording only): KEGG classification vocab descriptions say "absent when in none"

Both `ControlledVocabulary` descriptions end with **"Sparse: absent when the metabolite is in none."**
- `(Metabolite, kegg_functional_categories)`
- `(Metabolite, kegg_brite_classes)`

That reads as a negative ("this compound belongs to none of these categories"). It's the opposite
of how the data works and of what the explorer docs now say. KEGG's compound BRITE lists are
hand-curated, representative lists: fumarate, ethanol and L-carnitine are absent, yet they are
organic acids and the like. Absent means "KEGG did not list it", not "in none".

The explorer passes these descriptions through verbatim:
- `list_filter_values(filter_type='kegg_functional_category' / 'kegg_brite_class')` returns them
  in its `description` field;
- `kg_schema` / `run_cypher` users read them directly.

So the text contradicts the frozen explorer field descriptions right next to it.

**Ask:** replace the last sentence in both with something like:

> Sparse: absent when KEGG does not list the metabolite in any of these trees. The lists are
> hand-curated and partial (~10% / ~20% of metabolites), so absence is not evidence that a
> category does not apply.

Hash-neutral if only `description` changes. If it does move the hash, say so and the explorer
re-pins. No explorer code change.

## KG reply, ask 7 (2026-10-16): done, hash-neutral

Both descriptions now end with an absence sentence instead of "absent when the metabolite is in
none":
- `kegg_functional_categories`: "Sparse: absent when KEGG does not list the metabolite in
  br08001. The list is hand-curated and partial (about 10% of metabolites), so absence is not
  evidence that a category does not apply."
- `kegg_brite_classes`: the same, with "in any of these trees" and "about 20%".

The coverage figures are measured: 334 and 652 of 3,214 metabolites.

**Hash unchanged.** `description` is not in `controlled_vocabularies_hash`; we verified by
hashing both versions. No other vocabulary uses that wording. The live vocabulary nodes carry the
new text after the 2026-10-16 rebuild.

## Ask 8 (2026-10-16): missing `Metabolite_is_stereo_form_of` edges on common generic substrates

The explorer is adding a stereo-form hint to `genes_by_metabolite` / `metabolites_by_gene` /
`list_metabolites` (backlog 2c.8). It works off the stereo edges as they are. A check of
stereo-unspecified names against their L- / D- / α- / β- named siblings found **14 generic
nodes with no stereo edge at all**, although a specific form exists and carries the catalysis.
Most are heavily transported, so the TCDB → catalysis join fails on exactly the compounds an
analysis would try first (isoleucine, glucose, mannose, galactose).

| Generic node | InChIKey | `structure_kind` | catalysts | transporter genes | Unlinked specific forms (catalysts) |
|---|---|---|---|---|---|
| `chebi:17234` glucose | yes | defined | 0 | 3,091 | `C00031` D-Glucose (284), `C00221` β-D-Glucose (192), `C00267` α-D-Glucose (183) |
| `chebi:37684` mannose | **no** | defined | 0 | 2,958 | `C00159` D-Mannose (15) |
| `chebi:22599` arabinose | **no** | defined | 0 | 2,780 | `C00259` L-Arabinose (15) |
| `C01582` Galactose | yes | defined | 0 | 2,627 | `C00124` D-Galactose (72), `C00984` α (58), `C00962` β (16), `C01825` L-Galactose (1) |
| `C01496` Fructose | **no** | generic | 0 | 2,342 | `C00095` D-Fructose (214), `C02336` β-D-Fructose (119), `C10906` D-Fructose (0) |
| `chebi:24278` glucoside | **no** | generic | 0 | 2,114 | `C00963` β-D-Glucoside (68) |
| `chebi:26546` rhamnose | **no** | defined | 0 | 1,691 | `C00507` L-Rhamnose (3), `C02338` β-L (5), `C02476` α-L (5) |
| `chebi:24898` isoleucine | **no** | defined | 0 | 1,597 | `C00407` L-Isoleucine (121) |
| `chebi:33709` amino acid | **no** | generic | 0 | 942 | `C00151` L-Amino acid (60), `C00405` D-Amino acid (23) |
| `chebi:5417` glucosamine | **no** | defined | 0 | 636 | `C00329` D-Glucosamine (20) |
| `chebi:24175` galacturonate | **no** | generic | 0 | 591 | `C00333` D-Galacturonate (9) |
| `C05052` Ribulose | yes | defined | 0 | 586 | `C00309` D-Ribulose (3), `C00508` L-Ribulose (5) |
| `C01452` Sorbose | yes | defined | 0 | 72 | `C00247` L-Sorbose (2), `C00764` D-Sorbose (1) |
| `chebi:30867` dihydroorotate | yes | defined | 0 | 0 | `C00337` (S)-Dihydroorotate (114) |

Method: an explorer-side name match (strip a leading `L-` / `D-` / `DL-` / `(R)-` / `(S)-` /
`(±)-` / `α-` / `β-` descriptor; compare to the generic node's name, case-insensitive), kept only
where linking would change a count. It is a candidate list, not a rule; name matching misses
anything named differently (e.g. "D-Hexose").

**Three different causes, as far as we can tell:**
1. **No InChIKey on the generic node** (mannose, arabinose, rhamnose, isoleucine, glucosamine,
   Fructose, galacturonate, glucoside). The edge rule needs a shared InChIKey connectivity block,
   so these can never pass. ChEBI's stereo-unspecified records often lack a structure.
2. **InChIKey present but no edge** (glucose, Galactose, Ribulose, Sorbose, dihydroorotate).
   Possibly no **direct** ChEBI `is_a` (e.g. D-glucose `is_a` D-glucopyranose `is_a` glucose?),
   or a connectivity mismatch from a ring vs open-chain record.
3. **Class terms** (amino acid → L-/D-amino acid, glucoside → β-D-glucoside). These may be
   deliberately out of scope for a stereo edge. Your call; the explorer is fine either way.

**Asks:**
- **8a.** For cause 1, allow the edge when the generic record has no structure but ChEBI has a
  direct `is_a` from the specific form, and the specific form's name minus its descriptor equals
  the generic name (or a curated `stereo_link:` override). Then report how many edges this
  adds.
- **8b.** For cause 2, check why glucose / Galactose / Ribulose / Sorbose / dihydroorotate fail.
  If it's the direct-`is_a` requirement, allowing a short `is_a` path (≤ 2) within the same
  connectivity block would cover them. Anomers stay `is_stereo_form_of` edges, as now.
- **8c.** Say whether class terms (cause 3) should get stereo edges, so the explorer docs can
  state the rule.

**Explorer impact:** none in code. The hint and `include_stereo_forms` pick up new edges
automatically. Goldens with these metabolites move on absorb. Until then the explorer docs say
the edges are incomplete and name these examples.

## KG reply, ask 8 (2026-10-16): root cause, sources evaluated, options (for discussion, nothing changed yet)

### Root cause

Your three causes reduce to one: **the edge rule asks ChEBI for evidence in a form ChEBI doesn't
use for stereo-unspecified compounds.** Today `stereo_links` emits `specific → generic` only when
(a) a ChEBI term of the specific node has a **direct** `is_a` to a term of the generic node, and (b)
both nodes have an InChIKey with the same connectivity block. Checked against the raw ChEBI 256
file:

1. **ChEBI never links these directly.** It goes through the ring form, then the D-/L- form:
   `D-glucopyranose > D-glucose > glucose`, `alpha-L-galactose > L-galactopyranose > L-galactose >
   galactose`. That is 2–3 `is_a` steps in every sugar case. ChEBI has no "stereo form of" relation;
   `is_enantiomer_of` is its only stereo-specific one.
2. **ChEBI gives the stereo-unspecified terms no structure.** glucose, mannose, galactose,
   arabinose, rhamnose, isoleucine and glucosamine have no SMILES or InChIKey in ChEBI, only a
   generalized formula. Fructose has no formula either, which is why `C01496` reads
   `structure_kind = generic`. Our parser loses nothing.
3. **Some "generic" nodes carry one specific form's structure.** `C01582` Galactose carries
   aldehydo-D-galactose's, and `C01452` Sorbose carries keto-D-sorbose's (also its `chebi_id`);
   `C05052` Ribulose is similar. These come from KEGG itself: we checked KEGG's own MOL files, and
   KEGG draws these generics as one stereo form. MNX copies that. `chebi:30867` dihydroorotate
   carries the InChIKey and ChEBI id of (R)-dihydroorotic acid, because its MNX entity
   (`MNXM726835`) *is* (R)-dihydroorotic acid. Its (S) form's `is_a` also points at the acid, which
   the node holds only as a cross-reference.
4. **Class terms** (amino acid, glucoside, galactoside, galacturonate): their "specific forms" are
   many different compounds (glycine, etoposide, ADP-glucose, …).

### Other sources we evaluated (to avoid a more complex ChEBI rule)

- **KEGG MOL structures + InChIKey** (computed locally with RDKit). Rejected, for three reasons:
  - 8 of the 14 generics are `chebi:` nodes with no KEGG entry;
  - KEGG draws `C01582` / `C01452` / `C05052` stereo-specific, and draws "D-Hexose" `C00738`
    stereo-free, so D-Hexose would look like everyone's parent;
  - partially specified sugars (D-F6P vs β-D-F6P) have stereo on both sides, so "has a stereo
    layer" can't tell parent from child.
- **MetaNetX `chem_isom.tsv`** (MNX 4.5, 13,377 parent → child pairs). It reproduces 62 of our 76
  edges, but **covers 1 of your 14** (D-glucose → glucose). It also mixes in class parents
  (glucose → "D-Hexose", cholate → "Bile salt", maltodextrin → "Polysaccharide"), and it can't
  relate the pairs MNX itself conflates (F6P, 3-phosphoglycerate, lipoate…). Rejected as a primary
  source.

The fact that "mannose" is the stereo-unspecified form of D-mannose exists **only in ChEBI's
ontology**, because no source has a structure for the generic. So we keep ChEBI and make the rule
simpler and more chemical, not add a source.

### Options

- **B (KG recommendation). ChEBI-only rule, chemistry rather than names, plus a tiny blocklist.**
  - An `is_a` path of ≤ 3 steps where every term keeps the **same molecular formula and charge**.
    This replaces the InChIKey-block test, which can't work without structures.
  - The generic's term is not a ChEBI class (no structure and no concrete formula).
  - Edges already implied through another node are dropped (β-D-glucose → D-glucose → glucose stays
    two edges).
  - Geometric pairs stay excluded (existing rule).
  - **Simplification: read each node's *published* ChEBI ids** (`chebi_ids`, after the owner rule)
    instead of every KEGG cross-reference. On its own this removes two errors:
    - (S)-acetoin no longer holds "acetoin", so an existing (R)- → (S)-acetoin edge goes away;
    - Galactose no longer holds α-D-galactose, so a Galactose ↔ D-Galactose cycle the path rule
      would otherwise create goes away.

  **Measured on today's data, before the published-ids change:** 24 new edges, 16 correct, covering
  every non-class case in your table plus D-xylose, D-allose, D-sorbitol → glucitol, D-arabitol,
  D-glucarate and GalNAc. The leftovers:
  - 3 → "D-Hexose" `C00738`, a class that ChEBI gives a concrete formula: a 1-line `no_stereo_link:`
    entry;
  - 3 geometric pairs, caught by the existing rule;
  - keto-D-fructose → D-fructose, a tautomer, not a stereo form;
  - the Galactose cycle, removed by the published-ids change.
- **C. Fully curated `stereo_link:` list.** The rule only proposes candidates for review; no
  heuristic in the build. Exact, but every new paper or strain needs a review pass.
- **D (with B or C). Fix the generic nodes that carry a specific form's structure** (cause 3).
  Drop the KEGG / MNX structure and the stereo-specific ChEBI ids from a generic node when ChEBI
  says that structure belongs to a descendant of the node's own term. This is the same policy as
  the shipped MNX split. It is an identity fix as well as unblocking edges.
- **E. Class terms (your 8c): no stereo edges.** Class membership is a different relation.
  Fructose, fucose, N-acetylglucosamine and GDP-fucose look like classes only because ChEBI gives
  them no formula. Under B they stay unlinked; we'd list them, or add them to C's curated list.

**Existing edges this review found wrong** (fixed by B + published ids, or already against spec):
- (R)-acetoin → (S)-acetoin: these are enantiomers;
- geranyl diphosphate → "all-trans-polyprenyl diphosphate": a homolog class, different formula;
- 9,9'-dicis-ζ-carotene → all-trans-ζ-carotene: geometric, against spec §3.6.

**Questions for you:**
1. B + D + E, or C?
2. Is a ring / open-chain tautomer such as keto-D-fructose a "stereo form"? We say no.
3. For the four structureless non-class generics (fructose, fucose, GlcNAc, GDP-fucose): leave them
   unlinked, or add them to a curated list?

## Explorer reply, ask 8 (2026-10-16)

The root cause is convincing: ChEBI never links a generic name directly to its specific form
(the path is 2–3 `is_a` steps), and it gives stereo-unspecified terms no structure, so the
current rule can't fire on them.

**1. B + D + E** (not C). A curated-only list needs a review pass for every new paper or strain,
and that won't be kept up. B is a chemistry rule (same formula and charge along a ≤ 3-step
`is_a` path). It covers every non-class row in our table, finds real ones we missed (D-xylose,
D-allose, D-sorbitol, GalNAc), and removes 3 wrong edges. Three conditions:
- **B, charge test across merged conjugates.** Conjugate acid / base pairs are merged into one
  node, and its published `chebi_ids` hold both the acid and the anion. The same-formula-and-charge
  test should pass when **any** acid / base member matches, not only the scalar `chebi_id`.
  Otherwise a path written against the anion term fails on a node keyed by the acid.
- **D is an identity change, so record it.** Taking the specific form's structure and ChEBI ids
  off `C01582` / `C01452` / `C05052` / `chebi:30867` moves identifiers between nodes. Please list
  every moved id in `metabolite_id_remap.tsv` (or a new basis value), and keep it in the
  receiving node's `all_identifiers`. Then a user holding aldehydo-D-galactose's or
  (R)-dihydroorotic acid's id still resolves to the right node.
- **List the edge changes** (added and removed `Metabolite_is_stereo_form_of`, per pair) in the
  post-rebuild doc. Explorer goldens and docs name specific examples.

**E: agreed.** Class membership is a different relation. The explorer docs will say class
terms (amino acid, glucoside, galactoside, galacturonate) get no stereo link.

**2. Ring / open-chain forms (keto-D-fructose ↔ D-fructose) are not stereo forms.** If ChEBI
marks the pair as tautomers, the identity rules (`chebi_tautomer`) say they are one metabolite,
so it's a merge question, not an edge. If ChEBI doesn't mark them, leave them separate and
unlinked.

**3. Add the four structureless non-class generics to the curated list** (fructose, fucose,
N-acetylglucosamine, GDP-fucose): four one-line `stereo_link:` entries, each with a reason.
Fructose alone has 2,342 transporter genes, and GlcNAc matters for peptidoglycan and chitin
questions. This is not a recurring review burden.

**Explorer impact:** no code change. The stereo-form hint (`stereo_relatives` on
`list_metabolites` / `genes_by_metabolite` / `metabolites_by_gene`, and
`genes_by_metabolite(include_stereo_forms=True)`) picks up new edges automatically. On absorb
the explorer will update the docs paragraph that names mannose / isoleucine / glucose as
unlinked, and regenerate the goldens touching these metabolites.

## KG reply, ask 8 (2026-10-16, 2): B + E agreed; D narrowed after measuring it

**B, condition 1 (conjugates): yes, by construction.**
- The path test runs from **every** published ChEBI id of the specific node to **every** published
  ChEBI id of the generic node.
- A merged acid / base pair contributes both members on whichever side it sits.
- Formula and charge are compared *along the path* (each term against its own `is_a` parent),
  never against the node's scalar `chebi_id`.
- A unit test pins the case of a path written against the anion on an acid-keyed node.

**B, condition 3 (edge list): yes.** The post-rebuild doc lists every added and removed
`Metabolite_is_stereo_form_of` pair.

**Q2 (tautomers): consistent with your rule.**
- ChEBI does **not** mark keto-D-fructose ↔ D-fructose as tautomers; both have empty `tautomers`.
- So they stay separate and unlinked.
- Had it marked them, `C10906` / `C00095` are two KEGG ids, so the KEGG guard would refuse the
  `chebi_tautomer` merge anyway.

**Q3 (curated `stereo_link:`): agreed.** Five lines, each with a reason:
- `C00095` D-fructose → `C01496` Fructose;
- `C01019` L-fucose → `chebi:33984` fucose;
- `C01018` 6-deoxy-D-galactose (D-fucose) → `chebi:33984` fucose;
- `C00140` N-acetyl-D-glucosamine → `chebi:59640` N-acetylglucosamine;
- `C00325` GDP-L-fucose → `chebi:64608` GDP-fucose.

### D: measured, and it is much bigger than the 4 nodes in the ask

About **70 nodes** publish an InChIKey or ChEBI id that belongs to a stereo-specified *descendant*
of their own ChEBI term.

**The ~60 KEGG nodes are mostly correct:** KEGG names the compound generically but draws the
biological stereoisomer:
- 5-methyltetrahydrofolate (6S), folinic acid (6S);
- lipoamide / dihydrolipoamide / lipoyl-AMP (R);
- biopterin / dihydrobiopterin L-erythro, homoserine lactone L;
- D-mannose 6-phosphate drawn as its α-anomer, and similar.

Stripping those would delete good structures. **And B never reads InChIKeys** (the path test
uses formula and charge), so Galactose, Sorbose and Ribulose get their edges without D.

**The harmful cases are `chebi:` nodes** (TCDB substrate names) whose MNX entity is a *different*
stereoisomer, often the non-biological one. 12 of the 173 `chebi:` nodes with an InChIKey publish
one that isn't their own ChEBI term's:

| Node | Publishes |
|---|---|
| `chebi:17964` pipecolic acid | D-pipecolic acid |
| `chebi:37024` 2-aminoadipic acid | D-2-aminoadipic acid |
| `chebi:64307` 2,4-diaminobutyric acid | D-2,4-diaminobutyric acid |
| `chebi:30867` dihydroorotate | (R)-dihydroorotic acid (the biological form is S) |
| `chebi:37690` allose | L-allopyranose |
| `chebi:17234` glucose | a partially specified form (ChEBI gives glucose no structure) |
| bromate, iodate, chlorate, oxaliplatin, α-cyclodextrin, Tyr-Tyr | representation variants of the same compound |

**Proposed D (narrowed; no heuristic):**
- A `chebi:` node's `inchikey` / `smiles` come from **its own ChEBI term**, never from MNX: none
  when ChEBI has none (glucose, allose).
- Its `chebi_ids` are its own term, its secondary ids and merged conjugates / tautomers. MNX's
  ChEBI aliases for the entity are not published on it.
- KEGG-keyed nodes keep KEGG's drawing, which is KEGG's own assertion; unchanged.

**Your condition 2 (record moved ids):** the ids this removes, e.g. `chebi:41582` D-pipecolic acid
on pipecolic acid, mostly belong to **no** node in the KG.
- Keeping them resolvable to the generic node would keep the wrong answer.
- So we propose a release TSV `metabolite_xref_removed.tsv` (`id`, `was_on`, `reason`), and no
  `all_identifiers` entry. A resolver lookup of `chebi:41582` then returns not-found with a
  documented reason, instead of pipecolic acid.
- Where a removed id does name a written node, it is already that node's own identifier; no move
  is needed.

OK with narrowed D and the not-found behaviour?

## Explorer reply, ask 8 (2026-10-18): narrowed D accepted, two small points

**B, E, Q2, Q3: accepted as written.** The any-to-any id path test closes the conjugate concern,
and the five curated `stereo_link:` lines are what we asked for.

**Narrowed D: accepted.** Keeping KEGG's drawing on KEGG-keyed nodes is right, because it is
KEGG's own assertion and usually the biological isomer. Limiting the fix to `chebi:` nodes whose
MNX entity is another stereoisomer removes the wrong answers without a heuristic. Two points:

1. **Make the removed ids explainable at query time, not only in a release TSV.** The explorer
   can't read `metabolite_xref_removed.tsv` at runtime. A user holding `chebi:41582`
   (D-pipecolic acid) would get a bare `not_found` with no hint that the KG has pipecolic acid.
   - **Ask:** a sparse `Metabolite.removed_stereo_xrefs: str[]` on the node the id was removed
     from, with no identity meaning and never in `all_identifiers`. This is the same pattern as
     `recurated_from_ids`.
   - The resolver then keeps the id in `not_found` and warns: "`chebi:41582` names a different
     stereoisomer than any KG metabolite; it was removed from pipecolic acid (`chebi:17964`),
     the stereo-unspecified form."
   - Not blocking. If you'd rather not add a property, the bare `not_found` is acceptable.
2. **Representation variants are the same compound, so keep their ids resolvable.** Bromate,
   iodate, chlorate, oxaliplatin, α-cyclodextrin and Tyr-Tyr publish a different *representation*
   of the same compound, not a different stereoisomer.
   - Taking `inchikey` / `smiles` from the node's own ChEBI term is fine.
   - But please keep the MNX-side InChIKey / ChEBI alias in `all_identifiers`, so a user holding
     it still resolves. Only the stereo-mismatch ids (the first 6 rows of your table) should drop
     out.

**Please confirm in the post-rebuild doc:**
- **D touches only `inchikey` / `smiles` / `chebi_ids`.** On glucose and allose, `formula`,
  `elements`, `mass` (where ChEBI has a concrete formula) and `structure_kind` stay as they are.
  `list_metabolites` element / mass filters and the `structure_kind` breakdown read them.
- **The count of nodes that lose an InChIKey,** since the explorer's InChIKey resolver path
  depends on it.

**Explorer side:**
- no code change for B / D / E;
- on absorb, regenerate the goldens that touch the newly linked metabolites;
- update the analysis-doc paragraph that names mannose / isoleucine / glucose as unlinked;
- if point 1 lands, add the resolver warning, mirroring `recurated_from_ids`.

## KG reply, ask 8 (2026-10-18, 3): both points adopted; design closed

**Point 1: adopted.** A new sparse `Metabolite.removed_stereo_xrefs: str[]` holds CURIEs, with the
`recurated_from_ids` contract:
- it carries no identity meaning;
- it is never in `all_identifiers`;
- it gets its own `ControlledVocabulary` entry.

It sits on the node the id was removed from, e.g. `chebi:17964` pipecolic acid →
`["chebi:41582", "inchikey:HXEACLLIILLPRG-RXMQYKEDSA-M"]`.

**Point 2: adopted, with a ChEBI-driven split rather than a list.** An MNX-side id on a `chebi:`
node counts as a **stereo mismatch**, and moves to `removed_stereo_xrefs`, only when it is a ChEBI
term, or the InChIKey of a ChEBI term, that is a **strict `is_a` descendant of the node's own
term**. That is ChEBI's own statement that it is a more specific stereo form.
- Representation variants (bromate, iodate, chlorate, oxaliplatin, α-cyclodextrin, Tyr-Tyr) match
  no such descendant. They keep their MNX-side ids in `all_identifiers`; only `inchikey` / `smiles`
  switch to the node's own ChEBI term.
- The same applies to MNX's partially specified glucose key, which matches no ChEBI term.

**Confirmations (repeated in the post-rebuild doc):**
- D runs **after** stage G and touches only `inchikey`, `smiles`, `chebi_ids`, `all_identifiers`
  and the new `removed_stereo_xrefs`. `formula`, `elements`, `mass` and `structure_kind` are
  computed exactly as now.
- The post-rebuild doc gives the number of nodes that lose an InChIKey (expected: the 6
  stereo-mismatch rows, of which glucose and allose end with none), plus the full added / removed
  stereo-edge list.

**Final scope of the next rebuild:**
- **B:** a ChEBI `is_a` path of ≤ 3 steps with the same formula and charge, any published id to any
  published id; no class generics; transitive reduction; existing geometric exclusion; reading
  published `chebi_ids`.
- **`no_stereo_link:`** for D-Hexose.
- **The 5 curated `stereo_link:` lines.**
- **Narrowed D** with `removed_stereo_xrefs`.
- **E** (no stereo edges for class terms).
- **The 3 wrong existing edges removed:** (R)/(S)-acetoin, geranyl diphosphate → polyprenyl
  diphosphate, dicis-ζ-carotene → all-trans.

## KG delivery, ask 8 (2026-10-18): implemented and rebuilt

Details: KG change doc `docs/kg-changes/metabolite-identity-and-classes.md` **§40**. In short:
- **Stereo edges:** `Metabolite_is_stereo_form_of` 76 → **99**: +27 (§40 lists every pair), −4.
  The removals are the 3 wrong edges we named, plus Xylose → D-xylose, which was in the wrong
  direction and is now D-xylose → Xylose.
- **Your table:** 11 of your 14 rows are linked; the 3 class terms are not, as agreed.
- **Nothing else moves:** no node, `structure_kind`, repoint, paper row or dominant-form change.
- **Narrowed D:** 14 `chebi:` nodes change. 2 lose their InChIKey (glucose, allose), 10 have it
  replaced, and 8 carry `removed_stereo_xrefs`.
- **Remap:** new basis `stereo_form_removed`; 1 row, `chebi:144635` → `chebi:64307`.
- **What we added beyond the agreed scope:**
  - 3 extra curated links: sorbose ×2, plus xylose, which KEGG cross-references both ways;
  - a `no_stereo_link:` entry for keto-D-fructose `C10906`, your Q2;
  - the geometric-token rule now handles `9,9'-dicis-` locant forms;
  - conjugate acids / bases count as a node's own identity, but tautomers don't: ChEBI pairs
    L-dopachrome with DHICA as tautomers;
  - formula-less ChEBI terms may sit mid-path (rhamnose).
- **One correction:** `removed_stereo_xrefs` has no `ControlledVocabulary` entry, matching
  `recurated_from_ids`; our earlier reply said it would.

## KG review request, ask 8 (2026-10-18)

The dev graph (`bolt://localhost:7687`) carries the Ask 8 rebuild. The KG suite passes (1,290);
nothing is committed or released yet. Before we commit, please review against your own use. Full
pair lists are in KG change doc §40.

**1. The 27 new `Metabolite_is_stereo_form_of` edges.** Each should read "specific form →
stereo-unspecified form of the same compound". The ones we're least sure about:
- `C19891` 1D-chiro-inositol → `chebi:24848` inositol (chiro is one inositol stereoisomer);
- `C08353` β-D-ribopyranose → `C00121` D-ribose (an anomer → its generic);
- `chebi:16055` aldehydo-L-rhamnose → rhamnose (an open-chain form, but stereo-specified L);
- `C00818` D-glucarate → `chebi:30613` glucarate(2-) (generic at the dianion);
- `C00181` D-xylose → `C01394` Xylose (curated, because KEGG cross-references `C01394` to
  α-D-xylose).

```cypher
MATCH (s:Metabolite)-[:Metabolite_is_stereo_form_of]->(g:Metabolite)
RETURN s.id, s.name, g.id, g.name ORDER BY g.name
```

**2. The 4 removed edges.** Do any goldens or doc examples use them?
- (R)-acetoin → (S)-acetoin;
- geranyl diphosphate → all-trans-polyprenyl diphosphate;
- Xylose → D-xylose;
- 9,9'-dicis-ζ-carotene → all-trans-ζ-carotene.

**3. `removed_stereo_xrefs`** (8 nodes) for your resolver warning. Check the wording against real
cases:
- pipecolic acid → `chebi:41582` D-pipecolic acid, plus 3 more ChEBI ids;
- dihydroorotate → (R)-acid;
- 2-aminoadipic acid → D-;
- allose → L-allopyranose;
- Tyr-Tyr → L,L;
- 2,4-diaminobutyric acid → D-;
- D-glucosyl group → α-;
- lysyl group → D-.

```cypher
MATCH (m:Metabolite) WHERE m.removed_stereo_xrefs IS NOT NULL
RETURN m.id, m.name, m.removed_stereo_xrefs
```

**4. InChIKey changes on `chebi:` nodes:**
- glucose and allose now have **no** InChIKey;
- 10 nodes have their own ChEBI term's key;
- the MNX keys of bromate, iodate, chlorate, oxaliplatin and α-cyclodextrin still resolve through
  `all_identifiers`.

Does your InChIKey resolver path or any golden depend on the old keys?

**5. The new remap basis `stereo_form_removed`.** One row: `chebi:144635` → `chebi:64307`. Does
the resolver need a message for it, like `remeasured_elsewhere`?

**6. The deviations from the agreed scope:**
- 3 extra curated links (sorbose ×2, xylose);
- keto-D-fructose `C10906` blocked from stereo edges;
- the geometric-token rule extended to locant forms;
- conjugates but not tautomers counted as a node's own identity;
- formula-less ChEBI terms allowed mid-path;
- no `ControlledVocabulary` entry for `removed_stereo_xrefs`.

Objections?

Please reply below, under `## Explorer review, ask 8`.

## Explorer review, ask 8 (2026-10-18)

Reviewed against the dev graph (built 2026-10-18T05:51Z) with the explorer's own suites. Explorer
`main` already carries the stereo-form hint. **No objections; OK to commit and release.**

**Evidence:**
- **Regression:** 181 of 184 goldens unchanged. The 3 that move (`list_metabolites_search_glucose`,
  `list_metabolites_id_batch_with_unknown`, `metabolites_by_gene_pmm0913_family_inferred_warning`)
  move by **additions only**: new `stereo_relatives` entries such as glucose → D-Glucose, mannose →
  D-Mannose, isoleucine → L-Isoleucine, arabinose → L-Arabinose, fucose → L-/6-deoxy-D-galactose.
  No existing value changes.
- **Integration:** 564 metabolite / stereo / resolver tests pass, and doc examples show 0 drift.
  The only failure is the vocab-snapshot stamp, which is a routine absorb item.

**1. The 27 new edges: all accepted.** On the five you flagged:
- **1D-chiro-inositol → inositol:** right. The inositols are the textbook stereoisomer family,
  and myo-, scyllo- and muco- link the same way.
- **β-D-ribopyranose → D-ribose:** consistent with α/β-D-glucose → D-glucose (anomer → its
  generic).
- **aldehydo-L-rhamnose → rhamnose:** consistent with Q2. The ring / open-chain difference isn't
  a stereo edge, so there's no edge to L-Rhamnose. It is L-specified, so → the stereo-unspecified
  rhamnose is correct.
- **D-glucarate → glucarate(2-):** fine; the charge state of the generic term doesn't matter.
- **D-xylose → Xylose (curated):** fine, and the direction fix is right.

**2. The 4 removed edges:** no golden or doc example uses them.

**3. `removed_stereo_xrefs`:**
- None of the 17 ids is on any other node (no `all_identifiers` hit), so the resolver's
  fallback is reached only for genuinely absent forms.
- The removed ids have no name in the KG, so the warning won't try to name them. Planned
  wording: "`chebi:41582` is a stereo-specific form with no node in the KG; it was removed from
  pipecolic acid (`chebi:17964`), its stereo-unspecified form. Use that id, or a linked specific
  form (`stereo_relatives`)." The id stays in `not_found`.

**4. InChIKey changes:** no golden, example or resolver test depends on the old keys of glucose,
allose or the 10 replaced nodes.

**5. `stereo_form_removed` remap basis:** no separate message. The explorer never reads the
remap TSV at runtime. `chebi:144635` sits in `chebi:64307`'s `removed_stereo_xrefs`, so it gets
the same warning.

**6. Deviations:**
- No objections.
- **No `ControlledVocabulary` entry for `removed_stereo_xrefs` is correct.** It's an open
  identifier list that the explorer neither filters nor rolls up on, the same as
  `recurated_from_ids`.

**Explorer absorb, after your commit / release:**
- re-snapshot vocab;
- regenerate the 3 goldens;
- rewrite the analysis-doc paragraph that calls mannose / isoleucine / glucose unlinked;
- add the `removed_stereo_xrefs` resolver warning.

## Explorer absorb, ask 8 (2026-10-18): done

Absorbed the 2026-10-18T05:51:30Z build (KG commits `bbcb8219` / `5ac88ef7` / `d4282452`):
- vocab snapshot re-stamped; the hash is unchanged;
- 3 goldens regenerated, additive stereo links only;
- 0 example drift;
- the docs now state the linking rule: generic ↔ specific is linked, class terms and ring /
  open-chain forms are not;
- the `removed_stereo_xrefs` resolver warning is live.

**Ask 8 closed.**
