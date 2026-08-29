# PSORTb subcellular localization (`subcellular_localization`)

Generated from `inputs/ontologies/subcellular_localization.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

PSORTb predicted subcellular localization — a *structural* ontology of
five compartments for Gram-negative bacteria: `psortb_Cytoplasmic`,
`psortb_CytoplasmicMembrane`, `psortb_Periplasmic`, `psortb_OuterMembrane`,
`psortb_Extracellular`. It says where a protein is predicted to reside,
not what it does. Each gene carries at most one call.

## How genes get annotated

PSORTb combines signal-peptide, transmembrane-helix, motif and
homology modules into one localization call with a confidence
`score` on [7.5, 10.0] (the KG keeps only calls above PSORTb's reporting
threshold; proteins PSORTb leaves "Unknown" have no edge). The score is
exposed as `localization_score` in verbose mode. No trust axes — a single
predictor, so `sources`/`evidence` are not carried and the trust filters
raise for this ontology.

## Identifier form

`psortb_Cytoplasmic` — the `psortb_` prefix plus the PSORTb compartment
name (CamelCase, no separators); node `psortb_id` holds the same string.

## Hierarchy

Flat: five nodes, all `level=0`, no hierarchy edges. `gene_count` /
`organism_count` are direct; no `direct_gene_count`.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `SubcellularLocalization` |
| Gene → term edge | `Gene_has_subcellular_localization` |
| Hierarchy edges | none — flat ontology (`level=0` only, nothing to expand) |
| Fulltext index | `subcellularLocalizationFullText` |
| Trust axes on the gene edge | none — native scalars only |
| Verbose edge detail | `localization_score` (edge prop `score`) |
| Extra compact columns, `ontology_term_details` | `psortb_id` |
| Bridges out (`links_out`) | none |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`SubcellularLocalization`)

| Property | Type | Meaning |
|---|---|---|
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |
| `psortb_id` | string | PSORTb localization label as emitted by the tool (e.g. `CytoplasmicMembrane`) |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

none — the gene edge carries native scalars only (no trust axes, no ontology-owned categorical, no bridges), so no `list_filter_values` type is scoped to this ontology. Values on other tools' filters are still read live from the KG's `ControlledVocabulary` nodes at call time.

## Interpretation

Use as a filter or a grouping axis, not a functional call: "which of the
up-regulated genes are predicted outer-membrane or extracellular" is the
natural question, and pairs with SignalP (`signal_peptide_type`) and the
vesicle / exoproteome compartments in the expression layer. Higher
`localization_score` is more confident, but the score is PSORTb-internal
— compare within this ontology only. `Cytoplasmic` and
`CytoplasmicMembrane` cover most of every proteome; the three envelope /
outside compartments are where the biology usually is.

## Informativeness rule

Nothing is flagged; with five terms `informative_only` is moot. For
enrichment the two large compartments will dominate — restrict the
question to the envelope compartments.

## Pitfalls

- `level=1` returns nothing; the ontology is flat.
- No edge for a gene means PSORTb returned "Unknown" (below threshold),
  not cytoplasmic — treat absence as no call.
- PSORTb was trained on Gram-negative models; for cyanobacterial
  thylakoid proteins "CytoplasmicMembrane" is the best it can say.
- Trust filters (`sources`, `evidence`, `min_evidence_score`) raise here;
  `localization_score` is verbose-only and never filterable.

## Typical questions

- Which MED4 genes are predicted outer-membrane or extracellular? — `genes_by_ontology(ontology='subcellular_localization', organism='MED4', term_ids=['psortb_OuterMembrane','psortb_Extracellular'])`, then intersect with `differential_expression_by_gene`
- How many predicted periplasmic proteins does each organism carry?
- Is this gene's PSORTb call consistent with its SignalP signal peptide and its GO cellular-component annotation?

## Tools

- `search_ontology(ontology=['subcellular_localization'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='subcellular_localization', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['subcellular_localization'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['subcellular_localization'])` then `pathway_enrichment` / `cluster_enrichment(ontology='subcellular_localization', level=N)` — ORA.

## See also

- `docs://ontologies/signal_peptide_type`
- `docs://ontologies/go_cc`
- `docs://guide/concepts`
- `docs://tools/gene_ontology_terms`
- `docs://tools/ontology_term_details`
