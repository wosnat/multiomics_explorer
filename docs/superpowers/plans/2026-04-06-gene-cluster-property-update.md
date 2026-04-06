# GeneCluster Property Update — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propagate GeneCluster property renames/removals and cluster_type value changes from a KG rebuild through all code layers.

**Architecture:** Bottom-up: constants → query builders → API docstrings → MCP tool models → YAML inputs → regenerate skill docs → analysis frames → tests. Each task produces a commit.

**Tech Stack:** Python, Pydantic, Neo4j Cypher, pytest

**Spec:** `docs/superpowers/specs/2026-04-06-gene-cluster-property-update-design.md`

---

### Task 1: Update constants

**Files:**
- Modify: `multiomics_explorer/kg/constants.py`

- [ ] **Step 1: Update VALID_CLUSTER_TYPES**

Replace the 7 old values with 4 new values:

```python
VALID_CLUSTER_TYPES: set[str] = {
    "classification",
    "condition_comparison",
    "diel",
    "time_course",
}
```

- [ ] **Step 2: Verify import**

Run: `python -c "from multiomics_explorer.kg.constants import VALID_CLUSTER_TYPES; print(sorted(VALID_CLUSTER_TYPES))"`
Expected: `['classification', 'condition_comparison', 'diel', 'time_course']`

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/kg/constants.py
git commit -m "fix: update VALID_CLUSTER_TYPES to match KG rebuild"
```

---

### Task 2: Update query builders

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py`

- [ ] **Step 1: Update `build_list_clustering_analyses` verbose cluster collect (~line 2937-2943)**

Replace:
```python
        cluster_collect = (
            "collect({cluster_id: gc.id, name: gc.name,"
            " member_count: gc.member_count,"
            " functional_description: gc.functional_description,"
            " behavioral_description: gc.behavioral_description,"
            " peak_time_hours: gc.peak_time_hours,"
            " period_hours: gc.period_hours}) AS clusters"
        )
```

With:
```python
        cluster_collect = (
            "collect({cluster_id: gc.id, name: gc.name,"
            " member_count: gc.member_count,"
            " functional_description: gc.functional_description,"
            " expression_dynamics: gc.expression_dynamics,"
            " temporal_pattern: gc.temporal_pattern}) AS clusters"
        )
```

- [ ] **Step 2: Update `build_list_clustering_analyses` docstring (~line 2889-2890)**

Replace:
```
    Inline clusters (verbose): adds functional_description, behavioral_description,
    peak_time_hours, period_hours.
```

With:
```
    Inline clusters (verbose): adds functional_description, expression_dynamics,
    temporal_pattern.
```

- [ ] **Step 3: Update `build_gene_clusters_by_gene` verbose_cols (~line 3130-3140)**

Replace:
```python
        verbose_cols = (
            ",\n       ca.cluster_method AS cluster_method"
            ",\n       gc.member_count AS member_count"
            ",\n       gc.functional_description AS cluster_functional_description"
            ",\n       gc.behavioral_description AS cluster_behavioral_description"
            ",\n       ca.treatment AS treatment"
            ",\n       ca.light_condition AS light_condition"
            ",\n       ca.experimental_context AS experimental_context"
            ",\n       r.p_value AS p_value"
            ",\n       gc.peak_time_hours AS peak_time_hours"
            ",\n       gc.period_hours AS period_hours"
        )
```

With:
```python
        verbose_cols = (
            ",\n       ca.cluster_method AS cluster_method"
            ",\n       gc.member_count AS member_count"
            ",\n       gc.functional_description AS cluster_functional_description"
            ",\n       gc.expression_dynamics AS cluster_expression_dynamics"
            ",\n       gc.temporal_pattern AS cluster_temporal_pattern"
            ",\n       ca.treatment AS treatment"
            ",\n       ca.light_condition AS light_condition"
            ",\n       ca.experimental_context AS experimental_context"
            ",\n       r.p_value AS p_value"
        )
```

- [ ] **Step 4: Update `build_gene_clusters_by_gene` docstring (~line 3094-3097)**

Replace:
```
    RETURN keys (verbose): adds cluster_method, member_count,
    cluster_functional_description, cluster_behavioral_description,
    treatment, light_condition, experimental_context,
    p_value, peak_time_hours, period_hours.
```

With:
```
    RETURN keys (verbose): adds cluster_method, member_count,
    cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern, treatment, light_condition,
    experimental_context, p_value.
```

- [ ] **Step 5: Update `build_genes_in_cluster` verbose_cols (~line 3286-3292)**

Replace:
```python
        verbose_cols = (
            ",\n       g.function_description AS gene_function_description"
            ",\n       g.gene_summary AS gene_summary"
            ",\n       r.p_value AS p_value"
            ",\n       gc.functional_description AS cluster_functional_description"
            ",\n       gc.behavioral_description AS cluster_behavioral_description"
        )
```

With:
```python
        verbose_cols = (
            ",\n       g.function_description AS gene_function_description"
            ",\n       g.gene_summary AS gene_summary"
            ",\n       r.p_value AS p_value"
            ",\n       gc.functional_description AS cluster_functional_description"
            ",\n       gc.expression_dynamics AS cluster_expression_dynamics"
            ",\n       gc.temporal_pattern AS cluster_temporal_pattern"
        )
```

- [ ] **Step 6: Update `build_genes_in_cluster` docstring (~line 3279-3280)**

Replace:
```
    RETURN keys (verbose): adds gene_function_description, gene_summary,
    p_value, cluster_functional_description, cluster_behavioral_description.
```

With:
```
    RETURN keys (verbose): adds gene_function_description, gene_summary,
    p_value, cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern.
```

- [ ] **Step 7: Verify import**

Run: `python -c "from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses, build_gene_clusters_by_gene, build_genes_in_cluster; print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py
git commit -m "fix: update GeneCluster property references in query builders"
```

---

### Task 3: Update API docstrings

**Files:**
- Modify: `multiomics_explorer/api/functions.py`

- [ ] **Step 1: Update `gene_clusters_by_gene` docstring (~line 2265-2268)**

Replace:
```
    Per result (verbose): adds cluster_method, member_count,
    cluster_functional_description, cluster_behavioral_description,
    treatment, light_condition, experimental_context,
    p_value, peak_time_hours, period_hours.
```

With:
```
    Per result (verbose): adds cluster_method, member_count,
    cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern, treatment, light_condition,
    experimental_context, p_value.
```

- [ ] **Step 2: Update `genes_in_cluster` docstring (~line 2365-2366)**

Replace:
```
    Per result (verbose): adds gene_function_description, gene_summary,
    p_value, cluster_functional_description, cluster_behavioral_description.
```

With:
```
    Per result (verbose): adds gene_function_description, gene_summary,
    p_value, cluster_functional_description, cluster_expression_dynamics,
    cluster_temporal_pattern.
```

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/api/functions.py
git commit -m "fix: update API docstrings for GeneCluster property renames"
```

---

### Task 4: Update MCP tool Pydantic models

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`

- [ ] **Step 1: Update `InlineCluster` model (~line 2572-2579)**

Replace:
```python
        # verbose-only
        functional_description: str | None = Field(default=None,
            description="What the cluster genes ARE")
        behavioral_description: str | None = Field(default=None,
            description="What the cluster genes DO together")
        peak_time_hours: float | None = Field(default=None,
            description="Peak expression time in hours (diel clusters)")
        period_hours: float | None = Field(default=None,
            description="Expression period in hours (diel clusters)")
```

With:
```python
        # verbose-only
        functional_description: str | None = Field(default=None,
            description="What the cluster genes ARE")
        expression_dynamics: str | None = Field(default=None,
            description="Expression dynamics label (e.g. 'periodic in L:D only')")
        temporal_pattern: str | None = Field(default=None,
            description="Detailed temporal pattern description")
```

- [ ] **Step 2: Update `list_clustering_analyses` verbose description (~line 2682-2685)**

Replace:
```python
        verbose: Annotated[bool, Field(
            description="Include treatment, light_condition, experimental_context "
            "on analyses; functional_description, behavioral_description, "
            "peak_time_hours, period_hours on inline clusters.",
        )] = False,
```

With:
```python
        verbose: Annotated[bool, Field(
            description="Include treatment, light_condition, experimental_context "
            "on analyses; functional_description, expression_dynamics, "
            "temporal_pattern on inline clusters.",
        )] = False,
```

- [ ] **Step 3: Update `GeneClusterResult` model (~line 2783-2790)**

Replace:
```python
        cluster_functional_description: str | None = Field(default=None,
            description="What the cluster genes ARE (cluster-level)")
        cluster_behavioral_description: str | None = Field(default=None,
            description="What the cluster genes DO together (cluster-level)")
        peak_time_hours: float | None = Field(default=None,
            description="Peak expression time in hours (diel clusters)")
        period_hours: float | None = Field(default=None,
            description="Expression period in hours (diel clusters)")
```

With:
```python
        cluster_functional_description: str | None = Field(default=None,
            description="What the cluster genes ARE (cluster-level)")
        cluster_expression_dynamics: str | None = Field(default=None,
            description="Expression dynamics label (e.g. 'periodic in L:D only')")
        cluster_temporal_pattern: str | None = Field(default=None,
            description="Detailed temporal pattern description (cluster-level)")
```

- [ ] **Step 4: Update `gene_clusters_by_gene` verbose description (~line 2860-2864)**

Replace:
```python
        verbose: Annotated[bool, Field(
            description="Include cluster_method, member_count, "
            "cluster_functional_description, cluster_behavioral_description, "
            "peak_time_hours, period_hours, treatment, light_condition, "
            "experimental_context, p_value.",
        )] = False,
```

With:
```python
        verbose: Annotated[bool, Field(
            description="Include cluster_method, member_count, "
            "cluster_functional_description, cluster_expression_dynamics, "
            "cluster_temporal_pattern, treatment, light_condition, "
            "experimental_context, p_value.",
        )] = False,
```

- [ ] **Step 5: Update `GenesInClusterResult` model (~line 2951-2954)**

Replace:
```python
        cluster_functional_description: str | None = Field(default=None,
            description="What the cluster genes ARE (cluster-level)")
        cluster_behavioral_description: str | None = Field(default=None,
            description="What the cluster genes DO together (cluster-level)")
```

With:
```python
        cluster_functional_description: str | None = Field(default=None,
            description="What the cluster genes ARE (cluster-level)")
        cluster_expression_dynamics: str | None = Field(default=None,
            description="Expression dynamics label (e.g. 'periodic in L:D only')")
        cluster_temporal_pattern: str | None = Field(default=None,
            description="Detailed temporal pattern description (cluster-level)")
```

- [ ] **Step 6: Update `genes_in_cluster` verbose description (~line 3015-3018)**

Replace:
```python
        verbose: Annotated[bool, Field(
            description="Include gene_function_description, gene_summary (gene-level), "
            "p_value (edge-level), cluster_functional_description, "
            "cluster_behavioral_description (cluster-level).",
        )] = False,
```

With:
```python
        verbose: Annotated[bool, Field(
            description="Include gene_function_description, gene_summary (gene-level), "
            "p_value (edge-level), cluster_functional_description, "
            "cluster_expression_dynamics, cluster_temporal_pattern (cluster-level).",
        )] = False,
```

- [ ] **Step 7: Update cluster_type example values in `e.g.` strings**

Update these lines (replace old example values with new ones):

- Line 117: `"Distinct cluster types (e.g. ['response_pattern', 'diel_cycling'])"` → `"Distinct cluster types (e.g. ['condition_comparison', 'diel'])"`
- Line 129: `"Cluster type (e.g. 'response_pattern')"` → `"Cluster type (e.g. 'condition_comparison')"`
- Line 388: `"Distinct cluster types (e.g. ['condition_comparison', 'diel'])"` — already correct, skip
- Line 591: `"Cluster category (e.g. 'stress_response')"` → `"Cluster category (e.g. 'condition_comparison')"`
- Line 1003: `"Distinct cluster types (e.g. ['response_pattern'])"` → `"Distinct cluster types (e.g. ['condition_comparison'])"`
- Line 1027: `"Cluster type (e.g. 'response_pattern')"` → `"Cluster type (e.g. 'condition_comparison')"`
- Line 1156: `"Distinct cluster types (e.g. ['response_pattern'])"` → `"Distinct cluster types (e.g. ['condition_comparison'])"`
- Line 1195: `"Cluster type (e.g. 'response_pattern')"` → `"Cluster type (e.g. 'condition_comparison')"`

- [ ] **Step 8: Verify import**

Run: `python -c "from multiomics_explorer.mcp_server.tools import register_tools; print('OK')"`
Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "fix: update MCP tool models for GeneCluster property renames"
```

---

### Task 5: Update YAML inputs and regenerate skill docs

**Files:**
- Modify: `multiomics_explorer/inputs/tools/gene_clusters_by_gene.yaml`
- Modify: `multiomics_explorer/inputs/tools/genes_in_cluster.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_clustering_analyses.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_organisms.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_publications.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_experiments.yaml`
- Regenerate: `multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md`

- [ ] **Step 1: Update `gene_clusters_by_gene.yaml`**

Line 13: change `cluster_type="stress_response"` → `cluster_type="condition_comparison"`

Lines 27-32 (verbose_fields): replace entire block with:
```yaml
verbose_fields:
  - cluster_functional_description
  - cluster_expression_dynamics
  - cluster_temporal_pattern
  - cluster_method
  - member_count
  - treatment
  - light_condition
  - experimental_context
  - p_value
```

- [ ] **Step 2: Update `genes_in_cluster.yaml`**

Lines 27-31 (verbose_fields): replace entire block with:
```yaml
verbose_fields:
  - gene_function_description
  - gene_summary
  - p_value
  - cluster_functional_description
  - cluster_expression_dynamics
  - cluster_temporal_pattern
```

- [ ] **Step 3: Update `list_clustering_analyses.yaml`**

Lines 27-33 (verbose_fields): replace entire block with:
```yaml
verbose_fields:
  - treatment
  - light_condition
  - experimental_context
  - "clusters[].functional_description"
  - "clusters[].expression_dynamics"
  - "clusters[].temporal_pattern"
```

- [ ] **Step 4: Update `list_organisms.yaml`**

Line 15: in the example response, change `"cluster_types": ["response_pattern", "diel_cycling", "expression_level"]` → `"cluster_types": ["condition_comparison", "diel", "classification"]`

- [ ] **Step 5: Update `list_publications.yaml`**

Line 14: change `"by_cluster_type": [{"cluster_type": "response_pattern", "count": 4}, ...]` → `"by_cluster_type": [{"cluster_type": "condition_comparison", "count": 4}, ...]`

Line 18: change `"cluster_types": ["response_pattern"]` → `"cluster_types": ["condition_comparison"]`

- [ ] **Step 6: Update `list_experiments.yaml`**

Line 14: change `"by_cluster_type": [{"cluster_type": "response_pattern", "count": 7}, ...]` → `"by_cluster_type": [{"cluster_type": "condition_comparison", "count": 7}, ...]`

- [ ] **Step 7: Regenerate skill reference docs**

Run: `uv run python scripts/build_about_content.py`
Expected: all tools built successfully, no errors

- [ ] **Step 8: Verify generated docs contain new field names**

Run: `grep -l "expression_dynamics" multiomics_explorer/skills/multiomics-kg-guide/references/tools/gene_clusters_by_gene.md multiomics_explorer/skills/multiomics-kg-guide/references/tools/genes_in_cluster.md multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_clustering_analyses.md`
Expected: all 3 files listed

Run: `grep "behavioral_description" multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md`
Expected: no matches

- [ ] **Step 9: Commit**

```bash
git add multiomics_explorer/inputs/tools/*.yaml multiomics_explorer/skills/multiomics-kg-guide/references/tools/*.md
git commit -m "fix: update YAML inputs and regenerate skill docs for cluster property renames"
```

---

### Task 6: Update analysis frames

**Files:**
- Modify: `multiomics_explorer/analysis/frames.py`
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/to_dataframe.md`

- [ ] **Step 1: Update `_VERBOSE_CLUSTER_FIELDS` in `frames.py` (~line 180-185)**

Replace:
```python
    _VERBOSE_CLUSTER_FIELDS = (
        "functional_description",
        "behavioral_description",
        "peak_time_hours",
        "period_hours",
    )
```

With:
```python
    _VERBOSE_CLUSTER_FIELDS = (
        "functional_description",
        "expression_dynamics",
        "temporal_pattern",
    )
```

- [ ] **Step 2: Update docstring in `frames.py` (~line 160-163)**

Replace:
```
        (when present): ``cluster_functional_description``,
        ``cluster_behavioral_description``, ``cluster_peak_time_hours``,
        ``cluster_period_hours``.
```

With:
```
        (when present): ``cluster_functional_description``,
        ``cluster_expression_dynamics``, ``cluster_temporal_pattern``.
```

- [ ] **Step 3: Update `to_dataframe.md` (~line 177-179)**

Replace:
```
`verbose=True`): `cluster_functional_description`,
`cluster_behavioral_description`, `cluster_peak_time_hours`,
`cluster_period_hours`.
```

With:
```
`verbose=True`): `cluster_functional_description`,
`cluster_expression_dynamics`, `cluster_temporal_pattern`.
```

- [ ] **Step 4: Update `to_dataframe.md` example (~line 212-213)**

Replace:
```
# Extra columns: cluster_functional_description, cluster_behavioral_description,
#                cluster_peak_time_hours, cluster_period_hours
```

With:
```
# Extra columns: cluster_functional_description, cluster_expression_dynamics,
#                cluster_temporal_pattern
```

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/frames.py multiomics_explorer/skills/multiomics-kg-guide/references/analysis/to_dataframe.md
git commit -m "fix: update analysis frames for GeneCluster property renames"
```

---

### Task 7: Update unit tests — query builders

**Files:**
- Modify: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Update `test_verbose_adds_cluster_descriptions` (~line 2836-2840)**

Replace:
```python
    def test_verbose_adds_cluster_descriptions(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(verbose=True)
        assert "functional_description" in cypher
        assert "behavioral_description" in cypher
```

With:
```python
    def test_verbose_adds_cluster_descriptions(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(verbose=True)
        assert "functional_description" in cypher
        assert "expression_dynamics" in cypher
        assert "temporal_pattern" in cypher
```

- [ ] **Step 2: Update `test_verbose_adds_columns` for gene_clusters_by_gene (~line 2982-2992)**

Replace:
```python
    def test_verbose_adds_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=True)
        for col in ["cluster_functional_description",
                     "cluster_behavioral_description",
                     "cluster_method", "member_count",
                     "treatment", "light_condition",
                     "experimental_context", "p_value",
                     "peak_time_hours", "period_hours"]:
            assert f"AS {col}" in cypher, f"Missing verbose column: {col}"
```

With:
```python
    def test_verbose_adds_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=True)
        for col in ["cluster_functional_description",
                     "cluster_expression_dynamics",
                     "cluster_temporal_pattern",
                     "cluster_method", "member_count",
                     "treatment", "light_condition",
                     "experimental_context", "p_value"]:
            assert f"AS {col}" in cypher, f"Missing verbose column: {col}"
```

- [ ] **Step 3: Update `test_verbose_false_omits_verbose_columns` (~line 2994-2999)**

Replace:
```python
    def test_verbose_false_omits_verbose_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=False)
        assert "cluster_functional_description" not in cypher
        assert "cluster_behavioral_description" not in cypher
```

With:
```python
    def test_verbose_false_omits_verbose_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=False)
        assert "cluster_functional_description" not in cypher
        assert "cluster_expression_dynamics" not in cypher
```

- [ ] **Step 4: Update `test_verbose_renamed_columns` for genes_in_cluster (~line 3078-3092)**

Replace:
```python
    def test_verbose_renamed_columns(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, _ = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            verbose=True)
        for col in ["gene_function_description", "gene_summary",
                     "p_value", "cluster_functional_description",
                     "cluster_behavioral_description"]:
            assert f"AS {col}" in cypher, f"Missing verbose column: {col}"
        # Old column names must NOT appear
        assert "AS function_description" not in cypher
        assert "AS functional_description" not in cypher.replace(
            "cluster_functional_description", "")
        assert "AS behavioral_description" not in cypher.replace(
            "cluster_behavioral_description", "")
```

With:
```python
    def test_verbose_renamed_columns(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, _ = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            verbose=True)
        for col in ["gene_function_description", "gene_summary",
                     "p_value", "cluster_functional_description",
                     "cluster_expression_dynamics",
                     "cluster_temporal_pattern"]:
            assert f"AS {col}" in cypher, f"Missing verbose column: {col}"
        # Old column names must NOT appear
        assert "AS function_description" not in cypher
        assert "AS functional_description" not in cypher.replace(
            "cluster_functional_description", "")
        assert "AS expression_dynamics" not in cypher.replace(
            "cluster_expression_dynamics", "")
```

- [ ] **Step 5: Update `test_cluster_type_filter` example value (~line 2709-2714)**

Replace `"response_pattern"` with `"condition_comparison"`:
```python
    def test_cluster_type_filter(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(cluster_type="condition_comparison")
        assert len(conditions) == 1
        assert "$cluster_type" in conditions[0]
        assert params["cluster_type"] == "condition_comparison"
```

- [ ] **Step 6: Update `test_combined_filters` if it uses old cluster_type values**

Check line ~2743 — if it uses `cluster_type="response_pattern"`, change to `cluster_type="condition_comparison"`.

- [ ] **Step 7: Run query builder tests**

Run: `pytest tests/unit/test_query_builders.py -v -k "clustering or gene_cluster or genes_in_cluster"`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add tests/unit/test_query_builders.py
git commit -m "test: update query builder tests for GeneCluster property renames"
```

---

### Task 8: Update unit tests — API functions

**Files:**
- Modify: `tests/unit/test_api_functions.py`

- [ ] **Step 1: Update `TestListOrganisms._ROWS` fixture (~line 766)**

Replace `"cluster_types": ["response_pattern", "diel_cycling"]` with `"cluster_types": ["condition_comparison", "diel"]`

- [ ] **Step 2: Update `test_by_cluster_type_in_envelope` assertions (~line 806-809)**

Replace:
```python
        # MED4 has response_pattern and diel_cycling; EZ55 has none
        ct_map = {b["cluster_type"]: b["count"] for b in result["by_cluster_type"]}
        assert ct_map["response_pattern"] == 1
        assert ct_map["diel_cycling"] == 1
```

With:
```python
        # MED4 has condition_comparison and diel; EZ55 has none
        ct_map = {b["cluster_type"]: b["count"] for b in result["by_cluster_type"]}
        assert ct_map["condition_comparison"] == 1
        assert ct_map["diel"] == 1
```

- [ ] **Step 3: Update `TestListPublications._PUB_ROW` fixture (~line 1474)**

Replace `"cluster_types": ["response_pattern"]` with `"cluster_types": ["condition_comparison"]`

- [ ] **Step 4: Update `test_by_cluster_type_computed` assertion (~line 1558-1559)**

Replace:
```python
        ct_map = {b["cluster_type"]: b["count"] for b in result["by_cluster_type"]}
        assert ct_map["response_pattern"] == 1
```

With:
```python
        ct_map = {b["cluster_type"]: b["count"] for b in result["by_cluster_type"]}
        assert ct_map["condition_comparison"] == 1
```

- [ ] **Step 5: Update `TestListExperiments._summary_result` fixture (~line 1611)**

Replace `"by_cluster_type": [{"item": "response_pattern", "count": 3}]` with `"by_cluster_type": [{"item": "condition_comparison", "count": 3}]`

- [ ] **Step 6: Update `TestListExperiments._detail_row` fixture (~line 1638)**

Replace `"cluster_types": ["response_pattern"]` with `"cluster_types": ["condition_comparison"]`

- [ ] **Step 7: Update `test_summary_contains_envelope` assertion (~line 1819)**

Replace `assert result["by_cluster_type"][0]["cluster_type"] == "response_pattern"` with `assert result["by_cluster_type"][0]["cluster_type"] == "condition_comparison"`

- [ ] **Step 8: Run API function tests**

Run: `pytest tests/unit/test_api_functions.py -v -k "organism or publication or experiment"`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add tests/unit/test_api_functions.py
git commit -m "test: update API function tests for cluster_type value changes"
```

---

### Task 9: Update unit tests — frames

**Files:**
- Modify: `tests/unit/test_frames.py`

- [ ] **Step 1: Update verbose fixture data (~line 464-472)**

Replace:
```python
                    "functional_description": "ribosomal genes",
                    "behavioral_description": "early induction",
                    "peak_time_hours": 6.0,
                    "period_hours": None,
```

With:
```python
                    "functional_description": "ribosomal genes",
                    "expression_dynamics": "early induction",
                    "temporal_pattern": "Genes induced early under stress",
```

- [ ] **Step 2: Update `test_verbose_cluster_fields` assertions (~line 523-532)**

Replace:
```python
    def test_verbose_cluster_fields(self):
        """Verbose fields present → columns for functional/behavioral/peak/period."""
        df = analyses_to_dataframe(_ANALYSES_RESULT_VERBOSE)
        assert "cluster_functional_description" in df.columns
        assert "cluster_behavioral_description" in df.columns
        assert "cluster_peak_time_hours" in df.columns
        assert "cluster_period_hours" in df.columns
        row = df.iloc[0]
        assert row["cluster_functional_description"] == "ribosomal genes"
        assert row["cluster_peak_time_hours"] == 6.0
```

With:
```python
    def test_verbose_cluster_fields(self):
        """Verbose fields present → columns for expression_dynamics/temporal_pattern."""
        df = analyses_to_dataframe(_ANALYSES_RESULT_VERBOSE)
        assert "cluster_functional_description" in df.columns
        assert "cluster_expression_dynamics" in df.columns
        assert "cluster_temporal_pattern" in df.columns
        row = df.iloc[0]
        assert row["cluster_functional_description"] == "ribosomal genes"
        assert row["cluster_expression_dynamics"] == "early induction"
```

- [ ] **Step 3: Run frames tests**

Run: `pytest tests/unit/test_frames.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_frames.py
git commit -m "test: update frames tests for GeneCluster property renames"
```

---

### Task 10: Update integration tests and CyVer config

**Files:**
- Modify: `tests/integration/test_cyver_queries.py`
- Modify: `tests/integration/test_api_contract.py`

- [ ] **Step 1: Update `_KNOWN_MAP_KEYS` in `test_cyver_queries.py` (~line 129)**

Replace:
```python
    "peak_time_hours", "period_hours", "p_value",
```

With:
```python
    "p_value",
```

Also update the comment at line 121:
Replace `e.g. peak_time_hours on GeneCluster` with `e.g. p_value on Gene_in_gene_cluster`

- [ ] **Step 2: Update `test_api_contract.py` references (~line 891, 955)**

Replace `"cluster_behavioral_description"` with `"cluster_expression_dynamics"` and add `"cluster_temporal_pattern"` where appropriate. (Check the exact assertions during implementation — these are verbose field checks.)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_cyver_queries.py tests/integration/test_api_contract.py
git commit -m "test: update integration tests for GeneCluster property renames"
```

---

### Task 11: Regenerate regression fixtures

**Files:**
- Regenerate: `tests/regression/test_regression/*.yml`

- [ ] **Step 1: Regenerate regression fixtures**

Run: `uv run python scripts/build_test_fixtures.py`
Expected: fixtures regenerated with new cluster_type values

- [ ] **Step 2: Verify no old values remain**

Run: `grep -r "response_pattern\|diel_cycling\|expression_classification\|expression_level\|expression_pattern\|periodicity_classification\|diel_expression_pattern" tests/regression/`
Expected: no matches

- [ ] **Step 3: Commit**

```bash
git add tests/regression/
git commit -m "test: regenerate regression fixtures for KG rebuild"
```

---

### Task 12: Run full test suite

**Files:** none (verification only)

- [ ] **Step 1: Run unit tests**

Run: `pytest tests/unit/ -v`
Expected: all PASS

- [ ] **Step 2: Run integration tests (requires Neo4j)**

Run: `pytest -m kg -v`
Expected: all PASS

- [ ] **Step 3: Fix any remaining failures**

If any test still references old property names or values, fix and commit.
