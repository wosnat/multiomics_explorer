# KEGG (categories, pathways, KOs) (`kegg`)

Generated from `inputs/ontologies/kegg.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

KEGG orthology and pathway maps — the most common "which pathway is this
gene in" vocabulary. One `KeggTerm` label holds four kinds of node
(`level_kind`): `category` (Metabolism, Genetic Information Processing,
...), `subcategory` (Carbohydrate metabolism, ...), `pathway`
(`kegg.pathway:ko00910` Nitrogen metabolism) and `ko` (KEGG Orthology
groups, `kegg:K02575` NRT nitrate/nitrite transporter). Genes attach to
KOs; pathways and categories are reached by rollup.

## How genes get annotated

Every gene → KO edge comes from eggNOG-mapper (`sources=['eggnog']`,
`evidence='family_inferred'`): the gene was placed in an orthologous group
whose members carry that KO. There is no curated rung and no
`evidence_score` — all KEGG edges sit on one rung, so trust filters on
`kegg` do nothing useful; use `informative_only` and term size instead.
Pathway membership is a rollup from KO → pathway → subcategory → category
(`Kegg_term_is_a_kegg_term`). Pathway nodes also carry a literature index
(`Publication_discusses_kegg_pathway` → `discussed_by_n_publications`) and,
for pathways only, chemistry counts (`reaction_count`, `metabolite_count`)
tying them to the reaction / metabolite layer.

## Identifier form

Four prefixes on one label — `kegg.category:09100`, `kegg.subcategory:...`,
`kegg.pathway:ko00910`, and bare KO `kegg:K02575`. The `ko` pathway prefix
(not `map`) is the KG's canonical form. `list_metabolites(pathway_ids=[...])`
and `genes_by_ontology(ontology='kegg', term_ids=[...])` both take the
`kegg.pathway:` form; `discussed_by_publication` returns it.

## Hierarchy

Four levels, `level` 0-3 = `category` → `subcategory` → `pathway` → `ko`.
It is a DAG in practice: one KO belongs to many pathways (a glycolysis
enzyme is also in several biosynthesis maps), so `gene_count` on a pathway
is the union of its KOs' genes and sibling pathways overlap heavily.
`direct_gene_count` is present on every node; on a pathway it counts genes
attached to the pathway itself, which is normally 0 (genes attach to KOs).
BRITE hierarchies are a *separate* view over the same KOs, reached through
the `Kegg_term_in_brite_category` bridge.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `KeggTerm` |
| Gene → term edge | `Gene_has_kegg_ko` |
| Hierarchy edges (child → parent) | `Kegg_term_is_a_kegg_term` |
| Fulltext index | `keggFullText` |
| Trust axes on the gene edge | `sources`, `evidence` |
| Extra compact columns, `ontology_term_details` | `direct_gene_count`, `reaction_count`, `metabolite_count` |
| Literature index | `Publication_discusses_kegg_pathway` (`discussed_by_n_publications`) |
| Bridges out (`links_out`) | `Kegg_term_in_brite_category` → `brite` (*membership*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`KeggTerm`)

| Property | Type | Meaning |
|---|---|---|
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

Values: see `list_filter_values(filter_type=..., ontology='kegg')` — `trust_axes`, `evidence`, `sources`, and the ontology-specific categorical filter types are read from the KG's `ControlledVocabulary` nodes at call time.

## Interpretation

Pathway level (`level=2`) is the interpretable enrichment unit — it maps
directly onto the KEGG map images and onto `list_metabolites(pathway_ids=)`.
KO level (`level=3`) is the gene-family unit for "does this organism have
a nitrate transporter" questions. Because every edge is `family_inferred`,
KEGG annotation coverage is uniform across organisms, which makes it the
best axis for cross-organism comparisons that do not need curated depth.
For a pathway's *metabolites* (as opposed to its genes) go through the
chemistry layer — the two memberships differ (see
`docs://analysis/metabolites`).

## Informativeness rule

Catch-all maps are flagged uninformative — `ko01100` Metabolic pathways,
`ko01110` Biosynthesis of secondary metabolites, `ko01120` Microbial
metabolism in diverse environments, and a set of broad KO groups — and
dropped by `informative_only=True` (default on enrichment, opt-in on
browse/search). The flag is term-side only; the genes stay in the
background.

## Pitfalls

- Pathway `gene_count`s overlap — a gene in three maps is counted three
  times across siblings. Never sum them.
- `kegg` and `brite` share the same gene edge (`Gene_has_kegg_ko`): a
  BRITE enrichment is a re-partitioning of the same KOs, not independent
  evidence.
- No trust ladder to filter on: `sources`/`evidence` are constant. Passing
  `min_evidence_score` raises (KEGG carries no score axis).
- Pathway-anchored metabolite lists and KO-anchored gene lists for the
  same map are different sets; name the anchor when answering.
- Publication counts are a prose literature index, not expression — see
  `discussed_by_publication`.

## Typical questions

- Which KEGG pathways are enriched among genes down under phosphorus limitation in MED4?
- Does MIT1002 carry a KO for nitrate assimilation, and which pathway maps does it sit in?
- Which pathway maps are most discussed in the literature for this organism?
- What are the KO children of `kegg.pathway:ko00910`, and which BRITE categories does the pathway belong to?

## Tools

- `search_ontology(ontology=['kegg'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='kegg', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['kegg'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['kegg'])` then `pathway_enrichment` / `cluster_enrichment(ontology='kegg', level=N)` — ORA.

## See also

- `docs://ontologies/brite`
- `docs://ontologies/ec`
- `docs://analysis/enrichment`
- `docs://analysis/metabolites`
- `docs://tools/discussed_by_publication`
- `docs://tools/list_metabolites`
- `docs://tools/ontology_term_details`
