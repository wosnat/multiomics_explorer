# Changelog

All notable changes to `multiomics_explorer` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow the scheme `X.Y.Z[-(alpha|beta|rc).N]` (mirrors the KG repo)
and are tagged `vX.Y.Z…`.

**Process (accumulate-then-cut):** log notable changes under `[Unreleased]` as
they land. At release time, `/release-explorer` *cuts* `[Unreleased]` into a
dated version section, stamps the same version onto `pyproject.toml`, and
renders the GitHub Release notes from that section. The changelog is the
source of truth; the GitHub Release is a rendering of one section. See
`.claude/skills/release-explorer/SKILL.md`.

**Cross-repo contract:** the KG declares its minimum-compatible explorer
version via `Schema_info.mcp_min_version`. When a release here changes the
contract (new MCP tools, breaking arg shape, return-shape changes), bump
the version accordingly and coordinate with the KG-side `mcp_min_version`
ahead of the KG release. See KG plan §2.3 for the coordination dance.

## [Unreleased]

### Breaking
- **TCDB surface follows the KG 3a cleanup** (spec `docs/tool-specs/tcdb-cleanup-surface.md`; dialog `docs/kg-specs/2026-10-23-tcdb-cleanup-explorer-asks.md`; branch `tcdb-cleanup-surface`). Every gene → TCDB traversal now reads the KG's `tcdb_gate` (`direct` / `annotated` / `below_gate`), so rows and the KG precomputes come from one edge set. No aliases for anything removed.
  - **Removed:** `substrate_depth` (param, row field, `by_substrate_depth`, `transport_most_specific_rows` / `transport_inherited_rows`), `tcdb_evidence_score`, `tcdb_evidence_score_max`, `transport_substrate_resolution` and the `family_inferred` warnings on `genes_by_metabolite` / `metabolites_by_gene` / `gene_overview`; `include_superseded` on `gene_ontology_terms`; TCDB's `evidence_score` trust axis (`min_evidence_score` with `ontology='tcdb'` now raises), and the TCDB edge columns `confidence_score`, `source_agreement`, `pfam_support`, `go_support`, `consensus_n`, `attachment_depth`; TCDB term column `metabolite_count`; `level_kind` `tc_specificity` (now `tc_system`).
  - **Renamed:** `gene_overview.tcdb_family_count` → `tcdb_assignment_count` (follows the KG; `has_tcdb` reads it).
  - **Transport arm:** rows come from `direct` edges only, one row per gene × system × metabolite, with `tcdb_route`, `tcdb_calls` (call kinds on the row's lineage), `tcdb_identity`, `tcdb_direction`, `attached_tcdb_id`, `tcdb_substrate_system_count`; envelope `by_tcdb_route`, `tcdb_direct_rows` / `tcdb_family_rows`. Counts drop sharply because family roll-ups are gone (MED4 organism transport count ~1,200 → 136).
  - **Ontology tools (TCDB):** gated by default; one row per (gene, term) with a representative edge (best hit > tier > eggNOG, then identity) plus compact `tcdb_call` / `tcdb_gate` / `tcdb_calls`; verbose `tcdb_scov` / `tcdb_best_hit_rank` / `tcdb_bitscore` / `tcdb_bitscore_ratio`. Leaf-mode rows equal `Gene.tcdb_assignment_count`; TERM2GENE genes equal `TcdbFamily.gene_count`.

- **`coculture_partner` is now `list[str]`, not `str | None`** (KG contract change 2026-10-13; dialog in `docs/kg-specs/2026-10-13-coculture-partner-list-explorer-asks.md`). It lists every organism sharing the culture (sorted `preferred_name`s): treatment partners (coculture-vs-axenic, phage infection) **and** background partners (the culture was a coculture, the contrast is something else). `[]` when axenic. Affects `list_experiments` rows, `differential_expression_by_gene` verbose `experiments[]` and verbose rows, and `differential_expression_by_ortholog` rows (compact). On the new KG build an explorer without this change fails on all three tools: `list_experiments` raised a Cypher type error with `coculture_partner=` and a Pydantic validation error without it. Each partner's role lives on the `Tests_coculture_with` edge (`partner_role`); `'coculture' IN treatment_type` does not give the role (phage experiments are `viral`). The KG release will set `mcp_min_version` to the next explorer version.

### Added
- **TCDB opt-ins and hints** (same spec). `include_tcdb_family_substrates` on `genes_by_metabolite` / `metabolites_by_gene`: a fallback walk from a gene's family / subfamily call to its systems' substrates (`tcdb_route='family'`); never from class / subclass, never above a direct system, skips start nodes with > 200 substrates (ABC / MFS superfamilies) and nodes with none; only adds rows. Envelope `tcdb_family_substrates_not_shown` (what the walk would add; e.g. orthophosphate in MED4: 0 direct genes, 4 via the walk) and `tcdb_family_substrates_skipped`, with warnings. `include_weak_tcdb_hits` on `gene_ontology_terms` / `genes_by_ontology` adds `below_gate` rows without changing the default ones (gene-set size bounds use the gated count). `tcdb_call` filter on the five tools that take `call_class`; `by_tcdb_call` envelope (always present, like `by_call_class`). `gene_overview.tcdb_best_hit_identity`. TCDB term columns `tcdb_substrate_count`, `direction`, `direction_basis`. `list_filter_values` serves `tcdb_call`, `tcdb_gate`, `direction`. Docs: `docs://analysis/transport` "Reading a TCDB row", `docs://ontologies/tcdb` rewrite, tool YAML examples / mistakes, two new outfacing-lint patterns.


- **GO transport follow-ups** (spec `docs/tool-specs/go-transport-followups.md`; backlog 2c.14–2c.17). `genes_by_metabolite` / `metabolites_by_gene`: GO-arm filters `go_namespace` (`molecular_function` / `biological_process`) and `go_evidence` (gene→GO evidence class, validated against the KG vocabulary), applied to direct and inherited GO rows and never to KEGG / TCDB rows; set with the GO arm off they are ignored with a warning. Both tools gain a route-agreement rollup: envelope `by_evidence_source_combination` (`{evidence_sources, pair_count}` per gene × metabolite pair), `multi_source_gene_count` on gbm `by_metabolite[]` / mbg `top_metabolites[]`, `multi_source_metabolite_count` on gbm `top_genes[]` / mbg `by_gene[]`. `gene_overview` and `list_organisms` rows gain `go_transport_metabolite_count` (distinct metabolites through direct GO transport terms; roles excluded), also carried on `top_metabolic_capability[]`. Docs: `docs://analysis/transport` agreement + filter text, tool YAML examples / mistakes. Additive; no `mcp_min_version` bump.
- **GO transport surface on `genes_by_metabolite` / `metabolites_by_gene`** (spec `docs/tool-specs/go-transport-surface.md`, design `docs/superpowers/specs/2026-10-20-go-transport-surface-design.md`; backlog 2c.13; branch `go-transport-surface`). A third arm, `evidence_source='go_transport'`, is on by default: rows per gene x GO term x target, carrying `go_*` row fields (term id / name / namespace, annotation evidence) plus `target_kind`. Opt-in `go_include_ancestors` adds ancestor-term rows with `go_term_depth` / `go_axiom_term_*`; envelope gains `rows_by_go_term_depth` (null when the arm is off). `chebi.role:` inputs now reach GO and TCDB role edges. New warnings for filtered GO targets and for neurotransmitter-type targets. `kg_release_info` surfaces `go_transport_excluded_targets`. `kg_schema` relationship descriptions come from `config/edge_descriptions.yaml`. New `docs://analysis/transport` recipe page (listed in server instructions).
- **Control-arm timing on experiments and DE rows** (spec `docs/tool-specs/control-timing-surface.md`; backlog D6). `timepoint` / `growth_phase` describe the treatment arm; the new curated `control_timing` says whether the control was sampled at the same time or growth state (`matched`), at another time (`baseline`) or partly (`mixed`), and `design_notes` says how. `list_experiments`: compact `control_timing` (null without DE) and `design_notes` (omitted when absent), new `control_timing` filter (closed-vocab warning on unknown values), `by_control_timing` summary; `search_text` now documents that `design_notes` is indexed. `list_filter_values(filter_type='control_timing')`. `differential_expression_by_gene` / `differential_expression_by_ortholog`: `control_timing` on every row; by-gene `experiments[]` envelope gains `control_timing` and `design_notes`. `docs://guide/conventions` gains the treatment-arm paragraph; `control_timing` joins the vocab snapshot + docs-lint contexts. 16 goldens regenerated (new keys only — every existing value identical); 26 example responses refreshed. Additive; no `mcp_min_version` bump.
- **Stereo-form hint** (spec `docs/tool-specs/metabolite-stereo-hint.md`, backlog 2c.8 part 3). Stereo forms are separate `Metabolite` nodes and no count combines across `Metabolite_is_stereo_form_of`: TCDB substrate lists name compounds generically (transport on the unspecified node, e.g. Cysteine `C00736`: 0 catalysts), KEGG reactions use the specific form (catalysis on L-Cysteine `C00097`). `list_metabolites` rows gain sparse `stereo_relatives` (KG-wide counts; `specific_form` / `unspecified_form` / `enantiomer`). `genes_by_metabolite` and `metabolites_by_gene` gain an organism-scoped `stereo_relatives` envelope (generic ↔ specific relatives with genes in the organism; `reaction_count` / `transporter_count` / `gene_count` equal a re-call's `by_metabolite`), sparse `stereo_relative_ids` markers, and one warning listed first. `genes_by_metabolite(include_stereo_forms=True)` adds those relatives to the query (rows and `by_metabolite` entries tagged `via_stereo_form_of`, envelope `stereo_forms_added`); enantiomers are never hinted or added. Docs: `docs://analysis/metabolites` "Stereo forms" section, `conventions` chemistry paragraph, tool YAML mistakes / examples.
- **Metabolite resolver: removed stereo-specific ids warn.** An id the KG removed from a stereo-unspecified node because it names a more specific stereo form with no node of its own (`Metabolite.removed_stereo_xrefs`, e.g. D-pipecolic acid `chebi:41582` on pipecolic acid `chebi:17964`) stays in `not_found` with a warning naming that node, on all 7 metabolite-id tools.
- **Metabolite identity surface** (spec `docs/tool-specs/metabolite-identity-surface.md`, backlog 2c.8 parts 1–2). **Metabolite ids in any form resolve** on the 7 metabolite-id tools (`list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`, `list_metabolite_assays`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite`): bare or prefixed KEGG / ChEBI / MNX / HMDB / InChIKey ids are normalised to the KG's CURIE form and looked up in `Metabolite.all_identifiers`, so ids retired by the identity rebuild (e.g. `chebi:14654` → nitrate `kegg.compound:C00244`) map to the current node and appear in `resolved_aliases`; a removed measurement-only compound (`recurated_from_ids`) or a chemical-role id stays in `not_found` with a warning naming where to look. `list_metabolites`: the `kegg_compound_ids` / `chebi_ids` / `hmdb_ids` / `mnxm_ids` filters match any identifier (incl. secondary and retired ones); new `structure_kind` (`defined` / `generic` / `polymer`), `kegg_functional_categories` (KEGG br08001) and `kegg_brite_classes` (7 other KEGG compound trees, `Tree: Class`) — row fields, filters, and `by_structure_kind` / `by_kegg_functional_category` / `by_kegg_brite_class` envelopes ending in a `"not classified"` count. The three assay drill-downs gain `stereo_assignment` (`as_reported` / `dominant_form_assumed`) as a row field, filter and `by_stereo_assignment` envelope, plus a warning when rows assume the dominant stereo form. `list_filter_values` gains `structure_kind`, `kegg_functional_category`, `kegg_brite_class`, `stereo_assignment`. Docs: KEGG classification methodology (hand-curated, partial; absence ≠ negative), id resolution, lumping defined by `TcdbFamily.substrate_breadth`, `ChemicalRole` / `MetaboliteClass` few-shot queries.
- **Coculture partner roles on `list_experiments`.** New `coculture_role='treatment' | 'background'` filter keeps experiments with a partner of that role (`treatment` = the partner's presence is the contrast — coculture vs axenic or phage infection; `background` = the culture was a coculture, the contrast is something else); combined with `coculture_partner=` the role and the name must hold for the same partner. Verbose rows gain `coculture_partners: [{name, role, organism_id, organism_type}]` (sorted by name, `[]` when axenic; `organism_type='genome_strain'` means the partner has genes in the KG). The envelope gains `by_coculture_role` (experiments per role; always present). `list_filter_values(filter_type='partner_role')` serves the `Tests_coculture_with.partner_role` edge vocabulary (ControlledVocabulary read, pivot fallback + warning). Docs: `list_experiments` examples/mistakes (role vs `treatment_type=['coculture']`, pooled `['axenic', 'coculture']` designs, phage = `treatment` + `viral`), DE-tool chaining to `list_experiments(experiment_ids=…, verbose=True)` for roles, `conventions` organism-naming note. Live: `coculture_partner="Alteromonas"` → 5 treatment / 48 background.

### Changed
- Absorbed the KG dev rebuild of 2026-10-24T17:33:40.709Z (`0.0.0-dev`, `local-dev`; KG merges `8840a5ce` TCDB cleanup 3a + `d4ea8e9f` post-3a fixes; KG doc `tcdb-cleanup.md`). TCDB: 1,515 → 9,370 `TcdbFamily` nodes (range-only systems; three retired families remapped), one gene edge per source with `tcdb_gate`, substrates on `tc_system` only; genes with a transport arm ~30K → 6,981 (14 eggNOG genes lost theirs when remapped onto CorC `1.C.126.1.2`, which has no curated substrates). 65 transport-only metabolites removed (Metabolite 3,243 → 3,178; ouabain exemplar → digoxin `C06956`), icosanoid re-keyed; 182 KEGG pathways dropped as non-bacterial (449 → 267; Moreno 2023 `map04710` discusses edge gone); MEROPS `qcov` declared percent; `stereo_assignment` judged from ChEBI enantiomer links (msystems flags 21 → 23 dominant-form). gene_count 127,035 unchanged. `controlled_vocabularies_hash` re-pinned `eaf6e672…` → `7e2ada52…`; vocab snapshot drops `attachment_depth` / `substrate_depth`, tracks `tcdb_call` / `tcdb_gate` / `direction`. `schema_baseline.yaml`: targeted TCDB update (full re-capture samples and drops sparse props). 50 goldens regenerated (TCDB surface + announced data moves; 4 non-TCDB `genes_by_ontology` goldens gain only `by_tcdb_call: []`); 22 live pins moved with the rebuild (`list_metabolites` element / transport counts, `3.A.1` children 55 → 98 and links 128 → 11, stereo counts, GO-transport passthroughs); 117 example responses refreshed. KG-side follow-ups: `TcdbFamily.superfamily` reads "ArsA ATPase" across the ABC subtree (asks doc B1); dropped-pathway TSV (ask A1). -m kg: integration 3,304 passed, regression 184 passed; unit 6,953 passed.
- **Default-on GO rows change the numbers** (go-transport surface). `genes_by_metabolite` / `metabolites_by_gene` totals grow (urea in MED4: 34 -> 45 rows); `metabolites_by_gene` TCDB rollups now include TCDB role rows (e.g. PMM0065 transport 38 -> 40, PMM0392 12 -> 13). `gene_overview.evidence_sources` gains `go_transport` and `has_chemistry` widens to the direct GO route. `list_metabolites` organism filter and `top_organisms` are the union with `go_transport_organism_names`; rows carry `go_transport_organism_count` / `_names` (Alteromonas counts +15; MED4 `no_formula_excluded` 171 -> 176). The `metabolites_by_gene` stereo hint counts the three default arms. Tests: 19 goldens and 4 live-count pins regenerated; unit 6409 passed / 47 skipped, integration 3153 passed, regression 184 passed. The KG note's claim that adding `go_transport` moves `controlled_vocabularies_hash` is wrong: the hash recipe does not hash descriptions and `Metabolite.evidence_sources` is open, so the hash did not move at 2026-10-18T18:40Z.
- Absorbed the KG dev rebuild of 2026-10-19T17:03:46Z (`0.0.0-dev`, `local-dev`; KG commits `14022820` / `20b43309`, KG doc `tcdb-diamond-best-hit.md`): **TCDB diamond best hit + TCDB family-name fix.** Six new sparse open properties on `Gene_has_tcdb_family` (`best_hit_tcids`, `best_hit_names`, `best_hit_identity`, `best_hit_substrate_tcids` / `_ids` / `_names`) — absorbed only, not surfaced (out of explorer scope). Bug fix: 31 `TcdbFamily.name` values cut mid-parenthesis by the TCDB scraper were re-derived (`3.A.1.4.4` "The high-affinity (" → "The high-affinity (<1 μM) urea porter"). No node or edge added or removed. gene_count 127,035 unchanged. `controlled_vocabularies_hash` re-pinned `89c63aa0…` → `eaf6e672…` (verified: the KG recipe over the vocabulary minus the six `best_hit_*` entries reproduces the old hash). 5 goldens regenerated (4 `genes_by_metabolite` urea goldens: the name fix; `search_ontology_multi_go_bp_tcdb_transport`: TCDB Lucene scores from the changed name text); 0 live pins; 3 example drifts refreshed (`genes_by_metabolite`, `search_ontology`). `-m kg`: regression 184, integration 3,060 green; unit 6,316.
- Absorbed the KG dev rebuild of 2026-10-18T18:40:46Z (`0.0.0-dev`, `local-dev`; KG merge `c52c3580`, KG doc `go-transport-substrates.md`, explorer asks `docs/kg-specs/2026-10-18-go-transport-substrates-explorer-asks.md`): **GO transport substrates → Metabolite edges** (transport programme project 1). Four new edge types from GO terms (`Molecular_function_transports_metabolite` 257, `Biological_process_transports_metabolite` 246, `…_transports_chemical_role` 7 + 8; property `go_chebi_ids`); `Metabolite.evidence_sources` gains `go_transport` (208 metabolites); `Metabolite` 3,214 → 3,243 (+29 GO-only substrates: 25 generic, 4 defined); sparse `Metabolite.go_transport_organism_names` / `_count`; `Schema_info.go_transport_excluded_targets` (13 ids). ko02010 +2 / ko01100 +1 pathway metabolites. TCDB / KEGG / assay, `organism_count`, `transporter_gene_count` and `catalyst_gene_count` unchanged. gene_count 127,035 and `controlled_vocabularies_hash` unchanged — `Metabolite.evidence_sources` is an open vocabulary and the KG recipe does not hash descriptions (the KG note's "moves the hash" is wrong). 9 goldens regenerated (`list_metabolites` rollups + `metabolites_by_gene_pmm0392_med4_transport` `pathway_metabolite_count` 1,626 → 1,627; no shape changes); 5 live pins (N-bearing 1,692 → 1,694, generic+polymer 650 → 675, Peptides 60 → 61, not-classified tails, evidence_source values + `go_transport`); 8 example drifts refreshed (`list_filter_values`, `list_metabolites`); `kg_claims` coverage figures re-based to 3,243 + new `metabolite_go_transport_route`; `docs://analysis/metabolites` names the fourth evidence value. Not surfaced yet: the `list_metabolites(evidence_sources=…)` `Literal` and the field descriptions still list three values, and no drill-down walks the GO route — that is the TPS-001 surfacing follow-up. -m kg: regression 184, integration 3,060 green; unit 6,316.
- Absorbed the KG dev rebuild of 2026-10-18T13:42:30Z (`0.0.0-dev`, `local-dev`; KG commits `b7da1e9a` / `62b7b5db`): **GO release update** — one pinned GO release (go-basic + go-plus together, 2026-07-26) and alt_ids of live GO terms recovered on gene→GO edges. GO terms: BP 3,433 → 3,322, MF 2,899 → 2,890 (CC 451); GO term levels shift (e.g. 6 → 5 on the `gene_ontology_terms` BP exemplar); MED4 `go_bp` level-1 rollup 429 → 447 rows / 349 → 365 genes; `go:0005548` (phospholipid transporter activity) retired, so TCDB `3.A.1` `links_out` 129 → 128. No non-GO ontology moved. gene_count 127,035 and `controlled_vocabularies_hash` unchanged (vocab snapshot stamp only). 12 goldens regenerated (all GO-only content; no envelope key / type / `truncated` changes); 5 live pins moved (3.A.1 links ×3, composition 130 → 129, GO BP level-1 rows/genes); 11 example drifts refreshed across 4 tool YAMLs (39 blocks rewritten; `genes_by_ontology` examples also pick up the already-shipped `size_filtered_*` / `resolved_aliases` keys). `-m kg`: regression 184, integration 3,059 green; unit 6,315.
- Absorbed the KG dev rebuild of 2026-10-18T07:51:00Z (`0.0.0-dev`, `local-dev`; KG commits `0a45f807` / `2866e6d7` / `9423292a`): **control-timing curation pass + paperconfig corrections + Anjur-Dietrich published.** New curated `Experiment.control_timing` (`matched` / `baseline` / `mixed`; new closed `ControlledVocabulary`) and sparse `Experiment.design_notes` (in `experimentFullText`); live 151 `matched` / 18 `baseline` / 4 `mixed` over 173 DE experiments (the KG changelog's 150 / 21 / 3 over 174 predates the closure pass and the Thompson merge). `statistical_model_id` was dropped KG-side before it shipped. Explorer does not read either property yet; `schema_baseline.yaml` gains both. Data moves: Thompson 2011's MED4 48h contrast is now a timepoint of the starvation experiment (Experiment 209 → 208); Weissberg 2025's two "axenic long-term" RNA contrasts are removed (MED4 −1,849 DE rows), the HOT1A3 axenic proteome gains day 89, MED4 axenic day-14 reads `death`, and experiments are renamed axenic / coculture; Oleza 2017 `exoproteome` → `whole_cell` proteomics (exoproteome experiments 10 → 7); Moreno 2023 / Kaur / Ma / Tolonen / Biller growth phases re-curated (`stationary` gone, `growth_phase` 10 → 11 values); Fang 2019 vDOM is `carbon` with no Phage partner (Phage 10 → 9 experiments); Aharonovich 2016 HOT1A3 linear ratios converted; Barreto / Fuszard / Domínguez conditions corrected. Anjur-Dietrich 2025 bioRxiv `10.1101/2025.08.05.668435` → Anjur-Dietrich 2026 *Nat Commun* `10.1038/s41467-026-77598-7` (Publication + Experiment ids change; DE edges unchanged; discusses re-extracted). gene_count 127,035 unchanged. `controlled_vocabularies_hash` re-pinned `03d76346…` → `89c63aa0…` (new `control_timing` vocab; every description rephrased without apostrophes). 32 goldens regenerated (DE / ortholog / gene_overview / experiment / organism / publication rollups and `pathway_enrichment_med4_cyanorak_level1_10exp`; no envelope key or type changes); 4 live pins (Experiment 209 → 208 ×2, `table_scope` 192 → 191, exoproteome 10 → 7) and the per-timepoint growth-phase exemplar moved to Martiny 2006 MED4 P starvation; 21 example responses refreshed (64 blocks in 10 tool YAMLs). `-m kg`: regression 184, integration 3,042 green; unit 6,269. Surfacing `control_timing` / `design_notes` is the follow-up commit (`docs/kg-specs/2026-10-13-per-arm-sampling-shared-model-explorer-asks.md`).
- Absorbed the KG dev rebuild of 2026-10-18T05:51:30Z (`0.0.0-dev`, `local-dev`; KG commits `bbcb8219` / `5ac88ef7` / `d4282452`, KG doc §40, explorer ask 8): **stereo-form edges from ChEBI chemistry** (`is_a` path ≤ 3 steps with the same formula and charge, plus 8 curated links) — `Metabolite_is_stereo_form_of` 76 → 99 (+27, −4: (R)/(S)-acetoin, geranyl diphosphate → polyprenyl diphosphate, dicis-ζ-carotene, Xylose → D-xylose now D-xylose → Xylose); glucose / mannose / isoleucine / arabinose / fucose / fructose now linked, class terms and ring / open-chain forms deliberately not. `chebi:` nodes take `inchikey` / `smiles` from their own ChEBI term (glucose and allose now have none); 8 nodes carry the new sparse `removed_stereo_xrefs`. gene_count 127,035 and `controlled_vocabularies_hash` unchanged (vocab snapshot stamp only). 3 goldens regenerated, additive stereo links only (`list_metabolites_search_glucose`, `list_metabolites_id_batch_with_unknown`, `metabolites_by_gene_pmm0913_family_inferred_warning`, whose Xylose ↔ D-xylose `relation` labels flip with the edge direction fix); 0 example drifts; new `kg_claims` entry `stereo_link_examples`; the "stereo links are incomplete" prose rewritten to the rule (`docs://analysis/metabolites`, `genes_by_metabolite` / `metabolites_by_gene` YAML). Closes KG ask 8 and backlog 2c.10. `-m kg`: regression 184, integration 3,041 green.
- Absorbed the KG dev rebuild of 2026-10-16T08:17:23Z: KEGG classification vocab descriptions reworded (explorer ask 7, hash-neutral); vocab snapshot stamp and 1 `list_filter_values` example response refreshed.
- Absorbed the KG dev rebuild of 2026-10-15T19:58:07Z: curated sugar cross-reference moves (explorer ask 5; KG doc §39) — `HMDB0000122` / `CHEBI:17634` → D-Glucose `C00031`, `HMDB0000143` → `C00124`, `HMDB0000660` → `C00095`, `HMDB0001058` → `C00354`, `HMDB0000124` added on `C00085`. Hash and node / edge counts unchanged; 1 golden (`list_metabolites_search_glucose` `with_hmdb` 12 → 11) and 1 example (`with_hmdb` 125 → 126) moved.
- Absorbed the KG dev rebuild of 2026-10-15T19:17:46Z (`0.0.0-dev`, `local-dev`): **MNX stereo guard + canonical margin + KEGG BRITE classes** (explorer asks `docs/kg-specs/2026-10-15-metabolite-stereo-merge-asks.md` 1–4, 3b, 6; KG doc §38). MNX "same entity" merges no longer join stereo forms / anomers (9 pairs split; `C00193` / `C00261` and `C03688` / `C16240` kept separate): `Metabolite` 3,203 → 3,214, multi-KEGG nodes 21 → 10, `C00085` is "D-Fructose 6-phosphate" again, `Metabolite_is_stereo_form_of` 68 → 76; halides canonical on the ion (`C00698` / `C01324` / `C00742`); `catalyzed_metabolite_count` +5 on most organisms; `Metabolite.kegg_compound_categories` renamed `kegg_functional_categories`; new `Metabolite.kegg_brite_classes` (652 nodes, 28 values). gene_count 127,035 and expression unchanged. `controlled_vocabularies_hash` re-pinned `f09cfcaa…` → `03d76346…`. 12 goldens regenerated (organism / metabolite rollups, `mqa_mit9313_top5` back on `C00085`; no shape changes); 3 live pins (N-bearing 1,688 → 1,692, N+P 574 → 576, MED4+N 1,002 → 1,003); 25 example responses refreshed; `kg_claims` measured metabolites 134 → 135 (Biller "Phosphoglyceric Acid" now on `C00597`). No explorer code reads the renamed property yet (surfacing is backlog 2c.8). KG ask 5 (anomer HMDB xrefs, 17 pairs) stays a curated KG follow-up.
- Absorbed the KG dev rebuild of 2026-10-15 (built 2026-10-15T16:26:50Z, `0.0.0-dev`, `local-dev`): **metabolite identity + KEGG compound classes + chemical roles** (KG doc `metabolite-identity-and-classes.md`), plus the coculture-partner dedupe-by-id fix. `Metabolite` 3,356 → 3,203 (merges, 124 `chebi:` → KEGG re-keys, 57 role terms → `ChemicalRole`, 13 measurement-only nodes dropped; 320 retired ids in the KG's `metabolite_id_remap.tsv`); new labels `MetaboliteClass` (445) / `ChemicalRole` (111) and their edges, `Metabolite_is_stereo_form_of` / `_is_enantiomer_of`, assay-edge `stereo_assignment`, `TcdbFamily.substrate_breadth` (pinned lumping set — no gene's `transport_substrate_resolution` moved); `metaboliteFullText` now covers name + formula + identifier tokens. gene_count 127,035 unchanged; expression unchanged. `controlled_vocabularies_hash` re-pinned `6f01dce4…` → `f09cfcaa…`. 37 goldens regenerated (all chemistry / organism / publication rollups, `3.A.1` `metabolite_count` 554 → 518, Lucene score drift from 5 new 0-gene KEGG pathways; only shape change is `substrate_breadth` in verbose TCDB `properties`); 10 live pins moved (PMM0392 transported metabolites 13 → 12, N-bearing 1,693 → 1,688, transport-only 1,462 → 1,382, MED4+N 992 → 1,002, assay metabolite total 1,044 → 1,050, msystems flags top-5 names); 62 example responses refreshed, 1 example call re-pointed off a retired id (`chebi:14313` → `chebi:17234`); 2 `kg_claims` (measured metabolites 149 → 134, PMM0392 13 → 12). Prose: ABC-superfamily plateau 554 → 518 rows (301 inherited / 217 most_specific), `list_metabolites` search covers formula + identifiers, metabolite id-form examples (no `mnx:` nodes remain). Explorer surfacing of the new layer is backlog 2c.8 (not part of this absorb); retired ids currently resolve to `not_found`. KG asks D1 / D2 closed; merge-quality follow-up in `docs/kg-specs/2026-10-15-metabolite-stereo-merge-asks.md`. `-m kg`: regression 181, integration 2,899 green after fixes; unit 5,987.
- `list_experiments(coculture_partner=…)` matches any entry of the partner list (`ANY(p IN e.coculture_partner WHERE toLower(p) CONTAINS …)`), so background cocultures are now found: `coculture_partner="Alteromonas"` returns 53 experiments (was 5), including the Weissberg 2025 RNA-seq + proteomics and the Moreno 2023 cultures that the 2026-10-06 Pro N-import analysis missed. Combining it with `treatment_type=['coculture']` keeps only coculture-vs-axenic contrasts (param description + `conventions` say so). The `GENES_UPREGULATED_BY_COCULTURE` curated query and two `run_cypher` few-shot examples use the same `ANY(...)` form. A `-m kg` test pins the background-partner match.
- Absorbed the KG dev rebuild of 2026-10-13 (built 2026-10-13T13:51:35Z, `0.0.0-dev`, `local-dev`): coculture partner list + data corrections. `Experiment.coculture_partner` is a dense list rebuilt post-import from one `Tests_coculture_with` edge per partner, each with `partner_role ∈ {treatment, background}` (new edge `ControlledVocabulary`). The Moreno 2023 heterotroph-side experiments (40) were curator-corrected: `coculture` moved from `treatment_type` to `background_factors`, so `treatment_type=['coculture']` now returns 36 experiments (was 76) and `background_factors` `coculture` counts 78 (was 58). Barreto 2022 / Biller 2016 / Bernstein 2017 partners are recorded as background. The gene-less `Meiothermus ruber` treatment taxon (`ncbitaxon:277`) was retired (Bernstein's edge now points at the genome strain), so `OrganismTaxon` is 47 (was 48) and every `preferred_name` is unique; the "two nodes share 'Meiothermus ruber'" caveat is gone from `CLAUDE.md`, the `list_organisms` param description, 7 tool YAMLs and `conventions`. gene_count 127,035 unchanged. `controlled_vocabularies_hash` re-pinned `3833eeb4…` → `6f01dce4…`. `schema_baseline.yaml`: `coculture_partner: list`, `Tests_coculture_with.partner_role`. 20 goldens regenerated (every diff traced to the partner list, the Moreno correction or the retired taxon); 13 examples refreshed (`list_experiments`, `list_organisms`, `list_publications`, `kg_schema`); `kg_claims` organism counts 48 → 47; trust-invariant pins: the rollup-density count reads live, and the Meiothermus collision guard became a `preferred_name`-uniqueness guard. `-m kg`: 3,062 passing (2,881 integration + 181 regression). Closes KG ask D5.
- Absorbed the KG dev rebuild of 2026-10-13 (built 2026-10-13T06:28:00Z, `0.0.0-dev`, `local-dev`): Cyanorak coordinate + sequence fallback — 3,837 genes Cyanorak called but NCBI didn't now carry coordinates and a sequence, so every Gene has `contig` / `start` / `strand` / `sequence` (gene_count 127,035 unchanged); new closed vocabularies `Gene.coordinate_source` / `Gene.sequence_source` (`ncbi` / `cyanorak`). `controlled_vocabularies_hash` re-pinned `1f671eae…` → `3833eeb4…`. 3 `gene_details` goldens regenerated (additive: the two new properties); 2 examples re-pointed (`gene_aa_sequence`, `gene_neighbors`: `A9601_09441` is now a Cyanorak-placed gene, not a not_matched one); the null-coordinate edge-case fixture + its 2 `gene_neighbors` scenarios removed (no such gene exists; unit tests keep the not_matched path); "~3% of genes lack coordinates / sequence" prose retired (CLAUDE.md, concepts, `gene_aa_sequence`), `protein_id`-null-on-Cyanorak-only-genes documented. Closes KG ask D4.
- Absorbed the KG `0.1.0-alpha.7` release cut (built 2026-09-15T12:52:43Z, git `6bf6e513`, `deployment_role: staging`, `mcp_min_version: 0.1.0a5`): stamp-only — `controlled_vocabularies_hash` unchanged, gene_count 127,035 unchanged, 0 vocab moves, 0 golden regens, 0 example drifts; vocab-snapshot `kg_built_at` header re-stamped. The two `deployment_role == 'local-dev'` test pins became verbatim-passthrough assertions against live `Schema_info` (the deployed build now legitimately stamps `staging`). `-m kg`: 3,229 passing. KG-side residual: `release_highlights` / `breaking_changes` were not stamped on the cut (backlog 1.2).

### Fixed
- **Paging could duplicate and drop rows** (from the 2026-10-06 Pro N-import coculture analysis). Four tools paged over an ORDER BY that wasn't unique for the row grain, so SKIP/LIMIT pages overlapped while `returned == total_matching` still held. Live repro: `metabolites_by_gene(['PMM0331'])` at `limit=10` → 229 rows, 185 unique, 44 never returned; `list_experiments` lost 1 of 209 (axenic/coculture arms share organism + name). Every ORDER BY now ends in a unique key: `metabolites_by_gene` both arms + the API merge sort (`reaction_id` / `tcdb_family_id`), `metabolites_by_quantifies_assay` / `metabolites_by_flags_assay` (`r.id`), `assays_by_metabolite` (edge id, internal), `list_experiments` (`e.id`). A guard test pins the tail of each ORDER BY; a `-m kg` test checks concatenated pages == one call. Rows that previously tied may come back in a different (now stable) order.
- **`gene_neighbors` could exhaust Neo4j memory.** The detail query builds every anchor × neighbor row before `limit` applies, and `gene_neighbors(<every MED4 gene>, window=10000)` (~3.7M rows) raised `MemoryPoolOutOfMemoryError`. `window` is now capped at 100 (`le=100` on the MCP param, `ValueError` in the API), and detail mode rejects `len(locus_tags) × 2 × window > 100,000` with a "split into batches" error. Genome-wide coordinates: use `gene_details`.
- **Two filters dropped data without saying so** (from the 2026-10-06 Pro N-import coculture analysis; backlog 2c.3 / 2c.4). `genes_by_ontology`: the enrichment-tuned size defaults (`min_gene_set_size=5` / `max_gene_set_size=500`) dropped terms with nothing in the envelope, e.g. BRITE `transporters` `level=2` in MED4 returned 16 of 57 genes. New envelope fields `size_filtered_terms` / `size_filtered_genes` (always present, 0 when nothing is dropped) plus a warning naming `min_gene_set_size=1, max_gene_set_size=None` for enumeration. `metabolites_by_gene(metabolite_elements=…)` / `list_metabolites(elements=…)`: formula-less metabolites (mostly generic classes such as "amino acid") can never match an element filter. New envelope field `no_formula_excluded` (plus `no_formula_excluded_metabolites` on `metabolites_by_gene`), present only when the element filter is set, plus a warning when it is > 0. Defaults and existing fields are unchanged.

## [0.1.0-alpha.5] - 2026-09-15
**KG requirement:** this release targets KG `0.1.0-alpha.7` (the
KG-side sync that adds the organism annotation rollups, the
`ControlledVocabulary` hash, and the paper batch below). It adds a new MCP
tool (`ontology_term_details`) and changes row shapes, so the explorer
version becomes `0.1.0-alpha.5` and the KG's `mcp_min_version` must be
coordinated to `0.1.0a5` ahead of the KG release.

### Added
- Docs review 2026-09-15 (release Phase 1b, six-surface reviewer pass): 33 findings (3 P1), 32 fixed — highlights: the shared `organism` param description now states the real matching contract per tool family (widening word-match vs single-organism raise vs substring CONTAINS on the assay drill-downs); stale "never flagged pathway maps" / "must be prefixed" / "always 0" claims corrected; `python_api.md` limit-default and `kg_release_info(conn)` exceptions documented (source-side alignment → backlog 2.15); DE-tool response-model field texts caught up with the 2b.6a filters.
- `treatment_type` / `background_factors` filters on both DE tools (`differential_expression_by_gene`, `differential_expression_by_ortholog`) — same array-containment, case-insensitive semantics as `list_experiments`; genes whose edges all fail the filters land in `filtered_out` (by-gene), unknown values add envelope `warnings` on both tools (backlog 2b.6a). `differential_expression_by_ortholog` now also warns on unknown `growth_phases` values (previously `warnings` was always `[]`).
- `docs://index` — directory of every `docs://` page with per-entry approximate token size and read-when guidance, registered first so it is the natural discovery entry point.
- `docs://tools/{name}/full` — full tool pages (every example, verbose fields, complete chaining/mistakes lists), split out from the now-brief default `docs://tools/{name}` page.
- `docs://analysis/expression` — DE-tooling reference page (`differential_expression_by_gene` / `differential_expression_by_ortholog` / `gene_response_profile`, plus the `response_matrix` / `gene_set_compare` Python wrappers), moved out of `docs://guide/python_api` (closes backlog 3.14).
- `examples/*.py` scenario `# CONTENTS` TOC comment blocks (`pathway_enrichment.py`, `metabolites.py`, `ontology_terms.py`, `annotation_evidence.py`) naming each scenario function and its rough line number.
- Docs lint suite `tests/unit/test_docs_lint.py` (link integrity, stale identifiers from `inputs/lint/stale_identifiers.yaml`, quoted vocabulary values vs `inputs/lint/vocab_snapshot.yaml`, CLAUDE.md table shape, tool-inventory coherence incl. `start_here` routing) + `tests/integration/test_docs_kg_claims.py` (`-m kg`: every KG number the docs quote, from `inputs/lint/kg_claims.yaml`; vocab snapshot == live).
- `scripts/refresh_examples.py` — executes every YAML example `call` through an in-memory MCP client and rewrites (`--write`) or checks (`--check`) the `response:` block against the live KG; `tests/integration/test_about_examples.py::test_example_response_values_match_live` fails on drift. Example entries accept `illustrative: true` + `note:`.
- `scripts/snapshot_vocab.py` — regenerates the offline vocabulary snapshot after a KG rebuild.
- `docs://examples/annotation_evidence.py` registered (was referenced but not served); `examples/pathway_enrichment.py` rebuilt with the `--scenario landscape|de|cluster|ortholog|custom` interface.
- KG handoff `docs/kg-specs/2026-08-29-docs-review-kg-asks.md` (DOC-001..008).

- **Silent-zero warnings, shared helper.** New
  `_closed_vocab_warnings` / `_organism_zero_match_warning` helpers replace
  2b.1's per-field version; wired into `genes_by_function`, `list_experiments`,
  `list_publications`, `list_organisms`, `list_derived_metrics`,
  `list_clustering_analyses`, `gene_derived_metrics`, `gene_clusters_by_gene`,
  `genes_by_numeric_metric`, `genes_by_boolean_metric`,
  `genes_by_categorical_metric`, `genes_by_metabolite`, `metabolites_by_gene`,
  `list_metabolite_assays`, `differential_expression_by_gene`,
  `gene_response_profile`. New `warnings: list[str]` envelope key on 8
  response models that lacked it (`ListOrganismsResponse`,
  `GenesByFunctionResponse`, `ListPublicationsResponse`,
  `ListExperimentsResponse`, `ListClusteringAnalysesResponse`,
  `GeneDerivedMetricsResponse`, `ListDerivedMetricsResponse`,
  `GeneClustersByGeneResponse`). Warning text: `"<param> value '<v>' matched
  nothing — valid values: ... (list_filter_values(filter_type='<type>'))"` /
  `"organism '<v>' matched no organism — see list_organisms()"`.
- **Bare ontology/ortholog-group ID coercion + locus-tag case warning.**
  `genes_by_ontology`, `ontology_term_details`,
  `genes_by_homolog_group`, `differential_expression_by_ortholog`,
  `pathway_enrichment`, `cluster_enrichment` accept bare term / group ids
  (e.g. `ko00910` → `kegg.pathway:ko00910`, `GO:0006979` → `go:0006979`,
  `CK_00000570` → `cyanorak:CK_00000570`) and report the mapping in new
  `resolved_aliases: dict[str, list[str]]` (top-level on the first four,
  nested under `term_validation` on the two enrichment tools). 11 tools
  (`gene_overview`, `gene_details`, `gene_homologs`, `gene_aa_sequence`,
  `gene_neighbors`, `gene_ontology_terms`, `differential_expression_by_gene`,
  `gene_response_profile`, `gene_derived_metrics`, `gene_clusters_by_gene`,
  `metabolites_by_gene`) warn `"<input> not found; '<existing>' differs only
  by case"` on a locus_tag that differs only by case from a real
  `Gene.locus_tag` (locus tags are never normalised).
- **DM drill-down wrong-kind / impossible-filter routing.**
  `genes_by_numeric_metric` / `genes_by_boolean_metric` /
  `genes_by_categorical_metric` now classify a wrong-kind
  `derived_metric_ids` / `metric_types` entry as `not_matched_*` (not
  silently empty) with a `warnings` entry naming the sibling tool (`"<id>
  exists as value_kind=<kind> — use <tool>"`); an organism with no edges for
  the selected DM(s) sets `not_matched_organism` and names the DM's real
  organisms (previously misfired even on a wholly-absent `metric_type`).
  `genes_by_numeric_metric.bucket` is now `list[Literal['top_decile',
  'top_quartile', 'mid', 'low']]` — an unlisted value now raises a
  validation error instead of silently matching nothing.
  `genes_by_boolean_metric(flag=False)` on a positive-only DM warns `"<id>
  stores positive flags only — flag=False cannot match; read
  by_metric[*].false_count"`. `gene_derived_metrics` gained the same
  sibling-tool warning for a wrong-kind id.
- **BRITE requires `tree`; Lucene errors are readable.**
  `pathway_enrichment` / `cluster_enrichment` raise
  `ValueError("ontology='brite' needs tree= (12 trees; see
  list_filter_values(filter_type='brite_tree')) — a tree-less run mixes
  taxonomy and function terms.")` before any query when `ontology='brite'`
  and `tree` is omitted. Every fulltext-search tool's final retry
  (`genes_by_function`, `search_ontology`, `search_homolog_groups`,
  `list_publications`, `list_experiments`, `list_metabolites`,
  `list_clustering_analyses`, `list_derived_metrics`,
  `list_metabolite_assays`) now raises a readable `ValueError("search_text
  ... is not valid Lucene syntax: ...")` instead of the raw Neo4j driver
  exception on a persistent parse failure. `search_ontology` appends
  `"search_text was sanitised to '<q>'"` to `warnings` when its
  escape-and-retry changed the query.
- **Remaining silent paths on assays, clusters, metabolite IDs.**
  `list_metabolite_assays` / `assays_by_metabolite` warn
  `"organism '<name>' has no metabolomics assays — organisms with assays:
  ..."` when the organism resolves genomically but has zero
  `MetaboliteAssay` nodes. `genes_in_cluster(analysis_id=)` gains
  `not_found_analysis: str | None` (an unknown `analysis_id` no longer
  looks identical to "exists, zero clusters") plus a `warnings` entry.
  `genes_by_metabolite` /
  `list_metabolites` warn `"'<v>' is not a metabolite id — resolve names
  with list_metabolites(search_text=...)"` on a `metabolite_ids` entry
  matching no recognized id shape at all. `list_metabolites(elements=...)`
  silently normalises case / full-name element inputs and reports
  genuinely unrecognized ones in new `not_found.elements`.
  `metabolites_by_quantifies_assay` / `metabolites_by_flags_assay` classify
  a wrong-kind `assay_id` as found-but-wrong-kind with a sibling-tool
  warning instead of `not_found`.

- **Bare / xref metabolite-ID coercion** (closes KG-MET-014 explorer-side).
  Every `metabolite_ids` / `exclude_metabolite_ids`
  parameter on the 7 chemistry + metabolomics tools (`list_metabolites`,
  `genes_by_metabolite`, `metabolites_by_gene`, `list_metabolite_assays`,
  `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`,
  `assays_by_metabolite`) now accepts bare `C00064`, `CHEBI:17234` / `17234`,
  `HMDB…` and `MNXM…` and resolves them to the canonical `Metabolite.id`
  via the node xrefs before the query runs (previously a silent
  `not_found`). Canonical `kegg.compound:` / `chebi:` / `mnx:` inputs pass
  through with zero extra round-trips. Ambiguous CHEBI / HMDB / MNXM aliases
  expand to every matching node and append a `warnings` entry; unresolved
  inputs stay verbatim in `not_found`. New envelope key `resolved_aliases`
  (`{input: [canonical, ...]}`) on all 7; `warnings` added to
  `list_metabolites`, `list_metabolite_assays`, `assays_by_metabolite`.
  Exclude-wins-on-overlap is evaluated on canonical IDs. Outfacing lint
  gained release-note framing patterns (`previously`, `are now resolved`).

- `list_filter_values` description parity: every
  vocabulary-backed filter type now puts the property-level
  `ControlledVocabulary` text once on the envelope `description`, and rows
  carry the per-value meaning from the KG's new `value_descriptions` (B1,
  2026-08-29 rebuild — 39 nodes, the whole trust surface) with the
  redundant `"<value>: "` prefix stripped. Rows without per-value text
  (`cluster_type`, `interpro_type`, …) omit the key. Before, the trust
  types repeated the property paragraph on every row and left the
  envelope null.
- **Annotation-trust surface** on the ontology tools. Every gene→term edge
  across the 14 functional-edge ontologies carries a compact `evidence`
  column (five-rung ladder `curated > signature > homology >
  family_inferred > domain_inferred`); `sources[]`, `evidence_score`
  (`[0, 1]` composite) and `tier` are verbose. New filters on
  `genes_by_ontology`, `gene_ontology_terms`, `pathway_enrichment`,
  `cluster_enrichment` and `ontology_landscape`: `sources`, `evidence`,
  `max_tier`, `min_evidence_score` (the only numeric cutoff in the surface),
  `call_class` (MEROPS) and `interpro_type` (InterPro; required on InterPro
  enrichment). All default to `None` and never narrow a result unless set.
  Full-match envelope rollups `by_evidence` / `by_tier` / `by_sources` /
  `by_call_class` / `evidence_score_stats`, plus `evidence_score_signals`
  whenever `min_evidence_score` is set. Rows carry only the trust columns
  their ontology owns (strip rule). See `docs://analysis/annotation_evidence`.
- **InterPro, NCBIfam and MEROPS** registered as ontologies 15–17 across the
  ontology tools and both enrichment tools. `ontology_landscape` breaks
  InterPro rows down per `interpro_type` and reports `best_interpro_type`.
- `ontology_term_details` MCP tool — batch term lookup across all 17
  ontologies: parents, children, bridge links (`links_out`), direct and
  subtree gene / organism counts, per-ontology native detail; `not_found`
  for unknown IDs.
- `search_ontology` **browse mode**: omit `search_text` to list an
  ontology's terms ranked by `gene_count` (`mode: 'browse'`, `by_level`
  rollup). `ontology` now accepts a list (or `None` for all 17) with
  lockstep paging (`limit` / `offset` apply per ontology; `by_ontology`
  carries per-ontology truncation). New params `min_gene_count`, `organism`
  (adds `organism_gene_count`), `interpro_type`, `verbose` (term
  `description`). Every row carries `gene_count`, `organism_count` and
  `ontology_type`.
- `gene_overview` rows: `merops_classes` (list — a gene can carry both a
  `peptidase` and a `nonpeptidase_homolog` call), `ncbifam_family_count`,
  `merops_evidence_score_max` (sparse, uncoalesced — rank, don't filter);
  envelope `by_merops_class`, `has_ncbifam`.
- `list_filter_values` trust types (`evidence`, `sources`, `call_class`,
  `interpro_type`, `ncbifam_family_type`, `merops_catalytic_type`,
  `merops_family_class`, `best_hit_kind`, `pfam_support`,
  `attachment_depth`) read from the KG's `ControlledVocabulary` nodes with a
  live pivot-query fallback (`source: 'pivot'` + warning), and the
  config-derived `trust_axes` / `link_kinds` (scoped by `ontology=`).
- Per-ontology reference pages `docs://ontologies/{key}` (17 pages + index)
  generated from `inputs/ontologies/*.yaml`; `docs://analysis/annotation_evidence`
  methodology guide; runnable examples `examples/annotation_evidence.py`
  and `examples/ontology_terms.py`.
- `kg_release_info` **vocabulary-set assert**: a sixth assert bucket
  (`controlled_vocabularies_hash`) compares the KG's
  `Schema_info.controlled_vocabularies_hash` with the hash the explorer was
  built against. A mismatch, or a KG that predates the vocabulary contract,
  yields `warn` (never worse) with a summary sentence explaining that
  filters still validate live and `list_filter_values` reads live, but
  quoted value lists in `docs://ontologies` pages and parameter descriptions
  may be stale. `kg.controlled_vocabularies_hash` is surfaced. The pin is
  re-set at explorer release time to equal the live KG's hash.
- `genes_by_metabolite` / `metabolites_by_gene` detail rows carry
  `transport_substrate_resolution` on the transport arm (`resolved` |
  `family_inferred`; `None` on metabolism rows). It is the gene's
  KG-authoritative value repeated on each of that gene's transport rows —
  not a per-substrate fact (`substrate_depth` is) — so a batch scan can drop
  `family_inferred` rows without a join back to `top_genes[]` / `by_gene[]`.
- `list_organisms` rows: annotation-coverage counts `peptidase_gene_count`,
  `nonpeptidase_homolog_gene_count`, `interpro_gene_count`,
  `ncbifam_gene_count` (distinct genes, zero-filled); envelope
  `by_annotation_capability` (top 10 of the matched set by
  `peptidase_gene_count` desc then `preferred_name`, all four columns,
  all-zero rows excluded). No count filter by design — read the ranking.
- `list_filter_values(filter_type='cluster_type')` — the six
  `ClusteringAnalysis.cluster_type` values from `ControlledVocabulary`
  (`time_course`, `diel`, `condition_comparison`, `expression_bin`,
  `decay_pattern`, `genomic_island`), pivot fallback + warning if the node is
  missing. The `cluster_type` parameter descriptions on
  `list_clustering_analyses` / `gene_clusters_by_gene` now point here;
  `VALID_CLUSTER_TYPES` is the offline fallback (updated to 6 values).

- `genes_by_metabolite` / `metabolites_by_gene` transport rows carry
  `tcdb_evidence_score` (the KG's 5-signal composite on the gene × family
  edge, float in [0, 1]); rows rank by it within a depth tier. No score
  filter param by design — rank, don't filter. Envelope per-gene entries
  (`top_genes[]` / `by_gene[]`) gain `transport_substrate_resolution` and
  `tcdb_evidence_score_max`.
- `gene_overview` rows: `tcdb_evidence_score_max` (float | null; null = no
  TCDB call, never coalesced), `transported_metabolite_count` (int) and
  `transport_substrate_resolution` (`resolved` | `family_inferred` | null).
- `gene_overview` rows: `tcdb_family_count` (TCDB families at the deepest
  attachment only — the corrected successor of the removed
  `transporter_count`, which counted superseded ancestors) and
  `cazy_family_count`; envelope `has_tcdb` / `has_cazy`. Both read KG
  precomputes: the KG redefined `Gene.tcdb_family_count` to the
  deepest-attachment count in the 2026-08-29 rebuild
  (`docs/kg-specs/2026-08-29-gene-overview-family-counts-asks.md`), and a
  `-m kg` invariant test keeps it equal to the live edge count. Spec
  `docs/tool-specs/2026-08-29-gene-overview-family-counts.md`.
- Regression goldens regenerated for the 2026-08-29 gene-mapping rebuild
  (KG `fix(gene-mapping)`: NCBI↔Cyanorak position fallback by stop codon +
  frame; 423 shadow gene ids vanished, 359 paper rows re-homed; 127,458 →
  127,035 genes). 41 goldens moved: tied-score reordering, gene counts a
  few lower, shadow locus_tags gone.
- `list_metabolites` rows: `transporter_gene_count` (distinct genes over
  deepest TCDB attachments, all organisms) — pairs with `catalyst_gene_count`
  so transport-only reads `0 / >0`.
- `list_organisms` rows and `by_metabolic_capability[]` entries:
  `transported_metabolite_count`.
- Spec: `docs/tool-specs/2026-08-20-tcdb-substrate-depth-migration.md`.

### Breaking
- `mass_min` / `mass_max` → `min_mass` / `max_mass` (`list_metabolites`)
- `value_min` / `value_max` → `min_value` / `max_value` (`metabolites_by_quantifies_assay`)
- `metric_percentile_min` / `metric_percentile_max` → `min_percentile` / `max_percentile` (`metabolites_by_quantifies_assay`)
- `rank_by_metric_max` → `max_rank` (`metabolites_by_quantifies_assay`)
- `publication_doi` → `publication_dois` (`list_experiments`, `list_clustering_analyses`, `list_derived_metrics`, `gene_clusters_by_gene`, `gene_derived_metrics`, `genes_by_numeric_metric`, `genes_by_boolean_metric`, `genes_by_categorical_metric`, `list_metabolite_assays`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`)
- `bucket` → `metric_bucket` (`genes_by_numeric_metric`)
- `flag` → `flag_value` (`genes_by_boolean_metric`)
- `category` (`str`) → `gene_categories` (`list[str]`) (`genes_by_function`)
- `treatment_types` → `treatment_type` (`gene_response_profile`)
- `treatment_type` / `background_factors` / `growth_phases`: `str` → `list[str]` (`list_publications`)
- `omics_type`: `str` → `list[str]` (`list_clustering_analyses`, `list_derived_metrics`)
- `outputSchema` no longer emitted on `tools/list`

### Changed
- Generated tool pages default to a brief summary (params + one worked example); the full page (all examples, verbose fields) moved to `docs://tools/{name}/full`.
- `docs://guide/conventions` cut to its cross-tool core (~7k tokens); the chemistry sections (transport trust ladder, direction-agnosticism, metabolite ID forms) now live on `docs://analysis/metabolites` and the trust-surface sections on `docs://analysis/annotation_evidence`, with one-paragraph pointers left behind (closes backlog 3.15).
- `docs://guide/start_here` trimmed to the family table + response shapes, with cross-feeding and DE-by-functional-class recipes and an enrichment "step 0" added.
- MCP server instructions are size-aware — name `docs://index` first and carry its approximate resource sizes so agents pick brief vs. full pages deliberately.
- `differential_expression_by_ortholog` accepts `direction='both'` (runs up and down per group × experiment × timepoint, matching `differential_expression_by_gene`).
- `search_ontology.ontology` and `list_filter_values.ontology` typed to the closed 17-key ontology enum instead of a bare `str`.
- `list_clustering_analyses` matches `omics_type` case-insensitively.
- Tool descriptions rewritten to a five-slot template (what / when / params / returns / see-also), each ≤ 600 chars; shared parameter descriptions (`organism`, `limit`, `summary`, trust filters, the ontology key, …) centralized in `mcp_server/params.py` instead of re-described per tool.
- Python-API deprecation aliases for the renames above (`api/_compat.deprecated_alias`: `publication_doi`, `bucket`, `flag`, `category`, `treatment_types`, `mass_min`/`mass_max`, `value_min`/`value_max`, `metric_percentile_min`/`metric_percentile_max`, `rank_by_metric_max`, and the bare-`str` vocab filters) keep working one release and will be removed in `0.1.0-alpha.6`.
- `differential_expression_by_gene` envelope drops `n_experiments` (an exact duplicate of `experiment_count`; the ortholog twin only ever had `experiment_count`). Read `experiment_count`. (llm-review 2b.8)
- `resolve_gene` and `list_publications` gain `summary: bool = False` (envelope only, rollups uncapped) — the last two capped-rollup tools without it, so `by_organism` can always be read in full (on `resolve_gene` its counts then sum to `total_matching`). 36 of 42 tools now accept `summary=True`. (llm-review 2b.7)
- **LLM-consumer response diet.** Six related trims, each
  measured on a live call through `fastmcp.Client` (`len(json)//4`):
  - `differential_expression_by_gene`: `experiments[]` rows go compact by
    default — `experiment_id`, `treatment_type`, `table_scope`,
    `is_time_course`, `matching_genes`, `rows_by_status`, `omics_type`
    only; `experiment_name`, `background_factors`, `coculture_partner`,
    `table_scope_detail`, `timepoints` move behind `verbose=True`. New
    envelope key `n_experiments` (full count, computed before any
    trimming). `differential_expression_by_gene(locus_tags=['PMM1171'],
    summary=True)`: 22,095 chars / ~5,523 tokens → 12,586 chars / ~3,146
    tokens.
  - `pathway_enrichment` / `cluster_enrichment` gain `include_nonsignificant:
    bool` (MCP default `False` — only rows with `p_adjust < pvalue_cutoff`
    are returned; package default stays `True`, unchanged for existing
    scripts). MCP `limit` default 100→25 (`pathway_enrichment`) / 5→25
    (`cluster_enrichment`). `total_matching` now counts the pageable
    subset under the active filter (the significant-only count when
    `include_nonsignificant=False`); `n_significant` and the summary
    breakdowns (`by_experiment`, `by_cluster`, `cluster_summary`, …)
    always read the full tested set regardless of the flag.
    `pathway_enrichment(organism='MED4', experiment_ids=[<first MED4
    nitrogen experiment>], ontology='kegg', level=1)`: 105,614 chars /
    ~26,403 tokens → 19,817 chars / ~4,954 tokens.
  - MCP-side `limit` defaults resized for a context window (Python-package
    defaults unchanged): `genes_by_ontology` 500→50, `gene_ontology_terms`
    5→50, `genes_in_cluster` / `gene_clusters_by_gene` /
    `genes_by_numeric_metric` / `genes_by_boolean_metric` /
    `genes_by_categorical_metric` 5→25, `ontology_landscape` unlimited→15
    (`limit=None` still returns every row). Batch tools (`gene_overview`,
    `gene_details`, `gene_aa_sequence`, `gene_homologs`, `gene_neighbors`)
    move to `limit: int | None = None`, resolved to `max(25,
    len(locus_tags) * k)` (k = fan-out per tool, e.g. 1 for `gene_overview`
    / `gene_details` / `gene_aa_sequence`, 5 for `gene_homologs`,
    `2*window+1` for `gene_neighbors`) whenever the caller doesn't pass an
    explicit `limit`.
  - Detail calls (`summary=False`, the default, or tools without a
    `summary` param) cap every ranked `by_*` / `top_*` breakdown to its
    first 10 entries, sorted desc by its ranking count, with a sparse
    `<key>_truncated: true` sibling key added only when a list was
    actually capped; `summary=True` returns each list in full. Applies to
    `list_experiments` (`by_publication`, `by_metric_type`, `by_organism`,
    `by_treatment_type`, `by_background_factors`), `list_organisms`
    (`by_metric_type`, `top_annotation_capability`,
    `top_metabolic_capability` — previously hard-capped at 10 even in
    `summary=True`), `list_publications` (`by_metric_type`, `by_organism`),
    `resolve_gene` (`by_organism`), `genes_by_function` (`by_organism`),
    `metabolites_by_gene` (`top_metabolite_pathways`, `by_element`),
    `genes_by_metabolite` (`top_genes`, `top_reactions`,
    `top_tcdb_families` — previously hard-capped unconditionally),
    `differential_expression_by_gene` (`experiments`), and
    `pathway_enrichment` (`by_experiment`, now sorted desc by
    `n_significant`; `top_pathways_by_padj` is a genuine top-10 in both
    modes, sorted by `p_adjust` ascending, with no `_truncated`
    companion).
    `list_experiments(organism='MED4')`: 13,600 chars / ~3,400 tokens →
    12,132 chars / ~3,033 tokens.
  - Compact rows drop parent-constant / verbose-only fields that were
    previously serialized as `null` on the wire: `genes_by_metabolite` /
    `metabolites_by_gene` (`GeneReactionMetaboliteTriplet` moved onto the
    `SparseRow` base so its 9 already-verbose-only keys —
    `gene_category`, `metabolite_inchikey`, `metabolite_smiles`,
    `metabolite_mnxm_id`, `metabolite_hmdb_id`, `reaction_mnxr_id`,
    `reaction_rhea_ids`, `tcdb_level_kind`, `tc_class_id` — are genuinely
    absent, not `null`, in compact mode); `genes_by_numeric_metric` /
    `genes_by_boolean_metric` / `genes_by_categorical_metric` drop
    `name`, `value_kind`, `rankable`, `has_p_value`, `organism_name` from
    each row in compact mode (all present in `by_metric`); `list_derived_metrics`
    drops `has_p_value`, `field_description`, `experiment_id`,
    `publication_doi`, `compartment`, `omics_type`, `treatment_type`,
    `background_factors`, `growth_phases` in compact mode (`unit` stays
    compact — a numeric DM's `value` is unreadable without it).
    `metabolites_by_gene(['PMM0913'], 'MED4')`: 34,580 chars / ~8,645
    tokens → 12,319 chars / ~3,079 tokens.
  - `kg_schema` accepts `labels: list[str] | None`, `relationship_types:
    list[str] | None`, and `section: Literal['nodes', 'relationships',
    'both'] = 'both'` to scope the introspection instead of always
    dumping the whole graph; unknown values land in the new
    `not_found_labels` / `not_found_relationship_types` envelope keys
    (always present, `[]` when clean) rather than a silent empty entry.
    Property-sample queries are now deterministically ordered
    (`ORDER BY coalesce(n.id, elementId(n))` / `ORDER BY elementId(r)`)
    so repeated calls return byte-identical results. `kg_schema()` (full,
    unscoped dump — the only call shape available before this change):
    39,690 chars / ~9,922 tokens → `kg_schema(labels=['Gene'])`: 21,475
    chars / ~5,368 tokens.
- **KG rebuild 2026-08-29T18:29Z absorbed** (docs-review asks DOC-001/002/004/006, `docs/kg-specs/2026-08-29-docs-review-kg-asks.md` §4). Gene count unchanged (127,035). `controlled_vocabularies_hash` re-pinned `a7c97e00…` → `1f671eae…` (`Gene_has_pfam.evidence` gains `family_inferred`; `compartment` loses the never-used `spent_medium` / `lysate`). 10 goldens regenerated (9 from the eggNOG rung flip / KEGG global-map flag, 1 from the earlier NaN→None enrichment fix); 27 YAML example responses refreshed; 0 test pins moved. Prose rewritten wherever it described the old behaviour: eggNOG-only GO / EC / Pfam / CAZy edges now read `family_inferred` (score 0.333), never `curated`; `informative_only=True` now drops 11 of the 13 KEGG global / overview maps (`ko01100` …; `ko01310` / `ko01320` stay informative); `KeggTerm.direct_gene_count` is KO-only; compartment vocabulary is four values. Two behavioural `kg_claims` (eggNOG rung, KEGG map flags) guard the flips. `-m kg`: integration 2,753 / regression 176 green.
- **Docs review sweep (2026-08-29):** every served doc surface re-verified against code and the live KG. Highlights: treatment / background vocabulary values quoted in ~40 sites replaced with live values; organism-matching described uniformly (word-based on `preferred_name` + `name_synonyms`); `not_found` shapes documented as the three real forms; `organism_gene_count` subtree scope on both tools; `informative_only` defaults and KEGG informativeness described as live (KO-level only — `ko01100` is not flagged; `map00001` never existed); evidence-rung glosses replaced by one canonical section in `docs://analysis/annotation_evidence` (eggNOG-only GO/EC/Pfam/CAZy edges read `curated` today — KG ask DOC-001); TIGR two-level hierarchy + NCBIfam→TigrRole router surfaced in concepts / `ontology_term_details` / annotation_evidence; `enrichment.md` rewritten with runnable recipes (773 → 532 lines); `concepts.md` inline node counts dropped; CLAUDE.md tool table trimmed to routing one-liners (≤ ~620 chars/row) and the removed CLI struck from CLAUDE.md / README; every YAML example response regenerated from the live KG (`scripts/refresh_examples.py --write`) and fabricated example inputs replaced with real IDs.
- Generator: `## Common mistakes` heading always; union param types render every arm (`string | list[string] | None`); package-import key list no longer drops `returned` / `truncated`; ontology pages carry an "Applicable filter types" section instead of empty vocabulary boilerplate; `index.md` gains Levels / Hierarchy / Trust columns; `_NODE_PROP_NOTES` filled for every ontology label prop.

- `search_ontology.organism_gene_count` (and the `min_gene_count` floor when
  `organism` is set) is now SUBTREE-scoped — term + descendants, the same
  scope as `gene_count` and as `ontology_term_details.organism_gene_count`.
  Was: the term's direct edge only. Leaf terms are unchanged; ancestor rows
  gain the descendants' genes (GO `go:0008150` MED4: 1134).
- `docs://ontologies/{key}` pages no longer embed a build-time snapshot of
  `ControlledVocabulary` values (the build output depended on whether a KG
  was reachable); they point at `list_filter_values(..., ontology=key)`,
  which reads live. `scripts/build_about_content.py --live-vocab` opts back in.
- `list_organisms(organism_names=)` now resolves through the shared organism
  resolver (case-insensitive word match on `preferred_name` + `name_synonyms`,
  gene-bearing taxa) — `'MED4'` works here like in every other tool. An exact
  `preferred_name` still matches gene-less treatment taxa. Was: exact
  `preferred_name` only.
- Unit lint: user-facing text (tool docstrings, field descriptions, about
  yaml, skill docs) may not contain internal build shorthand (`PR 3b`,
  `slice 4`) — `tests/unit/test_no_internal_shorthand_in_docs.py`.
- `search_ontology.by_level` is emitted only for a single-ontology browse
  (`[]` when `ontology` spans several) — level scales differ per ontology,
  so summing them was meaningless.
- `ontology_term_details`: dropped a redundant api-side `link_kinds`
  re-filter (the query already narrows the bridge union). No behaviour change.
- One-edge-per-(gene, term) rebind tie-break: when two edges reaching a
  rollup term share the primary rank key (`evidence_score` /
  `confidence_score`), the deepest attachment (highest `level`) wins
  (`apoc.coll.sortMulti([rank_key, 'attachment_level'])`). A rollup row
  no longer reports a `superseded` ancestor edge over an equal-scored
  most-specific descendant (PMM0392 @ `tcdb:3.A.1`). Trust columns move
  on a few multi-edge rollup rows.
- **Breaking envelope keys:** `list_organisms.by_metabolic_capability` →
  `top_metabolic_capability` and `by_annotation_capability` →
  `top_annotation_capability` (project rule: `top_*` = hard-coded top-N,
  `by_*` = full frequency; both are top-10 rankings).
- **Two-state strings (KG hand-off 2026-08-28, HO-001).** The eight
  boolean-like KG properties are now named string pairs instead of
  `'true'` / `'false'` (`is_time_course`: `time_course` /
  `single_time_point`; `reports_fold_change`: `fold_change` /
  `no_fold_change`; `rankable`: `rankable` / `not_rankable`; `has_p_value`:
  `p_value` / `no_p_value`; `Derived_metric_quantifies_gene.significant`;
  `Derived_metric_flags_gene.value`: `flagged` / `not_flagged`;
  `Assay_flags_metabolite.flag_value`: `detected` / `not_detected`). Tool
  parameters and `bool` output columns are unchanged (one `two_state()`
  coercion helper in `kg/constants.py`); the surfaces that echo the KG
  literal change value: `differential_expression_by_ortholog`
  `experiments[*].is_time_course` (`list_experiments` coerces to bool) and
  `genes_by_boolean_metric.by_value[*].value`. `metabolites_by_flags_assay`
  / `assays_by_metabolite` `by_value` / `by_flag_value` rollups are now
  coerced to `bool` in Cypher (previously relied on pydantic parsing
  `'true'`). Pinned `EXPECTED_CONTROLLED_VOCABULARIES_HASH` re-pinned to
  the 2026-08-28 build (`sha256:d7191e2a…`); 8 new closed vocabularies.
- **Meiothermus taxid correction (HO-002).** The Bernstein 2017 treatment
  taxon is `ncbitaxon:277` (was `ncbitaxon:1299`, which is *Deinococcus
  radiodurans*). `OrganismTaxon` gains sparse `name_synonyms` /
  `taxonomy_note`; the shared organism resolver now also matches words
  against `name_synonyms` (`'Meiothermus taiwanensis'` resolves).
- `genes_by_boolean_metric` docs corrected: `flag=False` returns
  tested-absent rows on the 11 of 27 boolean DMs that store `not_flagged`
  edges (Biller 2022, Voigt 2014, Hennon 2015, Steglich 2010); only the
  rest are positive-only. Read `by_metric[*].false_count` (filtered slice)
  or `dm_false_count` (full DM; the KG precompute was 0 until the
  2026-08-28 rebuild — KG ask R6, fixed). The earlier "returns 0 rows on
  every DM" statement was wrong.
- `list_filter_values(filter_type='cluster_type')` carries the vocabulary
  description once, on the new envelope `description` key; per-row
  `description` is absent (trust filter types keep the per-row text and
  also populate the envelope key when every row agrees).
- `ontology_term_details` compact `links_out[]` rows omit `props` entirely
  (verbose-only) instead of emitting `props: null`.

- **Breaking:** PSORTb / SignalP native columns `localization_score` and
  `signal_peptide_*` on ontology rows moved from compact to verbose — they
  are ontology-specific scalars, now under the same verbose-only rule as
  every other native trust detail (`confidence_score`, `evalue`,
  `bit_score`, ...). Pass `verbose=True` to read them.
- **Breaking:** row-level result models serialize **sparsely** on the MCP
  wire: a key that was never set is omitted, an explicit `null` is kept.
  Absent means "not applicable to this row" (a verbose-only column on a
  compact call, a trust axis this ontology does not carry); `null` means
  "applicable, but this record has no value". `genes_by_metabolite` /
  `metabolites_by_gene`, `assays_by_metabolite` and
  `discussed_by_publication` keep their None-padded union shape. See
  `docs://guide/conventions`.
- `search_ontology` with an empty `search_text` no longer raises — it
  browses (see browse mode above).
- `gene_ontology_terms.ontology` accepts a list (or `None`); a trust filter
  carried by only some of the requested ontologies applies to those and
  drops the rest into `skipped_ontologies` with a warning, one carried by
  none raises.
- TCDB leaf rows (`gene_ontology_terms(mode='leaf')`) exclude
  `attachment_depth='superseded'` ancestor attachments unless
  `include_superseded=True`.
- `Experiment.table_scope` is now sparse: absent (never `""`) on
  experiments with no differential-expression table. `list_experiments`
  loses the `""` bucket in `by_table_scope`; `table_scope=[...]` filters
  simply never match those experiments.
- `treatment_type` is dense and non-empty on `Experiment`,
  `ClusteringAnalysis`, `DerivedMetric` and `MetaboliteAssay`; a
  characterization study with no perturbation carries a measurement-type
  value such as `rna_decay` / `tss_mapping` / `genomic_analysis`.
  `background_factors` is dense, `[]` only on sequence-only clustering
  analyses. `treatment_type` gains the values `chemical`, `oxygen`,
  `rna_decay`, `tss_mapping`, `genomic_analysis`; `growth_phases` stays an
  open vocabulary.
- KG paper batch absorbed: 48 organisms (adds *Synechococcus* WH8109),
  49 publications, 209 experiments; new `DerivedMetric` metric types
  (mRNA half-life / decay time, TSS and promoter features) are discoverable
  via `list_derived_metrics`. Schema baseline and regression goldens
  refreshed accordingly.

- **Breaking:** `genes_by_metabolite` / `metabolites_by_gene` param
  `transport_confidence` renamed to `substrate_depth`
  (`list['most_specific' | 'inherited']`, transport arm only). The retired
  values `substrate_confirmed` / `family_inferred` raise `ValueError` with a
  rename pointer. Row field `transport_confidence` → `substrate_depth`
  (straight from the KG edge). Envelope renames: `by_transport_confidence`
  → `by_substrate_depth` (key `substrate_depth`),
  `transport_substrate_confirmed_rows` / `transport_family_inferred_rows` →
  `transport_most_specific_rows` / `transport_inherited_rows`. Detail sort is
  now metabolism → `most_specific` → `inherited`, then `tcdb_evidence_score`
  descending. The old explorer-derived vocabulary (from
  `level_kind = 'tc_specificity'`) no longer matched the KG's substrate
  edges; see the spec above.
- **Breaking:** `gene_overview` row field `transporter_count` removed. It
  counted every TCDB attachment including ancestors superseded by a more
  specific call on the same gene — the wrong multiplicity under the
  deepest-attachment rule. Use `tcdb_evidence_score_max` (any call, how
  corroborated) + `transport_substrate_resolution` + `transported_metabolite_count`.
- Transport-arm rows in `genes_by_metabolite` / `metabolites_by_gene`, and
  the traversal behind `gene_overview.evidence_sources` / `has_chemistry`,
  are now deepest-attachment projections: an attachment to a TCDB family is
  skipped when the same gene is also attached to one of its descendants.
  Rows and the KG's precomputed counts (`transported_metabolite_count`,
  `transporter_gene_count`) are projections of one (gene, metabolite) set
  and agree by construction (PMM0392: 13 metabolites in both places, not
  554). Superseded ancestor rows are intentionally absent; ancestor
  membership remains visible via `gene_ontology_terms(ontology='tcdb')`.
  Rationale and live verification:
  `docs/kg-specs/2026-08-26-review-tcdb-substrate-depth-migration.md`.

- **Breaking:** `gene_overview` row field `metabolite_count` renamed to
  `catalyzed_metabolite_count`. Driven by KG-SYNC-001
  (`docs/kg-specs/2026-08-19-presync-kg-asks.md`): the KG retired the union
  (reaction OR transport) `Gene.metabolite_count` in favor of a
  catalysis-arm-only count (`Gene → Reaction → Metabolite`). A transport-only
  gene now reads 0 here with `'transport'` in `evidence_sources` (and, as of
  the TCDB substrate-depth migration below, `transported_metabolite_count > 0`).
- **Breaking:** `list_organisms` row field `metabolite_count` and the
  `by_metabolic_capability[].metabolite_count` envelope key renamed to
  `catalyzed_metabolite_count` (KG-SYNC-001). Semantics unchanged in spirit
  (this count was already catalysis-only) — the name now says so and matches
  the KG property 1:1.
- **Breaking:** `list_metabolites` row field `gene_count` renamed to
  `catalyst_gene_count` (KG-SYNC-001), now counting the catalysis arm only.
  The old guidance "`gene_count = 0` means metabolomics-only" no longer holds:
  transport-only metabolites also read 0. Discriminate via `evidence_sources`
  (`['metabolomics']`-only means no gene path at all) or, as of the TCDB
  substrate-depth migration below, `transporter_gene_count > 0`.

### Fixed
- `genes_by_homolog_group` / `differential_expression_by_ortholog` gain the `warnings: list[str]` envelope key every other coercing tool already had (empty when clean). `_run_fulltext` now reports a missing / unavailable fulltext index as "fulltext index unavailable … check kg_release_info" instead of mislabelling it a Lucene syntax error; only a real `ParseException` gets the Lucene message. (llm-review 2b.12)
- `genes_by_function`: a fulltext hit count with `total_matching=0` after `organism` / `category` / `min_quality` now reports an empty-intersection warning naming the active filters (was a bare zero that read as "no such genes in this organism"; `category` is an exact `Gene.gene_category` match and `'Transport'` is a small category — most transporters sit under `'Inorganic ion transport'`). New `mistakes` entry. (upstream ticket 2026-08 #1)
- `differential_expression_by_gene` docs: `rank` is the KG property `rank_by_effect` (direction-blind, on every reported edge); `rank_up` / `rank_down` are explicitly NOT genome-wide directional ranks — populated on the significant subset only, unusable as a GSEA ranking. Field descriptions + `mistakes` entry; GSEA itself queued as backlog 3.19. (upstream ticket 2026-08 #2)
- `genes_by_boolean_metric(flag=False)` always reported `true_count: 0` regardless of the DM's real flagged-edge count; it now reads the actual count.
- `genes_in_cluster` set `not_matched_organism` on any zero-row result, not just a genuine organism mismatch, which also made `cluster_enrichment`'s exists-but-empty warning path unreachable (it raised `"analysis_id not found"` instead); the check now only fires on a real mismatch.
- `pathway_enrichment`'s compact `experiments[]` rows (`ExpressionByExperiment`) serialized their verbose-only fields as explicit `null` on the wire instead of omitting them; the row class now inherits `SparseRow` so compact mode only carries the keys the API layer actually set. `top_pathways_by_padj` is a genuine top-10 in both `summary` modes (the `_truncated` companion key it never needed is removed). `resolve_gene`'s and `list_publications`'s `*_truncated` field descriptions pointed callers at `summary=True` to get the full list, which doesn't apply to those breakdowns; they now point at pagination / the right full-breakdown tool instead.
- `cluster_enrichment` / `pathway_enrichment` envelope rows emitted NaN for clusters with no description text (pandas str-column hole), which the MCP layer rejected; rows now carry `None`.
- Outfacing-doc lint no longer scans inside ```example-response fences (live KG payloads are data, not prose).

- `docs://ontologies/index` summary column no longer truncates at the
  YAML line wrap: summaries end at the first sentence (or a word boundary
  with `…`).

- One-edge-per-(gene, term) rebind on the ontology tools picked the
  **lowest**-ranked edge: the rebind reversed the output of
  `apoc.coll.sortMaps`, which already sorts descending, so multi-edge
  (gene, term) pairs reported the least-supported edge's trust columns.
  Rows now carry the best edge (highest `evidence_score` /
  `confidence_score` / deepest attachment). Row counts are unchanged; only
  the trust columns of multi-edge rollup rows move.
- `genes_by_ontology` full-match trust rollups no longer re-scan the detail
  rows on every paged call (aggregate-only projection).
- `search_ontology` / `ontology_term_details` resolve organism shorthand
  (`'MED4'`) the way the other single-organism tools do, and strip a null
  `direct_gene_count` instead of returning it as an applicable-but-empty
  key.

- `list_filter_values` now serves `treatment_type`, `background_factors`,
  `table_scope`, `detection_status` and `expression_status` (previously
  raised `Unknown filter_type` for all five); rows correctly union
  `applies_to` across the labels/edges each vocabulary spans, and
  per-value `source` (`vocabulary` vs pivot fallback) is tracked per value
  instead of one flag shared across every row.
- `genes_by_metabolite` / `metabolites_by_gene` now resolve `organism`
  once and enforce single-organism: an ambiguous genus word (e.g.
  `'Prochlorococcus'`) raises instead of silently blending rows from every
  matching strain, and `metabolites_by_gene`'s existence probe uses the
  resolved canonical organism name instead of the raw input, fixing a
  false-positive `not_found.locus_tags` for genes that actually exist.
- `pathway_enrichment` rows carry real experiment metadata again —
  `omics_type`, `table_scope`, `background_factors`, `is_time_course` and
  `name` (from `experiment_name`) were always null and `by_omics_type` was
  always empty, because the metadata was copied from compact-verbosity DE
  rows that never carry those columns; now merged in from `list_experiments`.
- `pathway_enrichment` raises on all-unknown `experiment_ids` and on an
  out-of-range `level` for the chosen ontology instead of returning a
  vacuous empty envelope; a partial batch of ids surfaces the unknown ones
  in the new `not_found_experiments` envelope key. `cluster_enrichment`
  raises the same way on an unknown `analysis_id` and an out-of-range
  `level`.
- Tested-absent (`detection_status='not_detected'`) rows on
  `metabolites_by_quantifies_assay` and `assays_by_metabolite` no longer
  carry a `metric_bucket` / `metric_percentile` / `rank_by_metric` — those
  were statistical artifacts of ranking over raw values including zeros,
  not a real signal on an untested/absent measurement; rank-gated filters
  now also exclude tested-absent rows so filtering and display agree.
  `assays_by_metabolite(summary=True)` computed `not_matched` /
  `metabolites_with_evidence` / `metabolites_without_evidence` from the
  (empty, in summary mode) `results` list, so metabolites with real
  evidence were wrongly reported as unmatched; the summary buckets now
  derive from the full filtered match set.
- `differential_expression_by_gene` and `gene_response_profile` used to
  fold a typo'd or unknown `growth_phases` / `treatment_types` value into
  `no_expression`, which is documented to mean "no expression edges at
  all" — misleading a caller into thinking a gene has no data instead of
  telling them their filter value doesn't exist. Both tools now
  distinguish the two cases (`filtered_out` for "has expression, just not
  matching this filter" vs `no_expression` for "no edges at all") and add
  a `warnings` entry naming the unrecognized value and pointing at
  `list_filter_values`.
- `genes_by_homolog_group`'s `by_organism` breakdown reordered between KG
  rebuilds whenever two organisms tied on count (no defined tie order from
  the underlying aggregation); now sorted count DESC, then
  `organism_name` ASC for a stable order across rebuilds.
- Documentation corrections: DM rankable-filter param names on the row
  fields they populate, real (not fabricated) experiment IDs in the
  Python-API worked example, `genes_by_function`'s `category` param name
  (was documented as `gene_categories`), the `table_scope` collapse
  sentence on the DE tools, and PSORTb/SignalP referred to by their actual
  ontology keys (`subcellular_localization` / `signal_peptide_type`)
  instead of implying they're informal names only.

## [0.1.0-alpha.4] - 2026-06-17
### Fixed
- `to_dataframe()` no longer drops the polymorphic `value` column from
  `gene_derived_metrics` results when a query mixes metric kinds (e.g. numeric
  + boolean + categorical). Such columns hold mixed scalar Python types, which
  pandas types as `object`; the flattener previously treated any non-list/dict
  `object` column as unflattenable and dropped it with a warning. Mixed-scalar
  columns are now kept as-is. Columns with genuine nesting still drop as before.

## [0.1.0-alpha.3] - 2026-06-15
### Added
- Corner-case verification harness (`tests/integration/edge_cases/` +
  `tests/integration/test_edge_case_contracts.py`): every MCP tool is exercised
  against degenerate-but-valid inputs (genome-only / expression-empty
  organisms, missing & mixed batches, pagination/filter-empty boundaries,
  null-valued properties such as coordinate-less genes) and
  checked against structural invariants (no crash, schema validity, count
  consistency, batch-diagnostic subsetting, empty-layer shape). A self-validating
  fixture bank re-pins after KG rebuilds, and a coverage gate fails if a
  registered tool has no edge-case scenarios.

### Changed

### Fixed
- `differential_expression_by_gene` no longer crashes on genes with zero
  differential-expression edges. The batch `top_categories` builder leaked a
  synthetic `{category: null, …}` row that violated the non-nullable
  `ExpressionTopCategory.category` model (raising a `ToolError`); null
  categories are now filtered out in both the batch and global builders.
  Surfaced by the new corner-case harness.
- Organism resolution no longer requires expression data. The shared
  `_validate_organism_inputs` resolver matched `Experiment` nodes with
  `gene_count > 0`, so genome-only (`experiment_count=0`) and
  metabolomics-only strains were unresolvable — every single-organism
  genomic tool (`genes_by_ontology`, `gene_ontology_terms`, …) raised
  `no organism matching '<name>' found` for them. Now matches
  `OrganismTaxon` with `gene_count > 0` (genomic presence, not expression),
  so any real organism — including genome-only / metabolomics-only strains —
  resolves, while gene-less higher-rank taxonomy nodes (genus / phage /
  non-target species) still raise a clear not-found instead of silently
  returning empty results.

## [0.1.0-alpha.2] - 2026-06-13
### Added
- `discussed_by_publication` MCP tool — forward literature-index lookup
  (publication DOIs → genes + KEGG pathways the paper names in prose).
  `UNION ALL` over `Publication_discusses_gene` +
  `Publication_discusses_kegg_pathway`; polymorphic rows
  (`entity_kind` / `entity_id` / `entity_name` / `prominence`, union-padded
  organism), summary rollups (`by_entity_kind`, `by_prominence`,
  `top_kegg_pathways`, `top_publications`), case-insensitive DOI matching,
  `not_found` / `not_matched`, offset pagination. Recall-biased narrative
  router — NOT exhaustive, NOT DE-table expression.
- Discusses literature-index surfaced across 3 existing discovery tools:
  `gene_overview` (per-gene `discussed_in_publication_count`, envelope
  `has_discussed` + `top_discussing_publications`; verbose
  `discussed_in_publications`), `list_publications` (per-row
  `discussed_gene_count` / `discussed_pathway_count`, envelope
  `by_discusses_coverage`), `search_ontology` (KEGG-only
  `discussed_by_n_publications`; verbose per-term `discussed_in_publications`).
- `kg_release_info` surfaces `Schema_info.release_highlights` +
  `breaking_changes` — passthrough of two optional properties the KG stamps
  on official (non-dev) releases. `KGIdentity` gains both fields (`str | None`,
  `None` on dev/legacy builds); `summary` appends short pointers when present.
  Kept passive by design (no recurring `ctx.warning`).
- `kg_release_info` surfaces `Schema_info.deployment_role`
  (`local-dev` | `staging` | `production`), stamped by the KG at build time.
  Flows through `_KG_IDENTITY_FIELDS` + `KGIdentity` like other identity
  fields; `null` → rendered as unknown on legacy KGs.

### Changed
- Correctness pass on the LLM-facing doc surface (guides, analysis docs, tool
  YAMLs, `CLAUDE.md`, server instructions) reconciled with the current
  41-tool set and live KG: tool count normalized to 41, stale `query=` alias
  removed from 5 example calls, missing `kg_release_info` row + summary stats
  added, enrichment/metabolites/concepts/conventions doc fixes.
- Anti-drift guards added (`tests/unit/test_about_content.py`): validate every
  example/steps/chaining kwarg against the live tool schema; assert every
  registered tool has a YAML + doc + `CLAUDE.md` row; assert hard-coded
  "N tools" claims match the live registry. Removed the stale
  experiment-characterization skill.

### Fixed
- `discussed_by_publication`: rename APOC frequency keys
  (`by_entity_kind` / `by_prominence`) to the semantic keys the Pydantic
  breakdown models require — a mock-invisible Pydantic validation error that
  only surfaced on live MCP calls.

### Tests / Internal
- Reconcile counts + regression goldens for the 2026-06-13 KG rebuild
  (+2 genome-only organisms, 45→47: Prochlorococcus MIT1314 / MIT1327): 5
  hard-coded integration assertions updated, 43 regression goldens
  regenerated (verified pure data drift, no structural changes).

## [0.1.0-alpha.1] - 2026-06-09
### Added
- `kg_release_info` MCP tool: returns the KG's release identity
  (`Schema_info` properties — version, built_at, counts, git identity)
  and a three-valued compatibility verdict (`ok` / `warn` / `unknown`)
  against the installed explorer version. Run by the MCP server lifespan
  at startup; cached on `KGContext`; tool reads from cache. PEP 440
  version comparison via `packaging.version.Version` (catches the
  pre-release-vs-release coordination case). 16 asserts in the v1
  EXPECTED_KG_SHAPE check (5 Schema_info properties + 5 node labels +
  3 relationship types + 2 non-zero counts + 1 version compat). See
  `docs/superpowers/specs/2026-06-02-kg-compatibility-check-design.md`.
- MCP server `instructions` updated to point agents at `kg_release_info`
  as a first call in any new session.
- Read-only Python toolkit for the Prochlorococcus/Alteromonas multi-omics
  knowledge graph (Neo4j). Two surfaces shipped:
  - **Python API** (`multiomics_explorer.api.functions`) — programmatic
    access for scripting and notebook use.
  - **MCP server** (`multiomics-kg-mcp`) — ~39 domain-specific tools for
    Claude Code: gene resolution, expression lookups, ontology enrichment,
    metabolite searches, derived-metric drill-downs, clustering, sequence /
    neighborhood lookup, ortholog navigation, and a `run_cypher` escape
    hatch (writes blocked).
- Neo4j env-var hygiene: `NEO4J_USERNAME` canonical (matches Neo4j BKM —
  Aura "Connect" credential file, Cypher Shell), `NEO4J_USER` accepted as
  back-compat alias via pydantic `AliasChoices`. `NEO4J_DATABASE` plumbed
  through to `driver.session(database=...)` (default `"neo4j"`).
- PyPI-readiness metadata in `pyproject.toml`: `[project.urls]`, keywords,
  classifiers, License-File. Wheel build excludes dev-only `inputs/`
  (consumed by `scripts/build_about_content.py`); LICENSE + generated
  skills/MD ship.
- `CHANGELOG.md` (this file) and the `/release-explorer` skill (`.claude/skills/release-explorer/`).

### Changed
- Tag scheme finalized as `v<version>` matching the KG's pre-release suffix
  discipline (`-(alpha|beta|rc).N`). First release is `v0.1.0-alpha.1`,
  not bare `v0.1.0`, to support the alpha cycle cleanly.

### Removed
- The `multiomics-explorer` CLI surface (only `multiomics-kg-mcp` console
  script remains). `typer` and `rich` dropped from runtime dependencies.
- Unused LangChain-agent fields from `Settings` (`model`, `model_provider`,
  `model_temperature`, `anthropic_api_key`, `openai_api_key`).
- Committed `mcpServers` block in `.claude/settings.json` (was hardcoded to
  one machine's path); simplified `.mcp.json` to drop the
  `${MULTIOMICS_EXPLORER_DIR}` indirection.

### Fixed
- `NEO4J_DATABASE` was previously a silent no-op (env var was documented in
  the KG MCP guide but ignored by the explorer). Driver session now honors
  it; forward-compatible for future non-default-DB releases.
