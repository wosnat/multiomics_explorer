# list_metabolite_assays

## What it does

Discover MetaboliteAssay nodes — the metabolomics measurement layer, mirroring `list_derived_metrics`.

Use as the pre-flight that reads value_kind and rankable; drill down with `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay` or `assays_by_metabolite`.
Filters: search_text, organism, value_kind, compartment, assay_ids, metabolite_ids, rankable, plus publication / experiment / condition.
Returns: by_organism, by_value_kind, by_compartment, by_detection_status, not_found; one row = one assay with detection_status_counts.
docs://tools/list_metabolite_assays; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Full-text search over MetaboliteAssay name, field_description, treatment, experimental_context. E.g. 'chitosan', 'cellular concentration', 'KEGG export'. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| metric_types | list[string] \| None | None | Filter by metric_type tags. Live values: 'cellular_concentration', 'extracellular_concentration', 'presence_flag_intracellular', 'presence_flag_extracellular'. |
| value_kind | string ('numeric', 'boolean') \| None | None | 'numeric' → metabolites_by_quantifies_assay drill-down; 'boolean' → metabolites_by_flags_assay. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| experiment_ids | list[string] \| None | None | Experiment node id(s). |
| assay_ids | list[string] \| None | None | MetaboliteAssay id(s). `not_found.assay_ids` lists unknowns. |
| metabolite_ids | list[string] \| None | None | Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites). |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap. |
| rankable | bool \| None | None | True → assays supporting rank/percentile/bucket on metabolites_by_quantifies_assay's rankable-gated filters. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 20 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Orient — what assays exist

```python
list_metabolite_assays(summary=True)
```

## Response sketch

```expected-keys
total_entries, total_matching, metabolite_count_total, by_organism, by_value_kind, by_compartment, top_metric_types, by_treatment_type, by_background_factors, by_growth_phase, by_detection_status, score_max, score_median, returned, offset, truncated, not_found, resolved_aliases, warnings, results
```

Result row: `assay_id, name, metric_type, value_kind, rankable, unit, field_description, organism_name, experiment_id, publication_doi, compartment, omics_type, …`

## Common mistakes

```mistake
Filter out value=0 / flag_value=false rows on drill-downs assuming they're noise.
```

```correction
Those rows are tested-absent — the metabolite was *assayed and not found*. Real biology. Keep them unless explicitly investigating presence-only.
```

```mistake
A metabolite missing from drill-down results means it was not detected.
```

```correction
Missing means *unmeasured* (not in the assay's scope). For 'tested and not found,' look for value=0 / flag_value=false / detection_status='not_detected' rows in the drill-down output.
```

```mistake
growth_phases=[] means the assay has no growth-state metadata.
```

```correction
growth_phases=[] reflects unpopulated KG state (KG-side backfill pending). The schema field exists; values populate without explorer-side code change when the upstream backfill lands.
```

## Chaining patterns

- list_metabolite_assays → metabolites_by_quantifies_assay(assay_ids=[...])
- list_metabolite_assays → metabolites_by_flags_assay(assay_ids=[...])
- list_metabolite_assays → assays_by_metabolite(metabolite_ids=[...])  # cross-organism reverse view
- list_metabolite_assays → list_metabolites(metabolite_ids=[...])  # chemistry context for measured compounds

Full reference (all examples, full response format, verbose fields): `docs://tools/list_metabolite_assays/full`
