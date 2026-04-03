# treatment_type → array + background_factors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt multiomics_explorer to the new KG schema where `Experiment.treatment_type` is an array (was scalar string) and `background_factors` is a new array property on Experiment, GeneCluster, Publication, and OrganismTaxon nodes.

**Architecture:** Two independent changes: (A) fix all Cypher that treats `e.treatment_type` as scalar, and (B) surface `background_factors` as a new filterable/displayable field. The changes propagate bottom-up through queries_lib → api/functions → mcp_server/tools. Few-shot examples in queries.py also need updating.

**Tech Stack:** Python, Neo4j Cypher (APOC), Pydantic, FastMCP, pytest

---

## Scope & Impact Summary

### A. treatment_type scalar→array (BREAKING)

Every Cypher pattern that treats `e.treatment_type` as a scalar string must change:

| Pattern | Before | After |
|---|---|---|
| Equality filter | `toLower(e.treatment_type) IN $treatment_types` | `ANY(t IN e.treatment_type WHERE toLower(t) IN $treatment_types)` |
| Frequency aggregation | `collect(e.treatment_type)` | `apoc.coll.flatten(collect(coalesce(e.treatment_type, [])))` |
| Direct return | `e.treatment_type AS treatment_type` | `e.treatment_type AS treatment_type` (OK — already returns list, but downstream Pydantic model must change `str → list[str]`) |
| group_by key | `e.treatment_type` (scalar) | Needs UNWIND to produce one row per treatment_type value |
| Few-shot examples | `{treatment_type: 'coculture'}`, `e.treatment_type = $treatment_type` | `'coculture' IN e.treatment_type`, `ANY(t IN e.treatment_type WHERE t = $treatment_type)` |

### B. background_factors (NEW)

New `str[]` property on Experiment, GeneCluster, Publication, OrganismTaxon. May be null.

- **Filter parameter**: Add `background_factors: list[str] | None` to experiment-based tools
- **Return field**: Include in results where treatment_type already appears
- **Summary breakdown**: Add `by_background_factors` where `by_treatment_type` exists
- **list_organisms / list_publications**: Return the pre-computed `background_factors` list

---

## File Map

| File | Changes |
|---|---|
| `multiomics_explorer/kg/queries_lib.py` | Fix all scalar treatment_type Cypher; add background_factors filter/return/aggregation |
| `multiomics_explorer/kg/queries.py` | Update few-shot example Cypher and explanations |
| `multiomics_explorer/api/functions.py` | Add background_factors params; update treatment_type summary builders; add by_background_factors |
| `multiomics_explorer/mcp_server/tools.py` | Update Pydantic models (treatment_type: str → list[str]); add background_factors fields/params |
| `multiomics_explorer/inputs/tools/*.yaml` | Update examples for array treatment_type; add background_factors |
| `docs/tool-specs/*.md` | Update parameter docs and examples |
| `tests/unit/test_query_builders.py` | Update expected Cypher patterns |
| `tests/integration/test_mcp_tools.py` | Update assertions for array treatment_type; add background_factors tests |
| `tests/integration/test_api_contract.py` | Update contract assertions |
| `tests/regression/` | Regenerate baselines |
| `CLAUDE.md` | Update tool table if needed |

---

## Task 1: Update queries_lib.py — Experiment filter helpers

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:740-790` (`_list_experiments_where`)
- Modify: `multiomics_explorer/kg/queries_lib.py:2443-2462` (`_gene_response_profile_where`)
- Test: `tests/unit/test_query_builders.py`

The filter condition `toLower(e.treatment_type) IN $treatment_types` treats treatment_type as scalar. Must change to array-aware pattern.

- [ ] **Step 1: Write failing test for _list_experiments_where treatment_type filter**

```python
def test_list_experiments_where_treatment_type_array_filter():
    """treatment_type is now an array — filter must use ANY()."""
    cypher, params = build_list_experiments(
        treatment_type=["coculture", "nitrogen_stress"],
    )
    # Must NOT contain the old scalar pattern
    assert "toLower(e.treatment_type) IN" not in cypher
    # Must contain array-aware pattern
    assert "ANY(t IN e.treatment_type WHERE toLower(t) IN $treatment_types)" in cypher
    assert params["treatment_types"] == ["coculture", "nitrogen_stress"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_query_builders.py::test_list_experiments_where_treatment_type_array_filter -v`
Expected: FAIL — old scalar pattern still present

- [ ] **Step 3: Fix `_list_experiments_where` in queries_lib.py**

Change lines 773-775 from:
```python
    if treatment_type:
        conditions.append("toLower(e.treatment_type) IN $treatment_types")
        params["treatment_types"] = [t.lower() for t in treatment_type]
```
To:
```python
    if treatment_type:
        conditions.append(
            "ANY(t IN e.treatment_type WHERE toLower(t) IN $treatment_types)"
        )
        params["treatment_types"] = [t.lower() for t in treatment_type]
```

- [ ] **Step 4: Fix `_gene_response_profile_where` in queries_lib.py**

Change lines 2456-2458 from:
```python
    if treatment_types:
        conditions.append(f"toLower({experiment_alias}.treatment_type) IN $treatment_types")
        params["treatment_types"] = [t.lower() for t in treatment_types]
```
To:
```python
    if treatment_types:
        conditions.append(
            f"ANY(t IN {experiment_alias}.treatment_type"
            f" WHERE toLower(t) IN $treatment_types)"
        )
        params["treatment_types"] = [t.lower() for t in treatment_types]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py -v -k "treatment_type"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "fix(queries): treatment_type filter uses ANY() for array property"
```

---

## Task 2: Update queries_lib.py — Experiment summary aggregation

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:933-946` (`build_list_experiments_summary`)
- Modify: `multiomics_explorer/kg/queries_lib.py:1495` (`build_differential_expression_by_gene_summary`)
- Modify: `multiomics_explorer/kg/queries_lib.py:2086-2098` (`build_differential_expression_by_ortholog_summary`)
- Test: `tests/unit/test_query_builders.py`

`collect(e.treatment_type)` collects arrays into a list-of-lists. Must flatten first.

- [ ] **Step 1: Write failing test for summary aggregation**

```python
def test_list_experiments_summary_flattens_treatment_type():
    """treatment_type is array — summary must flatten before frequencies."""
    cypher, _ = build_list_experiments_summary()
    assert "apoc.coll.flatten(collect(coalesce(e.treatment_type, [])))" in cypher
    assert "collect(e.treatment_type) AS tts" not in cypher
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_query_builders.py::test_list_experiments_summary_flattens_treatment_type -v`
Expected: FAIL

- [ ] **Step 3: Fix `build_list_experiments_summary`**

Change line 935 from:
```python
        "     collect(e.treatment_type) AS tts,\n"
```
To:
```python
        "     apoc.coll.flatten(collect(coalesce(e.treatment_type, []))) AS tts,\n"
```

- [ ] **Step 4: Fix `build_differential_expression_by_gene_summary`**

Change line 1495 from:
```python
        "       apoc.coll.frequencies(collect(e.treatment_type)) AS rows_by_treatment_type,\n"
```
To:
```python
        "       apoc.coll.frequencies(apoc.coll.flatten(collect(coalesce(e.treatment_type, [])))) AS rows_by_treatment_type,\n"
```

- [ ] **Step 5: Fix `build_differential_expression_by_ortholog_summary`**

Change line 2086 from:
```python
        "     r.expression_status AS status, e.treatment_type AS tt,\n"
```
To:
```python
        "     r.expression_status AS status,\n"
```

And restructure the summary to flatten treatment_type. The current pattern collects `tt` per row then runs frequencies. Since `e.treatment_type` is now an array, the simplest fix is to collect the array and flatten:

Change the entire WITH/RETURN block (lines 2085-2102) to collect `e.treatment_type` as an array and flatten before frequency counting. Specifically, replace `e.treatment_type AS tt` in the first WITH with `e.treatment_type AS tts`, then in the rows collection replace `tt: tt` with `tts: tts`, and in the RETURN replace `apoc.coll.frequencies([r IN rows | r.tt])` with `apoc.coll.frequencies(apoc.coll.flatten([r IN rows | coalesce(r.tts, [])]))`.

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_query_builders.py -v -k "summary"`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "fix(queries): flatten array treatment_type before frequency aggregation"
```

---

## Task 3: Update queries_lib.py — Experiment detail RETURN clauses

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:865` (`build_list_experiments` return)
- Modify: `multiomics_explorer/kg/queries_lib.py:1547` (DE by gene experiment summary)
- Modify: `multiomics_explorer/kg/queries_lib.py:1706` (DE by gene detail)
- Modify: `multiomics_explorer/kg/queries_lib.py:2183` (DE by ortholog top_experiments)
- Modify: `multiomics_explorer/kg/queries_lib.py:2253` (DE by ortholog detail)
- Test: `tests/unit/test_query_builders.py`

These lines return `e.treatment_type AS treatment_type`. Since treatment_type is now an array, Cypher will return a list. The Pydantic models downstream must accept `list[str]` (handled in Task 7). No Cypher change needed here — the RETURN is fine, but we should verify Cypher returns a list and the API layer handles it.

**No Cypher changes needed for direct RETURN clauses** — Neo4j returns the array as-is. The downstream model changes are in Tasks 7-8.

- [ ] **Step 1: Verify RETURN clauses don't need changes**

Confirm: `e.treatment_type AS treatment_type` returns a list when the property is an array. No fix needed.

- [ ] **Step 2: Commit (no-op, document decision)**

No commit needed — this task confirms no RETURN clause changes required.

---

## Task 4: Update queries_lib.py — gene_response_profile group_by

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:2465-2472` (`_group_key_expr`)
- Modify: `multiomics_explorer/kg/queries_lib.py:2584-2646` (`build_gene_response_profile` pass1+pass2)
- Test: `tests/unit/test_query_builders.py`

`group_by="treatment_type"` currently uses `e.treatment_type` as a scalar group key. With array treatment_type, we need to UNWIND the array so each treatment_type value produces its own row.

- [ ] **Step 1: Write failing test**

```python
def test_gene_response_profile_group_by_treatment_type_unwinds():
    """group_by=treatment_type must UNWIND array to produce one row per value."""
    cypher, _ = build_gene_response_profile(
        locus_tags=["PMM0001"],
        organism_name="Prochlorococcus MED4",
        group_by="treatment_type",
    )
    assert "UNWIND" in cypher or "unwind" in cypher.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_query_builders.py::test_gene_response_profile_group_by_treatment_type_unwinds -v`
Expected: FAIL

- [ ] **Step 3: Update `_group_key_expr` and callers**

Change `_group_key_expr` (lines 2465-2472) to return a dict with an optional UNWIND prefix:

```python
def _group_key_expr(group_by: str, alias: str = "e") -> tuple[str, str]:
    """Return (unwind_clause, group_key_expr) for the group key.

    When group_by='treatment_type', returns an UNWIND clause because
    treatment_type is an array property.
    """
    if group_by == "treatment_type":
        return (
            f"UNWIND coalesce({alias}.treatment_type, ['unknown']) AS _tt\n",
            "_tt",
        )
    elif group_by == "experiment":
        return ("", f"{alias}.id")
    else:
        raise ValueError(
            f"group_by must be 'treatment_type' or 'experiment', got '{group_by}'"
        )
```

Then update all callers (`build_gene_response_profile_envelope`, `build_gene_response_profile`) to unpack the tuple and insert the UNWIND clause into the Cypher at the appropriate position.

For `build_gene_response_profile` (the main query), the UNWIND should come after the first MATCH in pass2 (after line 2604 `MATCH (e:Experiment)-[r:Changes_expression_of]->(g)\n`), so the group_key is a scalar per row.

For `build_gene_response_profile_envelope`, the UNWIND goes after line 2519 `OPTIONAL MATCH (e2:Experiment)-[:Changes_expression_of]->(:Gene)\n`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_query_builders.py -v -k "response_profile"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "fix(queries): UNWIND array treatment_type for group_by in gene_response_profile"
```

---

## Task 5: Update queries_lib.py — Add background_factors to experiment queries

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:740-790` (`_list_experiments_where` — add filter)
- Modify: `multiomics_explorer/kg/queries_lib.py:860-881` (`build_list_experiments` — add to RETURN)
- Modify: `multiomics_explorer/kg/queries_lib.py:933-950` (`build_list_experiments_summary` — add aggregation)
- Modify: `multiomics_explorer/kg/queries_lib.py:698-737` (`build_list_organisms` — add to RETURN)
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests**

```python
def test_list_experiments_returns_background_factors():
    """New background_factors field in RETURN."""
    cypher, _ = build_list_experiments()
    assert "background_factors" in cypher

def test_list_experiments_where_background_factors_filter():
    """background_factors filter uses ANY() with coalesce for null safety."""
    cypher, params = build_list_experiments(
        background_factors=["axenic"],
    )
    assert "ANY(bf IN coalesce(e.background_factors, []) WHERE toLower(bf) IN $background_factors)" in cypher
    assert params["background_factors"] == ["axenic"]

def test_list_experiments_summary_has_by_background_factors():
    """Summary includes by_background_factors breakdown."""
    cypher, _ = build_list_experiments_summary()
    assert "by_background_factors" in cypher

def test_list_organisms_returns_background_factors():
    """OrganismTaxon now has background_factors."""
    cypher, _ = build_list_organisms()
    assert "background_factors" in cypher
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py -v -k "background_factors"`
Expected: FAIL

- [ ] **Step 3: Add `background_factors` filter to `_list_experiments_where`**

After the treatment_type block (line 775), add:

```python
    if background_factors:
        conditions.append(
            "ANY(bf IN coalesce(e.background_factors, [])"
            " WHERE toLower(bf) IN $background_factors)"
        )
        params["background_factors"] = [bf.lower() for bf in background_factors]
```

Add `background_factors: list[str] | None = None` parameter to `_list_experiments_where`, `build_list_experiments`, and `build_list_experiments_summary` signatures.

- [ ] **Step 4: Add `background_factors` to RETURN in `build_list_experiments`**

After line 865 (`e.treatment_type AS treatment_type,\n`), add:
```python
        "       coalesce(e.background_factors, []) AS background_factors,\n"
```

- [ ] **Step 5: Add `by_background_factors` to `build_list_experiments_summary`**

In collect_cols (line 933-939), add:
```python
        "     apoc.coll.flatten(collect(coalesce(e.background_factors, []))) AS bfs,\n"
```

In return_cols (line 942-949), add:
```python
        "       apoc.coll.frequencies(bfs) AS by_background_factors,\n"
```

- [ ] **Step 6: Add `background_factors` to `build_list_organisms`**

After line 732 (`o.treatment_types AS treatment_types,\n`), add:
```python
        "       o.background_factors AS background_factors,\n"
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/unit/test_query_builders.py -v -k "background_factors"`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(queries): add background_factors filter, return, and aggregation"
```

---

## Task 6: Update queries_lib.py — Add background_factors to remaining builders

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` — DE by gene, DE by ortholog, list_publications builders
- Test: `tests/unit/test_query_builders.py`

Add `background_factors` to RETURN clauses and summary aggregations in the differential expression and publication builders, mirroring where `treatment_type` already appears.

- [ ] **Step 1: Add `background_factors` to list_publications RETURN**

In `build_list_publications` (around line 622), add `p.background_factors AS background_factors` to the RETURN clause. Publications have pre-computed `background_factors` from the KG.

- [ ] **Step 2: Add `background_factors` to DE by gene experiment summary**

In `build_differential_expression_by_gene_summary_by_experiment` (line 1547), add `background_factors: coalesce(e.background_factors, [])` to the collect map.

- [ ] **Step 3: Add `background_factors` to DE by ortholog top_experiments**

In `build_differential_expression_by_ortholog_top_experiments` (line 2183), add `background_factors: coalesce(e.background_factors, [])` to the collect map.

- [ ] **Step 4: Add `background_factors` to DE by ortholog detail**

In `build_differential_expression_by_ortholog_results` (line 2253), add `coalesce(e.background_factors, []) AS background_factors` to the RETURN.

- [ ] **Step 5: Add `background_factors` to DE by gene detail**

In `build_differential_expression_by_gene` (verbose_cols, around line 1677), add `coalesce(e.background_factors, []) AS background_factors` to verbose columns.

- [ ] **Step 6: Add `background_factors` to gene cluster builders**

In `build_list_gene_clusters` (line 2841), add `coalesce(gc.background_factors, []) AS background_factors`. GeneCluster nodes also have this property.

In `build_list_gene_clusters_summary` (line 2737), add flattened background_factors collection and `by_background_factors` frequency.

- [ ] **Step 7: Run tests**

Run: `pytest tests/unit/test_query_builders.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(queries): add background_factors to DE, publications, and cluster builders"
```

---

## Task 7: Update api/functions.py

**Files:**
- Modify: `multiomics_explorer/api/functions.py`
- Test: `tests/unit/test_api_functions.py`

Pass through the new `background_factors` parameter and surface it in results. Update treatment_type handling where the API converts query results.

- [ ] **Step 1: Add `background_factors` parameter to `list_experiments`**

Add `background_factors: list[str] | None = None` parameter and pass through to query builders.

- [ ] **Step 2: Add `by_background_factors` to experiment summary builder**

In the summary assembly (around line 721), add `by_background_factors` conversion using `_apoc_freq_to_treatment_dict`.

- [ ] **Step 3: Add `background_factors` to `list_organisms` return**

The query already returns it after Task 5; verify the result passthrough works (it should — `list_organisms` returns raw rows).

- [ ] **Step 4: Add `background_factors` to `list_publications` return**

Same pattern — the query returns it, verify passthrough.

- [ ] **Step 5: Add `background_factors` parameter and handling to DE functions**

Add `background_factors` fields to the experiment detail structures returned by `differential_expression_by_gene` and `differential_expression_by_ortholog`.

- [ ] **Step 6: Add `background_factors` to gene cluster functions**

Add `background_factors` parameter to `list_gene_clusters` and pass through.

- [ ] **Step 7: Run tests**

Run: `pytest tests/unit/test_api_functions.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add multiomics_explorer/api/functions.py tests/unit/test_api_functions.py
git commit -m "feat(api): add background_factors parameter and return fields"
```

---

## Task 8: Update mcp_server/tools.py — Pydantic models

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Test: `tests/unit/test_mcp_models.py` (if exists, else integration tests)

Update all Pydantic models where `treatment_type: str` should become `treatment_type: list[str]`, and add `background_factors: list[str]` fields.

- [ ] **Step 1: Update ExperimentResult model**

Line 1105: Change `treatment_type: str` to `treatment_type: list[str]`.
Add: `background_factors: list[str] = Field(default_factory=list, description="Background experimental factors (e.g. ['axenic', 'continuous_light']). Empty list when none specified.")`

- [ ] **Step 2: Update OrganismResult model**

Line 112: Add `background_factors: list[str]` field.

- [ ] **Step 3: Update ExpressionByExperiment model**

Line 1343: Change `treatment_type: str` to `treatment_type: list[str]`.
Add `background_factors: list[str] = Field(default_factory=list, ...)`.

- [ ] **Step 4: Update ExpressionRow model**

Line 1402: Change `treatment_type: str` to `treatment_type: list[str]`.

- [ ] **Step 5: Update DE by ortholog result models**

Line 2029: Change `treatment_type: str` to `treatment_type: list[str]`.

- [ ] **Step 6: Update ListExperimentsResponse model**

Add `by_background_factors` field (same pattern as `by_treatment_type`).

- [ ] **Step 7: Add BackgroundFactorsBreakdown model**

```python
class BackgroundFactorsBreakdown(BaseModel):
    background_factor: str = Field(description="Background factor (e.g. 'axenic', 'diel_cycle')")
    count: int = Field(description="Number of experiments (e.g. 14)")
```

- [ ] **Step 8: Add `background_factors` filter parameter to list_experiments tool**

After `treatment_type` parameter (line 1173), add:
```python
background_factors: Annotated[list[str] | None, Field(
    description="Filter by background factors (case-insensitive exact match). "
    "E.g. ['axenic', 'diel_cycle']. "
    "Background factors describe experimental context that is not the primary treatment.",
)] = None,
```

- [ ] **Step 9: Add `background_factors` to list_gene_clusters tool parameters**

Similar to list_experiments.

- [ ] **Step 10: Update PublicationResult model**

Add `background_factors: list[str]` field.

- [ ] **Step 11: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "feat(mcp): update models for array treatment_type and background_factors"
```

---

## Task 9: Update few-shot examples in queries.py

**Files:**
- Modify: `multiomics_explorer/kg/queries.py`

- [ ] **Step 1: Update EXPRESSION_FOR_GENE**

Line 85: `e.treatment_type AS treatment_type` — no change needed (returns array now, which is fine).

- [ ] **Step 2: Update GENES_UPREGULATED_BY_COCULTURE**

Line 95: Change `{treatment_type: 'coculture'}` to a WHERE clause:
```python
GENES_UPREGULATED_BY_COCULTURE = """
MATCH (e:Experiment)-[r:Changes_expression_of {expression_direction: 'up'}]->(g:Gene)
WHERE 'coculture' IN e.treatment_type
  AND e.coculture_partner CONTAINS $coculture_genus
  AND e.organism_name CONTAINS $target_strain
RETURN g.locus_tag AS locus_tag, g.product AS product,
       r.log2_fold_change AS log2fc, r.adjusted_p_value AS padj,
       e.coculture_partner AS coculture_organism
ORDER BY r.log2_fold_change DESC
LIMIT 50
"""
```

- [ ] **Step 3: Update GENES_AFFECTED_BY_STRESS**

Line 107: Change `e.treatment_type = $treatment_type` to `$treatment_type IN e.treatment_type`.

- [ ] **Step 4: Update FEW_SHOT_EXAMPLES**

Update all Cypher in the examples list (lines 160-238):
- `{treatment_type: 'coculture'}` → WHERE clause with `'coculture' IN e.treatment_type`
- `e.treatment_type = 'nutrient_stress'` → `'nutrient_stress' IN e.treatment_type`
- Update explanations to mention treatment_type is now an array

- [ ] **Step 5: Add background_factors example**

Add a new few-shot example:
```python
{
    "question": "Which genes respond to nitrogen stress under diel cycle conditions?",
    "cypher": (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(g:Gene)\n"
        "WHERE 'nitrogen_stress' IN e.treatment_type\n"
        "  AND 'diel_cycle' IN coalesce(e.background_factors, [])\n"
        "  AND r.expression_status <> 'not_significant'\n"
        "RETURN g.locus_tag, g.product, r.log2_fold_change, e.name\n"
        "ORDER BY abs(r.log2_fold_change) DESC\n"
        "LIMIT 50"
    ),
    "explanation": (
        "Experiment.treatment_type is an array — use 'value' IN e.treatment_type. "
        "background_factors (also array, may be null) captures experimental context "
        "like 'axenic', 'diel_cycle', 'continuous_light'. Use coalesce for null safety."
    ),
}
```

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/kg/queries.py
git commit -m "fix(queries): update few-shot examples for array treatment_type and background_factors"
```

---

## Task 10: Update YAML inputs and tool-spec docs

**Files:**
- Modify: `multiomics_explorer/inputs/tools/list_experiments.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_publications.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_organisms.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_gene_clusters.yaml`
- Modify: `multiomics_explorer/inputs/tools/gene_response_profile.yaml`
- Modify: `docs/tool-specs/list_experiments.md`
- Modify: `docs/tool-specs/list_publications.md`
- Modify: `docs/tool-specs/list_organisms.md`

- [ ] **Step 1: Update YAML files**

In each YAML, update examples and field descriptions:
- `treatment_type` in result examples should show as list: `treatment_type: ["coculture"]`
- Add `background_factors` to result examples: `background_factors: ["axenic", "continuous_light"]`
- Add `background_factors` filter examples where applicable

- [ ] **Step 2: Update tool-spec docs**

Update parameter tables and response field tables to reflect array treatment_type and new background_factors.

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/inputs/tools/ docs/tool-specs/
git commit -m "docs: update tool YAMLs and specs for array treatment_type and background_factors"
```

---

## Task 11: Integration tests and regression baselines

**Files:**
- Modify: `tests/integration/test_mcp_tools.py`
- Modify: `tests/integration/test_api_contract.py`
- Regenerate: `tests/regression/`

- [ ] **Step 1: Update integration test assertions**

In `test_mcp_tools.py`:
- Where tests assert `treatment_type` is a string, change to assert it's a list
- Add assertions for `background_factors` in organism and experiment results
- Add test for background_factors filter

In `test_api_contract.py`:
- Update contract assertions for array treatment_type
- Add background_factors field checks

- [ ] **Step 2: Run integration tests against updated KG**

Run: `pytest -m kg -v`
Expected: May need KG rebuild first. If KG not yet rebuilt, mark as blocked.

- [ ] **Step 3: Regenerate regression baselines**

Run: `pytest tests/regression/ --generate-baselines` (or whatever the regeneration command is)

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: update integration tests and baselines for array treatment_type and background_factors"
```

---

## Task 12: Update CLAUDE.md and remaining docs

**Files:**
- Modify: `CLAUDE.md` (if tool table descriptions need updating)
- Modify: skills/references if they mention treatment_type patterns

- [ ] **Step 1: Update CLAUDE.md tool table**

Add `background_factors` to the description of `list_experiments` and any other tools that now surface it.

- [ ] **Step 2: Update skill references**

Check `.claude/skills/` for hardcoded treatment_type patterns (e.g. `add-or-update-tool/references/checklist.md` line 348-354) and update to array syntax.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md .claude/skills/
git commit -m "docs: update CLAUDE.md and skills for array treatment_type and background_factors"
```

---

## Dependency Order

```
Task 1 (filters) ──┐
Task 2 (aggregation)├─► Task 5 (bg_factors experiment) ──► Task 7 (API) ──► Task 8 (MCP models)
Task 3 (RETURN)  ───┤                                                           │
Task 4 (group_by) ──┘                                                           ▼
                        Task 6 (bg_factors others) ──────────────────────► Task 11 (integration)
                        Task 9 (few-shot) ─────────────────────────────►       │
                        Task 10 (docs) ────────────────────────────────► Task 12 (CLAUDE.md)
```

Tasks 1-4 can run in parallel (all modify queries_lib.py but different sections). Tasks 5-6 depend on 1-4. Tasks 7-8 depend on 5-6. Task 9 is independent. Tasks 10-12 are final.

## Pre-requisites

- **KG rebuild required**: The new KG with array treatment_type and background_factors must be deployed before integration tests (Task 11) can run. Unit tests (Tasks 1-8) can proceed with mock data.
- Check with user: Is the KG already rebuilt, or is this plan to be executed before the KG update?
