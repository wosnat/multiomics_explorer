# Annotation trust — reading "why do we believe this"

LLM-facing guide to the trust surface that sits on every gene→ontology-term
annotation across all 17 supported ontologies. Every `Gene_has_*` /
`Gene_involved_in_*` / `Gene_catalyzes_*` edge carries some subset of the
facts below; this page tells you which ontology carries which fact, where it
lives (compact row / verbose row / filter param), and how to use it without
misreading a categorical for a curation grade.

Runnable companion: `docs://examples/annotation_evidence.py` (5 scenarios:
`merops_call_class`, `tcdb_attachment_depth`, `interpro_enrichment`,
`trust_filtered_tcdb`, `organism_rollups`).

> **Counts in this doc are an illustrative snapshot** and drift with each KG
> rebuild. Use them for rough scale only; call `list_filter_values`,
> `ontology_landscape`, or `kg_release_info` for current figures.

---

## Three layers, one home each

Every gene→term edge fact belongs to exactly one of three layers. Where a
fact lives (compact column, verbose column, filter param) follows from which
layer it's in — this is the single decision that resolves almost every
question about the trust surface.

### Comparable trust axes

Facts with the *same meaning* wherever they occur:

- `sources[]` — which pipeline made the call (`eggnog`, `interproscan`,
  `uniprot`, `cyanorak`, ...).
- `evidence` — the five-rung ladder, see "The evidence ladder" below.
- `evidence_score` — a `[0, 1]` composite; TCDB, MEROPS, GO×3, EC, Pfam, CAZy.
- `tier` — 1–3, diamond-truncation depth of the ortholog call; TCDB / MEROPS.

Where they live: `evidence` is compact on every row of the 14 functional-edge
ontologies (null on PSORTb / SignalP, which carry no trust axes). `sources`,
`evidence_score`, `tier` are verbose. All four are filterable (`sources=`,
`evidence=`, `max_tier=`, `min_evidence_score=`), default `None` — a call with
no trust filters returns exactly what it always did.

### Native trust detail

Ontology-specific scalars that must **never** be compared across ontologies —
scale and direction differ (e-value lower-is-better; bit score, confidence,
probability higher-is-better):

- TCDB: `confidence_score`, `source_agreement`, `pfam_support`, `go_support`,
  `identity`, `qcov`, `evalue`, `consensus_n`, `attachment_depth`.
- MEROPS: `confidence_score`, `pfam_support`, `best_hit_kind`, `identity`,
  `qcov`, `evalue`, `consensus_n`, `best_hit_id`.
- InterPro: `libraries`, `evalue_library`, `evalue`, `match_count`, `start`, `end`.
- NCBIfam: `evalue`, `bit_score`, `start`, `end`.
- PSORTb: `localization_score`. SignalP: `signal_peptide_probability`,
  `signal_peptide_cleavage_site`, `signal_peptide_cleavage_probability`.

Where they live: verbose-only, under their native names. **Never a filter** —
no cutoff exists on any native scalar (InterPro's e-value included); none is
calibrated well enough to threshold safely.

### Materially-important facts

Categoricals whose *absence changes the biological reading*, not just its
confidence:

- MEROPS `call_class` — `peptidase` (a real peptidase call), `inhibitor` (a
  peptidase-inhibitor family), `nonpeptidase_homolog` (catalytically dead but
  sequence-similar). Compact **always**, filterable (`call_class=`), rolled up
  (`by_call_class`), auto-warned when `nonpeptidase_homolog` rows are silently
  included in a census.
- InterPro `interpro_type` — the 8-way FAMILY / DOMAIN / ... split. Same
  "compact always" treatment, though it is a term-character fact rather than an
  edge fact.

Why one compact column and not four: rollups already carry the distribution
(`by_evidence`, `by_tier`, `by_sources`), so the per-row payload only needs
the one axis an agent can read on **every** functional-edge row —
`evidence`. `evidence_score` is null on most of the 14 (only TCDB, MEROPS,
GO×3, EC, Pfam, CAZy carry it), so it moved to verbose and kept its role as
the within-ontology sort key and the *only* numeric cutoff in the whole
surface (`min_evidence_score`).

---

## The evidence ladder — one canonical paragraph

`evidence` is one of five rungs, strongest first:

| Rung | Intended meaning |
|---|---|
| `curated` | Asserted by a reference annotation (UniProt / NCBI / Cyanorak curation). |
| `signature` | A profile-HMM / signature hit from InterProScan on a family-level model (Pfam). |
| `homology` | A sequence-similarity call with an explicit hit (TCDB / MEROPS diamond). |
| `family_inferred` | Transferred from an ortholog family (eggNOG KO / COG / TCDB transfer, NCBIfam equivalog → TIGR role). |
| `domain_inferred` | Inferred from a domain-level match only (InterPro router to EC / CAZy / GO). |

Multi-source edges take the strongest rung. Rank by rung within one ontology;
across ontologies compare only with the live caveat below in mind.

**Live state (current build).** The rung is derived from `sources` at KG
build time, uniformly across every edge type: any curated source (`cyanorak`,
`uniprot`, `ncbi`) ⇒ `curated`; an `eggnog` source with no curated source ⇒
`family_inferred` (an orthology transfer — GO-BP ~434k edges, GO-MF ~180k,
GO-CC ~100k, EC 11.7k, Pfam 24.7k, CAZy 744 are eggNOG-only); InterProScan-only
⇒ the recorded signature strength (`signature` on Pfam, `family_inferred` /
`domain_inferred` elsewhere). The one asymmetry is deliberate: an
`['eggnog','interproscan']` pair reads `signature` on Pfam (the HMM hit is the
native rung) but `family_inferred` on GO / EC / CAZy. So `evidence=['curated']`
selects reference assertions everywhere, and `evidence_score` on an eggNOG-only
edge is 0.333 (single source, transferred). Older builds read eggNOG-only
GO / EC / Pfam / CAZy edges as `curated`; `kg_release_info` says which build
you are on. The per-ontology pages
(`docs://ontologies/{key}`) link here rather than restating the rungs.

---

## Per-ontology trust profile

| Ontology | Trust axes | `rank_prop` | Materially-important (compact) | Native detail (verbose) | Term facet |
|---|---|---|---|---|---|
| `go_bp`, `go_mf`, `go_cc` | sources, evidence, evidence_score | — | — | — | — |
| `ec` | sources, evidence, evidence_score | — | — | — | — |
| `kegg` | sources, evidence | — | — | — | — |
| `cog_category` | sources, evidence | — | — | — | — |
| `tigr_role` | sources (⊆ `[cyanorak, interproscan]`; an agreeing edge carries both — filter by membership, which the `sources=` filter already does), evidence (`curated` / `family_inferred`) | — | — | — | — |
| `cyanorak_role` | sources, evidence | — | — | — | — |
| `pfam` | sources, evidence, evidence_score | — | — | — | — |
| `brite` | (inherits kegg's — the gene edge is `Gene_has_kegg_ko`) | — | — | — | `tree` |
| `tcdb` | sources, evidence, evidence_score, tier | evidence_score | — | confidence_score, source_agreement, pfam_support, go_support, identity, qcov, evalue, consensus_n, attachment_depth | — |
| `cazy` | sources, evidence, evidence_score | — | — | — | — |
| `subcellular_localization` (PSORTb) | *none* | — | — | localization_score | — |
| `signal_peptide_type` (SignalP) | *none* | — | — | signal_peptide_probability, signal_peptide_cleavage_site, signal_peptide_cleavage_probability | — |
| `interpro` | sources, evidence | — | `interpro_type` (8-way, term-side) | libraries, evalue_library, evalue, match_count, start, end | `interpro_type` |
| `ncbifam` | sources, evidence | — | — | evalue, bit_score, start, end | — |
| `merops` | sources, evidence, evidence_score, tier | confidence_score | `call_class` (`peptidase` / `inhibitor` / `nonpeptidase_homolog`) | confidence_score, pfam_support, best_hit_kind, identity, qcov, evalue, consensus_n, best_hit_id | — |

`rank_prop` is what a hierarchical rollup ranks a gene's edges by when
picking the one edge whose trust columns populate an ancestor-term row (see
"One edge per (gene, term)" below). Ontologies without a `rank_prop` are
either flat or don't carry `evidence_score`/`confidence_score` at all.

`brite` shares `kegg`'s axes because BRITE gene membership is carried by the
same `Gene_has_kegg_ko` edge KEGG uses — there is no separate BRITE gene
edge to have its own trust facts.

---

## One edge per (gene, term)

A hierarchical ontology lets one gene reach the same ancestor term through
several annotations at once. Ask `genes_by_ontology` for TCDB at level 2 and
a transporter annotated to three different subfamilies under the same
superfamily reaches that superfamily three times.

Every gene × term row is still exactly one row. The row's identity columns
(`locus_tag`, `term_id`, `term_name`, `level`) describe the pair, and the
trust columns (`evidence`, `sources`, `evidence_score`, `tier`, plus
`call_class` and the native detail) are read off **one** of those
annotations: the gene's best edge under that term, chosen by the ontology's
`rank_prop` — `evidence_score` for TCDB, `confidence_score` for MEROPS, and
the depth of the attachment itself when the ontology declares neither.
Highest wins.

Three consequences worth holding on to:

- **A rollup row's trust is the gene's best case for that term, not its
  average.** `evidence: curated` on an ancestor row means at least one of
  the gene's annotations under that ancestor is curated; it says nothing
  about the others.
- **Filters win over the tiebreak.** The trust filters apply to the
  candidate edges before the best one is picked, so a `max_tier=2` row can
  never report `tier=3` by way of an edge the filter already removed. The
  gene simply drops out if nothing under that term survives.
- **Leaf mode does not need any of this.** In `gene_ontology_terms(mode=
  'leaf')` the term IS the attachment, so the row's trust columns are that
  edge's own facts. TCDB narrows further to the deepest surviving
  attachment — see the leaf-mode recipe below.

To see the individual annotations rather than the best one, drop to leaf
mode (`gene_ontology_terms`), where each attachment is its own row.

---

## Rank vs. filter — the one rule that matters most

Every numeric trust field in this surface falls into exactly one of two
buckets, and mixing them up is the most common mistake:

- **Rank by it.** `evidence_score` (row) and the gene-level rollups
  `tcdb_evidence_score_max` / `merops_evidence_score_max` (on `gene_overview`)
  are meant to be sorted on, not thresholded — except through the one
  sanctioned cutoff below. `0` is a real, uncorroborated hit, not an absence
  signal; absence is `null` (no call at all on that gene/edge). This mirrors
  substrate resolution / depth in `docs://analysis/metabolites` — the phrase
  "rank by it, never filter by it" describes the *gene-level max* rollups
  specifically.
- **Filter by it — but only through `min_evidence_score`.** The edge-level
  `evidence_score` *does* have exactly one sanctioned cutoff:
  `min_evidence_score=` on `genes_by_ontology`, `gene_ontology_terms`,
  `pathway_enrichment`, `cluster_enrichment`. On `genes_by_ontology` and
  `gene_ontology_terms`, setting it adds `evidence_score_signals` to the
  envelope — the `ControlledVocabulary`-backed list of composite inputs that
  feed the score for that edge type, keyed by edge type (live: TCDB
  `Gene_has_tcdb_family` → `eggnog_called`, `source_agreement`, `tier_le_2`,
  `pfam_support`, `go_support`; GO-BP → `multi_source`,
  `high_trust_assertion`, `not_domain_inferred`), so you can see what the
  number is actually made of before trusting a threshold. `identity` / `qcov`
  are native detail, not signals. `pathway_enrichment`
  / `cluster_enrichment` apply the same cutoff to shape the TERM2GENE mapping
  and background but don't carry `evidence_score_signals` themselves — read
  it from a `genes_by_ontology` call with the same filters first if you need
  the signal breakdown.
- **Never filter native detail.** No cutoff exists — or should be
  hand-rolled via `run_cypher` — on `evalue`, `bit_score`, `confidence_score`,
  `identity`, `qcov`, or any other native scalar. Different ontologies'
  native scalars aren't just differently scaled, some go the *opposite
  direction* (lower e-value is better; higher bit score is better), so even
  an internally-consistent per-ontology threshold doesn't generalize, and none
  of these fields are calibrated well enough across the KG's contributing
  pipelines to justify a universal default.

Defaults never filter: every trust param (`sources`, `evidence`, `max_tier`,
`min_evidence_score`, `call_class`) is `None` by default, so a call with no
trust filters returns the same rows it always did — the trust surface is
purely additive until you opt in.

Passing an axis an ontology doesn't carry raises `ValueError` naming that
ontology's supported axes — check first via
`list_filter_values(filter_type='trust_axes', ontology=...)`.

---

## The sparse row convention

A row only carries the trust columns its ontology owns — `tier` never
appears on a `kegg` row (KEGG has no tier axis); `interpro_type` never
appears on a `tcdb` row. Owned-but-null columns stay (a TCDB edge with only
eggNOG support carries `tier: null`, not an absent field). The rule holds on
the MCP wire as well as in the Python API, and it is the general row
convention: result rows are serialized sparsely — a key that is absent means
"not applicable to this row" (a verbose-only column on a compact call, an
axis this ontology does not carry), a key that is `null` means "applicable,
but this record has no value" (a gene with no MEROPS call carries
`merops_evidence_score_max: null`). A compact `tcdb` row from
`genes_by_ontology` is ~9 keys, a verbose one ~22. Three tools keep a
deliberately None-padded union shape instead, so their rows always carry
every column: `genes_by_metabolite` / `metabolites_by_gene` (cross-arm
fields, see `docs://analysis/metabolites`) and `assays_by_metabolite` /
`discussed_by_publication` (polymorphic rows).

---

## Multi-ontology filter scoping

On `gene_ontology_terms` and `ontology_landscape`, a trust filter carried by
every requested ontology applies normally; carried by some but not all
applies to those and drops the rest into `skipped_ontologies` with a
warning; carried by none raises. A **facet** — `interpro_type` for InterPro,
`tree` for BRITE — behaves differently: it narrows its own ontology and
leaves the others untouched (nothing is skipped), and raises when its owner
is not in the list at all.

---

## Envelope rollups are full-match

`by_evidence`, `by_tier`, `by_sources`, `by_call_class` and
`evidence_score_stats` describe every matching row, not the page you are
reading, and they are populated in compact mode — where `tier`, `sources`
and `evidence_score` are not on the row at all, the envelope is the only
place to read their distribution. On `gene_ontology_terms` they are empty
under `summary=true`, which fetches no rows.

---

## Vocabulary values: registered vs. pivoted

Filterable trust values (`evidence`, `sources`, `call_class`,
`interpro_type`, and the other categorical `filter_type`s on
`list_filter_values`) are read from the KG's `ControlledVocabulary` nodes,
never hard-coded. If a `ControlledVocabulary` node is missing for some edge
type, a live pivot query derives the value set instead, flagged `source:
"pivot"` plus a warning — same values, just not pre-registered. The same
rule covers non-trust closed vocabularies such as `cluster_type`.

---

## Vocabulary-hash compatibility

The KG stamps `Schema_info.controlled_vocabularies_hash` (sha256 over every
`ControlledVocabulary` entry's ids, values, closed/sparse flags and score
signals — descriptions excluded). `kg_release_info` compares it with the
hash the explorer was built against; a mismatch, or a KG that predates the
vocabulary contract, yields `verdict: warn` — never worse. What it means:
calls are unaffected (filters validate live, `list_filter_values` reads
live), but the value lists quoted in `docs://ontologies/{key}` pages and in
parameter descriptions were rendered from the pinned vocabulary and may be
stale. When the warn is up, trust `list_filter_values` over any quoted
list. The pin is re-set at explorer release time to equal the live KG's
hash.

---

## MEROPS `call_class` — orthogonal to `tier`

`call_class` (`peptidase` / `inhibitor` / `nonpeptidase_homolog`) answers "is
this gene actually catalytically active," not "how confident are we." A
`nonpeptidase_homolog` row can have a high `tier` and a strong
`confidence_score` — the annotation pipeline is very sure the gene resembles
a peptidase family by sequence, and equally sure that the catalytic residues
are degraded (a known evolutionary pattern — pseudo-enzymes retained for a
non-catalytic role). `inhibitor` marks a gene whose best hit lands in a
MEROPS peptidase-inhibitor family rather than a peptidase or homolog family
— a third, distinct type, not a confidence gradient on the other two. Treat
`call_class` as a **type** filter, not a **quality** filter:

- Read `tier` / `confidence_score` / `pfam_support` to judge *how sure* the
  MEROPS call is, for any `call_class`.
- Read `call_class` to judge *whether the gene is predicted to cleave
  peptide bonds, inhibit a peptidase, or neither*.

Omitting `call_class` from a `genes_by_ontology(ontology="merops", ...)` /
`pathway_enrichment(ontology="merops", ...)` call folds
`nonpeptidase_homolog` rows into whatever census or gene set you're
building, and fires an auto-warning naming the affected row count. Pass
`call_class=["peptidase"]` whenever the question is about protease activity
specifically — most questions are.

---

## InterPro `(interpro_type, level)` — why enrichment requires the type

InterPro registers 8 structurally distinct entry types —
`FAMILY`, `DOMAIN`, `HOMOLOGOUS_SUPERFAMILY`, `REPEAT`, `CONSERVED_SITE`,
`ACTIVE_SITE`, `BINDING_SITE`, `PTM` — and they size very differently at the
same hierarchy level (a MED4-scale snapshot at level 0: HOMOLOGOUS_SUPERFAMILY
74 testable terms, DOMAIN 47, FAMILY 5, CONSERVED_SITE 4, REPEAT 1, the
other three none).
Pooling them for enrichment would let the largest type dominate the Fisher
background the way an unscoped BRITE run is dominated by the enzyme tree.

Because of this, `interpro_type` is **required** whenever
`pathway_enrichment` or `cluster_enrichment` is called with
`ontology="interpro"` — omitting it raises. It is optional (a facet, not a
requirement) on `genes_by_ontology`, `gene_ontology_terms`,
`ontology_landscape`, and `search_ontology`, where InterPro rows carry
`interpro_type` as a compact column regardless of whether you scoped the
call.

Workflow: `ontology_landscape(organism=..., ontology="interpro")` to see the
per-type term-size breakdown (InterPro rows break down by `interpro_type` the
way BRITE rows break down by `tree`) → pick a type → pass it as
`interpro_type=` into enrichment.

---

## Bridges — forward-only composition / membership / router edges

Several ontologies carry a forward edge from their own term nodes into
another ontology's terms — TCDB families to Pfam domains and GO terms,
MEROPS families to Pfam domains, Pfam entries to InterPro entries, NCBIfam
families to InterPro entries, InterPro entries to EC numbers and CAZy
families (a **router** — InterPro's function-inference relation is
recall-biased and should never be read as "this gene has this EC/CAZy
function," only "this InterPro entry family clusters with this
EC/CAZy family"), NCBIfam families to TIGR roles
(`Ncbifam_family_has_tigr_role`, 1,847 edges, all from `TIGR*`-prefixed
families — also a router: only the `equivalog` subset licenses a gene-level
`Gene_has_tigr_role` edge (`evidence='family_inferred'`); the other family
types reach a role through the bridge only), and KEGG terms to BRITE
categories. TIGR roles themselves are a two-level hierarchy (21 main roles at
level 0, 115 sub-roles at level 1; `docs://ontologies/tigr_role`). Each bridge carries a
`link_kind` — `composition` (this family is built from these Pfam domains /
GO functions), `membership` (this family is one of that ontology's known
members), or `router` (a computed cross-reference, ambiguous when a source
term maps to multiple targets or isn't a `FAMILY`-type InterPro entry).

Bridges are modeled **forward only** by design — family → what characterizes
it, never the reverse (`links_in` does not exist). Walk them with
`ontology_term_details(term_ids=[...])`: each row carries `links_out[]`
(`{rel, link_kind, target_id, target_ontology, target_name}`; verbose adds the
edge props — `curated_tcids` on TCDB composition links, `member_id_count` on
MEROPS → Pfam, and `router_ambiguous` on InterPro router links — not a KG
property but computed by `ontology_term_details` at verbose time as
`links_total(router) > 1 OR interpro_type <> 'FAMILY'`, on InterPro links
only),
and `link_kinds=[...]` narrows to one kind. A two-hop walk
(`tcdb:3.A.1` → Pfam domains → InterPro entries) is scenario `bridge_walk`
in `docs://examples/ontology_terms.py`. To reach a *source* term from its
target (which TCDB families are built from this Pfam domain?) you still need
`run_cypher` — e.g.
`MATCH (t:TcdbFamily)-[:Tcdb_family_has_pfam_domain]->(p:Pfam {id: $id}) RETURN t`.
`list_filter_values(filter_type="link_kinds")` enumerates the kind vocabulary
and which bridge relationships carry each kind; every ontology's reference
page (`docs://ontologies/{key}`, index `docs://ontologies/index`) lists its
bridges out and in.

---

## Scenario `merops_call_class` — MEROPS peptidase-only clan census

**When:** "how many genes in this organism actually encode peptidases, by
clan?" — not "how many genes resemble a peptidase family by sequence."

```python
with_call_class = genes_by_ontology(
    ontology="merops", organism="MIT1002", level=0,
    call_class=["peptidase"],
)
# MIT1002 level 0, call_class=['peptidase']: 7 clans pass the default
# gene-set-size filter — SC 22, MA 18, MH 8, PB 8, SB 6, MG 5, SK 5.
# No warning fires; nonpeptidase_homolog rows are excluded by the filter.

without_call_class = genes_by_ontology(
    ontology="merops", organism="MIT1002", level=0,
)
# Omitting call_class returns 10 clans and fires a warning naming the
# nonpeptidase_homolog rows folded into the census.
```

Read `by_call_class` on either call to see the split without a second query.

---

## Scenario `tcdb_attachment_depth` — TCDB leaf mode: most-specific vs superseded

**When:** "what's this gene's actual TCDB call, not every ancestor it also
technically belongs to?"

```python
leaf_only = gene_ontology_terms(
    locus_tags=["PMM0392"], organism="MED4",
    ontology=["tcdb"], mode="leaf",
)
# Default: attachment_depth='most_specific' only — PMM0392: 7 rows.
# Genome-wide MED4: 670 raw tcdb edges collapse to 597 rows under this
# predicate.

with_superseded = gene_ontology_terms(
    locus_tags=["PMM0392"], organism="MED4",
    ontology=["tcdb"], mode="leaf", include_superseded=True, verbose=True,
)
# Adds back the 73 (genome-wide) rows most_specific drops, each labelled
# attachment_depth='superseded' — less specific, not wrong. PMM0392: 8 rows
# (7 most_specific + 1 superseded). PMM0392's
# superseded row is the tcdb:3.A.1 ABC-superfamily ancestor of its actual
# (deeper) subfamily attachment. `attachment_depth` is TCDB native detail,
# so the label itself needs verbose=True; the row set widens either way.
```

`include_superseded` is a leaf-mode-only switch; it has no effect outside
`mode="leaf"`.

---

## Scenario `interpro_enrichment` — InterPro-scoped enrichment

**When:** "which InterPro homologous superfamilies are enriched in my DE
set?" — a question that only makes sense scoped to one `interpro_type`.

```python
try:
    pathway_enrichment(
        organism="MED4", experiment_ids=[...],
        ontology="interpro", level=0,
    )
except Exception:
    pass  # raises: interpro_type is required when ontology='interpro'

result = pathway_enrichment(
    organism="MED4", experiment_ids=[...],
    ontology="interpro", interpro_type="HOMOLOGOUS_SUPERFAMILY", level=0,
)
```

Check term sizes per type first: `ontology_landscape(organism="MED4",
ontology="interpro")` — MED4 example: `interpro:IPR027417` ("P-loop
containing nucleoside triphosphate hydrolase") reaches 119 genes at
`interpro_type='HOMOLOGOUS_SUPERFAMILY'`, one of the largest single terms in
that stratum.

---

## Scenario `trust_filtered_tcdb` — Trust-filtered TCDB gene set before enrichment

**When:** "restrict a TCDB-based gene set to homology calls with a
corroborated score before testing it" — tightening a noisy hierarchical
ontology the same way `substrate_depth=['most_specific']` tightens transport
chemistry rows (see `docs://analysis/metabolites`).

```python
# Discover the axis set first (skip if already known).
axes = list_filter_values(filter_type="trust_axes", ontology="tcdb")
# ['sources', 'evidence', 'evidence_score', 'tier']

filtered = genes_by_ontology(
    ontology="tcdb", organism="MED4", level=2,
    evidence=["homology"], min_evidence_score=0.6,
)
# MED4 tcdb, genome-wide: 670 raw gene x family edges narrow to 98 under
# evidence=['homology'] AND evidence_score>=0.6; rolled up to level 2 those
# 98 edges collapse to 44 (gene x term) rows (total_matching). Read
# filtered["evidence_score_signals"] to see which composite inputs back
# the 0.6 threshold for this edge type.

enrichment = pathway_enrichment(
    organism="MED4", experiment_ids=[...],
    ontology="tcdb", level=2,
    evidence=["homology"], min_evidence_score=0.6,
)
# The same filters shape the enrichment TERM2GENE mapping AND the
# background identically (both traverse the same gene->leaf match stage),
# so gene set and background stay apples-to-apples —
# envelope["background_filtered"] confirms this.
```

---

## Scenario `organism_rollups` — coverage per organism

**When:** "which organisms carry the most peptidase / InterPro / NCBIfam
annotation?" — before choosing an organism for a trust-filtered census.

```python
orgs = list_organisms(limit=None)
orgs["top_annotation_capability"][:3]
# top 10 organisms by peptidase_gene_count (then name); columns
# peptidase_gene_count / nonpeptidase_homolog_gene_count / interpro_gene_count /
# ncbifam_gene_count; Alteromonas (MarRef v6) leads. The same four counts sit
# on every list_organisms row (zero-filled).
```

---

## Quick decision tree

```
Question involves "how confident / which pipeline / what type" on an
annotation
├─ "Compare trust across ontologies" → evidence (compact, every functional edge)
├─ "Rank within one ontology by corroboration" → evidence_score (verbose; TCDB/MEROPS/GO×3/EC/Pfam/CAZy only)
├─ "One hard cutoff on corroboration" → min_evidence_score (the only numeric filter; check evidence_score_signals)
├─ "Diamond-truncation depth of the ortholog call" → tier (TCDB/MEROPS only; max_tier keeps tier-null rows)
├─ "Is this actually a peptidase, not just homologous to one" → call_class (MEROPS only, compact always)
├─ "Which InterPro structural type" → interpro_type (compact always; REQUIRED on interpro enrichment)
├─ "Native e-value / bit score / identity / confidence_score" → verbose-only, per-ontology name, never a filter
├─ "Most-specific vs redundant ancestor attachment" → attachment_depth (TCDB; mode='leaf' + include_superseded)
└─ "What does term X compose from / belong to / route to" → ontology_term_details links_out (forward-only; reverse via run_cypher)
```
