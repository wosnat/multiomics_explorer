# NCBIfam families (`ncbifam`)

Generated from `inputs/ontologies/ncbifam.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

NCBIfam — NCBI's curated protein-family HMM collection, which absorbed
and continues TIGRFAMs. Each family is an HMM with a curated name, a
`family_type` that states how much function the name implies
(`equivalog` = full-length, same function across members; `subfamily`,
`superfamily`, `domain`, `repeat`, `signature`, `paralog`,
`hypoth_equivalog`, `exception`, `PfamEq` / `PfamAutoEq`, ...) and, for
many, a `gene_symbol` (`nrtA`, `ntcA`). The best source of confident
*names* for bacterial proteins in the KG.

## How genes get annotated

Gene → family edges come from InterProScan's NCBIfam member library
(`sources=['interproscan']`, `evidence='signature'` — the HMM's trusted
cutoff was met). Verbose native detail carries `evalue`, `bit_score` and
the matched region (`start`, `end`); higher bit score is better, and it
is NCBIfam-internal. No `evidence_score`. Families bridge *out* in two
directions: to the InterPro entry that integrates them
(`Ncbifam_family_in_interpro_entry`, membership — present on about half
of the families), and to archived TIGR roles
(`Ncbifam_family_has_tigr_role`, router — about a third of the
families). The role bridge is a lookup aid; only `equivalog` families
also produce a gene-level `Gene_has_tigr_role` edge (see
`docs://ontologies/tigr_role`).

## Identifier form

Two accession styles on one prefix: `ncbifam:NF006762` (NCBIfam-native,
here hemB porphobilinogen synthase) and `ncbifam:TIGR00254` (legacy
TIGRFAMs accessions kept by NCBIfam, here a diguanylate-cyclase domain
family).
Node `ncbifam_id` holds the bare accession; `family_type` and
`gene_symbol` are term-level (verbose on `search_ontology`, compact on
`ontology_term_details`).

## Hierarchy

Flat: every family is `level=0`, no hierarchy edges. `gene_count` /
`organism_count` are direct; no `direct_gene_count`. Family relationships
(a subfamily of a superfamily) exist only as `family_type` semantics, not
as edges — use the InterPro bridge for hierarchy.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `NcbifamFamily` |
| Gene → term edge | `Gene_has_ncbifam_family` |
| Hierarchy edges | none — flat ontology (`level=0` only, nothing to expand) |
| Fulltext index | `ncbifamFamilyFullText` |
| Trust axes on the gene edge | `sources`, `evidence` |
| Verbose edge detail | `evalue`, `bit_score`, `start`, `end` |
| Term columns, verbose `search_ontology` | `family_type`, `gene_symbol` |
| Extra compact columns, `ontology_term_details` | `ncbifam_id`, `family_type`, `gene_symbol` |
| Bridges out (`links_out`) | `Ncbifam_family_in_interpro_entry` → `interpro` (*membership*); `Ncbifam_family_has_tigr_role` → `tigr_role` (*router*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`NcbifamFamily`)

| Property | Type | Meaning |
|---|---|---|
| `description` | string | longer free text (verbose on `search_ontology`; compact on `ontology_term_details`) |
| `family_type` | string | NCBIfam model type (equivalog, subfamily, domain, ...) — the `ncbifam_family_type` filter value |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `gene_symbol` | string | gene symbol NCBIfam assigns to the family's members (sparse) |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `name` | string | term name (what `search_ontology` indexes) |
| `ncbifam_id` | string | bare NCBIfam / TIGRFAM accession (e.g. `TIGR00001`, `NF000001`); `id` is the `ncbifam:` CURIE |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `preferred_id` | string | same value as `id` |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Applicable filter types

- `evidence` — `list_filter_values(filter_type="evidence", ontology="ncbifam")`
- `sources` — `list_filter_values(filter_type="sources", ontology="ncbifam")`
- `ncbifam_family_type` — `list_filter_values(filter_type="ncbifam_family_type", ontology="ncbifam")`
- `link_kinds` — `list_filter_values(filter_type="link_kinds")`

Values are read live from the KG's `ControlledVocabulary` nodes at call time; this page never quotes them. `trust_axes` (`list_filter_values(filter_type="trust_axes", ontology="ncbifam")`) lists which comparable axes the gene edge carries.

Snapshot of vocabulary values at build time (`--live-vocab`):

- `Gene_has_ncbifam_family.evidence`: `signature`
- `Gene_has_ncbifam_family.sources`: `interproscan`
- `NcbifamFamily.family_type`: `PfamAutoEq`, `PfamEq`, `domain`, `equivalog`, `equivalog_domain`, `exception`, `hypoth_equivalog`, `hypoth_equivalog_domain`, `paralog`, `paralog_domain`, `repeat`, `retired`, `signature`, `subfamily`, `subfamily_domain`, `superfamily`
- `NcbifamFamily.is_uninformative`: `true`

## Interpretation

Read `family_type` before trusting the name: `equivalog` (and
`equivalog_domain`) means every member shares the function, so the family
name can be used as the gene's function; `subfamily` / `superfamily` /
`domain` mean shared ancestry, not shared function; `hypoth_equivalog`
is a conserved hypothetical; `exception` marks a family whose name is a
deliberate carve-out; `retired` families are kept for provenance and
should not be reported. Rank competing hits on one gene by `bit_score`
(verbose). `gene_symbol` is the quickest way to answer "which gene is
ntcA in this genome".

## Informativeness rule

About 200 families are flagged uninformative and dropped by
`informative_only=True`: mostly `hypoth_equivalog` (114 — conserved
hypotheticals) and `hypoth_equivalog_domain` (12), plus generically
named `equivalog` (51) and `subfamily` (14) families. `superfamily` and
`signature` families are not flagged; the flag is name-based, not
type-based. There is no `family_type` filter on the tools — list the
types with `list_filter_values(filter_type='ncbifam_family_type')`, read
the `by_family_type` envelope on `search_ontology`, browse with
`verbose=True` and filter client-side, or read `family_type` on
`ontology_term_details`.

## Pitfalls

- The `TIGR` accessions are NCBIfam families, not TIGR *roles*
  (`tigr_role` is a different ontology, reached from a family through
  the `Ncbifam_family_has_tigr_role` router link).
- A `subfamily`/`superfamily` hit does not license the family name as the
  gene's function; only `equivalog`-type families do.
- `bit_score` / `evalue` are verbose-only and never filterable.
- Flat: `level=1` returns nothing; hierarchy questions go through the
  InterPro bridge, which only about half of the families carry.
- `retired` families (`family_type='retired'`) still hold gene edges;
  do not quote them as current names.

## Typical questions

- Which equivalog-type NCBIfam families does MIT1002 carry that MED4 lacks? — `genes_by_ontology(ontology='ncbifam', organism='MIT1002', summary=True)` vs `organism='MED4'`, then keep `family_type='equivalog'` via `ontology_term_details`
- Which gene is `ntcA` in a Prochlorococcus genome, by NCBIfam gene symbol? — `search_ontology(ontology=['ncbifam'], search_text='ntcA', verbose=True)` then `genes_by_ontology(ontology='ncbifam', organism='MED4', term_ids=['ncbifam:TIGR03697'])`
- Which InterPro entry integrates `ncbifam:NF006762`, and which TIGR roles does `ncbifam:TIGR00254` route to? — `ontology_term_details(term_ids=['ncbifam:NF006762','ncbifam:TIGR00254'])` and read `links_out[]` (`membership` → `interpro:IPR001731`; `router` → `tigr.role:710`, `tigr.role:264`)
- Among genes up under nitrogen limitation, which named NCBIfam families recur? — `pathway_enrichment(..., ontology='ncbifam', direction='up')`

## Tools

- `search_ontology(ontology=['ncbifam'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='ncbifam', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['ncbifam'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['ncbifam'])` then `pathway_enrichment` / `cluster_enrichment(ontology='ncbifam', level=N)` — ORA.

## See also

- `docs://ontologies/interpro`
- `docs://ontologies/pfam`
- `docs://ontologies/tigr_role`
- `docs://analysis/annotation_evidence`
- `docs://tools/search_ontology`
- `docs://tools/ontology_term_details`
