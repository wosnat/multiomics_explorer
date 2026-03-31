# Gene Cluster MCP Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three MCP tools for querying GeneCluster nodes: `list_gene_clusters` (search/browse/filter), `gene_clusters_by_gene` (batch gene lookup), and `genes_in_cluster` (drill into members).

**Architecture:** Three tools across the standard 4-layer stack (query builders → API functions → MCP wrappers → about content). Shared `_gene_cluster_where` helper for common filters. Publication filter requires conditional MATCH pattern. Full-text search uses `geneClusterFullText` index. Single-organism enforcement on tools 2 and 3 via existing `_validate_organism_inputs`.

**Tech Stack:** Python, Neo4j Cypher, Pydantic, FastMCP, pytest

**Spec:** `docs/superpowers/specs/2026-03-31-gene-cluster-mcp-tools-design.md`

**Review Checkpoints:** Use `/code-review` after each review gate. Reference `/testing` for per-layer test patterns. Reference `/layer-rules` for architecture conventions.

**Test layers (see `/testing` skill):**
- `test_query_builders.py` — Cypher structure + params (no Neo4j)
- `test_api_functions.py` — API logic with mocked conn (no Neo4j)
- `test_tool_wrappers.py` — MCP wrapper Pydantic models + ToolError (no Neo4j)
- `test_about_content.py` — About-file consistency with Pydantic schemas (no Neo4j)
- `test_api_contract.py` — API return-type contracts (Neo4j required)
- `test_cyver_queries.py` — CyVer schema validation of builders (Neo4j required, auto-discovers)
- `test_regression.py` — Golden-file comparison (Neo4j required)

## Task Order and Review Gates

| # | Task | Description |
|---|---|---|
| 1 | Query builders: list_gene_clusters | WHERE helper + summary + detail builders with unit tests |
| 2 | API: list_gene_clusters | API function with unit tests |
| 3 | MCP wrapper: list_gene_clusters | Pydantic models + wrapper with unit tests |
| | **REVIEW GATE A** | **First tool end-to-end. Review all 3 layers.** |
| 4 | Query builders: gene_clusters_by_gene | Summary + detail + diagnostics builders with unit tests |
| 5 | API: gene_clusters_by_gene | API function with single-organism enforcement, unit tests |
| 6 | MCP wrapper: gene_clusters_by_gene | Pydantic models + wrapper with unit tests |
| | **REVIEW GATE B** | **Gene-centric tool. Review batch diagnostics and organism enforcement.** |
| 7 | Query builders: genes_in_cluster | Summary + detail builders with unit tests |
| 8 | API: genes_in_cluster | API function with unit tests |
| 9 | MCP wrapper: genes_in_cluster | Pydantic models + wrapper with unit tests |
| | **REVIEW GATE C** | **All 3 tools complete. Review full changeset.** |
| 10 | About content | Input YAML + build for all 3 tools |
| 11 | Integration tests + docs | Contract tests, CLAUDE.md update |
| | **REVIEW GATE D** | **Final review before merge.** |

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `multiomics_explorer/kg/queries_lib.py` | Add `_gene_cluster_where`, 6 builder functions |
| Modify | `multiomics_explorer/api/functions.py` | Add 3 API functions |
| Modify | `multiomics_explorer/api/__init__.py` | Re-export 3 new functions |
| Modify | `multiomics_explorer/mcp_server/tools.py` | Add Pydantic models + 3 tool wrappers |
| Modify | `tests/unit/test_query_builders.py` | Add tests for 6 builders |
| Modify | `tests/unit/test_api_functions.py` | Add tests for 3 API functions |
| Modify | `tests/unit/test_tool_wrappers.py` | Add tests for 3 wrappers |
| Modify | `tests/integration/test_api_contract.py` | Add contract tests for 3 functions |
| Create | `multiomics_explorer/inputs/tools/list_gene_clusters.yaml` | Human-authored about content |
| Create | `multiomics_explorer/inputs/tools/gene_clusters_by_gene.yaml` | Human-authored about content |
| Create | `multiomics_explorer/inputs/tools/genes_in_cluster.yaml` | Human-authored about content |
| Modify | `CLAUDE.md` | Add 3 tools to tool table |

---

### Task 1: Query builders — list_gene_clusters

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py`
- Modify: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for `_gene_cluster_where` helper**

Append to `tests/unit/test_query_builders.py`:

```python
class TestGeneClusterWhere:
    """Tests for _gene_cluster_where shared helper."""

    def test_no_filters(self):
        from multiomics_explorer.kg.queries_lib import _gene_cluster_where
        conditions, params = _gene_cluster_where()
        assert conditions == []
        assert params == {}

    def test_organism_filter(self):
        from multiomics_explorer.kg.queries_lib import _gene_cluster_where
        conditions, params = _gene_cluster_where(organism="MED4")
        assert len(conditions) == 1
        assert "organism_name" in conditions[0].lower() or "organism" in conditions[0].lower()
        assert params["organism"] == "MED4"

    def test_cluster_type_filter(self):
        from multiomics_explorer.kg.queries_lib import _gene_cluster_where
        conditions, params = _gene_cluster_where(cluster_type="stress_response")
        assert len(conditions) == 1
        assert "$cluster_type" in conditions[0]
        assert params["cluster_type"] == "stress_response"

    def test_treatment_type_filter(self):
        from multiomics_explorer.kg.queries_lib import _gene_cluster_where
        conditions, params = _gene_cluster_where(treatment_type=["nitrogen_stress"])
        assert len(conditions) == 1
        assert "$treatment_type" in conditions[0]
        assert params["treatment_type"] == ["nitrogen_stress"]

    def test_omics_type_filter(self):
        from multiomics_explorer.kg.queries_lib import _gene_cluster_where
        conditions, params = _gene_cluster_where(omics_type="MICROARRAY")
        assert len(conditions) == 1
        assert "$omics_type" in conditions[0]
        assert params["omics_type"] == "MICROARRAY"

    def test_combined_filters(self):
        from multiomics_explorer.kg.queries_lib import _gene_cluster_where
        conditions, params = _gene_cluster_where(
            organism="MED4", cluster_type="stress_response",
            treatment_type=["nitrogen_stress"], omics_type="MICROARRAY",
        )
        assert len(conditions) == 4
        assert len(params) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_query_builders.py::TestGeneClusterWhere -v
```
Expected: FAIL — `_gene_cluster_where` not defined.

- [ ] **Step 3: Implement `_gene_cluster_where`**

Add to `multiomics_explorer/kg/queries_lib.py` near the other `_*_where` helpers:

```python
def _gene_cluster_where(
    *,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
) -> tuple[list[str], dict]:
    """Build GeneCluster filter conditions + params shared by gene cluster builders."""
    conditions: list[str] = []
    params: dict = {}
    if organism is not None:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(gc.organism_name) CONTAINS word)"
        )
        params["organism"] = organism
    if cluster_type is not None:
        conditions.append("gc.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        conditions.append(
            "ANY(tt IN gc.treatment_type WHERE tt IN $treatment_type)"
        )
        params["treatment_type"] = treatment_type
    if omics_type is not None:
        conditions.append("gc.omics_type = $omics_type")
        params["omics_type"] = omics_type
    return conditions, params
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_query_builders.py::TestGeneClusterWhere -v
```
Expected: ALL PASS.

- [ ] **Step 5: Write failing tests for `build_list_gene_clusters_summary`**

Append to `tests/unit/test_query_builders.py`:

```python
class TestBuildListGeneClustersSummary:
    """Tests for build_list_gene_clusters_summary."""

    def test_no_search_no_filters(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters_summary
        cypher, params = build_list_gene_clusters_summary()
        assert "GeneCluster" in cypher
        assert "total_entries" in cypher
        assert "total_matching" in cypher
        assert "by_organism" in cypher
        assert "by_cluster_type" in cypher
        assert "by_treatment_type" in cypher
        assert "by_omics_type" in cypher
        assert "WHERE" not in cypher

    def test_with_search_text(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters_summary
        cypher, params = build_list_gene_clusters_summary(search_text="photosynthesis")
        assert "geneClusterFullText" in cypher
        assert params["search_text"] == "photosynthesis"
        assert "score_max" in cypher
        assert "score_median" in cypher

    def test_with_organism_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters_summary
        cypher, params = build_list_gene_clusters_summary(organism="MED4")
        assert "WHERE" in cypher
        assert params["organism"] == "MED4"

    def test_with_publication_doi_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters_summary
        cypher, params = build_list_gene_clusters_summary(
            publication_doi=["10.1038/msb4100087"])
        assert "Publication_has_gene_cluster" in cypher
        assert params["publication_doi"] == ["10.1038/msb4100087"]
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListGeneClustersSummary -v
```
Expected: FAIL — `build_list_gene_clusters_summary` not defined.

- [ ] **Step 7: Implement `build_list_gene_clusters_summary`**

Add to `multiomics_explorer/kg/queries_lib.py`:

```python
def build_list_gene_clusters_summary(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    publication_doi: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for list_gene_clusters.

    RETURN keys: total_entries, total_matching, by_organism,
    by_cluster_type, by_treatment_type, by_omics_type, by_publication.
    When search_text: adds score_max, score_median.
    """
    conditions, params = _gene_cluster_where(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, omics_type=omics_type,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('geneClusterFullText', $search_text)\n"
            "YIELD node AS gc, score\n"
        )
        score_cols = (
            ",\n     max(score) AS score_max"
            ",\n     percentileDisc(score, 0.5) AS score_median"
        )
        score_return = ", score_max, score_median"
    else:
        match_block = "MATCH (gc:GeneCluster)\n"
        score_cols = ""
        score_return = ""

    if publication_doi is not None:
        match_block += "MATCH (pub:Publication)-[:Publication_has_gene_cluster]->(gc)\n"
        conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "OPTIONAL MATCH (pub2:Publication)-[:Publication_has_gene_cluster]->(gc)\n"
        "WITH gc, collect(DISTINCT pub2.doi) AS pub_dois\n"
        "WITH collect(gc.organism_name) AS organisms,\n"
        "     collect(gc.cluster_type) AS cluster_types,\n"
        "     apoc.coll.flatten(collect(gc.treatment_type)) AS treatment_types,\n"
        "     collect(gc.omics_type) AS omics_types,\n"
        "     apoc.coll.flatten(collect(pub_dois)) AS pub_doi_list,\n"
        f"     count(gc) AS total_matching{score_cols}\n"
        "CALL { MATCH (all_gc:GeneCluster) RETURN count(all_gc) AS total_entries }\n"
        "RETURN total_entries, total_matching,\n"
        "       apoc.coll.frequencies(organisms) AS by_organism,\n"
        "       apoc.coll.frequencies(cluster_types) AS by_cluster_type,\n"
        "       apoc.coll.frequencies(treatment_types) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(omics_types) AS by_omics_type,\n"
        f"       apoc.coll.frequencies(pub_doi_list) AS by_publication{score_return}"
    )
    return cypher, params
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListGeneClustersSummary -v
```
Expected: ALL PASS.

- [ ] **Step 9: Write failing tests for `build_list_gene_clusters`**

Append to `tests/unit/test_query_builders.py`:

```python
class TestBuildListGeneClusters:
    """Tests for build_list_gene_clusters (detail builder)."""

    def test_no_search_returns_expected_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters
        cypher, params = build_list_gene_clusters()
        for col in ["cluster_id", "name", "organism_name", "cluster_type",
                     "treatment_type", "member_count", "source_paper"]:
            assert f"AS {col}" in cypher
        assert "score" not in cypher

    def test_with_search_text(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters
        cypher, params = build_list_gene_clusters(search_text="nitrogen")
        assert "geneClusterFullText" in cypher
        assert "score" in cypher
        assert params["search_text"] == "nitrogen"

    def test_verbose_adds_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters
        cypher, params = build_list_gene_clusters(verbose=True)
        for col in ["functional_description", "behavioral_description",
                     "cluster_method", "treatment", "light_condition",
                     "experimental_context"]:
            assert f"AS {col}" in cypher

    def test_verbose_false_omits_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters
        cypher, params = build_list_gene_clusters(verbose=False)
        assert "functional_description" not in cypher
        assert "behavioral_description" not in cypher

    def test_offset_emits_skip(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters
        cypher, params = build_list_gene_clusters(limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5

    def test_offset_zero_no_skip(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters
        cypher, params = build_list_gene_clusters(limit=10, offset=0)
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_publication_doi_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters
        cypher, params = build_list_gene_clusters(
            publication_doi=["10.1038/msb4100087"])
        assert "Publication_has_gene_cluster" in cypher
        assert params["publication_doi"] == ["10.1038/msb4100087"]

    def test_has_order_by(self):
        from multiomics_explorer.kg.queries_lib import build_list_gene_clusters
        cypher, _ = build_list_gene_clusters()
        assert "ORDER BY" in cypher
```

- [ ] **Step 10: Run tests to verify they fail**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListGeneClusters -v
```
Expected: FAIL — `build_list_gene_clusters` not defined.

- [ ] **Step 11: Implement `build_list_gene_clusters`**

Add to `multiomics_explorer/kg/queries_lib.py`:

```python
def build_list_gene_clusters(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    publication_doi: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for list_gene_clusters.

    RETURN keys (compact): cluster_id, name, organism_name, cluster_type,
    treatment_type, member_count, source_paper.
    When search_text: adds score.
    RETURN keys (verbose): adds functional_description, behavioral_description,
    cluster_method, treatment, light_condition, experimental_context,
    peak_time_hours, period_hours, publication_doi.
    """
    conditions, params = _gene_cluster_where(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, omics_type=omics_type,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('geneClusterFullText', $search_text)\n"
            "YIELD node AS gc, score\n"
        )
        score_col = ",\n       score"
        order_prefix = "score DESC, "
    else:
        match_block = "MATCH (gc:GeneCluster)\n"
        score_col = ""
        order_prefix = ""

    if publication_doi is not None:
        match_block += "MATCH (pub:Publication)-[:Publication_has_gene_cluster]->(gc)\n"
        conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       gc.functional_description AS functional_description"
            ",\n       gc.behavioral_description AS behavioral_description"
            ",\n       gc.cluster_method AS cluster_method"
            ",\n       gc.treatment AS treatment"
            ",\n       gc.light_condition AS light_condition"
            ",\n       gc.experimental_context AS experimental_context"
            ",\n       gc.peak_time_hours AS peak_time_hours"
            ",\n       gc.period_hours AS period_hours"
        )
        # Add publication DOI via optional match if not already joined
        if publication_doi is None:
            verbose_cols += (
                ",\n       pub_doi"
            )
            # Need to collect pub DOI before RETURN
            pub_collect = (
                "OPTIONAL MATCH (pub_v:Publication)-[:Publication_has_gene_cluster]->(gc)\n"
                "WITH gc, score, head(collect(pub_v.doi)) AS pub_doi\n"
                if search_text is not None else
                "OPTIONAL MATCH (pub_v:Publication)-[:Publication_has_gene_cluster]->(gc)\n"
                "WITH gc, head(collect(pub_v.doi)) AS pub_doi\n"
            )
        else:
            verbose_cols += ",\n       pub.doi AS pub_doi"
            pub_collect = ""
    else:
        pub_collect = ""

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
        f"{match_block}"
        f"{where_block}"
        f"{pub_collect}"
        "RETURN gc.id AS cluster_id, gc.name AS name,\n"
        "       gc.organism_name AS organism_name,\n"
        "       gc.cluster_type AS cluster_type,\n"
        "       gc.treatment_type AS treatment_type,\n"
        "       gc.member_count AS member_count,\n"
        f"       gc.source_paper AS source_paper{score_col}{verbose_cols}\n"
        f"ORDER BY {order_prefix}gc.organism_name, gc.name{skip_clause}{limit_clause}"
    )
    return cypher, params
```

- [ ] **Step 12: Run tests to verify they pass**

```bash
pytest tests/unit/test_query_builders.py::TestBuildListGeneClusters -v
```
Expected: ALL PASS.

- [ ] **Step 13: Run all query builder tests to check no regressions**

```bash
pytest tests/unit/test_query_builders.py -v
```
Expected: ALL PASS.

- [ ] **Step 14: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(query): add list_gene_clusters builders with shared WHERE helper"
```

---

### Task 2: API function — list_gene_clusters

**Files:**
- Modify: `multiomics_explorer/api/functions.py`
- Modify: `multiomics_explorer/api/__init__.py`
- Modify: `tests/unit/test_api_functions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_api_functions.py`:

```python
class TestListGeneClusters:
    """Tests for list_gene_clusters API function."""

    _SUMMARY_RESULT = {
        "total_entries": 16, "total_matching": 9,
        "by_organism": [{"item": "Prochlorococcus MED4", "count": 9}],
        "by_cluster_type": [{"item": "stress_response", "count": 9}],
        "by_treatment_type": [{"item": "nitrogen_stress", "count": 9}],
        "by_omics_type": [{"item": "MICROARRAY", "count": 9}],
        "by_publication": [{"item": "10.1038/msb4100087", "count": 9}],
    }

    _SUMMARY_RESULT_WITH_SCORE = {
        **_SUMMARY_RESULT,
        "score_max": 5.2, "score_median": 2.1,
    }

    _DETAIL_ROW = {
        "cluster_id": "cluster:msb4100087:med4:up_n_transport",
        "name": "MED4 cluster 1 (up, N transport)",
        "organism_name": "Prochlorococcus MED4",
        "cluster_type": "stress_response",
        "treatment_type": ["nitrogen_stress"],
        "member_count": 5,
        "source_paper": "Tolonen 2006",
    }

    def test_returns_dict_with_envelope(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT],
            [self._DETAIL_ROW],
        ]
        result = api.list_gene_clusters(conn=mock_conn)
        assert isinstance(result, dict)
        assert result["total_entries"] == 16
        assert result["total_matching"] == 9
        assert result["returned"] == 1
        assert len(result["results"]) == 1
        assert result["by_organism"][0]["organism_name"] == "Prochlorococcus MED4"

    def test_summary_mode_skips_detail(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT],
        ]
        result = api.list_gene_clusters(summary=True, conn=mock_conn)
        assert result["returned"] == 0
        assert result["results"] == []
        assert mock_conn.execute_query.call_count == 1

    def test_search_text_adds_score_fields(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT_WITH_SCORE],
            [{**self._DETAIL_ROW, "score": 5.2}],
        ]
        result = api.list_gene_clusters(
            search_text="nitrogen", conn=mock_conn)
        assert result["score_max"] == 5.2
        assert result["score_median"] == 2.1

    def test_empty_search_text_raises(self, mock_conn):
        with pytest.raises(ValueError, match="search_text must not be empty"):
            api.list_gene_clusters(search_text="", conn=mock_conn)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_api_functions.py::TestListGeneClusters -v
```
Expected: FAIL — `list_gene_clusters` not defined.

- [ ] **Step 3: Add builder imports to `api/functions.py`**

Add to the imports block in `multiomics_explorer/api/functions.py`:

```python
from multiomics_explorer.kg.queries_lib import (
    # ... existing imports ...
    build_list_gene_clusters,
    build_list_gene_clusters_summary,
)
```

- [ ] **Step 4: Implement `list_gene_clusters`**

Add to `multiomics_explorer/api/functions.py`:

```python
def list_gene_clusters(
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    publication_doi: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Browse, search, and filter gene clusters.

    Returns dict with keys: total_entries, total_matching,
    by_organism, by_cluster_type, by_treatment_type, by_omics_type,
    by_publication, returned, offset, truncated, results.
    When search_text provided: adds score_max, score_median.
    Per result (compact): cluster_id, name, organism_name, cluster_type,
    treatment_type, member_count, source_paper, score (when searching).
    Per result (verbose): adds functional_description, behavioral_description,
    cluster_method, treatment, light_condition, experimental_context,
    peak_time_hours, period_hours, pub_doi.

    summary=True: results=[], summary fields only.
    """
    if search_text is not None and not search_text.strip():
        raise ValueError("search_text must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    filter_kwargs = dict(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, omics_type=omics_type,
        publication_doi=publication_doi,
    )

    effective_text = search_text

    # Summary query — always runs
    try:
        sum_cypher, sum_params = build_list_gene_clusters_summary(
            search_text=effective_text, **filter_kwargs)
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
    except Neo4jClientError:
        if search_text is not None:
            logger.debug("list_gene_clusters: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            sum_cypher, sum_params = build_list_gene_clusters_summary(
                search_text=effective_text, **filter_kwargs)
            raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
        else:
            raise

    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_entries": raw_summary["total_entries"],
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_cluster_type": _rename_freq(
            raw_summary["by_cluster_type"], "cluster_type"),
        "by_treatment_type": _rename_freq(
            raw_summary["by_treatment_type"], "treatment_type"),
        "by_omics_type": _rename_freq(raw_summary["by_omics_type"], "omics_type"),
        "by_publication": _rename_freq(
            raw_summary["by_publication"], "publication_doi"),
    }

    if search_text is not None:
        envelope["score_max"] = raw_summary.get("score_max")
        envelope["score_median"] = raw_summary.get("score_median")

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    try:
        det_cypher, det_params = build_list_gene_clusters(
            search_text=effective_text, **filter_kwargs,
            verbose=verbose, limit=limit, offset=offset)
        results = conn.execute_query(det_cypher, **det_params)
    except Neo4jClientError:
        if search_text is not None and effective_text == search_text:
            logger.debug("list_gene_clusters detail: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            det_cypher, det_params = build_list_gene_clusters(
                search_text=effective_text, **filter_kwargs,
                verbose=verbose, limit=limit, offset=offset)
            results = conn.execute_query(det_cypher, **det_params)
        else:
            raise

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope
```

- [ ] **Step 5: Add to `api/__init__.py`**

Add `list_gene_clusters` to both the import and `__all__` in `multiomics_explorer/api/__init__.py`.

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/unit/test_api_functions.py::TestListGeneClusters -v
```
Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/api/__init__.py tests/unit/test_api_functions.py
git commit -m "feat(api): add list_gene_clusters function"
```

---

### Task 3: MCP wrapper — list_gene_clusters

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Modify: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_tool_wrappers.py`:

```python
class TestListGeneClustersWrapper:
    """Tests for list_gene_clusters MCP wrapper."""

    _SAMPLE_API_RETURN = {
        "total_entries": 16,
        "total_matching": 9,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 9}],
        "by_cluster_type": [{"cluster_type": "stress_response", "count": 9}],
        "by_treatment_type": [{"treatment_type": "nitrogen_stress", "count": 9}],
        "by_omics_type": [{"omics_type": "MICROARRAY", "count": 9}],
        "by_publication": [{"publication_doi": "10.1038/msb4100087", "count": 9}],
        "returned": 1,
        "offset": 0,
        "truncated": True,
        "results": [
            {"cluster_id": "cluster:msb4100087:med4:up_n_transport",
             "name": "MED4 cluster 1 (up, N transport)",
             "organism_name": "Prochlorococcus MED4",
             "cluster_type": "stress_response",
             "treatment_type": ["nitrogen_stress"],
             "member_count": 5,
             "source_paper": "Tolonen 2006"},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_gene_clusters",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_gene_clusters"](mock_ctx)
        assert result.total_entries == 16
        assert result.total_matching == 9
        assert result.returned == 1
        assert len(result.results) == 1
        assert result.results[0].cluster_id == "cluster:msb4100087:med4:up_n_transport"

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_gene_clusters",
            side_effect=ValueError("search_text must not be empty"),
        ):
            with pytest.raises(ToolError, match="search_text must not be empty"):
                await tool_fns["list_gene_clusters"](
                    mock_ctx, search_text="")

    @pytest.mark.asyncio
    async def test_params_forwarded(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_gene_clusters",
            return_value=self._SAMPLE_API_RETURN,
        ) as mock_api:
            await tool_fns["list_gene_clusters"](
                mock_ctx, search_text="nitrogen",
                organism="MED4", cluster_type="stress_response",
                summary=True, verbose=True, limit=10,
            )
        mock_api.assert_called_once()
        kwargs = mock_api.call_args.kwargs
        assert kwargs["search_text"] == "nitrogen"
        assert kwargs["organism"] == "MED4"
        assert kwargs["cluster_type"] == "stress_response"
        assert kwargs["summary"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_tool_wrappers.py::TestListGeneClustersWrapper -v
```
Expected: FAIL — `list_gene_clusters` not registered.

- [ ] **Step 3: Add Pydantic models and tool wrapper**

Add to `multiomics_explorer/mcp_server/tools.py` inside `register_tools()`:

```python
    # ── list_gene_clusters ─────────────────────────────────────────────

    class ListGeneClustersResult(BaseModel):
        cluster_id: str = Field(description="Cluster node ID (e.g. 'cluster:msb4100087:med4:up_n_transport')")
        name: str = Field(description="Cluster name (e.g. 'MED4 cluster 1 (up, N transport)')")
        organism_name: str = Field(description="Organism (e.g. 'Prochlorococcus MED4')")
        cluster_type: str = Field(description="Category: 'diel_periodicity', 'stress_response', or 'expression_level'")
        treatment_type: list[str] = Field(description="Treatment types (e.g. ['nitrogen_stress'])")
        member_count: int = Field(description="Number of genes in cluster (e.g. 5)")
        source_paper: str = Field(description="Paper reference (e.g. 'Tolonen 2006')")
        score: float | None = Field(default=None, description="Lucene relevance score (only when search_text provided)")
        # verbose-only
        functional_description: str | None = Field(default=None,
            description="What the genes ARE (enrichment summary)")
        behavioral_description: str | None = Field(default=None,
            description="What the genes DO together (temporal/response pattern)")
        cluster_method: str | None = Field(default=None,
            description="Clustering algorithm (e.g. 'K-means (K=9)')")
        treatment: str | None = Field(default=None,
            description="Free-text condition (e.g. 'N-starvation time course')")
        light_condition: str | None = Field(default=None,
            description="Light regime (e.g. 'continuous light')")
        experimental_context: str | None = Field(default=None,
            description="Experimental setup details")
        peak_time_hours: float | None = Field(default=None,
            description="Peak expression time for diel clusters (hours)")
        period_hours: float | None = Field(default=None,
            description="Oscillation period for periodic clusters (hours)")
        pub_doi: str | None = Field(default=None,
            description="Publication DOI")

    class GeneClusterOrganismBreakdown(BaseModel):
        organism_name: str = Field(description="Organism name")
        count: int = Field(description="Clusters for this organism")

    class GeneClusterTypeBreakdown(BaseModel):
        cluster_type: str = Field(description="Cluster type")
        count: int = Field(description="Clusters of this type")

    class GeneClusterTreatmentBreakdown(BaseModel):
        treatment_type: str = Field(description="Treatment type")
        count: int = Field(description="Clusters with this treatment")

    class GeneClusterOmicsBreakdown(BaseModel):
        omics_type: str = Field(description="Omics platform")
        count: int = Field(description="Clusters from this platform")

    class GeneClusterPublicationBreakdown(BaseModel):
        publication_doi: str = Field(description="Publication DOI")
        count: int = Field(description="Clusters from this publication")

    class ListGeneClustersResponse(BaseModel):
        total_entries: int = Field(description="Total GeneCluster nodes in KG")
        total_matching: int = Field(description="Clusters matching filters")
        by_organism: list[GeneClusterOrganismBreakdown] = Field(
            description="Clusters per organism, sorted by count desc")
        by_cluster_type: list[GeneClusterTypeBreakdown] = Field(
            description="Clusters per type, sorted by count desc")
        by_treatment_type: list[GeneClusterTreatmentBreakdown] = Field(
            description="Clusters per treatment type, sorted by count desc")
        by_omics_type: list[GeneClusterOmicsBreakdown] = Field(
            description="Clusters per omics platform, sorted by count desc")
        by_publication: list[GeneClusterPublicationBreakdown] = Field(
            description="Clusters per publication, sorted by count desc")
        score_max: float | None = Field(default=None,
            description="Highest Lucene score (only when search_text provided)")
        score_median: float | None = Field(default=None,
            description="Median Lucene score (only when search_text provided)")
        returned: int = Field(description="Results in this response")
        offset: int = Field(default=0, description="Offset into result set")
        truncated: bool = Field(description="True if total_matching > offset + returned")
        results: list[ListGeneClustersResult] = Field(
            default_factory=list, description="One row per cluster")

    @mcp.tool(
        tags={"clusters", "search"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                      "idempotentHint": True, "openWorldHint": False},
    )
    async def list_gene_clusters(
        ctx: Context,
        search_text: Annotated[str | None, Field(
            description="Lucene full-text query over name, functional_description, "
            "behavioral_description, experimental_context. Results ranked by score.",
        )] = None,
        organism: Annotated[str | None, Field(
            description="Filter by organism (case-insensitive partial match).",
        )] = None,
        cluster_type: Annotated[str | None, Field(
            description="Filter: 'diel_periodicity', 'stress_response', "
            "or 'expression_level'.",
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Filter by treatment type(s). E.g. ['nitrogen_stress'].",
        )] = None,
        omics_type: Annotated[str | None, Field(
            description="Filter: 'MICROARRAY', 'RNASEQ', or 'PROTEOMICS'.",
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description="Filter by publication DOI(s).",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include functional_description, behavioral_description, "
            "cluster_method, treatment, light_condition, experimental_context, "
            "peak_time_hours, period_hours, pub_doi.",
        )] = False,
        limit: Annotated[int, Field(description="Max results.", ge=1)] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0)] = 0,
    ) -> ListGeneClustersResponse:
        """Browse, search, and filter gene clusters.

        Search across cluster names, functional descriptions, behavioral
        descriptions, and experimental context. Filter by organism, cluster
        type, treatment type, omics type, or publication.

        Returns cluster IDs for use with genes_in_cluster.
        """
        await ctx.info(f"list_gene_clusters search_text={search_text!r} "
                       f"organism={organism} limit={limit}")
        try:
            conn = _conn(ctx)
            data = api.list_gene_clusters(
                search_text=search_text, organism=organism,
                cluster_type=cluster_type, treatment_type=treatment_type,
                omics_type=omics_type, publication_doi=publication_doi,
                summary=summary, verbose=verbose, limit=limit, offset=offset,
                conn=conn,
            )
            by_organism = [GeneClusterOrganismBreakdown(**b)
                           for b in data["by_organism"]]
            by_cluster_type = [GeneClusterTypeBreakdown(**b)
                               for b in data["by_cluster_type"]]
            by_treatment_type = [GeneClusterTreatmentBreakdown(**b)
                                 for b in data["by_treatment_type"]]
            by_omics_type = [GeneClusterOmicsBreakdown(**b)
                             for b in data["by_omics_type"]]
            by_publication = [GeneClusterPublicationBreakdown(**b)
                              for b in data["by_publication"]]
            results = [ListGeneClustersResult(**r) for r in data["results"]]
            response = ListGeneClustersResponse(
                total_entries=data["total_entries"],
                total_matching=data["total_matching"],
                by_organism=by_organism,
                by_cluster_type=by_cluster_type,
                by_treatment_type=by_treatment_type,
                by_omics_type=by_omics_type,
                by_publication=by_publication,
                score_max=data.get("score_max"),
                score_median=data.get("score_median"),
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of "
                           f"{response.total_matching} clusters")
            return response
        except ValueError as e:
            await ctx.warning(f"list_gene_clusters error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"list_gene_clusters unexpected error: {e}")
            raise ToolError(f"Error in list_gene_clusters: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_tool_wrappers.py::TestListGeneClustersWrapper -v
```
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "feat(mcp): add list_gene_clusters tool wrapper"
```

---

> **REVIEW GATE A:** First tool (list_gene_clusters) is end-to-end across all 3 layers. Review query builder Cypher, API envelope structure, and Pydantic models before proceeding to tools 2 and 3.

---

### Task 4: Query builders — gene_clusters_by_gene

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py`
- Modify: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for `build_gene_clusters_by_gene_summary`**

Append to `tests/unit/test_query_builders.py`:

```python
class TestBuildGeneClustersByGeneSummary:
    """Tests for build_gene_clusters_by_gene_summary."""

    def test_basic_structure(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370", "PMM0920"])
        assert "Gene_in_gene_cluster" in cypher
        assert "GeneCluster" in cypher
        assert "total_matching" in cypher
        assert "total_clusters" in cypher
        assert "not_found" in cypher or "nf" in cypher
        assert params["locus_tags"] == ["PMM0370", "PMM0920"]

    def test_with_cluster_type_filter(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"], cluster_type="stress_response")
        assert "$cluster_type" in cypher
        assert params["cluster_type"] == "stress_response"

    def test_with_publication_doi_filter(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"],
            publication_doi=["10.1038/msb4100087"])
        assert "Publication_has_gene_cluster" in cypher
        assert params["publication_doi"] == ["10.1038/msb4100087"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_query_builders.py::TestBuildGeneClustersByGeneSummary -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `build_gene_clusters_by_gene_summary`**

Add to `multiomics_explorer/kg/queries_lib.py`:

```python
def build_gene_clusters_by_gene_summary(
    *,
    locus_tags: list[str],
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for gene_clusters_by_gene.

    RETURN keys: total_matching, total_clusters,
    genes_with_clusters, genes_without_clusters,
    not_found, not_matched,
    by_cluster_type, by_treatment_type, by_publication.
    """
    params: dict = {"locus_tags": locus_tags}

    gc_conditions: list[str] = []
    if cluster_type is not None:
        gc_conditions.append("gc.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        gc_conditions.append(
            "ANY(tt IN gc.treatment_type WHERE tt IN $treatment_type)")
        params["treatment_type"] = treatment_type

    pub_match = ""
    if publication_doi is not None:
        pub_match = "MATCH (pub:Publication)-[:Publication_has_gene_cluster]->(gc)\n"
        gc_conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    gc_where = "WHERE " + " AND ".join(gc_conditions) + "\n" if gc_conditions else ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "OPTIONAL MATCH (gc:GeneCluster)-[:Gene_in_gene_cluster]->(g)\n"
        f"{pub_match}"
        f"{gc_where}"
        "WITH lt, g, gc\n"
        "WITH collect(DISTINCT CASE WHEN g IS NULL THEN lt END) AS nf_raw,\n"
        "     collect(DISTINCT CASE WHEN g IS NOT NULL AND gc IS NULL\n"
        "             THEN lt END) AS nm_raw,\n"
        "     collect(CASE WHEN gc IS NOT NULL THEN\n"
        "       {lt: lt, cid: gc.id, ct: gc.cluster_type,\n"
        "        tt: gc.treatment_type} END) AS rows\n"
        "WITH [x IN nf_raw WHERE x IS NOT NULL] AS not_found,\n"
        "     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched,\n"
        "     rows\n"
        "OPTIONAL MATCH (pub2:Publication)-[:Publication_has_gene_cluster]->(gc2:GeneCluster)\n"
        "WHERE gc2.id IN [r IN rows | r.cid]\n"
        "WITH not_found, not_matched, rows,\n"
        "     collect(DISTINCT {doi: pub2.doi, cid: gc2.id}) AS pub_rows\n"
        "WITH not_found, not_matched,\n"
        "     size(rows) AS total_matching,\n"
        "     size(apoc.coll.toSet([r IN rows | r.cid])) AS total_clusters,\n"
        "     size(apoc.coll.toSet([r IN rows | r.lt])) AS genes_with_clusters,\n"
        "     size(not_found) + size(not_matched) AS _unused,\n"
        "     size($locus_tags) - size(apoc.coll.toSet([r IN rows | r.lt]))\n"
        "       - size([x IN not_found WHERE x IS NOT NULL]) AS genes_without_clusters,\n"
        "     apoc.coll.frequencies([r IN rows | r.ct]) AS by_cluster_type,\n"
        "     apoc.coll.frequencies(\n"
        "       apoc.coll.flatten([r IN rows | r.tt])) AS by_treatment_type,\n"
        "     apoc.coll.frequencies(\n"
        "       [p IN pub_rows WHERE p.doi IS NOT NULL | p.doi]) AS by_publication,\n"
        "     not_found, not_matched\n"
        "RETURN total_matching, total_clusters,\n"
        "       genes_with_clusters, genes_without_clusters,\n"
        "       not_found, not_matched,\n"
        "       by_cluster_type, by_treatment_type, by_publication"
    )
    return cypher, params
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_query_builders.py::TestBuildGeneClustersByGeneSummary -v
```
Expected: ALL PASS.

- [ ] **Step 5: Write failing tests for `build_gene_clusters_by_gene`**

Append to `tests/unit/test_query_builders.py`:

```python
class TestBuildGeneClustersByGene:
    """Tests for build_gene_clusters_by_gene (detail builder)."""

    def test_returns_expected_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, params = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"])
        for col in ["locus_tag", "gene_name", "cluster_id",
                     "cluster_name", "cluster_type",
                     "membership_score", "member_count"]:
            assert f"AS {col}" in cypher

    def test_verbose_adds_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=True)
        for col in ["functional_description", "behavioral_description",
                     "treatment_type", "treatment", "source_paper", "p_value"]:
            assert f"AS {col}" in cypher

    def test_verbose_false_omits_verbose_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=False)
        assert "functional_description" not in cypher
        assert "behavioral_description" not in cypher

    def test_offset_emits_skip(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, params = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5

    def test_has_order_by(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(locus_tags=["PMM0370"])
        assert "ORDER BY" in cypher
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
pytest tests/unit/test_query_builders.py::TestBuildGeneClustersByGene -v
```
Expected: FAIL.

- [ ] **Step 7: Implement `build_gene_clusters_by_gene`**

Add to `multiomics_explorer/kg/queries_lib.py`:

```python
def build_gene_clusters_by_gene(
    *,
    locus_tags: list[str],
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_clusters_by_gene.

    RETURN keys (compact): locus_tag, gene_name, cluster_id, cluster_name,
    cluster_type, membership_score, member_count.
    RETURN keys (verbose): adds functional_description, behavioral_description,
    treatment_type, treatment, source_paper, p_value.
    """
    params: dict = {"locus_tags": locus_tags}

    gc_conditions: list[str] = []
    if cluster_type is not None:
        gc_conditions.append("gc.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        gc_conditions.append(
            "ANY(tt IN gc.treatment_type WHERE tt IN $treatment_type)")
        params["treatment_type"] = treatment_type

    pub_match = ""
    if publication_doi is not None:
        pub_match = "MATCH (pub:Publication)-[:Publication_has_gene_cluster]->(gc)\n"
        gc_conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    gc_where = ""
    if gc_conditions:
        gc_where = "WHERE " + " AND ".join(gc_conditions) + "\n"

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       gc.functional_description AS functional_description"
            ",\n       gc.behavioral_description AS behavioral_description"
            ",\n       gc.treatment_type AS treatment_type"
            ",\n       gc.treatment AS treatment"
            ",\n       gc.source_paper AS source_paper"
            ",\n       r.p_value AS p_value"
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
        "MATCH (gc:GeneCluster)-[r:Gene_in_gene_cluster]->(g:Gene {locus_tag: lt})\n"
        f"{pub_match}"
        f"{gc_where}"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       gc.id AS cluster_id, gc.name AS cluster_name,\n"
        "       gc.cluster_type AS cluster_type,\n"
        "       r.membership_score AS membership_score,\n"
        f"       gc.member_count AS member_count{verbose_cols}\n"
        f"ORDER BY g.locus_tag, gc.id{skip_clause}{limit_clause}"
    )
    return cypher, params
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
pytest tests/unit/test_query_builders.py::TestBuildGeneClustersByGene -v
```
Expected: ALL PASS.

- [ ] **Step 9: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(query): add gene_clusters_by_gene builders"
```

---

### Task 5: API function — gene_clusters_by_gene

**Files:**
- Modify: `multiomics_explorer/api/functions.py`
- Modify: `multiomics_explorer/api/__init__.py`
- Modify: `tests/unit/test_api_functions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_api_functions.py`:

```python
class TestGeneClustersByGene:
    """Tests for gene_clusters_by_gene API function."""

    _SUMMARY_RESULT = {
        "total_matching": 2, "total_clusters": 2,
        "genes_with_clusters": 2, "genes_without_clusters": 0,
        "not_found": [], "not_matched": [],
        "by_cluster_type": [{"item": "stress_response", "count": 2}],
        "by_treatment_type": [{"item": "nitrogen_stress", "count": 2}],
        "by_publication": [{"item": "10.1038/msb4100087", "count": 2}],
    }

    _DETAIL_ROW = {
        "locus_tag": "PMM0370",
        "gene_name": "cynA",
        "cluster_id": "cluster:msb4100087:med4:up_n_transport",
        "cluster_name": "MED4 cluster 1 (up, N transport)",
        "cluster_type": "stress_response",
        "membership_score": None,
        "member_count": 5,
    }

    def test_returns_envelope(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            # organism validation
            [{"organisms": ["Prochlorococcus MED4"]}],
            # summary
            [self._SUMMARY_RESULT],
            # detail
            [self._DETAIL_ROW],
        ]
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], conn=mock_conn)
        assert result["total_matching"] == 2
        assert result["total_clusters"] == 2
        assert result["genes_with_clusters"] == 2
        assert len(result["results"]) == 1

    def test_empty_locus_tags_raises(self, mock_conn):
        with pytest.raises(ValueError, match="locus_tags must not be empty"):
            api.gene_clusters_by_gene(locus_tags=[], conn=mock_conn)

    def test_summary_mode(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],
            [self._SUMMARY_RESULT],
        ]
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], summary=True, conn=mock_conn)
        assert result["returned"] == 0
        assert result["results"] == []

    def test_not_found_always_in_envelope(self, mock_conn):
        summary_with_nf = {
            **self._SUMMARY_RESULT,
            "not_found": ["FAKE001"],
            "genes_without_clusters": 0,
        }
        mock_conn.execute_query.side_effect = [
            [{"organisms": ["Prochlorococcus MED4"]}],
            [summary_with_nf],
        ]
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370", "FAKE001"], summary=True, conn=mock_conn)
        assert "FAKE001" in result["not_found"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_api_functions.py::TestGeneClustersByGene -v
```
Expected: FAIL.

- [ ] **Step 3: Add builder imports**

Add to imports in `multiomics_explorer/api/functions.py`:

```python
from multiomics_explorer.kg.queries_lib import (
    # ... existing imports ...
    build_gene_clusters_by_gene,
    build_gene_clusters_by_gene_summary,
)
```

- [ ] **Step 4: Implement `gene_clusters_by_gene`**

Add to `multiomics_explorer/api/functions.py`:

```python
def gene_clusters_by_gene(
    locus_tags: list[str],
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Gene-centric cluster lookup. Single organism enforced.

    Returns dict with keys: total_matching, total_clusters,
    genes_with_clusters, genes_without_clusters,
    not_found, not_matched,
    by_cluster_type, by_treatment_type, by_publication,
    returned, offset, truncated, results.
    Per result (compact): locus_tag, gene_name, cluster_id, cluster_name,
    cluster_type, membership_score, member_count.
    Per result (verbose): adds functional_description, behavioral_description,
    treatment_type, treatment, source_paper, p_value.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: if locus_tags is empty or spans multiple organisms.
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
        cluster_type=cluster_type, treatment_type=treatment_type,
        publication_doi=publication_doi,
    )

    # Summary query — always runs
    sum_cypher, sum_params = build_gene_clusters_by_gene_summary(
        locus_tags=locus_tags, **filter_kwargs)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_matching": total_matching,
        "total_clusters": raw_summary["total_clusters"],
        "genes_with_clusters": raw_summary["genes_with_clusters"],
        "genes_without_clusters": raw_summary["genes_without_clusters"],
        "not_found": raw_summary["not_found"],
        "not_matched": raw_summary["not_matched"],
        "by_cluster_type": _rename_freq(
            raw_summary["by_cluster_type"], "cluster_type"),
        "by_treatment_type": _rename_freq(
            raw_summary["by_treatment_type"], "treatment_type"),
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

    det_cypher, det_params = build_gene_clusters_by_gene(
        locus_tags=locus_tags, **filter_kwargs,
        verbose=verbose, limit=limit, offset=offset)
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope
```

- [ ] **Step 5: Add to `api/__init__.py`**

Add `gene_clusters_by_gene` to both the import and `__all__`.

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/unit/test_api_functions.py::TestGeneClustersByGene -v
```
Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/api/__init__.py tests/unit/test_api_functions.py
git commit -m "feat(api): add gene_clusters_by_gene with single-organism enforcement"
```

---

### Task 6: MCP wrapper — gene_clusters_by_gene

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Modify: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_tool_wrappers.py`:

```python
class TestGeneClustersByGeneWrapper:
    """Tests for gene_clusters_by_gene MCP wrapper."""

    _SAMPLE_API_RETURN = {
        "total_matching": 2, "total_clusters": 2,
        "genes_with_clusters": 2, "genes_without_clusters": 0,
        "not_found": [], "not_matched": [],
        "by_cluster_type": [{"cluster_type": "stress_response", "count": 2}],
        "by_treatment_type": [{"treatment_type": "nitrogen_stress", "count": 2}],
        "by_publication": [{"publication_doi": "10.1038/msb4100087", "count": 2}],
        "returned": 1, "offset": 0, "truncated": True,
        "results": [
            {"locus_tag": "PMM0370", "gene_name": "cynA",
             "cluster_id": "cluster:msb4100087:med4:up_n_transport",
             "cluster_name": "MED4 cluster 1 (up, N transport)",
             "cluster_type": "stress_response",
             "membership_score": None, "member_count": 5},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_clusters_by_gene",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["gene_clusters_by_gene"](
                mock_ctx, locus_tags=["PMM0370"])
        assert result.total_matching == 2
        assert result.genes_with_clusters == 2
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.gene_clusters_by_gene",
            side_effect=ValueError("locus_tags must not be empty"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["gene_clusters_by_gene"](
                    mock_ctx, locus_tags=[])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_tool_wrappers.py::TestGeneClustersByGeneWrapper -v
```
Expected: FAIL.

- [ ] **Step 3: Add Pydantic models and tool wrapper**

Add to `multiomics_explorer/mcp_server/tools.py` inside `register_tools()`:

```python
    # ── gene_clusters_by_gene ──────────────────────────────────────────

    class GeneClustersByGeneResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0370')")
        gene_name: str | None = Field(default=None,
            description="Gene name (e.g. 'cynA')")
        cluster_id: str = Field(
            description="Cluster node ID (e.g. 'cluster:msb4100087:med4:up_n_transport')")
        cluster_name: str = Field(
            description="Cluster name (e.g. 'MED4 cluster 1 (up, N transport)')")
        cluster_type: str = Field(
            description="Cluster category (e.g. 'stress_response')")
        membership_score: float | None = Field(default=None,
            description="Fuzzy membership score (null for K-means)")
        member_count: int = Field(
            description="Total genes in this cluster (e.g. 5)")
        # verbose-only
        functional_description: str | None = Field(default=None,
            description="What the cluster genes ARE (cluster-level)")
        behavioral_description: str | None = Field(default=None,
            description="What the cluster genes DO together (cluster-level)")
        treatment_type: list[str] | None = Field(default=None,
            description="Treatment types for this cluster")
        treatment: str | None = Field(default=None,
            description="Free-text condition description")
        source_paper: str | None = Field(default=None,
            description="Paper reference")
        p_value: float | None = Field(default=None,
            description="Assignment p-value (null for most methods)")

    class GeneClustersByGeneResponse(BaseModel):
        total_matching: int = Field(
            description="Gene × cluster rows matching filters")
        total_clusters: int = Field(
            description="Distinct clusters matched")
        genes_with_clusters: int = Field(
            description="Input genes with at least one cluster membership")
        genes_without_clusters: int = Field(
            description="Input genes with zero memberships after filters")
        not_found: list[str] = Field(default_factory=list,
            description="Locus tags not found in KG")
        not_matched: list[str] = Field(default_factory=list,
            description="Locus tags in KG but no cluster memberships after filters")
        by_cluster_type: list[GeneClusterTypeBreakdown] = Field(
            description="Rows per cluster type")
        by_treatment_type: list[GeneClusterTreatmentBreakdown] = Field(
            description="Rows per treatment type")
        by_publication: list[GeneClusterPublicationBreakdown] = Field(
            description="Rows per publication")
        returned: int = Field(description="Results in this response")
        offset: int = Field(default=0, description="Offset into result set")
        truncated: bool = Field(
            description="True if total_matching > offset + returned")
        results: list[GeneClustersByGeneResult] = Field(
            default_factory=list, description="One row per gene × cluster")

    @mcp.tool(
        tags={"clusters", "genes"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                      "idempotentHint": True, "openWorldHint": False},
    )
    async def gene_clusters_by_gene(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(
            description="Gene locus tags (e.g. ['PMM0370', 'PMM0920']).",
        )],
        organism: Annotated[str | None, Field(
            description="Organism name (case-insensitive partial match); "
            "inferred from genes if omitted. Single organism enforced.",
        )] = None,
        cluster_type: Annotated[str | None, Field(
            description="Filter: 'diel_periodicity', 'stress_response', "
            "or 'expression_level'.",
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Filter by treatment type(s).",
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description="Filter by publication DOI(s).",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include functional_description, behavioral_description, "
            "treatment_type, treatment, source_paper, p_value.",
        )] = False,
        limit: Annotated[int, Field(description="Max results.", ge=1)] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0)] = 0,
    ) -> GeneClustersByGeneResponse:
        """Find which gene clusters contain the given genes.

        Gene-centric lookup: 'what clusters are these genes in?'
        Single organism enforced. One row per gene × cluster.

        Use list_gene_clusters for discovery by text search.
        Use genes_in_cluster to drill into a cluster's full membership.
        """
        await ctx.info(f"gene_clusters_by_gene locus_tags={locus_tags} "
                       f"organism={organism}")
        try:
            conn = _conn(ctx)
            data = api.gene_clusters_by_gene(
                locus_tags, organism=organism,
                cluster_type=cluster_type, treatment_type=treatment_type,
                publication_doi=publication_doi,
                summary=summary, verbose=verbose, limit=limit, offset=offset,
                conn=conn,
            )
            by_cluster_type = [GeneClusterTypeBreakdown(**b)
                               for b in data["by_cluster_type"]]
            by_treatment_type = [GeneClusterTreatmentBreakdown(**b)
                                 for b in data["by_treatment_type"]]
            by_publication = [GeneClusterPublicationBreakdown(**b)
                              for b in data["by_publication"]]
            results = [GeneClustersByGeneResult(**r) for r in data["results"]]
            response = GeneClustersByGeneResponse(
                total_matching=data["total_matching"],
                total_clusters=data["total_clusters"],
                genes_with_clusters=data["genes_with_clusters"],
                genes_without_clusters=data["genes_without_clusters"],
                not_found=data["not_found"],
                not_matched=data["not_matched"],
                by_cluster_type=by_cluster_type,
                by_treatment_type=by_treatment_type,
                by_publication=by_publication,
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of "
                           f"{response.total_matching} gene×cluster rows")
            return response
        except ValueError as e:
            await ctx.warning(f"gene_clusters_by_gene error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"gene_clusters_by_gene unexpected error: {e}")
            raise ToolError(f"Error in gene_clusters_by_gene: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_tool_wrappers.py::TestGeneClustersByGeneWrapper -v
```
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "feat(mcp): add gene_clusters_by_gene tool wrapper"
```

---

> **REVIEW GATE B:** Gene-centric tool complete. Review batch diagnostics (not_found/not_matched), single-organism enforcement, and breakdown structures.

---

### Task 7: Query builders — genes_in_cluster

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py`
- Modify: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for `build_genes_in_cluster_summary`**

Append to `tests/unit/test_query_builders.py`:

```python
class TestBuildGenesInClusterSummary:
    """Tests for build_genes_in_cluster_summary."""

    def test_basic_structure(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster_summary
        cypher, params = build_genes_in_cluster_summary(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
        assert "Gene_in_gene_cluster" in cypher
        assert "total_matching" in cypher
        assert "not_found_clusters" in cypher or "nf" in cypher
        assert params["cluster_ids"] == ["cluster:msb4100087:med4:up_n_transport"]

    def test_with_organism_filter(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster_summary
        cypher, params = build_genes_in_cluster_summary(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            organism="MED4")
        assert "organism" in cypher.lower()
        assert params["organism"] == "MED4"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_query_builders.py::TestBuildGenesInClusterSummary -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `build_genes_in_cluster_summary`**

Add to `multiomics_explorer/kg/queries_lib.py`:

```python
def build_genes_in_cluster_summary(
    *,
    cluster_ids: list[str],
    organism: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_in_cluster.

    RETURN keys: total_matching, by_organism, by_cluster,
    by_category_raw, not_found_clusters, not_matched_clusters.
    """
    params: dict = {"cluster_ids": cluster_ids, "organism": organism}

    organism_filter = (
        "AND ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_name) CONTAINS word)\n"
        if organism is not None else ""
    )

    cypher = (
        "UNWIND $cluster_ids AS cid\n"
        "OPTIONAL MATCH (gc:GeneCluster {id: cid})\n"
        "OPTIONAL MATCH (gc)-[r:Gene_in_gene_cluster]->(g:Gene)\n"
        f"WHERE g IS NOT NULL {organism_filter}"
        "WITH cid, gc, g\n"
        "WITH collect(DISTINCT CASE WHEN gc IS NULL THEN cid END) AS nf_raw,\n"
        "     collect(DISTINCT CASE WHEN gc IS NOT NULL AND g IS NULL\n"
        "             THEN cid END) AS nm_raw,\n"
        "     collect(CASE WHEN g IS NOT NULL THEN\n"
        "       {lt: g.locus_tag, org: g.organism_name,\n"
        "        cat: coalesce(g.gene_category, 'Unknown'),\n"
        "        cid: cid, cname: gc.name} END) AS rows\n"
        "WITH [x IN nf_raw WHERE x IS NOT NULL] AS not_found_clusters,\n"
        "     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_clusters,\n"
        "     rows\n"
        "WITH not_found_clusters, not_matched_clusters,\n"
        "     size(rows) AS total_matching,\n"
        "     apoc.coll.frequencies([r IN rows | r.org]) AS by_organism,\n"
        "     apoc.coll.frequencies([r IN rows | r.cat]) AS by_category_raw,\n"
        "     [cid IN apoc.coll.toSet([r IN rows | r.cid]) |\n"
        "       {cluster_id: cid,\n"
        "        cluster_name: head([r IN rows WHERE r.cid = cid | r.cname]),\n"
        "        count: size([r IN rows WHERE r.cid = cid])}] AS by_cluster\n"
        "RETURN total_matching, by_organism, by_cluster, by_category_raw,\n"
        "       not_found_clusters, not_matched_clusters"
    )
    return cypher, params
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_query_builders.py::TestBuildGenesInClusterSummary -v
```
Expected: ALL PASS.

- [ ] **Step 5: Write failing tests for `build_genes_in_cluster`**

Append to `tests/unit/test_query_builders.py`:

```python
class TestBuildGenesInCluster:
    """Tests for build_genes_in_cluster (detail builder)."""

    def test_returns_expected_columns(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, _ = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
        for col in ["locus_tag", "gene_name", "product", "gene_category",
                     "organism_name", "cluster_id", "cluster_name",
                     "membership_score"]:
            assert f"AS {col}" in cypher

    def test_verbose_adds_columns(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, _ = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            verbose=True)
        for col in ["function_description", "gene_summary",
                     "p_value", "functional_description",
                     "behavioral_description"]:
            assert f"AS {col}" in cypher

    def test_has_order_by(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, _ = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
        assert "ORDER BY" in cypher

    def test_offset_emits_skip(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, params = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
pytest tests/unit/test_query_builders.py::TestBuildGenesInCluster -v
```
Expected: FAIL.

- [ ] **Step 7: Implement `build_genes_in_cluster`**

Add to `multiomics_explorer/kg/queries_lib.py`:

```python
def build_genes_in_cluster(
    *,
    cluster_ids: list[str],
    organism: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_in_cluster.

    RETURN keys (compact): locus_tag, gene_name, product, gene_category,
    organism_name, cluster_id, cluster_name, membership_score.
    RETURN keys (verbose): adds function_description, gene_summary,
    p_value, functional_description, behavioral_description.
    """
    params: dict = {"cluster_ids": cluster_ids, "organism": organism}

    organism_filter = (
        "AND ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_name) CONTAINS word)\n"
        if organism is not None else ""
    )

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       g.function_description AS function_description"
            ",\n       g.gene_summary AS gene_summary"
            ",\n       r.p_value AS p_value"
            ",\n       gc.functional_description AS functional_description"
            ",\n       gc.behavioral_description AS behavioral_description"
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
        "UNWIND $cluster_ids AS cid\n"
        "MATCH (gc:GeneCluster {id: cid})-[r:Gene_in_gene_cluster]->(g:Gene)\n"
        f"WHERE ($organism IS NULL{organism_filter.replace('AND ', ' OR (') + ')' if organism_filter else ''})\n"
        if organism is not None else
        "UNWIND $cluster_ids AS cid\n"
        "MATCH (gc:GeneCluster {id: cid})-[r:Gene_in_gene_cluster]->(g:Gene)\n"
    )

    # Simpler approach: conditional WHERE
    if organism is not None:
        cypher = (
            "UNWIND $cluster_ids AS cid\n"
            "MATCH (gc:GeneCluster {id: cid})-[r:Gene_in_gene_cluster]->(g:Gene)\n"
            "WHERE ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(g.organism_name) CONTAINS word)\n"
        )
    else:
        cypher = (
            "UNWIND $cluster_ids AS cid\n"
            "MATCH (gc:GeneCluster {id: cid})-[r:Gene_in_gene_cluster]->(g:Gene)\n"
        )

    cypher += (
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       g.product AS product, g.gene_category AS gene_category,\n"
        "       g.organism_name AS organism_name,\n"
        "       gc.id AS cluster_id, gc.name AS cluster_name,\n"
        f"       r.membership_score AS membership_score{verbose_cols}\n"
        f"ORDER BY gc.id, g.organism_name, g.locus_tag{skip_clause}{limit_clause}"
    )
    return cypher, params
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
pytest tests/unit/test_query_builders.py::TestBuildGenesInCluster -v
```
Expected: ALL PASS.

- [ ] **Step 9: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat(query): add genes_in_cluster builders"
```

---

### Task 8: API function — genes_in_cluster

**Files:**
- Modify: `multiomics_explorer/api/functions.py`
- Modify: `multiomics_explorer/api/__init__.py`
- Modify: `tests/unit/test_api_functions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_api_functions.py`:

```python
class TestGenesInCluster:
    """Tests for genes_in_cluster API function."""

    _SUMMARY_RESULT = {
        "total_matching": 5,
        "by_organism": [{"item": "Prochlorococcus MED4", "count": 5}],
        "by_cluster": [{"cluster_id": "cluster:msb4100087:med4:up_n_transport",
                         "cluster_name": "MED4 cluster 1", "count": 5}],
        "by_category_raw": [{"item": "N-metabolism", "count": 3}],
        "not_found_clusters": [],
        "not_matched_clusters": [],
    }

    _DETAIL_ROW = {
        "locus_tag": "PMM0370",
        "gene_name": "cynA",
        "product": "cyanate ABC transporter",
        "gene_category": "N-metabolism",
        "organism_name": "Prochlorococcus MED4",
        "cluster_id": "cluster:msb4100087:med4:up_n_transport",
        "cluster_name": "MED4 cluster 1 (up, N transport)",
        "membership_score": None,
    }

    def test_returns_envelope(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT],
            [self._DETAIL_ROW],
        ]
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            conn=mock_conn)
        assert result["total_matching"] == 5
        assert len(result["results"]) == 1

    def test_empty_cluster_ids_raises(self, mock_conn):
        with pytest.raises(ValueError, match="cluster_ids must not be empty"):
            api.genes_in_cluster(cluster_ids=[], conn=mock_conn)

    def test_summary_mode(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._SUMMARY_RESULT],
        ]
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            summary=True, conn=mock_conn)
        assert result["returned"] == 0
        assert result["results"] == []

    def test_not_found_clusters_in_envelope(self, mock_conn):
        summary_nf = {
            **self._SUMMARY_RESULT,
            "not_found_clusters": ["cluster:fake:id"],
        }
        mock_conn.execute_query.side_effect = [
            [summary_nf],
        ]
        result = api.genes_in_cluster(
            cluster_ids=["cluster:fake:id"], summary=True, conn=mock_conn)
        assert "cluster:fake:id" in result["not_found_clusters"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_api_functions.py::TestGenesInCluster -v
```
Expected: FAIL.

- [ ] **Step 3: Add builder imports and implement**

Add imports and function to `multiomics_explorer/api/functions.py`:

```python
def genes_in_cluster(
    cluster_ids: list[str],
    organism: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Cluster IDs → member genes. Single organism enforced.

    Returns dict with keys: total_matching, by_organism, by_cluster,
    top_categories, genes_per_cluster_max, genes_per_cluster_median,
    not_found_clusters, not_matched_clusters, not_matched_organism,
    returned, offset, truncated, results.
    Per result (compact): locus_tag, gene_name, product, gene_category,
    organism_name, cluster_id, cluster_name, membership_score.
    Per result (verbose): adds function_description, gene_summary,
    p_value, functional_description, behavioral_description.

    summary=True: results=[], summary fields only.

    Raises:
        ValueError: if cluster_ids is empty.
    """
    if not cluster_ids:
        raise ValueError("cluster_ids must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    # Summary query — always runs
    sum_cypher, sum_params = build_genes_in_cluster_summary(
        cluster_ids=cluster_ids, organism=organism)
    raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]

    def _rename_freq(freq_list, key_name):
        return sorted(
            [{key_name: f["item"], "count": f["count"]} for f in freq_list],
            key=lambda x: x["count"],
            reverse=True,
        )

    by_cluster = raw_summary["by_cluster"]
    cluster_counts = [c["count"] for c in by_cluster]

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_cluster": by_cluster,
        "top_categories": _rename_freq(
            raw_summary["by_category_raw"], "category")[:5],
        "genes_per_cluster_max": max(cluster_counts) if cluster_counts else 0,
        "genes_per_cluster_median": (
            statistics.median(cluster_counts) if cluster_counts else 0
        ),
        "not_found_clusters": raw_summary["not_found_clusters"],
        "not_matched_clusters": raw_summary["not_matched_clusters"],
    }

    # Check organism match
    if organism is not None and total_matching == 0 and not raw_summary["not_found_clusters"]:
        envelope["not_matched_organism"] = organism
    else:
        envelope["not_matched_organism"] = None

    # Detail query — skip when limit=0
    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    det_cypher, det_params = build_genes_in_cluster(
        cluster_ids=cluster_ids, organism=organism,
        verbose=verbose, limit=limit, offset=offset)
    results = conn.execute_query(det_cypher, **det_params)

    envelope["returned"] = len(results)
    envelope["offset"] = offset
    envelope["truncated"] = total_matching > offset + len(results)
    envelope["results"] = results
    return envelope
```

- [ ] **Step 4: Add to `api/__init__.py`**

Add `genes_in_cluster` to both the import and `__all__`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_api_functions.py::TestGenesInCluster -v
```
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/api/__init__.py tests/unit/test_api_functions.py
git commit -m "feat(api): add genes_in_cluster function"
```

---

### Task 9: MCP wrapper — genes_in_cluster

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Modify: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_tool_wrappers.py`:

```python
class TestGenesInClusterWrapper:
    """Tests for genes_in_cluster MCP wrapper."""

    _SAMPLE_API_RETURN = {
        "total_matching": 5,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 5}],
        "by_cluster": [{"cluster_id": "cluster:msb4100087:med4:up_n_transport",
                         "cluster_name": "MED4 cluster 1", "count": 5}],
        "top_categories": [{"category": "N-metabolism", "count": 3}],
        "genes_per_cluster_max": 5,
        "genes_per_cluster_median": 5.0,
        "not_found_clusters": [],
        "not_matched_clusters": [],
        "not_matched_organism": None,
        "returned": 1, "offset": 0, "truncated": True,
        "results": [
            {"locus_tag": "PMM0370", "gene_name": "cynA",
             "product": "cyanate ABC transporter",
             "gene_category": "N-metabolism",
             "organism_name": "Prochlorococcus MED4",
             "cluster_id": "cluster:msb4100087:med4:up_n_transport",
             "cluster_name": "MED4 cluster 1 (up, N transport)",
             "membership_score": None},
        ],
    }

    @pytest.mark.asyncio
    async def test_returns_response_model(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_in_cluster",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["genes_in_cluster"](
                mock_ctx,
                cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
        assert result.total_matching == 5
        assert result.genes_per_cluster_max == 5
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_value_error_raises_tool_error(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.genes_in_cluster",
            side_effect=ValueError("cluster_ids must not be empty"),
        ):
            with pytest.raises(ToolError):
                await tool_fns["genes_in_cluster"](
                    mock_ctx, cluster_ids=[])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_tool_wrappers.py::TestGenesInClusterWrapper -v
```
Expected: FAIL.

- [ ] **Step 3: Add Pydantic models and tool wrapper**

Add to `multiomics_explorer/mcp_server/tools.py` inside `register_tools()`:

```python
    # ── genes_in_cluster ───────────────────────────────────────────────

    class GenesInClusterResult(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0370')")
        gene_name: str | None = Field(default=None,
            description="Gene name (e.g. 'cynA')")
        product: str | None = Field(default=None,
            description="Gene product (e.g. 'cyanate ABC transporter')")
        gene_category: str | None = Field(default=None,
            description="Functional category (e.g. 'N-metabolism')")
        organism_name: str = Field(
            description="Organism (e.g. 'Prochlorococcus MED4')")
        cluster_id: str = Field(
            description="Cluster node ID")
        cluster_name: str = Field(
            description="Cluster name")
        membership_score: float | None = Field(default=None,
            description="Fuzzy membership score (null for K-means)")
        # verbose-only
        function_description: str | None = Field(default=None,
            description="Gene functional description (gene-level)")
        gene_summary: str | None = Field(default=None,
            description="Gene summary text (gene-level)")
        p_value: float | None = Field(default=None,
            description="Assignment p-value (edge-level)")
        functional_description: str | None = Field(default=None,
            description="What the cluster genes ARE (cluster-level)")
        behavioral_description: str | None = Field(default=None,
            description="What the cluster genes DO together (cluster-level)")

    class GenesInClusterClusterBreakdown(BaseModel):
        cluster_id: str = Field(description="Cluster node ID")
        cluster_name: str = Field(description="Cluster name")
        count: int = Field(description="Member genes in this cluster")

    class GenesInClusterCategoryBreakdown(BaseModel):
        category: str = Field(description="Gene category")
        count: int = Field(description="Genes in this category")

    class GenesInClusterResponse(BaseModel):
        total_matching: int = Field(
            description="Gene × cluster rows")
        by_organism: list[GeneClusterOrganismBreakdown] = Field(
            description="Members per organism")
        by_cluster: list[GenesInClusterClusterBreakdown] = Field(
            description="Members per cluster")
        top_categories: list[GenesInClusterCategoryBreakdown] = Field(
            description="Top 5 gene categories by count")
        genes_per_cluster_max: int = Field(
            description="Largest cluster's gene count")
        genes_per_cluster_median: float = Field(
            description="Median gene count across clusters")
        not_found_clusters: list[str] = Field(default_factory=list,
            description="Cluster IDs not found in KG")
        not_matched_clusters: list[str] = Field(default_factory=list,
            description="Clusters found but no members after organism filter")
        not_matched_organism: str | None = Field(default=None,
            description="Organism that didn't match any cluster's organism")
        returned: int = Field(description="Results in this response")
        offset: int = Field(default=0, description="Offset into result set")
        truncated: bool = Field(
            description="True if total_matching > offset + returned")
        results: list[GenesInClusterResult] = Field(
            default_factory=list, description="One row per gene × cluster")

    @mcp.tool(
        tags={"clusters", "genes"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                      "idempotentHint": True, "openWorldHint": False},
    )
    async def genes_in_cluster(
        ctx: Context,
        cluster_ids: Annotated[list[str], Field(
            description="GeneCluster node IDs (from list_gene_clusters "
            "or gene_clusters_by_gene).",
        )],
        organism: Annotated[str | None, Field(
            description="Filter by organism (case-insensitive partial match). "
            "Single organism enforced.",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include function_description, gene_summary (gene-level), "
            "p_value (edge-level), functional_description, "
            "behavioral_description (cluster-level).",
        )] = False,
        limit: Annotated[int, Field(description="Max results.", ge=1)] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0)] = 0,
    ) -> GenesInClusterResponse:
        """Get member genes of gene clusters.

        Takes cluster IDs from list_gene_clusters or gene_clusters_by_gene
        and returns their member genes. One row per gene × cluster.

        For cluster discovery by text, use list_gene_clusters first.
        For gene → cluster direction, use gene_clusters_by_gene.
        """
        await ctx.info(f"genes_in_cluster cluster_ids={cluster_ids} "
                       f"organism={organism}")
        try:
            conn = _conn(ctx)
            data = api.genes_in_cluster(
                cluster_ids, organism=organism,
                summary=summary, verbose=verbose, limit=limit, offset=offset,
                conn=conn,
            )
            by_organism = [GeneClusterOrganismBreakdown(**b)
                           for b in data["by_organism"]]
            by_cluster = [GenesInClusterClusterBreakdown(**b)
                          for b in data["by_cluster"]]
            top_categories = [GenesInClusterCategoryBreakdown(**b)
                              for b in data["top_categories"]]
            results = [GenesInClusterResult(**r) for r in data["results"]]
            response = GenesInClusterResponse(
                total_matching=data["total_matching"],
                by_organism=by_organism,
                by_cluster=by_cluster,
                top_categories=top_categories,
                genes_per_cluster_max=data["genes_per_cluster_max"],
                genes_per_cluster_median=data["genes_per_cluster_median"],
                not_found_clusters=data["not_found_clusters"],
                not_matched_clusters=data["not_matched_clusters"],
                not_matched_organism=data.get("not_matched_organism"),
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of "
                           f"{response.total_matching} gene×cluster rows")
            return response
        except ValueError as e:
            await ctx.warning(f"genes_in_cluster error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"genes_in_cluster unexpected error: {e}")
            raise ToolError(f"Error in genes_in_cluster: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_tool_wrappers.py::TestGenesInClusterWrapper -v
```
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "feat(mcp): add genes_in_cluster tool wrapper"
```

---

> **REVIEW GATE C:** All 3 tools complete across query builder, API, and MCP layers. Run full unit test suite before proceeding to about content and integration tests.

---

### Task 10: About content — input YAML and build

**Files:**
- Create: `multiomics_explorer/inputs/tools/list_gene_clusters.yaml`
- Create: `multiomics_explorer/inputs/tools/gene_clusters_by_gene.yaml`
- Create: `multiomics_explorer/inputs/tools/genes_in_cluster.yaml`

- [ ] **Step 1: Generate input YAML skeletons**

```bash
uv run python scripts/build_about_content.py --skeleton list_gene_clusters
uv run python scripts/build_about_content.py --skeleton gene_clusters_by_gene
uv run python scripts/build_about_content.py --skeleton genes_in_cluster
```

- [ ] **Step 2: Fill in list_gene_clusters.yaml**

Write to `multiomics_explorer/inputs/tools/list_gene_clusters.yaml`:

```yaml
examples:
  - title: Search for photosynthesis-related clusters
    call: list_gene_clusters(search_text="photosynthesis")

  - title: Browse all MED4 clusters
    call: list_gene_clusters(organism="MED4", limit=20)

  - title: Filter by treatment type
    call: list_gene_clusters(treatment_type=["nitrogen_stress"], verbose=True)

  - title: Find clusters then get member genes
    steps: |
      Step 1: list_gene_clusters(search_text="N transport")
              → extract cluster_id values from results

      Step 2: genes_in_cluster(cluster_ids=["cluster:msb4100087:med4:up_n_transport"])
              → see member genes

verbose_fields:
  - functional_description
  - behavioral_description
  - cluster_method
  - treatment
  - light_condition
  - experimental_context
  - peak_time_hours
  - period_hours
  - pub_doi

chaining:
  - "list_gene_clusters → genes_in_cluster → differential_expression_by_gene"
  - "list_gene_clusters → gene_clusters_by_gene (reverse lookup)"

mistakes:
  - "Cluster IDs are not in the fulltext index — use search_text for text queries, cluster_ids with genes_in_cluster."
```

- [ ] **Step 3: Fill in gene_clusters_by_gene.yaml**

Write to `multiomics_explorer/inputs/tools/gene_clusters_by_gene.yaml`:

```yaml
examples:
  - title: Check cluster membership for N-transport genes
    call: gene_clusters_by_gene(locus_tags=["PMM0370", "PMM0920", "PMM0958"])

  - title: Summary only — which genes have clusters?
    call: gene_clusters_by_gene(locus_tags=["PMM0370", "PMM0001"], summary=True)

  - title: Filter to stress response clusters
    call: gene_clusters_by_gene(locus_tags=["PMM0370"], cluster_type="stress_response", verbose=True)

verbose_fields:
  - functional_description
  - behavioral_description
  - treatment_type
  - treatment
  - source_paper
  - p_value

chaining:
  - "resolve_gene → gene_clusters_by_gene → genes_in_cluster"
  - "gene_clusters_by_gene → genes_in_cluster (see all cluster members)"

mistakes:
  - "Single organism enforced — don't mix PMM (MED4) and PMT (MIT9313) locus tags in one call."
```

- [ ] **Step 4: Fill in genes_in_cluster.yaml**

Write to `multiomics_explorer/inputs/tools/genes_in_cluster.yaml`:

```yaml
examples:
  - title: Get members of an N-transport cluster
    call: genes_in_cluster(cluster_ids=["cluster:msb4100087:med4:up_n_transport"])

  - title: Drill into multiple clusters at once
    call: genes_in_cluster(cluster_ids=["cluster:msb4100087:med4:up_n_transport", "cluster:msb4100087:med4:down_translation"], limit=20)

  - title: Verbose view with cluster context
    call: genes_in_cluster(cluster_ids=["cluster:msb4100087:med4:up_n_transport"], verbose=True)

verbose_fields:
  - function_description
  - gene_summary
  - p_value
  - functional_description
  - behavioral_description

chaining:
  - "list_gene_clusters → genes_in_cluster → gene_overview"
  - "gene_clusters_by_gene → genes_in_cluster → differential_expression_by_gene"

mistakes:
  - "Cluster IDs come from list_gene_clusters or gene_clusters_by_gene results — they are not gene locus tags."
```

- [ ] **Step 5: Build about content**

```bash
uv run python scripts/build_about_content.py list_gene_clusters gene_clusters_by_gene genes_in_cluster
```

- [ ] **Step 6: Run about content tests**

```bash
pytest tests/unit/test_about_content.py -v
```
Expected: ALL PASS including new tools.

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/inputs/tools/list_gene_clusters.yaml \
       multiomics_explorer/inputs/tools/gene_clusters_by_gene.yaml \
       multiomics_explorer/inputs/tools/genes_in_cluster.yaml \
       multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_gene_clusters.md \
       multiomics_explorer/skills/multiomics-kg-guide/references/tools/gene_clusters_by_gene.md \
       multiomics_explorer/skills/multiomics-kg-guide/references/tools/genes_in_cluster.md
git commit -m "docs: add about content for gene cluster tools"
```

---

### Task 11: Integration tests + CLAUDE.md

**Files:**
- Modify: `tests/integration/test_api_contract.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add contract tests**

Append to `tests/integration/test_api_contract.py`:

```python
@pytest.mark.kg
class TestListGeneClustersContract:
    def test_returns_dict_envelope(self, conn):
        result = api.list_gene_clusters(conn=conn)
        expected_keys = {
            "total_entries", "total_matching",
            "by_organism", "by_cluster_type", "by_treatment_type",
            "by_omics_type", "by_publication",
            "returned", "offset", "truncated", "results",
        }
        assert expected_keys <= set(result.keys())
        assert result["total_entries"] >= 16

    def test_search_text(self, conn):
        result = api.list_gene_clusters(
            search_text="nitrogen", conn=conn)
        assert result["total_matching"] >= 1
        assert "score_max" in result

    def test_organism_filter(self, conn):
        result = api.list_gene_clusters(
            organism="MED4", conn=conn)
        assert result["total_matching"] >= 9

    def test_result_keys_compact(self, conn):
        result = api.list_gene_clusters(limit=1, conn=conn)
        if result["results"]:
            expected = {"cluster_id", "name", "organism_name",
                        "cluster_type", "treatment_type",
                        "member_count", "source_paper"}
            assert expected <= set(result["results"][0].keys())

    def test_result_keys_verbose(self, conn):
        result = api.list_gene_clusters(
            verbose=True, limit=1, conn=conn)
        if result["results"]:
            for key in ("functional_description", "behavioral_description",
                        "cluster_method"):
                assert key in result["results"][0]


@pytest.mark.kg
class TestGeneClustersByGeneContract:
    def test_returns_dict_envelope(self, conn):
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], conn=conn)
        expected_keys = {
            "total_matching", "total_clusters",
            "genes_with_clusters", "genes_without_clusters",
            "not_found", "not_matched",
            "by_cluster_type", "by_treatment_type", "by_publication",
            "returned", "offset", "truncated", "results",
        }
        assert expected_keys <= set(result.keys())

    def test_known_gene_has_cluster(self, conn):
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370"], conn=conn)
        assert result["genes_with_clusters"] >= 1
        assert result["total_clusters"] >= 1

    def test_unknown_gene_in_not_found(self, conn):
        result = api.gene_clusters_by_gene(
            locus_tags=["PMM0370", "FAKE_GENE_XYZ"],
            conn=conn)
        assert "FAKE_GENE_XYZ" in result["not_found"]


@pytest.mark.kg
class TestGenesInClusterContract:
    def test_returns_dict_envelope(self, conn):
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            conn=conn)
        expected_keys = {
            "total_matching", "by_organism", "by_cluster",
            "top_categories", "genes_per_cluster_max",
            "genes_per_cluster_median",
            "not_found_clusters", "not_matched_clusters",
            "returned", "offset", "truncated", "results",
        }
        assert expected_keys <= set(result.keys())

    def test_known_cluster_has_members(self, conn):
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            conn=conn)
        assert result["total_matching"] == 5

    def test_result_keys_compact(self, conn):
        result = api.genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4:up_n_transport"],
            limit=1, conn=conn)
        expected = {"locus_tag", "gene_name", "product", "gene_category",
                    "organism_name", "cluster_id", "cluster_name",
                    "membership_score"}
        assert expected <= set(result["results"][0].keys())

    def test_unknown_cluster_in_not_found(self, conn):
        result = api.genes_in_cluster(
            cluster_ids=["cluster:fake:id"], conn=conn)
        assert "cluster:fake:id" in result["not_found_clusters"]
```

- [ ] **Step 2: Run integration tests**

```bash
pytest tests/integration/test_api_contract.py -k "GeneCluster or GenesInCluster" -v
```
Expected: ALL PASS against live KG.

- [ ] **Step 3: Run CyVer validation**

```bash
pytest tests/integration/test_cyver_queries.py -v
```
Expected: ALL PASS — new builders auto-discovered.

- [ ] **Step 4: Update CLAUDE.md tool table**

Add to the tool table in `CLAUDE.md`:

```markdown
| `list_gene_clusters` | Browse, search, and filter gene clusters. Optional Lucene search over functional/behavioral descriptions. Filterable by organism, cluster_type, treatment_type, omics_type, publication_doi. Rich summary breakdowns. |
| `gene_clusters_by_gene` | Batch gene-centric cluster lookup. Locus tags → cluster memberships. Single organism enforced. Reports genes_with/without_clusters, not_found, not_matched. |
| `genes_in_cluster` | Cluster IDs → member genes. Drill-down tool. Summary with top_categories, genes_per_cluster stats. Verbose includes both gene-level and cluster-level descriptions. |
```

- [ ] **Step 5: Run full unit test suite**

```bash
pytest tests/unit/ -v
```
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/integration/test_api_contract.py CLAUDE.md
git commit -m "test(integration): add gene cluster contract tests, update CLAUDE.md"
```

---

> **REVIEW GATE D:** All 11 tasks complete. Full unit + integration test suite passes. Review complete changeset before merge. Use `/code-review` for final validation.
