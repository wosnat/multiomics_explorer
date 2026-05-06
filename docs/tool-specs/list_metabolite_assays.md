# Tool spec: list_metabolite_assays

**Date:** 2026-05-06
**Status:** **FROZEN** — Phase 1 complete (scope + KG verification + Cypher live-verified). Ready for Phase 2 build (Mode A — single tool deep build). Ships first; gives drill-down callers `assay_id` / `value_kind` / `rankable` to inspect.
**Parent (full Phase 5 context):** [docs/tool-specs/2026-05-05-phase5-greenfield-assay-tools.md](2026-05-05-phase5-greenfield-assay-tools.md) — KG verification §3, tested-absent invariant §10, cross-tool conventions §11, Phase 2 deliverables §13.
**Mirror reference:** [docs/tool-specs/list_derived_metrics.md](list_derived_metrics.md) — DM analog. Phase 5 is a 1:1 structural mirror of the DM pipeline (per parent §1).

---

## 1. Purpose

Discovery surface for `MetaboliteAssay` nodes — entry point for the metabolomics-measurement workflow. Pre-flight inspection point for the 3 drill-down tools (`metabolites_by_quantifies_assay`, `metabolites_by_flags_assay`, `assays_by_metabolite`): the LLM inspects `value_kind`, `rankable`, `compartment`, and `metabolite_ids` membership here before drilling in.

Mirrors `list_derived_metrics`'s role exactly — see the DM spec for the surface convention's history. This tool extends that convention to the 10 `MetaboliteAssay` nodes in the live KG.

## 2. Out of scope

- Per-edge values / per-metabolite drill-down → `metabolites_by_quantifies_assay` / `metabolites_by_flags_assay`.
- Reverse lookup (metabolite → assays) → `assays_by_metabolite`.
- Metabolite-anchored discovery (compounds, not assays) → `list_metabolites`.
- Gene-side chemistry → `metabolites_by_gene`, `genes_by_metabolite`.

## 3. KG dependencies

Verified live 2026-05-05 / 2026-05-06 — see parent [§3 KG verification](2026-05-05-phase5-greenfield-assay-tools.md#3-kg-verification-step-2-closed-2026-05-05). Summary:

- 10 `MetaboliteAssay` nodes (4 organisms: MED4-cluster strains MIT0801/MIT9301/MIT9303/MIT9313; 2 papers: Capovilla 2023 + Kujawinski 2023; 8 experiments).
- `value_kind` / `rankable` distribution: 8 numeric (rankable=`"true"`), 2 boolean (rankable=`"false"`).
- 26 node properties — denormalized (`organism_name`, `experiment_id`, `publication_doi` direct on the node — no joins for scoping).
- `metaboliteAssayFullText` index over `name, field_description, treatment, experimental_context` (4 fields — wider corpus than DM's 2-field index).
- RANGE indexes on `compartment, experiment_id, metric_type, organism_name, value_kind`.
- Per-edge `time_point` rollup via `Assay_quantifies_metabolite` outgoing edges (numeric assays only — boolean schema lacks `time_point`).
- `growth_phases` empty `[]` on every assay today (KG-MET-017 backfill pending).

## 4. Tool signature

```python
@mcp.tool(
    tags={"metabolomics", "discovery", "catalog"},
    annotations={"readOnlyHint": True, "destructiveHint": False,
                 "idempotentHint": True, "openWorldHint": False},
)
async def list_metabolite_assays(
    ctx: Context,
    search_text: Annotated[str | None, Field(
        description="Full-text search over MetaboliteAssay name, field_description, "
                    "treatment, experimental_context. Examples: 'chitosan', "
                    "'cellular concentration', 'KEGG export'.",
    )] = None,
    organism: Annotated[str | None, Field(
        description="Organism (case-insensitive substring CONTAINS match). "
                    "Accepts short strain code ('MIT9301', 'MIT9303') or full "
                    "name ('Prochlorococcus MIT9313'). Per parent §11 Conv C.",
    )] = None,
    metric_types: Annotated[list[str] | None, Field(
        description="Filter by metric_type tags. Live values: "
                    "'cellular_concentration' (5), 'extracellular_concentration' (3), "
                    "'presence_flag_intracellular' (1), 'presence_flag_extracellular' (1).",
    )] = None,
    value_kind: Annotated[Literal["numeric", "boolean"] | None, Field(
        description="Filter by value kind. 'numeric' → drill via "
                    "`metabolites_by_quantifies_assay`; 'boolean' → "
                    "`metabolites_by_flags_assay`. No 'categorical' assays "
                    "in the current KG.",
    )] = None,
    compartment: Annotated[str | None, Field(
        description="Sample compartment. Live values: 'whole_cell' (7), "
                    "'extracellular' (3). Exact match.",
    )] = None,
    treatment_type: Annotated[list[str] | None, Field(
        description="Treatment type(s) (set-membership ANY-overlap, "
                    "case-insensitive). E.g. ['carbon'], ['phosphorus', 'growth_phase'].",
    )] = None,
    background_factors: Annotated[list[str] | None, Field(
        description="Background factor(s) (ANY-overlap, case-insensitive). "
                    "E.g. ['axenic', 'light'].",
    )] = None,
    growth_phases: Annotated[list[str] | None, Field(
        description="Growth phase(s) (ANY-overlap, case-insensitive). "
                    "Empty `[]` on every assay today (KG-MET-017 backfill pending — "
                    "fields populate without explorer-side code change).",
    )] = None,
    publication_doi: Annotated[list[str] | None, Field(
        description="Filter by publication DOI(s). Exact match. "
                    "E.g. ['10.1073/pnas.2213271120', '10.1128/msystems.01261-22'].",
    )] = None,
    experiment_ids: Annotated[list[str] | None, Field(
        description="Filter by Experiment node id(s).",
    )] = None,
    assay_ids: Annotated[list[str] | None, Field(
        description="Look up specific assays by id. Use to pin one assay "
                    "when the same `metric_type` appears across organisms / papers. "
                    "`not_found` lists IDs that don't exist as a MetaboliteAssay.",
    )] = None,
    metabolite_ids: Annotated[list[str] | None, Field(
        description="Restrict to assays measuring at least one of these "
                    "metabolites (1-hop via Assay_quantifies_metabolite | "
                    "Assay_flags_metabolite). Full prefixed IDs, e.g. "
                    "['kegg.compound:C00074']. NEW vs `list_derived_metrics`.",
    )] = None,
    exclude_metabolite_ids: Annotated[list[str] | None, Field(
        description="Exclude assays measuring any of these metabolites. "
                    "Set-difference cross-tool convention (parent §11 Conv A).",
    )] = None,
    rankable: Annotated[bool | None, Field(
        description="Filter to assays supporting rank/percentile/bucket analysis "
                    "on `metabolites_by_quantifies_assay`. Set True before passing "
                    "rankable-gated edge filters to that drill-down. (rankable=False "
                    "today returns the 2 boolean assays; the numeric drill-down's "
                    "rankable-gated filters are not applicable to boolean assays "
                    "regardless.)",
    )] = None,
    summary: Annotated[bool, Field(
        description="Return summary fields only (results=[]). Use for orientation.",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include heavy text fields per row: treatment, "
                    "light_condition, experimental_context.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results to return. Default 20 covers all 10 assays today.",
        ge=1,
    )] = 20,
    offset: Annotated[int, Field(
        description="Pagination offset (starting row, 0-indexed).", ge=0,
    )] = 0,
) -> ListMetaboliteAssaysResponse:
    """Discover MetaboliteAssay nodes — discovery surface for the metabolomics
    measurement layer.

    Call this first. Inspect `value_kind` (routes to the right drill-down),
    `rankable` (gates rankable filters on the numeric drill-down),
    `compartment` (whole_cell vs extracellular), and per-row
    `detection_status_counts` (signals how much of the assay is detected /
    sporadic / not_detected — primary headline per audit §4.3.3).

    A row with `value=0` / `flag_value=false` / `detection_status='not_detected'`
    on the drill-down tools is *tested-absent* (assayed and not found, real
    biology) — distinct from a missing row, which is *unmeasured* (not in
    the assay's scope). See parent §10.

    After this, drill via:
    - metabolites_by_quantifies_assay(assay_ids=[...]) — numeric arm details
    - metabolites_by_flags_assay(assay_ids=[...]) — boolean arm details
    - assays_by_metabolite(metabolite_ids=[...]) — reverse lookup across both arms
    - list_metabolites(metabolite_ids=[...]) — chemistry context for measured compounds
    """
```

## 5. Per-row schema

### Compact

| Field | Source | Notes |
|---|---|---|
| `assay_id` | `a.id` | parallel to DM `derived_metric_id` |
| `name` | `a.name` | |
| `metric_type` | `a.metric_type` | |
| `value_kind` | `a.value_kind` | `'numeric'` or `'boolean'` (no categorical today) |
| `rankable` | `a.rankable = "true"` | string→bool coercion (parent §11 Conv K) |
| `unit` | `a.unit` | empty string on boolean assays |
| `field_description` | `a.field_description` | canonical provenance per audit KG-MET-001 |
| `organism_name` | `a.organism_name` | |
| `experiment_id` | `a.experiment_id` | |
| `publication_doi` | `a.publication_doi` | |
| `compartment` | `a.compartment` | `'whole_cell'` or `'extracellular'` today |
| `omics_type` | `a.omics_type` | always `'METABOLOMICS'` |
| `treatment_type` | `coalesce(a.treatment_type, [])` | list |
| `background_factors` | `coalesce(a.background_factors, [])` | list |
| `growth_phases` | `coalesce(a.growth_phases, [])` | list — empty `[]` today (KG-MET-017) |
| `total_metabolite_count` | `a.total_metabolite_count` | per-assay distinct-metabolite count (parent §4.1.2) |
| `aggregation_method` | `a.aggregation_method` | e.g. `'mean_across_replicates'` |
| `preferred_id` | `a.preferred_id` | xref hint |
| `value_min` / `value_q1` / `value_median` / `value_q3` / `value_max` | precomputed on node | distribution stats |
| `timepoints` | `[label IN collect(DISTINCT r.time_point) WHERE label <> "" \| label]` | from outgoing `Assay_quantifies_metabolite` edges; D3 strips `""` sentinel |
| `detection_status_counts` | apoc-frequencies over outgoing quantifies edges | numeric assays only; `[]` on boolean rows |
| `score` | from fulltext | only when `search_text` provided |

### Verbose adds

`treatment, light_condition, experimental_context` (mirrors DM verbose).

## 6. Envelope

| Field | Source |
|---|---|
| `total_entries` | `count(MetaboliteAssay)` (unfiltered baseline) |
| `total_matching` | filtered count |
| `metabolite_count_total` | `sum(a.total_metabolite_count)` — **cumulative** across matching assays (per field-rubric clause 7: name predicts shape; same metabolite measured by N assays counts N times). For distinct counts route to `assays_by_metabolite(metabolite_ids=..., summary=True)` or `list_metabolites(metabolite_ids=...)`. |
| `by_organism` | apoc frequencies |
| `by_value_kind` | apoc frequencies |
| `by_compartment` | apoc frequencies |
| `top_metric_types` | apoc frequencies sorted desc |
| `by_treatment_type` | flattened list |
| `by_background_factors` | flattened list |
| `by_growth_phase` | flattened list (empty `[]` today — KG-MET-017) |
| `by_detection_status` | apoc frequencies over outgoing quantifies edges of matching numeric assays — rolls the audit §4.3.3 primary-headline up to envelope |
| `score_max` / `score_median` | only when `search_text` set (parent §11 Conv J) |
| `returned`, `truncated`, `offset` | structural |
| `not_found` | structured Pydantic class — `{assay_ids: [...], metabolite_ids: [...], publication_doi: [...], experiment_ids: [...]}` for each batch input that has unknown values; flat `[]` per field when all matched. Multi-batch tool → structured (parent §11 Conv B; §13.6 deviation note). |

**Sort key:** `score DESC` (when search), then `a.organism_name ASC, a.value_kind ASC, a.id ASC`. Mirrors DM.

## 7. Verified Cypher

Detail + summary verified live 2026-05-06 — see parent [§12.1](2026-05-05-phase5-greenfield-assay-tools.md#121-list_metabolite_assays). The query strings are reproduced there in full with `<_list_metabolite_assays_where conditions>` placeholder for the WHERE-clause helper.

Key live-verification fixtures (will become regression baselines):
- No filters → `total_entries=10`, `total_matching=10`, `metabolite_count_total=768` (cumulative across assays, NOT distinct).
- `value_kind='numeric'` + `rankable=True` → 8 rows.
- `value_kind='boolean'` → 2 rows.
- `compartment='extracellular'` → 3 rows.
- `metabolite_ids=['kegg.compound:C00074']` (PEP) → 10 rows (PEP is in every assay).
- `by_detection_status` envelope → `{detected: 247, sporadic: 51, not_detected: 902}` — tested-absent dominates 75% (the §10 invariant in numbers).

## 8. Special handling

- **Lucene retry** (parent §11 Conv J / D5) — escape `_LUCENE_SPECIAL` chars, retry once on `Neo4jClientError`.
- **String → bool coercion** (parent §11 Conv K / D4) — `a.rankable: "true"|"false"` → Python `bool`.
- **Single fulltext index over 4 fields** vs DM's 2 — the corpus is wider, so score distributions differ. Reuse the DM helper signature but verify `score_max` / `score_median` sanity in integration tests.
- **`metabolite_ids` filter:** uses `EXISTS { ... }` clause traversing both arms (`Assay_quantifies_metabolite | Assay_flags_metabolite`). The outer query stays grain-of-assay.

## 9. Phase 2 build dispatch (Mode A)

Per parent [§13 Phase 2 deliverables](2026-05-05-phase5-greenfield-assay-tools.md#13-phase-2-build-deliverables-review-driven-additions). All 4 implementer agents in one parallel dispatch (Stage 2 GREEN), each owning their layer file. Anti-scope-creep guardrail mandatory in every brief (§13.4).

| Stage | Agent | File(s) | Acceptance |
|---|---|---|---|
| RED | `test-updater` | `tests/unit/test_query_builders.py`, `test_api_functions.py`, `test_tool_wrappers.py` (+ `EXPECTED_TOOLS` + `TOOL_BUILDERS` registries in test_regression + test_eval) | All `list_metabolite_assays` tests written and red; unrelated tests still green |
| GREEN | `query-builder` | `kg/queries_lib.py`: `_list_metabolite_assays_where()` + `build_list_metabolite_assays{,_summary}()` | Cypher matches §7 / parent §12.1; CyVer registry §13.2 updated; NULL-handling §13.7 applied |
| GREEN | `api-updater` | `api/functions.py`: `list_metabolite_assays()` + `__all__` exports in `api/__init__.py` + `multiomics_explorer/__init__.py` | 2-query pattern; ValueError on bad inputs; Lucene retry; envelope assembly per §6 |
| GREEN | `tool-wrapper` | `mcp_server/tools.py`: Pydantic `ListMetaboliteAssaysResult` + `ListMetaboliteAssaysResponse` (+ typed sub-models per breakdown) + `@mcp.tool` wrapper | Field descriptions with REAL KG examples (§13.5); typed envelope sub-models (parent §11 Conv E); structured `not_found` per §13.6; tool docstring per the §4 template |
| GREEN | `doc-updater` | `inputs/tools/list_metabolite_assays.yaml` + regen via `build_about_content.py` + `CLAUDE.md` MCP-tools-table row | YAML carries `mistakes:` for tested-absent (parent §10), unmeasured-vs-absent, KG-MET-017 null state, structured `not_found`; chaining patterns per §13.5 |
| VERIFY | `code-reviewer` (subagent) + `pytest tests/unit/`, `tests/integration/ -m kg`, `tests/regression/ -m kg` | All Phase 2 outputs | Hard gate: code review confirms Cypher correctness; KG integration green |

## 10. Sequencing

Tool 1 ships first (this PR). The 3-tool drill-down slice (`metabolites_by_assay.md`) ships after this lands so the slice's writing-plans cycle has `assay_id` / `value_kind` / `rankable` available from this tool for the chained workflow + integration tests.

## 11. References

- Parent: [docs/tool-specs/2026-05-05-phase5-greenfield-assay-tools.md](2026-05-05-phase5-greenfield-assay-tools.md)
- DM analog: [docs/tool-specs/list_derived_metrics.md](list_derived_metrics.md)
- Audit driver: [docs/superpowers/specs/2026-05-04-metabolites-surface-audit.md §3b.1](../superpowers/specs/2026-05-04-metabolites-surface-audit.md)
- Roadmap: [docs/superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md §3 Phase 5](../superpowers/specs/2026-05-05-metabolites-surface-refresh-roadmap.md)
- KG-side ask companion: [docs/kg-specs/2026-05-06-metabolites-followup-asks.md](../kg-specs/2026-05-06-metabolites-followup-asks.md) (KG-MET-017)
