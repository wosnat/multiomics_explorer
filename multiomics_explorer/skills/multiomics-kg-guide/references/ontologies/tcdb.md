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
`identity`, `qcov`, `evalue`, `consensus_n`). A gene is attached at every
level of its lineage; `attachment_depth='most_specific'` marks the deepest
attachment and `'superseded'` the ancestors, which are less specific, not
wrong. Families also bridge *out* to the Pfam domains and GO terms that
characterise them (composition, with `curated_tcids` naming the curated
members behind each link).

## Identifier form

`tcdb:3.A.1.2.3` — prefix plus the dotted TC number; the number of fields
gives the level: `tcdb:3` class, `tcdb:3.A` subclass, `tcdb:3.A.1`
family, `tcdb:3.A.1.2` subfamily, `tcdb:3.A.1.2.3` specificity node.
Node `tcdb_id` holds the bare number, `tc_class_id` the class, and
`superfamily` the superfamily name where TCDB assigns one.

## Hierarchy

Strict five-level tree via `Tcdb_family_is_a_tcdb_family`, `level` 0-4
with `level_kind` `tc_class` → `tc_subclass` → `tc_family` →
`tc_subfamily` → `tc_specificity`. `gene_count` / `organism_count` are
subtree-inclusive and, because every gene is attached along its whole
lineage, they also equal the attached-gene count; `direct_gene_count` is
node-local. `member_count` is TCDB's own family size, `metabolite_count`
the size of the family's substrate set. The ABC superfamily `tcdb:3.A.1`
has dozens of subfamilies and a very large substrate set — most
"transports everything" artefacts trace to it.

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
| `level_kind` | string | what a level means in this ontology (see the vocabulary below) |
| `member_count` | int | upstream family size (source-database members), not KG genes |
| `metabolite_count` | int |  |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |
| `superfamily` | string |  |
| `tc_class_id` | string |  |
| `tcdb_id` | string |  |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Controlled vocabularies

- `Gene_has_tcdb_family.attachment_depth`: `most_specific`, `superseded`
- `Gene_has_tcdb_family.evidence`: `family_inferred`, `homology`
- `Gene_has_tcdb_family.go_support`: `corroborated`, `uncorroborated`
- `Gene_has_tcdb_family.pfam_support`: `corroborated`, `uncorroborated`
- `Gene_has_tcdb_family.source_agreement`: `both_sources`, `single_source`
- `Gene_has_tcdb_family.sources`: `eggnog`, `tcdb_diamond`
- `TcdbFamily.level_kind`: `tc_class`, `tc_subclass`, `tc_family`, `tc_subfamily`, `tc_specificity`

Values are read from the KG's `ControlledVocabulary` nodes at build time; confirm live via `list_filter_values(filter_type=..., ontology='tcdb')`.

## Interpretation

Read the trust ladder in order: `evidence_score` ranks how corroborated
the gene × family call is (rank, never threshold — `min_evidence_score`
exists but 0 is an uncorroborated hit, not an absent call); `tier` and
`source_agreement` say whether DIAMOND and eggNOG agree; `pfam_support`
/ `go_support` say whether the family's own Pfam/GO composition is
present on the gene. For "what does this gene transport" go through
`metabolites_by_gene`; for "which genes could transport X" go through
`genes_by_metabolite` — the family-anchored route via `genes_by_ontology`
misses cross-family substrate hits. Leaf mode on `gene_ontology_terms`
returns only `most_specific` attachments; pass `include_superseded=True`
to see the ancestors.

## Informativeness rule

No TCDB node is flagged uninformative. The seven class roots and the ABC
superfamily behave as catch-alls by size; enrich at `level=2` (family) or
`level=3` (subfamily) and confirm with `ontology_landscape`.

## Pitfalls

- `superseded` means the gene is also attached deeper — it is a real
  annotation, just not the gene's most specific one. Counting genes
  across levels without the leaf predicate multiplies them.
- A gene whose deepest attachment is a lumping superfamily reads
  `transport_substrate_resolution='family_inferred'` on `gene_overview`:
  its substrate breadth is reachability, not capability.
- TCDB encodes no transport direction (import vs export).
- `evidence_score` is TCDB-internal; do not compare it with MEROPS's or
  GO's.
- Family `metabolite_count` counts the curated substrate set, not what
  any particular gene moves.

## Typical questions

- Which ABC-transporter subfamilies does MED4 carry, and how corroborated is each call?
- What is the most specific TCDB family for `PMM0392`, and what does that family transport?
- Which Pfam domains and GO terms characterise `tcdb:3.A.1`, and how many children does it have?
- Which transporter families are enriched among genes up under phosphorus limitation, restricted to homology-evidenced calls?

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
