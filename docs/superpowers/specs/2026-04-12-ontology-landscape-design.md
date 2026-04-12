# `ontology_landscape` Design Spec (+ hierarchy helper + batching fix)

**Status:** Draft
**Date:** 2026-04-12
**Parent spec:** [2026-04-12-kg-enrichment-surface-design.md](2026-04-12-kg-enrichment-surface-design.md)
**Scope:** Child 1 of the KG enrichment surface work. No breaking changes. No external dependencies.

## What's in this spec

Three coherent pieces of Phase 1:

1. **`ontology_landscape` MCP tool** — new. Characterizes ontologies for enrichment.
2. **Unified hierarchy helper** — new L1 utility. First consumer is `ontology_landscape`; `genes_by_ontology` (Child 2) and `pathway_enrichment` (Child 3) will also use it.
3. **`gene_ontology_terms` batching fix** — internal change, no API impact. Fixes the 1.4 GiB Neo4j memory cap hit when pulling ~2k genes × GO MF.

These are bundled because (1) and (2) are tightly coupled (the helper exists to serve the tool), and (3) is independent but small enough to ship in the same sub-project without splitting review.

## Architectural principle (shared across the parent spec's children)

Counts and set-intersections happen in Cypher. Statistics and math happen in Python. `ontology_landscape` is a pure aggregation tool — all term-size distributions, percentiles, and per-level counts are computed by Neo4j, never rehydrated into pandas for rollup.

## `ontology_landscape`

### Signature

```
ontology_landscape(
    organism: str,
    ontology: str | None = None,
    experiment_ids: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,  # MCP default 10
    offset: int = 0,
)
```

**Default behavior (ontology=None):** surveys all ontology types in the KG for the organism and returns a combined ranking. Matches the "which ontology/level should I use?" starting-point question in the B1 analysis. Pass a specific `ontology` value (`'cyanorak_role'`, `'go_bp'`, `'kegg'`, …) to drill in.

**Params:**
- `organism` — required.
- `ontology` — optional. `None` surveys all; a specific value restricts.
- `experiment_ids` — optional batch list. Triggers per-experiment coverage columns.
- `summary` — if True, omit `results` rows and return summary fields only.
- `verbose` — if True, include `example_terms` per level.
- `limit` — default `10` at MCP layer. With ~9 ontologies × ~3–7 levels, 10 rows shows the top combinations without overwhelming. Small enough to match the "default limit stays small" convention.
- `offset` — default `0`.

### Each result row (per ontology × level)

- `ontology_type` — always present; matches `gene_ontology_terms`'s ontology field.
- `level` — integer hierarchy level. **`0` = root (broadest terms), higher integers = more specific.** Terms at level N have N ancestors. Leaves sit at varying depths depending on the ontology.
- `relevance_rank` — 1-indexed rank across **all rows in the response scope** (global when `ontology=None`, within-ontology when a specific `ontology` is passed). Stable regardless of limit/offset.
- `n_genes_at_level` — distinct genes reachable at this level.
- `genome_coverage` — `n_genes_at_level / total_organism_genes`.
- `n_terms_with_genes` — terms with ≥1 gene at this level.
- `min_genes_per_term` / `q1_genes_per_term` / `median_genes_per_term` / `q3_genes_per_term` / `max_genes_per_term` — term-size distribution.
- `example_terms` — top N terms by gene count with names (verbose only).
- If `experiment_ids` is set:
  - `min_exp_coverage`, `median_exp_coverage`, `max_exp_coverage` — aggregate of per-experiment coverage across the matched experiments.

### Rank criterion (internal implementation)

- `size_factor = min(1, median_genes_per_term / 5) × min(1, 50 / median_genes_per_term)` — penalty when median term size falls outside the sweet spot `[5, 50]`.
- When `experiment_ids` is None: `relevance_score = genome_coverage × size_factor`.
- When `experiment_ids` is set: `relevance_score = median_exp_coverage × size_factor`. Genome coverage remains visible as a column so a researcher can re-sort on it.
- Rows sorted by `relevance_score` descending before pagination. Ties broken by `genome_coverage` descending, then `level` ascending.
- `relevance_rank` is computed **before** `limit`/`offset` applies, so it stays meaningful when the caller paginates.
- `relevance_score` is not exposed in the output. The formula lives in the enrichment resource (Child 3) so researchers can reason about it.
- Sweet-spot bounds `[5, 50]` are internal constants, not tool parameters.

### Response envelope

Per layer-rules, L2 returns the full dict; L3 wraps with Pydantic.

- `results` — per-(ontology × level) rows (or `[]` when `summary=True`).
- `returned` — `len(results)`.
- `total_rows` — total `(ontology, level)` pairs before `limit`/`offset`.
- `truncated` — `returned < total_rows`.
- `offset` — echo of input.
- `not_found` — experiment_ids requested but absent from the KG (only when `experiment_ids` is set).
- `not_matched` — experiment_ids found but not matching `organism` (only when `experiment_ids` is set).
- `n_ontologies` — count of ontology types in the response.
- `by_ontology` — per-ontology summary: `{ontology_type: {best_level, best_genome_coverage, best_relevance_rank, n_levels}}`. Always populated, independent of pagination.
- `organism_gene_count`.

No `best_level` scalar field — `relevance_rank=1` is the equivalent.

### L1 Cypher builder

`ontology_landscape_query(ontology, organism, experiment_ids=None) -> tuple[str, dict]` in `kg/queries_lib.py`.

- One query per call (not one per level). Uses `UNWIND` over levels from the hierarchy helper output, `collect(DISTINCT g)` per level, percentiles via `percentileCont`.
- When `ontology=None` at L2, L2 iterates over known ontology types and unions results, OR (preferred) L1 supports a multi-ontology query variant. Decide during planning; lean toward L2 orchestration because it keeps L1 queries focused.
- `experiment_ids` branch joins through `Experiment`—`Changes_expression_of`—`Gene` to intersect gene sets per experiment before computing per-experiment coverage.

### YAML about-content

`inputs/tools/ontology_landscape.yaml` with:
- **examples:** (a) default no-ontology survey, (b) specific ontology with experiment_ids, (c) summary=True for breakdowns only.
- **chaining:** `ontology_landscape → genes_by_ontology(level=N)` (pathway defs) → `pathway_enrichment`.
- **verbose_fields:** `example_terms`.
- **mistakes:**
  - "Don't pick a level by term-size stats alone — always check `genome_coverage`. An ontology may have appealing median term size at a level that covers only 18% of the genome."
  - "When planning enrichment for specific experiments, pass `experiment_ids` — ontology coverage of those experiments' quantified genes matters more than genome-wide coverage."

### Tests

- Unit: ranking formula correctness across synthetic profiles (high coverage / bad median size / small genome / etc.).
- Integration (`-m kg`): runs against live KG; asserts CyanoRak level 1 is rank 1 for MED4 (matches B1 decision D1).
- Regression fixtures: capture full response for MED4 × all ontologies, MED4 × cyanorak_role × 10 experiments. Freeze in `tests/regression/`.

## Unified hierarchy helper

**Location:** internal to `kg/queries_lib.py`; not exported as a query builder.

**Function:** `hierarchy_expansion_cypher(ontology: str, level: int) -> tuple[str, dict]` (or similar fragment-returning helper — exact shape decided at plan time).

**Role:** return the `MATCH` / `WHERE` Cypher fragment for rolling up a term to a target level. Dispatches on ontology source:

- **CyanoRak:** dot-count on `role_code` (current B1 strategy).
- **KEGG pathway:** `level` property on `Kegg_term`.
- **Others** (GO BP/MF/CC, TIGR, COG, Pfam, EC): BFS up the `*_is_a_*` relation with a depth bound.

Replaces the per-ontology strategies currently scattered across B1's `enrich_utils/hierarchy.py`.

**Shared downstream:** Child 2 (`genes_by_ontology_query`) and Child 3 (`pathway_contingency_counts_query`) both use it.

**Tests:**
- Per-ontology unit tests: produce expected level-N terms for a known small subtree.
- Cross-ontology consistency: for each of the 9 ontologies, assert level 0 returns roots only and the deepest level returns leaves only.

## `gene_ontology_terms` batching fix

**Problem:** At ~2k genes × GO MF, the Neo4j transaction hits the 1.4 GiB memory cap and errors out. B1 worked around it with client-side chunking in `enrich_utils/extraction.py`.

**Fix:** chunk `locus_tags` internally into batches of N (default 500, configurable via env var `MULTIOMICS_KG_BATCH_SIZE`); run each batch as its own transaction; concatenate results at L2 before computing summary fields.

**No API change.** Small inputs behave identically (single-batch execution).

**Layer impact:**
- L1: no change (query builder already takes a `locus_tags` list).
- L2: `gene_ontology_terms()` iterates chunks, merges results and summary counters.
- L3: unchanged.

**Tests:**
- Unit: assert chunking kicks in at configured threshold; mock connection to verify N transactions are submitted for N×500+1 genes.
- Integration: regenerate existing regression fixture to confirm output byte-identical before/after chunking.

**Independent of 1+2.** Can ship anytime in Phase 1.

## Phase 1 step dependencies

```
[hierarchy helper] → [ontology_landscape]
                  → (Child 2: genes_by_ontology)
                  → (Child 3: pathway_enrichment)

[gene_ontology_terms batching fix]  (independent)
```

## Out of scope for this spec

- Anything about `genes_by_ontology` — Child 2.
- Fisher/BH/signed score — Child 3.
- The enrichment methodology resource — Child 3.
- KG schema changes — parent spec's KG requirements doc.

## Open questions deferred to plan stage

- Sweet-spot bounds `[5, 50]` in `size_factor`. Validate against the 9 ontologies during implementation — if cyanobacterial genome context pushes the useful range wider (e.g. down to 3), adjust. Decision made once; not a param.
- Multi-ontology L1 query vs. L2 orchestration loop. Measure; decide on implementation simplicity.
- Whether `example_terms` belongs only in verbose or always in `by_ontology` summary. Likely both, but content differs (summary shows the best level's examples; per-row shows that level's examples).
