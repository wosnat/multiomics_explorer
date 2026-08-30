# run_cypher

## What it does

Read-only Cypher escape hatch — writes are blocked, syntax and schema validated before execution.

Use only when no tool covers the question; read the shape first with `kg_schema(labels=[...])`.
Filters: query, limit.
Returns: returned, truncated, warnings (non-blocking) and results as raw column dicts; there is no total_matching.
docs://tools/run_cypher.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| query | string | — | Cypher query string. Write operations are blocked. A LIMIT clause is added automatically if absent. |
| limit | int | 25 | Max rows returned (paging). |

## Response format

### Envelope

```expected-keys
returned, truncated, warnings, results
```

- **returned** (int): Number of rows returned (e.g. 12)
- **truncated** (bool): True when returned == limit (more rows may exist)
- **warnings** (list[string]): Schema or property warnings from CyVer (non-blocking). Empty list means query is fully valid against the current KG schema.

## Few-shot examples

### Example 1: Count genes per organism strain

```example-call
run_cypher(query="MATCH (g:Gene) RETURN g.organism_name AS strain, count(g) AS gene_count ORDER BY gene_count DESC")
```

```example-response
{
  "returned": 25,
  "truncated": true,
  "warnings": [],
  "results": [
    {"strain": "Pseudomonas putida KT2440", "gene_count": 5487},
    {"strain": "Ruegeria pomeroyi DSS-3", "gene_count": 4368},
    {"strain": "Alteromonas (MarRef v6)", "gene_count": 4305},
    ...
  ]
}
```

### Example 2: Explore experiment schema

```example-call
run_cypher(query="MATCH (e:Experiment) RETURN keys(e) AS props LIMIT 1")
```

### Example 3: Query with schema warning

```example-call
run_cypher(query="MATCH (g:Gene)-[:HAS_FUNCTION]->(f:Function) RETURN g.locus_tag LIMIT 5")
```

```example-response
{
  "returned": 0,
  "truncated": false,
  "warnings": [
    "One of the labels in your query is not available in the database, make sure you didn't misspell it or that the label ...",
    "One of the relationship types in your query is not available in the database, make sure you didn't misspell it or tha..."
  ],
  "results": []
}
```

## Chaining patterns

```
kg_schema → run_cypher (use schema to write correct queries)
run_cypher → formalize into query builder once pattern is validated
```

## Common mistakes

- Warnings are non-blocking — the query still executes. Check warnings before trusting empty results.

```mistake
run_cypher(query='MATCH (g:Gene) WHERE g.locus_tag = $tag RETURN g', params={'tag': 'PMM0001'})
```

```correction
run_cypher(query="MATCH (g:Gene) WHERE g.locus_tag = 'PMM0001' RETURN g")
```

- No LIMIT in query? One is added automatically at the MCP default (25). Pass limit= to increase or add LIMIT directly in your query.

- Package import returns all four keys: returned, truncated, warnings, results.

- Reserved characters were replaced at KG build time, so string literals must match the stored form: an apostrophe is stored as a caret (`^`) and a pipe as a comma. `WHERE g.product CONTAINS "5'-nucleotidase"` matches nothing — write `CONTAINS '5^-nucleotidase'`. The same applies to search_text on the fulltext tools — search on the surrounding words instead (see docs://guide/conventions).

- Organism names in Cypher must be the exact `preferred_name` / `Gene.organism_name` string ('Prochlorococcus MED4', not 'MED4') — the word-based matching that the MCP tools do on `organism=` is not applied to raw queries. Note that 'Meiothermus ruber' names two OrganismTaxon nodes; join organisms through Gene_belongs_to_organism, never by name.

## Package import equivalent

```python
from multiomics_explorer import run_cypher

result = run_cypher(query=...)
# returns dict with keys: returned, truncated, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
