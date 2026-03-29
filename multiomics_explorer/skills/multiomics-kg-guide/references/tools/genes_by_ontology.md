# genes_by_ontology

## What it does

Find genes annotated to ontology terms, with hierarchy expansion.

Takes term IDs from search_ontology and finds all genes annotated to
those terms or any descendant terms in the ontology hierarchy.
Results are distinct genes (deduplicated across terms).

For term discovery, use search_ontology first.
For per-gene ontology details, use gene_ontology_terms.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| term_ids | list[string] | — | Ontology term IDs (from search_ontology). E.g. ['go:0006260', 'go:0006412']. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam') | — | Ontology the term IDs belong to. |
| organism | string \| None | None | Filter by organism (case-insensitive substring). E.g. 'MED4', 'Alteromonas'. Use list_organisms to see valid values. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include matched_terms, gene_summary, function_description. |
| limit | int | 5 | Max results. |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_matching, by_organism, by_category, by_term, returned, truncated, results
```

- **total_matching** (int): Distinct genes matching (e.g. 1742)
- **by_organism** (list[OntologyOrganismBreakdown]): Gene counts per organism, sorted desc
- **by_category** (list[OntologyCategoryBreakdown]): Gene counts per gene_category, sorted desc
- **by_term** (list[OntologyTermBreakdown]): Gene counts per input term, sorted desc (can overlap)
- **returned** (int): Results in this response (0 when summary=true)
- **truncated** (bool): True if total_matching > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001') |
| gene_name | string \| None (optional) | Gene name (e.g. 'dnaN') |
| product | string \| None (optional) | Gene product (e.g. 'DNA polymerase III, beta subunit') |
| organism_name | string | Organism (e.g. 'Prochlorococcus MED4') |
| gene_category | string \| None (optional) | Functional category (e.g. 'Replication and repair') |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| matched_terms | list[string] \| None (optional) | Input term IDs this gene was matched through (e.g. ['go:0006260']) |
| gene_summary | string \| None (optional) | Concatenated summary text |
| function_description | string \| None (optional) | Curated functional description |

## Few-shot examples

### Example 1: Find genes in a GO biological process

```example-call
genes_by_ontology(term_ids=["go:0006260"], ontology="go_bp")
```

```example-response
{
  "total_matching": 411,
  "by_organism": [{"organism_name": "Alteromonas macleodii EZ55", "count": 44}, ...],
  "by_category": [{"category": "Replication and repair", "count": 321}, ...],
  "by_term": [{"term_id": "go:0006260", "count": 411}],
  "returned": 5, "truncated": true,
  "results": [
    {"locus_tag": "A9601_00001", "gene_name": "dnaN", "product": "DNA polymerase III, beta subunit", "organism_name": "Prochlorococcus AS9601", "gene_category": "Replication and repair"},
    ...
  ]
}
```

### Example 2: Compare gene counts across terms

```example-call
genes_by_ontology(term_ids=["go:0006260", "go:0006412"], ontology="go_bp", summary=True)
```

```example-response
{
  "total_matching": 1742,
  "by_organism": [{"organism_name": "Alteromonas macleodii EZ55", "count": 152}, ...],
  "by_category": [{"category": "Translation", "count": 1182}, ...],
  "by_term": [{"term_id": "go:0006412", "count": 1331}, {"term_id": "go:0006260", "count": 411}],
  "returned": 0, "truncated": true, "results": []
}
```

### Example 3: Filter by organism

```example-call
genes_by_ontology(term_ids=["go:0006260"], ontology="go_bp", organism="MED4")
```

### Example 4: From term search to gene discovery

```
Step 1: search_ontology(search_text="replication", ontology="go_bp")
        → collect term IDs from results (e.g. "go:0006260")

Step 2: genes_by_ontology(term_ids=["go:0006260"], ontology="go_bp")
        → find genes annotated to these terms (with hierarchy expansion)

Step 3: gene_overview(locus_tags=["PMM0845", ...])
        → check data availability for discovered genes
```

## Chaining patterns

```
search_ontology → genes_by_ontology
genes_by_ontology → gene_overview
genes_by_ontology → gene_ontology_terms
```

## Common mistakes

- term_ids must come from the SAME ontology — don't mix GO and KEGG IDs

- by_term counts can overlap — a gene annotated to 2 input terms is counted in both

- Results are distinct genes, not per-term rows

```mistake
genes_by_ontology(term_ids=['replication'], ontology='go_bp')  # passing text, not IDs
```

```correction
search_ontology(search_text='replication', ontology='go_bp')  # search first, then use IDs
```

## Package import equivalent

```python
from multiomics_explorer import genes_by_ontology

result = genes_by_ontology(term_ids=..., ontology=...)
# returns dict with keys: total_matching, by_organism, by_category, by_term, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
