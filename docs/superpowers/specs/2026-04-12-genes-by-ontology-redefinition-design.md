# `genes_by_ontology` Redefinition Design Spec

**Status:** Draft
**Date:** 2026-04-12
**Parent spec:** [2026-04-12-kg-enrichment-surface-design.md](2026-04-12-kg-enrichment-surface-design.md)
**Depends on:** [Child 1 — ontology-landscape-design](2026-04-12-ontology-landscape-design.md) (unified hierarchy helper)
**Scope:** Child 2 of the KG enrichment surface work. **Breaking change** to an existing MCP tool.

## What's in this spec

Redefine the existing `genes_by_ontology` tool:
- Change output shape from distinct-gene rows to `(gene × term)` long format.
- Add `level` as an input; either `level` or `term_ids` (or both) must be supplied.
- Keep the tool name to avoid sprawl — this tool is the one that produces TERM2GENE pathway definitions for enrichment; there's no value in also keeping the gene-centric variant.

## Rationale

The current tool returns distinct genes with term attribution hidden inside a verbose `matched_terms` list. That shape:

- Is awkward for enrichment: pathway definitions need `(gene, term)` pairs directly (the TERM2GENE model clusterProfiler uses).
- Loses information the new shape exposes — which term(s) each gene matched on.
- Forces any roll-up-to-level use case into 69+ separate calls (B1's original workaround).

Adding a second tool (`genes_by_ontology_level`) with similar output shape and adjacent semantics creates two near-duplicate tools. Redefining in place is cleaner:
- One tool, one mental model: "find (gene, term) pairs for this ontology, scoped by input terms and/or a target level."
- Fits the `genes_by_*` family pattern (`genes_by_function`, `genes_by_homolog_group`) — long-format rows with shared envelope conventions.

## Signature

```
genes_by_ontology(
    ontology: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    organism: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,  # MCP default 500
    offset: int = 0,
)
```

**Input validation:** at least one of `level` or `term_ids` must be provided. Neither → `ValueError` at L2.

## Three modes, unified output shape

1. **`term_ids` only** — "gene discovery by pathway/term."
   - Expand DOWN: find genes annotated to any supplied term or its descendants.
   - Row `term_id` = the input term the gene matched against.
   - Matches the old tool's use case, but in long format.

2. **`level` only** — "pathway definitions at level N."
   - Roll UP: for every gene annotated anywhere in the ontology, report its level-N ancestor.
   - Row `term_id` = the level-N ancestor term.
   - Primary consumer of Child 3's `pathway_enrichment` when users want to inspect pathway definitions.

3. **`level` AND `term_ids`** — "scope rollup to specific pathways."
   - `term_ids` must be at the specified level (enforced; violators go to `not_matched`).
   - Row `term_id` = one of the supplied level-N terms.

## Each result row (matches `genes_by_*` family)

- `locus_tag, gene_name, product, organism_name, gene_category` — from Gene node.
- `term_id, term_name` — representative term per the mode above.
- Verbose: `matched_terms` (leaf terms that rolled up; populated when `level` is set and a single level-N term has multiple descendant leaves for a gene), `function_description`.

Output is the TERM2GENE + TERM2NAME model clusterProfiler uses. Callers can pass `results[['term_id','locus_tag']]` as TERM2GENE and `results[['term_id','term_name']].drop_duplicates()` as TERM2NAME to R's `enricher()` directly.

## Response envelope

- `results` — (gene × term) long-format rows (or `[]` when `summary=True`).
- `returned`, `total_matching`, `truncated`, `offset`.
- `n_genes`, `n_terms` — distinct counts across the full (pre-limit) result set.
- `genes_per_term_min/median/max`, `terms_per_gene_min/median/max` — distribution stats.
- `by_organism`, `by_category`, `by_term` — breakdowns (naming matches existing `genes_by_*` tools).
- `not_found` — term_ids requested but absent from the ontology.
- `not_matched` — term_ids present but not at the specified `level` (only when both `level` and `term_ids` are set).
- `score_max`, `score_median` — **not** present (no Lucene search in this tool).

## L1 Cypher builder

`genes_by_ontology_query(ontology, level=None, organism=None, term_ids=None) -> tuple[str, dict]` in `kg/queries_lib.py`.

- Replaces the existing gene-centric query.
- Uses Child 1's unified hierarchy helper to produce the `(term → gene)` expansion for the given mode.
- Returns one row per `(gene, term)` — distinct pairs, not distinct genes.

## Migration / breaking-change impact

Documented here because this is the only tool in the three children that breaks existing callers.

- **Row shape:** was distinct-gene rows → now `(gene × term)` long rows. Consumers counting `len(results)` to mean "number of genes" break; they should use `n_genes` (newly surfaced).
- **`total_matching` semantics:** was "count of distinct genes" → now "count of `(gene × term)` rows matching." `n_genes` recovers the old meaning.
- **Required params:** was `term_ids` required → now at least one of `level` or `term_ids`. Existing `genes_by_ontology(term_ids=[...])` calls continue to work with new long-format output.
- **Verbose fields:** `matched_terms` gains a narrower meaning (populated only when `level` is set and rollup chose a representative from multiple matching leaves). `gene_summary` removed from verbose — not meaningful at `(gene × term)` granularity; callers wanting gene summary should use `gene_overview`.
- **Skill references** (`skills/multiomics-kg-guide/references/tools/genes_by_ontology.md`) regenerated via `scripts/build_about_content.py` and `scripts/sync_skills.sh`.
- **Other tools' chaining/mistakes** referencing `genes_by_ontology`: audit and update to reflect long-format output. Affected: `genes_by_function.yaml`, `search_ontology.yaml`, `gene_ontology_terms.yaml` (chaining sections). No semantic conflict — just row-shape awareness.
- **Regression fixtures** regenerated.
- **Research-repo call sites** (out of scope for this spec, noted for awareness): `enrich_utils/extraction.py` in B1 uses `genes_by_ontology` as a validation oracle. The new shape is strictly richer — validation code migrates by selecting the new `term_id` column.

## YAML about-content

**Rewrite** `inputs/tools/genes_by_ontology.yaml` (not amend):

- **examples:**
  - Mode 1: `genes_by_ontology(ontology="go_bp", term_ids=["go:0006260"])` — gene discovery (unchanged use case, long-format response).
  - Mode 2: `genes_by_ontology(ontology="cyanorak_role", level=1)` — full pathway definitions at level 1 (replaces B1's 69-call workaround).
  - Mode 3: `genes_by_ontology(ontology="cyanorak_role", level=1, term_ids=["J", "K"])` — scoped rollup.
  - summary=True variant for breakdown-only output.
- **chaining:**
  - `ontology_landscape → genes_by_ontology(level=N)` (pick level → inspect pathway defs).
  - `search_ontology → genes_by_ontology(term_ids=[...])` (term discovery → gene membership).
  - `genes_by_ontology → pathway_enrichment` (pathway defs → enrichment).
  - `genes_by_ontology → gene_overview` (explore specific genes after filtering).
- **verbose_fields:** `matched_terms`, `function_description`.
- **mistakes:**
  - "At least one of `level` or `term_ids` must be set — calling without either is an error."
  - "Results are `(gene × term)` pairs, not distinct genes — use `n_genes` in the response for the gene count."
  - "For GO (a DAG), level slicing is a best-effort approximation — ancestor terms absorb descendant annotations. Check `ontology_landscape`'s genome_coverage per level before relying on a GO level."
  - wrong: `"genes_by_ontology(ontology='go_bp')"  # no level or term_ids`
    right: `"genes_by_ontology(ontology='go_bp', level=3)  # or pass term_ids"`

## Tests

- **Unit:** signature validation (ValueError on missing level+term_ids), `not_matched` reports term_ids at wrong level, distinct-count math for `n_genes` and `n_terms`.
- **Integration (`-m kg`):** MED4 × CyanoRak level 1 returns the 110 pathway definitions B1 used. MED4 × GO BP term_ids=[known term] returns expected genes including known descendants.
- **Regression fixtures:** regenerate for all existing `genes_by_ontology` test cases; new fixtures for mode 2 and mode 3.
- **Cross-tool audit:** run `scripts/sync_skills.sh` and spot-check the regenerated skill reference against the YAML.

## Layer-rules compliance

- L1: builder returns `tuple[str, dict]`. No execution, no formatting.
- L2: `genes_by_ontology()` in `api/functions.py` returns full response dict (summary + `results` + `returned` + `truncated` + `not_found` + `not_matched`). Validates inputs, raises `ValueError` for invalid combinations.
- L3: thin MCP wrapper. Pydantic response model. Default `limit=500`. `await ctx.info/warning` for batch-handling messages.
- L4: skill reference auto-generated from Pydantic + YAML.

## Out of scope for this spec

- `ontology_landscape` — Child 1.
- `pathway_enrichment`, Fisher/BH/signed score — Child 3.
- Unified hierarchy helper implementation — Child 1 (this spec consumes it).
- Research-repo migration of `enrich_utils/extraction.py`.

## Open questions deferred to plan stage

- Exact behavior when a gene has annotations in multiple subtrees reaching different level-N ancestors (e.g. a GO-BP gene annotated to two top-level processes). Default: emit one row per matched ancestor. Revisit if the row-multiplication concerns surface in testing.
- Whether `matched_terms` verbose field should be a JSON-encoded list or a pipe-separated string. Match the convention of whichever existing `genes_by_*` tool already settled this.
