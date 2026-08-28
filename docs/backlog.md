# Explorer backlog

Single list of open work for `multiomics_explorer`. One line per item: what, why, size, origin.
Status was verified against `main` on 2026-08-28 (HEAD `aab0fbc`). When an item ships, delete it
here and let the CHANGELOG carry the record — this file is only ever the *open* set.

Sizes: **S** ≤ half a day, no spec · **M** a day, one-page spec (Mode B) · **L** multi-day, full
`/add-or-update-tool` cycle · **KG** needs a KG-side change first.

## 1. Now — release cut (explorer 0.1.0-alpha.5 ↔ KG 0.1.0-alpha.7)

| # | Item | Size | Notes |
|---|---|---|---|
| 1.1 | `/release-explorer 0.1.0-alpha.5` — cuts `[Unreleased]`, tags, builds, publishes; pushes `main` (~87 commits ahead of origin). | S | Preflight: pinned `EXPECTED_CONTROLLED_VOCABULARIES_HASH` (`sha256:d7191e2a…`, 2026-08-28 dev build) must equal the live KG's at the cut; KG must first fix `flag_true_count` / `flag_false_count` (ask R6). |
| 1.2 | KG cut pairing: `Schema_info.version = 0.1.0-alpha.7`, `mcp_min_version = 0.1.0a5` (new tool ⇒ a4 clients rejected), `release_highlights` / `breaking_changes` stamped. | KG | Highlights + breaking list drafted in §4 A1 below. |
| 1.3 | Eval pass on the annotation-trust surface in `multiomics_research` (protease vs dead-homolog, urea transporter ranking, InterPro superfamily ORA on a dark-survival cluster). | M | The contract gates are green; only agent-driven runs show whether routing / warnings / `docs://` pages lead to the right tool. Roadmap "stress test" step. |

## 2. Follow-ups from the sync-release program (slices 3–4 + polish), post-cut

| # | Item | Size | Origin |
|---|---|---|---|
| 2.2 | `search_ontology.organism_gene_count` / `min_gene_count` are DIRECT-edge (spec 3 §7.4) while `ontology_term_details.organism_gene_count` walks the subtree. Align to subtree; moves the pinned per-organism InterPro numbers (IPR027417 MED4 119). Needs one spec line. | M | 3b review #2; spec 3 §15 |
| 2.3 | `list_filter_values` description parity: `cluster_type` rows are sparse with the vocab text once on the envelope; trust types (`evidence`, `sources`, …) still repeat it per row. Make all vocab-backed types envelope-once. Depends on KG B1 (per-value descriptions) for the rows to carry anything useful. | S | polish item 6 |
| 2.4 | Generated `docs://ontologies/{key}` pages embed live `ControlledVocabulary` values when a KG is reachable at build time, else a `list_filter_values` pointer — build output depends on the environment. Decide: always pointer, or a cached snapshot in `config/schema_baseline.yaml`. | S | 3b review #11 |
| 2.5 | `by_level` in multi-ontology browse sums across ontologies whose `level` scales differ (`ontology=None`). Scope to single-ontology browse or document. | S | 3b review #10 |
| 2.6 | Redundant api-side `link_kinds` re-filter in `ontology_term_details` (builder already narrows the rel union). Dead code with a test pinning it. | S | 3b review #9 |
| 2.7 | Lint pattern for internal shorthand leaking into docstrings: `(?:PR|slice)\s?\d[ab]?\b`. Only code comments use it today. | S | 3b review recommendation |
| 2.8 | `organism=` word-match backlog: genus node `Alteromonas` matches all strains; `AltDE` matches `AltDE1`. Resolver gates on `gene_count > 0` so treatment taxa are safe (KG B4 removes the last name collision). | M | slice-2 ledger |
| 2.9 | Literal KG counts still pinned in some `-m kg` tests (browse S33 417, `go:0006979` 875, DM counts, nitrite sums) — each paper batch flips them. Consider `Schema_info`-relative or tolerance assertions for the ones that are not release guards. | S | slice-4 RED |

### 2b. From the KG hand-off 2026-08-28 (`multiomics_biocypher_kg/docs/kg-changes/2026-08-28-explorer-handoff.md`)

Shipped 2026-08-28 against the 11:58Z dev build: HO-001 two-state strings (`two_state()` helper, hash re-pinned), HO-002 taxid + `name_synonyms` resolver, `genes_by_boolean_metric` flag=False doc correction. Still open:

| # | Item | Size | Origin |
|---|---|---|---|
| 2.13 | 2.9 follow-through: use `Schema_info.organism_count` / `experiment_count` / `gene_count` / `paper_count` for tolerance assertions (R4: already stamped). | S | R4 |

## 3. Older backlog — verified 2026-08-28

Shipped since the last refresh (removed from the open set): `_freq_rollup` helper extraction;
`search_text` kwarg unification (only `run_cypher.query` differs, by design); `tcdb_level_kind` filter
type; KEGG pathway `reaction_count` / `metabolite_count` on term rows and `list_metabolites`
pathway rollups; `mcp_min_version` mismatch (live reads `0.1.0a1`, verdict `ok`); KG-MET asks
001/006/013/016.

| # | Item | Size | Notes |
|---|---|---|---|
| 3.2 | Bare metabolite IDs (`C00064`) → prefixed canonical form via `m.kegg_compound_id` in compound-anchored tools; extend to CHEBI / HMDB / MNXM. Partially present (`kegg_compound_id` used in 2 sites) — verify scope. | M | KG-MET-014 |
| 3.3 | Organism-name resolution policy: chemistry tools accept `'MED4'`, `list_organisms(organism_names=)` requires the full `preferred_name`. Standardise (slice 4 made `search_ontology` / `ontology_term_details` use the shared resolver — `list_organisms` is the last exact-match holdout). | S | KG-MET-015 |
| 3.4 | `gene_overview`: `tcdb_family_count` / `cazy_family_count` routing signals (parallel to chemistry counts). `transporter_count` was removed in slice 2 for counting superseded ancestors — any replacement must count `attachment_depth = 'most_specific'` only. | S | TCDB/CAZy follow-up |
| 3.5 | `kg_schema` property-description enrichment + analysis-doc `field_description` callout. | M | metabolites roadmap Track B |
| 3.6 | Static MCP resources: resource templates don't list; `docs://` is registered per file now (guide/analysis/tools/ontologies/examples) — verify nothing is still template-only, then close. | S | project_static_resources |
| 3.7 | MCP usability audit passes B/C/D + KG-1..KG-7. Pass A shipped 2026-04-30. Re-scope against the current surface before starting — much of it landed via the readability passes and the trust surface. | L | audit |
| 3.8 | Chemistry slice 2+: `metabolites_by_pathway`, `list_reactions` / `genes_by_reaction`, `organism_metabolite_overlap`, Tier-3 `pathway_chemistry`. Defer until a workflow needs them. | L | chemistry design |
| 3.9 | Metabolomics-DM slice (`list_metabolite_measurements`, `metabolite_response_profile`). Gated on a KG-side metabolomics-DM spec. | KG + L | metabolites roadmap |
| 3.10 | KG-MET-002 docstring-only ask (compartment-in-name convention comment in `schema_config.yaml`). | KG | lowest stakes |
| 3.11 | PyPI publication (out of scope for `/release-explorer` v1; install path is the git tag). | M | release |

## 4. KG asks pending (explorer → KG)

Filed in chat 2026-08-28; copy into `docs/kg-specs/` when the KG picks them up.

**A — for the alpha.7 cut (P1)**
- A1. Stamp `Schema_info` at the cut: `version 0.1.0-alpha.7`, `mcp_min_version 0.1.0a5`, `git_sha_short`, `release_highlights` (KG-SYNC-005 trust surface; KG-SYNC-006 paper batch 49 pubs / 209 experiments / 48 organisms incl. WH8109; ORG-001 organism rollups; `controlled_vocabularies_hash` recipe; dense non-empty `treatment_type` / `background_factors` with `rna_decay` / `tss_mapping` / `genomic_analysis` / `oxygen`; Bernstein 2017 relabel; sparse `table_scope`), `breaking_changes` (InterPro `gene_count` direct → subtree; ncbifam `score` → `bit_score`; MeropsFamily `family_type` → `family_class`; `treatment_type: []` no longer occurs; `table_scope ""` → absent).
- A2. Hash freeze until the cut: no `ControlledVocabulary` value / `min_size` / `signals` edits without telling the explorer (description-only edits are hash-neutral).

**B — small, whenever (P3)**
- B1. Per-value descriptions on closed vocabularies (`value_descriptions` map) — unblocks 2.3.
- B2. Vocab descriptions are user-facing (served by `list_filter_values`, `docs://ontologies`): drop script/paperconfig provenance from `ClusteringAnalysis.cluster_type`'s text.
- B3. Stamp `min_size` on the vocab node (yaml-only today).
- ~~B4~~ closed 2026-08-28 (HO-002: synonyms + `taxonomy_note`, name kept). Was: two `OrganismTaxon` nodes share `preferred_name = 'Meiothermus ruber'` (genome strain + 0-gene treatment taxon) — disambiguate the treatment taxon's name or add a uniqueness validity test.

**C — notes, no action**: `expression_bin` declared but unused (drift test checks in-use ⊆ declared); `direct_gene_count` absent on PfamClan / BriteCategory (documented); 4 publications without `discusses` edges (pre-existing extraction gaps).

## 5. Conventions this file relies on

- Absent = not applicable, null = applicable-but-empty (`docs://guide/conventions`); row-level models are `SparseRow`, union-shape rows (`GeneReactionMetaboliteTriplet`, `AssaysByMetaboliteResult`, `DiscussedByPublicationResult`) stay `BaseModel`.
- Every `(edge_or_label, prop)` the explorer filters or rolls up on has a `ControlledVocabulary` node (`-m kg` coverage test); runtime falls back to a pivot query + warning, never a hard-coded list.
- Build flow: `/add-or-update-tool` (spec freeze → worktree, `git reset --hard main` right after `EnterWorktree` → RED → GREEN ×4 file-owned agents, explicit-path staging → VERIFY: `--lint`, code review, unit, `-m kg`, regression `--force-regen` with a classified diff → finishing-a-development-branch).
