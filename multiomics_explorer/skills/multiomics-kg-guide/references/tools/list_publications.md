# list_publications

## What it does

List publications with experiment summaries, DM rollups, and metabolomics rollups. Use as the discovery entry point for studies.

Routing: drill via `list_experiments(publication_doi=[doi])` for per-experiment detail; `list_clustering_analyses(publication_doi=[doi])` for clustering; `list_derived_metrics(publication_doi=[doi])` for non-DE evidence; `list_metabolite_assays(publication_doi=[doi])` when `metabolite_count > 0`. Per-row `derived_metric_value_kinds` routes to `genes_by_{numeric,boolean,categorical}_metric`.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism | string \| None | None | Filter by organism name (case-insensitive). E.g. 'MED4', 'HOT1A3'. |
| treatment_type | string \| None | None | Filter by experiment treatment type. Use list_filter_values for valid values. |
| background_factors | string \| None | None | Filter by background factor (case-insensitive exact match). E.g. 'axenic'. |
| growth_phases | string \| None | None | Filter by growth phase (case-insensitive). E.g. 'exponential', 'nutrient_limited'. |
| search_text | string \| None | None | Free-text search on title, abstract, and description (Lucene syntax). E.g. 'nitrogen', 'co-culture AND phage'. |
| author | string \| None | None | Filter by author name (case-insensitive). E.g. 'Sher', 'Chisholm'. |
| publication_dois | list[string] \| None | None | Restrict to specific publications by DOI (case-insensitive). Combines with other filters via AND. `not_found` in the response lists any provided DOIs that did not match. Mirrors the filter shape on sibling list_* tools (list_experiments.experiment_ids). |
| compartment | string \| None | None | Filter to publications with at least one experiment in this wet-lab compartment (e.g. 'vesicle', 'whole_cell'). Use list_filter_values(filter_type='compartment') to enumerate valid values. |
| verbose | bool | False | Include abstract and description. Default compact for routing. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |
| summary | bool | False | Envelope only: results=[], every by_* rollup uncapped. Use first, then narrow filters. |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_organism, by_treatment_type, by_background_factors, by_omics_type, by_cluster_type, by_value_kind, by_metric_type, by_compartment, by_discusses_coverage, returned, offset, truncated, not_found, warnings, results
```

- **total_entries** (int): Total publications in KG (unfiltered).
- **total_matching** (int): Publications matching filters.
- **by_organism** (list[PubOrganismBreakdown]): Publication counts per organism, sorted desc.
- **by_organism_truncated** (bool | None): True when the list was capped at 10 on a detail call — pass summary=True for the full breakdown.
- **by_treatment_type** (list[PubTreatmentTypeBreakdown]): Publication counts per treatment type, sorted desc.
- **by_background_factors** (list[PubBackgroundFactorBreakdown]): Publication counts per background factor, sorted desc.
- **by_omics_type** (list[PubOmicsTypeBreakdown]): Publication counts per omics platform, sorted desc.
- **by_cluster_type** (list[PubClusterTypeBreakdown]): Publication counts per cluster type, sorted desc.
- **by_value_kind** (list[PubValueKindBreakdown]): DerivedMetric value kind frequency rollup across matched publications.
- **by_metric_type** (list[PubMetricTypeBreakdown]): DerivedMetric type frequency rollup across matched publications.
- **by_metric_type_truncated** (bool | None): True when the list was capped at 10 on a detail call — pass summary=True for the full breakdown.
- **by_compartment** (list[PubCompartmentBreakdown]): Wet-lab compartment frequency rollup across matched publications.
- **by_discusses_coverage** (PubDiscussesCoverageBreakdown): Binary split {has_discusses, no_discusses} of matched publications by whether they carry a narrative 'discusses' literature index (45 vs 4 in the current KG).
- **returned** (int): Publications in this response (0 when summary=True).
- **offset** (int): Offset into full result set.
- **truncated** (bool): True if total_matching > returned.
- **not_found** (list[string]): Input publication_dois that did not match any Publication node (empty unless publication_dois was provided).
- **warnings** (list[string]): A closed-vocabulary filter value (treatment_type / background_factors / growth_phases / compartment) not found in the live vocabulary (see list_filter_values), or an organism that matches no OrganismTaxon. Advisory only — never changes which rows are returned. Empty when clean.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| doi | string | Publication DOI (e.g. '10.1038/s41396-022-01202-1'). |
| title | string | Publication title. |
| authors | list[string] | Author list (free-text, semicolon- or comma-delimited). |
| year | int | Publication year (e.g. 2022). |
| journal | string \| None (optional) | Journal name (e.g. 'The ISME Journal'). |
| study_type | string \| None (optional) | Study type tag (e.g. 'metabolomics', 'transcriptomics'). |
| organisms | list[string] (optional) | Organisms studied in this publication. |
| experiment_count | int (optional) | Number of experiments in KG from this publication. |
| treatment_types | list[string] (optional) | Experiment treatment types (e.g. coculture, nitrogen). Live vocabulary: list_filter_values(filter_type='treatment_type') or list_experiments(summary=True). |
| background_factors | list[string] (optional) | Distinct background factors across experiments (e.g. ['axenic', 'diel']). |
| omics_types | list[string] (optional) | Omics data types (e.g. RNASEQ, PROTEOMICS). |
| clustering_analysis_count | int (optional) | Number of clustering analyses from this publication. |
| cluster_types | list[string] (optional) | Distinct cluster types (e.g. ['condition_comparison']). |
| growth_phases | list[string] (optional) | Distinct growth phases across experiments. Timepoint-level condition, not gene-specific. |
| derived_metric_count | int (optional) | Number of DerivedMetric nodes from this publication. |
| derived_metric_value_kinds | list[string] (optional) | Value kinds of DerivedMetrics in this publication (subset of {numeric, boolean, categorical}). Use to route to genes_by_{kind}_metric. |
| compartments | list[string] (optional) | Wet-lab compartments measured in this publication (e.g. ['whole_cell', 'vesicle']). |
| metabolite_count | int (optional) | Distinct metabolites measured in this publication (precomputed Publication.metabolite_count). Non-zero on metabolomics-bearing papers. When > 0, drill via list_metabolite_assays(publication_doi=[...]) to inspect the paper's MetaboliteAssay nodes. |
| metabolite_assay_count | int (optional) | Distinct MetaboliteAssay edges anchored to this publication (precomputed). Diverges from metabolite_count when the same metabolite is measured in multiple compartments per paper. |
| metabolite_compartments | list[string] (optional) | Wet-lab compartments measured for metabolomics in this publication (e.g. ['whole_cell', 'extracellular']). Populated only when metabolite_assay_count > 0; [] otherwise. |
| discussed_gene_count | int (optional) | Distinct genes this publication discusses in prose (precomputed Publication.discussed_gene_count). Recall-biased narrative index, NOT DE-table expression. When > 0, drill via discussed_by_publication(publication_dois=[doi]). |
| discussed_pathway_count | int (optional) | Distinct KEGG pathways this publication discusses in prose (precomputed Publication.discussed_pathway_count). When > 0, drill via discussed_by_publication(publication_dois=[doi], entity_kind='kegg_pathway'). |
| score | float \| None (optional) | Lucene relevance score (only with search_text). |
| derived_metric_gene_count | int \| None (optional) | Total genes annotated by DerivedMetrics in this publication (verbose-only). |
| derived_metric_types | list[string] \| None (optional) | Distinct DerivedMetric types in this publication (verbose-only). |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| abstract | string \| None (optional) | Publication abstract (verbose-only). |
| description | string \| None (optional) | Curated study description (verbose-only). |
| cluster_count | int \| None (optional) | Total gene clusters across analyses (verbose-only). |

## Few-shot examples

### Example 1: Browse all studies

```example-call
list_publications()
```

```example-response
{
  "total_entries": 49,
  "total_matching": 49,
  "by_organism": [
    {"organism_name": "Prochlorococcus MED4", "count": 20},
    {"organism_name": "Prochlorococcus MIT9313", "count": 10},
    {"organism_name": "Prochlorococcus NATL2A", "count": 6},
    {"organism_name": "Synechococcus WH7803", "count": 6},
    {"organism_name": "Prochlorococcus MIT9312", "count": 5},
    ...
  ],
  "by_organism_truncated": true,
  "by_treatment_type": [
    {"treatment_type": "coculture", "count": 12},
    {"treatment_type": "carbon", "count": 6},
    {"treatment_type": "light", "count": 6},
    {"treatment_type": "viral", "count": 5},
    {"treatment_type": "growth_phase", "count": 4},
    ...
  ],
  "by_background_factors": [
    {"background_factor": "light", "count": 33},
    {"background_factor": "axenic", "count": 33},
    {"background_factor": "diel", "count": 9},
    {"background_factor": "coculture", "count": 8},
    {"background_factor": "darkness", "count": 3},
    ...
  ],
  "by_omics_type": [
    {"omics_type": "RNASEQ", "count": 26},
    {"omics_type": "MICROARRAY", "count": 10},
    {"omics_type": "PROTEOMICS", "count": 8},
    {"omics_type": "EXOPROTEOMICS", "count": 4},
    {"omics_type": "VESICLE_PROTEOMICS", "count": 3},
    ...
  ],
  "by_cluster_type": [
    {"cluster_type": "time_course", "count": 4},
    {"cluster_type": "diel", "count": 2},
    {"cluster_type": "condition_comparison", "count": 2},
    {"cluster_type": "decay_pattern", "count": 1},
    {"cluster_type": "genomic_island", "count": 1}
  ],
  "by_value_kind": [
    {"value_kind": "boolean", "count": 7},
    {"value_kind": "numeric", "count": 7},
    {"value_kind": "categorical", "count": 5}
  ],
  "by_metric_type": [
    {"metric_type": "expression_change_high_light_shock", "count": 1},
    {"metric_type": "expression_change_low_co2_no_o2_shock", "count": 1},
    {"metric_type": "expression_change_low_co2_shock", "count": 1},
    {"metric_type": "rapid_recovery_low_co2_no_o2_shock", "count": 1},
    {"metric_type": "rapid_recovery_low_co2_shock", "count": 1},
    ...
  ],
  "by_metric_type_truncated": true,
  "by_compartment": [
    {"compartment": "whole_cell", "count": 44},
    {"compartment": "exoproteome", "count": 4},
    {"compartment": "vesicle", "count": 3},
    {"compartment": "extracellular", "count": 1}
  ],
  "by_discusses_coverage": {"has_discusses": 45, "no_discusses": 4},
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "not_found": [],
  "results": [
    {
      "doi": "10.64898/2026.04.15.718746",
      "title": "Extreme genome reduction selectively retains modular regulatory architecture in Prochlorococcus MED4: conserved trans...",
      "authors": ["Zachary Johnson", "Natalie C. Sadler", "Marci R. Garcia", "Xiaolu Li", "Jordan Rozum", ...],
      "year": 2026,
      "journal": "bioRxiv",
      "study_type": "RNA-seq, Transcriptomics",
      "organisms": ["Prochlorococcus MED4"],
      "experiment_count": 2,
      "treatment_types": ["darkness", "light"],
      "background_factors": ["axenic", "diel"],
      "omics_types": ["RNASEQ"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": ["diel"],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "compartments": ["whole_cell"],
      "metabolite_count": 0,
      "metabolite_assay_count": 0,
      "metabolite_compartments": [],
      "discussed_gene_count": 75,
      "discussed_pathway_count": 11
    },
    {
      "doi": "10.1128/aem.00798-26",
      "title": "Vesicle-associated exudates from Alteromonas enhance growth and survival of Prochlorococcus in batch culture",
      "authors": ["Zhiying Lu", "Sydney Plummer", "James Kizziah", "Steven J. Biller", "J. Jeffrey Morris"],
      "year": 2026,
      "journal": "Applied and Environmental Microbiology",
      "study_type": "co-culture experiments with experimental evolution",
      "organisms": ["Alteromonas macleodii EZ55"],
      "experiment_count": 2,
      "treatment_types": ["compartment"],
      "background_factors": ["axenic"],
      "omics_types": ["EXOPROTEOMICS", "PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 6,
      "derived_metric_value_kinds": ["boolean"],
      "compartments": ["exoproteome", "whole_cell"],
      "metabolite_count": 0,
      "metabolite_assay_count": 0,
      "metabolite_compartments": [],
      "discussed_gene_count": 2,
      "discussed_pathway_count": 2
    },
    {
      "doi": "10.1101/2025.08.05.668435",
      "title": "Biofilm formation and dynamics in the marine cyanobacterium Prochlorococcus",
      "authors": ["Maya I. Anjur-Dietrich", "Katelyn G. Jones", "James I. Mullet", "Nhi N. Vo", "Kurt G. Castro", ...],
      "year": 2025,
      "journal": "bioRxiv",
      "study_type": "Ecology, Microbiology",
      "organisms": ["Prochlorococcus MIT9301"],
      "experiment_count": 1,
      "treatment_types": ["growth_phase"],
      "background_factors": ["axenic", "light"],
      "omics_types": ["RNASEQ"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": ["exponential"],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "compartments": ["whole_cell"],
      "metabolite_count": 0,
      "metabolite_assay_count": 0,
      "metabolite_compartments": [],
      "discussed_gene_count": 5,
      "discussed_pathway_count": 2
    },
    ...
  ]
}
```

### Example 2: Find coculture studies

```example-call
list_publications(treatment_type="coculture")
```

### Example 3: Chaining to experiments

```
Step 1: list_publications(organism="MED4")
        → find papers studying MED4

Step 2: list_experiments(publication_doi=[result["doi"]])
        → drill into experiments from a specific paper

Step 3: genes_by_function(search_text="photosystem", organism="MED4")
        → find genes of interest
```

### Example 4: Fetch metadata for a known DOI list

```example-call
list_publications(publication_dois=["10.1038/ismej.2016.70", "10.1101/2025.11.24.690089"], verbose=True)
```

### Example 5: Find vesicle-fraction publications with DM evidence

```example-call
list_publications(compartment="vesicle")
```

```example-response
{
  "total_entries": 49,
  "total_matching": 3,
  "by_organism": [
    {"organism_name": "Prochlorococcus MIT9313", "count": 2},
    {"organism_name": "Prochlorococcus MED4", "count": 1},
    {"organism_name": "Prochlorococcus MIT9312", "count": 1},
    {"organism_name": "Alteromonas macleodii AD45", "count": 1},
    {"organism_name": "Alteromonas macleodii ATCC27126", "count": 1},
    ...
  ],
  "by_organism_truncated": null,
  "by_treatment_type": [{"treatment_type": "compartment", "count": 3}],
  "by_background_factors": [
    {"background_factor": "axenic", "count": 3},
    {"background_factor": "light", "count": 2},
    {"background_factor": "darkness", "count": 1}
  ],
  "by_omics_type": [
    {"omics_type": "VESICLE_PROTEOMICS", "count": 3},
    {"omics_type": "VESICLE_DNASEQ", "count": 1},
    {"omics_type": "METABOLOMICS", "count": 1}
  ],
  "by_cluster_type": [],
  "by_value_kind": [
    {"value_kind": "numeric", "count": 3},
    {"value_kind": "boolean", "count": 1},
    {"value_kind": "categorical", "count": 1}
  ],
  "by_metric_type": [
    {"metric_type": "mascot_identification_probability", "count": 1},
    {"metric_type": "predicted_subcellular_localization", "count": 1},
    {"metric_type": "vesicle_dna_avg_read_coverage", "count": 1},
    {"metric_type": "vesicle_proteome_member", "count": 1},
    {"metric_type": "cell_abundance_biovolume_normalized", "count": 1},
    ...
  ],
  "by_metric_type_truncated": null,
  "by_compartment": [{"compartment": "vesicle", "count": 3}, {"compartment": "whole_cell", "count": 1}],
  "by_discusses_coverage": {"has_discusses": 2, "no_discusses": 1},
  "returned": 3,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "results": [
    {
      "doi": "10.1093/femsml/uqac025",
      "title": "Characterization of membrane vesicles in Alteromonas macleodii indicates potential roles in their copiotrophic lifestyle",
      "authors": [
        "Eduard Fadeev",
        "Cécile Carpaneto Bastos",
        "Jennifer H. Hennenfeind",
        "Steven J. Biller",
        "Daniel Sher",
        ...
      ],
      "year": 2023,
      "journal": "microLife",
      "study_type": "Proteomics, Microscopy, Extracellular vesicle analysis",
      "organisms": [
        "Alteromonas macleodii AD45",
        "Alteromonas macleodii ATCC27126",
        "Alteromonas macleodii BGP6",
        "Alteromonas macleodii BS11",
        "Alteromonas macleodii HOT1A3",
        ...
      ],
      "experiment_count": 6,
      "treatment_types": ["compartment"],
      "background_factors": ["axenic", "darkness"],
      "omics_types": ["VESICLE_PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 18,
      "derived_metric_value_kinds": ["numeric"],
      "compartments": ["vesicle"],
      "metabolite_count": 0,
      "metabolite_assay_count": 0,
      "metabolite_compartments": [],
      "discussed_gene_count": 22,
      "discussed_pathway_count": 0
    },
    {
      "doi": "10.1111/1462-2920.15834",
      "title": "Prochlorococcus extracellular vesicles: molecular composition and adsorption to diverse microbes",
      "authors": ["Steven J. Biller", "Rachel A. Lundeen", "Laura R. Hmelo", "Kevin W. Becker", "Aldo A. Arellano", ...],
      "year": 2022,
      "journal": "Environmental Microbiology",
      "study_type": "Multi-omics (lipidomics, proteomics, metabolomics)",
      "organisms": ["Prochlorococcus MIT9312", "Prochlorococcus MIT9313"],
      "experiment_count": 6,
      "treatment_types": ["compartment"],
      "background_factors": ["axenic", "light"],
      "omics_types": ["METABOLOMICS", "VESICLE_PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 6,
      "derived_metric_value_kinds": ["numeric"],
      "compartments": ["vesicle", "whole_cell"],
      "metabolite_count": 69,
      "metabolite_assay_count": 4,
      "metabolite_compartments": ["vesicle", "whole_cell"],
      "discussed_gene_count": 11,
      "discussed_pathway_count": 0
    },
    {
      "doi": "10.1126/science.1243457",
      "title": "Bacterial Vesicles in Marine Ecosystems",
      "authors": [
        "Steven J. Biller",
        "Florence Schubotz",
        "Sara E. Roggensack",
        "Anne W. Thompson",
        "Roger E. Summons",
        ...
      ],
      "year": 2014,
      "journal": "Science",
      "study_type": "Imaging, Proteomics, Genomics, Lipidomics, Nanoparticle tracking analysis",
      "organisms": ["Prochlorococcus MED4", "Prochlorococcus MIT9313"],
      "experiment_count": 3,
      "treatment_types": ["compartment"],
      "background_factors": ["axenic", "light"],
      "omics_types": ["VESICLE_DNASEQ", "VESICLE_PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 7,
      "derived_metric_value_kinds": ["boolean", "categorical", "numeric"],
      "compartments": ["vesicle"],
      "metabolite_count": 0,
      "metabolite_assay_count": 0,
      "metabolite_compartments": [],
      "discussed_gene_count": 0,
      "discussed_pathway_count": 0
    }
  ]
}
```

### Example 6: Inspect the metabolomics-bearing publications (per-row metabolite rollups)

```example-call
list_publications(publication_dois=["10.1128/msystems.01261-22", "10.1073/pnas.2213271120", "10.1111/1462-2920.15834"])
```

```example-response
{
  "total_entries": 49,
  "total_matching": 3,
  "by_organism": [
    {"organism_name": "Prochlorococcus MIT9313", "count": 3},
    {"organism_name": "Prochlorococcus MIT9312", "count": 1},
    {"organism_name": "Prochlorococcus MIT9303", "count": 1},
    {"organism_name": "Prochlorococcus MIT0801", "count": 1},
    {"organism_name": "Prochlorococcus MIT9301", "count": 1}
  ],
  "by_organism_truncated": null,
  "by_treatment_type": [
    {"treatment_type": "compartment", "count": 1},
    {"treatment_type": "carbon", "count": 1},
    {"treatment_type": "growth_phase", "count": 1},
    {"treatment_type": "phosphorus", "count": 1}
  ],
  "by_background_factors": [{"background_factor": "axenic", "count": 3}, {"background_factor": "light", "count": 2}],
  "by_omics_type": [
    {"omics_type": "METABOLOMICS", "count": 3},
    {"omics_type": "VESICLE_PROTEOMICS", "count": 1},
    {"omics_type": "RNASEQ", "count": 1}
  ],
  "by_cluster_type": [],
  "by_value_kind": [{"value_kind": "numeric", "count": 1}],
  "by_metric_type": [
    {"metric_type": "cell_abundance_biovolume_normalized", "count": 1},
    {"metric_type": "log2_vesicle_cell_enrichment", "count": 1},
    {"metric_type": "vesicle_abundance_biovolume_normalized", "count": 1}
  ],
  "by_metric_type_truncated": null,
  "by_compartment": [
    {"compartment": "whole_cell", "count": 3},
    {"compartment": "vesicle", "count": 1},
    {"compartment": "extracellular", "count": 1}
  ],
  "by_discusses_coverage": {"has_discusses": 3, "no_discusses": 0},
  "returned": 3,
  "offset": 0,
  "truncated": false,
  "not_found": [],
  "results": [
    {
      "doi": "10.1073/pnas.2213271120",
      "title": "Chitin utilization by marine picocyanobacteria and the evolution of a planktonic lifestyle",
      "authors": [
        "Giovanna Capovilla",
        "Rogier Braakman",
        "Gregory P. Fournier",
        "Thomas Hackl",
        "Julia Schwartzman",
        ...
      ],
      "year": 2023,
      "journal": "Proceedings of the National Academy of Sciences",
      "study_type": "Comparative genomics and enzymatic assays",
      "organisms": ["Prochlorococcus MIT9303", "Prochlorococcus MIT9313"],
      "experiment_count": 4,
      "treatment_types": ["carbon"],
      "background_factors": ["axenic", "light"],
      "omics_types": ["METABOLOMICS", "RNASEQ"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": ["exponential"],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "compartments": ["whole_cell"],
      "metabolite_count": 16,
      "metabolite_assay_count": 2,
      "metabolite_compartments": ["whole_cell"],
      "discussed_gene_count": 7,
      "discussed_pathway_count": 2
    },
    {
      "doi": "10.1128/msystems.01261-22",
      "title": "Metabolite diversity among representatives of divergent Prochlorococcus ecotypes",
      "authors": [
        "Elizabeth B. Kujawinski",
        "Rogier Braakman",
        "Krista Longnecker",
        "Jamie W. Becker",
        "Sallie W. Chisholm",
        ...
      ],
      "year": 2023,
      "journal": "mSystems",
      "study_type": "Metabolomics",
      "organisms": ["Prochlorococcus MIT0801", "Prochlorococcus MIT9301", "Prochlorococcus MIT9313"],
      "experiment_count": 6,
      "treatment_types": ["growth_phase", "phosphorus"],
      "background_factors": ["axenic"],
      "omics_types": ["METABOLOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "compartments": ["extracellular", "whole_cell"],
      "metabolite_count": 99,
      "metabolite_assay_count": 8,
      "metabolite_compartments": ["whole_cell", "extracellular"],
      "discussed_gene_count": 6,
      "discussed_pathway_count": 4
    },
    {
      "doi": "10.1111/1462-2920.15834",
      "title": "Prochlorococcus extracellular vesicles: molecular composition and adsorption to diverse microbes",
      "authors": ["Steven J. Biller", "Rachel A. Lundeen", "Laura R. Hmelo", "Kevin W. Becker", "Aldo A. Arellano", ...],
      "year": 2022,
      "journal": "Environmental Microbiology",
      "study_type": "Multi-omics (lipidomics, proteomics, metabolomics)",
      "organisms": ["Prochlorococcus MIT9312", "Prochlorococcus MIT9313"],
      "experiment_count": 6,
      "treatment_types": ["compartment"],
      "background_factors": ["axenic", "light"],
      "omics_types": ["METABOLOMICS", "VESICLE_PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 6,
      "derived_metric_value_kinds": ["numeric"],
      "compartments": ["vesicle", "whole_cell"],
      "metabolite_count": 69,
      "metabolite_assay_count": 4,
      "metabolite_compartments": ["vesicle", "whole_cell"],
      "discussed_gene_count": 11,
      "discussed_pathway_count": 0
    }
  ]
}
```

### Example 7: Find publications with a narrative literature index

```example-call
list_publications()
```

```example-response
{
  "total_entries": 49,
  "total_matching": 49,
  "by_organism": [
    {"organism_name": "Prochlorococcus MED4", "count": 20},
    {"organism_name": "Prochlorococcus MIT9313", "count": 10},
    {"organism_name": "Prochlorococcus NATL2A", "count": 6},
    {"organism_name": "Synechococcus WH7803", "count": 6},
    {"organism_name": "Prochlorococcus MIT9312", "count": 5},
    ...
  ],
  "by_organism_truncated": true,
  "by_treatment_type": [
    {"treatment_type": "coculture", "count": 12},
    {"treatment_type": "carbon", "count": 6},
    {"treatment_type": "light", "count": 6},
    {"treatment_type": "viral", "count": 5},
    {"treatment_type": "growth_phase", "count": 4},
    ...
  ],
  "by_background_factors": [
    {"background_factor": "light", "count": 33},
    {"background_factor": "axenic", "count": 33},
    {"background_factor": "diel", "count": 9},
    {"background_factor": "coculture", "count": 8},
    {"background_factor": "darkness", "count": 3},
    ...
  ],
  "by_omics_type": [
    {"omics_type": "RNASEQ", "count": 26},
    {"omics_type": "MICROARRAY", "count": 10},
    {"omics_type": "PROTEOMICS", "count": 8},
    {"omics_type": "EXOPROTEOMICS", "count": 4},
    {"omics_type": "VESICLE_PROTEOMICS", "count": 3},
    ...
  ],
  "by_cluster_type": [
    {"cluster_type": "time_course", "count": 4},
    {"cluster_type": "diel", "count": 2},
    {"cluster_type": "condition_comparison", "count": 2},
    {"cluster_type": "decay_pattern", "count": 1},
    {"cluster_type": "genomic_island", "count": 1}
  ],
  "by_value_kind": [
    {"value_kind": "boolean", "count": 7},
    {"value_kind": "numeric", "count": 7},
    {"value_kind": "categorical", "count": 5}
  ],
  "by_metric_type": [
    {"metric_type": "expression_change_high_light_shock", "count": 1},
    {"metric_type": "expression_change_low_co2_no_o2_shock", "count": 1},
    {"metric_type": "expression_change_low_co2_shock", "count": 1},
    {"metric_type": "rapid_recovery_low_co2_no_o2_shock", "count": 1},
    {"metric_type": "rapid_recovery_low_co2_shock", "count": 1},
    ...
  ],
  "by_metric_type_truncated": true,
  "by_compartment": [
    {"compartment": "whole_cell", "count": 44},
    {"compartment": "exoproteome", "count": 4},
    {"compartment": "vesicle", "count": 3},
    {"compartment": "extracellular", "count": 1}
  ],
  "by_discusses_coverage": {"has_discusses": 45, "no_discusses": 4},
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "not_found": [],
  "results": [
    {
      "doi": "10.64898/2026.04.15.718746",
      "title": "Extreme genome reduction selectively retains modular regulatory architecture in Prochlorococcus MED4: conserved trans...",
      "authors": ["Zachary Johnson", "Natalie C. Sadler", "Marci R. Garcia", "Xiaolu Li", "Jordan Rozum", ...],
      "year": 2026,
      "journal": "bioRxiv",
      "study_type": "RNA-seq, Transcriptomics",
      "organisms": ["Prochlorococcus MED4"],
      "experiment_count": 2,
      "treatment_types": ["darkness", "light"],
      "background_factors": ["axenic", "diel"],
      "omics_types": ["RNASEQ"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": ["diel"],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "compartments": ["whole_cell"],
      "metabolite_count": 0,
      "metabolite_assay_count": 0,
      "metabolite_compartments": [],
      "discussed_gene_count": 75,
      "discussed_pathway_count": 11
    },
    {
      "doi": "10.1128/aem.00798-26",
      "title": "Vesicle-associated exudates from Alteromonas enhance growth and survival of Prochlorococcus in batch culture",
      "authors": ["Zhiying Lu", "Sydney Plummer", "James Kizziah", "Steven J. Biller", "J. Jeffrey Morris"],
      "year": 2026,
      "journal": "Applied and Environmental Microbiology",
      "study_type": "co-culture experiments with experimental evolution",
      "organisms": ["Alteromonas macleodii EZ55"],
      "experiment_count": 2,
      "treatment_types": ["compartment"],
      "background_factors": ["axenic"],
      "omics_types": ["EXOPROTEOMICS", "PROTEOMICS"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": [],
      "derived_metric_count": 6,
      "derived_metric_value_kinds": ["boolean"],
      "compartments": ["exoproteome", "whole_cell"],
      "metabolite_count": 0,
      "metabolite_assay_count": 0,
      "metabolite_compartments": [],
      "discussed_gene_count": 2,
      "discussed_pathway_count": 2
    },
    {
      "doi": "10.1101/2025.08.05.668435",
      "title": "Biofilm formation and dynamics in the marine cyanobacterium Prochlorococcus",
      "authors": ["Maya I. Anjur-Dietrich", "Katelyn G. Jones", "James I. Mullet", "Nhi N. Vo", "Kurt G. Castro", ...],
      "year": 2025,
      "journal": "bioRxiv",
      "study_type": "Ecology, Microbiology",
      "organisms": ["Prochlorococcus MIT9301"],
      "experiment_count": 1,
      "treatment_types": ["growth_phase"],
      "background_factors": ["axenic", "light"],
      "omics_types": ["RNASEQ"],
      "clustering_analysis_count": 0,
      "cluster_types": [],
      "growth_phases": ["exponential"],
      "derived_metric_count": 0,
      "derived_metric_value_kinds": [],
      "compartments": ["whole_cell"],
      "metabolite_count": 0,
      "metabolite_assay_count": 0,
      "metabolite_compartments": [],
      "discussed_gene_count": 5,
      "discussed_pathway_count": 2
    },
    ...
  ]
}
```

## Chaining patterns

```
list_publications → list_experiments → differential_expression_by_gene
list_publications → genes_by_function
list_publications → list_clustering_analyses(publication_doi=[...])
list_publications(search_text=..., verbose=True) → classify → list_publications(publication_dois=[...]) for the picked subset
list_publications(compartment=...) → use derived_metric_value_kinds per result row to route to genes_by_{boolean,numeric,categorical}_metric
list_filter_values(filter_type='metric_type') → list_publications(search_text='<metric_type>') to find publications with that metric
list_publications (per-row `metabolite_count > 0`) → list_metabolite_assays(publication_doi=[...]) to inspect the paper's MetaboliteAssay nodes (numeric vs boolean, compartment, detection-status rollup).
list_publications (per-row `discussed_gene_count` or `discussed_pathway_count` > 0) → discussed_by_publication(publication_dois=[...]) to list the genes + KEGG pathways the paper names in prose.
```

## Common mistakes

- If a result row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric. Empty derived_metric_value_kinds means no DM evidence on this publication.

- treatment_type is a string filter, not a list — use treatment_type='coculture' not treatment_type=['coculture'].

- treatment_type / background_factors / growth_phase values are LIVE vocabularies read from the KG, not enums: an unknown value (e.g. 'nitrogen_stress' instead of 'nitrogen') returns 0 rows, never an error. Check list_filter_values(filter_type='growth_phase') or a summary=True call's by_treatment_type / by_background_factors rollup before filtering. Current treatment values are short nouns (nitrogen, light, carbon, iron, darkness, phosphorus, salt, viral, coculture, diel, ...); background_factors are light, axenic, coculture, darkness, diel, viral, chemical. On this tool the rollups come from an unfiltered list_publications() call.

- `organism=` is a word-based, case-insensitive match on preferred_name + name_synonyms — 'MED4' works. Two OrganismTaxon nodes share the name 'Meiothermus ruber' (genome strain + treatment taxon), so organism='Meiothermus ruber' counts papers tied to either.

- Use the dedicated author param for author filtering (e.g. author='Biller'), not search_text — search_text searches title, abstract, and description only.

- experiment_count is per-publication — a publication with experiment_count=10 may span multiple organisms and treatment types.

- metabolite_count > 0 indicates a metabolomics-bearing publication. Drill into MetaboliteAssay nodes via list_metabolite_assays(publication_doi=[...]); inspect compartments via metabolite_compartments per row.

- discussed_gene_count / discussed_pathway_count are the paper's prose literature index — the genes + KEGG pathways it names in text (recall-biased, NOT exhaustive, NOT DE-table expression). 0 on both means no narrative index (4 such publications, the `no_discusses` bucket). Drill into the named entities via discussed_by_publication(publication_dois=[...]).

```mistake
list_experiments(publication='Biller 2018')
```

```correction
list_publications(search_text='Biller') then list_experiments(publication_doi=['10.1038/...'])
```

## Package import equivalent

```python
from multiomics_explorer import list_publications

result = list_publications()
# returns dict with keys: total_entries, total_matching, by_organism, by_organism_truncated, by_treatment_type, by_background_factors, by_omics_type, by_cluster_type, by_value_kind, by_metric_type, by_metric_type_truncated, by_compartment, by_discusses_coverage, returned, offset, truncated, not_found, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
