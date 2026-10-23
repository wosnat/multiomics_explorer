# GO Transport Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This repo's `add-or-update-tool` skill (Mode B, cross-tool) governs Tasks 2–5: read `.claude/skills/add-or-update-tool/SKILL.md` before Task 2.

**Goal:** Surface the KG's GO transport route (GO term → Metabolite / ChemicalRole) in seven MCP tools, side by side with TCDB and KEGG and never blended.

**Architecture:** A new `go_transport` arm in `genes_by_metabolite` (gbm) and `metabolites_by_gene` (mbg), on by default, rows at gene × GO term × target grain, with opt-in ancestor inheritance. Role ids reach GO and TCDB role edges. Smaller pass-throughs in `gene_overview`, `list_metabolites`, `kg_release_info`, `kg_schema`, plus a new `docs://analysis/transport` page.

**Tech Stack:** Python 3.11, Neo4j Cypher (read-only), FastMCP 3.x, Pydantic v2, pytest (`-m kg` for live-KG tests).

**Spec:** `docs/superpowers/specs/2026-10-20-go-transport-surface-design.md` (approved 2026-10-23). Executors read both.

## Global Constraints

- Dev graph only: assume the four GO edges, `Schema_info.go_transport_excluded_targets` and the `go_transport` value exist. No degrade paths (spec §4).
- No blending: GO rows never change `transport` rows, `substrate_depth`, `tcdb_*`, `transporter_gene_count`, `catalyst_gene_count`, `organism_count`, `transport_substrate_resolution` (spec §2).
- GO namespace comes from the edge type (`type(t)`), never `labels(go)[0]` (the first label is `Entity`).
- Default `evidence_sources=None` ⇒ arms `("metabolism", "transport", "go_transport")`; inherited GO rows only with `go_include_ancestors=True`.
- Read-only repo; layer rules per `.claude/skills/layer-rules/`; outfacing-doc lint `uv run python scripts/build_about_content.py --lint` must exit 0.
- Field `description=` strings ≤ 250 chars; CLAUDE.md tool-table rows ≤ 700 chars.
- Phase 2 briefs carry the anti-scope-creep guardrail verbatim (add-or-update-tool SKILL.md, Stage 2).
- Default-on GO rows move existing gbm / mbg / gene_overview / list_metabolites goldens, examples and pins — regenerate in Task 4, never loosen an assertion.

## Review Focus

1. **Three-arm pagination (Mode 3):** `offset` past the TCDB rows must page into GO rows with no gap or duplicate; `total_matching` = sum of the three arms. → Task 2 test `test_gbm_three_arm_paging_continuity` (kg).
2. **Mixed role + metabolite batch:** `genes_by_metabolite(["chebi.role:26672", "kegg.compound:C00086"], organism="AltDE")` returns both target kinds; a role id in `exclude_metabolite_ids` drops its rows. → Task 2 `test_gbm_mixed_role_and_metabolite_batch` (kg), `test_gbm_exclude_role_id` (kg).
3. **Organism with no GO-route genes:** GO arm returns nothing, envelope keys present, no crash. → Task 2 edge-case scenario `gbm_go_arm_empty_organism`.
4. **Ancestors + filters:** `go_include_ancestors=True` with `exclude_metabolite_ids` naming an inherited-only target drops it; mbg with `metabolite_elements=["N"]` drops role rows and formula-less inherited classes. → Task 2 `test_gbm_ancestors_respect_exclude` (kg), `test_mbg_ancestors_with_elements` (kg).
5. **Excluded target with no node:** `genes_by_metabolite(["chebi:23906"], "MED4")` lists it in `not_found.metabolite_ids` **and** carries the curation warning. → Task 2 `test_gbm_excluded_target_without_node_warns` (kg).

---

## File map

| File | Change | Owner (Phase 2) |
|---|---|---|
| `multiomics_explorer/kg/queries_lib.py` | new GO arm builders (gbm, mbg); TCDB role branch in both transport arms; summaries gain the GO arm + `rows_by_go_term_depth`; `build_gene_overview` / `_summary` GO tag + `has_chemistry`; `_list_metabolites_where` organism union; `build_list_metabolites` / `_summary` GO organism fields + union `top_organisms` | query-builder |
| `multiomics_explorer/api/functions.py` | arms, validators, `go_include_ancestors`, sort keys, canonicaliser switch, warnings, `_KG_IDENTITY_FIELDS`, `kg_schema` descriptions | api-updater |
| `multiomics_explorer/config/edge_descriptions.yaml` (new) + `schema_baseline.yaml` | four GO caveat paragraphs; five edges required | api-updater |
| `multiomics_explorer/mcp_server/tools.py` | row / envelope models, `Literal`s, new param, field descriptions | tool-wrapper |
| `multiomics_explorer/inputs/tools/*.yaml`, `skills/.../references/analysis/{transport,metabolites}.md`, `CLAUDE.md`, `inputs/lint/kg_claims.yaml` | docs | doc-updater |
| `tests/unit/test_{query_builders,api_functions,tool_wrappers}.py`, `tests/integration/…`, `tests/integration/edge_cases/scenarios.py` | tests | test-updater |

---

### Task 1: Branch + baseline

**Files:** none modified.

- [ ] **Step 1:** Create the worktree via `superpowers:using-git-worktrees`, branch `go-transport-surface` from `main`.
- [ ] **Step 2:** Verify `git log --oneline -1` in the worktree equals `main` HEAD (`9f7f8a3` or later). If not, `git reset --hard main`.
- [ ] **Step 3:** Baseline: `pytest tests/unit -q` → all pass; `kg_release_info` verdict `ok` on built_at `2026-10-19T17:03:46Z` or later.

### Task 2 (Phase 1): Verified Cypher + frozen tool spec — USER GATE

**Files:**
- Create: `docs/tool-specs/go-transport-surface.md` (template `.claude/skills/add-or-update-tool/assets/tool-spec-template.md`)

**Interfaces — Produces (frozen names every later task uses):**
- `build_genes_by_metabolite_go_transport(*, metabolite_ids: list[str], organism: str, exclude_metabolite_ids: list[str] | None = None, metabolite_pathway_ids: list[str] | None = None, gene_categories: list[str] | None = None, include_ancestors: bool = False, verbose: bool = False, limit: int | None = None, offset: int = 0) -> tuple[str, dict]`
- `build_metabolites_by_gene_go_transport(*, locus_tags: list[str], organism: str, exclude_metabolite_ids: list[str] | None = None, metabolite_pathway_ids: list[str] | None = None, metabolite_elements: list[str] | None = None, include_ancestors: bool = False, verbose: bool = False, limit: int | None = None, offset: int = 0) -> tuple[str, dict]`
- Existing `build_genes_by_metabolite_summary` / `build_metabolites_by_gene_summary` gain `include_ancestors: bool = False`; `arms` accepts `"go_transport"`; RETURN gains `rows_by_go_term_depth`.
- Row keys added to both arms' RETURN (null where not applicable): `go_term_id, go_term_name, go_namespace, go_evidence, go_sources, go_term_depth, go_axiom_term_id, go_axiom_term_name, target_kind`; verbose `go_chebi_ids`.
- `go_namespace` values: `'molecular_function'` | `'biological_process'`. `target_kind`: `'metabolite'` | `'chemical_role'`.

- [ ] **Step 1: Draft + run the gbm GO arm (direct)** on live KG with `kegg.compound:C00086`, organism `Prochlorococcus MED4`. Expected: 11 rows over urtA–urtE (PMM0970–PMM0974); urtA has `go:0033221` (MF, curated, `['ncbi']`) and `go:0015840` (BP, curated, `['cyanorak','ncbi']`).
- [ ] **Step 2: Inherited branch.** Corpus check of the dedup rule (spec §3.3): count distinct (gene, target) inherited-only pairs = 4,194, genes with GO reach only by inheritance = 379, MED4 = 53 pairs / 28 genes; depth histogram 1: 2,709 / 2: 1,186 / 3: 241 / ≥4: 58.
- [ ] **Step 3: Role arms.** GO: `chebi.role:26672` in `Alteromonas mediterranea AltDE` returns `MADE_1013240` (`go:0015891`, BP). TCDB: `Tcdb_family_transports_chemical_role` walk with `TCDB_DEEPEST_ATTACHMENT_PREDICATE` — record row count for one role/organism pair.
- [ ] **Step 4: mbg GO arm** for `PMM0970`: 2 GO rows (urea MF + BP) after its 4 TCDB rows.
- [ ] **Step 5: Summaries.** For each of steps 1–4, `total_matching` from the summary query equals the detail row count; `rows_by_evidence_source` includes `go_transport`.
- [ ] **Step 6: Pass-throughs.** `gene_overview` EXISTS clause for GO (MED4 count of genes tagged `go_transport` = 59); `list_metabolites(organism_names=['Prochlorococcus MED4'])` union count vs current; `has_chemistry` delta for MED4.
- [ ] **Step 7: Filter no-ops.** Run each shared filter (`gene_categories`, `metabolite_pathway_ids`, `exclude_metabolite_ids`, `metabolite_elements`) with and without on the GO arm; each must change the result or be documented as a no-op.
- [ ] **Step 8:** Write `docs/tool-specs/go-transport-surface.md`: purpose, the Interfaces above, verified Cypher (marked "verified against live KG" with built_at), the numbers from steps 1–7 as test expectations, sort keys (spec §3.1), warnings copy (Task 4c).
- [ ] **Step 9: GATE.** Present the spec to the user. Do not start Task 3 until they freeze it. Commit: `docs(tool-spec): GO transport surface (frozen)`.

### Task 3 (Phase 2 RED): Failing tests — `test-updater` agent

**Files:**
- Modify: `tests/unit/test_query_builders.py`, `tests/unit/test_api_functions.py`, `tests/unit/test_tool_wrappers.py` (+ `EXPECTED_TOOLS` / `TOOL_BUILDERS` registries)
- Modify: `tests/integration/test_mcp_tools.py`, `tests/integration/test_tool_correctness_kg.py`, `tests/integration/test_api_contract.py`
- Modify: `tests/integration/edge_cases/scenarios.py` (`SCENARIO_BUILDERS`)

**Interfaces — Consumes:** Task 2's frozen names.

- [ ] **Step 1: Unit — builders.** Assert on Cypher strings / params:
  - `test_gbm_go_transport_builder_walks_both_edge_types` — Cypher contains `Molecular_function_transports_metabolite|Biological_process_transports_metabolite` and the role edge pair; `'go_transport' AS evidence_source`.
  - `test_gbm_go_transport_namespace_from_edge_type` — `go_namespace` derived via `type(t)`; Cypher does not contain `labels(go)[0]`.
  - `test_gbm_go_transport_include_ancestors_adds_isa_walk` — `include_ancestors=True` adds `Molecular_function_is_a_molecular_function|Biological_process_is_a_biological_process*1..`; False omits it.
  - `test_gbm_transport_arm_walks_tcdb_role_edge` / mbg twin — `Tcdb_family_transports_chemical_role` present.
  - `test_gene_overview_evidence_sources_includes_go_transport`, `test_gene_overview_has_chemistry_includes_go_route`.
  - `test_list_metabolites_organism_filter_unions_go_reach` — WHERE contains both `m.organism_names` and `m.go_transport_organism_names`.
- [ ] **Step 2: Unit — api.**
  - `test_gbm_default_arms_include_go_transport` (mock: three arm builders called when `evidence_sources=None`).
  - `test_gbm_rejects_unknown_evidence_source` lists `['metabolism', 'transport', 'go_transport']`.
  - `test_list_metabolites_accepts_go_transport`.
  - `test_canonicalize_roles_are_targets_true_passes_role_without_warning`; `…_false_keeps_role_warning` (default, other tools).
  - `test_gbm_sort_go_after_tcdb` — sort key orders metabolism < transport most_specific < transport inherited < go depth 0 < go depth 1; within GO: MF before BP, curated < family_inferred < domain_inferred.
  - `test_gbm_excluded_target_warning` — mock `go_transport_excluded_targets=['kegg.compound:C00080']`, input `C00080` ⇒ warning contains `by curation`.
  - `test_neurotransmitter_role_warning_gbm_input` / `_mbg_row`.
  - `test_kg_release_info_passes_excluded_targets`.
  - `test_kg_schema_relationship_description_from_yaml` — `relationships['Molecular_function_transports_metabolite']['description']` starts with `GO defines this molecular-function term`.
- [ ] **Step 3: Unit — wrappers.** `GeneReactionMetaboliteTriplet` has the 9 new fields + verbose `go_chebi_ids`; `go_include_ancestors` param on both tools; `evidence_sources` `Literal` includes `go_transport` (gbm, mbg, list_metabolites); `MetaboliteResult.go_transport_organism_names/_count`; envelope `rows_by_go_term_depth`.
- [ ] **Step 4: Integration (kg)** — Task 2's numbers as assertions: urea MED4 GO rows 11 (urtA 2); PMM0970 mbg GO rows 2 after 4 TCDB; AltDE siderophore includes `MADE_1013240`; MED4 `gene_overview` genes tagged `go_transport` = 59; `metabolites_by_gene(["PMM0261"], "MED4", go_include_ancestors=True)` returns a Lipid (`kegg.compound:C01356`) row with `go_term_depth == 1`, `go_axiom_term_name == "lipid transport"`, while the default call returns no GO rows for PMM0261 (`test_mbg_ancestors_murj_lipid`); plus the five Review Focus tests by name.
- [ ] **Step 5: Edge-case scenarios** — `gbm_go_arm_empty_organism` (an organism with no GO-route genes; pick via discovery Cypher in a comment), `gbm_role_id_no_edges`, `gbm_excluded_target_no_node` (`chebi:23906`), `mbg_ancestors_gene_without_ancestors`.
- [ ] **Step 6: Run** `pytest tests/unit/ -q --tb=no`. Expected: exactly the new tests red, rest green. Unrelated red ⇒ halt.
- [ ] **Step 7: Commit** `test: GO transport surface (red)`.

### Task 4 (Phase 2 GREEN): Four implementers in parallel — one message

Each brief: frozen spec + this task's sub-block + `layer-rules` + "tests are red in your scope; make them green" + the anti-scope-creep guardrail verbatim. Report `DONE` / `DONE_WITH_CONCERNS` / `BLOCKED`.

**4a `query-builder` — `kg/queries_lib.py`**
- [ ] Implement Task 2's two builders and the summary / transport-arm extensions. Inherited branch: dedup per spec §3.3 (emit only (gene, target) pairs with no depth-0 GO path; one row per (gene, own term, target) at min depth).
- [ ] `build_gene_overview` / `build_gene_overview_summary`: add `CASE WHEN EXISTS { MATCH (g)-[:Gene_enables_molecular_function|Gene_involved_in_biological_process]->()-[:Molecular_function_transports_metabolite|Biological_process_transports_metabolite|Molecular_function_transports_chemical_role|Biological_process_transports_chemical_role]->() } THEN ['go_transport']` to `evidence_sources`; widen `has_chemistry` with the same predicate. `metabolomics` tag unchanged.
- [ ] `_list_metabolites_where`: organism clause becomes `ANY(o IN coalesce(m.organism_names, []) + coalesce(m.go_transport_organism_names, []) WHERE toLower(o) IN $organism_names_lc)`; `build_list_metabolites` RETURN adds `go_transport_organism_names`, `go_transport_organism_count`; summary `top_organisms` counts the same union.
- [ ] Self-verify: `pytest tests/unit/test_query_builders.py -q`.

**4b `api-updater` — `api/functions.py` (+ `config/`)**
- [ ] `_VALID_EVIDENCE_SOURCES`, `_GBM`, `_MBG` gain `"go_transport"`; default arms three; Mode 1 / Mode 3 dispatch over three arms; `genes_by_metabolite(..., go_include_ancestors: bool = False)` and `metabolites_by_gene(..., go_include_ancestors: bool = False)` pass `include_ancestors`.
- [ ] `_gbm_sort_key` / `_mbg_sort_key`: order per Task 3 Step 2.
- [ ] `_canonicalize_metabolite_ids(conn, ids, *, roles_are_targets: bool = False)`; `_canonicalize_metabolite_id_params` threads it; gbm / mbg pass `True`.
- [ ] Warnings (exact copy):
  - excluded target: `"'{id}' is excluded from the GO transport route by curation (coupling ion or upper-level class) — an empty GO answer is not biology; TCDB rows still answer."`
  - neurotransmitter: `"chebi.role:25512 (neurotransmitter) on the GO route is mostly bacterial NSS amino-acid transporters, not neurotransmitter transport."`
- [ ] Excluded list read once per process alongside the `kg_release_info` cache; `_KG_IDENTITY_FIELDS` gains `"go_transport_excluded_targets"`.
- [ ] `kg_schema`: load `multiomics_explorer/config/edge_descriptions.yaml` (`{relationship_type: description}`), set `relationships[type]["description"]` when present. Seed with the four paragraphs from `multiomics_biocypher_kg/docs/kg-changes/go-transport-substrates.md` § "Caveat text". `schema_baseline.yaml`: add the four GO edge types and `Tcdb_family_transports_chemical_role` as required.
- [ ] Docstrings per outfacing rules; self-verify `pytest tests/unit/test_api_functions.py -q` and `--lint`.

**4c `tool-wrapper` — `mcp_server/tools.py`**
- [ ] `GeneReactionMetaboliteTriplet` (line ~676): 9 new fields + verbose `go_chebi_ids`, descriptions ≤ 250 chars ("term definition, not a gene fact" on `go_term_id`; BP-broader note on `go_namespace`).
- [ ] `Literal`s: gbm / mbg / list_metabolites (~8180) `evidence_sources` gain `"go_transport"`; descriptions at ~552 / ~646 / ~2340 list four values.
- [ ] `go_include_ancestors` param on both tools; `rows_by_go_term_depth` envelope model on both responses; `MetaboliteResult` gains `go_transport_organism_names` / `_count` (description: absent = no directly annotated gene path, not "no GO edge"); kg_release_info `kg` model gains `go_transport_excluded_targets: list[str] | None`; kg_schema relationship model gains optional `description`.
- [ ] Self-verify `pytest tests/unit/test_tool_wrappers.py -q`.

**4d `doc-updater` — docs**
- [ ] YAMLs: gbm, mbg, gene_overview, list_metabolites, kg_release_info, kg_schema, list_filter_values — examples (urea MED4 urtA; siderophore AltDE; one `go_include_ancestors=True`), mistakes (term definition ≠ gene fact; MED4 `ftn` via BP "iron ion transport"; empty for H⁺/Na⁺ is curation), chaining. Responses via `scripts/refresh_examples.py --write`, never by hand.
- [ ] New `skills/multiomics-kg-guide/references/analysis/transport.md` per spec §3.8; link from `metabolites.md` (four-value prose, "surfaced in gbm/mbg") and the guide.
- [ ] CLAUDE.md rows for the six tools (≤ 700 chars); `kg_claims.yaml` entries for MED4 59 genes and the GO role gene counts.
- [ ] `uv run python scripts/build_about_content.py && … --lint`.

- [ ] **Step 5: Commit** each agent's file set separately: `feat(go-transport): <layer>`.

### Task 5 (Phase 2 VERIFY)

- [ ] **Step 1:** `uv run python scripts/build_about_content.py --lint` → exit 0 (hard gate).
- [ ] **Step 2:** Background code review via `superpowers:requesting-code-review` against the diff + both specs; brief includes the outfacing checks in add-or-update-tool Stage 3 and: no `labels(go)[0]`; GO arm never touches TCDB-only rollups; inherited dedup rule; union filter.
- [ ] **Step 3:** `pytest tests/unit/ -q` → all pass; `uv run python scripts/refresh_examples.py --check` → drift 0.
- [ ] **Step 4:** `pytest tests/regression/ --force-regen -m kg -q`, then classify `git diff --stat tests/regression/`: only gbm / mbg / gene_overview / list_metabolites / kg_schema / kg_release_info goldens may move; each move traces to GO rows, role rows, the union, or new fields. Anything else ⇒ revert and investigate.
- [ ] **Step 5:** `pytest tests/integration/ -m kg -q -p no:cacheprovider` → all pass (incl. edge-case matrix + coverage gate). Pins moved by default-on GO rows are updated with a comment naming this change.
- [ ] **Step 6:** Restart `/mcp`; live-call `genes_by_metabolite(["kegg.compound:C00086"], "MED4")` and `metabolites_by_gene(["PMM0970"], "MED4")` and check the rows against Task 2.
- [ ] **Step 7:** One fix loop on review findings (re-dispatch the owning agent).

### Task 6: Record + close

**Files:** `CHANGELOG.md`, `docs/backlog.md`, `docs/kg-specs/2026-10-18-go-transport-substrates-explorer-asks.md`

- [ ] **Step 1:** CHANGELOG `[Unreleased]` `### Added` (GO arm, role inputs, ancestors flag, kg_schema descriptions, transport recipe) and `### Changed` (default-on GO rows move gbm / mbg totals; mbg TCDB rollups now include role rows; `has_chemistry` widens; `list_metabolites` organism filter = union).
- [ ] **Step 2:** backlog: delete 2c.13; add one line each under 2c for `gene_overview.go_transport_metabolite_count`, GO-arm `go_namespace` / `evidence` filters, `list_organisms` GO counts, per-metabolite `routes` rollup.
- [ ] **Step 3:** Asks doc: append "Explorer surfaced (date)" with the release note for the KG's `mcp_min_version` bump.
- [ ] **Step 4:** `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`.
