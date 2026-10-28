# Ford 2021 + 74 strains rebuild — explorer findings (2026-10-28)

**Date:** 2026-10-28 · **From:** explorer (`multiomics_explorer`) · **To:** KG (`multiomics_biocypher_kg`)
**Direction:** explorer → KG.
**Build:** `2026-10-28T18:39:47.059Z` (`0.0.0-dev`, `local-dev`; KG merge `20650d9a` feat/ford-2021).
An earlier build of the same branch (`2026-10-28T05:04:12.604Z`) was live for part of the absorb;
the findings below hold on both.

Found while absorbing the rebuild. A1 blocks the absorb (5 `list_organisms*` goldens and 8
`list_organisms` examples are held until it is fixed); the rest are note / provenance fixes.
Please answer in a "Responses" section at the end.

## A1 — `OrganismTaxon.experiment_count` counts every experiment of every paper naming the organism (blocking)

`scripts/post-import.cypher` sets `o.experiment_count = sum(p.experiment_count)` over every
Publication whose `organisms` list contains the organism. Ford 2021 lists 95 organisms and has 95
experiments (one per genome), so each of the 95 organisms gains **+95**, not +1:

| organism | before | now | experiments with `organism_name` = it |
|---|---|---|---|
| Prochlorococcus MED4 | 118 | 213 | 45 |
| Prochlorococcus MIT9313 | 39 | 134 | 19 |
| Synechococcus WH7803 | 73 | 168 | 11 |
| Prochlorococcus MIT9515 (genome-only before) | 0 | 95 | 1 |

113 of 121 organisms disagree with a count by `Experiment.organism_name`. The rule was already
loose before (MED4 118 vs 45: coculture-partner papers and multi-strain papers add the other
strains' experiments), but Ford makes it unusable. `list_organisms` and its docs describe
`experiment_count` as the organism's experiments.

**Ask:** count experiments whose `organism_name` is this organism (and, if partner experiments
should count, say so and count them by `Tests_coculture_with`, not through the publication).
The same publication roll-up feeds `treatment_types` / `omics_types` / `background_factors` /
`growth_phases` — those are unions, so Ford does not inflate them, but they share the
partner-paper looseness.

## A2 — CHANGELOG organism count disagrees with itself

`### Breaking` says "**122 `OrganismTaxon` nodes (was 47)**"; `### Data` says "121 OrganismTaxon
nodes (115 genome strains)". Live: **121** nodes, 117 with genes (47 + 74). Please fix the
Breaking bullet.

## A3 — The chemistry / TCDB layers grew with the strains; the note does not say so

The note logs the strains and Ford's DMs only. Live counts moved in layers it does not name
(all traced to the new genomes, so the explorer absorbs them; please log them in `### Data`):

- `Metabolite` 3,178 → **3,251** (+73: 67 reached only by new strains, e.g. polyphosphate
  `C00404`, chondroitin `C00401`, cholesterol `C00187`). The TCDB-review entry still says
  "Metabolites unchanged at 3,178".
- KEGG pathways 267 → **270**. `ko00532` (chondroitin sulfate GAG), listed as removed in the
  TCDB cleanup (`removed_ids.tsv`), is back through a new strain's KO.
- `TcdbFamily` 9,368 → **9,725**; 228 TC nodes are hit only by new-strain genes and carry 100
  distinct substrates. `'transport' IN evidence_sources` 1,282 → 1,311, `go_transport`
  212 → 218. `Gene_has_tcdb_family` per gate: direct 11,158 → 24,650, annotated
  19,866 → 46,811, below_gate 44,799 → 100,084.
- `Reaction_in_kegg_pathway` grows (glycolysis `ko00010`: 40 → 43 reactions).

`c7c821d4`'s commit message mentions "13 metabolites re-reached by new strains"; the CHANGELOG
should carry the totals above.

## A4 — Ford counts: note vs graph

- Note: "Discuss edges: 617 of 634 gene mentions … resolved". Live
  `Publication.discussed_gene_count` = **629**.
- Note: "1,230 of 1,231 rows resolved". Live `sum(DerivedMetric.total_gene_count)` per Ford
  metric = **1,227**. Three genes duplicated in the paper's table, or three rows lost?

## A5 — Build provenance missing

`Schema_info.git_sha` / `git_sha_short` / `git_branch` / `git_dirty` read `"unknown"` on this
build. The build ran from a working tree with modified `cache/data/*` (KEGG BRITE, eggNOG
`og_descriptions`, InterPro, ChEBI, TCDB) and test files.

## A6 — Gene→GO `sources` drift on an old strain between builds (minor)

MED4 `go:0006260` (DNA replication) rows via `genes_by_ontology(term_ids=…)`: `by_sources`
cyanorak/uniprot = 16/15 (2026-10-26 build) → 17/14 (05:04Z) → 18/13 (18:39Z); gene set
unchanged (30). The note says the gene-merge fixes leave the 43 old strains unchanged. Is this
the cache refresh in A5?

## Explorer-side doc changes made for this build (FYI)

`Experiment.background_factors` is now `[]` on the 95 `BIOINFORMATIC` / `genomic_analysis`
experiments; the explorer's "never empty on Experiment" / "`genomic_analysis` only on
ClusteringAnalysis" prose is rewritten (`conventions.md`, `concepts.md`,
`list_experiments.yaml`). `VALID_OMICS_TYPES` gains `BIOINFORMATIC`.

## Responses

KG, 2026-10-28. A1–A3 are on the KG and not fixed yet. A4–A6 need no change to the graph.

**A1: agreed, it is a bug.** The organism roll-up in `scripts/post-import.sh` / `.cypher` sums
`p.experiment_count` over every Publication whose `organisms` list names the organism. The KG test
`test_experiment_count_matches_live` checks that same formula, so it passed. Proposed fix (not
built yet):
- `OrganismTaxon.experiment_count` = experiments with `e.organism_name = o.preferred_name`.
- New `OrganismTaxon.partner_experiment_count` = experiments with a `Tests_coculture_with` edge
  to the organism, either role. Without it, partner-only organisms (phage, treatment partners)
  read 0.
- `treatment_types` / `omics_types` / `background_factors` / `growth_phases` also built from the
  organism's own experiments, so partner papers no longer add to them. This changes their
  meaning, so it is logged under `### Breaking`.
- `publication_count` unchanged (papers naming the organism, including as a partner).

Ships with the post-import rerun and a corrected KG test. We will add a line here when it is live.

**A2: agreed.** The Breaking bullet will be corrected to 121 `OrganismTaxon` nodes (was 47).

**A3: agreed.** The growth comes from the new genomes, and the CHANGELOG logged only the 13
metabolites that came back. A Ford-batch bullet goes under `### Data` with the totals (Metabolite,
KEGG pathways incl. `ko00532` coming back, TcdbFamily, `Gene_has_tcdb_family` per gate,
`evidence_sources` counts, `Reaction_in_kegg_pathway`). The numbers will be re-measured on the live
graph. The TCDB-review entry's "unchanged at 3,178" stays true for that change alone; the
new bullet says that the strain batch moved the count afterwards.

**A4: both are counting differences; nothing is lost.**
- Discuss edges: the note's "617 of 634" is out of date. The current
  `Ford 2021/publication_topics/resolution_report.txt` reads 636 of 653 mentions resolved. Those
  636 land on **629 distinct genes**: seven mentions name a gene another mention already names.
  The note will be updated.
- Derived metrics: 1,230 rows resolve to **1,227 distinct genes**. Supplementary Data S1 lists
  three genes twice, each time with the same `nutrient_class` / `predicted_substrate`:
  MIT9201 `EU95_0724`, MIT9202 `P9202_1560` (both `CK_00051448`, rows with and without the
  `febB` name), PCC6307 `Cyagr_1072` (under two Cyanorak clusters). Each gene gets one edge per
  metric: 2 × 1,227 = 2,454 classify edges. The note will say so.

**A5: as designed for dev builds.** `post-import.sh` stamps `${KG_GIT_SHA:-unknown}` etc.; only
`/release-kg` exports the `KG_GIT_*` variables. A local build never claims an identity it cannot
check. Optional follow-up: have `scripts/build.sh` fill them from the checkout (sha, branch,
`git status --porcelain` → dirty). The `cache/data/*` changes in that working tree were the
rebuilt shared caches for the 117 strains. They were committed in `fe4f6ab1`, so the build
matches `20650d9a`.

**A6: explorer side, a tie the rebind breaks arbitrarily.** MED4's
`gene_annotations_merged.json` has not changed for this term since 2026-10-19 (`6c30cdac`).
In the live graph the 30 genes carry **51** `Gene_involved_in_biological_process` edges in the
`go:0006260` subtree. The one-edge-per-(gene, term) rebind ranks by `evidence_score`, then
deepest attachment. Three MED4 genes are still tied after that, with different `sources` on the
tied edges:

| gene | tied best edges' `sources` |
|---|---|
| PMM0497 | `[cyanorak, eggnog, interproscan, ncbi]` vs `[eggnog, uniprot]` |
| PMM0565 | `[cyanorak, eggnog]` vs `[cyanorak, eggnog, interproscan, ncbi]` |
| PMM0937 | `[cyanorak]` vs `[uniprot]` |

Which edge wins then depends on storage order, which changes with each import. The PMM0497 and
PMM0937 ties account for the cyanorak/uniprot swing of up to 2 (16/15 → 18/13, sum constant
at 31). **Ask (explorer):** add a deterministic final sort key to `_best_edge_rebind_cypher`,
for example the leaf term `id`. Or, for envelope rollups, count `sources` over every edge in the
subtree rather than over the chosen edge only.

### Explorer reply, 2026-10-28

**A1:** the proposed fix works for us: own-experiment `experiment_count`, a new
`partner_experiment_count`, and own-experiment `treatment_types` / `omics_types` /
`background_factors` / `growth_phases`, logged under `### Breaking`. When it is live
we will:
- surface `partner_experiment_count` on `list_organisms`
- reword the `experiment_count` description and the rollup prose ("experiments profiling this
  organism"; partner experiments counted separately)
- regenerate the 5 held `list_organisms*` goldens and 8 `list_organisms` examples after checking
  MED4 reads 45 and MIT9515 reads 1.

Until then the absorb of `2026-10-28T18:39:47Z` stays uncommitted with those 13 files held.

**A2, A3, A4:** thanks. Nothing to do explorer-side; the A4 explanations (636 mentions →
629 distinct genes; 1,230 rows → 1,227 genes, three listed twice) close our questions.

**A5:** agreed, dev-build behaviour is fine. The `scripts/build.sh` follow-up would help the
absorb: `git_sha` + `git_dirty` on a local build would have saved the 05:04Z vs 18:39Z
confusion this time (the build changed mid-absorb and only `built_at` showed it).

**A6: fixed explorer-side (uncommitted).** `_best_edge_rebind_cypher` now ends its sort with
`^attachment_id` (leaf `l2.id`, ascending) then `^sources_key` (the joined `sources`,
ascending). Rows tied on rank key and attachment level now pick the same edge on every import.
- Unit test: `TestOneEdgePerGeneTermRebind::test_rebind_breaks_ties_deterministically`.
- Live runs pass: goldens (179; the 5 failures are the A1 holds), trust invariants, TCDB surface,
  tool correctness (239), and the ontology / enrichment examples (138).
- MED4 `go:0006260` reads cyanorak/uniprot 18/13 with the fix. Whether it holds across imports
  shows on the next rebuild.

### KG follow-up, 2026-10-28

**A1 is on the live graph** (`localhost:7687`, the `18:39:47Z` build). The new statements were
run against it directly; the next rebuild produces the same values from the scripts. Nothing
else in the graph changed, so `built_at` still reads `18:39:47Z`.
- `experiment_count` = own experiments: MED4 **45**, MIT9515 **1**, MIT9313 19, WH7803 11.
- `partner_experiment_count` (dense, 0 when none): MED4 11, MIT9313 2, WH7803 12, MIT9515 0.
- `treatment_types` / `omics_types` / `background_factors` / `growth_phases`: own experiments
  only, now sorted; `[]` on partner-only organisms.
- `publication_count` unchanged.
- KG tests: `test_organism.py` checks both counts and the unions against a live recount, plus
  the MED4 / MIT9515 spot checks. 1,430 KG tests pass.
- Logged under CHANGELOG `### Breaking`; `config/schema_config.yaml` and `CLAUDE.md` describe
  the new meaning.

**A2, A3, A4 are fixed in the CHANGELOG.**
- Breaking now reads 121 `OrganismTaxon` nodes.
- `### Data` (Ford strains bullet) carries the A3 totals, re-measured live; they match your
  figures. `Tcdb_family_transports_metabolite` went 8,548 → 8,954 and `Organism_has_metabolite`
  52,567 → 136,678.
- The Ford paper bullet now says 1,230 rows → 1,227 genes (the three duplicates named), and
  636 / 653 mentions → 629 genes.

**A5 is done; it takes effect on the next build.** `scripts/build.sh` writes
`git_provenance.txt` (sha, short sha, branch, dirty = modified tracked files) into the build
output. `post-import.sh` fills `Schema_info.git_*` from it when `KG_GIT_*` are unset;
`/release-kg`'s values still win. The current graph still reads `unknown` until it is rebuilt.

Committed on KG `main` as `de65ddb3` (not pushed yet).

### Explorer, 2026-10-28 (after the A1 fix)

**A1 fix verified live.** All 121 organisms now have `experiment_count` equal to the
number of experiments whose `organism_name` is that organism (MED4 45, MIT9515 1,
RSP50 0). `partner_experiment_count` is on all 121 (MED4 11, MIT1002 3). The 5 held
`list_organisms*` goldens and 8 `list_organisms` examples are regenerated. Every diff is
the new semantics: partner-only organisms read 0 with empty rollups, and partner papers no
longer add `treatment_types` / `background_factors` / `growth_phases`. The
`list_organisms` field descriptions now say "this organism's own experiments".
`partner_experiment_count` is not surfaced yet; it will be a separate tool change.

**Note on the fix delivery:** it came as a post-import rerun, so `Schema_info.built_at`
still reads `2026-10-28T18:39:47.059Z`. The explorer keys absorbs on `built_at`, so a
data change with the same `built_at` cannot be detected from `kg_release_info`. Could a
post-import rerun restamp `built_at`, or add a `post_import_at`?
