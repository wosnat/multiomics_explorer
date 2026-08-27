# CAZy families (`cazy`)

Generated from `inputs/ontologies/cazy.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

CAZy — Carbohydrate-Active enZymes: sequence-based families of the
enzymes that build, break and modify glycosidic bonds. Six classes
(`cazy:GH` glycoside hydrolases, `cazy:GT` glycosyltransferases, `cazy:PL`
polysaccharide lyases, `cazy:CE` carbohydrate esterases, `cazy:AA`
auxiliary activities, `cazy:CBM` carbohydrate-binding modules) and
numbered families within each (`cazy:GT2`). Relevant to
exopolysaccharide, cell-wall and — for Alteromonas — polysaccharide
degradation biology.

## How genes get annotated

Gene → family edges pool InterProScan (via dbCAN-style HMMs) and eggNOG
transfer (`sources[]`), merged with compact `evidence` (`curated`,
`family_inferred`, `domain_inferred`) and an `evidence_score` in [0, 1].
Family edges roll up to the class node via `Cazy_family_is_a_cazy_family`.
InterPro entries bridge *to* CAZy families as a `router`
(`Interpro_entry_related_to_cazy_family`) — a computed cross-reference,
read from the InterPro term.

## Identifier form

`cazy:GT` (class, level 0) and `cazy:GT2` (family, level 1) — prefix plus
the CAZy class letters and family number; node `cazy_id` holds the bare
family name.

## Hierarchy

Two levels via `Cazy_family_is_a_cazy_family`: `level_kind` `cazy_class`
(0) → `cazy_family` (1); the vocabulary also lists `cazy_subfamily`, but
no subfamily nodes are present. `gene_count` / `organism_count` are
subtree-inclusive on the class, direct on the family; `direct_gene_count`
is node-local.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `CazyFamily` |
| Gene → term edge | `Gene_has_cazy_family` |
| Hierarchy edges (child → parent) | `Cazy_family_is_a_cazy_family` |
| Fulltext index | `cazyFamilyFullText` |
| Trust axes on the gene edge | `sources`, `evidence`, `evidence_score` |
| Extra compact columns, `ontology_term_details` | `cazy_id`, `direct_gene_count` |
| Bridges out (`links_out`) | none |
| Bridges in (read from the source term) | `Interpro_entry_related_to_cazy_family` from `interpro` (*router*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`CazyFamily`)

| Property | Type | Meaning |
|---|---|---|
| `cazy_id` | string |  |
| `direct_gene_count` | int | genes attached to this exact node (not descendants); absent where it would be vacuous |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `level_kind` | string | what a level means in this ontology (see the vocabulary below) |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Controlled vocabularies

- `CazyFamily.level_kind`: `cazy_class`, `cazy_family`, `cazy_subfamily`
- `Gene_has_cazy_family.evidence`: `curated`, `family_inferred`, `domain_inferred`
- `Gene_has_cazy_family.sources`: `eggnog`, `interproscan`

Values are read from the KG's `ControlledVocabulary` nodes at build time; confirm live via `list_filter_values(filter_type=..., ontology='cazy')`.

## Interpretation

Family level is the unit — `cazy:GT2` (cellulose/chitin-synthase-like
transferases) and `cazy:GH23` (lytic transglycosylases) mean specific
chemistry, the class does not. CAZy is small in these genomes (tens of
families), so enrichment at level 1 works only for glycan-heavy gene sets;
otherwise use it as a per-gene annotation via `gene_ontology_terms`. Rank
by `evidence_score`; `curated` edges are rare and strong.

## Informativeness rule

No CAZy node is flagged uninformative. The six class roots are too broad
to enrich — use `level=1`.

## Pitfalls

- Family names are opaque (`GT2`, `GH13`); browse with
  `search_ontology(ontology=['cazy'], level=1)` and read `description` in
  verbose mode.
- A CAZy family says which fold/mechanism, not which sugar — substrate
  specificity varies within a family.
- InterPro → CAZy routing is recall-biased; when `router_ambiguous` is
  true on the InterPro term, look at the gene's own CAZy edge instead.

## Typical questions

- Which CAZy families does MIT1002 carry that MED4 lacks?
- Which glycosyltransferase families are enriched among genes up during biofilm or EPS production?
- Which InterPro entries route to `cazy:GH23`, and are those routings unambiguous?

## Tools

- `search_ontology(ontology=['cazy'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='cazy', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['cazy'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['cazy'])` then `pathway_enrichment` / `cluster_enrichment(ontology='cazy', level=N)` — ORA.

## See also

- `docs://ontologies/interpro`
- `docs://ontologies/pfam`
- `docs://ontologies/ec`
- `docs://analysis/annotation_evidence`
- `docs://analysis/enrichment`
- `docs://tools/ontology_term_details`
