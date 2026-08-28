# COG functional categories (`cog_category`)

Generated from `inputs/ontologies/cog_category.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

COG functional categories — the 26 single-letter classes of the Clusters
of Orthologous Groups system (`cog.category:E` amino acid transport and
metabolism, `cog.category:J` translation, `cog.category:S` function
unknown). The coarsest functional partition in the KG: every gene lands
in one or a few letters, which makes it the quickest whole-genome
composition view and the weakest enrichment axis.

## How genes get annotated

Assigned by eggNOG-mapper from the gene's orthologous group
(`sources=['eggnog']`, `evidence='family_inferred'` on every edge). A gene
can carry several letters when its group is multi-category. No curated
rung, no `evidence_score` — the trust surface is uniform, so filters on
`sources`/`evidence` do not separate anything.

## Identifier form

`cog.category:E` — prefix plus the single capital letter; node `code`
holds the bare letter, `name` the category description.

## Hierarchy

Flat: 26 nodes, all `level=0`, no hierarchy edges, nothing to expand.
`gene_count` / `organism_count` are direct (no `direct_gene_count` — it
would equal `gene_count`).

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `CogFunctionalCategory` |
| Gene → term edge | `Gene_in_cog_category` |
| Hierarchy edges | none — flat ontology (`level=0` only, nothing to expand) |
| Fulltext index | `cogCategoryFullText` |
| Trust axes on the gene edge | `sources`, `evidence` |
| Extra compact columns, `ontology_term_details` | `code` |
| Bridges out (`links_out`) | none |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`CogFunctionalCategory`)

| Property | Type | Meaning |
|---|---|---|
| `code` | string |  |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Controlled vocabularies

Values: see `list_filter_values(filter_type=..., ontology='cog_category')` — `trust_axes`, `evidence`, `sources`, and the ontology-specific categorical filter types are read from the KG's `ControlledVocabulary` nodes at call time.

## Interpretation

Use for genome-level composition ("what fraction of the genome is
informational vs metabolic") and for a first-pass enrichment when the
gene set is small and any finer ontology would fail `min_gene_set_size`.
Category `S` (function unknown) and `R` (general function prediction
only) are the "we don't know" bins; a gene set enriched in `S` is a set
of poorly annotated genes, not a biological signal.

## Informativeness rule

`cog.category:S` (function unknown) is flagged uninformative and dropped
by `informative_only=True`. `R` is not flagged but carries the same
caveat.

## Pitfalls

- Only 26 terms — an enrichment run over COG gives at most 26 tests and
  nearly every category is a large gene set; expect broad, low-resolution
  results.
- `level` is always 0; passing `level=1` returns nothing.
- Multi-letter genes contribute to several categories, so category
  `gene_count`s overlap.

## Typical questions

- What is the COG category composition of MED4 vs MIT9313?
- Which COG categories are over-represented in the darkness-responsive cluster?
- How many genes in this organism have no functional category beyond `S`?

## Tools

- `search_ontology(ontology=['cog_category'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='cog_category', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['cog_category'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['cog_category'])` then `pathway_enrichment` / `cluster_enrichment(ontology='cog_category', level=N)` — ORA.

## See also

- `docs://ontologies/kegg`
- `docs://ontologies/cyanorak_role`
- `docs://ontologies/tigr_role`
- `docs://analysis/enrichment`
- `docs://tools/genes_by_ontology`
- `docs://tools/ontology_term_details`
