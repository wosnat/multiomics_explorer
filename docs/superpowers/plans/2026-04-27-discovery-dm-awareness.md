# Discovery DM-Awareness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface DerivedMetric rollups + first-class `compartment` axis on 5 existing discovery tools (`gene_overview`, `list_experiments`, `list_publications`, `list_organisms`, `list_filter_values`).

**Architecture:** Modify the 4 layers (queries_lib → api/functions → mcp_server/tools → about-content YAML) per [add-or-update-tool](.claude/skills/add-or-update-tool/SKILL.md). KG-side rollups (`derived_metric_count`, `derived_metric_value_kinds`, `compartment` etc.) are already materialized live, so most tasks unblocked. Two tasks (gene_overview verbose fields, fulltext-search assertions) gate on the companion KG spec ([2026-04-27-derived-metric-fulltext-enrichment.md](docs/kg-specs/2026-04-27-derived-metric-fulltext-enrichment.md)) landing in the KG repo.

**Tech Stack:** Python 3.11+, FastMCP, Neo4j 5 (Cypher + APOC), pytest, Pydantic v2.

**Spec:** [2026-04-27-discovery-dm-awareness-design.md](docs/superpowers/specs/2026-04-27-discovery-dm-awareness-design.md)

---

## File structure

| File | Role | Tasks touching |
|---|---|---|
| `multiomics_explorer/kg/queries_lib.py` | Query builders | 1, 2, 3, 4, 5, 6 |
| `multiomics_explorer/api/functions.py` | API functions, envelope assembly | 1, 2, 3, 4, 5, 6 |
| `multiomics_explorer/mcp_server/tools.py` | MCP wrappers, Pydantic models | 1, 2, 3, 4, 5, 6 |
| `multiomics_explorer/inputs/tools/{name}.yaml` × 5 | About-content authoring | 7 |
| `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md` × 5 | Generated about content | 7 (regen) |
| `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/derived_metrics.md` | Hand-authored analysis ref | 7 |
| `tests/unit/test_query_builders.py` | Builder unit tests | 1–6 |
| `tests/unit/test_api_functions.py` | API unit tests | 1–6 |
| `tests/unit/test_tool_wrappers.py` | MCP wrapper tests, EXPECTED_TOOLS | 1–6 |
| `tests/integration/test_mcp_tools.py` | Live-KG integration tests | 1–6 |
| `tests/evals/cases.yaml` | Regression eval cases | 7 |
| `tests/regression/test_regression.py` | TOOL_BUILDERS registry | 7 |
| `tests/regression/test_regression/*.yml` | Regression baselines | 7 (regen) |
| `CLAUDE.md` | MCP Tools table | 7 |

## Task ordering

KG side (D5 + D8) was verified live before implementation began (2026-04-27 evening), so all tasks are unblocked. Task 5 absorbs the previous Task 6 (verbose per-kind + post-D8 rename adoption) since the KG already exposes the renamed names.

1. **list_filter_values** — 3 new filter types.
2. **list_organisms** — DM rollups + compartment filter.
3. **list_publications** — same shape as 2.
4. **list_experiments** — scalar compartment.
5. **gene_overview (full)** — compact + envelope + verbose per-kind fields, using post-D8 names directly. (Plan's old Task 6 is folded in.)
6. **Regression baselines + about content + CLAUDE.md** (plan's old Task 7).
7. **Fulltext-search assertions** (plan's old Task 8) — validates D5 token routing.

All tasks must be **strictly serial** because they all touch the same source/test files (the user's no-shared-files-concurrent constraint). Worktree-style parallelism is not applicable here.

---

## Task 1: `list_filter_values` — add `metric_type`, `value_kind`, `compartment` types

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (add 3 builders near `build_list_growth_phases:919`)
- Modify: `multiomics_explorer/api/functions.py:528-567` (extend dispatch)
- Modify: `multiomics_explorer/mcp_server/tools.py` (extend `Literal` for `filter_type` param + docstring)
- Modify: `tests/unit/test_query_builders.py` (add 3 test classes)
- Modify: `tests/unit/test_api_functions.py` (extend `TestListFilterValues`)
- Modify: `tests/unit/test_tool_wrappers.py` (extend wrapper test)
- Modify: `tests/integration/test_mcp_tools.py` (live-KG assertions)

- [ ] **Step 1: Write failing unit tests for the 3 new builders**

In `tests/unit/test_query_builders.py`, add:

```python
class TestBuildListMetricTypes:
    def test_returns_value_and_count(self):
        from multiomics_explorer.kg.queries_lib import build_list_metric_types
        cypher, params = build_list_metric_types()
        assert "MATCH (dm:DerivedMetric)" in cypher
        assert "dm.metric_type AS value" in cypher
        assert "count(*) AS count" in cypher
        assert "ORDER BY count DESC" in cypher
        assert params == {}


class TestBuildListValueKinds:
    def test_returns_value_and_count(self):
        from multiomics_explorer.kg.queries_lib import build_list_value_kinds
        cypher, params = build_list_value_kinds()
        assert "dm.value_kind AS value" in cypher
        assert "count(*) AS count" in cypher
        assert params == {}


class TestBuildListCompartments:
    def test_sources_from_experiment_not_derived_metric(self):
        """D7: Experiment.compartment is the source-of-truth (wet-lab fraction)."""
        from multiomics_explorer.kg.queries_lib import build_list_compartments
        cypher, params = build_list_compartments()
        assert "MATCH (e:Experiment)" in cypher
        assert "e.compartment AS value" in cypher
        assert "DerivedMetric" not in cypher
        assert params == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListMetricTypes tests/unit/test_query_builders.py::TestBuildListValueKinds tests/unit/test_query_builders.py::TestBuildListCompartments -v
```
Expected: FAIL with `ImportError: cannot import name 'build_list_metric_types'` (etc.)

- [ ] **Step 3: Implement the 3 builders**

In `multiomics_explorer/kg/queries_lib.py`, after `build_list_growth_phases` (line ~933), add:

```python
def build_list_metric_types() -> tuple[str, dict]:
    """List distinct DerivedMetric.metric_type values with DM counts.

    RETURN keys: value, count.
    """
    cypher = (
        "MATCH (dm:DerivedMetric) WHERE dm.metric_type IS NOT NULL\n"
        "RETURN dm.metric_type AS value, count(*) AS count\n"
        "ORDER BY count DESC, value"
    )
    return cypher, {}


def build_list_value_kinds() -> tuple[str, dict]:
    """List DerivedMetric.value_kind enum values with DM counts per kind.

    RETURN keys: value, count. Today's KG: {numeric, boolean, categorical}.
    """
    cypher = (
        "MATCH (dm:DerivedMetric) WHERE dm.value_kind IS NOT NULL\n"
        "RETURN dm.value_kind AS value, count(*) AS count\n"
        "ORDER BY count DESC, value"
    )
    return cypher, {}


def build_list_compartments() -> tuple[str, dict]:
    """List distinct Experiment.compartment values with experiment counts.

    Sourced from Experiment.compartment (wet-lab fraction), per slice-2 D7.

    RETURN keys: value, count.
    """
    cypher = (
        "MATCH (e:Experiment) WHERE e.compartment IS NOT NULL\n"
        "RETURN e.compartment AS value, count(*) AS count\n"
        "ORDER BY count DESC, value"
    )
    return cypher, {}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListMetricTypes tests/unit/test_query_builders.py::TestBuildListValueKinds tests/unit/test_query_builders.py::TestBuildListCompartments -v
```
Expected: 3 passed.

- [ ] **Step 5: Write failing API dispatch test**

In `tests/unit/test_api_functions.py`, extend `TestListFilterValues`:

```python
def test_dispatches_metric_type(self, mock_conn):
    mock_conn.execute_query.return_value = [
        {"value": "damping_ratio", "count": 4},
        {"value": "diel_amplitude_protein_log2", "count": 2},
    ]
    result = list_filter_values(filter_type="metric_type", conn=mock_conn)
    assert result["filter_type"] == "metric_type"
    assert result["total_entries"] == 2
    assert result["results"][0] == {"value": "damping_ratio", "count": 4}

def test_dispatches_value_kind(self, mock_conn):
    mock_conn.execute_query.return_value = [
        {"value": "boolean", "count": 14},
        {"value": "numeric", "count": 15},
    ]
    result = list_filter_values(filter_type="value_kind", conn=mock_conn)
    assert {r["value"] for r in result["results"]} == {"boolean", "numeric"}

def test_dispatches_compartment(self, mock_conn):
    mock_conn.execute_query.return_value = [
        {"value": "whole_cell", "count": 160},
        {"value": "vesicle", "count": 5},
    ]
    result = list_filter_values(filter_type="compartment", conn=mock_conn)
    assert result["total_entries"] == 2
    assert result["results"][0]["value"] == "whole_cell"
```

- [ ] **Step 6: Run test to verify failure**

```bash
pytest tests/unit/test_api_functions.py::TestListFilterValues -v -k "dispatches"
```
Expected: FAIL with `ValueError: Unknown filter_type: 'metric_type'`.

- [ ] **Step 7: Extend API dispatch**

In `multiomics_explorer/api/functions.py:528-567`, replace the existing function body's dispatch block with:

```python
def list_filter_values(
    filter_type: str = "gene_category",
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List valid values for a categorical filter.

    Returns dict with keys: filter_type, total_entries, returned, truncated, results.
    Per result: value, count.

    filter_type options:
      - ``gene_category``: gene functional categories.
      - ``brite_tree``: KEGG BRITE hierarchy trees.
      - ``growth_phase``: growth phase values on Experiment nodes.
      - ``metric_type``: DerivedMetric.metric_type tag values (slice 2).
      - ``value_kind``: DerivedMetric.value_kind enum (slice 2).
      - ``compartment``: Experiment.compartment values (slice 2 / D7).
    """
    conn = _default_conn(conn)
    if filter_type == "gene_category":
        cypher, params = build_list_gene_categories()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["category"], "count": r["gene_count"]} for r in rows]
    elif filter_type == "brite_tree":
        cypher, params = build_list_brite_trees()
        rows = conn.execute_query(cypher, **params)
        results = [
            {"value": r["tree"], "tree_code": r["tree_code"], "count": r["term_count"]}
            for r in rows
        ]
    elif filter_type == "growth_phase":
        cypher, params = build_list_growth_phases()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["phase"], "count": r["experiment_count"]} for r in rows]
    elif filter_type == "metric_type":
        cypher, params = build_list_metric_types()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["value"], "count": r["count"]} for r in rows]
    elif filter_type == "value_kind":
        cypher, params = build_list_value_kinds()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["value"], "count": r["count"]} for r in rows]
    elif filter_type == "compartment":
        cypher, params = build_list_compartments()
        rows = conn.execute_query(cypher, **params)
        results = [{"value": r["value"], "count": r["count"]} for r in rows]
    else:
        raise ValueError(f"Unknown filter_type: {filter_type!r}")
    total = len(results)
    return {
        "filter_type": filter_type,
        "total_entries": total,
        "returned": total,
        "truncated": False,
        "results": results,
    }
```

Also update the import block at the top of `api/functions.py` (currently around line 46–47):

```python
from ..kg.queries_lib import (
    build_list_brite_trees,
    build_list_gene_categories,
    build_list_growth_phases,
    build_list_metric_types,
    build_list_value_kinds,
    build_list_compartments,
    # ... existing imports ...
)
```

- [ ] **Step 8: Run API test to verify pass**

```bash
pytest tests/unit/test_api_functions.py::TestListFilterValues -v
```
Expected: all pass.

- [ ] **Step 9: Update MCP wrapper Literal**

In `multiomics_explorer/mcp_server/tools.py`, find the `list_filter_values` wrapper (search `def list_filter_values`). Update the `filter_type` `Annotated[Literal[...], ...]` to include the 3 new values, and update the docstring/Field description listing valid values.

```python
filter_type: Annotated[
    Literal["gene_category", "brite_tree", "growth_phase",
            "metric_type", "value_kind", "compartment"],
    Field(description=(
        "Which categorical filter to enumerate. "
        "'gene_category' / 'brite_tree' / 'growth_phase' (existing); "
        "'metric_type' / 'value_kind' / 'compartment' (slice 2 — DerivedMetric "
        "discovery)."
    )),
] = "gene_category"
```

- [ ] **Step 10: Run wrapper unit tests**

```bash
pytest tests/unit/test_tool_wrappers.py -v -k "FilterValues"
```
Expected: pass (existing tests + Pydantic accepts new Literal values).

- [ ] **Step 11: Add live-KG integration assertions**

In `tests/integration/test_mcp_tools.py`, find `TestListFilterValues` and append:

```python
@pytest.mark.kg
async def test_metric_type_returns_baseline(self, client):
    r = await client.call_tool("list_filter_values", {"filter_type": "metric_type"})
    payload = r.structured_content
    # Slice-2 baseline 2026-04-27: 13 distinct metric_types
    assert payload["total_entries"] >= 13
    values = {row["value"] for row in payload["results"]}
    assert "damping_ratio" in values
    assert "diel_amplitude_protein_log2" in values

@pytest.mark.kg
async def test_value_kind_returns_three_kinds(self, client):
    r = await client.call_tool("list_filter_values", {"filter_type": "value_kind"})
    payload = r.structured_content
    values = {row["value"] for row in payload["results"]}
    assert values == {"numeric", "boolean", "categorical"}

@pytest.mark.kg
async def test_compartment_returns_baseline(self, client):
    r = await client.call_tool("list_filter_values", {"filter_type": "compartment"})
    payload = r.structured_content
    values = {row["value"] for row in payload["results"]}
    assert "whole_cell" in values
    assert "vesicle" in values
```

- [ ] **Step 12: Run integration tests**

```bash
pytest tests/integration/test_mcp_tools.py::TestListFilterValues -m kg -v
```
Expected: all pass.

- [ ] **Step 13: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py multiomics_explorer/api/functions.py multiomics_explorer/mcp_server/tools.py tests/unit/test_query_builders.py tests/unit/test_api_functions.py tests/unit/test_tool_wrappers.py tests/integration/test_mcp_tools.py
git commit -m "feat(filter-values): add metric_type / value_kind / compartment filter types

Slice-2 entry point for DM-tool param discovery. Three new filter types
sourced from DerivedMetric (metric_type, value_kind) and Experiment
(compartment, per D7).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `list_organisms` — DM rollups + compartment filter + 3 envelope keys

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:935-1000` (`build_list_organisms` + `build_list_organisms_summary`)
- Modify: `multiomics_explorer/api/functions.py:570-680` (`list_organisms`)
- Modify: `multiomics_explorer/mcp_server/tools.py` (Pydantic `ListOrganismsResult` / `ListOrganismsResponse`, `compartment` param)
- Modify: 3 test files

- [ ] **Step 1: Write failing builder test**

In `tests/unit/test_query_builders.py`, extend `TestBuildListOrganisms`:

```python
def test_compact_returns_dm_rollup_fields(self):
    from multiomics_explorer.kg.queries_lib import build_list_organisms
    cypher, _ = build_list_organisms()
    assert "coalesce(o.derived_metric_count, 0) AS derived_metric_count" in cypher
    assert "coalesce(o.derived_metric_value_kinds, []) AS derived_metric_value_kinds" in cypher
    assert "coalesce(o.compartments, []) AS compartments" in cypher

def test_verbose_adds_dm_extras(self):
    from multiomics_explorer.kg.queries_lib import build_list_organisms
    cypher, _ = build_list_organisms(verbose=True)
    assert "coalesce(o.derived_metric_gene_count, 0) AS derived_metric_gene_count" in cypher
    assert "coalesce(o.derived_metric_types, []) AS derived_metric_types" in cypher

def test_compartment_filter_param(self):
    from multiomics_explorer.kg.queries_lib import build_list_organisms
    cypher, params = build_list_organisms(compartment="vesicle")
    assert "$compartment IN o.compartments" in cypher
    assert params["compartment"] == "vesicle"
```

- [ ] **Step 2: Run test to verify failure**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListOrganisms -v
```
Expected: 3 new tests fail.

- [ ] **Step 3: Update `build_list_organisms`**

In `multiomics_explorer/kg/queries_lib.py:935-991`, replace the function with:

```python
def build_list_organisms(
    *,
    organism_names_lc: list[str] | None = None,
    compartment: str | None = None,
    verbose: bool = False,
) -> tuple[str, dict]:
    """Build Cypher for listing organisms with data-availability signals.

    organism_names_lc: optional list of lowercased preferred_names. When
        None, returns all organisms. When non-None, restricts to organisms
        whose preferred_name (lowercased) is in the list.
    compartment: optional Experiment.compartment value (e.g. 'vesicle')
        to restrict to organisms whose compartments list includes it.

    RETURN keys (compact): organism_name, organism_type, genus, species,
    strain, clade, ncbi_taxon_id, gene_count, publication_count,
    experiment_count, treatment_types, background_factors, omics_types,
    clustering_analysis_count, cluster_types, derived_metric_count,
    derived_metric_value_kinds, compartments, reference_database,
    reference_proteome, growth_phases.
    RETURN keys (verbose): adds family, order, tax_class, phylum, kingdom,
    superkingdom, lineage, cluster_count, derived_metric_gene_count,
    derived_metric_types.
    """
    verbose_cols = (
        ",\n       o.family AS family,"
        "\n       o.order AS order,"
        "\n       o.tax_class AS tax_class,"
        "\n       o.phylum AS phylum,"
        "\n       o.kingdom AS kingdom,"
        "\n       o.superkingdom AS superkingdom,"
        "\n       o.lineage AS lineage,"
        "\n       coalesce(o.cluster_count, 0) AS cluster_count,"
        "\n       coalesce(o.derived_metric_gene_count, 0) AS derived_metric_gene_count,"
        "\n       coalesce(o.derived_metric_types, []) AS derived_metric_types"
        if verbose else ""
    )

    conditions = [
        "($organism_names_lc IS NULL"
        " OR toLower(o.preferred_name) IN $organism_names_lc)"
    ]
    params: dict = {"organism_names_lc": organism_names_lc}
    if compartment is not None:
        conditions.append("$compartment IN coalesce(o.compartments, [])")
        params["compartment"] = compartment

    where_block = "WHERE " + "\n  AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        f"{where_block}"
        "RETURN o.preferred_name AS organism_name,\n"
        "       o.organism_type AS organism_type,\n"
        "       o.genus AS genus,\n"
        "       o.species AS species,\n"
        "       o.strain_name AS strain,\n"
        "       o.clade AS clade,\n"
        "       o.ncbi_taxon_id AS ncbi_taxon_id,\n"
        "       o.gene_count AS gene_count,\n"
        "       o.publication_count AS publication_count,\n"
        "       o.experiment_count AS experiment_count,\n"
        "       o.treatment_types AS treatment_types,\n"
        "       coalesce(o.background_factors, []) AS background_factors,\n"
        "       o.omics_types AS omics_types,\n"
        "       coalesce(o.clustering_analysis_count, 0) AS clustering_analysis_count,\n"
        "       coalesce(o.cluster_types, []) AS cluster_types,\n"
        "       coalesce(o.derived_metric_count, 0) AS derived_metric_count,\n"
        "       coalesce(o.derived_metric_value_kinds, []) AS derived_metric_value_kinds,\n"
        "       coalesce(o.compartments, []) AS compartments,\n"
        "       o.reference_database AS reference_database,\n"
        "       o.reference_proteome AS reference_proteome,\n"
        "       coalesce(o.growth_phases, []) AS growth_phases"
        f"{verbose_cols}\n"
        "ORDER BY o.genus, o.preferred_name"
    )
    return cypher, params
```

- [ ] **Step 4: Update `build_list_organisms_summary`**

Replace lines 994-1000 with a summary builder that computes the 3 new envelope rollups:

```python
def build_list_organisms_summary(
    *,
    organism_names_lc: list[str] | None = None,
    compartment: str | None = None,
) -> tuple[str, dict]:
    """Summary count + DM/compartment rollups across matched organisms.

    RETURN keys: total_entries, total_matching, by_value_kind,
    by_metric_type, by_compartment.
    """
    conditions = [
        "($organism_names_lc IS NULL"
        " OR toLower(o.preferred_name) IN $organism_names_lc)"
    ]
    params: dict = {"organism_names_lc": organism_names_lc}
    if compartment is not None:
        conditions.append("$compartment IN coalesce(o.compartments, [])")
        params["compartment"] = compartment
    where_block = "WHERE " + "\n  AND ".join(conditions) + "\n"

    cypher = (
        "MATCH (o:OrganismTaxon)\n"
        "WITH count(o) AS total_entries\n"
        "OPTIONAL MATCH (o:OrganismTaxon)\n"
        f"{where_block}"
        "WITH total_entries,\n"
        "     count(o) AS total_matching,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(o.derived_metric_value_kinds, []))) AS vks,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(o.derived_metric_types, []))) AS mtypes,\n"
        "     apoc.coll.flatten(\n"
        "       collect(coalesce(o.compartments, []))) AS comps\n"
        "RETURN total_entries, total_matching,\n"
        "       apoc.coll.frequencies(vks) AS by_value_kind,\n"
        "       apoc.coll.frequencies(mtypes) AS by_metric_type,\n"
        "       apoc.coll.frequencies(comps) AS by_compartment"
    )
    return cypher, params
```

- [ ] **Step 5: Run builder tests to verify pass**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListOrganisms -v
```
Expected: all pass.

- [ ] **Step 6: Write failing API test**

In `tests/unit/test_api_functions.py`, extend `TestListOrganisms` with envelope and compartment-param assertions:

```python
def test_envelope_carries_dm_rollups(self, mock_conn):
    detail_rows = [{
        "organism_name": "Prochlorococcus marinus MED4",
        "organism_type": "marine_cyanobacterium",
        "genus": "Prochlorococcus", "species": "marinus", "strain": "MED4",
        "clade": "HLII", "ncbi_taxon_id": "59919",
        "gene_count": 1900, "publication_count": 4, "experiment_count": 12,
        "treatment_types": ["light_dark_cycle"], "background_factors": [],
        "omics_types": ["RNASEQ", "PROTEOMICS"],
        "clustering_analysis_count": 2, "cluster_types": ["coexpression"],
        "derived_metric_count": 7,
        "derived_metric_value_kinds": ["numeric", "boolean"],
        "compartments": ["whole_cell"],
        "reference_database": None, "reference_proteome": None,
        "growth_phases": [],
    }]
    summary_row = {
        "total_entries": 30, "total_matching": 1,
        "by_value_kind": {"numeric": 6, "boolean": 1},
        "by_metric_type": {"damping_ratio": 1},
        "by_compartment": {"whole_cell": 1},
    }
    mock_conn.execute_query.side_effect = [[summary_row], detail_rows]
    result = list_organisms(conn=mock_conn)
    assert result["by_value_kind"] == [
        {"value_kind": "numeric", "count": 6},
        {"value_kind": "boolean", "count": 1},
    ] or result["by_value_kind"][0]["value_kind"] in {"numeric", "boolean"}
    assert result["results"][0]["derived_metric_count"] == 7
    assert result["results"][0]["compartments"] == ["whole_cell"]

def test_compartment_filter_param_passes_through(self, mock_conn):
    mock_conn.execute_query.side_effect = [
        [{"total_entries": 30, "total_matching": 0,
          "by_value_kind": {}, "by_metric_type": {}, "by_compartment": {}}],
        [],
    ]
    list_organisms(compartment="vesicle", conn=mock_conn)
    # both summary + detail builders called with compartment param
    calls = mock_conn.execute_query.call_args_list
    assert any(c.kwargs.get("compartment") == "vesicle" for c in calls)
```

- [ ] **Step 7: Run API test to verify failure**

```bash
pytest tests/unit/test_api_functions.py::TestListOrganisms -v -k "envelope_carries_dm or compartment_filter"
```
Expected: FAIL.

- [ ] **Step 8: Update `list_organisms` API function**

Find `list_organisms` in `multiomics_explorer/api/functions.py:570`. Add `compartment` param, plumb to both builders, surface 3 new envelope keys, ensure new per-row fields appear unmodified in `results`.

```python
def list_organisms(
    organism_names: list[str] | None = None,
    compartment: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List organisms in the knowledge graph, optionally filtered by name or compartment.

    organism_names: when provided, restricts to organisms whose preferred_name
        matches (case-insensitive). Unknown names returned in `not_found`.
    compartment: when provided, restricts to organisms with at least one
        experiment in that wet-lab compartment ('whole_cell', 'vesicle',
        'exoproteome', 'spent_medium', 'lysate').
    summary: when True, sets limit=0 internally — results=[], summary fields only.

    Returns dict with keys: total_entries, total_matching, returned, offset,
    truncated, by_cluster_type, by_organism_type, by_value_kind, by_metric_type,
    by_compartment, not_found, results.
    Per result (compact): organism_name, organism_type, genus, species,
    strain, clade, ncbi_taxon_id, gene_count, publication_count,
    experiment_count, treatment_types, omics_types, clustering_analysis_count,
    cluster_types, derived_metric_count, derived_metric_value_kinds, compartments.
    Sparse fields (omitted when null): reference_database, reference_proteome.
    When verbose=True, also includes: family, order, tax_class, phylum, kingdom,
    superkingdom, lineage, cluster_count, derived_metric_gene_count,
    derived_metric_types.
    """
    conn = _default_conn(conn)
    if summary:
        limit = 0

    names_lc = [n.lower() for n in organism_names] if organism_names else None

    summary_cypher, summary_params = build_list_organisms_summary(
        organism_names_lc=names_lc, compartment=compartment,
    )
    summary_row = conn.execute_query(summary_cypher, **summary_params)[0]

    if limit == 0:
        results = []
    else:
        detail_cypher, detail_params = build_list_organisms(
            organism_names_lc=names_lc, compartment=compartment, verbose=verbose,
        )
        rows = conn.execute_query(detail_cypher, **detail_params)
        if offset:
            rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        # gate verbose-only fields off of compact responses
        if not verbose:
            results = [{k: v for k, v in r.items()
                        if k not in ("family", "order", "tax_class", "phylum",
                                     "kingdom", "superkingdom", "lineage",
                                     "cluster_count", "derived_metric_gene_count",
                                     "derived_metric_types")}
                       for r in rows]
        else:
            results = list(rows)
        # drop sparse nulls (existing behavior preserved)
        for r in results:
            if r.get("reference_database") is None:
                r.pop("reference_database", None)
            if r.get("reference_proteome") is None:
                r.pop("reference_proteome", None)

    # not_found from organism_names echo (existing behavior)
    not_found = []
    if organism_names:
        present_lc = {r["organism_name"].lower() for r in results} if not summary else set()
        # If summary, do a separate light query for present names (existing
        # behavior — keep as-is; refactor out of scope here).
        # Existing code path in this file handles this; keep it.
        ...  # (preserve existing not_found computation — see current impl ~lines 624-650)

    # Existing organism-type counts (preserve)
    ...  # (preserve existing by_organism_type computation)

    return {
        "total_entries": summary_row["total_entries"],
        "total_matching": summary_row["total_matching"],
        "returned": len(results),
        "offset": offset,
        "truncated": (limit is not None
                      and summary_row["total_matching"] > len(results)),
        "by_organism_type": ...,  # preserve
        "by_cluster_type": _rename_freq(summary_row.get("by_cluster_type", {}),
                                        "cluster_type"),
        "by_value_kind": _rename_freq(summary_row.get("by_value_kind", {}),
                                      "value_kind"),
        "by_metric_type": _rename_freq(summary_row.get("by_metric_type", {}),
                                       "metric_type"),
        "by_compartment": _rename_freq(summary_row.get("by_compartment", {}),
                                       "compartment"),
        "not_found": not_found,
        "results": results,
    }
```

**Note:** This step preserves existing computations (`by_organism_type`, `by_cluster_type`, `not_found`). The actual edit replaces the existing function in-place. Use `Read` first to capture the exact current implementation, then edit so existing assertions stay green. The skeleton above shows the new pieces only.

- [ ] **Step 9: Run API tests, fix any other failures**

```bash
pytest tests/unit/test_api_functions.py::TestListOrganisms -v
```
Expected: all pass (existing + new).

- [ ] **Step 10: Extend Pydantic models in MCP wrapper**

In `multiomics_explorer/mcp_server/tools.py`, find the `list_organisms` wrapper and the `ListOrganismsResult` / `ListOrganismsResponse` models. Add fields:

On `ListOrganismsResult`:
```python
derived_metric_count: int = Field(
    default=0,
    description="Total DerivedMetric annotations on this organism's experiments (0 when none).",
)
derived_metric_value_kinds: list[str] = Field(
    default_factory=list,
    description="Subset of {numeric, boolean, categorical} present across this organism's DMs. Use to route to genes_by_{numeric,boolean,categorical}_metric.",
)
compartments: list[str] = Field(
    default_factory=list,
    description="Wet-lab compartments measured for this organism (e.g. ['whole_cell', 'vesicle']).",
)
# Verbose-only
derived_metric_gene_count: int | None = Field(
    default=None,
    description="Total gene-level DM annotation count (verbose-only).",
)
derived_metric_types: list[str] | None = Field(
    default=None,
    description="Distinct metric_type tags observed (verbose-only).",
)
```

On `ListOrganismsResponse`:
```python
by_value_kind: list[dict] = Field(
    default_factory=list,
    description="DM value_kind frequency rollup across matched organisms.",
)
by_metric_type: list[dict] = Field(
    default_factory=list,
    description="DM metric_type frequency rollup.",
)
by_compartment: list[dict] = Field(
    default_factory=list,
    description="Wet-lab compartment frequency rollup.",
)
```

Add `compartment` param to the `list_organisms` wrapper signature:

```python
compartment: Annotated[
    str | None,
    Field(description="Filter to organisms with at least one experiment in this wet-lab compartment."),
] = None,
```

Pass through to `api.list_organisms(...)`.

- [ ] **Step 11: Run MCP wrapper tests**

```bash
pytest tests/unit/test_tool_wrappers.py -v -k "ListOrganisms"
```
Expected: pass.

- [ ] **Step 12: Add live-KG integration assertions**

In `tests/integration/test_mcp_tools.py`, extend `TestListOrganisms`:

```python
@pytest.mark.kg
async def test_envelope_dm_rollups_present(self, client):
    r = await client.call_tool("list_organisms", {"summary": True})
    payload = r.structured_content
    for key in ("by_value_kind", "by_metric_type", "by_compartment"):
        assert key in payload
        assert isinstance(payload[key], list)

@pytest.mark.kg
async def test_compartment_filter_narrows(self, client):
    r_all = await client.call_tool("list_organisms", {"summary": True})
    r_vesicle = await client.call_tool("list_organisms",
                                       {"compartment": "vesicle", "summary": True})
    assert r_vesicle.structured_content["total_matching"] <= r_all.structured_content["total_matching"]

@pytest.mark.kg
async def test_per_row_dm_count_present(self, client):
    r = await client.call_tool("list_organisms", {"limit": 5})
    rows = r.structured_content["results"]
    for row in rows:
        assert "derived_metric_count" in row
        assert "derived_metric_value_kinds" in row
        assert "compartments" in row
```

- [ ] **Step 13: Run integration tests**

```bash
pytest tests/integration/test_mcp_tools.py::TestListOrganisms -m kg -v
```
Expected: all pass.

- [ ] **Step 14: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py multiomics_explorer/api/functions.py multiomics_explorer/mcp_server/tools.py tests/unit/test_query_builders.py tests/unit/test_api_functions.py tests/unit/test_tool_wrappers.py tests/integration/test_mcp_tools.py
git commit -m "feat(list-organisms): surface DerivedMetric rollups + compartment filter

- Per-row compact: derived_metric_count, derived_metric_value_kinds, compartments
- Per-row verbose: derived_metric_gene_count, derived_metric_types
- New compartment filter param (sources from OrganismTaxon.compartments)
- Envelope: by_value_kind, by_metric_type, by_compartment

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `list_publications` — DM rollups + compartment filter + 3 envelope keys

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:760-892` (`build_list_publications` + `build_list_publications_summary` + `_list_publications_where`)
- Modify: `multiomics_explorer/api/functions.py:686-810` (`list_publications`)
- Modify: `multiomics_explorer/mcp_server/tools.py` (Pydantic models + wrapper)
- Modify: 3 test files

The structure mirrors Task 2 step-for-step. Differences:

- Source field: `Publication.compartments` (list, same as OrganismTaxon).
- Filter clause: `$compartment IN coalesce(p.compartments, [])` — same shape as organisms.
- WHERE builder lives in `_list_publications_where`; add the `compartment` branch there.

- [ ] **Step 1: Write failing builder tests**

In `tests/unit/test_query_builders.py`, extend `TestBuildListPublications`:

```python
def test_compact_returns_dm_rollup_fields(self):
    from multiomics_explorer.kg.queries_lib import build_list_publications
    cypher, _ = build_list_publications()
    assert "coalesce(p.derived_metric_count, 0) AS derived_metric_count" in cypher
    assert "coalesce(p.derived_metric_value_kinds, []) AS derived_metric_value_kinds" in cypher
    assert "coalesce(p.compartments, []) AS compartments" in cypher

def test_verbose_adds_dm_extras(self):
    from multiomics_explorer.kg.queries_lib import build_list_publications
    cypher, _ = build_list_publications(verbose=True)
    assert "coalesce(p.derived_metric_gene_count, 0) AS derived_metric_gene_count" in cypher
    assert "coalesce(p.derived_metric_types, []) AS derived_metric_types" in cypher

def test_compartment_filter_in_where(self):
    from multiomics_explorer.kg.queries_lib import build_list_publications
    cypher, params = build_list_publications(compartment="vesicle")
    assert "$compartment IN coalesce(p.compartments, [])" in cypher
    assert params["compartment"] == "vesicle"
```

- [ ] **Step 2: Run test to verify failure**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListPublications -v
```

- [ ] **Step 3: Update `_list_publications_where`**

In `multiomics_explorer/kg/queries_lib.py:740-758`, locate `_list_publications_where`. Add a `compartment` keyword param and append to conditions:

```python
def _list_publications_where(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    background_factors: str | None = None,
    growth_phases: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    publication_dois: list[str] | None = None,
    compartment: str | None = None,   # <-- NEW
) -> tuple[str, dict]:
    """... preserve existing docstring ..."""
    conditions: list[str] = []
    params: dict = {}

    # ... preserve existing conditions ...

    if compartment is not None:
        conditions.append("$compartment IN coalesce(p.compartments, [])")
        params["compartment"] = compartment

    where_block = "WHERE " + "\n  AND ".join(conditions) + "\n" if conditions else ""
    return where_block, params
```

- [ ] **Step 4: Update `build_list_publications`**

Add `compartment` keyword param, plumb to `_list_publications_where`, add the 3 compact RETURN columns + verbose extras (mirror Task 2 Step 3).

```python
def build_list_publications(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    background_factors: str | None = None,
    growth_phases: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    publication_dois: list[str] | None = None,
    compartment: str | None = None,   # NEW
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """... extend docstring with new fields + compartment param ..."""
    where_block, params = _list_publications_where(
        organism=organism, treatment_type=treatment_type,
        background_factors=background_factors, growth_phases=growth_phases,
        search_text=search_text, author=author,
        publication_dois=publication_dois, compartment=compartment,
    )

    verbose_cols = (
        ",\n       p.abstract AS abstract, p.description AS description,"
        "\n       p.cluster_count AS cluster_count,"
        "\n       coalesce(p.derived_metric_gene_count, 0) AS derived_metric_gene_count,"
        "\n       coalesce(p.derived_metric_types, []) AS derived_metric_types"
        if verbose else ""
    )
    # ... rest preserves existing structure but the RETURN block adds:
    #     coalesce(p.derived_metric_count, 0) AS derived_metric_count,
    #     coalesce(p.derived_metric_value_kinds, []) AS derived_metric_value_kinds,
    #     coalesce(p.compartments, []) AS compartments,
    # ... immediately after the existing clustering_analysis_count line.
```

Apply this pattern to **both** the search-text branch (line ~801) and the non-search branch (line ~824) — keep them in sync.

- [ ] **Step 5: Update `build_list_publications_summary`**

Add the 3 envelope rollups (mirror Task 2 Step 4 pattern):

```python
def build_list_publications_summary(
    *,
    # ... preserve existing params ...
    compartment: str | None = None,
) -> tuple[str, dict]:
    where_block, params = _list_publications_where(
        # ... preserve existing args ...
        compartment=compartment,
    )

    # Existing: total_entries / total_matching / clustering_analysis_count rollup.
    # NEW: also collect dm fields and emit by_value_kind / by_metric_type / by_compartment.
    # Pattern matches list_experiments_summary pre-existing code (lines ~1241-1264).

    # Schema-wise, the summary needs to project p_for_summary nodes' fields.
    # Add to the WITH clause:
    #     apoc.coll.flatten(collect(coalesce(p.derived_metric_value_kinds, []))) AS vks,
    #     apoc.coll.flatten(collect(coalesce(p.derived_metric_types, []))) AS mtypes,
    #     apoc.coll.flatten(collect(coalesce(p.compartments, []))) AS comps
    # And to RETURN:
    #     apoc.coll.frequencies(vks) AS by_value_kind,
    #     apoc.coll.frequencies(mtypes) AS by_metric_type,
    #     apoc.coll.frequencies(comps) AS by_compartment
```

The current summary builder uses an `OPTIONAL MATCH` pattern (queries_lib.py:885-891) — extend the matching variant for both the search-text and non-search paths.

- [ ] **Step 6: Run builder tests**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListPublications -v
```

- [ ] **Step 7: Update API + MCP layers**

Mirror Task 2 Steps 6–11:

- API: extend `list_publications` signature with `compartment: str | None = None`, plumb to both builders, surface 3 envelope keys via `_rename_freq` helper, expand docstring.
- MCP: extend `ListPublicationsResult` (compact + verbose fields) and `ListPublicationsResponse` (3 envelope keys), add `compartment` Annotated param.

- [ ] **Step 8: Add live-KG integration assertions**

In `tests/integration/test_mcp_tools.py`, extend `TestListPublications`:

```python
@pytest.mark.kg
async def test_dm_rollups_present(self, client):
    r = await client.call_tool("list_publications", {"summary": True})
    p = r.structured_content
    assert "by_value_kind" in p and "by_metric_type" in p and "by_compartment" in p

@pytest.mark.kg
async def test_compartment_filter_narrows(self, client):
    r_all = await client.call_tool("list_publications", {"summary": True})
    r_v = await client.call_tool("list_publications", {"compartment": "vesicle", "summary": True})
    assert r_v.structured_content["total_matching"] <= r_all.structured_content["total_matching"]
```

- [ ] **Step 9: Run all tests**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListPublications tests/unit/test_api_functions.py::TestListPublications tests/unit/test_tool_wrappers.py -v -k "Publications"
pytest tests/integration/test_mcp_tools.py::TestListPublications -m kg -v
```

- [ ] **Step 10: Commit**

```bash
git add multiomics_explorer/ tests/
git commit -m "feat(list-publications): surface DerivedMetric rollups + compartment filter

Same shape as list_organisms (Task 2). compartments rollup is a list on
Publication; filter uses '\$compartment IN coalesce(p.compartments, [])'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `list_experiments` — DM rollups + compartment filter + 3 envelope keys

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:1003-1300` (`_list_experiments_where`, `build_list_experiments`, `build_list_experiments_summary`)
- Modify: `multiomics_explorer/api/functions.py:826-960` (`list_experiments`)
- Modify: `multiomics_explorer/mcp_server/tools.py` (Pydantic models + wrapper)
- Modify: 3 test files

`list_experiments` differs from publications/organisms because `compartment` on Experiment is a **scalar** (not a list). Filter clause is `e.compartment = $compartment`.

- [ ] **Step 1: Write failing builder tests**

In `tests/unit/test_query_builders.py`, extend `TestBuildListExperiments`:

```python
def test_compact_returns_dm_rollup_fields_and_compartment_scalar(self):
    from multiomics_explorer.kg.queries_lib import build_list_experiments
    cypher, _ = build_list_experiments()
    assert "coalesce(e.derived_metric_count, 0) AS derived_metric_count" in cypher
    assert "coalesce(e.derived_metric_value_kinds, []) AS derived_metric_value_kinds" in cypher
    assert "e.compartment AS compartment" in cypher  # scalar, not list

def test_verbose_adds_dm_extras(self):
    from multiomics_explorer.kg.queries_lib import build_list_experiments
    cypher, _ = build_list_experiments(verbose=True)
    assert "coalesce(e.derived_metric_gene_count, 0) AS derived_metric_gene_count" in cypher
    assert "coalesce(e.derived_metric_types, []) AS derived_metric_types" in cypher
    assert "coalesce(e.reports_derived_metric_types, []) AS reports_derived_metric_types" in cypher

def test_compartment_filter_uses_scalar_eq(self):
    from multiomics_explorer.kg.queries_lib import build_list_experiments
    cypher, params = build_list_experiments(compartment="vesicle")
    assert "e.compartment = $compartment" in cypher
    assert params["compartment"] == "vesicle"
```

- [ ] **Step 2: Run test to verify failure**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListExperiments -v
```

- [ ] **Step 3: Update `_list_experiments_where`**

In `multiomics_explorer/kg/queries_lib.py:1003`, add `compartment` to the keyword params and append to conditions:

```python
def _list_experiments_where(
    *,
    # ... preserve existing params ...
    compartment: str | None = None,    # NEW
) -> tuple[str, dict]:
    # ... preserve existing logic, then append:
    if compartment is not None:
        conditions.append("e.compartment = $compartment")
        params["compartment"] = compartment
    # ... return as before
```

- [ ] **Step 4: Update `build_list_experiments`**

In `build_list_experiments` (line ~1114), add `compartment: str | None = None` to keyword params; plumb to `_list_experiments_where`; add the 3 compact + 3 verbose RETURN columns near the existing clustering_analysis_count emission (line ~1178):

```python
# Compact additions in RETURN:
#       coalesce(e.derived_metric_count, 0) AS derived_metric_count,
#       coalesce(e.derived_metric_value_kinds, []) AS derived_metric_value_kinds,
#       e.compartment AS compartment,
# Verbose additions in verbose_cols string:
#     "\n       coalesce(e.derived_metric_gene_count, 0) AS derived_metric_gene_count,"
#     "\n       coalesce(e.derived_metric_types, []) AS derived_metric_types,"
#     "\n       coalesce(e.reports_derived_metric_types, []) AS reports_derived_metric_types"
```

- [ ] **Step 5: Update `build_list_experiments_summary`**

Add `compartment` keyword param; plumb to `_list_experiments_where`. Extend the existing `collect_cols` block (line ~1241) and `return_cols` block (line ~1253) with:

```python
# In collect_cols (after the existing scopes/ctypes lines):
"     apoc.coll.flatten(collect(coalesce(e.derived_metric_value_kinds, []))) AS vks,\n"
"     apoc.coll.flatten(collect(coalesce(e.derived_metric_types, []))) AS mtypes,\n"
"     collect(e.compartment) AS comps"

# In return_cols:
",\n       apoc.coll.frequencies(vks) AS by_value_kind,\n"
"       apoc.coll.frequencies(mtypes) AS by_metric_type,\n"
"       apoc.coll.frequencies(comps) AS by_compartment"
```

- [ ] **Step 6: Run builder tests**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListExperiments -v
```

- [ ] **Step 7: Update API + MCP layers**

Mirror Task 2 / Task 3:

- API (`list_experiments`): add `compartment: str | None = None` param, plumb to both builders, surface 3 envelope keys via `_rename_freq`, expand docstring.
- MCP: extend `ListExperimentsResult` + `ListExperimentsResponse` Pydantic models (compact + verbose + envelope additions), add `compartment` Annotated param.

- [ ] **Step 8: Add live-KG integration assertions**

```python
@pytest.mark.kg
async def test_dm_rollups_in_experiment_envelope(self, client):
    r = await client.call_tool("list_experiments", {"summary": True})
    p = r.structured_content
    assert "by_value_kind" in p and "by_metric_type" in p and "by_compartment" in p

@pytest.mark.kg
async def test_compartment_vesicle_returns_5(self, client):
    r = await client.call_tool("list_experiments",
                               {"compartment": "vesicle", "summary": True})
    # 2026-04-27 baseline
    assert r.structured_content["total_matching"] == 5

@pytest.mark.kg
async def test_compartment_exoproteome_returns_7(self, client):
    r = await client.call_tool("list_experiments",
                               {"compartment": "exoproteome", "summary": True})
    assert r.structured_content["total_matching"] == 7

@pytest.mark.kg
async def test_per_row_compartment_field(self, client):
    r = await client.call_tool("list_experiments", {"limit": 5})
    for row in r.structured_content["results"]:
        assert "compartment" in row
        assert row["compartment"] in {"whole_cell", "vesicle", "exoproteome"}
```

- [ ] **Step 9: Run all tests**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListExperiments tests/unit/test_api_functions.py::TestListExperiments tests/unit/test_tool_wrappers.py -v -k "Experiments"
pytest tests/integration/test_mcp_tools.py::TestListExperiments -m kg -v
```

- [ ] **Step 10: Commit**

```bash
git add multiomics_explorer/ tests/
git commit -m "feat(list-experiments): surface DerivedMetric rollups + compartment filter

Compartment is a scalar on Experiment (not list); filter uses
'e.compartment = \$compartment'. Pinned baselines: vesicle=5,
exoproteome=7 experiments (2026-04-27).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `gene_overview` — full DM rollup (compact + verbose + envelope)

**KG-rebuild status:** unblocked. KG D8 rename verified live 2026-04-27: Gene now exposes `boolean_metric_count` / `categorical_metric_count` / `boolean_metric_types_observed` / `categorical_metric_types_observed`. This task absorbs the original plan's Task 6 (verbose per-kind fields + post-D8 names) since gating is gone.

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:404-470` (`build_gene_overview`)
- Modify: `multiomics_explorer/api/functions.py:300-360` (`gene_overview`)
- Modify: `multiomics_explorer/mcp_server/tools.py` (Pydantic models + envelope)
- Modify: 3 test files

- [ ] **Step 1: Write failing builder test**

```python
class TestBuildGeneOverview:
    def test_compact_returns_dm_rollup_synthesized(self):
        from multiomics_explorer.kg.queries_lib import build_gene_overview
        cypher, _ = build_gene_overview()
        # Compact RETURN must source per-kind counts so api/ can synthesize total + value_kinds
        assert "coalesce(g.numeric_metric_count, 0) AS numeric_metric_count" in cypher
        # Other per-kind fields come in via verbose pass-through OR via the api layer
        # (see Task 6 for the verbose pieces post-rename).

    def test_envelope_has_derived_metrics_aggregation_in_summary(self):
        # The summary builder must expose the count of genes with >0 DMs.
        from multiomics_explorer.kg.queries_lib import build_gene_overview_summary
        cypher, _ = build_gene_overview_summary(locus_tags=["PMM0001"])
        assert "has_derived_metrics" in cypher  # see Step 4 for exact pattern
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/unit/test_query_builders.py::TestBuildGeneOverview -v
```

- [ ] **Step 3: Extend `build_gene_overview`**

In `multiomics_explorer/kg/queries_lib.py`, find `build_gene_overview` (line ~417). The existing builder returns `cluster_membership_count` / `cluster_types` per row. Add compact-side per-kind sources so the API can synthesize the unified count, plus verbose-only per-kind types lists + compartments:

```python
# In the RETURN clause, after the existing cluster_types line, add (compact):
"       coalesce(g.numeric_metric_count, 0) AS numeric_metric_count,\n"
"       coalesce(g.boolean_metric_count, 0) AS boolean_metric_count,\n"
"       coalesce(g.categorical_metric_count, 0) AS categorical_metric_count,\n"

# In the verbose_cols string (verbose-only):
"\n       coalesce(g.numeric_metric_types_observed, []) AS numeric_metric_types_observed,"
"\n       coalesce(g.boolean_metric_types_observed, []) AS boolean_metric_types_observed,"
"\n       coalesce(g.categorical_metric_types_observed, []) AS categorical_metric_types_observed,"
"\n       coalesce(g.compartments_observed, []) AS compartments_observed"
```

Use post-D8 KG names directly (verified live 2026-04-27).

- [ ] **Step 4: Update `build_gene_overview_summary`**

The existing summary returns `has_clusters: int` (count of locus_tags with cluster_membership_count > 0). Add `has_derived_metrics`:

```python
# Replace the existing has_clusters expression (around line 404):
"       size([g IN found WHERE g.cluster_membership_count > 0]) AS has_clusters,\n"
"       size([g IN found WHERE\n"
"           coalesce(g.numeric_metric_count, 0)\n"
"         + coalesce(g.boolean_metric_count, 0)\n"
"         + coalesce(g.categorical_metric_count, 0) > 0]) AS has_derived_metrics,\n"
```

- [ ] **Step 5: Run builder tests**

```bash
pytest tests/unit/test_query_builders.py::TestBuildGeneOverview -v
```

- [ ] **Step 6: Write failing API test**

In `tests/unit/test_api_functions.py`, extend `TestGeneOverview`:

```python
def test_synthesizes_dm_count_and_value_kinds(self, mock_conn):
    """Compact derived_metric_count = sum of per-kind; value_kinds = which kinds > 0."""
    detail_rows = [{
        "locus_tag": "PMM0001", "gene_name": "rbcL",
        "cluster_membership_count": 0, "cluster_types": [],
        "numeric_metric_count": 5,
        "boolean_metric_count": 3,
        "categorical_metric_count": 0,
    }]
    summary_row = {
        "total_matching": 1, "found_count": 1,
        "has_clusters": 0, "has_derived_metrics": 1,
    }
    mock_conn.execute_query.side_effect = [[summary_row], detail_rows]
    result = gene_overview(locus_tags=["PMM0001"], conn=mock_conn)
    assert result["has_derived_metrics"] == 1
    row = result["results"][0]
    assert row["derived_metric_count"] == 8
    assert set(row["derived_metric_value_kinds"]) == {"numeric", "boolean"}

def test_zero_dm_gene_has_empty_value_kinds(self, mock_conn):
    detail_rows = [{
        "locus_tag": "PMM9999", "gene_name": "x",
        "cluster_membership_count": 0, "cluster_types": [],
        "numeric_metric_count": 0,
        "boolean_metric_count": 0,
        "categorical_metric_count": 0,
    }]
    summary_row = {"total_matching": 1, "found_count": 1,
                   "has_clusters": 0, "has_derived_metrics": 0}
    mock_conn.execute_query.side_effect = [[summary_row], detail_rows]
    result = gene_overview(locus_tags=["PMM9999"], conn=mock_conn)
    assert result["results"][0]["derived_metric_count"] == 0
    assert result["results"][0]["derived_metric_value_kinds"] == []
```

- [ ] **Step 7: Run API test to verify failure**

```bash
pytest tests/unit/test_api_functions.py::TestGeneOverview -v -k "synthesizes or zero_dm"
```

- [ ] **Step 8: Update `gene_overview` API function**

In `multiomics_explorer/api/functions.py`, find `gene_overview`. Synthesize the compact DM fields from the per-kind raw fields, then gate the per-kind fields + types-observed lists + compartments_observed on `verbose`:

```python
# After existing cluster-field handling, before returning:
KIND_FIELD_MAP = [
    ("numeric_metric_count", "numeric"),
    ("boolean_metric_count", "boolean"),
    ("categorical_metric_count", "categorical"),
]
VERBOSE_DM_FIELDS = (
    "numeric_metric_count", "boolean_metric_count", "categorical_metric_count",
    "numeric_metric_types_observed", "boolean_metric_types_observed",
    "categorical_metric_types_observed", "compartments_observed",
)

for r in results:
    # Synthesize unified rollup from per-kind counts (always needed)
    counts = {kind: r.get(field, 0) for field, kind in KIND_FIELD_MAP}
    r["derived_metric_count"] = sum(counts.values())
    r["derived_metric_value_kinds"] = [k for k, v in counts.items() if v > 0]
    if not verbose:
        # Strip per-kind raw fields from compact responses
        for f in VERBOSE_DM_FIELDS:
            r.pop(f, None)

# Surface has_derived_metrics in the envelope:
return {
    # ... existing keys ...
    "has_derived_metrics": raw_summary["has_derived_metrics"],
    # ... rest ...
}
```

- [ ] **Step 9: Run API tests**

```bash
pytest tests/unit/test_api_functions.py::TestGeneOverview -v
```
Expected: pass.

- [ ] **Step 10: Update Pydantic models**

In `multiomics_explorer/mcp_server/tools.py`, find `GeneOverviewResult`. Add compact + verbose fields:

```python
# Compact (always present)
derived_metric_count: int = Field(
    default=0,
    description="Total DerivedMetric annotations on this gene (sum across numeric/boolean/categorical kinds).",
)
derived_metric_value_kinds: list[str] = Field(
    default_factory=list,
    description="Subset of {numeric, boolean, categorical} where this gene has DM annotations. Use to route to genes_by_{kind}_metric drill-downs.",
)

# Verbose-only (None on compact responses)
numeric_metric_count: int | None = Field(default=None, description="Numeric DM count (verbose).")
boolean_metric_count: int | None = Field(default=None, description="Boolean DM count (verbose).")
categorical_metric_count: int | None = Field(default=None, description="Categorical DM count (verbose).")
numeric_metric_types_observed: list[str] | None = Field(default=None, description="Numeric metric_types observed (verbose).")
boolean_metric_types_observed: list[str] | None = Field(default=None, description="Boolean metric_types observed (verbose).")
categorical_metric_types_observed: list[str] | None = Field(default=None, description="Categorical metric_types observed (verbose).")
compartments_observed: list[str] | None = Field(default=None, description="DM compartments observed for this gene (verbose).")
```

On `GeneOverviewResponse`:

```python
has_derived_metrics: int = Field(
    default=0,
    description="Count of requested locus_tags carrying any DM annotation.",
)
```

- [ ] **Step 11: Run MCP wrapper tests**

```bash
pytest tests/unit/test_tool_wrappers.py -v -k "GeneOverview"
```

- [ ] **Step 12: Add live-KG integration assertions**

```python
@pytest.mark.kg
async def test_gene_overview_dm_rollup_for_biller_2018_gene(self, client, biller_2018_gene_id):
    """Pick any Biller 2018 gene with boolean DM annotations."""
    r = await client.call_tool("gene_overview", {"locus_tags": [biller_2018_gene_id]})
    p = r.structured_content
    assert p["has_derived_metrics"] == 1
    row = p["results"][0]
    assert row["derived_metric_count"] > 0
    assert "boolean" in row["derived_metric_value_kinds"]
```

(Capture a known Biller 2018 gene_id via `gene_derived_metrics(...).results[0].locus_tag` once the test suite has a fixture for it; otherwise hardcode against a known locus_tag from the KG.)

- [ ] **Step 13: Run integration test**

```bash
pytest tests/integration/test_mcp_tools.py::TestGeneOverview -m kg -v
```

- [ ] **Step 14: Commit**

```bash
git add multiomics_explorer/ tests/
git commit -m "feat(gene-overview): synthesize compact DM rollup + has_derived_metrics envelope

Compact derived_metric_count = sum of per-kind Gene counts;
derived_metric_value_kinds = kinds where count > 0. Envelope mirrors
existing has_clusters pattern.

Per-kind counts still source from KG-side classifier_flag_count /
classifier_label_count names — Task 6 renames those after the KG rebuild
adopts D8.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: ABSORBED INTO TASK 5

KG D8 rename was verified live before implementation began (2026-04-27 evening), so the original Task 5 / Task 6 split (compact-then-verbose) collapsed into a single Task 5. **Skip this section** — proceed to Task 7 after Task 5 lands.

The original Task 6 content is preserved below for historical reference but should NOT be executed independently.

---

### (Original Task 6 content — historical, do not execute)

**Status:** GATED on KG rebuild adopting D8. Run only after the companion KG spec has landed and verification queries pass.

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (`build_gene_overview`)
- Modify: `multiomics_explorer/api/functions.py` (`gene_overview`)
- Modify: `multiomics_explorer/mcp_server/tools.py` (Pydantic verbose-only fields)
- Modify: 3 test files
- Modify: `tests/regression/test_regression/gene_details_*.yml` (regen via `--force-regen`)

- [ ] **Step 1: Verify D8 rename landed in live KG**

```bash
uv run python -c "
from multiomics_explorer.kg.connection import get_connection
conn = get_connection()
rows = conn.execute_query('MATCH (g:Gene) RETURN keys(g) AS k LIMIT 1')
keys = set(rows[0]['k'])
assert 'boolean_metric_count' in keys, 'D8 not landed yet'
assert 'classifier_flag_count' not in keys, 'legacy keys still present'
print('D8 verified live')
"
```
Expected: prints "D8 verified live". If it fails, halt — KG side hasn't shipped.

- [ ] **Step 2: Update `build_gene_overview` to use renamed fields**

Replace the per-kind RETURN aliases added in Task 5 Step 3:

```python
# Old (Task 5):
"       coalesce(g.numeric_metric_count, 0) AS numeric_metric_count,\n"
"       coalesce(g.classifier_flag_count, 0) AS classifier_flag_count,\n"
"       coalesce(g.classifier_label_count, 0) AS classifier_label_count,\n"

# New (Task 6):
"       coalesce(g.numeric_metric_count, 0) AS numeric_metric_count,\n"
"       coalesce(g.boolean_metric_count, 0) AS boolean_metric_count,\n"
"       coalesce(g.categorical_metric_count, 0) AS categorical_metric_count,\n"
```

Same swap in `build_gene_overview_summary` for the `has_derived_metrics` arithmetic:

```python
"       size([g IN found WHERE\n"
"           coalesce(g.numeric_metric_count, 0)\n"
"         + coalesce(g.boolean_metric_count, 0)\n"
"         + coalesce(g.categorical_metric_count, 0) > 0]) AS has_derived_metrics,\n"
```

Add the verbose-only RETURN extras:

```python
# In the verbose_cols string:
"\n       coalesce(g.numeric_metric_types_observed, []) AS numeric_metric_types_observed,"
"\n       coalesce(g.boolean_metric_types_observed, []) AS boolean_metric_types_observed,"
"\n       coalesce(g.categorical_metric_types_observed, []) AS categorical_metric_types_observed,"
"\n       coalesce(g.compartments_observed, []) AS compartments_observed"
```

- [ ] **Step 3: Update `gene_overview` API**

Update the `KIND_FIELD_MAP` to use the new field names:

```python
KIND_FIELD_MAP = [
    ("numeric_metric_count", "numeric"),
    ("boolean_metric_count", "boolean"),
    ("categorical_metric_count", "categorical"),
]
```

- [ ] **Step 4: Update Pydantic models with verbose fields**

In `mcp_server/tools.py`, add to `GeneOverviewResult`:

```python
# Verbose-only — populated only when verbose=True
numeric_metric_count: int | None = Field(default=None, description="Numeric DM count for this gene (verbose).")
boolean_metric_count: int | None = Field(default=None, description="Boolean DM count for this gene (verbose).")
categorical_metric_count: int | None = Field(default=None, description="Categorical DM count for this gene (verbose).")
numeric_metric_types_observed: list[str] | None = Field(default=None, description="Numeric metric_types observed (verbose).")
boolean_metric_types_observed: list[str] | None = Field(default=None, description="Boolean metric_types observed (verbose).")
categorical_metric_types_observed: list[str] | None = Field(default=None, description="Categorical metric_types observed (verbose).")
compartments_observed: list[str] | None = Field(default=None, description="DM compartments observed for this gene (verbose).")
```

The api/ layer must keep the per-kind counts in the row when `verbose=True`, drop when `verbose=False`. Update the verbose gating in the api/ function.

- [ ] **Step 5: Add unit tests for verbose fields**

```python
def test_verbose_surfaces_per_kind_fields(self, mock_conn):
    detail_rows = [{
        "locus_tag": "PMM0001", "gene_name": "rbcL",
        "cluster_membership_count": 0, "cluster_types": [],
        "numeric_metric_count": 5,
        "boolean_metric_count": 3,
        "categorical_metric_count": 0,
        "numeric_metric_types_observed": ["damping_ratio"],
        "boolean_metric_types_observed": ["periodic_l_d"],
        "categorical_metric_types_observed": [],
        "compartments_observed": ["whole_cell"],
    }]
    summary_row = {"total_matching": 1, "found_count": 1, "has_clusters": 0, "has_derived_metrics": 1}
    mock_conn.execute_query.side_effect = [[summary_row], detail_rows]
    result = gene_overview(locus_tags=["PMM0001"], verbose=True, conn=mock_conn)
    row = result["results"][0]
    assert row["numeric_metric_count"] == 5
    assert row["boolean_metric_count"] == 3
    assert row["compartments_observed"] == ["whole_cell"]
```

- [ ] **Step 6: Run all gene_overview tests**

```bash
pytest tests/unit/test_query_builders.py::TestBuildGeneOverview tests/unit/test_api_functions.py::TestGeneOverview tests/unit/test_tool_wrappers.py -v -k "GeneOverview"
pytest tests/integration/test_mcp_tools.py::TestGeneOverview -m kg -v
```

- [ ] **Step 7: Regenerate `gene_details` regression baselines**

The 3 yml fixtures reference legacy `classifier_*` field names via `gene_details`'s `g{.*}` pass-through. The KG rename automatically changes what they should contain.

```bash
pytest tests/regression/ --force-regen -m kg -v
```

Expected: `tests/regression/test_regression/gene_details_alteromonas.yml`, `gene_details_synechococcus.yml`, `gene_details_flat_return.yml` updated with `boolean_metric_count` / `categorical_metric_count` keys (plus `*_types_observed` + `compartments_observed`).

- [ ] **Step 8: Verify regenerated baselines look right**

```bash
git diff tests/regression/test_regression/gene_details_*.yml | head -50
```

Expected: legacy keys removed, new D8 keys present.

- [ ] **Step 9: Commit**

```bash
git add multiomics_explorer/ tests/
git commit -m "feat(gene-overview): adopt D8 Gene-rename + add verbose per-kind fields

Post-KG-rebuild: classifier_flag_* → boolean_metric_*, classifier_label_*
→ categorical_metric_*. Verbose now surfaces per-kind counts +
*_types_observed lists + compartments_observed.

Regenerated gene_details_*.yml regression baselines for the rename.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Regression baselines + about content + CLAUDE.md

**Files:**
- Modify: `tests/evals/cases.yaml` (regression eval cases)
- Modify: `tests/regression/test_regression.py` (TOOL_BUILDERS — should not need changes since these tools are already registered)
- Modify: `tests/regression/test_regression/*.yml` (regen)
- Modify: `multiomics_explorer/inputs/tools/{gene_overview,list_experiments,list_publications,list_organisms,list_filter_values}.yaml`
- Regenerate: `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md`
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/derived_metrics.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add regression cases to `tests/evals/cases.yaml`**

Append:

```yaml
- name: list_organisms_compartment_vesicle
  tool: list_organisms
  params:
    compartment: vesicle
    summary: true

- name: list_publications_compartment_vesicle
  tool: list_publications
  params:
    compartment: vesicle
    summary: true

- name: list_experiments_compartment_vesicle
  tool: list_experiments
  params:
    compartment: vesicle
    summary: true

- name: list_filter_values_metric_type
  tool: list_filter_values
  params:
    filter_type: metric_type

- name: list_filter_values_value_kind
  tool: list_filter_values
  params:
    filter_type: value_kind

- name: list_filter_values_compartment
  tool: list_filter_values
  params:
    filter_type: compartment

- name: gene_overview_biller_2018_gene
  tool: gene_overview
  params:
    locus_tags: ["<known-biller-2018-locus_tag>"]   # capture before generating baselines
```

For the gene_overview case, capture a known Biller 2018 locus_tag by querying the live KG via run_cypher in your shell or via Python:

```bash
uv run python -c "
from multiomics_explorer.kg.connection import get_connection
conn = get_connection()
rows = conn.execute_query('''
    MATCH (g:Gene)<-[:Derived_metric_flags_gene]-(dm:DerivedMetric)
    WHERE dm.publication_doi CONTAINS 'biller_2018' OR dm.publication_doi CONTAINS '10.1128/mSystems.00040-18'
    RETURN g.locus_tag AS lt LIMIT 1
''')
print(rows[0]['lt'])
"
```

Replace `<known-biller-2018-locus_tag>` with the result. (Adjust the DOI predicate if Biller 2018 isn't in the KG yet — substitute any DM-bearing publication's locus_tag.)

- [ ] **Step 2: Regenerate regression baselines**

```bash
pytest tests/regression/ --force-regen -m kg -v
```

Expected: new baseline yml files for the cases above + refreshed yml for cases of the modified tools (column expansions).

- [ ] **Step 3: Verify baselines stable**

```bash
pytest tests/regression/ -m kg -v
```
Expected: all pass.

- [ ] **Step 4: Edit `inputs/tools/{name}.yaml` × 5**

For each of `gene_overview`, `list_experiments`, `list_publications`, `list_organisms`, `list_filter_values`, edit the YAML under `multiomics_explorer/inputs/tools/`:

**Common patterns to add (per-tool customization):**

`mistakes:` — add a top-of-list note:

```yaml
mistakes:
  - "If row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric."
```

`chaining:` — add:

```yaml
chaining:
  - "list_experiments → genes_by_{kind}_metric (use derived_metric_value_kinds to route)"
  - "list_filter_values(filter_type='compartment') → list_experiments(compartment=...) → ..."
```

`examples:` — add a compartment-filter example and a DM-routing example.

For `list_filter_values.yaml`, add 3 example calls covering the new filter types.

For `gene_overview.yaml`, add a chaining example "gene_overview → for genes with derived_metric_value_kinds, drill down to genes_by_{kind}_metric".

- [ ] **Step 5: Regenerate about content for each tool**

```bash
uv run python scripts/build_about_content.py gene_overview
uv run python scripts/build_about_content.py list_experiments
uv run python scripts/build_about_content.py list_publications
uv run python scripts/build_about_content.py list_organisms
uv run python scripts/build_about_content.py list_filter_values
```

Expected: 5 files in `multiomics_explorer/skills/multiomics-kg-guide/references/tools/` updated.

- [ ] **Step 6: Run about-content tests**

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -m kg -v
```
Expected: all pass.

- [ ] **Step 7: Update `references/analysis/derived_metrics.md`**

Open `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/derived_metrics.md` and add a new section **Discovery patterns** before *Gate awareness*:

```markdown
## Discovery patterns

The slice-2 discovery tools surface DerivedMetric rollups so you can browse
DM evidence without a separate `list_derived_metrics` call:

- `list_experiments`, `list_publications`, `list_organisms` carry per-row
  `derived_metric_count` (richness) and `derived_metric_value_kinds` (which
  kinds — use to route to the right drill-down). Verbose adds
  `derived_metric_types` (full list of metric_type tags) and
  `derived_metric_gene_count` (gene-level annotation total).
- Envelope rollups: `by_value_kind`, `by_metric_type`, `by_compartment`.
- `compartment` filter on the 3 list tools — `'whole_cell'`, `'vesicle'`,
  `'exoproteome'`, `'spent_medium'`, `'lysate'`. Use to scope to a wet-lab
  fraction.
- `gene_overview` carries per-gene `derived_metric_count` and
  `derived_metric_value_kinds`; verbose adds per-kind counts and
  `compartments_observed`. Envelope: `has_derived_metrics` (count of
  requested locus_tags with DM evidence).
- `list_filter_values` enumerates `metric_type`, `value_kind`, and
  `compartment` for guided discovery.

Search-text reach: after the 2026-04-27 KG fulltext enrichment landed,
`list_experiments(search_text="diel amplitude")` and
`list_publications(search_text="vesicle proteome")` route through DM tokens
(name, metric_type, field_description, compartment). `genes_by_function` is
**not** enriched with DM tokens — measuring `damping_ratio` on a gene
doesn't make `damping_ratio` part of its function.
```

- [ ] **Step 8: Update CLAUDE.md MCP Tools table**

Find the table (line ~32). Update the affected 5 rows in-place to mention DM/compartment additions:

- `gene_overview`: append "Per-row `derived_metric_count` + `derived_metric_value_kinds` (route to drill-downs); verbose adds per-kind counts + `compartments_observed`. Envelope `has_derived_metrics`."
- `list_experiments`: append "Per-row `derived_metric_count` / `derived_metric_value_kinds` / `compartment`; `compartment` filter; envelope `by_value_kind`/`by_metric_type`/`by_compartment`. Search-text picks up DM tokens (Slice 2)."
- `list_publications`: append "Same DM-rollup shape as list_experiments; per-row `compartments` is a list rollup. (Slice 2)"
- `list_organisms`: append "Same DM-rollup shape; `compartments` rollup list. (Slice 2)"
- `list_filter_values`: extend `Filter types` list with `metric_type`, `value_kind`, `compartment`.

- [ ] **Step 9: Run all tests + linters**

```bash
pytest tests/unit/ -v
pytest tests/integration/ -m kg -v
pytest tests/regression/ -m kg -v
```
Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add tests/ multiomics_explorer/inputs/ multiomics_explorer/skills/ CLAUDE.md
git commit -m "test+docs(slice-2): regression baselines + about-content for DM-aware discovery

- 7 new regression cases (compartment filters + 3 list_filter_values types + gene_overview DM)
- Regenerated baselines via --force-regen
- 5 YAML edits + about-content regen for the modified tools
- New 'Discovery patterns' section in references/analysis/derived_metrics.md
- CLAUDE.md MCP Tools table rows updated for the 5 tools

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Fulltext-search assertions

**Status:** Unblocked. KG D5 enrichment verified live 2026-04-27: `experimentFullText` includes `derived_metric_search_text` + `compartment` (bonus); `publicationFullText` includes `derived_metric_search_text` + `compartments` (bonus); `geneFullText` unchanged.

**Files:**
- Modify: `tests/integration/test_mcp_tools.py` (extend existing classes)
- Possibly: `tests/regression/test_regression.py` (add cases)

- [ ] **Step 1: Verify enrichment landed**

```bash
uv run python -c "
from multiomics_explorer.kg.connection import get_connection
conn = get_connection()
# Index covers the new property
r = conn.execute_query('''
    SHOW FULLTEXT INDEXES YIELD name, properties
    WHERE name = 'experimentFullText'
    RETURN properties
''')
assert 'derived_metric_search_text' in r[0]['properties'], 'Enrichment not landed'
# Sample search hits
hits = conn.execute_query('''
    CALL db.index.fulltext.queryNodes('experimentFullText', 'diel amplitude')
    YIELD node, score
    RETURN count(*) AS n
''')
assert hits[0]['n'] >= 1, 'No diel-amplitude hits — token enrichment broken'
print('D5 verified live')
"
```
Expected: prints "D5 verified live".

- [ ] **Step 2: Add fulltext-search integration assertions**

In `tests/integration/test_mcp_tools.py`:

```python
class TestSliceTwoSearchTextReach:
    @pytest.mark.kg
    async def test_list_experiments_search_diel_amplitude_hits_waldbauer(self, client):
        r = await client.call_tool("list_experiments",
                                   {"search_text": "diel amplitude", "limit": 5})
        ids = [row["id"] for row in r.structured_content["results"]]
        assert any("waldbauer_2012" in i for i in ids), f"Expected Waldbauer 2012 in {ids}"

    @pytest.mark.kg
    async def test_list_publications_search_damping_ratio_hits(self, client):
        r = await client.call_tool("list_publications",
                                   {"search_text": "damping ratio", "limit": 5})
        dois = [row["doi"] for row in r.structured_content["results"]]
        assert "10.1371/journal.pone.0043432" in dois  # Waldbauer 2012

    @pytest.mark.kg
    async def test_list_publications_search_vesicle_hits(self, client):
        r = await client.call_tool("list_publications",
                                   {"search_text": "vesicle proteome", "limit": 5})
        # Biller 2014/2022 vesicle proteomics papers
        assert r.structured_content["total_matching"] >= 1

    @pytest.mark.kg
    async def test_genes_by_function_NOT_enriched_with_dm_tokens(self, client):
        """Regression guard for D5: geneFullText must NOT match every protein-quantified
        gene for 'damping ratio' (would happen if the token were indexed against Gene)."""
        r = await client.call_tool("genes_by_function",
                                   {"search_text": "damping ratio", "limit": 5})
        # If geneFullText were enriched with DM tokens, this would return ~312
        # Waldbauer 2012 protein-quantified genes. Cap at well below that.
        assert r.structured_content["total_matching"] < 50, (
            f"genes_by_function returned {r.structured_content['total_matching']} hits — "
            "D5 regression: geneFullText looks DM-enriched but should not be."
        )
```

- [ ] **Step 3: Run integration tests**

```bash
pytest tests/integration/test_mcp_tools.py::TestSliceTwoSearchTextReach -m kg -v
```
Expected: all 4 pass.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_mcp_tools.py
git commit -m "test(slice-2): pin fulltext-search reach + geneFullText regression guard

After KG D5 enrichment lands, search_text on list_experiments /
list_publications routes through DM tokens. Negative assertion on
genes_by_function ensures geneFullText is NOT enriched (D5 design call).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Final integration check

- [ ] **Run full test suite**

```bash
pytest tests/unit/ -v
pytest tests/integration/ -m kg -v
pytest tests/regression/ -m kg -v
```
Expected: all green.

- [ ] **Verify CLAUDE.md table renders cleanly**

```bash
grep -A1 "gene_overview\|list_experiments\|list_publications\|list_organisms\|list_filter_values" CLAUDE.md | head -30
```

- [ ] **Smoke-test the MCP server end-to-end**

```bash
uv run multiomics-kg-mcp &
SERVER_PID=$!
sleep 3
# Use a quick MCP client invocation if available, otherwise restart the
# .claude/settings.json mcpServers entry and call the tools from a fresh
# Claude session.
kill $SERVER_PID
```

Slice 2 complete.

## Deferred follow-ups (tracked for slice 3+)

Items flagged during slice-2 implementation/review that don't block this merge:

1. **MCP-wrapper integration tests** for the 4 slice-2 tools (`gene_overview`, `list_experiments`, `list_publications`, `list_organisms`). Current integration tests in `tests/integration/test_mcp_tools.py` call `api.<func>(conn=conn)` directly, bypassing the FastMCP wrapper layer (typed Pydantic submodels, ToolError raising). The slice-1 DM tools use a `tool_fns[...]` fixture pattern that exercises the wrapper — extend it to cover the slice-2 list/overview tools. Coverage gap, not correctness.

2. ~~**`list_publications` in-memory envelope rollups → summary Cypher.** Slice 2 migrated `by_cluster_type` to summary Cypher, but `by_organism` / `by_treatment_type` / `by_background_factors` / `by_omics_type` still aggregate from detail rows in Python (`api/functions.py:798-810`). Same pattern as Tasks 2/4 already adopted. Currently fine because `list_publications` always fetches all matching detail rows, but it's wasted work and inconsistent with the slice-2 norm.~~ Shipped 2026-04-28.

3. **DE-tool `compartment` filter** (slice-3-tail). `differential_expression_by_gene` / `_by_ortholog` don't filter on compartment yet. Deferred until non-`whole_cell` DE lands; currently only `whole_cell` DE exists.

4. **Generic `Breakdown[T]` Pydantic generic.** Each tool has 3-4 nearly identical `XBreakdown` submodels (e.g. `OrgValueKindBreakdown` / `PubValueKindBreakdown` / `ExpValueKindBreakdown` are structurally identical). A `Breakdown[Annotated[str, Field(description=...)]]` generic could deduplicate, but Pydantic v2 generics interact awkwardly with FastMCP schema generation. Revisit if the breakdown class count doubles.

5. **`list_publications.md` and other about-content files**: review whether `(slice 2)` and `(D5)` / `(D7)` design tags accidentally leak into user-facing docstrings. Strip during a routine docs cleanup pass.

These items are tracked here rather than in commit messages so they don't get lost. Promote to a slice-3 plan when picked up.
