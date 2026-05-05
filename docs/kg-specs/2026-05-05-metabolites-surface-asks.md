# KG-side asks: metabolites surface refresh

**Date:** 2026-05-05
**Driver (audit):** [docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md](../superpowers/specs/2026-05-04-metabolites-surface-audit.md) — Part 5.A
**Roadmap (explorer side):** [docs/superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md](../superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md)
**Status:** 3 Live asks — 1× P1, 2× P2. KG-state verified against the live KG on 2026-05-05 (post-rebuild verification reduced Live count from 5 → 3: KG-MET-006 and KG-MET-016 fulfilled by post-import script; KG-MET-013 partially fixed).

---

## 1. Summary

Three asks remain live after the audit's verification pass + 2026-05-05 post-rebuild check. The shape is now **purely documentation-side** (provenance docs, compartment-convention docs, time-axis sentinel docs) — no precomputes or rollups remain Live. The 16 originally-numbered asks split as **3 Live / 8 Closed / 5 Retired**; full traceability in audit Part 5.D + this doc's §5.B. Two precomputes (KG-MET-006 `is_promiscuous`, KG-MET-016 `measured_compartments`) flipped from Live → Closed when post-rebuild verification confirmed the post-import script populates them. KG-MET-013 partially fixed (chitosan-paper `T=4`-style adapter parsing now resolves to `4 days / 96 hours`; Capovilla-paper empty-string `time_point=""` still maps to `-1` — likely a no-time-point sentinel rather than a parse miss).

What remains is one provenance-documentation reshape (P1), one decision-documentation pair (compartment convention, P2), and one adapter-sentinel documentation ask (P2 — narrowed from the original parse-fix scope).

---

## 2. Ask summary table

| ID | Category | Pri | Phase | Explorer consumer (roadmap phase) |
|---|---|---|---|---|
| KG-MET-001 | Documentation (RESHAPED) | P1 | first-pass | `kg_schema` field_description plumbing — backlog (deferred 2026-05-05) |
| KG-MET-002 | Decision + Documentation | P2 | first-pass | docs-only; informs `list_metabolite_assays` (Phase 5) |
| KG-MET-013 | Documentation (NARROWED) | P2 | first-pass | future cross-omics time-correlated tools (no current consumer) |

**Closed since first draft (verified live 2026-05-05 post-rebuild):**

| ID | Category | Pri | What landed |
|---|---|---|---|
| KG-MET-006 | Precompute | (was P2) | `TcdbFamily.is_promiscuous` populated by post-import L884-885 with rule `metabolite_count >= 50 OR member_count >= 100`; 30 of 12,883 families flagged. See §5.B. |
| KG-MET-016 | Rollup | (was P2) | `Metabolite.measured_compartments` populated by post-import L1166-1177 on all 107 measured metabolites; `[]` on the rest. See §5.B. |

---

## 3. Per-ask detail

### KG-MET-001 — `MetaboliteAssay.field_description` provenance docs (P1, RESHAPED)

**Ask:** Confirm + document the convention that `MetaboliteAssay.field_description` is the canonical normalisation-provenance field for the metabolomics layer. Specifically:

- (a) Add a brief `#` comment near `field_description: str` in `config/schema_config.yaml` calling out its provenance role.
- (b) Call out the convention in `metabolomics-extension.md` and any future metabolomics release notes.

**Why:** The original ask requested *adding* per-paper normalisation docs. Verification against the live KG (2026-05-05) showed those docs already exist, embedded in `field_description` itself. The reshape narrows the ask to "make the convention canonical and discoverable" rather than "add new data."

**Verified state (2026-05-05):**

`MetaboliteAssay.field_description` already carries rich, paper-specific provenance. Examples observed in the live KG:

- *"Intracellular metabolite concentration in fg/cell, blank-corrected, replicate-aggregated; Capovilla 2023 Table sd03"* (Capovilla paper)
- *"Per-cell intracellular concentration; KEGG-tagged; pre-aggregated by authors. Kujawinski 2023 cellSpecific KEGG export."* (Kujawinski paper)

Companion fields on the assay node (`value_kind`, `unit`, `metric_type`, `aggregation_method`) round out the provenance picture. The 2026-05-04 KG release notes (`metabolomics-extension.md`) treat `field_description` as first-class — it is one of four fields indexed in the `metaboliteAssayFullText` full-text index alongside `name`, `treatment`, and `experimental_context`. The reshape direction is consistent with KG-team intent.

**Acceptance criteria:**

- `config/schema_config.yaml` diff shows the YAML `#` comment on `field_description: str`.
- `metabolomics-extension.md` (or release notes) calls out the convention explicitly.

**Explorer-side dependency:** the explorer-side companion item (`kg_schema` property-description enrichment + analysis-doc Track B `field_description` callout) was deferred to backlog 2026-05-05 to keep Phase 1 focused on pass-through plumbing. KG-MET-001 itself stays Live as a KG-team ask — when both KG-MET-001 lands AND the backlog item is re-prioritized, the explorer's `kg_schema` MCP tool will surface `field_description` as a first-class provenance read.

**Out of scope here:** making the BioCypher property description propagate into the live Neo4j schema for schema-introspection callers — that is a separate, larger ask (touches BioCypher config, not just YAML docs). The YAML `#` comment is the cheapest fix.

---

### KG-MET-002 — Compartment-as-property docs (P2)

**Ask:** Document the convention that `Metabolite` is compartment-agnostic and compartment lives on `MetaboliteAssay`. Add to schema docs / `metabolomics-extension.md`. Convention is already in effect; documentation is the only gap.

**Why:** Audit §4.3.5 verified the convention via live-KG inspection. Without explicit documentation, downstream consumers re-derive the convention from inspection (or, worse, assume per-compartment Metabolite duplication). This ask makes the convention canonical so future tools / consumers don't have to reverse-engineer it.

**Verified state (2026-05-05):**

- Zero `Metabolite` nodes encode compartment in their name (no matches for `extracellular` / `intracellular` / `cytoplasm` / `compartment` substrings in `m.name`).
- 92 `Metabolite` nodes are measured in 2+ compartments via separate `MetaboliteAssay` edges. Examples: Phosphoenolpyruvate, (S)-Malate, D-Glucose 6-phosphate measured in both `whole_cell` and `extracellular` against the same `kegg.compound:` ID.

Convention is in effect; ask is documentation-only.

**Acceptance criteria:** schema docs / release-note diff exists explicitly stating the convention.

**Explorer-side dependency:** informs roadmap Phase 5 `list_metabolite_assays` — the discovery tool surfaces compartment per-assay-edge, not per-metabolite-node. Documenting the convention upstream lets the explorer cite KG-side docs rather than re-asserting the rule independently.

---

### KG-MET-013 — `time_point_hours` empty-string sentinel docs (P2, NARROWED)

**Ask (narrowed 2026-05-05 post-rebuild):** The chitosan-paper adapter parsing landed (`T=4 → 4 days / 96h`); the remaining gap is the Capovilla-paper case where `time_point=""` (empty string) maps to `time_point_hours=-1` / `time_point_order=0`. Decide whether this is:

- (a) An intentional "no-time-point" sentinel encoding (single-shot measurement, no time axis) — most likely interpretation. Document the convention in release notes / `metabolomics-extension.md` so future cross-omics consumers don't mistake it for a parse miss.
- (b) An actual parse miss to fix.

If (a), no adapter change needed — just document. If (b), fix the parse.

**Why:** Future cross-omics time-correlated tools (none in current explorer scope) need a clear contract for "no time axis" vs "time axis exists but couldn't parse". Today the only ambiguous case is the Capovilla single-shot sample.

**Verified state (2026-05-05 post-rebuild):**

Live KG `MetaboliteAssay` time-axis distribution:

| Publication | `time_point` | `time_point_hours` | `time_point_order` | n |
|---|---|---:|---:|---:|
| `10.1073/pnas.2213271120` (chitosan) | `"4 days"` | `96` | `1` | (numeric path landed ✓) |
| `10.1073/pnas.2213271120` (chitosan) | `"6 days"` | `144` | `2` | |
| `10.1128/msystems.01261-22` (Capovilla) | `""` (empty) | `-1` | `0` | (single-shot — no time axis intended?) |

Original chitosan misalignment is RESOLVED: `T=4`-style adapter parsing now yields `4 days / 96h / order=1`. The remaining `""` / `-1` / `0` triple looks like an intentional no-time-point encoding (Capovilla measured at one timepoint per condition, not a time course).

**Acceptance criteria:** release-note entry naming the convention (option a — recommended) OR adapter PR (option b — only if Capovilla truly was time-course).

**Explorer-side dependency:** no current explorer consumer. Logged for future cross-omics time-aware tools. The narrowed scope (documentation, not a parse fix) reduces the ask to a low-effort docstring update.

---

## 4. Closed since first draft (2026-05-05 post-rebuild verification)

Two precomputes flipped Live → Closed when post-rebuild inspection of `multiomics_biocypher_kg/scripts/post-import.sh` confirmed they are populated. Kept here for traceability so the audit's KG-MET numbering remains stable.

### KG-MET-006 — `TcdbFamily.is_promiscuous` (CLOSED)

**Was:** P2 precompute ask. **Now:** populated by post-import script L878-885 with the rule cited in the ask itself:

```cypher
SET t.is_promiscuous =
  (coalesce(t.metabolite_count, 0) >= 50) OR
  (coalesce(t.member_count, 0) >= 100)
```

**Verified live 2026-05-05 (post-rebuild):**

| Metric | Value |
|---|---:|
| Total `TcdbFamily` nodes | 12,883 |
| `is_promiscuous = true` | 30 |

The threshold is exactly the starting proposal in the original ask. Closing rationale: the explorer-side consumer (Phase 3 family_inferred warning rewrite) can read `is_promiscuous` directly from the live KG. No further KG action required.

### KG-MET-016 — `Metabolite.measured_compartments` (CLOSED)

**Was:** P2 rollup ask (per-Metabolite-node `measured_compartments`). **Now:** populated by post-import script L1153-1177:

```cypher
MATCH (m:Metabolite)<-[:Assay_quantifies_metabolite|Assay_flags_metabolite]-(a:MetaboliteAssay)
WITH m, count(DISTINCT a) AS acnt,
     collect(DISTINCT a.organism_name) AS orgs,
     collect(DISTINCT a.compartment) AS comps,
     count(DISTINCT a.publication_doi) AS pcnt
SET m.measured_assay_count = acnt,
    m.measured_organisms = ...,
    m.measured_compartments = apoc.coll.sort([c IN comps WHERE c IS NOT NULL]),
    m.measured_paper_count = pcnt;

// default empties on non-measured metabolites
MATCH (m:Metabolite) WHERE m.measured_assay_count IS NULL
SET m.measured_assay_count = 0,
    m.measured_organisms = [],
    m.measured_compartments = [],
    m.measured_paper_count = 0;
```

**Verified live 2026-05-05 (post-rebuild):**

| Metric | Value |
|---|---:|
| Metabolites with `measured_assay_count > 0` | 107 |
| Of those, with `measured_compartments` populated | 107 |
| Sample distinct compartment-set sizes | 92×2 (extracellular+whole_cell), 15×1 |

Closing rationale: explorer-side `list_metabolites` measurement-rollup pass-through (now Phase 1 §6.7) reads the populated property directly. KG team explicitly chose the "default empties" path rather than sparse fields — explorer code uses `coalesce(m.measured_compartments, [])` for safety, but the field is non-null on all metabolites.

---

## 5. Verification queries

These queries were used in the 2026-05-05 verification pass (audit Part 5.A evidence). Replay against the live KG before / after each ask lands.

### KG-MET-001 — verify field_description content

```cypher
MATCH (a:MetaboliteAssay)
RETURN a.id AS assay_id, a.name AS name, a.field_description AS field_description
ORDER BY a.id;
```

Expected: 10 rows, each with non-empty `field_description` containing per-paper provenance text.

### KG-MET-002 — verify compartment lives on edge, not node

```cypher
MATCH (m:Metabolite)
WHERE toLower(m.name) CONTAINS 'extracellular'
   OR toLower(m.name) CONTAINS 'intracellular'
   OR toLower(m.name) CONTAINS 'cytoplasm'
   OR toLower(m.name) CONTAINS 'compartment'
RETURN count(m) AS n_metabolites_with_compartment_in_name;

MATCH (m:Metabolite)<-[r:Assay_quantifies_metabolite|Assay_flags_metabolite]-(a:MetaboliteAssay)
WITH m, count(DISTINCT a.compartment) AS n_compartments
WHERE n_compartments >= 2
RETURN count(m) AS n_metabolites_in_multiple_compartments;
```

Expected: 0 in the first query; 92 in the second (reproduces audit §4.3.5 evidence).

### KG-MET-006 — verify closure (post-rebuild)

```cypher
MATCH (t:TcdbFamily)
RETURN count(t) AS total_families,
       sum(CASE WHEN t.is_promiscuous = true THEN 1 ELSE 0 END) AS n_promiscuous,
       sum(CASE WHEN t.is_promiscuous IS NULL THEN 1 ELSE 0 END) AS n_null
```

Expected (live 2026-05-05): `total_families=12,883`, `n_promiscuous=30`, `n_null=0`.

### KG-MET-013 — narrowed sentinel verification

```cypher
MATCH (a:MetaboliteAssay)-[r:Assay_quantifies_metabolite|Assay_flags_metabolite]->(:Metabolite)
WHERE r.time_point IS NOT NULL
RETURN DISTINCT
  a.publication_doi AS doi,
  r.time_point AS time_point,
  r.time_point_hours AS time_point_hours,
  r.time_point_order AS time_point_order
ORDER BY doi, time_point;
```

Expected (live 2026-05-05): chitosan paper `10.1073/pnas.2213271120` returns `4 days / 96 / 1` and `6 days / 144 / 2` (parse landed). Capovilla paper `10.1128/msystems.01261-22` returns `"" / -1 / 0` — the empty-string-as-no-time-point case that's the narrowed ask.

### KG-MET-016 — verify closure (post-rebuild)

```cypher
MATCH (m:Metabolite) WHERE m.measured_assay_count > 0
RETURN size(m.measured_compartments) AS n_compartments, count(m) AS n_metabolites
ORDER BY n_compartments DESC;
```

Expected (live 2026-05-05): 92 metabolites with 2 compartments + 15 with 1 compartment = 107 measured metabolites total.
