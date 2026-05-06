# KG-side asks: metabolites surface — followup batch

**Date:** 2026-05-06
**Predecessor (delivery snapshot):** [docs/kg-specs/2026-05-05-metabolites-surface-asks.md](2026-05-05-metabolites-surface-asks.md) — frozen as the original delivery to the KG team
**Driver (this batch):** Phase 5 scope review — [docs/tool-specs/2026-05-05-phase5-greenfield-assay-tools.md](../tool-specs/2026-05-05-phase5-greenfield-assay-tools.md) (D8 closure)
**Status:** 1 Live ask — 1× P2.

---

## 1. Why a followup doc

The 2026-05-05 asks doc was the snapshot delivered to the KG team after the metabolites-surface audit. It is now a stable historical record. Asks that surface *after* that delivery — during Phase 1–5 implementation — land here to keep the delivery boundary clear. KG-MET ID numbering continues from the original sequence (KG-MET-016 was the last; this batch starts at KG-MET-017) so cross-references in audit / spec / scope docs stay stable.

---

## 2. Ask summary table

| ID | Category | Pri | Surfaced from | Explorer consumer (roadmap phase) |
|---|---|---|---|---|
| KG-MET-017 | Data backfill | P2 | Phase 5 scope D8 (2026-05-06) | `MetaboliteAssay.growth_phases` (assay-node rollup) and/or `Experiment.time_point_growth_phases[]` (per-timepoint, indexed by `time_point_order`) populated for metabolomics — currently empty `[]` on every record. Mirrors `DerivedMetric.growth_phases` convention. Lights up the `growth_phases` row field + filter on `list_metabolite_assays`, and the per-edge `growth_phase` on `metabolites_by_quantifies_assay` + `assays_by_metabolite` (numeric rows) without explorer-side code change. |

---

## 3. Per-ask detail

### KG-MET-017 — Populate `growth_phases` on metabolomics analysis nodes / per-timepoint (P2)

**Ask:** Backfill growth-phase metadata on metabolomics records, mirroring the convention used for `DerivedMetric.growth_phases`. Two valid landing surfaces (KG team picks the right granularity, per existing convention for `DerivedMetric` / `Experiment.time_point_growth_phases`):

- (a) **Per analysis node** — populate `MetaboliteAssay.growth_phases: list[str]` on each assay (the assay is the metabolomics analog of `DerivedMetric` — audit §4.3.1 resolution). Today empty `[]` on all 10 assays. This is the minimum to mirror DM.
- (b) **Per timepoint** (when the experiment is time-resolved) — populate `Experiment.time_point_growth_phases: list[str]` parallel-indexed with `time_point_order`. Today empty `[]` on all 5 metabolomics experiments sampled. This unlocks per-edge `growth_phase` resolution via `(a)<-[:ExperimentHasMetaboliteAssay]-(e)` JOIN + `e.time_point_growth_phases[r.time_point_order]` lookup.

(b) is richer for time-resolved metabolomics (e.g. Capovilla 2023's 4d/6d chitosan timecourse — likely different physiological state per timepoint), but (a) is the minimum-viable mirror of DM.

**Why:** The DM family already exposes `dm.growth_phases` (populated on Biller DMs, empty on Waldbauer); explorer tools surface it as a row field + scoping filter. Phase 5 mirrors the DM pipeline 1:1, so the metabolomics surface already includes `growth_phases` row + filter on `list_metabolite_assays` and per-edge `growth_phase` on the numeric drill-down + reverse-lookup. **Today the explorer surface returns `null` / `[]` everywhere** because the KG fields are unpopulated. Light them up by backfilling — explorer needs no code change.

**Verified state (2026-05-06):**

```cypher
// MetaboliteAssay.growth_phases — empty list on all 10 assays
MATCH (a:MetaboliteAssay) RETURN a.id, a.growth_phases ORDER BY a.id
```
→ all 10 rows return `growth_phases: []`.

```cypher
// Experiment.time_point_growth_phases — empty list on all 5 metabolomics experiments sampled
MATCH (e:Experiment) WHERE e.omics_type = 'METABOLOMICS'
RETURN e.id, e.growth_phases, e.time_point_growth_phases LIMIT 5
```
→ all 5 rows return `time_point_growth_phases: []` and `growth_phases: []`.

For comparison, DM precedent (lit-up on Biller papers):

```cypher
MATCH (dm:DerivedMetric) WHERE size(coalesce(dm.growth_phases, [])) > 0
RETURN dm.id, dm.growth_phases LIMIT 3
```
→ several rows return `growth_phases: ["darkness"]` on Biller DMs (verified earlier, e.g. `list_derived_metrics` integration tests).

**Acceptance criteria:**

- `MetaboliteAssay.growth_phases` populated for at least the time-resolved metabolomics experiments (Capovilla 2023 chitosan), per (a). Mandatory.
- For (b), `Experiment.time_point_growth_phases` populated parallel-indexed with `time_point_order` for the same experiments. Optional but preferred — makes per-timepoint drill-down rows self-describing.
- Convention documented in `metabolomics-extension.md` (KG-side) so future metabolomics papers populate the field at adapter time, not as a post-import patch.

**Explorer-side dependency:** Phase 5 ships forward-compat — `growth_phases` row + filter on `list_metabolite_assays`, per-edge `growth_phase` on numeric drill-down + reverse-lookup rows. Today resolves to `null` / `[]`. When KG-MET-017 lands, fields populate automatically. No explorer-side code change required.

**YAML mistakes copy** (already in Phase 5 spec §5 D8 closure / §9): "`growth_phase=null` / `growth_phases=[]` on a metabolomics row today reflects unpopulated KG state (KG-MET-017), not 'no growth-state metadata for this measurement.'"

---

## 4. Process note for future followups

When a Phase 1–5 implementation surfaces a new KG-side gap:
1. Add the ask to this doc (incrementing `KG-MET-NNN`).
2. Cross-link from the explorer-side spec where it surfaced (which D-decision / which phase).
3. Update §2 summary table here.
4. Don't edit the 2026-05-05 delivery snapshot — that is frozen as the historical record.
5. When this batch is delivered to the KG team, freeze this file too and start a new dated followup doc for the next batch.
