# KG-side ask: `Gene.tcdb_family_count` should count deepest attachments only

**Date:** 2026-08-29 · **From:** explorer (`multiomics_explorer`) · **To:** KG (`multiomics_biocypher_kg`)
**Pri:** P3 (non-blocking — the explorer computes the count live until this lands) · **Kind:** graph (post-import
aggregation) + one KG validity test · **Hash-neutral** (no `ControlledVocabulary` change).
**Context:** explorer backlog 3.4 (`gene_overview` `tcdb_family_count` / `cazy_family_count`), spec
`docs/tool-specs/2026-08-29-gene-overview-family-counts.md`.

## Summary

`Gene.tcdb_family_count` counts **every** `Gene_has_tcdb_family` edge, including ancestor attachments that
carry `attachment_depth = 'superseded'` because the same gene is attached to a descendant family. That is the
multiplicity the substrate-depth migration (`docs/kg-changes/tcdb-two-source-upgrade.md`; explorer review
`docs/kg-specs/2026-08-26-review-tcdb-substrate-depth-migration.md`) moved the rest of the TCDB surface off —
`Gene.transported_metabolite_count` and `Metabolite.transporter_gene_count` are already deepest-attachment
projections. Ask: make `tcdb_family_count` a projection of the same set.

## Current state (live dev build 2026-08-29, rebuild #3)

```cypher
MATCH (g:Gene)-[r:Gene_has_tcdb_family]->(t:TcdbFamily)
RETURN r.attachment_depth AS depth, count(*) AS edges, count(DISTINCT g) AS genes, count(DISTINCT t) AS families
-- most_specific  47360  30547  1377
-- superseded      7267   7045   160
```

```cypher
MATCH (g:Gene) WHERE g.tcdb_family_count IS NOT NULL
OPTIONAL MATCH (g)-[r:Gene_has_tcdb_family]->()
WITH g, count(r) AS all_edges,
     size([x IN collect(r) WHERE x.attachment_depth = 'most_specific']) AS deepest
RETURN sum(CASE WHEN g.tcdb_family_count = deepest THEN 1 ELSE 0 END) AS eq_deepest,   -- 120413
       sum(CASE WHEN g.tcdb_family_count = all_edges THEN 1 ELSE 0 END) AS eq_all       -- 127458 (all genes)
```

So the prop equals the all-edges count on every gene and over-counts on 7,045 genes. Examples:
PMM0392 reads 8 (7 most-specific `3.A.1.x` + superseded `3.A.1`); M744_10340 / H6G84_08685 /
Sputw3181_2948 read 7 vs 4 most-specific.

`Gene.cazy_family_count` is exact (flat ontology, = edge count on all 127,458 genes) — no change.

The edge prop is exactly equivalent to the structural rule the explorer uses elsewhere
(`NOT EXISTS { (g)-[:Gene_has_tcdb_family]->(d) WHERE (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(tf) }`):
0 disagreements over all 54,627 edges.

## Required change

### Property changes

| Node | Property | Change | Notes |
|---|---|---|---|
| `Gene` | `tcdb_family_count` | redefine: count of `Gene_has_tcdb_family` edges with `attachment_depth = 'most_specific'` | keep name, keep `int` zero-filled on every Gene. Same aggregation step that computes `transported_metabolite_count`. |

### Test change

`tests/kg_validity/test_tcdb_cazy.py::test_tcdb_family_count_is_not_tier_gated` pins the all-edges
definition ("routing counts cover ALL edges — only the quality buckets are gated"). Tier-gating and
depth-gating are different axes: the new count is still not tier-gated (an uncorroborated
`most_specific` DIAMOND hit still counts), it just excludes ancestors superseded on the same gene. Suggested
replacement:

```python
def test_tcdb_family_count_is_deepest_attachment_only(run_query):
    """Routing count = most_specific attachments (any tier); superseded ancestors excluded."""
    n = run_query("""
        MATCH (g:Gene)
        OPTIONAL MATCH (g)-[r:Gene_has_tcdb_family]->() WHERE r.attachment_depth = 'most_specific'
        WITH g, count(r) AS actual WHERE coalesce(g.tcdb_family_count, -1) <> actual
        RETURN count(g) AS n
    """)[0]["n"]
    assert n == 0
```

Document the redefinition in `CLAUDE.md` (KG repo) next to `transported_metabolite_count` and list it under
`Schema_info.breaking_changes` if it lands on an official release (value change on an existing prop).

## Verification queries (after rebuild)

```cypher
-- 0 rows expected
MATCH (g:Gene)
OPTIONAL MATCH (g)-[r:Gene_has_tcdb_family]->() WHERE r.attachment_depth = 'most_specific'
WITH g, count(r) AS actual WHERE coalesce(g.tcdb_family_count, -1) <> actual
RETURN g.locus_tag, g.tcdb_family_count, actual LIMIT 5

-- PMM0392 → 7
MATCH (g:Gene {locus_tag:'PMM0392'}) RETURN g.tcdb_family_count

-- invariant: tcdb_family_count > 0  ⟺  transport_substrate_resolution IS NOT NULL   (0 expected)
MATCH (g:Gene)
WHERE (g.tcdb_family_count > 0) <> (g.transport_substrate_resolution IS NOT NULL)
RETURN count(g)
```

## Explorer side once landed

One-line swap in `build_gene_overview`: the live edge-prop comprehension → `coalesce(g.tcdb_family_count, 0)`.
The explorer `-m kg` invariant test (spec §tests (i)) compares the row value with the edge count, so the swap
is verified by the existing gate. No re-pin, no golden movement.

## Status

- [x] Reviewed with KG owner (2026-08-29)
- [x] Implemented in KG repo (aggregation + validity test) — `scripts/post-import.{sh,cypher}` transport-arm statement sets `tcdb_family_count = n_deepest`; `tests/kg_validity/test_tcdb_cazy.py::test_tcdb_family_count_is_deepest_attachment_only` + `_not_tier_gated` + `_matches_substrate_resolution_presence`
- [x] KG rebuilt (2026-08-29, dev build)
- [x] Verification queries pass — 0 mismatches, PMM0392 → 7, invariant 0 violations; `pytest -m kg` 1200 passed
- [ ] Explorer swapped to the precomputed prop
