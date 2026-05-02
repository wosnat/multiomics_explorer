# list_organisms

## What it does

List organisms in the knowledge graph, optionally filtered by name or compartment.

Returns taxonomy, gene counts, publication counts, and organism_type
for each organism. organism_type classifies each organism as
'genome_strain', 'treatment', or 'reference_proteome_match'.
Reference proteome match organisms also include reference_database
and reference_proteome fields.

Use the returned organism names as filter values in genes_by_function,
resolve_gene, genes_by_ontology, list_publications, etc. The organism
filter on those tools uses partial matching — "MED4",
"Prochlorococcus MED4", and "Prochlorococcus" all work. The
organism_names filter on this tool uses exact match (case-
insensitive) on preferred_name; unknown names are reported in
not_found.

After this tool, scope deeper queries to the chosen organism: use the
locus_tags filter on per-gene tools (gene_overview, gene_homologs)
and the organism filter on gene_ontology_terms, list_experiments,
and list_publications. Use list_filter_values for categorical
field enumeration.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| organism_names | list[string] \| None | None | Filter by exact organism preferred_name (case-insensitive). Pass values from a prior list_organisms call or another tool's organism_name field. Unknown names are reported in not_found rather than raising. |
| compartment | string \| None | None | Filter to organisms with at least one experiment in this wet-lab compartment (e.g. 'vesicle', 'whole_cell'). Use list_filter_values(filter_type='compartment') to enumerate valid values. |
| summary | bool | False | Return summary fields only (results=[]). |
| verbose | bool | False | Include full taxonomy hierarchy (family, order, class, phylum, kingdom, superkingdom, lineage). |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

## Response format

### Envelope

```expected-keys
total_entries, total_matching, by_cluster_type, by_organism_type, by_value_kind, by_metric_type, by_compartment, by_metabolic_capability, returned, offset, truncated, not_found, results
```

- **total_entries** (int): Total organisms in the KG
- **total_matching** (int): Organisms matching the filter (= total_entries when no filter)
- **by_cluster_type** (list[OrgClusterTypeBreakdown]): Organism counts per cluster type over the matched set, sorted by count descending
- **by_organism_type** (list[OrgTypeBreakdown]): Organism counts per type over the matched set, sorted by count descending
- **by_value_kind** (list[OrgValueKindBreakdown]): DM value_kind frequency rollup across matched organisms. Each entry: {value_kind, count}.
- **by_metric_type** (list[OrgMetricTypeBreakdown]): DM metric_type frequency rollup across matched organisms. Each entry: {metric_type, count}.
- **by_compartment** (list[OrgCompartmentBreakdown]): Wet-lab compartment frequency rollup across matched organisms. Each entry: {compartment, count}.
- **by_metabolic_capability** (list[OrgMetabolicCapabilityBreakdown]): Top 10 organisms by metabolite_count (within matched set), sorted desc. Filter excludes organisms with zero chemistry. [] when no matched organism has chemistry. Use list_metabolites(organism_names=[organism_name]) on top entries to enumerate their metabolites.
- **returned** (int): Number of results returned
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if total_matching > offset + returned
- **not_found** (list[string]): organism_names inputs that didn't match any organism (case-insensitive); [] when no filter

### Per-result fields

| Field | Type | Description |
|---|---|---|
| organism_name | string | Display name (e.g. 'Prochlorococcus MED4'). Use for organism filters in other tools. |
| organism_type | string | Classification: 'genome_strain', 'treatment', or 'reference_proteome_match' |
| genus | string \| None (optional) | Genus (e.g. 'Prochlorococcus', 'Alteromonas') |
| species | string \| None (optional) | Binomial species name (e.g. 'Prochlorococcus marinus') |
| strain | string \| None (optional) | Strain identifier (e.g. 'MED4', 'EZ55') |
| clade | string \| None (optional) | Ecotype clade, Prochlorococcus-specific (e.g. 'HLI', 'LLIV') |
| ncbi_taxon_id | int \| None (optional) | NCBI Taxonomy ID for cross-referencing external databases (e.g. 59919) |
| gene_count | int | Number of genes in the KG for this organism (e.g. 1976) |
| publication_count | int | Number of publications studying this organism (e.g. 11) |
| experiment_count | int | Total experiments across all publications (e.g. 46) |
| treatment_types | list[string] (optional) | Distinct treatment types studied (e.g. ['coculture', 'light_stress', 'nitrogen_stress']) |
| background_factors | list[string] (optional) | Distinct background factors across experiments (e.g. ['axenic', 'continuous_light', 'diel_cycle']) |
| omics_types | list[string] (optional) | Distinct omics types available (e.g. ['RNASEQ', 'PROTEOMICS']) |
| clustering_analysis_count | int (optional) | Number of clustering analyses for this organism (e.g. 4) |
| cluster_types | list[string] (optional) | Distinct cluster types (e.g. ['condition_comparison', 'diel']) |
| growth_phases | list[string] (optional) | Distinct growth phases across experiments (e.g. ['exponential', 'nutrient_limited']). Physiological state of the culture at sampling — timepoint-level, not gene-specific. |
| derived_metric_count | int (optional) | Total DerivedMetric annotations on this organism's experiments (0 when none). |
| derived_metric_value_kinds | list[string] (optional) | Subset of {numeric, boolean, categorical} present across this organism's DMs. Use to route to genes_by_{numeric,boolean,categorical}_metric. |
| compartments | list[string] (optional) | Wet-lab compartments measured for this organism (e.g. ['whole_cell', 'vesicle']). |
| reaction_count | int (optional) | Distinct reactions catalyzed by genes in this organism (e.g. 943). When > 0, drill in via list_metabolites(organism_names=[organism_name]) to enumerate metabolites this organism is capable of metabolizing. |
| metabolite_count | int (optional) | Distinct metabolites this organism's genes can act on (e.g. 1039). Capability signal — does NOT mean these metabolites were measured. Today reflects gene catalysis only; will grow to include transport substrates when the TCDB-CAZy ontology ships, with no schema change. When > 0, drill in via list_metabolites(organism_names=[organism_name]). |
| derived_metric_gene_count | int \| None (optional) | Total gene-level DM annotation count (verbose-only). |
| derived_metric_types | list[string] \| None (optional) | Distinct metric_type tags observed (verbose-only). |
| reference_database | string \| None (optional) | Reference database used for matching (e.g. 'MarRef v6'). Only on reference_proteome_match organisms. |
| reference_proteome | string \| None (optional) | Accession of matched reference proteome (e.g. 'GCA_003513035.1'). Only on reference_proteome_match organisms. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| family | string \| None (optional) | Taxonomic family (e.g. 'Prochlorococcaceae') |
| order | string \| None (optional) | Taxonomic order (e.g. 'Synechococcales') |
| tax_class | string \| None (optional) | Taxonomic class (e.g. 'Cyanophyceae') |
| phylum | string \| None (optional) | Taxonomic phylum (e.g. 'Cyanobacteriota') |
| kingdom | string \| None (optional) | Taxonomic kingdom (e.g. 'Bacillati') |
| superkingdom | string \| None (optional) | Taxonomic superkingdom (e.g. 'Bacteria') |
| lineage | string \| None (optional) | Full NCBI taxonomy lineage string (e.g. 'cellular organisms; Bacteria; ...; Prochlorococcus marinus') |
| cluster_count | int \| None (optional) | Total gene clusters across analyses (only with verbose=True, e.g. 35) |

## Few-shot examples

### Example 1: Browse all organisms

```example-call
list_organisms()
```

```example-response
{
  "total_entries": 36,
  "total_matching": 36,
  "by_organism_type": [
    {"organism_type": "genome_strain", "count": 29},
    {"organism_type": "treatment", "count": 5},
    {"organism_type": "reference_proteome_match", "count": 2}
  ],
  "returned": 5,
  "truncated": true,
  "offset": 0,
  "not_found": [],
  "results": [
    {"organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain", "genus": "Prochlorococcus", "species": "Prochlorococcus marinus", "strain": "MED4", "clade": "HLI", "ncbi_taxon_id": 59919, "gene_count": 1976, "publication_count": 16, "experiment_count": 112, "treatment_types": ["coculture", "carbon", "nitrogen", ...], "omics_types": ["RNASEQ", "PROTEOMICS"], "clustering_analysis_count": 4, "cluster_types": ["diel", "time_course"], "reaction_count": 943, "metabolite_count": 1039}
  ]
}
```

### Example 2: Full taxonomy

```example-call
list_organisms(verbose=True)
```

### Example 3: Look up specific organisms by name

```example-call
list_organisms(organism_names=["Prochlorococcus MED4", "Prochlorococcus MIT9301", "Bogus organism"])
```

```example-response
{"total_entries": 36, "total_matching": 2, "returned": 2, "truncated": false, "not_found": ["Bogus organism"], "by_organism_type": [{"organism_type": "genome_strain", "count": 2}], "by_metabolic_capability": [{"organism_name": "Prochlorococcus MED4", "reaction_count": 943, "metabolite_count": 1039}, {"organism_name": "Prochlorococcus MIT9301", "reaction_count": 916, "metabolite_count": 1018}], "results": [{"organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain", "gene_count": 1976, "reaction_count": 943, "metabolite_count": 1039, ...}, {"organism_name": "Prochlorococcus MIT9301", "organism_type": "genome_strain", "gene_count": 1935, "reaction_count": 916, "metabolite_count": 1018, ...}]}
```

### Example 4: Chaining to genes and publications

```
Step 1: list_organisms()
        → discover available organisms and data coverage

Step 2: genes_by_function(search_text="photosystem", organism="MED4")
        → search genes within a specific organism

Step 3: list_publications(organism="MED4")
        → find publications studying that organism
```

### Example 5: Find organisms with vesicle-fraction DM evidence

```example-call
list_organisms(compartment="vesicle")
```

```example-response
{"total_matching": 3, "by_compartment": [{"compartment": "vesicle", "count": 3}, {"compartment": "whole_cell", "count": 1}], "returned": 3, "truncated": false, "offset": 0, "not_found": [],
 "results": [
   {"organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain", "derived_metric_count": 17, "derived_metric_value_kinds": ["boolean", "categorical", "numeric"], "compartments": ["vesicle", "whole_cell"], "reaction_count": 943, "metabolite_count": 1039}
 ]}
```

### Example 6: Identify chemistry-rich organisms (capability ranking)

```example-call
list_organisms(summary=True)
```

```example-response
{"total_entries": 36, "total_matching": 36, "by_metabolic_capability": [{"organism_name": "Pseudomonas putida KT2440", "reaction_count": 1449, "metabolite_count": 1490}, {"organism_name": "Ruegeria pomeroyi DSS-3", "reaction_count": 1377, "metabolite_count": 1468}, {"organism_name": "Alteromonas macleodii EZ55", "reaction_count": 1348, "metabolite_count": 1428}], "returned": 0, "truncated": true, "offset": 0, "not_found": [], "results": []}
```

## Chaining patterns

```
list_organisms → genes_by_function
list_organisms → list_publications
list_organisms → resolve_gene
list_organisms → genes_by_ontology
list_organisms → list_clustering_analyses(organism=...)
list_organisms(compartment=...) → use derived_metric_value_kinds per result row to route to genes_by_{boolean,numeric,categorical}_metric
list_organisms (per-row metabolite_count > 0) → list_metabolites(organism_names=[organism_name]) for chemistry drill-down
```

## Good to know

- If a result row has derived_metric_value_kinds=['boolean'], drill down via genes_by_boolean_metric. For ['numeric'], use genes_by_numeric_metric. For ['categorical'], use genes_by_categorical_metric. Empty derived_metric_value_kinds means no DM evidence on this organism.

- gene_count and publication_count are counts of data in the KG, not biological totals

- Organisms with gene_count=0 are parent/umbrella taxonomy nodes (e.g. genus-level 'Alteromonas')

- The organism filter in other tools uses partial matching — 'MED4', 'Prochlorococcus MED4', and 'Prochlorococcus' all work

- organism_names on this tool uses exact match (case-insensitive) on preferred_name — short forms like 'MED4' will not match. Pass canonical names from a prior list_organisms call.

- not_found contains organism_names inputs whose preferred_name didn't match any OrganismTaxon (case-insensitive).

- reference_database and reference_proteome are sparse — only present on reference_proteome_match organisms, absent from others

- organism_type values: 'genome_strain' (real genome assembly), 'treatment' (non-genomic coculture partners), 'reference_proteome_match' (identified via reference database matching)

- growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — NOT a gene-specific property

- metabolite_count counts capability via gene catalysis — distinct metabolites reachable through Gene → Reaction → Metabolite. Does NOT include transport substrates (until TCDB-CAZy ships) or measured metabolites (until metabolomics-DM ships). 0 does not mean the metabolite is absent from the KG.

- by_metabolic_capability is a top-10 ranking sorted by metabolite_count descending; organisms with zero chemistry are excluded. Use it on summary=True calls to identify chemistry-rich organisms before drilling in via list_metabolites(organism_names=[...]).

## Package import equivalent

```python
from multiomics_explorer import list_organisms

result = list_organisms()
# returns dict with keys: total_entries, total_matching, by_cluster_type, by_organism_type, by_value_kind, by_metric_type, by_compartment, by_metabolic_capability, offset, not_found, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
