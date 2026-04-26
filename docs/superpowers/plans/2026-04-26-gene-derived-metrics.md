# gene_derived_metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `gene_derived_metrics` MCP tool — slice-1 tool 2 of 5 — a gene-centric batch lookup for `DerivedMetric` annotations across numeric / boolean / categorical kinds.

**Architecture:** Three layers (queries_lib → api → mcp_server) plus skills/about-content, mirroring `gene_clusters_by_gene`. One row per gene × DM with polymorphic `value` column (`r.value` after the 2026-04-26 KG edge-value unification rebuild). 13 compact Pydantic fields (11 emitted by Cypher today, 2 deferred forward-compat); 12 verbose Pydantic fields (11 emitted today, 1 deferred). Single organism enforced. Summary envelope has 16 keys including `not_found` / `not_matched` and 7 `by_*` breakdowns (one wide `by_metric` self-describing, six narrow `{<key>, count}` shape).

**Tech Stack:** Python 3.13, Neo4j (Bolt driver via `GraphConnection`), Cypher with APOC, FastMCP, Pydantic v2, pytest, CyVer.

**Spec:** [docs/tool-specs/gene_derived_metrics.md](../../tool-specs/gene_derived_metrics.md) (frozen — design iteration belongs in phase 1).

**Reference siblings:** `gene_clusters_by_gene` (closest analog — same envelope shape, single-organism, batch). `list_derived_metrics` (precedent for DM filter helper, string-bool coercion, p-value-family deferral).

**Pre-flight:**
- KG must be at the post-2026-04-26 rebuild state (verified: 5,114 quantifies + 4,694 flags + 316 classifies edges all carrying `r.value`). Confirm via [docs/kg-specs/2026-04-26-unify-derived-metric-edge-value.md](../../kg-specs/2026-04-26-unify-derived-metric-edge-value.md) §Status.
- Optional: work in a `git worktree` (run `uv run multiomics-explorer schema` to confirm KG connection before starting).

---

## File Structure

| Action | File | Responsibility |
|---|---|---|
| Modify | `multiomics_explorer/kg/queries_lib.py` | Add `build_gene_derived_metrics_summary()` + `build_gene_derived_metrics()` after line ~4525 (current end of `build_list_derived_metrics`). |
| Modify | `multiomics_explorer/api/functions.py` | Add `gene_derived_metrics()` after `gene_clusters_by_gene` (~line 2818, before `genes_in_cluster`). |
| Modify | `multiomics_explorer/api/__init__.py` | Add to imports + `__all__`. |
| Modify | `multiomics_explorer/__init__.py` | Add to imports + `__all__`. |
| Modify | `multiomics_explorer/mcp_server/tools.py` | Add 7 breakdown models near top of `register_tools()`. Add `GeneDerivedMetricsResult` + `GeneDerivedMetricsResponse` + `@mcp.tool async def gene_derived_metrics()`. |
| Create | `multiomics_explorer/inputs/tools/gene_derived_metrics.yaml` | Author examples / chaining / mistakes / verbose_fields. |
| Modify | `tests/unit/test_query_builders.py` | Add `TestBuildGeneDerivedMetrics` + `TestBuildGeneDerivedMetricsSummary`. |
| Modify | `tests/unit/test_api_functions.py` | Add `TestGeneDerivedMetrics`. |
| Modify | `tests/unit/test_tool_wrappers.py` | Add `"gene_derived_metrics"` to `EXPECTED_TOOLS` (line 49). Add `TestGeneDerivedMetricsWrapper`. |
| Modify | `tests/integration/test_mcp_tools.py` | Add `TestGeneDerivedMetrics` (`@pytest.mark.kg`). |
| Modify | `tests/integration/test_api_contract.py` | Add `TestGeneDerivedMetricsContract`. |
| Modify | `tests/integration/test_tool_correctness_kg.py` | Add `TestBuildGeneDerivedMetricsCorrectnessKG` if file pattern applies. |
| Modify | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS` dict (line 49). |
| Modify | `tests/evals/test_eval.py` | Add to `TOOL_BUILDERS` dict (line 56). |
| Modify | `tests/evals/cases.yaml` | Add 2-3 representative cases. |
| Modify | `CLAUDE.md` | Add row to MCP Tools table. |
| Generated | `multiomics_explorer/skills/multiomics-kg-guide/references/tools/gene_derived_metrics.md` | Output of `scripts/build_about_content.py gene_derived_metrics`. Not edited directly. |

---

## Task 1: Query builder — `build_gene_derived_metrics_summary`

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (append after line ~4525)
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for the summary builder**

Add to `tests/unit/test_query_builders.py` (placement: after `TestBuildListDerivedMetricsSummary`):

```python
class TestBuildGeneDerivedMetricsSummary:
    """Unit tests for build_gene_derived_metrics_summary (no Neo4j)."""

    def test_no_filters(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714", "PMM0001"])
        assert "UNWIND $locus_tags AS lt" in cypher
        assert "OPTIONAL MATCH (g:Gene {locus_tag: lt})" in cypher
        assert ("Derived_metric_quantifies_gene\n"
                "                    |Derived_metric_flags_gene\n"
                "                    |Derived_metric_classifies_gene") in cypher
        assert "WHERE dm IS NULL OR" not in cypher  # no DM filters
        assert params == {"locus_tags": ["PMM1714", "PMM0001"]}

    def test_metric_types_filter(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], metric_types=["damping_ratio"])
        assert "WHERE dm IS NULL OR ( dm.metric_type IN $metric_types" in cypher
        assert params["metric_types"] == ["damping_ratio"]

    def test_value_kind_filter(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], value_kind="numeric")
        assert "dm.value_kind = $value_kind" in cypher
        assert params["value_kind"] == "numeric"

    def test_compartment_filter(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], compartment="vesicle")
        assert "dm.compartment = $compartment" in cypher
        assert params["compartment"] == "vesicle"

    def test_treatment_type_lowercased(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], treatment_type=["DIEL", "Darkness"])
        assert "ANY(t IN coalesce(dm.treatment_type, [])" in cypher
        assert "toLower(t) IN $treatment_types_lower" in cypher
        assert params["treatment_types_lower"] == ["diel", "darkness"]

    def test_background_factors_lowercased(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], background_factors=["AXENIC"])
        assert "ANY(bf IN coalesce(dm.background_factors, [])" in cypher
        assert "toLower(bf) IN $bfs_lower" in cypher
        assert params["bfs_lower"] == ["axenic"]

    def test_publication_doi_filter(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"],
            publication_doi=["10.1371/journal.pone.0043432"])
        assert "dm.publication_doi IN $publication_doi" in cypher
        assert params["publication_doi"] == ["10.1371/journal.pone.0043432"]

    def test_derived_metric_ids_filter(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"],
            derived_metric_ids=["derived_metric:journal.pone.0043432:..."])
        assert "dm.id IN $derived_metric_ids" in cypher

    def test_combined_filters_anded(self):
        cypher, params = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"],
            value_kind="numeric", compartment="vesicle")
        # Both conditions inside the same `dm IS NULL OR (... AND ...)` group
        assert ("dm.value_kind = $value_kind AND dm.compartment = "
                "$compartment") in cypher

    def test_optional_match_cascade(self):
        cypher, _ = build_gene_derived_metrics_summary(
            locus_tags=["PMM1714"], value_kind="numeric")
        # Cascade emits g IS NULL → not_found, dm IS NULL → not_matched
        assert ("collect(DISTINCT CASE WHEN g IS NULL THEN lt END)"
                " AS nf_raw") in cypher
        assert ("collect(DISTINCT CASE WHEN g IS NOT NULL AND dm IS NULL"
                " THEN lt END) AS nm_raw") in cypher

    def test_rows_map_includes_name(self):
        cypher, _ = build_gene_derived_metrics_summary(locus_tags=["X"])
        # Required for by_metric self-describing entries
        assert "name: dm.name" in cypher

    def test_returns_all_envelope_keys(self):
        cypher, _ = build_gene_derived_metrics_summary(locus_tags=["X"])
        for key in [
            "total_matching", "total_derived_metrics",
            "genes_with_metrics", "genes_without_metrics",
            "not_found", "not_matched",
            "by_value_kind", "by_metric_type",
            "by_metric", "by_compartment",
            "by_treatment_type", "by_background_factors", "by_publication",
        ]:
            assert key in cypher, f"missing envelope key: {key}"

    def test_by_metric_self_describing_shape(self):
        cypher, _ = build_gene_derived_metrics_summary(locus_tags=["X"])
        # by_metric carries derived_metric_id, name, metric_type, value_kind, count
        assert "[dm_id IN apoc.coll.toSet([r IN rows | r.dm_id])" in cypher
        assert "derived_metric_id: dm_id" in cypher
        assert "name: head([r IN rows WHERE r.dm_id = dm_id | r.name])" in cypher
        assert "value_kind: head([r IN rows WHERE r.dm_id = dm_id | r.vk])" in cypher

    def test_total_derived_metrics_distinct(self):
        cypher, _ = build_gene_derived_metrics_summary(locus_tags=["X"])
        assert ("size(apoc.coll.toSet([r IN rows | r.dm_id]))"
                " AS total_derived_metrics") in cypher

    def test_genes_without_metrics_arithmetic(self):
        cypher, _ = build_gene_derived_metrics_summary(locus_tags=["X"])
        assert ("size(input_tags) - size(apoc.coll.toSet([r IN rows | r.lt]))"
                "\n         - size(not_found) AS genes_without_metrics") in cypher

    def test_locus_tags_param(self):
        _, params = build_gene_derived_metrics_summary(
            locus_tags=["A", "B"])
        assert params["locus_tags"] == ["A", "B"]
```

Ensure the import at top of `test_query_builders.py` includes:
```python
from multiomics_explorer.kg.queries_lib import (
    ...,
    build_gene_derived_metrics_summary,
)
```

- [ ] **Step 2: Run tests, expect ImportError → fail**

Run:
```bash
uv run pytest tests/unit/test_query_builders.py::TestBuildGeneDerivedMetricsSummary -v 2>&1 | head -20
```
Expected: collection error — `cannot import name 'build_gene_derived_metrics_summary'`.

- [ ] **Step 3: Implement `build_gene_derived_metrics_summary`**

Append to `multiomics_explorer/kg/queries_lib.py` after `build_list_derived_metrics` (~line 4525):

```python
def build_gene_derived_metrics_summary(
    *,
    locus_tags: list[str],
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for gene_derived_metrics.

    OPTIONAL MATCH cascade tracks not_found (no Gene) / not_matched
    (Gene present but no DM rows after filters, including kind-mismatch).
    DM-level filters wrapped inside `dm IS NULL OR (...)` so the OPTIONAL
    MATCH still emits a "no edge" row for not_matched bookkeeping.

    RETURN keys: total_matching, total_derived_metrics, genes_with_metrics,
    genes_without_metrics, not_found, not_matched, by_value_kind,
    by_metric_type, by_metric, by_compartment, by_treatment_type,
    by_background_factors, by_publication.
    """
    params: dict = {"locus_tags": locus_tags}

    dm_conditions: list[str] = []
    if metric_types is not None:
        dm_conditions.append("dm.metric_type IN $metric_types")
        params["metric_types"] = metric_types
    if value_kind is not None:
        dm_conditions.append("dm.value_kind = $value_kind")
        params["value_kind"] = value_kind
    if compartment is not None:
        dm_conditions.append("dm.compartment = $compartment")
        params["compartment"] = compartment
    if treatment_type is not None:
        dm_conditions.append(
            "ANY(t IN coalesce(dm.treatment_type, [])"
            " WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]
    if background_factors is not None:
        dm_conditions.append(
            "ANY(bf IN coalesce(dm.background_factors, [])"
            " WHERE toLower(bf) IN $bfs_lower)"
        )
        params["bfs_lower"] = [bf.lower() for bf in background_factors]
    if publication_doi is not None:
        dm_conditions.append("dm.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi
    if derived_metric_ids is not None:
        dm_conditions.append("dm.id IN $derived_metric_ids")
        params["derived_metric_ids"] = derived_metric_ids

    where_block = ""
    if dm_conditions:
        where_block = (
            "WHERE dm IS NULL OR ( "
            + " AND ".join(dm_conditions)
            + " )\n"
        )

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "OPTIONAL MATCH (g)<-[r:Derived_metric_quantifies_gene\n"
        "                    |Derived_metric_flags_gene\n"
        "                    |Derived_metric_classifies_gene]-(dm:DerivedMetric)\n"
        f"{where_block}"
        "WITH lt, g, dm, $locus_tags AS input_tags\n"
        "WITH input_tags,\n"
        "     collect(DISTINCT CASE WHEN g IS NULL THEN lt END) AS nf_raw,\n"
        "     collect(DISTINCT CASE WHEN g IS NOT NULL AND dm IS NULL THEN lt END) AS nm_raw,\n"
        "     collect(CASE WHEN dm IS NOT NULL THEN\n"
        "       {lt: lt, dm_id: dm.id, name: dm.name,\n"
        "        mt: dm.metric_type, vk: dm.value_kind,\n"
        "        comp: dm.compartment, doi: dm.publication_doi,\n"
        "        tt: dm.treatment_type, bfs: dm.background_factors} END) AS rows\n"
        "WITH input_tags,\n"
        "     [x IN nf_raw WHERE x IS NOT NULL] AS not_found,\n"
        "     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched,\n"
        "     rows\n"
        "RETURN size(rows) AS total_matching,\n"
        "       size(apoc.coll.toSet([r IN rows | r.dm_id])) AS total_derived_metrics,\n"
        "       size(apoc.coll.toSet([r IN rows | r.lt])) AS genes_with_metrics,\n"
        "       size(input_tags) - size(apoc.coll.toSet([r IN rows | r.lt]))\n"
        "         - size(not_found) AS genes_without_metrics,\n"
        "       not_found, not_matched,\n"
        "       apoc.coll.frequencies([r IN rows | r.vk]) AS by_value_kind,\n"
        "       apoc.coll.frequencies([r IN rows | r.mt]) AS by_metric_type,\n"
        "       [dm_id IN apoc.coll.toSet([r IN rows | r.dm_id]) |\n"
        "         {derived_metric_id: dm_id,\n"
        "          name: head([r IN rows WHERE r.dm_id = dm_id | r.name]),\n"
        "          metric_type: head([r IN rows WHERE r.dm_id = dm_id | r.mt]),\n"
        "          value_kind: head([r IN rows WHERE r.dm_id = dm_id | r.vk]),\n"
        "          count: size([r IN rows WHERE r.dm_id = dm_id])}] AS by_metric,\n"
        "       apoc.coll.frequencies([r IN rows | r.comp]) AS by_compartment,\n"
        "       apoc.coll.frequencies(\n"
        "         apoc.coll.flatten([r IN rows | coalesce(r.tt, [])])) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(\n"
        "         apoc.coll.flatten([r IN rows | coalesce(r.bfs, [])])) AS by_background_factors,\n"
        "       apoc.coll.frequencies([r IN rows | r.doi]) AS by_publication"
    )
    return cypher, params
```

- [ ] **Step 4: Run tests, expect PASS**

Run:
```bash
uv run pytest tests/unit/test_query_builders.py::TestBuildGeneDerivedMetricsSummary -v
```
Expected: 16 tests pass.

- [ ] **Step 5: Sanity-check the Cypher against live KG**

Run:
```bash
uv run python -c "
from multiomics_explorer.kg.queries_lib import build_gene_derived_metrics_summary
from multiomics_explorer.kg.connection import GraphConnection
cypher, params = build_gene_derived_metrics_summary(
    locus_tags=['PMN2A_2128', 'PMM1714', 'PMM_FAKE'])
conn = GraphConnection()
print(conn.execute_query(cypher, **params)[0])
"
```
Expected output matches the spec verification table:
```
{'total_matching': 12, 'total_derived_metrics': 12,
 'genes_with_metrics': 2, 'genes_without_metrics': 0,
 'not_found': ['PMM_FAKE'], 'not_matched': [], ...}
```

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(query): add build_gene_derived_metrics_summary

Summary builder for gene_derived_metrics tool (slice-1 #2).
OPTIONAL MATCH cascade tracks not_found / not_matched.
RETURNs 13 envelope keys including self-describing by_metric breakdown.
Verified live: total_matching=12 for ['PMN2A_2128', 'PMM1714', 'PMM_FAKE']."
```

---

## Task 2: Query builder — `build_gene_derived_metrics` (detail)

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py` (append after summary builder)
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_query_builders.py` after `TestBuildGeneDerivedMetricsSummary`:

```python
class TestBuildGeneDerivedMetrics:
    """Unit tests for build_gene_derived_metrics (detail)."""

    def test_no_filters(self):
        cypher, params = build_gene_derived_metrics(locus_tags=["PMM1714"])
        assert "UNWIND $locus_tags AS lt" in cypher
        assert "MATCH (g:Gene {locus_tag: lt})" in cypher
        assert ("MATCH (dm:DerivedMetric)-"
                "[r:Derived_metric_quantifies_gene\n"
                "                          |Derived_metric_flags_gene\n"
                "                          |Derived_metric_classifies_gene]"
                "->(g)") in cypher
        assert "WHERE" not in cypher.split("RETURN")[0]  # no filters
        assert params == {"locus_tags": ["PMM1714"]}

    def test_value_is_direct_r_access(self):
        # Post-rebuild: r.value, no CASE-on-value_kind, no properties(r)
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"])
        assert "r.value AS value" in cypher
        assert "CASE dm.value_kind" not in cypher
        assert "properties(r)" not in cypher

    def test_returns_compact_columns(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"])
        # 11 compact RETURN columns (13 Pydantic minus deferred adjusted_p_value, significant)
        for col in [
            "g.locus_tag AS locus_tag",
            "g.gene_name AS gene_name",
            "dm.id AS derived_metric_id",
            "dm.value_kind AS value_kind",
            "dm.name AS name",
            "r.value AS value",
            "dm.rankable = 'true' AS rankable",
            "dm.has_p_value = 'true' AS has_p_value",
        ]:
            assert col in cypher, f"missing compact column: {col}"

    def test_rankable_case_gates(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"])
        for col in ["rank_by_metric", "metric_percentile", "metric_bucket"]:
            assert (f"CASE WHEN dm.rankable = 'true' THEN r.{col} "
                    f"ELSE null END AS {col}") in cypher

    def test_has_p_value_columns_deferred(self):
        # adjusted_p_value, significant: declared in Pydantic; absent from Cypher
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"])
        assert "AS adjusted_p_value" not in cypher
        assert "AS significant" not in cypher

    def test_p_value_deferred_in_verbose(self):
        # Same forward-compat treatment; verbose RETURN omits r.p_value today
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"], verbose=True)
        assert "r.p_value" not in cypher

    def test_metric_types_filter(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], metric_types=["damping_ratio"])
        assert "WHERE dm.metric_type IN $metric_types" in cypher
        assert params["metric_types"] == ["damping_ratio"]

    def test_value_kind_filter(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], value_kind="numeric")
        assert "dm.value_kind = $value_kind" in cypher

    def test_compartment_filter(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], compartment="vesicle")
        assert "dm.compartment = $compartment" in cypher

    def test_treatment_type_lowercased(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], treatment_type=["DIEL"])
        assert "ANY(t IN coalesce(dm.treatment_type, [])" in cypher
        assert params["treatment_types_lower"] == ["diel"]

    def test_background_factors_lowercased(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], background_factors=["Axenic"])
        assert params["bfs_lower"] == ["axenic"]

    def test_publication_doi_filter(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], publication_doi=["10.X/Y"])
        assert "dm.publication_doi IN $publication_doi" in cypher

    def test_derived_metric_ids_filter(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], derived_metric_ids=["a"])
        assert "dm.id IN $derived_metric_ids" in cypher

    def test_combined_filters_anded(self):
        cypher, _ = build_gene_derived_metrics(
            locus_tags=["X"], value_kind="numeric", compartment="vesicle")
        assert ("WHERE dm.value_kind = $value_kind AND "
                "dm.compartment = $compartment") in cypher

    def test_verbose_adds_columns(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"], verbose=True)
        for col in [
            "dm.metric_type AS metric_type",
            "dm.field_description AS field_description",
            "dm.unit AS unit",
            "dm.compartment AS compartment",
            "coalesce(dm.treatment_type, []) AS treatment_type",
            "coalesce(dm.background_factors, []) AS background_factors",
            "dm.publication_doi AS publication_doi",
            "dm.treatment AS treatment",
            "dm.light_condition AS light_condition",
            "dm.experimental_context AS experimental_context",
        ]:
            assert col in cypher, f"missing verbose column: {col}"

    def test_allowed_categories_case_gated_in_verbose(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"], verbose=True)
        assert ("CASE WHEN dm.value_kind = 'categorical'\n"
                "            THEN dm.allowed_categories ELSE null END "
                "AS allowed_categories") in cypher

    def test_compact_omits_verbose_fields(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"], verbose=False)
        for col in ["AS metric_type", "AS field_description", "AS unit",
                    "AS allowed_categories", "AS compartment",
                    "AS treatment_type", "AS background_factors",
                    "AS publication_doi", "AS treatment",
                    "AS light_condition", "AS experimental_context"]:
            assert col not in cypher, f"{col} should be verbose-only"

    def test_order_by(self):
        cypher, _ = build_gene_derived_metrics(locus_tags=["X"])
        assert ("ORDER BY g.locus_tag ASC, dm.value_kind ASC, "
                "dm.id ASC") in cypher

    def test_limit_offset(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert "LIMIT $limit" in cypher
        assert params["limit"] == 10
        assert params["offset"] == 5

    def test_no_skip_when_offset_zero(self):
        cypher, params = build_gene_derived_metrics(
            locus_tags=["X"], limit=10)
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_no_limit_when_none(self):
        cypher, params = build_gene_derived_metrics(locus_tags=["X"])
        assert "LIMIT" not in cypher
        assert "limit" not in params
```

Update import block at top of `test_query_builders.py`:
```python
from multiomics_explorer.kg.queries_lib import (
    ...,
    build_gene_derived_metrics,
    build_gene_derived_metrics_summary,
)
```

- [ ] **Step 2: Run tests, expect fail (ImportError)**

```bash
uv run pytest tests/unit/test_query_builders.py::TestBuildGeneDerivedMetrics -v 2>&1 | head -20
```

- [ ] **Step 3: Implement `build_gene_derived_metrics`**

Append to `multiomics_explorer/kg/queries_lib.py` after `build_gene_derived_metrics_summary`:

```python
def build_gene_derived_metrics(
    *,
    locus_tags: list[str],
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_derived_metrics.

    One row per gene × DM. `r.value` is polymorphic across edge types
    (float / 'true'/'false' string / category string) — branch on
    value_kind in the consumer.

    RETURN keys (compact, 11 columns today): locus_tag, gene_name,
    derived_metric_id, value_kind, name, value, rankable, has_p_value,
    rank_by_metric, metric_percentile, metric_bucket.

    NOTE: adjusted_p_value, significant are declared in the Pydantic
    Result model with default=None but NOT in the current Cypher RETURN
    — no edge in today's KG carries those props (no DM has
    has_p_value='true') and including them produces CyVer schema
    warnings. Mirrors p_value_threshold deferral in
    build_list_derived_metrics. Re-add CASE-gated RETURN columns
    (`CASE WHEN dm.has_p_value = 'true' THEN r.<col> ELSE null END`)
    when a has_p_value='true' DM lands.

    RETURN keys (verbose, 11 added today): metric_type,
    field_description, unit, allowed_categories, compartment,
    treatment_type, background_factors, publication_doi, treatment,
    light_condition, experimental_context. p_value (raw, edge-side)
    is also deferred until has_p_value DM lands.
    """
    params: dict = {"locus_tags": locus_tags}

    conditions: list[str] = []
    if metric_types is not None:
        conditions.append("dm.metric_type IN $metric_types")
        params["metric_types"] = metric_types
    if value_kind is not None:
        conditions.append("dm.value_kind = $value_kind")
        params["value_kind"] = value_kind
    if compartment is not None:
        conditions.append("dm.compartment = $compartment")
        params["compartment"] = compartment
    if treatment_type is not None:
        conditions.append(
            "ANY(t IN coalesce(dm.treatment_type, [])"
            " WHERE toLower(t) IN $treatment_types_lower)"
        )
        params["treatment_types_lower"] = [t.lower() for t in treatment_type]
    if background_factors is not None:
        conditions.append(
            "ANY(bf IN coalesce(dm.background_factors, [])"
            " WHERE toLower(bf) IN $bfs_lower)"
        )
        params["bfs_lower"] = [bf.lower() for bf in background_factors]
    if publication_doi is not None:
        conditions.append("dm.publication_doi IN $publication_doi")
        params["publication_doi"] = publication_doi
    if derived_metric_ids is not None:
        conditions.append("dm.id IN $derived_metric_ids")
        params["derived_metric_ids"] = derived_metric_ids

    where_block = ""
    if conditions:
        where_block = "WHERE " + " AND ".join(conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       dm.metric_type AS metric_type"
            ",\n       dm.field_description AS field_description"
            ",\n       dm.unit AS unit"
            ",\n       CASE WHEN dm.value_kind = 'categorical'\n"
            "            THEN dm.allowed_categories ELSE null END "
            "AS allowed_categories"
            ",\n       dm.compartment AS compartment"
            ",\n       coalesce(dm.treatment_type, []) AS treatment_type"
            ",\n       coalesce(dm.background_factors, []) AS background_factors"
            ",\n       dm.publication_doi AS publication_doi"
            ",\n       dm.treatment AS treatment"
            ",\n       dm.light_condition AS light_condition"
            ",\n       dm.experimental_context AS experimental_context"
        )

    if offset:
        skip_clause = "\nSKIP $offset"
        params["offset"] = offset
    else:
        skip_clause = ""
    if limit is not None:
        limit_clause = "\nLIMIT $limit"
        params["limit"] = limit
    else:
        limit_clause = ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "MATCH (g:Gene {locus_tag: lt})\n"
        "MATCH (dm:DerivedMetric)-[r:Derived_metric_quantifies_gene\n"
        "                          |Derived_metric_flags_gene\n"
        "                          |Derived_metric_classifies_gene]->(g)\n"
        f"{where_block}"
        "RETURN g.locus_tag AS locus_tag,\n"
        "       g.gene_name AS gene_name,\n"
        "       dm.id AS derived_metric_id,\n"
        "       dm.value_kind AS value_kind,\n"
        "       dm.name AS name,\n"
        "       r.value AS value,\n"
        "       dm.rankable = 'true' AS rankable,\n"
        "       dm.has_p_value = 'true' AS has_p_value,\n"
        "       CASE WHEN dm.rankable = 'true' THEN r.rank_by_metric ELSE null END AS rank_by_metric,\n"
        "       CASE WHEN dm.rankable = 'true' THEN r.metric_percentile ELSE null END AS metric_percentile,\n"
        "       CASE WHEN dm.rankable = 'true' THEN r.metric_bucket ELSE null END AS metric_bucket"
        f"{verbose_cols}\n"
        "ORDER BY g.locus_tag ASC, dm.value_kind ASC, dm.id ASC"
        f"{skip_clause}{limit_clause}"
    )
    return cypher, params
```

- [ ] **Step 4: Run tests, expect PASS**

```bash
uv run pytest tests/unit/test_query_builders.py::TestBuildGeneDerivedMetrics -v
```
Expected: 22 tests pass.

- [ ] **Step 5: Sanity-check detail builder against live KG**

```bash
uv run python -c "
from multiomics_explorer.kg.queries_lib import build_gene_derived_metrics
from multiomics_explorer.kg.connection import GraphConnection
cypher, params = build_gene_derived_metrics(locus_tags=['PMM1714'])
rows = GraphConnection().execute_query(cypher, **params)
print(f'rows: {len(rows)}')  # expect 9
for r in rows[:3]:
    print(r['locus_tag'], r['value_kind'], type(r['value']).__name__, r['value'])
"
```
Expected:
```
rows: 9
PMM1714 boolean str true
PMM1714 categorical str Cytoplasmic Membrane
PMM1714 numeric float 1.3
```

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(query): add build_gene_derived_metrics (detail builder)

Detail builder for gene_derived_metrics tool. Single MATCH chain
unifies all 3 DM edge types (post-2026-04-26 r.value rebuild).
11 compact + 11 verbose RETURN columns; adjusted_p_value/significant
deferred (CyVer warnings, no DM has has_p_value=true today).
Verified live: 9 rows for PMM1714 with polymorphic r.value rendering."
```

---

## Task 3: API function — `gene_derived_metrics`

**Files:**
- Modify: `multiomics_explorer/api/functions.py` (insert after `gene_clusters_by_gene`, ~line 2818, before `genes_in_cluster`)
- Test: `tests/unit/test_api_functions.py`

- [ ] **Step 1: Write failing API tests**

Add to `tests/unit/test_api_functions.py`:

```python
class TestGeneDerivedMetrics:
    """Unit tests for api.gene_derived_metrics with mocked GraphConnection."""

    @pytest.fixture
    def mock_summary_result(self):
        return [{
            "total_matching": 9,
            "total_derived_metrics": 9,
            "genes_with_metrics": 1,
            "genes_without_metrics": 0,
            "not_found": [],
            "not_matched": [],
            "by_value_kind": [{"item": "numeric", "count": 7},
                              {"item": "boolean", "count": 1},
                              {"item": "categorical", "count": 1}],
            "by_metric_type": [{"item": "damping_ratio", "count": 1}],
            "by_metric": [{"derived_metric_id": "dm:foo",
                           "name": "Foo metric",
                           "metric_type": "damping_ratio",
                           "value_kind": "numeric",
                           "count": 1}],
            "by_compartment": [{"item": "whole_cell", "count": 7},
                               {"item": "vesicle", "count": 2}],
            "by_treatment_type": [{"item": "diel", "count": 6}],
            "by_background_factors": [{"item": "axenic", "count": 9}],
            "by_publication": [{"item": "10.1371/...", "count": 9}],
        }]

    def test_envelope_keys_present(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [mock_summary_result, []]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], conn=mock_conn, summary=True)
        for key in [
            "total_matching", "total_derived_metrics",
            "genes_with_metrics", "genes_without_metrics",
            "not_found", "not_matched",
            "by_value_kind", "by_metric_type", "by_metric",
            "by_compartment", "by_treatment_type",
            "by_background_factors", "by_publication",
            "returned", "offset", "truncated", "results",
        ]:
            assert key in data, f"missing envelope key: {key}"

    def test_summary_skips_detail_query(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        mock_conn.execute_query.return_value = mock_summary_result
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], conn=mock_conn, summary=True)
        assert mock_conn.execute_query.call_count == 1  # summary only
        assert data["results"] == []
        assert data["returned"] == 0
        assert data["truncated"] is True  # total_matching=9 > returned=0

    def test_empty_locus_tags_raises(self):
        with pytest.raises(ValueError, match="locus_tags must not be empty"):
            api.gene_derived_metrics([], conn=MagicMock())

    def test_truncated_full_set(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        details = [{"locus_tag": "PMM1714"}] * 9
        mock_conn.execute_query.side_effect = [mock_summary_result, details]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(["PMM1714"], conn=mock_conn)
        assert data["returned"] == 9
        assert data["truncated"] is False  # 9 not > 0+9

    def test_truncated_partial(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        details = [{"locus_tag": "PMM1714"}] * 5
        mock_conn.execute_query.side_effect = [mock_summary_result, details]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], conn=mock_conn, limit=5)
        assert data["returned"] == 5
        assert data["truncated"] is True  # 9 > 0+5

    def test_rename_freq_applied(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [mock_summary_result, []]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], conn=mock_conn, summary=True)
        # Frequency-style breakdowns get renamed item -> domain key
        assert data["by_value_kind"][0] == {"value_kind": "numeric", "count": 7}
        assert data["by_compartment"][0] == {"compartment": "whole_cell", "count": 7}

    def test_by_metric_passthrough_no_rename(self, mock_summary_result):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        mock_conn.execute_query.side_effect = [mock_summary_result, []]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM1714"], conn=mock_conn, summary=True)
        # by_metric is already shaped; should NOT be renamed
        assert data["by_metric"][0]["derived_metric_id"] == "dm:foo"
        assert data["by_metric"][0]["name"] == "Foo metric"

    def test_by_metric_sorted_count_desc(self):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        # Cypher returns set-iteration order, api/ must sort
        mock_summary = [{
            "total_matching": 5, "total_derived_metrics": 2,
            "genes_with_metrics": 1, "genes_without_metrics": 0,
            "not_found": [], "not_matched": [],
            "by_value_kind": [], "by_metric_type": [],
            "by_metric": [
                {"derived_metric_id": "a", "name": "A", "metric_type": "x",
                 "value_kind": "numeric", "count": 1},
                {"derived_metric_id": "b", "name": "B", "metric_type": "y",
                 "value_kind": "numeric", "count": 4},
            ],
            "by_compartment": [], "by_treatment_type": [],
            "by_background_factors": [], "by_publication": [],
        }]
        mock_conn.execute_query.side_effect = [mock_summary, []]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["X"], conn=mock_conn, summary=True)
        assert data["by_metric"][0]["count"] == 4
        assert data["by_metric"][1]["count"] == 1

    def test_not_found_plumbed_through(self):
        from unittest.mock import MagicMock, patch
        mock_conn = MagicMock()
        mock_summary = [{
            "total_matching": 0, "total_derived_metrics": 0,
            "genes_with_metrics": 0, "genes_without_metrics": 0,
            "not_found": ["PMM_FAKE"], "not_matched": [],
            "by_value_kind": [], "by_metric_type": [],
            "by_metric": [], "by_compartment": [],
            "by_treatment_type": [], "by_background_factors": [],
            "by_publication": [],
        }]
        mock_conn.execute_query.side_effect = [mock_summary, []]
        with patch("multiomics_explorer.api.functions._validate_organism_inputs"):
            data = api.gene_derived_metrics(
                ["PMM_FAKE"], conn=mock_conn, summary=True)
        assert data["not_found"] == ["PMM_FAKE"]
        assert data["not_matched"] == []
```

Add to imports in `test_api_functions.py`:
```python
from unittest.mock import MagicMock
```

- [ ] **Step 2: Run tests, expect fail (AttributeError)**

```bash
uv run pytest tests/unit/test_api_functions.py::TestGeneDerivedMetrics -v 2>&1 | head -20
```

- [ ] **Step 3: Implement `api.gene_derived_metrics`**

Add to `multiomics_explorer/api/functions.py`. Find the `gene_clusters_by_gene` function (~line 2720) and insert the new function immediately after it (before `genes_in_cluster`):

```python
def gene_derived_metrics(
    locus_tags: list[str],
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: Literal["numeric", "boolean", "categorical"] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Gene-centric DerivedMetric lookup. Single organism enforced.

    Returns dict with keys: total_matching, total_derived_metrics,
    genes_with_metrics, genes_without_metrics, not_found, not_matched,
    by_value_kind, by_metric_type, by_metric, by_compartment,
    by_treatment_type, by_background_factors, by_publication,
    returned, offset, truncated, results.
    Per result (compact, 13 Pydantic fields; 11 emitted by Cypher today):
    locus_tag, gene_name, derived_metric_id, value_kind, name, value,
    rankable, has_p_value, rank_by_metric, metric_percentile,
    metric_bucket, adjusted_p_value (None today), significant (None today).
    Per result (verbose adds, 12 Pydantic; 11 emitted today): metric_type,
    field_description, unit, allowed_categories, compartment,
    treatment_type, background_factors, publication_doi, treatment,
    light_condition, experimental_context, p_value (None today).

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: locus_tags empty, or spans multiple organisms,
                    or organism arg conflicts with inferred organism.
    """
    if not locus_tags:
        raise ValueError("locus_tags must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Single-organism enforcement
    _validate_organism_inputs(
        organism=organism, locus_tags=locus_tags,
        experiment_ids=None, conn=conn,
    )

    filter_kwargs = dict(
        metric_types=metric_types, value_kind=value_kind,
        compartment=compartment, treatment_type=treatment_type,
        background_factors=background_factors,
        publication_doi=publication_doi,
        derived_metric_ids=derived_metric_ids,
    )

    # Summary query — always runs
    sum_cypher, sum_params = build_gene_derived_metrics_summary(
        locus_tags=locus_tags, **filter_kwargs)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    total_matching = raw_summary["total_matching"]

    # by_metric is already shaped — sort by count desc; no rename
    by_metric = sorted(
        raw_summary["by_metric"], key=lambda x: x["count"], reverse=True)

    envelope = {
        "total_matching": total_matching,
        "total_derived_metrics": raw_summary["total_derived_metrics"],
        "genes_with_metrics": raw_summary["genes_with_metrics"],
        "genes_without_metrics": raw_summary["genes_without_metrics"],
        "not_found": raw_summary["not_found"],
        "not_matched": raw_summary["not_matched"],
        "by_value_kind": _rename_freq(
            raw_summary["by_value_kind"], "value_kind"),
        "by_metric_type": _rename_freq(
            raw_summary["by_metric_type"], "metric_type"),
        "by_metric": by_metric,
        "by_compartment": _rename_freq(
            raw_summary["by_compartment"], "compartment"),
        "by_treatment_type": _rename_freq(
            raw_summary["by_treatment_type"], "treatment_type"),
        "by_background_factors": _rename_freq(
            raw_summary["by_background_factors"], "background_factor"),
        "by_publication": _rename_freq(
            raw_summary["by_publication"], "publication_doi"),
    }

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_gene_derived_metrics(
        locus_tags=locus_tags, **filter_kwargs,
        verbose=verbose, limit=limit, offset=offset)
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope
```

Add to the import block at the top of `multiomics_explorer/api/functions.py` (the multi-line import from `multiomics_explorer.kg.queries_lib` ~line 29):

```python
from multiomics_explorer.kg.queries_lib import (
    ...,
    build_gene_derived_metrics,
    build_gene_derived_metrics_summary,
)
```

- [ ] **Step 4: Run tests, expect PASS**

```bash
uv run pytest tests/unit/test_api_functions.py::TestGeneDerivedMetrics -v
```
Expected: 9 tests pass.

- [ ] **Step 5: End-to-end sanity against live KG**

```bash
uv run python -c "
from multiomics_explorer import api
data = api.gene_derived_metrics(['PMM1714'], summary=True)
print('total_matching:', data['total_matching'])  # 9
print('by_value_kind:', data['by_value_kind'])
print('by_metric (top 3):', data['by_metric'][:3])
"
```
Expected: `total_matching: 9`; `by_value_kind` has numeric/boolean/categorical with `value_kind` key (renamed); `by_metric` entries carry `derived_metric_id`/`name`/`metric_type`/`value_kind`/`count`.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/api/functions.py tests/unit/test_api_functions.py
git commit -m "feat(api): add gene_derived_metrics

Gene-centric batch DerivedMetric lookup. Single-organism enforced
via _validate_organism_inputs. 2-query pattern (summary always runs;
detail skipped when limit=0). by_metric sorted by count desc in api/
(Cypher returns set-iteration order). Verified live for PMM1714."
```

---

## Task 4: Wire api exports

**Files:**
- Modify: `multiomics_explorer/api/__init__.py`
- Modify: `multiomics_explorer/__init__.py`

- [ ] **Step 1: Add to `api/__init__.py`**

Open `multiomics_explorer/api/__init__.py`. Find the import block listing api functions (look for `gene_clusters_by_gene` import). Add `gene_derived_metrics` alphabetically next to it:

```python
from multiomics_explorer.api.functions import (
    ...,
    gene_clusters_by_gene,
    gene_derived_metrics,
    gene_details,
    ...,
)
```

Add to `__all__` list in the same file, alphabetically:

```python
__all__ = [
    ...,
    "gene_clusters_by_gene",
    "gene_derived_metrics",
    "gene_details",
    ...,
]
```

- [ ] **Step 2: Add to `multiomics_explorer/__init__.py`**

Same edits — package-level re-export:

```python
from multiomics_explorer.api import (
    ...,
    gene_clusters_by_gene,
    gene_derived_metrics,
    ...,
)

__all__ = [
    ...,
    "gene_clusters_by_gene",
    "gene_derived_metrics",
    ...,
]
```

- [ ] **Step 3: Verify import path works**

```bash
uv run python -c "from multiomics_explorer import gene_derived_metrics; print(gene_derived_metrics.__name__)"
```
Expected: `gene_derived_metrics`.

- [ ] **Step 4: Commit**

```bash
git add multiomics_explorer/api/__init__.py multiomics_explorer/__init__.py
git commit -m "feat(exports): wire gene_derived_metrics into package surface"
```

---

## Task 5: MCP wrapper — Pydantic breakdown models

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` (inside `register_tools(mcp)`, near `GeneClusterTypeBreakdown` ~line 3131)

- [ ] **Step 1: Add the 7 breakdown models**

Find the `GeneClusterTypeBreakdown` definition (~line 3131 inside `register_tools(mcp)`). Add these 7 classes immediately after the cluster breakdowns block:

```python
    # ── gene_derived_metrics breakdowns ────────────────────────────────

    class GeneDmValueKindBreakdown(BaseModel):
        value_kind: Literal["numeric", "boolean", "categorical"] = Field(
            description="DM value kind.")
        count: int = Field(description="Rows of this value_kind.")

    class GeneDmMetricTypeBreakdown(BaseModel):
        metric_type: str = Field(description="DM metric_type tag.")
        count: int = Field(description="Rows of this metric_type.")

    class GeneDmMetricBreakdown(BaseModel):
        derived_metric_id: str = Field(description="Unique DM id.")
        name: str = Field(description="Human-readable DM name.")
        metric_type: str = Field(description="Category tag.")
        value_kind: Literal["numeric", "boolean", "categorical"] = Field(
            description="Routes to the matching genes_by_*_metric drill-down.")
        count: int = Field(description="Rows contributed by this DM.")

    class GeneDmCompartmentBreakdown(BaseModel):
        compartment: str = Field(
            description="Sample compartment ('whole_cell', 'vesicle', etc.).")
        count: int = Field(description="Rows in this compartment.")

    class GeneDmTreatmentBreakdown(BaseModel):
        treatment_type: str = Field(description="Treatment type.")
        count: int = Field(description="Rows touching this treatment.")

    class GeneDmBackgroundFactorBreakdown(BaseModel):
        background_factor: str = Field(description="Background experimental factor.")
        count: int = Field(description="Rows under this factor.")

    class GeneDmPublicationBreakdown(BaseModel):
        publication_doi: str = Field(description="Parent publication DOI.")
        count: int = Field(description="Rows from this publication.")
```

- [ ] **Step 2: Verify Pydantic models import without errors**

```bash
uv run python -c "
from multiomics_explorer.mcp_server.tools import register_tools
from fastmcp import FastMCP
register_tools(FastMCP('test'))
print('OK')
"
```
Expected: `OK` (no NameError or ValidationError).

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "feat(mcp): add gene_derived_metrics breakdown models

Seven Pydantic breakdown classes (1 wide GeneDmMetricBreakdown for
self-describing by_metric, 6 narrow {<key>, count} for the rest).
Mirrors gene_clusters_by_gene cluster breakdown pattern."
```

---

## Task 6: MCP wrapper — Result + Response models

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`

- [ ] **Step 1: Add `GeneDerivedMetricsResult` and `GeneDerivedMetricsResponse`**

Add immediately after the 7 breakdown models from Task 5:

```python
    class GeneDerivedMetricsResult(BaseModel):
        # ── compact (always populated by api/) ──────────────────────────
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM1714').")
        gene_name: str | None = Field(
            default=None,
            description="Gene name (e.g. 'dnaN') — null when KG has no name.")
        derived_metric_id: str = Field(
            description="Unique parent-DM id. Pass to `derived_metric_ids` "
                        "on genes_by_*_metric drill-downs to pin this exact "
                        "DM. metric_type, compartment, publication_doi etc. "
                        "are available in verbose mode or via "
                        "list_derived_metrics(derived_metric_ids=[...]).")
        value_kind: Literal["numeric", "boolean", "categorical"] = Field(
            description="Determines how to interpret `value`. Routes to the "
                        "matching genes_by_*_metric drill-down.")
        name: str = Field(
            description="Human-readable DM name (e.g. 'Transcript:protein "
                        "amplitude ratio'). Saves a round-trip to "
                        "list_derived_metrics for opaque metric_type codes.")
        value: float | str = Field(
            description="Polymorphic measurement: float on numeric rows, "
                        "'true'/'false' string on boolean rows, category "
                        "string on categorical rows. Branch on `value_kind`.")
        rankable: bool = Field(
            description="Echoed from parent DM. True iff this row's `value` "
                        "carries rank/percentile/bucket extras.")
        has_p_value: bool = Field(
            description="Echoed from parent DM. True iff adjusted_p_value/"
                        "significant carry data. No DM in current KG has p-values.")
        rank_by_metric: int | None = Field(
            default=None,
            description="Rank by metric value (1 = highest). Populated only "
                        "when parent DM rankable=True.")
        metric_percentile: float | None = Field(
            default=None,
            description="Percentile within metric distribution (0-100). "
                        "Same gate as rank_by_metric.")
        metric_bucket: str | None = Field(
            default=None,
            description="Bucket label ('top_decile', 'top_quartile', 'mid', "
                        "'low'). Same gate as rank_by_metric.")
        adjusted_p_value: float | None = Field(
            default=None,
            description="BH-adjusted p-value. Populated only when parent DM "
                        "has_p_value=True. No DM in current KG has p-values; "
                        "Cypher RETURN omits this column today.")
        significant: bool | None = Field(
            default=None,
            description="Significance flag at the DM's p_value_threshold. "
                        "Same gate as adjusted_p_value.")
        # ── verbose adds (default None / [] when verbose=False) ─────────
        metric_type: str | None = Field(
            default=None,
            description="Category tag for this DM (e.g. 'damping_ratio'). "
                        "Verbose only.")
        field_description: str | None = Field(
            default=None,
            description="Detailed explanation of what this DM measures. "
                        "Verbose only.")
        unit: str | None = Field(
            default=None,
            description="Measurement unit (e.g. 'hours', 'log2'). "
                        "Verbose only.")
        allowed_categories: list[str] | None = Field(
            default=None,
            description="Valid category strings — non-null only on "
                        "categorical rows. Verbose only.")
        compartment: str | None = Field(
            default=None,
            description="Sample compartment. Verbose only.")
        treatment_type: list[str] = Field(
            default_factory=list,
            description="Treatment type(s) for the parent experiment. "
                        "Verbose only.")
        background_factors: list[str] = Field(
            default_factory=list,
            description="Background experimental factors (may be empty). "
                        "Verbose only.")
        publication_doi: str | None = Field(
            default=None,
            description="Parent publication DOI. Verbose only.")
        treatment: str | None = Field(
            default=None,
            description="Treatment description in plain language. Verbose only.")
        light_condition: str | None = Field(
            default=None,
            description="Light regime. Verbose only.")
        experimental_context: str | None = Field(
            default=None,
            description="Longer experimental setup description. Verbose only.")
        p_value: float | None = Field(
            default=None,
            description="Raw p-value. Populated only when parent DM "
                        "has_p_value=True (none in current KG). Verbose only.")

    class GeneDerivedMetricsResponse(BaseModel):
        total_matching: int = Field(
            description="Gene × DM rows matching all filters.")
        total_derived_metrics: int = Field(
            description="Distinct DMs touching the input genes after filters.")
        genes_with_metrics: int = Field(
            description="Input genes with >=1 matching DM row.")
        genes_without_metrics: int = Field(
            description="Input genes present in KG but with zero matching "
                        "DM rows after filters.")
        not_found: list[str] = Field(
            default_factory=list,
            description="Input locus_tags absent from the KG (echo).")
        not_matched: list[str] = Field(
            default_factory=list,
            description="Input locus_tags in KG but with zero DM rows after "
                        "filters (includes kind-mismatch when value_kind set).")
        by_value_kind: list[GeneDmValueKindBreakdown] = Field(
            description="Rows per value_kind.")
        by_metric_type: list[GeneDmMetricTypeBreakdown] = Field(
            description="Rows per metric_type — coarse rollup; same "
                        "metric_type may aggregate across publications.")
        by_metric: list[GeneDmMetricBreakdown] = Field(
            description="Rows per unique DerivedMetric — fine breakdown that "
                        "disambiguates within a metric_type. Each entry "
                        "embeds name, metric_type, and value_kind so "
                        "derived_metric_ids can be picked for downstream "
                        "drill-down. Sorted by count desc.")
        by_compartment: list[GeneDmCompartmentBreakdown] = Field(
            description="Rows per compartment.")
        by_treatment_type: list[GeneDmTreatmentBreakdown] = Field(
            description="Rows per treatment_type (flattened).")
        by_background_factors: list[GeneDmBackgroundFactorBreakdown] = Field(
            description="Rows per background factor (flattened).")
        by_publication: list[GeneDmPublicationBreakdown] = Field(
            description="Rows per parent publication.")
        returned: int = Field(description="Length of results list.")
        offset: int = Field(default=0, description="Pagination offset used.")
        truncated: bool = Field(
            description="True when total_matching > offset + returned.")
        results: list[GeneDerivedMetricsResult] = Field(
            default_factory=list,
            description="One row per gene × DM. Empty when summary=True.")
```

- [ ] **Step 2: Verify models load**

```bash
uv run python -c "
from multiomics_explorer.mcp_server.tools import register_tools
from fastmcp import FastMCP
register_tools(FastMCP('test'))
print('OK')
"
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "feat(mcp): add GeneDerivedMetricsResult and GeneDerivedMetricsResponse

13 compact + 12 verbose Pydantic Result fields with default=None
forward-compat slots for adjusted_p_value/significant/p_value
(deferred from Cypher RETURN until has_p_value DM lands).
17-field envelope including not_found/not_matched and 7 by_* breakdowns."
```

---

## Task 7: MCP wrapper — `@mcp.tool` function

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py` (inside `register_tools(mcp)`)
- Modify: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 1: Add `gene_derived_metrics` to `EXPECTED_TOOLS`**

In `tests/unit/test_tool_wrappers.py` line 49, add `"gene_derived_metrics"` to the list (alphabetically near `gene_clusters_by_gene`):

```python
EXPECTED_TOOLS = [
    ...,
    "gene_clusters_by_gene",
    "gene_derived_metrics",
    "genes_in_cluster",
    ...,
]
```

- [ ] **Step 2: Write failing wrapper tests**

Append to `tests/unit/test_tool_wrappers.py` after `TestGeneClustersByGeneWrapper`:

```python
class TestGeneDerivedMetricsWrapper:
    """Unit tests for gene_derived_metrics MCP wrapper."""

    @pytest.fixture
    def envelope_data(self):
        return {
            "total_matching": 9, "total_derived_metrics": 9,
            "genes_with_metrics": 1, "genes_without_metrics": 0,
            "not_found": [], "not_matched": [],
            "by_value_kind": [{"value_kind": "numeric", "count": 7}],
            "by_metric_type": [{"metric_type": "damping_ratio", "count": 1}],
            "by_metric": [{"derived_metric_id": "dm:foo", "name": "Foo",
                           "metric_type": "damping_ratio",
                           "value_kind": "numeric", "count": 1}],
            "by_compartment": [{"compartment": "whole_cell", "count": 7}],
            "by_treatment_type": [{"treatment_type": "diel", "count": 6}],
            "by_background_factors": [{"background_factor": "axenic", "count": 9}],
            "by_publication": [{"publication_doi": "10.X/Y", "count": 9}],
            "returned": 1, "offset": 0, "truncated": True,
            "results": [{
                "locus_tag": "PMM1714",
                "gene_name": "dnaN",
                "derived_metric_id": "dm:foo",
                "value_kind": "numeric",
                "name": "Foo",
                "value": 1.3,
                "rankable": True,
                "has_p_value": False,
                "rank_by_metric": 286,
                "metric_percentile": 8.36,
                "metric_bucket": "low",
                # adjusted_p_value, significant: missing in dict; Pydantic fills None
            }],
        }

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self, tool_fns, envelope_data):
        from unittest.mock import patch, AsyncMock
        with patch("multiomics_explorer.mcp_server.tools.api.gene_derived_metrics",
                   return_value=envelope_data):
            ctx = AsyncMock()
            response = await tool_fns["gene_derived_metrics"](
                ctx, locus_tags=["PMM1714"])
        assert response.total_matching == 9
        assert response.returned == 1
        assert len(response.by_metric) == 1

    @pytest.mark.asyncio
    async def test_polymorphic_value_field(self, tool_fns):
        """Pydantic value: float | str accepts both."""
        from unittest.mock import patch, AsyncMock
        for val in [1.3, "true", "Cytoplasmic Membrane"]:
            envelope = {
                "total_matching": 1, "total_derived_metrics": 1,
                "genes_with_metrics": 1, "genes_without_metrics": 0,
                "not_found": [], "not_matched": [],
                "by_value_kind": [], "by_metric_type": [], "by_metric": [],
                "by_compartment": [], "by_treatment_type": [],
                "by_background_factors": [], "by_publication": [],
                "returned": 1, "offset": 0, "truncated": False,
                "results": [{
                    "locus_tag": "X", "gene_name": None,
                    "derived_metric_id": "dm:1",
                    "value_kind": "numeric" if isinstance(val, float) else "boolean",
                    "name": "n", "value": val,
                    "rankable": False, "has_p_value": False,
                }],
            }
            with patch("multiomics_explorer.mcp_server.tools.api.gene_derived_metrics",
                       return_value=envelope):
                ctx = AsyncMock()
                response = await tool_fns["gene_derived_metrics"](
                    ctx, locus_tags=["X"])
            assert response.results[0].value == val

    @pytest.mark.asyncio
    async def test_sparse_extras_default_none(self, tool_fns, envelope_data):
        """Result accepts row dicts with adjusted_p_value/significant absent."""
        from unittest.mock import patch, AsyncMock
        with patch("multiomics_explorer.mcp_server.tools.api.gene_derived_metrics",
                   return_value=envelope_data):
            ctx = AsyncMock()
            response = await tool_fns["gene_derived_metrics"](
                ctx, locus_tags=["X"])
        row = response.results[0]
        assert row.adjusted_p_value is None
        assert row.significant is None
        assert row.p_value is None  # verbose-only, also default None

    @pytest.mark.asyncio
    async def test_summary_empty_results(self, tool_fns, envelope_data):
        from unittest.mock import patch, AsyncMock
        envelope_data["results"] = []
        envelope_data["returned"] = 0
        envelope_data["truncated"] = True
        with patch("multiomics_explorer.mcp_server.tools.api.gene_derived_metrics",
                   return_value=envelope_data):
            ctx = AsyncMock()
            response = await tool_fns["gene_derived_metrics"](
                ctx, locus_tags=["X"], summary=True)
        assert response.results == []
        assert response.truncated is True

    @pytest.mark.asyncio
    async def test_value_error_to_tool_error(self, tool_fns):
        from unittest.mock import patch, AsyncMock
        from fastmcp.exceptions import ToolError
        with patch("multiomics_explorer.mcp_server.tools.api.gene_derived_metrics",
                   side_effect=ValueError("locus_tags must not be empty.")):
            ctx = AsyncMock()
            with pytest.raises(ToolError, match="locus_tags must not be empty"):
                await tool_fns["gene_derived_metrics"](ctx, locus_tags=[])
```

- [ ] **Step 3: Run tests, expect fail (KeyError)**

```bash
uv run pytest tests/unit/test_tool_wrappers.py::TestGeneDerivedMetricsWrapper -v 2>&1 | head -20
```
Expected: `KeyError: 'gene_derived_metrics'` (tool not registered yet).

- [ ] **Step 4: Implement the `@mcp.tool` wrapper**

Find the `gene_clusters_by_gene` `@mcp.tool` definition (~line 3769). Insert the new tool definition immediately after it (still inside `register_tools(mcp)`). Note: the Pydantic models from Tasks 5-6 are already in scope.

```python
    @mcp.tool(
        tags={"derived-metrics", "genes", "batch"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
    )
    async def gene_derived_metrics(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(
            description="Gene locus tags to look up (e.g. ['PMM1714', "
                        "'PMM0001']). Required, non-empty. Single organism "
                        "enforced — locus_tags must all resolve to the same "
                        "organism (or pair with `organism` to disambiguate).",
        )],
        organism: Annotated[str | None, Field(
            description="Organism to scope to. Accepts short strain code "
                        "('MED4', 'NATL2A', 'MIT1002') or full name. "
                        "Case-insensitive substring match. Inferred from "
                        "locus_tags when omitted.",
        )] = None,
        metric_types: Annotated[list[str] | None, Field(
            description="Filter by metric_type tags (e.g. "
                        "'diel_amplitude_protein_log2'). Same metric_type may "
                        "appear across publications — pair with publication_doi "
                        "or use derived_metric_ids to pin one specific DM.",
        )] = None,
        value_kind: Annotated[
            Literal["numeric", "boolean", "categorical"] | None, Field(
                description="Restrict to one DM kind. Each kind has a "
                            "different `value` column type — 'numeric' → "
                            "float, 'boolean' → 'true'/'false', "
                            "'categorical' → category string.",
            )] = None,
        compartment: Annotated[str | None, Field(
            description="Filter to DMs from one sample compartment "
                        "('whole_cell', 'vesicle', 'exoproteome', "
                        "'spent_medium', 'lysate'). Exact match.",
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Treatment type(s) to match. Returns DMs whose "
                        "treatment_type list overlaps ANY of the given "
                        "values. Case-insensitive.",
        )] = None,
        background_factors: Annotated[list[str] | None, Field(
            description="Background experimental factor(s) to match. "
                        "ANY-overlap. Case-insensitive.",
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description="Filter by one or more publication DOIs. Exact match.",
        )] = None,
        derived_metric_ids: Annotated[list[str] | None, Field(
            description="Look up specific DMs by their unique id. Use to "
                        "pin one DM when the same metric_type appears across "
                        "publications. Pair with `list_derived_metrics`.",
        )] = None,
        summary: Annotated[bool, Field(
            description="Return summary fields only (counts, breakdowns, "
                        "not_found / not_matched). Sugar for limit=0; results=[].",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include detailed text fields per row: treatment, "
                        "light_condition, experimental_context, plus raw "
                        "p_value when parent DM has_p_value=True.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max rows to return. Paginate with offset. Use "
                        "`summary=True` for summary-only (sets limit=0 "
                        "internally).",
            ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Pagination offset (starting row, 0-indexed).", ge=0,
        )] = 0,
    ) -> GeneDerivedMetricsResponse:
        """Polymorphic `value` column — branch on `value_kind` per row; consult `list_derived_metrics(value_kind=...)` first to know which DMs exist and whether numeric rows carry rank/percentile/bucket extras (rankable gate) or `adjusted_p_value`/`significant` (has_p_value gate).

        Gene-centric batch lookup for DerivedMetric annotations — one row
        per gene × DM. `value` is `float` on numeric rows, `'true'`/'false'`
        on boolean rows, category string on categorical rows. Numeric extras
        (rank_by_metric, metric_percentile, metric_bucket) are populated
        only when the parent DM is rankable; null otherwise. Same gate for
        adjusted_p_value / significant on has_p_value DMs (none in the
        current KG).

        Single organism enforced. not_found (locus_tag absent from KG) and
        not_matched (in KG but no DM rows after filters — includes
        kind-mismatch when value_kind is set) make empty rows diagnosable.
        For edge-level numeric filters (bucket / percentile / rank / value
        thresholds), pivot to genes_by_numeric_metric.
        """
        await ctx.info(f"gene_derived_metrics locus_tags={locus_tags} "
                       f"organism={organism}")
        try:
            conn = _conn(ctx)
            data = api.gene_derived_metrics(
                locus_tags, organism=organism,
                metric_types=metric_types, value_kind=value_kind,
                compartment=compartment, treatment_type=treatment_type,
                background_factors=background_factors,
                publication_doi=publication_doi,
                derived_metric_ids=derived_metric_ids,
                summary=summary, verbose=verbose,
                limit=limit, offset=offset, conn=conn,
            )
            # Build breakdowns + results into NEW locals (don't mutate data)
            by_value_kind = [GeneDmValueKindBreakdown(**b)
                             for b in data["by_value_kind"]]
            by_metric_type = [GeneDmMetricTypeBreakdown(**b)
                              for b in data["by_metric_type"]]
            by_metric = [GeneDmMetricBreakdown(**b)
                         for b in data["by_metric"]]
            by_compartment = [GeneDmCompartmentBreakdown(**b)
                              for b in data["by_compartment"]]
            by_treatment_type = [GeneDmTreatmentBreakdown(**b)
                                 for b in data["by_treatment_type"]]
            by_background_factors = [GeneDmBackgroundFactorBreakdown(**b)
                                     for b in data["by_background_factors"]]
            by_publication = [GeneDmPublicationBreakdown(**b)
                              for b in data["by_publication"]]
            results = [GeneDerivedMetricsResult(**r) for r in data["results"]]
            response = GeneDerivedMetricsResponse(
                total_matching=data["total_matching"],
                total_derived_metrics=data["total_derived_metrics"],
                genes_with_metrics=data["genes_with_metrics"],
                genes_without_metrics=data["genes_without_metrics"],
                not_found=data["not_found"],
                not_matched=data["not_matched"],
                by_value_kind=by_value_kind,
                by_metric_type=by_metric_type,
                by_metric=by_metric,
                by_compartment=by_compartment,
                by_treatment_type=by_treatment_type,
                by_background_factors=by_background_factors,
                by_publication=by_publication,
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of "
                           f"{response.total_matching} gene×DM rows")
            return response
        except ValueError as e:
            await ctx.warning(f"gene_derived_metrics error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"gene_derived_metrics unexpected error: {e}")
            raise ToolError(f"Error in gene_derived_metrics: {e}")
```

- [ ] **Step 5: Run wrapper tests + EXPECTED_TOOLS test, expect PASS**

```bash
uv run pytest tests/unit/test_tool_wrappers.py::TestGeneDerivedMetricsWrapper tests/unit/test_tool_wrappers.py::TestToolRegistration -v
```
Expected: 5 wrapper tests + 2 registration tests pass.

- [ ] **Step 6: Run all unit tests to confirm no regressions**

```bash
uv run pytest tests/unit/ -v 2>&1 | tail -30
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "feat(mcp): register gene_derived_metrics tool

@mcp.tool wrapper that thin-validates api/ output via Pydantic.
limit ge=1 (cluster precedent). value: float | str polymorphism
verified at the wrapper boundary. EXPECTED_TOOLS updated."
```

---

## Task 8: Integration test — live KG (`@pytest.mark.kg`)

**Files:**
- Modify: `tests/integration/test_mcp_tools.py`

- [ ] **Step 1: Write integration test class**

Append to `tests/integration/test_mcp_tools.py`:

```python
@pytest.mark.kg
class TestGeneDerivedMetrics:
    """Integration tests against live KG. Baselines pinned 2026-04-26."""

    @pytest.mark.asyncio
    async def test_pmm1714_all_three_kinds(self, tool_fns):
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], limit=20)
        assert response.total_matching == 9
        assert response.total_derived_metrics == 9
        assert response.genes_with_metrics == 1
        assert response.returned == 9
        kinds = {r.value_kind for r in response.results}
        assert kinds == {"numeric", "boolean", "categorical"}
        # Polymorphic value typing
        for r in response.results:
            if r.value_kind == "numeric":
                assert isinstance(r.value, float)
            elif r.value_kind == "boolean":
                assert r.value in ("true", "false")
            elif r.value_kind == "categorical":
                assert isinstance(r.value, str)

    @pytest.mark.asyncio
    async def test_pmm0001_diel_only(self, tool_fns):
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM0001"], limit=20)
        assert response.total_matching == 6
        assert all(r.value_kind == "numeric" for r in response.results)
        # 4 rankable (damping_ratio, diel_amp_*, protein_transcript_lag),
        # 2 non-rankable (peak_time_*)
        rankable_count = sum(1 for r in response.results if r.rankable)
        assert rankable_count == 4
        # Sparse extras null on non-rankable rows
        for r in response.results:
            if not r.rankable:
                assert r.rank_by_metric is None
                assert r.metric_percentile is None
                assert r.metric_bucket is None

    @pytest.mark.asyncio
    async def test_value_kind_filter_routes(self, tool_fns):
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], value_kind="boolean")
        assert response.total_matching == 1
        assert response.results[0].metric_type == "vesicle_proteome_member"
        assert response.results[0].value == "true"

    @pytest.mark.asyncio
    async def test_kind_mismatch_not_matched(self, tool_fns):
        """Gene with only boolean DM signal under value_kind='numeric' filter
        lands in not_matched, not silently dropped."""
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMN2A_2128"], value_kind="numeric")
        assert response.total_matching == 0
        assert response.not_matched == ["PMN2A_2128"]
        assert response.genes_without_metrics == 1
        assert response.not_found == []

    @pytest.mark.asyncio
    async def test_not_found_path(self, tool_fns):
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM_DOES_NOT_EXIST"])
        assert response.total_matching == 0
        assert response.not_found == ["PMM_DOES_NOT_EXIST"]
        assert response.not_matched == []
        assert response.genes_without_metrics == 0

    @pytest.mark.asyncio
    async def test_mixed_input_with_filter(self, tool_fns):
        """All 3 diagnostic buckets fire under value_kind='numeric'."""
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714", "PMM_FAKE", "PMN2A_2128"],
            value_kind="numeric", limit=20)
        assert response.total_matching == 7  # PMM1714 numeric only
        assert response.genes_with_metrics == 1
        assert response.genes_without_metrics == 1
        assert response.not_found == ["PMM_FAKE"]
        assert response.not_matched == ["PMN2A_2128"]

    @pytest.mark.asyncio
    async def test_compartment_filter(self, tool_fns):
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], compartment="vesicle", limit=20)
        assert response.total_matching == 3  # boolean + categorical + numeric Biller 2014

    @pytest.mark.asyncio
    async def test_publication_doi_filter(self, tool_fns):
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"],
            publication_doi=["10.1371/journal.pone.0043432"], limit=20)
        assert response.total_matching == 6  # 6 Waldbauer numeric DMs

    @pytest.mark.asyncio
    async def test_summary_only(self, tool_fns):
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], summary=True)
        assert response.results == []
        assert response.truncated is True
        # All by_* keys present (even if empty)
        for breakdown_attr in [
            "by_value_kind", "by_metric_type", "by_metric",
            "by_compartment", "by_treatment_type",
            "by_background_factors", "by_publication",
        ]:
            assert hasattr(response, breakdown_attr)

    @pytest.mark.asyncio
    async def test_by_metric_disambiguates(self, tool_fns):
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], summary=True)
        assert len(response.by_metric) == 9  # one per DM touching the gene
        for entry in response.by_metric:
            assert entry.derived_metric_id  # non-empty
            assert entry.name
            assert entry.metric_type
            assert entry.value_kind in ("numeric", "boolean", "categorical")
            assert entry.count >= 1

    @pytest.mark.asyncio
    async def test_verbose_columns(self, tool_fns):
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], verbose=True, limit=1)
        row = response.results[0]
        # Verbose-only fields populated (treatment, light_condition, etc.)
        assert row.treatment is not None
        assert row.light_condition is not None
        assert row.experimental_context is not None
        # p_value forward-compat — None today
        assert row.p_value is None

    @pytest.mark.asyncio
    async def test_organism_conflict_raises(self, tool_fns):
        from fastmcp.exceptions import ToolError
        ctx = AsyncMock()
        with pytest.raises(ToolError):
            await tool_fns["gene_derived_metrics"](
                ctx, locus_tags=["PMM1714", "PMN2A_2128"])  # MED4 + NATL2A

    @pytest.mark.asyncio
    async def test_truncation(self, tool_fns):
        ctx = AsyncMock()
        response = await tool_fns["gene_derived_metrics"](
            ctx, locus_tags=["PMM1714"], limit=2)
        assert response.returned == 2
        assert response.truncated is True
        assert response.total_matching == 9
```

- [ ] **Step 2: Run integration tests, expect PASS**

```bash
uv run pytest tests/integration/test_mcp_tools.py::TestGeneDerivedMetrics -v -m kg
```
Expected: 13 tests pass against live KG.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_mcp_tools.py
git commit -m "test(integration): add TestGeneDerivedMetrics live-KG tests

13 tests pinned to 2026-04-26 KG state covering: 3-kind gene
(PMM1714), single-kind gene (PMM0001), kind-mismatch path,
not_found, mixed-input diagnostics, compartment/DOI filters,
summary mode, by_metric disambiguation, verbose, organism conflict,
truncation."
```

---

## Task 9: Contract test

**Files:**
- Modify: `tests/integration/test_api_contract.py`

- [ ] **Step 1: Add contract test**

Append to `tests/integration/test_api_contract.py`:

```python
@pytest.mark.kg
class TestGeneDerivedMetricsContract:
    """Pin envelope shape + result keys; fail fast on accidental drift."""

    EXPECTED_ENVELOPE_KEYS = {
        "total_matching", "total_derived_metrics",
        "genes_with_metrics", "genes_without_metrics",
        "not_found", "not_matched",
        "by_value_kind", "by_metric_type", "by_metric",
        "by_compartment", "by_treatment_type",
        "by_background_factors", "by_publication",
        "returned", "offset", "truncated", "results",
    }

    EXPECTED_COMPACT_RESULT_KEYS = {
        "locus_tag", "gene_name", "derived_metric_id", "value_kind",
        "name", "value", "rankable", "has_p_value",
        "rank_by_metric", "metric_percentile", "metric_bucket",
        # adjusted_p_value, significant: deferred from Cypher; not in
        # raw rows today (Pydantic default=None fills them at the wrapper
        # layer)
    }

    EXPECTED_VERBOSE_ADD_KEYS = {
        "metric_type", "field_description", "unit", "allowed_categories",
        "compartment", "treatment_type", "background_factors",
        "publication_doi", "treatment", "light_condition",
        "experimental_context",
        # p_value: deferred — not in raw rows today
    }

    def test_envelope_keys_compact(self):
        data = api.gene_derived_metrics(["PMM1714"], limit=1)
        assert set(data.keys()) == self.EXPECTED_ENVELOPE_KEYS

    def test_compact_result_keys(self):
        data = api.gene_derived_metrics(["PMM1714"], limit=1)
        assert len(data["results"]) >= 1
        assert set(data["results"][0].keys()) == self.EXPECTED_COMPACT_RESULT_KEYS

    def test_verbose_result_keys(self):
        data = api.gene_derived_metrics(["PMM1714"], limit=1, verbose=True)
        expected = self.EXPECTED_COMPACT_RESULT_KEYS | self.EXPECTED_VERBOSE_ADD_KEYS
        assert set(data["results"][0].keys()) == expected
```

- [ ] **Step 2: Run, expect PASS**

```bash
uv run pytest tests/integration/test_api_contract.py::TestGeneDerivedMetricsContract -v -m kg
```
Expected: 3 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_api_contract.py
git commit -m "test(contract): pin gene_derived_metrics envelope + result keys

Locks in the 17-key envelope and the 11-key compact / 22-key
verbose result schema. Fails fast on accidental shape drift."
```

---

## Task 10: Regression + eval registration

**Files:**
- Modify: `tests/regression/test_regression.py`
- Modify: `tests/evals/test_eval.py`
- Modify: `tests/evals/cases.yaml`

- [ ] **Step 1: Add to regression `TOOL_BUILDERS`**

In `tests/regression/test_regression.py` line 49, add to the `TOOL_BUILDERS` dict (placement: after `list_derived_metrics`):

```python
TOOL_BUILDERS = {
    ...,
    "list_derived_metrics": build_list_derived_metrics,
    "list_derived_metrics_summary": build_list_derived_metrics_summary,
    "gene_derived_metrics": build_gene_derived_metrics,
    "gene_derived_metrics_summary": build_gene_derived_metrics_summary,
    ...,
}
```

Update the import block at the top of the file:

```python
from multiomics_explorer.kg.queries_lib import (
    ...,
    build_gene_derived_metrics,
    build_gene_derived_metrics_summary,
)
```

- [ ] **Step 2: Add to eval `TOOL_BUILDERS`**

Same additions to `tests/evals/test_eval.py` line 56 — separate dict.

- [ ] **Step 3: Add cases to `tests/evals/cases.yaml`**

Append:

```yaml
- id: gene_derived_metrics_pmm1714_all_kinds
  tool: gene_derived_metrics
  desc: PMM1714 has all 3 DM kinds (boolean + categorical + numeric)
  params:
    locus_tags: ["PMM1714"]
  expect:
    min_rows: 9
    columns:
      - locus_tag
      - derived_metric_id
      - value_kind
      - value
      - rankable

- id: gene_derived_metrics_kind_mismatch
  tool: gene_derived_metrics
  desc: NATL2A boolean-only gene under value_kind='numeric' lands in not_matched
  params:
    locus_tags: ["PMN2A_2128"]
    value_kind: numeric
  expect:
    min_rows: 0
    columns: []

- id: gene_derived_metrics_summary
  tool: gene_derived_metrics
  desc: Summary mode for mixed-input batch
  params:
    locus_tags: ["PMM1714", "PMM0001"]
    summary: true
  expect:
    min_rows: 0
    columns: []
```

- [ ] **Step 4: Regenerate regression baselines**

```bash
uv run pytest tests/regression/ --force-regen -m kg 2>&1 | tail -10
```
Expected: golden files written under `tests/regression/test_regression/`.

- [ ] **Step 5: Verify regression passes against new baselines**

```bash
uv run pytest tests/regression/ -m kg
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/regression/test_regression.py tests/evals/test_eval.py \
        tests/evals/cases.yaml \
        tests/regression/test_regression/
git commit -m "test(regression): register gene_derived_metrics builders

Both TOOL_BUILDERS dicts (regression + eval) updated. 3 cases.yaml
entries cover the 3-kind happy path, kind-mismatch, and summary mode.
Regression baselines regenerated."
```

---

## Task 11: About content YAML

**Files:**
- Create: `multiomics_explorer/inputs/tools/gene_derived_metrics.yaml`

- [ ] **Step 1: Create the YAML file**

```yaml
# Human-authored content for gene_derived_metrics about page.
# Auto-generated sections (params, response format, expected-keys)
# come from Pydantic models via scripts/build_about_content.py.

examples:
  - title: Gene with all three DM kinds (boolean + categorical + numeric)
    call: gene_derived_metrics(locus_tags=["PMM1714"])

  - title: Mixed-input summary — surfaces by_metric, not_found, not_matched
    call: gene_derived_metrics(locus_tags=["PMM1714", "PMM0001", "PMM_FAKE"], summary=True)

  - title: Kind-filter routing — only boolean DM signal
    call: gene_derived_metrics(locus_tags=["PMM1714"], value_kind="boolean")

  - title: Compartment routing — only vesicle DMs for this gene
    call: gene_derived_metrics(locus_tags=["PMM1714"], compartment="vesicle")

  - title: DE → DM annotation chain
    steps: |
      Step 1: differential_expression_by_gene(experiment_ids=[...], significant_only=True)
              → extract top hits' locus_tags

      Step 2: gene_derived_metrics(locus_tags=top_hits)
              → see which hits have rhythmicity flags / vesicle membership / damping rank

      Step 3 (drill-down): genes_by_numeric_metric(
                derived_metric_ids=["derived_metric:...:damping_ratio"],
                bucket=["top_decile"])
              → top-decile damped genes; intersect with DE top hits

verbose_fields:
  - metric_type
  - field_description
  - unit
  - allowed_categories
  - compartment
  - treatment_type
  - background_factors
  - publication_doi
  - treatment
  - light_condition
  - experimental_context
  - p_value

chaining:
  - "gene_derived_metrics → genes_by_numeric_metric(derived_metric_ids, bucket=[...])"
  - "differential_expression_by_gene → gene_derived_metrics(locus_tags)"
  - "resolve_gene → gene_derived_metrics(locus_tags)"

mistakes:
  - >-
    The `value` column is polymorphic — branch on each row's `value_kind`
    (`'numeric'` → float, `'boolean'` → `'true'`/`'false'` string,
    `'categorical'` → category string). Numeric rows additionally have
    `rank_by_metric`, `metric_percentile`, `metric_bucket` populated when
    their parent DM is rankable; null otherwise (e.g. `peak_time_protein_h`).
  - >-
    For numeric edge filtering (bucket / percentile / rank / value
    thresholds), pivot to `genes_by_numeric_metric`. This tool intentionally
    has no edge-level numeric filters — it is the gene-anchor surface only.
  - >-
    `not_matched` ≠ no DM signal at all. `not_matched` lists genes that
    exist in the KG but have zero DM rows AFTER the applied filters. A
    gene with only boolean DM signal called with `value_kind='numeric'`
    lands in `not_matched`. Inspect rollup props
    (`g.numeric_metric_count` etc. via `gene_overview`) for unfiltered
    availability.
  - >-
    Single organism enforced. Mixing locus_tags from MED4 and NATL2A
    raises `ValueError`. Call once per organism.
  - wrong: gene_derived_metrics(locus_tags=["PMM1714"], min_value=1.0)
    right: First call gene_derived_metrics(locus_tags=["PMM1714"]); then
      pivot to genes_by_numeric_metric(derived_metric_ids=[...], min_value=1.0)
  - wrong: gene_derived_metrics(locus_tags=[])
    right: locus_tags must be non-empty (raises ValueError).
```

- [ ] **Step 2: Generate about markdown**

```bash
uv run python scripts/build_about_content.py gene_derived_metrics
```
Expected: writes `multiomics_explorer/skills/multiomics-kg-guide/references/tools/gene_derived_metrics.md` directly.

- [ ] **Step 3: Run about-content tests**

```bash
uv run pytest tests/unit/test_about_content.py -v
uv run pytest tests/integration/test_about_examples.py -v -m kg
```
Expected: all tests pass (Pydantic ↔ generated md consistency; YAML examples execute).

- [ ] **Step 4: Commit**

```bash
git add multiomics_explorer/inputs/tools/gene_derived_metrics.yaml \
        multiomics_explorer/skills/multiomics-kg-guide/references/tools/gene_derived_metrics.md
git commit -m "docs(skill): add gene_derived_metrics about content

YAML with 5 examples, 3-step DE→DM chain, 6 mistakes covering
polymorphic value, drill-down pivot, not_matched semantics, and
single-organism enforcement. Generated about md via
scripts/build_about_content.py."
```

---

## Task 12: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add row to the MCP Tools table**

Find the table in `CLAUDE.md` under `## MCP Server > ### Tools`. Insert a row for `gene_derived_metrics` near `gene_clusters_by_gene`:

```markdown
| `gene_derived_metrics` | Gene-centric batch lookup for DerivedMetric annotations across numeric / boolean / categorical kinds. One row per gene × DM with polymorphic `value` column. Single organism enforced. Reports `not_found` / `not_matched` (kind-mismatch) for diagnosability. Pivots to `genes_by_{kind}_metric` for edge-level numeric filtering. |
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): add gene_derived_metrics to MCP Tools table"
```

---

## Task 13: Final code review pass

- [ ] **Step 1: Run code-review skill against the diff**

```bash
git log --oneline main..HEAD
git diff main...HEAD --stat
```
Expected: ~12-13 commits across 4 layers + tests + docs, ~1500-2000 LoC added.

- [ ] **Step 2: Walk through the code-review checklist**

Reference: `.claude/skills/code-review/SKILL.md`. For each layer:

- **Query builders.** Match `add-or-update-tool/references/checklist.md` Layer 1 conventions: kw-only args, `$param` placeholders, `AS snake_case`, `ORDER BY` present, no execution / no formatting / no upper-layer imports.
- **API.** Layer 2 conventions: assembles complete dict, accepts summary/verbose/limit/conn, validates inputs (`ValueError`), `_default_conn` used.
- **MCP wrapper.** Layer 3 conventions: thin wrapper, `Annotated[type, Field(description=...)]`, `Literal[...]` where appropriate, `ToolError` not strings, `async def` + `await ctx.info`, no field computation, doesn't mutate api/ dict.
- **Skills (about content).** Layer 4 conventions: YAML drives generated md; `verbose_fields` separates the per-result table; examples executable.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest tests/unit/ tests/integration/ -v -m "not kg" 2>&1 | tail -10
uv run pytest tests/ -v -m kg 2>&1 | tail -10
```
Expected: all green.

- [ ] **Step 4: Smoke-test through MCP**

Restart the MCP server (per `feedback_mcp_restart` workflow):

```bash
# In Claude Code: /mcp restart
```

Then test the tool via Claude Code MCP tool call:
```
Use mcp__multiomics-kg__gene_derived_metrics with locus_tags=["PMM1714"]
```
Expected: 9 rows returned, polymorphic `value` rendered correctly across kinds.

- [ ] **Step 5: Final commit (if any tweaks)**

```bash
git add -A
git commit -m "chore: post-review cleanup for gene_derived_metrics"  # only if needed
```

- [ ] **Step 6: Push and open PR (optional, per user preference)**

```bash
git push -u origin <branch-name>
# Or merge to main if working directly there.
```

---

## Self-review checks (against the spec)

**Spec coverage** — each spec section maps to a task:

- §Purpose / Use cases / Out of scope → captured in Task 11 YAML examples / mistakes.
- §Status / Prerequisites → assumed from spec sign-off; KG cleanup pre-flight noted.
- §KG dependencies → Cypher in Tasks 1-2 references the post-rebuild `r.value`; CASE-gating on `dm.rankable = 'true'`.
- §Refreshed live-KG baselines → integration test counts (Task 8) + cases.yaml (Task 10) pin to today's numbers.
- §Tool Signature → Task 7 `@mcp.tool` body.
- §Result-size controls (envelope + compact + verbose + sort key + value polymorphism) → Tasks 1, 2, 3, 6, 7.
- §Special handling (compartment exact-match, polymorphic r.value, defensive CASE-gating, organism enforcement, empty locus_tags, summary shortcut, p_value forward-compat, sparse-column shape) → covered across Tasks 1-3, 6, 7.
- §Query Builder → Tasks 1, 2.
- §API Function → Task 3.
- §MCP Wrapper → Tasks 5-7.
- §Tests (unit / integration / contract / correctness / regression / about) → Tasks 1, 2, 3, 7, 8, 9, 10, 11.
- §About Content → Task 11.
- §Implementation Order → matches this plan's task numbering.

**Placeholder scan:** none — every step has concrete code, exact paths, exact commands.

**Type consistency:**
- `build_gene_derived_metrics_summary` returns `tuple[str, dict]`; api/ unpacks `(cypher, params)` and passes via `**params`. ✓
- `gene_derived_metrics` (api) returns `dict`; MCP wrapper instantiates `GeneDerivedMetricsResponse(**...)` from it. ✓
- `value: float | str` consistent across api row → Pydantic Result. ✓
- `rankable`, `has_p_value` are Python `bool` everywhere (Cypher coerces via `dm.rankable = 'true' AS rankable`). ✓
- 7 breakdown class names match across Pydantic, response field annotations, and wrapper-body instantiations. ✓
- `EXPECTED_TOOLS` updated in test file; `TOOL_BUILDERS` updated in both regression and eval files. ✓

**Spec requirement with no task:** none found.

---

**Plan complete.** Saved to `docs/superpowers/plans/2026-04-26-gene-derived-metrics.md`.
