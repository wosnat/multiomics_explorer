# KG asks from the explorer's review of the KG CHANGELOG (2026-11-01)

Origin: explorer review of the KG `CHANGELOG.md` `[Unreleased]` section (working tree, 2026-11-01)
ahead of the next paired release (explorer `0.1.0-alpha.6` + the next KG release).
Live KG checked: built 2026-10-31T19:34:27Z (`0.0.0-dev`, `mcp_min_version: 0.1.0a5`).

Summary: one contract bug (fixed on the explorer side; the KG docs need aligning), the Breaking
section is too long for where it ends up, four figures don't match the live graph, and two
follow-ups on the new schema-completeness guarantee.

## C1 — Breaking changes never reached clients: key name mismatch (P1, explorer fixed)

`/release-kg` stamps the `### Breaking` section as `Schema_info.release_breaking`
(`release_kg.py`, CHANGELOG header). The explorer's `kg_release_info` read
`Schema_info.breaking_changes`, so breaking notes would never have shown even on an official
release. **Fixed explorer-side** (commit `42b1675`): `kg.breaking_changes` is now filled from
`release_breaking`, falling back to `breaking_changes`.

Asks:
- Align the KG docs that still say `breaking_changes`: `plans/backlog.md:643`,
  `docs/kg-changes/metabolite-identity-and-classes.md` (lines 7, 517, 643),
  `docs/superpowers/specs/2026-10-13-metabolite-identity-and-classes-design.md` (1364, 1440),
  `docs/kg-changes/docs-review-asks.md:82`. No code change needed.
- On the release cut, set `mcp_min_version` to `0.1.0a6` (live is still `0.1.0a5`). Explorers
  older than alpha.6 fail on the `coculture_partner` list, as your Breaking section says. Order:
  explorer alpha.6 is tagged first, then the KG release.

## C2 — `### Breaking` is too long to stamp (P1)

The Breaking section is ~8.8 KB (~2.2k tokens, ~30 bullets). It is stamped verbatim onto
`Schema_info` and returned by `kg_release_info`, which the MCP server tells every client to call
first. Every session would pay ~2k tokens before its first question, and the header's own rule
("one bullet per silently-changed semantics") is lost in the detail.

Ask: keep `### Breaking` to one line per change, roughly 8–10 bullets and under ~2 KB, for
example:

- Expression significance follows each paper's own criterion (no default 2-fold cutoff); 22 papers change.
- Fold changes on 6 papers were on the wrong scale and are corrected.
- `expression_direction` is absent when `log2_fold_change` is 0.
- `Experiment.coculture_partner` is a `str[]` of every partner; role on `Tests_coculture_with.partner_role`.
- `OrganismTaxon.experiment_count` / `treatment_types` / … count the organism's own experiments only.
- Metabolite ids are re-keyed to one canonical form (remap TSV); role terms moved to `ChemicalRole`.
- TCDB: one edge per call with `tcdb_gate`; substrates on systems only; several properties renamed or removed.
- 182 KEGG pathways irrelevant to bacteria are dropped; enrichment backgrounds shrink.

Move the detail (counts, removed-property lists, file pointers) to a section the extractor does
not stamp, e.g. `### Data` or a new `### Breaking (details)`. Counts that aren't a change of
meaning ("`TcdbFamily` has 9,725 nodes", "123 `OrganismTaxon` nodes") belong in `### Data`.

Minor, same section: `### Highlights` has 6 bullets against the ~5 cap. The Cyanorak-coordinates
bullet could fold into the genomes bullet.

## C3 — Figures that don't match the live graph (P2)

Checked against the live build above. Verified as written: 123 OrganismTaxon, 3,251 Metabolite,
436 MetaboliteClass, 102 ChemicalRole, 9,725 TcdbFamily, 8,954 `Tcdb_family_transports_metabolite`,
186 `Tests_coculture_with`, 270 KEGG pathways / 24 subcategories, 16,423 `[tcdb_best_hit]` genes.

| CHANGELOG says | Live | Ask |
|---|---|---|
| Highlights: "74 more picocyanobacterial genomes (now 116 genome strains)" | 118 organisms with genes (Prochlorococcus 45, Synechococcus 51, Cyanobium 3, Alteromonas 11, 8 others); 102 picocyanobacteria | Say which count 116 is, or use 118 |
| Highlights: "a partner search also finds the 35 experiments where the coculture was the context" | 77 experiments have a `background` partner edge; `coculture_partner="Alteromonas"` alone finds 48 background experiments | 35 seems to be the newly named ones (Data section); the highlight reads as the total. Reword or use 77 |
| Breaking: significant edges 102,557 → 113,725 ("over the previous corpus") | 113,669 significant edges | Fine as labelled, but readers will compare with the live graph; consider quoting the live figure too |
| Breaking: `expression_direction` absent on 1,510 edges | 1,509 edges with `log2_fold_change = 0`, all without direction | Off by one; check |

## C4 — Schema completeness follow-ups (P2)

Thanks for the complete `Schema_info.schema_info`. The explorer now uses it: `kg_schema` takes
property names and types from the declaration and only scans the graph for undeclared labels.
Your count of 72 missing properties matches ours (68 node + 4 relationship) on the current build.

Asks:
- **The reverse direction.** 18 declared properties are set on no node or edge in the live graph,
  so `kg_schema` now lists them. Please either drop them from `schema_config.yaml` or add the
  reverse check to `test_schema_coverage.py` with an allowlist for the legitimately optional ones
  (e.g. `p_value` on derived-metric edges, set only when a metric has p-values):
  - `BiologicalProcess` / `CellularComponent` / `MolecularFunction`: `anc2vec_embedding`
  - `EcNumber`: `rxnfp_embedding`, `level_is_best_effort`
  - `level_is_best_effort` on `CogFunctionalCategory`, `CyanorakRole`, `KeggTerm`, `Pfam`, `PfamClan`, `TigrRole`
  - `DerivedMetric.p_value_threshold`; `Derived_metric_quantifies_gene`: `p_value`, `adjusted_p_value`, `significant`
  - `Gene_in_gene_cluster.p_value`; `Protein.subcellular_location`; `Publication.pmid`
- **Label rule.** The explorer maps schema entries to Neo4j labels with the same rule as
  `_label()` in `test_schema_coverage.py` (`label_as_edge` capitalised, else the key in
  PascalCase). Please tell us if that rule changes.

## Status

Open. C1's explorer side is done; C1's doc alignment, C2, C3 and C4 are KG-side.
