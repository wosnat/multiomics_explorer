# Growth Phase Integration — Design

**Date:** 2026-04-17
**Status:** Design
**Scope:** Surface `growth_phase` (edge) and `growth_phases` (node) across all relevant explorer tools — return columns, filters, summaries, and a new `list_filter_values` type.

## Background

The KG build repo is adding `growth_phase` (string) on `Changes_expression_of` edges and `growth_phases` (string[]) on `Experiment` nodes (see `2026-04-12-timepoint-growth-phase-backfill-design.md` in `multiomics_biocypher_kg`). This property captures the physiological state of the culture at the time of sampling — `exponential`, `nutrient_limited`, `acclimated_steady_state`, `diel`, etc. (11-value enum plus `other:<slug>` escape hatch).

**Key semantic:** `growth_phase` is a **timepoint-level property of the experimental condition**, not a gene-level property. It describes the physiological state of the entire culture at the moment RNA/protein was harvested. Every gene measured at a given timepoint shares the same `growth_phase`. In the KG, it lives on the `Changes_expression_of` edge (one value per experiment×timepoint), not on the Gene node. When aggregated to the Experiment level, `growth_phases` is the set of distinct phases across all timepoints in that experiment (e.g., a nitrogen starvation time-course may span `["exponential", "nutrient_limited"]`).

The explorer currently has no code referencing `growth_phase`. The properties exist in `schema_baseline.yaml` and appear in regression fixtures (passively returned via property maps), but are not explicitly surfaced, filterable, or summarized.

## Goals

1. Return `growth_phase` / `growth_phases` in every tool that returns experiment or expression data.
2. Filter by `growth_phases` at the experiment level (browsing tools) and by `growth_phase` at the edge level (DE tools).
3. Add `by_growth_phase` summary breakdowns where appropriate.
4. Add `growth_phase` as a `list_filter_values` filter type for value discovery.

## Non-goals

- No `growth_phase` on `gene_response_profile` — that tool aggregates across all timepoints per gene×group_key; a mashed-together list of phases at that level is not informative.
- No changes to the KG build pipeline — those are handled in the biocypher repo.
- No new ontology or hierarchy for growth phases.

## KG-side prerequisites

New precomputed fields needed in the KG (via `post-import.cypher` in `multiomics_biocypher_kg`):

| Node | Field | Type | Derivation |
|---|---|---|---|
| `Experiment` | `growth_phases` | `str[]` | **Already exists.** Distinct `r.growth_phase` from child edges. |
| `Experiment` | `time_point_growth_phases` | `str[]` | **New.** Parallel array aligned with `time_point_labels`, `time_point_orders`, `time_point_hours`, etc. One entry per timepoint. Built alongside existing `time_point_*` arrays in post-import. |
| `Publication` | `growth_phases` | `str[]` | **New.** Distinct values from child experiments: `collect(DISTINCT x) FROM flatten(e.growth_phases)`. Follows `treatment_types`, `background_factors`, `omics_types` pattern. |
| `OrganismTaxon` | `growth_phases` | `str[]` | **New.** Same aggregation pattern as Publication. |
| `ClusteringAnalysis` | `growth_phases` | `str[]` | **New.** Distinct values from linked experiments via `ExperimentHasClusteringAnalysis`. Follows existing `background_factors`, `treatment_type` pattern on ClusteringAnalysis. |

Post-import Cypher (illustrative):

```cypher
// Experiment.time_point_growth_phases — parallel array
// Built alongside existing time_point_* arrays in the adapter or post-import.
// Each timepoint's growth_phase comes from the edge: r.growth_phase
// grouped by r.time_point_order to maintain alignment.

// Publication.growth_phases
MATCH (p:Publication)-[:Has_experiment]->(e:Experiment)
WITH p, apoc.coll.toSet(apoc.coll.flatten(collect(coalesce(e.growth_phases, [])))) AS phases
SET p.growth_phases = phases;

// OrganismTaxon.growth_phases
MATCH (o:OrganismTaxon)<-[:Gene_belongs_to_organism]-(:Gene)<-[:Changes_expression_of]-(e:Experiment)
WITH o, apoc.coll.toSet(apoc.coll.flatten(collect(coalesce(e.growth_phases, [])))) AS phases
SET o.growth_phases = phases;

// ClusteringAnalysis.growth_phases
MATCH (e:Experiment)-[:ExperimentHasClusteringAnalysis]->(ca:ClusteringAnalysis)
WITH ca, apoc.coll.toSet(apoc.coll.flatten(collect(coalesce(e.growth_phases, [])))) AS phases
SET ca.growth_phases = phases;
```

## Design

### Filter patterns

Two filter patterns, matching the approved approach:

**Experiment-level** (browsing tools): Filter on the `growth_phases` array property on Experiment/Publication/ClusteringAnalysis nodes. Same ANY-match semantics as `background_factors`:

```cypher
ANY(gp IN coalesce(e.growth_phases, []) WHERE toLower(gp) IN $growth_phases)
```

Case-insensitive. Matches if the experiment has *at least one* timepoint in the requested phase. A nitrogen starvation time-course with both `exponential` and `nutrient_limited` timepoints shows up for either filter value.

**Edge-level** (DE tools): Filter on `r.growth_phase` directly in the WHERE clause alongside existing edge filters (`direction`, `significant_only`):

```cypher
toLower(r.growth_phase) IN $growth_phases
```

This isolates specific-phase rows from multi-phase experiments — more precise than experiment-level filtering for DE results.

### Per-tool changes

#### 1. `list_experiments`

**Query builder** (`_list_experiments_where`): Add `growth_phases: list[str] | None` parameter. Cypher condition:
```cypher
ANY(gp IN coalesce(e.growth_phases, []) WHERE toLower(gp) IN $growth_phases)
```
Parameters normalized to lowercase.

**Return columns** (`build_list_experiments`): Add:
- `coalesce(e.growth_phases, []) AS growth_phases`
- `coalesce(e.time_point_growth_phases, []) AS time_point_growth_phases`

The `time_point_growth_phases` array is parallel to the existing `time_point_labels`, `time_point_orders`, `time_point_hours`, `time_point_totals`, `time_point_significant_up`, `time_point_significant_down` arrays.

**Summary** (`build_list_experiments_summary`): Add `growth_phases` to the collect/frequencies pattern:
```cypher
apoc.coll.flatten(collect(coalesce(e.growth_phases, []))) AS gps,
...
apoc.coll.frequencies(gps) AS by_growth_phase
```

**MCP layer**: Add `growth_phases` filter parameter. Add `growth_phases` and `time_point_growth_phases` to result model. Add `by_growth_phase` to summary response.

**API layer**: Thread `growth_phases` filter. Add `by_growth_phase` summary conversion via `_rename_freq`.

#### 2. `list_publications`

**Query builder** (`_list_publications_where`): Add `growth_phases: str | None` parameter (single value, matching `background_factors` pattern in this tool). Cypher condition on `p.growth_phases`:
```cypher
ANY(gp IN coalesce(p.growth_phases, []) WHERE toLower(gp) = toLower($growth_phases))
```

**Return column** (`build_list_publications`): Add:
- `coalesce(p.growth_phases, []) AS growth_phases`

**MCP/API**: Add filter parameter, add `growth_phases` to result model.

#### 3. `list_organisms`

**Return column** (`build_list_organisms`): Add:
- `coalesce(o.growth_phases, []) AS growth_phases`

No filter (organism is too high-level for growth_phase filtering). No summary.

**MCP/API**: Add `growth_phases` to result model.

#### 4. `list_clustering_analyses`

**Query builder** (`_clustering_analysis_where`): Add `growth_phases: list[str] | None` parameter. Cypher condition on `ca.growth_phases`:
```cypher
ANY(gp IN coalesce(ca.growth_phases, []) WHERE toLower(gp) IN $growth_phases)
```

**Return column** (`build_list_clustering_analyses`): Add:
- `coalesce(ca.growth_phases, []) AS growth_phases`

**Summary** (`build_list_clustering_analyses_summary`): Add to collect/frequencies:
```cypher
apoc.coll.flatten(collect(coalesce(ca.growth_phases, []))) AS growth_phases_flat,
...
apoc.coll.frequencies(growth_phases_flat) AS by_growth_phase
```

**MCP/API**: Add filter parameter, return column, summary breakdown.

#### 5. `differential_expression_by_gene`

**Shared WHERE** (`_differential_expression_where`): Add `growth_phases: list[str] | None` parameter. Edge-level condition:
```cypher
toLower(r.growth_phase) IN $growth_phases
```
Parameters normalized to lowercase.

**Return column** (`build_differential_expression_by_gene`): Add:
- `r.growth_phase AS growth_phase`

This appears in both compact and verbose modes. It is a timepoint-level experimental condition (like `timepoint` and `timepoint_hours`), not a gene property — every gene at the same experiment×timepoint has the same `growth_phase`.

**Summary global** (`build_differential_expression_by_gene_summary_global`): Add:
```cypher
apoc.coll.frequencies(collect(r.growth_phase)) AS rows_by_growth_phase
```

**Summary by experiment** (`build_differential_expression_by_gene_summary_by_experiment`): Add `growth_phase` to the timepoint-level grouping:
```cypher
WITH e, r.time_point AS tp, r.time_point_order AS tpo,
     r.time_point_hours AS tph, r.growth_phase AS gp,
     ...
     collect({timepoint: tp, timepoint_hours: tph,
              timepoint_order: tpo, growth_phase: gp, ...}) AS timepoints
```

**MCP/API**: Add `growth_phases` filter parameter. Add `growth_phase` to result model. Add `rows_by_growth_phase` to summary. Thread filter through all summary builders. MCP field description: `"Physiological state of the culture at this timepoint (e.g. 'exponential', 'nutrient_limited'). Timepoint-level condition, not gene-specific."`.

#### 6. `differential_expression_by_ortholog`

**Separate WHERE helper** (`_differential_expression_by_ortholog_where`): Add `growth_phases: list[str] | None` parameter. Same edge-level condition as `_differential_expression_where`:
```cypher
toLower(r.growth_phase) IN $growth_phases
```

**Return columns**: Add `r.growth_phase` to the result builders. In `build_differential_expression_by_ortholog_results`, the edge properties are aggregated at group×experiment×timepoint granularity — `growth_phase` is a timepoint-level condition (one value per experiment×timepoint, shared by all genes), so it appears as a scalar per result row.

**Summary**: Add `rows_by_growth_phase` to `build_differential_expression_by_ortholog_summary_global`.

**MCP/API**: Add `growth_phases` filter parameter. Add `growth_phase` to result model. Add summary breakdown.

#### 7. `pathway_enrichment`

**Enrichment inputs** (`de_enrichment_inputs` in `analysis/enrichment.py`): The function calls `differential_expression_by_gene` internally. Once DE returns `growth_phase` per row, it flows into `cluster_metadata` automatically via the `_METADATA_FIELDS` tuple. Add `"growth_phase"` to `_METADATA_FIELDS`.

**Filter**: Add `growth_phases: list[str] | None` parameter to `de_enrichment_inputs`. Filter DE rows by `growth_phase` before building clusters (same pattern as `timepoint_filter`). This lets users say "run enrichment on exponential-phase data only."

**MCP layer**: Add `growth_phases` filter parameter to the `pathway_enrichment` tool. Add `growth_phase` to `PathwayEnrichmentResult` model. Thread to `de_enrichment_inputs`.

**API layer**: Thread `growth_phases` parameter through to `de_enrichment_inputs`.

#### 8. `list_filter_values`

**New filter type**: `growth_phase`.

**Query builder**: New `build_list_growth_phases()` in `queries_lib.py`:
```cypher
MATCH (:Experiment)-[r:Changes_expression_of]->(:Gene)
WITH DISTINCT r.growth_phase AS phase
WHERE phase IS NOT NULL
RETURN phase ORDER BY phase
```

Returns distinct `growth_phase` values from edges with counts (count of edges or count of distinct experiments — experiments is more useful):

```cypher
MATCH (e:Experiment)-[r:Changes_expression_of]->(:Gene)
WITH r.growth_phase AS phase, e.id AS eid
WITH phase, count(DISTINCT eid) AS experiment_count
WHERE phase IS NOT NULL
RETURN phase, experiment_count
ORDER BY experiment_count DESC, phase
```

**API layer**: Add `elif filter_type == "growth_phase"` branch in `list_filter_values`. Returns `{"value": phase, "count": experiment_count}` per value.

**MCP layer**: Update `VALID_FILTER_TYPES` (if any validation exists) to include `growth_phase`. Update docstring.

### Layer summary

| Layer | Files changed |
|---|---|
| Query builders | `kg/queries_lib.py` |
| API | `api/functions.py`, `analysis/enrichment.py` |
| MCP | `mcp_server/tools.py` |
| Tests | `tests/unit/test_query_builders.py`, `tests/unit/test_tool_correctness.py` |
| Docs | `inputs/tools/list_experiments.yaml`, `inputs/tools/list_publications.yaml`, `inputs/tools/differential_expression_by_gene.yaml`, `inputs/tools/differential_expression_by_ortholog.yaml`, `inputs/tools/pathway_enrichment.yaml`, `inputs/tools/list_filter_values.yaml`, `inputs/tools/list_organisms.yaml`, `inputs/tools/list_clustering_analyses.yaml` |
| Regression | `tests/regression/` golden files |

### Ordering and dependencies

This work depends on the KG having the new precomputed fields (`time_point_growth_phases` on Experiment, `growth_phases` on Publication/OrganismTaxon/ClusteringAnalysis). The explorer code can be written and unit-tested (with mocks) before the KG rebuild, but regression and integration tests require the rebuilt KG.

Implementation order within the explorer:

1. **Query builders** — all `queries_lib.py` changes (filters, return columns, summaries)
2. **API layer** — threading filters, building summaries, sparse stripping
3. **MCP layer** — models, tool parameters, docstrings
4. **Enrichment** — `_METADATA_FIELDS` update, `growth_phases` filter in `de_enrichment_inputs`
5. **list_filter_values** — new builder + API branch + MCP update
6. **Unit tests** — builder assertions, tool correctness mocks
7. **Docs** — YAML updates, regenerate MCP resources
8. **Regression fixtures** — regenerate after KG rebuild

## Resolved decisions

- **Edge-level filter for DE tools, experiment-level for browsing tools.** A single filter parameter per tool. No dual filtering needed — edge-level is strictly more precise for DE.
- **`gene_response_profile` excluded.** Aggregates across timepoints; a mashed phase list adds noise, not signal.
- **`time_point_growth_phases` parallel array on Experiment.** Aligns with existing `time_point_*` convention. More useful than flat `growth_phases` for experiment browsing — shows which phase each timepoint is in.
- **Case-insensitive matching.** All growth_phase filters use `toLower()`, matching `background_factors` and `treatment_type` patterns.
- **`list_filter_values` counts by experiment.** `experiment_count` is more meaningful than edge count for a discovery tool — "how many experiments have exponential-phase data" vs "how many DE rows."
- **`growth_phase` is a timepoint-level experimental condition, not a gene property.** All descriptions, docstrings, and YAML docs must make this clear. It describes the physiological state of the culture at the moment of sampling — every gene measured at a given experiment×timepoint shares the same `growth_phase`. Pydantic field descriptions should say "Physiological state of the culture at this timepoint" (not "growth phase of this gene").
