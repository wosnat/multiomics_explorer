# search_ontology

## What it does

Search ontology terms by text — Lucene over term names only (no hierarchy traversal).

Returns term IDs and `level` for use with `genes_by_ontology`. Supports
fuzzy (~), wildcards (*), exact phrases ("..."), boolean (AND, OR) —
see docs://guide/conventions for syntax + scoring.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string | — | Lucene query over term names. E.g. 'replication', 'oxido*', 'transport AND membrane'. See docs://guide/conventions for Lucene scoring. |
| ontology | string | — | Ontology to search: 'go_bp', 'go_mf', 'go_cc', 'kegg', 'ec', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type'. |
| summary | bool | False | When true, return only summary fields (results=[]). |
| limit | int | 5 | Max results. |
| offset | int | 0 | Number of results to skip for pagination. |
| level | int \| None | None | Hierarchy level filter (0 = broadest). See docs://guide/conventions for the level convention. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Only valid when ontology='brite'. See docs://guide/conventions for the BRITE-tree scoping rule. |
| informative_only | bool | False | When True, exclude terms flagged uninformative in KG (e.g. KEGG 'metabolic pathways' map00001, GO root 'biological_process' go:0008150). Term-side filter only — never restricts the gene set. Default False (opt-in). |

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
| is_informative | bool | True iff term is not flagged is_uninformative (positive framing; coerced from sparse '<term>.is_uninformative' KG flag) |
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

### Example 7: Find PSORTb subcellular localizations

```example-call
search_ontology(search_text="outer", ontology="subcellular_localization")
```

```example-response
{
  "total_entries": 5,
  "total_matching": 1,
  "score_max": 2.42,
  "score_median": 2.42,
  "returned": 1,
  "truncated": false,
  "offset": 0,
  "results": [
    {"id": "psortb_OuterMembrane", "name": "Outer membrane",
     "score": 2.42, "level": 0}
  ]
}
```

### Example 8: Find SignalP lipoprotein signal-peptide types

```example-call
search_ontology(search_text="lipo", ontology="signal_peptide_type")
```

```example-response
{
  "total_entries": 5,
  "total_matching": 2,
  "score_max": 3.1,
  "score_median": 2.6,
  "returned": 2,
  "truncated": false,
  "offset": 0,
  "results": [
    {"id": "signalp_LIPO", "name": "Lipoprotein signal peptide (Sec/SPII)",
     "score": 3.1, "level": 0},
    {"id": "signalp_TATLIPO", "name": "TAT lipoprotein signal peptide (Tat/SPII)",
     "score": 2.6, "level": 0}
  ]
}
```

### Example 9: Filter out uninformative terms (term-side, opt-in)

```example-call
search_ontology(search_text="transport", ontology="kegg", informative_only=True)
```

```example-response
# `informative_only=True` drops terms flagged `is_uninformative='true'`
# (~224 sparsely-flagged terms genome-wide, mostly KEGG catch-all
# modules + a handful of Cyanorak / TIGR / GO / COG entries — Pfam is
# not flagged in the current KG). Each result row carries
# `is_informative: bool` (always populated). Use this when seeding
# term IDs into `genes_by_ontology` for enrichment so catch-all KEGG
# buckets don't dominate the term set.
{
  "total_entries": 18000,
  "total_matching": 22,
  "results": [
    {"id": "kegg:K02035", "name": "ABC.PE.S; peptide/nickel transport system substrate-binding protein", "score": 2.81, "level": 3, "is_informative": true}
  ]
}
```

### Example 10: From search to gene discovery

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

- Use this to assemble a custom `term_ids=[...]` list for `pathway_enrichment` / `cluster_enrichment`. Both tools accept either `level=N` (test all terms at one hierarchy depth) or `term_ids=[...]` (test a specific set you chose). Custom term sets are useful when relevant terms live at different depths — e.g. in GO, a term at level 3 may be more specific than one at level 4 because GO is graph-shaped, not strictly tree-shaped. See `docs://analysis/enrichment`.

- PSORTb and SignalP ontologies are **flat** (5 nodes each, single `level=0`). Don't pass `level=1` or higher — the search returns nothing because no terms exist at those levels.

- PSORTb / SignalP are **structural** ontologies (where a gene's product is / how it's handled). Use them for localization / secretion questions, not for functional-annotation `genes_by_function`-style proxies.

## Package import equivalent

```python
from multiomics_explorer import search_ontology

result = search_ontology(search_text=..., ontology=...)
# returns dict with keys: total_entries, total_matching, score_max, score_median, offset, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
