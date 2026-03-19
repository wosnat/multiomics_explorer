# Plan: `list_publications` — new tool

Surfaces the ~21 Publication nodes already in the KG. Publications are the
entry point for exploring expression data — "what studies exist?" Currently
invisible to Claude despite being fully populated with title, abstract,
authors, DOI.

## Status / Prerequisites

- [ ] KG change: Experiment node redesign (see `experiment_node_redesign.md`
  in KG repo). Requires `Has_experiment` edges from Publication → Experiment.
- [ ] KG change: EnvironmentalCondition absorbed into Experiment.

## Out of Scope

- Publication search by author name — could add later but not priority
- Publications without expression data (none currently exist in KG)
- Phase 2 temporal profiling tools — see `expression_tools_redesign.md`

---

## Tool Signature

```python
@mcp.tool()
def list_publications(
    ctx: Context,
    organism: str | None = None,
    condition_type: str | None = None,
    keyword: str | None = None,
) -> str:
    """List publications with expression data in the knowledge graph.

    Returns publication metadata and a summary of experiments each paper
    contributed. Use this to discover what studies exist before drilling
    into specific experiments with list_experiments.

    Args:
        organism: Filter by organism name (CONTAINS match). Matches both
            profiled organism and coculture partner. E.g. "MED4", "HOT1A3".
        condition_type: Filter by experiment type. E.g. "coculture",
            "nitrogen_stress", "light_stress". Use list_filter_values
            to see valid values.
        keyword: Free-text search on publication title and abstract.
    """
```

**Return columns:**
`doi`, `title`, `authors`, `year`, `journal`, `abstract`, `study_type`,
`experiment_count`, `organisms` (list), `condition_types` (list),
`omics_types` (list).

---

## KG-side Changes

- [ ] K1: Experiment node with `Has_experiment` edges from Publication
  (KG repo `experiment_node_redesign.md`)

## Implementation Order

| Order | Change | Where | Status |
|-------|--------|-------|--------|
| 1 | Experiment node + Has_experiment edges | KG | pending |
| 2 | `build_list_publications` in `queries_lib.py` | Explorer | this file |
| 3 | `list_publications` tool in `tools.py` | Explorer | this file |
| 4 | Tests, docs | Explorer | this file |

## Agent Assignments

| Step | Agent | Task | Depends on |
|------|-------|------|------------|
| 1 | **query-builder** | Add `build_list_publications` to `queries_lib.py` | KG rebuild |
| 2 | **tool-wrapper** | Add `list_publications` tool to `tools.py` | query-builder |
| 3a | **test-updater** | Add unit, integration, eval tests | tool-wrapper |
| 3b | **doc-updater** | Update `CLAUDE.md`, `README.md`, `AGENT.md`, `docs/testplans/testplan.md` | tool-wrapper |
| 4 | **code-reviewer** | Review all changes, run unit tests, grep for stale refs | test-updater, doc-updater |

---

## Query Builders

**Files:** `queries_lib.py`

### `build_list_publications`

```cypher
MATCH (p:Publication)-[:Has_experiment]->(e:Experiment)
{where_block}
WITH p,
     collect(DISTINCT e.organism_strain) AS organisms,
     collect(DISTINCT e.coculture_partner) AS partners,
     collect(DISTINCT e.treatment_type) AS condition_types,
     collect(DISTINCT e.omics_type) AS omics_types,
     count(DISTINCT e) AS experiment_count
RETURN p.doi AS doi,
       p.title AS title,
       p.authors AS authors,
       p.publication_year AS year,
       p.journal AS journal,
       p.abstract AS abstract,
       p.study_type AS study_type,
       experiment_count,
       organisms,
       condition_types,
       omics_types
ORDER BY p.publication_year DESC, p.title
```

**WHERE clause construction:**

```python
where_clauses: list[str] = []
params: dict = {}

if organism:
    where_clauses.append(
        "(e.organism_strain CONTAINS $org OR e.coculture_partner CONTAINS $org)"
    )
    params["org"] = organism

if condition_type:
    where_clauses.append("e.treatment_type = $ctype")
    params["ctype"] = condition_type

if keyword:
    # Use Neo4j full-text index on Publication if available,
    # otherwise fall back to CONTAINS on title + abstract
    where_clauses.append(
        "(p.title CONTAINS $kw OR p.abstract CONTAINS $kw)"
    )
    params["kw"] = keyword
```

**Strategy notes:**
- MATCH through Has_experiment ensures we only return publications that
  actually have expression data (filters out any stray Publication nodes)
- Filters apply to the Experiment node properties (organism, treatment_type)
  which requires the JOIN — but with ~21 publications and ~100 experiments
  this is trivially fast
- `organism` searches both `organism_strain` and `coculture_partner` via OR
- `condition_type` maps to `treatment_type` in Neo4j (naming convention
  difference — see resolved decisions in parent plan)
- No LIMIT — there are only ~21 publications

---

## Tool Wrapper Logic

**Files:** `tools.py`

Straightforward query-and-format. No post-query logic needed.

```python
@mcp.tool()
def list_publications(ctx, organism=None, condition_type=None, keyword=None):
    conn = _conn(ctx)
    cypher, params = build_list_publications(
        organism=organism, condition_type=condition_type, keyword=keyword,
    )
    results = conn.execute_query(cypher, **params)
    if not results:
        return _with_query("No publications found.", cypher, params, ctx)
    return _with_query(_fmt(results), cypher, params, ctx)
```

No caching needed — the result set is small (~21 rows max) and the query
is fast. No tier-1/tier-2 split — every publication fits in context.

---

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**
- [ ] `TestBuildListPublications.test_no_filters` — returns valid Cypher
  with no WHERE block
- [ ] `test_organism_filter` — WHERE has CONTAINS on organism_strain OR
  coculture_partner
- [ ] `test_condition_type_filter` — WHERE has exact match on treatment_type
- [ ] `test_keyword_filter` — WHERE has CONTAINS on title OR abstract
- [ ] `test_combined_filters` — all three filters produce AND-joined WHERE

**`tests/unit/test_tool_wrappers.py`:**
- [ ] `TestListPublicationsWrapper.test_no_filters_returns_json` — mock
  conn returns results, verify JSON output
- [ ] `test_empty_results` — returns "No publications found."
- [ ] `test_organism_passthrough` — organism param passed to builder
- [ ] Tool registration count updated

### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

- [ ] No filters → returns all ~21 publications
- [ ] `organism="MED4"` → returns subset with MED4 experiments
- [ ] `organism="HOT1A3"` → matches both as profiled organism and
  coculture partner
- [ ] `condition_type="coculture"` → returns papers with coculture experiments
- [ ] `keyword="nitrogen"` → matches on title or abstract
- [ ] Each result has non-empty `organisms`, `condition_types`, `omics_types`
- [ ] `experiment_count` > 0 for all results
- [ ] Known publication: Aharonovich 2016 (doi:10.1038/ismej.2016.70) present

### Eval cases (`tests/evals/cases.yaml`)

```yaml
- id: list_publications_all
  tool: list_publications
  desc: All publications returned when no filters
  params: {}
  expect:
    min_rows: 15
    columns: [doi, title, authors, year, experiment_count, organisms, condition_types]

- id: list_publications_organism
  tool: list_publications
  desc: Filter by organism returns subset
  params:
    organism: "MED4"
  expect:
    min_rows: 5
    columns: [doi, title, experiment_count]

- id: list_publications_coculture
  tool: list_publications
  desc: Coculture condition type filter
  params:
    condition_type: "coculture"
  expect:
    min_rows: 3
    columns: [doi, title, experiment_count]
    contains:
      condition_types: "coculture"

- id: list_publications_keyword
  tool: list_publications
  desc: Keyword search on title/abstract
  params:
    keyword: "nitrogen"
  expect:
    min_rows: 1
    columns: [doi, title]
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add row to MCP Tools table: `list_publications` — publications with experiment summaries |
| `README.md` | Add entry to MCP tools section, bump tool count |
| `AGENT.md` | Add row to tools table |
| `docs/testplans/testplan.md` | Add test plan section |
