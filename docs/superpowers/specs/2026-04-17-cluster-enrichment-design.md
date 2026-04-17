# `cluster_enrichment` — Design Spec

**Status:** Draft
**Date:** 2026-04-17
**Parent:** [KG Enrichment Surface](2026-04-12-kg-enrichment-surface-design.md)
**Motivated by:** The cluster-membership enrichment workflow documented in `docs://analysis/enrichment` §5 requires manual Python orchestration. This tool automates it as a single MCP call.

## Problem

To ask "what pathways are enriched in each cluster of a clustering analysis?", users today must:

1. Call `list_clustering_analyses` to find an analysis
2. Call `genes_in_cluster(analysis_id=...)` to get all member genes
3. Group genes by cluster, build a shared background (union of all clustered genes)
4. Call `genes_by_ontology` to build TERM2GENE
5. Call `fisher_ora` per cluster
6. Manually attach cluster metadata to results

This is the second most common enrichment pattern after DE-driven ORA (§4). The `pathway_enrichment` MCP tool automates the DE path; `cluster_enrichment` does the same for cluster membership.

## Scope

**In scope:**
- New MCP tool `cluster_enrichment` (L1–L4)
- New `cluster_enrichment_inputs()` helper in `analysis/enrichment.py`
- New L2 API function `cluster_enrichment()` in `api/functions.py`
- New L3 MCP wrapper in `mcp_server/tools.py`
- New YAML (`inputs/tools/cluster_enrichment.yaml`) + generated about-content MD
- Updates to `analysis/enrichment.md` (§5, §14) and `examples/pathway_enrichment.py`
- Full test coverage (unit, contract, integration, regression)

**Out of scope:**
- Signed scores (clusters aren't directional)
- Multi-analysis in one call
- Cherry-picking specific cluster_ids (user picks analysis via `list_clustering_analyses`)
- New L1 query builders (reuses existing `genes_in_cluster` API)

## Tool Surface

```python
cluster_enrichment(
    analysis_id: str,                    # required — single clustering analysis
    organism: str,                       # required — validated against analysis
    ontology: str,                       # required — which ontology to test
    level: int | None = None,            # ontology hierarchy level
    term_ids: list[str] | None = None,   # specific terms (mutually exclusive modes)
    tree: str | None = None,             # BRITE tree filter
    background: str = "cluster_union",   # "cluster_union" | "organism" | list[str]
    min_gene_set_size: int = 5,          # pathway size filter (M in background)
    max_gene_set_size: int | None = 500, # pathway size upper bound
    min_cluster_size: int = 3,           # skip clusters smaller than this
    max_cluster_size: int | None = None, # skip clusters larger than this
    pvalue_cutoff: float = 0.05,         # BH-adjusted p-value threshold
    summary: bool = False,               # summary fields only (results=[])
    verbose: bool = False,               # include secondary fields per row
    limit: int | None = None,            # api/ default; MCP default 5
    offset: int = 0,
)
```

### Key differences from `pathway_enrichment`

| Aspect | `pathway_enrichment` | `cluster_enrichment` |
|---|---|---|
| Input | `experiment_ids` (DE results) | `analysis_id` (cluster membership) |
| Background default | `table_scope` (per-experiment) | `cluster_union` (all clustered genes) |
| Direction | `direction`, `significant_only`, `timepoint_filter` | None — clusters aren't directional |
| Cluster filtering | None | `min_cluster_size`, `max_cluster_size` |
| Signed score | Yes (`signed_enrichment_score`) | No |
| Cluster key format | `"{experiment_id}\|{timepoint}\|{direction}"` | Cluster name from KG |

## Architecture & Data Flow

### `analysis/enrichment.py` — new `cluster_enrichment_inputs()` helper

```python
def cluster_enrichment_inputs(
    analysis_id: str,
    organism: str,
    min_cluster_size: int = 3,
    max_cluster_size: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> EnrichmentInputs:
```

Steps:
1. Call `genes_in_cluster(analysis_id=analysis_id, limit=None, conn=conn)` to get all cluster members
2. Validate organism matches the analysis (populate `not_found` / `not_matched`)
3. Group results by cluster — build `all_gene_sets: {cluster_name → [locus_tags]}`
4. Build `cluster_union` background = union of all member genes across **all** clusters (including those that will be filtered out by size)
5. Apply `min_cluster_size` / `max_cluster_size` filter to decide which clusters become foreground gene sets
6. Record filtered-out clusters in a `clusters_skipped` list with `{cluster_id, cluster_name, member_count, reason}`
7. Build `cluster_metadata` from cluster-level fields (cluster_id, cluster_name, cluster_type, member_count, functional_description, expression_dynamics, temporal_pattern)
8. Return `EnrichmentInputs` with:
   - `gene_sets`: only size-passing clusters
   - `background`: `{cluster_name → list(cluster_union)}` for all size-passing clusters
   - `cluster_metadata`: per-cluster metadata
   - `not_found`: `[analysis_id]` if analysis doesn't exist
   - `not_matched`: `[analysis_id]` if analysis belongs to a different organism
   - `no_expression`: always empty (DE-specific bucket, unused here)

The `EnrichmentInputs` model is reused as-is. DE-specific buckets stay empty for cluster inputs — no model changes needed.

### `api/functions.py` — new `cluster_enrichment()` L2 function

```python
def cluster_enrichment(
    analysis_id: str,
    organism: str,
    ontology: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    tree: str | None = None,
    background: str | list[str] = "cluster_union",
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    min_cluster_size: int = 3,
    max_cluster_size: int | None = None,
    pvalue_cutoff: float = 0.05,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
```

Orchestration:
1. **Validate inputs** — ontology valid, at least one of level/term_ids, background mode valid, pvalue range, min/max cluster size consistency
2. **Build inputs** — call `cluster_enrichment_inputs(analysis_id, organism, min_cluster_size, max_cluster_size, conn=conn)`
3. **Early return** if `not_found` or `not_matched` or no gene_sets (all clusters filtered out)
4. **Resolve background mode:**
   - `cluster_union`: already built by the helper (per-cluster dicts all pointing to the same union)
   - `organism`: query all genes for the organism, broadcast to all clusters
   - explicit `list[str]`: broadcast to all clusters
5. **Build TERM2GENE** via `genes_by_ontology(ontology, organism, level, term_ids, tree, ...)`
6. **Run `fisher_ora()`** with gene_sets, background, term2gene, min/max_gene_set_size
7. **Apply `pvalue_cutoff`** filter on `p_adjust`
8. **Attach cluster metadata** from `inputs.cluster_metadata` to each result row
9. **Fetch analysis-level metadata** via `list_clustering_analyses(analysis_ids=[analysis_id], limit=1, conn=conn)` — sources analysis_name, cluster_type, cluster_method, treatment_type, background_factors, growth_phases, omics_type, experiment_ids. This is a separate call because `genes_in_cluster` returns cluster-level fields but not analysis-level metadata
10. **Build summary fields** (when `summary=True` or always as envelope)
11. **Frame response envelope** with standard `returned`, `truncated`, `total_matching`, validation buckets

### `mcp_server/tools.py` — thin L3 wrapper

Following the registration pattern from layer-rules:
- Pydantic `ClusterEnrichmentResult` and `ClusterEnrichmentResponse` models
- `async def cluster_enrichment(ctx, ...)` with MCP default `limit=5`
- Calls `api.cluster_enrichment()`
- Emits `ctx.warning()` for `not_found`, `not_matched`, `clusters_skipped`
- Tags: `{"enrichment", "clustering"}`
- `annotations={"readOnlyHint": True}`

### No new L1 query builders

All KG access goes through existing API functions:
- `genes_in_cluster(analysis_id=...)` for cluster members
- `genes_by_ontology(...)` for TERM2GENE
- `list_clustering_analyses(analysis_ids=[...])` for analysis metadata (if needed)
- Organism gene list query for `background="organism"` mode

## Response Schema

### Detail rows

One row per (cluster × term) passing `pvalue_cutoff`. compareCluster-compatible:

| Column | Source | Always |
|---|---|---|
| `cluster` | cluster name from KG | yes |
| `cluster_id` | cluster ID from KG | yes |
| `term_id` | from TERM2GENE | yes |
| `term_name` | from TERM2GENE | yes |
| `level` | from TERM2GENE | yes |
| `gene_ratio` | `"k/n"` string | yes |
| `gene_ratio_numeric` | float | yes |
| `bg_ratio` | `"M/N"` string | yes |
| `bg_ratio_numeric` | float | yes |
| `rich_factor` | k/M | yes |
| `fold_enrichment` | (k/n)/(M/N) | yes |
| `pvalue` | Fisher exact | yes |
| `p_adjust` | BH-corrected | yes |
| `count` | k (hits) | yes |
| `bg_count` | M (pathway size in background) | yes |
No `signed_score`, no `direction`, no `gene_ids`.

### Verbose additions per row

| Column | Source |
|---|---|
| `cluster_functional_description` | GeneCluster node |
| `cluster_expression_dynamics` | GeneCluster node |
| `cluster_temporal_pattern` | GeneCluster node |
| `cluster_member_count` | GeneCluster node |

### Envelope (always returned)

| Field | Meaning |
|---|---|
| `analysis_id` | Input analysis ID |
| `analysis_name` | ClusteringAnalysis name |
| `organism_name` | Validated organism |
| `cluster_method` | From ClusteringAnalysis |
| `cluster_type` | From ClusteringAnalysis |
| `omics_type` | From ClusteringAnalysis |
| `treatment_type` | From ClusteringAnalysis (list) |
| `background_factors` | From ClusteringAnalysis (list) |
| `growth_phases` | From ClusteringAnalysis (list) |
| `experiment_ids` | Linked experiment IDs |
| `ontology` | Tested ontology |
| `level` | Tested level |
| `tree` | BRITE tree (if applicable) |
| `background_mode` | Which mode was used |
| `background_size` | N (genes in background) |
| `total_matching` | Pre-pagination row count |
| `returned` | Rows in this response |
| `truncated` | total_matching > returned |
| `not_found` | analysis_id absent from KG |
| `not_matched` | analysis_id belongs to different organism |
| `clusters_skipped` | Clusters filtered by size: `[{cluster_id, cluster_name, member_count, reason}]` |

### Summary fields (when `summary=True` or as envelope enrichment)

| Field | Meaning |
|---|---|
| `by_cluster` | Per-cluster: cluster_id, cluster_name, member_count, significant_terms count |
| `by_term` | Top terms ranked by number of clusters they appear in |
| `clusters_tested` | Number of clusters passing size filter |
| `total_terms_tested` | Unique terms in TERM2GENE |
| `n_significant` | Rows with p_adjust < pvalue_cutoff |

## Background Modes

| Mode | Background set | When to use |
|---|---|---|
| `cluster_union` (default) | Union of all member genes across all clusters in the analysis, **including** clusters filtered out by size | Clustering was done on a defined gene set; this is the measured universe |
| `organism` | All genes in the organism | Clustering covered the whole genome, or you want genome-wide context |
| `list[str]` | Explicit locus_tag list, broadcast to all clusters | Custom universe from external analysis |

**Critical:** `cluster_union` includes genes from size-filtered clusters. The size filter determines which clusters are tested as foregrounds, not which genes count as background.

## Testing

### Unit tests (`tests/unit/`)

**`test_api_functions.py`:**
- `cluster_enrichment_inputs()`: mock `genes_in_cluster` API call
  - Verify gene_sets built correctly (grouped by cluster)
  - Verify `cluster_union` background includes all genes (including from size-filtered clusters)
  - Verify `min_cluster_size` / `max_cluster_size` filtering
  - Verify `clusters_skipped` bucket populated with correct reasons
  - Verify `not_found` when analysis_id doesn't exist
  - Verify `not_matched` when organism doesn't match analysis
- `cluster_enrichment()` L2: mock inputs helper + `genes_by_ontology` + `fisher_ora`
  - Verify orchestration wiring
  - Verify `pvalue_cutoff` filtering
  - Verify response envelope fields present
  - Verify background mode switching (`cluster_union`, `organism`, explicit list)
  - Verify early return on empty gene_sets

**`test_tool_wrappers.py`:**
- Add `"cluster_enrichment"` to `EXPECTED_TOOLS`
- Pydantic response model validation
- `ToolError` on invalid inputs
- Warning emission for validation buckets

**`test_about_content.py`:**
- About-file consistency check (auto-covered by existing parametrized test once YAML + MD exist)

### Contract tests (`tests/integration/test_api_contract.py`)

- `TestClusterEnrichmentContract`: verify return dict shape and keys against live KG
  - Pick a known analysis_id, run with small ontology
  - Assert envelope keys present
  - Assert result row keys match schema

### Integration tests (`tests/integration/`)

**`test_mcp_tools.py`:**
- Smoke test: call via MCP, verify non-error response

**`test_tool_correctness_kg.py`:**
- End-to-end: known analysis_id + small ontology → non-empty results with expected columns
- Background modes: `cluster_union` vs `organism` produce different `background_size` values
- Size filtering: clusters below `min_cluster_size` appear in `clusters_skipped`, not in results
- Empty result: analysis with no clusters matching size filter → empty results, populated `clusters_skipped`

### CyVer validation (`tests/integration/test_cyver_queries.py`)

No new builders to add (reuses existing `genes_in_cluster` builders).

### Regression tests (`tests/regression/`)

Not applicable for this tool — output depends on Fisher exact test results, not deterministic Cypher output. The unit tests with mocked `fisher_ora` cover correctness.

## Deliverables

| File | Change |
|---|---|
| `multiomics_explorer/analysis/enrichment.py` | New `cluster_enrichment_inputs()` function |
| `multiomics_explorer/api/functions.py` | New `cluster_enrichment()` L2 function |
| `multiomics_explorer/api/__init__.py` | Export `cluster_enrichment` |
| `multiomics_explorer/__init__.py` | Re-export `cluster_enrichment` |
| `multiomics_explorer/mcp_server/tools.py` | New L3 wrapper + Pydantic models |
| `multiomics_explorer/inputs/tools/cluster_enrichment.yaml` | Human-authored about content |
| `multiomics_explorer/skills/multiomics-kg-guide/references/tools/cluster_enrichment.md` | Auto-generated via `build_about_content.py` |
| `multiomics_explorer/analysis/enrichment.md` | Update §5 (reference new tool), update §14 (mention alongside `pathway_enrichment`) |
| `examples/pathway_enrichment.py` | Update `scenario_3_cluster` comment to note MCP alternative |
| `tests/unit/test_api_functions.py` | Unit tests for helper + L2 |
| `tests/unit/test_tool_wrappers.py` | Add to `EXPECTED_TOOLS`, wrapper tests |
| `tests/integration/test_api_contract.py` | Contract test class |
| `tests/integration/test_mcp_tools.py` | Smoke test |
| `tests/integration/test_tool_correctness_kg.py` | Correctness tests |

## Alignment with enrichment.md

This tool codifies the manual workflow documented in `docs://analysis/enrichment` §5:

- §5 pattern: `genes_in_cluster(analysis_id=...)` → group by cluster → union background → `fisher_ora`
- §9 guidance: "the background is the clustering universe (all genes that were fed into the clustering algorithm, not all genes in the genome)" → `cluster_union` default
- §14 currently says "for cluster-membership enrichment, use the Python `fisher_ora` primitive" → update to reference `cluster_enrichment` MCP tool as the convenience alternative

## References

- Parent spec: [KG Enrichment Surface](2026-04-12-kg-enrichment-surface-design.md)
- Pathway enrichment spec: [pathway_enrichment](2026-04-12-pathway-enrichment-design.md)
- Clustering analysis spec: [clustering analysis tools](2026-04-03-clustering-analysis-mcp-tools-design.md)
- Enrichment methodology: `docs://analysis/enrichment`
- Example script: `examples/pathway_enrichment.py` scenario_3
