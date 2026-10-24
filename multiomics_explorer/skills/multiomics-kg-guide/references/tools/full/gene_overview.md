# gene_overview

## What it does

Batch gene triage: identity plus per-gene data-availability signals — expression, ortholog, cluster, DM, chemistry, annotation-family and literature counts.

Use to decide which drill-down has evidence for a gene batch; for the raw node dump use `gene_details`.
Filters: locus_tags.
Returns: by_organism, by_category, by_annotation_type, has_* batch counts, top_discussing_publications, not_found; one row = one gene's routing counts.
docs://tools/gene_overview; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845']. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int \| None | None | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Response format

### Envelope

```expected-keys
total_matching, by_organism, by_category, by_annotation_type, by_annotation_state, has_expression, has_significant_expression, has_orthologs, has_clusters, has_derived_metrics, has_chemistry, has_discussed, top_discussing_publications, has_ncbifam, has_tcdb, has_cazy, by_merops_class, returned, offset, truncated, not_found, warnings, results
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
- **has_tcdb** (int): Count of requested locus_tags with at least one gated TCDB call (tcdb_assignment_count > 0).
- **has_cazy** (int): Count of requested locus_tags with at least one CAZy family annotation (cazy_family_count > 0).
- **by_merops_class** (list[OverviewMeropsClassBreakdown]): Rollup of merops_classes over the result set, sorted desc by count.
- **returned** (int): Results in this response (0 when summary=true).
- **offset** (int): Offset into full result set.
- **truncated** (bool): True if total_matching > returned.
- **not_found** (list[string]): Input locus_tags not in KG.
- **warnings** (list[string]): Advisory diagnostics — e.g. a not_found locus_tag differs only by case from a real one (locus_tags are never case-normalised).

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
| catalyzed_metabolite_count | int (optional) | Distinct metabolites reachable via catalysis only (Gene_catalyzes_reaction → Reaction_has_metabolite). Transport-only genes read 0 — check transported_metabolite_count / 'transport' in evidence_sources (e.g. cynD PMM0372: 0 here, 3 transported). |
| tcdb_best_hit_identity | float \| None (optional) | Percent identity of the gene's rank-1 diamond best hit to TCDB, read live and NOT gated (reported even below the 40% gate). How close the nearest characterised system is; rank, don't filter. None = no best hit. |
| transported_metabolite_count | int (optional) | Distinct metabolites this gene transports via its direct TCDB systems (tcdb_gate='direct'; precomputed Gene.transported_metabolite_count). Pairs with catalyzed_metabolite_count. When > 0, drill via metabolites_by_gene(locus_tags=[...]). |
| go_transport_metabolite_count | int (optional) | GO-route mirror of transported_metabolite_count: distinct metabolites (not roles) via the gene's direct GO terms; is_a-inherited not counted. A term-definition count, not a gene fact. Drill via metabolites_by_gene. |
| evidence_sources | list[string] (optional) | Path provenance — values from {'metabolism', 'transport', 'metabolomics', 'go_transport'}. When non-empty, drill into metabolites_by_gene(locus_tags=[...]). Per-source definitions: see docs://guide/concepts. |
| merops_classes | list[string] (optional) | Distinct MEROPS call_class values across this gene's MEROPS calls (e.g. ['peptidase']). Empty when no MEROPS annotation. Drill via gene_ontology_terms(ontology='merops'). |
| ncbifam_family_count | int (optional) | Distinct NCBIfam family annotations on this gene. When > 0, drill via gene_ontology_terms(ontology='ncbifam'). |
| tcdb_assignment_count | int (optional) | Distinct gated TCDB targets (systems, subfamilies, families) minus any that is an ancestor of another (precomputed Gene.tcdb_assignment_count); equals the default TCDB leaf row count from gene_ontology_terms. 0 = no gated TCDB call. |
| cazy_family_count | int (optional) | Distinct CAZy families on this gene (precomputed Gene.cazy_family_count; flat ontology). When > 0, drill via gene_ontology_terms(ontology=['cazy']) or find peers with genes_by_ontology(ontology='cazy'). |
| merops_evidence_score_max | float \| None (optional) | Max MEROPS evidence_score over this gene's calls, in [0,1]. Uncoalesced: None = no MEROPS call at all, 0 = an uncorroborated one. Rank with it, don't filter. |
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
  "by_annotation_type": [
    {"annotation_type": "go_mf", "count": 1},
    {"annotation_type": "pfam", "count": 1},
    {"annotation_type": "cog_category", "count": 1},
    {"annotation_type": "tigr_role", "count": 1},
    {"annotation_type": "interpro", "count": 1}
  ],
  "by_annotation_state": [{"annotation_state": "informative_multi", "count": 1}],
  "has_expression": 1,
  "has_significant_expression": 1,
  "has_orthologs": 1,
  "has_clusters": 1,
  "has_derived_metrics": 1,
  "has_chemistry": 0,
  "has_discussed": 0,
  "top_discussing_publications": [],
  "has_ncbifam": 0,
  "has_tcdb": 0,
  "has_cazy": 0,
  "by_merops_class": [],
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM1428",
      "gene_name": null,
      "product": "EVE domain protein",
      "gene_category": "Unknown",
      "annotation_quality": 3,
      "organism_name": "Prochlorococcus MED4",
      "annotation_types": ["go_mf", "pfam", "cog_category", "tigr_role", "interpro"],
      "annotation_state": "informative_multi",
      "informative_annotation_types": ["go_mf", "pfam"],
      "expression_edge_count": 41,
      "significant_up_count": 4,
      "significant_down_count": 2,
      "closest_ortholog_group_size": 22,
      "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
      "cluster_membership_count": 2,
      "cluster_types": ["diel", "time_course"],
      "derived_metric_count": 9,
      "derived_metric_value_kinds": ["numeric", "boolean", "categorical"],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "tcdb_best_hit_identity": null,
      "transported_metabolite_count": 0,
      "go_transport_metabolite_count": 0,
      "evidence_sources": [],
      "merops_classes": [],
      "ncbifam_family_count": 0,
      "tcdb_assignment_count": 0,
      "cazy_family_count": 0,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 0
    }
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
{
  "total_matching": 1,
  "by_organism": [{"organism_name": "Alteromonas macleodii MIT1002", "count": 1}],
  "by_category": [{"category": "Transcription", "count": 1}],
  "by_annotation_type": [
    {"annotation_type": "go_bp", "count": 1},
    {"annotation_type": "go_mf", "count": 1},
    {"annotation_type": "pfam", "count": 1},
    {"annotation_type": "cog_category", "count": 1},
    {"annotation_type": "interpro", "count": 1}
  ],
  "by_annotation_state": [{"annotation_state": "informative_multi", "count": 1}],
  "has_expression": 1,
  "has_significant_expression": 1,
  "has_orthologs": 1,
  "has_clusters": 0,
  "has_derived_metrics": 1,
  "has_chemistry": 0,
  "has_discussed": 0,
  "top_discussing_publications": [],
  "has_ncbifam": 0,
  "has_tcdb": 0,
  "has_cazy": 0,
  "by_merops_class": [],
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "MIT1002_01809",
      "gene_name": null,
      "product": "MarR family winged helix-turn-helix transcriptional regulator",
      "gene_category": "Transcription",
      "annotation_quality": 3,
      "organism_name": "Alteromonas macleodii MIT1002",
      "annotation_types": ["go_bp", "go_mf", "pfam", "cog_category", "interpro"],
      "annotation_state": "informative_multi",
      "informative_annotation_types": ["go_bp", "go_mf", "pfam", "cog_category"],
      "expression_edge_count": 9,
      "significant_up_count": 2,
      "significant_down_count": 0,
      "closest_ortholog_group_size": 9,
      "closest_ortholog_genera": ["Alteromonas"],
      "cluster_membership_count": 0,
      "cluster_types": [],
      "derived_metric_count": 1,
      "derived_metric_value_kinds": ["boolean"],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "tcdb_best_hit_identity": null,
      "transported_metabolite_count": 0,
      "go_transport_metabolite_count": 0,
      "evidence_sources": [],
      "merops_classes": [],
      "ncbifam_family_count": 0,
      "tcdb_assignment_count": 0,
      "cazy_family_count": 0,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 0
    }
  ]
}
```

### Example 6: Transport-only gene — direct TCDB systems, zero catalysis reach

```example-call
gene_overview(locus_tags=["PMM0372", "PMM0001"])
```

```example-response
{
  "total_matching": 2,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 2}],
  "by_category": [
    {"category": "Central intermediary metabolism", "count": 1},
    {"category": "Replication and repair", "count": 1}
  ],
  "by_annotation_type": [
    {"annotation_type": "go_bp", "count": 2},
    {"annotation_type": "go_mf", "count": 2},
    {"annotation_type": "go_cc", "count": 2},
    {"annotation_type": "pfam", "count": 2},
    {"annotation_type": "cog_category", "count": 2},
    ...
  ],
  "by_annotation_state": [{"annotation_state": "informative_multi", "count": 2}],
  "has_expression": 2,
  "has_significant_expression": 2,
  "has_orthologs": 2,
  "has_clusters": 2,
  "has_derived_metrics": 2,
  "has_chemistry": 2,
  "has_discussed": 2,
  "top_discussing_publications": [
    {
      "doi": "10.1186/gb-2010-11-5-r54",
      "title": "RNA half-lives in the slow-growing marine cyanobacterium Prochlorococcus",
      "n_genes": 1
    },
    {
      "doi": "10.64898/2026.04.15.718746",
      "title": "Extreme genome reduction selectively retains modular regulatory architecture in Prochlorococcus MED4: conserved trans...",
      "n_genes": 1
    }
  ],
  "has_ncbifam": 2,
  "has_tcdb": 1,
  "has_cazy": 0,
  "by_merops_class": [],
  "returned": 2,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0001",
      "gene_name": "dnaN",
      "product": "DNA polymerase III, beta subunit",
      "gene_category": "Replication and repair",
      "annotation_quality": 3,
      "organism_name": "Prochlorococcus MED4",
      "annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "annotation_state": "informative_multi",
      "informative_annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "expression_edge_count": 37,
      "significant_up_count": 5,
      "significant_down_count": 2,
      "closest_ortholog_group_size": 22,
      "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
      "cluster_membership_count": 2,
      "cluster_types": ["decay_pattern", "diel"],
      "derived_metric_count": 17,
      "derived_metric_value_kinds": ["numeric", "boolean", "categorical"],
      "reaction_count": 4,
      "catalyzed_metabolite_count": 6,
      "tcdb_best_hit_identity": null,
      "transported_metabolite_count": 0,
      "go_transport_metabolite_count": 0,
      "evidence_sources": ["metabolism"],
      "merops_classes": [],
      "ncbifam_family_count": 1,
      "tcdb_assignment_count": 0,
      "cazy_family_count": 0,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 1
    },
    {
      "locus_tag": "PMM0372",
      "gene_name": "cynD",
      "product": "cyanate ABC transporter ATP-binding protein",
      "gene_category": "Central intermediary metabolism",
      "annotation_quality": 3,
      "organism_name": "Prochlorococcus MED4",
      "annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "annotation_state": "informative_multi",
      "informative_annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "expression_edge_count": 30,
      "significant_up_count": 12,
      "significant_down_count": 1,
      "closest_ortholog_group_size": 3,
      "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
      "cluster_membership_count": 4,
      "cluster_types": ["genomic_island", "decay_pattern", "diel", "time_course"],
      "derived_metric_count": 9,
      "derived_metric_value_kinds": ["numeric", "boolean", "categorical"],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "tcdb_best_hit_identity": 59.2,
      "transported_metabolite_count": 3,
      "go_transport_metabolite_count": 2,
      "evidence_sources": ["transport", "go_transport"],
      "merops_classes": [],
      "ncbifam_family_count": 1,
      "tcdb_assignment_count": 2,
      "cazy_family_count": 0,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 1
    }
  ]
}
```

### Example 7: CAZy-only gene — carbohydrate-active enzyme with no transporter call

```example-call
gene_overview(locus_tags=["HP15_1897"])
```

```example-response
{
  "total_matching": 1,
  "by_organism": [{"organism_name": "Marinobacter (MarRef v6)", "count": 1}],
  "by_category": [{"category": "Carbohydrate metabolism", "count": 1}],
  "by_annotation_type": [
    {"annotation_type": "pfam", "count": 1},
    {"annotation_type": "cog_category", "count": 1},
    {"annotation_type": "kegg", "count": 1},
    {"annotation_type": "brite", "count": 1},
    {"annotation_type": "ec", "count": 1},
    ...
  ],
  "by_annotation_state": [{"annotation_state": "informative_multi", "count": 1}],
  "has_expression": 0,
  "has_significant_expression": 0,
  "has_orthologs": 1,
  "has_clusters": 0,
  "has_derived_metrics": 0,
  "has_chemistry": 1,
  "has_discussed": 0,
  "top_discussing_publications": [],
  "has_ncbifam": 0,
  "has_tcdb": 0,
  "has_cazy": 1,
  "by_merops_class": [],
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "HP15_1897",
      "gene_name": null,
      "product": "FG-GAP repeat domain-containing protein",
      "gene_category": "Carbohydrate metabolism",
      "annotation_quality": 3,
      "organism_name": "Marinobacter (MarRef v6)",
      "annotation_types": ["pfam", "cog_category", "kegg", "brite", "ec", ...],
      "annotation_state": "informative_multi",
      "informative_annotation_types": ["pfam", "cog_category", "kegg", "brite", "ec", ...],
      "expression_edge_count": 0,
      "significant_up_count": 0,
      "significant_down_count": 0,
      "closest_ortholog_group_size": 3,
      "closest_ortholog_genera": ["Alteromonas", "Marinobacter", "Meiothermus"],
      "cluster_membership_count": 0,
      "cluster_types": [],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "reaction_count": 3,
      "catalyzed_metabolite_count": 4,
      "tcdb_best_hit_identity": null,
      "transported_metabolite_count": 0,
      "go_transport_metabolite_count": 0,
      "evidence_sources": ["metabolism"],
      "merops_classes": [],
      "ncbifam_family_count": 0,
      "tcdb_assignment_count": 0,
      "cazy_family_count": 4,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 0
    }
  ]
}
```

### Example 8: MEROPS peptidase + NCBIfam rollups on a gene

```example-call
gene_overview(locus_tags=["MIT1002_03660"])
```

```example-response
{
  "total_matching": 1,
  "by_organism": [{"organism_name": "Alteromonas macleodii MIT1002", "count": 1}],
  "by_category": [{"category": "Post-translational modification", "count": 1}],
  "by_annotation_type": [
    {"annotation_type": "go_bp", "count": 1},
    {"annotation_type": "go_mf", "count": 1},
    {"annotation_type": "go_cc", "count": 1},
    {"annotation_type": "pfam", "count": 1},
    {"annotation_type": "cog_category", "count": 1},
    ...
  ],
  "by_annotation_state": [{"annotation_state": "informative_multi", "count": 1}],
  "has_expression": 1,
  "has_significant_expression": 0,
  "has_orthologs": 1,
  "has_clusters": 0,
  "has_derived_metrics": 0,
  "has_chemistry": 0,
  "has_discussed": 0,
  "top_discussing_publications": [],
  "has_ncbifam": 1,
  "has_tcdb": 0,
  "has_cazy": 0,
  "by_merops_class": [{"merops_class": "peptidase", "count": 1}],
  "returned": 1,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "MIT1002_03660",
      "gene_name": "hslV",
      "product": "ATP-dependent protease subunit HslV",
      "gene_category": "Post-translational modification",
      "annotation_quality": 3,
      "organism_name": "Alteromonas macleodii MIT1002",
      "annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "annotation_state": "informative_multi",
      "informative_annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "expression_edge_count": 7,
      "significant_up_count": 0,
      "significant_down_count": 0,
      "closest_ortholog_group_size": 9,
      "closest_ortholog_genera": ["Alteromonas"],
      "cluster_membership_count": 0,
      "cluster_types": [],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "tcdb_best_hit_identity": null,
      "transported_metabolite_count": 0,
      "go_transport_metabolite_count": 0,
      "evidence_sources": [],
      "merops_classes": ["peptidase"],
      "ncbifam_family_count": 2,
      "tcdb_assignment_count": 0,
      "cazy_family_count": 0,
      "merops_evidence_score_max": 1.0,
      "discussed_in_publication_count": 0
    }
  ]
}
```

### Example 9: Genes named in the literature — which paper discusses them

```example-call
gene_overview(locus_tags=["PMT2118", "PMT_1030"])
```

```example-response
{
  "total_matching": 2,
  "by_organism": [{"organism_name": "Prochlorococcus MIT9313", "count": 2}],
  "by_category": [{"category": "Unknown", "count": 2}],
  "by_annotation_type": [{"annotation_type": "ncbifam", "count": 2}, {"annotation_type": "interpro", "count": 1}],
  "by_annotation_state": [{"annotation_state": "informative_single", "count": 2}],
  "has_expression": 2,
  "has_significant_expression": 1,
  "has_orthologs": 2,
  "has_clusters": 2,
  "has_derived_metrics": 2,
  "has_chemistry": 0,
  "has_discussed": 2,
  "top_discussing_publications": [
    {
      "doi": "10.1038/ismej.2016.70",
      "title": "Transcriptional response of Prochlorococcus to co-culture with a marine Alteromonas: differences between strains and ...",
      "n_genes": 2
    }
  ],
  "has_ncbifam": 2,
  "has_tcdb": 0,
  "has_cazy": 0,
  "by_merops_class": [],
  "returned": 2,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMT2118",
      "gene_name": null,
      "product": "Hypothetical protein",
      "gene_category": "Unknown",
      "annotation_quality": 2,
      "organism_name": "Prochlorococcus MIT9313",
      "annotation_types": ["ncbifam"],
      "annotation_state": "informative_single",
      "informative_annotation_types": ["ncbifam"],
      "expression_edge_count": 14,
      "significant_up_count": 2,
      "significant_down_count": 1,
      "closest_ortholog_group_size": 9,
      "closest_ortholog_genera": ["Prochlorococcus"],
      "cluster_membership_count": 2,
      "cluster_types": ["genomic_island", "time_course"],
      "derived_metric_count": 4,
      "derived_metric_value_kinds": ["numeric", "boolean"],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "tcdb_best_hit_identity": null,
      "transported_metabolite_count": 0,
      "go_transport_metabolite_count": 0,
      "evidence_sources": [],
      "merops_classes": [],
      "ncbifam_family_count": 1,
      "tcdb_assignment_count": 0,
      "cazy_family_count": 0,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 1
    },
    {
      "locus_tag": "PMT_1030",
      "gene_name": null,
      "product": "possible Glucose-6-phosphate dehydrogenase, C-ter",
      "gene_category": "Unknown",
      "annotation_quality": 2,
      "organism_name": "Prochlorococcus MIT9313",
      "annotation_types": ["interpro", "ncbifam"],
      "annotation_state": "informative_single",
      "informative_annotation_types": ["ncbifam"],
      "expression_edge_count": 10,
      "significant_up_count": 0,
      "significant_down_count": 0,
      "closest_ortholog_group_size": 1,
      "closest_ortholog_genera": ["Prochlorococcus"],
      "cluster_membership_count": 1,
      "cluster_types": ["genomic_island"],
      "derived_metric_count": 3,
      "derived_metric_value_kinds": ["numeric", "boolean"],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "tcdb_best_hit_identity": null,
      "transported_metabolite_count": 0,
      "go_transport_metabolite_count": 0,
      "evidence_sources": [],
      "merops_classes": [],
      "ncbifam_family_count": 2,
      "tcdb_assignment_count": 0,
      "cazy_family_count": 0,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 1
    }
  ]
}
```

### Example 10: GO-transport-only gene — evidence_sources reads ['go_transport'] with no TCDB or KEGG call

```example-call
gene_overview(locus_tags=["PMM0533", "PMM0970"])
```

*PMM0533 (aar, long-chain fatty acyl-ACP reductase) carries a GO transport term and no TCDB or KEGG chemistry, so `evidence_sources=['go_transport']` is its only chemistry tag; PMM0970 (urtA) carries `transport` and `go_transport`. `has_chemistry` in the summary now counts GO-only genes. The tag only says a GO route exists: drill with `metabolites_by_gene`.*

```example-response
{
  "total_matching": 2,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 2}],
  "by_category": [{"category": "Lipid metabolism", "count": 1}, {"category": "Stress response and adaptation", "count": 1}],
  "by_annotation_type": [
    {"annotation_type": "go_bp", "count": 2},
    {"annotation_type": "go_mf", "count": 2},
    {"annotation_type": "go_cc", "count": 2},
    {"annotation_type": "pfam", "count": 2},
    {"annotation_type": "cog_category", "count": 2},
    ...
  ],
  "by_annotation_state": [{"annotation_state": "informative_multi", "count": 2}],
  "has_expression": 2,
  "has_significant_expression": 2,
  "has_orthologs": 2,
  "has_clusters": 2,
  "has_derived_metrics": 2,
  "has_chemistry": 2,
  "has_discussed": 1,
  "top_discussing_publications": [
    {
      "doi": "10.1038/ismej.2017.88",
      "title": "Nitrogen cost minimization is promoted by structural changes in the transcriptome of N-deprived Prochlorococcus cells",
      "n_genes": 1
    },
    {
      "doi": "10.1038/msb4100087",
      "title": "Global gene expression of Prochlorococcus ecotypes in response to changes in nitrogen availability",
      "n_genes": 1
    }
  ],
  "has_ncbifam": 2,
  "has_tcdb": 1,
  "has_cazy": 0,
  "by_merops_class": [],
  "returned": 2,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0533",
      "gene_name": "aar",
      "product": "long-chain fatty acyl-ACP reductase",
      "gene_category": "Lipid metabolism",
      "annotation_quality": 3,
      "organism_name": "Prochlorococcus MED4",
      "annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "annotation_state": "informative_multi",
      "informative_annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "kegg", ...],
      "expression_edge_count": 33,
      "significant_up_count": 0,
      "significant_down_count": 8,
      "closest_ortholog_group_size": 23,
      "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
      "cluster_membership_count": 2,
      "cluster_types": ["decay_pattern", "diel"],
      "derived_metric_count": 11,
      "derived_metric_value_kinds": ["numeric", "boolean", "categorical"],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "tcdb_best_hit_identity": null,
      "transported_metabolite_count": 0,
      "go_transport_metabolite_count": 4,
      "evidence_sources": ["go_transport"],
      "merops_classes": [],
      "ncbifam_family_count": 1,
      "tcdb_assignment_count": 0,
      "cazy_family_count": 0,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 0
    },
    {
      "locus_tag": "PMM0970",
      "gene_name": "urtA",
      "product": "ABC-type urea transporter, substrate binding component",
      "gene_category": "Stress response and adaptation",
      "annotation_quality": 3,
      "organism_name": "Prochlorococcus MED4",
      "annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "annotation_state": "informative_multi",
      "informative_annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "expression_edge_count": 53,
      "significant_up_count": 17,
      "significant_down_count": 10,
      "closest_ortholog_group_size": 21,
      "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
      "cluster_membership_count": 5,
      "cluster_types": ["genomic_island", "decay_pattern", "diel", "time_course"],
      "derived_metric_count": 11,
      "derived_metric_value_kinds": ["numeric", "boolean", "categorical"],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "tcdb_best_hit_identity": 57.1,
      "transported_metabolite_count": 3,
      "go_transport_metabolite_count": 1,
      "evidence_sources": ["transport", "go_transport"],
      "merops_classes": [],
      "ncbifam_family_count": 1,
      "tcdb_assignment_count": 2,
      "cazy_family_count": 0,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 2
    }
  ]
}
```

### Example 11: GO-route metabolite count next to the TCDB count

```example-call
gene_overview(locus_tags=["PMM0372", "PMM0970", "PMM0974"])
```

*`go_transport_metabolite_count` mirrors `transported_metabolite_count` for the GO route: distinct metabolites named by the gene's own GO transport terms. urtE (PMM0974) reaches 3, cynD (PMM0372) 2 and urtA (PMM0970) 1, while all three reach 3 metabolites through their direct TCDB systems. Chemical roles and is_a-inherited GO targets are not counted; drill in with `metabolites_by_gene(..., evidence_sources=['go_transport'])`.*

```example-response
{
  "total_matching": 3,
  "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 3}],
  "by_category": [
    {"category": "Stress response and adaptation", "count": 2},
    {"category": "Central intermediary metabolism", "count": 1}
  ],
  "by_annotation_type": [
    {"annotation_type": "go_bp", "count": 3},
    {"annotation_type": "go_mf", "count": 3},
    {"annotation_type": "go_cc", "count": 3},
    {"annotation_type": "pfam", "count": 3},
    {"annotation_type": "cog_category", "count": 3},
    ...
  ],
  "by_annotation_state": [{"annotation_state": "informative_multi", "count": 3}],
  "has_expression": 3,
  "has_significant_expression": 3,
  "has_orthologs": 3,
  "has_clusters": 3,
  "has_derived_metrics": 3,
  "has_chemistry": 3,
  "has_discussed": 3,
  "top_discussing_publications": [
    {
      "doi": "10.1038/ismej.2017.88",
      "title": "Nitrogen cost minimization is promoted by structural changes in the transcriptome of N-deprived Prochlorococcus cells",
      "n_genes": 2
    },
    {
      "doi": "10.1038/msb4100087",
      "title": "Global gene expression of Prochlorococcus ecotypes in response to changes in nitrogen availability",
      "n_genes": 1
    },
    {
      "doi": "10.64898/2026.04.15.718746",
      "title": "Extreme genome reduction selectively retains modular regulatory architecture in Prochlorococcus MED4: conserved trans...",
      "n_genes": 1
    }
  ],
  "has_ncbifam": 3,
  "has_tcdb": 3,
  "has_cazy": 0,
  "by_merops_class": [],
  "returned": 3,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "warnings": [],
  "results": [
    {
      "locus_tag": "PMM0372",
      "gene_name": "cynD",
      "product": "cyanate ABC transporter ATP-binding protein",
      "gene_category": "Central intermediary metabolism",
      "annotation_quality": 3,
      "organism_name": "Prochlorococcus MED4",
      "annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "annotation_state": "informative_multi",
      "informative_annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "expression_edge_count": 30,
      "significant_up_count": 12,
      "significant_down_count": 1,
      "closest_ortholog_group_size": 3,
      "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
      "cluster_membership_count": 4,
      "cluster_types": ["genomic_island", "decay_pattern", "diel", "time_course"],
      "derived_metric_count": 9,
      "derived_metric_value_kinds": ["numeric", "boolean", "categorical"],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "tcdb_best_hit_identity": 59.2,
      "transported_metabolite_count": 3,
      "go_transport_metabolite_count": 2,
      "evidence_sources": ["transport", "go_transport"],
      "merops_classes": [],
      "ncbifam_family_count": 1,
      "tcdb_assignment_count": 2,
      "cazy_family_count": 0,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 1
    },
    {
      "locus_tag": "PMM0970",
      "gene_name": "urtA",
      "product": "ABC-type urea transporter, substrate binding component",
      "gene_category": "Stress response and adaptation",
      "annotation_quality": 3,
      "organism_name": "Prochlorococcus MED4",
      "annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "annotation_state": "informative_multi",
      "informative_annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "expression_edge_count": 53,
      "significant_up_count": 17,
      "significant_down_count": 10,
      "closest_ortholog_group_size": 21,
      "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
      "cluster_membership_count": 5,
      "cluster_types": ["genomic_island", "decay_pattern", "diel", "time_course"],
      "derived_metric_count": 11,
      "derived_metric_value_kinds": ["numeric", "boolean", "categorical"],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "tcdb_best_hit_identity": 57.1,
      "transported_metabolite_count": 3,
      "go_transport_metabolite_count": 1,
      "evidence_sources": ["transport", "go_transport"],
      "merops_classes": [],
      "ncbifam_family_count": 1,
      "tcdb_assignment_count": 2,
      "cazy_family_count": 0,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 2
    },
    {
      "locus_tag": "PMM0974",
      "gene_name": "urtE",
      "product": "ABC-type urea transporter, ATPase component UrtE",
      "gene_category": "Stress response and adaptation",
      "annotation_quality": 3,
      "organism_name": "Prochlorococcus MED4",
      "annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "annotation_state": "informative_multi",
      "informative_annotation_types": ["go_bp", "go_mf", "go_cc", "pfam", "cog_category", ...],
      "expression_edge_count": 34,
      "significant_up_count": 8,
      "significant_down_count": 1,
      "closest_ortholog_group_size": 19,
      "closest_ortholog_genera": ["Prochlorococcus", "Synechococcus"],
      "cluster_membership_count": 2,
      "cluster_types": ["genomic_island", "diel"],
      "derived_metric_count": 12,
      "derived_metric_value_kinds": ["numeric", "boolean", "categorical"],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "tcdb_best_hit_identity": 62.1,
      "transported_metabolite_count": 3,
      "go_transport_metabolite_count": 3,
      "evidence_sources": ["transport", "go_transport"],
      "merops_classes": [],
      "ncbifam_family_count": 1,
      "tcdb_assignment_count": 2,
      "cazy_family_count": 0,
      "merops_evidence_score_max": null,
      "discussed_in_publication_count": 1
    }
  ]
}
```

### Example 12: TCDB triage — assignment count, best-hit identity and the direct transport reach

```example-call
gene_overview(locus_tags=["PMM0372", "PMM0125", "PMM0673", "PMM0024"])
```

*`tcdb_assignment_count` counts the gene's gated TCDB targets (`tcdb_gate` direct or annotated, minus any target that is an ancestor of another). cynD (PMM0372) has 2 sibling systems and reaches 3 metabolites directly; ecfA1 (PMM0125) has 7 eggNOG subfamily calls but no system, so `transported_metabolite_count=0`; phnD (PMM0673) has 1 subfamily call and also 0 direct reach (its substrates come from the family walk in `metabolites_by_gene`); thiL (PMM0024) has 0, because its only TCDB edge is a weak tier-3 DIAMOND hit. `tcdb_best_hit_identity` is the identity of the rank-1 DIAMOND best hit, reported even below the gate (ecfA1 33.5) and null when there is none (phnD, thiL): rank by it, never filter.*

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
gene_overview (per-row `transported_metabolite_count` > 0) → metabolites_by_gene(locus_tags=[...], organism=..., evidence_sources=['transport']) — distinct Metabolite targets in the direct rows equal `transported_metabolite_count`.
gene_overview (per-row `tcdb_assignment_count` > 0 but `transported_metabolite_count` = 0) → metabolites_by_gene(locus_tags=[...], organism=..., include_tcdb_family_substrates=True) for family-level substrate candidates.
gene_overview (per-row `discussed_in_publication_count` > 0) → use verbose=True for the per-gene {doi, prominence, evidence} list, or discussed_by_publication(publication_dois=[...]) for the paper's full discussed set.
gene_overview (per-row `tcdb_assignment_count` > 0) → gene_ontology_terms(locus_tags=[...], ontology=['tcdb']) for the TC ids, `tcdb_call` / `tcdb_gate` and evidence; `cazy_family_count` > 0 → gene_ontology_terms(locus_tags=[...], ontology=['cazy']), or genes_by_ontology(ontology='cazy', organism=...) for peers.
gene_overview envelope `has_tcdb` / `has_cazy` = batch triage (how many input genes carry a transporter-family / carbohydrate-active-enzyme call) before deciding whether a pathway_enrichment(ontology='tcdb'|'cazy') run is worth it.
gene_overview (per-row `merops_classes` non-empty) → gene_ontology_terms(locus_tags=[...], ontology=['merops'], verbose=True) for the confidence_score / pfam_support detail behind the call, or genes_by_ontology(ontology='merops', call_class=['peptidase']) to find peers.
`merops_classes` is a list (`[]` default) because a gene can carry both a `peptidase` and a `nonpeptidase_homolog` MEROPS call on different families — don't assume at most one value. `merops_evidence_score_max` is sparse and uncoalesced (null = no MEROPS call at all) — rank by it, never filter by it.
gene_overview (per-row derived_metric_count > 0) → gene_derived_metrics(locus_tags=[...], organism=...) for the gene's full DM profile across numeric, boolean and categorical kinds
gene_overview → evidence_sources contains 'go_transport' → metabolites_by_gene(locus_tags=[...], organism=..., evidence_sources=['go_transport']) for the GO term and target behind the tag
```

## Common mistakes

- annotation_quality / min_quality semantics shifted in 2026-05 KG release. Existing notebooks using min_quality may select a different gene set than before. See docs://guide/conventions.

- If a result row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric. Empty derived_metric_value_kinds means no DM evidence on this gene.

- annotation_types lists which ontology types have data — use gene_ontology_terms to get the actual terms.

- When `evidence_sources` is non-empty, drill via `metabolites_by_gene` (gene-anchored) or `genes_by_metabolite` (metabolite-anchored). Values are subset of {'metabolism', 'transport', 'metabolomics'} — 'metabolomics' means at least one of the gene's reachable metabolites has measurement coverage.

- `catalyzed_metabolite_count` counts the catalysis arm only (distinct metabolites via Gene → Reaction → Metabolite). It is NOT a total chemistry reach: a transport-only gene reads 0 here while `transported_metabolite_count > 0` and 'transport' appears in `evidence_sources`. Use `evidence_sources` to see which arms exist before interpreting a 0.

- TCDB routing rule: `transported_metabolite_count > 0` means the gene points directly (`tcdb_gate='direct'`) at a TC system that TCDB curates with substrates; drill with `metabolites_by_gene`. `tcdb_assignment_count > 0` with `transported_metabolite_count = 0` means TCDB placed the gene only at family or subfamily level (or at a system with no curated substrate): its substrate candidates come from `metabolites_by_gene(..., include_tcdb_family_substrates=True)`, a recall expansion. `tcdb_assignment_count = 0` with a TCDB edge means weak DIAMOND hits only; `gene_ontology_terms(..., include_weak_tcdb_hits=True)` shows them.

- `tcdb_assignment_count` is the KG's count of the gene's gated TCDB targets (`tcdb_gate` direct or annotated), minus any target that is an ancestor of another; most are systems or subfamilies, not families. It equals the TCDB row count of `gene_ontology_terms(ontology=['tcdb'])` in default leaf mode. `has_tcdb` counts genes with `tcdb_assignment_count > 0`.

- `tcdb_best_hit_identity` is the percent identity of the gene's rank-1 DIAMOND best hit against TCDB, read without the gate: it is reported even when that hit is below the gate (< 40%). It is a hint of how close the nearest characterised system is. Rank by it, never filter; null means no best hit, not no TCDB call (an eggNOG-only gene reads null).

- discussed_in_publication_count > 0 means at least one publication names this gene in prose (a recall-biased literature index, NOT DE-table expression). At ~1 pub/gene the answer is usually inline: verbose=True returns discussed_in_publications as {doi, prominence, evidence} per gene. Use discussed_by_publication for a paper's full discussed set.

```mistake
gene_overview(locus_tags=['PMM0845'], verbose=True)  # just to see the gene
```

```correction
gene_overview(locus_tags=['PMM0845'])  # compact carries every routing count; verbose adds the text fields (gene_summary, function_description, all_identifiers), the per-gene discussed_in_publications list, per-kind DM counts (numeric/boolean/categorical_metric_count + *_metric_types_observed) and compartments_observed
```

- `limit` defaults to every input gene (min 25) rather than a small page — pass an explicit number to page.

- The annotation-family columns (`merops_classes`, `tcdb_assignment_count`, `tcdb_best_hit_identity`, `cazy_family_count`, `ncbifam_family_count`, `merops_evidence_score_max`) belong to the annotation-trust surface — see docs://analysis/annotation_evidence for how to read them.

- The `go_transport` tag in `evidence_sources` means the gene carries a GO term that GO defines as moving some compound or role (a term definition, not a measured transport activity). It is separate from `transport` (TCDB) and does not change `transported_metabolite_count`, `tcdb_*` counts or `catalyzed_metabolite_count`. A biological-process term can tag a gene that is not a transporter (MED4 `ftn` reaches iron through "iron ion transport"). Read `docs://analysis/transport` before combining the routes.

- `go_transport_metabolite_count` counts metabolites, not chemical roles, and direct GO terms only (no is_a-inherited targets). It is a count of what the gene's GO terms are defined to move, not a measured activity, and it does not add to `transported_metabolite_count` (TCDB) or `catalyzed_metabolite_count`. A gene can read 0 here and still carry `go_transport` in `evidence_sources` through a role target.

## Package import equivalent

```python
from multiomics_explorer import gene_overview

result = gene_overview(locus_tags=...)
# returns dict with keys: total_matching, by_organism, by_category, by_annotation_type, by_annotation_state, has_expression, has_significant_expression, has_orthologs, has_clusters, has_derived_metrics, has_chemistry, has_discussed, top_discussing_publications, has_ncbifam, has_tcdb, has_cazy, by_merops_class, returned, offset, truncated, not_found, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
