# Expose Ontology Info on Ortholog Groups

**Date:** 2026-04-01
**Backlog item:** #3 — Expose ontology info on ortholog groups

## Context

The KG has two consensus ontology edges on OrthologGroup nodes:

- `Og_has_cyanorak_role` -> CyanorakRole (assigned when >50% of member genes share the annotation)
- `Og_in_cog_category` -> CogFunctionalCategory (same majority rule)

These edges exist in the graph and are verified, but no MCP tool exposes them. The only current access is via the `functional_description` text property (a flat concatenation used in fulltext search), which is not structured or filterable.

## Scope

Enhance two existing tools. No new tools.

### 1. `search_homolog_groups`

**New filter parameters:**

- `cyanorak_roles: list[str] | None` — CyanorakRole term IDs (e.g., `["1.2.3", "1.2.4"]`)
- `cog_categories: list[str] | None` — CogFunctionalCategory term IDs (e.g., `["J", "K"]`)

Filter semantics: OR within each list (match groups with **any** of the provided IDs). AND across the two parameters if both are provided.

**New verbose output columns (detail builder):**

- `cyanorak_roles` — list of `{id, name}` from `Og_has_cyanorak_role` edges
- `cog_categories` — list of `{id, name}` from `Og_in_cog_category` edges

Groups without annotations return empty lists.

**Summary builder additions:**

- `by_cyanorak_role` — frequency breakdown of CyanorakRole annotations across matching groups
- `by_cog_category` — frequency breakdown of CogFunctionalCategory annotations across matching groups

### 2. `gene_homologs`

**New verbose output columns (detail builder):**

- `cyanorak_roles` — list of `{id, name}` per ortholog group
- `cog_categories` — list of `{id, name}` per ortholog group

**Summary builder additions:**

- `by_cyanorak_role` — frequency breakdown across groups in the result set
- `by_cog_category` — frequency breakdown across groups in the result set

## Layer Changes

### queries_lib.py

**`_gene_homologs_og_where`** — Add `cyanorak_roles` and `cog_categories` parameters. When provided, add relationship-based filter conditions:

```cypher
-- cyanorak_roles filter (added to WHERE or as preceding MATCH)
EXISTS { (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole) WHERE cr.id IN $cyanorak_roles }

-- cog_categories filter
EXISTS { (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory) WHERE cc.id IN $cog_categories }
```

**`build_search_homolog_groups`** — In verbose mode, add OPTIONAL MATCH + collect for ontology columns:

```cypher
OPTIONAL MATCH (og)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)
OPTIONAL MATCH (og)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)
WITH og, score,
     [x IN collect(DISTINCT {id: cr.id, name: cr.name}) WHERE x.id IS NOT NULL] AS cyanorak_roles,
     [x IN collect(DISTINCT {id: cc.id, name: cc.name}) WHERE x.id IS NOT NULL] AS cog_categories
```

**`build_search_homolog_groups_summary`** — Add frequency collections for `by_cyanorak_role` and `by_cog_category`. Requires OPTIONAL MATCH before the aggregation.

**`build_gene_homologs`** — Same OPTIONAL MATCH + collect pattern in verbose mode.

**`build_gene_homologs_summary`** — Add frequency breakdowns for both ontology types.

### functions.py

- `search_homolog_groups()` — Accept and pass through `cyanorak_roles` and `cog_categories` parameters.
- `gene_homologs()` — No new parameters (ontology columns appear automatically in verbose mode).

### tools.py

- `search_homolog_groups` MCP tool — Add `cyanorak_roles` and `cog_categories` optional parameters with descriptions. Update docstring.
- `gene_homologs` MCP tool — Update docstring to mention new verbose output columns.

### Tests

- Unit tests for new Cypher patterns (filter conditions, verbose columns, summary breakdowns)
- Unit tests for parameter passthrough in functions.py and tools.py
- Integration tests (if KG available) for filter accuracy

## Design Decisions

1. **Lists, not scalars** — A group can have multiple roles/categories, and users may want to filter by several at once.
2. **OR within list, AND across params** — `cyanorak_roles=["A","B"]` matches groups with role A or B. Providing both `cyanorak_roles` and `cog_categories` requires both to match.
3. **Verbose-only output** — Ontology annotations add OPTIONAL MATCHes; keeping them verbose-only avoids performance cost on compact queries.
4. **No changes to `genes_by_homolog_group`** — Out of scope per user decision.
5. **Filter by term ID, not text** — Consistent with other ontology filters in the codebase. Users can discover IDs via `search_ontology`.
6. **Enhance `_gene_homologs_og_where` shared helper** — Propagates filters to both summary and detail builders consistently.
