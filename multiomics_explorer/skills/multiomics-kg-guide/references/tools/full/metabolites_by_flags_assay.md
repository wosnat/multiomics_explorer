# metabolites_by_flags_assay

## What it does

Boolean MetaboliteAssay edges — one row per metabolite × flag edge; cross-organism. flag_value=False rows are tested-absent (both states stored).

Use for presence / absence calls; pre-flight `list_metabolite_assays`; values `metabolites_by_quantifies_assay`, both arms `assays_by_metabolite`.
Filters: assay_ids, organism, metabolite_ids, flag_value, stereo_assignment, plus publication / experiment filters.
Returns: by_value, by_stereo_assignment, by_assay, by_metric, not_found, excluded_assays (always empty); one row = one flag.
docs://tools/metabolites_by_flags_assay; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| assay_ids | list[string] | — | MetaboliteAssay IDs to drill into. Discover via `list_metabolite_assays(value_kind='boolean')`. E.g. ['metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular']. `not_found.assay_ids` lists IDs absent from the KG. |
| organism | string \| None | None | Organism: case-insensitive substring match on the organism name ('MED4'); a genus word matches every strain. See list_organisms. |
| metabolite_ids | list[string] \| None | None | Metabolite IDs in any form (KEGG, ChEBI, MNX, HMDB, InChIKey; bare or prefixed). Retired ids resolve (see resolved_aliases); removed compounds and chemical roles warn. docs://analysis/metabolites. |
| exclude_metabolite_ids | list[string] \| None | None | Drop these metabolites; any id form, bare or prefixed, retired ids resolve (see resolved_aliases); exclude wins on overlap. |
| experiment_ids | list[string] \| None | None | Filter to assays from these experiments. |
| publication_dois | list[string] \| None | None | Restrict to these publication DOIs. |
| compartment | string \| None | None | Keep rows in this compartment. Values: list_filter_values('compartment'). |
| treatment_type | list[string] \| None | None | Keep experiments with any of these treatment_type values. Values: list_filter_values('treatment_type'). |
| background_factors | list[string] \| None | None | Keep experiments with any of these background_factors. Values: list_filter_values('background_factors'). |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| flag_value | bool \| None | None | Filter by flag presence — `True` (presence flagged), `False` (absence flagged — *tested-absent*, real biology), `None` (both). `Assay_flags_metabolite` always stores both states (unlike the DM layer, where only 11 of 34 boolean DMs store `not_flagged`), so `flag_value=False` returns real rows (about 69% of boolean rows). |
| stereo_assignment | list[string] \| None | None | Stereo-form provenance (OR): 'as_reported' = the paper named the form; 'dominant_form_assumed' = it named none and the KG placed it on the dominant form (e.g. 'Alanine' on L-Alanine). ['as_reported'] drops assumed rows. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, by_value, by_stereo_assignment, by_assay, by_compartment, by_organism, by_metric, excluded_assays, warnings, resolved_aliases, not_found, returned, truncated, offset, results
```

- **total_matching** (int): Row count in the filtered slice.
- **by_value** (list[MfaByValue]): Counts per flag value (true / false). `false` rows are tested-absent (real biology, kept by default). Boolean arm has no `by_detection_status` — `flag_value` IS the qualitative-detection signal here.
- **by_stereo_assignment** (list[MfaByStereoAssignment]): Rows per stereo_assignment over the matched set. 'dominant_form_assumed' rows had no form named by the paper; filter stereo_assignment=['as_reported'] to drop them.
- **by_assay** (list[MfaByAssay]): Counts per assay_id.
- **by_compartment** (list[MfaByCompartment]): Counts per compartment.
- **by_organism** (list[MfaByOrganism]): Counts per organism (cross-organism by default).
- **by_metric** (list[MfaByMetric]): Per-assay filtered-slice rollup.
- **excluded_assays** (list[string]): Always `[]` here (no gates apply). Kept for envelope-shape consistency with the numeric drill-down.
- **warnings** (list[string]): No gate diagnostics here (no gates apply); metabolite-id notes (removed compound, chemical role), a count of dominant-form-assumed rows, and a sibling-tool notice when a requested assay_id exists as value_kind='numeric' (genuinely found, excluded from `not_found.assay_ids` — use `metabolites_by_quantifies_assay` instead). Otherwise `[]`.
- **resolved_aliases** (object): Metabolite inputs resolved to a different canonical ID (bare, xref, secondary or retired ids), `{input: [canonical]}`, across `metabolite_ids` and `exclude_metabolite_ids`. Inputs already canonical are not listed.
- **not_found** (MfaNotFound): Per-batch-input unknown IDs (4 buckets: assay_ids, metabolite_ids, experiment_ids, publication_doi — bucket key is singular `publication_doi` regardless of the `publication_dois` input filter name). assay_ids is a real existence check — an assay_id that exists as the other value_kind is NOT here (see `warnings`).
- **returned** (int): Length of `results`.
- **truncated** (bool): True when total_matching > offset + returned.
- **offset** (int): Pagination offset used.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| metabolite_id | string | Metabolite node id. |
| name | string | Canonical metabolite name. |
| kegg_compound_id | string \| None (optional) | KEGG compound id (e.g. 'C00019'); null if no KEGG xref. |
| flag_value | bool | Boolean flag — `false` is *tested-absent* (real biology, kept by default). |
| n_positive | int \| None (optional) | Number of replicates flagged positive. |
| stereo_assignment | string \| None (optional) | 'as_reported' (the paper named this stereo form) or 'dominant_form_assumed' (it named none; the KG placed the measurement on the dominant form, e.g. 'Alanine' on L-Alanine). |
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
{
  "results": [
    {
      "metabolite_id": "kegg.compound:C00003",
      "name": "NAD+",
      "kegg_compound_id": "C00003",
      "flag_value": true,
      "n_positive": 1,
      "stereo_assignment": "as_reported",
      "n_replicates": 1,
      "metric_type": "presence_flag_intracellular",
      "condition_label": "",
      "assay_id": "metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular",
      "organism_name": "Prochlorococcus MIT9301",
      "compartment": "whole_cell"
    },
    {
      "metabolite_id": "kegg.compound:C00019",
      "name": "S-Adenosyl-L-methionine",
      "kegg_compound_id": "C00019",
      "flag_value": true,
      "n_positive": 1,
      "stereo_assignment": "as_reported",
      "n_replicates": 1,
      "metric_type": "presence_flag_intracellular",
      "condition_label": "",
      "assay_id": "metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular",
      "organism_name": "Prochlorococcus MIT9301",
      "compartment": "whole_cell"
    },
    {
      "metabolite_id": "kegg.compound:C00020",
      "name": "AMP",
      "kegg_compound_id": "C00020",
      "flag_value": true,
      "n_positive": 1,
      "stereo_assignment": "as_reported",
      "n_replicates": 1,
      "metric_type": "presence_flag_intracellular",
      "condition_label": "",
      "assay_id": "metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular",
      "organism_name": "Prochlorococcus MIT9301",
      "compartment": "whole_cell"
    },
    ...
  ],
  "total_matching": 93,
  "by_value": [{"flag_value": false, "count": 58}, {"flag_value": true, "count": 35}],
  "by_stereo_assignment": [
    {"stereo_assignment": "as_reported", "count": 64},
    {"stereo_assignment": "dominant_form_assumed", "count": 29}
  ],
  "by_assay": [
    {
      "assay_id": "metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular",
      "count": 93
    }
  ],
  "by_compartment": [{"compartment": "whole_cell", "count": 93}],
  "by_organism": [{"organism_name": "Prochlorococcus MIT9301", "count": 93}],
  "by_metric": [
    {
      "assay_id": "metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular",
      "count": 93
    }
  ],
  "excluded_assays": [],
  "warnings": [
    "29 of 93 rows assume the dominant stereo form — the paper named no form (e.g. 'Alanine' placed on L-Alanine); filter ..."
  ],
  "resolved_aliases": {},
  "not_found": {"assay_ids": [], "metabolite_ids": [], "experiment_ids": [], "publication_doi": []},
  "returned": 5,
  "truncated": true,
  "offset": 0
}
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

### Example 7: Paper-stated stereo forms only — drop rows whose form the KG assumed

```example-call
metabolites_by_flags_assay(assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"], stereo_assignment=["as_reported"], summary=True)
```

```example-response
{
  "results": [],
  "total_matching": 64,
  "by_value": [{"flag_value": false, "count": 46}, {"flag_value": true, "count": 18}],
  "by_stereo_assignment": [{"stereo_assignment": "as_reported", "count": 64}],
  "by_assay": [
    {
      "assay_id": "metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular",
      "count": 64
    }
  ],
  "by_compartment": [{"compartment": "whole_cell", "count": 64}],
  "by_organism": [{"organism_name": "Prochlorococcus MIT9301", "count": 64}],
  "by_metric": [
    {
      "assay_id": "metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular",
      "count": 64
    }
  ],
  "excluded_assays": [],
  "warnings": [],
  "resolved_aliases": {},
  "not_found": {"assay_ids": [], "metabolite_ids": [], "experiment_ids": [], "publication_doi": []},
  "returned": 0,
  "truncated": true,
  "offset": 0
}
```

## Chaining patterns

```
list_metabolite_assays(value_kind='boolean') → metabolites_by_flags_assay(assay_ids=[...])  # discovery → drill-down
metabolites_by_flags_assay → assays_by_metabolite(metabolite_ids=[...])  # quantifies-arm complement (cross-organism reverse view)
metabolites_by_flags_assay → genes_by_metabolite(metabolite_ids=[...], organism=...)  # gene catalysts/transporters of these metabolites
metabolites_by_flags_assay → metabolites_by_gene(locus_tags=[...], organism=...)  # gene-anchored chemistry context
```

## Common mistakes

- Boolean arm only (`Assay_flags_metabolite`). Siblings: `metabolites_by_quantifies_assay` is the numeric-arm twin (values, detection_status, rankable buckets); `assays_by_metabolite` is the metabolite-anchored reverse lookup over both arms.

```mistake
metabolites_by_flags_assay(assay_ids=[...])  # then citing an L-amino-acid row as 'the paper detected L-alanine'
```

```correction
`stereo_assignment` on every row says who chose the stereo form:
`as_reported` = the paper named it (or the compound has no stereo
variant); `dominant_form_assumed` = the paper gave no form and the KG
placed the row on one form of the stereo family (usually the one with
the most catalysing genes — 'Alanine' lands on L-alanine
`kegg.compound:C00041`). The envelope's `by_stereo_assignment` counts
both over the matched set and a `warnings` entry fires when any row is
assumed. Pass `stereo_assignment=['as_reported']` when the stereo form
matters to the claim, or quote assumed rows as "L-form assumed".

```

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
experiment_ids, publication_doi) — multi-batch input → structured.
Inspect each bucket separately to see which input was bad. Mirrors
`MetNotFound` on `list_metabolites` and `GbmNotFound` on
`genes_by_metabolite`.

```

```mistake
flag_value=False returns 0 rows like genes_by_boolean_metric does.
```

```correction
`Assay_flags_metabolite` ALWAYS stores both states (KG literals
'detected' / 'not_detected', bool on the surface) — about 69% of
boolean rows are `flag_value=false`, and flag_value=False returns real
rows. On the DM side only 11 of 34 boolean DMs store `not_flagged`
edges (the rest are positive-only), so `genes_by_boolean_metric(flag_value=False)`
is DM-dependent — read its `by_metric[*].dm_false_count` first.

```

```mistake
excluded_assays / warnings will surface gating diagnostics.
```

```correction
`excluded_assays` is always `[]` here (no gates) — kept for cross-tool
envelope-shape consistency with `metabolites_by_quantifies_assay`.
Boolean assays have no `rankable` gate to probe. `warnings` carries only
metabolite-ID notes (a removed compound or a chemical-role id in
`metabolite_ids`) and the assumed-stereo-form count (see
`stereo_assignment`). Mirrors `genes_by_boolean_metric`
vs `genes_by_numeric_metric`.

```

```mistake
growth_phase populated on every row.
```

```correction
growth_phase is currently null on every row — the schema field exists
on Experiment, but `time_point_growth_phases[]` is empty for every
metabolomics experiment in the current KG (KG-side backfill pending).
Forward-compat surface; values populate without explorer-side code
change when the upstream backfill lands.

```

```mistake
metabolites_by_flags_assay(metabolite_ids=['C00064'])  # then treating `C00064` in `not_found` as 'no such metabolite'
```

```correction
Metabolite IDs on `metabolite_ids` / `exclude_metabolite_ids` are normalised and
looked up in every identifier the metabolite carries before the query runs:
`C00064` / `kegg.compound:c00064` → `kegg.compound:C00064`, `CHEBI:17234` /
`17234` → `chebi:17234`; `HMDB0000122`, `MNXM732398` and bare InChIKeys resolve
the same way. Retired ids of merged or re-keyed nodes resolve to the surviving
node (`chebi:14654` → nitrate `kegg.compound:C00244`). Every input that isn't
already canonical is listed in envelope `resolved_aliases`
(`{input: [canonical, ...]}`). A removed compound whose measurements moved to
another compound, and a chemical-role id (`chebi:10004`, 'vitamin (role)'),
stay verbatim in `not_found` with a `warnings` entry naming the replacement or
the role. Other unresolved inputs stay verbatim in `not_found` in the form you
passed.

```

- See `docs://analysis/metabolites` for the 3 source pipelines decision tree and `docs://guide/conventions` for tested-absent semantics (about 69% of boolean rows are flag_value=False, kept by default; on the DM side only 11 of 34 boolean DMs store `not_flagged` edges).

- `organism` here matches by case-insensitive CONTAINS, not the word-based match the gene tools use; cross-organism is the default.

## Package import equivalent

```python
from multiomics_explorer import metabolites_by_flags_assay

result = metabolites_by_flags_assay(assay_ids=...)
# returns dict with keys: total_matching, by_value, by_stereo_assignment, by_assay, by_compartment, by_organism, by_metric, excluded_assays, warnings, resolved_aliases, not_found, returned, truncated, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
