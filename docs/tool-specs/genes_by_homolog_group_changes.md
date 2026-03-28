# genes_by_homolog_group: What to Change

## Executive Summary

The **UPDATED spec** requires significant changes to the tool signature, Cypher queries, return envelope, and supporting query builders. The main shift is from a **single-organism (string) filter** to **multi-organism (list) filter** with **sophisticated not_found/not_matched diagnostics**.

---

## 1. QUERY BUILDER CHANGES

### File: `multiomics_explorer/kg/queries_lib.py`

#### 1.1 Function: `build_genes_by_homolog_group_summary`

**CURRENT signature:**
```python
def build_genes_by_homolog_group_summary(
    *,
    group_ids: list[str],
    organism: str | None = None,
) -> tuple[str, dict]:
```

**UPDATED signature:**
```python
def build_genes_by_homolog_group_summary(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
) -> tuple[str, dict]:
```

**Changes:**
- Parameter name: `organism` → `organisms`
- Parameter type: `str | None` → `list[str] | None`
- Return keys CHANGE (see below)

**CURRENT Cypher pattern:**
```cypher
WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
```

**UPDATED Cypher pattern (organisms is a LIST with OR semantics):**
```cypher
WHERE ($organisms IS NULL OR ANY(org_input IN $organisms
       WHERE ALL(word IN split(toLower(org_input), ' ')
             WHERE toLower(g.organism_strain) CONTAINS word)))
```

**CURRENT return keys:**
```
total_matching, total_genes, not_found, by_organism, by_category, by_group
```

**UPDATED return keys:**
```
total_matching, total_genes, not_found_groups, not_matched_groups,
by_organism, by_category, by_group
```

**Key logic changes:**
- `not_found` → `not_found_groups` (groups with no OrthologGroup node)
- NEW: `not_matched_groups` (groups exist but have 0 member genes after organism filter)
- Cypher must distinguish between these two cases using CASE/WHEN logic

---

#### 1.2 NEW Function: `build_genes_by_homolog_group_diagnostics`

**This function does NOT exist in current implementation. Must be added.**

**Signature:**
```python
def build_genes_by_homolog_group_diagnostics(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
) -> tuple[str, dict]:
    """Validate organisms against KG + result set.

    RETURN keys: not_found_organisms, not_matched_organisms.
    Returns empty lists when organisms is None.
    """
```

**Purpose:**
- Detects `not_found_organisms`: organisms matching zero Gene nodes in KG
- Detects `not_matched_organisms`: organisms exist in KG but have zero genes in the requested groups
- Only runs when `organisms is not None`

**Cypher logic (from spec):**
```cypher
WITH $organisms AS org_inputs
UNWIND CASE WHEN org_inputs IS NULL THEN [null]
       ELSE org_inputs END AS org_input
// Check existence in KG (any Gene node matching this organism)
OPTIONAL MATCH (g_any:Gene)
WHERE org_input IS NOT NULL
  AND ALL(word IN split(toLower(org_input), ' ')
          WHERE toLower(g_any.organism_strain) CONTAINS word)
WITH org_input, count(g_any) AS kg_count
// For those that exist, check if they match any group member
OPTIONAL MATCH (g:Gene)-[:Gene_in_ortholog_group]->(og:OrthologGroup)
WHERE org_input IS NOT NULL AND kg_count > 0
  AND og.id IN $group_ids
  AND ALL(word IN split(toLower(org_input), ' ')
          WHERE toLower(g.organism_strain) CONTAINS word)
WITH org_input, kg_count, count(g) AS matched_count
WITH collect(CASE WHEN org_input IS NOT NULL AND kg_count = 0
             THEN org_input END) AS nf_raw,
     collect(CASE WHEN org_input IS NOT NULL AND kg_count > 0
                   AND matched_count = 0 THEN org_input END) AS nm_raw
RETURN [x IN nf_raw WHERE x IS NOT NULL] AS not_found_organisms,
       [x IN nm_raw WHERE x IS NOT NULL] AS not_matched_organisms
```

---

#### 1.3 Function: `build_genes_by_homolog_group`

**CURRENT signature:**
```python
def build_genes_by_homolog_group(
    *,
    group_ids: list[str],
    organism: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
```

**UPDATED signature:**
```python
def build_genes_by_homolog_group(
    *,
    group_ids: list[str],
    organisms: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
```

**Changes:**
- Parameter name: `organism` → `organisms`
- Parameter type: `str | None` → `list[str] | None`

**CURRENT Cypher WHERE clause:**
```cypher
WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
```

**UPDATED Cypher WHERE clause:**
```cypher
WHERE ($organisms IS NULL OR ANY(org_input IN $organisms
       WHERE ALL(word IN split(toLower(org_input), ' ')
             WHERE toLower(g.organism_strain) CONTAINS word)))
```

**Details:**
- Single string `$organism` becomes a list `$organisms`
- Filter semantics: from "match all words in a single organism string" to "match if gene belongs to ANY of the listed organisms (OR semantics)"
- Allows cross-organism comparisons (pass ["MED4", "AS9601"])

---

### Summary of Cypher Builder Changes

| Builder | Current | Updated | Key Changes |
|---------|---------|---------|------------|
| `build_genes_by_homolog_group_summary` | `organism: str\|None` | `organisms: list[str]\|None` | OR semantics; returns `not_found_groups`, `not_matched_groups` |
| `build_genes_by_homolog_group_diagnostics` | NOT EXIST | NEW | Validates organisms against KG + groups |
| `build_genes_by_homolog_group` | `organism: str\|None` | `organisms: list[str]\|None` | OR semantics in WHERE clause |

---

## 2. API FUNCTION CHANGES

### File: `multiomics_explorer/api/functions.py`

#### Current signature:
```python
def genes_by_homolog_group(
    group_ids: list[str],
    organism: str | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
```

#### Updated signature:
```python
def genes_by_homolog_group(
    group_ids: list[str],
    organisms: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
```

#### Changes to function body:

**CURRENT query pattern (2 queries):**
1. Summary query
2. Detail query (skip if limit=0)

**UPDATED query pattern (3 queries):**
1. Summary query → `not_found_groups`, `not_matched_groups`
2. Diagnostics query (SKIP if `organisms is None`) → `not_found_organisms`, `not_matched_organisms`
3. Detail query (skip if limit=0)

**Return dict changes:**

**CURRENT keys:**
```python
{
    "total_matching": ...,
    "total_genes": ...,
    "by_organism": [...],
    "by_category": [...],
    "by_group": [...],
    "not_found": [...],
    "returned": ...,
    "truncated": ...,
    "results": [...]
}
```

**UPDATED keys:**
```python
{
    "total_matching": ...,
    "total_genes": ...,
    "by_organism": [...],
    "by_category": [...],
    "by_group": [...],
    "not_found_groups": [...],
    "not_matched_groups": [...],
    "not_found_organisms": [...],
    "not_matched_organisms": [...],
    "returned": ...,
    "truncated": ...,
    "results": [...]
}
```

**Logic changes:**
- Rename `not_found` → `not_found_groups`
- Add `not_matched_groups` from summary query
- Add `not_found_organisms`, `not_matched_organisms` from diagnostics query (empty lists if organisms is None)
- Handle frequency list → dict conversion for all breakdown fields

---

## 3. MCP WRAPPER CHANGES

### File: `multiomics_explorer/mcp_server/tools.py`

#### 3.1 Pydantic models (SAME - no changes needed)

The result models remain the same:
- `GenesByHomologGroupResult` — same fields ✓
- `HomologGroupOrganismBreakdown` — same ✓
- `HomologGroupCategoryBreakdown` — same ✓
- `HomologGroupGroupBreakdown` — same ✓

#### 3.2 Response model (UPDATED)

**CURRENT:**
```python
class GenesByHomologGroupResponse(BaseModel):
    total_matching: int
    total_genes: int
    by_organism: list[HomologGroupOrganismBreakdown]
    by_category: list[HomologGroupCategoryBreakdown]
    by_group: list[HomologGroupGroupBreakdown]
    not_found: list[str] = Field(default_factory=list)
    returned: int
    truncated: bool
    results: list[GenesByHomologGroupResult] = Field(default_factory=list)
```

**UPDATED:**
```python
class GenesByHomologGroupResponse(BaseModel):
    total_matching: int
    total_genes: int
    by_organism: list[HomologGroupOrganismBreakdown]
    by_category: list[HomologGroupCategoryBreakdown]
    by_group: list[HomologGroupGroupBreakdown]
    not_found_groups: list[str] = Field(default_factory=list)
    not_matched_groups: list[str] = Field(default_factory=list)
    not_found_organisms: list[str] = Field(default_factory=list)
    not_matched_organisms: list[str] = Field(default_factory=list)
    returned: int
    truncated: bool
    results: list[GenesByHomologGroupResult] = Field(default_factory=list)
```

#### 3.3 Tool wrapper function (UPDATED)

**CURRENT parameter:**
```python
organism: Annotated[str | None, Field(
    description="Filter by organism (case-insensitive substring). "
    "E.g. 'MED4', 'Alteromonas'. "
    "Use list_organisms to see valid values.",
)] = None,
```

**UPDATED parameter:**
```python
organisms: Annotated[list[str] | None, Field(
    description="Filter by organisms (case-insensitive substring, each entry "
    "matched independently). E.g. ['MED4', 'AS9601']. "
    "Use list_organisms to see valid values.",
)] = None,
```

**Changes to wrapper implementation:**
- Call signature: `api.genes_by_homolog_group(group_ids, organism=organism, ...)` → `api.genes_by_homolog_group(group_ids, organisms=organisms, ...)`
- Response envelope construction: add lines for new fields
  ```python
  not_found_groups=data["not_found_groups"],
  not_matched_groups=data["not_matched_groups"],
  not_found_organisms=data["not_found_organisms"],
  not_matched_organisms=data["not_matched_organisms"],
  ```

---

## 4. EXPORT CHANGES

### File: `multiomics_explorer/api/__init__.py`

**Current:**
```python
from .functions import (
    ...
    genes_by_homolog_group,
    ...
)

__all__ = [
    ...
    "genes_by_homolog_group",
    ...
]
```

**Updated:** SAME — no changes needed ✓

### File: `multiomics_explorer/__init__.py`

**Current:**
```python
from .api import (
    ...
    genes_by_homolog_group,
    ...
)

__all__ = [
    ...
    "genes_by_homolog_group",
    ...
]
```

**Updated:** SAME — no changes needed ✓

---

## 5. TEST CHANGES

### File: `tests/unit/test_query_builders.py`

#### TestBuildGenesByHomologGroup

**CURRENT test:**
```python
def test_organism_filter_clause(self):
    cypher, params = build_genes_by_homolog_group(
        group_ids=["cyanorak:CK_1"], organism="MED4")
    assert "$organism IS NULL" in cypher
    assert params["organism"] == "MED4"
```

**UPDATED test:**
```python
def test_organisms_filter_clause(self):
    cypher, params = build_genes_by_homolog_group(
        group_ids=["cyanorak:CK_1"], organisms=["MED4"])
    assert "$organisms IS NULL" in cypher
    assert params["organisms"] == ["MED4"]

def test_organisms_multiple_values(self):
    cypher, params = build_genes_by_homolog_group(
        group_ids=["cyanorak:CK_1"], organisms=["MED4", "AS9601"])
    assert "$organisms" in params
    assert len(params["organisms"]) == 2

def test_organisms_none_filter(self):
    cypher, params = build_genes_by_homolog_group(
        group_ids=["cyanorak:CK_1"], organisms=None)
    assert params["organisms"] is None
```

#### TestBuildGenesByHomologGroupSummary

**ADD test:**
```python
def test_organisms_filter(self):
    cypher, params = build_genes_by_homolog_group_summary(
        group_ids=["cyanorak:CK_1"], organisms=["MED4"])
    assert "$organisms IS NULL" in cypher
    assert params["organisms"] == ["MED4"]

def test_not_matched_groups_detection(self):
    """Verify query detects groups with 0 members after organism filter."""
    cypher, _ = build_genes_by_homolog_group_summary(
        group_ids=["cyanorak:CK_1"])
    assert "not_matched" in cypher
```

#### NEW test class: TestBuildGenesByHomologGroupDiagnostics

```python
class TestBuildGenesByHomologGroupDiagnostics:
    """Tests for build_genes_by_homolog_group_diagnostics."""

    def test_organisms_none_returns_empty(self):
        cypher, params = build_genes_by_homolog_group_diagnostics(
            group_ids=["cyanorak:CK_1"], organisms=None)
        # Should return Cypher that evaluates to empty lists
        assert "not_found_organisms" in cypher
        assert "not_matched_organisms" in cypher
        assert params["organisms"] is None

    def test_organisms_list_in_params(self):
        cypher, params = build_genes_by_homolog_group_diagnostics(
            group_ids=["cyanorak:CK_1"], organisms=["MED4"])
        assert params["organisms"] == ["MED4"]
        assert params["group_ids"] == ["cyanorak:CK_1"]

    def test_returns_expected_keys(self):
        cypher, _ = build_genes_by_homolog_group_diagnostics(
            group_ids=["cyanorak:CK_1"], organisms=["MED4"])
        assert "not_found_organisms" in cypher
        assert "not_matched_organisms" in cypher
```

---

### File: `tests/unit/test_api_functions.py`

#### TestGenesByHomologGroup

**CURRENT test:**
```python
def test_passes_params(self, mock_conn):
    mock_conn.execute_query.side_effect = [
        [{"total_matching": 0, "total_genes": 0,
          "by_organism": [], "by_category": [], "by_group": [],
          "not_found": []}],
    ]
    api.genes_by_homolog_group(
        ["cyanorak:CK_1"], organism="MED4", summary=True, conn=mock_conn)
```

**UPDATED test:**
```python
def test_passes_organisms_param(self, mock_conn):
    mock_conn.execute_query.side_effect = [
        [{"total_matching": 0, "total_genes": 0,
          "by_organism": [], "by_category": [], "by_group": [],
          "not_found_groups": [], "not_matched_groups": []}],
    ]
    api.genes_by_homolog_group(
        ["cyanorak:CK_1"], organisms=["MED4"], summary=True, conn=mock_conn)
```

**ADD tests:**
```python
def test_not_found_and_not_matched_groups(self, mock_conn):
    """Test that summary returns not_found_groups and not_matched_groups."""
    mock_conn.execute_query.side_effect = [
        [{
            "total_matching": 0, "total_genes": 0,
            "by_organism": [], "by_category": [], "by_group": [],
            "not_found_groups": ["FAKE_ID"],
            "not_matched_groups": ["real_id_no_members"]
        }],
    ]
    result = api.genes_by_homolog_group(
        ["FAKE_ID"], summary=True, conn=mock_conn)
    assert result["not_found_groups"] == ["FAKE_ID"]
    assert result["not_matched_groups"] == ["real_id_no_members"]

def test_not_found_and_not_matched_organisms(self, mock_conn):
    """Test that organisms diagnostics are included in result."""
    mock_conn.execute_query.side_effect = [
        [{
            "total_matching": 0, "total_genes": 0,
            "by_organism": [], "by_category": [], "by_group": [],
            "not_found_groups": [], "not_matched_groups": []
        }],
        [{
            "not_found_organisms": ["NONEXISTENT"],
            "not_matched_organisms": []
        }],
    ]
    result = api.genes_by_homolog_group(
        ["cyanorak:CK_1"], organisms=["NONEXISTENT"], conn=mock_conn)
    assert result["not_found_organisms"] == ["NONEXISTENT"]
    assert result["not_matched_organisms"] == []

def test_organisms_none_skips_diagnostics(self, mock_conn):
    """When organisms is None, diagnostics query is skipped."""
    mock_conn.execute_query.side_effect = [
        [{
            "total_matching": 1, "total_genes": 1,
            "by_organism": [{"item": "Prochlorococcus MED4", "count": 1}],
            "by_category": [], "by_group": [],
            "not_found_groups": [], "not_matched_groups": []
        }],
        [{"locus_tag": "PMM0001", ...}],
    ]
    result = api.genes_by_homolog_group(
        ["cyanorak:CK_1"], organisms=None, conn=mock_conn)
    # Only 2 queries (summary + detail), not 3
    assert mock_conn.execute_query.call_count == 2
    assert result["not_found_organisms"] == []
    assert result["not_matched_organisms"] == []
```

---

### File: `tests/unit/test_tool_wrappers.py`

#### TestGenesByHomologGroupWrapper

**CURRENT parameters test:**
```python
async def test_params_forwarded(self, tool_fns, mock_ctx):
    with patch(
        "multiomics_explorer.api.functions.genes_by_homolog_group",
        return_value=self._SAMPLE_API_RETURN,
    ) as mock_api:
        await tool_fns["genes_by_homolog_group"](
            mock_ctx, group_ids=["cyanorak:CK_1"],
            organism="MED4", summary=True, verbose=True, limit=10,
        )
    call_kwargs = mock_api.call_args
    assert call_kwargs.kwargs["organism"] == "MED4"
```

**UPDATED:**
```python
async def test_params_forwarded(self, tool_fns, mock_ctx):
    with patch(
        "multiomics_explorer.api.functions.genes_by_homolog_group",
        return_value=self._SAMPLE_API_RETURN,
    ) as mock_api:
        await tool_fns["genes_by_homolog_group"](
            mock_ctx, group_ids=["cyanorak:CK_1"],
            organisms=["MED4"], summary=True, verbose=True, limit=10,
        )
    call_kwargs = mock_api.call_args
    assert call_kwargs.kwargs["organisms"] == ["MED4"]
```

**UPDATE sample return:**
```python
_SAMPLE_API_RETURN = {
    "total_matching": 9,
    "total_genes": 9,
    "by_organism": [...],
    "by_category": [...],
    "by_group": [...],
    "not_found_groups": [],        # ADD
    "not_matched_groups": [],       # ADD
    "not_found_organisms": [],      # ADD
    "not_matched_organisms": [],    # ADD
    "returned": 2,
    "truncated": True,
    "results": [...],
}
```

**ADD tests:**
```python
@pytest.mark.asyncio
async def test_not_found_groups(self, tool_fns, mock_ctx):
    sample_with_not_found = {
        **self._SAMPLE_API_RETURN,
        "not_found_groups": ["FAKE_GROUP"],
    }
    with patch(
        "multiomics_explorer.api.functions.genes_by_homolog_group",
        return_value=sample_with_not_found,
    ):
        result = await tool_fns["genes_by_homolog_group"](
            mock_ctx, group_ids=["FAKE_GROUP"],
        )
    assert result.not_found_groups == ["FAKE_GROUP"]
    assert result.not_matched_groups == []

@pytest.mark.asyncio
async def test_not_matched_groups(self, tool_fns, mock_ctx):
    sample = {
        **self._SAMPLE_API_RETURN,
        "not_matched_groups": ["real_group"],
    }
    with patch(
        "multiomics_explorer.api.functions.genes_by_homolog_group",
        return_value=sample,
    ):
        result = await tool_fns["genes_by_homolog_group"](
            mock_ctx, group_ids=["real_group"],
        )
    assert result.not_matched_groups == ["real_group"]

@pytest.mark.asyncio
async def test_not_found_organisms(self, tool_fns, mock_ctx):
    sample = {
        **self._SAMPLE_API_RETURN,
        "not_found_organisms": ["NONEXISTENT_ORG"],
    }
    with patch(
        "multiomics_explorer.api.functions.genes_by_homolog_group",
        return_value=sample,
    ):
        result = await tool_fns["genes_by_homolog_group"](
            mock_ctx, group_ids=["cyanorak:CK_1"],
            organisms=["NONEXISTENT_ORG"],
        )
    assert result.not_found_organisms == ["NONEXISTENT_ORG"]

@pytest.mark.asyncio
async def test_not_matched_organisms(self, tool_fns, mock_ctx):
    sample = {
        **self._SAMPLE_API_RETURN,
        "not_matched_organisms": ["real_organism_not_in_group"],
    }
    with patch(
        "multiomics_explorer.api.functions.genes_by_homolog_group",
        return_value=sample,
    ):
        result = await tool_fns["genes_by_homolog_group"](
            mock_ctx, group_ids=["cyanorak:CK_1"],
            organisms=["real_organism_not_in_group"],
        )
    assert result.not_matched_organisms == ["real_organism_not_in_group"]
```

---

### File: `tests/regression/test_regression.py`

**CURRENT:**
```python
TOOL_BUILDERS = {
    ...
    "genes_by_homolog_group": build_genes_by_homolog_group,
    ...
}
```

**Updated:** SAME (no change to TOOL_BUILDERS mapping) ✓

**Baseline fixtures to update/add:**
- `baseline_fixtures/genes_by_homolog_group_basic.yml` — rename keys in expected output
- `baseline_fixtures/genes_by_homolog_group_organism_filter.yml` — rename keys, use organisms list
- `baseline_fixtures/genes_by_homolog_group_verbose.yml` — rename keys

---

### File: `tests/evals/cases.yaml`

**CURRENT cases:**
```yaml
- id: genes_by_homolog_group_basic
  tool: genes_by_homolog_group
  desc: Single group to member genes
  params:
    group_ids: ["cyanorak:CK_00000570"]
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain, gene_category, group_id]

- id: genes_by_homolog_group_organism_filter
  tool: genes_by_homolog_group
  desc: Group members filtered by organism
  params:
    group_ids: ["cyanorak:CK_00000570"]
    organism: "MED4"
  expect:
    min_rows: 1
    columns: [locus_tag, organism_strain, group_id]

- id: genes_by_homolog_group_verbose
  tool: genes_by_homolog_group
  desc: Verbose mode includes gene_summary and group context
  params:
    group_ids: ["cyanorak:CK_00000570"]
    verbose: true
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain, gene_category, group_id, gene_summary, function_description, consensus_product, source]
```

**UPDATED cases:**
```yaml
- id: genes_by_homolog_group_basic
  tool: genes_by_homolog_group
  desc: Single group to member genes
  params:
    group_ids: ["cyanorak:CK_00000570"]
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain, gene_category, group_id]

- id: genes_by_homolog_group_organism_filter
  tool: genes_by_homolog_group
  desc: Group members filtered by organisms (list)
  params:
    group_ids: ["cyanorak:CK_00000570"]
    organisms: ["MED4"]
  expect:
    min_rows: 1
    columns: [locus_tag, organism_strain, group_id]

- id: genes_by_homolog_group_multi_organism
  tool: genes_by_homolog_group
  desc: Filter to multiple organisms (cross-organism)
  params:
    group_ids: ["cyanorak:CK_00000570"]
    organisms: ["MED4", "AS9601"]
  expect:
    min_rows: 1
    columns: [locus_tag, organism_strain, group_id]

- id: genes_by_homolog_group_verbose
  tool: genes_by_homolog_group
  desc: Verbose mode includes gene_summary and group context
  params:
    group_ids: ["cyanorak:CK_00000570"]
    verbose: true
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain, gene_category, group_id, gene_summary, function_description, consensus_product, source]

- id: genes_by_homolog_group_multi
  tool: genes_by_homolog_group
  desc: Multiple groups
  params:
    group_ids: ["cyanorak:CK_00000570", "eggnog:COG0592@2"]
  expect:
    min_rows: 2
    columns: [locus_tag, organism_strain, group_id]
```

---

## 6. HELPER FUNCTION CHANGES

### File: `multiomics_explorer/api/functions.py`

If there's a `_apoc_freq_to_dict` or similar helper used for reshaping frequency lists from Cypher, it should **remain unchanged** — it's already used by other tools.

---

## 7. SUMMARY TABLE

| Component | Current | Updated | Severity |
|-----------|---------|---------|----------|
| **Query Builders** |
| `build_genes_by_homolog_group_summary` | `organism: str\|None` | `organisms: list[str]\|None` | **HIGH** |
| — | Returns `not_found` | Returns `not_found_groups`, `not_matched_groups` | **HIGH** |
| `build_genes_by_homolog_group_diagnostics` | NOT EXIST | NEW | **HIGH** |
| `build_genes_by_homolog_group` | `organism: str\|None` | `organisms: list[str]\|None` | **HIGH** |
| **API Function** |
| `genes_by_homolog_group` | 2 queries | 3 queries (when organisms not None) | **HIGH** |
| — | Runs summary + detail | Runs summary + diagnostics + detail | **HIGH** |
| — | Returns `not_found` | Returns `not_found_groups`, `not_matched_groups`, `not_found_organisms`, `not_matched_organisms` | **HIGH** |
| **MCP Wrapper** |
| Parameter name | `organism` | `organisms` | **HIGH** |
| Response fields | Has `not_found` | Has 4 not_* fields | **HIGH** |
| **Pydantic Models** |
| `GenesByHomologGroupResponse` | `not_found: list[str]` | `not_found_groups`, `not_matched_groups`, `not_found_organisms`, `not_matched_organisms` | **HIGH** |
| **Tests** |
| Unit tests | Parameter name `organism` | Parameter name `organisms` | **HIGH** |
| — | Test `not_found` | Test all 4 not_* variants | **HIGH** |
| — | No diagnostics tests | Add TestBuildGenesByHomologGroupDiagnostics | **MEDIUM** |
| Eval cases | `organism: "MED4"` | `organisms: ["MED4"]` | **MEDIUM** |
| — | 3 cases | Add 2 new cases (multi-organism, multiple groups) | **MEDIUM** |
| **Exports** |
| `api/__init__.py` | Already exported | No change needed | ✓ |
| `__init__.py` | Already exported | No change needed | ✓ |

---

## 8. IMPLEMENTATION CHECKLIST

- [ ] Update `build_genes_by_homolog_group_summary()` in `kg/queries_lib.py`
  - [ ] Change parameter: `organism → organisms` with type `str|None → list[str]|None`
  - [ ] Update WHERE clause for OR semantics
  - [ ] Change return keys: `not_found → not_found_groups, not_matched_groups`
  - [ ] Update Cypher CASE/WHEN logic to distinguish not_found vs not_matched

- [ ] Create `build_genes_by_homolog_group_diagnostics()` in `kg/queries_lib.py`
  - [ ] Signature with `group_ids`, `organisms` params
  - [ ] Implement full Cypher from spec
  - [ ] Return empty lists when organisms is None

- [ ] Update `build_genes_by_homolog_group()` in `kg/queries_lib.py`
  - [ ] Change parameter: `organism → organisms` with type `str|None → list[str]|None`
  - [ ] Update WHERE clause for OR semantics

- [ ] Update `genes_by_homolog_group()` API function in `api/functions.py`
  - [ ] Change parameter name: `organism → organisms`
  - [ ] Add call to diagnostics query builder (when organisms not None)
  - [ ] Update return dict keys (4 not_* fields)
  - [ ] Process diagnostics result

- [ ] Update Pydantic response model in `mcp_server/tools.py`
  - [ ] Update `GenesByHomologGroupResponse` fields: replace `not_found` with 4 fields

- [ ] Update MCP wrapper in `mcp_server/tools.py`
  - [ ] Change tool parameter: `organism → organisms`
  - [ ] Update Field description
  - [ ] Update envelope construction (add 4 new fields)
  - [ ] Update API call signature

- [ ] Update tests in `test_query_builders.py`
  - [ ] Rename `test_organism_filter_clause` → `test_organisms_filter_clause`
  - [ ] Update all organisms parameter usage
  - [ ] Add `test_organisms_none_filter()`, `test_organisms_multiple_values()`
  - [ ] Add `test_not_matched_groups_detection()`
  - [ ] Create `TestBuildGenesByHomologGroupDiagnostics` with 3 tests

- [ ] Update tests in `test_api_functions.py`
  - [ ] Update `test_passes_params()` → organisms param
  - [ ] Add `test_not_found_and_not_matched_groups()`
  - [ ] Add `test_not_found_and_not_matched_organisms()`
  - [ ] Add `test_organisms_none_skips_diagnostics()`

- [ ] Update tests in `test_tool_wrappers.py`
  - [ ] Update `_SAMPLE_API_RETURN` with 4 new fields
  - [ ] Update `test_params_forwarded()` → organisms param
  - [ ] Add `test_not_found_groups()`
  - [ ] Add `test_not_matched_groups()`
  - [ ] Add `test_not_found_organisms()`
  - [ ] Add `test_not_matched_organisms()`

- [ ] Update eval cases in `tests/evals/cases.yaml`
  - [ ] Update organism_filter case → organisms list
  - [ ] Add genes_by_homolog_group_multi_organism case
  - [ ] Add genes_by_homolog_group_multi case

- [ ] Update regression test baselines
  - [ ] genes_by_homolog_group_basic.yml
  - [ ] genes_by_homolog_group_organism_filter.yml
  - [ ] genes_by_homolog_group_verbose.yml

---

## 9. BREAKING CHANGES

- **Parameter rename:** `organism` → `organisms` (API + MCP)
- **Parameter type change:** `str|None` → `list[str]|None`
- **Return envelope keys:** `not_found` → `not_found_groups` (old key removed)
- **New return keys:** `not_matched_groups`, `not_found_organisms`, `not_matched_organisms`
- **Semantics change:** single organism string (fuzzy matching) → list of organisms (OR logic)

This is a **MAJOR** version bump for the tool if exposed as a public API.

