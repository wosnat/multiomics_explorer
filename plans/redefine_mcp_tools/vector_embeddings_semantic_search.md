# Plan: Vector Embeddings + Semantic Search (Future)

Extracted from `find_gene_improvements.md`. High-impact future work that spans
both the KG build pipeline and the explorer.

## Motivation

Lexical fulltext search (`search_genes`) misses conceptual matches. A query like
"genes involved in protecting against oxidative damage" should match `sodB`,
`katG`, `ahpC` etc., but these genes don't all share the same keywords.

## KG-side: Embedding generation

Store a vector embedding per Gene node for semantic similarity search.

**What to embed:** `product + " " + function_description + " " + alternate_functional_descriptions`.
Deduplicate across sources first.

**Model:** `text-embedding-3-small` (OpenAI, 1536 dims). ~35K genes × ~200 tokens ≈ $0.50.
Quality gap over open-source models matters for scientific text.

**Neo4j setup:**
```cypher
CREATE VECTOR INDEX geneEmbedding FOR (g:Gene) ON (g.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}}
```

## Explorer-side: Semantic search tool

Either a `search_genes_semantic` tool or a `semantic: bool` flag on
`search_genes`. Best results come from hybrid search: Lucene for exact terms +
vector for concepts, re-ranked by `0.5 * lucene_score_norm + 0.5 * cosine_sim`.

## Open questions

- Embedding model choice: OpenAI vs open-source (e.g. `all-MiniLM-L6-v2`)
  tradeoff between cost, quality on scientific text, and dependency
- Hybrid vs standalone: separate tool keeps `search_genes` simple; flag on
  `search_genes` is more discoverable
- Re-ranking weights: need empirical tuning on representative queries
- Embedding refresh: how to keep embeddings in sync when KG is rebuilt
