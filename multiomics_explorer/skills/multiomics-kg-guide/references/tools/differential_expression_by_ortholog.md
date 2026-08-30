# differential_expression_by_ortholog

## What it does

Find differential-expression rows framed by ortholog group —
one row per (group × experiment × timepoint), values are gene counts
(members responding), not individual gene rows. Cross-organism by
design. Results sorted by significant gene count.

Each list input (`group_ids`, `organisms`, `experiment_ids`) reports
both `not_found` (input absent from KG) and `not_matched` (in KG but
no expression after filters). Tested-absent semantics depend on the
parent experiment's `table_scope` — `all_detected_genes` keeps
`not_significant` rows; any other scope (`significant_only`,
`significant_any_timepoint`, `filtered_subset`, `top_n`) collapses
tested-absent with not-detected. See `docs://guide/conventions`.

Routing: discover groups via `search_homolog_groups`; group membership
without expression via `genes_by_homolog_group`; per-gene drill-down
via `differential_expression_by_gene`.

Each `organisms` entry is OR-matched (word-based); a genus word
(e.g. 'Alteromonas') matches every strain in that genus.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| group_ids | list[string] | — | Ortholog group IDs (from search_homolog_groups or gene_homologs). E.g. ['cyanorak:CK_00000570']. Bare ids are accepted (e.g. 'CK_00000570', 'COG0592@2') and coerced to canonical (see `resolved_aliases`). |
| organisms | list[string] \| None | None | Organisms, each word-matched as `organism`. Omit for all. |
| experiment_ids | list[string] \| None | None | Filter to these experiments. Get IDs from list_experiments. |
| direction | string ('up', 'down', 'both') \| None | None | Filter by expression direction. `'up'` / `'down'` restrict to one arm. `'both'` is the union of significant up + significant down — functionally identical to `direction=None, significant_only=True`; pick whichever spelling is clearer at the call site. Default `None` is unchanged. |
| significant_only | bool | False | If true, return only statistically significant rows. |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields in docs://tools/{name}. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Response format

### Envelope

```expected-keys
total_matching, matching_genes, matching_groups, experiment_count, median_abs_log2fc, max_abs_log2fc, returned, offset, truncated, by_organism, rows_by_status, rows_by_treatment_type, rows_by_background_factors, rows_by_growth_phase, by_table_scope, top_groups, top_experiments, not_found_groups, not_matched_groups, not_found_organisms, not_matched_organisms, not_found_experiments, not_matched_experiments, resolved_aliases, warnings, results
```

- **total_matching** (int): Gene x experiment x timepoint rows matching all filters
- **matching_genes** (int): Distinct genes with expression
- **matching_groups** (int): Distinct groups with >=1 gene having expression
- **experiment_count** (int): Distinct experiments in results
- **median_abs_log2fc** (float | None): Median |log2FC| for significant rows. Null if none.
- **max_abs_log2fc** (float | None): Max |log2FC| for significant rows. Null if none.
- **returned** (int): Rows in results
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if more results exist than returned
- **by_organism** (list[DEByOrthologOrganismBreakdown]): Rows per organism, sorted by count desc
- **rows_by_status** (object): {significant_up, significant_down, not_significant}
- **rows_by_treatment_type** (object): Row counts by treatment type
- **rows_by_background_factors** (object): Row counts by background factor
- **rows_by_growth_phase** (object): Row counts by growth phase. Growth phase is a timepoint-level condition, not gene-specific.
- **by_table_scope** (object): Row counts by experiment table_scope. `all_detected_genes` keeps tested-absent (`not_significant`) rows; any other scope (`significant_only`, `significant_any_timepoint`, `filtered_subset`, `top_n`) collapses tested-absent with not-detected. See `docs://guide/conventions`.
- **top_groups** (list[DifferentialExpressionByOrthologTopGroup]): Top 5 groups by significant gene count
- **top_experiments** (list[DifferentialExpressionByOrthologTopExperiment]): Top 5 experiments by significant gene count
- **not_found_groups** (list[string]): Input group_ids not found in KG
- **not_matched_groups** (list[string]): Groups that exist but have 0 expression matching filters
- **not_found_organisms** (list[string]): Organism filter values matching zero genes in KG
- **not_matched_organisms** (list[string]): Organisms in KG but with zero expression in groups
- **not_found_experiments** (list[string]): Experiment IDs not found in KG
- **not_matched_experiments** (list[string]): Experiments that exist but have 0 expression edges to group members
- **resolved_aliases** (object): Bare group_ids (e.g. 'CK_00000570', 'COG0592@2') coerced to canonical prefixed form, {input: [canonical]}. Empty when none were coerced.
- **warnings** (list[string]): Advisory diagnostics; empty when clean. Never changes which rows are returned.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| group_id | string | Ortholog group ID (e.g. 'cyanorak:CK_00000570') |
| consensus_gene_name | string \| None | Short gene name (e.g. 'psbB'). Null for hypotheticals. |
| consensus_product | string | Group product description (e.g. 'photosystem II chlorophyll-binding protein CP47') |
| experiment_id | string | Experiment ID |
| treatment_type | list[string] | Treatment categories (e.g. ['nitrogen']) |
| background_factors | list[string] (optional) | Background experimental factors |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4') |
| coculture_partner | string \| None (optional) | Coculture partner organism, if applicable |
| timepoint | string \| None | Timepoint label (e.g. '24h'). Null when edge has no label. |
| timepoint_hours | float \| None | Numeric hours (e.g. 24.0). Null for non-numeric labels. |
| timepoint_order | int | Sort key for time course order (e.g. 3) |
| genes_with_expression | int | Group members with expression at this timepoint |
| total_genes | int | Total group members in this organism (computed) |
| significant_up | int | Genes significantly upregulated |
| significant_down | int | Genes significantly downregulated |
| not_significant | int | Genes not meeting significance threshold |
| growth_phase | string \| None (optional) | Physiological state of the culture at this timepoint (e.g. 'exponential', 'nutrient_limited'). Timepoint-level condition — not gene-specific. |

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

Step 3 (if detail needed): genes_by_homolog_group(group_ids=[...], organisms=["MED4"])
        → member locus_tags per organism, then
        differential_expression_by_gene(locus_tags=[...], experiment_ids=[...])
        once per organism for the per-gene rows (or script it — see
        docs://guide/python_api)
```

## Chaining patterns

```
search_homolog_groups → differential_expression_by_ortholog
gene_homologs → differential_expression_by_ortholog
genes_by_homolog_group (triage) → differential_expression_by_ortholog
differential_expression_by_ortholog → genes_by_homolog_group(organisms=[...]) → differential_expression_by_gene per organism (per-gene detail behind a group × experiment row; loop it in Python per docs://guide/python_api)
```

## Common mistakes

- group_ids must be full IDs with prefix (e.g. 'cyanorak:CK_00000570')

- organisms is a list, not a string — use ['MED4'] not 'MED4'

- This tool does NOT enforce single organism — that is the point

- Results are group × experiment × timepoint (gene counts), not individual genes. For per-gene detail take the group's members from genes_by_homolog_group and call differential_expression_by_gene once per organism (docs://guide/python_api shows the loop).

- Diagnostics are suffixed flat lists: `not_found_groups` / `not_matched_groups`, `not_found_organisms` / `not_matched_organisms`, `not_found_experiments` / `not_matched_experiments`. See docs://guide/conventions for the shared not_found / not_matched semantics.

- treatment_type / background_factors / growth_phase values are LIVE vocabularies read from the KG, not enums: an unknown value (e.g. 'nitrogen_stress' instead of 'nitrogen') returns 0 rows, never an error. Check list_filter_values(filter_type='growth_phase') or list_experiments(summary=True)'s by_treatment_type / by_background_factors rollup before filtering. Current treatment values are short nouns (nitrogen, light, carbon, iron, darkness, phosphorus, salt, viral, coculture, diel, ...); background_factors are light, axenic, coculture, darkness, diel, viral, chemical.

- growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — NOT a gene-specific property

- For cross-experiment summarization patterns see `docs://guide/python_api` (Cross-experiment summarization — covers `response_matrix` for gene × treatment-group pivots and `gene_set_compare` for two-set comparisons).

## Package import equivalent

```python
from multiomics_explorer import differential_expression_by_ortholog

result = differential_expression_by_ortholog(group_ids=...)
# returns dict with keys: total_matching, matching_genes, matching_groups, experiment_count, median_abs_log2fc, max_abs_log2fc, returned, offset, truncated, by_organism, rows_by_status, rows_by_treatment_type, rows_by_background_factors, rows_by_growth_phase, by_table_scope, top_groups, top_experiments, not_found_groups, not_matched_groups, not_found_organisms, not_matched_organisms, not_found_experiments, not_matched_experiments, resolved_aliases, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
