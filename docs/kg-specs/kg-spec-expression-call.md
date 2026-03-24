# KG change spec: expression_call on Changes_expression_of edges

## Summary

Add `expression_call` as a precomputed property on `Changes_expression_of` edges.
Derived from existing `r.significant` + `r.expression_direction` at KG build time.

## Motivation

The `differential_expression_by_gene` tool needs a single enum field to:
- Filter rows (`WHERE r.expression_call <> "not_significant"`)
- Aggregate call breakdowns (`apoc.coll.frequencies(collect(r.expression_call))`)

Without this, every aggregation requires two conditional sums and every filter
requires two predicates. Having it precomputed also makes the intent clearer.

## Current state

All `Changes_expression_of` edges have:
- `significant`: string — `"significant"` or `"not_significant"`
- `expression_direction`: string — `"up"` or `"down"`

188,501 total edges; 42,687 significant (22,645 up / 20,042 down).

## Required changes

### New nodes

None.

### New edges

None.

### Property changes

| Node/Edge | Property | Change | Notes |
|---|---|---|---|
| `Changes_expression_of` (all 188,501 edges) | `expression_call` | Add new property | Derived: see derivation rule below |

### Derivation rule

```
expression_call =
  "significant_up"   when r.significant = "significant" AND r.expression_direction = "up"
  "significant_down" when r.significant = "significant" AND r.expression_direction = "down"
  "not_significant"  when r.significant = "not_significant"
```

The `expression_direction` field is still present and not removed — it may be
useful for other queries. `expression_call` is purely additive.

### Implementation (post-import computation)

```cypher
MATCH ()-[r:Changes_expression_of]->()
SET r.expression_call = CASE
  WHEN r.significant = "significant" AND r.expression_direction = "up"   THEN "significant_up"
  WHEN r.significant = "significant" AND r.expression_direction = "down" THEN "significant_down"
  ELSE "not_significant"
END
```

### New indexes

None required — `expression_call` is always used alongside other filters
(locus_tags, experiment_ids) that already use indexes.

## Verification queries

```cypher
-- 1. All edges have expression_call populated
MATCH ()-[r:Changes_expression_of]->()
WHERE r.expression_call IS NULL
RETURN count(r)
-- Expected: 0

-- 2. Total significant matches existing significant count
MATCH ()-[r:Changes_expression_of]->()
WHERE r.expression_call IN ["significant_up", "significant_down"]
RETURN count(r)
-- Expected: 42,687 (matches existing r.significant = "significant" count)

-- 3. Counts match existing fields
MATCH ()-[r:Changes_expression_of]->()
RETURN
  count(CASE WHEN r.expression_call = "significant_up"   THEN 1 END) AS new_up,
  count(CASE WHEN r.expression_call = "significant_down" THEN 1 END) AS new_down,
  count(CASE WHEN r.significant = "significant" AND r.expression_direction = "up"   THEN 1 END) AS old_up,
  count(CASE WHEN r.significant = "significant" AND r.expression_direction = "down" THEN 1 END) AS old_down
-- Expected: new_up = old_up, new_down = old_down

-- 4. No unexpected values
MATCH ()-[r:Changes_expression_of]->()
WHERE r.expression_call NOT IN ["significant_up", "significant_down", "not_significant"]
RETURN count(r)
-- Expected: 0
```

## Status

- [x] Spec reviewed with user
- [ ] Changes implemented in KG repo
- [ ] KG rebuilt
- [ ] Verification queries pass
