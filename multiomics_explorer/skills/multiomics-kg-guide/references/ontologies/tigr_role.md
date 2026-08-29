# TIGR roles (`tigr_role`)

Generated from `inputs/ontologies/tigr_role.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

TIGR (JCVI) functional roles — the classic "main role / sub role" scheme
from TIGR genome annotation (`tigr.role:164` Energy metabolism /
Photosynthesis, `tigr.role:156` Hypothetical proteins / Conserved). The
role vocabulary and the family-to-role assignments come from JCVI's
frozen TIGRFAMs 15.0 role archive; in this KG the gene-level roles arrive
from two sources (see `method`).

## How genes get annotated

Two sources feed `Gene_has_tigr_role`:

- **Cyanorak curation** — the TIGR role Cyanorak curators attached to the
  ortholog cluster. `sources=['cyanorak']`, `evidence='curated'`. Covers
  only the 22 Cyanorak-annotated picocyanobacteria.
- **NCBIfam family inference** — for each gene's NCBIfam hit whose family
  is `family_type='equivalog'` (same function in every member) and carries
  an archived TIGR role, the KG asserts that role on the gene.
  `sources=['interproscan']`, `evidence='family_inferred'`. Covers all
  organisms, heterotrophs included. Non-equivalog families never produce
  a gene edge — they reach a role only through the
  `Ncbifam_family_has_tigr_role` router bridge (see
  `docs://ontologies/ncbifam`), which is a lookup aid, not an annotation.

When both sources name the same role for a gene they are merged into ONE
edge with `sources=['cyanorak','interproscan']` and `evidence='curated'`
(curated wins the ladder). When they disagree the gene carries two
separate edges, distinguishable by `evidence`. The tools' `sources=`
filter matches by membership, so `sources=['cyanorak']` keeps the merged
edges; in raw Cypher use `'cyanorak' IN r.sources`, not
`r.sources = ['cyanorak']`. No `evidence_score`.

## Identifier form

Subroles: `tigr.role:164` — prefix plus the TIGR role numeric ID; node
`code` is the bare number, `name` the compound "Main role / Sub role"
string. Mainroles: `tigr.role:energy_metabolism` — prefix plus a slug of
the main-role text; node `code` is the slug, `name` the main-role text.
Two Cyanorak-only roots keep numeric ids — `tigr.role:856` "Not Found"
and `tigr.role:270` "Disrupted reading frame /" — so `level_kind`, not
the id shape, is the reliable level discriminator.

## Hierarchy

Two-level tree via `Tigr_role_is_a_tigr_role` (subrole → mainrole, one
parent per subrole): 21 roots at `level=0` (`level_kind='tigr_mainrole'`
— 19 slug-id mainroles plus the two numeric roots) and 115 subroles at
`level=1` (`level_kind='tigr_subrole'`).

Genes attach to subroles, except on the two numeric roots, which have
no subrole and carry a few hundred Cyanorak genes directly. A `level=1`
selection therefore misses those genes while a `level=0` rollup includes
them (MED4: 1,758 genes at level 1 vs 1,766 at level 0). `gene_count` /
`organism_count` are subtree-inclusive, so a mainrole's `gene_count` is
the union over its children and its `direct_gene_count` is 0; do not mix
levels in one ORA without collapsing them first. `ncbifam_family_count`
is the number of NCBIfam families bridged to the role via
`Ncbifam_family_has_tigr_role`, subtree-summed on mainroles.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `TigrRole` |
| Gene → term edge | `Gene_has_tigr_role` |
| Hierarchy edges (child → parent) | `Tigr_role_is_a_tigr_role` |
| Fulltext index | `tigrRoleFullText` |
| Trust axes on the gene edge | `sources`, `evidence` |
| Extra compact columns, `ontology_term_details` | `code`, `direct_gene_count`, `ncbifam_family_count` |
| Bridges out (`links_out`) | none |
| Bridges in (read from the source term) | `Ncbifam_family_has_tigr_role` from `ncbifam` (*router*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`TigrRole`)

| Property | Type | Meaning |
|---|---|---|
| `code` | string | source-database short code (COG one-letter category, Cyanorak / TIGR numeric role code) — the un-prefixed tail of `id` |
| `direct_gene_count` | int | genes attached to this exact node (not descendants); absent where it would be vacuous |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `level_kind` | string | what a level means in this ontology (e.g. `tc_family`, `pathway`) — read values via `list_filter_values` |
| `name` | string | term name (what `search_ontology` indexes) |
| `ncbifam_family_count` | int | NCBIfam families bridged to this role via `Ncbifam_family_has_tigr_role`; subtree sum on mainroles |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

- `evidence` — `list_filter_values(filter_type="evidence", ontology="tigr_role")`
- `sources` — `list_filter_values(filter_type="sources", ontology="tigr_role")`

Values are read live from the KG's `ControlledVocabulary` nodes at call time; this page never quotes them. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="tigr_role")`) lists which comparable axes the gene edge carries.

## Interpretation

A functional axis at roughly the granularity of a Cyanorak level-1 role
but with different boundaries (TIGR splits energy metabolism finely,
lumps regulation), and — unlike `cyanorak_role` — comparable across
genera: every organism carries roles, so "which roles dominate the
Alteromonas response" is a first-class question. Coverage is uneven:
inferred coverage is bounded by NCBIfam hits and the equivalog gate, so
under a fifth of an Alteromonas genome carries a role, versus ~90% of
MED4 where curated Cyanorak roles dominate. Level 1 (subroles) is the
usual enrichment unit; level 0 (mainroles) is genome-composition scale.

## Informativeness rule

Nine roles are flagged uninformative and dropped by
`informative_only=True`: five roots — the two numeric roots plus
`tigr.role:hypothetical_proteins`, `tigr.role:unclassified`,
`tigr.role:unknown_function` — and four subroles `tigr.role:156`, `157`,
`185`, `704` (hypothetical / unknown-function entries). A level-0
composition with `informative_only=True` therefore sees 16 roots, not
21. Inferred edges to these roles are still stored — a family *being*
"hypothetical" is a fact worth keeping — they are simply excluded from
enrichment by default.

## Pitfalls

- `level=0` returns the 21 mainroles, not every role. To work at subrole
  granularity pass `level=1`, or select on `level_kind='tigr_subrole'`.
- Mainrole `code` is a slug (`energy_metabolism`), subrole `code` a
  number — do not parse `code` as an integer across levels.
- Coverage bias in ORA: a heterotroph carries roles on only a fraction of
  its genes, so an enrichment whose background is "all genes of the
  organism" reports role enrichment that is really an annotation-density
  artifact. Pass an explicit `background=` list of the organism's genes
  with at least one TIGR edge — build it from
  `genes_by_ontology(ontology='tigr_role', level=0, organism=...)` and
  collect the distinct `locus_tag` values.
- Curated-vs-inferred disagreements (about 2.4% of role-carrying genes
  hold both an `evidence='curated'` and an `evidence='family_inferred'`
  edge) are facet choices, not errors (FtsH1: Cyanorak *Cell division*
  vs TIGR *Protein degradation*). Scope with the `evidence` filter when
  one view is wanted.
- Roles are broad (a hundred-odd subroles for a whole genome); use them
  for composition and coarse enrichment, not gene-level function.

## Typical questions

- Which TIGR sub roles are enriched among genes down at night in the diel experiment? — `pathway_enrichment(organism='MED4', experiment_ids=[...], ontology='tigr_role', level=1, direction='down')`
- How many MED4 genes fall under each TIGR main role? — `genes_by_ontology(ontology='tigr_role', organism='MED4', level=0, summary=True)`
- Which TIGR roles are most common among Alteromonas HOT1A3 genes? — `search_ontology(ontology=['tigr_role'], level=1, organism='HOT1A3')`
- Which NCBIfam families feed `tigr.role:164`, and what are its parents? — `ontology_term_details(term_ids=['tigr.role:164'])`
- Does the TIGR role agree with the Cyanorak role for this gene set? — `gene_ontology_terms(locus_tags=[...], organism='MED4', ontology=['tigr_role','cyanorak_role'])`

## Tools

- `search_ontology(ontology=['tigr_role'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='tigr_role', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['tigr_role'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['tigr_role'])` then `pathway_enrichment` / `cluster_enrichment(ontology='tigr_role', level=N)` — ORA.

## See also

- `docs://ontologies/ncbifam`
- `docs://ontologies/cyanorak_role`
- `docs://ontologies/cog_category`
- `docs://analysis/enrichment`
- `docs://analysis/annotation_evidence`
- `docs://tools/ontology_landscape`
- `docs://tools/ontology_term_details`
