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

Maps tool/case names to query builder functions. Cases pass ontology
as a param — no per-ontology partials needed:

```python
TOOL_BUILDERS = {
    "resolve_gene": build_resolve_gene,
    "genes_by_function": build_genes_by_function,
    "gene_overview": build_gene_overview,
    "gene_details": build_gene_details,
    "gene_homologs": build_gene_homologs,
    "list_organisms": build_list_organisms,
    "search_ontology": build_search_ontology,
    "genes_by_ontology": build_genes_by_ontology,
    "gene_ontology_terms": build_gene_ontology_terms,
    "list_publications": build_list_publications,
    "list_experiments": build_list_experiments,
    "list_experiments_summary": build_list_experiments_summary,
    "differential_expression_by_gene": build_differential_expression_by_gene,
    "search_homolog_groups": build_search_homolog_groups,
    "search_homolog_groups_summary": build_search_homolog_groups_summary,
    "genes_by_homolog_group": build_genes_by_homolog_group,
    "genes_by_homolog_group_summary": build_genes_by_homolog_group_summary,
    "differential_expression_by_ortholog": build_differential_expression_by_ortholog_results,
}
```

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
