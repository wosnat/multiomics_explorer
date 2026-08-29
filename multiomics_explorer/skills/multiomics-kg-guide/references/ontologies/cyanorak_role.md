# Cyanorak roles (`cyanorak_role`)

Generated from `inputs/ontologies/cyanorak_role.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

Cyanorak functional roles — the curated, cyanobacteria-specific role
hierarchy of the Cyanorak information system for marine picocyanobacteria
(Prochlorococcus and Synechococcus). Roles are named for the biology these
genomes actually contain (photosynthesis, phycobilisome, nutrient
acquisition, DNA metabolism, ...) with a three-level tree
(`cyanorak.role:D` Cellular processes → `cyanorak.role:D.2` Cell
division → ...).

## How genes get annotated

Every edge is `evidence='curated'` from `sources=['cyanorak']`: a Cyanorak
curator assigned the role to the gene's ortholog cluster. That makes this
the highest-trust functional annotation in the KG, but only for genomes
Cyanorak covers — Alteromonas and other non-picocyanobacteria have no
Cyanorak roles at all. No `evidence_score` (single source, single rung).

## Identifier form

`cyanorak.role:D` (level 0, a letter), `cyanorak.role:D.2` (level 1),
`cyanorak.role:D.2.1`-style codes (level 2). One root is not a letter:
`cyanorak.role:0` Non-coding gene (RNA), with four children. Node `code`
holds the bare dotted code; `name` is the full breadcrumb
(`Cellular processes > Cell division`).

## Hierarchy

Strict three-level tree via `Cyanorak_role_is_a_cyanorak_role`, `level`
0-2: 19 roots (18 letters plus `cyanorak.role:0`), 124 level-1 roles,
30 level-2 roles. `gene_count` / `organism_count` are
subtree-inclusive; `direct_gene_count` is node-local (most roots have
genes attached directly as well as through children). Level exact — no
DAG ambiguity.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `CyanorakRole` |
| Gene → term edge | `Gene_has_cyanorak_role` |
| Hierarchy edges (child → parent) | `Cyanorak_role_is_a_cyanorak_role` |
| Fulltext index | `cyanorakRoleFullText` |
| Trust axes on the gene edge | `sources`, `evidence` |
| Extra compact columns, `ontology_term_details` | `code`, `direct_gene_count` |
| Bridges out (`links_out`) | none |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`CyanorakRole`)

| Property | Type | Meaning |
|---|---|---|
| `code` | string | source-database short code (COG one-letter category, Cyanorak / TIGR numeric role code) — the un-prefixed tail of `id` |
| `direct_gene_count` | int | genes attached to this exact node (not descendants); absent where it would be vacuous |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

- `evidence` — `list_filter_values(filter_type="evidence", ontology="cyanorak_role")`
- `sources` — `list_filter_values(filter_type="sources", ontology="cyanorak_role")`

Values are read live from the KG's `ControlledVocabulary` nodes at call time; this page never quotes them. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="cyanorak_role")`) lists which comparable axes the gene edge carries.

## Interpretation

The go-to axis for Prochlorococcus/Synechococcus enrichment: curated,
organism-appropriate, and sized for these small genomes. Level 1 is the
usual enrichment unit (a few dozen roles of tens to hundreds of genes
each); level 0 is genome-composition scale. Cross-organism comparisons
are only meaningful *within* the picocyanobacteria — a zero for
Alteromonas means "not covered", never "absent".

## Informativeness rule

Five roles are flagged uninformative and dropped by
`informative_only=True`: the root `cyanorak.role:R` Other and its
children `R.1` Conserved hypothetical domains, `R.2` Conserved
hypothetical proteins, `R.4` Hypothetical proteins and `R.5` Other >
Other. They are the largest roles in every genome.

## Pitfalls

- Coverage is organism-bounded: `organism_count` tops out at the number of
  Cyanorak-covered genomes, and a cross-organism enrichment that includes
  Alteromonas will silently have half its background unannotated. Check
  `ontology_landscape(ontology=['cyanorak_role'], organism=...)`
  `genome_coverage` first.
- Curated does not mean specific — `Other > Conserved hypothetical
  proteins` is curated too.
- Role names are breadcrumbs; search the last segment (`search_text`) or
  browse with `level=1`.

## Typical questions

- Which Cyanorak roles are enriched among MED4 genes up under iron limitation? — `pathway_enrichment(organism='MED4', experiment_ids=[...], ontology='cyanorak_role', level=1, direction='up')`
- How many genes per level-1 role does MIT9313 carry vs MED4? — `genes_by_ontology(ontology='cyanorak_role', organism='MIT9313', level=1, summary=True)`
- Which MED4 genes are curated under Photosynthesis and respiration? — `genes_by_ontology(ontology='cyanorak_role', organism='MED4', term_ids=['cyanorak.role:J'])`
- Which organisms in the KG have Cyanorak coverage at all? — `ontology_term_details(term_ids=['cyanorak.role:J'], verbose=True)` and read `genes_by_organism[]`

## Tools

- `search_ontology(ontology=['cyanorak_role'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='cyanorak_role', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['cyanorak_role'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['cyanorak_role'])` then `pathway_enrichment` / `cluster_enrichment(ontology='cyanorak_role', level=N)` — ORA.

## See also

- `docs://ontologies/tigr_role`
- `docs://ontologies/cog_category`
- `docs://ontologies/go_bp`
- `docs://analysis/enrichment`
- `docs://analysis/annotation_evidence`
- `docs://tools/ontology_landscape`
- `docs://tools/ontology_term_details`
