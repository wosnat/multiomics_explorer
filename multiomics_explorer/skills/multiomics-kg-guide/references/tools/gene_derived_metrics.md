# gene_derived_metrics

## What it does

Polymorphic `value` column — branch on `value_kind` per row; consult `list_derived_metrics(value_kind=...)` first to know which DMs exist and whether numeric rows carry rank/percentile/bucket extras (rankable gate) or `adjusted_p_value`/`significant` (has_p_value gate).

Gene-centric batch lookup for DerivedMetric annotations — one row
per gene × DM. `value` is `float` on numeric rows, `'true'`/'false'`
on boolean rows, category string on categorical rows. Numeric extras
(rank_by_metric, metric_percentile, metric_bucket) are populated
only when the parent DM is rankable; null otherwise. Same gate for
adjusted_p_value / significant on has_p_value DMs (none in the
current KG).

Single organism enforced. not_found (locus_tag absent from KG) and
not_matched (in KG but no DM rows after filters — includes
kind-mismatch when value_kind is set) make empty rows diagnosable.
For edge-level numeric filters (bucket / percentile / rank / value
thresholds), pivot to genes_by_numeric_metric.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up (e.g. ['PMM1714', 'PMM0001']). Required, non-empty. Single organism enforced — locus_tags must all resolve to the same organism (or pair with `organism` to disambiguate). |
| organism | string \| None | None | Organism to scope to. Accepts short strain code ('MED4', 'NATL2A', 'MIT1002') or full name. Case-insensitive substring match. Inferred from locus_tags when omitted. |
| metric_types | list[string] \| None | None | Filter by metric_type tags (e.g. 'diel_amplitude_protein_log2'). Same metric_type may appear across publications — pair with publication_doi or use derived_metric_ids to pin one specific DM. |
| value_kind | string ('numeric', 'boolean', 'categorical') \| None | None | Restrict to one DM kind. Each kind has a different `value` column type — 'numeric' → float, 'boolean' → 'true'/'false', 'categorical' → category string. |
| compartment | string \| None | None | Filter to DMs from one sample compartment ('whole_cell', 'vesicle', 'exoproteome', 'spent_medium', 'lysate'). Exact match. |
| treatment_type | list[string] \| None | None | Treatment type(s) to match. Returns DMs whose treatment_type list overlaps ANY of the given values. Case-insensitive. |
| background_factors | list[string] \| None | None | Background experimental factor(s) to match. ANY-overlap. Case-insensitive. |
| publication_doi | list[string] \| None | None | Filter by one or more publication DOIs. Exact match. |
| derived_metric_ids | list[string] \| None | None | Look up specific DMs by their unique id. Use to pin one DM when the same metric_type appears across publications. Pair with `list_derived_metrics`. |
| summary | bool | False | Return summary fields only (counts, breakdowns, not_found / not_matched). Sugar for limit=0; results=[]. |
| verbose | bool | False | Include detailed text fields per row: treatment, light_condition, experimental_context, plus raw p_value when parent DM has_p_value=True. |
| limit | int | 5 | Max rows to return. Paginate with offset. Use `summary=True` for summary-only (sets limit=0 internally). |
| offset | int | 0 | Pagination offset (starting row, 0-indexed). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, total_derived_metrics, genes_with_metrics, genes_without_metrics, not_found, not_matched, by_value_kind, by_metric_type, by_metric, by_compartment, by_treatment_type, by_background_factors, by_publication, returned, offset, truncated, results
```

- **total_matching** (int): Gene × DM rows matching all filters.
- **total_derived_metrics** (int): Distinct DMs touching the input genes after filters.
- **genes_with_metrics** (int): Input genes with >=1 matching DM row.
- **genes_without_metrics** (int): Input genes present in KG but with zero matching DM rows after filters.
- **not_found** (list[string]): Input locus_tags absent from the KG (echo).
- **not_matched** (list[string]): Input locus_tags in KG but with zero DM rows after filters (includes kind-mismatch when value_kind set).
- **by_value_kind** (list[GeneDmValueKindBreakdown]): Rows per value_kind.
- **by_metric_type** (list[GeneDmMetricTypeBreakdown]): Rows per metric_type — coarse rollup; same metric_type may aggregate across publications.
- **by_metric** (list[GeneDmMetricBreakdown]): Rows per unique DerivedMetric — fine breakdown that disambiguates within a metric_type. Each entry embeds name, metric_type, and value_kind so derived_metric_ids can be picked for downstream drill-down. Sorted by count desc.
- **by_compartment** (list[GeneDmCompartmentBreakdown]): Rows per compartment.
- **by_treatment_type** (list[GeneDmTreatmentBreakdown]): Rows per treatment_type (flattened).
- **by_background_factors** (list[GeneDmBackgroundFactorBreakdown]): Rows per background factor (flattened).
- **by_publication** (list[GeneDmPublicationBreakdown]): Rows per parent publication.
- **returned** (int): Length of results list.
- **offset** (int): Pagination offset used.
- **truncated** (bool): True when total_matching > offset + returned.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM1714'). |
| gene_name | string \| None (optional) | Gene name (e.g. 'dnaN') — null when KG has no name. |
| derived_metric_id | string | Unique parent-DM id. Pass to `derived_metric_ids` on genes_by_*_metric drill-downs to pin this exact DM. metric_type, compartment, publication_doi etc. are available in verbose mode or via list_derived_metrics(derived_metric_ids=[...]). |
| value_kind | string ('numeric', 'boolean', 'categorical') | Determines how to interpret `value`. Routes to the matching genes_by_*_metric drill-down. |
| name | string | Human-readable DM name (e.g. 'Transcript:protein amplitude ratio'). Saves a round-trip to list_derived_metrics for opaque metric_type codes. |
| value | float | Polymorphic measurement: float on numeric rows, 'true'/'false' string on boolean rows, category string on categorical rows. Branch on `value_kind`. |
| rankable | bool | Echoed from parent DM. True iff this row's `value` carries rank/percentile/bucket extras. |
| has_p_value | bool | Echoed from parent DM. True iff adjusted_p_value/significant carry data. No DM in current KG has p-values. |
| rank_by_metric | int \| None (optional) | Rank by metric value (1 = highest). Populated only when parent DM rankable=True. |
| metric_percentile | float \| None (optional) | Percentile within metric distribution (0-100). Same gate as rank_by_metric. |
| metric_bucket | string \| None (optional) | Bucket label ('top_decile', 'top_quartile', 'mid', 'low'). Same gate as rank_by_metric. |
| adjusted_p_value | float \| None (optional) | BH-adjusted p-value. Populated only when parent DM has_p_value=True. No DM in current KG has p-values; Cypher RETURN omits this column today. |
| significant | bool \| None (optional) | Significance flag at the DM's p_value_threshold. Same gate as adjusted_p_value. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| metric_type | string \| None (optional) | Category tag for this DM (e.g. 'damping_ratio'). Verbose only. |
| field_description | string \| None (optional) | Detailed explanation of what this DM measures. Verbose only. |
| unit | string \| None (optional) | Measurement unit (e.g. 'hours', 'log2'). Verbose only. |
| allowed_categories | list[string] \| None (optional) | Valid category strings — non-null only on categorical rows. Verbose only. |
| compartment | string \| None (optional) | Sample compartment. Verbose only. |
| treatment_type | list[string] (optional) | Treatment type(s) for the parent experiment. Verbose only. |
| background_factors | list[string] (optional) | Background experimental factors (may be empty). Verbose only. |
| publication_doi | string \| None (optional) | Parent publication DOI. Verbose only. |
| treatment | string \| None (optional) | Treatment description in plain language. Verbose only. |
| light_condition | string \| None (optional) | Light regime. Verbose only. |
| experimental_context | string \| None (optional) | Longer experimental setup description. Verbose only. |
| p_value | float \| None (optional) | Raw p-value. Populated only when parent DM has_p_value=True (none in current KG). Verbose only. |

## Few-shot examples

### Example 1: Gene with all three DM kinds (boolean + categorical + numeric)

```example-call
gene_derived_metrics(locus_tags=["PMM1714"])
```

### Example 2: Mixed-input summary — surfaces by_metric, not_found, not_matched

```example-call
gene_derived_metrics(locus_tags=["PMM1714", "PMM0001", "PMM_FAKE"], summary=True)
```

### Example 3: Kind-filter routing — only boolean DM signal

```example-call
gene_derived_metrics(locus_tags=["PMM1714"], value_kind="boolean")
```

### Example 4: Compartment routing — only vesicle DMs for this gene

```example-call
gene_derived_metrics(locus_tags=["PMM1714"], compartment="vesicle")
```

### Example 5: DE → DM annotation chain

```
Step 1: differential_expression_by_gene(experiment_ids=[...], significant_only=True)
        → extract top hits' locus_tags

Step 2: gene_derived_metrics(locus_tags=top_hits)
        → see which hits have rhythmicity flags / vesicle membership / damping rank

Step 3 (drill-down): genes_by_numeric_metric(
          derived_metric_ids=["derived_metric:...:damping_ratio"],
          bucket=["top_decile"])
        → top-decile damped genes; intersect with DE top hits
```

## Chaining patterns

```
gene_derived_metrics → genes_by_numeric_metric(derived_metric_ids, bucket=[...])
differential_expression_by_gene → gene_derived_metrics(locus_tags)
resolve_gene → gene_derived_metrics(locus_tags)
```

## Common mistakes

- The `value` column is polymorphic — branch on each row's `value_kind` (`'numeric'` → float, `'boolean'` → `'true'`/`'false'` string, `'categorical'` → category string). Numeric rows additionally have `rank_by_metric`, `metric_percentile`, `metric_bucket` populated when their parent DM is rankable; null otherwise (e.g. `peak_time_protein_h`).

- For numeric edge filtering (bucket / percentile / rank / value thresholds), pivot to `genes_by_numeric_metric`. This tool intentionally has no edge-level numeric filters — it is the gene-anchor surface only.

- `not_matched` ≠ no DM signal at all. `not_matched` lists genes that exist in the KG but have zero DM rows AFTER the applied filters. A gene with only boolean DM signal called with `value_kind='numeric'` lands in `not_matched`. Inspect rollup props (`g.numeric_metric_count` etc. via `gene_overview`) for unfiltered availability.

- Single organism enforced. Mixing locus_tags from MED4 and NATL2A raises `ValueError`. Call once per organism.

```mistake
gene_derived_metrics(locus_tags=["PMM1714"], min_value=1.0)
```

```correction
First call gene_derived_metrics(locus_tags=["PMM1714"]); then pivot to genes_by_numeric_metric(derived_metric_ids=[...], min_value=1.0)
```

```mistake
gene_derived_metrics(locus_tags=[])
```

```correction
locus_tags must be non-empty (raises ValueError).
```

## Package import equivalent

```python
from multiomics_explorer import gene_derived_metrics

result = gene_derived_metrics(locus_tags=...)
# returns dict with keys: total_matching, total_derived_metrics, genes_with_metrics, genes_without_metrics, not_found, not_matched, by_value_kind, by_metric_type, by_metric, by_compartment, by_treatment_type, by_background_factors, by_publication, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
