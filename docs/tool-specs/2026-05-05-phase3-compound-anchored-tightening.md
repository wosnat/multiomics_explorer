# Tool spec: Phase 3 — Compound-anchored tightening + ergonomics (metabolites surface refresh)

**Date:** 2026-05-05.
**Roadmap:** [docs/superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md](../superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md) — Phase 3.
**Phase 1 spec (predecessor):** [docs/tool-specs/2026-05-05-phase1-pass-through-plumbing.md](2026-05-05-phase1-pass-through-plumbing.md).
**Phase 2 spec (predecessor):** [docs/tool-specs/2026-05-05-phase2-cross-cutting-renames.md](2026-05-05-phase2-cross-cutting-renames.md).
**Audit:** [docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md](../superpowers/specs/2026-05-04-metabolites-surface-audit.md) — Part 2 build-derived P2 (None-padding union shape on GBM + MBG), P3 (reversibility docstring, family_inferred warning rewrite, by_element semantics, MBG summary `top_genes=None` investigation). Audit row 377 (`search_ontology` `query=` alias) was originally Item 5 but DROPPED 2026-05-06 — see §6.5.
**Walkthrough decisions:** 2026-05-05 Q&A — items 1, 2, 3 APPROVED. Item 4 (`by_element` / `elements` semantics) APPROVED at frozen-spec review 2026-05-05. **Item 5 (cross-tool `query=` alias) DROPPED 2026-05-06** — initially option (c) then reversed; user judgment: not justified (the alias adds surface area without empirical pull, and `query=`-style LLM friction can be addressed via Field-description hinting on the existing `search_text=` kwarg in a future docs-only pass if it ever resurfaces). Item 6 resolved during Phase 3 ready-to-plan investigation (2026-05-05 chat); user decision at frozen-spec review: **drop the optional MBG docstring disambiguation note** — analysis-doc fix alone is sufficient.

## Mode

**Mode B (cross-tool small change).** Spec lists 3 compound-anchored tools (`genes_by_metabolite`, `metabolites_by_gene`, `list_metabolites`) for items 1-4 + 6, plus 1 analysis-doc snippet. No KG iteration (surface + docstring only); items are bundled because they share the compound-anchored chemistry surface and the same TDD scaffolding (test fixtures + about-content regen). Per-tool changes are mostly docstring / Field-description edits; the only behavior changes are (a) `_GBM_SPARSE_FIELDS` / `_MBG_SPARSE_FIELDS` reduction (item 1) and (b) two warning string replacements (item 3). **Item 5 (cross-tool `query=` alias) was DROPPED 2026-05-06** — Phase 3 now ships 5 active items, not 6.

## Purpose

Sharpen the row schema and docstrings on the compound-anchored chemistry tools so consumers read consistent shapes and accurate "involved in" / reversibility framing. The audit's build-derived second pass surfaced six small frictions; one (`search_ontology` `query=` alias) was DROPPED 2026-05-06, leaving 5 active items across `genes_by_metabolite`, `metabolites_by_gene`, and `list_metabolites` — all docstring-or-minor-schema edits scoped to the compound-anchored surface, with no KG dependencies and no breaking behavior shifts.

The 6 items are:

1. **`genes_by_metabolite` + `metabolites_by_gene` — None-padding for cross-arm fields.** Today the api/ layer sparse-strips arm-specific fields when null (so transport rows have no `reaction_id` key at all and metabolism rows have no `transport_confidence` key at all). Audit + walkthrough decision: surface explicit `None` for cross-arm fields so every row has identical key set. Cleaner schema for downstream code; row-fattening cost is trivial (~7 extra `None` keys per row).
2. **`genes_by_metabolite` + `metabolites_by_gene` — reaction-arm reversibility framing.** Today neither tool's docstring spells out that reaction edges are undirected AND carry no reversibility flag. Surface that explicitly: "reaction edges are undirected AND carry no reversibility flag — interpret all reaction-arm rows as 'involved in', never 'produces' / 'consumes' / 'reversible'." Folds in §4.1.2 (resolved 2026-05-05) with §4.1.1.
3. **`genes_by_metabolite` + `metabolites_by_gene` — family_inferred-dominance warning rewrite.** Both tools emit a warning that prescribes `transport_confidence='substrate_confirmed'` as a "high-precision" tighten action. The wording predates the §g reframing where both tiers are framed as annotations (neither is ground truth). Soften to informational + question-shape-aware; drop the "high-precision" prescription.
4. **`metabolites_by_gene` `by_element` envelope + `list_metabolites` per-row `elements` semantics docstring.** Today neither field's docstring explicitly says "presence-only, not stoichiometric, not mass-balanced." Surface those constraints. Note: roadmap line 92 names `list_metabolites` as the target, but the `by_element` *envelope* lives on `metabolites_by_gene` (verified §6.4 below); `list_metabolites` carries the per-row `elements` field. Both targets get the clarification.
5. **DROPPED 2026-05-06.** ~~All 8 list/search tools — accept `query=` alongside `search_text=` as ergonomic alias.~~ User judgment: the alias is not justified — adds surface area without empirical pull. The audit observation (scenario 6 `tcdb_chain`) is real but addressable through Field-description hints on the existing `search_text=` kwarg in a future docs-only pass if friction resurfaces. **Phase 3 now ships 5 active items.**
6. **`metabolites_by_gene` summary `top_genes=None` investigation — RESOLVED as analysis-doc fix.** Root cause confirmed 2026-05-05 (Phase 3 ready-to-plan investigation): `MetabolitesByGeneResponse` has no `top_genes` field by design (envelope intentionally has `by_gene` per-input rollup + `top_metabolites` top-non-input rollup). The "summary mode returns top_genes=None" observation came from `chem.get("top_genes")` calls in [analysis/metabolites.md:216](../../multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md#L216) and the build-time plan doc. Fix: update the analysis-doc snippet to use `by_gene`. (Optional MBG docstring disambiguation note dropped per user decision at frozen-spec review 2026-05-05.)

## Out of Scope

- **Pass-through plumbing** (per-row chemistry / measurement counts on 6 tools). Phase 1 — landed on main 2026-05-05.
- **Cross-cutting renames + filter additions** (`search` → `search_text`, `top_pathways` → `top_metabolite_pathways`, `exclude_metabolite_ids`, `direction='both'`). Phase 2 — landed on main 2026-05-05 (fast-forward merge `12c7068..d99784a`).
- **Docstring-only routing hints** on tools outside the compound-anchored family (`genes_by_ontology` TCDB pivot, `pathway_enrichment` / `cluster_enrichment` chemistry routing, `list_derived_metrics` chemistry routing, `gene_details` chemistry section). Roadmap Phase 4.
- **New assay tools.** Roadmap Phase 5.
- **Adding a `by_element` envelope to `genes_by_metabolite` or `list_metabolites`.** The MBG-only placement is intentional (the by-gene-set rollup is the meaningful aggregation; on `list_metabolites` per-row `elements` already carries the same information at the row level). Item 4 is a docstring clarification, not an envelope addition.
- **Adding a `top_genes` field to `MetabolitesByGeneResponse`.** The intentional symmetry (GBM `top_genes` ↔ MBG `top_metabolites` + `by_gene`) is preserved. Item 6 is a docs fix on the consumer side, not a schema change.
- **Augmenting `MetabolitesByGeneResponse` class docstring with a `top_genes`-nonexistence note.** Originally proposed as §6.6 second row; dropped per user decision at frozen-spec review 2026-05-05. The analysis-doc fix is the single authoritative correction; the MBG docstring already names `top_metabolites` as the gene-anchored mirror of GBM's `top_genes` (`tools.py:932`), which is sufficient.
- **`query=` alias on 8 list/search tools.** Originally Item 5; **DROPPED 2026-05-06** per user judgment (not justified — adds surface area without empirical pull). If `query=`-style LLM friction resurfaces, address via Field-description hints on the existing `search_text=` kwarg in a future docs-only pass. The 8 affected tools were `genes_by_function`, `list_publications`, `list_experiments`, `search_ontology`, `search_homolog_groups`, `list_clustering_analyses`, `list_derived_metrics`, `list_metabolites`. The single `query=` on `run_cypher` (Cypher source string) is unaffected.
- **Reaction-arm reversibility *data* — no `is_reversible` property added to KG.** Audit §4.1.2 RESOLVED: KEGG lacks reversibility upstream. The fix is permanent docstring framing, not a future schema extension.
- **Opinionated per-row `evidence_source`-aware shape splitting.** Walkthrough rejected this: union shape with `None`-padding is cleaner than two distinct row classes per arm.

## Status / Prerequisites

- [x] Scope reviewed with user (roadmap Phase 3 line items)
- [x] Phase 1 dependency acknowledged — Phase 3 build starts only after Phase 1 lands and Phase 2 is at minimum at frozen-spec stage. See §10 for sequencing.
- [x] No KG schema changes — all changes are surface-only (verified: no new node/edge/property reads)
- [x] `_GBM_SPARSE_FIELDS` / `_MBG_SPARSE_FIELDS` cross-arm fields enumerated (7 fields each: `transport_confidence`, `reaction_id`, `reaction_name`, `ec_numbers`, `mass_balance`, `tcdb_family_id`, `tcdb_family_name` — verified `api/functions.py:4872-4896`)
- [x] Current warning texts captured for both tools (`api/functions.py:5197-5201` GBM, `:5774-5781` MBG) — see §6.3
- [x] `top_genes=None` root cause investigated 2026-05-05 — confirmed docs bug, not aggregation bug; Phase 3 scope DOES NOT grow per ready-to-plan gate (roadmap line 98)
- [x] Pending decisions in §9 closed
- [ ] Frozen spec approved
- [ ] Ready for Phase 3 build (TDD via 4 file-owned agents)

## KG dependencies

None — Phase 3 is surface + docstring only. No new node/edge/property reads. No KG-side asks.

## Use cases

- **Schema-uniformity for downstream consumers (Item 1).** Today, downstream code that does `row.get("transport_confidence")` works (returns `None`) but `row["transport_confidence"]` raises `KeyError` on metabolism rows. After None-padding, both forms work; result envelopes have predictable per-row shape. Surfaced empirically in scenarios 2 (`compound_to_genes`), 3 (`gene_to_metabolites`), 6 (`tcdb_chain`) which all required arm-specific result-printing logic.
- **Annotation-vs-ground-truth framing (Items 2 + 3).** Both items push the "annotations are not ground truth" reframing into the tool surface itself: reaction-arm rows are "involved in" (no direction, no reversibility), and family_inferred transport tier is a question-shape-dependent annotation (not "low precision"). Avoids LLM consumers misreading reaction-arm rows as flux statements OR aggressively filtering family_inferred when the broad-screen question wants it.
- **Element-rollup semantics (Item 4).** Today the `by_element` rollup on MBG and the per-row `elements` on `list_metabolites` are presence-only — useful for "which gene set hits N-bearing chemistry" but NOT for "stoichiometric mass balance" or "atom count per compound." The docstring update tells consumers which question shape the data supports.
- **Documentation accuracy (Item 6).** The N-source workflow snippet in `analysis/metabolites.md` references a field that doesn't exist; readers (LLM and human) following the snippet would silently get `None`. The fix corrects the field name (`by_gene` instead of `top_genes`); the existing `tools.py:932` MBG docstring (naming `top_metabolites` as "gene-anchored mirror of GBM's `top_genes`") sufficiently disambiguates the field naming convention going forward.

---

## 6. Per-item changes

### 6.1 Item 1 — `genes_by_metabolite` + `metabolites_by_gene` None-padding for cross-arm fields

**Affected tools:** `genes_by_metabolite`, `metabolites_by_gene` (2 tools — share the `GeneReactionMetaboliteTriplet` row class).

**Behavior change:** the api/ layer no longer strips cross-arm fields when null. Every row in `results` carries the full set of cross-arm keys; arm-specific fields are `None` on rows from the other arm.

**Cross-arm fields that move from sparse-stripped → always present:**

| Field | Set on which arm? | None on which arm? |
|---|---|---|
| `reaction_id` | metabolism | transport |
| `reaction_name` | metabolism | transport |
| `ec_numbers` | metabolism | transport |
| `mass_balance` | metabolism | transport |
| `transport_confidence` | transport | metabolism |
| `tcdb_family_id` | transport | metabolism |
| `tcdb_family_name` | transport | metabolism |

**Other sparse fields stay sparse-stripped (no behavior change):**

- `gene_name`, `product` — sparse because the KG has nulls (often null curation).
- `metabolite_formula`, `metabolite_mass`, `metabolite_chebi_id` — sparse for KG-coverage reasons.
- `gene_category`, `metabolite_inchikey`, `metabolite_smiles`, `metabolite_mnxm_id`, `metabolite_hmdb_id`, `reaction_mnxr_id`, `reaction_rhea_ids`, `tcdb_level_kind`, `tc_class_id` — verbose-only fields; sparse-strip when null is the existing convention.

The distinction: cross-arm fields are *deterministically* null on rows from the other arm (a metabolism row will never have a `tcdb_family_id`); coverage-driven fields are *probabilistically* null. The walkthrough decision keeps the latter sparse and surfaces the former.

**Files touched:**

| Layer | File | Lines | Change |
|---|---|---|---|
| API | `multiomics_explorer/api/functions.py` | 4872-4896 (`_GBM_SPARSE_FIELDS` definition) | Remove the 7 cross-arm fields from `_GBM_SPARSE_FIELDS`. New tuple: `("gene_name", "product", "metabolite_formula", "metabolite_mass", "metabolite_chebi_id", <verbose fields>)`. |
| API | `multiomics_explorer/api/functions.py` | 5246 (`_MBG_SPARSE_FIELDS = _GBM_SPARSE_FIELDS`) | No change — alias picks up the new tuple automatically. Verify alias still holds after edit. |
| Pydantic models | `multiomics_explorer/mcp_server/tools.py` | 481-510 (row-class docstring); 513-541 (per-field descriptions for cross-arm fields) | Update class docstring to remove "All per-arm-specific fields are Optional and **sparse-stripped at the api/ layer when null**"; replace with "All per-arm-specific fields are Optional and explicitly `None` on rows from the other arm — every row carries identical keys." Update each cross-arm field's `description` to clarify "None on metabolism rows" / "None on transport rows" remains accurate (already says this). |
| Tool docstrings | `multiomics_explorer/mcp_server/tools.py` | 7187 (`metabolites_by_gene` doc); 7349 (`genes_by_metabolite` doc) | Add a "Per-row schema" / "Union shape" sentence to each tool's MCP docstring stating: "Every row carries the full cross-arm key set; metabolism-arm rows have `transport_confidence`/`tcdb_family_id`/`tcdb_family_name` = None, transport-arm rows have `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance` = None." |
| About content | `inputs/tools/{genes_by_metabolite,metabolites_by_gene}.yaml` | — | Update at least one example response to show the union shape (cross-arm None values present). New mistake entry per tool: "Every result row has the same key set — cross-arm fields are explicitly `None` on rows from the other arm. Use `row['transport_confidence']` (KeyError-free) rather than `row.get('transport_confidence')` if the difference matters." Regenerate via `build_about_content.py`. |
| Tests | `tests/unit/test_api_functions.py` | `TestGenesByMetabolite`, `TestMetabolitesByGene` | New `test_cross_arm_fields_none_padded` per tool: assert metabolism rows have `transport_confidence is None` (key present, value None) and `tcdb_family_id is None`; assert transport rows have `reaction_id is None`, `reaction_name is None`, `ec_numbers is None`, `mass_balance is None`. Existing tests that depended on sparse-stripping (e.g., assertions that a metabolism row has only metabolism keys) need updating — find via grep on `assert.*not in.*tcdb` / `assert.*not in.*reaction`. |
| Tests | `tests/unit/test_tool_wrappers.py` | `TestGenesByMetaboliteWrapper`, `TestMetabolitesByGeneWrapper` | Pydantic round-trip already tolerates None on Optional fields (no change needed); add an assertion that the serialized envelope contains None values explicitly (not stripped via `.model_dump(exclude_none=True)` on the response path). |
| Regression | `tests/regression/` | — | Will trigger fixture mismatches on every GBM / MBG fixture (rows now wider). Run `pytest tests/regression/ --force-regen -m kg -q` after the build. |

**Validation:**

- Existing `test_returns_dict_envelope` and similar shape tests pass (envelope keys unchanged).
- New `test_cross_arm_fields_none_padded` passes.
- `model_dump()` of every row contains all 7 cross-arm keys (some with value `None`); a metabolism row has 3 transport-arm `None` values (`transport_confidence`, `tcdb_family_id`, `tcdb_family_name`); a transport row has 4 metabolism-arm `None` values (`reaction_id`, `reaction_name`, `ec_numbers`, `mass_balance`). Non-cross-arm sparse fields (`gene_name`, `product`, `metabolite_formula`, `metabolite_mass`, `metabolite_chebi_id`, plus 9 verbose-only fields) continue to strip when null per existing convention — actual row width therefore varies. Verbose adds additional fields per existing convention.
- Sort key `_gbm_sort_key` (and `_mbg_sort_key`) at `functions.py:4899` continues to use `row.get("transport_confidence")` — already None-tolerant; no change.

**Migration risk:** consumers that did `if "transport_confidence" in row: ...` for arm-detection will now see the key on every row and have to switch to `if row["transport_confidence"] is not None: ...`. Mitigated by the about-content mistake entry. No external consumers exist (explorer surface not yet shipped to outside).

---

### 6.2 Item 2 — Reaction-arm reversibility framing on `genes_by_metabolite` + `metabolites_by_gene`

**Affected tools:** `genes_by_metabolite`, `metabolites_by_gene` (2 tools — share `GeneReactionMetaboliteTriplet`).

**No code change.** Pure docstring + about-content + analysis-doc edits.

**Canonical phrasing (lock at spec freeze):** *"Reaction edges are undirected AND carry no reversibility flag — interpret all reaction-arm rows as 'involved in', never 'produces' / 'consumes' / 'reversible'. (KG limitation: KEGG-anchored reactions lack both direction and `is_reversible`; see audit §4.1.1 + §4.1.2.)"*

**Where the phrasing lands:**

| Layer | File | Lines | Change |
|---|---|---|---|
| Row class docstring | `multiomics_explorer/mcp_server/tools.py` | 481-487 (`GeneReactionMetaboliteTriplet` class docstring) | Add the canonical phrasing as a new paragraph after the "Compact mode: 15 fields..." sentence. |
| Field description | `multiomics_explorer/mcp_server/tools.py` | 513-516 (`reaction_id` Field description); 517-521 (`reaction_name` Field description) | Suffix to existing descriptions: "Metabolism rows only — see class-level note on undirected, non-reversible interpretation." |
| Tool docstring | `multiomics_explorer/mcp_server/tools.py` | `genes_by_metabolite` MCP tool docstring (~7349) and `metabolites_by_gene` MCP tool docstring (~7187) | Add a "Reaction-arm framing" paragraph before the Args block: the canonical phrasing verbatim. |
| About content | `inputs/tools/{genes_by_metabolite,metabolites_by_gene}.yaml` | — | New mistake entry per tool: "Reaction-arm rows are NOT directional — KG reactions carry neither a substrate-vs-product role on `Reaction_has_metabolite` nor an `is_reversible` flag. Read `evidence_source='metabolism'` rows as 'gene catalyses a reaction *involving* this metabolite,' never as 'produces X' / 'consumes Y' / 'reversibly interconverts'. The KG limitation is permanent (KEGG lacks both upstream)." Regenerate via `build_about_content.py`. |
| Analysis doc | `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md` | Track A1 caveat section (search for "involved in" or "directional") | Extend the existing Track A1 direction caveat to also call out the reversibility gap. The audit text says "Analysis doc Track A1 caveat must be extended to call out the reversibility gap alongside the existing direction caveat." Single sentence addition, same paragraph. |

**Validation:**

- `build_about_content.py` regenerates cleanly.
- `metabolites.md` analysis doc renders cleanly (manual visual check; no test).
- No code-level test (docstring change has no behavioral effect).

---

### 6.3 Item 3 — family_inferred-dominance warning rewrite on `genes_by_metabolite` + `metabolites_by_gene`

**Affected tools:** `genes_by_metabolite`, `metabolites_by_gene` (2 tools, but the warning text differs slightly between them today — see below).

**Current GBM warning (`api/functions.py:5197-5201`):**

```python
warnings.append(
    "Majority of transport rows are family_inferred (rolled-up "
    "from broad TCDB families). Re-run with "
    "transport_confidence='substrate_confirmed' for "
    "substrate-curated transporter genes only."
)
```

**Current MBG warning (`api/functions.py:5774-5781`):**

```python
warnings.append(
    f"Transport rows in this slice are dominated by "
    f"`family_inferred` rollup ({transport_fi_total} of "
    f"{transport_fi_total + transport_sc_total} transport rows). "
    "For high-precision substrate-curated annotations only, set "
    "`transport_confidence='substrate_confirmed'` and/or "
    "`evidence_sources=['transport']`."
)
```

Both warnings prescribe `substrate_confirmed` as a "high-precision" remediation. Per audit §g (analysis doc), this framing is wrong: both tiers are annotations, neither is ground truth. The warning text predates that reframing.

**New warning text (both tools, symmetric — lock at spec freeze):**

```python
warnings.append(
    f"Most transport rows are `family_inferred` ({fi_count} of "
    f"{fi_count + sc_count}) — annotations rolled up from "
    "family-level transport potential. Workflow-dependent: use "
    "`transport_confidence='substrate_confirmed'` for "
    "conservative-cast questions (e.g. cross-organism inference); "
    "keep `family_inferred` for broad-screen candidate enumeration. "
    "Both tiers are annotations, neither is ground truth — see "
    "analysis-doc §g."
)
```

(`fi_count` = `transport_fi_total`; `sc_count` = `transport_sc_total`. F-string formatting kept for inline counts.)

**Symmetry decision:** GBM and MBG warnings now use identical phrasing (modulo the per-tool count variables). Today GBM lacks the inline count; MBG includes it. Standardize on MBG's "X of Y" inclusion — more informative, no cost.

**Files touched:**

| Layer | File | Lines | Change |
|---|---|---|---|
| API | `multiomics_explorer/api/functions.py` | 5197-5201 (GBM warning); 5774-5781 (MBG warning) | Replace both with the new symmetric phrasing. |
| Tests | `tests/unit/test_api_functions.py` | `TestGenesByMetabolite::test_family_inferred_warning_emitted` (and MBG counterpart) | Update string-match assertions to the new text. |
| Tests | `tests/unit/test_tool_wrappers.py` | — | If any test asserts on the warning string, update. |
| About content | `inputs/tools/{genes_by_metabolite,metabolites_by_gene}.yaml` | — | If any example response shows the warning string, update. **Replace** the existing mistake entry (the "treat family_inferred as low-precision" framing) with a new entry using workflow-dependent framing per audit §g. Single mistake entry per tool — net change is zero new entries, one rewrite. |
| Analysis doc | `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md` | §g framing section | Verify the §g section is consistent with the new warning. Audit walkthrough already updated this in Pass A; cross-check at edit time. |

**Drop A7 `precision_tier` scenario.** Audit row 382 says: "Drop A7 `precision_tier` scenario — A6 + §g already cover this teaching." Verified live 2026-05-05: `precision_tier` IS still present in `examples/metabolites.py` (`--scenario` choices: `compound_to_genes`, `cross_feeding`, `discover`, `gene_to_metabolites`, `measurement`, `n_source_de`, `precision_tier`, `tcdb_chain`). It must be removed as part of Phase 3 — see Files-touched table below. Files affected:

| Layer | File | Change |
|---|---|---|
| Examples | `multiomics_explorer/examples/metabolites.py` | Delete `def scenario_precision_tier()` function body. Remove `'precision_tier'` from the `--scenario` argparse choices. Remove its dispatch entry in the scenarios dict. Remove the docstring header line listing it. |
| Examples test | `tests/integration/test_examples.py` (or wherever per-scenario invocations are tested) | If the integration test enumerates scenarios via parametrize, drop `precision_tier`. |
| Analysis doc | `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md` | Remove any reference to A7 / `precision_tier` scenario; cross-check that A6 + §g coverage is intact (audit walkthrough already updated this in Pass A — verify at edit time). |

**Validation:**

- New warning string contains no "high-precision" prescription.
- Both tools emit identical warning text (modulo count variables).
- Existing `test_family_inferred_warning_emitted` assertions updated.
- KG-integration test for the warning trigger threshold (transport_fi_total > transport_sc_total) unchanged — only the message text changed, not the trigger logic.

---

### 6.4 Item 4 — `by_element` envelope semantics + `list_metabolites` per-row `elements` semantics docstring

**Affected tools:** `metabolites_by_gene` (envelope `by_element`), `list_metabolites` (per-row `elements`). Two surfaces, one semantic clarification.

**No code change.** Pure docstring + about-content edits.

**Verified placement (live code 2026-05-05):**
- `MbgByElement` Pydantic class at `multiomics_explorer/mcp_server/tools.py:933-947`.
- `MbgByElement.metabolite_count` field description at `tools.py:945-947`.
- `MetabolitesByGeneResponse.by_element` envelope-key description at `tools.py:1166-1170`.
- `list_metabolites` row class `elements` field at `tools.py:400`.
- **`genes_by_metabolite` does NOT carry `by_element`** (verified — Item 4 affects 2 tools, not 3, despite audit row 381 mentioning GBM).

**Canonical phrasing (lock at spec freeze):** *"Presence-only — count of distinct compounds containing each element at all. NOT stoichiometric (no atom counts per compound; stoichiometry lives in `metabolite.formula`). NOT mass-balanced (KG carries no substrate-vs-product role on `Reaction_has_metabolite`, see audit §4.1.1)."*

**Files touched:**

| Layer | File | Lines | Change |
|---|---|---|---|
| Pydantic — MBG envelope | `multiomics_explorer/mcp_server/tools.py` | 1166-1170 (`MetabolitesByGeneResponse.by_element` envelope-key Field description) | Append the canonical phrasing to the existing description. |
| Pydantic — MBG row | `multiomics_explorer/mcp_server/tools.py` | 933-947 (`MbgByElement` class docstring + `metabolite_count` Field description) | Append the canonical phrasing to the class docstring. |
| Pydantic — `list_metabolites` row | `multiomics_explorer/mcp_server/tools.py` | 400 (`elements` Field description on the metabolite row class) | Append "Presence list (no atom counts; stoichiometry lives in `formula`)." |
| Tool docstrings | `multiomics_explorer/mcp_server/tools.py` | `metabolites_by_gene` MCP tool docstring (around 7187); `list_metabolites` MCP tool docstring (around 7075) | Add a one-line summary of the semantics in the docstring args/notes block where `by_element` / `elements` are first mentioned. |
| About content | `inputs/tools/{metabolites_by_gene,list_metabolites}.yaml` | — | New mistake entry per tool: "`by_element` / `elements` is presence-only — counts of distinct compounds containing each element at all. NOT stoichiometric (atom counts live in `metabolite.formula`); NOT mass-balanced (KG `Reaction_has_metabolite` is undirected and carries no substrate/product role)." Regenerate via `build_about_content.py`. |

**Validation:**

- `build_about_content.py` regenerates cleanly.
- No test changes (docstring-only).

---

### 6.5 Item 5 — DROPPED 2026-05-06

~~`query=` alias on all 8 list/search tools.~~

**Status: DROPPED 2026-05-06** by user decision after frozen-spec re-review. Initial decision (2026-05-05) was option (c) — add the alias bidirectionally on all 8 tools. Reversed 2026-05-06: the alias adds surface area without empirical pull, and any `query=`-style LLM friction can be addressed via Field-description hints on the existing `search_text=` kwarg in a future docs-only pass if it ever resurfaces.

**No code, test, YAML, or doc changes for Item 5.** The 8 tools that take `search_text=` (`genes_by_function`, `list_publications`, `list_experiments`, `search_ontology`, `search_homolog_groups`, `list_clustering_analyses`, `list_derived_metrics`, `list_metabolites`) keep the canonical kwarg unchanged. The single `query=` on `run_cypher` (Cypher source string) is unaffected.

Audit row 377 remains an open observation; if `query=`-style friction is empirically observed in production usage post-Phase-3, revisit as a separate slice. Default response would be Field-description hinting (no alias), not the helper-mediated alias originally spec'd here.

---

### 6.6 Item 6 — `metabolites_by_gene` summary `top_genes=None` → analysis-doc fix

**Resolved during Phase 3 ready-to-plan investigation (2026-05-05).** Root cause: `MetabolitesByGeneResponse` has no `top_genes` field by design. The gene-anchored axis is `by_gene` (full per-input rollup) and `top_metabolites` (top non-input-axis); GBM's `top_genes` ↔ MBG's `top_metabolites` is the intentional symmetry (verified at `tools.py:932`). The "summary mode returns `top_genes=None`" observation came from `chem.get("top_genes", [])` calls in the analysis-doc snippet and the build-time plan doc, where the field never existed.

**No tool-side change.** Item 6's investigation was the gate; the gate confirmed the original 6-item Phase 3 scope holds. User decision at frozen-spec review 2026-05-05: drop the optional MBG docstring touch — the analysis-doc fix alone is sufficient (MBG class already names `top_metabolites` as "gene-anchored mirror of GBM's `top_genes`" at `tools.py:932`).

**Files touched (single-line edit, analysis-doc only):**

| Layer | File | Lines | Change |
|---|---|---|---|
| Analysis doc | `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md` | 216 (only authoritative reference) | Replace `chem["top_genes"]` with `chem["by_gene"]`. The `by_gene` per-input rollup carries `locus_tag`, `metabolite_count`, `reaction_count`, etc. — exactly the gene set the N-source workflow snippet needs. |

**Plan-doc historical references** at `docs/superpowers/plans/2026-05-04-metabolites-assets.md:739` and `:1423` are intentionally left as-is — those files are historical breadcrumbs of the build process, not authoritative documentation.

**About-content not affected.** No new mistake entry on `metabolites_by_gene.yaml` — the existing class docstring is judged sufficient.

**Validation:**

- `analysis/metabolites.md` snippet runs cleanly when manually traced (`chem["by_gene"]` exists; iterating returns the full input rollup).
- No test changes (docs-only).

---

## 7. Implementation file map (Mode B parallel build)

Per the `add-or-update-tool` skill Phase 2 file-ownership convention. Each agent gets one file; items spread across all 4 agents.

| Agent | File | Items touched |
|---|---|---|
| `query-builder` | `multiomics_explorer/kg/queries_lib.py` | None — Phase 3 has no Cypher changes. (Agent NOT dispatched for Phase 3 unless Phase 1's `--force-regen` run surfaces a query-builder regression that Phase 3 inherits. Verify before dispatch.) |
| `api-updater` | `multiomics_explorer/api/functions.py` | 6.1 (`_GBM_SPARSE_FIELDS` reduction); 6.3 (warning string replacements at GBM warning site + MBG warning site). |
| `tool-wrapper` | `multiomics_explorer/mcp_server/tools.py` | 6.1 (Pydantic class docstring + tool docstring None-padding paragraph for GBM + MBG); 6.2 (reaction-arm reversibility framing in `GeneReactionMetaboliteTriplet` + tool docstrings for GBM + MBG); 6.4 (`by_element` semantics in `MbgByElement` + `MetabolitesByGeneResponse.by_element` envelope-key Field + `list_metabolites` row `elements` Field). |
| `doc-updater` | `multiomics_explorer/inputs/tools/{genes_by_metabolite,metabolites_by_gene,list_metabolites}.yaml` + `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md` + `multiomics_explorer/examples/metabolites.py` (precision_tier scenario removal — Item 6.3) + `tests/integration/test_examples.py` if it parametrizes scenarios + `CLAUDE.md` | About-content for 3 YAMLs total (the 3 compound-anchored tools touched by items 6.1-6.4). Regen via `build_about_content.py`. Analysis-doc edits: Track A1 reversibility extension (6.2) + analysis-doc snippet correction `chem["top_genes"]` → `chem["by_gene"]` at line 216 (6.6) + drop A7 / `precision_tier` references (6.3). Examples edit: drop `scenario_precision_tier` function + argparse choice + dispatch dict entry (6.3). CLAUDE.md tool-table touch-ups for items 6.1-6.4 affected rows. |

**Anti-scope-creep guardrail (mandatory in every brief):** "DOCSTRING + Field-description edits dominate this phase. Code changes are: (a) sparse-field tuple reduction (1 edit); (b) two warning string replacements (2 edits). DO NOT modify any unrelated test, case, or yaml. If an unrelated test fails in your environment, REPORT AS A CONCERN; do not silently retune. The 7-field None-padding does NOT add behavior — Pydantic class already declares `default=None` on every cross-arm field; only the api/-layer sparse-strip is reduced. **Item 5 (`query=` alias) is DROPPED — do NOT touch any list/search-tool kwarg signature.**"

**Mode B briefing addendum:** "For Item 6.1, implement `genes_by_metabolite` as the template (one tuple edit + one row-class docstring update); then verify `metabolites_by_gene` inherits via `_MBG_SPARSE_FIELDS = _GBM_SPARSE_FIELDS` (line 5246) — single-line check, no per-tool extension needed. For Item 6.3, update both warning strings symmetrically — no per-tool drift. **Plus drop the A7 `precision_tier` scenario** in `examples/metabolites.py` + analysis doc + integration test parametrize (audit row 382)."

---

## 8. Test cases (one slice per layer)

All test patterns follow the `testing` skill conventions. New tests are **additions** to existing test classes — no rebaseline of existing assertions (except Item 6.1 which removes assertions on stripped keys).

### Query builder tests (`tests/unit/test_query_builders.py`)

None — Phase 3 has no Cypher changes.

### API tests (`tests/unit/test_api_functions.py`)

| Item | Test addition |
|---|---|
| 6.1 | `TestGenesByMetabolite.test_cross_arm_fields_none_padded` — assert metabolism rows have `transport_confidence is None`, `tcdb_family_id is None`, `tcdb_family_name is None` (keys present); transport rows have `reaction_id is None`, `reaction_name is None`, `ec_numbers is None`, `mass_balance is None`. Mirror for `TestMetabolitesByGene`. **Update existing tests** that asserted "key absent" on cross-arm fields — find via grep on `assert.*not in.*tcdb`, `assert.*not in.*reaction` in the GBM/MBG test classes. |
| 6.3 | `TestGenesByMetabolite.test_family_inferred_warning_text` — assert new warning text format. Mirror for `TestMetabolitesByGene`. Verify both contain identical phrasing modulo count variables. |
| 6.5 | DROPPED 2026-05-06 — no test additions. |

### Tool wrapper tests (`tests/unit/test_tool_wrappers.py`)

| Item | Test addition |
|---|---|
| 6.1 | `TestGenesByMetaboliteWrapper.test_envelope_serializes_none_cross_arm_fields` — assert `model_dump()` of a metabolism row contains `transport_confidence: None`, `tcdb_family_id: None`, `tcdb_family_name: None` (NOT stripped). Mirror for MBG. |
| 6.5 | DROPPED 2026-05-06 — no test additions. |

`EXPECTED_TOOLS` registry: no changes (Item 5 dropped). `TOOL_BUILDERS` registry: untouched.

### KG-integration tests (`tests/integration/`, marked `@pytest.mark.kg`)

| Item | Test |
|---|---|
| 6.1 | Round-trip per tool: `genes_by_metabolite(metabolite_ids=['kegg.compound:C00080'], organism='MED4')` returns rows with both metabolism and transport `evidence_source` values; assert metabolism rows carry `transport_confidence is None` and transport rows carry `reaction_id is None` (keys present, values None). Mirror for MBG. |
| 6.3 | Round-trip per tool: pick a metabolite where transport is family_inferred-dominated (e.g., a generic ChEBI ID with broad ABC-family annotations); assert the warning string in the response matches the new phrasing. |
| 6.5 | DROPPED 2026-05-06 — no KG-integration tests. |

### Regression tests (`tests/regression/`)

The Item 6.1 None-padding will trigger fixture mismatches on every GBM and MBG fixture — rows now wider by 3-4 None keys. Item 6.3 changes warning text; any fixture capturing the warning string needs regen.

Run `pytest tests/regression/ --force-regen -m kg -q` to refresh, then `pytest tests/regression/ -m kg -q` to verify clean.

**Add explicit regression assertions** locking the new shape:

- One regression case per tool (GBM + MBG) asserting every result row has all 7 cross-arm keys present (some `None`); a metabolism row has `transport_confidence`/`tcdb_family_id`/`tcdb_family_name` all `None`; a transport row has `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance` all `None`. Non-cross-arm sparse fields continue to strip — actual row width varies fixture-to-fixture, so DON'T assert on a single field count.
- One regression case per tool asserting the new warning text on a known family_inferred-dominated input.

### Docstring / analysis-doc tests

None enforceable in pytest — manual visual verification at PR review time.

---

## 9. Open questions / pending decisions

All resolved as of frozen-spec review 2026-05-05.

- [x] **Item 1 walkthrough decision.** APPROVED 2026-05-05 — surface explicit None for cross-arm fields, document union shape.
- [x] **Item 2 walkthrough decision.** APPROVED 2026-05-05 — extend reaction-arm docstring with reversibility framing; analysis-doc Track A1 caveat extended.
- [x] **Item 3 walkthrough decision.** APPROVED 2026-05-05 — soften family_inferred-dominance warning to question-shape-aware framing; drop "high-precision" prescription.
- [x] **Item 4 confirmation.** APPROVED at frozen-spec review 2026-05-05 — proceed with `by_element` / `elements` semantics docstring edits as spec'd in §6.4. Pure docstring; low risk.
- [x] **Item 5 — DROPPED 2026-05-06.** Initial decision (2026-05-05) was option (c) — add `query=` alias bidirectionally on all 8 list/search tools. Reversed 2026-05-06: not justified — alias adds surface area without empirical pull. Audit row 377 stays as a future-pass observation; if friction resurfaces, address via Field-description hinting on the existing `search_text=` kwarg (no alias). The reserved-keyword verification work (`query` is NOT Cypher / MCP / Pydantic reserved; already used on `run_cypher` per `tools.py:2079`) is preserved here as record but moot for Phase 3.
- [x] **Item 6 root cause.** Investigated 2026-05-05 (Phase 3 ready-to-plan gate) — confirmed docs bug, scope does not grow.
- [x] **Item 6 docstring scope.** DROPPED at frozen-spec review 2026-05-05 — analysis-doc one-line edit is the single authoritative correction; the optional MBG class-docstring disambiguation note is dropped. Existing `tools.py:932` docstring naming `top_metabolites` as "gene-anchored mirror of GBM's `top_genes`" is judged sufficient.

---

## 10. Phase 1 + Phase 2 interaction (build sequencing)

**Phase 3 build is unblocked: both predecessor phases have landed on main 2026-05-05.** Phase 1 landed first; Phase 2 landed via fast-forward merge `12c7068..d99784a` (4 commits). The §6 file:line references below were captured at the spec-freeze main HEAD (pre-Phase-1 + pre-Phase-2 for the relevant sections), so **most line numbers are now stale** — Phase 1 + Phase 2 already shifted them. Use anchor patterns over fixed line numbers — see §10 implementation-plan Step 0.

**File:line shifts already in effect from Phases 1 + 2.** The implementation plan (writing-plans output) must use **anchor patterns** rather than fixed line numbers — e.g., "in `_GBM_SPARSE_FIELDS` tuple definition" rather than "at `api/functions.py:4872`". Specific overlap zones (now historical, since both predecessor phases have landed):

| File | Phase 1 + 2 changes that shift Phase 3 anchors |
|---|---|
| `multiomics_explorer/mcp_server/tools.py` | Phase 1 expands `MetabolitesByGeneResponse` if it adds chemistry fields (verify — Phase 1 spec §6.1 doesn't list MBG response, so likely unaffected). Phase 2 renames `top_pathways` → `top_metabolite_pathways` on `ListMetabolitesResponse` and `MetabolitesByGeneResponse` envelope keys, and renames `MetTopPathway.pathway_id` → `metabolite_pathway_id` on the per-element class (verified Phase 2 spec §6.2). Phase 3 docstring edits land in different parts of the file (row class `GeneReactionMetaboliteTriplet`, `MbgByElement`, `search_ontology` Annotated params); no expected merge conflict. Adjacent line numbers shift; field-rename targets are stable by name. |
| `multiomics_explorer/api/functions.py` | Phase 1 extends 6 list-tool API signatures (per Phase 1 §6.2-6.6). Phase 2 adds `exclude_metabolite_ids` on 3 compound-anchored tools and `direction='both'` on DE (per Phase 2 §6.3-6.4). Phase 3's two code edit types (post-Item-5 drop) — (a) `_GBM_SPARSE_FIELDS` tuple at line 4872-4896 and (b) GBM warning at 5197-5201 + MBG warning at 5774-5781 — are in disjoint sections from Phase 1 + Phase 2. No expected conflict. |
| `multiomics_explorer/inputs/tools/genes_by_metabolite.yaml` | Phase 1 does not touch this YAML; Phase 2 adds `exclude_metabolite_ids` example/mistake. Phase 3 adds None-padding mistake + reversibility-framing mistake + family_inferred-warning replacement (drops old "high-precision" mistake). Section-level edits — should rebase cleanly. |
| `multiomics_explorer/inputs/tools/metabolites_by_gene.yaml` | Phase 1 does not touch this YAML; Phase 2 owns `top_pathways` → `top_metabolite_pathways` rename + `exclude_metabolite_ids` addition. Phase 3 adds None-padding mistake + reversibility-framing mistake + family_inferred-warning replacement + `by_element` semantics mistake. (No `top_genes`-nonexistence mistake — Item 6.6 second-row docstring touch was DROPPED at frozen-spec review 2026-05-05; analysis-doc fix alone is sufficient.) |
| `multiomics_explorer/inputs/tools/list_metabolites.yaml` | Phase 1 adds new examples + mistakes for measurement-rollup pass-through. Phase 2 owns `search` → `search_text` rename + `top_pathways` rename + `exclude_metabolite_ids` addition. Phase 3 adds one new mistake entry: Item 6.4 `elements` per-row semantics mistake. (Item 6.5 `query=` alias DROPPED — no longer touches this YAML.) Section-level edits — rebases cleanly. |
| `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md` | Phase 1 + Phase 2 do not touch this analysis doc; Phase 3 owns Track A1 reversibility extension (Item 6.2) and `chem["top_genes"]` → `chem["by_gene"]` correction (Item 6.6, single-line). |
| `tests/regression/` | Phase 1 regenerates fixtures for 6 tools. Phase 2 regenerates fixtures for 2 envelope-rename tools + DE. Phase 3 regenerates fixtures for GBM + MBG only (rows widened by None-padding) — Item 6.5's 8-tool surface change is dropped. Run order: one `--force-regen` invocation after the Phase 3 build, then verify clean. |

**Implementation plan must include:**

1. **Step 0 — Phase 1 + Phase 2 still on main.** Both phases landed on main 2026-05-05 (Phase 2 via fast-forward `12c7068..d99784a`). Defensive check before opening the Phase 3 worktree: confirm both are still on main (`git log --oneline main | head -20` should show the Phase 2 merge SHA at or near top). If either has been reverted or force-pushed off, halt — Phase 3 assumes both predecessor surfaces are present.
2. **Worktree baseline check.** Per `add-or-update-tool` skill Phase 2 guidance: `EnterWorktree` re-uses existing branch by name; verify worktree HEAD == main HEAD before dispatching agents.
3. **Anchor patterns over line numbers.** Brief each implementer agent to use grep / function-name anchors when locating edit sites. The §6 line numbers are spec-freeze artifacts.
4. **Single regression regen pass.** Don't double-regen. After all 3 implementer agents (no query-builder agent for Phase 3) report green and code review passes, one `--force-regen` invocation, then verify clean.

---

## 11. Acceptance criteria

- All 5 active items land per §6.1, §6.2, §6.3, §6.4, §6.6. (Item 5 §6.5 was DROPPED 2026-05-06; ship Phase 3 with Items 1, 2, 3, 4, 6 only.)
- Item 6.1: every GBM / MBG result row carries all 7 cross-arm keys (some `None` per arm); cross-arm fields are explicitly `None` on rows from the other arm (metabolism row → `transport_confidence`/`tcdb_family_id`/`tcdb_family_name` all `None`; transport row → `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance` all `None`); non-cross-arm sparse fields (`gene_name`, `product`, `metabolite_formula`, `metabolite_mass`, `metabolite_chebi_id`, plus 9 verbose-only) continue to be sparse-stripped per existing convention.
- Item 6.2: row class + field descriptions + tool docstrings + about-content YAML + analysis doc Track A1 all carry the canonical reversibility-framing phrasing.
- Item 6.3: GBM and MBG warnings emit identical text (modulo count variables); no occurrence of "high-precision" prescription remains in either warning; analysis-doc §g framing is consistent.
- Item 6.4: `MbgByElement` + `MetabolitesByGeneResponse.by_element` + `list_metabolites` row `elements` all carry the canonical "presence-only, not stoichiometric, not mass-balanced" phrasing.
- Item 6.5: DROPPED 2026-05-06 — no acceptance criterion. The 8 list/search tools' `search_text=` kwarg is unchanged; no new alias surface.
- Item 6.6: `analysis/metabolites.md:216` no longer references `chem["top_genes"]`. (MBG class-docstring disambiguation note dropped per user decision; not in scope.)
- All unit + KG-integration tests pass (3 pytest invocations: `tests/unit/`, `tests/integration/ -m kg`, `tests/regression/ -m kg`).
- Regression fixtures regenerated and locked (one explicit regression assertion per tool: GBM full-key-set, MBG full-key-set, new GBM warning text, new MBG warning text).
- Code review (hard gate per `add-or-update-tool` skill Stage 3) passes — particular attention to:
  - The `_GBM_SPARSE_FIELDS` reduction removes ONLY the 7 cross-arm fields; non-cross-arm sparse fields (gene_name, product, formula/mass/chebi, verbose-only) remain in the tuple.
  - The new warning text is byte-identical between GBM and MBG (modulo count variable names).
  - No `query=` kwarg added to any of the 8 search-aware tools (Item 5 dropped — confirm via `git grep "query.*Annotated\|query: str"` showing no new occurrences in `mcp_server/tools.py` or `api/functions.py` outside `run_cypher`).
  - No `top_genes` references remain in `analysis/metabolites.md`; plan-doc historical references at `docs/superpowers/plans/2026-05-04-metabolites-assets.md:739/1423` are intentionally untouched.
  - No MBG class-docstring change for the `top_genes` non-existence note (dropped per §9 user decision).
- About-content YAML edits regenerate cleanly via `build_about_content.py`.
- `CLAUDE.md` tool-table rows for the affected tools reflect changes where row prose mentions warning text, row shape, or element semantics. Items 6.1-6.4: rows for `genes_by_metabolite`, `metabolites_by_gene`, `list_metabolites`. (Item 6.5 dropped — no CLAUDE.md edits for the 8 search-aware tool rows.)
- `examples/metabolites.py` no longer carries the `precision_tier` scenario (Item 6.3 cleanup); `--scenario` choices now: `compound_to_genes`, `cross_feeding`, `discover`, `gene_to_metabolites`, `measurement`, `n_source_de`, `tcdb_chain` (7 scenarios).
