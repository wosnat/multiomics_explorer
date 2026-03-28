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

The MCP server exposes the KG to Claude Code with specialized tools. See tool tracker below for the full list.

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

## Tool Tracker

### Done

| Tool | Domain | Purpose |
|---|---|---|
| `kg_schema` | Schema | Graph schema: node labels, relationship types, properties |
| `run_cypher` | Schema | Raw Cypher escape hatch (read-only, validated) |
| `resolve_gene` | Gene | Resolve gene identifier to graph nodes (case-insensitive) |
| `get_gene_details` | Gene | All Gene node properties |
| `gene_overview` | Gene | Batch gene routing: identity + data availability signals |
| `genes_by_function` | Gene | Free-text search across functional annotations (Lucene) |
| `list_filter_values` | Gene | Valid values for categorical filters |
| `list_organisms` | Organism | All organisms with taxonomy and counts |
| `list_publications` | Publication | Publications with experiment summaries, filterable |
| `list_experiments` | Experiment | Experiments with gene count stats, summary mode |
| `search_ontology` | Ontology | Browse ontology terms by text (GO, KEGG, EC, COG, etc.) |
| `genes_by_ontology` | Ontology | Term IDs → genes, with hierarchy expansion |
| `gene_ontology_terms` | Ontology | Genes → ontology annotations (reverse lookup, batch) |
| `gene_homologs` | Ortholog | Gene locus_tags → ortholog group memberships |
| `search_homolog_groups` | Ortholog | Search ortholog groups by text (Lucene) |
| `genes_by_homolog_group` | Ortholog | Group IDs → member genes per organism |
| `differential_expression_by_gene` | Expression | Gene-centric DE: gene × experiment × timepoint |
| `differential_expression_by_ortholog` | Expression | Cross-organism DE framed by ortholog groups |

### Todo

| Tool | Domain | Purpose | Notes |
|---|---|---|---|
| `homologs_by_ontology` | Ortholog × Ontology | Ortholog groups annotated to ontology terms — functional enrichment view for gene sets | Bridges OG↔ontology; enrichment-style analysis |
| `ontology_subgraph` | Ontology | Navigate ontology hierarchies: expand to roots, list children, sub-categories | Uses is_a / part_of / regulates edges |

### Needs Exploration

| Idea | Domain | Notes |
|---|---|---|
| Genomic neighbors | Gene | Genes near gene X (operon/synteny). Needs: are start/end/strand populated consistently? |
| Coculture exposure | Experiment | `Tests_coculture_with` edges. Could be a filter on `list_experiments` rather than a new tool |

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
