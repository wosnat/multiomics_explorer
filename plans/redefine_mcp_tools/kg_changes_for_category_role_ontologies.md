# KG Changes for Category/Role Ontology Support

Spec for `multiomics_biocypher_kg` changes needed to support COG category,
Cyanorak role, and TIGR role in the explorer's ontology MCP tools.

---

## 1. Add `name` property to CyanorakRole and TigrRole nodes

**Problem:** All existing ontology nodes (BiologicalProcess, MolecularFunction,
CellularComponent, EcNumber, KeggTerm) use `name` as their human-readable text
property. CyanorakRole and TigrRole use `description` instead. CogFunctionalCategory
already has `name`.

**Fix:** Rename `description` → `name` on CyanorakRole and TigrRole nodes.

**Current state:**
```
CogFunctionalCategory: {id, code, name, preferred_id}              ✓ has name
CyanorakRole:          {id, code, description, preferred_id}        ✗ no name
TigrRole:              {id, code, description, preferred_id}        ✗ no name
```

**After fix:**
```
CyanorakRole:          {id, code, name, preferred_id}
TigrRole:              {id, code, name, preferred_id}
```

## 2. Create fulltext indexes

The explorer's `search_ontology` tool uses Neo4j fulltext indexes for Lucene-syntax
search. No indexes exist for these three node types.

Add to post-build index creation (alongside existing ontology indexes):

```cypher
CREATE FULLTEXT INDEX cogCategoryFullText IF NOT EXISTS
  FOR (n:CogFunctionalCategory) ON EACH [n.name];

CREATE FULLTEXT INDEX cyanorakRoleFullText IF NOT EXISTS
  FOR (n:CyanorakRole) ON EACH [n.name];

CREATE FULLTEXT INDEX tigrRoleFullText IF NOT EXISTS
  FOR (n:TigrRole) ON EACH [n.name];
```

Index on `name` (not `description`) — requires step 1 to be done first for
CyanorakRole and TigrRole.

## 3. Add TigrRole hierarchy edges

**Problem:** CyanorakRole has `Cyanorak_role_is_a_cyanorak_role` hierarchy edges
(154 edges linking sub-roles like `A.1` to main roles like `A`). TigrRole has the
same main/sub structure encoded in its `description` field but no hierarchy edges.

**Current TigrRole structure** (114 nodes, all flat):
```
tigr.role:100  "Central intermediary metabolism / Amino sugars"
tigr.role:102  "Central intermediary metabolism / Other"
tigr.role:108  "Energy metabolism / Aerobic"
tigr.role:120  "Energy metabolism / TCA cycle"
```

The text before ` / ` is the main category, after is the sub-category.
There are no separate main-category nodes — the main categories only appear
as prefixes in the description.

**Fix:** Create main-category TigrRole nodes and `Tigr_role_is_a_tigr_role` edges:

1. Parse unique main categories from the ` / ` split of existing descriptions
2. Create a TigrRole node for each main category (e.g. `tigr.main:energy_metabolism`)
   with `name` = "Energy metabolism", `code` = derived from existing code pattern
3. Add `Tigr_role_is_a_tigr_role` edge from each sub-role to its main category

**Example result:**
```
(tigr.role:120 "Energy metabolism / TCA cycle")
  -[:Tigr_role_is_a_tigr_role]->
(tigr.main:energy_metabolism "Energy metabolism")
```

**Alternative (simpler):** If creating new main-category nodes is too complex,
skip this step entirely. COG categories work fine without hierarchy — TIGR can too.
The explorer will just treat them as flat. The trade-off is that
`genes_by_ontology(term_ids=["tigr.main:..."])` won't expand to sub-roles.

---

## Verification

After rebuild:

```cypher
-- Step 1: name property exists
MATCH (t:CyanorakRole) WHERE t.name IS NULL RETURN count(t)
-- Expected: 0

MATCH (t:TigrRole) WHERE t.name IS NULL RETURN count(t)
-- Expected: 0

-- Step 2: fulltext indexes work
CALL db.index.fulltext.queryNodes('cogCategoryFullText', 'energy')
YIELD node, score RETURN node.name, score LIMIT 5

CALL db.index.fulltext.queryNodes('cyanorakRoleFullText', 'DNA')
YIELD node, score RETURN node.name, score LIMIT 5

CALL db.index.fulltext.queryNodes('tigrRoleFullText', 'metabolism')
YIELD node, score RETURN node.name, score LIMIT 5

-- Step 3: TIGR hierarchy (if implemented)
MATCH (child:TigrRole)-[:Tigr_role_is_a_tigr_role]->(parent:TigrRole)
RETURN parent.name, count(child) AS sub_roles
ORDER BY sub_roles DESC
```
