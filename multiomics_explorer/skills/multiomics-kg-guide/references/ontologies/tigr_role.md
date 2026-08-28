# TIGR roles (`tigr_role`)

Generated from `inputs/ontologies/tigr_role.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

TIGR (JCVI) functional roles — the classic "main role / sub role" scheme
from TIGR genome annotation (`tigr.role:164` Energy metabolism /
Photosynthesis, `tigr.role:156` Hypothetical proteins / Conserved). In
this KG the roles arrive through Cyanorak's curation layer, which carries
a TIGR role alongside its own role for each gene cluster.

## How genes get annotated

All edges are `evidence='curated'`, `sources=['cyanorak']` — the TIGR role
Cyanorak curators attached to the ortholog cluster. Same coverage boundary
as `cyanorak_role`: only Cyanorak-covered picocyanobacteria carry TIGR
roles; Alteromonas genes have none. No `evidence_score`.

## Identifier form

`tigr.role:164` — prefix plus the TIGR role numeric ID; node `code` is the
bare number, `name` the "Main role / Sub role" string.

## Hierarchy

Flat in the KG: every node is `level=0`, no hierarchy edges. The main-role
/ sub-role pairing lives inside `name`, not as a parent–child edge, so
there is no rollup from sub role to main role. `gene_count` /
`organism_count` are direct.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `TigrRole` |
| Gene → term edge | `Gene_has_tigr_role` |
| Hierarchy edges | none — flat ontology (`level=0` only, nothing to expand) |
| Fulltext index | `tigrRoleFullText` |
| Trust axes on the gene edge | `sources`, `evidence` |
| Extra compact columns, `ontology_term_details` | `code` |
| Bridges out (`links_out`) | none |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`TigrRole`)

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

Values: see `list_filter_values(filter_type=..., ontology='tigr_role')` — `trust_axes`, `evidence`, `sources`, and the ontology-specific categorical filter types are read from the KG's `ControlledVocabulary` nodes at call time.

## Interpretation

A second curated, picocyanobacteria-scoped functional axis, at roughly the
granularity of a Cyanorak level-1 role but with different boundaries
(TIGR splits energy metabolism finely, lumps regulation). Useful as a
cross-check on a Cyanorak enrichment, or when a question is phrased in
TIGR vocabulary. Same organism-coverage caveat as Cyanorak.

## Informativeness rule

The hypothetical / unknown-function roles (`tigr.role:156` and sibling
"Unknown function" entries) are flagged uninformative and dropped by
`informative_only=True`.

## Pitfalls

- Flat: `level=1` returns nothing; to group by main role, split `name` on
  ` / ` client-side.
- Coverage bounded to Cyanorak-covered organisms — check
  `genome_coverage` in `ontology_landscape` before enriching a mixed
  organism set.
- Roles are broad (a hundred-odd nodes for a whole genome); use them for
  composition and coarse enrichment, not gene-level function.

## Typical questions

- Which TIGR sub roles are enriched among genes down at night in the diel experiment?
- How many MED4 genes fall under each TIGR main role?
- Does the TIGR role agree with the Cyanorak role for this gene set?

## Tools

- `search_ontology(ontology=['tigr_role'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='tigr_role', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['tigr_role'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['tigr_role'])` then `pathway_enrichment` / `cluster_enrichment(ontology='tigr_role', level=N)` — ORA.

## See also

- `docs://ontologies/cyanorak_role`
- `docs://ontologies/cog_category`
- `docs://analysis/enrichment`
- `docs://tools/ontology_landscape`
- `docs://tools/ontology_term_details`
