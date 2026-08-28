# KG-side asks: slice 4 light surface + paper batch (KG-SYNC-006)

**Date:** 2026-08-27 · **From:** explorer (`multiomics_explorer`) · **To:** KG (`multiomics_biocypher_kg`)
**Context:** synced release program (KG 0.1.0-alpha.7 + explorer 0.1.0-alpha.5), slice 4 — the last slice
before the release cut. Rides on the same rebuild as the new-paper ingestion so the explorer pays one
regen cycle, not two. Previous asks docs: `2026-08-19-presync-kg-asks.md`,
`2026-08-27-annotation-trust-kg-asks.md` (KG-SYNC-005, §9 landed).

## 1. Why this doc

Slice 4 is three small explorer surfaces. Two of them are explorer-only reads of facts the KG already
carries; one needs four precomputed organism props so `list_organisms` stays a single node scan, the way
every existing organism rollup is built (`coalesce(o.<prop>, 0)` — `reaction_count`,
`transported_metabolite_count`, `measured_metabolite_count`, `derived_metric_count`). The rest of the doc
states what the explorer expects from the paper batch so the post-rebuild regen is a diff review, not an
investigation.

Current state is taken from `config/schema_baseline.yaml` (refreshed 2026-08-27 against KG-SYNC-005) — the
graph was down for the rebuild while this was written; §5 verification queries run once it is back.

## 2. Ask summary

| ID | Ask | Pri | Kind |
|---|---|---|---|
| **ORG-001** | Four precomputed `OrganismTaxon` props — `peptidase_gene_count`, `nonpeptidase_homolog_gene_count`, `interpro_gene_count`, `ncbifam_gene_count` — distinct genes per organism, same post-import aggregation family as `Gene.merops_classes` / `Gene.ncbifam_family_count` (already computed per gene). | **P2** | graph |
| ORG-002 | Document the `Schema_info.controlled_vocabularies_hash` recipe (what is hashed, in what order, which fields, algorithm) in the KG contract doc, and state the stability guarantee: unchanged vocab set ⇒ unchanged hash across rebuilds. Explorer pins the string and compares. | P3 | doc |
| ORG-003 | Paper batch: every new `Experiment.treatment_type` / `background_factors` / `omics_type` / `growth_phase` value is in the corresponding `ControlledVocabulary` node (no values outside the closed vocab); `Publication_discusses_*` edges + `Gene.discussed_in_publication_count` / `Publication.discussed_*_count` regenerated; `Schema_info.release_highlights` / `breaking_changes` stamped on the alpha.7 cut. | P2 | graph + vocab |
| ORG-004 | Paper batch: if any paper adds an organism, it lands as an `OrganismTaxon` with `organism_type` and the taxonomy fields populated (the explorer's `list_organisms` goldens key on `preferred_name`; a genome-only organism is fine — 2 exist). Tell the explorer the count delta (47 → N). | P2 | note |

Not asks (already in the KG, explorer-side only): `Schema_info.controlled_vocabularies_hash` (present since
KG-SYNC-005 — slice-4 item 1 is a read + verdict fold-in); per-row `transport_substrate_resolution` on
transport-arm rows (reads the existing `Gene.transport_substrate_resolution`).

## 3. Per-ask detail

### ORG-001 — organism-level protease / domain-coverage rollups

**Surface it unblocks.** `list_organisms` rows gain `peptidase_gene_count`, `nonpeptidase_homolog_gene_count`,
`interpro_gene_count`, `ncbifam_gene_count`; envelope gains `top_annotation_capability` (top-10 organisms by
`peptidase_gene_count`, carries the other three as columns, excludes zero rows) — the routing question is
"which organisms are protease-rich / which have thin domain coverage" before drilling into
`genes_by_ontology(ontology='merops', organism=…, call_class=['peptidase'])`.

**Definitions (distinct genes, organism-scoped, `OrganismTaxon` ← `Gene.organism_name`):**

| prop | definition | derived from |
|---|---|---|
| `peptidase_gene_count` | genes with `'peptidase' IN g.merops_classes` | `Gene.merops_classes` |
| `nonpeptidase_homolog_gene_count` | genes with `'nonpeptidase_homolog' IN g.merops_classes` (a gene can be in both — do not subtract) | `Gene.merops_classes` |
| `interpro_gene_count` | genes with ≥1 `Gene_has_interpro_entry` edge | edge existence |
| `ncbifam_gene_count` | genes with `g.ncbifam_family_count > 0` (retired families count — they are still calls) | `Gene.ncbifam_family_count` |

Emit `0`, not absent, on organisms with no such genes (genome-only organisms included) — the explorer
reads `coalesce(o.<prop>, 0)` either way, but a dense `0` keeps `capture_annotation_state` distributions
comparable. Invariant the explorer will assert in `tests/integration/test_trust_invariants.py`:
`peptidase_gene_count` == `count(DISTINCT g)` over `(g:Gene {organism_name})` with the MEROPS predicate,
per organism; and Σ over organisms of `peptidase_gene_count` ≥ any single `MeropsFamily.peptidase_gene_count`.

**Why KG-side.** Explorer pattern-counts would add four subqueries over gene edges to a tool that is a flat
47-node scan today, and would be the only organism rollup computed differently from its siblings. The KG
already runs the per-gene aggregation (`merops_classes`, `ncbifam_family_count`); this is one more
`collect`/`count` per organism in the same post-import pass.

**If declined:** explorer falls back to pattern counts on `list_organisms` (documented as such), or defers
the rollup past the release — it is the least important of the three slice-4 items.

### ORG-002 — `controlled_vocabularies_hash` recipe

`Schema_info.controlled_vocabularies_hash` already exists. The explorer will (a) pin the hash string it was
built against in `EXPECTED_KG_SHAPE`, (b) fold a mismatch into the `kg_release_info` verdict as `warn`
("vocabulary set changed since this explorer was built — `list_filter_values` reads live, filters still
validate, but docs://ontologies pages may list stale values"). For that to be honest the explorer needs to
know:

- what is hashed — presumably the sorted set of `(applies_to, property, values, closed, sparse, …)` tuples;
  say which fields are in and which (e.g. `description`) are out;
- the algorithm and encoding (sha256 over canonical JSON? first N hex chars?);
- the guarantee: a rebuild with an unchanged vocab set yields an identical hash (no build timestamp, no
  node-id, no ordering dependence).

Doc-only ask; no graph change. If the hash covers descriptions too, say so — then doc-only vocab edits
will also trip the warn, which is acceptable but should be stated.

### ORG-003 / ORG-004 — paper batch expectations

Not new schema — the explorer's regen rule for a content-only rebuild. The explorer expects, after the
rebuild:

- `Experiment` / `Publication` / `Changes_expression_of` counts grow; `Schema_info.paper_count` /
  `experiment_count` / `expression_edge_count` move accordingly (these feed `kg_release_info`).
- Every categorical on the new experiments is inside its `ControlledVocabulary` (`treatment_type`,
  `background_factors`, `omics_type`, `growth_phase`, `table_scope`, `direction`). A new value is fine —
  it just has to be in the vocab node so `list_filter_values` and the explorer's vocab-coverage test see it.
- The `discusses` literature index is regenerated for the new papers (the explorer's `discussed_*` rollups
  are precomputed node props — stale props would silently under-count).
- If a paper brings a data type the KG does not model today (new `DerivedMetric` kind, new
  `MetaboliteAssay` shape, a new omics layer), flag it in §6 — that is a schema change and would need its
  own explorer slice after the release rather than riding on slice 4.

## 4. Audited and accepted as-is (explicit non-asks)

- `Gene.transport_substrate_resolution` — the per-row transport-arm column is a read of the existing gene
  prop; no KG change.
- `Schema_info.controlled_vocabularies_hash` — exists; only the recipe doc (ORG-002).
- `MeropsFamily.peptidase_gene_count` / `peptidase_organism_count` — term-side twins already surfaced by
  `ontology_term_details`; ORG-001 is the organism-side complement, not a replacement.

## 5. Verification queries (run after the rebuild lands on `:7687`)

```cypher
-- ORG-001: props present and dense
MATCH (o:OrganismTaxon)
RETURN count(o) AS organisms,
       count(o.peptidase_gene_count) AS has_pep, count(o.nonpeptidase_homolog_gene_count) AS has_nonpep,
       count(o.interpro_gene_count) AS has_ipr, count(o.ncbifam_gene_count) AS has_nf,
       sum(o.peptidase_gene_count) AS pep_total

-- ORG-001: invariant, per organism (should return 0 rows)
MATCH (o:OrganismTaxon)
OPTIONAL MATCH (g:Gene {organism_name: o.organism_name}) WHERE 'peptidase' IN coalesce(g.merops_classes, [])
WITH o, count(DISTINCT g) AS live WHERE live <> coalesce(o.peptidase_gene_count, 0)
RETURN o.preferred_name, live, o.peptidase_gene_count

-- ORG-002: hash present and stable across two rebuilds of the same vocab set
MATCH (s:Schema_info {id: 'schema_info'})
RETURN s.version, s.built_at, s.controlled_vocabularies_hash, s.paper_count, s.experiment_count, s.organism_count

-- ORG-003: no categorical outside its vocab (example: treatment_type)
MATCH (v:ControlledVocabulary {applies_to: 'Experiment', property: 'treatment_type'})
MATCH (e:Experiment) UNWIND e.treatment_type AS t
WITH v, collect(DISTINCT t) AS seen
RETURN [x IN seen WHERE NOT x IN v.values] AS outside_vocab

-- ORG-003: discusses index covers the new papers
MATCH (p:Publication) WHERE NOT (p)-[:Publication_discusses_gene|Publication_discusses_kegg_pathway]->()
RETURN count(p) AS pubs_without_discusses, collect(p.doi)[0..10] AS sample

-- ORG-004: organism delta
MATCH (o:OrganismTaxon) RETURN count(o) AS organisms, collect(o.preferred_name) AS names
```

## 6. KG review

**Reviewed 2026-08-27 against the live rebuild** (`built_at 2026-08-27T13:55Z`, KG `main` @ `d7252549`:
GEO processed-supplements pass + WH8109 + KG-SYNC-005 + orphan-protein fix). §5 queries were run; results
inline. Nothing below is a schema change — no new node/edge types came out of the batch.

| ID | Verdict | Notes |
|---|---|---|
| **ORG-001** | **Accept — IMPLEMENTED & live** (KG `6c51bf3b`, build `2026-08-27T14:22Z`) | Definitions accepted as written with one substitution: organism scope is the `Gene_belongs_to_organism` edge, not `Gene.organism_name` (that is how every sibling rollup — `gene_count`, `reaction_count`, `transported_metabolite_count` — is built; same result, and the invariant query in §5 should join the same way). Dense `0`. Four `ControlledVocabulary` numeric entries + a `test_organism.py` assertion ride along. Live trial on the morning build: Σ `peptidase_gene_count` = 3,439 (max 148, Alteromonas MarRef), Σ nonpeptidase 787, Σ interpro 104,764, Σ ncbifam 48,182; 0 drift vs the edge-join recount. ⚠ **Do not join on `Gene.organism_name = o.preferred_name` for the invariant** — the *treatment* organism node `Meiothermus ruber` (`ncbitaxon:`) shares its `preferred_name` with the MruberA genome strain's `Gene.organism_name`, so a name join credits 99 peptidase genes to a node with `gene_count = 0`. Join via `Gene_belongs_to_organism`, as the KG test does. |
| **ORG-002** | **Accept (doc)** | Recipe, from `multiomics_kg/utils/controlled_vocab.py::vocabularies_hash`: for every vocabulary entry build `json.dumps({id, value_type, closed, values: sorted, sparse, expected_empty, exhaustive, min_value, max_value, signal_count, signals: sorted}, sort_keys=True)`; **sort** those strings; join with `\n`; `sha256` hex over the UTF-8 bytes; stored as `"sha256:" + full 64-hex`. **Excluded:** `description`, `applies_to_kind` (`id` = `applies_to.property` already pins the target). **Guarantee:** no timestamp, node id, YAML ordering or emission ordering enters the hash — same vocab *set* ⇒ same string across rebuilds; description-only edits do **not** trip it. Live value now: `sha256:80413969…ecc2d`. Written into `docs/kg-changes/vocabulary-contract.md` (KG `6c51bf3b`). ⚠ The hash changes once with that commit (ORG-001's four entries + the `ClusteringAnalysis.cluster_type` registration below); pin the KG-SYNC-006 value: `sha256:e81df1394964ab8ac3fb74ac2831530b8b21296b347d13d28c4d6f039f43efd4` (live, `built_at 2026-08-27T14:22Z`). |
| **ORG-003** | **Verified; gaps (b) and (c) closed in KG `6c51bf3b`, (a) is a naming note** | Inside vocab (live, `outside_vocab = []`): `treatment_type` (15 values, incl. new `chemical` — Hackl 2023 mitomycin C), `background_factors` (7), `omics_type`. Gaps: **(a)** there is no `Experiment.growth_phase` — the property is `growth_phases` (str[], post-import rollup, **open** vocab by contract: live values `exponential`, `acclimated_steady_state`, `acute_stress`, `darkness`, `diel`, `[]`); `list_filter_values` must enumerate it live, as the contract already says. **(b)** `table_scope` is `""` on 35 experiments that have no DE table (metabolomics / DM-only) — an adapter default that predates the batch and sits outside the 5-value closed vocab; now **sparse** — omitted, never `""` — so read `coalesce(e.table_scope, null)`. **(c)** `ClusteringAnalysis.cluster_type` has **no** vocab node; the batch adds two values — `decay_pattern` (Steglich 2010 half-life clusters) and `genomic_island` (Hackl 2023 islands as gene sets) — on top of `time_course`, `diel`, `condition_comparison`. now registered (`ClusteringAnalysis.cluster_type`, closed, 6 values incl. `expression_bin`). Discusses index: regenerated for all six GEO-pass papers with a PDF; live totals 1,298 gene / 176 pathway edges across 45 of 49 publications. The 4 without edges are **pre-existing, not batch**: Biller 2014 (extraction returned 0 mentions), Zinser 2009 (only mention is the ncRNA `rnpB` — no Gene node), Alonso 2023 + Domínguez 2017 (never extracted). `release_highlights` / `breaking_changes` are stamped by `/release-kg` at the cut, not by the rebuild. |
| **ORG-004** | **Note** — 47 → **48** | One new `OrganismTaxon`: **`Synechococcus WH8109`** (`insdc.gcf:GCF_000161795.2`, `organism_type = genome_strain`, `genus = Synechococcus`, `species = null` — same as WH7803/CC9311, NCBI has no species rank for them; 2,707 genes; full tool coverage). Motivated by Doron 2016 (Syn9 infection, third host). `genome_strain` 40 → 41. |

**Paper batch — what else moved (for the regen diff):** publications 32 → 49 with expression edges
(`Schema_info.paper_count = 49`, `experiment_count = 209`, `expression_edge_count = 327,522`, was 244,350).
New DE: Huang 2020 (WH7803 phage), Doron 2016 (WH7803/WH8102/WH8109), Hackl 2023 (MIT0604), Johnson
2026b (MED4); he 2022 NATL1A arm grew 109 → 4,137 edges. New `DerivedMetric` **metric_types** (existing
kinds, no new shape): `rna_half_life_min`, `rna_decay_time_min`, `expression_at_t0_log2` (Steglich),
`has_primary_tss`, `antisense_tss_count`, `internal_tss_count`, `minus10_element_score`,
`tss_distance_to_cds` (Voigt). Three characterization experiments (Steglich half-lives, Voigt TSS ×2)
~~deliberately carry **no `treatment_type`** (`[]` → absent)~~ — **superseded by §7**: they now carry
`rna_decay` / `tss_mapping`, and `treatment_type` is dense + non-empty on every Experiment; they
have DM edges only. Only edge losses vs the pre-batch snapshot are 9 edges on `PMM0236` shedding
wrongly-merged placeholder IDs (B1 fix) — intended.

## 7. Post-review amendment — `treatment_type` / `background_factors` contract (KG `33772b9b` + `5d2e444c`, 2026-08-27)

Triggered by the explorer edge-case gate: `gene_clusters_by_gene` raised pydantic
`treatment_type: Input should be a valid list, input_value=None` on the Steglich decay clusters.

**Root cause (KG side, not explorer).** The adapters emitted `[]`, but `neo4j-admin import`
materializes an empty `string[]` cell as *no property*. The §6 line "`[]` → absent" described that
import artefact, not a design. Affected on the KG-SYNC-006 build: 3 `Experiment` (Steglich, Voigt ×2),
12 `ClusteringAnalysis` (Steglich decay clusters + Hackl 2023 islands ×11), 14 `DerivedMetric`, and
1 `Experiment.background_factors` (Bernstein 2017 — a labelling error, see below).

**Contract after the next rebuild (pin the explorer against this):**

| Property | Guarantee | Notes |
|---|---|---|
| `Experiment.treatment_type` | **dense, `size ≥ 1`** (`ControlledVocabulary` `min_size: 1`) | A non-empty list is the "this is a real experiment" indicator. Studies with no perturbation name *what was measured*: `rna_decay` (Steglich 2010), `tss_mapping` (Voigt 2014 ×2). |
| `Experiment.background_factors` | **dense, `size ≥ 1`** (`min_size: 1`) | An experiment always has a held-constant context. |
| `ClusteringAnalysis.treatment_type` | dense, non-empty (validator rule) | Hackl 2023 genomic islands → `genomic_analysis`. |
| `ClusteringAnalysis.background_factors` | dense; **`[]` allowed** | A `genomic_analysis` has no experimental context. |
| `DerivedMetric.*`, `MetaboliteAssay.*` (both props) | dense, copied from the parent Experiment | so `size ≥ 1` in practice |
| `Experiment.table_scope` | unchanged — **sparse** | the one property where absent = not applicable |

**Vocabulary deltas** (`Experiment.treatment_type`, closed, 15 → **19** values): `+ oxygen` (Bernstein
2017 pO₂ turbidostat steady states), `+ rna_decay`, `+ tss_mapping`, `+ genomic_analysis`. The
convention going forward: when a new paper's design fits nothing, mint a short categorical value
rather than leave `[]`. `Experiment.background_factors` unchanged (7). New optional
`ControlledVocabulary` property **`min_size`** (int, string_array vocabs only) — `list_filter_values`
/ schema baseline may surface it. `Schema_info.controlled_vocabularies_hash` changes — the ORG-002
pinned value is superseded; the rebuilt graph (KG `16e8a8bf`, `built_at 2026-08-27T17:19Z`, KG validity
1,195 pass) carries **`sha256:496c5ad45b58829df2ab580415be09e001219772bb0a36005a0f05a2da2c7429`**.

**Data correction — Bernstein 2017 (`10.1128/mSystems.00181-16`).** Was `treatment_type:
[coculture, light]`, `background_factors: []` on the experiment and `[coculture]` / `[]` on all four
clustering analyses. Only binary-coculture samples are wired into the KG (3 irradiance × 3 pO₂), so
now: experiment `[light, oxygen]` / `[coculture]`; light clusters `[light]` / `[coculture]`; oxygen
clusters `[oxygen]` / `[coculture, light]`. `Tests_coculture_with` is unaffected (gated on
`treatment_organism`). Any explorer test pinned to the old Bernstein labels needs updating.

**Explorer actions.**
1. Withdraw the pending slice-4 coalesce amendment (`coalesce(e.treatment_type, [])` at ~7 sites) — not needed; pydantic `list[str]` is correct as-is.
2. Add `oxygen`, `rna_decay`, `tss_mapping`, `genomic_analysis` to any hard-coded treatment-type enum, or read `ControlledVocabulary {applies_to:'Experiment', property:'treatment_type'}`.
3. Edge-case gate: assert `treatment_type == ['rna_decay']` on the Steglich analysis (not `[]`).
4. Optional: a "characterization" facet in `list_experiments` can be derived as `treatment_type ⊆ {rna_decay, tss_mapping, genomic_analysis}` — no KG-side flag is planned.

**Verification (after rebuild):**
```cypher
MATCH (e:Experiment)
RETURN count(e) = count(e.treatment_type) AS dense_tt,
       count(e) = count(e.background_factors) AS dense_bf,
       sum(CASE WHEN size(e.treatment_type) = 0 OR size(e.background_factors) = 0 THEN 1 ELSE 0 END) AS empty;
-- expect true / true / 0
MATCH (n) WHERE n:ClusteringAnalysis OR n:DerivedMetric OR n:MetaboliteAssay
RETURN labels(n)[0] AS l, count(n) AS total, count(n.treatment_type) AS tt, count(n.background_factors) AS bf;
-- expect tt = bf = total per label
```
KG docs: `docs/kg-changes/experiment-list-props-dense.md`, CHANGELOG `### Fixed` + `### Data`.

## Status

- [x] Asks reviewed (KG side) — 2026-08-27, see §6
- [x] KG-SYNC-006 rebuilt (papers + ORG-001) on `:7687` — KG `6c51bf3b`, `built_at 2026-08-27T14:22Z`
- [x] §5 verification queries pass — ORG-001 dense on 48/48 (Σ peptidase 3,439), table_scope `""` count 0 (192/209 carry one), cluster_type outside-vocab `[]`, treatment_type/background_factors/omics_type outside-vocab `[]`; KG validity 1,189 pass
- [ ] Explorer `schema_baseline.yaml` refreshed; slice-4 tool spec written against the live build
- [x] KG `16e8a8bf` rebuilt on `:7687` (`built_at 2026-08-27T17:19Z`), §7 verification queries pass, KG validity 1,195 pass
- [ ] §7 amendment picked up ( coalesce amendment withdrawn; 4 new treatment_type values; Steglich gate → `['rna_decay']`; re-pin vocab hash)
