# pathway_enrichment

## What it does

Pathway over-representation analysis from DE results (Fisher + BH).

See docs://analysis/enrichment for methodology and examples.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string | — | Organism (case-insensitive fuzzy match, e.g. 'MED4'). Single-organism enforced. |
| experiment_ids | list[string] | — | Experiments to pull DE from. Get IDs from list_experiments. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite') | — | Ontology for pathway definitions. Run ontology_landscape first to rank by relevance. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'. |
| level | int \| None | None | Hierarchy level (0 = root). At least one of level or term_ids required. |
| term_ids | list[string] \| None | None | Specific term IDs to test. Combines with level to scope rollup. |
| direction | string ('up', 'down', 'both') | both | DE direction(s) to include in gene_sets. |
| significant_only | bool | True | If true, only significant DE rows count as foreground. |
| background | string | table_scope | 'table_scope' (default, per-cluster), 'organism', or explicit locus_tag list. |
| min_gene_set_size | int | 5 | Per-cluster M filter: drop pathways with fewer members in the background. |
| max_gene_set_size | int \| None | 500 | Per-cluster M filter upper bound. None disables. |
| pvalue_cutoff | float | 0.05 | Significance threshold for `p_adjust`. |
| timepoint_filter | list[string] \| None | None | Restrict to these timepoint labels. Useful for 10+ timepoint experiments. |
| growth_phases | list[string] \| None | None | Filter DE results by growth phase(s) before enrichment (case-insensitive). E.g. ['exponential']. |
| summary | bool | False | If true, omit results (envelope only). |
| limit | int | 100 | Max rows returned. Default 100 — top hits by p_adjust globally. |
| offset | int | 0 | Skip N rows before limit. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
organism_name, ontology, level, total_matching, returned, truncated, offset, n_significant, by_experiment, by_direction, by_omics_type, cluster_summary, top_clusters_by_min_padj, top_pathways_by_padj, not_found, not_matched, no_expression, term_validation, clusters_skipped, results
```

- **organism_name** (string): Single organism
- **ontology** (string): Ontology used
- **level** (int | None): Hierarchy level used (or None for term_ids-only)
- **total_matching** (int): Total (cluster x term) rows pre-pagination; equals Fisher tests run
- **returned** (int): Rows in this response
- **truncated** (bool): True when total_matching exceeds offset+returned
- **offset** (int): Pagination offset
- **n_significant** (int): Rows with p_adjust below pvalue_cutoff
- **by_experiment** (list[PathwayEnrichmentByExperiment]): Per-experiment tests + significance
- **by_direction** (list[PathwayEnrichmentByDirection]): Per-direction aggregates
- **by_omics_type** (list[PathwayEnrichmentByOmicsType]): Per-omics-type aggregates
- **cluster_summary** (PathwayEnrichmentClusterSummary): Distribution stats across clusters
- **top_clusters_by_min_padj** (list[PathwayEnrichmentTopCluster]): Top 5 clusters by smallest p_adjust
- **top_pathways_by_padj** (list[PathwayEnrichmentTopPathway]): Top 10 pathways by p_adjust across all clusters
- **not_found** (list[string]): Requested experiment_ids absent from KG
- **not_matched** (list[string]): Experiment IDs found but wrong organism
- **no_expression** (list[string]): Experiments matching organism but with no DE rows
- **term_validation** (PathwayEnrichmentTermValidation): Namespaced passthrough of term_id validation from genes_by_ontology
- **clusters_skipped** (list[PathwayEnrichmentClusterSkipped]): Clusters that produced no rows, with reason

### Per-result fields

| Field | Type | Description |
|---|---|---|
| cluster | string | Cluster key '{experiment_id}|{timepoint}|{direction}' |
| experiment_id | string | Experiment identifier |
| name | string \| None (optional) | Experiment display name |
| timepoint | string | Timepoint label; 'NA' for experiments without timepoints |
| timepoint_hours | float \| None (optional) | Numeric time in hours |
| timepoint_order | int \| None (optional) | Integer ordinal of the timepoint |
| direction | string | Expression direction: 'up' or 'down' |
| omics_type | string \| None (optional) | Experiment omics type (transcriptomics, proteomics, ...) |
| table_scope | string \| None (optional) | Coarse table_scope classifier |
| treatment_type | list[string] \| None (optional) | Treatment-type tags |
| background_factors | list[string] \| None (optional) | Background-condition tags |
| is_time_course | bool \| None (optional) | True for time-course experiments |
| growth_phase | string \| None (optional) | Physiological state of the culture at this timepoint. Timepoint-level, not gene-specific. |
| term_id | string | Ontology term ID |
| term_name | string | Ontology term display name |
| level | int \| None (optional) | Hierarchy depth of the term (0 = root) |
| tree | string \| None (optional) | BRITE tree name (sparse: BRITE only) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: BRITE only) |
| gene_ratio | string | 'k/n' string — DE genes in pathway over total DE genes in cluster (clusterProfiler: GeneRatio) |
| gene_ratio_numeric | float | k/n as float |
| bg_ratio | string | 'M/N' string — pathway members over background size (clusterProfiler: BgRatio) |
| bg_ratio_numeric | float | M/N as float |
| rich_factor | float | k/M — fraction of pathway's background members that are DE (clusterProfiler: RichFactor) |
| fold_enrichment | float | (k/n) / (M/N) — observed over null (clusterProfiler: FoldEnrichment) |
| pvalue | float | Fisher-exact p-value (one-sided enrichment) |
| p_adjust | float | Benjamini-Hochberg FDR within cluster (clusterProfiler: p.adjust) |
| count | int | k — DE genes in pathway (clusterProfiler: Count) |
| bg_count | int | M — pathway members in cluster's background |
| signed_score | float | sign * -log10(p_adjust); sign from direction (up: +, down: -) |

**Optional gene-list fields** (sparse, populated by higher-level callers):

| Field | Type | Description |
|---|---|---|
| foreground_gene_ids | list[string] \| None (optional) | The k DE genes in this pathway (clusterProfiler: geneID split) |
| background_gene_ids | list[string] \| None (optional) | Pathway members in background NOT in DE set (non-overlapping complement) |

## Few-shot examples

### Example 1: Single experiment, default direction=both

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="cyanorak_role", level=1)
```

### Example 2: Multi-experiment compareCluster analog (10 experiments in one call)

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_proteomics_axenic", "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic", "10.1128/spectrum.03275-22_dark_low_glucose_med4_proteomics", "10.1128/spectrum.03275-22_dark_high_glucose_med4_proteomics", "10.1128/spectrum.03275-22_light_low_glucose_med4_proteomics", "10.1128/spectrum.03275-22_light_high_glucose_med4_proteomics", "10.3389/fmicb.2022.1038136_salt_low_salinity_acclimation_28_med4_rnaseq", "10.1038/ismej.2017.88_nitrogen_stress_ndepleted_pro99_medium_med4_rnaseq", "10.1371/journal.pone.0165375_light_stress_constant_dark_med4_rnaseq_dark", "10.1371/journal.pone.0165375_viral_phage_phm2_lysate_med4_rnaseq_light"], ontology="cyanorak_role", level=1)
```

### Example 3: Summary-only (envelope, no rows)

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="cyanorak_role", level=1, summary=True)
```

### Example 4: Scope to specific pathways at a level

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="cyanorak_role", level=1, term_ids=["cyanorak.role:J", "cyanorak.role:K"])
```

### Example 5: BRITE tree-scoped enrichment (transporters)

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="brite", tree="transporters", level=1)
```

### Example 6: From landscape to enrichment

```
Step 1: ontology_landscape(organism="MED4", experiment_ids=[...])
        → pick an (ontology, level) by relevance_rank

Step 2: pathway_enrichment(organism="MED4", experiment_ids=[...], ontology=<picked>, level=<picked>)
        → Fisher ORA results
```

## Chaining patterns

```
ontology_landscape → genes_by_ontology(level=N) → pathway_enrichment
pathway_enrichment → gene_overview
differential_expression_by_gene → pathway_enrichment
```

## Common mistakes

- Default background is `table_scope` (per-experiment quantified set). `'organism'` inflates the denominator and underestimates enrichment. See `docs://analysis/enrichment` for the full methodology note.

- BH correction is per-cluster (experiment × timepoint × direction), NOT across clusters. Cross-experiment FDR is biological replication, not statistical.

- Single-organism enforced. Run separate calls per organism.

- Timepoints aren't comparable across experiments — `T0` in exp1 ≠ `T0` in exp2. That's why there's no `by_timepoint` breakdown.

- For cluster-membership / ortholog-group / custom-list enrichment, use the Python `fisher_ora` primitive (see `docs://analysis/enrichment`). The MCP tool is the DE-wired convenience only. Idiom: `term2gene = to_dataframe(genes_by_ontology(...))` then `fisher_ora(gene_sets, background, term2gene)` — no manual column munging.

- At least one of `level` or `term_ids` must be provided (matches `genes_by_ontology`).

- `min/max_gene_set_size` here means **M** — pathway size within each cluster's background (clusterProfiler semantics). This differs from `ontology_landscape`'s filter, which is organism-scoped. A pathway may be tested in one cluster and dropped in another when `background='table_scope'`.

- For brite enrichment, use `tree` to scope to a single BRITE tree (e.g. `tree='transporters'`). Without `tree`, all-BRITE enrichment is dominated by enzymes (~1,776 terms at level 3). Pick a specific level: `level=1` (BRITE category) or `level=2` (BRITE sub-category) are the most useful. Use `list_filter_values('brite_tree')` to discover trees → `ontology_landscape(ontology='brite', tree=...)` to pick level → `pathway_enrichment(ontology='brite', tree=..., level=...)` for enrichment.

```mistake
pathway_enrichment(..., background='genome')  # not a valid string
```

```correction
pathway_enrichment(..., background='organism')  # or 'table_scope' (default), or a locus_tag list
```

- growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — NOT a gene-specific property

## Package import equivalent

```python
from multiomics_explorer import pathway_enrichment

result = pathway_enrichment(organism=..., experiment_ids=..., ontology=...)
# returns dict with keys: organism_name, ontology, level, total_matching, offset, n_significant, by_experiment, by_direction, by_omics_type, cluster_summary, top_clusters_by_min_padj, top_pathways_by_padj, not_found, not_matched, no_expression, term_validation, clusters_skipped, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
