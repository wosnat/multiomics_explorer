# Tool spec: slice 4 — light surface + paper-batch absorption (Mode B)

**Status:** v1 — §7 live-verified 2026-08-27 against KG-SYNC-006 (`built_at 2026-08-27T15:41Z`, 127,458 genes, 48 organisms, 209 experiments, 49 papers; hash matches the pin). **FROZEN 2026-08-27** (user approval via /add-or-update-tool; `min_peptidase_gene_count` dropped before freeze). **Amendment v1.1 (§3.4 treatment_type null-safety) pending re-approval.**
**KG:** KG-SYNC-006 (`6c51bf3b`, `built_at 2026-08-27T14:22Z`) — asks + review in `docs/kg-specs/2026-08-27-slice4-kg-asks.md` (§6).
**Tools touched:** `kg_release_info`, `genes_by_metabolite`, `metabolites_by_gene`, `list_organisms`, `list_filter_values`, `list_clustering_analyses` / `gene_clusters_by_gene` (description only). Mode B: one-page spec, no KG iteration.

## 1. Purpose

Close the synced-release program before the alpha.5 / alpha.7 cut: (1) let the explorer detect a vocabulary-set drift against the KG it was built for; (2) put the gene-level `transport_substrate_resolution` on the transport-arm detail rows it already qualifies (today only on `top_genes[]` / `by_gene[]` and `gene_overview`); (3) organism-level protease / domain-coverage rollups on `list_organisms` (ORG-001, live); (4) absorb the paper batch (48 organisms, sparse `table_scope`, new `cluster_type` values, treatment-less characterization experiments) so goldens and constants match the shipped data.

## 2. Out of scope

New tools; changes to the trust surface (slice 3); spec §15 follow-ups from 3b (organism_gene_count subtree alignment, rebind tie-break, dead `router_ambiguous` Cypher column, `links_out[].props` null, index truncation); the `organism=` word-match backlog (`Alteromonas` genus / `AltDE` prefix).

## 3. Items

### 3.1 `kg_release_info` — vocabulary-set check (explorer-only)

- `EXPECTED_KG_SHAPE` gains `"controlled_vocabularies_hash": "sha256:e81df1394964ab8ac3fb74ac2831530b8b21296b347d13d28c4d6f039f43efd4"` (the KG-SYNC-006 value; recipe in KG `docs/kg-changes/vocabulary-contract.md`: sorted canonical-JSON of `{id, value_type, closed, values, sparse, expected_empty, exhaustive, min_value, max_value, signal_count, signals}` per vocab entry, `\n`-joined, sha256 hex, `"sha256:"` prefix; `description` excluded ⇒ doc-only vocab edits do not trip it).
- New assert bucket **6 — vocabulary set**: `{check: "controlled_vocabularies_hash", passed, expected, actual, detail}`. `passed` iff `schema_info.controlled_vocabularies_hash == expected`. Absent prop (pre-SYNC-005 KG) → `passed=False`, detail "KG predates the vocabulary contract".
- Verdict fold-in: a failed bucket 6 yields `warn` (never worse). Summary sentence: "Vocabulary set differs from the one this explorer was built against — filters still validate live and `list_filter_values` reads live, but docs://ontologies pages and Field descriptions may list stale values."
- `kg` envelope surfaces `controlled_vocabularies_hash` (already passed through via `s{.*}`; confirm it is not stripped by the projection at `api/functions.py:8584`).
- Release-time rule (goes into `release-explorer` preflight, doc only here): the pinned hash must equal the live KG's at cut time.

### 3.2 Per-row `transport_substrate_resolution` on transport-arm rows

- `GeneReactionMetaboliteTriplet` (shared by `genes_by_metabolite` + `metabolites_by_gene`) gains `transport_substrate_resolution: Literal["resolved","family_inferred"] | None` — compact, right after `tcdb_evidence_score`. Populated from `g.transport_substrate_resolution` on `evidence_source='transport'` rows; explicit `None` on metabolism rows (union-shape padding, Phase 3 Item 6.1 rule — this model is deliberately not `SparseRow`).
- Detail builders (`build_genes_by_metabolite_detail`, `build_metabolites_by_gene_detail`) add `g.transport_substrate_resolution AS transport_substrate_resolution` to the transport arm and `null AS transport_substrate_resolution` to the metabolism arm of the `UNION ALL`. Summary builders already collect it (queries_lib ~8791 / ~9394) — unchanged.
- Envelope: no new rollup (the `by_gene[]` / `top_genes[]` carriers stay authoritative); the existing `family_inferred` auto-warning is unchanged.
- Docs: `docs://analysis/metabolites` + both tool yamls: "row-level `transport_substrate_resolution` is the GENE's resolution (KG-authoritative), repeated on every transport row of that gene — it is not a per-substrate fact; use `substrate_depth` for the row".

### 3.3 `list_organisms` — annotation-capability rollups (ORG-001)

- Row columns (compact, after `measured_metabolite_count`): `peptidase_gene_count`, `nonpeptidase_homolog_gene_count`, `interpro_gene_count`, `ncbifam_gene_count` — `coalesce(o.<prop>, 0)`, same form as the chemistry rollups. Verbose unchanged.
- Envelope `by_annotation_capability`: top-10 organisms (within the matched set) by `peptidase_gene_count` desc, then `preferred_name`; carries all four columns; excludes rows with all four = 0. Mirrors `by_metabolic_capability` (api-side over matched rows in detail mode; summary builder in summary mode).
- No new filter (decided 2026-08-27): `list_organisms` returns 48 rows; agents read the `by_annotation_capability` ranking instead of selecting. Coverage counts are for reading, not selecting.
- Invariant test (`-m kg`, `test_trust_invariants.py`): per organism, `peptidase_gene_count` == `count(DISTINCT g)` over `(o)<-[:Gene_belongs_to_organism]-(g:Gene)` with `'peptidase' IN coalesce(g.merops_classes, [])`. **Join by edge, never by name** — the treatment-organism node `Meiothermus ruber` shares its `preferred_name` with the MruberA strain (KG review ORG-001).

### 3.4 Paper-batch absorption (no new params)

| what moved (KG review §6) | explorer change |
|---|---|
| organisms 47 → 48 (`Synechococcus WH8109`, genome_strain 41); papers 49; experiments 209; expression edges 327,522 | `schema_baseline.yaml` refresh; hard-coded counts in tests (search `47`, `45`, `41` organism / `32` paper pins); regen goldens for `list_organisms`, `list_publications`, `list_experiments`, `kg_release_info`, DE/enrichment cases touching the grown NATL1A / MED4 arms; `discussed_*` goldens (1,298 gene / 176 pathway edges). |
| `Experiment.table_scope` now sparse (absent, never `""`) on the 35 no-DE experiments | `e.table_scope IN $table_scopes` is already null-safe; `by_table_scope` loses the `""` bucket (goldens); `list_experiments` yaml + `docs://guide/conventions` note "absent = experiment has no DE table". |
| `ClusteringAnalysis.cluster_type` vocab node (closed, 6 values: + `decay_pattern`, `genomic_island`, `expression_bin`) | `VALID_CLUSTER_TYPES` is description-only (no validation) — switch the two Field descriptions to read the vocab via `list_filter_values`, and add `filter_type='cluster_type'` to `list_filter_values` (from `ControlledVocabulary`, pivot fallback per the slice-3 rule). Keep the constant as the offline fallback, updated to 6 values. |
| `growth_phases` (`str[]`, OPEN vocab) | already enumerated live (`build_list_growth_phases`); doc note that it is open. |
| 3 characterization experiments carry no `treatment_type` (absent) — **BREAKS `gene_clusters_by_gene` today** (`GeneClustersByGeneResult.treatment_type: list[str]` gets `None` → pydantic ValidationError → ToolError; found by the edge-case gate on KG-SYNC-006, amendment 2026-08-27) | Null-safe every row projection, KG-convention style: `coalesce(e.treatment_type, []) AS treatment_type` / `coalesce(ca.treatment_type, [])` at the seven builder sites (`queries_lib.py` ~2149, 3578, 3800, 4296, 4371, 5054, 5238 — list_experiments, DE rows, clustering analyses, gene_clusters_by_gene, genes_in_cluster) plus any api-side `row["treatment_type"]` reads; row models stay `list[str]` (empty list = characterization experiment, same as `background_factors`). Filter path is already null-safe (`ANY(t IN e.treatment_type …)` on null is falsy — filtered calls exclude them, unfiltered include them). `by_treatment_type` rollups must tolerate `[]`. Edge-case scenario: Steglich half-life analysis via `gene_clusters_by_gene` / `list_clustering_analyses` returns `treatment_type: []`. Yaml + conventions note: "`treatment_type: []` = characterization, not perturbation". |
| new `DerivedMetric` metric_types (`rna_half_life_min`, `rna_decay_time_min`, `expression_at_t0_log2`, `has_primary_tss`, `antisense_tss_count`, `internal_tss_count`, `minus10_element_score`, `tss_distance_to_cds`) | discovery-only (`list_derived_metrics`); no code change; DM goldens regen. |
| `treatment_type` gains `chemical` | vocab-driven already; goldens. |
| `PMM0236` sheds 9 wrongly-merged placeholder IDs | if any golden pinned them, the diff is expected. |

## 4. Result-size controls

Unchanged on every tool. `list_organisms` stays "always small" (48 rows, `verbose` for column control).

## 5. Parameters

| tool | new params |
|---|---|
| `list_organisms` | none — new columns + envelope key only |
| `list_filter_values` | `filter_type` += `cluster_type` |
| everything else | none — new columns / envelope keys only |

## 6. Row / envelope contracts

- `kg_release_info.asserts[]` += bucket 6 (shape above); `kg.controlled_vocabularies_hash` present.
- `GeneReactionMetaboliteTriplet` += `transport_substrate_resolution` (None-padded on metabolism rows).
- `ListOrganismsResult` += the four counts; `ListOrganismsResponse` += `by_annotation_capability[]` (`{preferred_name, organism_name, peptidase_gene_count, nonpeptidase_homolog_gene_count, interpro_gene_count, ncbifam_gene_count}`).
- `list_filter_values(filter_type='cluster_type')` rows: `{value, applies_to: ['ClusteringAnalysis'], description, source: 'vocabulary' | 'pivot'}`.

## 7. Cypher (verified live 2026-08-27 — every expected value below reproduced exactly)

```cypher
-- 7.1 list_organisms rollups (append to the existing RETURN)
       coalesce(o.peptidase_gene_count, 0) AS peptidase_gene_count,
       coalesce(o.nonpeptidase_homolog_gene_count, 0) AS nonpeptidase_homolog_gene_count,
       coalesce(o.interpro_gene_count, 0) AS interpro_gene_count,
       coalesce(o.ncbifam_gene_count, 0) AS ncbifam_gene_count
-- verified: Σ peptidase 3,439 (max 148, Alteromonas MarRef), Σ nonpeptidase 787, Σ interpro 104,764, Σ ncbifam 48,182; dense on 48/48

-- 7.2 invariant (0 rows expected)
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (o)<-[:Gene_belongs_to_organism]-(g:Gene) WHERE 'peptidase' IN coalesce(g.merops_classes, [])
WITH o, count(DISTINCT g) AS live WHERE live <> coalesce(o.peptidase_gene_count, 0)
RETURN o.preferred_name, live, o.peptidase_gene_count

-- 7.3 transport-arm detail row (fragment inside the existing transport UNION branch)
       g.transport_substrate_resolution AS transport_substrate_resolution,
-- metabolism branch: null AS transport_substrate_resolution
-- check: PMM0392 transport rows all read 'resolved'; an ABC-superfamily-only MED4 gene reads 'family_inferred'

-- 7.4 vocab read for cluster_type
MATCH (v:ControlledVocabulary {applies_to: 'ClusteringAnalysis', property: 'cluster_type'})
RETURN v.values AS values, v.description AS description, v.closed AS closed
-- verified: ['time_course','diel','condition_comparison','expression_bin','decay_pattern','genomic_island'], closed

-- 7.5 release identity
MATCH (s:Schema_info {id: 'schema_info'})
RETURN s.version, s.built_at, s.controlled_vocabularies_hash, s.paper_count, s.experiment_count, s.organism_count
-- expected hash sha256:e81df139…43efd4, paper_count 49, experiment_count 209, organism_count 48

-- 7.6 table_scope sparsity + treatment-less experiments
MATCH (e:Experiment) RETURN count(e) AS n, count(e.table_scope) AS with_scope, sum(CASE WHEN e.table_scope = '' THEN 1 ELSE 0 END) AS empty_string, sum(CASE WHEN e.treatment_type IS NULL THEN 1 ELSE 0 END) AS no_treatment
-- verified: 209 / 192 / 0 / 3
```

## 8. Tests, docs, build order

- RED: unit for the 3 builders/api/wrappers + `EXPECTED_KG_SHAPE` bucket 6 (mock hash match / mismatch / absent → ok / warn / warn), `list_filter_values('cluster_type')` vocab + pivot paths; integration `-m kg`: 7.2 invariant, 7.5 identity (hash equality with the pin — this test IS the release-time guard), 7.6 sparsity; edge-case scenarios: organism with all-zero rollups excluded from `by_annotation_capability`; `organism_names=` subset with zero peptidase genes → empty `by_annotation_capability`.
- Regression: `--force-regen` — expect the §3.4 diffs and nothing else; every other diff is a concern.
- Docs: yamls for the 5 touched tools, `analysis/metabolites.md` (§3.2 note), `guide/conventions.md` (sparse `table_scope`, open `growth_phases`, vocab-hash warn), `CLAUDE.md` rows, `examples/annotation_evidence.py` gains an organism-rollup scenario.
- Order: KG up → `schema_baseline` refresh → §7 verified → freeze → worktree (`EnterWorktree` then `git reset --hard main`) → RED → GREEN (4 agents, explicit-path staging) → VERIFY → merge → `/release-explorer 0.1.0-alpha.5`.

## 9. Acceptance

1. `kg_release_info()` on KG-SYNC-006 → `verdict: ok`, bucket 6 passed; with the pin altered → `warn` naming the hash.
2. `genes_by_metabolite(metabolite_ids=['<urea>'], organism='MED4')` transport rows carry `transport_substrate_resolution`; metabolism rows carry `None`.
3. `list_organisms()` → 48 rows, `by_annotation_capability[0]` = Alteromonas MarRef with `peptidase_gene_count=148`; `list_organisms(organism_names=['Prochlorococcus MED4'])` → `by_annotation_capability` has exactly MED4.
4. `list_filter_values(filter_type='cluster_type')` → 6 values, `source='vocabulary'`.
5. Regression regen diff matches §3.4 only.

## 10. Live-verification notes (2026-08-27)

- `Schema_info.version` reads `0.0.0-dev` / `git_sha_short = unknown` on this dev build — expected; the alpha.7 cut stamps them. `mcp_min_version = 0.1.0a1`.
- Top of `by_annotation_capability` will be `Alteromonas (MarRef v6)` (148 / 31 / 3746 / 1379), then AD45 129, Shewanella W3-18-1 128, BGP6 127, ATCC27126 125.
- Two `OrganismTaxon` nodes share `preferred_name = 'Meiothermus ruber'`: the genome strain (`insdc.gcf:GCF_000836395.1`, 2,884 genes, peptidase 99) and the treatment taxon (`ncbitaxon:1299`, 0 genes). `build_resolve_organism_for_organism` already gates on `gene_count > 0`, so `organism='ruber'` resolves to the strain; any new organism-count Cypher must join through `Gene_belongs_to_organism` (§3.3).
- `list_organisms` will return both nodes unless it already filters treatment taxa — verify in RED (the existing golden shows the current behaviour).
