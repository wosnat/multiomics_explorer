# TCDB transporter families (`tcdb`)

Generated from `inputs/ontologies/tcdb.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

The Transporter Classification Database — a five-level classification of
membrane transport systems (`tcdb:3.A.1` ABC superfamily,
`tcdb:2.A.1.5.3` a sucrose:H+ symporter). TCDB families are both an
ontology (genes annotated to families) and a chemistry node: families
carry curated substrate sets (`Tcdb_family_transports_metabolite`) that
the metabolite tools walk. Classes 1-5 are transporter types (channels,
secondary carriers, primary active, group translocators, transmembrane
electron carriers); 8 and 9 are accessory factors and incompletely
characterized systems.

## How genes get annotated

Gene → family edges come from a DIAMOND search against TCDB proteins
(`tcdb_diamond`) and from eggNOG transfer (`sources[]`), merged with a
compact `evidence` of `homology` (direct sequence hit) or
`family_inferred` (eggNOG only) and the fullest trust surface in the KG:
`evidence_score` in [0, 1], `tier`, and verbose native detail
(`confidence_score`, `source_agreement`, `pfam_support`, `go_support`,
`identity`, `qcov`, `evalue`, `consensus_n`). A gene is attached only
where a source placed it — at family, subfamily or specificity level
(levels 2-4; a handful at subclass level 1; never at a class root). Each
attachment carries `attachment_depth`: `superseded` means the same gene
also has a deeper attachment below this node (the ancestor is less
specific, not wrong); `most_specific` marks every attachment with no
deeper one. Families also bridge *out* to the Pfam domains and GO terms
that characterise them (composition, with `curated_tcids` naming the
curated members behind each link).

## Identifier form

`tcdb:3.A.1.2.3` — prefix plus the dotted TC number; the number of fields
gives the level: `tcdb:3` class, `tcdb:3.A` subclass, `tcdb:3.A.1`
family, `tcdb:3.A.1.2` subfamily, `tcdb:3.A.1.2.3` specificity node.
Node `tcdb_id` holds the bare number, `tc_class_id` the class, and
`superfamily` the superfamily name where TCDB assigns one.

## Hierarchy

Strict five-level tree via `Tcdb_family_is_a_tcdb_family`, `level` 0-4
with `level_kind` `tc_class` → `tc_subclass` → `tc_family` →
`tc_subfamily` → `tc_specificity`. Attachments sit at levels 1-4 only
(three at level 1, ~35k at family level 2, ~16k at subfamily level 3,
~4k at specificity level 4). `gene_count` / `organism_count` are
subtree-inclusive rollups, so a class or subclass reports thousands of
genes while its `direct_gene_count` is 0 — the seven class roots have no
attachments at all. `member_count` is TCDB's own family size,
`metabolite_count` the size of the family's substrate set. The ABC
superfamily `tcdb:3.A.1` has 55 direct children and a very large
substrate set — most "transports everything" artefacts trace to it.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `TcdbFamily` |
| Gene → term edge | `Gene_has_tcdb_family` |
| Hierarchy edges (child → parent) | `Tcdb_family_is_a_tcdb_family` |
| Fulltext index | `tcdbFamilyFullText` |
| Trust axes on the gene edge | `sources`, `evidence`, `evidence_score`, `tier` |
| Rank prop | `evidence_score` |
| Verbose edge detail | `confidence_score`, `source_agreement`, `pfam_support`, `go_support`, `identity`, `qcov`, `evalue`, `consensus_n`, `attachment_depth` |
| Leaf mode predicate | `attachment_depth = 'most_specific'` unless `include_superseded=True` |
| Term columns, verbose `search_ontology` | `superfamily`, `metabolite_count` |
| Extra compact columns, `ontology_term_details` | `tcdb_id`, `tc_class_id`, `direct_gene_count`, `member_count`, `superfamily`, `metabolite_count` |
| Bridges out (`links_out`) | `Tcdb_family_has_pfam_domain` → `pfam` (*composition*); `Tcdb_family_involved_in_biological_process` → `go_bp` (*composition*); `Tcdb_family_enables_molecular_function` → `go_mf` (*composition*); `Tcdb_family_located_in_cellular_component` → `go_cc` (*composition*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`TcdbFamily`)

| Property | Type | Meaning |
|---|---|---|
| `direct_gene_count` | int | genes attached to this exact node (not descendants); absent where it would be vacuous |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `level_kind` | string | what a level means in this ontology (e.g. `tc_family`, `pathway`) — read values via `list_filter_values` |
| `member_count` | int | upstream family size (source-database members), not KG genes |
| `metabolite_count` | int | distinct substrates reachable via `Tcdb_family_transports_metabolite` (rolled up over the subtree, so it grows toward the root) — on KEGG, metabolites in the pathway |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |
| `superfamily` | string | TCDB superfamily name the family belongs to, where TCDB assigns one (sparse) |
| `tc_class_id` | string | CURIE of the level-0 TC class this node sits under (e.g. `tcdb:3`) — for grouping without walking the hierarchy |
| `tcdb_id` | string | bare TC number (e.g. `3.A.1.14`); `id` is the `tcdb:` CURIE |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

- `evidence` — `list_filter_values(filter_type="evidence", ontology="tcdb")`
- `sources` — `list_filter_values(filter_type="sources", ontology="tcdb")`
- `attachment_depth` — `list_filter_values(filter_type="attachment_depth", ontology="tcdb")`
- `link_kinds` — `list_filter_values(filter_type="link_kinds")`

Values are read live from the KG's `ControlledVocabulary` nodes at call time; this page never quotes them. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="tcdb")`) lists which comparable axes the gene edge carries.

## Interpretation

Read the trust ladder in order: `evidence_score` ranks how corroborated
the gene × family call is (rank, never threshold — `min_evidence_score`
exists but 0 is an uncorroborated hit, not an absent call); `tier` and
`source_agreement` say whether DIAMOND and eggNOG agree; `pfam_support`
/ `go_support` say whether the family's own Pfam/GO composition is
present on the gene. `most_specific` is per attachment, not per gene: a
gene with hits in several sibling subfamilies keeps them all
(`PMM0392` has seven `most_specific` subfamilies under `tcdb:3.A.1`
plus the superfamily itself as `superseded`; 9,045 of 30,547 TCDB genes
carry more than one). For "what does this gene transport" go through
`metabolites_by_gene`; for "which genes could transport X" go through
`genes_by_metabolite` — the family-anchored route via `genes_by_ontology`
misses cross-family substrate hits. Leaf mode on `gene_ontology_terms`
returns only `most_specific` attachments; pass `include_superseded=True`
to see the ancestors. When `genes_by_ontology` rolls attachments up to a
target level and two edges tie on the rank key, the deeper attachment
wins, so a rollup row never reports a `superseded` ancestor edge over an
equally scored `most_specific` descendant.

## Informativeness rule

No TCDB node is flagged uninformative. The seven class roots and the ABC
superfamily behave as catch-alls by size; enrich at `level=2` (family) or
`level=3` (subfamily) and confirm with `ontology_landscape`.

## Pitfalls

- `superseded` means the gene is also attached deeper — it is a real
  annotation, just not the gene's most specific one. Counting genes
  across levels without the leaf predicate multiplies them.
- "The most specific family" is usually "families" — expect several
  `most_specific` rows per gene and report them as a set.
- A gene whose deepest attachment is a lumping superfamily reads
  `transport_substrate_resolution='family_inferred'` on `gene_overview`:
  its substrate breadth is reachability, not capability.
- TCDB encodes no transport direction (import vs export).
- `evidence_score` is TCDB-internal; do not compare it with MEROPS's or
  GO's.
- Family `metabolite_count` counts the curated substrate set, not what
  any particular gene moves.

## Typical questions

- Which ABC-transporter subfamilies does MED4 carry, and how corroborated is each call? — `genes_by_ontology(ontology='tcdb', organism='MED4', term_ids=['tcdb:3.A.1'], level=3, verbose=True)`
- What are the most specific TCDB families for `PMM0392`, and what do they transport? — `gene_ontology_terms(locus_tags=['PMM0392'], organism='MED4', ontology=['tcdb'])` then `metabolites_by_gene(locus_tags=['PMM0392'], organism='MED4')`
- Which Pfam domains and GO terms characterise `tcdb:3.A.1`, and how many children does it have? — `ontology_term_details(term_ids=['tcdb:3.A.1'])`
- Which transporter families are enriched among genes up under phosphorus limitation, restricted to homology-evidenced calls? — `pathway_enrichment(..., ontology='tcdb', level=2, direction='up', evidence=['homology'])`

## Tools

- `search_ontology(ontology=['tcdb'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='tcdb', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['tcdb'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['tcdb'])` then `pathway_enrichment` / `cluster_enrichment(ontology='tcdb', level=N)` — ORA.

## See also

- `docs://analysis/metabolites`
- `docs://analysis/annotation_evidence`
- `docs://ontologies/pfam`
- `docs://ontologies/brite`
- `docs://guide/conventions`
- `docs://tools/genes_by_metabolite`
- `docs://tools/metabolites_by_gene`
- `docs://tools/ontology_term_details`
