# Regression testing guide

## How it works

1. Test cases defined in `tests/evals/cases.yaml`
2. `test_regression.py` maps tool names to query builders via `TOOL_BUILDERS`
3. Runs each case's query against live KG
4. Compares results to golden files (YAML baselines managed by pytest-regressions)

## cases.yaml format

```yaml
- id: unique_case_id
  tool: tool_name          # maps to TOOL_BUILDERS key
  desc: What this case verifies
  params:
    param1: value1
    param2: value2
  expect:
    min_rows: 1            # minimum result rows (default 1)
    max_rows: 100          # optional upper bound
    columns: [col1, col2]  # required column names
    row0:                  # first row assertions
      col1: expected_value
    contains:              # at least one row has these values
      col2: expected_value
```

## TOOL_BUILDERS dict

Maps tool/case names to query builder functions. Uses **target**
names after v3 migration (update as tools are renamed):

```python
TOOL_BUILDERS = {
    "resolve_gene": build_resolve_gene,
    "genes_by_function": build_genes_by_function,  # was: search_genes
    "gene_overview": build_gene_overview,
    "gene_homologs": ...,  # was: get_homologs (multi-step)
    # Per-ontology partial entries
    "search_ontology_go_bp": partial(build_search_ontology, ontology="go_bp"),
    # ...
}
```

**Note:** During transition, old builder names remain in the actual
code until each tool is renamed. The above shows the target state.

When adding a new tool:
1. Add builder to `TOOL_BUILDERS`
2. Add cases to `cases.yaml`
3. Generate baselines: `pytest tests/regression/ --force-regen -m kg`

## Special paths in test_regression.py

Some tools have custom handling:
- `raw_cypher` — uses `run_cypher` directly
- `list_filter_values` — calls `build_list_gene_categories`
- `gene_homologs` (was `get_homologs_with_members`) — multi-step
  (groups → members)

## When to regenerate baselines

- After intentional Cypher changes (new RETURN columns, different ORDER BY)
- After KG rebuild (data may have changed)
- After KG schema changes
- After tool renames (new builder names in TOOL_BUILDERS)

```bash
pytest tests/regression/ --force-regen -m kg
```

Then verify the diffs are expected:
```bash
git diff tests/regression/
```

## Golden file location

Baselines stored in `tests/regression/` as YAML files, managed automatically
by pytest-regressions (`data_regression` fixture).

## Note on tied scores

After KG rebuilds, search_ontology fixtures may need regeneration due to
tied-score reordering. This is expected — the data is correct, just ordered
differently when scores are equal.
