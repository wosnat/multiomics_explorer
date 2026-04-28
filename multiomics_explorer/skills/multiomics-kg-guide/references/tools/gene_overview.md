# gene_overview

## What it does

Get an overview of genes: identity and data availability signals.

Use after resolve_gene, genes_by_function, genes_by_ontology, or
gene_homologs to understand what each gene is and what follow-up
data exists.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845']. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include gene_summary, function_description, all_identifiers. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

## Response format

### Envelope

```expected-keys
total_matching, by_organism, by_category, by_annotation_type, has_expression, has_significant_expression, has_orthologs, has_clusters, has_derived_metrics, returned, offset, truncated, not_found, results
```

- **total_matching** (int): Genes found in KG from input locus_tags
- **by_organism** (list[OverviewOrganismBreakdown]): Gene counts per organism, sorted desc
- **by_category** (list[OverviewCategoryBreakdown]): Gene counts per category, sorted desc
- **by_annotation_type** (list[OverviewAnnotationTypeBreakdown]): Gene counts per annotation type, sorted desc
- **has_expression** (int): Genes with expression data (expression_edge_count > 0)
- **has_significant_expression** (int): Genes with significant DE observations
- **has_orthologs** (int): Genes with ortholog group membership
- **has_clusters** (int): Genes with cluster membership
- **has_derived_metrics** (int): Count of requested locus_tags carrying any DM annotation.
- **returned** (int): Results in this response (0 when summary=true)
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if total_matching > returned
- **not_found** (list[string]): Input locus_tags not in KG

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001') |
| gene_name | string \| None (optional) | Gene name (e.g. 'dnaN') |
| product | string \| None (optional) | Gene product (e.g. 'DNA polymerase III subunit beta') |
| gene_category | string \| None (optional) | Functional category (e.g. 'Replication and repair') |
| annotation_quality | int \| None (optional) | Annotation quality score 0-3 (e.g. 3) |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4') |
| annotation_types | list[string] (optional) | Ontology types with annotations (e.g. ['go_bp', 'ec', 'kegg']) |
| expression_edge_count | int (optional) | Number of expression data points (e.g. 36) |
| significant_up_count | int (optional) | Significant up-regulated DE observations (e.g. 3) |
| significant_down_count | int (optional) | Significant down-regulated DE observations (e.g. 2) |
| closest_ortholog_group_size | int \| None (optional) | Size of tightest ortholog group (e.g. 9) |
| closest_ortholog_genera | list[string] \| None (optional) | Genera in tightest ortholog group (e.g. ['Prochlorococcus', 'Synechococcus']) |
| cluster_membership_count | int (optional) | Number of cluster memberships (e.g. 3) |
| cluster_types | list[string] (optional) | Distinct cluster types (e.g. ['condition_comparison', 'diel']) |
| derived_metric_count | int (optional) | Total DerivedMetric annotations on this gene (sum across numeric/boolean/categorical kinds). |
| derived_metric_value_kinds | list[string] (optional) | Subset of {numeric, boolean, categorical} where this gene has DM annotations. Use to route to genes_by_{kind}_metric drill-downs. |
| numeric_metric_count | int \| None (optional) | Numeric DM count (verbose). |
| boolean_metric_count | int \| None (optional) | Boolean DM count (verbose). |
| categorical_metric_count | int \| None (optional) | Categorical DM count (verbose). |
| numeric_metric_types_observed | list[string] \| None (optional) | Numeric metric_types observed (verbose). |
| boolean_metric_types_observed | list[string] \| None (optional) | Boolean metric_types observed (verbose). |
| categorical_metric_types_observed | list[string] \| None (optional) | Categorical metric_types observed (verbose). |
| compartments_observed | list[string] \| None (optional) | DM compartments observed for this gene (verbose). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| gene_summary | string \| None (optional) | Concatenated summary text (e.g. 'dnaN :: DNA polymerase III subunit beta :: Alternative locus ID') |
| function_description | string \| None (optional) | Curated functional description (e.g. 'Alternative locus ID') |
| all_identifiers | list[string] \| None (optional) | Cross-references: UniProt, CyanorakID, RefSeq, etc. (e.g. ['CK_Pro_MED4_00845', 'Q7V1M0', 'WP_011132479.1']) |

## Few-shot examples

### Example 1: Overview of a single gene

```example-call
gene_overview(locus_tags=["PMM1428"])
```

```example-response
{
  "total_matching": 1,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
  "by_category": [{"category": "Unknown", "count": 1}],
  "by_annotation_type": [{"annotation_type": "go_mf", "count": 1}, ...],
  "has_expression": 1, "has_significant_expression": 1, "has_orthologs": 1, "has_clusters": 1,
  "returned": 1, "truncated": false, "offset": 0, "not_found": [],
  "results": [
    {"locus_tag": "PMM1428", "gene_name": null, "product": "EVE domain protein", "gene_category": "Unknown", "annotation_quality": 3, "organism_name": "Prochlorococcus MED4", "annotation_types": ["go_mf", "pfam", "cog_category", "tigr_role"], "expression_edge_count": 36, "significant_up_count": 3, "significant_down_count": 2, "closest_ortholog_group_size": 9, "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"], "cluster_membership_count": 2, "cluster_types": ["condition_comparison"]}
  ]
}
```

### Example 2: Batch overview with mixed organisms

```example-call
gene_overview(locus_tags=["PMM1428", "EZ55_00275"])
```

### Example 3: Summary only (counts and breakdowns)

```example-call
gene_overview(locus_tags=["PMM0845", "PMM1428", "EZ55_00275"], summary=True)
```

### Example 4: From discovery to overview to details

```
Step 1: genes_by_function(search_text="photosystem")
        → collect locus_tags from results

Step 2: gene_overview(locus_tags=["PMM0845", ...])
        → check which genes have expression data, ontology, orthologs, clusters

Step 3: gene_ontology_terms(locus_tags=["PMM0845"])
        → drill into annotations for genes with rich annotation_types
```

## Chaining patterns

```
resolve_gene → gene_overview
genes_by_function → gene_overview
gene_overview → gene_ontology_terms
gene_overview → gene_homologs
gene_overview → differential_expression_by_gene
gene_overview → gene_clusters_by_gene
```

## Common mistakes

- annotation_types lists which ontology types have data — use gene_ontology_terms to get the actual terms

- expression_edge_count > 0 means expression data exists — use differential_expression_by_gene to explore it

- closest_ortholog_genera shows cross-genus reach — use gene_homologs for full group membership

- cluster_membership_count > 0 means cluster data exists — use gene_clusters_by_gene to explore it

```mistake
gene_overview(locus_tags=['PMM0845'], verbose=True)  # just to see the gene
```

```correction
gene_overview(locus_tags=['PMM0845'])  # verbose only needed for gene_summary text
```

## Package import equivalent

```python
from multiomics_explorer import gene_overview

result = gene_overview(locus_tags=...)
# returns dict with keys: total_matching, by_organism, by_category, by_annotation_type, has_expression, has_significant_expression, has_orthologs, has_clusters, has_derived_metrics, offset, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
