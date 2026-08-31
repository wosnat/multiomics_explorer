# resolve_gene

## What it does

Resolve a gene identifier (locus tag, gene name, old locus tag, RefSeq protein ID; case-insensitive) to matching Gene nodes.

Use when the input is a name or partial label; for what a gene does use `gene_overview`, for free-text search `genes_by_function`.
Filters: identifier, organism.
Returns: total_matching, by_organism; one row = one Gene match (locus_tag, gene_name, product, organism_name).
docs://tools/resolve_gene; summary=True first when a name may hit many strains.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| identifier | string | — | Gene identifier (case-insensitive) — locus_tag (e.g. 'PMM0001'), gene name (e.g. 'dnaN'), old locus tag, or RefSeq protein ID. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
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

- Case-insensitive matching: 'pmm0001', 'PMM0001', and 'Pmm0001' all work

- The organism filter is a word-based, case-insensitive match on preferred_name + name_synonyms — 'MED4' works, as does 'Prochlorococcus MED4'. A genus word alone ('Prochlorococcus') matches every strain of that genus — here that just widens the result set (this tool never raises on ambiguity; the single-organism expression tools do).

## Chaining patterns

- resolve_gene → gene_overview → gene_homologs
- resolve_gene → gene_details
- resolve_gene → gene_ontology_terms

Full reference (all examples, full response format, verbose fields): `docs://tools/resolve_gene/full`
