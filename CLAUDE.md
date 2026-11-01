# CLAUDE.md

## Project Overview

Tools for exploring a Prochlorococcus/Alteromonas multi-omics knowledge graph (Neo4j). Provides an MCP server for Claude Code and a Python package with the same 42 functions.

The KG is built by the separate `multiomics_biocypher_kg` repo. This repo is **read-only** — it never writes to the graph.

**Expression schema:** The KG uses `Experiment` nodes with `Changes_expression_of` edges to Gene. `Experiment.treatment_type` is an array (`str[]`), and `background_factors` (`str[]`, may be null) describes experimental context. Use `'value' IN e.treatment_type` for filtering and `coalesce(e.background_factors, [])` for null safety. See few-shot examples in `kg/queries.py`.

## Build and Run

```bash
uv sync

# Validate Neo4j connection
uv run python scripts/validate_connection.py

# Start MCP server (standalone, for testing)
uv run multiomics-kg-mcp

# Tests
pytest tests/unit/ -v          # no Neo4j needed
pytest -m kg -v                # requires Neo4j at localhost:7687
```

There is no CLI. For an ad-hoc read-only query use the `run_cypher` MCP tool, or from Python
`GraphConnection().execute_query("MATCH (g:Gene) RETURN count(g) AS n")`
(`from multiomics_explorer.kg.connection import GraphConnection`).

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
| `kg_release_info` | KG release identity (version, built_at, counts, `controlled_vocabularies_hash`) + compatibility verdict `ok` / `warn` / `unknown`. Recommended first call. `warn` = quoted value lists in docs may be stale; calls are unaffected. `go_transport_excluded_targets` / `tcdb_substrate_excluded_targets` explain empty GO / TCDB transport answers (curation, not biology). |
| `kg_schema` | Graph schema with node labels, relationship types, property names; edge descriptions carry reading caveats (e.g. the GO transport edges are term definitions, not gene facts). Read before `run_cypher`. |
| `resolve_gene` | Resolve an exact gene identifier (case-insensitive name / locus tag / alias) to matching Gene nodes, sorted by organism. First step when the input isn't a locus tag; free text → `genes_by_function`. |
| `genes_by_function` | Free-text Lucene search across gene functional annotations; `organism` / `gene_categories` / `min_quality` filters. Envelope `by_organism`, `by_category`, score stats. `[AQ]` |
| `gene_details` | Every Gene node property for a locus-tag batch (sequence, `gene_summary`, `function_description`, `catalytic_activities`, `contributing_sources`, coordinates, PSORTb / SignalP strings). Use `gene_overview` for triage; this is the raw dump. `[AQ]` |
| `gene_overview` | Batch gene triage: identity + per-row routing counts (expression, clusters, DMs, chemistry `evidence_sources` incl. `go_transport`, TCDB / CAZy / NCBIfam / MEROPS, literature) saying which drill-down has data. Null best-hit / evidence scores = no call (rank, don't filter). Envelope `has_*` counts. `[AQ]` `[TRUST]` |
| `gene_homologs` | Batch: locus_tags → ortholog group memberships, one row per gene × group. Filter by `source` / `taxonomic_level` / rank. Feeds `genes_by_homolog_group` and `differential_expression_by_ortholog`. |
| `gene_aa_sequence` | Batch: locus_tags → amino-acid sequences for BLAST / HMMER / alignment (no nucleotide). `fasta=True` returns one multi-FASTA blob and nulls per-row `sequence`. Per-row `sequence_length`, `protein_id`; `not_matched` = gene exists, no sequence. |
| `gene_neighbors` | Batch: anchor locus_tags → genes within ±`window` positions on the same contig (positional adjacency only, NOT co-expression). Per-row `rank_offset`, `bp_gap`, `strand`, `same_strand`; filters `max_bp_distance`, `same_strand`. Coordinates and strand are co-populated (NCBI, or Cyanorak for genes only Cyanorak called — `coordinate_source`); an anchor without them would land in `not_matched`. |
| `list_filter_values` | Valid values (+ counts, descriptions) for every closed vocabulary — gene, expression, DM, chemistry and trust (`ontology=` scopes trust vocabularies). From `ControlledVocabulary`; pivot fallback + warning. `[TRUST]` |
| `list_metabolite_assays` | Discover MetaboliteAssay nodes (metabolomics measurement layer) — pre-flight for the three assay drill-downs. Filter by organism, `value_kind`, compartment, treatment, publication, experiment / assay / metabolite IDs, `rankable`. Envelope `by_organism`, `by_value_kind`, `by_compartment`, `by_detection_status` (most numeric edges are tested-absent — real biology, never default-filter); per-row `detection_status_counts`, `timepoints`. |
| `list_metabolites` | Discover / filter metabolites (text, elements, mass, xrefs, pathways, `structure_kind`, KEGG classes — curated examples: unlisted ≠ not in it). `organism_names` alone = reached by that organism by any route; with `evidence_sources` = that organism's own route (`evidence_sources` alone is KG-wide). Rows route to `genes_by_metabolite` / `assays_by_metabolite`; `stereo_relatives` flags other stereo forms. |
| `genes_by_metabolite` | Metabolite / role IDs (`chebi.role:<n>`) → genes in ONE organism via KEGG, TCDB and GO routes, kept apart per row (`evidence_source`). TCDB rows are direct systems by default; `include_tcdb_family_substrates=True` adds family rows — read `tcdb_family_substrates_not_shown` before calling an arm empty. Agreement: `by_evidence_source_combination`. `docs://analysis/transport`. |
| `metabolites_by_gene` | Gene-anchored mirror of `genes_by_metabolite`: locus_tags → metabolites / roles in one organism (same routes, switches, row class); extra filter `metabolite_elements`. `summary=True` for 50+ genes. |
| `metabolites_by_quantifies_assay` | Numeric assay edges (discover via `list_metabolite_assays(value_kind='numeric')`): one row per metabolite × assay with `value`, `detection_status`, `stereo_assignment`, timepoint; rankable-gated bucket / percentile / rank filters. Cross-organism. Tested-absent rows kept by default. |
| `metabolites_by_flags_assay` | Boolean drill-down on `Assay_flags_metabolite` (discover via `list_metabolite_assays(value_kind='boolean')`). One row per metabolite × flag edge: `flag_value` (bool), `n_positive`, `n_replicates`, `stereo_assignment`. Filter `flag_value` (`False` = tested-absent, real biology; both states always stored) and `stereo_assignment` (paper-stated vs KG-assumed form). Cross-organism. Envelope `by_value`, `by_stereo_assignment`; `excluded_assays` always `[]` (shape parity with the numeric twin). |
| `assays_by_metabolite` | Reverse lookup: metabolite IDs → every measurement edge, numeric + boolean arms merged (polymorphic rows; cross-arm fields explicitly `None`; `stereo_assignment` on both). Cross-organism by default. `evidence_kind` scopes to one arm; `stereo_assignment` drops KG-assumed stereo forms. Flat `not_found` / `not_matched`; read `metabolites_matched` for distinct metabolites (`total_matching` is rows). Envelope `by_stereo_assignment`. Drill back via `metabolites_by_quantifies_assay(assay_ids=..., metabolite_ids=...)`. |
| `list_organisms` | All organisms with taxonomy + per-organism capability counts (genes, publications, experiments incl. as coculture partner, DMs, chemistry, metabolomics, annotation coverage). `organism_names` = word match on `preferred_name` / synonyms. `[TRUST]` |
| `list_publications` | Publications with experiment summaries; filter by organism, treatment, background_factors, `search_text`, author, `publication_dois`. Per-row DM / metabolomics rollups and `discussed_gene_count` / `discussed_pathway_count` (prose literature index, not DE); envelope `by_discusses_coverage`. Drill named entities via `discussed_by_publication`. |
| `discussed_by_publication` | Literature-index lookup: publication DOIs → genes + KEGG pathways the paper names in prose (recall-biased router, NOT DE). Polymorphic rows: `entity_kind` (`gene` / `kegg_pathway`), `entity_id`, `entity_name`, `prominence` (`central` / `peripheral`); verbose adds the `evidence` quote. Cross-organism. Filters `entity_kind`, `prominence`; envelope `by_entity_kind`, `by_prominence`, `top_kegg_pathways`. Does not expand pathways to genes — chain into `genes_by_ontology(ontology='kegg')`. |
| `list_experiments` | Experiments with gene-count stats, per-timepoint `growth_phase`, `table_scope`, `control_timing` / `design_notes`, DM and metabolomics rollups. `organism=` = profiled organism; `coculture_partner=` / `coculture_role=` for partners. `summary=True` for breakdowns. Filters: treatment, background, omics, publication, `search_text`, compartment, IDs. |
| `ontology_landscape` | Rank (ontology × level) combinations for enrichment: per-level term-size distribution, genome coverage, optional experiment-weighted coverage. Default surveys all 17 ontologies; BRITE per tree, InterPro per `interpro_type`. Filters `ontology` (list), `tree`, `call_class`, `interpro_type`. `informative_only=True` by default. `[TRUST]` |
| `search_ontology` | Search (Lucene `search_text`) or browse (omit it: terms by `gene_count`, narrow with `level` / `tree` / `interpro_type` / `min_gene_count` / `organism`) across one or many of the 17 ontologies; `limit` / `offset` apply per ontology. Counts are subtree-scoped. Semantics per ontology: `docs://ontologies/{key}`. `[TRUST]` |
| `ontology_term_details` | Term-side drill-down for a mixed batch of prefixed term IDs: name, level, `is_informative`, gene / organism counts, `parents[]` / `children[]`, and `links_out[]` bridges (`composition` / `membership` / `router`; router is recall-biased, never a gene-function call). `organism=` adds `organism_gene_count`. Routes to `genes_by_ontology(term_ids=...)`. `[TRUST]` |
| `search_homolog_groups` | Lucene search over ortholog groups (consensus product / gene name / description). Envelope `by_source`, `by_level`, score stats. Filters `source`, `taxonomic_level`, `max_specificity_rank`. Returns group IDs for `genes_by_homolog_group`. |
| `genes_by_homolog_group` | Group IDs → member genes per organism (`organisms=[...]` word-matched). Envelope `by_organism`, `top_categories`, `top_groups`, genes-per-group stats; `not_found_groups` / `not_matched_groups` / `not_found_organisms` / `not_matched_organisms`. |
| `genes_by_ontology` | (gene × term) TERM2GENE for any of the 17 ontologies in ONE organism: `term_ids` expands down, `level` rolls up, both = scoped rollup; BRITE needs `tree=`; size filters `min/max_gene_set_size`. Rows carry the compact `evidence` ladder; trust filters off by default. Substrate questions → `genes_by_metabolite`. `[TRUST]` |
| `gene_ontology_terms` | Reverse lookup: genes → their ontology annotations (batch, ONE organism). `mode='leaf'` (default, most-specific terms; TCDB rows per gene = `tcdb_assignment_count`, `include_weak_tcdb_hits=True` adds below-gate hits) or `mode='rollup'` (ancestors at target `level`). `ontology: list | None` with skip / raise scoping on trust filters (incl. `tcdb_call`); `tree` for BRITE. Envelope `by_ontology` (gene coverage), `by_term`, `by_tcdb_call`, density stats, `skipped_ontologies`. `[TRUST]` |
| `differential_expression_by_gene` | Gene-centric DE: one row per gene × experiment × timepoint (largest absolute log2FC first), summary stats always returned. Single organism (inferred when omitted). Filters `locus_tags`, `experiment_ids`, `direction`, `significant_only`, `growth_phases`, `treatment_type`, `background_factors`. Rows carry `control_timing`. Read the experiment's `table_scope` before interpreting missing rows. |
| `differential_expression_by_ortholog` | Cross-organism DE framed by ortholog groups: rows at group × experiment × timepoint with gene counts per status (not individual genes), each carrying `control_timing`. Filters `organisms`, `experiment_ids`, `direction`, `significant_only`, `growth_phases`, `treatment_type`, `background_factors`. Envelope `by_organism`, `rows_by_status`, `rows_by_treatment_type`, `by_table_scope`, `top_groups`, `top_experiments`; `not_found_*` / `not_matched_*` per input batch. |
| `gene_response_profile` | Cross-experiment gene-level summary: per gene, response breadth across treatment groups, rank and log2FC stats, `groups_tested_not_responded`. Sorted by breadth. Single organism (inferred). The `response_matrix` / `gene_set_compare` package utilities pivot this output. |
| `list_clustering_analyses` | Browse / search / filter published clustering analyses, each with inline `GeneCluster` children. Lucene `search_text` over name, treatment, context. Filters `organism`, `cluster_type` (`list_filter_values('cluster_type')`), treatment, background, omics, `experiment_ids`, `publication_dois`, `analysis_ids`. Rich summary breakdowns. |
| `list_derived_metrics` | Discover DerivedMetric nodes (non-DE column-level evidence: rhythmicity flags, amplitudes, survival classes) — entry point for the DM family. Inspect `rankable` / `has_p_value` / `value_kind` / `allowed_categories` here before the drill-downs, whose gated filters raise on incompatible DMs. Filters organism, `metric_types`, `value_kind`, compartment, omics, treatment, background, `growth_phases`, publication, experiment / DM IDs, `rankable`, `has_p_value`; Lucene `search_text`. |
| `gene_derived_metrics` | Gene-centric batch lookup across numeric / boolean / categorical DMs: one row per gene × DM with a polymorphic `value`. Single organism. `not_found` (gene absent) / `not_matched` (kind mismatch). Pivot to `genes_by_{numeric,boolean,categorical}_metric` for edge-level filtering. |
| `genes_by_numeric_metric` | Drill-down on `Derived_metric_quantifies_gene`. Filters: raw `min_value` / `max_value` (always), `metric_bucket` / percentile / rank (rankable-gated; mixed input soft-excludes into `excluded_derived_metrics` + `warnings`), `significant_only` / `max_adjusted_p_value` (`has_p_value`-gated). Cross-organism. Envelope `by_metric` pairs the filtered slice with full-DM precomputed ranges. |
| `genes_by_boolean_metric` | Drill-down on `Derived_metric_flags_gene`. Filter `flag_value` (None / True / False; `False` returns tested-absent rows only on DMs that store `not_flagged` — read `by_metric[*].false_count`). Cross-organism. Envelope `by_value`; `excluded_derived_metrics` / `warnings` always `[]` (shape parity with the numeric twin). |
| `genes_by_categorical_metric` | Drill-down on `Derived_metric_classifies_gene`. Filter `categories` (must be a subset of the selected DMs' `allowed_categories`; unknowns raise with the allowed union). Cross-organism. Envelope `by_category`; per-DM `by_metric` pairs the filtered slice with the full-DM distribution and `allowed_categories` (may exceed observed). |
| `gene_clusters_by_gene` | Batch: locus_tags → cluster memberships with analysis context (`analysis_id`, `analysis_name`). Single organism. Envelope `genes_with_clusters` / `genes_without_clusters`, `by_analysis`; `not_found` / `not_matched`. Filters `cluster_type`, treatment, background, `publication_dois`, `analysis_ids`. |
| `genes_in_cluster` | Cluster IDs OR `analysis_id` (mutually exclusive) → member genes. Envelope `top_categories`, genes-per-cluster stats, `analysis_name`; `not_found_clusters` / `not_matched_clusters`. Verbose adds gene- and cluster-level descriptions. |
| `pathway_enrichment` | Pathway ORA (Fisher + BH) from DE results, single organism. `direction='both'` runs up and down per experiment × timepoint. Background: `table_scope` (default), `organism`, or an explicit locus-tag list. `tree` for BRITE; `interpro_type` REQUIRED for `ontology='interpro'`. Trust filters shape TERM2GENE and background identically. Long-format compareCluster-compatible rows + validation buckets. `docs://analysis/enrichment`. `[ENR]` `[TRUST]` |
| `cluster_enrichment` | Cluster-based ORA (Fisher + BH) over a clustering analysis, single organism, one test per cluster × term. Background: `cluster_union` (default), `organism`, or an explicit list. Same row / envelope shape, `tree`, trust filters and `interpro_type` requirement as `pathway_enrichment`. `docs://analysis/enrichment`. `[ENR]` `[TRUST]` |
| `run_cypher` | Read-only Cypher escape hatch: writes blocked, syntax and schema validated before execution. Returns `{returned, truncated, warnings, results}`. Stored names use `^` for apostrophes and `,` for pipes. |

`[AQ]` `annotation_quality` is a 0..3 numeric encoding of `Gene.annotation_state` (informative-evidence count).

`[ENR]` `informative_only=True` by default on the enrichment tools and `ontology_landscape` — terms the KG flags uninformative (GO roots such as go:0008150, KO-level catch-alls) are excluded. The KEGG global / overview maps (`kegg.pathway:ko01100` etc.) are flagged too; KEGG category / subcategory nodes are not — gate those with `level`. `search_ontology` / `genes_by_ontology` / `gene_ontology_terms` default to `False`. Per-row `is_informative` surfaced for diagnosis.

`[TRUST]` Annotation-trust surface: 15 of the 17 ontologies (all but `subcellular_localization` (PSORTb) / `signal_peptide_type` (SignalP)) carry a compact `evidence` ladder on gene→term rows (`sources` / `evidence_score` / `tier` verbose); PSORTb / SignalP native detail — `localization_score`, `signal_peptide_*` — is verbose-only. Filters `sources`, `evidence`, `max_tier`, `min_evidence_score` (the only numeric cutoff; not on TCDB), `call_class` (MEROPS), `tcdb_call` (TCDB), `interpro_type` (InterPro, required on interpro enrichment). TCDB rows and gene sets read gated edges only (`tcdb_gate` direct or annotated). See `docs://analysis/annotation_evidence`.

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
- Configure via `.env`: `NEO4J_URI`, `NEO4J_USERNAME` (or back-compat alias `NEO4J_USER`), `NEO4J_PASSWORD`, optional `NEO4J_DATABASE` (default `neo4j`)
- KG deployed via Docker from `multiomics_biocypher_kg` repo

## Key Files

| File | Purpose |
|---|---|
| `multiomics_explorer/mcp_server/server.py` | MCP server entry point (FastMCP with Neo4j lifespan) |
| `multiomics_explorer/mcp_server/tools.py` | MCP tool implementations |
| `multiomics_explorer/kg/connection.py` | Neo4j driver wrapper (shared by MCP + Python API) |
| `multiomics_explorer/kg/schema.py` | Schema introspection from live KG |
| `multiomics_explorer/kg/queries.py` | Curated Cypher queries + few-shot examples |
| `multiomics_explorer/kg/queries_lib.py` | Query builder functions (parameterized Cypher) |
| `multiomics_explorer/api/functions.py` | Public Python API — wraps query builders + execute |
| `multiomics_explorer/config/settings.py` | Pydantic settings from .env |
| `multiomics_explorer/inputs/tools/{tool}.yaml` | Human-authored about-content (examples, mistakes, chaining, verbose_fields) — generated md is downstream |
| `multiomics_explorer/inputs/ontologies/{key}.yaml` | Human-authored per-ontology reference (17, keys = `ONTOLOGY_CONFIG`) — generated `references/ontologies/{key}.md` is downstream (`docs://ontologies/{key}`) |
| `scripts/build_about_content.py` | Generator — writes brief tool pages to `skills/multiomics-kg-guide/references/tools/*.md`, full tool pages to `references/tools/full/*.md`, and the docs directory to `references/index.md`, all directly (no separate sync step) |
| `CHANGELOG.md` | User-facing release notes: `[Unreleased]` holds only what changes for users (KG link + `### Highlights`, then Breaking / Added / Changed / Fixed); shape in the `release-explorer` skill |
| `docs/backlog.md` | The only open-work list — one line per item with size + origin; delete items when they ship (CHANGELOG keeps the record) |

## Skill / about-content workflow

Per `.claude/skills/layer-rules/`, the two skill subtrees behave differently:

**Tool docs are generated** — never edit
`multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md` (brief
pages), `references/tools/full/*.md` (full pages), or `references/index.md`
(the docs directory) directly — all three are written by the generator.
Source of truth:

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

**Per-ontology reference docs are generated too** — never edit
`multiomics_explorer/skills/multiomics-kg-guide/references/ontologies/*.md`
(served at `docs://ontologies/{key}` + `docs://ontologies/index`). Source of
truth: the hand-authored `multiomics_explorer/inputs/ontologies/{key}.yaml`
(keys = `ONTOLOGY_CONFIG` keys; fields `what_it_is`, `method`, `id_form`,
`hierarchy`, `interpretation`, `informativeness_rule`, `pitfalls`,
`typical_questions[]`, `see_also[]`) merged at build time with the
`ONTOLOGY_CONFIG` row (label, gene_rel, hierarchy rels, trust axes, facet,
compact/verbose columns, bridges), `config/schema_baseline.yaml` node props,
and — when a KG is reachable — `ControlledVocabulary` values (falls back to a
`list_filter_values` pointer; no Neo4j needed to build). The default build
runs this stage; `--ontologies` runs it alone; `--lint` covers the dir.

**Analysis docs are hand-authored** —
`multiomics_explorer/skills/multiomics-kg-guide/references/analysis/*.md` (e.g.
`enrichment.md`, `metabolites.md`) are edited directly. Update the corresponding
md when an analysis utility's signature, return shape, or behavior changes.
