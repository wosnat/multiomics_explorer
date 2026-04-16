# Ontology Level & Tree Consistency Design

**Date:** 2026-04-16
**Status:** Draft
**Scope:** Add `level` (input + output) and BRITE `tree`/`tree_code` (output, sparse; input filter) consistently across all ontology tools.

## Problem

After adding `level` to the KG and landing `genes_by_ontology`, `ontology_landscape`, and `pathway_enrichment` with level support, two ontology tools remain inconsistent:

- **`search_ontology`** — returns `id`, `name`, `score` only. No `level`, no `tree`. Users must make a follow-up call to learn where a discovered term sits in the hierarchy.
- **`gene_ontology_terms`** — returns leaf annotations only, with no `level` field. No way to roll up annotations to broader categories. No `tree` for BRITE.

Additionally, BRITE's 12-tree structure is not surfaced anywhere — all tools lump trees together, and `enzymes` (1,776 terms at level 3) dominates results. There is no way to filter by tree or see per-tree breakdowns.

## Design Decisions

1. **`level` as input + output on all ontology tools.** Every tool that returns ontology terms includes `level: int` per row and accepts an optional `level` filter.
2. **BRITE `tree`/`tree_code` sparse on all ontology result rows.** Present when ontology is BRITE, absent (stripped) otherwise. Not verbose-gated — short labels essential for disambiguation.
3. **`tree` as input filter** on all tools where BRITE results can appear. Filters by `t.tree` (human-readable name). Validation error if used with non-BRITE ontology.
4. **`gene_ontology_terms` gets explicit `mode` parameter** — `Literal["leaf", "rollup"]`, default `"leaf"`. Avoids ambiguity about what results represent. `mode="rollup"` requires `level`; `mode="leaf"` works with or without `level`.
5. **Reuse `_hierarchy_walk`** for rollup mode in `gene_ontology_terms` — proven pattern from `genes_by_ontology`.
6. **`list_filter_values` gets `brite_tree` filter type** — discoverable list of valid tree names.
7. **`ontology_landscape` breaks BRITE rows by tree** — keyed by `(ontology_type, tree, level)` for BRITE instead of `(ontology_type, level)`.

## Changes By Tool

### 1. `search_ontology`

**New inputs:**
- `level: Annotated[int | None, Field(description="Filter to terms at this hierarchy level. 0 = broadest.", ge=0)] = None`
- `tree: Annotated[str | None, Field(description="BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'.")] = None`

**New output fields on `SearchOntologyResult`:**
- `level: int` — always present
- `tree: str | None = None` — sparse (BRITE only)
- `tree_code: str | None = None` — sparse (BRITE only)

**Query builder changes (`build_search_ontology` + `build_search_ontology_summary`):**
- Add `t.level AS level, t.tree AS tree, t.tree_code AS tree_code` to RETURN clause
- Add conditional `WHERE t.level = $level` when `level` is provided
- Add conditional `AND t.tree = $tree` when `tree` is provided
- Both single-index and dual-index (Pfam UNION) variants updated. For the Pfam UNION variant, `WHERE t.level = $level` must go inside each UNION branch (before the UNION), not after — since the UNION merges two separate fulltext calls

**Validation:**
- `tree` with non-`"brite"` ontology raises `ValueError`

### 2. `gene_ontology_terms`

**New inputs:**
- `organism: Annotated[str, Field(description="Organism name or substring (e.g. 'MED4'). Single organism enforced.")]` — required, matches the pattern used by `genes_by_ontology`, `differential_expression_by_gene`, etc.
- `mode: Annotated[Literal["leaf", "rollup"], Field(description="'leaf' returns most-specific annotations (default). 'rollup' walks up to ancestors at the given level.")] = "leaf"`
- `level: Annotated[int | None, Field(description="Hierarchy level. In leaf mode: filter to leaves at this level. In rollup mode: required — target ancestor level (0 = broadest).", ge=0)] = None`
- `tree: Annotated[str | None, Field(description="BRITE tree name filter. Only valid when ontology='brite'.")] = None`

**New output fields on `OntologyTermRow`:**
- `level: int` — always present
- `tree: str | None = None` — sparse (BRITE only)
- `tree_code: str | None = None` — sparse (BRITE only)

**Summary changes:**
- `by_term` entries gain `level: int`
- `by_ontology` (`OntologyTypeBreakdown`) gains sparse `tree: str | None = None`, `tree_code: str | None = None`. BRITE entries broken down per tree.

**Behavioral modes:**

| `mode` | `level` | Behavior |
|---|---|---|
| `"leaf"` (default) | `None` | Current behavior: most-specific annotations, `level` in output |
| `"leaf"` | `N` | Leaf annotations filtered to those at exactly level N |
| `"rollup"` | `N` | Walk up from leaves to ancestors at level N via `_hierarchy_walk`. `DISTINCT` for convergent paths. |
| `"rollup"` | `None` | Validation error: "level required when mode='rollup'" |

**Query builder changes:**

`build_gene_ontology_terms` (detail):
- Leaf mode, no level: current MATCH + leaf_filter + add `t.level AS level, t.tree AS tree, t.tree_code AS tree_code` to RETURN
- Leaf mode, level=N: current MATCH + leaf_filter + `AND t.level = $level` + new columns in RETURN
- Rollup mode, level=N: replace MATCH + leaf_filter with `_hierarchy_walk` bind_up + walk_up + `WHERE t.level = $level`. Use `DISTINCT` on result to deduplicate convergent paths. New columns in RETURN.
- Tree filter: add `AND t.tree = $tree` in all modes when provided (BRITE only)

`build_gene_ontology_terms_summary`:
- Same mode split for the MATCH stage
- Rollup mode: collected terms include `{id: t.id, name: t.name, level: t.level, tree: t.tree, tree_code: t.tree_code}` from walked-up ancestor `t`. `DISTINCT` in collect to avoid counting same gene x ancestor pair multiple times.
- Leaf mode: add level/tree/tree_code to collected term dicts
- `by_ontology` aggregation for BRITE: group by `tree` to produce per-tree entries

**Validation:**
- `mode="rollup"` without `level` raises `ValueError`
- `tree` with non-`"brite"` ontology raises `ValueError`

**Organism enforcement:** `gene_ontology_terms` now requires a single organism (breaking change from the current multi-organism behavior). This aligns with `genes_by_ontology`, `differential_expression_by_gene`, `pathway_enrichment`, and `gene_response_profile`. The organism is resolved via the standard fuzzy-match pattern (substring match, must resolve to exactly one organism).

With organism scoping, all query builders use `MATCH (g:Gene {organism_name: $org})` as the entry point, and `locus_tags` become a WHERE filter:

Leaf mode:
```cypher
MATCH (g:Gene {organism_name: $org})-[:gene_rel]->(t:Label)
WHERE g.locus_tag IN $locus_tags
  AND NOT EXISTS {  -- leaf_filter: only for hierarchical same-label ontologies
    MATCH (g)-[:gene_rel]->(child:Label)-[:hierarchy]->(t)
  }
RETURN g.locus_tag AS locus_tag, t.id AS term_id, t.name AS term_name, t.level AS level
```
Note: the leaf filter `NOT EXISTS` must be in the same `WHERE` clause as the locus_tag filter (using `AND`), not a separate `WHERE`. Flat ontologies, Pfam (parent_label), and BRITE (bridge) skip the leaf filter entirely.

Rollup mode:
```cypher
MATCH (g:Gene {organism_name: $org})-[:gene_rel]->(leaf:Label)
WHERE g.locus_tag IN $locus_tags
MATCH (leaf)-[:hierarchy*0..]->(t:Label)
WHERE t.level = $level
RETURN DISTINCT g.locus_tag AS locus_tag, t.id AS term_id, t.name AS term_name, t.level AS level
```

Rollup mode with bridge (BRITE):
```cypher
MATCH (g:Gene {organism_name: $org})-[:Gene_has_kegg_ko]->(ko:KeggTerm)-[:Kegg_term_in_brite_category]->(leaf:BriteCategory)
WHERE g.locus_tag IN $locus_tags
MATCH (leaf)-[:Brite_category_is_a_brite_category*0..]->(t:BriteCategory)
WHERE t.level = $level
RETURN DISTINCT g.locus_tag AS locus_tag, t.id AS term_id, t.name AS term_name, t.level AS level, t.tree AS tree, t.tree_code AS tree_code
```

This aligns the bind pattern with `_hierarchy_walk`'s organism-scoped `bind_up`, though the builders construct the locus_tag WHERE clause themselves.

### 3. `genes_by_ontology`

**New input:**
- `tree: Annotated[str | None, Field(description="BRITE tree name filter. Only valid when ontology='brite'.")] = None`

**New output fields on `GenesByOntologyResult`:**
- `tree: str | None = None` — sparse (BRITE only)
- `tree_code: str | None = None` — sparse (BRITE only)

**Query builder changes:**
- Add `t.tree AS tree, t.tree_code AS tree_code` to RETURN in `build_genes_by_ontology_detail`, `build_genes_by_ontology_per_term`, `build_genes_by_ontology_per_gene`
- Add `AND t.tree = $tree` to the walk stage WHERE clause when `tree` is provided
- `per_gene` builder: `tree` doesn't apply (returns per-gene aggregates, not per-term)

**Validation:**
- `tree` with non-`"brite"` ontology raises `ValueError`

### 4. `ontology_landscape`

**New input:**
- `tree: Annotated[str | None, Field(description="BRITE tree name filter. Only valid when ontology='brite' or ontology=None.")] = None`

**New output fields on `OntologyLandscapeRow`:**
- `tree: str | None = None` — sparse (BRITE only)
- `tree_code: str | None = None` — sparse (BRITE only)

**Query builder changes (`build_ontology_landscape`):**
- For BRITE: add `t.tree AS tree, t.tree_code AS tree_code` to the grouping and RETURN
- Landscape rows for BRITE keyed by `(ontology_type, tree, level)` — 35 rows for MIT1002 instead of 4 lumped rows
- When `tree` filter provided: add `AND t.tree = $tree` to limit to one tree
- For non-BRITE ontologies: `tree`/`tree_code` not projected (null)

**Note:** The landscape builder currently groups by `(ontology, level)`. For BRITE, the grouping must expand to `(ontology, tree, tree_code, level)`. This requires conditional grouping — either a BRITE-specific branch in the builder or conditional columns. Since `t.tree` is `null` for non-BRITE, grouping by `t.tree` universally would create a single null-keyed group for non-BRITE — functionally identical to the current behavior. So the simplest approach is to always group by `t.tree, t.tree_code` and let non-BRITE produce null groups, then strip nulls in the API layer.

**Summary (`by_ontology` in the API response):**
- BRITE entries in `by_ontology` breakdown include sparse `tree`/`tree_code`
- `best_level` recommendation computed per tree for BRITE

### 5. `pathway_enrichment`

**New input:**
- `tree: Annotated[str | None, Field(description="BRITE tree name filter. Only valid when ontology='brite'.")] = None`

**New output fields on `PathwayEnrichmentResult`:**
- `tree: str | None = None` — sparse (BRITE only)
- `tree_code: str | None = None` — sparse (BRITE only)

**Implementation:**
- Pass `tree` through to internal `genes_by_ontology` call (for TERM2GENE construction)
- Pass `tree` through to internal `ontology_landscape` call (for background validation)
- `tree`/`tree_code` flow through from the `genes_by_ontology` results into the enrichment rows

**Validation:**
- `tree` with non-`"brite"` ontology raises `ValueError`

### 6. `list_filter_values`

**New filter type:** `"brite_tree"`

**New query builder:** `build_list_brite_trees`
```cypher
MATCH (b:BriteCategory)
RETURN b.tree AS tree, b.tree_code AS tree_code, count(*) AS term_count
ORDER BY b.tree
```
Counts all BriteCategory terms per tree (across all levels). This gives the total size of each tree.

**API layer:** New branch in `list_filter_values`:
```python
elif filter_type == "brite_tree":
    cypher, params = build_list_brite_trees()
```
Returns `{value: "enzymes", tree_code: "ko01000", count: N}` per tree.

**MCP tool:** Update `filter_type` Literal to include `"brite_tree"`.

### 7. Sparse field stripping

All API functions that return ontology result rows strip `None`-valued sparse fields before returning:
- `tree` → strip when `None`
- `tree_code` → strip when `None`

This matches the existing pattern for `level_is_best_effort` in `genes_by_ontology`.

## Validation Rules (all tools)

| Rule | Error message |
|---|---|
| `tree` provided with non-BRITE ontology | `"tree filter is only valid for ontology='brite'"` |
| `gene_ontology_terms`: `mode="rollup"` without `level` | `"level is required when mode='rollup'"` |
| `gene_ontology_terms`: `organism` resolves to 0 or 2+ organisms | Standard organism resolution error |

## Breaking Changes

- **`gene_ontology_terms` now requires `organism`** — previously accepted locus_tags from any organism. Callers must now pass an organism name/substring. This is a breaking change to the API function signature and MCP tool.

## Documentation & Test Updates

### enrichment.md

Update both copies (`multiomics_explorer/analysis/enrichment.md` and `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md`):
- Add BRITE as a supported ontology for enrichment
- Document `tree` parameter for scoping enrichment to a specific BRITE tree
- Add worked example: BRITE tree-scoped enrichment (e.g. "enrichment among transporters")
- Update ontology/level selection narrative to cover BRITE tree selection
- Note that all-BRITE enrichment without tree scoping is dominated by enzymes

### Example script (`examples/pathway_enrichment.py`)

Add a `brite` scenario:
- Use `list_filter_values("brite_tree")` to discover trees
- Use `ontology_landscape(ontology="brite", organism=..., tree="transporters")` to pick level
- Run `pathway_enrichment(ontology="brite", tree="transporters", level=1, ...)` on a DE experiment
- Print top enriched transporter categories

### Tool YAML inputs

Update all 6 YAML files in `multiomics_explorer/inputs/tools/`:
- `search_ontology.yaml` — add `level` and `tree` params, update examples
- `gene_ontology_terms.yaml` — add `mode`, `level`, `tree` params, add rollup example, update mistakes
- `genes_by_ontology.yaml` — add `tree` param, add BRITE example
- `ontology_landscape.yaml` — add `tree` param, note per-tree breakdown for BRITE
- `pathway_enrichment.yaml` — add `tree` param, add BRITE enrichment example
- `list_filter_values.yaml` — add `brite_tree` filter type

### Skill reference docs

Regenerate all `.md` files in `multiomics_explorer/skills/multiomics-kg-guide/references/tools/` via `build_about_content.py` after YAML updates.

### Tests

**Unit tests (`tests/unit/test_query_builders.py`):**
- `search_ontology`: test `level` and `tree` WHERE clauses appear in Cypher; test `tree`/`tree_code` in RETURN
- `gene_ontology_terms`: test all 4 mode/level combos (leaf/none, leaf/N, rollup/N, rollup/none→error); test tree filter; test DISTINCT in rollup; test bridge (BRITE) in rollup mode
- `genes_by_ontology`: test `tree` filter in WHERE clause; test `tree`/`tree_code` in RETURN
- `ontology_landscape`: test BRITE rows include `tree`/`tree_code` in grouping; test `tree` filter
- `pathway_enrichment`: test `tree` passthrough
- `list_filter_values`: test `build_list_brite_trees` returns expected columns

**Unit tests (`tests/unit/test_tool_correctness.py`):**
- `search_ontology`: test sparse field stripping (non-BRITE → no tree/tree_code in row); test level in result
- `gene_ontology_terms`: test mode param validation; test level in result; test sparse tree fields
- `genes_by_ontology`: test tree field in BRITE results; test tree validation error for non-BRITE
- `list_filter_values`: test `brite_tree` filter type

**Unit tests (`tests/unit/test_enrichment.py`):**
- No changes expected — enrichment logic is ontology-agnostic. `tree` flows through inputs, not the Fisher/BH math.

**Integration tests (`tests/integration/test_cyver_queries.py`):**
- Add BRITE-specific parametrizations with `tree` filter for: `search_ontology`, `genes_by_ontology`, `gene_ontology_terms` (both modes), `ontology_landscape`, `pathway_enrichment`

**Integration tests (`tests/integration/test_param_edge_cases.py`):**
- Add `tree` with non-BRITE ontology → error cases for all relevant tools
- Add `mode="rollup"` without `level` → error case for `gene_ontology_terms`

**Integration tests (`tests/integration/test_examples.py`):**
- Add `brite` scenario to the `pathway_enrichment.py` smoke test

**Regression tests (`tests/regression/`):**
- Add BRITE-specific golden files for: `search_ontology_brite`, `gene_ontology_terms_brite_leaf`, `gene_ontology_terms_brite_rollup`, `genes_by_ontology_brite_tree`, `ontology_landscape` (regenerate existing — now includes per-tree BRITE rows), `pathway_enrichment_brite_tree`
- Regenerate `list_filter_values` golden files (now includes `brite_tree` filter type)
- Regenerate existing `ontology_landscape_med4_all.yml` (BRITE rows now broken out per tree)

## Verified Cypher Patterns

All patterns tested against live KG (2026-04-16):

**search_ontology with level + tree filter:**
```cypher
-- Tested: MATCH (t:BriteCategory) WHERE t.name CONTAINS 'transporter'
-- Returns: id, name, level, tree, tree_code
-- Level/tree filter: WHERE t.level = 1 AND t.tree = 'transporters' ✓
-- Non-BRITE: tree/tree_code return null ✓
```

**gene_ontology_terms leaf mode with level:**
```cypher
-- GO leaf annotations with level in output ✓
-- E.g. MIT1002_01547: 5 GO leaf terms at levels 3-6
```

**gene_ontology_terms rollup mode (organism-scoped):**
```cypher
MATCH (g:Gene {organism_name: $org})-[:Gene_involved_in_biological_process]->(leaf:BiologicalProcess)
WHERE g.locus_tag IN $locus_tags
MATCH (leaf)-[:Biological_process_is_a_biological_process|Biological_process_part_of_biological_process*0..]->(t:BiologicalProcess)
WHERE t.level = 2
RETURN DISTINCT g.locus_tag AS locus_tag, t.id AS term_id, t.name AS term_name, t.level AS level
-- MIT1002_01547: 5 leaf terms → 4 ancestors at level 2 ✓
```

**gene_ontology_terms rollup mode (BRITE bridge, organism-scoped):**
```cypher
MATCH (g:Gene {organism_name: $org})-[:Gene_has_kegg_ko]->(ko:KeggTerm)-[:Kegg_term_in_brite_category]->(leaf:BriteCategory)
WHERE g.locus_tag IN $locus_tags
MATCH (leaf)-[:Brite_category_is_a_brite_category*0..]->(t:BriteCategory)
WHERE t.level = 0
RETURN DISTINCT g.locus_tag AS locus_tag, t.id AS term_id, t.name AS term_name, t.level AS level, t.tree AS tree, t.tree_code AS tree_code
-- MIT1002_01547: 7 leaf terms → 1 ancestor at level 0 ✓
```

**gene_ontology_terms rollup summary (organism-scoped):**
```cypher
MATCH (g:Gene {organism_name: $org})-[:Gene_has_kegg_ko]->(ko:KeggTerm)-[:Kegg_term_in_brite_category]->(leaf:BriteCategory)
WHERE g.locus_tag IN $locus_tags
MATCH (leaf)-[:Brite_category_is_a_brite_category*0..]->(t:BriteCategory)
WHERE t.level = 1
WITH g.locus_tag AS lt, collect(DISTINCT {id: t.id, name: t.name, level: t.level, tree: t.tree, tree_code: t.tree_code}) AS terms
-- by_term includes level, tree, tree_code; gene_term_counts correct ✓
```

**ontology_landscape per-tree BRITE grouping:**
```cypher
-- Tested: GROUP BY tree, tree_code, level for BRITE
-- 35 rows for MIT1002: per-tree × per-level with n_terms_with_genes, n_genes_at_level
-- enzymes tree dominates: 1,127 genes, 909 terms at level 3
-- transporters tree: 307 genes at level 0, 99 at level 2 ✓
```

**list_filter_values brite_tree:**
```cypher
-- 12 trees: chaperones, defense, dna_replication, enzymes, peptidases,
--   ribosome, secretion, transcription_factors, translation_factors,
--   transporters, trna_biogenesis, two_component ✓
```

## Files To Modify

| File | Changes |
|---|---|
| `multiomics_explorer/kg/queries_lib.py` | All query builders: add level/tree columns, tree filter, rollup mode for gene_ontology_terms, new `build_list_brite_trees` |
| `multiomics_explorer/api/functions.py` | All API functions: pass through new params, sparse field stripping, mode validation, `brite_tree` filter type |
| `multiomics_explorer/mcp_server/tools.py` | All tool functions + result models: new params, new fields, updated Literals |
| `multiomics_explorer/analysis/enrichment.md` | BRITE enrichment guidance, tree-scoped example |
| `multiomics_explorer/skills/.../references/analysis/enrichment.md` | Mirror of above |
| `multiomics_explorer/inputs/tools/*.yaml` | All 6 ontology tool YAMLs |
| `examples/pathway_enrichment.py` | New `brite` scenario |
| `tests/unit/test_query_builders.py` | New tests for all builder changes |
| `tests/unit/test_tool_correctness.py` | New tests for tool-layer changes |
| `tests/integration/test_cyver_queries.py` | BRITE parametrizations |
| `tests/integration/test_param_edge_cases.py` | Validation error cases |
| `tests/integration/test_examples.py` | `brite` scenario smoke test |
| `tests/regression/test_regression/` | New + regenerated golden files |

## Out of Scope

- No changes to `genes_by_function`, `gene_details`, `gene_overview`, or non-ontology tools
- No changes to `_hierarchy_walk` itself (reused as-is; `gene_ontology_terms` rollup reuses the walk fragment but constructs its own organism+locus_tag bind)
- No changes to enrichment math (`analysis/enrichment.py`) — `tree` is a filter, not a statistical parameter
