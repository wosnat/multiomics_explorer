# GO molecular function (`go_mf`)

Generated from `inputs/ontologies/go_mf.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

Gene Ontology *molecular function* — the biochemical activity a gene
product performs (e.g. `go:0003824` catalytic activity, `go:0005524` ATP
binding, `go:0015399` primary active transmembrane transporter activity).
Sister branches: `go_bp` (the process the activity serves) and `go_cc`
(where it happens).

## How genes get annotated

Same pooled pipeline as the other GO branches: Cyanorak curation, eggNOG
transfer, InterProScan signature-to-GO mapping, NCBI and UniProt records,
merged into one edge per (gene, term) with `sources[]`, a compact
`evidence` rung (`curated` / `family_inferred` / `domain_inferred`) and an
`evidence_score` in [0, 1] — rung semantics in
`docs://analysis/annotation_evidence`. Live on this edge type: eggNOG-only
edges read `family_inferred` (about 40% of the branch); curated sources
read `curated` (the largest rung on this branch); InterProScan-only edges
read `domain_inferred` or `family_inferred`.
Molecular function is the branch where `domain_inferred` is most common,
because a Pfam/InterPro domain maps naturally onto an activity (a kinase
domain implies kinase activity).

## Identifier form

`go:0003824` — `go:` prefix plus the seven-digit accession; the branch is
the node label (`MolecularFunction`). Pass `ontology='go_mf'` to the
branch-scoped tools; `ontology_term_details` accepts the bare ID.

## Hierarchy

DAG with `is_a` and `part_of` edges, about ten levels deep here; root
`go:0003674`. `level` is the shortest root path (`level_is_best_effort`
marks ambiguous depths). `gene_count` / `organism_count` are
subtree-inclusive, `direct_gene_count` is node-local; the two big level-1
branches, `catalytic activity` and `binding`, overlap heavily so their
counts do not add up.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `MolecularFunction` |
| Gene → term edge | `Gene_enables_molecular_function` |
| Hierarchy edges (child → parent) | `Molecular_function_is_a_molecular_function`, `Molecular_function_part_of_molecular_function` |
| Fulltext index | `molecularFunctionFullText` |
| Trust axes on the gene edge | `sources`, `evidence`, `evidence_score` |
| Extra compact columns, `ontology_term_details` | `direct_gene_count` |
| Bridges out (`links_out`) | none |
| Bridges in (read from the source term) | `Tcdb_family_enables_molecular_function` from `tcdb` (*composition*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`MolecularFunction`)

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

- `evidence` — `list_filter_values(filter_type="evidence", ontology="go_mf")`
- `sources` — `list_filter_values(filter_type="sources", ontology="go_mf")`

Values are read live from the KG's `ControlledVocabulary` nodes (`list_filter_values`); the list below is a build-time snapshot and may lag the KG. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="go_mf")`) lists which comparable axes the gene edge carries.

Vocabulary snapshot (build time):

- `Gene_enables_molecular_function.evidence`: `curated`, `family_inferred`, `domain_inferred`
- `Gene_enables_molecular_function.sources`: `cyanorak`, `eggnog`, `interproscan`, `ncbi`, `uniprot`

## Interpretation

Molecular-function terms are precise about *what* an enzyme does but say
nothing about pathway context — pair them with `go_bp`, KEGG or EC when the
question is "which pathway". `domain_inferred` edges are common and often
correct but broad (`ATP binding` on every P-loop protein); rank by
`evidence_score`; `curated` is backed by a reference source
(`cyanorak` / `uniprot` / `ncbi`), an eggNOG-only transfer reads
`family_inferred`. For enrichment, level 3-5 is the
usual working range — check `ontology_landscape` first.
Transporter-activity terms that GO defines with a substrate (a few
hundred terms, `Molecular_function_transports_metabolite` /
`…_chemical_role`) feed the `go_transport` route of `genes_by_metabolite`
/ `metabolites_by_gene`, which reads them by default: a term definition,
not a gene fact. Ask substrate questions there
(`go_namespace=['molecular_function']`), not through `genes_by_ontology`;
reading rules in `docs://analysis/transport`.

## Informativeness rule

Root `molecular_function` (`go:0003674`) is flagged uninformative. Level-1
`binding` / `catalytic activity` are unflagged but cover most of the
proteome; use `level` >= 2 or a `min_gene_count`/`max_gene_set_size` guard
instead of trusting them.

## Pitfalls

- Binding terms (`ATP binding`, `metal ion binding`) dominate any
  unfiltered enrichment — expect them and look past them.
- For "which genes move compound X" use `genes_by_metabolite` (the
  `go_transport` route reads these terms; `docs://analysis/transport`).
  TCDB families also bridge *out* to MF terms
  (`Tcdb_family_enables_molecular_function`, composition, forward-only —
  read it on the `tcdb` term, never on the GO term).
- Do not compare `evidence_score` to MEROPS scores — each is a
  within-ontology composite (TCDB carries no evidence score).

## Typical questions

- Which genes in MIT9313 have a non-domain-inferred oxidoreductase activity annotation? — `genes_by_ontology(ontology='go_mf', organism='MIT9313', term_ids=['go:0016491'], evidence=['curated','family_inferred'])`
- Which molecular functions are enriched in a co-expression cluster? — `cluster_enrichment(organism='MED4', analysis_id=..., ontology='go_mf', level=3)`
- Which MED4 genes carry an MF term defined as moving urea? — `genes_by_metabolite(metabolite_ids=['kegg.compound:C00086'], organism='MED4', evidence_sources=['go_transport'], go_namespace=['molecular_function'])`
- What is the sub-hierarchy under `go:0016491` oxidoreductase activity, and how many genes sit at each child? — `ontology_term_details(term_ids=['go:0016491'])` and read `children[]`
- Which TCDB families are characterised by `go:0005215` transporter activity? — the bridge runs from `tcdb` to GO only, so `run_cypher` over `Tcdb_family_enables_molecular_function`, or start from a `tcdb` term with `ontology_term_details`

## Tools

- `search_ontology(ontology=['go_mf'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='go_mf', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['go_mf'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['go_mf'])` then `pathway_enrichment` / `cluster_enrichment(ontology='go_mf', level=N)` — ORA.

## See also

- `docs://ontologies/go_bp`
- `docs://ontologies/go_cc`
- `docs://ontologies/ec`
- `docs://ontologies/tcdb`
- `docs://analysis/transport`
- `docs://analysis/annotation_evidence`
- `docs://analysis/enrichment`
- `docs://tools/genes_by_ontology`
- `docs://tools/ontology_term_details`
