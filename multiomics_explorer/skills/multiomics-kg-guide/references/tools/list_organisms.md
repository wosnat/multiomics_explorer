# list_organisms

## What it does

List organisms with taxonomy, data-availability counts, organism_type, DM rollups, chemistry-capability rollups, annotation-coverage rollups, and metabolomics-coverage rollup.

Routing: feed `organism_name` into per-organism scoping on `genes_by_function`, `genes_by_ontology`, `list_publications`, `list_experiments`. Per-row drill-downs: `catalyzed_metabolite_count > 0` → `list_metabolites(organism_names=[...])`; `measured_metabolite_count > 0` → `list_metabolite_assays(organism=...)`; `derived_metric_value_kinds` → matching `genes_by_{numeric,boolean,categorical}_metric`. Read `top_annotation_capability` (top-10 by `peptidase_gene_count`, plus `interpro_gene_count` / `ncbifam_gene_count`) to see which organisms carry MEROPS / InterPro / NCBIfam coverage — then `genes_by_ontology(ontology='merops'|'interpro'|'ncbifam', organism=...)`. `organism_names=` uses the same word-based, case-insensitive match on preferred_name + name_synonyms as every other tool's organism param ('MED4' works); unknown names land in `not_found`. Two OrganismTaxon nodes share preferred_name 'Meiothermus ruber' (genome strain + gene-less treatment taxon) — both list here.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism_names | list[string] \| None | None | Filter by organism: case-insensitive word match on preferred_name and name_synonyms, like every other tool's organism param ('MED4', 'Prochlorococcus MED4'; the synonym 'Meiothermus taiwanensis' resolves to 'Meiothermus ruber'); a genus word like 'Alteromonas' matches every strain. Unknown names are reported in not_found rather than raising. Note: two OrganismTaxon nodes share preferred_name 'Meiothermus ruber' (the genome strain + a gene-less treatment taxon) — join counts by Gene_belongs_to_organism, never by name. |
| compartment | string \| None | None | Filter to organisms with at least one experiment in this wet-lab compartment (e.g. 'vesicle', 'whole_cell'). Use list_filter_values(filter_type='compartment') to enumerate valid values. |
| summary | bool | False | Return summary fields only (results=[]). |
| verbose | bool | False | Include full taxonomy hierarchy (family, order, class, phylum, kingdom, superkingdom, lineage). |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_cluster_type, by_organism_type, by_value_kind, by_metric_type, by_compartment, top_metabolic_capability, top_annotation_capability, by_measurement_capability, returned, offset, truncated, not_found, results
```

- **total_entries** (int): Total organisms in the KG.
- **total_matching** (int): Organisms matching the filter (= total_entries when no filter).
- **by_cluster_type** (list[OrgClusterTypeBreakdown]): Organism counts per cluster type over the matched set, sorted desc.
- **by_organism_type** (list[OrgTypeBreakdown]): Organism counts per type over the matched set, sorted desc.
- **by_value_kind** (list[OrgValueKindBreakdown]): DM value_kind frequency rollup across matched organisms.
- **by_metric_type** (list[OrgMetricTypeBreakdown]): DM metric_type frequency rollup across matched organisms.
- **by_compartment** (list[OrgCompartmentBreakdown]): Wet-lab compartment frequency rollup across matched organisms.
- **top_metabolic_capability** (list[OrgMetabolicCapabilityBreakdown]): Top 10 organisms by catalyzed_metabolite_count (within matched set), sorted desc. Filter excludes organisms with zero chemistry. [] when no matched organism has chemistry. Use list_metabolites(organism_names=[organism_name]) on top entries to enumerate their metabolites.
- **top_annotation_capability** (list[OrgAnnotationCapabilityBreakdown]): Top 10 organisms (within matched set) by peptidase_gene_count desc, then preferred_name. Carries all four annotation counts; excludes organisms with all four = 0. [] when none. Coverage ranking for reading, not a filter.
- **by_measurement_capability** (OrgMeasurementCapability): Binary rollup of metabolomics measurement coverage across matched organisms: {has_metabolomics, no_metabolomics} (tool-specific deviation from list_/by_-style frequency rollups elsewhere — exactly two keys).
- **returned** (int): Number of results returned.
- **offset** (int): Offset into full result set.
- **truncated** (bool): True if total_matching > offset + returned.
- **not_found** (list[string]): organism_names inputs that didn't match any organism (case-insensitive); [] when no filter.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| organism_name | string | Display name (e.g. 'Prochlorococcus MED4'). Use for organism filters in other tools. |
| organism_type | string | Classification: 'genome_strain', 'treatment', or 'reference_proteome_match'. |
| genus | string \| None (optional) | Genus (e.g. 'Prochlorococcus', 'Alteromonas'). |
| species | string \| None (optional) | Binomial species name (e.g. 'Prochlorococcus marinus'). |
| strain | string \| None (optional) | Strain identifier (e.g. 'MED4', 'EZ55'). |
| clade | string \| None (optional) | Ecotype clade, Prochlorococcus-specific (e.g. 'HLI', 'LLIV'). |
| ncbi_taxon_id | int \| None (optional) | NCBI Taxonomy ID for cross-referencing external databases. |
| gene_count | int | Number of genes in the KG for this organism. |
| publication_count | int | Number of publications studying this organism. |
| experiment_count | int | Total experiments across all publications. |
| treatment_types | list[string] (optional) | Distinct treatment types studied (e.g. ['coculture', 'nitrogen', 'light']). Live vocabulary: list_filter_values(filter_type='treatment_type') or list_experiments(summary=True). |
| background_factors | list[string] (optional) | Distinct background factors across experiments (e.g. ['axenic', 'light', 'diel']). Live vocabulary: list_experiments(summary=True). |
| omics_types | list[string] (optional) | Distinct omics types available (e.g. ['RNASEQ', 'PROTEOMICS']). |
| clustering_analysis_count | int (optional) | Number of clustering analyses for this organism. |
| cluster_types | list[string] (optional) | Distinct cluster types (e.g. ['condition_comparison', 'diel']). |
| growth_phases | list[string] (optional) | Distinct growth phases across experiments (e.g. ['exponential', 'nutrient_limited']). Timepoint-level condition, not gene-specific. |
| derived_metric_count | int (optional) | Total DerivedMetric annotations on this organism's experiments. 0 when none. |
| derived_metric_value_kinds | list[string] (optional) | Subset of {numeric, boolean, categorical} present across this organism's DMs. Use to route to genes_by_{numeric,boolean,categorical}_metric. |
| compartments | list[string] (optional) | Wet-lab compartments measured for this organism (e.g. ['whole_cell', 'vesicle']). |
| reaction_count | int (optional) | Distinct reactions catalyzed by genes in this organism. When > 0, drill in via list_metabolites(organism_names=[organism_name]). |
| catalyzed_metabolite_count | int (optional) | Distinct metabolites this organism's genes can catalyze reactions on (Gene → Reaction → Metabolite; catalysis arm only — transport-reach excluded). Does NOT mean measured. When > 0, drill in via list_metabolites(organism_names=[organism_name]). |
| transported_metabolite_count | int (optional) | Distinct metabolites this organism's genes transport via their deepest TCDB attachments (precomputed OrganismTaxon.transported_metabolite_count). Pairs with catalyzed_metabolite_count; 0 when no TCDB calls. |
| measured_metabolite_count | int (optional) | Distinct metabolites measured in this organism via any MetaboliteAssay (precomputed OrganismTaxon.measured_metabolite_count). Different from catalyzed_metabolite_count (catalysis-arm chemistry capability). When > 0, drill in via list_metabolite_assays(organism=organism_name). |
| peptidase_gene_count | int (optional) | Genes in this organism with a MEROPS 'peptidase' call (merops_classes). Precomputed OrganismTaxon.peptidase_gene_count; 0 when none. Drill in via genes_by_ontology(ontology='merops', call_class='peptidase'). |
| nonpeptidase_homolog_gene_count | int (optional) | Genes with a MEROPS 'nonpeptidase_homolog' call (a gene can carry both classes). Precomputed OrganismTaxon.nonpeptidase_homolog_gene_count; 0 when none. |
| interpro_gene_count | int (optional) | Genes with at least one InterPro entry. Precomputed OrganismTaxon.interpro_gene_count; 0 when none. Coverage count for reading, not selecting. |
| ncbifam_gene_count | int (optional) | Genes with at least one NCBIfam family. Precomputed OrganismTaxon.ncbifam_gene_count; 0 when none. Coverage count for reading, not selecting. |
| derived_metric_gene_count | int \| None (optional) | Total gene-level DM annotation count (verbose-only). |
| derived_metric_types | list[string] \| None (optional) | Distinct metric_type tags observed (verbose-only). |
| reference_database | string \| None (optional) | Reference database used for matching (e.g. 'MarRef v6'). Only on reference_proteome_match organisms. |
| reference_proteome | string \| None (optional) | Accession of matched reference proteome (e.g. 'GCA_003513035.1'). Only on reference_proteome_match organisms. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| family | string \| None (optional) | Taxonomic family (e.g. 'Prochlorococcaceae'). |
| order | string \| None (optional) | Taxonomic order (e.g. 'Synechococcales'). |
| tax_class | string \| None (optional) | Taxonomic class (e.g. 'Cyanophyceae'). |
| phylum | string \| None (optional) | Taxonomic phylum (e.g. 'Cyanobacteriota'). |
| kingdom | string \| None (optional) | Taxonomic kingdom (e.g. 'Bacillati'). |
| superkingdom | string \| None (optional) | Taxonomic superkingdom (e.g. 'Bacteria'). |
| lineage | string \| None (optional) | Full NCBI taxonomy lineage string. |
| cluster_count | int \| None (optional) | Total gene clusters across analyses (verbose-only). |

## Few-shot examples

### Example 1: Browse all organisms

```example-call
list_organisms()
```

```example-response
{
  "total_entries": 48,
  "total_matching": 48,
  "by_cluster_type": [
    {"cluster_type": "genomic_island", "count": 11},
    {"cluster_type": "time_course", "count": 3},
    {"cluster_type": "condition_comparison", "count": 3},
    {"cluster_type": "diel", "count": 2},
    {"cluster_type": "decay_pattern", "count": 1}
  ],
  "by_organism_type": [
    {"organism_type": "genome_strain", "count": 41},
    {"organism_type": "treatment", "count": 5},
    {"organism_type": "reference_proteome_match", "count": 2}
  ],
  "by_value_kind": [
    {"value_kind": "numeric", "count": 10},
    {"value_kind": "boolean", "count": 5},
    {"value_kind": "categorical", "count": 4}
  ],
  "by_metric_type": [
    {"metric_type": "log2_mv_cell_enrichment", "count": 6},
    {"metric_type": "prop_abund_cells_percent", "count": 6},
    {"metric_type": "prop_abund_mvs_percent", "count": 6},
    {"metric_type": "antisense_tss_count", "count": 2},
    {"metric_type": "has_primary_tss", "count": 2},
    ...
  ],
  "by_compartment": [
    {"compartment": "vesicle", "count": 9},
    {"compartment": "whole_cell", "count": 5},
    {"compartment": "exoproteome", "count": 2}
  ],
  "top_metabolic_capability": [
    {
      "organism_name": "Pseudomonas putida KT2440",
      "reaction_count": 1449,
      "catalyzed_metabolite_count": 1490,
      "transported_metabolite_count": 1260
    },
    {
      "organism_name": "Ruegeria pomeroyi DSS-3",
      "reaction_count": 1377,
      "catalyzed_metabolite_count": 1468,
      "transported_metabolite_count": 1213
    },
    {
      "organism_name": "Alteromonas macleodii EZ55",
      "reaction_count": 1348,
      "catalyzed_metabolite_count": 1428,
      "transported_metabolite_count": 1266
    },
    {
      "organism_name": "Alteromonas (MarRef v6)",
      "reaction_count": 1263,
      "catalyzed_metabolite_count": 1359,
      "transported_metabolite_count": 1265
    },
    {
      "organism_name": "Alteromonas macleodii MIT1002",
      "reaction_count": 1288,
      "catalyzed_metabolite_count": 1354,
      "transported_metabolite_count": 1267
    },
    ...
  ],
  "top_annotation_capability": [
    {
      "preferred_name": "Alteromonas (MarRef v6)",
      "organism_name": "Alteromonas (MarRef v6)",
      "peptidase_gene_count": 148,
      "nonpeptidase_homolog_gene_count": 31,
      "interpro_gene_count": 3746,
      "ncbifam_gene_count": 1379
    },
    {
      "preferred_name": "Alteromonas macleodii AD45",
      "organism_name": "Alteromonas macleodii AD45",
      "peptidase_gene_count": 129,
      "nonpeptidase_homolog_gene_count": 32,
      "interpro_gene_count": 3495,
      "ncbifam_gene_count": 1611
    },
    {
      "preferred_name": "Shewanella sp. W3-18-1",
      "organism_name": "Shewanella sp. W3-18-1",
      "peptidase_gene_count": 128,
      "nonpeptidase_homolog_gene_count": 23,
      "interpro_gene_count": 3636,
      "ncbifam_gene_count": 1853
    },
    {
      "preferred_name": "Alteromonas macleodii BGP6",
      "organism_name": "Alteromonas macleodii BGP6",
      "peptidase_gene_count": 127,
      "nonpeptidase_homolog_gene_count": 33,
      "interpro_gene_count": 3608,
      "ncbifam_gene_count": 1656
    },
    {
      "preferred_name": "Alteromonas macleodii ATCC27126",
      "organism_name": "Alteromonas macleodii ATCC27126",
      "peptidase_gene_count": 125,
      "nonpeptidase_homolog_gene_count": 37,
      "interpro_gene_count": 3456,
      "ncbifam_gene_count": 1598
    },
    ...
  ],
  "by_measurement_capability": {"has_metabolomics": 5, "no_metabolomics": 43},
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "not_found": [],
  "results": [
    {
      "organism_name": "Alteromonas",
      "organism_type": "treatment",
      "genus": "Alteromonas",
      "species": null,
      "strain": null,
      "clade": null,
      "ncbi_taxon_id": 28108,
      "gene_count": 0,
      "publication_count": 0,
      "experiment_count": 0,
      "treatment_types": [],
      "background_factors": [],
      "omics_types": [],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "compartments": [],
      "reaction_count": 0,
      "catalyzed_metabolite_count": 0,
      "transported_metabolite_count": 0,
      "measured_metabolite_count": 0,
      "peptidase_gene_count": 0,
      "nonpeptidase_homolog_gene_count": 0,
      "interpro_gene_count": 0,
      "ncbifam_gene_count": 0
    },
    {
      "organism_name": "Alteromonas (MarRef v6)",
      "organism_type": "reference_proteome_match",
      "genus": "Alteromonas",
      "species": null,
      "strain": "Alt_MarRef",
      "clade": null,
      "ncbi_taxon_id": 232,
      "gene_count": 4305,
      "publication_count": 1,
      "experiment_count": 60,
      "treatment_types": ["carbon", "coculture"],
      "background_factors": ["coculture", "darkness", "light"],
      "omics_types": ["PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": ["darkness", "stationary"],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "compartments": [],
      "reaction_count": 1263,
      "catalyzed_metabolite_count": 1359,
      "transported_metabolite_count": 1265,
      "measured_metabolite_count": 0,
      "peptidase_gene_count": 148,
      "nonpeptidase_homolog_gene_count": 31,
      "interpro_gene_count": 3746,
      "ncbifam_gene_count": 1379,
      "reference_database": "MarRef v6",
      "reference_proteome": "UP000262181"
    },
    {
      "organism_name": "Alteromonas macleodii AD45",
      "organism_type": "genome_strain",
      "genus": "Alteromonas",
      "species": "Alteromonas macleodii",
      "strain": "AD45",
      "clade": null,
      "ncbi_taxon_id": 1004787,
      "gene_count": 3929,
      "publication_count": 1,
      "experiment_count": 6,
      "treatment_types": ["compartment"],
      "background_factors": ["axenic", "darkness"],
      "omics_types": ["VESICLE_PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 3,
      "derived_metric_value_kinds": ["numeric"],
      "compartments": ["vesicle"],
      "reaction_count": 1259,
      "catalyzed_metabolite_count": 1328,
      "transported_metabolite_count": 1266,
      "measured_metabolite_count": 0,
      "peptidase_gene_count": 129,
      "nonpeptidase_homolog_gene_count": 32,
      "interpro_gene_count": 3495,
      "ncbifam_gene_count": 1611
    },
    ...
  ]
}
```

### Example 2: Read the annotation-capability ranking (protease and domain coverage per organism)

```example-call
list_organisms(summary=True)
```

```example-response
{
  "total_entries": 48,
  "total_matching": 48,
  "by_cluster_type": [
    {"cluster_type": "genomic_island", "count": 11},
    {"cluster_type": "time_course", "count": 3},
    {"cluster_type": "condition_comparison", "count": 3},
    {"cluster_type": "diel", "count": 2},
    {"cluster_type": "decay_pattern", "count": 1}
  ],
  "by_organism_type": [
    {"organism_type": "genome_strain", "count": 41},
    {"organism_type": "treatment", "count": 5},
    {"organism_type": "reference_proteome_match", "count": 2}
  ],
  "by_value_kind": [
    {"value_kind": "numeric", "count": 10},
    {"value_kind": "boolean", "count": 5},
    {"value_kind": "categorical", "count": 4}
  ],
  "by_metric_type": [
    {"metric_type": "log2_mv_cell_enrichment", "count": 6},
    {"metric_type": "prop_abund_cells_percent", "count": 6},
    {"metric_type": "prop_abund_mvs_percent", "count": 6},
    {"metric_type": "antisense_tss_count", "count": 2},
    {"metric_type": "has_primary_tss", "count": 2},
    ...
  ],
  "by_compartment": [
    {"compartment": "vesicle", "count": 9},
    {"compartment": "whole_cell", "count": 5},
    {"compartment": "exoproteome", "count": 2}
  ],
  "top_metabolic_capability": [
    {
      "organism_name": "Pseudomonas putida KT2440",
      "reaction_count": 1449,
      "catalyzed_metabolite_count": 1490,
      "transported_metabolite_count": 1260
    },
    {
      "organism_name": "Ruegeria pomeroyi DSS-3",
      "reaction_count": 1377,
      "catalyzed_metabolite_count": 1468,
      "transported_metabolite_count": 1213
    },
    {
      "organism_name": "Alteromonas macleodii EZ55",
      "reaction_count": 1348,
      "catalyzed_metabolite_count": 1428,
      "transported_metabolite_count": 1266
    },
    {
      "organism_name": "Alteromonas (MarRef v6)",
      "reaction_count": 1263,
      "catalyzed_metabolite_count": 1359,
      "transported_metabolite_count": 1265
    },
    {
      "organism_name": "Alteromonas macleodii MIT1002",
      "reaction_count": 1288,
      "catalyzed_metabolite_count": 1354,
      "transported_metabolite_count": 1267
    },
    ...
  ],
  "top_annotation_capability": [
    {
      "preferred_name": "Alteromonas (MarRef v6)",
      "organism_name": "Alteromonas (MarRef v6)",
      "peptidase_gene_count": 148,
      "nonpeptidase_homolog_gene_count": 31,
      "interpro_gene_count": 3746,
      "ncbifam_gene_count": 1379
    },
    {
      "preferred_name": "Alteromonas macleodii AD45",
      "organism_name": "Alteromonas macleodii AD45",
      "peptidase_gene_count": 129,
      "nonpeptidase_homolog_gene_count": 32,
      "interpro_gene_count": 3495,
      "ncbifam_gene_count": 1611
    },
    {
      "preferred_name": "Shewanella sp. W3-18-1",
      "organism_name": "Shewanella sp. W3-18-1",
      "peptidase_gene_count": 128,
      "nonpeptidase_homolog_gene_count": 23,
      "interpro_gene_count": 3636,
      "ncbifam_gene_count": 1853
    },
    {
      "preferred_name": "Alteromonas macleodii BGP6",
      "organism_name": "Alteromonas macleodii BGP6",
      "peptidase_gene_count": 127,
      "nonpeptidase_homolog_gene_count": 33,
      "interpro_gene_count": 3608,
      "ncbifam_gene_count": 1656
    },
    {
      "preferred_name": "Alteromonas macleodii ATCC27126",
      "organism_name": "Alteromonas macleodii ATCC27126",
      "peptidase_gene_count": 125,
      "nonpeptidase_homolog_gene_count": 37,
      "interpro_gene_count": 3456,
      "ncbifam_gene_count": 1598
    },
    ...
  ],
  "by_measurement_capability": {"has_metabolomics": 5, "no_metabolomics": 43},
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "not_found": [],
  "results": []
}
```

### Example 3: Compare a few named organisms' annotation coverage

```example-call
list_organisms(organism_names=["Prochlorococcus MED4", "Alteromonas macleodii MIT1002"])
```

```example-response
{
  "total_entries": 48,
  "total_matching": 2,
  "by_cluster_type": [
    {"cluster_type": "genomic_island", "count": 1},
    {"cluster_type": "decay_pattern", "count": 1},
    {"cluster_type": "diel", "count": 1},
    {"cluster_type": "time_course", "count": 1}
  ],
  "by_organism_type": [{"organism_type": "genome_strain", "count": 2}],
  "by_value_kind": [
    {"value_kind": "boolean", "count": 2},
    {"value_kind": "numeric", "count": 2},
    {"value_kind": "categorical", "count": 1}
  ],
  "by_metric_type": [
    {"metric_type": "antisense_tss_count", "count": 1},
    {"metric_type": "damping_ratio", "count": 1},
    {"metric_type": "diel_amplitude_protein_log2", "count": 1},
    {"metric_type": "diel_amplitude_transcript_log2", "count": 1},
    {"metric_type": "expressed_above_background", "count": 1},
    ...
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 2}, {"compartment": "whole_cell", "count": 2}],
  "top_metabolic_capability": [
    {
      "organism_name": "Alteromonas macleodii MIT1002",
      "reaction_count": 1288,
      "catalyzed_metabolite_count": 1354,
      "transported_metabolite_count": 1267
    },
    {
      "organism_name": "Prochlorococcus MED4",
      "reaction_count": 943,
      "catalyzed_metabolite_count": 1039,
      "transported_metabolite_count": 1069
    }
  ],
  "top_annotation_capability": [
    {
      "preferred_name": "Alteromonas macleodii MIT1002",
      "organism_name": "Alteromonas macleodii MIT1002",
      "peptidase_gene_count": 120,
      "nonpeptidase_homolog_gene_count": 32,
      "interpro_gene_count": 3584,
      "ncbifam_gene_count": 1699
    },
    {
      "preferred_name": "Prochlorococcus MED4",
      "organism_name": "Prochlorococcus MED4",
      "peptidase_gene_count": 50,
      "nonpeptidase_homolog_gene_count": 8,
      "interpro_gene_count": 1545,
      "ncbifam_gene_count": 744
    }
  ],
  "by_measurement_capability": {"has_metabolomics": 0, "no_metabolomics": 2},
  "returned": 2,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "results": [
    {
      "organism_name": "Alteromonas macleodii MIT1002",
      "organism_type": "genome_strain",
      "genus": "Alteromonas",
      "species": "Alteromonas macleodii",
      "strain": "MIT1002",
      "clade": null,
      "ncbi_taxon_id": 28108,
      "gene_count": 4028,
      "publication_count": 4,
      "experiment_count": 14,
      "treatment_types": ["coculture", "growth_phase", "darkness", "compartment"],
      "background_factors": ["coculture", "light", "axenic", "diel", "darkness"],
      "omics_types": ["RNASEQ", "VESICLE_PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": ["exponential", "darkness", "diel"],
      "derived_metric_count": 5,
      "derived_metric_value_kinds": ["boolean", "numeric"],
      "compartments": ["vesicle", "whole_cell"],
      "reaction_count": 1288,
      "catalyzed_metabolite_count": 1354,
      "transported_metabolite_count": 1267,
      "measured_metabolite_count": 0,
      "peptidase_gene_count": 120,
      "nonpeptidase_homolog_gene_count": 32,
      "interpro_gene_count": 3584,
      "ncbifam_gene_count": 1699
    },
    {
      "organism_name": "Prochlorococcus MED4",
      "organism_type": "genome_strain",
      "genus": "Prochlorococcus",
      "species": "Prochlorococcus marinus",
      "strain": "MED4",
      "clade": "HLI",
      "ncbi_taxon_id": 59919,
      "gene_count": 1973,
      "publication_count": 20,
      "experiment_count": 119,
      "treatment_types": ["coculture", "carbon", "compartment", "salt", "viral", ...],
      "background_factors": ["light", "axenic", "chemical", "darkness", "viral", ...],
      "omics_types": ["RNASEQ", "MICROARRAY", "VESICLE_DNASEQ", "VESICLE_PROTEOMICS", "PROTEOMICS", ...],
      "clustering_analysis_count": 6,
      "cluster_types": ["genomic_island", "decay_pattern", "diel", "time_course"],
      "growth_phases": ["exponential", "acute_stress", "acclimated_steady_state", "infected", "nutrient_limited", ...],
      "derived_metric_count": 26,
      "derived_metric_value_kinds": ["boolean", "categorical", "numeric"],
      "compartments": ["vesicle", "whole_cell"],
      "reaction_count": 943,
      "catalyzed_metabolite_count": 1039,
      "transported_metabolite_count": 1069,
      "measured_metabolite_count": 0,
      "peptidase_gene_count": 50,
      "nonpeptidase_homolog_gene_count": 8,
      "interpro_gene_count": 1545,
      "ncbifam_gene_count": 744
    }
  ]
}
```

### Example 4: Full taxonomy

```example-call
list_organisms(verbose=True)
```

### Example 5: Look up specific organisms by name

```example-call
list_organisms(organism_names=["Prochlorococcus MED4", "Prochlorococcus MIT9301", "Bogus organism"])
```

```example-response
{
  "total_entries": 48,
  "total_matching": 2,
  "by_cluster_type": [
    {"cluster_type": "genomic_island", "count": 2},
    {"cluster_type": "decay_pattern", "count": 1},
    {"cluster_type": "diel", "count": 1},
    {"cluster_type": "time_course", "count": 1},
    {"cluster_type": "condition_comparison", "count": 1}
  ],
  "by_organism_type": [{"organism_type": "genome_strain", "count": 2}],
  "by_value_kind": [
    {"value_kind": "boolean", "count": 1},
    {"value_kind": "categorical", "count": 1},
    {"value_kind": "numeric", "count": 1}
  ],
  "by_metric_type": [
    {"metric_type": "antisense_tss_count", "count": 1},
    {"metric_type": "damping_ratio", "count": 1},
    {"metric_type": "diel_amplitude_protein_log2", "count": 1},
    {"metric_type": "diel_amplitude_transcript_log2", "count": 1},
    {"metric_type": "expressed_above_background", "count": 1},
    ...
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 1}, {"compartment": "whole_cell", "count": 1}],
  "top_metabolic_capability": [
    {
      "organism_name": "Prochlorococcus MIT9301",
      "reaction_count": 945,
      "catalyzed_metabolite_count": 1052,
      "transported_metabolite_count": 1061
    },
    {
      "organism_name": "Prochlorococcus MED4",
      "reaction_count": 943,
      "catalyzed_metabolite_count": 1039,
      "transported_metabolite_count": 1069
    }
  ],
  "top_annotation_capability": [
    {
      "preferred_name": "Prochlorococcus MED4",
      "organism_name": "Prochlorococcus MED4",
      "peptidase_gene_count": 50,
      "nonpeptidase_homolog_gene_count": 8,
      "interpro_gene_count": 1545,
      "ncbifam_gene_count": 744
    },
    {
      "preferred_name": "Prochlorococcus MIT9301",
      "organism_name": "Prochlorococcus MIT9301",
      "peptidase_gene_count": 49,
      "nonpeptidase_homolog_gene_count": 10,
      "interpro_gene_count": 1537,
      "ncbifam_gene_count": 774
    }
  ],
  "by_measurement_capability": {"has_metabolomics": 1, "no_metabolomics": 1},
  "returned": 2,
  "offset": 0,
  "truncated": false,
  "not_found": ["Bogus organism"],
  "results": [
    {
      "organism_name": "Prochlorococcus MED4",
      "organism_type": "genome_strain",
      "genus": "Prochlorococcus",
      "species": "Prochlorococcus marinus",
      "strain": "MED4",
      "clade": "HLI",
      "ncbi_taxon_id": 59919,
      "gene_count": 1973,
      "publication_count": 20,
      "experiment_count": 119,
      "treatment_types": ["coculture", "carbon", "compartment", "salt", "viral", ...],
      "background_factors": ["light", "axenic", "chemical", "darkness", "viral", ...],
      "omics_types": ["RNASEQ", "MICROARRAY", "VESICLE_DNASEQ", "VESICLE_PROTEOMICS", "PROTEOMICS", ...],
      "clustering_analysis_count": 6,
      "cluster_types": ["genomic_island", "decay_pattern", "diel", "time_course"],
      "growth_phases": ["exponential", "acute_stress", "acclimated_steady_state", "infected", "nutrient_limited", ...],
      "derived_metric_count": 26,
      "derived_metric_value_kinds": ["boolean", "categorical", "numeric"],
      "compartments": ["vesicle", "whole_cell"],
      "reaction_count": 943,
      "catalyzed_metabolite_count": 1039,
      "transported_metabolite_count": 1069,
      "measured_metabolite_count": 0,
      "peptidase_gene_count": 50,
      "nonpeptidase_homolog_gene_count": 8,
      "interpro_gene_count": 1545,
      "ncbifam_gene_count": 744
    },
    {
      "organism_name": "Prochlorococcus MIT9301",
      "organism_type": "genome_strain",
      "genus": "Prochlorococcus",
      "species": "Prochlorococcus marinus",
      "strain": "MIT9301",
      "clade": "HLII",
      "ncbi_taxon_id": 167546,
      "gene_count": 1926,
      "publication_count": 3,
      "experiment_count": 8,
      "treatment_types": ["growth_phase", "temperature", "phosphorus"],
      "background_factors": ["axenic", "light", "diel"],
      "omics_types": ["RNASEQ", "METABOLOMICS"],
      "clustering_analysis_count": 2,
      "cluster_types": ["genomic_island", "condition_comparison"],
      "growth_phases": ["exponential"],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "compartments": [],
      "reaction_count": 945,
      "catalyzed_metabolite_count": 1052,
      "transported_metabolite_count": 1061,
      "measured_metabolite_count": 99,
      "peptidase_gene_count": 49,
      "nonpeptidase_homolog_gene_count": 10,
      "interpro_gene_count": 1537,
      "ncbifam_gene_count": 774
    }
  ]
}
```

### Example 6: Chaining to genes and publications

```
Step 1: list_organisms()
        → discover available organisms and data coverage

Step 2: genes_by_function(search_text="photosystem", organism="MED4")
        → search genes within a specific organism

Step 3: list_publications(organism="MED4")
        → find publications studying that organism
```

### Example 7: Find organisms with vesicle-fraction DM evidence

```example-call
list_organisms(compartment="vesicle")
```

```example-response
{
  "total_entries": 48,
  "total_matching": 9,
  "by_cluster_type": [
    {"cluster_type": "genomic_island", "count": 3},
    {"cluster_type": "time_course", "count": 2},
    {"cluster_type": "decay_pattern", "count": 1},
    {"cluster_type": "diel", "count": 1}
  ],
  "by_organism_type": [{"organism_type": "genome_strain", "count": 9}],
  "by_value_kind": [
    {"value_kind": "numeric", "count": 9},
    {"value_kind": "boolean", "count": 3},
    {"value_kind": "categorical", "count": 2}
  ],
  "by_metric_type": [
    {"metric_type": "log2_mv_cell_enrichment", "count": 6},
    {"metric_type": "prop_abund_cells_percent", "count": 6},
    {"metric_type": "prop_abund_mvs_percent", "count": 6},
    {"metric_type": "antisense_tss_count", "count": 2},
    {"metric_type": "has_primary_tss", "count": 2},
    ...
  ],
  "by_compartment": [{"compartment": "vesicle", "count": 9}, {"compartment": "whole_cell", "count": 3}],
  "top_metabolic_capability": [
    {
      "organism_name": "Alteromonas macleodii MIT1002",
      "reaction_count": 1288,
      "catalyzed_metabolite_count": 1354,
      "transported_metabolite_count": 1267
    },
    {
      "organism_name": "Alteromonas macleodii BGP6",
      "reaction_count": 1275,
      "catalyzed_metabolite_count": 1341,
      "transported_metabolite_count": 1269
    },
    {
      "organism_name": "Alteromonas macleodii HOT1A3",
      "reaction_count": 1266,
      "catalyzed_metabolite_count": 1336,
      "transported_metabolite_count": 1269
    },
    {
      "organism_name": "Alteromonas macleodii AD45",
      "reaction_count": 1259,
      "catalyzed_metabolite_count": 1328,
      "transported_metabolite_count": 1266
    },
    {
      "organism_name": "Alteromonas macleodii ATCC27126",
      "reaction_count": 1251,
      "catalyzed_metabolite_count": 1309,
      "transported_metabolite_count": 1267
    },
    ...
  ],
  "top_annotation_capability": [
    {
      "preferred_name": "Alteromonas macleodii AD45",
      "organism_name": "Alteromonas macleodii AD45",
      "peptidase_gene_count": 129,
      "nonpeptidase_homolog_gene_count": 32,
      "interpro_gene_count": 3495,
      "ncbifam_gene_count": 1611
    },
    {
      "preferred_name": "Alteromonas macleodii BGP6",
      "organism_name": "Alteromonas macleodii BGP6",
      "peptidase_gene_count": 127,
      "nonpeptidase_homolog_gene_count": 33,
      "interpro_gene_count": 3608,
      "ncbifam_gene_count": 1656
    },
    {
      "preferred_name": "Alteromonas macleodii ATCC27126",
      "organism_name": "Alteromonas macleodii ATCC27126",
      "peptidase_gene_count": 125,
      "nonpeptidase_homolog_gene_count": 37,
      "interpro_gene_count": 3456,
      "ncbifam_gene_count": 1598
    },
    {
      "preferred_name": "Alteromonas macleodii BS11",
      "organism_name": "Alteromonas macleodii BS11",
      "peptidase_gene_count": 123,
      "nonpeptidase_homolog_gene_count": 29,
      "interpro_gene_count": 3349,
      "ncbifam_gene_count": 1577
    },
    {
      "preferred_name": "Alteromonas macleodii MIT1002",
      "organism_name": "Alteromonas macleodii MIT1002",
      "peptidase_gene_count": 120,
      "nonpeptidase_homolog_gene_count": 32,
      "interpro_gene_count": 3584,
      "ncbifam_gene_count": 1699
    },
    ...
  ],
  "by_measurement_capability": {"has_metabolomics": 2, "no_metabolomics": 7},
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "not_found": [],
  "results": [
    {
      "organism_name": "Alteromonas macleodii AD45",
      "organism_type": "genome_strain",
      "genus": "Alteromonas",
      "species": "Alteromonas macleodii",
      "strain": "AD45",
      "clade": null,
      "ncbi_taxon_id": 1004787,
      "gene_count": 3929,
      "publication_count": 1,
      "experiment_count": 6,
      "treatment_types": ["compartment"],
      "background_factors": ["axenic", "darkness"],
      "omics_types": ["VESICLE_PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 3,
      "derived_metric_value_kinds": ["numeric"],
      "compartments": ["vesicle"],
      "reaction_count": 1259,
      "catalyzed_metabolite_count": 1328,
      "transported_metabolite_count": 1266,
      "measured_metabolite_count": 0,
      "peptidase_gene_count": 129,
      "nonpeptidase_homolog_gene_count": 32,
      "interpro_gene_count": 3495,
      "ncbifam_gene_count": 1611
    },
    {
      "organism_name": "Alteromonas macleodii ATCC27126",
      "organism_type": "genome_strain",
      "genus": "Alteromonas",
      "species": "Alteromonas macleodii",
      "strain": "ATCC27126",
      "clade": null,
      "ncbi_taxon_id": 529120,
      "gene_count": 3834,
      "publication_count": 1,
      "experiment_count": 6,
      "treatment_types": ["compartment"],
      "background_factors": ["axenic", "darkness"],
      "omics_types": ["VESICLE_PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 3,
      "derived_metric_value_kinds": ["numeric"],
      "compartments": ["vesicle"],
      "reaction_count": 1251,
      "catalyzed_metabolite_count": 1309,
      "transported_metabolite_count": 1267,
      "measured_metabolite_count": 0,
      "peptidase_gene_count": 125,
      "nonpeptidase_homolog_gene_count": 37,
      "interpro_gene_count": 3456,
      "ncbifam_gene_count": 1598
    },
    {
      "organism_name": "Alteromonas macleodii BGP6",
      "organism_type": "genome_strain",
      "genus": "Alteromonas",
      "species": "Alteromonas macleodii",
      "strain": "BGP6",
      "clade": null,
      "ncbi_taxon_id": 28108,
      "gene_count": 4063,
      "publication_count": 1,
      "experiment_count": 6,
      "treatment_types": ["compartment"],
      "background_factors": ["axenic", "darkness"],
      "omics_types": ["VESICLE_PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 3,
      "derived_metric_value_kinds": ["numeric"],
      "compartments": ["vesicle"],
      "reaction_count": 1275,
      "catalyzed_metabolite_count": 1341,
      "transported_metabolite_count": 1269,
      "measured_metabolite_count": 0,
      "peptidase_gene_count": 127,
      "nonpeptidase_homolog_gene_count": 33,
      "interpro_gene_count": 3608,
      "ncbifam_gene_count": 1656
    },
    ...
  ]
}
```

### Example 8: Identify chemistry-rich organisms (capability ranking)

```example-call
list_organisms(summary=True)
```

```example-response
{
  "total_entries": 48,
  "total_matching": 48,
  "by_cluster_type": [
    {"cluster_type": "genomic_island", "count": 11},
    {"cluster_type": "time_course", "count": 3},
    {"cluster_type": "condition_comparison", "count": 3},
    {"cluster_type": "diel", "count": 2},
    {"cluster_type": "decay_pattern", "count": 1}
  ],
  "by_organism_type": [
    {"organism_type": "genome_strain", "count": 41},
    {"organism_type": "treatment", "count": 5},
    {"organism_type": "reference_proteome_match", "count": 2}
  ],
  "by_value_kind": [
    {"value_kind": "numeric", "count": 10},
    {"value_kind": "boolean", "count": 5},
    {"value_kind": "categorical", "count": 4}
  ],
  "by_metric_type": [
    {"metric_type": "log2_mv_cell_enrichment", "count": 6},
    {"metric_type": "prop_abund_cells_percent", "count": 6},
    {"metric_type": "prop_abund_mvs_percent", "count": 6},
    {"metric_type": "antisense_tss_count", "count": 2},
    {"metric_type": "has_primary_tss", "count": 2},
    ...
  ],
  "by_compartment": [
    {"compartment": "vesicle", "count": 9},
    {"compartment": "whole_cell", "count": 5},
    {"compartment": "exoproteome", "count": 2}
  ],
  "top_metabolic_capability": [
    {
      "organism_name": "Pseudomonas putida KT2440",
      "reaction_count": 1449,
      "catalyzed_metabolite_count": 1490,
      "transported_metabolite_count": 1260
    },
    {
      "organism_name": "Ruegeria pomeroyi DSS-3",
      "reaction_count": 1377,
      "catalyzed_metabolite_count": 1468,
      "transported_metabolite_count": 1213
    },
    {
      "organism_name": "Alteromonas macleodii EZ55",
      "reaction_count": 1348,
      "catalyzed_metabolite_count": 1428,
      "transported_metabolite_count": 1266
    },
    {
      "organism_name": "Alteromonas (MarRef v6)",
      "reaction_count": 1263,
      "catalyzed_metabolite_count": 1359,
      "transported_metabolite_count": 1265
    },
    {
      "organism_name": "Alteromonas macleodii MIT1002",
      "reaction_count": 1288,
      "catalyzed_metabolite_count": 1354,
      "transported_metabolite_count": 1267
    },
    ...
  ],
  "top_annotation_capability": [
    {
      "preferred_name": "Alteromonas (MarRef v6)",
      "organism_name": "Alteromonas (MarRef v6)",
      "peptidase_gene_count": 148,
      "nonpeptidase_homolog_gene_count": 31,
      "interpro_gene_count": 3746,
      "ncbifam_gene_count": 1379
    },
    {
      "preferred_name": "Alteromonas macleodii AD45",
      "organism_name": "Alteromonas macleodii AD45",
      "peptidase_gene_count": 129,
      "nonpeptidase_homolog_gene_count": 32,
      "interpro_gene_count": 3495,
      "ncbifam_gene_count": 1611
    },
    {
      "preferred_name": "Shewanella sp. W3-18-1",
      "organism_name": "Shewanella sp. W3-18-1",
      "peptidase_gene_count": 128,
      "nonpeptidase_homolog_gene_count": 23,
      "interpro_gene_count": 3636,
      "ncbifam_gene_count": 1853
    },
    {
      "preferred_name": "Alteromonas macleodii BGP6",
      "organism_name": "Alteromonas macleodii BGP6",
      "peptidase_gene_count": 127,
      "nonpeptidase_homolog_gene_count": 33,
      "interpro_gene_count": 3608,
      "ncbifam_gene_count": 1656
    },
    {
      "preferred_name": "Alteromonas macleodii ATCC27126",
      "organism_name": "Alteromonas macleodii ATCC27126",
      "peptidase_gene_count": 125,
      "nonpeptidase_homolog_gene_count": 37,
      "interpro_gene_count": 3456,
      "ncbifam_gene_count": 1598
    },
    ...
  ],
  "by_measurement_capability": {"has_metabolomics": 5, "no_metabolomics": 43},
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "not_found": [],
  "results": []
}
```

### Example 9: Survey measurement coverage across organisms

```example-call
list_organisms(summary=True)
```

```example-response
{
  "total_entries": 48,
  "total_matching": 48,
  "by_cluster_type": [
    {"cluster_type": "genomic_island", "count": 11},
    {"cluster_type": "time_course", "count": 3},
    {"cluster_type": "condition_comparison", "count": 3},
    {"cluster_type": "diel", "count": 2},
    {"cluster_type": "decay_pattern", "count": 1}
  ],
  "by_organism_type": [
    {"organism_type": "genome_strain", "count": 41},
    {"organism_type": "treatment", "count": 5},
    {"organism_type": "reference_proteome_match", "count": 2}
  ],
  "by_value_kind": [
    {"value_kind": "numeric", "count": 10},
    {"value_kind": "boolean", "count": 5},
    {"value_kind": "categorical", "count": 4}
  ],
  "by_metric_type": [
    {"metric_type": "log2_mv_cell_enrichment", "count": 6},
    {"metric_type": "prop_abund_cells_percent", "count": 6},
    {"metric_type": "prop_abund_mvs_percent", "count": 6},
    {"metric_type": "antisense_tss_count", "count": 2},
    {"metric_type": "has_primary_tss", "count": 2},
    ...
  ],
  "by_compartment": [
    {"compartment": "vesicle", "count": 9},
    {"compartment": "whole_cell", "count": 5},
    {"compartment": "exoproteome", "count": 2}
  ],
  "top_metabolic_capability": [
    {
      "organism_name": "Pseudomonas putida KT2440",
      "reaction_count": 1449,
      "catalyzed_metabolite_count": 1490,
      "transported_metabolite_count": 1260
    },
    {
      "organism_name": "Ruegeria pomeroyi DSS-3",
      "reaction_count": 1377,
      "catalyzed_metabolite_count": 1468,
      "transported_metabolite_count": 1213
    },
    {
      "organism_name": "Alteromonas macleodii EZ55",
      "reaction_count": 1348,
      "catalyzed_metabolite_count": 1428,
      "transported_metabolite_count": 1266
    },
    {
      "organism_name": "Alteromonas (MarRef v6)",
      "reaction_count": 1263,
      "catalyzed_metabolite_count": 1359,
      "transported_metabolite_count": 1265
    },
    {
      "organism_name": "Alteromonas macleodii MIT1002",
      "reaction_count": 1288,
      "catalyzed_metabolite_count": 1354,
      "transported_metabolite_count": 1267
    },
    ...
  ],
  "top_annotation_capability": [
    {
      "preferred_name": "Alteromonas (MarRef v6)",
      "organism_name": "Alteromonas (MarRef v6)",
      "peptidase_gene_count": 148,
      "nonpeptidase_homolog_gene_count": 31,
      "interpro_gene_count": 3746,
      "ncbifam_gene_count": 1379
    },
    {
      "preferred_name": "Alteromonas macleodii AD45",
      "organism_name": "Alteromonas macleodii AD45",
      "peptidase_gene_count": 129,
      "nonpeptidase_homolog_gene_count": 32,
      "interpro_gene_count": 3495,
      "ncbifam_gene_count": 1611
    },
    {
      "preferred_name": "Shewanella sp. W3-18-1",
      "organism_name": "Shewanella sp. W3-18-1",
      "peptidase_gene_count": 128,
      "nonpeptidase_homolog_gene_count": 23,
      "interpro_gene_count": 3636,
      "ncbifam_gene_count": 1853
    },
    {
      "preferred_name": "Alteromonas macleodii BGP6",
      "organism_name": "Alteromonas macleodii BGP6",
      "peptidase_gene_count": 127,
      "nonpeptidase_homolog_gene_count": 33,
      "interpro_gene_count": 3608,
      "ncbifam_gene_count": 1656
    },
    {
      "preferred_name": "Alteromonas macleodii ATCC27126",
      "organism_name": "Alteromonas macleodii ATCC27126",
      "peptidase_gene_count": 125,
      "nonpeptidase_homolog_gene_count": 37,
      "interpro_gene_count": 3456,
      "ncbifam_gene_count": 1598
    },
    ...
  ],
  "by_measurement_capability": {"has_metabolomics": 5, "no_metabolomics": 43},
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "not_found": [],
  "results": []
}
```

## Chaining patterns

```
list_organisms → genes_by_function
list_organisms → list_publications
list_organisms → resolve_gene
list_organisms → genes_by_ontology
list_organisms → list_clustering_analyses(organism=...)
list_organisms(compartment=...) → use derived_metric_value_kinds per result row to route to genes_by_{boolean,numeric,categorical}_metric
list_organisms (per-row catalyzed_metabolite_count > 0) → list_metabolites(organism_names=[organism_name]) for chemistry drill-down
list_organisms(summary=True) → top_annotation_capability → genes_by_ontology(ontology='merops', organism=..., call_class=['peptidase']) for the peptidase genes behind peptidase_gene_count
list_organisms → per-row interpro_gene_count / ncbifam_gene_count → ontology_landscape(organism=..., ontology=['interpro', 'ncbifam']) before enrichment on a domain ontology
```

## Common mistakes

- If a result row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric. Empty derived_metric_value_kinds means no DM evidence on this organism.

- gene_count and publication_count are counts of data in the KG, not biological totals.

- Organisms with gene_count=0 are parent/umbrella taxonomy nodes (e.g. genus-level 'Alteromonas').

- reference_database and reference_proteome are sparse — only present on reference_proteome_match organisms, absent from others.

- organism_type values: 'genome_strain' (real genome assembly), 'treatment' (non-genomic coculture partners), 'reference_proteome_match' (identified via reference database matching).

- `catalyzed_metabolite_count` counts catalysis capability only — distinct metabolites reachable through Gene → Reaction → Metabolite. Transport reach is the separate `transported_metabolite_count` (distinct metabolites through Gene → TcdbFamily → Metabolite over each gene's deepest TCDB attachments; breadth, not a confidence signal — inherited superfamily substrates count). Measurement-side coverage is `measured_metabolite_count`. catalyzed_metabolite_count=0 means no catalysis path in this organism, not that chemistry is absent from the KG.

- top_metabolic_capability is a top-10 ranking sorted by catalyzed_metabolite_count descending (transported_metabolite_count is carried as a column, not a sort key); organisms with zero chemistry are excluded. Use it on summary=True calls to identify chemistry-rich organisms before drilling in via list_metabolites(organism_names=[...]).

- by_measurement_capability is a binary rollup ({has_metabolomics, no_metabolomics}) — tool-specific shape that deviates from the list[{key,count}] frequency rollups elsewhere. See docs://guide/conventions for the standard envelope shape.

- The four annotation-coverage counts (`peptidase_gene_count`, `nonpeptidase_homolog_gene_count`, `interpro_gene_count`, `ncbifam_gene_count`) are distinct-gene counts per organism, zero-filled (never null). A gene carrying both a `peptidase` and a `nonpeptidase_homolog` MEROPS call counts once in each. They measure coverage, not annotation quality, and scale with genome size — rank Prochlorococcus strains against each other, not against a 4,000-gene heterotroph.

- `top_annotation_capability` is a top-10 ranking of the matched set by `peptidase_gene_count` descending, then `preferred_name`; the other three counts are carried as columns, not sort keys. All-zero rows are excluded from the ranking but still appear in `results`. There is no min-count filter — read the ranking, then drill in with genes_by_ontology(ontology='merops', call_class=['peptidase'], organism=...).

- Two OrganismTaxon nodes can share a `preferred_name` (the Meiothermus ruber genome strain and the gene-less Meiothermus ruber treatment taxon). Their rows differ in `organism_type` and `gene_count`; the treatment taxon reads 0 on every coverage count. When you need a strain, pick the `genome_strain` row.

## Package import equivalent

```python
from multiomics_explorer import list_organisms

result = list_organisms()
# returns dict with keys: total_entries, total_matching, by_cluster_type, by_organism_type, by_value_kind, by_metric_type, by_compartment, top_metabolic_capability, top_annotation_capability, by_measurement_capability, returned, offset, truncated, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
