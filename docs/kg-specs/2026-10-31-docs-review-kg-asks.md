# KG asks from the explorer docs review (2026-10-31)

**Status (KG answer + rebuild 2026-10-31T19:34:27Z, absorbed same day):** K1 not a bug — TCDB's own
grouping; `superfamily` now set on 257 families / 986 subfamilies / 6,025 systems, never class / subclass
(tcdb ontology page reworded). K2 fixed (new id `…:presence_flags_table_s2_extracellular:presence_flag_extracellular`,
`compartment='extracellular'`). K3 fixed (BIOINFORMATIC 11 / RNASEQ 8 / MICROARRAY 7; new vocab entry, hash
re-pinned `e3147f37…`). K4 intended (bacterial-relevance pruning). K5 not reproduced (no empty `metric_type`).
K6 open.

Origin: explorer Phase 1b docs review before the release after v0.1.0-alpha.5.
Live KG checked: built 2026-10-31T14:01:03Z (git b87b08ff, local-dev).

## K1 — `TcdbFamily.superfamily` holds the wrong superfamily name (P1)

`superfamily` doesn't name the node's own superfamily; it appears to be shifted or mis-joined.

| id | name | superfamily (live) |
|---|---|---|
| tcdb:3.A.1 | The ATP-binding Cassette (ABC) Superfamily | ArsA ATPase (ArsA) Superfamily |
| tcdb:3.A.1.7.1 | Phosphate porter, PhoSPstABC. | ArsA ATPase (ArsA) Superfamily |
| tcdb:3.A.3 | The P-type ATPase (P-ATPase) Superfamily | Heavy Metal Binding Domain |

838 nodes carry "ArsA ATPase (ArsA) Superfamily". The value is also null on some intermediate
levels (tcdb:3.A.1.7 is null while its child 3.A.1.7.1 is set), so it is inconsistent down the tree.

Check: `MATCH (t:TcdbFamily) WHERE t.superfamily IS NOT NULL RETURN t.superfamily, count(*) ORDER BY count(*) DESC`
and compare a sample against TCDB's superfamily table. Expected: ABC members read the ABC superfamily
(or null if TCDB assigns none); the value is either set on every level under a superfamily or documented
as leaf-only. The explorer shows this property in `search_ontology` / `ontology_term_details` verbose output.

## K2 — `presence_flag_extracellular` assay labelled `compartment='whole_cell'` (P2)

`metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_extracellular`
(name "Detected in extracellular pool (Kujawinski 2023 Table S2)") has `compartment='whole_cell'`, the same
as its intracellular twin. The `by_compartment` envelopes on `list_metabolite_assays` / `metabolites_by_flags_assay`
therefore can't separate the two pools. Expected: `compartment='extracellular'` (a value already in the
compartment vocabulary). Please also check the other Kujawinski 2023 assays for the same copy-over.

## K3 — Clustering analyses with empty-string `omics_type` (P3)

The 11 `ClusteringAnalysis` nodes with `cluster_type='genomic_island'` have `omics_type=''`, so
`list_clustering_analyses` reports `by_omics_type: [{"omics_type": "", "count": 11}]`. Expected:
`BIOINFORMATIC` (as the genomic_analysis experiments carry), or null. Never the empty string.

## K4 — confirm intent: KEGG level counts dropped (P3, question only)

Live KEGG level sizes are 5 categories / 24 subcategories / 270 pathways / 4,808 KOs. The explorer docs
had 6 / 46 / 447 / 4,644 from an earlier build. Was the drop in categories, subcategories and pathways
intentional, e.g. pruning to nodes with organism genes? If yes, nothing to do. The explorer docs are
being updated to the live values.

## K5 — unverified: empty `metric_type` on an assay (P3)

Reported by a reviewer, not yet re-checked (Neo4j was down mid-review): `metabolites_by_quantifies_assay`
`by_metric[*].metric_type` is `""` for the MIT9313 PNAS assay. Check
`MATCH (a:MetaboliteAssay) WHERE a.metric_type IS NULL OR a.metric_type = '' RETURN a.id`.

## K6 — unverified: TCDB `tier` wording in the `trust_axes` vocabulary (P3)

`Gene_has_tcdb_family.tier`'s own description is correct (consensus tier on `diamond_tier`, identity band
on `diamond_best_hit`, absent on eggNOG). A reviewer reports the `trust_axes` value description for TCDB
still reads "Diamond-truncation depth". If so, align it with the edge-property description.

## Not KG-side (recorded for completeness)

- `tcdb_family_substrates_skipped` lists the same 4 MED4 ABC genes (PMM0449/0450/0913/0977 →
  tcdb:3.A.1, 546 substrates) for every compound queried. This is how the explorer reports genes it skips
  because the family is too broad. It is explorer-side and goes in the explorer backlog.
