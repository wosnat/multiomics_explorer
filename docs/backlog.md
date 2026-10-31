# Explorer backlog

Single list of open work for `multiomics_explorer`. One line per item: what, why, size, origin.
Status was verified against `main` on 2026-10-31 (live KG dev build 2026-10-31T19:34Z; `main` = `origin/main`). When an item ships, delete it
here and let the CHANGELOG carry the record — this file is only ever the *open* set.

Sizes: **S** ≤ half a day, no spec · **M** a day, one-page spec (Mode B) · **L** multi-day, full
`/add-or-update-tool` cycle · **KG** needs a KG-side change first.

## 1. Now — next release (explorer 0.1.0-alpha.6, breaking)

`[Unreleased]` already carries breaking changes (alpha.5 alias removal, TCDB cleanup, `coculture_partner` list, `not_found.publication_dois`, `kg_release_info` kw-only) plus the metabolite identity / stereo surface, GO transport arm and `control_timing`.

| # | Item | Size | Notes |
|---|---|---|---|
| 1.1 | Cut alpha.6 with `/release-explorer` (CHANGELOG `[Unreleased]` → dated section; polish the Breaking list). | S | was 2c.12 |
| 1.2 | KG-side coordination for that cut: next official KG release sets `mcp_min_version` to the alpha.6 version and stamps `release_highlights` / `breaking_changes` (alpha.7 shipped with both null; live dev build still null). Draft both from the CHANGELOG once 1.1 is polished. | KG | §5 A1 |
| 1.3 | Decide whether 2b.6 consolidation rides this breaking release or becomes a separate alpha.7 (it was deferred from alpha.5 to avoid two breaking releases in a row — alpha.6 is already breaking). | — | decision |

## 2. Next — small, concrete (no design needed)

| # | Item | Size | Origin |
|---|---|---|---|
| 2d.1 | Cap pasted example responses in `refresh_examples.py` (≤ N rows, truncate nested dicts/lists) and refresh: ~5k YAML lines of untrimmed responses; `tools/full/genes_by_metabolite.md` ~23.6k tok, mostly responses. Then drop responses whose point the note already carries. Absorbs old 2c.11 (stereo-hint examples bloated three full pages; CLAUDE.md `list_metabolites` row lost "unlisted ≠ not in it" for KEGG classes at the 700-char limit). | M | docs-review 2026-10-31 |
| 2d.2 | Cap `summary=True` envelopes on `list_organisms` / `list_publications` / `resolve_gene` / `list_experiments` (larger than the default 5-row page today; docs now say so). Restores the "summary first" habit. | S | docs-review 2026-10-31 |
| 2d.3 | Restructure `analysis/metabolites.md` (~770 lines): fold §g into `analysis/transport.md` (phnD / Pst examples, breadth cap, scale repeat); split ID forms / stereo / structure_kind / KEGG categories to their own page; reorder tested-absent section; drop hard-coded counts. Glutamine reading path ~24k → ~12k tok. | M | docs-review 2026-10-31 (was 2d.3 + 2d.4) |
| 2d.5 | `docs://index` read-when overrides in the generator (rows are each page's first sentence). | S | docs-review 2026-10-31 |
| 2d.6 | `tcdb_family_substrates_skipped` lists the same breadth-capped genes (MED4 ABC `tcdb:3.A.1`: PMM0449/0450/0913/0977) for every compound — scope to genes whose family carries the queried metabolite, or say "skipped regardless of metabolite". | S | docs-review 2026-10-31 |
| 2d.7 | `examples/metabolites.py --scenario n_source_de`: top hits are TCDB drug / macromolecule substrates, not N sources — restrict to a curated N-source set. | S | docs-review 2026-10-31 |
| 2d.8 | `ontology_landscape` / `genes_by_ontology` size-filter warning fires on census-style calls; consider no warning when the caller passed explicit size bounds. Brief "Result row" field order (verbose-heavy models). | S | docs-review 2026-10-31 |
| 2.14 | Outfacing-identifier lint: cross-check backtick-quoted identifiers in tools.py Field/docstrings, inputs/tools/*.yaml, hand-authored references md, CLAUDE.md against live input-schema param names + response-model field names. | S | llm-review 2b.5 |
| 2.16 | Docs-surface guards: brief-sections lint (every brief carries Example/Response sketch/mistakes/chaining-or-marker), lint_index_size, kg_claims used_in content check, TOC line-number pin test, params.py verbose text names /full. | S | llm-review 2b.4 |
| 3.13 | Registry-driven lint: for every `ONTOLOGY_CONFIG` key with non-empty `hierarchy_rels`, flag md/yaml prose calling it "flat" or saying `level=1` returns nothing (the fixed regex missed 3 yamls + 2 test comments in the TIGR absorb). | S | tigr-role-bridge 2026-08-29 |
| 3.17 | Concepts-page node counts: generate at build time (or keep them out — current policy) and add a `kg_claims.yaml` entry per number the guides still quote (organism counts, ~127k genes, ~70% tested-absent, boolean-DM counts). | S | docs review 2026-08-29 |
| 3.12 | Annotated-genes ORA background mode for `pathway_enrichment` / `cluster_enrichment` (genes with ≥1 edge in the chosen ontology; TIGR coverage bias — workaround is an explicit `background=` list). | S | tigr-role-bridge 2026-08-29 |
| 3.20 | `kg_schema` property sampling misses sparse properties (`rank_up` on 9% of `Changes_expression_of` dropped out after the 2026-10-13 rebuild). Union keys over the whole type (`db.schema.relTypeProperties`) or flag sparse ones. | S | rebuild absorb 2026-10-13 |
| E6 | KG ask (P3): TCDB `tier` wording in the `trust_axes` vocab ("Diamond-truncation depth") should match the `Gene_has_tcdb_family.tier` edge description. | KG | `docs/kg-specs/2026-10-31-docs-review-kg-asks.md` |

## 3. Larger — needs a spec / design

| # | Item | Size | Origin |
|---|---|---|---|
| 2b.6 | **Consolidation** (breaking; see 1.3). Merge `metabolites_by_quantifies_assay` + `metabolites_by_flags_assay` → `metabolites_by_assay`; merge or front the three `genes_by_*_metric`; `SKILL.md` for the skill tree and collapse CLAUDE.md's tool table; delete the research repo's duplicate python guide + fix its dangling `docs://analysis/to_dataframe` link. | L | llm-review 2026-08-29 |
| 2.8 | Organism resolver word-match leaks: "Alteromonas mediterranea AltDE" / `AltDE` matches `AltDE1` and the builders leak AltDE1 genes; genus node `Alteromonas` matches all strains. Resolver gates on `gene_count > 0`, so treatment taxa are safe. | M | slice-2 ledger + GO transport 2026-10-23 (was 2.8 + 2c.18) |
| 3.21 | Eval pass on the annotation-trust surface in `multiomics_research` (protease vs dead-homolog, urea transporter ranking, InterPro superfamily ORA on a dark-survival cluster) — only agent-driven runs show whether routing / warnings / `docs://` pages lead to the right tool. Roadmap "stress test" step. | M | was 1.3 |
| 2c.2 | Genome-coordinate listing: all genes of an organism with contig / start / end / strand / `coordinate_source`, pageable (the N-import analysis swept `gene_neighbors` + `gene_details` instead). Possibly a `gene_details` organism mode. | M | N-import analysis 2026-10-06 |
| 2c.9 | Genome context for transport substrates: per transport row `organism_catalyst_gene_count`, `organism_transporter_gene_count`, `measured_in_organism`, stereo hop folded in ("0 direct, 41 via L-Cysteine"). E.g. MED4 `dppA` lists 29 substrates; MED4 has enzymes for 7. Explorer half of KG ask D3. | L | N-import analysis 2026-10-06 |
| 3.19 | GSEA (signed-`log2fc` ranking, fgsea-style) alongside Fisher ORA in `pathway_enrichment`; needs `all_detected_genes` experiments (table_scope gate), same trust filters / TERM2GENE as ORA, a GSEA section in `docs://analysis/enrichment`. | M | upstream ticket 2026-08 #2 |
| 3.5 | `kg_schema` property-description enrichment + analysis-doc `field_description` callout. | M | metabolites roadmap Track B |

## 4. Parked — until a request or workflow drives it

| # | Item | Size | Notes |
|---|---|---|---|
| 2.15b | `compartment` as `str \| list[str]` on the 12 functions taking `compartment: str` (non-breaking later). | M | no request |
| 3.7 | MCP usability audit passes B/C/D + KG-1..KG-7. Likely mostly superseded by the readability passes, trust surface and the two docs reviews — re-scope or drop before starting. | L | audit 2026-04 |
| 3.8 | Chemistry slice 2+: `metabolites_by_pathway`, `list_reactions` / `genes_by_reaction`, `organism_metabolite_overlap`, `pathway_chemistry`. | L | chemistry design |
| 3.11 | PyPI publication (install path is the git tag today). | M | release |

## 5. KG asks pending (explorer → KG)

**A — release coordination**
- A1. On the next official KG cut: `mcp_min_version` = explorer alpha.6, and stamp `release_highlights` / `breaking_changes` (null on alpha.7). Drafts come from the alpha.6 CHANGELOG (item 1.2).

**D — from the Pro N-import coculture analysis 2026-10-06 (not filed KG-side)**
- D3. Genome-context counts for transport substrates (KG half of 2c.9).
- D7. Culture-level measurement node type (cell counts, medium NH₄⁺/NO₃⁻, N biomass, DON): organism, condition, bottle id, time, growth phase, value, unit, measured/derived, extraction method. Medium nutrients can already go in as `spent_medium` metabolite assays. Not urgent.

**E — docs review 2026-10-31** — E6 (listed in §2).

**C — notes, no action**: `expression_bin` declared but unused (drift test checks in-use ⊆ declared); `direct_gene_count` absent on PfamClan / BriteCategory (documented); 4 publications without `discusses` edges (extraction gaps); no KEGG reactions on di-/tripeptides and KO gaps on transporters (`amt1`, `focA`) — annotation limits.

## 6. Conventions this file relies on

- Absent = not applicable, null = applicable-but-empty (`docs://guide/conventions`); row-level models are `SparseRow`, union-shape rows (`GeneReactionMetaboliteTriplet`, `AssaysByMetaboliteResult`, `DiscussedByPublicationResult`) stay `BaseModel`.
- Every `(edge_or_label, prop)` the explorer filters or rolls up on has a `ControlledVocabulary` node (`-m kg` coverage test); runtime falls back to a pivot query + warning, never a hard-coded list.
- Build flow: `/add-or-update-tool` (spec freeze → worktree, `git reset --hard main` right after `EnterWorktree` → RED → GREEN ×4 file-owned agents, explicit-path staging → VERIFY: `--lint`, code review, unit, `-m kg`, regression `--force-regen` with a classified diff → finishing-a-development-branch).
