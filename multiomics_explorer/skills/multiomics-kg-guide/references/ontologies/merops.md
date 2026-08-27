# MEROPS peptidase families (`merops`)

Generated from `inputs/ontologies/merops.yaml`, the `ONTOLOGY_CONFIG` registry and `config/schema_baseline.yaml` — do not edit. Index: `docs://ontologies/index`.

## What it is

MEROPS — the peptidase (protease) and peptidase-inhibitor database.
Families are grouped by catalytic mechanism (`catalytic_type`: serine,
cysteine, metallo, aspartic, threonine, glutamic, asparagine lyase,
mixed, unknown) into clans that share a fold (`merops.clan:SC`,
`merops.clan:MA`), with families (`merops.family:S33` prolyl
aminopeptidase, `merops.family:S14` Clp protease) and some subfamilies
below. `family_class` separates peptidase families from inhibitor
families. Term nodes also carry cleavage-specificity summaries
(`cleavage_summary`, `cleavage_p1_residues`, `known_cleavage_count`) from
MEROPS substrate data.

## How genes get annotated

Gene → family edges come from a DIAMOND search against MEROPS sequences
(`sources=['merops_diamond']`, `evidence='homology'`). The materially
important column is the compact `call_class`: `peptidase` (the best hit
is an active peptidase — a holotype or putative peptidase),
`nonpeptidase_homolog` (the best hit is a MEROPS-curated catalytically
dead homolog — same family, no proteolytic activity), or `inhibitor` (an
inhibitor-family hit). Trust axes: `evidence_score` in [0, 1], `tier`,
and verbose native detail (`confidence_score` — the rank prop —
`pfam_support`, `best_hit_kind`, `identity`, `qcov`, `evalue`,
`consensus_n`, `best_hit_id`). Families bridge *out* to the Pfam domains
that define them (`Merops_family_has_pfam_domain`, composition, with
`member_id_count` = how many MEROPS members carry that domain).

## Identifier form

`merops.clan:SC` (level 0), `merops.family:S33` (level 1),
`merops.family:S33A`-style subfamilies (level 2). The letter encodes the
catalytic type (S serine, C cysteine, M metallo, A aspartic, T threonine,
G glutamic, N asparagine lyase, P mixed, U unknown; inhibitors use `I`).
Node `merops_id` holds the bare identifier.

## Hierarchy

Three levels via `Merops_family_is_a_merops_family`, `level_kind`
`merops_clan` (0) → `merops_family` (1) → `merops_subfamily` (2).
`gene_count` / `organism_count` are subtree-inclusive and count *every*
hit including non-peptidase homologs; `peptidase_gene_count` /
`peptidase_organism_count` count only `call_class='peptidase'` edges and
are the numbers to quote for "how many proteases". `direct_gene_count` is
node-local; `member_count` is MEROPS's own family size.

## Graph shape (from the registry)

| | |
|---|---|
| Node label | `MeropsFamily` |
| Gene → term edge | `Gene_has_merops_family` |
| Hierarchy edges (child → parent) | `Merops_family_is_a_merops_family` |
| Fulltext index | `meropsFamilyFullText` |
| Trust axes on the gene edge | `sources`, `evidence`, `evidence_score`, `tier` |
| Rank prop | `confidence_score` |
| Compact edge columns | `call_class` |
| Verbose edge detail | `confidence_score`, `pfam_support`, `best_hit_kind`, `identity`, `qcov`, `evalue`, `consensus_n`, `best_hit_id` |
| Term columns, verbose `search_ontology` | `family_class`, `catalytic_type`, `peptidase_gene_count` |
| Extra compact columns, `ontology_term_details` | `merops_id`, `family_class`, `catalytic_type`, `peptidase_gene_count`, `peptidase_organism_count`, `direct_gene_count`, `member_count`, `cleavage_summary`, `cleavage_p1_residues`, `known_cleavage_count` |
| Bridges out (`links_out`) | `Merops_family_has_pfam_domain` → `pfam` (*composition*) |

Bridges are forward-only: `ontology_term_details` lists `links_out` on the source term; there is no `links_in`. `composition` = built from these parts; `membership` = one of that ontology's known members; `router` = a computed cross-reference, recall-biased, never a gene-function call.

## Node properties (`MeropsFamily`)

| Property | Type | Meaning |
|---|---|---|
| `catalytic_type` | string |  |
| `cleavage_p1_residues` | list |  |
| `cleavage_summary` | string |  |
| `description` | string | longer free text (verbose on `search_ontology`; compact on `ontology_term_details`) |
| `direct_gene_count` | int | genes attached to this exact node (not descendants); absent where it would be vacuous |
| `family_class` | string |  |
| `gene_count` | int | genes annotated to the term — subtree-inclusive on hierarchical labels, direct on flat ones |
| `id` | string | term ID as used in `term_ids=[...]` (self-prefixed CURIE) |
| `known_cleavage_count` | int |  |
| `level` | int | hierarchy depth, 0 = root / broadest |
| `level_kind` | string | what a level means in this ontology (see the vocabulary below) |
| `member_count` | int | upstream family size (source-database members), not KG genes |
| `merops_id` | string |  |
| `name` | string | term name (what `search_ontology` indexes) |
| `organism_count` | int | organisms with at least one gene annotated to the term (subtree-inclusive where `gene_count` is) |
| `peptidase_gene_count` | int |  |
| `peptidase_organism_count` | int |  |
| `preferred_id` | string | same value as `id` |

`ontology_term_details(verbose=True)` returns every property as `properties`; a compact column that is missing on the node is absent, not null (`docs://guide/conventions`).

## Controlled vocabularies

- `Gene_has_merops_family.best_hit_kind`: `holotype`, `putative`, `nonpeptidase_homolog`
- `Gene_has_merops_family.call_class`: `peptidase`, `inhibitor`, `nonpeptidase_homolog`
- `Gene_has_merops_family.evidence`: `homology`
- `Gene_has_merops_family.pfam_support`: `corroborated`, `uncorroborated`
- `Gene_has_merops_family.sources`: `merops_diamond`
- `MeropsFamily.catalytic_type`: `serine`, `cysteine`, `metallo`, `aspartic`, `threonine`, `glutamic`, `asparagine_lyase`, `mixed`, `unknown`
- `MeropsFamily.cleavage_p1_residues`: `Ala`, `Arg`, `Asn`, `Asp`, `Cys`, `Gln`, `Glu`, `Gly`, `His`, `Ile`, `Leu`, `Lys`, `Met`, `Phe`, `Pro`, `Ser`, `Thr`, `Trp`, `Tyr`, `Val`
- `MeropsFamily.family_class`: `peptidase`, `inhibitor`
- `MeropsFamily.level_kind`: `merops_clan`, `merops_family`, `merops_subfamily`

Values are read from the KG's `ControlledVocabulary` nodes at build time; confirm live via `list_filter_values(filter_type=..., ontology='merops')`.

## Interpretation

Always decide what the question is: a **peptidase census** wants
`call_class=['peptidase']` (or the term-side `peptidase_gene_count`); a
**sequence-family census** wants the unfiltered set. The tools warn when
`nonpeptidase_homolog` rows are present in an unfiltered result. Rank a
gene's competing family hits by `confidence_score` / `evidence_score`;
`pfam_support='corroborated'` means the family's defining Pfam domain is
also on the gene. `call_class` is orthogonal to `tier` — a confident hit
can be a confident non-peptidase homolog. Family level (1) is the
enrichment unit; clan level (0) groups by fold.

## Informativeness rule

No MEROPS node is flagged uninformative. Clan roots are large by
construction; enrich at `level=1`. `call_class` on enrichment shapes both
the term sets and the background, so a peptidase-only ORA is a different
test from an all-hits ORA.

## Pitfalls

- `gene_count` on a MEROPS term includes catalytically dead homologs;
  quote `peptidase_gene_count` for protease counts.
- `call_class` is an edge property — one gene can be `peptidase` in one
  family and `nonpeptidase_homolog` in another (`gene_overview` exposes
  the set as `merops_classes`).
- `inhibitor` families are not proteases; `family_class='inhibitor'`
  on the term is the term-side twin.
- `evidence_score` is MEROPS-internal; `merops_evidence_score_max` on
  `gene_overview` is sparse (null = no MEROPS call — rank, don't filter).
- Cleavage-specificity fields describe the family's known substrates in
  MEROPS, not this organism's biology.

## Typical questions

- How many active peptidases, by clan, does MIT1002 carry vs MED4?
- Which MEROPS families are enriched among genes up in stationary phase, counting peptidase calls only?
- Is `PMM0001`'s S14 hit an active Clp protease or a non-peptidase homolog?
- Which Pfam domains define `merops.family:S33`, and what are its cleavage-site preferences?

## Tools

- `search_ontology(ontology=['merops'])` — browse (no `search_text`; sorted by `gene_count`, filter with `level` / `min_gene_count` / `organism`) or Lucene search over term names.
- `ontology_term_details(term_ids=[...])` — one term or a batch: parents, children, `links_out` bridges, `gene_count` / `organism_count`, and per-organism counts with `verbose=True`.
- `genes_by_ontology(ontology='merops', organism=..., term_ids=[...] | level=N)` — term → genes (TERM2GENE for enrichment); `gene_ontology_terms(ontology=['merops'], locus_tags=[...])` — genes → terms.
- `ontology_landscape(ontology=['merops'])` then `pathway_enrichment` / `cluster_enrichment(ontology='merops', level=N)` — ORA.

## See also

- `docs://analysis/annotation_evidence`
- `docs://analysis/enrichment`
- `docs://ontologies/pfam`
- `docs://ontologies/brite`
- `docs://tools/gene_overview`
- `docs://tools/genes_by_ontology`
- `docs://tools/ontology_term_details`
