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
| treatment_types | list[string] \| None | None | Filter to specific treatment types (e.g. ['nitrogen', 'coculture']). Live vocabulary: list_filter_values(filter_type='treatment_type') or list_experiments(summary=True). |
| background_factors | list[string] \| None | None | Filter by background experimental factors (case-insensitive exact match). E.g. ['axenic', 'diel']. |
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
{
  "organism_name": "Prochlorococcus MED4",
  "genes_queried": 2,
  "genes_with_response": 2,
  "not_found": [],
  "no_expression": [],
  "returned": 2,
  "offset": 0,
  "truncated": false,
  "results": [
    {
      "locus_tag": "PMM0370",
      "gene_name": "cynA",
      "product": "cyanate ABC transporter, substrate-binding protein",
      "gene_category": "Central intermediary metabolism",
      "groups_responded": ["carbon", "coculture", "darkness", "iron", "nitrogen"],
      "groups_not_responded": ["light", "salt"],
      "groups_tested_not_responded": ["viral"],
      "groups_not_known": ["phosphorus"],
      "response_summary": {
        "carbon": {
          "experiments_total": 8,
          "experiments_tested": 2,
          "experiments_up": 0,
          "experiments_down": 2,
          "timepoints_total": 8,
          "timepoints_tested": 2,
          "timepoints_up": 0,
          "timepoints_down": 2,
          "up_best_rank": null,
          "up_median_rank": null,
          "up_max_log2fc": null,
          "down_best_rank": 121,
          "down_median_rank": 122.5,
          "down_max_log2fc": -1.1
        },
        "coculture": {
          "experiments_total": 2,
          "experiments_tested": 2,
          "experiments_up": 1,
          "experiments_down": 1,
          "timepoints_total": 3,
          "timepoints_tested": 3,
          "timepoints_up": 1,
          "timepoints_down": 1,
          "up_best_rank": 13,
          "up_median_rank": 13.0,
          "up_max_log2fc": 3.1049891422154707,
          "down_best_rank": 65,
          "down_median_rank": 65.0,
          "down_max_log2fc": -2.189091416993404
        },
        "darkness": {
          "experiments_total": 1,
          "experiments_tested": 1,
          "experiments_up": 1,
          "experiments_down": 0,
          "timepoints_total": 2,
          "timepoints_tested": 2,
          "timepoints_up": 1,
          "timepoints_down": 0,
          "up_best_rank": 147,
          "up_median_rank": 147.0,
          "up_max_log2fc": 1.6108981,
          "down_best_rank": null,
          "down_median_rank": null,
          "down_max_log2fc": null
        },
        "iron": {
          "experiments_total": 3,
          "experiments_tested": 3,
          "experiments_up": 2,
          "experiments_down": 1,
          "timepoints_total": 4,
          "timepoints_tested": 4,
          "timepoints_up": 2,
          "timepoints_down": 1,
          "up_best_rank": 50,
          "up_median_rank": 52.5,
          "up_max_log2fc": 0.75,
          "down_best_rank": 50,
          "down_median_rank": 50.0,
          "down_max_log2fc": -1.1
        },
        "light": {
          "experiments_total": 11,
          "experiments_tested": 1,
          "experiments_up": 0,
          "experiments_down": 0,
          "timepoints_total": 19,
          "timepoints_tested": 2,
          "timepoints_up": 0,
          "timepoints_down": 0,
          "up_best_rank": null,
          "up_median_rank": null,
          "up_max_log2fc": null,
          "down_best_rank": null,
          "down_median_rank": null,
          "down_max_log2fc": null
        },
        "nitrogen": {
          "experiments_total": 8,
          "experiments_tested": 8,
          "experiments_up": 6,
          "experiments_down": 0,
          "timepoints_total": 26,
          "timepoints_tested": 26,
          "timepoints_up": 16,
          "timepoints_down": 0,
          "up_best_rank": 1,
          "up_median_rank": 5.0,
          "up_max_log2fc": 5.7284866494887,
          "down_best_rank": null,
          "down_median_rank": null,
          "down_max_log2fc": null
        },
        "salt": {
          "experiments_total": 1,
          "experiments_tested": 1,
          "experiments_up": 0,
          "experiments_down": 0,
          "timepoints_total": 1,
          "timepoints_tested": 1,
          "timepoints_up": 0,
          "timepoints_down": 0,
          "up_best_rank": null,
          "up_median_rank": null,
          "up_max_log2fc": null,
          "down_best_rank": null,
          "down_median_rank": null,
          "down_max_log2fc": null
        }
      }
    },
    {
      "locus_tag": "PMM0920",
      "gene_name": "glnA",
      "product": "glutamine synthetase, type I",
      "gene_category": "Amino acid metabolism",
      "groups_responded": ["carbon", "coculture", "darkness", "light", "nitrogen"],
      "groups_not_responded": ["salt"],
      "groups_tested_not_responded": ["viral", "iron"],
      "groups_not_known": ["phosphorus"],
      "response_summary": {
        "carbon": {
          "experiments_total": 8,
          "experiments_tested": 7,
          "experiments_up": 1,
          "experiments_down": 2,
          "timepoints_total": 8,
          "timepoints_tested": 7,
          "timepoints_up": 1,
          "timepoints_down": 2,
          "up_best_rank": 94,
          "up_median_rank": 94.0,
          "up_max_log2fc": 0.7,
          "down_best_rank": 115,
          "down_median_rank": 153.5,
          "down_max_log2fc": -1.1
        },
        "coculture": {
          "experiments_total": 2,
          "experiments_tested": 2,
          "experiments_up": 1,
          "experiments_down": 1,
          "timepoints_total": 3,
          "timepoints_tested": 3,
          "timepoints_up": 1,
          "timepoints_down": 1,
          "up_best_rank": 24,
          "up_median_rank": 24.0,
          "up_max_log2fc": 2.4390669451712435,
          "down_best_rank": 268,
          "down_median_rank": 268.0,
          "down_max_log2fc": -2.79260227
        },
        "darkness": {
          "experiments_total": 1,
          "experiments_tested": 1,
          "experiments_up": 1,
          "experiments_down": 0,
          "timepoints_total": 2,
          "timepoints_tested": 2,
          "timepoints_up": 1,
          "timepoints_down": 0,
          "up_best_rank": 274,
          "up_median_rank": 274.0,
          "up_max_log2fc": 1.10213906,
          "down_best_rank": null,
          "down_median_rank": null,
          "down_max_log2fc": null
        },
        "light": {
          "experiments_total": 11,
          "experiments_tested": 4,
          "experiments_up": 0,
          "experiments_down": 1,
          "timepoints_total": 19,
          "timepoints_tested": 5,
          "timepoints_up": 0,
          "timepoints_down": 1,
          "up_best_rank": null,
          "up_median_rank": null,
          "up_max_log2fc": null,
          "down_best_rank": 20,
          "down_median_rank": 20.0,
          "down_max_log2fc": -1.665
        },
        "nitrogen": {
          "experiments_total": 8,
          "experiments_tested": 8,
          "experiments_up": 6,
          "experiments_down": 1,
          "timepoints_total": 26,
          "timepoints_tested": 26,
          "timepoints_up": 17,
          "timepoints_down": 2,
          "up_best_rank": 2,
          "up_median_rank": 9.0,
          "up_max_log2fc": 5.06051169137151,
          "down_best_rank": 31,
          "down_median_rank": 40.5,
          "down_max_log2fc": -2.173486157594152
        },
        "salt": {
          "experiments_total": 1,
          "experiments_tested": 1,
          "experiments_up": 0,
          "experiments_down": 0,
          "timepoints_total": 1,
          "timepoints_tested": 1,
          "timepoints_up": 0,
          "timepoints_down": 0,
          "up_best_rank": null,
          "up_median_rank": null,
          "up_max_log2fc": null,
          "down_best_rank": null,
          "down_median_rank": null,
          "down_max_log2fc": null
        }
      }
    }
  ]
}
```

### Example 2: Filter by treatment type

```example-call
gene_response_profile(locus_tags=["PMM0370"], treatment_types=["nitrogen", "coculture"])
```

*treatment_types values come from the live treatment_type vocabulary ('nitrogen', 'light', 'coculture', ...) — an unknown value silently yields no group, not an error.*

### Example 3: Read the four group buckets (incl. groups_tested_not_responded)

```example-call
gene_response_profile(locus_tags=["PMM0370"])
```

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "genes_queried": 1,
  "genes_with_response": 1,
  "not_found": [],
  "no_expression": [],
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "results": [
    {
      "locus_tag": "PMM0370",
      "gene_name": "cynA",
      "product": "cyanate ABC transporter, substrate-binding protein",
      "gene_category": "Central intermediary metabolism",
      "groups_responded": ["carbon", "coculture", "darkness", "iron", "nitrogen"],
      "groups_not_responded": ["light", "salt"],
      "groups_tested_not_responded": ["viral"],
      "groups_not_known": ["phosphorus"],
      "response_summary": {
        "carbon": {
          "experiments_total": 8,
          "experiments_tested": 2,
          "experiments_up": 0,
          "experiments_down": 2,
          "timepoints_total": 8,
          "timepoints_tested": 2,
          "timepoints_up": 0,
          "timepoints_down": 2,
          "up_best_rank": null,
          "up_median_rank": null,
          "up_max_log2fc": null,
          "down_best_rank": 121,
          "down_median_rank": 122.5,
          "down_max_log2fc": -1.1
        },
        "coculture": {
          "experiments_total": 2,
          "experiments_tested": 2,
          "experiments_up": 1,
          "experiments_down": 1,
          "timepoints_total": 3,
          "timepoints_tested": 3,
          "timepoints_up": 1,
          "timepoints_down": 1,
          "up_best_rank": 13,
          "up_median_rank": 13.0,
          "up_max_log2fc": 3.1049891422154707,
          "down_best_rank": 65,
          "down_median_rank": 65.0,
          "down_max_log2fc": -2.189091416993404
        },
        "darkness": {
          "experiments_total": 1,
          "experiments_tested": 1,
          "experiments_up": 1,
          "experiments_down": 0,
          "timepoints_total": 2,
          "timepoints_tested": 2,
          "timepoints_up": 1,
          "timepoints_down": 0,
          "up_best_rank": 147,
          "up_median_rank": 147.0,
          "up_max_log2fc": 1.6108981,
          "down_best_rank": null,
          "down_median_rank": null,
          "down_max_log2fc": null
        },
        "iron": {
          "experiments_total": 3,
          "experiments_tested": 3,
          "experiments_up": 2,
          "experiments_down": 1,
          "timepoints_total": 4,
          "timepoints_tested": 4,
          "timepoints_up": 2,
          "timepoints_down": 1,
          "up_best_rank": 50,
          "up_median_rank": 52.5,
          "up_max_log2fc": 0.75,
          "down_best_rank": 50,
          "down_median_rank": 50.0,
          "down_max_log2fc": -1.1
        },
        "light": {
          "experiments_total": 11,
          "experiments_tested": 1,
          "experiments_up": 0,
          "experiments_down": 0,
          "timepoints_total": 19,
          "timepoints_tested": 2,
          "timepoints_up": 0,
          "timepoints_down": 0,
          "up_best_rank": null,
          "up_median_rank": null,
          "up_max_log2fc": null,
          "down_best_rank": null,
          "down_median_rank": null,
          "down_max_log2fc": null
        },
        "nitrogen": {
          "experiments_total": 8,
          "experiments_tested": 8,
          "experiments_up": 6,
          "experiments_down": 0,
          "timepoints_total": 26,
          "timepoints_tested": 26,
          "timepoints_up": 16,
          "timepoints_down": 0,
          "up_best_rank": 1,
          "up_median_rank": 5.0,
          "up_max_log2fc": 5.7284866494887,
          "down_best_rank": null,
          "down_median_rank": null,
          "down_max_log2fc": null
        },
        "salt": {
          "experiments_total": 1,
          "experiments_tested": 1,
          "experiments_up": 0,
          "experiments_down": 0,
          "timepoints_total": 1,
          "timepoints_tested": 1,
          "timepoints_up": 0,
          "timepoints_down": 0,
          "up_best_rank": null,
          "up_median_rank": null,
          "up_max_log2fc": null,
          "down_best_rank": null,
          "down_median_rank": null,
          "down_max_log2fc": null
        }
      }
    }
  ]
}
```

### Example 4: Per-experiment breakdown

```example-call
gene_response_profile(locus_tags=["PMM0370"], group_by="experiment")
```

### Example 5: Chaining — find responsive genes then profile them

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

- Sibling tools: gene_response_profile is the cross-experiment ROLLUP (one row per gene, responses bucketed per treatment group, timepoints collapsed). differential_expression_by_gene is the row-level view (gene × experiment × timepoint with log2fc / padj). Profile first to see which treatments matter, then drill into one experiment with differential_expression_by_gene.

```mistake
Assuming groups_not_known means 'gene does not respond to this treatment'
```

```correction
groups_not_known means no expression data exists — the gene was not profiled or not reported for that treatment. Check experiments_total in the response_summary for coverage. groups_tested_not_responded is the stronger 'absent but inferred-tested' bucket (all experiments in the group report a full-coverage scope).
```

- treatment_type / background_factors / growth_phase values are LIVE vocabularies read from the KG, not enums: an unknown value (e.g. 'nitrogen_stress' instead of 'nitrogen') returns 0 rows, never an error. Check list_filter_values(filter_type='growth_phase') or list_experiments(summary=True)'s by_treatment_type / by_background_factors rollup before filtering. Current treatment values are short nouns (nitrogen, light, carbon, iron, darkness, phosphorus, salt, viral, coculture, diel, ...); background_factors are light, axenic, coculture, darkness, diel, viral, chemical. Here the group keys of response_summary and the treatment_types filter use those values.

- `no_expression` is this tool's name for the not_matched bucket (gene exists, no expression edges at all); `not_found` = locus_tag absent. See docs://guide/conventions for the shared not_found / not_matched semantics.

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
# returns dict with keys: organism_name, genes_queried, genes_with_response, not_found, no_expression, returned, offset, truncated, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
