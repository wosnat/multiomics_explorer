# CLAUDE.md

## Project Overview

Tools for exploring a Prochlorococcus/Alteromonas multi-omics knowledge graph (Neo4j). Provides an MCP server for Claude Code and a CLI.

The KG is built by the separate `multiomics_biocypher_kg` repo. This repo is **read-only** — it never writes to the graph.

**Expression schema:** The KG uses `Experiment` nodes with `Changes_expression_of` edges to Gene. `Experiment.treatment_type` is an array (`str[]`), and `background_factors` (`str[]`, may be null) describes experimental context. Use `'value' IN e.treatment_type` for filtering and `coalesce(e.background_factors, [])` for null safety. See few-shot examples in `kg/queries.py`.

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
| `kg_schema` | Graph schema with node labels, relationship types, property names |
| `resolve_gene` | Resolve a gene identifier (case-insensitive) to matching graph nodes. Returns flat list sorted by organism. |
| `genes_by_function` | Free-text search across gene functional annotations (Lucene syntax). Rich summary fields (by_organism, by_category, score stats). Supports category and organism filtering. |
| `gene_details` | All Gene node properties via g{.*} — use gene_overview for the common case |
| `gene_overview` | Batch gene routing: identity + data availability signals (annotation_types, expression counts, ortholog summary, cluster membership). Accepts locus_tags list. Rich summary fields (by_organism, by_category, by_annotation_type, expression/ortholog/cluster availability counts). |
| `gene_homologs` | Batch: gene locus_tags → ortholog group memberships. Flat long format (one row per gene × group). Filterable by source/level/rank. |
| `list_filter_values` | List valid values for categorical filters (gene categories) |
| `list_organisms` | All organisms with taxonomy, gene/publication/experiment counts, treatment types, background factors, omics types. Verbose adds full taxonomy hierarchy. |
| `list_publications` | Publications with experiment summaries, filterable by organism/treatment/background_factors/search/author |
| `list_experiments` | Experiments with gene count stats. Use `summary=true` for breakdowns by organism/treatment/background_factors/omics/table_scope, default returns individual experiments. Filterable by organism/treatment/background_factors/omics/publication/search/table_scope. |
| `ontology_landscape` | Rank (ontology × level) combinations for enrichment. Per-level term-size distribution, genome coverage, best-effort share (GO), optional experiment-weighted coverage. Default surveys all 9 ontologies. |
| `search_ontology` | Browse ontology terms by text search (GO, KEGG, EC, COG, Cyanorak, TIGR, Pfam). Summary fields: total_entries, score stats. Returns term IDs for use with `genes_by_ontology`. |
| `search_homolog_groups` | Search ortholog groups by text (Lucene). Searches consensus_product, consensus_gene_name, description, functional_description. Summary fields: by_source, by_level, score stats. Returns group IDs for use with `genes_by_homolog_group`. Filterable by source/taxonomic_level/max_specificity_rank. |
| `genes_by_homolog_group` | Group IDs → member genes per organism. Summary fields (by_organism, top_categories, top_groups, total_categories, genes_per_group_max/median). Batch tool with not_found/not_matched for groups and organisms. Filterable by organisms. |
| `genes_by_ontology` | Find genes annotated to ontology term IDs, with hierarchy expansion. Summary fields (by_organism, by_category, by_term). Verbose adds matched_terms, gene_summary, function_description. |
| `gene_ontology_terms` | Reverse lookup: get ontology annotations for genes (batch). Always returns leaf (most specific) terms. Optional ontology filter (None = all). Rich summary fields (by_ontology with gene coverage, by_term, annotation density stats). |
| `differential_expression_by_gene` | Gene-centric differential expression. One row per gene × experiment × timepoint. Summary stats always returned; detail rows sorted by |log2FC|. Filters: organism, locus_tags, experiment_ids, direction, significant_only. Single organism enforced. |
| `differential_expression_by_ortholog` | Differential expression framed by ortholog groups. Cross-organism. Results at group × experiment × timepoint granularity (gene counts, not individual genes). Rich summary fields (by_organism, rows_by_status, rows_by_treatment_type, by_table_scope, top_groups, top_experiments). Supports verbose, limit. Batch: not_found/not_matched for groups, organisms, experiments. Filterable by organisms, experiment_ids, direction, significant_only. |
| `gene_response_profile` | Cross-experiment gene-level summary: how each gene responds across treatments/experiments. One result per gene with response breadth, rank stats, log2FC stats. Sorted by response breadth. |
| `list_clustering_analyses` | Browse, search, and filter clustering analyses. Each analysis groups related gene clusters from a publication. Returns analyses with inline cluster children. Lucene search on analysis name, treatment, experimental_context. Filterable by organism, cluster_type, treatment_type, background_factors, omics_type, experiment_ids, publication_doi, analysis_ids. Rich summary breakdowns. |
| `gene_clusters_by_gene` | Batch gene-centric cluster lookup. Locus tags → cluster memberships with analysis context (analysis_id, analysis_name). Single organism enforced. Reports genes_with/without_clusters, not_found, not_matched, by_analysis. Filterable by cluster_type, treatment_type, background_factors, publication_doi, analysis_ids. |
| `genes_in_cluster` | Cluster IDs or analysis_id → member genes. Drill-down tool. Accepts cluster_ids list OR analysis_id (mutually exclusive). Summary with top_categories, genes_per_cluster stats, analysis_name. Verbose includes gene-level and cluster-level descriptions with disambiguated names. |
| `run_cypher` | Raw Cypher escape hatch (read-only). Write operations blocked; syntax and schema validated via CyVer before execution. Returns `{returned, truncated, warnings, results}`. |

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
