# CLAUDE.md

## Project Overview

Tools for exploring a Prochlorococcus/Alteromonas multi-omics knowledge graph (Neo4j). Provides an MCP server for Claude Code, a CLI, and a LangChain agent.

The KG is built by the separate `multiomics_biocypher_kg` repo. This repo is **read-only** — it never writes to the graph.

## Build and Run

```bash
uv sync

# Validate Neo4j connection
uv run python scripts/validate_connection.py

# Start MCP server (standalone, for testing)
uv run multiomics-kg-mcp

# CLI
uv run multiomics-explorer stats
uv run multiomics-explorer schema
uv run multiomics-explorer cypher "MATCH (g:Gene) RETURN count(g)"

# Tests
pytest tests/unit/ -v          # no Neo4j needed
pytest -m kg -v                # requires Neo4j at localhost:7687
```

## MCP Server

The MCP server (`multiomics_explorer/mcp_server/`) is the primary interface for Claude Code.

### Tools

| Tool | Purpose |
|---|---|
| `get_schema` | Graph schema with node counts, relationships, properties |
| `resolve_gene` | Resolve a gene identifier to matching graph nodes. Returns locus_tags grouped by organism. |
| `find_gene` | Full-text search across gene annotations (Lucene syntax) |
| `search_genes` | Simple CONTAINS search by locus_tag, gene name, or product |
| `get_gene_details` | Full gene profile with protein, organism, cluster, homologs |
| `query_expression` | Expression data with filters (gene, organism, condition, direction, FC, p-value) |
| `compare_conditions` | Cross-condition or cross-strain expression comparison |
| `get_homologs` | Homologs across strains, optionally with expression data |
| `run_cypher` | Raw Cypher escape hatch (read-only, write operations blocked) |

### Claude Code Configuration

Already in `.claude/settings.json`. Update the `--directory` path if needed:

```json
{
  "mcpServers": {
    "multiomics-kg": {
      "command": "uv",
      "args": ["run", "--directory", "/home/osnat/github/multiomics_explorer", "multiomics-kg-mcp"]
    }
  }
}
```

## Neo4j Connection

- Default: `bolt://localhost:7687` (no auth)
- Configure via `.env`: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- KG deployed via Docker from `multiomics_biocypher_kg` repo

## Key Files

| File | Purpose |
|---|---|
| `multiomics_explorer/mcp_server/server.py` | MCP server entry point (FastMCP with Neo4j lifespan) |
| `multiomics_explorer/mcp_server/tools.py` | MCP tool implementations |
| `multiomics_explorer/kg/connection.py` | Neo4j driver wrapper (shared by MCP + CLI) |
| `multiomics_explorer/kg/schema.py` | Schema introspection from live KG |
| `multiomics_explorer/kg/queries.py` | Curated Cypher queries + few-shot examples |
| `multiomics_explorer/kg/queries_lib.py` | Query builder functions (parameterized Cypher) |
| `multiomics_explorer/config/settings.py` | Pydantic settings from .env |
| `multiomics_explorer/cli/main.py` | Typer CLI |
| `multiomics_explorer/agents/tools.py` | LangChain agent tools |
