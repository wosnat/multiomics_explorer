# CLAUDE.md

## Project Overview

Tools for exploring a Prochlorococcus/Alteromonas multi-omics knowledge graph (Neo4j). Provides an MCP server for Claude Code and a CLI.

The KG is built by the separate `multiomics_biocypher_kg` repo. This repo is **read-only** — it never writes to the graph.

**Expression schema:** The KG uses `Experiment` nodes with `Changes_expression_of` edges to Gene. Expression query tools (`query_expression`, `compare_conditions`) have been removed and are being rebuilt with the new schema. Use `run_cypher` for expression queries in the meantime — see few-shot examples in `kg/queries.py`.

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
| `resolve_gene` | Resolve a gene identifier (case-insensitive) to matching graph nodes. Returns flat list sorted by organism. |
| `search_genes` | Free-text search across gene functional annotations (Lucene syntax). Supports category filtering and ortholog deduplication. |
| `get_gene_details` | All Gene node properties via g{.*} — use gene_overview for the common case |
| `gene_overview` | Batch gene routing: identity + data availability signals (annotation_types, expression counts, ortholog summary). Accepts gene_ids list. |
| `gene_homologs` | Batch: gene locus_tags → ortholog group memberships. Flat long format (one row per gene × group). Filterable by source/level/rank. |
| `list_filter_values` | List valid values for categorical filters (gene categories) |
| `list_organisms` | All organisms with taxonomy, gene/publication/experiment counts, treatment and omics types. Verbose adds full taxonomy hierarchy. |
| `list_publications` | Publications with experiment summaries, filterable by organism/treatment/search/author |
| `list_experiments` | Experiments with gene count stats. Use `summary=true` for breakdowns by organism/treatment/omics, default returns individual experiments. Filterable by organism/treatment/omics/publication/search. |
| `search_ontology` | Browse ontology terms by text search (GO, KEGG, EC). Returns term IDs for use with `genes_by_ontology`. |
| `genes_by_ontology` | Find genes annotated to ontology term IDs, with hierarchy expansion. Results grouped by organism. |
| `gene_ontology_terms` | Reverse lookup: get ontology annotations for a gene. Returns leaf (most specific) terms by default. |
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
| `multiomics_explorer/api/functions.py` | Public Python API — wraps query builders + execute |
| `multiomics_explorer/config/settings.py` | Pydantic settings from .env |
| `multiomics_explorer/cli/main.py` | Typer CLI |
