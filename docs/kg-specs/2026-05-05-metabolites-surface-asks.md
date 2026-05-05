# KG-side asks: metabolites surface refresh

**Date:** 2026-05-05
**Driver (audit):** [docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md](../superpowers/specs/2026-05-04-metabolites-surface-audit.md) — Part 5.A
**Roadmap (explorer side):** [docs/superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md](../superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md)
**Status:** 5 Live asks — 1× P1, 4× P2. KG-state verified against the live KG on 2026-05-05.

---

## 1. Summary

Five asks remain live after the audit's verification + layer-classification pass on 2026-05-05. The shape is heavily skewed toward documentation and small precomputes — **no P0 / P1 data-gap asks**. The 16 originally-numbered asks split as **5 Live / 6 Closed / 5 Retired**; full traceability lives in audit Part 5.D. Closed asks were already satisfied by the 2026-05 KG release or moved to the explorer side. Retired asks are out-of-scope upstream-annotation gaps with no recoverable data (KEGG lacks reaction direction / reversibility / complex modelling; TCDB lacks transport polarity).

What remains is small and targeted: one provenance-documentation reshape (P1), one decision-documentation pair (compartment convention, P2), one precompute (TCDB family promiscuity, P2), one adapter-behavior investigation (cross-omics time alignment, P2), and one rollup symmetry fix (per-Metabolite-node `measured_compartments`, P2).

---

## 2. Ask summary table

| ID | Category | Pri | Phase | Explorer consumer (roadmap phase) |
|---|---|---|---|---|
| KG-MET-001 | Documentation (RESHAPED) | P1 | first-pass | `kg_schema` field_description plumbing — Phase 1 |
| KG-MET-002 | Decision + Documentation | P2 | first-pass | docs-only; informs `list_metabolite_assays` (Phase 5) |
| KG-MET-006 | Precompute | P2 | first-pass | family_inferred warning rewrite (Phase 3) optional input; future tier-aware ranking |
| KG-MET-013 | Adapter behavior + Documentation | P2 | first-pass | future cross-omics time-correlated tools (no current consumer) |
| KG-MET-016 | Rollup | P2 | first-pass | `list_metabolites` measurement-rollup pass-through — Phase 5 |

---

## 3. Per-ask detail

### KG-MET-001 — `MetaboliteAssay.field_description` provenance docs (P1, RESHAPED)

**Ask:** Confirm + document the convention that `MetaboliteAssay.field_description` is the canonical normalisation-provenance field for the metabolomics layer. Specifically:

- (a) Add a brief `#` comment near `field_description: str` in `config/schema_config.yaml` calling out its provenance role.
- (b) Call out the convention in `metabolomics-extension.md` and any future metabolomics release notes.

**Why:** The original ask requested *adding* per-paper normalisation docs. Verification against the live KG (2026-05-05) showed those docs already exist, embedded in `field_description` itself. The reshape narrows the ask to "make the convention canonical and discoverable" rather than "add new data."

**Verified state (2026-05-05):**

`MetaboliteAssay.field_description` already carries rich, paper-specific provenance. Examples observed in the live KG:

- *"Intracellular metabolite concentration in fg/cell, blank-corrected, replicate-aggregated; Capovilla 2023 Table sd03"* (Capovilla paper)
- *"Per-cell intracellular concentration; KEGG-tagged; pre-aggregated by authors. Kujawinski 2023 cellSpecific KEGG export."* (Kujawinski paper)

Companion fields on the assay node (`value_kind`, `unit`, `metric_type`, `aggregation_method`) round out the provenance picture. The 2026-05-04 KG release notes (`metabolomics-extension.md`) treat `field_description` as first-class — it is one of four fields indexed in the `metaboliteAssayFullText` full-text index alongside `name`, `treatment`, and `experimental_context`. The reshape direction is consistent with KG-team intent.

**Acceptance criteria:**

- `config/schema_config.yaml` diff shows the YAML `#` comment on `field_description: str`.
- `metabolomics-extension.md` (or release notes) calls out the convention explicitly.

**Explorer-side dependency:** roadmap Phase 1 — `kg_schema` field_description plumbing item. Once KG-MET-001 lands, the explorer's `kg_schema` MCP tool surfaces the canonical provenance read in tool docstrings + analysis-doc Track B.

**Out of scope here:** making the BioCypher property description propagate into the live Neo4j schema for schema-introspection callers — that is a separate, larger ask (touches BioCypher config, not just YAML docs). The YAML `#` comment is the cheapest fix.

---

### KG-MET-002 — Compartment-as-property docs (P2)

**Ask:** Document the convention that `Metabolite` is compartment-agnostic and compartment lives on `MetaboliteAssay`. Add to schema docs / `metabolomics-extension.md`. Convention is already in effect; documentation is the only gap.

**Why:** Audit §4.3.5 verified the convention via live-KG inspection. Without explicit documentation, downstream consumers re-derive the convention from inspection (or, worse, assume per-compartment Metabolite duplication). This ask makes the convention canonical so future tools / consumers don't have to reverse-engineer it.

**Verified state (2026-05-05):**

- Zero `Metabolite` nodes encode compartment in their name (no matches for `extracellular` / `intracellular` / `cytoplasm` / `compartment` substrings in `m.name`).
- 92 `Metabolite` nodes are measured in 2+ compartments via separate `MetaboliteAssay` edges. Examples: Phosphoenolpyruvate, (S)-Malate, D-Glucose 6-phosphate measured in both `whole_cell` and `extracellular` against the same `kegg.compound:` ID.

Convention is in effect; ask is documentation-only.

**Acceptance criteria:** schema docs / release-note diff exists explicitly stating the convention.

**Explorer-side dependency:** informs roadmap Phase 5 `list_metabolite_assays` — the discovery tool surfaces compartment per-assay-edge, not per-metabolite-node. Documenting the convention upstream lets the explorer cite KG-side docs rather than re-asserting the rule independently.

---

### KG-MET-006 — `TcdbFamily.is_promiscuous` precompute (P2)

**Ask:** Add per-`TcdbFamily` boolean property `is_promiscuous: bool` so explorer tools can dim / rank `family_inferred` rows without re-deriving the rule client-side. The KG team owns the threshold definition; a starting proposal (subject to KG-team refinement) might be `metabolite_count >= 50 OR member_count >= 100`, but the actual cut-points should be chosen empirically against the family-count distribution.

**Why:** Audit §4.5 confounder #2 — family-level transport casts a wide net (ABC superfamily → ~554 metabolites/gene; broadest non-superfamily families also wide). Today the explorer's family_inferred-dominance warning is binary ("most rows are family_inferred"). With `is_promiscuous`, tools can surface a more informative summary: "of N family_inferred rows, M come from promiscuous families" — distinguishing curation-effort gaps from biologically-promiscuous transporters.

**Verified state (2026-05-05):**

`TcdbFamily` node properties (live KG): `[tc_class_id, organism_count, metabolite_count, name, tcdb_id, level, level_kind, gene_count, member_count, superfamily, id, preferred_id]`. **No `is_promiscuous` field.** Existing `superfamily` flag covers the very-broad case but not the "narrow but high-substrate-count" families that drive most family_inferred ambiguity in practice.

The audit's first-pass attempted to define the rule explorer-side via inline thresholds; that workflow was rejected in favor of a single KG-side precompute so tools and analysis docs can cite one canonical definition.

**Acceptance criteria:**

- `TcdbFamily` nodes carry `is_promiscuous: bool`.
- KG-team documents the threshold rule (which fields, which cut-points, why).

**Explorer-side dependency:** *optional* input to roadmap Phase 3's family_inferred warning rewrite. The Phase 3 warning rewrite can ship without `is_promiscuous` (warning becomes question-shape-aware text only); landing KG-MET-006 lets the warning add a concrete promiscuous-family share. Future tier-aware envelope rollups (e.g. `transport_confidence_breakdown` on `genes_by_metabolite`) become possible only after this ask lands.

---

### KG-MET-013 — `time_point_hours` adapter parse / sentinel (P2)

**Ask:** Investigate metabolomics-adapter behavior for `time_point_hours` when the source label is non-numeric (e.g. `"T=4"` resolves to `-1`). Then either:

- (a) Fix the parse so `T=4` resolves to `96` hours (day 4), OR
- (b) Document `-1` as a sentinel for "couldn't parse to hours" and apply consistently, OR
- (c) Document explicitly that cross-omics `time_point` is not guaranteed aligned and consumers must filter / join by `experiment_id` first AND surface raw `time_point` text alongside.

**Why:** Future cross-omics time-correlated tools (none in current explorer scope) need either consistent semantics or explicit non-alignment documentation. Right now this is a silent footgun — same `Experiment` node can yield different `time_point_order=1` rows that describe different real-world timings across omics modalities. KG-MET-013 closes the silence.

**Verified state (2026-05-05):**

Real misalignment confirmed in publication `10.1073/pnas.2213271120` (chitosan addition, MIT9303). Both METABOLOMICS and RNASEQ experiments share an `Experiment` node:

| Edge | `time_point` | `time_point_hours` | `time_point_order` |
|---|---|---:|---:|
| METABOLOMICS | `"T=4"` | `-1` | `1` |
| RNASEQ | `"day 1 and day 3"` | `24` | `1` |

Both label as `time_point_order=1` but describe different real-world timings. The Capovilla `field_description` for the same metabolomics assay (*"T=4 (3 reps) + T=6 (2 reps)"*) suggests `T=4 = day 4` of sampling, which would resolve to `96` hours — making `-1` more likely an adapter parse miss than an intended sentinel. The 2026-05-04 release doc does not call out a `-1` sentinel convention.

**Acceptance criteria:** either an adapter PR landing parsed values (option a), or a release-note entry naming the convention (option b or c).

**Explorer-side dependency:** no current explorer consumer. Logged for future cross-omics time-aware tools. Resolution of this ask sets the contract those future tools rely on.

---

### KG-MET-016 — `Metabolite.measured_compartments` rollup (P2)

**Ask:** Add `measured_compartments: list[str]` to `Metabolite` nodes, sparse — populated only on the 107 measured metabolites, omitted (or null) otherwise. Mirrors the existing `measured_assay_count` / `measured_paper_count` / `measured_organisms` rollup pattern on the same node.

**Why:** Symmetric gap in the measurement-rollup pipeline. The per-pair version of this rollup already exists at `Organism_has_metabolite.measured_compartments`; the per-Metabolite-node version is the lone holdout. The 2026-05-04 KG release explicitly added per-pair `measured_compartments` alongside the per-Metabolite rollups (`measured_assay_count` / `measured_paper_count` / `measured_organisms`); this ask completes the symmetric set so explorer pass-through reads one node, not a per-pair aggregate.

**Verified state (2026-05-05):**

- `Metabolite` node lacks `measured_compartments`.
- Existing per-Metabolite measurement fields = `[measured_assay_count, measured_paper_count, measured_organisms]`.
- Per-pair `Organism_has_metabolite.measured_compartments` is present (release-doc cross-ref). KG team has all the upstream data already.

**Acceptance criteria:**

- `Metabolite` nodes carry `measured_compartments: list[str]` where `measured_assay_count > 0`.
- Either null or absent (sparse-field policy) on the 3111 metabolites with no measurement coverage.

**Explorer-side dependency:** roadmap Phase 5 — `list_metabolites` measurement-rollup pass-through. Until KG-MET-016 lands, Phase 5 either (a) ships 3 of 4 fields (omitting `measured_compartments`) and revisits, or (b) waits for the rollup so the 4-field unit ships cohesively. The roadmap recommends (b).

---

## 4. Verification queries

These queries were used in the 2026-05-05 verification pass (audit Part 5.A evidence). Replay against the live KG before / after each ask lands.

### KG-MET-001 — verify field_description content

```cypher
MATCH (a:MetaboliteAssay)
RETURN a.id AS assay_id, a.name AS name, a.field_description AS field_description
ORDER BY a.id;
```

Expected: 10 rows, each with non-empty `field_description` containing per-paper provenance text.

### KG-MET-002 — verify compartment lives on edge, not node

```cypher
MATCH (m:Metabolite)
WHERE toLower(m.name) CONTAINS 'extracellular'
   OR toLower(m.name) CONTAINS 'intracellular'
   OR toLower(m.name) CONTAINS 'cytoplasm'
   OR toLower(m.name) CONTAINS 'compartment'
RETURN count(m) AS n_metabolites_with_compartment_in_name;

MATCH (m:Metabolite)<-[r:Assay_quantifies_metabolite|Assay_flags_metabolite]-(a:MetaboliteAssay)
WITH m, count(DISTINCT a.compartment) AS n_compartments
WHERE n_compartments >= 2
RETURN count(m) AS n_metabolites_in_multiple_compartments;
```

Expected: 0 in the first query; 92 in the second (reproduces audit §4.3.5 evidence).

### KG-MET-006 — TcdbFamily property inventory

```cypher
CALL db.schema.nodeTypeProperties() YIELD nodeType, propertyName
WHERE 'TcdbFamily' IN nodeType
RETURN collect(propertyName) AS properties;
```

Expected before: `[tc_class_id, organism_count, metabolite_count, name, tcdb_id, level, level_kind, gene_count, member_count, superfamily, id, preferred_id]`. Expected after: same plus `is_promiscuous`.

### KG-MET-013 — time_point_hours adapter check

```cypher
MATCH (e:Experiment)-[:ExperimentHasMetaboliteAssay]->(a:MetaboliteAssay)-[r:Assay_quantifies_metabolite|Assay_flags_metabolite]->(:Metabolite)
WHERE r.time_point IS NOT NULL
RETURN DISTINCT
  e.publication_doi AS doi,
  r.time_point AS time_point,
  r.time_point_hours AS time_point_hours,
  r.time_point_order AS time_point_order
ORDER BY doi, time_point;
```

Expected: `time_point_hours = -1` for any non-numeric `time_point` text. Cross-reference the chitosan paper `10.1073/pnas.2213271120` for the documented misalignment example.

### KG-MET-016 — Metabolite measurement rollup inventory

```cypher
MATCH (m:Metabolite)
WHERE m.measured_assay_count IS NOT NULL AND m.measured_assay_count > 0
RETURN keys(m) AS metabolite_keys
LIMIT 1;
```

Expected before: `measured_compartments` not in `metabolite_keys`. Expected after: present.

```cypher
MATCH (m:Metabolite)
WHERE m.measured_assay_count > 0
RETURN size(m.measured_compartments) AS n_compartments, count(m) AS n_metabolites
ORDER BY n_compartments DESC;
```

Expected after: 92 metabolites with 2 compartments + 15 metabolites with 1 compartment = 107 measured metabolites total (matches audit §1.1 measurement-anchored count).
