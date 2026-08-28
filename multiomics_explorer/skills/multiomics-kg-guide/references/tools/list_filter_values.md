# list_filter_values

## What it does

Enumerate valid values + counts for a categorical filter (gene_category, brite_tree, growth_phase, metric_type, value_kind, compartment, omics_type, evidence_source, cluster_type, plus the annotation-trust types).

`cluster_type` enumerates the closed ClusteringAnalysis.cluster_type
vocabulary from ControlledVocabulary (source='vocabulary'; falls back
to a pivot over ClusteringAnalysis nodes with a warning) — the live
source for the `cluster_type` filter on `list_clustering_analyses` /
`gene_clusters_by_gene`.

[TRUST] evidence / sources / call_class / interpro_type /
ncbifam_family_type / merops_catalytic_type / merops_family_class /
best_hit_kind / pfam_support / attachment_depth / trust_axes /
link_kinds enumerate the per-edge trust vocabulary. See
docs://analysis/annotation_evidence.

Routing: feed the returned `value`s into the corresponding filter on the relevant tool — `gene_category` → `genes_by_function(category=...)`; `brite_tree` → `ontology_landscape(tree=...)` / `pathway_enrichment(tree=...)`; `compartment` → `list_experiments` / `list_organisms` / `list_publications`; `metric_type` / `value_kind` → `list_derived_metrics` and `genes_by_{kind}_metric`; `omics_type` → `list_experiments(omics_type=...)`; `evidence_source` → `list_metabolites(evidence_sources=[...])`; the trust types → `sources` / `evidence` / `call_class` / `interpro_type` on `genes_by_ontology` and friends.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| filter_type | string ('gene_category', 'brite_tree', 'growth_phase', 'metric_type', 'value_kind', 'compartment', 'omics_type', 'evidence_source', 'evidence', 'sources', 'call_class', 'interpro_type', 'ncbifam_family_type', 'merops_catalytic_type', 'merops_family_class', 'best_hit_kind', 'pfam_support', 'attachment_depth', 'trust_axes', 'link_kinds', 'cluster_type') | gene_category | Which filter to enumerate: gene/expression (gene_category, brite_tree, growth_phase, omics_type, cluster_type), DerivedMetric (metric_type, value_kind, compartment), chemistry (evidence_source), or an annotation-trust vocabulary. |
| ontology | string \| None | None | Scope a trust filter_type (e.g. 'trust_axes') to one ontology key. Ignored on non-trust filter types. |

## Response format

### Envelope

```expected-keys
filter_type, description, total_entries, returned, truncated, warnings, results
```

- **filter_type** (string): The filter type returned (e.g. 'gene_category').
- **description** (string | None): Vocabulary-level description of the property behind this filter (ControlledVocabulary text; cluster_type and the trust types). Emitted once here, not per row. None elsewhere.
- **total_entries** (int): Total distinct values for this filter.
- **returned** (int): Number of results returned.
- **truncated** (bool): True if total_entries > returned.
- **warnings** (list[string]): E.g. a KG-side ControlledVocabulary-missing notice when a trust filter_type fell back to the pivot query.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| value | string | Filter value (e.g. 'Photosynthesis', 'Transport', 'Unknown'). |
| count | int \| None (optional) | Number of items with this value. None on trust filter types (ControlledVocabulary/pivot rows carry no per-value graph count). |
| tree_code | string \| None (optional) | BRITE tree code (sparse: only for brite_tree filter, e.g. 'ko01000'). |
| source | string \| None (optional) | Provenance of this value (sparse: trust filter types only): 'vocabulary' (from ControlledVocabulary) or 'pivot' (KG-side vocab node missing; derived from the graph, see envelope warnings). |
| applies_to | list[string] \| None (optional) | Edge/node type(s) this value is scoped to (sparse: trust filter types only), e.g. ['Gene_has_merops_family']. |
| description | string \| None (optional) | Human-readable meaning of this value (sparse: trust filter types only, from ControlledVocabulary). |

### Filter-type families

`filter_type` values fall into four families. Gene / expression:
`gene_category` (Gene.category, counts summed across organisms),
`brite_tree` (BRITE tree names + `tree_code`; count = terms, not
genes), `growth_phase` (timepoint-level culture state), `omics_type`
(the full canonical enum incl. METABOLOMICS), `cluster_type`
(ClusteringAnalysis.cluster_type from ControlledVocabulary, pivot
fallback + warning). DerivedMetric: `metric_type`, `value_kind`
(`numeric` / `boolean` / `categorical`), `compartment` (wet-lab
fraction). Chemistry: `evidence_source` (Metabolite.evidence_sources
values). Annotation-trust: `evidence`, `sources`, `call_class`,
`interpro_type`, `ncbifam_family_type`, `merops_catalytic_type`,
`merops_family_class`, `best_hit_kind`, `pfam_support`,
`attachment_depth` read ControlledVocabulary (pivot fallback + warning
when the node is missing); `trust_axes` / `link_kinds` are
config-derived and accept `ontology=` to scope. See
docs://analysis/annotation_evidence.


## Few-shot examples

### Example 1: List gene categories

```example-call
list_filter_values(filter_type="gene_category")
```

```example-response
{
  "filter_type": "gene_category",
  "total_entries": 26,
  "returned": 26,
  "truncated": false,
  "results": [
    {"value": "Unknown", "count": 12183},
    {"value": "Coenzyme metabolism", "count": 2146},
    {"value": "Stress response and adaptation", "count": 2073}
  ]
}
```

### Example 2: List BRITE trees

```example-call
list_filter_values(filter_type="brite_tree")
```

```example-response
{
  "filter_type": "brite_tree",
  "total_entries": 12,
  "returned": 12,
  "truncated": false,
  "results": [
    {"value": "enzymes", "tree_code": "ko01000", "count": 1776},
    {"value": "transporters", "tree_code": "ko02000", "count": 84},
    {"value": "protein families: signaling and cellular processes", "tree_code": "ko04131", "count": 150}
  ]
}
```

### Example 3: Find genes in a category

```
Step 1: list_filter_values(filter_type="gene_category")
        → extract value strings from results

Step 2: genes_by_function(search_text="photosystem", category="Photosynthesis")
        → get photosynthesis genes matching "photosystem"
```

### Example 4: Discover BRITE trees, then scope enrichment

```
Step 1: list_filter_values(filter_type="brite_tree")
        → discover available trees (e.g. "transporters", "enzymes")

Step 2: ontology_landscape(organism="MED4", ontology="brite", tree="transporters")
        → check coverage and pick level

Step 3: pathway_enrichment(organism="MED4", experiment_ids=[...], ontology="brite", tree="transporters", level=1)
        → run enrichment scoped to transporter categories
```

### Example 5: Discover available DerivedMetric tags

```example-call
list_filter_values(filter_type="metric_type")
```

```example-response
{"filter_type": "metric_type", "total_entries": 26, "returned": 26, "truncated": false,
 "results": [
   {"value": "cell_abundance_biovolume_normalized", "count": 2},
   {"value": "log2_vesicle_cell_enrichment", "count": 2},
   {"value": "mascot_identification_probability", "count": 2}
 ]}
```

### Example 6: Enumerate DerivedMetric value kinds

```example-call
list_filter_values(filter_type="value_kind")
```

```example-response
{"filter_type": "value_kind", "total_entries": 3, "returned": 3, "truncated": false,
 "results": [
   {"value": "boolean", "count": 16},
   {"value": "numeric", "count": 15},
   {"value": "categorical", "count": 3}
 ]}
```

### Example 7: List wet-lab compartments (for compartment filter)

```example-call
list_filter_values(filter_type="compartment")
```

```example-response
{"filter_type": "compartment", "total_entries": 3, "returned": 3, "truncated": false,
 "results": [
   {"value": "whole_cell", "count": 160},
   {"value": "exoproteome", "count": 7},
   {"value": "vesicle", "count": 5}
 ]}
```

### Example 8: Enumerate omics types (for experiment / publication filtering)

```example-call
list_filter_values(filter_type="omics_type")
```

```example-response
{"filter_type": "omics_type", "total_entries": 8, "returned": 8, "truncated": false,
 "results": [
   {"value": "EXOPROTEOMICS", "count": 8},
   {"value": "METABOLOMICS", "count": 8},
   {"value": "MICROARRAY", "count": 26},
   {"value": "PAIRED_RNASEQ_PROTEOME", "count": 1},
   {"value": "PROTEOMICS", "count": 72},
   {"value": "RNASEQ", "count": 63},
   {"value": "VESICLE_DNASEQ", "count": 1},
   {"value": "VESICLE_PROTEOMICS", "count": 10}
 ]}
# Returns the full canonical OMICS_TYPE enum (8 values) in alphabetical
# order. Values absent from current KG data still appear with count=0.
```

### Example 9: Enumerate metabolite evidence sources

```example-call
list_filter_values(filter_type="evidence_source")
```

```example-response
{"filter_type": "evidence_source", "total_entries": 3, "returned": 3, "truncated": false,
 "results": [
   {"value": "metabolism", "count": 2188},
   {"value": "transport", "count": 1355},
   {"value": "metabolomics", "count": 107}
 ]}
```

### Example 10: Enumerate the trust ladder (annotation-trust `evidence` axis)

```example-call
list_filter_values(filter_type="evidence")
```

```example-response
# `evidence` values, ordered by trust: curated > signature > homology >
# family_inferred > domain_inferred. Each row's `applies_to` names the
# gene-edge relationship types that carry the value (14 of the 17
# ontologies carry this axis — PSORTb/SignalP don't). `source` is
# "vocabulary" when read from the KG's ControlledVocabulary node,
# "pivot" when that node is missing and the value set was derived
# live via a fallback query (rare; a warning accompanies pivot rows).
# Trust-vocabulary rows carry no `count` (unlike gene_category /
# evidence_source) — there is no single precomputed cardinality for a
# value that spans several edge types at once.
{"filter_type": "evidence", "total_entries": 5, "returned": 5, "truncated": false,
 "results": [
   {"value": "curated", "applies_to": ["Gene_has_merops_family"], "description": "...", "source": "vocabulary"},
   {"value": "signature", "applies_to": ["Gene_has_interpro_entry", "Gene_has_ncbifam_family"], "description": "...", "source": "vocabulary"},
   {"value": "homology", "applies_to": ["Gene_has_tcdb_family", "Gene_has_merops_family", "Gene_has_pfam"], "description": "...", "source": "vocabulary"},
   {"value": "family_inferred", "applies_to": ["Gene_has_tcdb_family"], "description": "...", "source": "vocabulary"},
   {"value": "domain_inferred", "applies_to": ["Gene_involved_in_biological_process"], "description": "...", "source": "vocabulary"}
 ]}
```

### Example 11: Discover which trust axes an ontology supports

```example-call
list_filter_values(filter_type="trust_axes", ontology="tcdb")
```

```example-response
# trust_axes and link_kinds are config-derived, not KG-vocabulary reads
# — they answer "what filter params work on this ontology" before you
# call genes_by_ontology / pathway_enrichment with a trust filter.
# One row per axis (not one row per ontology) — `applies_to` narrows to
# the ontology you passed.
{"filter_type": "trust_axes", "total_entries": 4, "returned": 4, "truncated": false,
 "results": [
   {"value": "sources", "applies_to": ["tcdb"], "description": "...", "source": "config"},
   {"value": "evidence", "applies_to": ["tcdb"], "description": "...", "source": "config"},
   {"value": "evidence_score", "applies_to": ["tcdb"], "description": "...", "source": "config"},
   {"value": "tier", "applies_to": ["tcdb"], "description": "...", "source": "config"}
 ]}
```

### Example 12: Enumerate MEROPS call_class values

```example-call
list_filter_values(filter_type="call_class")
```

```example-response
# call_class has 3 values, not 2 — inhibitor is a real third state
# (the family itself is a MEROPS inhibitor family, distinct from a
# peptidase call or a catalytically-dead nonpeptidase_homolog call).
{"filter_type": "call_class", "total_entries": 3, "returned": 3, "truncated": false,
 "results": [
   {"value": "peptidase", "applies_to": ["Gene_has_merops_family"], "description": "...", "source": "vocabulary"},
   {"value": "inhibitor", "applies_to": ["Gene_has_merops_family"], "description": "...", "source": "vocabulary"},
   {"value": "nonpeptidase_homolog", "applies_to": ["Gene_has_merops_family"], "description": "...", "source": "vocabulary"}
 ]}
```

### Example 13: Enumerate InterPro types (for the interpro_type facet/filter)

```example-call
list_filter_values(filter_type="interpro_type")
```

```example-response
{"filter_type": "interpro_type", "total_entries": 8, "returned": 8, "truncated": false,
 "results": [
   {"value": "FAMILY", "applies_to": ["InterproEntry"], "description": "...", "source": "vocabulary"},
   {"value": "DOMAIN", "applies_to": ["InterproEntry"], "description": "...", "source": "vocabulary"},
   {"value": "HOMOLOGOUS_SUPERFAMILY", "applies_to": ["InterproEntry"], "description": "...", "source": "vocabulary"}
 ]}
```

### Example 14: Enumerate MEROPS / NCBIfam term-side categoricals

```example-call
list_filter_values(filter_type="merops_catalytic_type")
```

```example-response
# merops_catalytic_type (serine / cysteine / metallo / ...) is the
# spelled-out MEROPS catalytic-type code, sparse — null for inhibitor
# families. Distinct from merops_family_class (peptidase / inhibitor,
# a 2-state family-level label — not the same axis as the edge-level
# call_class above, though the value names overlap). Same read
# pattern for filter_type='ncbifam_family_type', 'best_hit_kind',
# 'pfam_support', 'attachment_depth' — all read from
# ControlledVocabulary (or a pivot fallback with a warning if that
# node is absent). None of these are ever hard-coded in this tool.
{"filter_type": "merops_catalytic_type", "total_entries": 9, "returned": 9, "truncated": false,
 "results": [
   {"value": "serine", "applies_to": ["MeropsFamily"], "description": "...", "source": "vocabulary"},
   {"value": "cysteine", "applies_to": ["MeropsFamily"], "description": "...", "source": "vocabulary"}
 ]}
```

### Example 15: Enumerate clustering-analysis types (for the cluster_type filter)

```example-call
list_filter_values(filter_type="cluster_type")
```

```example-response
# cluster_type is a closed vocabulary read from the KG's
# ControlledVocabulary node for ClusteringAnalysis.cluster_type — the
# authoritative source; the offline constant in the explorer is only a
# fallback. Same vocabulary-or-pivot rule as the trust types: if the
# node is missing, a live DISTINCT pivot over ClusteringAnalysis nodes
# supplies the values, flagged source="pivot" with a warning.
{"filter_type": "cluster_type", "total_entries": 6, "returned": 6, "truncated": false, "warnings": [],
 "results": [
   {"value": "time_course", "applies_to": ["ClusteringAnalysis"], "description": "...", "source": "vocabulary"},
   {"value": "diel", "applies_to": ["ClusteringAnalysis"], "description": "...", "source": "vocabulary"},
   {"value": "condition_comparison", "applies_to": ["ClusteringAnalysis"], "description": "...", "source": "vocabulary"},
   {"value": "expression_bin", "applies_to": ["ClusteringAnalysis"], "description": "...", "source": "vocabulary"},
   {"value": "decay_pattern", "applies_to": ["ClusteringAnalysis"], "description": "...", "source": "vocabulary"},
   {"value": "genomic_island", "applies_to": ["ClusteringAnalysis"], "description": "...", "source": "vocabulary"}
 ]}
```

## Chaining patterns

```
list_filter_values → genes_by_function(category=...)
list_filter_values(filter_type='cluster_type') → list_clustering_analyses(cluster_type=...) / gene_clusters_by_gene(cluster_type=...)
list_filter_values('brite_tree') → ontology_landscape(tree=...) → pathway_enrichment(tree=...)
list_filter_values(filter_type='metric_type') → list_derived_metrics(metric_types=[...]) → genes_by_{kind}_metric
list_filter_values(filter_type='compartment') → list_experiments(compartment=...) / list_organisms(compartment=...) / list_publications(compartment=...)
list_filter_values(filter_type='evidence_source') → list_metabolites(evidence_sources=[...]) for slicing by evidence type.
list_filter_values(filter_type='omics_type') → list_experiments(omics_type=...) for filtering by experiment type.
list_filter_values(filter_type='trust_axes', ontology=...) → genes_by_ontology / gene_ontology_terms / pathway_enrichment / cluster_enrichment(sources=..., evidence=..., max_tier=..., min_evidence_score=..., call_class=...) — see docs://analysis/annotation_evidence for the full per-ontology profile.
list_filter_values(filter_type='interpro_type') → genes_by_ontology(ontology='interpro', ...) / search_ontology(ontology='interpro', interpro_type=...) / pathway_enrichment(ontology='interpro', interpro_type=...).
list_filter_values(filter_type='call_class') → genes_by_ontology(ontology='merops', call_class=[...]).
```

## Common mistakes

- Use filter_type='metric_type' to discover DerivedMetric tags before passing them to genes_by_{kind}_metric or list_derived_metrics. filter_type='value_kind' enumerates {numeric, boolean, categorical}. filter_type='compartment' enumerates wet-lab fractions (whole_cell, vesicle, exoproteome, ...).

- count is summed across all organisms — a category with count=770 may cover genes in 10+ organisms

- For brite_tree: count is the number of ontology terms in the tree, not genes. Use ontology_landscape to check gene coverage.

```mistake
list_filter_values(category='Photosynthesis')  # no such param
```

```correction
list_filter_values(filter_type='gene_category')  # then pass value to genes_by_function
```

- growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — NOT a gene-specific property

- Trust-related filter_type values (`evidence`, `sources`, `call_class`, `interpro_type`, `ncbifam_family_type`, `merops_catalytic_type`, `merops_family_class`, `best_hit_kind`, `pfam_support`, `attachment_depth`) are read from the KG's ControlledVocabulary nodes (or a live pivot-query fallback, flagged via `source: "pivot"` and a warning, if that node is missing). They are never hard-coded — a KG rebuild that adds a new value shows up here automatically.

- `cluster_type` follows the same vocabulary-or-pivot rule (ControlledVocabulary for ClusteringAnalysis.cluster_type; six values). The value lists quoted in the `cluster_type` parameter descriptions of list_clustering_analyses / gene_clusters_by_gene are documentation only — this call is the live source, and a `warn` from kg_release_info on the vocabulary hash is the cue to prefer it over any quoted list.

- `trust_axes` and `link_kinds` are config-derived (not KG-vocabulary reads) — they answer 'which filter params work on this ontology', not 'what values exist'. Pass `ontology=...` to scope either to one ontology; omit it to see all.

```mistake
genes_by_ontology(ontology='go_bp', call_class=['peptidase'])  # go_bp has no call_class axis
```

```correction
list_filter_values(filter_type='trust_axes', ontology='go_bp')  # check axes first — go_bp supports sources/evidence/evidence_score only
```

## Package import equivalent

```python
from multiomics_explorer import list_filter_values

result = list_filter_values()
# returns dict with keys: filter_type, description, total_entries, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
