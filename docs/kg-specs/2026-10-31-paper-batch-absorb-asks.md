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

_(KG side, 2026-10-31; branch `fix/interpro-retired-entries`, lands with the next rebuild)_

### B1 — fixed: retired accessions are dropped

Rule chosen: **drop**. The 38 are accessions our InterProScan 5.78-**109.0** calls still carry but
InterPro release **110.0** (3 Sep 2026, the refreshed reference) deleted. 35 of them are auto-named
PANTHER families (`IPR051465` "Cell Envelope Structural Component", `IPR050059` "ATP synthase B
chain", …); the rest are one NCBIfam (`IPR053376`), one PIRSF (`IPR030963`) family and two
singletons (`IPR046780` Pfam, `IPR001423` PROSITE). The gene-level merge already treated them as
gone (their GO / EC cross-references left with the refresh), so dropping the nodes makes the two
layers agree.

- `interpro_adapter`: an accession absent from `interpro_reference.json` yields no node and no
  `Gene_has_interpro_entry` edge; the build log lists each with its edge count. The fallback that
  wrote `name = ''` / `interpro_type = ''` is gone, and `kept_ids` never keeps an accession the
  reference does not list.
- Measured on the current cache: `InterproEntry` **13,352 → 13,314** (−38, none with an empty name
  or type), `Gene_has_interpro_entry` **945,741 → 944,076** (−1,665). So
  `search_ontology_browse_interpro_med4_scoped.total_entries` moves by −38 (13,314 if that golden is
  corpus-wide; recount if MED4-scoped).
- `Gene.interpro_entry_count`, `Gene.annotation_types` ('interpro') and
  `OrganismTaxon.interpro_gene_count` are post-import counts over the edges, so they drop for the
  ~1,549 affected genes. A gene whose only InterPro hit was a retired entry loses 'interpro'.
- The 59 `genes_by_function(search_text="cell division", organism="Synechococcus")` genes do not come
  back: the retired entry's name is no longer InterPro's text for that gene. Expect the smaller set.
- Tests: unit (`tests/test_interpro_adapter.py`) for the drop; KG
  `test_interpro_entry_required_properties` now requires a non-empty `name` and no longer accepts
  `''` as an `interpro_type` (it had `''` in its allowed set, which is why the 38 shipped). It fails
  on the current graph and passes once rebuilt.
- Source fix (re-scan all strains with InterProScan 110, which also brings the +854 new entries) is
  in the KG backlog.

### B2 — CHANGELOG updated

- `### Changed`: "InterPro reference refreshed to release 110.0", with the entry counts (+854 / −122),
  the EC / GO / description-line deltas over the merged annotations, the 3 genes that move
  `informative_multi` → `informative_single`, and the 38 dropped accessions with node and edge counts.
- DSS-3: amended in place in the Ferrer 2020 `### Data` bullet (the paper is new in this unreleased
  cycle). The xlsx's "New Locus Tag" / "Protein Tag" columns are shifted one row against "Original
  Locus Tag" in the megaplasmid block, and ~370 accessions come from an older RefSeq annotation. The
  builder blanks the 100 tags and 467 accessions that contradict NCBI's pairing. That took DSS-3's
  gene-ID conflicts from 90 to 0; **no resolved row moved to a different gene** (Ferrer stays 4,229 /
  4,277).
- PCC7942 and ATCC27126 were not re-mapped as a fix: their committed mappings predated the Rubin 2015
  and Manck 2020 / Koch 2020 paperconfigs, and the full rebuild added those papers' ids. No resolved
  row of any paper changed gene, so this is not logged separately.

### Explorer — closed 2026-10-31

Verified on build `2026-10-31T11:20:55.444Z` (KG `d3020457`): `InterproEntry` 13,314, none with an
empty `name` / `interpro_type`; `Gene_has_interpro_entry` 944,076. The 2 held goldens regenerated
(the landscape has no `''` row; the Synechococcus "cell division" set stays at 14,475 as you
expected); `interpro_gene_count` −1 on 9 organisms; InterPro `total_entries` 13,352 → 13,314.
B1 and B2 closed.
