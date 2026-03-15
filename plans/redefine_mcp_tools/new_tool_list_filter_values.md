# Plan: `list_filter_values` Tool

New MCP tool — returns valid values for categorical filters: gene categories
and experimental condition types. Gives the LLM the vocabulary for `find_gene`
category filtering and `query_expression` / `compare_conditions` condition
filtering.

## Tool signature

```python
@mcp.tool()
def list_filter_values(ctx: Context) -> str:
    """List valid values for categorical filters used across tools.

    Returns:
    - gene_categories: values for the category filter on find_gene
      (e.g. "Photosynthesis", "Transport", "Stress response and adaptation")
    - condition_types: values for the condition filter on query_expression
      and compare_conditions (e.g. "nitrogen_stress", "light_stress", "coculture")
    """
```

## Query builders — `build_list_filter_values`

**Files:** `queries_lib.py`

Two queries combined in one tool call:

```cypher
-- Gene categories
MATCH (g:Gene) WHERE g.gene_category IS NOT NULL
RETURN g.gene_category AS category, count(*) AS gene_count
ORDER BY gene_count DESC
```

```cypher
-- Condition types
MATCH (e:EnvironmentalCondition)
RETURN DISTINCT e.condition_type AS condition_type, count(*) AS cnt
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
- Verify Cypher structure for category query (MATCH Gene, gene_category)
- Verify Cypher structure for condition type query (MATCH EnvironmentalCondition)
- No parameters — builders take no args

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
- Verify 25 gene categories returned
- Verify ~12 condition types returned

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
      RETURN DISTINCT e.condition_type AS condition_type, count(*) AS cnt
      ORDER BY cnt DESC
  expect:
    min_rows: 5
    columns: [condition_type, cnt]
    contains:
      condition_type: nitrogen_stress
```

### Regression snapshots (`tests/regression/`)

The `raw_cypher` eval cases above automatically produce regression baselines.
These snapshots catch any changes to the category vocabulary or condition types
after KG rebuilds.

```bash
pytest tests/regression/ --force-regen -m kg
pytest tests/regression/ -m kg
```
