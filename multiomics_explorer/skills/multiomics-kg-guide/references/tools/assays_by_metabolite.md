# assays_by_metabolite

## What it does

Metabolite IDs to every measurement edge, numeric and boolean arms merged into one polymorphic row set; cross-organism.

Use for the metabolite-anchored reverse view; drill back to one arm with `metabolites_by_quantifies_assay` / `metabolites_by_flags_assay`.
Filters: metabolite_ids (+exclude), organism, evidence_kind, metric_types, compartment.
Returns: by_evidence_kind, by_detection_status, by_flag_value, by_assay, metabolites_matched (distinct; total_matching counts rows), not_found, not_matched; one row = one edge.
docs://tools/assays_by_metabolite; summary=True first for 50+ IDs.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| metabolite_ids | list[string] | — | Metabolite IDs; bare or xref forms coerced (see resolved_aliases, docs://analysis/metabolites). |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| evidence_kind | string ('quantifies', 'flags') \| None | None | Filter by edge type. `'quantifies'` = numeric arm only (rows carry value, detection_status, timepoint*). `'flags'` = boolean arm only (rows carry flag_value, n_positive). Default `None` = both arms merged (polymorphic rows; cross-arm fields explicit `None`). |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; bare/xref forms coerced (see resolved_aliases); exclude wins on overlap. |
| metric_types | list[string] \| None | None | Filter by metric_type tag(s) on the parent assay. E.g. ['cellular_concentration', 'extracellular_concentration', 'presence_flag_intracellular', 'presence_flag_extracellular']. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Example

### Canonical reverse-lookup — PEP across both arms

```python
assays_by_metabolite(metabolite_ids=["kegg.compound:C00074"])
```

## Response sketch

```expected-keys
total_matching, by_evidence_kind, by_organism, by_compartment, by_assay, by_detection_status, by_flag_value, metabolites_with_evidence, metabolites_without_evidence, metabolites_matched, not_found, not_matched, resolved_aliases, warnings, returned, truncated, offset, results
```

Result row: `metabolite_id, metabolite_name, assay_id, assay_name, evidence_kind, n_replicates, metric_type, condition_label, organism_name, compartment, experiment_id, publication_doi, …`

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

## Chaining patterns

- list_metabolites(metabolite_ids=[...]) → assays_by_metabolite(metabolite_ids=[...])  # chemistry-layer discovery → measurement evidence
- metabolites_by_gene(locus_tags=[...]) → assays_by_metabolite(metabolite_ids=[...])  # gene-anchored chemistry → measurement evidence
- assays_by_metabolite → metabolites_by_quantifies_assay(assay_ids=[...], metabolite_ids=[...])  # drill back to numeric details (rankable filters, edge-level slicing)
- assays_by_metabolite → metabolites_by_flags_assay(assay_ids=[...], metabolite_ids=[...])  # drill back to boolean details

Full reference (all examples, full response format, verbose fields): `docs://tools/assays_by_metabolite/full`
