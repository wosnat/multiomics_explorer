# Multiomics Explorer

Tools for exploring a Prochlorococcus/Alteromonas multi-omics knowledge graph. Provides an MCP server for Claude Code and a Python package for scripting against the same Neo4j graph.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Running Neo4j instance with the multi-omics KG (built by [multiomics_biocypher_kg](https://github.com/wosnat/multiomics_biocypher_kg))

## Quick Start

```bash
# Clone and install
git clone <repo-url>
cd multiomics_explorer
cp .env.example .env
# Edit .env with your Neo4j settings

uv sync

# Verify the Neo4j connection
uv run python scripts/validate_connection.py
```

### MCP Server (Claude Code integration)

The MCP server exposes the KG to Claude Code through 42 typed tools (gene identity, expression, orthology, ontologies, clustering, derived metrics, chemistry, metabolomics, enrichment, literature index, plus a read-only Cypher escape hatch). The full table is in [CLAUDE.md](CLAUDE.md); per-tool docs are served as `docs://tools/{name}` and a routing guide as `docs://guide/start_here`.

To use with Claude Code, add to your `.claude/settings.json`:

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

### Python package

Every MCP tool is also an ordinary function under the `multiomics_explorer` namespace, unpaginated by default:

```python
from multiomics_explorer import gene_overview, differential_expression_by_gene, to_dataframe

overview = gene_overview(locus_tags=["PMM0370"])
df = to_dataframe(differential_expression_by_gene(organism="MED4", locus_tags=["PMM0370"]))
```

For ad-hoc Cypher from a script, use the shared connection wrapper (read-only by convention — this repo never writes to the graph):

```python
from multiomics_explorer.kg.connection import GraphConnection
GraphConnection().execute_query("MATCH (g:Gene) RETURN count(g) AS n")
```

See `docs://guide/python_api` (served by the MCP server; source at `multiomics_explorer/skills/multiomics-kg-guide/references/guide/python_api.md`) for import topology, return shapes, DataFrame conversion and worked recipes.

## Knowledge Graph

The Neo4j knowledge graph integrates, for Prochlorococcus, Synechococcus, Alteromonas and their co-culture partners:

- Genomes (protein-coding genes with sequences and coordinates), ortholog groups, and 17 functional / structural ontologies with an annotation-trust surface
- Differential expression from RNAseq, microarray and proteomics studies, plus published co-expression clusterings and derived per-gene metrics
- A chemistry layer (KEGG reactions, TCDB transport substrates) and a metabolomics measurement layer
- A recall-biased literature index of the genes and pathways each paper discusses

Call `kg_release_info` for the live counts and release identity.

## Architecture

- **MCP Server** — Primary interface. Tools for Claude Code to query the KG.
- **api/** — Public Python functions (same names as the tools) wrapping the query builders.
- **kg/** — Shared core: Neo4j connection, schema introspection, parameterized Cypher builders.

See [docs/architecture.md](docs/architecture.md) for the full technology stack, package structure, and data flow.

## Testing

```bash
# Unit tests (no Neo4j needed)
pytest tests/unit/ -v

# Integration tests (requires running Neo4j)
pytest -m kg -v
```

See [AGENT.md](AGENT.md) for detailed architecture and development instructions.
