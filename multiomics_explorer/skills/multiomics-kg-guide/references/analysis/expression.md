# Expression Analysis Guide

**Served as:** `docs://analysis/expression`

The differential-expression (DE) tool family and the two analysis utilities
that reshape its output into cross-experiment matrix views. Every Python
block below runs as written against the live KG.

---

## The DE-family tools

Three tools cover DE at different grains — pick by the shape of the question:

| Tool | Role |
|---|---|
| `differential_expression_by_gene` | DE rows for ONE organism (inferred from `locus_tags` / `experiment_ids`) — one row per gene × experiment × timepoint, sorted by \|log2FC\| |
| `differential_expression_by_ortholog` | DE framed by ortholog group across organisms — one row per group × experiment × timepoint, values are member gene counts per status |
| `gene_response_profile` | Cross-experiment rollup for ONE organism (inferred from `locus_tags`) — one row per gene, responses bucketed per treatment group with timepoints collapsed, broadest first |

Use `differential_expression_by_gene` for row-level fold changes and
timepoint dynamics. Use `differential_expression_by_ortholog` to compare a
group's response across strains — per-gene detail still comes from
`differential_expression_by_gene`, membership from `genes_by_homolog_group`.
Use `gene_response_profile` to see which treatments a gene set responds to
without per-timepoint log2FC; for the numbers behind a response, drop back to
`differential_expression_by_gene`.

`response_matrix` and `gene_set_compare` (below) both wrap
`gene_response_profile` — they are the Python-only entry points for a matrix
view across many genes and treatments at once, something none of the three
MCP tools returns directly.

**Read the experiment's `table_scope` before interpreting missing rows.** A
gene absent from `differential_expression_by_gene` results can mean "not
affected" or "not reported," and only an `all_detected_genes` experiment can
tell the two apart — a `significant_only` or `top_n` experiment simply never
reported genes that didn't clear its cutoff. Check `table_scope` (via
`list_experiments` or the tool's own `experiments[]` envelope) before reading
absence as biology.

---

## Cross-experiment summarization (`response_matrix` + `gene_set_compare`)

Two analysis utilities turn `gene_response_profile` output into matrix
views across treatments. Both group experiments by `treatment_type` by
default; pass `group_map` for custom groupings. Both share the
"direction classification" cell vocabulary:

| Value | Meaning |
|---|---|
| `"up"` | Only upregulated experiments in this group |
| `"down"` | Only downregulated experiments |
| `"mixed"` | Both up and down experiments |
| `"not_responded"` | Expression edges exist but none significant, OR gene inferred as tested via full-coverage scope (`groups_tested_not_responded`) |
| `"not_known"` | No expression data for this gene in this group |

### `response_matrix(genes, organism=None, ...)` — gene × group pivot

Returns a `pandas.DataFrame` indexed by `locus_tag` with one column per
group. Metadata columns `gene_name`, `product`, `gene_category` are
appended. Empty DataFrame (with `index.name="locus_tag"`) when no
results found.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `genes` | `list[str]` | required | Locus tags to query |
| `organism` | `str \| None` | `None` | Organism filter (fuzzy match) |
| `experiment_ids` | `list[str] \| None` | `None` | Experiment filter (ignored when `group_map` is set) |
| `group_map` | `dict[str, str] \| None` | `None` | `experiment_id → group label` for custom grouping |
| `conn` | `GraphConnection \| None` | `None` | Reuse an existing Neo4j connection |

**Basic treatment-type matrix:**

```python
from multiomics_explorer import response_matrix

df = response_matrix(
    genes=["PMM0370", "PMM0920", "PMM0965"],
    organism="MED4",
)
# Columns: one per treatment_type value (e.g. "nitrogen", "light", ...),
# then "gene_name", "product", "gene_category"
print(df[["nitrogen", "light"]])
```

**Custom grouping with `group_map`:**

```python
from multiomics_explorer import response_matrix

group_map = {
    "10.1038/msb4100087_growth_medium_growth_on_cyanate_as_med4_microarray": "early_N",
    "10.1038/msb4100087_nitrogen_nitrogen_deprivation_med4_med4_microarray": "late_N",
}
df = response_matrix(
    genes=["PMM0370", "PMM0920"],
    group_map=group_map,
)
# Columns: "early_N", "late_N", "gene_name", "product", "gene_category"
```

**Chaining from gene search:**

```python
from multiomics_explorer import genes_by_function, response_matrix

hits = genes_by_function(search_text="nitrogen", organism="MED4")
locus_tags = [r["locus_tag"] for r in hits["results"][:20]]
df = response_matrix(genes=locus_tags, organism="MED4")
```

**Common mistakes**

| Mistake | Fix |
|---|---|
| Passing `experiment_ids` when `group_map` is set | `group_map` overrides — pass experiments via `group_map` for custom grouping |
| Expecting numeric values (log2FC, p-values) in cells | `response_matrix` cells are categorical strings. Use `gene_response_profile` for rank/log2FC, or `differential_expression_by_gene` for per-timepoint numerics |
| Calling for a single gene | `gene_response_profile` directly returns richer per-group statistics |
| Assuming `"not_responded"` always means edge-based | Can also be inference-based via `groups_tested_not_responded` (full-coverage scope). Use `gene_response_profile` to distinguish |

### `gene_set_compare(set_a, set_b, ...)` — two-set partition

Compares response profiles for two gene sets. Builds a single response
matrix for the union, partitions by membership, and produces per-group
summary statistics.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `set_a` | `list[str]` | required | First gene set (locus tags) |
| `set_b` | `list[str]` | required | Second gene set |
| `organism` | `str \| None` | `None` | Organism filter |
| `set_a_name` | `str` | `"set_a"` | Label for set A in summary columns |
| `set_b_name` | `str` | `"set_b"` | Label for set B in summary columns |
| `experiment_ids` | `list[str] \| None` | `None` | Experiment filter (ignored when `group_map` is set) |
| `group_map` | `dict[str, str] \| None` | `None` | `experiment_id → group label` for custom grouping |
| `conn` | `GraphConnection \| None` | `None` | Reuse an existing Neo4j connection |

Returns a `dict`:

| Key | Type | Description |
|---|---|---|
| `overlap` | `DataFrame` | Genes present in both sets (same shape as `response_matrix` output) |
| `only_a` | `DataFrame` | Genes only in `set_a` |
| `only_b` | `DataFrame` | Genes only in `set_b` |
| `shared_groups` | `list[str]` | Groups where both sets have ≥1 responding gene |
| `divergent_groups` | `list[str]` | Groups where exactly one set has responding genes |
| `summary_per_group` | `DataFrame` | Indexed by group, columns: `{set_a_name}`, `{set_b_name}`, `overlap`, `shared` |

`summary_per_group` columns:

| Column | Type | Description |
|---|---|---|
| `{set_a_name}` | `int` | Count of responding genes from `set_a` in this group |
| `{set_b_name}` | `int` | Count of responding genes from `set_b` in this group |
| `overlap` | `int` | Count of responding overlap genes in this group |
| `shared` | `bool` | True if both sets have ≥1 responding gene |

"Responding" means the cell value is `"up"`, `"down"`, or `"mixed"`.

```python
from multiomics_explorer import gene_set_compare

result = gene_set_compare(
    set_a=["PMM0370", "PMM0920", "PMM0965"],
    set_b=["PMM0468", "PMM0552", "PMM0965"],
    organism="MED4",
    set_a_name="early_responders",
    set_b_name="late_responders",
)

print(result["overlap"])              # PMM0965
print(result["summary_per_group"])
#                      early_responders  late_responders  overlap  shared
# nitrogen                           3                2        1    True
# light                              0                1        0   False
print(result["shared_groups"])        # ["nitrogen"]
```

**Common mistakes**

| Mistake | Fix |
|---|---|
| Expecting `overlap` to contain only responding shared genes | `overlap` contains genes in both input lists regardless of response. "Shared" in `summary_per_group` is the responding-gene concept |
| Assuming `shared_groups` + `divergent_groups` are exhaustive | Groups where neither set responds appear in neither list |

---

## See also

- `docs://guide/python_api` — import topology, the three return shapes,
  `to_dataframe`, connection management, worked recipes.
- `docs://tools/differential_expression_by_gene`,
  `docs://tools/differential_expression_by_ortholog`,
  `docs://tools/gene_response_profile` — per-tool params and examples.
- `docs://analysis/enrichment` — pathway-level interpretation of a DE gene set.
