# Plan: `find_genes_by_function` Tool

New MCP tool — graph-traversal search for genes by GO process, KEGG pathway,
or EC number. Orthogonal to `find_gene` (fulltext) — this is structured
ontology lookup.

## Tool signature

```python
@mcp.tool()
def find_genes_by_function(
    ctx: Context,
    search_text: str,
    ontology: str | None = None,   # "go", "kegg", "ec" or None (all)
    organism: str | None = None,
    limit: int = 25,
) -> str:
    """Find genes by biological function, KEGG pathway, or enzyme class.

    Searches ontology nodes (BiologicalProcess, KeggOrthologousGroup, EcNumber)
    by name, then follows edges back to Gene nodes.

    Accepts GO/KEGG/EC IDs directly (e.g. "GO:0006260", "K02338", "2.7.7.7")
    or text queries (e.g. "DNA replication", "photosynthesis").

    Args:
        search_text: Ontology term name or ID. Partial EC numbers supported
            (e.g. "1.-.-.-" for all oxidoreductases).
        ontology: Limit to "go", "kegg", or "ec". Searches all if None.
        organism: Optional organism filter.
        limit: Max results (default 25).
    """
```

## Query builder — `build_find_genes_by_function`

**Files:** `queries_lib.py`

Detect whether input is an ID or text:
- GO ID: matches `GO:\d+`
- KEGG KO: matches `K\d{5}`
- EC number (full or partial): matches `\d+\.[-\d]+\.[-\d]+\.[-\d]+`
  e.g. `2.7.7.7`, `1.-.-.-`, `2.7.-.-`. EcNumber nodes already exist for
  every level of the hierarchy (`ec:1.-.-.-` = "Oxidoreductases", etc.).
  Normalize input to `ec:` prefix and exact-match on `e.id`.
- Otherwise: text search using CONTAINS on ontology node `name`

Example Cypher for GO text search:
```cypher
MATCH (bp:BiologicalProcess)
WHERE bp.name CONTAINS $search_text
MATCH (g:Gene)-[:Gene_involved_in_biological_process]->(bp)
WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.organism_strain AS organism_strain,
       collect(DISTINCT bp.name) AS matching_terms
ORDER BY g.locus_tag
LIMIT $limit
```

When `ontology` is None, UNION across all three ontology types.

**No KG changes needed** — uses existing edges:
- `Gene_involved_in_biological_process → BiologicalProcess`
- `Gene_has_kegg_ko → KeggOrthologousGroup`
- `Gene_catalyzes_ec_number → EcNumber`

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**
- GO ID detection (`GO:0006260` → exact match on BiologicalProcess)
- KEGG KO detection (`K02338` → exact match on KeggOrthologousGroup)
- EC full detection (`2.7.7.7` → exact match on `ec:2.7.7.7`)
- EC partial detection (`1.-.-.-` → exact match on `ec:1.-.-.-`)
- Text fallback (`DNA replication` → CONTAINS on ontology node name)
- Verify correct Cypher structure for each ontology type
- Verify UNION when `ontology` is None
- Organism filter present in WHERE clause

**`tests/unit/test_tool_wrappers.py`:**
- Mock query results, verify JSON response structure
- Verify `matching_terms` field present
- Error handling for invalid ontology value

### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

- GO text search: `"DNA replication"` → returns genes with GO process matches
- KEGG KO by ID: `"K02338"` → returns genes with that KO
- EC full: `"2.7.7.7"` → returns DNA polymerases
- EC partial: `"1.-.-.-"` → returns oxidoreductases (broader set)
- With organism filter: `"DNA replication", organism="MED4"` → only MED4 genes
- UNION mode: `ontology=None` → results from multiple ontology types
- Cross-organism (no organism filter):
  - GO `"response to oxidative stress"` → returns both Prochlorococcus and
    Alteromonas genes (238 genes across 13 strains)
  - EC `"1.-.-.-"` → oxidoreductases from both (229 genes, 13 strains)
  - KEGG `"K06147"` → ABC transporters from both (64 genes, 13 strains)
  - Assert results contain at least one Prochlorococcus and one Alteromonas gene

### Eval cases (`tests/evals/cases.yaml`)

```yaml
- id: find_genes_by_function_go_text
  tool: find_genes_by_function
  desc: GO text search finds genes in DNA replication
  params:
    search_text: DNA replication
    ontology: go
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain, matching_terms]

- id: find_genes_by_function_kegg_id
  tool: find_genes_by_function
  desc: KEGG KO lookup by ID
  params:
    search_text: K02338
    ontology: kegg
  expect:
    min_rows: 1

- id: find_genes_by_function_ec_full
  tool: find_genes_by_function
  desc: Full EC number lookup
  params:
    search_text: "2.7.7.7"
    ontology: ec
  expect:
    min_rows: 1

- id: find_genes_by_function_ec_partial
  tool: find_genes_by_function
  desc: Partial EC matches all oxidoreductases
  params:
    search_text: "1.-.-.-"
    ontology: ec
  expect:
    min_rows: 5

- id: find_genes_by_function_with_organism
  tool: find_genes_by_function
  desc: Organism filter restricts results
  params:
    search_text: photosynthesis
    ontology: go
    organism: MED4
  expect:
    min_rows: 1
    contains:
      organism_strain: Prochlorococcus MED4

- id: find_genes_by_function_go_cross_organism
  tool: find_genes_by_function
  desc: "response to oxidative stress" spans Pro + Alt (238 genes, 13 orgs)
  params:
    search_text: response to oxidative stress
    ontology: go
  expect:
    min_rows: 10
    columns: [locus_tag, gene_name, product, organism_strain, matching_terms]
    # Should include both Prochlorococcus and Alteromonas genes

- id: find_genes_by_function_ec_partial_cross_organism
  tool: find_genes_by_function
  desc: "1.-.-.-" (oxidoreductases) spans Pro + Alt (229 genes, 13 orgs)
  params:
    search_text: "1.-.-.-"
    ontology: ec
  expect:
    min_rows: 10

- id: find_genes_by_function_kegg_cross_organism
  tool: find_genes_by_function
  desc: ABC transporter KO shared across Pro + Alt
  params:
    search_text: K06147
    ontology: kegg
  expect:
    min_rows: 5
```

### Regression snapshots (`tests/regression/`)

Add `find_genes_by_function` to `TOOL_BUILDERS` in
`tests/regression/test_regression.py`:

```python
from multiomics_explorer.kg.queries_lib import build_find_genes_by_function

TOOL_BUILDERS = {
    ...
    "find_genes_by_function": build_find_genes_by_function,
}
```

Generate baselines after implementation:
```bash
pytest tests/regression/ --force-regen -m kg
pytest tests/regression/ -m kg
```
