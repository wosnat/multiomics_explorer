# Plan: `list_filter_values` Tool

New MCP tool — returns valid values for categorical filters: gene categories
and experimental condition types. Gives the LLM the vocabulary for `search_genes`
category filtering and `query_expression` / `compare_conditions` condition
filtering.

**Caching:** Results change only on KG rebuild. Cache in lifespan context on
first call and return the cached value on subsequent calls.

## Tool signature

```python
@mcp.tool()
def list_filter_values(ctx: Context) -> str:
    """List valid values for categorical filters used across tools.

    Returns:
    - gene_categories: values for the category filter on search_genes
      (e.g. "Photosynthesis", "Transport", "Stress response and adaptation")
    - condition_types: values for the condition filter on query_expression
      and compare_conditions (e.g. "nitrogen_stress", "light_stress", "coculture")
    """
```

## Agent assignments

| Step | Agent | Task | Depends on |
|------|-------|------|------------|
| 1 | **query-builder** | Add `build_list_gene_categories` and `build_list_condition_types` to `queries_lib.py` | — |
| 2 | **tool-wrapper** | Add `list_filter_values` tool to `tools.py` with caching and combined JSON response | query-builder |
| 3a | **test-updater** | Add unit, integration, eval, and regression tests for the new tool | tool-wrapper |
| 3b | **doc-updater** | Update `CLAUDE.md`, `README.md`, `AGENT.md`, `docs/testplans/testplan.md`, skills | tool-wrapper |
| 4 | **code-reviewer** | Review all changes against this plan, run unit tests, grep for stale refs | test-updater, doc-updater |

Steps 3a and 3b can run in parallel.

## Query builders

**Files:** `queries_lib.py`

Two separate builders for independent testability and reuse:

### `build_list_gene_categories`

```cypher
MATCH (g:Gene) WHERE g.gene_category IS NOT NULL
RETURN g.gene_category AS category, count(*) AS gene_count
ORDER BY gene_count DESC
```

### `build_list_condition_types`

```cypher
MATCH (e:EnvironmentalCondition)
RETURN e.condition_type AS condition_type, count(*) AS cnt
ORDER BY cnt DESC
```

Returns ~25 categories + ~12 condition types. Combined into one response:
```json
{
  "gene_categories": [{"category": "...", "gene_count": N}, ...],
  "condition_types": [{"condition_type": "...", "count": N}, ...]
}
```

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**
- `build_list_gene_categories`: verify Cypher structure (MATCH Gene, gene_category)
- `build_list_condition_types`: verify Cypher structure (MATCH EnvironmentalCondition)
- No parameters — both builders take no args

**`tests/unit/test_tool_wrappers.py`:**
- Mock both query results, verify combined JSON structure:
  `{"gene_categories": [...], "condition_types": [...]}`
- Verify each sub-list has expected keys

### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

- Verify known categories present: "Photosynthesis", "Transport",
  "Stress response and adaptation", "Translation"
- Verify known condition types present: "nitrogen_stress", "light_stress",
  "coculture"
- Verify all counts > 0
- Verify at least 20 gene categories returned
- Verify at least 5 condition types returned

### Eval cases (`tests/evals/cases.yaml`)

```yaml
- id: list_filter_values
  tool: list_filter_values
  desc: Returns gene categories and condition types
  params: {}
  expect:
    # This tool returns a combined JSON, so eval assertions are on the
    # tool wrapper response. Use a raw_cypher case for each sub-query
    # to snapshot the individual lists.

- id: list_filter_values_categories
  tool: raw_cypher
  desc: Snapshot of all gene categories with counts
  params:
    query: >
      MATCH (g:Gene) WHERE g.gene_category IS NOT NULL
      RETURN g.gene_category AS category, count(*) AS gene_count
      ORDER BY gene_count DESC
  expect:
    min_rows: 20
    columns: [category, gene_count]
    contains:
      category: Photosynthesis

- id: list_filter_values_conditions
  tool: raw_cypher
  desc: Snapshot of all condition types with counts
  params:
    query: >
      MATCH (e:EnvironmentalCondition)
      RETURN e.condition_type AS condition_type, count(*) AS cnt
      ORDER BY cnt DESC
  expect:
    min_rows: 5
    columns: [condition_type, cnt]
    contains:
      condition_type: nitrogen_stress
```

## Documentation updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add `list_filter_values` row to MCP Tools table |
| `README.md` | Add entry to MCP tools section, bump tool count |
| `AGENT.md` | Add row to tools table (~line 52) |
| `docs/testplans/testplan.md` | Add test plan section for new tool |
| `.claude/skills/update-tests/SKILL.md` | Update test counts after implementation |

### Regression snapshots (`tests/regression/`)

The `raw_cypher` eval cases above automatically produce regression baselines.
These snapshots catch any changes to the category vocabulary or condition types
after KG rebuilds.

```bash
pytest tests/regression/ --force-regen -m kg
pytest tests/regression/ -m kg
```
