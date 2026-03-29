# Tool spec: genes_by_function

## Purpose

Free-text search across gene functional annotations via the
`geneFullText` fulltext index. Phase 2 Discovery tool: text → gene IDs.

Replaces `search_genes` (v1): rename + v3 upgrade. Drops the
`deduplicate` parameter — ortholog bridging is handled by the tool
chain (`genes_by_function` → `gene_homologs`).

## Out of Scope

- **Ortholog deduplication** — dropped. Use `gene_homologs` for
  cross-organism bridging.
- **Ontology-based search** — use `genes_by_ontology`
- **Gene details** — use `gene_overview` for batch gene characterization
- **Expression data** — use `differential_expression_by_gene`

## Status / Prerequisites

- [x] KG spec: not needed — fulltext index and all Gene properties exist
- [x] Scope reviewed with user
- [x] Result-size controls decided (summary + limit)
- [ ] Ready for Phase 2 (build)

## Use cases

- **Function discovery** — "What genes are involved in photosynthesis?"
- **Cross-organism survey** — search broadly, use `by_organism` summary
  to see distribution, then filter by organism
- **Category-scoped search** — combine text search with category filter
  for precision
- **Chain:** `list_organisms` → discover organism names →
  `genes_by_function(organism=...)`
- **Chain:** `list_filter_values` → discover categories →
  `genes_by_function(category=...)`
- **Chain:** `genes_by_function` → `gene_overview` (batch details)
- **Chain:** `genes_by_function` → `gene_homologs` (ortholog bridging)

## KG dependencies

- `Gene` nodes: `locus_tag`, `gene_name`, `product`,
  `function_description`, `gene_summary`, `organism_strain`,
  `annotation_quality`, `gene_category`
- `geneFullText` fulltext index (on `gene_summary`, `gene_synonyms`,
  `alternate_functional_descriptions`, `pfam_names`, etc.)

All properties and index verified present in live KG (2026-03-23).

---

## Tool Signature

```python
@mcp.tool(
    tags={"genes", "discovery"},
    annotations={"readOnlyHint": True},
)
async def genes_by_function(
    ctx: Context,
    search_text: Annotated[str, Field(
        description="Free-text query (Lucene syntax supported). "
        "E.g. 'photosystem', 'nitrogen AND transport', 'dnaN~'.",
    )],
    organism: Annotated[str | None, Field(
        description="Filter by organism (case-insensitive substring). "
        "E.g. 'MED4', 'Prochlorococcus MED4'. "
        "Use list_organisms to see valid values.",
    )] = None,
    category: Annotated[str | None, Field(
        description="Filter by gene_category. "
        "E.g. 'Photosynthesis', 'Transport'. "
        "Use list_filter_values to see valid values.",
    )] = None,
    min_quality: Annotated[int, Field(
        description="Minimum annotation_quality (0-3). "
        "0=hypothetical, 1=has description, 2=named product, "
        "3=well-annotated. Use 2 to skip hypothetical proteins.",
        ge=0, le=3,
    )] = 0,
    summary: Annotated[bool, Field(
        description="When true, return only summary fields (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include function_description and gene_summary.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 5,
) -> GenesByFunctionResponse:
    """Search genes by functional annotation text.

    Full-text search across gene names, products, and functional
    descriptions. Supports Lucene syntax: quoted phrases, AND/OR,
    wildcards (*), fuzzy (~). Results ranked by relevance score.

    For ontology-based search, use genes_by_ontology.
    For gene details, use gene_overview.
    """
```

**Return envelope:** `total_search_hits, total_matching, by_organism,
by_category, score_max, score_median, returned, truncated, results`

**Per-result columns (compact — 7):**
`locus_tag`, `gene_name`, `product`, `organism_strain`,
`gene_category`, `annotation_quality`, `score`

**Verbose adds (2):**
`function_description`, `gene_summary`

## Result-size controls

Frequently large result set → summary + limit pattern.

### Summary fields (always present)

| Field | Type | Description |
|---|---|---|
| `total_search_hits` | int | Total genes matching search text (before organism/category/min_quality filters) |
| `total_matching` | int | Total genes matching search + all filters |
| `by_organism` | list | `[{organism, count}]` sorted desc (filtered) |
| `by_category` | list | `[{category, count}]` sorted desc (filtered) |
| `score_max` | float | Highest relevance score (filtered) |
| `score_median` | float | Median relevance score (filtered) |

`total_search_hits` gives filter selectivity context: "5 of 42
photosystem genes are in MED4". When no filters are active,
`total_search_hits == total_matching`.

### Zero-match behavior

When `total_matching=0`: all summary fields present, counts are 0,
`by_organism=[]`, `by_category=[]`, `score_max=0.0`,
`score_median=0.0`, `results=[]`, `returned=0`, `truncated=False`.

### Not a batch tool

This is a search tool (input is a text query, not known IDs).
No `not_found` field. See architecture_target_v3.md §Batch tools.

**Sort key:** `score DESC, locus_tag ASC`

**Default limit:** 5 (MCP), None (api/)

**Verbose:**
- Compact: locus_tag, gene_name, product, organism_strain,
  gene_category, annotation_quality, score
- Verbose adds: function_description, gene_summary

## Special handling

- **Lucene retry:** On `ClientError`, escape special chars and retry
  (applies to both summary and detail queries)
- **2-query pattern:** summary query always runs, detail query skipped
  when `limit=0`
- **No caching:** results depend on search text
- **No validation on category:** invalid values return empty results
  (fulltext search + category WHERE clause). Use `list_filter_values`
  for discovery.

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_genes_by_function()` + `build_genes_by_function_summary()` |
| 2 | API function | `api/functions.py` | `genes_by_function()` |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add to imports + `__all__` |
| 4 | MCP wrapper | `mcp_server/tools.py` | `@mcp.tool()` wrapper + Pydantic models |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | `TestBuildGenesByFunction` + `TestBuildGenesByFunctionSummary` |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | `TestGenesByFunction` |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | `TestGenesByFunctionWrapper` + update `EXPECTED_TOOLS` |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | Smoke test against live KG |
| 9 | Regression | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS` |
| 10 | Eval cases | `tests/evals/cases.yaml` | Regression + correctness cases |
| 11 | About content | `multiomics_explorer/inputs/tools/genes_by_function.yaml` | Input YAML → build → verify |
| 12 | Docs | `CLAUDE.md` | Rename in tool table |
| 13 | Code review | — | Run code-review skill (full checklist) |

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_genes_by_function_summary`

```python
def build_genes_by_function_summary(
    *,
    search_text: str,
    organism: str | None = None,
    category: str | None = None,
    min_quality: int = 0,
) -> tuple[str, dict]:
    """Build summary Cypher for genes_by_function.

    RETURN keys: total_search_hits, total_matching, by_organism,
    by_category, score_max, score_median.
    """
```

Cypher uses conditional counting to compute both `total_search_hits`
(before filters) and `total_matching` (after filters) in a single
pass:

```cypher
CALL db.index.fulltext.queryNodes('geneFullText', $search_text)
YIELD node AS g, score
WITH g, score,
     CASE WHEN
       ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
            WHERE toLower(g.organism_strain) CONTAINS word))
       AND ($min_quality = 0 OR g.annotation_quality >= $min_quality)
       AND ($category IS NULL OR g.gene_category = $category)
     THEN 1 ELSE 0 END AS matches
WITH count(g) AS total_search_hits,
     sum(matches) AS total_matching,
     max(CASE WHEN matches = 1 THEN score END) AS score_max,
     percentileDisc(
       CASE WHEN matches = 1 THEN score END, 0.5
     ) AS score_median,
     [x IN collect(
       CASE WHEN matches = 1 THEN g.organism_strain END
     ) WHERE x IS NOT NULL] AS organisms,
     [x IN collect(
       CASE WHEN matches = 1 THEN g.gene_category END
     ) WHERE x IS NOT NULL] AS categories
RETURN total_search_hits, total_matching, score_max, score_median,
       apoc.coll.frequencies(organisms) AS by_organism,
       apoc.coll.frequencies(categories) AS by_category
```

### `build_genes_by_function`

```python
def build_genes_by_function(
    *,
    search_text: str,
    organism: str | None = None,
    category: str | None = None,
    min_quality: int = 0,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build detail Cypher for genes_by_function.

    RETURN keys (compact): locus_tag, gene_name, product,
    organism_strain, gene_category, annotation_quality, score.
    RETURN keys (verbose): adds function_description, gene_summary.
    """
```

```cypher
CALL db.index.fulltext.queryNodes('geneFullText', $search_text)
YIELD node AS g, score
WHERE ($organism IS NULL OR ALL(word IN split(toLower($organism), ' ')
       WHERE toLower(g.organism_strain) CONTAINS word))
  AND ($min_quality = 0 OR g.annotation_quality >= $min_quality)
  AND ($category IS NULL OR g.gene_category = $category)
RETURN g.locus_tag AS locus_tag, g.gene_name AS gene_name,
       g.product AS product, g.organism_strain AS organism_strain,
       g.gene_category AS gene_category,
       g.annotation_quality AS annotation_quality,
       score
       [, g.function_description AS function_description,
          g.gene_summary AS gene_summary  -- verbose only]
ORDER BY score DESC, g.locus_tag
[LIMIT $limit]
```

### WHERE clause construction

Both builders share the same filter logic. The summary builder uses
it as a CASE expression (conditional counting); the detail builder
uses it as a WHERE clause. Filter conditions:

1. `$organism IS NULL OR ALL(word IN split(toLower($organism), ' ') WHERE toLower(g.organism_strain) CONTAINS word)` — case-insensitive multi-word organism match
2. `$min_quality = 0 OR g.annotation_quality >= $min_quality` — annotation quality floor
3. `$category IS NULL OR g.gene_category = $category` — exact category match

### Design notes

- **Sort order:** `score DESC, locus_tag ASC` — relevance-first with
  deterministic tiebreaker
- **No precomputed stats** — all summary fields are aggregated at query
  time from fulltext results. This is fine because fulltext search
  already limits the working set.
- **`total_search_hits` via conditional counting** — avoids running the
  fulltext query twice. Single pass: count all fulltext hits
  (`total_search_hits`), then count those passing filters
  (`total_matching`).
- **APOC `frequencies`** — returns `[{item, count}]`; api/ renames
  to domain keys (`organism`/`category`).

---

## API Function

**File:** `api/functions.py`

```python
def genes_by_function(
    search_text: str,
    organism: str | None = None,
    category: str | None = None,
    min_quality: int = 0,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Search genes by functional annotation text.

    Returns dict with keys: total_search_hits, total_matching,
    by_organism, by_category, score_max, score_median,
    returned, truncated, results.
    Per result: locus_tag, gene_name, product, organism_strain,
    gene_category, annotation_quality, score.
    Verbose adds: function_description, gene_summary.
    """
```

- `summary=True` → `limit=0`
- Always run summary query → total_search_hits, total_matching, breakdowns,
  score stats
- Skip detail when `limit=0`
- Lucene retry on `ClientError` (both summary and detail queries)
- Rename APOC `{item, count}` to domain keys, sort desc
- `returned = len(results)`, `truncated = total_matching > returned`
- Zero-match: `score_max=0.0`, `score_median=0.0`, empty breakdowns

### Removing

- `_deduplicate_by_orthogroup()` helper — no longer needed
- `build_search_genes_dedup_groups()` import — no longer needed
- Old `search_genes()` function

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

### Pydantic response models

```python
class OrganismBreakdown(BaseModel):
    organism: str = Field(description="Organism strain (e.g. 'Prochlorococcus MED4')")
    count: int = Field(description="Number of matching genes")

class CategoryBreakdown(BaseModel):
    category: str = Field(description="Gene category (e.g. 'Photosynthesis')")
    count: int = Field(description="Number of matching genes")

class GenesByFunctionResult(BaseModel):
    locus_tag: str = Field(description="Gene locus tag (e.g. 'PMM0001')")
    gene_name: str | None = Field(description="Gene name (e.g. 'dnaN')")
    product: str | None = Field(description="Gene product (e.g. 'DNA polymerase III subunit beta')")
    organism_strain: str = Field(description="Organism strain (e.g. 'Prochlorococcus MED4')")
    gene_category: str | None = Field(description="Functional category (e.g. 'Photosynthesis')")
    annotation_quality: int = Field(description="Annotation quality 0-3 (3=best)")
    score: float = Field(description="Fulltext relevance score")
    # verbose only:
    function_description: str | None = Field(default=None, description="Functional description text")
    gene_summary: str | None = Field(default=None, description="Combined gene annotation summary")

class GenesByFunctionResponse(BaseModel):
    total_search_hits: int = Field(description="Total genes matching search text (before filters)")
    total_matching: int = Field(description="Total genes matching search + all filters")
    by_organism: list[OrganismBreakdown] = Field(description="Gene counts per organism, sorted desc")
    by_category: list[CategoryBreakdown] = Field(description="Gene counts per category, sorted desc")
    score_max: float = Field(description="Highest relevance score")
    score_median: float = Field(description="Median relevance score")
    returned: int = Field(description="Number of results returned")
    truncated: bool = Field(description="True when total_matching > returned")
    results: list[GenesByFunctionResult] = Field(description="Gene results ranked by relevance")
```

Thin wrapper: `GenesByFunctionResponse(**data)` with standard error
handling (ValueError → ToolError, Exception → ToolError with prefix).

Note: `OrganismBreakdown` and `CategoryBreakdown` may be shared with
other tools that have the same breakdown shape — check existing models
before creating duplicates.

---

## Tests

### Remove (old search_genes)

| File | Remove |
|---|---|
| `test_query_builders.py` | `TestBuildSearchGenes` |
| `test_api_functions.py` | `TestSearchGenes` |
| `test_tool_wrappers.py` | `TestSearchGenesWrapper` |
| `test_tool_correctness.py` | `TestSearchGenesCorrectness` |
| `test_regression.py` | `search_genes` from `TOOL_BUILDERS` |
| `cases.yaml` | All `search_genes_*` cases |
| `test_regression/` | All `search_genes_*.yml` golden files |
| `gene_data.py` | `as_search_genes_result()` |

### Add (new genes_by_function)

| Layer | File | Test class |
|---|---|---|
| Query builder | `test_query_builders.py` | `TestBuildGenesByFunction`, `TestBuildGenesByFunctionSummary` |
| API | `test_api_functions.py` | `TestGenesByFunction` |
| MCP wrapper | `test_tool_wrappers.py` | `TestGenesByFunctionWrapper` + update `EXPECTED_TOOLS` |
| Integration | `test_mcp_tools.py` | Update existing search tests |
| Regression | `test_regression.py` | Add to `TOOL_BUILDERS` |
| Evals | `cases.yaml` | New `genes_by_function_*` cases |
| Fixtures | `gene_data.py` | `as_genes_by_function_result()` |

### Unit: query builder (`test_query_builders.py`)

```
class TestBuildGenesByFunction:
    test_no_filters
    test_organism_filter
    test_category_filter
    test_min_quality_filter
    test_combined_filters
    test_returns_expected_columns
    test_order_by
    test_verbose_false
    test_verbose_true
    test_limit_clause
    test_limit_none

class TestBuildGenesByFunctionSummary:
    test_no_filters
    test_with_filters
    test_returns_total_search_hits_and_total_matching
    test_shares_where_clause
```

### Unit: API function (`test_api_functions.py`)

```
class TestGenesByFunction:
    test_returns_dict
    test_summary_fields_present
    test_total_search_hits_vs_total_matching
    test_summary_true_skips_detail
    test_lucene_retry_on_error
    test_passes_params
    test_creates_conn_when_none
    test_importable_from_package
    test_zero_match_behavior
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

```
class TestGenesByFunctionWrapper:
    test_returns_pydantic_envelope
    test_empty_results
    test_params_forwarded
    test_truncation_metadata
    test_total_search_hits_present
    test_error_raises_tool_error

Update EXPECTED_TOOLS to include "genes_by_function".
Remove "search_genes" from EXPECTED_TOOLS.
```

### Integration (`test_mcp_tools.py`)

Against live KG:
- No filters → returns results with expected fields
- Organism filter narrows results
- Category filter narrows results
- Summary mode returns counts, empty results
- Each result has expected compact columns

### Regression (`test_regression.py`)

Add to `TOOL_BUILDERS`:
```python
"genes_by_function": build_genes_by_function,
```

### Eval cases (`cases.yaml`)

```yaml
- id: genes_by_function_photosystem
  tool: genes_by_function
  desc: Basic photosystem search
  params: {search_text: "photosystem"}
  expect:
    min_rows: 1
    columns: [locus_tag, gene_name, product, organism_strain,
              gene_category, annotation_quality, score]

- id: genes_by_function_with_organism
  tool: genes_by_function
  desc: Organism filter narrows results
  params: {search_text: "photosystem", organism: "MED4"}
  expect:
    min_rows: 1

- id: genes_by_function_category_filter
  tool: genes_by_function
  desc: Category filter
  params: {search_text: "iron", category: "Inorganic ion transport"}
  expect:
    min_rows: 1

- id: genes_by_function_min_quality
  tool: genes_by_function
  desc: Quality filter
  params: {search_text: "photosystem", min_quality: 2}
  expect:
    min_rows: 1

- id: genes_by_function_lucene_fuzzy
  tool: genes_by_function
  desc: Lucene fuzzy syntax
  params: {search_text: "dnaN~"}
  expect:
    min_rows: 1
```

---

## About Content

### Input YAML

**File:** `multiomics_explorer/inputs/tools/genes_by_function.yaml`

```yaml
examples:
  - title: Search for photosystem genes
    call: genes_by_function(search_text="photosystem")
    response: |
      {
        "total_search_hits": 42, "total_matching": 42,
        "by_organism": [{"organism": "Synechococcus WH8102", "count": 8}, ...],
        "by_category": [{"category": "Photosynthesis", "count": 35}, ...],
        "score_max": 6.1, "score_median": 3.2,
        "returned": 5, "truncated": true,
        "results": [
          {"locus_tag": "SYNW2505", "gene_name": "cyanoQ", "product": "photosystem II protein CyanoQ", "organism_strain": "Synechococcus WH8102", "gene_category": "Photosynthesis", "annotation_quality": 3, "score": 6.06},
          ...
        ]
      }

  - title: Filter by organism (note total_search_hits vs total_matching)
    call: genes_by_function(search_text="transport", organism="MED4")
    response: |
      {
        "total_search_hits": 120, "total_matching": 15,
        ...
      }

  - title: Filter by category
    call: genes_by_function(search_text="iron", category="Inorganic ion transport")

  - title: Summary only (counts and breakdowns)
    call: genes_by_function(search_text="photosystem", summary=True)

  - title: From search to gene details
    steps: |
      Step 1: genes_by_function(search_text="nitrogen fixation")
              → collect locus_tags from results

      Step 2: gene_overview(locus_tags=["PMM0001", ...])
              → detailed gene characterization

  - title: From search to ortholog bridging
    steps: |
      Step 1: genes_by_function(search_text="chaperone", organism="MED4")
              → collect locus_tags

      Step 2: gene_homologs(locus_tags=["PMM0001", ...])
              → find ortholog groups across organisms

verbose_fields:
  - function_description
  - gene_summary

chaining:
  - "list_organisms → genes_by_function (with organism filter)"
  - "list_filter_values → genes_by_function (with category filter)"
  - "genes_by_function → gene_overview"
  - "genes_by_function → gene_homologs → genes_by_homolog_group"

mistakes:
  - "Lucene syntax supported: quoted phrases, AND/OR, wildcards (*), fuzzy (~). Invalid syntax auto-retried with escaping."
  - "category filter is not validated — invalid values return empty results. Use list_filter_values to discover valid categories."
  - "by_organism and by_category reflect all matching genes (total_matching), not just the returned rows"
  - "total_search_hits counts genes matching search text before organism/category/min_quality filters — compare with total_matching for filter selectivity"
  - wrong: "genes_by_function(search_text='photosystem', limit=100)  # get everything"
    right: "genes_by_function(search_text='photosystem', summary=True)  # check counts first, then adjust limit"
```

### Build

```bash
uv run python scripts/build_about_content.py genes_by_function
```

### Verify

```bash
pytest tests/unit/test_about_content.py -v
pytest tests/integration/test_about_examples.py -v
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Rename `search_genes` → `genes_by_function` in tool table, update description |

## Cascading rename

| What | Files to update |
|---|---|
| Builder functions | `queries_lib.py`: remove `build_search_genes`, `build_search_genes_dedup_groups`; add `build_genes_by_function`, `build_genes_by_function_summary` |
| API function | `api/functions.py`: remove `search_genes`, `_deduplicate_by_orthogroup`; add `genes_by_function`. Update `api/__init__.py`, `multiomics_explorer/__init__.py` |
| MCP tool | `mcp_server/tools.py`: remove old `search_genes` tool; add `genes_by_function` with Pydantic models |
| Other tool docstrings | Grep for `search_genes` in all tool docstrings — update references |
| `list_filter_values` | Update description to reference `genes_by_function` instead of `search_genes` |
| Tests | Full replacement (see Tests section above) |
| Regression baselines | Delete old `search_genes_*.yml`, regenerate as `genes_by_function_*.yml` |

## Code Review

Run code-review skill (full checklist) as final step.
