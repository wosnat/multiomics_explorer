# Tool spec: search_ontology

## Purpose

Browse ontology terms by text search (Lucene syntax). Returns term IDs
for use with `genes_by_ontology`. Annotation tool in the Phase 2 ontology
triplet: `search_ontology` → `genes_by_ontology` → `gene_ontology_terms`.

Not a rename — same name, v3 upgrade.

## Out of Scope

- **Finding genes** — use `genes_by_ontology` with term IDs from this tool
- **Gene-level ontology details** — use `gene_ontology_terms`
- **Hierarchy browsing** — this tool does flat fulltext search; hierarchy
  expansion is `genes_by_ontology`'s job
- **Organism coverage per term** — direct-edge counts are misleading for
  hierarchical ontologies; use `genes_by_ontology` for organism breakdown

## Status / Prerequisites

- [x] KG spec: not needed — existing fulltext indexes suffice
- [x] Scope reviewed with user
- [x] Result-size controls decided (summary + limit, no verbose)
- [x] Ready for Phase 2 (build)

## Use cases

- **Term discovery** — "what GO biological process terms match
  'replication'?" → get term IDs for `genes_by_ontology`
- **Ontology browsing** — explore what terms exist in a given ontology
  (KEGG, EC, Pfam, etc.)
- **Chain:** `search_ontology` → `genes_by_ontology` → `gene_overview`

## KG dependencies

**Existing (no changes needed):**
- Fulltext indexes per ontology type (in `ONTOLOGY_CONFIG`)
- Node labels: BiologicalProcess, MolecularFunction, CellularComponent,
  EcNumber, KeggTerm, CogFunctionalCategory, CyanorakRole, TigrRole,
  Pfam, PfamClan

---

## Tool Signature

```python
@mcp.tool(
    tags={"ontology"},
    annotations={"readOnlyHint": True},
)
async def search_ontology(
    ctx: Context,
    search_text: Annotated[str, Field(
        description="Search query (Lucene syntax). "
        "E.g. 'replication', 'oxido*', 'transport AND membrane'.",
    )],
    ontology: Annotated[str, Field(
        description="Ontology to search: 'go_bp', 'go_mf', 'go_cc', "
        "'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam'.",
    )],
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> SearchOntologyResponse:
    """Browse ontology terms by text search (fuzzy, Lucene syntax).

    Returns term IDs for use with genes_by_ontology. Supports fuzzy (~),
    wildcards (*), exact phrases ("..."), boolean (AND, OR).
    """
```

**Return envelope:** `total_entries, total_matching, score_max, score_median, returned, truncated, results`

**Per-result columns (3):** `id`, `name`, `score`

## Result-size controls

Frequently large (71 results for "metabolism" in KEGG) → summary + limit.
No verbose — all per-result fields are lightweight.

### Summary fields (always present)

| Field | Type | Description |
|---|---|---|
| `total_entries` | int | Total terms in this ontology (label count, cheap) |
| `total_matching` | int | Terms matching the search text |
| `score_max` | float | Highest relevance score |
| `score_median` | float | Median relevance score |

### Detail mode

| Field | Type | Description |
|---|---|---|
| `id` | str | Term ID (e.g. `'go:0006260'`) |
| `name` | str | Term name (e.g. `'DNA replication'`) |
| `score` | float | Relevance score from fulltext search |

**Sort key:** `score DESC` (fulltext relevance)

**Default limit:** 5 (MCP), None (api/)

## Special handling

- **Lucene retry:** fulltext search may fail on special chars. API layer
  catches `Neo4jClientError` and retries with escaped query (existing
  pattern via `_LUCENE_SPECIAL`)
- **Pfam UNION:** Pfam searches both `pfamFullText` and
  `pfamClanFullText` indexes via UNION query (existing pattern)
- **No caching:** result depends on search_text
- **Validation:** `ontology` must be in `ONTOLOGY_CONFIG` (builder
  raises `ValueError`); `search_text` raises `ValueError` if
  empty/whitespace

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_search_ontology()` (update: add limit) + `build_search_ontology_summary()` (new) |
| 2 | API function | `api/functions.py` | `search_ontology()` (rewrite: `list[dict]` → `dict` envelope, 2-query pattern) |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Verify existing exports (no change expected) |
| 4 | MCP wrapper | `mcp_server/tools.py` | Rewrite: `async def`, Pydantic models, `ToolError` |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | Replace `TestBuildSearchOntology` + add `TestBuildSearchOntologySummary` |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | Replace `TestSearchOntology` |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | Replace `TestSearchOntologyWrapper` |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | Update response shape |
| 9 | Regression | `tests/regression/test_regression.py` | Update `TOOL_BUILDERS` (signature changed) |
| 10 | Eval cases | `tests/evals/cases.yaml` | Update params + shape |
| 11 | About content | `multiomics_explorer/inputs/tools/search_ontology.yaml` | Input YAML → build → verify |
| 12 | Docs | `CLAUDE.md` | Update tool description |
| 13 | Code review | — | Run code-review skill |

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_search_ontology`

```python
def build_search_ontology(
    *,
    ontology: str,
    search_text: str,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build Cypher for search_ontology.

    RETURN keys: id, name, score.
    """
```

Cypher (non-Pfam):
```cypher
CALL db.index.fulltext.queryNodes('{index_name}', $search_text)
YIELD node AS t, score
RETURN t.id AS id, t.name AS name, score
ORDER BY score DESC
[LIMIT $limit]  -- when limit is not None
```

Cypher (Pfam — UNION):
```cypher
CALL {
  CALL db.index.fulltext.queryNodes('{index_name}', $search_text)
  YIELD node AS t, score
  RETURN t.id AS id, t.name AS name, score
  UNION ALL
  CALL db.index.fulltext.queryNodes('{parent_index}', $search_text)
  YIELD node AS t, score
  RETURN t.id AS id, t.name AS name, score
}
RETURN id, name, score
ORDER BY score DESC
[LIMIT $limit]
```

**Design notes:**
- `limit` added to Cypher (v3 convention: server-side limiting)
- ONTOLOGY_CONFIG validation unchanged
- Pfam UNION pattern unchanged
- `ORDER BY score DESC` unchanged (natural sort for fulltext results)

### `build_search_ontology_summary`

```python
def build_search_ontology_summary(
    *,
    ontology: str,
    search_text: str,
) -> tuple[str, dict]:
    """Build summary Cypher for search_ontology.

    RETURN keys: total_entries, total_matching, score_max, score_median.
    """
```

Cypher (non-Pfam):
```cypher
CALL db.index.fulltext.queryNodes('{index_name}', $search_text)
YIELD node AS t, score
WITH count(t) AS total_matching,
     max(score) AS score_max,
     percentileDisc(score, 0.5) AS score_median
CALL { MATCH (all_t:{label}) RETURN count(all_t) AS total_entries }
RETURN total_entries, total_matching, score_max, score_median
```

Cypher (Pfam — UNION):
```cypher
CALL {
  CALL db.index.fulltext.queryNodes('{index_name}', $search_text)
  YIELD node AS t, score
  RETURN score
  UNION ALL
  CALL db.index.fulltext.queryNodes('{parent_index}', $search_text)
  YIELD node AS t, score
  RETURN score
}
WITH count(score) AS total_matching,
     max(score) AS score_max,
     percentileDisc(score, 0.5) AS score_median
CALL { MATCH (all_t:Pfam) RETURN count(all_t) AS pfam_count }
CALL { MATCH (all_c:PfamClan) RETURN count(all_c) AS clan_count }
RETURN pfam_count + clan_count AS total_entries,
       total_matching, score_max, score_median
```

**Design notes:**
- Summary always runs (cheap — fulltext search + aggregation +
  label count from Neo4j count store)
- `total_entries` via `CALL {}` subquery avoids Cartesian product
- `score_median` uses `percentileDisc(score, 0.5)` — same as
  `genes_by_function`
- Pfam `total_entries` counts both Pfam + PfamClan nodes (since search
  covers both indexes)
- Both builders share ONTOLOGY_CONFIG validation

---

## API Function

**File:** `api/functions.py`

```python
def search_ontology(
    search_text: str,
    ontology: str,
    summary: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Browse ontology terms by text search.

    Returns dict with keys: total_entries, total_matching, score_max,
    score_median, returned, truncated, results.
    Per result: id, name, score.
    """
```

- **Breaking change:** returns `dict` instead of `list[dict]`
- **Breaking change:** adds `summary`, `limit` params
- `summary=True` → `limit=0`
- 2-query pattern: summary always runs, detail skipped when `limit=0`
- Lucene retry on both summary and detail queries
- Summary query returns single row: `conn.execute_query(...)[0]`
- Validation: `ontology` checked by builder (`ValueError`);
  `search_text` raises `ValueError` if empty/whitespace

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

```python
class SearchOntologyResult(BaseModel):
    id: str = Field(description="Term ID (e.g. 'go:0006260')")
    name: str = Field(description="Term name (e.g. 'DNA replication')")
    score: float = Field(description="Fulltext relevance score (e.g. 5.23)")

class SearchOntologyResponse(BaseModel):
    total_entries: int = Field(description="Total terms in this ontology (e.g. 847)")
    total_matching: int = Field(description="Terms matching the search (e.g. 31)")
    score_max: float = Field(description="Highest relevance score (e.g. 5.23)")
    score_median: float = Field(description="Median relevance score (e.g. 2.1)")
    returned: int = Field(description="Results in this response (0 when summary=true)")
    truncated: bool = Field(description="True if total_matching > returned")
    results: list[SearchOntologyResult] = Field(
        default_factory=list, description="One row per matching term",
    )
```

### Wrapper

```python
@mcp.tool(
    tags={"ontology"},
    annotations={"readOnlyHint": True},
)
async def search_ontology(
    ctx: Context,
    search_text: Annotated[str, Field(
        description="Search query (Lucene syntax). "
        "E.g. 'replication', 'oxido*', 'transport AND membrane'.",
    )],
    ontology: Annotated[str, Field(
        description="Ontology to search: 'go_bp', 'go_mf', 'go_cc', "
        "'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam'.",
    )],
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> SearchOntologyResponse:
    """Browse ontology terms by text search (fuzzy, Lucene syntax).

    Returns term IDs for use with genes_by_ontology. Supports fuzzy (~),
    wildcards (*), exact phrases ("..."), boolean (AND, OR).
    """
    await ctx.info(f"search_ontology search_text={search_text!r} ontology={ontology}")
    try:
        conn = _conn(ctx)
        data = api.search_ontology(
            search_text, ontology, summary=summary,
            limit=limit, conn=conn,
        )
        results = [SearchOntologyResult(**r) for r in data["results"]]
        return SearchOntologyResponse(**{**data, "results": results})
    except ValueError as e:
        await ctx.warning(f"search_ontology error: {e}")
        raise ToolError(str(e))
    except Exception as e:
        await ctx.error(f"search_ontology unexpected error: {e}")
        raise ToolError(f"Error in search_ontology: {e}")
```

---

## Tests

### Unit: query builder (`test_query_builders.py`)

Replace `TestBuildSearchOntology` with:

```
class TestBuildSearchOntology:
    test_correct_fulltext_index (parametrize all 9 ontologies)
    test_returns_id_name_score_columns
    test_invalid_ontology_raises_valueerror
    test_search_text_passed_as_parameter
    test_pfam_union_query
    test_non_pfam_no_union
    test_limit_clause
    test_limit_none
    test_order_by_score_desc

class TestBuildSearchOntologySummary:
    test_returns_summary_keys (total_entries, total_matching, score_max, score_median)
    test_correct_fulltext_index (parametrize)
    test_pfam_union_query
    test_label_count_for_total_entries
    test_invalid_ontology_raises_valueerror
```

### Unit: API function (`test_api_functions.py`)

Replace `TestSearchOntology` with:

```
class TestSearchOntology:
    test_returns_dict (not list)
    test_summary_sets_limit_zero
    test_passes_params (search_text, ontology, limit)
    test_creates_conn_when_none
    test_lucene_retry
    test_invalid_ontology_raises
    test_empty_search_text_raises
    test_importable_from_package
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

Replace search_ontology tests with:

```
class TestSearchOntologyWrapper:
    test_returns_dict_envelope
    test_empty_results
    test_params_forwarded (search_text, ontology, summary, limit)
    test_truncation_metadata
    test_lucene_retry
    test_invalid_ontology_raises_toolerror
```

Update `EXPECTED_TOOLS` (tool name unchanged).

### Integration (`test_mcp_tools.py`)

Against live KG:
- Search returns expected fields in dict envelope
- Summary mode returns counts only
- Each result has expected columns (id, name, score)

### Regression (`test_regression.py`)

Update `TOOL_BUILDERS` (signature changed: added limit):
```python
"search_ontology": build_search_ontology,  # signature updated
```

Regenerate baselines: `pytest tests/regression/ --force-regen -m kg`

### Eval cases (`cases.yaml`)

```yaml
- id: search_ontology_go_bp
  tool: search_ontology
  desc: GO biological process search for replication
  params:
    search_text: replication
    ontology: go_bp
  expect:
    min_rows: 1
    columns: [id, name, score]

- id: search_ontology_kegg
  tool: search_ontology
  desc: KEGG search for metabolism (large result set)
  params:
    search_text: metabolism
    ontology: kegg
  expect:
    min_rows: 1
    columns: [id, name, score]

- id: search_ontology_pfam
  tool: search_ontology
  desc: Pfam search across domain + clan indexes
  params:
    search_text: polymerase
    ontology: pfam
  expect:
    min_rows: 1
    columns: [id, name, score]
```

(Keep per-ontology regression cases, update expected shape.)

---

## About Content

### Input YAML

**File:** `multiomics_explorer/inputs/tools/search_ontology.yaml`

```yaml
examples:
  - title: Search GO biological processes
    call: search_ontology(search_text="replication", ontology="go_bp")
    response: |
      {
        "total_entries": 847,
        "total_matching": 31,
        "score_max": 5.23,
        "score_median": 2.1,
        "returned": 5,
        "truncated": true,
        "results": [
          {"id": "go:0006260", "name": "DNA replication", "score": 5.23},
          {"id": "go:0006261", "name": "DNA-templated DNA replication", "score": 4.87},
          ...
        ]
      }

  - title: Summary only (how many terms match?)
    call: search_ontology(search_text="transport", ontology="go_bp", summary=True)

  - title: From search to gene discovery
    steps: |
      Step 1: search_ontology(search_text="replication", ontology="go_bp")
              → collect term IDs from results (e.g. "go:0006260")

      Step 2: genes_by_ontology(term_ids=["go:0006260"], ontology="go_bp")
              → find genes annotated to these terms (with hierarchy expansion)

      Step 3: gene_overview(locus_tags=["PMM0845", ...])
              → check data availability for discovered genes

chaining:
  - "search_ontology → genes_by_ontology"
  - "search_ontology → genes_by_ontology → gene_overview"

mistakes:
  - "search_ontology finds term IDs — use genes_by_ontology to find genes annotated to those terms"
  - "This tool searches term names only — it does not traverse the ontology hierarchy"
  - wrong: "search_ontology(search_text='PMM0845', ontology='go_bp')  # searching for a gene"
    right: "resolve_gene(identifier='PMM0845')  # use resolve_gene for gene lookups"
```

### Build

```bash
uv run python scripts/build_about_content.py search_ontology
```

### Verify

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -v
```

---

## Documentation

- `CLAUDE.md`: update search_ontology row — mention summary fields
- `docs/transition_plan_v3.md`: mark search_ontology as done in D4

## Code Review

Run code-review skill (full checklist) as final step.
