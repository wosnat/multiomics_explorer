# TCDB substrate-depth migration — genes_by_metabolite, metabolites_by_gene (+3 discovery extensions) (Mode B)

**Date:** 2026-08-20 · **Mode:** B (5 tools) · **Status:** FROZEN 2026-08-26 (v3: v2 + KG review `docs/kg-specs/2026-08-26-review-tcdb-substrate-depth-migration.md` §1–§4 applied; live-verified; no new filters)
**Driver:** Slice 2 of the synced-release program. The 2026-08 KG TCDB two-source upgrade replaced the substrate-trust signal: node-level `level_kind = 'tc_specificity'` (the explorer's `transport_confidence` derivation) now matches only 466 of 11,263 substrate edges; edge-level `substrate_depth` and gene-level `transport_substrate_resolution` are the contract (`multiomics_biocypher_kg/docs/kg-changes/tcdb-two-source-upgrade.md` §7). **Acceptance: the 8 slice-1 xfails go green** (2 integration + 6 regression cases in `XFAIL_CASES`).

## Design decisions (user-reviewed 2026-08-20)

1. **The explorer-invented `substrate_confirmed`/`family_inferred` per-row vocabulary dies**; the KG's own terms are surfaced under their own names. Live-verified rationale: nitrite via `2.A.16` (formate-nitrite family) is `most_specific` at a *family* node — the most specific *surviving* node for that substrate in the gene-pruned hierarchy (not a curation claim: only `tc_specificity` nodes own curated substrate classes; depth is what the KG materialised), yet the old rule called it family_inferred; conversely 49 MED4 `resolved` genes reach nitrite only via inherited `3.A.1` edges — per-row and per-gene trust are different facts.
2. **No new categorical "call confidence" field.** Call confidence already exists as the KG's 5-signal composite `evidence_score` (edge, [0,1]) / `Gene.tcdb_evidence_score_max` (gene, sparse). Per the KG contract §2: rank with it, expose it, never hard-filter by default. The `'tcdb' ∈ annotation_types` tier gate remains the KG's binary quality bucket; docs say "the score is the graded version of the same evidence."
3. **Fewer fields.** Every TCDB fact appears once, at the level it belongs to: gene-level facts on `gene_overview` (and in drill-down *envelopes*), row-level facts on drill-down rows.
4. **Deepest-attachment predicate applied on every transport-arm traversal (KG review §1, option a).** The KG computes every transport count it exposes over a gene's *deepest* TCDB attachments only — an attachment to `t` is superseded when the same gene is also attached to a descendant of `t`:
   ```cypher
   MATCH (g:Gene)-[gt:Gene_has_tcdb_family]->(tf:TcdbFamily)
   WHERE NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family]->(d:TcdbFamily)
                      WHERE (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(tf) }
   ```
   The explorer's transport-arm rows and its traversal-computed `evidence_sources` / `has_chemistry` adopt the identical predicate, so rows and count columns are projections of one (gene, metabolite) set — the KG's stated design. Live-verified 2026-08-26: PMM0392 all-edges → 554 distinct metabolites in `metabolites_by_gene` rows vs `gene_overview` 13; deepest-only → 13 = 13. Nitrite × MED4: 68 rows / 63 genes → 29 rows / 27 genes (39 superseded rows, all `inherited` via `3.A.1`). Nitrite cross-organism deepest genes 2,318 = `Metabolite.transporter_gene_count`. Superseded rows are exactly the superfamily rollup the KG's counts were redesigned to exclude; no row field is added for them (option b rejected — fewer fields; family membership incl. ancestors remains visible via `gene_ontology_terms(ontology='tcdb')`). The `*1..4` exists-check is bounded (TCDB is 5 levels) and ran sub-second on every verification query.
5. **`resolved` means "at least one non-lumping deepest attachment," not "all"** (KG review §3). A gene deepest-attached at both `2.A.16` and `3.A.1` is `resolved` and still carries `3.A.1`'s rollup inside `transported_metabolite_count`; per-row `substrate_depth` separates the `2.A.16` row from the `3.A.1` rows. The MBG warning and the `metabolites.md` trust-ladder text carry this one-sentence caveat.

## The resulting TCDB surface (what a consumer reads)

**Gene level** (`gene_overview` row):

| Field | Answers | Note |
|---|---|---|
| `tcdb_evidence_score_max` (float \| null) | any TCDB call, and how corroborated | **null = no TCDB call** (sparse KG property, surfaced as null — never coalesced to a sentinel). Replaces `transporter_count`. |
| `transported_metabolite_count` (int) | substrate breadth (deepest-attachment) | new; pairs with `catalyzed_metabolite_count` |
| `transport_substrate_resolution` (`resolved` \| `family_inferred` \| null) | is the breadth meaningful | new; `family_inferred` = reachability, not capability; null when no TCDB call |

`'transport' ∈ evidence_sources` keeps carrying cross-arm presence for routing. **BKM: read the score; if `resolved`, drill into substrates.**

**Row level** (`genes_by_metabolite` / `metabolites_by_gene` transport rows; all null on metabolism rows):

| Field | Old | Note |
|---|---|---|
| `substrate_depth` (`most_specific` \| `inherited`) | replaces `transport_confidence` | straight from the edge. Field description: "the most specific *surviving* transporter node for this substrate, relative to the gene-pruned hierarchy — not a curation level" |
| `tcdb_evidence_score` (float) | new | edge composite for the gene×family pair; rows rank by it within a depth tier |
| `tcdb_level_kind` | kept | ontology convention (`level_kind` on every ontology surface); no longer drives any derivation |
| `tcdb_family_id` / `tcdb_family_name` / `tc_class_id` | kept | unchanged |

Gene-level `transport_substrate_resolution` is **not** repeated per row; it lives in the envelopes that already aggregate per gene — `metabolites_by_gene.by_gene[]` and `genes_by_metabolite.top_genes[]` — and drives the gene-anchored auto-warning.

## Change summary

### genes_by_metabolite + metabolites_by_gene (core; GBM is the template, MBG mirrors)

| Surface | Old | New |
|---|---|---|
| Per-row | `transport_confidence` | `substrate_depth`; + `tcdb_evidence_score` (edge `gt.evidence_score`) |
| Filter param | `transport_confidence: list[...]` | `substrate_depth: list['most_specific'\|'inherited']` — `r.substrate_depth IN $...` on the transport arm only (per-arm scope unchanged). Unknown values raise ValueError listing valid ones; the two old value strings get a rename pointer in the message. **No score filter param** (contract §2) — the score is for ranking/reading. |
| Envelope counters | `transport_substrate_confirmed_rows` / `transport_family_inferred_rows` | `transport_most_specific_rows` / `transport_inherited_rows` |
| Envelope rollup | `by_transport_confidence` (models `{Gbm,Mbg}ByTransportConfidence`, key `transport_confidence`) | `by_substrate_depth` (models `{Gbm,Mbg}BySubstrateDepth`, key `substrate_depth`) |
| Envelope per-gene | `top_genes[]` (GBM), `by_gene[]` (MBG) | each entry gains `transport_substrate_resolution` + `tcdb_evidence_score_max` (raw gene props — null only when the gene has no TCDB call at all, independent of which rows it contributes here; *post-freeze wording clarification from the golden diff-review*) |
| Detail sort | metabolism → substrate_confirmed → family_inferred | metabolism → `most_specific` → `inherited`; within a transport tier, `tcdb_evidence_score` desc, then existing tiebreakers (api `transport_confidence_priority` → `substrate_depth_priority`; Cypher ORDER BY gains the score) |
| Auto-warning, GBM (metabolite-anchored) | fires when family_inferred dominates transport rows | same threshold mechanics keyed on `inherited` dominance, now computed over deepest-attachment rows only (superseded rows no longer inflate it — nitrite × MED4: 23 inherited of 29 rows, not 62 of 68); message names `substrate_depth=['most_specific']` as the narrowing filter |
| Auto-warning, MBG (gene-anchored) | derived per-gene family_inferred share | reads the gene's `transport_substrate_resolution = 'family_inferred'` (KG-authoritative; the 9 ABC-only MED4 genes carry it). Message: "substrate breadth is reachability, not capability for these genes" |
| Envelope map projections | `top_tcdb_families` derives substrate_confirmed from collected `level_kind` | derives from collected `substrate_depth` (carry `r.substrate_depth` through the row maps) |
| queries_lib sites | filter conditions L6954/6956 + L7498/7500; CASE derivations L7119/7135/7220 + L7685/7701/7797; map projections L7246/7318–7323 + L7824/7897–7902 | all re-keyed to `r.substrate_depth`; `gt.evidence_score AS tcdb_evidence_score` and `g.transport_substrate_resolution` / `g.tcdb_evidence_score_max` projected where listed. **Every transport-arm `MATCH (g)-[gt:Gene_has_tcdb_family]->(tf)` (detail, summary/count, envelope map projections, in both tools) gains the decision-4 `NOT EXISTS` predicate**; so does the `gene_overview` `evidence_sources` / `has_chemistry` traversal (queries_lib ~L485/558/566). Grep acceptance: no `level_kind = 'tc_specificity'` predicate remains (bare `tf.level_kind AS tcdb_level_kind` projections stay). |

### Discovery-tool extensions

| Tool | Change | Source |
|---|---|---|
| `gene_overview` | **remove** row `transporter_count` (aliased `g.tcdb_family_count`). Deliberate (KG review §4 considered): it counts *all* attachments incl. superseded ancestors (PMM0392: 8 edges, 7 deepest) — the wrong multiplicity under decision 4. If call multiplicity is wanted later it should be a KG-precomputed deepest-attachment count (future ask), not this column. | — |
| `gene_overview` | add `tcdb_evidence_score_max` (float \| null, no coalesce) | `g.tcdb_evidence_score_max` |
| `gene_overview` | add `transported_metabolite_count` (int, coalesce 0) | `g.transported_metabolite_count` |
| `gene_overview` | add `transport_substrate_resolution` (str \| null) | `g.transport_substrate_resolution` |
| `list_metabolites` | add row `transporter_gene_count` (int, coalesce 0) | `m.transporter_gene_count` — closes the trap loop: `catalyst_gene_count=0, transporter_gene_count>0` = transport-only |
| `list_organisms` | add row `transported_metabolite_count` (int, coalesce 0); `by_metabolic_capability[]` entries gain it as a column (ranking stays `catalyzed_metabolite_count`) | `o.transported_metabolite_count` |

`has_chemistry` / `evidence_sources` (traversal-computed) unchanged. No new params on the discovery tools; no result-size-control changes; `EXPECTED_TOOLS`/`TOOL_BUILDERS` unchanged.

### §8 checklist audit — closed (recorded, no further code)

`gt.tier`, `source_agreement`, `pfam_support`/`go_support`, edge `confidence_score`: not surfaced (score *components* remain `run_cypher`-only; the composite is what this slice exposes — a components drill-down is a later ask if a consumer needs explainability). `evidence_sources` / `genes_by_ontology(ontology='tcdb')` deliberately use edge-presence (recall) semantics — correct for ORA (consistent numerator/denominator) and documented as such; one-line note in `references/analysis/enrichment.md` ("TCDB in ORA": don't pre-filter membership by `annotation_types`/score; interpret enriched families via `most_specific` substrates).

## Verified against live KG

- 2026-08-20: `substrate_depth` non-null on all 11,263 substrate edges. Migrated detail query (urea × MED4): urtABCDE (PMM0970–0974) rank first as `most_specific`+`resolved` on `3.A.1.4.4`/`3.A.1.4.5`; ABC `3.A.1` `inherited` rows follow. Nitrite × MED4: `2.A.16` surfaces as `most_specific` at a family node; 57 genes reach nitrite via inherited `3.A.1`. Gene fields live: resolution on 30,076 genes (28,405/1,671); PMM0392 `resolved`, `transported_metabolite_count=13`; glucose `transporter_gene_count=3051`, `catalyst_gene_count=0`.
- 2026-08-26 (KG review §1 reproduced): deepest-attachment predicate — PMM0392 deepest families `3.A.1.{25,28,29,30,31,32,33}` → 13 distinct metabolites = `transported_metabolite_count`; superseded `3.A.1` → 554. Nitrite × MED4: 29 deepest rows (6 most_specific / 23 inherited), 27 genes; 39 superseded rows. Nitrite all-organism deepest genes 2,318 = `transporter_gene_count`. All predicate queries sub-second.
- 2026-08-19 (§7 of the presync asks doc): `Gene_has_tcdb_family.evidence_score` present on all 53,763 edges, float [0,1]; `Gene.tcdb_evidence_score_max` sparse (KG contract §8, schema baseline).
- 2026-08-20 (post-reconnect), migrated row query verified end-to-end: `gt.evidence_score` projects on all 68 urea × MED4 transport rows (10 `most_specific` + 58 `inherited`); ordering depth-tier → score desc yields urtBCDE (0.8) → urtA PMM0970 (0.6) → inherited `3.A.1` rows by score (0.8 … 0, tier-3 uncorroborated edges reach 0). `tcdb_evidence_score_max`: PMM0001 → null (no TCDB call; `transported_metabolite_count` 0, resolution null) vs PMM0392 → 0.8 / 13 / `resolved` — the null-means-no-call contract holds.

## Tests & docs

- The 8 xfails are the acceptance list: test-updater re-pins the 2 integration tests to the new names/semantics and removes the xfail marks; removes the 6 ids from `XFAIL_CASES`; regen those 6 goldens (`--force-regen -k genes_by_metabolite`) + diff-review. `gene_overview` goldens regen (column removal + 3 additions); `list_metabolites`/`list_organisms` goldens regen (1 column each).
- Unit assertions for renamed/new params, fields, envelopes across the 3 test files; edge-case scenarios for GBM/MBG/gene_overview updated where they name changed fields.
- Docs: GBM/MBG YAML (examples, mistakes, chaining — rewrite around the two axes + score ranking), discovery-tool YAML additions, regen + lint; CLAUDE.md rows; CHANGELOG: Breaking (param rename, row/envelope renames, `gene_overview.transporter_count` removed) + Added (new fields); `references/analysis/enrichment.md` "TCDB in ORA" note; `references/analysis/metabolites.md` trust-ladder paragraph.
- KG dialog: append to `docs/kg-specs/2026-08-19-presync-kg-asks.md` §9 the scraped-name truncation (`TcdbFamily 3.A.1.4.4` name = `"The high-affinity ("` — citation-stripper cut at an open paren; cosmetic scrape fix).

## Acceptance

1. Full suite green with **zero xfails** (the 8 markers removed, tests pass on new semantics).
2. No `level_kind = 'tc_specificity'` predicate in queries_lib.py; the `substrate_depth=` filter narrows live (urea × MED4 under the deepest-attachment predicate: `['most_specific']` → the 10 urtABCDE rows; unfiltered adds only the non-superseded inherited rows — re-pin exact count at Stage 3); transport rows within a depth tier order by `tcdb_evidence_score` desc.
3. Old param value strings raise with a rename pointer; old field/envelope names and `gene_overview.transporter_count` absent from rows, envelopes, docs.
4. `gene_overview`: PMM0392 → `tcdb_evidence_score_max=0.8`, `transported_metabolite_count=13`, `transport_substrate_resolution='resolved'`; PMM0001 → null/0/null. `list_metabolites`: glucose `transporter_gene_count>0`. `list_organisms`: MED4 `transported_metabolite_count>0`.
5. **Cross-tool agreement by construction** (KG review §1): distinct metabolites in `metabolites_by_gene(['PMM0392'])` transport rows == `gene_overview.transported_metabolite_count` (13); distinct genes in `genes_by_metabolite(nitrite, MED4)` transport rows == 27 and, summed across all organisms, == `list_metabolites` `transporter_gene_count` for nitrite (2,318). Encoded as integration tests.
