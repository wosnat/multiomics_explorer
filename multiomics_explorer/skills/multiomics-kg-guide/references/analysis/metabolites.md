# Working with metabolites

Read before any metabolite question: which pipeline answers it, then the drill. The KG models metabolites via three distinct source pipelines (metabolism, transport, metabolomics), each answering a different question class; transport evidence has two routes, TCDB `transport` and GO `go_transport`. **Find the question in the decision tree, check its row in the source table, then drill.**

Companion pages: `docs://analysis/transport` (reading TCDB and GO transport rows, empty answers, route agreement) and `docs://analysis/metabolite_ids` (id forms, stereo forms, compound classes).

Runnable companion: `docs://examples/metabolites.py` (7 scenarios).

> **Counts and per-gene distributions below are an illustrative snapshot** and
> drift with each KG rebuild. Use them for rough scale only; call
> `list_metabolites`, `list_metabolite_assays`, or `kg_release_info` for current
> figures.

## Quick decision tree

```
User asks about a metabolite or chemistry
├─ "Can / does gene X act on metabolite M?"
│   ├─ "produce / catalyse" → Track A1 b1/c1 (metabolism arm)
│   └─ "transport" → Track A2 b2/c2 (transport arm) + docs://analysis/transport (direct vs family rows)
├─ "Which genes act on M?" → genes_by_metabolite (read evidence_source split)
├─ "M shows transport only / 0 catalysts" → read stereo_relatives; genes_by_metabolite(include_stereo_forms=True) for transport ↔ catalysis joins (docs://analysis/metabolite_ids)
├─ "Which metabolites does gene X act on?" → metabolites_by_gene
├─ "Id lands in not_found / resolved to another id" → docs://analysis/metabolite_ids
├─ "Find metabolite by name → metabolite_id" → list_metabolites(search_text="...")  ← name-search hook; precedes any compound-anchored chain
├─ "Find metabolites by element / pathway / mass" → list_metabolites
├─ "Which metabolites are lipids / sugars / vitamins?" → list_metabolites(kegg_functional_categories=… / kegg_brite_classes=…) — partial, see docs://analysis/metabolite_ids
├─ "Which genes transport siderophores / vitamins (a chemical role)?" → genes_by_metabolite(metabolite_ids=['chebi.role:…']); run_cypher only for which TCDB systems carry a role (Track A f — Chemical roles)
├─ "GO vs TCDB transport, which routes agree, empty transport answer" → docs://analysis/transport
├─ "Cross-feeding between organisms" → Track A d — Cross-feeding bridge
├─ "N-source / chemistry-filtered DE" → Track A e — N-source / nutrient-class workflow
├─ "Genes that transport substrate X" → Track A2 b2 (metabolite-anchored; see also Track A f — Ontology bridges)
├─ "Genes annotated to TCDB family / KEGG term" → genes_by_ontology
├─ "What metabolomics assays exist for treatment / paper / organism?" → list_metabolite_assays  (Track B discovery)
├─ "Was metabolite M measured? At what level?" → assays_by_metabolite (cross-organism reverse lookup)
├─ "Top-N / detected-only metabolites in this numeric assay?" → metabolites_by_quantifies_assay
├─ "Which metabolites were flagged present/absent in this paper's S2 table?" → metabolites_by_flags_assay
└─ "value = 0 / not_detected / flag_value = false rows" → keep them: Track B "Tested-absent vs unmeasured"
```

## Source disambiguation

| `evidence_source` | Path in KG | Question it answers | Native tools | Key caveats |
|---|---|---|---|---|
| `metabolism` | `Gene → Reaction → Metabolite` (KEGG-derived) | "Which metabolites is this gene's reaction involved in?" | `genes_by_metabolite`, `metabolites_by_gene` (with `evidence_sources=['metabolism']`) | KO inference may be putative; `Reaction_has_metabolite` is undirected — upstream KEGG direction is unreliable, so the convention is permanent: use "involved in" framing, never "produces"/"consumes"; promiscuous enzymes inflate counts |
| `transport` | `Gene → TcdbFamily (tc_system) → Metabolite` (TCDB-derived; a gene's `transport` tag also counts systems curated only with chemical roles, e.g. 'drug') | "Which metabolites does this gene transport, through a TCDB system it is directly assigned to?" | `genes_by_metabolite`, `metabolites_by_gene` (with `evidence_sources=['transport']`) | Default rows need a `direct` system call; genes TCDB placed only at family or subfamily level need `include_tcdb_family_substrates=True` (family rows, a recall expansion); TCDB curation can be narrow (Pst → triphosphate only); direction is node-level (`tcdb_direction`), not per gene |
| `go_transport` | `Gene → GO term → Metabolite / ChemicalRole` (GO term's primary input) | "Does a GO term this gene carries define it as moving the compound?" | `genes_by_metabolite`, `metabolites_by_gene` (with `evidence_sources=['go_transport']`); `list_metabolites(evidence_sources=['go_transport'])` | A term definition, not a gene fact; molecular-function and biological-process terms mean different things; kept apart from TCDB (`organism_count`, `transporter_gene_count`, `catalyst_gene_count` ignore it); GO rows carry `go_term_id`, `go_namespace`, `go_evidence`, `go_term_depth`, `target_kind`. How to read it: `docs://analysis/transport` |
| `metabolomics` | `MetaboliteAssay → Metabolite` (mass-spec) | "Which metabolites were measured under this condition?" | `list_metabolite_assays` (discovery), `metabolites_by_quantifies_assay` / `metabolites_by_flags_assay` (per-arm drill-down), `assays_by_metabolite` (reverse lookup) — see Track B | No gene anchor; `Assay_quantifies` (concentration/intensity) ≠ `Assay_flags` (qualitative detection); compartment matters (`whole_cell` / `extracellular` / `vesicle`); a targeted panel — only a small fraction of KG metabolites is measured at all; replicate / normalisation conventions vary by paper |

The `metabolism`, `transport` and `go_transport` rows share tools — the `evidence_source` field on result rows is the discriminator, and `tcdb_route ∈ {direct, family}`, `tcdb_identity` and `tcdb_calls` further qualify transport rows (see `docs://analysis/transport`). The `metabolomics` row has dedicated tools — see Track B.

The `Metabolite.evidence_sources` list field on each Metabolite node already indicates which routes contribute (e.g., `['metabolism', 'transport', 'go_transport', 'metabolomics']`); read this to route quickly. It is metabolite-level: `transport` means some TCDB system lists the compound, not that any given organism reaches it. For one organism's reach by a route, pass both filters: `list_metabolites(organism_names=[...], evidence_sources=['transport'])` keeps only compounds the listed organism's own genes reach by that route.

**Ids, stereo forms and compound classes** live on their own page, `docs://analysis/metabolite_ids`: any id form resolves (`resolved_aliases`), a compound's stereo forms are separate nodes whose counts never combine (Cysteine vs L-Cysteine), and `structure_kind` / KEGG compound categories tell classes from molecules. Read it when an id lands in `not_found`, a `stereo_relatives` hint or "Stereo forms hold more rows" warning appears, or a row is a class such as 'Amino acid'.

**One row schema across the three arms.** `genes_by_metabolite` and `metabolites_by_gene` rows from all three arms share one schema. Fields that belong to another arm are `None`: `tcdb_*` on KEGG and GO rows; `reaction_*`, `ec_numbers` and `mass_balance` on TCDB and GO rows; `go_*` on KEGG and TCDB rows. Every row carries `evidence_source` and `metabolite_structure_kind` (`defined` / `generic` / `polymer`; null on role targets). Null optional fields (`gene_name`; formula / mass / chebi on role rows) can be left out of a row entirely, so read them with `row.get(...)`. Branch on `evidence_source`.

## When to surface caveats inline

Always restate the row's caveats when the answer touches it. The LLM should never claim:

- "This gene produces X" — only "this gene catalyses a reaction involving X". This is the permanent convention: upstream KEGG annotation direction is unreliable, so the KG intentionally stays undirected.
- "This gene transports X" from a family row — a `tcdb_route='family'` row means the gene's TCDB family or subfamily has some system curated with X; the annotation can't pin the system. Say "this gene belongs to a TCDB family that includes a system moving X, so X is candidate-only". Quote `tcdb_identity` and `tcdb_calls` when you rank candidates; even a direct row is a homology call, not a measured activity.
- "No gene in this organism acts on X" from a `0` on one stereo form — a generic node (Cysteine) has 0 reactions by construction and the catalysts sit on the specific form (L-Cysteine). Read `stereo_relatives` first (`docs://analysis/metabolite_ids`).
- "Metabolite X was not produced under condition Y" based on metabolomics absence — say "X was not detected in the targeted panel under condition Y" (targeted ≠ comprehensive).

---

## Track A1 — Reaction (KEGG) annotation

For the chemistry the gene's reaction is involved in via curated KEGG annotations. Always restate inline: KO inference may be putative; reaction direction is **permanently undirected** in this KG (upstream KEGG direction is unreliable); promiscuous enzymes inflate counts. Reversibility is also not encoded on `Reaction` nodes — KEGG lacks an `is_reversible` flag upstream, so the KG carries no direction *and* no reversibility on reactions (permanently unmitigable).

### Distinguishing reaction direction

KEGG reactions are stored in the KG **without substrate-vs-product
direction** — KEGG equation order is unreliable upstream, so we do not
encode it. Joins through `Reaction_has_metabolite` return both produced
and consumed metabolites identically. TCDB rows carry only a node-level
`tcdb_direction` hint (`uptake` / `export` / `unknown`, stated by TCDB),
not a per-gene direction.

To distinguish directionality, layer:

- **DE direction** (`differential_expression_by_gene` `direction='up'`
  vs `'down'`) — transcriptional response under treatment.
- **Functional annotation** (`gene_overview` Pfam/KO labels —
  `*-synthase` vs `*-permease`, `*-dehydrogenase` vs
  `*-hydratase`) — text-level disambiguation.

### a — Metabolite discovery & filtering

**Tool:** `list_metabolites`.

**When:** "what metabolites does the KG know about, filtered by element / mass / pathway / xref / organism" — discovery before downstream drill-down.

```python
result = list_metabolites(
    elements=["N"],                  # presence-only AND-of (here: N-bearing)
    pathway_ids=["map00910"],        # nitrogen metabolism
    organism_names=["Prochlorococcus MED4"],
    limit=20,
)
# Read result["top_metabolite_pathways"], result["top_organisms"], result["xref_coverage"],
# result["mass_stats"], result["by_evidence_source"].
```

The envelope `by_evidence_source` already breaks down by metabolism / transport / metabolomics — useful for routing.

### b1 — Reaction-anchored: compound → genes

**Tool:** `genes_by_metabolite` filtered to `evidence_sources=['metabolism']`.

**When:** "which MED4 genes catalyse a reaction involving glucose?"

```python
result = genes_by_metabolite(
    metabolite_ids=["C00031"],            # glucose — bare KEGG ID, coerced to kegg.compound:C00031
    organism="MED4",
    evidence_sources=["metabolism"],
)
# Each row has evidence_source="metabolism", an EC number, a reaction_id.
```

### c1 — Reaction-anchored: gene → metabolites

**Tool:** `metabolites_by_gene` filtered to `evidence_sources=['metabolism']`.

**When:** "which metabolites does PMM0001 catalyse reactions involving?"

```python
result = metabolites_by_gene(
    locus_tags=["PMM0001"],
    organism="MED4",
    evidence_sources=["metabolism"],
)
# Read result["by_element"] (chemistry signature) and result["top_metabolite_pathways"]
# (chemistry-pathway distinction — see caveat below).
```

**`by_element` semantics — presence-only, not stoichiometric.** Each row carries `metabolite_count` = the count of *distinct compounds in the full match set* that contain that element at all. E.g., `[('H', 6), ('O', 6), ('P', 6), ('C', 5), ('N', 4)]` over 6 distinct compounds means 6 contain H/O/P, 5 contain C, 4 contain N. It does **not** count atoms per compound (stoichiometry lives in `metabolite.formula`, e.g. `HO7P2` for diphosphate), and it is **not** mass-balanced across reactions — the KG intentionally carries no substrate-vs-product role on `Reaction_has_metabolite`. The per-row `elements` field is the same shape: a set of symbols, no counts. The envelope aggregates over `total_matching`, not the truncated page.

**Caveat — element filters skip formula-less metabolites.** `elements` / `metabolite_elements` never match a metabolite with no formula (mostly generic classes such as "amino acid", "dipeptide", "Polyamine"). When the filter is set, the envelope reports what it dropped (`no_formula_excluded`, plus `no_formula_excluded_metabolites` on `metabolites_by_gene`) and adds a `warnings` entry. Re-run without the element filter to inspect them.

**Caveat — `top_metabolite_pathways` is metabolite-anchored, NOT KO-anchored.** The chemistry-side `top_metabolite_pathways` traverses `Metabolite → KeggTerm` via the denormalized `m.pathway_ids` field (sourced from `Metabolite_in_pathway` edges). Target pathways are filtered by `KeggTerm.reaction_count >= 3` to drop signaling/disease pathways with no chemistry breadth — that's a *gate* on the target node, not part of the traversal. So this rollup answers **"which pathways do my gene's metabolites participate in?"** The envelope key is **`top_metabolite_pathways`** with per-element keys `metabolite_pathway_id` / `metabolite_pathway_name`, distinct from **ko-pathway** annotations (anchored on `Gene → KeggTerm` via the KO hierarchy, surfaced by `genes_by_ontology(ontology="kegg", ...)`, `pathway_enrichment`, etc.). They reach the same KEGG pathway maps but via different membership relations. Disambiguate explicitly when answering.

---

## Track A2 — Transport (TCDB) annotation

For substrates of the TCDB systems a gene is assigned to. Always restate inline: direct or family row, `tcdb_identity`, and that direction (`tcdb_direction`) is TCDB's statement about the node, not a per-gene fact.

### b2 — Transport-anchored: compound → genes

**Tool:** `genes_by_metabolite` filtered to `evidence_sources=['transport']`.

**When:** "which MED4 genes are predicted to transport nitrite?"

```python
result = genes_by_metabolite(
    metabolite_ids=["kegg.compound:C00088"],   # nitrite
    organism="MED4",
    evidence_sources=["transport"],
)
# Direct rows only by default: cynA / cynB / cynD on tcdb:3.A.1.16.1 / 3.A.1.16.2.
# Each row: tcdb_route="direct", tcdb_family_id = the system, tcdb_identity, tcdb_calls.
# result["tcdb_family_substrates_not_shown"] says what include_tcdb_family_substrates=True would add.
```

### c2 — Transport-anchored: gene → metabolites

**Tool:** `metabolites_by_gene` filtered to `evidence_sources=['transport']`.

**When:** "what does this gene's TCDB system transport?"

```python
result = metabolites_by_gene(
    locus_tags=["PMM0372"],                    # cynD
    organism="MED4",
    evidence_sources=["transport"],
)
# Two direct systems: tcdb:3.A.1.16.2 (cyanate, nitrite) and tcdb:3.A.1.16.1 (nitrate, nitrite).
# result["by_gene"][0]: tcdb_direct_rows, tcdb_family_rows, tcdb_assignment_count (2).
```

### Direct vs family rows

Default transport rows come only from TCDB systems a gene is directly assigned to. Genes TCDB placed only at family or subfamily level have no rows unless you pass `include_tcdb_family_substrates=True`, which adds `tcdb_route='family'` candidate rows. Read `tcdb_family_substrates_not_shown` before calling the transport arm empty. Row semantics, the phnD and Pst examples, the 200-substrate breadth cap, catch-all substrates and what an empty answer means: `docs://analysis/transport`.

---

## Track A — Combined annotation workflows

Workflows that cross both reaction and transport arms, or that consume the annotation-side results downstream.

### d — Cross-feeding bridge

**When:** "what could MED4 produce that ALT might consume?" — between-organism metabolic coupling.

**Three structural confounders — apply mitigations or the bridge degenerates to "both organisms have water and ATP":**

| # | Confounder | Arm | Mitigation |
|---|---|---|---|
| 1 | **Currency cofactors flood the rollup.** `top_metabolites` is sorted by gene_count, which is exactly the wrong sort for cross-feeding because the highest-reach metabolites are universal (H2O, ATP/ADP/AMP, Pi, PPi, NAD(P)(H), CO2). | metabolism | Pass `exclude_metabolite_ids=CURRENCY_METABOLITES_MIN8` directly on the next call (tool-side filter — pushes the mitigation into the query so envelope rollups also benefit; available on `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`). Minimal-8 (H2O, CO2, ATP, ADP, AMP, Pi, PPi, NAD(P)(H)) is the conservative default — see `examples/metabolites.py::CURRENCY_METABOLITES_MIN8`. Extend with H+, Glu/Gln, CoA, FAD if the seed pulls them in (these are borderline and depend on whether you care about central-N flux as a signal). Set-difference semantics with `metabolite_ids` — exclude wins on overlap. |
| 2 | **Family-level transport casts a wide net.** Family rows (`include_tcdb_family_substrates=True`) reflect a family's whole curated range, not a per-gene substrate. For cross-feeding *inferences* (which over-claim a specific substrate flowing between organisms), keep the default direct rows. | transport | Leave `include_tcdb_family_substrates` off on the Step-2 `genes_by_metabolite` call; rank the direct rows by `tcdb_identity`, then `tcdb_calls`. **Note:** for *broad-screen* questions (e.g. "which transporters could plausibly act on N?", scenario `n_source_de`) the opposite call applies — turn the walk on so family-level candidates are included. |
| 3 | **Transport polarity is node-level at best.** TCDB rows carry `tcdb_direction` (`uptake` / `export` / `unknown`), read from TCDB's numbering or names for the node, not measured per gene, and most nodes read `unknown`. KEGG reactions are undirected. Even with clean filters, "MED4 has cynA, ALT has nrtA" tells you both touch the substrate, not who's the producer. | both | Use `tcdb_direction` as a hint only and surface the limitation in the answer ("compatible with", not "confirmed"). The Track-B measurement layer can corroborate (extracellular elevation in coculture) but cannot confirm causality. |

**Pattern (two-step, with all three mitigations applied):**

```python
# 0. Derive a biologically-motivated seed (don't pick random PMM IDs — housekeeping
#    genes carry only currency cofactors and zero transport).
CURRENCY = [  # minimal-8 (H2O, CO2, ATP, ADP, AMP, Pi, PPi, NAD(P)(H))
    "kegg.compound:C00001", "kegg.compound:C00011", "kegg.compound:C00002",
    "kegg.compound:C00008", "kegg.compound:C00020", "kegg.compound:C00009",
    "kegg.compound:C00013", "kegg.compound:C00003", "kegg.compound:C00004",
    "kegg.compound:C00005", "kegg.compound:C00006",
]
seed = genes_by_ontology(
    organism="MED4",
    ontology="kegg",
    term_ids=["kegg.pathway:ko00910"],   # Nitrogen metabolism — both arms exercised
)
seed_locus_tags = sorted({r["locus_tag"] for r in seed["results"]})

# 1. Harvest MED4-side metabolite IDs from gene-anchored chemistry. Apply
#    confounder #1 mitigation at the tool level via `exclude_metabolite_ids`
#    so the envelope's `top_metabolites` rollup itself is currency-free
#    (tool-side set-difference; exclude wins on overlap).
med4_chem = metabolites_by_gene(
    locus_tags=seed_locus_tags,
    organism="MED4",
    exclude_metabolite_ids=CURRENCY,                     # confounder #1 — tool-side
    summary=True,
)
metabolite_ids = [m["metabolite_id"] for m in med4_chem["top_metabolites"]]

# 2. Cross to ALT — split per-arm so both have airtime; the transport side keeps
#    direct TCDB rows only (the default). Pass `exclude_metabolite_ids`
#    again as a belt-and-braces guard (cross-organism enrichment can re-introduce
#    currency hits — exclude is harmless if the input is already clean).
alt_transport = genes_by_metabolite(
    metabolite_ids=metabolite_ids,
    organism="Alteromonas macleodii HOT1A3",   # one strain, not the species — keeps locus tags consistent and cuts cross-strain duplicate rows
    evidence_sources=["transport"],
    # confounder #2: include_tcdb_family_substrates stays False (direct rows only)
    exclude_metabolite_ids=CURRENCY,
)
alt_metab = genes_by_metabolite(
    metabolite_ids=metabolite_ids,
    organism="Alteromonas macleodii HOT1A3",   # one strain, not the species — keeps locus tags consistent and cuts cross-strain duplicate rows
    evidence_sources=["metabolism"],
    exclude_metabolite_ids=CURRENCY,
)
# Frame results as "compatible with cross-feeding" — confounder #3 is unmitigable.
```

See `examples/metabolites.py --scenario cross_feeding` for the runnable end-to-end with both arms printed and the cyn-cluster + glnA + glsF seed.

### e — N-source / nutrient-class workflow

**When:** "which MED4 genes act on nitrogen-containing metabolites — and which of those respond to N starvation?"

```python
# 1. N-bearing chemistry-side gene set.
chem = metabolites_by_gene(
    locus_tags=[...candidate pool...],
    organism="MED4",
    metabolite_elements=["N"],          # presence-only AND-of
    summary=True,
)
locus_tags = [g["locus_tag"] for g in chem["by_gene"]]

# 2. DE under N starvation.
de = differential_expression_by_gene(
    organism="MED4",
    locus_tags=locus_tags,
    direction="both",
    significant_only=True,
)
```

**Caveat — promiscuous enzymes and family-level transport substrates inflate the gene set fed to DE.** Tighten via `evidence_sources=['metabolism']`, or leave `include_tcdb_family_substrates` off, if results are noisy; `by_gene[].tcdb_direct_rows` / `tcdb_family_rows` tell you which genes contribute only family-level reach. Symmetric primitives exist for `metabolite_elements=['P']`, `['S']`, `['Fe']`, etc.

### f — Ontology bridges

**TCDB substrate-anchored:** for "which genes transport substrate X?", prefer the metabolite-anchored route (`genes_by_metabolite(metabolite_ids=[...], evidence_sources=['transport'])`) over the family-anchored route (`genes_by_ontology(ontology='tcdb', ...)`). The metabolite-anchored route includes all families curating the substrate; the ontology route is family-anchored and misses cross-family substrate hits.

**TCDB family-anchored context:** to see what a family *is* before trusting its substrate set — its level (class / subclass / family / subfamily), parents and children, `member_count` vs `gene_count`, and the Pfam domains / GO terms it is built from (`links_out`, composition) — use `ontology_term_details(term_ids=['tcdb:3.A.1'])`. Browse families by size with `search_ontology(ontology=['tcdb'], level=2)`. The full TCDB reference (identifier form, the `tcdb_gate` / `tcdb_call` edge model, `direction`, `tcdb_substrate_count`, pitfalls) is `docs://ontologies/tcdb`; the other ontologies are indexed at `docs://ontologies/index`.

**Chemical roles (siderophores, vitamins, antibiotics):** role terms are `ChemicalRole` nodes
(`chebi.role:<n>`), not metabolites, so `list_metabolites` does not return them. A role id is a
valid input to `genes_by_metabolite` and `metabolites_by_gene`, which return TCDB and GO role
rows (`target_kind='chemical_role'`). TCDB curates some substrates only as a role
("siderophore"); to see which systems carry a role and its narrower roles, use `run_cypher`:

```cypher
CALL db.index.fulltext.queryNodes('chemicalRoleFullText', 'siderophore')
YIELD node AS role, score
WITH role ORDER BY score DESC LIMIT 1
MATCH (sub:ChemicalRole)-[:Chemical_role_is_a_chemical_role*0..]->(role)
MATCH (s:TcdbFamily {level_kind: 'tc_system'})-[:Tcdb_family_transports_chemical_role]->(sub)
RETURN role.id AS role_id, s.id AS tcdb_system_id, s.name AS tcdb_system_name,
       s.gene_count AS gene_count, collect(DISTINCT sub.name) AS via_roles
ORDER BY gene_count DESC, tcdb_system_id
```

`*0..` includes the role itself plus its narrower roles. Substrate edges leave systems only, and
most systems carry no genes (`gene_count = 0`: TCDB's range, not this KG's genomes). For the genes,
call `genes_by_metabolite(metabolite_ids=[role_id], organism=...)`.

**KEGG pathway-anchored — pick the right surface:**
- **metabolite_pathways** (compound-anchored): which metabolites are in pathway X → `list_metabolites(pathway_ids=[...])`. Edge: `Metabolite_in_pathway`.
- **ko_pathways** (gene-KO-anchored): which genes are annotated to KOs in pathway X → `genes_by_ontology(ontology='kegg', ...)`. Edges: `Gene_has_kegg_ko` + `Kegg_term_is_a_kegg_term`.
- **reaction_pathways** (reaction-anchored, not currently surfaced as a rollup): which reactions a gene catalyses map to pathway X. Reach via `run_cypher` over `Gene_catalyzes_reaction` + `Reaction_in_kegg_pathway`.

The same KEGG pathway map (e.g. `kegg.pathway:ko00910` Nitrogen metabolism) can be reached from all three anchors, but membership relations are different — a gene whose KO is in pathway X may not catalyse any reaction whose metabolites are in pathway X (and vice versa). Always name the anchor when answering.

---

## Track B — Metabolomics measurement

Four native tools cover the measurement layer (no `run_cypher` needed):

- **`list_metabolite_assays`** — discovery surface. Inspect `value_kind` (numeric/boolean → routes drill-down), `rankable` (gates `metric_bucket` / `min_percentile` / `max_percentile` / `max_rank` on the numeric drill-down), `compartment`, and per-row `detection_status_counts` (numeric assays) before drilling.
- **`metabolites_by_quantifies_assay`** — numeric-arm drill-down. One row per (metabolite × assay-edge) with `value`, `detection_status`, `timepoint*` and rankable-gated `metric_bucket` / `metric_percentile` / `rank_by_metric`. `by_detection_status` is the primary headline.
- **`metabolites_by_flags_assay`** — boolean-arm drill-down. Edge filter `flag_value` (`True` = presence flagged, `False` = tested-absent — real biology, most boolean rows).
- **`assays_by_metabolite`** — polymorphic reverse lookup. Cross-organism by default. Numeric rows carry `value` / `detection_status` / `timepoint*`; boolean rows carry `flag_value` / `n_positive`. Cross-arm fields explicit `None` (union-shape padding).

### Caveats — always restate when surfacing measurement results

- **No gene anchor.** A metabolite measurement says nothing about which gene produced/consumed it.
- **`Assay_quantifies` vs `Assay_flags`.** Quantifies = concentration/intensity (with `value`, `value_sd`, `n_replicates`, `metric_percentile`, `rank_by_metric`); Flags = qualitative detection (with `flag_value`, `n_positive`, `n_replicates`). Their downstream interpretation differs — split per DM convention into two drill-down tools.
- **Compartment matters.** `whole_cell` measures pool; `extracellular` measures excretion / uptake / spent media; `vesicle` measures cargo packaged into extracellular vesicles. Filter via the `compartment=` kwarg on every Track-B tool.
- **Targeted panel ≠ full metabolome.** Absence in measurement ≠ absence in cell. Only a small fraction of KG metabolites has any measurement; `list_metabolites(summary=True)` `by_measurement_coverage` gives the live split, `list_metabolite_assays(summary=True)` the assays and papers.
- **Stereo form may be the KG's call, not the paper's.** Every measurement row carries
  `stereo_assignment`: `as_reported` (the paper named the form, or the compound has no stereo
  variant) or `dominant_form_assumed` (the paper gave no form — e.g. 'Alanine' — and the KG
  placed the row on one form of the stereo family, usually the one with the most catalysing
  genes, here L-alanine `kegg.compound:C00041`). The drill-downs add `by_stereo_assignment` to the envelope and a
  `warnings` entry when assumed rows are present; pass `stereo_assignment=['as_reported']` to
  keep only the paper's own calls. Say "measured as alanine (L-form assumed)" when quoting an
  assumed row. Transport for the same compound usually sits on the generic node (Alanine
  `kegg.compound:C01401`): see `docs://analysis/metabolite_ids`.
- **Replicate / normalisation conventions vary by paper.** Read `value_sd` and `n_replicates` on the edge, plus `field_description` on the parent assay (canonical provenance read — `verbose=True` surfaces it). The `value` itself is processed per the paper's pipeline.
- **Tested-absent vs unmeasured.** See "Tested-absent vs unmeasured" below — the top-level invariant. Tested-absent rows (`value=0` / `detection_status='not_detected'` / `flag_value=false`) are biology, not noise; default-filtering them strips the majority of the layer.

### Tested-absent vs unmeasured

> **Top-level invariant for the metabolomics layer**, shared by the 4 metabolomics tools (`list_metabolite_assays`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite`). It determines how every row of every drill-down output is read.

In metabolomics, **two row states must not be conflated**:

| State | Numeric arm | Boolean arm | What it means |
|---|---|---|---|
| Measured-present | `value > 0` and/or `detection_status ∈ {detected, sporadic}` | `flag_value = true` | Metabolite assayed and found. |
| **Tested-absent** | `value = 0`, `n_non_zero = 0`, `detection_status = 'not_detected'` | `flag_value = false` | Metabolite *assayed and not found*. **Real biological data — keep in `results`, count toward `total_matching` and envelope rollups.** |
| **Unmeasured** | no row in result; `metabolite_id` in `not_found` / `not_matched` | no row in result | Metabolite *not in this assay's scope*. **No information — do not infer absence.** |

Tested-absent rows answer the biological question "is X actually absent under condition Y". Discarding them silently misreads the question. Unmeasured rows carry zero information either way.

**Tested-absent is the majority, not the exception.** Most numeric edges are `not_detected` and most boolean flags are `false`; read `by_detection_status` (`list_metabolite_assays`, `metabolites_by_quantifies_assay`) or `by_value` (`metabolites_by_flags_assay`) for the live split before drilling. Default-filtering tested-absent rows would discard most of the measured biology.

On the numeric arm (`metabolites_by_quantifies_assay` and the quantifies rows of `assays_by_metabolite`), a tested-absent row's `metric_bucket` / `metric_percentile` / `rank_by_metric` are always null — a raw-zero value could otherwise tie into a high bucket because most of the assay's edges are zero — and the rank-gated filters (`metric_bucket`, `min_percentile` / `max_percentile`, `max_rank`) never select `not_detected` rows.

| Surface | Behavior |
|---|---|
| `total_matching` | Counts measured rows = present + tested-absent. Excludes unmeasured (no row exists to count). |
| `results` (default) | Includes tested-absent rows. |
| Envelope rollups (`by_detection_status`, `by_value`, `by_flag_value`, `by_assay`, `by_compartment`, `by_organism`, `by_metric`) | Include tested-absent rows, so you can see how much of `total_matching` is biological absence. |
| Edge-level filters (`min_value > 0`, `detection_status` list excluding `not_detected`, `flag_value=True`) | Caller's choice, never on by default. Each one drops tested-absent rows when set; `flag_value=False` asks for them explicitly. |
| `assays_by_metabolite` `not_found` / `not_matched` | **Unmeasured only.** Tested-absent rows for in-scope metabolites are in `results`. |

### Discovery

```python
# 1. Inventory all metabolomics assays (mirrors list_derived_metrics — call first).
assays = list_metabolite_assays(summary=True)
# Read assays['by_value_kind'] (numeric vs boolean — picks the drill-down tool),
# assays['by_compartment'] (whole_cell / extracellular / vesicle),
# assays['by_treatment_type'], assays['by_detection_status']
# (cross-assay rollup for the numeric arm — primary headline).

# 2. Narrow by treatment / paper / organism.
p_assays = list_metabolite_assays(treatment_type=["phosphorus"], rankable=True)
# Dropping rankable=True also returns the boolean assays, which are
# non-rankable and land in excluded_assays if you pass rankable-gated
# filters with mixed input.
```

### Assay → metabolite drill-down

```python
# Numeric arm — pick assay_ids from list_metabolite_assays(value_kind='numeric').
result = metabolites_by_quantifies_assay(
    assay_ids=["metabolite_assay:msystems.01261-22:metabolites_kegg_export_9301_intracellular:cellular_concentration"],
    detection_status=["detected", "sporadic"],   # opt-out of tested-absent for a 'present-only' slice
    limit=20,
)
# Each row: metabolite_id, name, value, value_sd, detection_status,
# timepoint*, plus rankable-gated metric_bucket / metric_percentile / rank_by_metric.
# Envelope: by_detection_status (primary headline), by_metric (filtered slice +
# full-assay range echo), by_metric_bucket (rankable subset), by_assay.

# Top-decile drill on a rankable assay:
top_decile = metabolites_by_quantifies_assay(
    assay_ids=[<rankable_numeric_assay_id>],
    metric_bucket=["top_decile"],         # rankable-gated — raises if none of the assay set is rankable
    max_rank=10,                          # top-10 by rank_by_metric
)

# Boolean arm — pick assay_ids from list_metabolite_assays(value_kind='boolean').
flags = metabolites_by_flags_assay(
    assay_ids=["metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular"],
    flag_value=False,                     # tested-absent slice (real biology — most boolean rows)
    limit=20,
)
# Each row: metabolite_id, name, flag_value, n_positive, n_replicates,
# metric_type, condition_label, assay_id.
```

### Metabolite → assay reverse lookup

```python
# Polymorphic — both arms merged via UNION ALL. Cross-organism by default.
result = assays_by_metabolite(
    metabolite_ids=["kegg.compound:C00064"],   # glutamine; ['kegg.compound:C00074'] is PEP
    limit=20,
)
# Numeric rows carry value / detection_status / timepoint*; boolean rows carry
# flag_value / n_positive. Cross-arm fields are explicit None.
# Envelope: by_evidence_kind (quantifies vs flags split), by_detection_status,
# by_flag_value, by_assay, by_organism, by_compartment.
# Three states per metabolite:
#   1. id in `not_found`      → not in KG (unmeasured)
#   2. id in `not_matched`    → in KG, no edge after filters (unmeasured for this scope)
#   3. row in `results` with `value=0` / `flag_value=false` → tested-absent (real biology)

# Scope to one arm if needed:
quantifies_only = assays_by_metabolite(
    metabolite_ids=["kegg.compound:C00064"],
    evidence_kind="quantifies",            # filtered-out arm's envelope rollup is empty
)
# `metabolites_matched` (distinct metabolite count) is the right field — NOT total_matching, which is row count.
```

For numeric details on a specific assay × metabolite combo, drill back via `metabolites_by_quantifies_assay(assay_ids=[...], metabolite_ids=[...])`.

### Cross-omics anchoring

When the user asks "did P stress change metabolite X (and which P-acting genes responded)?", combine:

```python
# 1. Metabolomics evidence — pick relevant assays then drill numeric values.
p_assays = list_metabolite_assays(treatment_type=["phosphorus"], value_kind="numeric")
mvals = metabolites_by_quantifies_assay(
    assay_ids=[a["assay_id"] for a in p_assays["results"]],
    metabolite_ids=["kegg.compound:C00074"],   # PEP, for example
    detection_status=["detected", "sporadic"],
)

# 2. Expression evidence — which P-acting genes responded under N starvation
#    (or P-stress). Follow the chemistry-filtered DE pattern in Track A e
#    (metabolites_by_gene metabolite_elements=['P'] → differential_expression_by_gene).

# 3. Surface both with their caveats; do not conflate "metabolite changed" with
#    "metabolite caused effect" or vice versa.
```

Time-point alignment between metabolomics and expression assays still varies by paper — confirm experiment `id` matches before joining (the current KG has no nitrogen-stress metabolomics experiments, so the canonical N-DE workflow can't be mirrored on the metabolite side; phosphorus and carbon are the available stress-treatment cross-omics pairings).
