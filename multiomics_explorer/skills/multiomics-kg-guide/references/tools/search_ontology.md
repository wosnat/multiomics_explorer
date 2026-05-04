# search_ontology

## What it does

Browse ontology terms by text search (fuzzy, Lucene syntax).

Returns term IDs for use with genes_by_ontology. Supports fuzzy (~),
wildcards (*), exact phrases ("..."), boolean (AND, OR).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string | — | Search query (Lucene syntax). E.g. 'replication', 'oxido*', 'transport AND membrane'. |
| ontology | string | — | Ontology to search: 'go_bp', 'go_mf', 'go_cc', 'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy'. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |
| level | int \| None | None | Filter to terms at this hierarchy level. 0 = broadest. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'. |

## Response format

### Envelope

```expected-keys
total_entries, total_matching, score_max, score_median, returned, offset, truncated, results
```

- **total_entries** (int): Total terms in this ontology (e.g. 847)
- **total_matching** (int): Terms matching the search (e.g. 31)
- **score_max** (float | None): Highest relevance score (null if 0 matches, e.g. 5.23)
- **score_median** (float | None): Median relevance score (null if 0 matches, e.g. 2.1)
- **returned** (int): Results in this response (0 when summary=true)
- **offset** (int): Offset into full result set (e.g. 0)
- **truncated** (bool): True if total_matching > returned

### Per-result fields

| Field | Type | Description |
|---|---|---|
| id | string | Term ID (e.g. 'go:0006260') |
| name | string | Term name (e.g. 'DNA replication') |
| score | float | Fulltext relevance score (e.g. 5.23) |
| level | int | Hierarchy level of this term (0 = broadest) |
| tree | string \| None (optional) | BRITE tree name (sparse: BRITE only) |
| tree_code | string \| None (optional) | BRITE tree code (sparse: BRITE only) |

## Few-shot examples

### Example 1: Search GO biological processes

```example-call
search_ontology(search_text="replication", ontology="go_bp")
```

```example-response
{
  "total_entries": 2448,
  "total_matching": 31,
  "score_max": 2.48,
  "score_median": 1.78,
  "returned": 5,
  "truncated": true,
  "offset": 0,
  "results": [
    {"id": "go:0006260", "name": "DNA replication", "score": 2.48},
    {"id": "go:0006261", "name": "DNA-templated DNA replication", "score": 2.41},
    ...
  ]
}
```

### Example 2: Summary only (how many terms match?)

```example-call
search_ontology(search_text="transport", ontology="go_bp", summary=True)
```

### Example 3: BRITE search scoped to a specific tree

```example-call
search_ontology(search_text="transport", ontology="brite", tree="transporters")
```

```example-response
{
  "total_entries": 84,
  "total_matching": 12,
  "score_max": 3.1,
  "score_median": 2.0,
  "returned": 5,
  "truncated": true,
  "offset": 0,
  "results": [
    {"id": "brite:B99001", "name": "ABC transporters", "score": 3.1, "level": 1, "tree": "transporters", "tree_code": "ko02000"},
    ...
  ]
}
```

### Example 4: Filter search results by hierarchy level

```example-call
search_ontology(search_text="oxido*", ontology="kegg", level=2)
```

### Example 5: Find TCDB families that move sucrose

```example-call
search_ontology(search_text="sucrose", ontology="tcdb")
```

```example-response
{
  "total_entries": 4844,
  "total_matching": 6,
  "score_max": 3.42,
  "score_median": 2.10,
  "returned": 5,
  "truncated": true,
  "offset": 0,
  "results": [
    {"id": "tcdb:2.A.1.5.3", "name": "Sucrose:H+ symporter", "score": 3.42, "level": 4},
    ...
  ]
}
```

### Example 6: Browse CAZy glycoside hydrolase families

```example-call
search_ontology(search_text="GH13", ontology="cazy")
```

### Example 7: From search to gene discovery

```
Step 1: search_ontology(search_text="replication", ontology="go_bp")
        → collect term IDs from results (e.g. "go:0006260")

Step 2: genes_by_ontology(ontology="go_bp", organism="MED4", term_ids=["go:0006260"])
        → find (gene × term) pairs annotated to these terms in MED4
        (with hierarchy expansion DOWN). Single organism is required.

Step 3: gene_overview(locus_tags=["PMM0845", ...])
        → check data availability for discovered genes
```

## Chaining patterns

```
search_ontology → genes_by_ontology
search_ontology → genes_by_ontology → gene_overview
list_filter_values('brite_tree') → search_ontology(ontology='brite', tree=...)
```

## Common mistakes

- search_ontology finds term IDs — use genes_by_ontology to find (gene × term) pairs annotated to those terms (single organism required, hierarchy expanded DOWN by default)

- This tool searches term names only — it does not traverse the ontology hierarchy

- For brite: term IDs look like 'brite:ko00001' (tree root) or 'brite:K00001' (leaf KO). BRITE trees mix functional and taxonomic hierarchies — confirm the tree context before using term IDs in genes_by_ontology.

- Use `level` to restrict results to a specific hierarchy depth (0 = broadest). Use `tree` to scope BRITE searches to a single tree (e.g. 'transporters'). Both filters are optional.

- For BRITE, pass `tree=...` (e.g. `tree='transporters'`); without it, results are dominated by the largest BRITE tree (~1,776 enzyme entries at level 3) and rarely what's wanted. Discover trees via `list_filter_values('brite_tree')`.

- Supported ontologies: `go_bp`, `go_mf`, `go_cc`, `kegg`, `ec`, `cog_category`, `cyanorak_role`, `tigr_role`, `pfam`, `brite`, `tcdb`, `cazy`.

- TCDB is family-level transporter classification (e.g. `tcdb:1.A.1` voltage-gated ion channels). For substrate-anchored questions ('which genes transport sucrose?'), chain via `genes_by_metabolite` instead — that tool surfaces the TCDB substrate edges directly. Use `search_ontology(ontology='tcdb')` for *family*-level browsing.

```mistake
search_ontology(search_text='PMM0845', ontology='go_bp')  # searching for a gene
```

```correction
resolve_gene(identifier='PMM0845')  # use resolve_gene for gene lookups
```

## Package import equivalent

```python
from multiomics_explorer import search_ontology

result = search_ontology(search_text=..., ontology=...)
# returns dict with keys: total_entries, total_matching, score_max, score_median, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
