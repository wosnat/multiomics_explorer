# Explorer-side asks: GO transport substrates → Metabolite edges, and the transport programme (2026-10-18)

**Date:** 2026-10-18 · **From:** KG (`multiomics_biocypher_kg`) · **To:** explorer (`multiomics_explorer`)
**Direction:** KG → explorer (like `2026-10-13-coculture-partner-list-explorer-asks.md`).
**KG design:** `multiomics_biocypher_kg/docs/superpowers/specs/2026-10-18-go-transport-substrates-design.md`
(draft, approved KG-side; not yet planned or built).
**Context:** the `2026-10-06-pro_n_import_coculture` analysis (`multiomics_analysis/.../gaps_and_friction.md`,
`methods/notebook.md`; methodology review round 2) spent seven rule versions building its own
transporter and substrate rules on top of the KG. Your backlog items 2c.5, 2c.7, 2c.9 and KG ask D3
come from the same analysis. This doc covers (a) the programme the KG is starting to answer them,
and (b) the first slice, which is additive in the graph and ships with an explorer MCP release. We want your comments on both
before the KG plans slice 1, and early comments on slice 3, which **will** be breaking for you.

Please answer inline in a "Responses" section at the end.

## 1. The programme

### Framing

No route through the graph gives *the* transporters or *the* substrates; every route is biased by
design:

| Route | Built-in bias |
|---|---|
| TCDB family transfer (eggNOG) | inherits the subfamily's substrate list; can name the wrong sibling system (MED4 `cynD` reads nitrate/nitrite, `transport_substrate_resolution = 'resolved'`; it is the cyanate system) |
| TCDB best hit (diamond) | one curated reference at whatever identity; no direction. Computed today, then **discarded** by the tier/consensus collapse |
| GO substrate terms | only as good as whoever assigned the GO term; correlated with InterPro/KO naming |
| Metabolite class (KEGG BRITE) | lists representative compounds, so "unlisted" ≠ "not in the class" |
| Cyanorak / BRITE transporter categories | coarse class, no compound |

So the KG will publish **separate, cleanly queryable routes, each with its caveat stated where a
consumer meets it**, and stop fusing them into flags. The reader is an LLM agent; it answers a
question by reading several routes side by side. That works better than it sounds: on MED4, for the
46 genes where GO and the diamond best hit both name a substrate, after ChEBI normalisation 25 name
the same compound, 11 a related one, 10 disagree (mostly naming granularity). Agreement is the
confident core; disagreements are few enough to inspect.

### Questions the routes must serve

1. What are the transporters, and what do they transport?
2. Are up-regulated genes enriched for a transport family?
3. What transports X (a compound or a class, e.g. amino acids), if anything — and in which direction?

### Projects, in order

| # | Project | Explorer impact |
|---|---|---|
| 1 | **GO transport substrates → Metabolite edges** (this doc, §2–5) | additive graph change; ships with an explorer MCP release (GO arm surfaced) + `mcp_min_version` bump |
| 2 | **Diamond best-hit details** — keep each gene's best-hit TCDB systems (hits within 90% of the best bitscore, qcov ≥ 75%, TC classes 8/9 excluded) with *those systems'* own substrate lists | additive; shape TBD, stored minimally so it survives #3 |
| 3 | **TCDB nodes/edges redesign** — goal: the obvious query is the correct one. Likely retires `substrate_depth`, `substrate_breadth`, `transport_substrate_resolution` | **breaking** (see TPS-007) |
| 4 | **A transport-analysis recipe** for LLM consumers — several answers per question, each route's caveat, how to read agreement, what an empty answer means | proposed home: `docs://analysis/transport` (see TPS-005) |

A per-gene `Gene → Metabolite` transport edge was discussed and is deferred until after #3.

## 2. Slice 1: what lands

*(Updated 2026-10-18 after the explorer responses; §2–§3 are current.)*

GO defines its transport terms logically: "cyanate transmembrane transporter activity" (GO:0015110)
≡ *transmembrane transporter activity* **and** *has primary input* (RO:0004009) CHEBI:29195 (GO's
`go-plus` release). The KG turns those axioms into edges from GO term nodes to canonical
`Metabolite` / `ChemicalRole` nodes — the same nodes TCDB, KEGG reactions and metabolomics use.

| New edge | Source → target |
|---|---|
| `Molecular_function_transports_metabolite` | MolecularFunction → Metabolite |
| `Biological_process_transports_metabolite` | BiologicalProcess → Metabolite |
| `Molecular_function_transports_chemical_role` | MolecularFunction → ChemicalRole |
| `Biological_process_transports_chemical_role` | BiologicalProcess → ChemicalRole |

- **One edge property, `go_chebi_ids` (str[])** — GO's ChEBI id(s) before canonicalisation; one edge per
  (GO term, canonical target). The relation is always *has primary input* (RO:0004009), in MF and BP alike.
  MF ("is a transporter for X") and BP ("involved in moving X" — includes storage, regulation, accessory
  subunits) are separate edge types.
- **Target filter:** no edges to upper-level ChEBI classes (ion, monoatomic ion / cation / anion, metal
  cation, transition element cation, nitrogen molecular entity, biomacromolecule, chemical entity, protein,
  inorganic anion) or to H⁺ / Na⁺. The removed canonical ids are published as
  `Schema_info.go_transport_excluded_targets` (via `kg_release_info`). K⁺, Cl⁻, iron, metals and nutrient
  ions stay.
- **Each GO term carries only its own axiom.** No propagation to ancestor/descendant GO terms, genes or
  organisms. The edge says "GO defines this term as transporting X", **not** "this gene transports X";
  whether a gene deserves the term is the gene→GO edge's `sources` / `evidence`.
- **Roles:** GO names role substrates via its `GOCHE_n` classes, where n is the ChEBI role id. In the
  corpus they reach 5 roles — siderophore (`siderophore transport`, 290 genes direct), xenobiotic,
  vitamin, toxin, neurotransmitter (`neurotransmitter:sodium symporter activity`, 19 genes; bacterial
  NSS, mostly amino-acid transporters — the role name needs a caveat). All 5 already exist as
  `ChemicalRole` nodes; no role nodes are created.
- **New Metabolite nodes** for GO substrates no other route reaches, only when the GO term is a KG GO
  node. They carry a new `Metabolite.evidence_sources` value **`go_transport`**. The existing
  `transport` keeps meaning "TCDB substrate" — the routes stay separate.
- **No KEGG pathway pull-in:** a GO-only compound links only to pathways already in the graph; no
  `KeggTerm` is added and no existing pathway count changes.
- **One rollup for the GO route, kept separate:** `Metabolite.go_transport_organism_names` (str[]) /
  `go_transport_organism_count` (int), sparse on GO-reached metabolites. Unchanged: `organism_count` / `organism_names`, `transporter_count`,
  `transporter_gene_count`, `Organism_has_metabolite` and the Gene metabolite counts are unchanged.
  A GO-only metabolite therefore reads `organism_count = 0` but carries its GO reach in
  `go_transport_organism_*` (TPS-002).

Measured 2026-10-18 (go-plus of 2026-07-26): 1,593 GO transport terms carry a ChEBI substrate;
gene reach over 43 strains (TCDB: 30,547): 6,290 via ChEBI-class substrates only (first pass) →
6,786 including role substrates → **5,436 after the target filter** (2,777 MF+BP, 2,122 BP-only, 537
MF-only; MED4 59). MED4: cynA → cyanate; cynD → cyanate + nitrate; sul1/sul3 → sulfate; ktrA → K⁺;
amt1 → ammonium; urtA → urea; dpp → peptide; pstS → phosphate; fadD, rpaA, salY → none (correct);
ftn → iron ion via the BP term "iron ion transport" (ferritin stores iron — BP's broader meaning). Final counts (edges, new nodes,
generic share, filter drops) come with the KG build.

## 3. Contract change

| | Today | After slice 1 |
|---|---|---|
| GO term → Metabolite / ChemicalRole | none | 4 new edge types; property `go_chebi_ids: str[]`; targets filtered |
| `Metabolite.evidence_sources` | `metabolism`, `transport`, `metabolomics` | + `go_transport` (open vocabulary) |
| `Metabolite` nodes | — | + GO-only substrates (count TBD at build); `organism_count = 0`, GO reach in `go_transport_organism_names` / `_count` |
| `Schema_info.go_transport_excluded_targets` | — | new `str[]` (filtered canonical ids) |
| `controlled_vocabularies_hash` | — | **moves** (new value in an open vocab) |
| Everything TCDB / KEGG / assay | — | unchanged |

Nothing is renamed or removed. Slice 1 ships as a **joint release**: the explorer surfaces the GO route
in an MCP release, and the KG release that carries slice 1 raises `mcp_min_version` to that release.

## 4. Asks

| ID | Ask | Pri |
|---|---|---|
| **TPS-001** | **Shape of the GO arm in the MCP release.** e.g. `evidence_source ∈ {metabolism, transport, go_transport}` on `genes_by_metabolite` / `metabolites_by_gene` (path: Gene → GO term → Metabolite). What does each row carry, and do role inputs (`chebi.role:`) reach the role edges? | P1 |
| **TPS-002** | **GO-only metabolites with `organism_count = 0`.** The KG keeps the GO route out of organism rollups (no blending). Fine for `list_metabolites` (do you filter or sort on `organism_count` in a way that would surface or hide them oddly?), or do you want a separate GO-route organism rollup later? | P1 |
| TPS-003 | **Class reach** — "what transports amino acids via GO": walk GO `is_a` from the specific term, or walk `Metabolite_in_metabolite_class`. The KG plans no precompute; say if you want one. | P2 |
| TPS-004 | **Edge properties** — none. Would you use the axiom's original ChEBI id (before KG canonicalisation), e.g. to show "GO says CHEBI:29195"? Default: not stored. | P3 |
| **TPS-005** | **Recipe ownership** (#4). Proposed: an explorer `docs://analysis/transport` page, KG supplying route caveats + measured agreement numbers. Confirm it's yours, or propose a different home. Surfacing no longer waits for the recipe: either the recipe ships in the same release, or the tool docs carry the route caveats until it lands. | P2 |
| TPS-006 | **Where the per-route caveat lives** so an LLM meets it: `schema_config.yaml` comments are not exposed; there is no `ControlledVocabulary` node per edge type. Options: (a) a vocabulary-style description node per route; (b) `kg_schema` edge-type descriptions; (c) docs only. Preference? | P2 |
| **TPS-007** | **Early inventory for the redesign (#3).** Fields in scope: `substrate_depth`, `transport_substrate_resolution`, `transported_metabolite_count`, `tcdb_evidence_score_max`, `attachment_depth`, `substrate_breadth`. Which of these carry tool behaviour (filters, warnings, defaults) vs pass-through fields? Which would you most like to stop explaining to an LLM? This decides what the redesign keeps. | P2 |
| TPS-008 | **Backlog overlap.** 2c.5 (flat organism transport reach), 2c.7 (`substrate_source_family`) and 2c.9 (genome context per substrate) are folded into #2/#3 rather than shipped piecemeal. OK to hold them, or is any one needed sooner? | P2 |

## 5. Timeline

1. KG: implementation plan for slice 1 after the TPS-001/002 answers; build on the dev graph (7687).
2. Explorer: absorb the dev build and surface the GO arm (TPS-001).
3. Explorer: MCP release.
4. KG: release slice 1 with `mcp_min_version` raised to that explorer release.

- #2 and #3 get their own design docs; #3 will come with its own asks doc and an `mcp_min_version` bump.

## Responses (explorer, 2026-10-18)

Reviewed against this doc and the KG design
(`docs/superpowers/specs/2026-10-18-go-transport-substrates-design.md`, draft). Live-KG numbers below
are from the current dev graph. Overall: the concept is sound — separate routes, edges at GO-term
level with no propagation, `go_transport` kept apart from `transport`, roles only to existing
`ChemicalRole` nodes (all 5 confirmed live), no pathway pull-in. Five things need fixing before
slice 1 is planned.

### R1. Scope: the design doc still says "no MCP surfacing"

The design's §3 non-goals list "Explorer / MCP surfacing", and its §8 says surfacing "waits for the
recipe (project 4)". Slice 1 now ships with an explorer MCP release and an `mcp_min_version` bump
(this doc §3, §5). Please update the design: move surfacing out of non-goals, rewrite §8 as a joint
release, and add the bump to §7.

### R2. "Relation is always RO:0004009" may empty the process (BP) route

The genus filter includes BP (GO:0006810 *transport*), but as far as we know GO defines BP transport
terms ("cyanate transport") with *transports or maintains localization of* (RO:0002313), not *has
primary input*. Not checked against go-plus from here. If so, either the two
`Biological_process_*` edge types come out nearly empty, or the 1,593-term count already includes
RO:0002313 fillers, in which case "the relation is always RO:0004009", the parser rule and its unit
test are wrong. **Ask:** report axiom counts per relation × namespace before planning, and state
the relation per edge type.

### R3. BP is the weaker route; say so

BP "X transport" also covers storage, regulation and accessory subunits. ftn → iron ion is most
likely a BP annotation ("iron ion transport" on ferritin) — not really a GO-assignment error, but
what BP means. MF transporter activity is much closer to "this protein moves X". The route caveat
(TPS-006) should state the difference; shipping MF only in slice 1 is also an option.

### R4. The generic-share report won't catch the main noise

`structure_kind = 'generic'` flags classes, not H⁺ or Na⁺, which are specific molecules. Gene counts
on transport terms in the current KG: *proton transmembrane transporter activity* 429,
*proton-transporting ATP synthase activity, rotational mechanism* 318, *proton transmembrane
transport* (BP) 611; every symporter also names its coupling ion (NSS → Na⁺ is the same issue as the
neurotransmitter caveat). Unhandled, "what transports H⁺/Na⁺" is swamped and per-gene answers list
the driving ion next to the substrate. **Ask:** the §6 identity report lists the top target compounds
by gene count; decide on coupling ions from that. (Already handled in the design: PR/GO fillers are
skipped, so no "protein" substrate; electron-transport terms fall outside the genus filter.)

### R5. Agreement is weaker evidence than it reads

The 25/46 MED4 agreement compares routes that often share the same homology (InterPro2GO vs eggNOG
TCDB transfer). State that where the agreement claim is made, in both docs. Note also that the
comparison used the diamond best hit, which is not in the KG until project #2.

### Answers to the asks

- **TPS-001 — GO arm shape.** Add `go_transport` as a third `evidence_source` on
  `genes_by_metabolite` / `metabolites_by_gene`. Each row carries the GO term id + name, the
  namespace (MF / BP, per R3), and the gene→GO edge's `evidence` / `sources`, so cases like ftn can be
  told apart. `gene_overview` gets a `go_transport` value in its per-gene `evidence_sources`.
  `chebi.role:` inputs should reach the role edges (siderophore: 290 genes); today a role id is
  diagnostic-only in the explorer, so this is explorer work, no KG change needed.
- **TPS-002 — organism reach.** `organism_count = 0` is not honest once the GO arm is surfaced: the gene
  path exists, in up to 43 strains. Organism-scoped metabolite queries would silently miss GO-only
  compounds, and browse sorts would always push them to the bottom. A1 forbids *blending* routes,
  not a separate rollup. **Ask:** a separate property (e.g. `Metabolite.go_transport_organism_names`
  / `_count`) in slice 1; fallback is per-call computation explorer-side.
- **TPS-003 — class reach.** No precompute for slice 1; the recipe documents both walks.
- **TPS-004 — original ChEBI id.** Yes, store it (cheap). It is the only way to tell whether a
  GO↔TCDB disagreement comes from canonicalisation or from the annotation — matters for the
  "11 related" bucket.
- **TPS-005 — recipe.** Explorer-owned `docs://analysis/transport`, hand-authored like the other
  analysis pages; the KG supplies route caveats and measured agreement numbers. Until it lands, the
  tool docs carry the caveats.
- **TPS-006 — caveat home.** (b) `kg_schema` edge-type descriptions plus (c) docs. `kg_schema` is the
  page an LLM reads before `run_cypher`; (a) adds a node type just to hold prose. Given R3/R4 the
  caveat is load-bearing, so treat this as P1 alongside the release.
- **TPS-007 — redesign inventory.** Behaviour-carrying today: `substrate_depth` (filter, default row
  sort, "inherited dominates" warning); `transport_substrate_resolution` (`family_inferred` warning in
  `metabolites_by_gene`); `tcdb_evidence_score_max` (ranking guidance). The rest are mostly
  pass-through. A full classification comes with #3's asks doc.
- **TPS-008 — backlog.** Holding 2c.7 and 2c.9 is fine. 2c.5 (flat transport reach in `top_organisms`)
  gives a wrong-looking answer today; the explorer keeps its per-call Cypher fallback as an option
  rather than wait for #3.

### Other

- **Direction.** A non-goal in the design ("too sparse": 5 MED4 import annotations, all on one gene),
  which is reasonable — but question 3 asks "in which direction", so say here that no project in the
  programme currently answers it.
- **go-plus date.** This doc says go-plus of 2026-07-26; the design says downloaded 2026-10-18. Use the
  release date the cache header records.

---

## KG reply (2026-10-18)

All points absorbed into the KG design
(`docs/superpowers/specs/2026-10-18-go-transport-substrates-design.md`). Measured against go-plus
(release 2026-07-26) and every strain's merged annotations.

- **R1 — scope.** Done: surfacing is no longer a non-goal; design §8 is now the joint release (your
  TPS-001 shape), §7 carries the `mcp_min_version` bump.
- **R2 — relation.** Checked; the concern doesn't hold. Over transport-genus axioms, BP terms use
  *has primary input* too: 882 BP and 965 MF chemical fillers are RO:0004009; **no** transport term
  uses RO:0002313. The only other chemical relation is RO:0012001 *has small molecule activator*
  (23 MF terms, ligand-gated channels) — an activator, not a substrate, and excluded. The design now
  states the relation per edge type and the exclusion.
- **R3 — BP is weaker.** Agreed and confirmed: MED4 `ftn` reaches iron through BP "iron ion
  transport" (GO:0006826). MF-only was considered and rejected — of 6,786 genes reaching a GO
  substrate, 2,395 do so only through BP (3,689 both, 702 MF-only). MF and BP stay separate edge
  types; the caveat names the difference.
- **R4 — coupling ions / generic noise.** Confirmed and handled with a target filter
  (design §4, list in `config/go_transport_target_filter.yaml`). A frequency cut-off doesn't work: no
  target exceeds 18% of genes, and real substrates sit among the noise (peptide 10.1%, amino acid
  6.5%). So:
  - **Dropped:** upper-level ChEBI classes (ion, monoatomic ion / cation / anion, metal cation,
    transition element cation, nitrogen molecular entity, biomacromolecule, chemical entity,
    protein, inorganic anion); **H⁺ and Na⁺** — they stand out on share of *terms* (5.5% / 4.0%,
    next K⁺ 1.8%), and most genes reaching them as sole input are bioenergetics (ATP synthase,
    Na⁺-NQR, Na⁺/H⁺ antiporters). "What transports Na⁺" goes to TCDB only.
  - **Kept:** K⁺ (94% of its genes reach it as sole input — Trk, Ktr, K⁺ channels), Cl⁻ (CLC),
    iron and metals (of 1,124 genes reaching iron/metals, ~85% are transporters; the ~170
    non-transporters — ferritins, CopC/D, AhpC — come through BP, i.e. R3), nutrient ions.
  - The identity report publishes the per-target distribution (gene share, term share, strains) on
    every build.
- **R5 — agreement is correlated.** Added to the design's framing, with the note that the
  comparison used the diamond best hit, which is project #2.
- **TPS-002 — accepted.** New post-import `Metabolite.go_transport_organism_names` (str[]) /
  `go_transport_organism_count` (int), path Gene → MF|BP term → Metabolite; separate from
  `organism_names` (no blending). So §2's "GO-only metabolite reads `organism_count = 0`" still
  holds for `organism_count`, but the GO reach is now on the node.
- **TPS-004 — accepted.** Edge property `go_chebi_id` (str): the ChEBI id exactly as GO's axiom
  states it (for roles, the ChEBI role id behind `GOCHE_n`), before canonicalisation. Updates §2 /
  §3 above: the edges are no longer property-less.
- **TPS-006 — noted.** `kg_schema` edge-type descriptions are explorer-side; the KG will supply the
  caveat text (MF vs BP, the filter, "term definition ≠ gene fact") in the kg-changes doc for you to
  lift.
- **Direction.** Recorded in the design as an open gap: no project in the programme answers
  question 3's "in which direction".
- **go-plus date.** The derived cache header records the release date; the kg-changes doc stamps
  that, not the download date.

Updated contract (supersedes §3's rows where they differ):

| | After slice 1 |
|---|---|
| GO term → Metabolite / ChemicalRole | 4 edge types, one property `go_chebi_id` |
| Targets | filtered: no upper-level classes, no H⁺ / Na⁺ |
| `Metabolite.evidence_sources` | + `go_transport` |
| `Metabolite.go_transport_organism_names` / `_count` | new, sparse (on GO-reached metabolites) |
| `controlled_vocabularies_hash` | moves |

---

## Explorer follow-up (2026-10-18)

The reply resolves R1–R5, TPS-002 and TPS-004; R2 was wrong on our side (thanks for measuring).
Four items still need an answer before planning:

- **F1 — the H⁺ / Na⁺ drop must be visible to the reader.** "What transports Na⁺ via GO" now returns
  empty by curation, not biology (NhaS / Na⁺ antiporters, Na⁺ channels lose the GO route), and an
  LLM cannot tell "filtered" from "no transporter". **Ask:** put the filter list in the caveat text,
  and publish it where the explorer can read it — via `kg_release_info`, or in the kg-changes doc for
  us to copy into the tool docs. Explorer side: the GO arm warns when a requested target is on the
  filter list.
- **F2 — `go_chebi_id` cardinality.** The KG merges conjugate acid/base pairs and secondary ChEBI ids
  onto one node, so two of a term's axioms can land on the same Metabolite. With a single `str`
  property, one id is lost or two parallel edges appear. **Ask:** `str[]`, or one edge per axiom —
  state which.
- **F3 — the doc body is stale.** The reply supersedes only §3, but §2 still says "No edge
  properties" and "organism_count = 0" with no mention of `go_transport_organism_names` / `_count`.
  §2 says 6,290 genes; the reply says 6,786 reach a GO substrate — which is before the target filter
  and which after? **Ask:** update §2, or note that the reply's contract table supersedes §2 too, and
  reconcile the counts.
- **F4 — TPS-006 is explorer work for the release.** `kg_schema` has no edge-type descriptions today
  (only labels and properties), so lifting the caveat is a new explorer feature, not a doc paste.
  Explorer plan: a hand-authored edge-descriptions block next to `schema_baseline.yaml`, filled from
  the caveat text the KG supplies in the kg-changes doc. No KG change needed unless you'd rather stamp
  the descriptions in the graph.

TPS-003, -005, -007 and -008 are not addressed in the reply; we read that as agreement. Please
confirm.

## KG answer to the follow-up (2026-10-18)

§2 and §3 above are now current (F3); the design doc carries the same.

- **F1 — filter visibility. Done as asked.** Post-import stamps
  `Schema_info.go_transport_excluded_targets` (str[], the canonical Metabolite ids the filter removed,
  sorted), read from the build's derived cache so it matches what was built — available to
  `kg_release_info`. The kg-changes doc carries the same list with names and reasons as caveat text.
  Your GO-arm warning on a filtered target fits it.
- **F2 — `go_chebi_ids: str[]`.** One edge per (GO term, canonical target); the list holds every GO-stated
  ChEBI id that canonicalised onto that target (e.g. a conjugate pair). No parallel edges, no lost id.
- **F3 — counts reconciled.** 6,290 = first pass, ChEBI-class substrates only; 6,786 = including
  `GOCHE_n` role substrates, before the target filter; **5,436 after the filter** (2,777 MF+BP, 2,122
  BP-only, 537 MF-only; MED4 59). The build figure to check against is 5,436.
- **F4 — agreed.** Edge-type descriptions in `kg_schema` are explorer work; the KG supplies one
  ready-to-copy caveat paragraph per edge type in the kg-changes doc. No graph stamping.
- **TPS-003, -005, -007, -008 — confirmed agreement** (no precompute for class reach; the recipe is
  explorer-owned `docs://analysis/transport`; your TPS-007 inventory is noted for #3's asks doc; 2c.7 /
  2c.9 held, 2c.5 interim fallback is your call).

Unless you object, the KG proceeds to the implementation plan for slice 1.

## Explorer: no objection (2026-10-18)

F1–F4 and the TPS confirmations are accepted; please proceed to the slice 1 implementation plan.
Two small corrections:

- The design's validation section (line ~366) still checks MED4 against "the measured 65"; the
  post-filter figure is 59.
- §2's rollup bullet reads "Unchanged: … are unchanged" — leftover wording.

Explorer side, this is tracked as backlog 2c.13 (GO transport surface for the joint release),
including passing `Schema_info.go_transport_excluded_targets` through `kg_release_info`.

## KG built (2026-10-18)

Slice 1 is built and verified on the dev graph (branch `feat/go-transport` in the KG repo; not yet
released). Details and ready-to-copy caveat paragraphs per edge type:
`multiomics_biocypher_kg/docs/kg-changes/go-transport-substrates.md`.

- **Edges (count, distinct targets):** `Molecular_function_transports_metabolite` 257 (171),
  `Biological_process_transports_metabolite` 246 (182), `Molecular_function_transports_chemical_role` 7 (5),
  `Biological_process_transports_chemical_role` 8 (5); 518 total. Each carries `go_chebi_ids`.
- **Metabolite nodes** 3,214 to 3,243 (+29, `evidence_sources` contains `go_transport`);
  `Metabolite_in_pathway` +6 (into already-kept pathways), no new `KeggTerm`.
- **Target filter:** 13 ids, 88 axioms dropped, published as `Schema_info.go_transport_excluded_targets`
  (pass through `kg_release_info`).
- **Rollup:** `Metabolite.go_transport_organism_names` / `_count` on 198 metabolites (count min 1,
  median 10, max 43). Direct gene-to-GO annotations only, no `is_a` propagation, so 10 of the 208
  metabolite targets (reached only by ancestor terms no gene carries) have none.
  Clarification (final review): "sparse (on GO-reached metabolites)" means absent = no directly annotated gene path, NOT no GO transport edge; to test for an edge, test the edge.
- **Reach:** 5,436 genes over 43 strains (2,777 MF+BP, 2,122 BP-only, 537 MF-only); MED4 59,
  KT2440 390, DSS-3 332.
- **`controlled_vocabularies_hash` moved** (`go_transport` added to the `Metabolite.evidence_sources`
  description).
- **GO release moved to 2026-07-26** (was March 2026). Deltas: MolecularFunction nodes 2,899 to 2,890,
  BiologicalProcess 3,433 to 3,322, CellularComponent 451 unchanged; `Gene_enables_molecular_function`
  363,298 to 362,439, `Gene_involved_in_biological_process` 546,971 to 533,186,
  `Gene_located_in_cellular_component` 154,722 to 155,459.
- **Joint release:** the KG release carrying slice 1 sets `mcp_min_version` to the explorer release that
  surfaces the GO arm (backlog 2c.13).

## Explorer surfaced (2026-10-23)

Branch `go-transport-surface` (not yet merged; ships in the next explorer MCP release). Surfaced:
- `go_transport` as a default-on third arm on `genes_by_metabolite` / `metabolites_by_gene` (`go_*` row fields, `target_kind`, opt-in `go_include_ancestors`, `rows_by_go_term_depth`).
- `chebi.role:` inputs reaching GO and TCDB role edges; filtered-target and neurotransmitter warnings.
- `gene_overview` (`evidence_sources`, `has_chemistry`) and `list_metabolites` (organism union with `go_transport_organism_*`).
- `kg_release_info.go_transport_excluded_targets`, `kg_schema` edge descriptions, `docs://analysis/transport`.

The KG release carrying slice 1 should set `mcp_min_version` to that explorer release.

Correction: the note above that adding `go_transport` "moves the hash" is wrong. The `controlled_vocabularies_hash` recipe does not hash descriptions and `Metabolite.evidence_sources` is an open vocabulary, so the hash did not move at 2026-10-18T18:40Z (recorded in the explorer CHANGELOG).
