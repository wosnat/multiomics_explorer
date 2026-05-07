# gene_response_profile

## What it does

Summarize how each gene responds across experiments — one result
per gene with `response_summary` keyed by treatment type (default)
or experiment. Each entry reports experiments / timepoints tested,
responded (up / down), plus rank and log2FC stats for significant
rows. Sorted by response breadth (most groups first).

Routing: drill into a specific experiment's temporal pattern via
`differential_expression_by_gene(locus_tags=[...], experiment_ids=[id])`.
See `docs://guide/conventions` for tested-absent semantics
(`groups_tested_not_responded` vs `groups_not_known`).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags. E.g. ['PMM0370', 'PMM0920']. Get these from resolve_gene / gene_overview. |
| organism | string \| None | None | Organism name for validation (optional). Inferred from genes. Fuzzy word-based matching. |
| treatment_types | list[string] \| None | None | Filter to specific treatment types. |
| background_factors | list[string] \| None | None | Filter by background experimental factors (case-insensitive exact match). E.g. ['axenic', 'diel_cycle']. |
| experiment_ids | list[string] \| None | None | Restrict to specific experiments. Get these from list_experiments. |
| group_by | string ('treatment_type', 'experiment') | treatment_type | Group response summary by treatment_type (aggregates across experiments) or experiment (one entry per experiment). |
| limit | int | 50 | Max genes returned. |
| offset | int | 0 | Skip N genes for pagination. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
organism_name, genes_queried, genes_with_response, not_found, no_expression, returned, offset, truncated, results
```

- **organism_name** (string | None): Resolved organism name
- **genes_queried** (int): Count of input locus_tags (e.g. 17)
- **genes_with_response** (int): Genes with at least one significant expression edge (e.g. 15)
- **not_found** (list[string]): Input locus_tags not found in KG
- **no_expression** (list[string]): Gene exists but has zero expression edges
- **returned** (int): Genes in results after pagination (e.g. 15)
- **offset** (int): Offset into paginated gene list (e.g. 0)
- **truncated** (bool): True if more genes available beyond returned + offset

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0370') |
| gene_name | string \| None | Gene name (e.g. 'cynA'). Null if unannotated. |
| product | string \| None | Gene product description (e.g. 'cyanate transporter') |
| gene_category | string \| None | Functional category (e.g. 'Inorganic ion transport') |
| groups_responded | list[string] | Groups where gene is significant in at least one timepoint |
| groups_not_responded | list[string] | Groups where expression edges exist but none significant |
| groups_tested_not_responded | list[string] | Groups where all experiments use full-coverage scope (significant_only/significant_any_timepoint) but gene has no expression edge — inferred as tested, not significant |
| groups_not_known | list[string] | Groups with no expression edge for this gene and scope does not confirm coverage |
| response_summary | object | Per-group detail. Keys are treatment types or experiment IDs depending on group_by. |

## Few-shot examples

### Example 1: Gene response overview

```example-call
gene_response_profile(locus_tags=["PMM0370", "PMM0920"])
```

```example-response
{"organism_name": "Prochlorococcus marinus subsp. pastoris str. CCMP1986", "genes_queried": 2, "genes_with_response": 2, "not_found": [], "no_expression": [], "returned": 2, "offset": 0, "truncated": false, "results": [{"locus_tag": "PMM0370", "gene_name": "cynA", "product": "cyanate transporter", "gene_category": "Inorganic ion transport", "groups_responded": ["nitrogen_stress", "coculture"], "groups_not_responded": ["light_stress"], "groups_not_known": [], "response_summary": {"nitrogen_stress": {"experiments_total": 4, "experiments_tested": 3, "experiments_up": 3, "experiments_down": 0, "timepoints_total": 14, "timepoints_tested": 8, "timepoints_up": 8, "timepoints_down": 0, "up_best_rank": 3, "up_median_rank": 8.0, "up_max_log2fc": 5.7}}}]}
```

### Example 2: Filter by treatment type

```example-call
gene_response_profile(locus_tags=["PMM0370"], treatment_types=["nitrogen_stress", "coculture"])
```

### Example 3: Per-experiment breakdown

```example-call
gene_response_profile(locus_tags=["PMM0370"], group_by="experiment")
```

### Example 4: Chaining — find responsive genes then profile them

```
Step 1: genes_by_function(search_text="nitrogen transport", organism="MED4")
        → collect locus_tags from results

Step 2: gene_response_profile(locus_tags=["PMM0370", ...])
        → see which treatments each gene responds to

Step 3: differential_expression_by_gene(locus_tags=["PMM0370"], experiment_ids=["..."])
        → drill into time course for a specific experiment
```

## Chaining patterns

```
genes_by_function → gene_response_profile
genes_by_ontology → gene_response_profile
gene_overview → gene_response_profile (check expression_edge_count first)
gene_response_profile → differential_expression_by_gene (drill into specific experiment)
```

## Common mistakes

```mistake
Assuming groups_not_known means 'gene does not respond to this treatment'
```

```correction
groups_not_known means no expression data exists — the gene was not profiled or not reported for that treatment. Check experiments_total in the response_summary for coverage.
```

```mistake
Comparing up_max_log2fc across different organisms or platforms
```

```correction
log2FC magnitudes are not directly comparable across platforms (microarray vs RNA-seq). Ranks are comparable.
```

```mistake
Using this tool to see time course dynamics
```

```correction
This tool aggregates across timepoints. Use differential_expression_by_gene with a specific experiment to see temporal patterns.
```

- Results are sorted by response breadth — genes responding to more treatments appear first

- Single organism enforced — call once per organism

- Two Python wrappers reshape this tool's output into matrix views: `response_matrix(genes, organism)` for a gene × treatment-group pivot, and `gene_set_compare(set_a, set_b)` for two-set overlap / only-A / only-B partitioning. Top-level imports: `from multiomics_explorer import response_matrix, gene_set_compare`. See `docs://guide/python_api` (Cross-experiment summarization).

- DataFrame conversion: `to_dataframe(result)` auto-dispatches and returns the unwound gene × treatment-group table. See `docs://guide/python_api`.

## Package import equivalent

```python
from multiomics_explorer import gene_response_profile

result = gene_response_profile(locus_tags=...)
# returns dict with keys: organism_name, genes_queried, genes_with_response, not_found, no_expression, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
