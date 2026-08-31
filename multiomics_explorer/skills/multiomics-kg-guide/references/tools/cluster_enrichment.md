# cluster_enrichment

## What it does

Over-representation analysis (Fisher + BH) over one clustering analysis in ONE organism — one test per cluster × term.

Use when the gene sets are published clusters, after an `ontology_landscape` pre-flight; DE gene sets are `pathway_enrichment`, a custom list Python `fisher_ora`.
Filters: analysis_id, organism, ontology, level / term_ids, tree, background, gene-set size, cluster size, trust filters.
Returns: n_significant, by_cluster, by_term, clusters_tested, clusters_skipped, term_validation; one row = one (cluster, term) test.
docs://tools/cluster_enrichment; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| analysis_id | string | — | Clustering analysis ID. Get from list_clustering_analyses. |
| organism | string | — | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') | — | Ontology for pathway definitions. Run ontology_landscape first. |
| tree | string \| None | None | BRITE tree name filter. REQUIRED when ontology='brite' (12 trees; see list_filter_values(filter_type='brite_tree')) — a tree-less BRITE run raises, since it would mix taxonomy and function terms. Invalid for any other ontology. See docs://guide/conventions for the BRITE-tree scoping rule. |
| level | int \| None | None | Hierarchy level (0 = root). At least one of `level` or `term_ids` required. See docs://guide/conventions. |
| term_ids | list[string] \| None | None | Specific term IDs to test. Bare ids are accepted (e.g. 'ko00910', 'GO:0006979') and coerced to canonical (see `term_validation.resolved_aliases`). |
| background | string \| list[string] | cluster_union | 'cluster_union' (default — union of all clustered genes; differs from `pathway_enrichment`'s 'table_scope' default), 'organism', or explicit locus_tag list. See docs://analysis/enrichment for the full background semantics. |
| min_gene_set_size | int | 5 | Per-cluster M filter: drop pathways with fewer members. |
| max_gene_set_size | int \| None | 500 | Per-cluster M filter upper bound. None disables. |
| min_cluster_size | int | 3 | Skip clusters with fewer members than this. |
| max_cluster_size | int \| None | None | Skip clusters with more members. None disables. |
| pvalue_cutoff | float | 0.05 | Significance threshold for p_adjust. |
| include_nonsignificant | bool | False | Include rows with `p_adjust >= pvalue_cutoff`. Default False — only significant rows are returned, and `total_matching` counts just that pageable subset (== `n_significant`); pass True to page through every tested row, in which case `total_matching` covers all of them. `n_significant` itself is unaffected either way. |
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

### Single analysis, CyanoRak level 1

```python
cluster_enrichment(analysis_id="clustering_analysis:journal.pone.0005135:med4_diel_clusters", organism="MED4", ontology="cyanorak_role", level=1)
```

## Response sketch

```expected-keys
analysis_id, analysis_name, organism_name, cluster_method, cluster_type, omics_type, treatment_type, background_factors, growth_phases, experiment_ids, ontology, level, tree, total_matching, returned, truncated, offset, n_significant, by_cluster, by_term, clusters_tested, not_found, not_matched, warnings, clusters_skipped, term_validation, enrichment_params, filters_applied, trust_axes, background_filtered, interpro_type, results
```

Result row: `cluster, cluster_id, term_id, term_name, level, is_informative, tree, tree_code, gene_ratio, gene_ratio_numeric, bg_ratio, bg_ratio_numeric, …`

## Common mistakes

- cluster_enrichment is cluster-anchored (needs `analysis_id`); for DE gene sets use `pathway_enrichment(experiment_ids=...)`. `enrichment_params` (incl. `term2gene_row_count`) echoes what was tested, same as pathway_enrichment.

- No rows ≠ nothing tested: read `n_significant`, always the full tested-set count. [ENR] Default `limit=25` + `include_nonsignificant=False` return only significant rows (`p_adjust < pvalue_cutoff`); `total_matching` then counts just that pageable subset (== `n_significant`), so an empty `results` page always means `total_matching=0`. Pass `include_nonsignificant=True` to page through every tested row — `total_matching` then covers all of them; `n_significant` is unaffected either way.

- [ENR] `informative_only=True` default flipped in the 2026-05 KG release. BH-adjusted p-values depend on the term set tested per cluster — locked baselines need `informative_only=False` + post-filter on `is_informative`. See docs://guide/conventions.

## Chaining patterns

- Cluster-anchored ORA: cluster_enrichment tests each cluster of one clustering analysis; the sibling pathway_enrichment runs the same Fisher + BH test over DE gene sets (experiment × timepoint × direction). Same row/envelope shape.
- list_clustering_analyses → cluster_enrichment
- ontology_landscape → cluster_enrichment
- cluster_enrichment → gene_overview
- cluster_enrichment → genes_in_cluster
- cluster_enrichment(ontology='kegg', ...) → list_metabolites(pathway_ids=[<enriched_pathway_id>]) — inspect the chemistry of an enriched KEGG pathway (compound-anchored membership, distinct from the gene-KO membership the enrichment used). See docs://analysis/metabolites for the pathway-anchor disambiguation.
- See `docs://analysis/enrichment` for the full methodology and the `informative_only` filter semantics.
- See `docs://analysis/annotation_evidence` for the trust-axis registry and rank-vs-filter guidance for evidence_score.

Full reference (all examples, full response format, verbose fields): `docs://tools/cluster_enrichment/full`
