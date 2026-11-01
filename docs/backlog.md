# Explorer backlog

Single list of open work for `multiomics_explorer`. One line per item: what, why, size, origin.
Status was verified against `main` on 2026-10-31 (live KG dev build 2026-10-31T19:34Z; `main` = `origin/main`). When an item ships, delete it
here and let the CHANGELOG carry the record — this file is only ever the *open* set.

Sizes: **S** ≤ half a day, no spec · **M** a day, one-page spec (Mode B) · **L** multi-day, full
`/add-or-update-tool` cycle · **KG** needs a KG-side change first.

## 1. Now

| # | Item | Size | Notes |
|---|---|---|---|
| 1.2 | KG release notes never reach `Schema_info` (compose files don't forward `KG_RELEASE_HIGHLIGHTS` / `KG_RELEASE_BREAKING` / `KG_RELEASE_NOTES_URL`); alpha.7 and alpha.8 shipped with null highlights / breaking. Ask R1 in `docs/kg-specs/2026-11-01-kg-release-notes-not-stamped-asks.md`; after the KG fix, check `kg_release_info` shows both on alpha.8. | KG | R1 |
| 1.3 | Decide when the 2b.6 consolidation ships (kept out of alpha.6). | — | decision |

## 2. Next — small, concrete

Empty.

## 3. Larger — needs a spec / design

| # | Item | Size | Origin |
|---|---|---|---|
| 2d.3 | Restructure `analysis/metabolites.md` (~770 lines): fold §g into `analysis/transport.md` (phnD / Pst examples, breadth cap, scale repeat); split ID forms / stereo / structure_kind / KEGG categories to their own page; reorder tested-absent section; drop hard-coded counts. Glutamine reading path ~24k → ~12k tok. | M | docs-review 2026-10-31 (was 2d.3 + 2d.4) |
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
- A1. On the next official KG cut: `mcp_min_version` = explorer alpha.6, and stamp `release_highlights` / `release_breaking` (null on alpha.7). Drafts come from the alpha.6 CHANGELOG (item 1.2).

**D — from the Pro N-import coculture analysis 2026-10-06 (not filed KG-side)**
- D3. Genome-context counts for transport substrates (KG half of 2c.9).
- D7. Culture-level measurement node type (cell counts, medium NH₄⁺/NO₃⁻, N biomass, DON): organism, condition, bottle id, time, growth phase, value, unit, measured/derived, extraction method. Medium nutrients can already go in as `spent_medium` metabolite assays. Not urgent.

**C — notes, no action**: `expression_bin` declared but unused (drift test checks in-use ⊆ declared); `direct_gene_count` absent on PfamClan / BriteCategory (documented); 4 publications without `discusses` edges (extraction gaps); no KEGG reactions on di-/tripeptides and KO gaps on transporters (`amt1`, `focA`) — annotation limits.

## 6. Conventions this file relies on

- Absent = not applicable, null = applicable-but-empty (`docs://guide/conventions`); row-level models are `SparseRow`, union-shape rows (`GeneReactionMetaboliteTriplet`, `AssaysByMetaboliteResult`, `DiscussedByPublicationResult`) stay `BaseModel`.
- Every `(edge_or_label, prop)` the explorer filters or rolls up on has a `ControlledVocabulary` node (`-m kg` coverage test); runtime falls back to a pivot query + warning, never a hard-coded list.
- Build flow: `/add-or-update-tool` (spec freeze → worktree, `git reset --hard main` right after `EnterWorktree` → RED → GREEN ×4 file-owned agents, explicit-path staging → VERIFY: `--lint`, code review, unit, `-m kg`, regression `--force-regen` with a classified diff → finishing-a-development-branch).
