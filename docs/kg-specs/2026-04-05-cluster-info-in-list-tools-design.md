# Add Cluster Analysis Info to List Tools

## Goal

Surface clustering analysis summary data in `list_publications`, `list_organisms`, and `list_experiments` so researchers see cluster coverage without needing to call `list_clustering_analyses` separately. Mirrors how expression data (experiment counts, treatment types, omics types) is already surfaced in these tools.

## What changes for the researcher

Before: a researcher calling `list_publications()` sees experiment counts and treatment types but has no idea whether clustering analyses exist for a study. They must separately call `list_clustering_analyses` to discover this.

After: each publication, organism, and experiment result includes `clustering_analysis_count` and `cluster_types` (always), plus `cluster_count` (verbose). Top-level summaries include a `by_cluster_type` breakdown.

## New fields

### Per-result fields

| Field | Type | Mode | Description |
|---|---|---|---|
| `clustering_analysis_count` | int | always | Number of linked ClusteringAnalysis nodes |
| `cluster_types` | list[str] | always | Distinct cluster types (e.g. `["response_pattern", "diel_expression_pattern"]`) |
| `cluster_count` | int | verbose | Total GeneCluster nodes across linked analyses |

Added to all three tools: `list_publications`, `list_organisms`, `list_experiments`.

**Dropped from original design:** `clustered_gene_count` was removed. KG validation showed that `sum(CA.total_gene_count)` double-counts genes that appear in multiple analyses — for MED4, the sum is 4265 but only 1953 distinct genes exist across its 4 analyses. Computing distinct genes at materialization time would require traversing `Gene_in_gene_cluster` edges for every node, which is expensive and fragile. The `cluster_count` field (sum of `CA.cluster_count`) does not suffer from this problem since clusters are unique per analysis.

### Top-level summary breakdown

| Field | Type | Description |
|---|---|---|
| `by_cluster_type` | list[{cluster_type, count}] | Count of matching results (publications/organisms/experiments) that have at least one clustering analysis of that type. Same semantics as `by_treatment_type`. |

Added to all three tools. Same pattern as existing `by_treatment_type`, `by_omics_type`.

## Approach: materialize on nodes

Cluster summary fields are materialized as properties on `OrganismTaxon`, `Publication`, and `Experiment` nodes during KG build, matching the existing pattern for `experiment_count`, `treatment_types`, `omics_types`, etc.

### Graph edges used (verified against live KG 2026-04-05)

| Node | Edge to ClusteringAnalysis | Direction | Verified |
|---|---|---|---|
| `OrganismTaxon` | `ClusteringanalysisBelongsToOrganism` | CA --> Organism | yes |
| `Publication` | `PublicationHasClusteringAnalysis` | Pub --> CA | yes |
| `Experiment` | `ExperimentHasClusteringAnalysis` | Exp --> CA | yes |

All are direct one-hop edges (no chaining through intermediate nodes).

### ClusteringAnalysis properties used (verified against live KG 2026-04-05)

| Property | Type | Purpose |
|---|---|---|
| `cluster_type` | string | For `cluster_types` list and `by_cluster_type` breakdown |
| `cluster_count` | int | Summed for `cluster_count` (verbose) |

### Computation

For each node, aggregate over its linked ClusteringAnalysis nodes:

- `clustering_analysis_count` = count of linked CAs
- `cluster_types` = distinct `CA.cluster_type` values
- `cluster_count` = sum of `CA.cluster_count` across linked CAs

Nodes with no linked CAs get `clustering_analysis_count=0`, `cluster_types=[]`, `cluster_count=0`.

## Pre-work: Validate Cypher against live KG

Run these read-only queries to confirm edge directions, property names, and expected counts before writing any code. **Status: validated 2026-04-05.**

### OrganismTaxon validation
```cypher
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (ca:ClusteringAnalysis)-[:ClusteringanalysisBelongsToOrganism]->(o)
WITH o.organism_name AS organism,
     count(ca) AS ca_count,
     collect(DISTINCT ca.cluster_type) AS ctypes,
     sum(coalesce(ca.cluster_count, 0)) AS total_clusters
RETURN organism, ca_count, ctypes, total_clusters
ORDER BY ca_count DESC
```

Expected: 7 organisms with ca_count > 0 (MED4: 4, NATL2A: 4, MruberA: 2, BP1: 2, MIT1002: 1, MIT9313: 1, MIT9301: 1). All others: 0.

### Publication validation
```cypher
MATCH (p:Publication)
OPTIONAL MATCH (p)-[:PublicationHasClusteringAnalysis]->(ca:ClusteringAnalysis)
WITH p.doi AS doi,
     count(ca) AS ca_count,
     collect(DISTINCT ca.cluster_type) AS ctypes,
     sum(coalesce(ca.cluster_count, 0)) AS total_clusters
RETURN doi, ca_count, ctypes, total_clusters
ORDER BY ca_count DESC
```

Expected: 8 publications with ca_count > 0 (top: mSystems.00181-16 with 4 CAs). Remaining publications: 0.

### Experiment validation
```cypher
MATCH (e:Experiment)
OPTIONAL MATCH (e)-[:ExperimentHasClusteringAnalysis]->(ca:ClusteringAnalysis)
WITH e.id AS eid, e.organism_name AS org,
     count(ca) AS ca_count,
     collect(DISTINCT ca.cluster_type) AS ctypes,
     sum(coalesce(ca.cluster_count, 0)) AS total_clusters
WHERE ca_count > 0
RETURN eid, org, ca_count, ctypes, total_clusters
ORDER BY ca_count DESC
```

Expected: 11 experiments with CAs. Top: BP-1 coculture experiment with 4 CAs, 20 clusters.

### Cross-check with list_clustering_analyses
Verify that 15 total CAs exist across 7 cluster types: response_pattern (7), periodicity_classification (2), diel_expression_pattern (2), expression_classification (1), diel_cycling (1), expression_pattern (1), expression_level (1).

## Pre-work: KG enrichment (biocypher_kg)

Add a post-import enrichment step (or extend the existing one that computes `experiment_count`, `treatment_types`, etc.) to materialize three properties on `OrganismTaxon`, `Publication`, and `Experiment` nodes.

Example Cypher for OrganismTaxon:
```cypher
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (ca:ClusteringAnalysis)-[:ClusteringanalysisBelongsToOrganism]->(o)
WITH o,
     count(ca) AS ca_count,
     collect(DISTINCT ca.cluster_type) AS ctypes,
     sum(coalesce(ca.cluster_count, 0)) AS total_clusters
SET o.clustering_analysis_count = ca_count,
    o.cluster_types = ctypes,
    o.cluster_count = total_clusters
```

Similar for Publication (via `PublicationHasClusteringAnalysis`) and Experiment (via `ExperimentHasClusteringAnalysis`).

Create a spec/task doc in biocypher_kg describing the new materialized properties and the enrichment Cypher. This is the handoff for the KG rebuild — implementation of Layers 1-4 can proceed with unit tests, but integration tests wait for the KG update.

## Layer 1: Query builders (`kg/queries_lib.py`)

### Detail queries

All three tools: add three new properties to the RETURN clause. `cluster_count` is always returned from Cypher; verbose gating happens via the existing `verbose_cols` pattern.

**`build_list_publications`** (~line 586): Add to both search and non-search RETURN clauses:
```python
"       p.clustering_analysis_count AS clustering_analysis_count,\n"
"       coalesce(p.cluster_types, []) AS cluster_types,\n"
```
Add to verbose_cols:
```python
",\n       p.cluster_count AS cluster_count"
```

**`build_list_organisms`** (~line 712): Same pattern — add always-on fields to RETURN, verbose field to `verbose_cols`.

**`build_list_experiments`** (~line 827): Same pattern for detail query RETURN clause.

### Summary queries

**`build_list_publications_summary`** (~line 661): No Cypher changes — publications compute breakdowns in Python.

**`build_list_experiments_summary`** (~line 934): Add `cluster_types` collection and `apoc.coll.frequencies()` call, matching the existing pattern for `by_treatment_type`:
```cypher
reduce(ct = [], x IN collect(e.cluster_types) | ct + coalesce(x, [])) AS cts,
...
apoc.coll.frequencies(cts) AS by_cluster_type
```

**`build_list_organisms`**: No separate summary query exists (single query returns all). Python-side breakdown.

## Layer 2: API functions (`api/functions.py`)

**`list_publications`** (~line 551): Add `by_cluster_type` breakdown using the existing Python-side pattern (iterate results, accumulate `cluster_types` counts). Add to response dict alongside `by_omics_type`. Gate `cluster_count` behind `verbose` by popping it from non-verbose results.

**`list_organisms`** (~line 521): Add `by_cluster_type` Python-side breakdown (same accumulation pattern). Gate `cluster_count` behind `verbose`.

**`list_experiments`** (~line 639): Add `by_cluster_type` to summary dict via `_rename_freq()` (from Cypher's `apoc.coll.frequencies` output). Gate `cluster_count` behind `verbose` in detail rows.

## Layer 3: MCP wrappers (`mcp_server/tools.py`)

Update Pydantic response models for all three tools to include:
- `clustering_analysis_count: int` (always, in result items)
- `cluster_types: list[str]` (always, in result items)
- `cluster_count: int` (verbose, in result items)
- `by_cluster_type: list[dict]` (in top-level summary)

Update tool docstrings to mention clustering info availability.

## Layer 4: Skills — About YAML + regenerate

**Input YAML updates** (`inputs/tools/`):

`list_publications.yaml`:
- Add `cluster_count` to `verbose_fields`
- Update example response to include `clustering_analysis_count`, `cluster_types`
- Add chaining: `"list_publications -> list_clustering_analyses(publication_doi=[...])"`

`list_organisms.yaml`:
- Add `cluster_count` to `verbose_fields`
- Update example response to include `clustering_analysis_count`, `cluster_types`
- Add chaining: `"list_organisms -> list_clustering_analyses(organism=...)"`

`list_experiments.yaml`:
- Add `cluster_count` to `verbose_fields`
- Update example response to include `clustering_analysis_count`, `cluster_types`
- Add chaining: `"list_experiments -> list_clustering_analyses(experiment_ids=[...])"`

**Regenerate:**
```bash
cd /home/osnat/github/multiomics_explorer
uv run python scripts/build_about_content.py list_publications list_organisms list_experiments
```

## Tests

### Unit tests (`tests/unit/test_api_functions.py`)

All three list tool test classes use inline mock data (no external fixtures). For each:

1. **Add cluster fields to mock data**: Include `clustering_analysis_count`, `cluster_types`, `cluster_count` in mock rows. For list_experiments, update both `_summary_result()` and `_detail_row()` helpers.

2. **Test verbose gating**: Assert `cluster_count` present when `verbose=True`, absent when `verbose=False`. Follow existing pattern (e.g. `test_verbose_adds_abstract` for publications).

3. **Test `by_cluster_type` in summary**: Assert breakdown key present in response dict, sorted by count descending.

### Integration tests (`tests/integration/test_api_contract.py`)

1. **Verify materialized properties exist**: Assert `clustering_analysis_count` and `cluster_types` keys present in results (requires KG rebuild with materialized properties — will fail until pre-work is complete).

2. **Verify verbose adds `cluster_count`**: Extend existing `test_verbose_adds_fields` tests.

3. **Verify `by_cluster_type` in response envelope**: Extend existing `test_returns_dict_envelope` tests.

Note: Integration tests will fail until the KG is rebuilt with the new materialized properties (pre-work). Unit tests can be written immediately.

## Documentation (multiomics_research)

Update `docs/superpowers/specs/2026-03-31-gene-cluster-tools-what-changed.md` to note the new fields on list tools.

## Implementation order

1. **Pre-work: KG validation** — Already validated (see above)
2. **Pre-work: KG spec doc** — Handoff to biocypher_kg
3. **Pre-work: KG enrichment** — biocypher_kg rebuild
4. **Layer 1** — Query builders (queries_lib.py)
5. **Layer 2** — API functions (functions.py)
6. **Layer 3** — MCP wrappers (tools.py)
7. **Tests** — Unit tests can run immediately; integration tests after KG rebuild
8. **Layer 4** — About YAML + regenerate
9. **Documentation** — multiomics_research update

Layers 1-4 can be developed in parallel with the KG rebuild, using unit tests with mock data. Integration tests gate on KG rebuild completion.

## Current KG data (validated 2026-04-05)

15 clustering analyses across 7 organisms, 8 publications, 11 experiments.

### By organism
| Organism | CAs | Cluster types | Total clusters |
|---|---|---|---|
| MED4 | 4 | response_pattern, diel_cycling, expression_level | 35 |
| NATL2A | 4 | diel_expression_pattern, expression_classification, periodicity_classification | 45 |
| MruberA | 2 | response_pattern | 10 |
| BP1 | 2 | response_pattern | 10 |
| MIT1002 | 1 | periodicity_classification | 3 |
| MIT9313 | 1 | response_pattern | 7 |
| MIT9301 | 1 | expression_pattern | 5 |

### By cluster type
response_pattern (7), periodicity_classification (2), diel_expression_pattern (2), expression_classification (1), diel_cycling (1), expression_pattern (1), expression_level (1).

## Out of scope

- No new MCP tools — this adds fields to existing tools only
- No changes to `list_clustering_analyses`, `gene_clusters_by_gene`, or `genes_in_cluster`
- No filtering by cluster_type on the list tools (can be added later if needed)
- No changes to `gene_overview` or `gene_response_profile`
- No `clustered_gene_count` field (double-counting issue — see "Dropped from original design" above)
