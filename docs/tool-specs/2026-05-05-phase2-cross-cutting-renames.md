# Tool spec: Phase 2 — Cross-cutting renames + filter additions (metabolites surface refresh)

**Date:** 2026-05-05.
**Roadmap:** [docs/superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md](../superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md) — Phase 2.
**Phase 1 spec (predecessor):** [docs/tool-specs/2026-05-05-phase1-pass-through-plumbing.md](2026-05-05-phase1-pass-through-plumbing.md).
**Audit:** [docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md](../superpowers/specs/2026-05-04-metabolites-surface-audit.md) — Part 2 build-derived P1 cross-cutting (`top_pathways` rename), P2 (`search_text` rename), P2 cross-cutting (`exclude_metabolite_ids`), P2 (`direction='both'`).
**Walkthrough decisions:** 2026-05-05 Q&A — all 4 items APPROVED.

## Mode

**Mode B (cross-tool small change).** Spec lists 4 tools and 4 items; no KG iteration (surface-only); Phase 2 build briefing instructs each implementer "do tool 1 as template, extend to N within your file." Items are bundled because they share testing scaffolding (regression-fixture regen + about-content regen) and breaking-change ergonomics.

## Purpose

Lock in the breaking-but-controlled API changes that the audit flagged while the call-site count is still small. The audit reports 2 internal call sites for `search` → `search_text` (verified live: `examples/metabolites.py:127`, `tests/unit/test_api_functions.py:6850`); the `top_pathways` rename has a similarly small footprint (envelope keys appear in 2 query builders, 2 Pydantic models, 1 API test fixture, 1 regression baseline). Delaying these makes them costlier as the call-site count grows after the metabolites surface stabilizes.

The 4 items are:

1. `list_metabolites` — rename `search` → `search_text` for consistency with the 7 other list/search tools that already use `search_text`.
2. `list_metabolites` + `metabolites_by_gene` — rename envelope `top_pathways` → `top_metabolite_pathways` and the per-element keys `pathway_id` / `pathway_name` → `metabolite_pathway_id` / `metabolite_pathway_name` to disambiguate metabolite-pathway-rollup from KO-pathway-annotation (Option A naming convention from audit Part 2).
3. `list_metabolites` + `metabolites_by_gene` + `genes_by_metabolite` — add `exclude_metabolite_ids: list[str] | None = None` parameter (primitive negative filter mirroring `metabolite_ids` include semantics). Pushes audit §4.5 confounder #1 (currency-cofactor flooding) mitigation into the tool layer.
4. `differential_expression_by_gene` — accept `direction='both'` (matches `pathway_enrichment` convention; functionally equivalent to today's `direction=None, significant_only=True` — added for API discoverability, not new behavior).

## Out of Scope

- **Pass-through plumbing** (per-row chemistry / measurement counts on 6 tools). Phase 1 — already in flight on worktree `metabolites-phase1-plumbing`.
- **Compound-anchored tightening** (union-shape `None` padding on `metabolites_by_gene` / `genes_by_metabolite` rows, family_inferred warning rewrite, reversibility docstring, `by_element` semantics, `search_ontology` kwarg alias, `metabolites_by_gene` summary `top_genes=None` investigation). Roadmap Phase 3.
- **Docstring-only routing hints** (`genes_by_ontology` TCDB pivot, `pathway_enrichment` / `cluster_enrichment` chemistry routing, `list_derived_metrics` chemistry routing, `gene_details` chemistry section). Roadmap Phase 4.
- **New assay tools.** Roadmap Phase 5.
- **Backwards-compatibility aliasing.** All four renames are pure (no deprecated alias period). User decision 2026-05-05: the call-site count is small enough that a deprecation period adds churn without value.
- **Opinionated `exclude_currency_cofactors=True` default on `exclude_metabolite_ids`.** Roadmap §5 DEFER — start with the primitive list-of-IDs param; escalate only if callers re-discover the flooding pattern.

## Status / Prerequisites

- [x] Scope reviewed with user (roadmap Phase 2, walkthrough Q&A 2026-05-05)
- [x] Phase 1 dependency acknowledged — Phase 2 build starts only after Phase 1 (`metabolites-phase1-plumbing` worktree) lands on main. See §11 below for the file:line shifts and regen-ordering implications.
- [x] No KG schema changes — all changes are surface-only (verified: no new node/edge/property reads)
- [x] Internal call sites for `search=` enumerated (2 sites: `examples/metabolites.py:127`, `tests/unit/test_api_functions.py:6850`; live integration test sites also enumerated below)
- [x] `top_pathways` envelope locations enumerated (2 query builders, 2 Pydantic envelope models — verified: `genes_by_metabolite` does NOT carry `top_pathways` today, so Item 2 affects 2 tools, not 3)
- [x] `metabolite_ids` include filter present on all 3 tools (verified: `list_metabolites`, `metabolites_by_gene`, `genes_by_metabolite` all expose `metabolite_ids` — `exclude_metabolite_ids` mirrors directly)
- [x] `pathway_enrichment` `direction='both'` precedent reviewed (`api/functions.py:4276` default, validator at `:4300-4301`; merge handled by `de_enrichment_inputs` with `allowed_dirs = {"up", "down"} if direction == "both" else {direction}` at `analysis/enrichment.py:635`) — DE adopts the *spelling* but not the default-`'both'` choice
- [x] Cypher fragments verified against live KG 2026-05-05 (Item 3 NOT-IN syntax + parens requirement + set-difference + empty-list no-op; Item 4 IN-list equivalence with `<> 'not_significant'` confirmed at 51169 rows)
- [x] Pending decisions in §9 closed
- [ ] Frozen spec approved
- [ ] Ready for Phase 2 build (TDD via 4 file-owned agents)

## KG dependencies

None — Phase 2 is surface-only. No new node/edge/property reads. No KG-side asks.

## Use cases

- **API consistency (Item 1).** All 8 list/search tools now share the `search_text` kwarg name. Removes the one-off `search=` exception that surprises callers.
- **Cross-tool envelope disambiguation (Item 2).** Today, `list_metabolites` and `metabolites_by_gene` envelope `top_pathways` collides terminologically with the KEGG-pathway-annotation envelope on `genes_by_ontology(ontology="kegg")`. Renaming to `top_metabolite_pathways` makes "this is a metabolite-side rollup, not a KO-pathway annotation" explicit at the field-name level — addresses audit Part 2's "consumer reads `top_pathways` and assumes KO context" friction.
- **Currency-cofactor mitigation (Item 3).** Caller doing a "find genes that produce metabolite X" walk sees ATP / NAD(P)(H) / H2O dominate the top_metabolites rollup because cofactors appear in nearly every reaction. `exclude_metabolite_ids=[ATP, ADP, NADH, NADP, NADPH, H2O, ...]` strips the noise. Primitive-first; if callers re-derive the same exclusion list every call, escalate to a curated default in a future phase.
- **DE direction discoverability (Item 4).** Caller wanting both up and down DE rows currently writes `direction=None, significant_only=True` — works but is a non-obvious incantation. `direction='both'` is self-documenting and aligns with `pathway_enrichment(direction='both', ...)` convention. **Functionally identical to the current `None + significant_only=True` combo** — pure spelling sugar.

---

## 6. Per-item changes

### 6.1 Item 1 — `list_metabolites` `search` → `search_text` rename

**Affected tool:** `list_metabolites` (1 tool).

**Migration policy:** pure rename (no deprecated alias period). User decision 2026-05-05.

**Files touched:**

| Layer | File | Lines | Change |
|---|---|---|---|
| API | `multiomics_explorer/api/functions.py` | 4674-4693 | Rename param `search` → `search_text` in `def list_metabolites(...)`. Update docstring. |
| MCP wrapper | `multiomics_explorer/mcp_server/tools.py` | 7005-7012 | Rename `Annotated` param `search` → `search_text`; update Field description; pass through to API as `search_text=`. |
| Query builder | `multiomics_explorer/kg/queries_lib.py` | 998-1070 (`_list_metabolites_where`); 1072-1175 (`build_list_metabolites`); 1177-1305 (`build_list_metabolites_summary`) | Rename builder param `search` → `search_text` everywhere. **Cypher param name `$search` stays** (it's the fulltext index `db.index.fulltext.queryNodes(...)` second argument and is internal — renaming would cascade into the query string with no observable benefit). The Python-side `params["search"] = search_text` mapping makes this explicit. |
| Internal callers | `multiomics_explorer/examples/metabolites.py:127` | — | `list_metabolites(search="glutamine", limit=5)` → `list_metabolites(search_text="glutamine", limit=5)`. |
| Internal callers | `tests/unit/test_api_functions.py:6850` | — | `list_metabolites(search="glucose*", conn=conn)` → `list_metabolites(search_text="glucose*", conn=conn)`. |
| Internal callers | `tests/unit/test_api_functions.py:6863, 6865` | — | `test_search_empty_validation` — both `search=""` and `search="   "` calls renamed. |
| Internal callers | `tests/integration/test_api_contract.py:1298, 1326` | — | `list_metabolites(search="glucose", conn=conn)` and `list_metabolites(search="   ", conn=conn)` renamed. |
| About content | `multiomics_explorer/inputs/tools/list_metabolites.yaml` | — | Any `search:` example in `examples` / `chaining` updated to `search_text`. Regenerate via `build_about_content.py`. |
| Docs | `CLAUDE.md` (tool table row for `list_metabolites`) | — | If the row references the kwarg name, update. (Audit logs the row mentions "Lucene search"; verify exact wording at edit time.) |

**Validation:**
- Existing test `test_search_empty_validation` continues to pass under the new kwarg name (validation logic unchanged).
- `test_lucene_retry_on_parse_error` continues to pass (Lucene retry is a downstream behavior, not gated on kwarg name).

**Note:** there are no external callers (the explorer surface is not yet shipped to outside consumers), so no migration shim is necessary. Confirmed against `git grep "search=.*list_metabolites\|list_metabolites.*search=" --` (only the 4 sites above).

---

### 6.2 Item 2 — `top_pathways` envelope + per-element key rename

**Affected tools:** `list_metabolites`, `metabolites_by_gene` (2 tools — `genes_by_metabolite` does NOT carry `top_pathways` today).

**Migration policy:** pure rename (no deprecated alias period). User decision 2026-05-05.

**Renames:**

| Old | New | Where |
|---|---|---|
| envelope key `top_pathways` | `top_metabolite_pathways` | `ListMetabolitesResponse.top_pathways` (`tools.py:457`); `MetabolitesByGeneResponse.top_pathways` (`tools.py:1172`) |
| element key `pathway_id` | `metabolite_pathway_id` | `MetTopPathway.pathway_id` (`tools.py:424-427`); `MbgTopPathway.pathway_id` (`tools.py:1039-1070`) |
| element key `pathway_name` | `metabolite_pathway_name` | same two element classes |

**Unchanged element keys** (do not rename):
- `MetTopPathway.count` — count of metabolites in the rollup matching this pathway
- `MbgTopPathway.gene_count`, `MbgTopPathway.pathway_reaction_count`, `MbgTopPathway.pathway_metabolite_count` — already pathway-prefixed where it disambiguates

**Files touched:**

| Layer | File | Lines | Change |
|---|---|---|---|
| Pydantic models | `multiomics_explorer/mcp_server/tools.py` | 424-427 (`MetTopPathway`); 457 (`ListMetabolitesResponse.top_pathways`); 1039-1070 (`MbgTopPathway`); 1172 (`MetabolitesByGeneResponse.top_pathways`) | Rename fields + envelope keys. Update `Field(description=...)` text on each. |
| Query builder | `multiomics_explorer/kg/queries_lib.py` | 1227-1238 (`build_list_metabolites_summary` `top_pathways_block`); 1264, 1297 (RETURN aliases — search and non-search variants); 1273, 1304 (RETURN-key alias) | Rename Cypher RETURN aliases: `pathway_id` → `metabolite_pathway_id`, `pathway_name` → `metabolite_pathway_name`, `top_pathways` → `top_metabolite_pathways`. |
| Query builder | `multiomics_explorer/kg/queries_lib.py` | 7218-7244, 7251 (`build_metabolites_by_gene_summary` top_pathways subquery + RETURN) | Same rename for `metabolites_by_gene`. |
| API tests | `tests/unit/test_api_functions.py:6776-6781` (`TestListMetabolites._SUMMARY_ROW` mock fixture); 6822 (`test_returns_dict_envelope` assertion `"top_pathways" in out`) | — | Update mock fixture keys + assertion to new names. |
| MCP wrapper tests | `tests/unit/test_tool_wrappers.py:4858+` (`list_metabolites`); `tests/unit/test_tool_wrappers.py:5607+` (`metabolites_by_gene`) | — | Update any envelope-key fixtures / assertions. |
| Regression | `tests/regression/` | — | Run `pytest tests/regression/ --force-regen -m kg -q` to refresh fixtures, then verify new fixtures match the renamed schema. |
| About content | `multiomics_explorer/inputs/tools/list_metabolites.yaml`; `multiomics_explorer/inputs/tools/metabolites_by_gene.yaml` | — | Update example responses that quote `top_pathways` / `pathway_id` / `pathway_name`. Update `chaining` entries. Regenerate. |
| Docs | `CLAUDE.md` tool table rows for `list_metabolites` + `metabolites_by_gene` | — | The current rows reference `top_pathways` (e.g., the `metabolites_by_gene` row mentions `top_pathways` as a routing target). Update to `top_metabolite_pathways`. |
| Examples | `multiomics_explorer/examples/metabolites.py` | — | Any narrative or print output that references `top_pathways` / `pathway_id` / `pathway_name` updated. |

**Migration risk:** the rename is pure-string in the Cypher RETURN aliases — no aggregation logic shifts. Pydantic field-name change is the only structural touch on the wrapper side; consumers that programmatically destructure the envelope (`response.top_pathways`) will fail explicitly with `AttributeError: 'ListMetabolitesResponse' object has no attribute 'top_pathways'`, which is the desired loud failure for a breaking rename.

---

### 6.3 Item 3 — `exclude_metabolite_ids` filter addition

**Affected tools:** `list_metabolites`, `metabolites_by_gene`, `genes_by_metabolite` (3 tools).

**Parameter shape:** `exclude_metabolite_ids: list[str] | None = None`. Mirrors `metabolite_ids` include filter.

**Combined-filter semantics (user decision 2026-05-05):** **set-difference**. When both `metabolite_ids` and `exclude_metabolite_ids` are passed, the WHERE clause is constructed as the AND of include + NOT-exclude — so `exclude_metabolite_ids` always wins on overlap. No error / no warning on overlap (silent set-difference matches Cypher's natural semantics for `m.id IN $a AND NOT m.id IN $b`).

**Empty-list semantics:** `exclude_metabolite_ids=[]` is treated as `None` (no-op). Matches the existing `metabolite_ids=[]` convention (verified: existing `_list_metabolites_where` line 1053-1059 uses `if metabolite_ids:` truthy check, which falses on empty list).

**No envelope tracking:** unlike the DM-family `excluded_derived_metrics` envelope (`api/functions.py:3179`) which surfaces auto-excluded DMs from gating, `exclude_metabolite_ids` is user-driven exclusion — there's no auto-gate to surface. Do **not** add an envelope key for "what was excluded"; the caller passed the list, they know what they excluded.

**Cypher pattern (template — applies to all 3 tools):**

Existing include filter (model):
```python
if metabolite_ids:
    conditions.append("m.id IN $metabolite_ids")
    params["metabolite_ids"] = metabolite_ids
```

New exclude filter (mirror — **note parenthesization requirement, see below**):
```python
if exclude_metabolite_ids:
    conditions.append("(NOT (m.id IN $exclude_metabolite_ids))")
    params["exclude_metabolite_ids"] = exclude_metabolite_ids
```

**CyVer parenthesization requirement (verified against live KG 2026-05-05).** The unparenthesized form `m.id IN $a AND NOT m.id IN $b` is rejected by CyVer (the Cypher validator that gates `run_cypher` and is exercised by `pytest tests/integration/`) with a false-positive "write operation" error when both an include and an exclude clause appear in the same WHERE block. The parenthesized form `(m.id IN $a) AND (NOT (m.id IN $b))` passes. Apply parentheses defensively in all 5 WHERE helpers regardless of whether the helper is currently the only AND-clause builder for that tool. Test with combined include + exclude in unit tests to surface any future CyVer regression.

**Live-KG verification (2026-05-05):**
- `(NOT (m.id IN $cofactors))` over `Metabolite` returns 3214 / 3218 — the 4 explicitly-listed cofactor IDs drop out exactly.
- Combined include `{ATP, ADP, AMP, H2O}` + exclude `{ATP, ADP, NADH, NADPH}` returns `{AMP, H2O}` — set-difference holds.
- Empty-list exclude (`NOT m.id IN []`) returns 3218 / 3218 — no-op confirmed at the Cypher level. Python-layer truthy check still recommended (avoids generating noise AST).

**Files touched:**

| Layer | File | Lines | Change |
|---|---|---|---|
| API | `multiomics_explorer/api/functions.py` | 4674 (`list_metabolites`); 4928 (`genes_by_metabolite`); 5427 (`metabolites_by_gene`) | Add `exclude_metabolite_ids: list[str] \| None = None` immediately after `metabolite_ids` in each signature. Pass through to builder. |
| MCP wrapper | `multiomics_explorer/mcp_server/tools.py` | 7005 (`list_metabolites`); 7180 (`genes_by_metabolite`); 7398 (`metabolites_by_gene`) | Add `Annotated[list[str] \| None, Field(description="Exclude metabolites with these IDs ... If both `metabolite_ids` and `exclude_metabolite_ids` are passed, the result is the set difference (exclude wins on overlap).")] = None` immediately after `metabolite_ids`. |
| Query builder | `multiomics_explorer/kg/queries_lib.py` | 998-1070 (`_list_metabolites_where`, line 1053-1059 is the include-mirror site); 6143-... (`_genes_by_metabolite_metabolism_where`, lines 6177-6180); 6203-... (`_genes_by_metabolite_transport_where`, lines 6233-6236); 6631-... (`_metabolites_by_gene_metabolism_where`, lines 6699-6702); 6747-... (`_metabolites_by_gene_transport_where`) | Add the mirror block (4 lines) immediately after each existing include block. **Per-arm scope:** for the 2 chemistry drill-down tools, exclude applies on **both** arms (metabolism + transport), matching `metabolite_ids` per-arm scope. |
| Builder signatures | `kg/queries_lib.py` `build_list_metabolites`, `build_list_metabolites_summary`, `build_genes_by_metabolite`, `build_genes_by_metabolite_summary`, `build_metabolites_by_gene`, `build_metabolites_by_gene_summary` | — | Add `exclude_metabolite_ids: list[str] \| None = None` to each builder + summary builder signature; thread to WHERE helper. |
| Tests | `tests/unit/test_query_builders.py` | — | Add `test_exclude_metabolite_ids_filter` for each of the 3 tools' detail + summary builders. Assert generated Cypher contains `NOT m.id IN $exclude_metabolite_ids` and `params["exclude_metabolite_ids"]` is set. |
| Tests | `tests/unit/test_api_functions.py` | — | Add `test_exclude_metabolite_ids_passed` per tool — mock-driver test asserting param flows through. |
| Tests | `tests/unit/test_tool_wrappers.py` | — | Pydantic param-validation test per tool (accepts list of str, accepts None, rejects non-list). |
| Tests | `tests/integration/test_mcp_tools.py` (or equivalent) | — | KG-integration test per tool: pass an exclude list of currency cofactors (e.g., ATP, NADH, H2O ChEBI IDs) and assert their rows drop out. |
| About content | `inputs/tools/{list_metabolites,metabolites_by_gene,genes_by_metabolite}.yaml` | — | New mistake entry per tool: "When the `top_metabolites` rollup is dominated by ATP / NADH / NADP / NADPH / H2O / etc., pass `exclude_metabolite_ids=[<chebi_ids>]` to strip the cofactor noise. Set-difference semantics: `metabolite_ids` ∩ `exclude_metabolite_ids` is excluded silently." Regenerate. |
| Docs | `CLAUDE.md` | — | If row prose mentions the include filter, mention exclude alongside. |

**Worked example for the test (currency-cofactor strip).** Live verification 2026-05-05 confirms the KG `Metabolite.id` namespace has 3 prefixes: `kegg.compound:` (2657), `chebi:` (560), `mnx:` (1). Use `kegg.compound:` for cofactors:
```python
out = list_metabolites(
    organism="Prochlorococcus marinus MED4",
    exclude_metabolite_ids=[
        "kegg.compound:C00002",  # ATP
        "kegg.compound:C00008",  # ADP
        "kegg.compound:C00004",  # NADH
        "kegg.compound:C00005",  # NADPH
        "kegg.compound:C00001",  # H2O
    ],
)
# Expect: ATP, ADP, NADH, NADPH, H2O absent from results; total_matching reduced by ≤5.
```

---

### 6.4 Item 4 — `differential_expression_by_gene` accept `direction='both'`

**Affected tool:** `differential_expression_by_gene` (1 tool).

**Semantics:** `direction='both'` is the explicit, self-documenting spelling for "return rows with `expression_status` ∈ {`significant_up`, `significant_down`}". **Functionally equivalent to the current `direction=None, significant_only=True` combo** — both produce `r.expression_status <> 'not_significant'` in the WHERE clause. This is API discoverability sugar, not new behavior.

**Decisions locked (user 2026-05-05):**
- **Default stays `None`** (NOT changed to `'both'`). DE is more atomic than enrichment; existing callers should not see behavior shift.
- **No new per-row column.** `expression_status` already discriminates rows atomically (`'significant_up'` vs `'significant_down'`); callers can derive direction from status if needed. (Compare: `pathway_enrichment` adds a `direction` column because its rows aggregate across statuses — DE rows do not.)

**Cypher change (single branch addition):**

Existing logic (`_differential_expression_where`, `kg/queries_lib.py:2769-2774`):
```python
if direction == "up":
    conditions.append("r.expression_status = 'significant_up'")
elif direction == "down":
    conditions.append("r.expression_status = 'significant_down'")
elif significant_only:
    conditions.append("r.expression_status <> 'not_significant'")
```

After Item 4:
```python
if direction == "up":
    conditions.append("r.expression_status = 'significant_up'")
elif direction == "down":
    conditions.append("r.expression_status = 'significant_down'")
elif direction == "both":
    conditions.append("r.expression_status IN ['significant_up', 'significant_down']")
elif significant_only:
    conditions.append("r.expression_status <> 'not_significant'")
```

The new `'both'` branch and the existing `significant_only=True, direction=None` branch produce semantically equivalent results. Using `IN [...]` rather than `<> 'not_significant'` makes the intent explicit at the Cypher level (and is robust to future status-vocabulary additions — e.g. if a `significant_ambiguous` status were added later, `<> 'not_significant'` would silently include it; `IN ['significant_up', 'significant_down']` would not).

**Live-KG verification (2026-05-05):**
- `Changes_expression_of.expression_status` universe: exactly `{'not_significant': 181232, 'significant_up': 25637, 'significant_down': 25532}` (3 distinct values, 232401 total).
- `r.expression_status IN ['significant_up', 'significant_down']` returns 51169 (= 25637 + 25532).
- `r.expression_status <> 'not_significant'` returns 51169 — identical.
- Functional equivalence with `direction=None, significant_only=True` confirmed end-to-end.

**Files touched:**

| Layer | File | Lines | Change |
|---|---|---|---|
| API validation | `multiomics_explorer/api/functions.py:2078-2081` (`_VALID_DIRECTIONS` check) | — | Add `'both'` to the valid set. Confirm `_VALID_DIRECTIONS` constant location and add. |
| MCP wrapper | `multiomics_explorer/mcp_server/tools.py:3236` | — | Change `Literal["up", "down"] \| None` → `Literal["up", "down", "both"] \| None`. Update `Field(description=...)` to mention `'both'` as the explicit spelling for both-arm DE. |
| Query builder | `multiomics_explorer/kg/queries_lib.py:2769-2774` | — | Insert the new `elif direction == "both":` branch before the `significant_only` branch. |
| Tests | `tests/unit/test_query_builders.py:TestBuildDifferentialExpressionByGene` | — | Add `test_direction_both_filter` asserting generated Cypher contains `r.expression_status IN ['significant_up', 'significant_down']` when `direction="both"`. |
| Tests | `tests/unit/test_api_functions.py:TestDifferentialExpressionByGene` (line 2891) | — | Add `test_direction_both_returns_both_statuses` — mock-driver test asserting both up and down rows pass through. Existing `test_rows_by_status_filled` (line 3020) is the structural mirror. |
| Tests | `tests/unit/test_tool_wrappers.py` | — | Pydantic validation test: `direction="both"` accepted; `direction="invalid"` rejected. |
| Tests | `tests/integration/test_mcp_tools.py` | — | KG-integration test: pick a known organism+experiment with both up and down DE rows; assert `direction='both'` returns the union and `direction=None, significant_only=True` returns the same union (functional equivalence). |
| About content | `multiomics_explorer/inputs/tools/differential_expression_by_gene.yaml` | — | New example: `direction='both'` returning union. Mistake entry: "`direction='both'` is functionally identical to `direction=None, significant_only=True` — pick whichever spelling is clearer at the call site. Default `direction=None` is unchanged." Regenerate. |
| Docs | `CLAUDE.md` row for `differential_expression_by_gene` | — | If the row enumerates direction values, add `'both'`. |

---

## 7. Implementation file map (Mode B parallel build)

Per the `add-or-update-tool` skill Phase 2 file-ownership convention. Each agent gets one file; items spread across all 4 agents.

| Agent | File | Items touched |
|---|---|---|
| `query-builder` | `multiomics_explorer/kg/queries_lib.py` | 6.1 (`search_text` rename in `_list_metabolites_where`, `build_list_metabolites`, `build_list_metabolites_summary`); 6.2 (Cypher RETURN aliases for `top_metabolite_pathways` in 2 builders); 6.3 (mirror NOT-IN block in 5 WHERE helpers across 3 tools); 6.4 (new `'both'` branch in `_differential_expression_where`). |
| `api-updater` | `multiomics_explorer/api/functions.py` | 6.1 (kwarg rename + docstring + 4 internal call-site updates in `examples/metabolites.py` and tests); 6.2 (no API-layer change — envelope rename is wrapper-side); 6.3 (3 signature additions, threaded to builders); 6.4 (validator update + signature docstring). |
| `tool-wrapper` | `multiomics_explorer/mcp_server/tools.py` | 6.1 (Annotated kwarg rename); 6.2 (4 Pydantic field renames across `MetTopPathway` / `MbgTopPathway` / 2 envelope models); 6.3 (3 Annotated param additions); 6.4 (Literal extension + Field description). |
| `doc-updater` | `multiomics_explorer/inputs/tools/{list_metabolites,metabolites_by_gene,genes_by_metabolite,differential_expression_by_gene}.yaml` + `CLAUDE.md` tool table updates + `multiomics_explorer/examples/metabolites.py` (1 call-site rename) | About-content for 4 tools (regen via `build_about_content.py`); CLAUDE.md tool-table touch-ups for 4 tool rows; example narrative updates. |

**Anti-scope-creep guardrail (mandatory in every brief):** "ADD/RENAME only — do NOT modify any unrelated test, case, or yaml. If an unrelated test fails in your environment, REPORT AS A CONCERN; do not silently retune. Pinned baselines are KG-state guards. The 4 renames are pure-string substitutions (no aggregation logic, no semantic shifts); the 1 filter is a pure addition (no removal); the 1 direction option is a pure branch addition (no rebalancing of existing branches)."

**Mode B briefing addendum:** "For Item 3, implement `list_metabolites` as the template within your file (one tool, one WHERE helper); then extend the same pattern to `genes_by_metabolite` (2 WHERE helpers) and `metabolites_by_gene` (2 WHERE helpers). The Cypher fragment is identical across all 5 helpers — just placement varies."

---

## 8. Test cases (one slice per layer)

All test patterns follow the `testing` skill conventions. New tests are **additions** to existing test classes — no rebaseline of existing assertions.

### Query builder tests (`tests/unit/test_query_builders.py`)

| Item | Test addition |
|---|---|
| 6.1 | `TestBuildListMetabolites.test_search_text_param_threads` — assert builder accepts `search_text=` kwarg and produces the same Cypher as the previous `search=` (string-match the fulltext-index fragment). |
| 6.2 | `TestBuildListMetabolitesSummary.test_top_metabolite_pathways_alias` — assert generated Cypher RETURN contains `metabolite_pathway_id`, `metabolite_pathway_name`, `top_metabolite_pathways` aliases. Same for `TestBuildMetabolitesByGeneSummary.test_top_metabolite_pathways_alias`. |
| 6.3 | `TestBuildListMetabolites.test_exclude_metabolite_ids_filter` (and the summary builder counterpart). Assert: (a) generated Cypher contains `NOT m.id IN $exclude_metabolite_ids`; (b) `params["exclude_metabolite_ids"]` is set; (c) when both `metabolite_ids` and `exclude_metabolite_ids` are passed, both conditions appear AND-joined. Mirror tests for `genes_by_metabolite` (both arms) and `metabolites_by_gene` (both arms). |
| 6.4 | `TestBuildDifferentialExpressionByGene.test_direction_both_filter` — assert generated Cypher contains `r.expression_status IN ['significant_up', 'significant_down']`. |

### API tests (`tests/unit/test_api_functions.py`)

| Item | Test addition |
|---|---|
| 6.1 | `TestListMetabolites` — update existing `test_lucene_retry_on_parse_error` and `test_search_empty_validation` to use `search_text=`. No new test added (the rename is structural). |
| 6.2 | `TestListMetabolites._SUMMARY_ROW` mock fixture (line 6776-6781) — update keys to `top_metabolite_pathways` / `metabolite_pathway_id` / `metabolite_pathway_name`. `test_returns_dict_envelope` (line 6822) — update assertion to `"top_metabolite_pathways" in out`. Mirror for `TestMetabolitesByGene`. |
| 6.3 | `TestListMetabolites.test_exclude_metabolite_ids_passed` — mock-driver test asserting param flows to builder. Mirror for `TestGenesByMetabolite` and `TestMetabolitesByGene`. |
| 6.4 | `TestDifferentialExpressionByGene.test_direction_both_accepted` — `_VALID_DIRECTIONS` accepts `'both'`. `test_direction_both_returns_both_statuses` — mock returns both up + down rows when `direction='both'`. |

### Tool wrapper tests (`tests/unit/test_tool_wrappers.py`)

| Item | Test addition |
|---|---|
| 6.1 | `TestListMetabolitesWrapper` — update existing tests to pass `search_text=`. |
| 6.2 | `TestListMetabolitesWrapper.test_top_metabolite_pathways_field` — Pydantic model parsing of envelope with the new key. Mirror for `metabolites_by_gene`. |
| 6.3 | `TestListMetabolitesWrapper.test_exclude_metabolite_ids_param` — accept list[str], None, reject non-list. Mirror for `genes_by_metabolite`, `metabolites_by_gene`. |
| 6.4 | `TestDifferentialExpressionByGeneWrapper.test_direction_both_accepted` — Literal accepts `'both'`. Reject `'invalid'`. |

`EXPECTED_TOOLS` registry update: param-list change for the 4 affected tool entries (rename `search` → `search_text` for `list_metabolites`; add `exclude_metabolite_ids` for 3 tools; expand `direction` Literal for DE). No new tools added — `TOOL_BUILDERS` registry untouched.

### KG-integration tests (`tests/integration/`, marked `@pytest.mark.kg`)

| Item | Test |
|---|---|
| 6.1 | Update existing 2 `test_api_contract.py` call sites (lines 1298, 1326) to use `search_text=`. |
| 6.2 | Round-trip: `list_metabolites(summary=True)` returns envelope with `top_metabolite_pathways` (asserts the rename round-trips through Cypher → API → wrapper). Mirror for `metabolites_by_gene`. |
| 6.3 | Round-trip per tool: pass an exclude list of 4 currency cofactors; assert their rows drop out and `total_matching` decreases accordingly. |
| 6.4 | Round-trip: `direction='both'` and `direction=None, significant_only=True` return the same `total_matching` and the same row set on a known fixture organism+experiment (functional equivalence). |

### Regression tests (`tests/regression/`)

The 2 envelope-key renames + 1 per-element-key renames will trigger fixture mismatches on:
- `list_metabolites` summary fixtures (4 fixture sets)
- `metabolites_by_gene` summary fixtures
- Any DE fixture that exercised `direction=None` with mixed up/down output (none of these will break — `direction='both'` is additive, default unchanged).

Run `pytest tests/regression/ --force-regen -m kg -q` to refresh, then `pytest tests/regression/ -m kg -q` to verify clean.

**Add explicit regression assertions** locking the new shape (so a future accidental revert is caught):
- One regression case asserting `top_metabolite_pathways` in `list_metabolites(summary=True)` envelope — with sample fixture row containing `metabolite_pathway_id` / `metabolite_pathway_name`.
- One regression case asserting `top_metabolite_pathways` in `metabolites_by_gene(summary=True)` envelope — with sample fixture row.
- One regression case for `direction='both'` on DE — sample fixture row count + status distribution.

---

## 9. Open questions / pending decisions

All resolved as of 2026-05-05 walkthrough.

- [x] **Migration policy for `search` → `search_text`.** Pure rename, no deprecated alias period. (User 2026-05-05.) Rationale: 4 internal call sites total, all under our control; deprecation period adds churn without value at the current shipping stage.
- [x] **Migration policy for `top_pathways` → `top_metabolite_pathways` + per-element key renames.** Pure rename, no alias. (User 2026-05-05.) Same rationale.
- [x] **Combined-filter semantics when both `metabolite_ids` and `exclude_metabolite_ids` are passed.** Set difference (`include AND NOT exclude`); exclude wins on overlap; silent (no warning, no error). (User 2026-05-05.) Matches Cypher's natural AND-join semantics; no per-tool divergence.
- [x] **Default direction on `differential_expression_by_gene`.** Stays `None`. (User 2026-05-05.) Rationale: existing callers should not see behavior shift; `'both'` is added as one explicit option, not the new default. Distinct from `pathway_enrichment` which sets `default='both'`.
- [x] **Per-row `direction` column when `direction='both'`.** Reuse existing `expression_status` (`'significant_up'` / `'significant_down'`); no new column. (User 2026-05-05.) Rationale: DE rows are status-atomic; `pathway_enrichment` adds `direction` because its rows aggregate across statuses, which DE rows do not. Folding the user's observation: `direction='both'` is functionally identical to `direction=None, significant_only=True` — added for API discoverability, not new behavior.

---

## 10. Phase 1 interaction (build sequencing)

**Phase 2 build starts only after Phase 1 merges to main.** Phase 1 is in flight on worktree `metabolites-phase1-plumbing` at the time of this freeze. Phase 1 touches a non-overlapping set of *items* (per-row pass-through fields + envelope rollups on 6 tools) but a partially-overlapping set of *files* with Phase 2.

**File:line shifts to expect after Phase 1 lands.** All file:line references in §6 above are accurate as of the spec-freeze main HEAD; they will shift after Phase 1's PR merges. The implementation plan (writing-plans output) must use **anchor patterns** rather than fixed line numbers — e.g., "in `_list_metabolites_where`, immediately after the existing `if metabolite_ids:` block" rather than "at `kg/queries_lib.py:1059`". Specific overlap zones:

| File | Phase 1 changes that shift Phase 2 anchors |
|---|---|
| `multiomics_explorer/mcp_server/tools.py` | Phase 1 expands `ListMetabolitesResponse` (4 new per-row fields + `by_measurement_coverage` envelope), `MetabolitesByGeneResponse` (no Phase 1 changes), `GenesByMetaboliteResponse` (no Phase 1 changes), `GeneOverviewResponse` (4 new per-row fields + `has_chemistry`), and 4 list-tool response models. Phase 2 renames `top_pathways` (envelope key on `ListMetabolitesResponse`, `MetabolitesByGeneResponse`) — these envelope keys do **not** collide with Phase 1's `by_measurement_coverage` (envelope) or any Phase 1 per-row field. Adjacent line numbers shift; field-rename targets are stable by name. |
| `multiomics_explorer/api/functions.py` | Phase 1 extends 6 list-tool API signatures with new pass-through pulls. Phase 2's signature additions (`exclude_metabolite_ids` on 3 tools; `direction='both'` validator on DE) are independent. The 4 internal `search=` call-site updates in `examples/metabolites.py:127` and `tests/...` are unaffected by Phase 1 (Phase 1 doesn't touch examples or those test sites). |
| `multiomics_explorer/kg/queries_lib.py` | Phase 1 extends 6 query builders with SELECT-clause additions and one new envelope rollup CTE on `build_list_metabolites_summary` (`by_measurement_coverage`). Phase 2's 5 WHERE-helper changes for `exclude_metabolite_ids` are in different functions; the `top_pathways` RETURN-alias rename and the new `direction='both'` branch are also in disjoint sections. No expected merge conflicts at the AST level. |
| `multiomics_explorer/inputs/tools/list_metabolites.yaml` | Phase 1 adds new examples + mistakes for measurement-rollup pass-through. Phase 2 updates examples that reference `top_pathways` / `pathway_id` / `pathway_name` and adds new mistake/example for `exclude_metabolite_ids`. Section-level edits — should rebase cleanly. |
| `multiomics_explorer/inputs/tools/metabolites_by_gene.yaml` | Phase 1 does not touch this YAML. Phase 2 owns all edits. |
| `multiomics_explorer/inputs/tools/genes_by_metabolite.yaml` | Phase 1 does not touch this YAML. Phase 2 adds `exclude_metabolite_ids` example/mistake only. |
| `multiomics_explorer/inputs/tools/differential_expression_by_gene.yaml` | Phase 1 does not touch this YAML. Phase 2 owns all edits. |
| `tests/regression/` | Phase 1 regenerates fixtures for 6 tools (most importantly `list_metabolites` summary fixtures, `gene_overview` fixtures). Phase 2 regenerates fixtures for the 2 envelope-rename tools (`list_metabolites`, `metabolites_by_gene`) **on top of** Phase-1-regenerated fixtures. Run order: `pytest tests/regression/ --force-regen -m kg -q` once after the Phase 2 build, then verify clean. |

**Implementation plan must include:**

1. **Step 0 — Phase 1 land verification.** Before opening the Phase 2 worktree: confirm Phase 1's PR has merged to main (`git log --oneline main | grep -F 'phase1-pass-through-plumbing'`). If not yet merged, halt — Phase 2 builds on top of Phase-1-shipped surface, not pre-Phase-1 main.
2. **Worktree baseline check.** Per `add-or-update-tool` skill Phase 2 guidance: `EnterWorktree` re-uses existing branch by name; verify worktree HEAD == main HEAD before dispatching agents (`git log --oneline -1` on each).
3. **Anchor patterns over line numbers.** Brief each implementer agent to use grep / function-name anchors when locating edit sites. The §6 line numbers are spec-freeze artifacts, not implementation directives.
4. **Single regression regen pass.** Don't double-regen. After all 4 implementer agents report green and code review passes, one `--force-regen` invocation, then verify clean.

---

## 11. Acceptance criteria

- All 4 items land per §6.1 – §6.4.
- The 4 renames are pure-string substitutions: no aggregation, no semantic shifts, no Cypher row-count changes between old and new shape on a controlled fixture (regression `--force-regen` + visual diff confirms).
- The 1 filter addition (`exclude_metabolite_ids`) drops only the IDs explicitly passed (no over-filtering, no under-filtering); set-difference holds with `metabolite_ids` ∩ `exclude_metabolite_ids` excluded.
- The 1 direction-option addition (`'both'`) returns the union of `'up'` and `'down'` results; equivalent to `direction=None, significant_only=True` on a controlled fixture.
- All unit + KG-integration tests pass (3 pytest invocations: `tests/unit/`, `tests/integration/ -m kg`, `tests/regression/ -m kg`).
- Regression fixtures regenerated and locked (one explicit regression assertion per renamed envelope key + one for `direction='both'`).
- Code review (hard gate per `add-or-update-tool` skill Stage 3) passes — particular attention to:
  - The `search_text` rename touching the Python kwarg name only, leaving the internal Cypher `$search` parameter alias intact (verify by grep — Cypher should still pass `params["search"]` unchanged).
  - The `top_metabolite_pathways` Cypher RETURN aliases correctly cascading from query builder through API merge through Pydantic envelope.
  - The 5 `NOT m.id IN $exclude_metabolite_ids` blocks placed inside the right WHERE helpers (especially: per-arm scope on the 2 chemistry drill-down tools — exclude must apply on **both** metabolism + transport arms).
  - The new `direction == "both"` branch ordered before the `significant_only` branch, matching the existing `if/elif/elif` cascade in `_differential_expression_where`.
- About-content YAML edits regenerate cleanly via `build_about_content.py`.
- `CLAUDE.md` tool table reflects the renamed envelope keys + new param + new direction option for the 4 affected tool rows.
- All 4 internal call sites for `search=` updated to `search_text=` (`examples/metabolites.py:127`, `tests/unit/test_api_functions.py:6850/6863/6865`, `tests/integration/test_api_contract.py:1298/1326`).
