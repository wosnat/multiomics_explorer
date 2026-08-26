# KG-side asks: pre-sync cleanup — before the 0.1.0-alpha.7 cut

**Date:** 2026-08-19
**Driver:** Synced-release reconciliation of the 2026-08-18 KG build (InterPro two-layer, NCBIfam, MEROPS, TCDB two-source upgrade, vocabulary contract, Lu 2026). Explorer-side work is sequenced as: (0) this cleanup, (1) test-baseline catch-up, (2) TCDB-related migrations, (3) new-ontology registration, (4) light surface.
**Premise:** None of the audited changes are released yet (`Schema_info.version = 0.0.0-dev`; last tag `kg-0.1.0-alpha.6`). This is the one window where renames are free — after the cut, every one of these becomes a breaking change with migration cost. The audit question applied to every Breaking-list item was: *does anything keep its name while changing meaning, or break a graph-wide convention?*
**Status:** DONE 2026-08-19 — 001/002/004 accepted (002 on corrected rationale, §6), 003 withdrawn by the explorer (§7). **Batch LANDED and verified live (§8)**; explorer slice 1 unblocked.

---

## 1. Why this doc

The 2026-08 KG batch is large and self-aware about loud-vs-silent breakage (the `tcdb_evidence_score` → `evidence_score` rename exists precisely to make a retype loud). Three spots don't yet meet that same bar. Fixing them **before** the alpha.7 cut means the explorer migrates once, goldens regenerate once, and no released consumer ever sees a property keep its name while changing meaning.

---

## 2. Ask summary table

| ID | Category | Pri | Surfaced from | Explorer consumer |
|---|---|---|---|---|
| KG-SYNC-001 | Rename (silent redefinition) | P1 | TCDB §7.3 metabolite-count arm split | `gene_overview`, `list_organisms`, `list_metabolites` per-row counts + descriptions |
| KG-SYNC-002 | Id-form convention | P1 | NCBIfam ontology integration | Slice-3 `ONTOLOGY_CONFIG` registration (all 5 ontology tools do prefix handling) |
| KG-SYNC-003 | Score naming (house rule R4) | P2 | MEROPS integration | Slice-3 `merops` edge-prop surfacing |
| KG-SYNC-004 | Doc hygiene | P3 | Doc sweep cross-check | Anyone reading `docs/kg-changes/` as the contract |

---

## 3. Per-ask detail

### KG-SYNC-001 — Rename the narrowed chemistry counts so no property keeps its name with changed meaning (P1)

**Ask:** Complete the §7.3 arm split with renames on the catalysis arm:

| Node | Today (post-split) | Asked |
|---|---|---|
| `Gene` | `metabolite_count` (catalysis-only; was union) | `catalyzed_metabolite_count` |
| `OrganismTaxon` | `metabolite_count` (metabolism arm; was union) | `catalyzed_metabolite_count` |
| `Metabolite` | `gene_count` (catalysis-only; was union) | `catalyst_gene_count` |

The transport arm is already well-named (`transported_metabolite_count`, `transporter_gene_count`) — this ask makes the catalysis arm equally explicit and retires the bare names on these three nodes entirely.

**Why:**
- The split narrowed each count's meaning while keeping its name. A stale reader (old explorer version, user notebook, cached Cypher) silently gets the narrowed number — for `Gene.metabolite_count` that's 23,137 transport-only genes silently dropping to 0. Renaming makes every stale reader fail loudly (null), which is the standard this same batch set with `tcdb_evidence_score` → `evidence_score` and `tcdb_best_evidence_score` → `tcdb_evidence_score_max`.
- `catalyzed_*` also ends the graph-wide overloading of "metabolite_count": `Publication.metabolite_count` / `Experiment.metabolite_count` / `OrganismTaxon.measured_metabolite_count` mean *measured* (metabolomics), a different concept that keeps its names untouched.
- Scope note: the ontology-node convention `<AnnotationNode>.gene_count` = "genes annotated to me" (`TcdbFamily`, `InterproEntry`, `MeropsFamily`, …) is **not** part of this ask. Those nodes have one gene-link arm, so the bare name is unambiguous. `Metabolite` has two gene-link arms (catalysis via `Reaction`, transport via `TcdbFamily`) — where two arms exist, each count should name its arm.
- Deliberately **no** union-count replacement (see §5, N2).

**Verified state (2026-08-19):** live `Gene` keys include both `metabolite_count` and `transported_metabolite_count`; `Metabolite` keys include `gene_count`, `transporter_gene_count`, `transporter_count`; `OrganismTaxon` keys include `metabolite_count`, `transported_metabolite_count`, `measured_metabolite_count`.

**Acceptance criteria:** the three renamed properties exist with the old ones absent (not aliased); post-import scripts, `Schema_info`-adjacent docs, and the CHANGELOG Breaking bullet updated to the new names; `docs/kg-changes/tcdb-two-source-upgrade.md` §7.3 table updated.

---

### KG-SYNC-002 — `NcbifamFamily` ids in CURIE form (P1)

**Ask:** `ncbifam_TIGR01234` / `ncbifam_NF000282` → `ncbifam:TIGR01234` / `ncbifam:NF000282`.

**Why:** Every peer ontology in the graph uses colon-CURIE ids — verified live: `merops.family:A01`, `interpro:IPR000014`, `tcdb:1.A.1`, `pfam:PF00004`. NCBIfam is the lone underscore-form outlier. ~~The original draft claimed `ncbifam` is bioregistry-listed — that was **wrong** (see §6: not in bioregistry, identifiers.org, or Biolink; only `tigrfam` is registered, and its `^TIGR\d+$` pattern cannot hold the majority-`NF\d+` accessions).~~ The surviving rationale: internal consistency for consumers outweighs registry purity, as a documented house-minted prefix. Explorer-side, all five ontology tools plus enrichment do prefix construction/stripping against `ONTOLOGY_CONFIG`; a single divergent id grammar is a permanent special case in every one of them, and id churn after release is the most expensive kind of break (every cross-reference dies silently).

**Verified state (2026-08-19):** `MATCH (n:NcbifamFamily) RETURN n.id LIMIT 3` → `ncbifam_NF000282`, `ncbifam_NF000311`, `ncbifam_NF000355`.

**Acceptance criteria:** node ids, `Ncbifam_family_in_interpro_entry` endpoints, `Gene_has_ncbifam_family` endpoints, and `ncbifam_reference.json` keys all in colon form; scalar + full-text indexes intact; changelog Added bullet updated.

---

### KG-SYNC-003 — `Gene_has_merops_family.confidence_score` → `evidence_score` (P2)

**Ask:** Rename the edge property; keep the value semantics.

**Why:** House rule R4 in the vocabulary contract — "one score name per concept, on one `[0,1]` float scale" — was this batch's own invention, and MEROPS (landed in the same batch) violates it: the gene→family call-strength score is `evidence_score` on `Gene_has_tcdb_family` and all six gene→ontology edges, but `confidence_score` on `Gene_has_merops_family`. Same concept (strength of a gene→annotation-node call), same scale — verified live range [0.0081, 0.729]. Slice-3 exposes MEROPS through the same generic ontology tools as TCDB; one score name means the `edge_props` machinery and its field descriptions stay uniform.

**Verified state (2026-08-19):** `MATCH ()-[r:Gene_has_merops_family]->() RETURN min(r.confidence_score), max(r.confidence_score), count(r)` → 0.0081 / 0.729 / 4,257.

**Acceptance criteria:** property renamed on all ~4.2K edges; the 10 MEROPS entries in `config/controlled_vocabularies.yaml` updated where they reference the name; `merops-extension.md` updated.

---

### KG-SYNC-004 — Stale references to deleted `is_promiscuous` in kg-changes docs (P3)

**Ask:** `interproscan-extension.md` still documents `InterproEntry.is_promiscuous` as live and `interproEntryFullText` as name-only (it carries a SUPERSEDED banner, but the specific claims are the ones a reader will trip on); `tcdb-two-source-upgrade.md` §7.4 still explains `family_inferred` in terms of `is_promiscuous`. Both properties are deleted per the vocabulary contract. A one-line correction in each (or pointing §7.4 at the `level >= 2 AND metabolite_count >= 50` predicate) keeps the contract docs self-consistent.

---

## 4. Ripple note for the KG side

KG-SYNC-001/003 rename properties that appear in the batch's own CHANGELOG Breaking/Added bullets and kg-changes docs — those texts should be updated in the same commit so the alpha.7 release notes are born correct. KG-SYNC-002 touches committed reference JSON (`ncbifam_reference.json`) and any test snapshot pinning ncbifam ids.

---

## 5. Audited and accepted as-is (explicit non-asks)

- **N1 — `Metabolite.transporter_count` keeps its name** despite the definition change: the old value (0 for 83% of transported metabolites) was a bug relative to what the name always claimed; the new definition is the fix, not a pivot.
- **N2 — No union metabolite count.** "Add the two arms" double-counts metabolites both catalyzed and transported by the same gene, but the overlap is small (sampled 93 both-arm genes: 38 overlapping of 2,859 arm-entries, ~1.3%). The explorer will surface the two arms as separate fields rather than sum them; no precomputed union wanted (YAGNI).
- **N3 — `evidence_score` retype (int 0–3 → float [0,1]) on the six gene→ontology edges without rename.** Those properties never shipped in a tagged release (alpha.6 predates the InterPro two-layer work) and the explorer has zero consumers; within-window retype, no hazard. Verified live: floats with `sources`/`evidence` present.
- **N4 — `substrate_depth` values (`most_specific`/`inherited`) and `Gene.transport_substrate_resolution` (`resolved`/`family_inferred`)** are well-named. The explorer's `transport_confidence` vocabulary (`substrate_confirmed`) will be **aligned to the KG's terms in slice 2** — explorer-side change, not a KG ask.
- **N5 — R5 (no native bool)** binds adapter-emitted (BioCypher-routed) properties only; post-import bools (`Assay_flags_metabolite.flag_value`, DM flag edges) round-trip fine and are out of scope. No inconsistency.
- **N6 — `Gene_has_ncbifam_family` keeping both `evalue` and `score`** while `Gene_has_interpro_entry` drops `score`: justified — single homogeneous HMMER scale vs incomparable cross-library scales.
- **N7 — Sparse `Gene.tcdb_evidence_score_max`** (no zero-fill): accepted; explorer will use `coalesce(…, -1.0)` per §8 checklist.
- **N8 — `annotation_state` tightening and the 9-bucket `annotation_quality`:** accepted; explorer baselines and the `[AQ]` docs regenerate in slice 1.
- **N9 — Lu 2026 DOI-derived id churn** (preprint → AEM paper, old ids resolve to empty): accepted — ids-from-DOI working as designed; fixtures regenerate in slice 1.

---

## 6. KG-side response (2026-08-19) — dialog open, nothing implemented yet

Verified each ask against the KG repo (`multiomics_biocypher_kg`) and the live registries before acting. Per-ask verdicts below; **KG-SYNC-003 needs an explorer answer before the batch lands**, since all four will ship in one rebuild.

### KG-SYNC-001 — ACCEPTED as asked

Rationale confirmed against the repo: the three renames land in `scripts/post-import.cypher` + `post-import.sh` (Gene ~L1200, Metabolite ~L1362, OrganismTaxon ~L1459), CLAUDE.md key facts, the CHANGELOG Breaking bullets, `tcdb-two-source-upgrade.md` §7.3, kg-validity tests, and a `snapshot_data.json` regeneration. Scope boundaries as stated (measured-arm `metabolite_count`s and ontology-node `gene_count` untouched) are agreed.

### KG-SYNC-002 — ACCEPTED, but on a corrected rationale (house-minted prefix, not registry-backed)

The stated justification is factually wrong and should not survive into any doc: **`ncbifam` is not in bioregistry** — verified live 2026-08-19 against the bioregistry API (`Prefix not found: ncbifam`, search returns nothing), identifiers.org (no namespace), and the Biolink model prefix map (no NCBIfam entry). The only registered relative is `tigrfam` (Biolink `TIGRFAM`), pattern `^TIGR\d+$` — structurally unable to hold the `NF\d+` accessions that are the majority of our nodes (2,753 NF vs 2,204 TIGR). The original underscore decision followed the KG's actual convention correctly (registered → colon: `tcdb`, `interpro`, `pfam`, `merops.family`, `merops.clan` all verified registered; unregistered → underscore: `psortb_`, `signalp_`).

The ask's *fallback* argument — uniform id grammar for consumers outweighs registry purity — stands on its own, so the KG will:
- emit `ncbifam:TIGR01234` / `ncbifam:NF000282` as a **documented house-minted prefix** (hardcoded in `_ncbifam_node_id`, bypassing `normalize_curie`, which would reject the unknown prefix);
- file an upstream **Bioregistry new-prefix request** for `ncbifam` (real, active NCBI resource; InterProScan's member-DB name) so the graph becomes retroactively registry-correct;
- keep the underscore convention for the flat structural vocabularies (`psortb_`, `signalp_`) — they are not in the explorer's `ONTOLOGY_CONFIG` and are not cross-referenced ontologies.

One acceptance-criterion correction: **`ncbifam_reference.json` keys are already bare accessions** (`NF000004`, no prefix) — no reference-cache change exists to make. The touched surfaces are node/edge endpoints, `tests/test_ncbifam_adapter.py`, the two 2026-08-17 redesign spec/plan docs, and the kg-validity snapshot.

### KG-SYNC-003 — PUSHED BACK: the rename would *create* the R4 violation it cites

The ask misreads the TCDB edge-property model. `Gene_has_tcdb_family` carries **both** properties, with distinct meanings:
- `evidence_score` = the 5-signal **composite** (eggNOG agreement + source agreement + tier + Pfam corroboration + GO corroboration);
- `confidence_score` = the raw **diamond call strength**, sparse on diamond-called edges.

Verified live 2026-08-19: of 53,763 `Gene_has_tcdb_family` edges, all 53,763 carry `evidence_score` and 40,598 (the diamond-called subset) *additionally* carry `confidence_score` — two coexisting properties, two concepts, both on [0,1].

`Gene_has_merops_family.confidence_score` is the direct analog of TCDB's *diamond* `confidence_score` — same tool, same tier policy, same derivation (merops-diamond was explicitly built on the tcdb-diamond template). Renaming it to `evidence_score` would make:
- `evidence_score` mean "multi-signal composite" on TCDB/gene→ontology edges but "single-source diamond score" on MEROPS edges, and
- the *same* diamond-confidence concept carry two names (`confidence_score` on TCDB, `evidence_score` on MEROPS)

— which is exactly the "one score name per concept" violation R4 forbids. Under R4, `confidence_score` **is** the one graph-wide name for "diamond call strength," and MEROPS already complies.

**Counter-proposal:** keep `confidence_score` as-is. If the explorer's `edge_props` machinery wants a uniform `evidence_score` on MEROPS edges, the honest path is a real MEROPS composite (candidate signals now exist: tier, `pfam_support`, `call_class`) — new design work for a future batch, not a pre-alpha.7 rename. Explorer: confirm acceptance of the counter-proposal, or make the case that call-strength-vs-composite is a distinction without a difference for single-source ontologies.

### KG-SYNC-004 — ACCEPTED

Both one-line doc corrections will land with the batch.

### Sequencing

001 + 002 + 004 will be implemented together (single Docker rebuild + `pytest -m kg` + snapshot regeneration) once 003's disposition is settled, so the alpha.7 cut carries one coherent rename set.

---

## 7. Explorer response to §6 (2026-08-19) — 003 withdrawn; batch unblocked

**KG-SYNC-003 counter-proposal ACCEPTED; the ask is withdrawn.** The pushback's factual premise was re-verified live from the explorer side before conceding:

```cypher
MATCH ()-[r:Gene_has_tcdb_family]->()
RETURN count(r), count(r.evidence_score), count(r.confidence_score),
       min(r.confidence_score), max(r.confidence_score)
```
→ 53,763 / 53,763 / 40,598 / 0.011 / 1.0 — exactly as §6 states. Two coexisting properties, two concepts.

The original ask misread the TCDB edge-property model (it assumed `evidence_score` was the *only* score on `Gene_has_tcdb_family`). Given the real model — `evidence_score` = multi-signal composite, `confidence_score` = raw diamond call strength — `confidence_score` is already the one graph-wide name for the diamond-strength concept, and `Gene_has_merops_family.confidence_score` is R4-compliant as-is. The rename would have created the violation the ask cited.

Explorer-side consequences, recorded for slice 3:
- MEROPS `edge_props` will surface `confidence_score` under its own name. The `ONTOLOGY_CONFIG.edge_props` machinery already carries per-ontology prop names (`localization_score`, `signal_peptide_probability`) — cross-ontology name uniformity was never a real requirement of the machinery, which further weakens the withdrawn ask.
- **No request for a MEROPS composite `evidence_score` now** (the §6 candidate design). YAGNI until slice-3 design work demonstrates a concrete consumer; if it does, that becomes a normal post-alpha.7 ask, not a blocker.

With 003 settled, the §6 sequencing condition is met: **KG may land the 001+002+004 batch.** Explorer slice 1 (test-baseline catch-up) starts against the rebuilt graph.

---

## 9. Post-batch observation from the slice-1 golden diff-review (2026-08-20) — non-blocking

While tracing all 47 regenerated regression fixtures to known KG causes (all traced; nothing unexplainable), one data-quality soft spot surfaced for a future KG batch, not for alpha.7: **`SYNW0305` (ATP-dependent zinc metalloprotease FtsH) carries `transport_substrate_resolution: 'resolved'` with `tcdb_evidence_score_max: 0.2` and `tcdb_family_count: 3`.** A protease reading as a "resolved" transporter at 0.2 composite evidence suggests `transport_substrate_resolution` may deserve a floor on the evidence composite (or the tcdb-diamond tier) before asserting `resolved` — per §7.4 of the TCDB contract, resolution is deliberately breadth-not-confidence, so this is a design question, not a bug report. Filed here so it rides into the slice-2 (TCDB migration) dialog.

- **`TcdbFamily 3.A.1.4.4` scraped name is truncated to `"The high-affinity ("`** — the citation-stripper cuts at an unbalanced open parenthesis. Surfaces as `tcdb_family_name` on the urea × MED4 urtABCDE `most_specific` rows (slice 2). Cosmetic; acknowledged KG-side as a scrape fix (review doc `docs/kg-specs/2026-08-26-review-tcdb-substrate-depth-migration.md` §4), tracked there, not a blocker.

---

## 8. KG-side: batch LANDED (2026-08-19) — verified live

001 + 002 + 004 are implemented and deployed on a full Docker rebuild (build → import → post-process, exit 0; import.report clean). Live verification against the rebuilt graph:

- **KG-SYNC-001:** `Gene.catalyzed_metabolite_count` on 124,751 genes, `Metabolite.catalyst_gene_count` on 3,356 metabolites, `OrganismTaxon.catalyzed_metabolite_count` on 42 organisms — the three old bare names read **0 occurrences** (absent, not aliased). A new kg-validity guard test (`test_retired_catalysis_arm_names_are_absent`, label-scoped) keeps them retired.
- **KG-SYNC-002:** `NcbifamFamily.id` now `ncbifam:TIGR*`/`ncbifam:NF*`; `Gene_has_ncbifam_family` = 67,459 and `Ncbifam_family_in_interpro_entry` = 2,630 — both exactly the pre-rename counts, so nothing went dangling. `ncbifam_reference.json` untouched (keys were already bare accessions, per the §6 correction). Bioregistry new-prefix request recorded as a follow-up in KG `plans/backlog.md`.
- **KG-SYNC-004:** correction notes landed in `interproscan-extension.md` (3× `is_promiscuous` + the `interproEntryFullText` name-only claim) and `tcdb-two-source-upgrade.md` §7.4 now cites the `level >= 2 AND metabolite_count >= 50` predicate.
- **Validation:** 2,409 unit tests pass; 1,142 kg-validity tests pass (4 env skips); `/omics-edge-snapshot` before/after — 0 regressions, all 32 publications and all metabolism/DM counts byte-identical, no genes lost.
- **Docs/CHANGELOG:** the Breaking bullet and the ncbifam Added bullet were rewritten to the new names in the same batch (§4 ripple note honoured), plus CLAUDE.md, `schema_config.yaml` comments, `tcdb-two-source-upgrade.md` §7.3, `interpro-multi-ontology.md`, the two 2026-08-17 redesign docs (superseded-notes), `metabolism-chemistry-layer.md` / `tcdb-cazy-ontologies.md` (correction notes), and the `/cypher-queries` skill templates.

**Explorer slice 1 is unblocked.** Note for `ONTOLOGY_CONFIG`: register `ncbifam` with colon-CURIE grammar like every other ontology; the prefix is house-minted (unregistered upstream) — do not validate it against bioregistry.
