# B2 explorer improvements — triage from pathway-enrichment B2 retrospective

**Date:** 2026-04-25
**Source analysis:** `multiomics_research/analyses/2026-04-20-1243-pathway_enrichment_b2/`
  (`gaps_and_friction.md`, `api_coverage.md`, and the predecessor meta-doc
  `multiomics_research/docs/superpowers/specs/2026-04-18-research-methodology-v3-improvements-from-b2.md` §4.5)
**Predecessor fix:** `de_enrichment_inputs` background-collapse bug — already merged
  in `multiomics_explorer` on 2026-04-20 (B2 KG-data-bug section).
**Scope:** 9 paper-cut items to fix in this round, plus 1 longer-term DAG-awareness track
  captured for later. Each paper-cut card is sized to fit a single tool's
  `add-or-update-tool` pass; the cards are independent and can be batched in any order.

**Skill-content workflow.** Per [skills/layer-rules](.claude/skills/layer-rules/SKILL.md):
**never edit `skills/multiomics-kg-guide/references/tools/*.md` directly** — those files
are generated. The source of truth is `multiomics_explorer/inputs/tools/{tool}.yaml`
(human-authored: examples, mistakes, chaining, verbose_fields) plus the Pydantic models
in `mcp_server/tools.py` (params, response format, envelope keys). After YAML edits,
regenerate with `uv run python scripts/build_about_content.py` — the build script
writes directly to the skills tree, no separate sync step. If a section structure
that the build script doesn't yet support is needed (e.g. a brand-new subsection),
extend `scripts/build_about_content.py` in the same change.

---

## Summary

| # | Tool / surface | Change | Cost | Layers touched |
|---|---|---|---|---|
| 1 | `list_experiments` | Add `experiment_ids: list[str] \| None` filter | M | queries, api, mcp, yaml+regen, tests |
| 2 | `list_experiments` | Surface new KG field `distinct_gene_count` + docstring/yaml on cumulative-vs-distinct semantics | M | queries, api, mcp, yaml+regen, tests |
| 3 | `ontology_landscape` (MCP) | Change MCP `limit` default from `10` to `None`; warn about truncation | S | mcp, yaml+regen, tests |
| 5 | `pathway_enrichment` + `cluster_enrichment` about | Fix hard-coded "returns dict" in `build_about_content.py` for `EnrichmentResult`-returning tools; add `docs://examples/pathway_enrichment.py` cross-reference to both tool descriptions | S | scripts, yaml, mcp tool docstrings, regen+sync |
| 6 | `pathway_enrichment` about | Promote cluster-naming convention (`{exp}\|{tp}\|{direction}`, NaN→`"NA"`) to its own subsection | S | scripts, yaml, regen+sync |
| 7 | `pathway_enrichment` about | Add `term_ids` example for DAG ontologies (paired with `search_ontology`) | XS | yaml, regen+sync |
| 8 | `search_ontology` about | Clarify that BRITE search needs the `tree` filter | XS | yaml, regen+sync |
| 10 | `EnrichmentResult.term2gene` | Class docstring + extend `enrichment.md` §18 columns table with contextual columns | XS | analysis/enrichment.py, references/analysis/enrichment.md |
| 11 | `GeneRef` | Make hashable (so `.overlap_genes()` output drops into `set()`) | S | analysis/enrichment.py, tests |
| LT | `pathway_enrichment` (DAG-aware) | Long-term track — separate spec | L | spec only here |

`#4` and `#9` from the original B2 list:
- `#4` (`ontology_landscape.ontology_kind` field) is folded into the LT track since
  the kind taxonomy only earns its keep once DAG-aware enrichment consumes it.
- `#9` (`omics_type` NaN for Weissberg T) is dropped from this doc — the fix lives
  upstream in `multiomics_biocypher_kg`, not here.

Cost legend: XS ≈ YAML/docstring edit + regen · S ≈ <1 hr (one or two layers, sometimes
includes a small `build_about_content.py` extension) · M ≈ 4-layer pass per
`layer-rules` skill · L ≈ design-bearing.

---

## Cross-cutting checklist anchors

Every tool-touching card follows
[.claude/skills/add-or-update-tool](.claude/skills/add-or-update-tool/SKILL.md)
and its
[checklist](.claude/skills/add-or-update-tool/references/checklist.md).
The cards below list only the items specific to that card; common items below
apply to every relevant card without restating per-card.

**Layer 1-3 changes (cards #1, #2, #3):**
- Per-layer unit tests:
  `tests/unit/test_query_builders.py::TestBuildListExperiments` (or sibling) ·
  `tests/unit/test_api_functions.py::TestListExperiments` (or sibling) ·
  `tests/unit/test_tool_wrappers.py::TestListExperimentsWrapper` (or sibling).
  Update `EXPECTED_TOOLS` if any tool name/signature surface changes.
- Integration tests: `tests/integration/test_mcp_tools.py`,
  `tests/integration/test_api_contract.py` **whenever the return dict shape
  changes** (add/rename/remove field), and
  `tests/integration/test_tool_correctness_kg.py` if the builder signature
  changes.
- Regression / eval: `tests/evals/cases.yaml` + `tests/evals/test_eval.py`
  `TOOL_BUILDERS` + `tests/regression/test_regression.py` `TOOL_BUILDERS`.
  When return columns change, regenerate baselines with
  `pytest tests/regression/ --force-regen -m kg` then verify with
  `pytest tests/regression/ -m kg`.
- API/package exports: confirm `multiomics_explorer/api/__init__.py` and
  `multiomics_explorer/__init__.py` `__all__` are unchanged (no new tool here,
  only modifications) — but verify the names the cards touch are present.
- `CLAUDE.md` MCP Tools table — update the affected tool's row when its
  description (purpose / filters / fields) materially changes.

**About-content changes (cards #5, #6, #7, #8):**
- `tests/unit/test_about_content.py` — runs the build and validates structure.
  When `scripts/build_about_content.py` is modified (cards #5, #6) or new
  YAML sections are introduced, this test must pass.
- `tests/integration/test_about_examples.py` — every `examples:` entry in a
  YAML is exercised against the live KG. Cards #5 and #7 add new examples;
  the integration test must pass with KG running.
- Regen + sync (`scripts/build_about_content.py`)
  is implied for every YAML or build-script change.

**Skill / about-content workflow** (per
[skills/layer-rules](.claude/skills/layer-rules/SKILL.md) and `CLAUDE.md`):
**never edit `multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md`
directly** — those are generated. Edit `multiomics_explorer/inputs/tools/{tool}.yaml`
plus the Pydantic models in `mcp_server/tools.py`, then regen. Analysis docs
under `references/analysis/*.md` (e.g. `enrichment.md`) are hand-authored —
edit directly. If a section structure that the build script doesn't yet
support is needed, extend `scripts/build_about_content.py` in the same change.

**Common gotchas** (mirrored from the add-or-update-tool checklist):
- Don't forget `EXPECTED_TOOLS` in `test_tool_wrappers.py`.
- Don't forget `TOOL_BUILDERS` in `test_eval.py` AND `test_regression.py`
  (separate dicts).
- `test_api_contract.py` captures the pre-change shape and fails silently if
  not updated alongside a return-shape change.
- Every Cypher query needs `ORDER BY` — non-deterministic results break
  regression tests.
- Regression baselines must regenerate with `--force-regen` for any column
  shape change.

---

## Action items

### #1 — `list_experiments`: add `experiment_ids` filter

**What.** Add `experiment_ids: list[str] | None = None` parameter to
[multiomics_explorer/api/functions.py:730](multiomics_explorer/api/functions.py#L730)
and propagate through the query builder, MCP wrapper, and tests.

**Why.** All other "fetch by experiment" tools (`pathway_enrichment`, `ontology_landscape`,
`gene_overview`, `gene_response_profile`, `differential_expression_by_gene`,
`differential_expression_by_ortholog`, etc.) accept `experiment_ids`. The Step-1a pattern
"classify N experiments, fetch metadata for those N" currently requires pulling unfiltered
and local-filtering. Cheap today (~76 experiments) but wasteful as the KG grows, and an
inconsistency that researchers notice immediately.

**Evidence.** v3 meta doc §4.5 A1; B2 `api_coverage.md` MCP-tools row for `list_experiments`.

**Acceptance.**
- Python API: `list_experiments(experiment_ids=[...])` returns only matching rows;
  combines with other filters via AND. Filter applied at Cypher build time
  (Layer 1), not post-hoc in Python.
- MCP wrapper exposes `experiment_ids` with the same shape as on sibling tools
  (`list[str] | None = None`); see `pathway_enrichment` / `ontology_landscape`
  for canonical pattern.
- `not_found: list[str]` field returned in the envelope when any provided ID is
  unknown — mirrors batch behavior on sibling tools. Empty list when all
  matched.
- Behavior under `summary=True`: filter still applied; `total_matching` reflects
  filtered count; `not_found` populated; `results=[]`.
- `inputs/tools/list_experiments.yaml` gains an `examples:` entry using
  `experiment_ids=...` (e.g. classify-then-fetch pattern) and a `chaining:`
  entry showing how it connects to sibling tools. Regenerate.
- `CLAUDE.md` MCP Tools table — `list_experiments` row updated to mention the
  new filter alongside the existing list (organism / treatment / etc.).
- Tests (per cross-cutting anchors above):
  - `test_query_builders` covers single ID, multiple IDs, combined-with-organism,
    empty-input → returns all (treats `None` and `[]` differently — confirm via
    sibling-tool convention before locking).
  - `test_api_functions` covers `not_found` population, summary-mode, organism
    cross-validation if `experiment_ids` span multiple organisms (the
    `_validate_organism_inputs` helper is already used elsewhere; reuse).
  - `test_tool_wrappers` covers Pydantic envelope, `EXPECTED_TOOLS` is unchanged
    (no new tool, just a new param).
  - `test_mcp_tools` integration with the live KG.
  - `test_api_contract` — return shape gains `not_found`; assert presence.
  - `cases.yaml` + `test_eval.py` / `test_regression.py` `TOOL_BUILDERS`
    entries: at least one new case using `experiment_ids`; baselines regenerated
    with `--force-regen`.

**Cost.** M — full 4-layer pass.
**Depends on.** —

---

### #2 — `list_experiments`: surface `distinct_gene_count` + discoverability fix

**KG audit (2026-04-26, post upstream change).** The KG now precomputes
`distinct_gene_count` on every `Experiment` node:

- All 169 experiments populated; no null gaps.
- Invariant `distinct_gene_count <= gene_count` holds (0 violations).
- Time-course experiments where the same gene set is measured at every TP have
  `distinct_gene_count == time_point_totals[0]` (verified on multiple cases).
- One non-TC outlier exists where `distinct_gene_count != gene_count`
  (`carbon_stress_elevated_co2_800_ppm_ez55_rnaseq_coculture`, 2 "TPs",
  distinct=695, cumulative=768) — the math is consistent (multi-condition
  experiment with 73-gene overlap between groups labelled as TPs); curiosity
  not a blocker.

**Existing per-TP surface (unchanged).** Per-TP gene counts already flow through:
- `Experiment` node properties: `gene_count`, `time_point_count`,
  `time_point_totals`, `time_point_significant_up/down`,
  `time_point_labels/orders/hours`, `significant_up_count`,
  `significant_down_count`, plus the new `distinct_gene_count`.
- Top-level `gene_count` is the stored cumulative sum across timepoints
  (verified: NATL2A coculture, 7 TPs × 353 = 2471).
- API surface returns per-TP data: each experiment row carries a `timepoints[]`
  list with `{timepoint, timepoint_order, timepoint_hours, gene_count,
  genes_by_status}` per TP ([api/functions.py:872-899](multiomics_explorer/api/functions.py#L872)).
  `experiments_to_dataframe` flattens to `tp_gene_count`,
  `tp_significant_up/down/not_significant`
  ([analysis/frames.py:84-141](multiomics_explorer/analysis/frames.py#L84)).

**What.** Two parts:

1. **Surface `distinct_gene_count`** through the explorer:
   - `kg/queries_lib.py` `build_list_experiments` (around
     [line 1131](multiomics_explorer/kg/queries_lib.py#L1131)) — add
     `e.distinct_gene_count AS distinct_gene_count` to the RETURN clause.
   - `api/functions.py` `list_experiments`
     ([line 730](multiomics_explorer/api/functions.py#L730)) — pass through
     unchanged in result rows (post-processing already keeps top-level fields
     by default).
   - `mcp_server/tools.py` Pydantic response model — add `distinct_gene_count: int`
     to the per-experiment item schema so the field is part of the published
     contract.
   - `analysis/frames.py` `experiments_to_dataframe` — `distinct_gene_count`
     flows through automatically since `base = {k: v for k, v in exp.items() if
     k not in ("timepoints", "genes_by_status")}` already picks it up. Verify
     with a test; no code change expected.
   - `inputs/tools/list_experiments.yaml` — add an `examples:` entry showing
     `distinct_gene_count` in use (e.g. for filtering / sizing) and a
     `mistakes:` entry contrasting `gene_count` (cumulative) vs
     `distinct_gene_count` (unique). Regenerate via
     `scripts/build_about_content.py`.

2. **Discoverability fix on top-level `gene_count`** (still needed; the
   cumulative-vs-distinct distinction is now explicit thanks to the new field
   but the docstring should call it out):
   - Update `list_experiments` Python API docstring at
     [api/functions.py:748-771](multiomics_explorer/api/functions.py#L748) to
     state that top-level `gene_count` is the cumulative row count across
     timepoints (= `sum(time_point_totals)`), `distinct_gene_count` is the
     unique-gene scalar (suitable for detection-power / pathway-background
     reasoning), and per-TP detail lives in `timepoints[].gene_count` /
     `tp_gene_count`.
   - The same point is covered by the new YAML `mistakes:` entry above.

**Why.** Multi-timepoint experiments have inflated `gene_count` that misleads
pathway-background sizing. Caught in B2 Step 1a — researcher reported "Tolonen
2006 R1 gene_count 10,182" implying ~10k unique genes (MED4 has ~1,700 ORFs).
Now that the KG carries the right scalar, the explorer should expose it.

**Evidence.** B2 `gaps_and_friction.md` "gene_count misreported as cumulative
instead of per-timepoint"; KG-side spec landed 2026-04-26.

**Acceptance.**
- `kg/queries_lib.py` `build_list_experiments` RETURN extended with
  `e.distinct_gene_count AS distinct_gene_count` (Layer 1).
- `api/functions.py` passes through unchanged in result rows; the post-process
  loop already keeps top-level fields by default. Confirm no field popping.
- `mcp_server/tools.py` per-experiment Pydantic Result model gains
  `distinct_gene_count: int = Field(description="Distinct gene count
  across the experiment (= count of distinct gene IDs with ≥1 measurement
  edge, regardless of timepoint). Use this for detection-power / pathway-
  background sizing; contrast with cumulative top-level `gene_count`.")`.
- `analysis/frames.py` `experiments_to_dataframe` test asserts
  `distinct_gene_count` column present (no code change expected — `base = {k:
  v for k, v in exp.items() ...}` picks it up).
- `inputs/tools/list_experiments.yaml` gains a `mistakes:` entry contrasting
  `gene_count` (cumulative) vs `distinct_gene_count` (unique) and an
  `examples:` entry that surfaces both. Regenerate.
- `list_experiments` Python API docstring at
  [api/functions.py:748-771](multiomics_explorer/api/functions.py#L748)
  describes both fields with the cumulative-vs-distinct distinction.
- `CLAUDE.md` MCP Tools table — `list_experiments` row updated to mention
  `distinct_gene_count` in the field list.
- No rename of `gene_count` (back-compat preserved).
- Tests (per cross-cutting anchors):
  - `test_query_builders` asserts the new column in RETURN.
  - `test_api_functions` asserts the field is present on every row,
    `<= gene_count` invariant holds.
  - `test_tool_wrappers` validates Pydantic schema.
  - `test_api_contract` — return shape gains `distinct_gene_count`; update
    assertions.
  - `test_mcp_tools` integration smoke with live KG.
  - Regression baselines regenerated with `--force-regen` (column added →
    golden files change).

**Cost.** M — query builder + Pydantic + YAML + tests + regen.
**Depends on.** KG with `distinct_gene_count` precomputed (landed 2026-04-26 — done).

---

### #3 — `ontology_landscape` MCP: drop the silent `limit=10`

**What.** The Python API at
[multiomics_explorer/api/functions.py:2876](multiomics_explorer/api/functions.py#L2876)
has `limit: int | None = None` (no truncation by default). The MCP wrapper at
[multiomics_explorer/mcp_server/tools.py:4083](multiomics_explorer/mcp_server/tools.py#L4083)
overrides this with `limit: Annotated[int, ...] = 10`. A researcher running the MCP
tool gets a silently-truncated 10-row landscape.

Fix: change the MCP default to `None` (match the Python API), and ensure `truncated=True`
is loud in the response envelope when set. The envelope already includes `truncated`,
but the field surface ranks low in the model's response — a doc note at the top of the
tool's `Response format` section should call it out.

**Why.** B2 Step 1b: `ontology_landscape` is the entry point to ontology selection, and
researchers reach for the unfiltered survey before drilling. Default-to-10 makes the
survey feel done when it isn't. A4 in v3 meta doc.

**Evidence.** v3 meta doc §4.5 A4.

**Acceptance.**
- MCP `ontology_landscape` `limit` parameter defaults to `None` (Pydantic Field
  in `mcp_server/tools.py`). Field type changes from `int` to `int | None` to
  accommodate the new default.
- `inputs/tools/ontology_landscape.yaml` gains a `mistakes:` entry on truncation
  semantics — regenerate.
- Tests:
  - `test_tool_wrappers` `TestOntologyLandscapeWrapper` asserts the new default
    (no automatic 10-row truncation).
  - `test_mcp_tools` integration covers a default-limit call returning all rows
    (or asserts `truncated=False` when no truncation occurs).
  - `cases.yaml` / regression cases that pin `limit=10` are inspected — either
    keep the explicit pin (acceptable) or drop it (now redundant). Document the
    choice.

**Cost.** S — MCP wrapper Pydantic Field + YAML + test fix-ups.
**Depends on.** —

---

### #5 — `pathway_enrichment` docs: fix wrong "Package import equivalent" block

**What.** [scripts/build_about_content.py:307-330](scripts/build_about_content.py#L307-L330)
hard-codes `# returns dict with keys: ...` for every tool. For
`pathway_enrichment` the Python API returns an `EnrichmentResult` object (with
`.results` DataFrame + `.explain()`, `.overlap_genes()`, `.term2gene`,
`.to_envelope()`, `.to_compare_cluster_frame()`, `.generate_summary()` accessors),
not a dict. Two fix shapes:

- **(5a)** Add an optional `python_returns:` field (e.g. `python_returns: "EnrichmentResult"`)
  to the per-tool YAML schema. When present, `build_about_content.py` emits an
  object-shaped example (`result.results`, `result.to_envelope()`) and a pointer to
  `docs://examples/pathway_enrichment.py` instead of `# returns dict ...`. Default
  behavior unchanged for the 20+ tools that do return dicts.
- **(5b)** Auto-detect by inspecting the Python API function's return annotation
  in `multiomics_explorer/api/functions.py`. Cleaner but couples the build script
  to API import paths.

Recommend **(5a)** — explicit per-tool override, smaller blast radius. Set
`python_returns: EnrichmentResult` in `inputs/tools/pathway_enrichment.yaml`, extend
the script's `_build_package_import_section` (or equivalent) to branch on this field,
then regenerate + sync.

**Why.** "Single largest source of confusion during B2 plan review" — researcher
initially thought `experiment_id` wasn't a column on `result.results`, because the
generated block implied a flat dict.

**Evidence.** v3 meta doc §4.5 A2.

**Acceptance.**
- `scripts/build_about_content.py` supports a per-tool `python_returns` override
  (or whichever mechanism is chosen).
- `inputs/tools/pathway_enrichment.yaml` declares `python_returns: EnrichmentResult`
  and the regenerated `pathway_enrichment.md` shows an object-shape example with
  `.results` and `.to_envelope()`, not a dict.
- Build script run; sibling skill docs auto-updated (no separate sync needed —
  build_about_content.py writes directly to the skills tree).
- `cluster_enrichment` (which similarly returns an `EnrichmentResult`) gets the
  same override in the same commit — grep for tools where
  `from multiomics_explorer.analysis.enrichment import EnrichmentResult` appears.
- A regression test (or fixture diff) catches future drift between the YAML
  declaration and the actual return type.
- **Runnable-example cross-reference (folded in).** MCP tool descriptions for
  `pathway_enrichment` and `cluster_enrichment` (the docstrings at
  [mcp_server/tools.py:4193](multiomics_explorer/mcp_server/tools.py#L4193) and
  `:4273`, which `build_about_content.py` surfaces as the tool's "What it does"
  blurb) extended to also point at `docs://examples/pathway_enrichment.py` —
  e.g. "See `docs://analysis/enrichment` for methodology; `docs://examples/pathway_enrichment.py`
  for runnable code." For `cluster_enrichment`, note that the example file
  covers cluster-membership enrichment via the custom-`term2gene` path. The
  pre-existing methodology cross-reference (`docs://analysis/enrichment`) stays.
- Tests (per cross-cutting anchors):
  - `tests/unit/test_about_content.py` — passes after build script change and
    YAML override; assert generated md no longer says "returns dict" for
    `EnrichmentResult`-returning tools.
  - `tests/integration/test_about_examples.py` — examples in
    `pathway_enrichment.yaml` and `cluster_enrichment.yaml` execute against the
    live KG.

**Cost.** S — script change + YAML field + 2 docstring tweaks + regen + sync.
**Depends on.** —

---

### #6 — `pathway_enrichment` docs: cluster-naming convention as its own section

**What.** Cluster identifiers are `{experiment_id}|{timepoint}|{direction}` with
NaN-timepoints rendered as the literal string `"NA"`. This is the lookup key for
`result.explain(cluster, term_id)` and `result.overlap_genes(cluster, term_id)`. Today
it's mentioned only obliquely under `mistakes` in
[inputs/tools/pathway_enrichment.yaml](multiomics_explorer/inputs/tools/pathway_enrichment.yaml).
Promote it to a dedicated section.

Two shapes:

- **(6a)** Add a new YAML field (e.g. `response_notes:` or `cluster_naming:`)
  that `build_about_content.py` renders as a "Cluster naming" subsection under
  Response format. Generic enough to be reused by other tools that have
  drill-down keys (`cluster_enrichment`, future `gene_derived_metrics`).
- **(6b)** Inline-only — keep it under `mistakes` but make the entry the most
  prominent one (lead bullet, more elaborate example).

Recommend **(6a)** — the convention is authoritative, not a mistake to avoid;
"Common mistakes" is structurally the wrong section.

**Why.** Every drill-down pattern with `result.explain()` depends on this convention.
Researchers reaching for `.explain()` either guess the format and fail, or have to
hunt for it. B2 explore phase had this as friction.

**Evidence.** v3 meta doc §4.5 A3.

**Acceptance.**
- New `response_notes` (or chosen name) field supported in `build_about_content.py`,
  rendered as a subsection under Response format.
- `inputs/tools/pathway_enrichment.yaml` populates the field with the canonical
  format, a worked example (`pmm0001|6h|up`), and the NaN→`"NA"` rule.
- Old `mistakes` entry that mentioned the convention removed (now a redirect at most).
- Regenerate via `scripts/build_about_content.py`.
- Tests:
  - `tests/unit/test_about_content.py` — covers the new section structure
    (asserts the subsection renders when YAML field present).

**Cost.** S — YAML field + script extension + regen + sync.
**Depends on.** —

---

### #7 — `pathway_enrichment` docs: add `term_ids` example for DAG ontologies

**What.** Add a new entry under `examples:` in
[inputs/tools/pathway_enrichment.yaml](multiomics_explorer/inputs/tools/pathway_enrichment.yaml)
that shows the `search_ontology` → hand-curated `term_ids` workflow on a `go_*`
ontology, with a minimal MED4 panel. Also add a `mistakes` entry warning that for
DAG ontologies (`go_*`), `level`-only selection silently drops biologically-meaningful
terms at heterogeneous depths.

If the runnable example resource (`docs://examples/pathway_enrichment.py`, served from
`multiomics_explorer/mcp_server/resources.py` or wherever the static resource is
registered) is also kept in sync with the same scenario, update it in the same commit.

**Why.** B2 Step 1b spent debugging cycles believing the tool didn't support
`term_ids` (anti-hallucination near-miss); a worked example would have prevented
the wrong reach. Existing yaml has `term_ids=["cyanorak.role:J", ...]` example for
flat ontology; a sibling DAG example completes the coverage.

**Evidence.** B2 `gaps_and_friction.md` "Step 1b: `pathway_enrichment` level-only
mode for DAG ontologies is a UX refinement opportunity" + the meta-pattern entry
following it.

**Acceptance.**
- New `examples:` entry in `inputs/tools/pathway_enrichment.yaml` titled e.g.
  "Hand-curated DAG-ontology panel via `search_ontology` → `term_ids`", showing
  a 2-3-term MED4 panel.
- New `mistakes:` entry on DAG-vs-flat selection.
- Runnable resource at `docs://examples/pathway_enrichment.py` updated to mirror
  the new example, if it exists.
- Regenerate via `scripts/build_about_content.py`.
- Tests:
  - `tests/integration/test_about_examples.py` — the new example must execute
    against the live KG and return a non-empty enrichment result. Pick `term_ids`
    that have ≥`min_gene_set_size` MED4 members (B2 found `go:0071941` L3 with
    13 MED4 genes; verify before locking).

**Cost.** XS — YAML edits + regen.
**Depends on.** —

---

### #8 — `search_ontology` docs: BRITE `tree` filter requirement

**What.** Add a `mistakes:` entry to
[inputs/tools/search_ontology.yaml](multiomics_explorer/inputs/tools/search_ontology.yaml):
"For BRITE searches, pass `tree=...` (e.g. `tree='transporters'`); without it,
results are dominated by the largest BRITE tree (~1,776 enzyme entries) and rarely
what's wanted. Discover trees via `list_filter_values('brite_tree')`." Also add a
`chaining:` entry for the chain
`list_filter_values('brite_tree')` → `search_ontology(ontology='brite', tree=...)`
if not already present.

**Why.** B2 Step 1b skipped BRITE in the cross-ontology nitrogen search because the
researcher had to know about the `tree` filter from outside the tool. The same warning
is already in `inputs/tools/pathway_enrichment.yaml` and
`inputs/tools/ontology_landscape.yaml`; `search_ontology` deserves the same treatment.

**Evidence.** B2 `api_coverage.md` MCP-tools row for `search_ontology`.

**Acceptance.**
- New `mistakes:` entry in `inputs/tools/search_ontology.yaml` covering the BRITE
  case.
- New (or updated) `chaining:` entry showing the discovery → search chain.
- Regenerate via `scripts/build_about_content.py`.
- Tests:
  - `tests/unit/test_about_content.py` — passes after YAML edit + regen.

**Cost.** XS — YAML edits + regen.
**Depends on.** —

---

### #10 — `EnrichmentResult.term2gene`: enumerate contextual columns + class-docstring touch-up

**Audit (2026-04-25).** Gap is narrower than originally framed:

- `enrichment.md` §18 (lines 580-628, hand-authored) already documents
  `EnrichmentResult` as the return type and `term2gene` as a DataFrame, with a
  required/optional columns table (`term_id, term_name, locus_tag, gene_name,
  product`). Correct as far as it goes.
- `examples/pathway_enrichment.py` already shows `result: EnrichmentResult`,
  uses `result.term2gene` as a DataFrame, and includes a custom-term2gene path.
  No changes needed.
- The `EnrichmentResult` dataclass at
  [analysis/enrichment.py:1128](multiomics_explorer/analysis/enrichment.py#L1128)
  is type-annotated `term2gene: pd.DataFrame`, but the class docstring is the
  one-line "Rich wrapper around Fisher ORA output. See docs://analysis/enrichment."
  No per-field doc, so an IDE hover on `.term2gene` doesn't surface column shape.

**Two narrow gaps to close:**

1. **`enrichment.md` §18 columns table** lists only the required/optional
   columns. When `term2gene` is sourced from `genes_by_ontology`, the DataFrame
   also carries pass-through columns like `gene_category` and `level`
   (B2 observed). Extend the table with a "contextual / source-dependent"
   row group documenting these — explicit that the DataFrame is allowed to be
   wider than the required/optional set.
2. **`EnrichmentResult` class docstring** — replace the one-liner with a short
   field-by-field doc enumerating the shape of `results`, `inputs`, and
   `term2gene` (one line each, plus a `# columns: ...` note for `term2gene`).
   Cross-reference `docs://analysis/enrichment` §18.

Renaming `.term2gene` is **not** in scope (clusterProfiler-aligned name; rename
breaks downstream callers).

**Why.** B2 Step 2 explore: researcher initially expected a dict-like structure
and discovered the DataFrame shape from runtime errors. Documentation in
`enrichment.md` would have caught this if it had been read; the analysis md
needs to stay the canonical answer. The class-docstring touch-up is a small
ergonomic for IDE-driven exploration that doesn't go through the md.

**Evidence.** B2 `api_coverage.md` Python-API-observations row for `term2gene`.

**Acceptance.**
- `enrichment.md` §18 columns table includes a "contextual / source-dependent"
  row block listing `level`, `gene_category` (and any others observed when
  sourced from `genes_by_ontology`), with a note that the DataFrame allows
  additional columns to flow through.
- `EnrichmentResult` class docstring expanded to enumerate `results`, `inputs`,
  `term2gene` (and other key fields like `term_validation`, `params`) with
  one-line shape descriptions. Cross-reference to
  `docs://analysis/enrichment` §18.
- No script regen needed (analysis md is hand-authored; tool md unchanged).

**Cost.** XS — class docstring + analysis md edit.
**Depends on.** —

---

### #11 — `GeneRef`: make hashable

**What.** `GeneRef` (returned by `EnrichmentResult.overlap_genes(...)`) is unhashable,
so the natural pattern `set(result.overlap_genes(c1, t)) & set(result.overlap_genes(c2, t))`
fails. Researchers work around by extracting `.locus_tag` first, but the unhashability
is incidental — the type is conceptually a value object keyed on `(organism, locus_tag)`
or just `locus_tag`.

Add `__hash__` (and confirm `__eq__` is well-defined) on the dataclass. If `GeneRef`
holds mutable fields that should not participate in hashing (e.g. `log2fc` floats),
hash on the identity fields only.

**Why.** B2 Step 2 explore + redundancy audit. Common pattern; small ergonomic win.

**Evidence.** B2 `api_coverage.md` Python-API-observations row.

**Acceptance.**
- `GeneRef` instances are usable in `set()` and dict keys.
- Test in `tests/unit/` (analysis-layer suite — locate `GeneRef` test class
  by grep) covers: two `GeneRef` with same identity fields hash equal; same
  hashes survive a round-trip through `set()`; in-set semantics work for
  `result.overlap_genes(c1, t) ∩ result.overlap_genes(c2, t)` end-to-end on a
  small synthetic enrichment.
- If `frozen=True` is the chosen mechanism, no callers were relying on mutating
  `GeneRef` after construction (grep first across `multiomics_explorer/` and
  `tests/`).
- If `eq` was already auto-generated by `@dataclass`, confirm `frozen=True` /
  `eq=True, hash=True` doesn't break existing equality semantics.

**Cost.** S — code + test, single module.
**Depends on.** —

---

## Long-term track — DAG-aware pathway enrichment

Captured here as a future-work entry, not designed in this round. Combines the
original B2 items #4 (`ontology_landscape.ontology_kind` field) and #12 (DAG-aware
pathway_enrichment) — the kind taxonomy is a small surface piece of the larger
DAG-awareness story and should ship together.

**Sketch.** A DAG-aware mode for `pathway_enrichment` on `go_*` ontologies, with:

1. **Parent-child deduplication.** For a given DE foreground, surface the most-specific
   significant term and dampen parents whose signal is fully explained by the child
   (topGO "elim" / "weight" prior art).
2. **Annotation-sparsity awareness.** For organisms where the DAG has thin annotation
   at deep levels (MED4-class), choose the most-specific level with ≥`min_gene_set_size`
   coverage per subtree dynamically instead of a fixed numeric `level`.
3. **Defined null.** Document the multi-level "pathway background" rigorously
   (full genome? all annotated terms? subtree of a root term?). The current `level=N`
   has a clean answer; multi-level needs an explicit definition before it can ship.
4. **`ontology_kind` field on `ontology_landscape`.** Tag each ontology as `flat`
   (cyanorak_role, tigr_role, cog_category), `tree` (KEGG, BRITE), or `dag` (GO).
   Researcher and `pathway_enrichment` both branch on the kind. This is the small
   item that could ship first if a researcher needed it before the rest, but the
   triage call is to keep it bundled.
5. **Drill-down consistency.** Parent-child rollup semantics in `pathway_enrichment`
   must match `genes_by_ontology` so `result.explain()` works sensibly.

**When to design.** After the 9 paper-cuts land. Will need its own brainstorm + spec
+ plan; expected to be multi-week. Source design lineage: B2 `gaps_and_friction.md`
"design notes for future GO-aware pathway enrichment" — do not lose that text when
this feature gets picked up; it captures statistical and MED4-data-availability
constraints that motivate the choices.

**Status:** captured; not staffed.

---

## Out-of-scope

- **`omics_type` NaN for Weissberg T (B2 #9).** Field is populated for
  non-Weissberg experiments but NaN for Weissberg T experiments in
  `enrichment_all.csv`. Fix lives upstream in `multiomics_biocypher_kg`, not in
  this repo. File in that repo's backlog separately.
- **Methodology / skill-side findings.** B2 surfaced numerous research-methodology
  skill changes (signed-score caps, NC calibration, a-priori-list locking,
  manifest-currency-per-commit, etc.). Those land in `multiomics_research`,
  not here.

---

## Cross-references

- B2 friction log: `multiomics_research/analyses/2026-04-20-1243-pathway_enrichment_b2/gaps_and_friction.md`
- B2 API coverage: `multiomics_research/analyses/2026-04-20-1243-pathway_enrichment_b2/api_coverage.md`
- v3 meta doc §4.5 (API surface gaps): `multiomics_research/docs/superpowers/specs/2026-04-18-research-methodology-v3-improvements-from-b2.md`
- Architecture layer conventions: `skills/layer-rules`
- Tool-update workflow: `add-or-update-tool` skill
