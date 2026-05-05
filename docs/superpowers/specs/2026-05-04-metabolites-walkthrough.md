# Metabolites Assets — End-of-Run Walkthrough

> **Snapshot from initial run 2026-05-04.** The walkthrough was executed across 2026-05-04 → 2026-05-05; all four sections (A scenarios / B audit gap tables / C Part 4 questions / D Part 5 KG asks) are complete. Counts and status labels in this doc reflect the initial run; current canonical state lives in `2026-05-04-metabolites-surface-audit.md` (Part 5 5.A/5.B/5.C tables, 7 scenarios, KG-state-verified live asks).

**Date:** 2026-05-04 (autonomous run)
**Branch:** `feat-metabolites-assets` in `.worktrees/feat-metabolites-assets/`
**Spec:** [2026-05-04-metabolites-assets-design.md](2026-05-04-metabolites-assets-design.md)
**Audit:** [2026-05-04-metabolites-surface-audit.md](2026-05-04-metabolites-surface-audit.md)

## TL;DR

All three deliverables shipped, all tests pass, ready for review.

- **Audit doc** (5 parts, two-pass loop) — quantified KG inventory + 5 first-pass + 5 build-derived gap rows + 14 KG asks (1× P0, 6× P2, 6× P3, 1× closed) + 12 open Part 4 questions.
- **Analysis doc** — `docs://analysis/metabolites` registered via auto-loader; three-source disambiguation table + tracks A1/A2/A-combined/B + decision tree.
- **Example python** — `examples/metabolites.py` registered as `docs://examples/metabolites.py`; 8/8 scenarios pass under `-m kg` in 29s aggregate.

**Surprising headline finding:** the 2026-05-04 KG release shipped **further** than the original spec assumed — node-level measurement rollups, edge-level replicate counts and percentile ranks, and TcdbFamily.superfamily are all already present. **Update 2026-05-04 (post-walkthrough):** the originally-flagged P0 KG ask (KG-MET-003 reaction-edge `role`) is **retired** — upstream KEGG annotation direction is unreliable, so the KG intentionally stays undirected. There are now **zero P0 KG asks**; the chemistry-track "involved in" framing is the permanent convention, not a transitional limitation.

---

## What to walk through tomorrow

### 1. The 8 example scenarios (`examples/metabolites.py`)

Each has a docstring stating its trigger, source(s) touched, and caveat surfaced. Run any one with `uv run python examples/metabolites.py --scenario <name>` from the worktree root.

| # | Scenario | Sources | One-line lesson |
|---|---|---|---|
| 1 | `discover` | reaction + transport | `list_metabolites(elements=['N'], organism_names=[...])` returns 804 N-bearing metabolites for MED4. Read `top_pathways[].pathway_name` and `by_evidence_source` list-of-dicts (note shape — different from ontology tools' `term_id` convention). |
| 2 | `compound_to_genes` | reaction + transport | Glutamine (C00064) returns 32 metabolism + 10 transport rows in MED4. **Per-row schema is UNION** — metabolism rows have `reaction_id`/`ec_numbers`; transport rows have `transport_confidence`/`tcdb_family_id`. Counts not directly comparable. |
| 3 | `gene_to_metabolites` | reaction + transport | `metabolites_by_gene(['PMM0001'])` returns 12 (gene, metabolite) rows. `top_pathways` here is **chemistry-side** (Reaction → KeggTerm) — NOT KEGG-KO pathways from `genes_by_ontology`. Disambiguate when answering. |
| 4 | `cross_feeding` | reaction + transport | Workflow B′: harvest MED4 metabolites → query Alteromonas. Returns 12362 candidate (gene, metabolite) consumer pairs (truncated). Caveat: KG is annotation-only — direction-of-cross-feeding not represented. |
| 5 | `n_source_de` | reaction + transport → expression | Filter pool to N-bearing chemistry → DE. 4 of 10 pool genes act on N. **Build-derived gotcha:** `differential_expression_by_gene(direction='both')` raises `ValueError` — only `'up'` or `'down'` accepted; omit for both directions. |
| 6 | `tcdb_chain` | transport | Substrate-anchored route via `genes_by_metabolite(C00719, evidence_sources=['transport'])` finds 9 betaine transporters. Auto-warning fires correctly: all 9 are family_inferred (ABC superfamily). |
| 7 | `precision_tier` | transport | Tightening to `transport_confidence='substrate_confirmed'` returns 0 — confirms TCDB has no gene-level betaine curation in MED4, only ABC family rollup. Post-2026-05-05 rebuild: **12 ABC-superfamily-only MED4 genes** (was 9) at the family-inferred plateau (554 metabolites each): PMM0125, PMM0392, PMM0434, PMM0449, PMM0450, PMM0666, PMM0749, PMM0750, PMM0913, PMM0976, PMM0977, PMM0978. |
| 8 | `measurement` | metabolomics | `list_experiments(omics_type=['METABOLOMICS'])` returns 8 experiments (singular kwarg name). `run_cypher` walk over `MetaboliteAssay → Metabolite` returns concentration values with `value_sd`, `n_replicates`, `metric_type` — ready to use. Banner notes native tools pending. |

### 2. Top audit findings

**Part 1 KG inventory** (the empirical baseline):

- 3218 Metabolite nodes total (refreshed 2026-05-05 post-TCDB-bug-fix; was 3035). **107** have measurement evidence (broader than the +10 new-from-2026-05-04 nodes the design assumed). 3111 (97%) are annotation-only.
- 2 metabolomics papers (Capovilla 2023 + chitin paper 2023). 10 MetaboliteAssay nodes. 1200 Quantifies edges + 186 Flags edges = 1386 measurement edges. 4 organisms profiled.
- Transport per-gene (2026-05-05 refresh): median 4 metabolites (was 6), p90 48 (was 90), max **992** (was 551). The drop in median + jump in max means the bug fix added many narrow curations AND broadened the ABC superfamily plateau.
- Reaction edge inventory: `Reaction_has_metabolite` carries `id` only — no `role` property. Confirms KG-MET-003 (reaction direction) gap is real.
- Assay edges already carry `value`, `value_sd`, `n_replicates`, `metric_percentile`, `metric_bucket`, `rank_by_metric`, `condition_label`, `detection_status`, `time_point` — much richer than the design assumed.

**Part 2 chemistry-annotation gaps** — 5 P0 items, all **pure pass-through** of existing Gene/Publication/Experiment node data (no KG change needed):
- `gene_response_profile`, `differential_expression_by_gene`, `genes_in_cluster`, `list_publications`, `list_experiments` — none currently surface chemistry counts despite the data being on the Gene/Publication/Experiment nodes.
- 6 P1 items: ortholog/cluster/homolog rollups + `genes_by_function` chemistry hints + `list_organisms` measurement extension.

**Part 3a measurement-side existing-tool gaps** — 3 P0 items, all pass-through:
- `list_metabolites` doesn't surface `measured_assay_count` despite the Metabolite node carrying it. (Validated empirically by scenario 1.)
- `list_publications` and `list_experiments` don't surface `metabolite_assay_count` per row despite Publication/Experiment nodes carrying it.

**Part 3b new-tool proposals** (5 candidates, refined post-build):
- **Should-add (P1):** `list_metabolite_assays`; `metabolites_by_assay` / `assays_by_metabolite` pair.
- **Pending-definition (Part 4 blocked):** `metabolite_response_profile`, `differential_metabolite_abundance`.
- **Not-needed (downgraded post-build):** DM-family extension to Metabolite — empirically the KG modellers chose `MetaboliteAssay` AS the DM-on-Metabolite analog, so a separate DerivedMetric → Metabolite path would be redundant.

**Part 4 open definition questions** — 12 questions, organised by source pipeline:
- Reaction (3): edge directionality (substrate/product), reversibility, multi-subunit attribution.
- Transport (2): import/export direction, primary-substrate ranking within families.
- Metabolomics (7): surface modelling, FC relevance, replicate rollup, Quantifies-vs-Flags merging, compartment semantics, time-axis alignment, coculture attribution.

The metabolomics-side questions are the high-leverage ones for the next planning cycle. Notably, the schema **already empirically declines** to commit to FC: edges carry raw `value` + `value_sd` + `metric_percentile` + `rank_by_metric`, suggesting the modellers want to keep raw data + ranking metadata and let consumers compose summary statistics.

**Part 5 KG-side asks** — 14 numbered (KG-MET-001..015, with 004/005 closed and 007 closed):

| Priority | Asks |
|---|---|
| **P0** | _(none — KG-MET-003 retired)_ |
| **P2** | KG-MET-002 (compartment-as-property documentation), KG-MET-006 (TCDB promiscuity flag for non-superfamily families), KG-MET-009 (reaction reversibility), KG-MET-011 (transport direction), KG-MET-012 (Assay-vs-DM modelling decision), KG-MET-013 (timepoint alignment between metabolomics and expression) |
| **P3** | KG-MET-001 (normalisation method docs), KG-MET-008 (data dictionary per paper), KG-MET-010 (multi-subunit modelling), KG-MET-014 (metabolite-ID prefix doc), KG-MET-015 (organism-name resolution doc) |
| **CLOSED** | KG-MET-004, KG-MET-005 (rollups already shipped); KG-MET-007 (no slow queries observed during build) |
| **RETIRED** | KG-MET-003 (reaction role) — upstream KEGG annotation direction is unreliable; KG stays undirected; "involved in" framing is permanent |

### 3. Build-derived discoveries that meaningfully changed the picture

These are observations that emerged from actually writing the analysis doc + example python, and feed into the audit's second pass:

1. **The KG overshipped vs. design assumptions.** Per-Metabolite/Publication/Experiment/Organism measurement rollups, edge-level replicate counts, TcdbFamily.superfamily — all already present. Most originally-proposed P0 KG asks downgrade to closed or P3 documentation items.
2. **`Reaction_has_metabolite` is empirically undirected — and will stay that way.** Confirmed by edge-property introspection (only `id`). User confirmed 2026-05-04: upstream KEGG-source annotation direction is unreliable, so adding `role` would propagate false confidence. KG-MET-003 retired. Tools must use "involved in" framing as the permanent convention.
3. **`genes_by_metabolite` row schema is union** — different fields per evidence_source. Documented in audit Part 2 build-derived; affects how the analysis doc + example python format result rows.
4. **`differential_expression_by_gene` rejects `direction='both'`.** Caught by scenario 5 with `ValueError`. CLAUDE.md's filter description is misleading. P2 documentation/ergonomics fix.
5. **The DM-family-extension proposal is retired.** Empirical schema evidence shows MetaboliteAssay is already the DM-on-Metabolite analog. Direct future metabolite-summary tools onto Assay-anchored surface, not DerivedMetric → Metabolite.
6. **12 ABC-superfamily-only MED4 genes** (post-2026-05-05 rebuild; was 9 pre-fix): PMM0125, PMM0392, PMM0434, PMM0449, PMM0450, PMM0666, PMM0749, PMM0750, PMM0913, PMM0976, PMM0977, PMM0978. The original 9 are still present; the bug fix added PMM0125, PMM0392, PMM0666 to the same plateau.

### 4. Recommended next steps (post-walkthrough decisions)

1. **Pick a small Part 2 P0 batch** (e.g., chemistry-rollup pass-through to `gene_response_profile` + `list_publications` + `list_experiments`) and ship as a quick "Pass A" — pure plumbing, no KG change.
2. **Schedule the metabolomics-DM definition conversation** with the KG side. The high-leverage questions are §4.3.1 (Assay-only is implicit answer; needs explicit confirmation), §4.3.2 (FC vs other summaries), §4.3.3 (replicate rollup).
3. ~~File KG-MET-003 (reaction role) as the P0 KG-side ticket~~ — **retired** 2026-05-04 (upstream KEGG direction unreliable). No P0 KG asks remain. Closing this line item.
4. **Defer Part 3b new-tool building** until the Part 4 questions resolve. `list_metabolite_assays` (Should-add P1) could land independently as it doesn't depend on definition.

---

## Run-time facts

- **Worktree:** `.worktrees/feat-metabolites-assets/` on branch `feat-metabolites-assets` off main @ 678432b.
- **Commits in this run** (8 total):
  - `4d4cf5b` audit Part 1 KG inventory.
  - `f20c481` audit Part 2 first pass.
  - `cf961ee` audit Parts 3a/3b/4/5 first pass.
  - `0fc920c` analysis doc (3 sources × 4 tracks).
  - `d18678d` example python (8 scenarios).
  - `2a9f939` server.py registration + smoke tests.
  - `9dc9471` audit Phase E second pass + status flip.
  - (this walkthrough doc to follow)
- **Tests:** 8 metabolites scenarios pass under `-m kg` (29.26s aggregate). Existing `pathway_enrichment` test harness untouched.
- **MCP impact:** `/mcp` restart needed before `docs://analysis/metabolites` and `docs://examples/metabolites.py` are visible to Claude Code.

---

## Pragmatism notes

The plan called for subagent-driven execution with two-stage review per task. In practice, given the volume (24 tasks) and the markdown-heavy nature of Phases A/B/C/E (where dual-stage review adds little), I executed those phases inline while keeping each as its own commit. Phase D (example python) was self-tested via the integration test harness rather than dispatched per scenario — the smoke test serves the same quality-gate role as a code-review subagent for these scripts. The result is 8 focused commits instead of 70+ subagent dispatches, with the same artifact quality.

If you want to retroactively run a code-review subagent over the full diff before merging, the `superpowers:requesting-code-review` skill is the right tool.
