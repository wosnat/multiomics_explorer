# Tool spec: metabolites-by-assay drill-down slice (Mode B — 3 tools)

**Date:** 2026-05-06
**Status:** **FROZEN** — Phase 1 complete (scope + KG verification + Cypher live-verified). Ready for Phase 2 build (Mode B — 3-tool slice). Ships after `list_metabolite_assays`.
**Tools covered:** `metabolites_by_quantifies_assay` (numeric drill-down), `metabolites_by_flags_assay` (boolean drill-down), `assays_by_metabolite` (polymorphic reverse-lookup).
**Parent (full Phase 5 context):** [docs/tool-specs/2026-05-05-phase5-greenfield-assay-tools.md](2026-05-05-phase5-greenfield-assay-tools.md) — KG verification §3, tested-absent invariant §10, cross-tool conventions §11, Phase 2 deliverables §13.
**Discovery counterpart:** [docs/tool-specs/list_metabolite_assays.md](list_metabolite_assays.md) — Tool 1, ships first.
**Mirror references:**
- `metabolites_by_quantifies_assay` ↔ [`genes_by_numeric_metric.md`](genes_by_numeric_metric.md)
- `metabolites_by_flags_assay` ↔ [`genes_by_boolean_and_categorical_metric.md`](genes_by_boolean_and_categorical_metric.md) (boolean half)
- `assays_by_metabolite` ↔ [`gene_derived_metrics.md`](gene_derived_metrics.md)

---

## 1. Purpose

Close the metabolomics drill-down + reverse-lookup surface. After `list_metabolite_assays` orients the caller on which assays exist, these three tools answer:

| Tool | Question |
|---|---|
| `metabolites_by_quantifies_assay` | For these numeric assays, what metabolites were measured at what concentration / detection status? Filterable by detection_status, value range, rankable-gated bucket / percentile / rank. |
| `metabolites_by_flags_assay` | For these boolean assays, which metabolites were flagged present / absent? Filterable by `flag_value`. |
| `assays_by_metabolite` | For these metabolites, what evidence exists across all assays — quantifies + flags merged? Cross-organism by default; polymorphic `value` / `flag_value` columns. |

Mirror the DM-family pattern 1:1 (per parent §1 Mirror table). Mode B briefing — "implement `metabolites_by_quantifies_assay` first as the template, extend pattern to `metabolites_by_flags_assay` and `assays_by_metabolite`."

## 2. Out of scope

- Cross-experiment per-metabolite summary (`metabolite_response_profile`) — DEFERRED per audit §3b.2 (premature at 10-assay scale).
- DE-shaped metabolomics tool (`differential_metabolite_abundance`) — DEFERRED per audit §3b.4.
- Discovery / pre-flight → `list_metabolite_assays`.
- Compound-level chemistry → `list_metabolites`, `genes_by_metabolite`, `metabolites_by_gene`.

## 3. KG dependencies

Verified live 2026-05-05 / 2026-05-06 — see parent [§3](2026-05-05-phase5-greenfield-assay-tools.md#3-kg-verification-step-2-closed-2026-05-05).

- `Assay_quantifies_metabolite` edges: 1,200 total. 15 properties: `id, metric_type, condition_label, time_point, time_point_order, time_point_hours, value, value_sd, n_replicates, n_non_zero, metric_percentile, replicate_values, detection_status, rank_by_metric, metric_bucket`.
- `Assay_flags_metabolite` edges: 186 total. 6 properties: `id, metric_type, condition_label, flag_value, n_replicates, n_positive`.
- Distribution headlines: 902/1,200 numeric edges are `not_detected` (75%); 119/186 boolean rows are `flag_value="false"` (62%). **Tested-absent dominates** — see parent §10.
- Sentinel triple `(time_point="", time_point_hours=-1.0, time_point_order=0)` on 1,104/1,200 numeric edges (non-temporal experiments).
- `Experiment.time_point_growth_phases[]` parallel-indexed with `time_point_order`; **empty `[]` on every metabolomics experiment today** (KG-MET-017 backfill pending).
- Polymorphic edge match `[r:Assay_quantifies_metabolite|Assay_flags_metabolite]` trips CyVer warnings on cross-arm property reads. Production builders MUST use `UNION ALL` with distinct rel-vars (`rq` / `rf`) — see §7.3 + parent §12.4.

---

## 4. Tool 1 — `metabolites_by_quantifies_assay` (numeric drill-down)

### 4.1 Signature

```python
@mcp.tool(
    tags={"metabolomics", "metabolites", "drill-down", "numeric"},
    annotations={"readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def metabolites_by_quantifies_assay(
    ctx: Context,
    # Selection (required — D1 closure: assay_ids only)
    assay_ids: Annotated[list[str], Field(
        description="MetaboliteAssay IDs to drill into. Discover via "
                    "`list_metabolite_assays(value_kind='numeric')`. "
                    "`not_found.assay_ids` lists IDs that don't exist.",
        min_length=1,
    )],
    # Scoping (intersected with selection)
    organism: Annotated[str | None, Field(
        description="Filter to assays from this organism (CONTAINS match). "
                    "Cross-organism is the default; pass to narrow.",
    )] = None,
    metabolite_ids: Annotated[list[str] | None, Field(
        description="Restrict to specific metabolites (full prefixed IDs, "
                    "e.g. ['kegg.compound:C00074']). `not_found.metabolite_ids` "
                    "lists IDs absent from the KG; metabolites in the KG but "
                    "not measured by any selected assay surface as zero rows "
                    "(unmeasured per parent §10).",
    )] = None,
    exclude_metabolite_ids: Annotated[list[str] | None, Field(
        description="Exclude metabolites with these IDs. Set-difference "
                    "convention (parent §11 Conv A).",
    )] = None,
    experiment_ids: Annotated[list[str] | None, Field(
        description="Filter to assays from these experiments.",
    )] = None,
    publication_doi: Annotated[list[str] | None, Field(
        description="Filter by publication DOI(s). Exact match.",
    )] = None,
    compartment: Annotated[str | None, Field(
        description="Sample compartment ('whole_cell' or 'extracellular'). "
                    "Exact match.",
    )] = None,
    treatment_type: Annotated[list[str] | None, Field(
        description="Treatment type(s) (ANY-overlap, case-insensitive).",
    )] = None,
    background_factors: Annotated[list[str] | None, Field(
        description="Background factor(s) (ANY-overlap).",
    )] = None,
    growth_phases: Annotated[list[str] | None, Field(
        description="Growth phase(s) (ANY-overlap). Empty `[]` on assays today "
                    "(KG-MET-017 backfill pending).",
    )] = None,
    # Edge-level filters: always-available (any numeric assay)
    value_min: Annotated[float | None, Field(
        description="Lower bound on `value` (raw concentration / intensity). "
                    "**Caution**: `value > 0` strips tested-absent rows "
                    "(`value=0` / `detection_status='not_detected'`) — use "
                    "deliberately, never as default. See parent §10.",
    )] = None,
    value_max: Annotated[float | None, Field(
        description="Upper bound on `value`. Always applicable.",
    )] = None,
    detection_status: Annotated[list[str] | None, Field(
        description="Detection-status filter — primary headline per audit "
                    "§4.3.3. Values: 'detected', 'sporadic', 'not_detected'. "
                    "Excluding 'not_detected' strips tested-absent rows; "
                    "surface as caller choice, never default. See parent §10.",
    )] = None,
    timepoint: Annotated[list[str] | None, Field(
        description="Timepoint label(s) — exact match. Live values: "
                    "['4 days'], ['6 days']. Non-temporal experiments expose "
                    "no timepoint here (rows surface with `timepoint=null` per "
                    "D3 sentinel coercion).",
    )] = None,
    # Edge-level filters: rankable-gated
    metric_bucket: Annotated[list[str] | None, Field(
        description="Bucket label(s) — subset of "
                    "{'top_decile','top_quartile','mid','low'}. **Rankable-gated** — "
                    "raises if every selected assay has `rankable=false`. Soft-"
                    "excludes non-rankable assays from mixed input (surfaced in "
                    "envelope `excluded_assays`).",
    )] = None,
    metric_percentile_min: Annotated[float | None, Field(
        description="Lower bound on `metric_percentile` (0–100). **Rankable-gated.**",
        ge=0, le=100,
    )] = None,
    metric_percentile_max: Annotated[float | None, Field(
        description="Upper bound on `metric_percentile`. **Rankable-gated.**",
        ge=0, le=100,
    )] = None,
    rank_by_metric_max: Annotated[int | None, Field(
        description="Cap on `rank_by_metric` (1 = highest). Top-N drill-down. "
                    "**Rankable-gated.**",
        ge=1,
    )] = None,
    summary: Annotated[bool, Field(
        description="Return summary fields only (results=[]).",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include heavy-text fields per row: assay_name, "
                    "field_description, experimental_context, light_condition, "
                    "replicate_values.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max rows. Paginate with `offset`.", ge=1,
    )] = 5,
    offset: Annotated[int, Field(
        description="Pagination offset.", ge=0,
    )] = 0,
) -> MetabolitesByQuantifiesAssayResponse:
    """Drill into numeric MetaboliteAssay edges — one row per (metabolite × assay-edge).

    `value` (raw concentration / intensity) is always returned;
    `metric_bucket` / `metric_percentile` / `rank_by_metric` populated only on
    rankable-assay rows (mirrors `genes_by_numeric_metric`'s rankable gate).
    Rankable-gated filters raise if every selected assay has `rankable=false`,
    soft-exclude on mixed input.

    A row with `value=0` / `n_non_zero=0` / `detection_status='not_detected'`
    is *tested-absent* — the metabolite was assayed and not found. Real biology;
    counts toward `total_matching` and the `by_detection_status` envelope rollup.
    A *missing row* means *unmeasured* (not in this assay's scope) — distinct.
    Don't filter out tested-absent rows assuming noise. See parent §10.

    Pre-flight: `list_metabolite_assays(rankable=True, value_kind='numeric')`
    to confirm rankable filters apply.

    Drill across:
    - `assays_by_metabolite(metabolite_ids=[...])` — same metabolites' boolean evidence + cross-organism reverse view.
    - `genes_by_metabolite(metabolite_ids=[...], organism=...)` — gene catalysts/transporters of these metabolites.
    """
```

### 4.2 Per-row schema

`metabolite_id, name, kegg_compound_id, value, value_sd, n_replicates, n_non_zero, metric_type, metric_bucket, metric_percentile, rank_by_metric, detection_status, timepoint, timepoint_hours, timepoint_order, growth_phase (sparse — null today, KG-MET-017), condition_label, assay_id, organism_name, compartment`.

**Verbose adds:** `assay_name, field_description, experimental_context, light_condition, replicate_values`.

**Tested-absent ≠ unmeasured** (parent §10): `value=0` / `n_non_zero=0` / `detection_status='not_detected'` rows are *assayed and not found* — kept in `results`, counted in `total_matching` + envelope rollups. A missing row is *not in scope*. Don't conflate; don't default-filter.

### 4.3 Envelope

| Field | Source |
|---|---|
| `total_matching` | filtered count |
| `by_detection_status` | apoc frequencies — **primary headline per audit §4.3.3** |
| `by_metric_bucket` | apoc frequencies (rankable rows only) |
| `by_assay` | apoc frequencies |
| `by_compartment` | apoc frequencies |
| `by_organism` | apoc frequencies |
| `by_metabolite` (top N) | apoc frequencies + per-metabolite row counts |
| `by_metric` | per-assay precomputed-vs-filtered: enriches with `a.value_min/q1/median/q3/max` (full-assay range) alongside filtered slice min/max — lets the LLM read "your top-decile slice 0.012–0.16 out of full assay range 0–0.16" inline. Mirrors DM `by_metric`. |
| `excluded_assays` | rankable-gating: which assay_ids were soft-excluded under mixed-rankable input |
| `warnings` | rankable-gating warnings |
| `not_found` | structured `NotFound` (parent §11 Conv B / §13.6): `{assay_ids: [...], metabolite_ids: [...], experiment_ids: [...], publication_doi: [...]}` |
| `returned`, `truncated`, `offset` | structural |

### 4.4 Sort key

`r.rank_by_metric ASC NULLS LAST, m.id ASC, a.id ASC, r.time_point_order ASC` — top-ranked rows first when assay is rankable; deterministic fallback otherwise. Mirrors `genes_by_numeric_metric`.

---

## 5. Tool 2 — `metabolites_by_flags_assay` (boolean drill-down)

### 5.1 Signature

```python
@mcp.tool(
    tags={"metabolomics", "metabolites", "drill-down", "boolean"},
    annotations={"readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def metabolites_by_flags_assay(
    ctx: Context,
    # Selection (required — D1 closure)
    assay_ids: Annotated[list[str], Field(
        description="MetaboliteAssay IDs to drill into. Discover via "
                    "`list_metabolite_assays(value_kind='boolean')`. "
                    "`not_found.assay_ids` lists IDs that don't exist.",
        min_length=1,
    )],
    # Scoping (same block as numeric — copy-paste consistent for Mode B)
    organism: Annotated[str | None, Field(...)] = None,
    metabolite_ids: Annotated[list[str] | None, Field(...)] = None,
    exclude_metabolite_ids: Annotated[list[str] | None, Field(...)] = None,
    experiment_ids: Annotated[list[str] | None, Field(...)] = None,
    publication_doi: Annotated[list[str] | None, Field(...)] = None,
    compartment: Annotated[str | None, Field(...)] = None,
    treatment_type: Annotated[list[str] | None, Field(...)] = None,
    background_factors: Annotated[list[str] | None, Field(...)] = None,
    growth_phases: Annotated[list[str] | None, Field(...)] = None,
    # Edge-level filter: kind-specific
    flag_value: Annotated[bool | None, Field(
        description="Filter by flag presence — `True` (presence flagged), "
                    "`False` (absence flagged — *tested-absent*, real biology), "
                    "`None` (both). Unlike `genes_by_boolean_metric` (positive-"
                    "only KG storage), `Assay_flags_metabolite` stores both true "
                    "and false flags, so `flag_value=False` returns real rows. "
                    "API coerces to string `'true'`/`'false'` for Cypher (parent "
                    "§11 Conv K).",
    )] = None,
    summary: Annotated[bool, Field(...)] = False,
    verbose: Annotated[bool, Field(
        description="Include heavy-text fields per row: assay_name, field_description.",
    )] = False,
    limit: Annotated[int, Field(..., ge=1)] = 5,
    offset: Annotated[int, Field(..., ge=0)] = 0,
) -> MetabolitesByFlagsAssayResponse:
    """Drill into boolean MetaboliteAssay edges — one row per (metabolite × flag-edge).

    `flag_value=False` rows are *tested-absent* (assayed and not found, real
    biology). A missing row means *unmeasured*. Distinct (parent §10).
    62% of boolean rows in the live KG are `flag_value="false"` — tested-
    absent dominates the boolean arm too.

    No `by_detection_status` envelope — that field exists only on the numeric
    edge. On the boolean arm, `flag_value` IS the qualitative-detection signal;
    `by_value` is its envelope rollup.

    Drill across:
    - `assays_by_metabolite(metabolite_ids=[...])` — quantifies-arm complement.
    - `genes_by_metabolite(metabolite_ids=[...], organism=...)` — chemistry context.
    """
```

### 5.2 Per-row schema

`metabolite_id, name, kegg_compound_id, flag_value (bool), n_positive, n_replicates, metric_type, condition_label, assay_id, organism_name, compartment`.

**Verbose adds:** `assay_name, field_description`.

### 5.3 Envelope

| Field | Source |
|---|---|
| `total_matching` | filtered count |
| `by_value` | apoc frequencies on `flag_value` (true / false counts) |
| `by_assay` | apoc frequencies |
| `by_compartment` | apoc frequencies |
| `by_organism` | apoc frequencies |
| `by_metric` | per-assay precomputed `dm_true_count` / `dm_false_count` vs filtered slice — mirrors DM |
| `not_found` | structured `NotFound` (same shape as numeric drill-down) |
| `excluded_assays`, `warnings` | always `[]` here (no gates) — kept for cross-tool envelope-shape consistency |
| `returned`, `truncated`, `offset` | structural |

**No `by_detection_status`** — boolean arm has no `detection_status` field. Document in YAML mistakes so callers don't expect it.

### 5.4 Sort key

`r.flag_value DESC, m.id ASC, a.id ASC` — presence-flag-true rows first (so truncated heads show what was found before what was tested-absent), then alphabetical by metabolite.

---

## 6. Tool 3 — `assays_by_metabolite` (polymorphic reverse-lookup)

### 6.1 Signature

```python
@mcp.tool(
    tags={"metabolomics", "metabolites", "batch", "reverse-lookup"},
    annotations={"readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def assays_by_metabolite(
    ctx: Context,
    metabolite_ids: Annotated[list[str], Field(
        description="Metabolite IDs to look up (full prefixed, case-sensitive). "
                    "E.g. ['kegg.compound:C00074']. `not_found` lists IDs absent "
                    "from the KG; `not_matched` lists IDs in KG but with no "
                    "assay edge after filters (unmeasured for this scope, "
                    "parent §10). Required, non-empty.",
        min_length=1,
    )],
    organism: Annotated[str | None, Field(
        description="Optional organism filter (CONTAINS match). Default `None` = "
                    "cross-organism (D2 closure: cross-organism is natural shape "
                    "since metabolite IDs are organism-agnostic — one Metabolite "
                    "node shared across organisms per audit §4.3.5).",
    )] = None,
    evidence_kind: Annotated[Literal["quantifies", "flags"] | None, Field(
        description="Filter by edge type. `'quantifies'` = numeric arm only "
                    "(15-field rows incl. value, detection_status, timepoint). "
                    "`'flags'` = boolean arm only (6-field rows incl. flag_value). "
                    "Default `None` = both arms merged (rows are polymorphic; "
                    "cross-arm fields explicit `None` per parent §11 Conv B).",
    )] = None,
    exclude_metabolite_ids: Annotated[list[str] | None, Field(
        description="Exclude metabolites with these IDs (parent §11 Conv A).",
    )] = None,
    metric_types: Annotated[list[str] | None, Field(
        description="Filter by metric_type tag(s) on the parent assay node. "
                    "E.g. ['cellular_concentration', 'extracellular_concentration', "
                    "'presence_flag_intracellular', 'presence_flag_extracellular'].",
    )] = None,
    compartment: Annotated[str | None, Field(
        description="Sample compartment ('whole_cell', 'extracellular'). "
                    "Exact match on parent assay node.",
    )] = None,
    summary: Annotated[bool, Field(...)] = False,
    verbose: Annotated[bool, Field(
        description="Include heavy-text fields per row: assay_field_description, "
                    "replicate_values, experimental_context.",
    )] = False,
    limit: Annotated[int, Field(..., ge=1)] = 5,
    offset: Annotated[int, Field(..., ge=0)] = 0,
) -> AssaysByMetaboliteResponse:
    """Batch reverse-lookup: metabolite IDs → all measurement evidence across
    both arms (quantifies + flags). Cross-organism by default.

    Polymorphic rows: numeric-arm rows carry `value`, `value_sd`,
    `detection_status`, `timepoint*`, `metric_bucket`, `metric_percentile`,
    `rank_by_metric` (rankable subset). Boolean-arm rows carry `flag_value`,
    `n_positive`. Cross-arm fields are explicit `None` (union-shape padding,
    parallels Phase 3 decision on `genes_by_metabolite`).

    Three states for a metabolite (parent §10):
    1. `not_found` — ID not in the KG. **Unmeasured.**
    2. `not_matched` — ID in the KG, no assay edge after filters. **Unmeasured for this scope.**
    3. Row in `results` with `value=0` / `flag_value=false` / `detection_status='not_detected'` —
       *tested-absent* (assayed and not found). Real biology; counted in `total_matching`.

    Use `summary=True` for batch routing on 50+ metabolite_ids.

    Originates from:
    - `list_metabolites(metabolite_ids=[...])` — chemistry-layer discovery
    - `metabolites_by_gene(locus_tags=[...])` — gene-anchored chemistry

    Drill back to numeric details: `metabolites_by_quantifies_assay(assay_ids=[...], metabolite_ids=[...])`.
    """
```

### 6.2 Per-row schema (polymorphic)

`metabolite_id, metabolite_name, assay_id, assay_name, evidence_kind, value (numeric only), value_sd (numeric only), flag_value (boolean only), n_replicates, n_positive (boolean only), metric_type, metric_bucket (numeric, rankable only), metric_percentile (numeric, rankable only), detection_status (numeric only), timepoint (numeric only), timepoint_hours (numeric only), timepoint_order (numeric only), growth_phase (numeric only — KG-MET-017 null today), condition_label, organism_name, compartment, experiment_id, publication_doi`.

**Verbose adds:** `assay_field_description, replicate_values, experimental_context`.

Sparse cross-arm fields explicit `None` — mirrors Phase 3 union-shape padding decision.

### 6.3 Envelope

| Field | Source |
|---|---|
| `total_matching` | merged count across arms |
| `by_evidence_kind` | apoc frequencies |
| `by_organism` | apoc frequencies |
| `by_compartment` | apoc frequencies |
| `by_assay` | apoc frequencies |
| `by_detection_status` | numeric-row subset only — empty when `evidence_kind='flags'` filter excludes numeric rows |
| `by_flag_value` | boolean-row subset only — symmetric counterpart |
| `metabolites_with_evidence` / `metabolites_without_evidence` | per-input-ID partition (parallel to `gene_derived_metrics`'s `genes_with_metrics` / `genes_without_metrics`) |
| `metabolites_matched` | distinct count — use this for unique-metabolite tallies (NOT `total_matching`, which is row-count) |
| `not_found` | flat `list[str]` — single batch input (`metabolite_ids` only). Per parent §11 Conv B: flat for single-batch tools. |
| `not_matched` | flat `list[str]` — IDs in KG with no edge after filters. Distinct from `not_found`. |
| `returned`, `truncated`, `offset` | structural |

### 6.4 Sort key

`m.id ASC, evidence_kind DESC, a.id ASC, coalesce(timepoint_order, 999999) ASC` — group rows by metabolite first; `evidence_kind DESC` puts numeric (`'quantifies'`) before boolean (`'flags'`) within each metabolite (ASCII order; data-richer arm first in truncated heads).

---

## 7. Verified Cypher

Detail + summary verified live 2026-05-06 — see parent:
- [§12.2](2026-05-05-phase5-greenfield-assay-tools.md#122-metabolites_by_quantifies_assay) — `metabolites_by_quantifies_assay`
- [§12.3](2026-05-05-phase5-greenfield-assay-tools.md#123-metabolites_by_flags_assay) — `metabolites_by_flags_assay`
- [§12.4](2026-05-05-phase5-greenfield-assay-tools.md#124-assays_by_metabolite) — `assays_by_metabolite`

Live-verification fixtures (regression baselines):

| Tool | Fixture | Result |
|---|---|---|
| `metabolites_by_quantifies_assay` | `assay_ids=['metabolite_assay:pnas.2213271120:metabolites_intracellular_mit9313:cellular_concentration']` | `total_matching=64`, `by_detection_status={detected: 27, sporadic: 30, not_detected: 7}`, `by_metric_bucket={mid: 32, low: 16, top_quartile: 9, top_decile: 7}`. Top-5 rows: F6P top_decile rank 1–3, Citrate top_decile rank 4–5. |
| `metabolites_by_flags_assay` | `assay_ids=['metabolite_assay:msystems.01261-22:presence_flags_table_s2:presence_flag_intracellular']` | `total_matching=93`, `by_value={false: 58, true: 35}`. Top-5 rows alphabetically with `flag_value=true`: S-adenosyl-L-methionine, tyrosine, NADH, AMP, S-Adenosyl-L-homocysteine. |
| `assays_by_metabolite` | `metabolite_ids=['kegg.compound:C00074']` (PEP) | `total_matching=20` (18 quantifies + 2 flags), `by_detection_status={not_detected: 12, detected: 3, sporadic: 3}`, `by_flag_value={false: 2}`, `metabolites_matched=1`. **70% of all PEP measurements are tested-absent.** |

### 7.1 CyVer caveat (production-critical)

The polymorphic `[r:Assay_quantifies_metabolite|Assay_flags_metabolite]` shape with cross-arm property reads in CASE expressions trips a CyVer schema warning. **Production builders MUST use `UNION ALL` with distinct relationship variable names per branch (`rq` for quantifies, `rf` for flags)** — verified clean. See parent §12.4 for the verified pattern + §13.7 for the NULL-handling rules in the merge step.

---

## 8. Phase 2 build dispatch (Mode B — 3-tool slice)

Per parent [§13 Phase 2 deliverables](2026-05-05-phase5-greenfield-assay-tools.md#13-phase-2-build-deliverables-review-driven-additions). Mode B briefing per `add-or-update-tool` SKILL.md: implementer agents do **`metabolites_by_quantifies_assay` first as the template**, then extend pattern to `metabolites_by_flags_assay` and `assays_by_metabolite` within the same file.

Anti-scope-creep guardrail (parent §13.4) mandatory in every brief, verbatim:
> "ADD only — do NOT modify, rename, or rebaseline any existing test, case, or yml. If an unrelated test fails in your environment, REPORT AS A CONCERN; do not silently retune. Pinned baselines are KG-state guards."

| Stage | Agent | File(s) | Per-tool acceptance |
|---|---|---|---|
| RED | `test-updater` | `tests/unit/test_query_builders.py`, `test_api_functions.py`, `test_tool_wrappers.py` (+ `EXPECTED_TOOLS` + `TOOL_BUILDERS` registries in test_regression + test_eval) | All 3 tools' tests written and red; unrelated tests still green; `list_metabolite_assays` tests (already shipped) stay green |
| GREEN | `query-builder` | `kg/queries_lib.py`: `build_metabolites_by_quantifies_assay{,_summary,_diagnostics}()`, `build_metabolites_by_flags_assay{,_summary}()`, `build_assays_by_metabolite{,_summary}()` | Cypher matches §7 references; CyVer registry (parent §13.2) updated; UNION ALL pattern with `rq`/`rf` rel-vars on `assays_by_metabolite` (§7.1); NULL-handling per parent §13.7 |
| GREEN | `api-updater` | `api/functions.py`: 3 new functions + `__all__` exports in `api/__init__.py` + `multiomics_explorer/__init__.py` | 2-query pattern; rankable-gating diagnostics → ValueError on all-non-rankable for numeric drill-down; structured `not_found` for drill-downs (§4.3 + §5.3); flat `not_found` for reverse-lookup (§6.3); ValueError on bad inputs |
| GREEN | `tool-wrapper` | `mcp_server/tools.py`: 3 sets of Pydantic Result + Response models + `@mcp.tool` wrappers | Field descriptions with REAL KG examples (parent §13.5); typed envelope sub-models (parent §11 Conv E — naming `MqaTopMetabolite`, `MfaByValue`, `AbmByEvidenceKind`, etc.); structured `NotFound` for drill-downs (parent §13.6); tool docstrings with drill-down signposting + tested-absent invariant from §10 |
| GREEN | `doc-updater` | `inputs/tools/metabolites_by_quantifies_assay.yaml`, `metabolites_by_flags_assay.yaml`, `assays_by_metabolite.yaml` + regen via `build_about_content.py` + `CLAUDE.md` MCP-tools-table rows | YAML carries `mistakes:` for tested-absent (parent §10), structured-`not_found`, KG-MET-017 null state, CyVer `UNION ALL` lesson where relevant; chaining patterns per parent §13.5; `metabolites.md` analysis doc top-level §"Tested-absent vs unmeasured" added (parent §10 propagation table) |
| VERIFY | `code-reviewer` (subagent) + `pytest tests/unit/`, `tests/integration/ -m kg`, `tests/regression/ -m kg` | All Phase 2 outputs | Hard gate: code review confirms Cypher correctness (especially the `UNION ALL` rel-vars on reverse-lookup); integration green |

---

## 9. Implementer order (within each agent file — Mode B)

Per Mode B briefing convention:

1. `metabolites_by_quantifies_assay` first — carries the most edge-filter logic (rankable-gated diagnostics, by_metric envelope, sentinel coercions). Establishes the template patterns.
2. `metabolites_by_flags_assay` second — same scoping block (copy-paste consistent), simpler edge filter (single `flag_value`), no rankable gates. Reuses 80% of `_quantifies` patterns.
3. `assays_by_metabolite` third — polymorphic UNION ALL is the new shape. Reuses scoping conventions from 1+2 but introduces the per-arm rollup pattern (`by_detection_status` numeric-only + `by_flag_value` boolean-only).

---

## 10. References

- Parent: [docs/tool-specs/2026-05-05-phase5-greenfield-assay-tools.md](2026-05-05-phase5-greenfield-assay-tools.md)
- Discovery counterpart: [docs/tool-specs/list_metabolite_assays.md](list_metabolite_assays.md)
- DM-family analogs:
  - [docs/tool-specs/genes_by_numeric_metric.md](genes_by_numeric_metric.md)
  - [docs/tool-specs/genes_by_boolean_and_categorical_metric.md](genes_by_boolean_and_categorical_metric.md)
  - [docs/tool-specs/gene_derived_metrics.md](gene_derived_metrics.md)
- Audit driver: [docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md §3b.3a–c](../superpowers/specs/2026-05-04-metabolites-surface-audit.md)
- Roadmap: [docs/superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md §3 Phase 5](../superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md)
- KG-side ask: [docs/kg-specs/2026-05-06-metabolites-followup-asks.md](../kg-specs/2026-05-06-metabolites-followup-asks.md) (KG-MET-017 — `growth_phases` backfill, lights up forward-compat surface)
