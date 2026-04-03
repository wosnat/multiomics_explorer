# ClusteringAnalysis MCP Tools Design

**Date:** 2026-04-03
**Status:** Draft
**Depends on:** [ClusteringAnalysis Node Design (2026-03-31)](/home/osnat/github/multiomics_biocypher_kg/docs/superpowers/specs/2026-03-31-clustering-analysis-node-design.md) — already in live KG.

## Problem

The KG was rebuilt with `ClusteringAnalysis` as an intermediate node between Publication and GeneCluster. The explorer's 3 cluster tools still reference the old schema:
- 8 references to the removed `Publication_has_gene_cluster` edge in queries_lib.py
- No awareness of `ClusteringAnalysis` nodes
- `source_paper` property referenced but removed from GeneCluster
- `cluster_type` enum values in tool descriptions don't match the new schema
- `ExperimentHasClusteringAnalysis` linkage not surfaced

## Solution

Replace 3 tools with 3 tools: remove `list_gene_clusters`, add `list_clustering_analyses`, update `gene_clusters_by_gene` and `genes_in_cluster`.

## Tool Inventory

**Before (3 tools):**
- `list_gene_clusters` — browse/search GeneCluster nodes (broken edges)
- `gene_clusters_by_gene` — gene → cluster lookup
- `genes_in_cluster` — cluster → gene drill-down

**After (3 tools):**
- `list_clustering_analyses` — **new**, replaces `list_gene_clusters`. Browse/search analyses with inline child clusters. Full-text search on analysis-level index.
- `gene_clusters_by_gene` — **updated**. Adds analysis context to results. Fixes dead edges.
- `genes_in_cluster` — **updated**. Adds `analysis_id` as alternative entry point. Fixes dead edges.

Navigation flow:
```
list_clustering_analyses → genes_in_cluster(analysis_id=...)
                                    ↕
                        gene_clusters_by_gene
```

## Tool 1: `list_clustering_analyses` (new, replaces `list_gene_clusters`)

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `search_text` | str \| None | None | Lucene full-text on `clusteringAnalysisFullText` index (name, treatment, experimental_context) |
| `organism` | str \| None | None | Case-insensitive partial match on `organism_name` |
| `cluster_type` | str \| None | None | Enum: `diel_cycle`, `time_series_dynamics`, `response_pattern` |
| `treatment_type` | list[str] \| None | None | Filter by treatment type(s) |
| `background_factors` | list[str] \| None | None | Filter by background factors |
| `omics_type` | str \| None | None | `MICROARRAY`, `RNASEQ`, `PROTEOMICS` |
| `experiment_ids` | list[str] \| None | None | Filter by linked experiment IDs |
| `publication_doi` | list[str] \| None | None | Filter by publication DOI(s) |
| `analysis_ids` | list[str] \| None | None | Filter to specific ClusteringAnalysis node IDs |
| `summary` | bool | False | Summary fields only, results=[] |
| `verbose` | bool | False | Adds descriptions to inline cluster children + analysis free-text fields |
| `limit` | int | 5 | Max analyses returned |
| `offset` | int | 0 | Pagination offset |

### Summary fields

`total_entries`, `total_matching`, `by_organism`, `by_cluster_type`, `by_treatment_type`, `by_background_factors`, `by_omics_type`, `score_max`, `score_median` (last two only when `search_text` provided)

### Per-result fields

**Compact (always):**
`analysis_id`, `name`, `organism_name`, `cluster_method`, `cluster_type`, `cluster_count`, `total_gene_count`, `treatment_type`, `background_factors`, `omics_type`, `experiment_ids` (list, may be empty), `score` (when searching), `clusters` (inline list)

**Verbose adds:**
`treatment`, `light_condition`, `experimental_context`

### Inline cluster fields

**Compact (always):**
`cluster_id`, `name`, `member_count`

**Verbose adds:**
`functional_description`, `behavioral_description`, `peak_time_hours`, `period_hours`

### to_dataframe

Flattened: one row per analysis × cluster. Analysis fields repeat on each cluster row. Matches the flat long-format pattern used by all other tools.

### Edge traversals

| Filter/field | Edge path |
|---|---|
| `publication_doi` | `(pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)` |
| `experiment_ids` (filter) | `(e:Experiment)-[:ExperimentHasClusteringAnalysis]->(ca)` |
| `experiment_ids` (result field) | OPTIONAL MATCH same edge, collect IDs |
| `clusters` (inline) | `(ca)-[:ClusteringAnalysisHasGeneCluster]->(gc)` |
| `organism` | direct on `ca.organism_name` |

## Tool 2: `gene_clusters_by_gene` (updated)

### Edge fixes

- Publication filter: `Publication_has_gene_cluster` → traverse `PublicationHasClusteringAnalysis` + `ClusteringAnalysisHasGeneCluster`
- Join through `ClusteringAnalysisHasGeneCluster` to get analysis fields

### New parameter

- `analysis_ids` (list[str] | None) — filter by parent ClusteringAnalysis IDs

### Compact result fields

`locus_tag`, `gene_name`, `cluster_id`, `cluster_name`, `cluster_type`, `membership_score`, `analysis_id`, `analysis_name`, `treatment_type`, `background_factors`

### Verbose result fields (adds)

`cluster_method`, `member_count`, `cluster_functional_description`, `cluster_behavioral_description`, `treatment`, `light_condition`, `experimental_context`, `p_value`, `peak_time_hours`, `period_hours`

### Removed

- `source_paper` (dead property on GeneCluster)

### Summary field changes

- Add `by_analysis` breakdown
- `by_publication` edge traversal fixed via ClusteringAnalysis
- `by_cluster_type`, `by_treatment_type`, `by_background_factors` unchanged

## Tool 3: `genes_in_cluster` (updated)

### New parameter

- `analysis_id` (str | None) — alternative to `cluster_ids`. When provided, fetches all clusters from that analysis via `ClusteringAnalysisHasGeneCluster`. Mutually exclusive: must provide `cluster_ids` OR `analysis_id`, not both (raise ValueError if both given).

### Summary field changes

- Add `analysis_name` (informational, when `analysis_id` provided)

### Result field changes

- Rename `function_description` → `gene_function_description` (gene-level)
- Rename `functional_description` → `cluster_functional_description` (cluster-level)
- Rename `behavioral_description` → `cluster_behavioral_description` (cluster-level)
- `gene_summary` unchanged (already prefixed)
- No analysis metadata on result rows

### Compact result fields (unchanged except renames)

`locus_tag`, `gene_name`, `product`, `gene_category`, `organism_name`, `cluster_id`, `cluster_name`, `membership_score`

### Verbose result fields (updated names)

`gene_function_description`, `gene_summary`, `p_value`, `cluster_functional_description`, `cluster_behavioral_description`

## Analysis Utilities (DataFrame Conversion)

### Pattern

The codebase has a `to_dataframe(result)` generic converter in `analysis/frames.py` that handles flat results automatically. Tools with nested output get dedicated converters (e.g. `profile_summary_to_dataframe`, `experiments_to_dataframe`). These are registered in `_DEDICATED_FUNCTIONS` so `to_dataframe()` warns users with the right function name when it drops nested columns.

### New: `analyses_to_dataframe(result)`

`list_clustering_analyses` returns nested `clusters` list per analysis. The generic `to_dataframe()` will drop that column with a warning. Add a dedicated converter:

- **Input:** Raw dict from `list_clustering_analyses()`
- **Output:** One row per analysis × cluster. Analysis fields repeat on each cluster row.
- **Columns:** All analysis scalar fields + `cluster_id`, `cluster_name`, `cluster_member_count` (compact), plus `cluster_functional_description`, `cluster_behavioral_description`, `cluster_peak_time_hours`, `cluster_period_hours` (verbose, when present).
- Analyses with no clusters (shouldn't happen, but defensive) get one row with NaN cluster fields.

### Registration

- Add `"clusters": "analyses_to_dataframe()"` to `_DEDICATED_FUNCTIONS` in `frames.py`
- Export from `analysis/__init__.py`
- Update `to_dataframe.md` MCP resource doc with usage examples

### Existing tools

`gene_clusters_by_gene` and `genes_in_cluster` return flat results — `to_dataframe()` handles them automatically. The renamed fields (e.g. `cluster_functional_description`) are just column name changes, no structural impact.

## Query Layer Changes

### Removed

- `_gene_cluster_where` helper
- `build_list_gene_clusters_summary`
- `build_list_gene_clusters`
- All 8 references to `Publication_has_gene_cluster` edge

### New query builders

- `_clustering_analysis_where` — shared filter helper for organism, cluster_type, treatment_type, background_factors, omics_type on ClusteringAnalysis node
- `build_list_clustering_analyses_summary` — full-text via `clusteringAnalysisFullText` index, aggregation breakdowns
- `build_list_clustering_analyses` — analysis rows + inline clusters via `ClusteringAnalysisHasGeneCluster`, experiment IDs via OPTIONAL MATCH `ExperimentHasClusteringAnalysis`, publication filter via `PublicationHasClusteringAnalysis`

### Updated query builders

- `build_gene_clusters_by_gene_summary` / `build_gene_clusters_by_gene` — join through `ClusteringAnalysisHasGeneCluster` for analysis fields. Publication filter via `PublicationHasClusteringAnalysis`. Add `by_analysis` to summary. Add `analysis_ids` filter.
- `build_genes_in_cluster_summary` / `build_genes_in_cluster` — add `analysis_id` parameter that resolves to cluster IDs via `ClusteringAnalysisHasGeneCluster`. Rename description fields.

### Filtering strategy

Filters on denormalized GeneCluster properties (`organism_name`) can stay on GeneCluster directly. All other categorical filters (`cluster_type`, `treatment_type`, `omics_type`, `background_factors`) and publication/experiment filters go through ClusteringAnalysis node properties. Result fields like `cluster_type` in `gene_clusters_by_gene` compact results are also sourced from the CA node (not GC), since those properties are being removed from GeneCluster.

## KG Changes (request to multiomics_biocypher_kg)

### Remove denormalized properties from GeneCluster

These are now redundant — all cluster queries traverse to ClusteringAnalysis:
- `cluster_method`
- `cluster_type`
- `omics_type`
- `treatment_type`
- `background_factors`
- `treatment`
- `light_condition`
- `experimental_context`

**Keep on GeneCluster:** `organism_name` (matches Gene node pattern, used for organism filter in `genes_in_cluster` without CA join).

### Indexes

- Keep `geneClusterFullText` — no tool searches it, but useful for `run_cypher` ad-hoc queries
- Keep `clusteringAnalysisFullText` — used by `list_clustering_analyses`
- Keep scalar indexes on ClusteringAnalysis — already exist
- No new indexes needed

### Precomputed

No changes. `cluster_count` and `total_gene_count` on ClusteringAnalysis are already computed at build time.

## API Layer Changes

### Removed

- `list_gene_clusters()` function

### New

- `list_clustering_analyses()` — wraps new query builders, Lucene retry logic, `_rename_freq` for summary breakdowns, `to_dataframe` flattening (one row per analysis × cluster)

### Updated

- `gene_clusters_by_gene()` — updated query builder calls, new `analysis_ids` parameter, `by_analysis` in envelope
- `genes_in_cluster()` — new `analysis_id` parameter with mutual exclusion validation, renamed fields in results

## MCP Tool Layer Changes

### Removed

- `list_gene_clusters` tool + all its Pydantic models (`ListGeneClustersResult`, `ListGeneClustersResponse`)

### New

- `list_clustering_analyses` tool + Pydantic response/result models including inline cluster models

### Updated

- `gene_clusters_by_gene` — updated Pydantic models (new fields, removed `source_paper`), new `analysis_ids` parameter
- `genes_in_cluster` — new `analysis_id` parameter, renamed description fields in models

## Scope

### In scope
- All 4 layers: queries_lib.py, api/functions.py, mcp_server/tools.py, tool YAML docs
- Tool YAML docs (`inputs/tools/`): remove `list_gene_clusters.yaml`, add `list_clustering_analyses.yaml`, update `gene_clusters_by_gene.yaml` and `genes_in_cluster.yaml`
- MCP resource docs (`skills/multiomics-kg-guide/references/tools/`): regenerate via `scripts/build_about_content.py` (auto-generated from YAMLs + Pydantic schemas)
- Analysis utility: add `analyses_to_dataframe()` in `analysis/frames.py`, export from `analysis/__init__.py`, manually update `to_dataframe.md` resource doc (hand-written, under `references/analysis/`)
- CLI commands (`cli/main.py`): add `list-clustering-analyses`, `gene-clusters-by-gene`, `genes-in-cluster` subcommands (new — CLI had no cluster commands)
- Unit tests for query builders
- Integration tests (if KG available)
- Regression test fixture updates
- CLAUDE.md tool table update

### Out of scope
- KG-side changes (separate PR to multiomics_biocypher_kg)
