# Analysis utilities: `response_matrix` and `gene_set_compare`

## Scope

Two Python-only utility functions in `multiomics_explorer/analysis/`. No MCP tools, no query builders, no changes to existing functions. These compose the existing `gene_response_profile` API into DataFrame outputs for scripts and notebooks.

## Module layout

```
multiomics_explorer/analysis/
├── __init__.py          # re-exports: response_matrix, gene_set_compare
└── expression.py        # both functions
```

## Dependency chain

```
kg/queries_lib.py (query builders)
  └── api/functions.py (gene_response_profile)
        └── analysis/expression.py (response_matrix, gene_set_compare)
```

These functions call `api.gene_response_profile()` as a Python function, never via MCP.

## Function 1: `response_matrix`

### Signature

```python
def response_matrix(
    genes: list[str],
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    group_map: dict[str, str] | None = None,
    conn: GraphConnection | None = None,
) -> pd.DataFrame:
```

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| genes | list[str] | required | Gene locus tags |
| organism | str \| None | None | Organism name; inferred from genes if omitted |
| experiment_ids | list[str] \| None | None | Restrict to specific experiments |
| group_map | dict[str, str] \| None | None | Maps experiment_id to custom group label. When provided, calls `gene_response_profile` with `group_by="experiment"` and re-aggregates by group labels |
| conn | GraphConnection \| None | None | Reuse existing connection |

### Return value

DataFrame with:
- **Index:** `locus_tag`
- **Group columns:** one per treatment type (default) or custom group label (when `group_map` provided)
- **Metadata columns:** `gene_name`, `product`, `gene_category`

### Cell values (direction classification)

| Condition | Cell value |
|-----------|------------|
| `experiments_up > 0` and `experiments_down == 0` | `"up"` |
| `experiments_down > 0` and `experiments_up == 0` | `"down"` |
| Both > 0 | `"mixed"` |
| Group key in `groups_not_responded` | `"not_responded"` |
| Group key in `groups_not_known` | `"not_known"` |

### Implementation

1. **Without `group_map`:** Call `api.gene_response_profile(locus_tags=genes, organism=organism, experiment_ids=experiment_ids, group_by="treatment_type", conn=conn)`.
2. **With `group_map`:** Call `api.gene_response_profile(locus_tags=genes, organism=organism, experiment_ids=list(group_map.keys()), group_by="experiment", conn=conn)`. Then re-aggregate: for experiment IDs mapping to the same custom label, merge their response summaries (sum experiment/timepoint counts, collect rank/log2fc lists) and re-classify direction.
3. Pivot `response_summary` dict per gene into matrix columns using the direction classification table above.
4. Attach metadata columns (`gene_name`, `product`, `gene_category`) from the API result.

## Function 2: `gene_set_compare`

### Signature

```python
def gene_set_compare(
    set_a: list[str],
    set_b: list[str],
    organism: str | None = None,
    set_a_name: str = "set_a",
    set_b_name: str = "set_b",
    experiment_ids: list[str] | None = None,
    group_map: dict[str, str] | None = None,
    conn: GraphConnection | None = None,
) -> dict[str, pd.DataFrame | list[str]]:
```

### Parameters

| Name | Type | Default | Description |
|------|------|---------|-------------|
| set_a | list[str] | required | First gene set (locus tags) |
| set_b | list[str] | required | Second gene set (locus tags) |
| organism | str \| None | None | Organism name; inferred from genes if omitted |
| set_a_name | str | "set_a" | Label for set A in summary columns |
| set_b_name | str | "set_b" | Label for set B in summary columns |
| experiment_ids | list[str] \| None | None | Restrict to specific experiments |
| group_map | dict[str, str] \| None | None | Custom grouping (passed through to `response_matrix`) |
| conn | GraphConnection \| None | None | Reuse existing connection |

### Return value

```python
{
    "overlap": DataFrame,           # genes in both sets, with matrix + metadata columns
    "only_a": DataFrame,            # genes only in set_a
    "only_b": DataFrame,            # genes only in set_b
    "shared_groups": list[str],     # groups where both sets have responding genes
    "divergent_groups": list[str],  # groups where sets respond differently
    "summary_per_group": DataFrame, # per-group breakdown
}
```

### `summary_per_group` DataFrame

One row per group. Columns:

| Column | Type | Description |
|--------|------|-------------|
| `{set_a_name}` | int | Count of genes from set A responding to this group |
| `{set_b_name}` | int | Count of genes from set B responding to this group |
| `overlap` | int | Count of genes in both sets that respond to this group |
| `shared` | bool | True if both sets have at least one gene responding |

**"Responding"** = cell value in `{"up", "down", "mixed"}`.

**"Divergent"** = exactly one set has responding genes (the other has zero), or both sets respond but not in the same direction (e.g., set A is all "up" while set B is all "down").

### Implementation

1. Compute `union = deduplicated(set_a + set_b)`.
2. Call `response_matrix(genes=union, organism=organism, experiment_ids=experiment_ids, group_map=group_map, conn=conn)` — single API call.
3. Partition rows into `overlap`, `only_a`, `only_b` based on set membership.
4. For each group column, count responding genes per set, compute overlap count and `shared` boolean.
5. Derive `shared_groups` (both sets respond) and `divergent_groups` (response patterns differ) from summary.

## Testing

### Unit tests (`tests/unit/test_analysis.py`)

Mock `api.gene_response_profile` return value.

- `response_matrix`: correct DataFrame shape, direction classification for all five cell values, metadata columns present, `group_map` re-aggregation merges correctly
- `gene_set_compare`: correct partitioning (overlap/only_a/only_b row counts), `summary_per_group` counts, `shared_groups`/`divergent_groups` lists

### Integration tests (`tests/integration/test_analysis.py`)

Real KG, known MED4 genes.

- `response_matrix`: matrix shape matches gene count, known treatment types appear as columns
- `gene_set_compare` with two overlapping gene sets: partition sizes correct, `shared_groups` non-empty
