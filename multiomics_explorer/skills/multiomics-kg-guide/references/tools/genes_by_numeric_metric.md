# genes_by_numeric_metric

## What it does

Pass `derived_metric_ids` XOR `metric_types` (one required); rankable-gated filters (`bucket`, `min/max_percentile`, `max_rank`) raise if every selected DM has `rankable=False` and soft-exclude on mixed input — inspect `list_derived_metrics(value_kind='numeric', rankable=True)` first to see which DMs support which filters.

Numeric DM drill-down — one row per gene × DM. `r.value` (float) is
always returned; `rank_by_metric` / `metric_percentile` /
`metric_bucket` are populated only on rows from rankable DMs (null
otherwise — same shape as `gene_derived_metrics`). Cross-organism by
design; envelope `by_organism` and per-row `organism_name` make
cross-strain rows self-describing. The `by_metric` envelope rollup
pairs filtered-slice value distribution with full-DM distribution
(precomputed) so callers can read "your top-decile slice 12.2-25.3
out of full DM range 0-28" directly.

`excluded_derived_metrics` + `warnings` envelope keys are the
primary diagnostic when a real DM produces zero rows; check these
before assuming the result is empty for biological reasons.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| derived_metric_ids | list[string] \| None | None | DerivedMetric node IDs to drill into. Use when the same `metric_type` appears across publications / organisms and you need to pin one. Discover IDs via `list_derived_metrics`. Mutually exclusive with `metric_types`. |
| metric_types | list[string] \| None | None | Metric-type tags (e.g. ['damping_ratio', 'diel_amplitude_protein_log2']). Unions every DM carrying that tag, then narrows by scoping filters. Same tag can appear across organisms (e.g. 'cell_abundance_biovolume_normalized' is on both MIT9312 and MIT9313 today). Mutually exclusive with `derived_metric_ids`. |
| organism | string \| None | None | Organism to scope the DM set to. Accepts short strain code ('MED4', 'NATL2A', 'MIT9312') or full name. Case-insensitive substring match. Single-organism is **not** enforced — omit to drill across all organisms a metric_type spans. |
| locus_tags | list[string] \| None | None | Restrict drill-down to a specific gene set (e.g. DE hits from `differential_expression_by_gene`). Filter on `g.locus_tag IN $locus_tags` post-MATCH. Genes with no edge for the selected DM produce no row (silent — surfaced via `total_genes` shortfall). |
| experiment_ids | list[string] \| None | None | Scope to DMs from one or more experiments. |
| publication_doi | list[string] \| None | None | Scope to DMs from one or more publications. |
| compartment | string \| None | None | Sample compartment ('whole_cell', 'vesicle', 'exoproteome', 'spent_medium', 'lysate'). Exact match. |
| treatment_type | list[string] \| None | None | Treatment type(s) (e.g. ['diel', 'compartment']). ANY-overlap. Case-insensitive. |
| background_factors | list[string] \| None | None | Background factor(s) (e.g. ['axenic', 'light']). ANY-overlap. Case-insensitive. |
| growth_phases | list[string] \| None | None | Growth phase(s). ANY-overlap. Case-insensitive. |
| min_value | float \| None | None | Lower bound on `r.value`. Always applicable — no gate. Use for raw-threshold queries on non-rankable DMs (e.g. mascot probability >= 99). |
| max_value | float \| None | None | Upper bound on `r.value`. Always applicable. |
| min_percentile | float \| None | None | Lower bound on `r.metric_percentile` (0-100). **Rankable-gated** — raises if every selected DM has `rankable=False`. Soft-excludes non-rankable DMs from mixed input, surfaced in `excluded_derived_metrics`. |
| max_percentile | float \| None | None | Upper bound on `r.metric_percentile`. **Rankable-gated.** |
| bucket | list[string] \| None | None | Bucket label(s) — subset of {'top_decile','top_quartile','mid','low'}. **Rankable-gated.** Today's KG buckets correspond to decile / quartile splits computed at import time per DM. |
| max_rank | int \| None | None | Cap on `r.rank_by_metric` (1 = highest). Use for top-N drill-down. **Rankable-gated.** |
| significant_only | bool | False | Filter to `r.significant=true`. **has_p_value-gated** — raises against today's KG (no DM has p-values yet). Forward-compat surface; check `list_derived_metrics(has_p_value=True)` before using. |
| max_adjusted_p_value | float \| None | None | Upper bound on `r.adjusted_p_value`. **has_p_value-gated**. |
| summary | bool | False | Return summary fields only (counts, breakdowns, by_metric, diagnostics). Sugar for limit=0; results=[]. |
| verbose | bool | False | Include heavy text fields per row: gene_function_description, gene_summary, plus DM context (metric_type, field_description, unit, compartment, experiment_id, publication_doi, treatment_type, background_factors, treatment, light_condition, experimental_context). p_value (raw) is reserved for future has_p_value DMs. |
| limit | int | 5 | Max rows to return. Paginate with `offset`. Use `summary=True` for summary-only (sets limit=0). |
| offset | int | 0 | Pagination offset (starting row, 0-indexed). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_metric, top_categories, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, returned, offset, truncated, results
```

- **total_matching** (int): Rows after all filters + gate exclusion.
- **total_derived_metrics** (int): Distinct DMs contributing rows.
- **total_genes** (int): Distinct genes in results.
- **by_organism** (list[GenesByNumericMetricOrganismBreakdown]): Rows per organism.
- **by_compartment** (list[GenesByNumericMetricCompartmentBreakdown]): Rows per compartment.
- **by_publication** (list[GenesByNumericMetricPublicationBreakdown]): Rows per publication.
- **by_experiment** (list[GenesByNumericMetricExperimentBreakdown]): Rows per experiment.
- **by_metric** (list[GenesByNumericMetricBreakdown]): Per-DM rollup: filtered-slice value distribution + full-DM context. Sorted by count desc.
- **top_categories** (list[GenesByNumericMetricCategoryBreakdown]): Top 5 gene categories by count.
- **genes_per_metric_max** (int): Largest per-DM gene count.
- **genes_per_metric_median** (float): Median per-DM gene count.
- **not_found_ids** (list[string]): `derived_metric_ids` inputs not present in KG.
- **not_matched_ids** (list[string]): `derived_metric_ids` in KG but produced 0 rows after edge-level filters (excludes gate-excluded DMs).
- **not_found_metric_types** (list[string]): `metric_types` inputs that match no DM after scoping.
- **not_matched_metric_types** (list[string]): `metric_types` whose DMs produced 0 rows.
- **not_matched_organism** (string | None): `organism` arg that matched no surviving DM.
- **excluded_derived_metrics** (list[ExcludedDerivedMetric]): DMs dropped by rankable / has_p_value gate. Always present (empty list when no exclusions).
- **warnings** (list[string]): Human-readable summary of excluded_derived_metrics.
- **returned** (int): Length of results list.
- **offset** (int): Pagination offset used.
- **truncated** (bool): True when total_matching > offset + returned.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM1545'). |
| gene_name | string \| None (optional) | Gene name (e.g. 'rpsH'); null when KG has none. |
| product | string \| None (optional) | Gene product (e.g. '30S ribosomal protein S8'). |
| gene_category | string \| None (optional) | Functional category (e.g. 'Translation'). |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4'). |
| derived_metric_id | string | Unique parent-DM id. |
| name | string | DM human label. |
| value_kind | string | Always 'numeric' for this tool; kept for cross-tool row-shape consistency with `gene_derived_metrics`. |
| rankable | bool | Echoed from parent DM; True iff `rank_by_metric`/`metric_percentile`/`metric_bucket` carry data. |
| has_p_value | bool | Echoed from parent DM; True iff `adjusted_p_value`/`significant` carry data (none in current KG). |
| value | float | Measurement value. |
| rank_by_metric | int \| None (optional) | Rank by value (1=highest). Populated only when rankable=True. |
| metric_percentile | float \| None (optional) | Percentile (0-100). Same gate as rank_by_metric. |
| metric_bucket | string \| None (optional) | Bucket label (top_decile / top_quartile / mid / low). Same gate. |
| adjusted_p_value | float \| None (optional) | BH-adjusted p-value. Populated only when has_p_value=True. None in current KG. |
| significant | bool \| None (optional) | Significance flag. Same gate as adjusted_p_value. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| metric_type | string \| None (optional) | Category tag. Verbose only. |
| field_description | string \| None (optional) | Detailed explanation of what this DM measures. Verbose only. |
| unit | string \| None (optional) | Measurement unit. Verbose only. |
| compartment | string \| None (optional) | Sample compartment. Verbose only. |
| experiment_id | string \| None (optional) | Parent experiment id. Verbose only. |
| publication_doi | string \| None (optional) | Parent publication DOI. Verbose only. |
| treatment_type | list[string] (optional) | Treatment type(s). Verbose only. |
| background_factors | list[string] (optional) | Background factor(s). Verbose only. |
| treatment | string \| None (optional) | Treatment description in plain language. Verbose only. |
| light_condition | string \| None (optional) | Light regime. Verbose only. |
| experimental_context | string \| None (optional) | Longer experimental setup description. Verbose only. |
| gene_function_description | string \| None (optional) | Gene functional description (gene-level). Verbose only. |
| gene_summary | string \| None (optional) | Gene summary text (gene-level). Verbose only. |
| p_value | float \| None (optional) | Raw p-value; gated on has_p_value=True. Verbose only. None in current KG. |

## Few-shot examples

### Example 1: Canonical worked example — top-decile damping_ratio

```example-call
genes_by_numeric_metric(metric_types=['damping_ratio'], bucket=['top_decile'])
```

```example-response
{
  "total_matching": 32,
  "total_derived_metrics": 1,
  "total_genes": 32,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 32}],
  "by_compartment": [{"compartment": "whole_cell", "count": 32}],
  "by_publication": [{"publication_doi": "10.1371/journal.pone.0043432", "count": 32}],
  "by_experiment": [{"experiment_id": "10.1371/journal.pone.0043432_med4_diel", "count": 32}],
  "by_metric": [
    {"derived_metric_id": "derived_metric:journal.pone.0043432:table_s2_waldbauer_diel_metrics:damping_ratio", "metric_type": "damping_ratio", "name": "Transcript:protein amplitude ratio", "value_kind": "numeric", "count": 32, "rank_min": 1, "rank_max": 32, "value_min": 12.2, "value_q1": 13.7, "value_median": 15.9, "value_q3": 20.5, "value_max": 25.3, "dm_value_min": 0.2, "dm_value_q1": 2.8, "dm_value_median": 4.9, "dm_value_q3": 7.8, "dm_value_max": 25.3}
  ],
  "top_categories": [
    {"gene_category": "Translation", "count": 6},
    {"gene_category": "Carbohydrate metabolism", "count": 5},
    {"gene_category": "Photosynthesis", "count": 5}
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
  "returned": 32,
  "offset": 0,
  "truncated": false,
  "results": [
    {"locus_tag": "PMM1545", "gene_name": "rpsH", "product": "30S ribosomal protein S8", "gene_category": "Translation", "organism_name": "Prochlorococcus MED4", "derived_metric_id": "derived_metric:journal.pone.0043432:table_s2_waldbauer_diel_metrics:damping_ratio", "name": "Transcript:protein amplitude ratio", "value_kind": "numeric", "rankable": true, "has_p_value": false, "value": 25.3, "rank_by_metric": 1, "metric_percentile": 100.0, "metric_bucket": "top_decile"},
    {"locus_tag": "PMM0930", "gene_name": "phdB", "product": "pyruvate dehydrogenase E1 component beta subunit", "gene_category": "Carbohydrate metabolism", "organism_name": "Prochlorococcus MED4", "derived_metric_id": "derived_metric:journal.pone.0043432:table_s2_waldbauer_diel_metrics:damping_ratio", "name": "Transcript:protein amplitude ratio", "value_kind": "numeric", "rankable": true, "has_p_value": false, "value": 23.0, "rank_by_metric": 2, "metric_percentile": 99.68, "metric_bucket": "top_decile"}
  ]
}
```

### Example 2: Soft-exclude — mixed rankable + non-rankable metric_types

```example-call
genes_by_numeric_metric(metric_types=['damping_ratio', 'peak_time_protein_h'], bucket=['top_decile'])
```

```example-response
{
  "total_matching": 32,
  "total_derived_metrics": 1,
  "total_genes": 32,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 32}],
  "by_metric": [
    {"derived_metric_id": "derived_metric:journal.pone.0043432:table_s2_waldbauer_diel_metrics:damping_ratio", "metric_type": "damping_ratio", "value_kind": "numeric", "count": 32, "value_min": 12.2, "value_max": 25.3, "dm_value_min": 0.2, "dm_value_max": 25.3}
  ],
  "not_matched_metric_types": ["peak_time_protein_h"],
  "excluded_derived_metrics": [
    {"derived_metric_id": "derived_metric:journal.pone.0043432:table_s2_waldbauer_diel_metrics:peak_time_protein_h", "metric_type": "peak_time_protein_h", "rankable": false, "has_p_value": false, "reason": "non-rankable; `bucket` filter does not apply"}
  ],
  "warnings": ["1 non-rankable DM(s) excluded by `bucket` filter (peak_time_protein_h)"],
  "returned": 32,
  "offset": 0,
  "truncated": false,
  "results": [
    {"locus_tag": "PMM1545", "gene_name": "rpsH", "value": 25.3, "rank_by_metric": 1, "metric_bucket": "top_decile"}
  ]
}
```

### Example 3: Cross-organism — same metric_type spans two strains

```example-call
genes_by_numeric_metric(metric_types=['cell_abundance_biovolume_normalized'], bucket=['top_quartile'])
```

```example-response
{
  "total_matching": 308,
  "total_derived_metrics": 2,
  "total_genes": 308,
  "by_organism": [
    {"organism_name": "Prochlorococcus MIT9313", "count": 156},
    {"organism_name": "Prochlorococcus MIT9312", "count": 152}
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 308}],
  "by_metric": [
    {"derived_metric_id": "derived_metric:1462-2920.15834:s3_mit9313_abundance:cell_abundance_biovolume_normalized", "metric_type": "cell_abundance_biovolume_normalized", "name": "MIT9313 whole-cell protein abundance (biovolume-normalized, Trypsin/Lys-C)", "count": 156, "value_kind": "numeric"},
    {"derived_metric_id": "derived_metric:1462-2920.15834:s3_mit9312_abundance:cell_abundance_biovolume_normalized", "metric_type": "cell_abundance_biovolume_normalized", "name": "MIT9312 whole-cell protein abundance (biovolume-normalized, Trypsin/Lys-C)", "count": 152, "value_kind": "numeric"}
  ],
  "top_categories": [
    {"gene_category": "Translation", "count": 51},
    {"gene_category": "Unknown", "count": 39},
    {"gene_category": "Stress response and adaptation", "count": 35}
  ],
  "not_matched_organism": null,
  "warnings": [],
  "returned": 308,
  "truncated": false,
  "results": [
    {"locus_tag": "PMT9312_1674", "gene_name": "hemF", "organism_name": "Prochlorococcus MIT9312", "value": 4.6e-08, "rank_by_metric": 103, "metric_bucket": "top_quartile"}
  ]
}
```

### Example 4: Summary-only — distribution context without per-row drill-down

```example-call
genes_by_numeric_metric(metric_types=['damping_ratio'], summary=True)
```

```example-response
{
  "total_matching": 312,
  "total_derived_metrics": 1,
  "total_genes": 312,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 312}],
  "by_compartment": [{"compartment": "whole_cell", "count": 312}],
  "by_metric": [
    {"derived_metric_id": "derived_metric:journal.pone.0043432:table_s2_waldbauer_diel_metrics:damping_ratio", "metric_type": "damping_ratio", "name": "Transcript:protein amplitude ratio", "count": 312, "value_kind": "numeric", "value_min": 0.2, "value_q1": 2.8, "value_median": 4.9, "value_q3": 7.8, "value_max": 25.3, "dm_value_min": 0.2, "dm_value_max": 25.3}
  ],
  "genes_per_metric_max": 312,
  "genes_per_metric_median": 312.0,
  "warnings": [],
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "results": []
}
```

### Example 5: DE → top hits → numeric DM intersection

```
Step 1: differential_expression_by_gene(organism="MED4", significant_only=True, limit=20)
        → extract `locus_tag` from each result row (top-20 |log2FC|).

Step 2: genes_by_numeric_metric(
          metric_types=["damping_ratio"],
          locus_tags=[<those 20 locus_tags>])
        → re-rank within those genes only; check which DE hits also
          lead the damping_ratio distribution (per-row `rank_by_metric`,
          `metric_percentile`, `metric_bucket`).

Step 3 (drill-down): gene_overview(locus_tags=[<intersected genes>])
        → routing context for the genes that are both DE-significant
          AND high-damping.
```

## Chaining patterns

```
list_derived_metrics(value_kind='numeric', rankable=True) → genes_by_numeric_metric(derived_metric_ids=[...], bucket=[...])
differential_expression_by_gene → top hits → genes_by_numeric_metric(metric_types=[...], locus_tags=hits)
genes_by_numeric_metric → gene_overview(locus_tags=results)
```

## Good to know

- Non-rankable DM + rankable-gated filter. Calling with `metric_types=['peak_time_transcript_h']` + `bucket=['top_decile']` raises — `peak_time_transcript_h` is non-rankable. Inspect `list_derived_metrics(value_kind='numeric', rankable=True)` to see which DMs support `bucket` / `min_percentile` / `max_percentile` / `max_rank`. Mixed rankable/non-rankable DM sets don't raise — instead the envelope's `excluded_derived_metrics` + `warnings` pinpoint the excluded ones.

- P-value filter on current KG. `significant_only=True` or `max_adjusted_p_value=0.05` raises today because no DM has `has_p_value='true'`. The surface exists for future DMs; check `list_derived_metrics(has_p_value=True)` first.

- Sparse columns in results. `rank_by_metric` / `metric_percentile` / `metric_bucket` are null in rows from non-rankable DMs (e.g. `peak_time_*_h`); don't treat null as missing data — it's gate-driven. Per-row `rankable` (echoed from the parent DM) tells you which to expect.

- Cross-organism by default. No single-organism enforcement. `metric_types=['cell_abundance_biovolume_normalized']` returns rows from MIT9312 AND MIT9313 (the same metric_type spans both). Use `organism='MIT9312'` to scope; check per-row `organism_name` and envelope `by_organism` for cross-strain rows.

- `by_metric` is per-DM, not per-tag. Each `by_metric` entry is one DerivedMetric (uniquely identified by `derived_metric_id`). The same `metric_type` tag can appear across organisms (4 such tags in current KG). Use the per-DM rollup to disambiguate.

- Wrong-`value_kind` IDs land in `not_found_ids`, not a typed error. Passing a `derived_metric_ids` of a boolean or categorical DM today produces `not_found_ids=[that_id]` rather than a `value_kind` mismatch error — the diagnostics query hardcodes `value_kind='numeric'`, so non-numeric DMs simply don't appear in the result. Inspect via `list_derived_metrics(derived_metric_ids=[...])` to see the DM's actual `value_kind` and pivot to `genes_by_boolean_metric` or `genes_by_categorical_metric`. Slice-1 simplification — a richer 'wrong value_kind' diagnostic ships in a follow-up.

- Filtered slice vs full DM. `by_metric[i].value_*` describes rows that survived your filters. `by_metric[i].dm_value_*` describes the full DM (precomputed). They're different — your top-decile slice is intentionally narrower than the full DM range.

## Package import equivalent

```python
from multiomics_explorer import genes_by_numeric_metric

result = genes_by_numeric_metric()
# returns dict with keys: total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_metric, top_categories, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
