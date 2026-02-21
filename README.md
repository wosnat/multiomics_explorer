# Multiomics Explorer

LangChain-based agent for reasoning over a Prochlorococcus/Alteromonas multi-omics knowledge graph. Translates natural language questions into Cypher queries, executes them against a Neo4j database, and generates biologically grounded answers.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Running Neo4j instance with the multi-omics KG (built by [multiomics_biocypher_kg](https://github.com/wosnat/multiomics_biocypher_kg))
- API key for your LLM provider (Anthropic, OpenAI, etc.)

## Quick Start

```bash
# Clone and install
git clone <repo-url>
cd multiomics_explorer
cp .env.example .env
# Edit .env with your API key and Neo4j settings

uv sync

# Verify Neo4j connection
uv run python scripts/validate_connection.py

# Explore the graph
uv run multiomics-explorer stats
uv run multiomics-explorer schema

# Run a direct Cypher query
uv run multiomics-explorer cypher "MATCH (g:Gene)-[:Gene_belongs_to_organism]->(o:OrganismTaxon) WHERE o.strain_name = 'MED4' RETURN count(g)"

# Ask a natural language question
uv run multiomics-explorer query "What genes are upregulated in MED4 during coculture with Alteromonas?"

# Interactive mode
uv run multiomics-explorer interactive
```

## Knowledge Graph

The agent queries a Neo4j knowledge graph containing:
- **16,000+ genes** across 13 organisms (Prochlorococcus, Synechococcus, Alteromonas)
- **110,000+ expression edges** from 19 differential expression studies
- Protein annotations, GO terms, pathways, homology relationships
- Expression data from coculture experiments and environmental stress studies

## Development Stages

1. **Graph Foundation** (done) — Neo4j connection, schema introspection, curated queries, CLI
2. **NL→Cypher Translation** (in progress) — LangChain GraphCypherQAChain, evaluation framework
3. **Multi-hop Reasoning** (planned) — LangGraph agents, tool calling, LLM-as-judge evaluation

## Testing

```bash
# Unit tests (no Neo4j needed)
pytest tests/unit/ -v

# Integration tests (requires running Neo4j)
pytest -m kg -v
```

See [AGENT.md](AGENT.md) for detailed architecture and development instructions.
