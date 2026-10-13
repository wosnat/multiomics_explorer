# Explorer backlog

Single list of open work for `multiomics_explorer`. One line per item: what, why, size, origin.
Status was verified against `main` on 2026-08-29 (HEAD `f7b9a70`, live KG dev build 2026-08-29T06:22Z). When an item ships, delete it
here and let the CHANGELOG carry the record — this file is only ever the *open* set.

Sizes: **S** ≤ half a day, no spec · **M** a day, one-page spec (Mode B) · **L** multi-day, full
`/add-or-update-tool` cycle · **KG** needs a KG-side change first.

## 1. Now — release cut (explorer 0.1.0-alpha.5 ↔ KG 0.1.0-alpha.7)

| # | Item | Size | Notes |
|---|---|---|---|
| 1.2 | KG alpha.7 cut landed 2026-09-15 (version + `mcp_min_version 0.1.0a5` stamped, hash unchanged, absorbed same day) — residual: `release_highlights` / `breaking_changes` were NOT stamped (both null) and `deployment_role` reads `staging`; ask KG side to stamp the §4 A1 draft on the next re-cut or confirm intentional. | KG | Highlights + breaking list drafted in §4 A1 below. |
| 1.3 | Eval pass on the annotation-trust surface in `multiomics_research` (protease vs dead-homolog, urea transporter ranking, InterPro superfamily ORA on a dark-survival cluster). | M | The contract gates are green; only agent-driven runs show whether routing / warnings / `docs://` pages lead to the right tool. Roadmap "stress test" step. |

## 2. Follow-ups from the sync-release program (slices 3–4 + polish), post-cut

| # | Item | Size | Origin |
|---|---|---|---|
| 2.8 | `organism=` word-match backlog: genus node `Alteromonas` matches all strains; `AltDE` matches `AltDE1`. Resolver gates on `gene_count > 0` so treatment taxa are safe (KG B4 removes the last name collision). | M | slice-2 ledger |
| 2.14 | Outfacing-identifier lint: cross-check backtick-quoted identifiers in tools.py Field/docstrings, inputs/tools/*.yaml, hand-authored references md, CLAUDE.md against live input-schema param names + response-model field names (final-review rec, llm-review 2b.5). | S | 2b.5 final review |
| 2.15 | alpha.6 queue: remove api/_compat aliases; rename not_found.publication_doi buckets to publication_dois on the 3 metabolomics tools; consider compartment as list[str]; listify-or-reject bare str on remaining list[str] vocab params (3.18); align `kg_release_info(conn)` to the `conn: GraphConnection \| None = None` keyword-only contract (docs-review 2026-09-15 — python_api.md documents the exception meanwhile). | M | 2b.5 final review |
| 2.16 | Docs-surface guards (2b.4 final review): brief-sections lint (every brief carries Example/Response sketch/mistakes/chaining-or-marker), lint_index_size, kg_claims used_in content check, TOC line-number pin test, params.py verbose text names /full. | S | 2b.4 final review |

## 2b. LLM-consumer review 2026-08-29 (six-reviewer pass; report artifact `Explorer MCP Through an LLM's Eyes`, raw reports in session scratchpad)

| # | Item | Size | Status |
|---|---|---|---|
| 2b.6 | **Consolidation** (release boundary + KG `mcp_min_version`). Kept post-cut 2026-08-30 — tool merges too risky before alpha.5; means alpha.6 is a second breaking release. Merge `metabolites_by_quantifies_assay` + `metabolites_by_flags_assay` → `metabolites_by_assay`; merge or front the three `genes_by_*_metric`; `SKILL.md` for the skill tree and collapse CLAUDE.md's tool table; delete the research repo's duplicate python guide + fix its dangling `docs://analysis/to_dataframe` link. | L | queued |

## 2c. Pro N-import coculture analysis 2026-10-06 (`multiomics_analysis/analyses/2026-10-06-pro_n_import_coculture/gaps_and_friction.md`)

Explorer-side items only; KG asks from the same log are §4 D. Template / methodology entries in that log stay in the analysis repo.

| # | Item | Size | Notes |
|---|---|---|---|
| 2c.2 | Genome-coordinate listing: all genes of an organism with contig / start / end / strand, pageable, flagging the coordinate-less ones. The analysis needed it and swept `gene_neighbors` (8 × window=250) + `gene_details` instead. The OOM half shipped 2026-10-13 (window ≤ 100, row budget). Could be a `gene_details` organism mode instead of a new tool. | M | |
| 2c.5 | `list_metabolites` transport reach is flat (`top_organisms` 1,294–1,304 of 1,462 for every organism) because `m.organism_names` unions inherited superfamily (ABC) substrates. Most-specific-only reach does discriminate (639 MED4 … 1,201 Pseudomonas KT2440). Blocked on the KG precompute `Metabolite.transport_most_specific_organism_names`; then rebuild `top_organisms` / the organism filter for transport on it. Interim fallback: compute per call in Cypher. | M | KG ask (drafted 2026-10-13) |
| 2c.6 | `coculture_partner` is set only when coculture is the *treatment*. The 8 Weissberg 2025 N-starvation experiments (and García-Fernández glucose proteomics) have `background_factors: ['coculture']` and partner null, so the filter misses them and the agent reported "no Pro proteomics in coculture". Fix the param docs / `list_experiments` yaml mistakes section to say "treatment-only, also filter `background_factors=['coculture']`"; or, once KG D5 lands, match either field. | S | KG D5 |
| 2c.7 | TCDB transport rows on superfamily-only genes (e.g. `salY`, `inherited`) give the gene's own attachment (`tcdb:3.A.1`) as the family, not the TCDB node the substrate came from. Check the row shape, and consider a `substrate_source_family` field. | S | investigate first |

## 3. Older backlog — verified 2026-08-28

Shipped since the last refresh (removed from the open set): 3.9 metabolomics-DM slice (KG owner decided 2026-08-29: not planned, no driver dataset — reopenable); 3.10 KG-MET-002 (comment landed in rebuild #3); 3.6 static resources (verified 2026-08-29: every `docs://` URI is a static `FunctionResource`, no templates); `_freq_rollup` helper extraction;
`search_text` kwarg unification (only `run_cypher.query` differs, by design); `tcdb_level_kind` filter
type; KEGG pathway `reaction_count` / `metabolite_count` on term rows and `list_metabolites`
pathway rollups; `mcp_min_version` mismatch (live reads `0.1.0a1`, verdict `ok`); KG-MET asks
001/006/013/016.

| # | Item | Size | Notes |
|---|---|---|---|
| 3.5 | `kg_schema` property-description enrichment + analysis-doc `field_description` callout. | M | metabolites roadmap Track B |
| 3.7 | MCP usability audit passes B/C/D + KG-1..KG-7. Pass A shipped 2026-04-30. Re-scope against the current surface before starting — much of it landed via the readability passes and the trust surface. | L | audit |
| 3.8 | Chemistry slice 2+: `metabolites_by_pathway`, `list_reactions` / `genes_by_reaction`, `organism_metabolite_overlap`, Tier-3 `pathway_chemistry`. Defer until a workflow needs them. | L | chemistry design |
| 3.11 | PyPI publication (out of scope for `/release-explorer` v1; install path is the git tag). | M | release |
| 3.12 | Annotated-genes ORA background mode for `pathway_enrichment` / `cluster_enrichment` (per-organism genes with ≥1 edge in the chosen ontology; TIGR coverage bias — workaround is an explicit `background=` list from `genes_by_ontology(ontology='tigr_role', level=0)`). | S | tigr-role-bridge 2026-08-29 |
| 3.13 | Registry-driven outfacing lint: for every `ONTOLOGY_CONFIG` key with non-empty `hierarchy_rels`, flag md/yaml prose calling it "flat" or saying `level=1` returns nothing for it (the fixed `LINT_PATTERN` regex missed `search_ontology.yaml`, `genes_by_ontology.yaml`, `ontology_landscape.yaml` and two test comments during the TIGR absorb). | S | tigr-role-bridge code review 2026-08-29 |
| 3.17 | Generate the concepts-page node counts at build time (or keep them out — current policy) and add a `kg_claims.yaml` entry per number the guides still quote (48/47/43 organisms, ~127k genes, ~3% coordinate-less, ~70% / ~69% tested-absent, 11 of 27 boolean DMs). | S | docs review 2026-08-29 |
| 3.19 | GSEA (rank-based, e.g. fgsea-style permutation on a signed `log2fc` ranking) alongside the Fisher ORA in `pathway_enrichment` — the coculture analysis (`multiomics_analysis/docs/upstream-tickets-2026-08.md` #2) tried to build it on `rank_up` / `rank_down`, which are significant-only. Needs an `all_detected_genes` experiment (table_scope gate), a ranking choice (signed `log2fc` vs signed `rank`), and TERM2GENE from `genes_by_ontology` — same trust filters and background rules as ORA; `docs://analysis/enrichment` gets a GSEA section. Docs for the rank fields shipped 2026-08-30. | M | upstream ticket 2026-08 |
| 3.18 | Python-API input guards: `genes_by_metabolite` / `metabolites_by_gene` raise `TypeError` on `limit=None` (`offset + limit`, functions.py ~7122/7571/7276/7770 — signature says `int`, other tools accept `None`); list-typed params passed as a bare string (`list_experiments(omics_type='RNASEQ')`) iterate the string and silently match 0 rows via the API (MCP layer validates). Either accept `None` everywhere paging exists and reject `str` where `list[str]` is declared, or document. | S | docs review 2026-08-29 |

## 4. KG asks pending (explorer → KG)

Filed in chat 2026-08-28; the non-release set (B1–B3, new B5 rebuild-#3 ping, KG-MET-002, MET-DM spec question) is written up in
`multiomics_biocypher_kg/docs/kg-changes/2026-08-28-explorer-handoff.md` §"Explorer open asks (2026-08-29)". KG answered 2026-08-29 (same doc, §"KG answers to the consolidated explorer asks"): B2 + B3 + KG-MET-002 ship in rebuild #3 (hash-neutral); B1 filed KG-side as a trust-vocab slice after #3; MET-DM not planned.

**A — for the alpha.7 cut (P1)**
- A1. Stamp `Schema_info` at the cut: `version 0.1.0-alpha.7`, `mcp_min_version 0.1.0a5`, `git_sha_short`, `release_highlights` (KG-SYNC-005 trust surface; KG-SYNC-006 paper batch 49 pubs / 209 experiments / 48 organisms incl. WH8109; ORG-001 organism rollups; `controlled_vocabularies_hash` recipe; dense non-empty `treatment_type` / `background_factors` with `rna_decay` / `tss_mapping` / `genomic_analysis` / `oxygen`; Bernstein 2017 relabel; sparse `table_scope`), `breaking_changes` (InterPro `gene_count` direct → subtree; ncbifam `score` → `bit_score`; MeropsFamily `family_type` → `family_class`; `treatment_type: []` no longer occurs; `table_scope ""` → absent).
- A2. Hash freeze until the cut (extended ~1 week for 2b.5 + 2b.4, 2026-08-30): no `ControlledVocabulary` value / `min_size` / `signals` edits without telling the explorer (description-only edits are hash-neutral).

**B — small, whenever (P3)**
- ~~B1~~ landed in the 2026-08-29 08:53Z rebuild (`value_descriptions` on 39 of 122 `ControlledVocabulary` nodes, hash-neutral). 2.3 is unblocked.
- ~~B2~~ done in rebuild #3 (42 vocab descriptions rewritten researcher-facing; provenance → yaml comments; hash-neutral).
- ~~B3~~ done in rebuild #3 (`min_size: int` sparse on the vocab node — was dropped by BioCypher for lack of a schema slot; hash-neutral, no re-pin).
- ~~B5~~ rebuild #3 verified 2026-08-29 (07:22Z): `kg_release_info` ok, hash unchanged, 17/17 asserts; `min_size = 1` on the 7 promised vocab nodes; 4 goldens moved (3 Biller 2022 DM + `cluster_type` text), 2,904 `-m kg` passed after 4 stale pin fixes.
- ~~B4~~ closed 2026-08-28 (HO-002: synonyms + `taxonomy_note`, name kept). Was: two `OrganismTaxon` nodes share `preferred_name = 'Meiothermus ruber'` (genome strain + 0-gene treatment taxon) — disambiguate the treatment taxon's name or add a uniqueness validity test.

**D — from the Pro N-import coculture analysis 2026-10-06 (not yet filed KG-side)**
- D1. Metabolite equivalence across namespaces: nitrate `chebi:14654` (transport arm) and `kegg.compound:C00244` (metabolism arm) share no ChEBI / MNX / InChIKey xref (they are a conjugate pair). Generic "Cysteine" C00736 (TCDB) is not linked to "L-Cysteine" C00097 (reactions), which makes 20 of 49 zero-enzyme cells an ID artefact. Ask for an `equivalent_ids` field or an equivalence edge (charge-state + D/L-generic normalisation). Without it, joins between the transport and metabolism arms silently miss matches.
- D2. Chemical classes for Metabolite nodes (ChEBI is-a / role hierarchy or ClassyFire). Currently none; KEGG pathway or carrier-family proxies were ~50% wrong.
- D3. TCDB substrate granularity: subfamily lists are inherited by every member gene (`sul1`/`sul3` list amino acids + nitrate; `ktrA`/`nhaS` list ammonium; MIT9313 `putP` lists urea/nitrate/polyamines). Add a per-attachment substrate-breadth field or a "substrate plausible given genome" flag. Also: PepT depth looks inverted on `dpp` (generic peptide only `inherited`); missing / truncated names (`tcdb:4.C.1.1`, bare `1.A.1.x` / `2.A.88.x` show the ID; `3.A.1.4.4` = "The high-affinity ("); `urtE` has a stray score-0 `tcdb:1.B.42`.
- D4. Gene coordinates missing on 91 MED4 genes (~5%; e.g. `cyabrB2` PMM0573, `hli` PMM0815, `petL` PMM1718) and ~18% of MIT9313. Docs quote "~3%" overall (kg_claims, 3.17).
- D5. Populate `coculture_partner` whenever the culture is a coculture, not only when coculture is the treatment (pairs with 2c.6).
- D6. Experiments derived from one fitted model need a shared model / sample-set id, plus per-arm sampling day and growth state. The Weissberg anchor contrasts are algebraically linked (identity to 1e-15). The axenic arm is labelled d14 in one experiment and sits inside "d18" in another, and is labelled `nutrient_limited` although it is in full decline.
- D7. Culture-level measurement node type (cell counts, medium NH₄⁺/NO₃⁻, N biomass, DON): organism, condition, bottle id, time, growth phase, value, unit, measured/derived, extraction method. Medium nutrients can already go in as `spent_medium` metabolite assays. Researcher wants cell counts; it's not urgent.
- D8 (note): no KEGG reactions on di-/tripeptides; KO coverage gaps on transporters (`amt1`, `focA`). These are annotation limits, no ask yet.

**C — notes, no action**: `expression_bin` declared but unused (drift test checks in-use ⊆ declared); `direct_gene_count` absent on PfamClan / BriteCategory (documented); 4 publications without `discusses` edges (pre-existing extraction gaps).

## 5. Conventions this file relies on

- Absent = not applicable, null = applicable-but-empty (`docs://guide/conventions`); row-level models are `SparseRow`, union-shape rows (`GeneReactionMetaboliteTriplet`, `AssaysByMetaboliteResult`, `DiscussedByPublicationResult`) stay `BaseModel`.
- Every `(edge_or_label, prop)` the explorer filters or rolls up on has a `ControlledVocabulary` node (`-m kg` coverage test); runtime falls back to a pivot query + warning, never a hard-coded list.
- Build flow: `/add-or-update-tool` (spec freeze → worktree, `git reset --hard main` right after `EnterWorktree` → RED → GREEN ×4 file-owned agents, explicit-path staging → VERIFY: `--lint`, code review, unit, `-m kg`, regression `--force-regen` with a classified diff → finishing-a-development-branch).
