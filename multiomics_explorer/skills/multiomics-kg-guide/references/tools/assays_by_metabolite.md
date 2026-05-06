# assays_by_metabolite

## What it does

Batch reverse-lookup: metabolite IDs → all measurement evidence
across both arms (quantifies + flags). Cross-organism by default.

Polymorphic rows: numeric-arm rows carry `value`, `value_sd`,
`detection_status`, `timepoint*`, `metric_bucket`,
`metric_percentile`, `rank_by_metric` (rankable subset). Boolean-arm
rows carry `flag_value`, `n_positive`. Cross-arm fields are explicit
`None` (union-shape padding, parallels Phase 3 decision on
`genes_by_metabolite`).

A row with `value=0` / `flag_value=false` /
`detection_status='not_detected'` is *tested-absent* (assayed and
not found, kept in results). A missing row is *unmeasured* (not in
this assay's scope). Don't conflate.

Three states for a metabolite (parent §10):
  1. `not_found` — ID not in the KG. **Unmeasured.**
  2. `not_matched` — ID in the KG, no assay edge after filters.
     **Unmeasured for this scope.**
  3. Row in `results` with `value=0` / `flag_value=false` /
     `detection_status='not_detected'` — *tested-absent* (assayed
     and not found). Real biology; counted in `total_matching`.

Use `summary=True` for batch routing on 50+ metabolite_ids.

Originates from:
- `list_metabolites(metabolite_ids=[...])` — chemistry-layer discovery
- `metabolites_by_gene(locus_tags=[...])` — gene-anchored chemistry

Drill back to numeric details:
`metabolites_by_quantifies_assay(assay_ids=[...], metabolite_ids=[...])`.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| metabolite_ids | list[string] | — | Metabolite IDs to look up (full prefixed, case-sensitive). E.g. ['kegg.compound:C00074']. `not_found` lists IDs absent from the KG; `not_matched` lists IDs in KG but with no assay edge after filters (unmeasured for this scope, parent §10). Required, non-empty. |
| organism | string \| None | None | Optional organism filter (case-insensitive CONTAINS). Default `None` = cross-organism (D2 closure: metabolite IDs are organism-agnostic — one Metabolite node shared across organisms). |
| evidence_kind | string ('quantifies', 'flags') \| None | None | Filter by edge type. `'quantifies'` = numeric arm only (rows carry value, detection_status, timepoint*). `'flags'` = boolean arm only (rows carry flag_value, n_positive). Default `None` = both arms merged (polymorphic rows; cross-arm fields explicit `None`). |
| exclude_metabolite_ids | list[string] \| None | None | Exclude metabolites with these IDs (set-difference). |
| metric_types | list[string] \| None | None | Filter by metric_type tag(s) on the parent assay. E.g. ['cellular_concentration', 'extracellular_concentration', 'presence_flag_intracellular', 'presence_flag_extracellular']. |
| compartment | string \| None | None | Sample compartment ('whole_cell' or 'extracellular'). Exact match on the parent assay. |
| summary | bool | False | Return summary fields only (results=[]). |
| verbose | bool | False | Include heavy-text fields per row: assay_field_description, replicate_values, experimental_context. |
| limit | int | 5 | Max rows. Paginate with `offset`. |
| offset | int | 0 | Pagination offset. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, by_evidence_kind, by_organism, by_compartment, by_assay, by_detection_status, by_flag_value, metabolites_with_evidence, metabolites_without_evidence, metabolites_matched, not_found, not_matched, returned, truncated, offset, results
```

- **total_matching** (int): Row count merged across arms (one row per metabolite × assay-edge). Use `metabolites_matched` for distinct-metabolite count.
- **by_evidence_kind** (list[AbmByEvidenceKind]): Counts per arm (quantifies / flags).
- **by_organism** (list[AbmByOrganism]): Counts per organism.
- **by_compartment** (list[AbmByCompartment]): Counts per compartment.
- **by_assay** (list[AbmByAssay]): Counts per assay_id.
- **by_detection_status** (list[AbmByDetectionStatus]): Numeric-row subset rollup; empty when `evidence_kind='flags'`.
- **by_flag_value** (list[AbmByFlagValue]): Boolean-row subset rollup; empty when `evidence_kind='quantifies'`.
- **metabolites_with_evidence** (list[string]): Input `metabolite_ids` with at least one row in the filtered slice (parallel to `gene_derived_metrics`'s `genes_with_metrics`).
- **metabolites_without_evidence** (list[string]): Input `metabolite_ids` with no row in the filtered slice (includes both `not_found` and `not_matched` IDs).
- **metabolites_matched** (int): Distinct-metabolite count — use this for unique tallies (NOT `total_matching`, which is row-count).
- **not_found** (list[string]): Flat `list[str]` — single-batch reverse-lookup (parent §13.6). Input metabolite IDs absent from the KG.
- **not_matched** (list[string]): Flat `list[str]` — IDs in KG with no edge after filters (unmeasured for this scope). Distinct from `not_found`.
- **returned** (int): Length of `results`.
- **truncated** (bool): True when total_matching > offset + returned.
- **offset** (int): Pagination offset used.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| metabolite_id | string | Metabolite node id (e.g. 'kegg.compound:C00074'). |
| metabolite_name | string | Canonical metabolite name (e.g. 'Phosphoenolpyruvate'). |
| assay_id | string | Parent MetaboliteAssay id. |
| assay_name | string | Human-readable assay name. |
| evidence_kind | string ('quantifies', 'flags') | Discriminator: 'quantifies' = numeric arm, 'flags' = boolean arm. |
| n_replicates | int \| None (optional) | Number of replicates. |
| metric_type | string | Parent assay's metric tag. |
| condition_label | string \| None (optional) | Short condition descriptor. |
| organism_name | string | Source organism. |
| compartment | string | 'whole_cell' or 'extracellular'. |
| experiment_id | string \| None (optional) | Parent experiment id. |
| publication_doi | string \| None (optional) | Parent publication DOI. |
| value | float \| None (optional) | Raw concentration / intensity. Numeric arm only. |
| value_sd | float \| None (optional) | Standard deviation across replicates. Numeric arm only. |
| metric_bucket | string \| None (optional) | Bucket label. Numeric, rankable subset only. |
| metric_percentile | float \| None (optional) | Percentile (0-100). Numeric, rankable subset only. |
| rank_by_metric | int \| None (optional) | Rank by value (1=highest). Numeric, rankable subset only. |
| detection_status | string \| None (optional) | 'detected'/'sporadic'/'not_detected'. Numeric arm only. |
| timepoint | string \| None (optional) | Timepoint label. Numeric arm only. |
| timepoint_hours | float \| None (optional) | Timepoint in hours. Numeric arm only. |
| timepoint_order | int \| None (optional) | Timepoint order index. Numeric arm only. |
| growth_phase | string \| None (optional) | Growth phase. Numeric arm only — null today (KG-MET-017 backfill pending). |
| flag_value | bool \| None (optional) | Boolean flag. Boolean arm only. `false` is tested-absent (parent §10). |
| n_positive | int \| None (optional) | Number of replicates flagged positive. Boolean arm only. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| assay_field_description | string \| None (optional) | Canonical provenance description. Verbose only. |
| replicate_values | list[float] \| None (optional) | Per-replicate values. Verbose only. |
| experimental_context | string \| None (optional) | Long-form context. Verbose only. |

## Few-shot examples

### Example 1: Canonical reverse-lookup — PEP across both arms

```example-call
assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"])
```

```example-response
total_matching: 20  # 18 quantifies + 2 flags
by_evidence_kind: [{quantifies: 18}, {flags: 2}]
by_detection_status: [{not_detected: 12}, {detected: 3}, {sporadic: 3}]  # numeric subset
by_flag_value: [{false: 2}]  # boolean subset — 70% of all PEP measurements are tested-absent
by_organism: [4 organisms — MED4, MIT9301, MIT9303, NATL2A]
by_compartment: [{whole_cell: 12}, {extracellular: 8}]
by_assay: [14 assays — every numeric and boolean assay on the metabolomics layer covers PEP]
metabolites_with_evidence: ["kegg.compound:C00074"]
metabolites_without_evidence: []
metabolites_matched: 1
not_found: []
not_matched: []
results: [polymorphic — numeric rows carry value/detection_status/timepoint*; boolean rows carry flag_value/n_positive]  # default limit=5
```

### Example 2: Numeric arm only — quantifies edges

```example-call
assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"], evidence_kind="quantifies")
```

### Example 3: Boolean arm only — flags edges

```example-call
assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"], evidence_kind="flags")
```

### Example 4: Single-organism scope — MIT9313 only

```example-call
assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"], organism="MIT9313")
```

### Example 5: Batch routing — summary with mixed found / not-found IDs

```example-call
assays_by_metabolite(metabolite_ids=["kegg.compound:C00074", "kegg.compound:C99999", "kegg.compound:C00031"], summary=True)
```

### Example 6: Compartment scope — extracellular only

```example-call
assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"], compartment="extracellular")
```

## Chaining patterns

```
list_metabolites(metabolite_ids=[...]) → assays_by_metabolite(metabolite_ids=[...])  # chemistry-layer discovery → measurement evidence
metabolites_by_gene(locus_tags=[...]) → assays_by_metabolite(metabolite_ids=[...])  # gene-anchored chemistry → measurement evidence
assays_by_metabolite → metabolites_by_quantifies_assay(assay_ids=[...], metabolite_ids=[...])  # drill back to numeric details (rankable filters, edge-level slicing)
assays_by_metabolite → metabolites_by_flags_assay(assay_ids=[...], metabolite_ids=[...])  # drill back to boolean details
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
Use total_matching for unique-metabolite count.
```

```correction
`total_matching` is row count (one row per metabolite × assay-edge,
merged across both arms). Use `metabolites_matched` for distinct
metabolite count. PEP returns total_matching=20 but
metabolites_matched=1 — the same compound surfaces 20 times across
18 numeric edges + 2 boolean edges.

```

```mistake
Treat polymorphic rows as kind-uniform.
```

```correction
Numeric rows carry value / value_sd / detection_status / timepoint /
timepoint_hours / timepoint_order / metric_bucket / metric_percentile /
rank_by_metric. Boolean rows carry flag_value / n_positive. Cross-arm
fields are explicit `None` (union-shape padding) — branch on
`evidence_kind` ('quantifies' / 'flags') per row before reading
arm-specific columns. Mirrors `gene_derived_metrics`'s polymorphic
`value` column.

```

```mistake
assays_by_metabolite(metabolite_ids=[...], evidence_kind='quantifies')  # and expect by_flag_value populated
```

```correction
When `evidence_kind` filters out one arm, that arm's envelope rollup is
empty (no rows contribute). `evidence_kind='quantifies'` empties
`by_flag_value`; `evidence_kind='flags'` empties `by_detection_status`.
Cross-tool envelope shape is preserved (always present), but the
filtered-out arm's bucket lists are `[]`.

```

```mistake
Expect not_found to be a structured Pydantic model.
```

```correction
Reverse-lookup uses a flat `list[str]` for `not_found` because only
`metabolite_ids` is a batch input — single batch → flat per parent §13.6
(deviating from the structured `MqaNotFound` / `MfaNotFound` on the
drill-downs, where 4 inputs are batch). Both `not_found` and
`not_matched` are flat lists here.

```

```mistake
Conflate not_found with not_matched.
```

```correction
`not_found` = ID not in the KG (Metabolite node doesn't exist).
`not_matched` = ID in the KG but no MetaboliteAssay edge after filters
(Metabolite exists but is unmeasured for this scope). Both are
*unmeasured* per parent §10, but only `not_matched` IDs are present
in the chemistry layer.

```

## Package import equivalent

```python
from multiomics_explorer import assays_by_metabolite

result = assays_by_metabolite(metabolite_ids=...)
# returns dict with keys: total_matching, by_evidence_kind, by_organism, by_compartment, by_assay, by_detection_status, by_flag_value, metabolites_with_evidence, metabolites_without_evidence, metabolites_matched, not_found, not_matched, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
