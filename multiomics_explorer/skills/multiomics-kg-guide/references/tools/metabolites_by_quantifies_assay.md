# metabolites_by_quantifies_assay

## What it does

Numeric MetaboliteAssay edges — one row per metabolite × assay edge with its value; cross-organism.

Use for values, detection status and rankable cutoffs; pre-flight `list_metabolite_assays`; flags `metabolites_by_flags_assay`, both arms `assays_by_metabolite`.
Filters: assay_ids, organism, metabolite_ids, min/max_value, detection_status, timepoint, metric_bucket, min/max_percentile, max_rank.
Returns: by_detection_status, by_metric_bucket, by_assay, by_metric, excluded_assays; one row = one edge. Tested-absent rows kept.
docs://tools/metabolites_by_quantifies_assay; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| assay_ids | list[string] | — | MetaboliteAssay IDs to drill into (full prefixed). Discover via `list_metabolite_assays(value_kind='numeric')`. E.g. ['metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration']. `not_found.assay_ids` lists IDs absent from the KG. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| metabolite_ids | list[string] \| None | None | Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites). |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap. |
| experiment_ids | list[string] \| None | None | Filter to assays from these experiments. |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| min_value | float \| None | None | Lower bound on `value` (raw concentration / intensity). **Caution**: `value > 0` strips tested-absent rows (`value=0` / `detection_status='not_detected'`) — use deliberately, never as default. See `docs://guide/conventions`. |
| max_value | float \| None | None | Upper bound on `value`. Always applicable. |
| detection_status | list[string] \| None | None | Detection-status filter — primary qualitative headline. Values: 'detected', 'sporadic', 'not_detected'. Excluding 'not_detected' strips tested-absent rows; surface as caller choice, never default. See `docs://guide/conventions`. |
| timepoint | list[string] \| None | None | Timepoint label(s) — exact match. E.g. ['4 days'], ['6 days']. Non-temporal experiments expose no timepoint here (rows surface with `timepoint=null`). |
| metric_bucket | list[string] \| None | None | Bucket label(s) — subset of {'top_decile','top_quartile','mid','low'}. **Rankable-gated** — raises if every selected assay has `rankable=false`. Soft-excludes non-rankable assays from mixed input (surfaced in envelope `excluded_assays`). Tested-absent rows (`detection_status='not_detected'`) never match — their `metric_bucket` is nulled for display regardless of the stored value. |
| min_percentile | float \| None | None | Lower bound on `metric_percentile` (0-100). **Rankable-gated.** Tested-absent rows (`detection_status='not_detected'`) never match — their `metric_percentile` is nulled for display. |
| max_percentile | float \| None | None | Upper bound on `metric_percentile`. **Rankable-gated.** Tested-absent rows (`detection_status='not_detected'`) never match — their `metric_percentile` is nulled for display. |
| max_rank | int \| None | None | Cap on `rank_by_metric` (1 = highest). Top-N drill-down. **Rankable-gated.** Tested-absent rows (`detection_status='not_detected'`) never match — their `rank_by_metric` is nulled for display. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Canonical drill-down — MIT9313 chitosan rankable assay

```python
metabolites_by_quantifies_assay(assay_ids=["metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration"])
```

## Response sketch

```expected-keys
total_matching, by_detection_status, by_metric_bucket, by_assay, by_compartment, by_organism, by_metric, excluded_assays, warnings, resolved_aliases, not_found, returned, truncated, offset, results
```

Result row: `metabolite_id, name, kegg_compound_id, value, value_sd, n_replicates, n_non_zero, metric_type, metric_bucket, metric_percentile, rank_by_metric, detection_status, …`

## Common mistakes

- Numeric arm only (`Assay_quantifies_metabolite`). Siblings: `metabolites_by_flags_assay` is the boolean-arm twin (presence flags, no values); `assays_by_metabolite` is the metabolite-anchored reverse lookup over both arms.

```mistake
A requested assay_id silently disappears from the results and not_found.assay_ids stays empty.
```

```correction
A boolean assay_id is genuinely found (it exists as `value_kind='boolean'`)
but this tool only drills numeric edges — it's excluded from
`not_found.assay_ids` and reported via a `warnings` entry naming
`metabolites_by_flags_assay` as the tool to use instead.

```

```mistake
Filter out value=0 / flag_value=false rows assuming they are noise.
```

```correction
These rows are tested-absent — the metabolite was assayed and not found.
They are biology. Keep them unless explicitly investigating presence-only.

```

## Chaining patterns

- list_metabolite_assays(rankable=True, value_kind='numeric') → metabolites_by_quantifies_assay(assay_ids=[...])  # pre-flight: confirm rankable-gated filters apply
- metabolites_by_quantifies_assay → assays_by_metabolite(metabolite_ids=[...])  # boolean evidence + cross-organism reverse view
- metabolites_by_quantifies_assay → genes_by_metabolite(metabolite_ids=[...], organism=...)  # gene catalysts/transporters of these metabolites
- metabolites_by_quantifies_assay → metabolites_by_gene(locus_tags=[...], organism=...)  # gene-anchored chemistry context

Full reference (all examples, full response format, verbose fields): `docs://tools/metabolites_by_quantifies_assay/full`
