# KG change spec: gene_neighbors (performance index)

## Summary

Add a composite RANGE index `Gene(organism_name, contig, start)` so the `gene_neighbors` tool's genomic-window query is index-backed (seek + ordered limited scan) instead of scanning an entire organism's gene set and sorting in memory. Pure performance — no correctness dependency.

## Current state

`Gene` indexes today (verified live 2026-05-26 via `SHOW INDEXES`):

| name | properties | type |
|---|---|---|
| gene_locus_tag_idx | locus_tag | RANGE |
| gene_name_idx | gene_name | RANGE |
| gene_organism_name_idx | organism_name | RANGE |
| geneFullText | gene_summary, all_identifiers, … | FULLTEXT |

No index on `contig` or `start`. The neighbor query filters `organism_name = X AND contig = Y AND start < / > Z` and orders by `start`. Today the planner can only use `gene_organism_name_idx`, so each anchor scans its organism's full gene set (≈2,000–5,500 `Gene` nodes — e.g. *Pseudomonas putida* KT2440: 5,487) and sorts `start` in memory, **twice** (upstream + downstream subquery). Batch anchors multiply this.

`(contig, start)` is unique within a contig and `start` is always co-populated with `contig` (verified) — so the index is fully selective.

## Required changes

### New indexes

| Type | Name | Fields | Notes |
|---|---|---|---|
| RANGE (composite) | `gene_org_contig_start_idx` | `Gene(organism_name, contig, start)` | Equality prefix `(organism_name, contig)` + range/order suffix `start`. Backs the bounded-window subquery's seek + ORDER BY start + LIMIT. |

(No node/edge/property changes.)

## Example Cypher (desired)

After the index lands, each `gene_neighbors` subquery should plan as a `NodeIndexSeekByRange` on `gene_org_contig_start_idx` (confirm via `EXPLAIN`), touching ~`window` entries instead of the whole organism:

```cypher
MATCH (a:Gene {locus_tag: $lt})
MATCH (u:Gene)
WHERE u.organism_name = a.organism_name AND u.contig = a.contig AND u.start < a.start
WITH u ORDER BY u.start DESC LIMIT $window   // index-backed; no in-memory sort
RETURN collect(u) AS ups
```

## Verification queries

After rebuild:

```cypher
-- Index present and ONLINE
SHOW INDEXES YIELD name, properties, type, state
  WHERE name = 'gene_org_contig_start_idx' RETURN name, properties, type, state;

-- Plan uses the index (look for NodeIndexSeekByRange on gene_org_contig_start_idx)
EXPLAIN
MATCH (a:Gene {locus_tag: 'ACZ81_08860'})
MATCH (d:Gene) WHERE d.organism_name=a.organism_name AND d.contig=a.contig AND d.start > a.start
WITH d ORDER BY d.start ASC LIMIT 5 RETURN collect(d);
```

## Status

- [x] Spec reviewed with user
- [x] Index added in KG repo (post-import step) — `gene_org_contig_start_idx` added to both `scripts/post-import.sh` and `scripts/post-import.cypher` (kept in sync); KG validity tests added in `tests/kg_validity/test_post_import.py`; documented in `CLAUDE.md`.
- [x] Index applied live (no full rebuild needed — composite RANGE index built online via `CREATE INDEX ... IF NOT EXISTS` + `db.awaitIndexes`; ONLINE). Persisted in post-import so it survives future rebuilds.
- [x] Verification queries pass (index ONLINE + plan uses it).

### Verification result (2026-05-26, live graph)

`SHOW INDEXES` → `gene_org_contig_start_idx` | `[organism_name, contig, start]` | `RANGE` | `ONLINE`.

`EXPLAIN` of the neighbor subquery now seeks the composite index, with the contig equality **and** the `start` range folded into the seek (the old full-organism `NodeIndexSeek(organism_name)` + separate `Filter` is gone):

```
NodeIndexSeek | RANGE INDEX d:Gene(organism_name, contig, start)
               WHERE organism_name = a.organism_name AND contig = a.contig AND start > a.start
```

Two notes vs. the idealized "Example Cypher" above:
- Modern Neo4j labels this `NodeIndexSeek` (range form), not a distinct `NodeIndexSeekByRange` operator — the range predicate (`start > …`) is folded into `NodeIndexSeek` and confirmed in its `Details`.
- A bounded `Top` (LIMIT-k top-heap) remains over the seeked window. That is over the small same-contig downstream/upstream candidate set the seek returns — not a full-organism in-memory sort — so the headline goal (seek the window, don't scan the organism) holds.
