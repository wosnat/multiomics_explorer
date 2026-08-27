# Annotation-trust surface — design (slice 3 of the 2026-08 synced release)

**Date:** 2026-08-27
**Status:** design approved section-by-section (explorer owner, 2026-08-27); KG-SYNC-005 landed; frozen tool spec follows live Cypher verification
**Author:** Osnat + Claude
**KG contract:** `multiomics_biocypher_kg/docs/kg-changes/annotation-trust-surface.md` (KG-SYNC-005), `interpro-multi-ontology.md`, `merops-extension.md`, `tcdb-two-source-upgrade.md`, `vocabulary-contract.md`
**Asks dialog:** `docs/kg-specs/2026-08-27-annotation-trust-kg-asks.md` (ONT-001…015, all accepted)

## Motivation

Three ontologies arrived in the KG (InterPro, NCBIfam, MEROPS) together with a body of
per-edge "why do we believe this" facts that the explorer has no vocabulary for: TCDB's
two-source `evidence_score` / `tier` / `attachment_depth`, MEROPS's `call_class` / `tier` /
`pfam_support`, InterPro's `libraries` / sparse `evalue`, and the Layer-B `sources` /
`evidence` on the GO/EC/Pfam/CAZy edges. The explorer surfaces exactly two such facts today
(PSORTb `score`, SignalP `probability`) through ad-hoc prefixed columns and offers no trust
filter anywhere. Registering three more `ONTOLOGY_CONFIG` rows would have left the agent
reading `tier=3, pfam_support=corroborated, call_class=nonpeptidase_homolog` with no place
that says what it means.

This slice therefore builds one **annotation-trust surface** across all gene→term edges,
plus a term-side drill-down tool and a per-ontology reference, and registers the three
ontologies inside it.

## Section 1 — Scope and concept model

**Three concept layers, each with one home:**

| layer | what | where |
|---|---|---|
| comparable trust axes | facts with the same meaning wherever they occur: `sources[]`, `evidence` (`curated > signature > homology > family_inferred > domain_inferred`), `evidence_score` ∈ [0,1] (R4), `tier` 1–3 (diamond truncation depth; TCDB + MEROPS) | one compact column on every gene×term row; verbose for the rest; filter params; envelope rollups |
| native trust detail | ontology-specific scalars/facts that must not be compared across ontologies: `confidence_score`, `evalue`, `bit_score`, `libraries[]`, `evalue_library`, `match_count`, `source_agreement`, `pfam_support`, `go_support`, `best_hit_kind`, `identity`, `qcov`, `consensus_n`, `attachment_depth`, `localization_score`, `signal_peptide_*` | verbose, own names, never a filter |
| materially-important facts | categoricals whose absence changes the biological reading: MEROPS `call_class` | compact always + filter + rollup + auto-warning |

Plus a **term-character layer** (node side): `description`, `interpro_type`, NCBIfam
`family_type`, MEROPS `family_class` / `catalytic_type` / `peptidase_gene_count` /
`peptidase_organism_count` / cleavage profile, `gene_count` / `direct_gene_count`,
`is_uninformative`, forward bridges.

**Decisions taken in review:**
- **One compact trust column, not four.** Rollups carry the distribution; verbose carries the axes per row. **Decided 2026-08-27: `evidence`** (universal on all 14 functional edge types after KG-SYNC-005; absent on PSORTb/SignalP). `evidence_score` is verbose, remains the within-ontology sort key and the only cutoff.
- **`score` + `score_kind` rejected.** Native scalars differ in scale *and direction* (e-value lower-is-better, bit score / confidence / probability higher-is-better); a kind tag does not stop cross-ontology sorting. Rule: *compact = comparable, verbose = native.*
- PSORTb/SignalP columns keep their names and move compact → verbose.
- Term side has four layers: `search_ontology` compact / verbose (anything you would filter or compare wide on) and `ontology_term_details` compact / verbose (dig-in; verbose = every node property).

**Ground rules (binding, from KG contracts):**
1. Defaults never filter on trust. The only numeric cutoff is `min_evidence_score`; when set the envelope shows the fired signals.
2. No cutoff on any native scalar (InterPro contract forbids e-value thresholds; others are uncalibrated).
3. Edge presence = recall; `annotation_types` = quality. Ontology tools bind on edges.
4. Bridges are read forward only (family → what characterizes it). `ontology_term_details` has no `links_in`.
5. Gene-set semantics stay subtree-union (unchanged). Leaf rows honour `attachment_depth` / most-specific attachment.

**Tools touched:** `genes_by_ontology`, `gene_ontology_terms`, `search_ontology`, `ontology_landscape`, `pathway_enrichment`, `cluster_enrichment`, `list_filter_values`, `gene_overview`. **New:** `ontology_term_details`. Chemistry-arm tools untouched.

**Out of scope → slice 4:** `controlled_vocabularies_hash` in `kg_release_info`; per-row `transport_substrate_resolution`; `list_organisms` protease/domain rollups; NCBIfam `family_type` as a filter; ORA over bridges.

## Section 2 — `ONTOLOGY_CONFIG` as the single registry

Every column, filter, facet, bridge, and validation the builders perform is declared per
ontology in `kg/queries_lib.py::ONTOLOGY_CONFIG`. `_EDGE_PROP_COLS` (api) and the scattered
`ontology != "brite"` guards are removed.

```python
"merops": {
    "label": "MeropsFamily",
    "gene_rel": "Gene_has_merops_family",
    "hierarchy_rels": ["Merops_family_is_a_merops_family"],
    "fulltext_index": "meropsFamilyFullText",
    # trust axes — normalized name → edge prop; absent key = axis not carried
    "trust": {"sources": "sources", "evidence": "evidence", "evidence_score": "evidence_score",
              "tier": "tier", "rank_prop": "confidence_score"},
    # materially-important edge facts — compact, filterable, rolled up, warned on
    "compact_edge": {"call_class": {"prop": "call_class", "warn_values": ["nonpeptidase_homolog"]}},
    # native detail — verbose only, own names, never filters
    "verbose_edge": ["confidence_score", "pfam_support", "best_hit_kind", "identity", "qcov",
                     "evalue", "consensus_n", "best_hit_id"],
    # term side
    "facet": None,
    "term_compact": ["gene_count", "organism_count"],
    "term_verbose": ["family_class", "catalytic_type", "peptidase_gene_count"],
    "term_details_compact": ["merops_id", "family_class", "catalytic_type", "peptidase_gene_count",
                             "peptidase_organism_count", "direct_gene_count", "member_count"],
    "term_details_verbose": "*",
    "bridges_out": [("Merops_family_has_pfam_domain", "pfam", "composition")],
},
```

Per-ontology registry (post KG-SYNC-005):

| key | trust axes | rank_prop | compact_edge | verbose_edge | facet | term_verbose | bridges_out (kind) |
|---|---|---|---|---|---|---|---|
| go_bp/mf/cc, ec, pfam, cazy | sources, evidence, evidence_score | — | — | — | — | — | pfam → interpro (membership) |
| kegg, cog_category, cyanorak_role, tigr_role | sources, evidence | — | — | — | — | — | kegg → brite (membership) |
| brite | (via kegg edge) | — | — | — | tree | — | — |
| tcdb | sources, evidence, evidence_score, tier | evidence_score | — | confidence_score, source_agreement, pfam_support, go_support, identity, qcov, evalue, consensus_n, attachment_depth | — | superfamily, metabolite_count | → pfam, → go×3 (composition) |
| merops | sources, evidence, evidence_score, tier | confidence_score | call_class | (above) | — | family_class, catalytic_type, peptidase_gene_count | → pfam (composition) |
| interpro | sources, evidence | — | — | libraries, evalue_library, evalue, match_count, start, end | interpro_type | — | → ec, → cazy (router) |
| ncbifam | sources, evidence | — | — | evalue, bit_score, start, end | — | family_type, gene_symbol | → interpro (membership) |
| subcellular_localization | — | — | — | localization_score | — | — | — |
| signal_peptide_type | — | — | — | signal_peptide_probability, cleavage_site, cleavage_probability | — | — | — |

Invariants (import-time, `tests/unit/test_config_registry.py`): `term_details_compact ⊇ term_compact ∪ term_verbose`; every named prop exists in `config/schema_baseline.yaml`; `rank_prop ∈ trust ∪ verbose_edge`; bridge targets are known keys; **config declares no value lists** (values come from `ControlledVocabulary`, §8.3). `ALL_ONTOLOGIES` order: existing 14 + `interpro, ncbifam, merops` appended.

## Section 3 — Row schemas

**Strip-non-applicable, keep applicable-but-absent.** The `api/` layer drops columns the row's ontology does not own (config-driven); columns the ontology owns stay even when `null` (TCDB `tier` on an eggNOG-only edge; InterPro `evalue` on a PROSITE-only match) — there `null` is information. Envelope `trust_axes` says what to expect. Pydantic rows keep all fields `Optional`.

### 3.1 `genes_by_ontology`, `gene_ontology_terms`

| mode | columns |
|---|---|
| compact (existing) | `locus_tag`, `gene_name`, `product`, `gene_category` (GbO), `term_id`, `term_name`, `level`, `tree`, `tree_code`, `is_informative`, `ontology_type` (GOT multi) |
| compact (new) | `evidence` (§1), `interpro_type`, `call_class` |
| verbose (existing) | `function_description`, `level_is_best_effort`, `organism_name` |
| verbose (new) | `sources`, `evidence_score`, `tier`, then native detail per config |

**One edge per (gene, term).** On hierarchical ontologies a rollup row's `t` is an ancestor; trust columns come from the gene's best edge under `t` (`rank_prop` desc, then most specific attachment). Fixes the latent PSORTb-era `RETURN DISTINCT` + `r.*` duplication on rollups.

### 3.2 Enrichment — term rows unchanged; `interpro_type` sparse column; filters shape TERM2GENE, not the row.
### 3.3 Landscape — rows per `(ontology, level[, facet])`; `tree`/`tree_code` unchanged for BRITE; `interpro_type` sparse for InterPro.
### 3.4 `search_ontology`

| mode | columns |
|---|---|
| compact | `id`, `name`, `ontology_type`, `level`, `tree`, `tree_code`, `is_informative`, `score` (Lucene; null in browse), `gene_count`, `organism_count`, `interpro_type` |
| verbose | `description`, `level_kind`, `direct_gene_count` (hierarchical labels), config `term_verbose` union, KEGG `discussed_*` |

### 3.5 `ontology_term_details`

| mode | columns |
|---|---|
| compact | `term_id`, `ontology`, `label`, `name`, `description`, `level`, `level_kind`, `is_informative`, `gene_count`, `organism_count`, `direct_gene_count`, config `term_details_compact`, `parents[]` / `children[]` (`{id,name,level}`, direct; `children_total`, capped 50), `links_out[]` (`{rel, link_kind, target_id, target_ontology, target_name}`) |
| verbose | `properties` (= `t{.*}`), `links_out[].props` (`curated_tcids`, `member_id_count`), `genes_by_organism[]` |

### 3.6 `gene_overview` — `merops_classes` (`[]` default), `ncbifam_family_count` (0 default), `merops_evidence_score_max` (sparse, uncoalesced — twin of `tcdb_evidence_score_max`).

## Section 4 — Filter API and validation

Generic names, config-validated per ontology, default `None`. On `genes_by_ontology`, `gene_ontology_terms`, `pathway_enrichment`, `cluster_enrichment`; categorical ones also on `ontology_landscape`.

| param | type | semantics | valid on |
|---|---|---|---|
| `sources` | `list[str]` | any listed value `IN r.sources` | all 14 functional edge ontologies |
| `evidence` | `list[str]` | `r.evidence IN $v` | all 14 |
| `max_tier` | `int` 1–3 | `r.tier <= $v OR r.tier IS NULL` (TCDB eggNOG-only edges keep; `by_tier` shows the null bucket) | tcdb, merops |
| `min_evidence_score` | `float` | `r.evidence_score >= $v`; envelope adds `evidence_score_signals` | GO×3, EC, Pfam, CAZy, TCDB, MEROPS |
| `call_class` | `list[str]` | `r.call_class IN $v` | merops |
| `interpro_type` | `Literal[8]` | term facet; **required** on enrichment for `ontology='interpro'` | interpro |
| `tree` | unchanged | term facet, same `facet` config | brite |
| `include_superseded` | `bool=False` | leaf mode: include `attachment_depth='superseded'` rows (labelled) | tcdb |

Trust filters bind at the gene→leaf `MATCH … WHERE`, before the hierarchy walk and the `collect(DISTINCT g)` size collapse. Facets bind on `t` after the walk. Enrichment's TERM2GENE goes through the same match stage, so filters shape tested sets and background identically (`background_filtered` echoed).

Validation (`ValueError` → `ToolError`, pre-query): unsupported axis names the ontology's axes and points at `list_filter_values(filter_type='trust_axes')`; unknown categorical value lists the allowed set from `ControlledVocabulary`; `interpro_type` missing on interpro enrichment raises with the stratum hint.

**Multi-ontology (`gene_ontology_terms`, `ontology_landscape`, `search_ontology`): `ontology: list[str] | None`.** Rules (numeric-DM soft-exclude precedent): filter carried by all → apply; by some → apply and drop the rest into `skipped_ontologies[{ontology, reason}]` + warning; by none → raise. Facet with owner in set → apply to owner only, others untouched; owner absent → raise. `rollup` level beyond depth → 0 rows + skipped entry. Unknown name → raise. `genes_by_ontology` and enrichment stay single-ontology.

## Section 5 — Envelopes, rollups, warnings

Gene-set tools: `trust_axes {ontology: [axes]}`, `by_evidence`, `by_tier` (explicit `"null"` bucket), `by_sources` (membership counts), `by_call_class`, `evidence_score_stats {min, median, max, n_null}`, `evidence_score_signals {edge_type: [signals]}` (only when `min_evidence_score` set; from vocab `signals`), `filters_applied`, `skipped_ontologies`, `warnings`. Enrichment: `filters_applied`, `trust_axes`, `background_filtered`, `interpro_type`. `search_ontology`: `mode`, `by_ontology {total_entries, total_matching, score_max, returned, truncated}`, `by_level` (browse), `by_interpro_type` / `by_family_type`. `ontology_term_details`: `not_found`, `by_ontology`, `links_out_total`, `by_link_kind`.

Auto-warnings (rows-conditional, + `ctx.warning`): merops `nonpeptidase_homolog` rows without `call_class`; `max_tier` keeping tier-null rows; interpro enrichment stratum with 0 testable terms; `min_evidence_score` applied; skipped ontologies; browse mode truncated without narrowing filters. Each gets a corner-case scenario.

## Section 6 — `ontology_term_details`

```python
ontology_term_details(term_ids: list[str], organism: str | None = None,
                      link_kinds: list[Literal["composition","membership","router"]] | None = None,
                      verbose: bool = False, limit: int = 50, offset: int = 0)
```
Batch, cross-ontology (self-prefixed CURIEs), rows in input order, `not_found[]`. Bridges registry:

| rel | from → to | kind | props |
|---|---|---|---|
| `Tcdb_family_has_pfam_domain` | tcdb → pfam | composition | `curated_tcids` |
| `Tcdb_family_involved_in_biological_process` / `_enables_molecular_function` / `_located_in_cellular_component` | tcdb → go_* | composition | `curated_tcids` |
| `Merops_family_has_pfam_domain` | merops → pfam | composition | `member_id_count` |
| `Pfam_in_interpro_entry` | pfam → interpro | membership | — |
| `Ncbifam_family_in_interpro_entry` | ncbifam → interpro | membership | — |
| `Interpro_entry_related_to_ec_number` / `_cazy_family` | interpro → ec / cazy | router | `router_ambiguous` computed (out-degree > 1 or type ≠ FAMILY) |
| `Kegg_term_in_brite_category` | kegg → brite | membership | — |

Forward-only by construction; docstring carries the direction contract (composition 85% forward / ~31% backward for TCDB; router = recall-biased, never assign gene function). Cypher: one `UNWIND` batch; label guard over all 18 labels; per-label is-a union for parents/children; bridge blocks generated from config; `not_found = t IS NULL`.

## Section 7 — `search_ontology` browse mode; landscape facets; leaf filter

- `search_text` optional; `None`/`""` = **browse**: `MATCH (t:<label>)`, filters `level`, facet, `informative_only`, `min_gene_count`, optional `organism` (per-organism count scope), sort `gene_count DESC, id`, `score` null, envelope `mode: "browse"`, `by_level`. Search mode unchanged.
- Multi-ontology: Lucene scores are per index (BM25) → rows ordered `ontology_type` (config order) then `score DESC`; **`limit`/`offset` per ontology, lockstep paging**; `by_ontology[o].truncated`; `returned ≤ limit × n`. Implementation: api-layer fan-out per ontology (keeps the Pfam dual-index path).
- Landscape: facet generalization; `best_interpro_type` + `best_level` per ontology; `call_class` filter on merops so landscape sizes match enrichment sets; default fan-out = 17.
- Leaf filter: `NOT EXISTS { (g)-[:rel]->(child)-[:is_a*1..]->(t) }` (was one hop). TCDB additionally `r.attachment_depth = 'most_specific'` unless `include_superseded`.

## Section 8 — `gene_overview`, `list_filter_values`, vocab contract

- `gene_overview`: §3.6 columns; envelope `by_merops_class`, `has_ncbifam`.
- `list_filter_values`: new `filter_type` ∈ {`evidence`, `sources`, `call_class`, `interpro_type`, `ncbifam_family_type`, `merops_catalytic_type`, `merops_family_class`, `best_hit_kind`, `pfam_support`, `attachment_depth`} from `ControlledVocabulary` (`{value, applies_to[], description, source: "vocabulary"}`), plus `trust_axes` and `link_kinds` from config; `ontology` scopes.
- **Ownership:** config owns shape (which props, compact/verbose, axes, facets, bridges); `ControlledVocabulary` owns values/descriptions/min-max/signals, read at first use and cached per process.
- **Missing vocab node:** `-m kg` test failure naming the node (KG-side fix); at runtime a **pivot query** (`MATCH ()-[r:X]->() RETURN DISTINCT r.prop`) + `warnings` entry, `source: "pivot"` in `list_filter_values`. Never a hard-coded list, never a hard raise.

## Section 9 — Docs

- **New hand-authored** `docs://analysis/annotation_evidence` (three layers; per-ontology trust profile; rank-don't-filter; MEROPS `call_class`; InterPro `(type, level)` ORA; bridges direction; 4 recipes).
- **New generated per-ontology reference** `docs://ontologies/{key}` ×17 + `index`: `inputs/ontologies/{key}.yaml` (human: what it is, method, id form, hierarchy, interpretation, informativeness rule, pitfalls, typical questions) merged with config + schema baseline + `ControlledVocabulary` values at build time (`build_about_content.py` `ontologies` stage; `--lint` covers it). Linked from `concepts` (table), `enrichment`, `metabolites` (TCDB), `start_here`, every ontology-tool `Routing:` sentence, `ontology_term_details.ontology`.
- Guides: `concepts`, `conventions` (single compact trust column; strip rule; `trust_axes`; lockstep paging; browse vs search; vocab-vs-pivot), `start_here`.
- 8 tool yamls + new `ontology_term_details.yaml`; `examples/annotation_evidence.py`, `examples/ontology_terms.py`; `CLAUDE.md` rows + `[TRUST]` marker; api/analysis docstrings.
- Mirror KG semantics: `gene_count` subtree on hierarchical labels, direct on flat; `direct_gene_count` on hierarchical labels **except PfamClan and BriteCategory** (KG: constant 0, not emitted); GO/KEGG DAG counts don't sum; InterPro `gene_count` semantics changed (breaking, KG-side); `attachment_depth = superseded` means less specific, not wrong.

## Section 10 — Tests, regression, build order

Unit: parametrize all 17; Cypher names exactly config labels/edges/indexes; trust predicates before size collapse; one-edge rebind; `*1..` leaf filter; browse Cypher; term-details fragments; BRITE `tree` output byte-identical golden; strip rule; lockstep paging; multi-ontology matrix; vocab → pivot → warning; `EXPECTED_TOOLS` += `ontology_term_details`; 6 `Literal` bumps; `Field` ≤ 250 chars; `test_config_registry.py`; generator `ontologies` stage.
Integration (`-m kg`): smoke per (tool × new ontology) + browse + multi + details batch; `test_trust_vocab_coverage.py` (every filtered/rolled pair has a vocab node — §7.3 of asks doc); `test_trust_invariants.py` (merops peptidase set == `peptidase_gene_count` per organism; TCDB leaf rows == `attachment_depth='most_specific'` set; `gene_count` subtree semantics; signals == vocab); `edge_cases/scenarios.py` for the new tool + every new filter/warning.
Regression: `TOOL_BUILDERS` += `ontology_term_details`; ~15 new goldens; `--force-regen` on ontology tools, diff rule: existing rows may only lose the two moved PSORTb/SignalP columns and gain the new ontologies appended.
Build order: schema baseline refresh → spec frozen with live Cypher → worktree/HEAD check → RED (`test-updater`) → GREEN (4 file-owned agents; "registry first, one ontology as template, extend to 17; `ontology_term_details` last as Mode A within your file") → VERIFY (`--lint`, `code-reviewer` on all 18 labels/edges/indexes + bridge directions + predicate placement, unit → integration → regression) → verification-before-completion → finishing-a-development-branch.
Optional seam if split: **3a** registry + trust surface + 3 ontologies; **3b** `ontology_term_details` + browse mode + per-ontology reference docs.

## Self-review (2026-08-27)

- Placeholders: none. Single compact trust column decided: `evidence`.
- Consistency: `score`/`score_kind` removed everywhere; `attachment_depth` values match KG (`most_specific | superseded`); `family_class` / `bit_score` renames applied; `direct_gene_count` exceptions (PfamClan, BriteCategory) recorded.
- Scope: large; seam 3a/3b documented.
- Ambiguity resolved: `max_tier` keeps tier-null; lockstep paging bound stated; multi-ontology skip/raise matrix explicit.
