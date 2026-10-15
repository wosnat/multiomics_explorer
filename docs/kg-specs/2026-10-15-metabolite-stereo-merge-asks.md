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
