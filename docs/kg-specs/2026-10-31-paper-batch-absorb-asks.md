# Paper batch 2026-10-28 + InterPro refresh rebuild — explorer findings (2026-10-31)

**Date:** 2026-10-31 · **From:** explorer (`multiomics_explorer`) · **To:** KG (`multiomics_biocypher_kg`)
**Direction:** explorer → KG.
**Build:** `2026-10-31T08:59:10.026Z` (`0.0.0-dev`, `local-dev`; KG `932846d1` "rebuild cache with
new papers; dss3 remap fix", on merge `51a7dfa9` data/paper-batch-2026-10-28).

Found while absorbing the rebuild. Everything else in the build matched the CHANGELOG (10 papers,
A. macleodii 83-1, *T. pseudonana*, `treatment_type` `mutant` / `essentiality`, first `DNASEQ`
experiment). B1 holds 2 goldens back from the absorb. Please answer in a "Responses" section at
the end.

## B1 — 38 retired InterPro entries survive as nodes with empty `name` and `interpro_type` (blocking 2 goldens)

The refreshed `cache/data/interpro/interpro_reference.json` (InterPro `current_release`) has
54,922 entries: +854 / −122 against the previous reference. 38 of the removed accessions are
still emitted by the genes' InterProScan calls (the merged annotations' `interpro_entries`), so the
adapter builds an `InterproEntry` for them with no reference row:

```cypher
MATCH (i:InterproEntry {interpro_type: ''}) RETURN count(i)                 // 38 (also name = '')
MATCH (g:Gene)-[r:Gene_has_interpro_entry]->(i:InterproEntry {interpro_type: ''})
RETURN count(r), count(DISTINCT g), count(DISTINCT g.organism_name)          // 1,665 / 1,549 / 118
```

Examples: `interpro:IPR050059` (was "ATP synthase B chain", 118 genes), `IPR050071`, `IPR050075`
(~120 genes each), `IPR001423` (was "Lysophospholipase NTE1"). None of the 38 is announced in the
CHANGELOG.

What it breaks on the explorer side:

- `''` is outside the closed `interpro_type` vocabulary (`FAMILY`, `DOMAIN`, …, `PTM`).
  `ontology_landscape` (MED4) grows an `interpro_type: ''` row, and `interpro_type=` filters,
  required on InterPro enrichment, can never select these entries.
- The genes lose the entry's name text from search. `genes_by_function(search_text="cell division",
  organism="Synechococcus")` drops 59 genes, every one linked to one of the 38 (e.g. `H6G84_10955`
  iron uptake porin, `BL107_12315` possible porin).

**Ask:** pick one rule and apply it in the adapter. Either drop the gene edges to accessions the
reference no longer has (and log them), or keep the node with its last-known name / type from the
previous reference. Re-running InterProScan against the new release would also fix it at the
source. Add a KG test so `InterproEntry` never carries `name = ''` or `interpro_type = ''`.

**Held back until fixed:** goldens `ontology_landscape_med4_all_no_filter`,
`genes_by_function_synechococcus_filter`. If the fix drops the 38 nodes,
`search_ontology_browse_interpro_med4_scoped.total_entries` (13,352 now, regenerated in this
absorb) moves again by −38.

## B2 — CHANGELOG: InterPro refresh and the DSS-3 remap are not logged

`932846d1` refreshes `interpro_reference.json` (+854 / −122 entries; MED4 InterPro FAMILY genes at
level 0 move 1,167 → 1,161; e.g. 6 CDP-glycerol glycerophosphotransferases across 6 organisms now
match "polymerase") and re-maps DSS-3 / PCC7942 / ATCC27126 gene ids. Neither is in `[Unreleased]`.
Please add a `### Changed` bullet naming the InterPro release and the counts, and the DSS-3 remap
fix (what was wrong, how many rows moved).

## Responses

_(KG side)_
