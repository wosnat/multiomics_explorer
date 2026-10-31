# genes_by_function

## What it does

Free-text Lucene search over gene names, products and functional descriptions, ranked by relevance score.

Use when you have a description and no term ID; when the keyword maps to an ontology term use `search_ontology` then `genes_by_ontology`, for an exact identifier `resolve_gene`.
Filters: search_text, organism, gene_categories, min_quality.
Returns: total_search_hits, total_matching, by_organism, by_category, score stats; one row = one gene with its score.
docs://tools/genes_by_function; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string | — | Free-text query (Lucene syntax: quoted phrases, AND/OR, wildcards `*`, fuzzy `~`). E.g. 'photosystem', 'nitrogen AND transport', 'dnaN~'. Multi-word input is OR'd — quote the phrase or join with AND for an exact/combined match. See docs://guide/conventions for Lucene scoring details. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'); a genus word matches every strain. See list_organisms. |
| gene_categories | list[string] \| None | None | Filter by gene_category — matches any of the given values. E.g. ['Photosynthesis', 'Transport']. Use list_filter_values to see valid values. |
| min_quality | int | 0 | Minimum annotation_quality (0..3 numeric encoding of `Gene.annotation_state`): 0=no_evidence, 1=catch_all_only, 2=informative_single, 3=informative_multi. Use 2 to require at least one informative annotation source (a hypothetical protein with a Pfam / KO call still passes); 3 for multi-source support. [AQ] see docs://guide/conventions. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_filter_values` for valid filter values, `list_organisms` for valid organism names.

## Example

### Search for photosynthesis genes

```python
genes_by_function(search_text="photosystem")
```

## Response sketch

```expected-keys
total_search_hits, total_matching, by_organism, by_category, score_max, score_median, returned, offset, truncated, warnings, results
```

Result row: `locus_tag, gene_name, product, organism_name, gene_category, annotation_quality, score`

## Common mistakes

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
genes_by_function(search_text='ABC transporter permease', organism='HOT1A3', gene_categories=['Transport'])  # large total_search_hits, total_matching 1 -> 'no transporters in HOT1A3'
```

```correction
`gene_categories` matches any of the given values against a curated Gene.gene_category value, and in Alteromonas most transporters sit under 'Inorganic ion transport' (Prochlorococcus / Synechococcus use Cyanorak's 'Transport'), so a category filter can miss most of them. A large total_search_hits with total_matching 0 is an empty intersection, not an absence — the envelope says so in `warnings` (a tiny non-zero count gets no warning; compare the two fields yourself). Re-run without `gene_categories` and read `by_category` to see where the hits fall, or go ontology-first (`genes_by_ontology` with a TCDB / GO term) to enumerate transporters.
```

## Chaining patterns

- genes_by_function → gene_overview
- genes_by_function → gene_ontology_terms
- genes_by_function → genes_by_ontology (use term IDs from gene_ontology_terms)
- search_ontology → genes_by_ontology (ontology-first route, alternative to genes_by_function)

Full reference (all examples, full response format, verbose fields): `docs://tools/genes_by_function/full`
