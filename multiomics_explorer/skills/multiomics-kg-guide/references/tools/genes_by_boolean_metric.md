# genes_by_boolean_metric

## What it does

Drill into boolean DerivedMetric edges — one row per (gene × DM ×
edge value). `value` is the KG two-state literal (`'flagged'` / `'not_flagged'`).
Cross-organism by design.

Selection is `derived_metric_ids` XOR `metric_types` (exactly one
required); wrong-kind IDs (numeric / categorical) surface silently
in `not_found_ids`. Pre-flight via
`list_derived_metrics(value_kind='boolean')` to pick valid boolean
DMs. See `docs://guide/conventions` for the full DM family gating
contract.

**Two storage conventions coexist:** 11 of 27 boolean DMs store
both `flagged` and `not_flagged` edges (tested-absent is real
biology — `flag=False` returns rows), the rest are positive-only
(`flag=False` → 0 rows). Read `by_metric[*].false_count` to tell
'not flagged' from 'not assessed'; `by_metric[*].dm_false_count`
is the full-DM precomputed twin (0 on positive-only DMs).
See `docs://guide/conventions`.

The `by_metric` envelope rollup pairs filtered-slice true/false
tallies with full-DM precomputed counts so callers can read "32 of
32 MED4 vesicle-proteome members" directly.
`excluded_derived_metrics` / `warnings` are always [] here (no
gates apply); kept for envelope-shape consistency.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| derived_metric_ids | list[string] \| None | None | Boolean DerivedMetric node IDs. Use when the same `metric_type` appears across organisms / publications and you need to pin one. Discover IDs via `list_derived_metrics(value_kind='boolean')`. Mutually exclusive with `metric_types`. Wrong-kind IDs (numeric / categorical) surface silently in `not_found_ids`. |
| metric_types | list[string] \| None | None | Boolean metric-type tags (e.g. ['vesicle_proteome_member', 'periodic_in_coculture_LD']). Unions every DM carrying that tag, then narrows by scoping filters. Same tag can span organisms / publications — pin one specific DM via `derived_metric_ids` instead. Mutually exclusive with `derived_metric_ids`. |
| organism | string \| None | None | Organism to scope the DM set to. Accepts short strain code ('MED4', 'NATL2A', 'MIT9313') or full name; word-based, case-insensitive match. Single-organism is **not** enforced — omit to drill across all organisms a metric_type spans. |
| locus_tags | list[string] \| None | None | Restrict drill-down to a specific gene set (e.g. DE hits from `differential_expression_by_gene`). Filter on `g.locus_tag IN $locus_tags` post-MATCH. Genes with no edge for the selected DM produce no row. |
| experiment_ids | list[string] \| None | None | Scope to DMs from one or more experiments. |
| publication_doi | list[string] \| None | None | Scope to DMs from one or more publications. |
| compartment | string \| None | None | Sample compartment ('whole_cell', 'vesicle', 'exoproteome', 'extracellular'). Exact match. |
| treatment_type | list[string] \| None | None | Treatment type(s) (e.g. ['diel']). ANY-overlap. Case-insensitive. |
| background_factors | list[string] \| None | None | Background factor(s) (e.g. ['axenic', 'light']). ANY-overlap. Case-insensitive. |
| growth_phases | list[string] \| None | None | Growth phase(s). ANY-overlap. Case-insensitive. |
| flag | bool \| None | None | Filter on `r.value`: True keeps `'flagged'` edges, False keeps `'not_flagged'` edges (tested-absent — real biology, stored on 11 of 27 boolean DMs; the rest are positive-only and return 0 rows for False). Check `by_metric[*].false_count` before reading an absent gene as 'not flagged' vs 'not assessed'. |
| summary | bool | False | Return summary fields only (counts, breakdowns, by_metric, diagnostics). Sugar for limit=0; results=[]. |
| verbose | bool | False | Include heavy text fields per row: gene_function_description, gene_summary, plus DM context (metric_type, field_description, unit, compartment, experiment_id, publication_doi, treatment_type, background_factors, treatment, light_condition, experimental_context). |
| limit | int | 5 | Max rows to return. Paginate with `offset`. Use `summary=True` for summary-only (sets limit=0). |
| offset | int | 0 | Pagination offset (starting row, 0-indexed). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_value, top_categories, by_metric, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, returned, offset, truncated, results
```

- **total_matching** (int): Rows post-filter (gene × DM pairs).
- **total_derived_metrics** (int): Distinct DMs contributing rows.
- **total_genes** (int): Distinct genes in results.
- **by_organism** (list[GenesByNumericMetricOrganismBreakdown]): Rows per organism.
- **by_compartment** (list[GenesByNumericMetricCompartmentBreakdown]): Rows per compartment.
- **by_publication** (list[GenesByNumericMetricPublicationBreakdown]): Rows per publication.
- **by_experiment** (list[GenesByNumericMetricExperimentBreakdown]): Rows per experiment.
- **by_value** (list[GenesByBooleanMetricValueBreakdown]): Frequency rollup of `r.value` across surviving rows. Values are 'flagged' / 'not_flagged'; not_flagged rows exist on 11 of 27 boolean DMs.
- **top_categories** (list[GenesByNumericMetricCategoryBreakdown]): Top 5 gene categories by count.
- **by_metric** (list[GenesByBooleanMetricBreakdown]): Per-DM rollup: filtered-slice true/false counts + full-DM precomputed tallies. Sorted by count desc.
- **genes_per_metric_max** (int): Largest per-DM gene count.
- **genes_per_metric_median** (float): Median per-DM gene count.
- **not_found_ids** (list[string]): `derived_metric_ids` inputs not present in KG (or scoped out / wrong value_kind).
- **not_matched_ids** (list[string]): `derived_metric_ids` in KG but produced 0 rows after edge-level filters.
- **not_found_metric_types** (list[string]): `metric_types` inputs that match no DM after scoping.
- **not_matched_metric_types** (list[string]): `metric_types` whose DMs produced 0 rows.
- **not_matched_organism** (string | None): `organism` arg that matched no surviving DM.
- **excluded_derived_metrics** (list[ExcludedDerivedMetric]): Always [] for boolean DMs (no rankable / has_p_value gates). Kept for cross-tool envelope-shape consistency.
- **warnings** (list[string]): Always [] for boolean DMs. Kept for cross-tool envelope-shape consistency.
- **returned** (int): Length of results list.
- **offset** (int): Pagination offset used.
- **truncated** (bool): True when total_matching > offset + returned.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0090'). |
| gene_name | string \| None (optional) | Gene symbol; null when KG has none. |
| product | string \| None (optional) | Gene product. |
| gene_category | string \| None (optional) | Coarse functional category. |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4'). |
| derived_metric_id | string | Unique parent-DM id. |
| name | string | DM human label. |
| value_kind | string | Always 'boolean' for this tool; kept for cross-tool row-shape consistency with `genes_by_numeric_metric`. |
| rankable | bool | DM-level rankable flag (always False for boolean DMs in the current KG). |
| has_p_value | bool | DM-level p-value flag (always False for boolean DMs in the current KG). |
| value | string | 'flagged' or 'not_flagged' (KG two-state literal — see KG-spec BioCypher constraint). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| metric_type | string \| None (optional) | Category tag. Verbose only. |
| field_description | string \| None (optional) | Detailed explanation of what this DM measures. Verbose only. |
| unit | string \| None (optional) | Measurement unit (typically null for boolean DMs). Verbose only. |
| compartment | string \| None (optional) | Sample compartment. Verbose only. |
| experiment_id | string \| None (optional) | Parent experiment id. Verbose only. |
| publication_doi | string \| None (optional) | Parent publication DOI. Verbose only. |
| treatment_type | list[string] \| None (optional) | Treatment type(s). Verbose only. |
| background_factors | list[string] \| None (optional) | Background factor(s). Verbose only. |
| treatment | string \| None (optional) | Treatment description in plain language. Verbose only. |
| light_condition | string \| None (optional) | Light regime. Verbose only. |
| experimental_context | string \| None (optional) | Longer experimental setup description. Verbose only. |
| gene_function_description | string \| None (optional) | Gene functional description (gene-level). Verbose only. |
| gene_summary | string \| None (optional) | Gene summary text (gene-level). Verbose only. |

## Few-shot examples

### Example 1: Vesicle proteome cross-organism — same metric_type spans two strains

```example-call
genes_by_boolean_metric(metric_types=['vesicle_proteome_member'])
```

```example-response
{
  "total_matching": 59,
  "total_derived_metrics": 2,
  "total_genes": 59,
  "by_organism": [
    {"organism_name": "Prochlorococcus MED4", "count": 32},
    {"organism_name": "Prochlorococcus MIT9313", "count": 27}
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 59}],
  "by_publication": [{"publication_doi": "10.1126/science.1243457", "count": 59}],
  "by_experiment": [
    {"experiment_id": "10.1126/science.1243457_vesicle_proteomics_med4", "count": 32},
    {"experiment_id": "10.1126/science.1243457_vesicle_proteomics_mit9313", "count": 27}
  ],
  "by_value": [{"value": "flagged", "count": 59}],
  "top_categories": [
    {"gene_category": "Unknown", "count": 12},
    {"gene_category": "Stress response and adaptation", "count": 9},
    {"gene_category": "Cell wall and membrane", "count": 9},
    {"gene_category": "Translation", "count": 6},
    {"gene_category": "Post-translational modification", "count": 4}
  ],
  "by_metric": [
    {
      "derived_metric_id": "derived_metric:science.1243457:s2_med4_vesicle_proteome:vesicle_proteome_member",
      "name": "MED4 protein detected in vesicle proteome (Biller 2014 Table S2)",
      "metric_type": "vesicle_proteome_member",
      "value_kind": "boolean",
      "count": 32,
      "true_count": 32,
      "false_count": 0,
      "dm_total_gene_count": 32,
      "dm_true_count": 32,
      "dm_false_count": 0
    },
    {
      "derived_metric_id": "derived_metric:science.1243457:s3_mit9313_vesicle_proteome:vesicle_proteome_member",
      "name": "MIT9313 protein detected in vesicle proteome (Biller 2014 Table S3)",
      "metric_type": "vesicle_proteome_member",
      "value_kind": "boolean",
      "count": 27,
      "true_count": 27,
      "false_count": 0,
      "dm_total_gene_count": 27,
      "dm_true_count": 27,
      "dm_false_count": 0
    }
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
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "results": [
    {
      "locus_tag": "PMM0090",
      "gene_name": "degQ",
      "product": "serine endoprotease, periplasmic",
      "gene_category": "Post-translational modification",
      "organism_name": "Prochlorococcus MED4",
      "derived_metric_id": "derived_metric:science.1243457:s2_med4_vesicle_proteome:vesicle_proteome_member",
      "name": "MED4 protein detected in vesicle proteome (Biller 2014 Table S2)",
      "value_kind": "boolean",
      "rankable": false,
      "has_p_value": false,
      "value": "flagged"
    },
    {
      "locus_tag": "PMM0097",
      "gene_name": "tolC",
      "product": "TolC-like outer membrane efflux protein, RND family",
      "gene_category": "Stress response and adaptation",
      "organism_name": "Prochlorococcus MED4",
      "derived_metric_id": "derived_metric:science.1243457:s2_med4_vesicle_proteome:vesicle_proteome_member",
      "name": "MED4 protein detected in vesicle proteome (Biller 2014 Table S2)",
      "value_kind": "boolean",
      "rankable": false,
      "has_p_value": false,
      "value": "flagged"
    },
    {
      "locus_tag": "PMM0107",
      "gene_name": "aroK",
      "product": "shikimate kinase",
      "gene_category": "Amino acid metabolism",
      "organism_name": "Prochlorococcus MED4",
      "derived_metric_id": "derived_metric:science.1243457:s2_med4_vesicle_proteome:vesicle_proteome_member",
      "name": "MED4 protein detected in vesicle proteome (Biller 2014 Table S2)",
      "value_kind": "boolean",
      "rankable": false,
      "has_p_value": false,
      "value": "flagged"
    },
    ...
  ]
}
```

### Example 2: Scoped to one strain — NATL2A periodic-LD flag set

```example-call
genes_by_boolean_metric(metric_types=['periodic_in_coculture_LD'], organism='NATL2A')
```

```example-response
{
  "total_matching": 1651,
  "total_derived_metrics": 1,
  "total_genes": 1651,
  "by_organism": [{"organism_name": "Prochlorococcus NATL2A", "count": 1651}],
  "by_compartment": [{"compartment": "whole_cell", "count": 1651}],
  "by_publication": [{"publication_doi": "10.1128/mSystems.00040-18", "count": 1651}],
  "by_experiment": [
    {
      "experiment_id": "10.1128/mSystems.00040-18_darkness_extended_darkness_natl2a_rnaseq_coculture",
      "count": 1651
    }
  ],
  "by_value": [{"value": "flagged", "count": 1651}],
  "top_categories": [
    {"gene_category": "Unknown", "count": 479},
    {"gene_category": "Stress response and adaptation", "count": 196},
    {"gene_category": "Coenzyme metabolism", "count": 152},
    {"gene_category": "Translation", "count": 119},
    {"gene_category": "Amino acid metabolism", "count": 93}
  ],
  "by_metric": [
    {
      "derived_metric_id": "derived_metric:mSystems.00040-18:s4a_natl2a_coculture:periodic_in_coculture_LD",
      "name": "Periodic in NATL2A coculture L:D (Table S4A)",
      "metric_type": "periodic_in_coculture_LD",
      "value_kind": "boolean",
      "count": 1651,
      "true_count": 1651,
      "false_count": 0,
      "dm_total_gene_count": 1651,
      "dm_true_count": 1651,
      "dm_false_count": 0
    }
  ],
  "genes_per_metric_max": 1651,
  "genes_per_metric_median": 1651.0,
  "not_found_ids": [],
  "not_matched_ids": [],
  "not_found_metric_types": [],
  "not_matched_metric_types": [],
  "not_matched_organism": null,
  "excluded_derived_metrics": [],
  "warnings": [],
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "results": [
    {
      "locus_tag": "PMN2A_0001",
      "gene_name": "dnaA",
      "product": "chromosomal replication initiator protein",
      "gene_category": "Replication and repair",
      "organism_name": "Prochlorococcus NATL2A",
      "derived_metric_id": "derived_metric:mSystems.00040-18:s4a_natl2a_coculture:periodic_in_coculture_LD",
      "name": "Periodic in NATL2A coculture L:D (Table S4A)",
      "value_kind": "boolean",
      "rankable": false,
      "has_p_value": false,
      "value": "flagged"
    },
    {
      "locus_tag": "PMN2A_0002",
      "gene_name": "gst",
      "product": "glutathione S-transferase",
      "gene_category": "Coenzyme metabolism",
      "organism_name": "Prochlorococcus NATL2A",
      "derived_metric_id": "derived_metric:mSystems.00040-18:s4a_natl2a_coculture:periodic_in_coculture_LD",
      "name": "Periodic in NATL2A coculture L:D (Table S4A)",
      "value_kind": "boolean",
      "rankable": false,
      "has_p_value": false,
      "value": "flagged"
    },
    {
      "locus_tag": "PMN2A_0003",
      "gene_name": "gor",
      "product": "glutathione reductase",
      "gene_category": "Coenzyme metabolism",
      "organism_name": "Prochlorococcus NATL2A",
      "derived_metric_id": "derived_metric:mSystems.00040-18:s4a_natl2a_coculture:periodic_in_coculture_LD",
      "name": "Periodic in NATL2A coculture L:D (Table S4A)",
      "value_kind": "boolean",
      "rankable": false,
      "has_p_value": false,
      "value": "flagged"
    },
    ...
  ]
}
```

### Example 3: Summary-only — full-DM context without per-row drill-down

```example-call
genes_by_boolean_metric(metric_types=['vesicle_proteome_member'], summary=True)
```

```example-response
{
  "total_matching": 59,
  "total_derived_metrics": 2,
  "total_genes": 59,
  "by_organism": [
    {"organism_name": "Prochlorococcus MED4", "count": 32},
    {"organism_name": "Prochlorococcus MIT9313", "count": 27}
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 59}],
  "by_publication": [{"publication_doi": "10.1126/science.1243457", "count": 59}],
  "by_experiment": [
    {"experiment_id": "10.1126/science.1243457_vesicle_proteomics_med4", "count": 32},
    {"experiment_id": "10.1126/science.1243457_vesicle_proteomics_mit9313", "count": 27}
  ],
  "by_value": [{"value": "flagged", "count": 59}],
  "top_categories": [
    {"gene_category": "Unknown", "count": 12},
    {"gene_category": "Stress response and adaptation", "count": 9},
    {"gene_category": "Cell wall and membrane", "count": 9},
    {"gene_category": "Translation", "count": 6},
    {"gene_category": "Post-translational modification", "count": 4}
  ],
  "by_metric": [
    {
      "derived_metric_id": "derived_metric:science.1243457:s2_med4_vesicle_proteome:vesicle_proteome_member",
      "name": "MED4 protein detected in vesicle proteome (Biller 2014 Table S2)",
      "metric_type": "vesicle_proteome_member",
      "value_kind": "boolean",
      "count": 32,
      "true_count": 32,
      "false_count": 0,
      "dm_total_gene_count": 32,
      "dm_true_count": 32,
      "dm_false_count": 0
    },
    {
      "derived_metric_id": "derived_metric:science.1243457:s3_mit9313_vesicle_proteome:vesicle_proteome_member",
      "name": "MIT9313 protein detected in vesicle proteome (Biller 2014 Table S3)",
      "metric_type": "vesicle_proteome_member",
      "value_kind": "boolean",
      "count": 27,
      "true_count": 27,
      "false_count": 0,
      "dm_total_gene_count": 27,
      "dm_true_count": 27,
      "dm_false_count": 0
    }
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
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "results": []
}
```

### Example 4: Tested-absent rows — flag=False on a DM that stores not_flagged edges

```example-call
genes_by_boolean_metric(metric_types=['rapid_recovery_low_co2_shock'], flag=False)
```

*This Biller low-CO2 DM stores `not_flagged` edges, so `flag=False` returns real tested-absent rows (`value: 'not_flagged'`) and `by_metric[0].dm_false_count > 0`. On a positive-only DM (e.g. `vesicle_proteome_member`) the same call returns 0 rows and `dm_false_count: 0` — absent there means not assessed, not negative.*

```example-response
{
  "total_matching": 38,
  "total_derived_metrics": 1,
  "total_genes": 38,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 38}],
  "by_compartment": [{"compartment": "whole_cell", "count": 38}],
  "by_publication": [{"publication_doi": "10.1038/ismej.2015.36", "count": 38}],
  "by_experiment": [{"experiment_id": "10.1038/ismej.2015.36_carbon_low_co2_0004_co2_med4_microarray", "count": 38}],
  "by_value": [{"value": "not_flagged", "count": 38}],
  "top_categories": [
    {"gene_category": "Stress response and adaptation", "count": 17},
    {"gene_category": "Unknown", "count": 6},
    {"gene_category": "Coenzyme metabolism", "count": 5},
    {"gene_category": "Photosynthesis", "count": 2},
    {"gene_category": "Transcription", "count": 2}
  ],
  "by_metric": [
    {
      "derived_metric_id": "derived_metric:ismej.2015.36:s2_concordance_low_co2:rapid_recovery_low_co2_shock",
      "name": "MED4 rapid recovery under -CO2 shock (Bagby 2015 Table S2)",
      "metric_type": "rapid_recovery_low_co2_shock",
      "value_kind": "boolean",
      "count": 38,
      "true_count": 0,
      "false_count": 38,
      "dm_total_gene_count": 51,
      "dm_true_count": 13,
      "dm_false_count": 38
    }
  ],
  "genes_per_metric_max": 38,
  "genes_per_metric_median": 38.0,
  "not_found_ids": [],
  "not_matched_ids": [],
  "not_found_metric_types": [],
  "not_matched_metric_types": [],
  "not_matched_organism": null,
  "excluded_derived_metrics": [],
  "warnings": [],
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "results": [
    {
      "locus_tag": "PMM0051",
      "gene_name": null,
      "product": "cobQ/CobB/MinD/ParA nucleotide binding domain protein",
      "gene_category": "Cell cycle and division",
      "organism_name": "Prochlorococcus MED4",
      "derived_metric_id": "derived_metric:ismej.2015.36:s2_concordance_low_co2:rapid_recovery_low_co2_shock",
      "name": "MED4 rapid recovery under -CO2 shock (Bagby 2015 Table S2)",
      "value_kind": "boolean",
      "rankable": false,
      "has_p_value": false,
      "value": "not_flagged"
    },
    {
      "locus_tag": "PMM0075",
      "gene_name": null,
      "product": "conserved hypothetical protein",
      "gene_category": "Transcription",
      "organism_name": "Prochlorococcus MED4",
      "derived_metric_id": "derived_metric:ismej.2015.36:s2_concordance_low_co2:rapid_recovery_low_co2_shock",
      "name": "MED4 rapid recovery under -CO2 shock (Bagby 2015 Table S2)",
      "value_kind": "boolean",
      "rankable": false,
      "has_p_value": false,
      "value": "not_flagged"
    },
    {
      "locus_tag": "PMM0087",
      "gene_name": null,
      "product": "conserved hypothetical protein",
      "gene_category": "Unknown",
      "organism_name": "Prochlorococcus MED4",
      "derived_metric_id": "derived_metric:ismej.2015.36:s2_concordance_low_co2:rapid_recovery_low_co2_shock",
      "name": "MED4 rapid recovery under -CO2 shock (Bagby 2015 Table S2)",
      "value_kind": "boolean",
      "rankable": false,
      "has_p_value": false,
      "value": "not_flagged"
    },
    ...
  ]
}
```

### Example 5: DE → top hits → boolean flag intersection

```
Step 1: differential_expression_by_gene(organism="MED4", significant_only=True, limit=20)
        → extract `locus_tag` from each result row (top-20 |log2FC|).

Step 2: genes_by_boolean_metric(
          metric_types=["vesicle_proteome_member"],
          locus_tags=[<those 20 locus_tags>])
        → which DE hits are also vesicle-proteome members?
          Per-row `value="flagged"` confirms the flag; envelope
          `total_matching` shows the intersection size.

Step 3 (drill-down): gene_overview(locus_tags=[<intersected genes>])
        → routing context for the genes that are both DE-significant
          AND vesicle-detected.
```

## Chaining patterns

```
list_derived_metrics(value_kind='boolean') → genes_by_boolean_metric(metric_types=[...]) → gene_overview / genes_by_function
differential_expression_by_gene → top hits → genes_by_boolean_metric(metric_types=[...], locus_tags=hits)
genes_by_boolean_metric (no organism filter) → split via envelope by_organism for cross-strain comparison
```

## Common mistakes

- Two storage conventions coexist. 11 of 27 boolean DMs (Biller 2022, Voigt 2014, Hennon 2015, Steglich 2010) store `r.value="not_flagged"` edges, so `flag=False` returns tested-absent rows there; the rest (Biller 2014 / 2018, Coe 2016) are positive-only and return 0 rows for `flag=False`. Read `by_metric[*].false_count` before reading an absent gene as "not flagged" rather than "not assessed"; `dm_false_count` is the full-DM precomputed twin (0 on positive-only DMs). Contrast `metabolites_by_flags_assay`, whose edges always store both states.

- Sparse `rankable` / `has_p_value` echoes. Both are always `False` on every row from boolean DMs in the current KG — kept for cross-tool row-shape consistency with `genes_by_numeric_metric`, not because this tool reads them as a meaningful signal. Don't gate downstream logic on them.

```mistake
genes_by_boolean_metric(derived_metric_ids=['derived_metric:...:damping_ratio'])
```

```correction
genes_by_boolean_metric(metric_types=['vesicle_proteome_member'])
```

- See `docs://analysis/derived_metrics` for the DM family overview. Note: `flag=False` returns rows only on DMs that store `not_flagged` edges (11 of 27); metabolomics `metabolites_by_flags_assay` always stores both states.

## Package import equivalent

```python
from multiomics_explorer import genes_by_boolean_metric

result = genes_by_boolean_metric()
# returns dict with keys: total_matching, total_derived_metrics, total_genes, by_organism, by_compartment, by_publication, by_experiment, by_value, top_categories, by_metric, genes_per_metric_max, genes_per_metric_median, not_found_ids, not_matched_ids, not_found_metric_types, not_matched_metric_types, not_matched_organism, excluded_derived_metrics, warnings, returned, offset, truncated, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
