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

**Adding or modifying a tool?** Use the `add-or-update-tool` skill — it
orchestrates Phase 1 (scope + KG iteration + Cypher verification) and
Phase 2 (parallel TDD build with file-owned agents). See
`docs/superpowers/specs/2026-05-03-add-or-update-tool-redesign.md` for the
design.

The MCP server (`multiomics_explorer/mcp_server/`) is the primary interface for Claude Code.

### Tools

| Tool | Purpose |
|---|---|
| `kg_schema` | Graph schema with node labels, relationship types, property names |
| `resolve_gene` | Resolve a gene identifier (case-insensitive) to matching graph nodes. Returns flat list sorted by organism. |
| `genes_by_function` | Free-text search across gene functional annotations (Lucene syntax). Rich summary fields (by_organism, by_category, score stats). Supports category and organism filtering. `[AQ]` |
| `gene_details` | All Gene node properties via g{.*} — use gene_overview for the common case. `[AQ]` |
| `gene_overview` | Batch gene routing: identity + data availability signals (annotation_types, expression counts, ortholog summary, cluster membership). Accepts locus_tags list. Rich summary fields (by_organism, by_category, by_annotation_type, expression/ortholog/cluster availability counts). Per-row `derived_metric_count` + `derived_metric_value_kinds` (route to drill-downs); verbose adds per-kind counts + `compartments_observed`. Envelope `has_derived_metrics`. When per-row chemistry counts (`reaction_count`, `metabolite_count`, `transporter_count`) are non-zero, drill in via `genes_by_metabolite(metabolite_ids=[...], organism=...)` (metabolite-anchored) or the upcoming gene→metabolite tool (gene-anchored). `[AQ]` |
| `gene_homologs` | Batch: gene locus_tags → ortholog group memberships. Flat long format (one row per gene × group). Filterable by source/level/rank. |
| `list_filter_values` | List valid values for categorical filters (gene categories, BRITE trees, DM discovery). Filter types: `gene_category`, `brite_tree`, `metric_type`, `value_kind`, `compartment`. |
| `list_metabolites` | Discover/filter metabolites in the chemistry layer (incl. TCDB transport substrates). Filterable by elements, mass, organism_names, pathway_ids, evidence_sources, plus xref ID batch input. Rich envelope (top_organisms, top_pathways, by_evidence_source, xref_coverage, mass_stats) and per-row routing (gene_count, transporter_count → drill-down tools). |
| `genes_by_metabolite` | Drill-down: metabolite IDs → gene catalysts (`Gene → Reaction → Metabolite`) and transporters (`Gene → TcdbFamily → Metabolite`, rollup-extended). Single-organism enforced. Per-row `evidence_source` (`metabolism` / `transport`) and `transport_confidence` (`substrate_confirmed` / `family_inferred`) discriminate path and rollup-precision. Auto-warning when family_inferred dominates transport rows. Filterable by `ec_numbers`, `mass_balance`, `metabolite_pathway_ids`, `gene_categories`, `transport_confidence`, `evidence_sources` (per-arm scope: `ec_numbers`/`mass_balance` narrow metabolism only; `transport_confidence` narrows transport only; `metabolite_pathway_ids`/`gene_categories` narrow both). Routes from `top_genes` to `differential_expression_by_gene` / `gene_overview`; from `top_tcdb_families` to `genes_by_ontology(ontology="tcdb")`; from `top_reactions` to `genes_by_ontology(ontology="ec")` / `pathway_enrichment`. |
| `metabolites_by_gene` | Gene-anchored chemistry drill-down (gene → metabolites via reaction / transport). Symmetric counterpart to `genes_by_metabolite`; reuses the `GeneReactionMetaboliteTriplet` row class. Single-organism enforced. Same per-row `evidence_source` / `transport_confidence` discriminators and family_inferred-dominance auto-warning (per-gene-side here — the 9 ABC-superfamily-only MED4 genes each emit 551 transport-arm family_inferred rows). New filter: `metabolite_elements` (presence-only AND-of, e.g. `['N']` for the N-source workflow primitive). Inherited filters (per-arm scope mirrors GBM): `metabolite_ids`, `metabolite_pathway_ids`, `ec_numbers`, `mass_balance`, `gene_categories`, `transport_confidence`, `evidence_sources`. Detail rows globally sorted by precision tier (metabolism → substrate_confirmed → family_inferred) so a single ABC-only gene can't eat `limit=10`. New envelope rollups: `top_pathways` (KEGG pathways the gene set's chemistry reaches via reaction-side OR metabolite-side; chemistry-pathway filtered by `KeggTerm.reaction_count >= 3`) + `by_element` (C/N/P/S/metal-presence signature, periodic-table-bounded). Routes from `top_metabolites` to `list_metabolites(metabolite_ids=...)` for cross-refs OR to `genes_by_metabolite(metabolite_ids=..., organism=PARTNER)` for cross-feeding bridge (Workflow B'); from `top_pathways` to `list_metabolites(pathway_ids=...)` for full pathway roster (distinct from gene-KO pathway annotations in `genes_by_ontology(ontology="kegg")` — disambiguation in docstring); from `not_matched` to `gene_overview` for annotation context. Use `summary=True` for batch DE inputs (50+ locus_tags). |
| `list_organisms` | All organisms with taxonomy, gene/publication/experiment counts, treatment types, background factors, omics types. Verbose adds full taxonomy hierarchy. Filterable by `organism_names` (exact match, case-insensitive on `preferred_name`). Returns `not_found` when `organism_names` includes unknown values. Per-row `derived_metric_count`/`derived_metric_value_kinds`/`compartments` rollup; `compartment` filter; envelope `by_value_kind`/`by_metric_type`/`by_compartment`. Per-row `reaction_count`/`metabolite_count` chemistry-capability rollups; envelope `by_metabolic_capability` (top 10 organisms by metabolite_count, excludes zero-chemistry). |
| `list_publications` | Publications with experiment summaries, filterable by organism/treatment/background_factors/search/author/publication_dois. Returns `not_found` when `publication_dois` includes unknown values. Per-row `derived_metric_count`/`derived_metric_value_kinds`/`compartments` rollup; `compartment` filter; envelope `by_value_kind`/`by_metric_type`/`by_compartment`. |
| `list_experiments` | Experiments with gene-count stats. Per result: `gene_count` (cumulative row count across timepoints) + `distinct_gene_count` (unique genes — use for detection-power / background sizing). Per timepoint: `growth_phase` (str \| None). Use `summary=true` for breakdowns by organism/treatment/background_factors/omics/table_scope, default returns individual experiments. Filterable by organism/treatment/background_factors/omics/publication/search/table_scope/experiment_ids. `organism=` matches the profiled organism only — combine with `coculture_partner=` for partner-side filtering. Returns `not_found` when `experiment_ids` includes unknown values. Per-row `authors` (from Publication), `derived_metric_count`/`derived_metric_value_kinds`/`compartment`; `compartment` filter; envelope `by_value_kind`/`by_metric_type`/`by_compartment`. Search-text picks up DM tokens. |
| `ontology_landscape` | Rank (ontology × level) combinations for enrichment. Per-level term-size distribution, genome coverage, best-effort share (GO), optional experiment-weighted coverage. Default surveys all 12 ontologies (GO, KEGG, EC, COG, Cyanorak, TIGR, Pfam, BRITE, TCDB, CAZy). BRITE rows broken down per tree. Filterable by `tree` (BRITE only). |
| `search_ontology` | Browse ontology terms by text search (GO, KEGG, EC, COG, Cyanorak, TIGR, Pfam, BRITE, TCDB, CAZy). Summary fields: total_entries, score stats. Returns term IDs with `level` for use with `genes_by_ontology`. Filterable by `level` and `tree` (BRITE only). |
| `search_homolog_groups` | Search ortholog groups by text (Lucene). Searches consensus_product, consensus_gene_name, description, functional_description. Summary fields: by_source, by_level, score stats. Returns group IDs for use with `genes_by_homolog_group`. Filterable by source/taxonomic_level/max_specificity_rank. |
| `genes_by_homolog_group` | Group IDs → member genes per organism. Summary fields (by_organism, top_categories, top_groups, total_categories, genes_per_group_max/median). Batch tool with not_found/not_matched for groups and organisms. Filterable by organisms. |
| `genes_by_ontology` | Find (gene × term) pairs annotated to ontology terms (GO, KEGG, EC, COG, Cyanorak, TIGR, Pfam, BRITE, TCDB, CAZy), with hierarchy expansion. Three modes: `term_ids` only (expand DOWN), `level` only (roll UP), both (scoped rollup). TERM2GENE output for enrichment. Single organism enforced. Filterable by `tree` (BRITE only). Size filter (`min/max_gene_set_size`) matches `ontology_landscape`. For substrate-anchored TCDB questions (compound → genes), chain via `genes_by_metabolite` instead. |
| `gene_ontology_terms` | Reverse lookup: get ontology annotations for genes (batch). Two modes: `leaf` (default, most-specific terms) and `rollup` (walk up to ancestors at target level). Single organism enforced. Returns `level` per row, sparse `tree`/`tree_code` for BRITE. Filterable by `level`, `tree` (BRITE only). Rich summary fields (by_ontology with gene coverage, by_term, annotation density stats). |
| `differential_expression_by_gene` | Gene-centric differential expression. One row per gene × experiment × timepoint. Summary stats always returned; detail rows sorted by |log2FC|. Filters: organism, locus_tags, experiment_ids, direction, significant_only. Single organism enforced. |
| `differential_expression_by_ortholog` | Differential expression framed by ortholog groups. Cross-organism. Results at group × experiment × timepoint granularity (gene counts, not individual genes). Rich summary fields (by_organism, rows_by_status, rows_by_treatment_type, by_table_scope, top_groups, top_experiments). Supports verbose, limit. Batch: not_found/not_matched for groups, organisms, experiments. Filterable by organisms, experiment_ids, direction, significant_only. |
| `gene_response_profile` | Cross-experiment gene-level summary: how each gene responds across treatments/experiments. One result per gene with response breadth, rank stats, log2FC stats. Sorted by response breadth. |
| `list_clustering_analyses` | Browse, search, and filter clustering analyses. Each analysis groups related gene clusters from a publication. Returns analyses with inline cluster children. Lucene search on analysis name, treatment, experimental_context. Filterable by organism, cluster_type, treatment_type, background_factors, omics_type, experiment_ids, publication_doi, analysis_ids. Rich summary breakdowns. |
| `list_derived_metrics` | Discover DerivedMetric nodes (non-DE column-level evidence — rhythmicity flags, diel amplitudes, darkness-survival class). Entry point for the DM tool family. Inspect `rankable` / `has_p_value` / `value_kind` / `allowed_categories` here before drill-down tools (`gene_derived_metrics`, `genes_by_{numeric,boolean,categorical}_metric`) — those filters require gate-compatible DMs and raise otherwise. Filterable by organism, metric_types, value_kind, compartment, omics_type, treatment_type, background_factors, growth_phases, publication_doi, experiment_ids, derived_metric_ids, rankable, has_p_value. Lucene search + rich summary breakdowns. |
| `gene_derived_metrics` | Gene-centric batch lookup for DerivedMetric annotations across numeric / boolean / categorical kinds. One row per gene × DM with polymorphic `value` column. Single organism enforced. Reports `not_found` / `not_matched` (kind-mismatch) for diagnosability. Pivots to `genes_by_{kind}_metric` for edge-level numeric filtering. |
| `genes_by_numeric_metric` | Drill-down on `Derived_metric_quantifies_gene` (numeric DM family). Edge filters: raw-value threshold (always available), bucket / percentile / rank (rankable-gated, soft-exclude on mixed input), p-value (has_p_value-gated; raises today). Cross-organism by design. `by_metric` envelope pairs filtered-slice value distribution with full-DM context (precomputed). |
| `genes_by_boolean_metric` | Drill-down on `Derived_metric_flags_gene` (boolean DM family). Edge filter: `flag` (None / True / False; `False` returns 0 rows today per positive-only KG storage — `dm_false_count=0` on every current DM). Cross-organism by design. Wrong-kind IDs surface silently as `not_found_ids`. `by_value` envelope rollup; per-DM `by_metric` pairs filtered-slice `count`/`true_count`/`false_count` with full-DM `dm_*_count` (precomputed). `excluded_derived_metrics` / `warnings` always `[]` (no gates) — kept for cross-tool envelope-shape consistency. |
| `genes_by_categorical_metric` | Drill-down on `Derived_metric_classifies_gene` (categorical DM family). Edge filter: `categories` (subset of selected DMs' `allowed_categories`; unknowns raise `ValueError` with the full allowed union in the message). Cross-organism by design. `by_category` envelope rollup; per-DM `by_metric` pairs filtered-slice `by_category` with full-DM `dm_by_category` (zip of `category_labels` + `category_counts`) plus `allowed_categories` (schema-declared full set; may be a strict superset of observed). `excluded_derived_metrics` / `warnings` always `[]` — cross-tool envelope-shape consistency. |
| `gene_clusters_by_gene` | Batch gene-centric cluster lookup. Locus tags → cluster memberships with analysis context (analysis_id, analysis_name). Single organism enforced. Reports genes_with/without_clusters, not_found, not_matched, by_analysis. Filterable by cluster_type, treatment_type, background_factors, publication_doi, analysis_ids. |
| `genes_in_cluster` | Cluster IDs or analysis_id → member genes. Drill-down tool. Accepts cluster_ids list OR analysis_id (mutually exclusive). Summary with top_categories, genes_per_cluster stats, analysis_name. Verbose includes gene-level and cluster-level descriptions with disambiguated names. |
| `pathway_enrichment` | Pathway ORA (Fisher + BH) from DE results. Single-organism. `direction='both'` runs up and down per experiment×timepoint. Background modes: `table_scope` (default), `organism`, or explicit locus_tag list. Filterable by `tree` (BRITE only). Long-format compareCluster-compatible rows + envelope with validation buckets. See `docs://analysis/enrichment`. |
| `run_cypher` | Raw Cypher escape hatch (read-only). Write operations blocked; syntax and schema validated via CyVer before execution. Returns `{returned, truncated, warnings, results}`. |

`[AQ]` `annotation_quality` was redefined in the May 2026 KG release as a 0..3 numeric encoding of `Gene.annotation_state` (informative-evidence count). Existing `min_quality` filters silently shifted meaning.

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
| `multiomics_explorer/inputs/tools/{tool}.yaml` | Human-authored about-content (examples, mistakes, chaining, verbose_fields) — generated md is downstream |
| `scripts/build_about_content.py` | Generator — writes `skills/multiomics-kg-guide/references/tools/*.md` directly (no separate sync step) |

## Skill / about-content workflow

Per `.claude/skills/layer-rules/`, the two skill subtrees behave differently:

**Tool docs are generated** — never edit
`multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md` directly. Source of truth:

- Human-authored sections (`examples`, `mistakes`, `chaining`, `verbose_fields`,
  any new section structures): `multiomics_explorer/inputs/tools/{tool}.yaml`.
- Auto-generated sections (params, response format, envelope keys, "Package
  import equivalent"): Pydantic models in `mcp_server/tools.py` plus the
  generator in `scripts/build_about_content.py`. To change a generated section
  structure, edit the script (and the YAML schema if a new field is needed).

After edits, regenerate (writes directly to the skills tree):

```bash
uv run python scripts/build_about_content.py
```

**Analysis docs are hand-authored** —
`multiomics_explorer/skills/multiomics-kg-guide/references/analysis/*.md` (e.g.
`enrichment.md`, `expression.md`) are edited directly. Update the corresponding
md when an analysis utility's signature, return shape, or behavior changes.
