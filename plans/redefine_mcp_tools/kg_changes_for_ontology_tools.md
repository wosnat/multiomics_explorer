# Plan: KG Schema Changes for Ontology Tools

Required changes in `multiomics_biocypher_kg` to support the 3 new ontology
MCP tools (`search_ontology`, `genes_by_ontology`, `gene_ontology_terms`).
See `new_tool_find_genes_by_function.md` for the full tool design.

---

## Change 1: Unify KEGG node types to `KeggTerm`

### Problem

KEGG uses 4 separate node types with 3 different hierarchy edge types:

```
KeggCategory ←[:Kegg_subcategory_in_kegg_category]— KeggSubcategory
             ←[:Kegg_pathway_in_kegg_subcategory]— KeggPathway
             ←[:Ko_in_kegg_pathway]— KeggOrthologousGroup
```

This forces level-specific Cypher queries — every tool needs 4 code paths
for KEGG while GO and EC use a single uniform `*0..10` traversal.

Additionally, `KeggPathway.name` is empty for all 285 pathway nodes.

### Current state

| Node type | Count | Properties | `name` populated? |
|-----------|-------|------------|-------------------|
| `KeggCategory` | 6 | id, name, preferred_id | Yes |
| `KeggSubcategory` | 42 | id, name, preferred_id | Yes |
| `KeggPathway` | 285 | id, name, preferred_id | **No — empty string** |
| `KeggOrthologousGroup` | 2,674 | id, name, preferred_id | Yes |

Hierarchy edges:
- `Kegg_subcategory_in_kegg_category` (Subcategory → Category)
- `Kegg_pathway_in_kegg_subcategory` (Pathway → Subcategory)
- `Ko_in_kegg_pathway` (KO → Pathway)

### Target state

Single node type: **`KeggTerm`**

| Property | Type | Description |
|----------|------|-------------|
| `id` | string | Existing IDs: `kegg.category:09100`, `kegg.subcategory:09101`, `kegg.pathway:ko00010`, `kegg.orthology:K00001` |
| `name` | string | **Must be populated for all levels**, including pathways |
| `level` | string | `"category"`, `"subcategory"`, `"pathway"`, or `"ko"` |
| `preferred_id` | string | Existing preferred_id |

Single hierarchy edge: **`Kegg_term_is_a_kegg_term`**

Existing gene edge unchanged: `Gene_has_kegg_ko` → ko-level `KeggTerm` nodes.

### What to change in `multiomics_biocypher_kg`

1. **Schema definition** — replace 4 KEGG entity types with single `KeggTerm`
   entity type. Add `level` property. Define single `Kegg_term_is_a_kegg_term`
   relationship type.

2. **KEGG data adapter** — merge the 4 node generators into one that yields
   `KeggTerm` nodes with the `level` property set. Merge the 3 edge generators
   into one that yields `Kegg_term_is_a_kegg_term` edges.

3. **Pathway name population** — fix the pipeline step that populates KEGG
   pathway names. Currently yields `name: ""` for all pathways. Likely a
   missing API call or data source. The KEGG REST API at
   `https://rest.kegg.jp/list/pathway` provides pathway names.

4. **BioCypher schema config** — update `schema_config.yaml` (or equivalent)
   to define `KeggTerm` as a single entity with proper parent class mapping.

### Verification

After rebuild:
```cypher
-- All KEGG nodes are KeggTerm
MATCH (n:KeggTerm) RETURN n.level, count(n) ORDER BY n.level
-- Expected: category=6, ko=2674, pathway=285, subcategory=42

-- All pathway names populated
MATCH (n:KeggTerm {level: 'pathway'}) WHERE n.name = '' RETURN count(n)
-- Expected: 0

-- Hierarchy edges exist
MATCH ()-[r:Kegg_term_is_a_kegg_term]->() RETURN count(r)
-- Expected: ~5400

-- Old node types don't exist
MATCH (n:KeggCategory) RETURN count(n)
-- Expected: 0

-- Gene edges still work
MATCH (g:Gene)-[:Gene_has_kegg_ko]->(ko:KeggTerm {level: 'ko'}) RETURN count(g) LIMIT 1
-- Expected: > 0
```

---

## Change 2: Remove spurious MolecularFunction label from EcNumber nodes

### Problem

All 7,337 EcNumber nodes carry a `MolecularFunction` label (plus
`BiologicalProcessOrActivity`, `Entity`, `NamedThing`). This is likely
BioCypher parent-class inheritance — EcNumber inherits from
MolecularFunction in the Biolink ontology.

Impact:
- `MATCH (mf:MolecularFunction)` returns 9,433 nodes (2,096 real MF +
  7,337 EC numbers)
- EC hierarchy edges (`Ec_number_is_a_ec_number`) appear as
  MolecularFunction edges
- `search_ontology` for GO:MF would include EC numbers in results
- `gene_ontology_terms` for GO:MF would include EC annotations

### Current state

```
EcNumber node labels: [:EcNumber, :MolecularFunction, :BiologicalProcessOrActivity, :Entity, :NamedThing]
```

### Target state

```
EcNumber node labels: [:EcNumber, :Entity, :NamedThing]
MolecularFunction node labels: [:MolecularFunction, :BiologicalProcessOrActivity, :Entity, :NamedThing]
```

No overlap between the two.

### What to change in `multiomics_biocypher_kg`

1. **Schema definition** — ensure `EcNumber` does NOT inherit from
   `MolecularFunction` in the BioCypher schema config. Options:
   - Override the parent class for EcNumber to skip MolecularFunction
   - Use a custom entity definition that doesn't carry the MF label
   - Post-process to remove the label after loading

2. **Verify GO:MF node count** — after fix, `MATCH (mf:MolecularFunction)`
   should return ~2,096 nodes (not 9,433).

### Verification

After rebuild:
```cypher
-- No dual-labeled nodes
MATCH (n:EcNumber:MolecularFunction) RETURN count(n)
-- Expected: 0

-- EC nodes have correct labels
MATCH (n:EcNumber) RETURN labels(n), count(n)
-- Expected: [EcNumber, Entity, NamedThing] → 7337

-- MF count is clean
MATCH (n:MolecularFunction) RETURN count(n)
-- Expected: ~2096 (not 9433)

-- EC edges only on EcNumber
MATCH ()-[r:Ec_number_is_a_ec_number]->() RETURN count(r)
-- Unchanged: 14660

-- MF edges only on MolecularFunction
MATCH (n:MolecularFunction)-[r:Ec_number_is_a_ec_number]-() RETURN count(r)
-- Expected: 0
```

---

## Change 3: Add FULLTEXT indexes on ontology node names

### Problem

`search_ontology` uses fuzzy/Lucene text search on ontology term names.
Without fulltext indexes, queries fall back to full scans.

### Indexes to create

5 indexes, one per `ontology` param value:

| Index name | Node label(s) | Property | Node count |
|-----------|--------------|----------|------------|
| `biologicalProcessFullText` | `BiologicalProcess` | `name` | 2,448 |
| `molecularFunctionFullText` | `MolecularFunction` | `name` | ~2,096 (after EC fix) |
| `cellularComponentFullText` | `CellularComponent` | `name` | 328 |
| `ecNumberFullText` | `EcNumber` | `name` | 7,337 |
| `keggFullText` | `KeggTerm` | `name` | 3,007 |

### What to change in `multiomics_biocypher_kg`

Add index creation to the post-load script (or BioCypher index config):

```cypher
CREATE FULLTEXT INDEX biologicalProcessFullText
  FOR (n:BiologicalProcess) ON EACH [n.name];

CREATE FULLTEXT INDEX molecularFunctionFullText
  FOR (n:MolecularFunction) ON EACH [n.name];

CREATE FULLTEXT INDEX cellularComponentFullText
  FOR (n:CellularComponent) ON EACH [n.name];

CREATE FULLTEXT INDEX ecNumberFullText
  FOR (n:EcNumber) ON EACH [n.name];

CREATE FULLTEXT INDEX keggFullText
  FOR (n:KeggTerm) ON EACH [n.name];
```

**Important:** `molecularFunctionFullText` depends on Change 2 (EC/MF
label fix). If created before the fix, the index will include EC nodes.

### Verification

```cypher
SHOW FULLTEXT INDEXES
YIELD name, labelsOrTypes, properties
WHERE name IN ['biologicalProcessFullText', 'molecularFunctionFullText',
               'cellularComponentFullText', 'ecNumberFullText', 'keggFullText']
RETURN name, labelsOrTypes, properties

-- Test that fulltext search works
CALL db.index.fulltext.queryNodes('biologicalProcessFullText', 'replication')
YIELD node, score
RETURN node.id, node.name, score
LIMIT 5
```

---

## Implementation Order

Changes 1 and 2 are independent and can be done in parallel. Change 3
depends on both (MF index needs EC fix, KEGG index needs KeggTerm).

```
Change 1 (KEGG unification) ──┐
                               ├── Change 3 (fulltext indexes) ── Rebuild KG
Change 2 (EC/MF label fix) ───┘
```

After KG rebuild, update explorer-side:
- Regenerate `config/schema_baseline.yaml` from live KG
- Update `config/prompts.yaml` KEGG documentation
- Update `kg/queries.py` KEGG few-shot example
- Implement the 3 new ontology tools (per `new_tool_find_genes_by_function.md`)

---

## Risks

- **KEGG pathway names** — need to confirm the KEGG REST API provides
  pathway names in a format the pipeline can consume. If not, pathway-level
  search will return results with empty names.
- **BioCypher parent class inheritance** — the EC/MF label fix may require
  understanding BioCypher's schema inheritance model. The simplest fix may
  be a post-load Cypher command (`MATCH (n:EcNumber) REMOVE n:MolecularFunction`)
  if the schema config approach is complex.
- **Downstream breakage** — the `run_cypher` tool lets users write raw Cypher.
  Any saved queries referencing `KeggOrthologousGroup` etc. will break.
  This is acceptable since no one is relying on the current schema.
