# Explorer backlog

Single list of open work for `multiomics_explorer`. One line per item: what, why, size, origin.
Status was verified against `main` on 2026-11-11 (explorer `0.1.0-alpha.6`, live KG `0.1.0-alpha.9`, checked via MCP). When an item ships, delete it
here and let the CHANGELOG carry the record — this file is only ever the *open* set.

Sizes: **S** ≤ half a day, no spec · **M** a day, one-page spec (Mode B) · **L** multi-day, full
`/add-or-update-tool` cycle · **KG** needs a KG-side change first.

## 1. Now

Empty.

## 2. Next — small, concrete

Empty.

## 3. Larger — needs a spec / design

| # | Item | Size | Origin |
|---|---|---|---|
| 2b.6 | **Consolidation** (breaking; timing parked as 1.3). Merge `metabolites_by_quantifies_assay` + `metabolites_by_flags_assay` → `metabolites_by_assay`; merge or front the three `genes_by_*_metric`; `SKILL.md` for the skill tree and collapse CLAUDE.md's tool table; delete the research repo's duplicate python guide + fix its dangling `docs://analysis/to_dataframe` link. | L | llm-review 2026-08-29 |
| 2.8 | Organism resolver word-match leaks: "Alteromonas mediterranea AltDE" / `AltDE` matches `AltDE1` and the builders leak AltDE1 genes; genus node `Alteromonas` matches all strains. Resolver gates on `gene_count > 0`, so treatment taxa are safe. | M | slice-2 ledger + GO transport 2026-10-23 (was 2.8 + 2c.18) |
| 3.21 | Eval pass on the annotation-trust surface in `multiomics_research` (protease vs dead-homolog, urea transporter ranking, InterPro superfamily ORA on a dark-survival cluster) — only agent-driven runs show whether routing / warnings / `docs://` pages lead to the right tool. Roadmap "stress test" step. | M | was 1.3 |
| 2c.2 | Genome-coordinate listing: all genes of an organism with contig / start / end / strand / `coordinate_source`, pageable (the N-import analysis swept `gene_neighbors` + `gene_details` instead). Possibly a `gene_details` organism mode. | M | N-import analysis 2026-10-06 |
| 2c.9 | Genome context for transport substrates: per transport row `organism_catalyst_gene_count`, `organism_transporter_gene_count`, `measured_in_organism`, stereo hop folded in ("0 direct, 41 via L-Cysteine"). E.g. MED4 `dppA` lists 29 substrates; MED4 has enzymes for 7. Explorer half of KG ask D3. | L | N-import analysis 2026-10-06 |
| 3.19 | GSEA (signed-`log2fc` ranking, fgsea-style) alongside Fisher ORA in `pathway_enrichment`; needs `all_detected_genes` experiments (table_scope gate), same trust filters / TERM2GENE as ORA, a GSEA section in `docs://analysis/enrichment`. | M | upstream ticket 2026-08 #2 |
| 2d.3 | `genes_by_function`: per-row `matched_fields` (which of `gene_name_synonyms` / `all_identifiers` / `alternate_functional_descriptions` / `gene_summary` the text hit) + `by_matched_field` rollup; attributed post-hoc, since `geneFullText` scores fields together. "By name vs by product" counts need Cypher today. | M | spock hli_light_stress 2026-11-16 |
| 2d.4 | `genes_by_ontology` across organisms (`organism: str` is required today): "which strains carry InterPro X" over 100 strains means a loop or Cypher. Either `organism: str \| list[str] \| None` or a cross-organism presence mode (term × organism counts). | M | spock hli_light_stress 2026-11-16 |
| 2d.7b | `genes_by_metabolite` across organisms ("which strains make / transport X"). Not a gate relaxation: ATP alone reaches 16,145 genes in 118 organisms through the metabolism arm, and the organism-wide counts, stereo hint and `not_matched` all need per-organism forms. Design first, likely a per-organism summary mode before any row mode. The locus-tag half (2d.7a) shipped; keep the gates on `pathway_enrichment` / `cluster_enrichment` / `ontology_landscape` (per-genome background) and on `differential_expression_by_gene` / `gene_response_profile` (`differential_expression_by_ortholog` covers cross-organism). See 2d.4 for `genes_by_ontology`. | L | organism-gate audit 2026-11-18 |
| 2d.5 | DE-table QC (`de_table_qc` tool or `analysis/` utility): per experiment, target-gene presence count, sign fraction, repeated identical log2FC values, large \|FC\| called ns, `table_scope` / filtered-subset flags. Hand-rolled 3× in one analysis; a filtered 34-gene P table and a coculture table with 82% negative FC were caught only late. | M | spock hli_light_stress 2026-11-16 |
| 2d.6 | Gene × contrast call matrix (`analysis/` utility): up / ns / down / undefined per gene × time point using `table_scope` semantics (significant-only absence → ns; up-only → undefined for non-up; filtered subset → undefined outside the filter). Include identical-paralog (shared-probe) detection: identical log2FC pairs on arrays → unlisted twin undefined in significant-only array tables; RNA-seq untouched. | L | spock hli_light_stress 2026-11-16 |
| 3.5 | `kg_schema` property-description enrichment + analysis-doc `field_description` callout. | M | metabolites roadmap Track B |

## 4. Parked — until a request or workflow drives it

| # | Item | Size | Notes |
|---|---|---|---|
| 1.3 | Decide when the 2b.6 consolidation ships (breaking; kept out of alpha.6). Deferred 2026-11-11. | — | decision |
| 2.15b | `compartment` as `str \| list[str]` on the 12 functions taking `compartment: str` (non-breaking later). | M | no request |
| 3.8 | Chemistry slice 2+: `metabolites_by_pathway`, `list_reactions` / `genes_by_reaction`, `organism_metabolite_overlap`, `pathway_chemistry`. | L | chemistry design |
| 3.11 | PyPI publication (install path is the git tag today). | M | release |

## 5. KG asks pending (explorer → KG)

**D — from the Pro N-import coculture analysis 2026-10-06 (not filed KG-side)**
- D3. Genome-context counts for transport substrates (KG half of 2c.9).
- D7. Culture-level measurement node type (cell counts, medium NH₄⁺/NO₃⁻, N biomass, DON): organism, condition, bottle id, time, growth phase, value, unit, measured/derived, extraction method. Medium nutrients can already go in as `spent_medium` metabolite assays. Not urgent.

**E — from the spock analyses 2026-11-03..16 (not filed KG-side)**
- E1. Data defects: Steglich 2006 (10.1128/JB.01097-06) title contains "/H17188"; Zinser 2009 diel (10.1371/journal.pone.0005135) has 0 expression rows and Mfuzz cluster sizes sum to 1697 vs `total_gene_count` 1756, with mixed time origins in phase text; Pandhal 2007 iTRAQ holds 6 significant proteins vs ~15 in the table description.
- E2. Coculture 2025 `growth_phase` per time point describes the coculture arm only; the axenic control's state lives in `design_notes` free text.
- E3. `discusses` edges spread one sentence over more genes than it names (Tolonen 2006 "three hli genes" → 18 genes; Bagby 2015 "six" → 13).
- E4. hli annotation: PMM0815/PMM1396 lack protein_id + seed ortholog; Pfam PF31213 has no name; MED4 hli names (`hli`, `hli6`, `hli15`) don't follow paper numbering.
- E5. Genomics survey: no KEGG modules; no assembly-completeness field on OrganismTaxon (`reference_database` null for all Prochlorococcus); 46/110 KEGG-valid KOs in one catalogue have no KG node (KO nodes exist only when a gene carries them).

**C — notes, no action**: `expression_bin` declared but unused (drift test checks in-use ⊆ declared); `direct_gene_count` absent on PfamClan / BriteCategory (documented); 4 publications without `discusses` edges (extraction gaps); no KEGG reactions on di-/tripeptides and KO gaps on transporters (`amt1`, `focA`) — annotation limits.

## 6. Conventions this file relies on

- Absent = not applicable, null = applicable-but-empty (`docs://guide/conventions`); row-level models are `SparseRow`, union-shape rows (`GeneReactionMetaboliteTriplet`, `AssaysByMetaboliteResult`, `DiscussedByPublicationResult`) stay `BaseModel`.
- Every `(edge_or_label, prop)` the explorer filters or rolls up on has a `ControlledVocabulary` node (`-m kg` coverage test); runtime falls back to a pivot query + warning, never a hard-coded list.
- Build flow: `/add-or-update-tool` (spec freeze → worktree, `git reset --hard main` right after `EnterWorktree` → RED → GREEN ×4 file-owned agents, explicit-path staging → VERIFY: `--lint`, code review, unit, `-m kg`, regression `--force-regen` with a classified diff → finishing-a-development-branch).
