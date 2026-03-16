# Plan: Ontology-Based Gene Lookup — 3-Tool Design

Three new MCP tools for structured ontology gene lookup. Orthogonal to
`search_genes` (fulltext) — these use graph traversal through ontology
hierarchies.

**`search_ontology`** — browse/discover ontology terms by text search
**`genes_by_ontology`** — find genes by ontology ID(s), with hierarchy
expansion
**`gene_ontology_terms`** — reverse lookup: gene → ontology annotations

## Prerequisites (KG Changes)

All resolved in `multiomics_biocypher_kg` — verified 2026-03-15:

- [x] **Unify KEGG to a single `KeggTerm` node type** — 3007 nodes
  (6 category + 42 subcategory + 285 pathway + 2674 ko), `level`
  property present, 5446 `Kegg_term_is_a_kegg_term` hierarchy edges.
  `Gene_has_kegg_ko` points to ko-level KeggTerm nodes.
  **Note:** 13 KEGG "global/overview" pathway nodes (ko01100–ko01320)
  still have empty names. These are cross-pathway overview maps — minor
  issue, won't affect gene lookup.
- [x] **EcNumber / MolecularFunction label separation** — 0 dual-labeled
  nodes. EcNumber labels = `[Entity, NamedThing, EcNumber]`.
  MolecularFunction count = 2096 (clean, no EC contamination).
- [x] **Fulltext indexes on ontology node names** — all 5 created:
  `biologicalProcessFullText` (BiologicalProcess), `molecularFunctionFullText`
  (MolecularFunction), `cellularComponentFullText` (CellularComponent),
  `ecNumberFullText` (EcNumber), `keggFullText` (KeggTerm).

## Out of Scope

- Changes to `search_genes` or other existing tools (except extracting
  `_group_by_organism` from `resolve_gene` for shared use)
- Semantic search / vector embeddings — see
  `vector_embeddings_semantic_search.md`

---

## Ontology Types

5 ontology types, each with its own node label and gene relationship:

| Ontology param | Node Label | Gene → Ontology Relationship |
|----------------|-----------|------------------------------|
| `go_bp` | `BiologicalProcess` | `Gene_involved_in_biological_process` |
| `go_mf` | `MolecularFunction` | `Gene_enables_molecular_function` |
| `go_cc` | `CellularComponent` | `Gene_located_in_cellular_component` |
| `kegg` | `KeggTerm` | `Gene_has_kegg_ko` (only ko-level nodes) |
| `ec` | `EcNumber` | `Gene_catalyzes_ec_number` |

### Hierarchy Edges (for traversal)

All ontology types now use uniform variable-length path traversal.
GO uses `is_a` + `part_of` edges (standard GO ancestry). Regulatory
edges (`negatively_regulates`, `positively_regulates` — BP only) are excluded.

| Ontology | Hierarchy Relationships | Count |
|----------|------------------------|-------|
| GO:BP | `Biological_process_is_a_biological_process` | 8,372 |
|        | `Biological_process_part_of_biological_process` | 322 |
| GO:MF | `Molecular_function_is_a_molecular_function` | 5,326 |
|        | `Molecular_function_part_of_molecular_function` | 4 |
| GO:CC | `Cellular_component_is_a_cellular_component` | 788 |
|        | `Cellular_component_part_of_cellular_component` | 334 |
| EC | `Ec_number_is_a_ec_number` | 14,660 |
| KEGG | `Kegg_term_is_a_kegg_term` | ~5,400 (unified from 3 former edge types) |

### KG ID Formats

IDs are **lowercase** with prefixes:

| Type | Example ID | KeggTerm.level |
|------|-----------|----------------|
| GO (all 3) | `go:0006260` | — |
| KEGG KO | `kegg.orthology:K00001` | `ko` |
| KEGG Pathway | `kegg.pathway:ko00010` | `pathway` |
| KEGG Subcategory | `kegg.subcategory:09101` | `subcategory` |
| KEGG Category | `kegg.category:09100` | `category` |
| EC | `ec:1.-.-.-`, `ec:2.7.7.7` | — |

---

## Shared Config & Helpers

### `ONTOLOGY_CONFIG`

Single config dict in `queries_lib.py` drives all three builders. Avoids
15 separate functions — each builder is a single parameterized function
that looks up config by ontology key.

```python
ONTOLOGY_CONFIG = {
    "go_bp": {
        "label": "BiologicalProcess",
        "gene_rel": "Gene_involved_in_biological_process",
        "hierarchy_rels": [
            "Biological_process_is_a_biological_process",
            "Biological_process_part_of_biological_process",
        ],
        "fulltext_index": "biologicalProcessFullText",
    },
    "go_mf": {
        "label": "MolecularFunction",
        "gene_rel": "Gene_enables_molecular_function",
        "hierarchy_rels": [
            "Molecular_function_is_a_molecular_function",
            "Molecular_function_part_of_molecular_function",
        ],
        "fulltext_index": "molecularFunctionFullText",
    },
    "go_cc": {
        "label": "CellularComponent",
        "gene_rel": "Gene_located_in_cellular_component",
        "hierarchy_rels": [
            "Cellular_component_is_a_cellular_component",
            "Cellular_component_part_of_cellular_component",
        ],
        "fulltext_index": "cellularComponentFullText",
    },
    "ec": {
        "label": "EcNumber",
        "gene_rel": "Gene_catalyzes_ec_number",
        "hierarchy_rels": ["Ec_number_is_a_ec_number"],
        "fulltext_index": "ecNumberFullText",
    },
    "kegg": {
        "label": "KeggTerm",
        "gene_rel": "Gene_has_kegg_ko",
        "hierarchy_rels": ["Kegg_term_is_a_kegg_term"],
        "fulltext_index": "keggFullText",
        "gene_connects_to_level": "ko",  # genes only link to ko-level nodes
    },
}
```

### `_group_by_organism` helper

Extract the grouping logic already in `resolve_gene` (tools.py:149-157)
into a shared helper in `tools.py`:

```python
def _group_by_organism(results: list[dict]) -> dict:
    """Group gene results by organism_strain. Returns {organism: [genes], ...}."""
    grouped: dict[str, list[dict]] = {}
    for row in results:
        org = row.get("organism_strain", "Unknown")
        entry = {k: v for k, v in row.items() if k != "organism_strain"}
        grouped.setdefault(org, []).append(entry)
    return grouped
```

Refactor `resolve_gene` to use it too.

---

## Tool 1: `search_ontology`

Browse ontology terms by text search. Returns matching terms with IDs and
names — no gene counts (they would be misleading since stage 2 expands
hierarchies).

### Signature

```python
@mcp.tool()
def search_ontology(
    ctx: Context,
    search_text: str,
    ontology: str,         # required: "go_bp", "go_mf", "go_cc", "kegg", "ec"
    limit: int = 25,
) -> str:
    """Browse ontology terms by text search (fuzzy, Lucene syntax).

    Use this to discover ontology term IDs, then pass them to
    genes_by_ontology to find genes.

    Supports Lucene query syntax: fuzzy matching (~), wildcards (*),
    exact phrases ("..."), boolean operators (AND, OR).

    Args:
        search_text: Search query against term names. Examples:
            "DNA replication" — phrase match
            "replicat~" — fuzzy match
            "oxido*" — wildcard
            "transport AND membrane" — boolean
        ontology: Which ontology to search. One of:
            "go_bp" (biological process), "go_mf" (molecular function),
            "go_cc" (cellular component), "kegg", "ec".
            For KEGG, searches across all levels — level is encoded in
            the returned ID prefix:
              kegg.category:    (e.g. "Metabolism")
              kegg.subcategory: (e.g. "Carbohydrate metabolism")
              kegg.pathway:     (e.g. "Glycolysis")
              kegg.orthology:   (e.g. "K00001 alcohol dehydrogenase")
        limit: Max results (default 25).
    """
```

**Return columns:** `id`, `name`, `score`

KEGG level is evident from the ID prefix (`kegg.category:`, `kegg.subcategory:`,
`kegg.pathway:`, `kegg.orthology:`) — no separate `level` column needed.

**Error handling:** On `Neo4jClientError`, retry with Lucene special
characters escaped (same pattern as `search_genes` in tools.py:204-212).

**Empty results:** Return `{"results": [], "total": 0, "query": search_text}`
following the `search_genes` pattern.

### Query Builder

Single parameterized function in `queries_lib.py`. The fulltext index
name is looked up from `ONTOLOGY_CONFIG` and hardcoded into the Cypher
string (Neo4j fulltext index names cannot be parameterized).

```python
def build_search_ontology(
    *, ontology: str, search_text: str, limit: int = 25,
) -> tuple[str, dict]:
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    cfg = ONTOLOGY_CONFIG[ontology]
    index_name = cfg["fulltext_index"]
    cypher = (
        f"CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
        "YIELD node AS t, score\n"
        "RETURN t.id AS id, t.name AS name, score\n"
        "ORDER BY score DESC\n"
        "LIMIT $limit"
    )
    return cypher, {"search_text": search_text, "limit": limit}
```

---

## Tool 2: `genes_by_ontology`

Find genes by ontology ID(s). Walks hierarchy downward using
variable-length paths to collect all descendant terms, then returns
genes annotated to any term in the subtree.

### Signature

```python
@mcp.tool()
def genes_by_ontology(
    ctx: Context,
    term_ids: list[str],       # ontology IDs from search_ontology
    ontology: str,             # required: "go_bp", "go_mf", "go_cc", "kegg", "ec"
    organism: str | None = None,
    limit: int = 25,
) -> str:
    """Find genes annotated to ontology terms, with hierarchy expansion.

    Takes ontology term IDs (from search_ontology) and finds all genes
    annotated to those terms or any of their descendant terms in the
    ontology hierarchy.

    Args:
        term_ids: One or more ontology term IDs (from search_ontology).
        ontology: Which ontology the IDs belong to. One of:
            "go_bp" (biological process), "go_mf" (molecular function),
            "go_cc" (cellular component), "kegg", "ec".
        organism: Optional organism filter (fuzzy match on strain name).
        limit: Max gene results (default 25).
    """
```

**Return format:** Same as `resolve_gene` — genes grouped by organism
using the shared `_group_by_organism` helper. No `matching_terms` —
hierarchy expansion can produce 60+ terms per gene (redundant hierarchy
noise). Use `gene_ontology_terms` for per-gene detail.

```json
{
  "results": {
    "Prochlorococcus MED4": [
      {"locus_tag": "PMM0120", "gene_name": "dnaN", "product": "..."}
    ],
    "Alteromonas macleodii MIT1002": [...]
  },
  "total": 42
}
```

**Columns per gene:** `locus_tag`, `gene_name`, `product`
(organism is the grouping key)

### Query Builder

Single parameterized function in `queries_lib.py`. Looks up label,
relationships, and KEGG-specific `gene_connects_to_level` from
`ONTOLOGY_CONFIG`.

```python
def build_genes_by_ontology(
    *, ontology: str, term_ids: list[str],
    organism: str | None = None, limit: int = 25,
) -> tuple[str, dict]:
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    cfg = ONTOLOGY_CONFIG[ontology]
    label = cfg["label"]
    gene_rel = cfg["gene_rel"]
    hierarchy = "|".join(cfg["hierarchy_rels"])
    level_filter = cfg.get("gene_connects_to_level")

    level_clause = (
        f"\nWITH DISTINCT descendant\nWHERE descendant.level = '{level_filter}'"
        if level_filter else "\nWITH DISTINCT descendant"
    )

    cypher = (
        f"MATCH (root:{label}) WHERE root.id IN $term_ids\n"
        f"MATCH (root)<-[:{hierarchy}*0..15]-(descendant)"
        f"{level_clause}\n"
        f"MATCH (g:Gene)-[:{gene_rel}]->(descendant)\n"
        "WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')\n"
        "       WHERE toLower(g.organism_strain) CONTAINS word))\n"
        "RETURN DISTINCT g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.organism_strain AS organism_strain\n"
        "ORDER BY g.locus_tag\n"
        "LIMIT $limit"
    )
    return cypher, {
        "term_ids": term_ids, "organism": organism, "limit": limit,
    }
```

**Generated Cypher examples:**

GO:BP:
```cypher
MATCH (root:BiologicalProcess) WHERE root.id IN $term_ids
MATCH (root)<-[:Biological_process_is_a_biological_process|Biological_process_part_of_biological_process*0..15]-(descendant)
WITH DISTINCT descendant
MATCH (g:Gene)-[:Gene_involved_in_biological_process]->(descendant)
WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
RETURN DISTINCT g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.organism_strain AS organism_strain
ORDER BY g.locus_tag
LIMIT $limit
```

KEGG (adds `WITH DISTINCT descendant WHERE descendant.level = 'ko'`):
```cypher
MATCH (root:KeggTerm) WHERE root.id IN $term_ids
MATCH (root)<-[:Kegg_term_is_a_kegg_term*0..15]-(descendant)
WITH DISTINCT descendant
WHERE descendant.level = 'ko'
MATCH (g:Gene)-[:Gene_has_kegg_ko]->(descendant)
WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
RETURN DISTINCT g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.organism_strain AS organism_strain
ORDER BY g.locus_tag
LIMIT $limit
```

---

## Tool 3: `gene_ontology_terms`

Reverse lookup: given a gene, return its ontology annotations for a
specific ontology type. By default returns only leaf terms (most specific
annotations) — the ones that aren't ancestors of other annotations the
gene has.

Example: argR (`MIT1002_03493`) has 79 BP annotations, but only 12 leaf
terms (e.g. "arginine metabolic process", "plasmid recombination",
"regulation of arginine biosynthetic process"). The other 67 are generic
parents like "metabolic process" and "cellular process".

### Signature

```python
@mcp.tool()
def gene_ontology_terms(
    ctx: Context,
    gene_id: str,
    ontology: str,           # required: "go_bp", "go_mf", "go_cc", "kegg", "ec"
    leaf_only: bool = True,
    limit: int = 50,
) -> str:
    """Get ontology annotations for a gene.

    Returns the ontology terms a gene is annotated to. By default returns
    only the most specific (leaf) terms — those that are not ancestors of
    other terms the gene is annotated to.

    Args:
        gene_id: Gene locus_tag (e.g. "PMM0001").
        ontology: Which ontology to return. One of:
            "go_bp" (biological process), "go_mf" (molecular function),
            "go_cc" (cellular component), "kegg", "ec".
        leaf_only: If True (default), return only the most specific terms.
            If False, return all annotations.
        limit: Max results (default 50). Relevant mainly with
            leaf_only=False, which can return many ancestor terms.
    """
```

**Return columns:** `id`, `name` (uniform across all ontology types)

### Query Builder

Single parameterized function in `queries_lib.py`. Uses `ONTOLOGY_CONFIG`
for label, gene relationship, and hierarchy relationships.

For KEGG, `leaf_only` is effectively always true (genes only connect to
KO-level nodes), so the NOT EXISTS subquery is a no-op. No special
KEGG query shape — same `id`, `name` return columns as all others.

```python
def build_gene_ontology_terms(
    *, ontology: str, gene_id: str, leaf_only: bool = True, limit: int = 50,
) -> tuple[str, dict]:
    if ontology not in ONTOLOGY_CONFIG:
        raise ValueError(f"Invalid ontology '{ontology}'. Valid: {sorted(ONTOLOGY_CONFIG)}")
    cfg = ONTOLOGY_CONFIG[ontology]
    label = cfg["label"]
    gene_rel = cfg["gene_rel"]
    hierarchy = "|".join(cfg["hierarchy_rels"])

    if leaf_only:
        cypher = (
            f"MATCH (g:Gene {{locus_tag: $gene_id}})-[:{gene_rel}]->(t:{label})\n"
            "WHERE NOT EXISTS {\n"
            f"  MATCH (g)-[:{gene_rel}]->(child:{label})\n"
            f"        -[:{hierarchy}]->(t)\n"
            "}\n"
            "RETURN t.id AS id, t.name AS name\n"
            "ORDER BY t.name\n"
            "LIMIT $limit"
        )
    else:
        cypher = (
            f"MATCH (g:Gene {{locus_tag: $gene_id}})-[:{gene_rel}]->(t:{label})\n"
            "RETURN t.id AS id, t.name AS name\n"
            "ORDER BY t.name\n"
            "LIMIT $limit"
        )
    return cypher, {"gene_id": gene_id, "limit": limit}
```

**Generated Cypher examples:**

GO:BP — leaf_only=True:
```cypher
MATCH (g:Gene {locus_tag: $gene_id})-[:Gene_involved_in_biological_process]->(t:BiologicalProcess)
WHERE NOT EXISTS {
  MATCH (g)-[:Gene_involved_in_biological_process]->(child:BiologicalProcess)
        -[:Biological_process_is_a_biological_process|Biological_process_part_of_biological_process]->(t)
}
RETURN t.id AS id, t.name AS name
ORDER BY t.name
LIMIT $limit
```

GO:BP — leaf_only=False:
```cypher
MATCH (g:Gene {locus_tag: $gene_id})-[:Gene_involved_in_biological_process]->(t:BiologicalProcess)
RETURN t.id AS id, t.name AS name
ORDER BY t.name
LIMIT $limit
```

KEGG (same shape — leaf_only NOT EXISTS is a no-op since genes only
connect to KOs, which have no children):
```cypher
MATCH (g:Gene {locus_tag: $gene_id})-[:Gene_has_kegg_ko]->(t:KeggTerm)
WHERE NOT EXISTS {
  MATCH (g)-[:Gene_has_kegg_ko]->(child:KeggTerm)
        -[:Kegg_term_is_a_kegg_term]->(t)
}
RETURN t.id AS id, t.name AS name
ORDER BY t.name
LIMIT $limit
```

---

## Implementation Order

| Order | Change | Where |
|-------|--------|-------|
| 0 | Regenerate schema baseline: `uv run multiomics-explorer schema-snapshot` | `config/schema_baseline.yaml` |
| 1 | `ONTOLOGY_CONFIG` dict + `build_search_ontology`, `build_genes_by_ontology`, `build_gene_ontology_terms` (3 parameterized functions) | `queries_lib.py` |
| 2 | `_group_by_organism` helper + `search_ontology`, `genes_by_ontology`, `gene_ontology_terms` tool wrappers | `tools.py` |
| 3 | Tests + docs (parallel) | Explorer |

Step 0 is a prerequisite (schema baseline must match live KG).
Step 1 is self-contained. Step 2 depends on step 1.
Tests and docs can run in parallel after step 2.

**Already done** (stale KEGG/EC references fixed 2026-03-15):
- `kg/queries.py` — KEGG few-shot updated to `KeggTerm` + `Kegg_term_is_a_kegg_term`
- `config/prompts.yaml` — KEGG chain updated
- `AGENT.md` — MolecularFunction count fixed, KEGG nodes/rels updated

## Agent Assignments

| Step | Agent | Task | Depends on |
|------|-------|------|------------|
| 0 | manual | `uv run multiomics-explorer schema-snapshot` + `uv run multiomics-explorer schema-validate` | — |
| 1 | **query-builder** | Add `ONTOLOGY_CONFIG` + 3 parameterized builders to `queries_lib.py` | — |
| 2 | **tool-wrapper** | Add `_group_by_organism` helper, 3 tool wrappers (with Lucene retry for `search_ontology`), refactor `resolve_gene` to use helper. **Constraint:** `resolve_gene` output format must not change — verify JSON structure matches before/after. | 1 |
| 3a | **test-updater** | Add unit, integration, eval, and regression tests | 2 |
| 3b | **doc-updater** | Update `CLAUDE.md`, `README.md`, `docs/testplans/testplan.md` | 2 |
| 4 | **code-reviewer** | Review all changes against this plan, run unit tests | 3a, 3b |

---

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**

`ONTOLOGY_CONFIG`:
- [ ] All 5 ontology keys present with required fields
- [ ] Only `kegg` has `gene_connects_to_level`

`build_search_ontology`:
- [ ] Each ontology type produces Cypher with correct fulltext index name (hardcoded, not parameterized)
- [ ] All ontology types return same columns: `id`, `name`, `score`
- [ ] Invalid ontology value raises `ValueError` with valid options listed
- [ ] `search_text` passed as parameter (not interpolated)

`build_genes_by_ontology`:
- [ ] GO:BP → hierarchy expansion with `is_a|part_of*0..15` variable-length path
- [ ] EC → hierarchy expansion with `Ec_number_is_a_ec_number*0..15`
- [ ] KEGG → hierarchy expansion with `Kegg_term_is_a_kegg_term*0..15` + `WHERE descendant.level = 'ko'`
- [ ] Non-KEGG ontologies do NOT have level filter in Cypher
- [ ] Organism filter present in WHERE clause
- [ ] `term_ids` passed as parameter

`build_gene_ontology_terms`:
- [ ] Each ontology type uses correct node label and gene relationship from config
- [ ] `leaf_only=True` adds NOT EXISTS subquery with correct hierarchy edges
- [ ] `leaf_only=False` returns simple match without NOT EXISTS
- [ ] All ontology types return same columns: `id`, `name`
- [ ] `limit` parameter present in Cypher
- [ ] Invalid ontology value raises `ValueError` with valid options listed

**`tests/unit/test_tool_wrappers.py`:**

`search_ontology`:
- [ ] Mock query results, verify JSON response with `id`, `name`, `score`
- [ ] KEGG results have same columns as other ontologies
- [ ] Error on invalid ontology value
- [ ] Lucene special chars trigger retry with escaped query (Neo4jClientError)

`genes_by_ontology`:
- [ ] KEGG uses `Kegg_term_is_a_kegg_term` with `level = 'ko'` filter
- [ ] Invalid ontology value → error
- [ ] Mock query results, verify grouped-by-organism response format (uses `_group_by_organism`)
- [ ] Tool registration count updated

`gene_ontology_terms`:
- [ ] Mock query results, verify JSON response with `id` and `name`
- [ ] Invalid ontology value raises error
- [ ] `limit` parameter passed through

### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

`search_ontology`:
- [ ] `search_text="replication", ontology="go_bp"` → returns BP terms
- [ ] `search_text="oxidoreductase", ontology="ec"` → returns EC terms
- [ ] `search_text="metabolism", ontology="kegg"` → returns results from
  multiple KEGG levels (visible from ID prefixes)

`genes_by_ontology`:
- [ ] GO:BP by ID with hierarchy: `go:0006139` (nucleobase-containing
  compound metabolic process) → genes from 332 descendant terms
- [ ] GO:BP direct: specific leaf term → fewer genes than parent
- [ ] EC hierarchy: `ec:1.-.-.-` → all oxidoreductases via tree walk
- [ ] EC leaf: `ec:2.7.7.7` → DNA polymerases (direct only)
- [ ] KEGG Category: `kegg.category:09100` (Metabolism) → genes via
  `Kegg_term_is_a_kegg_term` hierarchy down to ko-level
- [ ] KEGG KO direct: `kegg.orthology:K00001` → genes (hierarchy depth 0)
- [ ] Organism filter: same term with/without organism → filtered subset
- [ ] Multiple term_ids: two GO IDs → union of results

`gene_ontology_terms`:
- [ ] BP leaf only: `gene_id="MIT1002_03493", ontology="go_bp"` → 12 leaf
  terms (argR)
- [ ] BP all: same gene with `leaf_only=False` → 79 terms
- [ ] EC: gene with EC annotations → returns EC numbers with `id`, `name`
- [ ] KEGG: gene with KOs → returns KOs with `id`, `name` (same columns as others)
- [ ] Gene with no annotations for given ontology → empty result
- [ ] `limit` caps results

### Eval cases (`tests/evals/cases.yaml`)

```yaml
- id: search_ontology_go_bp
  tool: search_ontology
  desc: Search biological processes for replication
  params:
    search_text: replication
    ontology: go_bp
  expect:
    min_rows: 1
    columns: [id, name, score]

- id: search_ontology_kegg
  tool: search_ontology
  desc: Search KEGG for metabolism
  params:
    search_text: metabolism
    ontology: kegg
  expect:
    min_rows: 1
    columns: [id, name, score]

- id: search_ontology_ec
  tool: search_ontology
  desc: Search EC for oxidoreductase
  params:
    search_text: oxidoreductase
    ontology: ec
  expect:
    min_rows: 1
    columns: [id, name, score]

- id: find_genes_go_bp_hierarchy
  tool: genes_by_ontology
  desc: GO BP hierarchy expansion finds genes in descendant terms
  params:
    term_ids: ["go:0006139"]
    ontology: go_bp
  expect:
    min_total: 10  # total field in grouped response

- id: find_genes_ec_hierarchy
  tool: genes_by_ontology
  desc: EC hierarchy from top-level class
  params:
    term_ids: ["ec:1.-.-.-"]
    ontology: ec
  expect:
    min_total: 10

- id: find_genes_kegg_category
  tool: genes_by_ontology
  desc: KEGG Category traversal to genes
  params:
    term_ids: ["kegg.category:09100"]
    ontology: kegg
  expect:
    min_total: 10

- id: find_genes_kegg_ko_direct
  tool: genes_by_ontology
  desc: KEGG KO direct lookup
  params:
    term_ids: ["kegg.orthology:K00001"]
    ontology: kegg
  expect:
    min_total: 1

- id: find_genes_with_organism
  tool: genes_by_ontology
  desc: Organism filter restricts results
  params:
    term_ids: ["go:0006139"]
    ontology: go_bp
    organism: MED4
  expect:
    min_total: 1
    result_key_contains: Prochlorococcus MED4  # organism appears as grouping key in results dict

- id: find_genes_multiple_ids
  tool: genes_by_ontology
  desc: Multiple GO term IDs return combined results
  params:
    term_ids: ["go:0006260", "go:0006139"]
    ontology: go_bp
  expect:
    min_total: 1

- id: gene_ontology_terms_bp_leaf
  tool: gene_ontology_terms
  desc: argR leaf BP annotations (most specific)
  params:
    gene_id: MIT1002_03493
    ontology: go_bp
  expect:
    min_rows: 5
    max_rows: 20
    columns: [id, name]

- id: gene_ontology_terms_bp_all
  tool: gene_ontology_terms
  desc: argR all BP annotations (full hierarchy)
  params:
    gene_id: MIT1002_03493
    ontology: go_bp
    leaf_only: false
  expect:
    min_rows: 50
    columns: [id, name]

- id: gene_ontology_terms_kegg
  tool: gene_ontology_terms
  desc: Gene KEGG KO annotations
  params:
    gene_id: MIT1002_03493
    ontology: kegg
  expect:
    min_rows: 1
    columns: [id, name]

- id: gene_ontology_terms_ec
  tool: gene_ontology_terms
  desc: Gene EC number annotations
  params:
    gene_id: MIT1002_03493
    ontology: ec
  expect:
    min_rows: 0
```

### Regression snapshots (`tests/regression/`)

Add parameterized builder calls to `TOOL_BUILDERS` in
`tests/regression/test_regression.py`. Use lambdas or `functools.partial`
to bind the `ontology` parameter for each variant:

```python
from functools import partial
from multiomics_explorer.kg.queries_lib import (
    build_search_ontology,
    build_genes_by_ontology,
    build_gene_ontology_terms,
)

# Add per-ontology entries using partial application:
TOOL_BUILDERS = {
    ...
    "search_ontology_go_bp": partial(build_search_ontology, ontology="go_bp"),
    "search_ontology_kegg": partial(build_search_ontology, ontology="kegg"),
    "genes_by_ontology_go_bp": partial(build_genes_by_ontology, ontology="go_bp"),
    "genes_by_ontology_kegg": partial(build_genes_by_ontology, ontology="kegg"),
    "search_ontology_ec": partial(build_search_ontology, ontology="ec"),
    "genes_by_ontology_ec": partial(build_genes_by_ontology, ontology="ec"),
    "gene_ontology_terms_go_bp": partial(build_gene_ontology_terms, ontology="go_bp"),
    "gene_ontology_terms_kegg": partial(build_gene_ontology_terms, ontology="kegg"),
    "gene_ontology_terms_ec": partial(build_gene_ontology_terms, ontology="ec"),
    # representative ontologies covering GO (multi-rel hierarchy), KEGG (level filter), EC (deep numeric hierarchy)
}
```

---

## Migration Impacts (from KG schema changes)

Explorer-side files that referenced old KEGG types or stale EC/MF labels.

| File | What was stale | Status |
|------|---------------|--------|
| `kg/queries.py:229-237` | Few-shot KEGG example used `KeggOrthologousGroup`, `Ko_in_kegg_pathway`, `KeggPathway` | **Fixed** 2026-03-15 |
| `config/prompts.yaml:50` | Documented old KEGG chain | **Fixed** 2026-03-15 |
| `AGENT.md:110-137` | Wrong MolecularFunction count, old KEGG node/rel names | **Fixed** 2026-03-15 |
| `config/schema_baseline.yaml` | Old KEGG types, stale EC/MF labels | **Step 0:** `uv run multiomics-explorer schema-snapshot` |

Note: `Gene_has_kegg_ko` edge name stays the same — it just points to
`KeggTerm` nodes (ko-level) instead of `KeggOrthologousGroup` nodes.

---

## Performance Considerations

- **Broad hierarchy walks**: A top-level term like `go:0008150`
  (biological_process, the root) would traverse the entire GO tree.
  The `LIMIT` caps gene results but the traversal itself can be slow.
  Mitigate with a depth cap on variable-length paths (e.g., `*0..15`).

---

## Design Decisions

- **Depth limit**: Cap variable-length paths at `*0..15`. GO max depth is
  ~15, so this covers the full hierarchy. Prevents runaway queries on
  root-level terms while ensuring no real results are silently dropped.
- **GO:MF / EcNumber dual-label**: Fixed in KG — EcNumber nodes no
  longer carry MolecularFunction label. MolecularFunction count = 2096
  (clean). Verified 2026-03-15.
- **Parametrized builders**: Single `ONTOLOGY_CONFIG` dict + 3 builder
  functions instead of 15 separate functions. Reduces duplication, makes
  adding new ontology types a config change.
- **Uniform return shape**: All ontology types return flat `id`, `name`
  columns — including KEGG. No special nested `ancestors` field. KEGG
  hierarchy context is available via `search_ontology` or `run_cypher`.
- **Empty results**: Follow existing pattern — return JSON with empty
  results + query context. Matches `resolve_gene` (`{"results": {},
  "message": "..."}`) and `search_genes` (`{"results": [], "total": 0,
  "query": "..."}`).

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add `search_ontology`, `genes_by_ontology`, `gene_ontology_terms` rows to MCP Tools table |
| `README.md` | Add entries to MCP tools section, bump tool count |
| `AGENT.md` | Fix stale counts (MolecularFunction ~9400→~2096), replace `KeggOrthologousGroup`/`KeggPathway`/`Ko_in_kegg_pathway` with `KeggTerm`/`Kegg_term_is_a_kegg_term`, add new tool rows |
| `config/prompts.yaml` | Update KEGG relationship documentation for `KeggTerm` schema |
| `kg/queries.py` | Update KEGG few-shot examples |
| `config/schema_baseline.yaml` | Regenerate from live KG (old KEGG types, stale EC/MF labels) |
| `docs/testplans/testplan.md` | Add test plan sections for all three tools |
