# Materialize Clustering Analysis Properties on OrganismTaxon, Publication, Experiment

## Context

The explorer's `list_organisms`, `list_publications`, and `list_experiments` tools surface pre-materialized summary properties like `experiment_count`, `treatment_types`, `omics_types`. We want to add clustering analysis coverage the same way.

The explorer repo will read these as direct node properties — no traversal at query time.

## New properties to materialize

| Property | Type | Description |
|---|---|---|
| `clustering_analysis_count` | int | Count of linked ClusteringAnalysis nodes |
| `cluster_types` | list[str] | Distinct `cluster_type` values from linked CAs |
| `cluster_count` | int | Sum of `cluster_count` across linked CAs |

Set on: `OrganismTaxon`, `Publication`, `Experiment`.

Nodes with no linked CAs get: `0`, `[]`, `0`.

## Enrichment Cypher

### OrganismTaxon

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

### Publication

```cypher
MATCH (p:Publication)
OPTIONAL MATCH (p)-[:PublicationHasClusteringAnalysis]->(ca:ClusteringAnalysis)
WITH p,
     count(ca) AS ca_count,
     collect(DISTINCT ca.cluster_type) AS ctypes,
     sum(coalesce(ca.cluster_count, 0)) AS total_clusters
SET p.clustering_analysis_count = ca_count,
    p.cluster_types = ctypes,
    p.cluster_count = total_clusters
```

### Experiment

```cypher
MATCH (e:Experiment)
OPTIONAL MATCH (e)-[:ExperimentHasClusteringAnalysis]->(ca:ClusteringAnalysis)
WITH e,
     count(ca) AS ca_count,
     collect(DISTINCT ca.cluster_type) AS ctypes,
     sum(coalesce(ca.cluster_count, 0)) AS total_clusters
SET e.clustering_analysis_count = ca_count,
    e.cluster_types = ctypes,
    e.cluster_count = total_clusters
```

## Where to add

Extend the existing post-import enrichment step that computes `experiment_count`, `treatment_types`, `omics_types`, etc. Same phase, same pattern.

## Verification

After enrichment, run:

```cypher
MATCH (o:OrganismTaxon)
WHERE o.clustering_analysis_count > 0
RETURN o.organism_name, o.clustering_analysis_count, o.cluster_types, o.cluster_count
ORDER BY o.clustering_analysis_count DESC
```

Expected: 7 organisms (MED4: 4/35, NATL2A: 4/45, MruberA: 2/10, BP1: 2/10, MIT1002: 1/3, MIT9313: 1/7, MIT9301: 1/5).

Same for Publication (8 with CAs) and Experiment (11 with CAs).

## Dependencies

- Requires: `ClusteringAnalysis` nodes with `cluster_type` and `cluster_count` properties (already exist)
- Requires: edges `ClusteringanalysisBelongsToOrganism`, `PublicationHasClusteringAnalysis`, `ExperimentHasClusteringAnalysis` (already exist)
- Blocked by: nothing — can run after existing enrichment
