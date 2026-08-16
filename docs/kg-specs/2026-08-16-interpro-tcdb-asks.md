# KG-side asks: InterPro + TCDB two-source integration

**Date:** 2026-08-16
**Driver:** explorer-side integration of `docs/kg-changes/{interproscan-extension,
interpro-two-layer, tcdb-two-source-upgrade}.md` + CHANGELOG `[Unreleased]`
**Verified against:** KG `0.0.0-dev`, `built_at 2026-08-13T12:19:46.858Z`
**Status:** ANSWERED — all 7 addressed by the KG-side design
`multiomics_biocypher_kg/docs/superpowers/specs/2026-08-16-vocabulary-contract-design.md`.
Frozen as the original delivery snapshot; asks surfacing after it continue in
[2026-08-16-interpro-tcdb-followup-asks.md](2026-08-16-interpro-tcdb-followup-asks.md)
(KG-IPT-009 onward). **Note:** KG-IPT-005's premise was incorrect and is corrected in
§2 of the followup — InterPro GO xrefs *did* land, as Layer B enrichment on the existing
GO edges.

Originally: 7 Live asks — 2× P1, 3× P2, 2× P3. 1 Deferred (not requested now).

Release-process items (`mcp_min_version` bump, version/`deployment_role` stamping,
`release_highlights` population, build pinning) are **out of scope for this doc** —
they are handled as part of the coordinated KG + MCP release.

---

## 1. Pre-flight: no KG defects found

Before raising asks, 37 invariant checks were run against the deployed build. **All
pass.** This batch contains **zero defect reports** — every ask below is a contract,
naming, or documentation item.

| Family | Checks | Result |
|---|---|---|
| InterPro rollups — `InterproEntry.{gene_count, member_count, organism_count, is_promiscuous}`, `Gene.interpro_entry_count`, `'interpro' ∈ annotation_types` ↔ edge presence | 6 | exact |
| InterPro structure — level ↔ parent-edge coherence, 100% within-type is-a, no dup gene→entry edges, `start <= end`, `match_count >= 1`, non-empty `libraries`, no orphan entries, no dup Pfam-bridge pairs | 8 | clean |
| TCDB rollups — `Gene.tcdb_family_count`, `tcdb_best_evidence_score` = max(edge score), `Metabolite.transporter_count` = distinct `deepest` sources, `level` ↔ `level_kind`, no orphan families | 5 | exact |
| TCDB contracts — `sources` sorted, `tier` absent on all eggNOG-only edges, `transport_substrate_resolution` sparse exactly on TCDB-annotated genes, no metabolite reachable only via `ancestor` | 4 | hold |
| Provenance vocabulary — `evidence_score ∈ 0..3`, `evidence='signature'` only on Pfam, inferred evidence ⇒ `interpro ∈ sources`, `sources` sorted | 4 | hold |
| DerivedMetric — `flag_true_count` drift, `total_gene_count` = true + false | 2 | exact |
| Misc — `annotation_quality ∈ 0..3`, no empty `treatment_type`, no null `control`, no null `publication_year` | 4 | clean |

The biller 2016 contrast correction is verified landed: both `ismej.2016.82` MIT1002
experiments carry `control = "12 hours after co-culturing with Prochlorococcus NATL2A"`,
`treatment_type = ['growth_phase']`, `background_factors = ['light', 'coculture']`.

---

## 2. Ask summary table

| ID | Category | Pri | Explorer consumer |
|---|---|---|---|
| KG-IPT-001 | Contract surface | **P1** | `list_filter_values`, every ontology-tool `Literal` type — controlled vocabularies as data |
| KG-IPT-002 | Naming decision | **P1** | `transport_confidence` enum on `genes_by_metabolite` / `metabolites_by_gene` |
| KG-IPT-003 | Property gap | P2 | `ontology_landscape.level_kind` column for InterPro rows |
| KG-IPT-004 | Documentation | P2 | MCP field descriptions for the 5 near-homonym chemistry counts |
| KG-IPT-005 | Confirmation | P2 | InterPro provenance design — are GO/pathway xrefs landing this release? |
| KG-IPT-006 | Confirmation | P3 | `is_promiscuous` treatment in InterPro ORA |
| KG-IPT-007 | Documentation | P3 | CHANGELOG prose uses property names the graph does not have |
| KG-IPT-008 | Index (deferred) | — | **Not requested now.** Recorded for the deferred W2 provenance-filter workstream |

---

## 3. Per-ask detail

### KG-IPT-001 — Publish the controlled vocabularies as machine-readable contract (P1)

**Ask:** Expose the closed vocabularies introduced by this integration as data — e.g. a
`Schema_info.controlled_vocabularies` JSON blob keyed
`{node_or_edge_label: {property: [values]}}`. Critically, `evidence` must be expressible
**per edge type**, because its domain is not uniform across edges.

Measured on the deployed build:

| Vocabulary | Values |
|---|---|
| `<gene→ontology>.sources` | `ncbi, cyanorak, uniprot, eggnog, interpro` |
| `<gene→ontology>.evidence` | `curated, signature, family_inferred, domain_inferred` — **per-edge-type subsets, see below** |
| `InterproEntry.interpro_type` | `FAMILY, DOMAIN, HOMOLOGOUS_SUPERFAMILY, REPEAT, CONSERVED_SITE, ACTIVE_SITE, BINDING_SITE, PTM` |
| `Tcdb_family_transports_metabolite.substrate_depth` | `deepest, ancestor` |
| `Gene.transport_substrate_resolution` | `resolved, family_inferred` (sparse) |

The per-edge-type restriction on `evidence`, which is documented nowhere:

| Edge type | Observed `evidence` values |
|---|---|
| `Gene_has_pfam` | `curated` (104,113), `signature` (73,340) |
| `Gene_catalyzes_ec_number` | `curated` (59,493), `family_inferred` (9,533) |
| `Gene_involved_in_biological_process` | `curated` (524,173), `family_inferred` (7,918), `domain_inferred` (7,782) |
| `Gene_has_cazy_family` | `curated` (1,514), `domain_inferred` (441), `family_inferred` (201) |

**Why:** Without this the explorer hard-codes all five vocabularies in
`list_filter_values` and in Pydantic `Literal` types, so the MCP silently drifts the
moment the KG adds a value — the failure mode is a wrong answer, not an error.

The per-edge-type subsetting matters semantically, not just cosmetically. A user asking
*"give me EC annotations that are not domain-inferred"* needs to know `domain_inferred`
is **not a possible value on `Gene_catalyzes_ec_number` at all**. Otherwise an empty
result set reads as "no such annotations exist" rather than "that category does not
apply to this edge" — and these strings are consumed by an LLM at query time, which will
not infer the distinction.

**Verified state (2026-08-16):**

```cypher
// evidence domain differs per edge type
MATCH ()-[r:Gene_has_pfam]->() RETURN r.evidence AS e, count(*) AS n ORDER BY n DESC
```
→ `curated` 104,113 · `signature` 73,340 (no `*_inferred` values at all)

```cypher
MATCH ()-[r:Gene_catalyzes_ec_number]->() RETURN r.evidence AS e, count(*) AS n ORDER BY n DESC
```
→ `curated` 59,493 · `family_inferred` 9,533 (no `signature`, no `domain_inferred`)

```cypher
MATCH ()-[r:Gene_involved_in_biological_process]->() UNWIND r.sources AS s
RETURN DISTINCT s ORDER BY s
```
→ `cyanorak, eggnog, interpro, ncbi, uniprot`

**Acceptance criteria:**
- A single queryable source of truth enumerating each vocabulary's full value set.
- `evidence` expressible per edge type (a flat union is insufficient — it would let the
  explorer offer `domain_inferred` on an EC query where it can never match).
- Versioned with the KG, so `kg_release_info` can detect vocabulary drift rather than
  the explorer discovering it through a wrong answer.

**Acceptable fallback:** an authoritative, versioned table in `docs/kg-changes/` that we
vendor into `kg/constants.py`. The requirement is authority and versioning, not the
transport mechanism.

---

### KG-IPT-002 — Settle `resolved` vs `substrate_confirmed` (P1)

**Ask:** Confirm the final vocabulary for the transport-confidence positive case.

The KG ships `Gene.transport_substrate_resolution ∈ {resolved, family_inferred}`. The MCP
already exposes a per-row `transport_confidence ∈ {substrate_confirmed, family_inferred}`
on `genes_by_metabolite` and `metabolites_by_gene`. Same concept, different word for the
positive case.

**Explorer preference:** we adopt the KG's `resolved` and retire `substrate_confirmed`,
keeping the graph as single source of truth. We need confirmation the KG vocabulary is
final before baking it into the public MCP enum.

**Why:** Both sides are pre-1.0 and both are cutting a release. This is the last cheap
moment to converge — after release, a rename is a breaking change to a published MCP
enum.

**Verified state (2026-08-16):**

```cypher
MATCH (g:Gene) RETURN g.transport_substrate_resolution AS r, count(*) AS n ORDER BY n DESC
```
→ `null` 94,675 · `resolved` 28,405 · `family_inferred` 1,671

**Acceptance criteria:** a yes/no on `resolved` being final. No KG change required if yes.

---

### KG-IPT-003 — `InterproEntry` has no `level_kind` (P2)

**Ask:** Either populate `InterproEntry.level_kind`, or explicitly declare it
null-by-design for InterPro.

**Why:** `TcdbFamily` and `CazyFamily` both carry `level_kind`, and `ontology_landscape`
emits that column for every ontology it surveys. InterPro's depth tiers (level 0/1/2)
have no natural names. We would rather emit `null` **on contract** than by accident, and
we do not want to invent a value the KG does not bless.

**Verified state (2026-08-16):**

```cypher
MATCH (n:InterproEntry) RETURN n.level AS lvl, count(*) AS n ORDER BY lvl
```
→ level 0: 11,430 · level 1: 1,490 · level 2: 79 (no `level_kind` key on any node)

```cypher
MATCH (t:TcdbFamily) RETURN t.level_kind AS lk, count(*) AS n ORDER BY n DESC
```
→ `tc_subfamily` 596 · `tc_family` 592 · `tc_specificity` 286 · `tc_subclass` 34 · `tc_class` 7

**Acceptance criteria:** either `level_kind` present on all 12,999 entries, or a
one-line statement in `interproscan-extension.md` that InterPro has no `level_kind` and
consumers should emit null.

---

### KG-IPT-004 — Canonical definitions for the five near-homonym chemistry counts (P2)

**Ask:** A canonical one-line definition per property, quotable verbatim in MCP field
descriptions.

| Property | Our current understanding |
|---|---|
| `Gene.metabolite_count` | catalysis arm only |
| `Gene.transported_metabolite_count` | transport arm, deepest attachments only |
| `Metabolite.gene_count` | catalysis arm only |
| `Metabolite.transporter_gene_count` | transport arm (genes) |
| `Metabolite.transporter_count` | distinct transporter **systems**, not genes |

**Why:** The metabolite-count split produced two easily-transposed pairs, plus
`transporter_count` / `transporter_gene_count` differing only by a word while counting
different entities. These strings are read by an LLM at query time — a wrong paraphrase
becomes a wrong answer, and we would rather quote than paraphrase.

**Verified state (2026-08-16):**

```cypher
MATCH (g:Gene) WHERE (g)-[:Gene_has_tcdb_family]->() AND coalesce(g.metabolite_count,0)=0
RETURN count(g) AS transport_only_reading_zero
```
→ 25,491 (confirms `metabolite_count` no longer includes the transport arm)

```cypher
MATCH (m:Metabolite) WHERE coalesce(m.transporter_count,0)>0
RETURN count(m) AS n, max(m.transporter_count) AS mx
```
→ 1,462 metabolites, max 123

**Acceptance criteria:** five one-line definitions, ideally in
`tcdb-two-source-upgrade.md` beside the existing property tables.

---

### KG-IPT-005 — Confirm InterPro → GO / pathway xrefs are not landing this release (P2)

**Ask:** Confirm the deferral so the explorer does not design for them.

**Why:** `interproscan-extension.md` lists them as *"artifacts populated 2026-08-07;
still not in the graph"*, and notes the open design question of whether they become an
additional evidence source on the **existing** `Gene_involved_in_biological_process` /
`_enables_molecular_function` / `_located_in_cellular_component` edges. That decision
changes the provenance shape we are building against right now. If it lands mid-flight
we re-litigate the `sources` / `evidence` surfacing design.

**Verified state (2026-08-16):** no InterPro-sourced GO edges present — the only
InterPro→ontology edges in the graph are the Layer-A routers:

```cypher
CALL db.relationshipTypes() YIELD relationshipType AS r
WHERE toLower(r) CONTAINS 'interpro' RETURN collect(r) AS rels
```
→ `Gene_has_interpro_entry`, `Interpro_entry_is_a_interpro_entry`,
`Pfam_in_interpro_entry`, `Interpro_entry_related_to_ec_number` (6,854),
`Interpro_entry_related_to_cazy_family` (122)

**Acceptance criteria:** a yes/no. No KG change required.

---

### KG-IPT-006 — Confirm `is_promiscuous` is a down-weighting hint, not a default filter (P3)

**Ask:** Confirm intended consumer semantics for `InterproEntry.is_promiscuous`.

**Explorer plan:** surface it per-row and let the user decide, mirroring the explicit
guidance in `tcdb-two-source-upgrade.md` §2 that advisory scores be used for ranking
rather than silent filtering. We will **not** exclude promiscuous entries by default.

**Why:** InterPro ORA is invalid unstratified — `gene_count` is extremely skewed, so a
default exclusion is tempting and would be the wrong call for the same reason
`filter_action` was deleted on the TCDB side.

**Verified state (2026-08-16):**

```cypher
MATCH (n:InterproEntry)
RETURN percentileCont(n.gene_count,0.5) AS p50, percentileCont(n.gene_count,0.95) AS p95,
       percentileCont(n.gene_count,0.99) AS p99, max(n.gene_count) AS mx
```
→ p50 = 12 · p95 = 94 · p99 = 307 · max 6,909 (IPR027417, P-loop NTPase superfamily)

```cypher
MATCH (n:InterproEntry) WHERE n.is_promiscuous RETURN count(*) AS n
```
→ 22 (exactly `gene_count >= 1000`, verified no drift)

**Acceptance criteria:** confirmation. No KG change required.

---

### KG-IPT-007 — CHANGELOG prose uses property names the graph does not have (P3)

**Ask:** Use exact graph property names in CHANGELOG prose, or note the mapping.

**Why:** The `[Unreleased] → Data` entry for biller 2016 refers to `control_condition`;
the graph property is `control`. A verification query for
`control_condition IS NULL` returns all 197 experiments, which reads exactly like a
dropped fix — this cost us a false-positive bug hunt before we found the real property
and confirmed the fix had landed correctly. Same class of issue as calling
`publication_year` "year".

**Verified state (2026-08-16):**

```cypher
MATCH (e:Experiment) WHERE e.id CONTAINS 'ismej.2016.82'
RETURN e.id AS id, e.treatment AS treatment, e.control AS control
```
→ `control = "12 hours after co-culturing with Prochlorococcus NATL2A"` on both
timepoint contrasts — the fix is correct; only the prose name is wrong.

```cypher
MATCH (e:Experiment) WHERE e.control IS NULL RETURN count(e) AS n
```
→ 0 of 197

**Acceptance criteria:** CHANGELOG prose referring to graph properties uses the exact
property name.

---

### KG-IPT-008 — Relationship property index on `evidence` (Deferred — not requested now)

**Not an ask for this release.** Recorded so it can be planned rather than discovered.

The graph currently has 86 indexes and **zero relationship-property indexes**. That is
correct at present cardinalities: the edge-property filters the explorer is adding now
touch `Tcdb_family_transports_metabolite` (11,263 edges) and `Gene_has_tcdb_family`
(53,763).

If the deferred W2 workstream lands (`source_filter` / `evidence_filter` on gene→ontology
tools), those filters run over `Gene_involved_in_biological_process` at **539,873** edges
and `Gene_has_pfam` at **177,453**. A relationship property index on `evidence` would
matter then.

All four InterPro indexes are present and correct — `interproEntryFullText`,
`interpro_entry_id_idx`, `interpro_entry_level_idx`, `interpro_entry_type_idx`, the last
being exactly the ORA stratification key the integration doc calls for. **No index asks
for this release.**

---

## 4. What we need answered to proceed

| ID | Blocking | Needs a KG change? |
|---|---|---|
| KG-IPT-002 | Blocks the public MCP `transport_confidence` enum | No — decision only |
| KG-IPT-003 | Blocks `ontology_landscape` InterPro rows | Either populate or document |
| KG-IPT-005 | Blocks the provenance-surfacing design | No — confirmation only |
| KG-IPT-001 | Not blocking; we hard-code the vocabularies without it, and drift silently | Yes |
| KG-IPT-004, 006, 007 | Not blocking | Documentation / confirmation |
