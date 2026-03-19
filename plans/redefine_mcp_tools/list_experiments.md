# Plan: `list_experiments` — new tool

The routing tool for expression data. Surfaces the ~100–120 Experiment nodes
with per-time-point summary statistics computed from expression edges. The LLM
browses experiments here, then passes experiment IDs to `query_expression`.

## Status / Prerequisites

- [ ] KG change: Experiment node redesign (see `experiment_node_redesign.md`)
- [ ] KG change: `Changes_expression_of` edges with `time_point_order`,
  `time_point_hours`, `significant` properties
- [ ] KG change: Full-text index on Experiment for keyword search

## Out of Scope

- Returning per-gene data — that's `query_expression`
- Phase 2 temporal profiling experiments — those will show up here once added
  to the KG with `condition_type="diel_profiling"`

---

## Tool Signature

```python
@mcp.tool()
def list_experiments(
    ctx: Context,
    publication: str | None = None,
    organism: str | None = None,
    condition_type: str | None = None,
    coculture_partner: str | None = None,
    omics_type: str | None = None,
    keyword: str | None = None,
    time_course_only: bool = False,
) -> str:
    """List differential expression experiments in the knowledge graph.

    Returns experiment metadata with per-time-point gene counts. Use this
    to browse the experimental landscape, then pass experiment IDs to
    query_expression for gene-level results.

    Args:
        publication: Filter by publication DOI or keyword on title.
            E.g. "Biller 2018" or "10.1038/ismej.2016.70".
        organism: Filter by organism name (CONTAINS match). Matches both
            profiled organism and coculture partner. E.g. "MED4", "HOT1A3".
        condition_type: Filter by experiment type. E.g. "coculture",
            "nitrogen_stress", "light_stress". Use list_filter_values
            to see valid values.
        coculture_partner: Filter by coculture partner organism only
            (CONTAINS match). Narrows coculture experiments. E.g.
            "Alteromonas", "HOT1A3".
        omics_type: Filter by omics platform. E.g. "RNASEQ", "PROTEOMICS",
            "MICROARRAY".
        keyword: Free-text search on experiment name, treatment, control,
            and experimental context. E.g. "continuous light", "diel".
        time_course_only: If True, return only time-course experiments
            (multiple time points).
    """
```

**Return columns:**
`experiment_id`, `name`, `publication_doi`, `publication_title`,
`organism_strain`, `condition_type`, `treatment`, `control`,
`coculture_partner`, `omics_type`, `is_time_course`, `time_points` (list of
objects with label/order/hours/significant/total), `gene_count`,
`significant_count`.

---

## KG-side Changes

- [ ] K1: Experiment node with all properties
- [ ] K2: `Changes_expression_of` edges with time_point_order, significant
- [ ] K3: Full-text index on Experiment (name, treatment, control, context)

## Implementation Order

| Order | Change | Where | Status |
|-------|--------|-------|--------|
| 1 | Experiment node + edges + indexes | KG | pending |
| 2 | `build_list_experiments` in `queries_lib.py` | Explorer | this file |
| 3 | `list_experiments` tool in `tools.py` | Explorer | this file |
| 4 | Tests, docs | Explorer | this file |

## Agent Assignments

| Step | Agent | Task | Depends on |
|------|-------|------|------------|
| 1 | **query-builder** | Add `build_list_experiments` to `queries_lib.py` | KG rebuild |
| 2 | **tool-wrapper** | Add `list_experiments` tool to `tools.py` | query-builder |
| 3a | **test-updater** | Add unit, integration, eval tests | tool-wrapper |
| 3b | **doc-updater** | Update `CLAUDE.md`, `README.md`, `AGENT.md`, `docs/testplans/testplan.md` | tool-wrapper |
| 4 | **code-reviewer** | Review all changes, run unit tests, grep for stale refs | test-updater, doc-updater |

---

## Query Builders

**Files:** `queries_lib.py`

### `build_list_experiments`

This query has two parts: (1) match and filter experiments, (2) aggregate
per-time-point stats from expression edges.

```cypher
MATCH (p:Publication)-[:Has_experiment]->(e:Experiment)
{where_block}
WITH p, e
OPTIONAL MATCH (e)-[r:Changes_expression_of]->(g:Gene)
WITH p, e,
     r.time_point AS tp,
     r.time_point_order AS tp_order,
     r.time_point_hours AS tp_hours,
     count(r) AS total,
     count(CASE WHEN r.significant = 'significant' THEN 1 END) AS significant
ORDER BY e.id, tp_order
WITH p, e,
     collect(CASE WHEN tp IS NOT NULL THEN {
       label: tp,
       order: tp_order,
       hours: tp_hours,
       significant: significant,
       total: total
     } END) AS time_points,
     sum(total) AS gene_count,
     sum(significant) AS significant_count
RETURN e.id AS experiment_id,
       e.name AS name,
       p.doi AS publication_doi,
       p.title AS publication_title,
       e.organism_strain AS organism_strain,
       e.treatment_type AS condition_type,
       e.treatment AS treatment,
       e.control AS control,
       e.coculture_partner AS coculture_partner,
       e.omics_type AS omics_type,
       e.is_time_course AS is_time_course,
       time_points,
       gene_count,
       significant_count
ORDER BY p.publication_year DESC, e.organism_strain, e.name
```

**WHERE clause construction:**

```python
where_clauses: list[str] = []
params: dict = {}

if publication:
    where_clauses.append(
        "(p.doi CONTAINS $pub OR p.title CONTAINS $pub)"
    )
    params["pub"] = publication

if organism:
    where_clauses.append(
        "(e.organism_strain CONTAINS $org OR e.coculture_partner CONTAINS $org)"
    )
    params["org"] = organism

if condition_type:
    where_clauses.append("e.treatment_type = $ctype")
    params["ctype"] = condition_type

if coculture_partner:
    where_clauses.append("e.coculture_partner CONTAINS $partner")
    params["partner"] = coculture_partner

if omics_type:
    where_clauses.append("e.omics_type = $otype")
    params["otype"] = omics_type.upper()

if keyword:
    # Uses full-text index if available, otherwise CONTAINS fallback
    where_clauses.append(
        "(e.name CONTAINS $kw OR e.treatment CONTAINS $kw "
        "OR e.control CONTAINS $kw OR e.experimental_context CONTAINS $kw)"
    )
    params["kw"] = keyword

if time_course_only:
    where_clauses.append("e.is_time_course = 'true'")
```

**Strategy notes:**
- Two-phase query: filter experiments first (cheap — ~100 nodes), then
  aggregate expression edges (heavier — ~188K edges but only for matched
  experiments)
- `OPTIONAL MATCH` on expression edges: experiments with no edges yet
  (shouldn't happen in practice) return 0 counts rather than being filtered
- Per-time-point grouping uses `collect({...})` map syntax — Neo4j 5+
  supports map literals in collect. Falls back to parallel arrays if needed
- `condition_type` param maps to `treatment_type` in Neo4j
- `organism` searches both `organism_strain` and `coculture_partner`
- No LIMIT — there are only ~100–120 experiments
- `time_points` collect may include a null entry for single-point experiments
  (where `time_point` is null on edges) — tool wrapper strips these

**Performance note:** Unfiltered query aggregates all ~188K edges. With
indexes on Experiment and the limited number of experiments, this should be
sub-second. If slow, per-time-point stats could be pre-computed as
post-import properties on Experiment — but premature optimization for now.

**Alternative: parallel arrays instead of map collect:**

If Neo4j version doesn't support `collect({...})` map syntax:

```cypher
WITH p, e,
     collect(DISTINCT r.time_point) AS tp_labels,
     collect(DISTINCT r.time_point_order) AS tp_orders,
     collect(DISTINCT r.time_point_hours) AS tp_hours
```

Then assemble the structured time_points in the tool wrapper Python code.
This is the safer approach — works with all Neo4j versions.

---

## Tool Wrapper Logic

**Files:** `tools.py`

The wrapper has post-query logic to assemble per-time-point stats if the
Cypher returns parallel arrays instead of map objects.

```python
@mcp.tool()
def list_experiments(ctx, publication=None, organism=None,
                     condition_type=None, coculture_partner=None,
                     omics_type=None, keyword=None,
                     time_course_only=False):
    conn = _conn(ctx)
    cypher, params = build_list_experiments(
        publication=publication, organism=organism,
        condition_type=condition_type,
        coculture_partner=coculture_partner,
        omics_type=omics_type, keyword=keyword,
        time_course_only=time_course_only,
    )
    results = conn.execute_query(cypher, **params)
    if not results:
        return _with_query("No experiments found.", cypher, params, ctx)

    # Strip null entries from time_points (single-point experiments)
    for row in results:
        if row.get("time_points"):
            row["time_points"] = [tp for tp in row["time_points"] if tp]

    return _with_query(_fmt(results), cypher, params, ctx)
```

**Alternative if using parallel arrays + Python assembly:**

```python
# If Cypher returns flat aggregates per experiment (no per-tp breakdown),
# run a second query to get per-tp stats for matched experiments:
def _build_time_point_stats(experiment_ids: list[str]) -> str:
    return (
        "UNWIND $exp_ids AS eid\n"
        "MATCH (e:Experiment {id: eid})-[r:Changes_expression_of]->(g:Gene)\n"
        "WITH e.id AS experiment_id, r.time_point AS label,\n"
        "     r.time_point_order AS tp_order, r.time_point_hours AS hours,\n"
        "     count(r) AS total,\n"
        "     count(CASE WHEN r.significant = 'significant' THEN 1 END) AS significant\n"
        "RETURN experiment_id, label, tp_order AS `order`, hours, significant, total\n"
        "ORDER BY experiment_id, tp_order"
    )
```

The tool wrapper would run the main query (experiment metadata), then the
stats query, then merge them in Python. This two-query approach is cleaner
than trying to do everything in one Cypher statement.

---

## Tests

### Unit tests

**`tests/unit/test_query_builders.py`:**
- [ ] `TestBuildListExperiments.test_no_filters` — valid Cypher, no WHERE
- [ ] `test_publication_filter` — WHERE has CONTAINS on doi OR title
- [ ] `test_organism_filter` — WHERE has CONTAINS on organism_strain OR
  coculture_partner
- [ ] `test_condition_type_filter` — WHERE has exact match on treatment_type
  (maps condition_type → treatment_type)
- [ ] `test_coculture_partner_filter` — WHERE has CONTAINS on coculture_partner
- [ ] `test_omics_type_filter` — WHERE has exact match, uppercased
- [ ] `test_keyword_filter` — WHERE has CONTAINS on name/treatment/control/context
- [ ] `test_time_course_only` — WHERE has is_time_course = 'true'
- [ ] `test_combined_filters` — multiple filters produce AND-joined WHERE

**`tests/unit/test_tool_wrappers.py`:**
- [ ] `TestListExperimentsWrapper.test_no_filters_returns_json`
- [ ] `test_empty_results` — returns "No experiments found."
- [ ] `test_null_time_points_stripped` — null entries removed from time_points
- [ ] `test_filters_passthrough` — all params forwarded to builder
- [ ] Tool registration count updated

### Integration tests (`tests/integration/test_tool_correctness_kg.py`)

- [ ] No filters → returns all ~100–120 experiments
- [ ] `organism="MED4"` → returns MED4 experiments
- [ ] `organism="HOT1A3"` → matches as both profiled and coculture partner
- [ ] `condition_type="coculture"` → coculture experiments only
- [ ] `coculture_partner="Alteromonas"` → narrows to Alteromonas cocultures
- [ ] `omics_type="PROTEOMICS"` → proteomics experiments only
- [ ] `publication="Biller 2018"` → experiments from that paper
- [ ] `time_course_only=True` → only experiments with is_time_course="true"
- [ ] `keyword="diel"` → matches on context/treatment fields
- [ ] Time-course experiments have time_points with >1 entry
- [ ] Each time_point entry has label, order, hours, significant, total
- [ ] gene_count and significant_count are > 0
- [ ] Known experiment: Aharonovich coculture MED4 has ~1696 genes

### Eval cases (`tests/evals/cases.yaml`)

```yaml
- id: list_experiments_all
  tool: list_experiments
  desc: All experiments returned when no filters
  params: {}
  expect:
    min_rows: 50
    columns: [experiment_id, name, publication_doi, organism_strain,
              condition_type, omics_type, is_time_course, gene_count]

- id: list_experiments_organism
  tool: list_experiments
  desc: Filter by organism
  params:
    organism: "MED4"
  expect:
    min_rows: 10
    columns: [experiment_id, organism_strain, gene_count]

- id: list_experiments_coculture_partner
  tool: list_experiments
  desc: Filter coculture experiments by partner
  params:
    condition_type: "coculture"
    coculture_partner: "Alteromonas"
  expect:
    min_rows: 3
    columns: [experiment_id, coculture_partner]
    contains:
      condition_type: "coculture"

- id: list_experiments_time_course
  tool: list_experiments
  desc: Time-course experiments only
  params:
    time_course_only: true
  expect:
    min_rows: 10
    columns: [experiment_id, is_time_course, time_points]

- id: list_experiments_proteomics
  tool: list_experiments
  desc: Proteomics experiments
  params:
    omics_type: "PROTEOMICS"
  expect:
    min_rows: 1
    columns: [experiment_id, omics_type]
    contains:
      omics_type: "PROTEOMICS"

- id: list_experiments_publication
  tool: list_experiments
  desc: Filter by publication
  params:
    publication: "Biller"
  expect:
    min_rows: 2
    columns: [experiment_id, publication_doi]
```

---

## Documentation Updates

| File | What to update |
|------|----------------|
| `CLAUDE.md` | Add row to MCP Tools table: `list_experiments` — experiments with time-point stats |
| `README.md` | Add entry to MCP tools section, bump tool count |
| `AGENT.md` | Add row to tools table |
| `docs/testplans/testplan.md` | Add test plan section |
