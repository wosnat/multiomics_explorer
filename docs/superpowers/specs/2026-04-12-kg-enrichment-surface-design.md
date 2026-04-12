# KG Enrichment Surface — Design Spec

**Status:** Draft
**Date:** 2026-04-12
**Motivated by:** `multiomics_research/analyses/2026-04-09-1713-pathway_enrichment_b1` and its `gaps_and_friction.md`.
**Scope:** `multiomics_explorer` repo only. KG-repo schema asks are captured as requirements docs, not implemented here. Research-repo migrations are out of scope.

## Problem

The pathway-enrichment B1 analysis ran Fisher-exact ORA over 10 experiments × 69 CyanoRak level-1 pathways, produced a signed-score enrichment landscape, and resolved an RNA/protein discordance question. The tooling required to get there was awkward:

- Ontology characterization needed a 4-step custom pipeline (extract → extract hierarchy → roll up → stats). The initial run selected the wrong hierarchy level because `genome_coverage` was not computed.
- Pathway definitions at a chosen level required either 69 separate `genes_by_ontology` calls or a custom roll-up.
- Bulk `gene_ontology_terms` hit Neo4j's 1.4 GiB transaction memory cap at ~2k genes × GO MF.
- Fisher + BH + signed score lived in a vendored `enrich_utils/` package that can't be reused from other analyses.

The research repo's `enrich_utils` is a local solution. The correct home for ontology-landscape characterization and pathway enrichment is the shared `multiomics_explorer` surface, so every analysis and MCP user gets the same primitives.

## Architectural principle

**Counts and set-intersections happen in Cypher. Statistics and math happen in Python.**

Fisher-exact on a pathway only needs four integers `(a, b, c, d)`: those are aggregate counts over graph patterns, not gene lists. Pulling 1,976 genes × 110 pathways into pandas to count intersections is the wrong layer. The KG's job is to serve counts; scipy's job is to test them.

This principle decides every downstream boundary:

- L1 (`kg/queries_lib.py`): Cypher builders that return aggregates. Per-level term-size stats. Per-pathway contingency counts. Not gene-list payloads.
- L2 (`api/functions.py`): Python orchestration. Calls L1. Runs Fisher, BH, signed score. NaN handling. Frames output DataFrames.
- L3 (`mcp_server/tools.py`): Thin MCP wrappers with summary fields.

## Alignment with clusterProfiler

We are intentionally building a KG-native equivalent of a subset of clusterProfiler (Yu et al. 2012, Xu et al. Nature Protocols 2024). Where conventions exist, we adopt them — so anyone coming from R recognizes the output immediately:

- **Output schema** matches `compareCluster` results: `Cluster, ID, Description, GeneRatio, BgRatio, RichFactor, FoldEnrichment, pvalue, p_adjust, qvalue, gene_ids, Count`. Our `signed_score` is added as an extension column, not a replacement.
- **Argument names** follow clusterProfiler: `min_gene_set_size` / `max_gene_set_size` (not `min_genes`), `pvalue_cutoff`, `qvalue_cutoff`, `show_category` (for summary truncation). TERM2GENE / TERM2NAME model shapes our `genes_at_ontology_level` output.
- **compareCluster analog:** `pathway_enrichment(experiment_ids=[...])` accepts multiple experiments in one call and emits long-format rows with a `cluster` column (= `experiment_id × timepoint × direction`). No caller-side looping.
- **Scoped deferrals:** ORA only in Phase 2. GSEA (rank-based), `simplify()` (GOSemSim DAG redundancy), gson export, enrichplot visualizations are all named and deferred.

## Meaningful divergences from clusterProfiler

These are intentional, documented in the methodology doc:

1. **Per-experiment `table_scope` background.** clusterProfiler uses a single universe per call. The B1 analysis (decision D2) uses each experiment's quantified gene set as the background for that experiment's tests, because an unquantified gene cannot be DE. The spec adopts `table_scope` as the default background.
2. **Tree-vs-DAG stance.** We build level-based hierarchy slicing natively (tree ontologies: CyanoRak, TIGR, COG; KEGG via level property). GO is a DAG; level slicing is best-effort. We flag the limitation in tool output rather than paper over it. DAG-aware methods (simplify, topGO-style elim/weight) are Phase 3+.
3. **Genome-coverage-driven ontology selection.** clusterProfiler does not compute genome_coverage. The B1 analysis showed this metric is load-bearing for hierarchy-level selection; we make it a required output of `ontology_landscape`.
4. **Loose min-gene-set-size default (5, not 10).** Cyanobacterial genomes are small (~2k genes); clusterProfiler's default excludes small pathways that matter here. Documented.

## New MCP tools

### `ontology_landscape(ontology, organism, experiment_ids=None)`

Characterize an ontology's suitability for enrichment on a given organism.

**Returns (per level):**
- `level` — integer hierarchy level
- `n_genes_at_level` — distinct genes reachable at this level
- `genome_coverage` — `n_genes_at_level / total_organism_genes`
- `n_terms_with_genes` — terms with ≥1 gene at this level
- `min_genes` / `q1_genes` / `median_genes` / `q3_genes` / `max_genes` — term-size distribution
- `example_terms` — top N terms by gene count with names
- If `experiment_ids` is set (option B chosen in brainstorm):
  - `min_exp_coverage`, `median_exp_coverage`, `max_exp_coverage` — aggregate of per-experiment coverage across the supplied experiments

**Sort order:** results returned sorted by relevance score (genome_coverage primary; `median_exp_coverage` as tie-breaker when `experiment_ids` is set).

**Summary:**
- `best_level` — level passing `genome_coverage ≥ 0.3` and `5 ≤ median_genes ≤ 50` with highest `genome_coverage`. Null if none qualify.
- `n_levels_qualifying`, `total_terms`.

### `genes_at_ontology_level(ontology, level, organism, term_ids=None, limit=None)`

Roll up gene annotations to a chosen hierarchy level. Batch-aware.

**Output:** long format, one row per `(locus_tag, term_id)` at the target level. Columns: `locus_tag, term_id, term_name, organism`.

**Summary:**
- `total_rows`, `n_genes`, `n_terms`
- `genes_per_term_min/median/max`, `terms_per_gene_min/median/max`
- `by_term` — term_id → count (top N)
- `not_found` — term_ids requested but missing at this level

This output shape is the TERM2GENE+TERM2NAME model clusterProfiler uses; anyone porting results to R can pass it to `enricher()` directly.

### `pathway_enrichment(organism, experiment_ids, ontology, level, direction='both', min_gene_set_size=5, max_gene_set_size=500, pvalue_cutoff=0.05, background='table_scope', timepoint_filter=None, verbose=False, limit=None)`

End-to-end ORA: pathway × experiment × timepoint × direction → Fisher + BH + signed score.

**Groups tested:** cartesian of (`experiment_ids × timepoints-present × direction`). `direction` ∈ {`up`, `down`, `both`}; `both` runs both separately and lets the caller (or `signed_score`) combine.

**Background (universe):**
- `'table_scope'` (default): per-experiment quantified gene set.
- `'organism'`: full organism gene set.
- `list[str]`: explicit locus_tag list (escape hatch).

**Output (long format, compareCluster-compatible):**
- `cluster` — `"{experiment_id}|{timepoint}|{direction}"`
- `experiment_id`, `timepoint`, `direction` — also as separate columns
- `term_id`, `term_name`
- `gene_ratio` — `"k/n"` string (and `gene_ratio_numeric` = k/n float)
- `bg_ratio` — `"M/N"` string (and `bg_ratio_numeric`)
- `rich_factor` — k/M
- `fold_enrichment` — (k/n) / (M/N)
- `pvalue`, `p_adjust` (BH within cluster), `qvalue` (Storey, optional; null if statsmodels.stats.multitest.multipletests q-value unavailable)
- `count` — k
- `bg_count` — M
- `gene_ids` — "/"-separated locus_tags of k DE genes in pathway (only when `verbose=True`)
- `signed_score` — `sign × -log10(p_adjust)`; sign from the dominant direction when `direction='both'` and both sides are tested

**BH scope:** applied per `cluster` group (matches the B1 analysis; matches clusterProfiler's compareCluster convention as inferred from their source).

**Summary:**
- `n_tests`, `n_significant` (p_adjust < pvalue_cutoff)
- `top_pathways_by_padj` (top N across all clusters)
- `by_experiment`, `by_direction`, `by_timepoint` — significance counts
- `universe_sizes` — dict of `cluster → N` (because `table_scope` varies)

**NaN-timepoint handling:** if an experiment's DE table uses NaN timepoints (Steglich, Tolonen cyanate, Tolonen urea per the B1 fix), they are treated as a single group named `"NA"`. Not silently dropped.

**Single-organism enforcement:** mirrors `differential_expression_by_gene`. Enrichment across organisms is not meaningful (different gene universes).

## New Python API (L2)

Public functions in `multiomics_explorer.api`:

- `ontology_landscape(...)` → dict
- `genes_at_ontology_level(...)` → DataFrame
- `pathway_enrichment(...)` → DataFrame (wide, as above)
- `signed_enrichment_score(df, direction_col='direction', padj_col='p_adjust')` → DataFrame with `signed_score` column. Standalone for recomposition.

All wrap L1 query builders. Fisher via `scipy.stats.fisher_exact`, BH via `statsmodels.stats.multitest.multipletests(method='fdr_bh')`.

## New Cypher builders (L1)

In `multiomics_explorer/kg/queries_lib.py`:

- `ontology_landscape_query(ontology, organism, experiment_ids=None)` — one query, aggregates per level. Uses `UNWIND` over levels, `collect(DISTINCT g)` per level, percentiles via `percentileCont`.
- `genes_at_ontology_level_query(ontology, level, organism, term_ids=None)` — one row per `(gene, term)` at target level after hierarchy expansion.
- `pathway_contingency_counts_query(ontology, level, organism, de_locus_tags, background_locus_tags, min_gene_set_size, max_gene_set_size)` — one row per pathway with `(pathway_id, pathway_name, a, b, c, d, M)` where a/b/c/d are the 2×2 counts used by Fisher.

### Unified hierarchy helper

Single internal function `hierarchy_expansion_cypher(ontology, level)` returning the `MATCH` / `WHERE` fragment for rolling up a term to a target level. Dispatches on ontology source:

- CyanoRak: dot-count on `role_code` (current strategy).
- KEGG pathway: `level` property on `Kegg_term`.
- Others (GO, TIGR, COG, Pfam, EC, Cyanorak subcategories): BFS up `*_is_a_*` relation.

Replaces the per-ontology strategies currently scattered across B1's `enrich_utils/hierarchy.py`.

## Modified existing tools

### `gene_ontology_terms` — internal batching fix

Hit 1.4 GiB transaction memory cap with 1,976 genes × GO MF. Fix: chunk the locus_tags parameter into batches of N (default 500, configurable env var `MULTIOMICS_KG_BATCH_SIZE`), run each as its own transaction, concatenate results. No API change; behavior identical for small inputs.

This is independent of the new tools and can ship anytime in Phase 1.

## MCP tool YAMLs (about content)

Every new tool gets an `inputs/tools/<tool>.yaml` in the existing pattern, providing `examples`, `chaining`, `verbose_fields`, `mistakes`, consumed by `scripts/build_about_content.py`:

- `inputs/tools/ontology_landscape.yaml`
- `inputs/tools/genes_at_ontology_level.yaml`
- `inputs/tools/pathway_enrichment.yaml`

**`mistakes` content (draft highlights):**
- `ontology_landscape`: "Don't pick a level by term-size stats alone — always check `genome_coverage`. An ontology may have appealing median term size at a level that covers only 18% of the genome."
- `genes_at_ontology_level`: "For GO, level slicing is a best-effort approximation — GO is a DAG and ancestor terms absorb descendant annotations. The `min_exp_coverage` signal in `ontology_landscape` is how you detect this."
- `pathway_enrichment`: "Default background is `table_scope` (per-experiment quantified set). Using `'organism'` inflates the denominator and underestimates enrichment. See `docs://analysis/enrichment` for the full methodology note."

## MCP resource + methodology doc — `docs://analysis/enrichment`

Single canonical file: `multiomics_explorer/analysis/enrichment.md`. Served as the MCP resource `docs://analysis/enrichment` (following the V2 resource pattern; matches `docs://analysis/response_matrix`). No separate `docs/methodology/enrichment.md` — one source, one location.

**Outline:**
1. When to use enrichment (DE result → which pathways?)
2. Tool sequence: `ontology_landscape` → `genes_at_ontology_level` (inspection) → `pathway_enrichment`
3. Ontology selection methodology
   - `genome_coverage` is required (not optional)
   - Tree-vs-DAG caveat (CyanoRak/TIGR/COG: tree-native; GO: best-effort)
   - Per-experiment coverage caveat when experiment sizes vary
4. Background set
   - Why `table_scope` (cite B1 decision D2)
   - When to use `organism` instead
5. Interpretation
   - Signed score as a visualization scalar
   - Catch-all categories (B1 caveat C3)
   - Cross-experiment FDR (B1 caveat C4)
6. Deferred methodology (pointers, not implementations)
   - GSEA for rank-based enrichment
   - `simplify()` / GOSemSim for GO-DAG redundancy collapse
   - topGO elim/weight
7. References: yulab book, Xu et al. 2024 protocol, B1 analysis

## KG requirements doc — `docs/kg_requirements/ontology_hierarchy.md`

Not implemented in this repo. Captures asks for the `multiomics_biocypher_kg` repo:

1. **Unified hierarchy-level property.** Each ontology term node should carry a `level: int` property. Current state: inconsistent (KEGG has level; CyanoRak derives from role_code dot-count; GO/TIGR/COG require BFS). A canonical property simplifies our L1 builder and removes risk of traversal bugs.
2. **Pfam clan edges.** `Pfam_in_pfam_clan` returned 0 edges. Low priority; Pfam isn't a strong enrichment candidate.
3. **KEGG pathway linkage.** 300/1,065 MED4 KO genes (28%) have no pathway edge. Flat across levels. Investigation needed: KOs without pathway assignments upstream, or missing edges in the KG build?

**Caveat carried forward from user:** the current `gaps_and_friction` entries may reflect KG build-pipeline doc artifacts, not live KG gaps. This requirements doc should be validated against the live KG before filing with the KG repo.

## Phase breakdown

### Phase 1 — Ontology surface

**Goal:** characterize ontologies and roll genes to any hierarchy level.

1. **Unified hierarchy helper** in `queries_lib`. Tests against all 9 ontologies (CyanoRak, KEGG, GO BP/MF/CC, TIGR, COG, Pfam, EC).
2. **`ontology_landscape`** — L1 → L2 → L3 → YAML. Includes `best_level` heuristic and optional `experiment_ids` (option B: aggregate stats only).
3. **`genes_at_ontology_level`** — L1 → L2 → L3 → YAML. Batch-aware.
4. **`gene_ontology_terms` batching fix.** Independent of 1–3, can ship anytime.
5. **KG requirements doc** — `docs/kg_requirements/ontology_hierarchy.md`. Validated against live KG before being shared.

Step 1 blocks 2 and 3.

### Phase 2 — Enrichment

**Goal:** one MCP tool for ORA end-to-end.

1. **`pathway_contingency_counts_query`** (L1). Returns `(a, b, c, d, M)` per pathway.
2. **`pathway_enrichment` api function** (L2). Fisher + BH + signed score + NaN handling.
3. **`signed_enrichment_score` util** (L2). Standalone; composable.
4. **`pathway_enrichment` MCP tool** (L3). Full YAML + compareCluster-aligned output.
5. **`docs://analysis/enrichment` resource** + `docs/methodology/enrichment.md`. Includes clusterProfiler reference and scoped deferrals.

Step 1 blocks 2, which blocks 4. Step 3 is parallel. Step 5 depends on 4 for concrete examples.

### Cross-cutting

- Regression fixtures regenerated for any tool touching hierarchy traversal.
- `kg_schema` tool docs updated to mention unified-hierarchy-level semantics.
- No research-repo changes (out of scope).
- No skill-file changes in this repo (methodology lives in `docs/methodology/` and the MCP resource, not in skill-rigor updates here).

## Out of scope

- GSEA (requires ranked full gene lists per experiment — new L1 builder `ranked_gene_scores_query`).
- `simplify()` / GOSemSim — requires custom OrgDb for non-model organisms, or KG-native IC computation.
- Enrichment visualizations (emapplot, cnetplot, upsetplot) — callers plot; we return data.
- `gson` format export.
- Multi-ontology combined enrichment.
- KG schema changes (captured as requirements doc only).
- Any research-repo migration or `enrich_utils` deprecation.

## Open questions deferred to plan stage

- Exact `best_level` heuristic thresholds (currently: `genome_coverage ≥ 0.3`, `5 ≤ median ≤ 50`). Validate against the 9 ontologies during Phase 1.
- `qvalue` computation — include only if trivially available from statsmodels; otherwise leave null.
- Whether `pathway_enrichment` should accept an explicit `pathway_definitions` DataFrame as an escape hatch (caller-supplied TERM2GENE). Leaning no — scope creep, and `genes_at_ontology_level` already supplies it.

## References

- B1 analysis: `multiomics_research/analyses/2026-04-09-1713-pathway_enrichment_b1/`
- Xu, S. et al. Using clusterProfiler to characterize multiomics data. *Nat Protoc* **19**, 3292–3320 (2024). doi:10.1038/s41596-024-01020-z
- yulab-smu biomedical-knowledge-mining book: https://yulab-smu.top/biomedical-knowledge-mining-book/
- Yu, G. et al. clusterProfiler: an R package for comparing biological themes among gene clusters. *OMICS* **16**, 284–287 (2012).
