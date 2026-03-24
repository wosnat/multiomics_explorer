# run_cypher

## What it does

Execute a raw Cypher query against the knowledge graph (read-only).

Use this as an escape hatch when other tools don't cover your query.
Write operations are blocked. Queries are validated for syntax and schema
correctness before execution — warnings are returned in the response.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| query | string | — | Cypher query string. Write operations are blocked. A LIMIT clause is added automatically if absent. |
| limit | int | 25 | Max results (default 25, max 200). |

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
run_cypher(query="MATCH (g:Gene) RETURN g.organism_strain AS strain, count(g) AS gene_count ORDER BY gene_count DESC")
```

```example-response
{
  "returned": 12,
  "truncated": false,
  "warnings": [],
  "results": [
    {"strain": "Alteromonas macleodii EZ55", "gene_count": 4136},
    {"strain": "Alteromonas macleodii HOT1A3", "gene_count": 4031}
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
    "One of the relationship types in your query is not available in the database (the missing relationship type is: HAS_FUNCTION)"
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

- Package import returns all four keys: returned, truncated, warnings, results. The build-script comment only shows a subset.

## Package import equivalent

```python
from multiomics_explorer import run_cypher

result = run_cypher(query=...)
# returns dict with keys: warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
