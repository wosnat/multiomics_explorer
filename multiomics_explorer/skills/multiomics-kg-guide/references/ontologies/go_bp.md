# GO biological process (`go_bp`)

Generated from `inputs/ontologies/go_bp.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

Gene Ontology *biological process* — the "what larger program is this gene
part of" branch of GO (e.g. `go:0006979` response to oxidative stress,
`go:0015979` photosynthesis). One of three GO branches; the other two are
`go_mf` (activity) and `go_cc` (location). GO is the most widely used
cross-species functional vocabulary, so it is the safest choice for
comparing Prochlorococcus, Synechococcus and Alteromonas on one axis.

## How genes get annotated

Gene → term edges are pooled from several annotation sources (`sources[]`
on the edge: Cyanorak curation, eggNOG orthology transfer, InterProScan
signature-to-GO mapping, NCBI and UniProt records). Each edge carries a
compact `evidence` rung (`curated` / `family_inferred` /
`domain_inferred`) and an `evidence_score` composite in [0, 1] that
rewards agreement between sources; the rung semantics are defined once
in `docs://analysis/annotation_evidence`. On this edge type the live
mapping is: eggNOG-only edges read `family_inferred` (the bulk of the
edges, ~434k), curated sources (`cyanorak` / `ncbi` / `uniprot`) read
`curated`, and InterProScan-only edges read `family_inferred` or
`domain_inferred`.
Annotation is propagated: a gene annotated to a specific term counts
toward every ancestor through `is_a` and `part_of`.

## Identifier form

`go:0006979` — lowercase `go:` prefix plus the seven-digit GO accession,
shared across all three branches (the branch is the node label, not the
prefix). A GO ID from any branch works in `ontology_term_details`; for the
branch-scoped tools pass `ontology='go_bp'`.

## Hierarchy

A directed acyclic graph, not a tree: a term can have several parents via
`is_a` and `part_of`, so `level` is the *shortest* path from the root
`go:0008150` and `level_is_best_effort='true'` flags terms whose depth is
ambiguous. Roughly twelve levels deep in this KG (root at 0, a long tail
past level 8). `gene_count` / `organism_count` are subtree-inclusive
(a gene counts toward every ancestor), `direct_gene_count` counts only
genes attached to that exact node — and because of the DAG, sibling
`gene_count`s do not sum to the parent's.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `BiologicalProcess` |
| Gene → term edge | `Gene_involved_in_biological_process` |
| Hierarchy edges (child → parent) | `Biological_process_is_a_biological_process`, `Biological_process_part_of_biological_process` |
| Fulltext index | `biologicalProcessFullText` |
| Trust axes on the gene edge | `sources`, `evidence`, `evidence_score` |
| Extra compact columns, `ontology_term_details` | `direct_gene_count` |
| Bridges out (`links_out`) | none |
| Bridges in (read from the source term) | `Tcdb_family_involved_in_biological_process` from `tcdb` (*composition*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`BiologicalProcess`)

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

- `evidence` — `list_filter_values(filter_type="evidence", ontology="go_bp")`
- `sources` — `list_filter_values(filter_type="sources", ontology="go_bp")`

Values are read live from the KG's `ControlledVocabulary` nodes at call time; this page never quotes them. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="go_bp")`) lists which comparable axes the gene edge carries.

Snapshot of vocabulary values at build time (`--live-vocab`):

- `BiologicalProcess.is_uninformative`: `true`
- `BiologicalProcess.level_is_best_effort`: `true`
- `Gene_involved_in_biological_process.evidence`: `curated`, `family_inferred`, `domain_inferred`
- `Gene_involved_in_biological_process.sources`: `cyanorak`, `eggnog`, `interproscan`, `ncbi`, `uniprot`

## Interpretation

`curated` now means a reference source (`cyanorak` / `ncbi` / `uniprot`);
an eggNOG orthology transfer reads `family_inferred` with
`evidence_score` 0.333, so rank by `evidence_score` when two annotations
of one gene compete. Use `evidence_score` to *rank* competing annotations of one
gene within GO, never as a cross-ontology threshold; `min_evidence_score`
exists as the single numeric cutoff if a stricter set is needed. Two
organisms annotated to the same process at level 3 are comparable; a
level-8 term with three genes in one organism is a curiosity, not a
signal. For enrichment, level 3-5 usually balances coverage against term
size — confirm with `ontology_landscape(ontology=['go_bp'])`.

## Informativeness rule

The root `biological_process` (`go:0008150`) is flagged uninformative and
dropped by `informative_only=True` (the default on enrichment). Levels 1-2
(`cellular process`, `metabolic process`) are not flagged but carry most of
the genome; treat any term whose `gene_count` is a large fraction of the
organism's genes as a catch-all.

## Pitfalls

- DAG depth is approximate: a level-3 term can be more specific than a
  level-4 term on another branch; check `level_is_best_effort`.
- Subtree counts overlap — never sum `gene_count` across siblings.
- `domain_inferred` GO terms come from InterPro signatures and can be very
  broad (a single ATP-binding domain implies `go:0005524` for every
  ATPase); rank rather than trust them equally with `curated`.
- TCDB families link *out* to GO terms (composition); the bridge is
  forward-only, so `ontology_term_details` on a GO term shows no TCDB
  links — walk it from the `tcdb` term, or use `run_cypher` over
  `Tcdb_family_involved_in_biological_process` for the reverse
  direction.

## Typical questions

- Which MED4 genes are annotated to response to oxidative stress, and how strong is each annotation? — `genes_by_ontology(ontology='go_bp', organism='MED4', term_ids=['go:0006979'], verbose=True)`
- Which GO biological processes are enriched among genes up under nitrogen starvation? — `pathway_enrichment(organism='MED4', experiment_ids=[...], ontology='go_bp', level=4, direction='up')`
- How many organisms carry at least one gene annotated to photosynthesis? — `ontology_term_details(term_ids=['go:0015979'])` and read `organism_count`
- What are the parents and children of `go:0006979`? — `ontology_term_details(term_ids=['go:0006979'])`; for the TCDB families built from a process, start from the `tcdb` term (the bridge is forward-only)

## Tools

- `search_ontology(ontology=['go_bp'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='go_bp', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['go_bp'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['go_bp'])` then `pathway_enrichment` / `cluster_enrichment(ontology='go_bp', level=N)` — ORA.

## See also

- `docs://ontologies/go_mf`
- `docs://ontologies/go_cc`
- `docs://analysis/annotation_evidence`
- `docs://analysis/enrichment`
- `docs://guide/conventions`
- `docs://tools/genes_by_ontology`
- `docs://tools/ontology_term_details`
