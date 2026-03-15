# Multiomics Explorer

Tools for exploring a Prochlorococcus/Alteromonas multi-omics knowledge graph. Provides an MCP server for Claude Code integration, a CLI, and a LangChain agent for natural language queries against Neo4j.

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
```

### MCP Server (Claude Code integration)

The MCP server exposes the KG to Claude Code with 10 specialized tools:
`get_schema`, `resolve_gene`, `search_genes`, `get_gene_details`, `query_expression`,
`compare_conditions`, `get_homologs`, `list_filter_values`, `list_organisms`, `run_cypher`.

To use with Claude Code, add to your `.claude/settings.json` (already configured in this repo):

```json
{
  "mcpServers": {
    "multiomics-kg": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/multiomics_explorer", "multiomics-kg-mcp"]
    }
  }
}
```

Then start Claude Code in any project directory — the KG tools will be available automatically.

### CLI

```bash
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

## Architecture

- **MCP Server** — Primary interface. Tools for Claude Code to query the KG.
- **CLI** — Typer-based terminal interface for direct exploration.
- **kg/** — Shared core: Neo4j connection, schema introspection, curated Cypher queries.

See [docs/architecture.md](docs/architecture.md) for the full technology stack, package structure, and data flow.

## Testing

```bash
# Unit tests (no Neo4j needed)
pytest tests/unit/ -v

# Integration tests (requires running Neo4j)
pytest -m kg -v
```

See [AGENT.md](AGENT.md) for detailed architecture and development instructions.
