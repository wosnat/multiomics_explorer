# pathway_enrichment

## What it does

Over-representation analysis (Fisher + BH) over DE gene sets in ONE organism — one test per experiment × timepoint × direction × term.

Use when the gene sets come from DE, after an `ontology_landscape` pre-flight; a clustering analysis is `cluster_enrichment`, a custom list Python `fisher_ora`.
Filters: experiment_ids, organism, ontology, level / term_ids, tree, direction, background, gene-set size, trust filters.
Returns: n_significant, by_experiment, by_direction, cluster_summary, top_pathways_by_padj; one row = one (cluster, term) test.
docs://tools/pathway_enrichment; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| experiment_ids | list[string] | — | Experiments to pull DE from. Get IDs from list_experiments. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') | — | Ontology for pathway definitions. Run ontology_landscape first to rank by relevance. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). REQUIRED when ontology='brite' (12 trees; see list_filter_values(filter_type='brite_tree')) — a tree-less BRITE run raises, since it would mix taxonomy and function terms. Invalid for any other ontology. See docs://guide/conventions for the BRITE-tree scoping rule. |
| level | int \| None | None | Hierarchy level (0 = root). At least one of `level` or `term_ids` required. See docs://guide/conventions. |
| term_ids | list[string] \| None | None | Specific term IDs to test. Combines with level to scope rollup. Bare ids are accepted (e.g. 'ko00910', 'GO:0006979') and coerced to canonical (see `term_validation.resolved_aliases`). |
| direction | string ('up', 'down', 'both') | both | DE direction(s) to include in gene_sets. |
| significant_only | bool | True | If true, only significant DE rows count as foreground. |
| background | string \| list[string] | table_scope | 'table_scope' (default, per-cluster quantified set), 'organism' (full genome — inflates denominator), or explicit locus_tag list. See docs://analysis/enrichment for the full background semantics. |
| min_gene_set_size | int | 5 | Per-cluster M filter: drop pathways with fewer members in the background. |
| max_gene_set_size | int \| None | 500 | Per-cluster M filter upper bound. None disables. |
| pvalue_cutoff | float | 0.05 | Significance threshold for `p_adjust`. |
| include_nonsignificant | bool | False | Include rows with `p_adjust >= pvalue_cutoff`. Default False — only significant rows are returned, and `total_matching` counts just that pageable subset (== `n_significant`); pass True to page through every tested row, in which case `total_matching` covers all of them. `n_significant` itself is unaffected either way. |
| timepoint_filter | list[string] \| None | None | Restrict to these timepoint labels. Useful for 10+ timepoint experiments. |
| growth_phases | list[string] \| None | None | Keep timepoints whose growth_phase is in this list. Values: list_filter_values('growth_phase'). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| limit | int | 25 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |
| informative_only | bool | True | True drops terms the KG flags uninformative (roots, catch-alls). |
| sources | list[string] \| None | None | Keep rows whose edge sources[] contains any of these values. Valid on the 14 functional-edge ontologies (not PSORTb/SignalP). See list_filter_values('sources'). |
| evidence | list[string] \| None | None | Keep rows whose compact evidence-ladder value is in this list. Valid on the 14 functional-edge ontologies. See docs://analysis/annotation_evidence. |
| max_tier | int \| None | None | Keep rows with edge tier <= this value OR tier IS NULL (diamond truncation depth, 1-3; null tier always kept). Valid on tcdb, merops only. |
| min_evidence_score | float \| None | None | Keep rows with edge evidence_score >= this cutoff (0-1; the only native-scalar cutoff allowed). Valid on go_bp/mf/cc, ec, pfam, cazy, tcdb, merops. |
| call_class | list[string ('peptidase', 'inhibitor', 'nonpeptidase_homolog')] \| None | None | MEROPS peptidase-call filter: keep rows whose call_class is in this list. Merops only; unfiltered mixes in catalytically-dead nonpeptidase_homolog rows. |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type (e.g. 'DOMAIN', 'FAMILY'). InterPro only; required on interpro enrichment/landscape strata - ranking across mixed entry types is not meaningful. |

**Discovery:** use `list_organisms` for valid organism names.

## Example

### Single experiment, default direction=both

```python
pathway_enrichment(organism="MED4", experiment_ids=["10.1101/2025.11.24.690089_growth_state_pro99lown_nutrient_starvation_med4_rnaseq_axenic"], ontology="cyanorak_role", level=1)
```

## Response sketch

```expected-keys
organism_name, ontology, level, total_matching, returned, truncated, offset, n_significant, by_experiment, by_direction, by_omics_type, cluster_summary, top_clusters_by_min_padj, top_pathways_by_padj, not_found, not_matched, warnings, no_expression, not_found_experiments, term_validation, clusters_skipped, enrichment_params, filters_applied, trust_axes, background_filtered, interpro_type, results
```

Result row: `cluster, experiment_id, name, timepoint, timepoint_hours, timepoint_order, direction, omics_type, table_scope, treatment_type, background_factors, is_time_course, …`

## Common mistakes

- pathway_enrichment is DE-anchored (needs `experiment_ids`); for a clustering analysis use `cluster_enrichment(analysis_id=...)`, for ortholog groups / custom lists use the Python `fisher_ora` primitive.

## Chaining patterns

- DE-anchored ORA: pathway_enrichment tests DE gene sets per experiment × timepoint × direction; the sibling cluster_enrichment runs the same Fisher + BH test over a clustering analysis's cluster membership (no direction). Same row/envelope shape.
- ontology_landscape → genes_by_ontology(level=N) → pathway_enrichment
- pathway_enrichment → gene_overview
- differential_expression_by_gene → pathway_enrichment
- pathway_enrichment(ontology='kegg', ...) → list_metabolites(pathway_ids=[<enriched_pathway_id>]) — inspect the chemistry of an enriched KEGG pathway (compound-anchored membership, distinct from the gene-KO membership the enrichment used). See docs://analysis/metabolites for the pathway-anchor disambiguation.
- See `docs://analysis/enrichment` for the full methodology and the `informative_only` filter semantics.
- ontology_landscape(ontology='interpro') → pathway_enrichment(ontology='interpro', interpro_type=..., level=...) — pick the InterPro type before enrichment; the param is required.
- See `docs://analysis/annotation_evidence` for the trust-axis registry (which filters apply to which ontology) and rank-vs-filter guidance for evidence_score.

Full reference (all examples, full response format, verbose fields): `docs://tools/pathway_enrichment/full`
