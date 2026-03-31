# Gene Cluster MCP Tools — Design Spec

## Summary

Three MCP tools for querying GeneCluster nodes in the knowledge graph. Enables discovery by text search, gene-centric cluster lookup, and drill-down into cluster membership. Depends on GeneCluster nodes being present in the KG (built by the `multiomics_biocypher_kg` repo).

## Motivation

From [gaps_and_friction.md](../../../analyses/) (nitrogen stress MED4 analysis):
> No clustering/co-expression — Gene co-expression clusters and dynamic pattern classifications from the time courses. Would enable "which cluster does this gene belong to?" queries.

The KG repo is adding GeneCluster nodes (Phase 1: ~34 clusters from Tolonen 2006 + Zinser 2009, growing to hundreds across 7+ papers). This spec covers the explorer-side MCP tools to query them.

## Graph Model (reference)

Built by `multiomics_biocypher_kg` — see `docs/superpowers/specs/2026-03-31-gene-cluster-nodes-design.md` in that repo.

### Node: GeneCluster

ID format: `cluster:{doi_short}:{cluster_id}`

Key properties: `name`, `source_paper`, `organism_name`, `cluster_method`, `cluster_type` (enum: "diel_periodicity" | "stress_response" | "expression_level"), `treatment_type` (string[]), `treatment`, `omics_type`, `light_condition`, `member_count`, `functional_description`, `behavioral_description`, `peak_time_hours`, `period_hours`, `experimental_context`.

### Edges

| Edge | Direction | Properties |
|---|---|---|
| `Publication_has_gene_cluster` | Publication → GeneCluster | (none) |
| `Gene_in_gene_cluster` | GeneCluster → Gene | `membership_score` (float, nullable — absent for K-means, present for Mfuzz/soft clustering), `p_value` (float, nullable — absent for most methods). Currently only `id` property exists in KG; edge score properties will appear with future papers (e.g., Zinser 2009 Mfuzz). |
| `Genecluster_belongs_to_organism` | GeneCluster → OrganismTaxon | (none) |

### Indexes

- Scalar: `gene_cluster_organism_idx`, `gene_cluster_treatment_type_idx`, `gene_cluster_type_idx`
- Full-text: `geneClusterFullText` on `name`, `functional_description`, `behavioral_description`, `experimental_context`

## Tool Overview

| Tool | Entry point | Pattern |
|---|---|---|
| `list_gene_clusters` | Text search + filters | Like `genes_by_function` (optional Lucene search) + `list_experiments` (rich filters) |
| `gene_clusters_by_gene` | Batch locus_tags | Like `gene_ontology_terms` (batch genes → annotations) |
| `genes_in_cluster` | Batch cluster_ids | Like `genes_by_homolog_group` (group IDs → member genes) |

All three tools enforce single organism.

## Tool 1: `list_gene_clusters`

Browse, search, and filter gene clusters. Primary discovery tool.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `search_text` | str \| None | None | Lucene full-text query over `name`, `functional_description`, `behavioral_description`, `experimental_context`. When provided, results ranked by score. |
| `organism` | str \| None | None | Filter by organism name (case-insensitive partial match) |
| `cluster_type` | str \| None | None | Filter: "diel_periodicity", "stress_response", "expression_level" |
| `treatment_type` | list[str] \| None | None | Filter by treatment type(s) |
| `omics_type` | str \| None | None | Filter: "MICROARRAY", "RNASEQ", "PROTEOMICS" |
| `publication_doi` | list[str] \| None | None | Filter by publication DOI(s) |
| `summary` | bool | False | When true, return only summary fields (no result rows) |
| `verbose` | bool | False | Include extended cluster properties |
| `limit` | int | 5 | Max results (ge=1) |
| `offset` | int | 0 | Skip results (ge=0) |

### Summary fields (always returned)

- `total_entries` — total GeneCluster nodes in KG
- `total_matching` — after filters
- `by_organism` — list of `{organism_name, count}`
- `by_cluster_type` — list of `{cluster_type, count}`
- `by_treatment_type` — list of `{treatment_type, count}`
- `by_omics_type` — list of `{omics_type, count}`
- `by_publication` — list of `{publication_doi, source_paper, count}`
- `score_max`, `score_median` — when `search_text` provided
- `returned`, `offset`, `truncated`

### Result rows (compact)

| Column | Source |
|---|---|
| `cluster_id` | GeneCluster.id |
| `name` | GeneCluster.name |
| `organism_name` | GeneCluster.organism_name |
| `cluster_type` | GeneCluster.cluster_type |
| `treatment_type` | GeneCluster.treatment_type |
| `member_count` | GeneCluster.member_count |
| `source_paper` | GeneCluster.source_paper |
| `score` | full-text score (only when `search_text` provided) |

### Result rows (verbose adds)

| Column | Source |
|---|---|
| `functional_description` | GeneCluster.functional_description |
| `behavioral_description` | GeneCluster.behavioral_description |
| `cluster_method` | GeneCluster.cluster_method |
| `treatment` | GeneCluster.treatment |
| `light_condition` | GeneCluster.light_condition |
| `experimental_context` | GeneCluster.experimental_context |
| `peak_time_hours` | GeneCluster.peak_time_hours |
| `period_hours` | GeneCluster.period_hours |
| `publication_doi` | via Publication_has_gene_cluster edge |

## Tool 2: `gene_clusters_by_gene`

Gene-centric: "what clusters are these genes in?" Single organism enforced.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `locus_tags` | list[str] | required | Gene locus tags |
| `organism` | str \| None | None | Organism name (case-insensitive partial match); inferred from genes if omitted. Single organism enforced. |
| `cluster_type` | str \| None | None | Filter by cluster type |
| `treatment_type` | list[str] \| None | None | Filter by treatment type(s) |
| `publication_doi` | list[str] \| None | None | Filter by publication DOI(s) |
| `summary` | bool | False | When true, return only summary fields (no result rows) |
| `verbose` | bool | False | Include extended cluster and edge properties |
| `limit` | int | 5 | Max results (ge=1) |
| `offset` | int | 0 | Skip results (ge=0) |

### Summary fields (always returned)

- `total_matching` — total gene × cluster rows after filters
- `total_clusters` — distinct clusters matched
- `genes_with_clusters` — count of input genes with at least one cluster membership
- `genes_without_clusters` — count of input genes with zero memberships after filters
- `not_found` — list of locus_tags not in KG (always returned, even in summary mode)
- `not_matched` — list of locus_tags in KG but no cluster memberships after filters (always returned)
- `by_cluster_type` — list of `{cluster_type, count}`
- `by_treatment_type` — list of `{treatment_type, count}`
- `by_publication` — list of `{publication_doi, source_paper, count}`
- `returned`, `offset`, `truncated`

### Result rows (compact)

One row per gene × cluster.

| Column | Source |
|---|---|
| `locus_tag` | Gene.locus_tag |
| `gene_name` | Gene.gene_name |
| `cluster_id` | GeneCluster.id |
| `cluster_name` | GeneCluster.name |
| `cluster_type` | GeneCluster.cluster_type |
| `membership_score` | Gene_in_gene_cluster.membership_score |
| `member_count` | GeneCluster.member_count |

### Result rows (verbose adds)

| Column | Source |
|---|---|
| `functional_description` | GeneCluster.functional_description (cluster-level) |
| `behavioral_description` | GeneCluster.behavioral_description (cluster-level) |
| `treatment_type` | GeneCluster.treatment_type |
| `treatment` | GeneCluster.treatment |
| `source_paper` | GeneCluster.source_paper |
| `p_value` | Gene_in_gene_cluster.p_value |

## Tool 3: `genes_in_cluster`

Cluster IDs → member genes. The drill-down tool. Single organism enforced.

### Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| `cluster_ids` | list[str] | required | GeneCluster node IDs (from tool 1 or 2) |
| `organism` | str \| None | None | Filter member genes by organism (case-insensitive partial match). Single organism enforced. |
| `summary` | bool | False | When true, return only summary fields (no result rows) |
| `verbose` | bool | False | Include extended gene and cluster properties |
| `limit` | int | 5 | Max results (ge=1) |
| `offset` | int | 0 | Skip results (ge=0) |

### Summary fields (always returned)

- `total_matching` — total gene × cluster rows
- `by_organism` — list of `{organism_name, count}`
- `by_cluster` — list of `{cluster_id, cluster_name, count}`
- `top_categories` — top 5 gene_category values by frequency
- `genes_per_cluster_max` — max member count across requested clusters
- `genes_per_cluster_median` — median member count
- `not_found_clusters` — list of cluster_ids not in KG
- `not_matched_clusters` — list of cluster_ids in KG but no members after filters
- `not_matched_organism` — organism provided but doesn't match any cluster's organism
- `returned`, `offset`, `truncated`

### Result rows (compact)

One row per gene × cluster.

| Column | Source |
|---|---|
| `locus_tag` | Gene.locus_tag |
| `gene_name` | Gene.gene_name |
| `product` | Gene.product |
| `gene_category` | Gene.gene_category |
| `organism_name` | Gene.organism_name |
| `cluster_id` | GeneCluster.id |
| `cluster_name` | GeneCluster.name |
| `membership_score` | Gene_in_gene_cluster.membership_score |

### Result rows (verbose adds)

| Column | Source |
|---|---|
| `function_description` | Gene.function_description (gene-level) |
| `gene_summary` | Gene.gene_summary (gene-level) |
| `p_value` | Gene_in_gene_cluster.p_value (edge-level) |
| `functional_description` | GeneCluster.functional_description (cluster-level) |
| `behavioral_description` | GeneCluster.behavioral_description (cluster-level) |

## Implementation Layers

Following existing architecture (`/layer-rules`):

### Query builders (`kg/queries_lib.py`)

- `build_list_gene_clusters()` — Cypher with optional full-text index call, WHERE clause filters, RETURN compact/verbose columns
- `build_list_gene_clusters_summary()` — summary-only variant with aggregation
- `build_gene_clusters_by_gene()` — Gene ← Gene_in_gene_cluster → GeneCluster traversal
- `build_gene_clusters_by_gene_summary()` — summary with not_found/not_matched detection
- `build_genes_in_cluster()` — GeneCluster → Gene_in_gene_cluster → Gene traversal
- `build_genes_in_cluster_summary()` — summary with cluster-level stats

### API functions (`api/functions.py`)

- `list_gene_clusters()` — calls builder, assembles envelope with breakdowns
- `gene_clusters_by_gene()` — single-organism enforcement, batch diagnostics
- `genes_in_cluster()` — single-organism enforcement, batch diagnostics

### MCP tool wrappers (`mcp_server/tools.py`)

- `list_gene_clusters()` — Pydantic response model, parameter validation
- `gene_clusters_by_gene()` — Pydantic response model, parameter validation
- `genes_in_cluster()` — Pydantic response model, parameter validation

### About content (`mcp_server/about/`)

- `list_gene_clusters.md` — usage guide with examples
- `gene_clusters_by_gene.md` — usage guide with examples
- `genes_in_cluster.md` — usage guide with examples

## Testing

### Unit tests (no Neo4j)

- `test_query_builders.py` — Cypher structure, params, verbose/compact columns for all 6 builders
- `test_api_functions.py` — API logic with mocked conn: envelope shape, batch diagnostics, single-organism enforcement
- `test_tool_wrappers.py` — Pydantic model validation, ToolError on bad input
- `test_about_content.py` — about-file consistency with Pydantic schemas

### Integration tests (Neo4j required)

- `test_api_contract.py` — return-type contracts for all 3 API functions
- `test_cyver_queries.py` — CyVer schema validation of all 6 builders (auto-discovered)
- `test_regression.py` — golden-file comparison for stable outputs

## Dependencies

- GeneCluster nodes in KG (built by `multiomics_biocypher_kg` repo, Phase 1+)
- Full-text index `geneClusterFullText` (created by post-import script)
- Scalar indexes on `organism_name`, `treatment_type`, `cluster_type`

## Verification Data (live KG as of 2026-03-31)

16 GeneCluster nodes from Tolonen 2006 (DOI: 10.1038/msb4100087):
- 9 MED4 clusters (5–124 members), 7 MIT9313 clusters (6–128 members)
- All `stress_response` type, `nitrogen_stress` treatment
- All linked via `Publication_has_gene_cluster` to DOI 10.1038/msb4100087
- All linked via `Genecluster_belongs_to_organism` to organism nodes
- `Gene_in_gene_cluster` edges have no `membership_score` or `p_value` (K-means, no fuzzy scores)
- Full-text index `geneClusterFullText` present on `name`, `functional_description`, `behavioral_description`, `experimental_context`

Known test genes and clusters for integration tests:
- `PMM0370` (urtA) → `cluster:msb4100087:med4:up_n_transport` (5 members)
- `PMM0297` → `cluster:msb4100087:med4:down_translation` (124 members)
- `PMT0992` → `cluster:msb4100087:mit9313:up_n_transport` (6 members)

## Not in Scope

- Analysis utilities for clusters (e.g., cluster overlap matrices) — separate spec
- Cluster enrichment edges (future KG work)
- Computing new clusters from expression data
- Cross-organism cluster comparison tools
