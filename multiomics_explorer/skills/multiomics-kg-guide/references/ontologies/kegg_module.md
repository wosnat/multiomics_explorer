# KEGG modules (module classes, modules) (`kegg_module`)

Generated from `inputs/ontologies/kegg_module.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

KEGG modules — small functional units, each written by KEGG as a formula
over KOs (`kegg.module:M00531` Assimilatory nitrate reduction, nitrate =>
ammonia). A module is a few steps of one route, where a KEGG pathway map
bundles many routes, so modules are the sharper "is this function here"
and enrichment unit. Above the modules sits KEGG's module classification
(`ko00002`): Pathway modules / Signature modules → class (Energy
metabolism) → subclass (Nitrogen metabolism) → module.

## How genes get annotated

Modules have no gene edge of their own: a gene reaches a module through
its KO (`Gene_has_kegg_ko`) and the `Kegg_term_in_kegg_module` bridge
(KO → module), so every module annotation inherits KEGG's trust profile
(`sources=['eggnog']`, `evidence='family_inferred'`, no score). Module
membership is parsed from KEGG's module definition (`definition` holds
it verbatim, `step_count` its number of steps). `gene_count` /
`organism_count` count genes reached through the KO bridge only — a gene
that carries an EC number but no KO is not counted, even when the EC
names a module enzyme.

## Identifier form

Two id shapes under one `kegg.module:` prefix. Modules use the real KEGG
module CURIE, `kegg.module:M00531` (`module_id` holds the bare
`M00531`). Class nodes use house-minted dotted slugs,
`kegg.module:pathway_modules.energy_metabolism.nitrogen_metabolism` —
they route in every tool but are not KEGG accessions and will fail an
external CURIE check. Both forms are valid in `term_ids=[...]`.

## Hierarchy

Strict four-level tree via `Kegg_module_is_a_kegg_module`, `level` 0-3
with `level_kind` `kegg_module_type` → `kegg_module_class` →
`kegg_module_subclass` → `kegg_module`. Genes reach level 3 only (via
their KO); `gene_count` / `organism_count` above it are subtree unions.
`direct_gene_count`, `module_id`, `definition` and `step_count` exist on
modules only and are absent on class rows. Every node carries
`module_type`, inherited from its tree on class nodes, so the
`module_type=` facet narrows at any level. Modules also link out to the
KEGG pathway maps they sit in (`Kegg_module_in_kegg_pathway`).

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `KeggModule` |
| Gene → term edge | `Gene_has_kegg_ko` |
| Hierarchy edges (child → parent) | `Kegg_module_is_a_kegg_module` |
| Reached via | `KeggTerm` terms through `Kegg_term_in_kegg_module` (the gene edge belongs to that ontology) |
| Fulltext index | `keggModuleFullText` |
| Facet param | `module_type` (node prop `module_type`) |
| Trust axes on the gene edge | `sources`, `evidence` |
| Extra compact columns, `ontology_term_details` | `module_type`, `module_id`, `step_count`, `definition`, `direct_gene_count`, `complete_organism_count` |
| Bridges out (`links_out`) | `Kegg_module_in_kegg_pathway` → `kegg` (*membership*) |
| Bridges in (read from the source term) | `Kegg_term_in_kegg_module` from `kegg` (*membership*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`KeggModule`)

| Property | Type | Meaning |
|---|---|---|
| `complete_organism_count` | int | organisms whose genome has every step of a module in this subtree annotated; differs from `organism_count` (KO-bridge genes) |
| `definition` | string | KEGG's module formula over KOs, verbatim (top-level space = step, space inside `()` = AND, `,` = OR, `+` = complex subunit, `-K` = optional subunit); modules only |
| `direct_gene_count` | int | genes attached to this exact node (not descendants); absent where it would be vacuous |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `level_kind` | string | what a level means in this ontology (e.g. `tc_family`, `pathway`) — read values via `list_filter_values` |
| `module_id` | string | bare KEGG module id (e.g. `M00531`); modules only — class nodes have house slug ids |
| `module_type` | string | KEGG module type: `pathway` (a route) or `signature` (a marker set); class nodes carry their tree's type — the `module_type=` facet value |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |
| `step_count` | int | steps in the module definition; modules only |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

- `evidence` — `list_filter_values(filter_type="evidence", ontology="kegg_module")`
- `sources` — `list_filter_values(filter_type="sources", ontology="kegg_module")`
- `link_kinds` — `list_filter_values(filter_type="link_kinds")`

Values are read live from the KG's `ControlledVocabulary` nodes (`list_filter_values`); the list below is a build-time snapshot and may lag the KG. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="kegg_module")`) lists which comparable axes the gene edge carries.

Vocabulary snapshot (build time):

- `Gene_has_kegg_ko.evidence`: `family_inferred`
- `Gene_has_kegg_ko.sources`: `eggnog`
- `KeggModule.module_type`: `pathway`, `signature`

## Interpretation

The module gene set = the organism's genes whose KO is written anywhere in
the module's definition. Use `level=3` for module ORA and for "which genes
does this route use" (`genes_by_ontology(term_ids=['kegg.module:M00531'])`);
class levels 1-2 give a coarse functional profile. A gene set is not a
route: it does not say whether every step of the module is present in the
genome. Per-genome completeness lives on the organism-to-module edge,
which `complete_organism_count` summarises on the term side.

## Informativeness rule

No module or class node is flagged uninformative, so
`informative_only` changes nothing here. The useful split is
`module_type`: `pathway` modules are routes (a substrate turned into a
product); `signature` modules are marker sets (drug resistance, a
nutrient-assimilation signature) whose genes need not form a route.
Pass `module_type='pathway'` to keep only routes; the default keeps both
kinds, and pooling them in one test is valid. Gate class nodes with
`level`.

## Pitfalls

- `organism_count` counts organisms with a gene whose KO is in the
  module. It is not the number of organisms with a module edge: an
  organism can reach a module only through EC-only genes or a module
  reference, so a module with `organism_count = 0` can still have
  organism edges. Read `complete_organism_count` for completeness.
- A module gene set is not a complete route — finding genes for one
  step says nothing about the others. Read `definition` and
  `step_count` before calling a route present.
- Signature modules are marker sets, not pathways; scope with
  `module_type='pathway'` when the question is about metabolism.
- `kegg`, `brite` and `kegg_module` share one gene edge
  (`Gene_has_kegg_ko`): a module enrichment re-partitions the same KOs,
  it is not independent evidence. Trust filters do nothing (single
  rung) and `min_evidence_score` raises.
- Class ids are house slugs, not KEGG accessions — do not send them to
  external KEGG services.
- One KO can sit in several modules, so sibling module `gene_count`s
  overlap. Never sum them.

## Typical questions

- Which modules match 'nitrate'? — `search_ontology(search_text='nitrate', ontology='kegg_module')`
- Which WH8102 genes make up assimilatory nitrate reduction? — `genes_by_ontology(ontology='kegg_module', term_ids=['kegg.module:M00531'], organism='Synechococcus WH8102', min_gene_set_size=1)` (SYNW2464, SYNW2477)
- Which KEGG modules are enriched among genes up in this experiment? — `pathway_enrichment(organism='MED4', experiment_ids=[...], ontology='kegg_module', level=3, module_type='pathway')`
- Which subclass and pathway maps does M00531 sit under? — `ontology_term_details(term_ids=['kegg.module:M00531'])` and read `parents[]` / `links_out[]`
- Which modules do these genes' KOs belong to? — `gene_ontology_terms(locus_tags=[...], ontology='kegg_module')`

## Tools

- `search_ontology(ontology=['kegg_module'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='kegg_module', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['kegg_module'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['kegg_module'])` then `pathway_enrichment` / `cluster_enrichment(ontology='kegg_module', level=N)` — ORA.

## See also

- `docs://ontologies/kegg`
- `docs://ontologies/brite`
- `docs://analysis/enrichment`
- `docs://analysis/annotation_evidence`
- `docs://tools/ontology_term_details`
