# differential_expression_by_gene

## What it does

Find differential-expression rows for one organism — one row per
(gene × experiment × timepoint), sorted by |log2FC|. Single-organism
enforced; at least one of `organism` / `locus_tags` / `experiment_ids`
is required. `expression_status` uses each experiment's publication-
specific threshold (not a uniform padj<0.05 cutoff).

Tested-absent semantics depend on the parent experiment's
`table_scope`: `all_detected_genes` keeps `not_significant` rows
(real biology — gene tested but did not respond); any other scope
(`significant_only`, `significant_any_timepoint`, `filtered_subset`,
`top_n`) collapses tested-absent with not-detected. Always check
`by_table_scope` (envelope) and the per-experiment `table_scope`
before reading missing rows. See `docs://guide/conventions` for the
full tested-absent framing.

Routing: `summary=True` for counts-only landscape; per-gene drill-down
to `gene_response_profile`; cross-organism via
`differential_expression_by_ortholog`; pathway interpretation via
`pathway_enrichment` (`docs://analysis/enrichment`).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string \| None | None | Organism: word-based, case-insensitive match on preferred_name + name_synonyms ('MED4' works; a genus word that matches several strains raises — name the strain). E.g. 'MED4', 'Prochlorococcus MED4'. Get valid names from list_organisms. |
| locus_tags | list[string] \| None | None | Gene locus tags. E.g. ['PMM0001', 'PMM0845']. Get these from resolve_gene / gene_overview. |
| experiment_ids | list[string] \| None | None | Experiment IDs to restrict to. Get these from list_experiments. |
| direction | string ('up', 'down', 'both') \| None | None | Filter by expression direction. `'up'` / `'down'` restrict to one arm. `'both'` is the union of significant up + significant down — functionally identical to `direction=None, significant_only=True`; pick whichever spelling is clearer at the call site. Default `None` is unchanged. |
| significant_only | bool | False | If true, return only statistically significant results. |
| growth_phases | list[string] \| None | None | Filter by growth phase(s) at sampling time (case-insensitive, edge-level). Isolates specific-phase rows from multi-phase experiments. E.g. ['exponential']. Live vocabulary: list_filter_values(filter_type='growth_phase'). An unknown value reports in the envelope `warnings`, and any gene with edges outside the requested phase(s) lands in `filtered_out`, not `no_expression`. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Add product, experiment_name, treatment, gene_category, omics_type, coculture_partner to each row. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
organism_name, matching_genes, total_matching, rows_by_status, median_abs_log2fc, max_abs_log2fc, experiment_count, n_experiments, rows_by_treatment_type, rows_by_background_factors, rows_by_growth_phase, by_table_scope, top_categories, experiments, not_found, no_expression, filtered_out, warnings, not_found_experiments, not_matched_experiments, returned, offset, truncated, results
```

- **organism_name** (string): Single organism for all results (e.g. 'Alteromonas macleodii HOT1A3')
- **matching_genes** (int): Distinct genes in results after filters (e.g. 5)
- **total_matching** (int): Total gene x experiment x timepoint rows matching filters (e.g. 15)
- **rows_by_status** (ExpressionStatusBreakdown): Row counts by expression_status across all results
- **median_abs_log2fc** (float | None): Median |log2FC| for significant rows only (e.g. 1.978). Null if no significant rows.
- **max_abs_log2fc** (float | None): Max |log2FC| for significant rows only (e.g. 3.591). Null if no significant rows.
- **experiment_count** (int): Number of experiments in results (e.g. 1)
- **n_experiments** (int): Count of matching experiments before any trimming (e.g. 1). Currently identical to experiment_count.
- **rows_by_treatment_type** (object): Row counts by treatment type (e.g. {'nitrogen': 15})
- **rows_by_background_factors** (object): Row counts by background factor (e.g. {'axenic': 10, 'diel': 5})
- **rows_by_growth_phase** (object): Row counts by growth phase. Growth phase is a timepoint-level condition, not gene-specific.
- **by_table_scope** (object): Row counts by experiment table_scope (e.g. {'all_detected_genes': 100, 'significant_only': 50}). `all_detected_genes` keeps tested-absent (`not_significant`) rows; any other scope (`significant_only`, `significant_any_timepoint`, `filtered_subset`, `top_n`) collapses tested-absent with not-detected. Check before reading missing rows. See `docs://guide/conventions`.
- **top_categories** (list[ExpressionTopCategory]): Top gene categories by significant gene count, max 5
- **experiments** (list[ExpressionByExperiment]): Per-experiment summary, sorted by significant row count desc. Compact by default (experiment_id, treatment_type, table_scope, is_time_course, matching_genes, rows_by_status, omics_type); verbose=True restores experiment_name, background_factors, coculture_partner, table_scope_detail, and the nested per-timepoint breakdown. Capped to the first 10 entries; summary=True returns the full list — n_experiments / experiment_count always reflect the full count.
- **experiments_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **not_found** (list[string]): Input locus_tags not found in KG
- **no_expression** (list[string]): Locus tags in KG with NO Changes_expression_of edge at all in the organism
- **filtered_out** (list[string]): Locus tags that DO have expression edges but none survive the active direction / significant_only / growth_phases filters — e.g. a growth_phases vocabulary typo. Never confuse with no_expression.
- **warnings** (list[string]): One entry per growth_phases value not found in the live vocabulary (see list_filter_values(filter_type='growth_phase')), plus one per not_found locus_tag differing only by case from a real one (locus_tags are never case-normalised). Empty when clean.
- **not_found_experiments** (list[string]): Input experiment_ids not found in KG (empty unless experiment_ids was provided)
- **not_matched_experiments** (list[string]): experiment_ids in KG but with no Changes_expression_of edges satisfying the active filters (e.g. vesicle proteomics / metabolomics experiments that never wire up DE edges; or experiments where no row passes direction / significant_only / growth_phases). Empty unless experiment_ids was provided.
- **returned** (int): Rows in results (e.g. 5)
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if total_matching > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'ACZ81_01830') |
| gene_name | string \| None | Gene name (e.g. 'amtB'). Null if unannotated. |
| experiment_id | string | Experiment ID (e.g. '10.1101/2025.11.24.690089_...') |
| treatment_type | list[string] | Treatment types from experiment (e.g. ['nitrogen']) |
| timepoint | string \| None | Timepoint label (e.g. 'days 60+89'). Null when edge has no label. |
| timepoint_hours | float \| None | Numeric hours (e.g. 432.0). Null for non-numeric labels. |
| timepoint_order | int | Sort key for time course order (e.g. 3) |
| log2fc | float | Log2 fold change (e.g. 3.591). Positive = up. |
| padj | float \| None | Adjusted p-value (e.g. 1.13e-12). Null if not computed. |
| rank | int | Rank by |log2FC| within experiment x timepoint; 1 = strongest (e.g. 77). KG property `rank_by_effect`. Direction-blind and populated on EVERY reported edge — the only genome-wide rank on this row (see rank_up / rank_down). |
| rank_up | int \| None (optional) | Rank by |log2FC| among significant_up genes within experiment x timepoint. Null if not significant_up. 1 = strongest. NOT a genome-wide directional rank — it is populated only on the significant-up subset, so it cannot serve as a ranked list over all detected genes (e.g. for GSEA); sort `log2fc` yourself for that. |
| rank_down | int \| None (optional) | Rank by |log2FC| among significant_down genes within experiment x timepoint. Null if not significant_down. 1 = strongest. NOT a genome-wide directional rank — populated only on the significant-down subset (see rank_up). |
| expression_status | string ('significant_up', 'significant_down', 'not_significant') | Significance call using publication-specific threshold (e.g. 'significant_up') |
| growth_phase | string \| None (optional) | Physiological state of the culture at this timepoint (e.g. 'exponential', 'nutrient_limited'). Timepoint-level condition — not gene-specific. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| product | string \| None (optional) | Gene product description (e.g. 'Ammonium transporter') |
| experiment_name | string \| None (optional) | Human-readable experiment name |
| treatment | string \| None (optional) | Treatment details (e.g. 'PRO99-lowN nutrient starvation') |
| gene_category | string \| None (optional) | Gene functional category (e.g. 'Inorganic ion transport') |
| omics_type | string \| None (optional) | Omics type (e.g. 'RNASEQ') |
| coculture_partner | string \| None (optional) | Coculture partner organism, if applicable |
| table_scope | string \| None (optional) | What genes the source DE table contains (e.g. 'all_detected_genes'). Verbose only. |
| table_scope_detail | string \| None (optional) | Free-text clarification of table_scope. Verbose only. |
| background_factors | list[string] (optional) | Background experimental factors. Verbose only. |

## Few-shot examples

### Example 1: Organism overview (summary only)

```example-call
differential_expression_by_gene(organism="MED4", summary=True)
```

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "matching_genes": 1967,
  "total_matching": 60012,
  "rows_by_status": {"significant_up": 5516, "significant_down": 5538, "not_significant": 48958},
  "median_abs_log2fc": 1.580899074554445,
  "max_abs_log2fc": 162.295,
  "experiment_count": 38,
  "n_experiments": 38,
  "rows_by_treatment_type": {
    "coculture": 5412,
    "carbon": 2015,
    "salt": 1953,
    "viral": 421,
    "phosphorus": 170,
    "light": 5396,
    "iron": 448,
    "nitrogen": 40445,
    "darkness": 3752
  },
  "rows_by_background_factors": {
    "light": 50181,
    "axenic": 36455,
    "chemical": 198,
    "viral": 51,
    "darkness": 683,
    "coculture": 17673,
    "diel": 7860
  },
  "rows_by_growth_phase": {
    "exponential": 6991,
    "acute_stress": 14133,
    "acclimated_steady_state": 2310,
    "infected": 472,
    "nutrient_limited": 24335,
    "recovery": 112,
    "death": 2848,
    "stationary": 654,
    "darkness": 654,
    "diel": 7503
  },
  "by_table_scope": {
    "all_detected_genes": 54444,
    "filtered_subset": 4599,
    "significant_only": 521,
    "significant_any_timepoint": 448
  },
  "top_categories": [
    {"category": "Unknown", "total_genes": 647, "significant_genes": 573},
    {"category": "Stress response and adaptation", "total_genes": 197, "significant_genes": 189},
    {"category": "Coenzyme metabolism", "total_genes": 177, "significant_genes": 157},
    {"category": "Translation", "total_genes": 141, "significant_genes": 127},
    {"category": "Amino acid metabolism", "total_genes": 100, "significant_genes": 93}
  ],
  "experiments": [
    {
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_coculture",
      "treatment_type": ["nitrogen"],
      "omics_type": "RNASEQ",
      "is_time_course": "time_course",
      "table_scope": "all_detected_genes",
      "matching_genes": 1849,
      "rows_by_status": {"significant_up": 553, "significant_down": 834, "not_significant": 7858}
    },
    {
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "treatment_type": ["nitrogen"],
      "omics_type": "RNASEQ",
      "is_time_course": "time_course",
      "table_scope": "all_detected_genes",
      "matching_genes": 1849,
      "rows_by_status": {"significant_up": 602, "significant_down": 640, "not_significant": 2456}
    },
    {
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_proteomics_axenic",
      "treatment_type": ["nitrogen"],
      "omics_type": "PROTEOMICS",
      "is_time_course": "time_course",
      "table_scope": "all_detected_genes",
      "matching_genes": 1424,
      "rows_by_status": {"significant_up": 599, "significant_down": 556, "not_significant": 3117}
    },
    {
      "experiment_id": "10.64898/2026.04.15.718746_extended_darkness_med4",
      "treatment_type": ["darkness"],
      "omics_type": "RNASEQ",
      "is_time_course": "time_course",
      "table_scope": "all_detected_genes",
      "matching_genes": 1876,
      "rows_by_status": {"significant_up": 556, "significant_down": 469, "not_significant": 2727}
    },
    {
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_proteomics_coculture",
      "treatment_type": ["nitrogen"],
      "omics_type": "PROTEOMICS",
      "is_time_course": "time_course",
      "table_scope": "all_detected_genes",
      "matching_genes": 1424,
      "rows_by_status": {"significant_up": 609, "significant_down": 394, "not_significant": 6117}
    },
    ...
  ],
  "experiments_truncated": null,
  "not_found": [],
  "no_expression": [],
  "filtered_out": [],
  "warnings": [],
  "not_found_experiments": [],
  "not_matched_experiments": [],
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "results": []
}
```

### Example 2: Top responders in an organism

```example-call
differential_expression_by_gene(organism="HOT1A3", significant_only=True, limit=10)
```

### Example 3: Gene expression profile across conditions

```example-call
differential_expression_by_gene(locus_tags=["PMM0001"], limit=20)
```

### Example 4: Batch genes in a specific experiment

```example-call
differential_expression_by_gene(locus_tags=["ACZ81_01830", "ACZ81_15555"], experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_hot1a3_rnaseq_axenic"], limit=20)
```

```example-response
{
  "organism_name": "Alteromonas macleodii HOT1A3",
  "matching_genes": 2,
  "total_matching": 6,
  "rows_by_status": {"significant_up": 2, "significant_down": 0, "not_significant": 4},
  "median_abs_log2fc": 2.7846347522016206,
  "max_abs_log2fc": 3.5913485347500225,
  "experiment_count": 1,
  "n_experiments": 1,
  "rows_by_treatment_type": {"nitrogen": 6},
  "rows_by_background_factors": {"axenic": 6, "light": 6},
  "rows_by_growth_phase": {"nutrient_limited": 6},
  "by_table_scope": {"all_detected_genes": 6},
  "top_categories": [
    {"category": "Inorganic ion transport", "total_genes": 1, "significant_genes": 1},
    {"category": "Signal transduction", "total_genes": 1, "significant_genes": 1}
  ],
  "experiments": [
    {
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_hot1a3_rnaseq_axenic",
      "treatment_type": ["nitrogen"],
      "omics_type": "RNASEQ",
      "is_time_course": "time_course",
      "table_scope": "all_detected_genes",
      "matching_genes": 2,
      "rows_by_status": {"significant_up": 2, "significant_down": 0, "not_significant": 4}
    }
  ],
  "experiments_truncated": null,
  "not_found": [],
  "no_expression": [],
  "filtered_out": [],
  "warnings": [],
  "not_found_experiments": [],
  "not_matched_experiments": [],
  "returned": 6,
  "offset": 0,
  "truncated": false,
  "results": [
    {
      "locus_tag": "ACZ81_01830",
      "gene_name": "amtB",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_hot1a3_rnaseq_axenic",
      "treatment_type": ["nitrogen"],
      "timepoint": "days 60+89",
      "timepoint_hours": null,
      "timepoint_order": 3,
      "log2fc": 3.5913485347500225,
      "padj": 1.134324271714239e-12,
      "rank": 77,
      "rank_up": 29,
      "rank_down": null,
      "expression_status": "significant_up",
      "growth_phase": "nutrient_limited"
    },
    {
      "locus_tag": "ACZ81_15555",
      "gene_name": "glnL",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_hot1a3_rnaseq_axenic",
      "treatment_type": ["nitrogen"],
      "timepoint": "days 60+89",
      "timepoint_hours": null,
      "timepoint_order": 3,
      "log2fc": 1.9779209696532185,
      "padj": 2.312257501433529e-06,
      "rank": 410,
      "rank_up": 95,
      "rank_down": null,
      "expression_status": "significant_up",
      "growth_phase": "nutrient_limited"
    },
    {
      "locus_tag": "ACZ81_01830",
      "gene_name": "amtB",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_hot1a3_rnaseq_axenic",
      "treatment_type": ["nitrogen"],
      "timepoint": "day 18",
      "timepoint_hours": 432.0,
      "timepoint_order": 1,
      "log2fc": 0.8560175767959709,
      "padj": 0.2588535702469227,
      "rank": 1103,
      "rank_up": null,
      "rank_down": null,
      "expression_status": "not_significant",
      "growth_phase": "nutrient_limited"
    },
    ...
  ]
}
```

### Example 5: Experiment without DE edges (vesicle proteomics / metabolomics)

```example-call
differential_expression_by_gene(experiment_ids=["10.1126/science.1243457_vesicle_proteomics_med4"], significant_only=True)
```

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "matching_genes": 0,
  "total_matching": 0,
  "rows_by_status": {"significant_up": 0, "significant_down": 0, "not_significant": 0},
  "median_abs_log2fc": null,
  "max_abs_log2fc": null,
  "experiment_count": 0,
  "n_experiments": 0,
  "rows_by_treatment_type": {},
  "rows_by_background_factors": {},
  "rows_by_growth_phase": {},
  "by_table_scope": {},
  "top_categories": [],
  "experiments": [],
  "experiments_truncated": null,
  "not_found": [],
  "no_expression": [],
  "filtered_out": [],
  "warnings": [],
  "not_found_experiments": [],
  "not_matched_experiments": ["10.1126/science.1243457_vesicle_proteomics_med4"],
  "returned": 0,
  "offset": 0,
  "truncated": false,
  "results": []
}
```

### Example 6: Both significant directions in one call (direction='both')

```example-call
differential_expression_by_gene(organism="MED4", direction="both", summary=True)
```

### Example 7: Chaining — find genes then check expression

```
Step 1: genes_by_function(search_text="nitrogen transport", organism="HOT1A3")
        → collect locus_tags from results

Step 2: differential_expression_by_gene(locus_tags=["ACZ81_01830", ...], summary=True)
        → check rows_by_status for significant hits, check by_table_scope for data completeness

Step 3: differential_expression_by_gene(locus_tags=["ACZ81_01830", ...], significant_only=True, limit=20)
        → get the significant expression rows
```

## Chaining patterns

```
genes_by_function → differential_expression_by_gene
genes_by_ontology → differential_expression_by_gene
gene_overview → differential_expression_by_gene (check expression_edge_count first)
list_experiments → differential_expression_by_gene (filter by table_scope there, pass experiment_ids)
differential_expression_by_gene → list_experiments(experiment_ids=[...]) to get the partner organism of a coculture experiment — `coculture_partner` is verbose-only in the compact experiments[] envelope
```

## Common mistakes

```mistake
Interpreting absence of a row as 'no change' when truncated=true
```

```correction
Check truncated flag; use summary=True for reliable counts or increase limit
```

```mistake
Assuming no_expression means 'not differentially expressed'
```

```correction
no_expression means no data available — gene may not have been profiled in those experiments
```

```mistake
Reading an empty `results=[]` as 'no DE response' when experiment_ids was passed
```

```correction
Check not_found_experiments (typo'd id) and not_matched_experiments (id real but no edges satisfy the filter — e.g. vesicle proteomics, or a too-strict significant_only). Empty results + non-empty not_matched_experiments means the filter eliminated every row, not that the gene didn't respond.
```

```mistake
Interpreting a missing gene as 'not affected' without checking table_scope
```

```correction
Check the experiment's table_scope — if significant_only or top_n, the gene may simply not have been reported. Only all_detected_genes experiments can distinguish 'not affected' from 'not reported'.
```

```mistake
Mixing organisms in a single call (e.g. MED4 + HOT1A3 locus_tags)
```

```correction
Call once per organism — tool enforces single-organism constraint
```

```mistake
differential_expression_by_gene(organism='Prochlorococcus', summary=True)  # genus word
```

```correction
differential_expression_by_gene(organism='MED4', summary=True)  # organism= is a word-based, case-insensitive match on preferred_name + name_synonyms — 'MED4' works; a bare genus word matches every strain and raises 'matches multiple organisms — be more specific'
```

- 'Meiothermus ruber' names two OrganismTaxon nodes (a genome strain and a gene-less treatment taxon). organism='Meiothermus ruber' resolves to the genome strain only (resolution gates on gene_count > 0), so it does not raise — but never join organism rows from list_organisms by that name.

- `direction` and `significant_only` interplay: when direction is 'up' / 'down' / 'both' it filters expression_status directly and `significant_only` is ignored (direction='up', significant_only=False still returns only significant_up rows). `significant_only=True` only matters with direction=None, where it drops not_significant rows — i.e. it equals direction='both'. Pick whichever spelling is clearer at the call site; default direction=None, significant_only=False returns everything.

- treatment_type / background_factors / growth_phase values are LIVE vocabularies read from the KG, not enums. An unknown growth_phases value (e.g. 'log' instead of 'exponential') now reports in the envelope `warnings` (e.g. "growth_phases value 'log' matched nothing — valid values: ... (list_filter_values(filter_type='growth_phase'))") — check `warnings` before trusting an empty or reduced result. Check list_filter_values(filter_type='growth_phase') or list_experiments(summary=True)'s by_treatment_type / by_background_factors rollup before filtering. Current treatment values are short nouns (nitrogen, light, carbon, iron, darkness, phosphorus, salt, viral, coculture, diel, ...); background_factors are light, axenic, coculture, darkness, diel, viral, chemical. Here they surface as the growth_phases filter and the rows_by_treatment_type / rows_by_background_factors / rows_by_growth_phase summary keys.

```mistake
Assuming a growth_phases typo silently returns 0 rows with no signal
```

```correction
A growth_phases value not in the live vocabulary lands in the envelope `warnings` (one entry per bad value), and any gene whose expression edges exist but fail to match direction / significant_only / growth_phases lands in `filtered_out` — never in `no_expression`, which is reserved for a gene with NO Changes_expression_of edge at all in the organism.
```

- `no_expression` is this tool's name for the not_matched bucket — a gene exists but has NO Changes_expression_of edge at all in the organism; `filtered_out` is the DIFFERENT bucket for a gene that DOES have edges but none survive direction / significant_only / growth_phases (including a vocabulary typo); `not_found` = locus_tag absent; experiment ids get their own `not_found_experiments` / `not_matched_experiments` pair. See docs://guide/conventions for the shared not_found / not_matched semantics.

```mistake
Treating `rank_up` / `rank_down` as genome-wide directional ranks (e.g. as the ranked list for a GSEA-style test or a genome-wide null)
```

```correction
They are populated ONLY on the significant subset — `rank_up` is non-null on significant_up genes, `rank_down` on significant_down genes; every non-significant gene is null and silently drops out. The one rank present on every reported edge is `rank` (KG property `rank_by_effect`, surfaced here under the shorter name), which is |log2FC|-based and direction-blind. For a signed genome-wide ranking sort the rows by `log2fc` yourself over an `all_detected_genes` experiment (check `table_scope` first), and use `rank_up` / `rank_down` only as validation handles for the significant tail.
```

- expression_status uses publication-specific thresholds, not a uniform padj<0.05

- Use summary=True first to see the landscape, then drill into specific genes/experiments

- Check by_table_scope in the summary to understand data completeness before drawing conclusions

- growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — NOT a gene-specific property

- For cross-experiment summarization (which treatments does this gene set respond to?) see `docs://guide/python_api` (Cross-experiment summarization — `response_matrix` for gene × treatment pivots, `gene_set_compare` for two-set overlap). For pathway-level interpretation chain to `pathway_enrichment` (`docs://analysis/enrichment`).

```mistake
Expecting per-timepoint counts, experiment_name, or table_scope_detail inside `experiments[]` from a plain call
```

```correction
`summary=True` (and every call by default) is the cheap landscape — each `experiments[]` entry is compact (experiment_id, treatment_type, table_scope, is_time_course, matching_genes, rows_by_status, omics_type). Per-timepoint counts and the other experiment metadata (experiment_name, background_factors, coculture_partner, table_scope_detail) need `verbose=True`.
```

## Package import equivalent

```python
from multiomics_explorer import differential_expression_by_gene

result = differential_expression_by_gene()
# returns dict with keys: organism_name, matching_genes, total_matching, rows_by_status, median_abs_log2fc, max_abs_log2fc, experiment_count, n_experiments, rows_by_treatment_type, rows_by_background_factors, rows_by_growth_phase, by_table_scope, top_categories, experiments, experiments_truncated, not_found, no_expression, filtered_out, warnings, not_found_experiments, not_matched_experiments, returned, offset, truncated, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
