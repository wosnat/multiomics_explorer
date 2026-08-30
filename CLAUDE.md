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
| `kg_release_info` | KG release identity (version, built_at, counts, `controlled_vocabularies_hash`) + compatibility verdict `ok` / `warn` / `unknown` vs what this explorer build expects. Recommended first call. `warn` = quoted value lists in docs may be stale; calls are unaffected (filters validate live, `list_filter_values` reads live). |
| `kg_schema` | Graph schema with node labels, relationship types, property names. Read before `run_cypher`. |
| `resolve_gene` | Resolve a gene identifier (case-insensitive name / locus tag / partial label) to matching Gene nodes, sorted by organism. First step when the input isn't a locus tag. |
| `genes_by_function` | Free-text Lucene search across gene functional annotations; `organism` / `gene_categories` / `min_quality` filters. Envelope `by_organism`, `by_category`, score stats. `[AQ]` |
| `gene_details` | Every Gene node property for a locus-tag batch (sequence, `gene_summary`, `function_description`, `catalytic_activities`, `contributing_sources`, coordinates, PSORTb / SignalP strings). Use `gene_overview` for triage; this is the raw dump. `[AQ]` |
| `gene_overview` | Batch gene triage: identity + data-availability routing per row — `expression_edge_count`, `cluster_membership_count`, `derived_metric_count`, `evidence_sources` (chemistry), `tcdb_family_count` / `cazy_family_count` / `ncbifam_family_count` / `merops_classes`, `tcdb_evidence_score_max` / `merops_evidence_score_max` (null = no call; rank, don't filter), `transport_substrate_resolution`, `discussed_in_publication_count` (literature index, not DE). Envelope `has_*` counts + `top_discussing_publications`; verbose adds per-kind DM counts and discussing DOIs. `[AQ]` `[TRUST]` |
| `gene_homologs` | Batch: locus_tags → ortholog group memberships, one row per gene × group. Filter by `source` / `taxonomic_level` / rank. Feeds `genes_by_homolog_group` and `differential_expression_by_ortholog`. |
| `gene_aa_sequence` | Batch: locus_tags → amino-acid sequences for BLAST / HMMER / alignment (no nucleotide). `fasta=True` returns one multi-FASTA blob and nulls per-row `sequence`. Per-row `sequence_length`, `protein_id`; `not_matched` = gene exists, no sequence. |
| `gene_neighbors` | Batch: anchor locus_tags → genes within ±`window` positions on the same contig (positional adjacency only, NOT co-expression). Per-row `rank_offset`, `bp_gap`, `strand`, `same_strand`; filters `max_bp_distance`, `same_strand`. Strand and coordinates are null together (~3% of genes, expression-only) — those anchors land in `not_matched`. |
| `list_filter_values` | Valid values (with counts and, where the KG provides them, descriptions) for every closed vocabulary: `gene_category`, `brite_tree`, `growth_phase`, `metric_type`, `value_kind`, `compartment`, `omics_type`, `evidence_source`, `cluster_type`, `treatment_type`, `background_factors`, `table_scope`, `detection_status`, `expression_status`, and the trust vocabularies (`evidence`, `sources`, `call_class`, `interpro_type`, `ncbifam_family_type`, `merops_*`, `best_hit_kind`, `pfam_support`, `attachment_depth`, `trust_axes`, `link_kinds`; scope with `ontology=`). Read from `ControlledVocabulary` nodes, pivot-query fallback + warning if one is missing. `[TRUST]` |
| `list_metabolite_assays` | Discover MetaboliteAssay nodes (metabolomics measurement layer) — pre-flight for the three assay drill-downs. Filter by organism, `value_kind`, compartment, treatment, publication, experiment / assay / metabolite IDs, `rankable`. Envelope `by_organism`, `by_value_kind`, `by_compartment`, `by_detection_status` (most numeric edges are tested-absent — real biology, never default-filter); per-row `detection_status_counts`, `timepoints`. |
| `list_metabolites` | Discover / filter metabolites in the chemistry layer (KEGG reactions + TCDB substrates + measured compounds). Filters: `search_text` (Lucene), `elements`, mass, `organism_names` (exact preferred_name), `pathway_ids`, `evidence_sources`, xref ID lists, `exclude_metabolite_ids`. Per-row routing: `catalyst_gene_count` → `genes_by_metabolite`, `transporter_gene_count` (genes) vs `transporter_count` (TcdbFamily systems), `measured_assay_count` → `assays_by_metabolite`. Envelope `by_evidence_source`, `top_metabolite_pathways`, `xref_coverage`, `by_measurement_coverage`, `resolved_aliases`. |
| `genes_by_metabolite` | Drill-down: metabolite IDs → gene catalysts (`Gene → Reaction → Metabolite`) and transporters (`Gene → TcdbFamily → Metabolite`, deepest attachment only) in ONE organism. Per-row `evidence_source`, `substrate_depth` (`most_specific` / `inherited`), `tcdb_evidence_score`, `transport_substrate_resolution`. Filters `ec_numbers`, `mass_balance`, `metabolite_pathway_ids`, `gene_categories`, `substrate_depth`, `evidence_sources`, `exclude_metabolite_ids`. Envelope `by_metabolite`, `top_genes`, `top_reactions`, `top_tcdb_families`; warning when inherited rows dominate. Reactions are undirected. |
| `metabolites_by_gene` | Gene-anchored chemistry drill-down: locus_tags → metabolites via reaction / transport (mirror of `genes_by_metabolite`, same row class and depth discriminators). Single organism. Extra filter `metabolite_elements` (AND-of-presence, e.g. `['N']`); envelope `by_gene` (carries `transport_substrate_resolution`), `top_metabolites`, `top_metabolite_pathways`, `by_element`; warning when a gene is `family_inferred`. Rows sort metabolism → most_specific → inherited so one ABC-only gene can't eat the page. `summary=True` for 50+ genes. |
| `metabolites_by_quantifies_assay` | Numeric drill-down on `Assay_quantifies_metabolite` (discover via `list_metabolite_assays(value_kind='numeric')`). One row per metabolite × assay edge: `value`, `detection_status`, `timepoint*`, plus rankable-gated `metric_bucket` / `metric_percentile` / `rank_by_metric` (mixed input soft-excludes into `excluded_assays` + `warnings`; all-non-rankable raises). Cross-organism. Tested-absent rows (`value=0` / `not_detected`) kept by default. Envelope `by_detection_status`, `by_metric`; `not_found` is a dict by input bucket. |
| `metabolites_by_flags_assay` | Boolean drill-down on `Assay_flags_metabolite` (discover via `list_metabolite_assays(value_kind='boolean')`). One row per metabolite × flag edge: `flag_value` (bool), `n_positive`, `n_replicates`. Filter `flag_value` (`False` = tested-absent, real biology; both states always stored). Cross-organism. Envelope `by_value`; `excluded_assays` always `[]` (shape parity with the numeric twin). |
| `assays_by_metabolite` | Reverse lookup: metabolite IDs → every measurement edge, numeric + boolean arms merged (polymorphic rows; cross-arm fields explicitly `None`). Cross-organism by default. `evidence_kind` scopes to one arm. Flat `not_found` / `not_matched`; read `metabolites_matched` for distinct metabolites (`total_matching` is rows). Drill back via `metabolites_by_quantifies_assay(assay_ids=..., metabolite_ids=...)`. |
| `list_organisms` | All organisms with taxonomy and per-organism counts: genes, publications, experiments, treatment / omics types, DM rollups, chemistry (`reaction_count`, `catalyzed_metabolite_count`, `transported_metabolite_count`), `measured_metabolite_count`, annotation coverage (`peptidase_gene_count`, `interpro_gene_count`, `ncbifam_gene_count`). `organism_names` = word match on `preferred_name` / synonyms. Envelope `top_metabolic_capability`, `top_annotation_capability`, `by_measurement_capability`. Two nodes share `preferred_name='Meiothermus ruber'` — join counts via `Gene_belongs_to_organism`, never by name. `[TRUST]` |
| `list_publications` | Publications with experiment summaries; filter by organism, treatment, background_factors, `search_text`, author, `publication_dois`. Per-row DM / metabolomics rollups and `discussed_gene_count` / `discussed_pathway_count` (prose literature index, not DE); envelope `by_discusses_coverage`. Drill named entities via `discussed_by_publication`. |
| `discussed_by_publication` | Literature-index lookup: publication DOIs → genes + KEGG pathways the paper names in prose (recall-biased router, NOT DE). Polymorphic rows: `entity_kind` (`gene` / `kegg_pathway`), `entity_id`, `entity_name`, `prominence` (`central` / `peripheral`); verbose adds the `evidence` quote. Cross-organism. Filters `entity_kind`, `prominence`; envelope `by_entity_kind`, `by_prominence`, `top_kegg_pathways`. Does not expand pathways to genes — chain into `genes_by_ontology(ontology='kegg')`. |
| `list_experiments` | Experiments with gene-count stats (`gene_count` cumulative over timepoints, `distinct_gene_count` for background sizing), per-timepoint `growth_phase`, `table_scope`, `authors`, DM and metabolomics rollups. `summary=True` for breakdowns by organism / treatment / background / omics / table_scope. `organism=` is the profiled organism; use `coculture_partner=` for the partner. Filters: treatment, background, omics, publication, `search_text`, `table_scope`, `compartment`, `experiment_ids`. |
| `ontology_landscape` | Rank (ontology × level) combinations for enrichment: per-level term-size distribution, genome coverage, optional experiment-weighted coverage. Default surveys all 17 ontologies; BRITE per tree, InterPro per `interpro_type`. Filters `ontology` (list), `tree`, `call_class`, `interpro_type`. `informative_only=True` by default. `[TRUST]` |
| `search_ontology` | Search (`search_text`, Lucene, `score`-sorted) or browse (omit `search_text`: every term sorted `gene_count DESC`, envelope `by_level`; narrow with `level` / `tree` / `interpro_type` / `min_gene_count` / `organism`) terms across one or many of the 17 ontologies. `ontology: list | None`; `limit` / `offset` apply per ontology (lockstep). `gene_count` / `organism_gene_count` are subtree-scoped. Verbose adds `description`, `direct_gene_count`, per-ontology detail; KEGG rows carry `discussed_by_n_publications`. Semantics per ontology: `docs://ontologies/{key}`. `[TRUST]` |
| `ontology_term_details` | Term-side drill-down for a mixed batch of self-prefixed term IDs (`go:`, `tcdb:`, `merops.family:`, `interpro:`, `ncbifam:`, `tigr.role:`, `kegg.pathway:`, `pfam:`, `ec:`, `cazy:`): name, level, `is_informative`, gene / organism / direct counts, `parents[]`, `children[]`, and `links_out[]` bridges (`link_kind` = `composition` / `membership` / `router`; router is recall-biased, never a gene-function call). Filter bridges with `link_kinds`; `organism=` adds `organism_gene_count`; verbose adds `properties`, `router_ambiguous`, `genes_by_organism`. Routes to `genes_by_ontology(term_ids=...)`. `[TRUST]` |
| `search_homolog_groups` | Lucene search over ortholog groups (consensus product / gene name / description). Envelope `by_source`, `by_level`, score stats. Filters `source`, `taxonomic_level`, `max_specificity_rank`. Returns group IDs for `genes_by_homolog_group`. |
| `genes_by_homolog_group` | Group IDs → member genes per organism (`organisms=[...]` word-matched). Envelope `by_organism`, `top_categories`, `top_groups`, genes-per-group stats; `not_found_groups` / `not_matched_groups` / `not_found_organisms` / `not_matched_organisms`. |
| `genes_by_ontology` | (gene × term) pairs for ontology terms in ONE organism, with hierarchy expansion: `term_ids` only expands DOWN, `level` only rolls UP, both = scoped rollup. TERM2GENE output for enrichment. All 17 ontologies; BRITE needs `tree=`; size filters `min/max_gene_set_size`. Compact rows carry `evidence` (+ `interpro_type`, `call_class`); verbose adds `sources` / `evidence_score` / `tier` and native detail. Trust filters `sources`, `evidence`, `max_tier`, `min_evidence_score`, `call_class`, `interpro_type` default to None. Substrate-anchored TCDB questions: `genes_by_metabolite`. `[TRUST]` |
| `gene_ontology_terms` | Reverse lookup: genes → their ontology annotations (batch, ONE organism). `mode='leaf'` (default, most-specific terms; TCDB keeps deepest attachments unless `include_superseded=True`) or `mode='rollup'` (ancestors at target `level`). `ontology: list | None` with skip / raise scoping on trust filters; `tree` for BRITE. Envelope `by_ontology` (gene coverage), `by_term`, density stats, `skipped_ontologies`. `[TRUST]` |
| `differential_expression_by_gene` | Gene-centric DE: one row per gene × experiment × timepoint, sorted by |log2FC|; summary stats always returned. Filters `organism` (inferred from `locus_tags` / `experiment_ids` when omitted; must resolve to one), `locus_tags`, `experiment_ids`, `direction` (`up` / `down` / `both`), `significant_only`. Read the experiment's `table_scope` before interpreting missing rows. |
| `differential_expression_by_ortholog` | Cross-organism DE framed by ortholog groups: rows at group × experiment × timepoint with gene counts per status (not individual genes). Filters `organisms`, `experiment_ids`, `direction`, `significant_only`. Envelope `by_organism`, `rows_by_status`, `rows_by_treatment_type`, `by_table_scope`, `top_groups`, `top_experiments`; `not_found_*` / `not_matched_*` per input batch. |
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

`[AQ]` `annotation_quality` is a 0..3 numeric encoding of `Gene.annotation_state` (informative-evidence count); earlier KG releases encoded product-name quality in the same field, so old `min_quality` filters silently select a different set.

`[ENR]` `informative_only=True` by default on the enrichment tools and `ontology_landscape` — terms the KG flags uninformative (GO roots such as go:0008150, KO-level catch-alls) are excluded. The KEGG global / overview maps (`kegg.pathway:ko01100` etc.) are flagged too; KEGG category / subcategory nodes are not — gate those with `level`. `search_ontology` / `genes_by_ontology` / `gene_ontology_terms` default to `False`. Per-row `is_informative` surfaced for diagnosis.

`[TRUST]` Annotation-trust surface: 15 of the 17 ontologies (all but `subcellular_localization` (PSORTb) / `signal_peptide_type` (SignalP)) carry a compact `evidence` ladder on gene→term rows (`sources` / `evidence_score` / `tier` verbose); PSORTb / SignalP native detail — `localization_score`, `signal_peptide_*` — is verbose-only. Filters `sources`, `evidence`, `max_tier`, `min_evidence_score` (the only numeric cutoff), `call_class` (MEROPS), `interpro_type` (InterPro, required on interpro enrichment). See `docs://analysis/annotation_evidence`.

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
| `scripts/build_about_content.py` | Generator — writes `skills/multiomics-kg-guide/references/tools/*.md` directly (no separate sync step) |
| `docs/backlog.md` | The only open-work list — one line per item with size + origin; delete items when they ship (CHANGELOG keeps the record) |

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
