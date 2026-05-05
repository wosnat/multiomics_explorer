# Tool spec: Phase 1 — P0 pass-through plumbing (metabolites surface refresh)

**Date:** 2026-05-05 (initial); refreshed 2026-05-05 post-rebuild after KG-MET-016 was confirmed Closed (the `list_metabolites` measurement-rollup item moved into this phase from Phase 5).
**Roadmap:** [docs/superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md](../superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md) — Phase 1
**Audit:** [docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md](../superpowers/specs/2026-05-04-metabolites-surface-audit.md) — Parts 2 P0, 2 P2 (filter type), 3a P0/P1, 3a build-derived P1
**KG-side asks (companion):** [docs/kg-specs/2026-05-05-metabolites-surface-asks.md](../kg-specs/2026-05-05-metabolites-surface-asks.md) — KG-MET-001 informs §6.6; KG-MET-006 + KG-MET-016 already Closed.

## Mode

**Mode B (cross-tool small change).** Spec lists 7 tools; Phase 1 is light (KG iteration done in audit + 2026-05-05 post-rebuild verification; schema unchanged); Phase 2 briefings instruct each implementer to "do tool 1 as template, extend to N within your file."

## Purpose

Make existing KG-side metabolite + measurement coverage data visible across the explorer's discovery surface. All seven items are additive, non-breaking, and either pass-through reads of node properties already in the KG or small derived rollups built from existing edges. No KG changes are required — Phase 1 is the "consume what 2026-05 KG release already shipped" pass (KG-MET-006 `is_promiscuous` and KG-MET-016 `Metabolite.measured_compartments` were both confirmed populated post-rebuild on 2026-05-05).

The motivation comes from audit Part 1 §1.2: the KG release shipped per-Publication / per-Experiment / per-OrganismTaxon / per-Metabolite measurement rollups (`metabolite_count`, `metabolite_assay_count`, `metabolite_compartments`, `measured_metabolite_count`, etc.) but the explorer's tool surface ignores them. The empirical consequence is that LLM consumers can't see "this publication has metabolomics data" or "this organism has 92 measured metabolites" without dropping down to `run_cypher`.

## Out of Scope

- **Cross-cutting renames** (`search` → `search_text`, `top_pathways` → `top_metabolite_pathways`, `exclude_metabolite_ids` filter, `direction='both'` on DE). Roadmap Phase 2 — separate slice with breaking-change ergonomics.
- **Compound-anchored tightening** (union-shape `None` padding, family_inferred warning rewrite, reversibility docstring, by_element semantics, search_ontology kwarg alias, `metabolites_by_gene` summary investigation). Roadmap Phase 3.
- **Docstring-only routing hints** (`genes_by_ontology` TCDB pivot, `pathway_enrichment` / `cluster_enrichment` chemistry routing, `list_derived_metrics` chemistry routing, `gene_details` chemistry section). Roadmap Phase 4.
- **New assay tools** (`list_metabolite_assays`, `metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite`). Roadmap Phase 5.
- **Property-level description propagation through BioCypher → Neo4j schema.** KG-side ask (out-of-scope per audit KG-MET-001 venue note). The explorer-side fix here is a curated static enrichment in `kg/schema.py` only.

## Status / Prerequisites

- [x] Scope reviewed with user (roadmap Phase 1, including 2026-05-05 post-rebuild scope refresh that pulled `list_metabolites` measurement rollup in from Phase 5)
- [x] No KG schema changes — all reads target properties already present (verified live 2026-05-05 via `kg_schema()` dump + post-import.sh inspection)
- [x] Cypher drafted for the only non-trivial item (`gene_overview` evidence_sources)
- [x] Cypher re-verified against live KG post-rebuild (5 verification cases in §6.1 all return expected `evidence_sources`)
- [x] All KG dependencies that previously gated this phase are now Closed (KG-MET-016 confirmed populated by post-import L1166-1177)
- [ ] Two pending decisions in §9: `transporter_count` field-name confirmation; `kg_schema` description-dict seed scope
- [ ] Frozen spec approved
- [ ] Ready for Phase 2

## KG dependencies (verified live 2026-05-05)

| Property / Edge | Coverage / Notes |
|---|---|
| `Publication.metabolite_count: int` | present on every publication; non-zero on 2 (Capovilla 2023, Kujawinski 2023) |
| `Publication.metabolite_assay_count: int` | non-zero on same 2 publications |
| `Publication.metabolite_compartments: list[str]` | populated when `metabolite_assay_count > 0`; values from {`whole_cell`, `extracellular`} |
| `Experiment.metabolite_count: int` | non-zero on 8 experiments |
| `Experiment.metabolite_assay_count: int` | non-zero on same 8 experiments |
| `Experiment.metabolite_compartments: list[str]` | populated when `metabolite_assay_count > 0` |
| `OrganismTaxon.measured_metabolite_count: int` | non-zero on 4 organisms (MIT9301, MIT9313, MIT0801, MIT9303) |
| `Gene.reaction_count: int` | precomputed Gene-side rollup; counts catalysed reactions |
| `Gene.metabolite_count: int` | **important semantic note:** at the Gene level this counts **distinct reachable metabolites via either reaction or transport** — different from `OrganismTaxon.metabolite_count` which is reaction-only. Verified live: PMM0392 has `reaction_count=0` and `metabolite_count=554` (all from 8 TCDB families). The list_organisms YAML mistake note about reaction-only semantics applies to OrganismTaxon, not Gene. |
| `Gene.tcdb_family_count: int` + `Gene.cazy_family_count: int` | precomputed gene-side annotation counts |
| `Metabolite.evidence_sources: list[str]` | values from `['metabolism', 'transport', 'metabolomics']` (verified buckets match audit Part 1 §1.1) |
| `Metabolite.measured_assay_count: int` | non-zero on 107 metabolites |
| `Metabolite.measured_paper_count: int` | non-zero on 107 metabolites |
| `Metabolite.measured_organisms: list[str]` | populated from `Organism_has_metabolite` rollup |
| `Metabolite.measured_compartments: list[str]` | populated by post-import L1166-1177 — verified live 2026-05-05 post-rebuild on all 107 measured metabolites; `[]` on the 3111 unmeasured. **Closes KG-MET-016.** |
| `OrganismTaxon.measured_metabolite_count: int` | already verified (4 organisms with non-zero) |
| Edge `Gene_catalyzes_reaction` | Gene → Reaction (precomputes via `reaction_count`) |
| Edge `Gene_has_tcdb_family` | Gene → TcdbFamily |
| Edge `Tcdb_family_transports_metabolite` | TcdbFamily → Metabolite |
| Edge `Reaction_has_metabolite` | Reaction → Metabolite |

## Use cases

- **Discovery routing:** `list_publications()` returning a paper's `metabolite_count > 0` immediately tells the LLM "metabolomics data lives here" without a separate query.
- **Cross-organism comparison:** `list_organisms(summary=True)` envelope shows which organisms have any metabolomics evidence vs none — informs choice of organism for measurement-anchored questions.
- **Gene-level chemistry triage:** `gene_overview(locus_tags=[...])` per-row `evidence_sources` tells the LLM which kinds of metabolite-anchored drill-downs apply (`metabolites_by_gene` always; `genes_by_metabolite` for the partner-organism cross-feeding bridge; future `assays_by_metabolite` for measurement context).
- **Filter discoverability:** `list_filter_values(filter_type='omics_type')` and `list_filter_values(filter_type='evidence_source')` make the canonical filter values discoverable for downstream tool calls.
- **Schema introspection clarity:** `kg_schema()` surfaces `MetaboliteAssay.field_description` (and a curated set of other key-property docstrings) so the LLM doesn't have to scan example values to understand semantics.

---

## 6. Per-tool changes

Sorted by complexity. Items 6.2 – 6.5 + 6.7 are pure pass-through; 6.6 is a small static-data extension; 6.1 is the only one with non-trivial Cypher.

### 6.1 `gene_overview` — chemistry counts + `evidence_sources` per row + `has_chemistry` envelope

**What's changing.** Add four new per-row fields plus one envelope key:

| New field | Source | Semantics |
|---|---|---|
| `reaction_count: int` | `g.reaction_count` (precomputed Gene node property) | Distinct reactions catalysed by gene. Drill via `metabolites_by_gene`. |
| `metabolite_count: int` | `g.metabolite_count` (precomputed Gene node property) | Distinct metabolites reachable via reaction OR transport. **Differs from `OrganismTaxon.metabolite_count` (reaction-only).** |
| `transporter_count: int` | `g.tcdb_family_count` (renamed for surface clarity) | Distinct TCDB families annotated to this gene. (Audit row referred to "transporter_count"; the Gene-node property is `tcdb_family_count`. Rename happens at the response key only.) |
| `evidence_sources: list[str]` | derived (see Cypher below) | Subset of `['metabolism', 'transport', 'metabolomics']` describing which kinds of paths exist from this gene to its metabolites. Path-existence semantics — not metabolite-level rollup. |
| `has_chemistry` (envelope) | summary aggregation | Count of genes in batch with non-empty `evidence_sources`. Mirrors `has_orthologs` / `has_clusters`. |

**Why semantic care matters on `evidence_sources`.** The naive rollup ("union of `m.evidence_sources` across reachable metabolites") would falsely tag a transport-only gene as `metabolism`-evidence whenever its TCDB-reachable metabolites also appear in some reaction elsewhere in the KG. Path-existence semantics — does the GENE participate in a reaction-to-metabolite path? — is what users actually want as a routing hint.

**Cypher (drafted; verification pending KG rebuild).** Per-row evidence_sources logic:

```cypher
UNWIND $locus_tags AS lt
MATCH (g:Gene {locus_tag: lt})
WITH g, lt,
  CASE WHEN EXISTS {
    MATCH (g)-[:Gene_catalyzes_reaction]->(:Reaction)-[:Reaction_has_metabolite]->(:Metabolite)
  } THEN ['metabolism'] ELSE [] END +
  CASE WHEN EXISTS {
    MATCH (g)-[:Gene_has_tcdb_family]->(:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(:Metabolite)
  } THEN ['transport'] ELSE [] END +
  CASE WHEN EXISTS {
    MATCH (g)-[:Gene_catalyzes_reaction]->(:Reaction)-[:Reaction_has_metabolite]->(m:Metabolite)
    WHERE coalesce(m.measured_assay_count, 0) > 0
  } OR EXISTS {
    MATCH (g)-[:Gene_has_tcdb_family]->(:TcdbFamily)-[:Tcdb_family_transports_metabolite]->(m:Metabolite)
    WHERE coalesce(m.measured_assay_count, 0) > 0
  } THEN ['metabolomics'] ELSE [] END AS evidence_sources
RETURN g.locus_tag AS locus_tag, ...,
       coalesce(g.reaction_count, 0) AS reaction_count,
       coalesce(g.metabolite_count, 0) AS metabolite_count,
       coalesce(g.tcdb_family_count, 0) AS transporter_count,
       evidence_sources
ORDER BY g.locus_tag
```

**Verification cases (live KG, 2026-05-05 post-rebuild — all pass):**

| Locus tag | `reaction_count` | `metabolite_count` | `transporter_count` | `evidence_sources` |
|---|---:|---:|---:|---|
| `PMM1428` (EVE domain protein) | 0 | 0 | 0 | `[]` |
| `PMM0001` (housekeeping reaction gene) | 4 | 6 | 0 | `["metabolism"]` |
| `PMM0392` (broad ABC transporter) | 0 | 554 | 8 | `["transport", "metabolomics"]` |
| `PMM0628` (transporter with N-uptake substrate) | 0 | 5 | 1 | `["transport", "metabolomics"]` |
| `PMM0263` (amt1 ammonia transporter) | 0 | 7 | 1 | `["transport"]` |

**Semantic note from verification:** the path-existence Cypher correctly distinguishes path-derived evidence from metabolite-level rollup. PMM0392 has reaction_count=0 — the `EXISTS { (g)-[:Gene_catalyzes_reaction]->...->(:Metabolite) }` subquery returns false even though its 554 transport-reachable metabolites carry `metabolism` on their own `m.evidence_sources`. PMM0263's single reachable metabolite is not in the 107 measured set, so `metabolomics` correctly drops out. An earlier Cypher draft using `g.metabolite_count > 0` as the metabolism gate produced false `metabolism` tags on transport-only genes (e.g. PMM0392 → `["metabolism","transport","metabolomics"]`); the corrected path-existence form is what landed.

**Envelope addition:**

```cypher
... existing summary CTE ...
       size([g IN found WHERE EXISTS {
         MATCH (g)-[:Gene_catalyzes_reaction|Gene_has_tcdb_family]->()-[:Reaction_has_metabolite|Tcdb_family_transports_metabolite]->(:Metabolite)
       }]) AS has_chemistry,
...
```

(Or: compute per-gene evidence_sources first, then count non-empty.)

**About-content updates** (`inputs/tools/gene_overview.yaml`):
- New example showing chemistry-rich gene response (PMM0392 or similar).
- Mistake entry: "When `evidence_sources` is non-empty, drill via `metabolites_by_gene` (gene-anchored) or `genes_by_metabolite` (metabolite-anchored). The list values are `['metabolism', 'transport', 'metabolomics']` — `metabolomics` means at least one of the gene's reachable metabolites has measurement coverage."
- Mistake entry: "`metabolite_count` on Gene is reaction-OR-transport reachable (verified PMM0392 with reaction_count=0 has metabolite_count=554 from 8 TCDB families) — not the same as `OrganismTaxon.metabolite_count` which is reaction-only."
- Chaining entry: "gene_overview (per-row `evidence_sources` non-empty) → metabolites_by_gene OR genes_by_metabolite for chemistry drill-down."

---

### 6.2 `list_publications` — measurement rollup pass-through

**What's changing.** Add three new per-row fields, all pure pass-through from Publication node properties:

| New field | Source |
|---|---|
| `metabolite_count: int` | `p.metabolite_count` (precomputed) |
| `metabolite_assay_count: int` | `p.metabolite_assay_count` (precomputed) |
| `metabolite_compartments: list[str]` | `p.metabolite_compartments` (precomputed) |

**Sparse-field policy:** `metabolite_compartments` is populated only when `metabolite_assay_count > 0`. Apply the existing convention used by `compartments` field — return as `list[str]` always (empty list when none), don't omit the key. Match how the existing `derived_metric_count` pattern surfaces.

**Cypher addition.** Pure SELECT extension to the existing `build_list_publications` detail query:

```cypher
... existing RETURN ...
       coalesce(p.metabolite_count, 0) AS metabolite_count,
       coalesce(p.metabolite_assay_count, 0) AS metabolite_assay_count,
       coalesce(p.metabolite_compartments, []) AS metabolite_compartments,
...
```

**Envelope:** no new envelope key. The publication's chemistry surfacing is per-row only; envelope rollups for measurement coverage live on `list_metabolites` (Phase 5).

**About-content updates** (`inputs/tools/list_publications.yaml`):
- New example: `list_publications(search_text="metabolite")` showing rows with non-zero `metabolite_count` / `metabolite_assay_count`.
- Chaining entry: "list_publications (per-row `metabolite_count > 0`) → run_cypher to inspect MetaboliteAssay nodes for the publication (Phase 5 will replace this with `list_metabolite_assays(publication_doi=[...])`)."

---

### 6.3 `list_experiments` — measurement rollup pass-through

**What's changing.** Same shape as 6.2 — three new per-row fields, all pass-through from Experiment node:

| New field | Source |
|---|---|
| `metabolite_count: int` | `e.metabolite_count` |
| `metabolite_assay_count: int` | `e.metabolite_assay_count` |
| `metabolite_compartments: list[str]` | `e.metabolite_compartments` |

**Cypher:** SELECT extension to `build_list_experiments` detail query — symmetric with 6.2.

**Envelope:** no change.

**About-content updates** (`inputs/tools/list_experiments.yaml`): mirror the publication entries.

---

### 6.4 `list_organisms` — measurement coverage rollup + binary envelope

**What's changing.** One new per-row field + one new envelope key:

| New field / envelope | Source / shape |
|---|---|
| `measured_metabolite_count: int` (per row) | `o.measured_metabolite_count` (precomputed OrganismTaxon property) |
| `by_measurement_capability` (envelope) | 2-bucket count: `{has_metabolomics: N, no_metabolomics: M}` where `has_metabolomics = sum(1 for org if measured_metabolite_count > 0)` |

**Why binary, not top-N.** Per audit Part 3a P1: at the current measurement scale (4 organisms with non-zero coverage out of ~37 total), a top-10 ranking is overkill. The binary "covered / not covered" split is more honest.

**Cypher addition.** Detail query — SELECT extension to `build_list_organisms`:

```cypher
... existing RETURN ...
       coalesce(o.measured_metabolite_count, 0) AS measured_metabolite_count,
...
```

Summary query — append envelope rollup CTE. Pattern parallels existing `by_metabolic_capability` rollup, but simpler shape (no top-N logic):

```cypher
... existing summary CTE ...
WITH ..., found AS organisms
WITH ...,
     {
       has_metabolomics: size([o IN organisms WHERE coalesce(o.measured_metabolite_count, 0) > 0]),
       no_metabolomics: size([o IN organisms WHERE coalesce(o.measured_metabolite_count, 0) = 0])
     } AS by_measurement_capability
RETURN ..., by_measurement_capability
```

**About-content updates** (`inputs/tools/list_organisms.yaml`):
- New example: `list_organisms(summary=True)` response showing `by_measurement_capability: {has_metabolomics: 4, no_metabolomics: 33}`.
- Mistake entry: "`measured_metabolite_count` is the count of distinct metabolites measured in this organism via any MetaboliteAssay — different from `metabolite_count` (reaction-only chemistry capability) and from `metabolite_count` on Gene/Publication/Experiment which are different rollups. The 4 organisms with non-zero `measured_metabolite_count` today are MIT9301 (4 assays), MIT9313 (3), MIT0801 (2), MIT9303 (1)."

---

### 6.5 `list_filter_values` — two new filter types + extracellular verification

**What's changing.**

(a) Add `filter_type='omics_type'`. Returns the canonical OMICS_TYPE enum:

```python
{"value": "RNASEQ", "count": <N>},
{"value": "PROTEOMICS", "count": <N>},
{"value": "METABOLOMICS", "count": <N>}, # newly populated as of 2026-05 release
{"value": "MICROARRAY", "count": <N>},
... (whatever the canonical enum carries)
```

The list **must** include `METABOLOMICS` even when `count=0` for backward consistency with the canonical enum. (Phase 5 assay tools will surface non-zero counts.) Source: existing `OMICS_TYPE` constant in the codebase + a Cypher count over `Experiment.omics_type` to populate `count` per value.

(b) Add `filter_type='evidence_source'`. Returns the three Metabolite-evidence categories:

```python
{"value": "metabolism", "count": 2188},   # count of metabolites where 'metabolism' IN m.evidence_sources
{"value": "transport", "count": 1355},
{"value": "metabolomics", "count": 107},
```

Source: Cypher count over `Metabolite.evidence_sources`.

(c) Verify the existing `compartment` filter type returns `extracellular` as a value (it should after the 2026-05 release added MetaboliteAssay edges with `compartment='extracellular'`). If the filter sources from `Experiment.compartment` only, broaden to also include `MetaboliteAssay.compartment` and `DerivedMetric.compartment`.

**Cypher additions.** Two new branches in `build_list_filter_values`. Both static:

```cypher
# omics_type
MATCH (e:Experiment)
WITH coalesce(e.omics_type, 'UNKNOWN') AS ot
WITH apoc.coll.frequencies(collect(ot)) AS counts
RETURN counts
```

Then merge with the canonical OMICS_TYPE enum constant in Python (so `METABOLOMICS` appears even at count=0 if no METABOLOMICS-typed Experiments exist yet).

```cypher
# evidence_source
MATCH (m:Metabolite)
UNWIND coalesce(m.evidence_sources, []) AS src
RETURN src AS value, count(*) AS count
```

(Or an apoc.coll.frequencies version.)

```cypher
# compartment broadening (verify before changing — current query may already aggregate across all *.compartment edges)
MATCH (e:Experiment) WHERE e.compartment IS NOT NULL
WITH e.compartment AS c
UNION ALL
MATCH (a:MetaboliteAssay) WHERE a.compartment IS NOT NULL
WITH a.compartment AS c
UNION ALL
MATCH (dm:DerivedMetric) WHERE dm.compartment IS NOT NULL
WITH dm.compartment AS c
RETURN c AS value, count(*) AS count
```

(Or simpler: aggregate over `(:Experiment|:MetaboliteAssay|:DerivedMetric)` with a union of label selectors.)

**About-content updates** (`inputs/tools/list_filter_values.yaml`):
- New examples showing the two new filter types.
- Chaining entry: "list_filter_values(filter_type='evidence_source') → list_metabolites(evidence_sources=[...]) for slicing by evidence type."
- Chaining entry: "list_filter_values(filter_type='omics_type') → list_experiments(omics_type=...) for filtering by experiment type."

---

### 6.6 `kg_schema` — property-description enrichment + analysis-doc Track B update

**What's changing.** Two parts:

**(a) `kg_schema()` property descriptions.** Today `kg_schema()` returns only property names + types. Per audit Part 3a build-derived row + KG-MET-001 venue note, the cheapest explorer-side fix is a static enrichment in `kg/schema.py` that merges a curated dict of property docstrings into the response. Initially seed with high-value descriptions:

```python
PROPERTY_DESCRIPTIONS = {
    "MetaboliteAssay": {
        "field_description": "Canonical normalisation-provenance string for the metabolomics layer. Carries paper-specific processing context (e.g. blank-correction, replicate aggregation, source units). Read this before interpreting `value` / `value_sd`.",
    },
    "Metabolite": {
        "evidence_sources": "Subset of ['metabolism', 'transport', 'metabolomics'] — which Metabolite-source pipelines (KEGG reaction, TCDB transport, MetaboliteAssay measurement) contribute to this metabolite.",
        "measured_assay_count": "Count of distinct MetaboliteAssay edges to this metabolite. Non-zero on 107 metabolites (out of ~3200) as of 2026-05.",
        "measured_paper_count": "Count of distinct publications with at least one MetaboliteAssay measuring this metabolite.",
        "measured_organisms": "List of organism preferred_name values where this metabolite has been measured.",
    },
    "TcdbFamily": {
        "metabolite_count": "Count of distinct metabolites this TCDB family is annotated to transport. May be 0 (family-level annotation only, no curated substrates).",
        "member_count": "Count of distinct genes annotated to this family across all organisms in KG.",
    },
}
```

The schema dump merges this into each node's properties so each property reads either as `{"type": "string"}` (current behavior) or `{"type": "string", "description": "..."}` (when curated).

**Implementation note (file-ownership).** The merge logic is one helper function in `kg/schema.py`; `mcp_server/tools.py:kg_schema` consumes the enriched dict via the existing schema-fetcher entrypoint. The constant lives in `kg/schema.py` so it's near the introspection layer.

**Out of scope:** automating description discovery from `multiomics_biocypher_kg` config files — that's a KG-side ask (KG-MET-001 venue note). The static dict here is curated, paged-in over time, and tied to the metabolomics surface only.

**(b) Analysis-doc Track B update.** Edit `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md` Track B section to reference `MetaboliteAssay.field_description` as the canonical provenance read that **precedes** `value` / `value_sd` interpretation. Add the convention as a callout near the top of Track B, with one example field_description value.

**Cypher:** none — this is Python static-data + a markdown edit.

**About-content updates** (`inputs/tools/kg_schema.yaml`):
- New mistake entry: "Property `description` is sparse — populated only on a curated set of high-value properties (currently `MetaboliteAssay.field_description` and selected `Metabolite.*` / `TcdbFamily.*` rollups). Property *type* is always present."
- New chaining entry: "kg_schema → for any property carrying `description`, the description text is the canonical semantic read; consult before assuming convention from name alone."

---

### 6.7 `list_metabolites` — measurement rollup pass-through

**Why this item lives in Phase 1 now.** Originally roadmap-Phase-5 because the audit identified KG-MET-016 (`Metabolite.measured_compartments`) as a gating dependency. Live verification 2026-05-05 post-rebuild confirmed the post-import script (L1166-1177) populates the property on all 107 measured metabolites and defaults the rest to `[]`. KG-MET-016 closed; the dependency dropped; the item moved into Phase 1's pure-pass-through cohort.

**What's changing.** Four new per-row fields plus one envelope key, all pure pass-through from `Metabolite` node properties:

| New field / envelope | Source | Notes |
|---|---|---|
| `measured_assay_count: int` (per row) | `m.measured_assay_count` | non-zero on 107 of ~3200 metabolites |
| `measured_paper_count: int` (per row) | `m.measured_paper_count` | non-zero on 107; 8 covered by 2 papers, 99 by 1 |
| `measured_organisms: list[str]` (per row) | `m.measured_organisms` | populated when `measured_assay_count > 0` |
| `measured_compartments: list[str]` (per row) | `m.measured_compartments` | populated when `measured_assay_count > 0` (KG-MET-016 closed) |
| `by_measurement_coverage` (envelope) | summary aggregation | `{by_paper_count: [{paper_count: 0, n: 3111}, {paper_count: 1, n: 99}, {paper_count: 2, n: 8}], by_compartment: [{compartment: 'whole_cell', n: <X>}, {compartment: 'extracellular', n: <Y>}]}` |

**Sparse-field policy.** Match the existing `list_metabolites` convention — return all four measurement fields as their default-empty value (`0`, `[]`) on metabolites without measurement coverage, NOT `null`. Verified live: post-import sets `measured_assay_count=0` and `measured_compartments=[]` on the 3111 non-measured metabolites (post-import L1173-1177). The KG team explicitly chose default-empties over sparse fields; consume that convention directly.

**Cypher.** Pure SELECT extension to the existing `build_list_metabolites` detail query:

```cypher
... existing RETURN ...
       coalesce(m.measured_assay_count, 0) AS measured_assay_count,
       coalesce(m.measured_paper_count, 0) AS measured_paper_count,
       coalesce(m.measured_organisms, []) AS measured_organisms,
       coalesce(m.measured_compartments, []) AS measured_compartments,
...
```

Envelope addition to the summary query — `by_measurement_coverage` rollup:

```cypher
... existing summary CTE over `metabolites` collection ...
WITH ..., metabolites,
  apoc.coll.frequencies([m IN metabolites | coalesce(m.measured_paper_count, 0)]) AS paper_freq,
  apoc.coll.frequencies(apoc.coll.flatten([m IN metabolites | coalesce(m.measured_compartments, [])])) AS compartment_freq
WITH ...,
  {
    by_paper_count: paper_freq,
    by_compartment: compartment_freq
  } AS by_measurement_coverage
RETURN ..., by_measurement_coverage
```

**Verification (live KG, 2026-05-05 post-rebuild):**

| Filter | Expected envelope `by_paper_count` | Expected `by_compartment` |
|---|---|---|
| `list_metabolites()` (all metabolites, summary=True) | `[{paper_count: 0, n: 3111}, {paper_count: 1, n: 99}, {paper_count: 2, n: 8}]` | `[{compartment: 'whole_cell', n: <107 of which whole_cell-measured>}, {compartment: 'extracellular', n: <of which extracellular-measured>}]` |
| `list_metabolites(evidence_sources=['metabolomics'])` (only measured) | `[{paper_count: 1, n: 99}, {paper_count: 2, n: 8}]` | sums to ≤ 107 with overlap on the 92 dual-compartment metabolites |

**About-content updates** (`inputs/tools/list_metabolites.yaml`):
- New example: `list_metabolites(evidence_sources=['metabolomics'], summary=True)` showing `by_measurement_coverage` envelope rolling up to 107 measured metabolites.
- Mistake entry: "`measured_compartments` is populated on all 107 measured metabolites (defaults to `[]` on the 3111 unmeasured); use `len(m['measured_compartments']) >= 1` to filter for measurement-anchored rows. Same metabolite measured in both whole_cell and extracellular returns one row with `measured_compartments=['extracellular','whole_cell']` (sorted), not two rows — Metabolite is compartment-agnostic per KG-MET-002."
- Chaining entry: "list_metabolites (per-row `measured_assay_count > 0`) → run_cypher to inspect MetaboliteAssay edges (Phase 5 will replace this with `assays_by_metabolite(metabolite_ids=[...])`)."

---

## 7. Implementation file map (Mode B parallel build)

Per the `add-or-update-tool` skill Phase 2 file-ownership convention. Each agent gets one file.

| Agent | File | Items touched |
|---|---|---|
| `query-builder` | `multiomics_explorer/kg/queries_lib.py` | 6.1 (gene_overview Cypher), 6.2 (list_publications), 6.3 (list_experiments), 6.4 (list_organisms detail + summary), 6.5 (list_filter_values branches), 6.7 (list_metabolites detail + summary) |
| `api-updater` | `multiomics_explorer/api/functions.py` (+ `kg/schema.py` for 6.6) | 6.1–6.5 + 6.7 row-class / response-shape extensions; 6.6 PROPERTY_DESCRIPTIONS dict + merge logic in `kg/schema.py` |
| `tool-wrapper` | `multiomics_explorer/mcp_server/tools.py` | 6.1–6.5 + 6.7 Pydantic model extensions (response classes); 6.6 schema response shape extension |
| `doc-updater` | `multiomics_explorer/inputs/tools/{gene_overview,list_publications,list_experiments,list_organisms,list_metabolites,list_filter_values,kg_schema}.yaml` + `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/metabolites.md` + `CLAUDE.md` tool-table updates | About-content for 7 tools; analysis-doc Track B update; CLAUDE.md tool table touch-ups for the changed surfaces |

**Cross-cutting note.** The `api-updater` agent owns BOTH `api/functions.py` AND `kg/schema.py` for this slice — `kg/schema.py` is the home of the schema-introspection helper, and the only API-layer file that's not `functions.py`. Keep the agent brief explicit about both files so the agent doesn't try to put `PROPERTY_DESCRIPTIONS` in `functions.py`.

## 8. Test cases (one slice per layer, applied to all 6 tools)

All test patterns follow the `testing` skill conventions. Key patterns per layer:

**Query builder tests** (`tests/unit/test_query_builders.py`): for each modified builder, assert the generated Cypher contains the new SELECT keys (string-match) and that `params` contains expected inputs.

**API tests** (`tests/unit/test_api_functions.py`): mock-driver tests asserting that the Python wrapper:
- For 6.1 — passes through the new fields and that `evidence_sources` defaults to `[]` when no chemistry edges exist.
- For 6.2/6.3 — passes through `metabolite_count` / `metabolite_assay_count` / `metabolite_compartments` correctly when present and as zero/empty when absent.
- For 6.4 — emits the `by_measurement_capability` envelope with binary buckets summing to the total organism count.
- For 6.5 — returns the omics_type enum including METABOLOMICS even when count=0; returns the 3-element evidence_source list with non-zero counts.
- For 6.6 — schema response carries `description` keys on the curated properties.

**Tool wrapper tests** (`tests/unit/test_tool_wrappers.py`): Pydantic model parsing tests asserting the new fields validate against representative responses from the spec's verification cases. Update `EXPECTED_TOOLS` registry with no signature changes (no new params); update `TOOL_BUILDERS` only where new builder functions are added (none in this slice — all existing builders are extended).

**KG-integration tests** (`tests/integration/`, marked `@pytest.mark.kg`): one round-trip test per tool that asserts a verification case from the spec. For 6.1, use PMM0392 (or post-rebuild equivalent) and assert `evidence_sources` matches the expected set.

**Regression tests** (`tests/regression/`): adding new fields will require `--force-regen` for affected fixtures. Document in the implementation plan.

## 9. Open questions / pending decisions

- [x] **Cypher re-verification after KG rebuild.** ✓ Verified live 2026-05-05 post-rebuild — 5 verification cases in §6.1 all pass. Gene.metabolite_count semantics confirmed by post-import.sh L908: "TCDB-S3 / KG-A2: UNION of catalysis + transport paths" — by design, not a bug. PMM0392 reproduces with 554 / 0 / 8. Path-existence Cypher correctly drops false `metabolism` tags on transport-only genes.
- [x] **`list_filter_values` extracellular verification.** ✓ Verified live: existing `build_list_compartments()` queries `Experiment.compartment` only, and `Experiment` carries 3 `extracellular` records (the metabolomics-paired experiments). `extracellular` is present in the current `compartment` filter return — no broadening needed.
- [ ] **Confirm `transporter_count` → `tcdb_family_count` rename direction.** The audit row + CLAUDE.md tool table both reference "transporter_count" as the surfaced field name. The Gene node property is `tcdb_family_count` (the count of TCDB family annotations on the gene). The §6.1 spec proposes surfacing the property as `transporter_count` in the response. **Recommendation: use `transporter_count`** — matches existing CLAUDE.md prose and gives the surface the user-facing-meaning name (a "transporter count" is more readable than a TCDB-specific term). Awaiting user confirm before freeze.
- [ ] **`kg_schema` curated property dict — initial seed scope.** §6.6 proposes seeding 3 nodes × ~6 properties. Open question whether to also seed `Reaction.*`, `OrganismTaxon.measured_metabolite_count`, and `Publication.metabolite_*` descriptions in the same slice, OR keep the seed minimal (MetaboliteAssay-only) and grow over time. **Recommendation: seed minimal (MetaboliteAssay.field_description + the 4 Metabolite measurement fields)** — narrower scope keeps the dict reviewable; expand in Phases 4 / 5 as those tools land.

## 10. Acceptance criteria

- All 7 tools surface the new fields per §6.1 – §6.7.
- Existing fields and shapes are unchanged on every tool (additive only).
- All unit + KG-integration tests pass (3 pytest invocations).
- Code review (hard gate per add-or-update-tool skill Stage 3) passes — particular attention to:
  - The `evidence_sources` Cypher correctly using path-existence subqueries (not metabolite-level rollup).
  - Sparse-field / coalesce conventions are consistent with the rest of the codebase.
  - The new `omics_type` filter type returns the canonical enum even when some values have count=0.
- About-content YAML edits regenerate cleanly via `build_about_content.py`.
- `metabolites.md` Track B references `field_description` as canonical provenance read.
- `CLAUDE.md` tool table reflects the new surface fields where the table currently describes per-row content.
