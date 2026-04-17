# `cluster_enrichment` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `cluster_enrichment` MCP tool that runs Fisher-exact ORA on all clusters within a clustering analysis, automating the manual workflow from `enrichment.md` §5.

**Architecture:** New `cluster_enrichment_inputs()` helper builds `EnrichmentInputs` from `genes_in_cluster` API results. New L2 `cluster_enrichment()` orchestrates: build inputs → resolve background → TERM2GENE → `fisher_ora` → envelope. Thin L3 MCP wrapper. No new L1 query builders.

**Tech Stack:** Python, Pydantic, FastMCP, Neo4j (read-only), scipy/statsmodels (via `fisher_ora`)

**Spec:** `docs/superpowers/specs/2026-04-17-cluster-enrichment-design.md`

---

### Task 1: `cluster_enrichment_inputs()` helper — tests

**Files:**
- Modify: `tests/unit/test_api_functions.py` (append at end)

- [ ] **Step 1: Write unit tests for `cluster_enrichment_inputs`**

```python
class TestClusterEnrichmentInputs:
    """Tests for cluster_enrichment_inputs helper."""

    _CLUSTER_RESULT = {
        "total_matching": 7,
        "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 7}],
        "by_cluster": [
            {"cluster_id": "gc:1", "cluster_name": "Cluster A", "count": 4},
            {"cluster_id": "gc:2", "cluster_name": "Cluster B", "count": 2},
            {"cluster_id": "gc:3", "cluster_name": "Cluster C", "count": 1},
        ],
        "top_categories": [],
        "genes_per_cluster_max": 4,
        "genes_per_cluster_median": 2,
        "not_found_clusters": [],
        "not_matched_clusters": [],
        "not_matched_organism": None,
        "analysis_name": "Test Analysis",
        "returned": 7,
        "truncated": False,
        "offset": 0,
        "results": [
            {"locus_tag": "PMM0001", "cluster_id": "gc:1", "cluster_name": "Cluster A",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0002", "cluster_id": "gc:1", "cluster_name": "Cluster A",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0003", "cluster_id": "gc:1", "cluster_name": "Cluster A",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0004", "cluster_id": "gc:1", "cluster_name": "Cluster A",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0005", "cluster_id": "gc:2", "cluster_name": "Cluster B",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0006", "cluster_id": "gc:2", "cluster_name": "Cluster B",
             "organism_name": "Prochlorococcus MED4"},
            {"locus_tag": "PMM0007", "cluster_id": "gc:3", "cluster_name": "Cluster C",
             "organism_name": "Prochlorococcus MED4"},
        ],
    }

    _ANALYSIS_META = {
        "results": [{
            "analysis_id": "ca:test",
            "name": "Test Analysis",
            "organism_name": "Prochlorococcus MED4",
            "cluster_method": "kmeans",
            "cluster_type": "diel_cycle",
            "cluster_count": 3,
            "total_gene_count": 7,
            "treatment_type": ["light_dark"],
            "background_factors": [],
            "growth_phases": [],
            "omics_type": "transcriptomics",
            "experiment_ids": ["exp:1"],
            "clusters": [],
        }],
        "total_matching": 1,
        "returned": 1,
        "truncated": False,
    }

    def test_builds_gene_sets_grouped_by_cluster(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4")
        assert "Cluster A" in inputs.gene_sets
        assert "Cluster B" in inputs.gene_sets
        assert sorted(inputs.gene_sets["Cluster A"]) == ["PMM0001", "PMM0002", "PMM0003", "PMM0004"]
        assert sorted(inputs.gene_sets["Cluster B"]) == ["PMM0005", "PMM0006"]

    def test_cluster_union_background_includes_all_genes(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4", min_cluster_size=3)
        # Cluster C (1 gene) is filtered out but its gene is still in background
        all_bg_genes = set(inputs.background["Cluster A"])
        assert "PMM0007" in all_bg_genes
        assert len(all_bg_genes) == 7

    def test_min_cluster_size_filters_small_clusters(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4", min_cluster_size=3)
        # Cluster B (2 genes) and Cluster C (1 gene) filtered out
        assert "Cluster A" in inputs.gene_sets
        assert "Cluster B" not in inputs.gene_sets
        assert "Cluster C" not in inputs.gene_sets

    def test_max_cluster_size_filters_large_clusters(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4", max_cluster_size=3)
        assert "Cluster A" not in inputs.gene_sets
        assert "Cluster B" in inputs.gene_sets
        assert "Cluster C" in inputs.gene_sets

    def test_clusters_skipped_populated(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4", min_cluster_size=3)
        assert len(inputs.clusters_skipped) == 2
        skipped_names = {s["cluster_name"] for s in inputs.clusters_skipped}
        assert skipped_names == {"Cluster B", "Cluster C"}

    def test_not_found_when_analysis_missing(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        empty_result = {
            **self._CLUSTER_RESULT,
            "total_matching": 0, "results": [], "returned": 0,
            "analysis_name": None,
        }
        empty_meta = {**self._ANALYSIS_META, "total_matching": 0, "results": [], "returned": 0}
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: empty_result)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: empty_meta)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:missing", organism="MED4")
        assert "ca:missing" in inputs.not_found

    def test_not_matched_when_organism_wrong(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        wrong_org_result = {
            **self._CLUSTER_RESULT,
            "not_matched_organism": "SomeOtherOrg",
            "total_matching": 0, "results": [], "returned": 0,
        }
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: wrong_org_result)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="SomeOtherOrg")
        assert "ca:test" in inputs.not_matched

    def test_cluster_metadata_populated(self, monkeypatch):
        import multiomics_explorer.analysis.enrichment as enr
        import multiomics_explorer.api.functions as f
        monkeypatch.setattr(f, "genes_in_cluster", lambda **_: self._CLUSTER_RESULT)
        monkeypatch.setattr(f, "list_clustering_analyses", lambda **_: self._ANALYSIS_META)
        inputs = enr.cluster_enrichment_inputs(
            analysis_id="ca:test", organism="MED4")
        md = inputs.cluster_metadata["Cluster A"]
        assert md["cluster_id"] == "gc:1"
        assert md["member_count"] == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_api_functions.py::TestClusterEnrichmentInputs -v`
Expected: FAIL — `cluster_enrichment_inputs` not yet defined

---

### Task 2: `cluster_enrichment_inputs()` helper — implementation

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.py` (append after `de_enrichment_inputs`)

- [ ] **Step 1: Add `clusters_skipped` field to `EnrichmentInputs`**

In `multiomics_explorer/analysis/enrichment.py`, add after the `no_expression` field (line ~65):

```python
    clusters_skipped: list[dict] = Field(
        default_factory=list,
        description=(
            "Clusters filtered out by size constraints. Each entry: "
            "{cluster_id, cluster_name, member_count, reason}."
        ),
    )
```

- [ ] **Step 2: Implement `cluster_enrichment_inputs`**

Append after `de_enrichment_inputs` (after line ~490):

```python
def cluster_enrichment_inputs(
    analysis_id: str,
    organism: str,
    min_cluster_size: int = 3,
    max_cluster_size: int | None = None,
    *,
    conn=None,
) -> EnrichmentInputs:
    """Build EnrichmentInputs from cluster memberships in a clustering analysis.

    Calls ``genes_in_cluster(analysis_id=...)`` and
    ``list_clustering_analyses(analysis_ids=[analysis_id])`` to gather
    cluster members and analysis metadata, groups by cluster, applies
    size filters, and returns an ``EnrichmentInputs`` with
    ``cluster_union`` background (union of ALL cluster members, including
    size-filtered clusters).

    Parameters
    ----------
    analysis_id : str
        Clustering analysis ID.
    organism : str
        Single organism name (fuzzy-matched).
    min_cluster_size : int, default 3
        Skip clusters with fewer members.
    max_cluster_size : int or None, default None
        Skip clusters with more members. None disables.
    conn : GraphConnection, optional
        Passed through to API calls.

    Returns
    -------
    EnrichmentInputs
        ``gene_sets`` keyed by cluster name (size-passing only).
        ``background`` per-cluster, all pointing to the cluster union.
        ``clusters_skipped`` lists filtered-out clusters with reasons.
    """
    from multiomics_explorer.api.functions import (
        genes_in_cluster as _genes_in_cluster,
        list_clustering_analyses as _list_analyses,
    )

    # Fetch all cluster members
    cluster_result = _genes_in_cluster(
        analysis_id=analysis_id, organism=organism,
        verbose=True, limit=None, conn=conn,
    )

    # Fetch analysis-level metadata
    analysis_meta_result = _list_analyses(
        analysis_ids=[analysis_id], limit=1, conn=conn,
    )
    analysis_meta = (
        analysis_meta_result["results"][0]
        if analysis_meta_result.get("results")
        else {}
    )

    # Check not_found / not_matched
    not_found: list[str] = []
    not_matched: list[str] = []
    if not cluster_result.get("results") and cluster_result.get("total_matching", 0) == 0:
        if cluster_result.get("not_matched_organism"):
            not_matched = [analysis_id]
        elif not analysis_meta:
            not_found = [analysis_id]
        else:
            not_found = [analysis_id]

    # Group results by cluster
    all_cluster_genes: dict[str, list[str]] = {}
    cluster_ids_map: dict[str, str] = {}  # cluster_name -> cluster_id
    cluster_verbose: dict[str, dict] = {}  # cluster_name -> verbose fields
    for row in cluster_result.get("results", []):
        cname = row["cluster_name"]
        all_cluster_genes.setdefault(cname, []).append(row["locus_tag"])
        if cname not in cluster_ids_map:
            cluster_ids_map[cname] = row["cluster_id"]
            cluster_verbose[cname] = {
                k: row.get(k)
                for k in (
                    "cluster_functional_description",
                    "cluster_expression_dynamics",
                    "cluster_temporal_pattern",
                )
            }

    # Build cluster_union background (ALL genes, before size filtering)
    all_genes = sorted({
        lt for genes in all_cluster_genes.values() for lt in genes
    })

    # Apply size filters
    gene_sets: dict[str, list[str]] = {}
    clusters_skipped: list[dict] = []
    for cname, genes in all_cluster_genes.items():
        count = len(genes)
        if count < min_cluster_size:
            clusters_skipped.append({
                "cluster_id": cluster_ids_map[cname],
                "cluster_name": cname,
                "member_count": count,
                "reason": f"below min_cluster_size ({min_cluster_size})",
            })
            continue
        if max_cluster_size is not None and count > max_cluster_size:
            clusters_skipped.append({
                "cluster_id": cluster_ids_map[cname],
                "cluster_name": cname,
                "member_count": count,
                "reason": f"above max_cluster_size ({max_cluster_size})",
            })
            continue
        gene_sets[cname] = genes

    # Build per-cluster background (shared union)
    background = {cname: list(all_genes) for cname in gene_sets}

    # Build cluster metadata
    cluster_metadata: dict[str, dict] = {}
    for cname in gene_sets:
        cluster_metadata[cname] = {
            "cluster_id": cluster_ids_map[cname],
            "cluster_name": cname,
            "member_count": len(gene_sets[cname]),
            **cluster_verbose.get(cname, {}),
        }

    # Thread analysis-level metadata into a top-level dict
    # (available via inputs.analysis_metadata for the L2 function)
    analysis_md = {
        "analysis_id": analysis_id,
        "analysis_name": analysis_meta.get("name")
            or cluster_result.get("analysis_name"),
        "cluster_method": analysis_meta.get("cluster_method"),
        "cluster_type": analysis_meta.get("cluster_type"),
        "omics_type": analysis_meta.get("omics_type"),
        "treatment_type": analysis_meta.get("treatment_type", []),
        "background_factors": analysis_meta.get("background_factors", []),
        "growth_phases": analysis_meta.get("growth_phases", []),
        "experiment_ids": analysis_meta.get("experiment_ids", []),
    }

    return EnrichmentInputs(
        organism_name=organism,
        gene_sets=gene_sets,
        background=background,
        cluster_metadata=cluster_metadata,
        not_found=not_found,
        not_matched=not_matched,
        no_expression=[],
        clusters_skipped=clusters_skipped,
        analysis_metadata=analysis_md,
    )
```

- [ ] **Step 3: Add `analysis_metadata` field to `EnrichmentInputs`**

In the `EnrichmentInputs` class, add after `clusters_skipped`:

```python
    analysis_metadata: dict = Field(
        default_factory=dict,
        description="Analysis-level metadata (analysis_id, name, cluster_type, etc.).",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_api_functions.py::TestClusterEnrichmentInputs -v`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.py tests/unit/test_api_functions.py
git commit -m "feat: add cluster_enrichment_inputs helper with tests"
```

---

### Task 3: `cluster_enrichment()` L2 API function — tests

**Files:**
- Modify: `tests/unit/test_api_functions.py` (append at end)

- [ ] **Step 1: Write unit tests for L2 function**

```python
class TestClusterEnrichment:
    """Input validation + orchestration for api.cluster_enrichment."""

    def test_importable_from_api(self):
        from multiomics_explorer.api import cluster_enrichment
        assert cluster_enrichment is not None

    def test_invalid_ontology_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="ontology"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="not_real", level=1,
            )

    def test_missing_level_and_term_ids_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="level|term_ids"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="cyanorak_role",
            )

    def test_bad_background_string_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="background"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="cyanorak_role", level=1,
                background="genome",
            )

    def test_bad_pvalue_cutoff_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="pvalue_cutoff"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="cyanorak_role", level=1,
                pvalue_cutoff=1.5,
            )

    def test_max_less_than_min_gene_set_size_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="max_gene_set_size"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="cyanorak_role", level=1,
                min_gene_set_size=50, max_gene_set_size=5,
            )

    def test_max_less_than_min_cluster_size_raises(self):
        from multiomics_explorer.api import cluster_enrichment
        with pytest.raises(ValueError, match="max_cluster_size"):
            cluster_enrichment(
                analysis_id="ca:1", organism="MED4",
                ontology="cyanorak_role", level=1,
                min_cluster_size=20, max_cluster_size=5,
            )

    @staticmethod
    def _stub_inputs(gene_sets=None, not_found=(), not_matched=()):
        from multiomics_explorer.analysis.enrichment import EnrichmentInputs
        return EnrichmentInputs(
            organism_name="MED4",
            gene_sets=gene_sets or {"Cluster A": ["PMM0001", "PMM0002"]},
            background={"Cluster A": ["PMM0001", "PMM0002", "PMM0003"]},
            cluster_metadata={"Cluster A": {
                "cluster_id": "gc:1", "cluster_name": "Cluster A",
                "member_count": 2,
            }},
            not_found=list(not_found),
            not_matched=list(not_matched),
            no_expression=[],
            clusters_skipped=[],
            analysis_metadata={
                "analysis_id": "ca:test", "analysis_name": "Test",
                "cluster_method": "kmeans", "cluster_type": "diel_cycle",
                "omics_type": "transcriptomics",
                "treatment_type": ["light_dark"],
                "background_factors": [], "growth_phases": [],
                "experiment_ids": ["exp:1"],
            },
        )

    @staticmethod
    def _stub_gbo_result(rows=()):
        return {
            "ontology": "cyanorak_role", "organism_name": "MED4",
            "results": list(rows),
            "not_found": [], "wrong_ontology": [],
            "wrong_level": [], "filtered_out": [],
        }

    def test_early_return_when_not_found(self, monkeypatch):
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr
        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(gene_sets={}, not_found=["ca:missing"]),
        )
        result = cluster_enrichment(
            analysis_id="ca:missing", organism="MED4",
            ontology="cyanorak_role", level=1,
        )
        assert result["not_found"] == ["ca:missing"]
        assert result["results"] == []

    def test_orchestration_produces_envelope(self, monkeypatch):
        import pandas as pd
        from multiomics_explorer.api import cluster_enrichment
        import multiomics_explorer.api.functions as f
        import multiomics_explorer.analysis.enrichment as enr

        monkeypatch.setattr(
            enr, "cluster_enrichment_inputs",
            lambda **_: self._stub_inputs(),
        )
        monkeypatch.setattr(
            f, "genes_by_ontology",
            lambda **_: self._stub_gbo_result([
                {"term_id": "CR:A", "term_name": "Cat A", "locus_tag": "PMM0001", "level": 1},
                {"term_id": "CR:A", "term_name": "Cat A", "locus_tag": "PMM0002", "level": 1},
                {"term_id": "CR:B", "term_name": "Cat B", "locus_tag": "PMM0003", "level": 1},
            ]),
        )
        # fisher_ora will run on real data — 2 genes in Cluster A,
        # 3 in background, 2 in CR:A pathway → should produce a result
        result = cluster_enrichment(
            analysis_id="ca:test", organism="MED4",
            ontology="cyanorak_role", level=1,
            pvalue_cutoff=1.0,  # accept all
        )
        assert "total_matching" in result
        assert "returned" in result
        assert "analysis_id" in result
        assert "organism_name" in result
        assert isinstance(result["results"], list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_api_functions.py::TestClusterEnrichment -v`
Expected: FAIL — `cluster_enrichment` not yet defined

---

### Task 4: `cluster_enrichment()` L2 API function — implementation

**Files:**
- Modify: `multiomics_explorer/api/functions.py` (append after `pathway_enrichment`, ~line 3373)
- Modify: `multiomics_explorer/api/__init__.py` (add export)
- Modify: `multiomics_explorer/__init__.py` (add re-export)

- [ ] **Step 1: Implement the L2 function**

Append to `multiomics_explorer/api/functions.py` after `pathway_enrichment`:

```python
def cluster_enrichment(
    analysis_id: str,
    organism: str,
    ontology: str,
    level: int | None = None,
    term_ids: list[str] | None = None,
    tree: str | None = None,
    background: str | list[str] = "cluster_union",
    min_gene_set_size: int = 5,
    max_gene_set_size: int | None = 500,
    min_cluster_size: int = 3,
    max_cluster_size: int | None = None,
    pvalue_cutoff: float = 0.05,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Cluster-membership over-representation analysis (Fisher + BH).

    Runs ORA across all clusters in a clustering analysis. Each cluster's
    member genes form a foreground gene set; background defaults to the
    union of all clustered genes (including size-filtered clusters).

    Returns dict with keys: analysis_id, analysis_name, organism_name,
    cluster_method, cluster_type, omics_type, treatment_type,
    background_factors, growth_phases, experiment_ids, ontology, level,
    tree, background_mode, background_size, total_matching, returned,
    truncated, offset, n_significant, not_found, not_matched,
    clusters_skipped, by_cluster, by_term, clusters_tested,
    total_terms_tested, results.

    Raises:
        ValueError: on invalid ontology, missing level/term_ids, bad
        background mode, bad pvalue_cutoff, bad size constraints.
    """
    # --- Input validation ---
    if ontology not in ALL_ONTOLOGIES:
        raise ValueError(
            f"Invalid ontology '{ontology}'. Valid: {ALL_ONTOLOGIES}"
        )
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
    if level is None and not term_ids:
        raise ValueError(
            "At least one of `level` or `term_ids` must be provided."
        )
    if isinstance(background, str):
        if background not in {"cluster_union", "organism"}:
            raise ValueError(
                f"background must be 'cluster_union', 'organism', or a list; "
                f"got {background!r}"
            )
    elif isinstance(background, list):
        if not background:
            raise ValueError("background list must be non-empty")
    else:
        raise ValueError(
            f"background must be 'cluster_union', 'organism', or a list; "
            f"got {type(background).__name__}"
        )
    if min_gene_set_size < 0:
        raise ValueError("min_gene_set_size must be >= 0.")
    if max_gene_set_size is not None and max_gene_set_size < min_gene_set_size:
        raise ValueError("max_gene_set_size must be >= min_gene_set_size.")
    if min_cluster_size < 0:
        raise ValueError("min_cluster_size must be >= 0.")
    if max_cluster_size is not None and max_cluster_size < min_cluster_size:
        raise ValueError("max_cluster_size must be >= min_cluster_size.")
    if not (0 < pvalue_cutoff < 1):
        raise ValueError(
            f"pvalue_cutoff must be in (0, 1); got {pvalue_cutoff}"
        )

    from multiomics_explorer.analysis.enrichment import (
        cluster_enrichment_inputs, fisher_ora,
    )
    import pandas as pd

    conn = _default_conn(conn)

    # Step 2: build EnrichmentInputs
    inputs = cluster_enrichment_inputs(
        analysis_id=analysis_id,
        organism=organism,
        min_cluster_size=min_cluster_size,
        max_cluster_size=max_cluster_size,
        conn=conn,
    )

    # Early return if not_found/not_matched or no gene sets
    if inputs.not_found or inputs.not_matched or not inputs.gene_sets:
        return _build_cluster_enrichment_envelope(
            df=pd.DataFrame(),
            inputs=inputs,
            gbo_result={},
            ontology=ontology,
            level=level,
            tree=tree,
            background_mode=background if isinstance(background, str) else "custom",
            pvalue_cutoff=pvalue_cutoff,
            summary=summary,
            verbose=verbose,
            limit=0,
            offset=offset,
        )

    # Step 3: resolve background
    if background == "cluster_union":
        resolved_bg = inputs.background
        bg_mode = "cluster_union"
    elif background == "organism":
        org_cypher = (
            "MATCH (g:Gene {organism_name: $org}) "
            "RETURN collect(g.locus_tag) AS locus_tags"
        )
        org_rows = conn.execute_query(org_cypher, org=inputs.organism_name)
        org_locus_tags = org_rows[0]["locus_tags"] if org_rows else []
        resolved_bg = {c: list(org_locus_tags) for c in inputs.gene_sets}
        bg_mode = "organism"
    else:
        resolved_bg = {c: list(background) for c in inputs.gene_sets}
        bg_mode = "custom"

    # Step 4: TERM2GENE
    gbo_result = genes_by_ontology(
        ontology=ontology,
        organism=inputs.organism_name,
        level=level,
        term_ids=term_ids,
        min_gene_set_size=0,
        max_gene_set_size=None,
        summary=False,
        verbose=False,
        limit=None,
        offset=0,
        tree=tree,
        conn=conn,
    )
    from multiomics_explorer.analysis.frames import to_dataframe
    term2gene = to_dataframe(gbo_result)

    # Step 5: fisher_ora
    if term2gene.empty or not inputs.gene_sets:
        df = pd.DataFrame()
    else:
        df = fisher_ora(
            gene_sets=inputs.gene_sets,
            background=resolved_bg,
            term2gene=term2gene,
            min_gene_set_size=min_gene_set_size,
            max_gene_set_size=max_gene_set_size,
        )

    # Step 6: attach cluster metadata
    if not df.empty:
        md_df = pd.DataFrame.from_dict(
            inputs.cluster_metadata, orient="index"
        ).reset_index().rename(columns={"index": "cluster"})
        df = df.merge(md_df, on="cluster", how="left")

    # Step 7: envelope
    return _build_cluster_enrichment_envelope(
        df=df,
        inputs=inputs,
        gbo_result=gbo_result,
        ontology=ontology,
        level=level,
        tree=tree,
        background_mode=bg_mode,
        pvalue_cutoff=pvalue_cutoff,
        summary=summary,
        verbose=verbose,
        limit=limit if limit is not None else len(df),
        offset=offset,
    )
```

- [ ] **Step 2: Implement `_build_cluster_enrichment_envelope`**

Add before `cluster_enrichment` in `api/functions.py`:

```python
def _build_cluster_enrichment_envelope(
    *, df, inputs, gbo_result, ontology, level, tree,
    background_mode, pvalue_cutoff, summary, verbose, limit, offset,
) -> dict:
    import pandas as pd

    total_matching = int(len(df))
    n_significant = int((df["p_adjust"] < pvalue_cutoff).sum()) if total_matching else 0

    # clusters_skipped from inputs
    clusters_skipped = inputs.clusters_skipped

    # Detect clusters that passed size filter but produced no Fisher rows
    produced_clusters = set(df["cluster"]) if total_matching else set()
    for cname in inputs.cluster_metadata:
        if cname in produced_clusters:
            continue
        if cname not in inputs.background or not inputs.background.get(cname):
            reason = "empty_background"
        elif not inputs.gene_sets.get(cname):
            reason = "empty_gene_set"
        else:
            reason = "no_pathways_in_size_range"
        clusters_skipped.append({
            "cluster_id": inputs.cluster_metadata[cname].get("cluster_id", ""),
            "cluster_name": cname,
            "member_count": inputs.cluster_metadata[cname].get("member_count", 0),
            "reason": reason,
        })

    # Background size (N)
    bg_size = 0
    if inputs.background:
        first_bg = next(iter(inputs.background.values()), [])
        bg_size = len(first_bg)

    # Summary fields
    by_cluster = []
    for cname in sorted(produced_clusters):
        sub = df[df["cluster"] == cname]
        by_cluster.append({
            "cluster_id": inputs.cluster_metadata.get(cname, {}).get("cluster_id", ""),
            "cluster_name": cname,
            "member_count": inputs.cluster_metadata.get(cname, {}).get("member_count", 0),
            "significant_terms": int((sub["p_adjust"] < pvalue_cutoff).sum()),
        })

    by_term = []
    if total_matching:
        sig_df = df[df["p_adjust"] < pvalue_cutoff]
        if not sig_df.empty:
            term_counts = sig_df.groupby("term_id").agg(
                term_name=("term_name", "first"),
                n_clusters=("cluster", "nunique"),
            ).sort_values("n_clusters", ascending=False).head(10)
            by_term = [
                {"term_id": tid, "term_name": row["term_name"],
                 "n_clusters": int(row["n_clusters"])}
                for tid, row in term_counts.iterrows()
            ]

    # Pagination
    if summary:
        returned_rows = []
        returned = 0
        truncated = total_matching > 0
    else:
        sliced = df.iloc[offset:offset + limit] if total_matching else df
        if not verbose:
            drop_cols = [c for c in (
                "cluster_functional_description",
                "cluster_expression_dynamics",
                "cluster_temporal_pattern",
                "cluster_member_count",
            ) if c in sliced.columns]
            sliced = sliced.drop(columns=drop_cols)
        returned_rows = sliced.to_dict(orient="records")
        returned = len(returned_rows)
        truncated = (offset + returned) < total_matching

    analysis_md = inputs.analysis_metadata

    return {
        "analysis_id": analysis_md.get("analysis_id"),
        "analysis_name": analysis_md.get("analysis_name"),
        "organism_name": inputs.organism_name,
        "cluster_method": analysis_md.get("cluster_method"),
        "cluster_type": analysis_md.get("cluster_type"),
        "omics_type": analysis_md.get("omics_type"),
        "treatment_type": analysis_md.get("treatment_type", []),
        "background_factors": analysis_md.get("background_factors", []),
        "growth_phases": analysis_md.get("growth_phases", []),
        "experiment_ids": analysis_md.get("experiment_ids", []),
        "ontology": ontology,
        "level": level,
        "tree": tree,
        "background_mode": background_mode,
        "background_size": bg_size,
        "total_matching": total_matching,
        "returned": returned,
        "truncated": truncated,
        "offset": offset,
        "n_significant": n_significant,
        "by_cluster": by_cluster,
        "by_term": by_term,
        "clusters_tested": len(produced_clusters),
        "total_terms_tested": int(gbo_result.get("total_matching", 0)) if gbo_result else 0,
        "not_found": inputs.not_found,
        "not_matched": inputs.not_matched,
        "clusters_skipped": clusters_skipped,
        "results": returned_rows,
    }
```

- [ ] **Step 3: Add exports**

In `multiomics_explorer/api/__init__.py`, add `cluster_enrichment` to both the import and `__all__`:

```python
from multiomics_explorer.api.functions import (
    ...
    cluster_enrichment,
    pathway_enrichment,
)

__all__ = [
    ...
    "cluster_enrichment",
    "pathway_enrichment",
]
```

In `multiomics_explorer/__init__.py`, add to the import and `__all__`:

```python
from multiomics_explorer.api.functions import (
    ...
    cluster_enrichment,
)

__all__ = [
    ...
    "cluster_enrichment",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_api_functions.py::TestClusterEnrichment -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/api/__init__.py multiomics_explorer/__init__.py tests/unit/test_api_functions.py
git commit -m "feat: add cluster_enrichment L2 API function with tests"
```

---

### Task 5: MCP wrapper — Pydantic models + registration

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py`

- [ ] **Step 1: Add Pydantic result and response models**

Add near the top of `tools.py` after `PathwayEnrichmentResponse` (after line ~257), inside `register_tools`:

```python
    class ClusterEnrichmentResult(BaseModel):
        cluster: str = Field(description="Cluster name from the clustering analysis")
        cluster_id: str = Field(description="Cluster ID from KG")
        term_id: str = Field(description="Ontology term ID")
        term_name: str = Field(description="Ontology term display name")
        level: int | None = Field(default=None, description="Hierarchy depth (0 = root)")
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
        gene_ratio: str = Field(
            description="'k/n' string — cluster genes in pathway over total cluster genes (clusterProfiler: GeneRatio)"
        )
        gene_ratio_numeric: float = Field(description="k/n as float")
        bg_ratio: str = Field(
            description="'M/N' string — pathway members over background size (clusterProfiler: BgRatio)"
        )
        bg_ratio_numeric: float = Field(description="M/N as float")
        rich_factor: float = Field(
            description="k/M — fraction of pathway's background members in cluster (clusterProfiler: RichFactor)"
        )
        fold_enrichment: float = Field(
            description="(k/n) / (M/N) — observed over null (clusterProfiler: FoldEnrichment)"
        )
        pvalue: float = Field(description="Fisher-exact p-value (one-sided enrichment)")
        p_adjust: float = Field(
            description="Benjamini-Hochberg FDR within cluster (clusterProfiler: p.adjust)"
        )
        count: int = Field(description="k — cluster genes in pathway (clusterProfiler: Count)")
        bg_count: int = Field(description="M — pathway members in cluster's background")
        # Verbose fields
        cluster_functional_description: str | None = Field(
            default=None, description="Verbose: functional description of cluster"
        )
        cluster_expression_dynamics: str | None = Field(
            default=None, description="Verbose: expression dynamics of cluster"
        )
        cluster_temporal_pattern: str | None = Field(
            default=None, description="Verbose: temporal pattern of cluster"
        )
        cluster_member_count: int | None = Field(
            default=None, description="Verbose: total genes in this cluster"
        )

    class ClusterEnrichmentByCluster(BaseModel):
        cluster_id: str = Field(description="Cluster ID")
        cluster_name: str = Field(description="Cluster name")
        member_count: int = Field(description="Genes in cluster")
        significant_terms: int = Field(description="Terms with p_adjust below cutoff")

    class ClusterEnrichmentByTerm(BaseModel):
        term_id: str = Field(description="Term ID")
        term_name: str = Field(description="Term name")
        n_clusters: int = Field(description="Clusters where this term is significant")

    class ClusterEnrichmentClusterSkipped(BaseModel):
        cluster_id: str = Field(description="Cluster ID")
        cluster_name: str = Field(description="Cluster name")
        member_count: int = Field(description="Genes in cluster")
        reason: str = Field(description="Why skipped")

    class ClusterEnrichmentResponse(BaseModel):
        analysis_id: str | None = Field(default=None, description="Clustering analysis ID")
        analysis_name: str | None = Field(default=None, description="Clustering analysis name")
        organism_name: str = Field(description="Single organism")
        cluster_method: str | None = Field(default=None, description="Clustering method")
        cluster_type: str | None = Field(default=None, description="Cluster type")
        omics_type: str | None = Field(default=None, description="Omics type")
        treatment_type: list[str] = Field(default_factory=list, description="Treatment types")
        background_factors: list[str] = Field(default_factory=list, description="Background factors")
        growth_phases: list[str] = Field(default_factory=list, description="Growth phases")
        experiment_ids: list[str] = Field(default_factory=list, description="Linked experiment IDs")
        ontology: str = Field(description="Ontology used")
        level: int | None = Field(default=None, description="Hierarchy level")
        tree: str | None = Field(default=None, description="BRITE tree (if applicable)")
        background_mode: str = Field(description="Background mode used: cluster_union, organism, custom")
        background_size: int = Field(description="N — genes in background")
        total_matching: int = Field(description="Total Fisher tests run")
        returned: int = Field(description="Rows in this response")
        truncated: bool = Field(description="True when total_matching exceeds offset+returned")
        offset: int = Field(default=0, description="Pagination offset")
        n_significant: int = Field(description="Rows with p_adjust below cutoff")
        by_cluster: list[ClusterEnrichmentByCluster] = Field(
            default_factory=list, description="Per-cluster significance counts"
        )
        by_term: list[ClusterEnrichmentByTerm] = Field(
            default_factory=list, description="Top terms by number of clusters"
        )
        clusters_tested: int = Field(description="Clusters passing size filter")
        total_terms_tested: int = Field(description="Unique terms in TERM2GENE")
        not_found: list[str] = Field(default_factory=list, description="Analysis IDs absent from KG")
        not_matched: list[str] = Field(default_factory=list, description="Analysis IDs wrong organism")
        clusters_skipped: list[ClusterEnrichmentClusterSkipped] = Field(
            default_factory=list, description="Clusters filtered out by size or producing no rows"
        )
        results: list[ClusterEnrichmentResult] = Field(
            default_factory=list, description="Long-format result rows"
        )
```

- [ ] **Step 2: Add tool registration**

Add at the end of `register_tools`, before the function's closing (after `pathway_enrichment`):

```python
    @mcp.tool(
        tags={"enrichment", "clustering", "ontology"},
        annotations={"readOnlyHint": True, "destructiveHint": False,
                     "idempotentHint": True, "openWorldHint": False},
    )
    async def cluster_enrichment(
        ctx: Context,
        analysis_id: Annotated[str, Field(
            description="Clustering analysis ID. Get from list_clustering_analyses.",
        )],
        organism: Annotated[str, Field(
            description="Organism (case-insensitive fuzzy match). Single-organism enforced.",
        )],
        ontology: Annotated[Literal[
            "go_bp", "go_mf", "go_cc", "ec", "kegg",
            "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite",
        ], Field(
            description="Ontology for pathway definitions. Run ontology_landscape first.",
        )],
        tree: Annotated[str | None, Field(
            description="BRITE tree name filter. Only valid when ontology='brite'.",
        )] = None,
        level: Annotated[int | None, Field(
            description="Hierarchy level (0 = root). At least one of level or term_ids required.",
            ge=0,
        )] = None,
        term_ids: Annotated[list[str] | None, Field(
            description="Specific term IDs to test.",
        )] = None,
        background: Annotated[str | list[str], Field(
            description="'cluster_union' (default), 'organism', or explicit locus_tag list.",
        )] = "cluster_union",
        min_gene_set_size: Annotated[int, Field(
            description="Per-cluster M filter: drop pathways with fewer members.",
            ge=0,
        )] = 5,
        max_gene_set_size: Annotated[int | None, Field(
            description="Per-cluster M filter upper bound. None disables.",
            ge=1,
        )] = 500,
        min_cluster_size: Annotated[int, Field(
            description="Skip clusters with fewer members than this.",
            ge=0,
        )] = 3,
        max_cluster_size: Annotated[int | None, Field(
            description="Skip clusters with more members. None disables.",
            ge=1,
        )] = None,
        pvalue_cutoff: Annotated[float, Field(
            description="Significance threshold for p_adjust.",
            gt=0, lt=1,
        )] = 0.05,
        summary: Annotated[bool, Field(
            description="If true, omit results (envelope only).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include cluster description fields on rows.",
        )] = False,
        limit: Annotated[int, Field(
            description="Max rows returned.",
            ge=1,
        )] = 5,
        offset: Annotated[int, Field(
            description="Skip N rows before limit.",
            ge=0,
        )] = 0,
    ) -> ClusterEnrichmentResponse:
        """Cluster-membership over-representation analysis (Fisher + BH).

        Runs ORA on every cluster in a clustering analysis. Use
        list_clustering_analyses to find analysis IDs. Background
        defaults to the union of all clustered genes.
        See docs://analysis/enrichment for methodology.
        """
        await ctx.info(
            f"cluster_enrichment analysis_id={analysis_id} "
            f"ontology={ontology} level={level}"
        )
        try:
            conn = _conn(ctx)
            result = api.cluster_enrichment(
                analysis_id=analysis_id,
                organism=organism,
                ontology=ontology,
                level=level,
                term_ids=term_ids,
                tree=tree,
                background=background,
                min_gene_set_size=min_gene_set_size,
                max_gene_set_size=max_gene_set_size,
                min_cluster_size=min_cluster_size,
                max_cluster_size=max_cluster_size,
                pvalue_cutoff=pvalue_cutoff,
                summary=summary,
                verbose=verbose,
                limit=limit,
                offset=offset,
                conn=conn,
            )
        except ValueError as e:
            raise ToolError(str(e)) from e

        # Emit warnings
        warnings = []
        if result["not_found"]:
            warnings.append(f"{len(result['not_found'])} analysis_ids not_found")
        if result["not_matched"]:
            warnings.append(f"{len(result['not_matched'])} not_matched (wrong organism)")
        if result.get("clusters_skipped"):
            warnings.append(f"{len(result['clusters_skipped'])} clusters skipped")
        if warnings:
            await ctx.warning("; ".join(warnings))

        return ClusterEnrichmentResponse(**result)
```

- [ ] **Step 3: Commit**

```bash
git add multiomics_explorer/mcp_server/tools.py
git commit -m "feat: add cluster_enrichment MCP wrapper with Pydantic models"
```

---

### Task 6: Unit tests — MCP wrapper

**Files:**
- Modify: `tests/unit/test_tool_wrappers.py`

- [ ] **Step 1: Add `cluster_enrichment` to `EXPECTED_TOOLS`**

In `tests/unit/test_tool_wrappers.py`, add `"cluster_enrichment"` to the `EXPECTED_TOOLS` list (line ~65):

```python
EXPECTED_TOOLS = [
    ...
    "pathway_enrichment",
    "cluster_enrichment",
]
```

- [ ] **Step 2: Add wrapper tests**

Append at end of `tests/unit/test_tool_wrappers.py`:

```python
class TestClusterEnrichmentWrapper:
    def test_response_model_imports(self):
        from multiomics_explorer.mcp_server.tools import (
            ClusterEnrichmentResult,
            ClusterEnrichmentResponse,
        )
        assert ClusterEnrichmentResult is not None
        assert ClusterEnrichmentResponse is not None

    def test_every_result_field_has_description(self):
        from multiomics_explorer.mcp_server.tools import ClusterEnrichmentResult
        for name, field in ClusterEnrichmentResult.model_fields.items():
            assert field.description, (
                f"ClusterEnrichmentResult.{name} missing Field(description=...)"
            )

    def test_every_envelope_field_has_description(self):
        from multiomics_explorer.mcp_server.tools import ClusterEnrichmentResponse
        for name, field in ClusterEnrichmentResponse.model_fields.items():
            assert field.description, (
                f"ClusterEnrichmentResponse.{name} missing Field(description=...)"
            )

    def test_clusterprofiler_names_mention_equivalent(self):
        from multiomics_explorer.mcp_server.tools import ClusterEnrichmentResult
        expected_mentions = {
            "gene_ratio": "GeneRatio",
            "bg_ratio": "BgRatio",
            "rich_factor": "RichFactor",
            "fold_enrichment": "FoldEnrichment",
            "count": "Count",
        }
        for field_name, cp_name in expected_mentions.items():
            field = ClusterEnrichmentResult.model_fields[field_name]
            assert cp_name in field.description, (
                f"{field_name} description should mention clusterProfiler name {cp_name}"
            )
```

- [ ] **Step 3: Run all wrapper tests**

Run: `pytest tests/unit/test_tool_wrappers.py -v`
Expected: PASS (including `test_all_tools_registered`)

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_tool_wrappers.py
git commit -m "test: add cluster_enrichment MCP wrapper unit tests"
```

---

### Task 7: YAML + generated about-content

**Files:**
- Create: `multiomics_explorer/inputs/tools/cluster_enrichment.yaml`
- Generate: `multiomics_explorer/skills/multiomics-kg-guide/references/tools/cluster_enrichment.md`

- [ ] **Step 1: Create the YAML input file**

```yaml
# Human-authored content for cluster_enrichment about page.

examples:
  - title: Single analysis, CyanoRak level 1
    call: cluster_enrichment(analysis_id="<analysis_id>", organism="MED4", ontology="cyanorak_role", level=1)

  - title: Summary-only (envelope, no rows)
    call: cluster_enrichment(analysis_id="<analysis_id>", organism="MED4", ontology="cyanorak_role", level=1, summary=True)

  - title: Verbose with cluster descriptions
    call: cluster_enrichment(analysis_id="<analysis_id>", organism="MED4", ontology="cyanorak_role", level=1, verbose=True)

  - title: BRITE tree-scoped
    call: cluster_enrichment(analysis_id="<analysis_id>", organism="MED4", ontology="brite", tree="transporters", level=1)

  - title: Organism background instead of cluster union
    call: cluster_enrichment(analysis_id="<analysis_id>", organism="MED4", ontology="cyanorak_role", level=1, background="organism")

  - title: From landscape to cluster enrichment
    steps: |
      Step 1: list_clustering_analyses(organism="MED4")
              → pick an analysis_id

      Step 2: ontology_landscape(organism="MED4")
              → pick (ontology, level) by relevance_rank

      Step 3: cluster_enrichment(analysis_id=<picked>, organism="MED4", ontology=<picked>, level=<picked>)
              → Fisher ORA results per cluster

verbose_fields:
  - cluster_functional_description
  - cluster_expression_dynamics
  - cluster_temporal_pattern
  - cluster_member_count

chaining:
  - "list_clustering_analyses → cluster_enrichment"
  - "ontology_landscape → cluster_enrichment"
  - "cluster_enrichment → gene_overview"
  - "cluster_enrichment → genes_in_cluster"

mistakes:
  - "Default background is `cluster_union` (union of all clustered genes, including size-filtered). Use `'organism'` only when clustering covers the full genome."
  - "BH correction is per-cluster, NOT across clusters."
  - "Single-organism enforced."
  - "No signed_score — clusters aren't directional. For direction-aware enrichment, use pathway_enrichment with DE experiments."
  - "At least one of `level` or `term_ids` must be provided."
  - "`min/max_gene_set_size` is the pathway M filter (per-cluster, clusterProfiler semantics). `min/max_cluster_size` is the cluster membership filter."
  - "For BRITE, scope to a specific tree with `tree=`. Use `list_filter_values('brite_tree')` to discover trees."
  - wrong: "cluster_enrichment(..., background='table_scope')  # not valid"
    right: "cluster_enrichment(..., background='cluster_union')  # or 'organism', or a locus_tag list"
```

- [ ] **Step 2: Generate the about-content MD**

Run: `uv run python scripts/build_about_content.py`

Verify output file exists: `multiomics_explorer/skills/multiomics-kg-guide/references/tools/cluster_enrichment.md`

- [ ] **Step 3: Sync skills**

Run: `bash scripts/sync_skills.sh`

- [ ] **Step 4: Commit**

```bash
git add multiomics_explorer/inputs/tools/cluster_enrichment.yaml multiomics_explorer/skills/multiomics-kg-guide/references/tools/cluster_enrichment.md
git commit -m "docs: add cluster_enrichment YAML and generated about-content"
```

---

### Task 8: Update enrichment.md and examples

**Files:**
- Modify: `multiomics_explorer/analysis/enrichment.md`
- Modify: `examples/pathway_enrichment.py`

- [ ] **Step 1: Update enrichment.md §5**

In `multiomics_explorer/analysis/enrichment.md`, after the code block in §5 (around line 200), add:

```markdown
**MCP convenience:** The `cluster_enrichment` tool automates this pipeline in a single
call — pass `analysis_id`, `organism`, `ontology`, and `level`. Background defaults to
`cluster_union` (all clustered genes). See `docs://tools/cluster_enrichment`.
```

- [ ] **Step 2: Update enrichment.md §14**

In §14 (around line 490), update the paragraph that says "For any other gene-list source...":

```markdown
For any other gene-list source (ortholog groups, custom lists), use the Python primitives
directly. For cluster-membership enrichment, use the `cluster_enrichment` MCP tool — it
automates the pattern from §5 in a single call.
```

- [ ] **Step 3: Update example script**

In `examples/pathway_enrichment.py`, add a comment at the top of `scenario_3_cluster` (line ~118):

```python
def scenario_3_cluster(args: argparse.Namespace) -> None:
    """Cluster-membership enrichment (non-DE).

    For the MCP convenience wrapper, use cluster_enrichment(analysis_id=...).
    """
```

- [ ] **Step 4: Commit**

```bash
git add multiomics_explorer/analysis/enrichment.md examples/pathway_enrichment.py
git commit -m "docs: update enrichment.md and examples for cluster_enrichment tool"
```

---

### Task 9: Integration tests (requires Neo4j)

**Files:**
- Modify: `tests/integration/test_api_contract.py`
- Modify: `tests/integration/test_mcp_tools.py`

- [ ] **Step 1: Add contract test**

Append to `tests/integration/test_api_contract.py`:

```python
@pytest.mark.kg
class TestClusterEnrichmentContract:
    """Verify cluster_enrichment return shape against live KG."""

    def test_envelope_keys(self, conn):
        from multiomics_explorer.api import list_clustering_analyses, cluster_enrichment
        # Find a real analysis
        analyses = list_clustering_analyses(limit=1, conn=conn)
        if not analyses["results"]:
            pytest.skip("No clustering analyses in KG")
        analysis = analyses["results"][0]
        result = cluster_enrichment(
            analysis_id=analysis["analysis_id"],
            organism=analysis["organism_name"],
            ontology="cyanorak_role",
            level=1,
            pvalue_cutoff=1.0,  # accept all to get rows
            limit=5,
            conn=conn,
        )
        assert isinstance(result, dict)
        for key in ("analysis_id", "organism_name", "ontology", "total_matching",
                     "returned", "truncated", "not_found", "not_matched",
                     "clusters_skipped", "results", "background_mode",
                     "background_size", "n_significant"):
            assert key in result, f"Missing key: {key}"

    def test_result_row_keys(self, conn):
        from multiomics_explorer.api import list_clustering_analyses, cluster_enrichment
        analyses = list_clustering_analyses(limit=1, conn=conn)
        if not analyses["results"]:
            pytest.skip("No clustering analyses in KG")
        analysis = analyses["results"][0]
        result = cluster_enrichment(
            analysis_id=analysis["analysis_id"],
            organism=analysis["organism_name"],
            ontology="cyanorak_role",
            level=1,
            pvalue_cutoff=1.0,
            limit=5,
            conn=conn,
        )
        if not result["results"]:
            pytest.skip("No enrichment results (insufficient data)")
        row = result["results"][0]
        for key in ("cluster", "cluster_id", "term_id", "term_name",
                     "gene_ratio", "bg_ratio", "pvalue", "p_adjust",
                     "count", "bg_count", "fold_enrichment"):
            assert key in row, f"Missing row key: {key}"
```

- [ ] **Step 2: Add MCP smoke test**

Append to `tests/integration/test_mcp_tools.py`:

```python
@pytest.mark.kg
class TestClusterEnrichmentIntegration:
    """Live-KG integration for cluster_enrichment."""

    def test_basic_call(self, conn):
        from multiomics_explorer.api import list_clustering_analyses, cluster_enrichment
        analyses = list_clustering_analyses(limit=1, conn=conn)
        if not analyses["results"]:
            pytest.skip("No clustering analyses in KG")
        analysis = analyses["results"][0]
        result = cluster_enrichment(
            analysis_id=analysis["analysis_id"],
            organism=analysis["organism_name"],
            ontology="cyanorak_role",
            level=1,
            pvalue_cutoff=1.0,
            limit=5,
            conn=conn,
        )
        assert isinstance(result["results"], list)
        assert result["background_mode"] == "cluster_union"

    def test_organism_background_differs(self, conn):
        from multiomics_explorer.api import list_clustering_analyses, cluster_enrichment
        analyses = list_clustering_analyses(limit=1, conn=conn)
        if not analyses["results"]:
            pytest.skip("No clustering analyses in KG")
        analysis = analyses["results"][0]
        r_union = cluster_enrichment(
            analysis_id=analysis["analysis_id"],
            organism=analysis["organism_name"],
            ontology="cyanorak_role", level=1,
            background="cluster_union", summary=True, conn=conn,
        )
        r_org = cluster_enrichment(
            analysis_id=analysis["analysis_id"],
            organism=analysis["organism_name"],
            ontology="cyanorak_role", level=1,
            background="organism", summary=True, conn=conn,
        )
        # Organism background should be >= cluster_union
        assert r_org["background_size"] >= r_union["background_size"]
```

- [ ] **Step 3: Run integration tests**

Run: `pytest tests/integration/test_api_contract.py::TestClusterEnrichmentContract tests/integration/test_mcp_tools.py::TestClusterEnrichmentIntegration -m kg -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_api_contract.py tests/integration/test_mcp_tools.py
git commit -m "test: add cluster_enrichment integration and contract tests"
```

---

### Task 10: Run full test suite + final verification

- [ ] **Step 1: Run unit tests**

Run: `pytest tests/unit/ -v`
Expected: PASS (all existing tests + new cluster_enrichment tests)

- [ ] **Step 2: Run integration tests**

Run: `pytest -m kg -v`
Expected: PASS

- [ ] **Step 3: Restart MCP server and verify tool appears**

Run: `/mcp` to restart MCP server, then verify `cluster_enrichment` appears in the tool list.

- [ ] **Step 4: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "fix: address test suite issues from cluster_enrichment integration"
```
