# Tool spec: `genes_by_boolean_metric` + `genes_by_categorical_metric`

Combined Phase-1 spec for tools 4 and 5 of the slice-1 DerivedMetric MCP
surface. Single doc because the two tools share ~90% of their parameter
list, envelope shape, validation logic, and 3-query orchestration —
diverging only in (a) the kind-specific edge filter (`flag` vs
`categories`), (b) the kind-specific filtered-slice envelope rollup
(`by_value` vs `by_category`), and (c) the kind-specific `by_metric`
per-row stats.

## Purpose

Gene-set drill-down on `Derived_metric_flags_gene` (boolean DMs) and
`Derived_metric_classifies_gene` (categorical DMs) edges, mirroring
[`genes_by_numeric_metric`](./genes_by_numeric_metric.md) (`Derived_metric_quantifies_gene`).
Given a DM selection (by ID or `metric_type`) plus optional scoping
filters and the kind-specific edge filter, return one row per gene × DM
match with envelope rollups by organism / compartment / publication /
experiment / metric and per-DM filtered-slice + full-DM stats.

Cross-organism by design — `metric_type` can repeat across organisms
(e.g. `vesicle_proteome_member` on MED4 + MIT9313;
`predicted_subcellular_localization` on MED4 + MIT9313 — see live counts
below). The `by_organism` envelope and per-row `organism_name` make
cross-strain rows self-describing.

## Out of Scope

- Numeric edge filters / rank / percentile / bucket / p-value — those
  belong to [`genes_by_numeric_metric`](./genes_by_numeric_metric.md).
- Polymorphic single-tool surface (one tool that dispatches on
  `value_kind`). Slice-1 spec §"Why three drill-down tools instead of
  one" — distinct filter surfaces and `by_metric` shapes outweigh the
  consolidation gain.
- Cross-evidence integration (combining DM rows with DE / cluster
  membership in one envelope). Deferred.
- TERM2GENE / ORA hooks built from boolean flag-true sets. Deferred.

## Status / Prerequisites

- [x] KG spec complete: [`docs/kg-specs/2026-04-26-unify-derived-metric-edge-value.md`](../kg-specs/2026-04-26-unify-derived-metric-edge-value.md)
- [x] KG changes landed (2026-04-26 rebuild — all three edge types
  expose `r.value`; `r.value_flag` and `r.value_text` removed)
- [x] Slice-1 design approved: [`docs/superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md`](../superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md)
- [x] Numeric drill-down (tool 3) shipped — establishes the envelope
  shape, validation pattern, and 3-query orchestration that these tools
  mirror
- [x] Cypher verified against live KG (this doc)
- [x] Phase-1 spec reviewed by user (2026-04-26)
- [x] Ready for Phase 2 (build)

## Use cases

**Tool 4 — `genes_by_boolean_metric`:**

- "Which proteins did Biller 2014 detect in the MED4 vesicle proteome?"
  → `metric_types=['vesicle_proteome_member'], organism='MED4'`
- "Show genes flagged in the NATL2A coculture L:D rhythmicity set."
  → `metric_types=['periodic_in_coculture_LD'], organism='NATL2A'`
- "Cross-organism vesicle-proteome members: which genes are detected
  in both MED4 and MIT9313 vesicles?" → `metric_types=['vesicle_proteome_member']`
  (no organism filter), then post-process on `by_organism` envelope.
- "Restrict the flag-set to my DE-hit gene list."
  → `metric_types=[...], locus_tags=[...DE hits]`

**Tool 5 — `genes_by_categorical_metric`:**

- "Show outer-membrane and periplasmic vesicle proteins across both
  Prochlorococcus strains."
  → `metric_types=['predicted_subcellular_localization'], categories=['Outer Membrane', 'Periplasmic']`
- "Show NATL2A genes classified as `darkness_axenic+darkness_coculture`
  (genes that survive in both)."
  → `metric_types=['darkness_survival_class'], categories=['darkness_axenic+darkness_coculture']`
- "Restrict the classification to my DE-hit gene list."
  → `metric_types=[...], locus_tags=[...DE hits]`

**Tool chains (both tools):**

```
list_derived_metrics(value_kind='boolean')      # discover DMs + IDs
  → genes_by_boolean_metric(...)                # pull flagged genes
  → gene_overview(locus_tags=[...])             # routing on flagged set

list_derived_metrics(value_kind='categorical')  # discover DMs + IDs
  → genes_by_categorical_metric(categories=[...])
  → genes_by_function(...) / pathway_enrichment(...)
```

## KG dependencies

| Layer | Element | Notes |
|---|---|---|
| Node | `DerivedMetric` | `value_kind, rankable, has_p_value` are stored as **string** `"true"` / `"false"` (BioCypher constraint — coerce to bool at builder boundary) |
| Edge | `Derived_metric_flags_gene` | Boolean DM → Gene. Keys: `id, metric_type, value`. `value` ∈ `{"true", "false"}` (string). |
| Edge | `Derived_metric_classifies_gene` | Categorical DM → Gene. Keys: `id, metric_type, value`. `value` is one of parent `dm.allowed_categories`. |
| Node | `Gene` | Result columns: `locus_tag, gene_name, product, gene_category, organism_name, function_description, gene_summary` |
| Node | `DerivedMetric` (boolean precomputed stats) | `flag_true_count, flag_false_count` — full-DM positive/negative tally. Today `flag_false_count=0` on all DMs (positive-only storage). |
| Node | `DerivedMetric` (categorical precomputed stats) | `category_labels` (list[str]) + `category_counts` (list[int]), parallel arrays — full-DM histogram across observed categories. `allowed_categories` is the schema-declared full set (may be a superset of observed labels). |

KG-spec reference: [unified `r.value`](../kg-specs/2026-04-26-unify-derived-metric-edge-value.md).

### Live KG state (verified 2026-04-26)

| Kind | DMs | Edges | Compartments | Sources |
|---|---:|---:|---|---|
| boolean | 16 | 4,694 | `whole_cell, vesicle` | Lopez 2017 (Alteromonas EZ55, 8 enrichment-set DMs); Biller 2018 (NATL2A + MIT1002 periodicity, 6 DMs); Biller 2014 (vesicle proteome × MED4 / MIT9313, 2 DMs) |
| categorical | 3 | 316 | `whole_cell, vesicle` | Biller 2014 (PSORTb localization × MED4 / MIT9313, 2 DMs — same `metric_type` across organisms); Biller 2018 (`darkness_survival_class`, 1 DM) |

Every current boolean and categorical DM has `rankable="false"`,
`has_p_value="false"`. The `rankable` / `has_p_value` echo on each
result row is informative-but-redundant for these two tools (homogeneous
per call) — kept on every row for **cross-tool result-shape
consistency** with `genes_by_numeric_metric` (slice-1 spec §"Result
columns").

---

## Tool Signatures

Identical scaffolding except for the kind-specific edge filter (boxed)
and the kind-specific envelope members.

### Tool 4 — `genes_by_boolean_metric`

```python
@mcp.tool(
    tags={"derived_metric", "boolean", "drill_down"},
    annotations={"readOnlyHint": True},
)
async def genes_by_boolean_metric(
    ctx: Context,
    # Selection — exactly one required (mutually exclusive)
    derived_metric_ids: Annotated[list[str] | None, Field(...)] = None,
    metric_types: Annotated[list[str] | None, Field(...)] = None,
    # Scoping — intersected with selected DM set
    organism: Annotated[str | None, Field(...)] = None,
    locus_tags: Annotated[list[str] | None, Field(...)] = None,
    experiment_ids: Annotated[list[str] | None, Field(...)] = None,
    publication_doi: Annotated[list[str] | None, Field(...)] = None,
    compartment: Annotated[str | None, Field(...)] = None,
    treatment_type: Annotated[list[str] | None, Field(...)] = None,
    background_factors: Annotated[list[str] | None, Field(...)] = None,
    growth_phases: Annotated[list[str] | None, Field(...)] = None,
    # ┌─────────────────────────────────────────────────────────┐
    # │ Kind-specific edge filter                                │
    flag: Annotated[bool | None, Field(...)] = None,
    # └─────────────────────────────────────────────────────────┘
    # Structural
    summary: Annotated[bool, Field(...)] = False,
    verbose: Annotated[bool, Field(...)] = False,
    limit: Annotated[int, Field(ge=1)] = 5,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> GenesByBooleanMetricResponse: ...
```

### Tool 5 — `genes_by_categorical_metric`

```python
@mcp.tool(
    tags={"derived_metric", "categorical", "drill_down"},
    annotations={"readOnlyHint": True},
)
async def genes_by_categorical_metric(
    ctx: Context,
    # Selection — exactly one required (mutually exclusive)
    derived_metric_ids: Annotated[list[str] | None, Field(...)] = None,
    metric_types: Annotated[list[str] | None, Field(...)] = None,
    # Scoping — same block as Tool 4
    organism: Annotated[str | None, Field(...)] = None,
    locus_tags: Annotated[list[str] | None, Field(...)] = None,
    experiment_ids: Annotated[list[str] | None, Field(...)] = None,
    publication_doi: Annotated[list[str] | None, Field(...)] = None,
    compartment: Annotated[str | None, Field(...)] = None,
    treatment_type: Annotated[list[str] | None, Field(...)] = None,
    background_factors: Annotated[list[str] | None, Field(...)] = None,
    growth_phases: Annotated[list[str] | None, Field(...)] = None,
    # ┌─────────────────────────────────────────────────────────┐
    # │ Kind-specific edge filter                                │
    categories: Annotated[list[str] | None, Field(...)] = None,
    # └─────────────────────────────────────────────────────────┘
    # Structural
    summary: Annotated[bool, Field(...)] = False,
    verbose: Annotated[bool, Field(...)] = False,
    limit: Annotated[int, Field(ge=1)] = 5,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> GenesByCategoricalMetricResponse: ...
```

---

## Result-size controls

Identical to `genes_by_numeric_metric`: large result set with summary +
detail modes. `summary=True` is sugar for `limit=0` (api/ skips the
detail query). MCP default `limit=5`.

### Per-result columns (compact, 11)

Identical across both tools — same shared block as `genes_by_numeric_metric`'s
compact, minus the rank/percentile/bucket trio (which is irrelevant to
the non-numeric edges):

| Column | Type | Notes |
|---|---|---|
| `locus_tag` | str | `g.locus_tag` |
| `gene_name` | str \| null | `g.gene_name` |
| `product` | str \| null | `g.product` |
| `gene_category` | str \| null | `g.gene_category` |
| `organism_name` | str | `g.organism_name` |
| `derived_metric_id` | str | `dm.id` |
| `name` | str | `dm.name` |
| `value_kind` | str | `'boolean'` (Tool 4) or `'categorical'` (Tool 5). Echoed for cross-tool row-shape consistency with `genes_by_numeric_metric`. |
| `rankable` | bool | Always `false` for current DMs in both tools. Echoed for cross-tool consistency. |
| `has_p_value` | bool | Always `false` for current DMs in both tools. Echoed for cross-tool consistency. |
| `value` | str | Tool 4: `"true"` / `"false"` (string-typed bool — see KG-spec §Out of scope). Tool 5: category label. |

### Per-result columns (verbose adds, 13/14)

Identical to `genes_by_numeric_metric` verbose set. Tool 5 adds one
extra column (`allowed_categories`) so every categorical row is
self-describing about its parent DM's full category set:

| Column | Type | Source |
|---|---|---|
| `metric_type` | str | `dm.metric_type` |
| `field_description` | str \| null | `dm.field_description` |
| `unit` | str \| null | `dm.unit` (typically null for boolean / categorical DMs) |
| `compartment` | str \| null | `dm.compartment` |
| `experiment_id` | str | `dm.experiment_id` |
| `publication_doi` | str | `dm.publication_doi` |
| `treatment_type` | list[str] | `coalesce(dm.treatment_type, [])` |
| `background_factors` | list[str] | `coalesce(dm.background_factors, [])` |
| `treatment` | str \| null | `dm.treatment` |
| `light_condition` | str \| null | `dm.light_condition` |
| `experimental_context` | str \| null | `dm.experimental_context` |
| `gene_function_description` | str \| null | `g.function_description` |
| `gene_summary` | str \| null | `g.gene_summary` |
| **(Tool 5 only)** `allowed_categories` | list[str] | `dm.allowed_categories` |

### Sort keys (deterministic, paginatable)

| Tool | ORDER BY |
|---|---|
| `genes_by_boolean_metric` | `dm.id ASC, g.locus_tag ASC` |
| `genes_by_categorical_metric` | `r.value ASC, dm.id ASC, g.locus_tag ASC` |

Boolean: no scalar to rank by; group rows by DM, then by locus_tag
within each DM. (When a paper materializes `r.value="false"` edges in
the future, slot `r.value DESC` between the two keys so `"true"`
groups before `"false"` within each DM. **Migration cost:** changing
the sort key invalidates regression baselines pinned to the current
2-key order — at that point regenerate via
`pytest tests/regression/ --force-regen -m kg`.)

Categorical: group by category first (most-readable for the LLM), then
by DM within category, then by locus_tag.

---

## Envelope shape

Same scaffolding as `GenesByNumericMetricResponse`, plus one
kind-specific envelope-level frequency rollup, plus a kind-specific
shape inside `by_metric`. Layout below shows shared fields once, then
boolean-specific, then categorical-specific.

### Shared envelope fields (both tools)

| Field | Type | Notes |
|---|---|---|
| `total_matching` | int | Rows post-filter (gene × DM pairs) |
| `total_derived_metrics` | int | DMs that survived selection + scoping (= len of surviving list). For these tools: same as numeric's "post-gate-survivors" count, but no gate exists, so it is just selection ∩ scoping. |
| `total_genes` | int | Distinct genes in the filtered slice |
| `by_organism` | list[{organism_name, count}] | Frequency rollup |
| `by_compartment` | list[{compartment, count}] | Frequency rollup |
| `by_publication` | list[{publication_doi, count}] | Frequency rollup |
| `by_experiment` | list[{experiment_id, count}] | Frequency rollup |
| `top_categories` | list[{gene_category, count}] | Top 5 by count, post-rename via `_rename_freq` |
| `genes_per_metric_max` | int | Max gene count across surviving DMs |
| `genes_per_metric_median` | float | Median gene count across surviving DMs |
| `not_found_ids` | list[str] | `derived_metric_ids` echo: passed but absent from KG (or scoped out by organism / publication / etc.) |
| `not_matched_ids` | list[str] | `derived_metric_ids` echo: present in KG but contributed zero rows post edge-filter |
| `not_found_metric_types` | list[str] | `metric_types` echo: tag matches no DM under the scope |
| `not_matched_metric_types` | list[str] | `metric_types` echo: tag matched DMs but all of them contributed zero rows post edge-filter |
| `not_matched_organism` | str \| null | `organism` echo when the param was set but no result row carried it (typo-detection signal) |
| `excluded_derived_metrics` | list[{...}] | **Always `[]`** for these two tools (no rankable / has_p_value gates). Kept as an envelope key for cross-tool row-shape consistency with `genes_by_numeric_metric` (slice-1 spec §"Gate-exclusion coverage" — "asserted to be keys on every drill-down response"). |
| `warnings` | list[str] | **Always `[]`** for these two tools. Same rationale. |
| `returned` | int | `len(results)` |
| `offset` | int | Echo of pagination offset |
| `truncated` | bool | `total_matching > offset + returned` |
| `results` | list[GenesByBooleanMetricResult \| GenesByCategoricalMetricResult] | Per-row data |

### Boolean-specific envelope additions

| Field | Type | Notes |
|---|---|---|
| `by_value` | list[{value, count}] | Frequency rollup of `r.value` across all surviving rows. Today every row is `"true"` (positive-only KG storage). When a paper materializes `"false"` edges, this surfaces the split without the LLM rewriting its query. |

`by_metric` row shape (one entry per surviving DM):

| Field | Type | Notes |
|---|---|---|
| `derived_metric_id` | str | |
| `name` | str | `dm.name` |
| `metric_type` | str | `dm.metric_type` |
| `value_kind` | str | Always `"boolean"` |
| `count` | int | Filtered slice — rows from this DM in the current result |
| `true_count` | int | Filtered slice — `r.value="true"` count |
| `false_count` | int | Filtered slice — `r.value="false"` count (always 0 today) |
| `dm_total_gene_count` | int | Full-DM tally (`dm.total_gene_count`) |
| `dm_true_count` | int | Full-DM tally (`dm.flag_true_count`) |
| `dm_false_count` | int | Full-DM tally (`dm.flag_false_count` — always 0 today) |

Pairing rationale: the LLM can read "your filtered slice has 32 of 32
flagged-true genes from the MED4 DM — the slice is the entire DM" or
"...has 5 of 1377 NATL2A periodic genes" without a follow-up
`list_derived_metrics` call. Mirrors numeric's filtered-slice
`value_min/q1/median` paired with full-DM `dm_value_min/q1/median`.

### Categorical-specific envelope additions

| Field | Type | Notes |
|---|---|---|
| `by_category` | list[{category, count}] | Frequency rollup of `r.value` across all surviving rows. Cross-DM unioned — a category present in two DMs sums. |

`by_metric` row shape (one entry per surviving DM):

| Field | Type | Notes |
|---|---|---|
| `derived_metric_id` | str | |
| `name` | str | `dm.name` |
| `metric_type` | str | `dm.metric_type` |
| `value_kind` | str | Always `"categorical"` |
| `count` | int | Filtered slice — rows from this DM in the current result |
| `by_category` | list[{category, count}] | Filtered slice — per-DM frequency, computed via `apoc.coll.frequencies` on filtered rows |
| `allowed_categories` | list[str] | `dm.allowed_categories` — schema-declared full set (may be a superset of observed) |
| `dm_total_gene_count` | int | Full-DM tally (`dm.total_gene_count`) |
| `dm_by_category` | list[{category, count}] | Full-DM histogram, zip of `dm.category_labels` + `dm.category_counts`. Includes only observed categories. |

Pairing rationale: same as boolean — slice vs full-DM context in one
view. The `allowed_categories` superset lets the LLM detect when a
category is declared but unobserved in the entire DM (e.g. MED4 PSORTb
declares `Extracellular` but it's absent from `dm_by_category`).

### Validation matrix (both tools)

| Situation | Behavior |
|---|---|
| Both `derived_metric_ids` AND `metric_types` set | `ValueError` "provide one of derived_metric_ids or metric_types, not both" |
| Neither selection param set | `ValueError` "must provide one of derived_metric_ids or metric_types" |
| `summary=True` | Force `limit=0` internally; detail query skipped |
| Selected DM has wrong `value_kind` (e.g. numeric DM passed to Tool 4) | **No raise** — diagnostics hardcodes `dm.value_kind='boolean'` (Tool 4) / `'categorical'` (Tool 5), so wrong-kind IDs simply fall into `not_found_ids`. Matches `genes_by_numeric_metric` behavior (api/functions.py:3000-3035 has no kind-mismatch branch — wrong-kind IDs land in `not_found_ids` silently). The `mistakes:` YAML for both tools tells the LLM to inspect `list_derived_metrics(value_kind='boolean')` / `list_derived_metrics(value_kind='categorical')` first. |
| **Tool 5 only** — `categories` includes value not in union of selected DMs' `allowed_categories` | `ValueError` listing unknowns + the allowed union |
| Selection scoped down to zero DMs (no surviving IDs after diagnostics) | Return empty envelope without running summary/detail (avoids `IN $derived_metric_ids` with empty list); `not_found_*` populated |
| `locus_tags` empty list | **No raise** — matches `genes_by_numeric_metric` (api/functions.py mutex check is the only validation; empty list passes through to Cypher and yields zero rows). Distinct from `gene_derived_metrics` (Tool 2), where `locus_tags` is required because that tool is single-organism batch over a gene set rather than a drill-down. |
| Single-organism check (locus_tags spanning organisms) | **Not enforced** — these tools are cross-organism by design, like `genes_by_numeric_metric`. The `_validate_organism_inputs` helper is **not** called. |

Skipped (compared to `genes_by_numeric_metric`):

- Rankable-gate validation (no rankable filter exists on these tools)
- has_p_value-gate validation (no p-value filter exists on these tools)
- `excluded_derived_metrics` / `warnings` population — keys are always
  `[]` but always present.

---

## Special handling

- **Cross-organism by design** — single-organism not enforced (matches
  `genes_by_numeric_metric`). `metric_type` like `vesicle_proteome_member`
  spans MED4 + MIT9313; `predicted_subcellular_localization` spans the
  same two strains. Callers who want one strain pass `organism=...`
  explicitly.
- **3-query orchestration** (mirrors numeric):
  1. Diagnostics — resolve `metric_types` / `derived_metric_ids` to
     surviving DM IDs by intersecting selection with `dm.value_kind`
     hardcode + scoping filters. For Tool 5, also fetch
     `dm.allowed_categories` per DM so api/ can validate `categories`
     against the union before summary/detail run.
  2. Summary — always runs (over surviving DM ID list)
  3. Detail — skipped when `limit==0`
- **Wrong-kind IDs surface as `not_found_ids`, not as a raise.** The
  diagnostics WHERE clause hardcodes `dm.value_kind='boolean'` (Tool 4)
  / `dm.value_kind='categorical'` (Tool 5), so a wrong-kind
  `derived_metric_id` doesn't survive the probe and api/ reports it as
  `not_found_ids`. This matches `genes_by_numeric_metric` exactly
  (which behaves the same way despite slice-1 spec §"Cross-cutting
  validation" line 427 promising a raise — the implementation never
  honored that). Per-tool `mistakes:` YAML tells the LLM to check
  `list_derived_metrics(value_kind=...)` first.
- **String-typed booleans on edges (Tool 4 only)** — `r.value` for
  `Derived_metric_flags_gene` is `"true"` / `"false"` (string), not
  Neo4j-native bool, due to the BioCypher constraint documented in the
  KG spec. The MCP `flag` param is a real Python `bool | None`; coerce
  at the query-builder boundary: `flag=True` → `r.value = 'true'`,
  `flag=False` → `r.value = 'false'`. The result column `value` is
  surfaced as the raw string for transparency (callers can see what's
  in the KG).
- **Positive-only storage gotcha (Tool 4 only)** — every current DM
  has `flag_false_count=0`; `flag=False` returns zero rows today. The
  `by_metric` envelope's `dm_false_count` makes this self-evident
  without an extra call. YAML `mistakes:` must surface this.
- **No CASE-gate-on-RETURN** — boolean / categorical edges have no
  rankable / has_p_value extras. Only the DM-level `rankable` /
  `has_p_value` echoes ride along on every row for cross-tool shape
  consistency. Skip the CASE wrappers used by numeric for
  `rank_by_metric` / `metric_percentile` / `metric_bucket`.

---

## Implementation Order

| Step | Layer | File | What |
|---|---|---|---|
| 1 | Query builder | `kg/queries_lib.py` | `build_genes_by_boolean_metric_diagnostics`, `_summary`, `(detail)` ×3 — and the same trio for categorical. 6 new builders. |
| 2 | API function | `api/functions.py` | `genes_by_boolean_metric()` + `genes_by_categorical_metric()` |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add both to imports + `__all__` |
| 4 | MCP wrapper | `mcp_server/tools.py` | 2 `@mcp.tool()` wrappers + Pydantic models per tool |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | `TestBuildGenesByBooleanMetric*` (×3 builders) + `TestBuildGenesByCategoricalMetric*` (×3 builders) |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | `TestGenesByBooleanMetric` + `TestGenesByCategoricalMetric` |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | `TestGenesByBooleanMetricWrapper` + `TestGenesByCategoricalMetricWrapper` + update `EXPECTED_TOOLS` |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | Smoke + happy-path per tool |
| 9 | Regression | `tests/regression/test_regression.py` | Add both to `TOOL_BUILDERS` |
| 10 | Eval cases | `tests/evals/cases.yaml` | One representative case per tool (boolean: vesicle proteome cross-organism; categorical: PSORTb membrane categories) |
| 11 | About content | `multiomics_explorer/inputs/tools/genes_by_boolean_metric.yaml` + `..._categorical_metric.yaml` | Examples, chaining, mistakes (incl. positive-only storage note for boolean) |
| 12 | Generated docs | `multiomics_explorer/skills/multiomics-kg-guide/references/tools/{name}.md` | `uv run python scripts/build_about_content.py {name}` × 2 |
| 13 | Docs | `CLAUDE.md` | 2 new rows in MCP Tools table |

Phase 2 build can run in parallel for the two tools — they touch
disjoint Pydantic models, separate API functions, separate test
classes. Recommend executing sequentially through the layers (builder
→ api → wrapper → tests) for both tools at each layer to keep the
diff reviewable.

---

## Query Builders

**File:** `kg/queries_lib.py`

Each tool gets 3 builders (mirrors numeric). Boolean and categorical
diagnostics builders share the same scaffolding; only the hardcoded
`value_kind` differs and (for categorical) the addition of
`allowed_categories` to RETURN.

### Tool 4 — `build_genes_by_boolean_metric_diagnostics`

```python
def build_genes_by_boolean_metric_diagnostics(
    *,
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """Pre-flight DM selection + value_kind validation probe.

    Reuses _list_derived_metrics_where with hardcoded value_kind='boolean'.
    Mismatches surface as zero-row results that api/ converts to ValueError.

    RETURN keys (one row per surviving DM, 6 columns):
      derived_metric_id, metric_type, value_kind, name,
      total_gene_count, organism_name.
    """
```

**Cypher (verified against live KG):**

```cypher
MATCH (dm:DerivedMetric)
WHERE dm.value_kind = 'boolean'
  AND <selection conditions: dm.id IN $... OR dm.metric_type IN $...>
  AND <scoping conditions per scope filter>
RETURN dm.id              AS derived_metric_id,
       dm.metric_type     AS metric_type,
       dm.value_kind      AS value_kind,
       dm.name            AS name,
       dm.total_gene_count AS total_gene_count,
       dm.organism_name   AS organism_name
ORDER BY dm.id ASC
```

Verified live: `metric_types=['vesicle_proteome_member']` → 2 rows
(MED4 + MIT9313 DMs).

### Tool 4 — `build_genes_by_boolean_metric_summary`

```python
def build_genes_by_boolean_metric_summary(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    flag: bool | None = None,
) -> tuple[str, dict]:
    """Build summary Cypher.

    Takes the diagnostics-validated derived_metric_ids list plus the
    edge-level flag filter (no gate validation needed — both tools have
    no gates). Produces all envelope rollups in one query.

    RETURN keys: total_matching, total_derived_metrics, total_genes,
    by_organism, by_compartment, by_publication, by_experiment,
    by_value, top_categories_raw, by_metric (per-DM filtered + full-DM
    stats), genes_per_metric_max, genes_per_metric_median.
    """
```

**Cypher (verified against live KG):**

```cypher
MATCH (dm:DerivedMetric)-[r:Derived_metric_flags_gene]->(g:Gene)
WHERE dm.id IN $derived_metric_ids
  [AND g.locus_tag IN $locus_tags]
  [AND r.value = $flag_str]   -- 'true' / 'false', when flag is set
WITH collect({
  dm_id: dm.id, dm_name: dm.name, mt: dm.metric_type, vk: dm.value_kind,
  org: g.organism_name, cat: coalesce(g.gene_category, 'Unknown'),
  comp: dm.compartment, doi: dm.publication_doi, exp: dm.experiment_id,
  lt: g.locus_tag,
  value: r.value,
  dm_total: dm.total_gene_count,
  dm_true: dm.flag_true_count,
  dm_false: dm.flag_false_count
}) AS rows
RETURN
  size(rows) AS total_matching,
  size(apoc.coll.toSet([x IN rows | x.dm_id])) AS total_derived_metrics,
  size(apoc.coll.toSet([x IN rows | x.lt]))    AS total_genes,
  apoc.coll.frequencies([x IN rows | x.org])   AS by_organism,
  apoc.coll.frequencies([x IN rows | x.comp])  AS by_compartment,
  apoc.coll.frequencies([x IN rows | x.doi])   AS by_publication,
  apoc.coll.frequencies([x IN rows | x.exp])   AS by_experiment,
  apoc.coll.frequencies([x IN rows | x.value]) AS by_value,
  apoc.coll.frequencies([x IN rows | x.cat])   AS top_categories_raw,
  [dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |
    {derived_metric_id: dm_id,
     name:        head([x IN rows WHERE x.dm_id = dm_id | x.dm_name]),
     metric_type: head([x IN rows WHERE x.dm_id = dm_id | x.mt]),
     value_kind:  head([x IN rows WHERE x.dm_id = dm_id | x.vk]),
     count:       size([x IN rows WHERE x.dm_id = dm_id]),
     true_count:  size([x IN rows WHERE x.dm_id = dm_id AND x.value = 'true']),
     false_count: size([x IN rows WHERE x.dm_id = dm_id AND x.value = 'false']),
     dm_total_gene_count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_total]),
     dm_true_count:  head([x IN rows WHERE x.dm_id = dm_id | x.dm_true]),
     dm_false_count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_false])
    }] AS by_metric,
  apoc.coll.max([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |
                 size([x IN rows WHERE x.dm_id = dm_id])]) AS genes_per_metric_max,
  toFloat(apoc.coll.sort([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |
                          size([x IN rows WHERE x.dm_id = dm_id])])
          [toInteger(size(apoc.coll.toSet([x IN rows | x.dm_id])) / 2)])
    AS genes_per_metric_median
```

Verified live: `metric_types=['vesicle_proteome_member']` →
`total_matching=58, total_derived_metrics=2, total_genes=58,
by_value=[{count:58, item:"true"}], by_metric` shows MED4 (32/32) +
MIT9313 (26/26) with `dm_true_count` matching `count` and
`dm_false_count=0` (positive-only storage).

### Tool 4 — `build_genes_by_boolean_metric` (detail)

```python
def build_genes_by_boolean_metric(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    flag: bool | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """Build detail Cypher.

    11 compact columns (per-row gene + DM identity + value), plus 13
    verbose columns. No CASE-gate wrappers needed — boolean edges have
    no rankable / has_p_value extras.

    RETURN keys (compact, 11): locus_tag, gene_name, product, gene_category,
    organism_name, derived_metric_id, name, value_kind, rankable,
    has_p_value, value.
    RETURN keys (verbose adds, 13): metric_type, field_description, unit,
    compartment, experiment_id, publication_doi, treatment_type,
    background_factors, treatment, light_condition, experimental_context,
    gene_function_description, gene_summary.
    """
```

**Cypher (verified):**

```cypher
MATCH (dm:DerivedMetric)-[r:Derived_metric_flags_gene]->(g:Gene)
WHERE dm.id IN $derived_metric_ids
  [AND g.locus_tag IN $locus_tags]
  [AND r.value = $flag_str]
RETURN g.locus_tag       AS locus_tag,
       g.gene_name       AS gene_name,
       g.product         AS product,
       g.gene_category   AS gene_category,
       g.organism_name   AS organism_name,
       dm.id             AS derived_metric_id,
       dm.name           AS name,
       dm.value_kind     AS value_kind,
       dm.rankable = 'true'    AS rankable,
       dm.has_p_value = 'true' AS has_p_value,
       r.value           AS value
       <verbose columns ...>
ORDER BY dm.id ASC, g.locus_tag ASC
[SKIP $offset]
[LIMIT $limit]
```

Verified live: `metric_types=['vesicle_proteome_member']`, limit 3 →
3 rows (PMM0090, PMM0097, PMM0107) all from MED4 DM, all `value="true"`,
`rankable=false`, `has_p_value=false`.

### Tool 5 — `build_genes_by_categorical_metric_diagnostics`

Same scaffolding as Tool 4's diagnostics, with two changes:

- Hardcoded `dm.value_kind = 'categorical'`
- One additional RETURN column: `dm.allowed_categories AS allowed_categories`
  (api/ unions these per DM and validates `categories` against the union)

```python
def build_genes_by_categorical_metric_diagnostics(
    *,
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
) -> tuple[str, dict]:
    """RETURN keys (one row per surviving DM, 7 columns):
      derived_metric_id, metric_type, value_kind, name,
      total_gene_count, organism_name, allowed_categories.
    """
```

**Cypher (verified live):**

```cypher
MATCH (dm:DerivedMetric)
WHERE dm.value_kind = 'categorical'
  AND <selection + scoping conditions>
RETURN dm.id              AS derived_metric_id,
       dm.metric_type     AS metric_type,
       dm.value_kind      AS value_kind,
       dm.name            AS name,
       dm.total_gene_count AS total_gene_count,
       dm.organism_name   AS organism_name,
       dm.allowed_categories AS allowed_categories
ORDER BY dm.id ASC
```

Verified live: `metric_types=['predicted_subcellular_localization']` →
2 rows (MED4 + MIT9313 DMs), each carrying the 6-element
`allowed_categories` list.

### Tool 5 — `build_genes_by_categorical_metric_summary`

```python
def build_genes_by_categorical_metric_summary(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    categories: list[str] | None = None,
) -> tuple[str, dict]:
    """RETURN keys: total_matching, total_derived_metrics, total_genes,
    by_organism, by_compartment, by_publication, by_experiment,
    by_category, top_categories_raw, by_metric (per-DM filtered slice +
    full-DM precomputed histogram), genes_per_metric_max,
    genes_per_metric_median.
    """
```

**Cypher (verified):**

```cypher
MATCH (dm:DerivedMetric)-[r:Derived_metric_classifies_gene]->(g:Gene)
WHERE dm.id IN $derived_metric_ids
  [AND g.locus_tag IN $locus_tags]
  [AND r.value IN $categories]
WITH collect({
  dm_id: dm.id, dm_name: dm.name, mt: dm.metric_type, vk: dm.value_kind,
  org: g.organism_name, cat: coalesce(g.gene_category, 'Unknown'),
  comp: dm.compartment, doi: dm.publication_doi, exp: dm.experiment_id,
  lt: g.locus_tag,
  value: r.value,
  dm_total: dm.total_gene_count,
  dm_labels: dm.category_labels,
  dm_counts: dm.category_counts,
  dm_allowed: dm.allowed_categories
}) AS rows
RETURN
  size(rows) AS total_matching,
  size(apoc.coll.toSet([x IN rows | x.dm_id])) AS total_derived_metrics,
  size(apoc.coll.toSet([x IN rows | x.lt]))    AS total_genes,
  apoc.coll.frequencies([x IN rows | x.org])   AS by_organism,
  apoc.coll.frequencies([x IN rows | x.comp])  AS by_compartment,
  apoc.coll.frequencies([x IN rows | x.doi])   AS by_publication,
  apoc.coll.frequencies([x IN rows | x.exp])   AS by_experiment,
  apoc.coll.frequencies([x IN rows | x.value]) AS by_category,
  apoc.coll.frequencies([x IN rows | x.cat])   AS top_categories_raw,
  [dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |
    {derived_metric_id: dm_id,
     name:        head([x IN rows WHERE x.dm_id = dm_id | x.dm_name]),
     metric_type: head([x IN rows WHERE x.dm_id = dm_id | x.mt]),
     value_kind:  head([x IN rows WHERE x.dm_id = dm_id | x.vk]),
     count:       size([x IN rows WHERE x.dm_id = dm_id]),
     by_category: apoc.coll.frequencies([x IN rows WHERE x.dm_id = dm_id | x.value]),
     allowed_categories:  head([x IN rows WHERE x.dm_id = dm_id | x.dm_allowed]),
     dm_total_gene_count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_total]),
     dm_by_category:
       [i IN range(0,
            size(head([x IN rows WHERE x.dm_id = dm_id | x.dm_labels])) - 1)
        | {item:  head([x IN rows WHERE x.dm_id = dm_id | x.dm_labels])[i],
           count: head([x IN rows WHERE x.dm_id = dm_id | x.dm_counts])[i]}]
    }] AS by_metric,
  apoc.coll.max([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |
                 size([x IN rows WHERE x.dm_id = dm_id])]) AS genes_per_metric_max,
  toFloat(apoc.coll.sort([dm_id IN apoc.coll.toSet([x IN rows | x.dm_id]) |
                          size([x IN rows WHERE x.dm_id = dm_id])])
          [toInteger(size(apoc.coll.toSet([x IN rows | x.dm_id])) / 2)])
    AS genes_per_metric_median
```

Verified live: `metric_types=['predicted_subcellular_localization'],
categories=['Outer Membrane', 'Periplasmic']` → `total_matching=14,
total_derived_metrics=2`, `by_category=[{Periplasmic:6}, {Outer
Membrane:8}]`, per-DM `by_metric` shows MED4 slice (5 OM + 3 PP) vs
full-DM histogram (11 Cyto / 6 CM / 5 OM / 3 PP / 7 Unknown — note
"Extracellular" appears in `allowed_categories` but absent from
`dm_by_category` → schema-declared but unobserved category).

### Tool 5 — `build_genes_by_categorical_metric` (detail)

Same scaffolding as Tool 4's detail, swapping the edge label and the
filter param:

```python
def build_genes_by_categorical_metric(
    *,
    derived_metric_ids: list[str],
    locus_tags: list[str] | None = None,
    categories: list[str] | None = None,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict]:
    """RETURN keys (compact, 11): same as Tool 4.
    RETURN keys (verbose adds, 14): same as Tool 4 + allowed_categories.
    """
```

**Cypher (verified):**

```cypher
MATCH (dm:DerivedMetric)-[r:Derived_metric_classifies_gene]->(g:Gene)
WHERE dm.id IN $derived_metric_ids
  [AND g.locus_tag IN $locus_tags]
  [AND r.value IN $categories]
RETURN g.locus_tag       AS locus_tag,
       g.gene_name       AS gene_name,
       g.product         AS product,
       g.gene_category   AS gene_category,
       g.organism_name   AS organism_name,
       dm.id             AS derived_metric_id,
       dm.name           AS name,
       dm.value_kind     AS value_kind,
       dm.rankable = 'true'    AS rankable,
       dm.has_p_value = 'true' AS has_p_value,
       r.value           AS value
       <verbose columns including dm.allowed_categories AS allowed_categories>
ORDER BY r.value ASC, dm.id ASC, g.locus_tag ASC
[SKIP $offset]
[LIMIT $limit]
```

Verified live: `metric_types=['predicted_subcellular_localization'],
categories=['Outer Membrane', 'Periplasmic']`, limit 5 → 5 rows all
from MED4 DM with `value="Outer Membrane"` (sort key drives this —
"Outer Membrane" < "Periplasmic" alphabetically); first 5 locus_tags
PMM0097, PMM0254, PMM1124, PMM1162, PMM1338 — all with `rankable=false`,
`has_p_value=false`.

### Shared WHERE-clause builder

Both diagnostics builders should reuse the existing
`_list_derived_metrics_where()` helper (already used by numeric
diagnostics) with the kind hardcoded. Both summary + detail builders
build `conditions` + `params` inline (mirrors numeric).

---

## API Functions

**File:** `api/functions.py`

Both functions follow the exact same orchestration as
`genes_by_numeric_metric()` (api/functions.py:2936), with the
gate-validation steps (numeric §5–§6) removed. Trimmed-down structure:

```python
def genes_by_boolean_metric(
    derived_metric_ids: list[str] | None = None,
    metric_types: list[str] | None = None,
    organism: str | None = None,
    locus_tags: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    publication_doi: list[str] | None = None,
    compartment: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    flag: bool | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """Boolean DerivedMetric drill-down. Cross-organism by design.

    3-query orchestration:
      1. diagnostics — resolve selection by intersecting with
         dm.value_kind='boolean' + scoping filters; surviving IDs
         drive Q2/Q3. Wrong-kind IDs and IDs filtered out by scoping
         both surface as not_found_ids (matches genes_by_numeric_metric).
      2. summary — aggregations over surviving DM ID list (always runs).
      3. detail — rows; skipped when limit==0.

    Selection is mutually exclusive: pass exactly one of
    derived_metric_ids or metric_types.

    Returns dict with keys: total_matching, total_derived_metrics,
    total_genes, by_organism, by_compartment, by_publication,
    by_experiment, by_value, by_metric, top_categories,
    genes_per_metric_max, genes_per_metric_median, not_found_ids,
    not_matched_ids, not_found_metric_types, not_matched_metric_types,
    not_matched_organism, excluded_derived_metrics (always []),
    warnings (always []), returned, offset, truncated, results.

    Raises:
        ValueError: derived_metric_ids+metric_types both/neither set.
    """
```

```python
def genes_by_categorical_metric(
    # … same scaffolding as boolean, with `categories` instead of `flag` …
) -> dict:
    """Categorical DerivedMetric drill-down. Cross-organism by design.

    Same 3-query orchestration as genes_by_boolean_metric, plus a
    pre-summary validation step on the categorical edge filter:

      1. diagnostics — resolve selection by intersecting with
         dm.value_kind='categorical' + scoping; collect each surviving
         DM's allowed_categories. Wrong-kind IDs surface as not_found_ids.
      2. (api/ validates) — categories filter is subset of union of
         surviving DMs' allowed_categories (raise on unknowns).
      3. summary — aggregations over surviving DM ID list (always runs).
      4. detail — rows; skipped when limit==0.

    Returns dict with keys: total_matching, total_derived_metrics,
    total_genes, by_organism, by_compartment, by_publication,
    by_experiment, by_category, by_metric, top_categories,
    genes_per_metric_max, genes_per_metric_median, not_found_ids,
    not_matched_ids, not_found_metric_types, not_matched_metric_types,
    not_matched_organism, excluded_derived_metrics (always []),
    warnings (always []), returned, offset, truncated, results.

    Raises:
        ValueError: derived_metric_ids+metric_types both/neither set;
                    categories includes unknown value (post-survivor union).
    """
```

### Orchestration steps (both functions)

1. Mutex check on `derived_metric_ids` / `metric_types` (same as numeric)
2. `summary=True` → `limit=0`
3. Q1: diagnostics — execute the kind-specific diagnostics builder
4. Build `not_found_ids` / `not_found_metric_types` from the diagnostics survivors
5. **(Categorical only)** Validate `categories` ⊆ union of `dm.allowed_categories`
   across surviving DMs; raise `ValueError` listing unknowns + the
   allowed union if not
6. **Defensive empty-survivor short-circuit** — if no DM survived
   selection + scoping, return an empty envelope with
   `excluded_derived_metrics=[]`, `warnings=[]`, populated `not_found_*`
   (skip Q2/Q3 to avoid `IN $derived_metric_ids` with empty list)
7. Q2: summary — always runs over the surviving DM ID list
8. Frequency-list rename via `_rename_freq`. `apoc.coll.frequencies`
   emits `[{item, count}]`; api/ renames `item → <key>` per
   downstream Pydantic field name:
     - `by_organism: item → organism_name`
     - `by_compartment: item → compartment`
     - `by_publication: item → publication_doi`
     - `by_experiment: item → experiment_id`
     - `top_categories_raw → top_categories[:5]: item → gene_category`
     - **(Tool 4)** `by_value: item → value`
     - **(Tool 5)** `by_category: item → category`
9. `by_metric` post-processing — Cypher emits the per-DM list with
   the right top-level keys, but the **nested** category-frequency
   lists for Tool 5 (`by_category`, `dm_by_category`) and any
   nested boolean breakdowns are still in `{item, count}` shape from
   the inner `apoc.coll.frequencies` / explicit-literal Cypher. api/
   walks each `by_metric` row and:
     - **(Tool 4)** no nested rename needed — `true_count`, `false_count`,
       `dm_*_count` are scalars, not freq lists
     - **(Tool 5)** rename `item → category` on both `by_category` and
       `dm_by_category` per row (helper: `_rename_freq` over each list)
   Then sort the rows by `count` DESC.
10. Compute `not_matched_ids` / `not_matched_metric_types` from the
    DM IDs that survived diagnostics but contributed zero rows post
    edge-filter (mirrors numeric's logic)
11. Compute `not_matched_organism` (organism passed but no `by_organism`
    row matched substring-insensitive)
12. Q3: detail — skipped when `limit==0`
13. Build envelope: `total_matching, total_derived_metrics, ...,
    excluded_derived_metrics=[], warnings=[], returned, offset, truncated, results`

The `excluded_derived_metrics=[]` and `warnings=[]` lines are
deliberate — kept as envelope keys for cross-tool shape consistency,
even though no soft-exclude path exists today.

---

## MCP Wrappers

**File:** `mcp_server/tools.py`

Define 2 sets of Pydantic models (one per tool) plus 2 `@mcp.tool()`
wrappers. Models mirror `GenesByNumericMetric*` (tools.py:4701-5170)
exactly except for the kind-specific envelope and `by_metric` shapes.

### Pydantic models — Tool 4

```python
class GenesByBooleanMetricResult(BaseModel):
    # 11 compact fields
    locus_tag: str = Field(..., description="Gene locus tag.")
    gene_name: str | None = Field(None, description="Gene symbol.")
    product: str | None = Field(None, description="Protein product.")
    gene_category: str | None = Field(None, description="Coarse functional category.")
    organism_name: str = Field(..., description="Organism (e.g. 'Prochlorococcus MED4').")
    derived_metric_id: str = Field(..., description="DM node id.")
    name: str = Field(..., description="DM display name.")
    value_kind: Literal["boolean"] = Field(..., description="Always 'boolean'.")
    rankable: bool = Field(..., description="DM-level rankable flag (always False today).")
    has_p_value: bool = Field(..., description="DM-level p-value flag (always False today).")
    value: str = Field(..., description="'true' or 'false' (string-typed bool).")
    # 13 verbose fields (default None)
    metric_type: str | None = None
    field_description: str | None = None
    unit: str | None = None
    compartment: str | None = None
    experiment_id: str | None = None
    publication_doi: str | None = None
    treatment_type: list[str] | None = None
    background_factors: list[str] | None = None
    treatment: str | None = None
    light_condition: str | None = None
    experimental_context: str | None = None
    gene_function_description: str | None = None
    gene_summary: str | None = None


class GenesByBooleanMetricBreakdown(BaseModel):
    derived_metric_id: str
    name: str
    metric_type: str
    value_kind: Literal["boolean"]   # always 'boolean'
    count: int                 # filtered slice
    true_count: int            # filtered slice
    false_count: int           # filtered slice
    dm_total_gene_count: int   # full-DM precomputed
    dm_true_count: int         # full-DM precomputed
    dm_false_count: int        # full-DM precomputed


class GenesByBooleanMetricValueBreakdown(BaseModel):
    value: str                 # 'true' or 'false'
    count: int


class GenesByBooleanMetricResponse(BaseModel):
    total_matching: int
    total_derived_metrics: int
    total_genes: int
    by_organism: list[GenesByNumericMetricOrganismBreakdown]   # reuse numeric's
    by_compartment: list[GenesByNumericMetricCompartmentBreakdown]
    by_publication: list[GenesByNumericMetricPublicationBreakdown]
    by_experiment: list[GenesByNumericMetricExperimentBreakdown]
    by_value: list[GenesByBooleanMetricValueBreakdown]
    top_categories: list[GenesByNumericMetricCategoryBreakdown]
    by_metric: list[GenesByBooleanMetricBreakdown]
    genes_per_metric_max: int
    genes_per_metric_median: float
    not_found_ids: list[str]
    not_matched_ids: list[str]
    not_found_metric_types: list[str]
    not_matched_metric_types: list[str]
    not_matched_organism: str | None
    excluded_derived_metrics: list[GenesByNumericMetricExcludedDM]   # reuse numeric's
    warnings: list[str]
    returned: int
    offset: int
    truncated: bool
    results: list[GenesByBooleanMetricResult]
```

### Pydantic models — Tool 5

Mirror Tool 4 exactly except:

- `value_kind` field on Result is `Literal["categorical"]`
- `value` field on Result holds a category string (not "true"/"false")
- Verbose-field block adds `allowed_categories: list[str] | None`
- Replace `GenesByBooleanMetricBreakdown` → `GenesByCategoricalMetricBreakdown`:

```python
class GenesByCategoricalMetricCategoryFreq(BaseModel):
    category: str
    count: int

class GenesByCategoricalMetricBreakdown(BaseModel):
    derived_metric_id: str
    name: str
    metric_type: str
    value_kind: Literal["categorical"]                   # always 'categorical'
    count: int                                            # filtered slice
    by_category: list[GenesByCategoricalMetricCategoryFreq]   # filtered slice
    allowed_categories: list[str]                        # full set (schema)
    dm_total_gene_count: int                             # full-DM precomputed
    dm_by_category: list[GenesByCategoricalMetricCategoryFreq]   # full-DM
```

- Replace `by_value` envelope field with `by_category` (same
  `GenesByCategoricalMetricCategoryFreq` shape)
- Reuse all the shared breakdown classes from `GenesByNumericMetric*`
  (organism / compartment / publication / experiment / category /
  excluded_dm)

### Wrapper structure

Both wrappers follow `genes_by_numeric_metric` (tools.py:4943-5170)
exactly:

1. Log selection_size via `await ctx.info(...)`
2. Call `api.genes_by_{kind}_metric(...)` inside a `try/except`
3. Catch `ValueError` → `await ctx.warning(...)` + `raise ToolError`
4. Catch `Exception` → `await ctx.error(...)` + `raise ToolError`
5. Construct typed breakdown lists from the returned dict
6. Return the typed `Response` model

`Annotated[..., Field(description=...)]` on every parameter, with
examples in the description (e.g. `"Metric-type tags (e.g.
['vesicle_proteome_member', 'periodic_in_coculture_LD']). ..."`). No
`Literal["..."]` on `flag` (it's `bool | None`); no `Literal[...]` on
`categories` either (the valid set varies per DM, validated in api/).

---

## Tests

### Unit: query builders (`test_query_builders.py`)

```
class TestBuildGenesByBooleanMetricDiagnostics:
    test_no_filters
    test_metric_types_filter
    test_derived_metric_ids_filter
    test_organism_filter
    test_scoping_filters_combine
    test_value_kind_hardcoded_boolean
    test_returns_expected_columns

class TestBuildGenesByBooleanMetricSummary:
    test_no_filters
    test_locus_tags_filter
    test_flag_true_filter
    test_flag_false_filter
    test_returns_expected_columns
    test_by_metric_carries_dm_precomputed_stats

class TestBuildGenesByBooleanMetric:
    test_no_filters
    test_locus_tags_filter
    test_flag_filter
    test_returns_expected_columns_compact
    test_returns_expected_columns_verbose
    test_order_by
    test_limit_clause
    test_limit_none

# Same trio for categorical, with `categories` filter instead of `flag`.
class TestBuildGenesByCategoricalMetricDiagnostics: ...
class TestBuildGenesByCategoricalMetricSummary:
    test_categories_filter
    test_by_metric_carries_dm_precomputed_histogram
    test_by_metric_includes_allowed_categories
    ...
class TestBuildGenesByCategoricalMetric: ...
```

### Unit: API functions (`test_api_functions.py`)

```
class TestGenesByBooleanMetric:
    test_returns_dict
    test_mutex_selection_raises
    test_neither_selection_raises
    test_kind_mismatch_in_not_found_ids     # numeric/categorical DM passed →
                                            # surfaces in not_found_ids (matches
                                            # genes_by_numeric_metric behavior)
    test_summary_true_skips_detail_query
    test_excluded_derived_metrics_always_empty_list
    test_warnings_always_empty_list
    test_not_found_plumbing
    test_not_matched_plumbing
    test_passes_flag_to_summary_and_detail
    test_creates_conn_when_none
    test_importable_from_package

class TestGenesByCategoricalMetric:
    # … same shape …
    test_kind_mismatch_in_not_found_ids        # boolean/numeric DM → not_found_ids
    test_categories_subset_validation_raises   # unknown category → ValueError
    test_categories_subset_validation_message_lists_allowed_union
    test_passes_categories_to_summary_and_detail
    test_by_category_renamed_item_to_category  # asserts api/'s nested rename
                                               # walks by_metric[*].by_category
                                               # and by_metric[*].dm_by_category
```

### Unit: MCP wrappers (`test_tool_wrappers.py`)

```
class TestGenesByBooleanMetricWrapper:
    test_returns_response_model
    test_empty_results
    test_params_forwarded
    test_truncation_metadata
    test_value_error_raises_tool_error

class TestGenesByCategoricalMetricWrapper:
    # … same shape …

# Update EXPECTED_TOOLS to include "genes_by_boolean_metric" and
# "genes_by_categorical_metric".
```

### Integration (`test_mcp_tools.py`)

Against live KG (`@pytest.mark.kg`):

- **Boolean** — `metric_types=['vesicle_proteome_member']` → 58 rows
  cross-organism (32 MED4 + 26 MIT9313); `by_organism` shows both
  strains; `by_metric` carries `dm_true_count`/`dm_false_count` matching
  the precomputed counts.
- **Boolean — flag=False** — `metric_types=['vesicle_proteome_member'],
  flag=False` → 0 rows (positive-only storage); `by_metric.dm_false_count`
  echoes 0 — gives the LLM the "this is what the KG looks like" signal
  without an extra call.
- **Boolean — locus_tags scoping** — pick 3 known vesicle-proteome MED4
  genes (`PMM0090, PMM0097, PMM0107`) + 1 non-vesicle gene → 3 rows
  matching, the 4th absent (no `not_found` because the gene exists in
  KG, just not flagged).
- **Categorical** — `metric_types=['predicted_subcellular_localization'],
  categories=['Outer Membrane', 'Periplasmic']` → 14 rows; `by_metric`
  shows MED4 (8 rows: 5 OM + 3 PP) + MIT9313 (6 rows: 3 OM + 3 PP);
  `dm_by_category` carries the full precomputed histogram per DM.
- **Categorical — unknown-category raise** — `categories=['nonsense']` →
  `ValueError`; assert error message lists every observed
  `allowed_category` for context.
- **Kind-mismatch surfaces as `not_found_ids` (both tools)** — pass a
  numeric `derived_metric_id` to `genes_by_categorical_metric` (or
  vice-versa) → call returns successfully with `total_matching=0`,
  `not_found_ids=[<that_id>]`, empty `results`. Mirrors
  `genes_by_numeric_metric` behavior; no raise.
- **Categorical — `by_category` rename verified** — assert
  `response.by_category[0].keys() == {'category', 'count'}` (envelope
  level) **and** `response.by_metric[0].by_category[0].keys() ==
  {'category', 'count'}` (nested rename — confirms the post-Cypher
  walk in api/ orchestration step 9 ran correctly). Same assertion
  on `by_metric[0].dm_by_category`.

### Regression (`test_regression.py`)

Add to `TOOL_BUILDERS`:

```python
"genes_by_boolean_metric": build_genes_by_boolean_metric,
"genes_by_categorical_metric": build_genes_by_categorical_metric,
```

Regenerate baselines via `pytest tests/regression/ --force-regen -m kg`
once both tools are wired through.

### Eval cases (`cases.yaml`)

Boolean — happy path:

```yaml
- id: genes_by_boolean_metric_vesicle_proteome
  tool: genes_by_boolean_metric
  desc: Vesicle proteome members across MED4 and MIT9313
  params:
    metric_types: ['vesicle_proteome_member']
  expect:
    min_rows: 50
    columns: [locus_tag, gene_name, organism_name, derived_metric_id,
              value_kind, value]
```

Boolean — summary mode + scoping cross-check:

```yaml
- id: genes_by_boolean_metric_natl2a_periodic_summary
  tool: genes_by_boolean_metric
  desc: NATL2A periodic LD summary, no rows
  params:
    metric_types: ['periodic_in_coculture_LD']
    organism: 'NATL2A'
    summary: true
  expect:
    summary_keys:
      - by_metric
      - by_value
      - excluded_derived_metrics    # asserts envelope key presence even when []
      - warnings
```

Categorical — happy path + filter:

```yaml
- id: genes_by_categorical_metric_psortb_membrane
  tool: genes_by_categorical_metric
  desc: PSORTb outer-membrane / periplasmic vesicle proteins
  params:
    metric_types: ['predicted_subcellular_localization']
    categories: ['Outer Membrane', 'Periplasmic']
  expect:
    min_rows: 10
    columns: [locus_tag, organism_name, derived_metric_id, value]
```

Categorical — unknown-category error:

```yaml
- id: genes_by_categorical_metric_unknown_category_raises
  tool: genes_by_categorical_metric
  desc: Unknown category raises with allowed-set context
  params:
    metric_types: ['predicted_subcellular_localization']
    categories: ['Foo']
  expect:
    raises: ValueError
```

---

## About Content (per tool)

Two YAML inputs:
- `multiomics_explorer/inputs/tools/genes_by_boolean_metric.yaml`
- `multiomics_explorer/inputs/tools/genes_by_categorical_metric.yaml`

Each generates its `.md` via
`uv run python scripts/build_about_content.py {name}`.

### Required `mistakes` coverage (Tool 4 — boolean)

Surface at the top of `mistakes:` (first-bullet placement matters —
generator preserves list order; LLM reads top first):

1. **Positive-only storage in current KG.** Quote the slice-1 spec
   §"KG invariants" §4 — `flag=False` returns zero rows today because
   every materialized boolean edge is `r.value="true"`. Inspect
   `by_metric[*].dm_false_count` (always 0 today) before assuming a
   gene is "not flagged false". Mirror the wording from the
   `genes_by_numeric_metric.yaml` p-value mistake.
2. **Wrong-kind DM for the tool.** Numeric or categorical
   `derived_metric_id` raises with a `value_kind` mismatch. Use
   `list_derived_metrics(value_kind='boolean')` to pick IDs.
3. **Sparse columns echo from parent DM.** `rankable` / `has_p_value`
   are always `False` on every row from these DMs — kept for cross-tool
   shape consistency, not because the tool reads them.

### Required `mistakes` coverage (Tool 5 — categorical)

1. **Wrong-kind DM for the tool.** Same pattern as Tool 4.
2. **Unknown category raises.** `categories=['foo']` raises with the
   full union of `allowed_categories` from the selected DMs in the
   error message — pull that set from `list_derived_metrics` verbose
   output or read it from the error itself.
3. **`allowed_categories` ⊋ `dm_by_category`.** A category may be
   declared (in `allowed_categories`) but unobserved in any gene
   (absent from `dm_by_category`). Example: MED4 PSORTb declares
   `Extracellular` but no gene is classified that way. `by_metric`
   row's `allowed_categories` and `dm_by_category` both carry the
   per-DM context; the LLM doesn't need a follow-up call.

### Required `chaining` coverage (both tools)

Mirror `genes_by_numeric_metric.yaml`:

- *Discovery → drill-down:* `list_derived_metrics(value_kind='boolean')`
  → `genes_by_boolean_metric(metric_types=...)` → `gene_overview` /
  `genes_by_function`.
- *DE-filtered slice:* `differential_expression_by_gene(...)` → extract
  `locus_tags` → `genes_by_{boolean,categorical}_metric(metric_types=...,
  locus_tags=[...])` to ask "which of my DE hits are also flagged /
  classified?".
- *Cross-organism interpretation:* `metric_types=['vesicle_proteome_member']`
  with no `organism` filter → split via `by_organism` envelope.

### Worked example response YAML (boolean)

```yaml
- title: Vesicle proteome cross-organism
  call: genes_by_boolean_metric(metric_types=['vesicle_proteome_member'])
  response: |
    {"total_matching": 58, "total_derived_metrics": 2, "total_genes": 58,
     "by_organism": [{"organism_name": "Prochlorococcus MED4", "count": 32},
                     {"organism_name": "Prochlorococcus MIT9313", "count": 26}],
     "by_value": [{"value": "true", "count": 58}],
     "by_metric": [{"derived_metric_id": "...med4_vesicle...", "count": 32, "true_count": 32, "false_count": 0, "dm_total_gene_count": 32, "dm_true_count": 32, "dm_false_count": 0}],
     "excluded_derived_metrics": [], "warnings": [],
     "results": [{"locus_tag": "PMM0090", "value": "true", ...}]}
```

### Worked example response YAML (categorical)

```yaml
- title: PSORTb outer-membrane + periplasmic
  call: genes_by_categorical_metric(metric_types=['predicted_subcellular_localization'], categories=['Outer Membrane', 'Periplasmic'])
  response: |
    {"total_matching": 14, "total_derived_metrics": 2,
     "by_category": [{"category": "Outer Membrane", "count": 8}, {"category": "Periplasmic", "count": 6}],
     "by_metric": [{"derived_metric_id": "...med4...", "count": 8, "by_category": [{"category":"Outer Membrane","count":5},{"category":"Periplasmic","count":3}], "allowed_categories": ["Cytoplasmic","Cytoplasmic Membrane","Periplasmic","Outer Membrane","Extracellular","Unknown"], "dm_by_category": [{"category":"Cytoplasmic","count":11},{"category":"Cytoplasmic Membrane","count":6},{"category":"Outer Membrane","count":5},{"category":"Periplasmic","count":3},{"category":"Unknown","count":7}]}],
     "excluded_derived_metrics": [], "warnings": [],
     "results": [{"locus_tag": "PMM0097", "value": "Outer Membrane", ...}]}
```

---

## Documentation Updates

| File | What to update |
|---|---|
| `CLAUDE.md` | Two new rows in the MCP Tools table (after `genes_by_numeric_metric`): one for `genes_by_boolean_metric`, one for `genes_by_categorical_metric`. Each row mirrors the numeric row's structure: kind-specific filter highlight + cross-organism note + envelope shape callout (`by_value`/`by_category`, `by_metric` slice + dm_*) + diagnostics-on-mismatch behaviour. |
| `multiomics_explorer/skills/multiomics-kg-guide/references/analysis/derived_metrics.md` | Already covers slice-1 architecture; add a short note about boolean positive-only-storage gotcha + categorical `allowed_categories` ⊋ `dm_by_category` pattern, paralleling the rankable / has_p_value gate notes already in the doc. |

---

## Design decisions (resolved 2026-04-26)

1. **`flag: bool | None`, not `Literal['true', 'false'] | None`.** Matches
   the repo precedent (`list_derived_metrics.rankable / has_p_value`,
   `genes_by_numeric_metric.significant_only`,
   `differential_expression_by_gene.significant_only` — all `bool` on
   the tool surface despite Neo4j-string storage). JSON-schema primitive,
   no enum-string for the LLM to memorize. Coerce at the query-builder
   boundary: `params['flag_str'] = 'true' if flag else 'false'`. The
   BioCypher string-typed-bool quirk stays internal per the KG spec.
2. **`by_value` (Tool 4) emits only observed values — no zero-count
   padding.** `apoc.coll.frequencies` already behaves this way. Today
   every call yields `[{value: "true", count: N}]`. The `false`
   absence is conveyed by `by_metric[*].dm_false_count=0`, which the
   LLM reads alongside the slice tally without an extra envelope key.
3. **No shared Pydantic Result base class across the 3 drill-down
   tools.** Each tool keeps its own free-standing `Result` /
   `Response` models, mirroring `GenesByNumericMetric*`. FastMCP's
   per-tool schema generation stays self-contained. Slice-1 spec
   §"Why three drill-down tools" already accepts this duplication.
4. **Boolean and categorical diagnostics builders stay as separate
   functions** (not factored into a configurable helper). Three
   near-clones are easier to reason about and test than one parametric
   builder. Revisit only if a fourth `value_kind` ever lands.
