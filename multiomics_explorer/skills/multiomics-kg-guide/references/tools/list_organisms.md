# list_organisms

## What it does

List all organisms in the knowledge graph.

Returns taxonomy, gene counts, publication counts, and organism_type
for each organism. organism_type classifies each organism as
'genome_strain', 'treatment', or 'reference_proteome_match'.
Reference proteome match organisms also include reference_database
and reference_proteome fields.

Use the returned organism names as filter values in genes_by_function,
resolve_gene, genes_by_ontology, list_publications, etc. The organism
filter uses partial matching — "MED4", "Prochlorococcus MED4", and
"Prochlorococcus" all work.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| verbose | bool | False | Include full taxonomy hierarchy (family, order, class, phylum, kingdom, superkingdom, lineage). |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

## Response format

### Envelope

```expected-keys
total_entries, by_cluster_type, by_organism_type, returned, offset, truncated, results
```

- **total_entries** (int): Total organisms in the KG
- **by_cluster_type** (list[OrgClusterTypeBreakdown]): Organism counts per cluster type, sorted by count descending
- **by_organism_type** (list[OrgTypeBreakdown]): Organism counts per type, sorted by count descending
- **returned** (int): Number of results returned
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if results were truncated by limit

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
  "total_entries": 32,
  "by_organism_type": [
    {"organism_type": "genome_strain", "count": 25},
    {"organism_type": "treatment", "count": 5},
    {"organism_type": "reference_proteome_match", "count": 2}
  ],
  "returned": 5,
  "truncated": true,
  "offset": 0,
  "results": [
    {"organism_name": "Prochlorococcus MED4", "organism_type": "genome_strain", "genus": "Prochlorococcus", "species": "Prochlorococcus marinus", "strain": "MED4", "clade": "HLI", "ncbi_taxon_id": 59919, "gene_count": 1976, "publication_count": 11, "experiment_count": 46, "treatment_types": ["coculture", "carbon_stress", "salt_stress", "viral", ...], "omics_types": ["RNASEQ", "MICROARRAY", "PROTEOMICS"], "clustering_analysis_count": 4, "cluster_types": ["condition_comparison", "diel", "classification"]},
    {"organism_name": "Alteromonas (MarRef v6)", "organism_type": "reference_proteome_match", "genus": "Alteromonas", "gene_count": 500, "reference_database": "MarRef v6", "reference_proteome": "UP000262181", ...}
  ]
}
```

### Example 2: Full taxonomy

```example-call
list_organisms(verbose=True)
```

### Example 3: Chaining to genes and publications

```
Step 1: list_organisms()
        → discover available organisms and data coverage

Step 2: genes_by_function(search_text="photosystem", organism="MED4")
        → search genes within a specific organism

Step 3: list_publications(organism="MED4")
        → find publications studying that organism
```

## Chaining patterns

```
list_organisms → genes_by_function
list_organisms → list_publications
list_organisms → resolve_gene
list_organisms → genes_by_ontology
list_organisms → list_clustering_analyses(organism=...)
```

## Good to know

- gene_count and publication_count are counts of data in the KG, not biological totals

- Organisms with gene_count=0 are parent/umbrella taxonomy nodes (e.g. genus-level 'Alteromonas')

- The organism filter in other tools uses partial matching — 'MED4', 'Prochlorococcus MED4', and 'Prochlorococcus' all work

- reference_database and reference_proteome are sparse — only present on reference_proteome_match organisms, absent from others

- organism_type values: 'genome_strain' (real genome assembly), 'treatment' (non-genomic coculture partners), 'reference_proteome_match' (identified via reference database matching)

- growth_phase is a timepoint-level condition describing the culture's physiological state at sampling — NOT a gene-specific property

## Package import equivalent

```python
from multiomics_explorer import list_organisms

result = list_organisms()
# returns dict with keys: total_entries, by_cluster_type, by_organism_type, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
