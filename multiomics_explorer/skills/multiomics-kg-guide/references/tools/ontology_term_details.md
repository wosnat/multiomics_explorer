# ontology_term_details

## What it does

Batch term lookup across the 17 ontologies — name, level, informativeness, gene and organism counts, parents, children, forward-only cross-ontology bridges.

Use when you already hold self-prefixed term IDs; to find IDs use `search_ontology`, for the member genes `genes_by_ontology`.
Filters: term_ids, organism, link_kinds.
Returns: by_ontology, by_link_kind, links_out_total, not_found; one row = one term with parents[], children[], links_out[] (composition / membership / recall-biased router).
docs://tools/ontology_term_details; per-ontology semantics docs://ontologies/{key}.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| term_ids | list[string] | — | Self-prefixed term IDs, any ontology mix (e.g. 'go:0006979', 'tcdb:3.A.1', 'interpro:IPR000362', 'pfam:PF00005', 'kegg.pathway:ko00010'). Rows return in input order. Bare ids accepted (e.g. 'ko00910', 'GO:0006979') — see `resolved_aliases`. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |
| link_kinds | list[string ('composition', 'membership', 'router')] \| None | None | Keep links_out of these kinds: 'composition' = built from target (tcdb/merops -> pfam); 'membership' = belongs to (pfam/ncbifam -> interpro, kegg -> brite); 'router' = recall-biased (interpro -> ec/cazy, ncbifam TIGR* -> tigr.role). Default all. |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| limit | int | 50 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |

**Discovery:** use `list_organisms` for valid organism names.

## Example

### A mixed batch across ontologies, including an unknown ID

```python
ontology_term_details(term_ids=["tcdb:3.A.1", "merops.family:S14", "interpro:IPR000362", "ncbifam:TIGR00254", "go:0006979", "bogus:xyz"])
```

## Response sketch

```expected-keys
total_matching, returned, offset, truncated, not_found, by_ontology, links_out_total, by_link_kind, resolved_aliases, warnings, results
```

Result row: `term_id, ontology, label, name, description, level, level_kind, is_informative, gene_count, organism_count, direct_gene_count, organism_gene_count, …`

## Common mistakes

- Term IDs are self-prefixed CURIEs and the ontology is inferred from the node label — pass `go:0006979`, `tcdb:3.A.1`, `merops.family:S14`, `pfam:PF00005` / `pfam.clan:CL0023`, `kegg.pathway:ko00910`, `kegg.orthology:K02338`, `interpro:IPR000362`, `ncbifam:TIGR00254` / `ncbifam:NF006762`, `tigr.role:energy_metabolism` (main role) / `tigr.role:112` (sub role), `ec:1.1.1.1`, `cazy:GT2`. There is no `ontology=` param; a bare accession without its prefix lands in `not_found`.

- `not_found` means no node with that ID exists in any registered ontology label. It is not a filter miss — `link_kinds` can empty `links_out` but never removes the row.

- `links_out` is forward-only (composition / membership / router from the source term). To find which TCDB families are built from a given Pfam domain you need the reverse direction, which this tool does not carry — see docs://analysis/annotation_evidence for the run_cypher form.

## Chaining patterns

- search_ontology(ontology=[...]) → ontology_term_details(term_ids=[...]) — search or browse first, then inspect the hits' hierarchy and bridges
- pathway_enrichment / cluster_enrichment → ontology_term_details(term_ids=[enriched term_ids]) — what is this enriched term, how broad, what is it built from
- ontology_term_details → genes_by_ontology(ontology=<row.ontology>, term_ids=[child.id], organism=...) — pick a child from children[] and expand it to genes
- ontology_term_details(link_kinds=['composition']) → ontology_term_details(term_ids=[links_out[].target_id]) — hop across bridges (tcdb → pfam → interpro)
- gene_ontology_terms(locus_tags=[...]) → ontology_term_details(term_ids=[row.term_id]) — from a gene's terms to the terms' context
- discussed_by_publication(publication_dois=[...]) → ontology_term_details(term_ids=[kegg.pathway ids]) — context for pathways a paper names

Full reference (all examples, full response format, verbose fields): `docs://tools/ontology_term_details/full`
