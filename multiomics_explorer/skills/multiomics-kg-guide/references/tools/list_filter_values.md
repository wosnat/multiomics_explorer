# list_filter_values

## What it does

Enumerate valid values (+ counts where the KG pivots them) for a categorical filter; the `filter_type` enum is the authoritative list of types.

Value sources: data types (gene_category, brite_tree, growth_phase,
metric_type, value_kind, compartment, omics_type, evidence_source)
pivot live nodes and carry `count`; `cluster_type` and the
annotation-trust types read `ControlledVocabulary` (pivot fallback +
warning when missing) and return `count=None`. Trust types are
documented in docs://analysis/annotation_evidence.

Routing: feed the returned `value`s into the corresponding filter — `gene_category` → `genes_by_function(category=...)`; `brite_tree` → `ontology_landscape(tree=...)` / `pathway_enrichment(tree=...)`; `growth_phase` → `list_experiments(growth_phases=[...])` / `list_derived_metrics(growth_phases=[...])`; `compartment` → `list_experiments` / `list_organisms` / `list_publications`; `metric_type` / `value_kind` → `list_derived_metrics` and `genes_by_{kind}_metric`; `omics_type` → `list_experiments(omics_type=...)`; `evidence_source` → `list_metabolites(evidence_sources=[...])`; `cluster_type` → `list_clustering_analyses` / `gene_clusters_by_gene`; the trust types → `sources` / `evidence` / `call_class` / `interpro_type` on `genes_by_ontology` and friends.

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
- **description** (string | None): Vocabulary-level description of the property behind this filter (ControlledVocabulary text; cluster_type and the trust types — first owner's text when a value spans several edge types). Emitted once here, not per row. None elsewhere.
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
| description | string \| None (optional) | Meaning of THIS value (sparse: vocabulary-backed filter types only, from ControlledVocabulary.value_descriptions). Absent when the KG carries no per-value text (e.g. cluster_type, interpro_type). The property-level text is on the envelope `description`, never repeated per row. |

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
  "description": null,
  "total_entries": 26,
  "returned": 26,
  "truncated": false,
  "warnings": [],
  "results": [
    {"value": "Unknown", "count": 41682},
    {"value": "Amino acid metabolism", "count": 7709},
    {"value": "Translation", "count": 7180},
    ...
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
  "description": null,
  "total_entries": 12,
  "returned": 12,
  "truncated": false,
  "warnings": [],
  "results": [
    {"value": "chaperones", "count": 27, "tree_code": "ko03110"},
    {"value": "defense", "count": 43, "tree_code": "ko02048"},
    {"value": "dna_replication", "count": 23, "tree_code": "ko03032"},
    ...
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
{
  "filter_type": "metric_type",
  "description": null,
  "total_entries": 53,
  "returned": 53,
  "truncated": false,
  "warnings": [],
  "results": [
    {"value": "log2_mv_cell_enrichment", "count": 6},
    {"value": "prop_abund_cells_percent", "count": 6},
    {"value": "prop_abund_mvs_percent", "count": 6},
    ...
  ]
}
```

### Example 6: Enumerate DerivedMetric value kinds

```example-call
list_filter_values(filter_type="value_kind")
```

```example-response
{
  "filter_type": "value_kind",
  "description": null,
  "total_entries": 3,
  "returned": 3,
  "truncated": false,
  "warnings": [],
  "results": [
    {"value": "numeric", "count": 46},
    {"value": "boolean", "count": 27},
    {"value": "categorical", "count": 10}
  ]
}
```

### Example 7: List wet-lab compartments (for compartment filter)

```example-call
list_filter_values(filter_type="compartment")
```

```example-response
{
  "filter_type": "compartment",
  "description": null,
  "total_entries": 4,
  "returned": 4,
  "truncated": false,
  "warnings": [],
  "results": [
    {"value": "whole_cell", "count": 183},
    {"value": "vesicle", "count": 13},
    {"value": "exoproteome", "count": 10},
    ...
  ]
}
```

### Example 8: Enumerate omics types (for experiment / publication filtering)

```example-call
list_filter_values(filter_type="omics_type")
```

```example-response
{
  "filter_type": "omics_type",
  "description": null,
  "total_entries": 8,
  "returned": 8,
  "truncated": false,
  "warnings": [],
  "results": [
    {"value": "EXOPROTEOMICS", "count": 10},
    {"value": "METABOLOMICS", "count": 12},
    {"value": "MICROARRAY", "count": 30},
    ...
  ]
}
```

### Example 9: Enumerate growth phases (timepoint-level culture state, for growth_phases filters)

```example-call
list_filter_values(filter_type="growth_phase")
```

```example-response
{
  "filter_type": "growth_phase",
  "description": null,
  "total_entries": 10,
  "returned": 10,
  "truncated": false,
  "warnings": [],
  "results": [
    {"value": "exponential", "count": 37},
    {"value": "darkness", "count": 33},
    {"value": "stationary", "count": 32},
    ...
  ]
}
```

### Example 10: Enumerate metabolite evidence sources

```example-call
list_filter_values(filter_type="evidence_source")
```

```example-response
{
  "filter_type": "evidence_source",
  "description": null,
  "total_entries": 3,
  "returned": 3,
  "truncated": false,
  "warnings": [],
  "results": [
    {"value": "metabolism", "count": 2225},
    {"value": "transport", "count": 1462},
    {"value": "metabolomics", "count": 149}
  ]
}
```

### Example 11: Enumerate the trust ladder (annotation-trust `evidence` axis)

```example-call
list_filter_values(filter_type="evidence")
```

```example-response
{
  "filter_type": "evidence",
  "description": "Inference strength on the shared ladder curated > signature > homology > family_inferred > domain_inferred (homology ...",
  "total_entries": 5,
  "returned": 5,
  "truncated": false,
  "warnings": [],
  "results": [
    {
      "value": "curated",
      "source": "vocabulary",
      "applies_to": [
        "Gene_involved_in_biological_process",
        "Gene_enables_molecular_function",
        "Gene_located_in_cellular_component",
        "Gene_catalyzes_ec_number",
        "Gene_has_cyanorak_role",
        ...
      ],
      "description": "assigned by a human curator or a curated reference annotation (Cyanorak, UniProt, NCBI); strongest rung"
    },
    {
      "value": "family_inferred",
      "source": "vocabulary",
      "applies_to": [
        "Gene_involved_in_biological_process",
        "Gene_enables_molecular_function",
        "Gene_located_in_cellular_component",
        "Gene_catalyzes_ec_number",
        "Gene_has_kegg_ko",
        ...
      ],
      "description": "transferred from an ortholog family or a single-function protein family (eggNOG orthology transfer, InterPro FAMILY e..."
    },
    {
      "value": "domain_inferred",
      "source": "vocabulary",
      "applies_to": [
        "Gene_involved_in_biological_process",
        "Gene_enables_molecular_function",
        "Gene_located_in_cellular_component",
        "Gene_has_cazy_family"
      ],
      "description": "transferred from a shared domain (InterPro DOMAIN entry); weakest rung, since a domain can occur outside the annotate..."
    },
    ...
  ]
}
```

### Example 12: Discover which trust axes an ontology supports

```example-call
list_filter_values(filter_type="trust_axes", ontology="tcdb")
```

```example-response
{
  "filter_type": "trust_axes",
  "description": null,
  "total_entries": 4,
  "returned": 4,
  "truncated": false,
  "warnings": [],
  "results": [
    {
      "value": "sources",
      "source": "config",
      "applies_to": ["tcdb"],
      "description": "Which pipelines asserted the annotation (membership list)."
    },
    {
      "value": "evidence",
      "source": "config",
      "applies_to": ["tcdb"],
      "description": "Strength ladder: curated > signature > homology > family_inferred > domain_inferred."
    },
    {
      "value": "evidence_score",
      "source": "config",
      "applies_to": ["tcdb"],
      "description": "Composite trust score in 0..1 — the only numeric cutoff (min_evidence_score) and the within-ontology sort key."
    },
    ...
  ]
}
```

### Example 13: Enumerate MEROPS call_class values

```example-call
list_filter_values(filter_type="call_class")
```

```example-response
{
  "filter_type": "call_class",
  "description": "Read-first verdict for one MEROPS candidate: inhibitor when the family is an I-family, nonpeptidase_homolog when the ...",
  "total_entries": 3,
  "returned": 3,
  "truncated": false,
  "warnings": [],
  "results": [
    {
      "value": "peptidase",
      "source": "vocabulary",
      "applies_to": ["Gene_has_merops_family"],
      "description": "best hit is a characterized or putative active peptidase; protease evidence"
    },
    {
      "value": "inhibitor",
      "source": "vocabulary",
      "applies_to": ["Gene_has_merops_family"],
      "description": "family is a MEROPS I-family; the product is a peptidase inhibitor, not a protease"
    },
    {
      "value": "nonpeptidase_homolog",
      "source": "vocabulary",
      "applies_to": ["Gene_has_merops_family"],
      "description": "best hit is a catalytically dead .9xx relative; fold evidence only, NOT protease evidence"
    }
  ]
}
```

### Example 14: Enumerate InterPro types (for the interpro_type facet/filter)

```example-call
list_filter_values(filter_type="interpro_type")
```

```example-response
{
  "filter_type": "interpro_type",
  "description": "InterPro entry class (FAMILY, DOMAIN, HOMOLOGOUS_SUPERFAMILY, CONSERVED_SITE, ACTIVE_SITE, REPEAT, BINDING_SITE, PTM)...",
  "total_entries": 8,
  "returned": 8,
  "truncated": false,
  "warnings": [],
  "results": [
    {"value": "FAMILY", "source": "vocabulary", "applies_to": ["InterproEntry"]},
    {"value": "DOMAIN", "source": "vocabulary", "applies_to": ["InterproEntry"]},
    {"value": "HOMOLOGOUS_SUPERFAMILY", "source": "vocabulary", "applies_to": ["InterproEntry"]},
    ...
  ]
}
```

### Example 15: Enumerate MEROPS / NCBIfam term-side categoricals

```example-call
list_filter_values(filter_type="merops_catalytic_type")
```

```example-response
{
  "filter_type": "merops_catalytic_type",
  "description": "Catalytic mechanism of a peptidase family, MEROPS^s single-letter code spelled out (S = serine, C = cysteine, M = met...",
  "total_entries": 9,
  "returned": 9,
  "truncated": false,
  "warnings": [],
  "results": [
    {"value": "serine", "source": "vocabulary", "applies_to": ["MeropsFamily"]},
    {"value": "cysteine", "source": "vocabulary", "applies_to": ["MeropsFamily"]},
    {"value": "metallo", "source": "vocabulary", "applies_to": ["MeropsFamily"]},
    ...
  ]
}
```

### Example 16: Enumerate clustering-analysis types (for the cluster_type filter)

```example-call
list_filter_values(filter_type="cluster_type")
```

```example-response
{
  "filter_type": "cluster_type",
  "description": "What kind of gene grouping the analysis is: time_course, diel, condition_comparison, expression_bin, decay_pattern (m...",
  "total_entries": 6,
  "returned": 6,
  "truncated": false,
  "warnings": [],
  "results": [
    {"value": "time_course", "source": "vocabulary", "applies_to": ["ClusteringAnalysis"]},
    {"value": "diel", "source": "vocabulary", "applies_to": ["ClusteringAnalysis"]},
    {"value": "condition_comparison", "source": "vocabulary", "applies_to": ["ClusteringAnalysis"]},
    ...
  ]
}
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

- `count` is None on every vocabulary-sourced row: all the trust filter types (`evidence`, `sources`, `call_class`, `interpro_type`, ...) AND `cluster_type`. Only the pivoted / precomputed types (`gene_category`, `brite_tree`, `growth_phase`, `metric_type`, `value_kind`, `compartment`, `omics_type`, `evidence_source`) carry a count. Read `applies_to` / `description` on the count-less rows instead.

- treatment_type and background_factors have no filter_type here — enumerate them from the by_treatment_type / by_background_factors rollups of list_experiments(summary=True) or list_publications(). They are live vocabularies: an unknown value passed to a filter returns 0 rows, not an error.

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

- Two `description` fields, two scopes: the envelope `description` is the property's vocabulary text (what `evidence` / `call_class` / `cluster_type` means as a whole), emitted once; a row's `description` is the meaning of that one value. Rows without per-value text simply omit the key — read the envelope, don't treat the absence as a missing vocabulary.

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
# returns dict with keys: filter_type, description, total_entries, returned, truncated, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
