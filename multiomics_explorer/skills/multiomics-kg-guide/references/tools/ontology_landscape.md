# ontology_landscape

## What it does

Rank (ontology x level) combinations by enrichment suitability.

Per-(ontology x level) stats: term-size distribution, genome coverage,
best-effort share (GO). Ranked by coverage x size_factor(median) with
sweet-spot [5, 50] median genes-per-term. Default ontology=None surveys
all 9 ontologies. Pass experiment_ids to weight by coverage of those
experiments' quantified genes. See docs://tools/ontology_landscape.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string | — | Organism (fuzzy match, e.g. 'MED4'). |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite') \| None | None | If None, surveys all 10 ontologies. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'. |
| experiment_ids | list[string] \| None | None | Restrict coverage computation to genes quantified in these experiments. |
| summary | bool | False | If true, omit per-row results (by_ontology only). |
| verbose | bool | False | Include example_terms (top 3 terms per level). |
| limit | int \| None | None | Max rows returned. None (default) returns all rows; set an integer to truncate. |
| offset | int | 0 | Skip N rows before limit |
| min_gene_set_size | int | 5 | Exclude terms with fewer genes than this (default 5). |
| max_gene_set_size | int | 500 | Exclude terms with more genes than this (default 500). |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
organism_name, organism_gene_count, n_ontologies, by_ontology, not_found, not_matched, total_matching, returned, truncated, offset, results
```

- **organism_name** (string)
- **organism_gene_count** (int)
- **n_ontologies** (int)
- **by_ontology** (object)
- **not_found** (list[string])
- **not_matched** (list[string])
- **total_matching** (int)
- **returned** (int)
- **truncated** (bool)
- **offset** (int)

### Per-result fields

| Field | Type | Description |
|---|---|---|
| ontology_type | string | Ontology key (e.g. 'cyanorak_role') |
| level | int | Hierarchy level; 0 = broadest |
| tree | string \| None (optional) | BRITE tree name (sparse: BRITE only) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: BRITE only) |
| relevance_rank | int | 1-indexed rank by spec_score; stable under pagination |
| n_terms_with_genes | int |  |
| n_genes_at_level | int |  |
| genome_coverage | float | n_genes_at_level / organism_gene_count |
| min_genes_per_term | int |  |
| q1_genes_per_term | float |  |
| median_genes_per_term | float |  |
| q3_genes_per_term | float |  |
| max_genes_per_term | int |  |
| n_levels_in_ontology | int | Levels this ontology spans (1 = flat) |
| best_effort_share | float \| None (optional) | Fraction of reached terms flagged level_is_best_effort (GO only; None for others) |
| min_exp_coverage | float \| None (optional) |  |
| median_exp_coverage | float \| None (optional) |  |
| max_exp_coverage | float \| None (optional) |  |
| n_experiments_with_coverage | int \| None (optional) |  |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| example_terms | list[ExampleTerm] \| None (optional) | Top 3 terms by gene count (verbose only) |

## Few-shot examples

### Example 1: Default survey — which ontology/level should I use for MED4?

```example-call
ontology_landscape(organism="MED4")
```

```example-response
{"organism_name": "Prochlorococcus MED4", "organism_gene_count": 1976, "n_ontologies": 9, "by_ontology": {"tigr_role": {"best_level": 0, "best_genome_coverage": 0.893, "best_relevance_rank": 1, "n_levels": 1}, "cyanorak_role": {"best_level": 1, "best_genome_coverage": 0.755, "best_relevance_rank": 2, "n_levels": 3}}, "results": [{"ontology_type": "tigr_role", "level": 0, "relevance_rank": 1, "genome_coverage": 0.893, "median_genes_per_term": 9.0, "n_levels_in_ontology": 1}]}
```

### Example 2: Drill into a specific ontology

```example-call
ontology_landscape(organism="MED4", ontology="go_bp", verbose=True)
```

```example-response
{"organism_name": "Prochlorococcus MED4", "n_ontologies": 1, "results": [{"ontology_type": "go_bp", "level": 2, "relevance_rank": 1, "example_terms": [{"term_id": "go:0044238", "name": "primary metabolic process", "n_genes": 657}]}]}
```

### Example 3: BRITE landscape scoped to a specific tree

```example-call
ontology_landscape(organism="MED4", ontology="brite", tree="transporters")
```

### Example 4: Weight by experiments (coverage of quantified genes)

```
Step 1: list_experiments(organism="MED4", table_scope=["all_detected_genes"])
        -> collect experiment_ids

Step 2: ontology_landscape(
          organism="MED4",
          experiment_ids=[ids from Step 1],
        )
        -> rows ranked by median_exp_coverage x size_factor;
           min_exp_coverage and max_exp_coverage reveal per-experiment spread
```

## Chaining patterns

```
ontology_landscape -> genes_by_ontology(level=N) -> pathway_enrichment (Phase 2)
list_experiments -> ontology_landscape(experiment_ids=...)
```

## Common mistakes

- Don't pick a level by term-size stats alone -- always check genome_coverage. An ontology may have appealing median term size at a level that covers only 18% of the genome.

- Top-ranked flat ontologies (tigr_role, cog_category, pfam) are valid enrichment surfaces but offer no level choice. For hierarchical drill-down, filter results to rows where n_levels_in_ontology > 1.

- KEGG has ~40% orphan KOs lacking pathway membership. If L3 coverage is substantially higher than L0-L2 coverage, the gap is structural -- those genes have KO-level annotations only.

- For GO BP, best_effort_share is typically 30-80% at useful levels (L3-L5). This is normal GO-DAG geometry (min-path != max-path), not a data quality issue.

- Stats reflect only terms with min_gene_set_size <= genes <= max_gene_set_size (default 5-500). If you pass min_gene_set_size=1, coverage and term counts will be higher but include terms too small or large for meaningful enrichment.

```mistake
results[0]['rank']  # AttributeError
```

```correction
results[0]['relevance_rank']
```

- BRITE stats at each level mix all trees together by default. Use `tree` to scope to a single BRITE tree (e.g. `tree='transporters'`). BRITE rows are broken down per tree when `tree` is specified. Use `list_filter_values('brite_tree')` to discover available trees.

```mistake
result['total_rows']  # KeyError
```

```correction
result['total_matching']
```

- Default `limit=None` returns all rows; if you set an explicit integer, check the response envelope's `truncated` field to know whether more rows exist beyond what was returned.

## Package import equivalent

```python
from multiomics_explorer import ontology_landscape

result = ontology_landscape(organism=...)
# returns dict with keys: organism_name, organism_gene_count, n_ontologies, by_ontology, not_found, not_matched, total_matching, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
