# BRITE Ontology Integration Design

**Date:** 2026-04-16
**Status:** Draft
**Scope:** Add KEGG BRITE functional hierarchies as the 10th ontology in the explorer.

## Context

The KG now contains 2,611 `BriteCategory` nodes across 12 KEGG BRITE functional hierarchy trees (enzymes, transporters, peptidases, etc.). These classify ~1,800 KO terms that lack KEGG pathway membership ("pathway-orphan KOs"). Nodes connect via `Gene -[:Gene_has_kegg_ko]-> KeggTerm -[:Kegg_term_in_brite_category]-> BriteCategory`, a 2-hop path — unlike every other ontology which uses a single `gene_rel` edge.

BriteCategory nodes have properties: `name`, `tree`, `tree_code`, `level` (0–3), `level_kind`, `member_ko_count`, `gene_count`, `organism_count`. Hierarchy edges: `Brite_category_is_a_brite_category` (child→parent). Fulltext index: `briteCategoryFullText` on `name`.

## Decision: Option (ii) — minimal surface, no tree parameter

BRITE becomes one `"brite"` ontology key in `ONTOLOGY_CONFIG`/`ALL_ONTOLOGIES`. No `tree` filter parameter on any tool. Tree is incidental metadata on returned rows, not a query dimension. Tree-scoped queries use `search_ontology` → term IDs → `genes_by_ontology`.

**Alternatives rejected:**
- **(A) One key + `tree` param:** cross-cutting parameter on ~5 tools that only applies to one ontology. API smell.
- **(B) Twelve keys:** 12× fixture/doc churn, `ontology_landscape` default output balloons.
- **(C) Synthetic tree root:** KG emits no tree-root node; inventing one misaligns with data.

**Accepted tradeoff:** `ontology_landscape` stats for BRITE at a given level mix all 12 trees together, which may dilute ranking. If tree-scoped enrichment becomes a common need, a `tree` parameter can be added later (option A).

## Architecture

### ONTOLOGY_CONFIG entry

```python
"brite": {
    "label": "BriteCategory",
    "gene_rel": "Gene_has_kegg_ko",
    "hierarchy_rels": ["Brite_category_is_a_brite_category"],
    "fulltext_index": "briteCategoryFullText",
    "bridge": {
        "node_label": "KeggTerm",
        "edge": "Kegg_term_in_brite_category",
    },
}
```

The `bridge` field is new — `None` (or absent) for all existing ontologies. It encodes the intermediate node and edge in the 2-hop gene-to-leaf path.

### `_hierarchy_walk` — new bridge branch

When `cfg.get("bridge")` is present, the helper emits 2-hop Cypher fragments:

```
bind_up:   MATCH (g:Gene {organism_name: $org})-[:Gene_has_kegg_ko]->(ko:KeggTerm)
                 -[:Kegg_term_in_brite_category]->(leaf:BriteCategory)
walk_up:   MATCH (leaf)-[:Brite_category_is_a_brite_category*0..]->(t:BriteCategory)
walk_down: MATCH (t:BriteCategory)<-[:Brite_category_is_a_brite_category*0..]-(leaf:BriteCategory)
```

This branch slots between the Pfam special case and the flat-ontology case. `bind_up` preserves the `MATCH (g:Gene {organism_name: $org})` prefix so that `build_ontology_expcov`'s prefix-stripping continues to work (the 2-hop tail is in the stripped portion).

### Verified Cypher patterns

All patterns verified against live KG (2026-04-16):

| Pattern | Cypher | Result |
|---|---|---|
| bind_up + walk_up | Gene→KO→BriteCategory→ancestor at level 0 | 864 genes at L0 for MED4 |
| walk_down | Root BriteCategory→descendants→KO→Gene | Returns genes under any root |
| gene_ontology_terms | Gene→KO→BriteCategory (direct) | Multi-tree annotations per gene |
| search_ontology | `briteCategoryFullText` fulltext | Matches across trees |
| ontology_landscape | Per-level aggregation over 2-hop | L0: 25 terms, 864 genes; L1: 54/786; L2: 62/592; L3: 5/33 |
| expcov | Experiment→Gene→KO→BriteCategory | L0: 807/1424 genes covered |

### KO multi-level annotation

A single KO can connect to multiple BriteCategory nodes at different levels within the same tree (e.g., K06861 in transporters at L1 and L2). These are never parent-child pairs — verified via `NOT EXISTS` query. The leaf filter (`_gene_ontology_terms_leaf_filter`) is therefore a no-op for BRITE but must be **skipped** to avoid emitting broken Cypher (the filter would incorrectly use `Gene_has_kegg_ko` targeting `BriteCategory`).

## Per-file changes

### `kg/constants.py`

- Append `"brite"` to `ALL_ONTOLOGIES` (position 10).

### `kg/queries_lib.py`

1. **`ONTOLOGY_CONFIG`** — add `"brite"` entry with `bridge` field (see above).
2. **`_hierarchy_walk`** — add bridge branch: if `cfg.get("bridge")`, emit 2-hop `bind_up`/`walk_up`/`walk_down`. Placed before the flat-ontology check.
3. **`_gene_ontology_terms_leaf_filter`** — add `cfg.get("bridge")` to the skip conditions (alongside `cfg.get("parent_label")`).
4. **`build_gene_ontology_terms` / `build_gene_ontology_terms_summary`** — these inline `gene_rel → label` instead of using `_hierarchy_walk`. Add bridge dispatch: when `cfg.get("bridge")`, emit `(g)-[:Gene_has_kegg_ko]->(:KeggTerm)-[:Kegg_term_in_brite_category]->(t:BriteCategory)` instead of `(g)-[:gene_rel]->(t:label)`.

### `mcp_server/tools.py`

- Add `"brite"` to the `ontology` Literal type hints on tools that accept ontology parameters (`search_ontology`, `genes_by_ontology`, `gene_ontology_terms`, `ontology_landscape`, `pathway_enrichment`).

### `api/functions.py`

- No structural changes. Iterates `ALL_ONTOLOGIES` / dispatches on `ONTOLOGY_CONFIG` — BRITE flows through.

### `config/schema_baseline.yaml`

- Add `BriteCategory` node label with properties.
- Add `Brite_category_is_a_brite_category` and `Kegg_term_in_brite_category` relationship types.

### Tests

- **Unit (`test_query_builders.py`):** `_hierarchy_walk` with `ontology="brite"` — verify bind_up/walk_up/walk_down fragments. Leaf filter skip for bridge ontologies.
- **Regression fixtures:** `ontology_landscape` gains BRITE rows (regenerate after implementation).
- **Integration (`-m kg`):** BRITE round-trip via `genes_by_ontology(ontology="brite", level=1)`, `gene_ontology_terms(ontology="brite")`, `search_ontology(ontology="brite")`.

### Skill docs / YAML inputs

- `inputs/tools/ontology_landscape.yaml` — add BRITE to valid values.
- `inputs/tools/search_ontology.yaml` — add BRITE.
- `inputs/tools/genes_by_ontology.yaml` — add BRITE.
- `inputs/tools/gene_ontology_terms.yaml` — add BRITE.
- `inputs/tools/pathway_enrichment.yaml` — add BRITE.
- `skills/multiomics-kg-guide/references/tools/` — update affected tool reference docs.

## KG prerequisite (non-blocking)

`Gene.annotation_types` does not currently include `"brite"`. This means `gene_overview` won't signal BRITE availability per gene. All ontology tools work via edge traversal and are unaffected. Follow-up task for `multiomics_biocypher_kg` pipeline.

## Scope boundary

This spec does NOT include:
- Tree-scoped parameters on any tool.
- New BRITE-specific tools.
- Changes to `gene_overview` beyond what `annotation_types` provides.
- KG pipeline changes (separate repo).
