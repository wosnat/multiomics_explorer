# Working with metabolites

LLM-facing decision-tree guide for metabolite questions. The KG models metabolites via three distinct source pipelines, each answering a different question class. **Read the disambiguation table first; pick the right row before drilling.**

Runnable companion: `docs://examples/metabolites.py` (8 scenarios).

## Source disambiguation

| `evidence_source` | Path in KG | Question it answers | Native tools | Key caveats |
|---|---|---|---|---|
| `metabolism` | `Gene → Reaction → Metabolite` (KEGG-derived) | "Which metabolites is this gene's reaction involved in?" | `genes_by_metabolite`, `metabolites_by_gene` (with `evidence_sources=['metabolism']`) | KO inference may be putative; `Reaction_has_metabolite` is undirected — upstream KEGG direction is unreliable, so the convention is permanent: use "involved in" framing, never "produces"/"consumes"; promiscuous enzymes inflate counts |
| `transport` | `Gene → TcdbFamily → Metabolite` (TCDB-derived) | "Which metabolites does this gene transport (or could transport, family-inferred)?" | `genes_by_metabolite`, `metabolites_by_gene` (with `evidence_sources=['transport']`) | family_inferred ≫ substrate_confirmed (per-gene median = 6 metabolites, p90 = 90, max = 551 via ABC superfamily); auto-warning fires when this skews; no import/export direction |
| `metabolomics` | `MetaboliteAssay → Metabolite` (mass-spec) | "Which metabolites were measured under this condition?" | None native today — use `run_cypher` (see Track B) | No gene anchor; `Assay_quantifies` (concentration/intensity) ≠ `Assay_flags` (qualitative detection); compartment matters (whole_cell vs extracellular); 107 of 3035 metabolites measured (96% are annotation-only); 2 papers, 10 assays; replicate / normalisation conventions vary by paper |

The `metabolism` and `transport` rows share tools — the `evidence_source` field on result rows is the discriminator, and `transport_confidence ∈ {substrate_confirmed, family_inferred}` further qualifies transport rows. The `metabolomics` row has no native tool — see Track B.

The `Metabolite.evidence_sources` list field on each Metabolite node already indicates which of the three pipelines contribute (e.g., `['metabolism', 'transport', 'metabolomics']`); read this to route quickly.

## When to surface caveats inline

Always restate the row's caveats when the answer touches it. The LLM should never claim:

- "This gene produces X" — only "this gene catalyses a reaction involving X". This is the permanent convention: upstream KEGG annotation direction is unreliable, so the KG intentionally stays undirected (Part 4 §4.1.1 resolved 2026-05-04).
- "This gene transports X" without qualifying tier — say "this gene's TCDB family is curated as transporting X (family-inferred)" when `transport_confidence='family_inferred'`.
- "Metabolite X was not produced under condition Y" based on metabolomics absence — say "X was not detected in the targeted panel under condition Y" (targeted ≠ comprehensive).

---

## Track A1 — Reaction (KEGG) annotation

For the chemistry the gene's reaction is involved in via curated KEGG annotations. Always restate inline: KO inference may be putative; reaction direction is **permanently undirected** in this KG (upstream KEGG direction is unreliable); promiscuous enzymes inflate counts.

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
# Read result["top_pathways"], result["top_organisms"], result["xref_coverage"],
# result["mass_stats"], result["by_evidence_source"].
```

The envelope `by_evidence_source` already breaks down by metabolism / transport / metabolomics — useful for routing.

### b1 — Reaction-anchored: compound → genes

**Tool:** `genes_by_metabolite` filtered to `evidence_sources=['metabolism']`.

**When:** "which MED4 genes catalyse a reaction involving glucose?"

```python
result = genes_by_metabolite(
    metabolite_ids=["C00031"],            # glucose (KEGG)
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
# Read result["by_element"] (chemistry signature) and result["top_pathways"]
# (chemistry-pathway distinction — see caveat below).
```

**`by_element` semantics — presence-only, not stoichiometric.** Each row carries `metabolite_count` = the count of *distinct compounds in the full match set* that contain that element at all. E.g., `[('H', 6), ('O', 6), ('P', 6), ('C', 5), ('N', 4)]` over 6 distinct compounds means 6 contain H/O/P, 5 contain C, 4 contain N. It does **not** count atoms per compound (stoichiometry lives in `metabolite.formula`, e.g. `HO7P2` for diphosphate), and it is **not** mass-balanced across reactions — the KG intentionally carries no substrate-vs-product role on `Reaction_has_metabolite` (Part 4 §4.1.1 resolved). The per-row `elements` field is the same shape: a set of symbols, no counts. The envelope aggregates over `total_matching`, not the truncated page.

**Caveat — `top_pathways` is metabolite-anchored, NOT KO-anchored.** The chemistry-side `top_pathways` traverses `Metabolite → KeggTerm` via the denormalized `m.pathway_ids` field (sourced from `Metabolite_in_pathway` edges; KG-A5 rollup). Target pathways are filtered by `KeggTerm.reaction_count >= 3` to drop signaling/disease pathways with no chemistry breadth — that's a *gate* on the target node, not part of the traversal. So this rollup answers **"which pathways do my gene's metabolites participate in?"** Naming convention (Option A): treat this as **metabolite_pathways**, distinct from **ko_pathways** (anchored on `Gene → KeggTerm` via the KO hierarchy, surfaced by `genes_by_ontology(ontology="kegg", ...)`, `pathway_enrichment`, etc.). They reach the same KEGG pathway maps but via different membership relations. Disambiguate explicitly when answering.

---

## Track A2 — Transport (TCDB) annotation

For substrates the gene's TCDB family transports. Always restate inline: family_inferred ≫ substrate_confirmed; ABC superfamily promiscuity; no direction.

### b2 — Transport-anchored: compound → genes

**Tool:** `genes_by_metabolite` filtered to `evidence_sources=['transport']`.

**When:** "which MED4 genes are predicted to transport glycine betaine?"

```python
result = genes_by_metabolite(
    metabolite_ids=["C00719"],            # glycine betaine
    organism="MED4",
    evidence_sources=["transport"],
    transport_confidence="substrate_confirmed",  # tighten when family_inferred dominates
)
# Each row has evidence_source="transport" and transport_confidence ∈ {substrate_confirmed, family_inferred}.
```

### c2 — Transport-anchored: gene → metabolites

**Tool:** `metabolites_by_gene` filtered to `evidence_sources=['transport']`.

**When:** "what does this gene's TCDB family transport?"

```python
result = metabolites_by_gene(
    locus_tags=["PMM0001"],
    organism="MED4",
    evidence_sources=["transport"],
)
# Detail rows are sorted by precision tier — substrate_confirmed first, then family_inferred.
```

### g — Precision-tier reading

When `genes_by_metabolite` / `metabolites_by_gene` emit the family_inferred-dominance auto-warning, most rows came from broad family-level inheritance. Strategies:

- **Tighten** with `transport_confidence="substrate_confirmed"` to keep high-confidence rows only.
- **Read** the warning's named family — often ABC superfamily — and decide whether to filter it out (`tcdb_family_ids` exclusion in advanced cases).
- **Pivot** for a single transporter family: `genes_by_ontology(ontology="tcdb", term_ids=[...])`. (But for substrate-anchored questions — "which genes transport X" — prefer the metabolite-anchored route in §b2.)

Empirical scale (KG release 2026-05-05 post-TCDB-bug-fix): per-gene metabolite count via transport — median 4, p90 48, max **992**. In MED4 specifically, **12 genes** sit at the ABC-superfamily plateau (554 metabolites each): PMM0125, PMM0392, PMM0434, PMM0449, PMM0450, PMM0666, PMM0749, PMM0750, PMM0913, PMM0976, PMM0977, PMM0978. Expect family_inferred-dominance warnings when querying common metabolites against MED4.

---

## Track A — Combined annotation workflows

Workflows that cross both reaction and transport arms, or that consume the annotation-side results downstream.

### d — Cross-feeding bridge (Workflow B′)

**When:** "what could MED4 produce that ALT might consume?" — between-organism metabolic coupling.

**Three structural confounders — apply mitigations or the bridge degenerates to "both organisms have water and ATP":**

| # | Confounder | Arm | Mitigation |
|---|---|---|---|
| 1 | **Currency cofactors flood the rollup.** `top_metabolites` is sorted by gene_count, which is exactly the wrong sort for cross-feeding because the highest-reach metabolites are universal (H2O, ATP/ADP/AMP, Pi, PPi, NAD(P)(H), CO2). | metabolism | Post-filter the harvested IDs against a currency blacklist. Minimal-8 (H2O, CO2, ATP, ADP, AMP, Pi, PPi, NAD(P)(H)) is the conservative default — see `examples/metabolites.py::CURRENCY_METABOLITES_MIN8`. Extend with H+, Glu/Gln, CoA, FAD if the seed pulls them in (these are borderline and depend on whether you care about central-N flux as a signal). |
| 2 | **Family-inferred plateau.** Broad-substrate TCDB families (especially ABC superfamily) propagate ~554 metabolites per MED4 gene at low confidence. A single ABC-superfamily gene in the seed will swamp the metabolite_id list with weak transport rollups. | transport | `transport_confidence='substrate_confirmed'` on the Step-2 `genes_by_metabolite` call. Empirical: in a 7-metabolite N-cross test against ALT this dropped transport rows 1426 → 185 (87%), leaving only curated CmpA/NrtA-family nitrate transporters. |
| 3 | **Transport polarity not encoded.** TCDB annotation says "transports X" without import/export direction (KG-MET-011 open). Even with clean filters, "MED4 has cynA, ALT has nrtA" tells you both touch the substrate, not who's the producer. | both | None on the annotation side — surface the limitation in the answer ("compatible with", not "confirmed"). The Track-B measurement layer can corroborate (extracellular elevation in coculture) but cannot confirm causality. |

**Pattern (two-step, with all three mitigations applied):**

```python
# 0. Derive a biologically-motivated seed (don't pick random PMM IDs — housekeeping
#    genes carry only currency cofactors and zero transport).
CURRENCY = {  # minimal-8 (H2O, CO2, ATP, ADP, AMP, Pi, PPi, NAD(P)(H))
    "kegg.compound:C00001", "kegg.compound:C00011", "kegg.compound:C00002",
    "kegg.compound:C00008", "kegg.compound:C00020", "kegg.compound:C00009",
    "kegg.compound:C00013", "kegg.compound:C00003", "kegg.compound:C00004",
    "kegg.compound:C00005", "kegg.compound:C00006",
}
seed = genes_by_ontology(
    organism="MED4",
    ontology="kegg",
    term_ids=["kegg.pathway:ko00910"],   # Nitrogen metabolism — both arms exercised
)
seed_locus_tags = sorted({r["locus_tag"] for r in seed["results"]})

# 1. Harvest MED4-side metabolite IDs from gene-anchored chemistry.
med4_chem = metabolites_by_gene(
    locus_tags=seed_locus_tags,
    organism="MED4",
    summary=True,
)
metabolite_ids = [
    m["metabolite_id"]
    for m in med4_chem["top_metabolites"]
    if m["metabolite_id"] not in CURRENCY                # confounder #1
]

# 2. Cross to ALT — split per-arm so both have airtime and the family_inferred
#    plateau is killed on the transport side only.
alt_transport = genes_by_metabolite(
    metabolite_ids=metabolite_ids,
    organism="Alteromonas macleodii HOT1A3",   # one strain, not the species — keeps locus tags consistent and cuts cross-strain duplicate rows
    evidence_sources=["transport"],
    transport_confidence="substrate_confirmed",          # confounder #2
)
alt_metab = genes_by_metabolite(
    metabolite_ids=metabolite_ids,
    organism="Alteromonas macleodii HOT1A3",   # one strain, not the species — keeps locus tags consistent and cuts cross-strain duplicate rows
    evidence_sources=["metabolism"],
)
# Frame results as "compatible with cross-feeding" — confounder #3 unmitigable today.
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
locus_tags = [g["locus_tag"] for g in chem["top_genes"]]

# 2. DE under N starvation.
de = differential_expression_by_gene(
    organism="MED4",
    locus_tags=locus_tags,
    direction="both",
    significant_only=True,
)
```

**Caveat — promiscuous enzymes / family_inferred transport inflate the gene set fed to DE.** Tighten via `evidence_sources=['metabolism']` or `transport_confidence='substrate_confirmed'` if results are noisy. Symmetric primitives exist for `metabolite_elements=['P']`, `['S']`, `['Fe']`, etc.

### f — Ontology bridges

**TCDB substrate-anchored:** for "which genes transport substrate X?", prefer the metabolite-anchored route (`genes_by_metabolite(metabolite_ids=[...], evidence_sources=['transport'])`) over the family-anchored route (`genes_by_ontology(ontology='tcdb', ...)`). The metabolite-anchored route includes all families curating the substrate; the ontology route is family-anchored and misses cross-family substrate hits.

**KEGG pathway-anchored — pick the right surface:**
- **metabolite_pathways** (compound-anchored): which metabolites are in pathway X → `list_metabolites(pathway_ids=[...])`. Edge: `Metabolite_in_pathway`.
- **ko_pathways** (gene-KO-anchored): which genes are annotated to KOs in pathway X → `genes_by_ontology(ontology='kegg', ...)`. Edges: `Gene_has_kegg_ko` + `Kegg_term_is_a_kegg_term`.
- **reaction_pathways** (reaction-anchored, not currently surfaced as a rollup): which reactions a gene catalyses map to pathway X. Reach via `run_cypher` over `Gene_catalyzes_reaction` + `Reaction_in_kegg_pathway`.

The same KEGG pathway map (e.g. `kegg.pathway:ko00910` Nitrogen metabolism) can be reached from all three anchors, but membership relations are different — a gene whose KO is in pathway X may not catalyse any reaction whose metabolites are in pathway X (and vice versa). Always name the anchor when answering.

---

## Track B — Metabolomics measurement (partially tooled)

> **Native tools pending.** No MCP tool surfaces `MetaboliteAssay` data today. Use `run_cypher` patterns below until the metabolomics-DM tools ship. See [audit](../../../../docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md) §3b for the planned surface.

### Caveats — always restate when surfacing measurement results

- **No gene anchor.** A metabolite measurement says nothing about which gene produced/consumed it.
- **`Assay_quantifies` vs `Assay_flags`.** Quantifies = concentration/intensity (with `value`, `value_sd`, `n_replicates`, `metric_percentile`, `rank_by_metric`); Flags = qualitative detection (with `flag_value`, `n_positive`, `n_replicates`). Their downstream interpretation differs.
- **Compartment matters.** `whole_cell` measures pool; `extracellular` measures excretion / uptake / spent media. Filter by compartment.
- **Targeted panel ≠ full metabolome.** Absence in measurement ≠ absence in cell. The current KG covers 107 distinct metabolites across 10 assays in 2 papers (Capovilla 2023 and the chitin paper) — out of 3218 metabolites total, so 97% have no measurement coverage.
- **Replicate / normalisation conventions vary by paper.** Read `value_sd` and `n_replicates` on the edge; the `value` itself is processed per the paper's pipeline (KG-MET-001 documentation is open).

### Discovery

```python
# Find metabolomics experiments (kwarg is `omics_type`, takes a list).
exps = list_experiments(omics_type=["METABOLOMICS"])

# Find papers — `list_publications` has NO omics filter today (audit Part 3a P0).
# Workaround: search_text or run_cypher.
pubs = list_publications(search_text="metabolomics")
# (Audit Part 3a calls these out as P0 measurement-rollup pass-through gaps.)
```

Today (2026-05-05) returns 8 experiments + 2 publications:
- `10.1128/msystems.01261-22` (Capovilla 2023, "Metabolite diversity ..."), 8 assays.
- `10.1073/pnas.2213271120` (chitin paper 2023), 2 assays.

Treatments observed: `phosphorus`, `growth_phase`, `carbon`. Compartments: `whole_cell`, `extracellular`. Organisms: MIT9301 (4), MIT9313 (3), MIT0801 (2), MIT9303 (1).

### Assay → metabolite drill-down (run_cypher)

```python
result = run_cypher(
    """
    MATCH (p:Publication {doi: 'DOI_HERE'})
          -[:PublicationHasMetaboliteAssay]->(a:MetaboliteAssay)
          -[r:Assay_quantifies_metabolite]->(m:Metabolite)
    RETURN m.preferred_id AS metabolite_id,
           m.name AS metabolite,
           a.compartment AS compartment,
           r.value AS value,
           r.value_sd AS value_sd,
           r.n_replicates AS n_replicates,
           r.metric_type AS metric_type,
           r.metric_percentile AS percentile,
           r.condition_label AS condition,
           a.experiment_id AS experiment
    ORDER BY value DESC
    """,
    limit=50,
)
```

For flag-only assays (qualitative detection — 2 of the 10 current assays), substitute `r:Assay_flags_metabolite` and read `r.flag_value`, `r.n_positive`.

### Metabolite → assay reverse lookup

```python
result = run_cypher(
    """
    MATCH (m:Metabolite {preferred_id: 'METABOLITE_ID'})
          <-[r:Assay_quantifies_metabolite|Assay_flags_metabolite]-(a:MetaboliteAssay)
          <-[:ExperimentHasMetaboliteAssay]-(e:Experiment)
    RETURN type(r) AS evidence_kind,
           e.id AS experiment,
           e.treatment_type AS treatment,
           e.background_factors AS background,
           a.compartment AS compartment,
           coalesce(r.value, r.flag_value) AS value
    """,
    limit=20,
)
# `evidence_kind` ∈ {Assay_quantifies_metabolite, Assay_flags_metabolite} — discriminate downstream.
```

### Cross-omics anchoring

When the user asks "did N starvation change metabolite X?", combine:

```python
# 1. Metabolomics evidence (run_cypher above).
# 2. Expression evidence — which N-acting genes responded:
#    follow Track A combined §e (metabolites_by_gene metabolite_elements=['N']
#    → differential_expression_by_gene).
# 3. Surface both with their caveats; do not conflate "metabolite changed" with
#    "metabolite caused effect" or vice versa.
```

Time-point alignment between metabolomics and expression assays is open (Part 4 §4.3.8 in the audit) — confirm experiment `id` matches before joining.

---

## Quick decision tree

```
User asks about a metabolite or chemistry
├─ "Can / does gene X act on metabolite M?"
│   ├─ "produce / catalyse" → Track A1 b1/c1 (metabolism arm)
│   └─ "transport" → Track A2 b2/c2 (transport arm) + g (precision-tier)
├─ "Which genes act on M?" → genes_by_metabolite (read evidence_source split)
├─ "Which metabolites does gene X act on?" → metabolites_by_gene
├─ "Find metabolite by name → metabolite_id" → list_metabolites(search="...")  ← name-search hook; precedes any compound-anchored chain
├─ "Find metabolites by element / pathway / mass" → list_metabolites
├─ "Cross-feeding between organisms" → Track A combined §d
├─ "N-source / chemistry-filtered DE" → Track A combined §e
├─ "Genes that transport substrate X" → Track A combined §f (metabolite-anchored)
├─ "Genes annotated to TCDB family / KEGG term" → genes_by_ontology
└─ "Was metabolite M measured? At what level?" → Track B (run_cypher)
```
