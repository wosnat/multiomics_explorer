# cluster_enrichment

## What it does

Run cluster-membership over-representation analysis (Fisher + BH) — one ORA per cluster in a clustering analysis.

Single-organism enforced. Background defaults to `cluster_union` (union
of all clustered genes — differs from `pathway_enrichment`'s
`table_scope` default); `organism` or an explicit locus_tag list are
also accepted. Background drives the Fisher denominator and matters
more than the ontology choice.

[TRUST] `sources` / `evidence` / `max_tier` / `min_evidence_score` /
`call_class` filter TERM2GENE at the same match stage as the
background, so tested sets and background move together;
`interpro_type` is required when `ontology='interpro'`. See
docs://analysis/annotation_evidence.

Routing: pre-flight via `list_clustering_analyses` for `analysis_id`
and `ontology_landscape` for `(ontology, level)`; drill enriched terms
via `gene_overview`, `genes_in_cluster`, or for KEGG
`list_metabolites(pathway_ids=...)` for compound-anchored membership.
See docs://analysis/enrichment for Fisher + BH methodology and
background semantics; docs://examples/pathway_enrichment.py for
runnable code (custom term2gene path covers cluster-membership ORA).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| analysis_id | string | — | Clustering analysis ID. Get from list_clustering_analyses. |
| organism | string | — | Organism: word-based, case-insensitive match on preferred_name + name_synonyms ('MED4' works; ambiguous match raises). Single-organism enforced. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') | — | Ontology for pathway definitions. Run ontology_landscape first. |
| tree | string \| None | None | BRITE tree name filter. Only valid when ontology='brite'. See docs://guide/conventions for the BRITE-tree scoping rule. |
| level | int \| None | None | Hierarchy level (0 = root). At least one of `level` or `term_ids` required. See docs://guide/conventions. |
| term_ids | list[string] \| None | None | Specific term IDs to test. |
| background | string \| list[string] | cluster_union | 'cluster_union' (default — union of all clustered genes; differs from `pathway_enrichment`'s 'table_scope' default), 'organism', or explicit locus_tag list. See docs://analysis/enrichment for the full background semantics. |
| min_gene_set_size | int | 5 | Per-cluster M filter: drop pathways with fewer members. |
| max_gene_set_size | int \| None | 500 | Per-cluster M filter upper bound. None disables. |
| min_cluster_size | int | 3 | Skip clusters with fewer members than this. |
| max_cluster_size | int \| None | None | Skip clusters with more members. None disables. |
| pvalue_cutoff | float | 0.05 | Significance threshold for p_adjust. |
| summary | bool | False | If true, omit results (envelope only). |
| limit | int | 5 | Max rows returned. |
| offset | int | 0 | Skip N rows before limit. |
| informative_only | bool | True | When True (default), exclude ontology terms flagged uninformative in the KG (e.g. KEGG KO 'uncharacterized protein' terms, GO root go:0008150; global KEGG maps like ko01100 are not flagged yet). Term-side filter — never restricts the gene set, background, or DE inputs. Pass False to include uninformative terms; per-row is_informative still surfaces in either mode. [ENR] Default flipped to True in 2026-05 KG release; see docs://guide/conventions. |
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
analysis_id, analysis_name, organism_name, cluster_method, cluster_type, omics_type, treatment_type, background_factors, growth_phases, experiment_ids, ontology, level, tree, total_matching, returned, truncated, offset, n_significant, by_cluster, by_term, clusters_tested, not_found, not_matched, clusters_skipped, term_validation, enrichment_params, filters_applied, trust_axes, background_filtered, interpro_type, results
```

- **analysis_id** (string | None): Clustering analysis ID
- **analysis_name** (string | None): Clustering analysis name
- **organism_name** (string): Single organism
- **cluster_method** (string | None): Clustering method
- **cluster_type** (string | None): Cluster type
- **omics_type** (string | None): Omics type
- **treatment_type** (list[string]): Treatment types
- **background_factors** (list[string]): Background factors
- **growth_phases** (list[string]): Growth phases
- **experiment_ids** (list[string]): Linked experiment IDs
- **ontology** (string): Ontology used
- **level** (int | None): Hierarchy level
- **tree** (string | None): BRITE tree (if applicable)
- **total_matching** (int): Total Fisher tests run
- **returned** (int): Rows in this response
- **truncated** (bool): True when total_matching exceeds offset+returned
- **offset** (int): Pagination offset
- **n_significant** (int): Rows with p_adjust below cutoff
- **by_cluster** (list[ClusterEnrichmentByCluster]): Per-cluster significance counts
- **by_term** (list[ClusterEnrichmentByTerm]): Top terms by number of clusters
- **clusters_tested** (int): Clusters passing size filter
- **not_found** (list[string]): Analysis IDs absent from KG
- **not_matched** (list[string]): Analysis IDs wrong organism
- **clusters_skipped** (list[ClusterEnrichmentClusterSkipped]): Clusters filtered out or producing no rows
- **term_validation** (PathwayEnrichmentTermValidation): Namespaced passthrough of term_id validation from genes_by_ontology
- **enrichment_params** (object | None): ORA parameters used for this call. See docs://analysis/enrichment.
- **filters_applied** (object): Echo of the trust filters actually set on this call. See docs://analysis/annotation_evidence.
- **trust_axes** (object): Trust axes the chosen ontology carries, e.g. {'tcdb': ['sources','evidence','evidence_score','tier']}.
- **background_filtered** (bool): True when a trust filter narrowed the background.
- **interpro_type** (string | None): Echo of the interpro_type stratum used (sparse: only when ontology='interpro').

### Per-result fields

| Field | Type | Description |
|---|---|---|
| cluster | string | Cluster name from the clustering analysis |
| cluster_id | string | Cluster ID from KG |
| term_id | string | Ontology term ID |
| term_name | string | Ontology term display name |
| level | int \| None (optional) | Hierarchy depth (0 = root) |
| is_informative | bool | True if the term is not flagged is_uninformative in the KG. Always present, regardless of informative_only setting, so callers can post-filter or diagnose. With default informative_only=True, all rows have is_informative=True by construction; pass informative_only=False to opt out and see uninformative terms. |
| tree | string \| None (optional) | BRITE tree name (sparse: BRITE only) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: BRITE only) |
| gene_ratio | string | 'k/n' string — cluster genes in pathway over total cluster genes (clusterProfiler: GeneRatio) |
| gene_ratio_numeric | float | k/n as float |
| bg_ratio | string | 'M/N' string — pathway members over background size (clusterProfiler: BgRatio) |
| bg_ratio_numeric | float | M/N as float |
| rich_factor | float | k/M — fraction of pathway's background members in cluster (clusterProfiler: RichFactor) |
| fold_enrichment | float | (k/n) / (M/N) — observed over null (clusterProfiler: FoldEnrichment) |
| pvalue | float | Fisher-exact p-value (one-sided enrichment) |
| p_adjust | float | Benjamini-Hochberg FDR within cluster (clusterProfiler: p.adjust) |
| count | int | k — cluster genes in pathway (clusterProfiler: Count) |
| bg_count | int | M — pathway members in cluster's background |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| cluster_functional_description | string \| None (optional) | Verbose: functional description of cluster |
| cluster_expression_dynamics | string \| None (optional) | Verbose: expression dynamics of cluster |
| cluster_temporal_pattern | string \| None (optional) | Verbose: temporal pattern of cluster |
| cluster_member_count | int \| None (optional) | Verbose: total genes in this cluster |

### `informative_only` filter

When True (default), exclude ontology terms flagged uninformative
in the KG (e.g. GO root go:0008150, catch-all Cyanorak / TIGR roles,
KEGG KOs named "uncharacterized protein"). Term-side filter — never
restricts the gene set, background, or cluster membership. Pass
False to include uninformative terms; per-row `is_informative` still
surfaces in either mode. KEGG is flagged at the KO level only:
pathway maps — including the global map `kegg.pathway:ko01100` — are
not flagged, so use `max_gene_set_size` to keep global maps out of a
pathway-level test.

See `docs://analysis/enrichment` (section "Informative-only filtering")
for rationale, Fisher denominator behavior, and opt-out guidance.


## Few-shot examples

### Example 1: Single analysis, CyanoRak level 1

```example-call
cluster_enrichment(analysis_id="clustering_analysis:journal.pone.0005135:med4_diel_clusters", organism="MED4", ontology="cyanorak_role", level=1)
```

### Example 2: Summary-only (envelope, no rows)

```example-call
cluster_enrichment(analysis_id="clustering_analysis:journal.pone.0005135:med4_diel_clusters", organism="MED4", ontology="cyanorak_role", level=1, summary=True)
```

### Example 3: BRITE tree-scoped

```example-call
cluster_enrichment(analysis_id="clustering_analysis:journal.pone.0005135:med4_diel_clusters", organism="MED4", ontology="brite", tree="transporters", level=1)
```

### Example 4: Organism background instead of cluster union

```example-call
cluster_enrichment(analysis_id="clustering_analysis:journal.pone.0005135:med4_diel_clusters", organism="MED4", ontology="cyanorak_role", level=1, background="organism")
```

### Example 5: InterPro enrichment requires interpro_type (illustrative — not a live response)

```example-call
cluster_enrichment(analysis_id="clustering_analysis:journal.pone.0005135:med4_diel_clusters", organism="MED4", ontology="interpro", interpro_type="HOMOLOGOUS_SUPERFAMILY", level=0)
```

*Same requirement as pathway_enrichment: ontology='interpro' without interpro_type raises (InterPro types size too differently to pool). Hand-written response — this call currently fails on the MCP surface (non-finite floats in the analysis's cluster description properties; a tool fix is pending).*

```example-response
{"trust_axes": {"interpro": ["sources", "evidence"]}, "interpro_type": "HOMOLOGOUS_SUPERFAMILY", "...": "..."}
```

### Example 6: MEROPS enrichment restricted to peptidase calls (call_class)

```example-call
cluster_enrichment(analysis_id="clustering_analysis:journal.pone.0005135:med4_diel_clusters", organism="MED4", ontology="merops", call_class=["peptidase"], level=0)
```

### Example 7: From landscape to cluster enrichment

```
Step 1: list_clustering_analyses(organism="MED4")
        → pick an analysis_id

Step 2: ontology_landscape(organism="MED4")
        → pick (ontology, level) by relevance_rank

Step 3: cluster_enrichment(analysis_id=<picked>, organism="MED4", ontology=<picked>, level=<picked>)
        → Fisher ORA results per cluster
```

## Chaining patterns

```
Cluster-anchored ORA: cluster_enrichment tests each cluster of one clustering analysis; the sibling pathway_enrichment runs the same Fisher + BH test over DE gene sets (experiment × timepoint × direction). Same row/envelope shape.
list_clustering_analyses → cluster_enrichment
ontology_landscape → cluster_enrichment
cluster_enrichment → gene_overview
cluster_enrichment → genes_in_cluster
cluster_enrichment(ontology='kegg', ...) → list_metabolites(pathway_ids=[<enriched_pathway_id>]) — inspect the chemistry of an enriched KEGG pathway (compound-anchored membership, distinct from the gene-KO membership the enrichment used). See docs://analysis/metabolites for the pathway-anchor disambiguation.
See `docs://analysis/enrichment` for the full methodology and the `informative_only` filter semantics.
See `docs://analysis/annotation_evidence` for the trust-axis registry and rank-vs-filter guidance for evidence_score.
```

## Common mistakes

- cluster_enrichment is cluster-anchored (needs `analysis_id`); for DE gene sets use `pathway_enrichment(experiment_ids=...)`. `enrichment_params` (incl. `term2gene_row_count`) echoes what was tested, same as pathway_enrichment.

- [ENR] `informative_only=True` default flipped in the 2026-05 KG release. BH-adjusted p-values depend on the term set tested per cluster — locked baselines need `informative_only=False` + post-filter on `is_informative`. See docs://guide/conventions.

- Default background is `cluster_union` (union of all clustered genes, including size-filtered). Use `'organism'` only when clustering covers the full genome.

- BH correction is per-cluster, NOT across clusters.

- Single-organism enforced.

- No signed_score — clusters aren't directional. For direction-aware enrichment, use pathway_enrichment with DE experiments.

- At least one of `level` or `term_ids` must be provided.

- `min/max_gene_set_size` is the pathway M filter (per-cluster, clusterProfiler semantics). `min/max_cluster_size` is the cluster membership filter.

- For BRITE, scope to a specific tree with `tree=`. Use `list_filter_values('brite_tree')` to discover trees.

- When a KEGG pathway is significantly enriched in a cluster, drill into its chemistry via `list_metabolites(pathway_ids=[<term_id>])`. The cluster's gene-KO membership and the pathway's compound-membership reach the same KEGG map via different relations — name the anchor when answering. See docs://analysis/metabolites.

- `ontology='interpro'` requires `interpro_type` (one of the 8 InterPro types) — omitting it raises. Trust filters (`sources`, `evidence`, `max_tier`, `min_evidence_score`, `call_class`) shape the per-cluster TERM2GENE mapping identically to `pathway_enrichment`; defaults never filter. See `docs://analysis/annotation_evidence`.

```mistake
cluster_enrichment(..., background='table_scope')  # not valid
```

```correction
cluster_enrichment(..., background='cluster_union')  # or 'organism', or a locus_tag list
```

## Package import equivalent

```python
from multiomics_explorer import cluster_enrichment

result = cluster_enrichment(analysis_id=..., organism=..., ontology=...)
# returns EnrichmentResult; access result.results
# and accessors. Call result.to_envelope() for the
# MCP-equivalent dict shape.
# See docs://examples/pathway_enrichment.py for runnable code.
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
