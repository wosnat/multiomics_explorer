# Plan: Add cog_category, cyanorak_role, tigr_role to ontology query system

## Context

The KG has three Gene → functional-category edge types not yet surfaced through the
ontology MCP tools (`search_ontology`, `genes_by_ontology`, `gene_ontology_terms`):

| Key | Label | Edge | Nodes | Hierarchy | Text prop |
|---|---|---|---|---|---|
| `cog_category` | `CogFunctionalCategory` | `Gene_in_cog_category` | 26 | none (flat) | `name` |
| `cyanorak_role` | `CyanorakRole` | `Gene_has_cyanorak_role` | 173 | `Cyanorak_role_is_a_cyanorak_role` (154 edges, 2-level) | `description` (no `name`) |
| `tigr_role` | `TigrRole` | `Gene_has_tigr_role` | 114 | none (but codes have "Main / Sub" structure) | `description` (no `name`) |

## Prerequisite: KG build changes

See [kg_changes_for_category_role_ontologies.md](kg_changes_for_category_role_ontologies.md)
for the full KG requirement doc. Summary:

1. Add `name` property to CyanorakRole and TigrRole nodes (copy from `description`)
2. Create fulltext indexes on all three node types
3. Add `Tigr_role_is_a_tigr_role` hierarchy edges (matching CyanorakRole pattern)

## Explorer changes (this repo)

With KG fixes in place, explorer changes are minimal — just config + docstrings.

### 1. Add 3 entries to ONTOLOGY_CONFIG (`queries_lib.py`)

Same shape as existing entries, no new fields needed:

```python
"cog_category": {
    "label": "CogFunctionalCategory",
    "gene_rel": "Gene_in_cog_category",
    "hierarchy_rels": [],          # flat — 26 single-letter categories
    "fulltext_index": "cogCategoryFullText",
},
"cyanorak_role": {
    "label": "CyanorakRole",
    "gene_rel": "Gene_has_cyanorak_role",
    "hierarchy_rels": ["Cyanorak_role_is_a_cyanorak_role"],
    "fulltext_index": "cyanorakRoleFullText",
},
"tigr_role": {
    "label": "TigrRole",
    "gene_rel": "Gene_has_tigr_role",
    "hierarchy_rels": ["Tigr_role_is_a_tigr_role"],
    "fulltext_index": "tigrRoleFullText",
},
```

### 2. Guard empty `hierarchy_rels` in query builders (`queries_lib.py`)

COG categories are flat (no hierarchy edges). Two builders need a guard:

- **`build_genes_by_ontology`**: When `hierarchy_rels` is `[]`, skip the
  `*0..15` traversal — use `WITH root AS descendant` instead of
  `MATCH (root)<-[:...*0..15]-(descendant)`.
- **`build_gene_ontology_terms`** (leaf_only): When `hierarchy_rels` is `[]`,
  skip the `NOT EXISTS` filter — all terms are leaves in a flat ontology.

### 3. Update MCP tool docstrings (`tools.py`)

Add `"cog_category"`, `"cyanorak_role"`, `"tigr_role"` to the `ontology`
parameter docs in `search_ontology`, `genes_by_ontology`, `gene_ontology_terms`.

### 4. Update tests (`test_query_builders.py`)

- `TestOntologyConfig.test_all_five_keys_present` → expect 8 keys
- Add `cog_category`, `cyanorak_role`, `tigr_role` to parametrized test cases
- Add test for empty `hierarchy_rels` path in `build_genes_by_ontology`
- Add test for empty `hierarchy_rels` + `leaf_only` in `build_gene_ontology_terms`

## Files to modify

| File | Changes |
|---|---|
| [queries_lib.py](multiomics_explorer/kg/queries_lib.py) | ONTOLOGY_CONFIG entries + guard empty hierarchy_rels |
| [tools.py](multiomics_explorer/mcp_server/tools.py) | Docstring updates |
| [test_query_builders.py](tests/unit/test_query_builders.py) | Config test + parametrized cases |

## Verification

1. `pytest tests/unit/test_query_builders.py -v` — all pass
2. After KG rebuild, test via MCP:
   ```
   search_ontology(ontology="cog_category", search_text="energy")
   search_ontology(ontology="cyanorak_role", search_text="DNA")
   genes_by_ontology(ontology="cog_category", term_ids=["cog.category:C"])
   genes_by_ontology(ontology="cyanorak_role", term_ids=["cyanorak.role:F"])  # hierarchy expansion
   gene_ontology_terms(ontology="tigr_role", gene_id="PMM0001")
   ```
