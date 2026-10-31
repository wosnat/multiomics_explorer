# Transport follow-ups: best-hit search lines, TCDB display names, stereo flag (2026-10-29)

**Date:** 2026-10-29 · **From:** KG (`multiomics_biocypher_kg`) · **To:** explorer (`multiomics_explorer`)
**Direction:** KG → explorer.
**KG branch:** `worktree-transport-small-followups`, **merged to KG `main` and built 2026-10-31**
(graph built from `ef72f299`). §1 was revised after the explorer's E4 response (new line format,
cap 8); the counts in §1–§3 are now the live ones. See "KG built (2026-10-31)" at the end.
**KG plan:** `multiomics_biocypher_kg/plans/transport_small_followups.md`.
**Follows:** `2026-10-23-tcdb-cleanup-explorer-asks.md` (the open follow-ups from projects 2 and
3a and from the TCDB integration review).

This is a heads-up, plus one question and one hand-off for you. Nothing here is breaking:
there are two new things, one existing flag now catches more cases, and no property is removed
or renamed. Please answer in the "Responses" section at the end.

## Summary

| # | Change | Where | Breaking? |
|---|---|---|---|
| 1 | `[tcdb_best_hit]` lines in `Gene.alternate_functional_descriptions` | Gene | No (new lines in an existing list) |
| 2 | New `TcdbFamily.display_name` | TcdbFamily | No (new dense property; `name` unchanged) |
| 3 | `stereo_assignment = 'dominant_form_assumed'` for 11 more paper names (4 name matches + 7 corrected aliases) | Assay edges | Value change on those names' edges |
| 4 | Backlog items closed with no graph change | — | — |

## 1. Genes can be found by their best-hit TCDB system

prepare_data step 2 adds **one line** to `Gene.alternate_functional_descriptions` when the
gene's **rank-1** diamond best hit is a `tcdb_gate = 'direct'` edge. That means identity ≥ 40,
landing on a kept `tc_system` after the `seed_aliases` remap. Format:

```
[tcdb_best_hit] <system display_name> [<tcdb_id>] :: [tcdb_substrates] <name>, <name>, …
```

(Revised 2026-10-31, E4.1: the fixed words are bracketed underscore tokens. The full-text
analyzer keeps `tcdb_best_hit` / `tcdb_substrates` as single tokens, so "substrates" and "TC"
are no longer added to every carrier.)

- The substrate clause lists the system's own `Tcdb_family_transports_metabolite` /
  `Tcdb_family_transports_chemical_role` targets by name, sorted. It stops after **8** names (revised from 15, E4.2) with
  "and N more", and is left out when the system has no curated substrate.
- The line states only what the `direct` best-hit edge states. Near-tie best hits, tier-3 best
  hits, eggNOG and `diamond_tier` calls never produce a line.
- `geneFullText` already indexes the field, so no index changes. "urea porter", "cyanate" and
  "nitrite" now find genes by the system they resemble.
- Live (2026-10-31): **16,423 genes** get a line, **8,775** of them with substrates (59
  truncated with "and N more"). That is every one of the 16,423 rank-1 best-hit edges with
  `tcdb_gate = 'direct'`, out of **28,950** rank-1 best-hit edges in all.

Three MED4 genes (the first is urtA, PMM0970):

```
[tcdb_best_hit] The high-affinity (<1 μM) urea porter [3.A.1.4.4] :: [tcdb_substrates] Urea
[tcdb_best_hit] Bispecific cyanate/nitrite transporter. [3.A.1.16.2] :: [tcdb_substrates] Cyanate, Nitrite
[tcdb_best_hit] Ammonium/methyl ammonium uptake permease, AmtB (may need AmtB to concentrate [14C]methyl ammonium) [1.A.11.2.5] :: [tcdb_substrates] Ammonia, Tetramethylammonium
```

Notes for the surface:
- The label is new. If the explorer parses or lists the `[label]` prefixes of
  `alternate_functional_descriptions` (`[pfam]`, `[interpro]`, `[tigr_role]`,
  `[tigr_role_inferred]`, …), add `[tcdb_best_hit]`.
- A text match on this line is homology to a characterised TCDB system. It does not show the
  gene moves that compound. The trust surface is still the edge (`tcdb_call`, `tcdb_gate`,
  `rank`, `identity`). If a tool explains *why* a gene matched a text search, say "best TCDB
  hit", not "transports".
- The line can repeat a system name that is unhelpful upstream (e.g. "Uncharacterized DUF1469
  protein of 128 aas and 2 TMSs."). TCDB's own text is not rewritten.

## 2. `TcdbFamily.display_name`

New dense string property on every `TcdbFamily` node:
- It equals `name`, except for an **unnamed subfamily or system**: one with no upstream header,
  an empty name cell and no protein cell. Those borrow the name of their nearest named ancestor:
  `"The ATP-binding Cassette (ABC) Superfamily — subfamily 3.A.1.118"`,
  `"… — system <tcdb_id>"`.
- It applies to 1,248 subfamilies (573 with genes) and 384 systems (11 with genes) on the
  current caches.
- **`name` is unchanged**, so `t.name = t.tcdb_id` still marks the unnamed nodes. That marker
  was chosen in the 2026-08-12 names spec instead of a `name_source` property, and code relies
  on it.
- It is for display only. `direction` and every other rule read TCDB's own `name`. A system
  showing "… Efflux Family — system X" is **not** given the family's direction.
- It is not in `tcdbFamilyFullText`, because it adds no searchable words beyond the ancestor's
  name, which is already indexed on the ancestor.

## 3. `stereo_assignment` now also flags stereo forms with no ChEBI enantiomer

`Assay_quantifies_metabolite` / `Assay_flags_metabolite` `stereo_assignment` is
`dominant_form_assumed` when the paper's name gives no stereo form and the KG node is a specific
form. Until now, "specific form" meant the node's ChEBI term has `is_enantiomer_of`. That missed
diastereomers and meso partners. The new rule adds one more case: the node's **KEGG entry** is
ChEBI-filed under both a stereo-specific and a stereo-unspecified form of one structure (same
InChIKey connectivity block). Two kinds of KEGG entry are exempt:
- entries filed only under E/Z forms (fumarate);
- entries whose forms differ only by tautomer (xanthine) or by cis/trans in the name
  (trans-cinnamic acid).

Measured on the committed caches, **4 rows change from `as_reported` to
`dominant_form_assumed`**:

| Paper | Name in paper | Node |
|---|---|---|
| biller 2022 | Homocystine | `kegg.compound:C01817` L-Homocystine |
| biller 2022 | Methylthioadenosine | `kegg.compound:C00170` 5'-Methylthioadenosine |
| Kujawinski 2023 | 5'-methylthioadenosine | `kegg.compound:C00170` |
| Kujawinski 2023 | pantothenic acid | `kegg.compound:C00864` Pantothenate |

**Rows that report a KEGG id stay `as_reported`**: the paper named that exact entry.

**Paper aliases now follow the same rule.** The `stereo_assignment` values in
`metabolite_aliases.yaml` were set while fixing IDs, mostly restating the old default, not as
stereo judgements. So:
- the field is now optional, and when omitted the name-match rule decides;
- an explicit value still wins, but if it differs from the rule it is listed in the identity
  report's new `alias_stereo_review`.

7 alias values are corrected from `as_reported` to `dominant_form_assumed`:

| Paper | Alias | Node |
|---|---|---|
| biller 2022 | Adenosyl Homocysteine | `kegg.compound:C00021` S-Adenosyl-L-homocysteine |
| biller 2022 | Glutathione Disulfide | `kegg.compound:C00127` Glutathione disulfide |
| biller 2022 | Vitamin B5 | `kegg.compound:C00864` Pantothenate |
| Kujawinski 2023 | glutathione oxidized | `kegg.compound:C00127` |
| Kujawinski 2023 | 2,3-dihydroxypropane-1-sulfonate | `kegg.compound:C19675` (R)-form |
| Kujawinski 2023 | n-acetyl muramic acid | `kegg.compound:C02713` N-Acetylmuramate |
| Kujawinski 2023 | n-acetyl glutamic acid | `kegg.compound:C00624` N-Acetyl-L-glutamate |

That makes **11 paper names** in all that now read `dominant_form_assumed` (4 name matches + 7
aliases), so biller "Vitamin B5" and Kujawinski "pantothenic acid" agree again. biller
"Adenosyl Methionine", "Glucose 1 phosphate" and "Methionine Sulfoxide" keep their curated
`dominant_form_assumed`: their nodes name the L/D form, but ChEBI gives the rule no evidence for
it. Any golden that pins `stereo_assignment` on these compounds will move.

## 4. Closed with no graph change (FYI)

- **MEROPS `Gene_has_merops_family.qcov`**: already declared percent 0–100 (`9cf8516a`). The
  backlog entry was out of date.
- **Unnamed best-hit systems** (project 2 note):
  - 3.A.1.129.1 now re-anchors to 3.A.1.106.22 (CydDC), via `tcdb_moved.json`.
  - 1.A.77.3.21 is named "AtpI of Synechococcus sp." from its protein cell (42 genes).
  - 1.B.1.12.1 (0 genes) and 2.A.49.2.14 (1 gene) are not on TCDB's pages and keep the bare
    TCID. Their `display_name` now borrows the family name.
- **`metabolite_identity_report.json` `remap` empties on a rerun**: by design. It is a diff
  against the previous step-6 run, and the report's `baseline` string now says so. The
  release-to-release record stays `docs/kg-changes/metabolite-identity/metabolite_id_remap.tsv`.
- **Reciprocal best-hit check recall** (~2,990 gate-passing proteins fail it): moved into the
  3b design, not tuned now.

## For the explorer

**E1. Hand-off: ChEBI class substrates.** TCDB lists ChEBI *structural classes* as substrates
(alpha-amino acid → C00045 on 76 systems, peptide, lipid, fatty acid, nucleoside, …). They stay
`Metabolite` nodes with `structure_kind = 'generic'` by design: they are classes, not
placeholders, and they are not in the substrate target filter. A transport answer that lands on
one should say "a class of compounds", not a single molecule. This now applies to the
`[tcdb_best_hit]` substrate clause too ("substrates: alpha-amino acid"). Is a note in
`docs://analysis/transport` enough, or do you want a flag in tool output?

**E2. Question: surfacing `display_name`.** Do you want `display_name` in the TCDB rows of
`gene_ontology_terms` / `genes_by_ontology` / `ontology_term_details` / `search_ontology`, in
place of or next to `name`? We expect "next to", with `name = tcdb_id` still the unnamed test.

**E3. Absorb items once built** (we'll add a "KG built" section with live counts):
- add the `[tcdb_best_hit]` label wherever the explorer documents description-line labels;
- re-pin goldens that touch the 11 paper names in §3 or the `alternate_functional_descriptions`
  of genes with a direct best hit (`gene_details`, `genes_by_function` text matches can rank
  differently now that ~16K genes have extra text).

**E4. Anything we missed?** If you search genes by transport text today and these lines would
double-count or confuse a tool, tell us before the rebuild. The format is still easy to change.

## Responses

**Explorer, 2026-10-31.** Checked against explorer `main` @ `cf10a4f` (code + goldens; not yet
against a live graph).

**E1 — a doc note is enough for now.** `docs://analysis/transport` already has a
"Catch-all substrates" bullet (Peptide, Protein → "some substrate"); we will extend it to ChEBI
structural classes (alpha-amino acid, lipid, nucleoside, …) and the `[tcdb_best_hit]` clause.
Separately, `genes_by_metabolite` / `metabolites_by_gene` rows carry no `structure_kind` today,
so a caller cannot tell a class from a molecule without a second call. We will project
`metabolite_structure_kind` onto those rows on our side; no KG change needed.

**E2 — next to `name`, as you expect.** `name = tcdb_id` stays our unnamed test. Scope is wider
than the four ontology tools: `tcdb_family_name` on the `genes_by_metabolite` /
`metabolites_by_gene` TCDB rows is projected straight from `tf.name`, so unnamed systems show a
bare TCID there too. We will add `display_name` alongside on all of them.

**E3 — absorb list.**
- Drop the label-documentation item: the explorer never parses or documents the
  `alternate_functional_descriptions` `[label]` prefixes (pass-through in `gene_details` only).
- Goldens that will move on §3: `mfa_msystems_as_reported_only` pins C00021, C00170, C00624,
  C00864, C00127 (these rows should leave the `as_reported` slice); also check
  `mfa_msystems_top5` and `metabolites_by_gene_pmm0392_med4_transport`.
- On §1: `genes_by_function_*` goldens and `gene_details` baselines for genes with a direct best
  hit.

**E4 — four asks before the rebuild.**
1. **Searchable tokens.** Does `geneFullText` tokenize `tcdb_best_hit`, `substrates` and `TC`?
   If so, a search for "substrates" matches ~16K genes. We would prefer those not to be matchable
   words (or a format whose fixed words are unlikely queries).
2. **Ranking weight.** A 15-name substrate clause makes these lines heavy for broad words
   ("ammonia", "amino", "sugar") and can push gene-named hits down in `genes_by_function`.
   Could the cap be lower (e.g. 8)?
3. **Unnamed best-hit systems.** The line uses the system's `display_name`, so a best hit on an
   unnamed system reads "The ATP-binding Cassette … — system 3.A.1.x.y", which looks like a
   family-level call. Rare (11 systems with genes), but please state it in §1.
4. **Spec clarifications.** (a) §1: give the denominator — 16,039 genes with a line out of how
   many with a rank-1 hit? (b) Example 3 shows `AmtB (…)`: is the ellipsis in the stored line or
   an elision in the spec? It matters for goldens. (c) §3: give the edge count that changes for
   the 7 aliases (only the 4 name-match rows are counted).

On our side we will add a `genes_by_function` mistakes entry: a match on a `[tcdb_best_hit]`
line means "best TCDB hit (homology)", not "transports".

**KG, 2026-10-31.** All four E4 asks are taken; the change is built (see the next section).

- **E4.1 tokens.** Checked on the live graph: `standard-no-stop-words` keeps underscore words
  whole (`tigr_role_inferred` matches 20,843 genes; `tigr` and `inferred` match 0), but
  "substrates" and "TC" were plain words. The line is now
  `[tcdb_best_hit] <display_name> [<tcdb_id>] :: [tcdb_substrates] <names>`. After the rebuild
  "substrates" matches 1,209 genes and "tc" 2,257, the same as before the lines existed (from
  TCDB names and other text). `tcdb_best_hit` and `tcdb_substrates` are matchable tokens, but
  only as those exact words. The TCDB id is split by the analyzer ("3", "a", "1.4.4"); search for
  an id needs a quoted phrase, as on `tcdbFamilyFullText`.
- **E4.2 cap.** Lowered to 8 names, then "and N more" (59 lines are truncated).
- **E4.3 unnamed systems.** §2's borrowed name ("<family> — system <id>") would be used, but on
  the built graph **no line carries one**: none of the 11 unnamed systems that have genes is the
  target of a rank-1 `direct` best hit. If one appears in a later build, the text reads like a
  family-level name although the edge is system-level; the id in brackets is the system's.
- **E4.4 clarifications.**
  - (a) 16,423 lines out of 28,950 rank-1 best-hit edges (12,527 below the gate; 0 not kept).
  - (b) The "(…)" in the old example 3 was an elision in the spec; the stored line has the full
    name (example now quoted in full). **But** 2,224 stored lines do contain a literal "…": TCDB
    names that `tcdb_names.json` already holds truncated (e.g. "… the nitrogenous regulatory
    glycohydrolase enzyme, DraG…"). Pin goldens on the exact stored string.
  - (c) Assay edges that flip `as_reported → dominant_form_assumed`: **44** in all —
    biller 2022 (`10.1111/1462-2920.15834`) 20 (5 names × 4 edges: Homocystine,
    Methylthioadenosine, Adenosyl Homocysteine, Glutathione Disulfide, Vitamin B5);
    Kujawinski 2023 (`10.1128/msystems.01261-22`) 24 (table S2: 6 names × 2 edges; the
    cell-specific KEGG export: n-acetyl glutamic acid, 12). The other Kujawinski rows on these
    nodes report a KEGG id and stay `as_reported` by the §3 rule.
- **E1–E3:** agreed as written; nothing to add on the KG side.

## KG built (2026-10-31)

Graph built from KG `main` @ `ef72f299` (`Schema_info.git_dirty = false`); deployed at
`localhost:7687`. Import report empty. `pytest -m kg`: 1,431 passed, 4 skipped.
`/omics-edge-snapshot` and the annotation-state baseline: no change. Node and edge counts per
label/type are identical to the previous build (this release changes properties only).

| Item | Live |
|---|---|
| Genes with a `[tcdb_best_hit]` line | 16,423 (8,775 with `[tcdb_substrates]`) |
| Rank-1 best-hit edges / of them `direct` | 28,950 / 16,423 |
| `TcdbFamily.display_name` | dense on all 9,725 nodes; differs from `name` on 1,632 (1,248 subfamilies, 573 with genes; 384 systems, 11 with genes) |
| Assay edges `stereo_assignment` | `as_reported` 1,434 · `dominant_form_assumed` 232 (44 flipped, see E4.4c) |
| `alias_stereo_review` (identity report) | 3 entries: biller "Adenosyl Methionine" (C00019), Kujawinski "2,3-dihydroxypropane-1-sulfonate" (C19675), "n-acetyl muramic acid" (C02713) — explicit `dominant_form_assumed` where the rule alone says `as_reported` |
| Full-text spot checks (`geneFullText`) | "urea" 650 · "cyanate" 182 · "substrates" 1,209 · "tc" 2,257 |

MED4 urtA (PMM0970): `[tcdb_best_hit] The high-affinity (<1 μM) urea porter [3.A.1.4.4] :: [tcdb_substrates] Urea`.

## Explorer absorbed (2026-10-31)

Build `2026-10-31T12:27:06.047Z` absorbed on explorer branch `absorb-rebuild-2026-10-31-1227` (E3 done): 17 goldens, 4 pins, 6 example responses; every diff traced to §1–§3, no shape change beyond `display_name` in verbose TCDB `properties`. The E1 / E2 / E4 explorer work is backlog 2c.20–2c.23.

## Explorer correction to E2 (2026-10-31)

After discussion, the explorer shows `display_name` in place of `name` on TCDB rows (`term_name`,
`tcdb_family_name`, term-detail names) rather than adding a second name field. `name = tcdb_id`
remains the KG's unnamed test. Nothing is needed KG-side.
