# gene_overview

## What it does

Batch gene routing: identity (gene_name, product, gene_category) plus per-gene data-availability signals (annotation_types, expression counts, ortholog/cluster summaries, DM rollups, chemistry rollups).

[TRUST] `merops_classes` / `ncbifam_family_count` / `merops_evidence_score_max` are the protease / family-domain routing columns. See docs://analysis/annotation_evidence.

Routing: drill into each axis when the per-gene signal is non-zero — `gene_ontology_terms` (annotation_types non-empty), `gene_homologs` (closest_ortholog_group_size > 0), `gene_clusters_by_gene` (cluster_membership_count > 0), `differential_expression_by_gene` / `gene_response_profile` (expression_edge_count > 0), `gene_derived_metrics` and `genes_by_{numeric,boolean,categorical}_metric` keyed off `derived_metric_value_kinds`, `metabolites_by_gene` / `genes_by_metabolite` (evidence_sources non-empty), `gene_ontology_terms(ontology='merops')` (merops_classes non-empty). Use `gene_details` for the full Gene-node property dump.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845']. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include gene_summary, function_description, all_identifiers. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

## Response format

### Envelope

```expected-keys
total_matching, by_organism, by_category, by_annotation_type, by_annotation_state, has_expression, has_significant_expression, has_orthologs, has_clusters, has_derived_metrics, has_chemistry, has_discussed, top_discussing_publications, has_ncbifam, by_merops_class, returned, offset, truncated, not_found, results
```

- **total_matching** (int): Genes found in KG from input locus_tags.
- **by_organism** (list[OverviewOrganismBreakdown]): Gene counts per organism, sorted desc.
- **by_category** (list[OverviewCategoryBreakdown]): Gene counts per category, sorted desc.
- **by_annotation_type** (list[OverviewAnnotationTypeBreakdown]): Gene counts per annotation type, sorted desc.
- **by_annotation_state** (list[OverviewAnnotationStateBreakdown]): Rollup of annotation_state over result set, sorted desc by count.
- **has_expression** (int): Genes with expression data (expression_edge_count > 0).
- **has_significant_expression** (int): Genes with significant DE observations.
- **has_orthologs** (int): Genes with ortholog group membership.
- **has_clusters** (int): Genes with cluster membership.
- **has_derived_metrics** (int): Count of requested locus_tags carrying any DM annotation.
- **has_chemistry** (int): Count of requested locus_tags with non-empty evidence_sources (participate in at least one reaction-to-metabolite or transport path).
- **has_discussed** (int): Count of requested locus_tags discussed in prose by at least one publication (discussed_in_publication_count > 0).
- **top_discussing_publications** (list[OverviewDiscussingPublication]): Publications ranked by how many of the queried genes they discuss (batch set-coverage — recovers 'which one paper covers most of my gene set'). Feed a doi into discussed_by_publication for that paper's full discussed set.
- **has_ncbifam** (int): Count of requested locus_tags with at least one NCBIfam family annotation (ncbifam_family_count > 0).
- **by_merops_class** (list[OverviewMeropsClassBreakdown]): Rollup of merops_classes over the result set, sorted desc by count.
- **returned** (int): Results in this response (0 when summary=true).
- **offset** (int): Offset into full result set.
- **truncated** (bool): True if total_matching > returned.
- **not_found** (list[string]): Input locus_tags not in KG.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001'). |
| gene_name | string \| None (optional) | Gene name (e.g. 'dnaN'). |
| product | string \| None (optional) | Gene product (e.g. 'DNA polymerase III subunit beta'). |
| gene_category | string \| None (optional) | Functional category (e.g. 'Replication and repair'). |
| annotation_quality | int \| None (optional) | 0..3 numeric encoding of `Gene.annotation_state` (informative-evidence count). 3=informative_multi, 2=informative_single, 1=catch_all_only, 0=no_evidence. [AQ] Definition shifted in 2026-05 KG release; see docs://guide/conventions. |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4'). |
| annotation_types | list[string] (optional) | Ontology source types where this gene has at least one annotation (e.g. ['go_bp', 'ec', 'kegg']). Presence-only — does NOT indicate content informativeness; a 'cog_category' entry may be 'Function unknown'. For term content, call gene_ontology_terms. |
| annotation_state | string | Informativeness state: informative_multi | informative_single | catch_all_only | no_evidence. |
| informative_annotation_types | list[string] (optional) | Subset of annotation_types backed by informative (non-catch-all) terms. |
| expression_edge_count | int (optional) | Number of expression data points. When > 0, drill via differential_expression_by_gene(locus_tags=[...]) or gene_response_profile. |
| significant_up_count | int (optional) | Significant up-regulated DE observations. When > 0, drill via differential_expression_by_gene(direction='up'). |
| significant_down_count | int (optional) | Significant down-regulated DE observations. When > 0, drill via differential_expression_by_gene(direction='down'). |
| closest_ortholog_group_size | int \| None (optional) | Size of tightest ortholog group. Use gene_homologs for full per-group membership and source/level metadata. |
| closest_ortholog_genera | list[string] \| None (optional) | Genera in tightest ortholog group (e.g. ['Prochlorococcus', 'Synechococcus']). Use gene_homologs for full membership; genes_by_homolog_group to expand a specific group. |
| cluster_membership_count | int (optional) | Number of cluster memberships. When > 0, drill via gene_clusters_by_gene for per-cluster details. |
| cluster_types | list[string] (optional) | Distinct cluster types (e.g. ['condition_comparison', 'diel']). Use gene_clusters_by_gene with cluster_type filter to scope drill-down. |
| derived_metric_count | int (optional) | Total DerivedMetric annotations on this gene (sum across numeric/boolean/categorical kinds). |
| derived_metric_value_kinds | list[string] (optional) | Subset of {numeric, boolean, categorical} where this gene has DM annotations. Use to route to genes_by_{kind}_metric drill-downs. |
| reaction_count | int (optional) | Distinct reactions catalysed by this gene (precomputed Gene-side rollup). When > 0, drill via metabolites_by_gene(locus_tags=[locus_tag], organism=...). |
| catalyzed_metabolite_count | int (optional) | Distinct metabolites reachable via catalysis only (Gene_catalyzes_reaction → Reaction_has_metabolite). Transport-only genes read 0 — check transported_metabolite_count / 'transport' in evidence_sources (e.g. PMM0392: 0 here, 13 transported). |
| tcdb_evidence_score_max | float \| None (optional) | Max KG 5-signal composite evidence_score over this gene's TCDB calls, in [0,1]. Rank with it, don't filter: 0 = uncorroborated DIAMOND hit, not absent. None = no TCDB call (never a sentinel). |
| transported_metabolite_count | int (optional) | Distinct metabolites this gene transports via its deepest TCDB attachments (precomputed Gene.transported_metabolite_count). Pairs with catalyzed_metabolite_count. When > 0, drill via metabolites_by_gene(locus_tags=[...]). |
| transport_substrate_resolution | string \| None (optional) | 'resolved' = at least one non-lumping deepest TCDB attachment (not all); 'family_inferred' = transported_metabolite_count is reachability, not capability. None = no TCDB call. Read the score; if resolved, drill into substrates. |
| evidence_sources | list[string] (optional) | Path provenance — values from {'metabolism', 'transport', 'metabolomics'}. When non-empty, drill into metabolites_by_gene(locus_tags=[...]). Per-source definitions: see docs://guide/concepts. |
| merops_classes | list[string] (optional) | Distinct MEROPS call_class values across this gene's MEROPS calls (e.g. ['peptidase']). Empty when no MEROPS annotation. Drill via gene_ontology_terms(ontology='merops'). |
| ncbifam_family_count | int (optional) | Distinct NCBIfam family annotations on this gene. When > 0, drill via gene_ontology_terms(ontology='ncbifam'). |
| merops_evidence_score_max | float \| None (optional) | Max MEROPS evidence_score over this gene's calls, in [0,1]. Twin of tcdb_evidence_score_max — uncoalesced: None = no MEROPS call at all, 0 = an uncorroborated one. Rank with it, don't filter. |
| discussed_in_publication_count | int (optional) | Distinct publications that discuss this gene in prose (precomputed Gene.discussed_in_publication_count). Recall-biased narrative mention, NOT DE-table expression. When > 0, set verbose=True for the per-paper DOI list, or call discussed_by_publication for a paper's full discussed set. |
| numeric_metric_count | int \| None (optional) | Numeric DM count (verbose-only). |
| boolean_metric_count | int \| None (optional) | Boolean DM count (verbose-only). |
| categorical_metric_count | int \| None (optional) | Categorical DM count (verbose-only). |
| numeric_metric_types_observed | list[string] \| None (optional) | Numeric metric_types observed (verbose-only). |
| boolean_metric_types_observed | list[string] \| None (optional) | Boolean metric_types observed (verbose-only). |
| categorical_metric_types_observed | list[string] \| None (optional) | Categorical metric_types observed (verbose-only). |
| compartments_observed | list[string] \| None (optional) | DM compartments observed for this gene (verbose-only). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| discussed_in_publications | list[DiscussedPublicationRef] \| None (optional) | Per-paper {doi, prominence, evidence} for papers discussing this gene (verbose-only; avg ~1, max 6 per gene). The evidence quote explains the mention inline. Call discussed_by_publication for a paper's full discussed set. |
| gene_summary | string \| None (optional) | Concatenated summary text (verbose-only, e.g. 'prmA :: ribosomal protein L11 methyltransferase :: Methylates ribosomal protein L11'). |
| function_description | string \| None (optional) | Curated functional description (verbose-only). May be null when no curated text exists. |
| all_identifiers | list[string] \| None (optional) | Cross-references: UniProt, CyanorakID, RefSeq, etc. (verbose-only). |

## Few-shot examples

### Example 1: Overview of a single gene

```example-call
gene_overview(locus_tags=["PMM1428"])
```

```example-response
{
  "total_matching": 1,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 1}],
  "by_category": [{"category": "Unknown", "count": 1}],
  "by_annotation_type": [{"annotation_type": "go_mf", "count": 1}, ...],
  "by_annotation_state": [{"annotation_state": "informative_multi", "count": 1}],
  "has_expression": 1, "has_significant_expression": 1, "has_orthologs": 1, "has_clusters": 1,
  "returned": 1, "truncated": false, "offset": 0, "not_found": [],
  "results": [
    {"locus_tag": "PMM1428", "gene_name": null, "product": "EVE domain protein", "gene_category": "Unknown", "annotation_quality": 3, "annotation_state": "informative_multi", "informative_annotation_types": ["go_mf", "pfam"], "organism_name": "Prochlorococcus MED4", "annotation_types": ["go_mf", "pfam", "cog_category", "tigr_role"], "expression_edge_count": 36, "significant_up_count": 3, "significant_down_count": 2, "closest_ortholog_group_size": 9, "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"], "cluster_membership_count": 2, "cluster_types": ["condition_comparison"]}
  ]
}
```

### Example 2: Batch overview with mixed organisms

```example-call
gene_overview(locus_tags=["PMM1428", "EZ55_00275"])
```

### Example 3: Summary only (counts and breakdowns)

```example-call
gene_overview(locus_tags=["PMM0845", "PMM1428", "EZ55_00275"], summary=True)
```

### Example 4: From discovery to overview to details

```
Step 1: genes_by_function(search_text="photosystem")
        → collect locus_tags from results

Step 2: gene_overview(locus_tags=["PMM0845", ...])
        → check which genes have expression data, ontology, orthologs, clusters

Step 3: gene_ontology_terms(locus_tags=["PMM0845"])
        → drill into annotations for genes with rich annotation_types
```

### Example 5: DM-bearing gene — see rhythmicity flags

```example-call
gene_overview(locus_tags=["MIT1002_01809"])
```

```example-response
{"total_matching": 1, "has_expression": 0, "has_derived_metrics": 1, "returned": 1, "truncated": false, "offset": 0, "not_found": [],
 "results": [
   {"locus_tag": "MIT1002_01809", "gene_name": null, "product": "MarR family winged helix-turn-helix transcriptional regulator", "organism_name": "Alteromonas macleodii MIT1002", "derived_metric_count": 1, "derived_metric_value_kinds": ["boolean"]}
 ]}
```

### Example 6: Transport-only gene — resolved transporter with zero catalysis reach

```example-call
gene_overview(locus_tags=["PMM0392", "PMM0001"])
```

```example-response
# catalyzed_metabolite_count counts the catalysis arm only
# (Gene → Reaction → Metabolite). PMM0392 reads 0 there, yet has
# chemistry: 'transport' in evidence_sources, tcdb_evidence_score_max
# 0.8 (how corroborated its best TCDB call is), transported_metabolite_count
# 13 (substrate breadth over its deepest TCDB attachments) and
# transport_substrate_resolution 'resolved' (at least one non-lumping
# attachment, so that breadth is a real call). PMM0001 has no TCDB
# call at all: score null, count 0, resolution null.
{"total_matching": 2, "has_expression": 2, "has_chemistry": 2, "returned": 2, "truncated": false, "offset": 0, "not_found": [],
 "results": [
   {"locus_tag": "PMM0392", "gene_name": "cbiQ", "product": "transmembrane component of ECF transporter energizing module", "organism_name": "Prochlorococcus MED4", "reaction_count": 0, "catalyzed_metabolite_count": 0, "tcdb_evidence_score_max": 0.8, "transported_metabolite_count": 13, "transport_substrate_resolution": "resolved", "evidence_sources": ["transport", "metabolomics"]},
   {"locus_tag": "PMM0001", "gene_name": "dnaN", "product": "DNA polymerase III, beta subunit", "organism_name": "Prochlorococcus MED4", "reaction_count": 4, "catalyzed_metabolite_count": 6, "tcdb_evidence_score_max": null, "transported_metabolite_count": 0, "transport_substrate_resolution": null, "evidence_sources": ["metabolism", "metabolomics"]}
 ]}
```

### Example 7: MEROPS peptidase + NCBIfam rollups on a gene

```example-call
gene_overview(locus_tags=["MIT1002_03660"])
```

```example-response
# merops_classes defaults to [] (list, not a single value — a gene can
# have both a peptidase call and a nonpeptidase_homolog call on
# different MEROPS families). ncbifam_family_count defaults to 0.
# merops_evidence_score_max is sparse and uncoalesced (null = no
# MEROPS call at all) — same rank-don't-filter contract as
# tcdb_evidence_score_max: read it to rank candidate genes, never as
# a pass/fail cutoff.
{"total_matching": 1, "by_merops_class": [{"merops_class": "peptidase", "count": 1}], "has_ncbifam": 0, "returned": 1, "truncated": false, "offset": 0, "not_found": [],
 "results": [
   {"locus_tag": "MIT1002_03660", "gene_name": null, "product": "Clp protease", "organism_name": "Alteromonas macleodii MIT1002", "merops_classes": ["peptidase"], "ncbifam_family_count": 0, "merops_evidence_score_max": 1.0}
 ]}
```

### Example 8: Genes named in the literature — which paper discusses them

```example-call
gene_overview(locus_tags=["PMT2118", "PMT_1030"])
```

```example-response
# Per-row discussed_in_publication_count flags genes a paper names in
# prose (avg 1.18, max 6 per gene). The envelope has_discussed counts
# input genes with >=1 discussing pub; top_discussing_publications
# ranks papers by how many of the queried genes they discuss
# (batch set-coverage — "which one paper covers most of my gene set").
{"total_matching": 2, "has_discussed": 2, "returned": 2, "truncated": false, "offset": 0, "not_found": [],
 "top_discussing_publications": [
   {"doi": "10.1038/ismej.2016.70", "title": "Transcriptional response of Prochlorococcus...", "n_genes": 2}
 ],
 "results": [
   {"locus_tag": "PMT2118", "gene_name": null, "product": "Hypothetical protein", "organism_name": "Prochlorococcus MIT9313", "discussed_in_publication_count": 1},
   {"locus_tag": "PMT_1030", "gene_name": null, "product": "possible Glucose-6-phosphate dehydrogenase, C-ter", "organism_name": "Prochlorococcus MIT9313", "discussed_in_publication_count": 1}
 ]}
```

## Chaining patterns

```
resolve_gene → gene_overview
genes_by_function → gene_overview
gene_overview → gene_ontology_terms
gene_overview → gene_homologs
gene_overview → differential_expression_by_gene
gene_overview → gene_clusters_by_gene
gene_overview(locus_tags=...) → for genes with derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric; for ['numeric'] use genes_by_numeric_metric; for ['categorical'] use genes_by_categorical_metric
gene_overview(verbose=True) → see compartments_observed for vesicle/whole-cell triage
gene_overview (per-row `evidence_sources` non-empty) → metabolites_by_gene OR genes_by_metabolite for chemistry drill-down.
gene_overview (per-row `transport_substrate_resolution='resolved'`, after reading `tcdb_evidence_score_max`) → metabolites_by_gene(locus_tags=[...], organism=..., evidence_sources=['transport']) — distinct metabolites in the rows equal `transported_metabolite_count`.
gene_overview (per-row `discussed_in_publication_count` > 0) → use verbose=True for the per-gene {doi, prominence, evidence} list, or discussed_by_publication(publication_dois=[...]) for the paper's full discussed set.
gene_overview (per-row `merops_classes` non-empty) → gene_ontology_terms(locus_tags=[...], ontology=['merops'], verbose=True) for the confidence_score / pfam_support detail behind the call, or genes_by_ontology(ontology='merops', call_class=['peptidase']) to find peers.
`merops_classes` is a list (`[]` default) because a gene can carry both a `peptidase` and a `nonpeptidase_homolog` MEROPS call on different families — don't assume at most one value. `merops_evidence_score_max` is sparse and uncoalesced (null = no MEROPS call at all, the twin contract of `tcdb_evidence_score_max`) — rank by it, never filter by it.
```

## Common mistakes

- annotation_quality / min_quality semantics shifted in 2026-05 KG release. Existing notebooks using min_quality may select a different gene set than before. See docs://guide/conventions.

- If a result row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric. Empty derived_metric_value_kinds means no DM evidence on this gene.

- annotation_types lists which ontology types have data — use gene_ontology_terms to get the actual terms.

- When `evidence_sources` is non-empty, drill via `metabolites_by_gene` (gene-anchored) or `genes_by_metabolite` (metabolite-anchored). Values are subset of {'metabolism', 'transport', 'metabolomics'} — 'metabolomics' means at least one of the gene's reachable metabolites has measurement coverage.

- `catalyzed_metabolite_count` counts the catalysis arm only (distinct metabolites via Gene → Reaction → Metabolite). It is NOT a total chemistry reach: a transport-only gene reads 0 here while `transported_metabolite_count > 0` and 'transport' appears in `evidence_sources`. Use `evidence_sources` to see which arms exist before interpreting a 0.

- TCDB routing rule: read the score; if resolved, drill into substrates. `tcdb_evidence_score_max` is the gene's most corroborated TCDB call (null = no TCDB call; 0 = an uncorroborated hit, not absence) — rank by it, never filter by it. `transport_substrate_resolution='family_inferred'` means `transported_metabolite_count` is reachability through a lumping family, not capability; `'resolved'` means at least one deepest attachment is non-lumping (not all of them — a superfamily rollup can still sit inside the count). Per-row `substrate_depth` in `metabolites_by_gene` separates the two.

- discussed_in_publication_count > 0 means at least one publication names this gene in prose (a recall-biased literature index, NOT DE-table expression). At ~1 pub/gene the answer is usually inline: verbose=True returns discussed_in_publications as {doi, prominence, evidence} per gene. Use discussed_by_publication for a paper's full discussed set.

```mistake
gene_overview(locus_tags=['PMM0845'], verbose=True)  # just to see the gene
```

```correction
gene_overview(locus_tags=['PMM0845'])  # verbose only needed for gene_summary text
```

## Package import equivalent

```python
from multiomics_explorer import gene_overview

result = gene_overview(locus_tags=...)
# returns dict with keys: total_matching, by_organism, by_category, by_annotation_type, by_annotation_state, has_expression, has_significant_expression, has_orthologs, has_clusters, has_derived_metrics, has_chemistry, has_discussed, top_discussing_publications, has_ncbifam, by_merops_class, offset, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
