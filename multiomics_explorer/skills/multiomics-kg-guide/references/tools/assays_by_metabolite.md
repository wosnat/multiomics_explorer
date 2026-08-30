# assays_by_metabolite

## What it does

Batch reverse-lookup: metabolite IDs → all measurement evidence
across both arms (quantifies + flags). Cross-organism by default
(metabolite IDs are organism-agnostic). Polymorphic rows: numeric-
arm rows carry `value`, `value_sd`, `detection_status`,
`timepoint*`, `metric_bucket`, `metric_percentile`,
`rank_by_metric` (rankable subset). Boolean-arm rows carry
`flag_value`, `n_positive`. Cross-arm fields are explicit `None`
(union-shape padding). Three states for a metabolite: `not_found`
(ID not in KG), `not_matched` (ID in KG, no edge after filters),
and tested-absent rows surfaced in `results` (`value=0` /
`flag_value=false` / `detection_status='not_detected'` — real
biology, kept by default). Use `metabolites_matched` for distinct-
metabolite count (NOT `total_matching` — that's row count). Use
`summary=True` on batch routing for 50+ metabolite_ids. Bare / xref
metabolite IDs are coerced to canonical (`resolved_aliases`;
collisions expand + warn).

Routing: drill back via
`metabolites_by_quantifies_assay(assay_ids=[...], metabolite_ids=[...])`
for numeric details. Upstream from
`list_metabolites(metabolite_ids=[...])` (chemistry-layer discovery)
or `metabolites_by_gene(locus_tags=[...])` (gene-anchored
chemistry). See `docs://guide/conventions` for tested-absent
semantics and `docs://analysis/metabolites` for the metabolomics
decision tree.

`organism` matches by case-insensitive CONTAINS (not word-match).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| metabolite_ids | list[string] \| None | — | Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites). |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| evidence_kind | string ('quantifies', 'flags') \| None | None | Filter by edge type. `'quantifies'` = numeric arm only (rows carry value, detection_status, timepoint*). `'flags'` = boolean arm only (rows carry flag_value, n_positive). Default `None` = both arms merged (polymorphic rows; cross-arm fields explicit `None`). |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap. |
| metric_types | list[string] \| None | None | Filter by metric_type tag(s) on the parent assay. E.g. ['cellular_concentration', 'extracellular_concentration', 'presence_flag_intracellular', 'presence_flag_extracellular']. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields in docs://tools/{name}. |
| limit | int \| None | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, by_evidence_kind, by_organism, by_compartment, by_assay, by_detection_status, by_flag_value, metabolites_with_evidence, metabolites_without_evidence, metabolites_matched, not_found, not_matched, resolved_aliases, warnings, returned, truncated, offset, results
```

- **total_matching** (int): Row count merged across arms (one row per metabolite × assay-edge). Use `metabolites_matched` for distinct-metabolite count.
- **by_evidence_kind** (list[AbmByEvidenceKind]): Counts per arm (quantifies / flags).
- **by_organism** (list[AbmByOrganism]): Counts per organism.
- **by_compartment** (list[AbmByCompartment]): Counts per compartment.
- **by_assay** (list[AbmByAssay]): Counts per assay_id.
- **by_detection_status** (list[AbmByDetectionStatus]): Numeric-row subset rollup; empty when `evidence_kind='flags'`.
- **by_flag_value** (list[AbmByFlagValue]): Boolean-row subset rollup; empty when `evidence_kind='quantifies'`.
- **metabolites_with_evidence** (list[string]): Input `metabolite_ids` with at least one row in the filtered slice (parallel to `gene_derived_metrics`'s `genes_with_metrics`). Computed from the full filtered match set, not from the (paginated, possibly empty) `results` page — populated the same way whether or not `summary=True`.
- **metabolites_without_evidence** (list[string]): Input `metabolite_ids` with no row in the filtered slice (includes both `not_found` and `not_matched` IDs).
- **metabolites_matched** (int): Distinct-metabolite count — use this for unique tallies (NOT `total_matching`, which is row-count).
- **not_found** (list[string]): Flat `list[str]` — single-batch reverse-lookup. Input metabolite IDs absent from the KG.
- **not_matched** (list[string]): Flat `list[str]` — IDs in KG with no edge after filters (unmeasured for this scope). Distinct from `not_found`. Computed from the full filtered match set (see `metabolites_with_evidence`) — correct even with `summary=True` or a batch larger than `limit`.
- **resolved_aliases** (object): Bare / xref metabolite inputs coerced to canonical IDs, `{input: [canonical, ...]}` — only coerced entries, across both `metabolite_ids` and `exclude_metabolite_ids`. A list longer than 1 is a collision (expanded to all; see `warnings`).
- **warnings** (list[string]): Diagnostic strings, e.g. a bare metabolite ID that resolved to more than one metabolite (expanded to all — pass the canonical id to narrow).
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
| metric_bucket | string \| None (optional) | Bucket label. Numeric, rankable subset only; null on tested-absent (`detection_status='not_detected'`) rows even then — a stored bucket from raw-zero coincidence is not a ranking signal. |
| metric_percentile | float \| None (optional) | Percentile (0-100). Numeric, rankable subset only; null on tested-absent rows (see `metric_bucket`). |
| rank_by_metric | int \| None (optional) | Rank by value (1=highest). Numeric, rankable subset only; null on tested-absent rows (see `metric_bucket`). |
| detection_status | string \| None (optional) | 'detected'/'sporadic'/'not_detected'. Numeric arm only. |
| timepoint | string \| None (optional) | Timepoint label. Numeric arm only. |
| timepoint_hours | float \| None (optional) | Timepoint in hours. Numeric arm only. |
| timepoint_order | int \| None (optional) | Timepoint order index. Numeric arm only. |
| growth_phase | string \| None (optional) | Growth phase. Numeric arm only — currently unpopulated (KG-side backfill pending). |
| flag_value | bool \| None (optional) | Boolean flag. Boolean arm only. `false` is tested-absent (real biology, kept by default). |
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
{
  "results": [
    {
      "metabolite_id": "kegg.compound:C00074",
      "metabolite_name": "Phosphoenolpyruvate",
      "assay_id": "metabolite_assay:msystems.01261-22:metabolites_kegg_export_0801_extracellular:extracellular_concentration",
      "assay_name": "MIT0801 extracellular metabolite concentration (mol/cell)",
      "evidence_kind": "quantifies",
      "n_replicates": 1,
      "metric_type": "extracellular_concentration",
      "condition_label": "replete_light_10",
      "organism_name": "Prochlorococcus MIT0801",
      "compartment": "extracellular",
      "experiment_id": "10.1128/msystems.01261-22_kujawinski_metabolomics_0801_extracellular",
      "publication_doi": "10.1128/msystems.01261-22",
      "value": 0.0,
      "value_sd": 0.0,
      "metric_bucket": null,
      "metric_percentile": null,
      "rank_by_metric": null,
      "detection_status": "not_detected",
      "timepoint": null,
      "timepoint_hours": null,
      "timepoint_order": null,
      "growth_phase": null,
      "flag_value": null,
      "n_positive": null,
      "assay_field_description": null,
      "replicate_values": null,
      "experimental_context": null
    },
    {
      "metabolite_id": "kegg.compound:C00074",
      "metabolite_name": "Phosphoenolpyruvate",
      "assay_id": "metabolite_assay:msystems.01261-22:metabolites_kegg_export_0801_intracellular:cellular_concentration",
      "assay_name": "MIT0801 intracellular metabolite concentration (mol/cell)",
      "evidence_kind": "quantifies",
      "n_replicates": 1,
      "metric_type": "cellular_concentration",
      "condition_label": "replete_light_10",
      "organism_name": "Prochlorococcus MIT0801",
      "compartment": "whole_cell",
      "experiment_id": "10.1128/msystems.01261-22_kujawinski_metabolomics_0801_whole_cell",
      "publication_doi": "10.1128/msystems.01261-22",
      "value": 0.0,
      "value_sd": 0.0,
      "metric_bucket": null,
      "metric_percentile": null,
      "rank_by_metric": null,
      "detection_status": "not_detected",
      "timepoint": null,
      "timepoint_hours": null,
      "timepoint_order": null,
      "growth_phase": null,
      "flag_value": null,
      "n_positive": null,
      "assay_field_description": null,
      "replicate_values": null,
      "experimental_context": null
    },
    {
      "metabolite_id": "kegg.compound:C00074",
      "metabolite_name": "Phosphoenolpyruvate",
      "assay_id": "metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_extracellular:extracellular_concentration",
      "assay_name": "MIT9301 extracellular metabolite concentration (mol/cell)",
      "evidence_kind": "quantifies",
      "n_replicates": 1,
      "metric_type": "extracellular_concentration",
      "condition_label": "P_limited_light_50",
      "organism_name": "Prochlorococcus MIT9301",
      "compartment": "extracellular",
      "experiment_id": "10.1128/msystems.01261-22_kujawinski_metabolomics_9301_extracellular",
      "publication_doi": "10.1128/msystems.01261-22",
      "value": 0.0,
      "value_sd": 0.0,
      "metric_bucket": null,
      "metric_percentile": null,
      "rank_by_metric": null,
      "detection_status": "not_detected",
      "timepoint": null,
      "timepoint_hours": null,
      "timepoint_order": null,
      "growth_phase": null,
      "flag_value": null,
      "n_positive": null,
      "assay_field_description": null,
      "replicate_values": null,
      "experimental_context": null
    },
    ...
  ],
  "total_matching": 20,
  "by_evidence_kind": [{"evidence_kind": "quantifies", "count": 18}, {"evidence_kind": "flags", "count": 2}],
  "by_organism": [
    {"organism_name": "Prochlorococcus MIT9313", "count": 8},
    {"organism_name": "Prochlorococcus MIT9301", "count": 8},
    {"organism_name": "Prochlorococcus MIT0801", "count": 2},
    {"organism_name": "Prochlorococcus MIT9303", "count": 2}
  ],
  "by_compartment": [{"compartment": "whole_cell", "count": 14}, {"compartment": "extracellular", "count": 6}],
  "by_assay": [
    {
      "assay_id": "metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration",
      "count": 4
    },
    {
      "assay_id": "metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_extracellular:extracellular_concentration",
      "count": 3
    },
    {
      "assay_id": "metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration",
      "count": 3
    },
    {
      "assay_id": "metabolite_assay:msystems.01261-22:metabolites_kegg_export_9313_extracellular:extracellular_concentration",
      "count": 2
    },
    {
      "assay_id": "metabolite_assay:msystems.01261-22:metabolites_kegg_export_9313_intracellular:cellular_concentration",
      "count": 2
    },
    ...
  ],
  "by_detection_status": [
    {"detection_status": "not_detected", "count": 12},
    {"detection_status": "detected", "count": 3},
    {"detection_status": "sporadic", "count": 3}
  ],
  "by_flag_value": [{"flag_value": false, "count": 2}],
  "metabolites_with_evidence": ["kegg.compound:C00074"],
  "metabolites_without_evidence": [],
  "metabolites_matched": 1,
  "not_found": [],
  "not_matched": [],
  "resolved_aliases": {},
  "warnings": [],
  "returned": 5,
  "truncated": true,
  "offset": 0
}
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

- Metabolite-anchored reverse lookup over BOTH arms. Siblings: `metabolites_by_quantifies_assay` (assay-anchored, numeric arm, rankable filters) and `metabolites_by_flags_assay` (assay-anchored, boolean arm) — drill back to them with the `assay_id`s found here.

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
`metabolite_ids` is a batch input — single batch → flat (deviating
from the structured `MqaNotFound` / `MfaNotFound` on the drill-downs,
where 4 inputs are batch). Both `not_found` and `not_matched` are
flat lists here.

```

```mistake
Conflate not_found with not_matched.
```

```correction
`not_found` = ID not in the KG (Metabolite node doesn't exist).
`not_matched` = ID in the KG but no MetaboliteAssay edge after filters
(Metabolite exists but is unmeasured for this scope). Both are
*unmeasured*, but only `not_matched` IDs are present in the chemistry
layer. See `docs://guide/conventions`.

```

```mistake
assays_by_metabolite(metabolite_ids=[...], summary=True)  # then read not_matched / metabolites_without_evidence off the (empty) results page
```

```correction
`not_matched` / `metabolites_with_evidence` / `metabolites_without_evidence`
are computed from the full filtered match set, not from `results` —
correct whether or not `summary=True` and regardless of `limit`. A
matched metabolite is never reported as `not_matched` just because its
row didn't make the current page.

```

```mistake
assays_by_metabolite(metabolite_ids=['C00064'])  # then treating `C00064` in `not_found` as 'no such metabolite'
```

```correction
Bare / xref metabolite IDs on `metabolite_ids` / `exclude_metabolite_ids` are resolved via
the node's cross-references before the query runs: `C00064` →
`kegg.compound:C00064`, `CHEBI:17234` / `17234` → the `chebi_id` match,
`HMDB0000122` → `hmdb_id`, `MNXM1095050` → `mnxm_id`. Canonical forms
(`kegg.compound:` / `chebi:` / `mnx:`) pass through untouched. Coerced
inputs are listed in envelope `resolved_aliases` (`{input: [canonical, ...]}`).
CHEBI / HMDB / MNXM xrefs are not unique — an ambiguous input expands to
ALL matching metabolites and appends a `warnings` entry; pass the canonical
id to narrow. Unresolved inputs stay verbatim and surface in `not_found`
in the form you passed.

```

- See `docs://analysis/metabolites` for the 3 source pipelines decision tree and `docs://guide/conventions` for the not_found vs not_matched convention across batch tools.

## Package import equivalent

```python
from multiomics_explorer import assays_by_metabolite

result = assays_by_metabolite(metabolite_ids=...)
# returns dict with keys: total_matching, by_evidence_kind, by_organism, by_compartment, by_assay, by_detection_status, by_flag_value, metabolites_with_evidence, metabolites_without_evidence, metabolites_matched, not_found, not_matched, resolved_aliases, warnings, returned, truncated, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
