# differential_expression_by_ortholog

## What it does

Differential expression framed by ortholog groups.

Cross-organism by design — results at group x experiment x timepoint
granularity showing how many group members respond. Gene counts,
not individual genes.

Three list filters — each reports not_found + not_matched:
- group_ids (required): ortholog groups
- organisms: restrict to specific organisms
- experiment_ids: restrict to specific experiments

For group discovery, use search_homolog_groups first.
For group membership without expression, use genes_by_homolog_group.
For per-gene expression, use differential_expression_by_gene.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| group_ids | list[string] | — | Ortholog group IDs (from search_homolog_groups or gene_homologs). E.g. ['cyanorak:CK_00000570']. |
| organisms | list[string] \| None | None | Filter by organisms (case-insensitive substring, OR semantics). E.g. ['MED4', 'MIT9313']. Use list_organisms to see valid values. |
| experiment_ids | list[string] \| None | None | Filter to these experiments. Get IDs from list_experiments. |
| direction | string ('up', 'down') \| None | None | Filter by expression direction. |
| significant_only | bool | False | If true, return only statistically significant rows. |
| verbose | bool | False | Add experiment_name, treatment, omics_type, table_scope, table_scope_detail to each row. |
| limit | int | 5 | Max result rows. |

## Response format

### Envelope

```expected-keys
total_rows, matching_genes, matching_groups, experiment_count, median_abs_log2fc, max_abs_log2fc, returned, truncated, by_organism, rows_by_status, rows_by_treatment_type, by_table_scope, top_groups, top_experiments, not_found_groups, not_matched_groups, not_found_organisms, not_matched_organisms, not_found_experiments, not_matched_experiments, results
```

- **total_rows** (int): Gene x experiment x timepoint rows matching all filters
- **matching_genes** (int): Distinct genes with expression
- **matching_groups** (int): Distinct groups with >=1 gene having expression
- **experiment_count** (int): Distinct experiments in results
- **median_abs_log2fc** (float | None): Median |log2FC| for significant rows. Null if none.
- **max_abs_log2fc** (float | None): Max |log2FC| for significant rows. Null if none.
- **returned** (int): Rows in results
- **truncated** (bool): True if more results exist than returned
- **by_organism** (list[object]): [{organism, count}] — rows per organism, sorted desc
- **rows_by_status** (object): {significant_up, significant_down, not_significant}
- **rows_by_treatment_type** (object): Row counts by treatment type
- **by_table_scope** (object): Row counts by experiment table_scope
- **top_groups** (list[DifferentialExpressionByOrthologTopGroup]): Top 5 groups by significant gene count
- **top_experiments** (list[DifferentialExpressionByOrthologTopExperiment]): Top 5 experiments by significant gene count
- **not_found_groups** (list[string]): Input group_ids not found in KG
- **not_matched_groups** (list[string]): Groups that exist but have 0 expression matching filters
- **not_found_organisms** (list[string]): Organism filter values matching zero genes in KG
- **not_matched_organisms** (list[string]): Organisms in KG but with zero expression in groups
- **not_found_experiments** (list[string]): Experiment IDs not found in KG
- **not_matched_experiments** (list[string]): Experiments that exist but have 0 expression edges to group members

### Per-result fields

| Field | Type | Description |
|---|---|---|
| group_id | string | Ortholog group ID (e.g. 'cyanorak:CK_00000570') |
| consensus_gene_name | string \| None | Short gene name (e.g. 'psbB'). Null for hypotheticals. |
| consensus_product | string | Group product description (e.g. 'photosystem II chlorophyll-binding protein CP47') |
| experiment_id | string | Experiment ID |
| treatment_type | string | Treatment category (e.g. 'nitrogen_limitation') |
| organism_strain | string | Organism (e.g. 'Prochlorococcus MED4') |
| coculture_partner | string \| None (optional) | Coculture partner organism, if applicable |
| timepoint | string \| None | Timepoint label (e.g. '24h'). Null when edge has no label. |
| timepoint_hours | float \| None | Numeric hours (e.g. 24.0). Null for non-numeric labels. |
| timepoint_order | int | Sort key for time course order (e.g. 3) |
| genes_with_expression | int | Group members with expression at this timepoint |
| total_genes | int | Total group members in this organism (computed) |
| significant_up | int | Genes significantly upregulated |
| significant_down | int | Genes significantly downregulated |
| not_significant | int | Genes not meeting significance threshold |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| experiment_name | string \| None (optional) | Human-readable experiment name. Verbose only. |
| treatment | string \| None (optional) | Detailed treatment string. Verbose only. |
| omics_type | string \| None (optional) | Omics type (e.g. 'RNASEQ'). Verbose only. |
| table_scope | string \| None (optional) | What genes the DE table contains. Verbose only. |
| table_scope_detail | string \| None (optional) | Free-text clarification of table_scope. Verbose only. |

## Few-shot examples

### Example 1: Expression across orthologs in a group

```example-call
differential_expression_by_ortholog(group_ids=["cyanorak:CK_00000570"])
```

### Example 2: Compare two groups in specific organisms

```example-call
differential_expression_by_ortholog(group_ids=["cyanorak:CK_00000570", "eggnog:COG0592@2"], organisms=["MED4", "MIT9313"])
```

### Example 3: Full pipeline from text to expression

```
Step 1: search_homolog_groups(search_text="photosystem II")
        → collect group_ids

Step 2: differential_expression_by_ortholog(group_ids=[...],
          organisms=["MED4", "MIT9313"])
        → triage: which groups have expression?

Step 3 (if detail needed): use expression_by_ortholog script
```

## Chaining patterns

```
search_homolog_groups → differential_expression_by_ortholog
gene_homologs → differential_expression_by_ortholog
genes_by_homolog_group (triage) → differential_expression_by_ortholog
differential_expression_by_ortholog → scripts/expression_by_ortholog.py (detail)
```

## Good to know

- group_ids must be full IDs with prefix (e.g. 'cyanorak:CK_00000570')

- organisms is a list, not a string — use ['MED4'] not 'MED4'

- This tool does NOT enforce single organism — that is the point

- Results are group × experiment × timepoint (gene counts), not individual genes. Use the script for per-gene detail.

## Package import equivalent

```python
from multiomics_explorer import differential_expression_by_ortholog

result = differential_expression_by_ortholog(group_ids=...)
# returns dict with keys: total_rows, matching_genes, matching_groups, experiment_count, median_abs_log2fc, max_abs_log2fc, by_organism, rows_by_status, rows_by_treatment_type, by_table_scope, top_groups, top_experiments, not_found_groups, not_matched_groups, not_found_organisms, not_matched_organisms, not_found_experiments, not_matched_experiments, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
