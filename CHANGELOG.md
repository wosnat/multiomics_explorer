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

**KG requirement:** this release targets KG `0.1.0-alpha.7` (the
KG-side sync that adds the organism annotation rollups, the
`ControlledVocabulary` hash, and the paper batch below). It adds a new MCP
tool (`ontology_term_details`) and changes row shapes, so the explorer
version becomes `0.1.0-alpha.5` and the KG's `mcp_min_version` must be
coordinated to `0.1.0a5` ahead of the KG release.

### Added

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
- `list_metabolites` rows: `transporter_gene_count` (distinct genes over
  deepest TCDB attachments, all organisms) — pairs with `catalyst_gene_count`
  so transport-only reads `0 / >0`.
- `list_organisms` rows and `by_metabolic_capability[]` entries:
  `transported_metabolite_count`.
- Spec: `docs/tool-specs/2026-08-20-tcdb-substrate-depth-migration.md`.

### Changed

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
  rest are positive-only. Read the filtered-slice `by_metric[*].false_count`
  — the precomputed `dm_false_count` reads 0 on current KG builds (KG ask
  R6). The earlier "returns 0 rows on every DM" statement was wrong.
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
