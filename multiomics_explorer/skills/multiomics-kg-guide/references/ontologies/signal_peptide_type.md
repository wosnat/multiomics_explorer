# SignalP signal-peptide type (`signal_peptide_type`)

Generated from `inputs/ontologies/signal_peptide_type.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

SignalP predicted signal-peptide type — a *structural* ontology of five
N-terminal signal classes: `signalp_SP` (Sec/SPI, classic secretory),
`signalp_LIPO` (Sec/SPII, lipoprotein), `signalp_TAT` (Tat/SPI, folded
export), `signalp_TATLIPO` (Tat/SPII) and `signalp_PILIN` (Sec/SPIII,
type IV pilin-like). It says how a protein is handled at the membrane
during export, not where it ends up or what it does.

## How genes get annotated

SignalP (v6-style multi-class prediction) assigns each protein the most
probable signal class with a `probability` on [0, 1]; proteins predicted
to have no signal peptide carry no edge. Where a cleavage site is
predicted the edge also carries `cleavage_site` (residue position) and
`cleavage_probability`. All three are verbose-only, under the names
`signal_peptide_probability`, `signal_peptide_cleavage_site`,
`signal_peptide_cleavage_probability`. No trust axes — trust filters
raise for this ontology.

## Identifier form

`signalp_SP` — the `signalp_` prefix plus the SignalP class name in upper
case; node `signalp_id` holds the same string.

## Hierarchy

Flat: five nodes, all `level=0`, no hierarchy edges. `gene_count` /
`organism_count` are direct; one edge per gene at most.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `SignalPeptideType` |
| Gene → term edge | `Gene_has_signal_peptide_type` |
| Hierarchy edges | none — flat ontology (`level=0` only, nothing to expand) |
| Fulltext index | `signalPeptideTypeFullText` |
| Trust axes on the gene edge | none — native scalars only |
| Verbose edge detail | `signal_peptide_probability` (edge prop `probability`), `signal_peptide_cleavage_site` (edge prop `cleavage_site`), `signal_peptide_cleavage_probability` (edge prop `cleavage_probability`) |
| Extra compact columns, `ontology_term_details` | `signalp_id` |
| Bridges out (`links_out`) | none |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`SignalPeptideType`)

| Property | Type | Meaning |
|---|---|---|
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |
| `signalp_id` | string | SignalP signal-peptide type code as emitted by the tool (e.g. `SP`, `LIPO`, `TAT`) |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

none — the gene edge carries native scalars only (no trust axes, no ontology-owned categorical, no bridges), so no `list_filter_values` type is scoped to this ontology. Values on other tools' filters are still read live from the KG's `ControlledVocabulary` nodes at call time.

## Interpretation

The natural companion to PSORTb and to the exoproteome / vesicle
compartments: a signal peptide plus an envelope PSORTb call is strong
evidence of a secreted or surface protein; `LIPO` marks lipoproteins
(surface-anchored, vesicle-enriched); `TAT` marks proteins exported
folded, often cofactor-containing. Probability is SignalP-internal —
rank within the ontology, never threshold across ontologies.

## Informativeness rule

Nothing is flagged; five terms. `signalp_SP` is by far the largest class
and behaves as the catch-all in any enrichment.

## Pitfalls

- Absence of an edge means "no signal peptide predicted", which is
  itself a call — but it is not represented as a term.
- `level=1` returns nothing (flat).
- Signal-peptide type is not localization: a `SP` protein may be
  periplasmic, outer-membrane or extracellular — read PSORTb for that.
- Cleavage fields are sparse (absent where SignalP reports no site).

## Typical questions

- Which MIT1002 genes carry a Tat signal peptide? — `genes_by_ontology(ontology='signal_peptide_type', organism='MIT1002', term_ids=['signalp_TAT'])`, then intersect with `differential_expression_by_gene`
- How many predicted lipoproteins does each organism have, and are they enriched in the vesicle proteome?
- Which secreted-protein candidates (SP + PSORTb extracellular) respond to nitrogen limitation?

## Tools

- `search_ontology(ontology=['signal_peptide_type'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='signal_peptide_type', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['signal_peptide_type'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['signal_peptide_type'])` then `pathway_enrichment` / `cluster_enrichment(ontology='signal_peptide_type', level=N)` — ORA.

## See also

- `docs://ontologies/subcellular_localization`
- `docs://ontologies/go_cc`
- `docs://guide/concepts`
- `docs://tools/gene_ontology_terms`
- `docs://tools/ontology_term_details`
