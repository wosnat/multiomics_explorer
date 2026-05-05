# Metabolites Surface Audit — 2026-05-04

**Date:** 2026-05-04 (initial); **last refreshed:** 2026-05-05 (walkthrough Q&A pass)
**Spec:** [2026-05-04-metabolites-assets-design.md](2026-05-04-metabolites-assets-design.md)
**Owner:** Osnat Weissberg
**Status:** Three-pass complete (first-pass design; build-derived second pass; walkthrough Q&A third pass). Ready for KG-side review and metabolomics-DM definition conversation.

This audit accompanies the metabolites assets effort. It quantifies the metabolite surface in the KG, lists existing-tool gaps for both chemistry-annotation and metabolomics-measurement layers, proposes new tools, captures open definition questions, and itemises KG-side asks. The audit runs in two passes: a first pass populated before the analysis doc and example python are written (`phase=first-pass`), and a second pass appended after they are written (`phase=build-derived`).

### Priority legend

Used in the `Priority` column across Parts 2, 3a, 3b, and 5.

| Code | Meaning |
|---|---|
| **P0** | Ship now; pure pass-through or otherwise unblocked. |
| **P1** | Should-add; clear value, not blocking. |
| **P2** | Quality-of-life. |
| **P3** | Low-priority polish (docstring tweaks, minor ergonomics). |
| **DROP** | Considered and rejected (e.g. would add per-row noise; redundant with another tool). |
| **DEFER** | Paused on a dependency (a Part 4 question, a KG-side decision, or another tool landing first). |
| **—** | No change recommended. |
| **CLOSED** | Already shipped (used in Part 5 for KG asks already satisfied). |
| **RETIRED** | Considered then withdrawn after the rationale changed (used in Part 5). |

---

## Part 1 — KG inventory (quantified)

All counts come from live `run_cypher` queries against the deployed KG (`bolt://localhost:7687`). Each query is shown inline so the audit is reproducible. **Numbers refreshed 2026-05-05** after the TCDB bug-fix KG rebuild (no schema changes; transport coverage broadened).

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
| `reaction-only` | 1833 | 56.9% |
| `transport-only` | 1015 | 31.5% |
| `transport+reaction` | 263 | 8.2% |
| `transport+reaction+measurement` | 72 | 2.2% |
| `reaction+measurement` | 20 | 0.6% |
| `measurement-only` | 10 | 0.3% |
| `transport+measurement` | 5 | 0.2% |
| **Total** | **3218** | **100%** |

**Key facts (2026-05-05 refresh):**
- **107 metabolites have measurement evidence** (sum of last 4 buckets) — unchanged in total, but the breakdown shifted toward `transport+reaction+measurement` (was 59, now 72) because the TCDB bug fix exposed transport links for 13 measured metabolites that previously surfaced as `reaction+measurement` only.
- **97% of measurement-anchored metabolites also have annotation evidence** (97 of 107) — the layers are mostly aligned, not parallel.
- **Annotation overlap grew with the bug fix:** 335 metabolites now have both transport and reaction annotation (was 260) — 12% of reaction-anchored metabolites also have transport (was 12% — same proportion, larger denominator on the transport side).
- **Net new metabolites:** +183 since 2026-05-04 (3035 → 3218). Most of the new content is transport-only (832 → 1015) and transport+reaction overlap (201 → 263).

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
| Gene → metabolite pairs (cross product through family) | 389 694 |
| Distinct genes annotated to ≥1 TCDB family | 8 971 |
| Distinct TCDB families with substrate links | 490 |
| Distinct metabolites with transport evidence | 1 355 |

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
| Distinct metabolites per gene | 1 | 4 | 48 | **992** |

Median dropped (6 → 4) because the bug fix added many narrow-family transport annotations to genes that previously had broad-family-only coverage; max went up (551 → 992) because the broadest ABC family now curates ~440 more substrates than it did pre-fix. The empirical ABC-superfamily caveat is sharper, not weaker.

In MED4 specifically, **12 genes** (was 9) now hit 554 distinct metabolites each via TCDB:

```
PMM0125, PMM0392, PMM0434, PMM0449, PMM0450, PMM0666,
PMM0749, PMM0750, PMM0913, PMM0976, PMM0977, PMM0978
```

The original 9 (PMM0434/0449/0450/0749/0750/0913/0976/0977/0978) are still present; the bug fix added PMM0125, PMM0392, PMM0666 to the same ABC-anchored band.

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
| `<none>` (no superfamily) | 5 985 | 10 712 |
| Major Facilitator (MFS) | 1 325 | 2 461 |
| ArsA ATPase | 1 059 | 1 855 |
| APC | 695 | 1 610 |
| Outer Membrane Pore-forming Protein I | 574 | 636 |

**Observation:** post-bug-fix, the `<none>`-superfamily-family count grew almost 10× (605 → 5 985) — the fix appears to have admitted many more curated TCDB families that lack superfamily assignment. Total link volume in this bucket only ~1.36× (7 886 → 10 712), so most new families are narrow (avg 1.8 metabolites). Whether they should be treated as substrate_confirmed or family_inferred still depends on family member count (KG-MET-006).

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
| 0 | 3111 |

The 8 metabolites covered by both papers are the cross-paper anchor set. 99 are paper-specific. 3111 (97%) of all metabolites have no measurement coverage at all (chemistry annotation only). Total measurement-anchored metabolites = 107 (unchanged across the rebuild).

### 1.6 Summary of Part 1 findings

1. **Three pipelines coexist with mostly-disjoint reach.** 1833 metabolites are reaction-only, 1015 transport-only, 107 measurement-anchored. Only 72 metabolites surface across all three. (Refreshed 2026-05-05 after the TCDB bug-fix rebuild; transport coverage grew most.)
2. **The metabolomics layer is rich but small.** 10 assays, 1386 edges, 107 distinct metabolites measured, 2 papers. Edge schemas already carry replicate counts, SD, percentiles, detection status, time point, condition label.
3. **Several proposed KG asks are already satisfied.** Per-Metabolite/-Publication/-Experiment/-Organism measurement rollups exist (KG-MET-004/005). TCDB family superfamily flag exists (KG-MET-006). Replicate counts exist on edges (KG-MET-001 partial).
4. **The genuine remaining KG gaps** (confirmed by §1.2 edge inventory and 2026-05-04 user resolution): normalisation-method documentation, a TcdbFamily-level promiscuity score for non-superfamily families, and a few documentation items. The reaction-direction role question is **resolved as a non-ask** — upstream KEGG annotation direction is unreliable, so explorer tools commit to "involved in" framing as a permanent convention. See Part 4 §4.1.1 + Part 5 KG-MET-003 retirement.

---

## Part 2 — Chemistry-annotation surface (existing tools)

How existing MCP tools surface (or fail to surface) the reaction-arm and transport-arm of metabolite annotation.

**Reframing rule (walkthrough Q&A 2026-05-05):** chemistry-rollup-as-routing-hint belongs on **discovery / overview** tools (`gene_overview`, `gene_details`, `list_*`), where counts inform "should I look here?" It is **noise** on **purpose-built / search-result / DM-anchored / ortholog / cluster** tools, where the question shape is already specific and the user can drill via `gene_overview` or `metabolites_by_gene` from returned locus_tags. A5 (`n_source_de`) is the empirical proof — chemistry was scoped upstream via `list_metabolites` + `genes_by_metabolite`, not surfaced as per-row context on `gene_response_profile`.

### TODO — recommended changes

Sorted P0 → P3 → "—". All are pure pass-through of Gene / Publication / Experiment / Organism / Metabolite node properties that already exist in the KG.

| Tool | Current chemistry surfacing | Recommended change | Priority | Phase |
|---|---|---|---|---|
| `gene_overview` | Per-row `reaction_count` / `metabolite_count` / `transporter_count` + drill-down hints | Strong baseline. Add: per-row `evidence_sources` rollup (which of metabolism/transport/measurement applies to the gene's metabolites). **Promoted P2 → P0 walkthrough Q&A 2026-05-05** — canonical gene-side routing surface. | P0 | first-pass |
| `list_publications` | None — chemistry-capability not exposed despite Publication node having `metabolite_count` / `metabolite_assay_count` | Surface `metabolite_count`, `metabolite_assay_count`, `metabolite_compartments` per row (data is on the node — KG-side rollup already exists; this is pure pass-through) | P0 | first-pass |
| `list_experiments` | None despite Experiment node having `metabolite_assay_count` etc. | Surface `metabolite_count`, `metabolite_assay_count`, `metabolite_compartments` per row (pass-through) | P0 | first-pass |
| `list_organisms` | Per-row `reaction_count` / `metabolite_count` + envelope `by_metabolic_capability` | Strong baseline. Add: `measured_metabolite_count` (already on node) + envelope `by_measurement_capability` mirroring the chemistry one | P1 | first-pass |
| `genes_by_function` | None — text search on annotation; no chemistry hint | When hits have non-zero chemistry counts, surface them in result rows (Gene-node pass-through) | P1 (PENDING decision — walkthrough flagged "maybe") | first-pass |
| `genes_by_ontology` | TCDB/EC ontologies route to chemistry via docstring | Add explicit pivot guidance from `tcdb` / `ec` term hits to `genes_by_metabolite` (metabolite-anchored route — see analysis doc Track A2 §f). Docstring-only; no per-row change. | P2 | first-pass |
| `list_filter_values` | Categorical filters listed (categories, BRITE, DM types, etc.) | Add `evidence_source` filter type (returns `['metabolism', 'transport', 'metabolomics']`) for downstream tools that want to filter on it | P2 | first-pass |
| `pathway_enrichment` | KEGG/EC ontology support; doesn't pivot to metabolites | Add docstring guidance: when KEGG pathway is enriched, route to `list_metabolites(pathway_ids=[...])` to inspect chemistry of the pathway. Docstring-only. | P2 | first-pass |
| `gene_details` | All Gene properties via `g{.*}` — chemistry counts present but undifferentiated | Add explicit chemistry section in docstring guidance; no schema change needed (data already flows) | P3 | first-pass |
| `cluster_enrichment` | Same as pathway_enrichment | Same — route to `list_metabolites(pathway_ids=[...])` for chemistry drill-down. Docstring-only. | P3 | first-pass |
| `list_derived_metrics` | None | DM-discovery surface need not surface chemistry directly — but the docstring should route from DM → `genes_by_*_metric` → drill into chemistry. Docstring-only. | P3 | first-pass |
| `list_metabolites` | Already chemistry-first by design — gene_count, transporter_count, top_pathways etc. | Strong baseline. Possible addition deferred to second pass (depends on what build phase reveals) | — | first-pass (no change) |
| `genes_by_metabolite` | Already chemistry-first — evidence_source / transport_confidence / per-row EC | Strong baseline | — | first-pass (no change) |
| `metabolites_by_gene` | Already chemistry-first — symmetric counterpart | Strong baseline | — | first-pass (no change) |
| `kg_schema` | Returns full schema including new metabolomics nodes/edges | No change needed — verified Part 1 §1.2 introspection works | — | first-pass (no change) |
| `run_cypher` | Free-form — chemistry available via direct Cypher | No tool change — but the analysis doc's Track-B `run_cypher` section is a documentation surface that effectively extends `run_cypher` with metabolomics patterns | — | first-pass (no change) |

### DROP — considered and rejected

These tools are purpose-built / search-result-shaped / DM-anchored / ortholog-anchored / cluster-anchored / identity-resolution. Adding per-row chemistry counts adds noise without informing the workflow — users who want chemistry should drill via `gene_overview` or `metabolites_by_gene` from the locus_tags these tools return.

| Tool | Original proposal | Reason for DROP |
|---|---|---|
| `gene_response_profile` | Per-result chemistry rollup (was P0) | Purpose-built; chemistry scopes upstream (A5 empirical proof) |
| `differential_expression_by_gene` | Per-row chemistry counts + envelope `by_chemistry_capability` (was P0) | Purpose-built DE; same reasoning |
| `differential_expression_by_ortholog` | Group-level chemistry pass-through (was P1) | Purpose-built DE at ortholog level; chemistry adds noise |
| `gene_homologs` | Group-level chemistry rollup (was P1) | Orthology lookup; chemistry not informative per-row |
| `genes_by_homolog_group` | Per-row chemistry counts (was P1) | Same |
| `search_homolog_groups` | Envelope `by_chemistry_coverage` (was P2) | Search-result shape; same reasoning |
| `gene_clusters_by_gene` | Per-cluster chemistry rollup (was P1) | Cluster-membership lookup; chemistry adds noise |
| `genes_in_cluster` | Per-row chemistry counts + envelope `top_metabolites` (was P0) | Cluster drill-down; chemistry adds noise |
| `list_clustering_analyses` | Per-analysis chemistry coverage (was P2) | Analysis-level rollup; member chemistry not informative |
| `gene_derived_metrics` | Per-row chemistry + N-rhythmicity warning (was P2) | DM-anchored; chemistry adds noise |
| `genes_by_numeric_metric` | Per-row chemistry + filtered-slice metabolite-class envelope (was P2) | Same |
| `genes_by_boolean_metric` | Per-row chemistry counts (was P2) | Same |
| `genes_by_categorical_metric` | Per-row chemistry counts (was P2) | Same |
| `gene_ontology_terms` | Per-gene chemistry as context (was P3) | Reverse ontology lookup; chemistry adds noise |
| `resolve_gene` | Per-row chemistry as light routing hint (was P3) | Identity resolution; chemistry not informative for ID matching |

### Summary

**P0 (3 items):** `gene_overview`, `list_publications`, `list_experiments` — all pure pass-through of existing node-property data. Pass A candidate.

**P1 (1 confirmed + 1 pending):** `list_organisms` (measurement-rollup extension); `genes_by_function` chemistry hints (PENDING walkthrough decision).

**Docstring-only (no per-row change):** `genes_by_ontology`, `pathway_enrichment`, `cluster_enrichment`, `list_derived_metrics`, `gene_details`. P2/P3 routing hints in docs; all lower-effort than P0 plumbing.

**Cross-cut:** all TODO items are pure pass-through. No tool needs new Cypher — only Pydantic envelope/row-model expansion + query SELECT list.

### Part 2 — build-derived rows (second pass)

| Tool | Current chemistry surfacing | Recommended change | Priority | Phase |
|---|---|---|---|---|
| `differential_expression_by_gene` | Accepts `direction` parameter but rejects `'both'` (only `'up'` / `'down'`) | Either accept `'both'` (run both internally and merge) OR document the limitation in the docstring + raise a clearer error message naming the alternative (omit param to get both directions). Surfaced by example python scenario `n_source_de` — initial code used `direction='both'` mirroring `pathway_enrichment` and crashed with `Invalid direction 'both'` | P2 | build-derived (scenario 5 `n_source_de`) |
| `genes_by_metabolite` | Per-row schema is **union** by evidence_source (metabolism rows have `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance`; transport rows have `transport_confidence`/`tcdb_family_id`/`tcdb_family_name`) — neither set is documented as conditional in the docstring | Document the union shape explicitly in the tool description; consider surfacing `transport_confidence: None` and `reaction_id: None` keys in metabolism/transport rows respectively for shape consistency | P2 | build-derived (scenarios 2 `compound_to_genes` + 6 `tcdb_chain` — required arm-specific result printing logic) |
| `metabolites_by_gene` | Same union shape as `genes_by_metabolite` | Same — document union shape | P2 | build-derived (scenario 3 `gene_to_metabolites`) |
| `metabolites_by_gene` (summary mode) | `summary=True` returns `top_genes=None` even when results exist (observed for small inputs) | Investigate: is `top_genes` only populated when input list is large enough? Document threshold or fix to always populate. Workaround used: extract gene set from non-summary `results` directly | P3 | build-derived (scenario 5 `n_source_de`) |
| `search_ontology` | Kwarg is `search_text`, not `query` (initially confused) | The discoverability is fine via signature inspection but the analysis-doc patterns and existing `pathway_enrichment.py` use `query=` style elsewhere. Consider accepting both `query=` and `search_text=` aliases for ergonomics | P3 | build-derived (scenario 6 `tcdb_chain`) |
| `list_metabolites` | Free-text search kwarg is `search`, not `search_text` — **outlier** across the 8 list/search tools (7 of 8 use `search_text`: `list_experiments`, `list_publications`, `list_clustering_analyses`, `list_derived_metrics`, `search_ontology`, `search_homolog_groups`, `genes_by_function`). | Rename `list_metabolites(search=)` → `list_metabolites(search_text=)` for consistency. Breaking change, but only 2 internal call sites today (example python `compound_to_genes` scenario; analysis doc Track A1 §c1) — both controlled. Update tool signature + 2 call sites + tests in one slice. | P2 | build-derived (walkthrough Q&A 2026-05-05) |
| `metabolites_by_gene` + `genes_by_metabolite` reaction-arm docstring | Reaction-arm rows have no direction (§4.1.1) AND no reversibility flag (§4.1.2 resolved 2026-05-05). Tool docstrings don't currently spell this out. | Document thoroughly: explicit "reaction edges are undirected AND carry no reversibility flag — interpret all reaction-arm rows as 'involved in', never 'produces'/'consumes'/'reversible'." Analysis doc Track A1 caveat must be extended to call out the reversibility gap alongside the existing direction caveat. Apply to both tools' YAML chaining/mistakes sections. | P3 | build-derived (walkthrough Q&A 2026-05-05) |
| `list_metabolites` (name-search discoverability) | `search` parameter exists and works (e.g., `search='glutamine'` returns 4 matches) but is **not surfaced in the analysis doc decision tree** as the canonical name→ID hook. Most user-facing questions arrive by metabolite NAME, not by KEGG ID. | Surface name→ID lookup as an explicit decision-tree branch: `list_metabolites(search='...')` precedes any compound-anchored chain. **Updated in this run (analysis doc + scenario `compound_to_genes` now demonstrates the two-step chain).** | P3 | build-derived (walkthrough Q&A 2026-05-05) |
| `metabolites_by_gene` / `genes_by_metabolite` `by_element` semantics | Envelope rollup is **presence-only** (count of distinct compounds containing each element at all) — **not stoichiometric** (no atom counts per compound; stoichiometry lives in `metabolite.formula`) and **not mass-balanced** (KG carries no substrate-vs-product role on `Reaction_has_metabolite`, Part 4 §4.1.1 resolved). Per-row `elements` field has the same shape (set of symbols, no counts). Tool docstrings don't make this explicit. | Document `by_element` semantics in tool description: "count of distinct compounds in `total_matching` containing each element". Note that mass-balanced flux is intentionally not surfaced. **Updated in this run (analysis doc Track A1 §c1 now spells this out).** | P3 | build-derived (walkthrough Q&A 2026-05-05) |
| `genes_by_metabolite` + `metabolites_by_gene` family_inferred-dominance warning text | Both tools emit a warning prescribing `transport_confidence='substrate_confirmed'` as a "high-precision" tighten action (functions.py:5197 and :5775). The wording predates the §g reframing: "Re-run with transport_confidence='substrate_confirmed' for substrate-curated transporter genes only" / "For high-precision substrate-curated annotations only, set transport_confidence='substrate_confirmed'". | Soften to informational + question-shape-aware: "Most transport rows are family_inferred (X of Y) — annotations rolled up from family-level transport potential. Use `substrate_confirmed` for conservative-cast questions (e.g. cross-organism inference); keep family_inferred for broad-screen candidate enumeration. See analysis-doc §g — both tiers are annotations, neither is ground truth." Drop A7 `precision_tier` scenario — A6 + §g already cover this teaching. | P3 | build-derived (walkthrough Q&A 2026-05-05; A7 dropped same commit) |
| **Cross-cutting:** `top_pathways` envelope-key + per-row naming across all tools presenting metabolite pathways (`list_metabolites`, `metabolites_by_gene`; eventually any other compound-anchored chemistry tool) | The word "pathway" is overloaded across compound-anchored and KO-anchored surfaces — both reach the same KEGG pathway maps but via different membership relations. Walkthrough Q&A 2026-05-05 caught a factual error in the analysis doc (claimed `metabolites_by_gene.top_pathways` traversed `Reaction → KeggTerm`; **actually traverses `Metabolite → KeggTerm` via `m.pathway_ids` denorm**, with `p.reaction_count >= 3` as a target-node gate, not a traversal). | **Adopt Option A naming convention** (terminology in analysis doc; tool-rename a separate slice if pursued): `metabolite_pathways` (compound-anchored, what `list_metabolites` / `metabolites_by_gene` surface today via `m.pathway_ids`); `ko_pathways` (gene-KO-anchored — already KO-anchored on ontology tools via `ontology="kegg"`, no rename needed); `reaction_pathways` (reaction-anchored via `Reaction_in_kegg_pathway`, not surfaced today, reserved for future). **Envelope key:** `top_pathways → top_metabolite_pathways`. **Per-row keys inside the list:** `metabolite_pathway_id` + `metabolite_pathway_name` (anchor-prefixed for clarity; supersedes `pathway_id`/`pathway_name` and replaces the `term_id`/`term_name` convention used by ontology tools — those stay on ontology tools, this is a different anchor). **Apply across all tools that surface compound-anchored pathway rollups.** Tool-side rename is a P1 follow-up; lands with Pass A surface refresh. **Updated in this run** (analysis doc Track A1 §c1 + §f rewritten with anchor-prefixed terms; factual error fixed). | P1 | build-derived (walkthrough Q&A 2026-05-05) |

---

## Part 3 — Metabolomics-measurement surface (greenfield)

### 3a — Existing-tool modifications

How existing MCP tools should expose measurement data, given that node-level rollups already exist (per Part 1 §1.2). Sorted P0 → P3.

| Tool | Current surfacing | Recommended change | Priority | Phase |
|---|---|---|---|---|
| `list_metabolites` | `gene_count`, `transporter_count`, `pathway_count`, `evidence_sources` per row | Add `measured_assay_count`, `measured_paper_count`, `measured_organisms` per row (pass-through from Metabolite node — already pre-computed). Add `measured_compartments` per row (**sparse — only emitted when `measured_assay_count > 0`**; cross-ref §4.3.5 on compartment semantics — one Metabolite node × N assays at different compartments). Add envelope `by_measurement_coverage` (counts at 0 / 1 / 2 papers; counts by compartment). **Open scoping (walkthrough 2026-05-05):** (a) sparse-field policy — omit key entirely vs include with empty list — pick one and apply consistently across measurement-side fields; (b) `measured_compartments` is not currently on the Metabolite node (only `measured_organisms` is) — either denormalize KG-side (match `measured_organisms` pattern) or aggregate explorer-side via `MATCH (m)<-[:Assay_quantifies_metabolite]-(a) RETURN collect(DISTINCT a.compartment)`. Decide before Pass A. | P0 | first-pass |
| `list_publications` | See Part 2 TODO | **Covered by Part 2** — same proposal (per-row `metabolite_count`, `metabolite_assay_count`, `metabolite_compartments` pass-through). Pass A scope. | P0 | (cross-ref Part 2) |
| `list_experiments` | See Part 2 TODO | **Covered by Part 2** — same proposal. Pass A scope. Routing hint when non-zero: drill via `run_cypher` until Track B native tool ships (audit Part 3b.1 / 3b.3). | P0 | (cross-ref Part 2) |
| `list_organisms` | Chemistry rollups present; measurement absent | Per-row `measured_metabolite_count` (pass-through from Organism node). Envelope `by_measurement_capability` as a **2-bucket count** — `{has_metabolomics: N, no_metabolomics: M}` — not a top-10 ranking. **Rationale (walkthrough 2026-05-05):** only 4 of 37 organisms have any metabolomics data, so a top-10 envelope is overkill at current scale; the binary "covered / not covered" split is more honest. | P1 | first-pass |
| `list_filter_values` | `compartment` filter type returns observed compartments; missing entries possibly | Verify `extracellular` is present in returned compartment list (KG release added it). Add `omics_type` filter type returning the canonical list including `METABOLOMICS` | P1 | first-pass |
| `kg_schema` | Returns full schema with all metabolomics nodes/edges | No change — Part 1 §1.2 confirmed introspection is correct and complete | — | first-pass (no change) |

**P0 summary (3 items):** `list_metabolites`, `list_publications`, `list_experiments` all need measurement-rollup pass-through. All data exists on nodes — no KG change required. This is the foundation for the Track-B discovery workflow.

#### 3a — build-derived rows (second pass)

| Tool | Current surfacing | Recommended change | Priority | Phase |
|---|---|---|---|---|
| `list_metabolites` | Confirmed empirically: per-row schema includes `gene_count`, `transporter_count`, `pathway_count`, `evidence_sources` — but NOT `measured_assay_count`, `measured_paper_count`, `measured_organisms` despite all three being on the Metabolite node | (Validates the first-pass P0 row.) Rephrase: this is **confirmed required** — without it, the LLM cannot use `list_metabolites` to find "measured-and-transport-able" metabolites in one call. Surfaced by scenario 1 `discover` | P0 | build-derived (validates first-pass) |
| `list_metabolites` envelope (pathway naming) | `top_pathways[].pathway_id`/`pathway_name` | **See Part 2 build-derived "Cross-cutting top_pathways" row** — canonical decision lives there. Envelope key → `top_metabolite_pathways`; per-row keys → `metabolite_pathway_id`/`metabolite_pathway_name`. Same convention applies to `metabolites_by_gene` and any future compound-anchored chemistry tool. | P1 | (cross-ref Part 2) |
| `list_metabolites` envelope (other) | `top_organisms[].organism_name` (not `preferred_name`); `by_evidence_source` is a list of dicts, not a flat dict | Two separate axes: (1) organism key — `organism_name` is what list_organisms uses too, so this is consistent across tools; the `preferred_name` reference was an audit-side typo. **Mark verified-consistent, no change.** (2) `by_evidence_source` shape — list-of-dicts is the standard envelope rollup shape used by other tools (`by_organism`, `by_category`, etc.); no change. | — | (verified consistent) |

### 3b — New-tool proposals

Each candidate gets a paragraph + signature sketch + `{recommendation, phase}`. Pending-definition entries name their blocking Part 4 question(s).

#### 3b.1 `list_metabolite_assays`

Discovery surface for `MetaboliteAssay` nodes — mirrors `list_experiments` per-assay and the parameter naming follows `list_derived_metrics` (the closest sibling discovery tool).

```python
list_metabolite_assays(
    search_text: str | None = None,                      # Lucene — matches sibling discovery tools
    organism: str | None = None,                         # singular str (not organism_names list) — matches list_derived_metrics
    metric_types: list[str] | None = None,
    value_kind: Literal['numeric', 'boolean'] | None = None,
    compartment: str | None = None,                      # str not Literal — KG may add new compartments; matches list_derived_metrics
    treatment_type: list[str] | None = None,             # singular — matches sibling discovery tools
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,            # singular
    experiment_ids: list[str] | None = None,
    assay_ids: list[str] | None = None,                  # batch specific-ID lookup; parallel to derived_metric_ids
    metabolite_ids: list[str] | None = None,             # unique to assays — find assays measuring specific compounds
    rankable: bool | None = None,                        # MetaboliteAssay node carries `rankable` (verified 2026-05-05); parallels list_derived_metrics
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> dict
```

**Filters intentionally omitted (compared to `list_derived_metrics`):**
- `omics_type` — assays are inherently METABOLOMICS; redundant.
- `has_p_value` — `MetaboliteAssay` node carries no p-value flag in the schema; not applicable. Add only if the KG gains an analog.

**Per-row** (verified against `MetaboliteAssay` node properties 2026-05-05; parallels `list_derived_metrics` row schema where applicable):

| Field | Source | Notes |
|---|---|---|
| `assay_id` | node `id` | renamed for clarity (parallels DM's `derived_metric_id`) |
| `name` | node | parallels DM |
| `organism_name` | node | parallels DM |
| `experiment_id` | node | parallels DM |
| `publication_doi` | node | parallels DM |
| `compartment` | node | parallels DM |
| `value_kind` | node | parallels DM (numeric / boolean — no categorical for assays) |
| `metric_type` | node | parallels DM |
| `treatment_type` | node | parallels DM |
| `treatment` | node | assay-specific (string detail beyond treatment_type) |
| `background_factors` | node | parallels DM |
| `growth_phases` | node | parallels DM |
| `unit` | node | parallels DM |
| `field_description` | node | parallels DM |
| `omics_type` | node | parallels DM (always METABOLOMICS for assays) |
| `rankable` | node | parallels DM — assay node carries this flag |
| `total_metabolite_count` | node | parallels DM's `total_gene_count` |
| `aggregation_method` | node | assay-specific |
| `light_condition` | node | assay-specific |
| `experimental_context` | node | assay-specific |
| `value_min` / `value_q1` / `value_median` / `value_q3` / `value_max` | node | distribution stats precomputed on assay node; not surfaced in DM today but available |
| `time_points` | edge aggregation | `collect(DISTINCT r.time_point)` across this assay's edges |

**Excluded (not on assay node, would require unhelpful aggregation):**
- `n_replicates` — varies per (metabolite × condition × timepoint); surface at edge-level via 3b.3 `metabolites_by_assay` instead.
- `allowed_categories` — DM-only; no categorical assays in current data.

**Envelope:** `by_compartment`, `by_value_kind`, `by_organism`, `top_metric_types`, `total_assay_count`, `total_metabolite_count` — parallels DM envelope shape.

**Justification:** structural — there's a node type with rich properties and no discovery tool. The 10-assay scale is small but the property graph is rich; all 8 metabolomics experiments are reachable today only via run_cypher.

**Recommendation: Should-add (P1).** Phase: first-pass.

#### 3b.2 `metabolite_response_profile`

Cross-experiment per-metabolite summary mirroring `gene_response_profile` — for each metabolite, summarise how it responds across treatments / growth phases / compartments.

```python
metabolite_response_profile(
    metabolite_ids: list[str],
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    compartment: str | None = None,
    summary: bool = False,
    limit: int = 25,
) -> dict
```

Per-row: `metabolite_id`, `preferred_name`, `compartments_observed`, `n_assays`, `n_papers`, `value_stats` (min/median/max/sd across edges), `direction_stats` (when fold-change semantic resolves), `n_replicates_total`, `top_treatments`. Envelope: `by_compartment`, `by_treatment_type`, `top_metabolites_by_response_breadth`.

**Recommendation: DEFER (premature).** Blocking Part 4 questions: §4.3.2 (FC relevance for metabolomics), §4.3.3 (replicate rollup convention), §4.3.5 (compartment semantics for cross-compartment comparison). **Walkthrough Q&A 2026-05-05:** marked premature for current scale (10 assays / 92 metabolites measured in both compartments / 2 papers). Reasons: (a) Part 4 questions unresolved; (b) at present scale a dedicated cross-experiment per-metabolite summary tool is not justified — `run_cypher` covers it adequately, and the side-by-side compartment shape demonstrated in scenario `measurement` is sufficient; (c) the future `differential_metabolite_abundance` (3b.4) may subsume part of this surface once FC semantics resolve. Revisit when measurement scale grows materially OR when Part 4 questions answer.

Phase: deferred.

#### 3b.3 Assay drill-down family — split per DM convention

The DM family pattern: **drill-down split by value_kind** (`genes_by_numeric_metric` + `genes_by_boolean_metric` + `genes_by_categorical_metric`); **batch reverse-lookup merged** (`gene_derived_metrics`, polymorphic `value`).

Apply the same pattern to assays. Empirical justification: the two assay edges differ substantially (verified 2026-05-05) — `Assay_quantifies_metabolite` carries 15 fields including `value`/`value_sd`/`replicate_values`/`metric_percentile`/`metric_bucket`/`rank_by_metric`/`detection_status`/`time_point`/`time_point_hours`/`time_point_order`; `Assay_flags_metabolite` carries 6 fields (just `flag_value`/`n_positive` + common). Merging into one drill-down would force a heavily-union row schema (60% sparse fields for flags rows).

Three tools in this slice:

##### 3b.3.a `metabolites_by_quantifies_assay`

Numeric drill-down — analog of `genes_by_numeric_metric`.

```python
metabolites_by_quantifies_assay(
    assay_ids: list[str],
    metabolite_ids: list[str] | None = None,
    metric_bucket: list[str] | None = None,
    metric_percentile_min: float | None = None,
    metric_percentile_max: float | None = None,
    rank_by_metric_max: int | None = None,
    value_min: float | None = None,
    value_max: float | None = None,
    detection_status: list[str] | None = None,
    time_point: list[str] | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> dict
# row: metabolite_id, name, value, value_sd, replicate_values, n_replicates, n_non_zero,
#      metric_type, metric_bucket, metric_percentile, rank_by_metric, detection_status,
#      time_point, time_point_hours, time_point_order, condition_label, assay_id
```

##### 3b.3.b `metabolites_by_flags_assay`

Boolean drill-down — analog of `genes_by_boolean_metric`.

```python
metabolites_by_flags_assay(
    assay_ids: list[str],
    metabolite_ids: list[str] | None = None,
    flag_value: bool | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> dict
# row: metabolite_id, name, flag_value, n_positive, n_replicates, metric_type,
#      condition_label, assay_id
```

##### 3b.3.c `assays_by_metabolite`

Batch reverse-lookup — analog of `gene_derived_metrics`. Merged across edge types with polymorphic `value` column.

```python
assays_by_metabolite(
    metabolite_ids: list[str],
    organism: str | None = None,
    evidence_kind: Literal['quantifies', 'flags'] | None = None,   # filter by edge type if needed
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> dict
# row: assay_id, organism_name, compartment, metric_type, evidence_kind,
#      value (numeric arm only), flag_value (boolean arm only), n_replicates,
#      time_point (numeric arm only), condition_label, experiment_id, publication_doi
# not_found / not_matched buckets for diagnosability (parallel to gene_derived_metrics)
```

**Recommendation: Should-add (P1).** Phase: first-pass.

#### 3b.4 `differential_metabolite_abundance`

DE-shaped tool for metabolite measurements. Inputs: experiment + condition pair; output: per-metabolite log-ratio (or comparable summary) + dispersion + significance.

**Recommendation: DEFER (premature; may never happen).** Blocking Part 4 questions: §4.3.2 (FC vs other statistics), §4.3.3 (replicate rollup), §4.3.4 (Quantifies vs Flags merging), §4.3.5 (within-vs-cross-compartment), §4.3.7 (cross-organism comparability for coculture).

**Walkthrough Q&A 2026-05-05:** premature for current scale (10 assays / 92 metabolites measured / 2 papers). The "may never happen" note is empirical: §4.3.2 may resolve that FC is *not* the right summary statistic for metabolomics — the schema already declines to commit to FC and instead carries raw `value` + `value_sd` + `metric_percentile` + `rank_by_metric` (Part 1 §1.5 / Part 4 §4.3.2). If Part 4 §4.3.2 confirms FC is wrong, this tool's natural shape evaporates and the right surface is per-metabolite percentile/rank context (already exposed via the 3b.3 quantifies drill-down). Revisit only if (a) measurement scale grows materially AND (b) Part 4 §4.3.2 + §4.3.4 resolve in favor of a DE-style aggregate.

Phase: deferred.

#### 3b.5 DM-family extension to Metabolite entity

The DM tool family (`list_derived_metrics`, `gene_derived_metrics`, `genes_by_*_metric`) currently targets Gene as the entity. Extending to also target Metabolite would let the KG model metabolomics summary statistics (rhythmicity, condition response, etc.) the same way it models gene-level rhythmicity / amplitudes today.

Looking at Part 1 §1.2: `MetaboliteAssay` is structurally similar to `DerivedMetric` (both are `InformationContentEntity`; both carry `value_kind`, `metric_type`, `value_max/median/min/q1/q3`, etc.). This suggests the KG modellers were thinking along these lines.

**Recommendation: NOT-NEEDED (downgraded build-derived).** Originally Pending-definition (Part 4 §4.3.1 / §4.3.6). Build-derived second pass concluded the KG modellers already answered §4.3.1 implicitly: `MetaboliteAssay` IS the DM-on-Metabolite analog (same `value_kind` / `metric_type` / `value_max/median/min/q1/q3` fields). Direct future metabolite-summary work onto `MetaboliteAssay`-anchored tools instead. See build-derived second pass below.

Phase: not-needed.

#### 3b.6 First-pass summary

| Proposal | Recommendation | Phase | Blocked by |
|---|---|---|---|
| `list_metabolite_assays` | Should-add (P1) | first-pass | — |
| `metabolite_response_profile` | DEFER (premature at current scale) | deferred | §4.3.2, §4.3.3, §4.3.5; revisit when scale grows |
| `metabolites_by_quantifies_assay` + `metabolites_by_flags_assay` + `assays_by_metabolite` | Should-add (P1) — split per DM convention; drill-down split by edge type, reverse-lookup merged | first-pass | — |
| `differential_metabolite_abundance` | DEFER (premature; may never happen — depends on §4.3.2 FC-relevance resolution) | deferred | §4.3.2, §4.3.3, §4.3.4, §4.3.5, §4.3.7 |
| DM-family extension to Metabolite | NOT-NEEDED (downgraded build-derived) | not-needed | (resolved — Assay IS the DM-on-Metabolite analog) |

**Verdict (post-walkthrough 2026-05-05):** Two ship-now slices = 4 tools total (3b.1 `list_metabolite_assays`; 3b.3 split into `metabolites_by_quantifies_assay` + `metabolites_by_flags_assay` + `assays_by_metabolite`). Two DEFER (3b.2 premature; 3b.4 premature, may never happen). One NOT-NEEDED (3b.5). Net forward path: 4 tools, all unblocked by Part 4 questions.

#### 3b — build-derived (second pass)

No new tool proposals from the build phase — the existing first-pass surface (5 candidates) covers the workflow gaps observed during the analysis doc and example python builds. The build did however **validate** the existing proposals:

| First-pass proposal | Build-derived verdict |
|---|---|
| `list_metabolite_assays` | **Validated.** Scenario `measurement` `measurement` had to use `run_cypher` because no native discovery tool exists for assays. Confirms Should-add (P1). |
| `metabolite_response_profile` | **Pattern validated, but recommendation flipped to DEFER (premature)** at walkthrough Q&A 2026-05-05. Scenario `measurement` (`measurement`) demonstrates the per-metabolite × compartment aggregation in run_cypher and it is adequate at the current 10-assay / 92-metabolite / 2-paper scale. Add the dedicated tool only when (a) Part 4 questions resolve AND (b) measurement scale grows materially OR `differential_metabolite_abundance` (3b.4) lands and absorbs part of this surface. |
| `metabolites_by_quantifies_assay` + `metabolites_by_flags_assay` + `assays_by_metabolite` (split per DM convention 2026-05-05) | **Pattern validated; surface refined.** Scenario `measurement` walks the assay → metabolite path. Walkthrough Q&A 2026-05-05: split drill-down by edge type per DM family precedent (Quantifies edge = 15 fields, Flags edge = 6 fields — 9-field difference makes union row schema heavily sparse). Reverse lookup stays merged with polymorphic `value`/`flag_value`. Should-add stands. |
| `differential_metabolite_abundance` | **Flipped to DEFER (premature; may never happen)** at walkthrough Q&A 2026-05-05. Scenario `measurement`'s raw values are clearly per-replicate concentrations; FC is not the natural summary. The schema empirically declines FC and the 3b.3 quantifies drill-down already exposes percentile/rank context — if §4.3.2 confirms FC is wrong for metabolomics, this tool's shape evaporates entirely. |
| DM-family extension to Metabolite | **Empirical evidence shifted toward Assay-only modelling.** Per Part 1 §1.2, `MetaboliteAssay` already carries the same fields a `DerivedMetric` would (value_kind, metric_type, percentiles, etc.). The KG modellers appear to have answered Part 4 §4.3.1 implicitly: Assay IS the DM-on-Metabolite analog. Recommendation: downgrade DM-family extension from Pending-definition to **Not-needed** — direct any metabolite-level summary work onto `MetaboliteAssay`-anchored tools instead. |

---

## Part 4 — Open definition questions

Organised by metabolite-source pipeline. Each question states the issue, names the options where enumerable, and lists the Part 3b proposals it blocks. Resolved questions live in §4.0 (numbered IDs preserved for back-references).

### 4.0 Resolved (or empirically resolved)

Questions that have been answered during design, build, or walkthrough. Numbered IDs preserved so cross-references in the rest of the doc + skill content + KG asks remain stable.

#### 4.1.1 Reaction edge directionality / role — RESOLVED (option c, 2026-05-04)

**Question:** Does `Reaction_has_metabolite` distinguish substrate from product, or only "involved in"?

**Resolution:** option (c). The KEGG-source annotation direction is unreliable upstream, so propagating it as a `role` property would surface false confidence rather than help. The KG stays undirected; explorer tools must use "involved in" framing as the **permanent** convention, not a transitional one.

**Implication for tools:** `metabolites_by_gene` and `genes_by_metabolite` row docstrings must say "involved in" (never "produces" / "consumes") for metabolism-arm rows. Analysis doc Track A1 caveat is now permanent. KG-MET-003 retired (see Part 5).

#### 4.1.4 Currency-cofactor confounder in metabolism rollups — RESOLVED (workflow-side, 2026-05-05)

**Question:** `top_metabolites` rollup in `metabolites_by_gene` is sorted by gene_count. For cross-feeding (Workflow B′), this is exactly the wrong sort: the highest-reach compounds across any non-trivial gene set are universal cofactors (H2O, ATP/ADP/AMP, Pi, PPi, NAD(P)(H), CO2). The bridge degenerates to "both organisms have water and ATP."

**Resolution:** workflow-side mitigation, no KG ask. The KG should not flag currency cofactors itself — what counts as "currency" is task-dependent (e.g., glutamate/glutamine are central-N currency in N-flux contexts but real signals in nutrient-class contexts). The mitigation is a tool-side post-filter against a minimal-8 blacklist (H2O, CO2, ATP, ADP, AMP, Pi, PPi, NAD(P)(H)), extensible per workflow.

**Implication for tools:** analysis doc Track A §d caveat now lists this as confounder #1 of three for Workflow B′. Example python `examples/metabolites.py::CURRENCY_METABOLITES_MIN8` provides the canonical blacklist constant. No tool API change needed.

**Empirical evidence:** seed PMM0001–PMM0005 (housekeeping) returned top_metabolites = {H2O, PPi, Glu, Gln, ATP, ADP, Pi, DNA, PRPP, dATP} — 7/10 currency or activated cofactors. Replacement biologically-motivated seed (6 N-metabolism genes via `genes_by_ontology(ontology='kegg', term_ids=['kegg.pathway:ko00910'])`) returned {nitrate, ammonia, nitrite, cyanate, Glu, Gln, H+, H2O, ATP, ADP} — minimal-8 blacklist drops 3, leaves 7 N-relevant compounds.

#### 4.1.2 Reaction reversibility — RESOLVED (annotation data insufficient, 2026-05-05)

**Question:** Is reaction reversibility represented?

**Resolution:** No. The Reaction node carries no `is_reversible` property (verified Part 1 §1.2 schema dump). Combined with §4.1.1 (no direction either), this means KG reaction annotations lack the data to support either direction or reversibility claims. The explorer must commit to the "involved in" framing as permanent — same conclusion as §4.1.1, extended to cover reversibility.

**Implication for tools (MCP must document thoroughly to avoid confusion):**
- `metabolites_by_gene` + `genes_by_metabolite` reaction-arm row docstrings: explicitly say "reaction edges are undirected AND carry no reversibility flag — interpret all reaction-arm rows as 'involved in', never 'produces'/'consumes'/'reversible'."
- Analysis doc Track A1: extend the "involved in" caveat to also call out the reversibility gap.
- Tracked as a Part 2 build-derived docstring TODO (rows for `metabolites_by_gene` + `genes_by_metabolite` + analysis-doc Track A1).

**Implication for KG asks:** none new. KG-MET-009 (was: add `is_reversible`) becomes moot — annotation upstream is insufficient. Mark KG-MET-009 RETIRED in Part 5 next time we touch it.

#### 4.3.1 + 4.3.6 Surface modelling — Assay IS the DM-on-Metabolite analog — RESOLVED (empirically, 2026-05-04 build-derived)

**Question (§4.3.1):** Is `MetaboliteAssay` the *only* measurement surface, or should there also be `DerivedMetric` nodes attached to `Metabolite` (mirroring `DerivedMetric → Gene` for gene-level summaries)?

**Same question, tool-surface framing (§4.3.6):** Should DM family extend to Metabolite, or stay Gene-only?

**Resolution:** Empirical evidence from the KG release shifted toward Assay-only. Per Part 1 §1.2, `MetaboliteAssay` already carries the same fields a `DerivedMetric` would (`value_kind`, `metric_type`, `value_max/median/min/q1/q3`, `unit`). The KG modellers appear to have answered §4.3.1 implicitly: **Assay IS the DM-on-Metabolite analog.**

**Implication for tools:** Part 3b.5 (DM-family extension to Metabolite) downgraded to NOT-NEEDED. Direct future metabolite-level summary work onto `MetaboliteAssay`-anchored tools (3b.1, 3b.3) instead.

---

### 4.1 Reaction (KEGG) source

(§4.1.1 + §4.1.2 + §4.1.4 resolved — see §4.0.)

#### 4.1.3 Multi-subunit enzymes

**Question:** When a reaction needs multiple gene products, are all subunits attributed to the reaction (1 reaction × N gene edges) or is there explicit complex modelling?

**Why it matters:** Naive counting would overstate "genes that catalyse reaction X" by a factor of subunit count.

**Current state:** unclear from schema. Likely 1 reaction × N gene edges. No `complex_id` property visible.

**Blocks:** ortholog-side chemistry rollups (`gene_homologs`, `genes_by_homolog_group`); affects whether group-level coverage is "any member" or weighted.

### 4.2 Transport (TCDB) source

#### 4.2.1 Transport direction (import vs export)

**Question:** Is import vs export representable per-family or per-(family, substrate) pair?

**Why it matters:** Some TCDB families have curated directionality. For cross-feeding workflows (`metabolites_by_gene` → `genes_by_metabolite` Workflow B′), direction would let us claim "MED4 exports X, ALT imports X" instead of just "both touch X."

**Current state:** edge has `id` only; no `direction` property. TcdbFamily node has no direction property visible.

**Options:**
- (a) Add `direction` property on `Tcdb_family_transports_metabolite` edge.
- (b) Add per-family `default_direction` on TcdbFamily node.
- (c) Stay undirected; document limitation.

**Blocks:** cross-feeding causal claims (analysis doc Track A combined §d).

#### 4.2.2 Curated primary substrate vs family-inferred substrate

**Question:** TcdbFamily already has `superfamily` (Part 1 §1.3). For non-superfamily families with many curated substrates, is one substrate the family's "primary"?

**Why it matters:** family_inferred dominance auto-warning could rank within-family substrates by primary-vs-secondary instead of treating them all equally.

**Current state:** no `is_primary` property on edge or node; the `<none>`-superfamily families (605 families, 7886 substrate links) average 13 substrates each — wide enough to benefit from ranking.

**Blocks:** sharper precision-tier reasoning in the example python's `precision_tier` scenario.

### 4.3 Metabolomics measurement source

(§4.3.1 + §4.3.6 resolved — see §4.0.)

#### 4.3.2 Fold-change vs other summary statistics

**Question:** Is fold-change the right summary statistic for metabolomics, or do we need a different convention?

**Empirical note:** Existing edges carry `value` (concentration), `value_sd`, `n_replicates`, `metric_percentile`, `metric_bucket`, `rank_by_metric` — all suggesting the KG modellers have already declined to commit to a single FC-style summary and instead carry raw values + percentile/rank context. **The user's intuition that FC may not apply is empirically supported by the schema.**

**Blocks:** Part 3b.2 (`metabolite_response_profile`), Part 3b.4 (`differential_metabolite_abundance`).

#### 4.3.3 Replicate rollup convention

**Question:** When a tool surfaces a value per metabolite, is it the mean across replicates, the median, or per-replicate rows?

**Empirical note:** Edges carry both `value` (single number, presumably aggregated) and `replicate_values` (list). Both are present, so consumers can choose. The open question is which to default to in tool envelopes.

**Blocks:** Part 3b.2, Part 3b.4.

#### 4.3.4 Quantifies vs Flags semantics — separate or merged

**Question:** `Assay_quantifies_metabolite` (concentration/intensity) and `Assay_flags_metabolite` (qualitative detection) carry different properties. Should new tools surface them as separate response columns (with `evidence_kind` discriminator) or merge them?

**Current state:** they are structurally distinct edges; the natural shape is to keep them separate but with a unifying `evidence_kind` field.

**Blocks:** Part 3b.4 (DE-shape tool needs to decide how to handle flag-only data).

#### 4.3.5 Compartment semantics

**Question:** `MetaboliteAssay` carries `compartment` as a string property (`whole_cell` | `extracellular`). Is the *same* metabolite measured in both compartments treated as one Metabolite node (with two edges) or two distinct Metabolite nodes?

**Current state:** appears to be one Metabolite × two assays (whole_cell + extracellular); compartment is on the Assay, not the Metabolite. Verify with a query in second pass.

**Blocks:** Part 3b.2 (response profile across compartments).

#### 4.3.7 Cross-organism comparability in coculture

**Question:** When a coculture experiment profiles both partners, can a metabolite measurement be attributed to one partner vs the other, or only to the joint medium?

**Current state:** assays carry `organism_name`. For monoculture this is unambiguous; for coculture, does the KG record the host organism or the medium?

**Blocks:** Part 3b.4 (differential abundance becomes cross-organism-ambiguous).

#### 4.3.8 Replicate / temporal axis

**Question:** Edges carry `time_point`, `time_point_hours`, `time_point_order` — same axis as expression DE? What's the relationship between metabolomics and expression timepoints?

**Current state:** schema is symmetric; need empirical check that timepoints align with `Changes_expression_of` timepoints in the same experiments.

**Blocks:** Part 3b.2 (response profile that crosses expression and metabolomics).

### 4.4 Question-to-proposal blocking matrix

Resolved questions live in §4.0 and don't appear here (they don't block anything). Only open questions and what they gate.

| Question | Blocks proposal |
|---|---|
| §4.1.3 multi-subunit | gene_homologs / homolog-group rollups (Part 2 — but those proposals are now DROPPED per gene-side reframe; question stays open for future ortholog work) |
| §4.2.1 transport direction | (none in 3b; affects Track A combined §d — confounder #3 of Workflow B′ §4.5) |
| §4.2.2 primary substrate | (none in 3b; sharpens precision_tier scenario; confounder #2 of Workflow B′ §4.5) |
| §4.3.2 FC relevance | 3b.2 (DEFER), 3b.4 (DEFER) |
| §4.3.3 replicate rollup | 3b.2 (DEFER), 3b.4 (DEFER) |
| §4.3.4 Quantifies vs Flags | 3b.4 (DEFER) |
| §4.3.5 compartment semantics | 3b.2 (DEFER); also gates `list_metabolites.measured_compartments` sparse-field policy (Part 3a) |
| §4.3.7 coculture attribution | 3b.4 (DEFER) |
| §4.3.8 temporal axis | 3b.2 (DEFER) |

### 4.5 Workflow B′ (cross-feeding bridge) — three-confounder synthesis

The cross-feeding bridge (`metabolites_by_gene` → `genes_by_metabolite` across organisms) has three structural confounders that compound; the analysis doc Track A §d caveat lists them as a single table. They are individually addressed in §4.1.4 / §4.2.2 / §4.2.1 above; this section synthesises so the bridge's net unmitigable risk is visible in one place.

| # | Confounder | Arm | Mitigation today | Status / KG ask |
|---|---|---|---|---|
| 1 | Currency-cofactor flooding (top_metabolites sorted by gene_count) | metabolism | Workflow-side: post-filter against minimal-8 blacklist (`examples/metabolites.py::CURRENCY_METABOLITES_MIN8`) | §4.1.4 — RESOLVED workflow-side |
| 2 | Family-level transport casts a wide net (ABC superfamily → ~554 metabolites/gene). Both tiers are annotations, not ground truth — transporter specificity is often promiscuous or under-characterized in nature. The gap between `substrate_confirmed` and `family_inferred` is more about curation effort than biological certainty. | transport | Filter call is question-shape-dependent: cross-feeding *inferences* (this workflow) → use `substrate_confirmed` for the conservative cast (~87% narrower; missing real family-level promiscuity is the lesser risk). Broad-screen *candidate* questions (e.g. `n_source_de`) → no filter; family_inferred captures the real N-uptake biology (PMM0263 amt1, PMM0628 gltS) that substrate_confirmed silently excludes. | §4.2.2 — sharpened by KG-MET-006 (is_promiscuous flag, P2) |
| 3 | Transport polarity not encoded | transport | None — surface as "compatible with cross-feeding", never confirmed | §4.2.1 — KG-MET-011 P2 (transport direction) |

**Net for Workflow B′:** confounders #1 and #2 are fully mitigable workflow-side today (no KG dependency); #3 is unmitigable and forces the "compatible with" framing regardless of filter aggressiveness. Track-B measurement layer can corroborate but not confirm causality — see analysis doc Track B §a.

**Empirical validation (2026-05-05):** the canonical example (`examples/metabolites.py --scenario cross_feeding`) uses 6 MED4 N-metabolism genes (cyn cluster + glnA + glsF) seeded via `genes_by_ontology(ontology='kegg', term_ids=['kegg.pathway:ko00910'])` and returns interpretable cross-feeding candidates: ALT CmpA/NrtA-family nitrate ABC transporters across 5 strains for the transport arm, ammonia-involved enzymes (5-oxoprolinase, hydroxymethylbilane synthase) for the metabolism arm. With all three mitigations applied, the bridge produces a non-trivial answer.

---

## Part 5 — KG-side asks

Items only `multiomics_biocypher_kg` can fix. Each ask carries `{category, priority, phase, why}`. Categories: Data gap / Precompute / Rollup / Index / Schema / Decision / Documentation.

| ID | Category | Priority | Phase | Ask | Why (explorer item it unblocks) |
|---|---|---|---|---|---|
| KG-MET-001 | Documentation | P1 | first-pass | Document the normalisation convention used for `Assay_quantifies_metabolite.value` per paper (raw concentration? log-transformed? z-score?) — and whether `value_sd` is on the same scale | Resolves Part 4 §4.3.3 (replicate rollup convention); needed for tool docstrings explaining what `value` means to the LLM |
| KG-MET-002 | Decision + Documentation | P2 | first-pass | Compartment-as-property is the chosen modelling. Document the convention: `Metabolite` node is compartment-agnostic; `MetaboliteAssay.compartment` carries the compartment. Verify no Metabolite node has compartment in its name/properties (i.e., glucose-intracellular and glucose-extracellular are the same Metabolite) | Resolves Part 4 §4.3.5 (compartment semantics); needed for analysis doc Track B |
| KG-MET-003 | Data gap | — | RETIRED 2026-05-04 | (Was: add `role` property on `Reaction_has_metabolite`.) **Retired** — upstream KEGG-source annotation direction is unreliable, so propagating it as `role` would create false confidence. Resolution to Part 4 §4.1.1 is option (c): stay undirected, "involved in" framing is permanent. | n/a — explorer-side tools simply commit to the "involved in" framing as their permanent convention |
| KG-MET-004 | Rollup | — | first-pass (CLOSED — already satisfied) | Per-Metabolite measurement rollups already on the node: `measured_assay_count`, `measured_paper_count`, `measured_organisms` | (verified in Part 1 §1.2 — no action needed) |
| KG-MET-005 | Rollup | — | first-pass (CLOSED — already satisfied) | Per-Publication / per-Experiment / per-Organism measurement rollups already exist: `metabolite_assay_count`, `metabolite_count`, `metabolite_compartments`, `measured_metabolite_count` | (verified in Part 1 §1.2) |
| KG-MET-006 | Precompute | P2 | first-pass | TcdbFamily.superfamily exists. Add: per-family `is_promiscuous` boolean (true when superfamily ∈ {large set} OR `member_count` > threshold OR `metabolite_count` > threshold) so explorer tools can dim/rank without re-deriving the rule | Sharper family_inferred precision-tier reasoning (Part 4 §4.2.2; analysis doc Track A2 §g). Today the explorer recomputes the rule client-side or via per-query joins |
| KG-MET-007 | Index | P3 | first-pass (deferred) | Audit-Phase-E-derived index asks — populated based on the slowest queries observed during example python build | Performance for new tool query paths; populated in second pass once query shapes stabilise |
| KG-MET-008 | Documentation | P3 | first-pass | Document each metabolomics paper's processed-value pipeline: extraction method, MS platform, internal standards, normalisation, replicate count, statistical-test convention. Likely surfaces as a Publication-node `processing_notes` field | LLM-readable provenance for Track-B caveat surfacing; reduces ambiguity when the LLM cites a measurement |
| KG-MET-009 | Data gap | — | RETIRED 2026-05-05 | (Was: add `is_reversible` boolean on Reaction node.) **Retired** — KEGG-source annotation lacks reversibility data upstream; same conclusion as KG-MET-003 retirement (Part 4 §4.1.1). Combined with no direction, the Reaction node cannot support either claim. Explorer commits to "involved in" framing as permanent. Resolution to Part 4 §4.1.2 = annotation insufficient. | n/a — explorer-side tools document the dual gap (no direction + no reversibility) in docstrings + analysis doc |
| KG-MET-010 | Data gap | P3 | first-pass | Multi-subunit enzyme complex modelling (e.g., `complex_id` on Reaction or Gene_catalyzes_reaction edges) | Resolves Part 4 §4.1.3; allows ortholog-side rollups to weight by complex membership |
| KG-MET-011 | Data gap | P2 | first-pass | Transport direction (import vs export) on Tcdb_family_transports_metabolite edges OR per-family default_direction on TcdbFamily | Resolves Part 4 §4.2.1; enables cross-feeding causal claims |
| KG-MET-012 | Decision | P2 | first-pass | Decide whether metabolite-level summary statistics (rhythmicity, etc.) should attach as `DerivedMetric → Metabolite` edges or live entirely on `MetaboliteAssay` properties. Communicate decision to explorer side | Resolves Part 4 §4.3.1 / §4.3.6; unblocks Part 3b.5 (DM-family extension to Metabolite) |
| KG-MET-013 | Documentation | P2 | first-pass | Confirm `time_point` properties on `Assay_quantifies_metabolite` align with `Changes_expression_of.time_point` for experiments that have both omics types | Resolves Part 4 §4.3.8; enables future cross-omics tools |

**Priority summary (first-pass, after 2026-05-04 retirement of KG-MET-003 + 2026-05-05 retirement of KG-MET-009):** 0× P0, 1× P1 (KG-MET-001), 5× P2 (KG-MET-002/006/011/012/013), 3× P3 (KG-MET-007 deferred / 008 / 010), 2× CLOSED (KG-MET-004/005), 2× RETIRED (KG-MET-003 / 009) = 13 first-pass asks.

**Surprising finding (revised):** the original spec assumed many KG asks would land in P0/P1 (data is missing). The actual KG release shipped much further than expected — node-level rollups exist, edge schemas are rich, family promiscuity is partially flagged. The originally-flagged P0 (reaction role) was retired by user decision because upstream KEGG annotation direction is unreliable. **There are no remaining P0 KG asks.** The chemistry-annotation track's "involved in" framing is now a permanent convention, not a transitional limitation.

### Part 5 — build-derived KG asks (second pass)

| ID | Category | Priority | Phase | Ask | Why |
|---|---|---|---|---|---|
| KG-MET-014 | Documentation | P3 | build-derived | Document the metabolite-ID prefix convention prominently in `kg_schema` output and tool docstrings (KEGG IDs are stored as `kegg.compound:Cxxxxx`, not bare `Cxxxxx`) | Caused first-attempt query failures during scenario 2 `compound_to_genes` — bare `C00064` returned 0 rows; the prefixed form returned 42. Cheap docstring win |
| KG-MET-015 | Documentation | P3 | build-derived | Document organism-name resolution rules: chemistry tools (e.g., `genes_by_metabolite(organism='MED4')`) accept short-name aliases, but `list_organisms(organism_names=['MED4'])` requires the full `preferred_name` (`Prochlorococcus MED4`) | Surfaces during scenario 1 `discover` first-attempt; minor friction but confusing without docs |
| KG-MET-007 (resolved) | Index | — | build-derived (NO INDEX ASKS) | Audit-Phase-D scenarios all completed in <30s aggregate (scenario 5 longest at ~8s due to multi-step DE chain). No slow queries observed. KG-MET-007 closes with no concrete index requests; revisit in next round | Performance baseline confirmed acceptable for current scale. |

**Final Part 5 totals (refreshed walkthrough Q&A 2026-05-05):** 15 numbered KG asks. **0× P0** (no P0 asks remain), 1× P1 (KG-MET-001 normalisation docs), 5× P2 (KG-MET-002/006/011/012/013), 5× P3 (KG-MET-008/010/014/015 + KG-MET-007 deferred), 2× CLOSED (KG-MET-004/005 rollup-already-shipped), 2× RETIRED (KG-MET-003 reaction direction; KG-MET-009 reaction reversibility — both KEGG-source upstream gaps). The KG release substantially overshipped relative to design-time assumptions.
