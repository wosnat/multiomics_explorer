# Convention: Standard Gene Stub

Whenever an MCP tool returns a list of genes, use this base set of fields:

```
locus_tag, gene_name, product, organism_strain
```

Tools may add context-specific fields on top (e.g. `score`, `annotation_quality`,
`function_description`), but the stub is always present.

## Shared query builder

`build_gene_stub(gene_id)` in `queries_lib.py` returns the stub for a
single gene by locus_tag:

```cypher
MATCH (g:Gene {locus_tag: $lt})
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.organism_strain AS organism_strain
```

Used by `get_homologs` (for `query_gene` metadata) and available to any
tool that needs a quick gene lookup.

## Current alignment

| Tool | Has stub? | Extra fields |
|---|---|---|
| `resolve_gene` | yes | — |
| `search_genes` | yes | `function_description`, `gene_summary`, `annotation_quality`, `score` |
| `genes_by_ontology` | yes | — |
| `get_homologs` members | **no** — missing `gene_name` | — |
| `get_gene_details` | n/a (single gene, full profile) | — |
| `query_expression` | n/a (expression rows, not gene lists) | — |

## Changes needed

- `get_homologs` members query: add `gene_name` to match the stub.

## Why

- LLM consumers build a mental model: "a gene always has these 4 fields."
  Consistent shape means no per-tool special-casing.
- Simplifies downstream formatting — one helper can render any gene list.
- Cost is minimal: `gene_name` is null ~46% of the time, but null values
  are cheap and predictable.
