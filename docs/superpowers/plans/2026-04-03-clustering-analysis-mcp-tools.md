# ClusteringAnalysis MCP Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `list_gene_clusters` with `list_clustering_analyses`, update `gene_clusters_by_gene` and `genes_in_cluster` to work with the new `ClusteringAnalysis` intermediate node, and add CLI commands + DataFrame utility.

**Architecture:** Bottom-up across 4 layers (queries_lib → api/functions → mcp_server/tools → CLI/YAML/docs). Each tool is updated in layer order. Old code removed after new code is in place. TDD throughout — write failing test, implement, pass.

**Tech Stack:** Python, Neo4j Cypher (APOC), Pydantic, FastMCP, Typer (CLI), pandas, pytest

---

## Scope & Impact Summary

| Before | After |
|---|---|
| `list_gene_clusters` (broken edges) | `list_clustering_analyses` (new) |
| `gene_clusters_by_gene` (no analysis context) | `gene_clusters_by_gene` (updated, analysis fields) |
| `genes_in_cluster` (no analysis entry point) | `genes_in_cluster` (updated, `analysis_id` param) |
| No CLI cluster commands | 3 CLI commands |
| No `analyses_to_dataframe` | New DataFrame converter |
| `Publication_has_gene_cluster` edge (8 refs) | `PublicationHasClusteringAnalysis` + `ClusteringAnalysisHasGeneCluster` |
| Denormalized filter fields on GC | Filters via CA node |

## File Map

| File | Changes |
|---|---|
| `multiomics_explorer/kg/queries_lib.py` | Remove `_gene_cluster_where`, `build_list_gene_clusters_summary`, `build_list_gene_clusters`. Add `_clustering_analysis_where`, `build_list_clustering_analyses_summary`, `build_list_clustering_analyses`. Update `build_gene_clusters_by_gene_summary`, `build_gene_clusters_by_gene`, `build_genes_in_cluster_summary`, `build_genes_in_cluster`. |
| `multiomics_explorer/api/functions.py` | Remove `list_gene_clusters`. Add `list_clustering_analyses`. Update `gene_clusters_by_gene`, `genes_in_cluster`. |
| `multiomics_explorer/api/__init__.py` | Replace `list_gene_clusters` with `list_clustering_analyses` in imports and `__all__` |
| `multiomics_explorer/__init__.py` | Add `list_clustering_analyses`, `gene_clusters_by_gene`, `genes_in_cluster` to imports and `__all__` |
| `multiomics_explorer/mcp_server/tools.py` | Remove `list_gene_clusters` tool + models. Add `list_clustering_analyses` tool + models. Update `gene_clusters_by_gene`, `genes_in_cluster` models + params. |
| `multiomics_explorer/analysis/frames.py` | Add `analyses_to_dataframe`. Register in `_DEDICATED_FUNCTIONS`. |
| `multiomics_explorer/analysis/__init__.py` | Export `analyses_to_dataframe` |
| `multiomics_explorer/cli/main.py` | Add `list-clustering-analyses`, `gene-clusters-by-gene`, `genes-in-cluster` commands |
| `multiomics_explorer/inputs/tools/list_clustering_analyses.yaml` | New YAML (replaces `list_gene_clusters.yaml`) |
| `multiomics_explorer/inputs/tools/gene_clusters_by_gene.yaml` | Update examples for new fields |
| `multiomics_explorer/inputs/tools/genes_in_cluster.yaml` | Update examples for renamed fields + analysis_id |
| `multiomics_explorer/inputs/tools/list_gene_clusters.yaml` | Delete |
| `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/to_dataframe.md` | Add `analyses_to_dataframe` docs |
| `tests/unit/test_query_builders.py` | Replace cluster test classes |
| `tests/unit/test_api_functions.py` | Replace cluster test classes |
| `tests/unit/test_tool_wrappers.py` | Replace cluster test classes + update `EXPECTED_TOOLS` |
| `tests/integration/test_api_contract.py` | Replace cluster contract classes |
| `tests/integration/test_cyver_queries.py` | Add new builders to `_BUILDERS` |
| `tests/regression/` | Regenerate baselines |
| `CLAUDE.md` | Update tool table |

---

## Task 1: Query builders — `_clustering_analysis_where` helper

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for `_clustering_analysis_where`**

In `tests/unit/test_query_builders.py`, replace `TestGeneClusterWhere` with:

```python
class TestClusteringAnalysisWhere:
    """Tests for _clustering_analysis_where shared helper."""

    def test_no_filters(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where()
        assert conditions == []
        assert params == {}

    def test_organism_filter(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(organism="MED4")
        assert len(conditions) == 1
        assert "organism_name" in conditions[0].lower()
        assert params["organism"] == "MED4"

    def test_cluster_type_filter(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(cluster_type="response_pattern")
        assert len(conditions) == 1
        assert "$cluster_type" in conditions[0]
        assert params["cluster_type"] == "response_pattern"

    def test_treatment_type_filter(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(treatment_type=["nitrogen_stress"])
        assert len(conditions) == 1
        assert "ANY(" in conditions[0]
        assert "$treatment_type" in conditions[0]
        assert params["treatment_type"] == ["nitrogen_stress"]

    def test_omics_type_filter(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(omics_type="MICROARRAY")
        assert len(conditions) == 1
        assert "$omics_type" in conditions[0]
        assert params["omics_type"] == "MICROARRAY"

    def test_background_factors_filter(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(
            background_factors=["axenic"])
        assert len(conditions) == 1
        assert "ANY(" in conditions[0]
        assert "background_factors" in conditions[0]
        assert params["background_factors"] == ["axenic"]

    def test_combined_filters(self):
        from multiomics_explorer.kg.queries_lib import _clustering_analysis_where
        conditions, params = _clustering_analysis_where(
            organism="MED4", cluster_type="response_pattern",
            treatment_type=["nitrogen_stress"], omics_type="MICROARRAY",
            background_factors=["axenic"],
        )
        assert len(conditions) == 5
        assert len(params) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestClusteringAnalysisWhere -v`
Expected: FAIL with ImportError (`_clustering_analysis_where` not found)

- [ ] **Step 3: Implement `_clustering_analysis_where`**

In `multiomics_explorer/kg/queries_lib.py`, replace `_gene_cluster_where` with:

```python
def _clustering_analysis_where(
    *,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    background_factors: list[str] | None = None,
) -> tuple[list[str], dict]:
    """Build ClusteringAnalysis filter conditions + params."""
    conditions: list[str] = []
    params: dict = {}
    if organism is not None:
        conditions.append(
            "ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(ca.organism_name) CONTAINS word)"
        )
        params["organism"] = organism
    if cluster_type is not None:
        conditions.append("ca.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        conditions.append(
            "ANY(tt IN ca.treatment_type WHERE tt IN $treatment_type)"
        )
        params["treatment_type"] = treatment_type
    if omics_type is not None:
        conditions.append("ca.omics_type = $omics_type")
        params["omics_type"] = omics_type
    if background_factors is not None:
        conditions.append(
            "ANY(bf IN coalesce(ca.background_factors, [])"
            " WHERE bf IN $background_factors)"
        )
        params["background_factors"] = background_factors
    return conditions, params
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestClusteringAnalysisWhere -v`
Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: add _clustering_analysis_where helper for CA node filters"
```

---

## Task 2: Query builders — `build_list_clustering_analyses_summary` + `build_list_clustering_analyses`

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for summary builder**

In `tests/unit/test_query_builders.py`, replace `TestBuildListGeneClustersSummary` with:

```python
class TestBuildListClusteringAnalysesSummary:
    """Tests for build_list_clustering_analyses_summary."""

    def test_no_search_no_filters(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary()
        assert "ClusteringAnalysis" in cypher
        assert "total_entries" in cypher
        assert "total_matching" in cypher
        assert "by_organism" in cypher
        assert "by_cluster_type" in cypher
        assert "by_treatment_type" in cypher
        assert "by_background_factors" in cypher
        assert "by_omics_type" in cypher
        assert "WHERE" not in cypher

    def test_with_search_text(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary(search_text="nitrogen")
        assert "clusteringAnalysisFullText" in cypher
        assert params["search_text"] == "nitrogen"
        assert "score_max" in cypher
        assert "score_median" in cypher

    def test_with_organism_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary(organism="MED4")
        assert "WHERE" in cypher
        assert params["organism"] == "MED4"

    def test_with_publication_doi_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary(
            publication_doi=["10.1038/msb4100087"])
        assert "PublicationHasClusteringAnalysis" in cypher
        assert params["publication_doi"] == ["10.1038/msb4100087"]

    def test_with_experiment_ids_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary(
            experiment_ids=["10.1038/msb4100087_n_starvation_med4"])
        assert "ExperimentHasClusteringAnalysis" in cypher
        assert params["experiment_ids"] == ["10.1038/msb4100087_n_starvation_med4"]

    def test_with_analysis_ids_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses_summary
        cypher, params = build_list_clustering_analyses_summary(
            analysis_ids=["clustering_analysis:msb4100087:med4_kmeans_nstarvation"])
        assert "$analysis_ids" in cypher
        assert params["analysis_ids"] == ["clustering_analysis:msb4100087:med4_kmeans_nstarvation"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListClusteringAnalysesSummary -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `build_list_clustering_analyses_summary`**

In `multiomics_explorer/kg/queries_lib.py`, replace `build_list_gene_clusters_summary` with:

```python
def build_list_clustering_analyses_summary(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    analysis_ids: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for list_clustering_analyses.

    RETURN keys: total_entries, total_matching, by_organism,
    by_cluster_type, by_treatment_type, by_background_factors,
    by_omics_type.
    When search_text: adds score_max, score_median.
    """
    conditions, params = _clustering_analysis_where(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, omics_type=omics_type,
        background_factors=background_factors,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('clusteringAnalysisFullText', $search_text)\n"
            "YIELD node AS ca, score\n"
        )
        score_cols = (
            ",\n     max(score) AS score_max"
            ",\n     percentileDisc(score, 0.5) AS score_median"
        )
        score_return = ", score_max, score_median"
    else:
        match_block = "MATCH (ca:ClusteringAnalysis)\n"
        score_cols = ""
        score_return = ""

    if publication_doi is not None:
        match_block += "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    if experiment_ids is not None:
        match_block += "MATCH (exp:Experiment)-[:ExperimentHasClusteringAnalysis]->(ca)\n"
        conditions.append("exp.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids

    if analysis_ids is not None:
        conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    cypher = (
        f"{match_block}"
        f"{where_block}"
        "WITH collect(ca.organism_name) AS organisms,\n"
        "     collect(ca.cluster_type) AS cluster_types,\n"
        "     apoc.coll.flatten(collect(ca.treatment_type)) AS treatment_types,\n"
        "     apoc.coll.flatten(collect(coalesce(ca.background_factors, []))) AS background_factors_flat,\n"
        "     collect(ca.omics_type) AS omics_types,\n"
        f"     count(ca) AS total_matching{score_cols}\n"
        "CALL { MATCH (all_ca:ClusteringAnalysis) RETURN count(all_ca) AS total_entries }\n"
        "RETURN total_entries, total_matching,\n"
        "       apoc.coll.frequencies(organisms) AS by_organism,\n"
        "       apoc.coll.frequencies(cluster_types) AS by_cluster_type,\n"
        "       apoc.coll.frequencies(treatment_types) AS by_treatment_type,\n"
        "       apoc.coll.frequencies(background_factors_flat) AS by_background_factors,\n"
        f"       apoc.coll.frequencies(omics_types) AS by_omics_type{score_return}"
    )
    return cypher, params
```

- [ ] **Step 4: Run summary tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListClusteringAnalysesSummary -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Write failing tests for detail builder**

In `tests/unit/test_query_builders.py`, replace `TestBuildListGeneClusters` with:

```python
class TestBuildListClusteringAnalyses:
    """Tests for build_list_clustering_analyses (detail builder)."""

    def test_no_search_returns_expected_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses()
        for col in ["analysis_id", "name", "organism_name", "cluster_method",
                     "cluster_type", "cluster_count", "total_gene_count",
                     "treatment_type", "background_factors", "omics_type"]:
            assert f"AS {col}" in cypher, f"Missing column: {col}"
        assert "score" not in cypher
        # Inline clusters via subquery
        assert "ClusteringAnalysisHasGeneCluster" in cypher

    def test_with_search_text(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(search_text="nitrogen")
        assert "clusteringAnalysisFullText" in cypher
        assert "score" in cypher
        assert params["search_text"] == "nitrogen"

    def test_verbose_adds_analysis_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(verbose=True)
        for col in ["treatment", "light_condition", "experimental_context"]:
            assert f"AS {col}" in cypher, f"Missing verbose column: {col}"

    def test_verbose_false_omits_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(verbose=False)
        assert "AS treatment\n" not in cypher and "AS treatment," not in cypher
        assert "AS light_condition" not in cypher

    def test_verbose_adds_cluster_descriptions(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(verbose=True)
        assert "functional_description" in cypher
        assert "behavioral_description" in cypher

    def test_inline_clusters_compact(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(verbose=False)
        # Compact clusters: id, name, member_count
        assert "cluster_id" in cypher or "gc.id" in cypher
        assert "member_count" in cypher

    def test_experiment_ids_optional_match(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses()
        # Experiment IDs should be OPTIONAL MATCH (may not exist)
        assert "OPTIONAL MATCH" in cypher
        assert "ExperimentHasClusteringAnalysis" in cypher

    def test_publication_doi_filter(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(
            publication_doi=["10.1038/msb4100087"])
        assert "PublicationHasClusteringAnalysis" in cypher
        assert params["publication_doi"] == ["10.1038/msb4100087"]

    def test_offset_emits_skip(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5

    def test_offset_zero_no_skip(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, params = build_list_clustering_analyses(limit=10, offset=0)
        assert "SKIP" not in cypher
        assert "offset" not in params

    def test_has_order_by(self):
        from multiomics_explorer.kg.queries_lib import build_list_clustering_analyses
        cypher, _ = build_list_clustering_analyses()
        assert "ORDER BY" in cypher
```

- [ ] **Step 6: Implement `build_list_clustering_analyses`**

In `multiomics_explorer/kg/queries_lib.py`, replace `build_list_gene_clusters` with:

```python
def build_list_clustering_analyses(
    *,
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: str | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    analysis_ids: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for list_clustering_analyses.

    RETURN keys (compact): analysis_id, name, organism_name, cluster_method,
    cluster_type, cluster_count, total_gene_count, treatment_type,
    background_factors, omics_type, experiment_ids, clusters.
    When search_text: adds score.
    RETURN keys (verbose): adds treatment, light_condition, experimental_context.
    Inline clusters (compact): cluster_id, name, member_count.
    Inline clusters (verbose): adds functional_description, behavioral_description,
    peak_time_hours, period_hours.
    """
    conditions, params = _clustering_analysis_where(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, omics_type=omics_type,
        background_factors=background_factors,
    )

    if search_text is not None:
        params["search_text"] = search_text
        match_block = (
            "CALL db.index.fulltext.queryNodes('clusteringAnalysisFullText', $search_text)\n"
            "YIELD node AS ca, score\n"
        )
        score_col = ",\n       score"
        order_prefix = "score DESC, "
    else:
        match_block = "MATCH (ca:ClusteringAnalysis)\n"
        score_col = ""
        order_prefix = ""

    if publication_doi is not None:
        match_block += "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    if experiment_ids is not None:
        match_block += "MATCH (exp:Experiment)-[:ExperimentHasClusteringAnalysis]->(ca)\n"
        conditions.append("exp.id IN $experiment_ids")
        params["experiment_ids"] = experiment_ids

    if analysis_ids is not None:
        conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    where_block = "WHERE " + " AND ".join(conditions) + "\n" if conditions else ""

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       ca.treatment AS treatment"
            ",\n       ca.light_condition AS light_condition"
            ",\n       ca.experimental_context AS experimental_context"
        )

    # Inline cluster subquery — compact or verbose
    if verbose:
        cluster_collect = (
            "collect({cluster_id: gc.id, name: gc.name,"
            " member_count: gc.member_count,"
            " functional_description: gc.functional_description,"
            " behavioral_description: gc.behavioral_description,"
            " peak_time_hours: gc.peak_time_hours,"
            " period_hours: gc.period_hours}) AS clusters"
        )
    else:
        cluster_collect = (
            "collect({cluster_id: gc.id, name: gc.name,"
            " member_count: gc.member_count}) AS clusters"
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
        f"{match_block}"
        f"{where_block}"
        # Collect experiment IDs (OPTIONAL — edge may not exist)
        "OPTIONAL MATCH (exp_link:Experiment)-[:ExperimentHasClusteringAnalysis]->(ca)\n"
        "WITH ca" + (", score" if search_text is not None else "") + ",\n"
        "     collect(DISTINCT exp_link.id) AS experiment_ids\n"
        # Collect inline clusters
        "OPTIONAL MATCH (ca)-[:ClusteringAnalysisHasGeneCluster]->(gc:GeneCluster)\n"
        "WITH ca" + (", score" if search_text is not None else "") + ", experiment_ids,\n"
        f"     {cluster_collect}\n"
        "RETURN ca.id AS analysis_id, ca.name AS name,\n"
        "       ca.organism_name AS organism_name,\n"
        "       ca.cluster_method AS cluster_method,\n"
        "       ca.cluster_type AS cluster_type,\n"
        "       ca.cluster_count AS cluster_count,\n"
        "       ca.total_gene_count AS total_gene_count,\n"
        "       ca.treatment_type AS treatment_type,\n"
        "       coalesce(ca.background_factors, []) AS background_factors,\n"
        "       ca.omics_type AS omics_type,\n"
        f"       experiment_ids, clusters{score_col}{verbose_cols}\n"
        f"ORDER BY {order_prefix}ca.organism_name, ca.name{skip_clause}{limit_clause}"
    )
    return cypher, params
```

- [ ] **Step 7: Run all detail tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListClusteringAnalyses -v`
Expected: all 11 tests PASS

- [ ] **Step 8: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: add list_clustering_analyses query builders (summary + detail)"
```

---

## Task 3: Query builders — update `gene_clusters_by_gene`

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for updated summary builder**

In `tests/unit/test_query_builders.py`, replace `TestBuildGeneClustersByGeneSummary`:

```python
class TestBuildGeneClustersByGeneSummary:
    """Tests for build_gene_clusters_by_gene_summary."""

    def test_basic_structure(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370", "PMM0920"])
        assert "Gene_in_gene_cluster" in cypher
        assert "GeneCluster" in cypher
        assert "ClusteringAnalysisHasGeneCluster" in cypher
        assert "total_matching" in cypher
        assert "total_clusters" in cypher
        assert "by_analysis" in cypher
        assert params["locus_tags"] == ["PMM0370", "PMM0920"]

    def test_no_old_publication_edge(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, _ = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"])
        assert "Publication_has_gene_cluster" not in cypher

    def test_with_cluster_type_filter(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"], cluster_type="response_pattern")
        assert "$cluster_type" in cypher
        assert params["cluster_type"] == "response_pattern"

    def test_with_publication_doi_filter(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"],
            publication_doi=["10.1038/msb4100087"])
        assert "PublicationHasClusteringAnalysis" in cypher
        assert params["publication_doi"] == ["10.1038/msb4100087"]

    def test_with_analysis_ids_filter(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene_summary
        cypher, params = build_gene_clusters_by_gene_summary(
            locus_tags=["PMM0370"],
            analysis_ids=["clustering_analysis:msb4100087:med4_kmeans_nstarvation"])
        assert "$analysis_ids" in cypher
```

- [ ] **Step 2: Write failing tests for updated detail builder**

In `tests/unit/test_query_builders.py`, replace `TestBuildGeneClustersByGene`:

```python
class TestBuildGeneClustersByGene:
    """Tests for build_gene_clusters_by_gene (detail builder)."""

    def test_returns_expected_compact_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, params = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"])
        for col in ["locus_tag", "gene_name", "cluster_id",
                     "cluster_name", "cluster_type",
                     "membership_score", "analysis_id", "analysis_name",
                     "treatment_type", "background_factors"]:
            assert f"AS {col}" in cypher, f"Missing compact column: {col}"

    def test_no_old_source_paper(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"])
        assert "source_paper" not in cypher

    def test_analysis_fields_from_ca_node(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(locus_tags=["PMM0370"])
        assert "ClusteringAnalysisHasGeneCluster" in cypher
        assert "ca.id AS analysis_id" in cypher
        assert "ca.name AS analysis_name" in cypher

    def test_verbose_adds_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=True)
        for col in ["cluster_functional_description", "cluster_behavioral_description",
                     "cluster_method", "member_count",
                     "treatment", "light_condition", "experimental_context",
                     "p_value", "peak_time_hours", "period_hours"]:
            assert f"AS {col}" in cypher, f"Missing verbose column: {col}"

    def test_verbose_false_omits_verbose_columns(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"], verbose=False)
        assert "cluster_functional_description" not in cypher
        assert "cluster_behavioral_description" not in cypher

    def test_no_old_publication_edge(self):
        from multiomics_explorer.kg.queries_lib import build_gene_clusters_by_gene
        cypher, _ = build_gene_clusters_by_gene(
            locus_tags=["PMM0370"],
            publication_doi=["10.1038/msb4100087"])
        assert "Publication_has_gene_cluster" not in cypher
        assert "PublicationHasClusteringAnalysis" in cypher

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

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneClustersByGeneSummary tests/unit/test_query_builders.py::TestBuildGeneClustersByGene -v`
Expected: FAIL (missing columns, old edge references)

- [ ] **Step 4: Implement updated `build_gene_clusters_by_gene_summary`**

Update in `multiomics_explorer/kg/queries_lib.py`. Key changes:
- Join `(ca:ClusteringAnalysis)-[:ClusteringAnalysisHasGeneCluster]->(gc)` to get analysis fields
- Replace `Publication_has_gene_cluster` with `PublicationHasClusteringAnalysis` via CA
- Add `analysis_ids` filter: `ca.id IN $analysis_ids`
- Filter `cluster_type`, `treatment_type`, `omics_type`, `background_factors` on `ca` instead of `gc`
- Add `by_analysis` breakdown: `apoc.coll.frequencies([r IN rows | r.aid]) AS by_analysis`

```python
def build_gene_clusters_by_gene_summary(
    *,
    locus_tags: list[str],
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    analysis_ids: list[str] | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for gene_clusters_by_gene.

    RETURN keys: total_matching, total_clusters,
    genes_with_clusters, genes_without_clusters,
    not_found, not_matched,
    by_cluster_type, by_treatment_type, by_background_factors,
    by_publication, by_analysis.
    """
    params: dict = {"locus_tags": locus_tags}

    ca_conditions: list[str] = []
    if cluster_type is not None:
        ca_conditions.append("ca.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        ca_conditions.append(
            "ANY(tt IN ca.treatment_type WHERE tt IN $treatment_type)")
        params["treatment_type"] = treatment_type
    if background_factors is not None:
        ca_conditions.append(
            "ANY(bf IN coalesce(ca.background_factors, [])"
            " WHERE bf IN $background_factors)")
        params["background_factors"] = background_factors
    if analysis_ids is not None:
        ca_conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    pub_match = ""
    if publication_doi is not None:
        pub_match = "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        ca_conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    ca_where = "WHERE " + " AND ".join(ca_conditions) + "\n" if ca_conditions else ""

    cypher = (
        "UNWIND $locus_tags AS lt\n"
        "OPTIONAL MATCH (g:Gene {locus_tag: lt})\n"
        "OPTIONAL MATCH (gc:GeneCluster)-[:Gene_in_gene_cluster]->(g)\n"
        "OPTIONAL MATCH (ca:ClusteringAnalysis)-[:ClusteringAnalysisHasGeneCluster]->(gc)\n"
        f"{pub_match}"
        f"{ca_where}"
        "WITH lt, g, gc, ca\n"
        "WITH collect(DISTINCT CASE WHEN g IS NULL THEN lt END) AS nf_raw,\n"
        "     collect(DISTINCT CASE WHEN g IS NOT NULL AND gc IS NULL\n"
        "             THEN lt END) AS nm_raw,\n"
        "     collect(CASE WHEN gc IS NOT NULL THEN\n"
        "       {lt: lt, cid: gc.id, ct: ca.cluster_type,\n"
        "        tt: ca.treatment_type,\n"
        "        bfs: coalesce(ca.background_factors, []),\n"
        "        aid: ca.id} END) AS rows\n"
        "WITH [x IN nf_raw WHERE x IS NOT NULL] AS not_found,\n"
        "     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched,\n"
        "     rows\n"
        "OPTIONAL MATCH (pub2:Publication)-[:PublicationHasClusteringAnalysis]->(ca2:ClusteringAnalysis)\n"
        "-[:ClusteringAnalysisHasGeneCluster]->(gc2:GeneCluster)\n"
        "WHERE gc2.id IN [r IN rows | r.cid]\n"
        "WITH not_found, not_matched, rows,\n"
        "     collect(DISTINCT {doi: pub2.doi, cid: gc2.id}) AS pub_rows\n"
        "WITH not_found, not_matched,\n"
        "     size(rows) AS total_matching,\n"
        "     size(apoc.coll.toSet([r IN rows | r.cid])) AS total_clusters,\n"
        "     size(apoc.coll.toSet([r IN rows | r.lt])) AS genes_with_clusters,\n"
        "     size($locus_tags) - size(apoc.coll.toSet([r IN rows | r.lt]))\n"
        "       - size([x IN not_found WHERE x IS NOT NULL]) AS genes_without_clusters,\n"
        "     apoc.coll.frequencies([r IN rows | r.ct]) AS by_cluster_type,\n"
        "     apoc.coll.frequencies(\n"
        "       apoc.coll.flatten([r IN rows | r.tt])) AS by_treatment_type,\n"
        "     apoc.coll.frequencies(\n"
        "       apoc.coll.flatten([r IN rows | r.bfs])) AS by_background_factors,\n"
        "     apoc.coll.frequencies(\n"
        "       [p IN pub_rows WHERE p.doi IS NOT NULL | p.doi]) AS by_publication,\n"
        "     apoc.coll.frequencies(\n"
        "       [r IN rows WHERE r.aid IS NOT NULL | r.aid]) AS by_analysis\n"
        "RETURN total_matching, total_clusters,\n"
        "       genes_with_clusters, genes_without_clusters,\n"
        "       not_found, not_matched,\n"
        "       by_cluster_type, by_treatment_type, by_background_factors,\n"
        "       by_publication, by_analysis"
    )
    return cypher, params
```

- [ ] **Step 5: Implement updated `build_gene_clusters_by_gene`**

Key changes:
- Join CA: `MATCH (ca:ClusteringAnalysis)-[:ClusteringAnalysisHasGeneCluster]->(gc)`
- Compact: add `ca.id AS analysis_id`, `ca.name AS analysis_name`, `ca.treatment_type AS treatment_type`, `coalesce(ca.background_factors, []) AS background_factors`; `ca.cluster_type AS cluster_type` (from CA, not GC)
- Verbose: add `ca.cluster_method AS cluster_method`, `gc.member_count AS member_count`, `gc.functional_description AS cluster_functional_description`, `gc.behavioral_description AS cluster_behavioral_description`, `ca.treatment AS treatment`, `ca.light_condition AS light_condition`, `ca.experimental_context AS experimental_context`, `gc.peak_time_hours AS peak_time_hours`, `gc.period_hours AS period_hours`
- Remove: `source_paper`
- Publication filter: via `PublicationHasClusteringAnalysis` on CA

```python
def build_gene_clusters_by_gene(
    *,
    locus_tags: list[str],
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    publication_doi: list[str] | None = None,
    analysis_ids: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for gene_clusters_by_gene.

    RETURN keys (compact): locus_tag, gene_name, cluster_id, cluster_name,
    cluster_type, membership_score, analysis_id, analysis_name,
    treatment_type, background_factors.
    RETURN keys (verbose): adds cluster_method, member_count,
    cluster_functional_description, cluster_behavioral_description,
    treatment, light_condition, experimental_context, p_value,
    peak_time_hours, period_hours.
    """
    params: dict = {"locus_tags": locus_tags}

    ca_conditions: list[str] = []
    if cluster_type is not None:
        ca_conditions.append("ca.cluster_type = $cluster_type")
        params["cluster_type"] = cluster_type
    if treatment_type is not None:
        ca_conditions.append(
            "ANY(tt IN ca.treatment_type WHERE tt IN $treatment_type)")
        params["treatment_type"] = treatment_type
    if background_factors is not None:
        ca_conditions.append(
            "ANY(bf IN coalesce(ca.background_factors, [])"
            " WHERE bf IN $background_factors)")
        params["background_factors"] = background_factors
    if analysis_ids is not None:
        ca_conditions.append("ca.id IN $analysis_ids")
        params["analysis_ids"] = analysis_ids

    pub_match = ""
    if publication_doi is not None:
        pub_match = "MATCH (pub:Publication)-[:PublicationHasClusteringAnalysis]->(ca)\n"
        ca_conditions.append("pub.doi IN $publication_doi")
        params["publication_doi"] = publication_doi

    ca_where = ""
    if ca_conditions:
        ca_where = "WHERE " + " AND ".join(ca_conditions) + "\n"

    verbose_cols = ""
    if verbose:
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
        "MATCH (ca:ClusteringAnalysis)-[:ClusteringAnalysisHasGeneCluster]->(gc)\n"
        f"{pub_match}"
        f"{ca_where}"
        "RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,\n"
        "       gc.id AS cluster_id, gc.name AS cluster_name,\n"
        "       ca.cluster_type AS cluster_type,\n"
        "       r.membership_score AS membership_score,\n"
        "       ca.id AS analysis_id, ca.name AS analysis_name,\n"
        "       ca.treatment_type AS treatment_type,\n"
        f"       coalesce(ca.background_factors, []) AS background_factors{verbose_cols}\n"
        f"ORDER BY g.locus_tag, gc.id{skip_clause}{limit_clause}"
    )
    return cypher, params
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneClustersByGeneSummary tests/unit/test_query_builders.py::TestBuildGeneClustersByGene -v`
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: update gene_clusters_by_gene builders for ClusteringAnalysis schema"
```

---

## Task 4: Query builders — update `genes_in_cluster` + remove old builders

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for updated builders**

In `tests/unit/test_query_builders.py`, replace `TestBuildGenesInClusterSummary` and `TestBuildGenesInCluster`:

```python
class TestBuildGenesInClusterSummary:
    """Tests for build_genes_in_cluster_summary."""

    def test_basic_structure(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster_summary
        cypher, params = build_genes_in_cluster_summary(
            cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:1"])
        assert "Gene_in_gene_cluster" in cypher
        assert "total_matching" in cypher
        assert params["cluster_ids"] == ["cluster:msb4100087:med4_kmeans_nstarvation:1"]

    def test_with_organism_filter(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster_summary
        cypher, params = build_genes_in_cluster_summary(
            cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:1"],
            organism="MED4")
        assert "organism" in cypher.lower()
        assert params["organism"] == "MED4"

    def test_with_analysis_id(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster_summary
        cypher, params = build_genes_in_cluster_summary(
            cluster_ids=None,
            analysis_id="clustering_analysis:msb4100087:med4_kmeans_nstarvation")
        assert "ClusteringAnalysisHasGeneCluster" in cypher
        assert params["analysis_id"] == "clustering_analysis:msb4100087:med4_kmeans_nstarvation"
        assert "analysis_name" in cypher


class TestBuildGenesInCluster:
    """Tests for build_genes_in_cluster (detail builder)."""

    def test_returns_expected_columns(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, _ = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:1"])
        for col in ["locus_tag", "gene_name", "product", "gene_category",
                     "organism_name", "cluster_id", "cluster_name",
                     "membership_score"]:
            assert f"AS {col}" in cypher

    def test_verbose_uses_renamed_columns(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, _ = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:1"],
            verbose=True)
        for col in ["gene_function_description", "gene_summary",
                     "p_value", "cluster_functional_description",
                     "cluster_behavioral_description"]:
            assert f"AS {col}" in cypher
        # Old names must not appear
        assert "AS function_description" not in cypher
        assert "AS functional_description" not in cypher
        assert "AS behavioral_description" not in cypher

    def test_with_analysis_id(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, params = build_genes_in_cluster(
            cluster_ids=None,
            analysis_id="clustering_analysis:msb4100087:med4_kmeans_nstarvation")
        assert "ClusteringAnalysisHasGeneCluster" in cypher
        assert params["analysis_id"] == "clustering_analysis:msb4100087:med4_kmeans_nstarvation"

    def test_has_order_by(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, _ = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:1"])
        assert "ORDER BY" in cypher

    def test_offset_emits_skip(self):
        from multiomics_explorer.kg.queries_lib import build_genes_in_cluster
        cypher, params = build_genes_in_cluster(
            cluster_ids=["cluster:msb4100087:med4_kmeans_nstarvation:1"],
            limit=10, offset=5)
        assert "SKIP $offset" in cypher
        assert params["offset"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGenesInClusterSummary tests/unit/test_query_builders.py::TestBuildGenesInCluster -v`
Expected: FAIL (missing `analysis_id` param, old column names)

- [ ] **Step 3: Implement updated `build_genes_in_cluster_summary`**

Key changes:
- Add `analysis_id: str | None = None` parameter
- When `analysis_id` is provided: `MATCH (ca:ClusteringAnalysis {id: $analysis_id})-[:ClusteringAnalysisHasGeneCluster]->(gc:GeneCluster)` to resolve cluster IDs. Add `analysis_name` to RETURN.
- When `cluster_ids` is provided: existing UNWIND pattern

```python
def build_genes_in_cluster_summary(
    *,
    cluster_ids: list[str] | None = None,
    analysis_id: str | None = None,
    organism: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_in_cluster.

    RETURN keys: total_matching, by_organism, by_cluster,
    by_category_raw, not_found_clusters, not_matched_clusters.
    When analysis_id: adds analysis_name.
    """
    params: dict = {"organism": organism}

    organism_filter = (
        "AND ALL(word IN split(toLower($organism), ' ')"
        " WHERE toLower(g.organism_name) CONTAINS word)\n"
        if organism is not None else ""
    )

    if analysis_id is not None:
        params["analysis_id"] = analysis_id
        match_block = (
            "MATCH (ca:ClusteringAnalysis {id: $analysis_id})"
            "-[:ClusteringAnalysisHasGeneCluster]->(gc:GeneCluster)\n"
            "WITH gc, ca.name AS analysis_name\n"
            "OPTIONAL MATCH (gc)-[r:Gene_in_gene_cluster]->(g:Gene)\n"
            f"WHERE g IS NOT NULL {organism_filter}"
            "WITH gc.id AS cid, gc, g, analysis_name\n"
        )
        nf_nm_block = (
            "WITH collect(DISTINCT CASE WHEN g IS NULL THEN cid END) AS nm_raw,\n"
            "     collect(CASE WHEN g IS NOT NULL THEN\n"
            "       {lt: g.locus_tag, org: g.organism_name,\n"
            "        cat: coalesce(g.gene_category, 'Unknown'),\n"
            "        cid: cid, cname: gc.name} END) AS rows,\n"
            "     head(collect(analysis_name)) AS analysis_name\n"
            "WITH [] AS not_found_clusters,\n"
            "     [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_clusters,\n"
            "     rows, analysis_name\n"
        )
        extra_return = ", analysis_name"
    else:
        params["cluster_ids"] = cluster_ids
        match_block = (
            "UNWIND $cluster_ids AS cid\n"
            "OPTIONAL MATCH (gc:GeneCluster {id: cid})\n"
            "OPTIONAL MATCH (gc)-[r:Gene_in_gene_cluster]->(g:Gene)\n"
            f"WHERE g IS NOT NULL {organism_filter}"
            "WITH cid, gc, g\n"
        )
        nf_nm_block = (
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
        )
        extra_return = ""

    cypher = (
        f"{match_block}"
        f"{nf_nm_block}"
        "WITH not_found_clusters, not_matched_clusters,\n"
        "     size(rows) AS total_matching,\n"
        "     apoc.coll.frequencies([r IN rows | r.org]) AS by_organism,\n"
        "     apoc.coll.frequencies([r IN rows | r.cat]) AS by_category_raw,\n"
        "     [cid IN apoc.coll.toSet([r IN rows | r.cid]) |\n"
        "       {cluster_id: cid,\n"
        "        cluster_name: head([r IN rows WHERE r.cid = cid | r.cname]),\n"
        "        count: size([r IN rows WHERE r.cid = cid])}] AS by_cluster"
        + (", analysis_name\n" if analysis_id is not None else "\n")
        + "RETURN total_matching, by_organism, by_cluster, by_category_raw,\n"
        f"       not_found_clusters, not_matched_clusters{extra_return}"
    )
    return cypher, params
```

- [ ] **Step 4: Implement updated `build_genes_in_cluster`**

Key changes:
- Add `analysis_id: str | None = None` parameter
- When `analysis_id`: match through CA → GC → Gene
- Rename verbose columns: `g.function_description AS gene_function_description`, `gc.functional_description AS cluster_functional_description`, `gc.behavioral_description AS cluster_behavioral_description`

```python
def build_genes_in_cluster(
    *,
    cluster_ids: list[str] | None = None,
    analysis_id: str | None = None,
    organism: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_in_cluster.

    RETURN keys (compact): locus_tag, gene_name, product, gene_category,
    organism_name, cluster_id, cluster_name, membership_score.
    RETURN keys (verbose): adds gene_function_description, gene_summary,
    p_value, cluster_functional_description, cluster_behavioral_description.
    """
    params: dict = {}

    verbose_cols = ""
    if verbose:
        verbose_cols = (
            ",\n       g.function_description AS gene_function_description"
            ",\n       g.gene_summary AS gene_summary"
            ",\n       r.p_value AS p_value"
            ",\n       gc.functional_description AS cluster_functional_description"
            ",\n       gc.behavioral_description AS cluster_behavioral_description"
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

    if analysis_id is not None:
        params["analysis_id"] = analysis_id
        cypher = (
            "MATCH (ca:ClusteringAnalysis {id: $analysis_id})"
            "-[:ClusteringAnalysisHasGeneCluster]->(gc:GeneCluster)"
            "-[r:Gene_in_gene_cluster]->(g:Gene)\n"
        )
    elif cluster_ids is not None:
        params["cluster_ids"] = cluster_ids
        cypher = (
            "UNWIND $cluster_ids AS cid\n"
            "MATCH (gc:GeneCluster {id: cid})-[r:Gene_in_gene_cluster]->(g:Gene)\n"
        )
    # Organism filter
    if organism is not None:
        params["organism"] = organism
        cypher += (
            "WHERE ALL(word IN split(toLower($organism), ' ')"
            " WHERE toLower(g.organism_name) CONTAINS word)\n"
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

- [ ] **Step 5: Remove old builders and helper**

Delete from `multiomics_explorer/kg/queries_lib.py`:
- `_gene_cluster_where` function
- `build_list_gene_clusters_summary` function
- `build_list_gene_clusters` function

Also delete `TestGeneClusterWhere` from `tests/unit/test_query_builders.py` (if not already replaced).

- [ ] **Step 6: Run all cluster-related query builder tests**

Run: `pytest tests/unit/test_query_builders.py -k "Cluster" -v`
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: update genes_in_cluster builders, remove old list_gene_clusters builders"
```

---

## Task 5: API layer — `list_clustering_analyses` + remove old

**Files:**
- Modify: `multiomics_explorer/api/functions.py`
- Modify: `multiomics_explorer/api/__init__.py`
- Modify: `multiomics_explorer/__init__.py`
- Test: `tests/unit/test_api_functions.py`

- [ ] **Step 1: Write failing test for `list_clustering_analyses`**

In `tests/unit/test_api_functions.py`, replace `TestListGeneClusters` with:

```python
class TestListClusteringAnalyses:
    """Tests for list_clustering_analyses API function."""

    def _make_summary_row(self):
        return {
            "total_entries": 2,
            "total_matching": 2,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 1},
                            {"item": "Prochlorococcus MIT9313", "count": 1}],
            "by_cluster_type": [{"item": "response_pattern", "count": 2}],
            "by_treatment_type": [{"item": "nitrogen_stress", "count": 2}],
            "by_background_factors": [{"item": "axenic", "count": 2}],
            "by_omics_type": [{"item": "MICROARRAY", "count": 2}],
        }

    def _make_detail_row(self):
        return {
            "analysis_id": "clustering_analysis:msb4100087:med4_kmeans_nstarvation",
            "name": "MED4 K-means N-starvation clusters",
            "organism_name": "Prochlorococcus MED4",
            "cluster_method": "K-means (K=9)",
            "cluster_type": "response_pattern",
            "cluster_count": 9,
            "total_gene_count": 410,
            "treatment_type": ["nitrogen_stress"],
            "background_factors": ["axenic", "continuous_light"],
            "omics_type": "MICROARRAY",
            "experiment_ids": [],
            "clusters": [
                {"cluster_id": "cluster:msb4100087:med4_kmeans_nstarvation:1",
                 "name": "Cluster 1", "member_count": 5},
            ],
        }

    def test_summary_mode(self, mock_conn):
        mock_conn.execute_query.return_value = [self._make_summary_row()]
        result = api.list_clustering_analyses(summary=True, conn=mock_conn)
        assert result["total_entries"] == 2
        assert result["total_matching"] == 2
        assert result["results"] == []
        assert result["returned"] == 0
        assert result["truncated"] is True
        assert mock_conn.execute_query.call_count == 1  # summary only

    def test_detail_mode(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [self._make_summary_row()],
            [self._make_detail_row()],
        ]
        result = api.list_clustering_analyses(limit=5, conn=mock_conn)
        assert result["returned"] == 1
        assert result["results"][0]["analysis_id"] == \
            "clustering_analysis:msb4100087:med4_kmeans_nstarvation"
        assert len(result["results"][0]["clusters"]) == 1

    def test_empty_search_text_raises(self, mock_conn):
        with pytest.raises(ValueError, match="search_text must not be empty"):
            api.list_clustering_analyses(search_text="", conn=mock_conn)

    def test_by_organism_rename(self, mock_conn):
        mock_conn.execute_query.return_value = [self._make_summary_row()]
        result = api.list_clustering_analyses(summary=True, conn=mock_conn)
        assert result["by_organism"][0]["organism_name"] == "Prochlorococcus MED4"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_api_functions.py::TestListClusteringAnalyses -v`
Expected: FAIL with AttributeError (function doesn't exist)

- [ ] **Step 3: Implement `list_clustering_analyses` and remove `list_gene_clusters`**

In `multiomics_explorer/api/functions.py`:
1. Delete the `list_gene_clusters` function
2. Add `list_clustering_analyses` following the same 2-query pattern. Import the new builders:

```python
def list_clustering_analyses(
    search_text: str | None = None,
    organism: str | None = None,
    cluster_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    omics_type: str | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    analysis_ids: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Browse, search, and filter clustering analyses.

    Returns dict with keys: total_entries, total_matching,
    by_organism, by_cluster_type, by_treatment_type, by_background_factors,
    by_omics_type, returned, offset, truncated, results.
    When search_text: adds score_max, score_median.
    Per result: analysis_id, name, organism_name, cluster_method,
    cluster_type, cluster_count, total_gene_count, treatment_type,
    background_factors, omics_type, experiment_ids, clusters.
    Verbose adds: treatment, light_condition, experimental_context.
    Inline clusters (compact): cluster_id, name, member_count.
    Inline clusters (verbose): adds functional_description,
    behavioral_description, peak_time_hours, period_hours.
    """
    if search_text is not None and not search_text.strip():
        raise ValueError("search_text must not be empty.")
    if summary:
        limit = 0

    conn = _default_conn(conn)

    filter_kwargs = dict(
        organism=organism, cluster_type=cluster_type,
        treatment_type=treatment_type, background_factors=background_factors,
        omics_type=omics_type, publication_doi=publication_doi,
        experiment_ids=experiment_ids, analysis_ids=analysis_ids,
    )

    effective_text = search_text

    # Summary query — always runs
    try:
        sum_cypher, sum_params = build_list_clustering_analyses_summary(
            search_text=effective_text, **filter_kwargs)
        raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
    except Neo4jClientError:
        if search_text is not None:
            logger.debug("list_clustering_analyses: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            sum_cypher, sum_params = build_list_clustering_analyses_summary(
                search_text=effective_text, **filter_kwargs)
            raw_summary = conn.execute_query(sum_cypher, **sum_params)[0]
        else:
            raise

    total_matching = raw_summary["total_matching"]
    envelope = {
        "total_entries": raw_summary["total_entries"],
        "total_matching": total_matching,
        "by_organism": _rename_freq(raw_summary["by_organism"], "organism_name"),
        "by_cluster_type": _rename_freq(
            raw_summary["by_cluster_type"], "cluster_type"),
        "by_treatment_type": _rename_freq(
            raw_summary["by_treatment_type"], "treatment_type"),
        "by_background_factors": _rename_freq(
            raw_summary["by_background_factors"], "background_factor"),
        "by_omics_type": _rename_freq(raw_summary["by_omics_type"], "omics_type"),
    }

    if search_text is not None:
        envelope["score_max"] = raw_summary.get("score_max")
        envelope["score_median"] = raw_summary.get("score_median")
    else:
        envelope["score_max"] = None
        envelope["score_median"] = None

    if limit == 0:
        envelope["returned"] = 0
        envelope["offset"] = offset
        envelope["truncated"] = total_matching > 0
        envelope["results"] = []
        return envelope

    try:
        det_cypher, det_params = build_list_clustering_analyses(
            search_text=effective_text, **filter_kwargs,
            verbose=verbose, limit=limit, offset=offset)
        results = conn.execute_query(det_cypher, **det_params)
    except Neo4jClientError:
        if search_text is not None and effective_text == search_text:
            logger.debug("list_clustering_analyses detail: Lucene parse error, retrying")
            effective_text = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            det_cypher, det_params = build_list_clustering_analyses(
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

Note: Extract `_rename_freq` as a module-level helper if not already (it's currently duplicated across functions — check if a shared version exists, otherwise keep the local pattern).

- [ ] **Step 4: Update exports**

In `multiomics_explorer/api/__init__.py`:
- Replace `list_gene_clusters` with `list_clustering_analyses` in imports and `__all__`

In `multiomics_explorer/__init__.py`:
- Add `list_clustering_analyses`, `gene_clusters_by_gene`, `genes_in_cluster` to imports and `__all__`

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_api_functions.py::TestListClusteringAnalyses -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/api/__init__.py multiomics_explorer/__init__.py tests/unit/test_api_functions.py
git commit -m "feat: add list_clustering_analyses API, remove list_gene_clusters"
```

---

## Task 6: API layer — update `gene_clusters_by_gene` + `genes_in_cluster`

**Files:**
- Modify: `multiomics_explorer/api/functions.py`
- Test: `tests/unit/test_api_functions.py`

- [ ] **Step 1: Write failing tests for updated `gene_clusters_by_gene`**

In `tests/unit/test_api_functions.py`, replace `TestGeneClustersByGene`. Key test updates:
- Summary row includes `by_analysis`
- Detail results include `analysis_id`, `analysis_name`, `treatment_type`, `background_factors`
- New `analysis_ids` parameter
- No `source_paper` in results

```python
class TestGeneClustersByGene:
    """Tests for gene_clusters_by_gene API function."""

    def _make_summary_row(self):
        return {
            "total_matching": 1,
            "total_clusters": 1,
            "genes_with_clusters": 1,
            "genes_without_clusters": 0,
            "not_found": [],
            "not_matched": [],
            "by_cluster_type": [{"item": "response_pattern", "count": 1}],
            "by_treatment_type": [{"item": "nitrogen_stress", "count": 1}],
            "by_background_factors": [{"item": "axenic", "count": 1}],
            "by_publication": [],
            "by_analysis": [{"item": "clustering_analysis:msb4100087:med4_kmeans_nstarvation", "count": 1}],
        }

    def test_envelope_has_by_analysis(self, mock_conn):
        mock_conn.execute_query.return_value = [self._make_summary_row()]
        result = api.gene_clusters_by_gene(
            ["PMM0370"], summary=True, conn=mock_conn)
        assert "by_analysis" in result
        assert result["by_analysis"][0]["analysis_id"] == \
            "clustering_analysis:msb4100087:med4_kmeans_nstarvation"

    def test_empty_locus_tags_raises(self, mock_conn):
        with pytest.raises(ValueError, match="locus_tags must not be empty"):
            api.gene_clusters_by_gene([], conn=mock_conn)
```

- [ ] **Step 2: Write failing tests for updated `genes_in_cluster`**

In `tests/unit/test_api_functions.py`, replace `TestGenesInCluster`:

```python
class TestGenesInCluster:
    """Tests for genes_in_cluster API function."""

    def test_mutual_exclusion(self, mock_conn):
        with pytest.raises(ValueError, match="cluster_ids.*analysis_id"):
            api.genes_in_cluster(
                cluster_ids=["cluster:x:y:1"],
                analysis_id="clustering_analysis:x:y",
                conn=mock_conn)

    def test_neither_provided_raises(self, mock_conn):
        with pytest.raises(ValueError, match="cluster_ids.*analysis_id"):
            api.genes_in_cluster(conn=mock_conn)

    def test_analysis_id_mode(self, mock_conn):
        mock_conn.execute_query.side_effect = [
            [{"total_matching": 5, "by_organism": [], "by_category_raw": [],
              "by_cluster": [], "not_found_clusters": [],
              "not_matched_clusters": [],
              "analysis_name": "MED4 K-means N-starvation clusters"}],
            [{"locus_tag": "PMM0370", "gene_name": "cynA",
              "product": "cyanate transporter", "gene_category": "N-metabolism",
              "organism_name": "Prochlorococcus MED4",
              "cluster_id": "cluster:msb4100087:med4_kmeans_nstarvation:1",
              "cluster_name": "Cluster 1", "membership_score": None}],
        ]
        result = api.genes_in_cluster(
            analysis_id="clustering_analysis:msb4100087:med4_kmeans_nstarvation",
            limit=5, conn=mock_conn)
        assert result["analysis_name"] == "MED4 K-means N-starvation clusters"
        assert result["returned"] == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_api_functions.py::TestGeneClustersByGene tests/unit/test_api_functions.py::TestGenesInCluster -v`
Expected: FAIL

- [ ] **Step 4: Update `gene_clusters_by_gene` in api/functions.py**

Key changes:
- Add `analysis_ids` parameter, pass to builders
- Add `by_analysis` to envelope: `_rename_freq(raw_summary["by_analysis"], "analysis_id")`
- Update builder import names if changed

- [ ] **Step 5: Update `genes_in_cluster` in api/functions.py**

Key changes:
- Change signature: `cluster_ids: list[str] | None = None, analysis_id: str | None = None`
- Add mutual exclusion validation:
```python
if cluster_ids is not None and analysis_id is not None:
    raise ValueError("Provide cluster_ids or analysis_id, not both.")
if cluster_ids is None and analysis_id is None:
    raise ValueError("Must provide cluster_ids or analysis_id.")
```
- Pass `analysis_id` to builders
- When `analysis_id`: add `"analysis_name"` to envelope from summary result
- Renamed fields flow through from query builder (no change needed in API — it returns raw results)

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit/test_api_functions.py -k "Cluster" -v`
Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/api/functions.py tests/unit/test_api_functions.py
git commit -m "feat: update gene_clusters_by_gene and genes_in_cluster API functions"
```

---

## Task 7: MCP tool layer — `list_clustering_analyses` + remove old

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Test: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 1: Update `EXPECTED_TOOLS`**

In `tests/unit/test_tool_wrappers.py`, replace `"list_gene_clusters"` with `"list_clustering_analyses"` in the `EXPECTED_TOOLS` list.

- [ ] **Step 2: Remove old `list_gene_clusters` tool and Pydantic models**

In `multiomics_explorer/mcp_server/tools.py`, delete:
- `ListGeneClustersResult` model
- `ListGeneClustersResponse` model
- `list_gene_clusters` tool function
- All breakdown models specific to `list_gene_clusters` (keep shared ones used by other cluster tools)

- [ ] **Step 3: Add `list_clustering_analyses` tool**

Add Pydantic models and tool function. Follow the registration pattern in tools.py:

```python
    # ── Clustering Analysis models ────────────────────────────────────

    class ClusteringAnalysisOrganismBreakdown(BaseModel):
        organism_name: str = Field(description="Organism name")
        count: int = Field(description="Analyses for this organism")

    class ClusteringAnalysisTypeBreakdown(BaseModel):
        cluster_type: str = Field(description="Cluster type category")
        count: int = Field(description="Analyses of this type")

    class ClusteringAnalysisTreatmentBreakdown(BaseModel):
        treatment_type: str = Field(description="Treatment type")
        count: int = Field(description="Analyses for this treatment")

    class ClusteringAnalysisBackgroundFactorBreakdown(BaseModel):
        background_factor: str = Field(description="Background factor")
        count: int = Field(description="Analyses with this factor")

    class ClusteringAnalysisOmicsBreakdown(BaseModel):
        omics_type: str = Field(description="Omics type")
        count: int = Field(description="Analyses of this omics type")

    class InlineCluster(BaseModel):
        cluster_id: str = Field(description="GeneCluster node ID")
        name: str = Field(description="Cluster name (e.g. 'Cluster 1')")
        member_count: int = Field(description="Gene count in cluster")
        # verbose-only
        functional_description: str | None = Field(default=None,
            description="What cluster genes ARE")
        behavioral_description: str | None = Field(default=None,
            description="What cluster genes DO together")
        peak_time_hours: float | None = Field(default=None,
            description="Peak expression time (diel only)")
        period_hours: float | None = Field(default=None,
            description="Oscillation period (diel only)")

    class ListClusteringAnalysesResult(BaseModel):
        analysis_id: str = Field(
            description="ClusteringAnalysis node ID (e.g. 'clustering_analysis:msb4100087:med4_kmeans_nstarvation')")
        name: str = Field(
            description="Human-readable analysis name")
        organism_name: str = Field(
            description="Organism (e.g. 'Prochlorococcus MED4')")
        cluster_method: str = Field(
            description="Algorithm (e.g. 'K-means (K=9)')")
        cluster_type: str = Field(
            description="Category: diel_cycle, time_series_dynamics, response_pattern")
        cluster_count: int = Field(
            description="Number of child clusters")
        total_gene_count: int = Field(
            description="Total genes across all clusters")
        treatment_type: list[str] = Field(
            description="Treatment type categories")
        background_factors: list[str] = Field(default_factory=list,
            description="Background experimental factors")
        omics_type: str = Field(
            description="MICROARRAY, RNASEQ, PROTEOMICS")
        experiment_ids: list[str] = Field(default_factory=list,
            description="Linked experiment IDs (may be empty)")
        clusters: list[InlineCluster] = Field(
            description="Child clusters inline")
        score: float | None = Field(default=None,
            description="Full-text relevance score (when searching)")
        # verbose-only
        treatment: str | None = Field(default=None,
            description="Free-text condition description")
        light_condition: str | None = Field(default=None,
            description="Light regime")
        experimental_context: str | None = Field(default=None,
            description="Setup details")

    class ListClusteringAnalysesResponse(BaseModel):
        total_entries: int = Field(
            description="Total analyses in KG (unfiltered)")
        total_matching: int = Field(
            description="Analyses matching filters")
        by_organism: list[ClusteringAnalysisOrganismBreakdown] = Field(
            description="Analyses per organism")
        by_cluster_type: list[ClusteringAnalysisTypeBreakdown] = Field(
            description="Analyses per cluster type")
        by_treatment_type: list[ClusteringAnalysisTreatmentBreakdown] = Field(
            description="Analyses per treatment type")
        by_background_factors: list[ClusteringAnalysisBackgroundFactorBreakdown] = Field(
            description="Analyses per background factor")
        by_omics_type: list[ClusteringAnalysisOmicsBreakdown] = Field(
            description="Analyses per omics type")
        score_max: float | None = Field(default=None,
            description="Highest relevance score (search only)")
        score_median: float | None = Field(default=None,
            description="Median relevance score (search only)")
        returned: int = Field(description="Results in this response")
        offset: int = Field(default=0, description="Offset into result set")
        truncated: bool = Field(
            description="True if total_matching > offset + returned")
        results: list[ListClusteringAnalysesResult] = Field(
            default_factory=list, description="One row per analysis")

    @mcp.tool(
        tags={"clusters", "analyses"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                      "idempotentHint": True, "openWorldHint": False},
    )
    async def list_clustering_analyses(
        ctx: Context,
        search_text: Annotated[str | None, Field(
            description="Lucene full-text query over analysis name, treatment, "
            "experimental_context. Results ranked by score.",
        )] = None,
        organism: Annotated[str | None, Field(
            description="Filter by organism (case-insensitive partial match).",
        )] = None,
        cluster_type: Annotated[str | None, Field(
            description="Filter: 'diel_cycle', 'time_series_dynamics', "
            "or 'response_pattern'.",
        )] = None,
        treatment_type: Annotated[list[str] | None, Field(
            description="Filter by treatment type(s). E.g. ['nitrogen_stress'].",
        )] = None,
        background_factors: Annotated[list[str] | None, Field(
            description="Filter by background factors. "
            "E.g. ['axenic', 'diel_cycle'].",
        )] = None,
        omics_type: Annotated[str | None, Field(
            description="Filter: 'MICROARRAY', 'RNASEQ', or 'PROTEOMICS'.",
        )] = None,
        experiment_ids: Annotated[list[str] | None, Field(
            description="Filter by linked experiment IDs.",
        )] = None,
        publication_doi: Annotated[list[str] | None, Field(
            description="Filter by publication DOI(s).",
        )] = None,
        analysis_ids: Annotated[list[str] | None, Field(
            description="Filter to specific ClusteringAnalysis node IDs.",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include treatment, light_condition, experimental_context "
            "on analyses, and descriptions on inline clusters.",
        )] = False,
        limit: Annotated[int, Field(description="Max results.", ge=1)] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0)] = 0,
    ) -> ListClusteringAnalysesResponse:
        """Browse, search, and filter clustering analyses.

        Each analysis groups related gene clusters from a publication.
        Returns analyses with inline cluster children. Search across
        analysis names, treatments, and experimental context.

        Returns analysis IDs for use with genes_in_cluster(analysis_id=...).
        """
        await ctx.info(f"list_clustering_analyses search_text={search_text!r} "
                       f"organism={organism} limit={limit}")
        try:
            conn = _conn(ctx)
            data = api.list_clustering_analyses(
                search_text=search_text, organism=organism,
                cluster_type=cluster_type, treatment_type=treatment_type,
                background_factors=background_factors,
                omics_type=omics_type, publication_doi=publication_doi,
                experiment_ids=experiment_ids, analysis_ids=analysis_ids,
                summary=summary, verbose=verbose, limit=limit, offset=offset,
                conn=conn,
            )
            # Wrap results with Pydantic models
            for r in data["results"]:
                r["clusters"] = [InlineCluster(**c) for c in r.get("clusters", [])]
            results = [ListClusteringAnalysesResult(**r) for r in data["results"]]
            by_organism = [ClusteringAnalysisOrganismBreakdown(**b) for b in data["by_organism"]]
            by_cluster_type = [ClusteringAnalysisTypeBreakdown(**b) for b in data["by_cluster_type"]]
            by_treatment_type = [ClusteringAnalysisTreatmentBreakdown(**b) for b in data["by_treatment_type"]]
            by_background_factors = [ClusteringAnalysisBackgroundFactorBreakdown(**b) for b in data["by_background_factors"]]
            by_omics_type = [ClusteringAnalysisOmicsBreakdown(**b) for b in data["by_omics_type"]]
            response = ListClusteringAnalysesResponse(
                total_entries=data["total_entries"],
                total_matching=data["total_matching"],
                by_organism=by_organism,
                by_cluster_type=by_cluster_type,
                by_treatment_type=by_treatment_type,
                by_background_factors=by_background_factors,
                by_omics_type=by_omics_type,
                score_max=data.get("score_max"),
                score_median=data.get("score_median"),
                returned=data["returned"],
                offset=data.get("offset", 0),
                truncated=data["truncated"],
                results=results,
            )
            await ctx.info(f"Returning {response.returned} of {response.total_matching} analyses")
            return response
        except ValueError as e:
            await ctx.warning(f"list_clustering_analyses error: {e}")
            raise ToolError(str(e))
        except Exception as e:
            await ctx.error(f"list_clustering_analyses unexpected error: {e}")
            raise ToolError(f"Error in list_clustering_analyses: {e}")
```

- [ ] **Step 4: Write wrapper test**

In `tests/unit/test_tool_wrappers.py`, replace `TestListGeneClustersWrapper`:

```python
class TestListClusteringAnalysesWrapper:
    _SAMPLE_API_RETURN = {
        "total_entries": 2, "total_matching": 1,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
        "by_cluster_type": [{"cluster_type": "response_pattern", "count": 1}],
        "by_treatment_type": [{"treatment_type": "nitrogen_stress", "count": 1}],
        "by_background_factors": [{"background_factor": "axenic", "count": 1}],
        "by_omics_type": [{"omics_type": "MICROARRAY", "count": 1}],
        "score_max": None, "score_median": None,
        "returned": 1, "offset": 0, "truncated": False,
        "results": [{
            "analysis_id": "clustering_analysis:msb4100087:med4_kmeans_nstarvation",
            "name": "MED4 K-means N-starvation clusters",
            "organism_name": "Prochlorococcus MED4",
            "cluster_method": "K-means (K=9)",
            "cluster_type": "response_pattern",
            "cluster_count": 9, "total_gene_count": 410,
            "treatment_type": ["nitrogen_stress"],
            "background_factors": ["axenic", "continuous_light"],
            "omics_type": "MICROARRAY",
            "experiment_ids": [],
            "clusters": [{"cluster_id": "cluster:msb4100087:med4_kmeans_nstarvation:1",
                           "name": "Cluster 1", "member_count": 5}],
        }],
    }

    @pytest.mark.asyncio
    async def test_returns_response(self, tool_fns, mock_ctx):
        with patch(
            "multiomics_explorer.api.functions.list_clustering_analyses",
            return_value=self._SAMPLE_API_RETURN,
        ):
            result = await tool_fns["list_clustering_analyses"](
                mock_ctx, limit=5)
        assert result.total_entries == 2
        assert result.returned == 1
        assert result.results[0].analysis_id == \
            "clustering_analysis:msb4100087:med4_kmeans_nstarvation"
        assert len(result.results[0].clusters) == 1
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_tool_wrappers.py::TestToolRegistration tests/unit/test_tool_wrappers.py::TestListClusteringAnalysesWrapper -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "feat: add list_clustering_analyses MCP tool, remove list_gene_clusters"
```

---

## Task 8: MCP tool layer — update `gene_clusters_by_gene` + `genes_in_cluster`

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`
- Test: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 1: Update `gene_clusters_by_gene` Pydantic models and tool params**

In `multiomics_explorer/mcp_server/tools.py`:
- `GeneClustersByGeneResult`: add `analysis_id`, `analysis_name`, `treatment_type`, `background_factors` to compact. Add `cluster_method`, `member_count` to verbose. Rename `functional_description` → `cluster_functional_description`, `behavioral_description` → `cluster_behavioral_description`. Remove `source_paper`.
- `GeneClustersByGeneResponse`: add `by_analysis` breakdown list.
- Tool function: add `analysis_ids` parameter. Add `by_analysis` breakdown construction.
- Add `GeneClusterAnalysisBreakdown` model:
```python
    class GeneClusterAnalysisBreakdown(BaseModel):
        analysis_id: str = Field(description="ClusteringAnalysis node ID")
        count: int = Field(description="Gene x cluster rows for this analysis")
```

- [ ] **Step 2: Update `genes_in_cluster` Pydantic models and tool params**

In `multiomics_explorer/mcp_server/tools.py`:
- Tool function: change `cluster_ids` to optional, add `analysis_id` parameter. Add mutual exclusion validation (or let API handle it).
- `GenesInClusterResponse`: add `analysis_name` field.
- `GenesInClusterResult`: rename `function_description` → `gene_function_description`, `functional_description` → `cluster_functional_description`, `behavioral_description` → `cluster_behavioral_description`.

- [ ] **Step 3: Update wrapper tests**

In `tests/unit/test_tool_wrappers.py`, replace `TestGeneClustersByGeneWrapper` and `TestGenesInClusterWrapper` with updated tests that validate new fields and parameters.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_tool_wrappers.py -k "Cluster" -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_wrappers.py
git commit -m "feat: update gene_clusters_by_gene and genes_in_cluster MCP tools"
```

---

## Task 9: Analysis utility — `analyses_to_dataframe`

**Files:**
- Modify: `multiomics_explorer/analysis/frames.py`
- Modify: `multiomics_explorer/analysis/__init__.py`
- Modify: `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/to_dataframe.md`
- Test: new tests in `tests/unit/test_analysis_frames.py` (or add to existing)

- [ ] **Step 1: Write failing test**

```python
class TestAnalysesToDataframe:
    def test_flattens_analysis_x_cluster(self):
        from multiomics_explorer.analysis import analyses_to_dataframe
        result = {
            "total_entries": 1, "total_matching": 1,
            "results": [{
                "analysis_id": "ca:1",
                "name": "Analysis 1",
                "organism_name": "MED4",
                "cluster_method": "K-means",
                "cluster_type": "response_pattern",
                "cluster_count": 2,
                "total_gene_count": 20,
                "treatment_type": ["nitrogen_stress"],
                "background_factors": ["axenic"],
                "omics_type": "MICROARRAY",
                "experiment_ids": [],
                "clusters": [
                    {"cluster_id": "c:1", "name": "Cluster 1", "member_count": 10},
                    {"cluster_id": "c:2", "name": "Cluster 2", "member_count": 10},
                ],
            }],
        }
        df = analyses_to_dataframe(result)
        assert len(df) == 2  # one row per cluster
        assert list(df["cluster_id"]) == ["c:1", "c:2"]
        assert list(df["analysis_id"]) == ["ca:1", "ca:1"]
        assert "clusters" not in df.columns

    def test_empty_results(self):
        from multiomics_explorer.analysis import analyses_to_dataframe
        result = {"results": []}
        df = analyses_to_dataframe(result)
        assert df.empty

    def test_no_results_key_raises(self):
        from multiomics_explorer.analysis import analyses_to_dataframe
        with pytest.raises(ValueError, match="results"):
            analyses_to_dataframe({"foo": "bar"})

    def test_verbose_cluster_fields(self):
        from multiomics_explorer.analysis import analyses_to_dataframe
        result = {
            "results": [{
                "analysis_id": "ca:1", "name": "A1",
                "organism_name": "MED4", "cluster_method": "K-means",
                "cluster_type": "response_pattern", "cluster_count": 1,
                "total_gene_count": 5, "treatment_type": ["ns"],
                "background_factors": [], "omics_type": "MICROARRAY",
                "experiment_ids": [],
                "clusters": [{
                    "cluster_id": "c:1", "name": "C1", "member_count": 5,
                    "functional_description": "transport genes",
                    "behavioral_description": "upregulated early",
                    "peak_time_hours": None, "period_hours": None,
                }],
            }],
        }
        df = analyses_to_dataframe(result)
        assert "cluster_functional_description" in df.columns
        assert "cluster_behavioral_description" in df.columns
        assert df.iloc[0]["cluster_functional_description"] == "transport genes"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_analysis_frames.py::TestAnalysesToDataframe -v` (or wherever the test lives)
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `analyses_to_dataframe`**

In `multiomics_explorer/analysis/frames.py`:

```python
def analyses_to_dataframe(result: dict) -> pd.DataFrame:
    """Convert a ``list_clustering_analyses`` result to an analysis × cluster DataFrame.

    Parameters
    ----------
    result:
        Raw dict returned by ``list_clustering_analyses()``.

    Returns
    -------
    pd.DataFrame
        One row per analysis × cluster. Analysis fields repeat on each row.
    """
    if "results" not in result:
        raise ValueError(
            "Expected a dict with a 'results' key. "
            "Got keys: " + ", ".join(sorted(result.keys()))
        )
    rows_list = result["results"]
    if not rows_list:
        return pd.DataFrame()
    records = []
    for analysis in rows_list:
        base = {k: v for k, v in analysis.items() if k != "clusters"}
        clusters = analysis.get("clusters", [])
        if clusters:
            for cluster in clusters:
                record = {**base}
                record["cluster_id"] = cluster.get("cluster_id")
                record["cluster_name"] = cluster.get("name")
                record["cluster_member_count"] = cluster.get("member_count")
                record["cluster_functional_description"] = cluster.get(
                    "functional_description")
                record["cluster_behavioral_description"] = cluster.get(
                    "behavioral_description")
                record["cluster_peak_time_hours"] = cluster.get(
                    "peak_time_hours")
                record["cluster_period_hours"] = cluster.get("period_hours")
                records.append(record)
        else:
            record = {**base}
            record["cluster_id"] = None
            record["cluster_name"] = None
            record["cluster_member_count"] = None
            record["cluster_functional_description"] = None
            record["cluster_behavioral_description"] = None
            record["cluster_peak_time_hours"] = None
            record["cluster_period_hours"] = None
            records.append(record)
    df = pd.DataFrame(records)
    if df.empty:
        return df
    return _flatten_columns(df)
```

Also add to `_DEDICATED_FUNCTIONS`:
```python
_DEDICATED_FUNCTIONS: dict[str, str] = {
    "response_summary": "profile_summary_to_dataframe()",
    "timepoints": "experiments_to_dataframe()",
    "clusters": "analyses_to_dataframe()",
}
```

- [ ] **Step 4: Export from `analysis/__init__.py`**

Add `analyses_to_dataframe` to imports and `__all__`.

- [ ] **Step 5: Update `to_dataframe.md` resource doc**

Add a section for `analyses_to_dataframe` following the existing pattern in `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/to_dataframe.md`.

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_analysis_frames.py::TestAnalysesToDataframe -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/analysis/frames.py multiomics_explorer/analysis/__init__.py multiomics_explorer/skills/multiomics-kg-guide/references/analysis/to_dataframe.md tests/unit/test_analysis_frames.py
git commit -m "feat: add analyses_to_dataframe for list_clustering_analyses"
```

---

## Task 10: CLI commands

**Files:**
- Modify: `multiomics_explorer/cli/main.py`

- [ ] **Step 1: Add `list-clustering-analyses` command**

```python
@app.command("list-clustering-analyses")
def list_clustering_analyses_cmd(
    search_text: str = typer.Option(None, "--search", "-s", help="Full-text search"),
    organism: str = typer.Option(None, "--organism", "-o", help="Filter by organism"),
    cluster_type: str = typer.Option(None, "--cluster-type", help="Filter by cluster type"),
    treatment_type: list[str] = typer.Option(None, "--treatment-type", help="Filter by treatment type"),
    summary: bool = typer.Option(False, "--summary", help="Summary only"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Include verbose fields"),
    limit: int = typer.Option(10, "--limit", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Browse and search clustering analyses."""
    from multiomics_explorer.api.functions import list_clustering_analyses
    from multiomics_explorer.kg.connection import GraphConnection

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        try:
            result = list_clustering_analyses(
                search_text=search_text, organism=organism,
                cluster_type=cluster_type, treatment_type=treatment_type,
                summary=summary, verbose=verbose, limit=limit, conn=conn,
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)

        if json_output:
            console.print(json.dumps(result, indent=2, default=str))
        else:
            console.print(f"[bold]Matching:[/bold] {result['total_matching']} of {result['total_entries']} analyses")
            for r in result["results"]:
                console.print(f"\n[bold]{r['name']}[/bold] ({r['analysis_id']})")
                console.print(f"  Organism: {r['organism_name']}  Method: {r['cluster_method']}")
                console.print(f"  Clusters: {r['cluster_count']}  Genes: {r['total_gene_count']}")
                for c in r.get("clusters", []):
                    console.print(f"    - {c['name']} ({c['member_count']} genes)")
            if result["truncated"]:
                console.print(f"\n[dim]Showing {result['returned']} of {result['total_matching']} (increase --limit)[/dim]")
```

- [ ] **Step 2: Add `gene-clusters-by-gene` command**

```python
@app.command("gene-clusters-by-gene")
def gene_clusters_by_gene_cmd(
    locus_tags: list[str] = typer.Argument(help="Gene locus tags"),
    summary: bool = typer.Option(False, "--summary", help="Summary only"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Include verbose fields"),
    limit: int = typer.Option(20, "--limit", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Find which gene clusters contain the given genes."""
    from multiomics_explorer.api.functions import gene_clusters_by_gene
    from multiomics_explorer.kg.connection import GraphConnection

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        try:
            result = gene_clusters_by_gene(
                locus_tags, summary=summary, verbose=verbose,
                limit=limit, conn=conn,
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)

        if json_output:
            console.print(json.dumps(result, indent=2, default=str))
        else:
            console.print(f"[bold]Matches:[/bold] {result['total_matching']} gene×cluster rows")
            console.print(f"  Clusters: {result['total_clusters']}  "
                          f"Genes with clusters: {result['genes_with_clusters']}")
            if result["not_found"]:
                console.print(f"  [yellow]Not found: {', '.join(result['not_found'])}[/yellow]")
            for r in result["results"]:
                console.print(f"  {r['locus_tag']} → {r['cluster_name']} ({r['analysis_name']})")
            if result["truncated"]:
                console.print(f"\n[dim]Showing {result['returned']} of {result['total_matching']}[/dim]")
```

- [ ] **Step 3: Add `genes-in-cluster` command**

```python
@app.command("genes-in-cluster")
def genes_in_cluster_cmd(
    cluster_ids: list[str] = typer.Argument(None, help="GeneCluster node IDs"),
    analysis_id: str = typer.Option(None, "--analysis-id", "-a",
        help="ClusteringAnalysis ID (alternative to cluster_ids)"),
    organism: str = typer.Option(None, "--organism", "-o", help="Filter by organism"),
    summary: bool = typer.Option(False, "--summary", help="Summary only"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Include verbose fields"),
    limit: int = typer.Option(20, "--limit", help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Get member genes of gene clusters or a clustering analysis."""
    from multiomics_explorer.api.functions import genes_in_cluster
    from multiomics_explorer.kg.connection import GraphConnection

    with GraphConnection() as conn:
        if not conn.verify_connectivity():
            console.print("[red]Cannot connect to Neo4j. Is it running?[/red]")
            raise typer.Exit(1)

        try:
            result = genes_in_cluster(
                cluster_ids=cluster_ids or None,
                analysis_id=analysis_id,
                organism=organism,
                summary=summary, verbose=verbose, limit=limit, conn=conn,
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)

        if json_output:
            console.print(json.dumps(result, indent=2, default=str))
        else:
            console.print(f"[bold]Members:[/bold] {result['total_matching']} genes")
            if result.get("analysis_name"):
                console.print(f"  Analysis: {result['analysis_name']}")
            for r in result["results"]:
                name_part = f" ({r['gene_name']})" if r.get("gene_name") else ""
                console.print(f"  {r['locus_tag']}{name_part} — {r.get('product', '')}")
            if result["truncated"]:
                console.print(f"\n[dim]Showing {result['returned']} of {result['total_matching']}[/dim]")
```

- [ ] **Step 4: Smoke test CLI commands**

Run:
```bash
uv run multiomics-explorer list-clustering-analyses --json --limit 2
uv run multiomics-explorer gene-clusters-by-gene PMM0370 --json
uv run multiomics-explorer genes-in-cluster --analysis-id clustering_analysis:msb4100087:med4_kmeans_nstarvation --limit 5 --json
```

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/cli/main.py
git commit -m "feat: add CLI commands for clustering analysis tools"
```

---

## Task 11: Tool YAMLs + regenerate resource docs

**Files:**
- Delete: `multiomics_explorer/inputs/tools/list_gene_clusters.yaml`
- Create: `multiomics_explorer/inputs/tools/list_clustering_analyses.yaml`
- Modify: `multiomics_explorer/inputs/tools/gene_clusters_by_gene.yaml`
- Modify: `multiomics_explorer/inputs/tools/genes_in_cluster.yaml`

- [ ] **Step 1: Delete old YAML**

```bash
rm multiomics_explorer/inputs/tools/list_gene_clusters.yaml
```

- [ ] **Step 2: Create `list_clustering_analyses.yaml`**

```yaml
# Human-authored content for list_clustering_analyses about page.
# Auto-generated sections (params, response format, expected-keys)
# come from Pydantic models via scripts/build_about_content.py.

examples:
  - title: Orient — what clustering analyses exist?
    call: list_clustering_analyses(summary=True)

  - title: Search for nitrogen-related analyses
    call: list_clustering_analyses(search_text="nitrogen")

  - title: Browse all MED4 analyses with cluster details
    call: list_clustering_analyses(organism="MED4", verbose=True)

  - title: Find analyses then drill into member genes
    steps: |
      Step 1: list_clustering_analyses(search_text="nitrogen")
              → extract analysis_id values from results

      Step 2: genes_in_cluster(analysis_id="clustering_analysis:msb4100087:med4_kmeans_nstarvation")
              → see all member genes across all clusters in the analysis

      Step 3: gene_overview(locus_tags=["PMM0370", "PMM0920", ...])
              → check data availability for cluster members

verbose_fields:
  - treatment
  - light_condition
  - experimental_context
  - "clusters[].functional_description"
  - "clusters[].behavioral_description"
  - "clusters[].peak_time_hours"
  - "clusters[].period_hours"

chaining:
  - "list_clustering_analyses → genes_in_cluster(analysis_id=...) → gene_overview"
  - "list_clustering_analyses → genes_in_cluster → differential_expression_by_gene"
  - "list_clustering_analyses → gene_clusters_by_gene (reverse lookup)"

mistakes:
  - "Analysis IDs are not in the fulltext index — use search_text for text queries, analysis_ids for direct lookup"
  - "score_max/score_median are null when no search_text is given (browsing mode)"
  - wrong: "genes_in_cluster(cluster_ids=['nitrogen'])  # passing text, not IDs"
    right: "list_clustering_analyses(search_text='nitrogen')  # search first, then use analysis_id"
  - wrong: "len(results)  # actual count"
    right: "response['total_matching']  # use total, not len — results may be truncated"
```

- [ ] **Step 3: Update `gene_clusters_by_gene.yaml`**

Update examples to reflect new fields (`analysis_id`, `analysis_name`, no `source_paper`). Update verbose_fields list. Update chaining.

- [ ] **Step 4: Update `genes_in_cluster.yaml`**

Update examples to include `analysis_id` parameter usage. Update verbose_fields with renamed columns. Add `analysis_id` to examples.

- [ ] **Step 5: Regenerate resource docs**

```bash
uv run python scripts/build_about_content.py list_clustering_analyses
uv run python scripts/build_about_content.py gene_clusters_by_gene
uv run python scripts/build_about_content.py genes_in_cluster
```

Also delete old generated doc:
```bash
rm multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_gene_clusters.md
```

- [ ] **Step 6: Run about-content consistency tests**

Run: `pytest tests/unit/test_about_content.py -v`
Expected: PASS (all tools have matching YAMLs and resource docs)

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/inputs/tools/ multiomics_explorer/skills/multiomics-kg-guide/references/tools/
git commit -m "docs: update tool YAMLs and regenerate resource docs for clustering tools"
```

---

## Task 12: Integration tests + CyVer + contract + regression

**Files:**
- Modify: `tests/integration/test_api_contract.py`
- Modify: `tests/integration/test_cyver_queries.py`
- Modify: `tests/regression/test_regression.py`

- [ ] **Step 1: Update API contract tests**

In `tests/integration/test_api_contract.py`, replace `TestListGeneClustersContract`, `TestGeneClustersByGeneContract`, `TestGenesInClusterContract` with updated versions that validate new response shapes, field names, and parameters.

Key changes:
- `TestListClusteringAnalysesContract`: test envelope keys, result keys (compact + verbose), inline cluster structure
- `TestGeneClustersByGeneContract`: test new compact keys (`analysis_id`, `analysis_name`, `treatment_type`, `background_factors`), new verbose keys (`cluster_functional_description`, `cluster_behavioral_description`, `cluster_method`, `member_count`)
- `TestGenesInClusterContract`: test `analysis_id` mode, renamed verbose keys (`gene_function_description`, `cluster_functional_description`, `cluster_behavioral_description`)

- [ ] **Step 2: Add new builders to CyVer `_BUILDERS`**

In `tests/integration/test_cyver_queries.py`, add:
```python
("list_clustering_analyses_summary", build_list_clustering_analyses_summary, {}),
("list_clustering_analyses", build_list_clustering_analyses, {}),
("list_clustering_analyses_verbose", build_list_clustering_analyses, {"verbose": True}),
("list_clustering_analyses_search", build_list_clustering_analyses_summary, {"search_text": "nitrogen"}),
```

Remove old cluster builders if present.

- [ ] **Step 3: Update regression test baselines**

Add new builders to `TOOL_BUILDERS` in `tests/regression/test_regression.py`. Remove old ones. Then regenerate:

```bash
pytest tests/regression/ --force-regen -m kg
```

- [ ] **Step 4: Run full integration suite**

```bash
pytest -m kg -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: update integration tests, CyVer coverage, and regression baselines"
```

---

## Task 13: CLAUDE.md + final cleanup

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update tool table**

Replace `list_gene_clusters` with `list_clustering_analyses` in the tool table. Update descriptions for `gene_clusters_by_gene` and `genes_in_cluster`.

- [ ] **Step 2: Run full unit test suite**

```bash
pytest tests/unit/ -v
```
Expected: all PASS

- [ ] **Step 3: Run full integration test suite (if KG available)**

```bash
pytest -m kg -v
```
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md tool table for clustering analysis tools"
```
