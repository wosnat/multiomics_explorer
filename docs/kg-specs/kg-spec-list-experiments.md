# KG change spec: list_experiments

## Summary

Fix empty-string `coculture_partner` on non-coculture Experiment nodes (should
be null) and add precomputed expression stats to Experiment nodes.

## Current state

76 Experiment nodes, all linked to Publications via `Has_experiment`.
188,501 `Changes_expression_of` edges across 74 experiments (2 have no edges —
this is valid, they represent experiments without DE data in the KG yet).

### Problem 1: Empty-string `coculture_partner` on non-coculture experiments

56 of 76 experiments have `coculture_partner = ""` instead of null.
These are non-coculture experiments (treatment_type != "coculture").

```cypher
-- Verify: non-coculture experiments with empty string partner
MATCH (e:Experiment)
WHERE e.treatment_type <> 'coculture' AND e.coculture_partner = ''
RETURN count(e) AS empty_partner
-- Result: 56
```

All 20 coculture experiments have a real `coculture_partner` value.
The empty string comes from the KG build pipeline setting the property
to `""` when the source data has no coculture partner, instead of
omitting it or setting null.

## Required changes

### New nodes

None.

### New edges

None.

### Property changes

| Node/Edge | Property | Change | Notes |
|---|---|---|---|
| Experiment (56 non-coculture) | `coculture_partner` | remove property (set null) | Currently `""`, should be absent. Non-coculture experiments have no partner. |

### Precomputed stats on Experiment nodes

Computed post-import, after `Changes_expression_of` edges are loaded.
Same pattern as precomputed stats on OrganismTaxon (see `kg-spec-list-organisms.md`).

| Property | Type | Description |
|---|---|---|
| `gene_count` | int | Total genes with expression data (`count(r)` over all edges) |
| `significant_count` | int | Genes with significant DE (`count(CASE WHEN r.significant = 'significant')`) |
| `time_point_count` | int | Number of distinct time points |
| `time_point_labels` | list[str] | Ordered time point labels (e.g. `["2h", "4h", "6h"]`); `""` = no label (non-time-course) |
| `time_point_orders` | list[int] | Parallel array of sort orders (1-indexed) |
| `time_point_hours` | list[float] | Parallel array of hours values; `-1.0` = unknown conversion |
| `time_point_totals` | list[int] | Parallel array of per-tp gene counts |
| `time_point_significants` | list[int] | Parallel array of per-tp significant counts |

All arrays are parallel (same length = `time_point_count`), ordered by
`time_point_order`.

**Neo4j constraint:** Arrays cannot contain nulls. Sentinel values:
- `time_point_labels`: `""` (empty string) for no label
- `time_point_hours`: `-1.0` for unknown hours conversion

**Edge cases:**
- Non-time-course experiments (single implicit time point): arrays have
  one entry with `time_point_labels = [""]`, `time_point_hours = [-1.0]`
- Experiments with 0 expression edges (2 exist): `gene_count = 0`,
  `significant_count = 0`, `time_point_count = 0`, all arrays empty `[]`

```cypher
-- Post-import computation
MATCH (e:Experiment)
OPTIONAL MATCH (e)-[r:Changes_expression_of]->(g:Gene)
WITH e,
     r.time_point AS tp,
     r.time_point_order AS tp_order,
     r.time_point_hours AS tp_hours,
     count(r) AS total,
     count(CASE WHEN r.significant = 'significant' THEN 1 END) AS sig
ORDER BY e.id, tp_order
WITH e,
     sum(total) AS gene_count,
     sum(sig) AS significant_count,
     collect(tp) AS tp_labels,
     collect(tp_order) AS tp_orders,
     collect(tp_hours) AS tp_hours_list,
     collect(total) AS tp_totals,
     collect(sig) AS tp_sigs
SET e.gene_count = gene_count,
    e.significant_count = significant_count,
    e.time_point_count = size(tp_labels),
    e.time_point_labels = tp_labels,
    e.time_point_orders = tp_orders,
    e.time_point_hours = tp_hours_list,
    e.time_point_totals = tp_totals,
    e.time_point_significants = tp_sigs
```

### New indexes

None.

## Verification queries

```cypher
-- 1. No empty-string coculture_partner
MATCH (e:Experiment)
WHERE e.coculture_partner = ''
RETURN count(e)
-- Expected: 0

-- 2. Non-coculture/non-viral experiments have null coculture_partner
MATCH (e:Experiment)
WHERE NOT e.treatment_type IN ['coculture', 'viral']
  AND e.coculture_partner IS NOT NULL
RETURN count(e)
-- Expected: 0

-- 3. Coculture experiments all have non-null coculture_partner
MATCH (e:Experiment)
WHERE e.treatment_type = 'coculture'
  AND (e.coculture_partner IS NULL OR e.coculture_partner = '')
RETURN e.id
-- Expected: 0 rows

-- 4. Total experiment count
MATCH (e:Experiment) RETURN count(e)
-- Expected: 76

-- 5. Precomputed gene_count matches live aggregation
MATCH (e:Experiment)
OPTIONAL MATCH (e)-[r:Changes_expression_of]->(g:Gene)
WITH e, count(r) AS live_count
WHERE e.gene_count <> live_count
RETURN e.id, e.gene_count, live_count
-- Expected: 0 rows

-- 6. Precomputed significant_count matches live aggregation
MATCH (e:Experiment)
OPTIONAL MATCH (e)-[r:Changes_expression_of]->(g:Gene)
WHERE r.significant = 'significant'
WITH e, count(r) AS live_count
WHERE e.significant_count <> live_count
RETURN e.id, e.significant_count, live_count
-- Expected: 0 rows

-- 7. Precomputed time_point_count matches distinct time points
MATCH (e:Experiment)
OPTIONAL MATCH (e)-[r:Changes_expression_of]->(g:Gene)
WITH e, count(DISTINCT r.time_point) AS live_count
WHERE e.time_point_count <> live_count
RETURN e.id, e.time_point_count, live_count
-- Expected: 0 rows

-- 8. All experiments have precomputed stats (no nulls)
MATCH (e:Experiment)
WHERE e.gene_count IS NULL
   OR e.significant_count IS NULL
   OR e.time_point_count IS NULL
   OR e.time_point_labels IS NULL
RETURN e.id
-- Expected: 0 rows
```

## Status

- [x] Spec reviewed with user
- [x] Changes implemented in KG repo
- [x] KG rebuilt
- [x] Verification queries pass (2026-03-22)
  - Query 2 note: 4 viral experiments have coculture_partner="Phage" —
    valid, the field is used for any interacting organism
