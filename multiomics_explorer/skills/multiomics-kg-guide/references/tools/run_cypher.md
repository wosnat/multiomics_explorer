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

## Example

### Count genes per organism strain

```python
run_cypher(query="MATCH (g:Gene) RETURN g.organism_name AS strain, count(g) AS gene_count ORDER BY gene_count DESC")
```

## Response sketch

```expected-keys
returned, truncated, warnings, results
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

## Chaining patterns

- kg_schema → run_cypher (use schema to write correct queries)
- run_cypher → formalize into query builder once pattern is validated

Full reference (all examples, full response format, verbose fields): `docs://tools/run_cypher/full`
