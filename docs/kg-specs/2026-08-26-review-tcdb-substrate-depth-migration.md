# KG-side review — `2026-08-20-tcdb-substrate-depth-migration.md` (DRAFT v2)

**Date:** 2026-08-26 · **Reviewer:** KG side (`multiomics_biocypher_kg`) · **Reviewed:** `docs/tool-specs/2026-08-20-tcdb-substrate-depth-migration.md`, DRAFT v2
**Question asked:** does the spec capture TCDB intent as it exists in the KG?
**Verdict:** **Yes, with one substantive gap (§1, live-verified — the spec's own acceptance gene PMM0392 reads 13 metabolites in `gene_overview` but 554 in `metabolites_by_gene` under the spec's row semantics) and two wording risks (§2, §3).** Fix §1 before freeze; §2–§3 are doc-text changes. Nothing in the spec asks the KG for a change.

Everything below was checked against the KG checkout at `5a8ce4e1` (post-alpha.7 rename batch):
`scripts/post-import.cypher` L1208–1327 / L1361–1468, `multiomics_kg/adapters/tcdb_adapter.py` L267–449,
`config/controlled_vocabularies.yaml` L178–271, `docs/kg-changes/tcdb-two-source-upgrade.md` §2 / §7.

---

## 0. What the spec gets right

| Spec claim | KG state | ✓ |
|---|---|---|
| `Tcdb_family_transports_metabolite.substrate_depth` ∈ `most_specific \| inherited`, set on every substrate edge | adapter-set, closed vocab, `VOCAB.check`ed at emit | ✓ |
| `Gene_has_tcdb_family.evidence_score` float `[0,1]`, 5 signals, present on all edges | post-import, `round(n/5.0, 3)` | ✓ |
| `Gene.tcdb_evidence_score_max` sparse; surface as **null**, never coalesce to a sentinel | `SET … = max(r.evidence_score)` only where an edge exists; vocab `sparse: true` | ✓ |
| `Gene.transport_substrate_resolution` ∈ `resolved \| family_inferred`, null when no TCDB edge | `CASE WHEN n_deepest = 0 THEN null …` — null removes the property | ✓ |
| `Gene.transported_metabolite_count`, `Metabolite.transporter_gene_count`, `OrganismTaxon.transported_metabolite_count` | all present post-KG-SYNC-001 | ✓ |
| No score filter param; rank/expose only; `'tcdb' ∈ annotation_types` remains the binary gate | matches contract §2 ("don't hard-filter on the score by default") and §3 | ✓ |
| §8 audit: components (`tier`, `source_agreement`, `pfam_support`, `go_support`) not surfaced because no cutoff is offered | consistent with contract §2 ("if you do offer a cutoff, surface the components") | ✓ |
| `level_kind = 'tc_specificity'` no longer drives any derivation | contract §6 explicitly deprecates it as a substrate filter (466 / 11,263 edges) | ✓ |

Design decisions 1–3 are the right reading of the contract. The live examples (urtABCDE, 2.A.16 nitrite, PMM0392) are consistent with the KG's definitions.

---

## 1. GAP — the gene-side *deepest-attachment* predicate is missing from the row surface

TCDB intent in the KG has **two orthogonal axes**. The spec captures one.

| Axis | Fact about | Meaning | In spec? |
|---|---|---|---|
| `substrate_depth` | **(TcdbFamily, Metabolite)** edge | is this node the most specific *surviving* node carrying this substrate | ✅ surfaced as row field + filter |
| deepest attachment | **(Gene, TcdbFamily)** edge | is this gene's attachment superseded by the same gene's attachment to a *descendant* family | ❌ neither applied nor surfaced |

The second axis is not optional — **every KG transport count the spec exposes is computed over deepest attachments only**, with the identical predicate at each site:

```cypher
MATCH (g:Gene)-[:Gene_has_tcdb_family]->(t:TcdbFamily)
WHERE NOT EXISTS {
  MATCH (g)-[:Gene_has_tcdb_family]->(d:TcdbFamily)
  WHERE (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(t)
}
```

- `Gene.transported_metabolite_count` + `transport_substrate_resolution` — post-import.cypher L1227–1253
- `Metabolite.transporter_gene_count` — L1374–1386
- `Organism_has_metabolite` transport arm → `OrganismTaxon.transported_metabolite_count` + edge `evidence_sources` — L1434–1468

Rationale (contract §7.3): 6,950 genes are attached at both an ancestor and its own descendant (e.g. `3.A.1` *and* `3.A.1.14`); unioning across all attachments pulled in the superfamily's full rollup despite a more specific call existing. Restricting to deepest keeps 99.7 % of genes and takes p90 from 554 → 97. The KG doc promises that `Gene.transported_metabolite_count` and `Metabolite.transporter_gene_count` "agree by construction — two projections of one (gene, metabolite) set."

### What breaks if GBM / MBG walk all `Gene_has_tcdb_family` edges

1. **`list_metabolites.transporter_gene_count` ≠ distinct genes in `genes_by_metabolite` rows** for any metabolite reached through a superseded ancestor edge. The spec's own live figure demonstrates it: *"49 MED4 `resolved` genes reach nitrite only via inherited `3.A.1` edges."* A `resolved` gene has a non-lumping deepest attachment; where that attachment sits under `3.A.1`, the `3.A.1` edge is superseded and the gene is **not** in the KG's nitrite `transporter_gene_count`. The "per-row and per-gene trust are different facts" observation in decision 1 is partly *this* predicate, not only `substrate_depth`.
2. **`gene_overview.transported_metabolite_count = 13` for PMM0392** will not match the distinct metabolites in its `metabolites_by_gene` rows if PMM0392 carries any ancestor+descendant pair.
3. **Explorer-traversed `evidence_sources` (`'transport' ∈ …`)** will disagree with `Organism_has_metabolite.evidence_sources` for the same (organism, metabolite) pairs.
4. The GBM auto-warning threshold ("`inherited` dominates transport rows") is inflated by superseded rows — exactly the rows the KG already decided not to count.

### Live verification (2026-08-26, alpha.7 build via MCP `run_cypher`)

Each query compares the all-edges traversal (what the spec's row queries imply) with the same traversal under the KG's deepest-attachment predicate.

| Case | all edges | deepest only | KG scalar |
|---|---|---|---|
| **PMM0392** (the spec's acceptance gene) — distinct metabolites in MBG rows | **554** | 13 | `transported_metabolite_count = 13`, `resolved` |
| PMM0392 families | `3.A.1` + `3.A.1.25/.28/.30/.32/.33` | the five subfamilies | — |
| **nitrite × MED4** — distinct genes in GBM rows | 63 | 27 | — |
| nitrite × MED4 — transport rows | 68 | 29 (39 superseded; all 39 are `inherited` via `3.A.1`) | — |
| **All metabolites** — `transporter_gene_count` vs distinct genes in all-edges rows | differ on **1,323 / 1,432** transported metabolites; 1.49 M excess (gene, metabolite) links; max +3,251 genes on one metabolite | — | — |

PMM0392 is decisive: under all-edges semantics `gene_overview` says 13 while `metabolites_by_gene` returns 554 rows-worth of metabolites for the same gene — the single `3.A.1` superfamily attachment, superseded by five subfamily calls, reintroduces the entire ABC rollup the KG's count was redesigned to exclude. Acceptance item 4 as written would pass while the drill-down contradicts it.

### Options (KG preference order)

- **(a) Apply the same `NOT EXISTS` predicate on the transport arm of GBM/MBG** (and the traversal that computes `evidence_sources`). Rows and the new count columns become projections of one set, which is the KG's stated design. Cost: one predicate per transport-arm MATCH; the `*1..4` variable-length exists-check is bounded (TCDB is 5 levels).
- **(b) Keep all rows, add a row field** e.g. `tcdb_attachment: deepest | superseded`, and state in every count-field description that counts use `deepest`. Preserves recall for users who want to see the ABC-superfamily row, keeps the discrepancy explainable.
- **(c) Document the discrepancy only.** Shipping without at least (c) silently breaks the by-construction agreement the KG contract advertises.

Whichever is chosen, acceptance item 4 should add a cross-check: `size(distinct genes in genes_by_metabolite(nitrite, MED4))` vs `list_metabolites` `transporter_gene_count` for nitrite (currently expected to *differ* under all-edges semantics — the spec should decide whether that is acceptable).

---

## 2. WORDING — `most_specific` is not "substrate-curated"

Decision 1 calls nitrite via `2.A.16` "genuinely substrate-curated". The KG says the opposite, in three places:

- contract §7.1: *"This is **not** 'curated vs inherited' — only `tc_specificity` nodes own `substrate_classes` … curated-vs-inherited is already exactly `level_kind = 'tc_specificity'`. Depth is the part that needed materialising."*
- adapter docstring (`_compute_substrate_depth`): most_specific ⇔ *no **kept** child carries the substrate* — relative to the **pruned** set.
- vocab description: *"most_specific = no kept child of this node carries the same substrate."*

Nitrite entered `2.A.16` from some `2.A.16.x.x` specificity node in the full hierarchy; it is `most_specific` at the family only because no gene here annotates below it. Consumers who read the field as curation depth will over-trust family-level rows. **Ask:** field description = "the most specific *surviving* transporter node for this substrate (relative to the gene-pruned hierarchy)"; drop "curated" from the rationale text.

---

## 3. WORDING — `resolved` means "at least one", not "all"

```cypher
g.transport_substrate_resolution =
  CASE WHEN n_deepest = 0 THEN null
       WHEN any(x IN breadth WHERE x = false) THEN 'resolved'
       ELSE 'family_inferred' END
```

`resolved` fires when **any** deepest attachment is non-lumping. A gene deepest-attached at both `2.A.16` and `3.A.1` is `resolved` and still carries `3.A.1`'s 554-substrate rollup inside its `transported_metabolite_count`. The BKM "read the score; if `resolved`, drill into substrates" is correct; the MBG gene-anchored warning and the `metabolites.md` trust-ladder paragraph should not imply that `resolved` ⇒ clean breadth. Per-row `substrate_depth` (plus §1's attachment axis) is what separates the `2.A.16` row from the `3.A.1` rows on such a gene. One sentence suffices.

---

## 4. Minor / for the record

- **Removing `gene_overview.transporter_count` (= `Gene.tcdb_family_count`)** loses call multiplicity. `tcdb_evidence_score_max` carries no count, and 9,792 of 30,076 TCDB genes (32.6 %) hold several calls at different scores. Fine if deliberate; consider keeping `tcdb_family_count` as a routing column under its KG name rather than deleting the concept.
- The KG contract's `coalesce(…, -1.0)` guidance is for Cypher total-ordering only; the spec's "null, never coalesced" at the API surface is the correct consumer-facing rule and does not conflict.
- `transport_substrate_resolution` being **not** tier-gated (11,871 `resolved` genes are tier-3-only) is correctly relied on by the MBG warning; no change.
- The §9 append about the `3.A.1.4.4` name truncation (`"The high-affinity ("`) is acknowledged as a KG-side scrape fix (citation-stripper cuts at an unbalanced open paren); tracked separately, not a blocker.

---

## 5. Requested changes before freeze

1. Decide §1 (a / b / c) and reflect it in the GBM/MBG query sites, the count-field descriptions, and acceptance item 4.
2. Reword `substrate_depth` per §2.
3. Add the one-sentence `resolved` caveat per §3.

No KG-side asks arise from this review.

---

## 6. Explorer response (2026-08-26) — all three requested changes applied in spec v3

- **§1 → option (a), adopted.** Reproduced the review's figures live before deciding (nitrite × MED4: 68→29 rows / 63→27 genes, 39 superseded all `inherited` via `3.A.1`; PMM0392: 554→13 = `transported_metabolite_count`, deepest families `3.A.1.{25,28,29,30,31,32,33}` — seven, not five; nitrite all-organism deepest genes 2,318 = `transporter_gene_count`). The `NOT EXISTS` predicate is applied on every transport-arm traversal in both drill-downs *and* on the `gene_overview` `evidence_sources` / `has_chemistry` traversal, so rows, envelope counts and the KG's scalars are projections of one set. Option (b)'s extra row field rejected (fewer-fields decision; ancestor membership stays visible via `gene_ontology_terms(ontology='tcdb')`). Acceptance gained an explicit cross-tool agreement item (spec acceptance 5), encoded as integration tests. The predicate ran sub-second on every verification query.
- **§2 applied.** `substrate_depth` field description and the decision-1 rationale now say "most specific *surviving* node relative to the gene-pruned hierarchy — not a curation level"; "curated" removed.
- **§3 applied.** New design decision 5 records `resolved` = at-least-one; the MBG warning and the `metabolites.md` trust-ladder paragraph carry the one-sentence caveat.
- **§4 — `transporter_count` removal stands, with a sharper reason your §1 supplies:** `tcdb_family_count` counts superseded ancestors too (PMM0392: 8 edges, 7 deepest), so it is the wrong multiplicity under the deepest-attachment rule. If call multiplicity is wanted later, the right shape is a KG-precomputed deepest-attachment count — a future ask, not this column.
- No KG-side asks arise. The `3.A.1.4.4` name truncation stays tracked KG-side.
