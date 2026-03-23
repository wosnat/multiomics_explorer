# list_organisms

## What it does

List all organisms with sequenced genomes in the knowledge graph.

Returns taxonomy, gene counts, and publication counts for each organism.
Use the returned organism names as filter values in search_genes,
resolve_gene, genes_by_ontology, list_publications, etc. The organism
filter uses partial matching — "MED4", "Prochlorococcus MED4", and
"Prochlorococcus" all work.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| verbose | bool | False | Include full taxonomy hierarchy (family, order, class, phylum, kingdom, superkingdom, lineage). |
| limit | int | 5 | Max results. |

## Response format

### Envelope

```expected-keys
total_entries, returned, truncated, results
```

- **total_entries** (int): Total organisms in the KG
- **returned** (int): Number of results returned
- **truncated** (bool): True if results were truncated by limit

### Per-result fields

| Field | Type | Description |
|---|---|---|
| organism_name | string | Display name (e.g. 'Prochlorococcus MED4'). Use for organism filters in other tools. |
| genus | string \| None (optional) | Genus (e.g. 'Prochlorococcus', 'Alteromonas') |
| species | string \| None (optional) | Binomial species name (e.g. 'Prochlorococcus marinus') |
| strain | string \| None (optional) | Strain identifier (e.g. 'MED4', 'EZ55') |
| clade | string \| None (optional) | Ecotype clade, Prochlorococcus-specific (e.g. 'HLI', 'LLIV') |
| ncbi_taxon_id | int \| None (optional) | NCBI Taxonomy ID for cross-referencing external databases (e.g. 59919) |
| gene_count | int | Number of genes in the KG for this organism (e.g. 1976) |
| publication_count | int | Number of publications studying this organism (e.g. 11) |
| experiment_count | int | Total experiments across all publications (e.g. 46) |
| treatment_types | list[string] (optional) | Distinct treatment types studied (e.g. ['coculture', 'light_stress', 'nitrogen_stress']) |
| omics_types | list[string] (optional) | Distinct omics types available (e.g. ['RNASEQ', 'PROTEOMICS']) |

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

## Few-shot examples

### Example 1: Browse all organisms

```example-call
list_organisms()
```

```example-response
{
  "total_entries": 15,
  "returned": 15,
  "truncated": false,
  "results": [
    {"organism_name": "Prochlorococcus MED4", "genus": "Prochlorococcus", "species": "Prochlorococcus marinus", "strain": "MED4", "clade": "HLI", "ncbi_taxon_id": 59919, "gene_count": 1976, "publication_count": 11, "experiment_count": 46, "treatment_types": ["coculture", "carbon_stress", "salt_stress", "viral", ...], "omics_types": ["RNASEQ", "MICROARRAY", "PROTEOMICS"]},
    {"organism_name": "Alteromonas macleodii EZ55", "genus": "Alteromonas", "gene_count": 4136, "publication_count": 2, ...}
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

Step 2: search_genes(search_text="photosystem", organism="MED4")
        → search genes within a specific organism

Step 3: list_publications(organism="MED4")
        → find publications studying that organism
```

## Chaining patterns

```
list_organisms → search_genes
list_organisms → list_publications
list_organisms → resolve_gene
list_organisms → genes_by_ontology
```

## Good to know

- gene_count and publication_count are counts of data in the KG, not biological totals

- Organisms with gene_count=0 are parent/umbrella taxonomy nodes (e.g. genus-level 'Alteromonas')

- The organism filter in other tools uses partial matching — 'MED4', 'Prochlorococcus MED4', and 'Prochlorococcus' all work

## Package import equivalent

```python
from multiomics_explorer import list_organisms

result = list_organisms()
# returns dict with keys: total_entries, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
