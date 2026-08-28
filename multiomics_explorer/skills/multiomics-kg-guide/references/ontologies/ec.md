# EC numbers (`ec`)

Generated from `inputs/ontologies/ec.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

Enzyme Commission numbers — the four-field nomenclature of enzyme
*reactions* (`ec:1.1.1.1` alcohol dehydrogenase). An EC number names the
chemistry, not the protein: unrelated proteins that catalyse the same
reaction share one EC, and one protein can carry several. Each node also
carries `catalytic_activity`, `alternate_name` and `comments` lists from
the upstream enzyme record.

## How genes get annotated

Gene → EC edges are pooled from Cyanorak curation, eggNOG orthology
transfer, InterProScan and UniProt (`sources[]`), merged into one edge
per (gene, term) with compact `evidence` — `curated` or `family_inferred`
— and an `evidence_score` in [0, 1]. Edges are propagated up the
hierarchy: a gene with `ec:1.1.1.1` counts toward `ec:1.1.1.-`,
`ec:1.1.-.-` and `ec:1.-.-.-`. EC is also the entry point to the
reaction layer: the KEGG `Reaction` nodes a gene catalyses carry EC
numbers, and `genes_by_metabolite` / `metabolites_by_gene` accept
`ec_numbers=[...]` as a filter.

## Identifier form

`ec:1.1.1.1` — lowercase `ec:` prefix plus the dotted number. Partial
numbers use `-` for the unspecified fields: `ec:2.-.-.-` (class),
`ec:2.7.-.-` (subclass), `ec:2.7.1.-` (sub-subclass). Node names are the
accepted enzyme names (`Transferases`, `Hexokinase`).

## Hierarchy

A strict four-level tree, `level` 0-3: class (7 nodes), subclass,
sub-subclass, full four-field number (thousands of leaves). The tree is
exact — no DAG ambiguity, no `level_kind`. `gene_count` /
`organism_count` are subtree-inclusive; `direct_gene_count` counts genes
attached to that exact number (for a partial EC that means genes whose
best call stopped at that resolution). Children are the more specific
numbers; `ontology_term_details` lists them with `children_total` (a
subclass can have hundreds).

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `EcNumber` |
| Gene → term edge | `Gene_catalyzes_ec_number` |
| Hierarchy edges (child → parent) | `Ec_number_is_a_ec_number` |
| Fulltext index | `ecNumberFullText` |
| Trust axes on the gene edge | `sources`, `evidence`, `evidence_score` |
| Extra compact columns, `ontology_term_details` | `direct_gene_count` |
| Bridges out (`links_out`) | none |
| Bridges in (read from the source term) | `Interpro_entry_related_to_ec_number` from `interpro` (*router*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`EcNumber`)

| Property | Type | Meaning |
|---|---|---|
| `alternate_name` | list |  |
| `catalytic_activity` | list |  |
| `comments` | list |  |
| `direct_gene_count` | int | genes attached to this exact node (not descendants); absent where it would be vacuous |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Controlled vocabularies

Values: see `list_filter_values(filter_type=..., ontology='ec')` — `trust_axes`, `evidence`, `sources`, and the ontology-specific categorical filter types are read from the KG's `ControlledVocabulary` nodes at call time.

## Interpretation

Level 3 (full EC) is the interpretable unit for "which enzymes does this
organism carry"; levels 0-2 are useful for enrichment when full numbers
are too sparse. `evidence='curated'` edges (Cyanorak / UniProt) beat
`family_inferred` (eggNOG) — rank by `evidence_score` when two sources
disagree on the fourth field. An EC number without a KEGG `Reaction` in
the chemistry layer is still a valid annotation; the reaction layer is a
subset of EC space.

## Informativeness rule

No EC node is flagged uninformative — the seven class roots
(`ec:1.-.-.-` ... `ec:7.-.-.-`) are simply too broad to enrich, so pass
`level>=1` or let `max_gene_set_size` drop them. Partial numbers at levels
1-2 are legitimate enrichment units when leaf coverage is thin.

## Pitfalls

- An EC annotation is about reaction chemistry, not substrate: two
  enzymes with the same EC can act on different substrates in vivo. Use
  the reaction/metabolite tools for compound-level questions.
- Partial ECs (`ec:1.1.1.-`) are a real resolution level — a gene may be
  attached there because no source resolved the fourth field, not because
  it is "incomplete".
- InterPro entries link *out* to EC numbers as a `router` bridge
  (`Interpro_entry_related_to_ec_number`): recall-biased, often ambiguous
  (`router_ambiguous=True` on the InterPro term). It is a hint to look up
  the gene's own EC edge, never a function call.
- Genes with a `Gene_catalyzes_reaction` edge are a stricter set than
  genes with any EC edge — see `docs://analysis/metabolites`.

## Typical questions

- Which MED4 genes are annotated to nitrite reductase (`ec:1.7.1.4` / `ec:1.7.2.1`) and with what evidence?
- Which enzyme sub-subclasses are enriched among genes up in coculture?
- What full EC numbers sit under `ec:2.7.7.-` in this KG, and how many organisms carry each?
- Which InterPro entries route to this EC number, and is the routing ambiguous?

## Tools

- `search_ontology(ontology=['ec'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='ec', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['ec'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['ec'])` then `pathway_enrichment` / `cluster_enrichment(ontology='ec', level=N)` — ORA.

## See also

- `docs://ontologies/kegg`
- `docs://ontologies/interpro`
- `docs://ontologies/go_mf`
- `docs://analysis/metabolites`
- `docs://analysis/annotation_evidence`
- `docs://analysis/enrichment`
- `docs://tools/ontology_term_details`
