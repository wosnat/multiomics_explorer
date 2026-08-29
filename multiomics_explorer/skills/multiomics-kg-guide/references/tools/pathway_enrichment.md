# pathway_enrichment

## What it does

Run pathway over-representation analysis from DE results (Fisher + BH).

Single-organism enforced. `direction='both'` runs up + down per
experiment × timepoint cluster. Three background modes — `table_scope`
(default, per-cluster quantified set), `organism` (full genome), or an
explicit locus_tag list — drive the Fisher denominator and matter more
than the ontology choice.

[TRUST] `sources` / `evidence` / `max_tier` / `min_evidence_score` /
`call_class` filter TERM2GENE at the same match stage as the
background, so tested sets and background move together;
`interpro_type` is required when `ontology='interpro'` (ranking
across mixed entry types is not meaningful). See
docs://analysis/annotation_evidence.

Routing: pre-flight via `ontology_landscape` to pick `(ontology, level)`;
chain `differential_expression_by_gene` for raw DE inputs; drill enriched
terms via `gene_overview` or, for KEGG, `list_metabolites(pathway_ids=...)`
to inspect compound-anchored membership of an enriched pathway.
See docs://analysis/enrichment for Fisher + BH methodology and
background semantics; docs://examples/pathway_enrichment.py for runnable
code (EnrichmentResult accessors, custom term2gene, compareCluster export).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string | — | Organism: word-based, case-insensitive match on preferred_name + name_synonyms ('MED4' works; ambiguous match raises). Single-organism enforced. |
| experiment_ids | list[string] | — | Experiments to pull DE from. Get IDs from list_experiments. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') | — | Ontology for pathway definitions. Run ontology_landscape first to rank by relevance. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'. See docs://guide/conventions for the BRITE-tree scoping rule. |
| level | int \| None | None | Hierarchy level (0 = root). At least one of `level` or `term_ids` required. See docs://guide/conventions. |
| term_ids | list[string] \| None | None | Specific term IDs to test. Combines with level to scope rollup. |
| direction | string ('up', 'down', 'both') | both | DE direction(s) to include in gene_sets. |
| significant_only | bool | True | If true, only significant DE rows count as foreground. |
| background | string \| list[string] | table_scope | 'table_scope' (default, per-cluster quantified set), 'organism' (full genome — inflates denominator), or explicit locus_tag list. See docs://analysis/enrichment for the full background semantics. |
| min_gene_set_size | int | 5 | Per-cluster M filter: drop pathways with fewer members in the background. |
| max_gene_set_size | int \| None | 500 | Per-cluster M filter upper bound. None disables. |
| pvalue_cutoff | float | 0.05 | Significance threshold for `p_adjust`. |
| timepoint_filter | list[string] \| None | None | Restrict to these timepoint labels. Useful for 10+ timepoint experiments. |
| growth_phases | list[string] \| None | None | Filter DE results by growth phase(s) before enrichment (case-insensitive). E.g. ['exponential']. |
| summary | bool | False | If true, omit results (envelope only). |
| limit | int | 100 | Max rows returned. Default 100 — top hits by p_adjust globally. |
| offset | int | 0 | Skip N rows before limit. |
| informative_only | bool | True | When True (default), exclude ontology terms flagged uninformative in the KG (e.g. KEGG KO 'uncharacterized protein' terms, GO root go:0008150; the global / overview KEGG maps such as ko01100). Term-side filter — never restricts the gene set, background, or DE inputs. Pass False to include uninformative terms; per-row is_informative still surfaces in either mode. [ENR] Default flipped to True in 2026-05 KG release; see docs://guide/conventions. |
| sources | list[string] \| None | None | Keep rows whose edge sources[] contains any of these values (e.g. ['eggnog']). Valid on the 14 functional-edge ontologies (not PSORTb / SignalP). Default None never filters. See list_filter_values(filter_type='sources'). |
| evidence | list[string] \| None | None | Keep rows whose compact evidence ladder value is in this list (read the value; rung assignment is per ontology — see docs://analysis/annotation_evidence). Valid on the 14 functional-edge ontologies. Default None never filters. |
| max_tier | int \| None | None | Keep rows with edge tier <= this value OR tier IS NULL (diamond truncation depth, 1-3; tier-null edges are always kept - see by_tier's null bucket). Valid on tcdb, merops only. |
| min_evidence_score | float \| None | None | Keep rows with edge evidence_score >= this cutoff (composite trust score, 0-1; the only native-scalar cutoff allowed). Valid on go_bp/mf/cc, ec, pfam, cazy, tcdb, merops. Envelope adds evidence_score_signals when set. |
| call_class | list[string ('peptidase', 'inhibitor', 'nonpeptidase_homolog')] \| None | None | MEROPS peptidase-call filter: keep rows whose call_class is in this list. Merops only; leaving unfiltered mixes in catalytically-dead homologs (nonpeptidase_homolog) - the envelope warns when it does. |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type (e.g. 'DOMAIN', 'FAMILY'). InterPro only; required on interpro enrichment/landscape strata - ranking across mixed entry types is not meaningful. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
organism_name, ontology, level, total_matching, returned, truncated, offset, n_significant, by_experiment, by_direction, by_omics_type, cluster_summary, top_clusters_by_min_padj, top_pathways_by_padj, not_found, not_matched, no_expression, not_found_experiments, term_validation, clusters_skipped, enrichment_params, filters_applied, trust_axes, background_filtered, interpro_type, results
```

- **organism_name** (string): Single organism
- **ontology** (string): Ontology used
- **level** (int | None): Hierarchy level used (or None for term_ids-only)
- **total_matching** (int): Total (cluster x term) rows pre-pagination; equals Fisher tests run
- **returned** (int): Rows in this response
- **truncated** (bool): True when total_matching exceeds offset+returned
- **offset** (int): Pagination offset
- **n_significant** (int): Rows with p_adjust below pvalue_cutoff
- **by_experiment** (list[PathwayEnrichmentByExperiment]): Per-experiment tests + significance
- **by_direction** (list[PathwayEnrichmentByDirection]): Per-direction aggregates
- **by_omics_type** (list[PathwayEnrichmentByOmicsType]): Per-omics-type aggregates
- **cluster_summary** (PathwayEnrichmentClusterSummary): Distribution stats across clusters
- **top_clusters_by_min_padj** (list[PathwayEnrichmentTopCluster]): Top 5 clusters by smallest p_adjust
- **top_pathways_by_padj** (list[PathwayEnrichmentTopPathway]): Top 10 pathways by p_adjust across all clusters
- **not_found** (list[string]): Requested experiment_ids absent from KG
- **not_matched** (list[string]): Experiment IDs found but wrong organism
- **no_expression** (list[string]): Experiments matching organism but with no DE rows
- **not_found_experiments** (list[string]): experiment_ids absent from the KG (partial-batch bucket; raises instead when every requested experiment_id lands here).
- **term_validation** (PathwayEnrichmentTermValidation): Namespaced passthrough of term_id validation from genes_by_ontology
- **clusters_skipped** (list[PathwayEnrichmentClusterSkipped]): Clusters that produced no rows, with reason
- **enrichment_params** (object | None): ORA parameters used for this call. See docs://analysis/enrichment.
- **filters_applied** (object): Echo of the trust filters actually set on this call. See docs://analysis/annotation_evidence.
- **trust_axes** (object): Trust axes the chosen ontology carries, e.g. {'tcdb': ['sources','evidence','evidence_score','tier']}.
- **background_filtered** (bool): True when a trust filter narrowed the background.
- **interpro_type** (string | None): Echo of the interpro_type stratum used (sparse: only when ontology='interpro').

### Per-result fields

| Field | Type | Description |
|---|---|---|
| cluster | string | Cluster key '{experiment_id}|{timepoint}|{direction}' |
| experiment_id | string | Experiment identifier |
| name | string \| None (optional) | Experiment display name |
| timepoint | string | Timepoint label; 'NA' for experiments without timepoints |
| timepoint_hours | float \| None (optional) | Numeric time in hours |
| timepoint_order | int \| None (optional) | Integer ordinal of the timepoint |
| direction | string | Expression direction: 'up' or 'down' |
| omics_type | string \| None (optional) | Experiment omics type (transcriptomics, proteomics, ...) |
| table_scope | string \| None (optional) | Coarse table_scope classifier |
| treatment_type | list[string] \| None (optional) | Treatment-type tags |
| background_factors | list[string] \| None (optional) | Background-condition tags |
| is_time_course | bool \| None (optional) | True for time-course experiments |
| growth_phase | string \| None (optional) | Physiological state of the culture at this timepoint. Timepoint-level, not gene-specific. |
| term_id | string | Ontology term ID |
| term_name | string | Ontology term display name |
| level | int \| None (optional) | Hierarchy depth of the term (0 = root) |
| is_informative | bool | True if the term is not flagged is_uninformative in the KG. Always present, regardless of informative_only setting, so callers can post-filter or diagnose. With default informative_only=True, all rows have is_informative=True by construction; pass informative_only=False to opt out and see uninformative terms. |
| tree | string \| None (optional) | BRITE tree name (sparse: BRITE only) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: BRITE only) |
| gene_ratio | string | 'k/n' string — DE genes in pathway over total DE genes in cluster (clusterProfiler: GeneRatio) |
| gene_ratio_numeric | float | k/n as float |
| bg_ratio | string | 'M/N' string — pathway members over background size (clusterProfiler: BgRatio) |
| bg_ratio_numeric | float | M/N as float |
| rich_factor | float | k/M — fraction of pathway's background members that are DE (clusterProfiler: RichFactor) |
| fold_enrichment | float | (k/n) / (M/N) — observed over null (clusterProfiler: FoldEnrichment) |
| pvalue | float | Fisher-exact p-value (one-sided enrichment) |
| p_adjust | float | Benjamini-Hochberg FDR within cluster (clusterProfiler: p.adjust) |
| count | int | k — DE genes in pathway (clusterProfiler: Count) |
| bg_count | int | M — pathway members in cluster's background |
| signed_score | float | sign * -log10(p_adjust); sign from direction (up: +, down: -) |
| foreground_gene_ids | list[string] \| None (optional) | Verbose only: the k DE genes in this pathway (clusterProfiler: geneID split) |
| background_gene_ids | list[string] \| None (optional) | Verbose only: pathway members in background NOT in DE set (non-overlapping complement) |

### `informative_only` filter

When True (default), exclude ontology terms flagged uninformative
in the KG (e.g. GO root go:0008150, catch-all Cyanorak / TIGR roles,
KEGG KOs named "uncharacterized protein"). Term-side filter — never
restricts the gene set, background, or DE inputs. Pass False to
include uninformative terms; per-row `is_informative` still surfaces
in either mode. KEGG is flagged at KO level (catch-all KOs) and at
pathway level (the global / overview maps, `ko01100` and kin), so a
`level=2` KEGG run loses those rows under the default.

See `docs://analysis/enrichment` (section "Informative-only filtering")
for rationale, Fisher denominator behavior, and opt-out guidance.


### Cluster naming

Cluster IDs returned in `results[].cluster` follow the canonical format:

```
{experiment_id}|{timepoint}|{direction}
```

Examples: `Tolonen_Ndeplete_R1|6h|up`, `Weissberg_axenic_RNA|day14|down`.

Timepoint handling: experiments without numeric timepoints (single-condition
studies) render the timepoint slot as the literal string `"NA"` —
e.g. `cluster_membership_exp1|NA|up`.

Drill-down accessors take the cluster string verbatim:

```python
result.explain("Tolonen_Ndeplete_R1|6h|up", "kegg.pathway:ko00910")
result.overlap_genes("Tolonen_Ndeplete_R1|6h|up", "kegg.pathway:ko00910")
```


## Few-shot examples

### Example 1: Single experiment, default direction=both

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="cyanorak_role", level=1)
```

### Example 2: Multi-experiment compareCluster analog (10 experiments in one call)

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_proteomics_axenic", "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic", "10.1128/spectrum.03275-22_dark_low_glucose_med4_proteomics", "10.1128/spectrum.03275-22_dark_high_glucose_med4_proteomics", "10.1128/spectrum.03275-22_light_low_glucose_med4_proteomics", "10.1128/spectrum.03275-22_light_high_glucose_med4_proteomics", "10.3389/fmicb.2022.1038136_salt_low_salinity_acclimation_28_med4_rnaseq", "10.1038/ismej.2017.88_nitrogen_stress_ndepleted_pro99_medium_med4_rnaseq", "10.1371/journal.pone.0165375_light_stress_constant_dark_med4_rnaseq_dark", "10.1371/journal.pone.0165375_viral_phage_phm2_lysate_med4_rnaseq_light"], ontology="cyanorak_role", level=1)
```

### Example 3: Summary-only (envelope, no rows)

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="cyanorak_role", level=1, summary=True)
```

### Example 4: Scope to specific pathways at a level

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="cyanorak_role", level=1, term_ids=["cyanorak.role:J", "cyanorak.role:K"])
```

### Example 5: BRITE tree-scoped enrichment (transporters)

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="brite", tree="transporters", level=1)
```

### Example 6: From landscape to enrichment

```
Step 1: ontology_landscape(organism="MED4", experiment_ids=[...])
        → pick an (ontology, level) by relevance_rank

Step 2: pathway_enrichment(organism="MED4", experiment_ids=[...], ontology=<picked>, level=<picked>)
        → Fisher ORA results
```

### Example 7: Hand-curated DAG-ontology panel via search_ontology + term_ids

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="go_bp", term_ids=["go:0071941", "go:0071705"])
```

### Example 8: InterPro enrichment scoped to one type

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="interpro", interpro_type="HOMOLOGOUS_SUPERFAMILY", level=0)
```

### Example 9: MEROPS enrichment restricted to peptidase calls (call_class)

```example-call
pathway_enrichment(organism="MIT1002", experiment_ids=["10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq"], ontology="merops", call_class=["peptidase"], level=0)
```

*call_class shapes the TERM2GENE mapping and the background identically (both go through the same gene->leaf MATCH), so foreground and background stay apples-to-apples. Omitting call_class tests nonpeptidase_homolog rows alongside real peptidases, inflating clan term sizes with catalytically-dead hits. Pick the experiment with list_experiments(organism='MIT1002', omics_type='rnaseq') — a MIT9301 metabolomics experiment passed here would return 0 rows.*

```example-response
{
  "organism_name": "Alteromonas macleodii MIT1002",
  "ontology": "merops",
  "level": 0,
  "total_matching": 98,
  "returned": 98,
  "truncated": false,
  "offset": 0,
  "n_significant": 5,
  "by_experiment": [
    {
      "experiment_id": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq",
      "name": "MIT1002 Dark-tolerant co-culture under 13:11 diel light:dark cycle vs Parental co-culture under 13:11 diel light:dark...",
      "omics_type": "RNASEQ",
      "table_scope": "significant_any_timepoint",
      "treatment_type": ["darkness"],
      "background_factors": ["coculture", "diel"],
      "is_time_course": true,
      "n_tests": 98,
      "n_significant": 5,
      "n_clusters": 14
    }
  ],
  "by_direction": [
    {"direction": "down", "n_tests": 49, "n_significant": 5},
    {"direction": "up", "n_tests": 49, "n_significant": 0}
  ],
  "by_omics_type": [{"omics_type": "RNASEQ", "n_tests": 98, "n_significant": 5}],
  "cluster_summary": {
    "n_clusters": 14,
    "n_tests_min": 7,
    "n_tests_median": 7.0,
    "n_tests_max": 7,
    "n_significant_min": 0,
    "n_significant_median": 0.0,
    "n_significant_max": 1,
    "universe_size_min": 3856,
    "universe_size_median": 3856.0,
    "universe_size_max": 3856
  },
  "top_clusters_by_min_padj": [
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|4h|down",
      "experiment_id": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq",
      "name": "MIT1002 Dark-tolerant co-culture under 13:11 diel light:dark cycle vs Parental co-culture under 13:11 diel light:dark...",
      "timepoint": "4h",
      "timepoint_hours": 4.0,
      "timepoint_order": 2,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "significant_any_timepoint",
      "treatment_type": ["darkness"],
      "background_factors": ["coculture", "diel"],
      "is_time_course": true,
      "n_tests": 7,
      "n_significant": 1,
      "universe_size": 3856,
      "min_padj": 0.0002629517773314062
    },
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|20h|down",
      "experiment_id": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq",
      "name": "MIT1002 Dark-tolerant co-culture under 13:11 diel light:dark cycle vs Parental co-culture under 13:11 diel light:dark...",
      "timepoint": "20h",
      "timepoint_hours": 20.0,
      "timepoint_order": 6,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "significant_any_timepoint",
      "treatment_type": ["darkness"],
      "background_factors": ["coculture", "diel"],
      "is_time_course": true,
      "n_tests": 7,
      "n_significant": 1,
      "universe_size": 3856,
      "min_padj": 0.008692801673555146
    },
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|16h|down",
      "experiment_id": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq",
      "name": "MIT1002 Dark-tolerant co-culture under 13:11 diel light:dark cycle vs Parental co-culture under 13:11 diel light:dark...",
      "timepoint": "16h",
      "timepoint_hours": 16.0,
      "timepoint_order": 5,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "significant_any_timepoint",
      "treatment_type": ["darkness"],
      "background_factors": ["coculture", "diel"],
      "is_time_course": true,
      "n_tests": 7,
      "n_significant": 1,
      "universe_size": 3856,
      "min_padj": 0.010203101803113903
    },
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|0h|down",
      "experiment_id": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq",
      "name": "MIT1002 Dark-tolerant co-culture under 13:11 diel light:dark cycle vs Parental co-culture under 13:11 diel light:dark...",
      "timepoint": "0h",
      "timepoint_hours": 0.0,
      "timepoint_order": 1,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "significant_any_timepoint",
      "treatment_type": ["darkness"],
      "background_factors": ["coculture", "diel"],
      "is_time_course": true,
      "n_tests": 7,
      "n_significant": 1,
      "universe_size": 3856,
      "min_padj": 0.01418211730594244
    },
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|8h|down",
      "experiment_id": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq",
      "name": "MIT1002 Dark-tolerant co-culture under 13:11 diel light:dark cycle vs Parental co-culture under 13:11 diel light:dark...",
      "timepoint": "8h",
      "timepoint_hours": 8.0,
      "timepoint_order": 3,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "significant_any_timepoint",
      "treatment_type": ["darkness"],
      "background_factors": ["coculture", "diel"],
      "is_time_course": true,
      "n_tests": 7,
      "n_significant": 1,
      "universe_size": 3856,
      "min_padj": 0.024018322030219336
    }
  ],
  "top_pathways_by_padj": [
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|4h|down",
      "term_id": "merops.clan:SB",
      "term_name": "SB",
      "p_adjust": 0.0002629517773314062,
      "signed_score": -3.5801238893775684
    },
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|20h|down",
      "term_id": "merops.clan:SB",
      "term_name": "SB",
      "p_adjust": 0.008692801673555146,
      "signed_score": -2.060840228699125
    },
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|16h|down",
      "term_id": "merops.clan:SB",
      "term_name": "SB",
      "p_adjust": 0.010203101803113903,
      "signed_score": -1.9912677800819054
    },
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|0h|down",
      "term_id": "merops.clan:SB",
      "term_name": "SB",
      "p_adjust": 0.01418211730594244,
      "signed_score": -1.8482589267239409
    },
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|8h|down",
      "term_id": "merops.clan:SB",
      "term_name": "SB",
      "p_adjust": 0.024018322030219336,
      "signed_score": -1.6194573365863747
    },
    ...
  ],
  "not_found": [],
  "not_matched": [],
  "no_expression": [],
  "term_validation": {"not_found": [], "wrong_ontology": [], "wrong_level": [], "filtered_out": []},
  "clusters_skipped": [],
  "enrichment_params": {
    "organism": "MIT1002",
    "ontology": "merops",
    "level": 0,
    "term_ids": null,
    "tree": null,
    "informative_only": true,
    "min_gene_set_size": 5,
    "max_gene_set_size": 500,
    "pvalue_cutoff": 0.05,
    "background_mode": "table_scope",
    "experiment_ids": ["10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq"],
    "direction": "both",
    "significant_only": true,
    "timepoint_filter": null,
    "growth_phases": null,
    "n_clusters_input": 14,
    "n_clusters_tested": 14,
    "n_clusters_skipped": 0,
    "term2gene_row_count": 118,
    "n_unique_terms": 27,
    "multitest_method": "fdr_bh",
    "filters_applied": {"call_class": ["peptidase"]},
    "trust_axes": {"merops": ["sources", "evidence", "evidence_score", "tier"]},
    "background_filtered": true,
    "interpro_type": null
  },
  "filters_applied": {"call_class": ["peptidase"]},
  "trust_axes": {"merops": ["sources", "evidence", "evidence_score", "tier"]},
  "background_filtered": true,
  "interpro_type": null,
  "results": [
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|4h|down",
      "experiment_id": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq",
      "name": "MIT1002 Dark-tolerant co-culture under 13:11 diel light:dark cycle vs Parental co-culture under 13:11 diel light:dark...",
      "timepoint": "4h",
      "timepoint_hours": 4.0,
      "timepoint_order": 2,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "significant_any_timepoint",
      "treatment_type": ["darkness"],
      "background_factors": ["coculture", "diel"],
      "is_time_course": true,
      "growth_phase": "diel",
      "term_id": "merops.clan:SB",
      "term_name": "SB",
      "level": 0,
      "is_informative": true,
      "gene_ratio": "3/49",
      "gene_ratio_numeric": 0.061224489795918366,
      "bg_ratio": "6/3856",
      "bg_ratio_numeric": 0.0015560165975103733,
      "rich_factor": 0.5,
      "fold_enrichment": 39.3469387755102,
      "pvalue": 3.7564539618772316e-05,
      "p_adjust": 0.0002629517773314062,
      "count": 3,
      "bg_count": 6,
      "signed_score": -3.5801238893775684
    },
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|20h|down",
      "experiment_id": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq",
      "name": "MIT1002 Dark-tolerant co-culture under 13:11 diel light:dark cycle vs Parental co-culture under 13:11 diel light:dark...",
      "timepoint": "20h",
      "timepoint_hours": 20.0,
      "timepoint_order": 6,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "significant_any_timepoint",
      "treatment_type": ["darkness"],
      "background_factors": ["coculture", "diel"],
      "is_time_course": true,
      "growth_phase": "diel",
      "term_id": "merops.clan:SB",
      "term_name": "SB",
      "level": 0,
      "is_informative": true,
      "gene_ratio": "2/36",
      "gene_ratio_numeric": 0.05555555555555555,
      "bg_ratio": "6/3856",
      "bg_ratio_numeric": 0.0015560165975103733,
      "rich_factor": 0.3333333333333333,
      "fold_enrichment": 35.7037037037037,
      "pvalue": 0.0012418288105078778,
      "p_adjust": 0.008692801673555146,
      "count": 2,
      "bg_count": 6,
      "signed_score": -2.060840228699125
    },
    {
      "cluster": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq|16h|down",
      "experiment_id": "10.1093/ismeco/ycae131_darkness_darktolerant_coculture_under_1311_mit1002_rnaseq",
      "name": "MIT1002 Dark-tolerant co-culture under 13:11 diel light:dark cycle vs Parental co-culture under 13:11 diel light:dark...",
      "timepoint": "16h",
      "timepoint_hours": 16.0,
      "timepoint_order": 5,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "significant_any_timepoint",
      "treatment_type": ["darkness"],
      "background_factors": ["coculture", "diel"],
      "is_time_course": true,
      "growth_phase": "diel",
      "term_id": "merops.clan:SB",
      "term_name": "SB",
      "level": 0,
      "is_informative": true,
      "gene_ratio": "2/39",
      "gene_ratio_numeric": 0.05128205128205128,
      "bg_ratio": "6/3856",
      "bg_ratio_numeric": 0.0015560165975103733,
      "rich_factor": 0.3333333333333333,
      "fold_enrichment": 32.95726495726496,
      "pvalue": 0.0014575859718734146,
      "p_adjust": 0.010203101803113903,
      "count": 2,
      "bg_count": 6,
      "signed_score": -1.9912677800819054
    },
    ...
  ]
}
```

### Example 10: Trust-filtered TCDB enrichment (sources + evidence + min_evidence_score)

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="tcdb", level=2, evidence=["homology"], min_evidence_score=0.6)
```

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "ontology": "tcdb",
  "level": 2,
  "total_matching": 8,
  "returned": 8,
  "truncated": false,
  "offset": 0,
  "n_significant": 1,
  "by_experiment": [
    {
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "n_tests": 8,
      "n_significant": 1,
      "n_clusters": 4
    }
  ],
  "by_direction": [
    {"direction": "down", "n_tests": 4, "n_significant": 1},
    {"direction": "up", "n_tests": 4, "n_significant": 0}
  ],
  "by_omics_type": [{"omics_type": "RNASEQ", "n_tests": 8, "n_significant": 1}],
  "cluster_summary": {
    "n_clusters": 4,
    "n_tests_min": 2,
    "n_tests_median": 2.0,
    "n_tests_max": 2,
    "n_significant_min": 0,
    "n_significant_median": 0.0,
    "n_significant_max": 1,
    "universe_size_min": 1849,
    "universe_size_median": 1849.0,
    "universe_size_max": 1849
  },
  "top_clusters_by_min_padj": [
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|down",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "timepoint": "day 14",
      "timepoint_hours": 336.0,
      "timepoint_order": 1,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "n_tests": 2,
      "n_significant": 1,
      "universe_size": 1849,
      "min_padj": 0.00013664450124670934
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|days 60+89|down",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "timepoint": "days 60+89",
      "timepoint_hours": null,
      "timepoint_order": 2,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "n_tests": 2,
      "n_significant": 0,
      "universe_size": 1849,
      "min_padj": 0.2544437633191516
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|up",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "timepoint": "day 14",
      "timepoint_hours": 336.0,
      "timepoint_order": 1,
      "direction": "up",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "n_tests": 2,
      "n_significant": 0,
      "universe_size": 1849,
      "min_padj": 0.3339623274028087
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|days 60+89|up",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "timepoint": "days 60+89",
      "timepoint_hours": null,
      "timepoint_order": 2,
      "direction": "up",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "n_tests": 2,
      "n_significant": 0,
      "universe_size": 1849,
      "min_padj": 1.0
    }
  ],
  "top_pathways_by_padj": [
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|down",
      "term_id": "tcdb:5.B.4",
      "term_name": "The Plant Photosystem I Supercomplex (PSI) Family",
      "p_adjust": 0.00013664450124670934,
      "signed_score": -3.8644078401971567
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|days 60+89|down",
      "term_id": "tcdb:5.B.4",
      "term_name": "The Plant Photosystem I Supercomplex (PSI) Family",
      "p_adjust": 0.2544437633191516,
      "signed_score": -0.5944081896689429
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|up",
      "term_id": "tcdb:3.A.1",
      "term_name": "The ATP-binding Cassette (ABC) Superfamily",
      "p_adjust": 0.3339623274028087,
      "signed_score": 0.4763025209843794
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|days 60+89|down",
      "term_id": "tcdb:3.A.1",
      "term_name": "The ATP-binding Cassette (ABC) Superfamily",
      "p_adjust": 0.9715890019141348,
      "signed_score": -0.012517409917788484
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|down",
      "term_id": "tcdb:3.A.1",
      "term_name": "The ATP-binding Cassette (ABC) Superfamily",
      "p_adjust": 0.9984403185332892,
      "signed_score": -0.0006778898381549934
    },
    ...
  ],
  "not_found": [],
  "not_matched": [],
  "no_expression": [],
  "term_validation": {"not_found": [], "wrong_ontology": [], "wrong_level": [], "filtered_out": []},
  "clusters_skipped": [],
  "enrichment_params": {
    "organism": "MED4",
    "ontology": "tcdb",
    "level": 2,
    "term_ids": null,
    "tree": null,
    "informative_only": true,
    "min_gene_set_size": 5,
    "max_gene_set_size": 500,
    "pvalue_cutoff": 0.05,
    "background_mode": "table_scope",
    "experiment_ids": ["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"],
    "direction": "both",
    "significant_only": true,
    "timepoint_filter": null,
    "growth_phases": null,
    "n_clusters_input": 4,
    "n_clusters_tested": 4,
    "n_clusters_skipped": 0,
    "term2gene_row_count": 98,
    "n_unique_terms": 35,
    "multitest_method": "fdr_bh",
    "filters_applied": {"evidence": ["homology"], "min_evidence_score": 0.6},
    "trust_axes": {"tcdb": ["sources", "evidence", "evidence_score", "tier"]},
    "background_filtered": true,
    "interpro_type": null
  },
  "filters_applied": {"evidence": ["homology"], "min_evidence_score": 0.6},
  "trust_axes": {"tcdb": ["sources", "evidence", "evidence_score", "tier"]},
  "background_filtered": true,
  "interpro_type": null,
  "results": [
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|down",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "timepoint": "day 14",
      "timepoint_hours": 336.0,
      "timepoint_order": 1,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "growth_phase": "nutrient_limited",
      "term_id": "tcdb:5.B.4",
      "term_name": "The Plant Photosystem I Supercomplex (PSI) Family",
      "level": 2,
      "is_informative": true,
      "gene_ratio": "7/472",
      "gene_ratio_numeric": 0.014830508474576272,
      "bg_ratio": "7/1849",
      "bg_ratio_numeric": 0.0037858301784748512,
      "rich_factor": 1.0,
      "fold_enrichment": 3.9173728813559325,
      "pvalue": 6.832225062335467e-05,
      "p_adjust": 0.00013664450124670934,
      "count": 7,
      "bg_count": 7,
      "signed_score": -3.8644078401971567
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|days 60+89|down",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "timepoint": "days 60+89",
      "timepoint_hours": null,
      "timepoint_order": 2,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "growth_phase": "nutrient_limited",
      "term_id": "tcdb:5.B.4",
      "term_name": "The Plant Photosystem I Supercomplex (PSI) Family",
      "level": 2,
      "is_informative": true,
      "gene_ratio": "2/168",
      "gene_ratio_numeric": 0.011904761904761904,
      "bg_ratio": "7/1849",
      "bg_ratio_numeric": 0.0037858301784748512,
      "rich_factor": 0.2857142857142857,
      "fold_enrichment": 3.1445578231292517,
      "pvalue": 0.1272218816595758,
      "p_adjust": 0.2544437633191516,
      "count": 2,
      "bg_count": 7,
      "signed_score": -0.5944081896689429
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|up",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "timepoint": "day 14",
      "timepoint_hours": 336.0,
      "timepoint_order": 1,
      "direction": "up",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "growth_phase": "nutrient_limited",
      "term_id": "tcdb:3.A.1",
      "term_name": "The ATP-binding Cassette (ABC) Superfamily",
      "level": 2,
      "is_informative": true,
      "gene_ratio": "11/405",
      "gene_ratio_numeric": 0.027160493827160494,
      "bg_ratio": "37/1849",
      "bg_ratio_numeric": 0.020010816657652784,
      "rich_factor": 0.2972972972972973,
      "fold_enrichment": 1.3572906239572908,
      "pvalue": 0.16698116370140434,
      "p_adjust": 0.3339623274028087,
      "count": 11,
      "bg_count": 37,
      "signed_score": 0.4763025209843794
    },
    ...
  ]
}
```

### Example 11: Read enrichment_params — what was actually tested

```example-call
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="cyanorak_role", level=1, summary=True)
```

*`enrichment_params` echoes every input plus the derived sizes: `term2gene_row_count` / `n_unique_terms` (the TERM2GENE actually fed to Fisher, after `informative_only` and the size filter), `n_clusters_input` / `n_clusters_tested` / `n_clusters_skipped` (with `clusters_skipped[]` naming the reason, e.g. `no_pathways_in_size_range`), `background_mode`, `filters_applied`, `trust_axes`. Diff this block between two runs before comparing p-values.*

```example-response
{
  "organism_name": "Prochlorococcus MED4",
  "ontology": "cyanorak_role",
  "level": 1,
  "total_matching": 268,
  "returned": 0,
  "truncated": true,
  "offset": 0,
  "n_significant": 10,
  "by_experiment": [
    {
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "n_tests": 268,
      "n_significant": 10,
      "n_clusters": 4
    }
  ],
  "by_direction": [
    {"direction": "down", "n_tests": 134, "n_significant": 8},
    {"direction": "up", "n_tests": 134, "n_significant": 2}
  ],
  "by_omics_type": [{"omics_type": "RNASEQ", "n_tests": 268, "n_significant": 10}],
  "cluster_summary": {
    "n_clusters": 4,
    "n_tests_min": 67,
    "n_tests_median": 67.0,
    "n_tests_max": 67,
    "n_significant_min": 0,
    "n_significant_median": 1.5,
    "n_significant_max": 7,
    "universe_size_min": 1849,
    "universe_size_median": 1849.0,
    "universe_size_max": 1849
  },
  "top_clusters_by_min_padj": [
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|down",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "timepoint": "day 14",
      "timepoint_hours": 336.0,
      "timepoint_order": 1,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "n_tests": 67,
      "n_significant": 7,
      "universe_size": 1849,
      "min_padj": 5.3663275155925714e-12
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|up",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "timepoint": "day 14",
      "timepoint_hours": 336.0,
      "timepoint_order": 1,
      "direction": "up",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "n_tests": 67,
      "n_significant": 2,
      "universe_size": 1849,
      "min_padj": 0.01470841266606779
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|days 60+89|down",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "timepoint": "days 60+89",
      "timepoint_hours": null,
      "timepoint_order": 2,
      "direction": "down",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "n_tests": 67,
      "n_significant": 1,
      "universe_size": 1849,
      "min_padj": 0.026878834137359475
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|days 60+89|up",
      "experiment_id": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic",
      "name": "MED4 PRO99-lowN nutrient starvation vs PRO99-lowN exponential growth (RNASEQ)",
      "timepoint": "days 60+89",
      "timepoint_hours": null,
      "timepoint_order": 2,
      "direction": "up",
      "omics_type": "RNASEQ",
      "table_scope": "all_detected_genes",
      "treatment_type": ["nitrogen"],
      "background_factors": ["axenic", "light"],
      "is_time_course": true,
      "n_tests": 67,
      "n_significant": 0,
      "universe_size": 1849,
      "min_padj": 1.0
    }
  ],
  "top_pathways_by_padj": [
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|down",
      "term_id": "cyanorak.role:K.2",
      "term_name": "Protein synthesis > Ribosomal proteins: synthesis and modification",
      "p_adjust": 5.3663275155925714e-12,
      "signed_score": -11.270322825165014
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|down",
      "term_id": "cyanorak.role:J.1",
      "term_name": "Photosynthesis and respiration > ATP synthase",
      "p_adjust": 2.9595955733190235e-05,
      "signed_score": -4.528767630926161
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|down",
      "term_id": "cyanorak.role:J.7",
      "term_name": "Photosynthesis and respiration > Photosystem I",
      "p_adjust": 2.9595955733190235e-05,
      "signed_score": -4.528767630926161
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|down",
      "term_id": "cyanorak.role:J.8",
      "term_name": "Photosynthesis and respiration > Photosystem II",
      "p_adjust": 0.00019818076445685364,
      "signed_score": -3.702938500686508
    },
    {
      "cluster": "10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic|day 14|down",
      "term_id": "cyanorak.role:J.2",
      "term_name": "Photosynthesis and respiration > CO2 fixation",
      "p_adjust": 0.0057441260269212304,
      "signed_score": -2.2407760401800956
    },
    ...
  ],
  "not_found": [],
  "not_matched": [],
  "no_expression": [],
  "term_validation": {"not_found": [], "wrong_ontology": [], "wrong_level": [], "filtered_out": []},
  "clusters_skipped": [],
  "enrichment_params": {
    "organism": "MED4",
    "ontology": "cyanorak_role",
    "level": 1,
    "term_ids": null,
    "tree": null,
    "informative_only": true,
    "min_gene_set_size": 5,
    "max_gene_set_size": 500,
    "pvalue_cutoff": 0.05,
    "background_mode": "table_scope",
    "experiment_ids": ["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"],
    "direction": "both",
    "significant_only": true,
    "timepoint_filter": null,
    "growth_phases": null,
    "n_clusters_input": 4,
    "n_clusters_tested": 4,
    "n_clusters_skipped": 0,
    "term2gene_row_count": 1487,
    "n_unique_terms": 106,
    "multitest_method": "fdr_bh",
    "filters_applied": {},
    "trust_axes": {"cyanorak_role": ["sources", "evidence"]},
    "background_filtered": false,
    "interpro_type": null
  },
  "filters_applied": {},
  "trust_axes": {"cyanorak_role": ["sources", "evidence"]},
  "background_filtered": false,
  "interpro_type": null,
  "results": []
}
```

## Chaining patterns

```
DE-anchored ORA: pathway_enrichment tests DE gene sets per experiment × timepoint × direction; the sibling cluster_enrichment runs the same Fisher + BH test over a clustering analysis's cluster membership (no direction). Same row/envelope shape.
ontology_landscape → genes_by_ontology(level=N) → pathway_enrichment
pathway_enrichment → gene_overview
differential_expression_by_gene → pathway_enrichment
pathway_enrichment(ontology='kegg', ...) → list_metabolites(pathway_ids=[<enriched_pathway_id>]) — inspect the chemistry of an enriched KEGG pathway (compound-anchored membership, distinct from the gene-KO membership the enrichment used). See docs://analysis/metabolites for the pathway-anchor disambiguation.
See `docs://analysis/enrichment` for the full methodology and the `informative_only` filter semantics.
ontology_landscape(ontology='interpro') → pathway_enrichment(ontology='interpro', interpro_type=..., level=...) — pick the InterPro type before enrichment; the param is required.
See `docs://analysis/annotation_evidence` for the trust-axis registry (which filters apply to which ontology) and rank-vs-filter guidance for evidence_score.
```

## Common mistakes

- pathway_enrichment is DE-anchored (needs `experiment_ids`); for a clustering analysis use `cluster_enrichment(analysis_id=...)`, for ortholog groups / custom lists use the Python `fisher_ora` primitive.

- [ENR] `informative_only=True` default flipped in the 2026-05 KG release. BH-adjusted p-values depend on the term set tested per cluster — locked baselines need `informative_only=False` + post-filter on `is_informative`. See docs://guide/conventions.

- `informative_only=True` shrinks the TERM2GENE mapping, and `enrichment_params.term2gene_row_count` shows by how much — MED4 KEGG at `level=3`: 1124 rows with `informative_only=False`, 1094 with the default. Compare `enrichment_params` across runs before comparing p-values. For KEGG the flag also covers the global / overview maps (`kegg.pathway:ko01100` and kin), so a `level=2` run drops those rows too.

- Default background is `table_scope` (per-experiment quantified set). `'organism'` inflates the denominator and underestimates enrichment. See `docs://analysis/enrichment` for the full methodology note.

- BH correction is per-cluster (experiment × timepoint × direction), NOT across clusters. Cross-experiment FDR is biological replication, not statistical.

- Single-organism enforced. Run separate calls per organism.

- Timepoints aren't comparable across experiments — `T0` in exp1 ≠ `T0` in exp2. That's why there's no `by_timepoint` breakdown.

- For cluster-membership / ortholog-group / custom-list enrichment, use the Python `fisher_ora` primitive (see `docs://analysis/enrichment`). The MCP tool is the DE-wired convenience only. Idiom: `term2gene = to_dataframe(genes_by_ontology(...))` then `fisher_ora(gene_sets, background, term2gene)` — no manual column munging.

- At least one of `level` or `term_ids` must be provided (matches `genes_by_ontology`).

- `min/max_gene_set_size` here means **M** — pathway size within each cluster's background (clusterProfiler semantics). This differs from `ontology_landscape`'s filter, which is organism-scoped. A pathway may be tested in one cluster and dropped in another when `background='table_scope'`.

- For brite enrichment, use `tree` to scope to a single BRITE tree (e.g. `tree='transporters'`). Without `tree`, all-BRITE enrichment is dominated by the `enzymes` tree (by far the largest). Pick a specific level: `level=1` (BRITE category) or `level=2` (BRITE sub-category) are the most useful. Use `list_filter_values('brite_tree')` to discover trees → `ontology_landscape(ontology='brite', tree=...)` to pick level → `pathway_enrichment(ontology='brite', tree=..., level=...)` for enrichment.

```mistake
pathway_enrichment(..., background='genome')  # not a valid string
```

```correction
pathway_enrichment(..., background='organism')  # or 'table_scope' (default), or a locus_tag list
```

```mistake
pathway_enrichment(..., ontology='interpro', level=0)  # missing interpro_type — raises
```

```correction
pathway_enrichment(..., ontology='interpro', interpro_type='HOMOLOGOUS_SUPERFAMILY', level=0)
```

- growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — NOT a gene-specific property

- For DAG ontologies (`go_*`), `level=N`-only enrichment silently drops biologically-meaningful terms at heterogeneous depths. For narrow research questions, hand-curate a `term_ids` panel via `search_ontology(ontology='go_bp', search_text=...)` and pass it directly. Use `level` only when surveying a whole branch.

- `ontology='interpro'` requires `interpro_type` — one of `FAMILY`, `DOMAIN`, `HOMOLOGOUS_SUPERFAMILY`, `REPEAT`, `CONSERVED_SITE`, `ACTIVE_SITE`, `BINDING_SITE`, `PTM`. Omitting it raises. Check sizing per type via `ontology_landscape(organism=..., ontology='interpro')` first.

- Trust filters (`sources`, `evidence`, `max_tier`, `min_evidence_score`, `call_class`) shape the TERM2GENE mapping fed to Fisher, not the row output — they change which (gene × term) pairs are tested, applied identically to foreground and background. Defaults are `None` and never filter. `min_evidence_score` is the only numeric cutoff; there is no filter on native scalars (`evalue`, `bit_score`, `confidence_score`, ...). See `docs://analysis/annotation_evidence`.

- MEROPS `call_class=['peptidase']` excludes `nonpeptidase_homolog` rows (catalytically-dead homologs) from both the tested gene set and the pathway definitions — run it whenever the enrichment question is about peptidase activity, not sequence homology to a peptidase family.

- When a KEGG pathway is significantly enriched, drill into its chemistry via `list_metabolites(pathway_ids=[<term_id>])`. This answers 'what compounds does the enriched pathway involve?' — a different anchor than the gene-KO membership the enrichment is built on. The same KEGG pathway map (e.g. `kegg.pathway:ko00910` Nitrogen metabolism) reaches the same map from compound-membership vs gene-KO-membership; a gene whose KO is in pathway X may not catalyse any reaction whose metabolites are in pathway X (and vice versa). See docs://analysis/metabolites.

- Unknown `experiment_ids` and an out-of-range `level` raise `ValueError` instead of returning a vacuous empty envelope. A partial batch (some ids unknown) keeps running — the unknown ones land in `not_found_experiments`; the call only raises when EVERY requested `experiment_id` is unknown. Flat ontologies (e.g. `cog_category`) only accept `level=0`; the raise message says so.

## Package import equivalent

```python
from multiomics_explorer import pathway_enrichment

result = pathway_enrichment(organism=..., experiment_ids=..., ontology=...)
# returns EnrichmentResult; access result.results
# and accessors. Call result.to_envelope() for the
# MCP-equivalent dict shape.
# See docs://examples/pathway_enrichment.py for runnable code.
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
