# Tool spec: TCDB cleanup surface (KG project 3a)

Mode B (cross-tool). Target KG build: the rebuild of KG branch `feat/post-3a-fixes`, which is 3a
plus the follow-up fixes. It was green-lit 2026-10-24 and is not built yet. The numbers in this spec
were measured on 3a build `2026-10-23T17:57:48.913Z`, and the 34 checks are re-run on the target
build. The KG change note is `multiomics_biocypher_kg/docs/kg-changes/tcdb-cleanup.md`. The design dialog is
`docs/kg-specs/2026-10-23-tcdb-cleanup-explorer-asks.md`.

## Purpose

The KG rebuilt the TCDB slice, and it is a breaking change:
- **Nodes:** the hierarchy now has 5 levels, ending in `tc_system`.
- **Substrates:** substrate edges leave `tc_system` nodes only.
- **Gene edges:** each source has its own `Gene_has_tcdb_family` edge (`tcdb_call`), stamped with
  an ordered `tcdb_gate` ∈ {`direct`, `annotated`, `below_gate`}.
- **Removed:** every scored or rolled-up TCDB property.

The explorer still reads the removed properties. Neo4j returns null for them, so there is no error;
the tools just return silently wrong results:
- TCDB leaf mode in `gene_ontology_terms` returns 0 rows.
- Transport rows include `below_gate` edges that the KG counts exclude.
- `substrate_depth`, `tcdb_evidence_score` and `transport_substrate_resolution` read null.

This spec makes every TCDB surface read the gate, so rows and the KG's precomputed counts come from
one edge set. It adds the one capability the KG dropped, the opt-in family substrate walk. It finishes
with a full absorb of the rebuild.

## Out of scope

- A per-gene transporter call, confidence, subunit role or per-gene direction. That is KG 3b.
- Transport systems. That is the systems project.
- A `direction` filter param on any tool. It is exposed as a column only; a filter can follow if
  people ask for one.
- The GO transport route (slice 1). It is unchanged. Only its shared row and envelope shapes follow
  the renames below.
- Anything about MEROPS. It shares field names (`confidence_score`, `pfam_support`, `consensus_n`,
  `identity`, `qcov`, `evalue`), which stay; only the TCDB-scoped prose about them changes.

## KG dependencies (verified against live KG)

- **`Gene_has_tcdb_family` edges.** Every edge has `tcdb_call` and `tcdb_gate`; both are dense.
  - Optional properties: `tier` (null on eggNOG), `identity`, `qcov`, `scov`, `evalue` (diamond);
    `rank`, `bitscore`, `bitscore_ratio` (best hit).
  - Units: `qcov` / `scov` / `identity` are percent.
- **`TcdbFamily` nodes.** Levels 0–4 map onto `tc_class` … `tc_system`.
  - Properties: `direction` (dense), `direction_basis` (sparse), `tcdb_substrate_count` (dense, all
    levels).
  - `gene_count` / `direct_gene_count` count gate-passing edges.
  - `superfamily` is sparse and stays.
- **Substrate edges.** `Tcdb_family_transports_metabolite` and `…_chemical_role` start from
  `tc_system` only and carry no `substrate_depth`.
- **Live-KG checks behind this spec:**
  - 34 invariant checks, all clean (asks doc, "post-rebuild check").
  - Gated leaf mode vs `Gene.tcdb_assignment_count`: 0 mismatches.
  - Gated TERM2GENE vs `TcdbFamily.gene_count`: 0 mismatches.

## Shared rules (all TCDB surfaces)

**G1. Gate.** Every gene → TCDB traversal is gated by default:
- **Annotation and ontology traversals** filter `r.tcdb_gate IN ['direct','annotated']`.
- **Transport-arm traversals** filter `r.tcdb_gate = 'direct'`. The one exception is the opt-in
  family walk, which starts from `annotated` edges (see the family walk below).
- **Counts the explorer computes live from edges are gated too:** `organism_gene_count` in
  `search_ontology` / `ontology_term_details`, `ontology_landscape` term sizes and coverage, and the
  transport-arm envelope counts. Only KG precomputes (`gene_count`, `tcdb_assignment_count`, …)
  arrive already gated.
- **Never re-derive the gate** from `tcdb_call`, `tier` or `rank`. The KG note says not to.

**G2. One row per (gene, node).** A (gene, node) pair can carry up to three edges: 2,446
gate-passing pairs carry two. Rows stay one per (gene, node), and the edge they report is chosen by
precedence:
1. `tcdb_call`: `diamond_best_hit` (rank 1), then `diamond_tier`, then `eggnog`;
2. then `identity` DESC.

Each row also carries **`tcdb_calls: list[str]`**: the call kinds on the gene's edges to the row's
node, **its ancestors or its descendants**, i.e. anywhere on the row's lineage, in precedence order.
This one rule covers every mode:
- **Leaf rows:** a leaf row has no gated descendant by definition, so in practice this is the node
  plus its ancestors.
- **Rollup and TERM2GENE rows:** the descendant calls are the ones that place the gene in the term.

Only gate-passing edges count. The one exception is the rows
that `include_weak_tcdb_hits` adds (G4): on those, `below_gate` calls count too. Default rows never
change.
- **Why ancestors count:** a call on an ancestor agrees with a call on the node itself. Leaf mode
  drops the ancestor rows, so without this their calls would vanish. Example: pstS has eggNOG and
  tier-2 on `3.A.1.7` and its best hit on `3.A.1.7.6`, so its `3.A.1.7.6` row reads `tcdb_calls` =
  `['diamond_best_hit', 'diamond_tier', 'eggnog']`.
- **Doc caveat:** `diamond_tier` and `diamond_best_hit` come from one diamond run, so only eggNOG +
  a diamond kind is independent agreement.

**G3. Removed explorer-side, all with no alias** (CHANGELOG breaking):
- the `substrate_depth` param, row field, `by_substrate_depth` / `rows_by_substrate_depth`,
  `transport_most_specific_rows` / `transport_inherited_rows`, and the depth-tier sort;
- `tcdb_evidence_score` (row), `tcdb_evidence_score_max` and `transport_substrate_resolution`
  (gene_overview, `top_genes`, `by_gene`), and the `family_inferred` / inherited-dominance warnings;
- `include_superseded`, `TCDB_DEEPEST_ATTACHMENT_PREDICATE` in its current ungated form, and
  `leaf_attachment`;
- the `evidence_score` trust axis and `rank_prop` for TCDB. As a result, `min_evidence_score` with
  `ontology='tcdb'` raises the existing "unsupported axis" error;
- TCDB verbose edge columns `confidence_score`, `source_agreement`, `pfam_support`, `go_support`,
  `consensus_n`, `attachment_depth`;
- the `TcdbFamily.metabolite_count` term column, replaced by `tcdb_substrate_count`;
- the `substrate_breadth` few-shot in `kg/queries.py`, rewritten as a walk to systems.

**G4. Opt-in for weak TCDB hits.** "Weak hits" are the edges the KG stamps `tcdb_gate =
'below_gate'`. All of them are diamond: tier-3 calls, near-tie best hits, and rank-1 best hits
under 40% identity. eggNOG edges are never below the gate. A new param, **`include_weak_tcdb_hits: bool = False`**, replaces
`include_superseded`. It goes on `gene_ontology_terms` and `genes_by_ontology`, and applies to TCDB
only. Passing `True` for an ontology other than TCDB is a no-op, documented the same way
`include_superseded` was.

**The switch only adds rows.** The default rows come back exactly as they would without it.
- **What it adds:** one row per `below_gate` edge, tagged `tcdb_gate = 'below_gate'` in compact.
- **What it skips:** in leaf mode, a `below_gate` edge on an ancestor of a row already returned, since
  it adds nothing. Example: cynD's tier-3 call on `3.A.1`, which sits above both of its direct
  systems.
- **Example, weak hits only:** MED4 thiL (PMM0024) is a thiamine-monophosphate kinase. Its only
  TCDB edge is a 28.5% tier-3 diamond hit on `8.A.159`.
  - Default: no TCDB rows, matching `tcdb_assignment_count = 0`.
  - With the switch: one `below_gate` row.
  - This is what weak hits mostly are on non-transporters.
- **Example, weak hits on top of gated ones:** MED4 ecfA1 (PMM0125).
  - Default: 7 gated eggNOG subfamily rows (`3.A.1.25` … `3.A.1.33`, `tcdb_assignment_count = 7`).
  - With the switch: 3 more `below_gate` best-hit system rows (33–35% identity).
- **Scale:** 159 MED4 genes have only `below_gate` edges.
- **Agreement:** on the added rows, `below_gate` calls count toward `tcdb_calls` (G2). Default rows
  keep their gated `tcdb_calls`.

**G5. `tcdb_call` filter.** Add `tcdb_call: list[str] | None = None` to the TCDB ontology tools:
`genes_by_ontology`, `gene_ontology_terms`, `ontology_landscape`, `pathway_enrichment`,
`cluster_enrichment`. These are the same five tools that take `call_class` today.
- It is wired through `compact_edge` like MEROPS `call_class`, and inherits `call_class`'s existing
  scoping exactly. On a single-ontology call it raises when the ontology is not TCDB. On
  `gene_ontology_terms` with an ontology list, it applies the same skip-or-raise rule the trust
  filters use today. No new behaviour.
- Values are validated against the `ControlledVocabulary` entry `Gene_has_tcdb_family.tcdb_call`.
- `list_filter_values` exposes `tcdb_call`, `tcdb_gate` and `direction`.

**G6. Renames in prose and Literals.** `tc_specificity` becomes `tc_system` everywhere: Pydantic
`Literal`s, `ONTOLOGY_CONFIG`, YAML, docs and tests.

## Per-tool changes

### `genes_by_metabolite` / `metabolites_by_gene` (transport arm)

**Direct rows (default).**
- **Gate:** `tcdb_gate = 'direct'` edges only. `tf` is always a `tc_system`.
- **Grain:** one row per (gene, system, metabolite), with the G2 dedupe. This drops 834 duplicate
  pairs: 696 eggNOG + best hit, 138 tier + best hit.
- **Row fields, removed:** `substrate_depth`, `tcdb_evidence_score`, `transport_substrate_resolution`.
- **Row fields, added:**

  | Field | Mode | Value |
  |---|---|---|
  | `tcdb_route` | compact | `'direct'`, or `'family'` for walk rows |
  | `tcdb_calls` | compact | `list[str]`, per G2 |
  | `tcdb_identity` | compact | `float \| null`: the `identity` of the row's G2 representative edge (on family rows, the gene's edge to the attached node). Null when that edge is eggNOG. |
  | `tcdb_direction` | compact | the system's `direction`: `uptake` / `export` / `unknown` |
  | `attached_tcdb_id` | compact | the TC node the gene's edge points at. Equals `tcdb_family_id` on direct rows. |
  | `tcdb_substrate_system_count` | compact | `int \| null`: null on direct rows; see the family walk |

- **Row fields, unchanged:**
  - compact: `tcdb_family_id`, `tcdb_family_name`;
  - verbose: `tcdb_level_kind` (its `Literal` changes `tc_specificity` → `tc_system`), `tc_class_id`.

- **Metabolism-arm rows** carry the same fields as null, keeping the polymorphic shape.
- **Sort:** metabolism, then transport `direct`, then transport `family`. Within transport:
  `tcdb_identity` DESC NULLS LAST, `tcdb_family_id`, `locus_tag`.

**Family walk (opt-in): `include_tcdb_family_substrates: bool = False`.**
- **The switch only adds rows.** Direct rows come back exactly as in the default call, and the walk
  adds `tcdb_route = 'family'` rows. Direct edges point at systems, so they are never walk starts,
  and a gene's walk never starts above its own direct system (start rule 3).
- **Targets:** the walk follows both substrate edge types, `Tcdb_family_transports_metabolite` and
  `Tcdb_family_transports_chemical_role`, as direct rows do. `tcdb_substrate_count` counts both.
- **Labelling:** family rows keep `evidence_source = 'transport'`. They count in
  `by_evidence_source`, `by_evidence_source_combination` and the `multi_source_*` counts only when
  the walk is on.
- **When the TCDB arm is excluded** (`evidence_sources` without `'transport'`), the switch is
  ignored with a warning. This is the rule the GO-arm filters already follow.
- **Start:** the walk starts from the gene's `tcdb_gate = 'annotated'` edges onto a node that
  passes four rules. The walk is a **fallback for genes TCDB could not place in a system**:
  1. **Family or subfamily only.** Never class or subclass. A subclass call ("Porters", 895
     substrates) says nothing about substrate. This excludes 3 eggNOG edges.
  2. **Deepest annotated node per lineage.** Skip a family when the same gene also has an
     `annotated` call on a subfamily under it. Example: eggNOG on `3.A.1` plus tier 2 on `3.A.1.4`
     walks only from `3.A.1.4`.
  3. **No walk above a direct system.** Skip a node when the gene has a `direct` edge to a system
     under it. Such a gene already has its system's substrates, and walking would add only its
     sibling systems' substrates. Example: urtA (PMM0970) has direct systems `3.A.1.4.4` /
     `3.A.1.4.5` (urea). Walking `3.A.1.4` would add 22 amino acids and keto acids from sibling
     systems. Live effect of this rule: MED4 walk rows 821 → 668, MIT1002 5,226 → 3,389.
     - **Accepted cost, a TCDB curation quirk:** MED4 pstA/B/C/S have direct systems under
       `3.A.1.7`, e.g. pstS → `3.A.1.7.6`, which TCDB curates with **triphosphate only**. So they
       don't reach orthophosphate, and they drop out of the orthophosphate answer. The direct row's
       system name ("High affinity phosphate-specific transporter, PstABCS") still says phosphate.
       The docs (`transport.md`, `metabolites.md`) name this case explicitly.
  4. **Breadth cap.** Skip a node whose `tcdb_substrate_count > 200` (a constant, not a param),
     and warn instead. The warning names the gene and the node, and says the call is
     superfamily-level with substrate unknown. The cap removes exactly two superfamilies, ABC
     `3.A.1` (551 substrates, 420 genes) and MFS `2.A.1` (471, 2 genes); the next-broadest start
     node is DHA1 `2.A.1.2` at 125. To see such a node's range anyway, use
     `ontology_term_details`.

  `below_gate` edges never start a walk.
- **Walk:** down `Tcdb_family_is_a_tcdb_family*1..4` to descendant `tc_system` nodes, then to their
  substrates.
- **Grain:** one row per (gene, `attached_tcdb_id`, metabolite):
  - `tcdb_route = 'family'`;
  - `tcdb_family_id` = the attached node itself, not a system;
  - `tcdb_substrate_system_count`: the number of descendant systems curated with that metabolite;
  - `tcdb_direction`: the attached node's own direction.
- **Dedupe:** drop a family-substrate row when the same (gene, metabolite) already has a direct row.
- **Envelope `by_tcdb_route`:** a `{tcdb_route, count}` list, replacing
  `by_substrate_depth`.
- **Size, live with all four rules** (metabolite and role targets):

  | Scope | Genes | Walk rows | Metabolites per start node |
  |---|---|---|---|
  | MED4 | 109 | 668 | p90 7, max 32 |
  | all organisms | 7,768 | 79,474 | p90 26, max 125 |

  Request volume is handled by `limit` / `truncated`, and walk rows sort after direct rows. There is
  no row cap, because silently dropping part of a node's range would mislead.
- **Catch-all substrates:** TCDB curates some generic ones, e.g. "molecule", "Peptide", "Protein".
  In MIT1002, "molecule" is the top walk metabolite with 1,250 rows. They pass through as curated;
  the docs say so.
- **Shared filters:** `metabolite_elements`, `exclude_metabolite_ids`, `evidence_sources`,
  `gene_categories` and `include_stereo_forms` apply to walk rows as they do to direct rows.
- **Motivating case** (verified):
  - MED4 phnD (PMM0673), the phosphonate ABC binding protein, has no system call. Its usable call
    is eggNOG on subfamily `3.A.1.9` (PhnT family); its diamond hit is tier 3 on `3.A.1`, a weak
    hit.
  - `genes_by_metabolite(['kegg.compound:C00009'], organism='MED4')` returns 0 transport rows, and
    the envelope hint says 4 genes are available.
  - With `include_tcdb_family_substrates=True`, phnC/D/E and PMM0717 appear through their
    subfamilies. phnD reaches orthophosphate, phosphonic acid, phosphite, phosphinate and Fe³⁺ via
    `3.A.1.9`.

**Envelope changes.**
- **`top_genes` / `by_gene`:** drop the resolution and score fields. Add
  `tcdb_direct_rows`, `tcdb_family_rows`, and `tcdb_assignment_count` (the KG
  precompute).
- **`by_metabolite`:** `transport_most_specific_rows` / `transport_inherited_rows` become
  `tcdb_direct_rows` / `tcdb_family_rows`.
- **`top_tcdb_families`:** drop `substrate_depth`; add `tcdb_route` and `direction`. Its
  `level_kind` `Literal` follows G6.
- **Removed models:** `GbmBySubstrateDepth` and `MbgBySubstrateDepth`. Added:
  `GbmByTcdbRoute` and `MbgByTcdbRoute`.
- **Shared `evidence_sources` / `has_chemistry` predicate:** must use the same `direct` set,
  replacing the ungated deepest-attachment predicate. Live counts must reconcile:

  | Explorer count (direct rows, no filters) | KG precompute it must equal |
  |---|---|
  | distinct direct genes for a metabolite, **unioned over all organisms** (`genes_by_metabolite` is single-organism; the KG count is global) | `Metabolite.transporter_gene_count` |
  | distinct direct **Metabolite** targets for a gene (exclude `target_kind='chemical_role'` rows; the KG count is metabolites only) | `Gene.transported_metabolite_count` |

- **Family-substrates hint (both tools).** This follows the `stereo_relatives` pattern: always report
  what the opt-in would add, so an empty direct result never reads as "no transporter".
  - **`tcdb_family_substrates_not_shown: {genes, metabolites, rows} | null`.** When
    `include_tcdb_family_substrates=False`, it gives what passing `True` would add, after the start rules,
    the cap and the dedupe against direct rows. When the walk is on, it is `null`, because those
    rows are already in `results`.
  - **`tcdb_family_substrates_skipped: list[{locus_tag, tcdb_id, tcdb_substrate_count}]`.** Genes whose
    family-walk start was removed by the breadth cap. Always computed: these are the "superfamily
    call, substrate unknown" genes.
  - **Live example:** orthophosphate in MED4 has 0 direct genes. The hint reads
    `{genes: 4, metabolites: 1, rows: 4}`: phnC, phnD, phnE, PMM0717.
  - **Cost:** one extra walk query (see the Verified Cypher timings). In MED4 the whole walk is 668
    rows.
- **Warnings** (these replace the `family_inferred` warning):
  - **`genes_by_metabolite`:** when `tcdb_family_substrates_not_shown.genes > 0`, warn: "N more genes reach
    these metabolites only through a family or subfamily call (e.g. phnD, phnC); pass
    `include_tcdb_family_substrates=True`". When the direct transport arm is empty, the warning leads with
    that.
  - **`metabolites_by_gene`, per requested gene** with gate-passing edges but no `direct` edge:
    - if a walk is possible, say that its transport arm is empty and suggest
      `include_tcdb_family_substrates=True` (MED4: 94 genes);
    - if every start is capped, say that the TCDB call is superfamily-level and its substrate is
      unknown (MED4: 4 genes).
  - **Breadth cap, `metabolites_by_gene` only:** when `tcdb_family_substrates_skipped` is non-empty,
    one warning names the skipped superfamily nodes. `genes_by_metabolite` keeps the
    `tcdb_family_substrates_skipped` list in its envelope but emits **no** cap warning. ABC
    `3.A.1`'s range covers 551 substrates, so the same ABC-only genes would be named for almost any
    query (decision 7).
- **Not reported here: genes with only weak hits** (`below_gate`). They never reach substrates or
  start a walk. `gene_ontology_terms(..., include_weak_tcdb_hits=True)` shows them.

### `gene_overview`

- **Removed:** `tcdb_evidence_score_max`, `transport_substrate_resolution`.
- **Added (compact):** `tcdb_best_hit_identity: float | null`, the `identity` of the gene's rank-1
  `diamond_best_hit` edge, read live. It is **not gated**: it is reported even when that hit is
  `below_gate` (< 40%), because it is a gene-level "how close is the nearest characterised system"
  hint. The `[TRUST]` rule applies: rank, don't filter. Null when the gene has no best hit.
- **Renamed: `tcdb_family_count` → `tcdb_assignment_count`.** This follows the KG rename
  (`Gene.tcdb_assignment_count`, no alias). Most targets are systems or subfamilies, so "family"
  misled. The meaning is the KG's: distinct gated TCDB targets, minus any that is an ancestor of
  another. `has_tcdb` is now `tcdb_assignment_count > 0`. Rewrite both descriptions (no
  "deepest-attachment"). Siblings `cazy_family_count` and `ncbifam_family_count` keep their names.
- **`evidence_sources` (chemistry):** `'transport'` follows the `direct` set.

### TCDB rows in `gene_ontology_terms` / `genes_by_ontology`

| Field | Mode | Status |
|---|---|---|
| `evidence` | compact | unchanged: `family_inferred` (eggNOG) or `homology` (diamond) |
| `tcdb_call` | compact | new: the G2 representative edge's call kind |
| `tcdb_gate` | compact | new: the representative edge's gate |
| `tcdb_calls` | compact | new, per G2 |
| `sources`, `tier` | verbose | unchanged; `tier` is null on eggNOG |
| `identity`, `qcov`, `evalue` | verbose | unchanged names, from the representative edge. Percent units for TCDB and MEROPS. The shared `qcov` Pydantic description says "fraction" and must say "percent". |
| `tcdb_scov`, `tcdb_best_hit_rank`, `tcdb_bitscore`, `tcdb_bitscore_ratio` | verbose | new; `tcdb_best_hit_rank` is the edge's `rank`, renamed so it isn't mistaken for a row rank |
| `evidence_score`, `attachment_depth`, `confidence_score`, `source_agreement`, `pfam_support`, `go_support`, `consensus_n` | — | removed for TCDB; the shared Pydantic fields stay for MEROPS |

**Envelope:**
- add `by_tcdb_call`, the twin of `by_call_class`;
- `by_tier` and `by_sources` are unchanged;
- `evidence_score_stats` is null for TCDB.

### `gene_ontology_terms`

- **Leaf mode:**
  - gate-passing edges (G1), minus any node that is an ancestor of another gate-passing target for
    the same gene;
  - one row per (gene, term) with the G2 representative edge and `tcdb_calls`.
- **Leaf rows reconcile with the KG precompute:** per gene, leaf row count = `Gene.tcdb_assignment_count`.
  Verified on MED4: 0 mismatches.
- **Rollup mode:** gate-passing edges, distinct (gene, ancestor).
- **Params:** `include_weak_tcdb_hits` (G4) and `tcdb_call` (G5).

### `genes_by_ontology` / `pathway_enrichment` / `cluster_enrichment` (TERM2GENE)

- **Gene sets:** gated (G1), distinct (gene, term), G2 representative edge.
- **Enrichment gene sets match the KG precompute:** distinct genes per term = `TcdbFamily.gene_count`.
  Verified on a 300-term sample: 0 mismatches.
- **Background:** the trust filters shape the gene sets and the background identically, as today.
- **Params:** `tcdb_call` (G5). `include_weak_tcdb_hits` goes on `genes_by_ontology` only; enrichment
  stays gated.
- **Enrichment row fields don't change.** The TERM2GENE passthrough already drops edge columns, so
  no TCDB edge field reaches an enrichment row.

### TCDB `ONTOLOGY_CONFIG` row (`kg/queries_lib.py`)

- `trust`: `sources`, `evidence`, `tier`. No `evidence_score`, no `rank_prop`.
- **Representative-edge ranking:** `_best_edge_rank_key` gains an ordered-categorical form,
  `rank_order: {"prop": "tcdb_call", "order": [...], "then": "identity"}`. MEROPS keeps
  `confidence_score`.
- `compact_edge`: `tcdb_call` (filterable), `tcdb_gate`.
- `verbose_edge` (KG prop → output column):
  - `identity`, `qcov`, `evalue` keep their names, as row columns shared with MEROPS;
  - `scov` → `tcdb_scov`, `rank` → `tcdb_best_hit_rank`, `bitscore` → `tcdb_bitscore`,
    `bitscore_ratio` → `tcdb_bitscore_ratio`.
- **Naming rule:** every TCDB-only output field carries `tcdb`, parallel to the GO arm's
  `go_transport_*`. Two kinds of name are exempt:
  - row columns shared across ontologies (`evidence`, `sources`, `tier`, `identity`, `qcov`,
    `evalue`);
  - term-side columns passed through under their KG node-property names (`direction`,
    `direction_basis`, `tcdb_substrate_count`, `superfamily`). These are already scoped by
    `ontology='tcdb'`, and `*` verbose returns the raw names anyway.
- `gate`: `{"prop": "tcdb_gate", "pass": ["direct","annotated"], "override_param":
  "include_weak_tcdb_hits"}`. This replaces `leaf_attachment`.
- `term_verbose` / `term_details_compact`: drop `metabolite_count`; add `tcdb_substrate_count`,
  `direction`, `direction_basis`.

### `search_ontology` / `ontology_term_details` / `ontology_landscape`

- **Term columns** (follow the config change above):

  | Tool | Compact | Verbose |
  |---|---|---|
  | `search_ontology` | `gene_count`, `organism_count` (unchanged) | `superfamily`; new `tcdb_substrate_count`, `direction`; `metabolite_count` removed |
  | `ontology_term_details` | `tcdb_id`, `tc_class_id`, `direct_gene_count`, `member_count`, `superfamily`; new `tcdb_substrate_count`, `direction`, `direction_basis`; `metabolite_count` removed | `*` (all node props), so `substrate_breadth` drops out on its own |

  The `SearchOntologyResult` / `OntologyTermDetailsRow` Pydantic fields change to match.
- **No default `gene_count > 0` filter.** The ~5,850 range-only nodes (TcdbFamily total 9,370 after the KG's retired-family remap) are legitimate discovery
  results. The docs say how to drop them: `min_gene_count=1` (browse mode), or read `gene_count`.
- **Children lists get larger:** `3.A.1` now has 98 children, 64 of them with genes, and the largest
  node has 155. Check that the `children[]` cap and truncation flag in `ontology_term_details` hold.
- **`ontology_landscape`:** fix the `tc_specificity` note. Stats need no change.

### `list_metabolites` / `list_organisms` / `gene_details`

Prose only:
- **`'transport'` in `evidence_sources`** means TCDB lists the metabolite as a substrate of a kept
  system. Route on `transporter_gene_count > 0`.
- **Transport counts and `transporter_count`** now count `direct` systems. Rewrite the
  `transporter_count` description, which still says `substrate_depth`.
- **`gene_details`** passes Gene properties through, so the removed ones simply disappear.

### `list_filter_values`

Drop the `attachment_depth` and `pfam_support` TCDB trust-value specs; add `tcdb_call`, `tcdb_gate`
and `direction`.

## Docs, examples, lint

- **YAML** (`inputs/tools/*.yaml`, `inputs/ontologies/tcdb.yaml`): rewrite every example and mistake
  the inventory lists. Responses are regenerated with `refresh_examples.py`; only `call:` is
  hand-edited.
- **Analysis md:** `annotation_evidence.md` replaces the attachment-depth scenario with a gate
  scenario. `metabolites.md` describes direct vs family substrates, using the phnD example and the
  Pst curation quirk.
  `enrichment.md` notes that TCDB TERM2GENE is gated.
- **`analysis/transport.md`** (the three-route page). Every TCDB passage describes the old model:
  - **Routes table, `transport` row:** "the gene's TCDB family lists the compound", qualified by
    `substrate_depth` / `tcdb_evidence_score`, with the `family_inferred` bias. Rewrite it as "a
    system the gene points at directly (`tcdb_gate='direct'`) is curated with the compound". The
    bias becomes "family-only genes return no rows by default; see
    `include_tcdb_family_substrates`".
  - **New section "Reading a TCDB row"**, parallel to "Reading a GO row":
    - row grain: one row per gene × system × metabolite;
    - `tcdb_route` direct vs family (the walk is a fallback for genes without a system), with the
      phnD / orthophosphate example and the Pst caveat: Pst's direct system is curated with
      triphosphate only;
    - `tcdb_calls`, including the caveat that the two diamond kinds are one source;
    - `tcdb_identity` as the in-route ranking signal;
    - catch-all substrates ("molecule", "Peptide", "Protein");
    - the superfamily breadth cap.
  - **"What an empty answer means":** add the TCDB cases. A family-only call means read
    `tcdb_family_substrates_not_shown` and the warning. A superfamily-only call means
    `tcdb_family_substrates_skipped`, substrate unknown.
  - **Scale line:** "59 MED4 genes on GO, a small set next to the TCDB route" needs the TCDB numbers:
    89 MED4 genes reach a substrate directly, and 203 carry a gated TCDB call.
  - **"Reading agreement":**
    - `transport` is one route whatever its `substrate_depth`, so the "add `substrate_depth`" advice
      goes.
    - Add: family rows join `by_evidence_source_combination` only when
      `include_tcdb_family_substrates=True`.
    - "None of the routes gives transport direction" is now wrong: TCDB rows carry
      `tcdb_direction`, which is node-level and TCDB-stated, not per gene.
  - **Recipes:** "rank within each route by `tcdb_evidence_score`" becomes "by `tcdb_identity`, then
    `tcdb_calls`". Add a recipe: "no direct transporter for X? Re-run with
    `include_tcdb_family_substrates=True`".
  - **Unchanged:** the urea example (`urtA`–`E` direct in MED4, verified) and the GO sections.
- **Guide md:** `concepts.md`, `conventions.md`, `start_here.md`, `python_api.md`.
- **Examples:** `examples/annotation_evidence.py`, `examples/metabolites.py`.
- **CLAUDE.md:** tool-table rows for the tools above. Drop `include_superseded`,
  `tcdb_evidence_score_max`, `transport_substrate_resolution` and `substrate_depth`.
- **Lint inputs:**
  - `stale_identifiers.yaml` gains `substrate_depth`, `include_superseded`,
    `transport_substrate_resolution`, `tcdb_evidence_score_max`, `attachment_depth` and
    `tc_specificity`, each with its replacement text.
  - The `kg_claims.yaml` attachment-depth claim is replaced by a `tcdb_gate` edge-count claim.
  - `_outfacing_lint.py` comments are updated.
- **Generated config:** `config/schema_baseline.yaml` is regenerated with `scripts/export_schema.py`.
  Edit it by hand only if the script can't run.
- **Release notes:** CHANGELOG `[Unreleased]` breaking-change entry, listing every removed field and
  param with its replacement.

## Tests

- **Unit:** rewrite the TCDB classes the inventory lists, don't patch them. Add tests for each G-rule.
- **Integration:**
  - **Agreement, rows vs KG precompute:**
    - gene_ontology_terms leaf rows = `Gene.tcdb_assignment_count`;
    - TERM2GENE genes = `TcdbFamily.gene_count`;
    - genes_by_metabolite direct genes, unioned over organisms = `Metabolite.transporter_gene_count`;
    - metabolites_by_gene direct Metabolite-kind targets per gene = `Gene.transported_metabolite_count`.
  - **Exemplars:** PMM0372 cynD gives 2 direct systems, `tcdb_assignment_count` = 2 and 3 metabolites.
    PMM0673 phnD covers the family-walk case. PMM0970 urtA covers "no walk above a direct system".
    PMM0710 pstS covers the curation quirk: direct triphosphate only, no family rows.
  - **Nesting:** genes with a transport arm ⊆ genes with `'tcdb'` in `annotation_types`.
  - **No duplicate rows:** no repeated (gene, term) row in any mode of `gene_ontology_terms` or
    `genes_by_ontology`. Today's leaf path emits one row per edge: PMM0970 `3.A.1.4.4`
    (eggNOG + best hit) and PMM0710 `3.A.1.7` (tier + eggNOG) each appear twice. No repeated
    (gene, system, metabolite) row in the transport arm either.
- **Edge-case scenarios:** replace the `substrate_depth` / `include_superseded` scenarios with:
  - `include_weak_tcdb_hits`;
  - `include_tcdb_family_substrates`;
  - a gene whose only walk start is ABC `3.A.1`: no walk rows, plus the breadth-cap warning;
  - a metabolite with 0 direct genes but a non-zero `tcdb_family_substrates_not_shown` (orthophosphate in
    MED4);
  - a `tcdb_call` filter that matches nothing;
  - a gene with only `below_gate` edges.
- **Regression:** 20 goldens are touched and are regenerated after review of each diff. New goldens:
  - `genes_by_metabolite_phosphate_med4_family_substrates`;
  - `gene_ontology_terms_tcdb_gate_pmm0372`.

## Verified Cypher (target build `2026-10-24T17:33:40.709Z`)

Drafted in Step 3 and run against the live target build. Builders may restructure these (the existing
builder patterns, parameter names, `summary` / `limit` plumbing), but must keep the semantics: gate,
ancestor-drop, precedence, lineage, start rules, cap and dedupe. The `LINEAGE` fragment is shared:
it is one helper in `queries_lib.py`, used by every builder that projects `tcdb_calls`.

**`gene_ontology_terms` leaf mode (TCDB): gate, ancestor-drop, weak-hit additions, G2 representative edge, lineage `tcdb_calls`.**

```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})-[r:Gene_has_tcdb_family]->(t:TcdbFamily)
WHERE (r.tcdb_gate IN ['direct','annotated'] OR $include_weak)
  AND ($tcdb_call IS NULL OR r.tcdb_call IN $tcdb_call)
WITH g, t, r, r.tcdb_gate IN ['direct','annotated'] AS gated
// default rows: drop a gated target that is an ancestor of another gated target
WHERE (gated AND NOT EXISTS { MATCH (g)-[r2:Gene_has_tcdb_family]->(d) WHERE r2.tcdb_gate IN ['direct','annotated'] AND (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(t) })
   OR (NOT gated AND NOT EXISTS { MATCH (g)-[r2:Gene_has_tcdb_family]->(d) WHERE r2.tcdb_gate IN ['direct','annotated'] AND (d=t OR (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(t)) })
WITH g, t, r, gated ORDER BY CASE r.tcdb_call WHEN 'diamond_best_hit' THEN 0 WHEN 'diamond_tier' THEN 1 ELSE 2 END, r.identity DESC
WITH g, t, head(collect(r)) AS rep, max(CASE WHEN gated THEN 1 ELSE 0 END)=0 AS weak_row
WITH g, t, rep, weak_row, [(g)-[rl:Gene_has_tcdb_family]->(l:TcdbFamily)
   WHERE (rl.tcdb_gate IN ['direct','annotated'] OR weak_row) AND (l = t OR (t)-[:Tcdb_family_is_a_tcdb_family*1..4]->(l) OR (l)-[:Tcdb_family_is_a_tcdb_family*1..4]->(t)) | rl.tcdb_call] AS calls
RETURN g.locus_tag AS locus_tag, t.id AS term_id, t.level_kind AS level_kind, rep.tcdb_call AS tcdb_call, rep.tcdb_gate AS tcdb_gate,
  [k IN ['diamond_best_hit','diamond_tier','eggnog'] WHERE k IN calls] AS tcdb_calls, rep.evidence AS evidence, rep.identity AS identity
ORDER BY locus_tag, term_id
```

**`genes_by_ontology` level rollup / TERM2GENE (TCDB): gated, one row per (gene, term).**

```cypher
MATCH (g:Gene {organism_name: $org})-[r:Gene_has_tcdb_family]->(leaf:TcdbFamily)
WHERE r.tcdb_gate IN ['direct','annotated'] AND ($tcdb_call IS NULL OR r.tcdb_call IN $tcdb_call)
MATCH (leaf)-[:Tcdb_family_is_a_tcdb_family*0..]->(t:TcdbFamily) WHERE t.level = $level
WITH t, g, r ORDER BY CASE r.tcdb_call WHEN 'diamond_best_hit' THEN 0 WHEN 'diamond_tier' THEN 1 ELSE 2 END, r.identity DESC
WITH t, g, head(collect(r)) AS rep, false AS weak_row
WITH t, g, rep, weak_row, [(g)-[rl:Gene_has_tcdb_family]->(l:TcdbFamily)
   WHERE (rl.tcdb_gate IN ['direct','annotated'] OR weak_row) AND (l = t OR (t)-[:Tcdb_family_is_a_tcdb_family*1..4]->(l) OR (l)-[:Tcdb_family_is_a_tcdb_family*1..4]->(t)) | rl.tcdb_call] AS calls
RETURN g.locus_tag AS locus_tag, t.id AS term_id, rep.tcdb_call AS tcdb_call, [k IN ['diamond_best_hit','diamond_tier','eggnog'] WHERE k IN calls] AS tcdb_calls
ORDER BY term_id, locus_tag
```

**Transport arm, direct rows (`metabolites_by_gene` shape; `genes_by_metabolite` binds the target instead of the gene).**

```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})-[r:Gene_has_tcdb_family {tcdb_gate: 'direct'}]->(t:TcdbFamily)
MATCH (t)-[:Tcdb_family_transports_metabolite|Tcdb_family_transports_chemical_role]->(x)
WITH g, t, x, r ORDER BY CASE r.tcdb_call WHEN 'diamond_best_hit' THEN 0 WHEN 'diamond_tier' THEN 1 ELSE 2 END, r.identity DESC
WITH g, t, x, head(collect(r)) AS rep, false AS weak_row
WITH g, t, x, rep, weak_row, [(g)-[rl:Gene_has_tcdb_family]->(l:TcdbFamily)
   WHERE (rl.tcdb_gate IN ['direct','annotated'] OR weak_row) AND (l = t OR (t)-[:Tcdb_family_is_a_tcdb_family*1..4]->(l) OR (l)-[:Tcdb_family_is_a_tcdb_family*1..4]->(t)) | rl.tcdb_call] AS calls
RETURN g.locus_tag AS locus_tag, 'transport' AS evidence_source, 'direct' AS tcdb_route,
  CASE WHEN x:Metabolite THEN 'metabolite' ELSE 'chemical_role' END AS target_kind, x.id AS metabolite_id, x.name AS metabolite_name,
  t.id AS tcdb_family_id, t.id AS attached_tcdb_id, t.direction AS tcdb_direction, rep.identity AS tcdb_identity,
  [k IN ['diamond_best_hit','diamond_tier','eggnog'] WHERE k IN calls] AS tcdb_calls, null AS tcdb_substrate_system_count
ORDER BY locus_tag, tcdb_identity DESC, tcdb_family_id, metabolite_id
```

**Transport arm, family walk rows (`include_tcdb_family_substrates=True`).**

```cypher
UNWIND $locus_tags AS lt

MATCH (g:Gene {locus_tag: lt})-[r:Gene_has_tcdb_family {tcdb_gate: 'annotated'}]->(a:TcdbFamily)
WHERE a.level_kind IN ['tc_family','tc_subfamily']
  AND NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family {tcdb_gate: 'annotated'}]->(d:TcdbFamily) WHERE (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(a) }
  AND NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family {tcdb_gate: 'direct'}]->(ds:TcdbFamily) WHERE (ds)-[:Tcdb_family_is_a_tcdb_family*1..4]->(a) }
  AND a.tcdb_substrate_count <= $cap
MATCH (s:TcdbFamily {level_kind: 'tc_system'})-[:Tcdb_family_is_a_tcdb_family*1..4]->(a)
MATCH (s)-[:Tcdb_family_transports_metabolite|Tcdb_family_transports_chemical_role]->(x)
WHERE NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family {tcdb_gate: 'direct'}]->(:TcdbFamily)-[:Tcdb_family_transports_metabolite|Tcdb_family_transports_chemical_role]->(x) }
WITH g, a, r, x, count(DISTINCT s) AS nsys
WITH g, a, x, nsys, r ORDER BY CASE r.tcdb_call WHEN 'diamond_best_hit' THEN 0 WHEN 'diamond_tier' THEN 1 ELSE 2 END, r.identity DESC
WITH g, a AS t, x, nsys, head(collect(r)) AS rep, false AS weak_row
WITH g, t, x, nsys, rep, weak_row, [(g)-[rl:Gene_has_tcdb_family]->(l:TcdbFamily)
   WHERE (rl.tcdb_gate IN ['direct','annotated'] OR weak_row) AND (l = t OR (t)-[:Tcdb_family_is_a_tcdb_family*1..4]->(l) OR (l)-[:Tcdb_family_is_a_tcdb_family*1..4]->(t)) | rl.tcdb_call] AS calls
RETURN g.locus_tag AS locus_tag, 'transport' AS evidence_source, 'family' AS tcdb_route,
  CASE WHEN x:Metabolite THEN 'metabolite' ELSE 'chemical_role' END AS target_kind, x.id AS metabolite_id, x.name AS metabolite_name,
  t.id AS tcdb_family_id, t.id AS attached_tcdb_id, t.direction AS tcdb_direction, rep.identity AS tcdb_identity,
  [k IN ['diamond_best_hit','diamond_tier','eggnog'] WHERE k IN calls] AS tcdb_calls, nsys AS tcdb_substrate_system_count
ORDER BY locus_tag, tcdb_identity DESC, tcdb_family_id, metabolite_id
```

**`tcdb_family_substrates_skipped` (breadth cap).**

```cypher
UNWIND $locus_tags AS lt

MATCH (g:Gene {locus_tag: lt})-[r:Gene_has_tcdb_family {tcdb_gate: 'annotated'}]->(a:TcdbFamily)
WHERE a.level_kind IN ['tc_family','tc_subfamily']
  AND NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family {tcdb_gate: 'annotated'}]->(d:TcdbFamily) WHERE (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(a) }
  AND NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family {tcdb_gate: 'direct'}]->(ds:TcdbFamily) WHERE (ds)-[:Tcdb_family_is_a_tcdb_family*1..4]->(a) }
  AND a.tcdb_substrate_count > $cap
RETURN DISTINCT g.locus_tag AS locus_tag, a.id AS tcdb_id, a.tcdb_substrate_count AS tcdb_substrate_count
```

**`tcdb_family_substrates_not_shown` for `genes_by_metabolite` (walk off).**

```cypher
MATCH (x) WHERE x.id IN $metabolite_ids
MATCH (s:TcdbFamily {level_kind: 'tc_system'})-[:Tcdb_family_transports_metabolite|Tcdb_family_transports_chemical_role]->(x)
MATCH (s)-[:Tcdb_family_is_a_tcdb_family*1..4]->(a:TcdbFamily)
WHERE a.level_kind IN ['tc_family','tc_subfamily'] AND a.tcdb_substrate_count <= $cap
MATCH (g:Gene {organism_name: $org})-[:Gene_has_tcdb_family {tcdb_gate: 'annotated'}]->(a)
WHERE NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family {tcdb_gate: 'annotated'}]->(d:TcdbFamily) WHERE (d)-[:Tcdb_family_is_a_tcdb_family*1..4]->(a) }
  AND NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family {tcdb_gate: 'direct'}]->(ds:TcdbFamily) WHERE (ds)-[:Tcdb_family_is_a_tcdb_family*1..4]->(a) }
  AND NOT EXISTS { MATCH (g)-[:Gene_has_tcdb_family {tcdb_gate: 'direct'}]->(:TcdbFamily)-[:Tcdb_family_transports_metabolite|Tcdb_family_transports_chemical_role]->(x) }
RETURN count(DISTINCT g) AS genes, count(DISTINCT x) AS metabolites, count(DISTINCT [g.locus_tag, a.id, x.id]) AS rows,
  collect(DISTINCT coalesce(g.gene_name, g.locus_tag))[0..8] AS example_genes
```

**`gene_overview` `tcdb_best_hit_identity` (not gated).**

```cypher
UNWIND $locus_tags AS lt
OPTIONAL MATCH (g:Gene {locus_tag: lt})
OPTIONAL MATCH (g)-[r:Gene_has_tcdb_family {tcdb_call: 'diamond_best_hit', rank: 1}]->()
RETURN lt, g IS NOT NULL AS found, g.tcdb_assignment_count AS tcdb_assignment_count, r.identity AS tcdb_best_hit_identity, r.tcdb_gate AS gate
```

**Results** (MED4 unless noted):

| Check | Result |
|---|---|
| Leaf rows, all MED4 genes vs `Gene.tcdb_assignment_count` | 322 rows, 0 mismatches, 0 duplicate (gene, term), 155 ms |
| `include_weak_tcdb_hits=True` | 739 rows. All 322 default rows unchanged; all 159 weak-only genes gain rows; added rows count their `below_gate` calls |
| `tcdb_call=['eggnog']` (filter changes results) | 12 → 10 rows on the 6-gene batch |
| `tcdb_call` matching nothing | 0 rows, no error |
| Nonexistent locus tag in a mixed batch | dropped from rows, so the existing `not_found` path applies |
| Level-3 rollup | 285 rows, 0 duplicates, 94 ms |
| Direct transport rows vs `Gene.transported_metabolite_count` (Metabolite-kind targets) | 143 rows, 0 duplicate (gene, system, target), 0 mismatches |
| Lineage `tcdb_calls` | pstS `3.A.1.7.6` → `['diamond_best_hit','diamond_tier','eggnog']`; cynD's two sibling systems one call each (siblings are not lineage) |
| Family walk (start rules 1–4) | 668 rows over 109 genes. phnD → orthophosphate via `3.A.1.9`. urtA and pstS get no family rows (direct systems below their subfamilies). Before rule 3 was added: 821 rows / 138 genes, with urtA → 22 sibling-system substrates |
| Breadth cap | 4 MED4 genes have a `3.A.1` start skipped (7 before rule 3) |
| `tcdb_family_substrates_not_shown` | orthophosphate `{genes: 4, metabolites: 1, rows: 4}` (phnC/D/E, PMM0717); urea `{0, 0, 0}` (all direct). About 0.6 s before rule 3 |
| `tcdb_best_hit_identity` | cynD 59.2 (direct); ecfA1 33.5 (`below_gate`, still reported); no best hit → null; unknown tag → `not_found` |

**Notes for the build:**
- **eggNOG often names several TC ids,** e.g. ecfA1 has 7 subfamilies. Each is its own leaf row, as
  the KG counts them.
- **Most remaining walk noise is eggNOG family or subfamily calls on non-transporters** (ftsY,
  htpG, clpB, motB, dsbB). Those calls pass the KG gate, so the explorer does not second-guess them.
  "Is this gene a transporter?" is KG 3b. The docs say family rows are a recall expansion.
- **`GBM_HINT` is the slowest query** (about 0.6 s). It runs on every `genes_by_metabolite` call, so
  the query builder should check it against the existing summary-query budget, and anchor on the
  organism's genes first if it needs to be faster.

## Absorb (last step, same branch)

**Target build:** the KG rebuild of `feat/post-3a-fixes`, green-lit 2026-10-24. That build carries
3a, the `tcdb_assignment_count` rename and the fixes below. This spec does not absorb
`2026-10-23T17:57:48Z` on its own.

That build adds, beyond TCDB:
- **182 KEGG pathways dropped** (449 → 267). Sweep the YAML, docs, examples and goldens against the
  KG's dropped-id list (ask A1). Update `kg_claims` pathway counts. Re-check
  `discussed_by_publication` for Moreno 2023 (`map04710` edge gone).
- **MEROPS `qcov` is in percent.** Fix the shared `qcov` Pydantic description ("fraction" →
  "percent") and any doc example that filters on a fraction.
- **`stereo_assignment` rule change:** 4 assay rows flip to `dominant_form_assumed`. Expect golden
  diffs in `metabolites_by_quantifies_assay` / `assays_by_metabolite`, classified as announced.
- **TcdbFamily total 9,370:** the retired-family remap. Gene-edge totals are unchanged.

Before absorbing, re-run the 34 TCDB invariant checks against the rebuilt graph.

Steps:

Per the `absorb-kg-rebuild` skill:
- Re-pin the hash, with a constants comment naming the target build's `built_at` (3a + post-3a fixes).
- Run `snapshot_vocab`.
- Run fixture guards.
- Pick a new exemplar for `test_ouabain_brite_classes`; ouabain was removed.
- Regenerate goldens after classifying them.
- Run `refresh_examples`.
- Run `build_about_content --live-vocab`.
- Check `kg_claims`.
- Do the highlights sweep using the KG note.
- Write the CHANGELOG entry.
- Restart `/mcp` and confirm `kg_release_info` reads `ok`.

## Decisions (approved 2026-10-24)

1. **Names.** `include_tcdb_family_substrates`, `include_weak_tcdb_hits`, `tcdb_route` {`direct`,
   `family`}, `tcdb_calls`, `tcdb_identity`, `tcdb_direction`, `attached_tcdb_id`,
   `tcdb_substrate_system_count`, `tcdb_best_hit_identity`, `tcdb_best_hit_rank`, `by_tcdb_call`.
2. **Family-walk grain:** per (gene, attached node, metabolite) with `tcdb_substrate_system_count`, rather
   than one row per system. Per system would multiply rows (e.g. 5 systems behind phnD's
   orthophosphate row), and up to hundreds for ABC.
3. **Walk breadth cap:** 200 substrates on the start node, as a constant with a warning.
4. **`include_weak_tcdb_hits` stays off the enrichment tools.**
5. **Single build branch** for the code change and the absorb, since the goldens and examples can
   only go green together.
6. **No family walk above a direct system** (start rule 3, approved 2026-10-24).
7. **No breadth-cap warning in `genes_by_metabolite`;** the envelope list stays (approved 2026-10-24).
