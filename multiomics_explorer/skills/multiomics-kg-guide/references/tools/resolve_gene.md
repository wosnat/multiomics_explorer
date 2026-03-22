# resolve_gene

## What it does

Resolve a gene identifier to matching genes in the knowledge graph.

Matching is case-insensitive — 'pmm0001', 'PMM0001', and 'Pmm0001'
all work. Use the returned locus_tags with gene_overview,
get_gene_details, get_homologs, or gene_ontology_terms. The organism
filter uses case-insensitive partial matching — 'MED4' and
'Prochlorococcus MED4' both work.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| identifier | string | — | Gene identifier (case-insensitive) — locus_tag (e.g. 'PMM0001'), gene name (e.g. 'dnaN'), old locus tag, or RefSeq protein ID. |
| organism | string \| None | None | Filter by organism (case-insensitive partial match). E.g. 'MED4', 'Prochlorococcus MED4'. |
| limit | int | 50 | Max results. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, returned, truncated, results
```

- **total_matching** (int): Total genes matching identifier + organism filter (e.g. 3)
- **returned** (int): Genes in this response (e.g. 3)
- **truncated** (bool): True if total_matching > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001') |
| gene_name | string \| None (optional) | Gene name (e.g. 'dnaN') |
| product | string \| None (optional) | Gene product (e.g. 'DNA polymerase III, beta subunit') |
| organism_strain | string | Organism (e.g. 'Prochlorococcus MED4') |

## Few-shot examples

### Example 1: Resolve by locus_tag

```example-call
resolve_gene(identifier="PMM0001")
```

```example-response
{
  "total_matching": 1,
  "returned": 1,
  "truncated": false,
  "results": [
    {"locus_tag": "PMM0001", "gene_name": "dnaN", "product": "DNA polymerase III, beta subunit", "organism_strain": "Prochlorococcus MED4"}
  ]
}
```

### Example 2: Resolve gene name across organisms

```example-call
resolve_gene(identifier="dnaN")
```

```example-response
{
  "total_matching": 15,
  "returned": 15,
  "truncated": false,
  "results": [
    {"locus_tag": "PMM0001", "gene_name": "dnaN", "product": "DNA polymerase III, beta subunit", "organism_strain": "Prochlorococcus MED4"},
    {"locus_tag": "PMT9312_0001", "gene_name": "dnaN", "product": "DNA polymerase III, beta subunit", "organism_strain": "Prochlorococcus MIT9312"},
    ...
  ]
}
```

### Example 3: Scoped to one organism

```example-call
resolve_gene(identifier="dnaN", organism="MED4")
```

### Example 4: Chain to gene overview

```
Step 1: resolve_gene(identifier="psbA")
        → collect locus_tags from results

Step 2: gene_overview(gene_ids=["PMM1070", "PMT9312_1073", ...])
        → compare function and data availability across organisms
```

## Chaining patterns

```
resolve_gene → gene_overview → get_homologs
resolve_gene → get_gene_details
resolve_gene → gene_ontology_terms
```

## Common mistakes

- Case-insensitive matching: 'pmm0001', 'PMM0001', and 'Pmm0001' all work

- The organism filter uses partial matching — 'MED4' and 'Prochlorococcus MED4' both work

```mistake
search_genes(search_text='PMM0001')  # wrong tool for ID lookup
```

```correction
resolve_gene(identifier='PMM0001')  # exact identity resolution
```

## Package import equivalent

```python
from multiomics_explorer import resolve_gene

result = resolve_gene(identifier=...)
# returns dict with keys: total_matching, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
