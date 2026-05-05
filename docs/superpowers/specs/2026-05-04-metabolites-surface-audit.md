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
| `genes_by_function` | Per-row chemistry hint (was P1 PENDING) | **DROPPED 2026-05-05.** Text-search rows are shape-specific (user already has a question); row narrative wants match score + functional snippet, not chemistry. Chain to `gene_overview` from returned locus_tags is one call away — already canonical. No empirical scenario in example python required this. |
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

**P1 (1):** `list_organisms` (measurement-rollup extension). [`genes_by_function` chemistry hints DROPPED 2026-05-05 — see DROP table.]

**Docstring-only (no per-row change):** `genes_by_ontology`, `pathway_enrichment`, `cluster_enrichment`, `list_derived_metrics`, `gene_details`. P2/P3 routing hints in docs; all lower-effort than P0 plumbing.

**Cross-cut:** all TODO items are pure pass-through. No tool needs new Cypher — only Pydantic envelope/row-model expansion + query SELECT list.

### Part 2 — build-derived rows (second pass)

| Tool | Current chemistry surfacing | Recommended change | Priority | Phase |
|---|---|---|---|---|
| `differential_expression_by_gene` | Accepts `direction` parameter but rejects `'both'` (only `'up'` / `'down'`) | Either accept `'both'` (run both internally and merge) OR document the limitation in the docstring + raise a clearer error message naming the alternative (omit param to get both directions). Surfaced by example python scenario `n_source_de` — initial code used `direction='both'` mirroring `pathway_enrichment` and crashed with `Invalid direction 'both'`. **Decision (walkthrough Q&A 2026-05-05): ACCEPT `'both'`** — run both internally and merge (matches `pathway_enrichment` convention). | P2 | build-derived (scenario 5 `n_source_de`) |
| `genes_by_metabolite` | Per-row schema is **union** by evidence_source (metabolism rows have `reaction_id`/`reaction_name`/`ec_numbers`/`mass_balance`; transport rows have `transport_confidence`/`tcdb_family_id`/`tcdb_family_name`) — neither set is documented as conditional in the docstring | Document the union shape explicitly in the tool description; consider surfacing `transport_confidence: None` and `reaction_id: None` keys in metabolism/transport rows respectively for shape consistency. **Decision (walkthrough Q&A 2026-05-05): BOTH** — (a) document union shape AND (b) surface explicit `None` for cross-arm fields so every row has identical key set. Cleaner schema for downstream code; row-fattening cost is trivial (~6 extra `None` keys per row). Apply symmetrically to `metabolites_by_gene`. | P2 | build-derived (scenarios 2 `compound_to_genes` + 6 `tcdb_chain` — required arm-specific result printing logic) |
| `metabolites_by_gene` | Same union shape as `genes_by_metabolite` | Same — document union shape AND surface `None` for cross-arm fields. **Decision (walkthrough Q&A 2026-05-05): BOTH** (cross-ref `genes_by_metabolite` row above). | P2 | build-derived (scenario 3 `gene_to_metabolites`) |
| `metabolites_by_gene` (summary mode) | `summary=True` returns `top_genes=None` even when results exist (observed for small inputs) | Investigate: is `top_genes` only populated when input list is large enough? Document threshold or fix to always populate. Workaround used: extract gene set from non-summary `results` directly. **Decision (walkthrough Q&A 2026-05-05): INVESTIGATE during Pass A** — root-cause first, then fix-or-document. | P3 | build-derived (scenario 5 `n_source_de`) |
| `search_ontology` | Kwarg is `search_text`, not `query` (initially confused) | The discoverability is fine via signature inspection but the analysis-doc patterns and existing `pathway_enrichment.py` use `query=` style elsewhere. Consider accepting both `query=` and `search_text=` aliases for ergonomics | P3 | build-derived (scenario 6 `tcdb_chain`) |
| `list_metabolites` | Free-text search kwarg is `search`, not `search_text` — **outlier** across the 8 list/search tools (7 of 8 use `search_text`: `list_experiments`, `list_publications`, `list_clustering_analyses`, `list_derived_metrics`, `search_ontology`, `search_homolog_groups`, `genes_by_function`). | Rename `list_metabolites(search=)` → `list_metabolites(search_text=)` for consistency. Breaking change, but only 2 internal call sites today (example python `compound_to_genes` scenario; analysis doc Track A1 §c1) — both controlled. Update tool signature + 2 call sites + tests in one slice. **Decision (walkthrough Q&A 2026-05-05): APPROVED** — lands with Pass A. | P2 | build-derived (walkthrough Q&A 2026-05-05) |
| `metabolites_by_gene` + `genes_by_metabolite` reaction-arm docstring | Reaction-arm rows have no direction (§4.1.1) AND no reversibility flag (§4.1.2 resolved 2026-05-05). Tool docstrings don't currently spell this out. | Document thoroughly: explicit "reaction edges are undirected AND carry no reversibility flag — interpret all reaction-arm rows as 'involved in', never 'produces'/'consumes'/'reversible'." Analysis doc Track A1 caveat must be extended to call out the reversibility gap alongside the existing direction caveat. Apply to both tools' YAML chaining/mistakes sections. **Decision (walkthrough Q&A 2026-05-05): APPROVED** — lands with Pass A YAML pass. | P3 | build-derived (walkthrough Q&A 2026-05-05) |
| `list_metabolites` (name-search discoverability) | `search` parameter exists and works (e.g., `search='glutamine'` returns 4 matches) but is **not surfaced in the analysis doc decision tree** as the canonical name→ID hook. Most user-facing questions arrive by metabolite NAME, not by KEGG ID. | Surface name→ID lookup as an explicit decision-tree branch: `list_metabolites(search='...')` precedes any compound-anchored chain. **Updated in this run (analysis doc + scenario `compound_to_genes` now demonstrates the two-step chain).** | P3 | build-derived (walkthrough Q&A 2026-05-05) |
| `metabolites_by_gene` / `genes_by_metabolite` `by_element` semantics | Envelope rollup is **presence-only** (count of distinct compounds containing each element at all) — **not stoichiometric** (no atom counts per compound; stoichiometry lives in `metabolite.formula`) and **not mass-balanced** (KG carries no substrate-vs-product role on `Reaction_has_metabolite`, Part 4 §4.1.1 resolved). Per-row `elements` field has the same shape (set of symbols, no counts). Tool docstrings don't make this explicit. | Document `by_element` semantics in tool description: "count of distinct compounds in `total_matching` containing each element". Note that mass-balanced flux is intentionally not surfaced. **Updated in this run (analysis doc Track A1 §c1 now spells this out).** | P3 | build-derived (walkthrough Q&A 2026-05-05) |
| `genes_by_metabolite` + `metabolites_by_gene` family_inferred-dominance warning text | Both tools emit a warning prescribing `transport_confidence='substrate_confirmed'` as a "high-precision" tighten action (functions.py:5197 and :5775). The wording predates the §g reframing: "Re-run with transport_confidence='substrate_confirmed' for substrate-curated transporter genes only" / "For high-precision substrate-curated annotations only, set transport_confidence='substrate_confirmed'". | Soften to informational + question-shape-aware: "Most transport rows are family_inferred (X of Y) — annotations rolled up from family-level transport potential. Use `substrate_confirmed` for conservative-cast questions (e.g. cross-organism inference); keep family_inferred for broad-screen candidate enumeration. See analysis-doc §g — both tiers are annotations, neither is ground truth." Drop A7 `precision_tier` scenario — A6 + §g already cover this teaching. **Decision (walkthrough Q&A 2026-05-05): APPROVED** — lands with Pass A. | P3 | build-derived (walkthrough Q&A 2026-05-05; A7 dropped same commit) |
| **Cross-cutting:** `top_pathways` envelope-key + per-row naming across all tools presenting metabolite pathways (`list_metabolites`, `metabolites_by_gene`; eventually any other compound-anchored chemistry tool) | The word "pathway" is overloaded across compound-anchored and KO-anchored surfaces — both reach the same KEGG pathway maps but via different membership relations. Walkthrough Q&A 2026-05-05 caught a factual error in the analysis doc (claimed `metabolites_by_gene.top_pathways` traversed `Reaction → KeggTerm`; **actually traverses `Metabolite → KeggTerm` via `m.pathway_ids` denorm**, with `p.reaction_count >= 3` as a target-node gate, not a traversal). | **Adopt Option A naming convention** (terminology in analysis doc; tool-rename a separate slice if pursued): `metabolite_pathways` (compound-anchored, what `list_metabolites` / `metabolites_by_gene` surface today via `m.pathway_ids`); `ko_pathways` (gene-KO-anchored — already KO-anchored on ontology tools via `ontology="kegg"`, no rename needed); `reaction_pathways` (reaction-anchored via `Reaction_in_kegg_pathway`, not surfaced today, reserved for future). **Envelope key:** `top_pathways → top_metabolite_pathways`. **Per-row keys inside the list:** `metabolite_pathway_id` + `metabolite_pathway_name` (anchor-prefixed for clarity; supersedes `pathway_id`/`pathway_name` and replaces the `term_id`/`term_name` convention used by ontology tools — those stay on ontology tools, this is a different anchor). **Apply across all tools that surface compound-anchored pathway rollups.** Tool-side rename is a P1 follow-up; lands with Pass A surface refresh. **Updated in this run** (analysis doc Track A1 §c1 + §f rewritten with anchor-prefixed terms; factual error fixed). **Decision (walkthrough Q&A 2026-05-05): APPROVED** — tool-rename lands with Pass A. | P1 | build-derived (walkthrough Q&A 2026-05-05) |
| **Cross-cutting:** `exclude_metabolite_ids` filter on compound-anchored tools (`metabolites_by_gene`, `genes_by_metabolite`, `list_metabolites`) | No way today to exclude specific metabolite IDs. §4.5 confounder #1 (currency-cofactor flooding — ATP / H2O / CO2 dominate `top_metabolites` rollups by gene_count) is mitigated only via client-side blacklist in `examples/metabolites.py::CURRENCY_METABOLITES_MIN8`, applied post-hoc by the example python. The tool layer is unaware. | Add `exclude_metabolite_ids: list[str] \| None = None` parameter (**option (a)** — primitive negative filter mirroring the existing `metabolite_ids` include semantics; user-controlled, no server-side opinion). Pushes §4.5 confounder #1 mitigation into the tool layer where envelope rollups can also benefit. **Defer** the opinionated `exclude_currency_cofactors=True` default (option (b/c)) until usage shows callers consistently re-discover currency flooding — revisit if it comes up in Pass-A user testing. | P2 | build-derived (walkthrough Q&A 2026-05-05) |

---

## Part 3 — Metabolomics-measurement surface (greenfield)

### 3a — Existing-tool modifications

How existing MCP tools should expose measurement data, given that node-level rollups already exist (per Part 1 §1.2). Sorted P0 → P3.

| Tool | Current surfacing | Recommended change | Priority | Phase |
|---|---|---|---|---|
| `list_metabolites` | `gene_count`, `transporter_count`, `pathway_count`, `evidence_sources` per row | Add `measured_assay_count`, `measured_paper_count`, `measured_organisms` per row (pass-through from Metabolite node — already pre-computed). Add `measured_compartments` per row (**sparse-field policy — omit key entirely when `measured_assay_count == 0`; populate as `list[str]` otherwise**; cross-ref §4.3.5 on compartment semantics — one Metabolite node × N assays at different compartments). Add envelope `by_measurement_coverage` (counts at 0 / 1 / 2 papers; counts by compartment). **Scoping resolved (walkthrough Q&A 2026-05-05):** (a) sparse-field policy = omit-key-when-empty (apply consistently across measurement-side fields). (b) compute location = **KG precompute** — denormalize as `measured_compartments` on Metabolite node (mirrors `measured_organisms` pattern). New ask logged as **KG-MET-016 P2** in Part 5 5.A Live; `list_metabolites` consumes pass-through once shipped. | P0 | first-pass |
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
# envelope: by_detection_status (counts of detected/sporadic/not_detected — primary headline
#           summary per §4.3.3 resolution), by_metric_bucket, by_assay, total_metabolite_count
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

**Implication for tools:** analysis doc Track A §d caveat now lists this as confounder #1 of three for Workflow B′. Example python `examples/metabolites.py::CURRENCY_METABOLITES_MIN8` provides the canonical blacklist constant. **Pass-A enhancement queued (Part 2 build-derived, 2026-05-05):** add `exclude_metabolite_ids: list[str] | None = None` to compound-anchored tools (`metabolites_by_gene`, `genes_by_metabolite`, `list_metabolites`) — primitive negative filter mirroring the existing `metabolite_ids` include semantics. Pushes the workflow-side mitigation into the tool layer (envelope rollups also benefit). Opinionated `exclude_currency_cofactors=True` default deferred until usage data shows the need (consistent with "what counts as currency is task-dependent" — start with primitive, escalate only if callers re-discover the flooding pattern).

**Empirical evidence:** seed PMM0001–PMM0005 (housekeeping) returned top_metabolites = {H2O, PPi, Glu, Gln, ATP, ADP, Pi, DNA, PRPP, dATP} — 7/10 currency or activated cofactors. Replacement biologically-motivated seed (6 N-metabolism genes via `genes_by_ontology(ontology='kegg', term_ids=['kegg.pathway:ko00910'])`) returned {nitrate, ammonia, nitrite, cyanate, Glu, Gln, H+, H2O, ATP, ADP} — minimal-8 blacklist drops 3, leaves 7 N-relevant compounds.

#### 4.1.2 Reaction reversibility — RESOLVED (annotation data insufficient, 2026-05-05)

**Question:** Is reaction reversibility represented?

**Resolution:** No. The Reaction node carries no `is_reversible` property (verified Part 1 §1.2 schema dump). Combined with §4.1.1 (no direction either), this means KG reaction annotations lack the data to support either direction or reversibility claims. The explorer must commit to the "involved in" framing as permanent — same conclusion as §4.1.1, extended to cover reversibility.

**Implication for tools (MCP must document thoroughly to avoid confusion):**
- `metabolites_by_gene` + `genes_by_metabolite` reaction-arm row docstrings: explicitly say "reaction edges are undirected AND carry no reversibility flag — interpret all reaction-arm rows as 'involved in', never 'produces'/'consumes'/'reversible'."
- Analysis doc Track A1: extend the "involved in" caveat to also call out the reversibility gap.
- Tracked as a Part 2 build-derived docstring TODO (rows for `metabolites_by_gene` + `genes_by_metabolite` + analysis-doc Track A1).

**Implication for KG asks:** none new. KG-MET-009 (was: add `is_reversible`) becomes moot — annotation upstream is insufficient. Mark KG-MET-009 RETIRED in Part 5 next time we touch it.

#### 4.1.3 Multi-subunit enzymes — RESOLVED (annotation data insufficient + no remaining consumer, 2026-05-05)

**Question:** When a reaction needs multiple gene products, are all subunits attributed to the reaction (1 reaction × N gene edges) or is there explicit complex modelling?

**Resolution:** Same retirement pattern as §4.1.1 / §4.1.2 — KEGG itself has no first-class complex/holo-enzyme modeling. KEGG's relational structure is `REACTION ↔ KO` (orthology groups) and `REACTION ↔ EC` (enzyme classification); multi-subunit info lives only in free-text ENZYME entry descriptions OR is implicit in multiple KO groups sharing a reaction. There is no upstream `complex_id` to propagate. (UniProt and BioCyc have explicit Complex nodes; KEGG does not.) Plus the question's original consumer (Part 2 ortholog-side chemistry rollups) was DROPPED in the gene-side reframe — even if the data existed, no proposal would consume it.

**Implication for tools:** none. Naive 1-reaction × N-gene-edge counting may overstate "genes that catalyse reaction X" by subunit count, but no downstream consumer cares today.

**Implication for KG asks:** KG-MET-010 RETIRED 2026-05-05. Annotation upstream insufficient; would only have been consumed by a now-DROPPED proposal.

#### 4.2.1 Transport direction (import vs export) — RESOLVED (annotation insufficient; heuristic rejected, 2026-05-05)

**Question:** Is import vs export representable per-family or per-(family, substrate) pair?

**Resolution:** No. The KG is a direct reflection of TCDB; TCDB carries no `direction` property on family or substrate edges. Three options were considered:
- **(a)** Skip; accept the gap. **Chosen.**
- **(b)** Heuristic name-matching on `tcdb_family_name` (uptake / efflux / importer / exporter / permease keywords) — rejected. Heuristics are lossy in the wrong way (antiporter/symporter move both directions simultaneously; "ABC superfamily" too broad; false confidence on cross-feeding-relevant edges where direction matters most). Same false-confidence trap that retired KG-MET-003.
- **(c)** Hand-curated TCDB-family direction map — rejected for now (effort cost outweighs current cross-feeding workflow demand; revisit if cross-feeding becomes a major use case).

**Implication for tools:** §4.5 Workflow B′ confounder #3 stays unmitigable. Cross-feeding analyses must surface as "compatible with cross-feeding", never "confirmed cross-feeding". Track-B measurement layer can corroborate (extracellular elevation in coculture) but cannot establish direction.

**Implication for KG asks:** KG-MET-011 RETIRED 2026-05-05. Annotation upstream insufficient; heuristic and curation alternatives both rejected.

#### 4.2.2 Curated primary substrate vs family-inferred substrate — RESOLVED (annotation insufficient, 2026-05-05)

**Question:** For non-superfamily TCDB families with many curated substrates, is one substrate the family's "primary"?

**Resolution:** No upstream data. TCDB carries no `is_primary` flag on family or substrate edges (verified user check 2026-05-05). Same retirement pattern as §4.1.1 / §4.1.2 / §4.1.3 / §4.2.1 — KG cannot propagate what's not there. Plus the question's original consumer (`precision_tier` scenario in example python) was DROPPED in the walkthrough — A6 + analysis-doc §g cover the substrate_confirmed/family_inferred reading without needing a primary-substrate signal.

**Implication for tools:** none. The within-family substrate ranking that would have powered "the family's primary substrate is X, but this transporter's specific substrate is Y" is unavailable. §g's question-shape framing (substrate_confirmed for conservative cast; no filter for broad screen) is the right answer at the tool surface.

**Implication for KG asks:** no new retirement. **KG-MET-006 stays alive** — it's a *separate* concept (per-family `is_promiscuous` precompute based on member_count / metabolite_count thresholds, not per-substrate primary ranking). KG-MET-006 still has value for the §4.5 confounder #2 reading; preserved as P2.

#### 4.3.2 Fold-change vs other summary statistics — RESOLVED (FC rejected; replication + detection + rank fields replace it, 2026-05-05)

**Question:** Is fold-change the right summary statistic for metabolomics, or do we need a different convention?

**Resolution:** No. FC is rejected. The schema already provides a richer signal via existing edge fields:

| Field | Source | Tells you |
|---|---|---|
| `detection_status` (enum: `detected` / `sporadic` / `not_detected`) | Quantifies edges | curator-graded detection call — three-state nuance beyond binary present/absent |
| `n_replicates` | Quantifies + Flags edges | sampling intensity |
| `n_non_zero` | Quantifies edges | detection reliability (how often above LOD) |
| `n_positive` | Flags edges | qualitative detection frequency |
| `value_sd` | Quantifies edges | within-condition variability |
| `metric_percentile` / `metric_bucket` / `rank_by_metric` | Quantifies edges | position within the assay's distribution |

Together these answer "is metabolite X consistently and detectably present?" — what FC would proxy for in transcriptomics. In metabolomics, the absolute-concentration + LOD framing is more honest: many measurements are at LOD (zeros are common), and ratios blow up under those conditions. The `detection_status` enum is particularly informative — it lets the LLM say "metabolite X is `sporadic`" without inventing a threshold.

**Implication for tools:** the 3b.3 quantifies/flags drill-downs already surface these fields per row (verified 2026-05-05 schema probe). Tools just need pass-through, not new statistical convention.

**Implication for proposals:** Part 3b.4 (`differential_metabolite_abundance`) stays DEFER (already so) — its premise weakens further. If a downstream FC-style summary is ever needed, it should be computed by consumers using the raw edge fields, not baked into a tool surface.

#### 4.3.3 Replicate rollup convention — RESOLVED (don't impose; surface raw fields + by_detection_status envelope, 2026-05-05)

**Question:** When a tool surfaces a value per metabolite, is it the mean across replicates, the median, or per-replicate rows?

**Resolution:** Don't pick. Same spirit as §4.3.2 — surface the rich field set the KG already exposes, let consumers choose:

- **Per-row** (Quantifies edges): `value` (KG-pre-aggregated single number), `value_sd`, `replicate_values` (list of per-replicate values for consumers who want a different rollup), `n_replicates`, `n_non_zero`, `detection_status`.
- **Envelope:** `by_detection_status` (counts of `detected` / `sporadic` / `not_detected` across the slice). This sidesteps the central-tendency question entirely by making the detection-reliability distribution the headline summary — more informative than "average value" when many measurements are at LOD.

**Implication for tools:**
- 3b.3 quantifies drill-down (`metabolites_by_quantifies_assay`): include `by_detection_status` in the envelope rollup spec.
- 3b.1 `list_metabolite_assays`: doesn't aggregate per-replicate; no change needed.
- 3b.4 (`differential_metabolite_abundance`) stays DEFER — its premise of choosing a single summary continues to weaken.

**Implication for KG asks:** none. KG-MET-001 (normalisation docs) still stands at P1 — separate concern (what does `value` mean per paper, units / log-scale / z-score).

#### 4.3.4 Quantifies vs Flags semantics — separate or merged — RESOLVED (split per DM convention, 2026-05-05)

**Question:** `Assay_quantifies_metabolite` (concentration/intensity) and `Assay_flags_metabolite` (qualitative detection) carry different properties. Should new tools surface them as separate response columns (with `evidence_kind` discriminator) or merge them?

**Resolution:** **Both, by tool layer** — same pattern as the DM family.

- **Drill-down: split.** `metabolites_by_quantifies_assay` (numeric arm) + `metabolites_by_flags_assay` (boolean arm) — separate tools. Per-tool row schemas stay clean (no union sparseness). Empirical justification: 9-field gap between the two edges (Quantifies = 15 fields, Flags = 6); merged drill-down would be 60% sparse for flags rows.
- **Batch reverse-lookup: merged.** `assays_by_metabolite` — single tool with `evidence_kind: Literal['quantifies', 'flags']` discriminator + polymorphic `value` / `flag_value` columns per row.

This mirrors the DM family precedent (split drill-down across `genes_by_numeric_metric` / `genes_by_boolean_metric` / `genes_by_categorical_metric`; batch reverse-lookup merged in `gene_derived_metrics`).

**Implication for tools:** see Part 3b.3 — three-tool split shipped together as a slice. Already specified.

#### 4.3.5 Compartment semantics — RESOLVED (one Metabolite node shared across all organisms + compartments, 2026-05-05)

**Question:** When the same metabolite is measured in both compartments, treated as one Metabolite node (with two edges) or two distinct Metabolite nodes?

**Resolution (user confirmation 2026-05-05):** **one Metabolite node shared across all organisms AND all compartments.** Compartment lives on the `MetaboliteAssay` edge property, not on the Metabolite node. Glucose intracellular and glucose extracellular in MED4, MIT9301, etc. are all the same `kegg.compound:C00031` node — disambiguation is via assay attachment, not node duplication.

**Implication for tools:**
- `list_metabolites` rows: per-row `measured_compartments` (sparse, only when `measured_assay_count > 0`) is the correct shape — collects `DISTINCT a.compartment` across attached assays. Already specced in Part 3a.
- Cross-compartment comparison (e.g., scenario `measurement` Step 2 side-by-side print) works because the same metabolite_id appears once with multiple assay edges.
- `metabolite_response_profile` (3b.2 DEFER) — when revisited, no compartment-disambiguation logic needed at the entity layer.

**Implication for KG asks:** KG-MET-002 (documentation ask) **stays alive** at P2 — the verification piece is checked off (one Metabolite node confirmed) but the explicit KG-side docstring documenting "Metabolite node is compartment-agnostic; compartment lives on MetaboliteAssay" is still useful for downstream consumers.

#### 4.3.7 Cross-organism comparability in coculture — RESOLVED (paper-method-dependent; not applicable to current data, 2026-05-05)

**Question:** When a coculture experiment profiles both partners, can a metabolite measurement be attributed to one partner vs the other, or only to the joint medium?

**Resolution (user 2026-05-05):** Paper-method-dependent. Some experimental designs allow per-partner attribution (e.g., physical separation, isotope labeling); others can only resolve the joint medium. The KG records this where applicable via analysis-node / edge properties + paper-level methodological context. Tools shouldn't bake in a single attribution convention — surface the per-paper context and let consumers interpret.

**Not applicable to current data:** the 2 metabolomics papers in the KG today (Kujawinski et al. 2022 — phosphorus + growth-phase axenic monocultures; chitobiose 2023 — carbon-source axenic) are NOT coculture metabolomics. The question doesn't surface in any current scenario.

**Implication for tools:** none today. When coculture metabolomics papers land, tools should expose per-paper method context (likely via the planned `MetaboliteAssay` properties + Publication-node `processing_notes` field — see KG-MET-008 P3).

**Implication for KG asks:** **KG-MET-008** (per-paper processing notes documentation, P3) **stays alive** — it covers this and the wider provenance question. No new ask.

#### 4.3.8 Replicate / temporal axis — RESOLVED (paper/experiment-design-dependent, 2026-05-05)

**Question:** Edges carry `time_point`, `time_point_hours`, `time_point_order` — same axis as expression DE? What's the relationship between metabolomics and expression timepoints?

**Resolution (user 2026-05-05):** Paper-method-dependent. Same `Experiment` node in the KG should imply the same time-axis (assays + expression edges sharing an experiment share their time origin). But actual alignment across measurement modalities depends on experiment design — sometimes samples were collected at the same timepoints, sometimes offset, sometimes at different cadences. Tools shouldn't assume alignment universally.

**Implication for tools:** when surfacing time-correlated cross-omics views (e.g., "metabolite X concentration ↔ gene Y expression at the same timepoint"), tools must filter or join by `experiment_id` first AND surface the timepoint values explicitly so consumers can verify alignment per case. Don't infer cross-omics co-timing from raw `time_point` matching alone.

**Implication for KG asks:** **KG-MET-013** (was: confirm time_point alignment) reframed but stays alive at P2. Now: document per-experiment which timepoints align across omics modalities (i.e., the `Experiment` node could carry a flag or note when cross-omics samples share collection timepoints). Resolves naturally with KG-MET-008 (per-paper processing notes).

#### 4.3.1 + 4.3.6 Surface modelling — Assay IS the DM-on-Metabolite analog — RESOLVED (empirically, 2026-05-04 build-derived)

**Question (§4.3.1):** Is `MetaboliteAssay` the *only* measurement surface, or should there also be `DerivedMetric` nodes attached to `Metabolite` (mirroring `DerivedMetric → Gene` for gene-level summaries)?

**Same question, tool-surface framing (§4.3.6):** Should DM family extend to Metabolite, or stay Gene-only?

**Resolution:** Empirical evidence from the KG release shifted toward Assay-only. Per Part 1 §1.2, `MetaboliteAssay` already carries the same fields a `DerivedMetric` would (`value_kind`, `metric_type`, `value_max/median/min/q1/q3`, `unit`). The KG modellers appear to have answered §4.3.1 implicitly: **Assay IS the DM-on-Metabolite analog.**

**Implication for tools:** Part 3b.5 (DM-family extension to Metabolite) downgraded to NOT-NEEDED. Direct future metabolite-level summary work onto `MetaboliteAssay`-anchored tools (3b.1, 3b.3) instead.

**Implication for KG asks:** KG-MET-012 RETIRED 2026-05-05. The decision the ask requested is implicitly answered (Assay-only), and the only remaining downstream consumer (3b.5) is NOT-NEEDED — no consumer remains. See Part 5.

---

### 4.1 Reaction (KEGG) source

All four sub-questions resolved (§4.1.1 direction, §4.1.2 reversibility, §4.1.3 multi-subunit, §4.1.4 currency cofactor) — see §4.0.

### 4.2 Transport (TCDB) source

Both sub-questions resolved (§4.2.1 direction, §4.2.2 primary substrate) — see §4.0.

### 4.3 Metabolomics measurement source

All eight sub-questions resolved (§4.3.1–§4.3.8) — see §4.0.

### 4.4 Question-to-proposal blocking matrix

**All Part 4 sub-questions resolved as of 2026-05-05** — see §4.0. No proposals remain blocked on a Part 4 question. The two DEFERed proposals (3b.2 `metabolite_response_profile`, 3b.4 `differential_metabolite_abundance`) are deferred on **scale**, not on definition.

### 4.5 Workflow B′ (cross-feeding bridge) — three-confounder synthesis

The cross-feeding bridge (`metabolites_by_gene` → `genes_by_metabolite` across organisms) has three structural confounders that compound; the analysis doc Track A §d caveat lists them as a single table. They are individually addressed in §4.0 (resolved entries for §4.1.4, §4.2.1, §4.2.2); this section synthesises so the bridge's net unmitigable risk is visible in one place.

| # | Confounder | Arm | Mitigation today | Status / KG ask |
|---|---|---|---|---|
| 1 | Currency-cofactor flooding (top_metabolites sorted by gene_count) | metabolism | Workflow-side: post-filter against minimal-8 blacklist (`examples/metabolites.py::CURRENCY_METABOLITES_MIN8`) | §4.1.4 — RESOLVED workflow-side. Pass-A enhancement queued (Part 2 build-derived): add `exclude_metabolite_ids` filter to compound-anchored tools so the mitigation lives in the tool layer too. |
| 2 | Family-level transport casts a wide net (ABC superfamily → ~554 metabolites/gene). Both tiers are annotations, not ground truth — transporter specificity is often promiscuous or under-characterized in nature. The gap between `substrate_confirmed` and `family_inferred` is more about curation effort than biological certainty. | transport | Filter call is question-shape-dependent: cross-feeding *inferences* (this workflow) → use `substrate_confirmed` for the conservative cast (~87% narrower; missing real family-level promiscuity is the lesser risk). Broad-screen *candidate* questions (e.g. `n_source_de`) → no filter; family_inferred captures the real N-uptake biology (PMM0263 amt1, PMM0628 gltS) that substrate_confirmed silently excludes. | §4.2.2 — sharpened by KG-MET-006 (is_promiscuous flag, P2) |
| 3 | Transport polarity not encoded | transport | None — surface as "compatible with cross-feeding", never confirmed | §4.2.1 — KG-MET-011 RETIRED (TCDB upstream lacks direction; heuristic + curation alternatives rejected). Permanent constraint. |

**Net for Workflow B′:** confounders #1 and #2 are fully mitigable workflow-side today (no KG dependency). #3 is permanently unmitigable — TCDB doesn't carry direction, heuristic alternatives were rejected, and KG-MET-011 is retired. The bridge therefore stays "compatible with cross-feeding" regardless of filter aggressiveness. Track-B measurement layer can corroborate but not confirm causality — see analysis doc Track B §a.

**Empirical validation (2026-05-05):** the canonical example (`examples/metabolites.py --scenario cross_feeding`) uses 6 MED4 N-metabolism genes (cyn cluster + glnA + glsF) seeded via `genes_by_ontology(ontology='kegg', term_ids=['kegg.pathway:ko00910'])` and returns interpretable cross-feeding candidates: ALT CmpA/NrtA-family nitrate ABC transporters across 5 strains for the transport arm, ammonia-involved enzymes (5-oxoprolinase, hydroxymethylbilane synthase) for the metabolism arm. With #1 and #2 mitigated workflow-side and #3 surfaced as "compatible with", the bridge produces a non-trivial answer.

---

## Part 5 — KG-side asks

Items only `multiomics_biocypher_kg` can fix. Each ask carries `{category, priority, phase, why}`. Categories: Data gap / Precompute / Rollup / Index / Schema / Decision / Documentation.

After walkthrough Q&A 2026-05-05, the 15 numbered asks split into three status buckets. **Live** is what the KG team should review; **Closed** and **Retired** are kept for traceability.

### 5.A Live asks (5 — review-required, KG-state verified 2026-05-05)

Verification queries run against the live KG 2026-05-05 (see commit message for query log). Each row carries a **Verified 2026-05-05** finding describing what was found in the live KG and why the ask remains live as scoped.

| ID | Category | Priority | Phase | Ask | Why + Verified state |
|---|---|---|---|---|---|
| KG-MET-001 | Documentation | P1 | first-pass (RESHAPED 2026-05-05) | **Reshaped:** Document that `MetaboliteAssay.field_description` is the canonical normalisation-provenance field (surface this in `kg_schema` output + Publication/Experiment node descriptions). The original ask requested *adding* per-paper normalisation docs; verification showed those docs already exist on the assay node. | **Verified 2026-05-05:** `MetaboliteAssay.field_description` already carries rich, paper-specific provenance. Examples: *"Intracellular metabolite concentration in fg/cell, blank-corrected, replicate-aggregated; Capovilla 2023 Table sd03"* (Capovilla paper) / *"Per-cell intracellular concentration; KEGG-tagged; pre-aggregated by authors. Kujawinski 2023 cellSpecific KEGG export."* (Kujawinski paper). `value_kind`, `unit`, `metric_type`, `aggregation_method` are also on the assay node. The ask now narrows to *making this discoverable* — confirm convention + surface it in schema-doc. **Cross-ref (KG release doc 2026-05-04, `metabolomics-extension.md`):** the release confirms `field_description` is treated as first-class provenance — it's one of four fields indexed in the `metaboliteAssayFullText` full-text index (alongside `name`, `treatment`, `experimental_context`). Reshape-direction is consistent with KG-team intent. |
| KG-MET-002 | Decision + Documentation | P2 | first-pass | Compartment-as-property is the chosen modelling. Document the convention: `Metabolite` node is compartment-agnostic; `MetaboliteAssay.compartment` carries the compartment. | **Verified 2026-05-05:** zero Metabolite nodes have compartment in their name (no matches for `extracellular` / `intracellular` / `cytoplasm` / `compartment` in `m.name`). 92 Metabolite nodes are measured in 2+ compartments — single Metabolite node, multiple `MetaboliteAssay` edges (e.g., Phosphoenolpyruvate, (S)-Malate, D-Glucose 6-phosphate measured in both `whole_cell` and `extracellular`). Convention IS in effect; ask remains a documentation request. |
| KG-MET-006 | Precompute | P2 | first-pass | Add per-TcdbFamily `is_promiscuous` boolean so explorer tools can dim/rank family_inferred rows without re-deriving the rule. | **Verified 2026-05-05:** TcdbFamily node properties = `[tc_class_id, organism_count, metabolite_count, name, tcdb_id, level, level_kind, gene_count, member_count, superfamily, id, preferred_id]`. **No `is_promiscuous` field.** Ask remains live as proposed. |
| KG-MET-013 | Adapter behavior + Documentation | P2 | first-pass (CONCRETE EVIDENCE FOUND) | **Sharpened (2026-05-05 cross-ref):** investigate whether metabolomics-adapter `time_point_hours=-1` for `"T=4"` is intended (sentinel for "couldn't parse to hours") or an adapter parse miss. Capovilla 2023 `field_description` says *"T=4 (3 reps) + T=6 (2 reps)"* where T=4 = day 4 (sample collection day in chitosan time-course). If T=4 should resolve to 96 hours, `-1` is a parse miss. Either fix the parse or document the sentinel convention explicitly. Then either (a) standardise time_point_hours conventions across omics, (b) document `-1` as the sentinel, or (c) document explicitly that cross-omics time_point is not guaranteed aligned. | **Verified 2026-05-05:** real misalignment found. Paper `10.1073/pnas.2213271120` (chitosan addition, MIT9303) has both METABOLOMICS and RNASEQ experiments. METABOLOMICS edge: `time_point="T=4"`, `time_point_hours=-1`, `time_point_order=1`. RNASEQ edge: `time_point="day 1 and day 3"`, `time_point_hours=24`, `time_point_order=1`. Both label as `time_point_order=1` but describe different real-world timings. **Cross-ref (KG release doc 2026-05-04, `metabolomics-extension.md`):** the release doc does not call out a `-1` sentinel convention; the field_description for this assay (*"T=4 (3 reps) + T=6 (2 reps)"*) suggests T=4 = day 4 of sampling, which would be 96 hours — making `-1` more likely an adapter parse miss than an intended sentinel. **Affects future cross-omics tools.** |
| KG-MET-016 | Rollup | P2 | walkthrough-derived | Add `measured_compartments: list[str]` to Metabolite node (sparse — populated only on the 107 measured metabolites). | **Verified 2026-05-05:** Metabolite node lacks `measured_compartments`. Existing per-Metabolite measurement fields = `[measured_assay_count, measured_paper_count, measured_organisms]`. Note: `Organism_has_metabolite` edge already carries `measured_compartments` per (Org, Metabolite) pair — KG team has the per-pair version, just needs to roll up to per-Metabolite at the node. Mirrors the existing `metabolite_compartments` precompute on Publication / Experiment / Organism. **Cross-ref (KG release doc 2026-05-04, `metabolomics-extension.md`):** release explicitly added `Organism_has_metabolite.measured_compartments` (per-pair) alongside `measured_assay_count` / `measured_paper_count` / `measured_organisms` (Metabolite-node rollups, KG-MET-004 / 005 satisfied). The per-Metabolite-node `measured_compartments` is the lone holdout in the otherwise-symmetric measurement-rollup pipeline — pure asymmetric gap, KG team likely has all the upstream data already. |
| KG-MET-015 | Documentation | P3 | build-derived | Document organism-name resolution rules: chemistry tools accept short-name aliases (`'MED4'`); `list_organisms(organism_names=['MED4'])` requires the full `preferred_name`. | **Not KG-state-verifiable** (purely documentation). Friction surfaced during scenario 1 `discover`. |

**Live tally:** 1× P1 (reshaped), 4× P2, 1× P3 = **6 asks** (down from 8 after verification). **No P0 asks remain.** Two precomputes (KG-MET-006 `is_promiscuous`, KG-MET-016 `measured_compartments`); four documentation/decision asks.

### 5.B Closed (5 — already satisfied, no asks found, or verified obsolete)

| ID | Category | Closed reason | Verified at |
|---|---|---|---|
| KG-MET-004 | Rollup | Per-Metabolite measurement rollups already on the node: `measured_assay_count`, `measured_paper_count`, `measured_organisms` | Part 1 §1.2 |
| KG-MET-005 | Rollup | Per-Publication / per-Experiment / per-Organism measurement rollups already exist: `metabolite_assay_count`, `metabolite_count`, `metabolite_compartments`, `measured_metabolite_count` | Part 1 §1.2 |
| KG-MET-007 | Index | Audit-Phase-D scenarios all completed in <30s aggregate (scenario 5 longest at ~8s due to multi-step DE chain). No slow queries observed; no concrete index requests to file. Revisit in next round when query shapes evolve | Phase-D run, 2026-05-04 |
| KG-MET-008 | Documentation | **CLOSED 2026-05-05 (verification-derived).** Was: paper-level `processing_notes` field on Publication. Verified: `MetaboliteAssay.field_description` already carries paper-specific processing provenance per assay (e.g., *"blank-corrected, replicate-aggregated; Capovilla 2023 Table sd03"* / *"pre-aggregated by authors"*). The remaining gap (paper-level vs assay-level framing) is low-value — a publication-summary view would aggregate over assays of the same paper, but the LLM can already extract per-assay provenance. Folded into KG-MET-001's reshape. | Live KG 2026-05-05 |
| KG-MET-014 | Documentation | **CLOSED 2026-05-05 (moved to explorer side).** Was: prominently document the `kegg.compound:` prefix convention. Verified: `Metabolite` node carries BOTH ID forms — `m.id = "kegg.compound:C00001"` (canonical) AND `m.kegg_compound_id = "C00001"` (bare). The friction that motivated this ask (bare `C00064` → 0 rows) only happens because explorer tools query `m.id`. **Solution is explorer-side**: accept bare IDs, resolve via `m.kegg_compound_id`. Logged to `project_backlog.md` as cross-MCP enhancement. | Live KG 2026-05-05 |

### 5.C Retired (5 — out-of-scope: upstream-annotation gaps or no consumer; unchanged by 2026-05-05 verification)

| ID | Category | Retired | Reason |
|---|---|---|---|
| KG-MET-003 | Data gap | 2026-05-04 | (Was: `role` on `Reaction_has_metabolite`.) Upstream KEGG annotation direction unreliable; propagating would create false confidence. Resolution: "involved in" framing is permanent. See §4.0 §4.1.1. |
| KG-MET-009 | Data gap | 2026-05-05 | (Was: `is_reversible` on Reaction.) KEGG lacks reversibility upstream — same gap as MET-003. See §4.0 §4.1.2. |
| KG-MET-010 | Data gap | 2026-05-05 | (Was: `complex_id` on Reaction / Gene_catalyzes_reaction.) KEGG has no first-class complex modelling upstream; the originally-blocking ortholog-side rollups were also DROPPED in the gene-side reframe — no remaining consumer. See §4.0 §4.1.3. |
| KG-MET-011 | Data gap | 2026-05-05 | (Was: transport direction on Tcdb_family_transports_metabolite or per-family default_direction.) TCDB lacks direction upstream; heuristic and curation alternatives both rejected (false-confidence trap). §4.5 confounder #3 stays permanently unmitigable. See §4.0 §4.2.1. |
| KG-MET-012 | Decision | 2026-05-05 | (Was: decide DerivedMetric → Metabolite vs MetaboliteAssay-only modelling.) The KG release implicitly answered §4.3.1/§4.3.6 — `MetaboliteAssay` already carries the DM-equivalent fields. The only remaining downstream consumer (3b.5) is NOT-NEEDED. See §4.0 §4.3.1+§4.3.6. |

### 5.D Final tally

16 numbered asks → **6 Live** (5.A) + **5 Closed** (5.B) + **5 Retired** (5.C), after KG-state verification 2026-05-05. The headline shape: zero data-gap asks remain at P0/P1; the live queue is mostly documentation/decision, plus two precomputes (KG-MET-006 TCDB `is_promiscuous`, KG-MET-016 Metabolite `measured_compartments`). **Verification-derived shifts (2026-05-05):** KG-MET-001 reshaped (provenance data already on `MetaboliteAssay.field_description` — ask narrowed to "make this discoverable"); KG-MET-008 closed (folded into MET-001 reshape — same field provides paper-level processing provenance per assay); KG-MET-014 closed and moved to explorer-side (`Metabolite` node carries both `m.id` prefixed form and `m.kegg_compound_id` bare form — fix is explorer-side bare-ID resolution, not KG documentation). **Surprising finding:** the original spec assumed many asks would land in P0/P1 because data was missing. The actual KG release shipped much further than expected — node-level rollups exist, edge schemas are rich, `field_description` already documents normalisation provenance per assay, family promiscuity is partially flagged via `superfamily`. The "involved in" framing for the chemistry-annotation track is now a permanent convention, not a transitional limitation.
