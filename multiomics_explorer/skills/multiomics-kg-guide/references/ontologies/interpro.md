# InterPro entries (`interpro`)

Generated from `inputs/ontologies/interpro.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

InterPro — the integrated protein-signature database that unifies Pfam,
TIGRFAMs/NCBIfam, PANTHER, SMART, CDD, Gene3D, SUPERFAMILY, PROSITE and
others into one entry per family, domain or site. Every entry has an
`interpro_type`: `FAMILY`, `DOMAIN`, `HOMOLOGOUS_SUPERFAMILY`, `REPEAT`,
`CONSERVED_SITE`, `ACTIVE_SITE`, `BINDING_SITE`, `PTM`. It is the widest
signature-level annotation in the KG and the hub the Pfam and NCBIfam
bridges point into.

## How genes get annotated

Gene → entry edges come from InterProScan (`sources=['interproscan']`,
`evidence='signature'` on every edge — a member-database signature
matched). Verbose native detail records which member libraries hit
(`libraries`), the best library and e-value (`evalue_library`, `evalue`),
`match_count`, and the matched region (`start`, `end`). No
`evidence_score` — InterProScan is a single source. Entries bridge *out*
to EC numbers and CAZy families (`Interpro_entry_related_to_ec_number`,
`_cazy_family`) as a `router`: a computed cross-reference that is
recall-biased. `ontology_term_details(verbose=True)` derives
`router_ambiguous` on each router link (true when the entry routes to
more than one target or is not a `FAMILY`-type entry); it is not stored
on the node.

## Identifier form

`interpro:IPR000362` — prefix plus the `IPR` accession; node
`interpro_id` holds the bare accession, `interpro_type` the entry type,
`member_count` the number of integrated member signatures.

## Hierarchy

InterPro's parent/child relationships (`Interpro_entry_is_a_interpro_entry`)
give up to three levels, `level` 0-2; `level_kind` has no natural names
and is left empty. The hierarchy is sparse and top-heavy: 11,431
entries at level 0, 1,490 at level 1, 79 at level 2. `gene_count` / `organism_count` are subtree-inclusive;
`direct_gene_count` is node-local. Entries of different `interpro_type`
can sit in one parent–child chain, so the hierarchy is not a type
hierarchy.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `InterproEntry` |
| Gene → term edge | `Gene_has_interpro_entry` |
| Hierarchy edges (child → parent) | `Interpro_entry_is_a_interpro_entry` |
| Fulltext index | `interproEntryFullText` |
| Facet param | `interpro_type` (node prop `interpro_type`) |
| Trust axes on the gene edge | `sources`, `evidence` |
| Verbose edge detail | `libraries`, `evalue_library`, `evalue`, `match_count`, `start`, `end` |
| Extra compact columns, `ontology_term_details` | `interpro_id`, `interpro_type`, `direct_gene_count`, `member_count` |
| Bridges out (`links_out`) | `Interpro_entry_related_to_ec_number` → `ec` (*router*); `Interpro_entry_related_to_cazy_family` → `cazy` (*router*) |
| Bridges in (read from the source term) | `Pfam_in_interpro_entry` from `pfam` (*membership*); `Ncbifam_family_in_interpro_entry` from `ncbifam` (*membership*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`InterproEntry`)

| Property | Type | Meaning |
|---|---|---|
| `description` | string | longer free text (verbose on `search_ontology`; compact on `ontology_term_details`) |
| `direct_gene_count` | int | genes attached to this exact node (not descendants); absent where it would be vacuous |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `interpro_id` | string | bare InterPro accession (e.g. `IPR000001`); `id` is the `interpro:` CURIE |
| `interpro_type` | string | InterPro entry type (`FAMILY` / `DOMAIN` / `HOMOLOGOUS_SUPERFAMILY` / ...) — the `interpro_type=` facet value |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `member_count` | int | upstream family size (source-database members), not KG genes |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

- `evidence` — `list_filter_values(filter_type="evidence", ontology="interpro")`
- `sources` — `list_filter_values(filter_type="sources", ontology="interpro")`
- `interpro_type` — `list_filter_values(filter_type="interpro_type", ontology="interpro")`
- `link_kinds` — `list_filter_values(filter_type="link_kinds")`

Values are read live from the KG's `ControlledVocabulary` nodes at call time; this page never quotes them. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="interpro")`) lists which comparable axes the gene edge carries.

Snapshot of vocabulary values at build time (`--live-vocab`):

- `Gene_has_interpro_entry.evalue_library`: `CDD`, `GENE3D`, `HAMAP`, `NCBIFAM`, `PANTHER`, `PFAM`, `PIRSF`, `PRINTS`, `PROSITE_PATTERNS`, `PROSITE_PROFILES`, `SFLD`, `SMART`, `SUPERFAMILY`
- `Gene_has_interpro_entry.evidence`: `signature`
- `Gene_has_interpro_entry.libraries`: `CDD`, `GENE3D`, `HAMAP`, `NCBIFAM`, `PANTHER`, `PFAM`, `PIRSF`, `PRINTS`, `PROSITE_PATTERNS`, `PROSITE_PROFILES`, `SFLD`, `SMART`, `SUPERFAMILY`
- `Gene_has_interpro_entry.sources`: `interproscan`
- `InterproEntry.interpro_type`: `FAMILY`, `DOMAIN`, `HOMOLOGOUS_SUPERFAMILY`, `REPEAT`, `CONSERVED_SITE`, `ACTIVE_SITE`, `BINDING_SITE`, `PTM`
- `InterproEntry.is_uninformative`: `true`

## Interpretation

Type first, then level. A `FAMILY` entry is a whole-protein family call
(closest to "what this protein is"); `DOMAIN` and `HOMOLOGOUS_SUPERFAMILY`
are architecture-level and shared across unrelated proteins; site-level
types (`ACTIVE_SITE`, `BINDING_SITE`, `CONSERVED_SITE`, `PTM`) are
motif-scale and very common. Because the eight types size so
differently, enrichment on `interpro` requires `interpro_type=` — one
Fisher background per (type, level) stratum — and `ontology_landscape`
reports `best_interpro_type` per level. For a gene's own function read
its EC / CAZy / GO edges; the InterPro router links only say "this
entry's family clusters with that EC / CAZy family".

## Informativeness rule

About a thousand entries are flagged uninformative and dropped by
`informative_only=True` — mostly `FAMILY` (644) and `DOMAIN` (372)
entries with generic names, plus a handful of sites, repeats and
`HOMOLOGOUS_SUPERFAMILY` entries. The flag is name-based, so broad
superfamilies are mostly *not* flagged; manage them with
`max_gene_set_size`. Keep the default on for enrichment and combine with
`interpro_type='FAMILY'` for the most interpretable term set.

## Pitfalls

- Omitting `interpro_type` on search or landscape mixes types that size
  by orders of magnitude; on enrichment it raises.
- Router links are not annotations: `router_ambiguous=True` (computed
  in verbose `ontology_term_details`) means the entry points at several
  EC numbers / CAZy families or is not a FAMILY entry; never assign the
  target function to the gene from the bridge.
- `evalue` is InterProScan-internal (best member library); it is
  verbose-only and never filterable.
- Pfam and NCBIfam entries bridge *into* InterPro (membership); read
  those links from the `pfam` / `ncbifam` term.

## Typical questions

- Which InterPro FAMILY entries are enriched among genes up under iron limitation in MED4? — `pathway_enrichment(organism='MED4', experiment_ids=[...], ontology='interpro', interpro_type='FAMILY', direction='up')`
- What is the parent entry of `interpro:IPR001907` (Clp protease proteolytic subunit), which EC number does it route to, and is the routing ambiguous? — `ontology_term_details(term_ids=['interpro:IPR001907'], verbose=True)`
- Which member libraries support this gene's InterPro hits? — `gene_ontology_terms(locus_tags=[...], organism='MED4', ontology=['interpro'], verbose=True)` and read `libraries`
- Walk from a TCDB family to its Pfam domains and on to the InterPro entries that integrate them — `ontology_term_details(term_ids=['tcdb:3.A.1'], link_kinds=['composition'])`, then `ontology_term_details(term_ids=[...pfam ids...], link_kinds=['membership'])`

## Tools

- `search_ontology(ontology=['interpro'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='interpro', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['interpro'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['interpro'])` then `pathway_enrichment` / `cluster_enrichment(ontology='interpro', level=N)` — ORA.

## See also

- `docs://analysis/annotation_evidence`
- `docs://analysis/enrichment`
- `docs://ontologies/pfam`
- `docs://ontologies/ncbifam`
- `docs://ontologies/ec`
- `docs://ontologies/cazy`
- `docs://tools/ontology_term_details`
