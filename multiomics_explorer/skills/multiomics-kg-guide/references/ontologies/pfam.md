# Pfam domains and clans (`pfam`)

Generated from `inputs/ontologies/pfam.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

Pfam protein domain families and clans. A Pfam entry (`pfam:PF00005` ABC
transporter ATPase domain) is a profile-HMM for one conserved domain; a
clan (`pfam.clan:CL0023` P-loop NTPase) groups families that share a fold
or common ancestry. Domain-level annotation: a multi-domain protein
carries several Pfam edges, and the same domain recurs across unrelated
proteins.

## How genes get annotated

Gene → Pfam edges pool InterProScan HMM hits with Cyanorak, eggNOG and
UniProt records (`sources[]`); compact `evidence` is `signature` (an HMM
match — the native Pfam rung), `curated` or `family_inferred`, with an `evidence_score` in
[0, 1] reflecting source agreement; rung semantics in
`docs://analysis/annotation_evidence`. Live on this edge type:
InterProScan-only and eggNOG+InterProScan edges read `signature` (the
HMM hit is kept even when eggNOG agrees); eggNOG-only edges read
`family_inferred` (~25k); any edge with a `cyanorak` or `uniprot` source
reads `curated`. Clan membership is a term-side edge
(`Pfam_in_pfam_clan`), so a gene's clan count is a rollup of its
domain hits. Pfam entries also bridge *out* to InterPro
(`Pfam_in_interpro_entry`, membership) — the InterPro entry that
integrates this Pfam signature.

## Identifier form

Domains `pfam:PF00005` (prefix + `PF` + five digits; node `short_name`
holds the Pfam short name such as `ABC_tran`); clans `pfam.clan:CL0023`.
Both forms work everywhere a `pfam` term ID is accepted, including
`ontology_term_details`.

## Hierarchy

Two levels on two labels: clans (`PfamClan`, `level=0`) and domains
(`Pfam`, `level=1`), linked by `Pfam_in_pfam_clan`. Many domains belong
to no clan and are therefore level-1 roots. `gene_count` on a clan is the
union of its member domains' genes; `direct_gene_count` is absent on both
labels (genes attach only to domains, so it would be vacuous). Search and
browse cover both labels in one call (two fulltext indexes).

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `Pfam` (parent label `PfamClan`) |
| Gene → term edge | `Gene_has_pfam` |
| Hierarchy edges (child → parent) | `Pfam_in_pfam_clan` |
| Fulltext index | `pfamFullText`, `pfamClanFullText` |
| Trust axes on the gene edge | `sources`, `evidence`, `evidence_score` |
| Extra compact columns, `ontology_term_details` | `short_name` |
| Bridges out (`links_out`) | `Pfam_in_interpro_entry` → `interpro` (*membership*) |
| Bridges in (read from the source term) | `Tcdb_family_has_pfam_domain` from `tcdb` (*composition*); `Merops_family_has_pfam_domain` from `merops` (*composition*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`Pfam`)

| Property | Type | Meaning |
|---|---|---|
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |
| `short_name` | string | Pfam short name (e.g. `ABC_tran`); `name` holds the long description |

Parent label `PfamClan`: `gene_count`, `id`, `level`, `name`, `organism_count`, `preferred_id`.

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

- `evidence` — `list_filter_values(filter_type="evidence", ontology="pfam")`
- `sources` — `list_filter_values(filter_type="sources", ontology="pfam")`
- `link_kinds` — `list_filter_values(filter_type="link_kinds")`

Values are read live from the KG's `ControlledVocabulary` nodes at call time; this page never quotes them. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="pfam")`) lists which comparable axes the gene edge carries.

Snapshot of vocabulary values at build time (`--live-vocab`):

- `Gene_has_pfam.evidence`: `curated`, `signature`, `family_inferred`
- `Gene_has_pfam.sources`: `cyanorak`, `eggnog`, `interproscan`, `uniprot`

## Interpretation

The right axis for "what is this protein built from" and for
architecture-level comparisons across distant organisms — domains are far
more conserved than whole-protein orthology. Level 1 (domains) is the
enrichment unit; clan level (0) is coarse but robust when domain sets are
sparse. Rank a gene's competing domain hits by `evidence_score`;
`signature` means an HMM threshold was passed, `curated` a
`cyanorak` / `uniprot` confirmation, and `family_inferred` an eggNOG-only
transfer with no HMM hit of its own. For the *integrated* view of a domain
(which InterPro entry, which GO terms it implies) follow `links_out` to
`interpro`.

## Informativeness rule

No Pfam entry or clan is flagged uninformative in the current KG. Very
common domains (`PF00005` ABC transporter, `PF00072` response regulator
receiver, `PF02518` histidine kinase ATPase) behave like catch-alls in
enrichment; use `max_gene_set_size` or `min_gene_count` to manage them.

## Pitfalls

- Domain edges are many-to-many: a gene with four domains is in four
  Pfam gene sets; `gene_count` overlaps heavily across domains of one
  architecture.
- `pfam:` IDs are domains, `pfam.clan:` IDs are clans — `level=0` browses
  clans only, `level=1` domains only.
- TCDB and MEROPS families bridge *to* Pfam (composition) — those links
  are read from the `tcdb` / `merops` term, not from the Pfam term.
- Pfam evidence tells you a domain is present, not that the protein is
  active — combine with MEROPS `call_class` or TCDB `attachment_depth`
  for functional calls.

## Typical questions

- Which Pfam domains are enriched among genes up in the vesicle proteome?
- Which MED4 genes carry `pfam:PF00005`? — `genes_by_ontology(ontology='pfam', organism='MED4', term_ids=['pfam:PF00005'])`; the TCDB families built from that domain are read from the `tcdb` side (`ontology_term_details(term_ids=['tcdb:3.A.1'], link_kinds=['composition'])`)
- What are the member domains of clan `pfam.clan:CL0023`, and which InterPro entry does each map to? — `ontology_term_details(term_ids=['pfam.clan:CL0023'])` for the children, then `ontology_term_details(term_ids=[...children...], link_kinds=['membership'])`
- Does this gene's domain architecture match its MEROPS or TCDB family call?

## Tools

- `search_ontology(ontology=['pfam'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='pfam', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['pfam'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['pfam'])` then `pathway_enrichment` / `cluster_enrichment(ontology='pfam', level=N)` — ORA.

## See also

- `docs://ontologies/interpro`
- `docs://ontologies/tcdb`
- `docs://ontologies/merops`
- `docs://analysis/annotation_evidence`
- `docs://analysis/enrichment`
- `docs://tools/ontology_term_details`
