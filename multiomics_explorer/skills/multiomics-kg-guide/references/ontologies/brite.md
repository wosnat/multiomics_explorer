# KEGG BRITE hierarchies (`brite`)

Generated from `inputs/ontologies/brite.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

KEGG BRITE functional hierarchies — twelve curated trees that classify
KEGG Orthology groups by protein family rather than by pathway:
`transporters`, `enzymes`, `peptidases`, `transcription_factors`,
`secretion`, `two_component`, `defense`, `chaperones`, `ribosome`,
`translation_factors`, `trna_biogenesis`, `dna_replication`. Where a
KEGG pathway asks "what process", BRITE asks "what kind of protein".

## How genes get annotated

BRITE has no gene edge of its own: genes reach a category through their
KO (`Gene_has_kegg_ko`) and the `Kegg_term_in_brite_category` bridge, so
every BRITE annotation inherits KEGG's trust profile
(`sources=['eggnog']`, `evidence='family_inferred'`, no score). Each
category node records which tree it belongs to (`tree`, `tree_code`) and
how many KOs it holds (`member_ko_count`).

## Identifier form

`kegg.brite:ko02000.A2` — prefix, the tree code (`ko02000` =
transporters), and the node path within that tree. `tree` is the
snake_case tree name used by the `tree=` facet; discover the names with
`list_filter_values(filter_type='brite_tree')`.

## Hierarchy

Up to four levels within a tree, `level` 0-3 with `level_kind`
`brite_class` → `brite_subclass` → `brite_family` → `brite_subfamily`
(`Brite_category_is_a_brite_category`); most trees stop at level 1 or
2 — only `enzymes` and `dna_replication` reach level 3, and
`peptidases`, `secretion` and `two_component` end at level 1. Trees
are independent — the
transporters tree and the enzymes tree share no nodes. `gene_count` /
`organism_count` are subtree-inclusive; there is no `direct_gene_count`
(genes never attach to a category directly). The `enzymes` tree is by far
the largest and swamps any un-faceted query.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `BriteCategory` |
| Gene → term edge | `Gene_has_kegg_ko` |
| Hierarchy edges (child → parent) | `Brite_category_is_a_brite_category` |
| Reached via | `KeggTerm` terms through `Kegg_term_in_brite_category` (the gene edge belongs to that ontology) |
| Fulltext index | `briteCategoryFullText` |
| Facet param | `tree` (node prop `tree`) |
| Trust axes on the gene edge | `sources`, `evidence` |
| Extra compact columns, `ontology_term_details` | `tree`, `tree_code` |
| Bridges out (`links_out`) | none |
| Bridges in (read from the source term) | `Kegg_term_in_brite_category` from `kegg` (*membership*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`BriteCategory`)

| Property | Type | Meaning |
|---|---|---|
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `level_kind` | string | what a level means in this ontology (e.g. `tc_family`, `pathway`) — read values via `list_filter_values` |
| `member_ko_count` | int | KOs listed under this BRITE category upstream (source membership, not KG genes) |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |
| `tree` | string | BRITE tree this category belongs to (snake_case, e.g. `transporters`) — the `tree=` facet value |
| `tree_code` | string | KEGG BRITE tree accession (e.g. `ko02000`) — the tree segment of `id` |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

- `evidence` — `list_filter_values(filter_type="evidence", ontology="brite")`
- `sources` — `list_filter_values(filter_type="sources", ontology="brite")`
- `brite_tree` — `list_filter_values(filter_type="brite_tree")`

Values are read live from the KG's `ControlledVocabulary` nodes at call time; this page never quotes them. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="brite")`) lists which comparable axes the gene edge carries.

Snapshot of vocabulary values at build time (`--live-vocab`):

- `BriteCategory.level_kind`: `brite_class`, `brite_subclass`, `brite_family`, `brite_subfamily`
- `BriteCategory.tree`: `enzymes`, `transporters`, `peptidases`, `transcription_factors`, `secretion`, `two_component`, `defense`, `chaperones`, `ribosome`, `translation_factors`, `trna_biogenesis`, `dna_replication`
- `Gene_has_kegg_ko.evidence`: `family_inferred`
- `Gene_has_kegg_ko.sources`: `eggnog`

## Interpretation

Always pick a tree first. `tree='transporters'` at level 1-2 gives the
transporter-family enrichment KEGG pathways cannot (an ABC importer and a
MFS exporter are one "membrane transport" pathway but different BRITE
families); `tree='transcription_factors'` or `two_component` gives
regulator-family views. Because the gene edge is KEGG's, a BRITE
enrichment re-partitions the same KO annotations — it is a different
lens, not independent evidence.

## Informativeness rule

No BRITE category is flagged uninformative; the level-0 class nodes of the
`enzymes` tree (Transferases, Hydrolases, ...) are catch-alls by size.
Scope with `tree=` and `level>=1`, and let `max_gene_set_size` handle the
rest.

## Pitfalls

- Un-faceted BRITE calls are dominated by the `enzymes` tree; `tree=` is
  a facet (it narrows only BRITE and raises if `brite` is not in the
  ontology list).
- Term IDs carry the tree code; a level-3 node in `transporters` and one
  in `enzymes` are unrelated even when their names look similar.
- For substrate-level transporter questions use TCDB (`tcdb`) or the
  chemistry layer; BRITE transporter families are KO groupings, not
  substrate calls.
- Trust filters on `brite` do nothing (single rung) and `min_evidence_score`
  raises.

## Typical questions

- Which transporter families (BRITE `transporters` tree) are enriched among genes up under nitrogen limitation?
- How many two-component system genes does MIT1002 carry, by BRITE subclass?
- Which BRITE categories does `kegg.orthology:K02575` belong to? — `ontology_term_details(term_ids=['kegg.orthology:K02575'])` and read `links_out[]`
- Which two-component-system genes does MIT1002 carry? — `genes_by_ontology(ontology='brite', organism='MIT1002', tree='two_component', level=1)`
- What are the level-2 families under the `secretion` tree, with gene counts for MED4?

## Tools

- `search_ontology(ontology=['brite'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='brite', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['brite'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['brite'])` then `pathway_enrichment` / `cluster_enrichment(ontology='brite', level=N)` — ORA.

## See also

- `docs://ontologies/kegg`
- `docs://ontologies/tcdb`
- `docs://guide/conventions`
- `docs://analysis/enrichment`
- `docs://tools/list_filter_values`
- `docs://tools/ontology_term_details`
