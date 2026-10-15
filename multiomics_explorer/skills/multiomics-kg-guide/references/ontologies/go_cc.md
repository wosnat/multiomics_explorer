# GO cellular component (`go_cc`)

Generated from `inputs/ontologies/go_cc.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

Gene Ontology *cellular component* — where a gene product is found
(e.g. `go:0005886` plasma membrane, `go:0009522` photosystem I,
`go:0005840` ribosome). Sister branches: `go_bp` and `go_mf`. It is a
functional-vocabulary view of location; the *predicted* localization of
each protein is a separate, flat ontology (`subcellular_localization`,
PSORTb).

## How genes get annotated

Same pooled GO pipeline: Cyanorak, eggNOG, InterProScan, NCBI, UniProt
merged into one edge per (gene, term) with `sources[]`, compact `evidence`
(`curated` / `family_inferred` / `domain_inferred`) and `evidence_score`;
rung semantics in `docs://analysis/annotation_evidence`. Live on this
edge type: eggNOG-only edges read `family_inferred` (the majority,
~100k), curated sources read `curated`, InterProScan-only edges read
`family_inferred` or `domain_inferred`.

## Identifier form

`go:0005886` — `go:` prefix plus the seven-digit accession; the branch is
the node label (`CellularComponent`). Use `ontology='go_cc'` on the
branch-scoped tools.

## Hierarchy

The shallowest GO branch here (about seven levels; root `go:0005575`).
`part_of` matters more than in the other branches — a photosystem subunit
is `part_of` the photosystem, which is `part_of` the thylakoid membrane —
so `level` is a min-path proxy and `level_is_best_effort` is set on many
terms. Counts are subtree-inclusive (`gene_count`, `organism_count`) with
`direct_gene_count` node-local; level 1 is almost the whole proteome.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `CellularComponent` |
| Gene → term edge | `Gene_located_in_cellular_component` |
| Hierarchy edges (child → parent) | `Cellular_component_is_a_cellular_component`, `Cellular_component_part_of_cellular_component` |
| Fulltext index | `cellularComponentFullText` |
| Trust axes on the gene edge | `sources`, `evidence`, `evidence_score` |
| Extra compact columns, `ontology_term_details` | `direct_gene_count` |
| Bridges out (`links_out`) | none |
| Bridges in (read from the source term) | `Tcdb_family_located_in_cellular_component` from `tcdb` (*composition*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`CellularComponent`)

| Property | Type | Meaning |
|---|---|---|
| `direct_gene_count` | int | genes attached to this exact node (not descendants); absent where it would be vacuous |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `level_is_best_effort` | string | sparse `'true'` flag — DAG term whose depth is a min-path proxy |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

- `evidence` — `list_filter_values(filter_type="evidence", ontology="go_cc")`
- `sources` — `list_filter_values(filter_type="sources", ontology="go_cc")`

Values are read live from the KG's `ControlledVocabulary` nodes at call time; this page never quotes them. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="go_cc")`) lists which comparable axes the gene edge carries.

Snapshot of vocabulary values at build time (`--live-vocab`):

- `CellularComponent.is_uninformative`: `true`
- `CellularComponent.level_is_best_effort`: `true`
- `Gene_located_in_cellular_component.evidence`: `curated`, `family_inferred`, `domain_inferred`
- `Gene_located_in_cellular_component.sources`: `cyanorak`, `eggnog`, `interproscan`, `ncbi`, `uniprot`

## Interpretation

Useful for "which complexes / compartments does this gene set touch"
questions — photosystem, phycobilisome, ribosome, membrane complexes,
carboxysome (`go:0031470`). For per-protein predicted localization use
PSORTb (`subcellular_localization`), which is 1:1 and scored; GO CC is
many-to-one and evidence-graded. For enrichment, level 2-4 is where the
named complexes live; level 1 (`cellular anatomical structure`) is a
catch-all.

## Informativeness rule

Root `cellular_component` (`go:0005575`) is flagged uninformative. Level 1
(`cellular anatomical structure`, `protein-containing complex`) is
unflagged but covers nearly everything; pass `level>=2` or
`max_gene_set_size` when enriching.

## Pitfalls

- `go:0016020` membrane and `go:0005886` plasma membrane are large and
  mostly `domain_inferred`; treat membrane enrichment as a weak signal
  unless corroborated by PSORTb or SignalP.
- Cyanobacterial compartments (thylakoid, carboxysome, phycobilisome)
  have no counterpart in Alteromonas — cross-organism comparison at those
  terms is structurally zero, not biologically absent.
- TCDB families bridge *out* to GO CC terms
  (`Tcdb_family_located_in_cellular_component`); the bridge is
  forward-only — read it on the `tcdb` term.

## Typical questions

- Which MED4 genes are annotated to the carboxysome, and with what evidence? — `genes_by_ontology(ontology='go_cc', organism='MED4', term_ids=['go:0031470'], verbose=True)`
- Are ribosome or photosystem components over-represented among down-regulated genes in darkness?
- What sits under `go:0034357` photosynthetic membrane in this KG? — `ontology_term_details(term_ids=['go:0034357'])`
- Does the GO CC annotation agree with PSORTb's predicted localization for this gene?

## Tools

- `search_ontology(ontology=['go_cc'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='go_cc', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['go_cc'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['go_cc'])` then `pathway_enrichment` / `cluster_enrichment(ontology='go_cc', level=N)` — ORA.

## See also

- `docs://ontologies/go_bp`
- `docs://ontologies/go_mf`
- `docs://ontologies/subcellular_localization`
- `docs://ontologies/signal_peptide_type`
- `docs://analysis/annotation_evidence`
- `docs://analysis/enrichment`
- `docs://tools/ontology_term_details`
