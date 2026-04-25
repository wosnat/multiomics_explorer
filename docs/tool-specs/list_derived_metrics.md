# Tool spec: list_derived_metrics
 
**Design spec:** [`docs/superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md`](../superpowers/specs/2026-04-23-derived-metric-mcp-tools-design.md) — shared slice-1 contract (KG invariants, gate logic, envelope conventions). This file adds tool-specific verified Cypher and Pydantic surface.

## Purpose

Entry-point discovery tool for `DerivedMetric` nodes — parallel to `list_clustering_analyses`. Answers "what non-DE evidence (scalar per-gene summaries) exists in the KG, for which organism / publication / experiment, and which value_kind?" and acts as pre-flight for the 4 downstream DM tools: the LLM inspects `rankable` / `has_p_value` / `value_kind` / `allowed_categories` / `compartment` here before selecting DMs for drill-downs.

## Out of Scope

- Member-gene enumeration (→ `gene_derived_metrics` / `genes_by_{kind}_metric`).
- Ortholog-group or cluster-level summaries of DM evidence (slice 2).
- Enrichment (TERM2GENE from DM flags/buckets — deferred, possibly outside MCP).

## Status / Prerequisites

- [x] KG changes landed (non-DE evidence extension — `multiomics_biocypher_kg/docs/kg-changes/non-de-evidence-extension.md`)
- [x] Scope reviewed with user
- [x] Result-size controls decided (large-set; `summary` + `limit` + `verbose`)
- [x] KG invariants verified live (2026-04-23)
- [ ] Build plan approved (then Phase 2)

## Use cases

- **Pre-flight for drill-downs.** Filter to `value_kind='numeric', rankable=True` before calling `genes_by_numeric_metric` with rankable-gated params.
- **Discovery.** "What periodicity / rhythm / darkness-survival evidence exists in this KG?" (Lucene on `name` + `field_description`).
- **Organism / publication scoping.** "What DMs does Waldbauer 2012 contribute? Biller 2018 on NATL2A vs MIT1002?"
- **Cross-tool chaining.** `list_derived_metrics` → `gene_derived_metrics(locus_tags=..., derived_metric_ids=...)`; or `list_derived_metrics` → `genes_by_{kind}_metric(derived_metric_ids=...)`.

## KG dependencies

Verified live 2026-04-23:

- `DerivedMetric` nodes (13 total). Properties queried: `id, name, metric_type, value_kind, rankable, has_p_value, unit, allowed_categories, field_description, organism_name, experiment_id, publication_doi, compartment, omics_type, treatment_type, background_factors, total_gene_count, growth_phases` (compact) + `treatment, light_condition, experimental_context, p_value_threshold` (verbose; last is gate-dependent).
- `derivedMetricFullText` index exists over `name, field_description`. Verified: `queryNodes('derivedMetricFullText', 'diel amplitude')` returns all 6 Waldbauer DMs with MED4-specific scores.
- DM has fully-denormalized parent fields (`organism_name`, `experiment_id`, `publication_doi`) — **no Experiment / Publication / OrganismTaxon joins needed** for scoping/filtering. Simpler than `list_clustering_analyses`.
- `dm.id` is unique per node (13/13).
- String-typed booleans: `dm.rankable` and `dm.has_p_value` stored as `"true"` / `"false"`; compare with `= 'true'`.
- `dm.allowed_categories` is `null` on non-categorical DMs (not `[]`) — caller-side nullability.
- `dm.growth_phases` is `[]` on Waldbauer numeric DMs (empty), `["darkness"]` on Biller DMs. `apoc.coll.flatten(collect(coalesce(...)))` tolerant.

## Tool Signature

```python
@mcp.tool(
    tags={"derived-metrics", "discovery", "catalog"},
    annotations={"readOnlyHint": True},
)
async def list_derived_metrics(
    ctx: Context,
    search_text: Annotated[str | None, Field(
        description="Full-text search over DM name and field_description. "
                    "Examples: 'diel amplitude', 'darkness survival', 'peak time'.",
    )] = None,
    organism: Annotated[str | None, Field(
        description="Organism to filter by. Accepts short strain code ('MED4', "
                    "'NATL2A', 'MIT1002') or full name ('Prochlorococcus MED4'). "
                    "Case-insensitive substring match.",
    )] = None,
    metric_types: Annotated[list[str] | None, Field(
        description="Filter by metric_type tags (e.g. 'diel_amplitude_protein_log2', "
                    "'periodic_in_coculture_LD'). The same metric_type may appear "
                    "across organisms / publications — use derived_metric_ids to pin "
                    "one specific DM when that matters.",
    )] = None,
    value_kind: Annotated[Literal["numeric", "boolean", "categorical"] | None, Field(
        description="Filter by value kind. Determines which drill-down tool applies: "
                    "'numeric' → genes_by_numeric_metric, 'boolean' → "
                    "genes_by_boolean_metric, 'categorical' → genes_by_categorical_metric.",
    )] = None,
    compartment: Annotated[str | None, Field(
        description="Sample compartment / scope. Current values: 'whole_cell', "
                    "'vesicle', 'exoproteome', 'spent_medium', 'lysate'.",
    )] = None,
    omics_type: Annotated[str | None, Field(
        description="Omics assay type. Examples: 'RNASEQ', 'PROTEOME', "
                    "'PAIRED_RNASEQ_PROTEOME'. Case-insensitive.",
    )] = None,
    treatment_type: Annotated[list[str] | None, Field(
        description="Treatment type(s) to match. Returns DMs whose treatment_type "
                    "list overlaps ANY of the given values (e.g. 'diel', 'darkness', "
                    "'nitrogen_starvation'). Case-insensitive.",
    )] = None,
    background_factors: Annotated[list[str] | None, Field(
        description="Background experimental factor(s) to match "
                    "(e.g. 'axenic', 'coculture', 'diel'). Returns DMs overlapping "
                    "ANY given value. Case-insensitive.",
    )] = None,
    growth_phases: Annotated[list[str] | None, Field(
        description="Growth phase(s) to match (e.g. 'darkness', 'exponential'). "
                    "Case-insensitive.",
    )] = None,
    publication_doi: Annotated[list[str] | None, Field(
        description="Filter by one or more publication DOIs "
                    "(e.g. '10.1128/mSystems.00040-18'). Exact match.",
    )] = None,
    experiment_ids: Annotated[list[str] | None, Field(
        description="Filter by one or more Experiment node ids.",
    )] = None,
    derived_metric_ids: Annotated[list[str] | None, Field(
        description="Look up specific DMs by their unique id (matches "
                    "`derived_metric_id` on each result). Use to pin one DM when "
                    "the same metric_type appears across publications or organisms.",
    )] = None,
    rankable: Annotated[bool | None, Field(
        description="Filter to DMs that support rank / percentile / bucket analysis. "
                    "Set to True before calling genes_by_numeric_metric with `bucket`, "
                    "`min_percentile`, `max_percentile`, or `max_rank` — those filters "
                    "require rankable=True on every selected DM.",
    )] = None,
    has_p_value: Annotated[bool | None, Field(
        description="Filter to DMs that carry statistical p-values. "
                    "Set to True before using `significant_only` or `max_adjusted_p_value` "
                    "on drill-downs. No DM in the current KG carries p-values, so "
                    "has_p_value=True returns zero rows today — kept available because "
                    "the drill-down p-value filters raise when no selected DM supports them.",
    )] = None,
    summary: Annotated[bool, Field(
        description="Return summary fields only (counts and breakdowns, no "
                    "individual results). Use for quick orientation.",
    )] = False,
    verbose: Annotated[bool, Field(
        description="Include detailed text fields per result: treatment, "
                    "light_condition, experimental_context, p_value_threshold.",
    )] = False,
    limit: Annotated[int, Field(
        description="Max results to return. Paginate with offset.", ge=0,
    )] = 20,
    offset: Annotated[int, Field(
        description="Pagination offset (starting row, 0-indexed).", ge=0,
    )] = 0,
) -> ListDerivedMetricsResponse:
    """Discover DerivedMetric (DM) nodes — column-level scalar summaries of
    gene behavior (e.g. rhythmicity flags, diel amplitudes, darkness-survival
    class) that sit alongside DE and gene clusters as non-DE evidence.

    Call this first, before `gene_derived_metrics` or the three
    `genes_by_{kind}_metric` drill-downs. Inspect `value_kind` (routes you
    to the right drill-down), `rankable` (gates bucket / percentile / rank
    filters), `has_p_value` (gates significance filters), and
    `allowed_categories` (for categorical DMs) here — drill-down tools
    will raise if you pass filters that the selected DM set doesn't support.
    """
```

## Result-size controls

Large result-set pattern — `summary` + `limit` + `verbose`. Default `limit=20` (enough to cover the whole KG today; paginate via `offset` if the set grows).

### Summary envelope

| Field | Type | Description |
|---|---|---|
| `total_entries` | int | Total DerivedMetric nodes in KG (unfiltered baseline). |
| `total_matching` | int | DMs matching all filters. |
| `by_organism` | list[{item, count}] | APOC frequencies on `dm.organism_name`. |
| `by_value_kind` | list[{item, count}] | APOC frequencies on `dm.value_kind`. |
| `by_metric_type` | list[{item, count}] | APOC frequencies on `dm.metric_type`. |
| `by_compartment` | list[{item, count}] | APOC frequencies on `dm.compartment`. |
| `by_omics_type` | list[{item, count}] | APOC frequencies on `dm.omics_type`. |
| `by_treatment_type` | list[{item, count}] | APOC frequencies on flattened `dm.treatment_type`. |
| `by_background_factors` | list[{item, count}] | APOC frequencies on flattened `dm.background_factors`. |
| `by_growth_phase` | list[{item, count}] | APOC frequencies on flattened `dm.growth_phases`. |
| `score_max` | float \| None | Max Lucene score; only when `search_text` provided. |
| `score_median` | float \| None | Median Lucene score; only when `search_text` provided. |
| `returned` | int | `len(results)`. |
| `truncated` | bool | `total_matching > returned`. |
| `offset` | int | Echo of input. |

### Detail (per-row compact)

`derived_metric_id, name, metric_type, value_kind, rankable, has_p_value, unit, allowed_categories, field_description, organism_name, experiment_id, publication_doi, compartment, omics_type, treatment_type, background_factors, total_gene_count, growth_phases` — plus `score` when `search_text` provided.

### Verbose adds

`treatment, light_condition, experimental_context` always. **`p_value_threshold` is declared in the Pydantic model (forward-compat) but not in the current Cypher RETURN clause** — the property does not exist on any `DerivedMetric` in today's KG, and querying it produces a CyVer schema warning. The field defaults to `None` in `ListDerivedMetricsResult`; add the CASE-gated RETURN column (`CASE WHEN dm.has_p_value = 'true' THEN dm.p_value_threshold ELSE null END AS p_value_threshold`) when a DM with `has_p_value='true'` lands in the KG.

**Sort key:** `score DESC` (if search), then `dm.organism_name ASC, dm.value_kind ASC, dm.id ASC`.

## Special handling

- **Lucene retry.** If full-text query parse-errors, retry with `_LUCENE_SPECIAL` escaping (existing pattern, shared with other fulltext tools).
- **String-boolean coercion.** `rankable` / `has_p_value` params are `bool | None` at API boundary; builder converts to `"true"` / `"false"` strings before interpolation.
- **Organism CONTAINS filter.** Mirror `_list_experiments_where` (space-split, lowercased, all-words CONTAINS). This is more tolerant than `_clustering_analysis_where`'s exact-equality; aligns with what callers naturally pass (`"MED4"` not `"Prochlorococcus MED4"`).

---

## Query Builder

**File:** `multiomics_explorer/kg/queries_lib.py`

### `_list_derived_metrics_where()` (shared helper)

Builds conditions + params dict from DM-level filters only (the fields that live on `dm.*` directly). No edge traversal needed — DM is fully denormalized.

```python
def _list_derived_metrics_where(
    *,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: str | None = None,
    compartment: str | None = None,
    omics_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    rankable: bool | None = None,
    has_p_value: bool | None = None,
) -> tuple[list[str], dict]:
    """Shared WHERE builder for build_list_derived_metrics{,_summary}."""
```

WHERE snippets:

```
organism            → (ALL(word IN split(toLower($organism), ' ')
                            WHERE toLower(dm.organism_name) CONTAINS word))
metric_types        → dm.metric_type IN $metric_types
value_kind          → dm.value_kind = $value_kind
compartment         → dm.compartment = $compartment
omics_type          → toUpper(dm.omics_type) = $omics_type_upper
treatment_type      → ANY(t IN coalesce(dm.treatment_type, [])
                           WHERE toLower(t) IN $treatment_types_lower)
background_factors  → ANY(bf IN coalesce(dm.background_factors, [])
                           WHERE toLower(bf) IN $bfs_lower)
growth_phases       → ANY(gp IN coalesce(dm.growth_phases, [])
                           WHERE toLower(gp) IN $gps_lower)
publication_doi     → dm.publication_doi IN $publication_doi
experiment_ids      → dm.experiment_id IN $experiment_ids
derived_metric_ids  → dm.id IN $derived_metric_ids
rankable            → dm.rankable = $rankable_str  (str '"true"'/'"false"')
has_p_value         → dm.has_p_value = $has_p_value_str
```

### `build_list_derived_metrics_summary`

Verified against live KG 2026-04-23 (n=4 rankable numeric DMs for MED4; `total_matching=4`, `total_entries=13`):

```cypher
CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)
YIELD node AS dm, score                -- only when search_text provided; else: MATCH (dm:DerivedMetric)
WHERE <conditions from _list_derived_metrics_where>
WITH collect(dm.organism_name) AS organisms,
     collect(dm.value_kind) AS value_kinds,
     collect(dm.metric_type) AS metric_types,
     collect(dm.compartment) AS compartments,
     collect(dm.omics_type) AS omics_types,
     apoc.coll.flatten(collect(coalesce(dm.treatment_type, []))) AS treatment_types,
     apoc.coll.flatten(collect(coalesce(dm.background_factors, []))) AS background_factors_flat,
     apoc.coll.flatten(collect(coalesce(dm.growth_phases, []))) AS growth_phases_flat,
     count(dm) AS total_matching
     -- when search_text: + max(score) AS score_max, percentileDisc(score, 0.5) AS score_median
CALL { MATCH (all_dm:DerivedMetric) RETURN count(all_dm) AS total_entries }
RETURN total_entries, total_matching,
       apoc.coll.frequencies(organisms) AS by_organism,
       apoc.coll.frequencies(value_kinds) AS by_value_kind,
       apoc.coll.frequencies(metric_types) AS by_metric_type,
       apoc.coll.frequencies(compartments) AS by_compartment,
       apoc.coll.frequencies(omics_types) AS by_omics_type,
       apoc.coll.frequencies(treatment_types) AS by_treatment_type,
       apoc.coll.frequencies(background_factors_flat) AS by_background_factors,
       apoc.coll.frequencies(growth_phases_flat) AS by_growth_phase
       -- when search_text: + score_max, score_median
```

### `build_list_derived_metrics`

Verified against live KG 2026-04-23 (returned 4 rankable numeric MED4 DMs; all fields populated):

```cypher
CALL db.index.fulltext.queryNodes('derivedMetricFullText', $search_text)
YIELD node AS dm, score                -- only when search_text provided; else: MATCH (dm:DerivedMetric)
WHERE <conditions>
RETURN dm.id AS derived_metric_id,
       dm.name AS name,
       dm.metric_type AS metric_type,
       dm.value_kind AS value_kind,
       dm.rankable AS rankable,
       dm.has_p_value AS has_p_value,
       dm.unit AS unit,
       CASE WHEN dm.value_kind = 'categorical'
            THEN dm.allowed_categories ELSE null END AS allowed_categories,
       dm.field_description AS field_description,
       dm.organism_name AS organism_name,
       dm.experiment_id AS experiment_id,
       dm.publication_doi AS publication_doi,
       dm.compartment AS compartment,
       dm.omics_type AS omics_type,
       coalesce(dm.treatment_type, []) AS treatment_type,
       coalesce(dm.background_factors, []) AS background_factors,
       dm.total_gene_count AS total_gene_count,
       coalesce(dm.growth_phases, []) AS growth_phases
       -- when search_text: + score
       -- when verbose: + dm.treatment AS treatment,
       --                + dm.light_condition AS light_condition,
       --                + dm.experimental_context AS experimental_context
       -- NOTE: p_value_threshold is NOT in the Cypher RETURN today — the property
       --       does not exist on any DerivedMetric in the current KG, and running
       --       the CASE-gated form trips a CyVer schema warning. The Pydantic
       --       field stays as-is (default None, forward-compat). Re-add the
       --       CASE-gated RETURN column — `CASE WHEN dm.has_p_value = 'true'
       --       THEN dm.p_value_threshold ELSE null END AS p_value_threshold` — when
       --       a DM lands with has_p_value='true' and the property materialized.
ORDER BY <score DESC if search_text,> dm.organism_name ASC, dm.value_kind ASC, dm.id ASC
SKIP $offset
LIMIT $limit
```

**Variable scoping:** no UNWIND/DISTINCT chains; flat aggregation. No scoping traps.

**Design notes:**
- Denormalization removes the need for Experiment/Publication/OrganismTaxon joins — simpler and faster than the clustering analog.
- **Defensive CASE-gating** per design-spec canonical pattern. This tool returns only DM-node properties (no edge props), so only two columns are subject to gating: `allowed_categories` (CASE-gated on `value_kind='categorical'` in the current Cypher), and `p_value_threshold` (verbose; gated on `has_p_value='true'` — *added to the Cypher RETURN only when a DM carries the property*; see §Verbose adds). The other gate-dependent columns (`rank_by_metric`, `metric_percentile`, `metric_bucket`, `adjusted_p_value`, `significant`) live on edges and surface only in `gene_derived_metrics` / `genes_by_numeric_metric` — those tools apply the same pattern there.
- `apoc.coll.flatten(collect(coalesce(..., [])))` correctly handles Waldbauer's empty `growth_phases` (verified).

---

## API Function

**File:** `multiomics_explorer/api/functions.py`

```python
def list_derived_metrics(
    search_text: str | None = None,
    organism: str | None = None,
    metric_types: list[str] | None = None,
    value_kind: Literal["numeric", "boolean", "categorical"] | None = None,
    compartment: str | None = None,
    omics_type: str | None = None,
    treatment_type: list[str] | None = None,
    background_factors: list[str] | None = None,
    growth_phases: list[str] | None = None,
    publication_doi: list[str] | None = None,
    experiment_ids: list[str] | None = None,
    derived_metric_ids: list[str] | None = None,
    rankable: bool | None = None,
    has_p_value: bool | None = None,
    summary: bool = False,
    verbose: bool = False,
    limit: int | None = None,
    offset: int = 0,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List DerivedMetric nodes with summary + detail modes.

    Returns dict with keys:
      total_entries, total_matching, by_organism, by_value_kind, by_metric_type,
      by_compartment, by_omics_type, by_treatment_type, by_background_factors,
      by_growth_phase, score_max (opt), score_median (opt),
      returned, offset, truncated, results.
    Per-result compact: derived_metric_id, name, metric_type, value_kind, rankable,
      has_p_value, unit, allowed_categories, field_description, organism_name,
      experiment_id, publication_doi, compartment, omics_type, treatment_type,
      background_factors, total_gene_count, growth_phases (+ score when searching).
    Verbose adds: treatment, light_condition, experimental_context, p_value_threshold.
    """
```

Implementation notes:
- `search_text == ""` → `ValueError`.
- Lucene retry path via `_LUCENE_SPECIAL` on `neo4j.exceptions.ClientError` with fulltext parse messages (mirror existing fulltext tools).
- `summary=True` → set `limit=0`; detail query skipped; `results=[]`.
- 2-query pattern: summary always runs; detail skipped when `limit == 0`.
- Wire exports: `api/__init__.py` + `multiomics_explorer/__init__.py` `__all__`.

---

## MCP Wrapper

**File:** `multiomics_explorer/mcp_server/tools.py`

Two Pydantic models:

```python
class ListDerivedMetricsResult(BaseModel):
    derived_metric_id: str = Field(
        description="Unique id for this DerivedMetric. Pass to `derived_metric_ids` "
                    "on drill-down tools (gene_derived_metrics, genes_by_*_metric) "
                    "to select this exact DM.")
    name: str = Field(
        description="Human-readable DM name "
                    "(e.g. 'Transcript:protein amplitude ratio').")
    metric_type: str = Field(
        description="Category tag identifying what is measured "
                    "(e.g. 'diel_amplitude_protein_log2'). The same metric_type "
                    "may appear across organisms / publications — pair with "
                    "organism or publication_doi when that matters, or use "
                    "derived_metric_id to pin one specific DM.")
    value_kind: Literal["numeric", "boolean", "categorical"] = Field(
        description="Routes to the correct drill-down tool: 'numeric' → "
                    "genes_by_numeric_metric, 'boolean' → genes_by_boolean_metric, "
                    "'categorical' → genes_by_categorical_metric.")
    rankable: bool = Field(
        description="True if this DM supports rank / percentile / bucket analysis "
                    "on genes_by_numeric_metric. When False, the `bucket`, "
                    "`min_percentile`, `max_percentile`, and `max_rank` filters "
                    "on that drill-down do not apply — passing them with only "
                    "non-rankable DMs raises; mixing rankable + non-rankable drops "
                    "the non-rankable ones and lists them in the drill-down's "
                    "`excluded_derived_metrics`.")
    has_p_value: bool = Field(
        description="True if this DM carries statistical p-values, enabling "
                    "`significant_only` and `max_adjusted_p_value` on drill-downs. "
                    "No DM in the current KG has p-values.")
    unit: str = Field(
        description="Measurement unit for numeric DMs (e.g. 'hours', 'log2'). "
                    "Empty string for boolean and categorical DMs.")
    allowed_categories: list[str] | None = Field(
        description="Valid category strings for this DM. Non-null only when "
                    "value_kind='categorical'; pass a subset as `categories` to "
                    "genes_by_categorical_metric.")
    field_description: str = Field(
        description="Detailed explanation of what this DM measures and how to "
                    "interpret its values.")
    organism_name: str = Field(
        description="Full organism name (e.g. 'Prochlorococcus MED4', "
                    "'Alteromonas macleodii MIT1002').")
    experiment_id: str = Field(
        description="Parent Experiment node id. Look up context via list_experiments.")
    publication_doi: str = Field(
        description="Parent publication DOI (e.g. '10.1128/mSystems.00040-18').")
    compartment: str = Field(
        description="Sample compartment or scope "
                    "(e.g. 'whole_cell', 'vesicle', 'exoproteome', "
                    "'spent_medium', 'lysate').")
    omics_type: str = Field(
        description="Omics assay type (e.g. 'RNASEQ', 'PROTEOME', "
                    "'PAIRED_RNASEQ_PROTEOME').")
    treatment_type: list[str] = Field(
        description="Treatment type(s) (e.g. ['diel'], ['darkness']).")
    background_factors: list[str] = Field(
        description="Background experimental factors "
                    "(e.g. ['axenic'], ['coculture', 'diel']). May be empty.")
    total_gene_count: int = Field(
        description="Number of distinct genes with at least one measurement "
                    "for this DM.")
    growth_phases: list[str] = Field(
        description="Growth phase(s) this DM pertains to "
                    "(e.g. ['darkness']). May be empty.")
    score: float | None = Field(
        default=None,
        description="Full-text relevance score; present only when search_text "
                    "was provided.")
    # verbose-only:
    treatment: str | None = Field(
        default=None,
        description="Treatment description in plain language "
                    "(verbose mode only).")
    light_condition: str | None = Field(
        default=None,
        description="Light regime (e.g. 'light:dark cycle'; verbose mode only).")
    experimental_context: str | None = Field(
        default=None,
        description="Longer description of the experimental setup that produced "
                    "this DM (verbose mode only).")
    p_value_threshold: float | None = Field(
        default=None,
        description="Threshold that defines statistical significance for this DM. "
                    "Non-null only when has_p_value=True (verbose mode only; "
                    "no DM in current KG has a threshold).")


class ListDerivedMetricsResponse(BaseModel):
    total_entries: int = Field(
        description="Total DMs in the KG (unfiltered baseline).")
    total_matching: int = Field(
        description="DMs matching all applied filters.")
    by_organism: list[dict] = Field(
        description="Counts per organism across matching DMs "
                    "(list of {organism_name, count}, sorted by count desc).")
    by_value_kind: list[dict] = Field(
        description="Counts per value_kind (list of {value_kind, count}).")
    by_metric_type: list[dict] = Field(
        description="Counts per metric_type (list of {metric_type, count}).")
    by_compartment: list[dict] = Field(
        description="Counts per compartment (list of {compartment, count}).")
    by_omics_type: list[dict] = Field(
        description="Counts per omics_type (list of {omics_type, count}).")
    by_treatment_type: list[dict] = Field(
        description="Counts per treatment_type across matching DMs "
                    "(list of {treatment_type, count}; DM treatment_type lists "
                    "are flattened before counting).")
    by_background_factors: list[dict] = Field(
        description="Counts per background_factor (list of "
                    "{background_factor, count}; flattened).")
    by_growth_phase: list[dict] = Field(
        description="Counts per growth_phase (list of {growth_phase, count}; "
                    "flattened).")
    score_max: float | None = Field(
        default=None,
        description="Max relevance score; present only when search_text "
                    "was provided.")
    score_median: float | None = Field(
        default=None,
        description="Median relevance score; present only when search_text "
                    "was provided.")
    returned: int = Field(
        description="Number of rows in results.")
    offset: int = Field(
        description="Pagination offset used for this call.")
    truncated: bool = Field(
        description="True when total_matching > returned (more rows available "
                    "— paginate with offset).")
    results: list[ListDerivedMetricsResult] = Field(
        description="Matching DerivedMetric entries. Empty when summary=True.")
```

Wrapper body: call `api.list_derived_metrics`, validate with `ListDerivedMetricsResponse(**data)`, return. `ToolError` on `ValueError`.

---

## Tests

### Unit: `tests/unit/test_query_builders.py::TestBuildListDerivedMetrics` + `TestBuildListDerivedMetricsSummary`

- `test_no_filters` — bare `MATCH (dm:DerivedMetric)`, no WHERE.
- `test_search_text` — fulltext CALL, `score` in RETURN, `ORDER BY score DESC, ...`.
- `test_organism_contains` — single-word + multi-word; lowercased split; both present in WHERE.
- `test_metric_types_list` — `dm.metric_type IN $metric_types` + param.
- `test_value_kind` — `dm.value_kind = $value_kind`.
- `test_compartment`, `test_omics_type`, `test_treatment_type_any`, `test_background_factors_null_safe`, `test_growth_phases_lowered`.
- `test_publication_doi_list`, `test_experiment_ids_list`, `test_derived_metric_ids_list`.
- `test_rankable_true_coerces_to_string` — `dm.rankable = 'true'` (param is string not bool).
- `test_has_p_value_false_coerces_to_string`.
- `test_combined_filters` — AND-joined, stable ordering of conditions.
- `test_returns_expected_columns` — compact column list.
- `test_verbose_adds_columns` — verbose path adds treatment/light_condition/experimental_context to the Cypher RETURN (p_value_threshold is declared on the Pydantic model but intentionally absent from the current Cypher — see §Verbose adds for the reinstatement rule).
- `test_allowed_categories_case_gated` — RETURN clause wraps allowed_categories in `CASE WHEN dm.value_kind = 'categorical' ...`.
- `test_limit_offset` — SKIP/LIMIT clauses + params.
- `test_order_by` — `dm.organism_name, dm.value_kind, dm.id` fallback; `score DESC` prefix when search.
- Summary class:
  - `test_shares_where_clause` — same conditions/params construction.
  - `test_apoc_frequencies_cols` — all 9 breakdowns in RETURN.
  - `test_search_adds_score_stats` — `score_max`, `score_median`.

### Unit: `tests/unit/test_api_functions.py::TestListDerivedMetrics`

- Mocked `GraphConnection`; assert:
  - envelope shape (keys present, empty results when `summary=True`),
  - `summary=True` forces `limit=0` (detail query NOT called),
  - Lucene retry path on parse error,
  - `search_text=""` → `ValueError`,
  - `rankable=True` / `rankable=False` / `None` path,
  - `truncated=True` when `total_matching > len(results)`,
  - `returned == len(results)`, `offset` echoed.

### Unit: `tests/unit/test_tool_wrappers.py::TestListDerivedMetricsWrapper` + update `EXPECTED_TOOLS`

- `test_returns_response_envelope` — shape-validates `ListDerivedMetricsResponse`.
- `test_empty_results` — `limit=0`.
- `test_rankable_bool_param` — tool accepts Python `True`/`False`, api receives same.
- `test_truncation_metadata`.

### Integration (KG, `@pytest.mark.kg`): `tests/integration/test_mcp_tools.py` → `TestListDerivedMetrics`

Baselines pinned to 2026-04-23 KG state; update when new DM papers land:

- `no_filters` → `total_entries == 13`, `total_matching == 13`.
- `value_kind='numeric'` → 6 rows; all have `compartment=='whole_cell'`.
- `value_kind='boolean'` → 6 rows; 4 on NATL2A, 2 on MIT1002.
- `value_kind='categorical'` → 1 row; `allowed_categories` non-null.
- `rankable=True` → 4 numeric rows (all Waldbauer rankable).
- `rankable=False` → 2 numeric rows (`peak_time_protein_h`, `peak_time_transcript_h`). Sanity-checks the `bool → "false"` string coercion path.
- `has_p_value=True` → **0 rows** (intentional, current KG state).
- `organism='MED4'` (short form) → 6 rows (all Waldbauer).
- `organism='NATL2A'` → 5 rows (Biller NATL2A DMs).
- `organism='MIT1002'` → 2 rows (Biller Alteromonas DMs).
- `search_text='diel amplitude'` → top hits are `diel_amplitude_*` DMs with highest scores.
- `publication_doi=['10.1128/mSystems.00040-18']` → 7 rows.
- `derived_metric_ids` direct lookup → 1 row per ID.
- `summary=True` → `results == []`, all `by_*` fields populated.
- Verbose adds `treatment, light_condition, experimental_context`, and `p_value_threshold == None` (since no DM has `has_p_value=true`).
- Envelope keys always present (zero-row filter case): all `by_*` are `[]`, not missing.

### Regression: `tests/evals/cases.yaml` + `TOOL_BUILDERS`

Add `"list_derived_metrics": build_list_derived_metrics` to `TOOL_BUILDERS`. Regenerate baselines once.

### About-content: `tests/unit/test_about_content.py` + `tests/integration/test_about_examples.py`

Pydantic ↔ YAML consistency + live-KG example execution.

---

## About Content

**File:** `multiomics_explorer/inputs/tools/list_derived_metrics.yaml`

Per the design spec §Documentation §"Required `mistakes` + `chaining` coverage":

- `mistakes:` — **first bullet** must reinforce pre-flight role: "Call this before drill-downs; inspect `rankable` / `has_p_value` / `value_kind` / `allowed_categories` to confirm downstream filters will apply. Otherwise drill-down tools hard-fail (intentionally)."
- `chaining:` entries:
  - `"list_derived_metrics → gene_derived_metrics(locus_tags, derived_metric_ids)"`
  - `"list_derived_metrics(value_kind='numeric', rankable=True) → genes_by_numeric_metric(derived_metric_ids, bucket=[...])"`
  - `"list_derived_metrics(value_kind='boolean') → genes_by_boolean_metric(derived_metric_ids, flag=True)"`
  - `"list_derived_metrics(value_kind='categorical') → genes_by_categorical_metric(derived_metric_ids, categories=[...])"`
- `examples:` — at minimum:
  - `list_derived_metrics(summary=True)` — orient.
  - `list_derived_metrics(search_text='diel amplitude')` — discovery via fulltext.
  - `list_derived_metrics(value_kind='numeric', rankable=True)` — pre-flight for numeric drill-down.
  - `list_derived_metrics(organism='NATL2A')` — per-organism inventory.
  - `list_derived_metrics(publication_doi=['10.1128/mSystems.00040-18'])` — per-paper inventory.
- `verbose_fields:` — `treatment, light_condition, experimental_context, p_value_threshold`.

Pydantic docstring first line (per design spec §S2 preamble hoist) echoes the pre-flight role: "Entry point for DerivedMetric workflows — inspect `rankable` / `has_p_value` / `value_kind` / `allowed_categories` before calling drill-down tools, which hard-fail on gate mismatches."

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `_list_derived_metrics_where()`, `build_list_derived_metrics()`, `build_list_derived_metrics_summary()` |
| 2 | Unit test | `tests/unit/test_query_builders.py` | `TestBuildListDerivedMetrics`, `TestBuildListDerivedMetricsSummary` |
| 3 | API function | `api/functions.py` | `list_derived_metrics()` |
| 4 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add to imports + `__all__` |
| 5 | Unit test | `tests/unit/test_api_functions.py` | `TestListDerivedMetrics` |
| 6 | MCP wrapper | `mcp_server/tools.py` | `ListDerivedMetricsResult`, `ListDerivedMetricsResponse`, `list_derived_metrics` |
| 7 | Unit test | `tests/unit/test_tool_wrappers.py` | `TestListDerivedMetricsWrapper` + `EXPECTED_TOOLS` |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | `TestListDerivedMetrics` (`@pytest.mark.kg`) |
| 9 | Regression | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS`, regenerate baselines |
| 10 | Eval cases | `tests/evals/cases.yaml` | Add cases |
| 11 | About content | `multiomics_explorer/inputs/tools/list_derived_metrics.yaml` | Author YAML |
| 12 | About markdown | (generated) | Run `scripts/build_about_content.py list_derived_metrics` |
| 13 | CLAUDE.md | `CLAUDE.md` | Add row to MCP Tools table |
| 14 | Code review | — | Per `.claude/skills/code-review/SKILL.md` |

Detailed bite-sized task list lives in `docs/superpowers/plans/2026-04-23-list-derived-metrics.md` (writing-plans format).
