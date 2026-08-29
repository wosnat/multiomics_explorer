# LLM-review 2b.2 — response diet on entry tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the default response of the most-called tools by 2–20k tokens per call by capping envelopes, moving per-timepoint / verbose-only detail behind `verbose`, and setting MCP-side `limit` defaults sized for a context window — with no information lost to a caller who asks for it.

**Architecture:** Defaults and caps change in the MCP wrapper layer (`mcp_server/tools.py`) and in the api layer's envelope builders (`api/functions.py`); the Python package keeps its current defaults where the plan says so (`limit=500` on `genes_by_ontology` stays in `api/`, the MCP wrapper passes 50). Rule for breakdowns: **detail calls (`summary=False`) carry the top-10 entries of every `by_*` / `top_*` list; `summary=True` carries the full list.** Rule for rows: fields that are constant per parent (per DM, per metabolite) or verbose-only are absent on compact rows. Read `.claude/skills/layer-rules/SKILL.md` and `.claude/skills/testing/SKILL.md` first. Generated docs are regenerated with `uv run python scripts/build_about_content.py`; YAML example responses with `uv run python scripts/refresh_examples.py --write <tool>`.

**Tech Stack:** Python 3.12, FastMCP 3, Pydantic v2, pandas (enrichment), pytest.

**Spec:** `docs/backlog.md` item 2b.2; review report artifact "Explorer MCP Through an LLM's Eyes" (Theme 1 table); raw reviews `review_{1..5}_*.md` in the session scratchpad.

## Global Constraints

- Branch `llm-review-2b`; never merge to `main`, never push.
- No tool added or removed. Envelope keys may be added (named below) but never removed; a capped list keeps its key and type.
- `summary=True` output is unchanged by the caps (full lists) unless a task says otherwise.
- Python-package defaults change only where a task names the api function; otherwise the MCP wrapper alone changes.
- Every task: `uv run pytest tests/unit -q -p no:cacheprovider` green; named `-m kg` tests green; goldens regenerated only for the named tools after classifying the diff; `refresh_examples.py --write` for tools whose default response changed; docs regenerated + `--lint` clean.
- Outfacing text: no dates, no changelog words ("now", "previously", "renamed") — the lints enforce it.
- Commit per task: `perf(<area>): <what> (llm-review 2b.2)` + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Compact `experiments[]` on `differential_expression_by_gene`

`api/functions.py` ≈3778-3812 builds `experiments[]` with a nested `timepoints[]` (each carrying `rows_by_status`, `matching_genes`, labels) for every experiment — 25–38 entries × ~400 tokens. `summary=True` for one gene costs 5.5k, MED4 9.2k.

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — the `experiments` loop; the `verbose` parameter already exists on this function (check; if it does not, the MCP wrapper has `verbose` — thread it through).
- Modify: `multiomics_explorer/mcp_server/tools.py` — `differential_expression_by_gene` response model: the per-experiment model's `timepoints` becomes `list[...] | None` with description "per-timepoint breakdown; present only with `verbose=True`"; `experiment_name`, `background_factors`, `table_scope_detail` also verbose-only. Add `n_experiments: int` to the envelope (count before any cap).
- Modify: `inputs/tools/differential_expression_by_gene.yaml` — `verbose_fields` gains the four names; one `mistakes` bullet ("`summary=True` is the cheap landscape; per-timepoint counts need `verbose=True`").
- Test: `tests/unit/test_api_functions.py`, `tests/unit/test_tool_wrappers.py`, `tests/integration/test_tool_correctness_kg.py`.

**Interfaces:**
- Produces: compact experiment entry = `{experiment_id, treatment_type, table_scope, is_time_course, matching_genes, rows_by_status}`; verbose adds `experiment_name, background_factors, table_scope_detail, timepoints[]`. Envelope gains `n_experiments`.

- [ ] **Step 1: Failing unit test.** Using the existing DE unit-test fixture (mocked summary rows with two experiments each with two timepoints): assert compact output entries have no `timepoints` key and no `experiment_name`, `out["n_experiments"] == 2`; with `verbose=True` both keys present.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_api_functions.py -q -k differential_expression_by_gene` → FAIL.
- [ ] **Step 3: Implement.** After building `experiments`, if not `verbose`: `experiments = [{k: v for k, v in e.items() if k in _DE_EXPERIMENT_COMPACT_KEYS} for e in experiments]` with `_DE_EXPERIMENT_COMPACT_KEYS = ("experiment_id", "treatment_type", "table_scope", "is_time_course", "matching_genes", "rows_by_status")`. Set `n_experiments = len(experiments)` before trimming and emit it.
- [ ] **Step 4: Run** unit → PASS; `uv run pytest tests/integration/test_tool_correctness_kg.py -m kg -q -k differential_expression` → PASS; manual: `differential_expression_by_gene(locus_tags=['PMM1171'], summary=True)` ≤ ~1.2k tokens (len(json)/4).
- [ ] **Step 5: Goldens + examples + docs.** `pytest tests/regression -m kg -k differential_expression_by_gene` — diff = dropped keys only; regenerate. `refresh_examples.py --write differential_expression_by_gene`; `build_about_content.py`; `--lint`. Check `analysis/enrichment.py::de_enrichment_inputs` and `examples/*.py` do not read `experiments[*].timepoints` from the compact output (grep `timepoints`); if they do, pass `verbose=True` there.
- [ ] **Step 6: Commit** `perf(expression): compact experiments[] envelope; timepoints behind verbose (llm-review 2b.2)`.

---

### Task 2: Enrichment returns significant rows first, 25 by default

`pathway_enrichment` MCP default `limit=100` returns non-significant filler (7 significant of 100 rows, 24.5k tokens); `cluster_enrichment` defaults to 5. Rows repeat the ~100-char `cluster` key.

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` — `pathway_enrichment` (≈6810-6990) and `cluster_enrichment` (≈6994-): new param `include_nonsignificant: bool = False` (description: "Include rows with `p_adjust ≥ pvalue_cutoff`. Default False — only significant rows are returned; `total_matching` counts all tested rows and `n_significant` the significant ones."); `limit` default 25 on both; keep the `cluster` string unchanged (compareCluster compatibility).
- Modify: `multiomics_explorer/api/functions.py` — the two api functions accept `include_nonsignificant: bool = True` (package default keeps today's behaviour) and filter `result.results` before pagination when False; `total_matching` stays the full count; `n_significant` unchanged.
- Modify: `inputs/tools/pathway_enrichment.yaml`, `cluster_enrichment.yaml` — examples re-run; `mistakes` bullet "no rows ≠ nothing tested: read `n_significant` / `total_matching`; `include_nonsignificant=True` shows the rest".
- Modify: `references/analysis/enrichment.md` — one paragraph in the "reading the output" section.
- Test: `tests/unit/test_api_functions.py`, `tests/unit/test_tool_wrappers.py`, `tests/integration/test_analysis.py`.

**Interfaces:**
- Produces: MCP `pathway_enrichment(...)` / `cluster_enrichment(...)` default rows = significant only, ≤25, sorted as today (by `p_adjust`); `include_nonsignificant=True` restores the full ranked list. Envelope unchanged otherwise.

- [ ] **Step 1: Failing unit tests.** Mock an enrichment result frame with 3 rows (`p_adjust` 0.01, 0.04, 0.5, cutoff 0.05): api call with `include_nonsignificant=False` returns 2 rows, `total_matching == 3`, `n_significant == 2`; wrapper test asserts the MCP default forwards `include_nonsignificant=False` and `limit=25`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** as described; find where `result.results` is sliced by `offset`/`limit` in the api function and filter first: `frame = frame[frame["p_adjust"] < pvalue_cutoff] if not include_nonsignificant else frame`.
- [ ] **Step 4: Run** unit → PASS; live `tests/integration/test_analysis.py -m kg -k enrichment`; manual: the MED4 nitrogen KEGG L1 call ≤ ~3k tokens.
- [ ] **Step 5: Goldens** (`pathway_enrichment_*`, `cluster_enrichment_*` — regression cases call the api layer: check whether they pass `limit`; if the api default keeps `include_nonsignificant=True` the goldens should not move — verify, regenerate only what the wrapper change touches), examples, docs.
- [ ] **Step 6: Commit** `perf(enrichment): significant rows by default, limit 25, include_nonsignificant opt-in (llm-review 2b.2)`.

---

### Task 3: MCP-side `limit` defaults sized for an LLM

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` `limit` defaults: `genes_by_ontology` 500 → 50 (api stays 500; Field text: "Default 50 over MCP; the package default is 500 for TERM2GENE"); `ontology_landscape` None → 15; `gene_ontology_terms` 5 → 50; `genes_in_cluster`, `gene_clusters_by_gene`, `genes_by_numeric_metric`, `genes_by_boolean_metric`, `genes_by_categorical_metric` 5 → 25; `gene_overview`, `gene_details`, `gene_homologs`, `gene_aa_sequence`, `gene_neighbors`: `limit: int | None = None` meaning `max(25, len(locus_tags))` (Field text: "Default: every input gene (min 25). Pass a number to page.") — resolve in the wrapper before calling the api function.
- Modify: each tool's `inputs/tools/*.yaml` where a `mistakes` / `chaining` line quotes the old default (grep `limit` in the YAML).
- Test: `tests/unit/test_tool_wrappers.py` (one assertion per changed default: the wrapper forwards the expected `limit` to the api function), `tests/unit/test_mcp_server.py` if it snapshots the schema.

- [ ] **Step 1: Failing tests** for each default (parametrize over `(tool, kwargs, expected_limit)`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; `uv run pytest tests/integration/test_mcp_tools.py -m kg -q`.
- [ ] **Step 5:** `refresh_examples.py --check` → rewrite drifted tools (`--write`), regenerate docs, lint. Goldens are api-level and should not move; verify with `pytest tests/regression -m kg -q`.
- [ ] **Step 6: Commit** `perf(mcp): limit defaults sized for a context window; batch tools default to the whole batch (llm-review 2b.2)`.

---

### Task 4: Top-10 caps on detail-call breakdowns

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — add

```python
_BREAKDOWN_CAP = 10

def _cap_breakdowns(envelope: dict, keys: tuple[str, ...], *, summary: bool) -> dict:
    """Detail calls carry the first _BREAKDOWN_CAP entries of each breakdown list;
    summary=True keeps the full list. Lists are already sorted by count DESC."""
    if summary:
        return envelope
    for k in keys:
        v = envelope.get(k)
        if isinstance(v, list) and len(v) > _BREAKDOWN_CAP:
            envelope[k] = v[:_BREAKDOWN_CAP]
            envelope[f"{k}_truncated"] = True
    return envelope
```

  and apply it in: `list_experiments` (`by_publication`, `by_metric_type`, `by_organism`, `by_treatment_type`, `by_background_factor`), `list_organisms` (`by_metric_type`, `top_annotation_capability`, `top_metabolic_capability`), `list_publications` (`by_metric_type`, `by_organism`), `resolve_gene` (`by_organism`), `genes_by_function` (`by_organism`), `metabolites_by_gene` (`top_metabolite_pathways` — ALSO sort it by `gene_count DESC, metabolite_count ASC` before capping; `by_element` — keep entries with count ≥ 2, then cap), `genes_by_metabolite` (`top_genes`, `top_reactions`, `top_tcdb_families`), `differential_expression_by_gene` (`experiments`, after Task 1: cap to 10 on detail calls, full on summary). Confirm each list is sorted DESC by its count before slicing; if a builder returns unsorted, sort in the api layer.
- Modify: `mcp_server/tools.py` — the affected response models gain `<key>_truncated: bool | None` fields (sparse; description "True when the list was capped at 10 — `summary=True` returns the full list").
- Modify: `references/guide/conventions.md` — one paragraph under the envelope section: the breakdown cap rule.
- Test: `tests/unit/test_api_functions.py::test_cap_breakdowns_*` (pure function + one tool-level test per tool with a 12-entry mock list).

- [ ] **Step 1: Failing tests.** **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; live `tests/integration/test_tool_correctness_kg.py -m kg`.
- [ ] **Step 5: Goldens** for the nine tools (diff = list length + new `_truncated` keys); examples; docs.
- [ ] **Step 6: Commit** `perf(envelopes): detail calls carry top-10 breakdowns, summary keeps the full list (llm-review 2b.2)`.

---

### Task 5: Compact rows drop parent-constant and verbose-only fields

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — `genes_by_metabolite` / `metabolites_by_gene`: extend the sparse-strip (`_GBM_SPARSE_FIELDS` ≈7309) so that when `verbose=False` the keys `gene_category, metabolite_inchikey, metabolite_smiles, metabolite_mnxm_id, metabolite_hmdb_id, reaction_mnxr_id, reaction_rhea_ids, tcdb_level_kind, tc_class_id` are removed from every row (they are documented as verbose fields already — confirm against the YAML `verbose_fields`). `genes_by_numeric_metric` / `genes_by_boolean_metric` / `genes_by_categorical_metric` (≈4748-): compact rows keep `locus_tag, gene_name, product, derived_metric_id, value` + the rank fields (`rank_by_metric, metric_percentile, metric_bucket` on numeric) — drop `name, value_kind, rankable, has_p_value, organism_name, metric_type` (all present in `by_metric`); verbose keeps everything. `list_derived_metrics` compact row = `derived_metric_id, name, metric_type, value_kind, rankable, organism_name, total_gene_count, allowed_categories`; verbose adds `field_description, experiment_id, publication_doi, compartment, omics_type, background_factors, treatment_type, has_p_value`.
- Modify: `mcp_server/tools.py` response models: the dropped fields become `| None` sparse with "verbose only" in the description; `inputs/tools/*.yaml` `verbose_fields` lists updated.
- Test: unit tests asserting the compact/verbose key sets per tool.

- [ ] Steps 1–4 as above (TDD, unit + `test_tool_correctness_kg -k "metric or metabolite"`).
- [ ] **Step 5: Goldens** for the six tools; examples; docs; check `examples/metabolites.py` and `docs://analysis/*` don't read a dropped key from a compact row (grep the key names in `examples/` and `references/analysis/`).
- [ ] **Step 6: Commit** `perf(rows): compact rows drop parent-constant and verbose-only fields (llm-review 2b.2)`.

---

### Task 6: `kg_schema` accepts `labels` and `section`

**Files:**
- Modify: `multiomics_explorer/kg/schema.py` (introspection ≈115-165) — accept optional `labels: list[str] | None` and `relationship_types: list[str] | None`; when given, sample only those. Also make the property sample deterministic: `MATCH (n:`{label}`) RETURN properties(n) AS props ORDER BY n.id LIMIT 10` (fixes the review-observed non-determinism on abstract labels).
- Modify: `multiomics_explorer/api/functions.py::kg_schema` (≈888) and `mcp_server/tools.py::kg_schema` — params `labels: list[str] | None = None`, `relationship_types: list[str] | None = None`, `section: Literal["nodes", "relationships", "both"] = "both"`. Unknown labels → `not_found_labels` / `not_found_relationship_types` envelope keys (empty lists when clean). Field text on `run_cypher` gains "scope with `kg_schema(labels=[...])`".
- Modify: `inputs/tools/kg_schema.yaml` — replace the two full-dump examples with (a) `kg_schema(labels=['Gene'], section='nodes')` and (b) `kg_schema(section='relationships')` trimmed; `illustrative: false`; regenerate via `refresh_examples.py --write kg_schema`.
- Test: `tests/unit/test_schema.py`, `tests/unit/test_tool_wrappers.py`, `tests/integration/test_mcp_tools.py -k kg_schema`.

- [ ] Steps 1–4 (TDD). **Step 5:** examples/docs; `docs://tools/kg_schema` must drop from ~26k to under ~3k tokens (check `wc -c` on the generated md). **Step 6: Commit** `perf(schema): kg_schema labels/section scoping; deterministic property sampling (llm-review 2b.2)`.

---

### Task 7: Verification, record, close

- [ ] `uv run python scripts/refresh_examples.py --check` → 0 drift; `uv run pytest tests/unit -q -p no:cacheprovider`; `uv run pytest tests/integration -m kg -q -p no:cacheprovider`; `uv run pytest tests/regression -m kg -q`; `git diff --stat tests/regression/` empty.
- [ ] Measure and record in the CHANGELOG bullet: token cost (len(json)/4) before → after for `differential_expression_by_gene(summary=True, 1 gene)`, `pathway_enrichment` (MED4 nitrogen, KEGG L1), `list_experiments(organism='MED4')`, `metabolites_by_gene(['PMM0913'],'MED4')`, `kg_schema(labels=['Gene'])`.
- [ ] CHANGELOG `[Unreleased]` `### Changed`: one bullet per task with the new params / keys (`include_nonsignificant`, `n_experiments`, `*_truncated`, `kg_schema(labels=, section=)`, the new defaults).
- [ ] `docs/backlog.md` — delete row `2b.2`. Commit `chore: close llm-review 2b.2 (CHANGELOG, backlog)`.
