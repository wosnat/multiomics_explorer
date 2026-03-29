# gene_ontology_terms

## What it does

Get ontology annotations for genes. One row per gene × term.

Returns the most specific (leaf) terms only — redundant ancestor terms
are excluded. Use ontology param to filter to one type, or omit for all.

For the reverse direction (find genes annotated to a term, with hierarchy
expansion), use genes_by_ontology. Use search_ontology to find terms by text.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| locus_tags | list[string] | — | Gene locus tags to look up. E.g. ['PMM0001', 'PMM0845']. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam') \| None | None | Filter to one ontology. None returns all. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| verbose | bool | False | Include organism_name per row. |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |

## Response format

### Envelope

```expected-keys
total_matching, total_genes, total_terms, by_ontology, by_term, terms_per_gene_min, terms_per_gene_max, terms_per_gene_median, returned, offset, truncated, not_found, no_terms, results
```

- **total_matching** (int): Total gene × term annotation rows
- **total_genes** (int): Distinct genes with at least one term
- **total_terms** (int): Distinct terms across all input genes
- **by_ontology** (list[OntologyTypeBreakdown]): Per ontology type: term + gene counts, sorted by term_count desc
- **by_term** (list[TermBreakdown]): Gene counts per term, sorted desc — shows shared terms across input genes
- **terms_per_gene_min** (int): Fewest leaf terms on any gene with terms (e.g. 1)
- **terms_per_gene_max** (int): Most leaf terms on any gene with terms (e.g. 15)
- **terms_per_gene_median** (float): Median leaf terms per gene with terms (e.g. 6.0)
- **returned** (int): Results in this response (0 when summary=true)
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if total_matching > returned
- **not_found** (list[string]): Input locus_tags not in KG
- **no_terms** (list[string]): Input locus_tags in KG but with no terms for queried ontology

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001') |
| term_id | string | Ontology term ID (e.g. 'go:0006260') |
| term_name | string | Term name (e.g. 'DNA replication') |
| ontology_type | string \| None (optional) | Ontology type when querying all (e.g. 'go_bp') |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| organism_name | string \| None (optional) | Organism (e.g. 'Prochlorococcus MED4') |

## Few-shot examples

### Example 1: GO biological process terms for a gene

```example-call
gene_ontology_terms(locus_tags=["PMM0001"], ontology="go_bp")
```

```example-response
{
  "total_matching": 2, "total_genes": 1, "total_terms": 2,
  "by_ontology": [{"ontology_type": "go_bp", "term_count": 2, "gene_count": 1}],
  "by_term": [
    {"term_id": "go:0006260", "term_name": "DNA replication", "ontology_type": "go_bp", "count": 1},
    {"term_id": "go:0006271", "term_name": "DNA strand elongation involved in DNA replication", "ontology_type": "go_bp", "count": 1}
  ],
  "terms_per_gene_min": 2, "terms_per_gene_max": 2, "terms_per_gene_median": 2.0,
  "returned": 2, "truncated": false, "not_found": [], "no_terms": [],
  "results": [
    {"locus_tag": "PMM0001", "term_id": "go:0006260", "term_name": "DNA replication"},
    {"locus_tag": "PMM0001", "term_id": "go:0006271", "term_name": "DNA strand elongation involved in DNA replication"}
  ]
}
```

### Example 2: All ontology annotations for a gene

```example-call
gene_ontology_terms(locus_tags=["PMM0001"])
```

### Example 3: Batch annotations with summary only

```example-call
gene_ontology_terms(locus_tags=["PMM0001", "PMM0845", "EZ55_00275"], summary=True)
```

### Example 4: From overview to ontology details

```
Step 1: gene_overview(locus_tags=["PMM0001"])
        → check annotation_types: ["go_bp", "go_mf", "kegg", "ec", ...]

Step 2: gene_ontology_terms(locus_tags=["PMM0001"], ontology="go_bp")
        → get actual GO BP terms

Step 3: genes_by_ontology(term_ids=["go:0006260"], ontology="go_bp")
        → find other genes with same term
```

## Chaining patterns

```
gene_overview → gene_ontology_terms (check annotation_types first)
gene_ontology_terms → genes_by_ontology (reverse: term → other genes)
resolve_gene → gene_ontology_terms
```

## Good to know

- ontology=None returns ALL ontology types — use ontology filter when you only need one type

- returns only leaf (most specific) terms — ancestor terms like 'metabolic process' are excluded because they are implied by the more specific child terms

- to check if a gene is connected to a broad term (e.g. 'DNA repair'), use genes_by_ontology which expands down the hierarchy — gene_ontology_terms only returns the leaf annotations

## Package import equivalent

```python
from multiomics_explorer import gene_ontology_terms

result = gene_ontology_terms(locus_tags=...)
# returns dict with keys: total_matching, total_genes, total_terms, by_ontology, by_term, terms_per_gene_min, terms_per_gene_max, terms_per_gene_median, offset, not_found, no_terms, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
