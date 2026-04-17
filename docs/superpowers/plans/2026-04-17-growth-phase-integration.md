# Growth Phase Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface `growth_phase` (timepoint-level experimental condition, not gene-specific) across all relevant explorer tools — return columns, filters, summaries, and a new `list_filter_values` type.

**Architecture:** Query builders add `growth_phase`/`growth_phases` columns and filter clauses (experiment-level for browsing tools, edge-level for DE tools). API layer threads filters and builds `by_growth_phase` summaries. MCP layer adds Pydantic model fields and tool parameters. New `list_filter_values` type for value discovery.

**Tech Stack:** Python, Neo4j (Cypher), FastMCP, pytest

**Spec:** `docs/superpowers/specs/2026-04-17-growth-phase-integration-design.md`

**Key semantic:** `growth_phase` describes the physiological state of the culture at sampling — every gene measured at a given experiment×timepoint shares the same value. It lives on the `Changes_expression_of` edge. `growth_phases` on Experiment/Publication/OrganismTaxon/ClusteringAnalysis is the set of distinct phases.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `multiomics_explorer/kg/queries_lib.py` | Modify | Add columns, filters, summaries to all builders |
| `multiomics_explorer/api/functions.py` | Modify | Thread filters, build summaries, sparse stripping |
| `multiomics_explorer/analysis/enrichment.py` | Modify | Add `growth_phase` to `_METADATA_FIELDS`, add filter to `de_enrichment_inputs` |
| `multiomics_explorer/mcp_server/tools.py` | Modify | Add Pydantic fields, tool parameters, docstrings |
| `tests/unit/test_query_builders.py` | Modify | Test new columns and filter clauses |
| `tests/unit/test_tool_correctness.py` | Modify | Test growth_phase in mocked results |
| `multiomics_explorer/inputs/tools/*.yaml` | Modify | Document new fields in tool YAML specs |
| `tests/regression/` | Regenerate | Golden files pick up new columns |

---

### Task 1: Query builders — experiment browsing tools

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:946-1205`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for `_list_experiments_where`**

In `tests/unit/test_query_builders.py`, find the `TestBuildListExperimentsWhere` class (or the test class that tests `_list_experiments_where`). Add:

```python
    def test_growth_phases_filter(self):
        where, params = _list_experiments_where(growth_phases=["exponential", "nutrient_limited"])
        assert "growth_phases" in where
        assert "toLower(gp) IN $growth_phases" in where
        assert params["growth_phases"] == ["exponential", "nutrient_limited"]

    def test_growth_phases_case_insensitive(self):
        _, params = _list_experiments_where(growth_phases=["Exponential"])
        assert params["growth_phases"] == ["exponential"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py -k "growth_phases_filter" -v`
Expected: FAIL — `_list_experiments_where` does not accept `growth_phases`.

- [ ] **Step 3: Add `growth_phases` filter to `_list_experiments_where`**

In `multiomics_explorer/kg/queries_lib.py:946-957`, add `growth_phases: list[str] | None = None` to the signature.

After the `background_factors` condition block (line 991), add:

```python
    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(e.growth_phases, [])"
            " WHERE toLower(gp) IN $growth_phases)"
        )
        params["growth_phases"] = [gp.lower() for gp in growth_phases]
```

- [ ] **Step 4: Thread `growth_phases` through callers**

In `build_list_experiments` (line 1018), add `growth_phases: list[str] | None = None` to the signature and pass it to `_list_experiments_where(... growth_phases=growth_phases)` at line 1047.

In `build_list_experiments_summary` (line 1129), add `growth_phases: list[str] | None = None` to the signature and pass it to `_list_experiments_where(... growth_phases=growth_phases)` at line 1152.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py -k "growth_phases" -v`
Expected: PASS

- [ ] **Step 6: Write failing tests for return columns**

```python
    def test_returns_growth_phases(self):
        cypher, _ = build_list_experiments()
        assert "growth_phases" in cypher
        assert "time_point_growth_phases" in cypher

    def test_summary_returns_by_growth_phase(self):
        cypher, _ = build_list_experiments_summary()
        assert "by_growth_phase" in cypher
```

- [ ] **Step 7: Add return columns to `build_list_experiments`**

In the `return_cols` string (line 1080-1103), after the `cluster_types` line (line 1103), add:

```python
        ",\n       coalesce(e.growth_phases, []) AS growth_phases"
        ",\n       coalesce(e.time_point_growth_phases, []) AS time_point_growth_phases"
```

Update the docstring to include `growth_phases, time_point_growth_phases` in RETURN keys.

- [ ] **Step 8: Add `by_growth_phase` to summary**

In `build_list_experiments_summary` `collect_cols` (line 1160-1168), after the `ctypes` line, add:

```python
        ",\n     apoc.coll.flatten(collect(coalesce(e.growth_phases, []))) AS gps"
```

In the `return_cols` (line 1171-1180), after `by_cluster_type`, add:

```python
        ",\n       apoc.coll.frequencies(gps) AS by_growth_phase"
```

Update the docstring to include `by_growth_phase` in RETURN keys.

- [ ] **Step 9: Run tests**

Run: `pytest tests/unit/test_query_builders.py -k "list_experiments" -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(queries): add growth_phases filter/columns/summary to list_experiments builders"
```

---

### Task 2: Query builders — publications, organisms, clustering

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:703-942, 3333-3444`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests**

```python
    # In TestBuildListPublications or equivalent:
    def test_returns_growth_phases(self):
        cypher, _ = build_list_publications()
        assert "growth_phases" in cypher

    def test_growth_phases_filter(self):
        cypher, params = build_list_publications(growth_phases="exponential")
        assert "growth_phases" in cypher
        assert "growth_phases" in params

    # In TestBuildListOrganisms or equivalent:
    def test_returns_growth_phases(self):
        cypher, _ = build_list_organisms()
        assert "growth_phases" in cypher

    # In TestBuildListClusteringAnalyses or equivalent:
    def test_returns_growth_phases(self):
        cypher, _ = build_list_clustering_analyses()
        assert "growth_phases" in cypher

    def test_growth_phases_filter(self):
        cypher, params = build_list_clustering_analyses(growth_phases=["diel"])
        assert "growth_phases" in cypher
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py -k "growth_phases" -v`
Expected: FAIL

- [ ] **Step 3: Add `growth_phases` to `_list_publications_where`**

In `_list_publications_where` (line 703-710), add `growth_phases: str | None = None` to the signature.

After the `background_factors` condition block (line 733-738), add:

```python
    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(p.growth_phases, [])"
            " WHERE toLower(gp) = toLower($growth_phases))"
        )
        params["growth_phases"] = growth_phases
```

Thread through `build_list_publications` (line 750) and `build_list_publications_summary` (line 831) signatures and their calls to `_list_publications_where`.

- [ ] **Step 4: Add return column to `build_list_publications`**

In both search_text and non-search variants of the RETURN clause (around lines 799 and 820), after the `cluster_types` line, add:

```python
        "       coalesce(p.growth_phases, []) AS growth_phases,\n"
```

Update the docstring to include `growth_phases` in RETURN keys.

- [ ] **Step 5: Add return column to `build_list_organisms`**

In the RETURN clause (line 921-941), after the `reference_proteome` line (line 939), add:

```python
        "       coalesce(o.growth_phases, []) AS growth_phases"
```

Move the trailing comma from `reference_proteome` line appropriately. Update docstring.

- [ ] **Step 6: Add `growth_phases` to `_clustering_analysis_where`**

In `_clustering_analysis_where` (line 3333-3340), add `growth_phases: list[str] | None = None` to the signature.

After the `background_factors` condition block (line 3361-3366), add:

```python
    if growth_phases:
        conditions.append(
            "ANY(gp IN coalesce(ca.growth_phases, [])"
            " WHERE toLower(gp) IN $growth_phases)"
        )
        params["growth_phases"] = [gp.lower() for gp in growth_phases]
```

Thread through `build_list_clustering_analyses` (line 3447) and `build_list_clustering_analyses_summary` (line 3370) signatures.

- [ ] **Step 7: Add return column and summary to clustering**

In `build_list_clustering_analyses`, add `growth_phases` to the return columns (after `background_factors`):

```python
        "       coalesce(ca.growth_phases, []) AS growth_phases,\n"
```

In `build_list_clustering_analyses_summary` collect_cols (line 3430-3434), add:

```python
        "     apoc.coll.flatten(collect(coalesce(ca.growth_phases, []))) AS growth_phases_flat,\n"
```

In the return cols (line 3437-3442), add:

```python
        "       apoc.coll.frequencies(growth_phases_flat) AS by_growth_phase,\n"
```

Update docstrings.

- [ ] **Step 8: Run tests**

Run: `pytest tests/unit/test_query_builders.py -k "growth_phases" -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(queries): add growth_phases to publications, organisms, clustering builders"
```

---

### Task 3: Query builders — differential expression

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:2006-2198, 2289-2361, 2640-2745, 2838-2913`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for DE by gene**

```python
    # In TestBuildDifferentialExpressionByGene or equivalent:
    def test_growth_phases_filter(self):
        cypher, params = build_differential_expression_by_gene(
            organism="MED4", growth_phases=["exponential"]
        )
        assert "r.growth_phase" in cypher
        assert params["growth_phases"] == ["exponential"]

    def test_returns_growth_phase(self):
        cypher, _ = build_differential_expression_by_gene(organism="MED4")
        assert "r.growth_phase AS growth_phase" in cypher

    def test_summary_global_returns_rows_by_growth_phase(self):
        cypher, _ = build_differential_expression_by_gene_summary_global(
            organism="MED4"
        )
        assert "rows_by_growth_phase" in cypher
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py -k "growth_phase" -v`
Expected: FAIL

- [ ] **Step 3: Add `growth_phases` to `_differential_expression_where`**

In `_differential_expression_where` (line 2006-2013), add `growth_phases: list[str] | None = None` to the signature.

Before the `return` statement (line 2040), add:

```python
    if growth_phases:
        conditions.append("toLower(r.growth_phase) IN $growth_phases")
        params["growth_phases"] = [gp.lower() for gp in growth_phases]
```

- [ ] **Step 4: Thread through DE by gene builders**

Add `growth_phases: list[str] | None = None` to these function signatures and pass it to `_differential_expression_where`:
- `build_differential_expression_by_gene` (line 2289)
- `build_differential_expression_by_gene_summary_global` (line 2101)
- `build_differential_expression_by_gene_summary_by_experiment` (line 2145)
- `build_differential_expression_by_gene_summary_diagnostics` (line 2201)

- [ ] **Step 5: Add `growth_phase` return column to DE by gene**

In `build_differential_expression_by_gene` (line 2340-2355), after the `expression_status` line (line 2355), add:

```python
        ",\n       r.growth_phase AS growth_phase"
```

Update docstring RETURN keys to include `growth_phase` with note: "Physiological state of the culture at this timepoint (timepoint-level condition, not gene-specific)."

- [ ] **Step 6: Add `rows_by_growth_phase` to summary global**

In `build_differential_expression_by_gene_summary_global` (line 2126-2141), after the `by_table_scope` line (line 2134), add:

```python
        "       apoc.coll.frequencies(collect(r.growth_phase)) AS rows_by_growth_phase,\n"
```

Update docstring RETURN keys.

- [ ] **Step 7: Add `growth_phase` to summary by experiment timepoints**

In `build_differential_expression_by_gene_summary_by_experiment` (line 2167-2197), in the first WITH clause (line 2170), add `r.growth_phase AS gp` alongside `r.time_point AS tp`:

```python
        "WITH e, r.time_point AS tp, r.time_point_order AS tpo,"
        " r.time_point_hours AS tph, r.growth_phase AS gp,\n"
```

In the timepoint collect (line 2179-2182), add `growth_phase: gp`:

```python
        "     collect({timepoint: tp, timepoint_hours: tph,"
        " timepoint_order: tpo, growth_phase: gp,\n"
```

- [ ] **Step 8: Add `growth_phases` to `_differential_expression_by_ortholog_where`**

In `_differential_expression_by_ortholog_where` (line 2640-2646), add `growth_phases: list[str] | None = None` to the signature.

Before the `return` statement (line 2670), add:

```python
    if growth_phases:
        conditions.append("toLower(r.growth_phase) IN $growth_phases")
        params["growth_phases"] = [gp.lower() for gp in growth_phases]
```

Thread through all ortholog builders that call this helper:
- `build_differential_expression_by_ortholog_summary_global` (line 2695)
- `build_differential_expression_by_ortholog_top_groups` (line 2748)
- `build_differential_expression_by_ortholog_top_experiments` (line 2791)
- `build_differential_expression_by_ortholog_results` (line 2838)
- `build_differential_expression_by_ortholog_membership_counts` (line 2921)
- `build_differential_expression_by_ortholog_diagnostics` (line 3049)

- [ ] **Step 9: Add `growth_phase` return column to ortholog results**

In `build_differential_expression_by_ortholog_results` (line 2880-2908), in the first WITH clause (line 2885-2890), add `r.growth_phase AS gp` alongside `r.time_point AS tp`:

```python
        "WITH og, e,\n"
        "     r.time_point AS tp,\n"
        "     r.time_point_hours AS tph,\n"
        "     r.time_point_order AS tpo,\n"
        "     r.growth_phase AS gp,\n"
```

In the RETURN clause, after `timepoint_order` (line 2901), add:

```python
        "       gp AS growth_phase,\n"
```

Update docstring RETURN keys.

- [ ] **Step 10: Add `rows_by_growth_phase` to ortholog summary global**

In `build_differential_expression_by_ortholog_summary_global` (line 2719-2743), in the first WITH clause (line 2725-2728), add `r.growth_phase AS gp` to the collected properties:

```python
        "WITH gid, g.locus_tag AS lt, e.organism_name AS org,\n"
        "     r.expression_status AS status, e.treatment_type AS tt,\n"
        "     e.background_factors AS bfs, e.table_scope AS ts, e.id AS eid,\n"
        "     r.log2_fold_change AS log2fc, r.growth_phase AS gp\n"
```

Add `gp` to the collected row dict (line 2729-2731):

```python
        "WITH collect({gid: gid, lt: lt, org: org,\n"
        "              status: status, tt: tt, bfs: bfs, ts: ts,\n"
        "              eid: eid, log2fc: log2fc, gp: gp}) AS rows\n"
```

After `by_table_scope` in the RETURN clause (line 2740), add:

```python
        "       apoc.coll.frequencies([r IN rows | r.gp]) AS rows_by_growth_phase,\n"
```

Update docstring RETURN keys.

- [ ] **Step 11: Run tests**

Run: `pytest tests/unit/test_query_builders.py -k "growth_phase or differential" -v`
Expected: All PASS

- [ ] **Step 12: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(queries): add growth_phase filter/column/summary to DE builders"
```

---

### Task 4: Query builder — `list_filter_values` growth_phase type

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing test**

```python
    def test_build_list_growth_phases(self):
        cypher, params = build_list_growth_phases()
        assert "r.growth_phase" in cypher
        assert "experiment_count" in cypher
        assert params == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_query_builders.py -k "growth_phases" -v`
Expected: FAIL — `build_list_growth_phases` not defined.

- [ ] **Step 3: Implement `build_list_growth_phases`**

In `multiomics_explorer/kg/queries_lib.py`, after `build_list_brite_trees` (around line 892), add:

```python
def build_list_growth_phases() -> tuple[str, dict]:
    """List distinct growth_phase values with experiment counts.

    RETURN keys: phase, experiment_count.
    """
    cypher = (
        "MATCH (e:Experiment)-[r:Changes_expression_of]->(:Gene)\n"
        "WITH r.growth_phase AS phase, e.id AS eid\n"
        "WITH phase, count(DISTINCT eid) AS experiment_count\n"
        "WHERE phase IS NOT NULL\n"
        "RETURN phase, experiment_count\n"
        "ORDER BY experiment_count DESC, phase"
    )
    return cypher, {}
```

- [ ] **Step 4: Run test**

Run: `pytest tests/unit/test_query_builders.py -k "growth_phases" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(queries): add build_list_growth_phases for list_filter_values"
```

---

### Task 5: API layer — all tools

**Files:**
- Modify: `multiomics_explorer/api/functions.py`

- [ ] **Step 1: Update `list_filter_values`**

In `list_filter_values` (line 518-549), after the `brite_tree` elif (line 533-538), add:

```python
    elif filter_type == "growth_phase":
        cypher, params = build_list_growth_phases()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["phase"], "count": r["experiment_count"]} for r in rows]
```

Add `build_list_growth_phases` to the imports from `kg.queries_lib` at the top of the file.

- [ ] **Step 2: Update `list_experiments`**

In `list_experiments` (around line 719), add `growth_phases: list[str] | None = None` to the signature.

Thread to `build_list_experiments(... growth_phases=growth_phases)` and `build_list_experiments_summary(... growth_phases=growth_phases)`.

In the summary result processing (around line 811), add `by_growth_phase` conversion alongside `by_background_factors`:

```python
        "by_growth_phase": _rename_freq(raw["by_growth_phase"], "growth_phase"),
```

The detail results already pass through all returned columns, so `growth_phases` and `time_point_growth_phases` will flow through automatically.

Update the docstring to mention `growth_phases`, `time_point_growth_phases`, `by_growth_phase`.

- [ ] **Step 3: Update `list_publications`**

In `list_publications` (around line 621), add `growth_phases: str | None = None` to the signature.

Thread to `build_list_publications(... growth_phases=growth_phases)`.

The return columns flow through automatically. Update docstring.

- [ ] **Step 4: Update `list_organisms`**

No filter to add. The new `growth_phases` column from the query builder flows through the existing result pass-through. Update docstring.

- [ ] **Step 5: Update `list_clustering_analyses`**

In `list_clustering_analyses` (around line 2371), add `growth_phases: list[str] | None = None` to the signature.

Thread to `build_list_clustering_analyses(... growth_phases=growth_phases)` and `build_list_clustering_analyses_summary(... growth_phases=growth_phases)`.

Add `by_growth_phase` to the summary result processing alongside `by_background_factors`.

- [ ] **Step 6: Update `differential_expression_by_gene`**

In `differential_expression_by_gene` (around line 1801), add `growth_phases: list[str] | None = None` to the signature.

Thread to all DE by gene builders: `build_differential_expression_by_gene(... growth_phases=growth_phases)` and all summary builders.

Add `rows_by_growth_phase` to the summary processing alongside `rows_by_background_factors`:

```python
        "rows_by_growth_phase": _status_dict(raw.get("rows_by_growth_phase", [])),
```

The detail `growth_phase` column flows through automatically.

- [ ] **Step 7: Update `differential_expression_by_ortholog`**

In `differential_expression_by_ortholog` (around line 1968), add `growth_phases: list[str] | None = None` to the signature.

Thread to all ortholog builders.

Add `rows_by_growth_phase` to the summary processing alongside `rows_by_background_factors`.

- [ ] **Step 8: Update `pathway_enrichment`**

In `pathway_enrichment` (line 3166), add `growth_phases: list[str] | None = None` to the signature. Thread to `de_enrichment_inputs`.

- [ ] **Step 9: Run existing unit tests to check for regressions**

Run: `pytest tests/unit/ -v`
Expected: PASS (existing tests don't check new fields)

- [ ] **Step 10: Commit**

```bash
git add multiomics_explorer/api/functions.py
git commit -m "feat(api): thread growth_phases filter and summaries across all API functions"
```

---

### Task 6: Enrichment layer — `_METADATA_FIELDS` and filter

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py:322-490`

- [ ] **Step 1: Add `growth_phase` to `_METADATA_FIELDS`**

In `_METADATA_FIELDS` (line 322-329), add `"growth_phase"` after `"background_factors"`:

```python
_METADATA_FIELDS = (
    "experiment_id", "experiment_name",
    "timepoint", "timepoint_hours", "timepoint_order",
    "direction",
    "omics_type", "table_scope",
    "treatment_type", "background_factors", "growth_phase",
    "is_time_course",
)
```

- [ ] **Step 2: Add `growth_phases` filter to `de_enrichment_inputs`**

In `de_enrichment_inputs` (line 351-359), add `growth_phases: list[str] | None = None` to the signature.

After the `timepoint_filter` check (line 446), add a growth_phase filter:

```python
        gp = row.get("growth_phase")
        if growth_phases is not None and (gp is None or gp.lower() not in {g.lower() for g in growth_phases}):
            continue
```

Note: Normalize the growth_phases set once before the loop for efficiency:

```python
    _gp_filter = {g.lower() for g in growth_phases} if growth_phases else None
```

Then in the loop:

```python
        if _gp_filter is not None:
            gp = (row.get("growth_phase") or "").lower()
            if gp not in _gp_filter:
                continue
```

Update the docstring Parameters section to document `growth_phases`.

- [ ] **Step 3: Run enrichment tests**

Run: `pytest tests/unit/ -k "enrichment" -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.py
git commit -m "feat(enrichment): add growth_phase to metadata fields and filter to de_enrichment_inputs"
```

---

### Task 7: MCP layer — list_filter_values, list_organisms, list_publications

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Test: `tests/unit/test_tool_correctness.py`

- [ ] **Step 1: Write failing test for `list_filter_values` growth_phase type**

In `tests/unit/test_tool_correctness.py`, in the `TestListFilterValues` class, add:

```python
    @pytest.mark.asyncio
    async def test_growth_phase_filter_type(self, tool_fns, mock_ctx):
        """growth_phase filter type returns growth phases with experiment counts."""
        with patch(
            "multiomics_explorer.api.functions.list_filter_values",
            return_value={
                "filter_type": "growth_phase",
                "total_entries": 3,
                "returned": 3,
                "truncated": False,
                "results": [
                    {"value": "exponential", "count": 34},
                    {"value": "nutrient_limited", "count": 14},
                    {"value": "diel", "count": 2},
                ],
            },
        ):
            result = await tool_fns["list_filter_values"](mock_ctx, filter_type="growth_phase")

        assert result.filter_type == "growth_phase"
        assert len(result.results) == 3
        assert result.results[0].value == "exponential"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tool_correctness.py -k "growth_phase_filter_type" -v`
Expected: FAIL — `Literal` type doesn't include `"growth_phase"`.

- [ ] **Step 3: Update `list_filter_values` tool**

In `multiomics_explorer/mcp_server/tools.py:312`, update the `Literal` type to include `"growth_phase"`:

```python
        filter_type: Annotated[Literal["gene_category", "brite_tree", "growth_phase"], Field(
            description="Which filter's valid values to return. "
            "'gene_category': values for the category filter in genes_by_function. "
            "'brite_tree': BRITE tree names for the tree filter in ontology tools. "
            "'growth_phase': physiological states of the culture at sampling time "
            "(timepoint-level condition, not gene-specific). Values for the "
            "growth_phases filter in list_experiments and DE tools.",
        )] = "gene_category",
```

Update the tool docstring to mention `growth_phase`.

- [ ] **Step 4: Update `OrganismResult` model**

In `OrganismResult` (line 339-367), after `cluster_types`, add:

```python
        growth_phases: list[str] = Field(default_factory=list, description="Distinct growth phases across experiments for this organism (e.g. ['exponential', 'nutrient_limited']). Physiological state of the culture at sampling — timepoint-level condition, not gene-specific.")
```

- [ ] **Step 5: Update `list_publications` models**

Find the publication result model. Add:

```python
        growth_phases: list[str] = Field(default_factory=list, description="Distinct growth phases across experiments (e.g. ['exponential']). Physiological state of the culture at sampling — timepoint-level condition, not gene-specific.")
```

Add `growth_phases` filter parameter to the `list_publications` tool function signature:

```python
        growth_phases: Annotated[str | None, Field(
            description="Filter by growth phase (case-insensitive). "
            "Physiological state of the culture at sampling time. "
            "E.g. 'exponential', 'nutrient_limited'. "
            "Use list_filter_values(filter_type='growth_phase') for valid values.",
        )] = None,
```

Thread to `api.list_publications(... growth_phases=growth_phases)`.

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_tool_correctness.py -k "list_filter_values or list_organisms or list_publications" -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_correctness.py
git commit -m "feat(mcp): add growth_phase to list_filter_values, list_organisms, list_publications"
```

---

### Task 8: MCP layer — list_experiments

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Test: `tests/unit/test_tool_correctness.py`

- [ ] **Step 1: Write failing test**

```python
    @pytest.mark.asyncio
    async def test_growth_phases_in_experiment_result(self, tool_fns, mock_ctx):
        """Experiment results include growth_phases and time_point_growth_phases."""
        # Use an existing mock that returns experiment data, extended with growth_phases
        with patch(
            "multiomics_explorer.api.functions.list_experiments",
            return_value={
                "total_entries": 1, "total_matching": 1, "returned": 1,
                "truncated": False, "offset": 0, "time_course_count": 1,
                "by_organism": [], "by_treatment_type": [],
                "by_background_factors": [], "by_omics_type": [],
                "by_publication": [], "by_table_scope": [],
                "by_cluster_type": [], "by_growth_phase": [
                    {"growth_phase": "exponential", "count": 1},
                ],
                "results": [{
                    "experiment_id": "exp1", "experiment_name": "Test",
                    "publication_doi": "10.1/test", "organism_name": "MED4",
                    "treatment_type": ["coculture"], "background_factors": [],
                    "coculture_partner": None, "omics_type": "RNASEQ",
                    "is_time_course": True, "table_scope": "all_detected_genes",
                    "table_scope_detail": None, "gene_count": 100,
                    "genes_by_status": {"significant_up": 10, "significant_down": 5, "not_significant": 85},
                    "timepoints": [
                        {"timepoint": "4h", "timepoint_hours": 4.0, "timepoint_order": 1,
                         "matching_genes": 100, "genes_by_status": {"significant_up": 10, "significant_down": 5, "not_significant": 85}},
                    ],
                    "clustering_analysis_count": 0, "cluster_types": [],
                    "growth_phases": ["exponential"],
                    "time_point_growth_phases": ["exponential"],
                }],
            },
        ):
            result = await tool_fns["list_experiments"](mock_ctx)

        assert result.results[0].growth_phases == ["exponential"]
        assert result.results[0].time_point_growth_phases == ["exponential"]
        assert len(result.by_growth_phase) == 1
        assert result.by_growth_phase[0].growth_phase == "exponential"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tool_correctness.py -k "growth_phases_in_experiment" -v`
Expected: FAIL

- [ ] **Step 3: Add `GrowthPhaseBreakdown` model and update `ExperimentResult`**

Add a new breakdown model after `ClusterTypeBreakdown` (around line 1549):

```python
    class GrowthPhaseBreakdown(BaseModel):
        growth_phase: str = Field(description="Growth phase (e.g. 'exponential'). Physiological state of the culture at sampling — timepoint-level condition, not gene-specific.")
        count: int = Field(description="Number of experiments with this growth phase (e.g. 34)")
```

In `ExperimentResult` (line 1492-1521), after `cluster_types` (line 1509), add:

```python
        growth_phases: list[str] = Field(default_factory=list, description="Distinct growth phases in this experiment (e.g. ['exponential', 'nutrient_limited']). Physiological state of the culture at sampling — timepoint-level condition, not gene-specific.")
        time_point_growth_phases: list[str] = Field(default_factory=list, description="Growth phase per timepoint, parallel to timepoints array (e.g. ['exponential', 'exponential', 'nutrient_limited']). Same phase for all genes at each timepoint.")
```

In `ListExperimentsResponse` (line 1551-1567), after `by_cluster_type` (line 1563), add:

```python
        by_growth_phase: list[GrowthPhaseBreakdown] = Field(default_factory=list, description="Experiment counts per growth phase, sorted by count descending")
```

- [ ] **Step 4: Add filter parameter and wire up**

In the `list_experiments` tool function (line 1573-1636), after the `background_factors` parameter (line 1585-1589), add:

```python
        growth_phases: Annotated[list[str] | None, Field(
            description="Filter by growth phase(s) (case-insensitive). "
            "Physiological state of the culture at sampling time. "
            "E.g. ['exponential', 'nutrient_limited']. "
            "Use list_filter_values(filter_type='growth_phase') for valid values.",
        )] = None,
```

In the `api.list_experiments` call (line 1652-1659), add `growth_phases=growth_phases`.

In the breakdown model building (line 1662-1669), add:

```python
            by_growth_phase = [GrowthPhaseBreakdown(**b) for b in result.get("by_growth_phase", [])]
```

In the `ListExperimentsResponse` construction (line 1687-1703), add `by_growth_phase=by_growth_phase`.

Update the tool docstring to mention growth_phases filter and `by_growth_phase` summary.

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_tool_correctness.py -k "list_experiments" -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_correctness.py
git commit -m "feat(mcp): add growth_phases filter, columns, and summary to list_experiments"
```

---

### Task 9: MCP layer — list_clustering_analyses

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`

- [ ] **Step 1: Update clustering analysis model and tool**

Find the clustering analysis result model. Add:

```python
        growth_phases: list[str] = Field(default_factory=list, description="Distinct growth phases (e.g. ['diel']). Physiological state of the culture at sampling — timepoint-level condition, not gene-specific.")
```

Add `growth_phases` filter parameter to the tool function:

```python
        growth_phases: Annotated[list[str] | None, Field(
            description="Filter by growth phase(s) (case-insensitive). "
            "E.g. ['diel', 'darkness']. "
            "Use list_filter_values(filter_type='growth_phase') for valid values.",
        )] = None,
```

Thread to `api.list_clustering_analyses(... growth_phases=growth_phases)`.

Add `GrowthPhaseBreakdown` to the summary response (reuse the model from Task 8). Wire up `by_growth_phase` in the response construction.

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/test_tool_correctness.py -k "clustering" -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "feat(mcp): add growth_phases to list_clustering_analyses"
```

---

### Task 10: MCP layer — differential expression tools

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Test: `tests/unit/test_tool_correctness.py`

- [ ] **Step 1: Write failing test for DE by gene**

```python
    @pytest.mark.asyncio
    async def test_growth_phase_in_expression_row(self, tool_fns, mock_ctx):
        """Expression rows include growth_phase field."""
        # Build mock that includes growth_phase in results
        mock_data = {
            "organism_name": "Prochlorococcus MED4",
            "matching_genes": 1, "total_matching": 1,
            "rows_by_status": {"significant_up": 1, "significant_down": 0, "not_significant": 0},
            "rows_by_treatment_type": {}, "rows_by_background_factors": {},
            "rows_by_growth_phase": {"exponential": 1},
            "by_table_scope": {},
            "median_abs_log2fc": 1.5, "max_abs_log2fc": 1.5,
            "experiment_count": 1,
            "top_categories": [],
            "experiments": [],
            "not_found": [], "no_expression": [],
            "returned": 1, "offset": 0, "truncated": False,
            "results": [{
                "locus_tag": "PMM0001", "gene_name": "test",
                "experiment_id": "exp1", "treatment_type": ["coculture"],
                "timepoint": "4h", "timepoint_hours": 4.0, "timepoint_order": 1,
                "log2fc": 1.5, "padj": 0.01, "rank": 1,
                "rank_up": 1, "rank_down": None,
                "expression_status": "significant_up",
                "growth_phase": "exponential",
            }],
        }
        with patch(
            "multiomics_explorer.api.functions.differential_expression_by_gene",
            return_value=mock_data,
        ):
            result = await tool_fns["differential_expression_by_gene"](
                mock_ctx, organism="MED4"
            )

        assert result.results[0].growth_phase == "exponential"
        assert result.rows_by_growth_phase == {"exponential": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tool_correctness.py -k "growth_phase_in_expression" -v`
Expected: FAIL — `ExpressionRow` has no `growth_phase` field.

- [ ] **Step 3: Update `ExpressionRow` model**

In `ExpressionRow` (line 1812-1909), after `expression_status` (line 1866) and before the verbose-only fields, add:

```python
        growth_phase: str | None = Field(
            default=None,
            description="Physiological state of the culture at this timepoint "
            "(e.g. 'exponential', 'nutrient_limited'). "
            "Timepoint-level condition shared by all genes — not gene-specific.",
        )
```

- [ ] **Step 4: Update `DifferentialExpressionByGeneResponse` model**

In `DifferentialExpressionByGeneResponse` (line 1911-1974), after `rows_by_background_factors` (line 1941-1944), add:

```python
        rows_by_growth_phase: dict[str, int] = Field(
            description="Row counts by growth phase "
            "(e.g. {'exponential': 100, 'nutrient_limited': 50}). "
            "Growth phase is a timepoint-level condition, not gene-specific.",
        )
```

- [ ] **Step 5: Update `ExpressionByExperiment` model for timepoint growth_phase**

In `ExpressionTimepoint` (line 1733-1750), after `timepoint_order` (line 1744), add:

```python
        growth_phase: str | None = Field(
            default=None,
            description="Physiological state at this timepoint "
            "(e.g. 'exponential'). Timepoint-level, not gene-specific.",
        )
```

- [ ] **Step 6: Add `growth_phases` filter parameter to DE by gene tool**

In the `differential_expression_by_gene` tool function (line 1980-2017), after `significant_only` (line 1999-2002), add:

```python
        growth_phases: Annotated[list[str] | None, Field(
            description="Filter by growth phase(s) at sampling time "
            "(case-insensitive, edge-level). Isolates specific-phase rows "
            "from multi-phase experiments. "
            "E.g. ['exponential']. "
            "Use list_filter_values(filter_type='growth_phase') for valid values.",
        )] = None,
```

Thread to `api.differential_expression_by_gene(... growth_phases=growth_phases)`.

- [ ] **Step 7: Update DE by ortholog models and tool**

Find the ortholog DE result model and response model. Add `growth_phase` field to the result row:

```python
        growth_phase: str | None = Field(
            default=None,
            description="Physiological state of the culture at this timepoint. "
            "Timepoint-level condition, not gene-specific.",
        )
```

Add `rows_by_growth_phase` to the response model:

```python
        rows_by_growth_phase: dict[str, int] = Field(
            default_factory=dict,
            description="Row counts by growth phase",
        )
```

Add `growth_phases` filter parameter to the tool function. Thread to API.

- [ ] **Step 8: Run tests**

Run: `pytest tests/unit/test_tool_correctness.py -k "differential_expression" -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_correctness.py
git commit -m "feat(mcp): add growth_phase to differential expression tool models and filters"
```

---

### Task 11: MCP layer — pathway_enrichment

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`

- [ ] **Step 1: Update `PathwayEnrichmentResult` model**

In `PathwayEnrichmentResult` (line 28-), after `timepoint_order` or `background_factors`, add:

```python
        growth_phase: str | None = Field(
            default=None,
            description="Physiological state of the culture at this timepoint "
            "(e.g. 'exponential'). Timepoint-level condition, not gene-specific.",
        )
```

- [ ] **Step 2: Add `growth_phases` filter parameter to tool**

In the `pathway_enrichment` tool function (line 3559), add:

```python
        growth_phases: Annotated[list[str] | None, Field(
            description="Filter DE results by growth phase(s) before enrichment "
            "(case-insensitive). Restricts clusters to specific phases. "
            "E.g. ['exponential'].",
        )] = None,
```

Thread to `api.pathway_enrichment(... growth_phases=growth_phases)`.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_tool_correctness.py -k "pathway_enrichment" -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "feat(mcp): add growth_phase to pathway_enrichment model and filter"
```

---

### Task 12: Unit test suite — full pass

- [ ] **Step 1: Run full unit test suite**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 2: Fix any failures**

If any existing tests fail due to new required fields in mock data, update those mocks to include `growth_phase`/`growth_phases`/`rows_by_growth_phase` with sensible defaults.

- [ ] **Step 3: Commit any fixes**

```bash
git add tests/unit/
git commit -m "fix(tests): update mocks for growth_phase fields"
```

---

### Task 13: Documentation — YAML specs

**Files:**
- Modify: `multiomics_explorer/inputs/tools/list_experiments.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_publications.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_filter_values.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_organisms.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_clustering_analyses.yaml`
- Modify: `multiomics_explorer/inputs/tools/differential_expression_by_gene.yaml`
- Modify: `multiomics_explorer/inputs/tools/differential_expression_by_ortholog.yaml`
- Modify: `multiomics_explorer/inputs/tools/pathway_enrichment.yaml`

- [ ] **Step 1: Update YAML specs**

For each YAML file, add `growth_phase`/`growth_phases` to:
- Example responses (show the field in context)
- Mistakes section where relevant (add: "growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — it is NOT a gene-specific property. All genes at the same experiment×timepoint share the same growth_phase.")
- Filter documentation

Key updates per tool:

**list_filter_values.yaml**: Add `growth_phase` to examples showing all filter types.

**list_experiments.yaml**: Add `growth_phases` filter param, show `growth_phases` and `time_point_growth_phases` in example response, show `by_growth_phase` in summary.

**list_publications.yaml**: Add `growth_phases` filter param and `growth_phases` in example response.

**list_organisms.yaml**: Add `growth_phases` in example response.

**list_clustering_analyses.yaml**: Add `growth_phases` filter and `growth_phases` in example response.

**differential_expression_by_gene.yaml**: Add `growth_phases` filter param, show `growth_phase` per row, show `rows_by_growth_phase` in summary.

**differential_expression_by_ortholog.yaml**: Same pattern as DE by gene.

**pathway_enrichment.yaml**: Add `growth_phases` filter param, show `growth_phase` per cluster row.

- [ ] **Step 2: Regenerate MCP resource markdown**

Run: `uv run python scripts/build_about_content.py`

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/inputs/tools/ multiomics_explorer/skills/
git commit -m "docs: add growth_phase to tool YAML specs and regenerate MCP resources"
```

---

### Task 14: Integration tests and regression fixtures

- [ ] **Step 1: Run integration tests**

Run: `pytest -m kg -v`
Expected: Some regression tests may fail due to new columns.

- [ ] **Step 2: Regenerate regression fixtures**

Run: `pytest -m kg tests/regression/test_regression.py --force-regen -v`

- [ ] **Step 3: Verify regression tests pass**

Run: `pytest -m kg tests/regression/test_regression.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/regression/
git commit -m "test: regenerate regression fixtures for growth_phase integration"
```

---

### Task 15: Smoke test

- [ ] **Step 1: Run full unit test suite**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 2: Run full integration test suite**

Run: `pytest -m kg -v`
Expected: All PASS

- [ ] **Step 3: Restart MCP and smoke test**

Run `/mcp` to restart the MCP server, then test:

```
list_filter_values(filter_type="growth_phase")
```

Verify: returns 10 growth phases with experiment counts.

```
list_experiments(growth_phases=["exponential"], summary=true)
```

Verify: `by_growth_phase` appears in response; results filtered to experiments with exponential-phase data.

```
list_experiments(growth_phases=["nutrient_limited"], limit=2)
```

Verify: `growth_phases` and `time_point_growth_phases` appear on each result.

```
differential_expression_by_gene(organism="MED4", growth_phases=["exponential"], significant_only=true, limit=3)
```

Verify: `growth_phase` appears on each row; all rows have `growth_phase: "exponential"`; `rows_by_growth_phase` in summary.

```
list_organisms(limit=3)
```

Verify: `growth_phases` appears on each organism.
