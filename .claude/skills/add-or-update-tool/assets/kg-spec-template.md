# KG change spec: {tool-name}

## Summary

One-line description of what KG changes are needed and why.

## Current state

What relevant nodes/edges/properties exist today.
Include `run_cypher` results: counts, sample data, schema excerpts.

## Required changes

### New nodes

| Label | Properties | Source | Notes |
|---|---|---|---|
| — | — | — | — |

### New edges

| Type | Source → Target | Properties | Notes |
|---|---|---|---|
| — | — | — | — |

### Property changes

| Node/Edge | Property | Change | Notes |
|---|---|---|---|
| — | — | add/rename/remove/type change | — |

### New indexes

| Type | Name | Fields | Notes |
|---|---|---|---|
| fulltext / btree | — | — | — |

## Example Cypher (desired)

```cypher
-- After KG changes, this query should work:
MATCH ...
RETURN ...
```

## Verification queries

Queries to run after KG rebuild to confirm changes landed:

```cypher
-- Count new nodes
MATCH (n:NewLabel) RETURN count(n)

-- Verify edge structure
MATCH (a)-[r:NEW_EDGE]->(b) RETURN labels(a), type(r), labels(b), count(*) LIMIT 5
```

## Status

- [ ] Spec reviewed with user
- [ ] Changes implemented in KG repo
- [ ] KG rebuilt
- [ ] Verification queries pass
