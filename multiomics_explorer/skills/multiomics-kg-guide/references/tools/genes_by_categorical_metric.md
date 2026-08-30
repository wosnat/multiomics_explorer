# genes_by_categorical_metric

## What it does

Categorical DerivedMetric edges — one row per gene × DM × edge value; cross-organism.

Use to slice genes by a category label after `list_derived_metrics`; values `genes_by_numeric_metric`, flags `genes_by_boolean_metric`.
Filters: derived_metric_ids XOR metric_types, organism, locus_tags, categories, plus the publication / experiment / condition filters.
Returns: by_category, by_metric (vs full-DM, allowed_categories), by_organism, not_found_ids, not_found_metric_types, not_matched_ids, not_matched_metric_types; one row = one edge.
docs://tools/genes_by_categorical_metric; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| derived_metric_ids | list[string] \| None | None | Categorical DerivedMetric node IDs. Use when the same `metric_type` appears across organisms / publications and you need to pin one. Discover IDs via `list_derived_metrics(value_kind='categorical')`. Mutually exclusive with `metric_types`. An id that exists as a different kind (numeric / boolean) moves to `not_matched_ids` with a `warnings` entry naming the sibling tool. |
| metric_types | list[string] \| None | None | Categorical metric-type tags (e.g. ['predicted_subcellular_localization', 'darkness_survival_class']). Unions every DM carrying that tag, then narrows by scoping filters. Same tag can span organisms / publications — pin one specific DM via `derived_metric_ids` instead. Mutually exclusive with `derived_metric_ids`. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| locus_tags | list[string] \| None | None | Restrict drill-down to a specific gene set (e.g. DE hits from `differential_expression_by_gene`). Filter on `g.locus_tag IN $locus_tags` post-MATCH. Genes with no edge for the selected DM produce no row. |
| experiment_ids | list[string] \| None | None | Scope to DMs from one or more experiments. |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| categories | list[string] \| None | None | Filter on `r.value`: keep rows whose value is in this set. Validated against the union of the selected DMs' `allowed_categories` — unknown values raise `ValueError` listing the allowed set. E.g. ['Outer Membrane', 'Periplasmic'] for `predicted_subcellular_localization`. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 25 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_category, top_categories, by_metric, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, returned, offset, truncated, results
```

- **total_matching** (int): Rows post-filter (gene × DM pairs).
- **total_derived_metrics** (int): Distinct DMs contributing rows.
- **total_genes** (int): Distinct genes in results.
- **by_organism** (list[GenesByNumericMetricOrganismBreakdown]): Rows per organism.
- **by_compartment** (list[GenesByNumericMetricCompartmentBreakdown]): Rows per compartment.
- **by_publication** (list[GenesByNumericMetricPublicationBreakdown]): Rows per publication.
- **by_experiment** (list[GenesByNumericMetricExperimentBreakdown]): Rows per experiment.
- **by_category** (list[GenesByCategoricalMetricCategoryFreq]): Frequency rollup of `r.value` across surviving rows. Cross-DM unioned — a category present in two DMs sums.
- **top_categories** (list[GenesByNumericMetricCategoryBreakdown]): Top 5 gene categories by count.
- **by_metric** (list[GenesByCategoricalMetricBreakdown]): Per-DM rollup: filtered-slice category histogram + full-DM precomputed histogram. Sorted by count desc.
- **genes_per_metric_max** (int): Largest per-DM gene count.
- **genes_per_metric_median** (float): Median per-DM gene count.
- **not_found_ids** (list[string]): `derived_metric_ids` inputs absent from the KG entirely (any kind, any organism), or scoped out by compartment / treatment_type / background_factors / growth_phases / publication_dois / experiment_ids.
- **not_matched_ids** (list[string]): `derived_metric_ids` that exist but produced 0 rows — either a different `value_kind` (see `warnings` for the sibling tool to use) or 0 rows after edge-level filters.
- **not_found_metric_types** (list[string]): `metric_types` inputs that match no DM after scoping.
- **not_matched_metric_types** (list[string]): `metric_types` whose DMs produced 0 rows.
- **not_matched_organism** (string | None): `organism` arg that matched no surviving (correct-kind) DM — set only when the DM(s) genuinely exist elsewhere; `warnings` lists the organisms they belong to.
- **excluded_derived_metrics** (list[ExcludedDerivedMetric]): Always [] for categorical DMs (no rankable / has_p_value gates). Kept for cross-tool envelope-shape consistency.
- **warnings** (list[string]): No rankable / has_p_value gates exist for categorical DMs, so excluded_derived_metrics stays []; warnings still carries a closed-vocabulary filter value (compartment / treatment_type / background_factors / growth_phases) not found in the live vocabulary, or an `organism` that matches no OrganismTaxon at all (distinct from not_matched_organism).
- **returned** (int): Length of results list.
- **offset** (int): Pagination offset used.
- **truncated** (bool): True when total_matching > offset + returned.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0097'). |
| gene_name | string \| None (optional) | Gene symbol; null when KG has none. |
| product | string \| None (optional) | Gene product. |
| gene_category | string \| None (optional) | Coarse functional category. |
| derived_metric_id | string | Unique parent-DM id. |
| value | string | Category label (one of the parent DM's `allowed_categories`). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| organism_name | string \| None (optional) | Organism (e.g. 'Prochlorococcus MED4'). Also in `by_organism`. Verbose only. |
| name | string \| None (optional) | DM human label. Also in `by_metric`. Verbose only. |
| value_kind | string \| None (optional) | Always 'categorical' for this tool; kept for cross-tool row-shape consistency with `genes_by_numeric_metric`. Also in `by_metric`. Verbose only. |
| rankable | bool \| None (optional) | DM-level rankable flag (always False for categorical DMs in the current KG). Also in `by_metric`. Verbose only. |
| has_p_value | bool \| None (optional) | DM-level p-value flag (always False for categorical DMs in the current KG). Also in `by_metric`. Verbose only. |
| metric_type | string \| None (optional) | Category tag. Verbose only. |
| field_description | string \| None (optional) | Detailed explanation of what this DM measures. Verbose only. |
| unit | string \| None (optional) | Measurement unit (typically null for categorical DMs). Verbose only. |
| compartment | string \| None (optional) | Sample compartment. Verbose only. |
| experiment_id | string \| None (optional) | Parent experiment id. Verbose only. |
| publication_doi | string \| None (optional) | Parent publication DOI. Verbose only. |
| treatment_type | list[string] \| None (optional) | Treatment type(s). Verbose only. |
| background_factors | list[string] \| None (optional) | Background factor(s). Verbose only. |
| treatment | string \| None (optional) | Treatment description in plain language. Verbose only. |
| light_condition | string \| None (optional) | Light regime. Verbose only. |
| experimental_context | string \| None (optional) | Longer experimental setup description. Verbose only. |
| gene_function_description | string \| None (optional) | Gene functional description (gene-level). Verbose only. |
| gene_summary | string \| None (optional) | Gene summary text (gene-level). Verbose only. |
| allowed_categories | list[string] \| None (optional) | Schema-declared full set for this row's parent DM. Verbose only. |

## Few-shot examples

### Example 1: PSORTb membrane categories — cross-organism slice

```example-call
genes_by_categorical_metric(metric_types=['predicted_subcellular_localization'], categories=['Outer Membrane', 'Periplasmic'])
```

```example-response
{
  "total_matching": 14,
  "total_derived_metrics": 2,
  "total_genes": 14,
  "by_organism": [
    {"organism_name": "Prochlorococcus MED4", "count": 8},
    {"organism_name": "Prochlorococcus MIT9313", "count": 6}
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 14}],
  "by_publication": [{"publication_doi": "10.1126/science.1243457", "count": 14}],
  "by_experiment": [
    {"experiment_id": "10.1126/science.1243457_vesicle_proteomics_med4", "count": 8},
    {"experiment_id": "10.1126/science.1243457_vesicle_proteomics_mit9313", "count": 6}
  ],
  "by_category": [{"category": "Outer Membrane", "count": 8}, {"category": "Periplasmic", "count": 6}],
  "top_categories": [
    {"gene_category": "Cell wall and membrane", "count": 5},
    {"gene_category": "Post-translational modification", "count": 3},
    {"gene_category": "Stress response and adaptation", "count": 3},
    {"gene_category": "Cell motility", "count": 1},
    {"gene_category": "Signal transduction", "count": 1}
  ],
  "by_metric": [
    {
      "derived_metric_id": "derived_metric:science.1243457:s2_med4_vesicle_proteome:predicted_subcellular_localization",
      "name": "MED4 vesicle protein PSORTb predicted localization (Biller 2014 Table S2)",
      "metric_type": "predicted_subcellular_localization",
      "value_kind": "categorical",
      "count": 8,
      "by_category": [{"category": "Outer Membrane", "count": 5}, {"category": "Periplasmic", "count": 3}],
      "allowed_categories": ["Cytoplasmic", "Cytoplasmic Membrane", "Periplasmic", "Outer Membrane", "Extracellular", ...],
      "dm_total_gene_count": 32,
      "dm_by_category": [
        {"category": "Cytoplasmic", "count": 11},
        {"category": "Unknown", "count": 7},
        {"category": "Cytoplasmic Membrane", "count": 6},
        {"category": "Outer Membrane", "count": 5},
        {"category": "Periplasmic", "count": 3}
      ]
    },
    {
      "derived_metric_id": "derived_metric:science.1243457:s3_mit9313_vesicle_proteome:predicted_subcellular_localization",
      "name": "MIT9313 vesicle protein PSORTb predicted localization (Biller 2014 Table S3)",
      "metric_type": "predicted_subcellular_localization",
      "value_kind": "categorical",
      "count": 6,
      "by_category": [{"category": "Periplasmic", "count": 3}, {"category": "Outer Membrane", "count": 3}],
      "allowed_categories": ["Cytoplasmic", "Cytoplasmic Membrane", "Periplasmic", "Outer Membrane", "Extracellular", ...],
      "dm_total_gene_count": 27,
      "dm_by_category": [
        {"category": "Unknown", "count": 15},
        {"category": "Cytoplasmic", "count": 3},
        {"category": "Extracellular", "count": 3},
        {"category": "Outer Membrane", "count": 3},
        {"category": "Periplasmic", "count": 3}
      ]
    }
  ],
  "genes_per_metric_max": 8,
  "genes_per_metric_median": 8.0,
  "not_found_ids": [],
  "not_matched_ids": [],
  "not_found_metric_types": [],
  "not_matched_metric_types": [],
  "not_matched_organism": null,
  "excluded_derived_metrics": [],
  "warnings": [],
  "returned": 14,
  "offset": 0,
  "truncated": false,
  "results": [
    {
      "locus_tag": "PMM0097",
      "gene_name": "tolC",
      "product": "TolC-like outer membrane efflux protein, RND family",
      "gene_category": "Stress response and adaptation",
      "derived_metric_id": "derived_metric:science.1243457:s2_med4_vesicle_proteome:predicted_subcellular_localization",
      "value": "Outer Membrane"
    },
    {
      "locus_tag": "PMM0254",
      "gene_name": null,
      "product": "protein of unknown function DUF3769",
      "gene_category": "Cell wall and membrane",
      "derived_metric_id": "derived_metric:science.1243457:s2_med4_vesicle_proteome:predicted_subcellular_localization",
      "value": "Outer Membrane"
    },
    {
      "locus_tag": "PMM1124",
      "gene_name": null,
      "product": "autotransporter beta-domain containing protein",
      "gene_category": "Signal transduction",
      "derived_metric_id": "derived_metric:science.1243457:s2_med4_vesicle_proteome:predicted_subcellular_localization",
      "value": "Outer Membrane"
    },
    ...
  ]
}
```

### Example 2: Darkness survival classes — single-organism scoping

```example-call
genes_by_categorical_metric(metric_types=['darkness_survival_class'], categories=['darkness_axenic+darkness_coculture'])
```

```example-response
{
  "total_matching": 95,
  "total_derived_metrics": 1,
  "total_genes": 95,
  "by_organism": [{"organism_name": "Prochlorococcus NATL2A", "count": 95}],
  "by_compartment": [{"compartment": "whole_cell", "count": 95}],
  "by_publication": [{"publication_doi": "10.1128/mSystems.00040-18", "count": 95}],
  "by_experiment": [
    {
      "experiment_id": "10.1128/mSystems.00040-18_darkness_extended_darkness_natl2a_rnaseq_axenic",
      "count": 95
    }
  ],
  "by_category": [{"category": "darkness_axenic+darkness_coculture", "count": 95}],
  "top_categories": [
    {"gene_category": "Stress response and adaptation", "count": 25},
    {"gene_category": "Photosynthesis", "count": 13},
    {"gene_category": "Translation", "count": 10},
    {"gene_category": "Unknown", "count": 10},
    {"gene_category": "Coenzyme metabolism", "count": 5}
  ],
  "by_metric": [
    {
      "derived_metric_id": "derived_metric:mSystems.00040-18:s5_natl2a_survival:darkness_survival_class",
      "name": "NATL2A darkness survival class (Table S5)",
      "metric_type": "darkness_survival_class",
      "value_kind": "categorical",
      "count": 95,
      "by_category": [{"category": "darkness_axenic+darkness_coculture", "count": 95}],
      "allowed_categories": [
        "darkness_axenic+darkness_coculture",
        "darkness_coculture+unique_coculture",
        "darkness_axenic+unique_axenic"
      ],
      "dm_total_gene_count": 258,
      "dm_by_category": [
        {"category": "darkness_axenic+darkness_coculture", "count": 95},
        {"category": "darkness_coculture+unique_coculture", "count": 87},
        {"category": "darkness_axenic+unique_axenic", "count": 76}
      ]
    }
  ],
  "genes_per_metric_max": 95,
  "genes_per_metric_median": 95.0,
  "not_found_ids": [],
  "not_matched_ids": [],
  "not_found_metric_types": [],
  "not_matched_metric_types": [],
  "not_matched_organism": null,
  "excluded_derived_metrics": [],
  "warnings": [],
  "returned": 25,
  "offset": 0,
  "truncated": true,
  "results": [
    {
      "locus_tag": "PMN2A_0016",
      "gene_name": "clpB1",
      "product": "ATP-dependent Clp protease ATP-binding subunit ClpB",
      "gene_category": "Stress response and adaptation",
      "derived_metric_id": "derived_metric:mSystems.00040-18:s5_natl2a_survival:darkness_survival_class",
      "value": "darkness_axenic+darkness_coculture"
    },
    {
      "locus_tag": "PMN2A_0017",
      "gene_name": "petE",
      "product": "plastocyanin",
      "gene_category": "Stress response and adaptation",
      "derived_metric_id": "derived_metric:mSystems.00040-18:s5_natl2a_survival:darkness_survival_class",
      "value": "darkness_axenic+darkness_coculture"
    },
    {
      "locus_tag": "PMN2A_0020",
      "gene_name": "glgB",
      "product": "1,4-alpha-glucan branching enzyme",
      "gene_category": "Carbohydrate metabolism",
      "derived_metric_id": "derived_metric:mSystems.00040-18:s5_natl2a_survival:darkness_survival_class",
      "value": "darkness_axenic+darkness_coculture"
    },
    ...
  ]
}
```

### Example 3: Summary-only — full-DM histogram + allowed_categories context

```example-call
genes_by_categorical_metric(metric_types=['predicted_subcellular_localization'], summary=True)
```

```example-response
{
  "total_matching": 59,
  "total_derived_metrics": 2,
  "total_genes": 59,
  "by_organism": [
    {"organism_name": "Prochlorococcus MED4", "count": 32},
    {"organism_name": "Prochlorococcus MIT9313", "count": 27}
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 59}],
  "by_publication": [{"publication_doi": "10.1126/science.1243457", "count": 59}],
  "by_experiment": [
    {"experiment_id": "10.1126/science.1243457_vesicle_proteomics_med4", "count": 32},
    {"experiment_id": "10.1126/science.1243457_vesicle_proteomics_mit9313", "count": 27}
  ],
  "by_category": [
    {"category": "Unknown", "count": 22},
    {"category": "Cytoplasmic", "count": 14},
    {"category": "Outer Membrane", "count": 8},
    {"category": "Cytoplasmic Membrane", "count": 6},
    {"category": "Periplasmic", "count": 6},
    ...
  ],
  "top_categories": [
    {"gene_category": "Unknown", "count": 12},
    {"gene_category": "Stress response and adaptation", "count": 9},
    {"gene_category": "Cell wall and membrane", "count": 9},
    {"gene_category": "Translation", "count": 6},
    {"gene_category": "Post-translational modification", "count": 4}
  ],
  "by_metric": [
    {
      "derived_metric_id": "derived_metric:science.1243457:s2_med4_vesicle_proteome:predicted_subcellular_localization",
      "name": "MED4 vesicle protein PSORTb predicted localization (Biller 2014 Table S2)",
      "metric_type": "predicted_subcellular_localization",
      "value_kind": "categorical",
      "count": 32,
      "by_category": [
        {"category": "Cytoplasmic", "count": 11},
        {"category": "Unknown", "count": 7},
        {"category": "Cytoplasmic Membrane", "count": 6},
        {"category": "Outer Membrane", "count": 5},
        {"category": "Periplasmic", "count": 3}
      ],
      "allowed_categories": ["Cytoplasmic", "Cytoplasmic Membrane", "Periplasmic", "Outer Membrane", "Extracellular", ...],
      "dm_total_gene_count": 32,
      "dm_by_category": [
        {"category": "Cytoplasmic", "count": 11},
        {"category": "Unknown", "count": 7},
        {"category": "Cytoplasmic Membrane", "count": 6},
        {"category": "Outer Membrane", "count": 5},
        {"category": "Periplasmic", "count": 3}
      ]
    },
    {
      "derived_metric_id": "derived_metric:science.1243457:s3_mit9313_vesicle_proteome:predicted_subcellular_localization",
      "name": "MIT9313 vesicle protein PSORTb predicted localization (Biller 2014 Table S3)",
      "metric_type": "predicted_subcellular_localization",
      "value_kind": "categorical",
      "count": 27,
      "by_category": [
        {"category": "Unknown", "count": 15},
        {"category": "Extracellular", "count": 3},
        {"category": "Periplasmic", "count": 3},
        {"category": "Cytoplasmic", "count": 3},
        {"category": "Outer Membrane", "count": 3}
      ],
      "allowed_categories": ["Cytoplasmic", "Cytoplasmic Membrane", "Periplasmic", "Outer Membrane", "Extracellular", ...],
      "dm_total_gene_count": 27,
      "dm_by_category": [
        {"category": "Unknown", "count": 15},
        {"category": "Cytoplasmic", "count": 3},
        {"category": "Extracellular", "count": 3},
        {"category": "Outer Membrane", "count": 3},
        {"category": "Periplasmic", "count": 3}
      ]
    }
  ],
  "genes_per_metric_max": 32,
  "genes_per_metric_median": 32.0,
  "not_found_ids": [],
  "not_matched_ids": [],
  "not_found_metric_types": [],
  "not_matched_metric_types": [],
  "not_matched_organism": null,
  "excluded_derived_metrics": [],
  "warnings": [],
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "results": []
}
```

### Example 4: DE → top hits → categorical classification intersection

```
Step 1: differential_expression_by_gene(organism="MED4", significant_only=True, limit=20)
        → extract `locus_tag` from each result row (top-20 |log2FC|).

Step 2: genes_by_categorical_metric(
          metric_types=["predicted_subcellular_localization"],
          locus_tags=[<those 20 locus_tags>])
        → which DE hits have a vesicle-PSORTb classification?
          Per-row `value` carries the category label; envelope
          `by_category` shows the slice's class distribution.

Step 3 (drill-down): gene_overview(locus_tags=[<intersected genes>])
        → routing context for the genes that are both DE-significant
          AND classified to a target compartment.
```

## Chaining patterns

```
list_derived_metrics(value_kind='categorical') → genes_by_categorical_metric(metric_types=[...], categories=[...]) → gene_overview / genes_by_function
differential_expression_by_gene → top hits → genes_by_categorical_metric(metric_types=[...], locus_tags=hits)
genes_by_categorical_metric (no organism filter) → split via envelope by_organism for cross-strain comparison
```

## Common mistakes

- Unknown category raises with the allowed-set in the error. `categories=['foo']` raises `ValueError` listing every value in the union of selected DMs' `allowed_categories`. Pull the set from `list_derived_metrics(value_kind='categorical')` verbose output, or read it from the error message itself — the tool surfaces the full union without a follow-up call.

- `allowed_categories` ⊋ `dm_by_category`. A category may be declared in `allowed_categories` (schema-level) but unobserved in any gene (absent from `dm_by_category`). Example: MED4 PSORTb declares `Extracellular` but no gene is classified that way — `dm_by_category` omits it. Both per-DM context fields appear in each `by_metric` row; inspect them together before assuming a category exists in the data.

- Sparse `rankable` / `has_p_value` echoes. Both are always `False` on every row from categorical DMs in the current KG — kept for cross-tool row-shape consistency with `genes_by_numeric_metric`, not because this tool reads them as a meaningful signal. Don't gate downstream logic on them.

```mistake
genes_by_categorical_metric(derived_metric_ids=['derived_metric:...:damping_ratio'])
```

```correction
genes_by_categorical_metric(metric_types=['predicted_subcellular_localization'])
```

- See `docs://analysis/derived_metrics` for the DM family overview (numeric / boolean / categorical drill-downs).

- `excluded_derived_metrics` is always `[]` here — no rankable / has_p_value gate applies to categorical DMs; it is kept for envelope-shape parity with `genes_by_numeric_metric`. `warnings` carries the closed-vocabulary, organism-existence and kind-mismatch notices instead.

## Package import equivalent

```python
from multiomics_explorer import genes_by_categorical_metric

result = genes_by_categorical_metric()
# returns dict with keys: total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_category, top_categories, by_metric, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, returned, offset, truncated, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
