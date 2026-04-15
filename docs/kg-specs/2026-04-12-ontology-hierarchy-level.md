# Precompute Unified `level` on Ontology Terms

> **KG-side companion:** `second_multiomics/docs/kg-changes/ontology-level.md` documents the adapter-level implementation (file list, derivation code paths, test plan). This document is the explorer-side ask; the two are aligned.

## Context

The explorer is adding an enrichment surface (see `docs/superpowers/specs/2026-04-12-kg-enrichment-surface-design.md` and its three children). Every piece of that surface — `ontology_landscape`, the redefined `genes_by_ontology(level=N)`, and `pathway_enrichment` — needs to roll genes up to a chosen hierarchy level.

Canonical node-label / gene-edge / hierarchy-edge names for each ontology live in `multiomics_explorer/kg/queries_lib.py::ONTOLOGY_CONFIG` — that dict is the source of truth this spec references throughout.

Live KG state (verified 2026-04-12):

| Ontology | Term count | Current level signal | Hierarchy traversal cost |
|---|---|---|---|
| BiologicalProcess | 3,052 | none | BFS via `Biological_process_is_a_biological_process` + `_part_of_` (depth 1–11) |
| MolecularFunction | 2,750 | none | BFS (similar) |
| CellularComponent | 408 | none | BFS |
| EcNumber | 7,337 | none (inferable from id segments) | BFS via `Ec_number_is_a_ec_number` (depth 1–4) |
| KeggTerm | 4,742 | `level: string` (`ko`/`pathway`/`subcategory`/`category`) | `level` lookup |
| CyanorakRole | 173 | none (dot-count on `code`) | dot-count or BFS (depth 1–3) |
| TigrRole | 114 | none — flat | n/a |
| CogFunctionalCategory | 26 | none — flat | n/a |
| Pfam | 5,471 | none (kind = leaf) | `Pfam_in_pfam_clan` cross-label (3,536/5,471 linked) |
| PfamClan | 509 | none (kind = root) | terminal parent label |

Without a unified property, the explorer's hierarchy helper has to dispatch four different strategies (dot-count, string lookup, BFS, flat) and BFS over GO at aggregate query time has already hit Neo4j's 1.4 GiB transaction memory cap on one nearby workload (`gene_ontology_terms` with ~2k genes × GO MF).

## Ask

Add a canonical **`level: int`** property to **every** ontology term — all labels, hierarchical and flat.

Labels in scope:

- `BiologicalProcess`, `MolecularFunction`, `CellularComponent`
- `EcNumber`
- `KeggTerm` (see naming collision note below)
- `CyanorakRole`
- `Pfam` (level 1), `PfamClan` (level 0) — 2-level cross-label hierarchy
- `TigrRole`, `CogFunctionalCategory` — flat

Semantics:

- `level = 0` at the root (broadest).
- `level = depth_from_root` measured via the ontology's `*_is_a_*` (and GO `*_part_of_*`) edges.
- **Tree ontologies** (`CyanorakRole`, `EcNumber`): unambiguous — each term has one parent path.
- **Stratified DAGs** (`KeggTerm`, `Pfam`/`PfamClan`): multiple parents per term are possible, but all paths from a term to a given ancestor have the same length, so `level` remains unambiguous.
  - `KeggTerm`: `0=category, 1=subcategory, 2=pathway, 3=ko`. 2,898 of 4,742 KEGG terms have ≥2 parents (max 36); level still unambiguous.
  - `Pfam = 1`, `PfamClan = 0`. Cross-label parent edge via `Pfam_in_pfam_clan` (3,536/5,471 linked; 1,935 Pfams have no clan — they still get `level = 1` because level is fixed by kind).
- **Variable-depth DAGs** (`BiologicalProcess`, `MolecularFunction`, `CellularComponent`): `level = min(depth)` across all root paths. For terms where `min-path ≠ max-path` to any ancestor, a sparse `level_is_best_effort: "true"` property is emitted (see below). Only GO produces this flag in practice.
- **Flat ontologies** (`TigrRole`, `CogFunctionalCategory`) get `level = 0` on every term. Keeps the explorer's helper uniform — `WHERE t.level = $target_level` works for every ontology without special-casing absence of the property.

### `level_is_best_effort` — sparse per-term flag

For variable-depth DAG terms (GO BP/MF/CC only) whose min-path to the namespace root differs from their max-path, the KG emits `level_is_best_effort: "true"` as a **string**, not a bool — biocypher has had bugs with bool-typed properties in the past, and the string form sidesteps them.

The property is **sparse**: emitted only when its value would be `"true"`, absent otherwise. Absence means "level is unambiguous for this term."

Consumer pattern:

```cypher
WHERE t.level_is_best_effort IS NOT NULL   -- ambiguous terms
WHERE t.level_is_best_effort IS NULL       -- unambiguous terms
```

No `coalesce` needed. The explorer's hierarchy helper and any enrichment tool flagging "level-N slicing is approximate" reads this property directly — it doesn't need to know which ontology a term belongs to.

This per-term flag replaces an earlier design that tagged each ontology with a `level_source` string. A per-term flag is more precise (only the GO terms that actually have ambiguity get flagged, not "all of GO") and is a free byproduct of the BFS that computes `level`.

## KEGG rename

`KeggTerm.level` is currently a **string** with values `{category, subcategory, pathway, ko}`. The KG implementation renames it to `level_kind` (same values, same semantics) and adds a new `level: int` with the `0/1/2/3` mapping. All KEGG-related explorer code switches to the int field; the string `level_kind` stays as a semantic label for callers who want `"pathway"` or `"ko"` directly.

`ONTOLOGY_CONFIG['kegg']['gene_connects_to_level'] = 'ko'` remains valid — gene→KEGG edges still terminate on leaf `ko` nodes, which now also carry `level = 3`.

Transition coordinated via KG-rebuild checkpoint: explorer code is updated in the same PR window as the rebuild so no version of either repo reads a missing or wrong-typed property.

## Derivation (adapter-side)

All derivation happens in the KG repo's biocypher adapters, not via post-import Cypher. Expected outcomes per ontology:

- **GO (BP/MF/CC):** Python BFS from canonical namespace roots (`GO:0008150`, `GO:0003674`, `GO:0005575`) through `is_a` + `part_of` parents. `regulates*` is **not** traversed. Implemented in `multiomics_kg/utils/go_utils.compute_go_levels`. Emits `level_is_best_effort: "true"` on terms whose min-path ≠ max-path.
- **EcNumber:** structural — the four-level nested iteration in `ec_adapter.py` assigns `level` per loop. Live distribution expected: 7/79/322/6,929 at levels 0/1/2/3.
- **CyanorakRole:** structural — walk parsed `parent` pointers in the role tree. Live distribution expected: 19/124/30 at levels 0/1/2.
- **KEGG, Pfam, PfamClan, TigrRole, COG:** fixed by kind, emitted directly in the relevant adapter.

## GO depth reference

Expected depth distribution for BP, observed in the live KG before rebuild (sanity-check against post-rebuild):

```
depth   n
1      16
2      98
3     274
4     565
5     721
6     650
7     462
8     211
9      42
10     10
11      2
```

## Deferred: ancestor closure

`level` alone leaves the hot path as `(Gene)-[:annotated]->(leaf)-[:is_a*0..]->(ancestor)` with `WHERE ancestor.level = $N`. Variable-depth BFS, bounded by the `level` filter. That's the pattern that hit the 1.4 GiB cap on one workload — but the blowup was specifically the unbounded fan-out of the intermediate cross-product. With `level` pruning the expansion, it may be enough. Measure first.

Two denormalization options are on the table if it isn't:

### Option A — Term-level `HAS_ANCESTOR` closure

One relationship per (term, transitive-ancestor) pair.

- **Cost:** low tens of thousands of edges across all hierarchical ontologies (order-of-magnitude estimate, not measured — KEGG's multi-parent DAG pushes its term-level closure up, but the total remains ~30× smaller than Option B). Negligible.
- **Query:** `(g:Gene)-[:annotated]->(leaf)-[:HAS_ANCESTOR]->(a {level: $N})` — fixed 2-hop, both typed and indexable. Kills variable-depth BFS.
- **Preserves** direct-vs-inherited distinction (enrichment cares).

### Option B — Gene-level annotation closure

Direct edges from gene to every ancestor term it inherits. Measured on the live KG:

| Ontology | Direct gene→term | Closure gene→ancestor | Expansion |
|---|---:|---:|---:|
| GO BP | 254,137 | 597,082 | 2.35× |
| GO MF | 170,314 | 463,350 | 2.72× |
| GO CC | 75,867 | 163,323 | 2.15× |
| EC | 33,235 | 105,351 | 3.17× |
| KEGG | 39,580 | 187,854 | 4.75× |
| CyanorakRole | 24,109 | 50,739 | 2.10× |
| **Total** | **~597k** | **~1.57M** | **~2.6×** |

- **Cost:** ~1.57M new edges. ~30× the size of option A. Meaningful storage (50–100 MB).
- **Query:** `(g:Gene)-[:ANNOTATED_AT]->(a {level: $N})` — one hop.
- **Tradeoff:** collapses every enrichment query to a single hop, but also the maintenance surface of the KG-build pipeline grows (closure regeneration on every annotation change).

### Recommended sequencing

1. **Phase 1 (this spec):** ship `level` only. Cheap. Unblocks the explorer's hierarchy helper and lets `ontology_landscape` work without BFS dispatch.
2. **Phase 2 (defer, measure first):** add option A (term-level closure) only if profiling `pathway_enrichment` at ~2k genes × ~110 pathways shows `level`-pruned BFS is too slow or too memory-hungry.
3. **Phase 3 (defer, unlikely):** option B is the nuclear option. Only if option A also fails.

## Bottom line

Phase 1 is cheap and obviously worth it: small per-term property, one-time build-pipeline BFS over GO, eliminates four dispatch strategies in the explorer, and strictly prunes the BFS that caused the 1.4 GiB incident.

Phase 2/3 are more expensive than the problem we've measured so far. `level` plus the explorer's existing internal batching fix (Child 1 of the enrichment surface) may be enough to keep the hot-path queries under the memory cap. Document the phase 2/3 options now so we have real numbers to revisit, but don't commit to them until `level`-alone profiling says we need them.

## Verification

After the KG rebuild, the following should hold:

```cypher
// Every ontology term has level set (hierarchical and flat alike)
MATCH (t) WHERE any(l IN labels(t) WHERE l IN
  ['BiologicalProcess','MolecularFunction','CellularComponent',
   'EcNumber','KeggTerm','CyanorakRole',
   'TigrRole','CogFunctionalCategory','Pfam','PfamClan'])
  AND t.level IS NULL
RETURN labels(t)[0] AS label, count(*) AS missing
// expected: 0 rows
```

```cypher
// Flat ontologies: all terms at level 0
MATCH (t:TigrRole) RETURN count(t) AS n, min(t.level) AS lo, max(t.level) AS hi
// expect n=114, lo=0, hi=0
MATCH (t:CogFunctionalCategory) RETURN count(t), min(t.level), max(t.level)
// expect 26, 0, 0

// Pfam / PfamClan: 2-level fixed-kind hierarchy
MATCH (t:Pfam) RETURN count(t) AS n, min(t.level) AS lo, max(t.level) AS hi
// expect n=5471, lo=1, hi=1 (including unlinked Pfams)
MATCH (t:PfamClan) RETURN count(t), min(t.level), max(t.level)
// expect 509, 0, 0
```

```cypher
// Roots exist at level 0 for each hierarchy
MATCH (t:CyanorakRole {level: 0}) RETURN count(t)  // expect 19
MATCH (t:EcNumber {level: 0}) RETURN count(t)      // expect 7
MATCH (t:KeggTerm {level: 0}) RETURN count(t)      // expect 6 (category)
```

```cypher
// GO BP level distribution matches BFS baseline (±0 after rebuild)
MATCH (t:BiologicalProcess) RETURN t.level AS level, count(*) AS n ORDER BY level
```

```cypher
// level_is_best_effort is sparse and string-valued
MATCH (t) WHERE t.level_is_best_effort IS NOT NULL
RETURN labels(t)[0] AS label, t.level_is_best_effort AS flag, count(*) AS n
// expected: only BiologicalProcess / MolecularFunction / CellularComponent, flag always "true"
```

## Stale entries in parent spec to remove

- **Pfam clan edges returning 0** — live KG shows 3,536/5,471 Pfams linked to PfamClan. Parent spec `2026-04-12-kg-enrichment-surface-design.md` §"KG requirements doc" item 2 should drop this item (the B1 `gaps_and_friction.md` claim was a stale KG-build-doc artifact).

## Dependencies

- Requires: existing ontology nodes and `*_is_a_*`/`*_part_of_*` edges (all present in live KG).
- Blocks: explorer's unified hierarchy helper lands as a one-line `WHERE t.level = $target_level` filter; removes BFS from the hot path for `ontology_landscape`, the redefined `genes_by_ontology`, and `pathway_enrichment`.

## Out of scope

- Materializing per-term gene counts (separate ask if/when warranted).
- Ancestor closure in either form — deferred, options documented above.
