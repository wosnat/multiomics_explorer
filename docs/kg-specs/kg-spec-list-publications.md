# KG change spec: list_publications

## Summary

Add a fulltext index on Publication nodes (title, abstract, description)
and precomputed experiment summary properties so the `list_publications`
tool can search and filter without joining to Experiment nodes.

## Current state

- 21 Publication nodes with `title`, `abstract`, `description` string properties
  and `organism` (list), `authors` (list)
- No fulltext index on Publication
- Other node types (Gene, Experiment, ontology terms) all have fulltext indexes
- Experiment summary data requires joining through `Has_experiment` edges

## Required changes

### New nodes

None.

### New edges

None.

### Property changes

| Node/Edge | Property | Change | Notes |
|---|---|---|---|
| Publication | `experiment_count` | add (int) | Count of Has_experiment edges. 0 for publications without experiments. |
| Publication | `treatment_types` | add (list) | Distinct treatment_type values from experiments. Empty list if no experiments. |
| Publication | `omics_types` | add (list) | Distinct omics_type values from experiments. Empty list if no experiments. |
| Publication | `organism` → `organisms` | rename | List property — plural name matches type. No existing code references `p.organism`. |

Computed post-import from:
```cypher
MATCH (p:Publication)
OPTIONAL MATCH (p)-[:Has_experiment]->(e:Experiment)
WITH p,
     count(e) AS ec,
     [x IN collect(DISTINCT e.treatment_type) WHERE x IS NOT NULL] AS tts,
     [x IN collect(DISTINCT e.omics_type) WHERE x IS NOT NULL] AS ots
SET p.experiment_count = ec,
    p.treatment_types = tts,
    p.omics_types = ots
```

The `WHERE x IS NOT NULL` filters handle the OPTIONAL MATCH case where
no experiments exist (collect would include a null entry).

### New indexes

| Type | Name | Fields | Notes |
|---|---|---|---|
| fulltext | `publicationFullText` | Publication(title, abstract, description) | Enables Lucene syntax search across title, abstract, and description |

## Index creation

```cypher
CREATE FULLTEXT INDEX publicationFullText IF NOT EXISTS
FOR (p:Publication)
ON EACH [p.title, p.abstract, p.description]
```

## Verification queries

```cypher
-- 1. Confirm index exists
SHOW INDEXES YIELD name, type, labelsOrTypes
WHERE name = 'publicationFullText'
RETURN name, type, labelsOrTypes

-- 2. Test fulltext search works (across all three fields)
CALL db.index.fulltext.queryNodes('publicationFullText', 'nitrogen')
YIELD node AS p, score
RETURN p.title, score
LIMIT 5

-- 3. Verify precomputed properties exist and have correct types
MATCH (p:Publication)
RETURN p.doi, p.experiment_count, p.treatment_types, p.omics_types
ORDER BY p.publication_year DESC
LIMIT 5

-- 4. Consistency check: experiment_count matches live count
MATCH (p:Publication)
OPTIONAL MATCH (p)-[:Has_experiment]->(e:Experiment)
WITH p, count(e) AS live_count
WHERE p.experiment_count <> live_count
RETURN p.doi, p.experiment_count, live_count

-- 5. Consistency check: treatment_types matches live aggregation
MATCH (p:Publication)
OPTIONAL MATCH (p)-[:Has_experiment]->(e:Experiment)
WITH p, [x IN collect(DISTINCT e.treatment_type) WHERE x IS NOT NULL] AS live_types
WHERE p.treatment_types <> live_types
RETURN p.doi, p.treatment_types, live_types

-- 6. No nulls in precomputed lists
MATCH (p:Publication)
WHERE ANY(x IN p.treatment_types WHERE x IS NULL)
   OR ANY(x IN p.omics_types WHERE x IS NULL)
RETURN p.doi
```

## Status

- [x] Spec reviewed with user
- [x] Changes implemented in KG repo
- [x] KG rebuilt
- [x] Verification queries pass (fulltext CALL untestable via run_cypher
  write filter; treatment_types list ordering differs but values match)
