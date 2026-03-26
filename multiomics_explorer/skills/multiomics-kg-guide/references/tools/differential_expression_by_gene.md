# differential_expression_by_gene

## What it does

Gene-centric differential expression. One row per gene x experiment x timepoint.

Returns summary statistics (always) + top results sorted by |log2FC|
(strongest effects first). Default limit=5 gives a quick overview.
Set summary=True for counts only, or increase limit for more rows.

At least one of organism, locus_tags, or experiment_ids is required.
All inputs must refer to the same organism — call once per organism.

When organism is the only filter, it scopes to that organism's full
expression data (e.g. MED4 = 47K edges). Combine with summary=True or
significant_only=True + limit for manageable results.

The expression_status field uses the publication-specific threshold from
each experiment's original paper (not a uniform padj<0.05 cutoff).

For cross-organism comparison via ortholog groups, use
differential_expression_by_ortholog.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string \| None | None | Organism name or partial match (e.g. 'MED4', 'Prochlorococcus MED4'). Fuzzy word-based matching (same as list_experiments). Get valid names from list_organisms. |
| locus_tags | list[string] \| None | None | Gene locus tags. E.g. ['PMM0001', 'PMM0845']. Get these from resolve_gene / gene_overview. |
| experiment_ids | list[string] \| None | None | Experiment IDs to restrict to. Get these from list_experiments. |
| direction | string ('up', 'down') \| None | None | Filter by expression direction. |
| significant_only | bool | False | If true, return only statistically significant results. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Add product, experiment_name, treatment, gene_category, omics_type, coculture_partner to each row. |
| limit | int | 5 | Max results. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
organism_strain, matching_genes, total_rows, rows_by_status, median_abs_log2fc, max_abs_log2fc, experiment_count, rows_by_treatment_type, top_categories, experiments, not_found, no_expression, returned, truncated, results
```

- **organism_strain** (string): Single organism for all results (e.g. 'Alteromonas macleodii HOT1A3')
- **matching_genes** (int): Distinct genes in results after filters (e.g. 5)
- **total_rows** (int): Total gene x experiment x timepoint rows matching filters (e.g. 15)
- **rows_by_status** (ExpressionStatusBreakdown): Row counts by expression_status across all results
- **median_abs_log2fc** (float | None): Median |log2FC| for significant rows only (e.g. 1.978). Null if no significant rows.
- **max_abs_log2fc** (float | None): Max |log2FC| for significant rows only (e.g. 3.591). Null if no significant rows.
- **experiment_count** (int): Number of experiments in results (e.g. 1)
- **rows_by_treatment_type** (object): Row counts by treatment type (e.g. {'nitrogen_stress': 15})
- **top_categories** (list[ExpressionTopCategory]): Top gene categories by significant gene count, max 5
- **experiments** (list[ExpressionByExperiment]): Per-experiment summary with nested timepoint breakdown, sorted by significant row count desc
- **not_found** (list[string]): Input locus_tags not found in KG
- **no_expression** (list[string]): Locus tags in KG but with no expression data matching filters
- **returned** (int): Rows in results (e.g. 5)
- **truncated** (bool): True if total_rows > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'ACZ81_01830') |
| gene_name | string \| None | Gene name (e.g. 'amtB'). Null if unannotated. |
| experiment_id | string | Experiment ID (e.g. '10.1101/2025.11.24.690089_...') |
| treatment_type | string | Treatment type from experiment (e.g. 'nitrogen_stress') |
| timepoint | string \| None | Timepoint label (e.g. 'days 60+89'). Null when edge has no label. |
| timepoint_hours | float \| None | Numeric hours (e.g. 432.0). Null for non-numeric labels. |
| timepoint_order | int | Sort key for time course order (e.g. 3) |
| log2fc | float | Log2 fold change (e.g. 3.591). Positive = up. |
| padj | float \| None | Adjusted p-value (e.g. 1.13e-12). Null if not computed. |
| rank | int | Rank by |log2FC| within experiment x timepoint; 1 = strongest (e.g. 77) |
| expression_status | string ('significant_up', 'significant_down', 'not_significant') | Significance call using publication-specific threshold (e.g. 'significant_up') |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| product | string \| None (optional) | Gene product description (e.g. 'Ammonium transporter') |
| experiment_name | string \| None (optional) | Human-readable experiment name |
| treatment | string \| None (optional) | Treatment details (e.g. 'PRO99-lowN nutrient starvation') |
| gene_category | string \| None (optional) | Gene functional category (e.g. 'Inorganic ion transport') |
| omics_type | string \| None (optional) | Omics type (e.g. 'RNASEQ') |
| coculture_partner | string \| None (optional) | Coculture partner organism, if applicable |

## Few-shot examples

### Example 1: Organism overview (summary only)

```example-call
differential_expression_by_gene(organism="MED4", summary=True)
```

```example-response
{"organism_strain": "Prochlorococcus marinus subsp. pastoris str. CCMP1986", "matching_genes": 1875, "total_rows": 47237, "rows_by_status": {"significant_up": 8460, "significant_down": 7296, "not_significant": 31481}, "median_abs_log2fc": 1.2, "max_abs_log2fc": 12.3, "experiment_count": 47, "rows_by_treatment_type": {"coculture": 15000, "nitrogen_stress": 8000, ...}, "top_categories": [{"category": "Photosynthesis", "total_genes": 42, "significant_genes": 38}], "experiments": [...], "not_found": [], "no_expression": [], "returned": 0, "truncated": true, "results": []}
```

### Example 2: Top responders in an organism

```example-call
differential_expression_by_gene(organism="HOT1A3", significant_only=True, limit=10)
```

### Example 3: Gene expression profile across conditions

```example-call
differential_expression_by_gene(locus_tags=["PMM0001"], limit=20)
```

### Example 4: Batch genes in a specific experiment

```example-call
differential_expression_by_gene(locus_tags=["ACZ81_01830", "ACZ81_15555"], experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_hot1a3_rnaseq_axenic"], limit=20)
```

```example-response
{"organism_strain": "Alteromonas macleodii HOT1A3", "matching_genes": 2, "total_rows": 6, "rows_by_status": {"significant_up": 2, "significant_down": 0, "not_significant": 4}, "median_abs_log2fc": 2.78, "max_abs_log2fc": 3.591, "experiment_count": 1, "rows_by_treatment_type": {"nutrient_starvation": 6}, "top_categories": [{"category": "Inorganic ion transport", "total_genes": 1, "significant_genes": 1}, {"category": "Signal transduction", "total_genes": 1, "significant_genes": 1}], "experiments": [{"experiment_id": "10.1101/...", "experiment_name": "HOT1A3 PRO99-lowN nutrient starvation (RNASEQ)", "treatment_type": "nutrient_starvation", "omics_type": "RNASEQ", "coculture_partner": null, "is_time_course": "true", "matching_genes": 2, "rows_by_status": {"significant_up": 2, "significant_down": 0, "not_significant": 4}, "timepoints": [{"timepoint": "day 18", "timepoint_hours": 432.0, "timepoint_order": 1, "matching_genes": 2, "rows_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 2}}]}], "not_found": [], "no_expression": [], "returned": 5, "truncated": true, "results": [{"locus_tag": "ACZ81_01830", "gene_name": "amtB", "experiment_id": "...", "treatment_type": "nutrient_starvation", "timepoint": "days 60+89", "timepoint_hours": null, "timepoint_order": 3, "log2fc": 3.591, "padj": 1.13e-12, "rank": 77, "expression_status": "significant_up"}]}
```

### Example 5: Chaining — find genes then check expression

```
Step 1: genes_by_function(search_text="nitrogen transport", organism="HOT1A3")
        → collect locus_tags from results

Step 2: differential_expression_by_gene(locus_tags=["ACZ81_01830", ...], summary=True)
        → check rows_by_status for significant hits

Step 3: differential_expression_by_gene(locus_tags=["ACZ81_01830", ...], significant_only=True, limit=20)
        → get the significant expression rows
```

## Chaining patterns

```
genes_by_function → differential_expression_by_gene
genes_by_ontology → differential_expression_by_gene
gene_overview → differential_expression_by_gene (check expression_edge_count first)
list_experiments → differential_expression_by_gene (use experiment_ids)
```

## Common mistakes

```mistake
Interpreting absence of a row as 'no change' when truncated=true
```

```correction
Check truncated flag; use summary=True for reliable counts or increase limit
```

```mistake
Assuming no_expression means 'not differentially expressed'
```

```correction
no_expression means no data available — gene may not have been profiled in those experiments
```

```mistake
Mixing organisms in a single call (e.g. MED4 + HOT1A3 locus_tags)
```

```correction
Call once per organism — tool enforces single-organism constraint
```

- expression_status uses publication-specific thresholds, not a uniform padj<0.05

- Use summary=True first to see the landscape, then drill into specific genes/experiments

## Package import equivalent

```python
from multiomics_explorer import differential_expression_by_gene

result = differential_expression_by_gene()
# returns dict with keys: organism_strain, matching_genes, total_rows, rows_by_status, median_abs_log2fc, max_abs_log2fc, experiment_count, rows_by_treatment_type, top_categories, experiments, not_found, no_expression, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
