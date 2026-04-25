# list_derived_metrics

## What it does

Discover DerivedMetric (DM) nodes — column-level scalar summaries
of gene behavior (e.g. rhythmicity flags, diel amplitudes,
darkness-survival class) that sit alongside DE and gene clusters as
non-DE evidence.

Call this first, before `gene_derived_metrics` or the three
`genes_by_{kind}_metric` drill-downs. Inspect `value_kind` (routes
you to the right drill-down), `rankable` (gates bucket / percentile
/ rank filters), `has_p_value` (gates significance filters), and
`allowed_categories` (for categorical DMs) here — drill-down tools
will raise if you pass filters that the selected DM set doesn't
support.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Full-text search over DM name and field_description. Examples: 'diel amplitude', 'darkness survival', 'peak time'. |
| organism | string \| None | None | Organism to filter by. Accepts short strain code ('MED4', 'NATL2A', 'MIT1002') or full name ('Prochlorococcus MED4'). Case-insensitive substring match. |
| metric_types | list[string] \| None | None | Filter by metric_type tags (e.g. 'diel_amplitude_protein_log2', 'periodic_in_coculture_LD'). The same metric_type may appear across organisms / publications — use derived_metric_ids to pin one specific DM when that matters. |
| value_kind | string ('numeric', 'boolean', 'categorical') \| None | None | Filter by value kind. Determines which drill-down tool applies: 'numeric' → genes_by_numeric_metric, 'boolean' → genes_by_boolean_metric, 'categorical' → genes_by_categorical_metric. |
| compartment | string \| None | None | Sample compartment / scope. Current values: 'whole_cell', 'vesicle', 'exoproteome', 'spent_medium', 'lysate'. |
| omics_type | string \| None | None | Omics assay type. Examples: 'RNASEQ', 'PROTEOME', 'PAIRED_RNASEQ_PROTEOME'. Case-insensitive. |
| treatment_type | list[string] \| None | None | Treatment type(s) to match. Returns DMs whose treatment_type list overlaps ANY of the given values (e.g. 'diel', 'darkness', 'nitrogen_starvation'). Case-insensitive. |
| background_factors | list[string] \| None | None | Background experimental factor(s) to match (e.g. 'axenic', 'coculture', 'diel'). Returns DMs overlapping ANY given value. Case-insensitive. |
| growth_phases | list[string] \| None | None | Growth phase(s) to match (e.g. 'darkness', 'exponential'). Case-insensitive. |
| publication_doi | list[string] \| None | None | Filter by one or more publication DOIs (e.g. '10.1128/mSystems.00040-18'). Exact match. |
| experiment_ids | list[string] \| None | None | Filter by one or more Experiment node ids. |
| derived_metric_ids | list[string] \| None | None | Look up specific DMs by their unique id (matches `derived_metric_id` on each result). Use to pin one DM when the same metric_type appears across publications or organisms. |
| rankable | bool \| None | None | Filter to DMs that support rank / percentile / bucket analysis. Set to True before calling genes_by_numeric_metric with `bucket`, `min_percentile`, `max_percentile`, or `max_rank` — those filters require rankable=True on every selected DM. |
| has_p_value | bool \| None | None | Filter to DMs that carry statistical p-values. Set to True before using `significant_only` or `max_adjusted_p_value` on drill-downs. No DM in the current KG carries p-values, so has_p_value=True returns zero rows today — kept available because the drill-down p-value filters raise when no selected DM supports them. |
| summary | bool | False | Return summary fields only (counts and breakdowns, no individual results). Use for quick orientation. |
| verbose | bool | False | Include detailed text fields per result: treatment, light_condition, experimental_context. (p_value_threshold is reserved for future DMs with statistical significance; always null in current data.) |
| limit | int | 20 | Max results to return. Paginate with offset. |
| offset | int | 0 | Pagination offset (starting row, 0-indexed). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_organism, by_value_kind, by_metric_type, by_compartment, by_omics_type, by_treatment_type, by_background_factors, by_growth_phase, score_max, score_median, returned, offset, truncated, results
```

- **total_entries** (int): Total DMs in the KG (unfiltered baseline).
- **total_matching** (int): DMs matching all applied filters.
- **by_organism** (list[object]): Counts per organism (list of {organism_name, count}, sorted by count desc).
- **by_value_kind** (list[object]): Counts per value_kind (list of {value_kind, count}).
- **by_metric_type** (list[object]): Counts per metric_type (list of {metric_type, count}).
- **by_compartment** (list[object]): Counts per compartment (list of {compartment, count}).
- **by_omics_type** (list[object]): Counts per omics_type (list of {omics_type, count}).
- **by_treatment_type** (list[object]): Counts per treatment_type (list of {treatment_type, count}; DM treatment_type lists are flattened before counting).
- **by_background_factors** (list[object]): Counts per background_factor (list of {background_factor, count}; flattened).
- **by_growth_phase** (list[object]): Counts per growth_phase (list of {growth_phase, count}; flattened).
- **score_max** (float | None): Max relevance score; present only when search_text was provided.
- **score_median** (float | None): Median relevance score; present only when search_text was provided.
- **returned** (int): Number of rows in results.
- **offset** (int): Pagination offset used for this call.
- **truncated** (bool): True when total_matching > returned (more rows available — paginate with offset).

### Per-result fields

| Field | Type | Description |
|---|---|---|
| derived_metric_id | string | Unique id for this DerivedMetric. Pass to `derived_metric_ids` on drill-down tools (gene_derived_metrics, genes_by_*_metric) to select this exact DM. |
| name | string | Human-readable DM name (e.g. 'Transcript:protein amplitude ratio'). |
| metric_type | string | Category tag identifying what is measured (e.g. 'diel_amplitude_protein_log2'). The same metric_type may appear across organisms / publications — pair with organism or publication_doi when that matters, or use derived_metric_id to pin one specific DM. |
| value_kind | string ('numeric', 'boolean', 'categorical') | Routes to the correct drill-down tool: 'numeric' → genes_by_numeric_metric, 'boolean' → genes_by_boolean_metric, 'categorical' → genes_by_categorical_metric. |
| rankable | bool | True if this DM supports rank / percentile / bucket analysis on genes_by_numeric_metric. When False, the `bucket`, `min_percentile`, `max_percentile`, and `max_rank` filters on that drill-down do not apply — passing them with only non-rankable DMs raises; mixing rankable + non-rankable drops the non-rankable ones and lists them in the drill-down's `excluded_derived_metrics`. |
| has_p_value | bool | True if this DM carries statistical p-values, enabling `significant_only` and `max_adjusted_p_value` on drill-downs. No DM in the current KG has p-values. |
| unit | string | Measurement unit for numeric DMs (e.g. 'hours', 'log2'). Empty string for boolean and categorical DMs. |
| allowed_categories | list[string] \| None | Valid category strings for this DM. Non-null only when value_kind='categorical'; pass a subset as `categories` to genes_by_categorical_metric. |
| field_description | string | Detailed explanation of what this DM measures and how to interpret its values. |
| organism_name | string | Full organism name (e.g. 'Prochlorococcus MED4', 'Alteromonas macleodii MIT1002'). |
| experiment_id | string | Parent Experiment node id. Look up context via list_experiments. |
| publication_doi | string | Parent publication DOI (e.g. '10.1128/mSystems.00040-18'). |
| compartment | string | Sample compartment or scope (e.g. 'whole_cell', 'vesicle', 'exoproteome', 'spent_medium', 'lysate'). |
| omics_type | string | Omics assay type (e.g. 'RNASEQ', 'PROTEOME', 'PAIRED_RNASEQ_PROTEOME'). |
| treatment_type | list[string] | Treatment type(s) (e.g. ['diel'], ['darkness']). |
| background_factors | list[string] | Background experimental factors (e.g. ['axenic'], ['coculture', 'diel']). May be empty. |
| total_gene_count | int | Number of distinct genes with at least one measurement for this DM. |
| growth_phases | list[string] | Growth phase(s) this DM pertains to (e.g. ['darkness']). May be empty. |
| score | float \| None (optional) | Full-text relevance score; present only when search_text was provided. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| treatment | string \| None (optional) | Treatment description in plain language (verbose mode only). |
| light_condition | string \| None (optional) | Light regime (e.g. 'light:dark cycle'; verbose mode only). |
| experimental_context | string \| None (optional) | Longer description of the experimental setup that produced this DM (verbose mode only). |
| p_value_threshold | float \| None (optional) | Threshold that defines statistical significance for this DM. Non-null only when has_p_value=True (verbose mode only; no DM in current KG has a threshold). |

## Few-shot examples

### Example 1: Orient — what DerivedMetrics exist in the KG?

```example-call
list_derived_metrics(summary=True)
```

### Example 2: Pre-flight for numeric drill-down — which DMs support rank/bucket?

```example-call
list_derived_metrics(value_kind="numeric", rankable=True)
```

### Example 3: Find rhythm / diel evidence via full-text

```example-call
list_derived_metrics(search_text="diel amplitude", limit=5)
```

### Example 4: Per-publication inventory

```example-call
list_derived_metrics(publication_doi=["10.1128/mSystems.00040-18"])
```

### Example 5: Per-organism inventory

```example-call
list_derived_metrics(organism="NATL2A", verbose=True)
```

### Example 6: Pick one DM unambiguously, then drill down

```
Step 1: list_derived_metrics(search_text="damping ratio")
        → copy the derived_metric_id of the best match

Step 2: genes_by_numeric_metric(
          derived_metric_ids=["derived_metric:...:damping_ratio"],
          bucket=["top_decile"])
        → top-decile genes by transcript-to-protein damping
```

## Chaining patterns

```
list_derived_metrics → gene_derived_metrics(locus_tags, derived_metric_ids)
list_derived_metrics(value_kind='numeric', rankable=True) → genes_by_numeric_metric(derived_metric_ids, bucket=[...])
list_derived_metrics(value_kind='boolean') → genes_by_boolean_metric(derived_metric_ids, flag=True)
list_derived_metrics(value_kind='categorical') → genes_by_categorical_metric(derived_metric_ids, categories=[...])
```

## Common mistakes

- Call this FIRST before drill-downs. Inspect rankable / has_p_value / value_kind / allowed_categories / compartment here — the downstream drill-down tools (genes_by_numeric_metric, genes_by_boolean_metric, genes_by_categorical_metric) hard-fail (by design) when the selected DM set doesn't support the requested filter. E.g. passing bucket=['top_decile'] with a non-rankable DM raises; passing significant_only=True when no selected DM has has_p_value=True raises.

- metric_type is a category tag, not a primary key — the same metric_type can appear across organisms or publications (periodic_in_coculture_LD exists once for NATL2A and once for MIT1002). Use derived_metric_ids to pin one specific DM; use metric_types to union across every DM with that tag.

- has_p_value=True returns zero rows against today's KG — no DM currently carries p-values. The filter exists for forward-compat; drill-down p-value filters (significant_only, max_adjusted_p_value) will raise with a diagnostic error.

- allowed_categories is non-null only when value_kind='categorical'. For boolean and numeric DMs it is null — not a bug.

```mistake
list_derived_metrics(rankable="true")
```

```correction
list_derived_metrics(rankable=True)
```

```mistake
list_derived_metrics(organism="Prochlorococcus MED4 strain")
```

```correction
list_derived_metrics(organism="MED4")
```

## Package import equivalent

```python
from multiomics_explorer import list_derived_metrics

result = list_derived_metrics()
# returns dict with keys: total_entries, total_matching, by_organism, by_value_kind, by_metric_type, by_compartment, by_omics_type, by_treatment_type, by_background_factors, by_growth_phase, score_max, score_median, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
