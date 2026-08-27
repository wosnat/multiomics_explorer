# KG-side asks: annotation-trust surface (slice 3 — interpro / ncbifam / merops + trust normalization)

**Date:** 2026-08-27 · **From:** explorer (`multiomics_explorer`) · **To:** KG (`multiomics_biocypher_kg`)
**Context:** synced release program (KG 0.1.0-alpha.7 + explorer 0.1.0-alpha.5), slice 3.
**KG review:** see §6 (2026-08-27) — all asks accepted; ONT-006/007/008/009/010 need explorer-side revision.
**Status of the three ontologies:** unreleased → renames and property changes are cheap now; every ask
below is scoped as "before the alpha.7 cut". Previous asks docs: `2026-08-19-presync-kg-asks.md`,
`2026-08-26-review-tcdb-substrate-depth-migration.md`.

## 1. Why this doc

The explorer is not registering three more ontologies — it is building a **normalized annotation-trust
surface** across all gene→term edges: every ontology row carries the same axes (`sources`, `evidence`,
`evidence_score`, `tier` — one compact trust column, the rest verbose; native scalars stay under their own names and are never compared across ontologies), the same
filter params (`sources`, `evidence`, `max_tier`, `min_evidence_score`, `call_class`, `interpro_type`),
and a new `ontology_term_details` tool that reads node props + forward bridges. Design:
`docs/superpowers/specs/2026-08-27-annotation-trust-surface-design.md` (sections 1–10 reviewed with the
explorer owner 2026-08-27; frozen tool spec follows this dialog).

A normalized column is only honest if the underlying KG facts share name, scale, and semantics. The asks
below are exactly the places where they don't — each one is otherwise an explorer-side special case that
would live forever.

Verified live against the 2026-08-26 build (`built_at 2026-08-26T08:50Z`, 124,751 genes) via `run_cypher`.

## 2. Ask summary

| ID | Ask | Pri | Kind |
|---|---|---|---|
| ONT-001 | `Gene_has_ncbifam_family.match_count` — contract says present, absent on all 67,459 edges. Emit or strike. | P2 | graph or doc |
| ONT-002 | Register sparse HMM/e-value props in `ControlledVocabulary` (`Gene_has_interpro_entry.evalue` null on 118,209/397,342; `match_count`; `Gene_has_ncbifam_family.evalue`/`score`) with the null-producing libraries named. | P3 | vocab |
| ONT-003 | Register diamond call props (`confidence_score`, `identity`, `qcov`, `evalue`, `consensus_n`) once each on `Gene_has_tcdb_family` (sparse) and `Gene_has_merops_family` (dense), with min/max. | P3 | vocab |
| ONT-004 | 10 retired `NcbifamFamily` nodes: `family_type` absent → `family_type = 'retired'` (closed vocab value). | P3 | graph |
| ONT-005 | `MeropsFamily.organism_count` blends dead homologs (no `peptidase_organism_count`). Note only. | P4 | note |
| **ONT-006** | **`evidence_score` on `Gene_has_merops_family`** (R4: one score name per concept; concept exists — `tier`, `pfam_support`). Or confirm `null` is the intended reading. | **P2** | graph |
| **ONT-007** | **Uniform `sources: str[]` on every functional gene→ontology edge type** (14 types: GO×3, EC, Pfam, CAZy, TCDB, KO, COG, cyanorak, tigr, interpro, ncbifam, merops; PSORTb/SignalP are structural and excluded). Today on 7; missing on merops (`['merops_diamond']`), interpro/ncbifam (`['interproscan']`), kegg/cog/cyanorak/tigr (eggnog/cyanorak). R2 already requires the `DataSource` join — the nodes exist. | **P1** | graph |
| **ONT-008** | **Uniform `evidence` categorical on every gene→ontology edge type**, one closed vocab. Proposed: `curated \| signature \| homology \| family_inferred \| domain_inferred` — `signature` for direct HMM/profile hits (InterPro, NCBIfam, Pfam-direct), `homology` (new) for diamond calls (TCDB `tcdb_diamond`, MEROPS), `family_inferred` for orthology transfer (eggNOG-sourced TCDB/KO/COG/roles). Multi-source edges take the strongest. | **P1** | graph + vocab |
| **ONT-009** | **`gene_count` / `organism_count` semantics differ by label**: `InterproEntry` = DIRECT genes (verified 171/171 parents), `MeropsFamily` / `TcdbFamily` / `CazyFamily` = SUBTREE (verified 54/54). Unify to subtree for hierarchical ontologies (InterPro's is-a is 100% within-type, so subtree is meaningful), or add `direct_gene_count` and document. | **P1** | graph |
| **ONT-010** | **`Gene_has_tcdb_family.attachment_depth`** ∈ `deepest \| superseded` — materialize the `NOT EXISTS` deepest-attachment predicate the KG already uses at 3 post-import sites. Structural fact, not a threshold (R3 doesn't apply). Lets `gene_ontology_terms` leaf rows and every KG count agree by construction, and lets superseded rows be *labelled* (the KG review's option b) instead of dropped. MEROPS needs none (0 double-attachments). | **P2** | graph |
| ONT-011 | Rename `Gene_has_ncbifam_family.score` → `bit_score`. `score` is already PSORTb's confidence on `Gene_has_subcellular_localization` (released); NCBIfam is unreleased and the value is an HMMER bit score. R4 spirit. | P3 | rename |
| ONT-012 | `family_type` is the same property name with two unrelated vocabularies on `MeropsFamily` (`peptidase\|inhibitor`) and `NcbifamFamily` (15 NCBIfam classes). R1b says namespace on collision (`level_kind` precedent). Suggest `MeropsFamily.family_type` → `family_class` (or `merops_family_type`); NCBIfam keeps the external term verbatim (R1). | P3 | rename |
| ONT-013 | `Gene.merops_evidence_score_max` (mirror of `tcdb_evidence_score_max`) — only if ONT-006 lands; gene-level "is this a protease at all" routing. | P4 | graph |
| ONT-014 | `ControlledVocabulary` coverage gap: no entries at all for `Gene_has_kegg_ko`, `Gene_in_cog_category`, `Gene_has_cyanorak_role`, `Gene_has_tigr_role`, `Gene_has_subcellular_localization`, `Gene_has_signal_peptide_type`. Falls out of ONT-007/008 for the first four; PSORTb/SignalP need `score` / `probability` / `cleavage_site` / `cleavage_probability` numeric entries. Explorer rule: every `(edge_or_label, prop)` it filters or rolls up on must have a vocab node — enforced by a `-m kg` test; at runtime a missing node falls back to a live `DISTINCT` pivot query + warning, never a hard-coded list. | **P2** | vocab |

## 2b. Which design decision each ask unblocks

| ask | design section | if granted | if declined |
|---|---|---|---|
| ONT-007 `sources` everywhere | §3 rows, §4.1 filter, §5.1 `by_sources` | one universal axis (14 edge types; the explorer's 17 ontology keys = 14 functional edges + brite (via the KO edge) + PSORTb + SignalP) | column/filter/rollup exist on 7 of 14 edge types; `skipped_ontologies` on the rest |
| ONT-008 `evidence` ladder | §1 single compact trust column choice, §4.1 | `evidence` becomes the candidate universal compact column | compact column = `evidence_score` (null on 9 ontologies); `evidence` filter on 6 |
| ONT-009 `gene_count` semantics | §3.4 `search_ontology` compact, §6 `ontology_term_details`, §7.1 browse sort | one number, comparable across ontologies in the list layer | per-ontology footnote; InterPro subtree computed live in details |
| ONT-010 `attachment_depth` | §7.3 leaf mode, `include_superseded` param | superseded TCDB rows labelled + requestable | `*1..` leaf filter drops them; no param |
| ONT-006 MEROPS `evidence_score` | §3, §4.1 `min_evidence_score`, §8.1 `merops_evidence_score_max` (ONT-013) | MEROPS joins the cutoff/rank axis | MEROPS trust read from `tier`+`pfam_support`; docstring says so |
| ONT-011 `bit_score` | §3 verbose column name | `bit_score` | column named `ncbifam_score` explorer-side to avoid the PSORTb `score` collision |
| ONT-012 `family_type` collision | §3.4 / §6 term columns | distinct names | explorer emits `merops_family_type` / `ncbifam_family_type` (prefix only where the KG collides) |
| ONT-014 vocab coverage | §4.2 validation, §8.2 `list_filter_values`, §8.3 pivot fallback | values + descriptions from the contract | runtime pivot query + warning; `-m kg` test stays red until landed |
| ONT-001/002/003/004 | §3 verbose columns, §8.2 | clean columns | nulls / doc notes |

## 3. Per-ask detail

### ONT-007 — uniform `sources` (P1) — rationale corrected 2026-08-27 per §6.1

Design driver: `sources` is a normalized trust axis and a filter param. With 7 of 14 gene→ontology edge
types lacking it, the axis is absent on half the ontologies and the filter must raise "unsupported axis"
on `ontology='merops'` — for an edge that has exactly one known source. Single-valued lists are fine
(`['merops_diamond']`).

Cost is one constant literal per adapter, not a merge change: every edge type missing `sources` is
single-source by configuration (`kegg_ko` / `cog_category` eggNOG-only; cyanorak / tigr roles
Cyanorak-only; interpro / ncbifam interproscan-only; merops merops_diamond-only). *(Earlier draft claimed a
per-token provenance map for KO/COG/roles — wrong; that map exists only for `ec_numbers`, `go_terms`,
`pfam_ids`, `cazy_ids`, `ncbifam_ids`, `gene_name`, `product`, `function_description`.)*

Live: `Gene_has_kegg_ko`, `Gene_in_cog_category`, `Gene_has_cyanorak_role`, `Gene_has_tigr_role`,
`Gene_has_interpro_entry`, `Gene_has_ncbifam_family`, `Gene_has_merops_family` carry no `sources`.

### ONT-008 — uniform `evidence` (P1)

Design driver: `evidence` is the single categorical an agent (or ORA) reads to tell a curated fact from a
guess. It exists on the 6 eggNOG-era edges with a strength ladder; the four scored ontologies express
the same idea in four private vocabularies (`tier`, `call_class`+`best_hit_kind`, `libraries`,
`family_type`). One closed ladder across all 14 functional edge types makes `evidence=['curated','signature']` mean
the same thing everywhere. Proposed mapping (KG to correct):

| edge | value |
|---|---|
| InterPro, NCBIfam | `signature` (direct HMM/profile match, pre-thresholded by the member DB) |
| TCDB `tcdb_diamond`-only, MEROPS | `homology` (new value: sequence-similarity call, tier carries strength) |
| TCDB `eggnog`-only, KO, COG, roles (eggNOG) | `family_inferred` (orthology transfer) |
| CyanoRak-sourced roles | `curated` |
| both-source TCDB | strongest of the two |

If `homology` is rejected, `family_inferred` for diamond calls is the fallback — but that hides the
direct-vs-transferred distinction the TCDB doc itself calls load-bearing.

### ONT-009 — `gene_count` semantics (P1)

`ontology_term_details` and `search_ontology` show `gene_count` side by side across ontologies; today the
same number means "genes attached here" on InterPro and "genes anywhere in the subtree" on MEROPS/TCDB/
CAZy. GO/KEGG/EC semantics not verified here — please state them in the reply. Preferred: subtree
everywhere hierarchical (matches what `genes_by_ontology(term_ids=[...])` returns), plus
`direct_gene_count` only if some consumer needs it.

### ONT-010 — `attachment_depth` on TCDB gene edges (P2)

MED4 live: 670 `Gene_has_tcdb_family` rows, 73 superseded (64 are tier-3 diamond family calls above an
eggNOG subfamily call). The explorer can compute this with a `*1..` `NOT EXISTS` in leaf mode, but then
(a) the row disappears rather than being explained, and (b) every explorer traversal re-derives a fact
the KG computes at 3 sites. A materialized `attachment_depth` also lets `genes_by_ontology` surface the
second source's evidence on the superseded row without double-counting the gene.

### ONT-006 — MEROPS `evidence_score` (P2)

With a normalized `evidence_score` column, a MEROPS tier-2 corroborated peptidase call reads `null` next
to a TCDB tier-3 uncorroborated call at `0.2`. Either emit `round(fired/2, 3)` over
`{tier_le_2, pfam_support}` (or 3 signals adding `call_class = 'peptidase'`), or state in the vocab
description that MEROPS trust is read from `tier` + `pfam_support` and the explorer documents it as such.

### ONT-001 / 002 / 003 / 004 / 011 / 012 / 014 — contract hygiene

Detail as in the summary table. All are one-line graph/vocab changes; 011 and 012 are renames that are
free only while unreleased.

## 4. Audited and accepted as-is (explicit non-asks)

- `InterproEntry.level_kind` / `NcbifamFamily.level_kind` null — contract (`expected_empty`).
- `MeropsFamily.catalytic_type` null on inhibitor clans/families; no `is_uninformative` on MEROPS.
- `Gene_has_merops_family.tier` vocab `closed: "false"` int 1–3.
- `Gene_has_merops_family.confidence_score` keeps its name (KG-SYNC-003 outcome stands).
- `Gene_has_tcdb_family.tier` sparse (absent on 13,165 eggNOG-only edges) — explorer keeps tier-less
  edges when `max_tier` filters; documented.
- InterPro `description` observed-only (44 nodes without) — additive degradation, fine.
- InterPro `evalue` never a filter (contract) — explorer offers no e-value cutoff.
- Bridge verbs encode strength (`has` composition / `in` membership / `related_to` router) and direction
  is load-bearing — explorer's `ontology_term_details.links_out` is forward-only by construction and
  derives `link_kind` from the relationship type; no KG property asked.
- `TcdbFamily.name = tcdb_id` fallback — derived, not materialized (R3).

## 5. Explorer-side consequences if an ask is declined

| declined | explorer fallback |
|---|---|
| ONT-007 | `sources` column null + filter raises on 6 ontologies; docs list which |
| ONT-008 | `evidence` column null on 7 ontologies; per-ontology strength read from `tier`/`libraries`/… in verbose |
| ONT-009 | `gene_count` column documented as "direct on interpro, subtree elsewhere"; `ontology_term_details` computes subtree live for interpro |
| ONT-010 | `*1..` leaf filter drops superseded rows silently |
| ONT-006 | `evidence_score` null on merops; docstring says read `tier`+`pfam_support` |

## 6. KG review (2026-08-27, `multiomics_biocypher_kg`)

Every live number above was re-verified against the 2026-08-26 build and all match. Responses below are
per ask ID; "accept" means the KG will ship it in one pre-alpha.7 batch (KG-SYNC-005). Explorer: please
revise the asks marked **revise** before the batch is cut.

### 6.1 Verdicts

| ID | Verdict | KG response |
|---|---|---|
| ONT-001 | accept — **strike** | Confirmed: `schema_config.yaml` and `ncbifam_adapter` only emit `start/end/evalue/score`; `match_count` lives only in the docs (`interpro-multi-ontology.md`, CLAUDE.md). It is meaningful on the cross-library InterPro edge (row tally) and noise on a single-library edge. Docs will be corrected; no property added. |
| ONT-002 | accept | The vocab yaml already supports `min_value`/`max_value` on `float`/`int` entries — no contract-schema extension needed. The "null-producing libraries" list will be **derived at build time** from the calls.json (libraries that never report an e-value) and written into the vocab description, not hand-maintained. |
| ONT-003 | accept | Same mechanism as ONT-002. |
| ONT-004 | accept | The 10 nodes are `NF*` accessions absent from `ncbifam_reference.json`; the adapter deliberately emits a minimal node with `family_type` omitted. Will emit `family_type = 'retired'`. Caveat: `NcbifamFamily.family_type` is an external-verbatim vocab (R1), so the entry description will name `retired` as the single KG-minted sentinel in that set. |
| ONT-005 | accept (optional) | `peptidase_organism_count` is the same post-import query as `peptidase_gene_count` with `collect(DISTINCT organism_name)`. Will add it — tell us if you would not surface it and we drop it. |
| ONT-006 | accept — **revise signal set** | Will emit `evidence_score` on `Gene_has_merops_family` with **2 signals, not 3**: `{tier <= 2, pfam_support = 'corroborated'}`. `call_class = 'peptidase'` is excluded: it is a *verdict* axis, not a placement-confidence axis — including it would score a confidently-placed dead homolog lower for being honest, and this doc already treats `pfam_support` and `call_class` as orthogonal. `signal_count: 2` + `signals` published per R4 so `round(score × 2)` recovers the raw count (same construction as the GO/Pfam edges). Scale is coarse (0 / 0.5 / 1) but honest. Unblocks ONT-013. |
| ONT-007 | accept (P1) — **rationale wrong, cost lower** | The "per-token provenance map" does **not** exist for KO/COG/roles: `gene_annotations_merged.json` carries `<field>_source` only for `ec_numbers`, `go_terms`, `pfam_ids`, `cazy_ids`, `ncbifam_ids`, `gene_name`, `product`, `function_description`. It is not needed: `kegg_ko` and `cog_category` are eggNOG-only in `gene_annotations_config.yaml`, cyanorak/tigr roles are Cyanorak-only, interpro/ncbifam are interproscan-only, merops is merops_diamond-only. Every missing edge type has a **constant** `sources` list — one literal per adapter + 7 vocab entries, no merge change. Please fix the rationale paragraph in §3. |
| ONT-008 | accept (P1) — **revise ladder** | `homology` accepted as a new value. Three corrections, see §6.2. |
| ONT-009 | accept (P1) — **premise incomplete** | GO / KEGG / EC / Pfam / COG nodes carry **no `gene_count` at all** (verified: 0 nodes with the property on `KeggTerm`, `BiologicalProcess`, `EcNumber`, `Pfam`, `CogFunctionalCategory`). The disagreement is direct (InterPro) vs subtree (TCDB/CAZy/MEROPS) vs **absent** (everything eggNOG-era + roles). KG will: make `gene_count` subtree on all four hierarchical ontologies and add `direct_gene_count` on the same four. InterPro's is-a is sparse (1,569 edges over ~13K nodes, ~86% level-0) so its `gene_count` barely moves; the `(interpro_type, level)`-stratified ORA rationale survives via `direct_gene_count`. A comparable `gene_count` on GO/KEGG/EC/Pfam/COG/roles is a **separate, larger ask** (GO subtree counts over a 30K-node DAG) — please file it explicitly as ONT-015 if the list layer needs it; it does not fall out of this one. |
| ONT-010 | accept (P2) — **revise value names** | The three post-import sites are real (`post-import.cypher` transported_metabolite_count / transporter_gene_count / Organism_has_metabolite); materializing once and reading the property at all three is a KG correctness win too. Value pair will follow the existing R5 vocabulary: `attachment_depth: most_specific \| superseded` (mirrors `substrate_depth: most_specific \| inherited`), not `deepest`. Vocab description will define `superseded` as "less specific than another attachment of the same gene", not "wrong" — an eggNOG family call above a diamond subfamily call is still a correct call. |
| ONT-011 | accept | `bit_score`. |
| ONT-012 | accept | Literal R1b collision. `MeropsFamily.family_type` → `family_class`; the existing `MeropsFamily.family_type` vocab entry renames with it. NCBIfam keeps `family_type` verbatim. |
| ONT-013 | accept | Trivial post-import `max()` once ONT-006 lands; bundled. Sparse like `tcdb_evidence_score_max` — use `coalesce(…, -1.0)`. |
| ONT-014 | accept (P2) | Gap confirmed: no vocab keys today for `Gene_has_kegg_ko`, `Gene_in_cog_category`, `Gene_has_cyanorak_role`, `Gene_has_tigr_role`, `Gene_has_subcellular_localization`, `Gene_has_signal_peptide_type`. Also missing and folded into this batch: `Gene_has_interpro_entry.evalue`/`match_count`, all `Gene_has_ncbifam_family.*`, the diamond props on `Gene_has_tcdb_family` / `Gene_has_merops_family` (ONT-002/003), and `Gene_has_tcdb_family.evidence` (new under ONT-008). |

### 6.2 ONT-008 corrections

1. **Keep per-edge vocab entries.** The current contract declares `evidence` *per edge type with differing
   domains* (vocab header: "per edge type, domains genuinely differ, spec §5.2"). One global closed ladder is
   compatible only if each edge's entry keeps listing its own **subset** of the ladder — do not collapse to a
   single entry. The explorer's `evidence=[...]` filter still means the same thing everywhere; what differs
   per edge is which values are *possible*.
2. **`homology` needs a stated rank.** Diamond tier 1 (≥70 % identity to a curated reference sequence) is
   stronger than eggNOG OG-transfer; tier 3 is weaker. KG ladder: `curated > signature > homology >
   family_inferred > domain_inferred`, with the vocab description stating that strength *within* `homology`
   is read from `tier`. Do **not** split `homology` by tier into separate ladder values — that reintroduces
   the private vocabulary the ask is removing.
3. **`evidence` is orthogonal to `call_class`.** A `nonpeptidase_homolog` MEROPS edge is still
   `evidence = homology` (the *placement* evidence is a homology hit; the verdict is a separate axis), exactly
   as `pfam_support` is already kept orthogonal to `call_class`.
4. Mapping as proposed otherwise stands: InterPro / NCBIfam → `signature` (consistent with `Gene_has_pfam`
   already using `signature` for InterPro-direct hits); KO / COG / eggNOG-sourced TCDB → `family_inferred`;
   Cyanorak + TIGR roles → `curated`; both-source TCDB → strongest = `homology`.
5. Table nit: the "TCDB `eggnog`-only" row is **net-new**, not a remap — `Gene_has_tcdb_family` carries no
   `evidence` today (0 of 53,763), only `sources` / `evidence_score`.

### 6.3 Doc nits

- ONT-007 says "13 types"; the enumeration is 14 (present on 7: GO×3, EC, Pfam, CAZy, TCDB; missing on 7:
  KO, COG, cyanorak, tigr, interpro, ncbifam, merops). §2b says "17 ontologies" — different counting basis;
  pick one and state it.
- §4 "no `is_uninformative` on MEROPS" — correct and intentional.

### 6.4 KG batch scope (KG-SYNC-005, pre-alpha.7)

Adapters: 7 constant `sources` literals + `evidence` on all 14 gene→ontology edge types (TCDB/MEROPS
derived from `sources`/`tier`). Post-import: `attachment_depth`, MEROPS `evidence_score` (+ `signals`,
`signal_count`), `Gene.merops_evidence_score_max`, `direct_gene_count` ×4 + InterPro `gene_count` → subtree,
`peptidase_organism_count`. Renames: `bit_score`, `family_class`. Vocab: ~25 entries. Docs: schema,
CLAUDE.md, `interpro-multi-ontology.md`, `merops-extension.md`, CHANGELOG `### Breaking` (InterPro
`gene_count` semantics + two renames). Verification: `capture_annotation_state.py --save/--compare`,
snapshot regen, vocab-drift test, byte-diff of `post-import-validate.sh` on untouched sections.


## 7. Explorer response (2026-08-27) — all verdicts accepted; one new ask; batch unblocked

### 7.1 Per-ask

| ID | Explorer |
|---|---|
| ONT-001 | Accept strike. Explorer verbose column set for ncbifam: `evalue`, `bit_score`, `start`, `end`. |
| ONT-002/003/014 | Accept. Explorer's `-m kg` vocab-coverage test will enumerate exactly the `(applies_to, property)` pairs it filters or rolls up on; list attached in §7.3 so the batch can be checked against it. |
| ONT-004 | Accept `retired` sentinel; surfaced verbatim, `list_filter_values(ncbifam_family_type)` shows the vocab description. |
| ONT-005 | **Keep it.** `ontology_term_details` will surface `peptidase_gene_count` + `peptidase_organism_count` side by side with `gene_count` / `organism_count` (details/compact). |
| ONT-006 | Accept 2-signal construction. Explorer docs state the scale is {0, 0.5, 1} and that `call_class` is a verdict axis read separately. |
| ONT-007 | Accept; §3 rationale corrected above. |
| ONT-008 | Accept all five corrections: per-edge vocab subsets retained (explorer unions them for `list_filter_values`, filters validate per selected ontology); `homology` ranked between `signature` and `family_inferred`, strength within it read from `tier`; orthogonal to `call_class`; TCDB `evidence` net-new. |
| ONT-009 | Accept subtree `gene_count` + `direct_gene_count` on the four hierarchical ontologies. Premise gap acknowledged → **ONT-015 filed below.** |
| ONT-010 | Accept `attachment_depth: most_specific \| superseded` and the "less specific, not wrong" definition; explorer param becomes `include_superseded` with that wording. |
| ONT-011/012/013 | Accept. Explorer reads `bit_score`, `family_class`, `merops_evidence_score_max` (sparse, uncoalesced in rows; `-1.0` only where a total order is required). |
| §6.3 nits | Fixed: 14 functional edge types vs 17 explorer ontology keys, basis stated. |

### 7.2 ONT-015 — `gene_count` / `organism_count` on the eggNOG-era ontology nodes (P2, new)

Ask: subtree-semantics `gene_count` and `organism_count` on `BiologicalProcess` / `MolecularFunction` /
`CellularComponent`, `EcNumber`, `KeggTerm`, `Pfam` + `PfamClan`, `CogFunctionalCategory`, `CyanorakRole`,
`TigrRole`, `BriteCategory` (and, for completeness, `SubcellularLocalization` / `SignalPeptideType`, flat).
Same post-import recipe already used for TCDB/CAZy/MEROPS/InterPro.

Why the list layer needs it: `search_ontology` gains a browse mode (no `search_text`) that sorts by
`gene_count` and filters on `min_gene_count`, and its compact row carries `gene_count`/`organism_count` on
every ontology. Today that column would be populated on 4 of 17 ontologies. The per-organism variant is
computed live by the explorer when `organism=` is given (that is a different number and stays live), but
the corpus-wide count is a node fact and belongs on the node.

Explorer fallback if declined or deferred to a later cut: browse mode without `organism=` sorts by
`id` on ontologies lacking the property, `gene_count` is `null` there, and the yaml lists which. Not a
blocker for alpha.7; a blocker for the "list ontology terms" story being uniform.

GO DAG note: the explorer's `genes_by_ontology` already walks `is_a|part_of *0..` over the full GO DAG per
organism at query time, so a one-off post-import subtree count over ~30K nodes is well within what the
graph already does per request.

### 7.3 Vocab pairs the explorer will assert (for the batch check)

Edge props: `sources`, `evidence`, `evidence_score` on all 14 functional gene→ontology edge types where
carried; `tier`, `confidence_score`, `identity`, `qcov`, `evalue`, `consensus_n`, `pfam_support` on
`Gene_has_tcdb_family` + `Gene_has_merops_family`; `source_agreement`, `go_support`, `attachment_depth` on
`Gene_has_tcdb_family`; `call_class`, `best_hit_kind` on `Gene_has_merops_family`; `libraries`,
`evalue_library`, `evalue`, `match_count` on `Gene_has_interpro_entry`; `evalue`, `bit_score` on
`Gene_has_ncbifam_family`; `score` on `Gene_has_subcellular_localization`; `probability`, `cleavage_site`,
`cleavage_probability` on `Gene_has_signal_peptide_type`.
Node props: `InterproEntry.interpro_type`, `NcbifamFamily.family_type`, `MeropsFamily.family_class`,
`MeropsFamily.catalytic_type`, `MeropsFamily.level_kind`, `TcdbFamily.level_kind`, `CazyFamily.level_kind`,
`BriteCategory.tree`, `Gene.merops_classes`.

### 7.4 Sequencing

KG-SYNC-005 batch → rebuilt graph on `:7687` → explorer refreshes the schema baseline, verifies the spec
Cypher live, freezes `docs/tool-specs/2026-08-27-annotation-trust-surface.md`, then builds. ONT-015 may
ride in the same batch or the next; the explorer design does not block on it.

## 8. KG reply to §7 (2026-08-27) — ONT-015 accepted into KG-SYNC-005

**ONT-015 — accept, same batch.** Cheaper than §7.2 assumes: the KG's GO layer is pruned to seed terms +
ancestors, so live it is 3,433 BP / 2,899 MF / 451 CC nodes (6.8K total, not 30K), with 5,945 / 3,694 / 544
`is_a` edges plus `part_of` edges (253 on BP). Other sizes: `EcNumber` 7,337 (7,330 is-a), `KeggTerm` 5,141
(8,928 is-a; KOs are multi-parent across pathways), `Pfam` 6,603 + `PfamClan` 533 (4,002 `Pfam_in_pfam_clan`),
`CyanorakRole` 173 (154 is-a), `TigrRole` 114 (flat), `CogFunctionalCategory` 26 (flat). Same `*0..` recipe
as CAZy/MEROPS.

Semantics the KG will ship, please mirror in the explorer docs:

- `gene_count` / `organism_count` = **subtree** on every hierarchical label (GO×3, EC, KEGG, PfamClan,
  CyanorakRole); = direct on flat labels (Pfam, TigrRole, COG, SubcellularLocalization, SignalPeptideType,
  NcbifamFamily — already there for the last three). `direct_gene_count` added on the hierarchical ones
  (same 4 + these 5), so the pair is uniform wherever a hierarchy exists.
- GO subtree walks **`is_a` ∪ `part_of`** (the KG's `level` and the explorer's `genes_by_ontology` both do;
  `regulates` is not in the graph). GO and KEGG are DAGs — a gene reachable through two parents is counted
  once per node, so **sibling counts do not sum to the parent's**; the vocab description says so.
- `PfamClan.gene_count` = distinct genes over member Pfams (one hop, `Pfam_in_pfam_clan`); Pfam itself is
  flat so `gene_count` = `direct_gene_count` there and only `gene_count` is emitted.
- `KeggTerm` counts are set on **all** levels (category / subcategory / pathway / ko); the existing
  pathway-only `reaction_count` / `metabolite_count` are untouched.
- `BriteCategory.gene_count` / `organism_count` **already exist** (subtree, since 2026-04) — drop it from
  the §7.2 list; it gets `direct_gene_count` for uniformity only.

§7.3 vocab list: matches the batch scope; two additions on the KG side — `direct_gene_count` is a plain int
(no vocab node, R3: it is a count) and `NcbifamFamily.family_type` gains the `retired` sentinel noted under
ONT-004. §7.4 sequencing accepted; KG plan: `plans/kg_sync_005_annotation_trust.md` in the KG repo.

## 9. KG-SYNC-005 landed (2026-08-27) — rebuilt graph on `:7687`, ready for the explorer schema-baseline refresh

Live numbers from the rebuilt graph (124,751 genes, unchanged):

- **ONT-007/008** — `sources` + `evidence` on 100% of all 14 gene→ontology edge types; 110
  `ControlledVocabulary` nodes (was ~62). TCDB: `homology` 40,598 / `family_inferred` 13,165 edges.
- **ONT-006/013** — `Gene_has_merops_family.evidence_score`: 0 → 151, 0.5 → 3,768, 1.0 → 338 (of 4,257);
  `Gene.merops_evidence_score_max` sparse on exactly the MEROPS-annotated genes.
- **ONT-010** — `attachment_depth`: 46,593 `most_specific` / 7,170 `superseded` (of 53,763); MED4 670/73 as
  predicted. `post-import-validate.sh` dump is **byte-identical** to the pre-batch baseline, so the
  materialized predicate reproduces the inline one on every transport-arm count.
- **ONT-009/015** — `gene_count`/`organism_count` on every ontology label; `direct_gene_count` on the 10
  hierarchical labels. InterPro subtree vs direct differ on only 115 of 12,999 entries (max delta 63).
  GO root `biological_process`: subtree 66,484 / direct 20,563. **Not emitted:** `direct_gene_count` on
  PfamClan and BriteCategory (constant 0 — vacuous; deviation from §8, please note in the explorer docs).
- **ONT-001/004/011/012** — no `match_count` on NCBIfam edges (contract corrected); 10 `retired` nodes;
  `bit_score` on 67,459 edges; `MeropsFamily.family_class` on all 155 nodes.
- **ONT-002** — the InterPro null-e-value library list (COILS, HAMAP, MOBIDB_LITE, PANTHER, PRINTS,
  PROSITE_PATTERNS, PROSITE_PROFILES, SUPERFAMILY) was measured by script over the committed calls.json and
  written into the vocab description — a static list re-measured on an InterProScan release bump, not
  recomputed at every build (deviation from §8 wording).
- Gates: unit 2,413 pass; `pytest -m kg` 1,187 pass / 4 skip; `capture_annotation_state --compare`: every
  distribution unchanged (no bucket added, as designed); snapshot regenerated. Your §7.3 pair list is
  asserted verbatim in `tests/kg_validity/test_annotation_trust.py::test_explorer_vocab_pairs_have_nodes`.

Contract doc: `multiomics_biocypher_kg/docs/kg-changes/annotation-trust-surface.md`. Not yet committed or
tagged — alpha.7 cut follows the explorer's live verification (§7.4).
