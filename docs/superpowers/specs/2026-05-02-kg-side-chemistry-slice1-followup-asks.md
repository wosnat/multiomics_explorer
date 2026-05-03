# KG-side follow-up asks for Chemistry MCP slice 1 — Metabolite-side denormalizations

**Date:** 2026-05-02
**Audience:** KG team conversation
**Companion to:** `multiomics_explorer/docs/superpowers/specs/2026-05-01-kg-side-chemistry-slice1-asks.md`
(direct-ask sibling — KG-A1..A4 already landed 2026-05-02)
**Driving spec:** `multiomics_explorer/docs/tool-specs/list_metabolites.md` (Phase 1 spec, pre-build)
**Verification state:** all current-state facts checked against live KG (`bolt://localhost:7687`) on 2026-05-02 (post-TCDB-CAZy rebuild).

**Build update (2026-05-02, late):** all 4 follow-up asks (KG-A5..A8)
**landed in the live KG**. Verified live: `Metabolite.pathway_ids`,
`pathway_names`, `pathway_count`, `organism_names` populated 100%
(3,025/3,025); `size(m.organism_names) == m.organism_count` invariant
holds. Glucose carries 35 pathway memberships, 31 organism reaches.
Chemistry slice-1 explorer build of `list_metabolites` is unblocked
and will use the rollup-based Cypher directly (no fallback branch).

This is a small follow-up batch of **direct asks** surfaced while drafting
the Cypher for `list_metabolites` (chemistry slice-1 first net-new tool).
All 4 are post-import rollups that **denormalize edge targets onto
`Metabolite`**, mirroring the `Publication.organisms` / `Publication.treatment_types`
pattern. Each one collapses an EXISTS-subquery filter into a flat
list-membership check, eliminates per-row edge traversals in the detail
query, and gives the LLM a couple of new at-a-glance routing signals.

Slice-1 explorer build can ship without these (current spec falls back to
`EXISTS { MATCH ... }` filter clauses + `[(m)-[:..]->(x) | x.id]` per-row
traversals), but the explorer code is materially simpler — and roughly 2-3×
faster on detail queries — when these are populated. Recommendation:
land them in the same post-import rebuild (or one shortly after) so the
explorer build picks them up cleanly.

## Summary of asks

| # | Item | Class | Severity | Status |
|---|---|---|---|---|
| **KG-A5** | `Metabolite.pathway_ids: list[str]` post-import rollup | Schema addition (post-import) | MED for explorer slice-1 (simplification + perf) | **LANDED 2026-05-02** |
| **KG-A6** | `Metabolite.pathway_names: list[str]` post-import rollup (paired with A5; verbose-row source) | Schema addition (post-import) | LOW–MED — paired ergonomics | **LANDED 2026-05-02** |
| **KG-A7** | `Metabolite.pathway_count: int` post-import rollup | Schema addition (post-import) | LOW–MED — routing signal | **LANDED 2026-05-02** |
| **KG-A8** | `Metabolite.organism_names: list[str]` post-import rollup | Schema addition (post-import) | MED — collapses organism filter from EXISTS subquery to flat ANY-in-list | **LANDED 2026-05-02** |

All four follow the same `Publication.organisms` / `OrganismTaxon.compartments`
denormalization precedent. Storage cost across all four is < 100K
strings + 3K ints (≪ 0.1% of graph storage).

---

## Direct asks

### KG-A5 — `Metabolite.pathway_ids: list[str]` post-import rollup

**Friction.** `list_metabolites` exposes `pathway_ids` per row and accepts
`pathway_ids` as a filter. Today both require traversing the
`Metabolite_in_pathway` edge:

```cypher
// Per-row collection (every detail query):
RETURN ...,
       [(m)-[:Metabolite_in_pathway]->(p:KeggTerm) | p.id] AS pathway_ids

// Filter (every filtered query):
WHERE EXISTS {
  MATCH (m)-[:Metabolite_in_pathway]->(p:KeggTerm)
  WHERE p.id IN $pathway_ids
}
```

Both patterns work but add edge-traversal cost per matched metabolite. With
~9,444 `Metabolite_in_pathway` edges across 3,025 metabolites (avg ~3
pathways/metabolite, max much higher for central compounds like ATP),
this materially slows detail queries that span thousands of metabolites.

**Verification.** Live query 2026-05-02 confirms `Metabolite.pathway_ids`
does not exist:

```
MATCH (m:Metabolite {id: 'kegg.compound:C00031'}) RETURN keys(m) AS k
→ ["kegg_compound_id","name","formula","elements","mass","inchikey","smiles",
   "mnxm_id","chebi_id","hmdb_id","evidence_sources","transporter_count",
   "id","preferred_id","gene_count","organism_count"]
   // No pathway_ids, no organism_names.
```

`Metabolite_in_pathway` covers 9,444 edges to 395 distinct pathway
KeggTerms (verified live).

**Desired affordance.** `Metabolite.pathway_ids: list[str]` populated as
the distinct sorted list of `KeggTerm.id` reachable via
`Metabolite_in_pathway`. Empty list when no pathway memberships.

```cypher
// New per-row collection (zero traversal):
RETURN ..., coalesce(m.pathway_ids, []) AS pathway_ids

// New filter (zero subquery):
WHERE ANY(p IN $pathway_ids WHERE p IN m.pathway_ids)
```

**Resolution.** Single-pass aggregation in `scripts/post-import.sh`,
slot near the existing chemistry rollups:

```cypher
MATCH (m:Metabolite)
CALL {
  WITH m
  OPTIONAL MATCH (m)-[:Metabolite_in_pathway]->(p:KeggTerm)
  WITH m, apoc.coll.sort(collect(DISTINCT p.id)) AS pids
  SET m.pathway_ids = pids
} IN TRANSACTIONS OF 1000 ROWS;
```

**Schema declaration:** add `pathway_ids: list[str]` to the `metabolite`
entry in `config/schema_config.yaml`.

**Cost.** ~6 lines; one rollup pass over 3,025 Metabolite nodes; storage
~9K strings.

**Pattern precedent:** `Publication.organisms`, `Publication.treatment_types`,
`Publication.omics_types` (all denormalize edge-target/scalar values
onto Publication for filter and per-row use).

---

### KG-A6 — `Metabolite.pathway_names: list[str]` post-import rollup (paired with A5)

**Friction.** The verbose row of `list_metabolites` exposes
`pathway_names` aligned with `pathway_ids`. Today this requires a second
per-row traversal:

```cypher
// Verbose row, today:
RETURN ...,
       [(m)-[:Metabolite_in_pathway]->(p:KeggTerm) | p.id] AS pathway_ids,
       [(m)-[:Metabolite_in_pathway]->(p:KeggTerm) | p.name] AS pathway_names
```

**Desired affordance.** `Metabolite.pathway_names: list[str]` aligned
**index-for-index** with `pathway_ids` (same sort order — alphabetical
on pathway_id). Empty list when no pathway memberships.

```cypher
// Verbose row with both rollups:
RETURN ...,
       coalesce(m.pathway_ids, []) AS pathway_ids,
       coalesce(m.pathway_names, []) AS pathway_names
```

**Resolution.** Same post-import block as KG-A5 — fold the names into the
same aggregation so alignment is guaranteed:

```cypher
MATCH (m:Metabolite)
CALL {
  WITH m
  OPTIONAL MATCH (m)-[:Metabolite_in_pathway]->(p:KeggTerm)
  WITH m, p
  ORDER BY p.id
  WITH m,
       collect(DISTINCT p.id) AS pids,
       collect(DISTINCT p.name) AS pnames
  SET m.pathway_ids = pids,
      m.pathway_names = pnames
} IN TRANSACTIONS OF 1000 ROWS;
```

The `ORDER BY p.id` before the `collect` keeps the two arrays aligned.

**Schema declaration:** add `pathway_names: list[str]` to the `metabolite`
entry in `config/schema_config.yaml` alongside KG-A5.

**Cost.** ~3 extra lines on top of A5; storage ~9K strings (avg
pathway_name ~30 chars).

**Pattern precedent:** Same as A5; pairs with the existing
`Publication.organisms` (just IDs) — but here we keep both because the
verbose row needs human-readable names for LLM rendering without a
KeggTerm join.

**Skip option.** If KG team prefers to keep `pathway_names` out of the
denormalization (storage-conservative), explorer can fall back to the
per-row traversal for the verbose case only — the filter and
non-verbose detail row both benefit from A5 alone. A6 is the smallest
of the four; LOW priority.

---

### KG-A7 — `Metabolite.pathway_count: int` post-import rollup

**Friction.** The Pydantic field rubric promotes "rollup-style routing
signals" on every node — `gene_count`, `organism_count`,
`transporter_count` already exist on `Metabolite`. `pathway_count` is the
natural completion of that set. Without it, the LLM can't ask "show me
metabolites that are in many pathways" without scanning detail rows.

**Verification.** Live query 2026-05-02 confirms `Metabolite.pathway_count`
does not exist (see KG-A5 verification block).

**Desired affordance.** `Metabolite.pathway_count: int` populated as
the distinct count of `KeggTerm` nodes reachable via `Metabolite_in_pathway`.
Default 0 when no edges (no separate defaults block needed —
`count(p)` returns 0 cleanly).

This becomes a per-row field on `MetaboliteResult` and lets the LLM route
to `genes_by_ontology(ontology="kegg", term_ids=[...])` for high-coverage
metabolites.

**Resolution.** Simplest form — pairs with KG-A5/A6 in the same block:

```cypher
MATCH (m:Metabolite)
CALL {
  WITH m
  OPTIONAL MATCH (m)-[:Metabolite_in_pathway]->(p:KeggTerm)
  WITH m, p
  ORDER BY p.id
  WITH m,
       collect(DISTINCT p.id) AS pids,
       collect(DISTINCT p.name) AS pnames,
       count(DISTINCT p) AS pcount
  SET m.pathway_ids = pids,
      m.pathway_names = pnames,
      m.pathway_count = pcount
} IN TRANSACTIONS OF 1000 ROWS;
```

**Schema declaration:** add `pathway_count: int` to the `metabolite`
entry in `config/schema_config.yaml`.

**Cost.** ~1 extra line on top of A5/A6; storage ~24KB total (3,025 ints).

**Pattern precedent:** `Reaction.gene_count`, `BriteCategory.gene_count`,
`OrganismTaxon.metabolite_count`, all the existing `Metabolite` rollups
(`gene_count`, `organism_count`, `transporter_count`).

---

### KG-A8 — `Metabolite.organism_names: list[str]` post-import rollup

**Friction.** `list_metabolites` accepts `organism_names: list[str]` to
restrict to metabolites reachable from at least one of the listed
organisms. Today this requires an EXISTS subquery against the
`Organism_has_metabolite` edge:

```cypher
// Filter, today:
WHERE EXISTS {
  MATCH (org:OrganismTaxon)-[:Organism_has_metabolite]->(m)
  WHERE toLower(org.preferred_name) IN $organism_names_lc
}
```

`Organism_has_metabolite` covers 56,898 edges across 3,025 metabolites
and 36 organisms (post-TCDB UNION). The EXISTS pattern is slow to plan
when combined with other filters (Cypher planner often re-evaluates the
subquery per matched metabolite).

**Verification.** Live query 2026-05-02 confirms `Metabolite.organism_names`
does not exist (see KG-A5 verification block).

**Desired affordance.** `Metabolite.organism_names: list[str]` populated
as the distinct sorted list of `OrganismTaxon.preferred_name` values
reachable via the (UNION'd post-TCDB) `Organism_has_metabolite` edge.
Case preserved as it appears on `OrganismTaxon` (lowercase comparison
done in the WHERE clause, mirroring how `OrganismTaxon.preferred_name`
itself is queried elsewhere).

```cypher
// New filter (no subquery):
WHERE ANY(o IN m.organism_names WHERE toLower(o) IN $organism_names_lc)
```

**Resolution.** Single-pass aggregation in `scripts/post-import.sh`,
slot near the existing chemistry rollups:

```cypher
MATCH (m:Metabolite)
CALL {
  WITH m
  OPTIONAL MATCH (org:OrganismTaxon)-[:Organism_has_metabolite]->(m)
  WITH m, apoc.coll.sort(collect(DISTINCT org.preferred_name)) AS onames
  SET m.organism_names = onames
} IN TRANSACTIONS OF 1000 ROWS;
```

`Metabolite.organism_count` (the existing scalar) and the new
`Metabolite.organism_names` are kept in sync trivially:
`size(m.organism_names) == m.organism_count` should be invariant; nice
sanity check for a post-import audit query.

**Schema declaration:** add `organism_names: list[str]` to the `metabolite`
entry in `config/schema_config.yaml`.

**Cost.** ~6 lines; one pass over 3,025 Metabolite nodes; storage ~45K
strings (~1MB).

**Pattern precedent:** `Publication.organisms`, `Experiment.organism_name`
(the scalar version of the same idea).

---

## Build sequencing

All 4 land in the same post-import rebuild — they're in adjacent
post-import blocks and share the same `IN TRANSACTIONS OF 1000 ROWS`
batching. Single PR, single rebuild.

Combined post-import block (suggested):

```cypher
// Chemistry slice-1 follow-up: A5/A6/A7 (pathway rollups)
MATCH (m:Metabolite)
CALL {
  WITH m
  OPTIONAL MATCH (m)-[:Metabolite_in_pathway]->(p:KeggTerm)
  WITH m, p
  ORDER BY p.id
  WITH m,
       collect(DISTINCT p.id) AS pids,
       collect(DISTINCT p.name) AS pnames,
       count(DISTINCT p) AS pcount
  SET m.pathway_ids = pids,
      m.pathway_names = pnames,
      m.pathway_count = pcount
} IN TRANSACTIONS OF 1000 ROWS;

// Chemistry slice-1 follow-up: A8 (organism rollup)
MATCH (m:Metabolite)
CALL {
  WITH m
  OPTIONAL MATCH (org:OrganismTaxon)-[:Organism_has_metabolite]->(m)
  WITH m, apoc.coll.sort(collect(DISTINCT org.preferred_name)) AS onames
  SET m.organism_names = onames
} IN TRANSACTIONS OF 1000 ROWS;
```

Both passes are O(n_metabolites × avg_edges_per_metabolite) — < 1s
combined on the current graph.

---

## Explorer-side forward-compat

Until the asks land, the explorer's `list_metabolites` builder uses the
fallback patterns documented in
`multiomics_explorer/docs/tool-specs/list_metabolites.md`:

```python
# pathway_ids — per-row traversal
"[(m)-[:Metabolite_in_pathway]->(p:KeggTerm) | p.id] AS pathway_ids"

# organism_names filter — EXISTS subquery
"EXISTS { MATCH (org:OrganismTaxon)-[:Organism_has_metabolite]->(m) "
"         WHERE toLower(org.preferred_name) IN $organism_names_lc }"
```

When the asks land, the builder switches to the simpler form — no
`coalesce`-style runtime branching needed because the rebuild is a
hard cutover (either the property exists or it doesn't; live KG is the
single source of truth at any one time). One PR on the explorer side,
post-rebuild, swaps the fallback for the rollup-based form.

If the KG team can land A5/A8 *before* the explorer build of
`list_metabolites` (the spec's first item in implementation order),
the explorer build skips the fallback path entirely. That's the cleanest
sequencing.

---

## What we're explicitly NOT asking for

- **`Reaction.metabolite_ids: list[str]` / `Reaction.organism_names: list[str]`**
  — same denormalization pattern but on `Reaction`. Out of scope for
  `list_metabolites` (Tool 1 of slice 1) but **highly relevant** to
  Tools 2 (`genes_by_metabolite`) and 3 (`gene_metabolic_role`) which
  hit the same EXISTS-subquery friction on the Reaction side. To be
  filed once the Tools 2/3 specs are written — likely as a parallel
  follow-up in 1-2 weeks.

- **`Metabolite.gene_locus_tags: list[str]`** — would denormalize
  individual catalysing/transporting gene locus_tags onto each
  Metabolite. Storage explodes (3,025 metabolites × ~50 genes avg = 150K
  strings) and the gene-anchored `genes_by_metabolite(metabolite_ids=[id])`
  drill-down is a single-hop traversal already. Skip.

- **`Metabolite.compartments_observed: list[str]`** — already filed
  pre-spec for the future metabolomics-DM spec (MET-M2 in the original
  KG-asks doc). Will land naturally with that spec; no need to pull
  forward.

- **`Metabolite.pathway_ids` lowercased mirror** — `KeggTerm.id` is
  already case-stable (`kegg.pathway:ko00910`); no lowercase round-trip
  needed. The `organism_names` ask (A8) doesn't need a lowercased
  mirror either — `toLower()` on a small list (~15 elements) per
  matched row is cheap, mirrors how `OrganismTaxon.preferred_name`
  itself is queried.

- **Composite or map-typed properties** (`pathways: [{id, name}]`) — would
  pack ID + name into a single map per pathway. Less aligned with the
  existing schema pattern (`Publication.organisms` is `list[str]`, not
  `list[map]`); skip in favor of the parallel-arrays approach in A5/A6.

---

## References

- Chemistry slice-1 design: `multiomics_explorer/docs/superpowers/specs/2026-05-01-metabolism-chemistry-mcp-tools-design.md`
- Original chemistry slice-1 KG-asks (KG-A1..A4 + TCDB-S* + MET-M*): `multiomics_explorer/docs/superpowers/specs/2026-05-01-kg-side-chemistry-slice1-asks.md`
- TCDB-CAZy ontology (live, 2026-05-02): `multiomics_biocypher_kg/docs/kg-changes/tcdb-cazy-ontologies.md`
- Driving spec (this doc's consumer): `multiomics_explorer/docs/tool-specs/list_metabolites.md`
- Pattern precedent: `Publication.organisms` / `Publication.treatment_types` populated via post-import (existing).
