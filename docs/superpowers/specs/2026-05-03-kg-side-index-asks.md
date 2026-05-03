# Two small index asks from chemistry slice 1 (KG-A9, KG-A10)

**From:** explorer team (multiomics_explorer)
**Date:** 2026-05-03
**Companion to:** the chemistry-slice-1 + follow-up KG-asks already landed
on this rebuild — `KG-A1..A4` (gene/metabolite/keggterm rollups) and
`KG-A5..A8` (Metabolite denormalization arrays). Both spec docs live
under `multiomics_explorer/docs/superpowers/specs/`.
**Driving spec:** `multiomics_explorer/docs/tool-specs/list_metabolites.md`
(Phase 1, frozen, ready for explorer-side build).
**Verification state:** all current-state facts checked against the live
KG (`bolt://localhost:7687`) on 2026-05-03 (post-2026-05-03 rebuild
that landed KG-A5..A8 + the substrate-edge rollup + the gene_count
transport-arm fix).

Two missing indexes surfaced during the explorer-side spec finalisation
for `list_metabolites`. Both are 1-line `CREATE INDEX` statements,
**online creation — no rebuild needed**. Useful well beyond
`list_metabolites` (any tool joining KEGG pathways or HMDB IDs benefits).

## Summary

| # | Item | Class | Severity | Status |
|---|---|---|---|---|
| **KG-A9** | `kegg_term_id_idx` RANGE on `KeggTerm.id` | Schema addition (online index) | MED — load-bearing for `list_metabolites.top_pathways` summary CALL + `not_found.pathway_ids` existence check | **LANDED 2026-05-03** |
| **KG-A10** | `metabolite_hmdb_idx` RANGE on `Metabolite.hmdb_id` | Schema addition (online index) | LOW — consistency with sibling chebi/kegg/mnxm indexes; affects `list_metabolites.hmdb_ids` filter only | **LANDED 2026-05-03** |

**Build update (2026-05-03):** both indexes live and ONLINE. Verified
via `SHOW INDEXES`: `kegg_term_id_idx` (RANGE on KeggTerm.id) and
`metabolite_hmdb_idx` (RANGE on Metabolite.hmdb_id) both
`state: ONLINE`. `list_metabolites` Phase 2 build is fully unblocked
on the performance front; the `top_pathways` summary CALL's KeggTerm
lookup is now an index seek instead of a 5K-node label scan.

---

## KG-A9 — `kegg_term_id_idx` RANGE on `KeggTerm.id`

**Friction.** `list_metabolites` consumes `Metabolite.pathway_ids: list[str]`
(KG-A5, the denormalized list of `KeggTerm.id` reachable via
`Metabolite_in_pathway`). Two places in the explorer-side build need to
look up `KeggTerm` by `id`:

1. **Summary builder `top_pathways` CALL** — for each of the top-10
   pathways by metabolite count, looks up `pathway_name`:
   ```cypher
   CALL {
     WITH all_pwys
     UNWIND apoc.coll.frequencies(all_pwys) AS f
     WITH f.item AS pathway_id, f.count AS count
     ORDER BY count DESC LIMIT 10
     OPTIONAL MATCH (p:KeggTerm {id: pathway_id})
     RETURN collect({
       pathway_id: pathway_id, pathway_name: p.name, count: count
     }) AS top_pathways
   }
   ```

2. **`not_found.pathway_ids` existence check** in api/:
   ```cypher
   MATCH (p:KeggTerm) WHERE p.id IN $pathway_ids
   RETURN collect(p.id) AS found
   ```

**Verification.** Live query 2026-05-03 confirms no RANGE/btree index on
`KeggTerm.id` exists (only the `keggFullText` fulltext on `KeggTerm.name`
+ existing range indexes on TcdbFamily/Metabolite/Reaction id fields).
KeggTerm has 5,058 nodes total. Without the index, Cypher does a label
scan + property filter per call — ~50K node-property comparisons per
summary query (10 pathway lookups × 5,058 KeggTerm nodes).

There's a precedent gap here too: `Reaction.id` is indexed
(`reaction_id_idx`), `Metabolite.id` is indexed (`metabolite_id_idx`),
but `KeggTerm.id` was missed. Same idea, same usage pattern.

**Desired affordance.** A standard RANGE index on `KeggTerm.id` so
property-equality lookups (`{id: $value}` and `IN $list`) become index
seeks instead of label scans.

**Resolution.** One-line online index creation:

```cypher
CREATE INDEX kegg_term_id_idx FOR (k:KeggTerm) ON (k.id);
```

If indexes are declared in a schema file (e.g.
`config/schema_config.yaml` or wherever the existing `metabolite_id_idx`,
`reaction_id_idx`, `tcdb_family_tcdb_id_idx` etc. are declared), add it
there too so it survives future rebuilds.

**Verification after creation:**

```cypher
SHOW INDEXES YIELD name, labelsOrTypes, properties, type, state
WHERE name = 'kegg_term_id_idx'
RETURN name, labelsOrTypes, properties, type, state
// Expect: ONLINE, KeggTerm, [id], RANGE
```

**Cost.** ~5 sec online build for 5,058 nodes; storage trivial (~50KB).

---

## KG-A10 — `metabolite_hmdb_idx` RANGE on `Metabolite.hmdb_id`

**Friction.** `list_metabolites` accepts `hmdb_ids: list[str]` as a
batch filter parameter, parallel to `chebi_ids`, `kegg_compound_ids`,
and `mnxm_ids`. The first three are index-backed (`metabolite_chebi_idx`,
`metabolite_kegg_id_idx`, `metabolite_mnxm_idx` all exist as RANGE
indexes); only `hmdb_id` lacks the sibling index — likely an oversight
when the chemistry layer was built.

**Verification.** Live query 2026-05-03 confirms no RANGE index on
`Metabolite.hmdb_id`. Coverage: 1,425 / 3,025 metabolites have
`hmdb_id` populated (~47%). Filter would do a label scan over all
3,025 Metabolite nodes — small enough today (~50ms) but inconsistent
with the sibling-index pattern.

**Desired affordance.** Sibling parity:

```cypher
CREATE INDEX metabolite_hmdb_idx FOR (m:Metabolite) ON (m.hmdb_id);
```

**Verification after creation:**

```cypher
SHOW INDEXES YIELD name, labelsOrTypes, properties, type, state
WHERE name = 'metabolite_hmdb_idx'
RETURN name, labelsOrTypes, properties, type, state
// Expect: ONLINE, Metabolite, [hmdb_id], RANGE
```

**Cost.** ~3 sec online build for 1,425 populated nodes; storage trivial.

---

## Both can land in the same online-index creation block

```cypher
CREATE INDEX kegg_term_id_idx FOR (k:KeggTerm) ON (k.id);
CREATE INDEX metabolite_hmdb_idx FOR (m:Metabolite) ON (m.hmdb_id);
```

No rebuild required — both are online-creation. Run the verification
queries after, and update whichever file declares the existing
`metabolite_id_idx` / `reaction_id_idx` / `tcdb_family_tcdb_id_idx`
indexes so they survive future rebuilds.

When done, please reply with the verification output (the two
`SHOW INDEXES` results) so the explorer-side can mark these as
landed in the follow-up KG-asks doc.

## Where these fit in the existing KG-asks numbering

- KG-A1..A4 — chemistry-slice-1 direct asks (`Gene.reaction_count`,
  `Gene.metabolite_count`, `Metabolite.elements`, KeggTerm pathway
  rollups). All landed 2026-05-02.
- KG-A5..A8 — chemistry-slice-1 follow-up asks (Metabolite
  denormalizations: `pathway_ids`, `pathway_names`, `pathway_count`,
  `organism_names`). All landed 2026-05-02.
- **KG-A9, KG-A10** (this batch) — index-only asks discovered during
  spec finalisation for the `list_metabolites` build.
- TCDB-S1..S5 — coordination suggestions, all accepted into the
  TCDB-CAZy spec.
- MET-M1..M5 — pre-spec suggestions for the future metabolomics-DM
  spec.

The explorer-side follow-up KG-asks doc is at
`multiomics_explorer/docs/superpowers/specs/2026-05-02-kg-side-chemistry-slice1-followup-asks.md`
— happy to amend it with KG-A9/A10 sections after these land.
