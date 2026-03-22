# Tool spec: list_experiments

## Purpose

Routing tool for expression data. Browse Experiment nodes with per-experiment
gene counts, then pass experiment IDs to `query_expression` for gene-level
results. Summary mode shows breakdowns by organism/treatment/omics to guide
filtering; detail mode returns individual experiments.

## Out of Scope

- Per-gene expression data — that's `query_expression`

## Status / Prerequisites

- [x] KG spec complete: `docs/kg-specs/kg-spec-list-experiments.md`
- [x] KG changes landed and verified (2026-03-22)
- [x] Scope reviewed with user
- [x] Result-size controls decided: summary/detail modes + verbose + limit
- [x] Ready for Phase 2 (build) — approved 2026-03-22

## Use cases

- **Orient:** "How many experiments are there? What organisms/treatments?"
  → summary mode
- **Browse experiments:** "What experiments are available for MED4?"
  → detail mode with organism filter
- **Filter by condition:** "Show me all coculture experiments" or
  "nitrogen and carbon stress experiments" → detail mode with filters
- **Chaining:** `list_organisms` → `list_experiments(organism=...)` →
  `query_expression(experiment_id=...)`
- **From publications:** `list_publications` → get DOI →
  `list_experiments(publication_doi=[...])`
- **Filter discovery:** `list_filter_values` → discover treatment_types →
  `list_experiments(treatment_type=[...])`

## KG dependencies

- `Experiment` nodes (76) with properties: id, name, organism_strain,
  treatment_type, treatment, control, coculture_partner, omics_type,
  is_time_course, light_condition, light_intensity, medium, temperature,
  statistical_test, experimental_context
- `Publication` → `Has_experiment` → `Experiment` edges (76)
- Precomputed stats on Experiment: gene_count, significant_count,
  time_point_count, time_point_labels, time_point_orders, time_point_hours,
  time_point_totals, time_point_significants
- Fulltext index: `experimentFullText` on Experiment (name, treatment,
  control, experimental_context, light_condition) — already exists in KG
- KG spec: `docs/kg-specs/kg-spec-list-experiments.md`

---

## Tool Signature

```python
@mcp.tool(
    tags={"experiments", "expression", "discovery"},
    annotations={"readOnlyHint": True},
)
async def list_experiments(
    ctx: Context,
    organism: Annotated[str | None, Field(
        description="Filter by organism name (case-insensitive partial match "
        "on profiled organism and coculture partner). "
        "E.g. 'MED4', 'Alteromonas'.",
    )] = None,
    treatment_type: Annotated[list[str] | None, Field(
        description="Filter by treatment type(s) (case-insensitive exact match). "
        "E.g. ['coculture', 'nitrogen_stress']. "
        "Use list_filter_values to see valid values.",
    )] = None,
    omics_type: Annotated[list[str] | None, Field(
        description="Filter by omics platform(s) (case-insensitive). "
        "E.g. ['RNASEQ', 'PROTEOMICS'].",
    )] = None,
    publication_doi: Annotated[list[str] | None, Field(
        description="Filter by publication DOI(s) (case-insensitive exact match). "
        "Get DOIs from list_publications. "
        "E.g. ['10.1038/ismej.2016.70'].",
    )] = None,
    coculture_partner: Annotated[str | None, Field(
        description="Filter by coculture partner organism (case-insensitive "
        "partial match). Narrows coculture experiments. "
        "E.g. 'Alteromonas', 'HOT1A3'.",
    )] = None,
    search_text: Annotated[str | None, Field(
        description="Free-text search on experiment name, treatment, control, "
        "experimental context, and light condition (Lucene fulltext, "
        "case-insensitive). E.g. 'continuous light', 'diel'.",
    )] = None,
    time_course_only: Annotated[bool, Field(
        description="If true, return only time-course experiments "
        "(multiple time points).",
    )] = False,
    mode: Annotated[Literal["summary", "detail"], Field(
        description="'summary' returns breakdowns by organism, treatment type, "
        "and omics type to guide filtering. 'detail' returns individual "
        "experiments with gene counts. Start with summary to orient, "
        "then use detail with filters.",
    )] = "summary",
    verbose: Annotated[bool, Field(
        description="Detail mode only. Include experiment name, publication "
        "title, treatment/control descriptions, and experimental conditions "
        "(light, medium, temperature, statistical test, context).",
    )] = False,
    limit: Annotated[int, Field(
        description="Detail mode only. Max results.", ge=1,
    )] = 50,
) -> ListExperimentsResponse:
    """List differential expression experiments in the knowledge graph.

    Start with mode='summary' to see experiment counts by organism, treatment
    type, and omics type. Then use mode='detail' with filters to browse
    individual experiments. Pass experiment IDs to query_expression for
    gene-level results.
    """
```

---

## Result-size controls

### Option B: Large result set (summary/detail modes)

76 experiments currently, growing to ~150-175 with 10 additional papers.
Summary mode provides breakdowns to guide filtering before requesting
detail rows.

About content is served via MCP resource `docs://tools/list_experiments`,
not as a tool mode parameter.

#### Summary mode

All filters apply — summary reflects the filtered subset.

| Field | Type | Description |
|---|---|---|
| total_entries | int | All experiments in KG (unfiltered) |
| total_matching | int | Experiments matching filters |
| by_organism | list[dict] | `[{organism_strain, experiment_count}]` sorted by experiment_count DESC |
| by_treatment_type | list[dict] | `[{treatment_type, experiment_count}]` sorted by experiment_count DESC |
| by_omics_type | list[dict] | `[{omics_type, experiment_count}]` sorted by experiment_count DESC |
| by_publication | list[dict] | `[{publication_doi, experiment_count}]` sorted by experiment_count DESC |
| time_course_count | int | Number of time-course experiments in matching set |
| score_max | float \| null | Max Lucene relevance score (only when search_text used) |
| score_median | float \| null | Median Lucene relevance score (only when search_text used) |

#### Detail mode

**Per-result columns (compact, 10 fields):**

| Field | Type | Description |
|---|---|---|
| experiment_id | str | Experiment identifier (e.g. "10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq") |
| publication_doi | str | Publication DOI (e.g. "10.1038/ismej.2016.70") |
| organism_strain | str | Profiled organism (e.g. "Prochlorococcus MED4") |
| treatment_type | str | Treatment category (e.g. "coculture", "nitrogen_stress") |
| coculture_partner | str \| null | Coculture partner organism, null for non-coculture (e.g. "Alteromonas macleodii HOT1A3") |
| omics_type | str | Omics platform (e.g. "RNASEQ", "MICROARRAY", "PROTEOMICS") |
| is_time_course | bool | Whether experiment has multiple time points |
| time_points | list[TimePoint] | Per-time-point stats. Omitted for non-time-course experiments. |
| gene_count | int | Total genes with expression data in this experiment (e.g. 1696) |
| significant_count | int | Genes with significant differential expression (e.g. 423) |

**TimePoint fields:** label, order, hours, total, significant

**Verbose adds (9 fields):**

| Field | Type | Description |
|---|---|---|
| name | str | Experiment display name (e.g. "MED4 Coculture with Alteromonas HOT1A3 vs Pro99 medium growth conditions (RNASEQ)") |
| publication_title | str | Publication title |
| treatment | str | Treatment description (e.g. "Coculture with Alteromonas HOT1A3") |
| control | str | Control description (e.g. "Pro99 medium growth conditions") |
| light_condition | str \| null | Light regime (e.g. "continuous light") |
| light_intensity | str \| null | Light intensity (e.g. "10 umol photons m-2 s-1") |
| medium | str \| null | Growth medium (e.g. "Pro99") |
| temperature | str \| null | Temperature (e.g. "24C") |
| statistical_test | str \| null | Statistical method (e.g. "Rockhopper") |
| experimental_context | str \| null | Context summary (e.g. "in Pro99 medium under continuous light") |

**Sort key:** `publication_year DESC, organism_strain ASC, name ASC`
(newest publications first, grouped by organism within publication).
When `search_text` is used, sort by `score DESC` first.

**Default limit:** 50

## Special handling

- **Precomputed stats:** All gene counts and time point stats are read
  from precomputed properties on Experiment nodes (KG build step). No
  joins to expression edges — single MATCH, property reads only. Same
  pattern as `list_organisms` with OrganismTaxon.
- **Fulltext search:** `search_text` uses the existing `experimentFullText`
  Lucene index (covers: name, treatment, control, experimental_context,
  light_condition). When `search_text` is provided, the query starts with
  `CALL db.index.fulltext.queryNodes('experimentFullText', $search_text)`,
  results include `score` and sort by `score DESC`. Lucene retry pattern
  applies (escape special chars on failure). When no `search_text`, uses
  standard MATCH. Works in both summary and detail modes.
- **Time point assembly:** Precomputed parallel arrays (labels, orders,
  hours, totals, significants) assembled into `time_points` list of dicts
  in API layer. Omitted for non-time-course experiments.
- **Case-insensitive matching:** All string filters use toLower/toUpper
  normalization in Cypher.
- **`coculture_partner` null handling:** Non-coculture/non-viral
  experiments have null coculture_partner. Coculture and viral experiments
  have the interacting organism (e.g. Alteromonas strain or Phage).

---

## Implementation Order

| Step | Layer | File | What |
|------|-------|------|------|
| 1 | Query builder | `kg/queries_lib.py` | `build_list_experiments()` + `build_list_experiments_summary()` |
| 2 | API function | `api/functions.py` | `list_experiments()` with `mode` param |
| 3 | Exports | `api/__init__.py`, `multiomics_explorer/__init__.py` | Add to imports + `__all__` |
| 4 | MCP wrapper | `mcp_server/tools.py` | `@mcp.tool()` wrapper with Pydantic models + mode dispatch |
| 5 | Unit tests | `tests/unit/test_query_builders.py` | `TestBuildListExperiments` + `TestBuildListExperimentsSummary` |
| 6 | Unit tests | `tests/unit/test_api_functions.py` | `TestListExperiments` |
| 7 | Unit tests | `tests/unit/test_tool_wrappers.py` | `TestListExperimentsWrapper` + update `EXPECTED_TOOLS` |
| 8 | Integration | `tests/integration/test_mcp_tools.py` | Smoke test against live KG |
| 9 | Regression | `tests/regression/test_regression.py` | Add to `TOOL_BUILDERS` |
| 10 | Eval cases | `tests/evals/cases.yaml` | Regression + correctness cases |
| 11 | About content | `multiomics_explorer/skills/multiomics-kg-guide/references/tools/list_experiments.md` | Per-tool about text |
| 12 | Docs | `CLAUDE.md` | Add row to MCP Tools table |

---

## Query Builder

**File:** `kg/queries_lib.py`

### `build_list_experiments`

```python
def build_list_experiments(
    *,
    organism: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
    coculture_partner: str | None = None,
    search_text: str | None = None,
    time_course_only: bool = False,
    verbose: bool = False,
    limit: int | None = None,
) -> tuple[str, dict]:
    """Build Cypher for listing experiments with precomputed gene count stats.

    RETURN keys (compact): experiment_id, publication_doi,
    organism_strain, treatment_type, coculture_partner, omics_type,
    is_time_course, gene_count, significant_count, time_point_count,
    time_point_labels, time_point_orders, time_point_hours,
    time_point_totals, time_point_significants.
    RETURN keys (verbose): adds name, publication_title, treatment,
    control, light_condition, light_intensity, medium, temperature,
    statistical_test, experimental_context.
    RETURN keys (search_text): adds score.
    """
```

### `build_list_experiments_summary`

```python
def build_list_experiments_summary(
    *,
    organism: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
    coculture_partner: str | None = None,
    search_text: str | None = None,
    time_course_only: bool = False,
) -> tuple[str, dict]:
    """Build summary aggregation Cypher for list_experiments.

    RETURN keys: total_matching, by_organism, by_treatment_type,
    by_omics_type, by_publication, time_course_count.
    RETURN keys (search_text): adds score_max, score_median.
    """
```

Both builders share the same WHERE clause construction.

**Summary Cypher (without search_text):**

```cypher
MATCH (p:Publication)-[:Has_experiment]->(e:Experiment)
{where_block}
WITH collect(e.organism_strain) AS orgs,
     collect(e.treatment_type) AS tts,
     collect(e.omics_type) AS omics,
     collect(p.doi) AS dois,
     collect(e.is_time_course) AS tc
RETURN size(orgs) AS total_matching,
       size([x IN tc WHERE x = 'true']) AS time_course_count,
       apoc.coll.frequencies(orgs) AS by_organism,
       apoc.coll.frequencies(tts) AS by_treatment_type,
       apoc.coll.frequencies(omics) AS by_omics_type,
       apoc.coll.frequencies(dois) AS by_publication
```

Uses `apoc.coll.frequencies` for per-dimension breakdowns — returns
`[{item, count}]` per dimension. API layer renames `item`/`count` to
domain-specific keys (e.g. `organism_strain`/`experiment_count`) and
sorts by `experiment_count` descending.

**Summary Cypher (with search_text):**

```cypher
CALL db.index.fulltext.queryNodes('experimentFullText', $search_text)
YIELD node AS e, score
MATCH (p:Publication)-[:Has_experiment]->(e)
{where_block}
WITH collect(e.organism_strain) AS orgs,
     collect(e.treatment_type) AS tts,
     collect(e.omics_type) AS omics,
     collect(p.doi) AS dois,
     collect(e.is_time_course) AS tc,
     collect(score) AS scores
RETURN size(orgs) AS total_matching,
       size([x IN tc WHERE x = 'true']) AS time_course_count,
       apoc.coll.frequencies(orgs) AS by_organism,
       apoc.coll.frequencies(tts) AS by_treatment_type,
       apoc.coll.frequencies(omics) AS by_omics_type,
       apoc.coll.frequencies(dois) AS by_publication,
       apoc.coll.max(scores) AS score_max,
       apoc.coll.sort(scores)[size(scores)/2] AS score_median
```

Score distribution (max/median) lets Claude judge whether the top
results are highly relevant or barely matching the search text.

**Detail Cypher (without search_text):**

```cypher
MATCH (p:Publication)-[:Has_experiment]->(e:Experiment)
{where_block}
RETURN e.id AS experiment_id,
       p.doi AS publication_doi,
       e.organism_strain AS organism_strain,
       e.treatment_type AS treatment_type,
       e.coculture_partner AS coculture_partner,
       e.omics_type AS omics_type,
       e.is_time_course AS is_time_course,
       e.gene_count AS gene_count,
       e.significant_count AS significant_count,
       e.time_point_count AS time_point_count,
       e.time_point_labels AS time_point_labels,
       e.time_point_orders AS time_point_orders,
       e.time_point_hours AS time_point_hours,
       e.time_point_totals AS time_point_totals,
       e.time_point_significants AS time_point_significants
       {verbose_columns}
ORDER BY p.publication_year DESC, e.organism_strain, e.name
{limit_clause}
```

**Detail Cypher (with search_text — fulltext entry point):**

```cypher
CALL db.index.fulltext.queryNodes('experimentFullText', $search_text)
YIELD node AS e, score
MATCH (p:Publication)-[:Has_experiment]->(e)
{where_block}
RETURN e.id AS experiment_id,
       p.doi AS publication_doi,
       e.organism_strain AS organism_strain,
       e.treatment_type AS treatment_type,
       e.coculture_partner AS coculture_partner,
       e.omics_type AS omics_type,
       e.is_time_course AS is_time_course,
       e.gene_count AS gene_count,
       e.significant_count AS significant_count,
       e.time_point_count AS time_point_count,
       e.time_point_labels AS time_point_labels,
       e.time_point_orders AS time_point_orders,
       e.time_point_hours AS time_point_hours,
       e.time_point_totals AS time_point_totals,
       e.time_point_significants AS time_point_significants,
       score
       {verbose_columns}
ORDER BY score DESC, e.organism_strain, e.name
{limit_clause}
```

All stats are precomputed on Experiment nodes during KG build (see KG spec).
No joins to expression edges needed — single MATCH, property reads only.
Same pattern as `list_organisms` reading precomputed stats from OrganismTaxon.

When `search_text` is provided, the fulltext index is the query entry point
(same pattern as `build_list_publications`). Results include `score` and
sort by relevance first. Additional filters (organism, treatment_type, etc.)
are applied via WHERE after the fulltext call.

`{verbose_columns}` expands to:
```
,      e.name AS name,
       p.title AS publication_title,
       e.treatment AS treatment,
       e.control AS control,
       e.light_condition AS light_condition,
       e.light_intensity AS light_intensity,
       e.medium AS medium,
       e.temperature AS temperature,
       e.statistical_test AS statistical_test,
       e.experimental_context AS experimental_context
```
when `verbose=True`, empty string otherwise.

**WHERE clause construction:**

```python
where_clauses: list[str] = []
params: dict = {}

if organism:
    where_clauses.append(
        "(toLower(e.organism_strain) CONTAINS toLower($org) "
        "OR toLower(e.coculture_partner) CONTAINS toLower($org))"
    )
    params["org"] = organism

if treatment_type:
    where_clauses.append(
        "toLower(e.treatment_type) IN $treatment_types"
    )
    params["treatment_types"] = [t.lower() for t in treatment_type]

if omics_type:
    where_clauses.append(
        "toUpper(e.omics_type) IN $omics_types"
    )
    params["omics_types"] = [t.upper() for t in omics_type]

if publication_doi:
    where_clauses.append(
        "toLower(p.doi) IN $dois"
    )
    params["dois"] = [d.lower() for d in publication_doi]

if coculture_partner:
    where_clauses.append(
        "toLower(e.coculture_partner) CONTAINS toLower($partner)"
    )
    params["partner"] = coculture_partner

# search_text is NOT in where_clauses — it controls which Cypher
# variant is used (fulltext entry point vs MATCH). The $search_text
# param is added directly when search_text is provided.

if time_course_only:
    where_clauses.append("e.is_time_course = 'true'")
```

**Design notes:**
- All stats are precomputed — no expression edge aggregation at query time.
  Query reads properties directly from Experiment nodes.
- Two Cypher variants per builder: with `search_text` (fulltext entry
  point) and without (MATCH entry point). Same pattern as
  `build_list_publications`.
- Summary query uses `apoc.coll.frequencies` for all 4 dimension
  breakdowns in a single pass. API layer renames `item`/`count` to
  domain keys and sorts by count descending.
- Both modes run summary query. Detail additionally runs detail query
  with LIMIT in Cypher.
- Precomputed parallel arrays for time point data — API layer assembles
  into structured TimePoint objects. Neo4j arrays can't contain nulls,
  so sentinel values (`""` for labels, `-1.0` for hours) are converted
  to null in the API layer.
- `is_time_course` stored as string `"true"/"false"` in KG — cast to bool
  in API layer.
- Non-time-course experiments have a single time point in arrays. The
  `time_points` field is omitted from results for these experiments since
  a single time point isn't useful for routing.
- Detail query uses LIMIT in Cypher. Total counts come from the summary
  query, not from the detail query.
- Case normalization: toLower/toUpper applied in Cypher for CONTAINS and
  IN filters. List parameters pre-normalized in Python for IN clauses.
- Lucene retry: API layer catches fulltext query failures from special
  characters in search_text, escapes them, and retries (same as
  `list_publications`).

---

## API Function

**File:** `api/functions.py`

```python
def list_experiments(
    organism: str | None = None,
    treatment_type: list[str] | None = None,
    omics_type: list[str] | None = None,
    publication_doi: list[str] | None = None,
    coculture_partner: str | None = None,
    search_text: str | None = None,
    time_course_only: bool = False,
    mode: str = "summary",
    verbose: bool = False,
    limit: int | None = None,
    *,
    conn: GraphConnection | None = None,
) -> dict:
    """List experiments with gene count statistics.

    Always returns: total_entries, total_matching, by_organism,
    by_treatment_type, by_omics_type, by_publication, time_course_count,
    returned, truncated, results.

    When summary=True: results is empty list.
    When summary=False (detail): results populated with experiments.
    Per result: experiment_id, publication_doi, organism_strain,
    treatment_type, coculture_partner, omics_type, is_time_course (bool),
    time_points (list, omitted if not time-course), gene_count,
    significant_count.
    When verbose=True, also includes: name, publication_title, treatment,
    control, light_condition, light_intensity, medium, temperature,
    statistical_test, experimental_context.
    """
```

Post-processing in API layer:

**Both modes:**
1. Run `build_list_experiments_summary` — returns total_matching,
   time_course_count, and `apoc.coll.frequencies` breakdowns
2. Lucene retry: if fulltext query fails with special chars, escape and retry
3. Rename `{item, count}` dicts to domain keys (e.g. `organism_strain`,
   `experiment_count`) and sort by `experiment_count` descending
4. Get `total_entries` from unfiltered count (separate count query or
   run summary with no filters)

**Detail mode additionally:**
5. Run `build_list_experiments` with LIMIT in Cypher
6. Cast `is_time_course` from string to bool
7. Assemble precomputed parallel arrays into `time_points` list of dicts.
   Convert sentinel values: `""` label → null, `-1.0` hours → null.
8. Omit `time_points` for non-time-course experiments
9. Set returned/truncated from results vs total_matching

**Summary mode:**
5. Set `results: []`, `returned: 0`, `truncated: True`

**`total_entries`:** Requires a separate count query (or cache). For ~150
experiments this is cheap — run unfiltered count query.

---

## MCP Wrapper

**File:** `mcp_server/tools.py`

```python
class TimePoint(BaseModel):
    label: str | None = Field(default=None, description="Time point label, null if unlabeled (e.g. '24h', '5h extended darkness (40h)')")
    order: int = Field(description="Sort order within experiment (e.g. 1, 2, 3)")
    hours: float | None = Field(default=None, description="Time in hours, null if unknown (e.g. 24.0)")
    total: int = Field(description="Total genes with expression data at this time point (e.g. 1696)")
    significant: int = Field(description="Genes with significant differential expression (e.g. 423)")

class ExperimentResult(BaseModel):
    # compact fields (always returned)
    experiment_id: str = Field(description="Experiment identifier (e.g. '10.1038/ismej.2016.70_coculture_alteromonas_hot1a3_med4_rnaseq')")
    publication_doi: str = Field(description="Publication DOI (e.g. '10.1038/ismej.2016.70')")
    organism_strain: str = Field(description="Profiled organism (e.g. 'Prochlorococcus MED4')")
    treatment_type: str = Field(description="Treatment category (e.g. 'coculture', 'nitrogen_stress')")
    coculture_partner: str | None = Field(default=None, description="Coculture partner organism, null for non-coculture (e.g. 'Alteromonas macleodii HOT1A3')")
    omics_type: str = Field(description="Omics platform (e.g. 'RNASEQ', 'MICROARRAY', 'PROTEOMICS')")
    is_time_course: bool = Field(description="Whether experiment has multiple time points")
    time_points: list[TimePoint] | None = Field(default=None, description="Per-time-point gene counts. Omitted for non-time-course experiments.")
    gene_count: int = Field(description="Total genes with expression data (e.g. 1696)")
    significant_count: int = Field(description="Genes with significant differential expression (e.g. 423)")
    score: float | None = Field(default=None, description="Lucene relevance score, present only when search_text is used (e.g. 2.45)")
    # verbose-only fields
    name: str | None = Field(default=None, description="Experiment display name (e.g. 'MED4 Coculture with Alteromonas HOT1A3 vs Pro99 medium growth conditions (RNASEQ)')")
    publication_title: str | None = Field(default=None, description="Publication title")
    treatment: str | None = Field(default=None, description="Treatment description (e.g. 'Coculture with Alteromonas HOT1A3')")
    control: str | None = Field(default=None, description="Control description (e.g. 'Pro99 medium growth conditions')")
    light_condition: str | None = Field(default=None, description="Light regime (e.g. 'continuous light')")
    light_intensity: str | None = Field(default=None, description="Light intensity (e.g. '10 umol photons m-2 s-1')")
    medium: str | None = Field(default=None, description="Growth medium (e.g. 'Pro99')")
    temperature: str | None = Field(default=None, description="Temperature (e.g. '24C')")
    statistical_test: str | None = Field(default=None, description="Statistical method (e.g. 'Rockhopper')")
    experimental_context: str | None = Field(default=None, description="Context summary (e.g. 'in Pro99 medium under continuous light')")

class OrganismBreakdown(BaseModel):
    organism_strain: str = Field(description="Organism name (e.g. 'Prochlorococcus MED4')")
    experiment_count: int = Field(description="Number of experiments for this organism (e.g. 46)")

class TreatmentTypeBreakdown(BaseModel):
    treatment_type: str = Field(description="Treatment category (e.g. 'coculture')")
    experiment_count: int = Field(description="Number of experiments (e.g. 16)")

class OmicsTypeBreakdown(BaseModel):
    omics_type: str = Field(description="Omics platform (e.g. 'RNASEQ')")
    experiment_count: int = Field(description="Number of experiments (e.g. 48)")

class PublicationBreakdown(BaseModel):
    publication_doi: str = Field(description="Publication DOI (e.g. '10.1038/ismej.2016.70')")
    experiment_count: int = Field(description="Number of experiments from this publication (e.g. 5)")

class ListExperimentsResponse(BaseModel):
    total_entries: int = Field(description="Total experiments in the KG (unfiltered)")
    total_matching: int = Field(description="Experiments matching filters")
    returned: int = Field(description="Number of results returned (0 in summary mode)")
    truncated: bool = Field(description="True if results were truncated by limit, or summary mode")
    by_organism: list[OrganismBreakdown] = Field(description="Experiment counts per organism, sorted by count descending")
    by_treatment_type: list[TreatmentTypeBreakdown] = Field(description="Experiment counts per treatment type, sorted by count descending")
    by_omics_type: list[OmicsTypeBreakdown] = Field(description="Experiment counts per omics platform, sorted by count descending")
    by_publication: list[PublicationBreakdown] = Field(description="Experiment counts per publication, sorted by count descending")
    time_course_count: int = Field(description="Number of time-course experiments in matching set")
    score_max: float | None = Field(default=None, description="Max Lucene relevance score, present only when search_text is used (e.g. 4.52)")
    score_median: float | None = Field(default=None, description="Median Lucene relevance score, present only when search_text is used (e.g. 1.23)")
    results: list[ExperimentResult] = Field(description="Individual experiments (empty in summary mode, populated in detail mode)")
```

Mode dispatch in wrapper: both modes return `ListExperimentsResponse`.
Summary mode: breakdowns populated, `results: []`, `returned: 0`,
`truncated: True`. Detail mode: breakdowns populated, `results`
populated, `returned` and `truncated` reflect the limit. Breakdowns
are always computed (cheap — aggregation over precomputed properties).

---

## Tests

### Unit: query builder (`test_query_builders.py`)

```
class TestBuildListExperiments:
    test_no_filters                — valid Cypher, no WHERE
    test_organism_filter           — WHERE toLower CONTAINS on organism_strain OR coculture_partner
    test_treatment_type_filter     — WHERE toLower IN $treatment_types
    test_omics_type_filter         — WHERE toUpper IN $omics_types
    test_publication_doi_filter    — WHERE toLower IN $dois
    test_coculture_partner_filter  — WHERE toLower CONTAINS on coculture_partner
    test_search_text_fulltext      — uses experimentFullText index, not CONTAINS
    test_time_course_only          — WHERE is_time_course = 'true'
    test_combined_filters          — multiple filters produce AND-joined WHERE
    test_returns_expected_columns  — compact columns present in RETURN
    test_verbose_false             — no verbose columns in RETURN
    test_verbose_true              — name, treatment, etc. in RETURN
    test_order_by                  — ORDER BY publication_year DESC, organism_strain, name
    test_limit_clause              — LIMIT present when limit set
    test_limit_none                — no LIMIT when limit is None

class TestBuildListExperimentsSummary:
    test_no_filters                — valid Cypher, returns lightweight projection
    test_with_filters              — WHERE applied to summary query
    test_search_text_fulltext      — uses experimentFullText index
    test_shares_where_clause       — same WHERE construction as detail builder
    test_returns_aggregation_keys  — RETURN has total_matching, time_course_count, by_organism, by_treatment_type, by_omics_type, by_publication
```

### Unit: API function (`test_api_functions.py`)

```
class TestListExperiments:
    test_detail_returns_dict       — returns dict with breakdowns + results
    test_summary_returns_dict      — returns dict with breakdowns + empty results
    test_passes_params             — all params forwarded to builder
    test_is_time_course_cast       — string "true"/"false" cast to bool
    test_time_points_assembled     — parallel arrays assembled into list of dicts
    test_time_points_omitted       — non-time-course results have no time_points key
    test_limit_slices_results      — limit applied, total_matching is full count
    test_breakdowns_computed       — by_organism, by_treatment_type, etc. match row data
    test_creates_conn_when_none    — default conn used when None
    test_importable_from_package   — importable from multiomics_explorer
```

### Unit: MCP wrapper (`test_tool_wrappers.py`)

```
class TestListExperimentsWrapper:
    test_summary_mode_empty_results    — mode="summary" returns breakdowns + results=[]
    test_detail_mode_has_results       — mode="detail" returns breakdowns + results
    test_default_mode_is_summary       — no mode param defaults to summary
    test_both_modes_have_breakdowns    — breakdowns populated in both modes
    test_detail_empty_results          — returns envelope with total_matching=0
    test_detail_params_forwarded       — all params forwarded to API
    test_detail_truncation_metadata    — returned == len(results), truncated flag correct
    test_detail_verbose_fields_present — verbose=True includes condition fields
    test_detail_verbose_fields_absent  — verbose=False excludes condition fields
    test_summary_with_filters          — filters applied to summary breakdowns

Update EXPECTED_TOOLS to include "list_experiments".
```

### Integration (`test_mcp_tools.py`)

Against live KG:
- Summary mode no filters → total_matching == total_entries
- Summary mode with organism filter → total_matching < total_entries
- Summary by_organism experiment_counts sum to total_matching
- Summary by_treatment_type counts sum to total_matching
- Summary by_omics_type counts sum to total_matching
- Detail mode no filters → returns experiments up to limit
- Detail `organism="MED4"` → returns MED4 experiments
- Detail `treatment_type=["coculture"]` → coculture experiments only
- Detail `omics_type=["PROTEOMICS"]` → proteomics experiments only
- Detail `time_course_only=True` → time-course experiments
- Detail `search_text="continuous light"` → fulltext matches
- Time-course experiments have time_points with >1 entry
- Non-time-course experiments have no time_points field
- gene_count and significant_count are >= 0
- is_time_course is bool, not string
- **Summary consistency:** summary total_matching == detail total row count
  (run both modes with same filters, verify counts match)

### Regression (`test_regression.py`)

Add to `TOOL_BUILDERS`:
```python
"list_experiments": build_list_experiments,
"list_experiments_summary": build_list_experiments_summary,
```

### Eval cases (`cases.yaml`)

```yaml
- id: list_experiments_summary
  tool: list_experiments
  desc: Summary mode shows breakdowns
  params:
    mode: summary
  expect:
    columns: [total_entries, total_matching, by_organism,
              by_treatment_type, by_omics_type, time_course_count]

- id: list_experiments_summary_filtered
  tool: list_experiments
  desc: Summary with organism filter
  params:
    mode: summary
    organism: "MED4"
  expect:
    columns: [total_entries, total_matching, by_organism]

- id: list_experiments_detail_all
  tool: list_experiments
  desc: Detail mode returns experiments
  params:
    mode: detail
  expect:
    min_rows: 50
    columns: [experiment_id, publication_doi, organism_strain,
              treatment_type, omics_type, is_time_course, gene_count]

- id: list_experiments_detail_organism
  tool: list_experiments
  desc: Detail filtered by organism
  params:
    mode: detail
    organism: "MED4"
  expect:
    min_rows: 10
    columns: [experiment_id, organism_strain, gene_count]

- id: list_experiments_detail_treatment_types
  tool: list_experiments
  desc: Detail filtered by multiple treatment types
  params:
    mode: detail
    treatment_type: ["coculture", "nitrogen_stress"]
  expect:
    min_rows: 20
    columns: [experiment_id, treatment_type]

- id: list_experiments_detail_coculture_partner
  tool: list_experiments
  desc: Detail filtered by coculture partner
  params:
    mode: detail
    coculture_partner: "Alteromonas"
  expect:
    min_rows: 3
    columns: [experiment_id, coculture_partner]

- id: list_experiments_detail_time_course
  tool: list_experiments
  desc: Detail time-course only
  params:
    mode: detail
    time_course_only: true
  expect:
    min_rows: 20
    columns: [experiment_id, is_time_course]

- id: list_experiments_detail_proteomics
  tool: list_experiments
  desc: Detail proteomics experiments
  params:
    mode: detail
    omics_type: ["PROTEOMICS"]
  expect:
    min_rows: 1
    columns: [experiment_id, omics_type]
```

---

## About Content

Auto-generated from Pydantic models + human-authored input YAML.
Served via MCP resource at `docs://tools/list_experiments`.

### Input YAML

**File:** `multiomics_explorer/inputs/tools/list_experiments.yaml`

```yaml
examples:
  - title: Orient — what experiments exist?
    call: list_experiments()
    response: |
      {"total_entries": 152, "total_matching": 152,
       "by_organism": [{"organism_strain": "Prochlorococcus MED4", "experiment_count": 46}, ...],
       "by_treatment_type": [{"treatment_type": "coculture", "experiment_count": 30}, ...],
       "by_omics_type": [{"omics_type": "RNASEQ", "experiment_count": 90}, ...],
       "time_course_count": 50, "returned": 0, "truncated": true, "results": []}

  - title: Summary for MED4 only
    call: list_experiments(organism="MED4")

  - title: Browse coculture experiments with Alteromonas
    call: list_experiments(mode="detail", treatment_type=["coculture"], coculture_partner="Alteromonas")

  - title: Time-course nitrogen stress in MED4
    call: list_experiments(mode="detail", organism="MED4", treatment_type=["nitrogen_stress"], time_course_only=True)

  - title: From publication to expression data
    steps: |
      Step 1: list_publications(search="Biller")
              -> get DOI from results

      Step 2: list_experiments(mode="detail", publication_doi=["10.1038/ismej.2016.70"])
              -> browse experiments, pick experiment_id

      Step 3: query_expression(experiment_id="...")
              -> get gene-level results

  - title: Orient then drill down
    steps: |
      Step 1: list_experiments()
              -> see 152 total, by_organism: MED4 (46), by_treatment_type: coculture (30), by_omics_type: RNASEQ (90)

      Step 2: list_experiments(mode="detail", organism="MED4", treatment_type=["coculture"])
              -> browse the 12 MED4 coculture experiments

      Step 3: query_expression(experiment_id="...")
              -> get gene-level results

verbose_fields:
  - name
  - publication_title
  - treatment
  - control
  - light_condition
  - light_intensity
  - medium
  - temperature
  - statistical_test
  - experimental_context

chaining:
  - "list_organisms -> list_experiments"
  - "list_publications -> list_experiments"
  - "list_filter_values -> list_experiments"
  - "list_experiments -> query_expression"

mistakes:
  - "Default mode is summary — use mode='detail' to see individual experiments"
  - "gene_count is total genes with expression data, not total significant genes — use significant_count for that"
  - "time_points is omitted for non-time-course experiments, not an empty list"
  - "verbose and limit only apply to detail mode, ignored in summary"
  - wrong: "list_experiments(publication='Biller 2018')"
    right: "list_publications(search='Biller') then list_experiments(publication_doi=['10.1038/...'])"
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add row to MCP Tools table: `list_experiments` — Experiments with gene count stats. Summary mode for breakdowns, detail mode for individual experiments. Filterable by organism/treatment/omics/publication. |
