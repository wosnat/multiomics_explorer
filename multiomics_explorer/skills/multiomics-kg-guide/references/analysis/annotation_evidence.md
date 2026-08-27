# Annotation trust — reading "why do we believe this"

LLM-facing guide to the trust surface that sits on every gene→ontology-term
annotation across all 17 supported ontologies. Every `Gene_has_*` /
`Gene_involved_in_*` / `Gene_catalyzes_*` edge carries some subset of the
facts below; this page tells you which ontology carries which fact, where it
lives (compact row / verbose row / filter param), and how to use it without
misreading a categorical for a curation grade.

Runnable companion: `docs://examples/annotation_evidence.py` (4 recipes).

> **Counts in this doc are an illustrative snapshot** and drift with each KG
> rebuild. Use them for rough scale only; call `list_filter_values`,
> `ontology_landscape`, or `kg_release_info` for current figures.

---

## Three layers, one home each

Every gene→term edge fact belongs to exactly one of three layers. Where a
fact lives (compact column, verbose column, filter param) follows from which
layer it's in — this is the single decision that resolves almost every
question about the trust surface.

| Layer | What it is | Where it lives |
|---|---|---|
| **Comparable trust axes** | Facts with the *same meaning* wherever they occur: `sources[]` (which pipeline made the call), `evidence` (a five-rung ladder: `curated > signature > homology > family_inferred > domain_inferred`), `evidence_score` (a `[0, 1]` composite, TCDB/MEROPS only), `tier` (1–3, diamond-truncation depth, TCDB/MEROPS only) | `evidence` is compact on every row of the 14 functional-edge ontologies (null on PSORTb/SignalP, which carry no trust axes at all). `sources`, `evidence_score`, `tier` are verbose. All four are filterable (`sources=`, `evidence=`, `max_tier=`, `min_evidence_score=`), defaulting to `None` — a call with no trust filters returns exactly what it always did. |
| **Native trust detail** | Ontology-specific scalars that must **never** be compared across ontologies because their scale and direction differ (e-value lower-is-better, bit score / confidence / probability higher-is-better): TCDB's `confidence_score`, `source_agreement`, `pfam_support`, `go_support`, `identity`, `qcov`, `evalue`, `consensus_n`, `attachment_depth`; MEROPS's `confidence_score`, `pfam_support`, `best_hit_kind`, `identity`, `qcov`, `evalue`, `consensus_n`, `best_hit_id`; InterPro's `libraries`, `evalue_library`, `evalue`, `match_count`, `start`, `end`; NCBIfam's `evalue`, `bit_score`, `start`, `end`; PSORTb's `localization_score`; SignalP's `signal_peptide_probability` / `signal_peptide_cleavage_site` / `signal_peptide_cleavage_probability` | Verbose-only, under their own native names. **Never a filter** — there is no cutoff anywhere on a native scalar (InterPro's e-value included; no ontology's native detail is calibrated enough to threshold safely). |
| **Materially-important facts** | Categoricals whose *absence changes the biological reading*, not just its confidence: MEROPS `call_class` (`peptidase` / `inhibitor` / `nonpeptidase_homolog` — a real peptidase call, a peptidase-inhibitor family, or a catalytically-dead homolog that still resembles a peptidase family by sequence) | Compact **always** (not verbose-gated, unlike the comparable axes), filterable (`call_class=`), rolled up (`by_call_class`), and auto-warned on when `nonpeptidase_homolog` rows are silently included in a census. InterPro's `interpro_type` (the 8-way FAMILY/DOMAIN/... split) gets the same "compact always" treatment, though it is a term-character fact rather than an edge fact. |

Why one compact column and not four: rollups already carry the distribution
(`by_evidence`, `by_tier`, `by_sources`), so the per-row payload only needs
the one axis an agent can read on **every** functional-edge row —
`evidence`. `evidence_score` is null on most of the 14 (only TCDB, MEROPS,
GO×3, EC, Pfam, CAZy carry it), so it moved to verbose and kept its role as
the within-ontology sort key and the *only* numeric cutoff in the whole
surface (`min_evidence_score`).

---

## Per-ontology trust profile

| Ontology | Trust axes | `rank_prop` | Materially-important (compact) | Native detail (verbose) | Term facet |
|---|---|---|---|---|---|
| `go_bp`, `go_mf`, `go_cc` | sources, evidence, evidence_score | — | — | — | — |
| `ec` | sources, evidence, evidence_score | — | — | — | — |
| `kegg` | sources, evidence | — | — | — | — |
| `cog_category` | sources, evidence | — | — | — | — |
| `tigr_role` | sources, evidence | — | — | — | — |
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

## Rank vs. filter — the one rule that matters most

Every numeric trust field in this surface falls into exactly one of two
buckets, and mixing them up is the most common mistake:

- **Rank by it.** `evidence_score` (row) and the gene-level rollups
  `tcdb_evidence_score_max` / `merops_evidence_score_max` (on `gene_overview`)
  are meant to be sorted on, not thresholded — except through the one
  sanctioned cutoff below. `0` is a real, uncorroborated hit, not an absence
  signal; absence is `null` (no call at all on that gene/edge). This mirrors
  the transport trust ladder in `docs://guide/conventions` — the phrase "rank
  by it, never filter by it" describes the *gene-level max* rollups
  specifically.
- **Filter by it — but only through `min_evidence_score`.** The edge-level
  `evidence_score` *does* have exactly one sanctioned cutoff:
  `min_evidence_score=` on `genes_by_ontology`, `gene_ontology_terms`,
  `pathway_enrichment`, `cluster_enrichment`. On `genes_by_ontology` and
  `gene_ontology_terms`, setting it adds `evidence_score_signals` to the
  envelope — the `ControlledVocabulary`-backed list of composite inputs that
  feed the score for that edge type (e.g. TCDB: `source_agreement`,
  `pfam_support`, `go_support`, `identity`, `qcov`), so you can see what the
  number is actually made of before trusting a threshold. `pathway_enrichment`
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
~74 testable terms, DOMAIN ~47, FAMILY ~7, the remaining five ≤4 each).
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
EC/CAZy family"), and KEGG terms to BRITE categories. Each bridge carries a
`link_kind` — `composition` (this family is built from these Pfam domains /
GO functions), `membership` (this family is one of that ontology's known
members), or `router` (a computed cross-reference, ambiguous when a source
term maps to multiple targets or isn't a `FAMILY`-type InterPro entry).

Bridges are modeled **forward only** by design — family → what characterizes
it, never the reverse (`links_in` does not exist). A term-side drill-down
tool that walks these bridges directly (batch term IDs → parents / children /
bridge targets in one call) is not part of this tool surface; reach bridge
edges via `run_cypher` when you need them (e.g.
`MATCH (t:TcdbFamily {id: $id})-[:Tcdb_family_has_pfam_domain]->(p:Pfam) RETURN p`).
`list_filter_values(filter_type="link_kinds")` enumerates the kind vocabulary
and which bridge relationships carry each kind.

---

## Recipe 1 — MEROPS peptidase-only clan census

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

## Recipe 2 — TCDB leaf mode: most-specific vs superseded

**When:** "what's this gene's actual TCDB call, not every ancestor it also
technically belongs to?"

```python
leaf_only = gene_ontology_terms(
    locus_tags=["PMM0392"], organism="MED4",
    ontology=["tcdb"], mode="leaf",
)
# Default: attachment_depth='most_specific' only. Genome-wide MED4: 670 raw
# tcdb edges collapse to 597 rows under this predicate.

with_superseded = gene_ontology_terms(
    locus_tags=["PMM0392"], organism="MED4",
    ontology=["tcdb"], mode="leaf", include_superseded=True,
)
# Adds back the 73 (genome-wide) rows most_specific drops, each labelled
# attachment_depth='superseded' — less specific, not wrong. PMM0392's
# superseded row is the tcdb:3.A.1 ABC-superfamily ancestor of its actual
# (deeper) subfamily attachment.
```

`include_superseded` is a leaf-mode-only switch; it has no effect outside
`mode="leaf"`.

---

## Recipe 3 — InterPro-scoped enrichment

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

## Recipe 4 — Trust-filtered TCDB gene set before enrichment

**When:** "restrict a TCDB-based gene set to homology calls with a
corroborated score before testing it" — tightening a noisy hierarchical
ontology the same way `substrate_depth=['most_specific']` tightens transport
chemistry rows (see `docs://guide/conventions`).

```python
# Discover the axis set first (skip if already known).
axes = list_filter_values(filter_type="trust_axes", ontology="tcdb")
# ['sources', 'evidence', 'evidence_score', 'tier']

filtered = genes_by_ontology(
    ontology="tcdb", organism="MED4", level=2,
    evidence=["homology"], min_evidence_score=0.6,
)
# MED4 tcdb, genome-wide: 670 raw gene x term edges narrow to 98 under
# evidence=['homology'] AND evidence_score>=0.6. Read
# filtered["evidence_score_signals"] to see which composite inputs back
# the 0.6 threshold for this edge type.

enrichment = pathway_enrichment(
    organism="MED4", experiment_ids=[...],
    ontology="tcdb", level=2,
    evidence=["homology"], min_evidence_score=0.6,
)
# The same filters shape the enrichment TERM2GENE mapping AND the
# background identically (both traverse the same gene->leaf match stage),
# so foreground and background stay apples-to-apples —
# envelope["background_filtered"] confirms this.
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
└─ "What does term X compose from / belong to / route to" → bridges_out (forward-only; reach via run_cypher)
```
