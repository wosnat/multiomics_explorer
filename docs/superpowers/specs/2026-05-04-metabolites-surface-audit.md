# Metabolites Surface Audit — 2026-05-04

**Date:** 2026-05-04
**Spec:** [2026-05-04-metabolites-assets-design.md](2026-05-04-metabolites-assets-design.md)
**Owner:** Osnat Weissberg
**Status:** First pass in progress

This audit accompanies the metabolites assets effort. It quantifies the metabolite surface in the KG, lists existing-tool gaps for both chemistry-annotation and metabolomics-measurement layers, proposes new tools, captures open definition questions, and itemises KG-side asks. The audit runs in two passes: a first pass populated before the analysis doc and example python are written (`phase=first-pass`), and a second pass appended after they are written (`phase=build-derived`).

---

## Part 1 — KG inventory (quantified)

All counts come from live `run_cypher` queries against the deployed KG (`bolt://localhost:7687`, KG release 2026-05-04). Each query is shown inline so the audit is reproducible.

### 1.1 Source-coverage Venn over Metabolite

Three Metabolite-source pipelines (transport via TCDB, gene reaction via KEGG, metabolomics measurement via MetaboliteAssay), broken down by which sources contribute to each metabolite.

```cypher
MATCH (m:Metabolite)
WITH m,
     EXISTS((m)<-[:Tcdb_family_transports_metabolite]-(:TcdbFamily)) AS has_transport,
     EXISTS((m)<-[:Reaction_has_metabolite]-(:Reaction)) AS has_reaction,
     EXISTS((m)<-[:Assay_quantifies_metabolite|Assay_flags_metabolite]-(:MetaboliteAssay)) AS has_measurement
RETURN
  CASE WHEN has_transport AND has_reaction AND has_measurement THEN 'transport+reaction+measurement'
       WHEN has_transport AND has_reaction THEN 'transport+reaction'
       WHEN has_transport AND has_measurement THEN 'transport+measurement'
       WHEN has_reaction AND has_measurement THEN 'reaction+measurement'
       WHEN has_transport THEN 'transport-only'
       WHEN has_reaction THEN 'reaction-only'
       WHEN has_measurement THEN 'measurement-only'
       ELSE 'orphan' END AS bucket,
  count(m) AS n
ORDER BY n DESC;
```

| Bucket | n | % of total |
|---|---:|---:|
| `reaction-only` | 1895 | 62.4% |
| `transport-only` | 832 | 27.4% |
| `transport+reaction` | 201 | 6.6% |
| `transport+reaction+measurement` | 59 | 1.9% |
| `reaction+measurement` | 33 | 1.1% |
| `measurement-only` | 10 | 0.3% |
| `transport+measurement` | 5 | 0.2% |
| **Total** | **3035** | **100%** |

**Key facts:**
- **107 metabolites have measurement evidence** (sum of last 4 buckets) — the metabolomics layer is broader than just the 10 measurement-only metabolites. Most measured metabolites also have annotation paths.
- **97% of measurement-anchored metabolites also have annotation evidence** (97 of 107) — the layers are mostly aligned, not parallel.
- **Annotation overlap is small:** only 260 of 2188 reaction-anchored metabolites also have transport (12%), suggesting the two annotation pipelines target largely different chemistry.

The `Metabolite.evidence_sources` list field already encodes the same split as a node-level array; the bucketing above can be reproduced from `m.evidence_sources` directly:

```cypher
MATCH (m:Metabolite)
RETURN coalesce(m.evidence_sources, []) AS evidence_sources, count(m) AS n
ORDER BY n DESC;
```

returns the same 7 buckets with identical counts.

### 1.2 Per-source edge inventory

Per pipeline, the edge labels and edge-level properties currently in the KG. This grounds Part 4 (open definition questions) and Part 5 (KG-side asks) in what the KG already has versus what is genuinely missing.

```cypher
CALL db.schema.relTypeProperties() YIELD relType, propertyName
WHERE relType IN ['Tcdb_family_transports_metabolite', 'Reaction_has_metabolite', 'Gene_has_tcdb_family', 'Gene_catalyzes_reaction', 'Assay_quantifies_metabolite', 'Assay_flags_metabolite', 'ExperimentHasMetaboliteAssay', 'PublicationHasMetaboliteAssay', 'MetaboliteAssayBelongsToOrganism']
RETURN relType, collect(propertyName) AS properties;
```

| Edge | Source → Target | Properties on edge | Notes |
|---|---|---|---|
| `Gene_has_tcdb_family` | Gene → TcdbFamily | `id` only | Edge does not carry confidence; substrate_confirmed vs family_inferred is computed elsewhere (likely from `TcdbFamily.superfamily` + member_count). |
| `Tcdb_family_transports_metabolite` | TcdbFamily → Metabolite | `id` only | No direction (import vs export). No primary-substrate ranking. |
| `Gene_catalyzes_reaction` | Gene → Reaction | `id` only | No direction or stoichiometry on this edge. |
| `Reaction_has_metabolite` | Reaction → Metabolite | `id` only | **No substrate/product role discriminator on this edge** — Part 4 reaction-direction question is real. |
| `Assay_quantifies_metabolite` | MetaboliteAssay → Metabolite | `value`, `value_sd`, `n_replicates`, `n_non_zero`, `replicate_values`, `time_point`, `time_point_hours`, `time_point_order`, `metric_type`, `metric_bucket`, `metric_percentile`, `rank_by_metric`, `condition_label`, `detection_status`, `id` | **Rich** — replicate count, SD, percentile, detection status all present. KG-MET-001 (replicate / normalisation) is mostly satisfied here; the open question is whether `value` is normalised and if so by what convention (per-paper). |
| `Assay_flags_metabolite` | MetaboliteAssay → Metabolite | `flag_value`, `n_positive`, `n_replicates`, `condition_label`, `metric_type`, `id` | Qualitative detection — `flag_value` discriminator. Edges include replicate count. |
| `ExperimentHasMetaboliteAssay` | Experiment → MetaboliteAssay | `id` only | Single edge per assay. |
| `PublicationHasMetaboliteAssay` | Publication → MetaboliteAssay | `id` only | Single edge per assay. |
| `MetaboliteAssayBelongsToOrganism` | MetaboliteAssay → OrganismTaxon | `id` only | Single edge per assay. |

**Pre-computed node-level rollups already in the KG (these reduce the KG-side ask list — see Part 5):**

- `Metabolite.measured_assay_count`, `Metabolite.measured_paper_count`, `Metabolite.measured_organisms` — **per-Metabolite measurement rollups already present**. KG-MET-004 is largely satisfied.
- `Publication.metabolite_assay_count`, `Publication.metabolite_compartments`, `Publication.metabolite_count` — **per-Publication metabolomics rollups already present**. KG-MET-005 (publication-side) is satisfied.
- `Experiment.metabolite_assay_count`, `Experiment.metabolite_compartments`, `Experiment.metabolite_count` — **per-Experiment rollups already present**. KG-MET-005 (experiment-side) is satisfied.
- `OrganismTaxon.measured_metabolite_count` — **per-Organism rollup already present**.
- `TcdbFamily.superfamily`, `TcdbFamily.metabolite_count`, `TcdbFamily.member_count` — **TCDB family promiscuity precompute already present** via `superfamily`. KG-MET-006 is largely satisfied.

### 1.3 Transport (TCDB) source

```cypher
MATCH (g:Gene)-[:Gene_has_tcdb_family]->(f:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)
RETURN count(*) AS gene_metabolite_pairs,
       count(DISTINCT g) AS distinct_genes,
       count(DISTINCT f) AS distinct_families,
       count(DISTINCT m) AS distinct_metabolites;
```

| Metric | Value |
|---|---:|
| Gene → metabolite pairs (cross product through family) | 347 937 |
| Distinct genes annotated to ≥1 TCDB family | 6 700 |
| Distinct TCDB families with substrate links | 404 |
| Distinct metabolites with transport evidence | 1 097 |

```cypher
MATCH (g:Gene)-[:Gene_has_tcdb_family]->(f:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)
WITH g, count(DISTINCT m) AS n_metabolites_per_gene
RETURN min(n_metabolites_per_gene) AS min_m,
       percentileDisc(n_metabolites_per_gene, 0.5) AS median_m,
       percentileDisc(n_metabolites_per_gene, 0.9) AS p90_m,
       max(n_metabolites_per_gene) AS max_m;
```

| Per-gene metabolite count (transport) | min | median | p90 | max |
|---|---:|---:|---:|---:|
| Distinct metabolites per gene | 1 | 6 | 90 | **551** |

The `max=551` confirms the spec's ABC-superfamily caveat: a single gene can carry hundreds of family-inferred metabolite associations.

```cypher
MATCH (f:TcdbFamily)
RETURN coalesce(f.superfamily, '<none>') AS superfamily,
       count(f) AS n_families,
       sum(f.metabolite_count) AS total_metab_links
ORDER BY total_metab_links DESC LIMIT 5;
```

Top 5 superfamilies by metabolite-link volume:

| Superfamily | n families | total metabolite links |
|---|---:|---:|
| `<none>` (no superfamily) | 605 | 7 886 |
| Major Facilitator (MFS) | 1 123 | 1 501 |
| ArsA ATPase | 1 053 | 1 298 |
| Outer Membrane Pore-forming Protein I | 505 | 451 |
| APC | 265 | 441 |

**Observation:** the `<none>`-superfamily families dominate the substrate-link volume because they are typically narrower curations (avg 13 metabolites per family) — but they have no superfamily-level promiscuity flag. Whether they should be treated as substrate_confirmed or family_inferred depends on family member count, which is in `TcdbFamily.member_count` — captured as a Part 5 ask.

### 1.4 Reaction (KEGG) source

```cypher
MATCH (g:Gene)-[:Gene_catalyzes_reaction]->(rx:Reaction)
WITH count(*) AS gene_reaction_edges, count(DISTINCT g) AS genes, count(DISTINCT rx) AS rxns
MATCH (rx2:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)
RETURN gene_reaction_edges, genes, rxns,
       count(*) AS reaction_metabolite_edges,
       count(DISTINCT rx2) AS distinct_reactions_total,
       count(DISTINCT m) AS distinct_metabolites_in_reactions;
```

| Metric | Value |
|---|---:|
| Gene → Reaction edges | 53 917 |
| Distinct genes with ≥1 reaction | 21 630 |
| Distinct Reactions with ≥1 gene | 2 349 |
| Reaction → Metabolite edges | 10 050 |
| Distinct Reactions total | 2 315 |
| Distinct metabolites in reactions | 2 188 |

**Observation:** `Reaction_has_metabolite` carries no `role` (substrate vs product) property — confirmed in §1.2. This is the empirical basis for the Part 4 reaction-direction question.

### 1.5 Metabolomics measurement source

```cypher
MATCH (a:MetaboliteAssay)
RETURN count(a) AS assay_count,
       collect(DISTINCT a.compartment) AS compartments,
       collect(DISTINCT a.value_kind) AS value_kinds,
       collect(DISTINCT a.metric_type) AS metric_types;
```

| Metric | Value |
|---|---|
| MetaboliteAssay count | 10 |
| Compartments | `whole_cell`, `extracellular` |
| Value kinds | `numeric`, `boolean` |
| Metric types | `cellular_concentration`, `extracellular_concentration`, `presence_flag_intracellular`, `presence_flag_extracellular` |

```cypher
MATCH (a:MetaboliteAssay)
RETURN a.compartment AS compartment, a.value_kind AS value_kind, count(a) AS n_assays
ORDER BY compartment, value_kind;
```

| Compartment | Value kind | n assays |
|---|---|---:|
| extracellular | numeric | 3 |
| whole_cell | boolean | 2 |
| whole_cell | numeric | 5 |

```cypher
MATCH (a:MetaboliteAssay)-[r:Assay_quantifies_metabolite]->(:Metabolite)
RETURN coalesce(r.metric_type, '<none>') AS metric_type, count(*) AS n_edges, count(DISTINCT a) AS n_assays
ORDER BY n_edges DESC;

MATCH (a:MetaboliteAssay)-[r:Assay_flags_metabolite]->(:Metabolite)
RETURN coalesce(r.metric_type, '<none>') AS metric_type, count(*) AS n_edges, count(DISTINCT a) AS n_assays
ORDER BY n_edges DESC;
```

Edge totals:

| Edge type | Metric type | n edges | n assays using |
|---|---|---:|---:|
| Quantifies | cellular_concentration | 648 | 5 |
| Quantifies | extracellular_concentration | 552 | 3 |
| Flags | presence_flag_intracellular | 93 | 1 |
| Flags | presence_flag_extracellular | 93 | 1 |
| **Quantifies (total)** |  | **1 200** | **8** |
| **Flags (total)** |  | **186** | **2** |

```cypher
MATCH (p:Publication)-[:PublicationHasMetaboliteAssay]->(a:MetaboliteAssay)
RETURN p.doi AS doi, p.title AS title, p.publication_year AS year, count(DISTINCT a) AS n_assays
ORDER BY n_assays DESC;
```

| DOI | Title | Year | n assays |
|---|---|---:|---:|
| `10.1128/msystems.01261-22` | Metabolite diversity among representatives of divergent Prochlorococcus ecotypes | 2023 | 8 |
| `10.1073/pnas.2213271120` | Chitin utilization by marine picocyanobacteria and the evolution of a planktonic lifestyle | 2023 | 2 |

```cypher
MATCH (a:MetaboliteAssay)-[:MetaboliteAssayBelongsToOrganism]->(o:OrganismTaxon)
RETURN o.preferred_name AS organism, count(DISTINCT a) AS n_assays
ORDER BY n_assays DESC;
```

| Organism | n assays |
|---|---:|
| Prochlorococcus MIT9301 | 4 |
| Prochlorococcus MIT9313 | 3 |
| Prochlorococcus MIT0801 | 2 |
| Prochlorococcus MIT9303 | 1 |

```cypher
MATCH (e:Experiment)-[:ExperimentHasMetaboliteAssay]->(a:MetaboliteAssay)
RETURN e.id AS experiment_id, e.treatment_type AS treatment, e.background_factors AS bg, e.compartment AS compartment, count(DISTINCT a) AS n_assays
ORDER BY n_assays DESC;
```

8 experiments contribute the 10 assays, with treatments split across:
- `phosphorus` (Capovilla 9301): 4 assays (3 whole_cell + 1 extracellular)
- `growth_phase` (Capovilla 0801, 9313): 4 assays (2 whole_cell + 2 extracellular)
- `carbon` (chitin paper, 9303 + 9313): 2 assays (whole_cell only)

All experiments have `axenic` background; some also have `light`.

```cypher
MATCH (m:Metabolite)
RETURN coalesce(m.measured_paper_count, 0) AS papers, count(m) AS n
ORDER BY papers DESC;
```

| Papers covering the metabolite | n metabolites |
|---:|---:|
| 2 | 8 |
| 1 | 99 |
| 0 | 2928 |

The 8 metabolites covered by both papers are the cross-paper anchor set. 99 are paper-specific. 2928 (96%) of all metabolites have no measurement coverage at all (chemistry annotation only).

### 1.6 Summary of Part 1 findings

1. **Three pipelines coexist with mostly-disjoint reach.** 1895 metabolites are reaction-only, 832 transport-only, 107 measurement-anchored. Only 59 metabolites surface across all three.
2. **The metabolomics layer is rich but small.** 10 assays, 1386 edges, 107 distinct metabolites measured, 2 papers. Edge schemas already carry replicate counts, SD, percentiles, detection status, time point, condition label.
3. **Several proposed KG asks are already satisfied.** Per-Metabolite/-Publication/-Experiment/-Organism measurement rollups exist (KG-MET-004/005). TCDB family superfamily flag exists (KG-MET-006). Replicate counts exist on edges (KG-MET-001 partial).
4. **The genuine KG gaps** (confirmed by §1.2 edge inventory) are: reaction-direction role, normalisation-method documentation, and a TcdbFamily-level promiscuity score that distinguishes narrow `<none>`-superfamily families from broad ones.

---

## Part 2 — Chemistry-annotation surface (existing tools)

(populated in Phase B Task B1; second pass — Phase E Task E1)

| Tool | Current chemistry surfacing | Recommended change | Priority | Phase |
|---|---|---|---|---|

---

## Part 3 — Metabolomics-measurement surface (greenfield)

### 3a — Existing-tool modifications

(populated in Phase B Task B2; second pass — Phase E Task E2)

| Tool | Current surfacing | Recommended change | Priority | Phase |
|---|---|---|---|---|

### 3b — New-tool proposals

(populated in Phase B Task B3; second pass — Phase E Task E3)

---

## Part 4 — Open definition questions

(populated in Phase B Task B4)

---

## Part 5 — KG-side asks

(populated in Phase B Task B5; second pass — Phase E Task E4)

| ID | Category | Priority | Phase | Ask | Why (explorer item it unblocks) |
|---|---|---|---|---|---|
