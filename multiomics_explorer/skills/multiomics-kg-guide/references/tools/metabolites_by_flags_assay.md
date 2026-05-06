# metabolites_by_flags_assay

## What it does

Drill into boolean MetaboliteAssay edges — one row per
(metabolite × flag-edge).

`flag_value=False` rows are *tested-absent* — assayed and not
found, real biology. 68.8% of boolean rows in the live KG are
`flag_value=false` (128 of 186 across the 2 boolean assays). A
missing row means *unmeasured*. Distinct (parent §10).

A row with `value=0` / `flag_value=false` /
`detection_status='not_detected'` is *tested-absent* (assayed
and not found, kept in results). A missing row is *unmeasured*
(not in this assay's scope). Don't conflate.

No `by_detection_status` envelope — that field exists only on
the numeric edge. On the boolean arm, `flag_value` IS the
qualitative-detection signal; `by_value` is its envelope rollup.

Drill across:
- `assays_by_metabolite(metabolite_ids=[...])` — quantifies-arm
  complement.
- `genes_by_metabolite(metabolite_ids=[...], organism=...)` —
  chemistry context.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| assay_ids | list[string] | — | MetaboliteAssay IDs to drill into. Discover via `list_metabolite_assays(value_kind='boolean')`. E.g. ['metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular']. `not_found.assay_ids` lists IDs absent from the KG. |
| organism | string \| None | None | Filter to assays from this organism (case-insensitive CONTAINS). Cross-organism is the default. |
| metabolite_ids | list[string] \| None | None | Restrict to specific metabolites (full prefixed IDs, e.g. ['kegg.compound:C00019']). `not_found.metabolite_ids` lists IDs absent from the KG. |
| exclude_metabolite_ids | list[string] \| None | None | Exclude metabolites with these IDs (set-difference). |
| experiment_ids | list[string] \| None | None | Filter to assays from these experiments. |
| publication_doi | list[string] \| None | None | Filter by publication DOI(s). E.g. ['10.1128/msystems.01261-22']. |
| compartment | string \| None | None | Sample compartment ('whole_cell' or 'extracellular'). |
| treatment_type | list[string] \| None | None | Treatment type(s) (ANY-overlap). |
| background_factors | list[string] \| None | None | Background factor(s) (ANY-overlap). |
| growth_phases | list[string] \| None | None | Growth phase(s) (ANY-overlap). Empty `[]` on assays today (KG-MET-017 backfill pending). |
| flag_value | bool \| None | None | Filter by flag presence — `True` (presence flagged), `False` (absence flagged — *tested-absent*, real biology), `None` (both). Unlike `genes_by_boolean_metric` (positive-only KG storage), `Assay_flags_metabolite` stores both true and false flags, so `flag_value=False` returns real rows (68.8% of boolean rows in the live KG). |
| summary | bool | False | Return summary fields only (results=[]). |
| verbose | bool | False | Include heavy-text fields per row: assay_name, field_description. |
| limit | int | 5 | Max rows. Paginate with `offset`. |
| offset | int | 0 | Pagination offset. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, by_value, by_assay, by_compartment, by_organism, by_metric, excluded_assays, warnings, not_found, returned, truncated, offset, results
```

- **total_matching** (int): Row count in the filtered slice.
- **by_value** (list[MfaByValue]): Counts per flag value (true / false). `false` rows are tested-absent (parent §10). Boolean arm has no `by_detection_status` — `flag_value` IS the qualitative-detection signal here.
- **by_assay** (list[MfaByAssay]): Counts per assay_id.
- **by_compartment** (list[MfaByCompartment]): Counts per compartment.
- **by_organism** (list[MfaByOrganism]): Counts per organism (cross-organism by default).
- **by_metric** (list[MfaByMetric]): Per-assay filtered-slice rollup.
- **excluded_assays** (list[string]): Always `[]` here (no gates) — kept for cross-tool envelope-shape consistency.
- **warnings** (list[string]): Always `[]` here (no gates).
- **not_found** (MfaNotFound): Per-batch-input unknown IDs (parent §13.6).
- **returned** (int): Length of `results`.
- **truncated** (bool): True when total_matching > offset + returned.
- **offset** (int): Pagination offset used.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| metabolite_id | string | Metabolite node id. |
| name | string | Canonical metabolite name. |
| kegg_compound_id | string \| None (optional) | KEGG compound id (e.g. 'C00019'); null if no KEGG xref. |
| flag_value | bool | Boolean flag — `false` is *tested-absent* (real biology, parent §10). |
| n_positive | int \| None (optional) | Number of replicates flagged positive. |
| n_replicates | int \| None (optional) | Number of replicates. |
| metric_type | string | Parent assay's metric tag (e.g. 'presence_flag_intracellular'). |
| condition_label | string \| None (optional) | Short condition descriptor (e.g. compartment + experiment). |
| assay_id | string | Parent MetaboliteAssay id. |
| organism_name | string | Source organism. |
| compartment | string | 'whole_cell' or 'extracellular'. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| assay_name | string \| None (optional) | Human-readable assay name. Verbose only. |
| field_description | string \| None (optional) | Canonical provenance description. Verbose only. |

## Few-shot examples

### Example 1: Canonical drill-down — msystems intracellular presence-flags

```example-call
metabolites_by_flags_assay(assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"])
```

```example-response
total_matching: 93
by_value: [{flag_value: false, count: 58}, {flag_value: true, count: 35}]
by_assay: [{assay_id: "metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular", count: 93}]
by_compartment: [{whole_cell: 93}]
by_organism: [{Prochlorococcus MIT9301: 93}]
excluded_assays: []
warnings: []
not_found: {assay_ids: [], metabolite_ids: [], experiment_ids: [], publication_doi: []}
results: [S-adenosyl-L-methionine flag=true, tyrosine flag=true, NADH flag=true, AMP flag=true, S-Adenosyl-L-homocysteine flag=true]  # default limit=5
```

### Example 2: Presence-only — flag_value=True

```example-call
metabolites_by_flags_assay(assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"], flag_value=True)
```

### Example 3: Tested-absent slice — flag_value=False

```example-call
metabolites_by_flags_assay(assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"], flag_value=False)
```

### Example 4: Summary — flag-distribution headline without rows

```example-call
metabolites_by_flags_assay(assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"], summary=True)
```

### Example 5: Cross-assay — both boolean assays at once (intracellular + extracellular)

```example-call
metabolites_by_flags_assay(assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular", "metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_extracellular"])
```

### Example 6: Metabolite-anchored — does PEP show up at all on the boolean assays?

```example-call
metabolites_by_flags_assay(assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular", "metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_extracellular"], metabolite_ids=["kegg.compound:C00074"])
```

## Chaining patterns

```
list_metabolite_assays(value_kind='boolean') → metabolites_by_flags_assay(assay_ids=[...])  # discovery → drill-down
metabolites_by_flags_assay → assays_by_metabolite(metabolite_ids=[...])  # quantifies-arm complement (cross-organism reverse view)
metabolites_by_flags_assay → genes_by_metabolite(metabolite_ids=[...], organism=...)  # gene catalysts/transporters of these metabolites
metabolites_by_flags_assay → metabolites_by_gene(locus_tags=[...], organism=...)  # gene-anchored chemistry context
```

## Common mistakes

```mistake
Filter out value=0 / flag_value=false rows assuming they are noise.
```

```correction
These rows are tested-absent — the metabolite was assayed and not found.
They are biology. Keep them unless explicitly investigating presence-only.

```

```mistake
A metabolite missing from results means it was not detected.
```

```correction
Missing means unmeasured (out of scope for this assay). For 'tested and
not found,' look for a value=0 / flag_value=false / detection_status='not_detected'
row.

```

```mistake
Expect by_detection_status in the envelope.
```

```correction
by_detection_status exists only on the numeric arm (its source field
lives on `Assay_quantifies_metabolite` edges). On boolean,
`flag_value` IS the qualitative-detection signal; `by_value` is its
envelope rollup (true / false counts).

```

```mistake
Expect not_found to be a flat list[str].
```

```correction
Drill-downs use a structured NotFound (4 keys: assay_ids, metabolite_ids,
experiment_ids, publication_doi) per parent spec §13.6 — multi-batch input
→ structured. Inspect each bucket separately to see which input was bad.
Mirrors `MetNotFound` on `list_metabolites` and `GbmNotFound` on
`genes_by_metabolite`.

```

```mistake
flag_value=False returns 0 rows like genes_by_boolean_metric does today.
```

```correction
`genes_by_boolean_metric` returns 0 rows for `flag=False` because the
DM layer stores positive-only edges (`dm_false_count=0` on every current
DM). `Assay_flags_metabolite` stores BOTH true and false flags — 68.8%
of edges in the live KG are `flag_value="false"` (128 of 186 across the
2 boolean assays). flag_value=False returns real rows here. Distinct
KG-storage convention.

```

```mistake
excluded_assays / warnings will surface gating diagnostics.
```

```correction
Always `[]` here (no gates) — kept for cross-tool envelope-shape
consistency with `metabolites_by_quantifies_assay`. Boolean assays
have no `rankable` gate to probe. Mirrors `genes_by_boolean_metric`
vs `genes_by_numeric_metric`.

```

```mistake
growth_phase populated on every row.
```

```correction
growth_phase is null on every row today — the schema field exists on
Experiment, but `time_point_growth_phases[]` is empty for every
metabolomics experiment in the current KG (KG-MET-017 backfill pending).
Forward-compat surface; values populate without explorer-side code change
when the KG ask lands.

```

## Package import equivalent

```python
from multiomics_explorer import metabolites_by_flags_assay

result = metabolites_by_flags_assay(assay_ids=...)
# returns dict with keys: total_matching, by_value, by_assay, by_compartment, by_organism, by_metric, excluded_assays, warnings, not_found, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
