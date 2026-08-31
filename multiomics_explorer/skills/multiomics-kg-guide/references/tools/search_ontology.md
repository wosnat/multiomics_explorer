# search_ontology

## What it does

Search (Lucene over term names) or browse (omit search_text: terms by gene_count) across one or many of the 17 ontologies.

Use to find term IDs or size an ontology; a term's hierarchy and bridges are `ontology_term_details`, its genes `genes_by_ontology`.
Filters: search_text, ontology, level, tree, interpro_type, min_gene_count, organism, informative_only.
Returns: mode, by_ontology, by_level, score stats, skipped_ontologies; one row = one term. Counts are subtree-scoped; limit / offset apply per ontology.
docs://tools/search_ontology and docs://ontologies/{key}; summary=True first.

## Parameters

| Name | Type | Default | Description |
|---|---|---|---|
| search_text | string \| None | None | Lucene query over term names, e.g. 'replication', 'oxido*', 'transport AND membrane'. None/'' = browse mode: list terms sorted by gene_count DESC (score null). See docs://guide/conventions for Lucene scoring. |
| ontology | string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops') \| list[string ('go_bp', 'go_mf', 'go_cc', 'ec', 'kegg', 'cog_category', 'cyanorak_role', 'tigr_role', 'pfam', 'brite', 'tcdb', 'cazy', 'subcellular_localization', 'signal_peptide_type', 'interpro', 'ncbifam', 'merops')] \| None | None | Ontology key or list. None = all 17. limit/offset apply per ontology. |
| summary | bool | False | True = envelope breakdowns only, no rows — the cheap first call. |
| limit | int | 5 | Max rows returned (paging). |
| offset | int | 0 | Rows to skip (paging). |
| level | int \| None | None | Hierarchy level filter (0 = broadest). See docs://guide/conventions for the level convention. |
| tree | string \| None | None | BRITE tree name filter (e.g. 'transporters'). Applies to 'brite' only; raises if 'brite' is not in the ontology set. See docs://guide/conventions for the BRITE-tree scoping rule. |
| informative_only | bool | False | True drops terms the KG flags uninformative (roots, catch-alls). |
| verbose | bool | False | True adds the fields listed under verbose_fields on this tool's docs://tools/ page. |
| interpro_type | string ('FAMILY', 'DOMAIN', 'HOMOLOGOUS_SUPERFAMILY', 'REPEAT', 'CONSERVED_SITE', 'ACTIVE_SITE', 'BINDING_SITE', 'PTM') \| None | None | Restrict to this InterPro entry type. Applies to 'interpro' only; raises if 'interpro' is not in the set. |
| min_gene_count | int \| None | None | Keep terms with gene_count >= this (subtree organism_gene_count when `organism` is set). Narrows browse mode. |
| organism | string \| None | None | Organism: case-insensitive word match on preferred_name / synonyms ('MED4'). Ambiguous match raises; see list_organisms. |

**Discovery:** use `list_organisms` for valid organism names.

## Example

### Search GO biological processes

```python
search_ontology(search_text="replication", ontology=["go_bp"])
```

## Response sketch

```expected-keys
mode, total_entries, total_matching, score_max, score_median, returned, offset, truncated, by_ontology, by_level, by_interpro_type, by_family_type, skipped_ontologies, warnings, results
```

Result row: `id, name, ontology_type, score, level, is_informative, tree, tree_code, interpro_type, discussed_by_n_publications, discussed_in_publications, gene_count, …`

## Common mistakes

- search_ontology finds term IDs — use genes_by_ontology to find (gene × term) pairs annotated to those terms (single organism required, hierarchy expanded DOWN by default), and ontology_term_details for a term's parents / children / bridges. Neither search nor browse walks the hierarchy for you — but the counts they show (`gene_count`, `organism_gene_count`) are subtree-scoped on hierarchical ontologies.

- `ontology` is a list (a single string is accepted); omit it to fan out over all 17 in registry order. `limit` / `offset` apply PER ontology (lockstep paging — `returned <= limit x n`); read `by_ontology[].truncated` to see which ontology still has pages. See docs://guide/conventions.

- Browse mode (no `search_text`) sorts by `gene_count DESC, id` and leaves `score` null; a browse that truncates with no `level` / facet / `min_gene_count` / `organism` filter adds a warning — you are paging through a whole ontology. Narrow first.

## Chaining patterns

- search_ontology → ontology_term_details(term_ids=[...]) — inspect the hits' parents / children / bridges before expanding
- search_ontology → genes_by_ontology
- search_ontology → genes_by_ontology → gene_overview
- search_ontology(ontology=[key], level=N) (browse) → ontology_landscape(ontology=[key]) → pathway_enrichment(ontology=key, level=N)
- list_filter_values('brite_tree') → search_ontology(ontology=['brite'], tree=...)
- search_ontology(ontology=['kegg'], verbose=True) → read per-term discussed_in_publications DOIs → list_publications(publication_dois=[...]) or discussed_by_publication(publication_dois=[...])
- search_ontology(ontology=['interpro'], interpro_type=...) / ['ncbifam'] / ['merops'] → genes_by_ontology(ontology=..., term_ids=[...], organism=...) — same forward chain as every other ontology

Full reference (all examples, full response format, verbose fields): `docs://tools/search_ontology/full`
