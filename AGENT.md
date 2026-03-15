# AGENT.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

Tools for querying and analyzing the Prochlorococcus/Alteromonas multi-omics knowledge graph (Neo4j). Provides an MCP server for Claude Code, a CLI, and a LangChain agent.

**This repo** (`multiomics_explorer`): MCP server, CLI, agent, evaluation framework
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

# Start MCP server standalone (for testing)
uv run multiomics-kg-mcp
```

## Architecture

### MCP Server (primary interface)

The MCP server (`mcp_server/`) exposes the KG to Claude Code via tools. Claude Code becomes the reasoning agent — no custom agentic pipeline needed.

**Tools:**
| Tool | Purpose |
|---|---|
| `get_schema` | Graph schema with node counts, relationship types, properties |
| `resolve_gene` | Resolve a gene identifier to matching graph nodes. Returns locus_tags grouped by organism. |
| `search_genes` | Free-text search across gene functional annotations (Lucene syntax). Supports category filtering and ortholog deduplication. |
| `get_gene_details` | Full gene profile: protein, organism, cluster, homologs |
| `query_expression` | Expression data with flexible filters (gene, organism, condition, direction, FC, p-value) |
| `compare_conditions` | Cross-condition or cross-strain expression comparison |
| `get_homologs` | Homologs across strains, optionally with expression data |
| `list_filter_values` | List valid values for categorical filters (gene categories, condition types) |
| `list_organisms` | All organisms with strain, genus, clade, gene count |
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

Uses LangChain's built-in `init_chat_model` for provider-agnostic LLM access.

Configured via `.env`:
```
MODEL=claude-sonnet-4-5-20250929
MODEL_PROVIDER=anthropic
MODEL_TEMPERATURE=0
```

### Neo4j Connection

Connects to existing KG at `bolt://localhost:7687` (no auth). The KG is built and deployed by the separate `multiomics_biocypher_kg` repo via Docker. This agent is **read-only** — it never writes to the graph.

Schema is introspected live from Neo4j (no dependency on KG repo files).

## Knowledge Graph Schema

### Node Types (BioCypher PascalCase)

| Label | Count | Key Properties |
|---|---|---|
| `Gene` | ~35,200 | `locus_tag`, `gene_name`, `product`, `function_description`, `gene_summary`, `organism_strain`, `annotation_quality` (0-3), `go_terms[]`, `kegg_ko[]`, `cog_category[]`, `all_identifiers[]` |
| `Protein` | ~26,600 | `gene_names[]`, `is_reviewed` ('reviewed'/'not reviewed'), `annotation_score`, `sequence_length`, `refseq_ids[]` |
| `OrganismTaxon` | 18 | `preferred_name` (e.g. 'Prochlorococcus MED4'), `strain_name`, `genus`, `species`, `clade`, `ncbi_taxon_id`, `organism_name` |
| `EnvironmentalCondition` | ~57 | `name`, `condition_type`, `condition_category`, `description`, `temperature`, `light_condition` |
| `Publication` | ~21 | `title`, `doi`, `study_type`, `publication_year` |
| `Cyanorak_cluster` | ~5,600 | `cluster_number` |
| `BiologicalProcess` | ~2,400 | `name` (GO term) |
| `MolecularFunction` | ~9,400 | `name` (GO term) |
| `CellularComponent` | ~330 | `name` (GO term) |
| `KeggOrthologousGroup` | ~2,700 | `name` |
| `KeggPathway` | ~285 | `name` |
| `EcNumber` | ~7,300 | `name`, `catalytic_activity[]` |
| `CogFunctionalCategory` | 26 | `code`, `name` |
| `CyanorakRole` | ~170 | `code`, `description` |
| `TigrRole` | ~114 | `code`, `description` |

### Key Relationship Types

| Relationship | Direction | Properties |
|---|---|---|
| `Gene_belongs_to_organism` | Gene → OrganismTaxon | — |
| `Protein_belongs_to_organism` | Protein → OrganismTaxon | — |
| `Gene_encodes_protein` | Gene → Protein | — |
| `Coculture_changes_expression_of` | OrganismTaxon → Gene | `log2_fold_change`, `adjusted_p_value`, `expression_direction`, `organism_strain` (preferred_name format), `time_point`, `publications[]`, `significant` ('significant'/'not significant'/'unknown'), `control_condition`, `treatment_condition`, `experimental_context`, `omics_type`, `statistical_test`, `analysis_name` |
| `Condition_changes_expression_of` | EnvironmentalCondition → Gene | same as above |
| `Coculture_changes_expression_of_ortholog` | OrganismTaxon → Gene | same + `original_gene`, `homology_source`, `homology_cluster_id`, `distance` |
| `Condition_changes_expression_of_ortholog` | EnvironmentalCondition → Gene | same + `original_gene`, `homology_source`, `homology_cluster_id`, `distance` |
| `Published_expression_data_about` | Publication → EnvironmentalCondition/OrganismTaxon | — |
| `Gene_is_homolog_of_gene` | Gene ↔ Gene (bidirectional) | `distance`, `cluster_id`, `source` |
| `Gene_in_cyanorak_cluster` | Gene → Cyanorak_cluster | — |
| `Gene_involved_in_biological_process` | Gene → BiologicalProcess | — |
| `Gene_enables_molecular_function` | Gene → MolecularFunction | — |
| `Gene_located_in_cellular_component` | Gene → CellularComponent | — |
| `Gene_has_kegg_ko` | Gene → KeggOrthologousGroup | — |
| `Ko_in_kegg_pathway` | KeggOrthologousGroup → KeggPathway | — |
| `Gene_catalyzes_ec_number` | Gene → EcNumber | — |
| `Gene_in_cog_category` | Gene → CogFunctionalCategory | — |
| `Gene_has_cyanorak_role` | Gene → CyanorakRole | — |
| `Gene_has_tigr_role` | Gene → TigrRole | — |

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
| RSP50 | HLI | — |
| MIT9312 | HLII | PMT9312_ |
| MIT9301 | HLII | P9301_ |
| AS9601 | HLII | A9601_ |
| NATL1A | LLII | NATL1_ |
| NATL2A | LLII | PMN2A_ |
| MIT9313 | LLIV | PMT9313_RS |

**Synechococcus/Parasynechococcus** (2): CC9311 (sync_), WH8102 (SYNW)
**Alteromonas** (3): MIT1002 (AKG35_RS), EZ55 (ALTBGP6_RS), HOT1A3 (ACZ81_)

**Treatment organisms** (coculture sources, not genomic): Alteromonas, Phage, Marinobacter, Thalassospira, Pseudohoeflea

### Environmental Condition Types

| `condition_type` | Description |
|---|---|
| `growth_medium` | Baseline growth conditions (control) |
| `light_stress` | Light/dark shifts, high-light stress |
| `gas_shock` | CO₂/O₂ perturbations |
| `nutrient_stress` | Nitrogen, iron, phosphate limitation |
| `growth_state` | Stationary vs exponential phase |
| `salt_stress` | Salinity changes |
| `iron_stress` | Iron limitation/addition |
| `pco2` | pCO₂ level experiments |
| `dark_tolerance` | Extended darkness survival |
| `viral_lysis_products` | Viral lysate exposure |
| `plastic_leachate_stress` | Plastic leachate exposure |
| `coculture` | Coculture conditions |

## Common Pitfalls

1. **Gene_encodes_protein direction**: Gene → Protein. Use `(g)-[:Gene_encodes_protein]->(p)`.

2. **Homology is bidirectional**: Always use undirected pattern `(g)-[:Gene_is_homolog_of_gene]-(h)`, never `(g)->`.

3. **Organism filtering**: Use `strain_name` for genome strains (e.g., `'MED4'`), `genus` for genus-level. Treatment organisms use `organism_name` (e.g., `'Alteromonas'`, `'Phage'`).

4. **Expression edges are split by source type**:
   - `Coculture_changes_expression_of` — source is OrganismTaxon
   - `Condition_changes_expression_of` — source is EnvironmentalCondition
   - To query both: use `|` syntax: `[r:Condition_changes_expression_of|Coculture_changes_expression_of]`
   - Target organism is on the edge as `r.organism_strain`, not via a separate MATCH

5. **EnvironmentalCondition filtering**: Use `condition_type` (e.g., `'nutrient_stress'`) and `description CONTAINS` for specific stressors. There are NO `nitrogen_level` or `phosphate_level` properties.

6. **Gene annotations are gene-centric**: GO, KEGG, COG relationships are on Gene nodes (not Protein): `Gene_involved_in_biological_process`, `Gene_has_kegg_ko`, `Gene_in_cog_category`, etc.

7. **Denormalized gene properties**: `gene_name`, `product`, `organism_strain`, `gene_summary`, `go_terms[]`, `kegg_ko[]` are directly on Gene nodes. No need to traverse relationships for basic info.

8. **Cyanorak clusters**: Only Prochlorococcus/Synechococcus genes have Cyanorak cluster membership. Alteromonas genes do not.

9. **adjusted_p_value can be null**: Some studies don't report adjusted p-values. Always use `IS NOT NULL` when filtering.

10. **Publication DOIs**: In `r.publications` arrays, DOIs are bare (e.g., `10.1038/...`), not prefixed with `doi:`.

11. **Always LIMIT**: When generating Cypher, include `LIMIT` unless doing aggregation. Use `ORDER BY` before `LIMIT`.

## Configuration

All config via `.env`:
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
| `mcp_server/tools.py` | MCP tool implementations |
| `cli/main.py` | Typer CLI |
| `evaluation_data/*.yaml` | Test cases for each stage |
