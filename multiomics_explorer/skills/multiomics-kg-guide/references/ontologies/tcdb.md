# TCDB transporter families (`tcdb`)

Generated from `inputs/ontologies/tcdb.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

The Transporter Classification Database — a five-level classification of
membrane transport systems (`tcdb:3.A.1` ABC superfamily,
`tcdb:3.A.1.4.4` a high-affinity urea porter). TCDB nodes are both an
ontology (genes called to TC ids) and a chemistry node: TCDB curates
substrates on its systems (the five-part ids), and those
`Tcdb_family_transports_metabolite` / `…_chemical_role` edges are what
the metabolite tools walk. Classes 1-5 are transporter types (channels,
secondary carriers, primary active, group translocators, transmembrane
electron carriers); 8 and 9 are accessory factors and incompletely
characterized systems.

## How genes get annotated

Each source's call is its own `Gene_has_tcdb_family` edge, tagged
`tcdb_call`: `eggnog` (eggNOG's TC ids; compact `evidence` reads
`family_inferred`), `diamond_tier` (a DIAMOND search against TCDB
proteins, truncated by tier: tier 1 → system, 2 → subfamily, 3 → family)
and `diamond_best_hit` (the top DIAMOND systems, rank 1 plus near-ties);
both DIAMOND kinds read `homology`. The KG stamps every edge with an
ordered `tcdb_gate`: `direct` (a rank-1 best hit at tier 1-2, a tier-1
call, or an eggNOG call onto a system; always onto a system), `annotated`
(other eggNOG calls, tier-2 calls) or `below_gate` (tier-3 calls,
near-tie best hits, best hits under 40% identity); KG-wide that is
11,158 direct, 19,866 annotated and 44,799 below-gate edges, so most
edges are weak hits. Every gene-side tool
reads gated edges only (`direct` + `annotated`); the transport arm reads
`direct` only. Trust axes are `sources`, `evidence` and `tier` (null on
eggNOG; on the two DIAMOND kinds it is derived differently, so never
compare it across kinds), plus the `tcdb_call` filter. There is no
evidence score. Verbose DIAMOND detail: `identity`, `qcov` (both
percent), `evalue`, `tcdb_scov`, `tcdb_best_hit_rank`, `tcdb_bitscore`,
`tcdb_bitscore_ratio`. Families also bridge *out* to the Pfam domains and
GO terms that characterise them (composition, with `curated_tcids`
naming the curated members behind each link).

## Identifier form

`tcdb:3.A.1.2.3` — prefix plus the dotted TC number; the number of fields
gives the level: `tcdb:3` class, `tcdb:3.A` subclass, `tcdb:3.A.1`
family, `tcdb:3.A.1.2` subfamily, `tcdb:3.A.1.2.3` system.
Node `tcdb_id` holds the bare number, `tc_class_id` the class, and
`superfamily` the superfamily name where TCDB assigns one.

## Hierarchy

Strict five-level tree via `Tcdb_family_is_a_tcdb_family`, `level` 0-4
with `level_kind` `tc_class` → `tc_subclass` → `tc_family` →
`tc_subfamily` → `tc_system`. Substrate edges leave `tc_system` nodes
only, so a family's substrate range is the union of its systems';
`tcdb_substrate_count` holds that range at every level (the ABC
superfamily `tcdb:3.A.1` reads 546). `gene_count` / `organism_count` are
subtree-inclusive and count gated edges only, so a class reports
thousands of genes while its `direct_gene_count` is 0. Most nodes are
range-only: systems TCDB curates (and their ancestors) with no KG gene
called to them, `gene_count = 0`; they exist so a family's range is
complete. Filter them with `min_gene_count=1` or by reading `gene_count`.
`member_count` is TCDB's own family size. Nodes carry TCDB's transport
`direction` (`uptake` / `export` / `unknown`, dense) and sparse
`direction_basis` (`abc_numbering`: ABC subfamilies 3.A.1.1-99 and their
systems, uptake only; `tcdb_name`: a `tc_system`'s own TCDB name, with
secretion read as export). Direction is conservative: family and
subfamily names never set it, so every family, and every subfamily outside
the ABC uptake range, reads `unknown`; hedged, organelle or two-way names
and a curated override list also leave `unknown`. `superfamily` is TCDB's
own label, copied as is and unreliable for whole groups (most ABC
`3.A.1.*` node reads "ArsA ATPase (ArsA) Superfamily"). The ABC superfamily has 97 children, so
`ontology_term_details` truncates its `children[]`.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `TcdbFamily` |
| Gene → term edge | `Gene_has_tcdb_family` |
| Hierarchy edges (child → parent) | `Tcdb_family_is_a_tcdb_family` |
| Fulltext index | `tcdbFamilyFullText` |
| Trust axes on the gene edge | `sources`, `evidence`, `tier` |
| Compact edge columns | `tcdb_call`, `tcdb_gate` |
| Verbose edge detail | `identity`, `qcov`, `evalue`, `tcdb_scov` (edge prop `scov`), `tcdb_best_hit_rank` (edge prop `rank`), `tcdb_bitscore` (edge prop `bitscore`), `tcdb_bitscore_ratio` (edge prop `bitscore_ratio`) |
| Representative edge per (gene, term) | `tcdb_call`: `diamond_best_hit` > `diamond_tier` > `eggnog`, then `identity` DESC |
| Gene-edge gate | `tcdb_gate` in `direct` / `annotated` by default; `include_weak_tcdb_hits=True` adds the rest |
| Term columns, verbose `search_ontology` | `superfamily`, `tcdb_substrate_count`, `direction` |
| Extra compact columns, `ontology_term_details` | `tcdb_id`, `tc_class_id`, `direct_gene_count`, `member_count`, `superfamily`, `tcdb_substrate_count`, `direction`, `direction_basis` |
| Bridges out (`links_out`) | `Tcdb_family_has_pfam_domain` → `pfam` (*composition*); `Tcdb_family_involved_in_biological_process` → `go_bp` (*composition*); `Tcdb_family_enables_molecular_function` → `go_mf` (*composition*); `Tcdb_family_located_in_cellular_component` → `go_cc` (*composition*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`TcdbFamily`)

| Property | Type | Meaning |
|---|---|---|
| `direct_gene_count` | int | genes attached to this exact node (not descendants); absent where it would be vacuous |
| `direction` | string | `uptake` / `export` / `unknown`, conservative: set only by ABC uptake numbering (3.A.1.1-99 subfamilies and their systems) or a `tc_system`'s own name; family and subfamily names never set it — node-level, not a per-gene call |
| `direction_basis` | string | sparse: which rule set `direction` (`abc_numbering`: uptake only / `tcdb_name`: systems only) |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `level_kind` | string | what a level means in this ontology (e.g. `tc_family`, `pathway`) — read values via `list_filter_values` |
| `member_count` | int | upstream family size (source-database members), not KG genes |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |
| `proteins` | string | `tc_system` only (sparse): TCDB's protein cell — gene symbols, accessions and source organism, lines joined by `; ` (e.g. `UrtA (R); UrtB (M)`); indexed by the TCDB full-text search |
| `superfamily` | string | TCDB's own superfamily label, copied as is (sparse); unreliable for whole groups — TCDB files every ABC `3.A.1.*` row under ArsA |
| `tc_class_id` | string | CURIE of the level-0 TC class this node sits under (e.g. `tcdb:3`) — for grouping without walking the hierarchy |
| `tcdb_id` | string | bare TC number (e.g. `3.A.1.14`); `id` is the `tcdb:` CURIE |
| `tcdb_substrate_count` | int | distinct Metabolite + ChemicalRole substrates TCDB curates on the `tc_system` nodes in this node's subtree (TCDB's range; on a system, its own count, 0 when none) |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

- `evidence` — `list_filter_values(filter_type="evidence", ontology="tcdb")`
- `sources` — `list_filter_values(filter_type="sources", ontology="tcdb")`
- `tcdb_call` — `list_filter_values(filter_type="tcdb_call", ontology="tcdb")`
- `tcdb_gate` — `list_filter_values(filter_type="tcdb_gate", ontology="tcdb")`
- `direction` — `list_filter_values(filter_type="direction", ontology="tcdb")`
- `link_kinds` — `list_filter_values(filter_type="link_kinds")`

Values are read live from the KG's `ControlledVocabulary` nodes at call time; this page never quotes them. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="tcdb")`) lists which comparable axes the gene edge carries.

Snapshot of vocabulary values at build time (`--live-vocab`):

- `Gene_has_tcdb_family.evidence`: `family_inferred`, `homology`
- `Gene_has_tcdb_family.sources`: `eggnog`, `tcdb_diamond`
- `Gene_has_tcdb_family.tcdb_call`: `eggnog`, `diamond_tier`, `diamond_best_hit`
- `Gene_has_tcdb_family.tcdb_gate`: `direct`, `annotated`, `below_gate`
- `TcdbFamily.direction`: `uptake`, `export`, `unknown`
- `TcdbFamily.direction_basis`: `abc_numbering`, `tcdb_name`
- `TcdbFamily.level_kind`: `tc_class`, `tc_subclass`, `tc_family`, `tc_subfamily`, `tc_system`

## Interpretation

A gene's leaf rows (`gene_ontology_terms`, default leaf mode) are its
gated targets minus any that is an ancestor of another, so their count is
`gene_overview.tcdb_assignment_count`; most are systems or subfamilies.
Several sibling rows per gene are normal (an eggNOG call often names
several TC ids). Each row reports one edge by precedence (best hit, tier,
eggNOG; then identity) and lists in `tcdb_calls` every call kind on its
lineage. eggNOG plus a DIAMOND kind is independent agreement; the two
DIAMOND kinds come from one DIAMOND run. Rank DIAMOND rows by `identity`;
never filter on it. For "what does this gene transport" go through
`metabolites_by_gene`; for "which genes could transport X" go through
`genes_by_metabolite`. Both return direct rows (the gene's own system)
by default and family rows with `include_tcdb_family_substrates=True`, a
walk from the gene's family or subfamily call down to TCDB's curated
systems. The family-anchored route via `genes_by_ontology` misses
cross-family substrate hits. Weak hits (`below_gate`) appear only with
`include_weak_tcdb_hits=True` on `gene_ontology_terms` /
`genes_by_ontology`; enrichment never uses them.

## Informativeness rule

No TCDB node is flagged uninformative. The seven class roots and the ABC
superfamily behave as catch-alls by size; enrich at `level=2` (family) or
`level=3` (subfamily) and confirm with `ontology_landscape`.

## Pitfalls

- Do not re-derive the gate from `tcdb_call`, `tier` or `rank`; read
  `tcdb_gate`. A weak hit is evidence only and feeds no count.
- A gene called only at family or subfamily level has no default
  substrate row. That is not "no transporter": read the
  `tcdb_family_substrates_not_shown` hint on the metabolite tools.
- A gene called only on the ABC or MFS superfamily (over 200 curated
  substrates) gets no family walk at all: its substrate is unknown, and
  `tcdb_family_substrates_skipped` lists it.
- TCDB curation is reported as-is: the Pst phosphate system
  `tcdb:3.A.1.7.6` is curated with triphosphate only, and catch-all
  substrates ("Peptide", "Protein") appear on some systems. Coupling
  ions (H+, Na+) and placeholders ("molecule", "ion") are filtered out
  (`Schema_info.tcdb_substrate_excluded_targets`), so Na+/H+ antiporters
  reach no metabolite.
- `direction` is node-level and TCDB-stated, not a per-gene measurement;
  most nodes read `unknown`.
- `tcdb_substrate_count` is TCDB's curated range for the node, not what
  any particular gene moves.

## Typical questions

- Which ABC-transporter subfamilies does MED4 carry, and how is each call supported? — `genes_by_ontology(ontology='tcdb', organism='MED4', term_ids=['tcdb:3.A.1'], level=3, verbose=True)`
- Which TC systems is cynD (`PMM0372`) called to, and what do they transport? — `gene_ontology_terms(locus_tags=['PMM0372'], organism='MED4', ontology=['tcdb'])` then `metabolites_by_gene(locus_tags=['PMM0372'], organism='MED4')`
- Which Pfam domains and GO terms characterise `tcdb:3.A.1`, and how broad is its substrate range? — `ontology_term_details(term_ids=['tcdb:3.A.1'])` (`tcdb_substrate_count`)
- Which transporter families are enriched among genes up under phosphorus limitation, restricted to DIAMOND calls? — `pathway_enrichment(..., ontology='tcdb', level=2, direction='up', evidence=['homology'])`
- Does this gene have weak TCDB hits below the gate? — `gene_ontology_terms(locus_tags=[...], organism=..., ontology=['tcdb'], include_weak_tcdb_hits=True)`

## Tools

- `search_ontology(ontology=['tcdb'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='tcdb', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['tcdb'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['tcdb'])` then `pathway_enrichment` / `cluster_enrichment(ontology='tcdb', level=N)` — ORA.

## See also

- `docs://analysis/transport`
- `docs://analysis/metabolites`
- `docs://analysis/annotation_evidence`
- `docs://ontologies/pfam`
- `docs://ontologies/brite`
- `docs://guide/conventions`
- `docs://tools/genes_by_metabolite`
- `docs://tools/metabolites_by_gene`
- `docs://tools/ontology_term_details`
