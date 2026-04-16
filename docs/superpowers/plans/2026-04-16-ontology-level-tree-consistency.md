# Ontology Level & Tree Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `level` (input + output) and BRITE `tree`/`tree_code` (output sparse; input filter) consistently across all ontology tools; add `mode`/`organism` to `gene_ontology_terms`; add `brite_tree` to `list_filter_values`.

**Architecture:** Query builders gain level/tree columns and conditional WHERE clauses. API layer passes through new params, strips sparse `None` fields, validates `tree` only with BRITE. MCP layer adds params and model fields. `gene_ontology_terms` gets a `mode` param (`"leaf"`/`"rollup"`) and requires `organism`. Rollup mode reuses `_hierarchy_walk` walk fragments.

**Tech Stack:** Python, Neo4j (Cypher), FastMCP, pytest

**Spec:** `docs/superpowers/specs/2026-04-16-ontology-level-tree-consistency-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `multiomics_explorer/kg/queries_lib.py` | Modify | Add level/tree to search_ontology builders; add organism/mode/level/tree to gene_ontology_terms builders; add tree to genes_by_ontology/landscape builders; add `build_list_brite_trees` |
| `multiomics_explorer/api/functions.py` | Modify | Pass through new params, sparse field stripping, validation, `brite_tree` filter type, organism resolution for gene_ontology_terms |
| `multiomics_explorer/mcp_server/tools.py` | Modify | New params on 6 tools, new fields on 5 result models, updated Literals |
| `tests/unit/test_query_builders.py` | Modify | Tests for all builder changes |
| `tests/unit/test_tool_correctness.py` | Modify | Tests for tool-layer changes |
| `tests/integration/test_cyver_queries.py` | Modify | BRITE parametrizations with new params |
| `tests/integration/test_param_edge_cases.py` | Modify | Validation error cases |
| `tests/integration/test_examples.py` | Modify | `brite` scenario smoke test |
| `multiomics_explorer/inputs/tools/*.yaml` | Modify | 6 YAML tool docs |
| `multiomics_explorer/analysis/enrichment.md` | Modify | BRITE enrichment guidance |
| `multiomics_explorer/skills/.../references/analysis/enrichment.md` | Modify | Mirror of above |
| `examples/pathway_enrichment.py` | Modify | New `brite` scenario |
| `tests/regression/` | Modify | New + regenerated golden files |

---

### Task 1: `list_filter_values` — add `brite_tree` filter type

Smallest change, standalone. Establishes the tree discovery mechanism.

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:872-878` (add `build_list_brite_trees` after `build_list_gene_categories`)
- Modify: `multiomics_explorer/api/functions.py:517-542` (add `brite_tree` branch)
- Modify: `multiomics_explorer/mcp_server/tools.py:285-330` (update `Literal`, model, docs)
- Test: `tests/unit/test_query_builders.py`
- Test: `tests/unit/test_tool_correctness.py`

- [ ] **Step 1: Write failing test for `build_list_brite_trees`**

In `tests/unit/test_query_builders.py`, add after existing `build_list_gene_categories` tests (or at end of file):

```python
class TestBuildListBriteTrees:
    def test_returns_tree_and_tree_code_columns(self):
        from multiomics_explorer.kg.queries_lib import build_list_brite_trees
        cypher, params = build_list_brite_trees()
        assert "b.tree AS tree" in cypher
        assert "b.tree_code AS tree_code" in cypher
        assert "count(*) AS term_count" in cypher
        assert "ORDER BY b.tree" in cypher
        assert params == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListBriteTrees -v`
Expected: FAIL — `ImportError: cannot import name 'build_list_brite_trees'`

- [ ] **Step 3: Implement `build_list_brite_trees`**

In `multiomics_explorer/kg/queries_lib.py`, after `build_list_gene_categories` (line 878), add:

```python
def build_list_brite_trees() -> tuple[str, dict]:
    """List BRITE trees with term counts.

    RETURN keys: tree, tree_code, term_count.
    """
    cypher = (
        "MATCH (b:BriteCategory)\n"
        "RETURN b.tree AS tree, b.tree_code AS tree_code, "
        "count(*) AS term_count\n"
        "ORDER BY b.tree"
    )
    return cypher, {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListBriteTrees -v`
Expected: PASS

- [ ] **Step 5: Write failing test for API `brite_tree` filter**

In `tests/unit/test_tool_correctness.py`, add to `TestListFilterValuesCorrectness`:

```python
@pytest.mark.asyncio
async def test_brite_tree_filter_type(self, tool_fns, mock_ctx):
    """brite_tree returns trees with tree_code."""
    with patch(
        "multiomics_explorer.api.functions.list_filter_values",
        return_value={
            "filter_type": "brite_tree",
            "total_entries": 12,
            "returned": 12,
            "truncated": False,
            "results": [
                {"value": "enzymes", "tree_code": "ko01000", "count": 2057},
                {"value": "transporters", "tree_code": "ko02000", "count": 184},
            ],
        },
    ):
        result = await tool_fns["list_filter_values"](
            mock_ctx, filter_type="brite_tree",
        )
    assert result.filter_type == "brite_tree"
    assert result.total_entries == 12
    assert len(result.results) == 2
    assert result.results[0].value == "enzymes"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/unit/test_tool_correctness.py::TestListFilterValuesCorrectness::test_brite_tree_filter_type -v`
Expected: FAIL — `"brite_tree"` not in Literal, rejected by pydantic validation.

- [ ] **Step 7: Update API `list_filter_values`**

In `multiomics_explorer/api/functions.py:528-531`, change:

```python
    if filter_type == "gene_category":
        cypher, params = build_list_gene_categories()
    else:
        raise ValueError(f"Unknown filter_type: {filter_type!r}")
    rows = conn.execute_query(cypher, **params)
    # Normalise to generic {value, count} shape
    results = [{"value": r["category"], "count": r["gene_count"]} for r in rows]
```

to:

```python
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
    else:
        raise ValueError(f"Unknown filter_type: {filter_type!r}")
```

Add `build_list_brite_trees` to the imports from `queries_lib` at the top of the file.

- [ ] **Step 8: Update MCP tool `list_filter_values`**

In `multiomics_explorer/mcp_server/tools.py:306`, change:

```python
        filter_type: Annotated[Literal["gene_category"], Field(
```

to:

```python
        filter_type: Annotated[Literal["gene_category", "brite_tree"], Field(
```

Update the description at line 307-308 to mention `brite_tree`:

```python
            description="Which filter's valid values to return. "
            "'gene_category': values for the category filter in genes_by_function. "
            "'brite_tree': BRITE tree names for the tree filter in ontology tools.",
```

- [ ] **Step 9: Run tests**

Run: `pytest tests/unit/test_query_builders.py::TestBuildListBriteTrees tests/unit/test_tool_correctness.py::TestListFilterValuesCorrectness -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py multiomics_explorer/api/functions.py multiomics_explorer/mcp_server/tools.py tests/unit/test_query_builders.py tests/unit/test_tool_correctness.py
git commit -m "feat: add brite_tree filter type to list_filter_values"
```

---

### Task 2: `search_ontology` — add `level` and `tree` to builders

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:1191-1284`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_query_builders.py`, add to `TestBuildSearchOntology`:

```python
    def test_returns_level_column(self):
        cypher, _ = build_search_ontology(ontology="go_bp", search_text="test")
        assert "t.level AS level" in cypher

    def test_returns_tree_columns(self):
        cypher, _ = build_search_ontology(ontology="brite", search_text="test")
        assert "t.tree AS tree" in cypher
        assert "t.tree_code AS tree_code" in cypher

    def test_level_filter_adds_where_clause(self):
        cypher, params = build_search_ontology(
            ontology="go_bp", search_text="test", level=2,
        )
        assert "t.level = $level" in cypher
        assert params["level"] == 2

    def test_tree_filter_adds_where_clause(self):
        cypher, params = build_search_ontology(
            ontology="brite", search_text="test", tree="transporters",
        )
        assert "t.tree = $tree" in cypher
        assert params["tree"] == "transporters"

    def test_tree_filter_with_non_brite_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_search_ontology(
                ontology="go_bp", search_text="test", tree="transporters",
            )

    def test_pfam_union_level_filter_inside_branches(self):
        cypher, params = build_search_ontology(
            ontology="pfam", search_text="test", level=1,
        )
        # Level filter must appear inside each UNION branch
        assert cypher.count("t.level = $level") == 2
        assert params["level"] == 1
```

Add matching tests for `TestBuildSearchOntologySummary` (same patterns for the summary builder):

```python
class TestBuildSearchOntologySummary:
    def test_level_filter_adds_where_clause(self):
        cypher, params = build_search_ontology_summary(
            ontology="go_bp", search_text="test", level=2,
        )
        assert "t.level = $level" in cypher
        assert params["level"] == 2

    def test_tree_filter_adds_where_clause(self):
        cypher, params = build_search_ontology_summary(
            ontology="brite", search_text="test", tree="transporters",
        )
        assert "t.tree = $tree" in cypher
        assert params["tree"] == "transporters"

    def test_tree_filter_with_non_brite_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_search_ontology_summary(
                ontology="go_bp", search_text="test", tree="x",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildSearchOntology::test_returns_level_column tests/unit/test_query_builders.py::TestBuildSearchOntology::test_level_filter_adds_where_clause -v`
Expected: FAIL — no `level` param accepted, no `level` in RETURN.

- [ ] **Step 3: Update `build_search_ontology_summary`**

In `multiomics_explorer/kg/queries_lib.py`, change the signature at line 1191:

```python
def build_search_ontology_summary(
    *, ontology: str, search_text: str,
    level: int | None = None,
    tree: str | None = None,
) -> tuple[str, dict]:
```

Add validation after `cfg = ONTOLOGY_CONFIG[ontology]` (after line 1200):

```python
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
```

For the **single-index branch** (line 1225–1232), add WHERE clause and update the aggregation to filter before counting:

```python
    else:
        label = cfg["label"]
        # Build optional filters
        filters = []
        if level is not None:
            filters.append("t.level = $level")
        if tree is not None:
            filters.append("t.tree = $tree")
        where_clause = ""
        if filters:
            where_clause = "WHERE " + " AND ".join(filters) + "\n"

        cypher = (
            f"CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "YIELD node AS t, score\n"
            f"{where_clause}"
            "WITH count(t) AS total_matching,\n"
            "     max(score) AS score_max,\n"
            "     percentileDisc(score, 0.5) AS score_median\n"
            f"CALL {{ MATCH (all_t:{label}) RETURN count(all_t) AS total_entries }}\n"
            "RETURN total_entries, total_matching, score_max, score_median"
        )
```

For the **Pfam UNION branch** (lines 1204–1221), add the level filter inside each UNION branch (tree doesn't apply to Pfam so no tree filter needed here):

```python
    if parent_index:
        pfam_filter = ""
        if level is not None:
            pfam_filter = "WHERE t.level = $level\n"

        cypher = (
            "CALL {\n"
            f"  CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "  YIELD node AS t, score\n"
            f"  {pfam_filter}"
            "  RETURN score\n"
            "  UNION ALL\n"
            f"  CALL db.index.fulltext.queryNodes('{parent_index}', $search_text)\n"
            "  YIELD node AS t, score\n"
            f"  {pfam_filter}"
            "  RETURN score\n"
            "}\n"
            "WITH count(score) AS total_matching,\n"
            "     max(score) AS score_max,\n"
            "     percentileDisc(score, 0.5) AS score_median\n"
            "CALL { MATCH (all_t:Pfam) RETURN count(all_t) AS pfam_count }\n"
            "CALL { MATCH (all_c:PfamClan) RETURN count(all_c) AS clan_count }\n"
            "RETURN pfam_count + clan_count AS total_entries,\n"
            "       total_matching, score_max, score_median"
        )
```

Update the params dict at the end:

```python
    params: dict = {"search_text": search_text}
    if level is not None:
        params["level"] = level
    if tree is not None:
        params["tree"] = tree
    return cypher, params
```

- [ ] **Step 4: Update `build_search_ontology`**

Change the signature at line 1237:

```python
def build_search_ontology(
    *, ontology: str, search_text: str,
    level: int | None = None,
    tree: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
```

Update docstring: `RETURN keys: id, name, score, level, tree, tree_code.`

Add validation after line 1250:

```python
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
```

Add level/tree to params dict (after line 1252):

```python
    params: dict = {"search_text": search_text}
    if level is not None:
        params["level"] = level
    if tree is not None:
        params["tree"] = tree
```

For the **single-index branch** (line 1277–1283):

```python
    else:
        filters = []
        if level is not None:
            filters.append("t.level = $level")
        if tree is not None:
            filters.append("t.tree = $tree")
        where_clause = ""
        if filters:
            where_clause = "WHERE " + " AND ".join(filters) + "\n"

        cypher = (
            f"CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "YIELD node AS t, score\n"
            f"{where_clause}"
            "RETURN t.id AS id, t.name AS name, score,\n"
            "       t.level AS level, t.tree AS tree, t.tree_code AS tree_code\n"
            "ORDER BY score DESC, id" + skip_clause + limit_clause
        )
```

For the **Pfam UNION branch** (line 1262–1275):

```python
    if parent_index:
        pfam_filter = ""
        if level is not None:
            pfam_filter = "  WHERE t.level = $level\n"

        cypher = (
            "CALL {\n"
            f"  CALL db.index.fulltext.queryNodes('{index_name}', $search_text)\n"
            "  YIELD node AS t, score\n"
            f"{pfam_filter}"
            "  RETURN t.id AS id, t.name AS name, score,\n"
            "         t.level AS level, t.tree AS tree, t.tree_code AS tree_code\n"
            "  UNION ALL\n"
            f"  CALL db.index.fulltext.queryNodes('{parent_index}', $search_text)\n"
            "  YIELD node AS t, score\n"
            f"{pfam_filter}"
            "  RETURN t.id AS id, t.name AS name, score,\n"
            "         t.level AS level, t.tree AS tree, t.tree_code AS tree_code\n"
            "}\n"
            "RETURN id, name, score, level, tree, tree_code\n"
            "ORDER BY score DESC, id" + skip_clause + limit_clause
        )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_query_builders.py::TestBuildSearchOntology tests/unit/test_query_builders.py::TestBuildSearchOntologySummary -v`
Expected: All PASS

- [ ] **Step 6: Run full query builder suite for regressions**

Run: `pytest tests/unit/test_query_builders.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: add level and tree to search_ontology query builders"
```

---

### Task 3: `search_ontology` — API + MCP layer

**Files:**
- Modify: `multiomics_explorer/api/functions.py:877-955`
- Modify: `multiomics_explorer/mcp_server/tools.py:958-998`
- Test: `tests/unit/test_tool_correctness.py`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_tool_correctness.py`, add to `TestSearchOntologyCorrectness`:

```python
@pytest.mark.asyncio
async def test_level_in_result_rows(self, tool_fns, mock_ctx):
    """Results include level field."""
    with patch(
        "multiomics_explorer.api.functions.search_ontology",
        return_value={
            "total_entries": 100,
            "total_matching": 1,
            "score_max": 3.0,
            "score_median": 3.0,
            "returned": 1,
            "truncated": False,
            "results": [
                {"id": "go:0006260", "name": "DNA replication", "score": 3.0, "level": 5},
            ],
        },
    ):
        result = await tool_fns["search_ontology"](
            mock_ctx, search_text="replication", ontology="go_bp",
        )
    assert result.results[0].level == 5

@pytest.mark.asyncio
async def test_brite_result_has_tree(self, tool_fns, mock_ctx):
    """BRITE results include tree and tree_code."""
    with patch(
        "multiomics_explorer.api.functions.search_ontology",
        return_value={
            "total_entries": 100,
            "total_matching": 1,
            "score_max": 3.0,
            "score_median": 3.0,
            "returned": 1,
            "truncated": False,
            "results": [
                {"id": "kegg.brite:ko02000.A5", "name": "PTS", "score": 3.0,
                 "level": 0, "tree": "transporters", "tree_code": "ko02000"},
            ],
        },
    ):
        result = await tool_fns["search_ontology"](
            mock_ctx, search_text="PTS", ontology="brite",
        )
    assert result.results[0].tree == "transporters"
    assert result.results[0].tree_code == "ko02000"

@pytest.mark.asyncio
async def test_non_brite_result_no_tree(self, tool_fns, mock_ctx):
    """Non-BRITE results have no tree/tree_code fields (sparse)."""
    with patch(
        "multiomics_explorer.api.functions.search_ontology",
        return_value={
            "total_entries": 100,
            "total_matching": 1,
            "score_max": 3.0,
            "score_median": 3.0,
            "returned": 1,
            "truncated": False,
            "results": [
                {"id": "go:0006260", "name": "DNA replication", "score": 3.0, "level": 5},
            ],
        },
    ):
        result = await tool_fns["search_ontology"](
            mock_ctx, search_text="replication", ontology="go_bp",
        )
    assert result.results[0].tree is None
    assert result.results[0].tree_code is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tool_correctness.py::TestSearchOntologyCorrectness::test_level_in_result_rows -v`
Expected: FAIL — `SearchOntologyResult` has no `level` field.

- [ ] **Step 3: Update `SearchOntologyResult` model**

In `multiomics_explorer/mcp_server/tools.py:958-961`, change:

```python
    class SearchOntologyResult(BaseModel):
        id: str = Field(description="Term ID (e.g. 'go:0006260')")
        name: str = Field(description="Term name (e.g. 'DNA replication')")
        score: float = Field(description="Fulltext relevance score (e.g. 5.23)")
```

to:

```python
    class SearchOntologyResult(BaseModel):
        id: str = Field(description="Term ID (e.g. 'go:0006260')")
        name: str = Field(description="Term name (e.g. 'DNA replication')")
        score: float = Field(description="Fulltext relevance score (e.g. 5.23)")
        level: int = Field(description="Hierarchy level of this term (0 = broadest)")
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
```

- [ ] **Step 4: Update `search_ontology` tool params**

In `multiomics_explorer/mcp_server/tools.py`, after the `offset` param (line 997), add:

```python
        level: Annotated[int | None, Field(
            description="Filter to terms at this hierarchy level. 0 = broadest.",
            ge=0,
        )] = None,
        tree: Annotated[str | None, Field(
            description="BRITE tree name filter (e.g. 'transporters'). "
            "Only valid when ontology='brite'.",
        )] = None,
```

Update the tool function body to pass `level` and `tree` to the API call.

- [ ] **Step 5: Update API `search_ontology`**

In `multiomics_explorer/api/functions.py:877`, update the signature:

```python
def search_ontology(
    search_text: str,
    ontology: str,
    summary: bool = False,
    limit: int | None = None,
    offset: int = 0,
    level: int | None = None,
    tree: str | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
```

Pass `level` and `tree` to both builder calls. In the summary call (around line 906):

```python
        envelope = conn.execute_query(
            *build_search_ontology_summary(
                ontology=ontology, search_text=search_text,
                level=level, tree=tree,
            )
        )
```

In the detail call (around line 935):

```python
        results = conn.execute_query(
            *build_search_ontology(
                ontology=ontology, search_text=search_text,
                level=level, tree=tree,
                limit=effective_limit, offset=offset,
            )
        )
```

After the detail call, strip sparse fields:

```python
    for r in results:
        if r.get("tree") is None:
            r.pop("tree", None)
            r.pop("tree_code", None)
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_tool_correctness.py::TestSearchOntologyCorrectness -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_correctness.py
git commit -m "feat: add level and tree to search_ontology API + MCP layer"
```

---

### Task 4: `gene_ontology_terms` — query builders (organism, mode, level, tree)

This is the biggest builder change. The builders gain `organism_name`, `mode`, `level`, and `tree` params.

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:1583-1728`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests for leaf mode with level**

In `tests/unit/test_query_builders.py`, add:

```python
class TestBuildGeneOntologyTermsLevelTree:
    def test_leaf_mode_returns_level_column(self):
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp",
            organism_name="Prochlorococcus MED4",
        )
        assert "t.level AS level" in cypher

    def test_leaf_mode_with_level_filter(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp",
            organism_name="Prochlorococcus MED4",
            level=5,
        )
        assert "t.level = $level" in cypher
        assert params["level"] == 5

    def test_leaf_mode_returns_tree_columns(self):
        cypher, _ = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="brite",
            organism_name="Test Org",
        )
        assert "t.tree AS tree" in cypher
        assert "t.tree_code AS tree_code" in cypher

    def test_tree_filter(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="brite",
            organism_name="Test Org",
            tree="transporters",
        )
        assert "t.tree = $tree" in cypher
        assert params["tree"] == "transporters"

    def test_tree_filter_with_non_brite_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_gene_ontology_terms(
                locus_tags=["PMM0001"], ontology="go_bp",
                organism_name="Test Org",
                tree="transporters",
            )

    def test_organism_scoped_match(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp",
            organism_name="Prochlorococcus MED4",
        )
        assert "organism_name: $org" in cypher
        assert "locus_tag IN $locus_tags" in cypher
        assert params["org"] == "Prochlorococcus MED4"

    def test_rollup_mode_uses_hierarchy_walk(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="go_bp",
            organism_name="Prochlorococcus MED4",
            mode="rollup", level=2,
        )
        # Walk up pattern
        assert "Biological_process_is_a_biological_process" in cypher
        assert "*0.." in cypher
        assert "t.level = $level" in cypher
        assert params["level"] == 2
        # DISTINCT for convergent paths
        assert "DISTINCT" in cypher
        # No leaf filter in rollup mode
        assert "NOT EXISTS" not in cypher

    def test_rollup_without_level_raises(self):
        with pytest.raises(ValueError, match="level is required"):
            build_gene_ontology_terms(
                locus_tags=["PMM0001"], ontology="go_bp",
                organism_name="Test Org",
                mode="rollup",
            )

    def test_rollup_brite_bridge(self):
        cypher, params = build_gene_ontology_terms(
            locus_tags=["PMM0001"], ontology="brite",
            organism_name="Test Org",
            mode="rollup", level=0,
        )
        assert ":Gene_has_kegg_ko" in cypher
        assert ":KeggTerm" in cypher
        assert ":Kegg_term_in_brite_category" in cypher
        assert "Brite_category_is_a_brite_category*0.." in cypher
        assert "t.level = $level" in cypher
        assert "DISTINCT" in cypher
```

- [ ] **Step 2: Write failing tests for summary builder**

```python
class TestBuildGeneOntologyTermsSummaryLevelTree:
    def test_leaf_mode_collects_level_and_tree(self):
        cypher, _ = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="brite",
            organism_name="Test Org",
        )
        assert "t.level" in cypher
        assert "t.tree" in cypher
        assert "t.tree_code" in cypher

    def test_rollup_mode_walks_hierarchy(self):
        cypher, params = build_gene_ontology_terms_summary(
            locus_tags=["PMM0001"], ontology="go_bp",
            organism_name="Prochlorococcus MED4",
            mode="rollup", level=2,
        )
        assert "*0.." in cypher
        assert "t.level = $level" in cypher
        assert params["level"] == 2

    def test_rollup_without_level_raises(self):
        with pytest.raises(ValueError, match="level is required"):
            build_gene_ontology_terms_summary(
                locus_tags=["PMM0001"], ontology="go_bp",
                organism_name="Test Org",
                mode="rollup",
            )
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneOntologyTermsLevelTree tests/unit/test_query_builders.py::TestBuildGeneOntologyTermsSummaryLevelTree -v`
Expected: FAIL — builders don't accept new params.

- [ ] **Step 4: Update `build_gene_ontology_terms`**

In `multiomics_explorer/kg/queries_lib.py`, change the signature at line 1667:

```python
def build_gene_ontology_terms(
    *,
    locus_tags: list[str],
    ontology: str,
    organism_name: str,
    mode: str = "leaf",
    level: int | None = None,
    tree: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
```

Update the docstring to reflect new modes.

Add validation after the existing ontology check:

```python
    if mode == "rollup" and level is None:
        raise ValueError("level is required when mode='rollup'")
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
```

Replace the MATCH construction and RETURN. The full function body becomes:

```python
    cfg = ONTOLOGY_CONFIG[ontology]
    gene_rel = cfg["gene_rel"]
    label = cfg["label"]

    params: dict = {"locus_tags": locus_tags, "org": organism_name}

    verbose_cols = (
        ",\n       g.organism_name AS organism_name"
        if verbose else ""
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

    # Tree filter clause (BRITE only, validated above)
    tree_clause = ""
    if tree is not None:
        tree_clause = " AND t.tree = $tree"
        params["tree"] = tree

    if mode == "rollup":
        # Walk up from leaf annotations to ancestors at target level
        params["level"] = level
        frag = _hierarchy_walk(ontology, direction="up")

        bridge = cfg.get("bridge")
        if bridge:
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(ko:{bridge['node_label']})"
                f"-[:{bridge['edge']}]->(leaf:{label})\n"
                "WHERE g.locus_tag IN $locus_tags"
            )
        else:
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(leaf:{label})\n"
                "WHERE g.locus_tag IN $locus_tags"
            )

        walk = frag["walk_up"]
        level_clause = f"WHERE t.level = $level{tree_clause}"

        cypher = (
            f"{bind}\n"
            f"{walk}\n"
            f"{level_clause}\n"
            "RETURN DISTINCT g.locus_tag AS locus_tag, t.id AS term_id,\n"
            "       t.name AS term_name, t.level AS level,\n"
            f"       t.tree AS tree, t.tree_code AS tree_code{verbose_cols}\n"
            f"ORDER BY g.locus_tag, t.id{skip_clause}{limit_clause}"
        )
    else:
        # Leaf mode
        leaf_filter = _gene_ontology_terms_leaf_filter(cfg)
        bridge = cfg.get("bridge")
        if bridge:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(:{bridge['node_label']})"
                f"-[:{bridge['edge']}]->(t:{label})\n"
            )
        else:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(t:{label})\n"
            )

        # Merge locus_tag filter with leaf filter
        locus_where = "WHERE g.locus_tag IN $locus_tags"
        level_filter = ""
        if level is not None:
            level_filter = f" AND t.level = $level"
            params["level"] = level

        if leaf_filter:
            # leaf_filter starts with "WHERE NOT EXISTS" — convert to AND
            combined_where = (
                f"{locus_where}{level_filter}{tree_clause}\n"
                f"  AND {leaf_filter.replace('WHERE ', '')}"
            )
        else:
            combined_where = f"{locus_where}{level_filter}{tree_clause}\n"

        cypher = (
            f"{match_line}"
            f"{combined_where}"
            "RETURN g.locus_tag AS locus_tag, t.id AS term_id,\n"
            "       t.name AS term_name, t.level AS level,\n"
            f"       t.tree AS tree, t.tree_code AS tree_code{verbose_cols}\n"
            f"ORDER BY g.locus_tag, t.id{skip_clause}{limit_clause}"
        )
    return cypher, params
```

- [ ] **Step 5: Update `build_gene_ontology_terms_summary`**

Change the signature at line 1613:

```python
def build_gene_ontology_terms_summary(
    *,
    locus_tags: list[str],
    ontology: str,
    organism_name: str,
    mode: str = "leaf",
    level: int | None = None,
    tree: str | None = None,
) -> tuple[str, dict]:
```

Add same validation. Replace the function body with mode-aware logic:

```python
    cfg = ONTOLOGY_CONFIG[ontology]
    gene_rel = cfg["gene_rel"]
    label = cfg["label"]

    if mode == "rollup" and level is None:
        raise ValueError("level is required when mode='rollup'")
    if tree is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")

    params: dict = {"locus_tags": locus_tags, "org": organism_name}

    tree_clause = ""
    if tree is not None:
        tree_clause = " AND t.tree = $tree"
        params["tree"] = tree

    if mode == "rollup":
        params["level"] = level
        frag = _hierarchy_walk(ontology, direction="up")
        bridge = cfg.get("bridge")
        if bridge:
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(ko:{bridge['node_label']})"
                f"-[:{bridge['edge']}]->(leaf:{label})\n"
                "WHERE g.locus_tag IN $locus_tags"
            )
        else:
            bind = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(leaf:{label})\n"
                "WHERE g.locus_tag IN $locus_tags"
            )
        walk = frag["walk_up"]
        level_clause = f"WHERE t.level = $level{tree_clause}"

        cypher = (
            f"{bind}\n"
            f"{walk}\n"
            f"{level_clause}\n"
            "WITH g.locus_tag AS lt, collect(DISTINCT "
            "{id: t.id, name: t.name, level: t.level, "
            "tree: t.tree, tree_code: t.tree_code}) AS terms\n"
            "WITH collect({lt: lt, cnt: size(terms), terms: terms}) AS genes\n"
            "WITH genes,\n"
            "     apoc.coll.flatten([g IN genes | g.terms]) AS all_terms,\n"
            "     [g IN genes | {locus_tag: g.lt, term_count: g.cnt}] "
            "AS gene_term_counts\n"
            "UNWIND all_terms AS t\n"
            "WITH genes, gene_term_counts, t.id AS tid, t.name AS tname, "
            "t.level AS tlevel, t.tree AS ttree, t.tree_code AS ttree_code, "
            "count(*) AS cnt\n"
            "WITH genes, gene_term_counts,\n"
            "     collect({term_id: tid, term_name: tname, level: tlevel, "
            "tree: ttree, tree_code: ttree_code, count: cnt}) AS by_term\n"
            "RETURN size(genes) AS gene_count,\n"
            "       size(apoc.coll.flatten([g IN genes | g.terms])) "
            "AS term_count,\n"
            "       by_term,\n"
            "       gene_term_counts"
        )
    else:
        # Leaf mode
        leaf_filter = _gene_ontology_terms_leaf_filter(cfg)
        bridge = cfg.get("bridge")
        if bridge:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(:{bridge['node_label']})"
                f"-[:{bridge['edge']}]->(t:{label})\n"
            )
        else:
            match_line = (
                f"MATCH (g:Gene {{organism_name: $org}})"
                f"-[:{gene_rel}]->(t:{label})\n"
            )

        locus_where = "WHERE g.locus_tag IN $locus_tags"
        level_filter = ""
        if level is not None:
            level_filter = f" AND t.level = $level"
            params["level"] = level

        if leaf_filter:
            combined_where = (
                f"{locus_where}{level_filter}{tree_clause}\n"
                f"  AND {leaf_filter.replace('WHERE ', '')}"
            )
        else:
            combined_where = f"{locus_where}{level_filter}{tree_clause}\n"

        cypher = (
            f"{match_line}"
            f"{combined_where}"
            "WITH g.locus_tag AS lt, collect({id: t.id, name: t.name, "
            "level: t.level, tree: t.tree, tree_code: t.tree_code}) AS terms\n"
            "WITH collect({lt: lt, cnt: size(terms), terms: terms}) AS genes\n"
            "WITH genes,\n"
            "     apoc.coll.flatten([g IN genes | g.terms]) AS all_terms,\n"
            "     [g IN genes | {locus_tag: g.lt, term_count: g.cnt}] "
            "AS gene_term_counts\n"
            "UNWIND all_terms AS t\n"
            "WITH genes, gene_term_counts, t.id AS tid, t.name AS tname, "
            "t.level AS tlevel, t.tree AS ttree, t.tree_code AS ttree_code, "
            "count(*) AS cnt\n"
            "WITH genes, gene_term_counts,\n"
            "     collect({term_id: tid, term_name: tname, level: tlevel, "
            "tree: ttree, tree_code: ttree_code, count: cnt}) AS by_term\n"
            "RETURN size(genes) AS gene_count,\n"
            "       size(apoc.coll.flatten([g IN genes | g.terms])) "
            "AS term_count,\n"
            "       by_term,\n"
            "       gene_term_counts"
        )
    return cypher, params
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_query_builders.py::TestBuildGeneOntologyTermsLevelTree tests/unit/test_query_builders.py::TestBuildGeneOntologyTermsSummaryLevelTree -v`
Expected: All PASS

- [ ] **Step 7: Fix existing tests that call old signatures**

The existing `TestBuildGeneOntologyTerms` and `TestBuildGeneOntologyTermsBrite` tests call the builders without `organism_name`. Update all existing calls to add `organism_name="Test Org"`. Search for all calls to `build_gene_ontology_terms(` and `build_gene_ontology_terms_summary(` in the test file and add the param.

- [ ] **Step 8: Run full suite**

Run: `pytest tests/unit/test_query_builders.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py tests/unit/test_query_builders.py
git commit -m "feat: add organism, mode, level, tree to gene_ontology_terms builders"
```

---

### Task 5: `gene_ontology_terms` — API + MCP layer

**Files:**
- Modify: `multiomics_explorer/api/functions.py:1391-1542`
- Modify: `multiomics_explorer/mcp_server/tools.py:1184-1246`
- Test: `tests/unit/test_tool_correctness.py`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_tool_correctness.py`, add to `TestGeneOntologyTermsCorrectness`:

```python
@pytest.mark.asyncio
async def test_level_in_result_rows(self, tool_fns, mock_ctx):
    """Results include level field."""
    with patch(
        "multiomics_explorer.api.functions.gene_ontology_terms",
        return_value={
            "total_matching": 1, "total_genes": 1, "total_terms": 1,
            "by_ontology": [], "by_term": [],
            "terms_per_gene_min": 1, "terms_per_gene_max": 1,
            "terms_per_gene_median": 1.0,
            "returned": 1, "truncated": False, "not_found": [], "no_terms": [],
            "results": [
                {"locus_tag": "PMM0001", "term_id": "go:0006260",
                 "term_name": "DNA replication", "level": 5},
            ],
        },
    ):
        result = await tool_fns["gene_ontology_terms"](
            mock_ctx, locus_tags=["PMM0001"], organism="MED4",
        )
    assert result.results[0].level == 5

@pytest.mark.asyncio
async def test_mode_rollup_without_level_raises(self, tool_fns, mock_ctx):
    """Rollup mode without level raises ToolError."""
    with pytest.raises(Exception):
        await tool_fns["gene_ontology_terms"](
            mock_ctx, locus_tags=["PMM0001"], organism="MED4",
            mode="rollup",
        )

@pytest.mark.asyncio
async def test_tree_with_non_brite_raises(self, tool_fns, mock_ctx):
    """tree param with non-BRITE ontology raises ToolError."""
    with pytest.raises(Exception):
        await tool_fns["gene_ontology_terms"](
            mock_ctx, locus_tags=["PMM0001"], organism="MED4",
            ontology="go_bp", tree="transporters",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tool_correctness.py::TestGeneOntologyTermsCorrectness::test_level_in_result_rows -v`
Expected: FAIL — no `organism` param on tool, no `level` on model.

- [ ] **Step 3: Update MCP models**

In `multiomics_explorer/mcp_server/tools.py:1184-1201`, update:

`OntologyTermRow` — add fields:

```python
    class OntologyTermRow(BaseModel):
        locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
        term_id: str = Field(description="Ontology term ID (e.g. 'go:0006260')")
        term_name: str = Field(description="Term name (e.g. 'DNA replication')")
        level: int = Field(description="Hierarchy level of this term (0 = broadest)")
        ontology_type: str | None = Field(default=None, description="Ontology type when querying all (e.g. 'go_bp')")
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
        organism_name: str | None = Field(default=None, description="Organism (verbose only)")
```

`OntologyTypeBreakdown` — add sparse tree fields:

```python
    class OntologyTypeBreakdown(BaseModel):
        ontology_type: str = Field(description="Ontology type (e.g. 'go_bp', 'kegg')")
        term_count: int = Field(description="Total terms in this ontology (e.g. 12)")
        gene_count: int = Field(description="Input genes with at least one term (e.g. 8)")
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
```

`TermBreakdown` — add level:

```python
    class TermBreakdown(BaseModel):
        term_id: str = Field(description="Ontology term ID (e.g. 'go:0015979')")
        term_name: str = Field(description="Term name (e.g. 'photosynthesis')")
        ontology_type: str = Field(description="Ontology type (e.g. 'go_bp')")
        level: int = Field(description="Hierarchy level of this term (0 = broadest)")
        count: int = Field(description="Genes annotated to this term (e.g. 4)")
```

- [ ] **Step 4: Update `gene_ontology_terms` tool params**

In `multiomics_explorer/mcp_server/tools.py:1223-1246`, update the signature. Add `organism` as required param after `locus_tags`, and add `mode`, `level`, `tree`:

```python
    async def gene_ontology_terms(
        ctx: Context,
        locus_tags: Annotated[list[str], Field(
            description="Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845'].",
        )],
        organism: Annotated[str, Field(
            description="Organism (case-insensitive substring match, e.g. 'MED4'). "
                        "Required — single-valued.",
        )],
        ontology: Annotated[
            Literal["go_bp", "go_mf", "go_cc", "kegg", "ec",
                    "cog_category", "cyanorak_role", "tigr_role", "pfam", "brite"] | None,
            Field(description="Filter to one ontology. None returns all."),
        ] = None,
        mode: Annotated[Literal["leaf", "rollup"], Field(
            description="'leaf' returns most-specific annotations (default). "
                        "'rollup' walks up to ancestors at the given level.",
        )] = "leaf",
        level: Annotated[int | None, Field(
            description="Hierarchy level. In leaf mode: filter to leaves at this level. "
                        "In rollup mode: required — target ancestor level (0 = broadest).",
            ge=0,
        )] = None,
        tree: Annotated[str | None, Field(
            description="BRITE tree name filter. Only valid when ontology='brite'.",
        )] = None,
        summary: Annotated[bool, Field(
            description="When true, return only summary fields (results=[]).",
        )] = False,
        verbose: Annotated[bool, Field(
            description="Include organism_name per row.",
        )] = False,
        limit: Annotated[int, Field(description="Max results.", ge=1)] = 5,
        offset: Annotated[int, Field(
            description="Number of results to skip for pagination.", ge=0,
        )] = 0,
    ) -> GeneOntologyTermsResponse:
```

Update the tool body to pass new params to the API.

- [ ] **Step 5: Update API `gene_ontology_terms`**

In `multiomics_explorer/api/functions.py:1391`, update signature:

```python
def gene_ontology_terms(
    locus_tags: list[str],
    organism: str,
    ontology: str | None = None,
    mode: str = "leaf",
    level: int | None = None,
    tree: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
```

Add organism resolution at the top (same pattern as `genes_by_ontology`):

```python
    organism = _validate_organism_inputs(
        organism=organism, locus_tags=None, experiment_ids=None, conn=conn,
    )
```

Add validation:

```python
    if mode == "rollup" and level is None:
        raise ValueError("level is required when mode='rollup'")
    if tree is not None and ontology is not None and ontology != "brite":
        raise ValueError("tree filter is only valid for ontology='brite'")
```

Pass new params to both summary and detail builder calls:

```python
    # In the summary loop:
    cypher, params = build_gene_ontology_terms_summary(
        locus_tags=chunk, ontology=ont,
        organism_name=organism,
        mode=mode, level=level, tree=tree,
    )

    # In the detail loop:
    cypher, params = build_gene_ontology_terms(
        locus_tags=chunk, ontology=ont,
        organism_name=organism,
        mode=mode, level=level, tree=tree,
        verbose=verbose, limit=..., offset=...,
    )
```

After assembling results, strip sparse fields:

```python
    for r in results:
        if r.get("tree") is None:
            r.pop("tree", None)
            r.pop("tree_code", None)
```

Also update `by_term` entries to include `level` from the summary data, and update `by_ontology` to include sparse `tree`/`tree_code` for BRITE entries.

- [ ] **Step 6: Fix existing tool correctness tests**

Update all existing `TestGeneOntologyTermsCorrectness` tests that call `gene_ontology_terms` to pass `organism="MED4"`.

- [ ] **Step 7: Run tests**

Run: `pytest tests/unit/test_tool_correctness.py::TestGeneOntologyTermsCorrectness -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_correctness.py
git commit -m "feat: add organism, mode, level, tree to gene_ontology_terms API + MCP"
```

---

### Task 6: `genes_by_ontology` — add `tree` across all layers

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:1436-1547` (detail + per_term builders)
- Modify: `multiomics_explorer/api/functions.py:1183-1389`
- Modify: `multiomics_explorer/mcp_server/tools.py:1022-1125`
- Test: `tests/unit/test_query_builders.py`
- Test: `tests/unit/test_tool_correctness.py`

- [ ] **Step 1: Write failing tests for builders**

In `tests/unit/test_query_builders.py`, add to `TestBuildGenesByOntologyDetail`:

```python
    def test_returns_tree_columns(self):
        cypher, _ = build_genes_by_ontology_detail(
            ontology="brite", organism="Test Org",
            level=1, min_gene_set_size=5, max_gene_set_size=500,
        )
        assert "t.tree AS tree" in cypher
        assert "t.tree_code AS tree_code" in cypher

    def test_tree_filter_adds_where(self):
        cypher, params = build_genes_by_ontology_detail(
            ontology="brite", organism="Test Org",
            level=1, min_gene_set_size=5, max_gene_set_size=500,
            tree="transporters",
        )
        assert "t.tree = $tree" in cypher
        assert params["tree"] == "transporters"

    def test_tree_filter_non_brite_raises(self):
        with pytest.raises(ValueError, match="tree filter is only valid"):
            build_genes_by_ontology_detail(
                ontology="go_bp", organism="Test Org",
                level=2, min_gene_set_size=5, max_gene_set_size=500,
                tree="transporters",
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py -k "test_returns_tree_columns or test_tree_filter_adds_where or test_tree_filter_non_brite_raises" -v`
Expected: FAIL

- [ ] **Step 3: Update `_genes_by_ontology_match_stage`**

Add `tree` param to `_genes_by_ontology_match_stage` signature. Add validation. In the Mode 2/3 branch (around line 1415), append tree filter to the level clause:

```python
    if tree is not None:
        level_clause += " AND t.tree = $tree"
        params["tree"] = tree
```

- [ ] **Step 4: Update `build_genes_by_ontology_detail` RETURN**

At line 1486, change:

```python
        "       t.id AS term_id, t.name AS term_name, t.level AS level"
```

to:

```python
        "       t.id AS term_id, t.name AS term_name, t.level AS level,\n"
        "       t.tree AS tree, t.tree_code AS tree_code"
```

Add `tree` param passthrough in all three `build_genes_by_ontology_*` functions.

- [ ] **Step 5: Update `build_genes_by_ontology_per_term` RETURN**

At line 1540, add tree columns:

```python
    "RETURN t.id AS term_id, t.name AS term_name, t.level AS level,\n"
    "       t.tree AS tree, t.tree_code AS tree_code,\n"
    "       t.level_is_best_effort IS NOT NULL AS best_effort,\n"
```

- [ ] **Step 6: Update MCP model**

Add to `GenesByOntologyResult` (line 1039):

```python
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
```

Add `tree` param to `genes_by_ontology` tool function.

- [ ] **Step 7: Update API sparse stripping**

In `multiomics_explorer/api/functions.py`, in `genes_by_ontology`, after the existing `level_is_best_effort` stripping (line 1379-1383), add:

```python
    for r in results:
        if r.get("tree") is None:
            r.pop("tree", None)
            r.pop("tree_code", None)
```

Pass `tree` to all builder calls.

- [ ] **Step 8: Run tests**

Run: `pytest tests/unit/test_query_builders.py -k "genes_by_ontology" -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py multiomics_explorer/api/functions.py multiomics_explorer/mcp_server/tools.py tests/unit/test_query_builders.py tests/unit/test_tool_correctness.py
git commit -m "feat: add tree filter and tree/tree_code output to genes_by_ontology"
```

---

### Task 7: `ontology_landscape` — add `tree` grouping

**Files:**
- Modify: `multiomics_explorer/kg/queries_lib.py:3723-3753`
- Modify: `multiomics_explorer/api/functions.py:2673-2848`
- Modify: `multiomics_explorer/mcp_server/tools.py:3363-3440`
- Test: `tests/unit/test_query_builders.py`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_query_builders.py`, add to `TestBuildOntologyLandscape`:

```python
    def test_returns_tree_columns_for_brite(self):
        cypher, _ = build_ontology_landscape(
            ontology="brite", organism_name="Test Org",
        )
        assert "t.tree" in cypher
        assert "t.tree_code" in cypher

    def test_groups_by_tree_for_brite(self):
        """BRITE landscape groups by (tree, tree_code, level)."""
        cypher, _ = build_ontology_landscape(
            ontology="brite", organism_name="Test Org",
        )
        # tree should appear in the WITH grouping clause
        assert "t.tree AS tree" in cypher
        assert "t.tree_code AS tree_code" in cypher

    def test_tree_filter(self):
        cypher, params = build_ontology_landscape(
            ontology="brite", organism_name="Test Org",
            tree="transporters",
        )
        assert "t.tree = $tree" in cypher
        assert params["tree"] == "transporters"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_builders.py::TestBuildOntologyLandscape::test_returns_tree_columns_for_brite -v`
Expected: FAIL

- [ ] **Step 3: Update `build_ontology_landscape`**

Add `tree` param to signature. Add validation. In the grouping/RETURN section (lines 3731-3747), add `t.tree AS tree, t.tree_code AS tree_code` to the `WITH` clause and RETURN:

Change the `WITH` at line 3731 from:

```python
        "WITH t.level AS level,\n"
```

to:

```python
        "WITH t.level AS level, t.tree AS tree, t.tree_code AS tree_code,\n"
```

Change the RETURN at line 3742 from:

```python
        "RETURN level, n_terms_with_genes,\n"
```

to:

```python
        "RETURN level, tree, tree_code, n_terms_with_genes,\n"
```

Add tree filter to the walk stage WHERE clause when `tree` is provided.

- [ ] **Step 4: Update MCP model**

Add to `OntologyLandscapeRow` (after line 3365):

```python
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
```

Add `tree` param to `ontology_landscape` tool function.

- [ ] **Step 5: Update API by_ontology**

In `multiomics_explorer/api/functions.py`, in `ontology_landscape`, update `by_ontology` construction (lines 2816-2826) to key by `(ont, tree)` for BRITE:

```python
    for r in all_rows:
        ont = r["ontology_type"]
        tree_val = r.get("tree")
        key = (ont, tree_val) if tree_val else (ont, None)
        if key not in by_ontology:
            by_ontology[key] = {
                "ontology_type": ont,
                "best_level": r["level"],
                "best_genome_coverage": r["genome_coverage"],
                "best_relevance_rank": r["relevance_rank"],
                "n_levels": 0,
            }
            if tree_val:
                by_ontology[key]["tree"] = tree_val
                by_ontology[key]["tree_code"] = r.get("tree_code")
        by_ontology[key]["n_levels"] += 1
```

Strip sparse tree fields from result rows:

```python
    for r in all_rows:
        if r.get("tree") is None:
            r.pop("tree", None)
            r.pop("tree_code", None)
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/test_query_builders.py::TestBuildOntologyLandscape -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add multiomics_explorer/kg/queries_lib.py multiomics_explorer/api/functions.py multiomics_explorer/mcp_server/tools.py tests/unit/test_query_builders.py
git commit -m "feat: add tree grouping and filter to ontology_landscape"
```

---

### Task 8: `pathway_enrichment` — add `tree` passthrough

**Files:**
- Modify: `multiomics_explorer/mcp_server/tools.py:28-60,3484-3508`
- Modify: `multiomics_explorer/api/functions.py:3061-3172`
- Test: `tests/unit/test_tool_correctness.py`

- [ ] **Step 1: Update MCP model**

Add to `PathwayEnrichmentResult` (after line 49):

```python
        tree: str | None = Field(default=None, description="BRITE tree name (sparse: BRITE only)")
        tree_code: str | None = Field(default=None, description="BRITE tree code (sparse: BRITE only)")
```

Add `tree` param to `pathway_enrichment` tool function (after `ontology` param):

```python
        tree: Annotated[str | None, Field(
            description="BRITE tree name filter. Only valid when ontology='brite'.",
        )] = None,
```

- [ ] **Step 2: Update API pathway_enrichment**

Add `tree` to signature. Add validation. Pass `tree` to internal `genes_by_ontology` call (line 3158):

```python
    gbo_result = genes_by_ontology(
        ontology=ontology,
        organism=inputs.organism_name,
        level=level,
        term_ids=term_ids,
        tree=tree,
        ...
    )
```

Strip sparse tree fields from enrichment result rows.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add multiomics_explorer/api/functions.py multiomics_explorer/mcp_server/tools.py tests/unit/test_tool_correctness.py
git commit -m "feat: add tree passthrough to pathway_enrichment"
```

---

### Task 9: Integration tests

**Files:**
- Modify: `tests/integration/test_cyver_queries.py`
- Modify: `tests/integration/test_param_edge_cases.py`

- [ ] **Step 1: Update `test_cyver_queries.py`**

In the `_BUILDERS` loop (lines 290-379), update `gene_ontology_terms_summary` and `gene_ontology_terms` entries to include `organism_name`:

```python
        (f"gene_ontology_terms_summary_{_ont_key}", build_gene_ontology_terms_summary,
         {"ontology": _ont_key, "locus_tags": _LOCUS,
          "organism_name": "Prochlorococcus marinus subsp. pastoris str. CCMP1986"}),
        (f"gene_ontology_terms_{_ont_key}", build_gene_ontology_terms,
         {"ontology": _ont_key, "locus_tags": _LOCUS,
          "organism_name": "Prochlorococcus marinus subsp. pastoris str. CCMP1986"}),
```

Add BRITE-specific entries with `tree` and `mode="rollup"`:

```python
    _BUILDERS.extend([
        ("gene_ontology_terms_brite_rollup", build_gene_ontology_terms,
         {"ontology": "brite", "locus_tags": _ALTERO_LOCUS,
          "organism_name": "Alteromonas macleodii MIT1002",
          "mode": "rollup", "level": 1}),
        ("gene_ontology_terms_brite_tree", build_gene_ontology_terms,
         {"ontology": "brite", "locus_tags": _ALTERO_LOCUS,
          "organism_name": "Alteromonas macleodii MIT1002",
          "tree": "transporters"}),
        ("search_ontology_brite_tree", build_search_ontology,
         {"ontology": "brite", "search_text": "transporter*",
          "tree": "transporters", "level": 1}),
    ])
```

(Define `_ALTERO_LOCUS = ["MIT1002_01547"]` near existing `_LOCUS`.)

- [ ] **Step 2: Update `test_param_edge_cases.py`**

Add validation error tests:

```python
def test_search_ontology_tree_with_non_brite(self, conn):
    with pytest.raises(ValueError, match="tree filter is only valid"):
        api.search_ontology("test", "go_bp", tree="transporters", conn=conn)

def test_gene_ontology_terms_rollup_without_level(self, conn):
    with pytest.raises(ValueError, match="level is required"):
        api.gene_ontology_terms(
            ["MIT1002_01547"], organism="MIT1002",
            mode="rollup", conn=conn,
        )

def test_gene_ontology_terms_tree_non_brite(self, conn):
    with pytest.raises(ValueError, match="tree filter is only valid"):
        api.gene_ontology_terms(
            ["MIT1002_01547"], organism="MIT1002",
            ontology="go_bp", tree="transporters", conn=conn,
        )

def test_genes_by_ontology_tree_non_brite(self, conn):
    with pytest.raises(ValueError, match="tree filter is only valid"):
        api.genes_by_ontology(
            ontology="go_bp", organism="MED4",
            level=2, tree="transporters", conn=conn,
        )
```

Update existing `test_gene_ontology_terms_invalid_ontology` to pass `organism`.

- [ ] **Step 3: Run integration tests**

Run: `pytest -m kg tests/integration/test_cyver_queries.py tests/integration/test_param_edge_cases.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/
git commit -m "test: add integration tests for level/tree params"
```

---

### Task 10: Regression fixtures

**Files:**
- Modify: `tests/evals/cases.yaml` (add new cases)
- Regenerate: `tests/regression/test_regression/` golden files

- [ ] **Step 1: Add new regression cases**

Add to `tests/evals/cases.yaml`:

```yaml
- id: search_ontology_brite_tree
  tool: search_ontology
  kwargs:
    ontology: brite
    search_text: "transporter*"
    tree: transporters
    level: 1

- id: gene_ontology_terms_brite_leaf
  tool: gene_ontology_terms
  kwargs:
    locus_tags: ["MIT1002_01547"]
    organism: "Alteromonas macleodii MIT1002"
    ontology: brite

- id: gene_ontology_terms_brite_rollup
  tool: gene_ontology_terms
  kwargs:
    locus_tags: ["MIT1002_01547"]
    organism: "Alteromonas macleodii MIT1002"
    ontology: brite
    mode: rollup
    level: 0
```

- [ ] **Step 2: Regenerate all fixtures**

Run: `pytest -m kg tests/regression/test_regression.py --force-regen -v`

This regenerates all golden files, including existing ones that now include new columns (`level`, `tree`, `tree_code`).

- [ ] **Step 3: Verify regression tests pass**

Run: `pytest -m kg tests/regression/test_regression.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/evals/cases.yaml tests/regression/
git commit -m "test: regenerate regression fixtures for level/tree consistency"
```

---

### Task 11: Documentation — YAML inputs + enrichment.md + example script

**Files:**
- Modify: `multiomics_explorer/inputs/tools/search_ontology.yaml`
- Modify: `multiomics_explorer/inputs/tools/gene_ontology_terms.yaml`
- Modify: `multiomics_explorer/inputs/tools/genes_by_ontology.yaml`
- Modify: `multiomics_explorer/inputs/tools/ontology_landscape.yaml`
- Modify: `multiomics_explorer/inputs/tools/pathway_enrichment.yaml`
- Modify: `multiomics_explorer/inputs/tools/list_filter_values.yaml`
- Modify: `multiomics_explorer/analysis/enrichment.md`
- Modify: `multiomics_explorer/skills/.../references/analysis/enrichment.md`
- Modify: `examples/pathway_enrichment.py`

- [ ] **Step 1: Update tool YAMLs**

For each YAML, add new params to the examples and update mistakes/tips:

- `search_ontology.yaml`: Add `level` and `tree` params. Add example: "Search BRITE transporters at level 1".
- `gene_ontology_terms.yaml`: Add `organism`, `mode`, `level`, `tree` params. Add rollup example. Update mistakes to mention `mode="rollup"` requires `level`.
- `genes_by_ontology.yaml`: Add `tree` param. Add BRITE example with tree filter.
- `ontology_landscape.yaml`: Add `tree` param. Note per-tree BRITE breakdown.
- `pathway_enrichment.yaml`: Add `tree` param. Add BRITE tree-scoped enrichment example.
- `list_filter_values.yaml`: Add `brite_tree` filter type.

- [ ] **Step 2: Update enrichment.md**

In `multiomics_explorer/analysis/enrichment.md`, add a section on BRITE enrichment:

- Document `tree` parameter for scoping enrichment
- Add worked example: landscape → pick tree → enrichment
- Note that all-BRITE enrichment without tree scoping is dominated by enzymes
- Add to ontology/level selection narrative

Copy the same changes to `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/enrichment.md`.

- [ ] **Step 3: Add `brite` scenario to example script**

In `examples/pathway_enrichment.py`, add a `brite` scenario function:

```python
def scenario_brite(conn, organism, experiment_ids):
    """BRITE tree-scoped enrichment."""
    # Discover trees
    trees = api.list_filter_values("brite_tree", conn=conn)
    print("Available BRITE trees:")
    for t in trees["results"]:
        print(f"  {t['value']} ({t['tree_code']}): {t['count']} terms")

    # Pick transporters, scout level
    landscape = api.ontology_landscape(
        organism=organism, ontology="brite", tree="transporters", conn=conn,
    )
    print("\nTransporter landscape:")
    for row in landscape["results"]:
        print(f"  level {row['level']}: {row['n_terms_with_genes']} terms, "
              f"{row['n_genes_at_level']} genes")

    # Enrichment at level 1
    result = api.pathway_enrichment(
        organism=organism, experiment_ids=experiment_ids,
        ontology="brite", tree="transporters", level=1,
        conn=conn,
    )
    print(f"\nEnriched transporter categories: {len(result.get('results', []))}")
    for row in result.get("results", [])[:5]:
        print(f"  {row['term_name']}: p_adjust={row['p_adjust']:.4f}")
```

Register in the CLI dispatch.

- [ ] **Step 4: Regenerate skill reference docs**

Run: `uv run python scripts/build_about_content.py`

- [ ] **Step 5: Update integration test for example script**

In `tests/integration/test_examples.py`, add `"brite"` to the parametrized scenarios.

- [ ] **Step 6: Commit**

```bash
git add multiomics_explorer/inputs/tools/ multiomics_explorer/analysis/enrichment.md multiomics_explorer/skills/ examples/pathway_enrichment.py tests/integration/test_examples.py
git commit -m "docs: update YAMLs, enrichment.md, and example script for level/tree"
```

---

### Task 12: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update tool table**

Update the `gene_ontology_terms` description to mention `mode`, `organism`, `level`. Update `list_filter_values` to mention `brite_tree`. Add note about `tree` filter on ontology tools.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for ontology level/tree consistency"
```

---

### Task 13: Final integration smoke test

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/unit/ -v`
Expected: All PASS

- [ ] **Step 2: Run integration tests**

Run: `pytest -m kg -v`
Expected: All PASS

- [ ] **Step 3: Restart MCP and smoke test**

Run `/mcp` to restart the MCP server, then test:

```python
# search_ontology with level + tree
search_ontology(ontology="brite", search_text="transporter*", level=1, tree="transporters")

# gene_ontology_terms rollup mode
gene_ontology_terms(locus_tags=["MIT1002_01547"], organism="MIT1002", ontology="go_bp", mode="rollup", level=2)

# gene_ontology_terms BRITE with tree
gene_ontology_terms(locus_tags=["MIT1002_01547"], organism="MIT1002", ontology="brite", tree="transporters")

# list_filter_values brite_tree
list_filter_values(filter_type="brite_tree")

# ontology_landscape BRITE per-tree
ontology_landscape(organism="MIT1002", ontology="brite")
```

- [ ] **Step 4: Final commit if any fixes needed**
