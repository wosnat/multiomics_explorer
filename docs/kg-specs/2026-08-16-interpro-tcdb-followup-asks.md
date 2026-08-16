# KG-side asks: InterPro + TCDB — followup batch (vocabulary-contract review)

**Date:** 2026-08-16
**Predecessor (delivery snapshot):** [docs/kg-specs/2026-08-16-interpro-tcdb-asks.md](2026-08-16-interpro-tcdb-asks.md) — frozen as the original delivery (KG-IPT-001…008)
**Driver (this batch):** explorer review of the KG-side design
`multiomics_biocypher_kg/docs/superpowers/specs/2026-08-16-vocabulary-contract-design.md`
**Verified against:** KG `0.0.0-dev`, `built_at 2026-08-13T12:19:46.858Z`
**Status:** 7 Live asks — 3× P2, 2× P3 live; KG-IPT-009 + KG-IPT-013 **resolved by the
KG at design rev 4–5** (property deleted rather than renamed). ID numbering continues from
KG-IPT-008. Reviewed through **design rev 5** — round 2 in §4b, round 3 in §4c.

---

## 1. Review verdict

**The vocabulary-contract design is approved from the explorer side.** The four house
rules (R1–R4) are well-argued, the `ControlledVocabulary` node shape covers what
KG-IPT-001 asked for, and `applies_to` making the `evidence` subsetting *structural*
rather than a prose caveat is exactly the right resolution.

Three of its claims were independently verified against the deployed graph and hold:

| Claim | Verification |
|---|---|
| §7.2 — InterPro GO xrefs already landed as Layer B on existing edges | **confirmed**, and reconciles exactly — see §2 |
| §9.4 — `interpro` excluded from `informative_annotation_types` | `0` genes carry it |
| §2.2 — `TcdbFamily.is_promiscuous` read by nothing in the explorer | `0` references (matches our own audit) |

The asks below are what the review surfaced. **KG-IPT-009 is a genuine defect** — the
first found on this integration — and it sits inside the v1 contract seed, so it should
be fixed before the vocabulary is frozen.

---

## 2. Accepted correction: KG-IPT-005 premise was wrong

The design's §7.2 is correct and the explorer accepts it in full.

Our KG-IPT-005 concluded from `db.relationshipTypes()` that InterPro→GO xrefs had not
landed. That method structurally cannot see them, because Layer B created **no new
relationship type** — it enriched the existing GO edges. The magnitude reconciles
exactly with the `+45,226` figure in `interpro-two-layer.md`:

```cypher
MATCH ()-[r:Gene_involved_in_biological_process]->() RETURN r.evidence AS e, count(*) AS n
// repeated for _enables_molecular_function and _located_in_cellular_component
```

| Edge | `curated` | inferred (`family_` + `domain_`) |
|---|---|---|
| `Gene_involved_in_biological_process` | 524,173 | 15,700 |
| `Gene_enables_molecular_function` | 334,451 | 23,711 |
| `Gene_located_in_cellular_component` | 146,370 | 5,815 |
| **total inferred** | | **45,226** |

**Consequence, as the design states:** the `sources` / `evidence` shape on GO edges is
final this release. The explorer will build provenance surfacing against it now rather
than deferring it. No KG action required — recorded so the correction is not lost.

What remains genuinely deferred (unchanged): InterPro MetaCyc **pathway** xrefs, and any
`Interpro_entry_related_to_go` Layer-A router.

---

## 3. Ask summary table

| ID | Category | Pri | Consumer / impact |
|---|---|---|---|
| KG-IPT-009 | **Defect** | **P1** | Layer-A router safety flag is uniformly false — **RESOLVED at rev 4 by deletion** |
| KG-IPT-010 | R1 compliance + seed gap | P2 | `Gene_has_interpro_entry.libraries` — 13 UPPERCASE values, not in the seed |
| KG-IPT-011 | Contract shape | P2 | `sources` domain differs per edge type; do not collapse the seed entry |
| KG-IPT-012 | Contract text | P3 | R4 float→integer recovery instruction is unsafe as written |
| KG-IPT-013 | **Round 2** — naming | P2 | `xref_specificity` names only one arm of a two-arm rule; wrong on 1,922 edges — **RESOLVED at rev 4 by deletion** |
| KG-IPT-014 | **Round 3** — contract | P3 | Deleted breadth thresholds now live only in prose; publish as advisory contract metadata |
| KG-IPT-015 | **Round 3** — hidden coupling | P2 | Inlined TCDB threshold silently drives the public `transport_substrate_resolution` enum |

---

## 4. Per-ask detail

### KG-IPT-009 — `ambiguous` is `false` on 100% of Layer-A router edges (P1, defect)

**Ask:** Fix the `ambiguous` computation before seeding it into the controlled-vocabulary
contract.

`interpro-two-layer.md` defines the flag as `true` = multi-term entry **or** non-FAMILY
type. The deployed graph has it `false` everywhere, on both router edge types.

**Why this matters more than a normal dead flag:** the Layer-A routers are explicitly
recall-biased and the docs are emphatic that they must never be read as annotation
(`~31%` reverse precision on the TCDB analogue). `ambiguous` is the field standing
between a router edge and a consumer treating it as a functional claim. Uniformly false,
it silently asserts that every router edge is unambiguous — the opposite of the intended
guardrail.

The design's §5.3 seeds `Layer-A ambiguous / source_db` into the v1 contract. Publishing
now would freeze `values: [true, false]` around a property that is never `true`, and the
kg-validity "declared − observed ⊆ expected_empty" gate (§6) would then either fail or
have to whitelist the bug.

**Verified state (2026-08-16):**

```cypher
MATCH ()-[r:Interpro_entry_related_to_ec_number]->() RETURN r.ambiguous AS amb, count(*) AS n
```
→ `false` 6,854 of 6,854

```cypher
MATCH ()-[r:Interpro_entry_related_to_cazy_family]->() RETURN r.ambiguous AS amb, count(*) AS n
```
→ `false` 122 of 122

The graph contradicts the documented rule on its own data — **3,863 of 6,854** EC router
edges originate from non-FAMILY entries, every one of which should be `true`:

```cypher
MATCH (n:InterproEntry)-[r:Interpro_entry_related_to_ec_number]->()
RETURN n.interpro_type AS t, r.ambiguous AS amb, count(*) AS n ORDER BY n DESC
```
→ FAMILY 2,991 · DOMAIN 2,261 · HOMOLOGOUS_SUPERFAMILY 994 · CONSERVED_SITE 369 ·
ACTIVE_SITE 147 · BINDING_SITE 72 · REPEAT 12 · PTM 8 — all `amb: false`

And **1,110 entries** carry multiple EC xrefs (the other `true` arm):

```cypher
MATCH (n:InterproEntry)-[r:Interpro_entry_related_to_ec_number]->()
WITH n, count(r) AS k WHERE k > 1 RETURN count(n) AS entries_with_multiple_ec, max(k) AS mx
```
→ 1,110 entries, max 14 ECs on one entry

**Acceptance criteria:**
- `ambiguous = true` on router edges from non-FAMILY entries and on edges from entries
  carrying more than one xref of that type.
- A kg-validity assertion that `ambiguous` is not single-valued across the router edges.
- Contract seeded only after the fix, so `values: [true, false]` is truthful.

**Not blocking the explorer.** Layer-A routers are deferred explorer-side (workstream
W3); this is raised because the contract freeze is imminent, not because we consume it.

---

### KG-IPT-010 — `Gene_has_interpro_entry.libraries` violates R1 and is missing from the seed (P2)

**Ask:** Apply R1 (lowercase `snake_case`) to `libraries`, and add it to the §5.3 v1 seed
as `value_type: string_array`.

It is a 13-value closed vocabulary, all UPPERCASE — the identical problem R1 fixes for
`interpro_type`, and unreleased, so free under §2.2.

**Why it is worth seeding rather than leaving to a later release:** `libraries` is the
member-DB granularity of the `signature`-vs-inferred distinction. "InterPro entries
backed by a direct Pfam HMM hit" is exactly how a user asks for method-independent
corroboration of an eggNOG-transferred annotation, which is the stated headline value of
the whole InterProScan integration. It is a natural filter axis for the explorer's
InterPro surface, and it is closed and small.

**Verified state (2026-08-16):**

```cypher
MATCH ()-[r:Gene_has_interpro_entry]->() UNWIND r.libraries AS l
RETURN l AS lib, count(*) AS n ORDER BY n DESC
```

| value | edges | | value | edges |
|---|---|---|---|---|
| `PFAM` | 141,658 | | `CDD` | 27,093 |
| `SUPERFAMILY` | 88,622 | | `HAMAP` | 24,511 |
| `GENE3D` | 79,515 | | `PROSITE_PATTERNS` | 22,783 |
| `PANTHER` | 59,645 | | `PIRSF` | 14,543 |
| `NCBIFAM` | 43,020 | | `PRINTS` | 14,220 |
| `PROSITE_PROFILES` | 33,813 | | `SFLD` | 1,646 |
| `SMART` | 27,191 | | | |

**Acceptance criteria:** values lowercased (`pfam`, `superfamily`, `gene3d`, `panther`,
`ncbifam`, `prosite_profiles`, `smart`, `cdd`, `hamap`, `prosite_patterns`, `pirsf`,
`prints`, `sfld`), declared as a `ControlledVocabulary` node with `closed: true`.

---

### KG-IPT-011 — `sources` domain differs per edge type; do not collapse the seed entry (P2)

**Ask:** Seed `sources` as one `ControlledVocabulary` node **per edge type**, exactly as
`evidence` is, rather than as a single shared "gene→ontology `sources`" entry.

§5.2 argues the per-`applies_to` structure specifically for `evidence`, and §5.3 lists
`sources` as a single item. The measured domains are not uniform: `ncbi` appears **only**
on the GO edges.

**Why:** this is the same failure mode §5.2 exists to prevent. A shared node would offer
`ncbi` as a valid `sources` filter on a CAZy query where it can never match, and the
empty result reads as "no NCBI-sourced CAZy annotations exist" rather than "NCBI does not
contribute to this edge at all". The node-id scheme (`<applies_to>.<property>`) already
handles this structurally — this is only about not collapsing the seed.

**Verified state (2026-08-16):**

```cypher
MATCH ()-[r:<EDGE>]->() UNWIND r.sources AS s RETURN collect(DISTINCT s) AS srcs
```

| Edge type | `sources` domain |
|---|---|
| `Gene_has_cazy_family` | `eggnog, interpro` |
| `Gene_catalyzes_ec_number` | `cyanorak, eggnog, interpro, uniprot` |
| `Gene_has_pfam` | `cyanorak, eggnog, interpro, uniprot` |
| `Gene_involved_in_biological_process` | `cyanorak, eggnog, interpro, ncbi, uniprot` |

(Values shown pre-R2; after R2 `interpro` → `interproscan`.)

**Acceptance criteria:** one node per (edge type, `sources`) pair, each carrying only the
values that edge type actually admits.

---

### KG-IPT-012 — R4's integer-recovery instruction is unsafe as written (P3)

**Ask:** Change the published description from *"multiply by `signal_count` for the raw
count"* to *"`round(score × signal_count)`"*.

**Why:** with 3-decimal rounding, `0.333 × 3 = 0.999`. A consumer truncating rather than
rounding recovers **0** instead of **1** — the worst case, since it silently converts the
weakest positive evidence into no evidence. The string is published inside the contract
and will be read literally by an LLM, which will not infer the rounding.

The same applies to the 5-signal scale where recovery is exact (`0.6 × 5 = 3.0`), so the
instruction is only unsafe on the 3-signal edges — which is most of them.

**On R4 itself:** the explorer finds the normalization argument persuasive. The failure
mode it removes (a consumer comparing a Pfam `3` to a TCDB `3` and being wrong by a
factor) is real, and publishing `signal_count` keeps the integer recoverable. No
objection to the change — only to the recovery instruction.

**Acceptance criteria:** the `description` on every `evidence_score`
`ControlledVocabulary` node specifies rounding explicitly.

---

## 4b. Round-2 review of design rev 2 (2026-08-16)

Rev 2's §0 asked for a re-check rather than a skim. Done. **R5 is endorsed, and its
central diagnostic claim is independently confirmed** — but the KG-IPT-009 replacement
name is not truthful, which is KG-IPT-013 below.

### R5's diagnosis verified

The claim "adapter-emitted `bool` is broken; post-import `bool` is not" holds exactly.
The schema carries **7** `bool` (entity, property) pairs across 5 distinct names — rev 2's
§9.1 table omits the two `is_promiscuous` pairs, which are post-import and *work*,
strengthening the case:

| Set by | Property | Live distribution | State |
|---|---|---|---|
| post-import | `agrees_across_sources` | 21,684 true / 32,079 false | fine |
| post-import | `pfam_corroborated` | 23,634 / 30,129 | fine |
| post-import | `go_corroborated` | 26,885 / 26,878 | fine |
| post-import | `TcdbFamily.is_promiscuous` | 13 true | fine |
| post-import | `InterproEntry.is_promiscuous` | 22 true | fine |
| **adapter** | `ambiguous` (×2 router edges) | **6,976 false, 0 true** | **broken** |

One honest caveat: the causal claim rests on a single adapter-emitted property, since
`ambiguous` is the only one. The prior is strong (it is the documented reason
`substrate_depth` and `rankable` are already strings) and **the fix is correct either
way**, because R5 removes the category rather than repairing it. Noted only so the
evidence base is not overstated as broader than one property.

### R3 tiers, R4 rounding, R5 itself — endorsed

No further comment. The `gene_breadth` / `substrate_breadth` reframing is a genuine
improvement over the flags we approved in rev 1: `is_multi_gene` firing at
`gene_count >= 1000` really did have no truthful negative, and a tier vocabulary leaves
room for the middle band §10.3 contemplates.

---

### KG-IPT-013 — `xref_specificity` names only one of the flag's two arms (P2)

**Ask:** Do not rename `ambiguous` to `xref_specificity: one_of_several | sole_xref`.
The name describes only the multiplicity arm of a rule that has two.

The computation rev 2 quotes and preserves is:

```python
amb = len(ecs) > 1 or etype != "FAMILY"     # interpro_adapter.py:388
```

That is a disjunction over **two orthogonal facts** — *this entry carries several xrefs*
and *this entry is not family-level*. `one_of_several` states the first. For edges
flagged only by the second arm it is simply false: the entry has exactly one EC xref, so
that xref **is** the sole xref, and the row would assert the opposite.

**Magnitude — 39.5% of flagged edges would be mislabeled:**

```cypher
MATCH (n:InterproEntry)-[r:Interpro_entry_related_to_ec_number]->()
WITH n, count(r) AS ec_k
RETURN sum(CASE WHEN ec_k>1 AND n.interpro_type='FAMILY'  THEN ec_k ELSE 0 END) AS multi_family,
       sum(CASE WHEN ec_k>1 AND n.interpro_type<>'FAMILY' THEN ec_k ELSE 0 END) AS multi_nonfamily,
       sum(CASE WHEN ec_k=1 AND n.interpro_type<>'FAMILY' THEN 1 ELSE 0 END)    AS sole_nonfamily,
       sum(CASE WHEN ec_k=1 AND n.interpro_type='FAMILY'  THEN 1 ELSE 0 END)    AS sole_family
```

| Arm | Edges | Correct under `ambiguous` | Correct under `one_of_several`? |
|---|---|---|---|
| multi-xref, FAMILY | 1,002 | true | yes |
| multi-xref, non-FAMILY | 1,941 | true | yes |
| **sole xref, non-FAMILY** | **1,922** | true | **no — it is the sole xref** |
| sole xref, FAMILY | 1,989 | false | yes (`sole_xref`) |

Flagged total **4,865**; 1,922 of them (39.5%) would carry a value contradicting their own
data. This is worse than the defect it replaces: `ambiguous` was uninformative, whereas
`one_of_several` would be actively wrong on a large minority — and it is published in a
controlled-vocabulary contract that asserts the value set is meaningful.

**Recommended fix — split the axes rather than rename the fusion.** The type arm is
*already* on the graph: the edge's source is an `InterproEntry` carrying `interpro_type`.
So the edge only needs to carry the fact that is not otherwise recoverable:

```
Interpro_entry_related_to_{ec_number,cazy_family}.xref_multiplicity:
    one_of_several | sole_xref        # len(xrefs) > 1, and nothing else
```

A consumer wanting the old `ambiguous` writes it explicitly, and can see which arm fired:

```cypher
MATCH (n:InterproEntry)-[r:Interpro_entry_related_to_ec_number]->(e:EcNumber)
WHERE r.xref_multiplicity = 'sole_xref' AND n.interpro_type = 'family'   // the clean 1:1 case
```

This is R5-compliant, strictly more informative, and each value is true of every row
carrying it. **Minimal-change fallback** if splitting is unwanted: keep the fusion but
name it for the consequence rather than one cause — e.g.
`xref_precision: imprecise | precise` — so no row asserts a fact contradicted by its own
entry.

**Acceptance criteria:** every value in the shipped vocabulary is true of every row that
carries it. Under the recommended fix: `one_of_several` = 2,943 · `sole_xref` = 3,911 on
the EC router (multiplicity arm only).

**Also correcting our own earlier figure:** the §6 entry criterion said "≥ 3,863 true".
The exact expected flagged count under the current `ambiguous` semantics is **4,865**
(3,863 non-FAMILY + 1,002 multi-xref FAMILY). §6 is updated.

---

## 4c. Round-3 review of design rev 5 (2026-08-16)

**Rev 5's derivability principle — "materialize traversals, not predicates" — is endorsed,
and it produced a better resolution than the one we proposed.** Deleting `ambiguous`
outright resolves KG-IPT-009 and KG-IPT-013 together; our recommended split
(`xref_multiplicity`) was still carrying a denormalized entry-level fact onto every edge.
Deleting `source_db` (a hardcoded constant) is obviously right. §4 and §5.3 are
internally consistent with the deletions — checked.

**Withdrawn objection.** We were going to raise that post-pruning out-degree is *not*
equivalent to the adapter's pre-pruning `len(ecs) > 1`, so the multiplicity arm is not
strictly derivable. §9.8 pre-empts it and the rebuttal is convincing: the pruned ECs are
the obsolete/invalid tokens Expasy has no node for, so if an entry lists 23 ECs and 22
are dead, the survivor is the only valid claim and flagging it "one of several" would be
wrong. Post-pruning out-degree is better semantics, not degraded semantics. No further
comment.

Two consequences of the deletions need recording — KG-IPT-014 and KG-IPT-015 below.
Neither argues for resurrecting a flag.

### KG-IPT-014 — publish the deleted thresholds as contract metadata (P3)

**Ask:** Seed `InterproEntry.gene_count` and `TcdbFamily.metabolite_count` as
`ControlledVocabulary` entries carrying the KG's cutoff in `description` (the node shape
already supports `min_value` / `max_value` / `description`).

**We agree with the deletion.** For the explorer's actual use — InterPro ORA — a
continuous `gene_count` is strictly better than a bit: we would rather down-weight by
magnitude than threshold at someone else's cutoff, and §3 R3 is right that a stored
threshold hides that a judgement was made.

**But the judgement itself is real editorial knowledge, and deletion leaves it only in
prose.** "`gene_count >= 1000` is where ubiquity begins for this corpus" and
"`metabolite_count >= 50` at `level >= 2`" are calibrated against this graph. After rev 5
they live in a design doc and `CLAUDE.md` — nowhere the explorer can read. Any consumer
wanting those exact sets hardcodes `1000`, which is precisely the hardcode-and-drift
failure §1's closing paragraph names as the reason the contract exists.

Publishing them as advisory metadata costs one seed entry each, keeps them versioned and
drift-detectable via `controlled_vocabularies_hash`, and does not resurrect the flag —
the value stays a count, and the cutoff stays advisory.

**Verified state (2026-08-16):** both predicates reproduce their sets exactly —
`level >= 2 AND metabolite_count >= 50` → 13 families; `gene_count >= 1000` → 22 entries.

---

### KG-IPT-015 — inlining the TCDB threshold creates a hidden coupling to a public enum (P2)

**Ask:** Record in `tcdb-two-source-upgrade.md` that recalibrating the TCDB breadth
threshold is a **`### Breaking`** change, because it silently moves genes between
`resolved` and `family_inferred`. Quantify the shift when it happens.

§3 R3 inlines `metabolite_count >= 50 AND level >= 2` into `post-import.cypher:1131`,
where it computes `Gene.transport_substrate_resolution`. §10.3 separately defers
recalibrating that threshold, noting `CLAUDE.md` flags it as due.

Those two decisions interact. **Before rev 5 the coupling was visible** — `is_promiscuous`
was a named property you could see feeding the resolution. Inlining hides it, and the
downstream property is one the MCP is about to publish as a public enum (KG-IPT-002
settled `resolved` as final, and the explorer retires `substrate_confirmed` to adopt it).
So a change §10.3 frames as deferred cosmetics would land as a semantic shift in a
published MCP value.

**The sensitivity is not small.** The entire `family_inferred` class rests on 13 families,
and the next band down holds nearly twice as many genes:

```cypher
MATCH (t:TcdbFamily) WHERE t.level >= 2
RETURN sum(CASE WHEN t.metabolite_count >= 50 THEN 1 ELSE 0 END) AS ge50,
       sum(CASE WHEN t.metabolite_count >= 25 AND t.metabolite_count < 50 THEN 1 ELSE 0 END) AS band25_50
```
→ `ge50` **13** · `band25_50` **25**

```cypher
MATCH (g:Gene)-[:Gene_has_tcdb_family]->(t:TcdbFamily)
WHERE t.level >= 2 AND t.metabolite_count >= 25 AND t.metabolite_count < 50
RETURN count(DISTINCT g) AS genes_touching_band
```
→ **2,750 genes**, against a current `family_inferred` class of **1,671**

Dropping the cutoff from 50 to 25 roughly triples the candidate pool for
`family_inferred`. That is a headline-grade change to a published enum, not a threshold
tweak.

**Acceptance criteria:** a note beside the inlined threshold, and in
`tcdb-two-source-upgrade.md`, stating that the cutoff is load-bearing for
`transport_substrate_resolution` and that changing it requires a `### Breaking` bullet
plus a before/after count of the two classes.

---

## 5. Minor observations (no action requested)

- **`tcdb-two-source-upgrade.md` §2's score distribution is stale** vs the deployed
  build: doc says `0 → 17,422 · 5 → 1,081`, graph has `0 → 17,045 · 1 → 8,599 ·
  2 → 9,461 · 3 → 7,541 · 4 → 9,957 · 5 → 1,160`. Drift from the 2026-08-13 rebuild.
  Worth refreshing while that doc is being edited anyway — it will be re-scaled to floats
  by R4 regardless.
- **`source_db` is degenerate** — `interpro.xml` on 100% of the 6,976 router edges. Fine
  to declare; noted so a single-valued vocabulary is not mistaken for a harvest error.
- **`Gene.tcdb_evidence_score_max` sparseness under normalization** —
  `tcdb-two-source-upgrade.md` §2 advises `coalesce(..., -1)` when a total order is
  required. Now that the property is a float in `[0,1]` and `0.0` is a legitimate value,
  that guidance needs a float sentinel (`-1.0`). Doc-only.
- **§9.3 threshold recalibration deferral** — the explorer agrees, for the reason the
  design gives: an unreadable `post-import-validate` diff would cost more than a better
  threshold, and that diff is the only evidence the renames changed nothing else.

---

## 6. Sequencing — AGREED 2026-08-16

Not an ask — a coordination item, recorded so it is not resolved by accident.
**Agreed by both sides on 2026-08-16: the explorer proceeds once the updated KG lands.**

§4 of the design renames `substrate_depth`: `deepest` → `most_specific`. The explorer's
W4 regression fix for `transport_confidence` reads exactly that property, and today
neither value is safe to build against: `deepest` guarantees breakage at the coordinated
release, and `most_specific` exists in no deployed build, so it cannot be tested or
fixtured.

`mcp_min_version` protects old-MCP-against-new-KG, but not the reverse — which is
precisely the window the explorer would be developing in.

**Agreed order:**

1. KG lands the §4 renames + the KG-IPT-009 fix, and redeploys.
2. Explorer implements W1 (InterPro ontology) + W4 (regression fixes) against the
   renamed graph.
3. Coordinated KG + MCP release.

The explorer's design spec is written against the **post-rename** vocabulary throughout,
so only implementation is gated on step 1.

**Explorer-side entry criteria for step 2** — the checks to run against the redeployed
build before implementation starts:

**Revised 2026-08-16 for design rev 2 (R5 removes native `bool`).** The three
boolean-reading queries below are rewritten per the mapping in the design's §9.1.

```cypher
// renames landed
MATCH ()-[r:Tcdb_family_transports_metabolite]->() RETURN r.substrate_depth AS d, count(*) AS n
//   expect: most_specific 4,381 · inherited 6,882   (no 'deepest' / 'ancestor')
MATCH (n:InterproEntry) RETURN DISTINCT n.interpro_type
//   expect: lowercase snake_case, 8 values
MATCH ()-[r:Gene_has_interpro_entry]->() UNWIND r.libraries AS l RETURN DISTINCT l
//   expect: lowercase, 13 values
// breadth flags DELETED at rev 5 — assert absence, and check the predicates still select the same sets
MATCH (t:TcdbFamily) WHERE t.is_promiscuous IS NOT NULL RETURN count(*)   // expect 0
MATCH (n:InterproEntry) WHERE n.is_promiscuous IS NOT NULL RETURN count(*) // expect 0
MATCH (t:TcdbFamily) WHERE t.level >= 2 AND t.metabolite_count >= 50 RETURN count(*)  // expect 13
MATCH (n:InterproEntry) WHERE n.gene_count >= 1000 RETURN count(*)                    // expect 22

// R5: no native bool anywhere
MATCH ()-[r:Gene_has_tcdb_family]->()
RETURN r.source_agreement AS agree, r.pfam_support AS pfam, r.go_support AS go, count(*) AS n
//   expect: both_sources 21,684 / single_source 32,079 · corroborated 23,634 / 26,885

// KG-IPT-009 + 013 resolved by DELETION at rev 4-5 — router edges carry no properties
MATCH ()-[r:Interpro_entry_related_to_ec_number]->()   RETURN DISTINCT keys(r) AS k  // expect [] (or ['id'])
MATCH ()-[r:Interpro_entry_related_to_cazy_family]->() RETURN DISTINCT keys(r) AS k  // expect [] (or ['id'])
//   edge counts unchanged: 6,854 EC · 122 CAZy

// contract present
MATCH (v:ControlledVocabulary) RETURN count(v) AS n
MATCH (s:Schema_info) RETURN s.controlled_vocabularies_hash IS NOT NULL AS stamped
```

Structural counts that must be unchanged by the rename pass (rollup drift regression):
`InterproEntry` 12,999 · `Gene_has_interpro_entry` 397,342 · `TcdbFamily` 1,515 ·
`Gene_has_tcdb_family` 53,763 · `Tcdb_family_transports_metabolite` 11,263 ·
GO inferred edges 45,226.
