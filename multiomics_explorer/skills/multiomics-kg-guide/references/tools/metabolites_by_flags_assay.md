# metabolites_by_flags_assay

## What it does

Boolean MetaboliteAssay edges — one row per metabolite × flag edge; cross-organism. flag_value=False rows are tested-absent: both states are stored.

Use for presence / absence calls; pre-flight `list_metabolite_assays`; values `metabolites_by_quantifies_assay`, both arms `assays_by_metabolite`.
Filters: assay_ids, organism, metabolite_ids, flag_value, plus publication / experiment / condition.
Returns: by_value, by_assay, by_metric, not_found, excluded_assays (empty here, for parity with the numeric twin); one row = one flag.
docs://tools/metabolites_by_flags_assay; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| assay_ids | list[string] | — | MetaboliteAssay IDs to drill into. Discover via `list_metabolite_assays(value_kind='boolean')`. E.g. ['metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular']. `not_found.assay_ids` lists IDs absent from the KG. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| metabolite_ids | list[string] \| None | None | Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites). |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap. |
| experiment_ids | list[string] \| None | None | Filter to assays from these experiments. |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| flag_value | bool \| None | None | Filter by flag presence — `True` (presence flagged), `False` (absence flagged — *tested-absent*, real biology), `None` (both). `Assay_flags_metabolite` always stores both states (unlike the DM layer, where only 11 of 27 boolean DMs store `not_flagged`), so `flag_value=False` returns real rows (about 69% of boolean rows). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Canonical drill-down — msystems intracellular presence-flags

```python
metabolites_by_flags_assay(assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"])
```

## Response sketch

```expected-keys
total_matching, by_value, by_assay, by_compartment, by_organism, by_metric, excluded_assays, warnings, resolved_aliases, not_found, returned, truncated, offset, results
```

Result row: `metabolite_id, name, kegg_compound_id, flag_value, n_positive, n_replicates, metric_type, condition_label, assay_id, organism_name, compartment, assay_name, …`

## Common mistakes

- Boolean arm only (`Assay_flags_metabolite`). Siblings: `metabolites_by_quantifies_assay` is the numeric-arm twin (values, detection_status, rankable buckets); `assays_by_metabolite` is the metabolite-anchored reverse lookup over both arms.

```mistake
A requested assay_id silently disappears from the results and not_found.assay_ids stays empty.
```

```correction
`not_found.assay_ids` is a real existence check — an unknown assay_id lands
there. A numeric assay_id is genuinely found (it exists as
`value_kind='numeric'`) but this tool only drills boolean edges — it's
excluded from `not_found.assay_ids` and reported via a `warnings` entry
naming `metabolites_by_quantifies_assay` as the tool to use instead.

```

```mistake
Filter out value=0 / flag_value=false rows assuming they are noise.
```

```correction
These rows are tested-absent — the metabolite was assayed and not found.
They are biology. Keep them unless explicitly investigating presence-only.

```

## Chaining patterns

- list_metabolite_assays(value_kind='boolean') → metabolites_by_flags_assay(assay_ids=[...])  # discovery → drill-down
- metabolites_by_flags_assay → assays_by_metabolite(metabolite_ids=[...])  # quantifies-arm complement (cross-organism reverse view)
- metabolites_by_flags_assay → genes_by_metabolite(metabolite_ids=[...], organism=...)  # gene catalysts/transporters of these metabolites
- metabolites_by_flags_assay → metabolites_by_gene(locus_tags=[...], organism=...)  # gene-anchored chemistry context

Full reference (all examples, full response format, verbose fields): `docs://tools/metabolites_by_flags_assay/full`
