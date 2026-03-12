# Architecture

## Overview

Multiomics Explorer provides read-only API access to a Prochlorococcus/Alteromonas multi-omics knowledge graph stored in Neo4j. The two primary interfaces are a **CLI** and an **MCP server** for Claude Code.

```
┌─────────────┐   ┌─────────────┐
│  Claude Code │   │   Terminal  │
│  (MCP client)│   │   (human)   │
└──────┬───────┘   └──────┬──────┘
       │                  │
       ▼                  ▼
┌─────────────┐   ┌─────────────┐
│  MCP Server │   │     CLI     │
│  (FastMCP)  │   │   (Typer)   │
└──────┬───────┘   └──────┬──────┘
       │                  │
       ▼                  ▼
┌─────────────────────────────────┐
│         kg/ (core layer)        │
│  connection · schema · queries  │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│        Neo4j (read-only)        │
│   built by multiomics_biocypher │
└─────────────────────────────────┘
```

## Technology Stack

| Layer | Tool | Notes |
|---|---|---|
| **Graph database** | [Neo4j](https://neo4j.com/) ≥5.0 | Industry-leading graph DB. Accessed via the official `neo4j` Python driver. |
| **KG construction** | [BioCypher](https://biocypher.org/) | Biomedical KG builder (separate repo `multiomics_biocypher_kg`). |
| **MCP server** | [FastMCP](https://github.com/modelcontextprotocol/python-sdk) (`mcp[cli]`) | Official Model Context Protocol SDK from Anthropic. |
| **CLI** | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) | Modern Python CLI framework with rich terminal output. |
| **Configuration** | [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) + python-dotenv | Type-safe settings from `.env` / environment variables. |
| **Package manager** | [uv](https://docs.astral.sh/uv/) | Fast Python package manager. Build backend: hatchling. |
| **Linting** | [Ruff](https://docs.astral.sh/ruff/) | Fast Python linter and formatter. |
| **Testing** | [Pytest](https://docs.pytest.org/) | With markers for unit (`tests/unit/`) and integration (`-m kg`). |

### Additional dependencies (not yet active)

These are installed but not part of the current CLI/MCP workflow:

| Dependency | Intended use |
|---|---|
| LangChain / LangGraph / langchain-neo4j | NL→Cypher agent (skeleton in `agents/`). Superseded by MCP approach for interactive use. |
| langchain-openai / langchain-anthropic | LLM providers for the LangChain agent. |
| RAGAS | Evaluation framework for future agent accuracy benchmarking. |
| Streamlit / Pandas / Plotly | Web UI (skeleton in `ui/`). |

## Package Structure

```
multiomics_explorer/
├── kg/                  # Core layer — shared by all interfaces
│   ├── connection.py    #   Neo4j driver wrapper
│   ├── schema.py        #   Schema introspection from live KG
│   └── queries.py       #   Curated Cypher queries + few-shot examples
├── mcp_server/          # MCP server for Claude Code
│   ├── server.py        #   FastMCP entry point with Neo4j lifespan
│   └── tools.py         #   Tool implementations
├── cli/                 # Typer CLI
│   └── main.py
├── config/              # Settings and prompt templates
│   ├── settings.py      #   Pydantic Settings from .env
│   └── prompts.yaml
├── agents/              # LangChain agent (skeleton, not active)
├── api/                 # API client (skeleton, not active)
├── ui/                  # Streamlit UI (skeleton, not active)
└── evaluation/          # RAGAS evaluation (skeleton, not active)
```

## Data Flow

1. **Neo4j** hosts the knowledge graph (built externally by BioCypher). This repo never writes to it.
2. **`kg/`** provides the shared data-access layer: driver management, schema introspection, and parameterized Cypher queries.
3. **CLI** (`typer`) and **MCP server** (`FastMCP`) both call into `kg/` to serve user or Claude requests.
4. Results are returned as structured text (CLI) or JSON (MCP) — no ORM or object mapping layer.
