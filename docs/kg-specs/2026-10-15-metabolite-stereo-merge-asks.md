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
