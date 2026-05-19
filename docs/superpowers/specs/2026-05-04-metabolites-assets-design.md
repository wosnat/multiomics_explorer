# Metabolites Assets + Surface Audit — Design

**Date:** 2026-05-04
**Status:** Design approved (awaiting written-spec review)
**Owner:** Osnat Weissberg

## 1. Context

The KG has three pipelines that add `Metabolite` content, each with its own evidence semantics and caveats:

1. **Transport (TCDB).** `Gene → TcdbFamily → Metabolite`. Family-level curation: a gene annotated to a TCDB family inherits that family's substrate list. Caveats: family_inferred ≫ substrate_confirmed in row counts (the family_inferred-dominance auto-warning is emitted when this skews); ABC superfamily is especially promiscuous (9 MED4 ABC genes × 551 substrates each); transport direction (import vs export) not represented.
2. **Gene reaction (KEGG).** `Gene → Reaction → Metabolite`. KEGG/EC/KO-derived enzyme catalysis. Caveats: KO assignments are often homology-inferred and may be putative; reaction directionality and substrate-vs-product roles depend on edge modelling (Part 4 question); promiscuous enzymes inflate metabolite counts; multi-subunit enzymes attributed per subunit.
3. **Metabolomics measurement.** `MetaboliteAssay → Metabolite` (under Experiment, attached to publications with `omics_type=METABOLOMICS`). Mass-spec measurement: `Assay_quantifies` for concentration/intensity, `Assay_flags` for qualitative detection. Caveats: **no gene anchor** (cannot attribute a measurement to a specific gene); detection vs quantification semantics differ; compartment matters (extracellular vs intracellular); targeted panels mean absence in measurement ≠ absence in cell; replicate counts and normalisation conventions vary by paper.

Chemistry slice-1 (`list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`) shipped to main on 2026-05-03..04 and surfaces sources 1 and 2 via the `evidence_source ∈ {transport, metabolism}` discriminator. The 2026-05-04 KG release ("metabolomics-extension") added source 3 — two new papers (Capovilla 2023, Kujawinski 2023), `MetaboliteAssay` nodes, `Assay_quantifies/flags_metabolite` edges, +10 Metabolite nodes, the new `extracellular` compartment, the new `growth_phase` background factor.

The explorer code recognises `METABOLOMICS` as a valid `omics_type` and reserves `"metabolomics"` as a placeholder `evidence_source` value, but **zero MCP tools surface `MetaboliteAssay` data**. Today the only access path is `run_cypher`. The block on building a native measurement surface is not engineering — it is missing definition: how should metabolomics measurements be modelled at the explorer layer (DerivedMetric on Metabolite? first-class Assay surface? both?), what is the right summary statistic (FC may not be the right semantic for metabolomics), how do replicates roll up, etc.

Separately, no unified analysis-track guide exists for LLM consumers across the three sources, and the chemistry surface itself has uneven tool coverage (e.g., `gene_response_profile`, DE tools, DM family, homolog tools, cluster tools do not surface chemistry rollups).

## 2. Goals

1. Produce a quantified, prioritised audit of metabolite surfacing — both chemistry annotations (existing layer, partial coverage) and metabolomics measurements (new layer, zero coverage). The audit must be spec-input quality: concrete enough to drive the metabolomics-DM definition conversation and the next round of explorer changes.
2. Add a metabolites analysis guide to the MCP `docs://analysis/` family so an LLM consuming the resource can disambiguate "which metabolites can this gene make" (annotation) from "which metabolites were measured under this condition" (measurement) and route correctly.
3. Add a runnable example script registered under `docs://examples/` that demonstrates the chemistry workflows end-to-end and gives the LLM a working pattern for measurement queries via `run_cypher` until native tools exist.

Non-goals are listed in §6.

## 3. Deliverables

### 3.1 Audit doc

**Path:** `docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md`

Five parts.

#### Part 1 — KG inventory (quantified)

Live counts pulled via `run_cypher` against the deployed KG. Each query is shown inline so the audit is reproducible. Organised around the three Metabolite-source pipelines:

- **Source-coverage Venn over Metabolite.** Counts for each non-empty subset of {transport (has TcdbFamily edge), reaction (has Reaction edge), measurement (has MetaboliteAssay edge)}: transport-only, reaction-only, measurement-only, transport+reaction, transport+measurement, reaction+measurement, all three. Plus total Metabolite count and by-compartment breakdown.
- **Per-source edge inventory.** For each of `Gene→TcdbFamily→Metabolite`, `Gene→Reaction→Metabolite`, and `MetaboliteAssay→Metabolite`, list the edge labels and edge-level properties present (e.g., does the reaction edge carry direction/role? does the assay edge carry replicate count, normalisation method?). This sets up Part 4 questions and Part 5 KG asks.
- **Transport.** TcdbFamily count, gene-family edge count, family→metabolite edge count, family_inferred vs substrate_confirmed split (count of (gene, metabolite) pairs at each tier).
- **Reaction.** Reaction count, gene-reaction edge count, reaction-metabolite edge count, distribution of reactions per gene and metabolites per reaction.
- **Measurement.** `MetaboliteAssay` total + by experiment + by publication + quantified-vs-flagged split + metabolite count per assay; coverage by organism, background factor (growth_phase), treatment_type, compartment.

This part is a fact-finding exercise. No prescriptive content.

#### Part 2 — Chemistry-annotation surface (existing tools)

Per-tool table covering tools that arguably should surface chemistry rollups but do not, plus tools that already do (with notes on completeness):

| Tool | Current chemistry surfacing | Recommended change | Priority | Phase |
|---|---|---|---|---|

Tools to evaluate at minimum: `gene_details`, `gene_overview`, `gene_response_profile`, `differential_expression_by_gene`, `differential_expression_by_ortholog`, `gene_homologs`, `genes_by_homolog_group`, `search_homolog_groups`, `gene_clusters_by_gene`, `genes_in_cluster`, `list_clustering_analyses`, `gene_derived_metrics`, `genes_by_numeric_metric`, `genes_by_boolean_metric`, `genes_by_categorical_metric`, `list_derived_metrics`, `list_publications`, `list_experiments`, `list_organisms`, `list_filter_values`, `genes_by_function`, `genes_by_ontology`, `gene_ontology_terms`, `kg_schema`, `pathway_enrichment`, `cluster_enrichment`, `resolve_gene`, `run_cypher`.

Priority: **P0** (blocks correct LLM answers on common questions) / **P1** (meaningful coverage gain) / **P2** (polish) / **P3** (defer).

Phase: **first-pass** (obvious add identified before building the analysis doc / example python) / **build-derived** (surfaced or validated during the build).

#### Part 3 — Metabolomics-measurement surface (greenfield)

Two subsections.

**3a — Existing-tool modifications.** Same table shape as Part 2 (including Phase column), scoped to measurement-side rollups. Tools to evaluate at minimum: `list_metabolites` (e.g., `measured_in_experiments` envelope rollup, per-row `assay_count` / `quantified_in` / `flagged_in`), `list_publications` (MetaboliteAssay counts per row when `omics_type` includes METABOLOMICS), `list_experiments` (same), `list_organisms` (measurement-capability rollup), `kg_schema` (confirm new node/edge types appear), `list_filter_values` (compartment values now include extracellular).

**3b — New-tool proposals.** One paragraph + signature sketch per candidate, plus `{recommendation, phase}`. Initial first-pass candidates to evaluate (build-derived candidates added in the second pass):

- `list_metabolite_assays` — discovery surface mirroring `list_experiments` but per-MetaboliteAssay.
- `metabolite_response_profile` — cross-experiment per-metabolite summary mirroring `gene_response_profile`.
- `metabolites_by_assay` / `assays_by_metabolite` — drill-down pair.
- `differential_metabolite_abundance` — DE-shaped tool. Likely **Pending-definition** because FC may not be the right semantic for metabolomics (raw concentrations, presence/absence, normalisation choices all open).
- DM-family extension to Metabolite entity — adding `Metabolite` as a target alongside `Gene` for the existing DM tool family (`list_derived_metrics`, `gene_derived_metrics`, `genes_by_*_metric`). Whether this is the right model is itself a Part 4 question.

Recommendation: **Must-add** (required for measurement-track usability) / **Should-add** (fills a clear question class) / **Nice-to-have** (convenience) / **Pending-definition** (depends on Part 4 resolution) / **Not-needed** (explicitly rejected).

Phase: **first-pass** (obvious from initial gap analysis — e.g., a node type with no discovery tool) / **build-derived** (surfaced because the analysis doc or example python revealed an unmet workflow need).

Each Pending-definition entry must name the specific Part 4 question(s) it depends on. Each build-derived entry must name the doc/example scenario that surfaced it.

#### Part 4 — Open definition questions

The blockers. Each question is stated, options enumerated where known, downstream impact noted.

Organised by metabolite-source pipeline.

**Reaction (KEGG) source:**
- Are reaction edges directional? Do they distinguish substrate vs product, or just "involved in"? If undirected, can `metabolites_by_gene` honestly report "this gene produces X" — or only "X is involved in a reaction this gene catalyses"?
- Is reversibility represented? KEGG often marks irreversible reactions; is this surfaced?
- How are multi-subunit enzymes attributed? One reaction per subunit, or shared across subunits?

**Transport (TCDB) source:**
- Is transport direction (import vs export) representable? Some TCDB families have known directionality; is it captured?
- For ABC superfamily and similar promiscuous families, is there a curated "primary substrate" property to soft-rank against the family-inherited list?

**Metabolomics measurement source:**
- Is metabolite measurement modelled as a `DerivedMetric` on `Metabolite`, a first-class `MetaboliteAssay` surface, or both? What does the LLM-facing surface look like in each option?
- Is fold-change the right summary statistic for metabolomics, or do we need a different convention (raw concentration, log-transformed concentration, presence/absence, ratio, fold-change-when-applicable)? What does each metabolomics paper's processed output actually contain? **(User flagged FC may not be relevant for metabolomics.)**
- How are replicates rolled up? Mean ± SD? Median? Per-replicate rows? If processed values are only available at the publication level, can we still surface raw values?
- How do `Assay_quantifies_metabolite` and `Assay_flags_metabolite` differ in semantics? Is `flags` qualitative detection (presence/absence) and `quantifies` quantitative (concentration)? Should they be separate response columns or merged with a discriminator?
- Compartment semantics for extracellular: is "extracellular metabolite" the same entity as the same-named intracellular metabolite (with compartment as a property), or distinct nodes? How does this affect the chemistry-annotation tools' compartment filter?
- Replicate / temporal axis: do metabolomics experiments share the timepoint structure of expression experiments, or have a different time axis?
- Cross-organism comparability: when both partners are profiled in a coculture experiment, how is metabolite assignment (which partner produced/consumed) handled, if at all?

#### Part 5 — KG-side asks

Items only `multiomics_biocypher_kg` can fix, captured in the same shape as the existing `2026-05-XX-kg-side-*-asks.md` docs. Each ask carries `{category, priority, phase, why}`.

**Categories** (descriptive — what kind of change):

- **Data gap** — missing property/edge/node that the explorer cannot derive (e.g., reaction directionality flag, replicate count on Assay edges).
- **Precompute** — analytic computed once at KG build time so the explorer can read it without query-time aggregation (e.g., per-Metabolite `family_inferred_only` flag, per-TcdbFamily promiscuity score).
- **Rollup** — pre-aggregated denormalisation served on a node so envelope rollups don't require traversal at query time (e.g., per-Metabolite `assay_count` / `experiments_measured` / `quantified_in` / `flagged_in`; per-Publication `metabolite_assay_count`).
- **Index** — Neo4j b-tree or full-text index added to make a current/proposed query feasible at scale.
- **Schema** — node/edge label changes, property type changes (e.g., compartment-as-property vs compartment-as-distinct-node decision).
- **Decision** — a modelling decision the KG side must make, surfaced from Part 4 with an explorer-side recommendation.
- **Documentation** — gap in the KG schema doc or convention doc that affects what the explorer can correctly tell the LLM.

**Priority taxonomy** (impact — what does it unblock):

- **P0** — blocks a Must-add explorer tool. Without this, the tool cannot be built.
- **P1** — significantly improves a Should-add tool's quality or LLM-readability (e.g., enables a richer envelope rollup, removes a caveat).
- **P2** — performance: precomputes / rollups / indexes that make a feasible-but-slow tool usable at scale, OR performance fixes for existing tools that became hot after metabolomics added paths.
- **P3** — nice-to-have polish.

**Phase** (when the ask was identified):

- **first-pass** — obvious before the analysis doc / example python build (e.g., from §1 caveats or Part 1 KG inventory).
- **build-derived** — surfaced or validated by the build (e.g., scenario X needed property Y that doesn't exist).

**Initial candidates** (audit phase will expand and assign category+priority):

- Replicate count, normalisation method, raw-vs-processed flag on `Assay_quantifies_metabolite` / `Assay_flags_metabolite` (Data gap).
- Compartment-as-property vs compartment-as-distinct-node (Schema + Decision; resolves Part 4 compartment question).
- Reaction edge directionality / role (substrate vs product) (Data gap or Schema; resolves Part 4 reaction-direction question).
- Per-Metabolite rollup properties for the existing `list_metabolites` tool (`assay_count`, `experiments_measured`, etc.) (Rollup).
- Per-Publication and per-Experiment metabolomics-capability rollups for existing discovery tools (`metabolite_assay_count`, distinct-metabolite-measured count) (Rollup).
- TCDB family promiscuity precompute (e.g., `is_superfamily` flag or substrate-count-percentile) so `metabolites_by_gene` can rank/dim family_inferred rows more cleanly (Precompute).
- Full-text or b-tree indexes on any new query paths the proposed tools would hit (Index — defer specific entries until proposed tool signatures stabilise).

This section is the explicit hand-off to the KG side. Each ask names its blocking explorer tool / friction in the **why** field. Asks with **Decision** category are paired with the corresponding Part 4 question. Each build-derived ask names the scenario or workflow that surfaced it.

---

### 3.2 Analysis doc

**Path:** `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md`

Hand-authored markdown (analysis docs are NOT generated; see CLAUDE.md). LLM-targeted: terse, decision-tree-shaped, mirrors the style of `enrichment.md`.

Structure:

1. **Source disambiguation table** — leads the doc. Three rows keyed on the three Metabolite-source pipelines, with caveats first-class:

   | `evidence_source` | Path | Question it answers | Native tools | Key caveats |
   |---|---|---|---|---|
   | `metabolism` | Gene → Reaction → Metabolite (KEGG) | Which metabolites can this gene catalyse? | `genes_by_metabolite`, `metabolites_by_gene` | KO inference may be putative; reaction direction modelling (Part 4); promiscuous enzymes inflate counts |
   | `transport` | Gene → TcdbFamily → Metabolite (TCDB) | Which metabolites does this gene transport (or could transport, family-inferred)? | `genes_by_metabolite`, `metabolites_by_gene` | family_inferred ≫ substrate_confirmed; ABC superfamily promiscuity; no import/export direction |
   | `metabolomics` | MetaboliteAssay → Metabolite (mass-spec) | Which metabolites were measured under this condition? | None native (run_cypher) | No gene anchor; detection vs quantification; compartment; targeted panel ≠ full metabolome; replicate/normalisation conventions vary |

   The LLM reads this first and routes accordingly. Each subsequent track section restates its caveat row's gotchas inline.

2. **Track A1 — Reaction (KEGG) annotation (fully tooled).** Workflows that focus on the metabolism arm of `genes_by_metabolite` / `metabolites_by_gene`. Covers:
   - a. Metabolite discovery & filtering (`list_metabolites`)
   - b1. Reaction-anchored: compound → genes via `evidence_sources=['metabolism']`
   - c1. Reaction-anchored: gene → metabolites via `evidence_sources=['metabolism']`; element signature; reaction-pathway distinction in `top_pathways`
3. **Track A2 — Transport (TCDB) annotation (fully tooled).** Workflows that focus on the transport arm. Covers:
   - b2. Transport-anchored: compound → genes via `evidence_sources=['transport']`
   - c2. Transport-anchored: gene → metabolites via `evidence_sources=['transport']`
   - g. Precision-tier reading (family_inferred-dominance auto-warning, `transport_confidence` filter)
4. **Track A — Combined annotation workflows.** Workflows that cross both annotation arms or downstream from them:
   - d. Cross-feeding bridge — Workflow B' (`metabolites_by_gene` → `genes_by_metabolite(organism=PARTNER)`)
   - e. N-source / nutrient-class workflow (`metabolite_elements`)
   - f. Ontology bridges (TCDB substrate-anchored, KEGG pathway-anchored)
5. **Track B — Metabolomics measurement (partially tooled).** Short section. Covers:
   - Discovery via `list_experiments(omics_types=['METABOLOMICS'])` and `list_publications(...)` with the METABOLOMICS filter.
   - Annotated `run_cypher` patterns for assay→metabolite and metabolite→assay traversals.
   - Caveat surfacing: how to read `Assay_quantifies` vs `Assay_flags`, compartment-aware filtering, replicate handling.
   - Banner: native tools pending; see audit doc for the planned surface.

The doc points to `docs://examples/metabolites.py` for runnable patterns.

---

### 3.3 Example python

**Path:** `examples/metabolites.py`

Registered statically in `multiomics_explorer/mcp_server/server.py` as `docs://examples/metabolites.py` (mirroring the `pathway_enrichment.py` pattern at server.py:91-99). Listed in `examples/README.md`. Exercised by `tests/integration/test_examples.py` under `-m kg`.

Eight scenarios. Each scenario is a function with a docstring stating the trigger condition ("Use this when the user asks ‹X›") and prints intermediate envelope state in addition to final results. Every scenario's docstring also names the metabolite-source caveat it surfaces, so the LLM learns the caveat alongside the workflow.

| # | Scenario | Calls | Source(s) | Caveat surfaced |
|---|---|---|---|---|
| 1 | Discover metabolites by element + pathway filter | 1 | reaction + transport | None specific (discovery) |
| 2 | Compound → genes, reading evidence_source split | 1 | reaction + transport | metabolism vs transport semantics differ; row counts not comparable |
| 3 | Gene → metabolites, reading element signature + top_pathways | 1 | reaction + transport | reaction-pathway in `top_pathways` ≠ KEGG-KO pathway from `genes_by_ontology` |
| 4 | Cross-feeding bridge MED4 → ALT | 2 | reaction + transport | direction-of-cross-feeding not in KG (KG is annotation-only) |
| 5 | N-source primitive → DE | 2-3 | reaction + transport → expression | promiscuous enzymes / family_inferred can inflate the gene set fed to DE |
| 6 | TCDB ontology → metabolite chain | 2 | transport | family_inferred dominance for promiscuous families |
| 7 | Precision-tier interpretation (family_inferred warning) | 1 | transport | the auto-warning itself; ABC superfamily example |
| 8 | Metabolomics measurement query (run_cypher) | 1 | measurement | no gene anchor; `Assay_quantifies` vs `Assay_flags`; compartment; targeted panel |

CLI scenario selector mirrors `pathway_enrichment.py`: `uv run python examples/metabolites.py --scenario <name>`.

## 4. Priority / recommendation taxonomies

Existing-tool changes (Audit Parts 2 and 3a):

- **P0** — blocks correct LLM answers on common questions
- **P1** — meaningful coverage gain
- **P2** — polish
- **P3** — defer / re-evaluate later

New-tool proposals (Audit Part 3b):

- **Must-add** — required for measurement-track usability
- **Should-add** — fills a clear question class
- **Nice-to-have** — convenience
- **Pending-definition** — depends on a Part 4 question; the entry must name which one(s)
- **Not-needed** — explicitly rejected (saves time later)

KG-side asks (Audit Part 5) carry `{category, priority, phase}`:

- **Categories**: Data gap / Precompute / Rollup / Index / Schema / Decision / Documentation (see Part 5 for definitions).
- **Priority**: **P0** (blocks Must-add tool) / **P1** (significantly improves Should-add tool) / **P2** (performance — precomputes / rollups / indexes for feasibility at scale) / **P3** (polish).
- **Phase**: see "Discovery phase" below.

Discovery phase (applied uniformly to Audit Parts 2, 3a, 3b, 5):

- **first-pass** — obvious add identified before building the analysis doc and example python. Populated in the audit's first pass.
- **build-derived** — surfaced or validated by building the analysis doc / example python. Populated in the audit's second pass; entry names the doc section or example scenario that surfaced it.

This axis is orthogonal to category and priority. It captures *how confident* we are in the recommendation: first-pass items came from analysis; build-derived items came from concretely trying to use the surface.

## 5. Order of work

Two-pass loop on the audit, with the analysis doc and example python in between.

1. Audit Part 1 (KG inventory queries via `run_cypher`).
2. **Audit first pass** — populate Parts 2, 3a, 3b, 5 with first-pass items only (obvious from §1 caveats and Part 1 numbers). Tag each row `phase=first-pass`.
3. Analysis doc (informed by Part 1 + first-pass audit).
4. Example python (instantiates analysis doc). While building, log:
   - Refinements to first-pass items (validated, downgraded, reshaped, or — exceptionally — dropped if misconceived).
   - Build-derived items: existing-tool gaps that emerge from writing scenarios, new-tool proposals justified by workflow pain, KG asks revealed by missing properties.
5. **Audit second pass** — apply refinements; append build-derived items tagged `phase=build-derived` with the doc section / scenario that surfaced each.
6. Register example python in `server.py`; add to `examples/README.md`; add to `tests/integration/test_examples.py`.
7. Walk-through with the user: examples and audit findings.

## 6. Out of scope

- Building any new tools. The audit produces proposals; build follows in separate cycles after definition resolves.
- Modifying existing tool implementations. The audit produces recommendations; mods follow.
- Resolving the Part 4 open definition questions. Those are user-driven conversations with the KG side.
- Generating MCP tool YAML/Pydantic changes. None are needed for this effort.

## 7. Acceptance criteria

**Audit doc:**
- All five parts present and populated.
- Part 1 shows live KG counts with reproducible Cypher.
- Parts 2 and 3a have `{priority, phase}` on every row.
- Part 3b has `{recommendation, phase}` on every proposal; every Pending-definition entry names its blocking Part 4 question; every build-derived entry names its surfacing doc section / example scenario.
- Part 5 has `{category, priority, phase, why}` on every KG-side ask. Each Decision-category ask is paired with its Part 4 question; each build-derived ask names its surfacing scenario.
- Build-derived items in any part are clearly distinguishable from first-pass items (e.g., separate sub-tables, sort order, or explicit phase column).

**Analysis doc:**
- Three-row source-disambiguation table (reaction / transport / measurement) is the first content block, and includes a caveats column.
- Tracks A1 (reaction-anchored), A2 (transport-anchored), and A combined cover all approved workflow identifiers (a, b1, b2, c1, c2, d, e, f, g).
- Track B has the run_cypher patterns, the caveat surfacing (Quantifies vs Flags, compartment, replicates), and the audit-doc banner.
- Doc is registered as `docs://analysis/metabolites` (verified by the auto-registration loop in server.py:71-86 — no code change needed; just file presence under `references/analysis/`).

**Example python:**
- All 8 scenarios runnable individually via `--scenario`.
- Registered statically in `server.py` (mirroring pathway_enrichment.py).
- Listed in `examples/README.md`.
- Test added to `tests/integration/test_examples.py` exercising each scenario under `-m kg`.

## 8. Risks

- KG inventory queries may hit unindexed paths and time out. Mitigation: use `run_cypher` with `LIMIT` on exploratory queries; fall back to property-existence counts if full path traversals are slow.
- Metabolomics edges may carry properties not yet documented in `kg_schema` output. Mitigation: Part 1 includes an explicit edge-property inventory step before any aggregation.
- The audit may surface a Part 4 question whose answer changes Track B's recommended `run_cypher` pattern in the example python. Mitigation: example python is built last; if a Part 4 answer arrives mid-build, defer scenario 8 and ship the chemistry-only example.
- Test execution time on `examples/metabolites.py` may grow beyond the existing budget. Mitigation: scenario 5's 2-3 step chain uses small `limit=` values; if needed, gate the slowest scenarios under a separate marker.
