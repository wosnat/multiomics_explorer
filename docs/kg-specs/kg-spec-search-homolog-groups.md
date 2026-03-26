I want# KG change spec: search-homolog-groups

## Summary

Enrich OrthologGroup nodes with descriptions (from Cyanorak/eggNOG APIs),
functional annotations (derived from member genes), and annotation edges.
Add fulltext index across all text fields to support Lucene-based search
in `search_homolog_groups`.

## Current state

21,122 OrthologGroup nodes (5,619 cyanorak + 15,503 eggnog).
All have `consensus_product`; ~52% have `consensus_gene_name`.
No fulltext index — only RANGE indexes on `id`, `name`,
`taxonomic_level`, `specificity_rank`.

Functional categories live on member genes via edges
(`Gene_has_cyanorak_role`, `Gene_in_cog_category`), not on the group.
~6K groups have `consensus_product` = "hypothetical protein" variants —
unsearchable without richer text.

## Required changes

### New properties

| Node | Property | Type | Source | Notes |
|---|---|---|---|---|
| OrthologGroup | `description` | string | Cyanorak API (CK_ groups), eggNOG API (COG/NOG groups) | Rich functional narrative. Null if API has no entry. |
| OrthologGroup | `functional_description` | string | Derived: concat CyanorakRole + CogFunctionalCategory names from member genes (majority/consensus) | Fallback when `description` is thin. E.g. "Photosynthesis and respiration > Photosystem II; Inorganic ion transport and metabolism" |

### New edges

| Type | Source -> Target | Properties | Notes |
|---|---|---|---|
| `Og_has_cyanorak_role` | OrthologGroup -> CyanorakRole | — | Consensus from member genes. A role is assigned if majority of members share it. |
| `Og_in_cog_category` | OrthologGroup -> CogFunctionalCategory | — | Consensus from member genes. Same majority rule. |

### New indexes

| Type | Name | Fields | Notes |
|---|---|---|---|
| fulltext | `orthologGroupFullText` | `OrthologGroup(consensus_product, consensus_gene_name, description, functional_description)` | Lucene search across all four text fields |

## Derivation rules

### `description` (from external APIs)

**eggNOG groups:** Loaded from local eggNOG SQLite database
(`$EGGNOG_DATA_DIR/eggnog.db`). OG node ID parsed (e.g.
`eggnog:COG0592@2` → og=`COG0592`, level=`2`) and queried against
the `og` table.

**Cyanorak groups:** null (no external description source).

### `functional_description` (derived from member genes)

Built from member genes' `cyanorak_Role` and `cog_category` fields
(both lists). Majority-vote: a code passes if >50% of member genes
have it. Cyanorak roles use full hierarchical names (e.g.
"Photosynthesis and respiration > Photosystem II"). Filtered out:
COG "S" (Function unknown), Cyanorak "R"/"R.2"/"R.4" (hypothetical).
Concatenated with "; " separator. Null if no annotations survive.

### `Og_has_cyanorak_role` / `Og_in_cog_category` edges

Same majority rule: create edge if >50% of member genes have that
annotation. This avoids noise from single outlier genes in large groups.

## Example Cypher (desired)

```cypher
-- Fulltext search across all text fields
CALL db.index.fulltext.queryNodes('orthologGroupFullText', 'photosynthesis')
YIELD node AS og, score
RETURN og.id AS group_id, og.consensus_gene_name AS consensus_gene_name,
       og.consensus_product AS consensus_product,
       og.description AS description,
       og.functional_description AS functional_description, score
ORDER BY score DESC
LIMIT 10

-- Traverse from group to functional category
MATCH (og:OrthologGroup {id: 'cyanorak:CK_00000570'})-[:Og_has_cyanorak_role]->(cr:CyanorakRole)
RETURN cr.id AS role_id, cr.name AS role_name
```

## Verification queries

```cypher
-- Index exists with all 4 fields
SHOW INDEXES YIELD name, type, labelsOrTypes, properties
WHERE name = 'orthologGroupFullText'
RETURN name, type, labelsOrTypes, properties

-- Search returns results (including via description/functional_description)
CALL db.index.fulltext.queryNodes('orthologGroupFullText', 'photosynthesis')
YIELD node, score
RETURN count(node) AS matches, max(score) AS max_score

-- New properties populated
MATCH (og:OrthologGroup)
RETURN count(og) AS total,
       count(og.description) AS with_description,
       count(og.functional_description) AS with_functional_description

-- New edges created
MATCH (og:OrthologGroup)-[:Og_has_cyanorak_role]->(cr:CyanorakRole)
RETURN count(*) AS cyanorak_role_edges, count(DISTINCT og) AS groups_with_roles

MATCH (og:OrthologGroup)-[:Og_in_cog_category]->(cc:CogFunctionalCategory)
RETURN count(*) AS cog_category_edges, count(DISTINCT og) AS groups_with_cog
```

## Status

- [x] Spec reviewed with user
- [x] Changes implemented in KG repo
- [x] KG rebuilt
- [x] Verification queries pass (2026-03-26): description 12,070/21,122, functional_description 11,669/21,122, Og_has_cyanorak_role 11,427 edges (8,871 groups), Og_in_cog_category 16,310 edges (15,387 groups), fulltext index on 4 fields
