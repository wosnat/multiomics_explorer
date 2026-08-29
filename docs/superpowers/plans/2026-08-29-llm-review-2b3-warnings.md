# LLM-review 2b.3 — silent zeros become warnings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every way an LLM commonly mis-calls a tool that today returns an empty-but-valid envelope instead produces a one-line `warnings[]` entry (or a raise, where the plan says so) that names the valid values or the sibling tool — at zero schema cost.

**Architecture:** One shared helper in `api/functions.py` validates closed-vocabulary parameters against the cached `ControlledVocabulary` reader (`_read_vocab_values`) and returns warning strings; a second shared helper coerces bare / wrong-case identifiers to the KG's self-prefixed forms and reports them as `resolved_aliases` (the pattern `list_metabolites` already uses for metabolite IDs). Tools that lack a `warnings` envelope key gain one (`list[str]`, always present). Read `.claude/skills/layer-rules/SKILL.md` and `.claude/skills/testing/SKILL.md` first. Plan 2b.1 Task 6 created `_vocab_warnings(conn, param, values, applies_to, prop, filter_type)` — reuse and generalise it; do not write a second one.

**Tech Stack:** Python 3.12, FastMCP 3, Pydantic v2, pytest.

**Spec:** `docs/backlog.md` item 2b.3; review artifact "Explorer MCP Through an LLM's Eyes" (Theme 4); raw reviews `review_{2..5}_*.md` in the session scratchpad.

## Global Constraints

- Branch `llm-review-2b`; never merge to `main`, never push.
- No tool added or removed. New envelope keys only: `warnings` (where missing), `resolved_aliases` (where a task adds coercion), `not_found_analysis` (`genes_in_cluster`). Never remove a key.
- A warning never changes the rows returned; only the named raises change behaviour (BRITE `tree`, Lucene parse errors).
- Warning text template, verbatim shape: `"<param> value '<v>' matched nothing — valid values: <up to 8, comma-separated>[, …] (list_filter_values(filter_type='<type>'))"`; for organism: `"organism '<v>' matched no organism — see list_organisms()"`; for sibling routing: `"<id> exists as <kind> — use <sibling_tool>"`.
- Every task: `uv run pytest tests/unit -q -p no:cacheprovider` green; named `-m kg` tests green; goldens regenerated only for the named tools after classifying the diff (new empty `warnings: []` / `resolved_aliases: {}` keys are the expected diff); examples refreshed; docs regenerated + `--lint` clean.
- Commit per task: `feat(warnings): <what> (llm-review 2b.3)` + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Shared vocabulary-warning helper across the discovery tools

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — generalise `_vocab_warnings` to a table-driven `_closed_vocab_warnings(conn, **params) -> list[str]` with

```python
_CLOSED_VOCAB_PARAMS: dict[str, tuple[str, str, str]] = {
    # param name: (applies_to label, ControlledVocabulary prop, list_filter_values type)
    "treatment_type": ("Experiment", "treatment_type", "treatment_type"),
    "treatment_types": ("Experiment", "treatment_type", "treatment_type"),
    "background_factors": ("Experiment", "background_factors", "background_factors"),
    "compartment": ("Experiment", "compartment", "compartment"),
    "table_scope": ("Experiment", "table_scope", "table_scope"),
    "growth_phases": ("Experiment", "growth_phase", "growth_phase"),
    "omics_type": ("Experiment", "omics_type", "omics_type"),
    "category": ("Gene", "gene_category", "gene_category"),
    "gene_categories": ("Gene", "gene_category", "gene_category"),
    "cluster_type": ("ClusteringAnalysis", "cluster_type", "cluster_type"),
    "metric_types": None,   # DM metric types are open-ended; handled in Task 3
}
```

  (verify each `(applies_to, prop)` pair against `inputs/lint/vocab_snapshot.yaml`; `gene_category` may be a pivot, which `_read_vocab_values` handles). Scalars and lists both accepted. Apply in: `list_experiments`, `list_publications`, `list_organisms` (compartment), `list_derived_metrics`, `list_clustering_analyses`, `list_metabolite_assays`, `gene_derived_metrics`, `genes_by_numeric_metric`, `genes_by_boolean_metric`, `genes_by_categorical_metric`, `genes_by_function` (category), `genes_by_metabolite` / `metabolites_by_gene` (gene_categories), `gene_clusters_by_gene`, `gene_response_profile`, `differential_expression_by_gene` (already wired by 2b.1 T6 — switch it to the shared helper). Organism zero-match: in every tool where `organism` is word-matched and the resolved set is empty and the tool does not already raise, append the organism warning (use the same resolve query `_validate_organism_inputs` uses, without raising).
- Modify: `mcp_server/tools.py` — response models of the tools above gain `warnings: list[str] = Field(default_factory=list, ...)` where missing.
- Modify: `references/guide/conventions.md` — the envelope section gets three lines: warnings are advisory, never change rows, and name the valid-values tool.
- Test: `tests/unit/test_api_functions.py` (helper unit tests + one per tool asserting the warning string for a bad value and `[]` for a good one), `tests/unit/test_tool_wrappers.py` (models carry the key), `tests/integration/test_param_edge_cases.py` (live: `list_experiments(organism='MED4', treatment_type=['bogus'])` → one warning).

- [ ] **Step 1: Failing tests.** **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** unit → PASS; live edge cases → PASS.
- [ ] **Step 5: Goldens** (every tool above gains `warnings: []` — regenerate that set), examples (`refresh_examples.py --check` → `--write` drifted), docs.
- [ ] **Step 6: Commit** `feat(warnings): closed-vocabulary and organism zero-match warnings on discovery tools (llm-review 2b.3)`.

---

### Task 2: Identifier coercion for terms, groups and locus tags

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — add

```python
_TERM_ID_COERCIONS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(?:kegg\.pathway:)?(?:map|ko)?(\d{5})$"), "kegg.pathway:ko{0}"),
    (re.compile(r"^(?:kegg\.orthology:|kegg:|ko:)?(K\d{5})$", re.I), "kegg.orthology:{0}"),
    (re.compile(r"^(?:go:)?(?:GO:)?(\d{7})$"), "go:{0}"),
    (re.compile(r"^(?:pfam:)?(PF\d{5})$", re.I), "pfam:{0}"),
    (re.compile(r"^(?:interpro:)?(IPR\d{6})$", re.I), "interpro:{0}"),
    (re.compile(r"^(?:tcdb:)?(\d\.[A-Z]\.\d+(?:\.\d+){0,2})$"), "tcdb:{0}"),
    (re.compile(r"^(?:ec:)?(\d+(?:\.(?:\d+|-)){3})$"), "ec:{0}"),
    (re.compile(r"^(?:cazy:)?((?:GH|GT|PL|CE|AA|CBM)\d+(?:_\d+)?)$"), "cazy:{0}"),
    (re.compile(r"^(?:merops\.family:)?([ACGMNPSTUI]\d{2}[A-Z]?)$"), "merops.family:{0}"),
    (re.compile(r"^(?:ncbifam:)?((?:TIGR|NF)\d{5,6})$"), "ncbifam:{0}"),
]
_GROUP_ID_COERCIONS = [
    (re.compile(r"^(?:cyanorak:)?(CK_\d{8})$"), "cyanorak:{0}"),
    (re.compile(r"^(?:eggnog:)?((?:COG|ENOG|[0-9A-Z]{5,7})\d*@\d+)$"), "eggnog:{0}"),
]

def _coerce_ids(ids: list[str], rules) -> tuple[list[str], dict[str, str]]:
    """Return (canonical ids in input order, {input: canonical} for the ones that changed)."""
```

  Verify each canonical form against live IDs (`search_ontology(ontology=..., limit=1)` per ontology; `search_homolog_groups(limit=2)` per source) before finalising the patterns; GO ids in the KG are `go:0006979` (7 digits, lowercase prefix) — confirm. Apply to `term_ids` on `genes_by_ontology`, `ontology_term_details`, `pathway_enrichment`, `cluster_enrichment`, `gene_ontology_terms` (if it takes term ids), and to `group_ids` on `genes_by_homolog_group`, `differential_expression_by_ortholog`. Locus tags: first check live whether any `Gene.locus_tag` contains a lowercase letter (`MATCH (g:Gene) WHERE g.locus_tag <> toUpper(g.locus_tag) RETURN count(g)`); if zero, uppercase-normalise `locus_tags` on every batch tool that takes them and report changed inputs in `resolved_aliases`; if non-zero, instead add a warning when a `not_found` tag differs only by case from an existing one (one extra `toUpper` lookup over the not_found set).
- Modify: `mcp_server/tools.py` — response models gain `resolved_aliases: dict[str, str]` (always present, `{}` when nothing changed) on the tools above; the `term_ids` / `group_ids` / `locus_tags` Field text gains "bare ids are accepted (e.g. `ko00910`, `GO:0006979`, `CK_00000570`)".
- Modify: `references/guide/conventions.md` — the ID-forms paragraph lists the accepted bare forms once.
- Test: `tests/unit/test_api_functions.py::test_coerce_ids_*` (table-driven over every pattern, plus a non-matching input passes through unchanged), one wrapper test per tool, `tests/integration/test_param_edge_cases.py` (live: `genes_by_ontology(term_ids=['ko00910'], organism='MED4')` returns rows and `resolved_aliases == {'ko00910': 'kegg.pathway:ko00910'}`).

- [ ] Steps 1–4 (TDD). **Step 5: Goldens** (new `resolved_aliases: {}` key on the named tools), examples, docs. **Step 6: Commit** `feat(ids): bare term / group / locus-tag ids coerced and reported in resolved_aliases (llm-review 2b.3)`.

---

### Task 3: Derived-metric drill-downs route wrong-kind and impossible filters

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — the three `genes_by_*_metric` functions and `gene_derived_metrics`: when a requested `metric_types` / `derived_metric_ids` entry exists with a different `value_kind`, move it from `not_found_*` to `not_matched_*` and append `"<id> exists as value_kind=<kind> — use genes_by_<kind>_metric"` (the diagnostics builder must look the id up without the `value_kind` predicate; extend `build_*_diagnostics` in `queries_lib.py` accordingly). `genes_by_boolean_metric(flag=False)` on a DM that stores no `not_flagged` edges: keep the DM's `by_metric` row (count 0, `false_count` 0) and warn `"<id> stores positive flags only — flag=False cannot match; read by_metric[*].false_count"`. `genes_by_numeric_metric(organism=X)` when the selected DMs have no edges in X: set `not_matched_organism` (exists, currently null) and warn listing the DMs' organisms.
- Modify: `mcp_server/tools.py` — `genes_by_numeric_metric.bucket` becomes `list[Literal["top_quartile", "upper_middle", "lower_middle", "bottom_quartile"]] | None` (read the exact allowed strings from `list_filter_values`/the KG `metric_bucket` vocabulary — do not guess); drop the prose that listed them.
- Test: unit tests per behaviour (mocked diagnostics rows), `tests/integration/test_param_edge_cases.py` live for the wrong-kind case.

- [ ] Steps 1–4 (TDD). **Step 5:** goldens for the four tools (diff = bucket moves + warnings), examples, docs. **Step 6: Commit** `feat(warnings): DM drill-downs name the sibling for wrong-kind ids, warn on impossible flag/organism filters, bucket is an enum (llm-review 2b.3)`.

---

### Task 4: BRITE requires `tree`; Lucene errors are readable

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — `pathway_enrichment` / `cluster_enrichment`: `if ontology == "brite" and not tree: raise ValueError("ontology='brite' needs tree= (12 trees; see list_filter_values(filter_type='brite_tree')) — a tree-less run mixes taxonomy and function terms.")`. Full-text tools (`genes_by_function`, `search_ontology`, `search_homolog_groups`, `list_metabolites(search_text)`, `list_experiments(search_text)`, `list_publications(search_text)`, `list_clustering_analyses(search_text)`, `list_derived_metrics(search_text)`): wrap the fulltext query call so a Neo4j `ClientError` whose message contains `ParseException` or `queryNodes` becomes `ValueError(f"search_text {search_text!r} is not valid Lucene syntax: <one line from the driver message>. Quote phrases, escape special characters, or drop trailing operators.")`. Where a tool already sanitises the query (search_ontology), append `"search_text was sanitised to '<q>'"` to `warnings` when the sanitised form differs from the input. `genes_by_function`: description gains "multi-word input is OR'd — quote the phrase or join with AND".
- Modify: `mcp_server/tools.py` Field/description text as named.
- Test: unit tests (raise a fake `ClientError` from the mocked conn and assert the ValueError text; BRITE raise), `tests/integration/test_param_edge_cases.py` live for `genes_by_function(search_text='psbA AND')`.

- [ ] Steps 1–4 (TDD). **Step 5:** docs (`mistakes` bullets), no goldens expected to move. **Step 6: Commit** `feat(errors): brite needs tree; Lucene parse errors readable; sanitised-query warning (llm-review 2b.3)`.

---

### Task 5: Remaining silent paths on assays and clusters

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — `list_metabolite_assays(organism=)` and `assays_by_metabolite(organism=)`: when the organism resolves but has zero MetaboliteAssay nodes, warn `"organism '<name>' has no metabolomics assays — organisms with assays: <names>"` (one query: `MATCH (a:MetaboliteAssay) RETURN collect(DISTINCT a.organism_name)`; cache per call). `genes_in_cluster(analysis_id=)` unknown: envelope key `not_found_analysis: str | None` set to the id, plus warning "see list_clustering_analyses(organism=...)". `genes_by_metabolite` / `list_metabolites` given an input that matches no ID pattern (e.g. `'glutamate'`): warn `"'<v>' is not a metabolite id — resolve names with list_metabolites(search_text=...)"`. `list_metabolites(elements=['Nitrogen'])` / lowercase symbols: normalise to element symbols where unambiguous (`n` → `N`), else warn; add `not_found.elements`. `metabolites_by_quantifies_assay` given a boolean assay id and vice versa: move to `not_matched` with the sibling warning (diagnostics lookup without the `value_kind` predicate, same pattern as Task 3).
- Modify: `mcp_server/tools.py` — models gain `not_found_analysis` (`genes_in_cluster`), `not_found.elements` (`list_metabolites`), `warnings` where missing.
- Test: unit per behaviour; live edge cases for the assay-organism and wrong-twin cases.

- [ ] Steps 1–4 (TDD). **Step 5:** goldens (`genes_in_cluster_*`, `list_metabolites_*`, assay tools), examples, docs. **Step 6: Commit** `feat(warnings): assay/cluster/metabolite silent paths report what to call instead (llm-review 2b.3)`.

---

### Task 6: Verification, record, close

- [ ] `uv run python scripts/refresh_examples.py --check` → 0 drift; unit; `tests/integration -m kg`; `tests/regression -m kg`; `git diff --stat tests/regression/` empty.
- [ ] Re-run the review's wrong-call battery live and paste the warning/raise text for each into the report file `.superpowers/sdd/<plan>/task-6-report.md`: bad organism on 3 tools; `treatment_type=['bogus']`; `category='Photosynthesiss'`; `growth_phases=['log']`; `bucket=['top']` (now a validation error); wrong-kind metric type; `flag=False` positive-only; `term_ids=['ko00910']`, `['GO:0006979']`; `group_ids=['CK_00000570']`; `locus_tags=['pmm0001']`; `ontology='brite'` no tree; `search_text='psbA AND'`; `list_metabolite_assays(organism='MED4')`; `genes_in_cluster(analysis_id='nope')`; `metabolites_by_quantifies_assay` with a boolean assay id.
- [ ] CHANGELOG `[Unreleased]` `### Added`: one bullet per task naming the new keys / raises / enum. `docs/backlog.md` — delete row `2b.3`. Commit `chore: close llm-review 2b.3 (CHANGELOG, backlog)`.
