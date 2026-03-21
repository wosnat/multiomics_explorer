# Plan: `list_publications` — new tool

Surfaces the ~21 Publication nodes in the KG. Publications are the
entry point for exploring expression data — "what studies exist?" Currently
invisible to Claude despite being fully populated with title, abstract,
authors, DOI.

## Status / Prerequisites

- [x] KG change: Experiment node redesign deployed (2026-03-20).
  76 Experiment nodes, `Has_experiment` edges from all 21 Publications.
- [x] KG change: EnvironmentalCondition absorbed into Experiment.
- [x] KG verified: 0 orphan publications (all have experiments).
- [x] KG change: `publicationFullText` index on Publication(title, abstract, description).
- [x] KG change: precomputed properties on Publication nodes
  (`experiment_count`, `treatment_types`, `omics_types`).
- [x] KG change: `organism` → `organisms` rename on Publication nodes.

## Out of Scope

- Summary/detail/about modes — this is a Phase C exercise tool, modes
  come in Phase D
- Phase 2 temporal profiling tools — see `expression_tools_redesign.md`

---

## Tool Signature

```python
@mcp.tool(
    tags={"publications", "discovery"},
    annotations={"readOnlyHint": True},
)
def list_publications(
    ctx: Context,
    organism: Annotated[str | None, Field(
        description="Filter by organism name (case-insensitive). "
        "E.g. 'MED4', 'HOT1A3'.",
    )] = None,
    treatment_type: Annotated[str | None, Field(
        description="Filter by experiment treatment type. "
        "Use list_filter_values for valid values.",
    )] = None,
    search_text: Annotated[str | None, Field(
        description="Free-text search on title, abstract, and description "
        "(Lucene syntax). E.g. 'nitrogen', 'co-culture AND phage'.",
    )] = None,
    author: Annotated[str | None, Field(
        description="Filter by author name (case-insensitive). "
        "E.g. 'Sher', 'Chisholm'.",
    )] = None,
    verbose: Annotated[bool, Field(
        description="Include abstract and description. "
        "Default compact for routing.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 50,
) -> dict:
    """List publications with expression data in the knowledge graph.

    Returns publication metadata and experiment summaries. Use this as
    an entry point to discover what studies exist, then drill into
    specific experiments with list_experiments or genes with search_genes.

    Response: {total_entries, total_matching, returned, truncated, results: [...]}.
    Per publication: doi, title, authors, year, journal, study_type,
    organisms, experiment_count, treatment_types, omics_types.
    With search_text, also: score. With verbose=True, also: abstract, description.
    """
```

**Return envelope:** `{total_entries, total_matching, returned, truncated, results: [...]}`

**Per-result columns (compact):** `doi`, `title`, `authors`, `year`, `journal`,
`study_type`, `organisms`, `experiment_count`, `treatment_types`,
`omics_types`.

Verbose adds: `abstract`, `description`.

---

## Implementation Order (follows add-or-update-tool skill)

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_list_publications()` |
| 2 | API function | `api/functions.py` | `list_publications()` |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add to imports + `__all__` |
| 4 | MCP wrapper | `mcp_server/tools.py` | `@mcp.tool()` wrapper |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | `TestBuildListPublications` |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | `TestListPublications` |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | `TestListPublicationsWrapper` + update `EXPECTED_TOOLS` |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | Smoke test against live KG |
| 9 | Regression | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS` |
| 10 | Eval cases | `tests/evals/cases.yaml` | Regression + correctness cases |
| 11 | About content | `multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_publications.md` | Per-tool about text |
| 12 | Docs | `CLAUDE.md` | Add row to MCP Tools table |

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_list_publications`

```python
def build_list_publications(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build Cypher for listing publications with experiment summaries.

    RETURN keys (compact): doi, title, authors, year, journal, study_type,
    organisms, experiment_count, treatment_types, omics_types.
    When search_text is provided, also: score.
    RETURN keys (verbose): adds abstract, description.
    """

def build_list_publications_summary(
    *,
    organism: str | None = None,
    treatment_type: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher for matching publications.

    RETURN keys: total_matching, total_entries.
    """
```

Both builders share the same WHERE clause construction. The summary
builder returns both `total_matching` (filtered count) and
`total_entries` (all publications in KG).

**Cypher (when `search_text` is provided):**

```cypher
CALL db.index.fulltext.queryNodes('publicationFullText', $search_text)
YIELD node AS p, score
{where_block}
RETURN p.doi AS doi,
       p.title AS title,
       p.authors AS authors,
       p.publication_year AS year,
       p.journal AS journal,
       p.study_type AS study_type,
       p.organisms AS organisms,
       p.experiment_count AS experiment_count,
       p.treatment_types AS treatment_types,
       p.omics_types AS omics_types,
       score
       {verbose_columns}
ORDER BY score DESC, p.publication_year DESC, p.title
{limit_clause}
```

`{limit_clause}` expands to `LIMIT $limit` when limit is provided.

**Cypher (when `search_text` is NOT provided):**

```cypher
MATCH (p:Publication)
{where_block}
RETURN p.doi AS doi,
       p.title AS title,
       p.authors AS authors,
       p.publication_year AS year,
       p.journal AS journal,
       p.study_type AS study_type,
       p.organisms AS organisms,
       p.experiment_count AS experiment_count,
       p.treatment_types AS treatment_types,
       p.omics_types AS omics_types
       {verbose_columns}
ORDER BY p.publication_year DESC, p.title
{limit_clause}
```

`{verbose_columns}` expands to `, p.abstract AS abstract, p.description AS description`
when `verbose=True`, empty string otherwise.

**WHERE clause construction:**

```python
conditions: list[str] = []
params: dict = {}

if search_text:
    params["search_text"] = search_text
    # fulltext CALL is prepended to the query — see Cypher above

if organism:
    conditions.append(
        "ANY(o IN p.organisms WHERE toLower(o) CONTAINS toLower($organism))"
    )
    params["organism"] = organism

if treatment_type:
    conditions.append(
        "ANY(t IN p.treatment_types WHERE toLower(t) = toLower($treatment_type))"
    )
    params["treatment_type"] = treatment_type

if author:
    conditions.append(
        "ANY(a IN p.authors WHERE toLower(a) CONTAINS toLower($author))"
    )
    params["author"] = author
```

**Design notes:**
- `search_text` uses `publicationFullText` index (Lucene syntax,
  case-insensitive, fuzzy matching) — same pattern as `search_genes`
  and `search_ontology`
- When `search_text` is provided, the query starts with a fulltext CALL
  and results are sorted by score first
- When `search_text` is not provided, the query starts with a MATCH
  and results are sorted by year DESC
- No experiment join needed — `experiment_count`, `treatment_types`,
  `omics_types` are precomputed properties on Publication node
  (see `docs/kg-specs/list_publications.md`)
- All filters work on Publication node properties directly:
  `p.organism` (list), `p.treatment_types` (list), `p.authors` (list)
- Publications without experiments have `experiment_count=0` and
  empty lists — included in unfiltered results, excluded when
  filtering by treatment_type (empty list has no matches)
- No LIMIT needed — only ~21 publications

---

## API Function

**File:** `api/functions.py`

```python
def list_publications(
    organism: str | None = None,
    treatment_type: str | None = None,
    search_text: str | None = None,
    author: str | None = None,
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List publications with expression data.

    Returns dict with keys: total_entries, total_matching, results.
    Per result: doi, title, authors, year, journal, study_type, organisms,
    experiment_count, treatment_types, omics_types.
    When verbose=True, also includes abstract, description.
    When search_text is provided, also includes score.
    """
    conn = _default_conn(conn)
    filter_kwargs = dict(
        organism=organism, treatment_type=treatment_type,
        search_text=search_text, author=author,
    )

    def _execute(st=search_text):
        kw = {**filter_kwargs, "search_text": st}
        count_cypher, count_params = build_list_publications_summary(**kw)
        summary = conn.execute_query(count_cypher, **count_params)[0]

        data_cypher, data_params = build_list_publications(
            **kw, verbose=verbose, limit=limit,
        )
        results = conn.execute_query(data_cypher, **data_params)
        return summary, results

    try:
        summary, results = _execute()
    except Neo4jClientError:
        if search_text:
            logger.debug("list_publications: Lucene parse error, retrying with escaped query")
            escaped = _LUCENE_SPECIAL.sub(r'\\\g<0>', search_text)
            summary, results = _execute(st=escaped)
        else:
            raise

    return {
        "total_entries": summary["total_entries"],
        "total_matching": summary["total_matching"],
        "results": results,
    }
```

The API function runs two queries: count (for `total`) then data
(with LIMIT). The MCP wrapper adds `returned` and `truncated` from
the API response.

Lucene escape retry follows the same pattern as `search_genes` and
`search_ontology`.

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

```python
from typing import Annotated
from pydantic import Field
from fastmcp.exceptions import ToolError

@mcp.tool(
    tags={"publications", "discovery"},
    annotations={"readOnlyHint": True},
)
def list_publications(
    ctx: Context,
    organism: Annotated[str | None, Field(
        description="Filter by organism name (case-insensitive). "
        "E.g. 'MED4', 'HOT1A3'.",
    )] = None,
    treatment_type: Annotated[str | None, Field(
        description="Filter by experiment treatment type. "
        "Use list_filter_values for valid values.",
    )] = None,
    search_text: Annotated[str | None, Field(
        description="Free-text search on title, abstract, and description "
        "(Lucene syntax). E.g. 'nitrogen', 'co-culture AND phage'.",
    )] = None,
    author: Annotated[str | None, Field(
        description="Filter by author name (case-insensitive). "
        "E.g. 'Sher', 'Chisholm'.",
    )] = None,
    verbose: Annotated[bool, Field(
        description="Include abstract and description. "
        "Default compact for routing.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results.", ge=1,
    )] = 50,
) -> dict:
    """List publications with expression data in the knowledge graph.

    Returns publication metadata and experiment summaries. Use this as
    an entry point to discover what studies exist, then drill into
    specific experiments with list_experiments or genes with search_genes.

    Response: {total_entries, total_matching, returned, truncated, results: [...]}.
    Per publication: doi, title, authors, year, journal, study_type,
    organisms, experiment_count, treatment_types, omics_types.
    With search_text, also: score. With verbose=True, also: abstract, description.
    """
    logger.info("list_publications organism=%s treatment_type=%s search_text=%s author=%s verbose=%s",
                organism, treatment_type, search_text, author, verbose)
    try:
        conn = _conn(ctx)
        result = api.list_publications(
            organism=organism, treatment_type=treatment_type,
            search_text=search_text, author=author,
            verbose=verbose, limit=limit, conn=conn,
        )
        return {
            "total_entries": result["total_entries"],
            "total_matching": result["total_matching"],
            "returned": len(result["results"]),
            "truncated": result["total_matching"] > len(result["results"]),
            "results": result["results"],
        }
    except ValueError as e:
        logger.warning("list_publications error: %s", e)
        raise ToolError(str(e))
    except Exception as e:
        logger.warning("list_publications unexpected error: %s", e)
        raise ToolError(f"Error in list_publications: {e}")
```

Limit defaults to 50, no max cap — publication rows are small in compact mode.
No caching — query is trivially fast on this dataset.
Returns `dict` envelope — FastMCP handles serialization to structured content.

---

## Tests

### Unit: query builder (`test_query_builders.py`)

```
class TestBuildListPublications:
    test_no_filters           — valid Cypher, no WHERE, no fulltext CALL, returns expected columns
    test_organism_filter      — WHERE has ANY(o IN p.organisms WHERE toLower CONTAINS)
    test_treatment_type_filter — WHERE has exact match on treatment_type
    test_search_text          — Cypher starts with fulltext CALL, ORDER BY score DESC
    test_search_text_none     — no fulltext CALL when search_text is None
    test_author_filter        — WHERE has ANY(a IN p.authors WHERE toLower(a) CONTAINS toLower($author))
    test_combined_filters     — all filters produce AND-joined WHERE
    test_returns_expected_columns — doi, title, authors, year, journal, etc.
    test_order_by             — ORDER BY publication_year DESC, title (no search_text)
    test_verbose_false        — no abstract/description in RETURN
    test_verbose_true         — abstract and description in RETURN
    test_limit_clause         — LIMIT $limit when limit provided
    test_limit_none           — no LIMIT when limit is None

class TestBuildListPublicationsSummary:
    test_no_filters           — returns total_entries and total_matching
    test_with_filters         — total_matching reflects filtered count
    test_shares_where_clause  — same filter logic as data builder
```

### Unit: API function (`test_api_functions.py`)

```
class TestListPublications:
    test_returns_dict         — calls summary + data builders, returns dict with total_entries/total_matching/results
    test_passes_params        — organism, treatment_type, search_text, author, verbose forwarded
    test_creates_conn_when_none — default conn used when None
    test_lucene_escape_retry  — Neo4jClientError with search_text triggers escaped retry
    test_importable_from_package — from multiomics_explorer import list_publications
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

```
class TestListPublicationsWrapper:
    test_returns_dict_envelope — response has total_entries, total_matching, returned, truncated, results
    test_empty_results        — returns envelope with returned=0, results=[]
    test_params_forwarded     — all params passed through to api
    test_truncation_metadata  — returned == len(results), truncated == (total_matching > returned)

Update EXPECTED_TOOLS to include "list_publications".
```

### Integration (`test_mcp_tools.py`)

Against live KG:
- No filters → returns all 21 publications
- `organism="MED4"` → subset with MED4 experiments
- `treatment_type="coculture"` → papers with coculture experiments
- `search_text="nitrogen"` → fulltext matches title/abstract
- `author="Chisholm"` → returns Chisholm lab papers
- Each result has experiment_count > 0

### Regression (`test_regression.py`)

Add to `TOOL_BUILDERS`:
```python
"list_publications": build_list_publications,
```

### Eval cases (`cases.yaml`)

```yaml
- id: list_publications_all
  tool: list_publications
  desc: All publications returned when no filters
  params: {}
  expect:
    min_rows: 15
    columns: [doi, title, authors, year, experiment_count, organisms,
              treatment_types, omics_types]

- id: list_publications_organism
  tool: list_publications
  desc: Filter by organism returns subset
  params:
    organism: "MED4"
  expect:
    min_rows: 5
    columns: [doi, title, experiment_count]

- id: list_publications_treatment_type
  tool: list_publications
  desc: Coculture treatment type filter
  params:
    treatment_type: "coculture"
  expect:
    min_rows: 3
    columns: [doi, title, experiment_count]

- id: list_publications_search_text
  tool: list_publications
  desc: Fulltext search on title/abstract
  params:
    search_text: "nitrogen"
  expect:
    min_rows: 1
    columns: [doi, title]

- id: list_publications_author
  tool: list_publications
  desc: Filter by author name
  params:
    author: "Chisholm"
  expect:
    min_rows: 2
    columns: [doi, title, authors]
```

---

## About Content

**File:** `multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_publications.md`

Using the about-content template (Option A: small result set, no modes):

- **What it does:** Entry point for exploring the KG — discover what
  studies exist, filter by organism/treatment/author/keyword, then
  drill into experiments or genes.
- **Parameters:** organism (case-insensitive CONTAINS on p.organism list),
  treatment_type (use list_filter_values for valid values),
  search_text (Lucene fulltext on title/abstract/description),
  author (case-insensitive CONTAINS), verbose (adds abstract/description),
  limit (default 50).
- **Response:** `{total_entries, total_matching, returned, truncated, results}`.
  Compact results by default; `verbose=True` adds abstract and description.
- **Chaining:** `list_publications` → `list_experiments` (by DOI or
  treatment_type) → `search_genes` or `query_expression` (by experiment).
- **Package import:** `from multiomics_explorer import list_publications` —
  returns `{total_entries, total_matching, results}` (no truncation wrapper).

Tagged blocks for the about file:

````
```example-call
list_publications(organism="MED4")
```

```expected-keys
total_entries, total_matching, returned, truncated, results
```

```example-call
list_publications(search_text="nitrogen", verbose=True)
```

```expected-keys
total_entries, total_matching, returned, truncated, results
```
````

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add row to MCP Tools table: `list_publications` — List publications with experiment summaries, filterable by organism/treatment/search/author |
