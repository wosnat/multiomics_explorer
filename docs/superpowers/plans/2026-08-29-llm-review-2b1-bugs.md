# LLM-review 2b.1 — confirmed bugs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the ten correctness bugs the 2026-08-29 LLM-consumer review confirmed live, without changing any tool's inventory or row shape beyond the named additions.

**Architecture:** Every fix is local to one of the four layers (`kg/queries_lib.py` builders → `api/functions.py` → `mcp_server/tools.py` wrappers → docs YAML/md). Read `.claude/skills/layer-rules/SKILL.md` and `.claude/skills/testing/SKILL.md` before touching code. Tests: unit (mocked `conn`, no Neo4j) in `tests/unit/`, live in `tests/integration/` under `pytestmark = pytest.mark.kg`. Docs under `multiomics_explorer/skills/**/tools/*.md` and `ontologies/*.md` are GENERATED — edit `inputs/tools/*.yaml`, `inputs/ontologies/*.yaml` or the Pydantic `Field` text, then run `uv run python scripts/build_about_content.py`. Guide / analysis md under `references/guide/`, `references/analysis/` are hand-authored.

**Tech Stack:** Python 3.12, FastMCP 3, Pydantic v2, neo4j driver, pytest (`uv run pytest`).

**Spec:** `docs/backlog.md` item 2b.1; review report artifact "Explorer MCP Through an LLM's Eyes"; raw reviews in the session scratchpad (`review_{1..6}_*.md`).

## Global Constraints

- Branch `llm-review-2b`. Never merge to `main`; never push.
- No new tools; no removed tools; no removed envelope keys. Additions only where the task names them.
- Every task ends green on `uv run pytest tests/unit -q -p no:cacheprovider` (5146+ tests) and on the named `-m kg` tests; the final task runs the full `-m kg` suites.
- Goldens (`tests/regression/`) may only be regenerated for the tools a task names, and only after the diff is classified as the intended change (`pytest tests/regression --force-regen -m kg -k <case>`; `git diff --stat tests/regression/` must list only those files).
- Outfacing text obeys `scripts/build_about_content.py --lint` (no dates, no changelog words, no internal shorthand) — `tests/unit/test_outfacing_lint.py` / `test_docs_lint.py` enforce it.
- Commit after each task: `fix(<area>): <what> (llm-review 2b.1)` + the `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer.

---

### Task 1: `list_filter_values` serves the remaining closed vocabularies

Ten doc sites (7 `Field` descriptions in `tools.py`, `conventions.md:128-132, 314`, `start_here.md:90`) send the LLM to `list_filter_values(filter_type='treatment_type')`, which is not in the Literal enum and raises. The KG holds `ControlledVocabulary` nodes for these (see `multiomics_explorer/inputs/lint/vocab_snapshot.yaml`: `treatment_type` on Experiment / DerivedMetric / MetaboliteAssay / ClusteringAnalysis, `background_factors` on the same four, `table_scope` on Experiment, `detection_status` on `Assay_quantifies_metabolite` (edge), `expression_status` on `Changes_expression_of`).

**Files:**
- Modify: `multiomics_explorer/api/functions.py:1467-1560` (`list_filter_values`) — add branches.
- Modify: `multiomics_explorer/mcp_server/tools.py:1649-1665` — extend the Literal + description.
- Modify: `multiomics_explorer/inputs/tools/list_filter_values.yaml` — one example `list_filter_values(filter_type='treatment_type')` (run `scripts/refresh_examples.py --write list_filter_values` for the response), one chaining line.
- Test: `tests/unit/test_api_functions.py` (find the existing `list_filter_values` cluster_type test and copy its mocking pattern), `tests/unit/test_tool_wrappers.py`, `tests/integration/test_mcp_tools.py`.

**Interfaces:**
- Produces: `filter_type` values `treatment_type`, `background_factors`, `table_scope`, `detection_status`, `expression_status`. Row shape identical to the `cluster_type` branch: `{"value", "applies_to": [labels...], "source"}` plus `description` (per-value, from `value_descriptions`) when the node carries one. For `treatment_type` / `background_factors` the vocabulary lives on four labels — read each `(applies_to, prop)` pair via `_read_vocab_values(conn, label, prop, "node", cache=False)`, union the values, and set `applies_to` to the sorted list of labels that carry the value. Edge-scoped ones use kind `"edge"` with the relationship type as `applies_to`.

- [ ] **Step 1: Failing unit test (api layer).** In `tests/unit/test_api_functions.py`, next to the existing `cluster_type` test, add:

```python
def test_list_filter_values_treatment_type_unions_four_labels(monkeypatch):
    calls = []
    def fake_read(conn, applies_to, prop, kind, *, cache=True):
        calls.append((applies_to, prop, kind))
        vals = {"Experiment": ["nitrogen", "iron"], "DerivedMetric": ["diel"],
                "MetaboliteAssay": ["nitrogen"], "ClusteringAnalysis": ["diel"]}[applies_to]
        return {"values": vals, "value_descriptions": {}, "description": "d", "source": "vocabulary", "warning": None}
    monkeypatch.setattr(api, "_read_vocab_values", fake_read)
    out = api.list_filter_values(filter_type="treatment_type", conn=MagicMock())
    by_value = {r["value"]: r for r in out["results"]}
    assert set(by_value) == {"nitrogen", "iron", "diel"}
    assert by_value["nitrogen"]["applies_to"] == ["Experiment", "MetaboliteAssay"]
    assert {c[0] for c in calls} == {"Experiment", "DerivedMetric", "MetaboliteAssay", "ClusteringAnalysis"}
```

Add the same shape for `table_scope` (single label, `applies_to == ["Experiment"]`) and `detection_status` (kind `"edge"`, `applies_to == ["Assay_quantifies_metabolite"]`).

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_api_functions.py -q -k list_filter_values` → the new tests FAIL with `ValueError: unknown filter_type`.

- [ ] **Step 3: Implement.** In `list_filter_values`, after the `cluster_type` branch add a table-driven branch:

```python
_MULTI_LABEL_VOCABS: dict[str, tuple[str, tuple[str, ...], str]] = {
    # filter_type: (property, applies_to labels/rel types, kind)
    "treatment_type": ("treatment_type", ("Experiment", "DerivedMetric", "MetaboliteAssay", "ClusteringAnalysis"), "node"),
    "background_factors": ("background_factors", ("Experiment", "DerivedMetric", "MetaboliteAssay", "ClusteringAnalysis"), "node"),
    "table_scope": ("table_scope", ("Experiment",), "node"),
    "detection_status": ("detection_status", ("Assay_quantifies_metabolite",), "edge"),
    "expression_status": ("expression_status", ("Changes_expression_of",), "edge"),
}
```

and in the function:

```python
    elif filter_type in _MULTI_LABEL_VOCABS:
        prop, labels, kind = _MULTI_LABEL_VOCABS[filter_type]
        carriers: dict[str, list[str]] = {}
        descs: dict[str, str] = {}
        source = "vocabulary"
        for label in labels:
            read = _read_vocab_values(conn, label, prop, kind, cache=False)
            if read["warning"]:
                warnings_out.append(read["warning"])
            if read["source"] != "vocabulary":
                source = read["source"]
            if envelope_description is None:
                envelope_description = read["description"]
            for v in read["values"]:
                carriers.setdefault(v, []).append(label)
                if v in read["value_descriptions"]:
                    descs.setdefault(v, read["value_descriptions"][v])
        results = [
            {"value": v, "applies_to": sorted(ls), "source": source,
             **({"description": descs[v]} if v in descs else {})}
            for v, ls in sorted(carriers.items())
        ]
```

Check how the `cluster_type` branch initialises `envelope_description` / `warnings_out` and mirror it exactly. Extend the wrapper Literal in `tools.py` with the five names and add "experiment vocabularies (treatment_type, background_factors, table_scope), measurement (detection_status), expression (expression_status)" to the description.

- [ ] **Step 4: Run** the unit tests → PASS. Then live: `uv run pytest tests/integration/test_mcp_tools.py -m kg -q -k list_filter_values` and a manual check that `list_filter_values(filter_type='treatment_type')` returns ≥ 15 values with `applies_to` lists.

- [ ] **Step 5: Docs.** Add the YAML example + run `uv run python scripts/refresh_examples.py --write list_filter_values`, then `uv run python scripts/build_about_content.py` and `--lint`. Verify the ten pointer sites now describe a working call (no text change needed unless they say "or list_experiments(summary=True)" as the *only* route — leave those). `uv run pytest tests/unit -q -p no:cacheprovider` green.

- [ ] **Step 6: Commit** `fix(filters): list_filter_values serves treatment_type / background_factors / table_scope / detection_status / expression_status (llm-review 2b.1)`.

---

### Task 2: Chemistry tools resolve `organism` once and enforce single-organism

`genes_by_metabolite(metabolite_ids, organism)` and `metabolites_by_gene(locus_tags, organism)` pass the raw `organism` word into the builders (word-match, so `'Prochlorococcus'` matches every strain and returns cross-organism rows) and into the existence probe (`functions.py:7580-7589`, exact match on `organism_name`, so `'MED4'` never matches and every found gene is listed in `not_found.locus_tags`).

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — `genes_by_metabolite` (≈6909), `metabolites_by_gene` (≈7340), reuse `_validate_organism_inputs` (≈3592).
- Modify: `multiomics_explorer/mcp_server/tools.py` — the two wrappers' `organism` Field text already says "ambiguous match raises"; confirm and keep.
- Test: `tests/unit/test_api_functions.py`, `tests/integration/test_tool_correctness_kg.py`.

**Interfaces:**
- Consumes: `_validate_organism_inputs(organism, None, None, conn) -> str` (canonical `preferred_name`; raises `ValueError` "no organism matching…" / "matches multiple organisms: …").
- Produces: both functions run every builder and the existence probe with the resolved canonical name; `not_found.organism` is set only when `_validate_organism_inputs` raised "no organism matching" (catch, return the empty envelope with `not_found.organism = organism` — that is the existing contract, keep it); an ambiguous word propagates the `ValueError` (the MCP wrapper turns it into a ToolError).

- [ ] **Step 1: Failing unit tests.**

```python
def test_metabolites_by_gene_probe_uses_resolved_organism(monkeypatch):
    monkeypatch.setattr(api, "_validate_organism_inputs", lambda o, lt, ex, conn: "Prochlorococcus MED4")
    conn = MagicMock()
    seen = []
    def exec_q(cypher, **params):
        seen.append(params)
        if "collect(DISTINCT g.locus_tag) AS found" in cypher:
            return [{"found": ["PMM0920"]}]
        return []            # every other builder: no rows (mock)
    conn.execute_query.side_effect = exec_q
    out = api.metabolites_by_gene(locus_tags=["PMM0920"], organism="MED4", conn=conn)
    probe = [p for p in seen if "locus_tags" in p and "organism" in p][-1]
    assert probe["organism"] == "Prochlorococcus MED4"
    assert out["not_found"]["locus_tags"] == []

def test_genes_by_metabolite_ambiguous_organism_raises(monkeypatch):
    def boom(o, lt, ex, conn):
        raise ValueError("organism 'Prochlorococcus' matches multiple organisms: A, B — be more specific")
    monkeypatch.setattr(api, "_validate_organism_inputs", boom)
    with pytest.raises(ValueError, match="multiple organisms"):
        api.genes_by_metabolite(metabolite_ids=["kegg.compound:C00025"], organism="Prochlorococcus", conn=MagicMock())
```

Read the existing `genes_by_metabolite` unit tests first: they mock `conn.execute_query` with ordered return values; match that style if `side_effect` by cypher text is awkward.

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_api_functions.py -q -k "metabolites_by_gene or genes_by_metabolite"` → new tests FAIL.

- [ ] **Step 3: Implement.** At the top of both functions (after argument validation, before any query):

```python
    try:
        organism_resolved = _validate_organism_inputs(organism, None, None, conn)
    except ValueError as e:
        if "no organism matching" in str(e):
            organism_resolved = None
        else:
            raise
```

When `organism_resolved is None` return the existing empty envelope with `not_found["organism"] = organism` (find where `not_found_org` is set, ≈7157/7266, and short-circuit there). Otherwise pass `organism_resolved` to every `build_*` call and to the probe. Keep the raw `organism` only in the echoed `organism_name`? — no: set the envelope `organism_name` to the resolved name (that is what `differential_expression_by_gene` does).

- [ ] **Step 4: Run** unit tests → PASS; then `uv run pytest tests/integration/test_tool_correctness_kg.py -m kg -q -k "metabolite"` and a manual live check: `metabolites_by_gene(locus_tags=['PMM0920','PMM1512'], organism='MED4')` → `not_found.locus_tags == []`; `genes_by_metabolite(['C00025'], organism='Prochlorococcus')` raises with the strain list.

- [ ] **Step 5: Goldens.** `uv run pytest tests/regression -m kg -q -k "genes_by_metabolite or metabolites_by_gene"`; any diff must be only `organism_name` becoming the canonical name or `not_found.locus_tags` emptying. Regenerate exactly those.

- [ ] **Step 6: Commit** `fix(chemistry): resolve organism once; enforce single-organism on genes_by_metabolite / metabolites_by_gene (llm-review 2b.1)`.

---

### Task 3: Enrichment rows carry real experiment metadata

`analysis/enrichment.py::de_enrichment_inputs` (≈548) copies `_METADATA_FIELDS` (≈519: `name`, `omics_type`, `table_scope`, `background_factors`, `is_time_course`, …) from DE rows that do not carry them, so every `pathway_enrichment` row has five nulls and `by_omics_type` is always `[]`.

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py:548-760`.
- Test: `tests/unit/test_enrichment.py`, `tests/integration/test_analysis.py`.

**Interfaces:**
- Consumes: `api.list_experiments(experiment_ids=[...], organism=<resolved>, limit=len(ids), conn=conn)` → rows with `experiment_id`, `experiment_name`, `omics_type`, `table_scope`, `background_factors`, `is_time_course` (check the exact row keys in `api/functions.py::list_experiments` before writing; `name` in `_METADATA_FIELDS` maps from `experiment_name`).
- Produces: `EnrichmentInputs.cluster_metadata[cluster]` populated for those five keys; `by_omics_type` non-empty on a real run.

- [ ] **Step 1: Failing unit test.** In `tests/unit/test_enrichment.py` find the existing `de_enrichment_inputs` test that mocks `differential_expression_by_gene`; add a mock for `list_experiments` returning one row per experiment with `omics_type="proteomics"`, `table_scope="all_detected_genes"`, `experiment_name="X"`, `background_factors=["axenic"]`, `is_time_course=False`; assert `inputs.cluster_metadata[any_cluster]["omics_type"] == "proteomics"` and `["table_scope"] == "all_detected_genes"`.

- [ ] **Step 2: Run** → FAIL (values are `None`).

- [ ] **Step 3: Implement.** In `de_enrichment_inputs`, after the DE call and before the metadata loop (≈685):

```python
    from multiomics_explorer.api import functions as _api  # local import: analysis must not import api at module load if that creates a cycle — check the file's existing imports first
    exp_meta_rows = _api.list_experiments(
        experiment_ids=list(experiment_ids), organism=organism,
        limit=len(experiment_ids), conn=conn,
    )["results"]
    exp_meta = {r["experiment_id"]: r for r in exp_meta_rows}
```

and in the per-cluster loop set `md["name"] = exp_meta.get(eid, {}).get("experiment_name")`, and the other four from the same row, falling back to the DE-row value when present. Keep `_METADATA_FIELDS` as the canonical key list.

- [ ] **Step 4: Run** unit → PASS; live: `uv run pytest tests/integration/test_analysis.py -m kg -q -k enrichment`; manual `pathway_enrichment(organism='MED4', experiment_ids=[<one nitrogen id>], ontology='kegg', level=1)` → rows have `omics_type`, `table_scope` set and `by_omics_type` non-empty.

- [ ] **Step 5: Goldens.** `pathway_enrichment_*` cases will change only in those five columns + `by_omics_type`; classify, regenerate those only. Update `inputs/tools/pathway_enrichment.yaml` examples via `refresh_examples.py --write pathway_enrichment`; regenerate docs.

- [ ] **Step 6: Commit** `fix(enrichment): merge experiment metadata into DE-derived enrichment rows (llm-review 2b.1)`.

---

### Task 4: Enrichment tools fail loudly on unknown IDs and out-of-range `level`

`pathway_enrichment(experiment_ids=['nope'])` and `cluster_enrichment(analysis_id='nope')` return a complete empty envelope with `not_found: []`; `pathway_enrichment(level=9)` on KEGG reports `clusters_skipped[*].reason == "no_pathways_in_size_range"`.

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — `pathway_enrichment` (≈5986-6170), `cluster_enrichment` (≈6201-).
- Modify: `multiomics_explorer/analysis/enrichment.py` — `de_enrichment_inputs` surfaces `not_found_experiments` (it already reads `de_full.get("not_found_experiments")`? verify at ≈759; if not, add), `cluster_enrichment_inputs` (≈815-830) already fills `not_found=[analysis_id]`.
- Modify: `multiomics_explorer/kg/queries_lib.py` — add `build_ontology_max_level(ontology)` returning `("MATCH (t:`{label}`) RETURN max(t.level) AS max_level", {})` using `ONTOLOGY_CONFIG[ontology]["label"]`.
- Test: `tests/unit/test_api_functions.py`, `tests/unit/test_query_builders.py`, `tests/integration/test_param_edge_cases.py`.

**Interfaces:**
- Produces: `ValueError` messages, verbatim:
  - `"experiment_ids not found: ['nope']. Get ids from list_experiments(organism='<organism>')."` — raised only when EVERY input id is unknown; a partial batch keeps running and lists the unknown ones in `not_found_experiments` (add that key to the `pathway_enrichment` envelope if absent — it exists on `differential_expression_by_gene`, mirror it).
  - `"analysis_id not found: 'nope'. Get ids from list_clustering_analyses(organism='<organism>')."`
  - `"level 9 is out of range for ontology 'kegg' (levels 0–3; 0 = root)."` — checked once per call, before any gene-set query; flat ontologies (max level 0) get `(levels 0 only — this ontology is flat)`.
  - New `clusters_skipped` reason `"no_terms_at_level"` is NOT needed once the raise exists; leave reasons untouched.

- [ ] **Step 1: Failing unit tests** (mock `conn.execute_query` so the DE / cluster call returns an empty result with `not_found_experiments=["nope"]` / cluster `not_found=["nope"]`; and one where the max-level query returns `{"max_level": 3}` with `level=9`):

```python
def test_pathway_enrichment_all_unknown_experiments_raises(monkeypatch):
    monkeypatch.setattr(api, "_validate_organism_inputs", lambda *a, **k: "Prochlorococcus MED4")
    monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 3)
    fake_inputs = SimpleNamespace(gene_sets={}, background={}, cluster_metadata={}, not_found=[], not_matched=[], no_expression=[], not_found_experiments=["nope"], clusters_skipped=[])
    monkeypatch.setattr(api, "de_enrichment_inputs", lambda *a, **k: fake_inputs)
    with pytest.raises(ValueError, match=r"experiment_ids not found: \['nope'\]"):
        api.pathway_enrichment(organism="MED4", experiment_ids=["nope"], ontology="kegg", level=1, conn=MagicMock())

def test_pathway_enrichment_level_out_of_range_raises(monkeypatch):
    monkeypatch.setattr(api, "_validate_organism_inputs", lambda *a, **k: "Prochlorococcus MED4")
    monkeypatch.setattr(api, "_ontology_max_level", lambda ontology, conn: 3)
    with pytest.raises(ValueError, match=r"level 9 is out of range for ontology 'kegg' \(levels 0–3"):
        api.pathway_enrichment(organism="MED4", experiment_ids=["x"], ontology="kegg", level=9, conn=MagicMock())
```

Read how the existing `pathway_enrichment` unit tests patch `de_enrichment_inputs` (the name it is imported under in `functions.py`) and use that exact attribute path.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement.** Add to `functions.py`:

```python
_MAX_LEVEL_CACHE: dict[str, int] = {}

def _ontology_max_level(ontology: str, conn) -> int:
    if ontology not in _MAX_LEVEL_CACHE:
        cypher, params = build_ontology_max_level(ontology)
        rows = conn.execute_query(cypher, **params)
        _MAX_LEVEL_CACHE[ontology] = int((rows[0]["max_level"] if rows else 0) or 0)
    return _MAX_LEVEL_CACHE[ontology]
```

In `pathway_enrichment` and `cluster_enrichment`, right after organism validation and only when `level is not None`:

```python
    max_level = _ontology_max_level(ontology, conn)
    if level < 0 or level > max_level:
        rng = f"levels 0–{max_level}; 0 = root" if max_level else "levels 0 only — this ontology is flat"
        raise ValueError(f"level {level} is out of range for ontology '{ontology}' ({rng}).")
```

After `inputs = de_enrichment_inputs(...)`: `if inputs.not_found_experiments and len(inputs.not_found_experiments) == len(experiment_ids): raise ValueError(...)`. Add `not_found_experiments: list[str] = field(default_factory=list)` to `EnrichmentInputs` if missing and populate it from `de_full["not_found_experiments"]`. Mirror for `cluster_enrichment` using `inputs.not_found`. Add `not_found_experiments` to the enrichment envelope + `EnrichmentResult` model where `not_found` is emitted (≈1374). Note the BRITE `tree` facet: max level must be computed on the same label; BRITE levels are per tree — use `max(t.level)` over the label (a looser bound is fine).

- [ ] **Step 4: Run** unit → PASS. Live: `uv run pytest tests/integration/test_param_edge_cases.py -m kg -q -k enrichment`; manual: the three raises above, plus `pathway_enrichment(..., ontology='cog_category', level=0)` still works (flat).

- [ ] **Step 5: Docs.** Add a `mistakes` bullet to `inputs/tools/pathway_enrichment.yaml` and `cluster_enrichment.yaml` ("unknown ids / out-of-range level raise; partial batches list the unknown ids in `not_found_experiments`"); regenerate. Goldens: envelope gains `not_found_experiments: []` on every `pathway_enrichment_*` case — classify, regenerate all of that family.

- [ ] **Step 6: Commit** `fix(enrichment): raise on all-unknown ids and out-of-range level; surface not_found_experiments (llm-review 2b.1)`.

---

### Task 5: Tested-absent assay rows carry no rank; `assays_by_metabolite(summary=True)` buckets from the full match set

Rows with `detection_status == 'not_detected'` (value 0) tie into `metric_bucket='top_quartile'`, `metric_percentile≈78` because ~78 % of values are zero. And `assays_by_metabolite(summary=True)` derives `not_matched` / `metabolites_without_evidence` from the (empty) page, reporting the matched metabolite as unmatched.

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — `metabolites_by_quantifies_assay` (search `def metabolites_by_quantifies_assay`) and `assays_by_metabolite` (≈8546-8712).
- Modify: `multiomics_explorer/inputs/tools/metabolites_by_quantifies_assay.yaml`, `assays_by_metabolite.yaml` — one `mistakes` bullet each; `references/analysis/metabolites.md` — one sentence in the tested-absent section.
- Test: `tests/unit/test_api_functions.py`, `tests/integration/test_two_state_invariants.py` (add the invariant: no row with `detection_status == 'not_detected'` has a non-null `metric_bucket`).

**Interfaces:**
- Produces: on both tools, for every result row where `detection_status == "not_detected"`: `metric_bucket = None`, `metric_percentile = None`, `rank_by_metric = None` (post-query, in the api layer; the KG values stay untouched). Filters `metric_bucket=` / `metric_percentile_min=` / `rank_by_metric_max=` keep their current semantics (they select on the stored value — document that they therefore never return tested-absent rows once the display fields are nulled; simplest consistent rule: add `AND r.detection_status <> 'not_detected'` to those three filter conditions in `queries_lib.py:10094-10102` and the `assays_by_metabolite` twin if it has them).
- `assays_by_metabolite`: `metabolites_matched`, `not_matched`, `metabolites_without_evidence` computed from the unpaged summary query, not from `results`.

- [ ] **Step 1: Failing unit tests.** Mock the row query to return one `not_detected` row with `metric_bucket="top_quartile"`, assert the api output has `None` for the three fields. For the summary bug: mock the summary row with `metabolites_matched=1` and an empty page; assert `not_matched == []` and `metabolites_without_evidence == []`.

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement.** A small helper used by both functions:

```python
_RANK_FIELDS = ("metric_bucket", "metric_percentile", "rank_by_metric")

def _null_rank_on_absent(rows: list[dict]) -> list[dict]:
    for r in rows:
        if r.get("detection_status") == "not_detected":
            for k in _RANK_FIELDS:
                if k in r:
                    r[k] = None
    return rows
```

For the summary bug, read ≈8654-8712: the identifiers for `not_matched` must come from a query over the matched set (there is a diagnostics builder for the numeric twin at `queries_lib.py:10107` — mirror it for `assays_by_metabolite` if none exists), never from `results`.

- [ ] **Step 4: Run** unit → PASS; live invariant test → PASS; manual `assays_by_metabolite(['C00025'], summary=True)` → `not_matched == []`.

- [ ] **Step 5: Docs + goldens.** Regenerate examples for the two tools (`refresh_examples.py --write`), docs, goldens for `assays_by_metabolite_*` / `metabolites_by_quantifies_assay_*` (diff = only the three fields on absent rows and the summary buckets).

- [ ] **Step 6: Commit** `fix(assays): no rank fields on tested-absent rows; summary buckets from the full match set (llm-review 2b.1)`.

---

### Task 6: DE tools report vocabulary typos instead of `no_expression`

`differential_expression_by_gene(growth_phases=['log'])` / `gene_response_profile(treatment_types=['Fe'])` return 0 rows and file the gene under `no_expression` ("gene exists, no expression edges") — false. Neither tool has `warnings`.

**Files:**
- Modify: `multiomics_explorer/api/functions.py` — `differential_expression_by_gene` (≈3700-3880) and `gene_response_profile` (≈4130-4290).
- Modify: `multiomics_explorer/mcp_server/tools.py` — the two response models gain `warnings: list[str]` and `filtered_out: list[str]`; `Field` text for `growth_phases` on DE-by-gene gains the `list_filter_values(filter_type='growth_phase')` pointer its siblings have.
- Test: `tests/unit/test_api_functions.py`, `tests/unit/test_tool_wrappers.py`, `tests/integration/test_param_edge_cases.py`.

**Interfaces:**
- Consumes: `_read_vocab_values(conn, "Experiment", "treatment_type", "node")` and `(…, "growth_phase", …)` — check `vocab_snapshot.yaml` for the exact `(applies_to, prop)` pair that carries `growth_phase` (it may be a timepoint-level property; if no ControlledVocabulary node exists, use the pivot fallback `_read_vocab_values` already does and accept its warning).
- Produces, on both tools: envelope key `warnings: list[str]` (always present, `[]` when clean) with one entry per unknown value: `"growth_phases value 'log' is not in the vocabulary (valid: exponential, stationary, …) — see list_filter_values(filter_type='growth_phase')"`; envelope key `filtered_out: list[str]` — genes that exist and have expression edges but zero rows after the vocabulary filters. `no_expression` keeps its exact meaning (no edges at all). Rule: a gene goes to `no_expression` only if it has no `Changes_expression_of` edge in the organism; if it has edges but the filtered query returned nothing, it goes to `filtered_out`.

- [ ] **Step 1: Failing unit tests.** Mock the diagnostics query so `has_expression` contains the gene while the filtered rows are empty; assert `out["filtered_out"] == ["PMM1171"]` and `out["no_expression"] == []`. Mock `_read_vocab_values` to return `["exponential", "stationary"]`; call with `growth_phases=["log"]`; assert `out["warnings"][0].startswith("growth_phases value 'log' is not in the vocabulary")`.

- [ ] **Step 2: Run** → FAIL (`KeyError: 'warnings'`).

- [ ] **Step 3: Implement.** Read ≈3828 (`no_expression = diag_raw["no_expression"]`) and ≈4188: the diagnostics query must report edge existence *unfiltered*; check `build_differential_expression_by_gene_diagnostics` (or whatever the builder is named — grep `no_expression` in `queries_lib.py`) — if it already applies the vocabulary filters, add an unfiltered `has_any_edge` collection to it. Then:

```python
    filtered_out = [lt for lt in found_genes if lt in has_any_edge and lt not in has_expression]
    no_expression = [lt for lt in found_genes if lt not in has_any_edge]
```

Vocabulary warnings:

```python
def _vocab_warnings(conn, param: str, values: list[str] | None, applies_to: str, prop: str, filter_type: str) -> list[str]:
    if not values:
        return []
    read = _read_vocab_values(conn, applies_to, prop, "node")
    valid = set(read["values"])
    bad = [v for v in values if v not in valid]
    if not bad:
        return []
    shown = ", ".join(sorted(valid)[:8]) + (", …" if len(valid) > 8 else "")
    return [f"{param} value '{v}' is not in the vocabulary (valid: {shown}) — see list_filter_values(filter_type='{filter_type}')" for v in bad]
```

(`filter_type='treatment_type'` works after Task 1.) Add the two keys to both Pydantic response models with `Field(default_factory=list, description=...)`.

- [ ] **Step 4: Run** unit → PASS; live edge cases → PASS; manual: `differential_expression_by_gene(locus_tags=['PMM1171'], growth_phases=['log'])` → `filtered_out == ['PMM1171']`, one warning.

- [ ] **Step 5: Docs + goldens.** `mistakes` bullets in both tool YAMLs; conventions partial-failure table gains `filtered_out` (Task 7 owns the other conventions edits — coordinate: this task adds only the one table row). Goldens for `differential_expression_by_gene_*` / `gene_response_profile_*` gain two empty keys — regenerate that family.

- [ ] **Step 6: Commit** `fix(expression): vocabulary typos warn and land in filtered_out, never no_expression (llm-review 2b.1)`.

---

### Task 7: Documentation corrections

Pure text, hand-authored + Field strings; no behaviour change.

**Files:**
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/guide/conventions.md:399` — replace ``(`metric_bucket`, `metric_percentile_*`, `rank_by_metric_max`)`` with ``(`bucket`, `min_percentile` / `max_percentile`, `max_rank` — they populate the row fields `metric_bucket`, `metric_percentile`, `rank_by_metric`; the assay twins spell the same filters `metric_bucket`, `metric_percentile_min` / `_max`, `rank_by_metric_max`)``. Also the partial-failure table: add the row "tool-specific diagnostic buckets — `wrong_ontology`, `wrong_level`, `filtered_out` (`genes_by_ontology`); `no_expression`, `filtered_out`, `not_found_experiments` (DE tools); `no_groups` (`gene_homologs`)".
- Modify: `references/guide/python_api.md:252-254` — replace the three fake IDs with two real MED4 nitrogen experiment IDs (get them live: `list_experiments(organism='MED4', treatment_type=['nitrogen'], limit=3)`), keeping the `early_N` / `late_N` group labels.
- Modify: `CLAUDE.md:48` — `genes_by_function` row: `category` (singular scalar), not `gene_categories`; `CLAUDE.md:92` and `conventions.md:607`, `start_here.md:125`, `concepts.md:250` — write `subcellular_localization` (PSORTb) / `signal_peptide_type` (SignalP) wherever the prose names the keys as "PSORTb / SignalP".
- Modify: `mcp_server/tools.py:4374, 4478, 5082, 5177` — the table_scope sentence becomes: "any other scope (`significant_only`, `significant_any_timepoint`, `filtered_subset`, `top_n`) collapses tested-absent with not-detected".
- Modify: `tools.py` `differential_expression_by_gene.organism` Field — replace "a genus word like 'Alteromonas' matches every strain" with "a genus word that matches several strains raises — name the strain" (single-organism tool).
- Test: `uv run pytest tests/unit -q -p no:cacheprovider` (docs lints), `scripts/build_about_content.py --lint`.

- [ ] **Step 1:** Make the edits (use `grep -n` to confirm each line before editing; line numbers drift after Tasks 1–6).
- [ ] **Step 2:** `uv run python scripts/build_about_content.py && uv run python scripts/build_about_content.py --lint && uv run pytest tests/unit -q -p no:cacheprovider` → green. `uv run python examples/pathway_enrichment.py --scenario de` still runs (python_api IDs are prose only, but check nothing else references the fake IDs: `grep -rn GSE37441 --include=*.md --include=*.py .`).
- [ ] **Step 3: Commit** `docs: DM filter names, real experiment ids, genes_by_function param, table_scope names, ontology keys for PSORTb/SignalP (llm-review 2b.1)`.

---

### Task 8: Verification, record, close

- [ ] **Step 1:** `uv run python scripts/refresh_examples.py --check` → 0 drift (fix with `--write <tool>` only where a task above changed the response).
- [ ] **Step 2:** `uv run pytest tests/unit -q -p no:cacheprovider` → green; `uv run pytest tests/integration -m kg -q -p no:cacheprovider` → green; `uv run pytest tests/regression -m kg -q` → green; `git diff --stat tests/regression/` empty.
- [ ] **Step 3:** CHANGELOG `[Unreleased]` → `### Fixed`: one bullet per task (1–7), naming the tool and the observable change (new envelope keys `filtered_out`, `warnings`, `not_found_experiments`; new `list_filter_values` types; the raises).
- [ ] **Step 4:** `docs/backlog.md` — delete row `2b.1`.
- [ ] **Step 5:** Commit `chore: close llm-review 2b.1 (CHANGELOG, backlog)`.
