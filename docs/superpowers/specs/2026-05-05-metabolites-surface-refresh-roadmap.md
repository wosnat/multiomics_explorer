# Metabolites Surface Refresh — Phasing Roadmap

**Date:** 2026-05-05 (initial); refreshed 2026-05-05 post-rebuild after KG-state verification reduced KG asks 5 Live → 3 Live.
**Audit (driver):** [docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md](2026-05-04-metabolites-surface-audit.md)
**KG-side asks (companion):** [docs/kg-specs/2026-05-05-metabolites-surface-asks.md](../../kg-specs/2026-05-05-metabolites-surface-asks.md)
**Phase 1 frozen spec:** [docs/tool-specs/2026-05-05-phase1-pass-through-plumbing.md](../../tool-specs/2026-05-05-phase1-pass-through-plumbing.md)
**Status:** Phasing locked; Phase 1 frozen spec drafted (pending user approval); per-phase implementation plans pending for Phases 2-5.
**Convention:** each phase below becomes one downstream `writing-plans` cycle.

---

## 1. Why a roadmap

The audit (Parts 2 + 3) is exhaustive about *what* needs to change in the MCP surface to land the metabolites refresh. It does not pick a shipping order. This roadmap selects a **risk-axis ordering**: pure pass-through plumbing first, breaking renames next while call-site count is still small, then surface tightening, then docstring-only routing hints, finally greenfield assay tools (and the one existing-tool item gated on KG-MET-016).

Each phase is small enough to fit one writing-plans cycle and one cohesive PR. Phases 3 and 4 touch disjoint files and may run in parallel worktrees if scheduling allows.

---

## 2. Phase summary

| Phase | Theme | Items | Blast radius | KG dep |
|---|---|---:|---|---|
| 1 | P0 plumbing — pass-through additions | 6 | non-breaking, additive | none |
| 2 | Cross-cutting renames + filter additions | 4 | breaking (controlled call sites) | none |
| 3 | Compound-anchored tightening + ergonomics | 6 | docstring + minor schema | none |
| 4 | Docstring-only routing hints | 5 | docs-only | none |
| 5 | Greenfield assay tools | 4 (new tools) | new surface | none |
| Backlog | `kg_schema` property-description enrichment + analysis-doc Track B `field_description` callout | 1 | docs-only / introspection | KG-MET-001 (Live, doc-only) |

**Total items:** 26 (25 Live across phases + 1 in backlog).

**Refresh 2026-05-05 post-rebuild:**
- The `list_metabolites` measurement-rollup pass-through item moved from Phase 5 → Phase 1 because KG-MET-016 (`Metabolite.measured_compartments`) is now populated by the post-import script, removing the gating dependency. Phase 5 is now pure greenfield (4 new assay tools, no existing-tool plumbing).
- The `kg_schema` property-description enrichment + analysis-doc Track B item (originally Phase 1) was moved to backlog per user decision 2026-05-05. Phase 1 net count: 6 items (was 6 originally; +1 from `list_metabolites` move-in, −1 from `kg_schema` move-out).

---

## 3. Per-phase detail

Each phase lists items, dependencies, and the open decisions (if any) that must close before writing-plans starts. Audit row references are inline so reviewers can verify completeness against the audit.

### Phase 1 — P0 plumbing (pass-through additions)

**Goal:** surface chemistry + measurement node-property data that already exists on the KG but is invisible in current MCP responses. All items are additive; no tool's existing fields change shape.

**Items:**

- **`gene_overview`** — per-row chemistry counts (`reaction_count`, `metabolite_count`, `transporter_count`) **plus** `evidence_sources` rollup (subset of `['metabolism', 'transport', 'metabolomics']` describing which path-existence applies) **plus** envelope `has_chemistry`. *Audit Part 2 P0; live verification 2026-05-05 surfaced that the chemistry counts are not currently in the response shape, so this item adds 4 fields, not just 1.*
- **`list_publications`** — per-row `metabolite_count`, `metabolite_assay_count`, `metabolite_compartments` (pass-through from Publication node — KG rollup already exists). *Audit Part 2 P0 / Part 3a cross-ref.*
- **`list_experiments`** — per-row `metabolite_count`, `metabolite_assay_count`, `metabolite_compartments` (pass-through from Experiment node). *Audit Part 2 P0 / Part 3a cross-ref.*
- **`list_organisms`** — per-row `measured_metabolite_count` (pass-through from Organism node) + envelope `by_measurement_capability` as a 2-bucket count `{has_metabolomics: N, no_metabolomics: M}`. *Audit Part 3a P1.*
- **`list_metabolites`** — per-row `measured_assay_count`, `measured_paper_count`, `measured_organisms`, `measured_compartments` (pass-through from Metabolite node) + envelope `by_measurement_coverage` (counts at 0 / 1 / 2 papers + counts by compartment). *Audit Part 3a P0; **previously gated on KG-MET-016, now unblocked** since the post-import script populates `Metabolite.measured_compartments` on all 107 measured metabolites (verified live 2026-05-05).*
- **`list_filter_values`** — add `omics_type` filter type (returns canonical list including `METABOLOMICS`); add `evidence_source` filter type (returns `['metabolism', 'transport', 'metabolomics']`) for downstream chemistry-layer routing. The `compartment` filter already returns `extracellular` via `Experiment.compartment` (verified live; 3 records). *Audit Part 2 P2 + Part 3a P1.*

**Dependencies:** none. KG-MET-016 (was the gating item for the `list_metabolites` row) is now Closed — see kg-asks §5.B.

**Ready-to-plan gate:** none open. All node-property reads verified in audit Part 1 §1.2 + 2026-05-05 post-rebuild verification.

**Out of scope here (deferred to Phase 5):** the four greenfield assay tools (`list_metabolite_assays`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite`).

---

### Phase 2 — Cross-cutting renames + filter additions

**Goal:** lock in the breaking-but-controlled changes early, while audit reports only 2 internal call sites for `search→search_text` and a similarly small footprint for `top_pathways→top_metabolite_pathways`. Delaying these makes them costlier as the call-site count grows. All four items are bundled because they share testing scaffolding and migration ergonomics.

**Items:**

- **`list_metabolites`** — rename kwarg `search` → `search_text` for consistency with the 7 other list/search tools. Update tool signature + 2 known internal call sites + tests. *Audit Part 2 build-derived P2; walkthrough Q&A 2026-05-05 APPROVED.*
- **`list_metabolites` + `metabolites_by_gene` (+ any future compound-anchored chemistry tool)** — rename envelope `top_pathways` → `top_metabolite_pathways`; per-row keys `pathway_id` / `pathway_name` → `metabolite_pathway_id` / `metabolite_pathway_name`. Adopts Option A naming convention from audit. *Audit Part 2 build-derived P1 cross-cutting; walkthrough Q&A 2026-05-05 APPROVED.*
- **`list_metabolites` + `metabolites_by_gene` + `genes_by_metabolite`** — add `exclude_metabolite_ids: list[str] | None = None` parameter (primitive negative filter mirroring `metabolite_ids` include semantics). Pushes §4.5 confounder #1 (currency-cofactor flooding) mitigation into the tool layer. *Audit Part 2 build-derived P2 cross-cutting.*
- **`differential_expression_by_gene`** — accept `direction='both'` (run both arms internally and merge, matching `pathway_enrichment` convention). *Audit Part 2 build-derived P2; walkthrough Q&A 2026-05-05 ACCEPT 'both'.*

**Dependencies:** Phase 1 should ship first so the new envelope keys land in tools that already have measurement-rollup pass-through tests.

**Ready-to-plan gate:** none open. Naming conventions and call-site counts already verified in audit.

**Out of scope here (Phase 3):** the union-shape `None`-key padding on `metabolites_by_gene` / `genes_by_metabolite` is a compound-anchored *tightening*, not a rename — phased separately.

---

### Phase 3 — Compound-anchored tightening + ergonomics

**Goal:** sharpen the row schema and docstrings on the compound-anchored chemistry tools (`metabolites_by_gene`, `genes_by_metabolite`, `list_metabolites`) so consumers read consistent shapes and accurate "involved in" / reversibility framing. Plus three ergonomics fixes that surfaced during the build but didn't fit Phases 1 or 2.

**Items:**

- **`genes_by_metabolite` + `metabolites_by_gene`** — surface explicit `None` for cross-arm fields so every row has identical key set (metabolism rows get `transport_confidence: None` / `tcdb_family_id: None` / `tcdb_family_name: None`; transport rows get `reaction_id: None` / `reaction_name: None` / `ec_numbers: None` / `mass_balance: None`). Document the union shape explicitly in tool descriptions. *Audit Part 2 build-derived P2; walkthrough Q&A 2026-05-05 BOTH (document + None-pad).*
- **`genes_by_metabolite` + `metabolites_by_gene`** — reaction-arm row docstrings explicitly say *"reaction edges are undirected AND carry no reversibility flag — interpret all reaction-arm rows as 'involved in', never 'produces' / 'consumes' / 'reversible'."* Cross-ref audit §4.0 §4.1.1 + §4.1.2. *Audit Part 2 build-derived P3.*
- **`genes_by_metabolite` + `metabolites_by_gene`** — rewrite family_inferred-dominance warning to question-shape-aware framing (drop the "high-precision" prescription; surface the substrate_confirmed / family_inferred distinction as workflow-dependent — both tiers are annotations, neither is ground truth). *Audit Part 2 build-derived P3 + §4.5 confounder #2; walkthrough Q&A 2026-05-05 APPROVED.*
- **`list_metabolites`** — document `by_element` semantics explicitly in the tool description ("count of distinct compounds in `total_matching` containing each element"; not stoichiometric, not mass-balanced). *Audit Part 2 build-derived P3.*
- **`search_ontology`** — accept both `query=` and `search_text=` kwargs as ergonomic aliases. *Audit Part 2 build-derived P3.*
- **`metabolites_by_gene` summary mode** — investigate root cause of `top_genes=None` on small inputs; fix or document threshold. *Audit Part 2 build-derived P3; walkthrough Q&A 2026-05-05 INVESTIGATE during this phase.*

**Dependencies:** Phase 2 (envelope key renames must already be in place so docstring updates reference the final names).

**Ready-to-plan gate:** the `top_genes=None` investigation may surface a deeper bug. If root cause is an aggregation off-by-one and not just a documentation gap, the phase scope grows by one fix item. Plan should include investigation as a first step before locking remaining tasks.

**Out of scope here (Phase 4):** routing-hint docstring updates on tools *outside* the compound-anchored family — those are docs-only and disjoint files.

---

### Phase 4 — Docstring-only routing hints

**Goal:** add cross-tool routing guidance to docstrings on tools that don't change shape, so the LLM picks up "when you see X, drill via Y" patterns identified during the audit walkthrough. Disjoint files from Phase 3; can run in parallel worktree.

**Items:**

- **`genes_by_ontology`** — add explicit pivot guidance from `tcdb` / `ec` term hits to `genes_by_metabolite` (metabolite-anchored route). *Audit Part 2 P2.*
- **`pathway_enrichment`** — when KEGG pathway is enriched, route to `list_metabolites(pathway_ids=[...])` to inspect chemistry of the pathway. *Audit Part 2 P2.*
- **`cluster_enrichment`** — same routing as `pathway_enrichment`. *Audit Part 2 P3.*
- **`list_derived_metrics`** — route from DM discovery → `genes_by_*_metric` → drill into chemistry via `metabolites_by_gene`. *Audit Part 2 P3.*
- **`gene_details`** — explicit chemistry section in docstring guidance (no schema change; data already flows). *Audit Part 2 P3.*

**Dependencies:** Phase 2 (new envelope keys + filter names appear in routing examples); Phase 3 (warning rewrite + reversibility framing referenced in chained guidance).

**Ready-to-plan gate:** none open. All docstring targets verified in audit.

---

### Phase 5 — Greenfield assay tools

**Goal:** ship the four new metabolomics-measurement tools that close the Track-B (measurement-anchored) workflow.

**Items:**

- **`list_metabolite_assays`** — discovery surface for `MetaboliteAssay` nodes (mirrors `list_experiments` per-assay; parameter naming follows `list_derived_metrics`). Full signature + per-row schema + envelope shape in audit Part 3b.1. *Audit Part 3b.1 P1.*
- **`metabolites_by_quantifies_assay`** — numeric-arm drill-down on `Assay_quantifies_metabolite` edges. Analog of `genes_by_numeric_metric`. Edge filters: `metric_bucket`, `metric_percentile_min/max`, `rank_by_metric_max`, `value_min/max`, `detection_status`, `time_point`. Envelope: `by_detection_status` (primary headline per audit §4.3.3 resolution) + `by_metric_bucket` + `by_assay`. *Audit Part 3b.3a P1.*
- **`metabolites_by_flags_assay`** — boolean-arm drill-down on `Assay_flags_metabolite` edges. Analog of `genes_by_boolean_metric`. Edge filter: `flag_value`. *Audit Part 3b.3b P1.*
- **`assays_by_metabolite`** — batch reverse-lookup merged across edge types with polymorphic `value` / `flag_value` columns. Analog of `gene_derived_metrics`. Filter: `evidence_kind: Literal['quantifies', 'flags']`. `not_found` / `not_matched` buckets for diagnosability. *Audit Part 3b.3c P1.*

**Dependencies:** none. KG-MET-001 (field_description provenance docs) and KG-MET-002 (compartment-as-property docs) inform (not block) tool docstrings; if either lands before Phase 5 ships, the new tool docstrings can cite the canonical convention directly.

**Ready-to-plan gate:** the four new tools should follow the `add-or-update-tool` skill (Phase 1 scoping → Phase 2 parallel TDD build), per CLAUDE.md.

**Sequencing within phase:** `list_metabolite_assays` first (discovery), then the three drill-down tools as a slice (shared envelope shape + Pydantic patterns).

---

## 4. Audit-row → phase mapping

Lets the reader verify completeness from either direction.

| Audit row | Phase |
|---|---|
| Part 2 P0 — `gene_overview` evidence_sources | 1 |
| Part 2 P0 — `list_publications` metab pass-through | 1 |
| Part 2 P0 — `list_experiments` metab pass-through | 1 |
| Part 2 P1 — `list_organisms` measurement extension | 1 |
| Part 2 P2 — `genes_by_ontology` TCDB/EC pivot guidance | 4 |
| Part 2 P2 — `list_filter_values` `evidence_source` filter (bundled with `omics_type` in same Phase 1 item) | 1 |
| Part 2 P2 — `pathway_enrichment` route to list_metabolites | 4 |
| Part 2 P3 — `gene_details` chemistry section | 4 |
| Part 2 P3 — `cluster_enrichment` route to list_metabolites | 4 |
| Part 2 P3 — `list_derived_metrics` DM→chemistry routing | 4 |
| Part 2 build-derived P2 — `differential_expression_by_gene` direction='both' | 2 |
| Part 2 build-derived P2 — `genes_by_metabolite` union-shape `None` padding | 3 |
| Part 2 build-derived P2 — `metabolites_by_gene` union-shape `None` padding | 3 |
| Part 2 build-derived P3 — `metabolites_by_gene` summary `top_genes=None` investigation | 3 |
| Part 2 build-derived P3 — `search_ontology` kwarg alias | 3 |
| Part 2 build-derived P2 — `list_metabolites` `search`→`search_text` rename | 2 |
| Part 2 build-derived P3 — reaction-arm reversibility docstring | 3 |
| Part 2 build-derived P3 — `list_metabolites` name-search discoverability (analysis doc — already done) | (closed in audit run) |
| Part 2 build-derived P3 — `list_metabolites` by_element semantics docstring | 3 |
| Part 2 build-derived P3 — family_inferred-dominance warning rewrite | 3 |
| Part 2 build-derived P1 cross-cutting — `top_pathways` → `top_metabolite_pathways` | 2 |
| Part 2 build-derived P2 cross-cutting — `exclude_metabolite_ids` filter | 2 |
| Part 3a P0 — `list_metabolites` measurement-rollup pass-through | 1 (moved from 5; KG-MET-016 closed) |
| Part 3a P1 — `list_organisms` measurement extension (cross-ref Part 2) | 1 |
| Part 3a P1 — `list_filter_values` `omics_type` filter type | 1 |
| Part 3a build-derived P1 — `kg_schema` field_description plumbing + analysis-doc Track B callout | Backlog (deferred 2026-05-05) |
| Part 3b.1 P1 — `list_metabolite_assays` (new) | 5 |
| Part 3b.3a P1 — `metabolites_by_quantifies_assay` (new) | 5 |
| Part 3b.3b P1 — `metabolites_by_flags_assay` (new) | 5 |
| Part 3b.3c P1 — `assays_by_metabolite` (new) | 5 |

---

## 5. DROPped / DEFERed / NOT-NEEDED — explicit non-scope

Mirrors the audit's drop list. Each item gets a one-line reason for not landing in any phase, so future readers don't ask "did we forget X?"

| Item | Reason for no phase |
|---|---|
| Per-row chemistry hint on `genes_by_function` | DROPPED 2026-05-05 — search-result shape; chain to `gene_overview` already canonical. |
| Per-result chemistry rollup on `gene_response_profile` | DROPPED — purpose-built; chemistry scopes upstream (A5 empirical proof). |
| Per-row chemistry on `differential_expression_by_gene` | DROPPED — purpose-built DE; same reasoning. |
| Group-level chemistry pass-through on `differential_expression_by_ortholog` | DROPPED — purpose-built DE at ortholog level. |
| Group-level chemistry rollup on `gene_homologs` | DROPPED — orthology lookup; chemistry not informative per-row. |
| Per-row chemistry on `genes_by_homolog_group` | DROPPED — same. |
| Envelope chemistry coverage on `search_homolog_groups` | DROPPED — search-result shape. |
| Per-cluster chemistry rollup on `gene_clusters_by_gene` | DROPPED — cluster-membership lookup. |
| Per-row chemistry + envelope `top_metabolites` on `genes_in_cluster` | DROPPED — cluster drill-down. |
| Per-analysis chemistry coverage on `list_clustering_analyses` | DROPPED — analysis-level rollup. |
| Per-row chemistry on `gene_derived_metrics` / `genes_by_*_metric` | DROPPED — DM-anchored; chemistry adds noise. |
| Per-gene chemistry on `gene_ontology_terms` | DROPPED — reverse ontology lookup. |
| Per-row chemistry on `resolve_gene` | DROPPED — identity resolution. |
| `metabolite_response_profile` (new tool) | DEFER — premature for current 10-assay / 92-metabolite / 2-paper scale. Revisit when scale grows or audit §4.3.2/3/5 questions resolve. |
| `differential_metabolite_abundance` (new tool) | DEFER — premature; may never happen. Schema empirically rejects FC; if §4.3.2 confirms, this tool's shape evaporates. |
| DM-family extension to Metabolite | NOT-NEEDED — `MetaboliteAssay` already carries the DM-equivalent fields; KG modellers answered §4.3.1/§4.3.6 implicitly. |
| Opinionated `exclude_currency_cofactors=True` default | DEFER — start with primitive `exclude_metabolite_ids` (Phase 2); escalate only if callers re-discover the flooding pattern. |
| `kg_schema` property-description enrichment + analysis-doc Track B `field_description` callout | DEFER 2026-05-05 — originally Phase 1, moved to backlog per user decision. Will land as a separate slice when re-prioritized. KG-MET-001 (the companion KG-side ask) stays Live. Logged to `project_backlog` memory. |

---

## 6. Sequencing notes

- **Phase 1 ships first.** Lowest blast radius; exercises the test-update + about-content regen pipeline before bigger phases hit it.
- **Phase 2 ships next.** Renames are cheapest now (audit reports 2 internal call sites for `search→search_text`; `top_pathways` rename has similarly small footprint). Delaying compounds the migration cost.
- **Phases 3 and 4 can interleave or run parallel** in separate worktrees — compound-anchored tightening (Phase 3) vs docstring-only routing (Phase 4) touch disjoint files. If only one developer is available, ship Phase 3 first because Phase 4's routing examples reference the final docstring framing landed in Phase 3.
- **Phase 5 is now pure greenfield** (4 new tools; the `list_metabolites` measurement-rollup item moved to Phase 1 after KG-MET-016 was confirmed Closed 2026-05-05 post-rebuild). Start writing-plans for it as soon as Phase 4 is in flight; the four new tools can proceed in parallel.
- **Per CLAUDE.md, all four new tools in Phase 5 should use the `add-or-update-tool` skill** (Phase 1 scoping → Phase 2 parallel TDD build). The three drill-down tools (`metabolites_by_quantifies_assay` / `metabolites_by_flags_assay` / `assays_by_metabolite`) form a natural slice and should be planned as a single writing-plans cycle, mirroring how the DM-family slice was structured.
