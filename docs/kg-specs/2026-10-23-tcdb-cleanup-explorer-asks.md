# TCDB cleanup is coming (2026-10-23)

**Date:** 2026-10-23 · **From:** KG (`multiomics_biocypher_kg`) · **To:** explorer (`multiomics_explorer`)
**Direction:** KG → explorer.
**KG design:** `multiomics_biocypher_kg/docs/superpowers/specs/2026-10-22-tcdb-cleanup-design.md`
(approved KG-side; implementation plan not written yet).
**Follows:** `2026-10-18-go-transport-substrates-explorer-asks.md`, project #3 ("TCDB nodes/edges
redesign"). That doc said #3 would be breaking for you. This is it.

This is a heads-up, not a list of tasks. We'd like your feedback before the KG writes the
implementation plan. Please answer in a "Responses" section at the end.

## Why

The TCDB slice has piled up rolled-up substrates and workaround properties. Consumers have to be
taught each one before the obvious query gives a correct answer:
- A gene placed only in the ABC superfamily inherits about 550 substrates.
- One gene carries 2–9 overlapping TCDB edges at different depths, and some of them are marked
  "superseded".
- Two analyses that tried to build transport systems from the KG spent most of their effort working
  around this: `multiomics_analysis/.../2026-10-06-pro_n_import_coculture` and
  `2026-07-06-alteromonas_coculture_carbon_sources`.

The diamond best hit (#2) names the specific characterised system a protein resembles. That makes a
cleaner model possible.

Project #3 is now split into three parts:
- **3a, TCDB cleanup.** This doc. Makes the TCDB slice faithful to TCDB and readable. No
  cross-source scoring.
- **3b, gene transport layer.** Its design comes next. A per-gene answer: is this a transporter, what
  kind, how sure. Built from TCDB plus KEGG BRITE, GO, Pfam/InterPro and Cyanorak roles.
- **Transport systems.** After 3b. Groups genes into systems and assigns each system's substrates.

## What changes in 3a

### TCDB nodes (`TcdbFamily`)
- **Five levels**, with `level_kind` `tc_class · tc_subclass · tc_family · tc_subfamily · tc_system`.
  `tc_system` replaces `tc_specificity`.
- **System nodes carry TCDB's own description text.**
- **New `direction`:** `uptake · export · unknown`, plus a sparse `direction_basis`
  (`abc_numbering · tcdb_name`). It is set only where TCDB itself states it: ABC subfamilies
  `3.A.1.1–99` are uptake and `3.A.1.100+` are export, or the TCDB name says uptake/efflux.
- **New `tcdb_substrate_count`** on family and subfamily nodes: the distinct substrates across all
  TCDB systems below the node.
- **About 10K TCDB nodes, up from 1.5K.** Two additions:
  - Best-hit systems become nodes, about 2K.
  - Every TCDB system with curated substrates under a kept family is kept, gene or no gene, about
    6.8K. Walking a family therefore returns TCDB's full substrate range.

  **Most of the new nodes have `gene_count = 0`.**

### Substrates
`Tcdb_family_transports_metabolite` and `…_chemical_role` leave **`tc_system` nodes only**, exactly as
TCDB curates them. Families no longer carry their own substrate edges. "What does family X
transport?" is a walk down to its systems.

### Gene → TCDB edges (`Gene_has_tcdb_family`)
One edge **per source**. Today eggNOG and diamond are merged onto one edge. The new property is
`call_kind`:

| `call_kind` | `sources` | Target | Properties |
|---|---|---|---|
| `eggnog` | `['eggnog']` | the TC id(s) eggNOG names | — |
| `diamond_tier` | `['tcdb_diamond']` | the tier-truncated call (tier 1 = system, 2 = subfamily, 3 = family) | `tier`, `identity`, `qcov`, `evalue` |
| `diamond_best_hit` | `['tcdb_diamond']` | each best-hit system (top + near-ties) | `identity`, `rank` (1 = top) |

- **Edge ids include the call kind.** The same gene and system can carry up to three edges, and that
  overlap is how agreement shows up.
- **Tier-3 calls stay as edges.**
- **`evidence`:** eggNOG `family_inferred`; both diamond kinds `homology`.

### Removed
- **From the substrate edges:** `substrate_depth`.
- **From `TcdbFamily`:** `substrate_breadth` (this retires the R3 exception) and `metabolite_count`.
- **From `Gene_has_tcdb_family`:**
  - `attachment_depth`
  - `evidence_score`, `source_agreement`, `pfam_support`, `go_support`
  - `confidence_score`, `consensus_n`
  - the six `best_hit_*` properties (now `diamond_best_hit` edges plus the system's own substrate
    edges)
- **From `Gene`:** `tcdb_evidence_score_max` and `transport_substrate_resolution`.
- **From the vocabulary:** their `ControlledVocabulary` entries. `controlled_vocabularies_hash` moves.

### Redefined: the transport arm of the metabolite rollups
The following are redefined on one rule: a gene reaches the substrates of systems it points at
**directly**. That means its rank-1 best hit, an eggNOG 5-part id, or a tier-1 diamond call. There is
no walk up or down the hierarchy.
- `Gene.transported_metabolite_count`
- `Metabolite.transporter_gene_count` / `transporter_count`
- `OrganismTaxon.transported_metabolite_count`
- the transport arm of `Organism_has_metabolite` and `Metabolite.organism_names` / `organism_count`
- `ChemicalRole.transporter_count` / `tcdb_family_count`

Measured on the current data, about 30.7K genes have TCDB evidence:

| Genes | Count | Transporter-like product name |
|---|---|---|
| Keep a transport arm | 13,228 | 51% |
| Lose it: tier-3 family match only | 12,579 | 8% |
| Lose it: tier-2 subfamily match only | 1,944 | 3% |
| Lose it: eggNOG names a family/subfamily only | 2,974 | 46% |

Most of the drop is non-transporters that today inherit a whole family's list. About 2,400 real
transporters read 0 in these counts until the systems project; MED4 `phnD` is one. They keep their
edges, and their family's compounds remain reachable by walking the hierarchy.

### Unchanged
- The annotation surface. `'tcdb'` in `annotation_types`, the `transporter` bucket of
  `annotation_quality`, and `has_any_edge` keep their gate: an eggNOG edge, or a diamond edge with
  `tier <= 2`.
- The KEGG compound and pathway sets.
- The TCDB → Pfam / GO bridges. They are now emitted on all kept nodes, including systems with no
  genes, as clues for system calling later.
- The GO transport route (slice 1).

### Not in 3a
No per-gene transporter call, confidence, subunit role or direction per gene, and no per-gene compound
edges. Those are 3b and the systems project.

## What we'd like from you

Any feedback on the model before it is planned. In particular, tell us if anything above would leave
a question your tools answer today with no way to answer it after the change. It also helps to know
early about anything you'd want named or shaped differently while it is still cheap to change.

## Responses

### Explorer response (2026-10-23)

Overall: we agree with the direction. Substrates only on `tc_system`, one edge per source, and dropping
the depth and score workarounds all make the explorer simpler. Most of our TCDB code exists to work
around the current model: the deepest-attachment predicate, `include_superseded`, `substrate_depth`
sorting and filtering, and the `substrate_breadth` few-shot. We accept the break.

Below, **Q** = we need an answer before you plan, **Ask** = we'd like a change, **Note** = we'll
handle it on our side.

#### R1 (Q, blocking): what gates `diamond_best_hit` emission, and does a weak hit count as direct?
Live KG today (min `tier` per gene × has `best_hit_*` × has eggNOG):

| min tier | best hit | eggNOG | genes |
|---|---|---|---|
| 3 | yes | no | 3,223 |
| 3 | yes | yes | 5,172 |
| 3 | no | no | 12,579 ← your "tier-3 only" row |
| 1 | no | either | 38 |

So best-hit data exists for many genes whose tier call is only family-level (tier 3). Under the
"directly" rule, a rank-1 best hit at tier-3 identity reaches the **system's** specific substrates,
which is more specific than the tier truncation itself allows. Please confirm:
1. What thresholds gate a best-hit edge? Is it the same identity/qcov bar as tier 1, or looser?
2. Is it intended that a tier-3-quality rank-1 best hit feeds `transported_metabolite_count` and the
   other rollups? If so, the rollups count system substrates for hits you won't call above family
   level. We'd rather the rollup rule be "rank-1 best hit **with tier ≤ 1**" (or whatever bar tier 1
   uses), or that best-hit edges carry `tier` too so consumers can gate them the same way.
3. Why do 38 genes have a tier-1 call but no best hit?

#### R2 (Ask): stamp the "direct" rule on the edge
The rollup rule is a three-branch predicate: `diamond_best_hit` with `rank = 1`, OR `eggnog` onto a
`tc_system`, OR `diamond_tier` with `tier = 1`. Every explorer transport query (genes_by_metabolite,
metabolites_by_gene, envelopes, `has_chemistry`, gene_overview `evidence_sources`) would have to
re-implement it, and stay matched to your precomputed counts. We already maintain one predicate like
this, `TCDB_DEEPEST_ATTACHMENT_PREDICATE`, and it is exactly what drifts. Please put a boolean on
`Gene_has_tcdb_family`, e.g. `reaches_substrates: true` (sparse or dense, your call), set on exactly
the edges the rollups use. Then rows and counts come from one set by construction.

#### R3 (Q): `has_any_edge` / `annotation_types` vs the transport arm
The annotation gate is "an eggNOG edge, or a diamond edge with `tier <= 2`", but per R1 a rank-1 best
hit can sit on a tier-3 gene. Such a gene would get `transported_metabolite_count > 0` while `'tcdb'`
is **not** in its `annotation_types`. Please confirm whether that combination can occur. If it can,
resolving R1 (2) probably fixes this too. Either way, the two gates should nest: transport arm ⊆
annotated.

#### R4 (Ask): a TCDB filter axis for `call_kind`, and a replacement `rank_prop`
- `evidence` can't distinguish `diamond_tier` from `diamond_best_hit` (both `homology`), so
  `call_kind` becomes the filter users need. Please add it to `ControlledVocabulary` and to the TCDB
  `trust_axes`. We'll expose it as a filter like MEROPS `call_class`.
- Naming: `call_kind` sits next to MEROPS `call_class` in the same filter surface, and the two mean
  different things. If you're open to it, a TCDB-specific name avoids users trying one where the
  other belongs. Suggestions: `tcdb_call`, `call_source`. Not blocking.
- We use `evidence_score` today as TCDB's `rank_prop`: it picks the representative edge when a gene ×
  term has several. With up to three edges per gene × system and no score, we need an ordering.
  Unless you object, we'll use `call_kind` precedence (`diamond_best_hit` rank 1 > `diamond_tier` >
  `eggnog`), then `identity`. If you'd rather define a canonical order KG-side, tell us.
- `min_evidence_score` becomes unsupported for TCDB. Our filter layer already raises "unsupported
  axis" per ontology, so this is a clean break, not silent emptiness. `max_tier` keeps null-tier
  edges (`tier <= $max_tier OR tier IS NULL`), so after the change `max_tier=1` would still return
  eggNOG and best-hit edges. That's acceptable if documented.
- Best-hit near-ties: is `rank` unique per gene (tie-broken deterministically), or can two edges
  share a rank? We need to know whether "rank = 1" can mean more than one system.

#### R5 (Q): which nodes carry `direction` and `tcdb_substrate_count`, and is `direction` dense?
- `direction`: is it on every node (`unknown` as the default) or sparse? Does an ABC subfamily's
  direction propagate down to its `tc_system` children? Users will ask "uptake systems for X" at the
  system level, where substrates now live. If systems don't inherit, we'd have to walk up for every
  row. Please state its placement in the vocabulary entry. We'd prefer it on all levels below the
  node where it's set.
- `tcdb_substrate_count` only on family and subfamily: please consider all five levels. On a system
  it's just its own count, and on class/subclass it's the same walk. One property on every node
  saves us a level switch in `search_ontology` / `ontology_term_details`. It also replaces the
  `metabolite_count` we read there today.

#### R6 (Q): `is_informative` and the ~8.5K zero-gene nodes
- Please set `is_informative` on the new system nodes (we default enrichment and landscape to
  `informative_only=True`).
- Is `tcdbFamilyFullText` going to index all ~10K nodes? Lucene `search_ontology('phosphate')` would
  then mostly return `gene_count = 0` systems. That's fine and useful ("what does TCDB know"), but we
  will default the organism-anchored tools to `gene_count > 0` and say so. No change asked, just
  confirm the index scope.
- `ontology_landscape` term-size stats: we expect the zero-gene nodes to drop out of the size
  filters, but haven't verified it yet. We'll check after the rebuild.

#### R7 (Note, the one capability gap): "what might this family-only gene transport?"
Today metabolites_by_gene answers this for MED4 `phnD` and the other ~2,400 real transporters
through `substrate_depth = 'inherited'` rows, flagged by `transport_substrate_resolution =
'family_inferred'` plus a warning. After 3a those genes return zero chemistry rows. The answer still
exists in the graph (gene → family → descendant systems → substrates), but no tool would walk it.
We'll add an opt-in walk on our side, something like `include_family_range=True` on
metabolites_by_gene / genes_by_metabolite, with rows tagged by the system they came through and the
family's `tcdb_substrate_count` shown up front, so the ABC-superfamily case stays visible and opt-in.
No KG change needed, except that per R5 `tcdb_substrate_count` should be on the family-level nodes
these genes attach to. If 3b will give a per-gene answer that replaces this, tell us and we'll keep
ours minimal.

#### R8 (Note): what we'll remove or rename explorer-side
- `substrate_depth` filter / row field / `rows_by_substrate_depth` (genes_by_metabolite,
  metabolites_by_gene); depth-tier sort order.
- `include_superseded` and leaf-mode deepest-attachment logic for TCDB in gene_ontology_terms. With
  one edge per source, leaf mode becomes "all edges, grouped by `call_kind`".
- gene_overview `tcdb_evidence_score_max` and `transport_substrate_resolution`; per-row
  `tcdb_evidence_score`. Until 3b, gene_overview will show the best rank-1 `identity` per gene, computed
  live, as the "how sure" hint. If you'd rather precompute that on `Gene`, it's cheap for us to read.
- TCDB verbose edge columns: `confidence_score`, `source_agreement`, `pfam_support`, `go_support`,
  `consensus_n`, `attachment_depth` out; `call_kind`, `rank` in.
- `tc_specificity` → `tc_system` in docs, the TCDB ontology YAML and examples; `substrate_breadth`
  few-shot in `queries.py` removed.
- TERM2GENE (genes_by_ontology, enrichment): multiple edges per gene × system become duplicates, so
  we'll dedupe on (gene, term). Also, near-tie best hits (rank ≥ 2) will place a gene in several
  systems' gene sets. Q: should enrichment TERM2GENE include rank ≥ 2 best hits? Our default would
  be rank-1 only for the best-hit kind, mirroring R2.

#### R9 (Q): `Gene.tcdb_family_count`
It isn't in the removed list, but it's defined today over `attachment_depth = 'most_specific'` edges.
What does it count after 3a: distinct TC nodes across all call kinds? It drives `has_tcdb` in the
gene_overview envelope.

#### Timing
We'd absorb this as one break with the vocabulary hash move: tools change, docs regenerate, goldens
regenerate. We'd like the R1/R2/R5 answers in the implementation plan so we can write our side in
parallel.

### KG reply (2026-10-23)

Thanks. Your R1 and R3 changed the design: best-hit edges now carry their own diamond statistics and
a `tier`. Answers are in order below. The KG design is updated to match
(`2026-10-22-tcdb-cleanup-design.md` §5.1, §5.3, §7, §9).

**R1 — best-hit gating.**
1. **What gates a best hit.** `best_hit_v1` requires qcov ≥ 75 and scov ≥ 75, TC class 1–4, and a
   reciprocal best hit. There is no identity floor. That rule is unchanged.
2. **What counts as "direct".** We agree a weak best hit should not reach system substrates.
   - **What a best-hit edge now carries:** each system's own `identity`, `qcov`, `scov`, `evalue`,
     `bitscore`, `bitscore_ratio` (to the top hit) and `rank`. It also carries **`tier` as an
     identity band**, using the tier-call cutoffs: 1 = ≥ 70%, 2 = 40–70%, 3 = < 40%. There is no
     consensus step, unlike tier calls, and the vocabulary entry says so. So `tier <= 2` works as
     one gate across both diamond kinds.
   - **"Direct" now means:** a best hit with `rank = 1` and `tier <= 2`, or an `eggnog` edge to a
     system, or a `diamond_tier` edge with `tier = 1`.
   - **Why tier calls can't stand in for this gate:** among genes whose tier call is only tier 3,
     619 have a best hit ≥ 70% and 2,545 a best hit at 40–70%. Tier calls come from a consensus
     collapse, not from identity alone.
   - **New expectation:** about **8.3K genes** keep a transport arm. It was ~13.2K in the first
     draft and is ~30K today.
3. **The 38 tier-1 genes with no best hit.** 32 are TC class 5/8/9, which best hits exclude by rule.
   3 fail scov ≥ 75 and 3 fail the reciprocal check. We are keeping best hits to classes 1–4.

**R2 — accepted, as a string.** Every `Gene_has_tcdb_family` edge carries
`substrate_reach ∈ {direct, not_direct}` (dense on this edge type). It is a string because R5 rules
out native bools. `direct` is set on exactly the edges the transport-arm rollups use.

**R3 — the gates now nest.** The annotation gate (`'tcdb'` in `annotation_types`, the `transporter`
bucket) gains the same arm: an `eggnog` edge, a `diamond_tier` edge with `tier <= 2`, or a
`diamond_best_hit` edge with `rank = 1` and `tier <= 2`.
- Measured: 1,055 genes gain `'tcdb'` (14,745 → 15,800).
- 0 genes would have a transport arm without the annotation. The KG test suite will check this.
- The annotation-state distribution moves only by those genes.

**R4 — mostly accepted.**
- **Renamed `call_kind` → `tcdb_call`.** Values are `eggnog`, `diamond_tier` and `diamond_best_hit`.
  It is registered in `ControlledVocabulary`. The trust-axis wiring is yours.
- **Ordering:** your precedence (best hit rank 1 > `diamond_tier` > `eggnog`, then `identity`) is
  fine. We won't define a canonical order KG-side.
- **`max_tier`:** this now covers best-hit edges too. Only `eggnog` edges have a null `tier`.
- **`rank`** is unique per gene and deterministic (bitscore desc, then TCID, then subject).
  `rank = 1` names exactly one system.

**R5 — accepted.**
- `direction` is dense on every level (`unknown` by default) and inherited downward from the node
  where the rule fires, so systems carry it. The ABC numbering rule sets it on a subfamily and
  everything below it.
- `tcdb_substrate_count` is on all five levels. On a system it is that system's own count, with 0
  when it has none.

**R6.**
- TCDB nodes carry no `is_uninformative` marker. The marker means "vague term", and the gene-less
  systems are not vague, so we won't set it. `gene_count > 0` is the right filter.
- `tcdbFamilyFullText` indexes all kept nodes (~10K). Your default to `gene_count > 0` on the
  organism-anchored tools sounds right.

**R7.** 3b will **not** give a per-gene substrate answer. 3b is the transporter call itself (role,
subunit type, purpose, direction, confidence). Substrates per gene come from the systems project. So
your opt-in family walk is the right interim; keep it as simple as you like.

**R8.**
- **Enrichment gene sets:** agreed, use rank-1 best hits only for the best-hit kind. For a uniform
  rule, use `tier <= 2` on rank-1 edges too. That matches `substrate_reach`.
- **The live "best rank-1 identity" in `gene_overview`:** fine for now. We won't precompute it on
  `Gene` in 3a, because 3b brings a per-gene confidence that should replace it.

**R9 — `Gene.tcdb_family_count`.** It stays. After 3a it counts distinct TC nodes over the gene's
gate-passing edges (the three arms in R3), deepest per lineage. Near-tie best hits never count as a
second family.

**Timing.** These answers go into the implementation plan as written, so you can work in parallel.
The other change since the first draft: `diamond_tier` edges also gain `scov`.

### Explorer follow-up (2026-10-23)

Thanks, all accepted. The best-hit `tier` band and `substrate_reach` solve R1–R3 cleanly. Two small
asks and three notes left. Nothing here blocks the plan.

**F1 (Ask): stamp the annotation gate too.** After R3 the gate is its own three-branch predicate:
`eggnog`, OR `diamond_tier` with `tier <= 2`, OR `diamond_best_hit` with `rank = 1` and `tier <= 2`.
Three explorer surfaces would re-derive it: `annotation_types` parity checks, TCDB TERM2GENE for
enrichment (R8), and row parity with `Gene.tcdb_family_count` (R9). That's the R2 argument again.
Either option works for us:
- a second dense string, e.g. `annotation_gate ∈ {pass, fail}`; or
- widen `substrate_reach` to `{direct, annotated, below_gate}`. The nesting (direct ⊆ annotated) you
  now guarantee makes this one ordered value.

Your call on the shape.

**F2 (Ask): define "deepest per lineage" precisely** (R9), or mark the counted edges (could fold into
F1). We'll test that the explorer's `gene_ontology_terms` leaf-mode rows reconcile with
`tcdb_family_count`. The case we can't infer: a `diamond_tier` subfamily edge and a rank-1 best-hit
system below it. Is that one family or two? And what if an eggNOG edge sits on a different branch?

**N1: correction to our R6.** The explorer reads the sparse `is_uninformative` marker, and a missing
marker means informative. So "no marker on the new nodes" is exactly right. Our ask was misworded.

**N2: `tier` now has two meanings on one property:** a consensus tier on `diamond_tier` edges and an
identity band on `diamond_best_hit` edges. That's fine for `max_tier` gating. We'll say so in the TCDB
ontology doc and in the trust-filter text so nobody compares tiers across `tcdb_call` kinds.

**N3: scale.** The transport arm goes from ~30K genes to ~8.3K, and gene-level counts in
`list_metabolites`, `list_organisms` and `gene_overview` move a lot. We'll call this out as a breaking
change in our CHANGELOG. Our R7 opt-in family walk will start only from gate-passing edges, so a
weak tier-3 family edge can't bring back the ~550-substrate ABC case.

### KG answer to the follow-up (2026-10-23)

**F1 — accepted, as one ordered property.** `substrate_reach` is replaced by **`tcdb_gate`**, dense on
every `Gene_has_tcdb_family` edge:

| `tcdb_gate` | Edges |
|---|---|
| `direct` | `diamond_best_hit` with `rank = 1` and `tier <= 2`; `eggnog` onto a `tc_system`; `diamond_tier` with `tier = 1` |
| `annotated` | the remaining annotation-gate edges: other `eggnog` edges, and `diamond_tier` with `tier = 2` |
| `below_gate` | everything else: tier-3 calls, near-tie best hits, rank-1 best hits with `tier = 3` |

- **What reads each value.** The transport-arm rollups read `direct`. The `'tcdb'` annotation gate,
  `tcdb_family_count` and TERM2GENE read `direct` + `annotated`.
- **The nesting holds per edge:** every direct arm is also an annotation arm. So
  `tcdb_gate IN ['direct','annotated']` is the annotation gate exactly.

**F2 — the definition.** `Gene.tcdb_family_count`:
1. Take the TC nodes targeted by the gene's edges with `tcdb_gate IN ['direct','annotated']`.
2. Drop any node that is an ancestor of another node in that set, whatever the call kind.
3. Count the distinct nodes that remain.

Your cases:
- A `diamond_tier` edge on subfamily `3.A.1.4` plus a rank-1 best hit on `3.A.1.4.4` gives **1**.
- Add an eggNOG edge on the sibling system `3.A.1.4.5` and it gives **2**.
- An eggNOG edge and a best hit on the same system give **1**.
- An eggNOG edge on a different branch counts separately.

We won't mark the counted edges. That would bring back `attachment_depth`, and the rule above is a
single ancestor check over the gate-passing edges.

**N1–N3:** noted. On N2, we'll word the `tier` vocabulary entry the same way: two derivations, one
gate, and no comparing tiers across `tcdb_call` kinds.

### Explorer close-out (2026-10-23)

Accepted as written; no further asks. We're closing this thread.

`tcdb_gate` covers all three of our surfaces with a plain `IN` filter. The F2 rule maps straight
onto our leaf mode: our existing deepest-attachment predicate, restricted to `tcdb_gate IN
['direct','annotated']` on both sides. So leaf-mode rows reconcile with `tcdb_family_count` by
construction, and we'll pin your four example cases as tests.

Two consequences we'll document on our side:
- Near-tie best hits are `below_gate`, so default and gated views never show them. They stay
  reachable through `tcdb_call` / `rank` filters.
- A gene whose only call is a tier-3 family edge is `below_gate` everywhere. Our R7 family walk
  will not start from it (per N3).

Please ping us when the plan lands. We'll draft the explorer-side spec against it.

### KG corrections after design review (2026-10-23)

A review of the design against the code found errors in what we told you. Corrected here; the design
doc has the details.

- **Node count: ~8.8K TCDB nodes, not ~10K.** The range-only systems number 5,249. The earlier
  ~6.8K double-counted systems that best-hit seeding already adds.
- **The KEGG compound set does change slightly.** Today the class-level roll-up reaches systems in
  families none of our genes touch. With substrates only on kept systems, that route goes. Effects:
  - **65 Metabolite nodes disappear.** They were transport-only and off-target for marine bacteria:
    prostaglandins, statins, ouabain, vitamin D3, phosphoinositides, retinal, propidium iodide and
    the like.
  - 8 ChemicalRoles lose their transport route.
  - 32 metabolites lose `'transport'` from `evidence_sources`. They keep their other arms.
  - 3 gene-less pathways go: Phagosome, Focal adhesion, and chondroitin sulfate GAG biosynthesis.
- **`'transport' IN Metabolite.evidence_sources` means "TCDB lists it as a substrate of a system in
  the KG"**, not "a gene here reaches it". A metabolite can carry the tag with
  `transporter_gene_count = 0`.
- **`TcdbFamily.gene_count` / `direct_gene_count` / `organism_count`** count gate-passing edges only
  (`tcdb_gate IN ['direct','annotated']`), the same set as your TERM2GENE. A system reached only
  through near-tie or tier-3 calls reads `gene_count = 0`.
- **System-side counts, exactly:**
  - `Metabolite.transporter_count`: distinct systems that carry the metabolite and are the target of
    at least one `direct` edge. Range-only systems never count.
  - `ChemicalRole.transporter_count` / `direct_transporter_count`: the same rule.
  - `ChemicalRole.tcdb_family_count` / `direct_tcdb_family_count`: the TCDB-side count, i.e.
    distinct kept systems curated with the role, range-only included.
- **`tcdb_gate` is computed after the eggNOG alias remap.** An eggNOG system id re-anchored to an
  ancestor is `annotated`, not `direct`.

### Explorer response to the corrections (2026-10-23)

Thanks for catching these before planning. All accepted. One small ask, and what each correction
means on our side.

**C1 (Ask): please list the 65 removed Metabolite ids** in the design doc or the release notes.
Our tests and examples already pin at least one of them: `kegg.compound:C01443` (ouabain) is our
exemplar for multi-class `kegg_brite_classes` in the integration suite. We'll pick a new exemplar,
but we want to sweep fixtures, goldens and YAML examples for the other 64 in one pass instead of
finding them as failures. The 3 pathway ids and 8 ChemicalRole ids would help too.

**C2 (Note): `'transport'` in `Metabolite.evidence_sources` no longer implies a gene.** Today our
docs treat that tag as a routing hint toward `genes_by_metabolite`. After 3a we'll route on
`transporter_gene_count > 0` instead and describe the tag as "TCDB lists it". No KG change asked.

**C3 (Note): the gate becomes the default on our TCDB gene-anchored tools.** `TcdbFamily.gene_count`
now counts gate-passing edges only. So an ungated `genes_by_ontology(ontology='tcdb')` would return
more genes than the term's `gene_count`, and through near-ties also genes in terms that read
`gene_count = 0`. To keep rows and counts in step, we'll default `genes_by_ontology`,
`gene_ontology_terms` and enrichment to `tcdb_gate IN ['direct','annotated']` for TCDB. We'll add an
explicit opt-in for `below_gate` edges, which replaces `include_superseded` in that role. This
supersedes our R8 note, which applied the gate to enrichment only.

**C4 (Note, naming):** `ChemicalRole.tcdb_family_count` now counts kept **systems**, range-only
included. `transporter_count` counts gene-reached systems. We'll document the two as "TCDB-side
range" vs "reached by genes in the KG". If you're renaming anyway, `tcdb_system_count` would read
truer than `tcdb_family_count`. Not blocking.

**C5 (Note):** we hold no counts or examples for the alias-remapped eggNOG edges or the node total,
so those corrections need nothing from us.

### KG answer to the corrections response (2026-10-23)

**C1 — done.** The predicted ids are in
`multiomics_biocypher_kg/docs/kg-changes/tcdb-cleanup/removed_ids.tsv`, with columns `change`, `id`,
`name`:
- 65 `metabolite_removed`;
- 32 `metabolite_loses_transport_tag`, which stay as nodes;
- 8 `chemical_role_loses_transport_route`;
- 3 `pathway_removed`: `kegg.pathway:ko04145` Phagosome, `ko04510` Focal adhesion, and `ko00532`
  chondroitin sulfate / dermatan sulfate biosynthesis.

`kegg.compound:C01443` (ouabain) is in the removed list.
- **How the list was made.** It is predicted from the 2026-10-19 build.
- **How it will be checked.** The implementation checks the rebuilt graph's diff against this file.
  We will confirm or correct it in the "KG built" note.

**C3 — fine by us.** The gate is a good default; the `below_gate` opt-in is your call.

**C4 — accepted.** `ChemicalRole.tcdb_family_count` / `direct_tcdb_family_count` become
**`tcdb_system_count` / `direct_tcdb_system_count`**. `transporter_count` /
`direct_transporter_count` keep their names and mean gene-reached systems.

**C2, C5 — noted.**

### KG built (2026-10-23)

3a is implemented and the graph is rebuilt. Branch `feat/tcdb-cleanup` of `multiomics_biocypher_kg`:
code and tests at `a46f83b5..f46c084e`, docs in the commit after. The kg suite passes (1,346 / 0
failed). Release notes: `docs/kg-changes/tcdb-cleanup.md`. Everything below is measured on the live
graph.

**Shipped as agreed.** One change of name: the draft name `call_kind` shipped as **`tcdb_call`**,
as R4 suggested. Everything else matches this dialog:
- `tcdb_gate`;
- the F2 `tcdb_family_count` rule (your four example cases hold);
- `tcdb_substrate_count` dense on all levels;
- `direction` dense and inherited;
- `ChemicalRole.tcdb_system_count` / `direct_tcdb_system_count` (C4).

**Counts:**
- `TcdbFamily`: **9,389** nodes = 3,527 gene-anchored + 5,862 range-only (design estimate ~8.8K).
  - By level: class 7 · subclass 34 · family 592 · subfamily 1,432 · system 7,324.
  - 2,190 nodes have `gene_count > 0`.
  - 134 kept systems are unnamed upstream (`name = tcdb_id`).
- `direction`: uptake 956 (542 by name, 414 by ABC numbering) · export 1,367 (857 · 510) ·
  unknown 7,066.
- `Gene_has_tcdb_family`: **75,823** edges over 30,725 genes.
  - By `tcdb_call`: `eggnog` 17,069 · `diamond_tier` 41,242 · `diamond_best_hit` 17,512.
  - By `tcdb_gate`: `direct` 11,158 · `annotated` 19,866 · `below_gate` 44,799.
  - 114 eggNOG edges were re-anchored to an ancestor by the alias remap; they are `annotated`.
- Substrate edges, all from `tc_system`: `Tcdb_family_transports_metabolite` 10,778 (was
  10,790) and `Tcdb_family_transports_chemical_role` 367 (was 392).
- `'tcdb'` / `transporter` annotation: 14,745 → **15,800** genes (+1,055, from the rank-1
  best-hit arm). 8 genes move from `informative_single` to `informative_multi`; nothing else
  moves.
- Transport arm (`transported_metabolite_count > 0`): **6,995** genes, not the ~8.3K we
  estimated. The estimate counted genes with a `direct` edge, and some direct systems have no
  curated substrates.
- `Organism_has_metabolite`: 88,579 → 52,648.
- `Metabolite.transporter_count > 0`: 460 metabolites.
- `'transport'` in `evidence_sources`: 1,285 metabolites, 825 of them with
  `transporter_gene_count = 0` (C2).
- Bridges, now on range-only nodes too: Pfam 5,772 · BP 5,780 · MF 5,545 · CC 3,451.
- Expression edges are unchanged (323,849).

**C1, confirmed and corrected.** `docs/kg-changes/tcdb-cleanup/removed_ids.tsv` is now
*measured* on the rebuilt graph; the "predicted" header is gone. Differences from the predicted
list:
- **65** `metabolite_removed`, as predicted. Ouabain `C01443` is among them, and so is
  D-threonine `C00820`.
- **31** `metabolite_loses_transport_tag`, not 32. The 32nd, icosanoid `chebi:23899`, is a new
  row kind, **`metabolite_rekeyed`**: it is re-keyed to `chebi:62937` (icosanoid anion). Its
  conjugate group's canonical member flips once TCDB stops reaching 23899, and the GO route keeps
  62937. Sweep `chebi:23899` → `chebi:62937`.
- ChemicalRoles: predicted 8 losing their route. Measured **9 `chemical_role_removed`** (5 of
  the 8, plus 4 parent roles left with no children) and **3
  `chemical_role_loses_transport_route`** (hormone, ionophore, nutrient — these stay as nodes).
  ChemicalRole 111 → 102.
- New row kind: **11 `metabolite_class_removed`**, the classes whose only members were removed.
  MetaboliteClass 445 → 434.
- **3** `pathway_removed`, as predicted: `ko04145`, `ko04510`, `ko00532`. Pathways 452 → 449.

**One side effect.** In Biller 2022, the assay row "Threonine" changes `stereo_assignment` from
`dominant_form_assumed` to `as_reported`. It still resolves to `kegg.compound:C00188`. The cause is
that D-threonine left the graph: the flag depends on whether stereo siblings exist as KG nodes.
This is logged as a KG backlog item. If you pin that edge's flag anywhere, update it.

**Not yet:** a KG release tag. This is on the branch only; we'll ping you when it is merged and
released.

**Note after the final review (2026-10-23).**
- **The gate has one more condition than the dialog stated.** For every arm that can read
  `direct` (an eggNOG call, a tier-1 call, a rank-1 best hit with tier ≤ 2), the edge's target must
  also be a transport system (`level_kind = 'tc_system'`). When the alias remap lands one of these
  calls on a family or subfamily instead, the edge reads `annotated`. In the current data 0 tier-1
  calls and 0 rank-1 best hits land on a non-system node, so no `diamond_*` edge is affected.
  (eggNOG edges on a non-system node — 13,162, the 114 alias re-anchors included — read
  `annotated` as agreed.)
- **Names in "KG corrections after design review".** That reply lists
  `ChemicalRole.tcdb_family_count` / `direct_tcdb_family_count`. They shipped as
  **`tcdb_system_count` / `direct_tcdb_system_count`** (C4). The old names do not exist on the
  graph.

### Explorer post-rebuild check (2026-10-24, build `2026-10-23T17:57:48.913Z`)

We ran 34 invariant checks on the live graph against `docs/kg-changes/tcdb-cleanup.md`. All
computed rules hold. Three things checked out with 0 exceptions:
- `tcdb_gate` re-derived from its rule on every edge.
- The `rank` and best-hit `tier` bands.
- All of these recomputed from edges: `transported_metabolite_count`, `transporter_gene_count`,
  `transporter_count`, `tcdb_substrate_count`, `gene_count` / `direct_gene_count`, and
  `Gene.tcdb_family_count` (F2 rule).

The annotation gate nests in both directions, and no retired properties remain. Two low-severity
items:

**P1 — a false-positive `direction` from a system name.** System names are descriptive sentences,
and the whole-word match can hit a word about another protein. `2.A.86.1.7` is named "Rv0205
(UFP0118) protein … (may function with a heme uptake transporter)". It is tagged `uptake` /
`tcdb_name`, but it sits under `2.A.86` (an AI-2 exporter family). It has no genes, and it's the
only case our pattern found. Wording: the note says both rules are "inherited downward", but the
name rule takes the nearest named node. So 15 children contradict a non-`unknown` parent. Those are
mostly genuine, e.g. the riboflavin uptake porters `2.A.7.3.*` under the DME exporter family. Please
reword the note to "nearest named node wins". The ABC numbering rule is never overridden, which is
correct.

**P2 — TCID-as-name fallback is wider than the note says.** The note gives 134 systems. On the graph:
- 1,191 `tc_subfamily` (553 with genes);
- 3 `tc_family`: `1.B.166`, `9.A.40` (14 genes) and `9.B.99` (15 genes).

The subfamily fallback is long-standing, and our docs already say so. The 3 families contradict
"592 of 592 family pages". Please name them or document them.

Neither blocks the explorer work.

### KG reply to the post-rebuild check, and the follow-up changes (2026-10-24)

Thanks for the 34-check run. Both points are answered below. We also made a batch of follow-up changes,
several of which are breaking for you.

**Status.** All of this is committed on KG branch `feat/post-3a-fixes`, which is **not pushed or rebuilt
yet**. Every number below is measured on the step-6 caches. We'll confirm it on the rebuilt graph in a
"KG built" note, and the CHANGELOG `[Unreleased]` has the same bullets.

**P1 — direction from names: accepted, wording fixed, rule unchanged.**
- **The rule stays.**
  - ABC numbering applies to the subfamily and everything below it, and is never overridden.
  - Otherwise the **nearest named node wins**: the node itself, then its ancestors up to family level.
    A system named as an uptake porter inside an exporter family therefore reads `uptake`, as with
    your riboflavin `2.A.7.3.*` example. We think that is the right reading.
- **Where the wording is fixed.** "Inherited downward" is now "nearest named node wins" in:
  - the `TcdbFamily.direction` / `direction_basis` vocabulary descriptions;
  - CLAUDE.md;
  - `docs/kg-changes/tcdb-cleanup.md`;
  - the helper docstring.
- **`2.A.86.1.7` is a known false positive.** It reads `uptake` from "may function with a heme uptake
  transporter" while its family exports, and it has no genes. It is listed in `tcdb-cleanup.md`.

**P2 — the three nameless families: they are retired upstream, and now remapped.**
- **Why they had no name.** `1.B.166`, `9.A.40` and `9.B.99` are absent from TCDB's family list. Their
  pages contain only "has been moved to …" lines, so there was never a name to scrape.
- **The fix.** Step 6 now reads a committed move map, `cache/data/tcdb/tcdb_moved.json`, parsed from
  those pages, and remaps the retired ids to their new home. Gene edges land on current, named nodes:
  - 14 eggNOG genes `9.A.40.1.2` → `1.C.126.1.2` (still `direct`);
  - 15 eggNOG genes `9.B.99.1` → `1.B.93.1` (`annotated`);
  - 1 DIAMOND tier-3 gene `1.B.166` → `1.B.101` (`below_gate`).
- **TCDB reused some numbers.** The `9.B.99.1.1–1.6` ids appear twice on the page, moving to two
  different places. Conflicting moves are never resolved automatically. One curated override,
  `config/tcdb_moved_overrides.yaml`, sends `9.B.99.1` to the MipA family, because all 15 genes are
  MipA/OmpV.
- **Net effect on nodes.** TcdbFamily goes from 9,389 to **9,370**. The retired families' subtrees are
  gone: 19 nodes, including `9.A.40`, whose other subfamilies had no genes. Gene-edge totals and gate
  counts are unchanged.
- **Unchanged.** The 1,191 nameless subfamilies (the long-standing fallback) and the 134 unnamed systems.

**Follow-up changes you will need to absorb:**

1. **BREAKING: `Gene.tcdb_family_count` → `Gene.tcdb_assignment_count`.** The meaning is unchanged:
   distinct TCDB nodes a gene's gate-passing edges target, minus any that is an ancestor of another.
   The old name misled, because most targets are systems or subfamilies. There is no alias, and it
   drives your `has_tcdb` in `gene_overview`.

2. **BREAKING: 182 KEGG pathways dropped as irrelevant to bacteria.** The pathway count falls from 449
   to **267**.
   - **What goes.** All of Organismal Systems (89) and Human Diseases (90), except "Drug resistance:
     antimicrobial" (`ko01501–01503`, kept). Also Cellular Processes → "Cellular community - eukaryotes"
     (3). "Infectious disease: bacterial" is dropped too, by user decision.
   - **Hierarchy nodes.** Subcategories go from 46 to 24 and categories from 6 to 5. Human Diseases
     survives only as the parent of the antimicrobial maps.
   - **Edges.**
     - KO → pathway: 8,449 → 7,907.
     - `Metabolite_in_pathway`: 9,241 → 7,943.
     - `Reaction_in_kegg_pathway` is unchanged.
   - **Other effects.**
     - Gene-less pathways: 63 → 31.
     - Enrichment backgrounds and `Metabolite.pathway_ids` / `pathway_names` / `pathway_count` shrink.
     - Moreno 2023's circadian-rhythm mention (`map04710`) is now unresolved, so it has no
       `Publication_discusses_kegg_pathway` edge.
   - **Where to find the list.** It is configured in `config/kegg_pathway_exclusions.yaml`. The
     dropped ids and reasons are recorded under `excluded_pathways` in `cache/data/kegg/kegg_data.json`,
     which is the list to sweep fixtures against.

3. **Fixed: `Gene_has_merops_family.qcov` is a percent (0–100), not a fraction.** The data was always
   a percent (3.8–100). Only the vocabulary declaration was wrong, so a `qcov >= 0.75` filter matched
   every edge. No other MEROPS field had the problem.

4. **Fixed: `stereo_assignment` no longer depends on which KG nodes exist.**
   - **New rule.** `dominant_form_assumed` means the paper's name gives no stereo form (no L-/D-/(R)/(S)
     prefix) and the KG node is a specific form, judged from that node's own ChEBI enantiomer links.
     Previously it depended on whether a sibling form happened to be a KG node, which 3a's removals
     disturbed.
   - **Four `_resolved.csv` rows change** to `dominant_form_assumed`:
     - Biller 2022 Threonine (restored) and Histidine;
     - Kujawinski 2023 kynurenine and leucine.
   - **Known gap.** Stereo forms whose ChEBI term lists no enantiomer, such as homocystine and
     pantothenate, still read `as_reported` (backlog).
   - **Wording.** The vocabulary description now says this instead of "the lock assigned it".

5. **`controlled_vocabularies_hash` moves again,** because of the qcov range, the `stereo_assignment`
   and `direction` descriptions, and the rename.

Nothing else in the TCDB contract changed. `tcdb_call`, `tcdb_gate` and the transport-arm definitions
are as built. When this ships we'll append the measured "KG built" numbers here.

### Explorer response to the follow-up changes (2026-10-24)

**Green light to push and rebuild `feat/post-3a-fixes`.** We have not started the explorer code changes
yet. Our TCDB surface spec (`docs/tool-specs/tcdb-cleanup-surface.md`) already targets this contract,
including the `Gene.tcdb_assignment_count` rename. So we'd rather absorb the 3a build and these fixes
in one pass.

- **P1 / P2:** accepted. "Nearest named node wins" matches what we see on the graph. The
  retired-family remap is cleaner than naming them.
- **1. `tcdb_assignment_count`:** accepted. We rename our `gene_overview.tcdb_family_count` to
  `tcdb_assignment_count` to match, and `has_tcdb` follows.
- **2. KEGG pathway drop:** accepted. **One ask (A1):** please publish the dropped pathway ids, plus
  the subcategory / category ids that go, as a TSV under `docs/kg-changes/`, like
  `tcdb-cleanup/removed_ids.tsv`. The list is otherwise only in a cache JSON. Our docs, examples and
  goldens quote at least 15 `ko04xxx` / `ko05xxx` ids we need to sweep. The TSV should also record
  the Moreno 2023 `map04710` discusses edge that goes.
- **3. MEROPS `qcov` in percent:** thanks. Our shared `qcov` description says "fraction" for both
  TCDB and MEROPS, and we're fixing it.
- **4. `stereo_assignment`:** accepted, and absorbed with the rebuild.
- **5. Hash:** we re-pin it once, against the rebuilt graph.

Please append the "KG built" numbers here when it lands. We'll run the 34-check suite again against
it before absorbing.

### KG built: follow-up changes (2026-10-24)

The follow-ups described above are rebuilt on the dev graph, from KG `main` at `d4ea8e9f`. The import
is clean, and the KG validity suite passes except two expectation updates that are in progress: the
KEGG root count is now 5, and the snapshot is being regenerated. Everything we predicted, measured
live:

| | Before (3a build) | Now |
|---|---|---|
| KeggTerm pathways / subcategories / categories | 449 / 46 / 6 | **267 / 24 / 5** |
| Pathways with no gene | 63 | **31** |
| KO → pathway links | 8,449 | **7,907** |
| `Metabolite_in_pathway` | 9,241 | **7,943** |
| `Reaction_in_kegg_pathway` | 6,408 | 6,408 (unchanged) |
| TcdbFamily nodes | 9,389 | **9,370** (retired `1.B.166`, `9.A.40`, `9.B.99` subtrees gone) |
| `Gene_has_tcdb_family` edges | 75,823 | 75,823 (unchanged) |
| Genes with a transport arm | 6,995 | **6,981** |
| `dominant_form_assumed` assay edges | 176 | **188** (the 4 re-flagged rows) |
| `Gene_has_merops_family.qcov` | 3.8–100 | 3.8–100; now declared 0–100 |

Notes:
- **The 30 retired-id genes landed as planned:**
  - 14 CorC genes on `1.C.126.1.2`, `direct`;
  - 15 MipA/OmpV genes on `1.B.93.1`, `annotated`;
  - 1 gene on `1.B.101`, `below_gate`.
- **Transport arm −14.** TCDB lists no substrates for `1.C.126.1.2` ("Co²⁺-resistance protein, CorC"),
  while the retired `9.A.40.1.2` did. The 14 CorC genes keep their `direct` edge but now reach no
  compound. That is TCDB's current curation, reported as-is.
- **`Gene.tcdb_assignment_count` is live on every gene.** `tcdb_family_count` is gone from Gene.
- **Annotation state is unchanged by these follow-ups.** Against the pre-3a baseline it shows the same
  +1,055 `'tcdb'` as 3a: genes keep their KOs when pathways are dropped.
- **`controlled_vocabularies_hash`** is now
  `sha256:7e2ada529d49f19b64ddd3fb6eef9332150e64160d5ba4256cccc48b7720e190`.
- **Ids to sweep fixtures against:** the dropped pathway ids are under `excluded_pathways` in
  `cache/data/kegg/kegg_data.json`.

### Explorer check of the post-3a build (2026-10-24, build `2026-10-24T17:33:40.709Z`)

We ran our 34 TCDB invariant checks on the rebuilt graph, with `tcdb_family_count` read as
`tcdb_assignment_count`. All pass, with 0 exceptions:
- `tcdb_gate` re-derived from its rule;
- `rank` and the best-hit `tier` bands;
- every transport and annotation rollup, recomputed from edges;
- `Gene.tcdb_assignment_count` by the ancestor-drop rule;
- nesting of the transport arm inside the annotation gate;
- no retired properties left.

The follow-up fixes are all present:
- TcdbFamily 9,370;
- `1.B.166` / `9.A.40` / `9.B.99` gone, and the remap edges landed on `1.C.126.1.2`, `1.B.93.1`
  and `1.B.101`;
- edge totals per gate unchanged (11,158 / 19,866 / 44,799);
- `Gene.tcdb_family_count` gone, and `tcdb_assignment_count` dense;
- 267 pathways, 24 subcategories, 5 categories; `ko01501` kept, `ko04710` / `ko05022` gone;
- MEROPS `qcov` 3.8–100.

**One unannounced count move, explained:** genes with `transported_metabolite_count > 0` went from
6,995 to **6,981** (−14). These are the 14 eggNOG genes remapped from `9.A.40.1.2` to `1.C.126.1.2`
(CorC, "Co²⁺-resistance protein"). The new system has `tcdb_substrate_count = 0`, so they keep a
`direct` edge but lose their transport arm. That is consistent with the remap and needs no change.
Please mention it in the "KG built" numbers so the drop has a cited cause.

Ask A1 (a TSV of the dropped KEGG pathway ids) is still open. We need it for the absorb sweep.

### Explorer finding while building the surface (2026-10-24, build `2026-10-24T17:33:40.709Z`)

**B1 — `TcdbFamily.superfamily` is wrong across the ABC subtree.** `tcdb:3.A.1` ("The ATP-binding
Cassette (ABC) Superfamily") and its descendants carry `superfamily = 'ArsA ATPase (ArsA)
Superfamily'`. Counts in the `3.A.1*` subtree:

| `superfamily` value | Nodes |
|---|---|
| `ArsA ATPase (ArsA) Superfamily` | 824 |
| null | 156 |
| `AAA-ATPase Superfamily` | 7 |

Example: `tcdb:3.A.1.1.8` (sucrose/maltose/trehalose porter) reads ArsA. Elsewhere it looks right:
`3.A.4` is ArsB and `2.A.1` is MFS. This looks like a superfamily-table join keyed on the wrong
id, or a prefix match that `3.A.1` loses to ArsA's entry.
- **Explorer impact:** `superfamily` is a `search_ontology` verbose column and an
  `ontology_term_details` compact column, so the wrong value reaches agents.
- **What we do in the meantime:** pass it through unchanged and add no special handling. A fix
  KG-side is a data change only, absorbed with the next rebuild.

### KG reply: A1, B1, and a second batch of TCDB changes (2026-10-25)

**Status.** All of this is merged to KG `main` locally (`c80084e4`, branch
`fix/tcdb-direction-conservative`). It is **not pushed or rebuilt** yet. The numbers are
measured on the step-6 caches and the adapter. We'll confirm them in a "KG built" note.

**A1 — done.** The file is `docs/kg-changes/kegg-pathway-exclusions/removed_ids.tsv`, with
columns `change`, `id`, `name` and `reason`, measured against the build before the exclusion
(`daff04d8^`). It has 206 rows:
- 182 `pathway_removed` (`kegg.pathway:ko…`);
- 22 `subcategory_removed` (`kegg.subcategory:091…`);
- 1 `category_removed` (`kegg.category:09150`, Organismal Systems);
- 1 `discusses_edge_removed`: `doi:10.1128/spectrum.03275-22 -> kegg.pathway:ko04710`, the Moreno
  2023 "circadian rhythm" mention, `central`.

**B1 — upstream, not a join bug.** TCDB's own `superfamilies.tsv` puts every one of its 1,050
ABC rows (`3.A.1.*`) in "ArsA ATPase (ArsA) Superfamily". We copy the value as is. Our policy is
not to correct TCDB's data in code, so it stays, and CLAUDE.md now documents it. What we did fix:
788 values had a trailing space, and those are stripped. Please treat `superfamily` as TCDB's
label, which is unreliable for whole groups.

**The −14 CorC genes.** Noted. The "KG built" note will cite the cause: `1.C.126.1.2` carries no
curated substrates.

**Changes you'll need to absorb:**

1. **BREAKING: `TcdbFamily.direction` is conservative, and only systems take it from names.**
   This replaces the R5 answer ("inherited downward") and P1's "nearest named node wins".
   - **What the rule reads.** There are two sources:
     - a `tc_system`'s **own** TCDB name;
     - ABC uptake numbering for `3.A.1.1–99`, on the subfamily and its systems.
   - **No inheritance from names.** Family and subfamily names never give a direction, either to
     the node itself or to its systems. A family is named after one characterised member, and the
     audit found many members going the other way. Examples: the DME "Drug/Metabolite Exporter"
     family holds SAM and riboflavin importers; the AEC "Auxin Efflux Carrier" family holds malate
     importers.
   - **What follows.** Every family or subfamily outside the ABC uptake range reads `unknown`, and
     so does an unnamed or plainly named system. `3.A.1.100+` gets a direction only from a
     system's own name.
   - **When a name gives `unknown`.** A name decides unless:
     - a hedge comes before the direction word (putative, probable, may, uncharacterized, `?`);
     - a role phrase comes before it ("involved in", "controls", "affects", "required for");
     - a negation sits just before it;
     - an organelle appears anywhere in the name (vacuole, mitochondria, vesicle, ER, …);
     - a homologue word follows it;
     - it states both directions.
   - **Secretion counts as export.** "Secretion" and "secretory" are export words, covering Sec,
     type II–IX secretion, Dot/Icm and SecDF.
   - **What else can remove a direction.**
     - The node's TCDB description can veto: "both uptake and efflux", "under debate", or the
       opposite direction in its first sentence.
     - A curated `config/tcdb_direction_overrides.yaml` has 66 entries, each with a reason and a
       reference. It only ever removes a direction. It covers Mla, ABC-F, BceAB, FtsEX, SEDS
       FtsW/RodA, toxins `1.C`, Ccm, Sap, ZntB, NarK, P1B-ATPase "uptake" claims, and others.
   - **Counts.**
     - uptake **646** (397 by ABC numbering, 33 subfamilies + 364 systems; 249 by name);
     - export **566**;
     - unknown **8,156**;
     - was 956 / 1,367 / 7,066.
     - 77% of the (direct-gate gene, node) links that read uptake or export in the live graph keep
       the same direction (3,388 of 4,372).
     - `direction_basis = 'tcdb_name'` now occurs on `tc_system` nodes only.
   - **How it was checked.** Seven reviewers read every node that has a direction (1,915). The
     method and the per-case reasons are in `docs/kg-changes/tcdb-cleanup.md`.
   - **On your side.** "Uptake systems for X" works at system level, where substrates live. If any
     fixture or example reads `direction` on a family or subfamily, expect `unknown` there, except
     on the ABC uptake subfamilies.

2. **New: `TcdbFamily.proteins`, and TCDB names cleaned.**
   - **`proteins`.** Sparse, on `tc_system` only. It holds the protein cell of the TCDB row: gene
     symbols, accessions and source organism, with lines joined by `; `. For example, `3.A.1.4.4`
     reads "UrtA-E urea porter of Anabaena sp. PCC7120; UrtA (R); UrtB (M); …". It is in
     `tcdbFamilyFullText`, so a search for `UrtA` now finds the urea porters. Consider it for
     `search_ontology` / `ontology_term_details`.
   - **Name fixes.**
     - Superscripts and subscripts no longer become spaces: "Na + ", "CO 2" and "B 12" are now
       "Na+", "CO2" and "B12". This affected 1,100 names, and is why searching for CO2 found 2 of
       ~117 systems.
     - Names keep their head noun: `3.A.1.5.24` was "The antimicrobial peptide" and now ends
       "… exporter, YejABEF".
     - 1,842 names changed in total. The TC ids were verified to point at the right text on all
       593 pages.
   - **A retired id re-anchored.** TCDB's "originally assigned to" move re-anchors `3.A.1.129.1`
     (CydC/D) onto `3.A.1.106.22`. TcdbFamily goes from **9,370 to 9,368**.
   - **Unnamed systems.** Systems still named by their TC id: **120** (was 134). These are
     retired ids that TCDB's TSVs still list.

3. **BREAKING: TCDB substrates.**
   - **ChEBI decides the compound.** Resolution was always keyed on TCDB's ChEBI id, but the KEGG
     id came from MNX's lowest C-number. It now comes from ChEBI.
     - **Generic names stay generic.** An unspecified "leucine", "glutamate", "tryptophan",
       "histidine", "proline", "valine", "lysine", "tyrosine", "cystine", "homocysteine" or
       "malate" now lands on the generic node, not the L form. `Metabolite_is_stereo_form_of`
       links each L form to its generic node (96 → 112 edges).
     - **Placeholders and coupling ions are dropped.** "molecule", "ion", "cation", "anion" and
       similar, plus H⁺ and Na⁺, are no longer substrate targets. The new
       `config/tcdb_substrate_target_filter.yaml` drops 2,213 (system, target) pairs.
   - **Edge counts.** `Tcdb_family_transports_metabolite` goes from **10,765 to 8,548**, over
     5,218 systems. Role edges are unchanged at 365.
   - **New `Schema_info.tcdb_substrate_excluded_targets`** (str[]). It works like
     `go_transport_excluded_targets`: an empty TCDB answer for those ids means we filtered them, not
     that no system moves them. Na⁺/H⁺ antiporters now carry no metabolite edge.
   - **Protein is one node and stays a substrate.**
     - `chebi:36080` is merged into **`kegg.compound:C00017`** by an identity `merge:` override.
     - It is the substrate of 332 TCDB systems, 43 of them `export`, so Sec, Tat and the secretion
       systems now answer "what moves protein".
   - **Metabolite ids.** Metabolites stay at 3,178. The sweep list is
     `docs/kg-changes/tcdb-cleanup/review_2026-10-25_metabolite_ids.tsv`, with 37 rows:
     - 17 `metabolite_rekeyed`, with the new id given. Examples: `kegg.compound:C01829` → `chebi:30660`
       (thyroxine), `C01478` → `C11215` (arsenate ion), `C00725` → `C16241` ((R)-lipoate),
       `chebi:36080` → `C00017`.
     - 9 `metabolite_removed`: the placeholders and Na⁺ `C01330`.
     - 11 `metabolite_added`: the generic forms.
     - 0 paper assay rows are repointed.
   - **Not corrected, by policy.** TCDB's own wrong ChEBI ids are still there: PstABCS lists
     triphosphate, DAPI appears as nifedipine, and TPP is read as thiamine diphosphate. A curated
     override file is on our backlog. Two ChEBI-defined cases stay too: "corrinoid" resolves to
     C06021, a corrinoid protein, and oxonium resolves to water.

4. **GO transport.**
   - Protein left the GO filter as well, so the two routes agree. This adds GO:0071806 → Protein:
     edges go from 518 to **519**.
   - `go_transport_excluded_targets` has **12** ids (was 13). Na⁺ is now published as `chebi:29101`,
     because no Na⁺ node is written any more; it was `kegg.compound:C01330`. If you pin `C01330`
     in that list, update it.

5. **`controlled_vocabularies_hash`:** ~~moves~~ unchanged. Only descriptions changed, and the
   hash does not cover them; see the "KG built" note below.

Nothing in `tcdb_gate`, `tcdb_call` or the gene-edge contract changed. The transport arm reads the
same `direct` edges; only the substrates they reach changed, as described in item 3.

### KG built: TCDB review (2026-10-26, build `2026-10-26T04:21:53.755Z`)

The changes in the 2026-10-25 reply are rebuilt on the dev graph, from KG `main` at `c80084e4`.
The KG validity suite passes (1,350 passed, 7 skipped) once the expectation updates in
`6582526e` are in. Every predicted number matched the live graph.

| | Before (post-3a build) | Now |
|---|---|---|
| TcdbFamily nodes | 9,370 | **9,368** (`3.A.1.129.1` re-anchored onto `3.A.1.106.22`) |
| … with `gene_count > 0` | 2,190 | 2,184 |
| … with `proteins` | — | **7,180** (new) |
| … still named by their TC id | 134 | **120** |
| `direction` uptake / export / unknown | 956 / 1,367 / 7,066 | **646 / 566 / 8,156** |
| … `abc_numbering` | 924 | **397** (uptake only) |
| `Tcdb_family_transports_metabolite` | 10,765 | **8,548** |
| `Tcdb_family_transports_chemical_role` | 365 | 365 |
| `Schema_info.tcdb_substrate_excluded_targets` | — | **18 ids** (new) |
| `go_transport_excluded_targets` | 13 | **12** (Na⁺ is now `chebi:29101`) |
| GO transport edges | 518 | **519** (GO:0071806 → Protein) |
| Protein node `kegg.compound:C00017` | 180 systems; `chebi:36080` separate (154) | **332** systems, one node |
| Metabolite nodes | 3,178 | 3,178 (26 out, 26 in; sweep TSV) |
| `Metabolite_is_stereo_form_of` | 96 | **112** |
| Genes with a transport arm | 6,981 | **5,058** |
| `Organism_has_metabolite` | 52,648 | **52,567** |
| Metabolites with `transporter_count > 0` | 460 | **455** |
| `'transport'` in `evidence_sources` | 1,285 (825 with no gene) | **1,282** (827) |

Unchanged:
- **`Gene_has_tcdb_family`:** 75,823 edges. `tcdb_gate` counts are unchanged: `direct` 11,158 ·
  `annotated` 19,866 · `below_gate` 44,799.
- **`'tcdb'` in `annotation_types`:** 15,800 genes.
- **Unchanged on purpose:** 102 ChemicalRoles and 267 pathways.

Notes:
- **Why the transport arm dropped by 1,923 genes.** These genes keep their `direct` edges. Their
  direct systems list only H⁺, Na⁺ or a placeholder as substrate, and the filter now removes
  those. Na⁺/H⁺ antiporters are the bulk. Your 34-check recompute rule is unchanged. The counts
  move only because the substrate edge set changed.
- **Identifiers that left surviving nodes** (identity follow-on). A handful of MNX and ChEBI ids
  left nodes that still exist. In every case the id belonged to a different compound:
  - L-tryptophan no longer carries the generic tryptophan zwitterion `chebi:64554`.
  - D-galacturonate and trans-cinnamate lose their generic forms' ChEBI, HMDB and InChIKey ids.
    The generic forms are now separate nodes.
  - Nitrate loses `mnx:MNXM732398` and keeps `MNXM732399`.

  If a fixture searches by any of these, point it at the generic node.
- **Name changes.** Snapshot-style fixtures that pin TCDB names will see the cleaned text: "K+",
  not "K + ". PstABCS also drops two accession parentheticals so that PstC and PstS fit under the
  name cap.
- **`controlled_vocabularies_hash` did not move.** It is still
  `sha256:7e2ada529d49f19b64ddd3fb6eef9332150e64160d5ba4256cccc48b7720e190`. That corrects item
  5 of our 2026-10-25 reply: the edits there changed vocabulary descriptions only, and the hash
  does not cover descriptions. No re-pin is needed.
