# AGENT.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

LangChain-based reasoning agent for querying and analyzing the Prochlorococcus/Alteromonas multi-omics knowledge graph (Neo4j). Translates natural language questions into Cypher queries, executes them, and generates biologically grounded answers.

**This repo** (`multiomics_explorer`): Agent, CLI, evaluation framework
**KG builder repo** (`multiomics_biocypher_kg`): Builds the Neo4j graph (separate repo, no dependency)

## Build and Run Commands

```bash
# Install dependencies
uv sync

# Validate Neo4j connection
uv run python scripts/validate_connection.py

# CLI commands
uv run multiomics-explorer stats                    # KG statistics
uv run multiomics-explorer schema                   # Print graph schema
uv run multiomics-explorer schema --json             # Schema as JSON
uv run multiomics-explorer cypher "MATCH (g:Gene) RETURN count(g)"  # Direct Cypher
uv run multiomics-explorer query "What genes are upregulated in MED4?"  # NL query
uv run multiomics-explorer interactive               # REPL mode

# Export schema for LLM prompts
uv run python scripts/export_schema.py --format prompt

# Run unit tests (no Neo4j needed)
pytest tests/unit/ -v

# Run integration tests (requires Neo4j at localhost:7687)
pytest tests/ -v -m kg

# Run Streamlit UI (when implemented)
uv run streamlit run multiomics_explorer/ui/app.py
```

## Architecture

### MCP Server (primary interface)

The MCP server (`mcp_server/`) exposes the KG to Claude Code via 7 tools. Claude Code becomes the reasoning agent — no custom agentic pipeline needed.

```bash
# Start MCP server standalone (for testing)
uv run multiomics-kg-mcp

# Or configure Claude Code to auto-start it (see .claude/settings.json)
```

**Tools:**
| Tool | Purpose |
|---|---|
| `get_schema` | Graph schema with node counts, relationship types, properties |
| `search_genes` | Search by locus_tag, gene name, or product keyword |
| `get_gene_details` | Full gene profile: protein, organism, cluster, homologs |
| `query_expression` | Expression data with flexible filters (gene, organism, condition, direction, FC, p-value) |
| `compare_conditions` | Cross-condition or cross-strain expression comparison |
| `get_homologs` | Homologs across strains, optionally with expression data |
| `run_cypher` | Raw Cypher escape hatch (read-only) |

### Graph Foundation (shared library)

- Neo4j connection management (`kg/connection.py`)
- Schema introspection from live KG (`kg/schema.py`)
- Curated query library with validation queries (`kg/queries.py`)
- CLI for schema inspection and direct Cypher

### LangChain Agents (legacy/alternative)

**Stage 2: NL→Cypher Translation** (skeleton)
- `agents/cypher_agent.py` — GraphCypherQAChain with domain-specific prompts
- Few-shot examples in `config/prompts.yaml` and `kg/queries.py`
- Evaluation dataset: `evaluation_data/stage2_nl_cypher_pairs.yaml`

**Stage 3: Multi-hop Reasoning** (not started)
- `agents/reasoning_agent.py` — LangGraph state machine
- Superseded by MCP + Claude Code approach for interactive research

### LLM Configuration

Uses LangChain's built-in `init_chat_model` for provider-agnostic LLM access:

```python
from langchain.chat_models import init_chat_model

llm = init_chat_model(
    settings.model,                    # e.g., "claude-sonnet-4-5-20250929"
    model_provider=settings.model_provider,  # e.g., "anthropic"
    temperature=settings.model_temperature,
)
```

Configured via `.env`:
```
MODEL=claude-sonnet-4-5-20250929
MODEL_PROVIDER=anthropic
MODEL_TEMPERATURE=0
```

No custom LLM factory needed — `init_chat_model` handles OpenAI, Anthropic, Ollama, etc.

### Neo4j Connection

Connects to existing KG at `bolt://localhost:7687` (no auth). The KG is built and deployed by the separate `multiomics_biocypher_kg` repo via Docker. This agent is **read-only** — it never writes to the graph.

Schema is introspected live from Neo4j (no dependency on KG repo files).

## Knowledge Graph Schema

### Node Types (BioCypher PascalCase)

| Label | Count | Key Properties |
|---|---|---|
| `Gene` | ~16,400 | `locus_tag`, `product`, `function_description`, `go_biological_processes[]` |
| `Protein` | ~5,000 | `protein_name`, `function_description`, `amino_acid_sequence`, GO terms |
| `OrganismTaxon` | ~18 | `strain_name`, `genus`, `species`, `clade`, `ncbi_taxon_id` |
| `EnvironmentalCondition` | varies | `name`, `condition_type`, `nitrogen_level`, `light_condition`, etc. |
| `Publication` | ~19 | `title`, `doi`, `study_type` |
| `Cyanorak_cluster` | ~1,000 | `cluster_number` |
| `BiologicalProcess` | varies | `name` (GO term) |
| `MolecularFunction` | varies | `name` (GO term) |
| `CellularComponent` | varies | `name` (GO term) |
| `Pathway` | varies | `name`, `organism` |
| `EcNumber` | varies | `name` |
| `ProteinDomain` | varies | `name`, `type` |

### Key Relationship Types

| Relationship | Direction | Properties |
|---|---|---|
| `Gene_belongs_to_organism` | Gene → OrganismTaxon | — |
| `Protein_belongs_to_organism` | Protein → OrganismTaxon | — |
| `Gene_encodes_protein` | Protein → Gene | — |
| `Affects_expression_of` | (OrganismTaxon\|EnvironmentalCondition) → Gene | `log2_fold_change`, `adjusted_p_value`, `expression_direction`, `time_point`, `publications[]` |
| `Affects_expression_of_homolog` | same sources → Gene | same + `original_gene`, `distance`, `homology_cluster_id` |
| `Gene_is_homolog_of_gene` | Gene ↔ Gene (bidirectional) | `distance`, `cluster_id`, `source` |
| `Gene_in_cyanorak_cluster` | Gene → Cyanorak_cluster | — |
| `protein_involved_in_biological_process` | Protein → BiologicalProcess | `evidence_code` |
| `protein_enables_molecular_function` | Protein → MolecularFunction | `evidence_code` |
| `protein_take_part_in_pathway` | Protein → Pathway | — |
| `protein_has_domain` | Protein → ProteinDomain | — |
| `protein_catalyzes_ec_number` | Protein → EcNumber | — |

### Node ID Conventions

- Gene: `ncbigene:<locus_tag>` (e.g., `ncbigene:PMM0001`)
- Protein: `uniprot:<accession>`
- Organism (genomic): `insdc.gcf:<accession>` (e.g., `insdc.gcf:GCF_000011465.1`)
- Organism (treatment): `ncbitaxon:<taxid>`
- GO terms: `go:<GO:XXXXXXX>`
- Publications: DOI string

### Organisms in the Graph

**Prochlorococcus** (8 strains):
| Strain | Clade | Locus Prefix |
|---|---|---|
| MED4 | HLI | PMM |
| MIT9312 | HLII | PMT9312_ |
| AS9601 | HLII | A9601_ |
| MIT9301 | HLII | P9301_ |
| NATL1A | LLI | NATL1_ |
| NATL2A | LLII | PMN2A_ |
| MIT9313 | LLIV | PMT9313_RS |
| RSP50 | — | — |

**Synechococcus/Parasynechococcus** (2): CC9311 (sync_), WH8102 (SYNW)
**Alteromonas** (3): MIT1002 (AKG35_RS), EZ55 (ALTBGP6_RS), HOT1A3

**Treatment organisms** (coculture sources, not genomic): Phage, Marinobacter, Thalassospira, Pseudohoeflea, Alteromonas (genus-level)

## Common Pitfalls

1. **Gene_encodes_protein direction**: Protein → Gene. To go Gene → Protein, use `(g)<-[:Gene_encodes_protein]-(p)`.

2. **Homology is bidirectional**: Always use undirected pattern `(g)-[:Gene_is_homolog_of_gene]-(h)`, never `(g)->`.

3. **Organism filtering**: Use `strain_name` for specific strains (e.g., `'MED4'`), `genus` for genus-level (e.g., `'Alteromonas'`). Do NOT use `organism_name` (inconsistent format).

4. **Denormalized gene properties**: `function_description` and `go_biological_processes` are copied from Protein onto Gene during post-import. No need to traverse Gene→Protein for these.

5. **Cyanorak clusters**: Only Prochlorococcus/Synechococcus genes have Cyanorak cluster membership. Alteromonas genes do not.

6. **adjusted_p_value can be null**: Some studies don't report adjusted p-values. Always use `IS NOT NULL` when filtering.

7. **Expression edge sources**: Coculture experiments → source is `OrganismTaxon`. Stress experiments → source is `EnvironmentalCondition`. Both use the same `Affects_expression_of` edge label.

8. **Always LIMIT**: When generating Cypher, include `LIMIT` unless doing aggregation. Use `ORDER BY` before `LIMIT`.

## Configuration

All config via `.env` (copy from `.env.example`):
- `NEO4J_URI` — Bolt URL (default: `bolt://localhost:7687`)
- `MODEL` / `MODEL_PROVIDER` — LLM model and provider
- `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — API keys
- `KG_REPO_PATH` — Optional path to KG builder repo for richer metadata

## Testing

- `pytest tests/unit/` — Unit tests (no external dependencies)
- `pytest -m kg` — Integration tests (require running Neo4j)
- `pytest -m eval` — Evaluation tests (require LLM API, slow)

Tests auto-skip if Neo4j is unreachable.

## Key Files

| File | Purpose |
|---|---|
| `config/settings.py` | Pydantic settings from .env |
| `config/prompts.yaml` | LLM system prompts + few-shot examples |
| `kg/connection.py` | Neo4j driver wrapper |
| `kg/schema.py` | Schema introspection from live KG |
| `kg/queries.py` | Curated Cypher queries + few-shot examples |
| `agents/cypher_agent.py` | NL→Cypher agent (Stage 2) |
| `agents/reasoning_agent.py` | Multi-hop reasoning (Stage 3, TODO) |
| `mcp_server/server.py` | MCP server entry point (FastMCP) |
| `mcp_server/tools.py` | 7 MCP tool implementations |
| `cli/main.py` | Typer CLI |
| `evaluation_data/*.yaml` | Test cases for each stage |
