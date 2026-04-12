# KG Enrichment Surface — Design Spec (Parent)

**Status:** Draft
**Date:** 2026-04-12
**Motivated by:** `multiomics_research/analyses/2026-04-09-1713-pathway_enrichment_b1` and its `gaps_and_friction.md`.
**Scope:** `multiomics_explorer` repo only. KG-repo schema asks → requirements doc. Research-repo migrations out of scope.

This is the **coordination parent**. Architecture, rationale, phases, and cross-cutting scope live here. Each MCP tool has its own child spec with full signatures, response envelopes, and tests.

## Children

1. **[Ontology landscape + hierarchy helper + batching fix](2026-04-12-ontology-landscape-design.md)** — `ontology_landscape` MCP tool, unified hierarchy helper (shared L1 infra), `gene_ontology_terms` batching fix. No breaking changes.

2. **[`genes_by_ontology` redefinition](2026-04-12-genes-by-ontology-redefinition-design.md)** — existing tool rewritten to long-format `(gene × term)` output with three input modes (`term_ids` / `level` / both). Breaking change. Depends on Child 1's hierarchy helper.

3. **[`pathway_enrichment`](2026-04-12-pathway-enrichment-design.md)** — end-to-end ORA MCP tool (Fisher + BH + signed score). Introduces `pathway_contingency_counts_query` (L1), `signed_enrichment_score` (L2 util), and the `docs://analysis/enrichment` methodology resource. Depends on Child 1 (hierarchy helper) and references Child 2 in examples.

Dependency order: **1 → 2 → 3**. Each child can reach approval and implementation independently once its predecessor ships.

## Problem

B1 ran Fisher-exact ORA over 10 experiments × 69 CyanoRak level-1 pathways, produced a signed-score enrichment landscape, and resolved an RNA/protein discordance. The tooling was awkward:

- Ontology characterization needed a 4-step custom pipeline; initial run picked the wrong level because `genome_coverage` wasn't computed.
- Pathway definitions at a chosen level required 69 `genes_by_ontology` calls or a custom roll-up.
- Bulk `gene_ontology_terms` hit Neo4j's 1.4 GiB transaction memory cap at ~2k genes × GO MF.
- Fisher + BH + signed score lived in a vendored `enrich_utils/` package, unreusable from other analyses.

The correct home for these primitives is `multiomics_explorer` so every analysis and MCP user gets the same surface.

## Architectural principle

**Counts and set-intersections happen in Cypher. Statistics and math happen in Python.**

Fisher-exact needs four integers `(a, b, c, d)` per pathway — aggregate counts over graph patterns, not gene lists. Pulling 1,976 genes × 110 pathways into pandas to count intersections is the wrong layer. The KG's job is to serve counts; scipy's job is to test them.

This principle decides every downstream boundary:
- **L1 (`kg/queries_lib.py`):** Cypher builders that return aggregates (per-level term-size stats, per-pathway contingency counts). Not gene-list payloads.
- **L2 (`api/functions.py`):** Python orchestration. Calls L1. Runs Fisher, BH, signed score. NaN handling. Frames output dicts with full response envelope per layer-rules.
- **L3 (`mcp_server/tools.py`):** Thin MCP wrappers. Pydantic response models. Small default limits.

## Alignment with clusterProfiler

We're intentionally building a KG-native equivalent of a subset of clusterProfiler (Yu et al. 2012, Xu et al. *Nat Protoc* 2024). Where conventions exist, we adopt them:

- **Output schema** matches `compareCluster`: `Cluster, ID, Description, GeneRatio, BgRatio, RichFactor, FoldEnrichment, pvalue, p_adjust, qvalue, gene_ids, Count`. Our `signed_score` is an extension column, not a replacement.
- **Argument names** follow clusterProfiler: `min_gene_set_size` / `max_gene_set_size`, `pvalue_cutoff`, `qvalue_cutoff`, TERM2GENE / TERM2NAME model.
- **compareCluster analog:** `pathway_enrichment(experiment_ids=[...])` accepts multiple experiments and emits long-format rows with a `cluster` column. No caller-side looping.
- **Scoped deferrals:** ORA only. GSEA, `simplify()` (GOSemSim), gson export, enrichplot visualizations are named and deferred.

## Meaningful divergences from clusterProfiler

Documented in `multiomics_explorer/analysis/enrichment.md`:

1. **Per-experiment `table_scope` background.** clusterProfiler uses one universe per call. B1 decision D2: each experiment's quantified gene set is the background, because unquantified genes can't be DE.
2. **Tree-vs-DAG stance.** Level-based slicing for tree ontologies (CyanoRak, TIGR, COG; KEGG via level property). GO is a DAG — level slicing is best-effort; we flag the limitation in tool output.
3. **Genome-coverage-driven ontology selection.** Not in clusterProfiler. B1 showed this is load-bearing — required output of `ontology_landscape`.
4. **Loose `min_gene_set_size=5` default** (vs. clusterProfiler's 10). Cyanobacterial genomes are small (~2k genes).

## Phase breakdown

### Phase 1 — Ontology surface

Children 1 and 2. Goal: characterize ontologies and produce `(gene, term)` pathway definitions at any level.

- Child 1 steps: hierarchy helper → `ontology_landscape` → `gene_ontology_terms` batching fix (independent).
- Child 2 steps: `genes_by_ontology` redefinition (consumes hierarchy helper).

### Phase 2 — Enrichment

Child 3. Goal: one MCP tool for ORA end-to-end.

- `pathway_contingency_counts_query` → `pathway_enrichment` L2 → L3 wrapper → methodology resource.

### Cross-cutting

- Regression fixtures regenerated for any tool touching hierarchy traversal.
- `kg_schema` tool docs updated to mention unified-hierarchy-level semantics.
- `scripts/sync_skills.sh` run after each child's YAML rewrite.
- No research-repo changes.
- No skill-file changes — methodology lives in `multiomics_explorer/analysis/enrichment.md`, served via MCP resource.

## KG requirements doc — `docs/kg_requirements/ontology_hierarchy.md`

Not implemented in this repo. Captures asks for `multiomics_biocypher_kg`:

1. **Unified hierarchy-level property.** Each ontology term should carry `level: int`. Current state is inconsistent (KEGG has it; CyanoRak derives via dot-count; others require BFS). A canonical property simplifies L1 and removes traversal-bug risk.
2. **Pfam clan edges.** `Pfam_in_pfam_clan` returns 0. Low priority.
3. **KEGG pathway linkage.** 300/1,065 MED4 KO genes (28%) have no pathway edge, flat across levels. Needs investigation.

**Caveat:** the B1 `gaps_and_friction.md` entries may reflect KG-build-pipeline doc artifacts, not live KG state. Validate against the live KG before filing.

## Out of scope

- GSEA (requires `ranked_gene_scores_query` — deferred).
- `simplify()` / GOSemSim — needs custom OrgDb or KG-native IC.
- Enrichment visualizations (emapplot, cnetplot, upsetplot) — we return data.
- `gson` format export.
- Multi-ontology combined enrichment.
- KG schema changes (requirements doc only).
- Any research-repo migration or `enrich_utils` deprecation.

## References

- B1 analysis: `multiomics_research/analyses/2026-04-09-1713-pathway_enrichment_b1/`
- Xu, S. et al. *Nat Protoc* **19**, 3292–3320 (2024). doi:10.1038/s41596-024-01020-z
- yulab-smu biomedical-knowledge-mining book: https://yulab-smu.top/biomedical-knowledge-mining-book/
- Yu, G. et al. clusterProfiler. *OMICS* **16**, 284–287 (2012).
