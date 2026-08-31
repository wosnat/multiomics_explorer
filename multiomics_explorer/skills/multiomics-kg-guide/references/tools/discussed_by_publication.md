# discussed_by_publication

## What it does

Literature index: publication DOIs to the genes and KEGG pathways each paper names in prose, with a prominence label — recall-biased, never DE-table data.

Use for what a paper names; its DE results come from `list_experiments` then `differential_expression_by_gene`. Pathways return verbatim — chain `genes_by_ontology(ontology='kegg')` for genes.
Filters: publication_dois, entity_kind, prominence.
Returns: by_entity_kind, by_prominence, top_kegg_pathways, not_found, not_matched; one row = (doi, entity_kind, entity_id, prominence).
docs://tools/discussed_by_publication; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| publication_dois | list[string] | — | Restrict to these publication DOIs. |
| entity_kind | string ('gene', 'kegg_pathway') \| None | None | Restrict to one arm: 'gene' or 'kegg_pathway'. None = both. |
| prominence | string ('central', 'peripheral') \| None | None | Filter edges by prominence: 'central' or 'peripheral'. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 50 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

## Example

### What does a paper discuss?

```python
discussed_by_publication(publication_dois=["10.1038/ismej.2016.70"])
```

## Response sketch

```expected-keys
total_entries, total_matching, returned, offset, truncated, by_entity_kind, by_prominence, top_kegg_pathways, top_publications, not_found, not_matched, results
```

Result row: `doi, entity_kind, entity_id, entity_name, organism, prominence, evidence`

## Common mistakes

- This is a recall-biased narrative literature index — the genes and pathways a paper names in prose, NOT exhaustive coverage and NOT the supplementary DE-table expression data. Only about 1,000 distinct genes are named across the whole corpus (out of ~127k). For expression, use differential_expression_by_gene.

- It returns the KEGG pathway terms the paper discusses verbatim — it does NOT expand a pathway to its member genes. To get genes in a discussed pathway, chain into genes_by_ontology(ontology='kegg', term_ids=[pathway_id], organism=...).

- entity_id is the raw node id: gene rows carry the bare locus_tag (e.g. PMT2118); kegg_pathway rows carry the prefixed id (e.g. kegg.pathway:ko00710). Feed gene ids to gene_overview, pathway ids to genes_by_ontology(ontology='kegg').

## Chaining patterns

- list_publications → discussed_by_publication
- discussed_by_publication → gene_overview
- discussed_by_publication → genes_by_ontology(ontology='kegg', term_ids=[...])
- discussed_by_publication(entity_kind='gene') → gene_overview → differential_expression_by_gene
- discussed_by_publication(entity_kind='kegg_pathway') → genes_by_ontology(ontology='kegg', term_ids=[pathway_id]) → pathway_enrichment

Full reference (all examples, full response format, verbose fields): `docs://tools/discussed_by_publication/full`
