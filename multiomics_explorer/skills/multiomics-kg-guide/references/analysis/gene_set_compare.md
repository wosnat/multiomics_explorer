# gene_set_compare

## What it does

Compares expression response profiles for two gene sets. Builds a
single response matrix for the union of both sets, then partitions
results into overlap / only_a / only_b and produces per-group summary
statistics showing which treatments each set responds to.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| set_a | list[str] | required | First gene set (locus tags) |
| set_b | list[str] | required | Second gene set (locus tags) |
| organism | str \| None | None | Organism filter |
| set_a_name | str | "set_a" | Label for set A in summary columns |
| set_b_name | str | "set_b" | Label for set B in summary columns |
| experiment_ids | list[str] \| None | None | Experiment filter (ignored when group_map set) |
| group_map | dict[str, str] \| None | None | experiment_id → group label for custom grouping |
| conn | GraphConnection \| None | None | Reuse existing Neo4j connection |

## Response format

Returns a `dict` with these keys:

| Key | Type | Description |
|---|---|---|
| `overlap` | DataFrame | Genes present in both sets. Same format as response_matrix output. |
| `only_a` | DataFrame | Genes only in set_a |
| `only_b` | DataFrame | Genes only in set_b |
| `shared_groups` | list[str] | Groups where both sets have at least one responding gene |
| `divergent_groups` | list[str] | Groups where exactly one set has responding genes |
| `summary_per_group` | DataFrame | Indexed by group with columns: {set_a_name}, {set_b_name}, overlap, shared |

### summary_per_group columns

| Column | Type | Description |
|---|---|---|
| `{set_a_name}` | int | Count of responding genes from set_a in this group |
| `{set_b_name}` | int | Count of responding genes from set_b in this group |
| `overlap` | int | Count of responding overlap genes in this group |
| `shared` | bool | True if both sets have ≥1 responding gene |

"Responding" means the cell value is "up", "down", or "mixed".

## Few-shot examples

### Example 1: Compare two gene sets

```python
from multiomics_explorer.analysis import gene_set_compare

result = gene_set_compare(
    set_a=["PMM0370", "PMM0920", "PMM0965"],
    set_b=["PMM0468", "PMM0552", "PMM0965"],
    organism="MED4",
    set_a_name="early_responders",
    set_b_name="late_responders",
)

# Genes in both sets
print(result["overlap"])  # PMM0965

# Per-group summary
print(result["summary_per_group"])
#                      early_responders  late_responders  overlap  shared
# nitrogen_stress                    3                2        1    True
# light_stress                       0                1        0   False

# Treatments where both sets respond
print(result["shared_groups"])  # ["nitrogen_stress"]
```

### Example 2: With custom grouping

```python
from multiomics_explorer.analysis import gene_set_compare

group_map = {
    "GSE37441_MED4_Nlimit_1": "nitrogen",
    "GSE59000_MED4_HL": "light",
}
result = gene_set_compare(
    set_a=["PMM0370"],
    set_b=["PMM0920"],
    group_map=group_map,
)
```

## Chaining patterns

```
genes_by_function (two searches) → gene_set_compare (compare pathways)
genes_by_ontology (two terms) → gene_set_compare (compare GO term gene sets)
gene_set_compare → differential_expression_by_gene (drill into divergent groups)
```

## Common mistakes

```mistake
Using overlapping sets and expecting overlap DataFrame to contain all shared genes
```

```correction
The overlap DataFrame contains genes present in BOTH input lists, regardless
of whether they respond. A gene in both sets that shows "not_known" everywhere
still appears in overlap. "Shared" in summary_per_group means both sets have
responding genes in a group — different concept.
```

```mistake
Assuming divergent_groups and shared_groups are exhaustive
```

```correction
Groups where neither set responds appear in neither list. Only groups with at
least one responding gene in at least one set are classified.
```
