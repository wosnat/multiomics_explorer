# genes_by_function

## What it does

Free-text search across gene names, products, and functional descriptions. Lucene syntax (see docs://guide/conventions). Results ranked by relevance score.

Routing: feed `locus_tag`s into `gene_overview` (data-availability triage), `gene_ontology_terms` (annotation drill-down), or `genes_by_ontology` for ontology-anchored search instead. A genus word in `organism` (e.g. 'Alteromonas') matches every strain in that genus rather than raising ambiguous.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string | — | Free-text query (Lucene syntax: quoted phrases, AND/OR, wildcards `*`, fuzzy `~`). E.g. 'photosystem', 'nitrogen AND transport', 'dnaN~'. Multi-word input is OR'd — quote the phrase or join with AND for an exact/combined match. See docs://guide/conventions for Lucene scoring details. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| gene_categories | list[string] \| None | None | Filter by gene_category — matches any of the given values. E.g. ['Photosynthesis', 'Transport']. Use list_filter_values to see valid values. |
| min_quality | int | 0 | Minimum annotation_quality (0..3 numeric encoding of `Gene.annotation_state`): 0=no_evidence, 1=catch_all_only, 2=informative_single, 3=informative_multi. Use 2 to skip hypothetical proteins; 3 for high-confidence. [AQ] Definition shifted in 2026-05 KG release; see docs://guide/conventions. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields in docs://tools/{name}. |
| limit | int \| None | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Response format

### Envelope

```expected-keys
total_search_hits, total_matching, by_organism, by_category, score_max, score_median, returned, offset, truncated, warnings, results
```

- **total_search_hits** (int): Total genes matching search text (before organism/gene_categories/quality filters).
- **total_matching** (int): Total genes matching search + all filters.
- **by_organism** (list[FunctionOrganismBreakdown]): Gene counts per organism, sorted desc.
- **by_organism_truncated** (bool | None): True when the list was capped at 10 — `summary=True` returns the full list.
- **by_category** (list[FunctionCategoryBreakdown]): Gene counts per category, sorted desc.
- **score_max** (float | None): Highest relevance score (null if 0 matches).
- **score_median** (float | None): Median relevance score (null if 0 matches).
- **returned** (int): Number of results returned.
- **offset** (int): Offset into full result set.
- **truncated** (bool): True when total_matching > returned.
- **warnings** (list[string]): An empty intersection (search_text hit genes but `organism` / `gene_categories` / `min_quality` left total_matching=0 — not an absence of matching genes), a `gene_categories` value not found in the live vocabulary (see list_filter_values(filter_type='gene_category')), or an `organism` that matches no OrganismTaxon. Advisory only — never changes which rows are returned. Empty when clean.

### Per-result fields

| Field | Type | Description |
|---|---|---|
| locus_tag | string | Gene locus tag (e.g. 'PMM0001'). |
| gene_name | string \| None (optional) | Gene name (e.g. 'dnaN'). |
| product | string \| None (optional) | Gene product (e.g. 'DNA polymerase III subunit beta'). |
| organism_name | string | Organism name (e.g. 'Prochlorococcus MED4'). |
| gene_category | string \| None (optional) | Functional category (e.g. 'Photosynthesis'). |
| annotation_quality | int | Annotation quality, 0..3 numeric encoding of `Gene.annotation_state` (informative-evidence count). 3=informative_multi, 2=informative_single, 1=catch_all_only, 0=no_evidence. [AQ] Definition shifted in 2026-05 KG release; see docs://guide/conventions. |
| score | float | Lucene relevance score. |

**Verbose-only fields** (included when `verbose=True`):

| Field | Type | Description |
|---|---|---|
| function_description | string \| None (optional) | Functional description text (verbose-only). |
| gene_summary | string \| None (optional) | Combined gene annotation summary (verbose-only). |

## Few-shot examples

### Example 1: Search for photosynthesis genes

```example-call
genes_by_function(search_text="photosystem")
```

```example-response
{
  "total_search_hits": 2039,
  "total_matching": 2039,
  "by_organism": [
    {"organism_name": "Prochlorococcus MIT9303", "count": 87},
    {"organism_name": "Synechococcus CC9311", "count": 82},
    {"organism_name": "Synechococcus sp. BL107", "count": 79},
    {"organism_name": "Synechococcus WH7803", "count": 78},
    {"organism_name": "Prochlorococcus MIT9313", "count": 78},
    ...
  ],
  "by_organism_truncated": true,
  "by_category": [
    {"category": "Photosynthesis", "count": 1001},
    {"category": "Stress response and adaptation", "count": 274},
    {"category": "Unknown", "count": 247},
    {"category": "Energy production", "count": 234},
    {"category": "Post-translational modification", "count": 87},
    ...
  ],
  "score_max": 6.588601112365723,
  "score_median": 4.331913948059082,
  "returned": 5,
  "offset": 0,
  "truncated": true,
  "results": [
    {
      "locus_tag": "H6G84_06320",
      "gene_name": "psbO",
      "product": "photosystem II manganese-stabilizing polypeptide",
      "organism_name": "Synechococcus elongatus PCC 7942",
      "gene_category": "Unknown",
      "annotation_quality": 3,
      "score": 6.588601112365723
    },
    {
      "locus_tag": "M744_01545",
      "gene_name": "psbO",
      "product": "photosystem II manganese-stabilizing polypeptide",
      "organism_name": "Synechococcus elongatus UTEX 2973",
      "gene_category": "Unknown",
      "annotation_quality": 3,
      "score": 6.588601112365723
    },
    {
      "locus_tag": "SYNPCC7002_A0269",
      "gene_name": "psbO",
      "product": "photosystem II manganese-stabilizing polypeptide",
      "organism_name": "Synechococcus PCC 7002",
      "gene_category": "Unknown",
      "annotation_quality": 3,
      "score": 6.588601112365723
    },
    ...
  ]
}
```

### Example 2: Search with organism filter and verbose output

```example-call
genes_by_function(search_text="nitrogen transport", organism="MED4", verbose=True)
```

### Example 3: Get counts only (no rows)

```example-call
genes_by_function(search_text="chaperone", summary=True)
```

```example-response
{
  "total_search_hits": 1428,
  "total_matching": 1428,
  "by_organism": [
    {"organism_name": "Pseudomonas putida KT2440", "count": 62},
    {"organism_name": "Shewanella sp. W3-18-1", "count": 54},
    {"organism_name": "Marinobacter (MarRef v6)", "count": 54},
    {"organism_name": "Alteromonas (MarRef v6)", "count": 48},
    {"organism_name": "Alteromonas macleodii HOT1A3", "count": 42},
    ...
  ],
  "by_organism_truncated": null,
  "by_category": [
    {"category": "Post-translational modification", "count": 641},
    {"category": "Stress response and adaptation", "count": 199},
    {"category": "Unknown", "count": 167},
    {"category": "Coenzyme metabolism", "count": 119},
    {"category": "Cell motility", "count": 72},
    ...
  ],
  "score_max": 7.583498001098633,
  "score_median": 4.1626152992248535,
  "returned": 0,
  "offset": 0,
  "truncated": true,
  "results": []
}
```

### Example 4: Chaining — find genes then inspect details

```
Step 1: genes_by_function(search_text="ferredoxin", summary=True)
        → note total_matching and by_organism breakdown

Step 2: genes_by_function(search_text="ferredoxin", organism="MIT9313", limit=20)
        → collect locus_tags from results

Step 3: gene_overview(locus_tags=["PMT0001", ...])
        → get expression availability and annotation details
```

## Chaining patterns

```
genes_by_function → gene_overview
genes_by_function → gene_ontology_terms
genes_by_function → genes_by_ontology (use term IDs from gene_ontology_terms)
search_ontology → genes_by_ontology (ontology-first route, alternative to genes_by_function)
```

## Common mistakes

- annotation_quality / min_quality semantics shifted in 2026-05 KG release. Existing notebooks using min_quality may select a different gene set than before. See docs://guide/conventions.

```mistake
genes_by_function(search_text='GO:0015977')
```

```correction
genes_by_ontology(ontology='go_bp', organism='MED4', term_ids=['go:0015977']) for ontology term lookup (ontology + organism required); genes_by_function is for free-text search.
```

```mistake
len(result['results'])  # to count matches
```

```correction
result['total_matching']  # results may be truncated
```

```mistake
genes_by_function(search_text='ABC transporter permease', organism='HOT1A3', gene_categories=['Transport'])  # total_search_hits 8705, total_matching 1 -> 'no transporters in HOT1A3'
```

```correction
`gene_categories` matches any of the given values against a curated Gene.gene_category value, and 'Transport' is a real but small category (most transporters sit under 'Inorganic ion transport'). A large total_search_hits with total_matching 0 is an empty intersection, not an absence — the envelope says so in `warnings` (a tiny non-zero count gets no warning; compare the two fields yourself). Re-run without `gene_categories` and read `by_category` to see where the hits fall, or go ontology-first (`genes_by_ontology` with a TCDB / GO term) to enumerate transporters.
```

- Use summary=True to get organism/category breakdowns without fetching gene rows.

- Use min_quality=2 to skip hypothetical proteins and get better-annotated results.

- The organism filter is a word-based, case-insensitive match on preferred_name + name_synonyms — 'MED4' works. A genus word alone ('Prochlorococcus') matches every strain of that genus. 'Meiothermus ruber' names two OrganismTaxon nodes (genome strain + gene-less treatment taxon) — only the genome strain has genes, so gene hits are unaffected.

## Package import equivalent

```python
from multiomics_explorer import genes_by_function

result = genes_by_function(search_text=...)
# returns dict with keys: total_search_hits, total_matching, by_organism, by_organism_truncated, by_category, score_max, score_median, returned, offset, truncated, warnings, results
```

Use package import for bulk data extraction in scripts.
Use MCP for reasoning and interactive exploration.
