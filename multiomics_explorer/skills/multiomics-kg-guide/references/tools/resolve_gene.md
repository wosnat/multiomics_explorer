# resolve_gene

## What it does

Resolve a gene identifier (locus tag, gene name, old locus tag, RefSeq protein ID; case-insensitive) to matching Gene nodes.

Use when the input is an exact name, locus tag or alias (no partial matching); for partial / free-text use `genes_by_function`, for what a gene does `gene_overview`.
Filters: identifier, organism.
Returns: total_matching, by_organism; one row = one Gene match (locus_tag, gene_name, product, organism_name).
docs://tools/resolve_gene; summary=True returns by_organism uncapped (larger than the default call).

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| identifier | string | — | Gene identifier (case-insensitive) — locus_tag (e.g. 'PMM0001'), gene name (e.g. 'dnaN'), old locus tag, or RefSeq protein ID. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'); a genus word matches every strain. See list_organisms. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |

**Discovery:** use `list_organisms` for valid organism names.

## Example

### Resolve by locus_tag

```python
resolve_gene(identifier="PMM0001")
```

## Response sketch

```expected-keys
total_matching, by_organism, returned, offset, truncated, results
```

Result row: `locus_tag, gene_name, product, organism_name`

## Common mistakes

- Sibling tools: resolve_gene answers 'which node is this identifier?' (locus_tag / gene_name / alias → gene rows, no annotation payload). For 'what do I know about this gene' use gene_overview(locus_tags=[...]); for 'which genes do X' use genes_by_function(search_text=...).

- Matching is exact and case-insensitive ('pmm0001', 'PMM0001' and 'Pmm0001' all work); a partial identifier ('PMM000') matches nothing — use genes_by_function for partial or free-text input.

- not_found is not reported — an identifier with no match simply yields total_matching=0 and results=[]. See docs://guide/conventions for the not_found / not_matched shapes on batch tools.

## Chaining patterns

- resolve_gene → gene_overview → gene_homologs
- resolve_gene → gene_details
- resolve_gene → gene_ontology_terms

Full reference (all examples, full response format, verbose fields): `docs://tools/resolve_gene/full`
