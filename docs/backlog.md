# Explorer backlog

Single list of open work for `multiomics_explorer`. One line per item: what, why, size, origin.
Status was verified against `main` on 2026-08-29 (HEAD `f7b9a70`, live KG dev build 2026-08-29T06:22Z). When an item ships, delete it
here and let the CHANGELOG carry the record — this file is only ever the *open* set.

Sizes: **S** ≤ half a day, no spec · **M** a day, one-page spec (Mode B) · **L** multi-day, full
`/add-or-update-tool` cycle · **KG** needs a KG-side change first.

## 1. Now — release cut (explorer 0.1.0-alpha.5 ↔ KG 0.1.0-alpha.7)

| # | Item | Size | Notes |
|---|---|---|---|
| 1.1 | `/release-explorer 0.1.0-alpha.5` — cuts `[Unreleased]`, tags, builds, publishes; pushes `main` (~87 commits ahead of origin). | S | Preflight: pinned `EXPECTED_CONTROLLED_VOCABULARIES_HASH` (`sha256:d7191e2a…`, 2026-08-28 dev build) must equal the live KG's at the cut (R6 flag counts verified fixed 2026-08-29; hash unchanged). |
| 1.2 | KG cut pairing: `Schema_info.version = 0.1.0-alpha.7`, `mcp_min_version = 0.1.0a5` (new tool ⇒ a4 clients rejected), `release_highlights` / `breaking_changes` stamped. | KG | Highlights + breaking list drafted in §4 A1 below. |
| 1.3 | Eval pass on the annotation-trust surface in `multiomics_research` (protease vs dead-homolog, urea transporter ranking, InterPro superfamily ORA on a dark-survival cluster). | M | The contract gates are green; only agent-driven runs show whether routing / warnings / `docs://` pages lead to the right tool. Roadmap "stress test" step. |

## 2. Follow-ups from the sync-release program (slices 3–4 + polish), post-cut

| # | Item | Size | Origin |
|---|---|---|---|
| 2.8 | `organism=` word-match backlog: genus node `Alteromonas` matches all strains; `AltDE` matches `AltDE1`. Resolver gates on `gene_count > 0` so treatment taxa are safe (KG B4 removes the last name collision). | M | slice-2 ledger |

### 2b. From the KG hand-off 2026-08-28 (`multiomics_biocypher_kg/docs/kg-changes/2026-08-28-explorer-handoff.md`)

Shipped 2026-08-28 against the 11:58Z dev build: HO-001 two-state strings (`two_state()` helper, hash re-pinned), HO-002 taxid + `name_synonyms` resolver, `genes_by_boolean_metric` flag=False doc correction. Still open:

| # | Item | Size | Origin |
|---|---|---|---|
| 2.13 | ~~2.9~~ shipped 2026-08-29 (`kg_count` fixture; ~30 paper-batch-fragile pins now assert against live Cypher / node precomputes). Left as deliberate guards: chemistry counts (`list_metabolites` N / N+P / MED4+N), Phase-5 metabolomics §7 fixtures, `cases.yaml` eval snapshots (rankable 42/41). `Schema_info.*_count` not needed after all — per-count live queries were more precise. | — | R4 |

## 2b. LLM-consumer review 2026-08-29 (six-reviewer pass; report artifact `Explorer MCP Through an LLM's Eyes`, raw reports in session scratchpad)

| # | Item | Size | Status |
|---|---|---|---|
| 2b.4 | **Discovery layer.** `docs://index` (~600 tok, sizes + read-when), guides registered first, instructions carry sizes + the `summary=True` habit; generated tool pages split brief / `/full` with capped example blocks (`kg_schema` page 26k → ~1k); `conventions` cut to its ~4.5k cross-tool core with `annotation_evidence` / `metabolites` as canonical homes (absorbs 3.15); `start_here` trimmed to family table + shapes, add cross-feeding and DE-by-functional-class recipes, step 0 for enrichment; `examples/*.py` scenario TOC. | M | queued |
| 2b.5 | **Schema diet.** Five-slot description template ≤150 tok; shared Field constants (organism ×27, trust filters ×5, informative_only ×5, metabolite-id coercion ×6); twin-name alignment with one-release aliases (`min_value`/`value_min`, `bucket`/`metric_bucket`, `flag`/`flag_value`, `category`→`gene_categories`, `publication_doi(s)`, `treatment_type` str→list on `list_publications`, `direction` enums); drop the `has_p_value` surface until the KG ships p-values; decide the `outputSchema` policy (342 KB of the 508 KB tools/list). | M | queued |
| 2b.6 | **Consolidation** (release boundary + KG `mcp_min_version`). Merge `metabolites_by_quantifies_assay` + `metabolites_by_flags_assay` → `metabolites_by_assay`; merge or front the three `genes_by_*_metric`; `treatment_type` / `background_factors` filters on both DE tools; `SKILL.md` for the skill tree and collapse CLAUDE.md's tool table; delete the research repo's duplicate python guide + fix its dangling `docs://analysis/to_dataframe` link. | L | queued |
| 2b.7 | real `summary=` on `resolve_gene` / `list_publications` threaded into `_cap_breakdowns` (restores the by_organism-sum invariant; no `limit=0` overload). | S | queued |
| 2b.8 | `n_experiments` duplicates `experiment_count` on `differential_expression_by_gene` — drop one in 2b.5. | S | queued |
| 2b.9 | audit remaining MCP row models for `SparseRow` (ExpressionByExperiment was the last found non-sparse). | S | queued |
| 2b.10 | `summary=True` is no longer reliably the cheap call on `metabolites_by_gene` — one conventions sentence. | S | queued |
| 2b.11 | `_cap_breakdowns` is imported privately by `analysis/enrichment.py` — move to a shared module. | S | queued |
| 2b.12 | `warnings` key on `genes_by_homolog_group` / `differential_expression_by_ortholog` (the only coercing tools without one); narrow `_run_fulltext`'s catch to `ParseException` or mention index-unavailable in the message. | S | llm-review 2b.3 final review |

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
| 3.14 | Move the `response_matrix` / `gene_set_compare` API reference (~140 lines) out of `docs://guide/python_api` into a new hand-authored `docs://analysis/expression` page (DE tools + cross-experiment summarization), leaving a pointer. Blocked only on writing the page. | S | docs review 2026-08-29 |
| 3.15 | Split the chemistry sections of `docs://guide/conventions` (transport trust ladder, direction-agnosticism, metabolite ID forms) into their own page or fold them into `docs://analysis/metabolites`; conventions keeps one-paragraph pointers. | S | docs review 2026-08-29 |
| 3.17 | Generate the concepts-page node counts at build time (or keep them out — current policy) and add a `kg_claims.yaml` entry per number the guides still quote (48/47/43 organisms, ~127k genes, ~3% coordinate-less, ~70% / ~69% tested-absent, 11 of 27 boolean DMs). | S | docs review 2026-08-29 |
| 3.18 | Python-API input guards: `genes_by_metabolite` / `metabolites_by_gene` raise `TypeError` on `limit=None` (`offset + limit`, functions.py ~7122/7571/7276/7770 — signature says `int`, other tools accept `None`); list-typed params passed as a bare string (`list_experiments(omics_type='RNASEQ')`) iterate the string and silently match 0 rows via the API (MCP layer validates). Either accept `None` everywhere paging exists and reject `str` where `list[str]` is declared, or document. | S | docs review 2026-08-29 |

## 4. KG asks pending (explorer → KG)

Filed in chat 2026-08-28; the non-release set (B1–B3, new B5 rebuild-#3 ping, KG-MET-002, MET-DM spec question) is written up in
`multiomics_biocypher_kg/docs/kg-changes/2026-08-28-explorer-handoff.md` §"Explorer open asks (2026-08-29)". KG answered 2026-08-29 (same doc, §"KG answers to the consolidated explorer asks"): B2 + B3 + KG-MET-002 ship in rebuild #3 (hash-neutral); B1 filed KG-side as a trust-vocab slice after #3; MET-DM not planned.

**A — for the alpha.7 cut (P1)**
- A1. Stamp `Schema_info` at the cut: `version 0.1.0-alpha.7`, `mcp_min_version 0.1.0a5`, `git_sha_short`, `release_highlights` (KG-SYNC-005 trust surface; KG-SYNC-006 paper batch 49 pubs / 209 experiments / 48 organisms incl. WH8109; ORG-001 organism rollups; `controlled_vocabularies_hash` recipe; dense non-empty `treatment_type` / `background_factors` with `rna_decay` / `tss_mapping` / `genomic_analysis` / `oxygen`; Bernstein 2017 relabel; sparse `table_scope`), `breaking_changes` (InterPro `gene_count` direct → subtree; ncbifam `score` → `bit_score`; MeropsFamily `family_type` → `family_class`; `treatment_type: []` no longer occurs; `table_scope ""` → absent).
- A2. Hash freeze until the cut: no `ControlledVocabulary` value / `min_size` / `signals` edits without telling the explorer (description-only edits are hash-neutral).

**B — small, whenever (P3)**
- ~~B1~~ landed in the 2026-08-29 08:53Z rebuild (`value_descriptions` on 39 of 122 `ControlledVocabulary` nodes, hash-neutral). 2.3 is unblocked.
- ~~B2~~ done in rebuild #3 (42 vocab descriptions rewritten researcher-facing; provenance → yaml comments; hash-neutral).
- ~~B3~~ done in rebuild #3 (`min_size: int` sparse on the vocab node — was dropped by BioCypher for lack of a schema slot; hash-neutral, no re-pin).
- ~~B5~~ rebuild #3 verified 2026-08-29 (07:22Z): `kg_release_info` ok, hash unchanged, 17/17 asserts; `min_size = 1` on the 7 promised vocab nodes; 4 goldens moved (3 Biller 2022 DM + `cluster_type` text), 2,904 `-m kg` passed after 4 stale pin fixes.
- ~~B4~~ closed 2026-08-28 (HO-002: synonyms + `taxonomy_note`, name kept). Was: two `OrganismTaxon` nodes share `preferred_name = 'Meiothermus ruber'` (genome strain + 0-gene treatment taxon) — disambiguate the treatment taxon's name or add a uniqueness validity test.

**C — notes, no action**: `expression_bin` declared but unused (drift test checks in-use ⊆ declared); `direct_gene_count` absent on PfamClan / BriteCategory (documented); 4 publications without `discusses` edges (pre-existing extraction gaps).

## 5. Conventions this file relies on

- Absent = not applicable, null = applicable-but-empty (`docs://guide/conventions`); row-level models are `SparseRow`, union-shape rows (`GeneReactionMetaboliteTriplet`, `AssaysByMetaboliteResult`, `DiscussedByPublicationResult`) stay `BaseModel`.
- Every `(edge_or_label, prop)` the explorer filters or rolls up on has a `ControlledVocabulary` node (`-m kg` coverage test); runtime falls back to a pivot query + warning, never a hard-coded list.
- Build flow: `/add-or-update-tool` (spec freeze → worktree, `git reset --hard main` right after `EnterWorktree` → RED → GREEN ×4 file-owned agents, explicit-path staging → VERIFY: `--lint`, code review, unit, `-m kg`, regression `--force-regen` with a classified diff → finishing-a-development-branch).
